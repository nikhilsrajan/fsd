# fsd

**Fetch satellite imagery, build datacubes, and run your own model over them — on your laptop or
across a cloud cluster, with the same code.**

Sentinel-2 L2A from **CDSE** or the **Microsoft Planetary Computer** → per-geometry **datacubes** →
flattened **training arrays** → **inference** → COGs + STAC. All I/O goes through an `fsspec` seam,
so local and `abfss://` are a config change rather than a rewrite, and scaling out is a `runner=`
argument.

**fsd does not train your model.** It hands you training arrays, takes back a bundled adapter, and
runs it at scale. That line is deliberate and permanent.

## Install

```bash
pip install "fsd[local] @ git+ssh://git@github.com/nikhilsrajan/fsd.git"
# extras: [local] snakemake, for the default runner="local" pipeline · [s3] s3fs, for
# s3:// transport incl. CDSE EODATA · [azure] adlfs · [aml] the Azure ML scale runner ·
# [mpc] Planetary Computer · [grid] ROI→S2 tiling · [notebooks] · [dev] ruff/pytest
```

The core install deliberately carries neither `snakemake` nor `s3fs` — one is only ever a
subprocess, the other an fsspec backend resolved by URL scheme, and together they cost 53
packages / 111 MB that an AML-only or MPC-only user never touches. Ask for what you use;
fsd names the missing extra if you don't.

Python ≥ 3.11. For development: clone, then `pip install -e ".[dev,local]"`.

## 60 seconds

```python
import datetime
import fsd
from fsd.sources.cdse import CdseCredentials

# 1. Imagery for an ROI and a window -> a GeoParquet tile catalog.
catalog = fsd.download(
    roi="my_roi.geojson",
    startdate=datetime.datetime(2018, 1, 1),
    enddate=datetime.datetime(2019, 1, 1),
    bands=["B04", "B08", "B8A", "SCL"],
    dst_folderpath="data/s2l2a",
    creds=CdseCredentials.from_env(),
    max_tiles=20,   # required cost guardrail: refuse the run if the ROI matches more
)                   # than this many MGRS granules. Preflight checks it before any spend.

# 2. Labelled polygons + that catalog -> flattened training arrays.
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
)

arrays = training.load()   # {"data", "ids", "labels", "coords", "metadata"}
# arrays["data"] is (samples, timestamps, bands) -- train whatever you like on it.

# 3. Your trained model, bundled as a ModelAdapter, run over a region -> COGs + STAC.
result = fsd.run_inference(
    "my_bundle/",                    # the bundle is the first positional argument
    output_folderpath="data/predictions",
    roi="my_roi.geojson",            # ROI mode needs all five of the next arguments
    catalog_filepath=catalog,
    startdate=datetime.datetime(2018, 1, 1),
    enddate=datetime.datetime(2019, 1, 1),
    mosaic_days=20,
    bands=["B04", "B08", "B8A", "SCL"],
    merge=True,
)
```

**The same calls run on a cluster** — add `runner="aml"` and point `storage=` at blob. No pipeline
code changes; that is the whole design. A 300-cell ROI over Austria ran that way in 18.8 minutes
across 32 nodes.

`fsd.deploy` is the one verb still a stub: the bundle format is fixed, but pushing a bundle to a
registry lands in P6.

## Where to go next

| you want | read |
|---|---|
| a guaranteed-to-succeed first run, offline, no credentials | [`docs/tutorial.md`](docs/tutorial.md) |
| your own region, real imagery, a cluster, your own model, or a map viewer | [`docs/howto/`](docs/howto/) |
| a readable script to copy | [`examples/`](examples/) — `eurocrops_rf.py`, a complete `ModelAdapter` |
| how the code is laid out, and what must stay true | [`ARCHITECTURE.md`](ARCHITECTURE.md) |
| where fsd is heading | [`ROADMAP.md`](ROADMAP.md) |
| what a term means | [`CONTEXT.md`](CONTEXT.md) |
| why something was decided | [`docs/adr/`](docs/adr/) |
| how fsd got this shape — the forks taken and dropped | [`docs/history.md`](docs/history.md) |
| a measured result about running at scale | [`docs/findings/`](docs/findings/) |
| the Azure environment variables | [`docs/reference/environment.md`](docs/reference/environment.md) |
| a reusable command | [`RECIPES.md`](RECIPES.md) |
| design documents | [`specs/`](specs/) — start at `00-overview.md` |
| operating procedures for real runs | [`runbooks/`](runbooks/) |
| open work | `gh issue list` — issues #1–#62 |

[`demos/E2E_AUSTRIA.md`](demos/E2E_AUSTRIA.md) is a full benchmark report of a real 300-cell run —
read it as measurements, not as instructions; the instructions are the tutorial + how-tos above.

## Contributing

`pytest -q` and `ruff check src/ tests/ demos/` must be clean. Tests are synthetic and offline;
anything needing credentials or a cluster is a run-book. Design lands as a spec first. Details in
[`ARCHITECTURE.md` §8](ARCHITECTURE.md#8-contributing).

## License

MIT.
