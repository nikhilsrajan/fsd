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
