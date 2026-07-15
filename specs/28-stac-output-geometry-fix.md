# Spec 28 — STAC inference-output geometry: use the true S2-cell polygon, not the raster bbox

> **Status: DONE (2026-07-14) — reviewed (Opus@high), merged to `main` (`620441e`, not pushed), regen
> runbook PASS.** `catalog/stac.py::cog_outputs_to_items`
> gained `geometries=`, `_output_item_id`'s docstring untouched, new
> `cog_outputs_to_items_from_manifest`; `api.py::_finalize_outputs`/`_resolve_inference_pairs`/
> `_run_inference_roi` thread `geometries` from `input.csv.shapefilepath` per D1/D2; new
> `demos/regen_output_stac.py` + `runbooks/28-stac-geometry-regen.md` (the user runs the regen —
> not yet executed). 4 new tests (`tests/test_catalog_stac.py` ×3, `tests/test_model.py` ×1);
> `pytest -q` 213 passed / 2 skipped, `ruff check` clean. Docs updated: `CHANGES.md`, `BUGS.md`
> (BUG-003), `specs/17` pointer, `TODO.md` #27. **Signed off (2026-07-14) — ready to implement.**
> Opus@high (interview → spec). Implements
> **TODO #27**. Signed off with the **manifest-driven** design (D1/D2 revised per the user: geometry from
> `input.csv.shapefilepath`, deterministic, no sibling-file discovery, no raster-box fallback). Small,
> self-contained correctness fix to `catalog/stac.py::cog_outputs_to_items` (+ tests + STAC regeneration
> of the existing outputs). **Hotspot-friendly — no downloads, no network.** Implementation lands in a
> **Sonnet@medium** session against this spec (spec 24 D5); Claude (Opus) does not implement. Context: the serving pivot
> (`PROGRESS.md` LATEST 2026-07-14, `../STACNOTATOR_DIGEST.md`, memory [[fsd-serving-stacnotator]]) makes
> item geometry a **serving-correctness** concern, not a cosmetic one.

## Motivation

Every fsd inference-output STAC Item currently gets an **axis-aligned rectangle** for its `geometry`:
`catalog/stac.py::cog_outputs_to_items` reads the output COG's bounds and builds
`geom = shapely.geometry.box(*bounds4326)` (`stac.py:183`). But an fsd datacube/output is a **north-up
raster rectangle that does not hug the ROI** — it carries a nodata halo and its valid footprint is the
**slanted S2 grid-cell polygon** (`fsd.grid.roi_to_s2_grids`), which is written to **`geometry.geojson`
in every cell/datacube folder** (CRS84). So the Item footprint **over-claims coverage**.

Confirmed on the real Austria run (cell `477303c`):
- `geometry.geojson` (truth): a slanted quadrilateral —
  `(14.766,48.492) (14.789,48.534) (14.847,48.526) (14.825,48.484)`.
- STAC Item `geometry`: the bbox rectangle — `(14.766,48.484)–(14.847,48.534)`, north-aligned.

**Why this is now serving-critical (not cosmetic):**
- STACNotator's self-hosted tiler does a per-tile **`ST_Intersects(item.geom, tile)`**
  (`../stacnotator/tiler/src/tiles.py:87`) to decide which COGs to read; a boxy footprint makes items
  match tiles that are actually **all nodata** → wasted COG reads.
- **pgSTAC search** (the titiler-pgstac / MPC path fsd is targeting) keys mosaics off item geometry →
  wrong/loose search hits.
- The footprint is the durable thing every downstream consumer trusts. STAC's `geometry` is meant to be
  the **footprint of the data**, and a bounding box is a coarse over-approximation the spec discourages
  when the real footprint is known — and here it *is* known, sitting right next to the COG.

## Non-goals (explicitly out)

- **No change to `tile_catalog_to_items`.** The *tile* catalog path already uses the true catalog
  geometry (`row["geometry"]`); only the inference-output path is wrong.
- **No `proj:*` change.** `proj:shape` / `proj:transform` / `proj:code` correctly describe the raster
  grid and stay read from the COG.
- **No re-inference, no downloads.** Serves/regenerates over the existing outputs on disk.
- **No new item-builder signature churn beyond what the fix needs** (see D2 for the one design choice).

## Design (revised 2026-07-14 per user: drive geometry from `input.csv`, deterministically — no sibling-file discovery, no fallback)

**Key decision (user):** the STAC creation must be **deterministic and manifest-driven**, not a
filesystem heuristic. `run_inference` already builds every output from a **build manifest `input.csv`**
whose **`shapefilepath`** column points at each cell's `geometry.geojson` (written by
`workflows/create_datacube.py:84`; columns: `shapefilepath, export_folderpath, id, …`). The STAC
creation reads **the same `input.csv`** to pair each output COG with its true footprint — no
`dirname(output.tif)/geometry.geojson` guessing, no raster-box fallback.

### D1 — Thread the geometry through from the manifest (`input.csv.shapefilepath`)
- **`cog_outputs_to_items(cog_filepaths, *, geometries=None, …)`** gains a `geometries` argument: a
  mapping **`{output_cog_filepath: geometry.geojson path}`** (dict, keyed by COG path — robust to the
  ordering/`sorted()` the caller does elsewhere). For each output COG, read the polygon from its mapped
  `geometry.geojson` through the **`fsd.storage`** seam (`fs.open`); it is **CRS84 == EPSG:4326 lon/lat**,
  so **no reprojection** — use it as the Item `geometry`, `bbox = polygon.bounds`.
- **Both inference modes supply `geometries` from `input.csv`:**
  - **ROI mode** (`api._run_inference_roi`) already reads the manifest back to collect outputs
    (`api.py:801-806`: `output.tif = <export_folderpath>/output.tif`). Thread `shapefilepath` from the
    same rows → `geometries = {out: shapefilepath}` → pass into `_finalize_outputs` →
    `cog_outputs_to_items`.
  - **Pre-built `input.csv` mode** (`_resolve_inference_pairs`, `api.py:399`) already parses the csv;
    capture `shapefilepath` alongside `datacube_filepath`/`id` and build the same map.
- `_finalize_outputs` gains a `geometries=` param it forwards to `cog_outputs_to_items` (it keeps doing
  the merge over `output_filepaths` unchanged).
- Everything else stays as today — `id` (`_output_item_id`), `proj:shape`/`proj:transform`/`proj:code`
  from the COG, the single `output` asset, `dt`, `collection`, and the **uniqueness guard**.

### D2 — No discovery, no fallback (deterministic contract)
- The sibling-file discovery + per-item warn-fallback from the first draft is **removed** (user: "fallback
  becomes unnecessary"). When `geometries` is provided, **every** output COG must have an entry with a
  readable polygon; a missing/unreadable/empty one **raises** a clear error (a manifest that lists an
  output but no footprint is a real inconsistency — fail loud, don't silently box).
- **`geometries=None`** keeps the **existing raster-box behavior** unchanged — this is *not* a per-item
  fallback but the explicit "no manifest supplied" path for geometry-less callers (unit tests; a bare
  list of arbitrary COGs; the folder/list pre-built modes that have no `input.csv`). The **real
  `run_inference` pipeline always passes `geometries`**, so its outputs are always geometry-accurate.
- **Optional guard:** if the `geometry.geojson`'s `properties.id` disagrees with `_output_item_id(cog)`,
  raise (deterministic pairing must hold). The **uniqueness guard** on item ids is unchanged.

*(Folder/list pre-built modes without an `input.csv` (`_resolve_inference_pairs` glob/list branches) have
no `shapefilepath`; they pass `geometries=None` → raster box, as today. If geometry-accurate STAC is ever
needed there too, source it from `<datacube_folder>/geometry.geojson` — the same file the manifest points
at — but that's out of scope here: the run_inference model-output path is manifest-driven.)*

### D3 — bbox / STAC validity
`bbox` becomes the polygon bounds (tighter, and STAC-valid: `bbox` contains `geometry`). A minor, correct
change from today's raster bbox.

### D4 — Regenerate the existing 300-item STAC (from the same `input.csv`)
The fix changes *new* STAC writes; the outputs already on disk (`tests/outputs/demo_e2e/model_outputs/
stac/`) still carry box geometries. Regenerate them **from the existing manifest**
(`tests/outputs/demo_e2e/model_outputs/cells/input.csv`) — **no re-inference, no downloads** (reads 300
COG headers + the 300 `shapefilepath` geometries, rewrites JSON):

```python
# regeneration = re-run just the STAC tail, manifest-driven (deterministic; no compute, no download)
import pandas as pd
from fsd.catalog import stac as _stac
rows = pd.read_csv(".../model_outputs/cells/input.csv")
geometries = {f"{exp}/output.tif": sp for exp, sp in zip(rows.export_folderpath, rows.shapefilepath)}
cogs = [c for c in geometries if os.path.exists(c)]
items = _stac.cog_outputs_to_items(cogs, geometries=geometries,
                                   collection_id="fsd-inference", band_names=["crop_class"])
_stac.write_stac_catalog(items, ".../model_outputs/stac", catalog_id="fsd-inference",
                         collection_id="fsd-inference")
```

Ship this as a tiny `demos/regen_output_stac.py` (reads `input.csv`), run as a **runbook step** (the user
runs it; Claude does not) — it writes a `_result.json` reporting `{items, distinct_ids,
non_rectangular_geoms}`.

## Verification

**pytest (pure, deterministic, no network):**
- **New:** write a tiny synthetic output COG + a `geometry.geojson` (non-rectangular polygon) in a temp
  dir; call `cog_outputs_to_items([cog], geometries={cog: geom_path})`; assert the Item `geometry` equals
  that polygon (not the raster box), `bbox == polygon.bounds`, and it's **not** an axis-aligned rectangle
  (4 corners ≠ two distinct x's × two distinct y's).
- **New (deterministic contract):** `geometries` provided but **missing an entry** for a COG (or the
  mapped file is unreadable) → **raises** (no silent box).
- **New (geometry-less path):** `cog_outputs_to_items([cog])` with `geometries=None` → the raster-bounds
  box (today's behavior preserved, unchanged for geometry-less callers/tests).
- **Regression:** `test_run_inference_writes_cogs_and_stac` (spec 26) still passes — it exercises the
  `geometries=None` path unless updated to thread the manifest; add/extend one assertion that the
  ROI/`input.csv` path yields the polygon geometry.

**Runbook (spec-24, the user runs) — hotspot-friendly:**
- Regenerate the demo STAC (D4) → `_result.json`: `items==300`, `distinct_ids==300`,
  `non_rectangular_geoms==300` (every cell's footprint is now the slanted polygon).
- *(Optional visual, folds into spec 29's STACNotator check)*: once the outputs are served, the item
  footprints overlay the true cell shapes, not boxes.

Target: full `pytest -q` green (+2 tests), `ruff check` clean.

## Living docs to update (on implement)
- **`CHANGES.md`** — a note (behavior change: inference-output Item geometry is now the true cell
  polygon, from the sibling `geometry.geojson`; bbox tightened; fallback to raster box).
- **`BUGS.md`** — a BUG entry (over-claiming footprint; found during the STACNotator serving study).
- **`specs/17-stac-catalog.md`** — pointer to this fix (it owns `cog_outputs_to_items`).
- **`TODO #27`** — mark DONE.
- **`PROGRESS.md`** + memory [[fsd-status]] — checkpoint.

## Open questions for sign-off
1. **`geometries` as `{cog: geom_path}` vs. `{cog: shapely polygon}`** — recommendation: `{cog: geom_path}`
   (the item builder reads the file, keeping the manifest→path mapping the single source of truth); pass
   pre-parsed polygons only if a caller already has them in memory.
2. **A convenience `cog_outputs_to_items_from_manifest(input_csv)` wrapper** (reads `input.csv`, builds
   `geometries`, calls the low-level) — realizes "STAC creation uses the same `input.csv`" directly, and
   `_finalize_outputs` + the regen script both call it. Recommendation: **yes**, add the thin wrapper.
3. **Regeneration as a committed `demos/regen_output_stac.py` (reads `input.csv`) vs. a one-off
   `python -c`** — recommendation: a tiny committed script (reusable; deterministic; handy after any run).

*(Resolved by the user 2026-07-14: geometry source = `input.csv.shapefilepath` (deterministic,
manifest-driven), **not** sibling-file discovery; **no raster-box fallback** in the manifest path — missing
geometry raises.)*
