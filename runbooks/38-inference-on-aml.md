# Run-book: 38 Phases 0–3 — inference at scale on Azure ML

> Spec-24 run-book for **spec 38 §6** (P4). **You** run this; paste back each phase's printed
> `_result.json`. Builds on spec 36's cluster/identity (already proven, `runbooks/36-aml-runner.md`)
> and spec 37's blob-inputs pattern — this run-book adds the **inference Environment** (D4), the
> **adapter-import smoke** (D11), and the **inference dispatch** (D1/D1a/D2). It does NOT rebuild
> the cluster or the spec-36 datacube Environment; it builds a **second**, model-specific one.
>
> **▶ Picking up from `runbooks/40-train-and-bundle.md`:** this is the **last** leg of the demo
> pipeline (see `runbooks/README.md`). Runbook 40 left you a trained + bundled `adapters:DemoRF` at
> `tests/outputs/p40_train_and_bundle/demo_rf_bundle/`. You point this run-book at it via
> **`AZ_BUNDLE_LOCAL`** (exported in the Setup block below) and it stages that bundle to blob +
> dispatches inference. The archive imagery must already be on blob (runbook 37). If you're arriving
> straight from runbook 40, you already have the venv + `demos/adapters.py` on `PYTHONPATH` — the one
> new thing here is the **inference Environment** (below), which bakes that adapter into the image.
>
> **Concrete `rise` values are NOT in this file** (public repo). Paste them as env vars from the
> uncommitted `../../AZURE_INFRA_PRIVATE.md` (workspace root). Run the private-identifier sweep
> (`RECIPES.md`) before pushing anything derived from this run-book.

## Purpose

Prove `run_inference(roi=…, runner="aml")` end to end: the inference Environment builds and the
adapter actually imports inside it (Phase 0); a small single-MGRS-tile ROI tiles into its grid cells
and every cell's `output.tif` lands on blob, one of them byte-identical to a local
`run_inference(roi=…)` of the matching cell (Phase 1); resume + the D13 duplicate guard both work
(Phase 2); and a real multi-cell ROI fans out across N nodes with bundle-loads == n_nodes, not
n_cells (Phase 3 — the D7 claim, the deliverable that demonstrates Mode C end to end).

## Prerequisites
- VPN connected, `az login` done, correct subscription selected — the driver does blob I/O in every
  phase (bundle staging, reading `_status/*.json`).
- The fsd venv with `[aml,azure,mpc,grid]` (grid tiles the ROI) **plus the adapter's own runtime
  deps** (sklearn + joblib for DemoRF) if you want to exercise the driver-side
  `_ensure_bundle`/local-baseline comparison locally:
  `cd fsd && source .venv/bin/activate && pip install -e ".[dev,azure,aml,mpc,grid]" scikit-learn joblib`
  and `export PYTHONPATH="$PWD/demos:$PYTHONPATH"` (so `adapters:DemoRF` resolves — **same as
  runbook 40**; if you came straight from it this is already set).
- **The spec-36 datacube Environment already built** (`runbooks/36-aml-runner.md`) — untouched by
  this run-book, just a precondition for the cluster being usable at all.
- **The demo bundle from `runbooks/40-train-and-bundle.md` Phase 3** — `tests/outputs/p40_train_and_bundle/demo_rf_bundle`
  (adapter ref **`adapters:DemoRF`**, `n_timestamps=8`). **If runbook 40 is green, this exists and
  you're done here** — the Setup block exports it as `AZ_BUNDLE_LOCAL`. Its adapter is
  `demos/adapters.py` (in the repo, but **not in the fsd wheel**), so the inference image below must
  `COPY` that module (D4) — that is what the "Build the inference Environment" section does. Any other
  bundle (`fsd.model.bundle.save(adapter, artifacts, dst)`) works too, as long as the image resolves
  its `bundle.json` `adapter` ref.
- The Austria archive catalog already on blob (`runbooks/37-download-on-aml.md` Phase 3 /
  `runbooks/37-verify-archive.md`) — inference never calls CDSE/MPC (SO-6), so imagery must already
  be there.
- Test ROIs: `s2grid=476da24` (single-tile, verified 100% inside T33UWP — Phase 1/2) and
  **`AT_2018_TRAIN.geojson`** (900 labelled fields, verified 100% inside `AT_ROI` = inside the
  archive footprint — Phase 3). **Do NOT use `austria_eurocrops_sampled_ethiopia_translated.geojson`
  for Phase 3** — it is the Austria fields *translated to Ethiopia* (36°E), so it has **zero overlap
  with the Austria archive** and every cell would build an empty cube (the exact mistake that wasted
  a run in `runbooks/36-aml-runner.md` Phase 3 — see the box there).

## Setup — paste your concrete values (from `AZURE_INFRA_PRIVATE.md`, uncommitted)
```bash
cd fsd
export AZ_RG='<resource group>'
export AZ_ML_WORKSPACE='<aml workspace>'
export AZ_SUBSCRIPTION_ID='<subscription id>'
export AZ_CLUSTER='<the d16 cluster name>'
export AZ_UAMI_NAME='<compute identity name>'
export AZ_UAMI_CLIENT_ID="$(az identity show -g "$AZ_RG" -n "$AZ_UAMI_NAME" --query clientId -o tsv)"
export AZ_ACCOUNT='<storage account>'
export AZ_FS='<filesystem/container>'
export AZ_ROOT="abfss://${AZ_FS}@${AZ_ACCOUNT}.dfs.core.windows.net/nsasiraj/fsd-p4-inference"
# ⚠️ The VERIFIED archive catalog is under the download root's `archive/` prefix (runbook 37 Phase 3
# / runbook 36's `AZ_ARCHIVE_CATALOG`) — NOT `mpc/` (runbook 34's pre-fix-radiometry output). Point
# at exactly what runbook 36 used, or you build cubes against the wrong bytes.
export AZ_CATALOG_URL="abfss://${AZ_FS}@${AZ_ACCOUNT}.dfs.core.windows.net/nsasiraj/fsd-p2/archive/catalog.parquet"

# D4: a SECOND, inference-specific Environment (spec-36's Dockerfile + the adapter package
# + its deps). Operator run-book step -- Claude never runs `az ml`/`az acr` (CLAUDE.md).
export AZ_INFER_ENV_NAME='fsd-infer-env'
# ⚠️ FIRST RUN: this Environment does NOT exist yet -- go BUILD it via the "Build the inference
#    Environment (D4)" section below (that `az ml environment create` step is what sets
#    AZ_INFER_ENV_VERSION), THEN come back here. The line below only READS BACK the version of an
#    ALREADY-built env (for later runs). On a first run `az ml environment list -n <missing>` errors
#    with a cryptic `System.Net.Http...HttpConnectionResponseContent` -- that just means "not built
#    yet". `2>/dev/null` swallows it; the guard below tells you what to do.
export AZ_INFER_ENV_VERSION="$(az ml environment list -n "$AZ_INFER_ENV_NAME" -g "$AZ_RG" \
  -w "$AZ_ML_WORKSPACE" --query "[].version" -o tsv 2>/dev/null | sort -V | tail -1)"
if [ -z "$AZ_INFER_ENV_VERSION" ]; then
  echo "AZ_INFER_ENV_VERSION is EMPTY -> the inference Environment isn't built yet. Run the"
  echo "'Build the inference Environment (D4)' section below FIRST (it sets this var), then continue."
else
  echo "inference environment: ${AZ_INFER_ENV_NAME}:${AZ_INFER_ENV_VERSION}"
fi

export AZ_N_SHARDS='16'    # Phase 3 fan-out width (>= the cluster's max_instances is fine, D1 degrades)

# ▶ The bundle runbook 40 Phase 3 produced -- the thing every phase here stages + runs. If you used a
#   different OUT40 in runbook 40, point this at that bundle dir instead.
export AZ_BUNDLE_LOCAL="$PWD/tests/outputs/p40_train_and_bundle/demo_rf_bundle"

# OUT38 is THIS run-book's OWN scratch (Docker build context, env ymls, phase scripts + results).
# It is DISTINCT from runbook 40's OUT40 on purpose: running the two run-books back-to-back in one
# shell can't cross-write, because neither reuses a bare `OUT`. The only thing that crosses over from
# runbook 40 is AZ_BUNDLE_LOCAL (above), the bundle path.
export OUT38="$PWD/tests/outputs/p4_inference_aml"   # gitignored
mkdir -p "$OUT38"

# Fail cheap on the driver BEFORE any cluster spend (the runbook-36 lesson: a wrong catalog prefix,
# a non-intersecting ROI, or a missing bundle is a wasted run). Requires VPN + az login.
.venv/bin/python - <<'PY'
import os
from fsd.storage import fs
cat = os.environ["AZ_CATALOG_URL"]
assert fs.exists(cat), f"archive catalog NOT found: {cat} (wrong prefix? VPN off? see the warning above)"
for roi in ("../shapefiles/s2grid=476da24.geojson", "../shapefiles/AT_2018_TRAIN.geojson"):
    assert os.path.exists(roi), f"ROI missing: {roi} (cwd must be fsd/)"
# The bundle from runbook 40 must exist + parse, and its adapter ref must import in THIS venv
# (the same check the inference image must pass on a node -- catch a bad AZ_BUNDLE_LOCAL now).
bundle = os.environ["AZ_BUNDLE_LOCAL"]
assert os.path.isdir(bundle), f"AZ_BUNDLE_LOCAL is not a dir: {bundle} (did runbook 40 Phase 3 run? right OUT40?)"
from fsd.model.bundle import read_spec, resolve_ref
spec = read_spec(bundle)
assert spec["adapter"] == "adapters:DemoRF", f"bundle adapter ref is {spec['adapter']!r} (expected adapters:DemoRF)"
assert spec["n_timestamps"] == 8, f"bundle n_timestamps={spec['n_timestamps']} (expected 8 -- runbook 40 Phase 3 sets it)"
resolve_ref(spec["adapter"])   # imports demos/adapters.py -> DemoRF; fails here if demos/ not on PYTHONPATH
print("preflight OK:", cat, "reachable; ROIs present; bundle", spec["adapter"], "T=", spec["n_timestamps"])
PY
```

## Build the inference Environment (D4) — once, or whenever the fsd wheel / adapter changes

> **Do this BEFORE the Setup block's `AZ_INFER_ENV_VERSION=$(az ml environment list …)` line and
> before Phase 0.** That line only *reads back* the auto-assigned version — it assumes the
> environment already exists. If you run it first, `AZ_INFER_ENV_VERSION` comes back **empty** and
> every phase's `environment="…:$AZ_INFER_ENV_VERSION"` breaks.
>
> This is the **second**, model-specific Environment (D4). It is spec-36's datacube image
> (`runbooks/36-aml-runner.md` "Build the AML Environment") **plus** the adapter's runtime deps
> (here `scikit-learn` + `joblib`) **plus** the adapter module itself, made importable. Operator
> step — **Claude never runs `az ml`/`az acr`** (`CLAUDE.md`).
>
> ⚠️ **The coupling that decides whether this works:** a bundle stores its adapter as a
> `module:attribute` import string in `bundle.json`, resolved on the node via
> `importlib.import_module(module_path)` (`fsd.model.bundle.resolve_ref`). The image must import
> **exactly that module string.** Check yours: `cat "$AZ_BUNDLE_LOCAL/bundle.json"` → the `adapter`
> field. For the demo that is **`"adapter": "adapters:DemoRF"`** (the locked demo model — `demos/
> adapters.py`, trained at T=8, built + bundled by `runbooks/40-train-and-bundle.md`; it is in the
> repo but **not in the fsd wheel**, so the image must `COPY` it in). The recipe below makes the
> `adapters` module importable as `adapters` so it matches that ref. If your ref differs, change the
> `COPY`/`PYTHONPATH`
> (or `pip install` your real adapter package) so the module resolves — a mismatch is the exact
> `ModuleNotFoundError` Phase 0 exists to catch.

```bash
# (Requires the Setup block's AZ_* vars already exported: AZ_RG, AZ_ML_WORKSPACE, OUT38, …)
export AZ_INFER_ENV_NAME='fsd-infer-env'

# 1. Build context = fsd wheel + the `adapters` module + a Dockerfile, in one directory.
#    The demo adapter (`adapters:DemoRF`) lives at demos/adapters.py -- in the repo, but NOT in the
#    fsd wheel (the wheel packages only src/fsd/), so the image must COPY it in. AZ_ADAPTERS_SRC
#    defaults to it; point it elsewhere for your own adapter (must import as the bundle.json ref's module).
export AZ_ADAPTERS_SRC="${AZ_ADAPTERS_SRC:-demos/adapters.py}"
rm -rf "$OUT38/infer_env_src" && mkdir -p "$OUT38/infer_env_src/adapter_src"
.venv/bin/pip wheel . --no-deps -w "$OUT38/infer_env_src" && ls "$OUT38"/infer_env_src/fsd-*.whl
cp -r "$AZ_ADAPTERS_SRC" "$OUT38/infer_env_src/adapter_src/"   # -> adapter_src/adapters.py == module `adapters`

cat > "$OUT38/infer_env_src/Dockerfile" <<'DOCKER'
# The same base image spec 36 proved works on this cluster.
FROM mcr.microsoft.com/azureml/openmpi4.1.0-ubuntu22.04:latest
COPY fsd-*.whl /tmp/
COPY adapter_src/ /opt/adapter/
# [azure] -> adlfs + azure-identity + azure-keyvault-secrets (blob I/O, D3 identity, bundle staging)
# [mpc]   -> planetary-computer. s3fs/pystac-client are core deps. NOT [aml] (driver-side only).
# PLUS the adapter's runtime deps (scikit-learn, joblib) -- the two lines D4 adds over spec 36.
RUN python -m pip install --no-cache-dir "$(ls /tmp/fsd-*.whl)[azure,mpc]" scikit-learn joblib \
 && python -m pip cache purge || true
# Make the adapter importable as `adapters` -- the SAME name bundle.json's `adapter` ref uses
# (`adapters:DemoRF`). If your ref differs, change this to match, or `pip install` your package.
ENV PYTHONPATH=/opt/adapter
DOCKER

cat > "$OUT38/infer-environment.yml" <<YML
\$schema: https://azuremlschemas.azureedge.net/latest/environment.schema.json
name: ${AZ_INFER_ENV_NAME}
build:
  path: ./infer_env_src
  dockerfile_path: Dockerfile
YML

# version is omitted on purpose -> AML auto-increments it. Capture what it assigned:
export AZ_INFER_ENV_VERSION="$(az ml environment create -f "$OUT38/infer-environment.yml" \
  -g "$AZ_RG" -w "$AZ_ML_WORKSPACE" --query version -o tsv)"
echo "built ${AZ_INFER_ENV_NAME}:${AZ_INFER_ENV_VERSION}"
```
- **Expect:** the image build runs (several minutes the first time), then `built fsd-infer-env:<N>`.
- ⚠️ **Export `AZ_INFER_ENV_VERSION` in every later shell** (the phase scripts reference
  `${AZ_INFER_ENV_NAME}:${AZ_INFER_ENV_VERSION}`). To recover it: the Setup block's
  `az ml environment list … --query "[].version" -o tsv | sort -V | tail -1` line.
- **PASS if:** the following prints the name and version back (`--version` is **required** —
  `az ml environment show` without it fails with `Must provide either version or label`):
  ```bash
  az ml environment show -n "$AZ_INFER_ENV_NAME" --version "$AZ_INFER_ENV_VERSION" \
    -g "$AZ_RG" -w "$AZ_ML_WORKSPACE" --query "[name, version]" -o tsv
  ```

### Verify the image imports fsd AND the adapter (cheap check before Phase 0)
A registered environment can exist and still be unusable (wrong `python` on `PATH`, missing dep,
`PYTHONPATH` that doesn't resolve the adapter). One cheap job settles it **without** needing a
staged bundle — do it before Phase 0 (which additionally needs `AZ_BUNDLE_LOCAL`):
```bash
cat > "$OUT38/infer_env_smoke.yml" <<YML
\$schema: https://azuremlschemas.azureedge.net/latest/commandJob.schema.json
display_name: fsd-infer-env-smoke
experiment_name: fsd-infer-phase0
command: >-
  python -c "import fsd, s3fs, adlfs, planetary_computer, pystac_client, sklearn, joblib;
  from fsd.model.bundle import resolve_ref;
  print('FSD_INFER_ENV_OK', fsd.__version__, resolve_ref('adapters:DemoRF').__name__)"
environment: azureml:${AZ_INFER_ENV_NAME}:${AZ_INFER_ENV_VERSION}
compute: azureml:${AZ_CLUSTER}
YML
az ml job create -f "$OUT38/infer_env_smoke.yml" -g "$AZ_RG" -w "$AZ_ML_WORKSPACE" --query name -o tsv
# then stream it with the returned job name:
#   az ml job stream -n <job-name> -g "$AZ_RG" -w "$AZ_ML_WORKSPACE"
```
- **PASS if:** the log prints `FSD_INFER_ENV_OK 0.1.0 DemoRF` and the job finishes `Completed`.
- **FAIL — `ModuleNotFoundError: No module named 'fsd'`:** the image's default `python` isn't the
  one pip installed into (pin an explicit interpreter in the Dockerfile, rebuild, re-smoke).
- **FAIL — `ModuleNotFoundError: No module named 'adapters'`** (or your adapter's module): the
  `PYTHONPATH`/module name in the image doesn't match your `bundle.json`'s `adapter` ref
  (`adapters:DemoRF`) — fix the `COPY`/`ENV PYTHONPATH` (or `pip install` the real package), rebuild,
  re-smoke. **Do not** proceed to Phase 0 — it would hit the same import after paying to stage a
  bundle.
- **FAIL — a *different* module missing** (`sklearn`, `adlfs`, …): add it to the Dockerfile's install
  line and rebuild.

- **Re-run this whole step whenever the fsd wheel OR the adapter changes** — the image bakes both.

## Phase 0 — the inference Environment + adapter-import smoke
```bash
cat > "$OUT38/phase0.py" <<'PY'
import json, os
from fsd.model import bundle as fsd_bundle
from fsd.workflows import runners

# 1. Save (or point at) a bundle, then stage it to blob exactly the way
#    run_aml_inference will -- proves D3 (manifest-driven fetch) before Phase 1.
BUNDLE_LOCAL = os.environ.get("AZ_BUNDLE_LOCAL")  # e.g. a locally-trained bundle folder
assert BUNDLE_LOCAL, "export AZ_BUNDLE_LOCAL=<local bundle path> first"
staged = runners._stage_bundle(BUNDLE_LOCAL, f"{os.environ['AZ_ROOT']}/_phase0_bundle")

from azure.ai.ml import MLClient
from azure.identity import DefaultAzureCredential
ml_client = MLClient(DefaultAzureCredential(), os.environ["AZ_SUBSCRIPTION_ID"],
                     os.environ["AZ_RG"], os.environ["AZ_ML_WORKSPACE"])

aml_command = runners._import_aml_command()
status_url = f"{os.environ['AZ_ROOT']}/_status/phase0_smoke.json"
job = aml_command(
    command=f"python -m fsd.workflows.adapter_smoke {staged} --status-url {status_url}",
    environment=f"{os.environ['AZ_INFER_ENV_NAME']}:{os.environ['AZ_INFER_ENV_VERSION']}",
    compute=os.environ["AZ_CLUSTER"],
    environment_variables={"AZURE_CLIENT_ID": os.environ["AZ_UAMI_CLIENT_ID"]},
    display_name="fsd-infer-smoke-phase0", experiment_name="fsd-infer-phase0",
)
runners._aml_submit_and_wait(ml_client, {"smoke": job}, os.environ["AZ_ROOT"], "phase0-smoke")

from fsd.storage import fs
with fs.open(status_url, "r") as f:
    smoke_status = json.load(f)

out = {"phase": "phase0-environment-smoke", "pass": smoke_status["status"] == "ok",
      "staged_bundle_url": staged, "smoke_status": smoke_status}
print("FSD_RESULT_BEGIN"); print(json.dumps(out, indent=2)); print("FSD_RESULT_END")
with open(f"{os.environ['OUT38']}/phase0_result.json", "w") as f:
    json.dump(out, f, indent=2)
PY
.venv/bin/python "$OUT38/phase0.py"
```
- **Expect:** one AML job scales a node 0→1, `smoke_status.status == "ok"`, `smoke_status.error is
  null`.
- **PASS if:** the above. This proves D4 (the adapter + its deps are actually importable inside the
  built Environment) and D3 (bundle staging + `fs.get`-to-scratch) **before any cube is built.**
- **FAIL — `ModuleNotFoundError` in `smoke_status.error`:** the inference Environment is missing a
  dependency (or the adapter package itself) — rebuild it per the Setup block's `az ml environment
  create` note, then re-run this phase.

## Phase 1 — a small single-MGRS-tile ROI → its grid cells, to blob

> ⚠️ **"single-tile" here = single MGRS *tile*, NOT single grid *cell*** (CLAUDE.md's terminology
> rule). `s2grid=476da24` is a **~4.6 km ROI whose imagery all comes from one MGRS tile (T33UWP,
> one CRS)** — chosen so the datacube *build* needs no cross-CRS merge. But `run_inference(roi=…)`
> **always tiles** the ROI into ~5 km S2 grid cells (`grid_size_km=5`, `scale_fact=1.1`), and this
> grid-unaligned ROI spills into a ~3×3 neighborhood → **9 grid cells**, each = one datacube = one
> `output.tif`. So this phase produces **~9 per-cell COGs**, not one — a *good* thing: it exercises
> the multi-cell fan-out-to-blob at tiny scale before Phase 3's 900. (One literal cell would need a
> grid-*aligned* single-cell geometry; not worth it for a smoke.)

```bash
cat > "$OUT38/phase1.py" <<'PY'
import io, json, os
import fsd
import geopandas as gpd
from fsd.storage import fs

# NOTE: run_id / n_shards / skip_smoke etc. are `run_aml_inference` args, so they go INSIDE
# runner_kwargs — `fsd.run_inference` itself has no such params (passing them to it is a TypeError).
common_kwargs = dict(
    cluster=os.environ["AZ_CLUSTER"],
    environment=f"{os.environ['AZ_INFER_ENV_NAME']}:{os.environ['AZ_INFER_ENV_VERSION']}",
    root=os.environ["AZ_ROOT"], identity_client_id=os.environ["AZ_UAMI_CLIENT_ID"],
    subscription_id=os.environ["AZ_SUBSCRIPTION_ID"], resource_group_name=os.environ["AZ_RG"],
    workspace_name=os.environ["AZ_ML_WORKSPACE"], run_id="phase1-roi",
)

bundle_path = os.environ["AZ_BUNDLE_LOCAL"]

result = fsd.run_inference(
    bundle_path, roi="../shapefiles/s2grid=476da24.geojson",
    output_folderpath=f"{os.environ['AZ_ROOT']}/phase1_out",
    catalog_filepath=os.environ["AZ_CATALOG_URL"],
    startdate="2018-04-01", enddate="2018-09-01", mosaic_days=20,
    bands=["B04", "B08", "B8A", "SCL"],
    runner="aml", runner_kwargs=common_kwargs, storage="azure",
)

# how many cells did the ROI tile into? (grids.geojson is written by run_inference via the seam)
with fs.open(result.grids_filepath, "rb") as f:
    n_cells = len(gpd.read_file(io.BytesIO(f.read())))

out = {"phase": "phase1-roi-cells-to-blob",
      # every tiled cell must have produced an output.tif (collect drops any that didn't exist)
      "pass": bool(result.output_filepaths) and len(result.output_filepaths) == n_cells,
      "n_grid_cells": n_cells, "n_outputs": len(result.output_filepaths),
      "output_filepaths": result.output_filepaths,
      "stac_catalog_filepath": result.stac_catalog_filepath}
print("FSD_RESULT_BEGIN"); print(json.dumps(out, indent=2, default=str)); print("FSD_RESULT_END")
with open(f"{os.environ['OUT38']}/phase1_result.json", "w") as f:
    json.dump(out, f, indent=2, default=str)
PY
.venv/bin/python "$OUT38/phase1.py"
```
- **Expect:** the smoke job (D11, on by default) then one shard job, both scale a node 0→1; **one
  `output.tif` per tiled grid cell** under `phase1_out/cells/<window>/<cell-id>/output.tif` on blob
  (≈ 9 for this ROI — the exact count = `roi_to_s2_grids`'s output, printed as `n_grid_cells`).
- **PASS if:** `n_outputs == n_grid_cells` (every tiled cell produced a COG — none silently dropped)
  and each exists on blob (`fs.exists`), with correct nodata/CRS/transform (`gdalinfo <vsiadls-path>`
  on one). For the AML-vs-local proof (mirrors spec 36 Phase 3b), run the SAME call with
  `runner="local"` and compare **one matching cell by id** (`.../cells/<window>/<cell-id>/output.tif`)
  — should be byte-identical. You need only one cell for that check, not all nine.
- **If it fails:** paste `$OUT38/phase1_result.json`; `n_outputs < n_grid_cells` means some cells
  failed (read their `_status`/`az ml job stream`); a `ModuleNotFoundError` despite Phase 0 passing
  means the Environment changed between phases — rebuild + re-smoke.

## Phase 2 — resume + the D13 duplicate guard
```bash
cat > "$OUT38/phase2.py" <<'PY'
import json, os
import fsd

common_kwargs = dict(
    cluster=os.environ["AZ_CLUSTER"],
    environment=f"{os.environ['AZ_INFER_ENV_NAME']}:{os.environ['AZ_INFER_ENV_VERSION']}",
    root=os.environ["AZ_ROOT"], identity_client_id=os.environ["AZ_UAMI_CLIENT_ID"],
    subscription_id=os.environ["AZ_SUBSCRIPTION_ID"], resource_group_name=os.environ["AZ_RG"],
    workspace_name=os.environ["AZ_ML_WORKSPACE"], skip_smoke=True,   # Environment already proven
    run_id="phase2-resume",   # a run_aml_inference arg -> lives in runner_kwargs, not on run_inference
)

# Re-run Phase 1 verbatim -- every cell should skip via the D6 output.tif-exists check.
# NOTE: same output_folderpath as Phase 1 so setup() finds the existing input.csv and each
# cell's output.tif already on blob; the new run_id only renames this run's staging area.
result = fsd.run_inference(
    os.environ["AZ_BUNDLE_LOCAL"], roi="../shapefiles/s2grid=476da24.geojson",
    output_folderpath=f"{os.environ['AZ_ROOT']}/phase1_out",
    catalog_filepath=os.environ["AZ_CATALOG_URL"],
    startdate="2018-04-01", enddate="2018-09-01", mosaic_days=20,
    bands=["B04", "B08", "B8A", "SCL"],
    runner="aml", runner_kwargs=common_kwargs, storage="azure",
)

# The D13 guard: hand-assemble a duplicated input.csv and confirm dispatch REFUSES it.
from fsd.storage import fs
from fsd.workflows import runners
import pandas as pd
csv_url = f"{os.environ['AZ_ROOT']}/phase2_dup/input.csv"
row = {"id": "dupcell", "shapefilepath": "x", "catalog_filepath": "y",
      "startdate": "2018-04-01", "enddate": "2018-09-01",
      "export_folderpath": f"{os.environ['AZ_ROOT']}/phase2_dup/dupcell",
      "mosaic_days": 20, "mosaic_scheme": "calendar", "scl_mask_classes": "0,1,3,7,8,9,10",
      "bands": "B04,B08,B8A,SCL"}
row2 = dict(row, startdate="2018-05-01")   # SAME export_folderpath, DIFFERENT content
with fs.open(csv_url, "w") as f:
    pd.DataFrame([row, row2]).to_csv(f, index=False)
guard_raised = False
try:
    runners.run_aml_inference(csv_url, os.environ["AZ_BUNDLE_LOCAL"], **common_kwargs)
except ValueError as exc:
    guard_raised = "duplicate unit dispatch" in str(exc)

out = {"phase": "phase2-resume-and-guard", "pass": bool(result.output_filepaths) and guard_raised,
      "resume_output_filepaths": result.output_filepaths, "d13_guard_raised": guard_raised}
print("FSD_RESULT_BEGIN"); print(json.dumps(out, indent=2, default=str)); print("FSD_RESULT_END")
with open(f"{os.environ['OUT38']}/phase2_result.json", "w") as f:
    json.dump(out, f, indent=2, default=str)
PY
.venv/bin/python "$OUT38/phase2.py"
```
- **Expect:** the resume run reports the same `n_units`/`n_skipped == n_units` shape as
  `runbooks/36-aml-runner.md` Phase 2 (D6/D7 now for inference); `d13_guard_raised: true`.
- **PASS if:** both. **FAIL — `d13_guard_raised: false`:** the guard regressed; do not proceed to
  Phase 3 (a partially-failed Phase 3 re-run is exactly when this bites for real).

## Phase 3 — the real fan-out
> ⚠️ **ROI (the runbook-36 lesson):** use **`AT_2018_TRAIN.geojson`** — 900 labelled fields verified
> 100% inside `AT_ROI` = inside the archive footprint. Do **NOT** use
> `austria_eurocrops_sampled_ethiopia_translated.geojson` (Austria fields *translated to Ethiopia*,
> 36°E) — it has **zero overlap** with the Austria archive, so all 900 cells would build empty cubes
> and the whole run is wasted. This is the exact mistake `runbooks/36-aml-runner.md` Phase 3 hit.
```bash
cat > "$OUT38/phase3.py" <<'PY'
import json, os, time
import fsd
from fsd.storage import fs

RUN_ID = "phase3-fanout"
N_SHARDS = int(os.environ["AZ_N_SHARDS"])
common_kwargs = dict(
    cluster=os.environ["AZ_CLUSTER"],
    environment=f"{os.environ['AZ_INFER_ENV_NAME']}:{os.environ['AZ_INFER_ENV_VERSION']}",
    root=os.environ["AZ_ROOT"], identity_client_id=os.environ["AZ_UAMI_CLIENT_ID"],
    subscription_id=os.environ["AZ_SUBSCRIPTION_ID"], resource_group_name=os.environ["AZ_RG"],
    workspace_name=os.environ["AZ_ML_WORKSPACE"], skip_smoke=True,
    n_shards=N_SHARDS, run_id=RUN_ID,
)

# setup() tiles the ROI + writes each cell's slice on the DRIVER before any job submits -- for
# ~900 cells that is ~1-2 min of blob writes with a throttled progress+ETA line. It is NOT a
# hang: the tell that you are still in setup (not dispatch) is that the azure-ai-ml
# "experimental class" warnings have not printed yet (azure.ai.ml is imported lazily at dispatch).
t0 = time.time()
result = fsd.run_inference(
    os.environ["AZ_BUNDLE_LOCAL"],
    roi="../shapefiles/AT_2018_TRAIN.geojson",   # inside the archive; see the box above
    output_folderpath=f"{os.environ['AZ_ROOT']}/phase3_out",
    catalog_filepath=os.environ["AZ_CATALOG_URL"],
    startdate="2018-04-01", enddate="2018-09-01", mosaic_days=20,
    bands=["B04", "B08", "B8A", "SCL"],
    runner="aml", runner_kwargs=common_kwargs, storage="azure",
    cores=1,      # D7 load-once-per-node: one whole-shard group per node -> bundle-loads == n_nodes
                  # (the clean demo number; RF load is sub-second). Drop it for the load-per-core
                  # default (bundle-loads == n_nodes * node_cores), then compare against sum(n_groups).
    merge=False,
)
wall_seconds = time.time() - t0

# run_inference returns the InferenceResult, NOT the runner's per-shard report -- so read the
# _status/<k>.json files the dispatch aggregated (spec-24 shape) to get timing + the D7 bundle-load
# count. (This is the telemetry runbook 36 Phase 3 could not record; now machine-checkable.)
run_root = f"{os.environ['AZ_ROOT'].rstrip('/')}/runs/{RUN_ID}"
shards = []
for k in range(N_SHARDS):
    su = f"{run_root}/_status/{k}.json"
    if fs.exists(su):
        with fs.open(su, "r") as f:
            shards.append(json.load(f))
n_failed = sum(s["n_failed"] for s in shards)
slowest = max((s["seconds"] for s in shards), default=0.0)

out = {"phase": "phase3-real-fanout",
      "pass": bool(result.output_filepaths) and len(shards) > 0 and n_failed == 0,
      "wall_seconds": round(wall_seconds, 1),
      "slowest_shard_seconds": round(slowest, 1),
      "driver_overhead_seconds": round(wall_seconds - slowest, 1),   # setup+alloc+queue (TODO #48/#55)
      "n_shards_reported": len(shards),
      "sum_shard_units": sum(s["n_units"] for s in shards),
      "n_cells_out": len(result.output_filepaths),
      "n_failed": n_failed, "n_skipped": sum(s["n_skipped"] for s in shards),
      "bundle_loads": sum(s.get("n_groups", 1) for s in shards),     # cores=1 -> == n_shards == n_nodes
      "output_folderpath": result.output_folderpath,
      "stac_catalog_filepath": result.stac_catalog_filepath}
print("FSD_RESULT_BEGIN"); print(json.dumps(out, indent=2, default=str)); print("FSD_RESULT_END")
with open(f"{os.environ['OUT38']}/phase3_result.json", "w") as f:
    json.dump(out, f, indent=2, default=str)
PY
.venv/bin/python "$OUT38/phase3.py"
```
- **Expect:** `n_shards` jobs (or fewer if `n_cells < n_shards`, D1's degrade), each `Completed`,
  every shard's `_status/<k>.json` `status: "ok"`, `n_failed: 0` across all shards. A ~1–2 min
  driver-side setup pause (with progress) precedes dispatch — see the note in the script.
- **PASS if:** `pass: true` in `phase3_result.json`, i.e. the exact-partition check
  (`sum_shard_units == n_cells_out == the ROI's cell count`, `n_skipped == 0` on a cold run),
  `n_failed == 0`, **and** the D7 claim `bundle_loads == n_shards_reported` (with `cores=1`, one
  bundle load per node — not once per cell). `driver_overhead_seconds`/`slowest_shard_seconds`
  feed TODO #55's timed-demo report.
- **If it fails:** paste `$OUT38/phase3_result.json`; `az ml job stream -n <job-name> ...` for a
  per-node traceback (job names are in the raised `RuntimeError`'s shard list, or
  `_status/*.json`'s `aml_job_status` for a job with no status file at all).

## Success criteria (`_result.json`)
Each phase writes `$OUT38/phase<N>_result.json` (also printed between `FSD_RESULT_BEGIN`/`_END`
markers). The run passes when every phase's `pass` is true. **Paste these files back** (not logs).

## Stop / observe
- `az ml job list -w "$AZ_ML_WORKSPACE" -g "$AZ_RG" --query "[?contains(name,'infer')]"` to watch
  jobs land; `az ml job stream -n <name> ...` for live logs on one.
- Abort a phase script with Ctrl-C — the AML jobs it already submitted keep running (cancel them in
  the studio/`az ml job cancel` if you want to actually stop spend); re-running the phase script is
  safe (D6/D12 resume) except Phase 2/3's fresh `run_id`s, which start a new run.
- **To force a truly cold run, point at a NEW `output_folderpath` — do not `fs.rm` the old prefix.**
  `fs.rm(prefix, recursive=True)` on `abfss://` deletes the files and *then* raises
  `DirectoryIsNotEmpty` (TODO #50) — it reads as "nothing happened" while the data is gone. Re-running
  onto the same folder is self-healing anyway (D6 skips finished cells).
- **VPN must stay up for the whole run** — the driver does blob I/O in every phase (bundle staging,
  reading `_status/*.json`). VPN off surfaces as `ErrorCode:AuthorizationFailure` (network rules),
  not a permissions error.
