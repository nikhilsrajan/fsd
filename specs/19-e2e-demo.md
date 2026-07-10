# Spec 19 — end-to-end demo (demo_01 + demo_02 + demo_03) + ROI→S2-grid tiling

> **Superseded in part by spec 23 (2026-07-10):** `demos/e2e_ethiopia.py` → `demos/e2e_austria.py`,
> which starts from a real CDSE download and uses ROI-mode `run_inference`. See spec 23 + `demos/E2E_AUSTRIA.md`.
>
> **Status: SIGNED OFF + IMPLEMENTED + VERIFIED (2026-07-06).** SO-1..SO-6 approved as drafted. Landed
> `src/fsd/grid.py` (`roi_to_s2_grids`, clean-room port) + `tests/test_grid.py` (4 tests, skip
> without the `[grid]` extra) + `pyproject` `[grid]`/`[model-example]` extras; `demos/` (`adapters.py`
> `DemoRF`, `e2e_ethiopia.py`, `README.md` report); isolated `.venv-modeldeploy` (gitignored).
> **`--fast` smoke validated end-to-end** on real data (67 s cold / 13 s warm: tiling → features →
> RF → 6 COGs + STAC → merged map + 3 figures). **Real finding:** the ROI straddles the S2
> MGRS zone-36/37 boundary in practice (grids land in BOTH 32636 and 32637 — the spec's
> "single-zone" assumption was wrong), so `run_inference(merge=True)` refuses (single-CRS
> principle) and the demo does a reproject-to-dominant-zone **display merge**. **Full run DONE**
> (~44 min / 8 cores): 300 grids, 217,914 training pixels (T=19), RF on 186,086 samples, 300 COGs +
> STAC, both zones display-merged; figures + numbers in `demos/README.md`.
>
> A full **Mode-A** run of the whole product on the
> **existing Ethiopia `satellite_benchmark/` data** — reproducing the three legacy demo
> notebooks as one flow through the fsd verbs: **prep/tiling** (`demo_preparation`) →
> **training data + inference datacubes** (`demo_01`) → **train** (`demo_02`) → **deploy /
> inference → COG + STAC + map** (`demo_03`). It also **lands the ROI→S2-grid tiling** (the
> `DROPPED.md` deferred item, ROADMAP §4 / P4 groundwork) as a small `fsd.grid` module.
>
> **No satellite download in this run** — it uses the already-downloaded catalog. This is a
> **pipeline-validation** run: the labels are Austrian EuroCrops polygons *translated onto
> Ethiopia*, so **model quality is meaningless** — we're proving the plumbing end-to-end and
> getting QGIS-verifiable artifacts. The *real* run (proper Austria imagery, downloaded fresh,
> then the Ethiopia data deleted to free space) comes later once university wifi is available.
>
> Runs in an **isolated venv** so fsd's lean `.venv` never gets sklearn/s2 in it. Decisions
> flagged **[SO-n]** need sign-off. After sign-off we build `fsd.grid`, write the demo + report,
> and execute end to end.

## Inputs (given)
- **Training polygons:** `shapefiles/austria_eurocrops_sampled_ethiopia_translated.geojson`
  (1015 fields, `id=fid`, `label=EC_hcat_n`, 11 classes; bounds ~`[36.13, 11.41, 36.87, 11.99]`).
  **The polygons were relocated → any prior training datacubes / flattened arrays are now
  INVALID and must be regenerated into fresh dirs [SO-5].**
- **Inference ROI:** `shapefiles/inference_roi.geojson` (1 polygon, EPSG:4326, same footprint).
  → must be **split into S2 grids** (below).
- **Imagery:** `satellite_benchmark/sentinel-2-l2a/catalog.parquet` (Ethiopia, 579 COG tiles,
  2018 full year; bands **B04/B08/B8A/SCL**). Covers both the fields and the ROI. Although the
  ROI is geographically east of 36°E, **in practice the per-grid datacubes land in BOTH
  EPSG:32636 and 32637** (the builder picks each grid's dominant MGRS tile zone; S2 zone-36 tiles
  reach past 36°E) — see the merge note in step 5.

## The pipeline (what runs)

1. **ROI → S2 grids** (`demo_preparation`): `fsd.grid.roi_to_s2_grids(roi, grid_size_km=5,
   scale_fact=1.1)` → polyfill the ROI's convex hull at the S2 level for ~5 km (res 11), keep
   cells intersecting the ROI, scale each by 1.1 (10 % overlap so adjacent tiles don't seam),
   then **`gpd.overlay(grids, roi)` clip** so grids stay *inside* the ROI. **Save the gridded ROI
   as GeoJSON** for QGIS [SO-6].
2. **Training data** (`demo_01` + `demo_02` prep): `fsd.create_training_data(label_polygons=EC,
   catalog=benchmark, 2018 full year, mosaic_days=20 → T=19, bands=[B04,B08,B8A,SCL],
   adapter=DemoRF())` → per-field datacubes + flatten + **`features.npy`** (the adapter's feature
   transform). Fresh output dir.
3. **Train** (`demo_02`): your sklearn code — `RandomForestClassifier` on `features` +
   `LabelEncoder`; `joblib.dump((clf, le), rf.joblib)`. fsd does not train.
4. **Inference datacubes** (`demo_01`): `workflows.create_datacube.run_create_datacube(
   shapefilepath=inference_s2_grids.geojson, id_col="id", 2018 full year, bands, no label)` →
   one datacube per grid cell + `input.csv`.
5. **Deploy / inference** (`demo_03`): `fsd.run_inference(model=DemoRF+artifact,
   inference_datacubes=input.csv)` → one **COG per grid** + a **STAC** catalog. Because the ROI
   spans two UTM zones, `run_inference(merge=True)` would (rightly) refuse the cross-CRS merge;
   the demo instead reprojects each output to the **dominant** zone (nearest, categorical-safe)
   and mosaics that into a **display** crop-map COG.
6. **Visual outputs** (`demo_01` + `demo_03`) [SO-6]: save the gridded-ROI/fields/ROI GeoJSON,
   a **per-class NDVI timeseries** plot from the training features, and a **categorical model-
   output map** plot of the merged COG (with a class legend). Embedded in the report.

### The demo adapter (band-limited)
`satellite_benchmark/` has only **B04/B08/B8A** (+SCL), so the shipped 9-band `EuroCropsRF`
(NDVI/NDRE/GCVI/SAVI) **cannot** run here (NDRE needs B05, GCVI needs B03). The demo uses a
reduced adapter — `feature_sequence = [mask_invalid_and_interpolate, compute NDVI + SAVI (both
from B04/B08), remove B04/B08/B8A]` → 2 features; `required_bands=[B04,B08]`; `n_timestamps=19`;
categorical `uint8`/`nodata 255`. The full 9-band adapter returns for the real-Austria run.

## [SO-1] ROI→S2-grid tiling → new `src/fsd/grid.py` (deps isolated)
Port `rsutils.s2_grid_utils.get_s2_grids_gdf` (read-only ref) into a small, tested fsd module —
this is the ROADMAP §4 / P4 groundwork and lets the demo be **fsd-native** (not import legacy
rsutils):
```python
# src/fsd/grid.py
def roi_to_s2_grids(roi, *, grid_size_km=5, scale_fact=1.1, res=None, clip=True) -> gpd.GeoDataFrame:
    # res from grid_size_km (5 km → S2 res 11); s2.polyfill(convex_hull) → keep intersecting →
    # shapely.affinity.scale(scale_fact) each cell → gpd.overlay(grids, roi) if clip. cols: id, geometry.
```
**`s2` + `s2cell` go in a new optional `[grid]` extra**, NOT fsd core deps — fsd's `.venv` stays
lean. (Alternative considered: call `rsutils.s2_grid_utils` from the demo script only. Rejected:
the tiling is a real, reusable fsd capability heading for `run_inference(roi=…)`, and a
clean-room port + test is worth it now.) **This spec does NOT yet wire `run_inference(roi=…)`**
— the demo chains `grid → create_datacube → run_inference(datacubes)` explicitly; the ROI
front-end + download integration stay **P4**.

## [SO-2] Isolated venv
A second venv `fsd/.venv-modeldeploy` (**gitignored**, like `.venv-rslearn`):
```bash
python3.11 -m venv .venv-modeldeploy
.venv-modeldeploy/bin/pip install -e ".[dev,grid,model-example]"
```
`model-example` = sklearn + joblib; `grid` = s2 + s2cell; plus matplotlib/seaborn for plots
(already in the `notebooks` extra — fold plotting deps into `model-example` or add to the run).
fsd's own `.venv` is never touched.

## [SO-3] Deliverables + location
- **`src/fsd/grid.py`** + `tests/test_grid.py` (synthetic).
- **`demos/e2e_ethiopia.py`** — the runnable end-to-end script (the 6 steps), with a
  `--fast` toggle (subset fields/grids/shorter window) for a quick smoke vs the full run.
- **`demos/README.md`** — the **report**: (a) the venv-creation + run steps (so it's reproducible
  by hand), and (b) the **results** — shapes/counts/runtime, embedded figures, and the saved
  GeoJSON/COG paths for QGIS. Filled in after the run.
- **Figures committed** (small PNGs, like `benchmarks/…_figures/`); **heavy outputs**
  (datacubes, per-grid COGs) → `tests/outputs/demo_e2e/` (**gitignored**); the **gridded-ROI
  GeoJSON** saved where the user can open it in QGIS (committed — it's small + a deliverable).

## [SO-4] Scope + honest caveat
- **Full shapefiles** as given (1015 fields; the ROI tiles to **300 grid cells**), **full-year
  2018** (`2018-01-01`→`2018-12-31`, mosaic 20 → **T=19**), matching demo_01/02/03. Mixed-zone →
  the demo reproject-merges the outputs into one ROI-wide display map (step 5).
- **Runtime/disk caveat:** 1015 full-year training cubes + ~100–150 inference cubes is heavy
  (order ~1–2 h on 8 cores; tens of GB of intermediate cubes in the gitignored output dir). The
  `--fast` toggle exists for a smoke pass. Recommend the **full** run for the report, `--fast`
  to shake out bugs first.
- **Model quality is NOT meaningful** (Austrian crop labels on Ethiopian imagery) — this
  validates the *pipeline* and yields QGIS artifacts. Real run: fresh Austria download, then
  delete the Ethiopia data to free space.

## [SO-5] Invalidate stale artifacts
The training polygons moved, so any earlier `training_datacubes` / `training_data` / flattened
arrays under `tests/outputs/` are stale. The demo writes to **fresh** dirs
(`tests/outputs/demo_e2e/…`) and does not read old ones. (Note the old `tests/outputs/flatten/`
etc. from prior runbooks are now geographically inconsistent with these polygons.)

## [SO-6] Visual + shapefile outputs (your asks)
The report + script produce, and the report embeds/links:
1. **Shapefiles for QGIS:** `inference_s2_grids.geojson` (the clipped gridded ROI), plus copies/
   references of the training fields + the raw ROI — so the grid tiling can be eyeballed against
   the ROI (does it fill it, stay inside, overlap by ~10 %?).
2. **NDVI timeseries plots** (from training features, `demo_01`-style): per-class **median NDVI
   over the 19 windows** (one line per crop class) + a "first N pixels" spaghetti plot — the
   phenology signal the RF sees. Saved PNG(s).
3. **Model-output map plot** (`demo_03`-style `plot_categorical_tif`): the merged crop-map COG
   rendered as a categorical map with a **class→colour legend**. Saved PNG.

## Out of scope
- **Satellite download** (uses the existing catalog; download is the *real* run, later).
- **`run_inference(roi=…)` API wiring** + download-in-the-loop — **P4**; the demo chains the
  steps explicitly.
- **Azure / Batch**, the 9-band model, model accuracy.

## Ripple effects
- New `src/fsd/grid.py` + `tests/test_grid.py`; `pyproject.toml` `[grid]` extra (s2, s2cell).
- `DROPPED.md`: ROI→S2-grid tiling moves from **deferred** → **landed** (`fsd.grid`), noting
  `run_inference(roi=…)` front-end still P4.
- `demos/` new folder (README report + script); `.gitignore` add `.venv-modeldeploy/` and
  `tests/outputs/demo_e2e/`.
- `RECIPES.md` (grid tiling + the e2e demo command), `ROADMAP.md` (P4: grid ported, front-end
  remains), `CHANGES.md`, `PROGRESS.md`. Living-doc `notebooks` guidance unchanged.

## Tests (`tests/test_grid.py`, synthetic; no s2 network)
- `roi_to_s2_grids` on a small synthetic ROI: returns a non-empty `GeoDataFrame` (`id`,
  `geometry`, EPSG:4326); every clipped grid **intersects** the ROI and (with `clip=True`) is
  **contained** in it (`overlay` worked); `scale_fact` visibly enlarges pre-clip cells; grid
  count is stable/deterministic. Skips if `s2`/`s2cell` aren't importable (the `[grid]` extra).
- The end-to-end run itself is the **manual `demos/README.md`** (real data, QGIS gate), not a
  unit test.

## Sign-off checklist
- [x] **[SO-1]** Port ROI→S2 tiling into `src/fsd/grid.py` (clean-room from rsutils ref);
      `s2`+`s2cell` in a `[grid]` optional extra (core stays lean); `run_inference(roi=…)` stays P4.
- [x] **[SO-2]** Isolated `fsd/.venv-modeldeploy` (gitignored); `pip install -e ".[dev,grid,model-example]"`.
- [x] **[SO-3]** Deliverables: `fsd/grid.py` + test, `demos/e2e_ethiopia.py` (+`--fast`),
      `demos/README.md` report; figures committed, heavy outputs gitignored, gridded-ROI GeoJSON saved.
- [x] **[SO-4]** Full shapefiles, full-year T=19, single-zone merge; runtime/disk caveat +
      `--fast`; model quality explicitly not meaningful (pipeline validation).
- [x] **[SO-5]** Regenerate into fresh dirs (relocated polygons invalidate old datacubes/flattened).
- [x] **[SO-6]** Save gridded-ROI + fields + ROI GeoJSON (QGIS), per-class NDVI timeseries PNG,
      and categorical model-output map PNG; all embedded/linked in the report.
