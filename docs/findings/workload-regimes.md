---
status: current
summary: Training-data generation and inference are opposite cluster regimes — 781× more pixels per unit — so one set of fan-out defaults cannot serve both. Measured 2026-07-28.
---

# Finding — training and inference are opposite cluster regimes

**Measured:** 2026-07-28, over run-book 36 Phase 3 (900 training cubes) and run-book 38 Phase 3
(300 inference cells).
**Tracking issue:** [#59](https://github.com/nikhilsrajan/fsd/issues/59). Related: [#61](https://github.com/nikhilsrajan/fsd/issues/61), [#60](https://github.com/nikhilsrajan/fsd/issues/60), [#54](https://github.com/nikhilsrajan/fsd/issues/54), [#48](https://github.com/nikhilsrajan/fsd/issues/48).

> Point-in-time (spec 41 D3). True of the code and the cluster configuration on 2026-07-28.

## The headline

Same verbs, same runner, the same `n_shards` / `cores` / `cubes_per_task` knobs — and per-unit
economics that differ by three orders of magnitude.

| | training units (900 fields) | inference units (300 cells) |
|---|---|---|
| median cube | 14 × 15 px, 13 KB | 597 × 554 px, 21.2 MB |
| whole set | 0.02 GB | 4.13 GB * |
| work per unit | milliseconds of raster work | ~52 s of real work |

**781× more pixels per unit, ~260× more overall.**

\* The 300 inference cubes on blob total **4.13 GB** across 600 `.npy` files (run-book 41 Step 3).
`PROGRESS.md` records **5.48 GB** from the same day; the likeliest explanation is that figure was
taken over the **local** run, whose T=10 axis carries 25 % more data than the cluster's T=8 — but
that is a guess, and one listing would settle it. **The 781× per-unit ratio is unaffected**: it
comes from pixel dimensions, not totals.

## What follows

**Inference is genuinely work-bound**, so a 16-way fan-out earns its keep — and it is well
balanced: 18.75 cells/shard × ~52 s/cell = 975 s predicted against 982.7 s observed, no straggler.
Keep `cores` and `cubes_per_task` small; D7's load-once-per-node already assumes this.

**Training is overhead-bound end to end.** The real cost is per-unit round-trips — `setup`'s 4–7
blob calls per unit (measured 79 ms/unit = 71 s for 900), task startup, catalog reads, bundle
loads. The raster work is nothing. Fanning 900 tiny units across N nodes pays N× container startup
(~100 s cold, see [cloud-overhead](cloud-overhead.md)) to save seconds of compute; the ~1084 s a
16-node dispatch costs would **dwarf the entire 900-unit workload**. At this scale 1–2 nodes with a
large `cubes_per_task` almost certainly beats a 16-way fan-out.

## Also unmeasured: read amplification

Both regimes read the **same whole MGRS-tile COGs** — there are no windowed reads (see
`LIMITATIONS.md`, Data-sources). So training reads ~74 GB of granules to produce 21 MB of cubes: a
**~3500× amplification** that per-unit fan-out does nothing about, but a shared or cached read
would.

## What to do

1. Measure wall-clock vs node count for **each regime separately** and find each one's crossover.
2. Then either (a) pick different runner defaults per verb, or (b) auto-size from the work-unit
   stats `setup` already computes — it knows N and every cell's pixel dimensions before dispatch.
3. **Fix the driver overhead first** ([#61](https://github.com/nikhilsrajan/fsd/issues/61)). No
   fan-out width, node SKU or `cores` setting touches it, and it was a third of the inference run.

**Do not tune blind** — instrument first, the same discipline as [#54](https://github.com/nikhilsrajan/fsd/issues/54).

## A correction worth keeping

This finding originally carried a reading that **"cluster overhead is fixed per fan-out width and
grows with the number of nodes"**, from run-book 37 Phase 2's two-point sweep (8× the nodes → 3.1×
the overhead, 1.42× the speedup). That reading was **wrong**, and
[cloud-overhead](cloud-overhead.md) holds the measurement that killed it: the 8-node run paid a
one-off 203 s cluster scale-up **and** was crippled by the band-stratified partition
([#60](https://github.com/nikhilsrajan/fsd/issues/60)), whose slowest shard did 113.7 s of work
while two shards did 7 s. Overhead does not scale with width; the three 16-node runs each ramped in
under 50 s.

## Sources

- `demos/E2E_AUSTRIA_AML.md` §6.2 — the same comparison in its original home
- `runbooks/41-recover-aml-job-timings.md` Step 3 — the on-blob byte counts
- Issue [#59](https://github.com/nikhilsrajan/fsd/issues/59) — the tracking item
