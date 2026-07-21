# Run-book 34b — cross-baseline render proof (spec 34 §1e), self-contained

**You run this; Claude never runs Docker/networked scripts (spec 24).** Paste back
`tests/outputs/spec34_mixed_baseline/_result.json` + a note on what the 4-URL check showed.

**What it proves (spec 34 §1e).** fsd's ingest stamps each S2 granule's *own* processing-
baseline offset into its COG (GDAL scale/offset tag + STAC `raster:bands`). A titiler-pgstac
mosaic with `unscale=true` applies each item's offset **per-item, at read, before mosaicking**,
so imagery on **either side of the 2022-01-25 baseline cutover renders at consistent
brightness** — the harmonization MPC's own `sentinel-2-l2a` collection cannot provide (it exposes
no per-item offset). This is **the gap fsd's ingest fills** (spec 34 §1e).

**Runs on LOCAL copies (`[G6]`)** — validates the offset→unscale *mechanism* (storage-agnostic),
not blob-serving. Titiler-reads-blob (GDAL Azure auth inside the tiler) is a separate P5 item.

- **Time:** ~10 min total (a small download + the mini-MPC stack coming up).
- **Cost:** ~free (MPC anonymous; a handful of small COGs on local disk).

> **⚠️ This run-book is self-contained on purpose.** An earlier version delegated to
> `runbooks/30-tier2-mini-mpc.md` "verbatim, but with a different dataset", which sent the
> runner through five files and several commands that didn't apply to this slice (geoparquet
> export not consumed by the loader, a crop-map helper that can't render RGB, a compose mount
> hard-wired to the spec-30 Austria data). Everything you need is below. `demos/mini_mpc/`
> Docker mechanics are documented generically in `demos/mini_mpc/README.md`.

---

## Prerequisites

- [ ] Docker + Docker Compose.
- [ ] Core venv with `fsd` + the `mpc` extra: `pip install -e ".[dev,mpc]"` (no `[azure]` — stays
      local). The **stac-geoparquet** step is **not** needed (see Step 3); the core `.venv` suffices.
- [ ] QGIS (or any XYZ-tile viewer) for the visual Step 6.

## Step 1 — pull the mixed-baseline slice (local disk)

```bash
cd fsd
.venv/bin/python runbooks/scripts/34_mixed_baseline_slice.py \
    --dst tests/outputs/spec34_mixed_baseline
```

The script uses two **tight 5-day windows** over the same MGRS tile `T33UWP` — one pre-cutover
(2021-06) and one post-cutover (2022-06). Four bands (`B04,B03,B02,SCL` — visible RGB + mask for
the eyeball). Keep the windows narrow: MPC assets are **full 110 km MGRS tiles** (~100–270 MB per
band-COG), so a wide window is a multi-GB download. This slice is ~2 granules/window.

- **Expect:** two short progress runs, then a JSON dump ending `"pass": true`.
- **PASS if:** `_result.json`'s `"distinct_offsets"` shows **two different values** (e.g.
  `[-1000, 0]`) and `"pass"` is `true` — this proves the two windows really straddle the baseline
  cutover, not just "downloaded something." (`-1000` is the DN-unit offset in the *catalog*; the
  COG GDAL tag stores it reflectance-unit as `-0.1` — see Step 5.)
- **If it fails:** MPC discovery blips are transient — retry. A `max_tiles` error means the window
  matched more granules than the cap; **narrow the window** (don't just raise the cap — that
  multiplies the download).

## Step 2 — export a static STAC catalog

```bash
.venv/bin/python -c "
from fsd.catalog.catalog import TileCatalog
cat = TileCatalog('tests/outputs/spec34_mixed_baseline/catalog.parquet')
print(cat.to_stac('tests/outputs/spec34_mixed_baseline/stac'))
"
```

- **Expect:** a path to `.../stac/catalog.json`; the tree has **4 items** (2 pre + 2 post).
- This static STAC (`catalog.json` → collection → item JSONs) is the **only** artifact the loader
  needs. You do **not** need `stac-geoparquet` — `load_pgstac.py` converts this STAC to ndjson
  itself (see Step 3).

## Step 3 — bring up the mini-MPC stack, pointed at THIS slice

The compose stack bind-mounts one host folder to `/data` in the raster container, and it defaults
to the spec-30 Austria data. **You must repoint it at this slice, or every tile render 404s**
(`/data/<granule>/B04.tif: No such file or directory`). Set it in `demos/mini_mpc/.env`:

```bash
# demos/mini_mpc/.env  — FSD_OUTPUTS_DIR is relative to the compose dir
FSD_OUTPUTS_DIR=../../tests/outputs/spec34_mixed_baseline
```

Then bring the stack up (recreating the raster container so it picks up the new mount):

```bash
cd demos/mini_mpc
docker compose up -d --force-recreate raster
docker compose ps -a          # all 3 running; db healthy; raster shows 127.0.0.1:8082->8082
# verify the mount actually points at this slice:
docker inspect fsd-mini-mpc-raster --format '{{range .Mounts}}{{.Source}} -> {{.Destination}}{{"\n"}}{{end}}'
#   want: .../tests/outputs/spec34_mixed_baseline -> /data
```

- **PASS if:** all 3 containers up (db `healthy`, raster `running`) **and** the mount shows
  `spec34_mixed_baseline`. If `raster` is `restarting`, check `docker compose logs raster --tail 60`.

## Step 4 — load the slice into pgSTAC

```bash
cd ../..
.venv/bin/python demos/mini_mpc/load_pgstac.py \
    --stac-dir tests/outputs/spec34_mixed_baseline/stac \
    --outputs-dir tests/outputs/spec34_mixed_baseline \
    --result-json tests/outputs/spec34_mixed_baseline/_result_load.json
```

`--stac-dir` and `--outputs-dir` point at the **same physical folder** from different bases
(`--outputs-dir` is repo-root-relative here; `FSD_OUTPUTS_DIR` in `.env` is compose-dir-relative).
The loader rewrites each asset href to `/data/<path-under-outputs-dir>`, so `--outputs-dir` **must**
match the folder mounted in Step 3.

- **PASS if:** `_result_load.json` shows `collections: 1, items: 4`.
- **If it fails:** an href `"not under --outputs-dir"` error means `--outputs-dir` ≠ `FSD_OUTPUTS_DIR`.

## Step 5 — confirm the per-baseline offset was stamped (the core claim, numerically)

Before rendering, verify each item carries **its own** baseline's offset — this is what `unscale`
applies. This is the strongest proof of the mechanism and takes seconds:

```bash
.venv/bin/python -c "
import rasterio, glob, os
for p in sorted(glob.glob('tests/outputs/spec34_mixed_baseline/S2*/B04.tif')):
    yr = os.path.basename(os.path.dirname(p)).split('_')[2][:4]
    with rasterio.open(p) as s:
        print(yr, 'offset', round(s.offsets[0], 5), 'scale', s.scales[0])
"
```

- **PASS if:** **2021** items → `offset 0.0` (baseline < 04.00, no correction) and **2022** items →
  `offset -0.1` (baseline ≥ 04.00, i.e. −1000 DN expressed in reflectance units to pair with
  `scale=1/10000`, spec 34 §1a). Different baselines → different offsets = **conditional per-item
  application confirmed.**
- **Note the units:** the GDAL tag / STAC `raster:bands` offset is **reflectance-unit** (`-0.1`)
  so `unscale=true` (which computes `DN*scale + offset`) yields physical reflectance. The *catalog*
  `offset` column stays **DN-unit** (`-1000`) for the datacube builder. (Stamping the DN offset
  `-1000` alongside `scale=1/10000` was the black-tile bug fixed in `c2bf1f1`.)

## Step 6 — visual cross-baseline render (the §1e picture)

Register a search and view it. **Important:** titiler-pgstac's default mosaic is **newest-on-top**,
so a search over *both* years shows almost entirely the 2022 tiles — the 2021 (pre-baseline) tiles
are buried and never meet a 2022 tile on screen, so **the auto-mosaic hides the seam**. To see the
cross-baseline effect you must force both baselines visible with **two datetime-filtered searches**:

```bash
# register a 2021-only and a 2022-only search; each prints an {"id": "..."} you use below
Y21=$(curl -s -X POST http://127.0.0.1:8082/searches/register -H "Content-Type: application/json" \
  -d '{"collections":["sentinel-2-l2a"],"datetime":"2021-01-01/2021-12-31"}' \
  | python -c "import sys,json;print(json.load(sys.stdin)['id'])")
Y22=$(curl -s -X POST http://127.0.0.1:8082/searches/register -H "Content-Type: application/json" \
  -d '{"collections":["sentinel-2-l2a"],"datetime":"2022-01-01/2022-12-31"}' \
  | python -c "import sys,json;print(json.load(sys.stdin)['id'])")
echo "2021 search: $Y21"; echo "2022 search: $Y22"
```

Add these **four** XYZ layers in QGIS (Browser → XYZ Tiles → New Connection). Substitute the
printed ids; RGB = `B04,B03,B02`. **Match `rescale` to `unscale`:** `unscale=true` yields
reflectance (0–0.3), `unscale=false` yields raw DN (0–3000) — using one rescale for both is
meaningless (unscale changes the units 10000×).

```
# HARMONIZED — unscale=true, reflectance rescale. The two years should MATCH over common ground.
http://127.0.0.1:8082/searches/<Y21>/tiles/WebMercatorQuad/{z}/{x}/{y}.png?assets=B04&assets=B03&assets=B02&rescale=0,0.3&unscale=true&resampling=bilinear
http://127.0.0.1:8082/searches/<Y22>/tiles/WebMercatorQuad/{z}/{x}/{y}.png?assets=B04&assets=B03&assets=B02&rescale=0,0.3&unscale=true&resampling=bilinear

# RAW (negative control) — unscale=false, DN rescale. 2022 should look ~33% BRIGHTER than 2021.
http://127.0.0.1:8082/searches/<Y21>/tiles/WebMercatorQuad/{z}/{x}/{y}.png?assets=B04&assets=B03&assets=B02&rescale=0,3000&unscale=false&resampling=bilinear
http://127.0.0.1:8082/searches/<Y22>/tiles/WebMercatorQuad/{z}/{x}/{y}.png?assets=B04&assets=B03&assets=B02&rescale=0,3000&unscale=false&resampling=bilinear
```

- **PASS if:** with `unscale=true`, the **2021 and 2022 layers match** in brightness over the same
  ground (harmonized). With `unscale=false`, the **2022 layer is visibly brighter** than 2021 (the
  raw baseline step the harmonization removes). Toggling the year layers on/off over a common,
  cloud-free area is the clearest way to see it.
- **Why not a single mixed-year mosaic:** newest-on-top hides the 2021 tiles, so a single search
  can't show the seam. The two-search method isolates baseline as the only variable (same ROI,
  same orbit pair, only the year differs). Take screenshots of the true/false pair.

## Success criteria (paste back)

- Step 1 `_result.json`: `"pass": true`, `"distinct_offsets"` has 2+ entries.
- Step 4: `collections: 1, items: 4`.
- Step 5: 2021 → `offset 0.0`, 2022 → `offset -0.1` (conditional per-baseline stamp).
- Step 6: `unscale=true` matches across years; `unscale=false` shows 2022 brighter. Screenshots.

## Stop / observe / teardown

- Step 1 is short — Ctrl-C is safe, just re-run.
- Tear the stack down with `docker compose down` from `demos/mini_mpc/` when done (`.pgdata`
  persists; see `demos/mini_mpc/README.md` for reset/reload/delete-search commands).
