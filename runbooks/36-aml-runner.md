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
  see "Build the AML Environment" below if it doesn't exist yet. **Rebuild it** if the fsd wheel
  changed since it was last built; the image predates the `_roi_gdf` and TODO #49 fixes.
- **The imagery archive on blob — `runbooks/37-download-on-aml.md` Phase 3's output**
  (`<download-root>/archive/` + its `catalog.parquet`: Austria `AT_ROI`, full-year 2018,
  B02/B03/B04/B08/B8A/SCL, MGRS tiles T33UVP/T33UVQ/T33UWP/T33UWQ).
- **`runbooks/37-verify-archive.md` PASSED** — do not start here otherwise. It is the gate that
  says the archive's radiometry tags are right and its catalog covers what landed; both are
  invisible failures from inside this run-book (green run, wrong science).

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
# Optional per-user path segment under the container (e.g. your username), if your
# storage layout scopes work by user. Set to empty (AZ_PREFIX='') if you write to the
# container root. Keep it consistent with what runbook 37 used.
export AZ_PREFIX='<your path prefix, e.g. username>'
export AZ_ROOT="abfss://${AZ_FS}@${AZ_ACCOUNT}.dfs.core.windows.net/${AZ_PREFIX:+$AZ_PREFIX/}fsd-p2"

# The imagery this run-book builds cubes FROM = whatever runbook 37's Phase 3 wrote to.
# It may live under a DIFFERENT root than `AZ_ROOT` (this run-book's own runs/outputs
# root) -- runbook 37's default is `fsd-p2-download/archive`, runbook 34's was
# `fsd-p2/imagery`. Set `AZ_ARCHIVE_ROOT` to the root you actually downloaded into.
# Getting it wrong is silent: a stale prefix builds cubes SUCCESSFULLY from the pre-fix
# spec-34 COGs, whose radiometry tags TODO #44 says are wrong.
export AZ_ARCHIVE_ROOT="${AZ_ROOT}"   # e.g. .../${AZ_PREFIX:+$AZ_PREFIX/}fsd-p2-download if you used runbook 37's default
export AZ_ARCHIVE_CATALOG="${AZ_ARCHIVE_ROOT}/archive/catalog.parquet"

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

# Confirm the archive catalog is really there before spending cluster time on it.
.venv/bin/python -c "
from fsd.storage import fs; import os
u = os.environ['AZ_ARCHIVE_CATALOG']; print('archive catalog:', u, fs.exists(u))"
```
- **PASS if:** the client-id line prints 8 hex characters **and** the archive-catalog line prints
  `True`. `False` means you are pointed at a prefix that does not exist — fix `AZ_ARCHIVE_ROOT`
  before Phase 1 rather than discovering it inside a job.

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

catalog_filepath = os.environ["AZ_ARCHIVE_CATALOG"]   # runbook 37 Phase 3's archive
run_folderpath = os.environ["AZ_ROOT"] + "/runs/phase1"
csv_filepath = run_folderpath + "/input.csv"

# setup() runs locally (cheap) -- it only writes small per-shape files, not imagery.
create_datacube.setup(
    catalog_filepath=catalog_filepath, timestamp_col="timestamp",
    # Sits 100% inside T33UWP, one of the archive's four MGRS tiles. Paths are
    # relative to `fsd/` (the Setup block's `cd fsd`), i.e. ONE `..`, not two.
    shapefilepath="../shapefiles/s2grid=476da24.geojson",  # single-tile Austria ROI
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
> ⚠️ **`setup()` APPENDS to `input.csv`; it does not rewrite it** (`create_datacube.py:127-131`:
> if the csv exists, the new rows are `pd.concat`-ed onto the old ones, **with no dedupe by id**).
> So re-running the same script does **not** re-run the same work-unit list — it runs a list that
> has grown by one copy of every shape. That is why this phase reports **`n_units: 2` for a
> one-cell ROI**, and a third run would report 3. `n_units` is "rows in `input.csv`", not "cells".
> Measured 2026-07-22; recorded as TODO #53.

- **Expect:** a fresh shard/job submits and completes quickly (no rebuild work).
- **PASS if:** `n_skipped == n_units`, `n_failed: 0`, and the elapsed `seconds` collapses versus
  Phase 1 (measured 2026-07-22: **47.3 s → 5.4 s**, `n_units: 2, n_skipped: 2`). It is the
  **`n_skipped == n_units` equality** that proves D7 — every unit asked `run_task` to rebuild and
  every one returned immediately — *not* any particular literal count, which the append behaviour
  above makes a moving target.
- **Confirm it did not rewrite** (the strongest form of the same claim): the `datacube.npy` blob's
  **last-modified timestamp is unchanged** from Phase 1:
  ```bash
  az storage blob show --account-name "$AZ_ACCOUNT" --container-name "$AZ_FS" \
    --name <path-under-container>/runs/phase1/<window>/<cell>/datacube.npy \
    --query properties.lastModified -o tsv
  ```
  compared before/after. An unchanged timestamp is the property that makes retries safe (D7).
- **If you want a clean second measurement** rather than a resumed one, delete `input.csv` (not the
  built cubes) before re-running: `python -c "from fsd.storage import fs; import os;
  fs.rm(os.environ['AZ_ROOT'] + '/runs/phase1/input.csv')"`. Single file, so TODO #50's broken
  recursive delete does not apply.

## Phase 3 — real fan-out (the demo)

> ⚠️ **The ROI must sit inside the archive's footprint, and the obvious-looking one does not.**
> `austria_eurocrops_sampled_ethiopia_translated.geojson` — this step's original ROI — is at
> **36.1–36.9°E / 11.4–12.0°N (Ethiopia)**, despite the "austria" in its name; the archive covers
> **T33UVP/T33UVQ/T33UWP/T33UWQ (13.6–16.5°E / 47.8–49.7°N)**. Zero intersection, so every one of
> the 1015 fields would produce an empty cube. Use **`AT_2018_TRAIN.geojson`** instead: 900 labelled
> fields (`fid` / `crop`), verified 2026-07-22 to lie **entirely within `AT_ROI`**, which is what
> run-book 37 Phase 3 downloaded. (Both ROIs also exercise the label path `flatten` needs.)

```bash
cat > "$OUT/phase3.py" <<'PY'
import json, os, time
from fsd.workflows import create_datacube, runners

# Time the whole thing. Without this the shard reports give in-job build time only,
# and the driver-side cost (setup + node allocation + image pull + queueing) is
# invisible -- which is most of the wall clock at high shard counts (TODO #48).
t0 = time.time()

catalog_filepath = os.environ["AZ_ARCHIVE_CATALOG"]   # runbook 37 Phase 3's archive
run_folderpath = os.environ["AZ_ROOT"] + "/runs/phase3"
csv_filepath = run_folderpath + "/input.csv"

create_datacube.setup(
    catalog_filepath=catalog_filepath, timestamp_col="timestamp",
    # 900 labelled fields, all inside AT_ROI = inside the archive's footprint.
    # (NOT austria_eurocrops_sampled_ethiopia_translated.geojson -- see the box above.)
    shapefilepath="../shapefiles/AT_2018_TRAIN.geojson",
    id_col="fid", run_folderpath=run_folderpath,
    startdate="2018-04-01", enddate="2018-09-01",
    bands=["B04", "B08", "B8A", "SCL"], scl_mask_classes=[0, 1, 3, 7, 8, 9, 10],
    mosaic_days=20, csv_filepath=csv_filepath, label_col="crop",
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
wall = time.time() - t0
slowest = max(s["seconds"] for s in result["shards"].values())
out = {"phase": "phase3-real-fanout", "pass": True,
       "wall_seconds": round(wall, 1),
       "slowest_shard_seconds": slowest,
       # everything not spent building: setup, allocation, image pull, queueing
       "driver_overhead_seconds": round(wall - slowest, 1),
       "result": result}
print("FSD_RESULT_BEGIN"); print(json.dumps(out, indent=2, default=str)); print("FSD_RESULT_END")
with open(f"{os.environ['OUT']}/phase3_result.json", "w") as f:
    json.dump(out, f, indent=2, default=str)
PY
.venv/bin/python "$OUT/phase3.py"
```
- **Expect:** the cluster scales to (up to) `AZ_N_SHARDS` nodes, each running one shard of the
  labelled fields via the **existing** local Snakemake runner inside the job.
- ⚠️ **Run `phase3.py` ONCE.** `setup()` appends to `input.csv` (see Phase 2's box / TODO #53), so a
  second run submits **1800** work-units for 900 fields. On already-built cells that is only wasted
  time, but on *unbuilt* ones the duplicate pair can be round-robined onto **two shards running
  concurrently**, both building the same cell and writing the same `datacube.npy` — an output race
  with no lock behind it. If you must re-run, delete `runs/phase3/input.csv` first.
- **PASS if:** every shard's `status == "ok"`, `sum(n_units) == sum(n_skipped) + sum(n_failed) ==
  0 + (total fields)` — on a **first** run; see the box above for why a re-run inflates it — and,
  the real proof, a **local** build of the same ROI (`runner="local"`,
  **the same `AZ_ARCHIVE_CATALOG`**, same `startdate`/`enddate`/`bands`/`mosaic_days`) produces a
  **byte-identical** `datacube.npy`
  for a handful of spot-checked cells (`fsd.storage.fs.load_npy(...)` both, `np.array_equal`), or
  a documented, explained difference (e.g. floating-point non-determinism in a resample kernel —
  not expected here, since the build is deterministic per spec 34).
- **Cost:** up to `AZ_N_SHARDS` `d16` nodes for the fan-out's duration; autoscales back to 0.

### Phase 3b — the equivalence check (**this is the actual demo claim**)

A green fan-out proves the *plumbing*. It does not prove the runner is a **seam** — that
`runner="aml"` and `runner="local"` produce the same science. That is the claim the whole project
rests on ("runner/storage = config, not a rewrite"), and it is only proven by comparing cubes.

Builds a handful of the same cells **locally**, from the **same blob archive**, into a **separate
local run folder** (a separate folder is required — pointed at the AML output, `run_task` would
simply skip and you would compare a cube against itself).

```bash
cat > "$OUT/phase3b.py" <<'PY'
import json, os
import geopandas as gpd
import numpy as np
import pandas as pd
from fsd.storage import fs
from fsd.workflows import create_datacube, runners

K = int(os.environ.get("AZ_COMPARE_CELLS", "3"))

# 1. what the cluster built
with fs.open(os.environ["AZ_ROOT"] + "/runs/phase3/input.csv", "r") as f:
    aml = pd.read_csv(f)
sample = aml.head(K)                      # deterministic, not random

# 2. the same fields, as a local subset shapefile
fields = gpd.read_file("../shapefiles/AT_2018_TRAIN.geojson")
local_dir = f"{os.environ['OUT']}/local_compare"
os.makedirs(local_dir, exist_ok=True)
subset_path = f"{local_dir}/fields.geojson"
fields[fields["fid"].isin(sample["id"])].to_file(subset_path, driver="GeoJSON")

# 3. build them locally -- SAME archive catalog, SAME window/bands/mosaic params.
#    Only the runner differs. That is the whole point.
local_csv = f"{local_dir}/input.csv"
create_datacube.setup(
    catalog_filepath=os.environ["AZ_ARCHIVE_CATALOG"], timestamp_col="timestamp",
    shapefilepath=subset_path, id_col="fid", run_folderpath=local_dir,
    startdate="2018-04-01", enddate="2018-09-01",
    bands=["B04", "B08", "B8A", "SCL"], scl_mask_classes=[0, 1, 3, 7, 8, 9, 10],
    mosaic_days=20, csv_filepath=local_csv, label_col="crop",
)
runners.run_local(local_csv, cores=int(os.environ.get("AZ_LOCAL_CORES", "4")))

# 4. compare cube for cube
local = pd.read_csv(local_csv)
comparisons = []
for _, r in sample.iterrows():
    lrow = local[local["id"] == r["id"]]
    if lrow.empty:
        comparisons.append({"id": r["id"], "error": "not built locally"}); continue
    a = fs.load_npy(r["datacube_filepath"])
    b = fs.load_npy(lrow.iloc[0]["datacube_filepath"])
    comparisons.append({
        "id": r["id"],
        "aml_shape": list(a.shape), "local_shape": list(b.shape),
        "dtype_match": str(a.dtype) == str(b.dtype),
        "shape_match": a.shape == b.shape,
        "identical": bool(a.shape == b.shape and np.array_equal(a, b)),
        "max_abs_diff": (float(np.abs(a.astype("float64") - b.astype("float64")).max())
                         if a.shape == b.shape else None),
    })

out = {"phase": "phase3b-aml-vs-local-equivalence", "status": "ok",
       "metrics": {"n_compared": len(comparisons),
                   "n_identical": sum(c.get("identical", False) for c in comparisons),
                   "comparisons": comparisons},
       "expected": {"n_identical": len(comparisons)}, "error": None}
out["pass"] = out["metrics"]["n_identical"] == len(comparisons) and len(comparisons) > 0
print("FSD_RESULT_BEGIN"); print(json.dumps(out, indent=2, default=str)); print("FSD_RESULT_END")
with open(f"{os.environ['OUT']}/phase3b_result.json", "w") as f:
    json.dump(out, f, indent=2, default=str)
PY
.venv/bin/python "$OUT/phase3b.py"
```
- **Expect:** `n_identical == n_compared`, every `max_abs_diff` `0.0`.
- **PASS if:** `pass: true` — the AML-built and locally-built cubes are **byte-identical**. The build
  is deterministic (spec 34), so anything else is a real difference, not float noise.
- **FAIL — shapes differ:** the two runs did not see the same imagery. Check that the local build
  used `AZ_ARCHIVE_CATALOG` and not a stale local catalog, and that the window/bands/`mosaic_days`
  match Phase 3 exactly.
- **FAIL — same shape, non-zero `max_abs_diff`:** a genuine finding. Report it rather than
  explaining it away; a resample/mosaic path that depends on the machine would undermine the seam.
- **Cost:** K cells built on your laptop, reading imagery from blob over VPN — slower per cell than
  a node. Start with `AZ_COMPARE_CELLS=3`.

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
