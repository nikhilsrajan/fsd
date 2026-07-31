# Ingest stores raw DN and declares radiometry as metadata; it never bakes normalized pixels

**Status:** accepted (spec 34, Decision 1 — LOCKED 2026-07-20)

**Context.** A single XYZ URL over a multi-year mosaic that spans the 2022-01-25 processing-baseline
cutover must render **consistently** (pre-04.00 images otherwise look darker than ≥04.00 in RGB). The
legacy `apply_boa_offset` baked `clip(DN−1000, 0, 65535)` into the stored pixels — permanently lossy
in `(0,1000]`, it kills MPC's byte-copy, and it forces one scale on two consumers (science wants
physical reflectance, the viewer wants the bright ≥04.00 look).

**Decision.** Store **reflectance bands as raw DN, `uint16`, `nodata=0`** — no radiometric shift baked
into pixels. Carry radiometry as **metadata in two places**: the COG's internal **GDAL scale/offset
tag** (what titiler/rio-tiler `unscale=true` actually applies — STAC `raster:bands` are not forwarded
to the tiler) and **STAC `raster:bands` scale/offset** (what the builder and other tools read).
`offset = −1000` for baseline ≥ 04.00 else `0`; `scale = 1/10000`. The **builder** applies the offset
at read → physical reflectance; **titiler** applies the tag per-item before mosaicking. This retires
the bespoke `boa_add_offset` catalog column and closes #10/#30.

**Considered options.** **Bake-toward-old + clamp** (legacy) — lossy on disk *and* darkens the images
the user finds correct. **Bake-toward-new** (`DN+1000` on old data) — loss-free and bright, but still
re-encodes pre-2022 data, needs nodata masking, and still forces one scale on both consumers. Metadata
declaration dominates both on byte-copy, recomputability, and per-consumer scale.

**Consequences.** MPC stays a **byte-copy plus a cheap header-only metadata stamp** (no pixel decode);
CDSE gets the GDAL tag for free since it re-encodes anyway. The **archive is lossless** and the
**viewer is correct from one URL**. The *derived* science datacube still clips `clip(DN+offset,0,…)`
before the median mosaic — now a conscious, documented, recoverable choice (raw DN survives on disk),
not a silent bug. Every stored artifact declares its nodata (ingest sets `nodata=0` if the source
omits it).
