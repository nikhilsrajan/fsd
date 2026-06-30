# Spec 07 — Raster image utilities (`raster/images.py`)

Folds in: `rsutils/modify_images.py` + the raster helpers in `rsutils/utils.py`.

## Responsibility

The rasterio-level primitives the datacube builder (and deploy notebooks) depend
on. Two flavors:

- **File-based**: `(src_filepath, dst_filepath, sequence)` — read, apply ops, write.
- **In-memory**: operate on `(data, profile)` tuples — used by the in-memory
  datacube builder.

## Functions to carry over (names may be tidied)

| Function | Purpose |
|----------|---------|
| `crop(…, shapes_gdf, nodata, all_touched)` | mask/crop raster to geometry |
| `reproject(…, dst_crs)` | reproject raster |
| `resample_by_ref` / `resample_by_ref_meta` | match a reference grid/profile |
| `load_images(src_filepaths, shapes_gdf, …, njobs)` | parallel load+crop → `[(data,profile)]` |
| `modify_images` / `modify_images_inplace` | apply op sequence over many (parallel) |
| `merge_inplace(data_profile_list, nodata)` | mosaic in-memory rasters |
| `driver_specific_meta_updates(meta, driver)` | fix profile for GTiff etc. |
| small helpers: `get_epochs_str`, `modify_filepath`, `add_epochs_prefix` | temp paths |
| `save_geotiff(dst, data, profile)` | write any `(data, profile)` to GeoTIFF |
| `stack_bands(data_profile_list)` | stack single-band rasters (shared grid) → multi-band |
| `save_rgb_geotiff(dst, [r,g,b], scale_max=None)` | 3-band RGB GeoTIFF for QGIS (added for visual validation, TODO #7 done) |

## Decisions
- Keep the `(data, profile)` in-memory convention — the in-memory datacube engine
  is built on it.
- Trim `rsutils.utils` to only the raster/path helpers actually used; leave the
  rest behind (record in DROPPED.md). `rsutils` also pulls `seaborn`, `numba`,
  `s2`, `s2cell` — only bring what's needed (numba is needed by ops; plotting libs
  belong in notebooks, not core).

## Drops vs legacy
- Non-raster `rsutils` grab-bag (plotting, s2 grid helpers, rich-data filter,
  preprocessing, esa download) — not part of core; see DROPPED.md.

## Tests
- crop/reproject/resample on a synthetic raster produce expected shape/crs.
- `merge_inplace` mosaics two adjacent tiles correctly.
