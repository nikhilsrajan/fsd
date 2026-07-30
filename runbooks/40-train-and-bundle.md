---
status: current
summary: Train adapters:DemoRF @ T=8 and bundle it, driver-side; not yet run at the time of this stamping.
---

# Run-book: 40 Phases 1–3 — features → train `adapters:DemoRF` @ T=8 → bundle

> Spec-24 run-book. **You** run this; paste back each phase's printed `_result.json`. This is the
> **missing link** between `runbooks/39-training-data-on-aml.md` (which landed the raw training
> arrays) and `runbooks/38-inference-on-aml.md` (whose **Phase 0** stages the bundle this run-book
> produces). No new fsd code: bundling (`fsd.model.bundle.save`) and the driver-side feature path
> (`api._apply_training_features`) already exist; **training is permanently user-side** (ADR-0018 /
> CLAUDE.md — fsd does NOT train).
>
> **Concrete `rise` values are NOT in this file** (public repo). Paste them as env vars from the
> uncommitted `../../AZURE_INFRA_PRIVATE.md` (workspace root). Run the private-identifier sweep
> (`RECIPES.md`) before pushing anything derived from this run-book.

## Purpose

Turn the landed training arrays (`runbooks/39-training-data-on-aml.md` Phase 1 →
`tests/outputs/p39_training_data_aml/landed/`, a `(172781, 8, 3)` uint16 `data.npy` over bands
**B04/B08/B8A**, **T=8**) into a trained + bundled **`adapters:DemoRF`**:

1. **Phase 1** — add `features.npy` to the landed set: **median-per-field** aggregation
   (`aggregate="median_per_id"`, ~900 field rows) + **DemoRF's feature transform, on the driver**
   (ADR-0020: the general-purpose cluster image emits raw; the adapter never reaches a node).
2. **Phase 2** — **you** train DemoRF at **T=8** on the ~900 field medians (RF + `LabelEncoder` →
   `joblib`, a few-hundred-KB model). fsd does not train.
3. **Phase 3** — **bundle** it (`fsd.model.bundle.save`) and prove the bundle round-trips. This bundle
   folder is exactly what `runbooks/38-inference-on-aml.md` **Phase 0** stages to blob (`AZ_BUNDLE_LOCAL`).

## Locked (2026-07-27, user) — do NOT re-litigate
- **Demo model = `adapters:DemoRF`** — `required_bands=[B04,B08]`, trained at **T=8**. It lives at
  **`demos/adapters.py`** (in this repo, but **not in the fsd wheel** — the wheel packages only
  `src/fsd/`), importable as `adapters` with `demos/` on `PYTHONPATH`. Phase 1/2/3 do
  `from adapters import DemoRF`; the inference image (`runbooks/38-*` D4) `COPY`s `demos/adapters.py`
  so `adapters:DemoRF` resolves on a node. `[B04,B08] ⊆ [B04,B08,B8A]`, so the landed arrays already
  carry DemoRF's bands.
- **DemoRF pins `n_timestamps = 0` on purpose** — T is *model-determined*: the run sets it on the
  instance and **the bundle records it** (bundle-safe for any T). So Phase 3 sets `adapter.n_timestamps
  = 8` before `bundle.save`, and the resulting `bundle.json` carries `n_timestamps: 8` — which is what
  runbook 38's inference preflight reads (`read_spec` → `want_t`, `api.py:1072`). A fresh `DemoRF()`
  reads `n_timestamps == 0`; that is correct, not a bug.
- This run-book **feeds an intact runbook 38** — it does not touch 38's tested Phases 0–3.

## Prerequisites
- **`runbooks/39-training-data-on-aml.md` Phase 1 GREEN** — the raw arrays are landed under
  `tests/outputs/p39_training_data_aml/landed/` (`data.npy`/`ids.npy`/`labels.npy`/`coords.npy`/
  `metadata.pickle.npy`; **no `features.npy` yet** — Phase 1 there passed no adapter).
- **`demos/adapters.py:DemoRF` importable as `adapters`** (`required_bands=[B04,B08]`,
  `n_timestamps=0` model-determined, categorical `uint8`/`255`; `feature_sequence` =
  `mask_invalid_and_interpolate` → compute NDVI+SAVI from B04/B08 → remove B04/B08/B8A ⇒ **2 feature
  bands**). It is in the repo — just put `demos/` on `PYTHONPATH` (below); no separate local module.
- The fsd venv with the aml extra **and the training deps** (sklearn + joblib):
  ```bash
  cd fsd && source .venv/bin/activate && pip install -e ".[dev,aml]" scikit-learn joblib
  export PYTHONPATH="$PWD/demos:$PYTHONPATH"     # so `from adapters import DemoRF` resolves
  ```
  (Phase 1 re-runs the aml reduce; Phase 2/3 are fully local.)
- **VPN connected**, `az login` done, correct subscription selected — Phase 1's reduce dispatches an
  AML job and the driver does blob I/O (reading `input.csv`, `_status/*.json`, land-local reads).
  Phases 2 and 3 are fully **local** (no cluster, no VPN).

## Setup — paste your concrete values (from `AZURE_INFRA_PRIVATE.md`, uncommitted)
```bash
cd fsd
export AZ_RG='<resource group>'
export AZ_ML_WORKSPACE='<aml workspace>'
export AZ_SUBSCRIPTION_ID='<subscription id>'
export AZ_CLUSTER='<the d16 cluster name>'
export AZ_UAMI_NAME='<compute identity name>'
export AZ_ACCOUNT='<storage account>'
export AZ_FS='<filesystem/container>'
export AZ_ROOT="abfss://${AZ_FS}@${AZ_ACCOUNT}.dfs.core.windows.net/fsd-p2-build"   # runbook 36/39's root
export AZ_ENV_NAME='fsd-aml-env'
export AZ_ENV_VERSION="$(az ml environment list -n "$AZ_ENV_NAME" -g "$AZ_RG" \
  -w "$AZ_ML_WORKSPACE" --query "[].version" -o tsv | sort -V | tail -1)"
export AZ_UAMI_CLIENT_ID="$(az identity show -g "$AZ_RG" -n "$AZ_UAMI_NAME" --query clientId -o tsv)"
echo "environment: ${AZ_ENV_NAME}:${AZ_ENV_VERSION} ; client id: ${AZ_UAMI_CLIENT_ID:0:8}…"

# The runbook-36 Phase-3 input.csv (900 cubes, id/label/datacube_filepath) — SAME as runbook 39 Phase 1.
export AZ_PHASE3_INPUT_CSV="${AZ_ROOT}/runs/<phase3-run-id>/input.csv"

# The arrays runbook 39 Phase 1 landed. Phase 1 below adds features.npy INTO this folder.
export LANDED="$PWD/tests/outputs/p39_training_data_aml/landed"

export OUT40="$PWD/tests/outputs/p40_train_and_bundle"   # gitignored. Distinct from runbook 38's OUT38,
                                                         # so running the two back-to-back can't cross-write.
mkdir -p "$OUT40"

# Fail cheap on the driver BEFORE any cluster spend: the landed raw arrays must already exist.
.venv/bin/python - <<'PY'
import os
from fsd.storage import fs
landed = os.environ["LANDED"]
for name in ("data.npy", "ids.npy", "labels.npy", "coords.npy", "metadata.pickle.npy"):
    assert os.path.exists(os.path.join(landed, name)), f"missing landed array: {name} (run runbook 39 Phase 1 first)"
assert not os.path.exists(os.path.join(landed, "features.npy")), \
    "features.npy already present — Phase 1 already ran (fine to re-run; it overwrites features)."
assert fs.exists(os.environ["AZ_PHASE3_INPUT_CSV"]), "AZ_PHASE3_INPUT_CSV not on blob (wrong run-id? VPN off?)"
try:
    from adapters import DemoRF
    a = DemoRF()
    assert a.required_bands == ["B04", "B08"], f"DemoRF.required_bands={a.required_bands} (expected [B04,B08])"
    # n_timestamps is model-determined (DemoRF pins 0); Phase 3 sets it to 8 on the instance and the
    # bundle records it. A fresh DemoRF() reading 0 here is correct, not an error.
    assert a.n_timestamps == 0, f"DemoRF.n_timestamps={a.n_timestamps} (expected 0 — T is set at bundle time)"
    print("preflight OK: landed arrays present; input.csv reachable; DemoRF importable (T set at bundle time)")
except ImportError:
    raise SystemExit("`from adapters import DemoRF` failed — put `demos/` on PYTHONPATH (see Prerequisites).")
PY
```
- **PASS if:** the preflight prints `preflight OK: …`. A failing assert names exactly what to fix.

## Phase 1 — `features.npy` = median-per-field + DemoRF's transform (driver-side)

> **`aggregate="median_per_id"` — the modelling unit, not just a size trick.** The labels are
> **per field** (one crop class per `id`), so the honest training sample is the field, not the pixel.
> `median_per_id` (`np.nanmedian` over each field's pixels, one row per `id`, label by first
> occurrence — `fsd/model/features.py:40`) collapses the **172,781 pixels → ≤900 field medians**
> *before* DemoRF's NDVI/SAVI transform runs. This (a) denoises mixed/edge pixels, matching legacy
> demo_02, and (b) keeps the trained model **tiny** — an *un*aggregated per-pixel RF on 172k rows
> bloats to ~1 GB, and **the bundle is fetched to every inference node** (D3), so size matters. It is
> **training-only**: `aggregate` is separate from `DemoRF.feature_sequence`, so inference still applies
> the same NDVI/SAVI transform **per pixel** → a per-pixel crop map (the demo_02/03 design, not skew).
>
> **Why this re-runs the aml reduce (design note, option (a)):** `flatten_training_data(...,
> adapter=DemoRF(), aggregate="median_per_id")` on `runner="aml"` dispatches the single-node reduce
> again (**~2.5 min**, one node — measured 146 s), but `_land_local` **skips** every array already
> landed locally (`api.py:613` — existence = already landed), so nothing is re-transferred; then
> `_apply_training_features` runs the median **then** DemoRF's `feature_sequence` **on the driver** over
> the local `data.npy` and writes `features.npy` (+ `feature_ids`/`feature_labels`, at field level).
> This is the KISS path — **zero new fsd code**. A public `fsd.apply_features(export_folderpath,
> adapter=…, aggregate=…)` verb over already-landed arrays would avoid the re-run (option (b) in
> `runbooks/HANDOFF-train-and-bundle.md`), but it needs a 1-para spec + a test and the ~2.5-min re-run
> does not justify it (YAGNI). **The adapter never reaches a node** (ADR-0020): the reduce command is
> a bare `python -m fsd.workflows.flatten …` with no `--adapter` flag — the transform is driver-only.
>
> **Note on nodata:** `median_per_id` uses `np.nanmedian`, but raw nodata is `0` (not NaN), so a
> fully/partly-cloudy field-timestep leans on `mask_invalid_and_interpolate` (the FIRST step of
> `DemoRF.feature_sequence`, which runs *after* the median) to clean up — same as legacy demo_02.

```bash
cat > "$OUT40/phase1.py" <<'PY'
import json, os, time
from fsd import api
from adapters import DemoRF     # demos/adapters.py (in repo, not in the wheel) -- demos/ on PYTHONPATH

t0 = time.time()
td = api.flatten_training_data(
    os.environ["AZ_PHASE3_INPUT_CSV"],
    export_folderpath=os.environ["LANDED"],   # the runbook-39 landed folder; land-local skips existing arrays
    id_col="id", label_col="label",
    adapter=DemoRF(),                          # -> features.npy applied DRIVER-SIDE after land-local (ADR-0020)
    aggregate="median_per_id",                 # -> ~900 field medians BEFORE NDVI/SAVI (denoise + tiny model)
    runner="aml",
    runner_kwargs=dict(
        cluster=os.environ["AZ_CLUSTER"],
        environment=f"{os.environ['AZ_ENV_NAME']}:{os.environ['AZ_ENV_VERSION']}",
        root=os.environ["AZ_ROOT"], identity_client_id=os.environ["AZ_UAMI_CLIENT_ID"],
        subscription_id=os.environ["AZ_SUBSCRIPTION_ID"], resource_group_name=os.environ["AZ_RG"],
        workspace_name=os.environ["AZ_ML_WORKSPACE"], run_id="rb40-features",
    ),
)
wall = time.time() - t0

d = td.load()
feats = d["features"]
out = {
    "phase": "phase1-features", "pass": True,
    "wall_seconds": round(wall, 1),
    "feature_bands": td.feature_bands,
    "features_shape": list(feats.shape),
    "feature_ids_len": len(d["feature_ids"]),
    "feature_labels_present": "feature_labels" in d,
    "feature_labels_len": len(d["feature_labels"]) if "feature_labels" in d else None,
    "raw_data_kept": os.path.exists(os.path.join(os.environ["LANDED"], "data.npy")),
    "n_timestamps": td.n_timestamps, "bands": td.bands,
}
# machine-check the shape contract: (n_fields, T=8, n_feature_bands); labels align 1:1 with features.
out["pass"] = (
    feats.ndim == 3 and feats.shape[1] == 8 and feats.shape[2] >= 1
    and out["feature_ids_len"] == feats.shape[0]
    and out["feature_labels_present"] and out["feature_labels_len"] == feats.shape[0]
    and out["raw_data_kept"]
)
print("FSD_RESULT_BEGIN"); print(json.dumps(out, indent=2, default=str)); print("FSD_RESULT_END")
with open(f"{os.environ['OUT40']}/phase1_result.json", "w") as f:
    json.dump(out, f, indent=2, default=str)
PY
.venv/bin/python "$OUT40/phase1.py"
```
- **Expect:** **one** AML job in the Studio UI (a reduce, not a fan-out); then `features.npy`,
  `feature_ids.npy`, `feature_labels.npy` appear under `$LANDED` alongside the kept raw `data.npy`.
- **PASS if:** `pass: true`, i.e. `features_shape` is **`(≈900, 8, 2)`** — one row **per field**
  (`median_per_id` collapsed the 172,781 pixels to ≤900 unique `id`s; the exact count = fields with ≥1
  valid pixel), T=8, and 2 feature bands (`feature_bands == ["NDVI", "SAVI"]` — DemoRF computes NDVI+SAVI
  then removes B04/B08/B8A). `feature_labels_present: true` and both `feature_ids_len`/`feature_labels_len`
  equal `features_shape[0]`; `raw_data_kept: true` (the transform is additive — `data.npy` stays).
  **Without** `aggregate` you'd instead see `(172781, 8, 2)` — one row per pixel, and a ~1 GB model
  downstream; the median is what keeps it field-level and small.
- **FAIL — `adapter.required_bands not in requested bands`:** the landed cube bands (B04/B08/B8A)
  don't cover DemoRF's `required_bands` — but `[B04,B08] ⊆ [B04,B08,B8A]`, so this only fires if
  DemoRF was edited; check its `required_bands`.
- **FAIL — a KeyError / band-not-found inside the transform:** DemoRF's `feature_sequence` references
  a band not in `metadata["bands"]` (B04/B08/B8A). Its indices must be computable from those three.
- **If it fails:** paste `$OUT40/phase1_result.json`.

## Phase 2 — train DemoRF at T=8 (YOUR sklearn code — fsd does NOT train)

> **This is permanently user-side** (ADR-0018 / CLAUDE.md). The run-book *guides* your training; it
> adds no fsd code. Below is the reference flow (spec 19 demo_02 / `examples/eurocrops_rf.py`
> docstring) — adapt it to your own metrics/validation. The artifact must be whatever `DemoRF.load()`
> expects to `joblib.load` (the sketch loads `(clf, label_encoder)`).
>
> **Keep the model small — it's fetched to every inference node** (D3). With `median_per_id` you're
> training on ~900 field rows, so a plain `RandomForestClassifier` is already a few hundred KB (the
> result below records `model_bytes` — sanity-check it's MB, not GB). If you ever drop the aggregate
> and train per-pixel (172k rows), an unpruned RF balloons to ~1 GB; then add `min_samples_leaf=50`
> and `joblib.dump(..., compress=3)`. At field level you don't need either.

```bash
cat > "$OUT40/phase2_train.py" <<'PY'
import json, os
import joblib
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import LabelEncoder
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score
from fsd.storage import fs

LANDED = os.environ["LANDED"]
features = fs.load_npy(os.path.join(LANDED, "features.npy"))          # (n_fields≈900, T=8, Bf=2)
feature_labels = fs.load_npy(os.path.join(LANDED, "feature_labels.npy"))
X = features.reshape(len(features), -1)                 # (n_fields, T*Bf) -- T-outer, band-inner
y_raw = feature_labels

le = LabelEncoder().fit(y_raw)
y = le.transform(y_raw)
Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.25, random_state=0, stratify=y)
clf = RandomForestClassifier(n_estimators=200, n_jobs=-1, random_state=0).fit(Xtr, ytr)

train_acc = accuracy_score(ytr, clf.predict(Xtr))
test_acc = accuracy_score(yte, clf.predict(Xte))

# Persist EXACTLY what DemoRF.load() expects to joblib.load (adapt if your adapter differs).
artifact = os.path.join(os.environ["OUT40"], "rf.joblib")
joblib.dump((clf, le), artifact)

model_bytes = os.path.getsize(artifact)
out = {"phase": "phase2-train",
       "pass": os.path.exists(artifact) and test_acc > 0.0 and model_bytes < 50_000_000,
       "n_samples": int(X.shape[0]), "n_features": int(X.shape[1]),
       "n_classes": int(len(le.classes_)),
       "train_accuracy": round(float(train_acc), 4), "test_accuracy": round(float(test_acc), 4),
       "model_bytes": model_bytes, "artifact": artifact}
print("FSD_RESULT_BEGIN"); print(json.dumps(out, indent=2, default=str)); print("FSD_RESULT_END")
with open(f"{os.environ['OUT40']}/phase2_result.json", "w") as f:
    json.dump(out, f, indent=2, default=str)
PY
.venv/bin/python "$OUT40/phase2_train.py"
```
- **Expect:** an `rf.joblib` under `$OUT40` (a few hundred KB at field level); a train/test accuracy
  printed. `n_samples` ≈ 900 (fields), `n_features == 16` (`T·Bf == 8·2`). (Absolute accuracy is your
  call — this run-book checks the artifact was produced, beats chance, and is **small**.)
- **PASS if:** `pass: true` — `rf.joblib` exists, `test_accuracy > 0`, **and `model_bytes < 50 MB`**
  (the size gate: a per-pixel unpruned RF trips this at ~1 GB; `median_per_id` keeps it tiny).
  **Inspect `test_accuracy` and `n_classes` yourself** — a very low score, or a class count that
  doesn't match your labels, means the features/labels are off (re-check Phase 1). If `model_bytes` is
  huge, you likely dropped `aggregate="median_per_id"` in Phase 1 — re-run it.
- **Accuracy is now HONEST (report it as such).** One row per field means the train/test split is
  inherently **field-wise** — no field appears in both. Per-pixel training with a random split leaks:
  pixels from the *same* field (near-identical spectra) land in both train and test, so the score
  measures memorization, not generalization (in this demo: an inflated **0.696** per-pixel vs a real
  **~0.29** field-wise). The field-wise number is the one for the demo report. A `train_accuracy` of
  ~1.0 with a much lower test score is an **overfit** tell (200 unpruned trees memorizing ~675 train
  fields, 16 features): to lift generalization — *not* size — add `min_samples_leaf` / `max_depth` or
  cut `n_estimators`. But ~29% honest 9-class crop accuracy from only NDVI+SAVI over 8 mosaics is a
  plausible feature ceiling; improving it (more bands/features) is a modelling exercise, permanently
  your side (ADR-0018). It does **not** block the pipeline demo — the bundle is valid either way.
- **Note:** `X.reshape(len, -1)` flattens `(T=8, Bf)` per row in **T-outer, band-inner** order, which
  is exactly what DemoRF uses at inference — it inherits `BaseModelAdapter.datacube_to_X`
  (`adapter.py:111`: `(T,H,W,B) -> (H*W, T*B)`, T slower / B faster). Same ordering both sides = the
  F1 anti-skew guarantee. (DemoRF does not override `datacube_to_X`, so no mirroring needed.)

## Phase 3 — bundle `adapters:DemoRF` + prove it round-trips

```bash
cat > "$OUT40/phase3_bundle.py" <<'PY'
import json, os, shutil
from fsd.model import bundle as fsd_bundle
from adapters import DemoRF

BUNDLE_DIR = os.path.join(os.environ["OUT40"], "demo_rf_bundle")
if os.path.isdir(BUNDLE_DIR):
    shutil.rmtree(BUNDLE_DIR)   # clean rebuild
artifact = os.path.join(os.environ["OUT40"], "rf.joblib")

# DemoRF pins n_timestamps=0 (model-determined) -> set T=8 on the instance so the bundle RECORDS 8.
# save() reads spec fields off the object; runbook 38's inference preflight reads them back via
# read_spec (api.py:1072). Without this the manifest would carry 0 and the T-check would be skipped.
adapter = DemoRF()
adapter.n_timestamps = 8
fsd_bundle.save(adapter, {"model": artifact}, BUNDLE_DIR)

# (a) model-free preflight: read bundle.json WITHOUT importing/loading the model.
spec = fsd_bundle.read_spec(BUNDLE_DIR)
# (b) full round-trip: resolve ref -> instantiate -> inject artifact path -> validate spec -> .load().
adapter = fsd_bundle.load(BUNDLE_DIR)

out = {"phase": "phase3-bundle", "bundle_dir": BUNDLE_DIR,
       "adapter_ref": spec["adapter"],
       "required_bands": spec["required_bands"], "n_timestamps": spec["n_timestamps"],
       "output_dtype": spec["output_dtype"], "output_nodata": spec["output_nodata"],
       "output_band_names": spec["output_band_names"],
       "artifacts": spec["artifacts"], "feature": spec["feature"],
       "roundtrip_loaded": adapter is not None}
out["pass"] = (
    spec["adapter"] == "adapters:DemoRF"
    and spec["required_bands"] == ["B04", "B08"]
    and spec["n_timestamps"] == 8
    and spec["output_dtype"] == "uint8" and spec["output_nodata"] == 255
    and "model" in spec["artifacts"]
    and out["roundtrip_loaded"]
)
print("FSD_RESULT_BEGIN"); print(json.dumps(out, indent=2, default=str)); print("FSD_RESULT_END")
with open(f"{os.environ['OUT40']}/phase3_result.json", "w") as f:
    json.dump(out, f, indent=2, default=str)
print(f"\nBUNDLE READY: {BUNDLE_DIR}")
print("→ point runbook 38's  export AZ_BUNDLE_LOCAL=<this path>  at it (Phase 0 stages it to blob).")
PY
.venv/bin/python "$OUT40/phase3_bundle.py"
```
- **Expect:** `$OUT40/demo_rf_bundle/` containing `bundle.json` + `rf.joblib`; the printed
  `BUNDLE READY: …` path.
- **PASS if:** `pass: true` — `bundle.json`'s `adapter` is **`adapters:DemoRF`**,
  `required_bands == [B04, B08]`, **`n_timestamps == 8`**, `output_dtype/nodata` are `uint8`/`255`,
  the `model` artifact href is recorded, **and** `fsd.model.bundle.load(BUNDLE_DIR)` round-trips
  (resolves `adapters:DemoRF`, injects the artifact path, spec-validates, calls `.load()`).
- **FAIL — `adapter` ref is not `adapters:DemoRF`:** DemoRF isn't importable from the `adapters`
  module by that name — the ref `save()` records is `f"{cls.__module__}:{cls.__qualname__}"`, and the
  inference image (`runbooks/38-*`) must `COPY` a module that resolves *this exact string*. Fix the
  module layout so `from adapters import DemoRF` works, re-bundle.
- **FAIL — `ValueError: bundle.json … disagrees with … (code/bundle drift)`:** `bundle.load`'s
  validate step found the DemoRF class's declared spec ≠ what was baked into `bundle.json` (e.g. you
  edited `n_timestamps` between save and load). Re-bundle from the current class.

## Hand-off to runbook 38
`$OUT40/demo_rf_bundle/` is the bundle `runbooks/38-inference-on-aml.md` **Phase 0** consumes:
```bash
export AZ_BUNDLE_LOCAL="$OUT40/demo_rf_bundle"   # carry into the runbook-38 shell
```
Runbook 38's image-build section must `COPY` your `adapters` module (so `adapters:DemoRF` resolves
on a node) and its window/bands (`2018-04-01..2018-09-01`, `mosaic_days=20`, `[B04,B08,B8A,SCL]`)
already give **T=8** ⊇ `required_bands=[B04,B08]` — consistent with this bundle.

## Success criteria (`_result.json`)
Each phase writes `$OUT40/phase<N>_result.json` (also printed between `FSD_RESULT_BEGIN`/`_END`).
The run passes when every phase's `pass` is true. **Paste these files back** (not the AML job logs).
```json
{ "phase": "phase3-bundle", "pass": true,
  "adapter_ref": "adapters:DemoRF", "required_bands": ["B04","B08"], "n_timestamps": 8 }
```

## Stop / observe
- **Phase 1 (aml):** `az ml job stream -n <job-name> -g "$AZ_RG" -w "$AZ_ML_WORKSPACE"` (job name is
  in `run_aml_flatten`'s returned status / the Studio URL printed at submission). Abort with Ctrl-C —
  an already-submitted job keeps running (`az ml job cancel -n <name> …` to stop spend). Re-running is
  self-healing: land-local skips landed arrays; the reduce overwrites its one blob array (D7);
  `_apply_training_features` overwrites `features.npy`. **Do not** `fs.rm(prefix, recursive=True)` to
  "clean up" — broken on `abfss://` (TODO #50).
- **Phases 2 & 3 are local** — no VPN, no cluster. Re-run freely; Phase 3 rebuilds the bundle dir
  cleanly each time (`shutil.rmtree` first).
