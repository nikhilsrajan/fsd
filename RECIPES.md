# RECIPES — reusable commands & scripts

A durable, append-only index of useful commands and one-off scripts, so they don't get
lost. **When a non-trivial command or script proves useful, add it here** with: what it
does, the exact command, and a pointer to the committed script (if any).

Conventions:
- Run from the **workspace root** (parent of `fsd/`) unless noted; the data folders
  (`satellite_benchmark/`, `shapefiles/`) live there.
- Always use the venv: `fsd/.venv/bin/python` (deps are not in system Python).
- Committed scripts live in `fsd/benchmarks/`; step-by-step manual runbooks live in
  `fsd/tests/manual/*.md`. Bulk outputs go to `fsd/tests/outputs/` (gitignored).

---

## Environment

```bash
cd fsd
python3.11 -m venv .venv && source .venv/bin/activate && pip install -e ".[dev]"
```

## Tests & lint

```bash
fsd/.venv/bin/python -m pytest -q            # fast synthetic tests
fsd/.venv/bin/ruff check src/ tests/         # lint (add --fix to autofix)
```

## High-level API (spec 16 / P0)

The user-facing verbs. `import fsd` then:

```python
import fsd
catalog = fsd.download(roi, startdate, enddate, bands, dst_folderpath, creds, max_tiles=600)
training = fsd.create_training_data(
    label_polygons, catalog_filepath=catalog, startdate=..., enddate=..., mosaic_days=20,
    bands=[...], id_col="fid", label_col="crop", export_folderpath=..., cores=8,
)
arrays = training.load()   # {"data" (px,T,b), "ids", "labels", "coords", "metadata"}
```

`fsd.compute_n_timestamps(start, end, mosaic_days)` = the calendar `T` (preflight uses it).
`run_inference` / `deploy` are stubs (P4 / P6). Install: `pip install
"git+ssh://git@github.com/nikhilsrajan/fsd.git"`. Module = `src/fsd/api.py`.

## Safe download runner CLI (spec 26)

A thin CLI over `download_resume` — preview before committing GB + quota, and a clean
mid-run stop. Run from `fsd/`, venv active.

```bash
# preview: metadata only, zero band bytes
.venv/bin/python -m fsd.sources.download_cli \
  --roi my_roi.geojson --start 2018-01-01 --end 2019-01-01 \
  --bands B04 B08 B8A SCL --dst data/s2l2a --catalog data/s2l2a/catalog.parquet \
  --max-tiles 600 --dry-run

# real run, with a stop-file armed (touch it to stop cleanly; resume by re-running)
.venv/bin/python -m fsd.sources.download_cli \
  --roi my_roi.geojson --start 2018-01-01 --end 2019-01-01 \
  --bands B04 B08 B8A SCL --dst data/s2l2a --catalog data/s2l2a/catalog.parquet \
  --max-tiles 600 --stop-file /tmp/fsd.stop --creds cdse_credentials.json
# touch /tmp/fsd.stop   # from another terminal, to stop cleanly
```

Writes `<dst>/_result.json` (spec 24 paste-back shape); exit code doubles as PASS/FAIL (0 on
clean completion or a user stop, non-zero on failures/circuit-trip/unresolved pool-break).
Confirm-run runbook: `runbooks/26-download-confirm-run.md`.

## STAC export of the tile catalog (spec 17)

Additive interchange view — the GeoParquet stays the query format. Pure-metadata (no raster
reads); `proj:code` from the MGRS tile in the product id.

```python
from fsd.catalog.catalog import TileCatalog
TileCatalog("data/s2l2a/catalog.parquet").to_stac("data/s2l2a/stac")   # -> catalog.json
# or: fsd.catalog.stac.tile_catalog_to_items(gdf) / write_stac_catalog(items, dst)
```

Module = `src/fsd/catalog/stac.py`. `read_proj=True` adds per-asset `proj:shape/transform`
(opens rasters). `stac-geoparquet` deferred.

## Download (CDSE → local COG archive)

Full-year, multi-CRS Sentinel-2 L2A download (the `satellite_benchmark/` archive).
Script: `fsd/benchmarks/download_year_ethiopia.py`. Report:
`benchmarks/download_report_2018_ethiopia.md`.

## Datacube build

- **Full-ROI year benchmark (single big ROI, `s2grid=165bca4`):**
  `fsd/benchmarks/datacube_year_ethiopia.py` (+ `_plots.py`). Report:
  `benchmarks/datacube_report_2018_ethiopia.md`.
- **Full-year, per-field build for the 1015 EuroCrops fields** (one cube/field over
  2018, calendar mosaic, per-cube `timings.json`):
  ```bash
  FSD_WRITE_TIMINGS=1 fsd/.venv/bin/python fsd/benchmarks/eurocrops_year_build.py
  ```
  Script: `fsd/benchmarks/eurocrops_year_build.py`. Cubes → `tests/outputs/datacube_year/`.
- **Manual runbook (real multi-CRS build, QGIS-validated):** `tests/manual/datacube.md`.

## Flatten (datacubes → per-pixel training arrays)

- **Real-data flatten runbook** (EuroCrops fields → per-field cubes via the workflow →
  `flatten` → `data/coords/ids/labels`): `tests/manual/flatten.md`. Depends on spec 15
  (calendar mosaic) so cubes across tiles/zones share a `timestamps` axis.

## Benchmarks & analysis

- **Datacube build report + stats for the 1015-field full-year run** (aggregates the
  per-cube `timings.json`, flattens, computes per-class NDVI phenology, writes report +
  figures):
  ```bash
  fsd/.venv/bin/python fsd/benchmarks/eurocrops_year_report.py
  ```
  Script: `fsd/benchmarks/eurocrops_year_report.py`. Report:
  `benchmarks/eurocrops_year_report.md`.
- **Parallelism / throughput sweep** (throughput vs `cores`, per-step timing, read log):
  `fsd/benchmarks/datacube_throughput_sweep.py`. Runbook:
  `tests/manual/throughput_benchmark.md`.
- **COG vs JP2 A/B** (build-time + storage): `fsd/benchmarks/prep_cog_dataset.py`
  (JP2→COG dataset) + `fsd/benchmarks/compare_cog_jp2.py`. Runbook:
  `tests/manual/cog_experiment.md`.

## Data maintenance

- **In-place JP2 → COG migration** (converts a JP2 archive to COG+overviews, resumable,
  disk-safety floor, `--verify`): `fsd/benchmarks/migrate_jp2_to_cog.py`.

## Plug a model in + run local inference (spec 18, P0.5)

Write a small adapter (declarations + `load` + `predict`), let fsd run the feature transform in
both training and inference (F1 anti-skew), then infer over pre-built datacubes → COG + STAC.

```python
import fsd
from fsd.bands import modify
from fsd.model import BaseModelAdapter, bundle

class MyModel(BaseModelAdapter):
    required_bands = ["B04", "B08"]
    n_timestamps = 19
    output_dtype, output_nodata, output_band_names = "uint8", 255, ["crop_class"]
    feature_sequence = [                       # the ONE transform, used at train AND inference
        (modify.mask_invalid_and_interpolate, {}),
        (modify.compute_bands, dict(bands_to_compute=["NDVI"])),
        (modify.remove_bands, dict(bands_to_remove=["B04", "B08"])),
    ]
    def load(self):    import joblib; self.clf = joblib.load(self.artifacts["model"])
    def predict(self, X): return self.clf.predict(X).astype("uint8")

# training data with features (writes features.npy additively; raw data.npy kept):
td = fsd.create_training_data(..., adapter=MyModel(), aggregate=None)   # or "median_per_id"
d = td.load()                                  # d["features"], d["feature_labels"], ...

# package for travel / cloud (adapter class must be importable by module:attr):
bundle.save(MyModel(), {"model": "rf.joblib"}, "my_bundle")

# inference over PRE-BUILT inference datacubes -> COG per cube + STAC (+ optional merged map):
res = fsd.run_inference("my_bundle", inference_datacubes="…/input.csv",
                        output_folderpath="…/out", merge=True)
# res.output_filepaths (COGs), res.stac_catalog_filepath, res.merged_filepath
```

- Model-free preflight: `fsd.model.bundle.read_spec("my_bundle")` reads bands/`T` from
  `bundle.json` with no import/model-load. `run_inference` asserts bands ⊇ `required_bands` and
  `T == n_timestamps` before any predict.
- Full Mode-A walkthrough on real data: `tests/manual/deploy.md`. Bundle mechanics explained:
  `specs/18-model-bundle-explainer.md`. Example adapter: `examples/eurocrops_rf.py`.

## ROI → S2-grid tiling (fsd.grid, spec 19)

Split an ROI into overlapping S2 cells (one cell = one inference datacube), clipped to the ROI.
Needs the `[grid]` extra (`pip install -e ".[grid]"` → s2 + s2cell).

```python
from fsd import grid
grids = grid.roi_to_s2_grids("shapefiles/inference_roi.geojson", grid_size_km=5, scale_fact=1.1)
grids.to_file("inference_s2_grids.geojson", driver="GeoJSON")   # cols: id, geometry (EPSG:4326)
# feed to workflows.create_datacube as the inference shapes (id_col="id")
```

## End-to-end demo (demo_01+02+03, spec 19)

Full Mode-A run on the existing Ethiopia data, in an isolated venv (keeps fsd's `.venv` lean):

```bash
cd fsd
python3.11 -m venv .venv-modeldeploy
.venv-modeldeploy/bin/pip install -e ".[dev,grid,model-example]"
.venv-modeldeploy/bin/python demos/e2e_ethiopia.py --fast     # ~1 min smoke (6 grids)
.venv-modeldeploy/bin/python demos/e2e_ethiopia.py --cores 8  # full run (300 grids, 1015 fields, T=19)
```

Outputs: `demos/figures/{s2_grids,ndvi_timeseries,crop_map}.png` (committed) + QGIS artifacts
(gridded ROI GeoJSON, per-grid COGs, STAC, merged display map) under `tests/outputs/demo_e2e/`
(gitignored). Report + finding (multi-zone display merge): `demos/README.md`.

## ROI inference in one call (`run_inference(roi=…)`, spec 21 / P0.75)

Tile an ROI → build a datacube per S2 grid cell → infer → per-cell COGs + STAC + merged map,
all local via the runner seam. Needs the `[grid]` extra (`.venv-modeldeploy`). The adapter must
be importable by `module:attr` (put it in a module on `PYTHONPATH`, not `__main__`):

```python
import datetime, geopandas as gpd
from shapely.geometry import box
import fsd
from ndvi_thresh import NDVIThresh          # an importable adapter module

res = fsd.run_inference(
    NDVIThresh(), output_folderpath="tests/outputs/roi_inference",
    roi=gpd.GeoDataFrame({"geometry": [box(36.20, 11.45, 36.28, 11.53)]}, crs="EPSG:4326"),
    catalog_filepath="../satellite_benchmark/sentinel-2-l2a/catalog.parquet",
    startdate=datetime.datetime(2018, 6, 1), enddate=datetime.datetime(2018, 7, 11),  # T=2 @ 20d
    mosaic_days=20, bands=["B04", "B08", "B8A", "SCL"],
    grid_size_km=5, scale_fact=1.1, merge="reproject", cores=2,
)
# res.grids_filepath, res.output_filepaths (per-cell COGs), res.stac_catalog_filepath, res.merged_filepath
```

- `merge`: `True` = strict single-CRS (refuses a zone-straddling ROI); `"reproject"` =
  cross-UTM-zone-safe merge to one CRS — the **max-total-area** zone, or a `merge_crs=<EPSG>` you
  pass; **lossless where a cell already matches the target**. Re-running resumes (Snakemake skips
  cells whose `done_infer.txt` exists).
- Full runbook: `tests/manual/roi_inference.md`. Real smoke: ~9 km ROI → 10 cells / 10 COGs in ~40 s.

## e2e LOCAL gate on fresh CDSE data — the go-to run-book (spec 23)

One command runs the whole local pipeline (download → jp2→COG → datacube → flatten → train →
bundle → ROI build+infer → COG/STAC/merged) on real Austria data, with decomposed download timings +
a throughput probe + a no-download ETA estimator. **Reusable template** — swap `--roi/--train`
(cross-UTM-zone ROIs supported). Needs CDSE creds + the `[dev,grid,model-example]` venv.

```bash
.venv-modeldeploy/bin/python demos/e2e_austria.py --creds /path/to/cdse_credentials.json
.venv-modeldeploy/bin/python demos/e2e_austria.py --fast   # 2-month window + small inference ROI
# your region:  --roi shapefiles/FR_ROI.geojson --train shapefiles/FR_FIELDS.geojson --id-col fid --label-col crop
```

Estimate another region **without downloading it** (uses a prior run's `timings.json → cost_model`):

```python
from estimate import estimate_run          # demos/estimate.py
estimate_run("FR_ROI.geojson", START, END, BANDS, creds=creds, cost_model=cost_model,
             max_cloudcover=70)             # -> {granules, cells, GB, download_min, compute_min, total_min}
```

- Missing imagery? the compute verbs now print an actionable `fsd.download(...)` plan
  (`cdse.plan_download`) — they never auto-fetch. Full guide: `demos/E2E_AUSTRIA.md`.

## Regenerate an output STAC's geometry from its manifest (spec 28)

The inference-output STAC Item `geometry` is the true S2-cell polygon (from
`input.csv.shapefilepath`), not the raster bbox — re-derive it any time (no re-inference):

```bash
.venv/bin/python -m demos.regen_output_stac \
    --input-csv tests/outputs/demo_e2e/model_outputs/cells/input.csv \
    --stac-dir tests/outputs/demo_e2e/model_outputs/stac
# writes a _result.json: {items, distinct_ids, non_rectangular_geoms}
```
Full runbook: `runbooks/28-stac-geometry-regen.md`.

## Serve the crop map to STACNotator (Tier-1 pre-styled XYZ, spec 29)

A minimal FastAPI/`rio-tiler` server over the demo's `merged.tif`, for STACNotator's
Bring-Your-Own-XYZ mode (no viewer, no pgSTAC — Tier 2 is the full stack):

```bash
python3.11 -m venv .venv-titiler && .venv-titiler/bin/pip install -e ".[titiler]"
.venv-titiler/bin/python -m demos.titiler_serve
# -> XYZ template: http://127.0.0.1:8000/cropmap/tiles/{z}/{x}/{y}.png
```

- **curl smoke:** `curl -s -o /tmp/t.png -w '%{http_code} %{content_type}\n'
  http://127.0.0.1:8000/cropmap/tiles/13/4437/2823.png` -> `200 image/png`.
- **QGIS quick-check:** Add Layer -> Add XYZ Layer, paste the template URL, pan to Austria —
  distinct class colors, transparent nodata, correctly placed.
- **STACNotator BYO:** paste the same template URL as a Bring-Your-Own-XYZ imagery slice.
- Full runbook (incl. the STACNotator step): `runbooks/29-tier1-stacnotator-byo.md`.
