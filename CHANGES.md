# CHANGES vs legacy

Living record of how `fsd` differs from the legacy repos for behavior that **is**
carried over (renames, restructures, behavioral tweaks). Pure removals go in
`DROPPED.md`.

## Structure
- Three repos (`fetch_satdata` + `rsutils` + `cdseutils`) → one `src`-layout
  package `fsd` with functional modules: `sources/ catalog/ datacube/ bands/
  raster/ workflows/`.
- `cdseutils.*` → `fsd.sources.cdse` (+ shared bits in `fsd.config`).
- `rsutils.modify_images` (+ raster helpers from `rsutils.utils`) → `fsd.raster.images`.
- `rsutils.modify_bands` → `fsd.bands.modify`.
- `fetch_satdata.datacube.create_datacube_inmemory_single` → `fsd.datacube.builder`.
- `fetch_satdata.core.datacube_ops` → `fsd.datacube.ops`.
- `fetch_satdata.datacube.datacube_flatten_2d` → `fsd.datacube.flatten`.
- `fetch_satdata.workflows.create_datacube` + `setup_datacube_run` → `fsd.workflows.create_datacube`.

## Behavioral
- Catalog is the single file-based store (**GeoParquet**); the in-memory datacube
  builder reads it directly. No SQLite, no separate datacube/config DBs.
- Datacube builder is exposed behind a stable `build_datacube(...)` seam so an
  alternate engine (e.g. `rslearn`) can emit the same artifacts.
- **All file I/O via `fsspec`** (`fsd.storage`) — local in v1, Azure Blob / S3
  additive. No module touches raw paths directly.
- **S3 download generalized**: legacy's CDSE-private `boto3` download → a first-class,
  provider-agnostic S3 transport in `fsd.storage` (fsspec/`s3fs`, any `endpoint_url`:
  AWS, CDSE EODATA, MinIO…). CDSE keeps only STAC discovery + S2 file-selection. No
  direct `boto3`.
- Datacube creation restructured into **task + runner seam**: Snakemake becomes the
  *local* runner; the datacube task is CLI-invokable and runner-agnostic so an Azure
  Batch runner can dispatch it unchanged (Phase 2).
- CDSE catalog-query disk cache **removed** (always query live).
- Python floor raised 3.10 → **3.11**.
- Plotting / sklearn moved out of core into notebook extras.
- **`raster.images` parallel helpers run serially when `njobs == 1`** (no
  `multiprocessing.Pool`), instead of legacy's always-Pool. Same results; usable
  inside tests/other already-parallel contexts and avoids pickling/process
  overhead for the common single-job case. `njobs > 1` still uses a Pool.
- **`raster.images.reproject` now guards its output fill against `nodata=None`**
  (falls back to 0, matching the guard `resample_by_ref_meta` already had);
  legacy `reproject` would build an all-None-filled array if `nodata` was unset.
- `raster.images` follows the locked in-memory `(data, profile)` op convention for
  `crop`/`reproject`/`resample_by_ref_meta`/`merge_inplace` (the spec-phase scaffold
  had sketched some as file-in/file-out; corrected to match what the datacube
  builder actually chains via op `sequence`s).
- `bands.modify` carries only the demo-path ops (`modify_bands`,
  `mask_invalid_and_interpolate`, `compute_bands`, `remove_bands`, `scale_bands`) plus
  `expand_datacube`/`expand_flattened`. The `mask_interpolate` numba kernel that
  `mask_invalid_and_interpolate` needed (was in `rsutils.utils_preprocess`) is folded
  in as a private helper. All spectral indices from the legacy table are kept
  (NDVI/NDRE/GCVI/SAVI + NDWI/LSWI/BSI/PSRI/NDTI). Off-path ops deferred — see
  DROPPED.md (`median_mosaic`, `sav_gol`, `trim_bands`, `modify_bands_chunkwise`,
  preprocess-log (de)serialization).

## Kept identical (intentionally, for notebook portability)
- Datacube artifact format: `datacube.npy` + `metadata.pickle.npy` and the
  metadata dict keys.
- Flattened-data artifact set: `data.npy / ids.npy / labels.npy / metadata.pickle.npy`.
- 5-D band-array contract for `bands.modify`.
- Default bands, `scl_mask_classes`, `mosaic_days`, reference band B08, nodata 0.
