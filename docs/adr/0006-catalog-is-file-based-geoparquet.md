# The tile catalog is a file-based GeoParquet store

**Status:** accepted (spec 00 requirements interview; spec 02)

**Context.** The legacy `fetch_satdata` used a SQLite stack — `CatalogManager`, separate
config/geometry/datacube DBs, a config-id registry, and IOU dedup. It is stateful, needs a live DB
process/file lock, and does not sit naturally on object storage.

**Decision.** The catalog is a **file-based GeoParquet** read/queried via `TileCatalog`, and it is
read and written **through the storage seam** (ADR 0003) like every other artifact. Not SQLite, not
GeoJSON.

**Considered options.** **SQLite** (legacy) — superseded; reconsider only when concurrent-write
scaling is genuinely needed. **GeoJSON** — rejected: it is an interchange format, not a columnar
query format, and does not scale to catalog-sized row counts.

**Consequences.** The catalog lives on blob alongside the imagery — no separate database tier to
provision on the cluster. A STAC representation is an **additive export view**, not a second store
(see ADR 0016). The reconsider trigger is concurrent-write scaling; the retired SQLite dedup/registry
capabilities are recorded in `DROPPED.md`.
