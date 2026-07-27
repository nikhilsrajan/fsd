# All file I/O flows through the `fsd.storage` (fsspec) seam

**Status:** accepted (spec 00 requirements interview; spec 10 / P1)

**Context.** v1 runs entirely on local disk, but the real end goal is to run at scale on Azure Blob
(and generically S3) **without cloud lock-in**. The legacy repos opened paths directly (`os.*`,
`boto3`), which would force a per-backend rewrite the moment I/O moved off the laptop.

**Decision.** Every module does file I/O through **`fsd.storage`** (fsspec): `open` / `exists` /
`makedirs` / `get` / `put` and a first-class, endpoint-generic `transfer(src, dst)`. No module opens
a path directly. The **one documented exception** is raster *pixel* reads, which go through
rasterio/GDAL VSI (`/vsicurl/`, `/vsis3/`, …) because GDAL owns that read path. Local backend now;
Azure Blob / S3 become **config** (protocol prefix + credentials), not code.

**Considered options.** Direct `os`/`boto3` per backend (legacy). Rejected: it hard-codes the
environment into every call site, re-appears in every new module, and is exactly the lock-in the
project exists to avoid.

**Consequences.** Switching a run to `abfss://…` or `s3://…` is a URL + config change, not a code
change. The "write to node-local scratch → `storage.transfer` → `fs.rename`" atomic-publish pattern
recurs wherever pixel I/O must land on a remote store — `cdse._push_scratch_to_remote`,
`datacube.builder._save_npy_atomic`, and `raster.cog.to_cog` (see ADR 0001). Direct `boto3` is
banned in favour of generic `s3fs` transport (any `endpoint_url`).
