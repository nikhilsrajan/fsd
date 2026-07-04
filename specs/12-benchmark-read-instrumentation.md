# Spec 12 — Datacube throughput benchmark · Part 2: per-read instrumentation

> **Status: signed off + implemented (2026-07-04).** Builder `write_read_log` +
> `reads.jsonl`, harness `--read-log` with `conflict_stats` / `duration_vs_concurrency`
> (instantaneous peak-in-flight concurrency), 4 read plots + report/stats block, unit +
> smoke tested. Full 100-grid `--read-log` run produces the real same-file/different-file
> verdict. See `CHANGES.md`.


Part 2 of the 3-part effort against the datacube-creation bottleneck:
- Part 1 (spec 11, DONE): parallelism-sweep harness → baseline. Finding: throughput knees at
  `cores=4`; per-grid `load_images` slows **2.41 s → 9.07 s (3.76×)** as parallelism rises →
  I/O read contention is *inferred* to be the bottleneck.
- **Part 2 (this spec):** log every individual windowed read and *directly prove or disprove*
  the "parallel reads block each other" hypothesis — turn the inferred `load_images` slowdown
  into a measured **read-duration-vs-concurrency** curve, a **read-conflict count**, and a
  **same-tile-vs-different-tile** split. **Minimal read-path touch; layers onto the Part-1 sweep.**
- Part 3 (spec 13, later): tile-splitting experiment (the candidate fix), validated by re-running
  Parts 1 & 2 and diffing.

## Goal
Answer the user's original question — *"how many read conflicts happened, and did they cause the
`load_images` slowdown?"* — with a **real measurement**, not an inference. Concretely, produce:
1. a **read-conflict count** per `cores` setting (pairs of reads from different grids whose
   wall-clock intervals overlap), and
2. a **read-duration-vs-concurrency curve** (does the *same* windowed read take longer when more
   reads run at once?) — the direct test of the hypothesis, and
3. a **same-file / same-MGRS-tile / different-tile** breakdown of those conflicts (which kind of
   contention dominates → informs whether Part-3 tile-splitting will actually help; only the
   **same-file** kind is what tile-splitting eliminates).

### Three identifiers — do not conflate (the unit of a "conflict")
The read path exposes three nested identifiers; a conflict must be keyed on the right one:
- **MGRS tile** (e.g. `36NXF`) — geographic location, **the same across all acquisition dates**.
  Coarse: many physical files share it. *Not* a same-file key.
- **SAFE product id** — unique per **(MGRS tile × acquisition datetime)** = one product folder
  (`local_folderpath`). Still holds multiple band files.
- **filepath** = `<product folder>/<band>.jp2` — unique per **(product × band)** = **one physical
  file**. This is the real same-file key.

Two grids overlapping the same MGRS tile request the *same acquisitions* of it, so they open the
**identical** `B08.jp2` → a true **same-file** conflict (shared page cache / GDAL handle / seek on
one file). Two grids on the same MGRS tile but colliding on *different* acquisitions or *different*
bands touch **different** physical files (co-located, but not same-file). Two grids on different
MGRS tiles are fully disjoint. Every logged read therefore carries **all three** (`mgrs_tile`,
`product_id`, `filepath`), and each overlapping pair is classified:
- **same-file** — identical `filepath` (same product **and** band). ← *the only kind Part-3
  tile-splitting removes* (disjoint grids stop colliding on one big file).
- **same-tile, different-file** — same `mgrs_tile`, different `filepath` (diff acquisition/band).
- **different-tile** — different `mgrs_tile` entirely (pure disk-bandwidth contention).

This is **reusable**, layered onto the existing sweep: it does **not** run its own separate sweep —
it enriches every `cores` run of the Part-1 harness with a read log, so concurrency varies naturally
from `cores=1` (≈none) to `cores=10` (heavy) and the curve falls straight out.

## What one read is (the unit we log)
The only disk reads during `build_datacube` happen in the **`load_images` phase**: `_load_images`
→ `images.load_images(njobs=1)` → one `crop_tif` per `(tile, band)` file = one **windowed
`rasterio.open` + `mask.mask`** (never a full-tile read; CLAUDE.md constraint). Reference-merge,
resample, stack, ops all run on already-in-memory `(data, profile)` — **no further disk reads**. So
the read log for a grid = exactly its `load_images` reads, and `sum(read durations) ≈
load_images_seconds`. That equivalence is a built-in self-check.

Within one grid the reads are **serial** (`njobs_load_images=1`), so **two overlapping reads always
come from two different grid processes** — every overlap is a genuine cross-process parallel read.
This clean property is why concurrency = "how many grids are mid-read right now".

## One small enabling change (the only library touch)
`datacube.builder.build_datacube` gains a **`write_read_log: bool = False`** flag (off by default →
no behavior change, no extra file), mirroring the existing `write_timings` seam:
- When set **and** `njobs_load_images == 1`, `_load_images` times each `load_image` call with
  **`time.time()`** (epoch wall clock — *must* be wall clock, not `perf_counter`, so intervals are
  comparable **across processes**) and appends one row per read to a **`reads.jsonl`** sidecar next
  to `datacube.npy`:
  ```json
  {"id": "<grid id>", "mgrs_tile": "36NXF", "product_id": "S2A_..._20180601T...",
   "band": "B08", "filepath": ".../<product>/B08.jp2",
   "start": 1751630400.123, "end": 1751630400.842, "duration": 0.719}
  ```
- `mgrs_tile` = the `..._T<tile>...` substring (same rule the harness already uses); `product_id` =
  the product-folder basename (`local_folderpath`), unique per (tile × datetime); `filepath` = the
  physical file. All three are logged so the analysis can classify conflicts at the correct
  granularity (see "Three identifiers" above) — the same-file key is `filepath`, **not** `mgrs_tile`.
- The workflow enables it **without runner/Snakefile plumbing** via a new `FSD_WRITE_READ_LOG=1`
  env var, read in `workflows.task.main` alongside `FSD_WRITE_TIMINGS` and passed through; task
  subprocesses inherit it from the harness. (Same mechanism as spec 11.)
- **Limitation (documented, accepted):** if `njobs_load_images > 1` the per-grid reads themselves
  fan out into a `Pool` and the simple in-process log would miss them, so read-logging is a no-op in
  that mode. The sweep uses `njobs_load_images=1` (parallelism is at the grid/process level via
  Snakemake), so this never bites the benchmark. Noted so nobody expects it to work otherwise.

No change to generic `fsd.raster.images` signatures — the timing loop lives in `builder._load_images`
(the file whose comment already says it "scrutinises the read phase"), on the logging path only.

## Harness additions (Part-2 layer on `datacube_throughput_sweep.py`)
Off by default; enabled with a new `--read-log` flag (or `FSD_WRITE_READ_LOG=1`). When on, for each
`cores` run the harness sets the env var, runs the sweep exactly as today, then **collects every
grid's `reads.jsonl`** into one global, wall-clock-aligned list and computes:

- **Concurrency timeline** — sweep the merged read intervals; at each read's start count how many
  other reads (necessarily other grids) are in flight → each read tagged with a `concurrency` value
  (and the interval's mean concurrency). Report max / mean concurrency per `cores`.
- **Read conflicts** — total count of overlapping read *pairs* (different grids). This is the
  literal "how many read conflicts happened" number, per `cores`.
- **Read-duration-vs-concurrency curve** — bucket reads by concurrency → **mean/median read
  duration per bucket**. Rising duration with concurrency = processes wait on each other = the
  hypothesis **confirmed**; flat = something else (revisit). This is the headline plot.
- **Conflict classification (three-way)** — for each overlapping pair, classify by the identifiers
  above: **same-file** (identical `filepath`), **same-tile-different-file** (same `mgrs_tile`, diff
  `filepath`), or **different-tile**. Report all three counts and the duration curve split by class.
  **Only same-file overlaps** stress one physical file (page cache / GDAL handle / seek) and are what
  Part-3 tile-splitting eliminates; same-tile-different-file and different-tile are disk-bandwidth
  contention that splitting does **not** fix. This split is the number that predicts Part-3 payoff:
  if conflicts are overwhelmingly *different-file*, tile-splitting won't help much and we'd redirect
  Part 3.
- **Self-check** — per grid, `sum(read durations)` vs the `timings.json` `load_images` value; they
  should track. Flag large drift (would mean untimed I/O somewhere).

All read-analysis functions that do arithmetic on intervals (`conflict_stats`,
`duration_vs_concurrency`, tile-parse) are **pure** and unit-tested on synthetic intervals — no
raster or subprocess needed.

## Report additions — same living `benchmarks/datacube_throughput_report.md`
A new **"Read contention (Part 2)"** section, only populated when the run had `--read-log`:
- table `cores → #reads, #conflicts, max/mean concurrency, mean read duration`;
- the **read-duration-vs-concurrency** curve (the money plot) + the three-way class split;
- a concurrency-over-time strip for the busiest `cores` run;
- one-paragraph verdict: *is the Part-1 `load_images` slowdown explained by read concurrency, and is
  it **same-file** (→ tile-splitting helps) or different-file/different-tile disk-bandwidth
  contention (→ tile-splitting won't)?* — the sentence Part 3 acts on.
Plus the machine-readable numbers into the existing `*_stats.json` (new `read_contention` block) so
Part-3's before/after diff includes conflict counts, not just wall-time.

## Cache handling — measure, don't force (unchanged from spec 11)
Warm-as-is, **no `sudo purge`**. Part 2 is precisely the tool that *starts* to separate cache from
contention: a **same-file** overlapping read that is *faster* than baseline suggests cache reuse (two
processes hitting the same warm `B08.jp2`); one that is *slower* suggests contention on that file.
The three-way class duration split is the first quantitative cut at that separation. A deliberate cold-vs-warm A/B is still **out** (a later systematic experiment).

## Explicitly OUT (deferred)
- Any **fix** for contention — tile-splitting is **Part 3 (spec 13)**; this spec only *measures*.
- `njobs_load_images > 1` read-logging (Pool-level capture) — not needed for the sweep.
- Forced cold-cache A/B and any per-syscall / `iostat`-level tracing — later, if the JSONL-level
  measurement proves insufficient.
- Azure/Batch (this characterizes the local machine).

## Reusability
The `reads.jsonl` seam and the pure analysis functions are permanent; re-runnable with `--read-log`;
enriches the one living report + `stats.json` baseline. After a Part-3 change, re-run with
`--read-log` and diff `read_contention` (fewer/lighter same-tile conflicts = the fix worked).

## Validation
- Unit tests (pure, synthetic intervals): `conflict_stats` (overlap-pair count, max/mean
  concurrency), `duration_vs_concurrency` (bucketing/means), the three-way conflict classification
  (same-file / same-tile-diff-file / different-tile), and the `mgrs_tile` + `product_id` parse from a
  filepath. Plus a builder test: `write_read_log=True` writes a well-formed `reads.jsonl` whose row
  count == number of band files read, carries all three identifiers, and durations ≥ 0; off by
  default writes nothing.
- Smoke: harness on a 3-grid subset, `cores=[1,2]`, `--read-log` → report gains a populated Read
  contention section + stats block, no error.

## Manual runbook
Extend `tests/manual/throughput_benchmark.md` with the `--read-log` variant: how to enable it, the
extra outputs (`reads.jsonl` per grid, the new report section + plots), how to read the
duration-vs-concurrency curve and the three-way (same-file / same-tile / different-tile) split, and
the self-check.
