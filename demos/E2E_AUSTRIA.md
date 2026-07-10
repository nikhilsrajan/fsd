# Running fsd locally — the end-to-end guide (Austria)

**This is the go-to doc for running fsd on your own machine.** It walks the whole local pipeline on
real, freshly-downloaded Sentinel-2 data, explains every stage (including **how to bundle your own
model**), and records real timings you can extrapolate from. Driver: `demos/e2e_austria.py`
(spec 23). Model quality here is not meaningful (a demo RF) — this validates the *plumbing + timings*.

---

## 1. What fsd does locally

```
  fsd.download            fsd.create_training_data                 fsd.run_inference(roi=…)
 ┌────────────┐   catalog  ┌──────────────────────────┐   bundle   ┌───────────────────────────┐
 │ CDSE STAC  │──────────▶ │ build datacubes over the │ ─────────▶ │ tile ROI → S2 cells;      │
 │ + S3 .jp2  │  (parquet  │ label fields → FLATTEN → │  (model)   │ per cell: build cube +    │
 │ → COG      │   + COGs)  │ features.npy  → train RF │            │ infer → COG; +STAC +merge │
 └────────────┘            └──────────────────────────┘            └───────────────────────────┘
   step 2                     steps 3–4                               step 5
```

The user-facing surface is **four verbs**: `fsd.download`, `fsd.create_training_data`,
`fsd.run_inference`, `fsd.deploy` (the last a P6 stub). Every verb **preflights** — it asserts
bands / T / inputs and fails fast with a clear message *before* any heavy compute, so most mistakes
surface in seconds, not after an hour.

---

## 2. Where the imagery comes from — `fsd.download` is a separate step, and why (CDSE now; MPC later)

- **Download is its own verb, run once, up front** (`fsd.download` → a `catalog.parquet` + local
  COGs). The compute verbs (`create_training_data`, `run_inference`) **read** that catalog and
  **never call CDSE themselves.** If imagery is missing they stop with an **actionable download
  plan** (the exact `fsd.download(...)` to run), never a silent auto-fetch. Step 2 of the demo *is*
  that download.
- **Why separate — three reasons, not just quota:** (1) **CDSE quota** — one controlled pull, not N
  pulls from N workers; (2) **redundant fan-out** — 1,000 grid cells over overlapping MGRS tiles
  would otherwise refetch the same bytes 1,000×; (3) **the Batch model** — download once → storage
  (local now, Azure Blob later) → compute reads from the storage seam.
- **CDSE needs the download because it serves quota'd S3 `.jp2`**, which fsd **converts to COG on
  arrival** (the native ingest format the datacube build reads fast). So with CDSE, `download` is
  **required** before the compute verbs.
- **How this changes with Microsoft Planetary Computer (MPC), later.** MPC serves **COGs over public
  HTTP + STAC** — no quota, and no conversion needed. fsd will read MPC pixels **in place** through
  the GDAL VSI path it already uses for raster reads; an MPC-backed catalog is just a `TileCatalog`
  of `/vsicurl/https://…` COG URLs. The verbs don't change and there's **no `if source==…` branch** —
  point them at an MPC catalog and it "just works" because there is nothing to materialize, so the
  missing-data guardrail never fires. **CDSE → `download` required; MPC → `download` optional.**
  *(MPC is forward design — not built yet; TODO #21.)*
- **CDSE is intermittently flaky (BUG-001), and that's expected.** Discovery (STAC) is **anonymous**;
  only the byte download needs **S3 keys**. The download is **idempotent** (skips files on disk),
  fail-fast with a **circuit breaker**, and wrapped in a **resume-loop** — if a pass trips on a bad
  CDSE window, **just re-run the script; it resumes** and completes the remainder. A slow/failing
  pass is not a fsd bug.

---

## 3. Prerequisites

- **Python 3.11** and the isolated demo venv (keeps fsd core lean):
  ```bash
  python3.11 -m venv .venv-modeldeploy
  .venv-modeldeploy/bin/pip install -e ".[dev,grid,model-example]"
  ```
  The extras are split deliberately: **`[grid]`** = `s2`/`s2cell` (ROI→S2-cell tiling — *not* in
  core, which is why `fsd.grid` is an optional import); **`[model-example]`** =
  `scikit-learn`/`joblib`/`matplotlib` (the demo model + plots, *not* fsd itself — fsd never
  trains); `[dev]` = ruff/pytest; `[azure]` = `adlfs` (Phase-2, unused in v1).
- **CDSE credentials** — a gitignored `cdse_credentials.json` with the legacy keys
  (`sh_clientid`/`sh_clientsecret` for discovery, `s3_access_key`/`s3_secret_key` for download).
  Point the script at it with `--creds /path/to/cdse_credentials.json` or `$CDSE_CREDENTIALS_JSON`.
  S3 keys **can expire** — the script warns via `CdseCredentials.is_expired`.
- **No VPN required.** fsd talks to CDSE over the public internet; a VPN only affects *your* measured
  throughput (see §10) — it is never a setup step to reproduce.

---

## 4. Reuse it for your own region (change 3 things)

```bash
.venv-modeldeploy/bin/python demos/e2e_austria.py \
    --roi   shapefiles/YOUR_ROI.geojson \
    --train shapefiles/YOUR_FIELDS.geojson \
    --id-col fid --label-col crop
```

Everything else — download, tiling, build, infer, merge — is unchanged, **including cross-UTM-zone
ROIs** (France, Russia): each cell builds a datacube in its own CRS, and the merged map reprojects
all cells to one CRS (`merge="reproject"`, area-dominant target, or a `merge_crs=` you choose). The
**model** (adapter + bands) is the separate, model-developer-owned part (§6). The "swap these"
inputs are also named constants at the top of the script (`ROI_FP`, `TRAIN_FP`, `ID_COL`,
`LABEL_COL`).

---

## 5. Run it

```bash
.venv-modeldeploy/bin/python demos/e2e_austria.py --creds /path/to/cdse_credentials.json
.venv-modeldeploy/bin/python demos/e2e_austria.py --fast            # 2-month window + small inference ROI
.venv-modeldeploy/bin/python demos/e2e_austria.py --tiny-download   # tiniest: also clip the DOWNLOAD
```

Smoke levels (increasing download cost): **`--tiny-download`** clips *both* the download and the
inference ROI to one small central slice (few granules, trains only on fields inside it — the
fastest true end-to-end); **`--fast`** shortens the window + shrinks the *inference* ROI but still
downloads the full ROI; no flag = full season over the whole ROI. `--cores` (training-data build
parallelism), `--infer-cores` (inference build+infer parallelism — **keep low**, each ~5×5 km cube
is memory-heavy; defaults to `max(1, cores//4)`).
The 7 steps and what they produce (all heavy artifacts under `tests/outputs/demo_e2e/`, gitignored):

| step | produces |
|------|----------|
| 0 preflight | validates creds + inputs |
| 1 tiling | `inference_s2_grids.geojson` + `figures/s2_grids.png` |
| 2 download | `imagery/catalog.parquet` + local COGs; the timing report (§8) |
| 3 training data | `training_data/features.npy` (+ raw `data.npy`) |
| 4 train + bundle | `rf.joblib` + `bundle/` (`bundle.json` + artifact) |
| 5 run_inference | `model_outputs/<cell>/output.tif` per cell + `stac/` + `merged.tif` |
| 6 plots | `figures/ndvi_timeseries.png`, `figures/crop_map.png` |
| 7 report | `timings.json` (incl. the `cost_model`) + the ETA estimator |

---

## 6. Bundling YOUR model — the step-by-step guide

**fsd owns the plumbing** (download, datacube, flatten, tiling, COG/STAC/merge, runner). **The model
developer owns the two endpoints** that connect a model to fsd. Write a small adapter (the
`ModelAdapter` Protocol is duck-typed — any framework; subclass `BaseModelAdapter` for defaults, so
it's ~10 lines), then `bundle.save`. See `demos/adapters.py::DemoRF` for a complete worked example.

**6.1 Declarations** (read at preflight, before any heavy compute):
`required_bands`, `n_timestamps` (T the model was trained on — leave `0`/model-determined if it
varies per model), `output_dtype`, `output_nodata`, `output_band_names` (1 name → categorical map;
N → probabilities/regression).

**6.2 Endpoint ① — datacube → model input** (developer-owned). The feature transform, declared
**once** and run by fsd at **both** training and inference (the anti-skew guarantee — train and
serve see identical features):
- `feature_sequence` — a `fsd.bands.modify` pipeline `[(fn, kwargs), …]` on the 5-D
  `(samples, T, H, W, bands)` contract (the primary, declarative way); **or** override
  `features(data5d, band_indices)` for logic the sequence can't express.
- `datacube_to_X(feats, band_indices)` — reshape features `(T,H,W,B)` → model input `(H*W, T*B)`.
  Default provided; override if your model wants a different layout.

**6.3 `predict(X_chunk)`** — your framework, model input → raw per-pixel predictions. fsd handles
chunking (`predict_batch_size`) and the NaN→nodata scatter.

**6.4 Endpoint ② — raw output → standard `Output`** (developer-owned). `to_output(raw, hw)` →
`Output((bands, H, W), dtype, nodata, band_names)` — how your model's numbers become the COG bands
fsd writes. Default maps a class/vector per pixel using the §6.1 declarations; override for custom
band packing.

**6.5 `load()`** — read your artifact(s) into memory once per worker; `self.artifacts`
`{name: absolute path}` is injected by the bundle before `load()`. (fsd never trains — you bring a
trained model.)

**6.6 Bundle it:**
```python
from fsd.model import bundle
bundle_dir = bundle.save(adapter, {"model": "rf.joblib"}, "…/bundle")
bundle.read_spec(bundle_dir)          # the model-free manifest (no import, no model load)
```
The bundle is a folder with `bundle.json` (the `module:attr` adapter ref + the §6.1 spec + relative
artifact hrefs) and the artifact(s). **Why it matters:** it's the shippable, self-describing unit;
`read_spec` validates a run **without importing the model** (model-free preflight); and the
`module:attr` ref must be **importable** (installed package / on `PYTHONPATH`) because it crosses a
subprocess/Batch boundary — a `__main__`/notebook class won't reload.

---

## 7. The bundle on disk

```json
{
  "fsd_bundle_version": 1,
  "adapter": "adapters:DemoRF",
  "artifacts": {"model": "rf.joblib"},
  "required_bands": ["B04", "B08"],
  "n_timestamps": 9,
  "output_dtype": "uint8", "output_nodata": 255, "output_band_names": ["crop_class"],
  "feature": {"kind": "sequence", "steps": ["mask_invalid_and_interpolate", "compute_bands", "remove_bands"]}
}
```
`read_spec` reads just this (fast, no imports). `bundle.load` resolves the adapter, injects absolute
artifact paths, checks the class's declared spec against the manifest (catches code/bundle drift),
and calls `.load()`. A field the class leaves **unset** (e.g. `n_timestamps=0`) is taken from the
bundle — this is what lets **one adapter class back models trained on different T**.

---

## 8. Results (fill from a real run)

> Run the demo (`--fast` first) and paste the console's **timing breakdown** + **download** block
> here, plus the QGIS screenshots. Placeholders below show the shape.

```
step                          seconds   share
0_preflight                       0.x      -%
1_tiling                          x.x      -%
2_download                        x.x     -%    <- transfer vs convert vs wall below
3_training_data                   x.x     -%
4_train_bundle                    x.x      -%
5_run_inference                   x.x     -%
6_plots                           x.x      -%
7_report                          0.x      -%
TOTAL                             x.x    100%

download:
  transfer :  ___ s  (___ GB, ___ MB/s summed)
  convert  :  ___ s  (jp2 → COG, ___ files)
  wall     :  ___ s  (___ granules, _ pass)
  probe ___ MB/s vs effective ___ MB/s -> <CDSE/link-bound | local contention>
```
Outputs: `model_outputs/<cell>/output.tif` (one COG per cell), `stac/catalog.json`, `merged.tif`.
Screenshots: `figures/s2_grids.png`, `figures/ndvi_timeseries.png`, `figures/crop_map.png`.

---

## 9. Trusting the numbers & estimating other regions

- **Read probe-vs-effective.** The **probe** is single-threaded achievable CDSE MB/s right now; the
  **effective** rate is the run's bytes ÷ transfer-time at concurrency. probe ≈ effective → you're
  **CDSE/link-bound**; probe ≫ effective → **local contention** (background downloads) or the
  concurrency cap. A VPN or a busy link lowers *both* — it's a *your-machine* caveat, not CDSE. If
  the numbers look off, re-run without background load.
- **Estimate another region without downloading it** (`demos/estimate.py`). Runtime = counts ×
  per-unit costs; the counts are exact cheap queries and this run calibrates the costs
  (`timings.json → cost_model`):
  ```python
  from estimate import estimate_run
  # e.g. "how long for full France, same window/bands?" — no download:
  estimate_run("FR_ROI.geojson", START, END, BANDS, creds=creds, cost_model=cost_model,
               max_cloudcover=70)   # -> {granules, cells, GB, download_min, convert_min, compute_min, total_min}
  ```
  It STAC-queries the granule count, `roi_to_s2_grids` the cell count, and `compute_n_timestamps`
  the T — all without downloading — then multiplies by the cost model. **Caveats:** throughput is
  environment-bound (holds within the same link); bytes/granule vary at ROI edges; the cloud filter
  is queried exactly, not modelled; CDSE flaky windows add resume variance.

---

## Appendix A — Concepts & conventions you'll meet

- **The time axis is derived, not free-form.** `T = ceil((enddate − startdate) / mosaic_days)`;
  windows are half-open `[start, end)`, each labelled by its start boundary, and **empty windows are
  still emitted** (as nodata). So **every datacube over the same `(start, end, mosaic_days)` has a
  byte-identical `timestamps` axis** — which is why multi-tile / multi-CRS cubes can stack, and
  **flatten requires it**. Your adapter's `n_timestamps` must equal this T (or be model-determined).
  Dates are localized to **UTC** to compare against tz-aware catalog timestamps.
- **On-disk artifacts.** A datacube = `datacube.npy` + `metadata.pickle.npy` (metadata is
  `np.save`'d-pickle, a deliberate cross-platform fix). **`nodata = 0`** throughout. Inference = one
  COG per cube + a STAC catalog; `merged.tif` is a display product.
- **Everything is 10 m, resampled to a *real* B08 image** — not an abstract target grid (the
  reference-image resampling rule). Other resolutions need a different known-resolution reference
  band, not just different resample params.
- **Boundary cells don't lose data.** When a grid cell straddles an MGRS-tile boundary, all covering
  tiles of the same acquisition are nodata-fill merged onto the reference grid (not collapsed).
- **`flatten` drops all-nodata pixels** and keeps `coords.npy` (per-pixel easting/northing). *Caveat*
  (TODO #16): coords across two UTM zones are fine as per-pixel IDs, but not as geography.
- **Validate visually in QGIS** — the pipeline saves RGB/composite + categorical outputs precisely
  because rasters must be eyeballed, not just unit-tested.

## Appendix B — Known v1-local limitations (these are *known*, not bugs you found)

- **COG conversion is local-dst only** — both COG-on-download and the inference-output COG require a
  local path; remote/Blob is the deferred stage-local→convert→upload path (a P1/P4 item — the "who
  converts on Blob?" question).
- **`cores > 1` requires a model bundle**, not a live adapter (it crosses a subprocess). The demo
  saves a bundle anyway; a live adapter runs sequentially.
- **The datacube rectangle carries a nodata halo** and can't hug a slanted ROI edge — cosmetic;
  `flatten` drops the nodata. Don't be alarmed eyeballing a cube in QGIS.
- **`fsd.deploy` is a P6 stub** (registration/push); local train + bundle + infer is the complete
  path today.
