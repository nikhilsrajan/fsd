# The datacube builder is a generic engine driven by per-artifact self-description

**Status:** accepted (spec 34, Decision 2 / #35 — LOCKED 2026-07-20, option B)

**Context.** `build_datacube` hard-coded S2 assumptions that block non-S2 sources and force every
download to carry SCL: the op chain `apply_cloud_mask_scl → drop_bands(["SCL"]) → median_mosaic`
(SCL mandatory — `bands=['B04']` raised), `reference_band="B08"`, and `nodata=0`.

**Decision.** Make the builder a **generic engine that reads a per-artifact declaration** — band
**roles** (`reflectance`/`mask`/`reference`), the **mask spec** (`{band, mask_type, classes}` or
`None`), the **reference band**, and **nodata** — all carried by the artifact (catalog rows + STAC
asset metadata). **No product registry and no `if source==…`.** Both S2 sources go through the
generic path (so the contract has a real consumer and isn't hollow); ERA5/CHIRPS/S1 become
**additive** declarations. Same principle as ADR 0011: the artifact self-describes, the builder reads
it.

**Considered options.** **A — leave it half-hard-coded** (rejected: the contract stays partly baked
into the builder). **C — a full pluggable op-graph + `sources/base.py: Source` ABC** (deferred to
TODO #11 — a separate effort this spec deliberately does not swallow).

**Consequences.** New sources are added by declaring their bands/mask/reference, not by editing the
builder. The builder needs no ambient product config. Pairs with ADR 0011 (radiometry is one more
declared field) and ADR 0013 (what happens when the declaration is missing).
