# Spec 16 — Packaging + high-level API surface (P0)

> **Status: SIGNED OFF (2026-07-06) — implementing.** SO-1..SO-6 approved as drafted
> (SO-2: `download` is its own verb). First spec of the north-star roadmap
> (`ROADMAP.md`), phase **P0** — *minus* STAC, which is split into spec 17. Goal: make fsd
> **pip-installable from GitHub** and give it the **high-level verb surface** users will call,
> with **`create_training_data` fully working locally** and `run_inference` / `deploy` as
> contract-pinning **stubs**. No Azure, no STAC, no ModelAdapter impl here.
>
> **Release demo:** in a fresh venv, `pip install git+ssh://git@github.com/nikhilsrajan/fsd.git`,
> then `import fsd; fsd.create_training_data(...)` runs download→datacube→flatten on the
> EuroCrops set locally and returns training arrays — the user never types "flatten."
>
> Decisions flagged **[SO-n]** need explicit sign-off (see checklist).

## Motivation

fsd today is a set of well-factored **internal** modules (`sources`, `catalog`, `datacube`,
`workflows`, `flatten`) driven by workflow entrypoints that expose implementation vocabulary
(`run_create_datacube`, `flatten(filepaths_df=…, filepath_col=…)`, `input.csv`). The roadmap
(ROADMAP §2.5) requires **scope to go up**: intended users say *"make me training data,"* not
*"flatten these datacubes."* P0 introduces that user-facing layer and the packaging to ship it,
while deliberately deferring everything cloud/model/STAC to later phases. Getting the **verb
signatures** right now is get-it-right-early surface #3 (contract) and #4 (runner/storage seam
boundary) — even the unimplemented verbs.

## What changes (contained, additive)

1. **New `src/fsd/api.py`** — the high-level verb surface, re-exported from `fsd/__init__.py`
   so `import fsd; fsd.create_training_data(...)` works. Wraps existing modules; adds **no**
   new pipeline logic. [SO-1: api.py + top-level re-export]
2. **`create_training_data(...)`** — fully implemented orchestrator over the existing
   `workflows.create_datacube.run_create_datacube` + `datacube.flatten.flatten`. Hides
   `input.csv`, `filepath_col`, and the word "flatten." Returns a `TrainingData` handle.
3. **`download(...)`** — thin verb wrapping `sources.cdse.download` + `TileCatalog`
   construction, so the demo's "download" step is one call. [SO-2: download as its own verb vs
   folded into create_training_data]
4. **`run_inference(...)`, `deploy(...)`** — **signature stubs** that raise
   `NotImplementedError` with docstrings pinning the contract (ROI+dates+mosaic+model_bundle;
   `runner`/`storage` seams; ROI→S2 tiling per ROADMAP §4). No behavior in P0.
5. **Seams as parameters from day one** — every verb takes `runner="local"` and `storage=None`
   (local default). Only `"local"` is wired; anything else raises. Reuses the existing
   `run_create_datacube(runner=…)` guard. [SO-3: seam params present but local-only]
6. **Preflight** — a small `fsd.api._preflight(...)` run **before** any download/build,
   establishing the ROADMAP §2.6 pattern: cheap checks that fail fast (see below). [SO-4]
7. **Packaging polish** — user-facing `README.md` (install-from-GitHub + a ~5-line quickstart),
   version `0.0.1 → 0.1.0`, and verify `pip install git+ssh://…` resolves. **No console-script
   CLI in P0** (fsd is Python-API-first; `python -m fsd.workflows.task` stays). [SO-5]

The existing modules and workflow entrypoints are **unchanged and remain public** — `api.py`
is a façade over them, not a replacement.

## API — precise signatures

```python
# src/fsd/api.py
from dataclasses import dataclass

@dataclass
class TrainingData:
    """Handle to a completed training-data build (paths; lazy-load arrays)."""
    export_folderpath: str            # holds data.npy / ids.npy / labels.npy / coords.npy / metadata.pickle.npy
    run_folderpath: str               # per-field datacubes + input.csv
    n_pixels: int
    n_timestamps: int
    bands: list[str]
    def load(self) -> dict: ...        # {"data","ids","labels","coords","metadata"} via fsd.storage

def download(
    roi, startdate, enddate, bands, dst_folderpath, creds,
    *, max_tiles, max_cloudcover=None, cog=True, progress=True,
    storage=None,
) -> str:                              # returns catalog_filepath (a TileCatalog GeoParquet)
    """Fetch S2 L2A tiles for the ROI/date range into dst_folderpath and build/append its
    TileCatalog. Thin wrapper over sources.cdse.download. Preflighted."""

def create_training_data(
    label_polygons,                    # path or GeoDataFrame: known-label geometries
    catalog_filepath,                  # an existing TileCatalog (from download())
    startdate, enddate, mosaic_days, bands,
    id_col, label_col,
    export_folderpath,
    *,
    scl_mask_classes=config.SCL_MASK_CLASSES,
    feature_sequence=None,             # [SO-6] signature pinned; non-None -> NotImplementedError (P0.5)
    aggregate=None,                    # [SO-6] "median_per_id"|callable|None; non-None -> NotImplementedError (P0.5)
    cores=1, runner="local", storage=None,
    run_folderpath=None,               # default: a subdir of export_folderpath
) -> TrainingData:
    """label polygons + a downloaded catalog -> per-field datacubes -> flattened training
    arrays. Hides `flatten`. Preflighted. runner/storage are seams (local-only in P0)."""

def run_inference(roi, startdate, enddate, mosaic_days, model_bundle,
                  *, runner="local", storage=None, **kw):
    raise NotImplementedError(
        "run_inference lands in P4. Contract: ROI -> S2-grid tiles (ROADMAP §4, port "
        "s2_grid_utils) -> per-grid inference datacubes -> model_bundle (ModelAdapter, "
        "P0.5) -> COG + STAC (spec 17). Preflight validates T==model.n_timestamps and bands.")

def deploy(model_bundle, *, storage=None, **kw):
    raise NotImplementedError(
        "deploy lands in P6. Contract: register a self-describing model bundle "
        "(adapter code + artifact + spec) for scaled inference (ROADMAP §3.4).")
```

### `create_training_data` — implementation (orchestration only)
1. **Preflight** (below). On failure, raise before any heavy work.
2. `run_create_datacube(catalog_filepath, timestamp_col="timestamp", shapefilepath=<label_
   polygons>, id_col, run_folderpath, startdate, enddate, bands, scl_mask_classes,
   mosaic_days, csv_filepath=<run>/input.csv, label_col, cores, runner)` — builds one datacube
   per polygon, writes `input.csv` (already carries `datacube_filepath`,`id`,`label`).
3. `flatten.flatten(filepaths_df=read(input.csv), filepath_col="datacube_filepath",
   id_col="id", label_col="label", export_folderpath)` — the step the user never sees.
4. Read `metadata.pickle.npy` for `n_timestamps`/`bands`, `data.npy` shape for `n_pixels`;
   return `TrainingData`. If `label_polygons` is a GeoDataFrame, write it to a temp GeoJSON
   under `run_folderpath` first (the workflow reads a path).

### Preflight (P0 minimal — the §2.6 pattern) [SO-4]
Checks that cost ~nothing, run before download/build; raise `PreflightError` (aggregating all
failures) on any miss:
- `mosaic_days >= 1`; `startdate < enddate`; `bands` non-empty.
- **`T` is computable & sane**: `T = ceil((enddate-startdate)/mosaic_days) >= 1` (the spec-15
  identity; also the hook where P4 will assert `T == model.n_timestamps`).
- `id_col`/`label_col` exist in `label_polygons`; polygons non-empty & valid geometry.
- `catalog_filepath` exists and is a readable TileCatalog (for `create_training_data`).
- `export_folderpath` writable via `storage`.
- For `download`: `creds` present; `dst_folderpath` writable; `max_tiles >= 1`.

## Out of scope (explicit — later specs)
- **STAC** catalog — **spec 17** (P0 leaves the catalog as today's GeoParquet).
- **`feature_sequence` / `aggregate` behavior** — **P0.5** (ModelAdapter). P0 pins the params
  and raises if used. [SO-6]
- **`run_inference` / `deploy` behavior**, ROI→S2 tiling port (`fsd/grid.py`) — **P4 / P6**.
- **Any Azure** — `runner="batch"`, blob `storage` — **P1/P2**. P0 wires only `"local"`.
- **A console-script CLI** — deferred; `python -m fsd.workflows.task` remains. [SO-5]

## Ripple effects
- `RECIPES.md` — add the `import fsd; fsd.download(...); fsd.create_training_data(...)` recipe.
- `CHANGES.md` — note the new high-level façade (behavior unchanged; existing entrypoints kept).
- `PROGRESS.md` — mark P0/spec-16.
- `README.md` — new user-facing quickstart (was minimal/dev-only).
- No change to `sources`/`catalog`/`datacube`/`workflows`/`flatten` behavior.

## Tests (`tests/test_api.py`, new)
- **`create_training_data` happy path** (synthetic or the EuroCrops subset fixture): produces
  `data/ids/labels/metadata` under `export_folderpath`; `TrainingData` fields match the arrays;
  **hides flatten** (no `input.csv`/`filepath_col` in the public call).
- **GeoDataFrame input** accepted (written to a temp GeoJSON) as well as a path.
- **Preflight rejects before work**: bad dates, `mosaic_days=0`, empty bands, missing
  `id_col`, missing catalog → `PreflightError`, and **no folders/downloads created**.
- **Seam guard**: `runner="batch"` / non-local `storage` → clear error.
- **Stubs**: `run_inference` / `deploy` raise `NotImplementedError` with the contract message.
- **`feature_sequence`/`aggregate` non-None → `NotImplementedError`** (pinned, deferred). [SO-6]
- **Packaging**: a smoke test / documented check that `pip install git+ssh://…` imports and
  exposes `fsd.create_training_data`.

## Sign-off checklist
- [ ] **[SO-1]** `fsd/api.py` façade, re-exported at top level (`fsd.create_training_data`).
- [ ] **[SO-2]** `download` is its own verb (vs folded into `create_training_data`).
- [ ] **[SO-3]** `runner`/`storage` seam params present on every verb, local-only wired.
- [ ] **[SO-4]** Preflight runs before any download/build; raises `PreflightError` with the
      §2.6 checks (incl. the `T` computation).
- [ ] **[SO-5]** Packaging: README quickstart + version 0.1.0 + install-from-GitHub verified;
      **no** console CLI in P0.
- [ ] **[SO-6]** `feature_sequence`/`aggregate` params **pinned in the signature** but raise
      `NotImplementedError` (behavior deferred to P0.5).
- [ ] `run_inference`/`deploy` are contract-pinning stubs; STAC untouched (spec 17).
- [ ] Existing modules/entrypoints unchanged and still public.
