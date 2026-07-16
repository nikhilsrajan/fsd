# Run-book: spec 32 — MPC source + processing-baseline harmonization (single tile, B04 only)

> Spec 24 template. A run-book is what Claude hands the user instead of running a
> pipeline/long/networked script itself. The user runs the commands and pastes back each step's
> `_result.json`; Claude diffs it against the success criteria below.

## Handoff checklist (before starting a fresh session)
- [x] Claude has flushed durable state to `fsd/PROGRESS.md` (+ `MEMORY.md`).
- [ ] User ran `/handoff <goal>` when ready to run this (real network; hotspot-friendly — this is
      one MGRS tile, one band, two tiny COGs).
- [ ] Fresh session started; model/effort set for the verifying session (Opus/high to diff the
      pasted `_result.json` against this doc).

## Purpose
First real MPC network exercise of the spec-32 source + baseline-harmonization pipeline: prove
`fsd.sources.mpc.download` (pure COG byte-copy, no `jp2->COG` conversion) works against real MPC
traffic, confirm the two **open items** the spec flagged (live STAC property names, the
`planetary-computer` signing API), and prove the processing-baseline offset is captured + applied
correctly across the 2022-01-25 baseline-04.00 cutover (correctness debt #10).

## Prerequisites
- venv: `fsd/.venv`, extras: `pip install -e ".[dev,mpc]"` (installs `planetary-computer`).
  **Open item (spec 32):** if `fsd.storage.transfer(signed_https, local)` doesn't stream cleanly
  via fsspec's `http` backend (needs `aiohttp`; `pip install aiohttp` if step 2 raises an
  import/protocol error), that is the fallback path to confirm — not a code bug to route around
  silently; report back so we decide, don't just patch it in.
- creds: **none** — MPC discovery + this Phase-1 download are anonymous. Optional
  `PC_SDK_SUBSCRIPTION_KEY` env var raises rate limits (not needed for one tile/band).
- free disk: a few MB (single-band COGs, no full-tile download).
- a real network connection (mobile hotspot is fine — this is intentionally tiny).
- ROI: `../shapefiles/s2grid=476da24.geojson` (the single-MGRS-tile Austria test ROI, CLAUDE.md).

All commands below run from the `fsd/` package root.

## Steps

### Step 1 — discover: confirm the live STAC property names (spec 32 open item)
```bash
.venv/bin/python -c "
import json
import geopandas as gpd
from fsd.sources import mpc

roi = gpd.read_file('../shapefiles/s2grid=476da24.geojson')
items = mpc._search_items(roi, '2021-11-01', '2022-03-01', max_cloudcover=60.0)
print('items found:', len(items))
for it in items[:3]:
    print(it.id, '| baseline:', it.properties.get('s2:processing_baseline'),
          '| mgrs_tile:', it.properties.get('s2:mgrs_tile'),
          '| datetime:', it.datetime)
    print('  B04 asset href (signed, truncated):', it.assets['B04'].href[:80], '...')
"
```
- **Expect:** at least 2 items straddling `2022-01-25` printed, each with a non-`None`
  `s2:processing_baseline` and `s2:mgrs_tile`, and a `B04` asset present with an https href
  carrying a SAS query string (`?st=...&se=...&sp=...`).
- **PASS if:** `s2:processing_baseline` and `s2:mgrs_tile` are both present (confirms the spec's
  assumed property names against a live item — the spec's flagged open item). If either key is
  absent/named differently, **stop and report back** — `fsd.sources.mpc._offset_for_item` /
  `_mgrs_tile_from_item` need the real key name, not a guess.
- **If it fails:** an empty `items` list means the ROI/date window found nothing — widen
  `max_cloudcover` or the date range; a `KeyError`/`ImportError` on `planetary_computer` means the
  `[mpc]` extra isn't installed.

### Step 2 — pick two items straddling 2022-01-25 (one pre-, one post-baseline) and download B04
```bash
mkdir -p tests/outputs/mpc_baseline
.venv/bin/python -c "
import datetime, json
import geopandas as gpd
from fsd.catalog.catalog import TileCatalog
from fsd.sources import mpc

roi = gpd.read_file('../shapefiles/s2grid=476da24.geojson')
items = mpc._search_items(roi, '2021-11-01', '2022-03-01', max_cloudcover=60.0)
pre = next(it for it in items if it.datetime < datetime.datetime(2022, 1, 25, tzinfo=it.datetime.tzinfo))
post = next(it for it in items if it.datetime >= datetime.datetime(2022, 1, 25, tzinfo=it.datetime.tzinfo))
print('pre :', pre.id, pre.properties.get('s2:processing_baseline'), pre.datetime)
print('post:', post.id, post.properties.get('s2:processing_baseline'), post.datetime)

catalog = TileCatalog('tests/outputs/mpc_baseline/catalog.parquet')
result = mpc.download(
    roi, pre.datetime - datetime.timedelta(days=1), post.datetime + datetime.timedelta(days=1),
    ['B04'], 'tests/outputs/mpc_baseline/imagery', catalog,
    max_tiles=10, max_cloudcover=60.0, progress=True,
)
print(result)

gdf = catalog.read()
print(gdf[['id', 'timestamp', 'boa_add_offset']].to_string())
result_json = {
    'step': 'mpc-baseline-download', 'status': 'ok' if result.failed_count == 0 else 'failed',
    'pass': result.failed_count == 0,
    'metrics': {'successful': result.successful_count, 'failed': result.failed_count,
                'boa_add_offsets': dict(zip(gdf['id'], gdf['boa_add_offset'].astype(int)))},
    'expected': {'failed': 0, 'one_row_offset_0': True, 'one_row_offset_minus1000': True},
    'error': None,
}
with open('tests/outputs/mpc_baseline/_result_step2.json', 'w') as f:
    json.dump(result_json, f, indent=2, default=str)
print(json.dumps(result_json, indent=2, default=str))
"
```
- **Expect:** `pre`/`post` item ids + baselines printed (pre should be < 04.00, post >= 04.00), a
  `DownloadResult(successful_count=2, ..., failed_count=0, ...)`, then the catalog table showing
  **two rows**: the pre-baseline row with `boa_add_offset == 0` and the post-baseline row with
  `boa_add_offset == -1000`.
- **PASS if:** `_result_step2.json` has `pass: true`, `metrics.failed == 0`, and
  `metrics.boa_add_offsets` has exactly one `0` and one `-1000` value.
- **If it fails:** an `ImportError` on `aiohttp`/a transfer error is the fsspec-`http`-backend open
  item (spec 32 §Open items) — try `pip install aiohttp` and re-run; if it still fails, that's the
  signal to fall back to a `/vsicurl`-based or `requests`-stream `get` (a follow-on fix, not
  something to guess at here). A `KeyError: 'B04'` means the asset-key assumption (`item.assets["B04"]`)
  doesn't match the live item — report the actual asset keys from step 1.

### Step 3 — build a 2-timestamp datacube and spot-check the harmonized pixel
```bash
.venv/bin/python -c "
import datetime, json
import geopandas as gpd
from fsd.catalog.catalog import TileCatalog
from fsd.datacube import builder
from fsd.storage import fs

roi = gpd.read_file('../shapefiles/s2grid=476da24.geojson')
cat = TileCatalog('tests/outputs/mpc_baseline/catalog.parquet')
subset = cat.filter(roi, datetime.datetime(2021, 11, 1), datetime.datetime(2022, 3, 1))
flat = builder.flatten_catalog(subset)
print(flat[['id', 'band', 'boa_add_offset']].to_string())

builder.build_datacube(
    catalog_subset=flat, shape_gdf=roi,
    startdate=datetime.datetime(2021, 11, 1), enddate=datetime.datetime(2022, 3, 1),
    bands=['B04'], mosaic_days=120, reference_band='B04',
    export_folderpath='tests/outputs/mpc_baseline/cube', if_missing_files='warn',
)
dc = fs.load_npy('tests/outputs/mpc_baseline/cube/datacube.npy')
print('datacube shape:', dc.shape)
print('B04 mean per timestamp (nodata=0 excluded):',
      [dc[t][dc[t] != 0].mean() if (dc[t] != 0).any() else None for t in range(dc.shape[0])])
"
```
- **Expect:** `flat` shows `boa_add_offset` of `0` for the pre-baseline B04 row and `-1000` for the
  post-baseline row (band-exemption is moot here — B04 is the only band); the datacube builds
  without error; per-timestamp means printed.
- **PASS if:** the build completes and the printed means are both in a **plausible harmonized S2
  reflectance-DN range** (roughly a few hundred to a few thousand for vegetation/bare ground — NOT
  differing by ~1000 between the two dates, which would indicate the harmonization did not apply).
  A visual spot-check (open the two source COGs the download step wrote,
  `tests/outputs/mpc_baseline/imagery/<pre-item-id>/B04.tif` and `.../<post-item-id>/B04.tif`, in
  QGIS) should show the raw pre-harmonization post-baseline COG reading ~1000 DN higher than the
  cube's harmonized value at the same pixel — confirming the shift happened at build time, not on
  the source file.
- **If it fails:** an `if_missing_files` warning about area coverage/time gaps is expected for a
  single-tile ROI at the calendar-mosaic edges — not a failure unless the build itself raises.

## Success criteria (`_result.json`)
Step 2 writes `tests/outputs/mpc_baseline/_result_step2.json`:
```json
{
  "step": "mpc-baseline-download",
  "status": "ok",
  "pass": true,
  "metrics": {
    "successful": 2, "failed": 0,
    "boa_add_offsets": { "<pre-item-id>": 0, "<post-item-id>": -1000 }
  },
  "expected": { "failed": 0, "one_row_offset_0": true, "one_row_offset_minus1000": true },
  "error": null
}
```
The run passes when step 1 confirms both live STAC properties exist, step 2's `_result_step2.json`
has `pass: true` with exactly one `0` and one `-1000` offset, and step 3's datacube build completes
with the two timestamps' harmonized means in a plausible, non-baseline-split range (ideally
corroborated by the QGIS spot-check). **Paste back `_result_step2.json`** (and note the step 1/3
console output + QGIS observation) — not raw logs.

## Stop / observe
- This is a **tiny** run (one MGRS tile, one band, two dates) — no progress bar or ETA needed;
  each step should finish in well under a minute on a normal connection.
- No stop-file / circuit breaker in this Phase-1 path (spec 32 §1 scope note: full
  `download_resume`-style orchestration for MPC is a Phase-2 TODO) — Ctrl-C is safe (idempotent
  skip on existing files covers a re-run).
