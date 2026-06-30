"""Datacube builder — general seam + S2-L2A in-memory implementation.

Spec: specs/03-datacube.md. Folds in the working in-memory builder
(create_datacube_inmemory_single). `build_datacube` is the stable seam; an
alternate engine (e.g. rslearn) must emit the same datacube.npy + metadata.

Artifact contract (specs/00 §6):
  datacube.npy        : 4-D (timestamps|ids, height, width, bands)
  metadata.pickle.npy : {geotiff_metadata, timestamps, ids, bands,
                         data_shape_desc, geometry{shape, crs}, ...}
"""

from __future__ import annotations

import datetime

from fsd import config


def build_datacube(
    catalog_subset,            # band-flattened tiles for this shape
    shape_gdf,                 # single geometry (+ id, optional label)
    startdate: datetime.datetime,
    enddate: datetime.datetime,
    bands: list[str],
    *,
    mosaic_days: int = config.MOSAIC_DAYS,
    scl_mask_classes: list[int] | None = None,
    reference_band: str = config.REFERENCE_BAND,
    export_folderpath: str,
    njobs: int = 1,
    njobs_load_images: int = 1,
    if_missing_files: str = "raise_error",   # raise_error | warn | None
    max_timedelta_days: int = config.MAX_TIMEDELTA_DAYS,
) -> None:
    """Assemble one cloud-masked, time-mosaicked datacube and save it.

    Steps (specs/03): missing-files check -> load+crop -> dst_crs (max area
    contribution) -> reference profile (merge B08) -> resample to ref -> stack
    by timestamp x band -> SCL mask -> drop SCL -> median mosaic -> save.
    """
    raise NotImplementedError
