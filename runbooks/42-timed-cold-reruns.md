# Run-book: 42 — timed COLD re-runs of the two untimed AML steps

> Spec-24 run-book. **You** run it; paste back each step's `_result.json`. Claude never runs it
> (CLAUDE.md).
> **⚠️ This one spends money.** It allocates the 16-node cluster twice and writes a second copy of
> the imagery archive to blob. Run `runbooks/41-recover-aml-job-timings.md` **first** — it is free.
> Chosen by the user 2026-07-28 with that cost stated.
>
> **What run-book 41 changed about this one (2026-07-28).** Steps 1 + 1b closed the timeline for
> free and gave both of this run-book's targets a tight **lower bound**: run-book 36 Phase 3's wall
> is **≥ 343 s** and run-book 37 Phase 3's is **≥ 354 s** (job span plus the 19 s / 26 s to the
> driver's own `_result.json` write). Two consequences:
>
> - **It is much cheaper than it looked.** Each step is a ~6-minute cluster run, not ~20 min.
> - **It is still worth running**, because a lower bound is not a wall: only a real
>   `wall_seconds` pins the *pre-dispatch* window (`setup()` + submit + allocation), which for these
>   two phases has never been measured at all. Differenced against 41's spans it completes the
>   decomposition — and gives run-book 42's own `wall_seconds` line something to be checked against.

## Purpose

Produce a genuine `wall_seconds` for the two AML steps that have none, so the local-vs-AML report
(`demos/E2E_AUSTRIA_AML.md`) can quote a measured driver wall instead of "not measured":

| step | run-book | what has to be cold | why a plain re-run will NOT do |
|---|---|---|---|
| A | 36 Phase 3 — build 900 field cubes | a **fresh** `run_folderpath` | D7 resume: the 900 cubes exist under `runs/phase3`, so a re-run times the *skip* path (Phase 2 measured that: 47.3 s → 5.4 s) |
| B | 37 Phase 3 — download the archive | a **fresh** `dst`/catalog prefix | the download skips assets already on blob; re-running into `archive/` measures existence checks |

Each step is a faithful replay of the original call — same inputs, same window, same bands, same
`n_shards`, same `cores` — with only the **output prefix** changed and the driver wall recorded.
Anything else changed and the number is not comparable to the per-shard seconds already stored.

## Prerequisites
- **VPN connected**, `az login`, correct subscription.
- `fsd/.venv` with `[dev,azure,aml]`.
- The **AML Environment** run-book 36/37 used, rebuilt if the wheel moved (`AZ_ENV_NAME:VERSION`).
- **Run-book 41 already run**, so we know what the free path recovered.
- The cluster **idle** — do not run Steps A and B at the same time, and do not run them alongside
  anything else on the cluster. Two jobs contending for 32 nodes distorts both walls, which is the
  only thing this run-book is measuring.

## Setup — paste your concrete values (from `AZURE_INFRA_PRIVATE.md`, uncommitted)
```bash
cd fsd && source .venv/bin/activate
export AZ_RG='<resource group>'
export AZ_ML_WORKSPACE='<aml workspace>'
export AZ_SUBSCRIPTION_ID='<subscription id>'
export AZ_CLUSTER='<the d16 cluster name>'
export AZ_UAMI_NAME='<compute identity name>'
export AZ_UAMI_CLIENT_ID="$(az identity show -g "$AZ_RG" -n "$AZ_UAMI_NAME" --query clientId -o tsv)"
export AZ_ACCOUNT='<storage account>'
export AZ_FS='<filesystem/container>'
export AZ_PREFIX='<your path prefix, e.g. username>'
export AZ_ROOT="abfss://${AZ_FS}@${AZ_ACCOUNT}.dfs.core.windows.net/${AZ_PREFIX:+$AZ_PREFIX/}fsd-p2"

# The VERIFIED archive that run-book 36 built cubes FROM (read-only input here).
export AZ_ARCHIVE_CATALOG="${AZ_ROOT}/archive/catalog.parquet"
# The ROI on blob that run-book 37 Phase 3 downloaded for (AT_ROI).
export AZ_ROI_REAL_URL='<the AT_ROI geojson url on blob that runbook 37 Phase 3 used>'

export AZ_ENV_NAME='fsd-aml-env'
export AZ_ENV_VERSION="$(az ml environment list -n "$AZ_ENV_NAME" -g "$AZ_RG" \
  -w "$AZ_ML_WORKSPACE" --query "[].version" -o tsv 2>/dev/null | sort -V | tail -1)"
echo "environment: ${AZ_ENV_NAME}:${AZ_ENV_VERSION}"

export AZ_N_SHARDS='16'      # what BOTH original runs actually used (16 shards in each result file)
export OUT42="$PWD/tests/outputs/p42_timed_reruns"   # gitignored
mkdir -p "$OUT42"
```

## Steps

### Step A — run-book 36 Phase 3, cold and timed (build 900 field cubes)

Writes 900 fresh cubes under `${AZ_ROOT}/runs/phase3-timed/` (~21 MB total — the training cubes are
tiny, median 14×15 px). Cluster time is the cost, not storage.

> ⚠️ **Run this script exactly ONCE.** `create_datacube.setup()` appends to `input.csv` with no
> dedupe (TODO #53), so a second run dispatches 1800 units for 900 fields and the wall becomes
> meaningless. If you must retry, delete `${AZ_ROOT}/runs/phase3-timed/input.csv` first (single
> file — TODO #50's broken recursive delete does not apply).

```bash
cat > "$OUT42/stepA.py" <<'PY'
import json, os, time
from fsd.workflows import create_datacube, runners

RUN = "phase3-timed"
run_folderpath = os.environ["AZ_ROOT"] + f"/runs/{RUN}"
csv_filepath = run_folderpath + "/input.csv"

t0 = time.time()
# Identical to runbook 36 Phase 3 except run_folderpath/csv_filepath (fresh -> real work).
create_datacube.setup(
    catalog_filepath=os.environ["AZ_ARCHIVE_CATALOG"], timestamp_col="timestamp",
    shapefilepath="../shapefiles/AT_2018_TRAIN.geojson",
    id_col="fid", run_folderpath=run_folderpath,
    startdate="2018-04-01", enddate="2018-09-01",
    bands=["B04", "B08", "B8A", "SCL"], scl_mask_classes=[0, 1, 3, 7, 8, 9, 10],
    mosaic_days=20, csv_filepath=csv_filepath, label_col="crop",
)
t_setup = time.time() - t0

result = runners.run_aml(
    csv_filepath,
    cluster=os.environ["AZ_CLUSTER"],
    environment=f"{os.environ['AZ_ENV_NAME']}:{os.environ['AZ_ENV_VERSION']}",
    root=os.environ["AZ_ROOT"], identity_client_id=os.environ["AZ_UAMI_CLIENT_ID"],
    n_shards=int(os.environ["AZ_N_SHARDS"]),
    cores=16,            # run_aml's default -- what the ORIGINAL run used (it passed no cores=)
    subscription_id=os.environ["AZ_SUBSCRIPTION_ID"],
    resource_group_name=os.environ["AZ_RG"], workspace_name=os.environ["AZ_ML_WORKSPACE"],
    run_id=RUN,
)
wall = time.time() - t0
shards = result["shards"]
slowest = max(s["seconds"] for s in shards.values())
out = {"step": "A-runbook36-phase3-cold-timed", "status": "ok",
       "pass": all(s["n_failed"] == 0 for s in shards.values()),
       "metrics": {
           "wall_seconds": round(wall, 1),
           "setup_seconds": round(t_setup, 1),
           "slowest_shard_seconds": slowest,
           "driver_overhead_seconds": round(wall - slowest, 1),
           "sum_shard_seconds": round(sum(s["seconds"] for s in shards.values()), 1),
           "n_shards": len(shards), "cores_per_shard": 16,
           "sum_shard_units": sum(s["n_units"] for s in shards.values()),
           "sum_skipped": sum(s["n_skipped"] for s in shards.values()),
           "sum_failed": sum(s["n_failed"] for s in shards.values()),
           "run_folderpath": run_folderpath,
       },
       "expected": {"sum_shard_units": 900, "sum_skipped": 0, "sum_failed": 0, "n_shards": 16},
       "error": None, "result": result}
print("FSD_RESULT_BEGIN"); print(json.dumps(out, indent=2, default=str)); print("FSD_RESULT_END")
with open(f"{os.environ['OUT42']}/stepA_result.json", "w") as f:
    json.dump(out, f, indent=2, default=str)
PY
.venv/bin/python "$OUT42/stepA.py"
```

- **Expect:** 16 jobs `Completed`; per-shard seconds in the same neighbourhood as the stored run
  (slowest **213.8 s**, Σ 2851.8 s) — that similarity is the check that this really was the same work.
- **PASS if:** `sum_shard_units == 900`, **`sum_skipped == 0`** (this is the cold-ness proof — a
  non-zero value means the prefix was not fresh and the wall is worthless), `sum_failed == 0`.
- **Runtime:** the original run's **jobs** executed in a 324 s window (run-book 41 Step 1b: 16 jobs,
  17:49:57 → 17:55:21 UTC) and its driver wrote the result 19 s after the last one ended, so the
  wall is **≥ 343 s**. Expect ~6–8 min. The unmeasured part is the **pre-dispatch** window
  (`setup()` over 900 shapes — 71 s when measured locally — plus submit and first-node allocation),
  and pinning it is the point of this step. **Do not compare this wall against the local laptop's
  build alone** — see the report's confounds section.
- **If it fails / hangs:** Ctrl-C is safe (the driver is only polling; jobs keep running — cancel
  them in the Studio if you want the nodes back). Paste the traceback.

### Step B — run-book 37 Phase 3, cold and timed (download the archive again)

> 💸 **This is the expensive one.** It writes a **second full copy of a 418.0 GB archive**
> (3456 assets, measured by run-book 41 Step 2) to `${AZ_ROOT}/archive-timed/`, and holds 16 nodes
> for ~6–8 min while it does. **Step C deletes it — do not skip Step C**, or you are paying to store
> 418 GB twice. The compute is minutes; the storage is only cheap if it is transient.

> ⚠️ It writes to a **fresh** `dst` and a **fresh** catalog on purpose. Never point a timed re-run at
> `archive/` — that prefix is the one `37-verify-archive.md` certified and everything downstream
> reads.

```bash
export AZ_MAX_TILES='600'    # a real cap (TODO #49); the archive is 576 MGRS tiles
cat > "$OUT42/stepB.py" <<'PY'
import json, os, time
from fsd.workflows import runners

RUN = "phase3-archive-timed"
dst = os.environ["AZ_ROOT"] + "/archive-timed"

# Bare date STRINGS, exactly as the original run passed them. pystac_client expands a
# date-only string to the end of its day, which is why the original landed 3456 assets
# and the pd.Timestamp dry-run landed 3432 (TODO #52). Passing Timestamps here would
# download 24 fewer assets and quietly break comparability.
t0 = time.time()
result = runners.run_aml_download(
    os.environ["AZ_ROI_REAL_URL"], "2018-01-01", "2019-01-01",
    ["B02", "B03", "B04", "B08", "B8A", "SCL"],
    dst, dst + "/catalog.parquet",
    source="mpc",
    max_tiles=int(os.environ["AZ_MAX_TILES"]),
    n_shards=int(os.environ["AZ_N_SHARDS"]),
    run_id=RUN,
    cluster=os.environ["AZ_CLUSTER"],
    environment=f"{os.environ['AZ_ENV_NAME']}:{os.environ['AZ_ENV_VERSION']}",
    root=os.environ["AZ_ROOT"], identity_client_id=os.environ["AZ_UAMI_CLIENT_ID"],
    subscription_id=os.environ["AZ_SUBSCRIPTION_ID"],
    resource_group_name=os.environ["AZ_RG"], workspace_name=os.environ["AZ_ML_WORKSPACE"],
)
wall = time.time() - t0
reports = result["reports"]
slowest = max(r["seconds"] for r in reports.values())
out = {"step": "B-runbook37-phase3-cold-timed", "status": "ok",
       "pass": all(r["n_failed"] == 0 and not r.get("circuit_tripped") for r in reports.values()),
       "metrics": {
           "wall_seconds": round(wall, 1),
           "slowest_shard_seconds": slowest,
           "driver_overhead_seconds": round(wall - slowest, 1),
           "sum_shard_seconds": round(sum(r["seconds"] for r in reports.values()), 1),
           "n_shards": len(reports),
           "sum_assets": sum(r["n_assets"] for r in reports.values()),
           "sum_skipped": sum(r["n_skipped"] for r in reports.values()),
           "sum_failed": sum(r["n_failed"] for r in reports.values()),
           "dst": dst,
       },
       "expected": {"sum_assets": 3456, "sum_skipped": 0, "sum_failed": 0, "n_shards": 16},
       "error": None, "result": result}
print("FSD_RESULT_BEGIN"); print(json.dumps(out, indent=2, default=str)); print("FSD_RESULT_END")
with open(f"{os.environ['OUT42']}/stepB_result.json", "w") as f:
    json.dump(out, f, indent=2, default=str)
PY
.venv/bin/python "$OUT42/stepB.py"
```

- **Expect:** 16 jobs `Completed`, 216 assets each; per-shard seconds near the stored run
  (slowest **192.1 s**, Σ 2434.7 s).
- **PASS if:** `sum_assets == 3456`, **`sum_skipped == 0`** (cold-ness proof), `sum_failed == 0`,
  no shard circuit-tripped.
- **`sum_assets == 3432` is not a failure** — it means the date-string behaviour changed under us
  (TODO #52's 24-asset boundary acquisition). Paste it; Claude annotates the row rather than
  discarding it.
- **Runtime:** the original run's jobs executed in a 328 s window and its driver wrote the result
  26 s later, so the wall is **≥ 354 s**; expect ~6–8 min. MPC is a live service and can be slower
  on the day — the circuit breaker stops a pathological run.

### Step C — delete the timed copies (do this the same day)

```bash
# CHECK the paths first -- this is a recursive delete.
echo "will delete under container ${AZ_FS}:"
echo "  ${AZ_PREFIX:+$AZ_PREFIX/}fsd-p2/archive-timed"
echo "  ${AZ_PREFIX:+$AZ_PREFIX/}fsd-p2/runs/phase3-timed"
```
```bash
az storage fs directory delete --account-name "$AZ_ACCOUNT" -f "$AZ_FS" --auth-mode login -y \
  -n "${AZ_PREFIX:+$AZ_PREFIX/}fsd-p2/archive-timed"
az storage fs directory delete --account-name "$AZ_ACCOUNT" -f "$AZ_FS" --auth-mode login -y \
  -n "${AZ_PREFIX:+$AZ_PREFIX/}fsd-p2/runs/phase3-timed"
```
```bash
cat > "$OUT42/stepC.py" <<'PY'
import json, os
from fsd.storage import fs
paths = {"archive_timed": os.environ["AZ_ROOT"] + "/archive-timed",
         "runs_phase3_timed": os.environ["AZ_ROOT"] + "/runs/phase3-timed"}
gone = {k: (not fs.exists(v)) for k, v in paths.items()}
out = {"step": "C-cleanup", "status": "ok", "pass": all(gone.values()),
       "metrics": {"deleted": gone, "paths": paths},
       "expected": {"deleted": {k: True for k in paths}}, "error": None}
print("FSD_RESULT_BEGIN"); print(json.dumps(out, indent=2)); print("FSD_RESULT_END")
with open(f"{os.environ['OUT42']}/stepC_result.json", "w") as f:
    json.dump(out, f, indent=2)
PY
.venv/bin/python "$OUT42/stepC.py"
```
- **PASS if:** both `deleted` values are `true`.
- **The verified `archive/` prefix and `runs/phase3` must be untouched** — the delete paths above
  both end in `-timed`. If you typed one wrong, stop and say so before running anything else.

## Success criteria (`_result.json`)
Three files: `stepA_result.json`, `stepB_result.json`, `stepC_result.json`, each
`{step, status, pass, metrics, expected, error}`. **Paste all three** (not the logs). The two
numbers the report needs are `metrics.wall_seconds` from A and B; everything else is the evidence
that they measured cold, comparable work.

## Stop / observe
- Progress: the driver polls every 30 s; watch the jobs in AML Studio (the experiment names are
  `fsd-phase3-timed` and `fsd-download-phase3-archive-timed`).
- Abort: Ctrl-C the driver, then cancel the jobs in Studio to release nodes. A partial Step B leaves
  files under `archive-timed/` — Step C still cleans them up.
- Cost: two cluster allocations of up to 16 × 16-vCPU nodes, ~6–8 min each, plus a **418.0 GB**
  second copy of the archive on blob until Step C runs.
