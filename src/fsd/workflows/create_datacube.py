"""High-level batch entrypoint: setup work-units, then run via a runner.

Spec: specs/08-workflows.md. Preserves the demo_01 UX of run_create_datacube.
"""

from __future__ import annotations

import datetime


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
    """Per geometry: write geometry.geojson + subset catalog + an input.csv row."""
    raise NotImplementedError


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
    raise NotImplementedError
