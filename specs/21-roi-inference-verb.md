# Spec 21 — Local ROI inference verb (`run_inference(roi=…)`, P0.75)

> **AMENDED 2026-07-28 — see `D-GRID-1`:** an ROI is one *region* (multi-row input is unioned
> before tiling), so `roi_to_s2_grids` returns **one row per S2 cell with unique ids**. The
> original clip used `gpd.overlay` against the ROI's individual rows, which repeated cell ids for a
> multi-polygon ROI and collapsed N work units onto one export folder. Found by runbook 38 Phase 3.
>
> **Status: SIGNED OFF + IMPLEMENTED + VERIFIED (2026-07-07).** SO-1..SO-6 approved (SO-6 accepted
> as drafted; SO-5 redesigned to three merge modes). Landed: `run_inference(roi=…)` front-end +
> `InferenceResult.grids_filepath` + three-mode `_merge_outputs` (`api.py`); the per-cell
> **build+infer** unit-of-work `workflows/infer_task.py` + `_snakefiles/create_inference/Snakefile`
> + `runners.run_local_inference`; the demo refactored to `merge="reproject"`. **163 tests, ruff
> clean** (`test_api_roi.py` +8, `test_workflows.py` +3). **Real smoke** (`.venv-modeldeploy`,
> benchmark Ethiopia): a ~9 km ROI → **10 cells → 10 COGs (uint8/nodata 255/EPSG:32636) + STAC(10)
> + reproject-merge (899×889, 96.9 % valid)** in 42 s @ cores=2; resumability sentinels
> (`done_infer.txt`) confirmed. One bug found+fixed: snakemake parses an empty `--config key=` as
> `None`, so `predict_batch_size` is now omitted-when-None. Runbook `tests/manual/roi_inference.md`.
> Completes **Mode A**: one call turns an ROI GeoJSON into per-cell crop-class COGs + a STAC catalog,
> all local — the new work was the **`roi=` front-end** on `run_inference` and folding the per-cell
> build+infer into the **runner seam** (Snakemake locally, so P4 is a clean runner swap to Batch).
>
> Roadmap phase **P0.75** (ROADMAP §4 / P4 groundwork). Depends on nothing new; no Azure, no
> infra-ask. Decisions flagged **[SO-n]** need explicit sign-off before implementation.

## Motivation

Today the product has two entry points but a gap between them:

- `create_training_data(label_polygons=…)` — labelled field shapes → training arrays. **Done** (spec 18).
- `run_inference(inference_datacubes=…)` — a model over **pre-built** cubes → COG + STAC. **Done** (spec 18).
- `fsd.grid.roi_to_s2_grids(roi)` — tile an ROI into ~5 km S2 cells. **Done** (spec 19).

What's missing is the verb the north-star (ROADMAP §1.5) actually promises: *"give fsd a
region of interest + dates + mosaic interval; it tiles the ROI, builds a cube per cell, runs
the model, writes COGs + STAC — the user never thinks about tiling."* The demo (spec 19)
already proves the **sequence** works by wiring the pieces by hand in `demos/e2e_ethiopia.py`.
P0.75 makes that sequence a **single verb**.

**Second motivation — protect the P4 promise (the reason we discussed Snakemake).** ROADMAP P4
says inference-at-scale is *"only the runner/dispatch swap, no new pipeline code."* That holds
**only if** the per-cell work is a **runner-dispatched unit-of-work**, exactly like the datacube
build already is (`workflows/task.py` + Snakefile → Batch swaps in untouched). Right now
`run_inference` infers with its **own `multiprocessing.Pool`** (`engine.run_local`), a *second*
fan-out mechanism that P4 would have to demolish. P0.75 is where we fold inference into the
runner seam so P4 stays a one-line `runner="batch"` swap.

## What ships

1. **`run_inference(roi=…)`** — a new front-end path on the existing verb (§API).
2. **A per-cell `build + infer → COG` unit-of-work** (`workflows/infer_task.py`) + its
   **Snakefile** + a runner entry, mirroring the build task so Batch (P4) dispatches it unchanged.
3. **Preflight** for ROI mode: T-match, bands, adapter, ROI/catalog coverage — *before* a cube is built.
4. **`tests/manual/roi_inference.md`** runbook + unit tests. Docs updated
   (`ROADMAP` P0.75→done, `PROGRESS`, `CHANGES`, `RECIPES`).

Explicitly **out of scope**: `create_training_data(roi=…)` (deferred — labelled fields already
*are* the geometries, no ROI→cell tiling needed); anything Azure (P1+); bundle registration (P6).

## API — the `roi=` overload [SO-1]

`run_inference` gains a second, mutually-exclusive calling convention. `inference_datacubes=`
(the spec-18 pre-built path) stays exactly as-is.

```python
fsd.run_inference(
    model,                          # bundle path (str) OR live ModelAdapter — see [SO-4]
    *,
    # --- NEW: ROI mode (mutually exclusive with inference_datacubes=) ---
    roi=…,                          # GeoDataFrame | path | geojson mapping (EPSG:4326)
    catalog_filepath=…,             # the imagery catalog covering the ROI (from fsd.download)
    startdate=…, enddate=…, mosaic_days=…, bands=…,
    grid_size_km=5, scale_fact=1.1, # forwarded to fsd.grid.roi_to_s2_grids
    scl_mask_classes=config.SCL_MASK_CLASSES,
    output_folderpath=…,
    # --- shared with the pre-built path ---
    merge=False, cores=1, runner="local", storage=None,
    predict_batch_size=None, skip_nan=True, progress=True,
) -> InferenceResult                # + a new `grids_filepath` field
```

- Passing **both** `roi=` and `inference_datacubes=` (or neither) is a preflight error.
- ROI mode requires `catalog_filepath` + `startdate`/`enddate`/`mosaic_days`/`bands`; the
  pre-built path forbids them.
- `InferenceResult` gains `grids_filepath: str | None` (the saved gridded-ROI GeoJSON, for QGIS).

**Signature note:** `run_inference` currently takes `inference_datacubes` as its 2nd positional
arg. To keep ROI-mode kwargs clean and avoid a confusing positional, ROI-mode args are
**keyword-only** and `inference_datacubes` becomes optional (default `None`). [SO-1]

## The chain (what ROI mode runs)

1. **Preflight (cheap, before any build)** [SO-2] — fail before spending on cube builds:
   - `compute_n_timestamps(startdate, enddate, mosaic_days) == adapter.n_timestamps` (the calendar-mosaic payoff, ROADMAP §3.3);
   - `adapter.required_bands ⊆ bands`;
   - model/bundle loads and declares a coherent spec;
   - `roi` non-empty and intersects the catalog's footprint;
   - `runner`/`storage` are local (P0.75 is local-only, same guard as the other verbs).
2. **Tile** — `grids = fsd.grid.roi_to_s2_grids(roi, grid_size_km, scale_fact)`; save
   `grids.geojson` under `output_folderpath` (→ `InferenceResult.grids_filepath`). Needs the
   `[grid]` extra; a clean error if absent (spec 19 already does this).
   **One row per cell, ids unique — see D-GRID-1.**
3. **Setup** — reuse `workflows.create_datacube.setup(shapefilepath=grids, id_col="id",
   label_col=None, …)`: per cell, write `geometry.geojson` + `catalog.parquet` slice + an
   `input.csv` row. Cells with **no intersecting tiles are skipped** (existing behaviour). This
   is the *same* setup the build workflow uses — no new slicing code.
4. **Fan out the per-cell `build + infer → COG` task via the runner** [SO-3] — for each
   `input.csv` row: build the datacube (existing `builder.build_datacube`) **then** infer it to
   `output.tif` (existing `engine.infer_datacube_to_cog`) **in one task process**, model loaded
   once per task. Snakemake runs `cores` cells at a time; `done.txt`/`output.tif` give
   **resumability** (re-run skips finished cells). This is the unit Batch dispatches in P4.
5. **Collect + STAC** — gather every `output.tif`, build the STAC catalog
   (`catalog.stac.cog_outputs_to_items` + `write_stac_catalog`, unchanged from spec 18).
6. **Optional merge** — three modes [SO-5]:
   - `merge=False` (default) — per-cell COGs only.
   - `merge=True` — **strict single-CRS** merge to `merged.tif`; **refuses on mixed CRS** with an
     error pointing at `merge="reproject"`. Data-faithful: no resampling; the COGs are authoritative.
   - `merge="reproject"` — **display merge**: reproject every cell to the **dominant zone** (the CRS
     covering the most cells) with **nearest-neighbour** resampling (categorical output — must not
     interpolate class values), then merge. Produces one viewable `merged.tif`, documented as
     **lossy / for viewing only**; the per-cell COGs remain the authoritative output.

   This **promotes the demo's reproject-merge into fsd core** — it currently lives only in
   `demos/e2e_ethiopia.py`, so today a zone-straddling `merge=True` *errors* instead of producing a
   map. Now a user who asks for a merged map across a zone-straddling ROI (spec 19's real finding)
   gets one via `"reproject"`, while the default never reprojects silently (protects the single-CRS
   principle). The demo is refactored to call `merge="reproject"` instead of its own logic.

## D-GRID-1 (AMENDMENT 2026-07-28) — an ROI is one *region*; cell ids are unique

**Added after a real failure, not at design time.** The original spec said "tile the ROI" and left
the multi-polygon case unstated. The implementation clipped with
`gpd.overlay(grids, roi_gdf, how="intersection")`, which emits **one row per (cell × roi-polygon)
pair** — so a multi-row `roi` silently multiplied rows and **repeated cell ids**.

**The contract, now explicit:**
1. **An ROI is one region.** A multi-row `roi` is `unary_union`-ed into a single (multi)polygon
   **first**, and *every* step — convex-hull polyfill, `intersects` filter, **and the clip** —
   works against that union. (The union was already computed and used for the first two steps;
   only the clip departed from it. That inconsistency was the bug.)
2. **One S2 cell = one row = one work unit = one datacube = one `output.tif`.** `id` (the S2 cell
   id) is the **work-unit key**: `create_datacube.setup(id_col="id")` derives `export_folderpath`
   from it. Ids MUST be unique in the returned frame; `roi_to_s2_grids` asserts this before
   returning, and `setup()` independently refuses duplicate ids for **any** caller.
3. **Per-*shape* datacubes are a different verb.** If you want one cube per polygon, pass your
   shapefile straight to `workflows.create_datacube` with your own unique `id_col` — that is the
   training path (`create_training_data`), not roi mode. **An ROI file and a label file are not
   interchangeable inputs.**

**Why it mattered (measured 2026-07-28, runbook 38 Phase 3).** `AT_2018_TRAIN.geojson` — a *label
set* of 900 EuroCrops field polygons — was wired into the `roi=` slot. Result: **1167 rows for 172
distinct cells**, one cell repeated **43×**, each row a ~0.016 km² field fragment of a 49.6 km²
cell (0.98 % of it), with the ROI's own attributes dropped by `roi_gdf[["geometry"]]` so the
fragments carried **no identity to distinguish them**. Downstream, `export_folderpath` collapsed
1167 work units onto 172 folders, so up to 16 threads wrote the same `geometry.geojson`
concurrently → Azure `InvalidBlockList` on the block-blob commit, and last-writer-wins geometry.
Duplicate rows are *contiguous* out of `overlay`, so **100 %** of 16-wide dispatch windows
contained a collision and **99 %** of work units belonged to a duplicated cell.

**Two faults, both fixed:** the wrong *class* of file in the `roi=` slot (a runbook error — Phase 3
now uses `AT_ROI.geojson`, 1 polygon, 10,682 km² → **300 unique cells**), and a tiling function that
did not enforce its own invariant, so bad input produced silently-wrong output instead of an error.

**Not a behaviour change for the validated path:** a single-polygon ROI clips identically
(`overlay` against one row ≡ intersecting with that row), so runbook 38 Phase 1's 9 cells are
unchanged. Regression tests: `tests/test_grid.py` (multi-polygon → unique ids; union-clip still
clips; single-polygon unchanged) + `tests/test_workflows.py::test_setup_refuses_duplicate_ids`.

**Tiling moves INTO preflight (amends step 2 of "The chain").** Tiling is local, CPU-only work, so
it now runs *inside* the preflight block — **before** `fs.makedirs(output_folderpath)` and before
`_ensure_bundle`. A bad ROI therefore costs seconds, not: a blob folder, a bundle upload (measured
**627 s** for 13 MB over VPN), setup's N per-cell blob writes, and an AML dispatch. Preflight rejects
**duplicate cell ids** and **an ROI that tiles to 0 cells**, and then **prints the cell count**
(`[run_inference] roi -> N grid cells`) — N *is* the cluster workload and the bill, and nobody saw it
coming this time. Three layers, deliberately: `roi_to_s2_grids` asserts uniqueness at source,
preflight catches it before spend, `setup()` refuses it for every caller (including non-roi ones).
Tests: `tests/test_api_roi.py` — the duplicate-id case asserts `spent == []` (nothing created or
uploaded), the empty-tiling case fails the test outright if the bundle is staged.

**The retry that wasn't the fix.** A `storage.fs._write_with_retry` was added the same day for the
*hypothesised* transient adlfs race and **reverted** once this root cause was found: retrying cannot
resolve a deterministic same-blob collision, and 16 threads × 6 attempts buried the real error under
a minutes-long storm that read as an infinite loop. `InvalidBlockList` under concurrency should be
read as **"two writers, one blob"** first. See TODO #57 (retracted) / #58.

**Process note.** This spec's silence on multi-polygon ROIs is what let a wrong input through for
three run-books. When a spec says "tile the ROI", the shape of `roi` is part of the contract —
state it.

## Key design decision — inference in the runner seam, not a second pool [SO-3]

This is the crux we discussed. Two candidates:

| | **A. Per-cell `build+infer` is ONE runner task** *(proposed)* | **B. Keep two stages: Snakemake builds all cubes, then `engine.run_local` mp.Pool infers all** |
|---|---|---|
| P4 (Batch) | **Clean runner swap** — Batch dispatches the same task | Must rip out the mp.Pool and re-implement dispatch |
| Fan-out mechanisms | **One** (the runner seam), for build *and* infer | Two (Snakemake + mp.Pool) |
| Resumability | Free (Snakemake sentinels per cell) | mp.Pool has none by construction |
| Pipelining | A cell infers as soon as its cube builds | "build ALL, then infer ALL" |
| Model load | **once per task** (= per cell at 1 cell/task); cheap for RF, batchable for heavy models via `cells_per_task` (future knob) | once per pool worker, amortized across many cubes |

**Proposed: A.** It's the only option that keeps the ROADMAP-P4 "just a runner swap" promise
honest, unifies the fan-out, and gives resumability for free. The one real cost — model reload
per task — is negligible for the RF/NDVI models in scope, and the mitigation (K cells per task)
is a granularity knob we'd want to tune for Batch anyway (AZURE_INFRA §7's open "task
granularity" question — better set locally and cheaply now). `cells_per_task` defaults to **1**
in P0.75; batching is a documented future lever, not built now. [SO-3]

The spec-18 **pre-built-cubes path keeps its mp.Pool** — it's a local convenience for "I already
have cubes" and Batch never needs it. Only the new `roi=` path goes through the runner seam.
(Routing the pre-built path through an infer-only Snakemake rule too is possible but deferred —
no P4 dependency on it.)

## Model must be a bundle in ROI mode [SO-4]

The runner shells out to a subprocess per cell, so the model must cross a process boundary — a
**bundle path** (F5), not a live in-memory adapter. Mirrors the existing `cores>1 requires a
bundle` rule (spec 18). UX: if a **live** `ModelAdapter` is passed to `roi=` mode, fsd
**auto-saves it to a temp bundle** first (via `model.bundle.save`) so the simple call still
works — provided the adapter class is import-path resolvable (F5 requires it anyway). A
non-importable `__main__` adapter raises a clear preflight error pointing at the bundle
requirement. [SO-4]

## Imagery presence + the CDSE-quota constraint [SO-6]

P0.75 assumes the imagery for the ROI is **already downloaded** and covered by
`catalog_filepath` (as the demo does). A `fetch_missing=True` path that calls `fsd.download`
inside `run_inference` is **deferred**. Preflight instead **warns** (not fails) if some grid cells
have no tiles in the catalog, and those cells are skipped in setup (existing behaviour).

**Why this is the *correct* long-term shape, not just a P0.75 shortcut — conserve CDSE quota.**
When a download step *is* eventually wired for the cloud, it must be a **one-time, up-front
download into shared blob storage** (a control-plane step); the **Batch inference tasks then read
imagery from blob only — never CDSE.** N spun-up VMs each re-fetching the same tiles from CDSE
would multiply quota usage (CDSE is rate/quota-limited) and be slow. So `fsd.download` (CDSE →
blob) stays a **separate phase** from the per-cell inference fan-out — and the two are **already
decoupled**: inference consumes a `catalog_filepath` and has no code path to CDSE. This constraint
belongs in **AZURE_INFRA §7 / the P4 design**; recorded here so SO-6's deferral is a deliberate
architectural choice, not an oversight. [SO-6 — accepted for P0.75 as drafted]

## Files

- `src/fsd/api.py` — `run_inference` gains the `roi=` branch (tile → setup → runner → collect →
  STAC → merge); `InferenceResult.grids_filepath`; ROI-mode preflight helpers. `_merge_outputs`
  gains the `"reproject"` (display) mode — reproject-to-dominant-zone, nearest-neighbour — shared
  by both the pre-built and ROI paths.
- `demos/e2e_ethiopia.py` — refactored to call `run_inference(..., merge="reproject")` instead of
  its own hand-rolled reproject-merge (that logic moves into core, above).
- `src/fsd/workflows/infer_task.py` — **new** unit-of-work: build one datacube **+** infer →
  COG, CLI-invokable (`python -m fsd.workflows.infer_task … --bundle … --output …`), a superset
  of `task.py`'s args. Reuses `builder.build_datacube` + `engine.infer_datacube_to_cog`.
- `src/fsd/workflows/_snakefiles/create_inference/Snakefile` — **new** sibling of the build
  Snakefile; one job per cell shelling `infer_task`; `done.txt` resumability. Build Snakefile
  untouched (low risk).
- `src/fsd/workflows/runners.py` — small generalization so `run_local` can drive either Snakefile
  (or a `run_local_inference` sibling); Batch stub comment updated to name the infer task.
- `src/fsd/workflows/create_datacube.py` — `setup` reused as-is (no label path already supported).
- Docs: `ROADMAP.md` (P0.75 → done), `PROGRESS.md`, `CHANGES.md`, `RECIPES.md` (the one-call
  recipe), `tests/manual/roi_inference.md` (**new** runbook, supersedes the deploy.md §3 3×3-grid
  stand-in — that stand-in existed *because* this verb didn't).

## Testing

- **pytest** (`tests/test_api.py` / a new `tests/test_workflows_inference.py`): ROI-mode preflight
  (T-mismatch, missing bands, both/neither entry-point, non-importable adapter); the `infer_task`
  CLI on a synthetic 1-cell fixture (build+infer → a valid 1-band COG); mutually-exclusive-args
  guard; `grids_filepath` populated. Real Snakemake dispatch stays a dry-run test (as spec 08).
- **Manual** (`tests/manual/roi_inference.md`): the spec-19 demo ROI as a **single
  `run_inference(roi=…)` call** on `satellite_benchmark/`, then QGIS-eyeball the per-cell COGs +
  the merged/display map (the visual-validation gate). Should reproduce the demo's post-spec-20
  numbers (0 dead cells) — a regression anchor.

## Sign-off checklist

- [x] **SO-1** — API: overload `run_inference` with keyword-only `roi=` mode (vs a separate
      verb); `inference_datacubes` becomes optional; both/neither is an error.
- [x] **SO-2** — Preflight the ROI run (T, bands, adapter, ROI∩catalog, seams) *before* any cube build.
- [x] **SO-3** — **Fold per-cell `build+infer` into the runner seam as ONE task** (option A), so
      P4 is a pure runner swap; `cells_per_task=1` now, batching deferred; pre-built mp.Pool path kept.
- [x] **SO-4** — ROI mode requires a **bundle**; auto-save a live adapter to a temp bundle for UX.
- [x] **SO-5** — `merge`: `False` | `True` (strict single-CRS, refuses cross-CRS) | `"reproject"`
      (display merge, nearest-neighbour, lossy, for viewing). **Promotes the demo's reproject-merge
      into core**; per-cell COGs stay authoritative; default never reprojects silently.
- [x] **SO-6** — Assume imagery present (catalog covers ROI); `fetch_missing`/download-inside
      **deferred**; missing-tile cells warn + skip. **Cloud: `fsd.download` (CDSE→blob) is a
      one-time up-front phase; Batch inference tasks read blob, never CDSE (conserve quota) —
      carried to P4 / AZURE_INFRA §7.** *(accepted for P0.75 as drafted.)*
