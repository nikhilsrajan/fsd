# Spec 10 — Storage seam & scale-out (Azure-ready, cloud-agnostic)

New module + cross-cutting design. This spec exists so the **real end goal** —
running download + datacube creation **on Azure at scale via Azure Batch, without
cloud lock-in** — is reachable *additively* from the v1 local core, never as a
rewrite. **No Azure code ships in v1**; this spec defines the seams v1 must honor.

## Principle

Lock-in risk lives in two places: **where files are** and **what schedules
compute**. Put both behind seams; keep everything else cloud-unaware.

## Seam 1 — Storage (`fsd/storage/fs.py`, via `fsspec`)

- Every read/write in the package goes through this module — no other module calls
  `open`, `os.path.exists`, `np.save(path)`, `gpd.read_*(path)` on a raw path.
- `fsspec` gives one API over `file://` (local, v1), `az://`/`abfs://` (Azure Blob
  via `adlfs`, Phase 2), `s3://`, `gs://`. Backend is chosen by URL scheme + a
  credentials/`storage_options` config — **a config change, not a code change**.
- Minimal surface:
  ```python
  open(path, mode, **storage_options)        # context manager, any backend
  exists(path) / makedirs(path)
  put(local, remote) / get(remote, local)    # for tools needing real local files
  save_npy(path, arr) / load_npy(path)
  read_parquet(path) / write_parquet(path, gdf)

  # first-class S3-compatible transport (decision):
  transfer(src_url, dst_url, *, src_options=None, dst_options=None, njobs=1)
  ls(url, **storage_options) / glob(pattern, **storage_options)
  ```

### S3-compatible object stores are first-class (decision)

Any S3-compatible store is just an fsspec filesystem (`s3fs`) configured with
`endpoint_url` + keys via `storage_options` — **AWS** (`s3://...`, no endpoint),
**CDSE EODATA** (`endpoint_url=https://eodata.dataspace.copernicus.eu`), **MinIO**,
**Wasabi**, etc. So:

- A **tile download = `transfer(src_s3_url, dst_url)`** — copy from a source S3
  filesystem to the destination (local in v1, Azure Blob in Phase 2). The transport
  is **provider-agnostic and reusable**; users and future sources can call it
  directly (not buried inside CDSE).
- `boto3` is **not** used directly; `s3fs` (aiobotocore) is the one S3 stack. (If a
  CDSE edge case ever needs it, a boto3-backed `transfer` is a drop-in behind the
  same signature — the source code above it doesn't change.)
- **rasterio caveat:** rasterio reads remote rasters via GDAL VSI (`/vsicurl/`,
  `/vsiaz/`), not fsspec. The raster module (`07`) must accept either a real local
  path or a VSI path; the task may `get()` a tile to local scratch before heavy
  rasterio work. Document this explicitly when implementing.

## Seam 2 — Compute (task + runner, see `08-workflows.md`)

- **Unit-of-work** = build one datacube. CLI-invokable
  (`python -m fsd.workflows.task ...`), self-contained, storage-agnostic via Seam 1.
- **Runner** consumes the work-unit list and runs the task across it. v1: local
  (Snakemake). Phase 2: Azure Batch (each row → one Batch task running the same CLI
  on a pool VM, reading/writing blob via Seam 1). Other backends (k8s, AWS Batch)
  are then just more runners.
- What scales on Azure Batch = **datacube creation** (parallel over geometries).
  **Download** stays a single quota-bound job (CDSE caps concurrency at 4) writing
  tiles to shared storage that the Batch tasks read.

## v1 obligations (so Phase 2 is additive)

1. All I/O through `fsd.storage`; no raw path I/O anywhere else.
2. `fsd.workflows.task` is pure, CLI-invokable, and reads/writes only via storage.
3. Paths are treated as URLs (scheme-aware), not assumed local.
4. Credentials/`storage_options` passed via config, never hard-coded.

## Explicitly Phase 2 (NOT in v1)
- `adlfs`/Azure Blob wiring, Azure Batch pool/job/task submission, container image
  for Batch nodes, blob-backed scratch management.

## Tests (v1)
- `fsd.storage` round-trips npy/parquet/text on the **local** backend.
- A datacube task run end-to-end using only `fsd.storage` paths (local) — proving no
  module bypasses the seam.
- (design check) grep/lint guard: no direct `open(`/`np.save(`/`gpd.read_file(` on
  paths outside `fsd.storage`.
