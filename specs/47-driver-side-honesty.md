---
status: current
summary: Make the driver act on and report what it already knows — refuse a work list that no longer matches the request (#66), show progress on the four silent AML legs (#65), and diff the catalog before dispatching a download (#64).
---

# Spec 47 — driver-side honesty: stale work lists, silent dispatch, no-op downloads

**Status: 📝 DRAFT — awaiting sign-off.** Written against issues **#66**, **#65** and **#64**, all
three raised by the user from the same full AML e2e run (2026-08-18) driven from
`notebooks/e2e_austria_aml.ipynb`. Four §7 questions are open; each carries a default resolved by
Claude, to confirm or overturn at sign-off. Nothing in `src/` is touched yet.

> **The one sentence:** in all three defects the driver **already has** the information that would
> have saved the user — the freshly tiled cell ids, the job statuses, the discovered asset list —
> and it neither acts on it nor says it out loud.

---

## 1. Three defects, measured

| # | defect | measured cost |
|---|---|---|
| **#66** | a changed ROI is silently ignored when `output_folderpath` is reused | **a wrong answer**: the second run re-inferred the *first* ROI's 9 cells |
| **#65** | AML dispatch/poll/merge print nothing | **30m10s** of near-total silence; the operator checked Studio and asked if it had hung |
| **#64** | a no-op download still dispatches the fan-out | **5m31s** of cold start to discover there was nothing to do |

They look like three unrelated papercuts. They are one shape: a driver-side fact that exists in
memory at the moment it would be useful, and is dropped on the floor.

### #66 — the resume key is existence, not identity

`api._run_inference_roi` step 2 (`src/fsd/api.py:1233-1249`):

```python
run_folderpath = os.path.join(output_folderpath, "cells")
csv_filepath   = os.path.join(run_folderpath, "input.csv")
if not fs.exists(csv_filepath):        # resume-by-existence
    _create_datacube.setup(...)
```

The new ROI *is* read, tiled, and written to `grids.geojson` (overwritten unconditionally, one
line above) — and the fan-out then reads `input.csv`, so the stale work list wins. The resume
itself is correct and wanted: a 299-cell run that dies at cell 280 must not restart from zero.
What is missing is any check that the cached work list still **corresponds to the request**.

Deleting the stale folder is not a workaround: `fs.rm(recursive=True)` is unreliable on `abfss://`
(#50).

### #65 — one `print()` in 1169 lines

`src/fsd/workflows/runners.py` contains exactly **one** `print()`, and it is the Snakemake
interrupt handler (`runners.py:56`). Measured this session by direct count. Four legs are silent:

| leg | driver-side? | visible in AML Studio? | output today |
|---|---|---|---|
| `_stage_bundle` upload | yes | no (not submitted yet) | none — **627 s for 13 MB over VPN** |
| `_aml_submit_and_wait` poll loop | yes | yes | **none** |
| collect + STAC (`_existing_outputs`) | yes | no (all terminal) | none |
| `_merge_outputs` | yes | no | **none — ~1000 s on 300 cells** |

The merge is the worst case: entirely local, reading every per-cell COG over the WAN through
`/vsiadls/`.

**The bar already exists in this repo.** `create_datacube.setup`'s `_tick`
(`workflows/create_datacube.py:120-133`) prints:

```
[setup] 34/300 shapes (11%) | 7.9 shapes/s | elapsed 4s | eta 33s
```

Rate + elapsed + ETA, throttled to one line per 2 s. The four legs above should match it. `_tick`
is currently a **closure inside `setup`**, so it cannot be reused as written.

### #64 — the driver already holds the asset list

For `source="mpc"` — the source the notebook uses — discovery **already runs on the driver**
before submission (`runners.py:1092`):

```python
rows = _mpc.discover_shard_rows(roi, startdate, enddate, bands, dst_folderpath, ...)
n_assets = len(rows)
...
shards = shard_units(rows, n_shards)
```

Each row carries `tile_id` (the STAC item id), `band`, and `dst`
(`src/fsd/sources/mpc.py:440-456`). The catalog carries `id`, `files`, `local_folderpath`
(`fsd.catalog.catalog.COLUMNS`). So the diff "what does this request need that the catalog does
not already have" is computable **on the driver, from data already in memory**, before a single
node warms up. Today nothing computes it: every discovered asset is sharded and dispatched, and
the per-granule skip logic runs on the node.

`source="cdse"` is structurally different: it submits **exactly one whole-ROI job** and discovery
happens *on the node*. The same fix there needs a new driver-side discovery pass — see D8.

## 2. Scope

**In:** a work-list-identity check in `api._run_inference_roi` (#66); a shared progress helper plus
its four call sites in `workflows/runners.py` (#65); a driver-side catalog diff in
`runners.run_aml_download`'s **MPC** branch (#64).

**Out:** the CDSE download path (D8); changing the resume mechanism itself (`input.csv` stays the
work list); `fs.rm` on blob (#50); the per-shard cold-start overhead itself (#48); any change to
what a download *fetches* once dispatched.

## 3. Decisions

### Part A — #66, the stale work list

#### D1 — a cached `input.csv` whose cell-id set differs from the freshly tiled grids is a hard error

When `input.csv` exists, read its `id` column and compare it as a **set** against the `id` column
of the grids just written to `grids.geojson`. On any difference, raise `PreflightError` naming
`output_folderpath`, the two counts, a bounded sample of the symmetric difference, and the fix
(use a new `output_folderpath` — it is the identity of the run).

Raise rather than silently re-tiling, because the alternative repairs are both worse: rewriting
`input.csv` in place would orphan every already-written cell under the old id set, and deleting
the folder is not reliably possible on blob (#50). A hard error turns a silent wrong answer into
one actionable line, which is what the issue asks for.

**This is strictly weaker than what a mature workflow engine does, deliberately.** Snakemake's
*default* rerun triggers include the non-file params, the input set, and the rule code — it
detects a changed request and **re-runs**. fsd cannot re-run safely (see above), so it detects and
**refuses**. Detect-and-refuse is the honest subset.

#### D2 — the compared key is the cell-id set, not a parameter hash

Only the id set is compared. Not `startdate`/`enddate`/`bands`/`mosaic_days` — those already have
a home in the run-folder name since spec 46 D1/D2 (`20180401_20180930_m20`), so a changed window
or `mosaic_days` writes a *different* folder and cannot collide. The id set is exactly the
dimension spec 46 left unguarded, and exactly the one the ROI controls.

**Known consequence, stated rather than discovered:** spec 46 D4 changed cell counts for every ROI
(AT_ROI 300 → 299, `s2grid=476da24` 9 → 1, measured 2026-08-19). So **every run folder created
before 2026-08-19 now mismatches its own freshly tiled grids** and D1 will refuse a resume into
it. That is correct — those work lists genuinely no longer describe what the code would produce —
but the error message must name this specific cause, or it reads as a bug for the one week it is
common.

#### D3 — `output_folderpath` is documented as the identity of a run

The docstring of `run_inference` gains one sentence saying so, and D1's error message repeats it.
Nothing currently says it, which is why reusing one looked free.

### Part B — #65, the four silent legs

#### D4 — one progress helper, extracted from `_tick`, used everywhere

`create_datacube.setup`'s `_tick` closure is promoted to a module-level helper (proposed:
`fsd.progress.ticker(total, label)` returning a callable with `_tick`'s throttle + ETA behaviour).
`setup` is refactored to use it, so there is **one** implementation and one output format rather
than a second copy in `runners.py`. Line format is unchanged from what `setup` prints today —
users have already learned to read it, and #65 explicitly names it as the bar.

#### D5 — the four legs print, in `[label] done/total (pct%) | rate | elapsed | eta` shape

```
[stage] bundle -> abfss://.../runs/<run_id>/bundle | 4 files, 13.2 MB
[stage] 4/4 files (100%) | 0.0 files/s | elapsed 627s | eta 0s
[aml]   run_id=20260819T231205Z root=abfss://.../runs/20260819T231205Z
[aml]   12/32 jobs terminal (38%) | elapsed 214s | eta 349s | 20 running
[merge] 137/299 inputs (46%) | 0.3 inputs/s | elapsed 452s | eta 540s
```

- **`_stage_bundle`** prints the destination and total bytes *before* the upload starts (the 627 s
  leg is the one where silence costs most), then ticks per file.
- **`_aml_submit_and_wait`** ticks once per poll, from the `statuses` dict it already maintains.
  ETA is derived from the terminal-count rate, which is honest for a fan-out and useless for a
  single job — so with one job it prints the elapsed and omits the ETA rather than inventing one.
- **`_merge_outputs`** ticks per input, matching `[setup]` exactly.
- **collect (`_existing_outputs`)** ticks per probed path.

#### D6 — the run root is printed early, before any job is submitted

One line naming `run_id` and `run_root`, so `_status/*.json` and `_timing.json` can be watched
from outside the notebook while the run is in flight. This is the cheapest item in the whole spec
and the one that most directly answers "is it stuck?".

#### D7 — `ml_client.jobs.stream()` is rejected, not overlooked

The AML SDK does ship a progress affordance: `JobOperations.stream(name)` (verified against the
**installed** `azure-ai-ml 1.34.1` in `fsd/.venv`, not from memory). It is **per-job and
blocking** — signature `(self, name: str) -> None`, "Streams the logs of a running job". For an
N-shard fan-out it would serialise on shard 0 and report nothing about shards 1..N-1 until it
returned. The poll loop already holds every job's status; ticking from that is both more accurate
and non-blocking. Recorded here so the obvious alternative is not re-proposed later.

### Part C — #64, the no-op download

#### D8 — MPC dispatch is preceded by a driver-side catalog diff; CDSE is explicitly out

In `run_aml_download`'s MPC branch, immediately after `discover_shard_rows` and **before**
`_aml_download_preflight`:

1. read the existing catalog if it exists (a `TileCatalog` read, cheap; absent catalog → the
   shortfall is everything, unchanged behaviour);
2. compute the shortfall = discovered rows whose `(tile_id, band)` the catalog does not already
   carry;
3. **shortfall empty** → print `[download] 0 of N assets missing; nothing to download` and return
   the same result shape a real run returns, **without submitting anything**;
4. **shortfall partial** → `shard_units` **the shortfall**, not the full row list, and say so:
   `[download] 41 of 828 assets missing; dispatching 41`.

Step 4 matters as much as step 3: a request that is 95 % already-present must not shard 100 %.

**CDSE is out of scope and says so in the docstring.** Its discovery runs on the node inside the
single whole-ROI job (§1), so the same treatment requires a new driver-side CDSE discovery pass —
a larger change, a different risk profile, and not the path that produced the measured 5m31s.

#### D9 — the diff key is the catalog row, not the file on disk, and is named loudly

"Already present" means **the catalog has a row for `tile_id` whose `files` covers `band`**. It
does *not* stat the destination object. Rationale: a per-granule existence probe is one WAN
listing per asset — on the order of the cold start this decision exists to avoid — and the
catalog is already the archive's declared contents everywhere else in fsd.

The cost is a real failure mode: a catalog row whose file was deleted or never landed makes the
diff skip a download that is genuinely needed. **rclone makes exactly this trade explicit** — its
default compares size *and* modtime, and the cheap comparison (`--size-only`) is an opt-in flag
rather than a silent default. fsd's position: the cheap key is the default (the catalog *is* fsd's
source of truth), but D9 requires it be named in the docstring and in the printed line, so a user
who suspects a hole in the archive knows what was and was not checked.

## 4. Acceptance criteria

1. Re-running `run_inference(roi=...)` into an `output_folderpath` whose `input.csv` holds a
   different cell-id set raises `PreflightError` naming the folder, both counts, and a sample of
   the difference; re-running with the **same** ROI still resumes and skips completed cells.
2. The D1 error message names the spec-46 cell-count change as a probable cause when the cached
   set is a strict superset of the fresh one by a small number of cells.
3. `run_inference` and `download` docstrings state that `output_folderpath` / the run folder is
   the identity of a run.
4. `_tick` lives in exactly one place; `create_datacube.setup`'s output format is byte-identical
   to today's (regression test on the printed line).
5. Each of the four legs emits at least one progress line for a run of ≥ 2 units, in the
   `[label] done/total (pct%) | ... | elapsed | eta` shape; a single-job wait omits the ETA rather
   than inventing one.
6. The run root + run id are printed before the first `create_or_update` call.
7. An MPC download whose every discovered asset is already in the catalog returns **without
   calling `ml_client.jobs.create_or_update` at all**, and its return value has the same keys a
   dispatched run returns.
8. A partially-present MPC download shards only the shortfall: with 828 discovered and 41 missing,
   the submitted shard rows total 41.
9. A CDSE download is unchanged (regression test) and its docstring says why.
10. `pytest -q` and `ruff check src/ tests/ demos/ examples/` clean; no network in the unit tests
    (the AML client is injected, spec 36 D3 invariant 3).

## 5. Risks

- **D1 refuses a resume the user wanted.** Anyone resuming a pre-2026-08-19 run folder is blocked
  until they pick a new `output_folderpath`, losing the already-computed cells. Mitigated by D2's
  message requirement; the alternative (silently inferring the wrong ROI) is worse. Cheap escape
  hatch if wanted: see §7 Q1.
- **D8's diff skips a needed download** when the catalog over-declares (a row whose file is
  missing). This is D9's stated cost. Mitigated by naming it in the printed line; a `force=`
  escape hatch is §7 Q3.
- **Progress printing changes stdout** for anything parsing these functions' output. Nothing in
  the repo does. Notebook users see more, which is the point.
- **The extraction in D4 touches a hot, working path** (`setup` runs on every run). Mitigated by
  AC4's byte-identical regression test.

## 6. Alternatives considered

- **#66: rewrite `input.csv` from the new grids instead of raising.** Rejected — it orphans every
  cell already written under the old id set, and cannot clean them up on blob (#50).
- **#66: hash the full request (dates, bands, mosaic_days, ROI) into a run key.** Rejected as
  redundant: spec 46 D1/D2 already put window + `mosaic_days` in the folder name, so those cannot
  collide. Only the id set is unguarded. Revisit if a future parameter escapes the folder name.
- **#65: `ml_client.jobs.stream()`.** Rejected — per-job and blocking (D7).
- **#65: a logging handler instead of `print`.** Rejected for consistency: the audience is a
  notebook cell, and `[setup]`'s established output is `print` (memory `long-process-progress`).
- **#64: keep the skip on the node only.** Rejected — that is today's behaviour and is exactly
  what cost 5m31s.
- **#64: stat every destination object.** Rejected as self-defeating (D9): one WAN listing per
  asset approaches the cold-start cost the decision exists to avoid.

## 7. Questions at sign-off

1. **D1: hard error, or warning + proceed with the cached list?** → Default: **hard error**
   (matches the issue's own "Suggested"). The counter-argument is the one-week spec-46 drift
   window in D2, which a warning would smooth over. If you want a middle path, the cheapest is an
   explicit `resume=False`/`force_resetup=` kwarg rather than a softer default. *Default resolved
   by Claude; overturn in review.*
2. **D8: short-circuit only, or short-circuit + shortfall-only dispatch?** → Default: **both**.
   Short-circuit alone fixes the measured 5m31s; shortfall-only is what makes a 95 %-present
   request cheap, and the issue calls step 4 out explicitly. It is also the riskier half (D9), so
   this is the one to split out if you want a smaller first landing. *Default resolved by Claude.*
3. **D9: catalog row only, or row + destination existence?** → Default: **row only**, named in the
   docstring and the printed line. *Default resolved by Claude.*
4. **Does #64 also apply to `create_training_data(download=True)`?** → Default: **yes, for free** —
   it routes through the same `run_aml_download`, so no extra work. Flagged only so the acceptance
   test covers it.

## 8. Best-practice alignment / sources

- **`azure-ai-ml` 1.34.1, `azure.ai.ml.operations.JobOperations.stream`** — inspected directly in
  `fsd/.venv` (primary source: the installed SDK, not documentation about it). Supplied the exact
  signature `(self, name: str) -> None` and the docstring "Streams the logs of a running job",
  which establishes that the SDK's only built-in progress affordance is **single-job and
  blocking**. That is the whole basis of D7 rejecting it for an N-shard fan-out, and the reason
  D5 ticks from the poll loop's own `statuses` dict instead.
- **[Snakemake — `--rerun-triggers` / CLI](https://snakemake.readthedocs.io/en/stable/executing/cli.html)**
  and its [FAQ](https://snakemake.readthedocs.io/en/stable/project_info/faq.html): supplied the
  benchmark for D1/D2 — a mature workflow engine's **default** rerun triggers are `code`, `input`,
  `mtime`, `params` and `software-env`, i.e. a changed *parameter set* or *input set* invalidates
  cached work, and file-modification-time alone is explicitly the *legacy* mode
  (`--rerun-trigger mtime`). fsd's `input.csv` resume keys on **existence alone**, which is weaker
  than even that legacy mode. It also supplied the distinction D1 leans on: Snakemake *re-runs* on
  a changed request, whereas fsd cannot (blob `rm -r`, #50) and therefore *refuses* — detect-and-
  refuse as the honest subset of detect-and-rerun.
- **[rclone — `sync` / comparison flags](https://rclone.org/commands/rclone_sync/)** and
  [docs](https://rclone.org/docs/): supplied the framing for D9. rclone's default skips a file only
  when size **and** modtime match, and the cheaper comparison (`--size-only`) is an explicit opt-in
  because it trades correctness for cost. This is why D9 keeps the cheap catalog-row key (the
  catalog is fsd's declared source of truth) but **requires it be named** in the docstring and the
  printed line rather than being an invisible default — the failure mode (a row whose file never
  landed) is real and the user must be able to see which check ran.
- `src/fsd/workflows/create_datacube.py:120-133` (internal): `_tick`'s throttle + rate + ETA
  format, which D4/D5 adopt verbatim rather than inventing a second progress style; #65 names it
  as the bar explicitly.
- `src/fsd/workflows/runners.py:1092` + `src/fsd/sources/mpc.py:440-456` (internal): established
  that MPC discovery already runs on the driver and that each row carries `tile_id`/`band`/`dst` —
  which is what makes D8's diff nearly free for MPC, and what makes it *not* free for CDSE.
- `specs/46-run-addressability-and-grid-dedup.md` D1/D2/D4 (internal): the run-folder name already
  encodes window + `mosaic_days` (so D2 need not compare them) and D4's measured cell-count change
  (300 → 299, 9 → 1) is the source of the drift consequence D2 must state.
- Issues #64/#65/#66 (internal): every measured number in §1 — 5m31s, 30m10s, 627 s for 13 MB,
  ~1000 s merge on 300 cells — is from the user's 2026-08-18 run, quoted rather than re-derived.

## 9. Implementation note

Per `CLAUDE.md`'s model split, implementation is a **Sonnet session at `/effort medium`** against
this spec once signed off. Suggested landing order, smallest and safest first:

1. **Part A / #66** — `src/fsd/api.py` `_run_inference_roi` (~20 lines + 2 tests). Highest
   severity, lowest risk.
2. **Part B / #65** — new `src/fsd/progress.py`, refactor `workflows/create_datacube.py` to use
   it, then the four call sites in `workflows/runners.py` (~80 lines + tests). Mechanical.
3. **Part C / #64** — `workflows/runners.py` MPC branch (~50 lines + tests). The riskiest, and the
   one §7 Q2 may split in half.

Parts A and B touch disjoint files from C and can land independently if the session runs long.
