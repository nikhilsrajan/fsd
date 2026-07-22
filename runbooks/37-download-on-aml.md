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

Prove `api.download(runner="aml")` end to end, for both sources: a node reads its S3 creds from
blob (or Key Vault) and authenticates through fsd's storage seam (Phase 0); one tile lands on blob
per source with **correct** radiometry (Phase 1); MPC's fan-out actually partitions the asset list
and is measurably faster than `n_shards=1` (Phase 2 — the D1 claim); and the real archive that
unblocks spec 36's datacube fan-out on real data lands on blob (Phase 3, which also **deletes the
blob creds file** once the run completes — D5 REVISED's accepted plaintext-at-rest trade-off is
scoped to the run's duration only).

## Prerequisites
- **VPN connected**, `az login` done, correct subscription selected.
- The fsd venv with the `[aml]` **and** `[azure]` extras (Key Vault needs `azure-keyvault-secrets`,
  now in `[azure]`): `cd fsd && source .venv/bin/activate && pip install -e ".[dev,azure,aml,mpc]"`.
- The spec-36 AML Environment already built (`runbooks/36-aml-runner.md`'s "Build the AML
  Environment" step) — **rebuild it** if the fsd wheel changed since (it must carry
  `azure-keyvault-secrets`, `s3fs`, `planetary-computer`, `pystac-client` — D10; verify in Phase 1).
- A **local** CDSE creds JSON (the legacy `cdse_credentials.json` shape — `sh_clientid`/
  `sh_clientsecret`/`s3_access_key`/`s3_secret_key`) to push to the blob `_secrets/` prefix in
  Phase 0. (If instead you have a KV write role, populate a Key Vault secret the same shape and use
  the KV path noted above — this run-book does not grant that role.)

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

export AZ_VAULT_URL='<rise Key Vault url>'          # e.g. kv<proj>.vault.azure.net -- KV path (if you have write)
export AZ_CDSE_SECRET_NAME='<cdse creds secret name>'

export AZ_LOCAL_CREDS_JSON='<path to your local cdse_credentials.json>'   # blob path (used for the demo)
export AZ_CREDS_URL="${AZ_ROOT}/_secrets/cdse_credentials.json"

export AZ_UAMI_CLIENT_ID="$(az identity show -g "$AZ_RG" -n "$AZ_UAMI_NAME" --query clientId -o tsv)"
echo "client id resolved: ${AZ_UAMI_CLIENT_ID:0:8}…"

export OUT="$PWD/tests/outputs/p2_download_aml"     # gitignored
mkdir -p "$OUT"
```
- **PASS if:** the client-id line prints 8 hex characters.

## Phase 0 — identity + CDSE creds (blob `_secrets/` push, D5 REVISED)
```bash
cat > "$OUT/phase0.py" <<'PY'
import json, os
from fsd.storage import fs
from fsd.sources.cdse import CdseCredentials

# Push the local CDSE creds JSON to the blob _secrets/ prefix (D5 REVISED: the
# operator has blob write but no KV write). Same identity spec 36 D4 proved for
# blob authenticates this write; the node reads it back via the same identity
# in Phase 1's job (fs.open, CdseCredentials.from_json -- no new read code).
with open(os.environ["AZ_LOCAL_CREDS_JSON"]) as f:
    local_json = f.read()
with fs.open(os.environ["AZ_CREDS_URL"], "w") as f:
    f.write(local_json)

creds = CdseCredentials.from_json(os.environ["AZ_CREDS_URL"])
creds.require_s3()

out = {
    "phase": "phase0-identity-and-blob-creds", "pass": True,
    "creds_url": os.environ["AZ_CREDS_URL"],
    "s3_access_key_set": bool(creds.s3_access_key),
    "s3_keys_expired": creds.is_expired(),
}
print("FSD_RESULT_BEGIN"); print(json.dumps(out, indent=2)); print("FSD_RESULT_END")
with open(f"{os.environ['OUT']}/phase0_result.json", "w") as f:
    json.dump(out, f, indent=2)
PY
.venv/bin/python "$OUT/phase0.py"
```
- **Expect:** `s3_access_key_set: true`, `s3_keys_expired: false` (or `null` if `s3_keys_expire`
  isn't set in the JSON).
- **PASS if:** no exception and the above. A write-permission error here means the compute
  identity's blob write role needs attention **before** Phase 1. **Note the plaintext-at-rest
  trade-off** (`LIMITATIONS.md`): the creds file now sits on blob until Phase 3 deletes it.

## Phase 1 — one tile to blob, per source
```bash
cat > "$OUT/phase1.py" <<'PY'
import json, os
from fsd.workflows import runners

common = dict(
    cluster=os.environ["AZ_CLUSTER"], environment=f"{os.environ['AZ_ENV_NAME']}:1",
    root=os.environ["AZ_ROOT"], identity_client_id=os.environ["AZ_UAMI_CLIENT_ID"],
    subscription_id=os.environ["AZ_SUBSCRIPTION_ID"], resource_group_name=os.environ["AZ_RG"],
    workspace_name=os.environ["AZ_ML_WORKSPACE"],
)

cdse_result = runners.run_aml_download(
    "../../shapefiles/s2grid=476da24.geojson", "2018-06-01", "2018-06-11", ["B04"],
    os.environ["AZ_ROOT"] + "/cdse", os.environ["AZ_ROOT"] + "/cdse/catalog.parquet",
    source="cdse", max_tiles=5, creds_url=os.environ["AZ_CREDS_URL"],
    run_id="phase1-cdse", **common,
)
mpc_result = runners.run_aml_download(
    "../../shapefiles/s2grid=476da24.geojson", "2018-06-01", "2018-06-11", ["B04"],
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
    cluster=os.environ["AZ_CLUSTER"], environment=f"{os.environ['AZ_ENV_NAME']}:1",
    root=os.environ["AZ_ROOT"], identity_client_id=os.environ["AZ_UAMI_CLIENT_ID"],
    subscription_id=os.environ["AZ_SUBSCRIPTION_ID"], resource_group_name=os.environ["AZ_RG"],
    workspace_name=os.environ["AZ_ML_WORKSPACE"],
)
roi = "../../shapefiles/austria_eurocrops_sampled_ethiopia_translated.geojson"  # multi-tile

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
```bash
cat > "$OUT/phase3.py" <<'PY'
import json, os
from fsd.workflows import runners

common = dict(
    cluster=os.environ["AZ_CLUSTER"], environment=f"{os.environ['AZ_ENV_NAME']}:1",
    root=os.environ["AZ_ROOT"], identity_client_id=os.environ["AZ_UAMI_CLIENT_ID"],
    subscription_id=os.environ["AZ_SUBSCRIPTION_ID"], resource_group_name=os.environ["AZ_RG"],
    workspace_name=os.environ["AZ_ML_WORKSPACE"],
)
# Fill in the REAL roi/date-window/bands you need on blob (not the Phase 1/2 smoke ROI).
roi = "<the real roi geojson path>"
result = runners.run_aml_download(
    roi, "<startdate>", "<enddate>", ["B04", "B08", "B8A", "SCL"],
    os.environ["AZ_ROOT"] + "/archive", os.environ["AZ_ROOT"] + "/archive/catalog.parquet",
    source="<cdse-or-mpc>", max_tiles=int(os.environ.get("AZ_MAX_TILES", "500")),
    n_shards=int(os.environ.get("AZ_N_SHARDS", "8")),  # ignored for source="cdse" (D1: always 1)
    creds_url=os.environ.get("AZ_CREDS_URL"),  # or vault_url=/secret_name= if you have a KV write role
    run_id="phase3-archive", **common,
)
out = {"phase": "phase3-real-archive", "pass": True, "result": result}
print("FSD_RESULT_BEGIN"); print(json.dumps(out, indent=2, default=str)); print("FSD_RESULT_END")
with open(f"{os.environ['OUT']}/phase3_result.json", "w") as f:
    json.dump(out, f, indent=2, default=str)
PY
.venv/bin/python "$OUT/phase3.py"
```
- **Expect:** the real ROI/window lands on `$AZ_ROOT/archive`, correctly radiometry-tagged
  (spec 34), ready for spec 36's `run_aml` to build datacubes against.
- **PASS if:** no failed/circuit-tripped job, and the catalog covers the expected tile count
  (`fsd.sources.cdse.plan_download`/`query_catalog` against the same roi/window, offline, should
  show `missing_count == 0` afterwards).
- **This retires TODO #44** (the pre-fix radiometry artifacts) if `archive` replaces or supersedes
  the old `spec34-demo/` prefix — decide with the user whether to also delete the stale prefix.
- **Delete the blob creds file now that the run is done** (D5 REVISED's plaintext-at-rest trade-off
  is scoped to the run's duration only):
  ```bash
  .venv/bin/python -c "from fsd.storage import fs; import os; fs.rm(os.environ['AZ_CREDS_URL'])"
  ```
  **PASS if:** the command exits cleanly (`fs.rm` on an fsspec path); re-running `fs.exists` on
  `AZ_CREDS_URL` afterwards should return `False`.

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
