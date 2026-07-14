# Run-book: spec 29 — Tier-1 pre-styled XYZ, validated via STACNotator Bring-Your-Own-XYZ

> Spec 24 template. A run-book is what Claude hands the user instead of running a
> pipeline/long/networked script itself. The user runs the commands and pastes back each step's
> `_result.json` (+ a screenshot for step 5); Claude diffs it against the success criteria below.

## Handoff checklist (before starting a fresh session)
- [x] Claude has flushed durable state to `fsd/PROGRESS.md` (+ `MEMORY.md`).
- [ ] User ran `/handoff <goal>` when ready to run this.
- [ ] Fresh session started (not `/compact`); model/effort set for the verifying session
      (Opus/high to diff the pasted `_result.json`/screenshot against this doc).

## Purpose
Before standing up the full pgSTAC + titiler-pgstac stack (Tier 2), prove the **simplest**
serving integration end-to-end: a **pre-styled XYZ tile URL** for the crop map, consumed by
**STACNotator's Bring-Your-Own-XYZ mode** (`../STACNOTATOR_DIGEST.md §2` mode 3). This de-risks the
two categorical-rendering gotchas (discrete colormap, nearest resampling) against the real
consumer, with **no downloads** (serves the existing `merged.tif`).

## Prerequisites
- A dedicated venv: `.venv-titiler` (`python3.11 -m venv .venv-titiler &&
  .venv-titiler/bin/pip install -e ".[titiler]"`) — kept isolated from `.venv`/`.venv-modeldeploy`.
- The existing demo output `tests/outputs/demo_e2e/model_outputs/merged.tif` (from the full
  Austria e2e run, `demos/E2E_AUSTRIA.md`). If deleted, re-run `demos/e2e_austria.py` first.
- (Step 4) QGIS, for a fast pre-check before standing up STACNotator.
- (Step 5) STACNotator running locally per its own README (`AUTH_PROVIDER=local`,
  `make dev-init && make dev-up`) — a separate NASA Harvest repo, not part of `fsd/`.

All commands below run from the `fsd/` package root.

## Steps

### Step 1 — install
```bash
python3.11 -m venv .venv-titiler
.venv-titiler/bin/pip install -e ".[titiler]"
.venv-titiler/bin/python -c "import rio_tiler, fastapi, uvicorn; print('ok')"
```
- **Expect:** `ok`.
- **PASS if:** the import exits 0.

### Step 2 — launch the server
```bash
.venv-titiler/bin/python -m demos.titiler_serve
```
- **Expect:**
  ```
  XYZ template: http://127.0.0.1:8000/cropmap/tiles/{z}/{x}/{y}.png
  bounds (lon/lat): [14.xx, 48.xx, 15.xx, 49.xx]
  Ctrl-C to stop.
  ```
  (validates `merged.tif` exists first — if missing, it prints the `e2e_austria.py` command that
  produces it and exits non-zero instead of starting).
- **PASS if:** the process stays up and prints the template + bounds. Leave it running; do the
  remaining steps from a second terminal.
- **If it fails:** a "not found" error means `merged.tif` is missing — re-run the e2e demo. A port
  conflict — pass `--port 8001`.

### Step 3 — server smoke (curl, scriptable)
```bash
# a tile inside the Waldviertel ROI (pick z/x/y from the bounds printed in step 2, e.g. via
# https://tools.geofabrik.de/calc/ or any slippy-tile calculator) — for the default demo ROI,
# zoom 13 around (14.9E, 48.7N) works:
curl -s -o /tmp/tile_in.png -w '%{http_code} %{content_type} %{size_download}\n' \
    http://127.0.0.1:8000/cropmap/tiles/13/4437/2823.png

# a tile far from the data (mid-Atlantic):
curl -s -o /tmp/tile_out.png -w '%{http_code} %{content_type} %{size_download}\n' \
    http://127.0.0.1:8000/cropmap/tiles/13/0/0.png

python3 -c "
import json
in_size = __import__('os').path.getsize('/tmp/tile_in.png')
out_size = __import__('os').path.getsize('/tmp/tile_out.png')
result = {
    'step': 'tier1-server-smoke', 'status': 'ok', 'pass': in_size > 0 and out_size > 0,
    'metrics': {'tile_bytes': in_size, 'out_of_bounds_tile_bytes': out_size,
                'content_type': 'image/png'},
    'expected': {'tile_bytes': '>0', 'content_type': 'image/png'}, 'error': None,
}
with open('tests/outputs/demo_e2e/_result_29_smoke.json', 'w') as f:
    json.dump(result, f, indent=2)
print(json.dumps(result, indent=2))
"
```
- **Expect:** both curl lines show `200 image/png <nonzero size>`.
- **PASS if:** `_result_29_smoke.json`'s `pass` is `true` (both tiles non-empty PNGs).

### Step 4 — QGIS quick-check (optional, fast, no STACNotator)
1. QGIS -> Layer -> Add Layer -> Add XYZ Layer -> New -> paste
   `http://127.0.0.1:8000/cropmap/tiles/{z}/{x}/{y}.png` -> Add.
2. Pan/zoom to the bounds printed in step 2 (Waldviertel, Austria).
- **PASS if:** the crop map renders with **distinct class colors** (not a continuous/smeared
  gradient), nodata is **transparent** (basemap shows through), and the shape is correctly placed
  over the basemap (not offset/rotated).
- **If it fails:** a smeared gradient means resampling isn't nearest (a code regression, not a
  config issue — flag it); a solid opaque block instead of transparent nodata means the `nodata=255`
  masking isn't reaching the render (flag it); an offset shape is a CRS/transform bug (flag it).

### Step 5 — STACNotator Bring-Your-Own-XYZ (the real integration test)
1. Start STACNotator locally per its own README: `AUTH_PROVIDER=local`, `make dev-init && make dev-up`.
2. Create a campaign/collection whose imagery slice uses **Bring-Your-Own XYZ**, pasting
   `http://127.0.0.1:8000/cropmap/tiles/{z}/{x}/{y}.png` as the template URL.
3. Open the slice in the STACNotator viewer; pan/zoom to Austria.
- **PASS if:** the crop map displays correctly colored + placed, nodata transparent, and
  panning/zooming loads only in-view tiles (check the browser Network tab or server log — no
  full-extent re-fetch).
- **Paste:** a screenshot of the rendered map in STACNotator, plus a one-line note of any
  mis-color / mis-placement / CORS error observed (each is a real finding, not a "retry it").
  A CORS error in the browser console means the server's `CORSMiddleware` isn't reaching the
  browser (check the server is actually the one STACNotator is pointed at — not a stale process).

### Stop
Ctrl-C the server from step 2 (read-only serving; nothing to clean up).

## Success criteria (`_result.json` + screenshot)
```json
{ "step": "tier1-server-smoke", "status": "ok", "pass": true,
  "metrics": { "tile_bytes": 1234, "content_type": "image/png" },
  "expected": { "tile_bytes": ">0", "content_type": "image/png" },
  "error": null }
```
Steps 4/5 have no JSON — they're visual PASS/FAIL + a screenshot (step 5) pasted back.

## Stop / observe
- Progress: the server prints the XYZ template + bounds once at startup; no ongoing log noise
  (each tile request is served on demand).
- Abort: Ctrl-C at any time (nothing in-flight to corrupt — it's a read-only GET server).
