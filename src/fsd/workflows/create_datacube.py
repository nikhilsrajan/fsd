"""High-level batch entrypoint: setup work-units, then run via a runner.

Spec: specs/08-workflows.md. Preserves the demo_01 UX of run_create_datacube.

Setup reads the catalog once, then pre-slices it per shape (via `catalog.filter_gdf`)
so each parallel build job reads only its small subset — no shared-file contention. The
per-row start/end dates are the *actual* tile-derived min/max (the median_mosaic
anchor, spec 04 caveat / TODO #2). This is the shape-centric workflow TODO #15 will
later optimize.
"""

from __future__ import annotations

import concurrent.futures
import datetime
import io
import os
import time

import geopandas as gpd
import pandas as pd

from fsd import config
from fsd.catalog.catalog import TileCatalog, filter_gdf
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
    mosaic_scheme: str = config.MOSAIC_SCHEME,
    max_concurrent: int = config.SETUP_MAX_CONCURRENT,
) -> None:
    """Per geometry: write geometry.geojson + catalog.parquet slice + input.csv row.

    Reads the catalog **once**, then reuses `catalog.filter_gdf` for each shape's
    date+overlap slice (which also persists `area_contribution`). Shapes with no
    intersecting tiles are skipped with a note. Prints live progress + ETA: the
    per-shape writes are network I/O on a remote run folder, so this can run for
    minutes and must not look like a hang.

    Shapes are prepared concurrently (`max_concurrent` threads) because that work is
    latency-bound blob I/O, not CPU. `input.csv` row order still follows the
    shapefile's order. Pass `max_concurrent=1` for the old serial behaviour.

    The mosaic anchor written to each row is the caller's `startdate`/`enddate` (not
    the per-shape actual acquisition min/max), so every shape mosaics on the same
    calendar grid and the resulting cubes share a `timestamps` axis that `flatten` can
    concatenate (spec 15). The per-shape actual dates are still used for the run-folder
    name only.
    """
    startdate = pd.to_datetime(startdate, utc=True)
    enddate = pd.to_datetime(enddate, utc=True)
    # D6a (spec 36, TODO #40): read via fsd.storage + BytesIO -- a local path behaves
    # exactly as before (fsd.storage routes file:// transparently), and this closes the
    # last raw-path geometry read that a cluster node (no `shapefiles/` checkout) can't do.
    with fs.open(shapefilepath, "rb") as f:
        shapes_gdf = gpd.read_file(io.BytesIO(f.read()))

    # Read the catalog ONCE for the whole run, then filter it in memory per shape
    # (`filter_gdf`). `TileCatalog.filter` re-reads the file on every call, which on a
    # remote catalog made setup cost one full download per shape: 900 shapes over
    # `abfss://` = 900 downloads of the same ~121 KiB parquet (~106 MiB, ~900 VPN
    # round-trips) before a single job was submitted. Same rows out, one read in.
    catalog_gdf = TileCatalog(catalog_filepath).read()

    n_shapes = len(shapes_gdf)
    print(f"[setup] catalog read once: {len(catalog_gdf)} rows, for {n_shapes} shapes",
          flush=True)

    t0 = time.time()
    last_print = 0.0

    def _tick(done: int, force: bool = False) -> None:
        """Live progress + ETA -- setup does per-shape network I/O and can run for
        many minutes on a remote run folder; silence is indistinguishable from a hang."""
        nonlocal last_print
        now = time.time()
        if not force and now - last_print < 2.0:
            return
        last_print = now
        elapsed = now - t0
        rate = done / elapsed if elapsed > 0 and done else 0.0
        eta = f"{(n_shapes - done) / rate:.0f}s" if rate else "?"
        pct = 100 * done / n_shapes if n_shapes else 100.0
        print(f"[setup] {done}/{n_shapes} shapes ({pct:.0f}%) | {rate:.1f} shapes/s "
              f"| elapsed {elapsed:.0f}s | eta {eta}", flush=True)

    def _prepare(srow) -> dict | None:
        """One shape's control files + its input.csv row. Pure per-shape work: it
        touches only this shape's own folder, and reads (never mutates) the shared
        `catalog_gdf` — which is what makes the pool below safe."""
        shape_gdf = gpd.GeoDataFrame(
            {"geometry": [srow["geometry"].buffer(0)], COL_ID: [srow[id_col]]},
            crs=shapes_gdf.crs,
        )
        if label_col is not None:
            shape_gdf[COL_LABEL] = srow[label_col]

        subset = filter_gdf(catalog_gdf, shape_gdf, startdate, enddate)
        if subset.shape[0] == 0:
            print(f"[setup] skip id={srow[id_col]}: no tiles in range/overlap", flush=True)
            return None

        actual_start = subset[timestamp_col].min()
        actual_end = subset[timestamp_col].max()
        export_folderpath = os.path.join(
            run_folderpath,
            f"{actual_start.strftime('%Y%m%d')}_{actual_end.strftime('%Y%m%d')}",
            str(srow[id_col]),
        )
        if fs.is_local(export_folderpath):
            # os.path.abspath is only meaningful (and safe) for a local path — on a
            # URL (e.g. abfss://...) it would corrupt the host/scheme (specs/31 §6).
            export_folderpath = os.path.abspath(export_folderpath)
        fs.makedirs(export_folderpath)
        shape_path = os.path.join(export_folderpath, "geometry.geojson")
        catalog_path = os.path.join(export_folderpath, "catalog.parquet")
        # D6a (spec 36): write via fsd.storage rather than gpd.to_file(path) directly, so
        # this per-unit geometry lands correctly on a remote export_folderpath too.
        with fs.open(shape_path, "w") as f:
            f.write(shape_gdf.to_json())
        fs.write_parquet(catalog_path, subset)

        row = {
            "shapefilepath": shape_path,
            # Calendar anchor = the caller's window (spec 15), not per-shape actual
            # acquisition min/max — so all shapes mosaic on the same grid. actual_start/
            # actual_end are used above for the run-folder name only.
            "startdate": startdate,
            "enddate": enddate,
            "catalog_filepath": catalog_path,
            "export_folderpath": export_folderpath,
            "datacube_filepath": os.path.join(export_folderpath, "datacube.npy"),
            "images_count": int(subset.shape[0]),
            COL_ID: srow[id_col],
        }
        if label_col is not None:
            row[COL_LABEL] = srow[label_col]
        return row

    # Threads, not processes: every shape costs ~4-7 tiny blob round-trips
    # (`makedirs` + `geometry.geojson` + the `catalog.parquet` slice), so the loop is
    # latency-bound and the GIL is released for the duration of each call. Same
    # pattern `sources.mpc.download`/`download_shard` already run concurrently through
    # `fsd.storage` against blob. Measured 2026-07-22: 900 shapes serially = ~1.8
    # s/shape (~27 min) on `rise` over VPN.
    #
    # Results are placed BY INDEX and compacted afterwards, so `input.csv` row order
    # is the shapefile's order regardless of completion order — parallelism must not
    # change the manifest. (An exception in a worker still propagates out of
    # `fut.result()`, as before; the pool's `__exit__` lets in-flight shapes finish
    # first, so slightly more work lands before it surfaces.)
    prepared: list[dict | None] = [None] * n_shapes
    _tick(0, force=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_concurrent) as pool:
        futures = {
            pool.submit(_prepare, srow): i
            for i, (_, srow) in enumerate(shapes_gdf.iterrows())
        }
        done = 0
        for fut in concurrent.futures.as_completed(futures):
            prepared[futures[fut]] = fut.result()
            done += 1
            _tick(done)

    rows = [r for r in prepared if r is not None]
    _tick(n_shapes, force=True)

    if not rows:
        raise ValueError("setup produced no work-units (no shape had tiles in range).")

    input_df = pd.DataFrame(rows)
    input_df["added_on"] = pd.Timestamp.now(tz="UTC")
    input_df["mosaic_days"] = mosaic_days
    input_df["mosaic_scheme"] = mosaic_scheme
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
    mosaic_scheme: str = config.MOSAIC_SCHEME,
    dry_run: bool = False,
    unlock: bool = False,
    overwrite_setup_csv: bool = True,
    runner: str = "local",
    runner_kwargs: dict | None = None,
):
    """Run setup (unless csv exists), then dispatch the task via `runner`.

    `runner_kwargs` (spec 36 D3) is forwarded to `runners.run_aml` when `runner="aml"`
    (e.g. `cluster=`, `environment=`, `root=`, `identity_client_id=`) -- the local runner
    takes no extra kwargs, so it is ignored for `runner="local"`.
    """
    if overwrite_setup_csv and fs.exists(csv_filepath):
        fs.rm(csv_filepath)

    if not fs.exists(csv_filepath):
        setup(
            catalog_filepath=catalog_filepath, timestamp_col=timestamp_col,
            shapefilepath=shapefilepath, id_col=id_col, run_folderpath=run_folderpath,
            startdate=startdate, enddate=enddate, bands=bands,
            scl_mask_classes=scl_mask_classes, mosaic_days=mosaic_days,
            csv_filepath=csv_filepath, label_col=label_col, mosaic_scheme=mosaic_scheme,
        )

    if runner == "local":
        return runners.run_local(csv_filepath, cores=cores, dry_run=dry_run, unlock=unlock)
    if runner == "aml":
        return runners.run_aml(csv_filepath, **(runner_kwargs or {}))
    raise ValueError(f"Unknown runner={runner!r}; valid values: 'local', 'aml'.")
