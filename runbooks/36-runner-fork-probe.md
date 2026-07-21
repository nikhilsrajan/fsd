# Run-book: 36 — runner fork probe (Batch vs AML: what does `rise` actually give us *today*?)

> Spec-24 run-book. **You** run this; paste back the single `_result.json`. It is the gate before
> **spec 36 (the scale runner)**: it replaces two guesses — *"Batch has enough quota"* and *"AML
> compute can reach blob under MSI"* — with facts. **Read-only. No jobs are submitted, no pools
> resized, nothing is written to blob.** ~5 minutes.
>
> **Concrete `rise` values are NOT in this file** (public repo). You paste them as env vars from the
> uncommitted `../../AZURE_INFRA_PRIVATE.md` (workspace root). See Setup.

## Why this exists

`ROADMAP.md` §5.0 and `AZURE_INFRA.md` §3 both assume **Azure Batch** is the scale target. That
assumption predates an upstream `raapid-infra` change (recorded 2026-07-15) that grew the project's
**AML** capacity substantially while leaving **Batch** untouched. Two facts decide the fork and
neither is verified (`AZURE_INFRA.md` §8 lists both as open):

1. **Batch's actual dedicated-core quota.** A fresh Batch account ships with ~6 dedicated vCPUs —
   not enough to boot even *one* pool node. If that is still the case, Batch is blocked behind a
   portal quota request (a human elsewhere, days of latency).
2. **Whether the `rise` compute identity is attached to the AML clusters.** P1 proved the storage
   seam works under that identity (`runbooks/31-p1-datacube-on-blob.md`). On Batch, pool nodes run
   as it by construction. On AML that is *unconfirmed* — and if no user-assigned identity is
   attached, AML inherits none of P1's proven blob access and needs its own RBAC ask.

Everything else about the fork is already decided or is a design choice inside spec 36.

## Pre-registered decision rule (agreed before seeing the numbers)

I apply this mechanically to your `_result.json`; it is written down first so the interpretation
isn't invented after the fact.

| Condition | Decision |
|---|---|
| `batch.dedicatedCoreQuota` ≥ 2 × pool VM cores | **Batch.** Portable task-queue model, MSI guaranteed, docs already aligned. |
| ≥ 1 × pool VM cores, but < 2 × | **Batch**, single node for the demo; file the quota ask in parallel. |
| < 1 × pool VM cores **and** an AML cluster has a **user-assigned** identity + non-zero quota | **AML.** Batch is externally blocked; AML runs today. |
| < 1 × pool VM cores **and** no AML user-assigned identity | **Batch + quota ask** (blocked), because AML would need its own RBAC ask *as well as* a new auth path — strictly more work than waiting. |

**`taskSlotsPerNode` is deliberately NOT in this rule.** We chose a **shard-of-`input.csv`** unit of
work (one dispatched unit runs the existing local Snakemake runner over its shard), so
`max_tasks_per_node = 1` is no longer a blocker and the `tfvars` ask it would have required is off
the table. The probe still reports it, because it bounds a *later* optimization.

## Prerequisites
- **VPN connected** and `az login` done (same as run-book 31).
- Azure CLI on PATH. **No `az` extensions needed** — the AML facts are read through `az rest`
  against ARM precisely so you don't have to install the `ml` extension.
- Any Python 3 (no fsd venv required — this probe imports nothing from fsd).
- Your identity needs **Reader** on the `rise` resource group. You already have more than that
  (run-book 31 round-tripped blob), so this should be automatic.

## Setup — paste your concrete values (from `AZURE_INFRA_PRIVATE.md`, uncommitted)
```bash
# fill these from ../../AZURE_INFRA_PRIVATE.md "Placeholder -> concrete" table (do NOT commit them)
export AZ_RG='<resource group>'            # rg<proj>
export AZ_LOC='<region>'                   # <loc>
export AZ_BATCH_ACCOUNT='<batch account>'  # ba<proj>
export AZ_BATCH_POOL='<pool id>'           # <proj>-pool
export AZ_ML_WORKSPACE='<aml workspace>'   # mlw<proj>
export AZ_ACR='<container registry>'       # acr<proj>
export OUT="$PWD/tests/outputs/runner_fork_probe"   # gitignored outputs dir
mkdir -p "$OUT"
```

## Steps

### Step 1 — write the probe script
```bash
cat > "$OUT/probe.py" <<'PY'
import datetime, json, os, subprocess, sys

OUT   = os.environ["OUT"]
RG    = os.environ["AZ_RG"]
LOC   = os.environ["AZ_LOC"]
BACCT = os.environ["AZ_BATCH_ACCOUNT"]
BPOOL = os.environ["AZ_BATCH_POOL"]
MLWS  = os.environ["AZ_ML_WORKSPACE"]
ACR   = os.environ["AZ_ACR"]

steps = []


def add(step, ok, metrics=None, error=None, required=True):
    steps.append({"step": step, "status": "ok" if ok else "fail", "pass": bool(ok),
                  "required": required, "metrics": metrics or {},
                  "error": (str(error)[:400] if error else None)})


def az(*args):
    """Run an az command, return parsed JSON. Raises on non-zero exit."""
    out = subprocess.run(["az", *args, "-o", "json"], capture_output=True, text=True)
    if out.returncode != 0:
        raise RuntimeError((out.stderr or out.stdout).strip()[:400])
    return json.loads(out.stdout) if out.stdout.strip() else {}


# --- Step A: context (which subscription are we even looking at?) -------------
sub = None
try:
    acct = az("account", "show")
    sub = acct["id"]
    add("context", True, {"user": acct.get("user", {}).get("name"),
                          "subscription_id": sub,
                          "subscription_name": acct.get("name")})
except Exception as e:
    add("context", False, error=e)

# --- Step B: Batch account quota + endpoint (THE fork-deciding number) --------
try:
    b = az("batch", "account", "show", "-n", BACCT, "-g", RG)
    add("batch_quota", True, {
        "dedicatedCoreQuota": b.get("dedicatedCoreQuota"),
        "lowPriorityCoreQuota": b.get("lowPriorityCoreQuota"),
        "dedicatedCoreQuotaPerVMFamilyEnforced": b.get("dedicatedCoreQuotaPerVMFamilyEnforced"),
        "dedicatedCoreQuotaPerVMFamily": b.get("dedicatedCoreQuotaPerVMFamily"),
        "poolQuota": b.get("poolQuota"),
        "activeJobAndJobScheduleQuota": b.get("activeJobAndJobScheduleQuota"),
        "accountEndpoint": b.get("accountEndpoint"),        # closes an AZURE_INFRA.md §8 unknown
        "poolAllocationMode": b.get("poolAllocationMode"),
        "provisioningState": b.get("provisioningState"),
    })
except Exception as e:
    add("batch_quota", False, error=e)

# --- Step C: Batch pool shape, read through ARM (no batch data-plane login) ---
if sub:
    pool_id = (f"/subscriptions/{sub}/resourceGroups/{RG}/providers/Microsoft.Batch"
               f"/batchAccounts/{BACCT}/pools/{BPOOL}")
    try:
        p = az("resource", "show", "--ids", pool_id, "--api-version", "2024-07-01")
        pr = p.get("properties", {})
        dep = pr.get("deploymentConfiguration", {}).get("virtualMachineConfiguration", {})
        add("batch_pool", True, {
            "vmSize": pr.get("vmSize"),
            "taskSlotsPerNode": pr.get("taskSlotsPerNode"),      # expect 1 (module default)
            "scaleSettings": pr.get("scaleSettings"),            # autoscale formula / fixed targets
            "currentDedicatedNodes": pr.get("currentDedicatedNodes"),
            "allocationState": pr.get("allocationState"),
            "provisioningState": pr.get("provisioningState"),
            "imageReference": dep.get("imageReference"),         # is the DSVM image what we think?
            "nodeAgentSkuId": dep.get("nodeAgentSkuId"),
            "containerConfiguration": dep.get("containerConfiguration"),  # container-enabled?
            "startTask_present": bool(pr.get("startTask")),
        })
    except Exception as e:
        add("batch_pool", False, error=e)

# --- Step D: AML computes via ARM — identity is the fork-deciding fact --------
if sub:
    url = (f"https://management.azure.com/subscriptions/{sub}/resourceGroups/{RG}"
           f"/providers/Microsoft.MachineLearningServices/workspaces/{MLWS}"
           f"/computes?api-version=2023-10-01")
    try:
        resp = az("rest", "--method", "get", "--url", url)
        computes = []
        for c in resp.get("value", []):
            props = c.get("properties", {}) or {}
            inner = props.get("properties", {}) or {}
            scale = inner.get("scaleSettings", {}) or {}
            ident = c.get("identity", {}) or {}
            computes.append({
                "name": c.get("name"),
                "computeType": props.get("computeType"),
                "vmSize": inner.get("vmSize"),
                "vmPriority": inner.get("vmPriority"),
                "maxNodeCount": scale.get("maxNodeCount"),
                "minNodeCount": scale.get("minNodeCount"),
                "provisioningState": props.get("provisioningState"),
                # THE question: is a user-assigned identity attached?
                "identityType": ident.get("type"),
                "userAssignedIdentities": sorted((ident.get("userAssignedIdentities") or {}).keys()),
            })
        add("aml_computes", True, {"count": len(computes), "computes": computes})
    except Exception as e:
        add("aml_computes", False, error=e)

# --- Step E: AML per-VM-family quota (best effort) ----------------------------
if sub:
    url = (f"https://management.azure.com/subscriptions/{sub}/providers"
           f"/Microsoft.MachineLearningServices/locations/{LOC}/usages?api-version=2023-10-01")
    try:
        resp = az("rest", "--method", "get", "--url", url)
        rows = []
        for u in resp.get("value", []):
            limit = u.get("limit")
            if limit in (None, 0, -1):
                continue
            rows.append({"name": (u.get("name") or {}).get("localizedValue") or (u.get("name") or {}).get("value"),
                         "currentValue": u.get("currentValue"), "limit": limit})
        add("aml_quota", True, {"families_with_quota": rows}, required=False)
    except Exception as e:
        add("aml_quota", False, error=e, required=False)

# --- Step F: ACR shape (only matters if Batch wins: can `az acr build` work?) -
try:
    r = az("acr", "show", "-n", ACR, "-g", RG)
    add("acr", True, {
        "sku": (r.get("sku") or {}).get("name"),
        "loginServer": r.get("loginServer"),
        "publicNetworkAccess": r.get("publicNetworkAccess"),
        "networkRuleBypassOptions": r.get("networkRuleBypassOptions"),
        "adminUserEnabled": r.get("adminUserEnabled"),
        "zoneRedundancy": r.get("zoneRedundancy"),
    }, required=False)
except Exception as e:
    add("acr", False, error=e, required=False)

# --- Step G: subscription VM-family quota in the region (context, best effort)-
try:
    rows = [{"name": (u.get("name") or {}).get("localizedValue"),
             "currentValue": u.get("currentValue"), "limit": u.get("limit")}
            for u in az("vm", "list-usage", "-l", LOC)
            if u.get("limit") not in (None, 0)
            and any(k in ((u.get("name") or {}).get("localizedValue") or "")
                    for k in ("Total Regional", "DDv5", "Dv6", "EDSv4", "Dv5"))]
    add("vm_quota", True, {"families": rows}, required=False)
except Exception as e:
    add("vm_quota", False, error=e, required=False)

required_ok = all(s["pass"] for s in steps if s["required"])
result = {"runbook": "36-runner-fork-probe",
          "pass": required_ok,
          "steps": steps,
          "utc": datetime.datetime.now(datetime.timezone.utc).isoformat()}
with open(os.path.join(OUT, "_result.json"), "w") as f:
    json.dump(result, f, indent=2)
print(json.dumps(result, indent=2))
sys.exit(0 if required_ok else 1)
PY
echo "wrote $OUT/probe.py"
```
- **Expect:** `wrote .../probe.py`.
- **PASS if:** the file exists (no result yet).

### Step 2 — run the probe (VPN must be up)
```bash
python3 "$OUT/probe.py"
```
- **Expect:** a JSON dump ending in `"pass": true`, with `context`, `batch_quota`, `batch_pool`,
  `aml_computes` all `"pass": true`. `aml_quota` / `acr` / `vm_quota` are `"required": false` —
  they add colour, they don't gate.
- **PASS if:** top-level `"pass": true` → writes `$OUT/_result.json`.
- **Partial reads (all still useful — paste whatever you get):**
  - `batch_quota` **fails with AuthorizationFailed** → your identity lacks Reader on the Batch
    account. Tell me; that itself is an RBAC ask and a fork input.
  - `batch_pool` fails but `batch_quota` succeeded → the pool may not be an ARM-tracked resource.
    Fallback: `az batch account login -g "$AZ_RG" -n "$AZ_BATCH_ACCOUNT"` then
    `az batch pool show --pool-id "$AZ_BATCH_POOL" -o json` and paste that output. (The login is
    AAD-based and writes only to your local `az` config.)
  - `aml_computes` returns `"count": 0` → the clusters aren't provisioned in this workspace;
    that alone decides the fork in Batch's favour.
  - `aml_quota` failing is fine — that API is inconsistently available and it is not required.
- **If it hangs (>60 s on a step):** almost always **VPN down** or the wrong subscription selected.
  Ctrl-C is completely safe — every call in this probe is a `GET`.

## Success criteria (`_result.json`)
Paste `$OUT/_result.json`. Shape:
```json
{ "runbook": "36-runner-fork-probe", "pass": true,
  "steps": [
    { "step": "context",       "pass": true, "metrics": { "subscription_id": "..." } },
    { "step": "batch_quota",   "pass": true, "metrics": { "dedicatedCoreQuota": 0, "accountEndpoint": "..." } },
    { "step": "batch_pool",    "pass": true, "metrics": { "vmSize": "...", "taskSlotsPerNode": 1 } },
    { "step": "aml_computes",  "pass": true, "metrics": { "computes": [ { "name": "...", "identityType": "..." } ] } }
  ] }
```
It carries concrete `rise` identifiers, so **paste it into the chat only** — do not commit it
(`tests/outputs/` is gitignored, so leaving the file where it lands is safe).

I diff it against the pre-registered rule above, state the decision it forces, and then draft
**`specs/36-scale-runner.md`** against a backend we know is reachable. Two `AZURE_INFRA.md` §8
unknowns (the Batch account endpoint host format; the AML cluster names/quota) close as a side
effect.

## Stop / observe
- Seconds per step; no progress line needed.
- Abort: Ctrl-C — safe, the probe only issues read-only ARM/CLI `GET`s.
- Re-run: idempotent (overwrites `$OUT/_result.json`).
