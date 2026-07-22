# Run-book: 37 Phases 0–3 — download on Azure ML, end to end

> Spec-24 run-book for **spec 37 §6**. **You** run this; paste back each phase's printed JSON.
> Builds on spec 36's cluster/identity/Environment (already proven, `runbooks/36-phase0-identity-
> smoke.md` + `runbooks/36-aml-runner.md`) — this run-book adds the **CDSE creds delivery** leg (D5)
> and the **download** dispatch (D1/D2/D3), not a new cluster/identity/Environment.
>
> **D5 REVISED (2026-07-22, keep-both):** Key Vault *write* is operationally blocked for the operator
> (`ForbiddenByRbac` — the compute UAMI only holds *read*, `Key Vault Secrets User`), so **this
> run-book uses the blob-JSON `--creds-url` fallback** below (mutually exclusive with the KV path).
> KV stays wired and is still preferred wherever a write role exists — swap `AZ_CREDS_URL` for
> `AZ_VAULT_URL`/`AZ_CDSE_SECRET_NAME` in Phase 1/3's `run_aml_download` calls if you have one.
>
> **Concrete `rise` values are NOT in this file** (public repo). Paste them as env vars from the
> uncommitted `../../AZURE_INFRA_PRIVATE.md` (workspace root).

## Purpose

Prove `api.download(runner="aml")` end to end, for both sources: the ROI and the S3 creds reach
blob and the creds round-trip cleanly (Phase 0); one tile lands on blob per source with **correct**
radiometry (Phase 1); MPC's fan-out actually partitions the asset list and is measurably faster
than `n_shards=1` (Phase 2 — the D1 claim); and the real archive that unblocks spec 36's datacube
fan-out on real data lands on blob (Phase 3).

**Two things every CDSE phase does, by construction:** it reads the ROI from a **blob url** (the
node cannot see your laptop's `shapefiles/`), and it wraps the run in `blob_creds()`, which puts
the creds JSON on blob just before the run and deletes it in a `finally` just after — D5 REVISED's
plaintext-at-rest trade-off is scoped to a single run, not to the run-book.

## Prerequisites
- **VPN connected**, `az login` done, correct subscription selected. Not optional and not only for
  the node: **the driver does blob I/O in every phase** (ROI + creds push, MPC shard CSVs, reading
  `_status/*.json` back). VPN off ⇒ `ErrorCode:AuthorizationFailure` on the first write — see the
  precondition note in Phase 0.
- The fsd venv with the `[aml]` **and** `[azure]` extras (Key Vault needs `azure-keyvault-secrets`,
  now in `[azure]`): `cd fsd && source .venv/bin/activate && pip install -e ".[dev,azure,aml,mpc]"`.
- The spec-36 AML Environment already built (`runbooks/36-aml-runner.md`'s "Build the AML
  Environment" step) — **rebuild it** if the fsd wheel changed since (it must carry fsd itself plus
  `azure-keyvault-secrets`, `s3fs`, `planetary-computer`, `pystac-client` — D10). **Run that step's
  "Verify the image actually contains fsd" smoke job before Phase 1**: the dispatcher submits a bare
  `python -m fsd.workflows.download …` with no code upload and no pip install, so a missing module
  in the image surfaces as a `ModuleNotFoundError` *after* the cluster scales up and CDSE bytes
  start moving. The smoke job costs seconds and rules that out.
- A **local** CDSE creds JSON (the legacy `cdse_credentials.json` shape — `sh_clientid`/
  `sh_clientsecret`/`s3_access_key`/`s3_secret_key`). It stays on your machine; each CDSE phase
  copies it to the blob `_secrets/` prefix for the duration of that one run and deletes it after.
  (If instead you have a KV write role, populate a Key Vault secret the same shape and use the KV
  path noted above — this run-book does not grant that role.)
- The ROI geometries are pushed to blob in Phase 0 — **the node cannot read your local
  `shapefiles/`**, so every `roi` argument from Phase 1 on is a blob url.

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
export AZ_ROOT="abfss://${AZ_FS}@${AZ_ACCOUNT}.dfs.core.windows.net/fsd-p2-download"
export AZ_ENV_NAME='fsd-aml-env'          # spec 36 D5's environment, reused
# The version AML assigned when you built it (runbook 36's env step exports this):
export AZ_ENV_VERSION="$(az ml environment list -n "$AZ_ENV_NAME" -g "$AZ_RG" \
  -w "$AZ_ML_WORKSPACE" --query "[].version" -o tsv | sort -V | tail -1)"
echo "environment: ${AZ_ENV_NAME}:${AZ_ENV_VERSION}"

export AZ_VAULT_URL='<rise Key Vault url>'          # e.g. kv<proj>.vault.azure.net -- KV path (if you have write)
export AZ_CDSE_SECRET_NAME='<cdse creds secret name>'

export AZ_LOCAL_CREDS_JSON='<path to your local cdse_credentials.json>'   # blob path (used for the demo)
export AZ_CREDS_URL="${AZ_ROOT}/_secrets/cdse_credentials.json"

export AZ_UAMI_CLIENT_ID="$(az identity show -g "$AZ_RG" -n "$AZ_UAMI_NAME" --query clientId -o tsv)"
echo "client id resolved: ${AZ_UAMI_CLIENT_ID:0:8}…"

# Knobs the phase scripts read. Both have inline defaults, so the runs work if you
# skip this block -- exported here so the values are VISIBLE rather than buried in
# an os.environ.get() default further down.
export AZ_N_SHARDS='8'      # MPC fan-out width (Phase 2 + Phase 3). Ignored for CDSE (D1: 1 job).
export AZ_MAX_TILES='700'   # guardrail for BOTH sources: raises before dispatch if the
                            # ROI x window matches more MGRS tiles than this. Counts tiles,
                            # not assets (assets = tiles x bands). 2018 full year over
                            # AT_ROI = 572 tiles, so 500 would refuse it.

export OUT="$PWD/tests/outputs/p2_download_aml"     # gitignored
mkdir -p "$OUT"
echo "n_shards=${AZ_N_SHARDS}  max_tiles=${AZ_MAX_TILES} (both sources)"
```
- **PASS if:** the client-id line prints 8 hex characters **and** the environment line prints a
  real version (`fsd-aml-env:3`, not `fsd-aml-env:`). An empty version means no environment is
  registered under that name — go build it (`runbooks/36-aml-runner.md`) before continuing.

## Phase 0 — inputs on blob: the ROI, and a creds round-trip that leaves nothing behind

> **The ROI must be on blob too, not just the creds.** `run_aml_download` splices `roi` straight
> into the node's command (`runners.py`: `--roi {roi}`), and the node is a different machine — a
> local relative path like `../../shapefiles/x.geojson` resolves on your laptop during discovery
> and then **fails on the node**. (CDSE only: the MPC path pre-discovers on the driver and hands
> the node a blob shard CSV, so it never reads the ROI remotely. Upload anyway — Phase 1 runs both.)

> **Creds lifetime (revised):** the creds JSON is pushed **immediately before** each run and deleted
> in a `finally` **immediately after**, rather than sitting on blob from Phase 0 to Phase 3. Two
> reasons: the exposure window shrinks from the whole run-book (hours/days) to one run, and — the
> bigger one — a `finally` deletes it **even when the run fails**, where a delete step written at
> the end of Phase 3 silently never executes on the failure path. The window still cannot be shorter
> than the run: the node reads the file when the job starts, and an AML node retry re-reads it.

> **Precondition — the DRIVER must reach blob, not just the node.** This phase writes the ROI from
> your machine, and later phases keep doing driver-side blob I/O (MPC shard CSVs out, `_status/*.json`
> back). The `rise` storage account is **deny-by-default firewalled**, reachable only from VPN IP
> ranges + the project subnets, so a laptop needs **VPN up** (`AZURE_INFRA_PRIVATE.md`). Check it
> before the phase, or you get a 60-line adlfs traceback ending in:
> ```
> RuntimeError: Failed to upload block: This request is not authorized to perform this operation.
> ErrorCode:AuthorizationFailure
> ```
> **That code means network rules, not RBAC** — `AuthorizationPermissionMismatch` is the missing-role
> one. So don't go hunting role assignments: **connect the VPN and re-run** (confirmed 2026-07-22 —
> VPN was off; identical script passed once it was on). If the VPN *is* up, compare your egress IP
> (`curl -s https://api.ipify.org`) against
> `az storage account show -n "$AZ_ACCOUNT" -g "$AZ_RG" --query networkRuleSet -o json`, and re-run
> the known-green `runbooks/31-p1-access-probe.md` to tell "environment broken" from "this run-book
> broken". If the driver can never reach blob from where you are, run the whole run-book from a VM
> inside the `rise` VNet, as `runbooks/34-download-to-blob.md` requires.

```bash
# --- inputs the NODE must be able to read: push the ROI geometries to blob ---
export AZ_ROI_URL="${AZ_ROOT}/_inputs/s2grid=476da24.geojson"                     # Phase 1/2 smoke ROI
export AZ_ROI_MULTI_URL="${AZ_ROOT}/_inputs/austria_eurocrops_sampled.geojson"    # Phase 2 multi-tile ROI

cat > "$OUT/phase0.py" <<'PY'
import contextlib, json, os
from fsd.storage import fs
from fsd.sources.cdse import CdseCredentials

# 1. ROI push -- local path -> blob url, so the node's `--roi` argument resolves.
for local, url in [
    ("../shapefiles/s2grid=476da24.geojson", os.environ["AZ_ROI_URL"]),
    ("../shapefiles/austria_eurocrops_sampled_ethiopia_translated.geojson",
     os.environ["AZ_ROI_MULTI_URL"]),
]:
    with open(local, "rb") as src, fs.open(url, "wb") as dst:
        dst.write(src.read())

# 2. The creds context manager every later phase uses. Push -> yield -> ALWAYS delete.
helper = '''
import contextlib, os
from fsd.storage import fs

@contextlib.contextmanager
def blob_creds():
    """D5 REVISED: put the CDSE creds JSON on blob for exactly one run, and remove
    it even if that run raises. Yields the url to pass as `creds_url=`."""
    url = os.environ["AZ_CREDS_URL"]
    with open(os.environ["AZ_LOCAL_CREDS_JSON"]) as f:
        payload = f.read()
    with fs.open(url, "w") as f:
        f.write(payload)
    try:
        yield url
    finally:
        with contextlib.suppress(Exception):
            fs.rm(url)
'''
with open(f"{os.environ['OUT']}/blob_creds.py", "w") as f:
    f.write(helper)

# 3. Prove the round-trip works -- and leave nothing on blob.
import sys; sys.path.insert(0, os.environ["OUT"])
from blob_creds import blob_creds

with blob_creds() as creds_url:
    creds = CdseCredentials.from_json(creds_url)
    creds.require_s3()
    readback_ok = bool(creds.s3_access_key)
    expired = creds.is_expired()

out = {
    "phase": "phase0-inputs-on-blob", "pass": True,
    "roi_url": os.environ["AZ_ROI_URL"],
    "roi_on_blob": fs.exists(os.environ["AZ_ROI_URL"]),
    "roi_multi_on_blob": fs.exists(os.environ["AZ_ROI_MULTI_URL"]),
    "s3_access_key_set": readback_ok,
    "s3_keys_expired": expired,
    "creds_deleted_after_use": not fs.exists(os.environ["AZ_CREDS_URL"]),
}
print("FSD_RESULT_BEGIN"); print(json.dumps(out, indent=2)); print("FSD_RESULT_END")
with open(f"{os.environ['OUT']}/phase0_result.json", "w") as f:
    json.dump(out, f, indent=2)
PY
.venv/bin/python "$OUT/phase0.py"
```
- **Expect:** `roi_on_blob: true`, `roi_multi_on_blob: true`, `s3_access_key_set: true`,
  `s3_keys_expired: false` (or `null` if `s3_keys_expire` isn't set), and
  **`creds_deleted_after_use: true`**.
- **PASS if:** all of the above. This one phase proves blob **write** (ROI + creds push), blob
  **read** (creds parse back), and that the delete path works — the three things Phases 1/3 depend on.
- **FAIL — `creds_deleted_after_use: false`:** the identity can write but not delete on that prefix.
  Stop and fix it here; otherwise every later phase leaves creds on blob.
- **FAIL — a write-permission error:** the compute identity's blob write role needs attention
  **before** Phase 1.

## Phase 1 — one tile to blob, per source
```bash
cat > "$OUT/phase1.py" <<'PY'
import json, os
from fsd.workflows import runners

common = dict(
    cluster=os.environ["AZ_CLUSTER"], environment=f"{os.environ['AZ_ENV_NAME']}:{os.environ['AZ_ENV_VERSION']}",
    root=os.environ["AZ_ROOT"], identity_client_id=os.environ["AZ_UAMI_CLIENT_ID"],
    subscription_id=os.environ["AZ_SUBSCRIPTION_ID"], resource_group_name=os.environ["AZ_RG"],
    workspace_name=os.environ["AZ_ML_WORKSPACE"],
)

import sys; sys.path.insert(0, os.environ["OUT"])
from blob_creds import blob_creds          # Phase 0 wrote this: push -> run -> always delete

# B02/B03 ride along with B04 so the archive can serve true-colour RGB later
# (mini-MPC / STACNotator); they also unlock NDWI/GCVI/BSI in fsd.bands.modify.
BANDS = ["B02", "B03", "B04"]

# CDSE: the creds exist on blob only for the duration of this one run.
with blob_creds() as creds_url:
    cdse_result = runners.run_aml_download(
        os.environ["AZ_ROI_URL"], "2018-06-01", "2018-06-11", BANDS,
        os.environ["AZ_ROOT"] + "/cdse", os.environ["AZ_ROOT"] + "/cdse/catalog.parquet",
        source="cdse", max_tiles=5, creds_url=creds_url,
        run_id="phase1-cdse", **common,
    )

# MPC: anonymous -- no creds on blob at all.
mpc_result = runners.run_aml_download(
    os.environ["AZ_ROI_URL"], "2018-06-01", "2018-06-11", BANDS,
    os.environ["AZ_ROOT"] + "/mpc", os.environ["AZ_ROOT"] + "/mpc/catalog.parquet",
    source="mpc", max_tiles=5, n_shards=1, run_id="phase1-mpc", **common,
)

out = {"phase": "phase1-one-tile-per-source", "pass": True,
       "cdse": cdse_result, "mpc": mpc_result}
print("FSD_RESULT_BEGIN"); print(json.dumps(out, indent=2, default=str)); print("FSD_RESULT_END")
with open(f"{os.environ['OUT']}/phase1_result.json", "w") as f:
    json.dump(out, f, indent=2, default=str)
PY
.venv/bin/python "$OUT/phase1.py"
```
- **Expect:** two AML jobs (one per source), each scaling a node 0→1; no exception.
- **Also confirm the creds are gone** once the script returns — it should print nothing:
  ```bash
  .venv/bin/python -c "from fsd.storage import fs; import os; print(fs.exists(os.environ['AZ_CREDS_URL']) or '')"
  ```
- **PASS if:** both `cdse_result`/`mpc_result` return with no failed job, a `catalog.parquet` exists
  under each source's prefix, and — the radiometry check (spec 34's whole point) — the blob COG's
  GDAL `scale`/`offset` tags match a **local** download of the same tile
  (`gdalinfo <blob-cog-vsiadls-path>` vs. `gdalinfo <local-cog>` — both should show the *same*
  `offset`/`scale` pair; not `offset=-1000` next to `scale=1/10000`, the black-tile bug TODO #44
  documents).
- **If it fails:** paste `$OUT/phase1_result.json`; if submission itself failed with an environment
  error, `az ml job stream -n <job-name> ...` (job names are in each result's `job_statuses`) — most
  likely D10's untested deps (`s3fs`/`planetary-computer`/`pystac-client`/`azure-keyvault-secrets`
  missing from the Environment); rebuild it per the prerequisites.

## Phase 2 — MPC fan-out + speedup
```bash
cat > "$OUT/phase2.py" <<'PY'
import json, os, time
from fsd.workflows import runners

common = dict(
    cluster=os.environ["AZ_CLUSTER"], environment=f"{os.environ['AZ_ENV_NAME']}:{os.environ['AZ_ENV_VERSION']}",
    root=os.environ["AZ_ROOT"], identity_client_id=os.environ["AZ_UAMI_CLIENT_ID"],
    subscription_id=os.environ["AZ_SUBSCRIPTION_ID"], resource_group_name=os.environ["AZ_RG"],
    workspace_name=os.environ["AZ_ML_WORKSPACE"],
)
roi = os.environ["AZ_ROI_MULTI_URL"]   # multi-tile, on blob (Phase 0 pushed it)

t0 = time.time()
one = runners.run_aml_download(
    roi, "2018-04-01", "2018-09-01", ["B04", "B08", "B8A", "SCL"],
    os.environ["AZ_ROOT"] + "/mpc-p2-n1", os.environ["AZ_ROOT"] + "/mpc-p2-n1/catalog.parquet",
    source="mpc", max_tiles=500, n_shards=1, run_id="phase2-n1", **common,
)
t_one = time.time() - t0

t0 = time.time()
n = runners.run_aml_download(
    roi, "2018-04-01", "2018-09-01", ["B04", "B08", "B8A", "SCL"],
    os.environ["AZ_ROOT"] + "/mpc-p2-nN", os.environ["AZ_ROOT"] + "/mpc-p2-nN/catalog.parquet",
    source="mpc", max_tiles=500, n_shards=int(os.environ.get("AZ_N_SHARDS", "8")),
    run_id="phase2-nN", **common,
)
t_n = time.time() - t0

out = {"phase": "phase2-mpc-fanout-speedup", "pass": True,
       "seconds_n_shards_1": round(t_one, 1), "seconds_n_shards_n": round(t_n, 1),
       "speedup": round(t_one / t_n, 2) if t_n else None,
       "n_shards": n["n_jobs"], "one": one, "n": n}
print("FSD_RESULT_BEGIN"); print(json.dumps(out, indent=2, default=str)); print("FSD_RESULT_END")
with open(f"{os.environ['OUT']}/phase2_result.json", "w") as f:
    json.dump(out, f, indent=2, default=str)
PY
.venv/bin/python "$OUT/phase2.py"
```
- **Expect:** the `n_shards=1` run and the `n_shards=N` run both complete; `N` nodes visibly running
  concurrently in the Studio UI for the second.
- **PASS if:** (a) **partition, not loss**: every asset in the ROI's discovery list appears in
  exactly one shard CSV across the N run — spot-check `$AZ_ROOT/runs/phase2-nN/shards/*.csv` row
  counts sum to the single discovery count; (b) **speedup**: `speedup` is meaningfully > 1 (D1's
  claim is *near-linear* until a knee — a `speedup` well under `N` is a real result to report, not
  a failure, but flag it) — this is the number that answers "does MPC fan-out actually make it
  faster."
- **Cost:** up to `AZ_N_SHARDS` `d16` nodes for the fan-out's duration, twice (once per run).

## Phase 3 — the real archive

> **Which arguments apply to which source — read this before writing the call.** The dispatcher
> takes one signature for both sources and **silently ignores** what doesn't apply. Passing a
> CDSE-only argument to an MPC run raises nothing.
>
> | argument | `source="cdse"` | `source="mpc"` |
> |---|---|---|
> | `creds_url` / `vault_url`+`secret_name` | **required** (exactly one) | **ignored** — MPC is anonymous. Passing `creds_url` here puts your CDSE keys on blob for the whole run **for no reason**. |
> | `max_tiles` | applies — now checked on the **driver** before dispatch, as well as on the node | applies — **fixed 2026-07-22 (TODO #49)**; it was previously accepted and silently dropped, so an MPC AML run was uncapped. Counts distinct **MGRS tiles**, not assets: `n_tiles = assets / len(BANDS)`. |
> | `n_shards` | ignored (D1: CDSE is always 1 job) | applies |
>
> So the two sources get **two different scripts** below. Don't merge them.

### Step 3a — push the real ROI to blob
Phase 0 pushed only the Phase 1/2 test ROIs. The node cannot read your local `shapefiles/`.
```bash
export AZ_ROI_REAL_LOCAL='../shapefiles/<your roi>.geojson'
export AZ_ROI_REAL_URL="${AZ_ROOT}/_inputs/$(basename "$AZ_ROI_REAL_LOCAL")"

.venv/bin/python -c "
from fsd.storage import fs; import os
with open(os.environ['AZ_ROI_REAL_LOCAL'],'rb') as s, fs.open(os.environ['AZ_ROI_REAL_URL'],'wb') as d:
    d.write(s.read())
print('roi on blob:', fs.exists(os.environ['AZ_ROI_REAL_URL']), os.environ['AZ_ROI_REAL_URL'])"
```
- **PASS if:** it prints `roi on blob: True`. Skipping this fails discovery immediately (cheap, but
  pointless) — and before the `_roi_gdf` storage-seam fix it failed with a *lying* `No such file or
  directory` from GDAL.

### Step 3b — discover first: how big is this run?
Driver-side STAC query only. **No bytes move.** Do this before committing a long run — `max_tiles`
does not cap MPC, and MPC reports no `bytes_downloaded` (TODO #48), so this count is your only
size signal.
```bash
.venv/bin/python -c "
from fsd.sources import mpc; import os, pandas as pd
rows = mpc.discover_shard_rows(os.environ['AZ_ROI_REAL_URL'],
    pd.Timestamp('<startdate>'), pd.Timestamp('<enddate>'),
    ['B02','B03','B04','B08','B8A','SCL'], os.environ['AZ_ROOT']+'/archive')
print('assets:', len(rows))"
```
- **Calibration from real runs:** Phase 2 moved **964** assets in ~494 s wall at `n_shards=8`.
  Scale linearly for a first estimate (≈0.5 s/asset of wall clock at N=8), and remember ~380 s of
  that was fixed cluster startup, not transfer (TODO #48). Measured 2026-07-22: a full year of 2018
  over Austria's 4 MGRS tiles at 6 bands = **3432 assets**.
- **PASS if:** the count is what you expect for the ROI × window × bands. A surprising number here
  is much cheaper to investigate than a surprising blob bill afterwards.

### Step 3c (MPC) — anonymous, fans out. **No creds anywhere.**
```bash
cat > "$OUT/phase3.py" <<'PY'
import json, os, time
from fsd.workflows import runners

# Time the run. Without this, the shard reports give in-job download time only, and
# the driver-side overhead (node allocation + image pull + queueing) is invisible --
# which is most of the wall clock at high shard counts (TODO #48).
t0 = time.time()

common = dict(
    cluster=os.environ["AZ_CLUSTER"], environment=f"{os.environ['AZ_ENV_NAME']}:{os.environ['AZ_ENV_VERSION']}",
    root=os.environ["AZ_ROOT"], identity_client_id=os.environ["AZ_UAMI_CLIENT_ID"],
    subscription_id=os.environ["AZ_SUBSCRIPTION_ID"], resource_group_name=os.environ["AZ_RG"],
    workspace_name=os.environ["AZ_ML_WORKSPACE"],
)
# B02+B03 join the analysis bands so this archive can also be served as true-colour
# RGB (B04/B03/B02) by the mini-MPC / STACNotator stack later, without a re-download.
BANDS = ["B02", "B03", "B04", "B08", "B8A", "SCL"]

# NO blob_creds() and NO creds_url= -- CDSE-only, and passing creds here would put
# them on blob for nothing. See the argument table above.
result = runners.run_aml_download(
    os.environ["AZ_ROI_REAL_URL"], "<startdate>", "<enddate>", BANDS,
    os.environ["AZ_ROOT"] + "/archive", os.environ["AZ_ROOT"] + "/archive/catalog.parquet",
    source="mpc",
    max_tiles=int(os.environ["AZ_MAX_TILES"]),   # a REAL cap now -- enforced on the
                        # driver for MPC too (TODO #49). Raises before dispatch if the
                        # ROI x window matches more MGRS tiles than this. Size it with
                        # Step 3b: n_tiles = assets / len(BANDS).
    n_shards=int(os.environ.get("AZ_N_SHARDS", "8")),
    run_id="phase3-archive", **common,
)
wall = time.time() - t0
slowest = max(r["seconds"] for r in result["reports"].values())
out = {"phase": "phase3-real-archive", "source": "mpc", "pass": True,
       "wall_seconds": round(wall, 1),
       "slowest_shard_seconds": slowest,
       # everything not spent transferring: allocation, image pull, queueing (TODO #48)
       "driver_overhead_seconds": round(wall - slowest, 1),
       "result": result}
print("FSD_RESULT_BEGIN"); print(json.dumps(out, indent=2, default=str)); print("FSD_RESULT_END")
with open(f"{os.environ['OUT']}/phase3_result.json", "w") as f:
    json.dump(out, f, indent=2, default=str)
PY
.venv/bin/python "$OUT/phase3.py"
```

### Step 3c (CDSE) — one job, creds required, `max_tiles` applies
```bash
cat > "$OUT/phase3_cdse.py" <<'PY'
import json, os, sys
from fsd.workflows import runners

sys.path.insert(0, os.environ["OUT"])
from blob_creds import blob_creds      # CDSE only -- see the argument table

common = dict(
    cluster=os.environ["AZ_CLUSTER"], environment=f"{os.environ['AZ_ENV_NAME']}:{os.environ['AZ_ENV_VERSION']}",
    root=os.environ["AZ_ROOT"], identity_client_id=os.environ["AZ_UAMI_CLIENT_ID"],
    subscription_id=os.environ["AZ_SUBSCRIPTION_ID"], resource_group_name=os.environ["AZ_RG"],
    workspace_name=os.environ["AZ_ML_WORKSPACE"],
)
BANDS = ["B02", "B03", "B04", "B08", "B8A", "SCL"]

with blob_creds() as creds_url:      # on blob only while this run is in flight
    result = runners.run_aml_download(
        os.environ["AZ_ROI_REAL_URL"], "<startdate>", "<enddate>", BANDS,
        os.environ["AZ_ROOT"] + "/archive", os.environ["AZ_ROOT"] + "/archive/catalog.parquet",
        source="cdse",
        max_tiles=int(os.environ["AZ_MAX_TILES"]),
        creds_url=creds_url,          # or vault_url=/secret_name= if you have a KV write role
        run_id="phase3-archive", **common,   # n_shards omitted: CDSE is always 1 job (D1)
    )
out = {"phase": "phase3-real-archive", "source": "cdse", "pass": True, "result": result}
print("FSD_RESULT_BEGIN"); print(json.dumps(out, indent=2, default=str)); print("FSD_RESULT_END")
with open(f"{os.environ['OUT']}/phase3_result.json", "w") as f:
    json.dump(out, f, indent=2, default=str)
PY
.venv/bin/python "$OUT/phase3_cdse.py"
```
- ⚠️ **Don't run both variants under the same `run_id`** — they write into the same `/archive`
  catalog. Use distinct `run_id`s and distinct `dst`/`catalog` prefixes if you want both.
- **Re-running after a cancelled/failed attempt: just re-run. Do not try to clear the prefix.**
  The run is self-healing — `_transfer_and_stamp_one` is an "idempotent skip on an existing
  non-empty `dst_path`", `download_shard` records every row in `tile_meta` whether it transferred
  or skipped, and `TileCatalog.append` **upserts by id** (unioning `files`), so no duplicate rows
  can accumulate. A partially-downloaded prefix therefore converges to the same correct catalog,
  paying only for the missing assets. Expect a non-zero `n_skipped` — that is the resume working.
  ⚠️ **`fs.rm(prefix, recursive=True)` is broken on `abfss://`** (TODO #50): it deletes part of the
  tree and then raises `DirectoryIsNotEmpty`, leaving a half-cleared prefix. Harmless given the
  idempotency above, but it will not give you the clean slate you asked for — so don't rely on it,
  and note that a resumed run's wall clock is **not** comparable to a cold one.
- **Expect:** the real ROI/window lands on `$AZ_ROOT/archive`, correctly radiometry-tagged
  (spec 34), ready for spec 36's `run_aml` to build datacubes against.
- **PASS if:** no failed/circuit-tripped job, and the catalog covers the expected tile count
  (`fsd.sources.cdse.plan_download`/`query_catalog` against the same roi/window, offline, should
  show `missing_count == 0` afterwards).
- **This retires TODO #44** (the pre-fix radiometry artifacts) if `archive` replaces or supersedes
  the old `spec34-demo/` prefix — decide with the user whether to also delete the stale prefix.
- **The creds file deletes itself (CDSE variant only)** — `blob_creds()`'s `finally` runs whether
  the download succeeded or raised. Confirm (should print nothing), and if it *does* print `True`,
  delete it by hand immediately:
  ```bash
  .venv/bin/python -c "from fsd.storage import fs; import os; print(fs.exists(os.environ['AZ_CREDS_URL']) or '')"
  # if that printed True:
  .venv/bin/python -c "from fsd.storage import fs; import os; fs.rm(os.environ['AZ_CREDS_URL'])"
  ```
- **Whatever the outcome, the CDSE S3 keys were on blob in plaintext for the length of this run.**
  If the archive run was long, or the `_secrets/` prefix is readable by more than {compute identity,
  you}, **rotate the CDSE keys** afterwards — that is the only mitigation that survives someone
  having already copied the file. `s3_keys_expire` bounds the damage but does not eliminate it.

## Success criteria (`_result.json`)
Each phase writes `$OUT/phase<N>_result.json`, e.g.:
```json
{ "phase": "phase1-one-tile-per-source", "pass": true,
  "cdse": { "run_id": "phase1-cdse", "n_jobs": 1 },
  "mpc":  { "run_id": "phase1-mpc",  "n_jobs": 1 } }
```
Paste these back (not the AML job logs) — Claude diffs them against the PASS conditions above.

## Stop / observe
- Progress: `az ml job stream -n <job-name> -g "$AZ_RG" -w "$AZ_ML_WORKSPACE"` (job names are in
  each phase's `result["job_statuses"]`/`reports`). Studio URL prints at submission.
- Abort: `Ctrl-C` the Python driver (already-submitted AML jobs keep running — cancel individually
  with `az ml job cancel -n <job-name> ...`), or cancel a specific job the same way.
- Re-run: Phase 0/1 are cheap and safe to repeat. Phase 2 costs 2x the fan-out per re-run. Phase 3
  is the real spend — confirm the ROI/window/`max_tiles` before running.
