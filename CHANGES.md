# CHANGES vs legacy

Living record of how `fsd` differs from the legacy repos for behavior that **is**
carried over (renames, restructures, behavioral tweaks). Pure removals go in
`DROPPED.md`.

## STAC export view of the tile catalog (spec 17 / P0, 2026-07-06)
- **New (additive), `TileCatalog` GeoParquet schema unchanged:** `src/fsd/catalog/stac.py` maps
  catalog rows → **STAC Items** (one Item per tile-product acquisition, one asset per band file)
  and writes a **static, self-contained STAC catalog (JSON)** via `pystac`, through the
  `fsd.storage` seam. `TileCatalog.to_stac(dst)` is the convenience entrypoint.
- **Pure-metadata by default:** `proj:code` (EPSG) is derived from the **MGRS tile in the product
  id** (e.g. `T37PBP`→`EPSG:32637`), so `to_stac` reads **no rasters** (579-tile benchmark → 579
  items in 0.06 s, both UTM zones correct). Per-asset `proj:shape`/`proj:transform` are opt-in
  (`read_proj=True`). Media types by extension (COG for `.tif`); `eo:cloud_cover` from
  `cloud_cover`; `MTD_TL.xml` as a metadata asset; source `.SAFE` as a `via` link.
- **Round-trippable:** `stac.items_to_rows(...)` reconstructs the catalog columns losslessly.
- `pystac` promoted to a **direct** dependency (was transitive via `pystac-client`).
  `stac-geoparquet` deferred (add when pgstac/TiTiler needs it). Advances TODO #14 (STAC half).

## High-level API façade — `fsd.*` verbs (spec 16 / P0, 2026-07-06)
- **New (additive), no behavior change to existing modules:** `src/fsd/api.py` adds the
  user-facing verbs `fsd.download`, `fsd.create_training_data` (+ `run_inference` / `deploy`
  stubs, `compute_n_timestamps`, `TrainingData`, `PreflightError`), re-exported at top level so
  `import fsd; fsd.create_training_data(...)` works. It is a **façade** over
  `sources.cdse` / `workflows.create_datacube` / `datacube.flatten` — the legacy-derived
  entrypoints (`run_create_datacube`, `flatten`) are unchanged and still public.
- **Scope raised (ROADMAP §2.5):** `create_training_data` hides `input.csv` + the word
  "flatten"; the user provides label polygons + a catalog and gets back
  `data/ids/labels/coords/metadata`.
- **Seams present from day one:** every verb takes `runner="local"` / `storage=None`; non-local
  values raise (Azure Batch / blob land in P1/P2 as config, not API changes).
- **Preflight (ROADMAP §2.6):** cheap checks (window/`T`/bands/columns/catalog) run *before*
  any download or build and raise `PreflightError`, aggregating all failures.
- **`feature_sequence` / `aggregate`** are pinned in the `create_training_data` signature but
  raise `NotImplementedError` until P0.5 (ModelAdapter). Version bumped `0.0.1 → 0.1.0`.

## Calendar-interval median mosaic — new default (spec 15, 2026-07-05)
- **Behavior change (kept-but-changed): `median_mosaic` now buckets acquisitions into fixed
  calendar windows by default** (`mosaic_scheme="calendar"`, `config.MOSAIC_SCHEME`). Windows are
  `[startdate + k·mosaic_days, …)` over `[startdate, enddate)`; **labels are window-start
  boundaries** (not the first acquisition date); **empty windows are emitted as all-nodata slices**.
  So every datacube built over the same `startdate`/`enddate`/`mosaic_days` has an **identical
  `timestamps` axis regardless of tile/orbit/UTM zone** — which is what lets `flatten` (spec 05)
  concatenate cubes across a multi-tile training set. `mosaic_scheme="acquisition"` restores the
  exact legacy labeling (first-acquisition labels, occupied buckets only, gap-opens-interval quirk).
- **Resolves the TODO #2 anchor caveat.** The workflow `create_datacube.setup` now threads the
  **caller's calendar `startdate`/`enddate`** into each work-unit's mosaic anchor (the per-shape
  actual acquisition min/max is kept only for the run-folder name). Previously it threaded the
  actual first/last acquisition, so windows shifted shape-to-shape.
- **Threading:** `mosaic_scheme` added to `build_datacube`, `workflows.task` (`--mosaic-scheme`
  CLI, default from config), `create_datacube.setup`/`run_create_datacube` (+ an `input.csv`
  column), and the bundled Snakefile. Boundary rule is half-open `[lo, hi)` (a timestamp on a
  boundary lands in the later window; the final window is upper-inclusive so a timestamp exactly at
  `enddate` isn't dropped) — differs from legacy's `<=` walk only for an on-boundary timestamp.
- **Ripple:** mosaic timestamp *labels* change (calendar boundaries), but the pixel groupings /
  medians for a dense window are unchanged, so `datacube.md`'s numeric NDVI references still hold;
  the runbook carries a note. Legacy outputs are reproducible via `mosaic_scheme="acquisition"`.
- **Known limitation logged (TODO #16):** `flatten` concatenates per-cube `coords.npy` but a
  multi-zone training set mixes eastings/northings from different UTM zones (west→32636, east→32637)
  — fine as pixel identifiers, wrong if used spatially. Not fixed here.

## satellite_benchmark migrated JP2 → COG in place (spec 14 follow-up, 2026-07-04)
- **Data change (not code):** the real test archive `satellite_benchmark/` was converted from
  native JP2 to **COG (+ overviews), in place** — every `Bxx.jp2` → `Bxx.tif`, the `.jp2` deleted
  (no duplicate copies), and its `catalog.parquet` `files` column rewritten to `.tif`. 2316 band
  files, 0 failed, lossless (bit-identical verified); archive grew 94 → 159 GiB (COG+overviews ≈
  1.70× JP2). Downstream is unaffected — rasterio reads `.tif` transparently, so datacube builds /
  throughput runs work unchanged (they now read COG, i.e. faster; see the throughput runbook note).
- **New tool `benchmarks/migrate_jp2_to_cog.py`** (reusable): in-place JP2→COG migrator built on
  `fsd.raster.cog.to_cog`. Resumable (skips already-`.tif`), disk-safety floor (aborts before free
  space hits `--floor-gib`), live progress bar + ETA, catalog resynced from actual on-disk state,
  and a `--verify {full,quick,none}` pre-delete gate (default `quick` = readback + shape/dtype +
  overviews check; `full` re-decodes for bit-identical). Conversion is memory-bandwidth-bound → 8
  workers (the perf cores) is the knee; 10 gave no gain.

## COG-on-download — native ingest format (spec 14, 2026-07-04)
- **Behavior change (kept-but-changed): `sources.cdse.download` now converts each fetched JP2
  band to a lossless COG by default** (`cog: bool = True`). On-disk band files are `Bxx.tif`
  (was `Bxx.jp2`) and the catalog `files` column records `.tif`. `cog=False` restores the exact
  prior behavior (native `Bxx.jp2`). Turns the spec-13 finding (COG builds 1.58×–3.46× faster,
  lossless) into the ingest default so downloads are build-fast from the start.
- **COGs carry overviews** (`OVERVIEWS="AUTO"`) for the future TiTiler XYZ/WMTS goal (TODO #14).
  The datacube build reads full-res and never uses them; they cost ~+38% on top of base COG (so
  ingest COGs are ~1.7× JP2 storage — a deliberate tiling-readiness cost, not a build cost).
- **New `src/fsd/raster/cog.py::to_cog`** — one canonical local raster → COG primitive: lossless
  (DEFLATE + PREDICTOR=2; `NBITS=16` promotes S2's declared 15-bit depth so PREDICTOR=2 is legal —
  pixels unchanged), **atomic** (`.part` + `os.replace`, mirroring `storage.transfer`), optional
  overviews, optional `verify` (bit-identical read-back). COG profile constants live in `config`.
- **Download flow:** a band is fetched to a local staging sibling (`Bxx.tif.src.jp2`) via
  `storage.transfer`, converted with `to_cog`, staging removed; `MTD_TL.xml` transfers as-is.
  Idempotency keys on the final `.tif`; a crash leaves at most the staging JP2 (atomic convert),
  so resume re-fetches cleanly. Conversion runs inline in the existing S3 worker threads (GDAL
  releases the GIL) — a dedicated conversion process pool is a noted future optimization.
- **Seam boundary:** `cog=True` requires a **local** `root_folderpath`; a remote (`s3://`/`az://`)
  dst raises a clear error (the stage-local→convert→upload path is deferred to the Azure milestone).
- **`benchmarks/prep_cog_dataset.py` refactored** to delegate its conversion to `to_cog` (one
  source of truth for the COG profile); behavior identical (it still pins `OVERVIEWS="NONE"`).
- The read/build/datacube/workflow path is untouched — rasterio reads `.tif` transparently (spec 13).

## COG vs JP2 storage/time experiment (spec 13, 2026-07-04)
- **New (no legacy equivalent), no `src/fsd/` change:** measures what storing S2 tiles as
  **COG** vs native **JP2** buys in build time and costs in disk. Three additive benchmark
  scripts + harness CLI knobs; the read path is already format-agnostic (rasterio detects
  JP2/GTiff), so the switch is pure data + catalog.
  - `benchmarks/prep_cog_dataset.py` — converts the first N months of `satellite_benchmark`
    JP2 → **base COG** (DEFLATE + PREDICTOR=2, tiled 512, **no overviews**) into a mirror tree
    `satellite_benchmark_cog/` + a parallel `catalog.parquet`. Lossless: `NBITS=16` promotes S2's
    declared 15-bit depth (in a uint16 container) so PREDICTOR=2 is legal — pixel values
    unchanged; a bit-identical assert guards it. Includes a **disk pre-flight** (sample-estimate +
    free-space check, aborts before writing) and live progress/ETA. Emits `cog_vs_jp2_storage.md`
    (JP2 → base COG → COG+overviews, overview row estimated from a sample).
  - `datacube_throughput_sweep.py` gained **`--catalog` / `--start` / `--end` / `--tag`** so the
    Part-1/2 harness A/Bs JP2 vs COG with non-clobbering tagged outputs (report/stats/figures).
    Report image links now derive from `FIG_DIR` (tag-aware); added a `STATS` constant (replaces
    the fragile `FIG_DIR.replace("_figures", …)` derivation).
  - `benchmarks/compare_cog_jp2.py` — merges the two tagged `stats.json` + storage json into the
    team report `cog_vs_jp2_report.md`: time table, the **JP2-vs-COG duration-vs-concurrency
    overlay** (the decode-bound test), storage table, verdict.
  - Runbook `tests/manual/cog_experiment.md`. Measured on this data: base COG ≈ **1.23× JP2**
    (S2 JP2 barely out-compresses DEFLATE), overview delta ~+38%.

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

## Datacube throughput benchmark, Part 2 — per-read instrumentation (2026-07-04)
- `datacube.builder.build_datacube` gained a **`write_read_log: bool = False`** flag (off by
  default → no extra file), mirroring `write_timings`. When set (and `njobs_load_images == 1`)
  it times each windowed read with **wall-clock `time.time()`** (comparable across grid
  processes) and writes a **`reads.jsonl`** sidecar next to `datacube.npy` — one row per read:
  `id` (grid), `mgrs_tile`, `product_id`, `band`, `filepath`, epoch `start`/`end`, `duration`.
  The workflow enables it via **`FSD_WRITE_READ_LOG=1`** (read in `workflows.task.main`). With
  `njobs_load_images > 1` the log is skipped with a `RuntimeWarning` (reads fan out to a Pool).
  The load loop was refactored: `_load_images` returns `(catalog_gdf, data_profile_list, reads)`
  and, on the logging path, reads each file serially via new `_load_images_logged`.
- `benchmarks/datacube_throughput_sweep.py` gained a **`--read-log`** flag (spec 12): it sets
  the env var, collects every grid's `reads.jsonl`, and computes **read conflicts** (overlapping
  read pairs from different grids), a **read-duration-vs-concurrency** curve (the direct test of
  the "parallel reads block each other" hypothesis), and a **same-file / same-tile / different-
  tile** classification — only *same-file* conflicts are what Part-3 tile-splitting can remove.
  Adds a "Read contention" section + 4 plots to the same living report and a `read_contention`
  block per `cores` to `stats.json`. Pure analysis (`conflict_stats`, `duration_vs_concurrency`,
  `_annotate_reads`) is unit-tested; `--read-log` is off by default so the baseline is unchanged.
- Concurrency is **instantaneous peak-in-flight** (bounded by `cores`), not overlap-degree — the
  metric the hypothesis needs. Tile-splitting itself stays deferred to Part 3 (spec 13).

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
