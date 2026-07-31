# One COG chokepoint: `raster.cog.to_cog`

**Status:** accepted (spec 14 COG-on-download, 2026-07-04; spec 18 inference outputs; `DROPPED.md`)

**Context.** The legacy code wrote Cloud-Optimized GeoTIFFs in more than one place with its own
settings — notably `rio_cogeo`/`cog_translate` in the deploy worker (`model/demo_model_deploy.py::
write_cog`) — so COG conventions (compression, predictor, bit depth, overviews, atomicity) could
drift between the download path and the inference/output path.

**Decision.** All COG writing goes through a **single home, `raster.cog.to_cog`** — lossless
`DEFLATE` + `PREDICTOR`, `NBITS=16`, atomic write, with overviews. It is used by **both**
COG-on-download (spec 14 ingest) and inference outputs (spec 18). The legacy `rio_cogeo` write is
superseded.

**Considered options.** Per-caller COG writes (legacy). Superseded: duplicated settings that drift,
and multiple places to fix when the profile or atomicity strategy changes.

**Consequences.** One place to reason about and extend the COG contract — which is exactly why
remote-destination publishing was added *there* rather than in a caller (see ADR 0001). Every COG fsd
emits — ingested imagery and inference outputs alike — has the same profile.
