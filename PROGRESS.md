# PROGRESS — fsd

Resume anchor. Read this + `specs/00-overview.md` to pick up where we left off.

_Last updated: 2026-06-30_

## Where we are

Spec phase **complete and signed off**; package **scaffolded**; `storage` and
`catalog` **implemented and tested** (16 automated tests pass, ruff clean).

## Build order & status (from `specs/00-overview.md §7`)

| # | Module | Status |
|---|--------|--------|
| 0 | `config.py` | ✅ done (constants) |
| 1 | `storage/fs.py` | ✅ implemented · ✅ verified (`tests/test_storage.py` + manual `storage.md` Section A all pass; Section B = S3, needs creds, still manual) |
| 4 | `sources/cdse.py` | 🟡 `CdseCredentials` done + tested (`tests/test_cdse.py`, 8 tests: from_json/to_json/from_env, masked repr, s3_storage_options, require_complete, is_expired). **NEXT: `query_catalog` + `download`.** |
| 2 | `catalog/catalog.py` | ✅ implemented · ✅ verified (`tests/test_catalog.py`, 6 tests) |
| 3 | `raster/images.py` | ✅ implemented · ✅ verified (`tests/test_raster.py`, 24 tests; + RGB/GeoTIFF save helpers) |
| 3 | `bands/modify.py` | ✅ implemented · ✅ verified (`tests/test_bands.py`, 12 tests) |
| — | **real-data validation** (raster+bands) | ✅ `tests/manual/realdata.md` — TCC/FCC/NDVI on tile T33UWP confirmed in QGIS by user |
| 4 | `sources/cdse.py` | ⬜ scaffolded stub |
| 5 | `datacube/ops.py → builder.py → flatten.py` | ⬜ scaffolded stubs |
| 6 | `workflows/task.py · runners.py · create_datacube.py` + Snakefile | ⬜ scaffolded stubs |
| — | `notebooks/01_data_prep.ipynb` | ⬜ later |

## Next step (when resuming) — REPRIORITIZED: download before datacube

Build **`sources/cdse.py` (module #4)** first and test it, *then* the datacube
(module #5). Rationale (user, 2026-07-01): download is the actual first pipeline step.

CDSE implementation plan (grounded in legacy `cdseutils/{utils,sentinel2}.py` +
`fetch_satdata/.../sentinel2_via_s3.py`, all re-read):
1. ✅ **DONE** — `CdseCredentials`: `from_json` (reads legacy `cdse_credentials.json`
   keys), `to_json`, `from_env` (cloud/Batch path), `s3_storage_options`,
   `require_complete`, `is_expired`, secret-masking `__repr__`. Canonical local format
   = gitignored `secrets/cdse_credentials.json` (NOT mysecrets.py; agreed + spec 01
   updated). User's real file verified to load (values never printed).
2. `query_catalog(roi, start, end, creds, max_cloudcover)`: ROI → convex-hull bbox in
   WGS84 → `sentinelhub.SentinelHubCatalog.search(collection=S2L2A, bbox, time)` →
   gdf `{id, timestamp, geometry, s3url=res['assets']['data']['href'],
   cloud_cover=res['properties']['eo:cloud_cover']}` → `sjoin` keep intersecting →
   **assert id uniqueness**. No cache (decision).
3. Port the **file-selection** logic from `cdseutils/sentinel2.py` (pure, testable):
   `parse_s3url`, `sentinel2_id_parser`, `parse_band_filename`,
   `select_s3paths_to_download` (L2A: pick **highest-res per band** + `MTD_TL.xml`),
   `s3url_to_download_folderpath`. Replace legacy `boto3` object-listing with
   `fsd.storage.ls` (s3fs, CDSE endpoint); the byte copy is `fsd.storage.transfer`.
4. `download(...)`: query → `max_tiles` guard (raise, est ~0.725 GB/tile) → per tile
   `ls` the `.SAFE`, select files, `transfer` to `root_folderpath` (skip existing =
   idempotent), **chunked** catalog append, **cap concurrency at 4** (CDSE quota).

Confirmed: legacy's on-disk layout (`s3url_to_download_folderpath` → strip `.SAFE`,
save bands as short `B02.jp2` etc.) is EXACTLY the `satellite/` folder layout already
present — so fsd downloads should reproduce that tree.

**Testing needs CDSE creds** (SH id/secret + S3 keys) — ask user. Real test = tiny
1-file/1-tile download (not 700 MB); this also covers `storage.md` Section B.
Then: datacube module #5, then augment `realdata.md` with the time-series datacube test.

**Test geometries** (`shapefiles/`, EPSG:4326): `s2grid=476da24.geojson` = Austria tile
T33UWP, single-tile (used for raster/bands realdata.md, done). `s2grid=165bca4.geojson`
= Ethiopia ROI (lon ~36.2/lat ~11.6) straddling the **36°E UTM zone boundary** → pulls
S2 tiles in **both EPSG:32636 & 32637** = THE multi-tile/multi-CRS test for CDSE download
+ datacube creation (its tiles aren't in `satellite/` yet, so download must run first).

## Decisions log (all locked unless noted)

- Scope: download → datacube → flatten. Train/deploy stay in notebooks.
- Sentinel-2 **L2A only**. **GeoParquet** catalog. Keep **Snakemake** as the *local*
  runner only. Keep `coords.npy`. CDSE query cache **removed**.
- Storage = **fsspec** seam (local now; blob/S3 additive). S3 transport **first-class
  & generic** (s3fs, any endpoint); no direct boto3.
- Real end goal: Azure Batch scale-out, **cloud-agnostic** — achieved via the storage
  seam + a runner-agnostic CLI datacube task. **No Azure code in v1.**
- OQ-3 **resolved**: source contract is a documented function signature (no ABC) until
  a 2nd source exists.
- Hard constraint: never edit `fetch_satdata/`, `rsutils/`, `cdseutils/` (read-only
  reference). Keep `DROPPED.md` / `CHANGES.md` current.

## Key files
- Design: `specs/00..10`. Living docs: `DROPPED.md`, `CHANGES.md`.
- Implemented: `src/fsd/config.py`, `src/fsd/storage/fs.py`.
- Manual tests: `tests/manual/` (one guide per module).
- Cross-session memory: see `MEMORY.md` entries `fsd-*`.

## Environment note
Deps are **not** in system Python. Dev setup:
`python3.11 -m venv .venv && source .venv/bin/activate && pip install -e ".[dev]"`.
