# fsd

A small, clean toolkit to **fetch satellite tiles and build datacubes** for geospatial ML.
Clean-room rewrite combining only the necessary parts of the legacy `fetch_satdata`,
`rsutils`, and `cdseutils` repos.

**v1 scope:** Sentinel-2 **L2A** from **CDSE** → per-geometry **datacubes** → flattened
**training arrays**. It is **cloud-agnostic by design** (all I/O through an `fsspec` seam) so
the same code runs locally today and scales on the cloud later — see
[`ROADMAP.md`](ROADMAP.md) for the north-star and phased plan.

## Install

```bash
pip install "git+ssh://git@github.com/nikhilsrajan/fsd.git"
# extras: [notebooks] (matplotlib/sklearn/joblib), [azure] (adlfs), [dev] (ruff/pytest)
pip install "fsd[notebooks] @ git+ssh://git@github.com/nikhilsrajan/fsd.git"
```

Requires Python ≥ 3.11. For development, clone and `pip install -e ".[dev]"`.

## Quickstart (high-level API)

The verbs are what you call; the modules under `fsd.*` are internals.

```python
import datetime
import fsd
from fsd.sources.cdse import CdseCredentials

creds = CdseCredentials.from_env()  # or from a secrets JSON

# 1. Download S2 L2A tiles for an ROI + date range -> a tile catalog.
catalog = fsd.download(
    roi="my_roi.geojson",
    startdate=datetime.datetime(2018, 1, 1),
    enddate=datetime.datetime(2019, 1, 1),
    bands=["B04", "B08", "B8A", "SCL"],
    dst_folderpath="data/s2l2a",
    creds=creds,
    max_tiles=600,
)

# 2. Known-label polygons + catalog -> flattened training arrays. (No "flatten" needed.)
training = fsd.create_training_data(
    label_polygons="my_labeled_fields.geojson",
    catalog_filepath=catalog,
    startdate=datetime.datetime(2018, 1, 1),
    enddate=datetime.datetime(2019, 1, 1),
    mosaic_days=20,
    bands=["B04", "B08", "B8A", "SCL"],
    id_col="fid",
    label_col="crop_type",
    export_folderpath="data/training",
    cores=8,
)

arrays = training.load()        # {"data","ids","labels","coords","metadata"}
# arrays["data"] is (pixels, timestamps, bands) — feed it to your own model (sklearn/torch/…).
```

Training and inference-at-scale are on the roadmap: `fsd.run_inference(...)` and
`fsd.deploy(...)` exist as stubs today (P4 / P6). `runner=` and `storage=` parameters are
seams — local-only now, Azure Batch / blob later, by config not code.

## Documents
- [`ROADMAP.md`](ROADMAP.md) — north-star, phased releases, the model contract.
- [`specs/`](specs/) — compartmentalized design specs (start at `00-overview.md`).
- [`RECIPES.md`](RECIPES.md) — reusable commands & scripts.
- [`DROPPED.md`](DROPPED.md) / [`CHANGES.md`](CHANGES.md) — deferred capabilities / behavior changes.
