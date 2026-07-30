---
status: current
summary: The committed offline tutorial micro-fixture (real COGs clipped to one grid cell); signed off, amended same day for an in-region VM build.
---

# Spec 42 — the tutorial micro-fixture: a committed, offline, real-pixel dataset

**Status: ✅ SIGNED OFF (2026-07-30, user) — amended A1 the same day, see §8.** Carved out of
**spec 41 (D11, phase P6)** because this is data engineering with its own acceptance criteria and its
own failure modes, not documentation.

> **⚠️ Read §8 (amendment A1) before §2 D1.** A1 moves the build **in-region onto an Azure VM,
> sourcing the blob MPC archive instead of the local CDSE archive** — which supersedes D1's
> radiometry mechanism and revises acceptance test 2. D1 is kept intact below because its reasoning
> is the fallback path.

> **What this delivers:** `fsd/tests/data/tutorial/` — a ~15–25 MB committed dataset that drives
> the **entire local pipeline** (datacube → training data → train → inference → COG/STAC/crop map)
> **offline, with zero credentials, in minutes.**
>
> **Why it exists:** spec 41 D11. fsd reads whole 110 km MGRS-tile granules, so no real download is
> tutorial-sized (~426 MB/granule; ~3.4 GB for one tile-month). And fsd currently **ships zero
> data** — `.gitignore` blanket-ignores `*.tif`/`*.geojson`/`*.parquet`/`*.npy`, and `shapefiles/`
> lives outside the repo. A tutorial that "cannot fail" is impossible until this exists.
>
> **It gates spec 41 P7** (tutorial + how-tos) and nothing else. P1–P5 proceed independently.

---

## 1. The target, measured

Everything below is measured, not assumed.

**Grid cell `4772924`** — selected from the 300 cells over `AT_ROI` because it holds the most
labelled fields.

| Property | Value | How established |
|---|---|---|
| Bounds (EPSG:4326) | 15.3900 – 15.4717 E, 48.4821 – 48.5320 N | `grid.roi_to_s2_grids('AT_ROI.geojson', grid_size_km=5)` |
| Labelled fields | **43**, 7 crops | `sjoin` with `AT_2018_TRAIN.geojson` (900 fields) |
| Crop distribution | maize 20 · hemp 13 · alfalfa 4 · mustard 2 · winter wheat 2 · pasture 1 · spring wheat 1 | same |
| **MGRS tile** | **`T33UWP`, single tile — 24/24 granules** | granule-id token, `demo_e2e` catalog |
| Granule dates | 24, **2018-04-06 → 2018-09-28** (~5–15 day cadence) | same |
| Processing baseline | **`N0500` on all 24** | `_N0500_` token in every granule id |

Two consequences worth stating: the cell is **entirely inside one MGRS tile**, so the fixture
exercises the simple single-tile path (no multi-CRS merge — noted for the how-to); and it
**strictly dominates `s2grid=476da24`** as a test ROI, which is also single-tile-in-`T33UWP` but
contains **zero** labels (it sits ~100 km east, near Vienna).

---

## 2. Decisions

### D1 — Source the pixels by clipping the existing archive, and **stamp radiometry by re-derivation**

The source is `fsd/tests/outputs/demo_e2e/imagery/` (74 GB, 207 granules, 4 tiles, Apr–Sep 2018,
B04/B08/B8A/SCL, already COG, gitignored).

**The catch, and it is the whole risk of this spec.** That archive is **radiometrically
un-harmonized** and its catalog schema proves it:

| Catalog | Columns |
|---|---|
| `demo_e2e/imagery` (CDSE-era) | `id, satellite, timestamp, s3url, local_folderpath, files, cloud_cover, geometry` — **no `boa_add_offset`** |
| `mpc_baseline` (MPC-era) | same **+ `boa_add_offset`**, values `[-1000, 0]` |

All 24 granules are baseline `N0500` (≥ 04.00 ⇒ ESA `BOA_ADD_OFFSET = −1000`; cross-validated in
**spec 32**), so pixels built from this archive without a stamp read **~1000 DN high** — the open
TODO #30/#10 defect. A tutorial that teaches wrong radiometry is worse than no tutorial.

**Considered and rejected: a fresh MPC download.** MPC stamps `boa_add_offset` correctly by
construction (spec 32/34) and is anonymous, but covering the same Apr–Sep 2018 window means ~24
granules × ~426 MB ≈ **~10 GB** of download for a 20 MB output. *A cross-check against the existing
`mpc_baseline` archive was also considered and does not work:* it is the same tile `T33UWP` but
**2022 dates** (9 granules, Jan–Mar 2022, B04+SCL only), so no acquisition overlaps 2018 and no
per-pixel comparison is possible.

**Decision:** clip from the local archive, and write the fixture catalog **with `boa_add_offset`
re-derived independently from the baseline token in each granule id** (`_N0500_` ⇒ ≥ 04.00 ⇒
−1000) — the same independent-re-derivation technique spec 40 D14 uses for its offset assertion,
rather than copying a value from a row that does not have one.

Two things make this safe rather than optimistic:
- **ADR 0013's loudness rule works in our favour**: an unstamped file-backed catalog *raises*. The
  fixture cannot silently ship unstamped.
- The re-derivation is asserted in the acceptance tests (§4) as an **independent** check, not a
  restatement of what the builder did.

Note this makes the fixture the **first correctly-stamped artifact derived from that archive** — a
small, contained down-payment on TODO #30/#10, which stays open for the archive itself.

### D2 — Bands, timestamps and what gets committed

- **Bands: `B04`, `B08`, `SCL`.** B04+B08 give NDVI (and B08 at 10 m is the resampling reference
  per the project's reference-image rule); SCL is required for masking. **`B8A` is excluded** — it
  is 20 m, adds ~1/3 to the byte count, and `DemoRF`-style tutorial features do not need it.
- **All 24 timestamps kept.** At `mosaic_days=20` over Apr–Sep this yields ~9 mosaic intervals —
  a real seasonal time series with real gaps and real cloud, which is the point. Dropping to 12
  would halve the bytes and halve the pedagogy; the byte count is already acceptable.
- **Clip window:** the cell bounds **plus a one-pixel-plus-resampling buffer**, in the granule's
  native UTM CRS, so the datacube builder's crop→reproject→merge→resample-to-B08 path has margin
  and the tutorial does not produce an artificial nodata edge.
- **Estimated size:** 24 granules × (B04 ~500×500 + B08 ~500×500 + SCL ~250×250) uint16, COG,
  compressed ⇒ **~15–25 MB.** Precedent for committed binaries: `demos/figures/*.png` is 3.1 MB.
  **If the built fixture exceeds 30 MB, stop and report** rather than committing it (§5).

### D3 — Labels ship with the fixture, collapsed to three classes

- `tests/data/tutorial/fields.geojson` — the 43 fields clipped to the cell, columns `fid` +
  `crop` (original) + `label` (collapsed).
- **`label` ∈ {`maize`, `hemp`, `other`}.** The raw 7-class distribution over 43 samples is not
  trainable (four near-singletons); a 3-class split is. The tutorial states the collapse and why.
- `tests/data/tutorial/roi.geojson` — the cell polygon, for the inference leg.

### D4 — The generator is a committed, re-runnable script

`tests/data/tutorial/build_fixture.py` — committed alongside the output, taking the archive path as
an argument. Reasons: the fixture must be **reproducible** rather than a mystery binary; it will be
rebuilt when the archive or the schema moves; and it documents exactly what was done to ESA pixels
(relevant to D5's licensing). It is **not** part of the `fsd` wheel and **not** run by the test
suite — it is a one-off tool whose *output* is the artifact.

### D5 — Licensing: the modified-data notice, verbatim

`tests/data/tutorial/NOTICE` carries **exactly**:

```
Contains modified Copernicus Sentinel data 2018
```

Verified against the European Commission's *Legal notice on the use of Copernicus Sentinel Data and
Service Information*, which grants *"(a) reproduction; (b) distribution; (c) communication to the
public; (d) adaptation, modification and combination"*, and requires the plain notice
*'Copernicus Sentinel data [Year]'* for unmodified data but *'Contains modified Copernicus Sentinel
data [Year]'* **where the data "have been adapted or modified"**. Clipping is modification, so the
**modified** form is the correct one — the plain-reading guess is wrong. The same string appears in
`docs/tutorial.md` and in the fixture's `README.md`.

### D6 — `.gitignore` gains a narrow negation

```gitignore
# Tutorial micro-fixture (spec 42) — deliberately committed; see tests/data/tutorial/NOTICE
!tests/data/tutorial/**
```

Placed after the blanket data rules, scoped to that one path. This deliberately pokes a hole in a
rule that exists for good reasons (*"never commit downloaded tiles or datacubes"*), so it is
narrow, commented, and points at the notice.

---

## 3. Build steps

The generator performs, in order:

1. **Select** — read the archive catalog, filter to `T33UWP` granules intersecting the cell
   (expect **24**), assert all carry an `_N0500_` token.
2. **Clip** — for each granule × band, window-read the source COG to the buffered cell bounds in
   native UTM and write a COG through **`raster.cog.to_cog`** (the single chokepoint, ADR 0014) so
   the fixture is byte-shaped exactly like a real archive.
3. **Catalog** — write `catalog.parquet` with the same schema as the source **plus
   `boa_add_offset`**, re-derived per D1, and per-granule `geometry` recomputed from the *clipped*
   raster bounds (not copied — the footprints changed).
4. **Labels + ROI** — write `fields.geojson` (43 fields, collapsed `label`) and `roi.geojson`.
5. **Notice** — write `NOTICE` and `README.md` (provenance: source granule ids, clip bounds, date,
   generator invocation).
6. **Report** — print a `_result.json` (spec 24 shape) with granule count, per-band byte totals,
   total size, and the derived offset.

---

## 4. Acceptance criteria

All four must pass. **1–3 are automated in `tests/test_tutorial_fixture.py`** and become part of
the 520-test suite; 4 is the spec-41 D13 cold-start gate and is the user's.

1. **Structural** — 24 granules × 3 bands present; every file opens as a valid COG; `catalog.parquet`
   has one row per granule with non-empty geometry; row count == granule count.
2. **Radiometric (independent)** — `boa_add_offset == −1000` for every row, re-derived in the test
   *from the granule id's baseline token*, not read from the column the generator wrote. This is
   the assertion that makes D1 safe.
3. **Pipeline** — a full offline run over the fixture succeeds and is **deterministic**:
   `create_training_data` → 43 ids, 3 classes, expected `(pixels, timestamps, bands)` shape with
   `T == 9` at `mosaic_days=20`; train a trivial classifier; `run_inference` → one `output.tif` +
   STAC item; assert cube values are in a plausible post-offset reflectance range (i.e. the
   ~1000 DN error would fail this).
4. **Cold-start** — the user, on a fresh clone and fresh venv, follows `docs/tutorial.md`
   literally and reaches a crop map. First failing instruction stops the run and is reported.

---

## 5. Risks

| Risk | Mitigation |
|---|---|
| **The un-harmonized source is the whole risk** (TODO #30/#10) | D1's independent re-derivation + acceptance test 2 + ADR 0013's loudness rule (unstamped catalog raises) |
| **The clipped-granule path may not satisfy the builder** — it crops, reprojects, merges and resamples to a B08 reference | Acceptance test 3 is exactly this end-to-end run. **If it fails, that is a real builder finding** → file an issue, do not paper over it in the generator |
| **Fixture exceeds a reasonable committed size** | Hard stop at **30 MB**; fall back to 12 timestamps before dropping bands |
| **Committed ESA pixels in a public MIT repo** | D5, verified against the primary EC notice |
| **The fixture drifts from the real archive's schema** | The generator is committed and re-runnable (D4); acceptance test 1 pins the schema |
| **Single-tile only ⇒ multi-CRS merge untested by the tutorial** | Accepted and documented; that path stays covered by `AT_ROI` and the existing suite |

---

## 6. Best-practice alignment / sources

**Legal notice on the use of Copernicus Sentinel Data and Service Information — European
Commission, DG GROW**
([PDF](https://sentinels.copernicus.eu/documents/247904/690755/Sentinel_Data_Legal_Notice)).
Contributed the legal basis for committing clipped ESA pixels to a public repo — it grants
*"reproduction; distribution; communication to the public; adaptation, modification and
combination"* — and, decisively, the **distinction between the two attribution notices**: the plain
*'Copernicus Sentinel data [Year]'* versus *'Contains modified Copernicus Sentinel data [Year]'*
required *"where the … Data … have been adapted or modified"*. D5 uses the **modified** form
because clipping is modification. Read from the primary EC document rather than a summary, since it
is a legal claim.

**Internal, load-bearing:** **spec 32** cross-validated the ESA baseline-04.00 ⇒
`BOA_ADD_OFFSET = −1000` rule (not re-derived here — cited); **spec 34 / ADR 0011** give the
ingest contract this fixture must satisfy (store raw DN, *declare* radiometry, never bake
normalized pixels); **ADR 0013** supplies the loudness rule that prevents an unstamped fixture
shipping silently; **ADR 0014** makes `raster.cog.to_cog` the only COG writer, which is why step 2
routes through it; **spec 40 D14** supplied the independent-re-derivation-from-the-granule-id
technique adopted in D1 and acceptance test 2; **spec 41 D11/D13** is the parent decision and the
cold-start gate.

---

## 7. Not in scope

- **Fixing TODO #30/#10 for the whole archive.** This spec stamps *the fixture* correctly; the
  74 GB archive stays as it is.
- **A multi-tile / multi-CRS fixture.** Single tile by design (D2, §5).
- **Writing the tutorial itself** — spec 41 P7, gated on this.
- **Shipping the fixture inside the `fsd` wheel.** It lives under `tests/data/`, available from a
  clone, not from `pip install`. If a wheel-installed user needs it later, that is a packaging
  decision with its own trade-offs.

---

## 8. Amendments

### A1 — Build in-region on an Azure VM, sourcing the blob MPC archive (user, 2026-07-30)

**Trigger.** The user: *"I would like to run the spec 42 code on azure vm (which should ideally be
equivalent to running locally). This is so that I don't run out of data on my mobile hotspot."*

**This is not only a bandwidth decision — it removes this spec's central risk.** §2 D1 accepted a
real hazard: the *local* `demo_e2e` archive is CDSE-era and **declares no radiometry at all** (no
`boa_add_offset` column), so the fixture's offset had to be re-derived from the `_N0500_` token in
each granule id. The **blob** archive is different, and better. Measured from the verification
sample that runbook 37 landed locally
(`tests/outputs/p2_verify_archive/local_ingest/catalog.parquet`):

| Source | Example id | Radiometry columns |
|---|---|---|
| local `demo_e2e/imagery` (CDSE-era) | `S2B_MSIL2A_20180928T100019_**N0500**_R122_T33UWP_…` | **none** |
| blob archive, sampled by runbook 37-verify (MPC-era) | `S2A_MSIL2A_20180106T100401_R122_T33UVP_…` (**no N-token**) | **`offset`, `nodata`** |
| `mpc_baseline` (MPC-era) | `S2B_MSIL2A_20220219T100019_R122_T33UWP_…` | **`boa_add_offset`** |

So the blob archive is **MPC-sourced and self-declaring** (spec 40 A1 made `2_download` source from
MPC; spec 34/35 persist the declaration). Radiometric correctness becomes a property of the *source*
rather than something this generator must reconstruct.

**Decision.**

1. **The build runs on an in-region Azure VM, reading the blob MPC archive**; the ~15–25 MB output is
   written to blob and **landed home via `storage.transfer`** (the land-local pattern, spec 39 D4).
   Bulk reads never cross the WAN, so the hotspot pays for ~20 MB, not ~74 GB.
2. **Radiometry is read from the source's own declaration, not re-derived.** Note the id-token
   re-derivation of D1 is **impossible** on this path — MPC granule ids carry **no `_N####_` token**
   (see the table). This is a genuine mechanism change, not a relabelling.
3. **Never hardcode the declaration's column name.** It is `offset` in one catalog and
   `boa_add_offset` in another — read it through fsd's declaration API (spec 35 / ADR 0011), and let
   ADR 0013's loudness rule raise if the source is unstamped.
4. **All generator I/O is fsspec urls through `fsd.storage`** (ADR 0003); pixel reads via
   rasterio/GDAL VSI (the documented exception); COG writes via `raster.cog.to_cog`, which already
   supports a remote dst (ADR 0001). This is what makes "equivalent to running locally" true: source
   and destination are **arguments**, and local-vs-`abfss://` is config, not code (spec 31).
5. **The local CDSE path of D1 is retained as a documented fallback** — usable with no network at
   all, at the cost of the re-derived offset and its weaker guarantee.
6. **The run is driven by a run-book** (`runbooks/43-build-tutorial-fixture.md`), since Claude does
   not run networked or long scripts (spec 24). The run-book records **where the driver ran**, which
   spec 40 D10 established is a property of a run, not a detail.

**Preconditions the run-book must verify on the VM before clipping anything** — none can be checked
from the laptop, and all three would waste the run if assumed:

- the blob archive covers **`T33UWP`, Apr–Sep 2018**, with **B04, B08, SCL** (runbook 37 Phase 3
  landed 213 MPC granules over `AT_ROI`'s four tiles, so this is likely but unverified for *this*
  tile and band set);
- every selected row carries a **non-null radiometry declaration**;
- the granule count for cell `4772924` — the local CDSE archive gave **24**; the MPC archive is a
  different selection (different cloud-cover filtering and dedup, spec 33) and **may not give 24**.
  Whatever it gives is the fixture's timestamp count, and `T` in acceptance test 3 follows from it
  rather than being asserted at 9 in advance.

**Revised acceptance test 2 (replaces §4.2).** The independent-re-derivation check is unavailable, so:

- every fixture row carries a radiometry declaration that **round-trips through the declaration API**;
- the declaration was **copied from the source, not invented** — assert equality against the source
  catalog row, so a generator bug cannot manufacture a plausible-looking offset;
- cube values from acceptance test 3 fall in a **plausible post-offset reflectance range**, which is
  the check that would catch the ~1000 DN error regardless of how the offset arrived.

**Consequences and residual risk.** The radiometry hazard drops from "the whole risk of this spec"
(§5 row 1) to an ordinary provenance check, and TODO #30/#10 becomes irrelevant to the fixture —
though it stays open for the local archive. In exchange, the build acquires the cloud
prerequisites of spec 41 D2 (VPN, `az login`, an in-region VM), so it can no longer be done offline
on the preferred path. And **"equivalent to running locally" is a claim, not yet a measurement**: if
the VM and local builds produce different bytes for the same cell, that is a **storage-seam finding**
worth an issue in its own right, not a fixture problem to paper over. The fallback in (5) exists
precisely so that comparison remains possible.
