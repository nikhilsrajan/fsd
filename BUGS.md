# BUGS — manual-review register

Living record of bugs that need **human evaluation** (esp. anything touching real
credentials, live services, or geospatial correctness the user wants to eyeball).
Add a section per bug. Status: `OPEN` · `INVESTIGATING` · `RESOLVED` · `WONTFIX`.

---

## BUG-001 — CDSE S3 intermittent auth errors (server-side, not fsd)

**Status:** ROOT CAUSE IDENTIFIED (CDSE server-side infra) → **largely designed out.**
The worst offender was the recursive **S3 `.SAFE` listing** during file-selection;
`fsd` now discovers band S3 hrefs from the **CDSE STAC API** (`pystac-client`,
anonymous) instead, so it **never lists over S3**. The only remaining S3-auth op is
the per-file byte `transfer`, which retains a **fail-fast retry** (`_download_one`)
for the residual intermittency. Full analysis:
`debug-attempts/s3_paths_fetch/cdse_s3_intermittent_auth_report.md` (+ repro script
`s3_paths_fetch_test.py`).
**Found:** 2026-07-01, live-testing `fsd.sources.cdse.download`.
**Resolved (listing):** 2026-07-01 via the STAC pivot (see CHANGES.md).

### Root cause (from the user's multi-run debug)
Listing CDSE S3 objects intermittently returns `SignatureDoesNotMatch` **or**
`InvalidAccessKeyId`, yet the **same keys + same code fully succeed on other runs**
(the run table shows success interleaved with both error codes). The decisive
evidence: the repro uses the **legacy boto3** `Bucket("eodata").objects.filter(
Prefix=...)` — the known-good reference — and it **also fails intermittently**. So
the earlier "s3fs recursive-signing" hypothesis is **wrong**; my shallow-ls-ok /
recursive-glob-fail observation was good-window vs bad-window luck, not a
delimiter/recursion effect.

Three distinct outcomes (success / `SignatureDoesNotMatch` / `InvalidAccessKeyId`)
from identical inputs can only come from **inconsistent credential state across
CDSE's load-balanced cluster nodes** (node fully replicated → success; node missing
key → `InvalidAccessKeyId`; node with stale/partial state → `SignatureDoesNotMatch`).
Service moves in good/bad **windows** (bad windows stack retries → ~120 s/URL).
Corroborated by a CDSE community-forum report of the same pattern (~June 2026).

### Also cleared up along the way
- The initial `InvalidAccessKeyId` was **not** simply stale keys (regenerating did
  not stop the alternation) — it's the same intermittent server-side issue.
- The catalog's `L2A_N0500` s3url is **correct** (the `L2A`-without-baseline variant
  404s). URL was never the problem.

### Ruled out (do NOT re-investigate — settled in the report)
S3 key validity/expiry · wrong/special-char secret · clock skew · rate-limit math
(429 ≠ these errors) · boto3≥1.36 checksum change · missing session token · boto3
resource-vs-client / pagination · s3fs-vs-boto3 signing · the URL/region/addressing.

### Fix direction — client resilience (accepted approach from the report)
Make the S3 listing/transfer resilient to transient failures rather than trying to
eliminate them:
- Treat `{SignatureDoesNotMatch, InvalidAccessKeyId, SlowDown, AccessDenied}` as
  **retryable** (permanent on real AWS, transient on CDSE).
- **Fail fast per URL** (~3 tries, 2s/4s backoff + jitter), then skip.
- **Checkpoint** completed work so reruns resume and skip done items.
- **Circuit breaker**: after ~N consecutive failures, stop (bad window) and rerun
  later.
- **Parallelize** good windows; pin the OTC endpoint
  (`https://eodata.ams.dataspace.copernicus.eu/`) + reuse one client to cut routing
  variance.

### Done (2026-07-01)
- ✅ **Listing eliminated** — discovery + band hrefs now come from the STAC API; no
   S3 `.SAFE` listing (removes most S3-auth exposure).
- ✅ **Retry lives in `sources/cdse`** (`_download_one` + `_RETRYABLE_S3`), not the
   provider-agnostic storage seam — so a future AWS/Azure backend won't retry genuine
   auth errors. Custom retry (botocore treats these codes as non-retryable).
- ✅ **Fail-fast per file** — 3 tries, `2s·2^n` + jitter, on the 4 CDSE-transient codes.
- ✅ **OTC-pinned endpoint** — `config.CDSE_S3_ENDPOINT_URL = eodata.ams…`.
   Live-confirmed 2026-07-01: OTC endpoint did `ls`+`GET` fine while the GSLB alias
   (`eodata.dataspace…`) returned `SignatureDoesNotMatch`/`Forbidden` in the same
   minute — and OTC itself 403'd 5× then cleared (the windowing). A 1-file B08
   download succeeded through `_download_one`.
- ✅ **Catalog is the checkpoint** — chunked, `files`-unioning append; idempotent
   (skips files already on disk).

### Measured at scale (2026-07-02) — see `benchmarks/download_report_2018_ethiopia.md`
First 1-year batch (579 tiles, 4 bands): during a **sustained bad window**, file-level
success was only **~22.5%** (623 ok / 2152 fail of 2776), **80/579 tiles complete** in
one pass. Making `Forbidden` retryable moved an earlier **0%** pass to ~22.5%, but
in-run retries can't beat a bad window — confirms **fail-fast + resume-later** over
grinding. Idempotent per-chunk catalog made the killed run fully resumable.

### Still open (revisit if downloads prove flaky at scale)
- ✅ **Circuit breaker + resume-loop DONE (2026-07-02).** `download(max_consecutive_failures=N)`
  trips (`circuit_tripped`) on a bad window; `download_resume(...)` re-runs idempotently
  until a clean pass (trip → `cooldown_s` back-off, partial → immediate retry), with an
  `on_pass` hook to persist per-pass stats. Needs a real at-scale re-run in a good window
  to confirm convergence.
- **Concurrency**: currently `config.MAX_CONCURRENT_S3 = 4` (CDSE's documented quota);
  the report ran `≈6` fine. Keep configurable; tune with real runs.
- **Retryable set**: bad windows also surface a bare `Forbidden`/`403` (seen
  2026-07-01), which `_RETRYABLE_S3` does NOT currently include (to avoid masking
  genuine permission errors). Reconsider adding it during at-scale tuning (TODO #9).
- **Per-tile restructure**: `download` still builds one flat work list then chunks it.
  Fine for now; per-tile atomic units would make partial-window resume cleaner.

### Actions outside fsd (user)
- Report the run log to CDSE (their infra; only they can fix server-side).

---

## BUG-002 — datacube builder dropped tiles when several cover one shape (spec 20)

**Status:** RESOLVED (2026-07-07, spec 20). **Geospatial correctness — eyeball the QGIS
re-run.**

**Symptom.** In the spec-19 end-to-end demo, 9 of 300 inference grids came out ~nodata
(worst `165b09c`: 0.6 % valid) while neighbours were 70–90 %. They clustered on an MGRS
tile-**row** boundary (lat ~11.75).

**Root cause.** `datacube/builder.py::_stack_datacube` built `ts_band_index =
dict(zip((timestamp, band), image_index))` — a **dict**, so when a shape overlapped several
tiles of the **same acquisition** (adjacent MGRS tiles from one orbit pass share an identical
timestamp), only the **last** survived and the rest of the shape became nodata. Grid
`165b09c` had 4 tiles at 100 % of its 72 timestamps → 1 kept → 0.6 % valid despite ~80 %
raw coverage; data sat only in rows 525–548 of 549.

**Why it hid.** Training/flatten uses small field polygons that *mostly* sit inside a single
tile → collisions were rare and the loss small (the demo cold-rebuild recovered only ~6 % more
training pixels: 217,914 → 230,567), so it never stood out. The 5 km inference grids (spec 19)
are the first shapes big enough to straddle boundaries badly (up to 4 tiles/acquisition). Almost
certainly a **faithfully-ported legacy bug** (`fetch_satdata` has the same dict shape).

**Fix.** Group ALL images per `(timestamp, band)` and **nodata-fill merge** them on the
reference grid (everything is already resampled there); overlap tie-break = `dst_crs`-native
tiles first, then `image_index`. Confined to `_stack_datacube`; output shape/axes unchanged.
**Verified:** grid `165b09c` 0.6 % → **82.8 %** valid after the fix. Tests:
`test_stack_merges_multiple_tiles_same_timestamp`, `test_stack_overlap_tiebreak_prefers_native_crs`.

**To re-eyeball (user).** The spec-19 demo `crop_map.png` / `merged.tif` after the re-run
(lat-11.75 gaps should be gone) and the multi-CRS `datacube.md` cube in QGIS.

---

## BUG-003 — inference-output STAC Item geometry over-claimed coverage (raster bbox, not cell shape)

**Status:** RESOLVED (2026-07-14, spec 28). **Serving correctness — regenerate + re-eyeball the
demo STAC over a real basemap once served.**

**Symptom.** Every inference-output STAC Item's `geometry` was the output COG's axis-aligned
bounding box (`catalog/stac.py::cog_outputs_to_items`, `geom = shapely.geometry.box(*bounds4326)`),
not the true S2-cell footprint. Confirmed on the real Austria run (cell `477303c`):
`geometry.geojson` (truth) is a slanted quadrilateral `(14.766,48.492) (14.789,48.534)
(14.847,48.526) (14.825,48.484)`; the STAC Item shipped the north-aligned box
`(14.766,48.484)–(14.847,48.534)` instead.

**Why it matters.** An fsd datacube/output is a north-up raster rectangle carrying a nodata halo
around the real (slanted) ROI shape — the box **over-claims coverage**. This was cosmetic until
the STACNotator serving study (`PROGRESS.md` LATEST 2026-07-14): a per-tile `ST_Intersects`
(either STACNotator's self-hosted tiler or pgSTAC search, the Tier-2 target) matches items whose
box overlaps a query tile even when the *actual* footprint (past the halo) does not — wasted COG
reads and wrong/loose pgSTAC search hits.

**Found.** Discovered while digesting STACNotator's tiler (`../stacnotator/tiler/src/tiles.py:87`)
during the serving-pivot design study, not from a failing test — the geometry was always
structurally valid, just wrong.

**Fix.** `cog_outputs_to_items(cog_filepaths, geometries={cog: geometry.geojson_path}, …)` — the
Item geometry/bbox now come from the **build manifest** (`input.csv.shapefilepath`, the same
`geometry.geojson` `run_inference` already writes per cell), not the raster. Deterministic and
manifest-driven by design: no sibling-file discovery, no fallback — a manifest entry missing its
footprint raises rather than silently boxing. `geometries=None` (geometry-less callers: bare COG
lists, unit tests, the pre-built folder/list inference modes with no manifest) keeps the old
raster-bbox behavior, unchanged. See `CHANGES.md` and `specs/28-stac-output-geometry-fix.md`.

**To re-eyeball (user).** Run `runbooks/28-stac-geometry-regen.md` (regenerates the existing
300-item demo STAC from its manifest, no re-inference) — expect `non_rectangular_geoms == 300`.
Visually: once served (spec 29 Tier 1 or a Tier-2 pgSTAC search), item footprints should hug the
slanted cell shapes, not boxes.
