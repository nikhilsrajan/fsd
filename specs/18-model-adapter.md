# Spec 18 — ModelAdapter contract + local train/deploy (P0.5)

> **Superseded in part:** the engine's `cores>1` inference used a `multiprocessing.Pool` here;
> **spec 22 retired it** — `cores>1` now fans out via the Snakemake infer-only runner, `cores=1`
> stays the in-process path, and inference is idempotent (skip existing unless `overwrite`). The
> contract/adapter/bundle/features design below is unchanged.

> **Status: SIGNED OFF + IMPLEMENTED + VERIFIED (2026-07-06).** SO-1..SO-8 approved as drafted.
> New `src/fsd/model/` (`adapter`/`features`/`engine`/`bundle`) + `catalog.stac.cog_outputs_to_items`
> (spec 17 SO-6) + `api.py` wiring (`create_training_data(adapter/feature_sequence/aggregate)`,
> real `run_inference`, `deploy` docstring); exports `ModelAdapter`/`BaseModelAdapter`/`Output`/
> `load_bundle`/`save_bundle`. Example `examples/eurocrops_rf.py`; runbook `tests/manual/deploy.md`;
> `tests/test_model.py` (9 tests). **150 tests, ruff clean.** One real bug found+fixed: the
> engine now **copies `band_indices`** before `modify_bands` (which mutates it in place) so
> reusing the dict across cubes can't corrupt it. Companion: `specs/18-model-bundle-explainer.md`.
>
> Roadmap phase **P0.5** — the last P0-tier
> piece before Azure, and the one that makes fsd a *product* (plug-in models), not just a
> data pipeline. Formalizes ROADMAP §3 (F1–F5) into running code, **fully local (Mode A)**:
> a project team declares a small **ModelAdapter**, trains their own model (fsd doesn't care
> how), and fsd runs **create_training_data** and **inference → COG + STAC** with **one**
> feature-transform definition shared across both (the anti-skew invariant).
>
> Reproduces the legacy `demo_02_model_train` + `demo_03_model_deploy` (EuroCrops RF) through
> the fsd verbs. **Does NOT** touch Azure, ROI→S2 tiling, or bundle *registration* (those are
> P4/P6); this is the local engine those phases will call.
>
> Decisions flagged **[SO-n]** need explicit sign-off (see checklist). Contract F-refs map to
> ROADMAP §3: F1 anti-skew feature transform, F2 fsd owns predict loop, F3 output shaping,
> F4 per-id aggregation, F5 code-first bundle.

## Motivation

The legacy feature transform (`mask_invalid_and_interpolate → compute NDVI/NDRE/GCVI/SAVI →
remove raw bands`) is **copy-pasted** between `demo_02_model_train.ipynb` (cell-4) and
`model/demo_model_deploy.py::modify_datacube` — the textbook train/serve-skew trap. Two
copies *will* drift. The whole roadmap (verb API, inference-at-scale, deploy) is pinned on a
model contract that (a) makes fsd run that transform **once**, in both directions, and (b)
lets a team plug a model in without fsd knowing the framework. Building it **locally now**
pins the contract shape with running code, is independent of the rslearn build-vs-borrow
decision (the model contract is ours regardless), and completes Mode A end-to-end.

## Design stance — code-first, structural, additive [SO-1]

The adapter is a **plain Python class** the user writes, referenced by **import-path** (F5),
that fsd **duck-types** — no forced base class, matching the OQ-3 precedent ("source contract
is a documented function signature, no ABC, until a real 2nd implementation exists"). We ship:
- a **`ModelAdapter` `typing.Protocol`** (documentation + static typing; structural, not
  inherited), and
- an optional **`BaseModelAdapter`** convenience (sensible defaults for `datacube_to_X` /
  `to_output`) a user *may* subclass but need not.

Nothing in the existing pipeline changes shape; this is **additive** (`create_training_data`
gains wiring for its already-declared `feature_sequence`/`aggregate` params; `run_inference`
gets a real local body; a new `src/fsd/model/` package appears).

## The contract (`src/fsd/model/adapter.py`)

```python
class ModelAdapter(Protocol):
    # --- declarations fsd reads BEFORE any heavy work (preflight) ---
    required_bands: list[str]        # must be obtainable from the datacube/source
    n_timestamps: int                # T the model was trained on; fsd asserts == derived T
    output_dtype: str                # e.g. "uint8"
    output_nodata: int | float       # e.g. 255
    output_band_names: list[str]     # 1 => categorical map; N => probs/regression bands

    # --- feature engineering: ONE definition, run by fsd at train AND inference [F1] ---
    feature_sequence: list[tuple[Callable, dict]] | None   # a fsd bands.modify sequence (primary)
    def features(self, data5d, band_indices) -> tuple[np.ndarray, dict]: ...  # escape hatch (optional)

    # --- model lifecycle (user owns; any framework) ---
    def load(self) -> None: ...                       # load artifact ONCE per worker
    def datacube_to_X(self, feats, band_indices): ... # reshape features -> model input
    def predict(self, X_chunk): ...                   # raw model output; fsd owns the loop [F2]
    def to_output(self, raw, hw) -> Output: ...       # -> (bands,H,W)+dtype/nodata/names [F3]
```

`Output = namedtuple("Output", "array dtype nodata band_names")` with `array` shape
`(bands, H, W)`.

### F1 — the anti-skew invariant [SO-2]
The feature transform is declared **once, in the adapter**, as a `bands.modify` **sequence**
(the primary path — the exact legacy vocabulary already exists in `fsd.bands.modify`:
`mask_invalid_and_interpolate`, `compute_bands`, `remove_bands`, `scale_bands`), with an
escape-hatch `features()` callable for anything the sequence can't express. **fsd runs it in
both directions** via the 5-D contract `(samples, timestamps, H, W, bands)`:
- **training** (`create_training_data`): flattened samples `(N, T, B)` →
  `bands.modify.expand_flattened` → run transform → squeeze → store.
- **inference**: datacube `(T, H, W, B)` → `expand_datacube` → run transform → squeeze.

Same function object, same params, both times → skew is structurally impossible.

### F2 — fsd owns the predict loop [SO-3]
fsd, not the adapter, drives inference over a datacube (generalizing
`demo_model_deploy.get_model_output`):
1. run the feature transform (F1),
2. `adapter.datacube_to_X(feats, band_indices)` → `X` of shape `(H·W, n_features)`,
3. **drop invalid rows** (any-NaN) by default (`skip_nan=True`) — models rarely accept NaN;
   the dropped pixels get `output_nodata`,
4. call `adapter.predict` in **chunks** of `predict_batch_size` (default = whole tile),
5. scatter predictions back into a full `(H·W,)`/`(H·W, bands)` array filled with
   `output_nodata`, reshape to `(bands, H, W)`.

`BaseModelAdapter` supplies the common `datacube_to_X` (the legacy
`reshape(T,HW,B).swapaxes(0,1).reshape(HW, T·B)`) so a typical adapter writes almost nothing.

### F3 — output shaping → COG + STAC [SO-4]
`adapter.to_output(raw, hw)` returns the `(bands, H, W)` array + `dtype`/`nodata`/`band_names`.
fsd writes a **lossless COG with overviews** by **reusing `fsd.raster.cog.to_cog`** (not the
legacy `rio_cogeo` path), using the datacube metadata's `geotiff_metadata` `transform`/`crs`,
then builds a **STAC catalog over the outputs** by **implementing spec-17's designed-for
`cog_outputs_to_items`** (spec 17 SO-6: "one Item per output COG, `proj:*` free because we
just wrote it"). Output STAC reuses `write_stac_catalog` + the asset/media-type helpers.

### F4 — per-id aggregation (optional, off by default) [SO-5]
`create_training_data(aggregate=...)`: `None` (default, per-pixel — matches what the legacy
notebook actually trains on), `"median_per_id"` (the `np.nanmedian` per-`id` reducer from
`demo_02` cell-3), or a `callable(ids, data, labels) -> (ids, data, labels)`. Applied **before**
the feature transform. The **train-per-id / predict-per-pixel asymmetry is documented, not
blocked** (ROADMAP §3.3 "honest asymmetry").

### F5 — the model bundle [SO-6]
A **self-describing, loadable** bundle so adapter code + artifact(s) + spec travel together:
```
bundle/
  bundle.json     # {adapter: "my_pkg.adapters:CropRF", artifacts: {model: "rf.joblib"},
                  #  required_bands: [...], n_timestamps: 19, output_dtype: "uint8",
                  #  output_nodata: 255, output_band_names: [...], feature: {...descriptor...}}
  rf.joblib       # artifact(s), referenced relatively
```
`fsd.model.bundle.load(path) -> ModelAdapter` imports the adapter class, injects artifact
paths, calls `.load()`. `save(adapter, path)` writes the manifest + copies artifacts (via the
**storage seam**, so blob works later). **Registration/push is P6** — `deploy` stays a stub
that will consume this bundle; `run_inference` accepts either a live adapter **or** a bundle
path. `bundle.json` also records the declared `n_timestamps`/`required_bands` so preflight can
validate **without importing/loading the model**.

## Verbs (wiring, `src/fsd/api.py`)

### `create_training_data(..., adapter=None, feature_sequence=None, aggregate=None)`
Wire the already-declared params (they currently raise `NotImplementedError`):
- If `adapter` given, fsd reads `adapter.feature_sequence`/`adapter.features` (anti-skew
  preferred) and validates `adapter.required_bands ⊆ bands` and (if declared)
  `compute_n_timestamps(...) == adapter.n_timestamps` **in preflight**. Passing both `adapter`
  and a raw `feature_sequence` is a preflight error (ambiguous).
- After flatten: optional `aggregate` → feature transform → write **`features.npy`**
  (+ feature band names in metadata) **additively**; raw `data.npy` is **kept** (cheap;
  enables re-featurizing without re-flatten). `TrainingData` gains `features`/`feature_bands`
  and `.load()` returns `features` when present.
- Adapter-less use still works: pass `feature_sequence`/`aggregate` directly (exploratory).

### `run_inference(...)` — local engine (P0.5 scope) [SO-7]
P0.5 implements the **local inference core**: given **already-built inference datacubes**
(a folder or an `input.csv` of `datacube_filepath`s, exactly like `demo_03`) + an adapter/bundle,
produce one **COG per datacube** + a **STAC catalog**, with an optional **merged** COG
(the legacy `merge_images`). Signature (local-first; the ROI form is P4):
```python
run_inference(model, inference_datacubes, output_folderpath, *,
              predict_batch_size=None, skip_nan=True, merge=False,
              cores=1, runner="local", storage=None) -> InferenceResult
```
**Preflight** (before any predict): assert every datacube's `bands ⊇ required_bands` and
`len(timestamps) == n_timestamps`; refuse with an explanatory error otherwise (ROADMAP §2.6).
The **ROI → S2-tiling + download → build → this core** front-end stays the **P4** stub — P4
calls this same engine, so the contract is pinned now. `runner`/`storage` local-only in P0.5.

### `deploy(...)`
Stays a P6 stub, but its docstring is updated to name the concrete bundle format from SO-6.

## Module layout (new `src/fsd/model/`)
- `adapter.py` — `ModelAdapter` Protocol, `BaseModelAdapter`, `Output`.
- `engine.py` — `infer_datacube(adapter, datacube, metadata, ...)` (F1→F2→F3 for one cube) +
  the fan-out over many cubes (reuses the `workflows` runner seam; local now).
- `bundle.py` — `save`/`load` (storage-seam aware).
- `features.py` — the shared 5-D transform runner (`apply_feature_transform(data5d,
  band_indices, adapter)`) used by both verbs (the single anti-skew chokepoint).

## Example + validation
- **Example adapter** (`examples/eurocrops_rf.py`, not shipped in the wheel): wraps
  `(clf, le)` from a joblib, declares the NDVI/NDRE/GCVI/SAVI `feature_sequence`, `required_bands
  = the 9 S2 L2A bands`, categorical `to_output`. Reproduces demo_02+demo_03.
- **Mode A manual runbook** `tests/manual/deploy.md`: EuroCrops fields → `create_training_data`
  (with adapter) → user trains RF → wrap in adapter/bundle → `run_inference` over the
  translated-Ethiopia grids → COG + STAC + merged map, QGIS-eyeballed (visual-validation rule).
- **pytest** `tests/test_model.py` (synthetic, deterministic): a tiny fake adapter (argmax over
  a NDVI feature) exercises the engine — feature transform runs once, predict-loop chunking +
  NaN→nodata scatter, `(bands,H,W)` COG written (transform/crs preserved), STAC round-trips,
  preflight rejects band/`T` mismatch, `median_per_id` reducer, bundle save/load.

## Out of scope (explicit)
- **Azure / Batch / blob**, ROI→S2 tiling + download (P4), bundle **registration/push** (P6).
- **No-code adapters** (config-only) — code-first only [F5]; revisit if a real need appears.
- **Training** — permanently user-side; fsd never fits a model.
- **Regression/multi-band outputs** are *supported by the contract* (`output_band_names` len>1)
  but the shipped example is categorical; a regression example can come later.

## Ripple effects
- `api.py` — wire `create_training_data` feature/aggregate/adapter; real `run_inference` body;
  `deploy` docstring. `__init__`/`__all__` export `ModelAdapter`, `BaseModelAdapter`, `load_bundle`.
- `catalog/stac.py` — implement `cog_outputs_to_items` (spec 17 SO-6, was designed-for).
- `pyproject.toml` — no new **core** dep (joblib/sklearn live in the *example*, not fsd core;
  add an optional `[model-example]` extra if the runbook needs them).
- Living docs: `CHANGES.md` (verbs wired; STAC output builder), `RECIPES.md` (adapter + inference
  recipe), `TODO.md` (regression example; no-code path), `DROPPED.md` (legacy `rio_cogeo` deploy
  path → fsd `to_cog`), `PROGRESS.md`, `specs/16` + `specs/17` back-pointers, `ROADMAP.md` (mark
  P0.5 spec'd). `notebooks/` guidance unchanged.

## Sign-off checklist
- [x] **[SO-1]** Adapter = code-first class, duck-typed; ship a `Protocol` + optional
      `BaseModelAdapter` (no forced ABC, per OQ-3). Additive; no pipeline reshape.
- [x] **[SO-2]** F1: one feature transform in the adapter (`feature_sequence` primary, `features()`
      escape hatch), run by fsd in BOTH verbs via the 5-D contract. Training writes `features.npy`
      additively; raw `data.npy` kept.
- [x] **[SO-3]** F2: fsd owns the predict loop (feature→`datacube_to_X`→drop-NaN→chunked
      `predict`→`nodata` scatter→`(bands,H,W)`); `predict_batch_size`/`skip_nan` flags;
      `BaseModelAdapter` supplies the common reshape.
- [x] **[SO-4]** F3: `to_output`→`(bands,H,W)`+dtype/nodata/names; fsd writes lossless COG via
      `raster.cog.to_cog` (transform/crs from `geotiff_metadata`) + STAC via new
      `cog_outputs_to_items` (spec 17 SO-6).
- [x] **[SO-5]** F4: `aggregate ∈ {None default, "median_per_id", callable}` before the transform;
      per-id/per-pixel asymmetry documented, not blocked.
- [x] **[SO-6]** F5: self-describing loadable **bundle** (manifest + artifacts, storage-seam
      aware; spec fields enable model-free preflight). `run_inference` takes adapter **or** bundle;
      push/register deferred to P6.
- [x] **[SO-7]** `run_inference` P0.5 = local engine over **pre-built inference datacubes** →
      COG+STAC (+optional merge); ROI→tiling front-end stays P4 and will call this core. Preflight
      asserts bands ⊇ required_bands and `T == n_timestamps` before any predict.
- [x] **[SO-8]** New `src/fsd/model/` (adapter/engine/bundle/features); example EuroCrops RF +
      `tests/manual/deploy.md` + synthetic `tests/test_model.py`; living docs updated.
