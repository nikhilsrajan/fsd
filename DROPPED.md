# DROPPED & DEFERRED

Living record of capabilities present in the legacy repos (`fetch_satdata`,
`rsutils`, `cdseutils`) that are **not** carried into `fsd` v1, so future versions
can reconsider them. Add a row whenever something is intentionally left out.

Status: `dropped` (no plan) · `deferred` (intended later) · `superseded` (replaced).

| Item | From | Status | Reason | Reconsider when |
|------|------|--------|--------|-----------------|
| Sentinel-2 **L1C** path | fetch_satdata, cdseutils | dropped | v1 is L2A-only | an L1C use-case returns |
| **s2cloudless** cloud masking (`run_s2cloudless`, CMK `apply_cloud_mask`) | datacube_ops | dropped | L1C-only; heavy dep | L1C re-added |
| **Planet** datacube path (`create_planet_*`) | fetch_satdata | dropped | was a simpler same-CRS/same-res special case; not a download source | a uniform-grid source is needed |
| **SSH / cluster fetch** (`fetch_from_cluster`, `sshutils`, `sshcreds`) | fetch_satdata | dropped | infra-specific tile transfer | multi-machine workflow returns |
| **ESA WorldCover / WorldCereal** TIF generators | fetch_satdata scripts | dropped | reference-data tooling, not core | reference layers needed in-repo |
| **ROI splitting** via s2geometry (`rsutils.s2_grid_utils`) | rsutils | **deferred** | needed for country-scale memory limits, but not v1 | building datacubes for very large ROIs |
| **SQLite** catalog stack (`CatalogManager`, `sqlite_db_utils`, configs/geometries/datacube DBs, config-id registry, IOU dedup) | fetch_satdata | superseded | replaced by file-based catalog | concurrent-write scaling needed |
| File-staging datacube engine (`core/create_datacube.py`, intermediate tiffs in working_dir) | fetch_satdata | superseded | replaced by in-memory builder | — |
| Sentinel-Hub **Process API** download (`download_data*`, evalscripts) | cdseutils | dropped | v1 uses S3 tile download only | small on-the-fly composites needed |
| CDSE catalog-query **disk cache** | cdseutils | dropped | decision: always query live | API rate/cost becomes a problem |
| Direct **boto3** S3 client | cdseutils | superseded | replaced by generic fsspec/`s3fs` transport (any endpoint) | s3fs hits a CDSE edge case → boto3 `transfer` backend |
| CDSE username/password creds | cdseutils | dropped | already unused (SH + S3 keys suffice) | — |
| `rsutils` grab-bag: plotting, `rich_data_filter`, `utils_preprocess`, `esa_download`, `s2`/`s2cell` helpers | rsutils | dropped | not on the data-prep path; plotting belongs in notebooks | per-need |
| `scripts_tobedeleted/*`, `*_old.py` | fetch_satdata | dropped | dead code | — |
| Unused snakefiles (planet, malawi mask, demo_model_deploy, legacy s2l2a) | fetch_satdata | dropped | keep only in-memory S2 datacube snakefile | — |
| `modify_bands.median_mosaic` (window/step) + numba kernel | rsutils | deferred | distinct from the datacube builder's `datacube_ops.median_mosaic`; not on the demo band-math path | a training-time rolling mosaic is needed |
| `modify_bands.sav_gol` (Savitzky–Golay smoothing) | rsutils | deferred | not used by demo 01/02 band sequences | temporal smoothing wanted in prep |
| `modify_bands.trim_bands` | rsutils | deferred | not used by demos | timestamp trimming needed as an op |
| `modify_bands.modify_bands_chunkwise` | rsutils | deferred | memory-scaling chunked apply for huge flattened arrays; training is a notebook (out of core) | large-array band math hits memory limits |
| `modify_bands.generate_preprocess_log_*` / `generate_sequence_from_preprocess_log` | rsutils | deferred | preprocess-sequence (de)serialization for reproducibility; not on the demo band path | persisting/replaying a preprocessing recipe is needed |
| `rsutils.utils_preprocess` grab-bag (cloud-mask, SAR scaling, patch-finding) except the `mask_interpolate` kernel | rsutils | dropped | only `mask_interpolate` is needed (folded into `bands.modify`); rest is off-path | per-need |

> When reconsidering an item, link the spec that re-introduces it.
