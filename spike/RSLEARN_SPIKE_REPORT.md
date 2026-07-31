---
status: current
summary: Build-vs-borrow report -- rslearn v0.1.13 vs fsd. Teaches rslearn's data model, prices three options (switch / hybrid / stay), and states what each claim rests on. DRAFT -- the measured sections are gated on probes 01 and 02.
---

# rslearn vs fsd — build-vs-borrow report

> **DRAFT — measurements pending.** Sections 2, 3, 4 and 7 are complete and rest only on source
> reads that anyone can re-check. Sections 1, 5 and 6 carry **⬜ pending** markers wherever a
> number has to come from a probe that has not run yet. Do not take the recommendation in §6 as
> final until those are filled.
>
> **Pinned version.** Every `file:line` citation below is against **rslearn v0.1.13 @ `a5c50c63`**
> (2026-07-28) as vendored read-only at the workspace root, and against **fsd `main` @ `9e7c5f2`**.
> Paths written `rslearn/...` are relative to the rslearn repo root; paths written `src/fsd/...`
> or `docs/...` are relative to this repo.

## 0. What this document is, and what it is not

**It is:** a teaching document plus a costed decision. It assumes you know fsd and know nothing
about rslearn. §2 teaches rslearn from zero. §3 and §4 are the two halves of the comparison,
deliberately written in that order. §5 prices the overheads. §6 is the recommendation.

**It is not** a benchmark of model accuracy, and it is not an evaluation of rslearn's training
stack on its own merits. fsd deliberately does not train models (`ROADMAP.md`); training stays on
the user's side. So rslearn's `train/` and `models/` subsystems are assessed only for what they
would *cost or give* fsd, not for whether they are good deep-learning code.

**Standing bias warning, stated up front because it is real.** The source read this report builds
on (`RSLEARN_READ_2026-07-31.md`) leans against rslearn, and the same analysis now writes the
supposedly neutral verdict. Two guards are applied: §3 (rslearn's genuine advantages) is written
*before* §4 and is required to be at least as specific and quantified as §4; and §6.4 names
explicitly what evidence would flip the recommendation. If you read §3 and it feels like a
formality, the report has failed and you should say so.

### Status of the evidence

| question | status | where |
|---|---|---|
| What rslearn's data model is | ✅ read | §2, cited |
| Source breadth, model zoo, maintenance | ✅ measured from source | §3, method stated |
| Azure support | ✅ read (**none exists**) / ⬜ VM probe pending | §4.1, run-book Step 3 |
| Install weight — is there a lite path? | ✅ read (**no**) | §4.2 |
| Install weight — the actual numbers | ✅ **measured: 5.3 GB venv, 2.9 GB cold download, 88.5 s** | §4.2, §5 |
| Does the stock install even import? | ✅ **measured: no — undeclared `einops`** | §4.2.1 |
| Does the acquisition path import torch? | ⬜ re-run probe 01 after `pip install einops` | §2.3 |
| Does the calendar-`T` contract survive? | ⬜ **pending probe 02 — the gate** | §4.3, §5 |
| Pixel equivalence vs fsd | ⬜ pending (Step 4, unwritten) | §5 |

---

## 1. Executive summary

⬜ **Written last.** It states the recommendation in five sentences for someone who reads nothing
else. Blocked on probes 01 and 02 because the recommendation's price tag comes from them.

What can be said already, and is unlikely to move:

1. **Adopting rslearn does not save fsd's hardest work.** Scale-out onto Azure is fsd's, it is
   built, and it was cluster-validated 2026-07-29. rslearn contains **zero** Azure code (§4.1).
2. **rslearn's breadth is real and large** — 50 distinct concrete data-source entry points versus
   fsd's 2, and a foundation-model zoo fsd has no analogue for (§3.1, §3.2).
3. **The breadth gap is narrower than it looks on Sentinel-2 specifically** (5 rslearn
   implementations vs fsd's 2) and **wider than it looks everywhere else** — SAR, Landsat, DEM,
   climate, soil, land cover, crop labels (§3.1).
4. **The install is 5.3 GB and does not work out of the box** — a stock
   `pip install rslearn==0.1.13` cannot `import rslearn.config` without one extra package (§4.2.1).
5. **A full switch is the option the evidence is worst for**; the live question is the hybrid
   (§6.2).

---

## 2. Teaching rslearn

### 2.1 The five nouns

rslearn's mental model is a **dataset of windows**, not a pipeline of arrays. Learn these five
words and most of the library reads straightforwardly (`docs/CoreConcepts.md:1-30`):

| noun | what it is | fsd's nearest thing |
|---|---|---|
| **dataset** | a directory (local or any `UPath`) holding a `config.json` plus windows | *no analogue* — fsd has a **catalog** (GeoParquet) plus loose artifacts, not a dataset object |
| **window** | one geographic area + one time range. "Roughly corresponds to a training or test example" (`docs/CoreConcepts.md:6-10`) | a **grid cell** (`fsd.grid.roi_to_s2_grids`) — one cell = one datacube = one task |
| **layer** | one kind of data within a window: a raster layer of Sentinel-2, a vector layer of field polygons | fsd has no layers; bands are an axis of one array, labels are a separate GeoDataFrame |
| **item** | one downloadable unit from a source — e.g. one Sentinel-2 scene | a **granule** row in `catalog.parquet` |
| **item group** | the set of items composited together into *one* output raster for a window | one **timestamp slice** of fsd's datacube (one mosaic) |

The critical structural difference is **layer**. In fsd, a datacube is one 5-D array
`(samples, timestamps, height, width, bands)` and labels live outside it. In rslearn, a window is a
*directory* whose subdirectories are layers, and labels are just another layer. That is why
rslearn can carry Sentinel-2 + Sentinel-1 + a DEM + OSM buildings + your annotations in one
coherent object, and fsd cannot without inventing something.

### 2.2 The three verbs (plus one)

rslearn's acquisition is three CLI stages (`docs/CoreConcepts.md:60-97`,
`rslearn/dataset/manage.py`):

```
rslearn dataset add_windows   # define WHERE and WHEN            (main.py:110)
rslearn dataset prepare       # match source items to windows    (main.py:569)
rslearn dataset ingest        # download items into a tile store (main.py:840)
rslearn dataset materialize   # crop/reproject/composite to windows (main.py:955)
```

- **prepare** answers *which scenes does each window need?* and writes the answer as item groups.
  This is the stage where `QueryConfig` — and therefore the `T` question of §4.3 — lives.
- **ingest** downloads whole items into a shared **tile store**, converting to random-access
  formats. It is parallelized **over items**; prepare and materialize are parallelized **over
  windows** (`docs/CoreConcepts.md:88-89`).
- **materialize** crops, reprojects, mosaics and writes the per-window rasters.

`ingest` is skippable: `"ingest": false` in a layer's `data_source` block makes the source a
`DirectMaterializeDataSource` (`rslearn/data_sources/direct_materialize_data_source.py:26`),
going straight from the remote asset to the window. This matters for Azure cost — it halves the
number of writes — and it is the mode the official time-series example uses
(`docs/examples/GetImageTimeSeries.md:31`).

Model verbs (`main.py:1034-1058`) are `rslearn model fit | validate | test | predict`, all
Lightning CLI. fsd does not compete here and does not want to.

### 2.3 Where a numpy array comes out

The concern that rslearn cannot hand you a plain array is **wrong**. Readback is public:
`rslearn/dataset/window_data_storage/storage.py:88,110` (`read_raster` / `read_rasters`), also
`per_layer.py:265,287`.

What is true is that **rslearn's on-disk product is not a cube**. After materialize you get, per
window, one directory per item group:

```
windows/default/<window>/layers/
  sentinel2/     sentinel2.1/     sentinel2.2/   ...   # one dir per group, each a GeoTIFF
```

(`docs/examples/GetImageTimeSeries.md:114-122`.) Turning that into fsd's
`(samples, timestamps, height, width, bands)` is a readback loop you write — mechanically easy,
but it is *your* code, and its correctness depends entirely on §4.3.

The compositors that build each group are in `rslearn/dataset/compositing.py`:
`FirstValidCompositor`, `MeanCompositor`, `MedianCompositor`, and
`SpatialMosaicTemporalStackCompositor` (`compositing.py:283`) — the last is the closest analogue
of fsd's mosaic-then-stack and is the first thing to try in an equivalence test.

**Torch is not on this path at import time.** `rslearn/utils/array.py` is imported by
`materialize.py:13`, `compositing.py:18` and `config/dataset.py:29`, but its torch import is under
`if TYPE_CHECKING:` (`utils/array.py:10-11`). Static reading says the acquisition path is
torch-free to *import*. It is emphatically not torch-free to *install* (§4.2). Probe 01 checks the
import claim empirically.

### 2.4 Worked example — rslearn

This is rslearn's own documented recipe for the job fsd calls "download a time series"
(`docs/examples/GetImageTimeSeries.md`), reproduced so you can see the real ergonomics. **~30
lines of JSON, one GeoJSON of points, three commands.**

`config.json`:

```json
{
  "layers": {
    "sentinel2": {
      "type": "raster",
      "band_sets": [{"bands": ["R", "G", "B"], "dtype": "uint8"}],
      "data_source": {
        "class_path": "rslearn.data_sources.planetary_computer.Sentinel2",
        "ingest": false,
        "init_args": {
          "harmonize": true,
          "query": {"eo:cloud_cover": {"lt": 50}},
          "sort_by": "datetime", "sort_ascending": true
        },
        "query_config": {"space_mode": "INTERSECTS", "max_matches": 99}
      }
    }
  }
}
```

```bash
rslearn dataset add_windows --root $DATASET_PATH --group default \
  --fname locations.geojson --utm --resolution 10 --window_size 256 \
  --start 2025-06-01T00:00:00+00:00 --end 2025-09-01T00:00:00+00:00
rslearn dataset prepare  --root $DATASET_PATH
rslearn dataset materialize --root $DATASET_PATH
```

Read the config carefully — it is where rslearn's design shows:

- `class_path` + `init_args` is **jsonargparse**: any source class, constructed from config. This
  is a genuinely good extension seam; adding a source is adding a class, not editing a registry.
- `query` passes **raw STAC filters** through (`eo:cloud_cover < 50`). fsd has no equivalent
  push-down of arbitrary STAC predicates.
- `space_mode: "INTERSECTS"` yields one group per overlapping scene; `MOSAIC` merges into
  coverage groups. fsd only does the mosaic behavior.
- `harmonize: true` is **opt-in** and defaults off (`copernicus.py:680`) — see §4.4.

### 2.5 The same job in fsd — side by side

fsd's tutorial (`docs/tutorial.md`, reviewed 2026-07-31) over the committed fixture:

```python
training = fsd.create_training_data(
    label_polygons="tests/data/tutorial/fields.geojson",
    catalog_filepath="tests/data/tutorial/catalog.parquet",
    startdate=startdate, enddate=enddate, mosaic_days=20,
    bands=["B04", "B08", "SCL"],
    id_col="fid", label_col="label",
    export_folderpath="/tmp/fsd_tutorial/training",
)
data, labels = training.load()["data"], training.load()["labels"]
```

| | rslearn | fsd |
|---|---|---|
| unit of configuration | a `config.json` + CLI flags | Python keyword arguments |
| unit of work | a **window** (a dataset directory) | a **grid cell** (a datacube) |
| output | per-group GeoTIFF dirs | one `datacube.npy` + `metadata.pickle.npy` |
| labels | another layer in the same window | a separate GeoDataFrame joined at flatten |
| to get `(N, T, bands)` | write a readback loop over groups | it is the return value |
| number of timesteps `T` | data-dependent (§4.3) | `ceil(span / mosaic_days)`, known before download |

Neither is obviously better as ergonomics. rslearn's config-first shape is better for *many
heterogeneous layers*; fsd's function-call shape is better for *one array you are about to hand
to sklearn*. That difference tracks the two projects' actual purposes.

### 2.6 Vocabulary translation table

| rslearn | fsd | note |
|---|---|---|
| window | grid cell | rslearn's is also the train/test example; fsd's is only a work unit |
| layer | — | no fsd analogue; fsd's bands are an array axis |
| item | granule / catalog row | |
| item group | timestamp slice of the cube | the `T` question lives here |
| tile store | — | fsd writes COGs directly to the storage seam |
| `prepare` | catalog query | fsd's catalog is built once, queried per cell |
| `ingest` | `fsd.download` | fsd has no separate materialize stage |
| `materialize` | `run_create_datacube` | |
| `QueryConfig.period_duration` | `mosaic_days` | **the analogue the 2026-07-06 doc missed** |
| `max_matches` | `T` | rslearn's is a cap, fsd's is an identity |
| `DataSource` | `Source` (issue #11) | rslearn's seam is more mature |
| Lightning `model fit` | — (out of scope) | fsd never trains |

---

## 3. Where rslearn is genuinely better

Written first and required to be as specific as §4. These are not concessions; they are the case
for Plan C.

### 3.1 Source breadth — the numbers, with the method

**Method — re-runnable, and you should re-run it before quoting the number:**

```bash
python spike/probes/census_data_sources.py --rslearn-root ../rslearn
```

[`probes/census_data_sources.py`](probes/census_data_sources.py) parses every module in
`rslearn/data_sources/*.py` with `ast` (no imports, so no install and no torch), resolves class
bases transitively, and keeps classes that reach `DataSource` and are neither private
(`_`-prefixed) nor one of the six abstract bases (`DataSource`, `ItemLookupDataSource`,
`RetrieveItemDataSource`, `DirectMaterializeDataSource`, `StacDataSource`,
`AxisAlignedStacDataSource`). Its docstring states the two ways the count could mislead.

| | count |
|---|---|
| modules in `rslearn/data_sources/` | **36** |
| classes reaching `DataSource` (incl. abstract/private) | **47** |
| concrete, public, instantiable source classes | **40 names / 50 distinct (module, class) pairs** |
| fsd sources | **2** (`sources/cdse.py`, `sources/mpc.py`) |

The 50 cover roughly 29 distinct providers/datasets: Sentinel-1 and -2 (five independent S2
implementations — Copernicus/CDSE, Element84 on AWS, GCP public data, MPC, EarthDaily), Landsat
(four routes: GCP, AWS, USGS, MPC), NASA HLS, NAIP, Planet + Planet basemaps, XYZ tiles, Google
Earth Engine, Google Satellite Embedding v1, Copernicus DEM GLO-30, SRTM, Sentinel-3 SLSTR LST,
ERA5-Land (three temporal variants) and ERA5-Land via EarthDataHub, CHELSA daily climate,
SoilGrids, SoilDB, WorldCover, WorldCereal, WorldPop, USDA CDL, EuroCrops, OpenStreetMap, and
`LocalFiles`.

**Two honest qualifications, in both directions:**

- **Against the breadth argument:** on **Sentinel-2 L2A specifically — the only thing fsd v1
  claims** — the gap is 5 implementations to 2, not 50 to 2. fsd already covers two of the five
  routes rslearn covers.
- **For the breadth argument:** everything that is *not* Sentinel-2 is the gap, and it is total.
  fsd has no SAR, no Landsat, no DEM, no climate, no soil, no land cover, no crop-label source.
  Issue **#11** ("Additional data sources (MPC, CHIRPS, ERA5, …) + the `Source` ABC") and **#21**
  (source-capability model) are exactly this, and rslearn has shipped answers for ERA5 (three
  variants) and much more.

**A correction to the source read, which overstated this.** `RSLEARN_READ_2026-07-31.md` §8 says
the breadth gap "is the whole content of issues #11/#21/#31/#32/#33/#36". It is not: **#31, #32,
#33 and #36 are MPC operational issues** (stream-in-place vs copy, signed-URL expiry, resume
orchestration, speed comparison) that adopting rslearn would **not** close. Only #11 and #21 are
breadth. The honest breadth ledger is 2 issues, not 6.

`EuroCrops` deserves a specific callout: `rslearn/data_sources/eurocrops.py:60` is a first-class
source for the exact label corpus fsd's flatten training set uses. That is a direct, concrete
overlap with work fsd does by hand.

### 3.2 The model zoo — fsd has no analogue at all

`rslearn/models/` is **13,736 LOC** and wires in, as named modules: AnySat, Clay, CLIP, CROMA,
DETR, DINOv3, Galileo, Molmo, OlmoEarth-pretrain, Panopticon, Presto, Prithvi, SAM2, SatlasPretrain,
SSL4EO-S12, Swin, TerraMind, Tessera, U-Net, FPN, Faster R-CNN. Plus a task layer
(`rslearn/train/tasks/`): classification, detection, segmentation, regression, per-pixel
regression, embedding, multi-task.

fsd's model story is a **contract** (`BaseModelAdapter`, `docs/tutorial.md`) that you implement
against your own sklearn/torch model. That is the right scope for fsd — but it means a user who
wants "fine-tune a geospatial foundation model on my labels" gets nothing from fsd and a great
deal from rslearn. If that is where NASA Harvest work is heading, this is the single strongest
argument in the whole document for Plan C, and it should not be discounted because fsd's roadmap
currently says training is out of scope.

### 3.3 The layer abstraction genuinely beats fsd's array

fsd's 5-D contract is excellent for "one sensor, many dates, hand it to sklearn". It has no answer
for "Sentinel-2 **and** Sentinel-1 **and** a DEM **and** OSM roads, co-registered per window, with
labels alongside". rslearn's window/layer model handles that natively, including **vector** layers
(`rslearn/data_sources/vector_source.py`, `openstreetmap.py`, `eurocrops.py`) which fsd's raster
pipeline has no concept of.

### 3.4 Maintenance and community

| | rslearn | fsd |
|---|---|---|
| commits, all time | **3,060** | — |
| commits since 2026-01-01 | **1,290** (~184/month) | — |
| commits in the last 90 days | **255** | — |
| distinct commit authors (all time) | **52** | 1 + Claude |
| license | Apache-2.0 | MIT |
| institutional backing | AllenAI (OlmoEarth team) | this project |
| docs site | mkdocs, 17 top-level pages + per-source pages | `docs/` tree, spec 41 |

This is the bus-factor argument and it is one-sided. A dependency maintained by 52 people at a
funded institute is a materially different risk profile from a package maintained by one person.
Apache-2.0 is compatible with fsd's MIT for *use as a dependency*; it carries a patent grant and a
NOTICE-preservation requirement, neither of which is a problem for depending on it.

### 3.5 A design detail rslearn gets right that fsd has open as a bug

rslearn signs MPC asset URLs **lazily, at the moment of read** — `planetary_computer.sign(...)`
appears at each use site (`planetary_computer.py:220,265,373,400,1019`), not once up front. fsd's
issue **#32** ("MPC signed-URL expiry / re-sign for long builds") is open precisely because fsd
signs earlier. rslearn's placement is the better pattern and fsd can adopt it **without adopting
rslearn** — which is itself a finding: some of the value here is copyable, not borrowable.

---

## 4. Where fsd is better *for this project*

The qualifier matters. None of these say rslearn is bad software; they say the fit is wrong for
fsd's stated target.

### 4.1 Azure — rslearn has none, and this is the deployment target

Grep over all 54,850 LOC (`RSLEARN_READ_2026-07-31.md` §3):

| pattern | hits in `rslearn/**/*.py` |
|---|---|
| `azure` / `adlfs` / `abfs://` / `blob.core` | **0** |
| `gs://` | 13 |
| `s3://` | 11 |

The only `azure` string in the repo describes MPC's *own* hosting, i.e. reading from public/signed
blobs, not writing to ours.

**One precision that cuts in rslearn's favour**, and the source read stated it too loosely: core
declares plain `fsspec>=2025.10.0` (`pyproject.toml:15`); it is the **`extra`** group that adds
`fsspec[gcs, s3]` (`pyproject.toml:44`). So *every* cloud backend is opt-in there, not just
Azure's — which means adding `adlfs` to that same group would be **in pattern**, a small upstream
PR rather than an architectural change. The Azure gap is a gap in coverage and testing, not a
structural refusal.

rslearn is built on UPath + fsspec (`rslearn/utils/fsspec.py`), so `abfss://` *should* work with
`adlfs` installed. But fsd's own experience is that fsspec was never the hard part — **GDAL/VSI
auth under managed identity** was, and fsd solved it separately in spec 31 (`/vsiadls/` + a fresh
token). rslearn reads pixels through rasterio too (`rslearn/utils/raster_format.py`), so it
inherits that problem with no known upstream solution. **fsd's fix is not portable into rslearn
without patching rslearn**, and patching a read-only upstream is a finding against Plan C, not a
task.

⬜ **Pending run-book Step 3** — the three sub-questions (does `UPath("abfss://…")` resolve; can
`rslearn.tile_stores.default` write under `DefaultAzureCredential`; does GDAL inside rslearn read
it under MSI). This is the highest-risk unknown in the spike.

### 4.2 Install weight — heavy, with categorically no lite path

`rslearn/pyproject.toml:11-31`, **core** dependencies (not extras):

```
torch>=2.7.0 · torchvision>=0.22.0 · torchmetrics[detection]>=1.7 · lightning>=2.5.1.post0
boto3>=1.39 · fiona>=1.10 · flask>=3.0.0 · rasterio>=1.4 · pyproj · shapely · soilgrids · Pillow
```

`pip install rslearn` installs the entire deep-learning stack plus a web framework and an AWS SDK
whether or not you train anything. The optional groups (`pyproject.toml:33-97`) are `extra`, `dev`,
`terratorch`, `docs` — and `extra` only *adds* more (xarray, zarr, transformers, wandb). **There
is no `rslearn[data]`.**

**Measured on the VM, 2026-07-31** (probe 01; `pip install --no-cache-dir 'rslearn==0.1.13'` into
a fresh `python3.11 -m venv`):

| | |
|---|---|
| venv size on disk | **5,289.5 MB (5.3 GB)** |
| bytes downloaded (cold, `--no-cache-dir`) | **2,892 MB (2.9 GB)** |
| cold install wall time | **88.5 s** on an Azure VM (~33 MB/s) |

For scale: fsd's own `.venv` is the numpy/rasterio/fsspec set listed above. **5.3 GB is not a
laptop install**, and it is the floor — it buys you zero data, before any extra.

#### 4.2.1 The stock install does not import — an upstream packaging bug

Probe 01's first successful run found something no source read had predicted: **on a stock
`pip install rslearn==0.1.13`, `import rslearn.config` — the library's very first import —
raises `ModuleNotFoundError: No module named 'einops'`.** All five modules on the acquisition
path fail identically.

The cause is a one-line classification slip upstream:

- `einops>=0.8` is declared in the **`extra`** optional group (`pyproject.toml:39`), not in core;
- but `rslearn/utils/raster_format.py:9` does a bare top-level `import einops` (used at
  `raster_format.py:788`, `einops.rearrange(array, "c h w -> h w c")`);
- and `rslearn/config/__init__.py` → `config/dataset.py:31` imports `RasterFormat` from it.

So the 5.3 GB venv is, out of the box, **unusable without one further `pip install einops`**.

**Be fair about what this is and is not.** It is a packaging defect, not a design flaw: the fix is
one line upstream, and `einops` is the *only* extra-group package a core module imports at top
level — the others (`osmium` in `openstreetmap.py`, `cdsapi`/`netCDF4` in `climate_data_store.py`,
`omnicloudmask` in `dataset/omni_cloud_mask.py`) sit behind specific data sources, which is the
correct pattern. But it is evidence about **operational maturity at the version we would adopt**:
the most basic possible smoke test — install the package, import it — fails, which means it is not
in their release CI. For a dependency that would sit under fsd's download path in production, that
is a real signal, and it is the kind of thing that shows up only by running the install.

⬜ **Not yet checked:** whether this is already reported upstream, and whether it is fixed after
0.1.13. Worth one look before the report is final — and worth filing if not.

fsd's core is `numpy, pandas, geopandas, shapely, rasterio, pyarrow, fsspec, s3fs, pystac,
pystac-client, numba, snakemake, tqdm` with everything cloud-shaped behind extras (`azure`, `aml`,
`mpc`, `grid`, `titiler`, `model-example`). fsd's Mode-A promise — pip install, a laptop, an RF —
**cannot survive a dependency that installs torch.** If rslearn is adopted for acquisition, the
lean-install property is spent unless rslearn sits behind fsd's own extra.

⬜ **Pending probe 01** for venv size, wheel bytes, cold-install wall time, and the empirical
`sys.modules` check on whether the materialize path pulls torch at import.

### 4.3 The calendar-`T` contract — 🚩 the gate

fsd's `T = ceil((enddate - startdate) / mosaic_days)` (`src/fsd/api.py:69-80`) is a **pure
function of the caller's window**, computable with zero downloads. Two fsd properties depend on
that:

- **Preflight** asserts `T == adapter.n_timestamps` *before* any download — the cost guardrail on
  a fan-out.
- **Cross-cell flatten** requires every cube over the same window to share one `timestamps` axis.

The 2026-07-06 comparison called this contract "unique". **It is not** —
`QueryConfig.period_duration` (`rslearn/config/dataset.py:445-457`) is the direct analogue, and
that correction is the most useful thing the re-read produced: the two systems are much closer on
the axis we thought was a moat.

But the implementation diverges three ways (`rslearn/data_sources/utils.py:434-485`):

| # | rslearn | source | fsd | consequence |
|---|---|---|---|---|
| 1 | empty sub-periods are **dropped** | `utils.py:464` | every window emitted, nodata-filled | **`T` becomes data-dependent** — differs between grid cells |
| 2 | periods walk **backwards from the end** | `utils.py:446-455` | start-anchored | window **phase** differs when the span isn't an exact multiple |
| 3 | trailing partial period **dropped** (floor) | `utils.py:447-448` | ceil — partial kept | off-by-one on almost every real window |

Plus `per_period_mosaic_reverse_time_order` **defaults to `True`** (`config/dataset.py:466-473`):
groups return most-recent-first with a `FutureWarning`; the default flips after 2026-04-01.

**Why (1) is load-bearing:** if `T` is only knowable after querying, preflight cannot fire early
and cells with different scene availability cannot be stacked. A re-alignment shim (map groups
back onto their period index, fill gaps) restores both — but that is **new fsd code that Plan C
was supposed to delete.**

⬜ **Pending probe 02.** Prediction: `dense_tutorial_window` gives fsd `T = 10` and rslearn **9**.
If the probe returns 10, §4.2 of the source read is wrong and this section must be re-derived
before the recommendation stands.

### 4.4 Harmonization posture — fsd's is more robust

rslearn's baseline-04.00 harmonization (`rslearn/data_sources/copernicus.py:44-90`):

- **opt-in, defaults OFF** — `harmonize: bool = False` (`copernicus.py:680`);
- **hard-asserts the offset is exactly −1000** — `assert offset == -1000` (`copernicus.py:73`),
  comment *"For now assert the offset is always -1000."* Any other declared `BOA_ADD_OFFSET`
  crashes;
- reads the value from the product metadata XML — the right source, same as fsd.

fsd's spec 34 + amendment A2 chose the opposite posture deliberately: **derive per item, accept
`{0, −1000}`, refuse rather than assume.** That was vindicated on real data — the blob MPC
archive's pre-Collection-1 2018 products correctly declare `0`, and a hardcoded `== -1000`
assertion *did* fail against it (PROGRESS, 2026-07-31). **rslearn is predicted to `AssertionError`
on the tutorial fixture** with harmonization on. The 2026-07-06 doc credited rslearn's
harmonization as a reason to adopt; that credit is withdrawn.

(`aws_sentinel2_element84.py:35-36` notes its COGs are "already harmonized, even though it is not
really documented" — an honest comment, and a reminder that the posture varies per source in
rslearn too.)

### 4.5 Scale-out — built, validated, and not something rslearn offers

rslearn parallelizes with local multiprocessing (`main.py:52-58`: `forkserver` context,
`DEFAULT_MAX_WORKERS = 32`, `workers=-1`). There is no distributed runner. fsd's AML runner seam
fanned out 97 jobs / 213 granules / 300 grid cells in 18.8 minutes unattended (2026-07-29). This
half of the work is fsd's regardless of the verdict — which is exactly why a *full switch* is the
weakest of the three options.

---

## 5. The overheads, priced

Partially measured. Probe 01's weight numbers are in (VM, 2026-07-31); its import reading and all
of probe 02 are still ⬜.

| overhead | fsd today | rslearn | source |
|---|---|---|---|
| venv size on disk | ⬜ measure | **5,289.5 MB** | probe 01 |
| wheel download bytes (cold) | ⬜ measure | **2,892 MB** | probe 01, `--no-cache-dir` |
| cold install wall time | ⬜ measure | **88.5 s** (Azure VM, ~33 MB/s) | probe 01 |
| stock install actually imports? | yes | **no** — needs `pip install einops` | §4.2.1 |
| import time (acquisition path) | ⬜ | ⬜ re-run after einops | probe 01 |
| torch pulled at import? | n/a | ⬜ re-run (predicted **no**) | §2.3 |
| `T` on the tutorial window | 10 | ⬜ probe 02 (predicted **9**) | §4.3 |
| re-alignment shim, if needed | 0 LOC | ⬜ estimate after probe 02 | §4.3 |
| Azure write under MSI | works (spec 31) | ⬜ Step 3 | §4.1 |
| pixel equivalence vs fixture | baseline | ⬜ Step 4 | |

The first run also reported `rslearn.__version__` as **`unknown`** (the package exposes no
`__version__` attribute) and showed **`boto3` already in `sys.modules`** even though every
acquisition import had failed — i.e. an AWS SDK loads on a path that touches no AWS. Both are
minor; the boto3 reading needs confirming on the re-run, since it was taken from a partial import.

---

## 6. The three options

⬜ **Prices pending.** The *shapes* are settled and stated here; the numbers and the final call
come after the probes.

### 6.1 Option A — full switch (fsd rebuilt on rslearn)

**What it buys:** 50 sources, the model zoo, 52 maintainers.
**What it costs:** rewriting fsd's Azure layer *into* a library with zero Azure support and a
read-only-reference constraint that forbids patching it; losing Mode-A; writing a `T` shim; and
re-doing scale-out anyway, since rslearn has no distributed runner.
**Current read:** the evidence is worst for this option. It gives away fsd's finished work to
acquire breadth fsd could also acquire more cheaply (§6.2).

### 6.2 Option B — hybrid: an rslearn-backed `Source` behind an extra ← **the live question**

This is the option to work hardest on, and it is the one the sharpened question in
`RSLEARN_READ_2026-07-31.md` §8 lands on: *should fsd's `Source` seam gain an optional
rslearn-backed source, behind an extra, for breadth?*

**Shape:** `pip install fsd[rslearn]` adds a `Source` implementation that drives rslearn's
prepare/materialize for sources fsd does not have (ERA5, DEM, Landsat, S1, WorldCover…), lands the
output in fsd's storage seam, and hands fsd's own datacube builder the arrays. fsd keeps its
`T` contract, its Azure layer, its runner, and its lean core.

**What it must survive — the questions to attack in §6.4 and in a grilling pass:**

1. Does the `T` shim (§4.3) have to exist for *every* rslearn-backed source, and who owns it?
2. Can rslearn write to Azure at all (§4.1)? If not, the hybrid runs rslearn *outside* the cloud
   path and only for local/ancillary data — a much smaller prize.
3. Is `fsd[rslearn]` honest, given rslearn's core deps mean that extra is a 2 GB+ install?
4. Does one extra source (say ERA5) actually need rslearn, or is it 200 lines of fsd code? The
   hybrid pays off only if the *marginal* source is cheap, and that depends on rslearn's `Source`
   adapter being thin.
5. Two dependency trees with two rasterio/fsspec version constraints — is that solvable or a
   recurring tax?

### 6.3 Option C — stay on Plan B, copy what is copyable

**What it buys:** no new dependency, Mode-A intact, no `T` shim, full control of the Azure path.
**What it costs:** every new source is fsd's to write, and the model-zoo gap (§3.2) stays open
permanently.
**What it should steal regardless of the verdict:** rslearn's lazy MPC signing (§3.5, closes fsd
issue #32's design question), the `class_path` + `init_args` extension seam for fsd's own `Source`
ABC (issue #11), and `space_mode: INTERSECTS` as a second matching mode.

### 6.4 Recommendation, and what would change it

⬜ **Pending.** Written after probe 02. Stated in advance, so it cannot be quietly reverse-engineered
from whatever the probes say:

- **If probe 02 shows `T` matches** (rslearn returns 10): the strongest technical objection to the
  hybrid collapses, §4.3 must be re-derived, and Option B gets materially more attractive.
- **If Step 3 shows rslearn writes to Azure blob under MSI without patching**: the largest cost of
  both A and B drops, and A stops being unreasonable.
- **If probe 01 shows a modest install** (contradicting §4.2's read): the Mode-A objection weakens.
- **If the team's direction turns toward foundation-model fine-tuning** (§3.2): that alone can
  outweigh every infrastructure argument here, because fsd has no path to it at all.

---

## 7. What this report does not know

Stated plainly so nothing here is over-read:

1. **Nothing has been run.** Every claim above is a source read or a repository measurement. All
   ⬜ items are genuinely open.
2. **No accuracy comparison exists** and none is planned — the spike compares acquisition, not
   model quality.
3. **rslearn's training stack is not evaluated on its merits.** §3.2 counts what is there; it does
   not claim those models work well for crop mapping in Austria or Ethiopia.
4. **The `T` analysis is a reading of one loop** (`utils.py:434-485`). Probe 02 exists because a
   careful read can still be wrong.
5. **Version pin.** rslearn moves fast (255 commits in 90 days). Everything here is v0.1.13 and
   has a shelf life measured in weeks.

## 8. Sources

| source | what it contributed |
|---|---|
| `rslearn/docs/CoreConcepts.md` | the window/layer/item/item-group model; the prepare/ingest/materialize split; that ingest parallelizes over items while prepare/materialize parallelize over windows |
| `rslearn/docs/examples/GetImageTimeSeries.md` | the worked example in §2.4, verbatim — config shape, `ingest: false`, the per-group output directory layout |
| `rslearn/rslearn/data_sources/utils.py:434-485` | the three `period_duration` divergences (drop-empty, end-anchor, floor) that §4.3 rests on |
| `rslearn/rslearn/config/dataset.py:445-473` | `period_duration`'s own docstring, and the `per_period_mosaic_reverse_time_order` default + deprecation |
| `rslearn/rslearn/data_sources/copernicus.py:44-90,680` | harmonization is opt-in and hard-asserts −1000 |
| `rslearn/pyproject.toml:11-97` | torch/lightning/flask/boto3 are core; the four optional groups contain no lite path; `einops>=0.8` sits in `extra` (line 39) though a core module imports it; core declares bare `fsspec` and only `extra` adds `fsspec[gcs, s3]` (line 44) — no Azure backend in either |
| `rslearn/rslearn/utils/raster_format.py:9,788` + `config/dataset.py:31` | the import chain that makes a stock install fail: `rslearn.config` → `RasterFormat` → bare `import einops` |
| probe 01 `_result_probe01.json`, VM run 2026-07-31 | 5,289.5 MB venv; 2,892 MB cold download; 88.5 s install; the `einops` failure on all five acquisition imports; `__version__` absent |
| `rslearn/rslearn/main.py:52-58,110-1058` | the CLI verb set; `forkserver`; `DEFAULT_MAX_WORKERS = 32` — i.e. local multiprocessing, no distributed runner |
| `rslearn/rslearn/data_sources/planetary_computer.py:220,265,373,400,1019` | lazy per-read MPC signing (§3.5) |
| `rslearn/rslearn/dataset/window_data_storage/storage.py:88,110` | public numpy readback exists |
| `rslearn/rslearn/dataset/compositing.py:283` | `SpatialMosaicTemporalStackCompositor` as fsd's nearest analogue |
| `rslearn/rslearn/utils/array.py:10-11` | torch import guarded by `TYPE_CHECKING` — the basis for "torch-free at import" |
| rslearn git history (`a5c50c63`) | 3,060 commits, 1,290 since 2026-01-01, 255 in 90 days, 52 authors |
| AST census of `rslearn/data_sources/*.py` | 36 modules, 47 `DataSource` subclasses, 40 concrete public classes / 50 (module, class) pairs |
| `spike/RSLEARN_READ_2026-07-31.md` | the prior source read this report builds on and, in §3.1, corrects on the issue ledger |
| `fsd` `pyproject.toml`, `src/fsd/api.py:69-80`, `docs/tutorial.md` | fsd's core deps and extras; the `T` identity; the worked example in §2.5 |
| `gh issue view 11,12,21,31,32,33,36` | which open issues rslearn would and would not close |

---
*Cross-refs: [`README.md`](README.md) (charter), [`RSLEARN_READ_2026-07-31.md`](RSLEARN_READ_2026-07-31.md)
(the source read), [`RUNBOOK-rslearn-spike.md`](RUNBOOK-rslearn-spike.md) (the measurements),
[`../RSLEARN_COMPARISON.md`](../RSLEARN_COMPARISON.md) (the 2026-07-06 analysis being revised).*
