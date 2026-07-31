# STAC is a thin, additive export view over the GeoParquet catalog — not the store

**Status:** accepted (spec 17, signed off + implemented + verified 2026-07-06)

**Context.** STAC is the interchange standard the serving stack (pgSTAC + titiler-pgstac) and other
tools speak, but the pipeline's **query** store is GeoParquet (ADR 0006). The choice is whether STAC
*replaces* the store or *rides alongside* it.

**Decision.** Adopt STAC **now, but deliberately thin**: `catalog/stac.py` + `TileCatalog.to_stac`
provide an **additive export view** generated from the GeoParquet catalog. GeoParquet remains the
canonical query format; STAC is a projection of it, not a second source of truth.

**Considered options.** **Make STAC the store** — rejected: heavier, and STAC/JSON is not the columnar
query format the pipeline needs. **No STAC at all** — rejected: loses standard interchange and the
titiler-pgstac serving path.

**Consequences.** The serving path consumes the STAC export without the pipeline depending on a STAC
database. Declared radiometry rides in the STAC `raster:bands` fields (ADR 0011), so the export is how
downstream tools learn the scale/offset. STAC stays cheap to regenerate from the catalog.
