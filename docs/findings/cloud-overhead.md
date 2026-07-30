---
status: current
summary: Where a cloud run's wall-clock actually goes — 35 % of an inference run and 90 % of a merge run was the driver collecting results over blob, not the cluster computing. Measured 2026-07-28.
---

# Finding — fsd's cloud overhead is the driver, not the cluster

**Measured:** 2026-07-28, from run-book 38 Phases 3 and 4 (+ run-books 36 and 37 for contrast).
**Method:** run-book 41 Steps 1, 1b and 3 — AML's own `StartTimeUtc`/`EndTimeUtc` per job, the
driver's `_result.json` write time, and every artefact's blob `last_modified`.
**Tracking issue:** [#61](https://github.com/nikhilsrajan/fsd/issues/61). Related: [#48](https://github.com/nikhilsrajan/fsd/issues/48), [#59](https://github.com/nikhilsrajan/fsd/issues/59), [#54](https://github.com/nikhilsrajan/fsd/issues/54).

> Point-in-time (spec 41 D3). These numbers were true of the code and the VPN link on 2026-07-28.
> Fix (a) has since landed, which changes them — see "What has been fixed" below.

## The headline

**35 % of the inference run, and 90 % of the merge run, was the driver collecting results over
blob** — sequential per-output round-trips on the operator's laptop, untouched by any fan-out
width, node SKU or `cores` setting.

| run | wall | driver **pre**-dispatch | job span | driver **post**-collect |
|---|---|---|---|---|
| 38 P3 — inference, 300 cells | 2066.9 s | 249 s | 1089 s | **729 s** |
| 38 P4 — merge, 300 cells, no-op jobs | 1082.1 s | 66 s | 44 s | **972 s** |
| 36 P3 — build 900 cubes | ≥ 343 s | *not measured* | 324 s | 19 s |
| 37 P3 — download 3456 assets | ≥ 354 s | *not measured* | 328 s | 26 s |

`post` is measured directly (the `_result.json` write minus the last job's end); `pre` is the
residual against a known wall. **The arithmetic is the check** — had the timestamps been misread,
the residual would have come out grossly negative instead of a plausible 249 s / 66 s.

## The 249 s before dispatch

All on one clock, so these are exact:

| | window | seconds |
|---|---|---|
| `setup()` — 300 cell slices + geometries + `input.csv` | 09:06:15 → 09:06:37 | **22** |
| stage the model bundle (13.26 MB) | 09:06:48 → 09:07:01 | **13** |
| dispatch — write 16 shard CSVs | 09:07:03 → 09:07:11 | **8** |
| **submit → the first job actually executes** | 09:07:11 → 09:10:32 | **201** |
| total | | **257** |

**201 s of AML queue-and-allocate dominates it** — issue [#48](https://github.com/nikhilsrajan/fsd/issues/48)'s
cold start, now pinned. It is a fixed toll *per dispatch*, which is why an inference run wants
**one** call with `merge=True` rather than a Phase 3 followed by a Phase 4.

## The 972 s after the last job

| | window | seconds | per unit |
|---|---|---|---|
| collect — 300 `fs.exists`, then a COG open + `geometry.geojson` read each; **zero writes** | 12:09:39 → 12:19:55 | **616** | 2.05 s/cell |
| STAC — write 300 Items + `catalog.json` | 12:19:55 → 12:22:36 | **161** | 0.53 s/item |
| merge — read 300 COGs → `merged.tif` | 12:22:36 → 12:25:49 | **193** | |
| write `_result.json` | 12:25:49 → 12:25:51 | **2** | |
| total | | **972** | |

616 s of pure reads with zero writes is the signature of the collect loop
(`api.py:1228-1240` → `catalog/stac.py:233`) — about three sequential blob round-trips per output
cell at ~0.68 s each over VPN. **It scales with the number of output units, not with the work**,
which is why run-books 36 and 37 — whose collect is 16 `_status` reads — pay 19 s and 26 s while
moving far more data.

## Inside the job span

| run | node stagger | longest job | in-job work | **container startup** |
|---|---|---|---|---|
| 36 P3 (16 nodes) | 32 s | 316 s | 213.8 s | **102 s** |
| 37 P3 (16 nodes) | 26 s | 328 s | 192.1 s | **136 s** |
| 38 P3 (16 nodes) | 22 s | 1089 s | 982.7 s | **106 s** |
| 37 P2 (1 node, **warm**) | 0 s | 592 s | 577.6 s | **14 s** |
| 37 P2 (8 nodes, scaling 1→8) | 203 s | 219 s | 113.7 s | **105 s** |

- **Container startup is ~100–135 s cold, ~14 s warm.** Paid by every node in parallel, so it
  costs ~100 s of wall at any width — but on the training regime's millisecond units it is the
  entire cost.
- **Node stagger is 22–48 s once the cluster is already scaled out**, and 203 s in the one case
  where it had to grow 1 → 8. **Stagger is a scale-up cost, not a per-node one.**

## Three earlier readings this measurement killed

Kept because the corrections are the point — each was plausible and each was wrong.

| Earlier claim | What the measurement showed |
|---|---|
| "The overhead is fixed cluster spin-up" (from Phase 4 ≈ Phase 3's computed overhead, within 0.2 %) | It is the **driver's post-run collect**. The near-equality was a coincidence of two different large costs. |
| "Most of it is the bundle upload over VPN (627 s)" | The bundle stage was **13 s**. The entire pre-dispatch window is 249 s and cannot contain a 627 s upload. |
| "Ramp-up grows with fan-out width" (8 nodes → 3.1× the overhead of 1) | The 8-node run paid a one-off **203 s scale-up** and was crippled by the band-stratified partition ([#60](https://github.com/nikhilsrajan/fsd/issues/60)). The three 16-node runs each ramped in under 50 s. |

## What has been fixed, and what is left

- **✅ (a) landed 2026-07-28** — `api._existing_outputs` replaces 300 sequential `fs.exists` with
  **one `fs.glob`**, removing ~1 of the ~3 round-trips per cell (~1/3 of the 616 s on a VPN driver).
  The non-obvious part, and why it needed a test: `fs.glob` returns the filesystem's own path form
  (adlfs yields `container/path/…`, no `abfss://` scheme), so a globbed hit never string-equals a
  caller-built URL. Matching is on the scheme-independent tail `<window>/<cell_id>/output.tif`.
  A naive URL comparison would have matched everything locally and **nothing on blob**.
- **(b) open** — thread the per-item COG open + `geometry.geojson` read (~2 of 3 round-trips per
  cell, ~410 s). Do it under a single `raster.rio_env`: GDAL's env stack is thread-local, which is
  exactly the trap the merge fix hit.
- **(c) open** — batch the 301 STAC Item writes (~161 s), or write one catalog object.
- **(d) longer term** — have each node emit its own Items so the driver only concatenates; the
  collect then scales with `n_shards`, like run-book 36's.

**Do these before tuning any cluster knob** ([#59](https://github.com/nikhilsrajan/fsd/issues/59)):
no fan-out width, node SKU or `cores` setting touches this window, and it was a third of the run.

It is also the strongest argument for **running the driver in Azure** — same code, ~50× lower
per-round-trip latency — but that is a deployment change, whereas (a)–(c) are local edits that
help the laptop case too.

## Caveats

- **The post-window decomposition is Phase 4's, not Phase 3's.** Phase 4 wrote its STAC into the
  same output folder, overwriting Phase 3's Item timestamps. Both runs do the same collect over the
  same 300 outputs, so the decomposition transfers, but the per-segment numbers were measured on
  the merge run. Phase 3's own 729 s is consistent: 616 + 161 = 777 s, within 7 %.
- **~8 s of laptop-vs-Azure clock skew.** The pre-window is 257 s on the blob clock against 249 s
  derived from the laptop's wall. Every figure here is far larger than that, and each decomposition
  is internally single-clock.

## Sources

- `runbooks/41-recover-aml-job-timings.md` — Steps 1, 1b, 3: the recovery method (free, read-only)
- `demos/E2E_AUSTRIA_AML.md` §6.1 — the same analysis in its original home, with the full run context
- Issue [#61](https://github.com/nikhilsrajan/fsd/issues/61) — the tracking item and its fix list
