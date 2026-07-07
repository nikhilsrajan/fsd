# Spec 03 — Datacube builder (general engine + S2-L2A impl)

Folds in: `datacube/create_datacube_inmemory_single.py` (the working, in-memory
path). The older file-staging `core/create_datacube.py` is **not** carried over.

## Responsibility

For **one** geometry + date range, assemble a cloud-masked, time-mosaicked
datacube from the downloaded tiles and save it to disk.

## The engine seam

Expose a stable function the workflow layer and notebooks call, plus an internal
interface so an alternate backend (e.g. `rslearn`) can produce the same artifact:

```python
def build_datacube(
    catalog_subset: gpd.GeoDataFrame,   # tiles for this shape (band-flattened)
    shape_gdf: gpd.GeoDataFrame,        # single geometry (+ id, optional label)
    startdate, enddate,
    bands: list[str],
    *,
    mosaic_days: int,
    scl_mask_classes: list[int],
    reference_band: str = "B08",
    export_folderpath: str,
    njobs: int = 1, njobs_load_images: int = 1,
    if_missing_files: str = "raise_error",   # raise_error|warn|None
    max_timedelta_days: int = 5,
) -> None      # writes datacube.npy + metadata.pickle.npy
```

> Seam intent: `build_datacube` is the contract; the S2-L2A engine below is the
> default implementation. A future `rslearn`-backed builder must emit the same
> `datacube.npy` + `metadata.pickle.npy` so downstream (flatten/deploy) is
> unchanged. Keep engine internals private behind this signature.

## S2-L2A algorithm (preserve exactly)

1. **Missing-files check** (`if_missing_files`): area coverage == 100%, no time
   gaps > `max_timedelta_days`, every requested band present for every tile.
   `all`-missing always raises.
2. **Load + crop**: read each (tile,band) `.jp2`, crop to `shape` (all_touched,
   nodata=0), keep `(data, profile)` in memory; drop invalid images.
3. **dst_crs** = CRS with the highest mean area contribution among tiles.
   *Why:* `rasterio.merge` (step 4) requires a uniform CRS, so all tiles must
   collapse into a single zone; picking the max-area-contribution zone minimises
   the reprojected area. Deliberate, not incidental (TODO.md #5).
4. **Reference profile** = merge the `reference_band` (B08) images (reprojecting
   off-CRS ones to dst_crs first).
5. **Resample** every image whose crs/height/width ≠ reference to the reference
   profile (nearest). *Why a real B08 image and not a computed target grid:* the
   user does not trust `rasterio`'s resample to align pixels to an abstract target,
   so non-10 m bands are matched to an actual known-10 m image (B08). This is why
   output is uniformly 10 m; other target resolutions would need a different
   known-resolution reference image, not just different resample params (TODO.md #1).
6. **Stack** per sorted timestamp × band → 4-D `(timestamps|ids, H, W, bands)`;
   missing `(ts,band)` filled with nodata. When several tiles of the **same acquisition**
   cover the shape (it straddles an MGRS tile boundary), **all** are nodata-fill merged onto
   the reference grid — not collapsed to one (spec 20 bugfix; tie-break `dst_crs`-native first).
7. **Ops** (see `04-datacube-ops.md`): `apply_cloud_mask_scl(scl_mask_classes)`
   → `drop_bands(["SCL"])` → `median_mosaic(mosaic_days)`.
8. **Save** `datacube.npy` + `metadata.pickle.npy` (contract in `00-overview.md §6`).

### Notes carried from legacy
- No external `dst_crs` argument — determined in-situ (avoids extra reproject+resample).
- `njobs_load_images` separate from `njobs` (image load is light but I/O-bound;
  heavy steps use the global `njobs` so they don't fight Snakemake parallelism).
- Reference band = B08 (10 m) for S2 L2A.

## Drops vs legacy
- The file-staging engine (`crop_and_reproject` writing intermediate tiffs to a
  `working_dir`), the L1C/s2cloudless branch, the `datacube catalog` + config-id
  registry + IOU/geometry-dedup bookkeeping around datacube creation.

## Tests
- Synthetic tiny tiles (2 timestamps, mixed CRS) → datacube of expected shape,
  bands order, SCL dropped, mosaic count.
- Missing-band/area/time → correct flag + raise/warn behavior.
