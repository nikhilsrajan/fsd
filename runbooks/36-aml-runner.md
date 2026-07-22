# Run-book: 36 Phases 1–3 — the AML runner, end to end

> Spec-24 run-book for **spec 36 §6 Phases 1–3**. **You** run this; paste back each phase's
> printed JSON. Phase 0 (identity smoke) already ran and is green
> (`runbooks/36-phase0-identity-smoke.md`) — this run-book assumes D4 confirmed.
>
> **Concrete `rise` values are NOT in this file** (public repo). You paste them as env vars from
> the uncommitted `../../AZURE_INFRA_PRIVATE.md` (workspace root).

## Purpose

Prove `runner="aml"` end to end: one shard/one cube (Phase 1), a resumed re-run that skips
everything already built (Phase 2, proving D7), and a real multi-shard fan-out compared
cube-for-cube against a local build of the same ROI (Phase 3 — **this is the demo**).

## Prerequisites
- **VPN connected**, `az login` done, correct subscription selected.
- The fsd venv with the `[aml]` extra: `cd fsd && source .venv/bin/activate &&
  pip install -e ".[dev,azure,aml]"` (installs `azure-ai-ml` — unlike Phase 0, this run-book calls
  `fsd.workflows.runners.run_aml` directly from your laptop via the Python SDK, not the `az ml`
  CLI, so the driver needs the SDK).
- An **AML Environment** already built for spec 36 D5 (fsd wheel + `[azure]` extra installed) —
  see "Build the AML Environment" below if it doesn't exist yet.
- The Austria archive already on blob (`runbooks/34-download-to-blob.md`'s output) for Phase 3's
  comparison ROI.

## Setup — paste your concrete values (from `AZURE_INFRA_PRIVATE.md`, uncommitted)
```bash
cd fsd
export AZ_RG='<resource group>'                 # rg<proj>
export AZ_ML_WORKSPACE='<aml workspace>'        # mlw<proj>
export AZ_SUBSCRIPTION_ID='<subscription id>'
export AZ_CLUSTER='<the d16 cluster name>'      # cluster-<proj>-d16
export AZ_UAMI_NAME='<compute identity name>'   # id<proj>-compute
export AZ_ACCOUNT='<storage account>'           # st<proj>
export AZ_FS='<filesystem/container>'           # e.g. data
export AZ_ROOT="abfss://${AZ_FS}@${AZ_ACCOUNT}.dfs.core.windows.net/fsd-p2"
export AZ_ENV_NAME='fsd-aml-env'
# AZ_ENV_VERSION is exported by "Build the AML Environment" below (AML auto-assigns it).
# In a *later* shell, re-export the version you built:
#   export AZ_ENV_VERSION="$(az ml environment list -n "$AZ_ENV_NAME" -g "$AZ_RG" \
#     -w "$AZ_ML_WORKSPACE" --query "[].version" -o tsv | sort -V | tail -1)"

export AZ_UAMI_CLIENT_ID="$(az identity show -g "$AZ_RG" -n "$AZ_UAMI_NAME" --query clientId -o tsv)"
echo "client id resolved: ${AZ_UAMI_CLIENT_ID:0:8}…"

# Knob the phase scripts read (inline default 8 if unset -- exported here to keep it visible).
export AZ_N_SHARDS='8'      # datacube fan-out width (Phase 3)

export OUT="$PWD/tests/outputs/p2_aml_runner"    # gitignored
mkdir -p "$OUT"
```
- **PASS if:** the client-id line prints 8 hex characters.

## Build the AML Environment (spec 36 D5) — once, or whenever the fsd wheel changes

> **The image must contain fsd itself.** `runners.run_aml`/`run_aml_download` submit a bare
> `python -m fsd.workflows.…` command with **no `code=` upload and no pip install in the command**
> (`runners.py`, `aml_command(command=…, environment=…, compute=…)`). That is the opposite of
> `36-phase0-identity-smoke.md`, which uploaded `code: ./job_src` and pip-installed the wheel at job
> start — fine for a probe, but it produces no *registered* environment for `environment=` to name.
> So the wheel is baked into the image here, via a **Docker build context**.
>
> **Why a build context and not `conda_file`:** in the environment schema, `conda_file` *requires*
> `image`, and `image`/`build` are mutually exclusive — so a conda spec can't carry a local wheel
> (only the conda file itself is uploaded, not sibling files). `build.path` uploads the **whole
> directory**, wheel included. (AML CLI v2 environment YAML schema — see Sources at the bottom.)

```bash
# 1. Build context = the wheel + a Dockerfile, in one directory.
rm -rf "$OUT/env_src" && mkdir -p "$OUT/env_src"
.venv/bin/pip wheel . --no-deps -w "$OUT/env_src" && ls "$OUT"/env_src/fsd-*.whl

cat > "$OUT/env_src/Dockerfile" <<'DOCKER'
# The same base image phase 0 proved works on this cluster.
FROM mcr.microsoft.com/azureml/openmpi4.1.0-ubuntu22.04:latest
COPY fsd-*.whl /tmp/
# [azure] -> adlfs + azure-identity + azure-keyvault-secrets (blob I/O, D4 identity, D5 KV creds)
# [mpc]   -> planetary-computer (asset signing). s3fs/pystac-client are core deps.
# NOT [aml]: azure-ai-ml is a *driver*-side dep; the node never submits jobs.
RUN python -m pip install --no-cache-dir "$(ls /tmp/fsd-*.whl)[azure,mpc]" \
 && python -m pip cache purge || true
DOCKER

cat > "$OUT/env.yml" <<YML
\$schema: https://azuremlschemas.azureedge.net/latest/environment.schema.json
name: ${AZ_ENV_NAME}
build:
  path: ./env_src
  dockerfile_path: Dockerfile
YML

# version is omitted on purpose -> AML auto-increments it. Capture what it assigned:
export AZ_ENV_VERSION="$(az ml environment create -f "$OUT/env.yml" \
  -g "$AZ_RG" -w "$AZ_ML_WORKSPACE" --query version -o tsv)"
echo "built ${AZ_ENV_NAME}:${AZ_ENV_VERSION}"
```
- **Expect:** the image build runs (several minutes the first time), then `built fsd-aml-env:<N>`.
- ⚠️ **Export `AZ_ENV_VERSION` in every later shell** — the phase scripts reference
  `${AZ_ENV_NAME}:${AZ_ENV_VERSION}`. If you lose it:
  `az ml environment list -n "$AZ_ENV_NAME" -g "$AZ_RG" -w "$AZ_ML_WORKSPACE" --query "[].version" -o tsv`
- **PASS if:** the following prints the name and version back:
  ```bash
  az ml environment show -n "$AZ_ENV_NAME" --version "$AZ_ENV_VERSION" \
    -g "$AZ_RG" -w "$AZ_ML_WORKSPACE" --query "[name, version]" -o tsv
  ```
  `--version` (or `--label`) is **required** — `az ml environment show` without one fails with
  `Must provide either version or label`. Don't query `provisioning_state`: it is not in the
  environment schema, and `--query` on a missing field prints an empty line that reads like a
  failure.

### Verify the image actually contains fsd (do this before Phase 1)
A registered environment can exist and still be unusable — a wrong base-image `python` on `PATH`
would put the wheel somewhere the job's interpreter can't see. One cheap job settles it:
```bash
cat > "$OUT/env_smoke.yml" <<YML
\$schema: https://azuremlschemas.azureedge.net/latest/commandJob.schema.json
display_name: fsd-env-smoke
experiment_name: fsd-p2
command: >-
  python -c "import fsd, s3fs, adlfs, planetary_computer, pystac_client;
  import azure.keyvault.secrets;
  print('FSD_ENV_OK', fsd.__version__)"
environment: azureml:${AZ_ENV_NAME}:${AZ_ENV_VERSION}
compute: azureml:${AZ_CLUSTER}
YML
az ml job create -f "$OUT/env_smoke.yml" -g "$AZ_RG" -w "$AZ_ML_WORKSPACE" --query name -o tsv
# then stream it with the returned job name:
#   az ml job stream -n <job-name> -g "$AZ_RG" -w "$AZ_ML_WORKSPACE"
```
- **PASS if:** the log prints `FSD_ENV_OK 0.1.0` and the job finishes `Completed`.
- **FAIL — `ModuleNotFoundError: No module named 'fsd'`:** the image's default `python` isn't the
  one pip installed into. Fix in the Dockerfile (pin an explicit interpreter path, e.g.
  `RUN /opt/miniconda/bin/python -m pip install …`, and set `ENV PATH=` accordingly), rebuild, and
  re-run this smoke — **do not** proceed to Phase 1, which would burn cluster time and CDSE quota
  before hitting the same import.
- **FAIL — a *different* module missing** (`adlfs`, `planetary_computer`, …): an extra is missing
  from the Dockerfile's install line; add it and rebuild.

- **Re-run this whole step whenever the fsd wheel changes** — `run_aml`'s preflight (D10) checks the
  environment *resolves*, not that it's *current*; rebuild after any `src/fsd/` change you want on
  the cluster, and re-export the new `AZ_ENV_VERSION`.

## Phase 1 — one shard, one cube
```bash
cat > "$OUT/phase1.py" <<'PY'
import json, os, sys
from fsd.workflows import create_datacube, runners

catalog_filepath = os.environ["AZ_ROOT"] + "/imagery/catalog.parquet"  # runbook 34's output
run_folderpath = os.environ["AZ_ROOT"] + "/runs/phase1"
csv_filepath = run_folderpath + "/input.csv"

# setup() runs locally (cheap) -- it only writes small per-shape files, not imagery.
create_datacube.setup(
    catalog_filepath=catalog_filepath, timestamp_col="timestamp",
    shapefilepath="../../shapefiles/s2grid=476da24.geojson",  # single-tile Austria ROI
    id_col="id", run_folderpath=run_folderpath,
    startdate="2018-04-01", enddate="2018-09-01",
    bands=["B04", "B08", "B8A", "SCL"], scl_mask_classes=[0, 1, 3, 7, 8, 9, 10],
    mosaic_days=20, csv_filepath=csv_filepath, label_col=None,
)

result = runners.run_aml(
    csv_filepath,
    cluster=os.environ["AZ_CLUSTER"], environment=f"{os.environ['AZ_ENV_NAME']}:{os.environ['AZ_ENV_VERSION']}",
    root=os.environ["AZ_ROOT"], identity_client_id=os.environ["AZ_UAMI_CLIENT_ID"],
    n_shards=1, subscription_id=os.environ["AZ_SUBSCRIPTION_ID"],
    resource_group_name=os.environ["AZ_RG"], workspace_name=os.environ["AZ_ML_WORKSPACE"],
    run_id="phase1",
)
out = {"phase": "phase1-one-shard-one-cube", "pass": True, "result": result}
print("FSD_RESULT_BEGIN"); print(json.dumps(out, indent=2, default=str)); print("FSD_RESULT_END")
with open(f"{os.environ['OUT']}/phase1_result.json", "w") as f:
    json.dump(out, f, indent=2, default=str)
PY
.venv/bin/python "$OUT/phase1.py"
```
- **Expect:** the cluster scales 0→1, one job runs `python -m fsd.workflows.shard ...`, and
  `FSD_RESULT_BEGIN…END` prints a `result` with `n_shards: 1` and no exception.
- **PASS if:** `result.shards["0"].status == "ok"` and a `datacube.npy` exists at
  `$AZ_ROOT/runs/phase1/<cell>/datacube.npy` (check with
  `az storage blob list --account-name "$AZ_ACCOUNT" --container-name "$AZ_FS"
  --prefix fsd-p2/runs/phase1 -o table` or `fsd.storage.fs.exists(...)` from a Python shell).
- **If it fails:** paste `$OUT/phase1_result.json` and the AML job's stderr
  (`az ml job stream -n <job-name> -g "$AZ_RG" -w "$AZ_ML_WORKSPACE"` — the job name is in
  `result.job_statuses`... if submission itself failed, the traceback prints directly).

## Phase 2 — resume (proves D7)
Re-run the **exact same command** (Phase 1 script, unchanged) a second time:
```bash
.venv/bin/python "$OUT/phase1.py"
```
- **Expect:** a fresh shard/job submits and completes quickly (no rebuild work).
- **PASS if:** the shard's status shows `n_skipped: 1`, `n_units: 1`, `n_failed: 0`, and the
  `datacube.npy` blob's **last-modified timestamp is unchanged** from Phase 1 (`az storage blob
  show --account-name "$AZ_ACCOUNT" --container-name "$AZ_FS"
  --name fsd-p2/runs/phase1/<cell>/datacube.npy --query properties.lastModified -o tsv`,
  compared before/after). An unchanged timestamp is the property that makes retries safe (D7) —
  the resumed job asked `run_task` to rebuild, and `run_task` returned immediately instead.

## Phase 3 — real fan-out (the demo)
```bash
cat > "$OUT/phase3.py" <<'PY'
import json, os
from fsd.workflows import create_datacube, runners

catalog_filepath = os.environ["AZ_ROOT"] + "/imagery/catalog.parquet"
run_folderpath = os.environ["AZ_ROOT"] + "/runs/phase3"
csv_filepath = run_folderpath + "/input.csv"

create_datacube.setup(
    catalog_filepath=catalog_filepath, timestamp_col="timestamp",
    shapefilepath="../../shapefiles/austria_eurocrops_sampled_ethiopia_translated.geojson",
    id_col="fid", run_folderpath=run_folderpath,
    startdate="2018-04-01", enddate="2018-09-01",
    bands=["B04", "B08", "B8A", "SCL"], scl_mask_classes=[0, 1, 3, 7, 8, 9, 10],
    mosaic_days=20, csv_filepath=csv_filepath, label_col="EC_hcat_n",
)

result = runners.run_aml(
    csv_filepath,
    cluster=os.environ["AZ_CLUSTER"], environment=f"{os.environ['AZ_ENV_NAME']}:{os.environ['AZ_ENV_VERSION']}",
    root=os.environ["AZ_ROOT"], identity_client_id=os.environ["AZ_UAMI_CLIENT_ID"],
    n_shards=int(os.environ.get("AZ_N_SHARDS", "8")),
    subscription_id=os.environ["AZ_SUBSCRIPTION_ID"],
    resource_group_name=os.environ["AZ_RG"], workspace_name=os.environ["AZ_ML_WORKSPACE"],
    run_id="phase3",
)
out = {"phase": "phase3-real-fanout", "pass": True, "result": result}
print("FSD_RESULT_BEGIN"); print(json.dumps(out, indent=2, default=str)); print("FSD_RESULT_END")
with open(f"{os.environ['OUT']}/phase3_result.json", "w") as f:
    json.dump(out, f, indent=2, default=str)
PY
.venv/bin/python "$OUT/phase3.py"
```
- **Expect:** the cluster scales to (up to) `AZ_N_SHARDS` nodes, each running one shard of the
  EuroCrops fields via the **existing** local Snakemake runner inside the job.
- **PASS if:** every shard's `status == "ok"`, `sum(n_units) == sum(n_skipped) + sum(n_failed) ==
  0 + (total fields)`, and — the real proof — a **local** build of the same ROI (`runner="local"`,
  same `startdate`/`enddate`/`bands`/`mosaic_days`) produces a **byte-identical** `datacube.npy`
  for a handful of spot-checked cells (`fsd.storage.fs.load_npy(...)` both, `np.array_equal`), or
  a documented, explained difference (e.g. floating-point non-determinism in a resample kernel —
  not expected here, since the build is deterministic per spec 34).
- **Cost:** up to `AZ_N_SHARDS` `d16` nodes for the fan-out's duration; autoscales back to 0.

## Success criteria (`_result.json`)
Each phase writes `$OUT/phase<N>_result.json`:
```json
{ "phase": "phase1-one-shard-one-cube", "pass": true,
  "result": { "run_id": "phase1", "n_shards": 1,
              "shards": { "0": { "status": "ok", "n_units": 1, "n_skipped": 0, "n_failed": 0 } } } }
```
Paste these back (not the AML job logs) — Claude diffs them against the PASS conditions above.

## Stop / observe
- Progress: `az ml job stream -n <job-name> -g "$AZ_RG" -w "$AZ_ML_WORKSPACE"` (the job name is on
  each shard's AML job; `result["job_statuses"]` has the per-shard AML status if you need to look
  one up). Studio URL is printed at submission.
- Abort a phase: `Ctrl-C` the Python driver (the already-submitted AML jobs keep running --
  cancel them individually with `az ml job cancel -n <job-name> ...` if you don't want that),
  or `az ml job cancel -n <job-name> -g "$AZ_RG" -w "$AZ_ML_WORKSPACE"` per job.
- Re-run: Phases 1/2 are idempotent by design (D7). Phase 3 is too, but costs more per re-run.

## Sources — the environment-build step

Checked 2026-07-22, after `az ml environment show --query provisioning_state` failed for the
operator with `Must provide either version or label`.

- **[CLI (v2) environment YAML schema](https://learn.microsoft.com/en-us/azure/machine-learning/reference-yaml-environment?view=azureml-api-2)**
  — the whole build-context rewrite rests on this table: *"`image` … **One of `image` or `build` is
  required**"*, *"`conda_file` … **If specified, `image` must be specified as well**"* (so a conda
  spec can never carry a local wheel), *"`build.path` — Local path to the directory to use as the
  build context"*, and *"`build.dockerfile_path` … Default: `Dockerfile`"*. Also *"`version` … **If
  omitted, Azure Machine Learning will autogenerate a version**"* — why the step captures the
  assigned version into `AZ_ENV_VERSION` instead of hardcoding `:1`. The page's field list contains
  **no `provisioning_state`**, which is why the old PASS check queried a field that does not exist.
- **[`az ml environment` CLI reference](https://learn.microsoft.com/en-us/cli/azure/ml/environment?view=azure-cli-latest)**
  — `az ml environment show` takes `--name` as the only *required* parameter with `--version`/
  `--label` "optional", but the operator's error shows one of the pair is required in practice;
  hence the corrected `--version "$AZ_ENV_VERSION"` invocation and the `az ml environment list
  --query "[].version"` recovery command. Also documents `--build-context/-b` and `--image/-i` as
  **mutually exclusive**, corroborating the schema's `image` xor `build`.
