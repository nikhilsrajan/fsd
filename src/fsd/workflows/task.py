"""The unit-of-work: build ONE datacube. Runner-agnostic, CLI-invokable.

Spec: specs/08-workflows.md, specs/10-storage-and-scale.md.

This is what an Azure Batch task (Phase 2) dispatches unchanged. It:
- reads its inputs (geometry + pre-sliced catalog) and writes its artifact via
  fsd.storage / the builder,
- knows nothing about how it was scheduled.

Run as:  python -m fsd.workflows.task <shapefilepath> <catalog_filepath>
             <startdate> <enddate> <export_folderpath>
             --bands B04,B08,B8A,SCL --mosaic-days 20
             --scl-mask-classes 0,1,3,7,8,9,10
"""

from __future__ import annotations

import argparse
import datetime

import geopandas as gpd
import pandas as pd

from fsd import config
from fsd.datacube import builder
from fsd.storage import fs


def run_task(
    shapefilepath: str,
    catalog_filepath: str,
    startdate: datetime.datetime,
    enddate: datetime.datetime,
    export_folderpath: str,
    *,
    bands: list[str],
    mosaic_days: int,
    scl_mask_classes: list[int],
    if_missing_files: str | None = "warn",
    njobs: int = 1,
    njobs_load_images: int = 1,
) -> None:
    """Build one datacube from a setup work-unit and save it to export_folderpath.

    `catalog_filepath` is the per-shape GeoParquet slice written by setup
    (`TileCatalog.filter` output — already date+overlap filtered, carries
    `area_contribution`); we band-flatten it and hand it to the builder.
    """
    shape_gdf = gpd.read_file(shapefilepath)
    subset_gdf = fs.read_parquet(catalog_filepath)
    flattened = builder.flatten_catalog(subset_gdf)

    builder.build_datacube(
        catalog_subset=flattened,
        shape_gdf=shape_gdf,
        startdate=startdate,
        enddate=enddate,
        bands=bands,
        mosaic_days=mosaic_days,
        scl_mask_classes=scl_mask_classes,
        export_folderpath=export_folderpath,
        njobs=njobs,
        njobs_load_images=njobs_load_images,
        if_missing_files=if_missing_files,
    )


def _parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="python -m fsd.workflows.task",
        description="Build a single Sentinel-2 L2A datacube (one work-unit).",
    )
    p.add_argument("shapefilepath", help="geometry.geojson for this shape")
    p.add_argument("catalog_filepath", help="per-shape catalog.parquet slice")
    p.add_argument("startdate", help="actual (tile-derived) start; ISO or 'YYYY-MM-DD'")
    p.add_argument("enddate", help="actual (tile-derived) end")
    p.add_argument("export_folderpath", help="where datacube.npy + metadata go")
    p.add_argument("--bands", required=True, help="comma-separated, e.g. B04,B08,B8A,SCL")
    p.add_argument("--mosaic-days", type=int, default=config.MOSAIC_DAYS)
    p.add_argument("--scl-mask-classes",
                   default=",".join(map(str, config.SCL_MASK_CLASSES)),
                   help="comma-separated SCL classes to mask")
    p.add_argument("--if-missing-files", default="warn",
                   choices=["raise_error", "warn", "none"])
    p.add_argument("--njobs", type=int, default=1)
    p.add_argument("--njobs-load-images", type=int, default=1)
    return p.parse_args(argv)


def main(argv=None) -> None:
    args = _parse_args(argv)
    run_task(
        shapefilepath=args.shapefilepath,
        catalog_filepath=args.catalog_filepath,
        startdate=pd.to_datetime(args.startdate),
        enddate=pd.to_datetime(args.enddate),
        export_folderpath=args.export_folderpath,
        bands=args.bands.split(","),
        mosaic_days=args.mosaic_days,
        scl_mask_classes=[int(v) for v in args.scl_mask_classes.split(",")],
        if_missing_files=None if args.if_missing_files == "none" else args.if_missing_files,
        njobs=args.njobs,
        njobs_load_images=args.njobs_load_images,
    )


if __name__ == "__main__":
    main()
