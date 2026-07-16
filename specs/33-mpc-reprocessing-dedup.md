# Spec 33 — MPC reprocessing de-duplication (TODO #34)

> **Status: ✅ SIGNED OFF (2026-07-16).** Interview → grill → cross-validate → spec, written per
> the handoff `/tmp/fsd-handoff-spec33-mpc-dedup.md`. All 5 design forks resolved with a cited
> external source each (see § Best-practice alignment); no open items blocked sign-off. **→ NEXT:
> a Sonnet@medium session implements against this text** (spec 24 D5) — this session did not
> implement.

## Motivation

The spec-32 runbook's first real MPC run (2026-07-16) returned **two STAC items for one
physical acquisition**:

- `S2B_MSIL2A_20220301T100029_R122_T33UWP_20220303T182540` (original processing)
- `S2B_MSIL2A_20220301T100029_R122_T33UWP_20240604T180322` (a 2024 reprocessing)

Same sensing time (`20220301T100029`), same MGRS tile (`T33UWP`), different item ids (the
trailing field differs) — so `sources.cdse._finalize_catalog_gdf`'s **id-uniqueness** assert
passes cleanly; nothing catches it. Both were downloaded (224 MB + 272 MB), both catalogued, and
`datacube.builder._stack_datacube` merged them via an incidental tie-break (`dst_crs`-native
first, then `image_index`) rather than a deliberate choice. **Not radiometrically wrong** — spec
32's `boa_add_offset` harmonizes each processing on its own baseline before the merge — but it
wastes bytes and leaves a silent, arbitrary pick between two versions of one scene. TODO #34's own
note: fix this **before any at-scale MPC download** (spec 31 Phase 2), where redundant reprocessed
granules would multiply real byte cost.

## Design forks, resolved

The five forks named in `PROGRESS.md`'s `→ NEXT`, in order:

### Fork 4 first (it decides Fork 1): does CDSE have the same duplication?

**Cross-validated (§ Best-practice alignment below).** Yes, CDSE can also surface multiple items
for what looks like one acquisition — but for a **different, structurally distinct** reason: a
single datatake split across two datastrips for one geographic area produces near-duplicate
**CDSE** products *by design* (ESA-confirmed on the CDSE forum), and CDSE's actual anti-duplication
strategy is **wholesale deletion of old-baseline products** from the catalogue, not a queryable
"pick latest" property. Critically, CDSE's near-duplicates from datastrip splits can carry
**different pixel coverage / border artefacts at the same nominal tile+time** — i.e. a naive
`(sensing_time, mgrs_tile)` dedup applied to CDSE could **silently discard legitimate, non-
duplicate coverage**. MPC's duplication (confirmed root cause: a one-off `sen2cor` timestamp
pipeline bug, since cleaned up on MPC's side, per Q1 sources) is a different failure mode: the
same granule, same footprint, twice.

### Fork 1 — where dedup lives: **MPC-only (`sources/mpc.py`), not shared `_finalize_catalog_gdf`**

Because Fork 4 shows the two providers' duplicate mechanisms are not the same problem, applying one
dedup rule to both would risk **actively breaking CDSE** (dropping a legitimate datastrip-split
scene as a false-positive "duplicate"). MPC's items are already single-MGRS-tile granules
(unlike CDSE's per-datatake `.SAFE` products), so the datastrip-split failure mode structurally
does not apply to MPC: two different real acquisitions cannot share both the exact same MGRS tile
*and* the exact same sensing instant (S2's ~5-day single-satellite revisit rules that out). Dedup
therefore lives entirely in `sources/mpc.py`, touches nothing in `cdse.py`, and CDSE keeps its
current behavior (correctly out of scope — CDSE's own datastrip-split handling, if ever needed, is
a separate future TODO, not this spec).

### Fork 2 — the key: no new catalog column; group in-memory on `(timestamp, mgrs_tile)`

The key does not need to be persisted. Dedup runs on the **discovered STAC item list**, before
`_items_to_gdf`/`_finalize_catalog_gdf` — i.e. before a catalog row is ever created — so there is
no need for a new `mgrs_tile` catalog column (avoiding a `COLUMNS`/back-compat change entirely).
`item.datetime` (tz-aware, sensing time) + `sources.mpc._mgrs_tile_from_item(item)` (existing
helper, currently dead code per the spec-32 review banner — **this gives it its first real
caller**) together form the in-memory grouping key.

### Fork 3 — which copy wins: **`s2:generation_time`, not the item id's trailing field**

**Cross-validated (§ below) — this reverses the handoff's suggested "parse the id's last field"
approach.** A live MPC item query confirms `properties["s2:generation_time"]` is a real,
populated, RFC-3339 STAC property (not a deprecated-and-gone field) that carries exactly the
same instant as the id's trailing field, but as a structured timestamp — no string-parsing.
Separately, ESA's own SentiWiki naming-convention reference explicitly declines to guarantee the
id's trailing "Product Discriminator" field is monotonically increasing ("can be earlier or
slightly later than the datatake sensing time") — so id-string comparison is not a safe "latest
wins" rule even though it happens to work on the one observed pair. **Winner = `max` by
`s2:generation_time`** among a duplicate group. Missing `s2:generation_time` on any item in a
group that actually needs a tie-break **raises** (deterministic, no silent guess — mirrors spec
32 D3's precedent for `s2:processing_baseline`); a singleton (no duplicate) group never needs the
property at all, so a normal non-duplicated item is unaffected even if it lacked the field.

### Fork 5 — applied at discovery time, both `query_catalog` and `download`

Dedup runs immediately after `_search_items` returns the raw item list, before `_items_to_gdf`, in
**both** `query_catalog` and `download` (the two MPC entry points that call `_search_items`) — so
a duplicate is never even selected for download, which is the actual byte-saving that matters
(the 224+272 MB was wasted at download time, not at catalog-merge time). Existing catalogs already
holding a duplicate pair (e.g. `tests/outputs/mpc_baseline/catalog.parquet`, 9 rows including the
known pair) are **not migrated** by this spec — this is a discovery-time fix, not a catalog
migration; a stale test artifact with a duplicate stays as-is unless someone re-runs the discovery
+ download from scratch. (No production catalog exists yet at this scale, so no migration tooling
is warranted — noted as a non-issue, not deferred work.)

## Scope

**In:**
- `sources/mpc.py`: a new `_dedupe_reprocessed_items(items) -> list` helper, called in both
  `query_catalog` and `download` right after `_search_items`.
- Give `_mgrs_tile_from_item` its first real caller (already exists, spec-32 dead code).
- pytest (synthetic, duck-typed fake items — same pattern as the existing `tests/test_mpc.py`).

**Out (named, deferred):**
- **Any CDSE change.** Fork 4/1 above conclude CDSE needs a structurally different fix, if any,
  and that is not this spec's problem (no TODO opened for it now — CDSE's datastrip-split
  near-duplicates are a different, undemonstrated-as-a-problem-for-fsd issue; open a TODO only if
  it's ever observed to bite).
- **Migrating existing catalogs** that already hold a duplicate pair (Fork 5) — discovery-time
  fix only.
- **A persisted `mgrs_tile` catalog column** — not needed (Fork 2); `_mgrs_tile_from_item` is used
  in-memory only, at discovery time, same as today's dead-code shape (just now called).
- **Reporting/telemetry on how many duplicates were dropped** beyond an optional progress-gated
  print line (parity with existing `download(progress=True)` style) — not a hard requirement.

## Design

### `sources/mpc.py` — new dedup step between `_search_items` and `_items_to_gdf`

```python
def _generation_time(item) -> str:
    """s2:generation_time (RFC-3339 str) — the reliable "which processing pass"
    property (cross-validated over the id's trailing field, which ESA's own
    naming-convention doc does not guarantee is monotonic). Raises if missing —
    only called when a duplicate group actually needs a tie-break."""
    gt = item.properties.get("s2:generation_time")
    if gt is None:
        raise ValueError(
            f"MPC item {item.id!r} is one of >1 items for the same "
            "acquisition (same sensing time + MGRS tile) but has no "
            "'s2:generation_time' property; cannot pick the latest processing "
            "(spec 33 Fork 3)."
        )
    return gt


def _dedupe_reprocessed_items(items: list) -> list:
    """Collapse multiple STAC items covering the SAME acquisition (identical
    sensing `item.datetime` + MGRS tile, spec 33) down to one — the item with
    the latest `s2:generation_time` wins. A no-op for items with distinct
    (timestamp, tile) keys (the overwhelmingly common case)."""
    groups: dict[tuple, list] = {}
    for it in items:
        key = (it.datetime, _mgrs_tile_from_item(it))
        groups.setdefault(key, []).append(it)
    return [
        group[0] if len(group) == 1 else max(group, key=_generation_time)
        for group in groups.values()
    ]
```

Wired into both entry points, immediately after `_search_items`:

```python
items = _search_items(roi_gdf, startdate, enddate, max_cloudcover=max_cloudcover)
items = _dedupe_reprocessed_items(items)   # spec 33
```

(`query_catalog` and `download` each already have their own `_search_items(...)` call site —
insert the one extra line at each, per the existing structure at `mpc.py:154`/`mpc.py:272`.)

### Where nothing changes

`_items_to_gdf`, `_finalize_catalog_gdf` (shared with CDSE — untouched, Fork 1), the catalog
schema (`catalog.COLUMNS` — untouched, Fork 2), `_select_item_files`/`_transfer_one`/download
orchestration (operate on the already-deduped item list, no awareness needed), `builder.py`'s
`_stack_datacube` tie-break logic (still exists as a general safety net for genuine same-timestamp
multi-tile-boundary coverage per spec 20 — unrelated to this fix, and now simply never exercised
by an MPC reprocessing duplicate since one never reaches the catalog).

## Tests

**pytest (synthetic, duck-typed fake items — matches `tests/test_mpc.py`'s existing `_FakeItem` /
`_fake_item(...)` pattern):**

- **No duplicates → no-op.** Two fake items with distinct `(datetime, mgrs_tile)` pairs:
  `_dedupe_reprocessed_items` returns both, unchanged, in original order-independent set.
- **Duplicate pair → latest generation_time wins.** Two fake items sharing identical `datetime`
  + `mgrs_tile` (via `properties["s2:mgrs_tile"]`) but different ids and different
  `s2:generation_time` values (one earlier, one later): only the later-generation-time item
  survives. Assert by `id`, not by list position.
- **Duplicate pair, three-way.** Three items in one group (simulating a scene reprocessed twice):
  the max-generation-time item wins regardless of input order.
- **Missing `s2:generation_time` on a duplicate group → raises** with a message naming the item
  id and the property. A *singleton* item lacking `s2:generation_time` does **not** raise (never
  reaches `_generation_time` — only called inside a `len(group) > 1` branch).
- **Falls back to `item.id` for the tile key** when `s2:mgrs_tile` is absent (reuses
  `_mgrs_tile_from_item`'s existing fallback — no new behavior to test here beyond confirming the
  dedup key composes with it correctly).
- **Integration: `query_catalog` and `download` both drop the duplicate.** Monkeypatch
  `_search_items` (as existing tests already do, `tests/test_mpc.py:138`) to return the exact
  `20220301T100029` two-item duplicate pair (real ids, fabricated `s2:generation_time`s matching
  the real `20220303`/`20240604` ordering) plus one distinct control item; assert the resulting
  catalog/gdf has exactly 2 rows (control + winner), never 3, and that `download`'s work list only
  contains the winner's assets (i.e. the loser's bytes are never even queued for transfer).
- **Regression:** full existing suite stays green; `tests/test_mpc.py`'s existing tests
  (`_offset_for_item`, `_items_to_gdf`, `_mgrs_tile_from_item`, `download`) are unaffected since
  none of their fixtures currently construct same-timestamp/same-tile duplicates.

No runbook needed — this is a pure discovery-time filter over STAC search results, fully
exercisable with synthetic/duck-typed items; no new network behavior to validate against real MPC
data beyond what spec 32's runbook already exercised (that runbook's own duplicate finding is the
existing real-world evidence this spec fixes).

## Deliverables (for the Sonnet@medium implement session)

- `sources/mpc.py`: `_generation_time` + `_dedupe_reprocessed_items` (new); one call-site edit each
  in `query_catalog` and `download`.
- Tests per the Tests section (new cases in `tests/test_mpc.py`, following its existing
  `_FakeItem`/`_fake_item` fixtures).
- Living docs: `CHANGES.md` (MPC discovery now dedupes reprocessed acquisitions), `TODO.md` (#34 →
  DONE; note CDSE's structurally different datastrip-split issue is explicitly NOT covered, no new
  TODO unless it's later observed to bite), `PROGRESS.md`, memory (`fsd-status` if it tracks
  per-spec state).
- No `pyproject.toml`/catalog-schema/builder changes (Forks 1/2 conclude none are needed).

## Best-practice alignment / sources (cross-validated 2026-07-16)

Per-source credit — exactly what each source contributed to a decision above (full detail +
additional context: `specs/research-s2-reprocessing-dedup.md`, filed as supporting research for
this spec):

- **Live MPC STAC item query** (`planetarycomputer.microsoft.com/api/stac/v1/search`, collection
  `sentinel-2-l2a`, checked 2026-07-16) — **contributed:** confirmed `properties["s2:generation_time"]`
  is a real, populated RFC-3339 timestamp on live items (Fork 3's chosen key), and that no
  top-level `created`/`updated`/`published` property exists as an alternative.
- **`stac-extensions/sentinel-2`** (github.com/stac-extensions/sentinel-2) — **contributed:** that
  `s2:generation_time`/`s2:processing_baseline` are formally deprecated in favor of
  `processing:datetime`/`processing:version` (`stac-extensions/processing`) — noted as a caveat
  (MPC's live items don't yet populate the replacement keys, so the legacy `s2:` name is what
  actually works today).
- **CDSE community forum — "Sentinel-2 L2A duplicate products (and border artefact)"**
  (forum.dataspace.copernicus.eu/t/.../789) — **contributed:** ESA-confirmed datastrip-split
  near-duplicates on CDSE are *by design*, not an error, and can carry different pixel
  coverage/border artefacts at nominally the same tile+time — the key fact behind Fork 1/4's
  "MPC-only, do not extend to CDSE" decision (a shared dedup rule risks discarding legitimate CDSE
  coverage).
- **CDSE — "Sentinel-2 Old Baselines – Products Deletion" + Phase 2 notice**
  (dataspace.copernicus.eu/news/2024-10-10-... and .../2025-8-11-...) — **contributed:** CDSE's
  actual anti-duplication mechanism is catalogue-level deletion of old-baseline products, not a
  queryable "pick latest" property — confirms CDSE's problem (if any) is structurally different
  from MPC's, reinforcing Fork 1.
- **SentiWiki — S2 Products page** (sentiwiki.copernicus.eu/web/s2-products, the current
  authoritative naming-convention reference, superseding the older PDF Sentinel-2 Products
  Specification Document) — **contributed:** ESA's own text on the id's trailing "Product
  Discriminator" field: "the time in this field can be earlier or slightly later than the datatake
  sensing time" — the specific fact that rules out id-string lexicographic comparison as a
  guaranteed "latest wins" rule (Fork 3).
- **`stactools-packages/sentinel2` issue #130** ("Change Item ID to better represent a specific
  space/time") — **contributed:** the STAC-ecosystem convention that reprocessed items of one
  acquisition should be distinguished via the STAC Version extension rather than an ad hoc key —
  the precedent that "latest-wins by a real timestamp property" (not id parsing) is the
  ecosystem-aligned approach (Fork 3), and reinforces that dedup keys need care (issue #5 in the
  same repo separately warns same-time/same-tile items from different receiving stations are
  legitimately distinct — a caution folded into Fork 1's "MPC structurally can't hit the CDSE
  false-positive case" argument, not a literal MPC risk since MPC has no receiving-station
  multiplicity in its archive).
- **`microsoft/PlanetaryComputer` discussion #275** — **contributed:** independent confirmation
  that MPC's known historical duplicate-item cases trace to a one-off `sen2cor` timestamp pipeline
  bug (since cleaned up on MPC's side), not a standing reprocessing-duplication policy — grounds
  the Motivation's framing that this is a real, if boundable, class of duplicate.

## Open items to confirm at sign-off

- **None blocking.** All five forks were resolved with a cited external check, not left open. The
  one soft judgement call: whether a *singleton* MPC item's total absence of `s2:generation_time`
  should also raise (defensive) vs. stay silent (current design — only raises inside an actual
  duplicate group). Recommendation: stay silent for singletons (a property fsd doesn't otherwise
  use for anything else shouldn't gate every single-item run); flag for the user to override at
  sign-off if they'd rather it be strict everywhere.
