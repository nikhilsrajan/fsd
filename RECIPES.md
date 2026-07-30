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

Full-year, multi-CRS Sentinel-2 L2A download (produced the `satellite_benchmark/` archive —
**⚠️ that archive was since DELETED for disk space; this recipe is kept as the how-to, but the
data it made is gone.** The current real-data archive is `fsd/tests/outputs/demo_e2e/imagery/`,
Austria — see CLAUDE.md).
Script: `fsd/benchmarks/download_year_ethiopia.py`. Report:
`benchmarks/download_report_2018_ethiopia.md`.

## Download (MPC → local COG archive, spec 32)

Microsoft Planetary Computer S2 L2A: anonymous discovery + a **pure COG byte-copy** download (no
`jp2->COG` conversion — MPC assets are already COG). Install the extra once: `pip install -e ".[mpc]"`.

```python
import datetime
import geopandas as gpd
from fsd.catalog.catalog import TileCatalog
from fsd.sources import mpc

roi = gpd.read_file("shapefiles/s2grid=476da24.geojson")
catalog = TileCatalog("imagery/catalog.parquet")
result = mpc.download(
    roi, datetime.datetime(2021, 11, 1), datetime.datetime(2022, 3, 1),
    ["B04"], "imagery", catalog, max_tiles=10, max_cloudcover=60.0, progress=True,
)
# catalog rows carry boa_add_offset: 0 pre-baseline-04.00, -1000 at/after 2022-01-25
```
Or via the high-level API: `fsd.download(roi, start, end, ["B04"], "imagery", source="mpc",
max_tiles=10)` (no `creds` needed). Full runbook (real network, one tile/band):
`runbooks/32-mpc-baseline.md`.

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

## Export a STAC catalog to stac-geoparquet (spec 30 Deliverable B)

```bash
python3.11 -m venv .venv-serving && .venv-serving/bin/pip install -e ".[dev,serving]"
.venv-serving/bin/python -m demos.mini_mpc.export_stac_geoparquet \
    --stac-dir tests/outputs/demo_e2e/model_outputs/stac
# writes catalog.parquet next to catalog.json + a _result.json: {items, dst}
```
Round-trip test: `.venv-serving/bin/python -m pytest -q tests/test_stac_geoparquet.py`
(skips cleanly in fsd's core `.venv` — `pytest.importorskip`).

## Serve fsd outputs through a local pgSTAC + titiler-pgstac "mini-MPC" (Tier 2, spec 30)

The register→searchId→XYZ flow MPC uses, over a stock local pgSTAC stack (`demos/mini_mpc/`):

```bash
cd demos/mini_mpc && cp -n .env.example .env && docker compose up --build -d && cd ../..
.venv-serving/bin/pip install "pypgstac[psycopg]==0.9.11" requests   # once, into .venv-serving

.venv-serving/bin/python demos/mini_mpc/load_pgstac.py \
    --stac-dir tests/outputs/demo_e2e/model_outputs/stac \
    --outputs-dir tests/outputs/demo_e2e/model_outputs/cells
# -> _result.json: {collections: 1, items: 300}

.venv-serving/bin/python demos/mini_mpc/register_and_url.py
# -> prints http://127.0.0.1:8082/searches/<id>/tiles/WebMercatorQuad/{z}/{x}/{y}.png?...

curl -s -o /tmp/t.png -w '%{http_code} %{content_type}\n' \
    "<paste the URL above, z=13 x=4437 y=2823>"   # -> 200 image/png
```
- **QGIS quick-check:** Add Layer -> Add XYZ Layer, paste the printed template as-is
  (`{z}/{x}/{y}` literal), pan to Austria — real class colors, **true (non-boxy) cell footprints**.
- Teardown: `docker compose down` (keeps `./.pgdata`) or `docker compose down -v` (wipes it).
- Full runbook (7 steps incl. the STAC search + optional STACNotator step):
  `runbooks/30-tier2-mini-mpc.md`. What's borrowed vs. locally built + why:
  `demos/mini_mpc/README.md`.

## Azure compute seam — `storage="azure"` (spec 31, P1)

`create_training_data`/`download` now accept `storage="azure"` (or `{"backend": "azure"}`):
it sets `FSSPEC_ABFSS_ANON=false` for the process (env + `fsspec.config.conf`), the one
config key adlfs needs — it then auto-resolves `DefaultAzureCredential` and every
`fs.*`/`rio_open` call against an `abfss://…` URL just works. No account/key config: the
storage account comes from the URL host itself (`abfss://<fs>@<account>.dfs.core.windows.net/<path>`).

```bash
# opt-in — core stays lean, this is NOT in [dev]
fsd/.venv/bin/pip install -e ".[dev,azure]"
az login   # or rely on the node's managed identity at P4 — DefaultAzureCredential tries both
export FSSPEC_ABFSS_ANON=false   # belt-and-suspenders; storage="azure" also sets this in-process
```

```python
import fsd
training = fsd.create_training_data(
    label_polygons, catalog_filepath="abfss://data@<account>.dfs.core.windows.net/p1-demo/imagery/catalog.parquet",
    startdate=..., enddate=..., mosaic_days=30, bands=["B08", "SCL"],   # SCL mandatory, TODO #35
    id_col="id", label_col="label",
    export_folderpath="abfss://data@<account>.dfs.core.windows.net/p1-demo/out/",
    storage="azure",
)
```

- `fsd.storage.azure.to_vsi(url)` — the deterministic `abfss://… -> /vsiadls/…` translation
  GDAL's pixel reads need (adlfs is not on GDAL's VSI path); local paths pass through unchanged.
- `fsd.raster.rio_open` is the one place that actually opens a raster — swapped in for bare
  `rasterio.open` at the 3 pixel-read sites (`raster/images.py`, `raster/cog.py`,
  `catalog/stac.py`). Nothing else in fsd needs to change to read/write blob.
- Real credentialed proof (staged data + a GDAL `/vsiadls/` read, before any of the above code
  existed): `runbooks/31-p1-upload-slice.md` + `runbooks/scripts/31_upload_slice.py` (ran green
  2026-07-17). Full compute-seam demo (build a datacube reading/writing blob):
  `runbooks/31-p1-datacube-on-blob.md`.
- **Not wired**: `download`-to-blob (`sources/mpc.py`/`sources/cdse.py` keep their local-only
  guards — suspended into the ingest/normalization contract spec, TODO #38) and
  `run_inference`/`deploy` (`storage_allowed=False` — P4/P5, TODO #39).

## Probe: does a GeoDataFrame's `.attrs` survive a GeoParquet write→read? (spec 35 / TODO #42)

Offline, ~2 s, read-only. Proves the TODO-#42 gap and validates the footer-metadata fix in one go —
re-run it after any `geopandas`/`pandas`/`pyarrow` bump, because geopandas
[PR #3597](https://github.com/geopandas/geopandas/pull/3597) (merged 2025-10-30) will change the
first answer from `{}` to the round-tripped attrs.

```bash
.venv/bin/python - <<'PY'
import geopandas as gpd, pandas as pd, pyarrow as pa, pyarrow.parquet as pq, io, json, shapely
print("geopandas", gpd.__version__, "| pandas", pd.__version__, "| pyarrow", pa.__version__)

g = gpd.GeoDataFrame({"id": ["a"], "geometry": [shapely.box(0, 0, 1, 1)]}, crs="EPSG:4326")
g.attrs["declaration"] = {"x": 1}
buf = io.BytesIO(); g.to_parquet(buf)
print("geopandas attrs survive? ", gpd.read_parquet(io.BytesIO(buf.getvalue())).attrs)   # {} on 1.1.4

df = pd.DataFrame({"a": [1]}); df.attrs["declaration"] = {"x": 1}
b = io.BytesIO(); df.to_parquet(b, engine="pyarrow")
print("pandas attrs survive?    ", pd.read_parquet(io.BytesIO(b.getvalue())).attrs)      # {'declaration': ...}
print("pandas footer keys:      ", list(pq.read_table(io.BytesIO(b.getvalue())).schema.metadata))

# the spec-35 route: stamp a footer key, keep the file valid GeoParquet
t = pq.read_table(io.BytesIO(buf.getvalue()))
md = dict(t.schema.metadata); md[b"PANDAS_ATTRS"] = json.dumps({"fsd:declaration": {"v": 1}}).encode()
out = io.BytesIO(); pq.write_table(t.replace_schema_metadata(md), out); raw = out.getvalue()
print("stamped file still reads:", gpd.read_parquet(io.BytesIO(raw)).crs.to_string())
print("footer-only read:        ", list(pq.read_metadata(io.BytesIO(raw)).metadata))
PY
```

**Expected (geopandas 1.1.4 / pandas 3.0.3 / pyarrow 24.0.0):** geopandas `{}`, pandas
`{'declaration': {'x': 1}}` with a `PANDAS_ATTRS` footer key, the stamped file still readable as
GeoParquet, and `pq.read_metadata` listing `PANDAS_ATTRS` + `geo` **without reading a row group**.
⚠️ Never put a dataclass in `.attrs` — JSON-encoding it warns *"defaulting to empty attributes"* and
raises `TypeError` (spec 35 §2a).

**Implemented 2026-07-21** (spec 35, closing TODO #42): the footer route above is now
`fsd.storage.fs.write_parquet`/`read_parquet`, generically, for any `.attrs`.

## Re-stamp / inspect a catalog's `SourceDeclaration` (spec 35 §6)

A catalog written before spec 35 (or by code that forgets to pass `declaration=` to
`TileCatalog.append`) carries no `fsd:declaration` footer stamp — `flatten_catalog`/
`build_datacube` now raise on it (§5a) rather than silently defaulting to S2. No
re-download is needed — `restamp_cli` rewrites only the catalog Parquet (a KB-MB
read + re-write in place; the imagery it points at is untouched) and
`inspect_cli` reads the footer only (no row group). Both go through
`fsd.storage`, so they work on `abfss://`/`s3://` too.

```bash
# stamp (or re-stamp) a catalog -- refuses to overwrite a *different* existing stamp
# without --force; idempotent against the same declaration.
.venv/bin/python -m fsd.catalog.restamp_cli /path/to/catalog.parquet --declaration s2_l2a

# print the stamped declaration, footer-only (no row group read) -- the sidecar's
# human-legibility without its separation risk.
.venv/bin/python -m fsd.catalog.inspect_cli /path/to/catalog.parquet
```

The four catalogs known to need this (spec 35 §6): the Austria `demo_e2e/imagery/
catalog.parquet`, `mpc_baseline/imagery/`, the `rise` blob catalog from runbook
`34-download-to-blob`, and per-cell slices in old run folders — folded into TODO #44's
re-ingest rather than run separately.

## Run the datacube fan-out on the AML cluster (spec 36, P2)

`runner="aml"` dispatches the **same** build fan-out `runner="local"` runs, as shards on
`rise`'s AML cluster, instead of Snakemake-on-this-laptop:

```python
from fsd import api

api.create_training_data(
    ..., runner="aml",
    runner_kwargs=dict(
        cluster="<the d16 cluster name>",       # AZURE_INFRA_PRIVATE.md
        environment="fsd-aml-env:1",             # spec 36 D5 -- build once, see runbooks/36-aml-runner.md
        root="abfss://<fs>@<account>.dfs.core.windows.net/<prefix>",
        identity_client_id="<compute identity client id>",  # az identity show --query clientId
        n_shards=8,                              # default: the cluster's max_instances
    ),
)
```

Or call the runner directly for a from-a-run-folder `input.csv` without going through
`create_training_data`: `fsd.workflows.runners.run_aml(csv_filepath, cluster=..., ...)`.
Never hardcode `cluster`/`identity_client_id` in anything under `fsd/` — they are
concrete `rise` identifiers (`AZURE_INFRA_PRIVATE.md`, workspace root, not a git repo).

## Run download-to-blob on the AML cluster (spec 37, P2)

`runner="aml"` dispatches the download itself onto `rise`, colocated with blob, instead
of relaying every byte through the driver machine. Dispatch shape is **per-source**
(D1): CDSE always runs as **one** job (its S3 concurrency cap is per-credential, so
fan-out can't help); MPC **fans out** across N nodes (no per-credential cap — Azure
Blob throughput scales with parallelism):

```python
from fsd import api

# CDSE -- one job. S3 creds are read on the node from exactly one of two mutually
# exclusive sources (D5 REVISED): Key Vault OR a blob JSON. roi must be a url the
# node can also read (not an in-memory GeoDataFrame).
api.download(
    "shapefiles/roi.geojson", startdate, enddate, ["B04", "B08", "SCL"],
    "abfss://<fs>@<account>.dfs.core.windows.net/<prefix>",
    source="cdse", max_tiles=200, runner="aml",
    runner_kwargs=dict(
        cluster="<the d16 cluster name>",        # AZURE_INFRA_PRIVATE.md
        environment="fsd-aml-env:1",              # spec 36 D5's Environment, reused
        root="abfss://<fs>@<account>.dfs.core.windows.net/<prefix>",
        identity_client_id="<compute identity client id>",   # az identity show --query clientId
        vault_url="<rise Key Vault url>",          # AZURE_INFRA_PRIVATE.md -- Key Vault path
        secret_name="<CDSE creds secret name>",
        # -- OR (mutually exclusive with vault_url/secret_name) --
        # creds_url="abfss://<fs>@<account>.dfs.core.windows.net/<prefix>/_secrets/cdse_credentials.json",
    ),
)

# MPC -- fans out across N shards (default: the cluster's max_instances); anonymous,
# no vault_url/secret_name/creds_url needed.
api.download(
    "shapefiles/roi.geojson", startdate, enddate, ["B04", "B08", "SCL"],
    "abfss://<fs>@<account>.dfs.core.windows.net/<prefix>",
    source="mpc", max_tiles=200, runner="aml",
    runner_kwargs=dict(
        cluster="<the d16 cluster name>", environment="fsd-aml-env:1",
        root="abfss://<fs>@<account>.dfs.core.windows.net/<prefix>",
        identity_client_id="<compute identity client id>", n_shards=8,
    ),
)
```

Or call the dispatcher directly: `fsd.workflows.runners.run_aml_download(roi, startdate,
enddate, bands, dst_folderpath, catalog_filepath, source=..., cluster=..., ...)`. Same
identity/environment reuse as spec 36; never hardcode `cluster`/`identity_client_id`/
`vault_url`/`creds_url` in anything under `fsd/` (concrete `rise` identifiers,
`AZURE_INFRA_PRIVATE.md`). Full phased validation, including the blob `_secrets/` push/delete
(D5 REVISED): `runbooks/37-download-on-aml.md`; datacube fan-out validation (spec 36):
`runbooks/36-aml-runner.md`.

## Flatten already-built blob cubes on the AML cluster + land locally (spec 39, P2)

`flatten_training_data(runner="aml")` turns an existing `input.csv` of blob cube paths (e.g.
runbook 36 Phase 3's own `input.csv`) into ONE compact training array — a single-node reduce,
not a fan-out — and brings the array home to a **local** folder:

```python
from fsd import api

td = api.flatten_training_data(
    "abfss://<fs>@<account>.dfs.core.windows.net/<prefix>/runs/<phase3-run-id>/input.csv",
    export_folderpath="tests/outputs/training_data",   # LOCAL
    id_col="id", label_col="label",                    # label_col optional (D-labels)
    runner="aml",
    runner_kwargs=dict(
        cluster="<the d16 cluster name>",        # AZURE_INFRA_PRIVATE.md
        environment="fsd-aml-env:1",              # spec 36 D5's Environment, reused (no adapter)
        root="abfss://<fs>@<account>.dfs.core.windows.net/<prefix>",
        identity_client_id="<compute identity client id>",
    ),
)
print(td.n_pixels, td.n_timestamps, td.bands)
```

Or dispatch the reduce directly: `fsd.workflows.runners.run_aml_flatten(input_csv,
export_folderpath, id_col=..., cluster=..., ...)` — `export_folderpath` there is the **blob**
prefix the node writes to; land-local is `api._land_local`, called for you above.

## Full one-verb e2e: download → build → flatten → land-local on AML (spec 39, P2)

`create_training_data` grows an optional download phase and becomes the full-pipeline façade —
one call chains MPC/CDSE download, the per-cell build fan-out (spec 36), and the flatten reduce
+ land-local (spec 39), all against the SAME blob `root`:

```python
from fsd import api
import geopandas as gpd

fields = gpd.read_file("shapefiles/austria_eurocrops_sampled_ethiopia_translated.geojson")

td = api.create_training_data(
    label_polygons=fields,   # in-memory gdf -- auto-staged to the blob root once (Q3)
    catalog_filepath="abfss://<fs>@<account>.dfs.core.windows.net/<prefix>/catalog.parquet",
    startdate="2018-04-01", enddate="2018-09-01", mosaic_days=20,
    bands=["B04", "B08", "B8A", "SCL"], id_col="fid", label_col="EC_hcat_n",
    export_folderpath="tests/outputs/training_data",   # LOCAL -- always, both runners
    source="mpc", download=True, max_tiles=700,        # max_tiles required when download=True
    runner="aml",
    runner_kwargs=dict(
        cluster="<the d16 cluster name>", environment="fsd-aml-env:1",
        root="abfss://<fs>@<account>.dfs.core.windows.net/<prefix>",   # catalog/cubes/input.csv/
                                                                        # the raw reduce output
        identity_client_id="<compute identity client id>",
    ),
    # adapter=DemoRF(),   # optional -- runs on the DRIVER after land-local (D2/ADR-0020),
                           # never on a cluster node.
)
```

`download=False` (default) keeps the existing "catalog must already exist" behavior — pass
`download=True` only when there is no catalog yet. `export_folderpath` is always the LOCAL
landing target; never pass a blob URL there. Full phased validation:
`runbooks/39-training-data-on-aml.md`.

## Sweep tracked files for concrete `rise` identifiers (pre-push hygiene)

`fsd/` is a **public** MIT repo; the concrete `rise` names/IDs live only in
`AZURE_INFRA_PRIVATE.md` at the workspace root. This catches a placeholder that got
written as a real value. Found two real leaks on 2026-07-22 (spec 37's Key Vault + VM
names, and an older storage-account name in `runbooks/34-download-to-blob.md`).

Run from the `fsd/` checkout, with the private doc one level up:

```bash
grep -oE '`[a-z0-9][a-zA-Z0-9._-]{5,}`' ../AZURE_INFRA_PRIVATE.md | tr -d '`' | sort -u \
  > /tmp/concrete.txt
while read -r v; do
  files=$(git ls-files -z | xargs -0 grep -lF "$v" 2>/dev/null)
  [ -n "$files" ] && echo "TRACKED HIT: $v -> $(echo $files | tr '\n' ' ')"
done < /tmp/concrete.txt
```

- `git ls-files` (not a bare `grep -r`) is the point: it scans **only tracked files**, so
  gitignored local artifacts (`tests/outputs/`, scratch notebooks) don't drown the signal —
  they never reach GitHub.
- **Known-clean false positives:** `identityReference` (an Azure Batch API field) and
  `prevent_destroy` (a Terraform lifecycle meta-argument) in `AZURE_INFRA.md` — generic API
  terms that happen to appear in the private doc's Terraform excerpts, not identifiers. Since
  2026-07-30 also `env.example.sh` / `env.local.sh` (fsd's own filenames), `fsd-aml-env` /
  `fsd-infer-env` (fsd's own AML environment names) and `030f6ac` (an fsd commit sha) — all
  named in the private doc, none of them `rise` identifiers.
- **Found 2026-07-30 (spec 41 P4):** `cluster-rise-d16`, the concrete cluster name, in a comment
  in `src/fsd/workflows/runners.py` and a docstring in `demos/plot_aml_timings.py`. Both scrubbed
  forward to `cluster-<proj>-d16` + a pointer. **Run this sweep after any session that writes
  prose about a real run** — that is how both of these got in, and how 2026-07-22's two did.
- A real hit is scrubbed by replacing it with the private doc's **placeholder** form plus a
  pointer (e.g. `` the `rise` storage account (`st<proj>`, concrete name in
  `AZURE_INFRA_PRIVATE.md`) ``). Note this is scrub-*forward* only — if the leaking commit
  is already pushed, the value stays in history unless you rewrite + force-push.

## Verify a worktree's code against the repo's FULL dependency set (test/lint parity)

A per-spec worktree `.venv` built with a bare `pip install -e ".[dev]"` is **not** equivalent
to the repo `.venv`, and the difference reads as a regression when it isn't. Two traps
(diagnosed 2026-07-28 while reviewing TODO #57):

- **Fewer tests.** The optional extras aren't installed, so `tests/test_azure_seam.py` (25
  tests, needs `adlfs`) and `tests/test_grid.py` (4 tests, needs `s2sphere`) `importorskip` at
  module level → `411 passed / 4 skipped` instead of `436 / 2`. Nothing is silently
  uncollected, but **`test_azure_seam.py` is exactly the module that covers `fsd.storage`**
  (`test_memory_scheme_roundtrip_parquet_and_npy` exercises `save_npy`/`write_parquet`), so a
  storage change "verified" in a bare worktree venv is unverified where it matters.
- **A different ruff.** The fresh venv resolves a newer ruff (0.16.0 vs the repo venv's
  0.15.20) with a much larger default rule set → hundreds of findings, which invites narrowing
  to `--select E4,E7,E9,F,I` and thereby *hiding* real ones. `pyproject.toml` is read correctly
  in both — it is a version difference, **not** a git-worktree config-discovery quirk.

Run the worktree's **code** against the repo's **deps** instead of rebuilding the venv:

```bash
REPO=/path/to/fsd; WT=$REPO/.claude/worktrees/<name>
cd "$WT"
PYTHONPATH="$REPO/.venv/lib/python3.11/site-packages" "$WT/.venv/bin/python" -m pytest -q
"$REPO/.venv/bin/ruff" check --config pyproject.toml src tests
```

The worktree's own editable `fsd` still wins on `sys.path`: a `.pth`-installed editable finder
is only processed in a real *site* directory, not in a `PYTHONPATH` entry — so imports resolve
to the worktree's `src/fsd`, while `adlfs`/`s2sphere`/etc. come from the repo venv. Sanity-check
with `python -c "import fsd; print(fsd.__file__)"` before trusting the run.

---

## Harvest every timing that was ever measured (`_result.json` sweep)

The one reliable way to answer "what do we actually have a number for?" — the run-books' stored
results carry timings at inconsistent depths (`wall_seconds` at the top for run-books 38–40,
per-shard `seconds` nested under `result.shards`/`result.reports` for 36–37). Written 2026-07-28
while sourcing `demos/E2E_AUSTRIA_AML.md`; it is what found the per-shard seconds everyone thought
were missing, and the band-stratified shard imbalance (TODO #60).

```bash
cd fsd && python3 - <<'PY'
import glob, json

def walk(d, pre=""):
    out = {}
    if isinstance(d, dict):
        for k, v in d.items():
            if isinstance(v, (dict, list)):
                out.update(walk(v, pre + k + "."))
            elif any(t in k.lower() for t in
                     ("second", "wall", "time", "elapsed", "duration", "speedup")):
                out[pre + k] = v
    elif isinstance(d, list):
        for i, v in enumerate(d):
            out.update(walk(v, pre + str(i) + "."))
    return out

for f in sorted(glob.glob("tests/outputs/**/*result*.json", recursive=True)):
    t = walk(json.load(open(f)))
    if t:
        print(f"\n### {f}")
        for k, v in t.items():
            print(f"   {k} = {v}")
PY
```

**Read the per-shard seconds, not just the max.** Equal `n_units` with unequal `seconds` is a
partitioner problem, not noise — that is exactly how TODO #60 surfaced.

## Run the whole cluster demo as one script, then render its timing figures (spec 40, P2)

Replaces hand-running run-books 36→37→39→40→38 for a fresh AML demo. See
`demos/E2E_AUSTRIA_AML.md` §8 for the full env-var contract and VM prerequisites — this is just the
two commands once that's set up.

```bash
# ALL SIX extras -- `[dev,azure,aml]` alone gets you to 4_train_bundle and then dies on
# `ModuleNotFoundError: joblib`, after the download has been paid for (2026-07-29).
# fsd core is deliberately lean: it never trains a model, so sklearn/joblib are an extra.
pip install -e ".[dev,azure,aml,mpc,grid,model-example]"

# estimate first, zero side effects (D6); then the real run under tmux (D7)
python demos/e2e_austria_aml.py --fresh --dry-run
python demos/e2e_austria_aml.py --fresh --confirm-spend

# a partial/failed run resumes with the SAME id it printed -- completed steps skip instantly (D5)
python demos/e2e_austria_aml.py --run-id <id> --confirm-spend

# figures render OFF-BOX from timings.json alone, no cluster/network needed (D12)
python demos/plot_aml_timings.py tests/outputs/demo_e2e_aml/<run_id>/timings.json
```

`timings.json` is self-contained (D9): send back that one file and the plotter reproduces every
figure anywhere. `_timing.json` (the per-run dispatch telemetry `workflows.runners._aml_submit_and_wait`
writes beside `_status/`, ADR 0021) is embedded inside it — no separate forensics run-book needed
going forward (that was run-book 41's whole job, now free).

## Rebuild BOTH AML Environments (after any fsd change that runs on a node)

**The node's `fsd` comes from the image, not from your checkout.** `git pull` on the driver
changes nothing about what executes on the cluster: the AML Environment bakes in a wheel, so any
change under `src/fsd/workflows/`, `sources/`, `datacube/`, `raster/` or `model/` needs a rebuild
before the cluster sees it. Skipping this is silent — the run stays green and produces correct
science, it just behaves like the old code.

**Worked example (2026-07-29):** spec 40's four in-job stamps were added, the driver was updated,
the images were not. A complete 25-minute demo run came back with `job_admission_seconds: null` on
all 97 jobs — D11's headline metric, gone, with nothing failing. `demos/e2e_austria_aml.py` now
gates on this after the first dispatch, but the cheap fix is to rebuild first.

Full context + failure modes: `runbooks/36-aml-runner.md` (general-purpose) and
`runbooks/38-inference-on-aml.md` §"the inference Environment (D4)". This is the two builds in one
place, for when you already know why.

**Where to run it:** anywhere with a working `az` + `ml` extension and network access to the
workspace — the image builds in **ACR, not locally**, so no Docker is needed on your machine.
`build.path` only uploads the context. From a laptop this means **the VPN must be on**: the upload
lands in the workspace's own storage account, which is deny-by-default firewalled like every other
account in the project.

```bash
cd /path/to/fsd
git pull                      # FIRST -- the wheel is built from the working tree
export OUT="${OUT:-$HOME/fsd-envs}" && mkdir -p "$OUT"
# assumes AZ_RG / AZ_ML_WORKSPACE / AZ_ENV_NAME / AZ_INFER_ENV_NAME are exported

# Guard: `export VAR="$(az ...)"` CANNOT fail -- export always returns 0, so a broken az
# silently assigns its error text and every later command uses a garbage version. Seen live
# 2026-07-29: `built fsd-aml-env:No module named 'rpds.rpds'`. Validate before continuing.
_fsd_check_version() {   # $1 = name, $2 = captured value
  case "$2" in
    ''|*[!0-9]*) printf '\n!! FAILED: %s came back as %s -- not a version number.\n' \
                        "$1" "${2:-<empty>}" >&2
                 printf '   STOP. Do not run the next block; see "az CLI gotchas" below.\n\n' >&2
                 return 1;;
  esac
  printf 'ok: %s=%s\n' "$1" "$2"
}

# --- 1. general-purpose image: download + datacube build + flatten -------------------
rm -rf "$OUT/env_src" && mkdir -p "$OUT/env_src"
.venv/bin/pip wheel . --no-deps -w "$OUT/env_src" && ls "$OUT"/env_src/fsd-*.whl

cat > "$OUT/env_src/Dockerfile" <<'DOCKER'
FROM mcr.microsoft.com/azureml/openmpi4.1.0-ubuntu22.04:latest
COPY fsd-*.whl /tmp/
# [azure] -> adlfs + azure-identity + azure-keyvault-secrets;  [mpc] -> planetary-computer.
# NOT [aml]: azure-ai-ml is driver-side only -- the node never submits jobs.
RUN python -m pip install --no-cache-dir "$(ls /tmp/fsd-*.whl)[azure,mpc]" \
 && python -m pip cache purge || true
DOCKER

cat > "$OUT/env.yml" <<YML
\$schema: https://azuremlschemas.azureedge.net/latest/environment.schema.json
name: ${AZ_ENV_NAME}
build:
  path: ./env_src
  dockerfile_path: Dockerfile
YML

AZ_ENV_VERSION="$(az ml environment create -f "$OUT/env.yml" \
  -g "$AZ_RG" -w "$AZ_ML_WORKSPACE" --query version -o tsv)"
_fsd_check_version AZ_ENV_VERSION "$AZ_ENV_VERSION" && export AZ_ENV_VERSION \
  && echo "built ${AZ_ENV_NAME}:${AZ_ENV_VERSION}"

# --- 2. inference image: the same, PLUS the adapter + its runtime deps ---------------
export AZ_ADAPTERS_SRC="${AZ_ADAPTERS_SRC:-demos/adapters.py}"
rm -rf "$OUT/infer_env_src" && mkdir -p "$OUT/infer_env_src/adapter_src"
.venv/bin/pip wheel . --no-deps -w "$OUT/infer_env_src" && ls "$OUT"/infer_env_src/fsd-*.whl
cp -r "$AZ_ADAPTERS_SRC" "$OUT/infer_env_src/adapter_src/"

cat > "$OUT/infer_env_src/Dockerfile" <<'DOCKER'
FROM mcr.microsoft.com/azureml/openmpi4.1.0-ubuntu22.04:latest
COPY fsd-*.whl /tmp/
COPY adapter_src/ /opt/adapter/
# scikit-learn + joblib are the adapter's runtime deps -- the two lines this adds over image 1.
RUN python -m pip install --no-cache-dir "$(ls /tmp/fsd-*.whl)[azure,mpc]" scikit-learn joblib \
 && python -m pip cache purge || true
# Importable as `adapters` -- the SAME name bundle.json's `adapter` ref uses (`adapters:DemoRF`).
ENV PYTHONPATH=/opt/adapter
DOCKER

cat > "$OUT/infer-environment.yml" <<YML
\$schema: https://azuremlschemas.azureedge.net/latest/environment.schema.json
name: ${AZ_INFER_ENV_NAME}
build:
  path: ./infer_env_src
  dockerfile_path: Dockerfile
YML

AZ_INFER_ENV_VERSION="$(az ml environment create -f "$OUT/infer-environment.yml" \
  -g "$AZ_RG" -w "$AZ_ML_WORKSPACE" --query version -o tsv)"
_fsd_check_version AZ_INFER_ENV_VERSION "$AZ_INFER_ENV_VERSION" && export AZ_INFER_ENV_VERSION \
  && echo "built ${AZ_INFER_ENV_NAME}:${AZ_INFER_ENV_VERSION}"

echo "export AZ_ENV_VERSION=$AZ_ENV_VERSION AZ_INFER_ENV_VERSION=$AZ_INFER_ENV_VERSION"
```

**Version is omitted on purpose** — AML auto-increments, so a rebuild always lands on a NEW version
and never mutates one a previous run referenced. Capture what it assigned (the last `echo`) and
export both in every later shell.

- **Lost a version?** `az ml environment list -n "$AZ_ENV_NAME" -g "$AZ_RG" -w "$AZ_ML_WORKSPACE" --query "[].version" -o tsv | sort -V | tail -1`
- **Verify:** `az ml environment show -n "$AZ_ENV_NAME" --version "$AZ_ENV_VERSION" -g "$AZ_RG" -w "$AZ_ML_WORKSPACE" --query "[name, version]" -o tsv`. `--version` is **required** — without it the CLI fails with `Must provide either version or label`. Don't query `provisioning_state`: it is not in the environment schema, and `--query` on a missing field prints an empty line that reads like a failure.
- **Each build is ~10–20 min of ACR time and occasionally flaky** — which is exactly why the demo script verifies Environments rather than building them (spec 40 D4): one bad build must not kill a 40-minute unattended run.
- ⚠️ **WAIT for the `prepare_image` build to finish before launching anything against the new version — nothing will stop you otherwise.** `az ml environment create` registers the *asset* immediately and returns; the image builds asynchronously. The v2 `Environment` object carries **no build state whatsoever** (`base_path, conda_file, creation_context, dump, id, validate, version` — verified 2026-07-29), so `ml_client.environments.get(name, version)` succeeds against a half-built image and **the demo's D4 preflight goes green regardless**. Submit early and the jobs do not fail — they sit in *Preparing* until ACR is done, and that wait lands between `submitted_at` and `process_start_at`, i.e. **inside `job_admission_seconds`**. A 15-minute build would silently become 15 minutes of "admission" in D11's headline metric. Watch it finish:
  ```bash
  # the image build appears as a job in the workspace; wait for Completed
  az ml job list -g "$AZ_RG" -w "$AZ_ML_WORKSPACE" \
    --query "[?contains(name,'prepare_image')].{name:name,status:status}" -o table
  ```
  Or Studio → Environments → the new version → build log. Wait for **both** images.

### az CLI gotchas (both cost a build attempt on 2026-07-29)

**1. `az ml` auto-upgrades itself and cannot, on an AML compute instance.** The `ml` extension
there is installed **system-wide** at `/opt/az/extensions/ml`, owned by root, but you run as
`azureuser`. Any `az ml …` command may decide to upgrade it, fail with
`Permission denied: '/opt/az/extensions/ml/…'`, and leave it **half-deleted** — after which every
`az ml` call dies with `FileExistsError: /opt/az/extensions/ml` or
`No module named 'rpds.rpds'`. Fix without root by giving yourself a private extension dir:

```bash
export AZURE_EXTENSION_DIR="$HOME/.azure/cliextensions"     # put this in ~/.bashrc
mkdir -p "$AZURE_EXTENSION_DIR"
az extension add -n ml                                       # your own copy, no sudo
az config set extension.use_dynamic_install=no               # never auto-install again
az ml -h >/dev/null && echo "ml extension OK"
```

Or just **build from a laptop** with a working `az` — the image builds in ACR either way, so the
only thing the build machine needs is the CLI and (off-network) the VPN.

**2. `export VAR="$(az …)"` swallows the failure.** `export` always returns 0, so a broken CLI
assigns its *error text* as the version and the run continues with garbage — the literal output was
`built fsd-aml-env:No module named 'rpds.rpds'`. That is why the block above captures first,
validates with `_fsd_check_version`, and only then exports.
