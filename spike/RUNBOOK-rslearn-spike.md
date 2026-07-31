---
status: current
summary: Run the rslearn build-vs-borrow spike on the VM -- install weight, the calendar-T contract (offline, decisive), then the Azure and equivalence probes that Step 2 gates.
---

# Run-book: rslearn spike (Plan C evaluation)

> **Deliberately unnumbered and inside `spike/`.** Run-book numbers are a `main` sequence and
> `44` is already taken (`runbooks/44-todo-to-issues.md`). This branch may never merge, so it
> does not claim a number from that sequence. If the Plan-C decision goes to C, this gets a
> number on the way in. Same reasoning for not writing a `specs/44-*.md`: see `README.md`
> ("Does this need a spec?").
>
> Spec 24 rules apply: Claude does not run any of this. You run it, paste back each step's
> `_result.json`, Claude diffs it against the success criteria below and never reads live logs.

## Purpose

Answer the three charter questions with measurements instead of argument, cheapest-and-most-
decisive first. The static half is already done and written up in
[`RSLEARN_READ_2026-07-31.md`](RSLEARN_READ_2026-07-31.md) — **read section 6 before starting**;
it lists exactly what is still unknown and predicts what each probe should return.

## Where this runs, and why

**On the VM, not the laptop** (your call, 2026-07-31 — hotspot data). Note what that buys:

| step | network | satellite bytes |
|---|---|---|
| 1 — install | ~2–3 GB of wheels, once | none |
| 2 — T contract | **none** | **none** |
| 3 — Azure write | blob only | tiny |
| 4 — equivalence | CDSE/MPC | one small cell |

**Step 2 is the decision gate and it is free after Step 1.** It can invalidate the shape of
Steps 3–4, which is why those two are not written yet.

## Prerequisites

- On the VM, this branch: `git switch spike/rslearn && git pull`.
- `python3.11+` (rslearn requires `>=3.11`).
- The tutorial fixture present at `tests/data/tutorial/` (it is committed — Step 0 checks).
- Steps 3–4 only: `az login`, and `source env.local.sh` for the `AZ_*` variables
  (see `env.example.sh`). **Never paste concrete account names or URLs into a result file** —
  this branch is part of a public MIT repo.
- **Never install rslearn into `.venv`.** The isolated env is `.venv-rslearn` (gitignored). Main
  must stay lean, and install weight is itself a measurement.

---

## Steps

### Step 0 — confirm the branch and the ground truth

```bash
cd fsd
git rev-parse --abbrev-ref HEAD          # expect: spike/rslearn
ls tests/data/tutorial/catalog.parquet   # expect: the file exists
python3 -c "import pathlib,json; p=pathlib.Path('tests/data/tutorial'); print(json.dumps({'granule_dirs': len([d for d in p.iterdir() if d.is_dir()]), 'mb': round(sum(f.stat().st_size for f in p.rglob('*'))/1e6,1)}))"
```

- **Expect:** branch `spike/rslearn`; `catalog.parquet` exists; roughly `36` granule dirs, ~`27` MB.
- **PASS if:** all three hold. No `_result.json` — just paste the output.
- **If the fixture is missing:** stop. It is the comparison corpus for Step 4 and it replaces the
  deleted `satellite_benchmark/`. It should have come with the merge.

### Step 1 — install rslearn into an isolated venv, and weigh it

```bash
cd fsd
python3.11 -m venv .venv-rslearn
source .venv-rslearn/bin/activate
python -c "import sys; assert 'venv-rslearn' in sys.prefix, sys.prefix; print('isolated OK', sys.prefix)"

# Time it and keep the log -- both numbers feed the probe.
time pip install --report /tmp/rslearn_install.json 'rslearn==0.1.13' 2>&1 | tee /tmp/rslearn_install.log
```

Then read the two numbers off it and run the probe:

```bash
# MB actually downloaded, from pip's own machine-readable report
python - <<'PY'
import json
r = json.load(open('/tmp/rslearn_install.json'))
mb = sum(i.get('download_info', {}).get('archive_info', {}).get('size', 0) or 0 for i in r.get('install', []))/1e6
print(f"download_mb ~= {mb:.0f}   packages = {len(r.get('install', []))}")
PY

python spike/probes/probe_01_install_weight.py \
    --out tests/outputs/rslearn_spike \
    --install-seconds <the `real` seconds from `time`> \
    --download-mb <the number printed above>
```

- **Expect:** the install succeeds and pulls torch, torchvision, torchmetrics and lightning as
  **core** dependencies (`pyproject.toml:11-31`) — a multi-GB venv is the *expected* result here,
  not a problem with your machine.
- **PASS if:** `_result_probe01.json` has `"status": "ok"`. The interesting field is
  `metrics.torch_free_acquisition_path` — predicted **`true`**.
- **If `torch_free_acquisition_path` is `false`:** that contradicts
  `RSLEARN_READ_2026-07-31.md` §4.3. Not a failure — paste it, it changes the write-up.
- **If pip backtracks for a long time:** known upstream hazard; their own comment at
  `pyproject.toml:44-47` describes botocore pinning causing exactly this. Add `--only-binary=:all:`
  or install with `uv pip install` and note which you used.

### Step 2 — the calendar-`T` contract (offline, decisive) 🚩 DECISION GATE

```bash
cd fsd && source .venv-rslearn/bin/activate
python spike/probes/probe_02_t_contract.py --out tests/outputs/rslearn_spike
```

**Zero network, zero satellite data.** Four synthetic cases isolate three predicted divergences
between rslearn's `period_duration` and fsd's `T = ceil(span / mosaic_days)`.

- **Expect** (predicted from `rslearn/data_sources/utils.py:434-485`):

  | case | fsd `T` | rslearn groups, predicted |
  |---|---|---|
  | `dense_tutorial_window` | 10 | **9** (trailing partial period dropped) |
  | `exact_multiple_no_partial` | 9 | 9 |
  | `two_empty_periods` | 9 | **7** (empty periods dropped) |
  | `default_reverse_time_order` | 9 | 9, but reverse-chronological + a `FutureWarning` |

- **PASS if:** `_result_probe02.json` has `"status": "ok"` and all four cases returned an integer
  group count. **A pass does not mean rslearn matched fsd** — read `metrics.findings`.
- **The result that matters:** `metrics.findings.T_matches_fsd_on_dense_window`.
  - **`false`** (predicted) → rslearn's `T` is data-dependent. Plan C then **requires a
    re-alignment shim in fsd** (map groups back onto their period index, fill gaps) before
    preflight or cross-cell flatten can work at all — i.e. adoption *adds* fsd code rather than
    deleting it. Steps 3–4 stay worth running, but the bar for Plan C has risen.
  - **`true`** → `RSLEARN_READ_2026-07-31.md` §4.2 is **wrong**. Stop and paste the result;
    the read gets re-derived before anything else runs.
- **If it errors on import or signature:** rslearn's API moved between 0.1.13 and whatever
  installed. Paste the traceback; the probe is pinned to the version in Step 1 for this reason.

### Step 3 — can rslearn write to Azure blob under managed identity? *(not yet written)*

**Gated on Step 2.** This is the highest-risk question in the spike
(`RSLEARN_READ_2026-07-31.md` §3: **zero** azure/adlfs/abfs references in 54,850 LOC, and
`fsspec[gcs, s3]` declares no azure backend), but its *shape* depends on whether a shim is
needed, so the probe is written after Step 2 comes back.

What it will have to establish, recorded now so the design is not re-derived:

1. Does `UPath("abfss://…")` resolve at all in the spike venv, and does it need `adlfs` added by
   hand (upstream does not declare it)?
2. Can `rslearn.tile_stores.default` **write** a tile there under `DefaultAzureCredential`?
3. Does rasterio/GDAL *inside* rslearn read that path under MSI — or does it hit the same wall
   fsd solved separately in spec 31 with `/vsiadls/` + a fresh token? fsd's answer is not
   portable into rslearn without patching it, and patching a read-only reference is not allowed.

### Step 4 — pixel equivalence against the tutorial fixture *(not yet written)*

**Gated on Steps 2 and 3.** Acquire the same cell/window/bands rslearn-side and diff against the
committed fixture: grid cell `4772924`, T33UWP, 2018-04-01 → 2018-09-28, B04/B08/SCL,
`mosaic_days=20`. fsd's published numbers over exactly this corpus are the comparison baseline.

Two things to watch, both from the read:

- rslearn's harmonization is **opt-in** (`harmonize: bool = False`, `copernicus.py:680`) and
  **hard-asserts `offset == -1000`** (`copernicus.py:73`). This fixture's products correctly
  declare `0`, so **rslearn is predicted to `AssertionError`** if harmonization is switched on
  against this archive. That is a genuine finding about rslearn, worth capturing precisely.
- Any `T` mismatch from Step 2 must be reconciled *before* a pixel diff means anything —
  comparing a 9-deep stack to a 10-deep one is not a comparison.

---

## Success criteria (`_result.json`)

Steps 1 and 2 each write `tests/outputs/rslearn_spike/_result_probe0N.json`:

```json
{ "step": "probe_0N_...", "status": "ok|fail", "pass": true,
  "metrics": { }, "expected": { }, "error": null }
```

**Paste those two files back, not the logs.** `tests/outputs/` is gitignored, so nothing here is
committed by accident.

The spike does **not** pass or fail as a whole — it is a measurement exercise. It is *complete*
when the charter's three questions have numbers against them and
`spike/RSLEARN_SPIKE_REPORT.md` carries a go/no-go on Plan C.

## Stop / observe

- Steps 0 and 2 are seconds. Step 1 is minutes and is the only large download.
- Nothing here is destructive; nothing writes outside `.venv-rslearn/` and
  `tests/outputs/rslearn_spike/`, both gitignored.
- Abort: Ctrl-C. To start over: `rm -rf .venv-rslearn` and redo Step 1.
