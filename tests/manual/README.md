# Manual test guides

Step-by-step runbooks you read and execute by hand to verify a module against its
spec. One file per module; they grow over time — ask to **augment** a file when you
want more checks.

| Guide | Module | Spec |
|-------|--------|------|
| `storage.md` | `fsd.storage.fs` | `specs/10-storage-and-scale.md` |
| `realdata.md` | `fsd.raster.images` + `fsd.bands.modify` (real tile, QGIS) | `specs/07-raster.md`, `06-bands.md`, `09-notebooks.md` |
| `debug_s3paths.md` | _superseded_ — BUG-001 S3 listing debug (the STAC pivot removed S3 listing) | `../../BUGS.md` |

These complement (don't replace) automated `pytest` in `tests/`. Use a manual guide
for credentialed / remote / exploratory checks; deterministic local checks are also
good candidates for automation when you want them hands-free.
