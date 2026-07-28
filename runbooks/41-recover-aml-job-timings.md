# Run-book: 41 — recover the missing AML wall clocks from the workspace's job history

> Spec-24 run-book. **You** run it; paste back `_result.json`. Claude never runs it (CLAUDE.md).
> **Free, read-only, seconds to run.** It starts no jobs, allocates no nodes, writes nothing to
> blob — it only *reads* AML's own record of jobs that already ran.

## Purpose

Two steps of the AML pipeline have **no measured wall clock**, which is what blocks the
local-vs-AML timing report:

| run-book | phase | what is stored | what is missing |
|---|---|---|---|
| 36 | 3 (build 900 cubes) | per-shard `seconds` (16 shards, slowest 213.8 s) | **driver wall** |
| 37 | 3 (archive download) | per-shard `seconds` (16 shards, slowest 192.1 s) | **driver wall** |

Both run-books *now* emit `wall_seconds` (`36:295`, `37:399`) — the instrumentation is already
there; the **stored results predate it**. Re-running Phase 3 of either would measure the resume
path (the 900 cubes and the archive already exist on blob), i.e. the wrong thing.

This run-book asks AML instead: every job carries submit/start/end timestamps in the workspace's
job history. From those we can reconstruct the **job-level span** (first submit → last completion),
which is a **lower bound** on the driver wall, and — more valuable for TODO #59 — the
**queue + node-allocation delay** (submit → start), the single biggest unknown inside the 1084 s of
driver overhead run-book 38 Phase 3 measured.

**It calibrates itself.** Four of the six experiments it queries have a *known, independently
measured* driver wall. If the reconstructed spans do not sit sensibly inside those, the method is
rejected and the two rows stay "not measured" — which is a valid outcome.

| experiment | known driver wall | source |
|---|---|---|
| `fsd-infer-phase3-fanout` | 2066.9 s (slowest shard 982.7) | `tests/outputs/p4_inference_aml/phase3_result.json` |
| `fsd-infer-phase4-merge` | 1082.1 s | `tests/outputs/p4_inference_aml/phase4_result.json` |
| `fsd-download-phase2-n1` | 699.6 s (1 shard, 964 assets) | `tests/outputs/p2_download_aml/phase2_result.json` |
| `fsd-download-phase2-nN` | 493.9 s (8 shards, 964 assets) | same file |

## Prerequisites
- **VPN connected**, `az login` done, correct subscription selected.
- `fsd/.venv` with the `[aml]` extra (`azure-ai-ml` — the same one run-books 36–38 use).
- Nothing else. No cluster, no environment, no bundle.

## Setup — paste your concrete values (from `AZURE_INFRA_PRIVATE.md`, uncommitted)
```bash
cd fsd
source .venv/bin/activate
export AZ_RG='<resource group>'
export AZ_ML_WORKSPACE='<aml workspace>'
export AZ_SUBSCRIPTION_ID='<subscription id>'
export OUT41="$PWD/tests/outputs/p41_job_timings"   # gitignored
mkdir -p "$OUT41"
```

## Steps

### Step 1 — harvest job timestamps

Writes `$OUT41/_result.json` plus `$OUT41/jobs_raw.json` (one raw serialized job, for diagnosis if
the timestamps are not where this script expects).

```bash
cat > "$OUT41/step1.py" <<'PY'
import json, os, re, datetime

from azure.ai.ml import MLClient
from azure.identity import DefaultAzureCredential

OUT = os.environ["OUT41"]

# experiment_name -> (label, known driver wall_seconds or None)
WANT = {
    "fsd-phase3":                  ("rb36 P3 - build 900 cubes",        None),
    "fsd-download-phase3-archive": ("rb37 P3 - archive download",       None),
    "fsd-download-phase2-n1":      ("rb37 P2 - 964 assets, 1 shard",   699.6),
    "fsd-download-phase2-nN":      ("rb37 P2 - 964 assets, 8 shards",  493.9),
    "fsd-infer-phase3-fanout":     ("rb38 P3 - 300-cell inference",   2066.9),
    "fsd-infer-phase4-merge":      ("rb38 P4 - merge only",           1082.1),
}

ml_client = MLClient(DefaultAzureCredential(), os.environ["AZ_SUBSCRIPTION_ID"],
                     os.environ["AZ_RG"], os.environ["AZ_ML_WORKSPACE"])

TIMEISH = re.compile(r"(time|date|created|start|end|complet|finish|duration)", re.I)
ISOISH = re.compile(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}")


def _parse(v):
    """Return a tz-aware datetime for anything that looks like one, else None."""
    if isinstance(v, datetime.datetime):
        return v if v.tzinfo else v.replace(tzinfo=datetime.timezone.utc)
    if isinstance(v, str) and ISOISH.match(v):
        try:
            return datetime.datetime.fromisoformat(v.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def scan_times(obj, prefix="", out=None, depth=0):
    """Recursively collect {dotted.key: iso} for every datetime-looking value."""
    out = {} if out is None else out
    if depth > 6:
        return out
    if isinstance(obj, dict):
        items = obj.items()
    elif hasattr(obj, "__dict__") and not isinstance(obj, (str, bytes)):
        items = vars(obj).items()
    else:
        return out
    for k, v in items:
        key = f"{prefix}{k}".lstrip("_")
        dt = _parse(v)
        if dt is not None and TIMEISH.search(str(k)):
            out[key] = dt.astimezone(datetime.timezone.utc).isoformat()
        elif isinstance(v, (dict,)) or (hasattr(v, "__dict__") and not isinstance(v, (str, bytes))):
            scan_times(v, prefix=key + ".", out=out, depth=depth + 1)
    return out


# --- 1. list the workspace's jobs, keep ours -------------------------------------------------
listed, matched = 0, []
for job in ml_client.jobs.list():
    listed += 1
    if listed > 3000:
        break
    exp = getattr(job, "experiment_name", None)
    if exp in WANT:
        matched.append((exp, job.name, getattr(job, "display_name", None)))

# --- 2. fetch each matched job in full and scan it for timestamps ------------------------------
raw_dumped = False
per_exp = {}
for exp, name, display in matched:
    full = ml_client.jobs.get(name)
    times = scan_times(full)
    cc = getattr(full, "creation_context", None)
    for attr in ("created_at", "last_modified_at"):
        dt = _parse(getattr(cc, attr, None))
        if dt is not None:
            times[f"creation_context.{attr}"] = dt.astimezone(datetime.timezone.utc).isoformat()
    props = getattr(full, "properties", None) or {}
    if isinstance(props, dict):
        for k, v in props.items():
            dt = _parse(v)
            if dt is not None:
                times[f"properties.{k}"] = dt.astimezone(datetime.timezone.utc).isoformat()
    per_exp.setdefault(exp, []).append(
        {"name": name, "display_name": display, "status": getattr(full, "status", None), "times": times}
    )
    if not raw_dumped:
        try:
            raw = full._to_dict()
        except Exception:  # noqa: BLE001 - diagnostic only
            raw = {k: str(v) for k, v in vars(full).items()}
        with open(f"{OUT}/jobs_raw.json", "w") as f:
            json.dump(raw, f, indent=2, default=str)
        raw_dumped = True

# --- 3. aggregate per experiment ---------------------------------------------------------------
def _mins(jobs, keys):
    vals = [j["times"][k] for j in jobs for k in keys if k in j["times"]]
    return (min(vals), max(vals)) if vals else (None, None)


SUBMIT_KEYS = ("creation_context.created_at", "properties.StartTimeUtc")
END_KEYS = ("properties.EndTimeUtc", "creation_context.last_modified_at")

summary = {}
for exp, jobs in sorted(per_exp.items()):
    label, known = WANT[exp]
    keys_seen = sorted({k for j in jobs for k in j["times"]})
    sub_min, sub_max = _mins(jobs, SUBMIT_KEYS)
    end_min, end_max = _mins(jobs, END_KEYS)
    span = None
    if sub_min and end_max:
        span = round(
            (datetime.datetime.fromisoformat(end_max) - datetime.datetime.fromisoformat(sub_min)
             ).total_seconds(), 1
        )
    summary[exp] = {
        "label": label, "n_jobs": len(jobs), "known_driver_wall_seconds": known,
        "time_keys_seen": keys_seen,
        "first_submit": sub_min, "last_submit": sub_max,
        "first_end": end_min, "last_end": end_max,
        "job_span_seconds": span,
        "span_vs_known_ratio": (round(span / known, 3) if (span and known) else None),
    }

# --- 4. calibration verdict --------------------------------------------------------------------
# A reconstructed span is credible if, for every experiment with a KNOWN driver wall, it lands
# inside (0.5x, 1.05x) of it -- it must not exceed the wall (the driver started first and stopped
# last) and must not be a small fraction of it (that would mean we picked up the wrong field).
calib = {}
for exp, s in summary.items():
    if s["known_driver_wall_seconds"] and s["job_span_seconds"]:
        r = s["span_vs_known_ratio"]
        calib[exp] = {"ratio": r, "ok": bool(0.5 < r <= 1.05)}
n_calib = len(calib)
n_ok = sum(1 for c in calib.values() if c["ok"])
recovered = [e for e in ("fsd-phase3", "fsd-download-phase3-archive")
             if summary.get(e, {}).get("job_span_seconds")]

out = {
    "step": "1-harvest-aml-job-timestamps",
    "status": "ok",
    "pass": bool(n_calib >= 2 and n_ok == n_calib and len(recovered) == 2),
    "metrics": {
        "n_jobs_listed": listed, "n_jobs_matched": len(matched),
        "experiments_found": sorted(per_exp), "n_calibration_experiments": n_calib,
        "n_calibration_ok": n_ok, "calibration": calib,
        "recovered_spans_for": recovered, "summary": summary,
    },
    "expected": {
        "n_calibration_experiments": ">= 2",
        "n_calibration_ok": "== n_calibration_experiments",
        "recovered_spans_for": ["fsd-phase3", "fsd-download-phase3-archive"],
    },
    "error": None,
}
print("FSD_RESULT_BEGIN"); print(json.dumps(out, indent=2, default=str)); print("FSD_RESULT_END")
with open(f"{OUT}/_result.json", "w") as f:
    json.dump(out, f, indent=2, default=str)
PY
.venv/bin/python "$OUT41/step1.py"
```

> ✅ **RUN 2026-07-28 — done, do not re-run.** Result below; go to Step 1b. Kept in full because it
> is the record of how the timestamps were located.
>
> 226 jobs listed, **113 matched**, all six experiments present, and
> `properties.StartTimeUtc` + `properties.EndTimeUtc` on every one of them. It reported
> `pass: false`, and **both of its PASS criteria turned out to be wrong**, in ways worth keeping:
>
> - **The 0.5× lower bound was unjustified.** It assumed a job span could not be much smaller than
>   the wall containing it. `fsd-infer-phase3-fanout` came in at **0.527** and is entirely
>   legitimate: the driver owned 978 of those 2066.9 s. A small ratio is the *finding*, not a
>   symptom. Only `ratio <= 1.02` is a real rule.
> - **Aggregating per experiment merges attempts.** `fsd-infer-phase4-merge` holds **48** jobs
>   (3 × 16 — the two failed Phase-4 runs plus the good one) and
>   `fsd-download-phase3-archive` holds **24**. Min-to-max across all of them spans hours, hence
>   Phase 4's bogus 4.98×. Step 1b groups by attempt.
> - `creation_context.created_at` is **not** the submit time — several jobs carry a `created_at`
>   *later* than their own `EndTimeUtc`. Ignore it; use `StartTimeUtc`.
>
> **Recovered:** run-book 36 Phase 3 = 16 jobs, one clean attempt, executing 15:49:57 → 15:55:21 UTC
> on 2026-07-22 ⇒ **job span 324 s**, a lower bound on its missing driver wall.

### Step 1b — per-job timestamps, grouped into attempts (free, read-only)

> ✅ **RUN 2026-07-28 — `pass: true`, do not re-run.** All four calibrations passed
> (0.846 / 0.836 / 0.527 / 0.692). `fsd-infer-phase4-merge` split into the expected attempts and
> `fsd-download-phase3-archive` into two — an 8-job attempt that was **Cancelled** and the real
> 16-job run (span **328 s**). `fsd-phase3` span **324 s**. Combining each span with the driver's own
> `_result.json` write time closed every wall exactly; see `demos/E2E_AUSTRIA_AML.md` §6.1.
>
> ⚠️ **Timezone gotcha, for anyone reading the two result files side by side.** Step 1 printed
> absolute times **2 h earlier** than Step 1b, because Step 1 called `.astimezone(utc)` on a value
> that was already local-aware. **Step 1b's naive timestamps are the true UTC** — independently
> confirmed by the `_result.json` write times, which land 12–16 min after the last job under that
> reading and ~2 h *before* it under the other. **All durations in both files are unaffected**;
> only the absolute labels differed.

**Run this after Step 1.** Step 1 proved the timestamps exist (`properties.StartTimeUtc` /
`properties.EndTimeUtc`, both present on all 113 matched jobs) and that `StartTimeUtc` is the
**execution** start, not the submit time — the `n_shards=1` download job's span (592 s) exceeds its
own in-job `seconds` (577.6) by just 14.4 s, which is a container wrapper, not a node allocation.

Step 1 had one real flaw: it aggregated `min`/`max` over a whole **experiment**, and two experiments
contain **several attempts** of the same phase (`fsd-infer-phase4-merge` has **48** jobs = 3 × 16,
the two failed Phase-4 runs plus the good one; `fsd-download-phase3-archive` has **24**, not 16).
Min-to-max across all of them spans hours, which is why Phase 4 "calibrated" at 4.98×. That is a
grouping bug, not a bad method — and it is exactly the run we need clean.

This step keeps every job's own start/end, splits an experiment into attempts on a gap in start
times, and reports each attempt separately.

```bash
cat > "$OUT41/step1b.py" <<'PY'
import datetime, json, os, re

from azure.ai.ml import MLClient
from azure.identity import DefaultAzureCredential

OUT = os.environ["OUT41"]
GAP_SECONDS = 900          # a start-time gap this large begins a new attempt

# experiment -> (label, known driver wall, in-job slowest `seconds` from the stored _result.json)
WANT = {
    "fsd-phase3":                  ("rb36 P3 - build 900 cubes",       None,   213.779),
    "fsd-download-phase3-archive": ("rb37 P3 - archive download",      None,   192.081),
    "fsd-download-phase2-n1":      ("rb37 P2 - 964 assets, 1 shard",   699.6,  577.622),
    "fsd-download-phase2-nN":      ("rb37 P2 - 964 assets, 8 shards",  493.9,  113.663),
    "fsd-infer-phase3-fanout":     ("rb38 P3 - 300-cell inference",   2066.9,  982.7),
    "fsd-infer-phase4-merge":      ("rb38 P4 - merge only",           1082.1,  None),
}

ml_client = MLClient(DefaultAzureCredential(), os.environ["AZ_SUBSCRIPTION_ID"],
                     os.environ["AZ_RG"], os.environ["AZ_ML_WORKSPACE"])
ISOISH = re.compile(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}")


def _dt(v):
    if isinstance(v, datetime.datetime):
        return v if v.tzinfo else v.replace(tzinfo=datetime.timezone.utc)
    if isinstance(v, str) and ISOISH.match(v):
        try:
            return datetime.datetime.fromisoformat(v.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


jobs_by_exp = {}
for job in ml_client.jobs.list():
    exp = getattr(job, "experiment_name", None)
    if exp not in WANT:
        continue
    full = ml_client.jobs.get(job.name)
    props = getattr(full, "properties", None) or {}
    start, end = _dt(props.get("StartTimeUtc")), _dt(props.get("EndTimeUtc"))
    if start is None:
        continue
    jobs_by_exp.setdefault(exp, []).append({
        "display_name": getattr(full, "display_name", None),
        "status": getattr(full, "status", None),
        "start": start, "end": end,
        "job_seconds": round((end - start).total_seconds(), 1) if end else None,
    })

report = {}
for exp, jobs in sorted(jobs_by_exp.items()):
    label, known, slowest_in_job = WANT[exp]
    jobs.sort(key=lambda j: j["start"])
    attempts, cur = [], [jobs[0]]
    for prev, j in zip(jobs, jobs[1:]):
        if (j["start"] - prev["start"]).total_seconds() > GAP_SECONDS:
            attempts.append(cur); cur = []
        cur.append(j)
    attempts.append(cur)

    out_attempts = []
    for a in attempts:
        starts = [j["start"] for j in a]
        ends = [j["end"] for j in a if j["end"]]
        durs = [j["job_seconds"] for j in a if j["job_seconds"] is not None]
        span = round((max(ends) - min(starts)).total_seconds(), 1) if ends else None
        out_attempts.append({
            "n_jobs": len(a),
            "statuses": sorted({j["status"] for j in a}),
            "first_start": min(starts).isoformat(),
            "last_start": max(starts).isoformat(),
            "last_end": max(ends).isoformat() if ends else None,
            "start_stagger_seconds": round((max(starts) - min(starts)).total_seconds(), 1),
            "job_span_seconds": span,
            "longest_job_seconds": max(durs) if durs else None,
            "shortest_job_seconds": min(durs) if durs else None,
            "sum_job_seconds": round(sum(durs), 1) if durs else None,
            # per-job container wrapper: AML job duration minus the work the shard reported
            "wrapper_seconds_vs_stored_slowest": (
                round(max(durs) - slowest_in_job, 1)
                if (durs and slowest_in_job is not None) else None
            ),
            # driver time spent OUTSIDE the job window (preflight, setup, bundle stage,
            # first-node allocation, post-run collect + STAC)
            "driver_outside_span_seconds": (
                round(known - span, 1) if (known and span) else None
            ),
            "per_job": [
                {"display_name": j["display_name"], "status": j["status"],
                 "start": j["start"].isoformat(),
                 "end": j["end"].isoformat() if j["end"] else None,
                 "job_seconds": j["job_seconds"],
                 "start_offset_seconds": round((j["start"] - min(starts)).total_seconds(), 1)}
                for j in sorted(a, key=lambda x: x["start"])
            ],
        })
    report[exp] = {"label": label, "known_driver_wall_seconds": known,
                   "n_attempts": len(out_attempts), "attempts": out_attempts}

# The good attempt of a multi-attempt experiment is the LAST all-Completed one.
def _good(exp):
    for a in reversed(report[exp]["attempts"]):
        if a["statuses"] == ["Completed"]:
            return a
    return None


calib = {}
for exp, r in report.items():
    if r["known_driver_wall_seconds"]:
        a = _good(exp)
        if a and a["job_span_seconds"]:
            ratio = round(a["job_span_seconds"] / r["known_driver_wall_seconds"], 3)
            calib[exp] = {"ratio": ratio, "n_jobs": a["n_jobs"], "ok": bool(0 < ratio <= 1.02)}

out = {
    "step": "1b-per-job-timestamps-by-attempt", "status": "ok",
    "pass": bool(calib and all(c["ok"] for c in calib.values())),
    "metrics": {"calibration": calib, "report": report},
    # A span may legitimately be a SMALL fraction of the wall -- that just means the driver,
    # not the cluster, owned most of the time. The only hard rule is span <= wall.
    "expected": {"every calibration ratio": "0 < ratio <= 1.02"},
    "error": None,
}
print("FSD_RESULT_BEGIN"); print(json.dumps(out, indent=2, default=str)); print("FSD_RESULT_END")
with open(f"{OUT}/_result_step1b.json", "w") as f:
    json.dump(out, f, indent=2, default=str)
PY
.venv/bin/python "$OUT41/step1b.py"
```

- **Expect:** `fsd-infer-phase4-merge` split into **3 attempts** of 16 (the two known Phase-4 bugs
  plus the good run) and `fsd-download-phase3-archive` into **more than one**; the single-attempt
  experiments (`fsd-phase3`, `fsd-infer-phase3-fanout`, both Phase-2 downloads) unchanged from
  Step 1.
- **PASS if:** every calibration ratio is `0 < ratio <= 1.02`. A job span **must not exceed** the
  driver wall that contains it; there is no lower bound, because a small ratio is itself the finding
  (it means the driver, not the cluster, owned the time).
- **What it buys:** `start_stagger_seconds` is the node ramp-up measured directly, and
  `driver_outside_span_seconds` is everything the driver did before the first job started and after
  the last one ended. Those two are the decomposition TODO #59 has been asking for, and this step
  gets them for free.
- **Runtime:** ~113 `jobs.get` calls; a minute or so over VPN. Read-only.

### Step 2 — measure the archive's size on blob (free, read-only)

> ✅ **RUN 2026-07-28 — `pass: true`, do not re-run.** **3456 tif = 418.0 GB, 121 MB per asset.**
> Per band: B04 96.9 / B08 99.3 / B03 96.4 / B02 95.1 / B8A 29.0 / **SCL 1.21** GB — an 80× spread
> that confirms TODO #60's band-stratification mechanism in bytes. Derived: **171.7 MB/s per node**
> during transfer, **≤ 1.18 GB/s** aggregate — against the laptop's 16.7 MB/s
> (`demos/E2E_AUSTRIA_AML.md` §5). Also the number run-book 42 Step B duplicates on blob.

The local table quotes **44.61 GB / 16.7 MB/s** for its download step. The AML download row cannot
state a throughput because **nothing ever recorded the archive's bytes** — the MPC reports carry
`bytes_downloaded: 0` (only the CDSE path counts bytes). One recursive listing fixes that.

Add your download root first (the one run-book 37 Phase 3 wrote to — run-book 36 calls it
`AZ_ARCHIVE_ROOT`):

```bash
export AZ_ACCOUNT='<storage account>'
export AZ_FS='<filesystem/container>'
export AZ_ARCHIVE_PATH='<path under the container to the archive dir, e.g. nsasiraj/fsd-p2/archive>'
```

```bash
cat > "$OUT41/step2.py" <<'PY'
import collections, json, os

from adlfs import AzureBlobFileSystem
from azure.identity import DefaultAzureCredential

OUT = os.environ["OUT41"]
afs = AzureBlobFileSystem(account_name=os.environ["AZ_ACCOUNT"], credential=DefaultAzureCredential())
root = f"{os.environ['AZ_FS']}/{os.environ['AZ_ARCHIVE_PATH'].strip('/')}"

info = afs.find(root, detail=True)
tifs = {k: v for k, v in info.items() if k.endswith(".tif")}
total = sum(v.get("size", 0) for v in tifs.values())
by_band = collections.Counter()
for k, v in tifs.items():
    by_band[os.path.basename(k)] += v.get("size", 0)

out = {
    "step": "2-archive-bytes-on-blob", "status": "ok",
    "pass": len(tifs) == 3456,
    "metrics": {
        "n_tif": len(tifs), "n_objects_total": len(info),
        "total_bytes": total, "total_gb": round(total / 1e9, 2),
        "mean_mb_per_asset": round(total / max(len(tifs), 1) / 1e6, 2),
        "bytes_by_band": {b: round(n / 1e9, 2) for b, n in sorted(by_band.items())},
    },
    "expected": {"n_tif": 3456},
    "error": None,
}
print("FSD_RESULT_BEGIN"); print(json.dumps(out, indent=2)); print("FSD_RESULT_END")
with open(f"{OUT}/_result_step2.json", "w") as f:
    json.dump(out, f, indent=2)
PY
.venv/bin/python "$OUT41/step2.py"
```

- **Expect:** `n_tif: 3456` (576 granules × 6 bands, the count `37-verify-archive.md` step 2 pinned).
- **PASS if:** `n_tif == 3456`. A different count is not fatal for the timing report — paste it and
  Claude will reconcile it against `p2_verify_archive/step2_result.json` — but it would mean the
  archive changed since it was verified, which is worth knowing on its own.
- **Runtime:** one recursive listing over VPN; tens of seconds. Read-only.

### Step 3 — split the pre-dispatch and post-collect windows (free, read-only)

**Scope reduced after Steps 1 + 1b.** They already established the shape: run-book 38 Phase 3 =
**249 s pre-dispatch + 1089 s of jobs + 729 s post-collect**, and the bundle-upload hypothesis is
**dead** (627 s cannot fit inside a 249 s window). What is still open is the *split within* each
window, which the blobs the driver wrote can answer — every one carries a `last_modified`, and the
run is still on blob:

- **inside the 249 s pre-window** — how much is `setup()`'s per-cell writes vs the bundle stage vs
  dispatch. `input.csv`'s last write ends `setup()`; the `_bundle/` window is the upload; the
  `shards/*.csv` window is dispatch.
- **inside the 729 s post-window** — confirm it is the collect by checking that `catalog.json` is
  the driver's last blob write and that the 300 STAC Items were written sequentially (TODO #61 (c)).

Anchor: **driver t0 = `catalog.json` last-modified − 2066.9 s** (the STAC catalog is the last thing
the driver writes).

```bash
export AZ_ACCOUNT='<storage account>'
export AZ_FS='<filesystem/container>'
# The run root and output folder of runbook 38 Phase 3 (paths under the container, no scheme):
export AZ_P3_RUN='<...>/fsd-p4-inference/runs/phase3-fanout'
export AZ_P3_OUT='<...>/fsd-p4-inference/phase3_out'
```

```bash
cat > "$OUT41/step3.py" <<'PY'
import collections, json, os

from adlfs import AzureBlobFileSystem
from azure.identity import DefaultAzureCredential

OUT = os.environ["OUT41"]
WALL = 2066.9              # runbook 38 Phase 3's measured driver wall
FIRST_JOB_START = "2026-07-28T07:10:32+00:00"   # from Step 1
LAST_JOB_END = "2026-07-28T07:28:41+00:00"

afs = AzureBlobFileSystem(account_name=os.environ["AZ_ACCOUNT"],
                          credential=DefaultAzureCredential())
FSNAME = os.environ["AZ_FS"]


def group(path):
    """Bucket every blob under `path` by a coarse kind, with each bucket's write window."""
    info = afs.find(f"{FSNAME}/{path.strip('/')}", detail=True)
    buckets = collections.defaultdict(list)
    for k, v in info.items():
        base = os.path.basename(k)
        if base in ("input.csv", "catalog.json", "merged.tif"):
            kind = base
        elif "/_bundle/" in k:
            kind = f"_bundle/{base}"
        elif "/shards/" in k:
            kind = "shards/*.csv"
        elif "/_status/" in k:
            kind = "_status/*.json"
        else:
            kind = f"other:{os.path.splitext(base)[1] or base}"
        mt = v.get("last_modified")
        if mt is not None:
            buckets[kind].append((mt, v.get("size", 0)))
    out = {}
    for kind, rows in buckets.items():
        times = sorted(t for t, _ in rows)
        out[kind] = {
            "n": len(rows),
            "bytes": sum(s for _, s in rows),
            "first_written": str(times[0]),
            "last_written": str(times[-1]),
            "write_window_seconds": round((times[-1] - times[0]).total_seconds(), 1),
        }
    return out


run = group(os.environ["AZ_P3_RUN"])
out_folder = group(os.environ["AZ_P3_OUT"])

out = {
    "step": "3-driver-timeline-from-blob", "status": "ok",
    "pass": bool(run) and bool(out_folder),
    "metrics": {
        "wall_seconds": WALL,
        "first_job_start": FIRST_JOB_START, "last_job_end": LAST_JOB_END,
        "run_root": run, "output_folder": out_folder,
    },
    "expected": {
        "_bundle/*": "its write window is the bundle upload -- the 627 s hypothesis",
        "input.csv last_written": "end of setup(), before dispatch",
        "catalog.json last_written": "the driver's final write; t0 = this - wall",
    },
    "error": None,
}
print("FSD_RESULT_BEGIN"); print(json.dumps(out, indent=2, default=str)); print("FSD_RESULT_END")
with open(f"{OUT}/_result_step3.json", "w") as f:
    json.dump(out, f, indent=2, default=str)
PY
.venv/bin/python "$OUT41/step3.py"
```

- **Expect:** a `_bundle/` bucket with 2 files (`bundle.json` + the model artifact), an `input.csv`,
  16 `shards/*.csv`, 16 `_status/*.json`, and in the output folder a `catalog.json` plus 300
  `output.tif`.
- **PASS if:** both groups come back non-empty. There is no threshold to hit — **the numbers are the
  finding**. Claude lays them on the same axis as the job starts/ends and reports where the 977.9 s
  went.
- **What each bucket means:** the `_bundle/` write window is the upload (the hypothesis under test);
  `input.csv`'s last write ends `setup()`; the `shards/*.csv` window is dispatch; `_status/*.json`
  should track the job end times from Step 1; `catalog.json` is the driver's last write, which
  anchors t0.
- **Caveat to respect:** `last_modified` is a *write completion* time, so a bucket's window is the
  span between completions, not the wall of the operation that produced it. For a 2-file bundle it
  brackets the big upload well; for a 1-file bucket the window is 0 and tells you only *when*, not
  *how long*. Claude will not report a duration a single timestamp cannot support.
- **Runtime:** two recursive listings; under a minute. Read-only.

### ~~Step 4 — MLflow fallback~~ — NOT NEEDED

Kept only so the option is on record. The plan was to fall back on MLflow (`pip install mlflow
azureml-mlflow`) if the v2 job object carried no timestamps. **Step 1 found them** —
`properties.StartTimeUtc` and `properties.EndTimeUtc` were present on all 113 matched jobs — so the
extra dependencies are unnecessary. Do not run this.

## Success criteria (`_result.json`)
Each step writes its own file under `$OUT41`: `_result.json` (Step 1), `_result_step1b.json`,
`_result_step2.json`, `_result_step3.json`. Each is
`{step, status, pass, metrics, expected, error}`. **Paste the files** (not the logs).

**A `pass: false` is not automatically a failed step here.** Step 1 returned `pass: false` on its
first run, and the cause was the script's own aggregation (min/max across a whole experiment, which
merges several attempts of the same phase into one bogus span), not the data — which is precisely
what Step 1b fixes. Steps 2 and 3 have no threshold to hit at all: their numbers *are* the result.

## Status (2026-07-28)
- **Step 1 — RUN.** `pass: false`, 226 jobs listed / 113 matched, all 6 experiments found,
  `StartTimeUtc`/`EndTimeUtc` present throughout. Both PASS criteria were wrong (see the box at
  Step 1); the data was fine.
- **Step 1b — RUN, `pass: true`.** All 4 calibrations passed. Spans: rb36 P3 **324 s**,
  rb37 P3 **328 s** (after discarding a cancelled 8-job attempt), rb38 P3 **1089 s**.
- **Together they closed the whole timeline** — with each run's `_result.json` write time as the
  driver's last action: rb38 P3 = 249 pre + 1089 jobs + **729 post**; rb38 P4 = 66 + 44 + **972
  post**; rb36 P3 wall **≥ 343 s**; rb37 P3 wall **≥ 354 s**. → **TODO #61** (the post-run collect
  is the overhead) and `demos/E2E_AUSTRIA_AML.md` §6.1.
- **Step 2 — RUN, `pass: true`.** Archive = **3456 tif / 418.0 GB / 121 MB per asset**; per-band
  totals confirm TODO #60 in bytes (80× B04-vs-SCL). Gives the AML download row its throughput.
- **Step 3 — RUN, `pass: true`.** Both driver windows decompose. **Pre:** `setup()` **22 s**,
  bundle stage **13 s** (13.26 MB — the 627 s guess is dead by measurement), dispatch **8 s**,
  submit→first-job-execution **201 s**. **Post (sums to 972 s exactly):** collect, reads only,
  **616 s** (2.05 s/cell); STAC writes **161 s** (0.53 s/item); merge **193 s**; result write 2 s.
  → TODO #61's fixes (a) and (c) now have price tags.
  - ⚠️ **Post is Phase 4's window, not Phase 3's** — Phase 4 wrote its STAC into the same output
    folder, overwriting Phase 3's Item timestamps (`catalog.json` is stamped 12:22:36 = Phase 4).
    Same collect over the same 300 outputs, so it transfers; the numbers are the merge run's.
  - Also settled the timezone question: the 16 `_status/*.json` blob writes (09:24:13 → 09:28:33)
    fall inside Step 1b's job window, which is impossible under Step 1's reading.
  - Side finding: the 300 inference cubes on blob total **4.13 GB** over 600 `.npy`, against
    `PROGRESS.md`'s 5.48 GB — unreconciled, flagged in `demos/E2E_AUSTRIA_AML.md` §6.2.

## All free recovery is now DONE
Steps 1, 1b, 2 and 3 have run. Everything recoverable without spending has been recovered; what
remains is `runbooks/42-timed-cold-reruns.md` for two real `wall_seconds`.

## Stop / observe
- Runtime: Step 1 and 1b are ~113 `jobs.get` calls each (a minute over VPN); Steps 2 and 3 are
  recursive listings (tens of seconds).
- Abort: Ctrl-C. Every step is read-only — nothing to clean up.
- Cost: **zero.** No compute allocated by any step.

## What Claude does with the results
- **Step 1/1b** → a **job-execution span** per phase, always labelled as *"reconstructed from AML
  job history — a lower bound on the driver wall"*, never as `wall_seconds`; plus the
  ramp-vs-driver-side split that TODO #59 wants.
- **Step 2** → the archive's bytes, so the AML download row can state a throughput.
- **Step 3** → where run-book 38 Phase 3's 977.9 s of driver-side time actually went.
- Anything these cannot establish stays **"not measured"** in `demos/E2E_AUSTRIA_AML.md`.
