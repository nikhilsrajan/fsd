# Run-book: spec 26 — safe download confirm-run (tiny 1-MGRS-tile Austria slice)

> Spec 24 template. A run-book is what Claude hands the user instead of running a
> pipeline/long/networked script itself. The user runs the commands and pastes back each step's
> `_result.json`; Claude diffs it against the success criteria below — **never against a live
> conversation's memory** (spec 26's deliberate pause point: this doc is self-contained).

## Handoff checklist (before starting a fresh session)
- [x] Claude has flushed durable state to `fsd/PROGRESS.md` (+ `MEMORY.md`).
- [x] User ran `/handoff <goal>` when ready to run this (a real, non-hotspot connection).
- [ ] Fresh session started (not `/compact`); model/effort set for the verifying session
      (Opus/high to diff the pasted `_result.json` against this doc).

## Purpose
First real CDSE network exercise of the spec-25/25b download pipeline: prove `download_resume`
completes cleanly against real CDSE traffic, exercise the `--dry-run`/`--stop-file` safety seams
(spec 26), and measure the transfer-vs-convert split + probe-vs-aggregate MB/s (spec 25's reason
to exist, so far only reasoned about).

## Prerequisites
- venv: `fsd/.venv` (`pip install -e ".[dev]"`), or the modeldeploy venv used for the e2e demo.
- creds: a `cdse_credentials.json` (or `$CDSE_CREDENTIALS_JSON`) with valid S3 keys (see
  `demos/E2E_AUSTRIA.md` §3). CDSE STAC discovery is anonymous; only the download step needs S3 keys.
- free disk: ≥ 5 GB under `fsd/tests/outputs/demo_e2e/imagery` (the target is ~2 GB).
- a real (non-hotspot) network connection — this is the network half of spec 26.

All commands below run from the `fsd/` package root.

## Steps

### Step 0 — preflight: creds + the tiny 1-MGRS-tile slice
```bash
.venv/bin/python -c "
import datetime, os, sys
sys.path.insert(0, 'demos')
import e2e_austria as demo
from fsd.sources.cdse import CdseCredentials

creds_fp = os.environ.get('CDSE_CREDENTIALS_JSON') or os.path.join('../secrets', 'cdse_credentials.json')
creds = CdseCredentials.from_json(creds_fp)
creds.require_s3()
assert not creds.is_expired(), 'S3 keys expired — refresh cdse_credentials.json'

demo.START = datetime.datetime(2018, 4, 1)
demo.END = datetime.datetime(2018, 6, 1)          # the --fast window: fewer granules
os.makedirs('tests/outputs/demo_e2e', exist_ok=True)
fp = demo._single_tile_roi('tests/outputs/demo_e2e/tiny_roi.geojson')
print('tiny ROI ->', fp)
"
```
- **Expect:** `tiny ROI -> tests/outputs/demo_e2e/tiny_roi.geojson`, no assertion error.
- **PASS if:** the script exits 0 and the geojson file exists.
- **If it fails:** a creds/expiry error means refresh `cdse_credentials.json` before continuing;
  a "no CDSE tiles intersect" error means the network/STAC endpoint is unreachable — check
  connectivity before retrying.

### Step 1 — dry-run (metadata only, zero band bytes)
```bash
.venv/bin/python -m fsd.sources.download_cli \
  --roi tests/outputs/demo_e2e/tiny_roi.geojson \
  --start 2018-04-01 --end 2018-06-01 \
  --bands B04 B08 B8A SCL \
  --dst tests/outputs/demo_e2e/imagery \
  --catalog tests/outputs/demo_e2e/imagery/catalog.parquet \
  --max-tiles 10 --dry-run \
  --result-json tests/outputs/demo_e2e/imagery/_result_step1.json
```
- **Expect:** a printed plan (`needed: N granules | present: 0 | missing: N`), exit code `0`.
- **PASS if:** `missing_count` is between **5 and 10** (a single MGRS tile revisited every ~5 days
  over the 2-month window → ~7 granules; exact count depends on the real STAC match/cloud filter);
  **zero bytes transferred** (no new files under `--dst`); exit code `0`.
- **If it fails / hangs:** this step makes no network transfer beyond the anonymous STAC query, so
  a hang here points at CDSE STAC reachability, not the download pipeline. Ctrl-C is safe (no
  side effects to clean up).

### Step 2 — real download, stop-file armed
```bash
.venv/bin/python -m fsd.sources.download_cli \
  --roi tests/outputs/demo_e2e/tiny_roi.geojson \
  --start 2018-04-01 --end 2018-06-01 \
  --bands B04 B08 B8A SCL \
  --dst tests/outputs/demo_e2e/imagery \
  --catalog tests/outputs/demo_e2e/imagery/catalog.parquet \
  --max-tiles 10 --stop-file /tmp/fsd.stop \
  --result-json tests/outputs/demo_e2e/imagery/_result_step2.json
```
- **Expect:** `probing throughput (downloads 1 band file)…` (this transfers one full JP2 and can
  sit silent for up to ~a minute on a slow link — not a hang), then `probe: N.N MB/s`, then
  `discovering + planning download…`, then live progress lines every ~5s with `file/s` + `ETA`
  (the first one appears only after the first granule finishes downloading **and** converting),
  then a final summary line (`successful=... failed=... | transfer=...s convert=...s | probe=...
  aggregate=... | stopped=False ...`).
- **PASS if:** exit code `0`; `_result_step2.json` has `status="ok"`, `metrics.failed == 0`,
  `metrics.successful + metrics.skipped` matches the step-1 `missing_count`
  (i.e. every missing file landed), `metrics.stopped == false`, `metrics.circuit_tripped == false`,
  `metrics.pool_broken == false`.
- **If it fails / hangs:** `touch /tmp/fsd.stop` to stop cleanly (expect a clean drain within a
  few seconds — no hung process, no orphaned `.part`/`.src.jp2` files). **To resume, `rm -f
  /tmp/fsd.stop` first** (else the re-run stops again immediately, before downloading anything),
  then re-run the same command (idempotent skip on files already on disk). Paste
  `_result_step2.json` either way.

### Step 3 — integrity check
```bash
.venv/bin/python -c "
import glob, os
from fsd.catalog.catalog import TileCatalog

dst = 'tests/outputs/demo_e2e/imagery'
bands = ['B04', 'B08', 'B8A', 'SCL']
leftover = glob.glob(os.path.join(dst, '**', '*.part'), recursive=True) + \
           glob.glob(os.path.join(dst, '**', '*.src.jp2'), recursive=True)
cat = TileCatalog(os.path.join(dst, 'catalog.parquet')).read()
missing_band_files = []
for folder in cat['local_folderpath']:
    for b in bands:
        fp = os.path.join(folder, f'{b}.tif')
        if not os.path.exists(fp):
            missing_band_files.append(fp)

print('catalog rows:', len(cat))
print('leftover staging files:', leftover)
print('missing band files:', missing_band_files)
assert len(cat) > 0, 'no rows in catalog'
assert not leftover, f'staging leftovers: {leftover}'
assert not missing_band_files, f'missing band files: {missing_band_files}'
print('PASS')
"
```
- **Expect:** `catalog rows: N` (matching step 1/2's granule count), `leftover staging files: []`,
  `missing band files: []`, then `PASS`.
- **PASS if:** the script prints `PASS` (its asserts all held) — every requested band is present as
  a `Bxx.tif` COG per catalog row, no `.part`/`.src.jp2` left anywhere under `--dst`.
- **If it fails:** paste the printed lists (which rows/files) — do not re-run the download yet.

### Step 4 — report the measurement (spec 25's reason to exist)
```bash
.venv/bin/python -c "
import json
r = json.load(open('tests/outputs/demo_e2e/imagery/_result_step2.json'))
m = r['metrics']
print(f\"transfer: {m['transfer_s']:.1f}s | convert: {m['convert_s']:.1f}s | \"
      f\"gb: {m['gb']:.2f} | probe: {m['probe_mb_per_s']:.1f} MB/s | \"
      f\"aggregate: {m['aggregate_mb_per_s']:.1f} MB/s\")
"
```
- **Expect:** the transfer_s/convert_s split and probe-vs-aggregate MB/s line.
- **PASS/FAIL:** no hard threshold (this is the first baseline measurement) — just captured. Flag
  it if `aggregate_mb_per_s` is far below `probe_mb_per_s` (< ~50%, say) — that's a
  local-contention/concurrency signal worth a follow-up, not a step failure.

### Optional — stop drill
Re-run step 2's command from a clean state (or after removing a few `Bxx.tif` files to have
work left); a few seconds after progress lines start, in another terminal:
```bash
touch /tmp/fsd.stop
```
- **Expect:** the run drains in-flight transfers/converts and exits within a few seconds — no
  hang, no `.part`/`.src.jp2` leftovers.
- **PASS if:** exit code `0`, `_result.json` has `status="stopped"`, `metrics.stopped == true`.
  Re-running the same command afterward (without `--stop-file` armed, or with it removed) resumes
  and completes (idempotent skip on what's already on disk).

## Success criteria (`_result.json`)
Each step writes `<dst>/_result_step<N>.json` (step 2's shape, spec 24 / spec 26 §4):
```json
{
  "step": "download-confirm-run",
  "status": "ok | dry-run | stopped | failed",
  "pass": 1,
  "metrics": {
    "needed": 7, "present": 0, "missing": 7,
    "successful": 7, "failed": 0, "failed_total": 0, "skipped": 0,
    "gb": 2.0, "transfer_s": 0, "convert_s": 0,
    "probe_mb_per_s": 0, "aggregate_mb_per_s": 0,
    "elapsed_s": 0, "stopped": false,
    "circuit_tripped": false, "pool_broken": false
  },
  "expected": {
    "missing_count_range": [5, 10],
    "failed": 0, "stopped": false, "circuit_tripped": false, "pool_broken": false
  },
  "error": null
}
```
The run passes when step 1's `missing` is in `[5, 10]`, step 2's `status == "ok"` with
`failed == 0` and `stopped == false`, and step 3's integrity script prints `PASS`.
**Paste these files back** (not the logs).

## Stop / observe
- Startup is not instant and not silent: `download_cli` prints `probing throughput…` then
  `probe: N.N MB/s` (the probe downloads one full JP2 — silent for up to ~a minute on a slow
  link), then `discovering + planning download…`. Live progress starts only after the first
  granule lands.
- Progress: `download_cli` prints a live line every ~5s with rate (`N.N file/s`) and ETA
  (`ETA ~Nm`, or `ETA ~?` before the first completion).
- `--quiet` suppresses all of the above (the startup lines and the live progress lines).
- Dry-run: `--dry-run` (step 1) prints the plan + cost estimate with **zero** side effects.
- Abort: `touch /tmp/fsd.stop` (armed via `--stop-file`) — clean drain within seconds, resume-safe.
  Ctrl-C also works (not resume-guaranteed the same way — prefer the stop-file).
