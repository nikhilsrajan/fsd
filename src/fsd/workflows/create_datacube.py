"""High-level batch entrypoint: setup work-units, then run via a runner.

Spec: specs/08-workflows.md. Preserves the demo_01 UX of run_create_datacube.

Setup pre-slices the big catalog once per shape (via TileCatalog.filter) so each
parallel build job reads only its small subset — no shared-file contention. The
per-row start/end dates are the *actual* tile-derived min/max (the median_mosaic
anchor, spec 04 caveat / TODO #2). This is the shape-centric workflow TODO #15 will
later optimize.
"""

from __future__ import annotations

import datetime
import os

import geopandas as gpd
import pandas as pd

from fsd.catalog.catalog import TileCatalog
from fsd.storage import fs
from fsd.workflows import runners

COL_ID = "id"
COL_LABEL = "label"


def setup(
    catalog_filepath: str,
    timestamp_col: str,
    shapefilepath: str,
    id_col: str,
    run_folderpath: str,
    startdate: datetime.datetime,
    enddate: datetime.datetime,
    bands: list[str],
    scl_mask_classes: list[int],
    mosaic_days: int,
    csv_filepath: str,
    label_col: str | None,
) -> None:
    """Per geometry: write geometry.geojson + catalog.parquet slice + input.csv row.

    Reuses `TileCatalog.filter` for the date+overlap slice (which also persists
    `area_contribution`). Shapes with no intersecting tiles are skipped with a note.
    """
    startdate = pd.to_datetime(startdate, utc=True)
    enddate = pd.to_datetime(enddate, utc=True)
    catalog = TileCatalog(catalog_filepath)
    shapes_gdf = gpd.read_file(shapefilepath)

    rows = []
    for _, srow in shapes_gdf.iterrows():
        shape_gdf = gpd.GeoDataFrame(
            {"geometry": [srow["geometry"].buffer(0)], COL_ID: [srow[id_col]]},
            crs=shapes_gdf.crs,
        )
        if label_col is not None:
            shape_gdf[COL_LABEL] = srow[label_col]

        # NOTE: re-reads the catalog per shape (TileCatalog.filter). Fine for v1
        # setup (not the hot path); a bulk single-read is a TODO #15 optimisation.
        subset = catalog.filter(shape_gdf, startdate, enddate)
        if subset.shape[0] == 0:
            print(f"[setup] skip id={srow[id_col]}: no tiles in range/overlap")
            continue

        actual_start = subset[timestamp_col].min()
        actual_end = subset[timestamp_col].max()
        export_folderpath = os.path.abspath(os.path.join(
            run_folderpath,
            f"{actual_start.strftime('%Y%m%d')}_{actual_end.strftime('%Y%m%d')}",
            str(srow[id_col]),
        ))
        fs.makedirs(export_folderpath)
        shape_path = os.path.join(export_folderpath, "geometry.geojson")
        catalog_path = os.path.join(export_folderpath, "catalog.parquet")
        shape_gdf.to_file(shape_path, driver="GeoJSON")
        fs.write_parquet(catalog_path, subset)

        row = {
            "shapefilepath": shape_path,
            "startdate": actual_start,
            "enddate": actual_end,
            "catalog_filepath": catalog_path,
            "export_folderpath": export_folderpath,
            "datacube_filepath": os.path.join(export_folderpath, "datacube.npy"),
            "images_count": int(subset.shape[0]),
            COL_ID: srow[id_col],
        }
        if label_col is not None:
            row[COL_LABEL] = srow[label_col]
        rows.append(row)

    if not rows:
        raise ValueError("setup produced no work-units (no shape had tiles in range).")

    input_df = pd.DataFrame(rows)
    input_df["added_on"] = pd.Timestamp.now(tz="UTC")
    input_df["mosaic_days"] = mosaic_days
    input_df["scl_mask_classes"] = ",".join(str(v) for v in scl_mask_classes)
    input_df["bands"] = ",".join(bands)

    if fs.exists(csv_filepath):
        with fs.open(csv_filepath, "r") as f:
            input_df = pd.concat([pd.read_csv(f), input_df], ignore_index=True)
    with fs.open(csv_filepath, "w") as f:
        input_df.to_csv(f, index=False)


def run_create_datacube(
    catalog_filepath: str,
    timestamp_col: str,
    shapefilepath: str,
    id_col: str,
    run_folderpath: str,
    startdate: datetime.datetime,
    enddate: datetime.datetime,
    bands: list[str],
    scl_mask_classes: list[int],
    mosaic_days: int,
    csv_filepath: str,
    label_col: str | None,
    cores: int,
    *,
    dry_run: bool = False,
    unlock: bool = False,
    overwrite_setup_csv: bool = True,
    runner: str = "local",
):
    """Run setup (unless csv exists), then dispatch the task via `runner`."""
    if overwrite_setup_csv and fs.exists(csv_filepath):
        fs.rm(csv_filepath)

    if not fs.exists(csv_filepath):
        setup(
            catalog_filepath=catalog_filepath, timestamp_col=timestamp_col,
            shapefilepath=shapefilepath, id_col=id_col, run_folderpath=run_folderpath,
            startdate=startdate, enddate=enddate, bands=bands,
            scl_mask_classes=scl_mask_classes, mosaic_days=mosaic_days,
            csv_filepath=csv_filepath, label_col=label_col,
        )

    if runner != "local":
        raise ValueError(f"Unknown runner={runner!r}; only 'local' exists in v1.")
    return runners.run_local(csv_filepath, cores=cores, dry_run=dry_run, unlock=unlock)
