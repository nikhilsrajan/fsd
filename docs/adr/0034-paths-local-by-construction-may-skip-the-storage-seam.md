# Paths that are local by construction may skip the storage seam

**Status:** accepted (spec 102 A9, 2026-10-09). Supersedes ADR 0003 in part: its "one documented exception"
clause.

**Context.** ADR 0003 routes all file I/O through `fsd.storage`, so a run moves from local disk to Azure Blob or
S3 by config alone. It names one exception: raster pixel reads through GDAL. By 2026-10 about 15 sites used the
standard library on paths that can only be local:
- the user config file;
- adapter source trees read to package a bundle;
- docker build contexts;
- node-local scratch directories, the scratch → `transfer` → `rename` pattern in ADR 0003's own Consequences;
- GDAL's temporary writes.

The refactor audit (#145) counted them as violations next to the sites the rule really exists for: paths that come
from a caller and may be a URL.

**Decision.** The exception covers raster pixel I/O through rasterio/GDAL, and paths that are **local by
construction**: temporary and scratch directories the process creates itself, the user config file, and source
trees read in order to package them. A path that comes from a caller, a CLI flag or config, and so may be a URL,
always goes through `fsd.storage`.

**Options rejected.**
- *Route every site through `fs`.* `fs` would need `mkdtemp`, `shutil` and GDAL-temp equivalents. That is more code
  for no change in behaviour, and fsspec itself keeps its process-local temporaries in the standard library's temp
  space.
- *Keep the rule and accept the exceptions silently.* The rule would then flag about 15 harmless sites in every
  audit and hide the few real ones.

**Consequences.** A reviewer asks one question of a direct `open`/`os` call: can this path ever be a URL? If it
can, it is a finding. Temp and scratch code stays plain standard library. Watch for a "local" path that starts
arriving from config: once it can, it moves to `fs`.
