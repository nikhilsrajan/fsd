# spike/rslearn — build-vs-borrow evaluation (Plan C)

> **This branch (`spike/rslearn`) only.** `main` continues **Plan B** (fsd's own pipeline). This
> branch evaluates **Plan C** (selective leverage of AllenAI's `rslearn` as a library underneath
> fsd's Azure runner + flatten/ModelAdapter). Motivation & options: `../RSLEARN_COMPARISON.md`.
> Do **not** do main-line spec work here; keep this branch focused so the final keep/merge
> decision is clean.

## Status — 2026-07-31

| | |
|---|---|
| Branch | refreshed from `main` (merge `d542aeb`) — the spike is measured against fsd **as it is today**, not as it was on 2026-07-06 |
| rslearn under evaluation | **v0.1.13** @ `a5c50c63` (2026-07-28), read-only at the workspace root |
| Static analysis | ✅ done — [`RSLEARN_READ_2026-07-31.md`](RSLEARN_READ_2026-07-31.md) |
| Probes written | ✅ 01 (install weight) + 02 (the `T` contract) — `probes/` |
| Probes run | ⬜ none yet — [`RUNBOOK-rslearn-spike.md`](RUNBOOK-rslearn-spike.md), on the VM |
| Report | 🟡 **drafted, measurements pending** — [`RSLEARN_SPIKE_REPORT.md`](RSLEARN_SPIKE_REPORT.md). §2 (teaching rslearn), §3 (rslearn's advantages) and §4 (fsd's) are complete and cited; §1, §5, §6 carry ⬜ markers gated on probes 01/02 |
| Verdict | ⬜ not called — §6.4 states in advance what would flip it |

**Offline census, not a run-book probe:** `probes/census_data_sources.py` re-derives the breadth
number the report's §3.1 rests on (36 modules → 47 `DataSource` subclasses → 40 concrete names →
**50 concrete (module, class) entry points**, vs fsd's 2). Pure `ast`, no imports, no install —
re-run it whenever rslearn is bumped:
`python spike/probes/census_data_sources.py --rslearn-root ../rslearn`

**Read [`RSLEARN_READ_2026-07-31.md`](RSLEARN_READ_2026-07-31.md) first.** Three of the charter's
original assumptions did not survive it, and one of the three questions below is now answered
without running anything.

## Does this need a spec? A roadmap? — no. Deliberately.

Asked and answered 2026-07-31:

- **No `specs/44-*.md`.** Main-line spec numbers belong to `main`; this branch merges only at a
  "switch to Plan C" decision, so a spec here would either sit orphaned forever (if we stay B) or
  collide with whatever `main` numbered 44 meanwhile. The charter + the read + the run-book
  already carry the design load a spec would.
- **No run-book number either** — `runbooks/44` is taken on `main`. The run-book lives here as
  `RUNBOOK-rslearn-spike.md` and takes a number only on the way in.
- **No roadmap.** A spike whose whole point is to be cheap and possibly thrown away should not
  acquire a phase plan. `../ROADMAP.md` records the *outcome*, not the process.

If the spike goes to Plan C, all three reverse and the work gets normal spec treatment.

## Branch discipline
- **Isolated env:** all rslearn work uses a **separate venv `fsd/.venv-rslearn`** (gitignored via
  the `.venv-*/` rule). Never `pip install rslearn` into `fsd/.venv` — main must stay lean
  (numpy/rasterio/fsspec), and install weight is itself a benchmark metric (Q3).
- **Merge direction:** sync **main → this branch** periodically (stay fresh). Only merge **this
  branch → main** if/when we decide to switch to Plan C.
- **Outputs:** probe artifacts under `fsd/tests/outputs/rslearn_spike/` (gitignored); committed
  deliverables = this charter, the read, the probes, the run-book, and the final report. Log
  reusable commands in `../RECIPES.md`.
- **`rslearn/` is read-only reference.** Read it; never edit it. If the spike concludes rslearn
  needs patching to work for us, that *is* a finding against Plan C, not a task.

## The questions — and what is already known

From `../RSLEARN_COMPARISON.md` §7, re-scored after the 2026-07-31 read:

1. **Acquisition into Azure blob.** Can rslearn's Sentinel-2 sources materialize into `rise` blob
   (UPath/fsspec + MSI) and produce bands equivalent to fsd's download?
   → **Wide open, and the riskiest.** rslearn has **zero** Azure references in 54,850 LOC and
   declares `fsspec[gcs, s3]` only. Needs the VM. Run-book Steps 3–4.

2. **A numpy datacube without Lightning.**
   → **Reframed.** At *install* time this is impossible — torch and lightning are **core**
   dependencies, not extras. At *import* time it looks achievable (probe 01 checks). The real
   obstacle turned out to be elsewhere: rslearn's `period_duration` is a close analogue of fsd's
   calendar mosaic, but it **drops empty periods, floors the span, and anchors from the end**, so
   `T` is data-dependent where fsd's is a pure function of the window. Probe 02, offline, decides
   it. **This is the gate.**

3. **Install weight for a Mode-A laptop user.**
   → **Answered in principle: heavy, with no lite path.** `pip install rslearn` pulls the whole
   deep-learning stack plus `flask` and `boto3`. Only the actual numbers are outstanding (probe 01).
   This directly contradicts fsd's Mode-A promise, so it is a live argument against C.

## Benchmark corpus — ⚠️ changed

The original charter named `satellite_benchmark/`. **That archive no longer exists** (deleted for
disk pressure). The replacement is **`tests/data/tutorial/`** — committed, 27 MB, 36 granules ×
B04/B08/SCL, grid cell `4772924`, MGRS tile T33UWP, 2018-04-01 → 2018-09-28, with
`catalog.parquet` and 43 labelled fields.

It is a *better* corpus for this: small, offline-reproducible, single-tile (no multi-CRS
confound), radiometrically correct (declared `offset = 0`, verified), and fsd's own reviewed
numbers over it are already published — so equivalence has a checked baseline on day one.

## What to compare (unchanged in intent)

- **`T` contract compatibility** — probe 02. New, and now first: nothing else is meaningful until
  the two systems agree on how many timesteps a window has.
- **Output equivalence** — does rslearn's mosaic match fsd's `datacube.npy` on the same
  bands/dates/window? (pixel diff, *after* any `T` mismatch is reconciled)
- **Dependency weight** — venv size, install time, import time.
- **Blob/MSI compatibility** — including whether GDAL/VSI auth works inside rslearn, which fsd
  solved separately in spec 31.
- **Harmonization correctness** — note the read's finding: rslearn's is **opt-in** and
  **hard-asserts `-1000`**, so it is predicted to crash on this fixture's correct `0`.
- **Build time** — wall + per-stage, against fsd's published numbers.
- **Code complexity** — config/LOC to get from geometries → numpy datacube.

## Verdict

On completion, write `spike/RSLEARN_SPIKE_REPORT.md` with the numbers and a go/no-go on Plan C.
Then either merge → `main` (switch to C) or delete the branch (stay B). Record the call in
`../ROADMAP.md`, in issue #12, and in memory.

**Sharpen the question the report has to answer** (from the read, §8): the live decision is no
longer "should fsd be *built on* rslearn" — the Azure gap and the install weight make that
expensive — but **"should fsd's `Source` seam gain an optional rslearn-backed source, behind an
extra, for breadth?"** That is smaller, cheaper and reversible, and it is what issues
#11/#21/#31/#32/#33/#36 are really asking for.
