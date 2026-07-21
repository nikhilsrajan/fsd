# Run-book: 36 Phase 0 — identity smoke on the AML cluster

> Spec-24 run-book for **spec 36 §6 Phase 0**. **You** run this; paste back the printed JSON.
> One AML job, one node, a few minutes of a `d16` node, then the cluster scales back to 0.
>
> **Concrete `rise` values are NOT in this file** (public repo). You paste them as env vars from the
> uncommitted `../../AZURE_INFRA_PRIVATE.md` (workspace root). See Setup.

## Purpose — the one question

**Can a job on the AML cluster authenticate to blob as the project's compute identity, through
fsd's existing storage + raster seams, with no fsd code change?**

That is spec 36 **D4**, and it is the only genuine unknown left in the design. The AML cluster has
**only a user-assigned managed identity** (probe 36 confirmed `identityType: UserAssigned`), and a
user-assigned identity is *never* selected implicitly — so `fsd/storage/azure.py`'s bare
`DefaultAzureCredential()` would fail on the node unless `AZURE_CLIENT_ID` is set. D4 claims setting
that one environment variable is the whole fix, because `azure-identity` already defaults
`managed_identity_client_id` to it.

**This runs before any runner code is written.** If D4 is wrong, every downstream deliverable in
spec 36 is built on sand; if it's right, the rest of P2 is plumbing.

The probe also runs a **negative control** (step C): the same credential *without* `AZURE_CLIENT_ID`.
That distinguishes "our fix works" from "no fix was ever needed" — which changes the spec either way,
so it is worth the ten extra lines.

## What it proves (and what it deliberately does not)

| Proves | Does not touch |
|---|---|
| MSI token acquisition on a cluster node, and **which identity** the token belongs to | Sharding, job fan-out, Snakemake-in-job |
| `fsd.storage.fs` read/write against project blob **from a node** | Datacube correctness |
| `fsd.raster.rio_open` → `/vsiadls/` streaming read of a real COG **from a node** | Throughput or timing |
| That an fsd **wheel** installs and imports on the cluster (spec 36 D5's premise) | The final job environment definition |

## Prerequisites
- **VPN connected**, `az login` done, correct subscription selected.
- `az ml` CLI extension: `az extension add -n ml` (or `az extension update -n ml`). **No Python
  Azure SDK is installed on your laptop** — the CLI does the submitting, deliberately, so nothing
  new lands in `.venv`.
- The fsd venv, only to *build a wheel*: `cd fsd && source .venv/bin/activate`.
- An existing COG on blob to read — any band file from `runbooks/34-download-to-blob.md`'s output.

## Setup — paste your concrete values (from `AZURE_INFRA_PRIVATE.md`, uncommitted)
```bash
cd fsd
export AZ_RG='<resource group>'                 # rg<proj>
export AZ_ML_WORKSPACE='<aml workspace>'        # mlw<proj>
export AZ_CLUSTER='<the d16 cluster name>'      # cluster-<proj>-d16
export AZ_UAMI_NAME='<compute identity name>'   # id<proj>-compute
export AZ_ACCOUNT='<storage account>'           # st<proj>
export AZ_FS='<filesystem/container>'           # e.g. data
export AZ_SCRATCH_PREFIX='fsd-p2-phase0'        # scratch prefix inside the container
# an existing COG on blob (from runbook 34) — full abfss:// URL:
export FSD_PROBE_COG='abfss://<fs>@<account>.dfs.core.windows.net/<path/to/a/band>.tif'

export OUT="$PWD/tests/outputs/phase0_identity"     # gitignored
mkdir -p "$OUT/job_src"

# the client ID of the compute identity — this is what the whole probe turns on
export AZ_UAMI_CLIENT_ID="$(az identity show -g "$AZ_RG" -n "$AZ_UAMI_NAME" --query clientId -o tsv)"
echo "client id resolved: ${AZ_UAMI_CLIENT_ID:0:8}…"
```
- **PASS if:** the last line prints 8 hex characters. Empty ⇒ wrong RG/identity name, or not logged in.

## Steps

### Step 1 — build the fsd wheel
```bash
.venv/bin/pip wheel . --no-deps -w "$OUT/job_src" && ls -la "$OUT/job_src"/fsd-*.whl
```
- **Expect:** exactly one `fsd-<version>-py3-none-any.whl`.
- **PASS if:** the wheel exists.
- **Why a wheel and not `pip install git+https://…`:** it tests *your working tree*, so the probe
  can't accidentally validate an older pushed commit — and it needs no push (`CLAUDE.md`: push only
  when asked).

### Step 2 — write the probe script
```bash
cat > "$OUT/job_src/probe.py" <<'PY'
"""Phase 0: prove MSI -> blob works on an AML node through fsd's own seams."""
import base64, datetime, json, os, sys

steps = []


def add(step, ok, metrics=None, error=None, required=True):
    steps.append({"step": step, "status": "ok" if ok else "fail", "pass": bool(ok),
                  "required": required, "metrics": metrics or {},
                  "error": (str(error)[:400] if error else None)})


def claims(token):
    """Non-secret identity claims from a JWT. The token itself is NEVER recorded."""
    payload = token.split(".")[1]
    payload += "=" * (-len(payload) % 4)
    d = json.loads(base64.urlsafe_b64decode(payload))
    return {k: d.get(k) for k in ("appid", "oid", "tid", "aud", "xms_mirid")}


ACCOUNT = os.environ["FSD_PROBE_ACCOUNT"]
FS      = os.environ["FSD_PROBE_FS"]
PREFIX  = os.environ["FSD_PROBE_PREFIX"].strip("/")
COG     = os.environ["FSD_PROBE_COG"]
WANT_ID = os.environ.get("AZURE_CLIENT_ID")

ROOT    = f"abfss://{FS}@{ACCOUNT}.dfs.core.windows.net/{PREFIX}"
scratch = f"{ROOT}/probe-{datetime.datetime.now(datetime.timezone.utc):%Y%m%dT%H%M%S}"

# --- Step A: what did the environment actually hand us? ----------------------
add("env", True, {
    "AZURE_CLIENT_ID_set": bool(WANT_ID),
    "DEFAULT_IDENTITY_CLIENT_ID_set": bool(os.environ.get("DEFAULT_IDENTITY_CLIENT_ID")),
    "two_agree": (WANT_ID == os.environ.get("DEFAULT_IDENTITY_CLIENT_ID")
                  if WANT_ID and os.environ.get("DEFAULT_IDENTITY_CLIENT_ID") else None),
    "python": sys.version.split()[0],
})

# --- Step B: THE test — fsd's own credential path, and WHICH identity it got --
try:
    import fsd
    from fsd.storage import azure as fsd_azure
    tok = fsd_azure.storage_token()
    c = claims(tok)
    got = c.get("appid")
    add("fsd_token_identity", bool(got) and (WANT_ID is None or got == WANT_ID), {
        "fsd_version": getattr(fsd, "__version__", "?"),
        "token_appid": got,
        "matches_AZURE_CLIENT_ID": (got == WANT_ID) if WANT_ID else None,
        "audience": c.get("aud"),
        "claims": c,
    })
except Exception as e:
    add("fsd_token_identity", False, error=e)

# --- Step C: NEGATIVE CONTROL — is D4's fix actually load-bearing? -----------
# Same credential class, AZURE_CLIENT_ID removed. If this ALSO succeeds, the node
# resolves the UAMI implicitly and spec 36 D4 can be simplified away.
try:
    from azure.identity import DefaultAzureCredential
    saved = os.environ.pop("AZURE_CLIENT_ID", None)
    try:
        bare = DefaultAzureCredential()
        btok = bare.get_token("https://storage.azure.com/.default").token
        add("negative_control_no_client_id", True,
            {"succeeded": True, "token_appid": claims(btok).get("appid"),
             "interpretation": "bare DefaultAzureCredential WORKS on the node -> D4 may be unnecessary"},
            required=False)
    finally:
        if saved is not None:
            os.environ["AZURE_CLIENT_ID"] = saved
except Exception as e:
    add("negative_control_no_client_id", True,
        {"succeeded": False,
         "interpretation": "bare DefaultAzureCredential FAILS on the node -> D4 is load-bearing, as designed",
         "failure": str(e)[:300]},
        required=False)

# --- Step D: fsd.storage round-trip from the node ---------------------------
try:
    from fsd.storage import fs
    fsd_azure.configure_storage("azure")
    import numpy as np
    arr = np.arange(12, dtype="uint16").reshape(3, 4)
    npy = f"{scratch}/probe.npy"
    fs.save_npy(npy, arr)
    back = fs.load_npy(npy)
    txt = f"{scratch}/probe.txt"
    with fs.open(txt, "w") as f:
        f.write("phase0")
    with fs.open(txt, "r") as f:
        got_txt = f.read()
    add("fsd_storage_roundtrip", bool((back == arr).all()) and got_txt == "phase0", {
        "path": scratch, "npy_shape": list(back.shape), "npy_equal": bool((back == arr).all()),
        "text_equal": got_txt == "phase0", "exists": fs.exists(npy)})
except Exception as e:
    add("fsd_storage_roundtrip", False, {"path": scratch}, error=e)

# --- Step E: GDAL /vsiadls/ read of a real COG, via fsd.raster.rio_open ------
try:
    from fsd.raster import rio_open
    with rio_open(COG) as ds:
        win = ds.read(1, window=((0, min(256, ds.height)), (0, min(256, ds.width))))
        meta = {"crs": str(ds.crs), "shape": [ds.height, ds.width], "dtype": str(ds.dtypes[0]),
                "window_shape": list(win.shape), "window_nonzero": int((win != 0).sum())}
    add("fsd_rio_open_vsiadls", True, meta)
except Exception as e:
    add("fsd_rio_open_vsiadls", False, {"cog": COG}, error=e)

# --- cleanup (best effort) ---------------------------------------------------
try:
    from fsd.storage import fs as _fs
    _fs.rm(scratch, recursive=True)
except Exception:
    pass

required_ok = all(s["pass"] for s in steps if s["required"])
result = {"runbook": "36-phase0-identity-smoke", "pass": required_ok, "steps": steps,
          "utc": datetime.datetime.now(datetime.timezone.utc).isoformat()}
os.makedirs("./outputs", exist_ok=True)          # AML auto-uploads ./outputs
with open("./outputs/_result.json", "w") as f:
    json.dump(result, f, indent=2)
print("FSD_RESULT_BEGIN")
print(json.dumps(result, indent=2))
print("FSD_RESULT_END")
sys.exit(0 if required_ok else 1)
PY
echo "wrote $OUT/job_src/probe.py"
```
- **PASS if:** the file exists.

### Step 3 — write the environment + job spec
```bash
cat > "$OUT/job_src/conda.yaml" <<'YML'
name: fsd-phase0
channels:
  - conda-forge
dependencies:
  - python=3.11
  - pip
YML

# NOTE: unquoted heredoc — your exported values are substituted into the YAML.
cat > "$OUT/job.yml" <<YML
\$schema: https://azuremlschemas.azureedge.net/latest/commandJob.schema.json
display_name: fsd-phase0-identity-smoke
experiment_name: fsd-p2
code: ./job_src
command: >-
  pip install --quiet "./\$(ls fsd-*.whl)[azure]" &&
  python probe.py
environment:
  image: mcr.microsoft.com/azureml/openmpi4.1.0-ubuntu22.04:latest
  conda_file: ./job_src/conda.yaml
compute: azureml:${AZ_CLUSTER}
environment_variables:
  AZURE_CLIENT_ID: ${AZ_UAMI_CLIENT_ID}
  FSD_PROBE_ACCOUNT: ${AZ_ACCOUNT}
  FSD_PROBE_FS: ${AZ_FS}
  FSD_PROBE_PREFIX: ${AZ_SCRATCH_PREFIX}
  FSD_PROBE_COG: ${FSD_PROBE_COG}
YML
grep -c AZURE_CLIENT_ID "$OUT/job.yml" && echo "job.yml written"
```
- **Expect:** `1` then `job.yml written`.
- **PASS if:** `job.yml` contains a real GUID for `AZURE_CLIENT_ID` (`grep AZURE_CLIENT_ID "$OUT/job.yml"`).
- ⚠️ **`job.yml` now contains concrete `rise` identifiers.** It lives under `tests/outputs/`, which is
  gitignored — leave it there, don't move it into the repo proper.

### Step 4 — submit and watch
```bash
cd "$OUT" && az ml job create -f job.yml -g "$AZ_RG" -w "$AZ_ML_WORKSPACE" --query name -o tsv
```
- Copy the returned job name, then stream it:
```bash
az ml job stream -n <job-name> -g "$AZ_RG" -w "$AZ_ML_WORKSPACE"
```
- **Expect:** the cluster scales 0→1 (a few minutes), the environment builds **the first time only**
  (~5–10 min; cached afterwards), pip installs, then the block between `FSD_RESULT_BEGIN` and
  `FSD_RESULT_END`.
- **PASS if:** that JSON has `"pass": true`.
- **Cost:** one `d16` node for the job's duration; the cluster autoscales back to 0 (`minNodeCount: 0`).
- **If streaming disconnects** (it does, over VPN) the job keeps running:
  `az ml job show -n <job-name> -g "$AZ_RG" -w "$AZ_ML_WORKSPACE" --query status -o tsv`, then
  `az ml job download -n <job-name> -g "$AZ_RG" -w "$AZ_ML_WORKSPACE" --all -o "$OUT/dl"` and read
  `"$OUT/dl"/**/outputs/_result.json`.
- **To abort:** `az ml job cancel -n <job-name> -g "$AZ_RG" -w "$AZ_ML_WORKSPACE"`. Safe — the only
  side effect is a scratch prefix the probe deletes itself.

## Reading the result — what each outcome means for spec 36

Paste the `FSD_RESULT_BEGIN…END` JSON. I diff it against this table; **no outcome here is a dead
end**, each just points at a different edit:

| Result | Meaning | What changes in spec 36 |
|---|---|---|
| All required steps pass | **D4 confirmed.** Node identity works through fsd's seams, unmodified. | Nothing. Proceed to implementation. |
| `fsd_token_identity` passes **and** `negative_control_no_client_id.succeeded == true` | The node resolves the UAMI implicitly; the env var was never needed. | **D4 simplifies away** — delete the `AZURE_CLIENT_ID` requirement and test 5. |
| `fsd_token_identity` fails, `token_appid` ≠ your client ID | A *different* identity answered (submitter, or another UAMI). | Add `identity: type: managed` to the job spec and re-run — this also answers spec 36 §8 Q2. |
| `fsd_token_identity` passes but `fsd_storage_roundtrip` 403s | Identity is right, RBAC or the storage firewall is not. | An RBAC/network ask — tell me and I'll draft it. Not a design change. |
| `fsd_rio_open_vsiadls` fails alone | GDAL VSI needs different node config than adlfs does. | Narrow, contained; spec 36 D5 gains a GDAL env note. Everything else stands. |
| Environment build or `pip install` fails | Packaging, not identity. | **D5 changes** (pinned base image / prebuilt ACR image sooner). D4 remains untested — we'd re-run. |

## Success criteria (`_result.json`)
```json
{ "runbook": "36-phase0-identity-smoke", "pass": true,
  "steps": [
    { "step": "env",                          "pass": true },
    { "step": "fsd_token_identity",           "pass": true, "metrics": { "matches_AZURE_CLIENT_ID": true } },
    { "step": "negative_control_no_client_id","pass": true, "required": false },
    { "step": "fsd_storage_roundtrip",        "pass": true },
    { "step": "fsd_rio_open_vsiadls",         "pass": true }
  ] }
```
`negative_control_no_client_id` is **diagnostic, not a gate** — it passes either way and records
*which* way, because that is the thing worth knowing.

## Stop / observe
- Progress: `az ml job stream` prints the node allocation, image build, and pip output live; the
  Studio URL printed at submit shows the same.
- Abort: `az ml job cancel …` (safe).
- Re-run: idempotent — each run writes a fresh timestamped scratch prefix and deletes it.
