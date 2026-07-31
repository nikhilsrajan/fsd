---
status: current
summary: Build spec 42's committed tutorial micro-fixture — small ROI/label derivation on the laptop, pixel clipping in-region on an Azure VM, ~20 MB landed home and committed.
---

# Run-book 43 — build the tutorial micro-fixture (spec 42, amendment A1)

**You run this; Claude never runs networked/long scripts (spec 24).** Paste back each step's
`_result.json` from `tests/outputs/p6_tutorial_fixture/` — not the logs.

**What it produces.** `fsd/tests/data/tutorial/` — a **~15–25 MB committed** dataset that drives the
whole local pipeline (datacube → training data → train → inference → COG/STAC/crop map) **offline,
with zero credentials, in minutes.** It is what makes `docs/tutorial.md` able to promise success
(spec 41 D11 / ADR 0026). Contents: 24-ish granules × 3 bands of real Sentinel-2 COGs clipped to one
5 km grid cell, a `catalog.parquet`, 43 labelled fields, the cell polygon, and a `NOTICE`.

**Why it splits across two machines.** The two halves need different things and neither machine can
do both:

| Step | Where | Why there |
|---|---|---|
| 0 | **laptop** | needs `shapefiles/` (`AT_ROI`, `AT_2018_TRAIN`), which live at the **workspace root, outside the repo** — a `git clone` on a VM cannot supply them. Tiny, offline, no bulk data. **Its two outputs reach the VM by being committed** (48 KB) — see Step 0a. |
| 1–5 | **Azure VM in the `rise` VNet** | needs the **blob MPC archive**; reading it from a laptop would pull tens of GB over your hotspot, which is the whole reason for A1. |
| 6–7 | **laptop** | verify + commit. Only ~20 MB crosses the wire. |

- **Time:** ~15 min on the VM once set up; step 1 is the slow part the first time.
- **Cost:** trivial — a few hundred MB of blob reads, ~20 MB stored.
- **Safe to interrupt:** yes. The generator is idempotent per output file; re-run and it skips what
  exists. Nothing is deleted.

---

## Prerequisites

- [ ] **The generator script exists and is merged.** `tests/data/tutorial/build_fixture.py`, written
      by an implementation session against **spec 42 §3** (Sonnet@medium). This run-book does not
      create it. Its CLI contract is fixed in **Step 3 below and is normative** — the implementer
      must match it, or this run-book is wrong.
- [ ] A VM/compute instance **inside the `rise` VNet**. The storage account is deny-by-default
      firewalled, so "any Azure VM" will not do. **On this tenant plain VMs report *"SSH access from
      the public internet is disabled"*** → use an **Azure ML compute instance** (Studio → Notebooks →
      *Terminal*): inside the VNet, already signed in as you, no SSH needed. Validated this way
      before (run-book 34).
- [ ] `AZ_ARCHIVE_ROOT` — the blob archive root written by run-book 37, i.e. the prefix whose
      `archive/catalog.parquet` exists. Concrete values: **`AZURE_INFRA_PRIVATE.md` at the workspace
      root** (never in this repo). If you don't have that file, **file a ticket with your platform
      admin** for storage access first.
- [ ] No credentials of any kind for the imagery — the archive is already downloaded, and MPC was
      anonymous.

> **Do not put secrets in `~/cloudfiles/`** on a compute instance — that share is mounted on every
> instance in the workspace. Nothing here needs secrets, so the simplest safe move is: don't create
> any.

---

## Step 0 — laptop: derive the ROI and the labels (offline, seconds)

This is the half that needs `shapefiles/`. It writes two small GeoJSONs that the VM step consumes,
so the VM never needs the workspace root.

```bash
cd ~/NASA-Harvest/project/fetch_satdata_claude/fsd
source .venv/bin/activate

python tests/data/tutorial/derive_roi_and_labels.py \
    --at-roi   ../shapefiles/AT_ROI.geojson \
    --fields   ../shapefiles/AT_2018_TRAIN.geojson \
    --cell-id  4772924 \
    --out      tests/data/tutorial \
    --result   tests/outputs/p6_tutorial_fixture/_result_step0.json
```

- **Expect:**
  ```
  cell 4772924  bounds 15.3900,48.4821,15.4717,48.5320  fields 43  classes grain_maize_corn_popcorn=20 hemp_cannabis=13 other=10
  major crops (derived by area, not hardcoded): grain_maize_corn_popcorn, hemp_cannabis
  ```
- **PASS if:** `fields == 43`, three classes present, and both `tests/data/tutorial/roi.geojson` and
  `fields.geojson` exist. All of that is gated in `_result.json`'s `pass` — it is computed, not
  hardcoded.
- **The class names are long and that is correct** (spec 42 **A3**). The raw labels in
  `AT_2018_TRAIN.geojson` are HCAT compound names, and the two majors are **derived by clipped
  area**, not hardcoded — an earlier version compared against the literals `maize`/`hemp`, matched
  nothing, and collapsed all 43 fields into `other`. If you want a different split, pass
  `--n-major N` (N+1 classes); do not edit a crop name into the script.
- **`--label-col` defaults to `crop`**, which is what `AT_2018_TRAIN.geojson` uses. (`EC_hcat_n`
  belongs to a *different* workspace file, `austria_eurocrops_sampled_ethiopia_translated.geojson`.)

> **Choosing a different cell?** `tests/data/tutorial/survey_cells.py` ranks every cell over the ROI
> by crop variety, labelled area and top-2 share. `4772924` wins on **top-2 share (82 %)** — two
> cells have 8 crops rather than 7, but there the catch-all `other` becomes the *largest* class
> (spec 42 A3's table).
- **Sanity check that matters:** the cell must land at **15.39–15.47 E**. If you see ~16.0 E you have
  the *wrong cell* — that is `s2grid=476da24`, which contains **zero labels** (spec 42 §1).

> Why derive rather than hand-pick: `4772924` is reproducible only as
> `roi_to_s2_grids(AT_ROI, grid_size_km=5)`, and that call needs `AT_ROI`. Deriving it once here and
> committing the result means neither the VM nor a tutorial reader ever needs `shapefiles/`.

---

## Step 0a — laptop: commit Step 0's output so the VM can clone it

The VM runs Steps 2-4 against `roi.geojson` and `fields.geojson`, but it **cannot produce them** —
Step 0 needs `shapefiles/` from the workspace root, which is outside the repo. An AML compute
instance has **no `scp`**, so the practical transport is the repo itself. The two files total
**48 KB**, are already un-ignored by spec 42 D6's negation, and are part of the fixture anyway
(D3) — Step 7 would commit them regardless. Committing them here just moves that forward.

```bash
cd ~/NASA-Harvest/project/fetch_satdata_claude/fsd
git check-ignore tests/data/tutorial/roi.geojson tests/data/tutorial/fields.geojson
echo "exit=$?   # want exit=1 -- not ignored (do NOT add -v, see Step 7)"
du -ch tests/data/tutorial/*.geojson | tail -1
git add tests/data/tutorial/roi.geojson tests/data/tutorial/fields.geojson
git commit -m "spec 42: tutorial fixture ROI + labels (run-book 43 Step 0)"
git push origin main
```

- **PASS if:** `exit=1`, the total is **tens of KB** (not MB), and the push succeeds.
- **Why push matters:** Step 1c clones from GitHub. Anything not pushed does not exist on the VM —
  including the generator scripts themselves.
- **If you re-run Step 0** (different cell, different `--n-major`), re-commit and re-push before
  going back to the VM, or Step 2 silently uses the old cell.

---

## Step 1 — VM: get a shell and set it up (one-time, slow pace)

```bash
# AML compute instance: Azure Studio -> Notebooks -> Terminal. No ssh needed.

# 1a) Which identity is this shell? It must hold Storage Blob Data Contributor
#     on the rise storage account -- your laptop's identity is irrelevant here.
az account show --query user -o json
#     On a compute instance you are normally already signed in. If not: az login

# 1b) tmux FIRST. The browser terminal drops more easily than SSH would.
tmux new -s fixture

# 1c) Clone (HTTPS -- a fresh VM has no GitHub key, and fsd is public).
git clone https://github.com/nikhilsrajan/fsd.git
cd fsd
git log --oneline -1        # note the SHA; the fixture's provenance records it

# 1c-i) Confirm Step 0a's output actually came down with the clone.
#       If either is missing, you did not push -- go back to Step 0a.
ls -l tests/data/tutorial/roi.geojson tests/data/tutorial/fields.geojson

# 1d) venv + the extras this run actually needs.
python3.11 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,azure,grid]"
```

**Why exactly those three extras** — `azure` gives `adlfs` + `azure-identity` (reading `abfss://`
and the GDAL VSI token); `grid` gives `s2`/`s2cell` so the precondition check can re-derive the cell
if asked; `dev` gives `pytest`. **`mpc` is deliberately not needed** — nothing here calls the MPC
API, we only read COGs it already delivered. *(If an import fails at step 2, the missing extra is
the bug, not your environment — that class of defect voided a whole cluster run once.)*

```bash
# 1e) Point at the blob archive. Values come from AZURE_INFRA_PRIVATE.md.
export AZ_ARCHIVE_ROOT="abfss://<fs>@<account>.dfs.core.windows.net/<prefix>"

# 1f) Prove blob access BEFORE doing any work -- and prove the export actually took.
#     (An `export VAR="$(az ...)"` that silently stores an error string has cost a run before.)
echo "AZ_ARCHIVE_ROOT=[$AZ_ARCHIVE_ROOT]"
python -c "
import os
from fsd.storage import fs          # NOT 'from fsd import storage as fs' --
root = os.environ['AZ_ARCHIVE_ROOT'] # fsd.storage is a PACKAGE; the functions
                                     # live in fsd.storage.fs
assert root.startswith('abfss://'), f'not a blob url: {root!r}'
print('catalog exists:', fs.exists(root + '/archive/catalog.parquet'))
"
```

- **Expect:** `catalog exists: True`
- **PASS if:** True. **FAIL → stop here.** `AuthorizationFailure` usually means **network rules**
  (you are not inside the VNet), not RBAC. `False` means `AZ_ARCHIVE_ROOT` points at the wrong
  prefix — run-book 37 writes `<root>/archive/`, *not* the `mpc/` prefix from run-book 34.

---

## Step 2 — VM: verify the three A1 preconditions (read-only, no writes)

Amendment A1 lists three things that **cannot be checked from the laptop** and each of which would
waste the run if assumed. Check them before clipping a single pixel.

```bash
python tests/data/tutorial/build_fixture.py \
    --archive-root "$AZ_ARCHIVE_ROOT/archive" \
    --roi   tests/data/tutorial/roi.geojson \
    --bands B04 B08 SCL \
    --startdate 2018-04-01 --enddate 2018-09-30 \
    --check-only \
    --result tests/outputs/p6_tutorial_fixture/_result_step2.json
```

**Pass `--bands` here.** It is optional to the CLI, but without it the "all three bands present"
PASS condition below cannot be evaluated and `_result.json` records it as `unchecked` rather than
silently satisfied.

**`--startdate`/`--enddate` are required in practice.** Spec 42 §1/D2 specify **Apr–Sep 2018**, but
the blob archive holds the **full year**: the first real Step 2 run (2026-07-31) returned **72
granules, 2018-01-01 .. 2019-01-01** — ~3× the bytes, half of it winter. Without a window the
generator takes whatever the archive has, which is a different fixture than the spec describes.

- **Expect** something like:
  ```
  granules intersecting cell : 21   (of 72 before the 2018-04-01..2018-09-30 window)
  single MGRS tile           : True ['33UWP']
  bands present              : B02, B03, B04, B08, B8A, SCL
  radiometry declared        : 21/21 rows non-null   (column: 'offset')
  offset value(s)            : [0]  sources={'declared': 21}
  date span                  : 2018-04-.. .. 2018-09-..
  ```
- **PASS if:** all four of — a single MGRS tile, all three bands present, **every** row carries a
  non-null radiometry declaration, and the date span is non-empty and covers Apr–Sep 2018. All four
  are now gated in `_result.json`'s `pass` (they used to be printed but not gated).
- **Check `offset_sources` says `declared`, not `derived`** (spec 42 A2). `declared` means the value
  was **copied from the source catalog's own column** — A1's "copied, not invented" evidence. This is
  the only place that fact is observable: run-book Step 6 runs offline and cannot see the source at
  all. `derived` means the generator fell back to D1's id-token rule, which on the MPC path should
  never happen — if you see it, **stop and tell Claude.**
- **`offset value(s): [0]` is CORRECT here, not a bug.** Spec 42 D1 worried about the opposite
  (the *local* CDSE archive is all `_N0500_`, i.e. baseline ≥ 04.00, so it needs −1000). The blob
  MPC archive serves the **pre-Collection-1** products for 2018: the sample landed by run-book
  37-verify is `S2A_MSIL2A_20180106T100401_R122_T33UVP_`**`20201014`**`T034051` — generated
  **2020-10-14**, before baseline 04.00 arrived on **2022-01-25**, so `BOA_ADD_OFFSET` does not
  exist for it and 0 is the true declaration. Spec 32 D3 derives this per item from
  `s2:processing_baseline`, and hit the boundary empirically (`03.00 → 0`, `04.00 → −1000`). Both
  archives are internally correct — they are **different product versions of the same
  acquisitions**. What *would* be a bug is `0` on a granule whose baseline is ≥ 04.00, which
  `sources={'declared': N}` plus spec 32's per-item derivation rules out.
  *(Acceptance test 2 asserts `offset in (0, −1000)` precisely so both paths pass; the earlier
  hardcoded `== −1000` would have failed this run.)*
- **The granule count is NOT a pass criterion.** MPC applies different cloud-cover filtering and
  reprocessing dedup (spec 33), so it may not give 24 — and the first real run returned **72** over the full year, i.e. *more*, before the Apr–Sep window. **Whatever it gives is the fixture's timestamp
  count**, and `T` in step 6 follows from it — do not expect 9 mosaic intervals in advance.
- **FAIL on "radiometry declared" → stop and tell Claude.** That is the one assumption A1 rests on:
  the blob archive is supposed to be MPC-sourced and self-declaring, unlike the local CDSE archive
  which declares nothing. If it is unstamped, the fallback is spec 42 D1's local build with a
  re-derived offset — a different run, not a retry.
- **Note the column name in the output.** It is `offset` in one catalog and `boa_add_offset` in
  another; the generator must read it via the declaration API, never a hardcoded name (A1).

---

## Step 3 — VM: dry run (counts and bytes, zero side effects)

```bash
python tests/data/tutorial/build_fixture.py \
    --archive-root "$AZ_ARCHIVE_ROOT/archive" \
    --roi    tests/data/tutorial/roi.geojson \
    --fields tests/data/tutorial/fields.geojson \
    --out    tests/data/tutorial \
    --bands  B04 B08 SCL \
    --startdate 2018-04-01 --enddate 2018-09-30 \
    --max-bytes 31457280 \
    --dry-run \
    --result tests/outputs/p6_tutorial_fixture/_result_step3.json
```

**This CLI is normative** — the implementer of `build_fixture.py` must match these flags
(spec 42 D4). `--max-bytes` is the **30 MB hard stop** from spec 42 D2.

- **Expect:** per-band estimated output sizes and a projected total, e.g.
  `projected total: 18.4 MB (24 granules x 3 bands)  -- under the 30.0 MB cap`
- **PASS if:** projected total **< 30 MB** and the granule/band counts match step 2.
- **If projected > 30 MB:** do **not** raise the cap. Spec 42 D2's documented fallback is **drop to
  12 timestamps before dropping bands** (`--max-timestamps 12`). Report the number to Claude first.
  The kept timestamps are spread **evenly across the date span** (endpoints included), not the first
  12 — taking the first 12 of 24 would leave Apr–Jun only and destroy the seasonal series D2 calls
  the point of the fixture.

---

## Step 4 — VM: build it

```bash
python tests/data/tutorial/build_fixture.py \
    --archive-root "$AZ_ARCHIVE_ROOT/archive" \
    --roi    tests/data/tutorial/roi.geojson \
    --fields tests/data/tutorial/fields.geojson \
    --out    tests/data/tutorial \
    --bands  B04 B08 SCL \
    --startdate 2018-04-01 --enddate 2018-09-30 \
    --max-bytes 31457280 \
    --result tests/outputs/p6_tutorial_fixture/_result_step4.json
```

- **Expect:** a live progress line per granule with ETA, then a summary: granules written, per-band
  bytes, total bytes, the derived radiometry value, and the source granule ids recorded in
  `tests/data/tutorial/README.md`.
- **PASS if:** `status: ok`, every granule × band written, total under the cap,
  **`all_offsets_declared: true`** (spec 42 A2 — the "copied from the source, not invented" gate;
  `offset_sources` must read `{"declared": N}` with no `derived`), and `tests/data/tutorial/` now
  contains `catalog.parquet`, `NOTICE`, `README.md` and the COGs.
- **`README.md` must not contain the archive url.** The generator redacts `--archive-root`'s value
  from the recorded invocation because this file is committed to a **public MIT repo**. Confirm:
  `grep -c 'abfss://' tests/data/tutorial/README.md` → **0**. If it is not 0, stop — do not commit.
- **`NOTICE` must read exactly** `Contains modified Copernicus Sentinel data 2018` — the
  **modified** form, because clipping *is* modification under the EC legal notice (spec 42 D5). If
  it says the plain `Copernicus Sentinel data 2018`, that is a defect, not a nitpick.
- **If it fails partway:** re-run the same command; it skips completed files. Nothing is deleted.

---

## Step 5 — VM → laptop: land it home (~20 MB, hotspot-safe)

The fixture is the only thing that crosses the WAN. A compute instance has no `scp`, so it goes
via blob — **as a single tar object**, because `fs.put`/`fs.get` are deliberately **file-only**
(`put_file`/`put_file`; they take no `recursive`, and a directory argument fails). One object is
also the more reliable transfer.

```bash
# On the VM: tar the fixture, then stage the ONE object to your own scratch prefix.
tar czf /tmp/tutorial_fixture.tgz -C . tests/data/tutorial
ls -lh /tmp/tutorial_fixture.tgz          # sanity: tens of MB, not hundreds

python -c "
import os
from fsd.storage import fs
dst = os.environ['AZ_ARCHIVE_ROOT'] + '/scratch/tutorial_fixture.tgz'
fs.put('/tmp/tutorial_fixture.tgz', dst)
print('staged ->', dst)
"
```

```bash
# On the LAPTOP (VPN on):
cd ~/NASA-Harvest/project/fetch_satdata_claude/fsd && source .venv/bin/activate
python -c "
import os
from fsd.storage import fs
src = os.environ['AZ_ARCHIVE_ROOT'] + '/scratch/tutorial_fixture.tgz'
fs.get(src, '/tmp/tutorial_fixture.tgz')
print('landed')
"
tar xzf /tmp/tutorial_fixture.tgz         # restores tests/data/tutorial/ in place
du -sh tests/data/tutorial
```

- **Expect:** `du` shows **≤ 30 MB**.
- **PASS if:** the size matches step 4's reported total (±1 MB for filesystem overhead).
- **The untar overwrites `roi.geojson`/`fields.geojson`** with the copies the VM used — the same
  bytes Step 0a committed, so `git status` should show no change to them. If it does, the VM built
  against a different ROI than you committed.

---

## Step 6 — laptop: prove it works offline (the real acceptance test)

**Disconnect from VPN and from wifi for this step.** The whole point of the fixture is that it needs
neither.

```bash
python -m pytest tests/test_tutorial_fixture.py -s
```

**Use `-s`, and expect ~3-4 minutes.** Criterion 3 builds **one datacube per label polygon** — 43
fields x 36 granules x 3 bands, serially — and `create_datacube.setup` prints a live
`[setup] N/43 shapes … ETA` line throughout. **pytest captures stdout by default**, so without
`-s` you get a bare `..` and a long silence that reads exactly like a hang. Measured 2026-07-31 on
a laptop: **3 min 18 s**, all 3 passing.

- **Expect:** the three automated criteria of spec 42 §4 pass —
  **(1) structural** (every granule × band opens as a valid COG; one catalog row per granule with
  non-empty geometry); **(2) radiometric** (every row's declaration round-trips, is one of the two
  physically meaningful values `0`/`-1000`, and is uniform across the fixture); **(3) pipeline**
  (`create_training_data` → 43 ids, 3 classes; train; `run_inference` → one `output.tif` + STAC
  item; cube values in a plausible post-offset reflectance range).
- **"Equals the source catalog's value" is NOT checked here** — it cannot be, with the network off
  (spec 42 A2). That gate is Step 2/Step 4's `offset_sources: {"declared": N}`. Criterion 3's
  reflectance range is the offline check that would still catch a ~1000 DN error however the offset
  arrived.
- **PASS if:** all pass **with no network**. A test that needs the network has smuggled in a
  dependency the tutorial cannot rely on.
- **Criterion 3's `T` comes from step 2's actual granule count** — do not assert 9 if the archive
  gave a different number of dates.

---

## Step 7 — laptop: commit it

```bash
# .gitignore blanket-ignores *.tif/*.geojson/*.parquet -- spec 42 D6 pokes ONE narrow hole.
# NOTE: use check-ignore WITHOUT -v. With -v, git also prints paths that merely
# match a NEGATION pattern, so a correctly-working negation prints
# ".gitignore:37:!tests/data/tutorial/** ..." and exits 0 -- which reads as a
# failure but is the pass. Without -v: no output and exit 1 == not ignored.
git check-ignore tests/data/tutorial/catalog.parquet; echo "exit=$?   # want exit=1"
# roi.geojson + fields.geojson are already committed (Step 0a); this adds the COGs,
# catalog.parquet, NOTICE and README.md.
git add .gitignore tests/data/tutorial tests/test_tutorial_fixture.py
git status --porcelain
```

- **PASS if:** `git check-ignore` prints **nothing and exits 1** (the negation works) and
  `git status` shows the fixture files as added — **and nothing else**. If `tests/outputs/**` or a
  `.npy` appears, stop: the negation is too broad.
- Then commit. **Do not push without asking** (working contract).

---

## Success criteria (`_result.json`)

Each step writes `tests/outputs/p6_tutorial_fixture/_result_step<N>.json`:

```json
{ "step": "step4_build", "status": "ok", "pass": true,
  "metrics": { "granules": 24, "bands": ["B04","B08","SCL"], "total_bytes": 19300000,
               "offsets": [-1000], "declaration_column": "offset",
               "offset_sources": { "declared": 24 }, "all_offsets_declared": true,
               "mgrs_tiles": ["T33UWP"], "date_span": ["2018-04-06","2018-09-28"] },
  "expected": { "under_cap": true },
  "error": null }
```

`offset_sources` / `all_offsets_declared` are spec 42 **A2**'s gate: they are the only evidence that
the radiometry was **copied from the source** rather than invented by the generator, and they exist
only here because Step 6's suite runs with the network off.

The run passes when every step's `pass` is true. **Paste these files back, not the logs.**

## Stop / observe

- **Progress:** step 4 prints a per-granule line with ETA.
- **Dry run:** step 3 (`--dry-run`) gives counts, bytes and the cap check with **zero** writes.
- **Abort:** `Ctrl-C` is safe at every step — the generator is per-file idempotent and deletes
  nothing. Re-run the same command to resume.
- **If the browser terminal drops:** `tmux attach -t fixture`.

## What to send back

1. `_result_step0.json` … `_result_step4.json`, plus step 6's pytest summary line.
2. The **granule count** from step 2 and the **declaration column name** — both feed the tutorial's
   text and neither is knowable from here.
3. The `git log --oneline -1` SHA from step 1c, for the fixture's provenance record.

## Notes for whoever reads this later

- **The single clipped tile means the tutorial never exercises multi-MGRS-tile merge.** Deliberate
  (spec 42 §5); that path stays covered by `AT_ROI` and the synthetic suite, and
  `docs/howto/your-own-region.md` must say so.
- **"VM ≡ local" is a claim, not a measurement** (A1). If you ever build the fixture both ways and
  the bytes differ, that is a **storage-seam finding** worth an issue in its own right — not a
  fixture bug to smooth over. Spec 42 D1's local path is retained precisely so the comparison stays
  possible.
