# Run-book: 31 — P1 Azure access probe ("hello Azure")

> Spec-24 run-book. **You** run this; paste back the single `_result.json`. It is the gate
> before the P1 spec: it proves your *personal* identity can reach `rise` storage and tells the
> spec which auth + which GDAL VSI driver work. ~15 min, no fsd pipeline, no downloads.
>
> **Concrete `rise` values are NOT in this file** (it's in the public repo). You paste them as
> env vars from the uncommitted `../../P1_AZURE_SETUP.md` §3 (workspace root). See Setup.

## Handoff checklist (this runs BEFORE the P1 spec handoff)
- [ ] You've run this probe and it's green (or you've pasted the failure).
- [ ] Then run `/handoff "write + sign off spec 31 (P1 storage seam) from the probe results"`
      → fresh **Opus@high** session (spec-first: it writes the spec, does not code).

## Purpose
Prove, from this laptop over the VPN, that (1) `az` points at the `rise` subscription, (2) your
identity can **round-trip a blob** via **adlfs** (the fsd storage seam) — the RBAC gate, and
(3) **rasterio/GDAL** can read an Azure object via **`/vsiadls/`** (ADLS Gen2) — the raster-read
seam. One script, one `_result.json`.

## Prerequisites
- **VPN connected** (storage is firewalled to VPN + `rise` subnets — nothing works without it).
- `az login` already done (you confirmed). Azure CLI on PATH.
- fsd venv active with the azure extra + identity:
  ```bash
  cd fsd && source .venv/bin/activate
  pip install -e ".[dev,azure]" azure-identity
  ```

## Setup — paste your concrete values (from `P1_AZURE_SETUP.md` §3, uncommitted)
```bash
# fill these from ../../P1_AZURE_SETUP.md §3 (do NOT commit them)
export AZ_ACCOUNT='<storage account>'          # the ADLS Gen2 account name
export AZ_FS='<filesystem/container>'          # e.g. the container in §3
export AZ_SCRATCH_PREFIX='<scratch prefix>'    # e.g. fsd-p1-scratch  (no leading/trailing slash needed)
export AZ_RG='<resource group>'                # the rise resource group
export OUT="$PWD/tests/outputs/p1_probe"       # gitignored outputs dir
mkdir -p "$OUT"
```

## Steps

### Step 1 — write the probe script
```bash
cat > "$OUT/probe.py" <<'PY'
import json, os, subprocess, datetime, io, sys

OUT     = os.environ["OUT"]
ACCOUNT = os.environ["AZ_ACCOUNT"]
FS      = os.environ["AZ_FS"]
PREFIX  = os.environ["AZ_SCRATCH_PREFIX"].strip("/")
RG      = os.environ["AZ_RG"]
OBJ     = f"{PREFIX}/probe.tif"          # relative to the filesystem/container
steps   = []

def add(step, ok, metrics=None, error=None):
    steps.append({"step": step, "status": "ok" if ok else "fail", "pass": bool(ok),
                  "metrics": metrics or {}, "error": (str(error)[:400] if error else None)})

# --- Step A: az identity + subscription + resource group reachable ---
try:
    acct = json.loads(subprocess.check_output(["az","account","show","-o","json"], text=True))
    grp  = json.loads(subprocess.check_output(["az","group","show","-n",RG,"-o","json"], text=True))
    add("az_identity_subscription", True, {
        "user": acct.get("user", {}).get("name"),
        "subscription_id": acct.get("id"),
        "subscription_name": acct.get("name"),
        "resource_group_found": grp.get("name")})
except Exception as e:
    add("az_identity_subscription", False, error=e)

# --- build a tiny real GeoTIFF in memory (representative of an fsd band read) ---
import numpy as np, rasterio
from rasterio.io import MemoryFile
from rasterio.transform import from_origin
tif_bytes = None
try:
    prof = dict(driver="GTiff", width=2, height=2, count=1, dtype="uint8",
                crs="EPSG:4326", transform=from_origin(0, 2, 1, 1))
    with MemoryFile() as mem:
        with mem.open(**prof) as ds:
            ds.write(np.array([[1,2],[3,4]], dtype="uint8"), 1)
        tif_bytes = mem.read()
except Exception as e:
    add("build_probe_tif", False, error=e)

# --- Step B: adlfs round-trip (the fsd storage seam + the RBAC gate) ---
az_url = f"{FS}/{OBJ}"
if tif_bytes is not None:
    try:
        from azure.identity import DefaultAzureCredential
        from adlfs import AzureBlobFileSystem
        fs = AzureBlobFileSystem(account_name=ACCOUNT, credential=DefaultAzureCredential())
        with fs.open(az_url, "wb") as f:
            f.write(tif_bytes)
        with fs.open(az_url, "rb") as f:
            got = f.read()
        add("adlfs_roundtrip", got == tif_bytes,
            {"path": f"az://{az_url}", "wrote_bytes": len(tif_bytes), "read_bytes": len(got)})
    except Exception as e:
        add("adlfs_roundtrip", False, {"path": f"az://{az_url}"}, error=e)

# --- Step C: rasterio/GDAL VSI read — which driver opens it (/vsiadls first, /vsiaz fallback) ---
try:
    tok = json.loads(subprocess.check_output(
        ["az","account","get-access-token","--resource","https://storage.azure.com/","-o","json"],
        text=True))["accessToken"]
    drivers = {}
    for drv in ("/vsiadls", "/vsiaz"):
        vp = f"{drv}/{az_url}"
        try:
            with rasterio.Env(AZURE_STORAGE_ACCESS_TOKEN=tok, AZURE_STORAGE_ACCOUNT=ACCOUNT):
                with rasterio.open(vp) as ds:
                    arr = ds.read(1)
            drivers[drv] = "ok" if (arr.shape == (2,2) and int(arr[0,0]) == 1) else f"unexpected:{arr.shape}"
        except Exception as e:
            drivers[drv] = f"error: {str(e)[:120]}"
    ok = "ok" in (drivers.get("/vsiadls"), drivers.get("/vsiaz"))
    add("gdal_vsi_read", ok, {"drivers": drivers, "gdal": rasterio.__gdal_version__})
except Exception as e:
    add("gdal_vsi_read", False, error=e)

# --- best-effort cleanup of the probe object ---
try:
    from adlfs import AzureBlobFileSystem
    from azure.identity import DefaultAzureCredential
    AzureBlobFileSystem(account_name=ACCOUNT, credential=DefaultAzureCredential()).rm(az_url)
except Exception:
    pass

result = {"runbook": "31-p1-access-probe",
          "pass": all(s["pass"] for s in steps) and len(steps) >= 3,
          "steps": steps,
          "utc": datetime.datetime.utcnow().isoformat()}
with open(os.path.join(OUT, "_result.json"), "w") as f:
    json.dump(result, f, indent=2)
print(json.dumps(result, indent=2))
sys.exit(0 if result["pass"] else 1)
PY
echo "wrote $OUT/probe.py"
```
- **Expect:** `wrote .../probe.py`.
- **PASS if:** the file exists (no result yet).

### Step 2 — run the probe (VPN must be up)
```bash
python "$OUT/probe.py"
```
- **Expect:** a JSON dump ending with `"pass": true`, and `steps` showing
  `az_identity_subscription`, `adlfs_roundtrip`, `gdal_vsi_read` all `"pass": true`.
- **PASS if:** top-level `"pass": true` → writes `$OUT/_result.json`.
- **Partial reads:**
  - `adlfs_roundtrip` **fails with 403 / AuthorizationPermissionMismatch** → your *personal*
    identity lacks **Storage Blob Data Contributor** on the account. That's the one admin RBAC
    grant to request (tell me; I'll draft the ask). Everything else may still be fine.
  - `gdal_vsi_read` shows `/vsiadls: ok` but `/vsiaz: error` (or vice-versa) → that's a
    **success** — it tells the P1 spec which driver to use. Only both-erroring is a fail.
  - Any step erroring with `az ...` not found / not logged in → fix `az login` / PATH first.
- **If it hangs (>60s on a step):** almost always **VPN down** or wrong subscription — Ctrl-C
  (safe, nothing persisted but the tiny probe object which the script also cleans up), fix, re-run.

## Success criteria (`_result.json`)
Paste `$OUT/_result.json`. It has:
```json
{ "runbook": "31-p1-access-probe", "pass": true,
  "steps": [
    { "step": "az_identity_subscription", "pass": true,
      "metrics": { "subscription_id": "...", "resource_group_found": "..." } },
    { "step": "adlfs_roundtrip", "pass": true, "metrics": { "wrote_bytes": 0, "read_bytes": 0 } },
    { "step": "gdal_vsi_read", "pass": true, "metrics": { "drivers": { "/vsiadls": "ok" } } }
  ] }
```
Green = P1 access is real; I diff it and we proceed to the spec-31 handoff. A `subscription_id`
also lets you fill the last ⬜ in `P1_AZURE_SETUP.md` §2.

## Stop / observe
- The probe is seconds per step; no long progress line needed.
- Abort: Ctrl-C (safe — the only side effect is one tiny `probe.tif` in scratch, auto-deleted).
- Re-run: idempotent (overwrites the same probe object each time).
