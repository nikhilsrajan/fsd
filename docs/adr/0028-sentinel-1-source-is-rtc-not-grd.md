# The Sentinel-1 collection fsd ingests is `sentinel-1-rtc`, not `sentinel-1-grd`

**Status:** accepted (grilling session, 2026-09-04 — confirmed by the user; spec to follow)

**Context.** Adding Sentinel-1 forces a choice between two MPC collections. The obvious objection to
GRD — "it isn't map-projected" — is **false**, and was checked: MPC's `sentinel-1-grd` *items* carry
`proj:epsg: 4326` with a real `proj:transform`, and serve `vv`/`vh` as `profile=cloud-optimized`
GeoTIFFs. rasterio reads them. The decision therefore rests on radiometry, self-description and grid,
not on readability.

**Decision.** Ingest **`sentinel-1-rtc`** (float32 γ⁰, `nodata: -32768`, 10 m, UTM). Do **not** ingest
`sentinel-1-grd`.

**Considered options.** **GRD** — its pixels are detected amplitude DN, and reaching σ⁰/γ⁰ requires the
per-scene calibration vectors served as XML annotation assets (`schema-calibration-vv`), applied as
`value = DN²/A²` with a **range-dependent** gain plus a GRD constant offset (ESA). fsd's radiometry
model is a **scalar per-row `offset`**; a range-dependent gain vector is a different *kind* of
radiometry, not a new field. GRD's assets also carry **no `raster:bands` at all** — no `nodata`, no
`data_type`, no `scale` — so the artifact does not self-describe and the source module would have to
hardcode what the provider failed to state, which is exactly what [ADR 0011](0011-ingest-stores-raw-dn-declares-radiometry.md)
and [ADR 0012](0012-builder-generic-via-artifact-self-description.md) exist to prevent. Finally GRD is
EPSG:4326 on a **degree** grid (~0.000177°), which has no fixed metric resolution and will never
co-grid with S2's 10 m UTM — against the project's reference-image-resampling principle. RTC is UTM
10 m and aligns with S2 natively. On the science, γ⁰ with terrain and incidence-angle variation removed
is what makes a multi-date backscatter series comparable across passes and slopes, which is the whole
point for agriculture.

**Consequences.** **RTC requires a Planetary Computer account** — MPC's collection metadata states that
retrieving SAS tokens for RTC needs one. This puts credentials back on the `source="mpc"` path that was
deliberately made credential-free for the README quickstart on 2026-09-04, and the auth story becomes
**per-collection, not per-source**. Accepted knowingly: an account is cheaper than owning a SAR
calibration engine.

**⚠️ Bad provider metadata, recorded so nobody re-litigates this.** MPC's **GRD** asset descriptions
read "…with radiometric terrain correction applied." That contradicts ESA's definition of a Level-1 GRD
product and contradicts the existence of a separate `sentinel-1-rtc` collection. It is a provider
metadata error, not evidence that GRD is pre-corrected.
