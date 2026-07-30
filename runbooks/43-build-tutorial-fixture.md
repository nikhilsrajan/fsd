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
| 0 | **laptop** | needs `shapefiles/` (`AT_ROI`, `AT_2018_TRAIN`), which live at the **workspace root, outside the repo** — a `git clone` on a VM cannot supply them. Tiny, offline, no bulk data. |
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

- **Expect:** `cell 4772924  bounds 15.3900,48.4821,15.4717,48.5320  fields 43  classes maize=20 hemp=13 other=10`
- **PASS if:** `fields == 43`, three classes present, and both `tests/data/tutorial/roi.geojson` and
  `fields.geojson` exist. The collapse is **maize / hemp / other** (spec 42 D3) — the raw 7 classes
  over 43 samples are not trainable.
- **Sanity check that matters:** the cell must land at **15.39–15.47 E**. If you see ~16.0 E you have
  the *wrong cell* — that is `s2grid=476da24`, which contains **zero labels** (spec 42 §1).

> Why derive rather than hand-pick: `4772924` is reproducible only as
> `roi_to_s2_grids(AT_ROI, grid_size_km=5)`, and that call needs `AT_ROI`. Deriving it once here and
> committing the result means neither the VM nor a tutorial reader ever needs `shapefiles/`.

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
from fsd import storage as fs
root = os.environ['AZ_ARCHIVE_ROOT']
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
    --check-only \
    --result tests/outputs/p6_tutorial_fixture/_result_step2.json
```

**Pass `--bands` here.** It is optional to the CLI, but without it the "all three bands present"
PASS condition below cannot be evaluated and `_result.json` records it as `unchecked` rather than
silently satisfied.

- **Expect** something like:
  ```
  granules intersecting cell : 24        (local CDSE archive gave 24; MPC may differ -- see below)
  single MGRS tile           : T33UWP    (24/24)
  bands present              : B04, B08, SCL
  radiometry declared        : 24/24 rows non-null   (column: 'offset')
  offset value(s)            : [-1000]  sources={'declared': 24}
  date span                  : 2018-04-06 .. 2018-09-28
  ```
- **PASS if:** all four of — a single MGRS tile, all three bands present, **every** row carries a
  non-null radiometry declaration, and the date span is non-empty and covers Apr–Sep 2018. All four
  are now gated in `_result.json`'s `pass` (they used to be printed but not gated).
- **Check `offset_sources` says `declared`, not `derived`** (spec 42 A2). `declared` means the value
  was **copied from the source catalog's own column** — A1's "copied, not invented" evidence. This is
  the only place that fact is observable: run-book Step 6 runs offline and cannot see the source at
  all. `derived` means the generator fell back to D1's id-token rule, which on the MPC path should
  never happen — if you see it, **stop and tell Claude.**
- **The granule count is NOT a pass criterion.** MPC applies different cloud-cover filtering and
  reprocessing dedup (spec 33), so it may not give 24. **Whatever it gives is the fixture's timestamp
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

The fixture is the only thing that crosses the WAN. Easiest path off a compute instance, which has
no `scp`:

```bash
# On the VM: stage the fixture to blob under your own scratch prefix.
python -c "
import os
from fsd import storage as fs
fs.put('tests/data/tutorial', os.environ['AZ_ARCHIVE_ROOT'] + '/scratch/tutorial_fixture', recursive=True)
print('staged')
"
```

```bash
# On the LAPTOP (VPN on):
cd ~/NASA-Harvest/project/fetch_satdata_claude/fsd && source .venv/bin/activate
python -c "
import os
from fsd import storage as fs
fs.get(os.environ['AZ_ARCHIVE_ROOT'] + '/scratch/tutorial_fixture', 'tests/data/tutorial', recursive=True)
print('landed')
"
du -sh tests/data/tutorial
```

- **Expect:** `du` shows **≤ 30 MB**.
- **PASS if:** the size matches step 4's reported total (±1 MB for filesystem overhead).

> Alternative if `fs.put/get` are not both available for directories: zip on the VM
> (`tar czf tutorial.tgz tests/data/tutorial`), stage the single archive, land it, untar. One object
> is also the more reliable transfer.

---

## Step 6 — laptop: prove it works offline (the real acceptance test)

**Disconnect from VPN and from wifi for this step.** The whole point of the fixture is that it needs
neither.

```bash
python -m pytest tests/test_tutorial_fixture.py -q
```

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
