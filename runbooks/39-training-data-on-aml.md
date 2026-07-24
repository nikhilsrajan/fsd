# Run-book: 39 Phases 0–2 — training data on Azure ML: flatten → land-local, then full e2e

> Spec-24 run-book for **spec 39 §6**. **You** run this; paste back each phase's printed JSON.
> Builds on runbook 36 (build fan-out, cluster/identity/Environment already proven) and runbook 37
> (download dispatch) — this run-book adds the **flatten reduce + land-local** leg (D3/D4) and then
> proves `create_training_data` as the **one-verb download→build→flatten→land-local** façade (D1).
>
> **Concrete `rise` values are NOT in this file** (public repo). Paste them as env vars from the
> uncommitted `../../AZURE_INFRA_PRIVATE.md` (workspace root).

## Purpose

Phase 1 proves the missing half of the demo pipeline: `flatten_training_data(runner="aml")` turns
the ~900 blob cubes runbook 36 Phase 3 already built into **one** local training array, dispatched
as a single-node reduce (not a fan-out) — and measures `data.npy`'s actual size (D3's memory
estimate). Phase 2 proves the **composition**: `create_training_data(download=True, runner="aml")`
chains MPC download → build → flatten → land-local in one call, on a small fresh subset.

## Prerequisites
- **VPN connected**, `az login` done, correct subscription selected (driver does blob I/O:
  reading `input.csv`, writing `_status/*.json`, `storage.transfer` land-local reads).
- The fsd venv with the `[aml]` extra: `cd fsd && source .venv/bin/activate && pip install -e ".[dev,aml,mpc]"`.
- The spec-36 AML Environment already built and smoke-tested (`runbooks/36-aml-runner.md`) — flatten
  runs on the **same general-purpose Environment**, no rebuild needed (ADR-0020: no adapter image).
- **Phase 0's precondition**: runbook 36 Phase 3's cubes + `input.csv` (`id`/`label`/
  `datacube_filepath`) already on blob. This run-book does not build them.

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
export AZ_ROOT="abfss://${AZ_FS}@${AZ_ACCOUNT}.dfs.core.windows.net/fsd-p2-build"   # runbook 36's root
export AZ_ENV_NAME='fsd-aml-env'
export AZ_ENV_VERSION="$(az ml environment list -n "$AZ_ENV_NAME" -g "$AZ_RG" \
  -w "$AZ_ML_WORKSPACE" --query "[].version" -o tsv | sort -V | tail -1)"
echo "environment: ${AZ_ENV_NAME}:${AZ_ENV_VERSION}"

export AZ_UAMI_CLIENT_ID="$(az identity show -g "$AZ_RG" -n "$AZ_UAMI_NAME" --query clientId -o tsv)"
echo "client id resolved: ${AZ_UAMI_CLIENT_ID:0:8}…"

# runbook-36 Phase 3's own input.csv -- Phase 0 below only CONFIRMS this exists.
export AZ_PHASE3_INPUT_CSV="${AZ_ROOT}/runs/<phase3-run-id>/input.csv"

export OUT="$PWD/tests/outputs/p39_training_data_aml"     # gitignored
mkdir -p "$OUT"
```
- **PASS if:** the client-id line prints 8 hex characters and the environment line prints a real
  version.

## Phase 0 — preconditions: the runbook-36 cubes + input.csv exist
```bash
.venv/bin/python -c "
from fsd.storage import fs
import json, os, pandas as pd

input_csv = os.environ['AZ_PHASE3_INPUT_CSV']
exists = fs.exists(input_csv)
sample_ok = False
n_rows = 0
if exists:
    with fs.open(input_csv, 'r') as f:
        df = pd.read_csv(f)
    n_rows = len(df)
    if n_rows:
        sample = df.iloc[0]['datacube_filepath']
        sample_ok = fs.exists(sample) and fs.exists(
            os.path.join(os.path.dirname(sample), 'metadata.pickle.npy'))

out = {'phase': 'phase0-preconditions', 'pass': bool(exists and sample_ok and n_rows > 0),
       'input_csv_exists': exists, 'n_rows': n_rows, 'sample_cube_reads': sample_ok}
print('FSD_RESULT_BEGIN'); print(json.dumps(out, indent=2)); print('FSD_RESULT_END')
with open(f\"{os.environ['OUT']}/phase0_result.json\", 'w') as f:
    json.dump(out, f, indent=2)
"
```
- **PASS if:** `input_csv_exists`, `sample_cube_reads` both `true`, `n_rows > 0` (expect ~900 for
  the full `AT_2018_TRAIN` set). **If this fails, stop** — run runbook 36 Phase 3 first; this
  run-book does not build cubes.

## Phase 1 — flatten-reduce over the existing blob cubes → local (proves the reduce + land-local at scale)
```bash
cat > "$OUT/phase1.py" <<'PY'
import json, os, time
from fsd import api
from fsd.storage import fs

t0 = time.time()
td = api.flatten_training_data(
    os.environ["AZ_PHASE3_INPUT_CSV"],
    export_folderpath=f"{os.environ['OUT']}/landed",   # LOCAL
    id_col="id", label_col="label",
    runner="aml",
    runner_kwargs=dict(
        cluster=os.environ["AZ_CLUSTER"],
        environment=f"{os.environ['AZ_ENV_NAME']}:{os.environ['AZ_ENV_VERSION']}",
        root=os.environ["AZ_ROOT"], identity_client_id=os.environ["AZ_UAMI_CLIENT_ID"],
        subscription_id=os.environ["AZ_SUBSCRIPTION_ID"], resource_group_name=os.environ["AZ_RG"],
        workspace_name=os.environ["AZ_ML_WORKSPACE"], run_id="phase1-flatten",
    ),
)
wall = time.time() - t0

data_bytes = os.path.getsize(f"{os.environ['OUT']}/landed/data.npy")
loaded = td.load()
out = {
    "phase": "phase1-flatten-reduce-at-scale", "pass": True,
    "wall_seconds": round(wall, 1),
    "n_pixels": td.n_pixels, "n_timestamps": td.n_timestamps, "bands": td.bands,
    "data_npy_bytes": data_bytes, "data_shape": list(loaded["data"].shape),
    "ids_len": len(loaded["ids"]), "labels_present": "labels" in loaded,
    "labels_len": len(loaded["labels"]) if "labels" in loaded else None,
    "coords_sample": loaded["coords"][0].tolist() if len(loaded["coords"]) else None,
}
print("FSD_RESULT_BEGIN"); print(json.dumps(out, indent=2, default=str)); print("FSD_RESULT_END")
with open(f"{os.environ['OUT']}/phase1_result.json", "w") as f:
    json.dump(out, f, indent=2, default=str)
PY
.venv/bin/python "$OUT/phase1.py"
```
- **Expect:** **one** AML job in the Studio UI (not 16 — this is a reduce, D3), then the compact
  array appears locally under `$OUT/landed`.
- **PASS if:** `data_shape` is `(pixels, 8, 3)` (T=8 for the runbook-36 Apr–Sep 2018 @ 20-day window,
  3 bands after SCL is masked); `ids_len == pixels`; `labels_present: true` and `labels_len ==
  pixels` (the `input.csv` carries labels); `coords_sample` values are in `[-180,180]`/`[-90,90]`
  (EPSG:4326, spec 05); **record `data_npy_bytes`** — this replaces the D3 "tens to low-hundreds of
  MB" estimate with a measurement (update `LIMITATIONS.md` with the real number).
- **FAIL signature — `ValueError: Attribute timestamps are not consistent`:** a cube with a
  different mosaic window slipped into `input.csv` (`_check_metadata_consistency`,
  `flatten.py:82`) — inspect which `id` and fix the manifest, don't retry blindly.
- **Cost:** one AML node for the reduce's duration (proportional to reading ~900 cubes over the
  seam, not to their total bytes — flatten keeps only non-nodata pixels).

## Phase 2 — full one-verb e2e on a SMALL fresh subset (proves the composition)

> Pick a **few** `AT_2018_TRAIN` fields (bound the MPC download cost — this is not a scale test,
> Phase 1 already proved scale). 3–5 fields is enough to prove download→build→flatten→land-local
> chains correctly.

```bash
cat > "$OUT/phase2.py" <<'PY'
import json, os
import geopandas as gpd
from fsd import api

fields = gpd.read_file("../shapefiles/austria_eurocrops_sampled_ethiopia_translated.geojson")
small = fields[fields["fid"].isin(fields["fid"].iloc[:4])]   # a handful of fields

BANDS = ["B04", "B08", "B8A", "SCL"]
STARTDATE, ENDDATE, MOSAIC_DAYS = "2018-04-01", "2018-09-01", 20

runner_kwargs = dict(
    cluster=os.environ["AZ_CLUSTER"],
    environment=f"{os.environ['AZ_ENV_NAME']}:{os.environ['AZ_ENV_VERSION']}",
    root=os.environ["AZ_ROOT"] + "/phase2-e2e",
    identity_client_id=os.environ["AZ_UAMI_CLIENT_ID"],
    subscription_id=os.environ["AZ_SUBSCRIPTION_ID"], resource_group_name=os.environ["AZ_RG"],
    workspace_name=os.environ["AZ_ML_WORKSPACE"],
)

td = api.create_training_data(
    label_polygons=small,   # in-memory gdf -- auto-staged to the blob root (Q3)
    catalog_filepath=os.environ["AZ_ROOT"] + "/phase2-e2e/catalog.parquet",
    startdate=STARTDATE, enddate=ENDDATE, mosaic_days=MOSAIC_DAYS, bands=BANDS,
    id_col="fid", label_col="EC_hcat_n",
    export_folderpath=f"{os.environ['OUT']}/phase2_landed",   # LOCAL
    source="mpc", download=True, max_tiles=10,
    runner="aml", runner_kwargs=runner_kwargs,
)

expected_t = api.compute_n_timestamps(STARTDATE, ENDDATE, MOSAIC_DAYS)
out = {
    "phase": "phase2-full-e2e-small-subset", "pass": True,
    "n_pixels": td.n_pixels, "n_timestamps": td.n_timestamps, "expected_t": expected_t,
    "bands": td.bands, "n_bands": len(td.bands),
    "catalog_on_blob": True, "export_folderpath": td.export_folderpath,
}
print("FSD_RESULT_BEGIN"); print(json.dumps(out, indent=2, default=str)); print("FSD_RESULT_END")
with open(f"{os.environ['OUT']}/phase2_result.json", "w") as f:
    json.dump(out, f, indent=2, default=str)
PY
.venv/bin/python "$OUT/phase2.py"
```
- **Optional — driver-side features:** add `adapter=DemoRF()` to the `create_training_data(...)`
  call above and assert `fs.exists(f"{OUT}/phase2_landed/features.npy")` afterward — proves D2's
  "features run on the driver, after land-local" for the aml path.
- **Expect:** catalog + per-field cubes appear under `$AZ_ROOT/phase2-e2e`; the local array lands
  under `$OUT/phase2_landed`.
- **PASS if:** `n_timestamps == expected_t`; `n_bands == len(BANDS) - 1` (SCL is masked, not a
  data band); the run completes with no failed job at any of the three phases (download/build/
  flatten).
- **If it fails:** paste `$OUT/phase2_result.json`; a `PreflightError` naming `max_tiles` means the
  subset's window matched more MGRS tiles than expected — narrow the fields or raise `max_tiles`.

## Success criteria (`_result.json`)
Each phase writes `$OUT/phase<N>_result.json`, e.g.:
```json
{ "phase": "phase1-flatten-reduce-at-scale", "pass": true,
  "n_pixels": 12345, "n_timestamps": 8, "data_npy_bytes": 4000000 }
```
Paste these back (not the AML job logs) — Claude diffs them against the PASS conditions above.

## Stop / observe
- Progress: `az ml job stream -n <job-name> -g "$AZ_RG" -w "$AZ_ML_WORKSPACE"` (job names are in
  `runners.run_aml_flatten`'s returned `job_statuses`). Studio URL prints at submission.
- Abort: `Ctrl-C` the Python driver (an already-submitted AML job keeps running — cancel with
  `az ml job cancel -n <job-name> ...`).
- Re-run: land-local (`storage.transfer`) is existence-checked — a re-run skips already-landed
  files. The reduce itself recomputes (cheap; it overwrites one array, D7). **Do not**
  `fs.rm(prefix, recursive=True)` to "clean up" — broken on `abfss://` (TODO #50); re-running is
  self-healing.
