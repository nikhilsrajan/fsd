# Spec 20 — bugfix: datacube builder drops tiles when several cover one shape

> **Status: SIGNED OFF + IMPLEMENTED (2026-07-07).** SO-1..SO-4 approved as drafted. Fixed
> `_stack_datacube` (per-`(timestamp,band)` nodata-fill merge, native-CRS-first tie-break) +
> 2 targeted unit tests; the existing single-tile e2e test is the no-op case. **Verified on real
> data:** the worst demo grid `165b09c` went **0.6 % → 82.8 % valid** (≈ its raw coverage). Demo
> re-run in progress to refresh the report/figures.
>
> A **correctness bug** in the datacube builder,
> found via the spec-19 end-to-end demo: a shape covered by **multiple tiles of the same
> acquisition** (i.e. straddling a Sentinel-2 MGRS tile boundary) keeps only **one** tile's
> data per `(timestamp, band)` and nodata-fills the rest. Fix = merge all same-`(timestamp,
> band)` images onto the reference grid instead of picking one. Contained change to
> `datacube/builder.py::_stack_datacube` + a synthetic test + re-run the demo.

## Symptom
In the spec-19 demo (300 inference grids over the Ethiopia ROI), **9 grids came out ~nodata**
(3 under 10 % valid) while their neighbours were 70–90 % valid. They cluster on a horizontal
band at **lat ~11.75** — an MGRS tile-**row** boundary. Worst grid `165b09c`: built datacube is
**0.6 % valid**, with data only in **rows 525–548 of 549** (a thin southern sliver), even though
the raw source tiles cover **~80 %** of it.

## Root cause
`datacube/builder.py::_stack_datacube`:
```python
ts_band_index = dict(zip(zip(catalog_gdf["timestamp"], catalog_gdf["band"]),
                         catalog_gdf["image_index"]))   # <-- dict: one image per (ts, band)
...
stack = [data_profile_list[ts_band_index[(ts, b)]][0] if (ts, b) in ts_band_index else missing
         for b in bands]
```
Adjacent MGRS tiles from **one orbit pass share an identical acquisition timestamp**. When a
shape overlaps several such tiles, they collide on `(timestamp, band)` and the dict keeps only
the **last** one — so the shape gets a single tile's crop, and wherever that tile has no data
(the rest of the shape) is nodata.

**Confirmed:** grid `165b09c` has **4 tiles at 100 % of its 72 timestamps**
(`T37PBP`,`T37PBN`,`T36PZU`,`T36PZT` — it meets a tile-row boundary *and* the 36°E zone
boundary); the builder keeps 1 of 4. A "healthy" neighbour `165b0a4` also collides (2 tiles/ts)
but the retained tile happens to cover 82 %, so it *looks* fine — meaning **partial silent data
loss is widespread**, not limited to the 9 obvious grids.

**Why it wasn't caught:** training/flatten uses small field polygons that sit inside a single
tile (one image per `(timestamp, band)` → no collision). Only large shapes — the **5 km
inference grids** (new in spec 19) — straddle tile boundaries. The multi-CRS `datacube.md`
QGIS check likely landed on a region the retained tile happened to cover. Legacy
`fetch_satdata` has the same `dict((ts,band)->image)` shape, so this is almost certainly a
**faithfully-ported legacy bug**, not a rewrite regression.

## The fix
Everything is already **resampled onto the single reference grid** (same H×W, `dst_crs`) before
stacking (`_resample_by_indices`). So combining multiple images for one `(timestamp, band)` is a
cheap element-wise **nodata-fill merge** on the reference grid:

```python
# group ALL image_indices per (timestamp, band), not one:
from collections import defaultdict
ts_band_indices = defaultdict(list)
for ts, b, idx in zip(catalog_gdf["timestamp"], catalog_gdf["band"], catalog_gdf["image_index"]):
    ts_band_indices[(ts, b)].append(idx)

def _merge_on_ref(indices):
    out = np.full((1, ref_h, ref_w), nodata, dtype=fill_dtype)
    for idx in _order(indices):                      # deterministic order (below)
        img = data_profile_list[idx][0]              # (1, ref_h, ref_w)
        out = np.where(out == nodata, img, out)      # first valid wins
    return out
```

- **Overlap tie-break `_order` [SO-1]:** where two tiles both have valid data (tile overlaps +
  the 10 % grid overlap), first-valid-wins, so order matters. Prefer **`dst_crs`-native tiles
  over reprojected ones** (reprojected pixels are resampled → slightly softer), then by
  `image_index` for determinism. (Alternative: keep legacy "last wins" — rejected; native-first
  is a small quality win and deterministic.)
- **Cross-band consistency [SO-2]:** each band is merged independently, but S2 tiles share one
  valid footprint across bands (a granule's nodata mask is the same for B04/B08/SCL), so a given
  pixel resolves to the same tile for every band → no B04-from-A / SCL-from-B mixing in practice.
  Documented as an assumption; not enforced.
- **Missing `(ts, band)`** still nodata-fills (unchanged). `nodata = config.NODATA = 0`.

No change to `dst_crs` selection, the reference profile, resampling, SCL masking, or
`median_mosaic`. Output shape/axes unchanged — the same cube, now correctly filled.

## Scope of impact (what changes in outputs)
- Any shape overlapping **>1 tile per acquisition** now gets **all** their coverage, not one.
  Boundary-straddling inference grids go from partly/mostly-nodata → full. Small single-tile
  shapes (training fields) are **unaffected** (one image per `(ts, band)` → merge is a no-op).
- The existing `satellite_benchmark` multi-CRS `datacube.md` cube should gain coverage too;
  re-eyeball in QGIS as part of verification.

## Tests (`tests/test_datacube*.py`, synthetic)
- **Boundary case (new):** two synthetic same-`timestamp` images that each cover **half** the
  reference grid (complementary nodata) → after stack the `(timestamp, band)` slice is **fully
  valid** (today: half nodata). Assert the pre-fix dict behavior would have dropped one.
- **Overlap tie-break:** two images with an overlapping valid region → the `_order` winner’s
  values appear in the overlap; deterministic across runs.
- **No-op for single-tile:** one image per `(ts, band)` → identical to current output.
- Existing datacube tests must still pass (single-tile fixtures unchanged).

## Ripple effects
- `datacube/builder.py::_stack_datacube` only (plus a small `_merge_on_ref`/`_order` helper).
- `CHANGES.md` — behavior change: multi-tile shapes now merge same-timestamp tiles (was: keep
  one). `BUGS.md`/`TODO.md` — record the found+fixed bug. `specs/03-datacube.md` /
  `specs/04-datacube-ops.md` — note the per-`(ts,band)` merge step. `PROGRESS.md`.
- `tests/manual/datacube.md` — add a boundary-straddling grid to the QGIS checklist.
- **Re-run the spec-19 demo** after the fix → the lat-11.75 gaps should close; update
  `demos/README.md` + figures. (The zone-mixing *display* merge remains a separate, cosmetic
  item — optionally improve `demos/_merge_for_display` to a common-grid 4326 mosaic.)

## Sign-off checklist
- [x] **[SO-1]** Overlap tie-break = `dst_crs`-native first, then `image_index` (deterministic
      first-valid-wins), replacing legacy last-wins.
- [x] **[SO-2]** Per-band independent nodata-fill; document the shared-footprint assumption
      (no cross-band pixel mixing in practice).
- [x] **[SO-3]** Fix is confined to `_stack_datacube`; `dst_crs`/reference/resample/mask/mosaic
      and the output shape/axes unchanged.
- [x] **[SO-4]** Tests: `test_stack_merges_multiple_tiles_same_timestamp` (boundary
      full-coverage) + `test_stack_overlap_tiebreak_prefers_native_crs`; the single-tile no-op is
      the existing `test_build_datacube_end_to_end`. Existing datacube tests green. Demo re-run +
      report/figure refresh in progress.
