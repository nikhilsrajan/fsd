# Run-book: full Austria end-to-end (the go-to-doc showcase run)

> Spec 24 run-book. Claude never runs the long/networked e2e — you run it, paste back the summary
> (`timings.json` + coverage), and it fills `demos/E2E_AUSTRIA.md §8` (the go-to user doc's Results).
> This is the **FULL** real run (real CDSE download → datacube → train on real Austria EuroCrops
> labels → inference → crop map), the pre-P1 milestone. Model quality is not the point — the
> data-generation + model-deploy **infrastructure** working end-to-end on real data is.

## Prereqs
- **Python 3.11** on `PATH` (`python3.11 --version`). The venv itself is created in **Setup** below —
  you do **not** need it beforehand.
- **Fresh CDSE creds** at `../secrets/cdse_credentials.json` (or `$CDSE_CREDENTIALS_JSON`) — S3 keys
  **not expired** (they lapse fast; step 0 warns). See `demos/E2E_AUSTRIA.md §3`.
- Disk: **≥ 50 GB free** under `tests/outputs/demo_e2e/` (you have ~148 GB — fine).
- A real (non-hotspot) network — **university wifi ✓**.
- All commands run from the `fsd/` package root.

## Setup — create the demo venv (once; idempotent, safe to re-run)
The e2e needs a **separate** venv `.venv-modeldeploy` with the `[dev,grid,model-example]` extras
(sklearn/s2/matplotlib) that are deliberately kept out of fsd's lean core `.venv`. This block creates
it only if missing, then verifies the imports the run depends on:
```bash
cd fsd   # package root — all commands below assume this
test -x .venv-modeldeploy/bin/python || python3.11 -m venv .venv-modeldeploy
.venv-modeldeploy/bin/pip install -e ".[dev,grid,model-example]"
.venv-modeldeploy/bin/python -c "import fsd, sklearn, joblib, matplotlib, s2, rasterio, s3fs, geopandas; print('venv OK')"
```
- **Expect:** the final line prints `venv OK` (all imports resolve), exit 0. First-time install
  pulls sklearn/geopandas/rasterio and takes a few minutes; a re-run is a fast no-op.
- The extras (from `demos/E2E_AUSTRIA.md §3`): **`[grid]`** = `s2`/`s2cell` (ROI→S2-cell tiling);
  **`[model-example]`** = `scikit-learn`/`joblib`/`matplotlib` (the demo RF + plots — *not* fsd
  itself); **`[dev]`** = ruff/pytest.
- Wrong venv is the #1 new-user mistake: the demo **will not** run under fsd's core `.venv` (no
  sklearn/s2). Always invoke it as `.venv-modeldeploy/bin/python …` as every step below does.

## Size expectation (from the tiny confirm-run, scaled to the full 6-month window)
~2–4 MGRS tiles → **~80–160 granules → ~20–45 GB**, download ~18–40 min @ ~19 MB/s wall, plus
~30–45 min compute (the two datacube-build stages dominate) → **~1–1.5 hr total**. Step 0 gives the
exact number before you commit.

## Steps

### Step 0 — preflight: creds + size the FULL download (dry-run, STAC only, zero band bytes)
```bash
.venv-modeldeploy/bin/python -m fsd.sources.download_cli \
  --roi ../shapefiles/AT_ROI.geojson \
  --start 2018-04-01 --end 2018-09-30 \
  --bands B04 B08 B8A SCL \
  --max-cloudcover 70 \
  --dst tests/outputs/demo_e2e/imagery \
  --catalog tests/outputs/demo_e2e/imagery/catalog.parquet \
  --max-tiles 200 --dry-run \
  --result-json tests/outputs/demo_e2e/imagery/_result_dryrun_full.json
```
- **Expect:** `... needed: N granules | present: M | missing: K`, exit 0. (`--max-cloudcover 70`
  matches what the e2e will actually download.)
- **DECISION GATE:** with the real `N`, estimated GB ≈ `0.27 × N`; download minutes ≈ `GB×1000/19/60`.
  Proceed only if that GB comfortably fits free disk and the time is acceptable. If `N` is near the
  `--max-tiles 200` guardrail, the e2e will *refuse* — narrow the window or raise `MAX_TILES` in
  `demos/e2e_austria.py`.

### Step 1 — clean slate for honest §8 numbers (recommended)
The confirm-run left ~13 tiny-slice granules in `imagery/`; keeping them makes the full run's
download GB/time understated (they'd skip). For representative go-to-doc numbers, start clean:
```bash
rm -rf tests/outputs/demo_e2e/imagery tests/outputs/demo_e2e/model_outputs
rm -f /tmp/fsd.stop
```
(Skip this if you'd rather resume/reuse what's already downloaded — the run is idempotent either way;
just note §8's download numbers won't be a clean full measurement.)

### Step 2 — run the full e2e (backgrounded, ~1–1.5 hr)
FULL mode = **no** `--tiny-download`, **no** `--fast` (full AT_ROI download, Apr–Sep window, full
inference ROI):
```bash
nohup .venv-modeldeploy/bin/python demos/e2e_austria.py --cores 8 \
  --creds ../secrets/cdse_credentials.json \
  > tests/outputs/demo_e2e/full_run.log 2>&1 &
echo "PID $! — tail -f tests/outputs/demo_e2e/full_run.log"
```
- **Expect (in the log):** a `mode: FULL | window 2018-04-01..2018-09-30 | T=10 | cores=8 …` banner,
  then the 7 timed steps in order: `0. preflight` → `1. ROI → S2 grid cells` → `2. download`
  (probe line, then `download_resume` live progress with `file/s`+ETA — the heart, ~20–40 min) →
  `3. training data` → `4. train` → `5. run_inference` → `6. plots` → `7. report`, then a per-step
  timing table and `timings.json`.
- **This run benefits from this session's fixes:** `download()` now `makedirs` the fresh `imagery/`
  dir (so step 1's `rm -rf` is safe), and step 2's timing carries the honest `transfer_wall_s`.
- **Abort/resume:** step 2 uses `download_resume` directly (no `--stop-file` seam here). `Ctrl-C` is
  safe and the download is **idempotent** — re-run the *same* command to resume (files on disk skip).
  The compute steps (3–5) are also resumable (skip existing cubes/outputs).

### Step 3 — collect + report back
```bash
cat tests/outputs/demo_e2e/timings.json
ls -la demos/figures/                       # s2_grids.png, ndvi_timeseries.png, crop_map.png regenerated
.venv-modeldeploy/bin/python -c "
import rasterio, numpy as np
m = 'tests/outputs/demo_e2e/model_outputs/merged.tif'
import os
if os.path.exists(m):
    with rasterio.open(m) as ds:
        a = ds.read(1); print('merged map:', ds.shape, ds.crs, 'valid%:', round(100*float((a!=0).mean()),1))
"
```
- **Paste back:** `timings.json` (the per-step breakdown + total), the number of MGRS tiles/granules
  and GB downloaded (from the step-2 log summary line), the grid-cell count (step 1), the merged-map
  shape + valid%, and confirm the 3 figures regenerated. Claude fills `E2E_AUSTRIA.md §8` from these.

## Success criteria
- Step 0 exits 0 with a sane `needed` count (well under 200).
- Step 2 exits 0; `timings.json` written; the 3 figures regenerated; a `model_outputs/merged.tif`
  crop map produced with a plausible valid% (single UTM zone 33 → no cross-zone display merge needed).
- No `.part`/`.src.jp2` left under `imagery/` (integrity — same check as `runbooks/26` step 3 if you
  want to be thorough).

## After the run
The numbers land in `demos/E2E_AUSTRIA.md §8` and the download story (the safe runner
`python -m fsd.sources.download_cli`, from `runbooks/26`) gets threaded into §2/§5 — turning
`E2E_AUSTRIA.md` into the single go-to user document (and retiring the stale `demos/README.md`).
See `/tmp/fsd-handoff-austria-doc.md`.
