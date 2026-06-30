"""Raster image utilities: crop / reproject / resample / merge / load.

Spec: specs/07-raster.md. Folds in rsutils.modify_images + raster helpers from
rsutils.utils. Two flavors: file-based and in-memory (data, profile) tuples — the
in-memory datacube builder is built on the latter.

NOTE (specs/10): rasterio reads remote rasters via GDAL VSI, not fsspec. For
remote sources, fetch to local scratch via fsd.storage.get first, or pass a VSI
path. Keep this in mind when implementing.
"""

from __future__ import annotations

import rasterio.warp

NEAREST = rasterio.warp.Resampling.nearest


# --- file-based --------------------------------------------------------------


def crop(src_filepath, dst_filepath, shapes_gdf, *, nodata=0, all_touched=True):
    raise NotImplementedError


def reproject(src_filepath, dst_filepath, *, dst_crs):
    raise NotImplementedError


def resample_by_ref(src_filepath, dst_filepath, *, ref_filepath, resampling=NEAREST):
    raise NotImplementedError


def modify_images(src_filepaths, dst_filepaths, sequence, *, njobs=1, raise_error=True,
                  print_messages=True):
    """Apply an op sequence over many files in parallel."""
    raise NotImplementedError


# --- in-memory (data, profile) ----------------------------------------------


def load_images(src_filepaths, *, shapes_gdf=None, nodata=0, all_touched=True,
                raise_error=False, njobs=1, print_messages=True):
    """Parallel load (+optional crop) -> list[(data, profile)]."""
    raise NotImplementedError


def modify_images_inplace(data_profile_list, sequence, *, njobs=1, print_messages=True):
    raise NotImplementedError


def resample_by_ref_meta(data_profile, *, ref_meta, resampling=NEAREST):
    raise NotImplementedError


def merge_inplace(data_profile_list, *, nodata=None):
    """Mosaic in-memory rasters -> (merged_data, merged_profile)."""
    raise NotImplementedError


# --- helpers -----------------------------------------------------------------


def driver_specific_meta_updates(meta, driver="GTiff"):
    raise NotImplementedError
