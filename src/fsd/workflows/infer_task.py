"""The ROI-inference unit-of-work: build ONE datacube, then infer it to a COG.

Spec: specs/21-roi-inference-verb.md (P0.75).

A superset of `fsd.workflows.task`: the *same* datacube build, plus a model-inference step
that loads the bundle **once per task** and writes `output.tif` alongside the datacube. This is
the **per-cell build+infer** work-unit an Azure Batch node dispatches unchanged at P4 — the
reason inference goes through the runner seam rather than a separate process pool.

The model must be a **bundle** (it crosses a subprocess boundary); `run_inference(roi=…)`
auto-saves a live adapter to one.

Run as:  python -m fsd.workflows.infer_task <shapefilepath> <catalog_filepath>
             <startdate> <enddate> <export_folderpath>
             --bands B04,B08,B8A,SCL --mosaic-days 20
             --scl-mask-classes 0,1,3,7,8,9,10
             --bundle <bundle_path> --output <output.tif>
"""

from __future__ import annotations

import argparse
import datetime
import os

import pandas as pd

from fsd import config
from fsd.datacube import ops
from fsd.model import bundle as _bundle
from fsd.model import engine
from fsd.workflows import task as _task


def run_infer_task(
    shapefilepath: str,
    catalog_filepath: str,
    startdate: datetime.datetime,
    enddate: datetime.datetime,
    export_folderpath: str,
    *,
    bands: list[str],
    mosaic_days: int,
    scl_mask_classes: list[int],
    bundle_path: str,
    output_filepath: str,
    mosaic_scheme: str = config.MOSAIC_SCHEME,
    if_missing_files: str | None = "warn",
    njobs: int = 1,
    njobs_load_images: int = 1,
    predict_batch_size: int | None = None,
    skip_nan: bool = True,
) -> str:
    """Build the cell's datacube (reuses `task.run_task`) then infer it to `output_filepath`.

    Returns the output COG path. The bundle is loaded once here (one cell per task); heavy
    models amortise this by covering K cells per task (a future granularity knob, spec 21).
    """
    _task.run_task(
        shapefilepath=shapefilepath,
        catalog_filepath=catalog_filepath,
        startdate=startdate,
        enddate=enddate,
        export_folderpath=export_folderpath,
        bands=bands,
        mosaic_days=mosaic_days,
        scl_mask_classes=scl_mask_classes,
        mosaic_scheme=mosaic_scheme,
        if_missing_files=if_missing_files,
        njobs=njobs,
        njobs_load_images=njobs_load_images,
    )
    datacube_filepath = os.path.join(export_folderpath, "datacube.npy")
    adapter = _bundle.load(bundle_path)
    return engine.infer_datacube_to_cog(
        adapter, datacube_filepath, output_filepath,
        predict_batch_size=predict_batch_size, skip_nan=skip_nan,
    )


def _parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="python -m fsd.workflows.infer_task",
        description="Build one datacube and infer it to a COG (one ROI-inference work-unit).",
    )
    p.add_argument("shapefilepath", help="geometry.geojson for this cell")
    p.add_argument("catalog_filepath", help="per-cell catalog.parquet slice")
    p.add_argument("startdate", help="calendar-window start; ISO or 'YYYY-MM-DD'")
    p.add_argument("enddate", help="calendar-window end")
    p.add_argument("export_folderpath", help="where datacube.npy + metadata go")
    p.add_argument("--bands", required=True, help="comma-separated, e.g. B04,B08,B8A,SCL")
    p.add_argument("--mosaic-days", type=int, default=config.MOSAIC_DAYS)
    p.add_argument("--mosaic-scheme", default=config.MOSAIC_SCHEME,
                   choices=list(ops.MOSAIC_SCHEMES))
    p.add_argument("--scl-mask-classes",
                   default=",".join(map(str, config.SCL_MASK_CLASSES)),
                   help="comma-separated SCL classes to mask")
    p.add_argument("--if-missing-files", default="warn",
                   choices=["raise_error", "warn", "none"])
    p.add_argument("--njobs", type=int, default=1)
    p.add_argument("--njobs-load-images", type=int, default=1)
    p.add_argument("--bundle", required=True, help="model bundle path")
    p.add_argument("--output", required=True, help="output COG path")
    p.add_argument("--predict-batch-size", type=int, default=None)
    p.add_argument("--no-skip-nan", action="store_true",
                   help="predict on every pixel (default skips all-NaN pixels)")
    return p.parse_args(argv)


def main(argv=None) -> None:
    args = _parse_args(argv)
    run_infer_task(
        shapefilepath=args.shapefilepath,
        catalog_filepath=args.catalog_filepath,
        startdate=pd.to_datetime(args.startdate),
        enddate=pd.to_datetime(args.enddate),
        export_folderpath=args.export_folderpath,
        bands=args.bands.split(","),
        mosaic_days=args.mosaic_days,
        scl_mask_classes=[int(v) for v in args.scl_mask_classes.split(",")],
        bundle_path=args.bundle,
        output_filepath=args.output,
        mosaic_scheme=args.mosaic_scheme,
        if_missing_files=None if args.if_missing_files == "none" else args.if_missing_files,
        njobs=args.njobs,
        njobs_load_images=args.njobs_load_images,
        predict_batch_size=args.predict_batch_size,
        skip_nan=not args.no_skip_nan,
    )


if __name__ == "__main__":
    main()
