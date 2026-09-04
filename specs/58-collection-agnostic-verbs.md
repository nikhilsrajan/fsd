---
status: current
summary: fsd's verbs are Sentinel-2-shaped — `scl_mask_classes` sits on three of them, `source` conflates provider with product, and one collection id is hardcoded inside the MPC module. Split Source (provider) from Collection (product), move every collection-level fact onto a registered `CollectionDeclaration` resolved driver-side, and prove the abstraction neutral on S2 before adding `sentinel-1-rtc` (P2) and `hls2-s30`/`hls2-l30` (P3). Advances #11, #21; reserves #98; defers #99.
---

# Spec 58 — collection-agnostic verbs

**Status:** **DRAFT — awaiting sign-off.** · **Opened:** 2026-09-04
**Advances:** [#11](https://github.com/nikhilsrajan/fsd/issues/11) (additional sources + the `Source`
contract), [#21](https://github.com/nikhilsrajan/fsd/issues/21) (source-capability model).
**Reserves:** [#98](https://github.com/nikhilsrajan/fsd/issues/98) (computed masks — shape only).
**Defers:** [#99](https://github.com/nikhilsrajan/fsd/issues/99) (cross-collection fusion),
[#100](https://github.com/nikhilsrajan/fsd/issues/100) (measure reference-image resampling),
[#1](https://github.com/nikhilsrajan/fsd/issues/1) (configurable output resolution).
**Origin:** the user, 2026-09-04: *"the goal is to make download and create training data verbs
satellite agnostic — specifically data from mpc — which includes hls and modis"*, followed by a
full grilling session that produced ADRs [0028](../docs/adr/0028-sentinel-1-source-is-rtc-not-grd.md),
[0029](../docs/adr/0029-collections-declare-what-must-not-be-mosaicked.md),
[0030](../docs/adr/0030-source-and-collection-are-orthogonal-axes.md),
[0031](../docs/adr/0031-collection-strings-resolve-on-the-driver.md).
**Related:** [spec 34](34-ingest-normalization-contract.md) (the declaration contract this extends),
[spec 35](35-declaration-persistence.md) (the stamp), [ADR 0010](../docs/adr/0010-calendar-interval-mosaic-default.md)
(the calendar mosaic the partition rule constrains).

---

## 1. The problem

fsd claims a generic pipeline and mostly has one — `build_datacube` genuinely contains no
`if source == ...`. But the **verbs** are Sentinel-2-shaped, and the shape is load-bearing:

- **`scl_mask_classes` is on three public verbs** (`create_training_data`, `run_inference`,
  `verify_adapter`) while `SourceDeclaration.mask_spec` already holds the same fact generically. The
  verb parameter **overrides** the declaration in `build_datacube`, so there are two sources of truth
  and the S2-shaped one wins — and the catalog's stamp then records something the build did not do.
- **`source` conflates provider with product.** `sources/mpc.py:144` hardcodes
  `collections=[config.SATELLITE_S2L2A]`, and four sites validate `source` against the literal pair
  `("cdse", "mpc")`. The catalog column named `satellite` has always held a STAC **collection id**;
  `catalog/stac.py:481` round-trips `item.collection_id` into it. The code knows; the name lies.
- **`max_cloudcover` is the same wart, unflagged** — it sits on `download` and
  `create_training_data`, and Sentinel-1 has no cloud cover at all.
- **The cube path digest has no collection in it.** `window_folder_segment` →
  `params_key(bands, mosaic_scheme, scl_mask_classes)` (`workflows/create_datacube.py:84`). S1 and S2
  avoid collision only because their band *names* differ. **HLS bands are named `B04`/`B08`/`B8A`,
  identical to S2's** — so an HLS cube and an S2 cube over the same cell, window and `mosaic_days`
  resolve to the **same path**, and the second silently reuses the first.
- **A requested band that does not exist is silently dropped.** `_select_item_files`
  (`sources/mpc.py:234`) does `if asset is None: continue`. Ask for `B08` against HLS L30, where it
  genuinely does not exist, and you get a cube quietly missing a band.
- **`reference_band` has no guard.** If it is not among the requested `bands`, `ref_indices` is empty
  (`datacube/builder.py:282`) and the failure happens deep inside the merge.

None of this is visible while only one collection exists. All of it lands the moment a second does.

## 2. Scope

**In:** the public verbs (`download`, `create_training_data`, `run_inference`, `verify_adapter`), the
declaration contract, the collections registry, the catalog schema, canonical band naming, and two
new collections — `sentinel-1-rtc` and `hls2-s30`/`hls2-l30`.

**Out, each with a home:**

- **MODIS** (`modis-09A1-061` and friends) — needs `native_grid=True`, which is designed-for and
  unimplemented (spec 34 `[G2]`), plus composite-item temporal semantics. Deliberately later; the
  user's call, 2026-09-04.
- **Cross-collection fusion** — one cube = one collection (D16). [#99](https://github.com/nikhilsrajan/fsd/issues/99).
- **Computed masks (OmniCloudMask)** — the *shape* is reserved in D7; the implementation is
  [#98](https://github.com/nikhilsrajan/fsd/issues/98).
- **Sentinel-1 GRD** — rejected, ADR 0028.
- **Bitfield (multi-bit enum) mask extraction** — named, not built (D7).
- **Configurable output resolution** — [#1](https://github.com/nikhilsrajan/fsd/issues/1), untouched.

## 3. Decisions

### D1 — Source is the provider, Collection is the product

Two orthogonal verb parameters. **Source** decides authentication, transport and whether native bytes
need converting (`"cdse"`, `"mpc"`). **Collection** decides bands, mask, radiometry and grid, named by
its STAC collection id (`"sentinel-2-l2a"`, `"sentinel-1-rtc"`, `"hls2-s30"`, `"hls2-l30"`);
`collection` defaults to `"sentinel-2-l2a"`. Full rationale and rejected alternatives: **ADR 0030**.

"Satellite agnostic" is explicitly *not* the axis: S1 GRD and S1 RTC are the same satellite, HLS is
two satellites in one collection, and a verb agnostic over satellites still could not tell RTC from
GRD.

`download`'s default `source` changes `"cdse"` → `"mpc"`, matching `create_training_data` and the
MPC-first README. The current default requires credentials while the documented happy path does not.

### D2 — A collections registry, and `CollectionDeclaration`

Per-collection facts move to `fsd/collections/`, keyed by STAC collection id
(`s2_l2a.py`, `s1_rtc.py`, `hls.py`). `restamp_cli`'s embryonic
`DECLARATIONS = {"s2_l2a": ...}` (`catalog/restamp_cli.py:25`) becomes a view over it.
`SourceDeclaration` is renamed **`CollectionDeclaration`** — its own docstring already says
"collection-level declaration" three times. The persisted JSON key (`fsd:declaration`) and the field
names are unchanged by the rename, so **the rename alone invalidates nothing**.

**Asset-key resolution stays in the source modules** and becomes collection-aware: MPC keys assets
`"B04"`, CDSE keys them `"B04_10m"` — same collection, different lookup, so it is a provider fact.

### D3 — Masking is declared, never passed

**Delete `scl_mask_classes` from `create_training_data`, `run_inference` and `verify_adapter`.** The
`CollectionDeclaration`'s `mask_spec` becomes the only source of truth. A user wanting different mask
classes registers a **named collection variant** (D13), which is stampable, addressable and reusable
where an inline list was none of those.

This closes the "lying stamp": the catalog is stamped with the collection's declaration at ingest
(`sources/mpc.py:330`), and nothing overrides it at build time any more.

### D4 — The cube path digest keys on the collection

`params_key` becomes a function of **collection id + a digest of the resolved
`CollectionDeclaration` + the partition selection (D9)**, alongside the existing bands / window /
`mosaic_days` / `mosaic_scheme`. This fixes the HLS↔S2 path collision in §1 and makes *any*
collection-level change — mask classes, nodata, reference band — correctly invalidate cached cubes,
which a single `scl_mask_classes` field could never do.

**Consequence, accepted:** every existing cube path, `_flatten_stamp.json` and known-empty manifest
is invalidated.

### D5 — Radiometry generalizes in four small moves, not one big one

The pipeline is **already dtype-generic**: `_stack_datacube` takes `fill_dtype` from the first loaded
image (`builder.py:652`), so a float32 S1 cube comes out float32 with no change. The only
integer-only chokepoint is `apply_offset`'s `clip(DN + offset, 0, 65535)` (`raster/images.py:256`),
which **early-returns at `offset == 0`** — the case for both S1 RTC and HLS. So:

1. **Add `scale` as a catalog column beside `offset` — declared, never applied.** Radiometry is
   metadata and pixels stay raw DN (ADR 0011). HLS DN stays `int16` with `scale=0.0001` declared,
   exactly as S2 DN stays `uint16` with `scale=1/10000` declared today. This does not touch the build
   path; it makes the STAC export and viewer rendering correct.
2. **`apply_offset` clips to the loaded array's dtype range**, not a literal `0..65535`. Removes the
   landmine before any collection declares a non-zero offset on signed or float data.
3. **Replace `_is_reflectance` with `CollectionDeclaration.radiometry_bands`** (`None` = all bands
   carry the declared offset/scale). The regex `^B\d` (`raster/images.py:234`) is a *collection* fact
   answered globally, used at **four** sites including both source modules at stamp time. It is
   harmless for S1 (offset 0 either way) and accidentally correct for HLS (`B04` → True); it is
   wrong for anything not named `B<digit>`.
4. **Do NOT add a declared `dtype`.** The artifact self-describes its dtype; declaring it twice
   invites disagreement, which is what ADR 0012 exists to prevent.

### D6 — `max_cloudcover` is kept, capability-gated

It is not S2-specific but *optical*-specific — HLS items carry `eo:cloud_cover` — and it is a
**discovery** filter, so it does **not** enter the cube digest. `CollectionDeclaration` gains a
capability flag; passing `max_cloudcover` to a collection with no cloud-cover property raises a
`PreflightError` naming the collection.

Rejected: a generic STAC `query=` passthrough. CDSE and MPC do not expose identical property
vocabularies, so a passthrough would make verb behaviour depend on the *provider* — reintroducing
exactly the coupling D1 removes.

### D7 — `mask_type="bitmask"` means "any listed bit set"

`MaskSpec` gains **`bits: tuple[int, ...]`** — a separate field from `classes`, never an overload:
`classes=(1,2,3)` means *pixel values*, `bits=(1,2,3)` means *bit positions*, and conflating them
yields a silently wrong mask.

`bitmask` masks a pixel when **any** listed bit is set. This is the universal idiom, not an
invention: NASA's own `hls-vi` uses `cloud_like = int("00001110", 2)` (bits 1/2/3) and tests
`fmask & cloud_like`; GEE's HLS guidance builds the same integer with `1 << bit` and `bitwiseAnd`.

**The HLS default is `bits = (1, 2, 3, 4)`** — cloud, adjacent-to-cloud/shadow, cloud shadow **and
snow/ice**. This follows GEE's example rather than NASA's `hls-vi` (bits 1/2/3), and is the user's
call, 2026-09-04. It is a **deliberate asymmetry with the S2 default**, which masks cloud/shadow/
cirrus but leaves snow (SCL 11) and water (SCL 6) unmasked. Recorded here so it is not later
"fixed" into consistency by accident.

**Bit*field* extraction is named, not built.** HLS Fmask bits 6–7 are a 2-bit aerosol enum, not a
flag; MODIS QA is largely enums. A future `mask_type="bitfield"` slots into the same growable
constant. Nobody masks clouds with the aerosol level.

**`MaskSpec` is defined as "a named band that is either read or computed."** The `producer` field
that makes the second half real is [#98](https://github.com/nikhilsrajan/fsd/issues/98) and is not
implemented; the *definition* is fixed now because `MaskSpec` is serialized into every catalog footer
and `_mask_spec_from_json` rejects unknown fields.

**`FSD_DECLARATION_VERSION` goes 1 → 2.** Without the bump, an older fsd reading a new footer reports
"unknown field 'bits'" instead of the intended "written by a newer fsd — upgrade" (spec 35 §5a).

### D8 — Canonical band names are STAC EO `common_name`, mapped by fsd

fsd addresses bands by the **STAC EO `common_name` vocabulary** (`red`, `nir`, `nir08`, `swir16`,
`swir22`, …). `CollectionDeclaration.band_aliases` maps canonical name → the collection's native
asset key. **fsd declares the mapping; the provider's published `common_name` is not trusted**, for a
demonstrated reason:

| canonical | HLS L30 | HLS S30 | S2 L2A | NASA's correspondence table |
|---|---|---|---|---|
| `red` | B04 | B04 | B04 | pair |
| `nir08` (narrow ~0.86) | **B05** | **B8A** | B8A | **L30 B05 ↔ S30 B8A** |
| `nir` (broad ~0.835) | — | B08 | B08 | S30 B08 has **no** L30 equivalent |

MPC assigns `common_name: "nir"` to *both* L30 `B05` and S30 `B08`, and leaves `B8A` with no common
name — pairing the two bands NASA explicitly declines to pair. MPC also **contradicts itself**: its
`landsat-c2-l2` collection names the same OLI band 5 `nir08`.

**Requests normalize to canonical form.** `bands=["B8A"]` and `bands=["nir08"]` against S30 produce
the *same* cube at the *same* path; without normalization two spellings yield two byte-identical
cubes at two digests that the skip logic can never reconcile. The prize is concrete: an adapter
declaring `required_bands=["red", "nir08"]` runs unchanged against S2 L2A, HLS S30 and HLS L30.

**`_select_item_files`'s silent skip becomes a raise** (`sources/mpc.py:234`).

### D9 — A collection declares what must not be mosaicked together

`CollectionDeclaration` gains **`mosaic_partition: tuple[str, ...]`** (catalog property keys that must
hold a single value within one build) and **`partition_policy: "raise" | "auto"`**. `build_datacube`
enforces it generically. Full rationale: **ADR 0029**.

- `sentinel-1-rtc`: `mosaic_partition = ("sat:orbit_state",)`, `partition_policy = "raise"`.
- `sentinel-2-l2a`, `hls2-s30`, `hls2-l30`: `()` — no enforcement, no behaviour change.

**The error is the discovery mechanism.** It enumerates the available
`(orbit_state, relative_orbit)` pairs with acquisition counts and ROI coverage, because relative
orbit numbers are a function of geometry and dates and cannot be known in advance.

**`sat:relative_orbit` is offered as a filter and reported, but not enforced** — the evidence splits.
Strict per-timestep comparison wants it fixed (GEE), but a 250 km IW swath with 175 orbits per 12-day
cycle means fixing it caps the ROI to one swath and roughly halves temporal density, and WorldCereal
— the global operational crop system — deliberately does not fix it. fsd enforces what is nearly
always wrong to mix, and reports what is context-dependent.

`orbit_state` / `relative_orbit` are **build-time selectors, not merely download filters**: a catalog
downloaded without a filter contains mixed orbits, and the build is where the partition must be
satisfied. They therefore appear on every verb that builds, and filter the catalog before the build.

### D10 — Authentication is a collection capability

`CollectionDeclaration.requires_subscription_key: bool`; `sentinel-1-rtc` sets it. MPC as a *provider*
is anonymous; one of its collections is not.

**No new verb parameter.** `PC_SDK_SUBSCRIPTION_KEY` is already the mechanism (`config.py:75`), read
by the `planetary-computer` package itself, so there is nothing to plumb — an fsd parameter would be
a second source of truth for the same secret.

**A preflight before any network call** is mandatory here rather than nice-to-have: unauthenticated
RTC access fails with **404, not 403**, and a 404 from a STAC search is indistinguishable from a
legitimate empty result. Without the preflight a user without a key concludes their ROI has no
Sentinel-1 coverage. The error must name the collection, the env var, and that the key comes from the
**developer portal**, not a JupyterHub token.

On AML the key rides the existing Key Vault path (`secrets.get_secret`) already used for CDSE
credentials. No second secret mechanism.

### D11 — `reference_band` is decoupled from `native_grid`

They are different facts. `native_grid` is about **tiling** (is there an MGRS-style grid to collapse
across?); `reference_band` is about **band resolution uniformity** (do bands within a granule need
resampling onto each other?). S2 needs a reference because its bands are 10/20/60 m. **HLS does
not** — every optical band is 30 m with identical `proj:shape [3660, 3660]`. **S1 RTC does not** —
VV and VH are both 10 m. Both are tiled/scene-based, so `native_grid=False`; that combination is
currently inexpressible.

- **`reference_band=None` gains its own meaning**, independent of `native_grid`: bands are
  grid-uniform, use the first requested band, run no resample step.
- `sentinel-2-l2a` → `"B08"` (unchanged); `sentinel-1-rtc`, `hls2-s30`, `hls2-l30` → `None`.
- **Add the missing guard:** a declared non-`None` `reference_band` absent from `bands` raises a
  preflight error instead of failing inside the merge.

This does not resolve [#1](https://github.com/nikhilsrajan/fsd/issues/1) — S2 at 20 m still needs a
different reference band. It removes a no-op; it does not choose a different target. Note that for S1
and HLS the resampling-quality question ([#100](https://github.com/nikhilsrajan/fsd/issues/100))
simply does not arise: there is nothing to resample.

### D12 — Catalog schema changes, no shim, no migration tool

| change | why |
|---|---|
| `satellite` → `collection` | the column already holds a collection id |
| `+ scale` | D5 |
| `+ properties` (JSON, the source item's STAC properties verbatim) | D9's enforcement needs `sat:orbit_state`; one generic column rather than per-collection ones |

The standing policy holds: **no read-time back-compat shim** (`catalog/catalog.py:177`, spec 34
`[G4]`). A migration CLI was considered and **rejected by the user (2026-09-04)** in favour of
re-downloading and regenerating cubes on AML. That also retires the stale radiometry in the Austria
archive — a fresh ingest under post-spec-34 code stamps the correct baseline offset, where the
existing archive is ~1000 DN high.

### D13 — Registration is driver-side; the declaration travels as JSON

`fsd.collections.register(id, declaration)` is a **public, plain in-process dict** — no entry points,
no packaging, no image rebuild. **The driver resolves `collection=` to a `CollectionDeclaration`
before dispatch, and the resolved declaration travels as JSON** in a control file under the run
folder that every shard reads. The variant's *name* travels alongside for the digest and cube
metadata. **Nodes never consult a registry** — done uniformly, including for built-in collections, so
there is one code path rather than two where only the user-variant path breaks and only remotely.
Full rationale: **ADR 0031**.

**A declaration may not contain callables.** A custom mosaic function, or #98's mask `producer`, must
be a `"module:attr"` string resolved node-side against an installed package, as `ModelAdapter` does.

### D14 — Artifact facts vs build policy

`CollectionDeclaration` holds two kinds of fact, documented as two groups:

| group | fields | may vary per build? |
|---|---|---|
| **Artifact facts** (describe the bytes) | `nodata`, `scale`, `radiometry_bands`, `band_aliases`, `requires_subscription_key` | **No** — stamped at ingest; the artifact self-describes (ADR 0012) |
| **Build policy** (bytes → cube) | `mask_spec`, `mosaic_method`, `mosaic_partition`, `partition_policy`, `reference_band` | **Yes** |

A build may use a **different named collection** from the catalog's stamp **only if its artifact
facts are identical**; differing artifact facts raise. So `s2-strict` (a mask variant) builds fine
against a catalog stamped `sentinel-2-l2a` — the bytes are the same granules — but a variant
claiming `nodata=-9999` against a catalog stamped `nodata=0` raises, because that is a lie about the
artifact.

The old `scl_mask_classes` override was wrong not because it was S2-shaped but because it silently
overrode a **stamped** fact.

### D15 — Not every (source, collection) pair is valid

Each source module declares which collections it serves — `cdse` → `("sentinel-2-l2a",)`, `mpc` →
the four. `source="cdse", collection="sentinel-1-rtc"` raises at preflight, naming what that source
does serve. Orthogonal axes do not imply a full cross product.

### D16 — One cube, one collection

`build_datacube` resolves one declaration, one `reference_band`, one `nodata`. It stays that way.
Fusion is [#99](https://github.com/nikhilsrajan/fsd/issues/99): ADR 0010's calendar mosaic already
gives two cubes over the same window an identical `timestamps` axis, but each resamples to *its own*
reference image, so band-axis concatenation needs a **reference grid above the collection** — a new
concept, better designed after two collections exist independently.

### D17 — The Sentinel-1 collection is `sentinel-1-rtc`

Not `sentinel-1-grd`. GRD needs a per-pixel, range-dependent calibration LUT that fsd's scalar
offset/scale model cannot express, declares no `raster:bands` at all (so the artifact does not
self-describe, against ADR 0011/0012), and is EPSG:4326 on a degree grid that will never co-grid with
10 m UTM. Full rationale, including the "it isn't map-projected" objection that turned out to be
**false**, and MPC's incorrect "radiometric terrain correction applied" GRD asset description:
**ADR 0028**.

### D18 — Validation uses two windows, because HLS cannot reach 2018

MPC's HLS2 archive starts **2020-01-01**; the labelled Austria window is Apr–Sep **2018**, and the
EuroCrops labels are 2018 (`GEOM_DATE_` = 2018-07-31 on all 1015 records; the `MFA-2021` string in
the INSPIRE ids is the dataset publication version, not the crop year). So one window cannot serve
both.

- **Window A — 2018, labelled.** `s2grid=476da24`, Apr–Sep 2018, `sentinel-2-l2a` +
  `sentinel-1-rtc`, with the EuroCrops labels. Proves what needs labels: `create_training_data`
  running unchanged across two collections, and S1 orbit enforcement end-to-end.
- **Window B — 2021, unlabelled.** Same cell, Apr–Sep 2021, `hls2-s30` + `hls2-l30` +
  `sentinel-2-l2a`. Proves band aliasing and bitmask masking. Including S2 over the *same* dates is
  what makes D8 numerically testable: `red`/`nir08` from S2 L2A and HLS S30 must agree over the same
  fields on the same dates.
- **Footprint is one grid cell, not the four-tile `AT_ROI`.** The full ROI was 74 GB for one
  collection. The multi-tile/multi-CRS path is already covered by existing S2 tests and does not need
  re-proving per collection.
- Window B may reuse the 2018 EuroCrops polygons **as geometry** for a `create_training_data`
  plumbing run. The run-book must label it **plumbing, not a science result**.

## 4. Phases

**P1 — the contract. No new collections.**
D1, D2, D3, D4, D5, D6, D7 (shape + `bits`, unused), D8 (mechanism + the `_select_item_files` raise),
D11, D12, D13, D14, D15, D16. Ends green with **S2 L2A behaving identically through the new
machinery**, proven by pytest and existing synthetic fixtures — no network, no cluster.

**P2 — `sentinel-1-rtc`.** D9, D10, D17. Validated on Window A.

**P3 — `hls2-s30` + `hls2-l30`.** D7 (bitmask implementation), D8 (the alias maps). Validated on
Window B.

## 5. Acceptance criteria

**P1**

1. `pytest -q` and `ruff check src tests demos examples` clean.
2. No public verb accepts `scl_mask_classes`; `grep -rn scl_mask_classes src/` returns only the S2
   declaration's `classes` and config's default list.
3. A cube built for S2 L2A through the new machinery is **bit-identical** to one built before the
   change, given the same inputs and an equivalent declaration. (Path differs; pixels do not.)
4. Two builds differing only in `collection` resolve to **different** cube paths.
5. `bands=["B8A"]` and `bands=["nir08"]` against a collection declaring that alias resolve to the
   **same** path.
6. A requested band absent from an item **raises**, naming the band and the collection.
7. A declared non-`None` `reference_band` absent from `bands` raises at preflight.
8. `source="cdse", collection="sentinel-1-rtc"` raises, naming CDSE's served collections.
9. A `collection=` string registered only on the driver reaches an AML shard correctly — tested by
   asserting the control file carries the declaration JSON and the node reads it without a registry.
10. `from_json` on a v1 footer still parses; a v2 footer read by v1-era code raises the
    version-mismatch message, not an unknown-field message.

**P2**

11. A build whose rows span both orbit states **raises**, and the message enumerates the available
    `(orbit_state, relative_orbit)` pairs with counts and coverage.
12. The same build with `orbit_state=` given succeeds.
13. Two cubes differing only in `orbit_state` resolve to different paths.
14. With `PC_SDK_SUBSCRIPTION_KEY` unset, `collection="sentinel-1-rtc"` raises at preflight
    **before any network call**.
15. Window A run-book: S1 and S2 cubes build for the same cell/window; `create_training_data`
    produces arrays from each with **no verb-signature difference between them**.

**P3**

16. HLS Fmask masking with `bits=(1,2,3,4)` masks exactly the pixels where those bits are set,
    verified against a hand-built fixture.
17. Window B run-book: `red` and `nir08` from `sentinel-2-l2a` and `hls2-s30` over the same cell and
    dates agree within a stated tolerance; a disagreement is an alias-map bug, not noise.
18. Visual QGIS check per collection (per `CLAUDE.md`).

## 6. Risks

- **The re-download is the long pole**, not the code. P1 is deliberately network-free so the
  abstraction lands before any transfer starts.
- **A bit-identical S2 cube (AC 3) may be impossible if any rounding shifts.** If so, that is a
  finding to report, not something to paper over — it would mean the "no behaviour change" claim is
  false and needs stating.
- **`properties` as a JSON column** could become a dumping ground. It carries the source item's STAC
  properties verbatim and nothing else; anything fsd *uses* is either a declaration field or a
  first-class column.
- **HLS L30/S30 band-name collision is a live foot-gun** until D8 lands: `B05` is NIR on L30 and
  Red-Edge 1 on S30. The alias map is the fix; until then, native names must not be encouraged.
- **The declaration JSON on the wire adds a control-file read per shard.** Negligible next to
  #48/#54's existing per-shard overhead, but it should not be added blindly to the driver-side loop.

## 7. Alternatives considered

- **A fused `source="mpc:sentinel-1-rtc"` string** — welds provider to product; the axes genuinely
  cross (S2 L2A is on CDSE *and* MPC; HLS is on MPC *and* LP DAAC). ADR 0030.
- **Rename `scl_mask_classes` → `mask_classes` and keep it** — preserves both the lying stamp and the
  two sources of truth, and still costs the digest change.
- **A generic STAC `query=` passthrough** instead of named filters — leaks provider vocabulary into
  the verb. D6.
- **A multi-collection cube** — makes `mask_spec`, `nodata`, `dtype`, `reference_band` per-*band*,
  turning the declaration into a per-band table, designed against zero fusion experience. D16 / #99.
- **A migration CLI for existing catalogs** — designed (modelled on `restamp_cli`, rewriting only the
  Parquet, no re-download) and then **rejected by the user** in favour of a clean re-ingest. D12.
- **Auto-selecting the best-covering S1 orbit and printing it** — an auto-selection that gets printed
  is one that gets ignored, and it makes a science choice for the user. ADR 0029.
- **Node-side collection resolution via `module:attr`** — works, but forces a user's variant to be a
  packaged, installed module plus an image rebuild, for what is data. ADR 0031.

## 8. Questions at sign-off

All eighteen decisions above were put to the user individually during the grilling session of
2026-09-04 and confirmed. **Two of the author's own claims were checked and found wrong during that
session, and both are recorded rather than quietly dropped:**

- **"MPC's GRD is not map-projected."** False — GRD *items* carry `proj:epsg: 4326` and a real
  `proj:transform`, and serve COG assets. The RTC decision rests on calibration, self-description and
  grid instead (ADR 0028).
- **"The datacube pipeline is integer-only / clips to uint16."** False — `_stack_datacube` takes its
  dtype from the loaded image, and `apply_offset` early-returns at `offset == 0`. D5 shrank from a
  rewrite to four small moves as a result.

A third was corrected by the **user**: the EuroCrops labels are 2018 (deliberately matched to the
imagery), not 2021 — which reversed the plan to move everything to a 2021 window and produced D18's
two-window design instead.

## 9. Best-practice alignment / sources

- **[MPC STAC collection + item JSONs](https://planetarycomputer.microsoft.com/api/stac/v1/collections)**
  (`sentinel-1-rtc`, `sentinel-1-grd`, `hls2-s30`, `hls2-l30`, `landsat-c2-l2`) — every concrete
  value in D8, D11, D17 and §1: RTC's `float32`/`nodata: -32768`/10 m/UTM; GRD's `proj:epsg: 4326`
  and absent `raster:bands`; HLS's 30 m `proj:shape [3660,3660]`, asset lists and `eo:cloud_cover`;
  the `common_name` assignments — including MPC naming OLI band 5 `nir08` in `landsat-c2-l2` but
  `nir` in `hls2-l30`, the self-contradiction that justifies fsd declaring its own map.
- **[MPC `sentinel-1-rtc` collection metadata](https://planetarycomputer.microsoft.com/dataset/sentinel-1-rtc)**
  — "A Planetary Computer account is required to retrieve SAS tokens to read the RTC data": the whole
  of D10.
- **[microsoft/PlanetaryComputer discussions #167, #182, #184](https://github.com/microsoft/PlanetaryComputer/discussions/167)**
  — that unauthenticated RTC access fails as **404, not 403**, and that the key must come from the
  developer portal rather than JupyterHub. This is why D10's preflight is mandatory rather than
  advisory.
- **[Copernicus Sentinel-1 documentation](https://documentation.dataspace.copernicus.eu/Data/SentinelMissions/Sentinel1.html)**
  and **[ESA SNAP Calibration Operator](https://step.esa.int/main/wp-content/help/versions/10.0.0/snap-toolboxes/eu.esa.microwavetbx.sar.op.calibration.ui/operators/CalibrationOp.html)**
  — GRD's `value = DN²/A²` with a **range-dependent** gain plus a GRD constant offset: the reason
  D17 rejects GRD, since fsd's radiometry is a scalar per-row offset.
- **[NASA HLS — Algorithms](https://hls.gsfc.nasa.gov/algorithms/)** — the Fmask bit layout (bit 1
  cloud, 2 adjacent, 3 shadow, 4 snow/ice, 5 water; 6–7 aerosol enum) and that HLS's Fmask does not
  distinguish cirrus, so bit 0 is effectively unused. D7's bit list and the flags-vs-enum split.
- **NASA `hls-vi`** — `cloud_like = int("00001110", 2)` then `fmask & cloud_like`: confirmation that
  "any listed bit set" is the standard idiom rather than an invention, and that bits 1/2/3 are
  NASA's own default. D7.
- **[GEE HLSL30/HLSS30 catalog entries](https://developers.google.com/earth-engine/datasets/catalog/NASA_HLS_HLSL30_v002)**
  — the same `1 << bit` / `bitwiseAnd` idiom, and the one place practice differs: GEE's example also
  masks snow/ice (bit 4). The user chose GEE's stricter default over NASA's. D7.
- **[NASA HLS spectral bands](https://www.earthdata.nasa.gov/data/projects/hls/spectral-bands)** —
  the L30↔S30 correspondence table: **L30 B05 (NIR Narrow) ↔ S30 B8A**, with S30 B08 having *no* L30
  equivalent. The single fact that makes MPC's `common_name` assignment wrong and D8 necessary.
- **[STAC EO extension](https://github.com/stac-extensions/eo)** — the `common_name` vocabulary fsd
  adopts, and that `nir08`/`nir09` are narrow bands centred ~0.85/0.95 µm. D8's canonical names.
- **[LP DAAC HLS Python tutorial](https://lpdaac.usgs.gov/documents/923/HLS_Tutorial_vRI80pO.html)**
  and **[hrodmn.dev](https://hrodmn.dev/posts/hls/)** — independent confirmation of the `fmask &
  bitmask` idiom, and that the standard HLS workflow is "select per product, then rename to common
  names" (the pattern D8 formalizes).
- **[GEE — Detecting Changes in Sentinel-1 Imagery (pt 2)](https://developers.google.com/earth-engine/tutorials/community/detecting-changes-in-sentinel-1-imagery-pt-2)**
  and **[GEE SAR Basics](https://developers.google.com/earth-engine/tutorials/community/sar-basics)**
  — that analysts should specify *both* orbit pass and relative orbit so local incidence angles stay
  comparable. The strict end of D9's evidence.
- **[On the influence of acquisition geometry in backscatter time series over wheat](https://www.sciencedirect.com/science/article/pii/S0303243421003780)**
  — that combining geometries requires incidence-angle normalization *followed by* azimuthal
  anisotropy correction: two corrections fsd does not have, hence enforcement rather than blending.
- **[WorldCereal (ESSD 2023)](https://essd.copernicus.org/articles/15/5491/2023/)** — that the global
  operational crop system does *not* fix relative orbit and compensates with percentile features.
  The counterweight that makes D9 report rather than enforce `sat:relative_orbit`.
- **[ESA Sentinel-1 revisit and coverage](https://sentinel.esa.int/web/sentinel/user-guides/sentinel-1-sar/revisit-and-coverage)**
  — 250 km IW swath, 175 orbits per 12-day cycle, 6-day constellation repeat: the quantities behind
  "fixing relative orbit caps the ROI to one swath and halves temporal density". D9.
- **[Digital Earth Africa Sentinel-1 specs](https://docs.digitalearthafrica.org/en/latest/data_specs/Sentinel-1_specs.html)**
  and **[ASF RTC Product Guide](https://hyp3-docs.asf.alaska.edu/guides/rtc_product_guide/)** — that
  γ⁰ is preferred where topography matters, and what RTC removes. The science half of D17.
- **[OmniCloudMask](https://github.com/DPIRD-DMA/OmniCloudMask)** — inputs (Red/Green/NIR, 10–50 m,
  float32) and outputs (classes 0 clear / 1 thick cloud / 2 thin cloud / 3 cloud shadow), which is
  what showed a computed mask needs no new *interpretation*, only a new *origin*. D7's "read or
  computed" definition and #98.

## 10. Implementation note — build order

P1 → P2 → P3, each in its own worktree branch, implemented in a **Sonnet** session
(`/model sonnet`, `/effort medium`) against this spec, reviewed by Opus, then merged `--no-ff` and
the worktree pruned (the standing practice in `CLAUDE.md`). Downloads and AML regeneration are
**run-books** in `fsd/runbooks/` that the user executes, returning each step's `_result.json`
(spec 24). The re-download cannot start until P1 lands, because P1 is what changes the catalog
schema. `v0.2.0` is cut after P3 — this breaks the public API, and `v0.1.0` was cut on the
understanding that it would.
