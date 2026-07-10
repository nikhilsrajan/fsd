# Spec 22 — Unify inference on the runner seam (retire `engine.run_local`'s `mp.Pool`) + idempotent outputs

> **Status: SIGNED OFF (2026-07-07).** SO-1..SO-5 approved as drafted. After P0.75 (spec 21), `engine.run_local`'s
> `multiprocessing.Pool` is the **only** parallel fan-out in fsd that does **not** go through the
> runner seam. This spec retires it: the pre-built-cubes inference path (spec 18) fans out its
> `cores>1` work through **Snakemake** (like the build and ROI paths), so **Batch (P4) can dispatch
> pre-built inference too** and P4 stays a pure `runner=` swap. It also makes inference **idempotent
> / resumable** — a re-run skips outputs that already exist (the gap the P0.75 demo exposed).
>
> Modifies signed-off **spec 18** engine behavior. Decisions flagged **[SO-n]** need sign-off.

## Motivation

Two problems, one fix.

1. **`mp.Pool` is the odd fan-out out.** The datacube build (spec 08) and ROI inference (spec 21)
   both parallelise through the **runner seam** (Snakemake locally → Batch at P4, unchanged). But
   `run_inference(inference_datacubes=…)` still parallelises with an in-process
   `multiprocessing.Pool` (`engine.run_local`). That's a *second* mechanism that P4 would have to
   replace rather than swap — the exact thing P0.75 was written to avoid, left in one corner.

2. **Inference isn't resumable.** `engine.run_local` (both the pool **and** the sequential branch)
   has **no idempotency** — it processes every `(datacube, output)` pair and overwrites,
   regardless of whether `output.tif` exists. So a re-run re-infers everything. The P0.75 demo
   showed this: step 4 (build, Snakemake) skipped existing cubes, but step 5 (`run_inference`,
   engine) re-inferred every grid. Snakemake gives resumability for free; the in-process path can
   get it with a one-line existence check.

Retiring the pool onto the runner seam fixes (1); making outputs idempotent fixes (2).

## Design

`engine.run_local` today: `cores==1` **or** a live adapter → sequential **in-process** (no bundle);
`cores>1` **and** a bundle → `mp.Pool`. Only the `cores>1` branch is the pool. The change:

| call | mechanism | bundle? | resumable? |
|---|---|---|---|
| `cores == 1` / live adapter | in-process sequential (**kept**) | no | ✅ (new — skip existing) |
| `cores > 1` | **Snakemake infer-only fan-out** (replaces `mp.Pool`) | yes (auto-saved if live) | ✅ |

Every current *semantic* is preserved: `cores=1` stays no-bundle in-process; `cores>1` already
required a bundle. Only the `cores>1` **mechanism** changes (pool → Snakemake), and both paths gain
skip-existing.

### Keep the `cores=1` in-process path — don't Snakemake *everything* [SO-1]

Tempting to route all inference through Snakemake and delete the in-process path. **Don't** — the
fast synthetic pytest suite (`test_model.py`) runs `run_inference` in-process with live adapters
(`cores=1`); shelling every call to Snakemake would make those subprocess- and bundle-heavy
integration tests that depend on snakemake being installed, violating the "fast, synthetic,
deterministic pytest" rule (CLAUDE.md). `cores=1` in-process stays the test/debug/small-run path.

### Route in `api`, not `engine` (layering) [SO-2]

`engine` is the model layer; `runners` is workflows, and `workflows.infer_task` already imports
`engine` — so `engine.run_local` importing `runners` would be a cycle. The `cores>1` → Snakemake
decision lives in **`api.run_inference`** (which already imports both). `engine.run_local` shrinks
to the pure in-process path (pool + `_worker` deleted); `api` calls `runners.run_local_infer_only`
for `cores>1`.

### Idempotent outputs — skip existing unless `overwrite=True` [SO-3]

Inference becomes idempotent in **both** paths:
- **in-process:** skip a `(dc, out)` pair when `fs.exists(out)` and not `overwrite`.
- **Snakemake:** the infer-only Snakefile targets `output.tif` directly, so existing outputs are
  skipped by Snakemake's DAG (no separate sentinel needed).
- **default = skip** (resumable). `overwrite=True` forces recompute (in-process re-runs all pairs;
  the runner path removes targets / uses `--forceall`). The ROI path (spec 21) already resumes via
  `done_infer.txt` and honours `overwrite` the same way.

This directly fixes the demo re-run: `run_inference` on an already-inferred set now reports
"nothing to do" instead of re-deploying.

### `cubes_per_task` batching knob (default 1) [SO-4]

The pool loaded the bundle **once per worker** and reused it across many cubes; Snakemake reloads
it **once per task**. For **many tiny cubes + a fast model (RF)**, per-cube Python-startup +
bundle-load can dominate and be *slower* than the pool. So the infer-only fan-out groups
`cubes_per_task` cubes per Snakemake job (one bundle load amortised over K cubes). **Default 1**
(one cube per job → finest resumability, current-like behaviour); raise it for many-small-cube or
heavy-model runs. This is the same granularity lever AZURE_INFRA §7 flags for Batch and that spec
21 deferred for the ROI path (`cells_per_task`) — set here for the infer-only path; ROI batching
stays deferred.

**No `mp.Pool` inside the task — the whole point is to retire it.** The two axes of parallelism are
split: **across tasks = Snakemake** (`--cores N` runs N task processes; the *only* parallel
primitive), **within a task = a plain sequential `for` loop** over the group's cubes (bundle loaded
once, no pool/threads). `cubes_per_task` is purely a *grouping* knob that decides how many cubes one
sequential task owns; it does **not** reintroduce intra-task concurrency. This mirrors the old pool's
economics (its workers each loaded once and looped over many cubes) with a Snakemake-scheduled OS
process as the "worker" and explicit static grouping in place of `imap_unordered`'s dynamic per-cube
pull — the tradeoff being coarser load-balancing + coarser resumability (a K-group re-runs whole if
any one of its K outputs is missing), tuned by the knob. **Any future need for finer balancing is a
smaller `cubes_per_task`, never a pool inside the task.**

### Default `cores` unchanged [SO-5]

`run_inference` keeps `cores=1` as the default → fully backward-compatible: nothing shells to
Snakemake unless a user opts into parallel (`cores>1`). The only visible change at the default is
that a re-run now skips existing outputs (SO-3).

## Files

- `src/fsd/model/engine.py` — delete the `mp.Pool` branch + `_worker`; `run_local` becomes the
  in-process sequential path (loads bundle/adapter once, loops), now with a **skip-existing** guard
  (`overwrite` param).
- `src/fsd/workflows/infer_only_task.py` — **new** unit-of-work: infer one-or-more prebuilt
  datacubes → COG(s), CLI-invokable (`--input-csv … --rows i:j --bundle …`); a thin loop over
  `engine.infer_datacube_to_cog` (loads the bundle once per task → the `cubes_per_task` amortiser).
- `src/fsd/workflows/_snakefiles/infer_only/Snakefile` — **new**; one job per `cubes_per_task`
  group, `output:` = that group's `output.tif` list (existing outputs skipped by the DAG).
- `src/fsd/workflows/runners.py` — `run_local_infer_only(input_csv, *, cores, bundle_path,
  cubes_per_task, overwrite, …)`.
- `src/fsd/api.py` — `run_inference` pre-built branch: `cores>1` writes a `(datacube_filepath,
  output_filepath)` CSV and calls `run_local_infer_only`; `cores=1` calls `engine.run_local`.
  New `overwrite` + `cubes_per_task` params (both modes). Auto-save a live adapter to a temp bundle
  when `cores>1` (mirrors ROI mode).
- Docs: `CHANGES.md` (engine parallelism + idempotency), `specs/18` (pointer to this change),
  `tests/manual/deploy.md` (note resumability + the `cores>1` = runner behaviour), `PROGRESS.md`,
  memory.

## Testing

- **pytest:** `run_inference(cores=1)` still in-process (existing tests unchanged, stay fast);
  a **skip-existing** test (run twice → second is a no-op, mtimes unchanged; `overwrite=True`
  recomputes); `infer_only_task` CLI on a synthetic cube → COG; `cubes_per_task>1` groups rows
  (dry-run job count); the infer-only Snakefile dry-run (skipif snakemake absent).
- **Manual:** extend `tests/manual/deploy.md` — run `run_inference(inference_datacubes=…, cores=4)`
  on the benchmark, confirm Snakemake fan-out + a second run skips everything; `overwrite=True` reruns.
- **Real smoke:** the P0.75 demo (`e2e_ethiopia.py`) re-run should now **skip** step-5 inference
  when `model_outputs/*/output.tif` exist (the behaviour that motivated this spec).

## Sign-off checklist

- [x] **SO-1** — Keep `cores=1` in-process (tests/debug/small, no bundle); only `cores>1` moves to
      Snakemake. Do **not** Snakemake-ify everything.
- [x] **SO-2** — Route the `cores>1`→Snakemake decision in `api.run_inference`, not `engine`
      (avoid a model→workflows import cycle); `engine.run_local` becomes in-process-only.
- [x] **SO-3** — Inference is **idempotent**: skip existing outputs unless `overwrite=True`, in both
      paths; default skip (fixes the demo re-run).
- [x] **SO-4** — Add `cubes_per_task` (default 1) so `cores>1` amortises bundle load; ROI
      `cells_per_task` stays deferred.
- [x] **SO-5** — Default stays `cores=1` (backward-compatible; only new default behaviour is skip-existing).
