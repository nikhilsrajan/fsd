# Run-book: spec 28 — regenerate the demo STAC with the true cell geometry

> Spec 24 template. A run-book is what Claude hands the user instead of running a
> pipeline/long/networked script itself. The user runs the commands and pastes back each step's
> `_result.json`; Claude diffs it against the success criteria below.

## Handoff checklist (before starting a fresh session)
- [x] Claude has flushed durable state to `fsd/PROGRESS.md` (+ `MEMORY.md`).
- [ ] User ran `/handoff <goal>` when ready to run this.
- [ ] Fresh session started (not `/compact`); model/effort set for the verifying session
      (Opus/high to diff the pasted `_result.json` against this doc).

## Purpose
`cog_outputs_to_items` used to write the inference-output STAC Item's `geometry` as the raster
bounding box, over-claiming coverage past the true slanted S2-cell footprint (TODO #27). The fix
(spec 28) sources the footprint from the build manifest (`input.csv.shapefilepath` ->
`geometry.geojson`) instead. This regenerates the **existing** 300-item Austria demo STAC from that
same manifest — **no re-inference, no downloads**: it just reads 300 COG headers + 300
`geometry.geojson` polygons and rewrites the STAC JSON.

## Prerequisites
- venv: `fsd/.venv` (`pip install -e ".[dev]"`) — no extra deps needed (pure `fsd.catalog.stac`).
- The existing demo outputs on disk: `tests/outputs/demo_e2e/model_outputs/cells/input.csv` +
  the 300 per-cell `output.tif`/`geometry.geojson` pairs (from the full Austria e2e run,
  `demos/E2E_AUSTRIA.md`). If that folder was deleted to free space, this run-book cannot proceed —
  re-run `demos/e2e_austria.py` first.
- free disk: negligible (JSON rewrite only).

All commands below run from the `fsd/` package root.

## Steps

### Step 1 — regenerate the STAC catalog
```bash
.venv/bin/python -m demos.regen_output_stac \
    --input-csv tests/outputs/demo_e2e/model_outputs/cells/input.csv \
    --stac-dir tests/outputs/demo_e2e/model_outputs/stac \
    --result-json tests/outputs/demo_e2e/model_outputs/_result_28.json
```
- **Expect:** a JSON blob printed to stdout with `"items": 300`, `"distinct_ids": 300`,
  `"non_rectangular_geoms": 300`.
- **PASS if:** `_result_28.json`'s `pass` is `true` and all three metrics above hold — every
  cell's footprint is now the slanted S2-grid polygon, not a box.
- **If it fails / hangs:** this is a pure metadata rewrite (no network, sub-second per item) — a
  failure means a manifest/geometry mismatch (a row's `shapefilepath` missing or unreadable, or an
  output COG absent). Paste the `error` field; it will name the offending path.

### Step 2 (optional) — spot-check one item's geometry against its manifest polygon
```bash
.venv/bin/python -c "
import json, pandas as pd
rows = pd.read_csv('tests/outputs/demo_e2e/model_outputs/cells/input.csv')
row = rows.iloc[0]
with open(row['shapefilepath']) as f:
    truth = json.load(f)['features'][0]['geometry']
item_fp = f\"tests/outputs/demo_e2e/model_outputs/stac/fsd-inference/{row['id']}/{row['id']}.json\"
with open(item_fp) as f:
    item = json.load(f)
assert item['geometry'] == truth, 'geometry mismatch!'
print('OK: item geometry matches geometry.geojson for cell', row['id'])
"
```
- **Expect:** `OK: item geometry matches geometry.geojson for cell <id>`.
- **PASS if:** no `AssertionError`.

### Step 3 (optional, folds into spec 29's STACNotator check)
Once outputs are served (spec 29 Tier 1 or a later Tier 2), visually confirm the item footprints
overlay the true slanted cell shapes, not axis-aligned boxes — no separate action needed here.

## Success criteria (`_result.json`)
```json
{ "step": "regen-output-stac", "status": "ok", "pass": true,
  "metrics": { "items": 300, "distinct_ids": 300, "non_rectangular_geoms": 300 },
  "expected": {},
  "error": null }
```
Paste `tests/outputs/demo_e2e/model_outputs/_result_28.json` back (not logs).

## Stop / observe
- This is a single fast, deterministic pass (sub-second per item, no network) — nothing to stop.
- Idempotent: safe to re-run any time after a `run_inference` pass.
