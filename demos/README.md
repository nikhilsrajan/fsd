# fsd demos

The go-to end-to-end guide is **[`E2E_AUSTRIA.md`](E2E_AUSTRIA.md)** — running the full fsd pipeline
locally (**download → datacube → train → inference → COG/STAC/merged crop map**) on fresh real
Sentinel-2 data for an Austria ROI, with real timings, the download runner, and the "bring your own
model" bundling guide.

What's in this folder:

- **`e2e_austria.py`** — the driver, and a **reusable template**: point `--roi` / `--train`
  (+ `--id-col` / `--label-col`) at your own region and it runs unchanged, including cross-UTM-zone
  ROIs. See `E2E_AUSTRIA.md §4`.
- **`adapters.py`** — `DemoRF`, a complete worked `ModelAdapter` example (the model-developer-owned
  endpoints). See `E2E_AUSTRIA.md §6`.
- **`estimate.py`** — estimate the runtime/size of another region **without downloading it**
  (calibrated by a real run's `cost_model`). See `E2E_AUSTRIA.md §9`.
- **`figures/`** — committed output figures: `s2_grids.png`, `ndvi_timeseries.png`, `crop_map.png`
  (heavy artifacts live under `tests/outputs/demo_e2e/`, gitignored).

> **History.** This demo began as a Mode-A run on the Ethiopia `satellite_benchmark/` data
> (`e2e_ethiopia.py`, with EuroCrops labels *translated* onto Ethiopian imagery — pipeline-only,
> agronomically meaningless). It was renamed to `e2e_austria.py` and rebased onto **real downloaded
> Austria imagery with genuine EuroCrops labels**. The real bugs that full-ROI runs caught along the
> way (the spec-20 tile-merge coverage bug, the spec-26 STAC id collision, the multi-UTM-zone display
> merge) are recorded in **`E2E_AUSTRIA.md` Appendix C**.
