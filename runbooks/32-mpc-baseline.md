# Run-book: spec 32 — MPC source + processing-baseline harmonization (single tile, B04 + SCL, 2 dates)

> **v2 (2026-07-16)** — corrected after the first real run. v1's steps 2 and 3 were internally
> impossible (B04-only vs `build_datacube`'s hardcoded SCL requirement), over-fetched **1.7 GB**
> instead of the promised "few MB", and had PASS criteria that couldn't fail. See the correction
> notes on each step. The v1 defects trace back to **spec 32's own Tests section**, not the
> implementation.

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
- free disk: **~400 MB**, and expect to actually move that much over the wire. ⚠️ **v1 claimed "a
  few MB, no full-tile download" — that was wrong, and the first real run disproved it.** MPC's
  assets are **full-tile (~110 km) COGs**: a single B04 measured **96–272 MB** on this tile. This
  run fetches 2 items × (B04 + SCL) ≈ **~320 MB**. Nothing here reads a window — Phase 1 copies
  whole tiles by design (spec 32 §Scope), even though the ROI is only ~21 km² (**0.18 %** of a
  tile). That ratio is the open Phase-2 stream-vs-copy question (TODO #31) and the main suspect in
  any "MPC feels slow" reading (TODO #36).
- a real network connection. **On a mobile hotspot this is ~320 MB — not instant**; it is small
  enough to be safe, but it is not the "tiny" run v1 advertised.
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

### Step 2 — pick two items straddling 2022-01-25 (one pre-, one post-baseline) and download B04 + SCL

> **Corrected 2026-07-16 (v2).** The original step 2 had three defects, all found on the first real
> run: (a) it downloaded **B04 only**, but `build_datacube` structurally requires **SCL** (its op
> chain hardcodes `apply_cloud_mask_scl` → `drop_bands(["SCL"])`) → step 3 always crashed; (b) it
> downloaded the **whole date range between** `pre` and `post`, so a run intended to fetch 2 tiny
> assets fetched **9 full MGRS tiles / 1.7 GB** on a hotspot; (c) its `pass` flag only checked
> `failed_count == 0`, so it reported success while never testing the offsets it claimed to.
> Fixed: two **tight ±1 h windows** (exactly the two chosen items), `['B04','SCL']`, and a `pass`
> that actually asserts the two offsets. Adding SCL also makes the **band exemption LIVE** (SCL must
> come back `0` while B04 comes back `-1000`) instead of "moot" as the spec put it.

```bash
mkdir -p tests/outputs/mpc_baseline
.venv/bin/python -c "
import datetime, json
import geopandas as gpd
from fsd.catalog.catalog import TileCatalog
from fsd.sources import mpc

roi = gpd.read_file('../shapefiles/s2grid=476da24.geojson')
CUTOVER = datetime.datetime(2022, 1, 25, tzinfo=datetime.timezone.utc)
items = sorted(mpc._search_items(roi, '2021-11-01', '2022-03-01', max_cloudcover=60.0),
               key=lambda it: it.datetime)
# Deterministic + adjacent across the cutover: the LAST pre-baseline item and the FIRST post one.
pre = [it for it in items if it.datetime < CUTOVER][-1]
post = [it for it in items if it.datetime >= CUTOVER][0]
print('pre :', pre.id, pre.properties.get('s2:processing_baseline'), pre.datetime)
print('post:', post.id, post.properties.get('s2:processing_baseline'), post.datetime)

catalog = TileCatalog('tests/outputs/mpc_baseline/catalog.parquet')
# One tight window per item -> exactly these two acquisitions, not the whole span between them.
failed = 0
for it in (pre, post):
    r = mpc.download(
        roi, it.datetime - datetime.timedelta(hours=1), it.datetime + datetime.timedelta(hours=1),
        ['B04', 'SCL'], 'tests/outputs/mpc_baseline/imagery', catalog,
        max_tiles=4, max_cloudcover=60.0, progress=True,
    )
    print(it.id, '->', r)
    failed += r.failed_count

gdf = catalog.read().set_index('id')
offsets = {i: int(gdf.loc[i, 'boa_add_offset']) for i in (pre.id, post.id)}
files = {i: gdf.loc[i, 'files'] for i in (pre.id, post.id)}
print('offsets:', offsets)
print('files  :', files)
ok = (failed == 0 and offsets[pre.id] == 0 and offsets[post.id] == -1000
      and all('SCL.tif' in f and 'B04.tif' in f for f in files.values()))
result_json = {
    'step': 'mpc-baseline-download', 'status': 'ok' if ok else 'failed', 'pass': bool(ok),
    'metrics': {'failed': failed, 'item_ids': [pre.id, post.id],
                'baselines': {pre.id: pre.properties.get('s2:processing_baseline'),
                              post.id: post.properties.get('s2:processing_baseline')},
                'boa_add_offsets': offsets, 'files': files,
                'catalog_rows': int(len(gdf))},
    'expected': {'failed': 0, 'pre_offset': 0, 'post_offset': -1000,
                 'both_have_B04_and_SCL': True},
    'error': None,
}
with open('tests/outputs/mpc_baseline/_result_step2.json', 'w') as f:
    json.dump(result_json, f, indent=2, default=str)
print(json.dumps(result_json, indent=2, default=str))
"
```
- **Expect:** `pre` with a baseline **< 04.00** and `post` with **>= 04.00**; two `DownloadResult`s
  with `failed_count=0`; `offsets` = `{<pre>: 0, <post>: -1000}`; both items' `files` listing
  **both** `B04.tif` and `SCL.tif`.
- **PASS if:** `_result_step2.json` has `pass: true` — which now checks all of: `failed == 0`, the
  pre item's offset is `0`, the post item's offset is `-1000`, and both items have B04 + SCL.
- **Note (expected, not a failure):** `metrics.catalog_rows` may exceed 2 — the earlier v1 run left
  9 B04-only rows in this catalog, and MPC can return **two items for the same acquisition** (an
  original and a later reprocessing, e.g. `…20220301T100029…_20220303T182540` vs
  `…_20240604T180322`). Step 3 filters to the two `item_ids` explicitly, so neither affects it.
  (fsd does not yet de-duplicate reprocessed acquisitions — TODO #34.)
- **If it fails:** an `ImportError` on `aiohttp`/a transfer error is the fsspec-`http`-backend open
  item (spec 32 §Open items) — try `pip install aiohttp` and re-run; if it still fails, that's the
  signal to fall back to a `/vsicurl`-based or `requests`-stream `get` (a follow-on fix, not
  something to guess at here). A `KeyError`/missing asset for `B04`/`SCL` means the asset-key
  assumption doesn't match the live item — report the actual asset keys from step 1.

### Step 3 — build a 2-timestamp datacube + an unharmonized control, and measure the shift

> **Corrected 2026-07-16 (v2).** The original step 3 (a) passed `bands=['B04']` → always raised
> `ValueError: SCL band not present in datacube`; (b) used `mosaic_days=120` over a **120-day**
> window, which yields **T=1**, not the "2-timestamp datacube" it promised — so its pre-vs-post
> comparison was impossible; and (c) its PASS test ("means in a plausible range") was too vague to
> fail a genuinely broken harmonization. Replaced with an **A/B against an unharmonized control**:
> build the same cube twice, once as-is and once with every `boa_add_offset` forced to `0`. On
> pixels that cannot clip, the harmonized post-baseline slice must equal the control **exactly
> minus 1000**, and the pre-baseline slice must be **bit-identical** (its offset is 0). That is a
> real-data measurement of the fix, not a plausibility judgement.

```bash
.venv/bin/python -c "
import datetime, json, math
import numpy as np
import geopandas as gpd
from fsd.catalog.catalog import TileCatalog
from fsd.datacube import builder
from fsd.storage import fs

roi = gpd.read_file('../shapefiles/s2grid=476da24.geojson')
ids = json.load(open('tests/outputs/mpc_baseline/_result_step2.json'))['metrics']['item_ids']
cat = TileCatalog('tests/outputs/mpc_baseline/catalog.parquet')

# Filter to EXACTLY step 2's two items (ignores v1 leftovers + reprocessed duplicates).
subset = cat.filter(roi, datetime.datetime(2021, 11, 1), datetime.datetime(2022, 3, 2))
subset = subset[subset['id'].isin(ids)].reset_index(drop=True)
assert len(subset) == 2, f'expected 2 tile rows, got {len(subset)}'
flat = builder.flatten_catalog(subset)
print(flat[['id', 'band', 'boa_add_offset']].to_string())

# Bracket the two acquisitions so each lands in its OWN calendar window => T=2.
ts = sorted(subset['timestamp'])
start = ts[0].tz_convert('UTC').normalize().to_pydatetime().replace(tzinfo=None)
end = (ts[1].tz_convert('UTC').normalize() + datetime.timedelta(days=1)).to_pydatetime().replace(tzinfo=None)
mosaic_days = math.ceil((end - start).days / 2)
print(f'window: {start.date()} -> {end.date()}, mosaic_days={mosaic_days}')

def build(f, tag):
    out = f'tests/outputs/mpc_baseline/cube_{tag}'
    builder.build_datacube(
        catalog_subset=f, shape_gdf=roi, startdate=start, enddate=end,
        bands=['B04', 'SCL'], mosaic_days=mosaic_days, reference_band='B04',
        export_folderpath=out, if_missing_files='warn',
    )
    return fs.load_npy(out + '/datacube.npy')

cube_h = build(flat, 'harmonized')                      # as-is
flat0 = flat.copy(); flat0['boa_add_offset'] = 0        # control: harmonization disabled
cube_u = build(flat0, 'control')

print('cube shape (T,H,W,bands):', cube_h.shape)  # bands=1: SCL is dropped after masking
assert cube_h.shape[0] == 2, f'expected T=2, got {cube_h.shape[0]}'
pre_h, post_h, pre_u, post_u = cube_h[0], cube_h[1], cube_u[0], cube_u[1]

# The pre-baseline slice has offset 0 -> must be untouched by harmonization.
pre_identical = bool(np.array_equal(pre_h, pre_u))
# On post-baseline pixels that cannot clip (>1000), harmonized == control - 1000, exactly.
m = post_u > 1000
shift_exact = bool(m.any() and np.array_equal(post_h[m].astype(np.int32),
                                              post_u[m].astype(np.int32) - 1000))
mean = lambda a: float(a[a != 0].mean()) if (a != 0).any() else None
metrics = {
    'shape': list(cube_h.shape), 'pre_identical_to_control': pre_identical,
    'post_shift_is_exactly_minus_1000': shift_exact,
    'n_nonclipping_post_pixels': int(m.sum()),
    'mean_pre_harmonized': mean(pre_h), 'mean_post_harmonized': mean(post_h),
    'mean_pre_control': mean(pre_u), 'mean_post_control': mean(post_u),
}
ok = pre_identical and shift_exact
result_json = {'step': 'mpc-baseline-build', 'status': 'ok' if ok else 'failed', 'pass': bool(ok),
               'metrics': metrics,
               'expected': {'pre_identical_to_control': True,
                            'post_shift_is_exactly_minus_1000': True, 'shape_T': 2},
               'error': None}
with open('tests/outputs/mpc_baseline/_result_step3.json', 'w') as f:
    json.dump(result_json, f, indent=2, default=str)
print(json.dumps(result_json, indent=2, default=str))
"
```
- **Expect:** `flat` shows **B04 → `-1000` for the post item / `0` for the pre item, and SCL → `0`
  for both** (the band exemption, now live on real data); both cubes build; `T == 2`.
- **PASS if:** `_result_step3.json` has `pass: true` — i.e. `pre_identical_to_control` (offset 0
  changed nothing) **and** `post_shift_is_exactly_minus_1000` (the post-baseline slice is the
  control shifted down by exactly 1000 DN on every non-clipping pixel). Note
  `mean_post_control - mean_post_harmonized ≈ 1000` is the human-readable version of the same fact.
- **If it fails:** an `if_missing_files` warning about area coverage/time gaps is expected for a
  single-tile ROI at the calendar-mosaic edges — not a failure unless the build itself raises. If
  `post_shift_is_exactly_minus_1000` is **false**, that is a genuine spec-32 regression — paste
  `_result_step3.json` back; do not work around it.

## Success criteria (`_result.json`)
Step 2 writes `tests/outputs/mpc_baseline/_result_step2.json`, step 3 writes `_result_step3.json`:
```json
{
  "step": "mpc-baseline-download",
  "status": "ok",
  "pass": true,
  "metrics": {
    "failed": 0,
    "item_ids": ["<pre-item-id>", "<post-item-id>"],
    "baselines": { "<pre-item-id>": "02.xx", "<post-item-id>": "04.00+" },
    "boa_add_offsets": { "<pre-item-id>": 0, "<post-item-id>": -1000 },
    "files": { "<pre-item-id>": "B04.tif,SCL.tif", "<post-item-id>": "B04.tif,SCL.tif" },
    "catalog_rows": 9
  },
  "expected": { "failed": 0, "pre_offset": 0, "post_offset": -1000,
                "both_have_B04_and_SCL": true },
  "error": null
}
```
```json
{
  "step": "mpc-baseline-build",
  "status": "ok",
  "pass": true,
  "metrics": {
    "shape": [2, "<H>", "<W>", 1],
    "pre_identical_to_control": true,
    "post_shift_is_exactly_minus_1000": true,
    "n_nonclipping_post_pixels": "<int, must be > 0>",
    "mean_pre_harmonized": "<~few hundred to few thousand DN>",
    "mean_post_harmonized": "<~1000 below mean_post_control>",
    "mean_pre_control": "<equal to mean_pre_harmonized>",
    "mean_post_control": "<~1000 above mean_post_harmonized>"
  },
  "expected": { "pre_identical_to_control": true,
                "post_shift_is_exactly_minus_1000": true, "shape_T": 2 },
  "error": null
}
```
The run passes when step 1 confirms both live STAC properties exist, step 2's `pass: true` (offsets
`0` / `-1000` on the two chosen items, both with B04 + SCL), and step 3's `pass: true` (the
post-baseline slice is the unharmonized control shifted down by **exactly 1000 DN**, the
pre-baseline slice untouched). **Paste back `_result_step2.json` + `_result_step3.json`** — not raw
logs. A later session diffs them against the `expected` blocks above.

## Stop / observe
- One MGRS tile, two bands, two dates — but **~320 MB over the wire** (full-tile COGs; see
  Prerequisites). `progress=True` prints a per-file line. On a hotspot behind a VPN expect this to
  take a while; that is the link and the full-tile copy, **not** evidence about MPC's speed (TODO
  #36 — a source-speed comparison run locally can't answer that; see the TODO for why).
- No stop-file / circuit breaker in this Phase-1 path (spec 32 §1 scope note: full
  `download_resume`-style orchestration for MPC is a Phase-2 TODO) — Ctrl-C is safe (idempotent
  skip on existing files covers a re-run).
