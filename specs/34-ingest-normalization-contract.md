# Spec 34 — Ingest / normalization contract (`stage → normalize → put`, per source)

> **Status: ✅ IMPLEMENTED (2026-07-20, Sonnet@medium).** Signed off 2026-07-20 (Opus@high — user
> sign-off after a `grilling` pass) then implemented same-day against this spec. `pytest -q` green
> (279 passed/3 skipped), `ruff` clean. **→ NEXT: Opus@high review, then the user runs
> `runbooks/34-download-to-blob.md` + `runbooks/34-mini-mpc-cross-baseline.md`.**
> Promotes **TODO #38**
> (the item; this is spec **34**). Re-opens **download-to-blob for all sources** (suspended out of P1 —
> spec 31 §5/§5-ARCHIVE) now that the storage/compute seam is **proven** (spec 31, 2026-07-18).
> Generalizes spec 31's suspended §5 from an MPC-only byte-copy into a per-source
> `stage → normalize → put` contract. **Spec-first (spec 24):** this session writes the spec only;
> implementation is a later Sonnet@medium session against the signed-off spec.
>
> **Decisions locked (2026-07-20):** Scope (§Scope); **Decision 1 — radiometry/encoding + nodata**
> (§1); **Decision 2 — builder generalization / #35** (§2, option B + a user-facing "add a source"
> guide). **Stress-tested via a `grilling` pass (2026-07-20)** — seven resolutions folded in, each
> tagged `[G1]`–`[G7]` at the point it bites:
> - **[G1]** the datacube (science) still clips — the lossless win is on-disk only (§1f).
> - **[G2]** grid-topology generalization deferred to the ERA5 spec, `NotImplementedError`-guarded (§2b).
> - **[G3]** categorical-class masking only, behind a growable `mask_type` field (§2a/§2b).
> - **[G4]** no legacy: no back-compat shim; builder *requires* the new schema; data re-ingested (§5).
> - **[G5]** cloud-VM-first runbook + tmux/detach-safety + Azure-noob hand-holding (§4/§5).
> - **[G6]** cross-baseline acceptance runs on *local copies*; titiler-serves-blob deferred to P5 (§4).
> - **[G7]** code onto the VM via git-clone (Batch dress rehearsal); rsync for debug (§4/§5).

## Motivation

fsd's real end goal is download → datacube → inference on **Azure Batch at scale without cloud
lock-in** (ROADMAP; spec 10). P1 proved the **storage/compute seam** (build+flatten with every byte
on the `rise` blob, config-not-code) but deliberately **suspended download-to-blob** out of scope,
because "getting bytes onto blob" is a **normalization** concern, not a storage-seam concern:

- **CDSE** = *format* normalization (jp2 → COG).
- **MPC** = *radiometry* normalization (S2 processing-baseline BOA offset) — assets already COG.
- **ERA5** (future) = *container* normalization (netCDF → COG).

Designing that inside the storage-seam spec would have baked in the very source-specific split the
roadmap pivot ("the downloader normalizes, the datacube builder does not") exists to remove. This
spec is that pivot's payoff: **the ingest job makes each source uniform and self-describing**, so the
datacube builder sees one input contract regardless of source.

The unit of work is a **job**: `stage → normalize → put` (blob). It is NOT a dumb copy — it does
whatever per-source processing is required to normalize, then writes a self-describing artifact
(COG + STAC/catalog metadata). This is the same self-contained unit-of-work the P2 Batch runner
(TODO #41) will later dispatch.

**Where the job runs (execution model) — [G5].** The job is a **portable CLI unit-of-work** and
storage is config-not-code, so it runs unchanged wherever it is launched. `fs.transfer(src, dst)`
**streams through the launching machine**, so *where you run it decides whose bandwidth carries the
bytes*: on a laptop over a hotspot, the full GB volume crosses the hotspot; on a **cloud VM** on/near
`rise`, the bytes go CDSE/MPC → cloud-node → blob and the laptop carries only the SSH session. This
spec therefore targets a **cloud-VM-first** runbook (the "download happens on the cloud, no hotspot
load" property you want) — achieved **without** the Batch runner, which is only needed for *automated
fleet-scale* dispatch of many such jobs (P2, TODO #41). Running one job on a cloud VM by hand is the
P2 dress rehearsal.

## Scope

**In (LOCKED — "Contract + MPC + CDSE"):**
- The `stage → normalize → put` contract itself (the shape below), general enough that a future
  non-S2 source (ERA5/CHIRPS/S1) fits **without a source-specific `if` in the hot path**.
- Implement download-to-blob for the **two sources we have**: **MPC** (radiometry-declare +
  byte-copy) and **CDSE** (format jp2→COG + declare). Lifts the local-only guards
  (`mpc.py`, `cdse.py`) suspended by spec 31.
- The **encoding contract**: on-disk dtype/nodata + how radiometry is carried (Decision 1).
- Builder generalization to consume the contract instead of hardcoding S2 (Decision 2 — #35).
- Closes **#30/#10** (CDSE `boa_add_offset` retrofit) as a special case of the metadata mechanism;
  closes **#37** (CDSE-download-to-blob).

**Designed-for but NOT implemented this spec:**
- **ERA5 / CHIRPS / S1** — the contract must accommodate them (netCDF→COG container normalization,
  no-mask sources), but no code. First real non-S2 source is a later spec (ties to #11 Source ABC).

**Out (deferred, named):**
- **Azure Batch/AML runner** (P2, TODO #41) — this spec's jobs run under the **local** runner.
- **Inference/serving on blob** (P4/P5, TODO #39) — unchanged.
- **Production stream-vs-copy** (TODO #31), **MPC long-build re-signing** (#32), **MPC resume
  orchestration** (#33) — untouched.

## 1. Decision 1 — radiometry / encoding / nodata (LOCKED 2026-07-20)

**Ingest stores raw DN and *declares* radiometry as metadata; it does NOT bake normalized pixels.**

Driving requirement (user, 2026-07-20): a **single XYZ URL** over a multi-year mosaic spanning the
2022-01-25 processing-baseline cutover must render **consistently** (pre-04.00 images otherwise look
darker than ≥04.00 in RGB). The correctness fork behind it (the `clip(DN−1000,0,65535)` question)
resolves as follows, cross-validated below.

### 1a. On-disk encoding

- **Reflectance bands: raw DN, `uint16`, `nodata=0`.** No radiometric shift is baked into the pixels.
  Rationale: (i) baking `clip(DN−1000,0,65535)` toward the old/physical scale **silently eats real
  reflectance in (0,1000]** and is **permanent**; (ii) baking **kills MPC's byte-copy** (already-COG
  assets would have to decode+re-encode); (iii) baking forces one scale on two consumers that want
  different scales (science wants physical reflectance, the viewer wants the bright ≥04.00 look).
- **Radiometry carried as metadata, in BOTH places (fork resolved 2026-07-20 by cross-validation):**
  - **COG internal GDAL scale/offset tags — required for the viewer.** titiler/rio-tiler
    `unscale=true` applies **only the raster's internal GDAL tags**, **not** STAC `raster:bands`
    (titiler maintainer, disc. #803: raster:bands scale/offset are *"not currently forwarded to the
    ImageData object"*). So the single-URL cross-baseline render (§1b) needs the per-item offset in
    the **COG tag**. `offset = −1000` for baseline ≥ 04.00 else 0 (the per-item, load-bearing value);
    `scale = 1/10000` (constant — so `unscale` yields physical reflectance; the viewer `rescale` is
    then in reflectance units, e.g. `0,0.3`).
  - **STAC `raster:bands[].offset` / `.scale`** — the self-describing interchange the **builder** and
    other tools read (§2a), and what **closes #10/#30** (CDSE reads the same declared offset instead
    of the hardcoded 0). Same values as the tag.
  - **Consequence for byte-copy:** CDSE (re-encoded jp2→COG anyway) gets the GDAL tag **for free**.
    **MPC is a byte-copy PLUS a cheap GDAL metadata stamp** (scale/offset + nodata-if-missing) — a
    header-tag edit that **never decodes pixels** (no radiometric loss, fast), *not* a pure copy.
    Whether the in-place stamp keeps a strictly-valid COG is a **runbook observation** (like spec 31's
    `mv`-atomicity check), with a GDAL-COG-driver re-encode as the documented fallback.
  - **No double-application:** plain `rasterio.open`/`read` (the builder) **never** auto-applies GDAL
    scale/offset — they are inert metadata on a normal read — so the builder reads raw DN and applies
    the declared offset itself; only `unscale`-aware readers (titiler) apply the tag. The two coexist
    safely, and the values are identical, so there is no source of drift.
  - **Retires the bespoke `boa_add_offset` catalog column** (spec 32) for this standard mechanism.

### 1b. Who applies the offset (one lossless COG, two consumers)

- **Science** — the datacube builder applies the per-band offset → physical reflectance, as it does
  today (`_apply_boa_offsets`), but reads it from the declared metadata, not the bespoke column.
- **Viewing** — titiler-pgstac `unscale=true` applies **each item's own** offset at read, *before*
  mosaicking, so a single XYZ URL + one uniform `rescale`/`colormap` renders mixed baselines
  consistently. Verified mechanism: rio-tiler applies a dataset's internal scale/offset per-asset in
  the mosaic path; the per-baseline difference is absorbed from per-item metadata, which a uniform
  request parameter cannot do.
- **Negative/low reflectance is real signal, not missing** (ClearSKY; ESA offset intent) — keeping
  raw DN preserves it **on disk**. The *derived* datacube still clips (see §1f — this is the honest
  scope of the win).

### 1c. nodata (user flag, 2026-07-20 — "MPC tifs sometimes lack nodata")

- **Ingest guarantees every stored artifact declares its nodata.** Some MPC COGs omit the nodata tag;
  ingest **sets `nodata=0`** when the source omits it. This is part of *normalize* (metadata
  normalization), not optional.
- **Why it is load-bearing on both paths:** the builder's masking/merge/flatten all key off
  `nodata=0` (`load_image(nodata=…)`, `rasterio.merge(nodata=0)`, flatten's all-nodata drop); and the
  **viewer** needs a declared nodata so `DN=0` renders **transparent** (and is excluded *before* the
  offset scaling) instead of as a black, offset-shifted pixel — otherwise the slippy map gets black
  borders/seams.
- **nodata is itself a declared value** (S2 L2A convention = 0; ESA reserves 0 as NO_DATA). Do **not**
  assume `DN=0` is nodata for *arbitrary* future sources (ClearSKY warning) — it is declared per
  source/artifact, defaulting to 0 for S2. This folds into Decision 2's artifact self-description.

### 1d. Rejected

- **Bake toward old + clamp** (today's `apply_boa_offset` = `clip(DN−1000,0,65535)` **applied to the
  stored bytes**): lossy on disk *and* wrong for the viewing goal (darkens the ≥04.00 images the user
  finds correct). **This spec drops the clamp from the store/on-disk path** — the COG keeps raw DN. (A
  clip still occurs *inside the derived datacube*, consciously — §1f.)
- **Bake toward new** (`DN+1000` on old data): loss-free and gives the desired bright look, but still
  re-encodes pre-2022 data, needs nodata masking, and forces one scale on both consumers. Metadata
  declaration dominates it on every axis (byte-copy, recomputability, per-consumer scale).

### 1e. Evidence that the metadata is load-bearing (MPC as the negative example)

MPC's live `sentinel-2-l2a` collection exposes **no `raster:bands` scale/offset**, **no `renders`
extension**, and its COGs carry the offset only in the buried product XML (issue #134). Consequently
**no single MPC XYZ URL can cross-baseline-harmonize** — `unscale=true` has nothing to apply and a
uniform `color_formula` cannot shift pre- vs post-2022 items differently. This is exactly the gap
fsd's ingest fills by *writing* the offset metadata MPC omits. **Acceptance proof runs on fsd's own
mini-MPC** (spec 30 titiler-pgstac), not on MPC.

### 1f. The datacube (science) still clips — the lossless win is on-disk only [G1]

**Be precise about what this spec does and does not fix.** The offset **must** be applied *before*
the median mosaic (a calendar window straddling 2022-01-25, or any multi-year cube, would otherwise
median unharmonized DN across the baseline cutover → wrong values). So the builder harmonizes at read
and the **datacube array is `uint16` + `clip(DN+offset, 0, 65535)`** — meaning post-baseline DN in
`(0,1000]` still clips to 0 **in the cube the model trains/infers on**. That is today's behavior, and
we keep it:

- **What we fixed:** the *on-disk COG* is now **raw DN, lossless** (was: nothing on disk; the offset
  lived only in a catalog column and the clamp was the only representation). The clip is now a
  **conscious, documented, recoverable** choice, not a silent bug — the true DN survives on disk, so a
  future `float32`/`int16` or zarr datacube (TODO #13) can recover the `(0,1000]` values without
  re-downloading.
- **Why it's acceptable:** agricultural reflectance rarely lives in `(0,1000]` (that's dark
  water / deep shadow), and the user explicitly accepts the loss (2026-07-20). `int16`/`float32`
  were weighed and rejected for *this* spec: `int16` breaks the `nodata=0` invariant the whole
  builder/flatten/merge chain assumes; `float32` is a datacube-dtype contract change (flatten, model
  input, 2× size) that belongs with TODO #13, not here.
- **No overclaim:** this spec does **not** make the science cube lossless. It makes the **archive**
  lossless and the **viewer** correct (§1b), and it removes the *silent* nature of the cube clip.

## 2. Decision 2 — builder generalization (#35) — LOCKED 2026-07-20 (option B)

`build_datacube` hardcodes S2 assumptions that block non-S2 sources and force every download to carry
SCL (`datacube/builder.py`): the op chain `apply_cloud_mask_scl → drop_bands(["SCL"]) → median_mosaic`
(SCL mandatory — `bands=['B04']` raises), `reference_band="B08"`, and `nodata=config.NODATA` (0).

**Chosen altitude: B — formal artifact self-description.** The builder becomes a generic engine that
reads a per-artifact declaration; there is **no product registry and no `if source==…`**. Both S2
sources go through the generic path (so the contract has a real consumer — avoids the spec-32/33
"hollow contract nothing exercises" trap); ERA5/CHIRPS/S1 become **additive**. This is the same
principle as §1: **the artifact self-describes; the builder reads it.** (Not A — leaves the contract
half-hardcoded. Not C — the full pluggable op-graph + `sources/base.py: Source` ABC is TODO #11, a
separate effort this spec deliberately does not swallow.)

### 2a. The source→builder contract — what the builder needs, and where it reads it

All of it is **carried by the artifact** (catalog + STAC), so the builder needs no ambient product
config:

| What | Where it lives | Default (S2 L2A) | Consumed by |
|---|---|---|---|
| per-band **role** — `reflectance` / `mask` / `reference` | catalog `band` rows + STAC asset `roles` | B08=`reference`, SCL=`mask`, rest=`reflectance` | op-sequence assembly |
| **mask spec** — `{band, mask_type, classes}` or **None** `[G3]` | catalog/collection metadata | `mask_type="categorical_classes"`, SCL, classes `[0,1,3,7,8,9,10]` | mask step (skipped if None) |
| **reference band** (resolution reference), or "native — no resample" | declared role | B08 (10 m) | reference-profile / resample |
| per-band **offset / scale** | STAC `raster:bands` (§1) | offset −1000 (≥04.00) / 0; scale 1/10000 | radiometry apply |
| **nodata** | COG tag + catalog (§1c) | 0 | load / merge / flatten |
| **mosaic method** | build param / declaration | median | mosaic step |

### 2b. Op-sequence assembly (replaces the hardcoded chain)

The builder assembles its sequence *from the declaration* instead of hardcoding it:
- **radiometry** — apply each band's declared offset/scale (§1); no-op when offset 0 / absent.
- **mask** — if a mask band is declared → `apply_cloud_mask` with its `classes`, then drop the mask
  band (unless kept, §2c); if **None** → skip both. **This closes #35** (`bands=['B04']` no longer
  raises; non-optical sources need no SCL).
  - **`[G3]` categorical-class masking only, behind a growable `mask_type`.** Implemented:
    `mask_type="categorical_classes"` (mask where the mask band ∈ `classes` — covers SCL). The field
    is the seam for `bitmask` (Landsat/HLS QA) / `threshold` (continuous cloud-probability) masks
    *later*; a declaration with any **other** `mask_type` raises a clear `NotImplementedError` (not a
    wrong mask). Documented as a limitation in `adding-a-source.md`.
- **mosaic** — `median` (default) over the calendar windows — unchanged engine assumption.
- **reference / resample** — resample to the declared reference band's grid (default B08).
  - **`[G2]` grid-topology generalization is DEFERRED to the ERA5 spec.** This spec keeps the
    **S2-tiled single-CRS-collapse + reference-merge** machinery untouched, and implements only the
    parts of the declaration testable on real S2 data now (mask opt-out, reference/nodata/radiometry
    from the declaration). A **"single native grid → skip collapse"** value is a *declared-but-not-yet-
    executed* field: a source that declares it triggers a clear **`NotImplementedError`** ("native
    single-grid sources land with the ERA5/CHIRPS spec"), **not** a silent mis-collapse. The reason:
    the non-tiled path needs a real non-S2 source to build+test against (spec-32/33 "don't ship an
    untested path" lesson). So **`source-agnostic` is true for what ships** — mask/reference/nodata/
    radiometry are declaration-driven and exercised on real S2 data — and grid-topology is honestly
    marked designed-for-but-deferred.

### 2c. Mask kept-as-option (the sub-fork)

Default = **current behavior: mask-then-drop** the mask band. Add an option to **keep** the mask band
in the cube (role retained, not dropped) for workflows that want QA/SCL available downstream.
"No mask declared" skips both mask and drop.

### 2d. Extensibility + documentation (user requirement, 2026-07-20)

The contract only earns its name if a **library user can add a new source themselves**. Two graded
deliverables enforce this:

1. **`fsd/docs/adding-a-source.md` — "How to add a new source."** Must detail:
   - the two halves of the source contract: **ingest** (`stage → normalize → put` — discovery via
     `query_catalog`, then materialize/normalize writing the right metadata) and **builder** (the
     §2a table verbatim: exactly what the builder reads and *where it looks*);
   - a field-by-field reference — each declaration field → where to put it → default → S2 example;
   - a **worked example**: add a hypothetical single-band, no-mask, single-native-grid source
     (CHIRPS-like) end to end, showing it flows through `build_datacube` untouched;
   - a pointer to the future `Source` ABC formalization (#11), which this doc seeds.
2. **Docstrings sufficient to derive that doc from the code** — every declaration field documented at
   its definition; the op-assembly logic documented as "reads X from Y." This is a **review/DoD
   criterion**, not a nicety: the reviewer checks that a reader of `builder.py` + the source modules
   can populate a new source without reading this spec.

## 3. Per-source normalization map

The shape that covers all sources with **no source-specific `if` in the hot path**: ingest dispatches
**once, at setup**, on a per-source **container transform**, then writes a **uniform, self-describing
artifact** (COG + STAC/catalog metadata per §1/§2a). Only the container transform differs per source;
everything downstream (builder, viewer) reads the artifact, never the source.

| Source | `stage` | `normalize` (container) | `normalize` (radiometry) | mask | reference / grid | `put` |
|---|---|---|---|---|---|---|
| **CDSE** (S2 L2A) | fetch jp2 from S3 | **jp2 → COG** (`to_cog`, exists) | **`processing:version`** → offset (STAC Processing Ext.; see §3a **A1**); stamp GDAL tag + `raster:bands` (**closes #30/#10**) | SCL, classes | B08 / MGRS tiled, multi-CRS | `fs.transfer`/write to blob |
| **MPC** (S2 L2A) | signed HTTPS href | **byte-copy** (already COG) **+ GDAL tag stamp** (offset+nodata) | **`s2:processing_baseline`** → offset (S2 STAC Ext.; see §3a **A1**) | SCL, classes | B08 / MGRS tiled, multi-CRS | `fs.transfer` to blob |
| **ERA5** (future, designed-for) | netCDF/GRIB | **netCDF → COG** (container; forecloses `/vsicurl` stream) | units/scale → `raster:bands` | **None** | native single global lat/lon grid — **skip CRS-collapse** | write to blob |

- **CDSE and MPC are both S2** → they exercise the S2 path (mask present, tiled multi-CRS). **ERA5**
  is the *designed-for* proof the contract is source-agnostic (no mask, single grid); its
  container-transform (netCDF→COG) and native-grid builder path are **built with the ERA5 spec** `[G2]`
  — the row is here so the contract shape is validated against it, not so code ships.
- The **only** per-source branch is the container transform, chosen at setup from the source's
  declaration — **not** re-decided per tile, per band, or in the builder.

### 3a. Amendment A1 — the baseline property differs per provider (2026-07-20, post-runbook)

**Status: AMENDMENT — corrects a factual error in the signed-off spec.** Found by
`runbooks/34-download-to-blob.md --source cdse`, which hard-failed on every CDSE item with
`ValueError: ... has no 's2:processing_baseline' property`.

**What the spec got wrong.** §3's original CDSE row said "STAC baseline → offset", and
`sources/_s2_radiometry.py`'s docstring asserted that *"CDSE's STAC items carry the same
`s2:processing_baseline` property, per the S2 STAC extension both providers implement."*
**That is false for the endpoint fsd actually queries.** `config.CDSE_STAC_URL` is
`https://stac.dataspace.copernicus.eu/v1/`, and CDSE's v1 catalogue (Feb 2025) performed a
*"removal of the satellite-specific STAC extensions in favor of a more generic metadata model."*
There is **no `s2:` namespace in a CDSE v1 item at all** — the observed property set is
`processing:*`, `product:*`, `grid:code`, `view:*`, `eopf:*`, `sat:*`, `eo:*`. The claim was true
of CDSE's *older* catalogue and was carried forward unverified; it is exactly the class of
external-fact error the "cross-validate every spec against authoritative sources" practice exists
to catch, and it was not caught because the claim was plausible (both providers *do* implement
STAC extensions — just different ones).

**The correction.** The baseline is provider-specific in *name only*; the value format
(`"MM.mm"`) and the semantics are identical, so `baseline_tuple` is unchanged.

| Provider | Property | Extension | Observed (T33UWP, Jun 2022) |
|---|---|---|---|
| **MPC** | `s2:processing_baseline` | S2 STAC extension | `"05.09"` etc. (leg **passed**) |
| **CDSE v1** | `processing:version` | STAC **Processing** extension | `"05.10"` ≡ `N0510` in the product id, on all 8 items |

`offset_for_item` therefore resolves the baseline from an **ordered tuple of known
baseline-bearing properties**, first hit wins:

```python
_BASELINE_PROPS = (
    "s2:processing_baseline",  # MPC / legacy CDSE — S2 STAC extension
    "processing:version",      # CDSE STAC v1 — STAC Processing extension
)
```

**What does NOT change (deliberately):**

- **Still keyed on baseline, never on acquisition date.** Reprocessing stamps a ≥ 04.00 baseline on
  a pre-2022 acquisition — the observed items are June-2022 acquisitions **reprocessed in June 2024**
  to baseline 05.10, so a date-keyed rule would get them wrong. This is why §1's original wording
  chose baseline over date, and A1 does not weaken it.
- **Still a hard `ValueError` when no known property is present — no silent `0`.** This is the whole
  point of the spec: TODO #30/#10 is the bug where a hardcoded `boa_add_offset=0` put cubes ~1000 DN
  high (the reason the `demo_e2e` archive is radiometrically unusable for science). A loud failure on
  unrecognized metadata is strictly better than a quiet wrong number, and A1 preserves it.
- **No fallback to parsing `N0510` from the product id**, even though the id always carries it.
  Two *documented standard properties* beat a filename convention, and a silent id-regex fallback
  would mask the next provider metadata-model migration — which is precisely how this defect
  reached a runbook. If a third provider needs it, it is a new entry in `_BASELINE_PROPS`, not a
  regex.

**Blast radius (verified 2026-07-20):** `s2:processing_baseline` was CDSE's *only* missing property
dependency. `sources/cdse.py` otherwise reads only `eo:cloud_cover` (present in v1), and MGRS/EPSG
are parsed from the product id (`_safe_root_from_item`, `catalog/stac.py::_parse_mgrs`), not from
`s2:mgrs_tile`. MPC's extra `s2:` reads (`s2:mgrs_tile`, `s2:generation_time`) are untouched — MPC
still serves the `s2:` extension, and its runbook leg passed.

**Tests (add to §4):** `offset_for_item` resolves from `s2:processing_baseline` alone; from
`processing:version` alone; prefers `s2:processing_baseline` when both are present and disagree
(pins the precedence order); and still raises when neither is present. Fixtures are duck-typed
items, so no network — matching §4's existing synthetic style.

## 4. Tests (pytest — synthetic/local; the credentialed/visual parts are runbooks)

Traced against the **real builder call chain** (`datacube/builder.py`), not "the function exists" — the
spec-32/33 lesson. The generic op-assembly (§2b) is the load-bearing new logic, so it is tested from
**both** sides of the #35 fork:

- **§2b op-assembly — S2 path (mask present):** a synthetic catalog declaring an SCL mask band builds
  the same op sequence as today (`apply_cloud_mask → drop → median`) and produces an identical cube to
  the pre-refactor builder on the same input (a **golden regression** — the refactor is behavior-
  preserving for S2).
- **§2b op-assembly — no-mask path (#35 closed) `[G2]`:** a synthetic catalog with **no mask band
  declared** and a single band builds `bands=['B04']`-style **without raising** (today it raises
  `ValueError: SCL band not present`), skipping both mask and drop — on an ordinary **S2-grid**
  catalog (the mask opt-out is what #35 is; grid-topology is deferred, so there is **no** "native-grid
  skips collapse" test here — we don't test unbuilt code).
- **Native-grid guard is loud, not silent `[G2]`:** a declaration requesting a single native grid (or
  a non-`categorical_classes` `mask_type` `[G3]`) raises a clear **`NotImplementedError`**, not a
  wrong/misassembled cube.
- **Mask kept-as-option (§2c):** the mask band is retained in the output cube when declared "keep".
- **Radiometry (§1) — on-disk raw DN + declared offset:**
  - `apply_boa_offset`'s lossy `clip(DN−1000,0,65535)` is **removed from the ingest/store path**;
    a test asserts a stored reflectance DN in `(0,1000]` **survives to disk** (the regression the old
    on-disk-only representation silently lost).
  - ingest writes `offset`/`scale` to **both** the COG GDAL tag and STAC `raster:bands`, with equal
    values (mock the writer; assert the tag and the item metadata agree).
  - a plain `rasterio.open(...).read()` of a stamped COG returns **raw DN** (no auto-unscale) — pins
    "no double-application" so the builder + tag can't drift.
- **Datacube still clips, consciously `[G1]`:** a build over a catalog spanning the baseline cutover
  applies the offset before the median and produces a `uint16` cube where post-baseline `(0,1000]`
  clips to 0 — a test **pins this as the intended behavior** (not a bug), with a comment pointing at
  §1f and the true DN preserved on disk. Guards against a future "fix" silently changing the dtype.
- **nodata (§1c):** ingesting a source COG **without** a nodata tag yields a stored artifact declaring
  `nodata=0`; a source COG that declares nodata keeps its declared value.
- **Catalog/STAC declaration round-trip:** roles (`reflectance`/`mask`/`reference`), mask classes,
  nodata, offset/scale survive write→read of the catalog + STAC export (the builder reads exactly what
  ingest wrote).
- **`build_datacube` reads the declaration, not `config`:** mutate the declared `reference_band` /
  mask classes / nodata in the synthetic catalog and assert the build honors the **declared** value,
  not the `config.*` default (proves the hardcoding is gone).
- **regression `[G4]`:** the full existing suite stays green **after the synthetic test fixtures are
  rewritten to the new declaration schema** (there is **no** back-compat shim — see §5/`[G4]` — so a
  fixture that still carries the retired `boa_add_offset` column / no roles is *expected* to fail and
  must be migrated, not shimmed); `ruff` clean.

**Runbooks (user runs on a cloud VM; paste back `_result.json`):**
- **Download-to-blob per source (cloud-VM-first) `[G5]/[G7]`** — CDSE (jp2→COG→blob) and MPC
  (copy+stamp→blob) each land a self-describing artifact on the `rise` blob; assert COGs present +
  non-zero, GDAL tag + `raster:bands` offset present, nodata declared, catalog paths `abfss://…`. The
  runbook is written **cloud-VM-first** with Azure-noob hand-holding (§5): provision/reach the VM →
  `az login` → **git-clone** the branch + venv + `pip install -e ".[dev,azure]"` → `export
  FSSPEC_ABFSS_ANON=false` → run the download CLI **inside `tmux`** (detach-safe against a dropped
  SSH) → monitor progress → verify on blob. `rsync` noted as the pre-push debug shortcut.
- **Single-URL cross-baseline render (§1e acceptance) — on LOCAL copies `[G6]`** — pull a small
  mixed-baseline COG set (pre-2022 + post-2022, already offset-stamped at ingest) to local/VM disk,
  load into the **mini-MPC** stack (spec 30 local pgSTAC + titiler-pgstac), register one search,
  request tiles with `unscale=true` + a reflectance `rescale`, and **eyeball one XYZ URL with no
  baseline seam** (visual-validation principle; QGIS/STACNotator BYO). Runs on **local copies** so it
  validates the offset→unscale *mechanism* (storage-agnostic); **titiler-reads-blob** (GDAL Azure auth
  inside the tiler container) is a **separate P5 serving item**, deliberately out of this proof. This
  is the harmonization MPC itself cannot give (§1e).

## 5. Deliverables (for the Sonnet@medium implement session)

- **`fsd/sources/cdse.py`** — lift the `cog=True`-needs-local guard (`cdse.py:645`); jp2→COG path
  writes the GDAL scale/offset + nodata tags and populates `raster:bands` (**closes #30/#10, #37**).
- **`fsd/sources/mpc.py`** — lift the local-only guard (`mpc.py:294`); after `fs.transfer`, stamp the
  GDAL scale/offset + nodata tags (cheap, no pixel decode); populate `raster:bands`. Remove the
  build-time-only reliance on the bespoke `boa_add_offset` column.
- **`fsd/datacube/builder.py`** — replace the hardcoded op chain with **declaration-driven
  assembly** (§2b): mask opt-out, reference from declaration, nodata from declaration, offset from
  `raster:bands`. Remove `apply_boa_offset`'s lossy clamp from the store path (keep a read-time apply).
- **`fsd/catalog/` + `fsd/catalog/stac.py` `[G4]`** — carry band **roles**, mask spec (`{band,
  mask_type, classes}`), nodata, offset/scale. **Retire the `boa_add_offset` column with NO
  back-compat shim:** the builder *requires* the new declaration schema; a legacy catalog is **not**
  read (it is disposable — re-ingested, §"Data" below). STAC export writes `raster:bands` + asset
  `roles`. Update the synthetic test fixtures to the new schema.
- **`fsd/docs/adding-a-source.md`** (§2d) — the "how to add a new source" guide + the docstring DoD.
- **`fsd/runbooks/34-*.md` (cloud-VM-first, Azure-noob) `[G5]/[G7]`** — the download-to-blob runbook
  (§4) written for someone new to Azure: reach/provision the VM, `az login`, **git-clone** the branch
  (the Batch dress rehearsal) + venv + `pip install -e ".[dev,azure]"`, `export FSSPEC_ABFSS_ANON=
  false`, run the CLI **under `tmux`** with a cheat-sheet (`tmux new -s dl` / `Ctrl-b d` detach /
  `tmux attach -t dl` reattach after a dropped SSH) so an accidental disconnect can't kill a
  multi-hour download, progress monitoring, verify-on-blob, and `rsync` as the pre-push debug
  shortcut. Plus the mini-MPC cross-baseline runbook (§4, local copies). Committed scripts under
  `runbooks/scripts/`, `_result.json` written unconditionally, `--dst` passed as an arg (no `rise`
  values in the repo) — the spec-31 runbook pattern.
- **Data (re-ingest, not migrate) `[G4]`** — no legacy to preserve (user, 2026-07-20): the 74 GB
  Austria `demo_e2e` archive and `mpc_baseline` are **disposable**; real-data validation re-downloads
  a small slice under the new contract (incl. a **mixed-baseline** slice for the §1e acceptance).
- **Tests** per §4. **Living docs:** `TODO.md`, `CHANGES.md`, `PROGRESS.md`, memory `[[fsd-status]]`
  (§Open).

## Best-practice alignment / sources — per-source credit

- **ESA:** `ρ = (DN + BOA_ADD_OFFSET)/QUANTIFICATION_VALUE`; `BOA_ADD_OFFSET = −1000` for baseline
  ≥ 04.00 (2022-01-25), `QUANTIFICATION_VALUE = 10000`; the offset exists to preserve near-zero/
  negative reflectance over dark surfaces. → §1a formula + why clamping is lossy.
  — https://sentinel.esa.int/en/web/sentinel/technical-guides/sentinel-2-msi/level-2a-algorithms-products
- **ClearSKY:** "do not treat 'negative' as 'missing'"; "do not assume DN=0 is always NoData — SAFE
  products declare special values." → §1b (negative is signal) + §1c (nodata is declared, not assumed).
  — https://clearsky.vision/knowledge/sentinel2-scaling-harmonization
- **Google Earth Engine `S2_SR_HARMONIZED`:** the "standard" baked harmonization subtracts 1000 from
  new data toward the old range, and does **not** clamp negatives. → §1d (why we don't clamp; why bake
  is the lossy/common-but-wrong-for-us choice). — https://developers.google.com/earth-engine/datasets/catalog/COPERNICUS_S2_SR_HARMONIZED
- **rio-tiler / TiTiler:** `unscale=true` applies a dataset's **internal scale/offset** per-asset;
  mosaic reads each item independently → per-item offset absorbed before mosaicking. → §1b viewing path.
  — https://developmentseed.org/titiler/endpoints/stac/ ; https://cogeotiff.github.io/rio-tiler/latest/
- **TiTiler.PgSTAC mosaic:** single `/searches/{id}/tiles/...` endpoint takes `unscale`, `rescale`,
  `colormap` → the single-URL cross-baseline render. → §1b, §1e acceptance.
  — https://stac-utils.github.io/titiler-pgstac/1.2.3/endpoints/searches_endpoints/
- **TiTiler maintainer (V. Sarago, disc. #803):** STAC `raster:bands` scale/offset are **"not
  currently forwarded to the ImageData object"** — `unscale` applies **only the raster's internal GDAL
  tags**. odc-stac #55 corroborates: readers do **not** auto-apply `raster:bands` (manual workaround).
  → §1a **resolved fork**: the offset must be stamped into the **COG GDAL tag** for the viewer (not
  `raster:bands` alone) → MPC = byte-copy **+ metadata stamp**, not a pure copy.
  — https://github.com/developmentseed/titiler/discussions/803 ; https://github.com/opendatacube/odc-stac/issues/55
- **MPC issue #134 + live collection metadata:** MPC exposes no per-item `raster:bands` offset / no
  `renders` → no MPC single-URL harmonization possible; proves the metadata is load-bearing. → §1e.
  — https://github.com/microsoft/PlanetaryComputer/issues/134 ;
    https://planetarycomputer.microsoft.com/api/stac/v1/collections/sentinel-2-l2a
- **STAC Processing extension** (added by A1, 2026-07-20): defines `processing:version` as *"The
  version of the primary processing software or processing chain that produced the data. For example,
  this could be **the processing baseline for the Sentinel missions**."* → §3a **A1**: this is the
  authoritative basis for reading CDSE's baseline from `processing:version` — the field's documented
  purpose for this exact mission family, not an inference from a coincidence.
  — https://github.com/stac-extensions/processing
- **CDSE v1 catalogue release note** (added by A1, 2026-07-20): the new catalogue features
  *"removal of the satellite-specific STAC extensions in favor of a more generic metadata model that
  fits the new generation of Copernicus satellites and contributing missions"*, on STAC 1.1. → §3a
  **A1**: explains *why* `s2:processing_baseline` vanished from `stac.dataspace.copernicus.eu/v1/`
  and why the original spec's "both providers implement the same extension" premise was false.
  — https://dataspace.copernicus.eu/news/2025-2-13-release-new-cdse-stac-catalogue
- **CDSE STAC API docs** (checked 2026-07-20, *negative* result): documents the v1 endpoint and its
  collections but **does not document per-item property schemas**, so the property set could not be
  confirmed from docs alone. → §3a **A1** methodology: the live probe against `CDSE_STAC_URL` was
  necessary, not optional — a docs-only cross-validation would have missed this.
  — https://documentation.dataspace.copernicus.eu/APIs/STAC.html
- **ESA/CDSE baseline versioning** (added by A1): the `NMMmm` product-id field ≡ the `MM.mm`
  baseline string (`N0510` ≡ `05.10`), and baselines are deployed over time (05.11 in 2024, 05.12 in
  2025) against *older* acquisitions via reprocessing. → §3a **A1**: corroborates that
  `processing:version` and the product id agree, and that baseline ≠ acquisition date.
  — https://documentation.dataspace.copernicus.eu/Data/SentinelMissions/Sentinel2.html ;
    https://dataspace.copernicus.eu/news/2024-7-19-deployment-sentinel-2-processing-baseline-version-0511-23-july
- **fsd's own source** (read 2026-07-20): `apply_boa_offset` = `clip(DN−1000,0,65535)` (the lossy
  clamp we drop); `build_datacube` hardcodes SCL mask/drop + `reference_band=B08` + `nodata=0`;
  `mpc.py`/`cdse.py` local-only guards. → §1d, §2. *(spec-32 lesson: this class of fact no external
  source surfaces.)*

## Open items (to resolve at/after sign-off)

- ✅ **COG GDAL-tags vs STAC `raster:bands`** — **RESOLVED** (§1a): `unscale` honors only the GDAL tag,
  so stamp both; MPC = byte-copy + metadata stamp.
- **In-place GDAL tag stamp vs COG re-encode (MPC)** — whether stamping scale/offset/nodata in place
  keeps a strictly-valid COG, or forces a GDAL-COG-driver rewrite. **A runbook observation, not a
  design fork** (fallback documented in §1a); measured at the download-to-blob runbook.
- **Living-doc updates on sign-off** — `TODO.md` (#38 → this spec; #35 closed, #37/#30/#10 folded),
  `CHANGES.md` (the `apply_boa_offset` clamp dropped from the store path; `boa_add_offset` column →
  `raster:bands` + GDAL tag; builder now declaration-driven), `PROGRESS.md`, memory `[[fsd-status]]`.
