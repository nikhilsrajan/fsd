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
| **ROI → S2-grid tiling** via s2geometry (`rsutils.s2_grid_utils.get_s2_grids_gdf`) | rsutils | **LANDED (spec 19, 2026-07-06)** | ported clean-room into **`fsd.grid.roi_to_s2_grids`** (polyfill convex hull @ res 11 → keep intersecting → scale 1.1 → `gpd.overlay` clip; cols `id`,`geometry`). `s2`+`s2cell` in the optional **`[grid]`** extra (core stays lean). Used by the end-to-end demo (`demos/`). **Still deferred: the `run_inference(roi=…)` front-end** (ROI→tiling→download→build→infer in one verb) = **P4** — the demo chains the steps explicitly. | **P4** front-end wiring; also very large ROIs |
| **SQLite** catalog stack (`CatalogManager`, `sqlite_db_utils`, configs/geometries/datacube DBs, config-id registry, IOU dedup) | fetch_satdata | superseded | replaced by file-based catalog | concurrent-write scaling needed |
| File-staging datacube engine (`core/create_datacube.py`, intermediate tiffs in working_dir) | fetch_satdata | superseded | replaced by in-memory builder | — |
| Legacy **`rio_cogeo`/`cog_translate`** COG write in the deploy worker (`model/demo_model_deploy.py::write_cog`) | fetch_satdata | superseded | replaced by fsd's single COG home `raster.cog.to_cog` (lossless DEFLATE+PREDICTOR, NBITS=16, atomic, overviews) used by both COG-on-download (spec 14) and inference outputs (spec 18) | — |
| Sentinel-Hub **Process API** download (`download_data*`, evalscripts) | cdseutils | dropped | v1 uses S3 tile download only | small on-the-fly composites needed |
| CDSE catalog-query **disk cache** | cdseutils | dropped | decision: always query live | API rate/cost becomes a problem |
| Direct **boto3** S3 client | cdseutils | superseded | replaced by generic fsspec/`s3fs` transport (any endpoint) | s3fs hits a CDSE edge case → boto3 `transfer` backend |
| CDSE username/password creds | cdseutils | dropped | already unused (SH + S3 keys suffice) | — |
| `sentinelhub` dependency (catalog search via `SentinelHubCatalog` + SH OAuth creds + SH base/token URLs) | cdseutils | dropped | replaced by anonymous CDSE STAC API (`pystac-client`); STAC items also give per-band S3 hrefs, removing the flaky `.SAFE` S3 listing (BUG-001) | a CDSE service needs SH OAuth |
| S3 recursive `.SAFE` listing (`fs.glob`/boto3 `filter(Prefix=)`) for file-selection | cdseutils/fetch_satdata | dropped | STAC item `assets` provide the band hrefs directly; avoids the intermittent S3 auth failures (BUG-001) | STAC stops exposing per-band assets |
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

## Approaches tried inside fsd and reverted

Not legacy carry-overs — things fsd built, ran, and removed. Recorded here because each one will
look like a good idea again, and the code they were removed from now carries only a pointer
(`docs/reference/code-comments.md`: cut the changelog, keep the hazard).

### The `InvalidBlockList` write retry (`storage/fs.py`, reverted 2026-07-28, #57 → #58)

`_write_with_retry` retried any write whose error message looked like a transient Azure
block-commit race. **It fixed nothing, and made diagnosis worse.**

The failure it was built for was duplicate work-unit ids making 16 threads write the *same* blob
(spec 21 D-GRID-1). That collision is deterministic, so every writer simply retried into every
other writer — turning a fast, legible failure into a minutes-long error storm that buried the real
cause. The actual fix was to refuse duplicate ids at the source (`create_datacube.setup`).

No transient adlfs race has ever been observed here: run-book 36 wrote 900 distinct blobs at the
same 16-way concurrency, same VPN, same account, in 71 s with zero errors.

**If you reintroduce it:** match only Azure storage error codes, never adlfs's
`"Failed to upload block"` prefix — that comes from a catch-all `except Exception` in
`adlfs/spec.py::_async_upload_chunk`, so every write failure wears it, permanent auth/RBAC ones
included.
