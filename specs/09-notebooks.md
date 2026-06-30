# Spec 09 — Notebooks, packaging & tooling

Folds in: `fetch_satdata/pyproject.toml`, the three demo notebooks.

## Goal

Make `fsd` trivially testable from notebooks against the **installed** package —
the way `demo_01..03` imported the old package.

## Packaging
- `src`-layout, package `fsd`, `pip install -e .` for dev.
- `pyproject.toml`: setuptools backend, `requires-python = ">=3.11"`,
  `package-data` to ship `workflows/_snakefiles/**/*`.
- Dependencies (minimum, to be finalized at implementation): `geopandas`,
  `rasterio`, `numpy`, `pandas`, `shapely`, `sentinelhub`, `boto3`, `numba`,
  `snakemake`, `tqdm`, `fsspec`, `s3fs` (S3-compatible transport), `pyarrow`
  (GeoParquet). No direct `boto3`. Plotting/sklearn live in notebook extras, **not**
  core. Azure backends (`adlfs`, Azure Batch SDK) are a Phase-2 optional extra.
- Optional extras: `[notebooks]` (matplotlib, seaborn, ipywidgets, scikit-learn,
  joblib), `[dev]` (ruff, pytest).

## Notebooks (`notebooks/`)
Mirror the demo flow but importing `fsd`:
- `01_data_prep.ipynb` — credentials → `fsd.sources.cdse.download(...)` →
  `fsd.workflows.create_datacube.run_create_datacube(...)` →
  `fsd.datacube.flatten.flatten(...)`; plus the NDVI sanity plots.
- `02_model_train.ipynb` — load flattened arrays, `fsd.bands.modify`, sklearn RF.
  (Kept as a notebook; not core.)
- `03_model_deploy.ipynb` — apply model over inference datacubes, merge, STAC.
  (Kept as a notebook; uses `fsd.raster` + `fsd.bands`.)

> Hardcoded absolute paths in the legacy notebooks become a small config cell /
> `.env`-style block at the top. No secrets committed.

## Tooling
- `ruff` for lint+format; `pytest` for `tests/` (fast, synthetic; network tests
  marked and opt-in).

## Decisions to confirm
- Are notebooks 02/03 in-scope to **port now**, or added later once the data-prep
  core is implemented? (Core scope = data prep; deploy/train are notebook demos.)
