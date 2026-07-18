# Spec 10 — Storage seam & scale-out (Azure-ready, cloud-agnostic)

New module + cross-cutting design. This spec exists so the **real end goal** —
running download + datacube creation **on Azure at scale via Azure Batch, without
cloud lock-in** — is reachable *additively* from the v1 local core, never as a
rewrite. **No Azure code ships in v1**; this spec defines the seams v1 must honor.

> **Pointer (2026-07-16):** MPC (`sources/mpc.py`, spec 32) is another first-class source through
> this same `fsd.storage` seam — its download is a pure `storage.transfer(signed_https, local)`
> byte-copy (fsspec `http` -> local), no S3-specific transport. Its Phase-2 realization (streaming
> MPC COGs in place on Azure vs copying to `rise`) is spec 31's retargeted scope.

## Principle

Lock-in risk lives in two places: **where files are** and **what schedules
compute**. Put both behind seams; keep everything else cloud-unaware.

## Seam 1 — Storage (`fsd/storage/fs.py`, via `fsspec`)

> **Realized for Azure by spec 31 (P1, 2026-07-17)** — the compute half (build + flatten
> reading/writing blob via `abfss://` + GDAL `/vsiadls/`; `fsd/storage/azure.py` +
> `fsd/raster/rio_open`). Download-to-blob is **suspended** into the ingest/normalization
> contract spec (fsd's own `mpc.py`/`cdse.py` keep their local-only guards in P1).

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
  rasterio work. Document this explicitly when implementing. **Realized (spec 31,
  P1): `fsd.raster.rio_open`** — a thin `rasterio.open` wrapper in the three
  pixel-read sites (`raster/images.py`, `raster/cog.py`, `catalog/stac.py`); local
  paths pass straight through, an `abfss://`/`az://` path routes to GDAL's
  `/vsiadls/` handler under a per-open refreshed token. No `get()`-to-scratch path
  was needed — streaming range-reads via VSI is the P4 Batch-node behavior wanted.

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
