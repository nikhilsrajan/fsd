# notebooks

Notebooks that exercise the **installed** `fsd` package (mirroring the legacy demo
notebooks). Install dev + notebook extras first:

```bash
pip install -e ".[notebooks,dev]"
```

Planned (see specs/09-notebooks.md):

- `01_data_prep.ipynb` — credentials → `fsd.sources.cdse.download` →
  `fsd.workflows.create_datacube.run_create_datacube` → `fsd.datacube.flatten.flatten`,
  plus NDVI sanity plots.
- `02_model_train.ipynb` — load flattened arrays, `fsd.bands.modify`, sklearn RF. (later)
- `03_model_deploy.ipynb` — apply model over inference datacubes, merge, STAC. (later)

Put paths/secrets in a top config cell or a local `.env`; never commit credentials.
