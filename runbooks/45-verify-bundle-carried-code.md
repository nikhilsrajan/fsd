---
status: current
summary: Verify spec 44 phase 1 — the bundle carries its adapter, so the inference image is generic; Phase 0 is offline in seconds, Phases 1-3 prove it on the cluster and delete the per-adapter image build.
---

# Run-book: 45 — verify bundle-carried adapter source (spec 44 phase 1)

> Spec-24 run-book for **spec 44 §4** (phase 1, signed off 2026-08-19). **You** run this; paste back
> each phase's `_result.json`. Claude diffs it against the success criteria below and never reads
> your logs.
>
> **What this is proving:** that an inference image no longer needs to contain the model's adapter.
> Before spec 44, shipping one `my_adapter.py` to the nodes meant a Dockerfile, a `.dockerignore`,
> two AML YAMLs, a `pip wheel`, an `az ml environment create` and a smoke job — **repeated every
> time the adapter changed**. After it, the adapter rides inside the bundle and the image differs
> only by *dependency family* (sklearn vs torch).
>
> **Concrete `rise` values are NOT in this file** (public repo). Paste them as env vars from the
> uncommitted `../../AZURE_INFRA_PRIVATE.md` (workspace root). Run the private-identifier sweep
> (`RECIPES.md`) before pushing anything derived from this run-book.

## Purpose

Four phases, cheapest first, so an expensive failure is never the first thing you learn:

| Phase | Proves | Cost |
|---|---|---|
| **0** | The whole phase-1 contract, **offline** — code embedded, layout preserved, loads with the source deleted, `__main__` refused, v1 bundles still load, missing deps named | **~10 s**, no cloud, no creds |
| **1** | A **generic** inference Environment (no adapter baked in) imports the adapter from the bundle | one image build + one ~40–380 s smoke job |
| **2** | A real ROI inference run works end to end on that generic image | one small fan-out |
| **3** | The **migration boundary**: a pre-spec-44 bundle fails on the generic image, and re-saving fixes it | ~1 min |

**Phase 0 is the gate for everything else.** If it fails, stop — Phases 1–3 cost money and cannot
succeed.

## Prerequisites

- **Phase 0 only:** the fsd venv, nothing else. No VPN, no `az login`, no imagery.
  ```bash
  cd fsd && source .venv/bin/activate && pip install -e ".[dev]"
  ```
- **Phases 1–3:** VPN connected, `az login` done, correct subscription selected. The spec-36
  cluster + identity already proven (`runbooks/36-aml-runner.md`), the Austria archive already on
  blob (`runbooks/37-download-on-aml.md`), and a bundle to run — either the demo bundle from
  `runbooks/40-train-and-bundle.md` Phase 3 or your own.
- ⚠️ **Re-save any bundle made before 2026-08-19.** See Phase 3 — this is the one migration step.

---

## Phase 0 — offline proof (no cloud)

```bash
cd fsd
.venv/bin/python runbooks/scripts/45_verify_bundle_code.py
```

- **Expect:** a printed `_result.json` ending `"pass": true` with `"checks_passed": "6/6"`.
- **PASS if:** `pass == true` **and** `metrics.fsd_bundle_version == 2` **and**
  `metrics.c_loads_with_source_deleted == true`.
- **The one that matters is `c`.** It builds a bundle, **deletes the adapter's source directory
  from disk**, and loads the bundle in a fresh subprocess. If that passes, the adapter reached the
  interpreter from inside the bundle and nowhere else — which is what a cluster node does.
- **Sanity-check `metrics.fsd_bundle_module`** points at the fsd you think you're testing. If it
  points somewhere unexpected, your venv's editable install is aimed at a different checkout and
  every later phase will mislead you.
- **If it fails:** paste `tests/outputs/spec44_verify/_result.json`. It is written even when the
  script raises, and it carries the failing check's own message. Do not proceed to Phase 1.

---

## Phase 1 — build a **generic** inference Environment and smoke it

This is the phase that deletes work. You are rebuilding the inference Environment from
`runbooks/38-inference-on-aml.md` → "Build the inference Environment", **with the adapter removed**.

### 1a — strip the adapter from the Dockerfile

In your `demo_model/Dockerfile` (or wherever you keep it), **delete these two lines**:

```dockerfile
COPY my_adapter.py /opt/adapter/          # DELETE — the bundle carries this now
ENV PYTHONPATH=/opt/adapter               # DELETE — bundle.load puts code/ on sys.path
```

Keep everything else: the base image, the fsd wheel, and the adapter's **runtime dependencies**
(`scikit-learn`, `joblib`, …). Dependencies still belong in the image — spec 44 moved the *code*,
not the deps.

> **Name the image for its dependency set, not for the model.** `fsd-infer-sklearn`, not
> `fsd-infer-croprf`. That naming is the whole point: one sklearn image serves every sklearn
> adapter you will ever write, and you rebuild it only when the dependency set changes.

### 1b — build and register it (operator step)

```bash
az ml environment create --file infer-environment.yml \
  --resource-group "$AZ_RG" --workspace-name "$AZ_ML_WORKSPACE"
```

Then read back the auto-assigned version, exactly as runbook 38 does:

```bash
export AZ_INFER_ENV_VERSION=$(az ml environment list --name "$AZ_INFER_ENV_NAME" \
  --resource-group "$AZ_RG" --workspace-name "$AZ_ML_WORKSPACE" \
  --query "max_by([].{v:version}, &v).v" -o tsv)
echo "$AZ_INFER_ENV_NAME:$AZ_INFER_ENV_VERSION"
```

- **PASS if:** the build succeeds and `AZ_INFER_ENV_VERSION` is **non-empty**.
- **Claude never runs `az ml`/`az acr`** (`CLAUDE.md`) — this is yours.

### 1c — re-save the bundle with this fsd, then smoke it

The bundle must be written by a post-spec-44 fsd, or it carries no `code/` block:

```bash
cd fsd
.venv/bin/python - <<'PY'
import json, os, sys
sys.path.insert(0, "./demo_model")          # wherever your adapter module lives
from my_adapter import CropRF               # your class
from fsd.model import bundle

adapter = CropRF()
adapter.n_timestamps = 10                   # whatever your model was trained on
bundle_dir = bundle.save(
    adapter,
    {"model": "path/to/rf.joblib"},
    "./demo_bundle",
    requirements=["scikit-learn>=1.5", "joblib"],   # DECLARED, never installed
)
m = bundle.read_spec(bundle_dir)
print(json.dumps({"adapter": m["adapter"], "version": m["fsd_bundle_version"],
                  "code": m.get("code"), "requirements": m.get("requirements")}, indent=2))
PY
```

- **Expect:** `"version": 2` and a `"code"` block naming your `.py`. If `code` is `null`, your
  adapter classified as *installed* (it is pip-installed) or the save refused — read the error.

Now stage it and run the **adapter-import smoke** against the generic image (runbook 38's Phase 0
step, unchanged except that the image no longer contains the adapter):

```bash
cd fsd
.venv/bin/python -m fsd.workflows.adapter_smoke "$AZ_ROOT/bundles/spec44/demo_bundle" \
  --status-url "$AZ_ROOT/runs/spec44-smoke/_status/0.json"
```

- **Expect:** `{"status": "ok", "error": null}`.
- **PASS if:** `status == "ok"`. **This is the headline result**: the adapter imported inside an
  image that has never heard of it.
- **If it fails with a named dependency** (e.g. `scikit-learn>=1.5: not installed`), that is D5
  working — add the dep to the image and rebuild. It is *not* a spec-44 failure.
- **If it fails with `ModuleNotFoundError: my_adapter`**, the bundle is stale (v1). Re-run 1c.

Record Phase 1 as:

```json
{ "step": "spec44-phase1-generic-image", "status": "ok", "pass": true,
  "metrics": { "env_version": "<AZ_INFER_ENV_VERSION>", "bundle_version": 2,
               "code_files": ["my_adapter.py"], "smoke_status": "ok" },
  "expected": { "bundle_version": 2, "smoke_status": "ok" },
  "error": null }
```

---

## Phase 2 — a real ROI inference run on the generic image

Use a **small, single-MGRS-tile ROI** (`shapefiles/s2grid=476da24.geojson`, 100% inside `T33UWP`) so
this is minutes, not an hour.

```bash
cd fsd
.venv/bin/python - <<'PY'
import fsd, os, json
result = fsd.run_inference(
    model="./demo_bundle",                       # the re-saved, v2 bundle
    roi=os.environ["ROI_PATH"],
    output_folderpath=os.environ["AZ_ROOT"] + "/runs/spec44-verify",      # a FRESH folder — it is the run id
    startdate=..., enddate=..., mosaic_days=20,  # must give the bundle's n_timestamps
    runner="aml", storage="abfss://...",
    runner_kwargs=dict(cluster=os.environ["AZ_CLUSTER"],
                       environment=f'{os.environ["AZ_INFER_ENV_NAME"]}:{os.environ["AZ_INFER_ENV_VERSION"]}',
                       identity_client_id=os.environ["AZ_UAMI_CLIENT_ID"]),
)
print(json.dumps({"n_outputs": len(result.output_filepaths)}, indent=2))
PY
```

- **Expect:** one `output.tif` per grid cell, plus a STAC catalog.
- **PASS if:** every cell produced an `output.tif` and no job failed with an import error.
- ⚠️ **Use a fresh `output_folderpath`** — it is the run id, and a stale `input.csv` in an existing
  folder silently ignores a changed ROI (issue #66).
- **If it hangs with no output for a long stretch:** that is issue #65 (silent dispatch/poll/merge),
  not a spec-44 failure. Check `_status/*.json` on blob.
- **Open the merged COG in QGIS.** Visual validation is the standard here — a run that "succeeded"
  and produced a nonsense map is a failure.

---

## Phase 3 — the migration boundary (do not skip)

**A bundle saved before 2026-08-19 will NOT run on the generic image.** It has no `code/` block, so
`bundle.load` resolves the adapter ref from the environment — and the environment no longer contains
it. This is correct, expected, and the only migration step.

```bash
cd fsd
.venv/bin/python - <<'PY'
from fsd.model import bundle
m = bundle.read_spec("path/to/an/old/bundle")
print("version:", m.get("fsd_bundle_version"), "| code:", m.get("code"))
PY
```

- **`version: 1` or `code: None`** → re-save it with Phase 1c. That is the whole migration.
- **Old bundles still work on the OLD image**, unchanged — nothing you already built has broken.
  `bundle.load` accepts versions 1 and 2.
- **PASS if:** you have identified every bundle you intend to keep running, and each is either
  re-saved or knowingly pinned to an adapter-carrying image.

---

## Success criteria (`_result.json`)

Phase 0 writes `tests/outputs/spec44_verify/_result.json` itself. Phases 1–3 you fill in by hand
from the shapes above. The run passes when every phase's `pass` is true.

**Paste the result files back, not the logs.**

The single sentence that means this worked: **you rebuilt the inference image without the adapter in
it, and the model still ran.**

## Stop / observe

- **Phase 0** is offline and takes seconds; Ctrl-C is harmless.
- **Phase 1b** is an `az ml` image build — watch it in the AML studio Environments tab.
- **Phase 2**: progress is `_status/<k>.json` files appearing under `$AZ_ROOT/runs/spec44-verify/runs/<run_id>/_status/`.
  Abort by cancelling the jobs in AML studio; re-running with the **same** `output_folderpath`
  resumes (cells with an existing `output.tif` are skipped).
- Nothing here writes outside `tests/outputs/` locally and under `$AZ_ROOT` on blob.
