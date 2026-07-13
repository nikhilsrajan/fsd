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
First write the run's success criteria once; `--expected-json` echoes them into every
`_result.json`'s `expected` block, so each pasted result is self-contained for the diff (spec 26 §4).
The CLI additionally auto-fills the universal invariants (`failed=0, stopped=false,
circuit_tripped=false, pool_broken=false`) on the real-download result.
```bash
mkdir -p tests/outputs/demo_e2e/imagery
cat > tests/outputs/demo_e2e/expected.json <<'JSON'
{
  "missing_count_range": [10, 15],
  "successful": "missing_count * (len(bands) + 1)",
  "failed": 0
}
JSON
.venv/bin/python -m fsd.sources.download_cli \
  --roi tests/outputs/demo_e2e/tiny_roi.geojson \
  --start 2018-04-01 --end 2018-06-01 \
  --bands B04 B08 B8A SCL \
  --dst tests/outputs/demo_e2e/imagery \
  --catalog tests/outputs/demo_e2e/imagery/catalog.parquet \
  --max-tiles 15 --dry-run \
  --expected-json tests/outputs/demo_e2e/expected.json \
  --result-json tests/outputs/demo_e2e/imagery/_result_step1.json
```
- **Expect:** a printed plan (`needed: N granules | present: 0 | missing: N`), exit code `0`.
- **PASS if:** `missing_count` is between **10 and 15** (a single MGRS tile revisited every ~5 days —
  S2A+S2B combined — over the 2-month window → **~13 granules**; exact count depends on the real STAC
  match/cloud filter); **zero bytes transferred** (no new files under `--dst`); exit code `0`.
  Note `--max-tiles` (the download guardrail, checked in step 2) must be **≥ this count** or step 2
  raises `... matched tiles exceed max_tiles`; 15 leaves headroom above the observed 13.
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
  --max-tiles 15 --stop-file /tmp/fsd.stop \
  --expected-json tests/outputs/demo_e2e/expected.json \
  --result-json tests/outputs/demo_e2e/imagery/_result_step2.json
```
> **To capture a real throughput measurement (step 4), step 2 must actually transfer bytes.** If
> `tests/outputs/demo_e2e/imagery` already holds a completed run, every file is skipped
> (`skipped == successful`, `transfer_s == 0`, `aggregate == 0`) — a valid resume, but it measures
> nothing. For a fresh measurement either use a clean `--dst` (and matching `--catalog`) or
> `rm -rf tests/outputs/demo_e2e/imagery/Sentinel-2` first, then run.
- **Expect:** `probing throughput (downloads 1 band file)…` (this transfers one full JP2 and can
  sit silent for up to ~a minute on a slow link — not a hang), then `probe: N.N MB/s`, then
  `discovering + planning download…`, then live progress lines every ~5s with `file/s` + `ETA`
  (the first one appears only after the first granule finishes downloading **and** converting),
  then a final summary line (`successful=... failed=... | transfer=...s convert=...s | probe=...
  aggregate=... | stopped=False ...`).
- **PASS if:** exit code `0`; `_result_step2.json` has `status="ok"`, `metrics.failed == 0`,
  `metrics.stopped == false`, `metrics.circuit_tripped == false`, `metrics.pool_broken == false`,
  and every requested file landed: **`metrics.successful == missing_count × files_per_granule`**,
  where `files_per_granule = len(bands) + 1` (the +1 is `MTD_TL.xml`) — so for 13 granules × (4 bands
  + 1) = **65**. Note `metrics.successful` already *includes* already-present files, and
  `metrics.skipped` is the subset that were already on disk: `skipped == 0` ⇒ a fresh download (real
  `transfer_s`/`aggregate`), `skipped == successful` ⇒ a pure resume (zeros — nothing measured). Do
  **not** add `successful + skipped` (that double-counts, and mixes file vs granule units).
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
print(f\"transfer: {m['transfer_s']:.1f}s (summed) / {m['transfer_wall_s']:.1f}s wall | \"
      f\"convert: {m['convert_s']:.1f}s (summed) | gb: {m['gb']:.2f}\")
print(f\"probe(1 stream): {m['probe_mb_per_s']:.1f} | per-stream: {m['aggregate_mb_per_s']:.1f} | \"
      f\"wall(all streams): {m['wall_transfer_mb_per_s']:.1f} MB/s\")
"
```
- **Expect:** the transfer/convert split (summed-across-threads **and** wall) and three MB/s numbers.
- **How to read it** (three rates, three different things — don't compare the wrong pair):
  - `probe_mb_per_s` — a **single** stream, wall-clock.
  - `aggregate_mb_per_s` — bytes ÷ **thread-summed** transfer_s → the **per-stream** rate under
    concurrency. Compare this to `probe`: `per-stream ≈ probe` ⇒ streams don't interfere;
    `per-stream ≪ probe` ⇒ they contend for a shared resource (the CDSE link, usually — *not*
    necessarily local CPU/disk).
  - `wall_transfer_mb_per_s` — bytes ÷ **wall** transfer span → the **effective** throughput all
    streams achieved together. **This is the one that matters for tuning:** `wall ≥ probe` ⇒
    concurrency helped; `wall < probe` ⇒ it didn't (the link is the bottleneck) — try fewer streams
    with `--max-concurrent-s3 1` or `2`.
- **PASS/FAIL:** no hard threshold — this is a baseline to capture. (First real run, 2026-07-13:
  probe 25 / per-stream 4.8 / wall 19 MB/s on a 3.5 GB / 13-granule slice → link-bound, 4 streams
  slightly slower than 1.)

### Optional — stop drill
Re-run step 2's command from a clean state (or after removing a few `Bxx.tif` files to have
work left); a few seconds after progress lines start, in another terminal:
```bash
touch /tmp/fsd.stop
```
- **Expect:** within ~1s the CLI prints `[fsd.download] stop requested — halting new submissions;
  draining N in-flight transfer(s)/convert(s), then exiting…`, then it finishes those N and exits —
  no hang, no `.part`/`.src.jp2` leftovers. **The stop is not instant:** it halts *new* submissions
  but lets everything already in flight finish (that's what guarantees no partial files). `N ≈
  --max-staged` (default ~`MAX_CONCURRENT_S3 + 2×MAX_CONVERT_PROCS` ≈ 20), so on a fast link the
  progress % can still climb a good bit after the touch — expected, not a bug. To make the stop
  tighter (at a throughput cost), lower `--max-staged` (e.g. `--max-staged 4` → ~4 in-flight).
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
    "needed": 13, "present": 0, "missing": 13,
    "successful": 65, "failed": 0, "failed_total": 0, "skipped": 0,
    "gb": 2.0, "transfer_s": 0, "transfer_wall_s": 0, "convert_s": 0,
    "probe_mb_per_s": 0, "aggregate_mb_per_s": 0, "wall_transfer_mb_per_s": 0,
    "elapsed_s": 0, "stopped": false,
    "circuit_tripped": false, "pool_broken": false
  },
  "expected": {
    "missing_count_range": [10, 15],
    "successful": "missing_count * (len(bands) + 1)",
    "failed": 0, "stopped": false, "circuit_tripped": false, "pool_broken": false
  },
  "error": null
}
```
(`needed`/`present`/`missing` are **granules**; `successful`/`skipped`/`failed` are **files** —
`(len(bands) + 1)` per granule, the +1 being `MTD_TL.xml`. So 13 granules ⇒ 65 files.)
The run passes when step 1's `missing` is in `[10, 15]`, step 2's `status == "ok"` with
`failed == 0`, `stopped == false`, and `successful == missing × (len(bands)+1)`, and step 3's
integrity script prints `PASS`. A real throughput number (step 4) additionally needs
`skipped == 0` (a fresh download, not a resume). **Paste these files back** (not the logs).

## Stop / observe
- Startup is not instant and not silent: `download_cli` prints `probing throughput…` then
  `probe: N.N MB/s` (the probe downloads one full JP2 — silent for up to ~a minute on a slow
  link), then `discovering + planning download…`. Live progress starts only after the first
  granule lands.
- Progress: `download_cli` prints a live line every ~5s with rate (`N.N file/s`) and ETA
  (`ETA ~Nm`, or `ETA ~?` before the first completion).
- `--quiet` suppresses all of the above (the startup lines and the live progress lines).
- Dry-run: `--dry-run` (step 1) prints the plan + cost estimate with **zero** side effects.
- Abort: `touch /tmp/fsd.stop` (armed via `--stop-file`). The stop-file is polled ~every 1s, so
  within ~1s you get `[fsd.download] stop requested — … draining N in-flight …`. It's a **clean**
  stop, not an instant kill: new submissions halt, but the `N ≈ --max-staged` transfers/converts
  already in flight finish first (so no partial `.part`/`.src.jp2` files are left). Progress can
  keep climbing until that drain completes — lower `--max-staged` to shrink it. Ctrl-C also works
  (not resume-guaranteed the same way — prefer the stop-file).
