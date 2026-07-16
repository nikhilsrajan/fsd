# Research: Sentinel-2 L2A STAC reprocessing / duplicate-item de-duplication

Supporting research for a spec on de-duplicating Sentinel-2 L2A STAC items when a source
serves multiple "processings" of the same physical acquisition. No dedicated research-notes
folder existed in `fsd/` yet; filed alongside `fsd/specs/` since it directly feeds a spec's
"Best-practice alignment / sources" section. Renumber/move if a spec is opened for this.

## Q1 — Does MPC expose a real STAC property for processing pass, other than the item id?

**Yes.** Queried a live item from `https://planetarycomputer.microsoft.com/api/stac/v1/search`
(collection `sentinel-2-l2a`, item `S2B_MSIL2A_20240608T095549_R122_T33UXP_20240608T131656`).
Its `properties` block contains:

```
"s2:generation_time": "2024-06-08T13:16:56.674469Z",
"s2:processing_baseline": "05.10",
```

`s2:generation_time` matches exactly the id's trailing field (`20240608T131656`) but as a proper
RFC-3339 timestamp property — no string-parsing needed. `s2:processing_baseline` gives the
baseline version directly (e.g. `"05.10"`, matching product-id field `N0510`). There is **no**
top-level `created`, `updated`, or `published` property on MPC items (checked the live response;
absent).

Per the STAC extension spec (**[stac-extensions/sentinel-2](https://github.com/stac-extensions/sentinel-2)**),
both fields are now deprecated in favor of generic STAC extensions, but MPC's live items still
populate the legacy `s2:` names, not the replacements:
- `s2:processing_baseline` → deprecated in favor of `processing:version`
- `s2:generation_time` → deprecated in favor of `processing:datetime`

(the replacement extension is **[stac-extensions/processing](https://github.com/stac-extensions/processing)**,
which defines `processing:datetime` as "Processing date and time of the corresponding data
formatted according to RFC 3339" and `processing:version` as "The version of the primary
processing software or processing chain that produced the data"). Neither `processing:*` key was
present on the live MPC item queried (2026-07-16) — only the legacy `s2:` ones. **Conclusion for
the spec: use `properties["s2:generation_time"]` (fallback to parsing the id only if absent) —
it is a real, documented STAC property, not string-parsing.**

Root cause of *why* MPC ever had true duplicates (not just re-triggered by baseline) is
independently confirmed in **[microsoft/PlanetaryComputer discussion #275](https://github.com/microsoft/PlanetaryComputer/discussions/275)**:
a bug in MPC's L1C→L2A conversion pipeline mishandled how `sen2cor` embeds a processing
timestamp in asset paths, producing genuine duplicate STAC items (not reprocessing — a pipeline
bug), which MPC then identified and deleted. That thread does not describe using `created`/
`updated`/`s2:processing_baseline` to resolve it — it was a one-off cleanup, not a standing
dedup policy.

## Q2 — Does CDSE exhibit the same multi-item-per-acquisition behavior, and does it dedupe differently?

**Yes, CDSE has the same class of issue, for a different reason, and does not appear to dedupe
systematically at the catalog level.** Per the **[CDSE community forum thread "Sentinel-2 L2A
duplicate products (and border artefact)"](https://forum.dataspace.copernicus.eu/t/sentinel-2-l2a-duplicate-products-and-border-artefact/789)**,
users reported multiple L2A products with identical sensing time/baseline but different
generation/creation dates and even different pixel values at borders. CDSE support's official
(ESA-sourced) explanation: the datatake was split across two datastrips for that specific
geographic area, so near-duplicate products are produced **by design**, not as an error. CDSE's
guidance was simply "use the most recent generated set of data" and that older duplicates "will
soon be removed from the catalogue" — i.e. a manual/administrative cleanup, not a documented
programmatic dedup key.

Separately, CDSE's **[Sentinel-2 Old Baselines – Products Deletion](https://dataspace.copernicus.eu/news/2024-10-10-sentinel-2-old-baselines-products-deletion)**
and **[Phase 2 deletion notice](https://dataspace.copernicus.eu/news/2025-8-11-sentinel-2-old-baselines-products-deletion-phase-2)**
confirm CDSE's actual dedup strategy for *baseline* reprocessing is wholesale **deletion of the
old-baseline products from the catalogue** once Collection-1 reprocessing completes — i.e. CDSE
avoids the multi-item problem at the catalog level by not keeping both versions live, rather than
by exposing a queryable "pick the latest" property. This differs from MPC, which (per Q1) keeps
all historical items live and relies on per-item generation-time properties.

**Conclusion: this is not an MPC-only quirk** — both providers can surface multiple items per
acquisition — but the mechanism differs (MPC: pipeline bug, now cleaned up, both old/new baseline
items can coexist long-term; CDSE: datastrip-split near-duplicates by design, plus a policy of
deleting old baselines rather than versioning them). A spec should not assume "if CDSE, no
dedup needed."

## Q3 — Does ESA's naming-convention doc confirm the last field = processing/generation timestamp, strictly increasing?

**Partially confirmed, with an important caveat — do not treat it as a strict monotonic
generation timestamp.** Per **SentiWiki's [S2 Products page](https://sentiwiki.copernicus.eu/web/s2-products)**
(Copernicus's current authoritative naming-convention reference, superseding the older PDF
*Sentinel-2 Products Specification Document*, ESA ref S2-PDGS-TAS-DI-PSD, at
`https://sentinels.copernicus.eu/documents/247904/0/Sentinel-2-product-specifications-document-V14-9.pdf`):

> The "Product Discriminator" field [the last field before `.SAFE`] is 15 characters in length,
> and is used to distinguish between different end user products from the same datatake...
> Depending on the instance, the time in this field can be earlier or slightly later than the
> datatake sensing time.

That explicit caveat ("can be earlier or slightly later") means ESA does **not** document it as a
strictly-increasing generation timestamp suitable for guaranteed lexicographic "pick latest"
comparison — it's a discriminator, not a formal version counter. In practice it usually *is* the
processing/publication time and *usually* sorts correctly, but ESA's own doc stops short of
guaranteeing monotonicity. **For the spec: prefer the STAC property `s2:generation_time` (Q1,
which is RFC-3339 and independently populated) over parsing/sorting the id's last field; if
falling back to the id field, document that ESA's own spec does not guarantee it's monotonic.**

## Q4 — Ecosystem precedent for handling reprocessed-duplicate STAC items?

**Yes — documented STAC-ecosystem convention exists.** Per **[stactools-packages/sentinel2 issue
#130](https://github.com/stactools-packages/sentinel2/issues/130)** ("Change Item ID to better
represent a specific space/time"), the STAC convention (as stated by the maintainers) is:

> Item IDs [should represent] a specific location and time(s) and do not include info that could
> change if the Item was reprocessed... Reprocessed versions of Items should instead implement the
> STAC Version extension.

i.e. the sanctioned pattern is: (1) give reprocessed items of the same acquisition the **same**
STAC id (drop processing-baseline/discriminator from the id), and (2) use the **STAC Version
extension** (`https://github.com/stac-extensions/version`, not separately fetched here but the
canonical "latest version of this item" mechanism in the STAC ecosystem) to mark which is
current/latest, rather than inventing an ad hoc dedup key. A related discussion,
**stactools-packages/sentinel2 issue #5** ("Duplicate scene ids for scenes with same geometry /
datetime but different receiving stations"), documents the adjacent but distinct case of
legitimately different scenes (different ground stations) that must **not** be collapsed — i.e.
the ecosystem precedent also warns that not every same-time/same-tile pair is a duplicate to
merge; some are genuinely different data.

**Conclusion for the spec:** fsd's dedup key should be (mgrs_tile, datatake/sensing start time,
relative_orbit) with "latest" chosen by `s2:generation_time`/`processing:datetime` — mirroring
the STAC Version-extension intent — not solely by id-string comparison, and the spec should
explicitly flag that datastrip-split cases (Q2) are a known false-positive risk for any such
dedup logic.
