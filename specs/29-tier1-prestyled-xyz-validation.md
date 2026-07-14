# Spec 29 — Tier-1 serving validation: a pre-styled XYZ for the crop map, consumed by STACNotator

> **Status: SIGNED OFF (2026-07-14) — ready to implement.** Opus@high (interview → spec). Implements
> **TODO #26, Tier 1** (the fast, DB-free rung of the serving-contract validation). Signed off with the
> recommended defaults on the open questions (serve `merged.tif`; a `render.json` seam with a
> `CLASS_COLORS` fallback; a fixed pre-styled `/cropmap` route; STACNotator as a guided manual runbook
> step). **Hotspot-friendly — serves the existing `merged.tif` on disk; no downloads, no pgSTAC.**
> Implementation lands in a **Sonnet@medium** session against this spec (spec 24 D5); the live serving +
> STACNotator check is a **spec-24 runbook the user runs** (Claude does not run the server). Context: the serving pivot (`PROGRESS.md` LATEST 2026-07-14,
> `../STACNOTATOR_DIGEST.md`, memory [[fsd-serving-stacnotator]]). **Replaces** the superseded `specs/27`
> `titiler_serve` (which built a local Leaflet/MosaicJSON viewer) — here there is **no viewer**;
> STACNotator is the consumer and the deliverable is a **pre-styled XYZ URL**.

## Motivation

We've committed to serving fsd's outputs to **STACNotator** via standard endpoints (memory
[[fsd-serving-stacnotator]]). Before standing up the full pgSTAC + titiler-pgstac stack (Tier 2), prove
the **simplest** integration end-to-end, on artifacts that already exist, with no downloads: a
**pre-styled XYZ tile URL** for the crop map that STACNotator consumes through its **Bring-Your-Own-XYZ**
mode (`../STACNOTATOR_DIGEST.md §2` mode 3 — a plain `https://…/{z}/{x}/{y}.png` passed through as-is).

This de-risks the two rendering gotchas (`demos/TITILER_LEAFLET.md §7`) against the **real consumer**:
categorical `uint8` needs an explicit **discrete colormap** (not a continuous stretch), and the UTM→
WebMercator reproject must resample **nearest** (never blend class codes). It also prototypes the
**"model-developer submits a display config → fsd emits pre-styled tiles"** idea (the precursor to the
STAC render extension, TODO #28) with the categorical crop map as the first case.

## Non-goals (explicitly out)

- **No pgSTAC / titiler-pgstac / STAC API.** That's Tier 2 (TODO #26). This is a single pre-styled COG.
- **No fsd viewer / Leaflet page / MosaicJSON.** STACNotator is the viewer (this is why `specs/27` was
  cancelled). The deliverable is a URL, not a UI.
- **No `src/fsd/` change.** Serves the existing `merged.tif`; all new code under `demos/` + the
  `[titiler]` extra. (Categorical rendering issues here are display config, not pipeline bugs.)
- **No STAC catalog dependency.** Tier 1 serves one COG; it does not read `stac/` (that's Tier 2). *(The
  geometry fix, spec 28, is independent and lands in parallel — it matters for Tier 2's search, not for
  this single-COG render.)*
- **No downloads, no re-inference, no Azure.** Local `merged.tif` only. Not in the lean core `.venv`.

## Design

### D1 — Deps: a `[titiler]` optional extra (isolated venv)
```toml
titiler = [            # P5 serving validation (spec 29 Tier 1; grows for Tier 2). NOT fsd core.
    "rio-tiler>=6,<8",       # the COG tile read + render (the pre-styled route)
    "fastapi",               # the app
    "uvicorn[standard]",     # ASGI server
    # titiler.core / titiler.mosaic are added in Tier 2 (pgSTAC); Tier 1 needs only rio-tiler.
]
```
Install into a dedicated venv (keeps `.venv` / `.venv-modeldeploy` untouched):
`python3.11 -m venv .venv-titiler && .venv-titiler/bin/pip install -e ".[titiler]"`.
`rio-tiler` brings `rasterio` (already a core dep). Verified against `rio-tiler` 6.x (used by titiler
0.24 / STACNotator's own tiler).

### D2 — Deliverable shape
- **`demos/titiler_serve.py`** — a minimal FastAPI app that serves **one pre-styled XYZ layer** over
  `merged.tif`, plus a `python -m` / `__main__` `uvicorn.run` launcher. **No HTML.**
- **`runbooks/29-tier1-stacnotator-byo.md`** — the spec-24 runbook (install → launch → curl smoke →
  QGIS quick-check → STACNotator BYO), authored by Sonnet to §Verification.

### D3 — The pre-styled XYZ route (clean, param-free)
`GET /cropmap/tiles/{z}/{x}/{y}.png` — a hand-rolled route over `rio-tiler` so the external URL carries
**no query params** (a true pre-styled XYZ, ideal for BYO):
```python
from rio_tiler.io import Reader
from rio_tiler.errors import TileOutsideBounds

with Reader(MERGED) as r:                      # merged.tif, EPSG:32633 uint8 class map
    try:
        img = r.tile(x, y, z, indexes=[1], nodata=NODATA,        # NODATA=255
                     resampling_method="nearest")                # class codes: never interpolate
    except TileOutsideBounds:
        return Response(EMPTY_PNG, media_type="image/png")       # transparent 256×256
    png = img.render(img_format="PNG", colormap=CMAP)            # CMAP: discrete {code:(R,G,B,A)}
return Response(png, media_type="image/png",
                headers={"Cache-Control": "public, max-age=86400"})
```
- `indexes=[1]` — the single `crop_class` band. `nodata=255` → masked → **transparent** in the PNG
  (alpha 0), so the ROI's slanted edges / gaps show the basemap through. `resampling_method="nearest"`
  — rio-tiler reprojects UTM→WebMercator per tile; nearest is mandatory for class codes.
- `CMAP` = a **discrete** rio-tiler colormap `dict[int, (R,G,B,A)]` for **every** code 0–8 (D4); codes
  not in the map (incl. 255) render transparent.
- Out-of-bounds tiles → a cached transparent PNG (STACNotator renders nothing there; no 204 needed for
  BYO, but a transparent 200 is simplest and universally handled).

*(This mirrors exactly what STACNotator's own tiler does — `rio_tiler` `.tile()` + `.render()`,
`tiler/src/tiles.py` — so it's a faithful, minimal stand-in for the eventual titiler-pgstac tile.)*

### D4 — The render/colormap config (precursor to the render extension, TODO #28)
- Build `CMAP` from a **display config**: the categorical class-code→color map. **Source of truth =
  `demos/e2e_austria.py::CLASS_COLORS`** (shared with the crop-map figure); class order is deterministic
  (`sorted(le.classes_)`, all 9 present — see `E2E_AUSTRIA.md §8`), so `sorted(CLASS_COLORS)` gives codes
  0 = `alfalfa_lucerne` … 8 = `winter_common_soft_wheat`. Convert each hex → `(R,G,B,255)`.
- `titiler_serve.py` may `from e2e_austria import CLASS_COLORS` (side-effect-free import — the module has
  a `__main__` guard) **or** read a small **`render.json`** (`[{code,name,color}]`) if present, falling
  back to `CLASS_COLORS`. Preferring a `render.json` here is the deliberate seam toward TODO #28, where
  the *model bundle* supplies this config and fsd writes it as the STAC render extension — Tier 1 is the
  first consumer of that same config shape.

### D5 — App, CORS, launch
- **Startup:** resolve `--merged` (default `tests/outputs/demo_e2e/model_outputs/merged.tif`), `--host`
  (default `127.0.0.1`), `--port` (default `8000`). **Validate `merged.tif` exists** (else print the
  command that produces it — `demos/e2e_austria.py` — and exit non-zero). Build `CMAP`.
- **CORS is mandatory** — STACNotator's frontend (`localhost:5173`) fetches tiles cross-origin via
  `<img crossOrigin="anonymous">`, so add a permissive `CORSMiddleware` (`allow_origins=["*"]`). Without
  it the browser blocks the tiles. (This is *the* detail that makes BYO work in a browser.)
- **Print the ready-to-paste XYZ template** on startup, e.g.
  `http://127.0.0.1:8000/cropmap/tiles/{z}/{x}/{y}.png`, plus the `merged.tif` **bounds in lon/lat** (so
  the user knows where to pan in STACNotator/QGIS). Optionally expose it at `GET /` as JSON
  (`{xyz_template, bounds4326, class_legend}`) for convenience.
- **Launch:** `python -m demos.titiler_serve` → `uvicorn.run(app, …)`; "Ctrl-C to stop" (read-only).

### D6 — Conventions honored
Discrete categorical colormap + `nodata=255` transparent + `nearest` resampling (D3/D4) — the make-or-
break trio from `demos/TITILER_LEAFLET.md §7`. Output nodata is **255** (uint8 class raster), not the
datacube's 0.

## Verification (spec-24 runbook — the user runs it; Claude never runs the server)

`runbooks/29-tier1-stacnotator-byo.md` (Sonnet authors to these criteria); the user pastes back a
`_result.json` + a screenshot.

- **Step 1 — install:** `.venv-titiler` + `pip install -e ".[titiler]"`. PASS: `python -c "import
  rio_tiler, fastapi, uvicorn"` exits 0.
- **Step 2 — launch:** `.venv-titiler/bin/python -m demos.titiler_serve`. PASS: validates `merged.tif`,
  prints the XYZ template + bounds, stays up.
- **Step 3 — server smoke (curl, scriptable):** `GET /cropmap/tiles/{z}/{x}/{y}.png` for a z/x/y inside
  the Waldviertel ROI → **200, `Content-Type: image/png`, non-empty**; a far-away tile → transparent
  PNG. Writes `_result.json` (`tile_bytes>0`, `content_type=="image/png"`).
- **Step 4 — QGIS quick-check (optional, fast, no STACNotator):** add an **XYZ layer** with the template
  URL; pan to Austria. PASS: the crop map renders with **distinct class colors** (not a continuous
  smear), transparent nodata, correctly placed over the basemap. (Matches the project's QGIS-eyeballing
  principle; a fast pre-check before standing up STACNotator.)
- **Step 5 — STACNotator BYO (the real integration test):** run STACNotator locally (its own README:
  `AUTH_PROVIDER=local`, `make dev-init && make dev-up`); create a campaign/collection whose slice uses
  **Bring-Your-Own XYZ** = the fsd template URL. PASS: the crop map displays in STACNotator, correctly
  colored + placed, nodata transparent, panning/zooming loads only in-view tiles. Paste a **screenshot**
  + note any mis-color / mis-placement / CORS error (each a real finding). This answers the actual
  question: *is the fsd endpoint convenient for STACNotator?*
- **Stop:** Ctrl-C (read-only serving; nothing to clean up).

## Test plan (pytest — pure; no server beyond TestClient, no network)
Runs in `.venv-titiler` (skip the module if `rio_tiler` not importable, like `test_grid.py` skips
without `[grid]`):
- **colormap builder** — `sorted(CLASS_COLORS)` → a 9-entry discrete `{0:(R,G,B,255),…,8:…}`; assert
  code 0 = `alfalfa_lucerne`'s color, 8 = `winter…`'s, every code 0–8 present, 255 absent.
- **render.json override** — a `render.json` is honored over `CLASS_COLORS`; absent → falls back.
- **tile render smoke (TestClient)** — write a tiny synthetic uint8 COG (a few class codes + some 255) in
  a tmp dir, point the app at it, `GET /cropmap/tiles/{z}/{x}/{y}.png` for an in-bounds tile → 200,
  `image/png`, non-empty; an out-of-bounds tile → 200 transparent. Assert the CORS header is present.
- Keep it lightweight; no dependence on the 44 GB outputs or the network.

Target: pure tests pass in `.venv-titiler`; `ruff check` clean on the new files.

## Living docs to update (on implement)
- **`pyproject.toml`** — the `[titiler]` extra (D1).
- **`E2E_AUSTRIA.md`** — §3 note the `[titiler]` extra + `.venv-titiler`; a §8 "serve the crop map to
  STACNotator (BYO-XYZ)" pointer to this spec + the runbook.
- **`RECIPES.md`** — the launch command + the curl smoke + the QGIS-XYZ and STACNotator-BYO steps.
- **`CHANGES.md`** — additive demo/serving note (no pipeline behavior change).
- **`TODO #26`** — mark **Tier 1 DONE**; Tier 2 (pgSTAC + titiler-pgstac mini-MPC) remains.
- **`PROGRESS.md`** + memory [[fsd-status]] / [[fsd-serving-stacnotator]] — checkpoint.

## Open questions for sign-off
1. **Serve `merged.tif` (single display mosaic) vs. a per-cell COG** for Tier 1 — recommendation:
   `merged.tif` (one clean pre-styled layer; simplest true "pre-styled XYZ"). Per-cell + catalog is
   Tier 2.
2. **`render.json` seam now vs. just `CLASS_COLORS`** (D4) — recommendation: support `render.json` with a
   `CLASS_COLORS` fallback, so Tier 1 already consumes the config shape TODO #28 will emit.
3. **Bake a fixed `/cropmap` route vs. expose a parametric titiler `/cog` too** — recommendation: the
   fixed pre-styled route is the deliverable (clean BYO URL); add a parametric `/cog` (titiler.core) only
   if you want `/cog/info`/tilejson for debugging (defer to Tier 2).
4. **How far to script the STACNotator step** — recommendation: keep it a guided manual runbook step
   (STACNotator has its own dev setup); we validate the *endpoint*, not automate STACNotator.
