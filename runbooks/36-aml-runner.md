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

export AZ_UAMI_CLIENT_ID="$(az identity show -g "$AZ_RG" -n "$AZ_UAMI_NAME" --query clientId -o tsv)"
echo "client id resolved: ${AZ_UAMI_CLIENT_ID:0:8}…"

export OUT="$PWD/tests/outputs/p2_aml_runner"    # gitignored
mkdir -p "$OUT"
```
- **PASS if:** the client-id line prints 8 hex characters.

## Build the AML Environment (spec 36 D5) — once, or whenever the fsd wheel changes
```bash
.venv/bin/pip wheel . --no-deps -w "$OUT/env_src" && ls "$OUT"/env_src/fsd-*.whl

cat > "$OUT/env_src/conda.yaml" <<'YML'
name: fsd-aml-env
channels:
  - conda-forge
dependencies:
  - python=3.11
  - pip
YML

cat > "$OUT/env.yml" <<YML
\$schema: https://azuremlschemas.azureedge.net/latest/environment.schema.json
name: ${AZ_ENV_NAME}
image: mcr.microsoft.com/azureml/openmpi4.1.0-ubuntu22.04:latest
conda_file: ./env_src/conda.yaml
YML

# NOTE: this build installs the wheel via a post-provisioning step is NOT how AML
# environments work -- the wheel itself must be a pip dependency baked into the conda
# spec. Simplest correct form: publish the wheel to a location pip can reach (e.g. a
# private index, or inline as a local path dependency) and add it to conda.yaml's
# `pip:` list before `az ml environment create`. See AML docs "Manage environments"
# for the exact pip-from-local-wheel syntax at the version installed
# (`az ml environment create -f env.yml -g "$AZ_RG" -w "$AZ_ML_WORKSPACE"`).
az ml environment create -f "$OUT/env.yml" -g "$AZ_RG" -w "$AZ_ML_WORKSPACE" --query name -o tsv
```
- **Expect:** `${AZ_ENV_NAME}` printed back.
- **PASS if:** `az ml environment show -n "$AZ_ENV_NAME" -g "$AZ_RG" -w "$AZ_ML_WORKSPACE"
  --query provisioning_state -o tsv` prints `Succeeded`.
- **Re-run whenever the fsd wheel changes** — `run_aml`'s preflight (D10) checks the environment
  resolves, but not that it's current; rebuild after any `src/fsd/` change you want on the cluster.

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
    cluster=os.environ["AZ_CLUSTER"], environment=f"{os.environ['AZ_ENV_NAME']}:1",
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
    cluster=os.environ["AZ_CLUSTER"], environment=f"{os.environ['AZ_ENV_NAME']}:1",
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
