# Spec 11 — Datacube throughput benchmark · Part 1: parallelism-sweep harness

Part 1 of a 3-part effort against the datacube-creation bottleneck:
- **Part 1 (this spec):** a reusable harness that measures how throughput scales with
  parallelism over a fixed geometry set, and emits a baseline report. **No read-path changes.**
- Part 2 (spec 12, later): per-read instrumentation → parallel-reads / duration-vs-concurrency.
- Part 3 (spec 13, later): tile-splitting experiment (the candidate fix).

## Goal
A **reusable, re-runnable harness** answering: *how does the total time to build N datacubes
change as we add parallel build processes, and where does the time go per step?* The first run
is the **baseline** we re-run to measure every future speedup. Optimal-`cores` falls out of it;
it is not the point.

## Inputs
- grids: `shapefiles/100_random_grids.geojson` (id col `id`) — one datacube per grid.
- catalog: `satellite_benchmark/sentinel-2-l2a/catalog.parquet`.
- window / bands / mosaic_days / scl_mask_classes — `B04,B08,B8A,SCL`, 20-day, standard SCL
  classes. **Window defaults to a short representative slice** `2018-06-01 → 2018-07-10`
  (~16 acquisitions) so the 100-grid × 6-`cores` sweep runs in ~tens of minutes; a full year
  would be hours. Configurable.
- sweep: `cores` list (default `[1,2,4,6,8,10]`); grids = all 100; optional `n_grids` subset +
  `repeats`.

## What it does
1. **Characterize (static, no raster reads):** per grid → # tiles it intersects (per
   acquisition) + total band-files it will read; **grid×tile overlap** → per tile, how many
   grids touch it (= *potential* shared reads / how heavy each grid is). Saves a JSON.
2. **Sweep:** for each `cores`, run `run_create_datacube` over the grids at that parallelism in
   a fresh run folder; time the whole call (**total wall-time**). Collect **per-grid wall-time**
   (free, from the Snakefile `start.txt`/`done.txt` sentinels) and **per-step timings** (sidecar,
   below).
3. **Aggregate + report** → one living report + a stats JSON for cross-run diffing.

## One small enabling change (the only library touch)
`datacube.builder.build_datacube` gains a **`write_timings: bool = False`** flag (off by
default → normal builds leave no extra file). When set, it times each phase (missing-check ·
load_images · dst_crs · reference-merge · resample · stack · ops · save) and writes a tiny
**`timings.json`** (per-phase seconds + sizing counts) next to `datacube.npy`. The workflow
enables it **without runner/Snakefile plumbing** via the `FSD_WRITE_TIMINGS=1` env var, read in
`workflows.task.main` and passed through to the builder; task subprocesses inherit it from the
harness. (Per-grid wall-time needs no change — the `start.txt`/`done.txt` sentinels carry it.)

## Report contents — `benchmarks/datacube_throughput_report.md`
- Config + machine.
- **Characterization:** #grids, tiles-per-grid distribution, hottest tiles / overlap (how
  shareable the reads are).
- **Throughput vs parallelism:** table `cores → total wall-time, throughput (grids/min),
  speedup & efficiency vs cores=1`; the sweet-spot.
- **Where time goes:** aggregate per-phase time, and specifically **how `load_images` time /
  fraction grows with `cores`** — the contention signal that motivates Part 2.
- **Per-grid:** wall-time vs #tiles (which grids are heavy).
- Plots (matplotlib): throughput-vs-cores, per-phase breakdown, load_images-vs-cores.

## Cache handling — measure, don't force (decided)
Run warm-as-is; **no `sudo purge`**. Report the cache caveat honestly: re-running the *same*
grids across settings can warm shared windows, though mostly-disjoint windowed reads limit reuse.
`repeats` (+ optional randomized `cores` order) can average residual warmth. Disentangling cache
vs contention precisely is Part 2's job (per-read timings).

## Explicitly OUT (deferred)
- Per-read logging, parallel-reads count, duration-vs-concurrency → **Part 2 (spec 12)**.
- Tile-splitting → **Part 3 (spec 13)**.
- Forcing cold cache; Azure/Batch runs (this harness characterizes the local machine).

## Reusability
Parametrized + re-runnable; one report regenerated each run; a `*_stats.json` baseline saved so
future optimizations diff against it. Lives in `benchmarks/` (alongside `datacube_year_ethiopia*`).

## Validation
- Unit test: the static grid×tile overlap function on synthetic grids.
- Smoke: harness on a 3-grid subset, `cores=[1,2]` → produces report + stats without error.
