# fsd — Overview & Architecture Spec

> `fsd` is a clean-room rewrite that combines only the necessary parts of the
> legacy `fetch_satdata`, `rsutils`, and `cdseutils` repos into one small,
> tidy package. This document is the top-level spec; each module has its own
> small spec under `specs/`.

## 1. Goal

A minimal, clean Python package that can:

1. **Download** satellite tiles from a source (CDSE first; extensible later).
2. **Build datacubes** (per-geometry, time × band stacks) from downloaded tiles.
3. **Flatten** datacubes into model-ready training arrays.

Model **training** and **deployment** are *not* part of the core package — they
stay in user notebooks that import `fsd` (exactly as the legacy demo notebooks
imported the old package). See `specs/09-notebooks.md`.

### Real end goal (drives the architecture, not v1 scope)

Run download + datacube creation **on Azure at scale via Azure Batch**, **without
cloud lock-in**. We do *not* build Azure code in v1. Instead v1 is built on two
seams that make scale-out **additive** (see `specs/10-storage-and-scale.md`):

- **Storage seam (`fsspec`)** — all file I/O goes through `fsspec`; local backend
  now, Azure Blob (`adlfs`) / S3 / GCS become a config change later.
- **Runner seam over a CLI unit-of-work** — "build one datacube" is a standalone,
  CLI-invokable task. Snakemake is just the *local* runner; an Azure Batch runner
  (Phase 2) dispatches the **same** task.

### Phasing

| Phase | Contents |
|-------|----------|
| **1 (now)** | Clean local core: download → datacube → flatten + notebook 01. Built on the two seams. No Azure code. Snakemake = local runner. |
| **2** | Azure Batch runner dispatching the same datacube task; blob storage via `fsspec`. Cloud-agnostic by construction. |
| later | Port notebooks 02 (train) / 03 (deploy); ROI-splitting for country-scale ROIs. |

## 2. Non-negotiable constraints

- The legacy repos (`fetch_satdata/`, `rsutils/`, `cdseutils/`) are **read-only
  reference**. Never edit them.
- Every capability dropped or changed relative to legacy is recorded in
  `DROPPED.md` / `CHANGES.md`.

## 3. Locked decisions (from requirements interview)

| Area | Decision |
|------|----------|
| Scope | download → datacube → flatten (data-prep core only) |
| Satellite | Sentinel-2 **L2A only** (no L1C, no s2cloudless) |
| Source design | Thin seam + CDSE only (no plugin registry yet) |
| Datacube engine | General engine w/ clean seam (so OSS libs e.g. `rslearn` can be swapped/benchmarked); S2 L2A is the first & priority implementation |
| Orchestration | **Snakemake = local runner only**; runner is a swappable seam over a CLI datacube task (Azure Batch runner = Phase 2) |
| Storage | **`fsspec`** for all I/O; local backend in v1, blob/S3 additive |
| Catalog store | File-based **GeoParquet** (not SQLite, not GeoJSON) |
| Datacube format | `datacube.npy` + `metadata.pickle.npy` (pickle kept; metadata carries rasterio transform/CRS) |
| Flatten output | **keep `coords.npy`** (per-pixel easting/northing) |
| CDSE query cache | **removed** (always query live) |
| ROI splitting | **Deferred** to a later version (needed at country scale, not v1) |
| Azure in v1 | **Seams only, no Azure code** |
| Layout | Functional modules |
| Python / tooling | 3.11, pyproject + ruff + pytest |
| Testing UX | `notebooks/` exercises the *installed* package |

## 4. Package layout (src-layout, editable-installable)

```
fsd/
  pyproject.toml
  README.md
  DROPPED.md                 # living: what was dropped & why
  CHANGES.md                 # living: what changed vs legacy
  specs/                     # these documents
  src/fsd/
    __init__.py
    config.py                # constants: bands, default mask classes, nodata, urls
    sources/
      __init__.py
      base.py                # Source seam (interface/contract)
      cdse.py                # CDSE: credentials, catalog query, S3 tile download
    storage/
      __init__.py
      fs.py                  # fsspec-based open/exists/makedirs/put/get + first-class S3 transfer (s3fs, any endpoint); one entry for all I/O
    catalog/
      __init__.py
      catalog.py             # read/append/filter the file-based tile catalog (via storage)
    raster/
      __init__.py
      images.py              # crop / reproject / resample / merge / load (from rsutils.modify_images + utils)
    datacube/
      __init__.py
      builder.py             # general engine seam + S2-L2A in-memory builder
      ops.py                 # scl cloud mask, drop bands, median mosaic
      flatten.py             # datacube(s) -> 2D training arrays
    bands/
      __init__.py
      modify.py              # interpolate, spectral indices, remove/scale (from rsutils.modify_bands)
    workflows/
      __init__.py
      task.py                # the CLI unit-of-work: build ONE datacube (runner-agnostic)
      runners.py             # runner seam: local runner now; azure-batch later
      create_datacube.py     # high-level entrypoint (setup + run via a runner)
      _snakefiles/
        create_datacube/Snakefile   # the local runner's implementation
  notebooks/                 # uses installed fsd, mirrors demo_01..03
  tests/                     # pytest smoke tests
```

## 5. Module map → spec files

| Module | Spec | Folds in (legacy) |
|--------|------|-------------------|
| storage (fsspec seam) | `10-storage-and-scale.md` | new (cloud-agnostic I/O) |
| sources (seam + CDSE) | `01-sources.md` | `cdseutils/*`, `download/download_sentinel2_from_s3.py`, `core/sentinel2_via_s3.py` |
| catalog | `02-catalog.md` | catalog-writing parts of `sentinel2_via_s3.py`, `catalogmanager*` (file mode only) |
| datacube builder | `03-datacube.md` | `datacube/create_datacube_inmemory_single.py` |
| datacube ops | `04-datacube-ops.md` | `core/datacube_ops.py` (L2A subset) |
| flatten | `05-flatten.md` | `datacube/datacube_flatten_2d.py` |
| bands | `06-bands.md` | `rsutils/modify_bands.py` |
| raster | `07-raster.md` | `rsutils/modify_images.py`, `rsutils/utils.py` |
| workflows (task + runner seam) | `08-workflows.md` | `workflows/create_datacube.py`, `setup_datacube_run.py`, snakefile |
| notebooks/tooling | `09-notebooks.md` | demo notebooks, `pyproject.toml` |
| storage & scale (fsspec + runners + Azure phasing) | `10-storage-and-scale.md` | new |

## 6. Core data contracts (shared across modules)

These types/shapes are the seams between modules — keep them stable.

- **All file I/O** goes through `fsd.storage` (fsspec) — paths may be local or
  remote URLs; no module opens files directly.
- **Tile catalog** (GeoDataFrame persisted as **GeoParquet**): columns
  `id, satellite, timestamp, s3url, local_folderpath, files, cloud_cover, geometry`.
  One row per downloaded tile; `files` = comma-joined band filenames present on disk.
- **Datacube** = 4-D `np.ndarray` `(timestamps|ids, height, width, bands)`.
- **Datacube metadata** (pickled dict):
  `geotiff_metadata (rasterio profile incl. transform/crs), timestamps, ids, bands, data_shape_desc, geometry{shape, crs}` (+ `mosaic_index_intervals`, `previous_timestamps` after mosaicking).
- **Flattened training data**: `data.npy (pixels, timestamps, bands)`, `coords.npy (pixels, 2)` (kept), `ids.npy`, `labels.npy` (optional), `metadata.pickle.npy`.
- **Defaults** (`config.py`): `BANDS_DEFAULT = [B02,B03,B04,B05,B06,B07,B08,B11,B12,SCL]`,
  `SCL_MASK_CLASSES = [0,1,3,7,8,9,10]`, `MOSAIC_DAYS = 20`, `REFERENCE_BAND = B08`, `NODATA = 0`.

## 7. Build order (proposed)

1. `config` + `storage` (fsspec seam) + `raster` + `bands` (leaf utilities).
2. `catalog` (GeoParquet via `storage`).
3. `sources/cdse` (depends on catalog + config + storage).
4. `datacube/ops` → `datacube/builder` → `datacube/flatten`.
5. `workflows`: `task` (CLI unit-of-work) → `runners` (local) → `create_datacube`.
6. `notebooks` + `tests`.

## 8. Resolved decisions & remaining open questions

Resolved (were OQ-1/2/4): catalog = **GeoParquet**; flatten **keeps `coords.npy`**;
CDSE query cache **removed**. Storage = **fsspec**; Snakemake = **local runner
only**; **no Azure code in v1**.

- **OQ-3 (open):** `sources/base.py` — abstract `Source` ABC now, or just a
  documented function-signature contract? Recommendation: documented signature now
  (matches "thin seam"); promote to ABC when a 2nd source appears.
