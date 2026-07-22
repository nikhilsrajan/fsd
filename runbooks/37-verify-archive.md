# Run-book: 37 verify-archive — is `$AZ_ROOT/archive` trustworthy?

> Spec-24 run-book. **You** run this; paste back each step's `_result.json`. Claude diffs them
> against the criteria here and never reads your logs.
>
> **Concrete `rise` values are NOT in this file** (public repo). Paste them as env vars from the
> uncommitted `../../AZURE_INFRA_PRIVATE.md` (workspace root).

## Purpose

`runbooks/37-download-on-aml.md` Phase 3 landed **3456 assets / 576 granules** on
`$AZ_ROOT/archive` and reported `0 failed`. That says the *jobs* succeeded. It does **not** say the
archive is usable. Two gates stand between it and `runbooks/36-aml-runner.md`:

1. **Radiometry (hard gate).** Spec 34's whole guarantee is that each COG carries the right GDAL
   `scale`/`offset`. TODO #44 exists because those were once wrong (`offset=-1000` DN paired with
   `scale=1/10000`) and rendered all-black. The AML image was built from a **wheel of unknown
   vintage** — if it predates the fix (`c2bf1f1`), the whole archive is mis-tagged and every
   datacube built on it is silently wrong. Never checked. Steps 4–5.
2. **Catalog completeness.** Run-book 36 builds datacubes from `archive/catalog.parquet`; anything
   missing from that file is silently missing from every cube. Steps 1–3.

**This run-book writes nothing to the archive.** Every step is a read; the only writes are local,
under `$OUT`. Nothing here can make the archive worse.

### One prediction to check first, because it changes how you read Step 1

All 16 Phase-3 shards were handed the **same** `--catalog` url (`runners.py:645`), and
`TileCatalog.append` is a read-modify-write of that one parquet (`catalog.py:106-136`) with no lock
and no per-shard file. Shards finished 105.7–192.1 s in (TODO #48), so their appends overlapped.
**If that race bit, the bytes are all on blob but the catalog under-reports them** — Step 1's row
count comes in under 576 while Step 2 finds the files present but *undeclared*. That is the
signature to look for; Steps 1+2 together tell "we didn't download it" apart from "we downloaded it
and lost the catalog row", which are very different problems.

## Prerequisites
- **VPN connected**, `az login` done, correct subscription selected — the driver does blob I/O in
  every step. `ErrorCode:AuthorizationFailure` = network rules (VPN), **not** RBAC.
- `cd fsd && source .venv/bin/activate` with `[dev,azure,mpc]` installed.
- Phase 3 of `runbooks/37-download-on-aml.md` complete (the archive exists).
- ~150 MB of local disk + one MPC asset download for Step 5.

## Setup — paste your concrete values (from `AZURE_INFRA_PRIVATE.md`, uncommitted)
```bash
cd fsd
export AZ_ACCOUNT='<storage account>'
export AZ_FS='<filesystem/container>'
export AZ_ROOT="abfss://${AZ_FS}@${AZ_ACCOUNT}.dfs.core.windows.net/fsd-p2-download"
export AZ_ARCHIVE="${AZ_ROOT}/archive"
export AZ_CATALOG="${AZ_ARCHIVE}/catalog.parquet"
export AZ_BANDS='B02,B03,B04,B08,B8A,SCL'

export OUT="$PWD/tests/outputs/p2_verify_archive"   # gitignored
mkdir -p "$OUT"

# The ROI Phase 3 actually used -- don't guess the filename, list what you pushed:
.venv/bin/python -c "
from fsd.storage import fs; import os
print('\n'.join(fs.ls(os.environ['AZ_ROOT'] + '/_inputs')))"
export AZ_ROI_REAL_URL="${AZ_ROOT}/_inputs/<the one Phase 3 used, e.g. AT_ROI.geojson>"

# The EXACT dates Phase 3 ran with -- read them off the script you ran, don't retype from memory.
# (This is the whole point of Step 3: the dry run in Phase 3b and the run in Phase 3c were typed
# separately, so a one-day difference between them is a live hypothesis for 3432 vs 3456.)
grep -n '20[0-9][0-9]-' tests/outputs/p2_download_aml/phase3.py
export AZ_START='<startdate from the line above>'
export AZ_END='<enddate from the line above>'
# If you still know what you typed into Phase 3b's dry run and it differs, set these too
# (leave them equal to AZ_START/AZ_END if it was the same):
export AZ_START_3B="$AZ_START"
export AZ_END_3B="$AZ_END"

echo "archive=$AZ_ARCHIVE  roi=$AZ_ROI_REAL_URL"
echo "window=$AZ_START..$AZ_END (3b: $AZ_START_3B..$AZ_END_3B)"
```
- **PASS if:** the `_inputs` listing shows your ROI, the `grep` prints the two date literals, and
  both echoes show fully-substituted values (no `<...>` placeholders left). If `phase3.py` is gone,
  say so — Step 3 still runs, it just loses the 3b-vs-3c comparison.

## Step 1 — what the catalog says landed (gate 2a)

```bash
cat > "$OUT/step1.py" <<'PY'
import collections, json, os, re
import pandas as pd
from fsd.catalog.catalog import TileCatalog

cat = TileCatalog(os.environ["AZ_CATALOG"])
gdf = cat.read()

files = gdf["files"].fillna("").apply(lambda s: [f for f in s.split(",") if f])
n_assets = int(files.apply(len).sum())
bands = sorted({os.path.splitext(f)[0] for fl in files for f in fl})
mgrs = gdf["id"].str.extract(r"_(T\d{2}[A-Z]{3})_", expand=False)
ts = pd.to_datetime(gdf["timestamp"], utc=True)
dates = ts.dt.date
per_date = collections.Counter(dates)
decl = cat.declaration

out = {
    "step": "1-catalog-inventory", "status": "ok",
    "metrics": {
        "n_rows_granules": int(len(gdf)),
        "n_assets": n_assets,
        "bands_seen": bands,
        "files_per_granule": {str(k): int(v) for k, v in
                              collections.Counter(files.apply(len)).items()},
        "mgrs_tiles": sorted(x for x in mgrs.dropna().unique()),
        "n_distinct_dates": int(len(per_date)),
        "date_min": str(min(per_date)), "date_max": str(max(per_date)),
        "granules_on_date_min": int(per_date[min(per_date)]),
        "granules_on_date_max": int(per_date[max(per_date)]),
        "offset_values": {str(k): int(v) for k, v in gdf["offset"].value_counts().items()},
        "nodata_values": {str(k): int(v) for k, v in gdf["nodata"].value_counts().items()},
        "declaration_stamped": decl is not None,
        "declaration": repr(decl)[:200] if decl is not None else None,
        "duplicate_ids": int(len(gdf) - gdf["id"].nunique()),
    },
    "expected": {"n_rows_granules": 576, "n_assets": 3456,
                 "bands_seen": os.environ["AZ_BANDS"].split(","),
                 "declaration_stamped": True, "duplicate_ids": 0},
    "error": None,
}
out["pass"] = (out["metrics"]["n_assets"] == 3456
               and out["metrics"]["declaration_stamped"]
               and out["metrics"]["duplicate_ids"] == 0)
print("FSD_RESULT_BEGIN"); print(json.dumps(out, indent=2)); print("FSD_RESULT_END")
with open(f"{os.environ['OUT']}/step1_result.json", "w") as f:
    json.dump(out, f, indent=2)
PY
.venv/bin/python "$OUT/step1.py"
```
- **Expect:** `n_rows_granules: 576`, `n_assets: 3456`, `bands_seen` = your 6 bands,
  `files_per_granule: {"6": 576}`, `declaration_stamped: true`.
- **PASS if:** `pass: true`.
- **FAIL — `declaration_stamped: false`:** **stop, this blocks run-book 36 outright.** Spec 35 makes
  `build_datacube` *raise* on an unstamped file-sourced catalog, so every Phase-1 task would die.
  Fix with `python -m fsd.catalog.restamp_cli` (spec 35 §6) before anything else.
- **FAIL — `n_rows_granules` well under 576:** the predicted concurrent-append race. Do **not**
  re-download; go straight to Step 2, which distinguishes lost rows from missing bytes.
- **Watch even on a pass:** `offset_values` should hold one or two values only (`0` and/or `-1000`,
  DN units). Anything else means the offset column is not what spec 34 §1a assumes, and Step 4's
  rule needs revisiting before you trust it.

## Step 2 — what actually landed on blob, vs what the catalog declares (gate 2b)

The decisive step. `fs.glob` lists the archive itself; the catalog is only a claim about it.

```bash
cat > "$OUT/step2.py" <<'PY'
import json, os, random
from fsd.storage import fs
from fsd.catalog.catalog import TileCatalog

archive = os.environ["AZ_ARCHIVE"].rstrip("/")
gdf = TileCatalog(os.environ["AZ_CATALOG"]).read()

def key(path):                     # "<granule-id>/<BAND>.tif", scheme-independent
    return "/".join(path.rstrip("/").split("/")[-2:])

declared = set()
for _, r in gdf.iterrows():
    granule = os.path.basename(str(r["local_folderpath"]).rstrip("/"))
    for f in str(r["files"]).split(","):
        if f:
            declared.add(f"{granule}/{f}")

print("listing the archive prefix (one paged call, may take a minute)...", flush=True)
on_blob = {key(p) for p in fs.glob(f"{archive}/*/*.tif")}

missing = sorted(declared - on_blob)        # catalog claims it; blob doesn't have it
undeclared = sorted(on_blob - declared)     # blob has it; catalog never recorded it

# Zero-byte leftovers would be silently "skipped" by a re-run's idempotency check.
sample = random.Random(0).sample(sorted(on_blob), min(20, len(on_blob)))
sizes = {k: fs.size(f"{archive}/{k}") for k in sample}

out = {
    "step": "2-blob-vs-catalog", "status": "ok",
    "metrics": {
        "n_files_on_blob": len(on_blob),
        "n_declared_in_catalog": len(declared),
        "n_declared_but_missing_on_blob": len(missing),
        "n_on_blob_but_undeclared": len(undeclared),
        "missing_sample": missing[:10],
        "undeclared_sample": undeclared[:10],
        "undeclared_granules": len({k.split("/")[0] for k in undeclared}),
        "sampled_sizes_min_bytes": min(sizes.values()) if sizes else None,
        "n_zero_byte_in_sample": sum(1 for v in sizes.values() if v == 0),
    },
    "expected": {"n_files_on_blob": 3456, "n_declared_but_missing_on_blob": 0,
                 "n_on_blob_but_undeclared": 0, "n_zero_byte_in_sample": 0},
    "error": None,
}
out["pass"] = (out["metrics"]["n_declared_but_missing_on_blob"] == 0
               and out["metrics"]["n_on_blob_but_undeclared"] == 0
               and out["metrics"]["n_zero_byte_in_sample"] == 0)
print("FSD_RESULT_BEGIN"); print(json.dumps(out, indent=2)); print("FSD_RESULT_END")
with open(f"{os.environ['OUT']}/step2_result.json", "w") as f:
    json.dump(out, f, indent=2)
PY
.venv/bin/python "$OUT/step2.py"
```
- **Expect:** `n_files_on_blob: 3456`, both diffs `0`.
- **PASS if:** `pass: true`.
- **How to read a failure — the two cases are opposite problems:**
  - `n_on_blob_but_undeclared > 0` (files present, no catalog row) ⇒ **the catalog lost updates**,
    the bytes are fine. Nothing to re-download; the catalog needs rebuilding from what is on blob,
    and the fan-out needs per-shard catalogs. Paste the numbers — this is a code fix, not an ops fix.
  - `n_declared_but_missing_on_blob > 0` (row present, file absent) ⇒ **real data loss**: a transfer
    was recorded that did not land, or something deleted under the prefix (see TODO #50 —
    `fs.rm(..., recursive=True)` deletes and *then* raises).
- **FAIL — `n_zero_byte_in_sample > 0`:** truncated transfers that a re-run would **skip**
  (`_transfer_and_stamp_one` skips any existing non-empty file — a zero-byte one it would retry, but
  a partially-written non-empty one it would not). Report the sample; do not re-run blindly.

## Step 3 — the 3432 vs 3456 discovery drift (gate 2c)

Discovery is **not** authoritative here — the blob listing from Step 2 is. What this step settles is
whether the *query* is stable, which is what decides between "MPC ingested items between the two
queries" (nothing to fix) and "STAC paging is non-deterministic" (a new TODO). Two back-to-back
discoveries answer that directly. Driver-side STAC only — **no bytes move.**

```bash
cat > "$OUT/step3.py" <<'PY'
import collections, json, os
import pandas as pd
from fsd.sources import mpc

roi = os.environ["AZ_ROI_REAL_URL"]
bands = os.environ["AZ_BANDS"].split(",")
archive = os.environ["AZ_ARCHIVE"]

def discover(start, end, as_timestamp=False):
    if as_timestamp:
        start, end = pd.Timestamp(start), pd.Timestamp(end)
    rows = mpc.discover_shard_rows(roi, start, end, bands, archive)
    return {f'{r["tile_id"]}/{r["band"]}.tif' for r in rows}, rows

# Pass the dates the SAME WAY the run did -- as bare strings. pystac-client expands a
# date-only *string* to the whole day (`2019-01-01` -> `...T23:59:59Z`) but treats a
# *datetime* as an exact instant (`...T00:00:00Z`), so the two forms are different
# windows for identical-looking dates. Both are measured here; see TODO #52.
print("discovery 1/2 (phase-3 window, string dates -- as the run passed them)...", flush=True)
a, rows_a = discover(os.environ["AZ_START"], os.environ["AZ_END"])
print("discovery 2/2 (same window, repeated -- tests paging determinism)...", flush=True)
b, _ = discover(os.environ["AZ_START"], os.environ["AZ_END"])
print("discovery 3 (same dates as pd.Timestamp -- the instant-semantics window)...", flush=True)
ts_form, _ = discover(os.environ["AZ_START"], os.environ["AZ_END"], as_timestamp=True)

c = None
if (os.environ["AZ_START_3B"], os.environ["AZ_END_3B"]) != (os.environ["AZ_START"], os.environ["AZ_END"]):
    print("discovery 3 (the phase-3b dry-run window)...", flush=True)
    c, _ = discover(os.environ["AZ_START_3B"], os.environ["AZ_END_3B"])

from fsd.storage import fs                       # step 2 kept only samples -- re-list the set here
print("listing the archive prefix...", flush=True)
blob = {"/".join(p.rstrip("/").split("/")[-2:]) for p in fs.glob(f"{archive.rstrip('/')}/*/*.tif")}

import re
by_date = collections.Counter(pd.Timestamp(r["timestamp"]).date() for r in rows_a)
only_disc = sorted(a - blob)
only_blob = sorted(blob - a)
sensing_date = lambda k: (re.search(r"_(\d{8})T", k).group(1) if re.search(r"_(\d{8})T", k) else "?")

out = {
    "step": "3-discovery-drift", "status": "ok",
    "metrics": {
        "discovery_1_assets": len(a), "discovery_2_assets": len(b),
        "discovery_repeatable": a == b,
        "discovery_timestamp_form_assets": len(ts_form),
        "str_vs_timestamp_delta": len(a) - len(ts_form),
        "discovery_3b_window_assets": (len(c) if c is not None else None),
        "b3_window_differs": c is not None,
        "n_assets_on_blob": len(blob),
        "only_in_discovery": len(only_disc), "only_on_blob": len(only_blob),
        "only_in_discovery_sample": only_disc[:10], "only_on_blob_sample": only_blob[:10],
        # sensing date parsed from the granule id -- says WHERE in the window the
        # difference sits (a window-edge date points at an operator date mismatch).
        "sensing_dates_only_on_blob": sorted({sensing_date(k) for k in only_blob}),
        "sensing_dates_only_in_discovery": sorted({sensing_date(k) for k in only_disc}),
        "discovery_first_date": str(min(by_date)), "discovery_last_date": str(max(by_date)),
        "granules_on_first_date": round(by_date[min(by_date)] / max(len(bands), 1)),
        "granules_on_last_date": round(by_date[max(by_date)] / max(len(bands), 1)),
    },
    "expected": {"discovery_repeatable": True, "only_in_discovery": 0, "only_on_blob": 0},
    "error": None,
}
out["pass"] = out["metrics"]["discovery_repeatable"] and not only_disc and not only_blob
print("FSD_RESULT_BEGIN"); print(json.dumps(out, indent=2)); print("FSD_RESULT_END")
with open(f"{os.environ['OUT']}/step3_result.json", "w") as f:
    json.dump(out, f, indent=2)
PY
.venv/bin/python "$OUT/step3.py"
```
- **Expect:** both discoveries return the same count, and it matches what is on blob.
- **PASS if:** `pass: true`.
- **Reading the outcome — four cases, three of them benign:**

  | what you see | what it means | action |
  |---|---|---|
  | `discovery_1 == discovery_2 == n_assets_on_blob` | everything discovered landed and the query is stable | none |
  | `str_vs_timestamp_delta > 0` and `sensing_dates_only_on_blob` = **the window's end date** | **the str/Timestamp window difference (TODO #52)** — the run passed bare date strings (whole-day end), the 3b dry run wrapped them in `pd.Timestamp` (instant end), so the run legitimately collected one extra acquisition day | no data action; the archive is a superset of the intended window |
  | `discovery_3b_window_assets` differs with a different 3b window | you typed **different dates** into the dry run and the run | none — an operator input difference |
  | `discovery_repeatable: false` | **STAC paging is non-deterministic** — the same query returns different asset sets | **new TODO**, do not fix here |
  | `only_on_blob > 0` on dates **inside** the window, with a repeatable discovery | the archive holds granules MPC no longer returns (superseded/reprocessed, spec 33 dedupe) | report — it affects Step 5's id comparison |
  | `only_in_discovery > 0` | assets the query finds that never landed — **real under-download** | investigate before run-book 36 |

  **This step failing is not automatically a blocker.** `only_in_discovery: 0` is the load-bearing
  number: it says nothing was missed. `only_on_blob > 0` means the archive is a *superset* of the
  query, which is harmless as long as you know why.

- **Cost:** three STAC queries over a year. Minutes, no bytes.

## Step 4 — radiometry: the tags on the archive itself (gate 1, part A)

The rule comes straight from spec 34 §1a and needs no reference download: a **reflectance** band
must carry `scale = 1/10000` with `offset = <catalog DN offset> / 10000` (so `0.0` or `-0.1`);
**SCL is not reflectance** — `scale = 1.0`, `offset = 0.0`. The bug TODO #44 documents is
`offset = -1000` sitting next to `scale = 1/10000`.

The window read is not decoration: it proves GDAL can actually open and decode the blob COGs, which
is exactly what run-book 36's datacube builder will do.

```bash
cat > "$OUT/step4.py" <<'PY'
import json, os
import pandas as pd
import rasterio.windows
from fsd import config
from fsd.catalog.catalog import TileCatalog
from fsd.raster import rio_open

gdf = TileCatalog(os.environ["AZ_CATALOG"]).read().sort_values("id").reset_index(drop=True)

# Sample deterministically: first / middle / last, plus one granule per distinct
# catalog offset value so both radiometric baselines get checked if both are present.
idx = {0, len(gdf) // 2, len(gdf) - 1}
for off in gdf["offset"].unique():
    idx.add(int(gdf.index[gdf["offset"] == off][0]))
sample = gdf.loc[sorted(idx)]

REFL, SCALE = "B04", config.S2_REFLECTANCE_SCALE
checks = []
for _, r in sample.iterrows():
    folder = str(r["local_folderpath"]).rstrip("/")
    for band in (REFL, "SCL"):
        if f"{band}.tif" not in str(r["files"]).split(","):
            continue
        url = f"{folder}/{band}.tif"
        print(f"reading {band} of {r['id']} ...", flush=True)
        with rio_open(url) as src:
            scale, offset = float(src.scales[0]), float(src.offsets[0])
            w = rasterio.windows.Window(0, 0, min(256, src.width), min(256, src.height))
            arr = src.read(1, window=w)
            info = {
                "id": r["id"], "band": band, "url_tail": "/".join(url.split("/")[-2:]),
                "scale": scale, "offset": offset,
                "catalog_offset_dn": int(r["offset"]),
                "nodata": (None if src.nodata is None else float(src.nodata)),
                "dtype": str(src.dtypes[0]), "crs": str(src.crs),
                "size": [src.width, src.height],
                "window_checksum": int(arr.astype("int64").sum()),
            }
        if band == "SCL":
            info["expected_scale"], info["expected_offset"] = 1.0, 0.0
        else:
            info["expected_scale"] = SCALE
            info["expected_offset"] = int(r["offset"]) * SCALE
        info["tag_ok"] = (abs(info["scale"] - info["expected_scale"]) < 1e-12
                          and abs(info["offset"] - info["expected_offset"]) < 1e-9)
        info["black_tile_bug"] = (abs(info["scale"] - SCALE) < 1e-12
                                  and abs(info["offset"] + 1000.0) < 1e-6)
        info["nodata_ok"] = info["nodata"] == float(config.NODATA)
        checks.append(info)

out = {
    "step": "4-radiometry-tags", "status": "ok",
    "metrics": {
        "n_checked": len(checks),
        "n_tag_ok": sum(c["tag_ok"] for c in checks),
        "n_black_tile_bug": sum(c["black_tile_bug"] for c in checks),
        "n_nodata_ok": sum(c["nodata_ok"] for c in checks),
        "distinct_offsets": sorted({c["offset"] for c in checks}),
        "checks": checks,
    },
    "expected": {"n_tag_ok": len(checks), "n_black_tile_bug": 0, "n_nodata_ok": len(checks)},
    "error": None,
}
out["pass"] = (out["metrics"]["n_tag_ok"] == len(checks)
               and out["metrics"]["n_black_tile_bug"] == 0
               and out["metrics"]["n_nodata_ok"] == len(checks))
print("FSD_RESULT_BEGIN"); print(json.dumps(out, indent=2)); print("FSD_RESULT_END")
with open(f"{os.environ['OUT']}/step4_result.json", "w") as f:
    json.dump(out, f, indent=2)
PY
.venv/bin/python "$OUT/step4.py"
```
- **Expect:** every B04 shows `scale: 0.0001` with `offset: 0.0` or `-0.1`; every SCL shows
  `scale: 1.0, offset: 0.0`; `nodata: 0.0` throughout; `n_black_tile_bug: 0`.
- **PASS if:** `pass: true`.
- **FAIL — `n_black_tile_bug > 0`:** ⛔ **the archive was written by a pre-`c2bf1f1` wheel.**
  Stop. Do not run run-book 36 against it. The AML image needs rebuilding (gate 4) and the archive
  re-ingesting; the science path would not notice, which is exactly why this gate exists.
- **FAIL — a GDAL/`/vsiadls/` read error:** that is an *access* failure, not a radiometry one —
  `runbooks/31-p1-access-probe.md` is the known-green reference for telling the two apart.
- **Note:** a `distinct_offsets` of `[0.0]` alone is not suspicious for 2018 data whose granules were
  never reprocessed to baseline ≥ 04.00; `[-0.1]` alone is equally fine if they all were. What would
  be wrong is `-1000.0`.

## Step 5 — the same granule, ingested locally by *this* checkout (gate 1, part B)

Step 4 checks the tags against the rule. This step checks them against **a fresh ingest by the code
in your working tree**, which is the only way to catch "the AML image carries a different wheel than
the repo". Same granule, same bands, ~150 MB.

```bash
cat > "$OUT/step5.py" <<'PY'
import json, os
import geopandas as gpd
import pandas as pd
import rasterio.windows
from fsd.catalog.catalog import TileCatalog
from fsd.raster import rio_open
from fsd.sources import mpc

OUT = os.environ["OUT"]
with open(f"{OUT}/step4_result.json") as f:
    step4 = json.load(f)
blob_checks = {(c["id"], c["band"]): c for c in step4["metrics"]["checks"]}
target_id = step4["metrics"]["checks"][0]["id"]

gdf = TileCatalog(os.environ["AZ_CATALOG"]).read()
row = gdf[gdf["id"] == target_id].iloc[0]
ts = pd.Timestamp(row["timestamp"])

# A tiny ROI strictly inside the granule footprint pins discovery to this acquisition.
pt = row["geometry"].representative_point().buffer(0.001)
roi = gpd.GeoDataFrame({"id": [target_id]}, geometry=[pt], crs="EPSG:4326")

local_dir = f"{OUT}/local_ingest"
lcat = TileCatalog(f"{local_dir}/catalog.parquet")
print(f"downloading {target_id} B04+SCL locally (~150 MB)...", flush=True)
res = mpc.download(
    roi, (ts - pd.Timedelta(minutes=5)).to_pydatetime(), (ts + pd.Timedelta(minutes=5)).to_pydatetime(),
    ["B04", "SCL"], local_dir, lcat, max_tiles=4, progress=True,
)
local = lcat.read()
same_acq = local[pd.to_datetime(local["timestamp"], utc=True) == ts]
local_id = str(same_acq.iloc[0]["id"]) if len(same_acq) else None

comparisons = []
if local_id is not None:
    for band in ("B04", "SCL"):
        blob = blob_checks.get((target_id, band))
        path = f"{local_dir}/{local_id}/{band}.tif"
        if blob is None or not os.path.exists(path):
            continue
        with rio_open(path) as src:
            w = rasterio.windows.Window(0, 0, min(256, src.width), min(256, src.height))
            arr = src.read(1, window=w)
            loc = {"scale": float(src.scales[0]), "offset": float(src.offsets[0]),
                   "nodata": (None if src.nodata is None else float(src.nodata)),
                   "dtype": str(src.dtypes[0]), "size": [src.width, src.height],
                   "window_checksum": int(arr.astype("int64").sum())}
        comparisons.append({
            "band": band, "blob": {k: blob[k] for k in
                                   ("scale", "offset", "nodata", "dtype", "size", "window_checksum")},
            "local": loc,
            "tags_match": (abs(loc["scale"] - blob["scale"]) < 1e-12
                           and abs(loc["offset"] - blob["offset"]) < 1e-9
                           and loc["nodata"] == blob["nodata"]),
            "pixels_match": loc["window_checksum"] == blob["window_checksum"],
        })

out = {
    "step": "5-blob-vs-local-ingest", "status": "ok",
    "metrics": {
        "blob_granule_id": target_id, "local_granule_id": local_id,
        "ids_identical": local_id == target_id,
        "download": {"successful": res.successful_count, "failed": res.failed_count,
                     "skipped": res.skipped_count},
        "n_compared": len(comparisons),
        "n_tags_match": sum(c["tags_match"] for c in comparisons),
        "n_pixels_match": sum(c["pixels_match"] for c in comparisons),
        "comparisons": comparisons,
    },
    "expected": {"n_tags_match": len(comparisons), "n_pixels_match": len(comparisons),
                 "ids_identical": True},
    "error": None,
}
out["pass"] = (len(comparisons) > 0
               and out["metrics"]["n_tags_match"] == len(comparisons)
               and res.failed_count == 0)
print("FSD_RESULT_BEGIN"); print(json.dumps(out, indent=2)); print("FSD_RESULT_END")
with open(f"{OUT}/step5_result.json", "w") as f:
    json.dump(out, f, indent=2)
PY
.venv/bin/python "$OUT/step5.py"
```
- **Expect:** `ids_identical: true`, `n_tags_match: 2`, `n_pixels_match: 2`.
- **PASS if:** `pass: true` — i.e. the tags a **local ingest by this checkout** produces are the tags
  the **cluster** wrote. That is the deployed-wheel check.
- **FAIL — tags differ:** the AML image's fsd predates the working tree's. Rebuild the image
  (gate 4) **and** re-ingest the archive; run-book 36 stays blocked until then. Paste the
  `comparisons` block — the direction of the difference says which side is stale.
- **`ids_identical: false` (pixels differ, tags match):** benign and expected if Step 3 reported
  `only_on_blob > 0` — MPC has since reprocessed this granule, so you downloaded a *newer* item for
  the same acquisition. Tags matching is still the result that matters; note the id pair.
- **Cleanup:** `rm -rf "$OUT/local_ingest"` once pasted back (it is gitignored either way).

## Success criteria (`_result.json`)

Each step writes `$OUT/step<N>_result.json` in the spec-24 shape:
```json
{ "step": "1-catalog-inventory", "status": "ok", "pass": true,
  "metrics": { "n_assets": 3456 }, "expected": { "n_assets": 3456 }, "error": null }
```
**Paste those five files back** (not the logs). The gates clear when:
- **Gate 1 (radiometry, hard):** steps 4 **and** 5 pass.
- **Gate 2 (catalog):** steps 1 **and** 2 pass. Step 3 is diagnostic — a fail there is a finding to
  record (possibly a new TODO), not necessarily a blocker, as long as steps 1+2 agree that
  everything discovered actually landed and is declared.

Only then is `runbooks/36-aml-runner.md` safe to run.

## Stop / observe
- Steps 1, 2, 4 are blob reads: seconds to a couple of minutes (Step 2's listing is the slowest).
- Step 3 is three STAC queries over a year — minutes, no bytes.
- Step 5 downloads ~150 MB from MPC and prints per-asset progress.
- Abort: `Ctrl-C` any step. Nothing here writes to the archive, so there is no partial state to
  clean up beyond `$OUT`.
