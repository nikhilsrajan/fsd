# Spec 26 — safe download runner (`--dry-run`/`--stop-file`/progress) + measured confirm-run

> **Status: SIGNED OFF (2026-07-11) — awaiting implementation.** Opus@high (interview → spec).
> **C1–C6 all accepted as drafted** (generic `should_stop` predicate; standalone
> `python -m fsd.sources.download_cli`; `--dry-run` touches zero band bytes; exit 0 on clean
> completion *or* user stop; `_fmt_progress` gains shared rate+ETA; tiny 1-MGRS-tile confirm-run).
> Interview decisions locked: **D1** deliver both the safe-runner CLI *and* the measured
> real-CDSE confirm-run (one spec); **D2** the runner is a thin **CLI wrapping
> `download_resume`** (not a Snakemake unit-of-work — the download stage stays off the
> workflow layer for now); **D3** `--stop-file` is checked **mid-pass, in `download()`'s
> submit loop** (halt new work within seconds, in-flight transfers drain); **D4** the
> confirm-run is the **tiny 1-MGRS-tile** Austria slice (~7 granules / ~2 GB). Builds on
> spec 25 (transfer/convert split) + spec 25b (exception-safe callbacks, no hang) — this is
> the **first real CDSE network exercise** of that pipeline. Implementation lands in a
> **Sonnet@medium** session against this spec (spec 24 D5). Claude (Opus) does **not** run
> the confirm-run — it is a **runbook** the user runs (spec 24), pasting back `_result.json`.
>
> **⚠️ Deliberate pause point (mobile-hotspot constraint, 2026-07-11).** This spec's two halves
> are separated by a network seam. The **offline half** — the CLI, the `should_stop` seam,
> `DownloadResult.stopped`, the `_fmt_progress` ETA, all pytest (monkeypatched, no bytes), the
> docs, **and the fully-written runbook `.md` itself** — is implemented + reviewed with no
> network. The **network half** — runbook **step 2 onward** (the real download → integrity →
> report) — is **not run by this project's normal sessions**; the user runs it only when on a
> real (non-hotspot) connection. So after 26 is implemented + reviewed, we **hand off + clear**;
> the confirm-run happens in a later session when the user is available, and whichever session
> verifies the pasted `_result.json` diffs it against the runbook's **self-contained `expected`
> block** (never against this conversation's memory — see §5).

## Motivation

Spec 25 rebuilt `download()` into a transfer-thread-pool → convert-process-pool pipeline; spec
25b made its callbacks exception-safe so a dead pool / write error can no longer hang it. What's
still missing is the thing spec 24 demands before *any* long, networked, side-effecting run: a way
to **start it, watch it, and stop it safely** — and then the actual measured run that proves the
pipeline works against real CDSE traffic and quantifies the transfer-vs-convert split (spec 25's
whole reason to exist, so far only reasoned about, never measured).

Today a real download is driven ad-hoc (`demos/e2e_austria.py`, or a bare `download_resume` call).
There is no `--dry-run` preview a user can eyeball before committing GB + quota, no clean
**stop** (only Ctrl-C, which can strand `.part`/`.src.jp2` staging and doesn't drain in-flight
transfers), and no machine-readable result for the spec-24 paste-back protocol. This spec adds a
small CLI over the existing `download_resume` and a runbook for the first real run.

## Non-goals (explicitly out)

- **No new download *engine*.** All resilience already exists (`download_resume` loop, circuit
  breaker, `pool_broken` clean-stop, atomic `.part`+rename, idempotent skip). This spec is a
  **driver + a stop seam + a runbook**, not a rewrite. `_transfer_one`/`_convert_one`/`to_cog`/
  discovery/the breaker are untouched.
- **No Snakemake / runner-seam integration for download** (D2). Batch-dispatching the download as
  a unit-of-work is a later phase (P1/P4); this CLI is the local driver. (When that lands it can
  reuse the same `should_stop`/result-json contract.)
- **No auto-fetch from the compute verbs.** `create_training_data`/`run_inference` still never
  download (quota + Batch download-once model); this CLI is the explicit, user-run fetch.
- **No cost-model calibration deliverable.** The confirm-run *reports* the transfer/convert split
  and probe-vs-aggregate MB/s; turning those into a persisted `cost_model` for `plan_download`'s
  ETA is follow-up (TODO), not this spec.

## Design

### 1. A `should_stop` seam on `download` / `download_resume` (D3 — the stop mechanism)

The stop mechanism is a **generic predicate**, not a hard-coded stop-file — keeps `download()`
decoupled from any filesystem convention and reuses the exact machinery spec 25b built for
`tripped`/`pool_broken`.

- **New kwarg `should_stop: Callable[[], bool] | None = None`** on `download()` (and pass-through
  on `download_resume`). Defaults `None` → today's behavior exactly (backward compatible).
- In `download()`'s **submit loop**, check it alongside the existing flags, at both existing
  checkpoints — top-of-loop and post-`sem_staged.acquire()`:
  ```python
  if state["tripped"] or state["pool_broken"] or _stop():   # _stop() = should_stop and should_stop()
      break
  ```
  where `_stop()` is a tiny local that (a) short-circuits when `should_stop is None`, (b) throttles
  the predicate to at most once per `config.PROGRESS_EVERY_S` (cache the last value + timestamp in
  `state`) so a filesystem `os.path.exists` isn't stat-ed per granule. On the first `True`, set
  `state["stopped"] = True` (under `lock`) so it's sticky and surfaced.
- **Semantics = exactly `tripped`/`pool_broken`:** stop halts **new** submissions only; every
  already-submitted transfer (and its chained convert) finalizes normally through the leak-proof
  spec-25b callbacks, then `all_done` fires and the pools shut down cleanly. A stopped item is
  *never attempted* → **not** a failure, not in `failures`, not counted in `total_count` (identical
  to a tripped item). `.part`/`.src.jp2` staging is cleaned by the same `finally` paths as always.
- **`DownloadResult.stopped: bool = False`** — additive, defaulted (backward compatible). `download`
  sets it from `state["stopped"]`; `sum_results` ORs it across passes (one-liner, like
  `circuit_tripped`/`pool_broken`).
- **`download_resume`**: pass `should_stop` through to each pass **and** add an explicit
  `if r.stopped: break` to the loop (a user stop ends the resume loop immediately — it is neither a
  bad-window cooldown nor a completion). Check `should_stop()` once before starting each new pass too,
  so a stop between passes doesn't launch another.

### 2. The CLI — `python -m fsd.sources.download_cli` (D2)

New module `src/fsd/sources/download_cli.py` (a `main(argv=None)` + `if __name__ == "__main__"`),
mirroring the `python -m fsd.workflows.task` convention. It **only** parses args, builds the
`should_stop` closure, calls `download_resume`, and writes the result JSON — no download logic of
its own.

**Args** (argparse):

| flag | meaning |
|---|---|
| `--roi PATH` | ROI GeoJSON (required) |
| `--start YYYY-MM-DD` / `--end YYYY-MM-DD` | date window (required) |
| `--bands B04 B08 …` | band list (required) |
| `--dst PATH` | root download folder (required) |
| `--catalog PATH` | catalog parquet (required) |
| `--creds PATH` | CDSE credentials json (default `$CDSE_CREDENTIALS_JSON`) |
| `--max-tiles N` | required guardrail (as `download`) |
| `--max-cloudcover F` | optional |
| `--dry-run` | print the plan (metadata only, **zero band bytes**) and exit 0 |
| `--stop-file PATH` | when this file appears, stop cleanly (touch it to stop) |
| `--max-passes N` | default 10 |
| `--no-cog` | keep native JP2 (default converts to COG) |
| `--max-convert-procs N` / `--max-staged N` | optional pass-through (default auto) |
| `--result-json PATH` | write the spec-24 `_result.json` here (default `<dst>/_result.json`) |
| `--expected-json PATH` | runbook success criteria echoed into the result `expected` block (§4) |
| `--quiet` | suppress the live progress + startup lines (default: on) |

- **`--dry-run`** → `plan_download(...)` + `format_download_plan(...)` printed; **no `probe_throughput`**
  (a probe transfers a real band file — a dry-run must touch **zero** band bytes; only the anonymous
  STAC query runs). Writes a result-json with `status="dry-run"`, `metrics` = the plan counts. Exit 0.
- **Real run** → optional single `probe_throughput` at the start (baseline MB/s for the report;
  gated by `--quiet`? no — always, it's one file and central to the confirm-run's purpose; make it
  skippable with `--no-probe` for re-runs), then `download_resume(..., should_stop=_stop_from_file)`,
  then `sum_results` → write result-json. `_stop_from_file = (lambda: os.path.exists(stop_file))` when
  `--stop-file` given, else `None`.
- **Exit code**: 0 on clean completion (nothing failed) or a user stop; **non-zero** if the aggregate
  has `failed_count > 0` after `max_passes`, or `circuit_tripped`, or `pool_broken` unresolved — so a
  runbook step's PASS/FAIL is the process exit code *and* the result-json, per spec 24.

### 3. Progress + ETA (memory: long-process-progress)

`download` already prints `_fmt_progress` every `config.PROGRESS_EVERY_S`. Extend `_fmt_progress`
(additive, keeps its existing fields) to append **rate + ETA** derived from `done/total` and elapsed:
`… | 12.3 files/min | ETA ~7m`. ETA is omitted (shown as `ETA ~?`) until `done > 0`. This is the one
`src/fsd/` line-format change; it flows to every caller (demos included). The CLI prints a final
one-line summary from the summed result (successful/failed/skipped, GB, transfer_s vs convert_s,
probe vs aggregate MB/s, stopped/tripped/pool_broken).

### 4. The `_result.json` shape (spec 24 paste-back)

```json
{
  "step": "download-confirm-run",
  "status": "ok | dry-run | stopped | failed",
  "pass": <n_passes_run>,
  "metrics": {
    "needed": .., "present": .., "missing": ..,          // dry-run + real
    "successful": .., "failed": .., "skipped": ..,        // real only
    "gb": .., "transfer_s": .., "convert_s": ..,
    "probe_mb_per_s": .., "aggregate_mb_per_s": ..,
    "elapsed_s": .., "stopped": false,
    "circuit_tripped": false, "pool_broken": false
  },
  "expected": { "...": "the runbook's success criteria, echoed for the diff" },
  "error": null
}
```
`aggregate_mb_per_s = bytes_downloaded / transfer_seconds` (effective transfer rate); comparing it to
`probe_mb_per_s` is the transfer-contention diagnostic (spec 23 D2). `status="stopped"` when the run
ended on the stop-file; `"failed"` when the exit is non-zero.

- **`expected`** = the CLI's universal success invariants (`failed=0, stopped=false,
  circuit_tripped=false, pool_broken=false`, real run only) merged with the runbook's run-specific
  criteria from `--expected-json` — so the pasted result is self-contained for the diff.
- **`error`** = a short reason on a non-exception `status="failed"`. If the run *raises* (network /
  creds / disk), the CLI still writes a `status="failed"` result with `error=repr(exc)` before
  re-raising, so the runbook flow always has a result to paste.
- **Three throughput rates** (don't compare the wrong pair): `probe_mb_per_s` = one stream, wall;
  `aggregate_mb_per_s` = bytes / thread-summed transfer_s = per-stream rate under concurrency (compare
  to probe: ≪ ⇒ streams contend); `wall_transfer_mb_per_s` = bytes / wall transfer span = effective
  all-streams rate (≥ probe ⇒ concurrency helped). `--max-concurrent-s3 N` sweeps the stream count.

### 5. The confirm-run runbook — `runbooks/26-download-confirm-run.md` (D4)

Template = `runbooks/TEMPLATE.md`. Target = the **tiny 1-MGRS-tile Austria slice** (the
`demos/e2e_austria.py::_single_tile_roi` logic: a small box at the dominant MGRS tile's ROI-overlap
centroid, clipped to that one tile → ~7 granules / ~2 GB, single UTM-33). Steps:

0. **Preflight** — creds present (`$CDSE_CREDENTIALS_JSON` readable), venv, free disk ≥ ~5 GB, write
   the tiny-slice GeoJSON (reuse the demo helper or a tiny inline script in the runbook).
1. **Dry-run** — `python -m fsd.sources.download_cli --dry-run …`. PASS = `missing_count` ≈ 7 (one
   tile × bands), plan printed, **zero bytes** transferred, exit 0.
2. **Real download w/ stop armed** — same command without `--dry-run`, with `--stop-file /tmp/fsd.stop`
   and `--progress`. PASS = exit 0, `successful == missing`, `failed == 0`, `stopped == false`,
   progress lines with ETA appeared. (Runbook documents: `touch /tmp/fsd.stop` to stop; expect a clean
   drain within seconds, `.part`/`.src.jp2` all gone.)
3. **Integrity** — every requested band present as `Bxx.tif` (COG w/ overviews) under `<dst>`, catalog
   has the tile rows, no `.part`/`.src.jp2` left. PASS/FAIL scripted (reuse the spec-23 integrity
   check style).
4. **Report** — read `_result.json`; record transfer_s vs convert_s split and probe vs aggregate MB/s.
   This is the measurement spec 25 was built to produce. No hard PASS threshold (first baseline) —
   just captured; a wild probe≫aggregate gap is flagged for follow-up.

The user pastes each step's `_result.json`; Claude (Opus) diffs it vs the runbook's success criteria
(never reads live logs — spec 24). A **stop drill** (start step 2, `touch` the stop-file mid-run,
confirm clean stop + resumability on re-run) is an explicit optional step.

## Test plan — `pytest` only (Claude may run it; **no network**)

All use monkeypatched `_search_items`/`_select_item_files`/`fs.transfer` (as the spec-25/25b tests do)
+ the watchdog-thread helper for no-hang.

1. **`should_stop` halts the submit loop mid-pass.** Injected multi-item work; `should_stop` returns
   `True` after the first item is finalized (e.g. flips a flag from a transfer stub, or a counter).
   Assert: `download` returns (watchdog), `result.stopped is True`, `total_count < len(work)` (stopped
   early), every attempted item accounted (`successful + failed == total_count`), no leaked permit.
2. **`should_stop=None` is a no-op** — regression: a normal run with the default finishes all work,
   `stopped is False`.
3. **`download_resume` breaks on a stopped pass** — a `should_stop` that trips on pass 1; assert only
   one pass ran and the returned list's last result has `stopped True`; no cooldown taken.
4. **`sum_results` ORs `stopped`** (extend the aggregation test).
5. **CLI dry-run** — `download_cli.main([...])` with `--dry-run` and a monkeypatched `plan_download`;
   assert it prints the plan, writes a `status="dry-run"` result-json, transfers **zero** bytes
   (`fs.transfer` monkeypatched to fail the test if called), exit code 0.
6. **CLI real path wiring** — `main([...])` (no `--dry-run`) with a monkeypatched `download_resume`
   returning a canned result; assert the result-json shape/fields and the exit code mapping
   (0 on clean, non-zero on `failed_count>0`). Also `--stop-file` builds a predicate that reads the
   file (create the file → predicate True).
7. **`_fmt_progress` ETA** — unit-test the new rate/ETA formatting (done=0 → `ETA ~?`; done>0 → a
   finite ETA), and that existing fields are unchanged (the spec-23 progress assertions still pass).
8. **Regression:** all 47 `test_cdse.py` tests still pass unchanged; `ruff check` clean.

## Docs to update on implement

- **`CHANGES.md`** — new entry: safe download CLI (`python -m fsd.sources.download_cli`) with
  `--dry-run`/`--stop-file`/progress-ETA; additive `should_stop` on `download`/`download_resume` +
  `DownloadResult.stopped`; `_fmt_progress` gains rate+ETA.
- **`RECIPES.md`** — the exact dry-run and real-run CLI commands (they're the reusable download driver).
- **`runbooks/26-download-confirm-run.md`** — new (the confirm-run + optional stop drill).
- **`README`** — a one-line pointer to the download CLI under the download quickstart.
- **`PROGRESS.md`** + memory `fsd-status` — spec 26 landed; next = the confirm-run result, then P1.
- **`TODO.md`** — "persist the confirm-run's transfer/convert split as a `cost_model` for
  `plan_download` ETA" (follow-up).

## Explicitly OUT (deferred)

- Persisting a calibrated `cost_model` from the confirm-run (TODO above).
- Snakemake/Batch dispatch of the download unit-of-work (P1/P4 — reuses this `should_stop`/result-json
  contract).
- A pause/resume (as opposed to stop) control; `SIGTERM`/`SIGINT` handler wiring (the stop-file is the
  one stop mechanism this spec ships; Ctrl-C stays as-is).
- Any change to `_transfer_one`/`_convert_one`/`to_cog`/discovery/the circuit breaker/`pool_broken`.

## Confirm at sign-off

- **C1 — the stop seam is a generic `should_stop` predicate** (§1), checked mid-pass at the two
  existing submit-loop checkpoints, throttled to `PROGRESS_EVERY_S`, with additive
  `DownloadResult.stopped` and a `download_resume` `if r.stopped: break`. Agree, or prefer a concrete
  `stop_file: str` kwarg baked into `download()` (simpler signature, but couples the engine to the
  filesystem convention)?
- **C2 — the runner is a standalone CLI** `python -m fsd.sources.download_cli` wrapping
  `download_resume` (§2), not wired to the workflow/runner seam. Good, or would you rather I put it at
  a different entrypoint (e.g. a top-level `python -m fsd.download` or a `console_scripts` entry)?
- **C3 — `--dry-run` touches zero band bytes** (§2): plan via `plan_download` only, **no**
  `probe_throughput`. The probe (one real band file) runs only on the real path (skippable with
  `--no-probe`). OK?
- **C4 — exit code doubles as the runbook PASS/FAIL** (§2): non-zero on `failed_count>0` after
  `max_passes` / `circuit_tripped` / unresolved `pool_broken`; 0 on clean completion **or** a user
  stop. Good, or should a user stop be non-zero (distinguishable from "finished clean")?
- **C5 — `_fmt_progress` gains rate + ETA** (§3), one additive line-format change flowing to all
  callers (demos included). OK, or keep `_fmt_progress` frozen and print ETA only from the CLI's own
  pass-summary line?
- **C6 — the confirm-run is the tiny 1-MGRS-tile slice** (§5, D4) as a runbook, with an optional stop
  drill. Good, or want the medium multi-tile run folded in as a second runbook step?
