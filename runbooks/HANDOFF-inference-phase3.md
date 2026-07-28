# Handoff — implement the adlfs concurrent-write seam retry (TODO #57), then finish runbook 38 Phase 3

Fresh-session baton. **This is a pointer, not the source of truth** — the durable, detailed state is
already in the repo. Read those first; don't re-derive what they hold.

## Read these (in order), then start
1. `fsd/PROGRESS.md` — **top block** ("⭐ NEXT STEP" → "🔴 THE NEXT TASK") = the canonical plan +
   the **fully-designed fix** (constants, functions, call-site, tests, verify steps) + git state.
2. `fsd/TODO.md` #57 — the one-paragraph problem statement (root cause + fix shape).
3. `fsd/LIMITATIONS.md` — the two new rows (adlfs concurrent-write race; roi-mode convex-hull tiling).
4. `fsd/CLAUDE.md` — working contract (spec-first, Claude never runs pipeline/networked scripts →
   operator runbooks with `_result.json`; model/effort split; commit/push only when asked).

## The task (one sentence)
Add a **backend-agnostic retry** for adlfs's transient `InvalidBlockList` to the storage seam
(`src/fsd/storage/fs.py`) so `create_datacube.setup()`'s concurrent per-cell blob writes survive at
scale, then the user re-runs `runbooks/38-inference-on-aml.md` **Phase 3** (the 1167-cell fan-out that
died at shape 0/1167).

## Why this is the blocker (one paragraph)
Runbook 38 is **GREEN through Phase 2** on the real cluster (env smoke, Phase 0 D3/D4, Phase 1 → 9
cells, Phase 2 resume + D13 guard). **Phase 3 died in driver-side `create_datacube.setup()`**:
16-thread concurrent `geometry.geojson`/`catalog.parquet` writes through the one shared adlfs client
race on Azure's `commit_block_list` → `InvalidBlockList`. Transient (a re-write works), no retry today.
`config.SETUP_MAX_CONCURRENT` is import-bound so it can't be lowered at runtime. Same class as the
`9422a1a` grids.geojson seam fix (GDAL/seam mismatch), one layer down (seam not resilient under real
concurrency + a flaky link).

## Locked / decided — do NOT re-litigate
- **User chose (2026-07-28) "keep 1167 + fix adlfs"** — do NOT shrink the ROI; make the seam resilient.
  (Fewer-cells options are noted for the future, not for now.)
- The fix is **driver-side** → it unblocks Phase 3 with **no AML image rebuild** (rebuilding the
  inference Environment is optional hygiene so nodes get the retry too).
- `fs.py` must stay **backend-agnostic** — match the transient error by **message substring**, never
  import azure (azure is an optional backend).

## Model / effort
The fix is **fully designed in PROGRESS.md** → a **Sonnet@medium** session can implement it test-first
against that design (it's mechanical: retry helper + 2 seam fns + wrap 2 writers + 1 call-site swap +
retry unit tests). Switch back to **Opus@high** for review before merge (the repo's
Sonnet-implements / Opus-reviews gate). No spec needed — it's a bug fix against a recorded design, not
new behavior; but keep the tests **non-vacuous** (assert the retry actually retries; assert
non-transient re-raises).

## Definition of done
`pytest -q` green (baseline **436 passed / 2 skipped**) + `ruff check src/ tests/` clean; TODO #57 +
the LIMITATIONS row flipped to fixed; then the **user** re-runs runbook 38 Phase 3 and pastes
`phase3_result.json` (expect `sum_shard_units == n_cells_out == 1167`, `n_failed == 0`, `bundle_loads
== n_shards` with `cores=1`). That closes the last leg of the demo pipeline.

## Git state at handoff
`main` **4 commits ahead of `origin/main` (`e7d8ba6`), UNPUSHED** (+ this handoff flush commit).
`4050b3b` · `511c300` · `9422a1a` (grids seam fix) · `265bec4` (median + OUT40/OUT38 + rb38 Phase 1).
**Nothing else pending; tree clean.** Push only when asked, RECIPES.md identifier sweep first.

## Suggested `/handoff` goal
"Implement the adlfs InvalidBlockList seam retry (TODO #57, designed in PROGRESS.md) test-first, then
the user re-runs runbook 38 Phase 3 (1167-cell fan-out). Sonnet@medium implement → Opus@high review."
