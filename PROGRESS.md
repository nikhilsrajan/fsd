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
| 2 | `catalog/catalog.py` | ✅ implemented · ✅ verified (`tests/test_catalog.py`, 6 tests) |
| 3 | `raster/images.py`, `bands/modify.py` | ⬜ scaffolded stubs |
| 4 | `sources/cdse.py` | ⬜ scaffolded stub |
| 5 | `datacube/ops.py → builder.py → flatten.py` | ⬜ scaffolded stubs |
| 6 | `workflows/task.py · runners.py · create_datacube.py` + Snakefile | ⬜ scaffolded stubs |
| — | `notebooks/01_data_prep.ipynb` | ⬜ later |

## Next step (when resuming)

1. Implement module #3: `raster/images.py` (read/crop/resample/merge band rasters)
   and `bands/modify.py` (band math on 5D arrays) per `specs/07-raster.md` +
   `specs/06-bands.md`. These are the building blocks the datacube builder consumes.
2. (when creds handy) Run `tests/manual/storage.md` Section B against CDSE S3.

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
