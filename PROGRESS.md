# PROGRESS — fsd

Resume anchor. Read this + `specs/00-overview.md` to pick up where we left off.

_Last updated: 2026-07-01_

## Where we are

Spec phase **complete and signed off**; package **scaffolded**; `storage` and
`catalog` **implemented and tested** (16 automated tests pass, ruff clean).

## Build order & status (from `specs/00-overview.md §7`)

| # | Module | Status |
|---|--------|--------|
| 0 | `config.py` | ✅ done (constants) |
| 1 | `storage/fs.py` | ✅ implemented · ✅ verified (`tests/test_storage.py` + manual `storage.md` Section A all pass; Section B = S3, needs creds, still manual) |
| 4 | `sources/cdse.py` | ✅ `CdseCredentials` + `query_catalog` + `download` implemented (18 tests, ruff clean). **Discovery pivoted to the CDSE STAC API (`pystac-client`, anonymous) — drops `sentinelhub` and the flaky S3 `.SAFE` listing (BUG-001)**; band S3 hrefs come from STAC `assets`. Metadata path live-verified (Ethiopia ROI, 138 tiles Jan–Mar 2018, highest-res selection + MTD_TL.xml). Byte `transfer` has fail-fast retry; **1-file smoke test DONE** (2026-07-01): B08_10m of T37PBP via `_download_one` → 45 MB, valid JP2 10980² uint16 EPSG:32637. Observed BUG-001 intermittency live (OTC endpoint `eodata.ams` worked for ls+GET while the GSLB alias failed; a bad window 403'd 5× then cleared) — validates the OTC pin. At-scale download + benchmarking = TODO #9. |
| 2 | `catalog/catalog.py` | ✅ implemented · ✅ verified (`tests/test_catalog.py`, 6 tests) |
| 3 | `raster/images.py` | ✅ implemented · ✅ verified (`tests/test_raster.py`, 24 tests; + RGB/GeoTIFF save helpers) |
| 3 | `bands/modify.py` | ✅ implemented · ✅ verified (`tests/test_bands.py`, 12 tests) |
| — | **real-data validation** (raster+bands) | ✅ `tests/manual/realdata.md` — TCC/FCC/NDVI on tile T33UWP confirmed in QGIS by user |
| 5 | `datacube/ops.py → builder.py → flatten.py` | ⬜ scaffolded stubs |
| 6 | `workflows/task.py · runners.py · create_datacube.py` + Snakefile | ⬜ scaffolded stubs |
| — | `notebooks/01_data_prep.ipynb` | ⬜ later |

## Next step (when resuming)

`sources/cdse.py` (module #4) is **implemented + tested** (STAC-based discovery, see
the status table). Remaining before moving on:

1. **Real download smoke test** — deferred: user is on limited hotspot data
   (2026-07-01). When on good bandwidth, run a **1-file/1-tile** download to confirm
   the byte `transfer` + retry path end-to-end (also covers `storage.md` Section B).
   Everything up to the bytes (STAC query, asset selection, catalog write) is already
   verified live / by mocked tests.
2. **Datacube module #5** (`datacube/ops.py → builder.py → flatten.py`) — the next
   build target; then augment `realdata.md` with the time-series datacube QGIS test.

CDSE discovery pivot (2026-07-01): dropped `sentinelhub` + the S3 `.SAFE` listing for
the **CDSE STAC API** (`pystac-client`, anonymous). STAC item `assets` give per-band
S3 hrefs directly → no recursive S3 listing (the BUG-001 failure). Only the byte
`transfer` touches S3 auth, wrapped in fail-fast retry. On-disk layout unchanged
(strip `.SAFE`, short `B02.jp2` names) = the `satellite/` folder layout.
Residual resilience items (circuit breaker, per-tile restructure) tracked in BUGS.md.

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
