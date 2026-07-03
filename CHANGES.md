# CHANGES vs legacy

Living record of how `fsd` differs from the legacy repos for behavior that **is**
carried over (renames, restructures, behavioral tweaks). Pure removals go in
`DROPPED.md`.

## Datacube throughput benchmark, Part 1 + `write_timings` seam (2026-07-03)
- **New (no legacy equivalent):** `benchmarks/datacube_throughput_sweep.py` — a reusable
  harness (spec 11 · Part 1) that sweeps build parallelism (`cores`) over the 100-grid ROI
  set and reports throughput + per-step timing + static grid×tile overlap. Baseline lives
  in `benchmarks/datacube_throughput_report.md` (+ `*_stats.json` for cross-run diffing).
- `datacube.builder.build_datacube` gained a **`write_timings: bool = False`** flag (off by
  default → no extra file in normal runs): when set, it writes a `timings.json` sidecar
  (per-phase wall-seconds + sizing counts) next to `datacube.npy`. The workflow enables it
  via the **`FSD_WRITE_TIMINGS=1`** env var (read in `workflows.task.main`), so the harness
  toggles it with zero runner/Snakefile plumbing. Phases are wrapped in a `_timed` ctx mgr.
- Read-path instrumentation (per-read parallel-reads / duration-vs-concurrency) is **not**
  here — deferred to Part 2 (spec 12); tile-splitting to Part 3 (spec 13).

## Workflows: task/runner split + fsd seams (2026-07-03)
- `workflows/create_datacube.py` + `setup_datacube_run.py` + the in-memory Snakefile →
  `fsd.workflows` as **task** (`task.py`, build one datacube, CLI `python -m
  fsd.workflows.task`) + **runner** (`runners.run_local`, drives the bundled Snakefile) +
  **entrypoint** (`create_datacube.run_create_datacube`: setup → runner). Same
  start.txt/done.txt sentinels + deterministic jitter.
- **Subset catalog is GeoParquet** (`catalog.parquet`) written via `TileCatalog.filter`
  (which already persists `area_contribution`), not legacy `catalog.geojson` + a separate
  `calculate_area_contribution` — the builder consumes the slice directly.
- **Task defaults `if_missing_files="warn"`** (legacy builder defaulted `raise_error`): at
  batch scale one partial-coverage shape shouldn't abort its job.
- **Snakemake and the task are invoked via `sys.executable -m …`** (not bare `snakemake`
  / `python`), so the workflow runs regardless of PATH / venv activation and the task
  always runs in the same interpreter as the runner.
- CLI passes `--bands` / `--scl-mask-classes` as **comma-strings** (single tokens) rather
  than legacy space-separated `nargs` (simpler Snakemake shell quoting).
- Added `storage.fs.rm` (delete through the seam; used to overwrite `input.csv`).

## Datacube builder: missing-band nodata fill shape (2026-07-02)
- Legacy `create_datacube_inmemory_single` filled a missing `(timestamp, band)` with
  `np.full((height, width), 0)` — a **2-D** array, while present bands are **3-D**
  `(1, H, W)` (rasterio single-band read). `np.stack`-ing them together would raise a
  shape error, and the fill defaulted to `float64` (promoting the whole cube). `fsd`
  fills with `(1, H, W)` in the present bands' dtype so the stack actually works.
- **Why it never bit legacy:** with `if_missing_files='raise_error'` (the default),
  any partially-missing band raises *before* stacking, so the buggy branch was
  unreachable. `fsd` fixes it so `warn`/`None` modes produce a valid cube. Same
  `datacube.npy` output on the complete-data path.

## Discovery: STAC API instead of Sentinel Hub (2026-07-01)
- Legacy discovered tiles via `sentinelhub.SentinelHubCatalog` (SH OAuth creds) and
  then listed each `.SAFE` over **S3** to find band files. `fsd` instead queries the
  **CDSE STAC API** (`pystac-client`, anonymous) and reads each item's `assets` to
  get the **per-band S3 hrefs directly** — no SH creds, no S3 listing.
- **Why:** the S3 `.SAFE` listing failed intermittently (`SignatureDoesNotMatch` /
  `InvalidAccessKeyId`) — a CDSE server-side issue (BUG-001). STAC sidesteps it; the
  only remaining S3-auth op is the per-file byte `transfer`, wrapped in fail-fast
  retry. Discovery no longer needs credentials at all.
- **Behavioral parity:** same catalog columns (`id, timestamp, geometry, s3url,
  cloud_cover`), same highest-res-per-band + `MTD_TL.xml` selection, same flattened
  on-disk layout. Note: STAC `item.id` has **no `.SAFE` suffix** (SH ids did); the
  `s3url` still carries `.SAFE`.

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
