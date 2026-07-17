# Run-book: spec 33 — MPC reprocessing dedup, proven on live MPC data

> Spec 24 template. A run-book is what Claude hands the user instead of running a
> pipeline/long/networked script itself. The user runs the commands and pastes back the
> `_result.json`; Claude diffs it against the success criteria below.

> **Why this exists even though spec 33 says "no runbook needed."** The spec is right that the
> logic is fully covered by synthetic pytest (8 tests, all verified non-vacuous by a mutation test
> at Opus review). What pytest *cannot* prove is the one thing this fix rests on: that
> **`s2:generation_time` is really populated on the live MPC items** for the exact duplicate pair
> that started this, and that `query_catalog` really collapses it **in the real world** — the fake
> items in `tests/test_mpc.py` have that property because *we put it there*. This run-book closes
> that gap. It is **discovery-only: zero bytes of imagery are downloaded** (~kilobytes of STAC
> JSON, a few seconds) — unlike runbook 32's ~320 MB.

## Handoff checklist (before starting a fresh session)
- [x] Claude has flushed durable state to `fsd/PROGRESS.md`.
- [ ] Fresh session started; model/effort set for the verifying session (Opus/high to diff the
      pasted `_result.json` against this doc).

## Purpose
Prove on **live MPC traffic** that spec 33's dedup fires on the real duplicate acquisition found
by runbook 32 (`20220301T100029` / `T33UWP`, served twice: original `20220303T182540` +
reprocessing `20240604T180322`), that the winner is the later processing, and that the loser's
bytes are never queued. Also empirically checks the one soft finding from the Opus review: that
live `s2:generation_time` values share a **single uniform RFC-3339 format** (the tie-break compares
them as strings).

## Prerequisites
- venv: `fsd/.venv` with `[dev,mpc]` extras (already installed if you ran runbook 32).
- creds: **none** — MPC discovery is anonymous.
- free disk: **~0**. Nothing is downloaded. No `download()` call is made anywhere in this run-book.
- network: a real connection, but **hotspot-trivial** (a few STAC API calls, kilobytes).
- ROI: `../shapefiles/s2grid=476da24.geojson` (the single-MGRS-tile Austria ROI covering T33UWP —
  the same ROI runbook 32 used when it surfaced the duplicate).

ℹ️ **The code under test is now on `main`** (spec 33's implementation was merged out of the
worktree `spec33-docs-update` at the Opus review, 2026-07-16). `fsd/.venv`'s editable install
points at `main`'s `src/`, so this run-book needs **no `PYTHONPATH` juggling** — just the normal
venv. **Step 0 still exists to make a wrong-code run impossible** — do not skip it.

## Setup
**None.** No env vars, no arguments — the probe derives its own paths. (v1 of this run-book used
`export OUT=...` + a heredoc; when the export didn't survive into a fresh shell it silently wrote
nothing, and the run produced no `_result.json` at all. That whole pattern is gone — the probe is
now a committed script.)

## Steps

### Step 1 — run the probe (discovery only, no downloads)
```bash
cd /Users/nikhilsrajan/NASA-Harvest/project/fetch_satdata_claude/fsd
.venv/bin/python runbooks/scripts/33_probe_dedup.py
```
That is the whole run. It prints the result JSON and writes
`tests/outputs/spec33_dedup/_result.json` (gitignored).

- **Expect:** a JSON dump with `"pass": true`, `duplicate_groups_upstream: 1`, a
  `duplicate_group_ids` entry listing **both** `..._20220303T182540` and `..._20240604T180322`,
  `catalog_row_count` **one less than** `raw_item_count`, `known_winner_present: true`,
  `known_loser_present: false`, and `generation_time_format_shapes` containing exactly one entry
  (e.g. `["NNNN-NN-NNTNN:NN:NN.NNNNNNZ"]`).
- **PASS if:** `_result.json` has `"pass": true` (exit code 0).
- **The script always writes `_result.json`** — even on a hard failure (bad import, missing ROI,
  wrong code loaded). If something breaks, the file will contain `"status": "fail"` and the
  traceback tail in `error`. **Paste the file either way**; there should never be a situation where
  it doesn't exist. If it genuinely doesn't, the script prints the JSON to stdout as a fallback —
  paste that.
- **If `status` is `inconclusive`:** **not** a failure — it means MPC fixed the duplicate upstream
  and live data can no longer exercise dedup. Paste it back anyway; we record it and fall back to
  the synthetic tests as the guarantee.
- **If it hangs:** Ctrl-C is safe — nothing is downloaded.

Step 0 of v1 (a separate "is the right code loaded?" check) is now **built into the probe**: it
raises `WRONG CODE: ...` before touching the network if `_dedupe_reprocessed_items` is absent, and
reports `mpc_module_loaded_from` in its metrics so the loaded path is visible in the result.

### Step 2 — the synthetic suite, for the record
```bash
.venv/bin/python -m pytest -q tests/test_mpc.py
```
- **Expect:** `19 passed`.
- **PASS if:** 19 passed, 0 failed.

## Success criteria (`_result.json`)
```json
{ "step": "spec33-live-dedup", "status": "ok", "pass": true,
  "metrics": { "duplicate_groups_upstream": 1, "catalog_row_count": 0, "known_loser_present": false },
  "expected": { "known_loser_present": false },
  "error": null }
```
The run passes when step 1's `pass` is `true` **and** step 2 is `19 passed`. **Paste
`tests/outputs/spec33_dedup/_result.json` back** (not the logs).

## Stop / observe
- Runtime: seconds. No progress line needed; no ETA to report.
- Abort: Ctrl-C. Nothing is downloaded, so there is nothing to clean up or resume.
