# rslearn vs fsd — build-vs-borrow analysis

> **Status: analysis + OPEN DECISION (2026-07-06).** A thorough read of the `rslearn/`
> repo (read-only reference, cloned at workspace root) against the current fsd codebase and
> `fsd/ROADMAP.md`, to answer: *are we reinventing rslearn, and should we pip-install and
> leverage it instead?* The recommendation in §7 is mine; the **direction is the user's call.**

## 1. What rslearn is

`rslearn` (**AllenAI / OlmoEarth Team**, **Apache-2.0**, actively maintained — torch 2.7,
fsspec 2025.10, v0.1.12) is *"a tool for developing remote sensing datasets and models."* It
is a **broad, mature superset** of almost the entire fsd pipeline **plus** deep-learning
training and foundation models. It is both a **CLI** (`rslearn dataset prepare/ingest/
materialize`, `rslearn model fit/predict`) and an importable **Python library**.

Core data model:
- **Dataset** = raster/vector **layers** + spatiotemporal **windows** (a window = CRS +
  resolution + bounds + time range ≈ one training/inference example).
- **Data sources** (30+): CDSE/Copernicus, AWS S2 (Element84 COGs), Planetary Computer, GCP,
  Landsat, HLS, NAIP, **EuroCrops**, WorldCover/WorldCereal/CDL, DEM, ERA5, OSM, XYZ, … a
  unified `get_items(geometries, query_config)` API.
- **prepare → ingest → materialize**: match items to windows → download+reproject into a
  **tile store** (fsspec/UPath, local or S3) → crop/reproject/**composite** to window grid.
- **Compositors**: `MEDIAN`, `MEAN`, `FIRST_VALID`, temporal reducers, and **cloud-aware**
  ones incl. **`Sentinel2SCLBestClear`/`Sentinel2SCLFirstValid`** (SCL-based).
- **train/** on **PyTorch Lightning**: `Task` (segmentation/regression/classification/
  detection) + model components + **foundation models** (OlmoEarth, Satlas, Clay, Prithvi,
  Galileo, Presto, DINOv3, …). Config-driven YAML/JSON.
- **model predict** on new windows = inference (incl. a GeoTIFF-inference workflow that maps
  onto fsd's "run model over an ROI").

## 2. Overlap map (fsd ↔ rslearn)

| fsd piece | rslearn equivalent | verdict |
|---|---|---|
| `storage/` fsspec seam | `utils.fsspec` + **UPath** (universal_pathlib), `tile_stores` (file/S3) | same philosophy, rslearn more mature — **light reinvention** |
| `sources/cdse` (CDSE STAC + S3) | `data_sources/copernicus.py` (S2 L1C/L2A) **+ 30 other sources** | rslearn far broader, incl. **baseline-04.00 +1000 harmonization** — **reinvention** |
| `catalog/TileCatalog` (GeoParquet) | windows + `items.json` + tile-store index | different model (window-centric) — **distinct** |
| `raster/images` (load, reproject, **reference-resample**) | source reproject-to-window-projection + `utils.raster_*` | overlaps; rslearn reprojects to an explicit window CRS+res — **reinvention/distinct** |
| `datacube/ops.median_mosaic` (**calendar**, spec 15) | `dataset/compositing.py` (MEDIAN, SCL compositors, temporal reducers) | strong overlap; **fsd's identical-calendar-T contract is unique** |
| `datacube/builder` (**`datacube.npy` 5-D tensor**) | `materialize` → per-window per-layer GeoTIFFs; DataModule reads patches lazily | **fundamentally different data model** |
| `datacube/flatten` (→ **pixel table** ids/labels) | none direct (Lightning DataModule reads patches for torch) | **fsd-unique** (classical-ML table) |
| `bands/modify` (5-D band-math sequence) | `train/transforms` (torch transforms) | conceptual overlap, different impl |
| `workflows/` (**Snakemake** runner + task CLI) | `main.apply_on_windows` (**multiprocessing.Pool**) + CLI | **both single-node**; see §3 |
| **ModelAdapter** contract (any sklearn/torch/tf) | Lightning `Task` + model YAML (**torch-only**) | **fsd-unique** (framework-agnostic, classical ML) |
| **Azure Batch runner** (planned P2) | **not in core** (AllenAI uses separate `rslearn_projects`/Beaker) | **ours regardless** — see §3 |
| COG-on-download (spec 14) | `raster_format` geotiff; direct-materialize from COG sources | partial overlap |
| STAC (planned P0) | consumes STAC (`pystac_client`) for sources; dataset format is its own | different |
| foundation models (roadmap P6) | **Satlas/Clay/Prithvi/OlmoEarth/…** built-in | **rslearn far ahead** |

## 3. THE critical finding — rslearn does *not* solve our scale-out

rslearn's core parallelism is **`multiprocessing.Pool` on one machine** (`apply_on_windows`,
`--workers` capped at CPU count). It has **no distributed/cloud runner in the core repo** —
AllenAI scales it via a *separate* `rslearn_projects` repo on **Beaker** (their compute), not
Azure Batch. So the **crown-jewel differentiator of this whole project — cloud scale-out on
raapid `rise`/Azure Batch — is ours to build no matter what.** rslearn is, for our purposes,
in the *same category as fsd's local Snakemake runner*: a single-node engine that our runner
seam would dispatch. This reframes the question from **"fsd vs rslearn"** to **"for the data
pipeline *underneath* our Azure runner, do we build or borrow?"**

## 4. Where rslearn is clearly better (don't reinvent these)

- **Breadth of data sources** (30+, unified API) incl. **CDSE with harmonization**,
  EuroCrops, Planetary Computer, AWS COG S2, HLS, DEM, ERA5, OSM. fsd has one (CDSE).
- **Foundation models + Lightning training** — an enormous body of work (P4–P6 of our
  roadmap) that we would otherwise build from scratch, worse-supported.
- **Reprojection / geometry / raster-format utilities** — battle-tested `STGeometry`,
  `Projection`, UPath-based I/O.
- **Maturity & support**: Apache-2.0, AllenAI-backed, tests, docs, releases.

## 5. Where fsd is genuinely distinct (not mere reinvention)

- **Lean footprint.** fsd = numpy/rasterio/fsspec. rslearn pulls **torch + lightning +
  foundation models** (a heavy install). For Azure-hesitant colleagues wanting a **simple RF
  on a laptop** (Mode A), that weight is a real cost.
- **Classical-ML paradigm.** fsd's **`flatten` → `(pixels, T, bands)` table + ids/labels →
  sklearn RandomForest** is a clean, simple path. rslearn's train/predict is **torch-Lightning
  DataModule + patches**; a plain sklearn model does **not** fit it cleanly. Our demo_02/03 is
  exactly this classical case.
- **The `datacube.npy` tensor** (eager 5-D `(samples,T,H,W,bands)`) — simple to reason about
  for small ROIs + classical ML; rslearn is lazy per-window GeoTIFFs.
- **Opinions we hold deliberately** (`fsd-geospatial-nitpicks`): reference-image resampling to
  **B08 10 m** (vs an abstract target grid), single-CRS merge, **calendar-mosaic identical-T**
  (spec 15 — enables clean cross-tile flatten *and* pre-download preflight of `T`),
  **COG-on-download** (spec 14).
- **The Azure/raapid runner + the framework-agnostic ModelAdapter** — our value-add.

## 6. Paradigm mismatch (the deciding tension)

rslearn is built **for deep learning**: windows → per-layer GeoTIFFs → Lightning DataModule →
torch model → predictions. fsd (today) is built **for classical ML**: datacube tensor →
flatten to a pixel table → sklearn → COG. These are *different shapes of the same pipeline*.
Adopting rslearn wholesale means **adopting its DL-centric data model** — great for foundation
models (our long-term goal), heavier and awkward for the simple RF case (our current users).

## 7. Options & recommendation

- **A — Adopt rslearn wholesale.** Retire fsd's pipeline; build only the Azure-Batch runner +
  a thin RF wrapper. *Max reuse, but* throws away validated fsd code, forces the DL data model
  + heavy deps on simple users, big paradigm shift.
- **B — Ignore rslearn, continue fsd.** Full control, lean. *But* we reinvent 30 data sources,
  compositors, reprojection, and eventually all of train/predict/foundation-models — worse
  and slower than rslearn.
- **C — Selective leverage (RECOMMENDED).** Pip-install rslearn as a **library for what it
  does best and stably — data sources (CDSE+harmonization, EuroCrops, PC/AWS COG), and its
  geometry/reprojection/raster utils** — and keep fsd's lean **datacube/flatten/ModelAdapter/
  Azure-runner** on top. Later, when we reach foundation models (P6), lean on rslearn's
  `models`/`train`. Build our Azure-Batch runner to dispatch *either* engine.
- **D — Align, don't absorb (yet).** Stay independent but adopt rslearn's proven *formats/
  concepts* (STAC, window/projection model) so we can interoperate/migrate later, without the
  heavy dependency now.

**My recommendation: C, gated by a time-boxed spike.** The spike answers the load-bearing
questions before we commit the roadmap:
1. Can rslearn's `copernicus.Sentinel2` L2A source **write into `rise` Azure blob** (UPath/
   fsspec + MSI) and give us COG bands equivalent to fsd's CDSE download? (If yes, we retire
   `sources/cdse` and inherit 30 sources + harmonization for free.)
2. Can we get a **plain numpy time-series datacube** out of rslearn's materialize +
   compositors that our `flatten` + `ModelAdapter` consume — *without* dragging in Lightning?
   (Tests whether "rslearn for acquisition, fsd for the ML table" is clean or leaky.)
3. Dependency weight / install friction of `rslearn` (even `pip install rslearn` without
   `[extra]`) on a laptop for a Mode-A user.

If the spike is clean, **C reshapes the roadmap**: P0 shifts from "polish fsd's own pipeline"
toward "wrap rslearn acquisition + keep fsd's flatten/adapter/runner," and we stop building
data sources and compositors ourselves.

## 8. Regardless-of-decision follow-ups

- **Harmonization (+1000, baseline 04.00):** rslearn's CDSE source handles it; **verify fsd's
  `sources/cdse` does too** — a real correctness item independent of adoption.
- **STAC:** rslearn consumes STAC but its dataset format is bespoke; our P0 STAC decision
  stands either way (our output catalog is ours).
- The Azure-Batch runner (P2) is unaffected — it's ours in every option.

---
*Cross-refs: `fsd/ROADMAP.md` (the plan this may reshape), `fsd/AZURE_INFRA.md` (the runner
target), `PROGRESS.md` (what fsd has already built + validated).*
