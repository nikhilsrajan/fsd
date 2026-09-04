# A collection declares what must not be mosaicked together; the builder enforces it

**Status:** accepted (grilling session, 2026-09-04 — confirmed by the user; spec to follow)

**Context.** `median_mosaic` blends every acquisition falling in a calendar window
([ADR 0010](0010-calendar-interval-mosaic-default.md)). For optical collections that is correct and
intended. For Sentinel-1 it is **physically wrong**: ascending and descending passes view a field
from opposite look directions, and RTC removes terrain and incidence effects on the γ⁰ conversion
but not azimuthal anisotropy or look direction. Medianing them together produces a number that
corresponds to no observation. Combining across geometries in the literature requires an
incidence-angle normalization *followed by* an azimuthal anisotropy correction — two corrections fsd
does not have and should not invent.

**Decision.** `CollectionDeclaration` gains **`mosaic_partition: tuple[str, ...]`** — the catalog
property keys that must hold a **single value** within one build — and **`partition_policy`**
(`"raise" | "auto"`). `build_datacube` enforces it generically. `sentinel-1-rtc` declares
`mosaic_partition = ("sat:orbit_state",)` with `partition_policy = "raise"`; the error **enumerates
the available `(orbit_state, relative_orbit)` pairs with acquisition counts and ROI coverage**, so
the failure is also the discovery mechanism. `sentinel-2-l2a`, `hls2-s30` and `hls2-l30` declare
`()` — no enforcement, no behaviour change for optical.

**Why optical is exempt is a product fact, not an oversight.** HLS applies BRDF normalization and
bandpass adjustment specifically so L30 and S30 stack; S2 L2A's viewing-geometry variation is small
and the product is built to be composited. Radar has no equivalent harmonization step. Because the
tolerance is a property of the *product*, it belongs on the collection declaration rather than in
the builder.

**Considered options.** **Warn on mixing** — rejected: silent-by-default for something physically
wrong. **Auto-select the best-covering orbit and print it** — rejected: an auto-selection that gets
printed is an auto-selection that gets ignored, and it makes a science choice on the user's behalf.
**Enforce `sat:relative_orbit` too** — rejected as an *enforced* constraint, see below.

**Consequences.** `sat:relative_orbit` is **offered as a filter and reported, but not enforced.**
The evidence splits: strict per-timestep comparison wants it fixed, but ESA's geometry makes that
expensive — a 250 km IW swath, 175 orbits per 12-day cycle, so fixing it caps the ROI to one swath
and roughly halves temporal density. WorldCereal, the global operational crop system, deliberately
does not fix it (it cannot, globally) and compensates with geometry-tolerant percentile features.
fsd therefore **enforces what is nearly always wrong to mix, and reports what is context-dependent
and sometimes impossible to avoid.** Enforcement also requires the catalog to carry the source
item's STAC properties, which is what makes the generic `properties` column load-bearing rather
than a convenience.
