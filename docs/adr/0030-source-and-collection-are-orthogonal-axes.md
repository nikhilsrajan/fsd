# Source (provider) and Collection (product) are two orthogonal axes, not one string

**Status:** accepted (grilling session, 2026-09-04 — confirmed by the user; spec to follow)

**Context.** fsd's verbs took a single `source="cdse"|"mpc"` string, and `sources/mpc.py` hardcoded
`collections=[config.SATELLITE_S2L2A]`. The catalog column named `satellite` has always held a STAC
**collection id** (`"sentinel-2-l2a"`) — `catalog/stac.py` even round-trips `item.collection_id` into
it — so the code already knew the distinction; only the name lied. The single-string model cannot
express the differences that actually decide behaviour: S1 GRD and S1 RTC are the *same satellite*
but only one is usable; HLS is *two satellites* in one collection; MPC hosts S2, S1, HLS and MODIS.

**Decision.** Two orthogonal parameters. **Source** = the provider (auth, transport, whether the
native bytes need converting). **Collection** = the product, named by its STAC collection id
(bands, mask, radiometry, grid — everything a `CollectionDeclaration` describes). The verbs take
`source=` and `collection=` separately; `collection` defaults to `"sentinel-2-l2a"`. The catalog
column `satellite` is renamed `collection`. `SourceDeclaration` is renamed
`CollectionDeclaration`, because it describes a product, not a provider.

**Considered options.** **A fused string** (`source="mpc:sentinel-1-rtc"`) — cheap, but it welds the
provider to the product, and the axes genuinely cross: S2 L2A is on both CDSE and MPC, HLS is on both
MPC and LP DAAC. **Keep one `source` string** — the status quo, and the reason one collection was
hardcoded into the MPC module. **"Satellite agnostic"** as the framing — rejected outright: a verb
agnostic over *satellites* still could not tell RTC from GRD.

**Consequences.** Per-collection knowledge moves to a registry, `fsd/collections/`, keyed by STAC
collection id; `restamp_cli`'s embryonic `DECLARATIONS = {"s2_l2a": ...}` becomes a view over it.
Asset-key resolution stays inside each source module (MPC keys assets `"B04"`, CDSE `"B04_10m"`) but
becomes collection-aware. Because the catalog column is renamed, **every existing catalog is
invalidated** — accepted deliberately: the user chose to re-download and rebuild rather than ship a
migration shim, which also retires the stale radiometry in the Austria archive.
