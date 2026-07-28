# Handoff — run runbook 38 Phase 3 with the CORRECTED ROI (operator run + triage)

Fresh-session baton. **This is a pointer, not the source of truth** — the durable state is in the
repo. Read those first; don't re-derive what they hold.

**Status change vs. the previous baton (2026-07-28):** that baton said "TODO #57 landed, just re-run
Phase 3". **It was wrong about the bug.** Phase 3's real blocker was duplicate S2 cell ids caused by
passing a *label set* as `roi=` (TODO #58 / spec 21 **D-GRID-1**) — now fixed at source, with the
runbook's ROI corrected to `AT_ROI.geojson`. No code work pending; the remaining step is the **user**
running Phase 3 and pasting back `phase3_result.json`.

## Read these (in order), then start
1. `fsd/PROGRESS.md` — **top block** = canonical status + the "READ THIS BEFORE RE-RUNNING" box.
2. `fsd/specs/21-roi-inference-verb.md` **D-GRID-1** — the amended contract: an ROI is one *region*;
   one cell = one row = one work unit; ids unique. This is what the failure taught.
3. `fsd/runbooks/38-inference-on-aml.md` — **Phase 3** is the thing to run (ROI box at its head).
   Phases 0–2 are GREEN and idempotent; re-run them only if the shell/env was lost.
4. `fsd/TODO.md` **#58** (the real bug) and **#57** (retracted root cause) + `fsd/LIMITATIONS.md`.
5. `fsd/CLAUDE.md` — working contract (Claude never runs pipeline/networked scripts → the **user** runs
   the runbook and pastes `_result.json`; Claude diffs it against the success criteria and never reads
   live logs; commit/push only when asked).

## The task (one sentence)
User runs runbook 38 **Phase 3** with the corrected ROI (`AT_ROI.geojson` → ~300 cells) and pastes
`$OUT38/phase3_result.json`; Claude checks it against the runbook's PASS criteria and triages
anything that isn't green.

## 🔴 Phase 3 has NEVER RUN — read this before anything else
Its two 2026-07-28 attempts died on the same bug, and it was **not** the adlfs race TODO #57
describes. **`AT_2018_TRAIN.geojson` — a label set of 900 field polygons — was passed as `roi=`.**
`roi_to_s2_grids` then clipped with `gpd.overlay(grids, roi_gdf)`, which emits one row per
*(cell × polygon)* pair → **1167 rows for 172 distinct cells**, one repeated 43×. `id` is the
work-unit key (`export_folderpath` derives from it), so up to 16 threads wrote the **same** blob →
`InvalidBlockList`. Fixed at source: union clip + unique-id assertion (`grid.py`), duplicate-id guard
in `setup()`, runbook ROI corrected, spec 21 amended (**D-GRID-1**), TODO #58.

**Consequences for this run:** expect **~300 cells**, not 1167 — and each is a **full ~49 km² cube**
(vs the 0.016 km² fragments the old numbers came from), so it is far more pixels per task than any
previous run. **Size the fan-out before committing to it.** Every PASS criterion quoting 1167 is void.

## The TODO #57 retry was REVERTED — there is no write-retry any more
It was built for a hypothesised transient adlfs race that has never been demonstrated (runbook 36
wrote 900 distinct blobs, same 16-way concurrency, same VPN, same account, 71 s, zero errors). It
could not have fixed Phase 3: a retry cannot resolve a deterministic same-blob collision, and 16
threads x 6 attempts buried the real error under a minutes-long `[storage] transient write error`
storm that read as an infinite loop. **Reverted in full** — a failed blob write now raises on the
first attempt, which is what makes the real cause legible. `fs.write_bytes`/`write_text` survive as
plain seam helpers. **If you see `InvalidBlockList` again, suspect TWO WRITERS ON ONE BLOB first.**

## Duplicate ids now fail in PREFLIGHT, before any spend
`run_inference` tiles the ROI *inside* preflight — before `fs.makedirs(output_folderpath)` and before
`_ensure_bundle` — and rejects duplicate cell ids or an ROI that tiles to 0 cells. So a bad ROI costs
seconds, not a bundle upload (627 s for 13 MB over VPN) + N blob writes + an AML dispatch. Preflight
also **prints the cell count before spending**: `[run_inference] roi -> N grid cells`. **Read that
line — N is the cluster workload and the bill.**

## Definition of done
`phase3_result.json` with `pass: true` — i.e. `sum_shard_units == n_cells_out == <the cell count
`[setup]` printed>` (~300 for `AT_ROI`; the old 1167 is void), `n_failed == 0`,
`n_skipped == 0` on a cold run, and the D7 claim `bundle_loads == n_shards_reported` (with `cores=1`,
one bundle load per node). `driver_overhead_seconds` / `slowest_shard_seconds` feed TODO #55's timed-demo
report. Then: flush PROGRESS.md, flip the runbook 38 Phase 3 header to GREEN, and the demo pipeline
(download → build → flatten → train+bundle → inference) is end-to-end complete.

## Triage table — if Phase 3 does not go green
| What you see | What it means | Next step |
|---|---|---|
| Dies at shape ~0 in **seconds**, `AuthorizationFailure` / `AADSTS…` / `ContainerNotFound` | A **permanent** error, surfacing immediately as it should. Usually **VPN down** (blob network rules) or a stale `az login`. | Fix creds/VPN, re-run. Do **not** reintroduce a retry to paper over it. |
| `InvalidBlockList` anywhere | **Two writers, one blob** — that is what the error literally reports, and what both 2026-07-28 failures were. There is no retry any more, so it raises immediately with the colliding path in the message. | Check the shapes/grids file for duplicate ids: `gpd.read_file(p)["id"].duplicated().any()`. Preflight should have caught it — if it didn't, that is a bug in the guard, not a reason to retry. |
| Setup completes, jobs fail **node-side** | Not this fix's territory (the fix is driver-side). | `az ml job stream -n <name>` for one shard's traceback; job names are in the raised `RuntimeError`'s shard list or `_status/*.json`. |
| Long silent pause before any AML output | **Not a hang** — driver-side `setup()` writing every cell's control files. The tell: the `azure.ai.ml` "experimental class" warnings have not printed yet (imported lazily at dispatch). A throttled `[setup] N/<total> … eta` line should be ticking. | Wait. |

## Locked / decided — do NOT re-litigate
> ⚠️ **Only the user's own calls belong in this box.** Inherited "facts" do not — see the retraction
> below. Nothing goes here unless you can name where it was verified.

- **ROI is `AT_ROI.geojson`** (1 polygon, 10,682 km² → **~300 cells**). ❌ **RETRACTED:** the previous
  baton locked "ROI must be `AT_2018_TRAIN.geojson`" and "keep 1167 cells". Both were wrong.
  `AT_2018_TRAIN` is a **label set** (900 field polygons) that was mistakenly wired into the `roi=`
  slot; the "1167 cells" figure was 1167 *(cell × field)* fragments over 172 real cells, not a cell
  count. The original warning it grew from was only about *imagery overlap* (don't use the
  Ethiopia-translated file) and got over-generalised into the wrong file class. See spec 21 D-GRID-1.
- **Still true:** do **NOT** use `austria_eurocrops_sampled_ethiopia_translated.geojson` (Austria
  fields translated to 36°E Ethiopia): zero overlap with the Austria archive → every cell builds an
  empty cube. This is the mistake runbook 36 Phase 3 hit.
- **No AML image rebuild needed** — the fixes are driver-side, so the local venv carries them.
- `fs.py` stays **backend-agnostic** — never import azure to classify an error.

## Model / effort
This is an **operator run + result triage**, not implementation. **Opus@high** to diff
`phase3_result.json` against the PASS criteria and debug anything that isn't green. Drop to
Sonnet@medium only if triage turns into mechanical code work against a written design.

## Git state at handoff
`main` = `3db3dd9`, in sync with `origin/main` (the TODO #57 retry, pushed 2026-07-28). **The
D-GRID-1 work — `grid.py`, `api.py`, `create_datacube.py`, specs/21, the doc corrections, +6 tests — is
UNCOMMITTED on top of it**, along with the TODO #57 revert and the preflight guard (`pytest -q` 443
passed / 2 skipped, `ruff` clean). The
`worktree-todo57-adlfs-retry` worktree + branch are pruned; `spike/rslearn` untouched.

## Working agreement adopted 2026-07-28 (after this bug)
Before proposing a fix, state three things **separately**, so the wrong one can be corrected cheaply:
**(1) Observed** — what the log/measurement literally says; **(2) Inferred** — the mechanism claimed
to produce it; **(3) Assumed** — what is taken on faith from docs/handoffs, *with its source*, flagged
as unverified. This bug cost two failed cloud runs because an inherited assumption ("ROI must be
`AT_2018_TRAIN`") was presented as established fact inside a do-not-re-litigate box. **Run the cheap
local check before the expensive cloud run** — 1167-vs-172 was three lines of geopandas.

## Gotcha that cost time last session — don't repeat it
A per-spec worktree `.venv` built with a bare `pip install -e ".[dev]"` is **not** equivalent to the
repo `.venv`: it silently skips `tests/test_azure_seam.py` (25 tests — the module that covers
`fsd.storage`!) and `tests/test_grid.py` (4), and resolves a newer ruff whose larger default rule set
invites narrowing `--select` and hiding real findings. Full recipe for testing worktree **code** against
the repo's **deps** is in `RECIPES.md` ("Verify a worktree's code against the repo's FULL dependency
set"). Baseline on `main` today: **441 passed / 2 skipped**, `ruff check src/ tests/` clean.

## Suggested `/handoff` goal
"Run runbook 38 Phase 3 with the corrected ROI (AT_ROI, ~300 cells; spec 21 D-GRID-1) and triage `phase3_result.json`
against the PASS criteria. Opus@high."
