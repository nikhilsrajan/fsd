# Remote-dst COG publishing lives in `raster.cog.to_cog`, not its callers

**Status:** accepted (2026-07-23, spec 38 / P4)

**Context.** At scale (Mode C) fsd must write Cloud-Optimized GeoTIFFs to blob from two sites — the
per-cell `output.tif` on an AML node (`model.engine._write_output_cog`) and the driver-side `merged.tif`
(`api._merge_outputs`) — but `to_cog` was **local-dst only** (TODO #17): it uses `os.makedirs` /
`rasterio.open(mode="w")` / `os.replace` on the destination path, which fails on an `abfss://` URL.

**Decision.** Extend the single `raster.cog.to_cog` chokepoint to be remote-dst-aware — when `dst` is a
remote `fsd.storage` URL, convert on node-local scratch, `storage.transfer` to a remote `.part`, then
`fs.rename` onto the final path (atomic, reusing the spec-36 D7 rename primitive). `engine` and `api`
remain **unchanged callers** that get blob destinations for free.

**Considered options.** Put the remote branch in `engine._write_output_cog` (the initial spec-38 draft).
Rejected: it fixes only the per-cell `output.tif` and **misses** `merged.tif` (which also calls `to_cog`
and also breaks on blob), and it pushes storage-seam knowledge into the model layer.

**Consequences.** The "pixel I/O is local; publish via the seam" exception (`CLAUDE.md`) now lives in the
raster layer where the pixel I/O already is — the third instance of that pattern after
`cdse._push_scratch_to_remote` and `datacube.builder._save_npy_atomic`. The same remote-`to_cog` is
reusable for the deferred remote-dst *download* COG (TODO #15b). `cdse`'s `to_cog` calls always target
local scratch, so they are unaffected.
