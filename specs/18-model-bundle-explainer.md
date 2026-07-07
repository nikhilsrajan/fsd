# Spec 18 — companion: how the model **bundle** works (SO-6, explained)

> Companion to `specs/18-model-adapter.md`. This explains **[SO-6]** by example: what
> `bundle.json` is, how the string `"adapter": "crop_mapper.adapters:CropRF"` turns back into
> a live Python object, and the full save → load → infer flow. Nothing here is implemented
> yet — it's the design, written as runnable code so we can agree on it before building.

---

## 1. The problem the bundle solves

You train a model on your laptop. Later — maybe on a **different machine**, maybe a **cloud
worker that has never seen your code** — fsd has to run that model over a datacube. For that,
fsd needs three things back:

1. the **artifact** (the trained weights, e.g. `rf.joblib`),
2. the **code** that knows how to featurize the datacube, reshape it, call the model, and
   shape the output (your `ModelAdapter`),
3. the **spec** (which bands, how many timestamps, output dtype/nodata) so fsd can *validate a
   run is compatible before spending money downloading data*.

A **bundle** is just a folder that carries all three, plus a small `bundle.json` manifest that
ties them together. `fsd.model.bundle.save(...)` writes it; `fsd.model.bundle.load(...)` turns
it back into a live adapter object.

```
my_crop_model_bundle/
├── bundle.json        # the manifest (text; git/PR-reviewable)
└── rf.joblib          # the artifact, referenced *relatively* from bundle.json
```

---

## 2. The one confusing line: `"adapter": "crop_mapper.adapters:CropRF"`

That string is an **import path in `module:attribute` form** — the *exact* convention
setuptools "entry points", gunicorn (`gunicorn myapp.wsgi:app`), and uvicorn
(`uvicorn main:app`) use. Read it as:

```
crop_mapper.adapters : CropRF
└────── module ──────┘ └ attr ┘
   importable Python     the class
   module (a .py or       inside it
   package on sys.path)
```

It is **not** a file path and **not** a pickle. It's a *reference* that says: "import the
module `crop_mapper.adapters`, then take the attribute named `CropRF` from it." fsd resolves it
in **four lines of stdlib**:

```python
# src/fsd/model/bundle.py
import importlib

def resolve_ref(ref: str):
    """'crop_mapper.adapters:CropRF' -> the CropRF class object (not an instance)."""
    module_path, _, attr = ref.partition(":")          # ("crop_mapper.adapters", ":", "CropRF")
    if not attr:
        raise ValueError(f"adapter ref must be 'module:attribute', got {ref!r}")
    module = importlib.import_module(module_path)       # like `import crop_mapper.adapters`
    return getattr(module, attr)                        # like `crop_mapper.adapters.CropRF`
```

`importlib.import_module("crop_mapper.adapters")` does the same thing as typing
`import crop_mapper.adapters` — it runs Python's normal import machinery, so `crop_mapper` has
to be **findable on `sys.path`** (i.e. `pip install`ed, or `pip install -e .`'d, or on
`PYTHONPATH`). `getattr(module, "CropRF")` then pulls the class object out. Now fsd holds your
class and can do `adapter = CropRF()` — **without ever importing sklearn itself or knowing
what CropRF does.**

> **Why a reference instead of pickling the whole adapter?** Pickling an object bakes in the
> exact class + library versions and is fragile across machines/versions and unreadable in a
> PR. A `module:attr` string + a `pip install` of your project is portable, reviewable, and
> versioned by your own package — the same reason web servers point at `app:server` rather
> than shipping a pickled server. **The artifact (`rf.joblib`) is still loaded however you
> like** (joblib, torch.load, …) — that happens *inside* your adapter's `load()`, so fsd stays
> framework-agnostic.

---

## 3. Worked example — end to end

### 3.1 Your project (a normal pip-installable package)

```
crop_mapper/                     # your project repo, `pip install -e .`
├── pyproject.toml               # name = "crop_mapper"; depends on fsd, scikit-learn, joblib
└── crop_mapper/
    ├── __init__.py
    └── adapters.py              # <-- the module in "crop_mapper.adapters:CropRF"
```

### 3.2 The adapter (`crop_mapper/adapters.py`)

This is the *only* code you write. It subclasses fsd's optional `BaseModelAdapter` (which
supplies the common `datacube_to_X` reshape), declares the spec + the feature transform, and
implements `load` / `predict` / `to_output`.

```python
# crop_mapper/adapters.py
import joblib
import numpy as np

from fsd.model import BaseModelAdapter, Output
from fsd.bands import modify   # fsd's feature vocabulary (same funcs the legacy demo used)

S2_L2A_BANDS = ["B02", "B03", "B04", "B05", "B06", "B07", "B08", "B11", "B12"]


class CropRF(BaseModelAdapter):
    # --- spec: fsd reads these BEFORE any heavy work (preflight) ---
    required_bands = S2_L2A_BANDS
    n_timestamps = 19                    # T the RF was trained on
    output_dtype = "uint8"
    output_nodata = 255
    output_band_names = ["crop_class"]   # 1 band => categorical map

    # --- F1: ONE feature transform, run by fsd at BOTH train and inference ---
    feature_sequence = [
        (modify.mask_invalid_and_interpolate, {}),
        (modify.compute_bands, dict(bands_to_compute=["NDVI", "NDRE", "GCVI", "SAVI"])),
        (modify.remove_bands, dict(bands_to_remove=S2_L2A_BANDS)),
    ]

    # --- lifecycle: you own these (any framework) ---
    def load(self):
        # self.artifacts is injected by bundle.load() with ABSOLUTE paths (see §3.5).
        self.clf, self.le = joblib.load(self.artifacts["model"])

    # datacube_to_X is inherited from BaseModelAdapter (the legacy reshape:
    #   (T,H,W,B) features -> (H*W, T*B)); override only if your model needs a different shape.

    def predict(self, X_chunk):
        return self.clf.predict(X_chunk)          # fsd hands you valid (non-NaN) rows in chunks

    def to_output(self, raw, hw):
        h, w = hw
        arr = raw.reshape(1, h, w).astype(self.output_dtype)   # (bands=1, H, W)
        return Output(array=arr, dtype=self.output_dtype,
                      nodata=self.output_nodata, band_names=self.output_band_names)
```

Notice: **no file paths hard-coded**, and fsd never appears in your model logic — only in the
imports and the base class.

### 3.3 Train, then build the bundle

```python
# train.py (your code — fsd does not train)
import joblib
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import LabelEncoder

# ... make training data with fsd.create_training_data(adapter=CropRF(), ...), fit ...
clf = RandomForestClassifier(n_estimators=200).fit(X_train, y_train)
le  = LabelEncoder().fit(y_raw)
joblib.dump((clf, le), "rf.joblib")

# now package it into a bundle:
from fsd.model import bundle
from crop_mapper.adapters import CropRF

bundle.save(
    adapter=CropRF(),                        # an instance (fsd reads its declared spec fields)
    artifacts={"model": "rf.joblib"},        # name -> local file to copy into the bundle
    dst="my_crop_model_bundle",              # the bundle folder to create
)
```

### 3.4 What `bundle.save` writes — `my_crop_model_bundle/bundle.json`

`save` reads the spec fields **off the adapter instance**, copies each artifact into the
bundle folder (via the storage seam), and records a **relative** href for each:

```json
{
  "fsd_bundle_version": 1,
  "adapter": "crop_mapper.adapters:CropRF",
  "artifacts": { "model": "rf.joblib" },
  "required_bands": ["B02","B03","B04","B05","B06","B07","B08","B11","B12"],
  "n_timestamps": 19,
  "output_dtype": "uint8",
  "output_nodata": 255,
  "output_band_names": ["crop_class"],
  "feature": { "kind": "sequence",
               "steps": ["mask_invalid_and_interpolate","compute_bands","remove_bands"] }
}
```

- `"adapter"` is filled by `f"{type(adapter).__module__}:{type(adapter).__qualname__}"` —
  fsd derives the `module:attr` string automatically from the object you passed. You don't
  hand-write it.
- The spec fields (`required_bands`, `n_timestamps`, …) are **mirrored** here so fsd can run
  **preflight without importing your code or loading the model** (see §4). The class stays the
  source of truth; the manifest is a cheap, readable copy.
- `"feature"` is a human-readable descriptor only (provenance); the *executable* transform is
  the class's `feature_sequence`.

### 3.5 Loading it back — `bundle.load`

```python
# src/fsd/model/bundle.py  (sketch)
import json, os
from fsd.storage import fs

_SPEC_FIELDS = ("required_bands", "n_timestamps",
                "output_dtype", "output_nodata", "output_band_names")

def load(bundle_path: str):
    with fs.open(os.path.join(bundle_path, "bundle.json")) as f:
        manifest = json.load(f)

    cls = resolve_ref(manifest["adapter"])       # §2: 'crop_mapper.adapters:CropRF' -> class
    adapter = cls()                              # instantiate (no artifacts yet)

    # give the adapter ABSOLUTE artifact paths, resolved relative to the bundle folder:
    adapter.artifacts = {
        name: os.path.join(bundle_path, rel_href)
        for name, rel_href in manifest["artifacts"].items()
    }

    # (optional) cross-check the class's declared spec against the manifest to catch drift:
    for field in _SPEC_FIELDS:
        if getattr(adapter, field, None) != manifest[field]:
            raise ValueError(f"bundle/{field} disagrees with {manifest['adapter']}.{field}")

    adapter.load()                               # YOUR load(): joblib.load(self.artifacts['model'])
    return adapter                               # a ready-to-use ModelAdapter
```

### 3.6 Using it — `run_inference`

`run_inference` accepts either a live adapter **or** a bundle path (it just calls
`bundle.load` for you):

```python
import fsd

result = fsd.run_inference(
    model="my_crop_model_bundle",              # a bundle path (or CropRF() directly)
    inference_datacubes="…/inference_datacubes",  # folder / input.csv of pre-built cubes
    output_folderpath="…/model_outputs",
    merge=True,                                 # also write a single merged COG (legacy behavior)
)
# -> writes one COG per datacube + a STAC catalog under output_folderpath
```

---

## 4. The payoff: **model-free preflight**

Because the spec fields live in `bundle.json` as plain text, fsd can answer *"is this run even
compatible?"* by reading a tiny JSON file — **no importing your package, no loading the
RF, no touching the network**:

```python
with fs.open("my_crop_model_bundle/bundle.json") as f:
    spec = json.load(f)

T = fsd.compute_n_timestamps(startdate, enddate, mosaic_days)   # pure function (spec 15)
if T != spec["n_timestamps"]:
    raise fsd.PreflightError(
        f"your dates/mosaic_days give T={T} but the model needs T={spec['n_timestamps']}")
if not set(spec["required_bands"]).issubset(requested_bands):
    raise fsd.PreflightError("model needs bands you didn't request")
```

This is the ROADMAP §2.6 promise: refuse an incompatible run **before** a fan-out spends money
downloading tiles. The full adapter (code + artifact) is only imported/loaded once the run is
known to be valid and actually starts predicting.

---

## 5. Why this travels to the cloud later (P4/P6 preview)

On an Azure Batch worker the same three pieces are needed. The bundle makes that a config
problem, not a code problem:

- **code** → your `crop_mapper` package is `pip install`ed into the fsd container image (or the
  worker pulls it), so `crop_mapper.adapters:CropRF` resolves there exactly as on your laptop.
- **artifact** → `bundle.save`/`load` go through the **storage seam**, so
  `load("abfss://…/my_crop_model_bundle")` works unchanged; the `rf.joblib` href is still
  relative to the bundle folder.
- **spec** → the same `bundle.json` drives the same preflight before the cloud fan-out.

`deploy(bundle, …)` (P6) is then just "put this bundle where workers can reach it and register
it" — the *format* we're pinning now doesn't change.

---

## 6. FAQ

- **What if my adapter needs more than one artifact?** `artifacts={"model": "rf.joblib",
  "scaler": "scaler.joblib"}` → all copied in, all resolved to absolute paths in
  `self.artifacts`; read whichever you need in `load()`.
- **Does `crop_mapper` have to be pip-installed?** Yes — it must be importable on `sys.path`
  (`pip install -e .` in dev is enough). That's the deliberate trade for portability over
  pickling. A future no-code path (config-only) is out of scope [SO-1/F5].
- **Can I skip the bundle and just pass `CropRF()`?** Yes, for local iteration
  `run_inference(model=CropRF()...)` works. The bundle exists for *reproducibility and
  travel* (other machines, cloud, PR review, P6 registration).
- **Where does the feature transform run?** Inside fsd, from `adapter.feature_sequence`, in
  **both** `create_training_data` and `run_inference` — that's the F1 anti-skew guarantee; the
  bundle just makes sure the same class (hence the same sequence) is what gets loaded.
