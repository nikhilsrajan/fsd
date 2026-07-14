# Spec 27 — titiler + Leaflet: verify the inference STAC catalog + COGs in a web map

> **⛔ STATUS: SUPERSEDED (2026-07-14) — DO NOT IMPLEMENT.** This spec proposed building a *local
> Leaflet dashboard* (MosaicJSON, DB-free) to eyeball the outputs. During sign-off, a design discussion
> (see the LATEST block in `PROGRESS.md` + `../STACNOTATOR_DIGEST.md` at the workspace root) established
> that **fsd should not build a dashboard at all** — NASA Harvest's **STACNotator** is the viewer, and
> fsd's job is to emit *standard* STAC + COGs + a render config so a **stock pgSTAC + titiler-pgstac**
> stack serves the XYZ endpoints STACNotator consumes (the MPC pattern). The replacement plan lives in
> **TODO #26** (serving contract + validation), **#27** (the STAC-geometry fix — now serving-critical),
> **#28** (model-dev render config → STAC render extension), **#29** (B02/B03 band expansion, parked).
> Kept for history + the concept groundwork (the categorical-colormap / UTM→3857 gotchas still apply).
> The companion explainer `demos/TITILER_LEAFLET.md` remains a useful **concepts primer** (COG / XYZ /
> titiler / STAC / MPC), but its "build a MosaicJSON Leaflet page" framing is superseded.
>
> ~~**Status: DRAFT — awaiting sign-off.**~~ Opus@high (interview → spec). Companion explainer (written
> first, from scratch): `demos/TITILER_LEAFLET.md` — read it for the *why*; this spec is the *what to
> build*. Implementation lands in a **Sonnet@medium** session against this spec once signed off
> (spec 24 D5). Claude (Opus) does **not** run the server — verification is a **spec-24 runbook** the
> user runs (`runbooks/28-titiler-leaflet-verify.md`), pasting back a `_result.json` + a screenshot.
>
> **Three forks resolved by the user at interview (2026-07-14):**
> - **Single-layer mosaic, MosaicJSON-backed (DB-free).** The browser adds **one** XYZ layer pointed at
>   a **MosaicJSON** the server builds by walking our STAC once at startup (item bbox + href → tile→COG
>   index, no COG reads). Serving is titiler's `/mosaic` endpoint: per tile the server looks up the
>   covering COG(s) and range-reads only those. This is the **MPC-like lightweight experience** (one
>   layer, viewport-limited) **without a database** — *not* 300 client-side layers (an earlier draft's
>   mistake — heavier than MPC). `titiler-pgstac` (live pgSTAC, exactly MPC's stack) is the documented
>   **next rung** for Azure scale, not built.
> - **One combined FastAPI app.** A single `uvicorn` process mounts titiler's mosaic + single-COG
>   routers *and* static-serves the Leaflet HTML + `/items.geojson` — one origin, no CORS/`file://` pain.
> - **DB-free** throughout (no pgSTAC/Postgres in the MVP).
>
> **Scope: P5 serving/observability (`ROADMAP.md`, `TODO #14`), orthogonal to the pipeline.** A local
> eyeball/QA tool over artifacts that already exist — **no `src/fsd/` code**; everything lands under
> `demos/` + a `[titiler]` extra. `tests/outputs/demo_e2e/` is **present on disk** (user confirmed
> 2026-07-14), so no regeneration step is needed.

## Motivation

The full Austria run (`E2E_AUSTRIA.md §8`) produced a STAC catalog of **300 inference Items** + their
COGs + a `merged.tif` mosaic, and `src/fsd/catalog/stac.py` is unit-tested — but **no client has ever
consumed that catalog as a catalog.** pytest asserts 300 distinct Items; nobody has pointed a STAC/
tiling client at `collection.json`, walked the item links, resolved the asset hrefs, and watched the
crop map render. That gap is exactly where the last two real bugs hid (the spec-20 tile-merge holes and
the spec-26 item-id collision — `E2E_AUSTRIA.md` Appendix C), and it is the kind of thing you catch **by
eye**. This spec stands up the minimal **titiler + Leaflet** dashboard that reads our STAC and renders
the COGs as one seamless, lightweight mosaic layer — the browser analogue of the project's
QGIS-eyeballing principle.

## Non-goals (explicitly out)

- **No `src/fsd/` change.** titiler consumes the COGs + STAC fsd already writes. All new code is under
  `demos/` (+ the `pyproject` `[titiler]` extra). If anything here tempts an `src/` change, stop and
  raise it — it means the catalog/COG output is wrong, which is a *finding*, not a titiler task.
- **No database / no pgSTAC in the MVP.** The mosaic is a **static MosaicJSON** built from the catalog.
  `titiler-pgstac` (+ a local pgSTAC Postgres, live STAC-query mosaics — MPC's stack, the Azure P5
  target) is **documented as the next rung** (explainer §8), not implemented.
- **No 300 client-side layers.** The heavy approach; superseded by the mosaic endpoint.
- **No remote/Blob/S3 serving.** Asset hrefs are absolute local paths, opened by GDAL directly. Serving
  from Blob/S3 is the storage-seam follow-up (`TODO #17`, P1) — a href + GDAL-env change only.
- **No hosting / auth / deployment.** Local `uvicorn` on `localhost` for eyeballing; not a service.
- **No new inference run.** Serves the existing `tests/outputs/demo_e2e/model_outputs/` artifacts.
- **Not in the lean core `.venv`.** titiler/rio-tiler/cogeo-mosaic/fastapi/uvicorn live in a `[titiler]`
  extra installed into an isolated `.venv-titiler`, mirroring the `[grid]`/`[model-example]` split.

## Design

### D1 — Deps: a new `[titiler]` optional extra (isolated venv)

Add to `pyproject.toml`:

```toml
titiler = [            # P5 serving/observability demo (titiler + Leaflet); NOT fsd core (spec 27)
    "titiler.mosaic>=0.24,<0.25",  # MosaicTilerFactory (the /mosaic endpoint); pulls titiler.core + cogeo-mosaic
    "titiler.core>=0.24,<0.25",    # single-COG TilerFactory (/cog, for /cog/info + optional merged compare)
    "fastapi",                     # pulled by titiler.*; pinned here as a direct import
    "uvicorn[standard]",           # ASGI server to run the app (titiler does NOT depend on it)
]
```

Install into a dedicated venv (keeps `.venv` and `.venv-modeldeploy` untouched):

```bash
python3.11 -m venv .venv-titiler
.venv-titiler/bin/pip install -e ".[titiler]"
```

`titiler.mosaic` brings `cogeo-mosaic` (the `MosaicJSON` reader/writer) and, transitively,
`titiler.core` / `rio-tiler` / `rasterio` / `morecantile` / `pydantic~=2`. Verified against the
titiler **0.24.2** release train (latest, 2025-10-16); the endpoint paths below are that version's.

### D2 — Deliverable shape: two files under `demos/` + one runbook

- **`demos/titiler_serve.py`** — the combined FastAPI app: walks the STAC → builds a MosaicJSON →
  mounts the mosaic + single-COG routers + static routes, with a `python -m` / `__main__` launcher
  (`uvicorn.run`). One process serves everything (D3).
- **`demos/leaflet_dashboard.html`** — a single self-contained static page (Leaflet from CDN is fine;
  a local dev page, *not* an Artifact, so no CSP constraint). Fetches `/config.json`, renders the map +
  the one mosaic layer + optional footprints overlay + legend + a status line.
- **`runbooks/28-titiler-leaflet-verify.md`** — the spec-24 runbook the user runs (§Verification).
  Authored by Sonnet from the success criteria there.

No `class_map.json` generation step is required — the class order is deterministic (D5).

### D3 — The combined FastAPI app (`titiler_serve.py`)

**Startup (before serving):**
1. **Resolve paths** — argparse/env: `--outputs` (default `tests/outputs/demo_e2e/model_outputs`) →
   `STAC_DIR=<outputs>/stac`, `MERGED=<outputs>/merged.tif`, `MOSAIC=<outputs>/inference.mosaicjson`;
   `--host` (default `127.0.0.1`), `--port` (default `8000`).
2. **Validate (fail fast, clear message):** assert `STAC_DIR/catalog.json`,
   `STAC_DIR/fsd-inference/collection.json`, `MERGED` exist; else print what's missing + the command
   that produces it (`demos/e2e_austria.py`) and exit non-zero.
3. **Walk the STAC (the test):** read `collection.json` → for each `rel:"item"` link, resolve its
   relative href against the collection path and read the Item JSON → collect `(item_id, geometry/bbox,
   assets.output.href)`. **Fail loudly** on a duplicate item id or a missing/nonexistent `output` href
   (mirrors the spec-26 guard — a broken catalog must not silently render). Factor this into a **pure
   helper** `walk_inference_stac(stac_dir) -> list[ItemRef]` (unit-tested, D-test).
4. **Build the MosaicJSON** from those items with `cogeo_mosaic.mosaic.MosaicJSON.from_features`:
   features = one GeoJSON `Feature` per item (`geometry` from the item, `properties["path"] = cog_href`
   so the default accessor returns the COG path); `minzoom`/`maxzoom` sensible for 10 m data
   (e.g. 8/15, a config constant — do **not** open COGs to detect it). Write it to `MOSAIC`
   (`inference.mosaicjson`). Because bounds come from the STAC geometry, **no COG is opened** at build.
5. **Build** the colormap + legend (D5), the `/items.geojson` FeatureCollection (footprints), and the
   `CONFIG` dict (D4).

**App:**
```python
from titiler.core.factory import TilerFactory
from titiler.mosaic.factory import MosaicTilerFactory
from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import uvicorn

app = FastAPI(title="fsd inference STAC viewer (spec 27)")

mosaic = MosaicTilerFactory(router_prefix="/mosaic")
app.include_router(mosaic.router, prefix="/mosaic", tags=["mosaic"])   # /mosaic/tiles/{tms}/{z}/{x}/{y}, /mosaic/{tms}/tilejson.json
cog = TilerFactory(router_prefix="/cog")
app.include_router(cog.router, prefix="/cog", tags=["cog"])            # /cog/info, /cog/tiles/... (debug + optional merged compare)

app.mount("/stac", StaticFiles(directory=STAC_DIR), name="stac")      # raw catalog, inspectable/curl-able
@app.get("/")            def index():  return FileResponse(DASHBOARD_HTML)
@app.get("/config.json") def config(): return JSONResponse(CONFIG)
@app.get("/items.geojson") def items(): return JSONResponse(FOOTPRINTS)
```
- **CORS:** single-origin, so not required; add a permissive `CORSMiddleware` anyway (belt-and-braces
  for a future two-origin/QGIS-WMTS pull). One line.
- **Launch:** `python -m demos.titiler_serve` → `uvicorn.run(app, …)`; print the dashboard URL
  (`http://127.0.0.1:8000/`), the mosaic item count, and "Ctrl-C to stop".

### D4 — `/config.json` (the single source the page reads)

The **server** owns the render parameters (the page has zero fsd knowledge):

```json
{
  "tms": "WebMercatorQuad",
  "mosaic_tilejson": "/mosaic/WebMercatorQuad/tilejson.json?url=/abs/inference.mosaicjson",
  "merged_url": "/abs/merged.tif",
  "items_geojson": "/items.geojson",
  "item_count": 300,
  "bidx": 1, "nodata": 255, "resampling": "nearest",
  "colormap": {"0": "#6A3D9A", "1": "#B15928", "2": "#DAA520", "3": "#1B5E20",
               "4": "#FFD500", "5": "#7CB342", "6": "#F0E4B0", "7": "#FF7F00", "8": "#8B7500"},
  "legend": [{"code": 0, "name": "alfalfa_lucerne", "color": "#6A3D9A"}, ...]
}
```
- `mosaic_tilejson` is the titiler mosaic TileJSON URL (already carrying `?url=<mosaicjson>`); the page
  fetches it to get the XYZ tile-URL template + bounds/zoom, then appends the render params below.
- `item_count` = the number of items the startup walk indexed (so the page can show "mosaic: N cells").
- `colormap` is the **discrete** class-code→hex map for **every** code 0–8 (D5); the page URL-encodes
  `JSON.stringify(colormap)` into the `colormap=` param. `merged_url` feeds the optional `/cog` compare
  layer. `legend` drives the on-map legend so map + legend can never disagree.

### D5 — The categorical colormap (the make-or-break detail)

Outputs are **`uint8`, class codes 0–8, nodata 255, single band** (`bundle.json`:
`output_dtype=uint8`, `output_nodata=255`, `output_band_names=["crop_class"]`). Built **in
`titiler_serve.py`** from the demo's `CLASS_COLORS`:

- **Class order is authoritative + deterministic:** class codes come from `sklearn.LabelEncoder`
  (`classes_` is **sorted**); `e2e_austria.py` returns `list(le.classes_)` and the crop-map figure
  indexes `classes[code]`. All 9 classes are present in the Austria training set (`E2E_AUSTRIA.md §8`),
  so **`sorted(CLASS_COLORS.keys())` == the code→name order** (0 = `alfalfa_lucerne` … 8 =
  `winter_common_soft_wheat`). Build `colormap` + `legend` from that sorted list — do **not** re-run or
  re-train to recover it.
- **Source the colors from `demos/e2e_austria.py::CLASS_COLORS`** (single source of truth, shared with
  the figures). `titiler_serve.py` may `from e2e_austria import CLASS_COLORS` (module has a proper
  `if __name__=="__main__"` guard, so import is side-effect-free) **or** carry a documented copy with an
  assert that the two match — Sonnet's call; prefer the import to avoid drift.
- **Render params (all three matter), applied to the mosaic tiles:** `bidx=1`, `nodata=255` (→
  transparent; request **`.png`** for the alpha channel), `resampling=nearest` (never interpolate class
  codes across the UTM→3857 reproject — `TITILER_LEAFLET.md §7`). A missing colormap or nodata renders
  the class map as noise — the #1 failure mode.

### D6 — The Leaflet page (`leaflet_dashboard.html`)

On load: `fetch('/config.json')`, then build:

1. **Basemap** — OSM `L.tileLayer` for context.
2. **The mosaic layer (default on) — the one raster layer.** `fetch(config.mosaic_tilejson)` → take its
   XYZ tile-URL template + `bounds`/`minzoom`/`maxzoom`; append `&bidx=1&nodata=255&resampling=nearest
   &colormap={enc(JSON.stringify(colormap))}` and add as a single `L.tileLayer`; fit the map to the
   TileJSON bounds. Panning/zooming stays light — XYZ requests only in-view tiles, and the server reads
   only the covering cells per tile.
3. **Footprints overlay (optional, on).** `fetch('/items.geojson')` → `L.geoJSON` of the 300 cell
   outlines (cheap; proves the catalog parses + geolocates before any pixel loads).
4. **Compare layer (optional, off).** `merged.tif` via the `/cog` endpoint (same params) so the user can
   A/B the catalog-driven mosaic against the pipeline's pre-merged product.
5. **Layer control** (`L.control.layers`) — basemap / mosaic / footprints / merged-compare.
6. **Legend** — a small control listing `legend[].name` + color swatch.
7. **Status line** — "mosaic: {item_count} cells indexed" (from config); if the mosaic TileJSON or tiles
   fail, surface it visibly (the whole point is that a broken catalog is obvious).

**No per-COG client layers, no client-side catalog walk** — the walk happened server-side at startup
(D3.3). This keeps the browser light regardless of catalog size.

### D7 — What stays fixed / conventions honored

- **Reference/CRS:** titiler reprojects UTM(32633)→WebMercator(3857) per tile; **nearest** only (D5).
- **Non-overlapping cells:** the 300 cells tile the ROI without overlap, so the mosaic's per-tile pixel
  selection never blends class codes — each tile comes from exactly one cell's COG. (Default mosaic
  pixel-selection is fine; no need to tune `skipcovered`/`pixel_selection`.)
- **Output nodata is 255** (uint8 class raster), distinct from the datacube's `nodata=0`. Use 255 here
  (from `bundle.json`), not 0.
- **Item hrefs are absolute local paths** — correct for local GDAL; the one thing that changes for
  Blob/S3 later (Non-goals). The MosaicJSON stores those same paths.

## Verification (spec-24 runbook — Claude never runs the server)

`runbooks/28-titiler-leaflet-verify.md` (Sonnet authors it to these criteria). The user runs it and
pastes back `_result.json` + one screenshot; the reviewing session diffs against the runbook's own
`expected` block (not this conversation).

- **Step 1 — install:** `.venv-titiler` + `pip install -e ".[titiler]"`. PASS: `python -c "import
  titiler.mosaic, titiler.core, cogeo_mosaic, uvicorn, fastapi"` exits 0.
- **Step 2 — launch:** `.venv-titiler/bin/python -m demos.titiler_serve`. PASS: startup validation +
  STAC walk succeed, it prints the dashboard URL + "mosaic: 300 cells indexed", and stays up. (A broken
  catalog fails here — that's a finding.)
- **Step 3 — server smoke (curl, scriptable):**
  - `GET /config.json` → 200; `colormap` has 9 entries, `legend` length 9, `item_count == 300`.
  - `GET /mosaic/WebMercatorQuad/tilejson.json?url=<mosaic>` → 200 with a `tiles` XYZ template + bounds.
  - `GET /mosaic/tiles/WebMercatorQuad/{z}/{x}/{y}.png?url=<mosaic>&bidx=1&nodata=255
    &resampling=nearest&colormap=<enc>` for a z/x/y inside the ROI → 200, `Content-Type: image/png`,
    non-empty body.
  - `GET /items.geojson` → 200, FeatureCollection with 300 features.
  - Writes `_result.json` (`metrics`={config_classes:9, item_count:300, mosaic_features:300,
    tile_bytes:>0}, `expected`={9,300,300,">0"}).
- **Step 4 — visual (the actual STAC verification):** open `http://127.0.0.1:8000/`. PASS if: the
  crop-map **mosaic** overlays Waldviertel in the right place with **distinct class colors** (not a
  continuous smear) and transparent nodata; **panning/zooming is snappy** (one layer, only in-view tiles
  load); the 300 **footprints** align with the raster; the legend matches the crop-map figure. Paste a
  **screenshot** + note any mis-color / mis-placement / missing-cell / seam (each a real finding, per
  Appendix-C history).
- **Stop:** Ctrl-C (read-only serving; nothing to clean up).

## Test plan (pytest — pure functions only; no server, no network)

Runs in `.venv-titiler` (skip the module if titiler/cogeo-mosaic not importable, like `test_grid.py`
skips without `[grid]`):

- **colormap/legend builder** — `sorted(CLASS_COLORS)` → a 9-entry discrete `{"0":hex,…,"8":hex}` +
  `legend`; assert code 0 = `alfalfa_lucerne`, 8 = `winter_common_soft_wheat`, colors match, every code
  0–8 present, 255 absent.
- **`walk_inference_stac` (pure)** — against a **tiny synthetic catalog fixture** (2 items): returns 2
  correct `(id, geometry, cog_href)`; a **duplicate-id** catalog raises; a **missing `output` href**
  raises (mirrors the spec-26 guard). No dependence on the 44 GB outputs.
- **MosaicJSON build (pure)** — feed 2 synthetic features (geometry + `properties.path`) to the build
  helper → a `MosaicJSON` whose tile index references **both** hrefs; assert both appear. (needs
  `cogeo-mosaic`; skip if absent.)
- **config/footprints assembly** — required keys present, `nodata==255`, `resampling=="nearest"`,
  `tms=="WebMercatorQuad"`, `item_count == len(items)`; `/items.geojson` is a valid FeatureCollection.
- **app wiring (optional, TestClient):** build a **2-COG synthetic mosaic** in a tmp dir (two tiny 1×1
  uint8 COGs + a 2-item catalog), start the app against it via FastAPI `TestClient`, and hit
  `/config.json` (200, 9 classes), `/mosaic/WebMercatorQuad/tilejson.json` (200), `/items.geojson`
  (200, 2 features). Keep lightweight; skip if it needs the network.

Target: pure tests pass in `.venv-titiler`; `ruff check` clean on the new files. The live render is the
runbook's job.

## Living docs to update (on implement)

- **`pyproject.toml`** — the `[titiler]` extra (D1).
- **`demos/TITILER_LEAFLET.md`** — already written (the explainer); add a one-line "how to run" pointer
  to `titiler_serve.py` once it exists.
- **`E2E_AUSTRIA.md`** — §3 note the `[titiler]` extra + `.venv-titiler`; a §8 "verify the STAC in a
  map" pointer to `TITILER_LEAFLET.md` + the runbook.
- **`RECIPES.md`** — append the launch command + the Step-3 curl smokes, so they're not lost.
- **`TODO #14`** — mark the titiler serving layer **DONE (local MVP, spec 27: MosaicJSON single-layer)**;
  keep **titiler-pgstac** (live pgSTAC, MPC-shaped) + **Blob/S3 serving** as the remaining scale items
  (link `TODO #17`).
- **`CHANGES.md`** — a note (additive demo/serving; no pipeline behavior change).
- **`PROGRESS.md`** + memory `fsd-status` — the checkpoint.

## Open questions for sign-off

1. **Colors from `CLASS_COLORS` import vs. a checked copy** (D5) — import preferred; flag if you'd
   rather the demo write a `class_map.json` at train time and the server read that (needs a re-run or a
   one-shot writer for the existing outputs). Default: import.
2. **MosaicJSON zoom range** (D3.4) — default `minzoom=8, maxzoom=15` for 10 m data, as a config
   constant (no COG opened to detect it). Say if you want it read from a sample COG instead.
3. **`.venv-titiler` vs. reuse `.venv-modeldeploy`** (D1) — dedicated venv recommended (keeps the
   reproducible demo venv untouched); reuse is fine if you'd rather not have a third venv.
