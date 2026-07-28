# Handoff — implement spec 40 (`demos/e2e_austria_aml.py`)

**Ephemeral baton.** Durable state is in the repo; this is a pointer plus the traps that are not
obvious from the spec. Do not re-derive what the repo holds.

**Model/effort: Sonnet@medium.** This is spec-following implementation against a signed-off design.
Switch back to Opus@high for review. Do not re-open the design — it was grilled to ten decisions on
2026-07-28 and every one is recorded with its reasoning.

## Read these first, in `fsd/`
1. **`specs/40-e2e-aml-demo-script.md`** — the contract. D1–D15, deliverables in §5, tests in §6.
2. **`docs/adr/0021-dispatch-telemetry-is-a-file-not-a-return-value.md`** — why timing is a file.
   If you find yourself wanting to add `result.timing`, read this first; it is the rejected option.
3. **`CONTEXT.md`** — vocabulary. **demo run / step / run / job admission / dispatch telemetry** are
   defined terms with `_Avoid_` lists. Use them in code, docstrings and commits. "Phase" is banned
   in this work (it means a run-book's manual stage).
4. **`demos/e2e_austria.py`** — the script you are mirroring. Same eight step labels, same
   `timed_step` accumulator, same `timings.json` schema.
5. **`CLAUDE.md`** — the working contract. Two rules bite here: **all file I/O through `fsd.storage`**
   (rasterio/GDAL VSI is the documented exception), and **Claude never runs the pipeline** — you
   write the script, the operator runs it.

## Build order (each step green before the next)

**1. The in-job stamps (deliverable 1).** Four entrypoints: `workflows/{shard,download,infer_shard,
flatten}.py`. Add `process_start_at` (**first line of the module**, before heavy imports),
`work_start_at`, `work_end_at`, `ended_at` to the `_status/<k>.json` each already writes. Keep
`seconds` exactly as-is — run-books and stored results depend on it.

**2. Dispatch telemetry (deliverable 2).** `runners._aml_submit_and_wait` records `submitted_at`
per job (as each `create_or_update` returns) and `returned_at`, then writes
`<run_root>/_timing.json`. Derive `job_admission_seconds`, `import_seconds`,
`dispatch_overhead_seconds` and the per-run additive split per spec D11. **Return nothing new** —
no dataclass changes (ADR 0021).

**3. Tests (deliverable 6)** — spec §6. The one that matters most is the **additive invariant**:
`driver_prep + first_admission + execution_window + teardown_detect + post_collect` sums to the run
wall. That property is the only reason the 2026-07-28 forensics were trustworthy.

**4. The script (deliverable 3)**, then **the plotter (deliverable 4)**, then the operator notes
(deliverable 5).

## Traps — every one of these has already cost a cloud run

- **GDAL/rasterio cannot open `abfss://`.** Five instances so far (cdse `_roi_gdf`, `task.py`,
  spec-39 gdf staging, `grids.geojson`, `_merge_outputs`). Anything you hand to rasterio must come
  through the VSI seam or local scratch. **Assume every new blob path is instance six.**
- **`fs.glob` returns the filesystem's own path form**, not your url — adlfs gives `container/path/…`
  with no scheme. A url comparison matches everything locally and nothing on blob. See
  `api._output_key` for the pattern that handles it (and `test_output_key_is_scheme_independent`).
- **`rio_open` owns a `rasterio.Env` per handle and GDAL's env stack is LIFO** — holding many open
  at once and closing them in creation order tears down the root env. Use `raster.rio_env` (one env
  for N datasets). This is why spec 40 does not thread the metadata reads: doing it needs care.
- **`create_datacube.setup()` appends to `input.csv` with no dedupe** (TODO #53). Running a setup
  twice dispatches double. The demo run must not re-enter setup for an existing `run_id`.
- **`export_folderpath` is `run_folderpath/<window>/<id>`** and `<window>` is derived per-shape from
  actual timestamps, so it **varies between cells** (`create_datacube.py:147-151`). Any path pattern
  must span it.
- **Clock skew is real:** ~8 s laptop-vs-Azure was measured. `job_admission` subtracts a node clock
  from a driver clock, so D11's preflight skew probe is load-bearing, and a negative admission must
  be reported as negative, never floored at 0.
- **The local suite stays green through every remote-only bug.** Green tests are necessary and not
  sufficient here; the spec's tests exist to pin contracts, not to prove the cluster path works.

## Definition of done
`pytest -q` green (451 passed / 2 skipped at handoff), `ruff check src/ tests/` clean, spec §5's six
deliverables present, and **the script not run by you** — it goes to the operator with §8's
prerequisites (VM inside the project's compute subnet, `az login`, `--dry-run` first).

## Explicitly NOT in scope
- TODO #61 **(b)** threaded metadata reads and **(c)** batched STAC writes. Fix (a) landed
  2026-07-28; (b)/(c) are the bigger halves (~410 s and ~161 s of a 2067 s run) but they are
  independent of spec 40 and want their own review. Do not fold them in.
- TODO #62 (re-run the local demo), TODO #59 (cluster sizing), TODO #55 (the docs refactor).
- Run-book 42 — **superseded, do not run.**
- Rewriting `demos/E2E_AUSTRIA_AML.md`. That happens when the operator returns a `timings.json`,
  per spec §7 (rewrite around the VM run; laptop evidence demoted to a labelled appendix).

## Git state at handoff
`main` = `73183ba` + this session's uncommitted work (the #61 fix + its 3 tests, TODO #61/#62,
run-book 42's superseded banner, PROGRESS, this file). **Two commits are unpushed**: `616650b`
(timing report, TODO #60/#61, run-books 41/42) and `73183ba` (spec 40, ADR 0021, glossary).
