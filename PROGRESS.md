# PROGRESS — fsd

Resume anchor. Read this + `specs/00-overview.md` to pick up where we left off.

_Last updated: 2026-06-30_

## Where we are

Spec phase **complete and signed off**; package **scaffolded**; first module
(`storage`) **implemented** and **partially verified** by hand.

## Build order & status (from `specs/00-overview.md §7`)

| # | Module | Status |
|---|--------|--------|
| 0 | `config.py` | ✅ done (constants) |
| 1 | `storage/fs.py` | ✅ implemented · 🟡 manual verify in progress (`tests/manual/storage.md` §0,A1,A2 pass; A3–A8 + Section B pending) |
| 2 | `catalog/catalog.py` | ⬜ scaffolded stub |
| 3 | `raster/images.py`, `bands/modify.py` | ⬜ scaffolded stubs |
| 4 | `sources/cdse.py` | ⬜ scaffolded stub |
| 5 | `datacube/ops.py → builder.py → flatten.py` | ⬜ scaffolded stubs |
| 6 | `workflows/task.py · runners.py · create_datacube.py` + Snakefile | ⬜ scaffolded stubs |
| — | `notebooks/01_data_prep.ipynb` | ⬜ later |

## Next step (when resuming)

1. Finish running `tests/manual/storage.md` Section A (and Section B if creds handy);
   report any mismatch so `storage/fs.py` can be fixed.
2. (optional) Mirror Section A into automated `tests/test_storage.py`.
3. Implement `catalog/catalog.py` (GeoParquet `TileCatalog`) on top of the storage seam.

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
