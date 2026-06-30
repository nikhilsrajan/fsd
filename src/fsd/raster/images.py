"""Raster image utilities: crop / reproject / resample / merge / load.

Spec: specs/07-raster.md. Folds in rsutils.modify_images + the raster/path
helpers from rsutils.utils that the data-prep path actually uses.

Convention (locked, specs/07): every in-memory op takes ``(data, profile)`` as
its first two arguments and returns ``(data, profile)``. This lets ops be chained
as a ``sequence`` of ``(func, kwargs)`` pairs (see ``modify_image_inplace``). The
in-memory datacube builder is built entirely on this convention.

NOTE (specs/10): rasterio reads rasters through GDAL's VSI layer, not fsspec, so
the file-based functions here open paths with ``rasterio.open`` directly. For a
*remote* source, fetch to local scratch via ``fsd.storage.get`` first (or pass a
GDAL ``/vsi*/`` path). Whole-file downloads stay in ``fsd.storage``; pixel reads
live here.
"""

from __future__ import annotations

import datetime
import functools
import multiprocessing as mp
import os
import random
import string

import numpy as np
import rasterio
import rasterio.io
import rasterio.mask
import rasterio.merge
import rasterio.transform
import rasterio.warp
import tqdm

NEAREST = rasterio.warp.Resampling.nearest

__all__ = [
    "NEAREST",
    # in-memory (data, profile) ops
    "crop",
    "reproject",
    "resample_by_ref_meta",
    "resample_by_ref",
    "merge_inplace",
    # sequence runners
    "modify_image_inplace",
    "modify_images_inplace",
    # file-based
    "crop_tif",
    "load_image",
    "load_images",
    "modify_image",
    "modify_images",
    "read_tif",
    # helpers
    "driver_specific_meta_updates",
    "image_to_memfile",
    "images_to_memfiles",
    "delete_aux_xml",
    "modify_filepath",
    "get_random_alnum_str",
    "get_epochs_str",
    "add_epochs_prefix",
]


# --- parallel-map helper -----------------------------------------------------


def _pmap(func, items, njobs, print_messages):
    """Map ``func`` over ``items``. Serial when ``njobs == 1`` (no Pool, so it
    stays usable inside tests and other already-parallel contexts); otherwise a
    ``multiprocessing.Pool``. Optional tqdm progress bar."""
    items = list(items)
    if njobs == 1:
        it = tqdm.tqdm(items) if print_messages else items
        return [func(x) for x in it]
    with mp.Pool(njobs) as p:
        mapped = p.imap(func, items)
        if print_messages:
            mapped = tqdm.tqdm(mapped, total=len(items))
        return list(mapped)


# --- in-memory (data, profile) ops -------------------------------------------


def crop(
    data: np.ndarray,
    profile: dict,
    shapes_gdf,
    nodata=None,
    all_touched: bool = False,
    crop: bool = True,
) -> tuple[np.ndarray, dict]:
    """Mask/crop an in-memory raster to ``shapes_gdf`` (reprojected to the raster
    CRS). Returns cropped ``(data, profile)``."""
    out_profile = profile.copy()
    if nodata is None:
        nodata = profile["nodata"]

    with rasterio.io.MemoryFile() as memfile:
        with memfile.open(**profile) as dataset:
            dataset.write(data)
            shapes = shapes_gdf.to_crs(dataset.crs)["geometry"].to_list()
            out_data, out_transform = rasterio.mask.mask(
                dataset, shapes, crop=crop, nodata=nodata, all_touched=all_touched,
            )

    out_profile.update({
        "height": out_data.shape[1],
        "width": out_data.shape[2],
        "transform": out_transform,
        "nodata": nodata,
    })
    return out_data, out_profile


def reproject(
    data: np.ndarray,
    profile: dict,
    dst_crs,
    resampling=NEAREST,
) -> tuple[np.ndarray, dict]:
    """Reproject an in-memory raster to ``dst_crs``. No-op if already there."""
    src_crs = profile["crs"]
    if src_crs == dst_crs:
        return data, profile

    src_count = profile["count"]
    src_width = profile["width"]
    src_height = profile["height"]
    src_transform = profile["transform"]
    src_bounds = rasterio.transform.array_bounds(
        height=src_height, width=src_width, transform=src_transform
    )

    transform, width, height = rasterio.warp.calculate_default_transform(
        src_crs, dst_crs, src_width, src_height, *src_bounds
    )

    out_profile = profile.copy()
    out_profile.update({
        "crs": dst_crs,
        "transform": transform,
        "width": width,
        "height": height,
    })
    out_profile = driver_specific_meta_updates(meta=out_profile)

    nodata = profile["nodata"]
    out_data = np.full(
        (src_count, height, width),
        fill_value=nodata if nodata is not None else 0,
        dtype=profile["dtype"],
    )

    for i in range(src_count):
        rasterio.warp.reproject(
            source=data[i],
            destination=out_data[i],
            src_transform=src_transform,
            src_crs=src_crs,
            dst_transform=transform,
            dst_crs=dst_crs,
            resampling=resampling,
        )

    return out_data, out_profile


def resample_by_ref_meta(
    data: np.ndarray,
    profile: dict,
    ref_meta: dict,
    resampling=NEAREST,
) -> tuple[np.ndarray, dict]:
    """Resample an in-memory raster onto the grid (transform/size/CRS) described
    by ``ref_meta``, keeping the source's nodata/dtype/count."""
    out_profile = ref_meta.copy()
    out_profile["nodata"] = profile["nodata"]
    out_profile["dtype"] = profile["dtype"]
    out_profile = driver_specific_meta_updates(
        meta=out_profile, driver=profile["driver"]
    )
    out_profile["count"] = profile["count"]

    nodata = out_profile["nodata"]
    out_data = np.full(
        (out_profile["count"], out_profile["height"], out_profile["width"]),
        fill_value=nodata if nodata is not None else 0,
        dtype=out_profile["dtype"],
    )

    for i in range(out_profile["count"]):
        rasterio.warp.reproject(
            source=data[i],
            destination=out_data[i],
            src_transform=profile["transform"],
            dst_transform=out_profile["transform"],
            src_nodata=profile["nodata"],
            dst_nodata=out_profile["nodata"],
            src_crs=profile["crs"],
            dst_crs=out_profile["crs"],
            resampling=resampling,
        )

    return out_data, out_profile


def resample_by_ref(
    data: np.ndarray,
    profile: dict,
    ref_filepath: str,
    resampling=NEAREST,
) -> tuple[np.ndarray, dict]:
    """``resample_by_ref_meta`` with the reference grid read from a file."""
    with rasterio.open(ref_filepath) as ref:
        ref_meta = ref.meta.copy()
    return resample_by_ref_meta(
        data=data, profile=profile, ref_meta=ref_meta, resampling=resampling
    )


def merge_inplace(data_profile_list, nodata=None) -> tuple[np.ndarray, dict]:
    """Mosaic a list of in-memory rasters into one ``(data, profile)``."""
    merged_profile = data_profile_list[0][1].copy()
    memfiles = images_to_memfiles(data_profile_list)

    merged_data, merged_transform = rasterio.merge.merge(
        [memfile.open() for memfile in memfiles], nodata=nodata
    )

    merged_profile.update({
        "nodata": nodata,
        "count": merged_data.shape[0],
        "height": merged_data.shape[1],
        "width": merged_data.shape[2],
        "transform": merged_transform,
    })
    return merged_data, merged_profile


# --- sequence runners --------------------------------------------------------


def modify_image_inplace(
    data: np.ndarray,
    profile: dict,
    sequence: list,
    raise_error: bool = True,
) -> tuple[np.ndarray, dict]:
    """Apply an ordered ``[(func, kwargs), ...]`` op sequence to one in-memory
    raster. On failure with ``raise_error=False`` returns ``(None, None)``."""
    failed = False
    for func, kwargs in sequence:
        try:
            new_data, new_profile = func(data=data, profile=profile, **kwargs)
            del data, profile
            data, profile = new_data, new_profile
        except Exception:
            if raise_error:
                raise
            failed = True
            break
    if failed:
        return None, None
    return data, profile


def _modify_image_inplace_by_tuple(data_profile, sequence, raise_error):
    data, profile = data_profile
    return modify_image_inplace(
        data=data, profile=profile, sequence=sequence, raise_error=raise_error
    )


def modify_images_inplace(
    data_profile_list,
    sequence: list,
    njobs: int = 1,
    raise_error: bool = True,
    print_messages: bool = True,
):
    """Apply an op sequence over many in-memory rasters."""
    func = functools.partial(
        _modify_image_inplace_by_tuple, sequence=sequence, raise_error=raise_error
    )
    return _pmap(func, data_profile_list, njobs, print_messages)


# --- file-based --------------------------------------------------------------


def crop_tif(
    src_filepath: str,
    shapes_gdf,
    nodata=None,
    all_touched: bool = False,
) -> tuple[np.ndarray, dict]:
    """Crop straight from a file. Cheaper than load-then-crop: rasterio only
    reads the windowed region rather than the whole raster."""
    with rasterio.open(src_filepath) as src:
        out_meta = src.meta.copy()
        if nodata is None:
            nodata = out_meta["nodata"]
        shapes = shapes_gdf.to_crs(src.crs)["geometry"].to_list()
        out_image, out_transform = rasterio.mask.mask(
            src, shapes, crop=True, nodata=nodata, all_touched=all_touched,
        )

    out_meta.update({
        "height": out_image.shape[1],
        "width": out_image.shape[2],
        "transform": out_transform,
        "nodata": nodata,
    })
    out_meta = driver_specific_meta_updates(meta=out_meta)
    return out_image, out_meta


def load_image(
    src_filepath: str,
    shapes_gdf=None,
    nodata=None,
    all_touched: bool = True,
    raise_error: bool = True,
) -> tuple[np.ndarray, dict]:
    """Load a raster (optionally cropping to ``shapes_gdf``) into ``(data,
    profile)``. On failure with ``raise_error=False`` returns ``(None, None)``."""
    try:
        if shapes_gdf is None:
            with rasterio.open(src_filepath) as src:
                return src.read(), src.meta.copy()
        return crop_tif(
            src_filepath=src_filepath,
            shapes_gdf=shapes_gdf,
            nodata=nodata,
            all_touched=all_touched,
        )
    except Exception:
        if raise_error:
            raise
        return None, None


def _load_image_partial(src_filepath, shapes_gdf, nodata, all_touched, raise_error):
    return load_image(
        src_filepath=src_filepath,
        shapes_gdf=shapes_gdf,
        nodata=nodata,
        all_touched=all_touched,
        raise_error=raise_error,
    )


def load_images(
    src_filepaths: list[str],
    shapes_gdf=None,
    nodata=None,
    all_touched: bool = True,
    raise_error: bool = True,
    njobs: int = 1,
    print_messages: bool = True,
):
    """Parallel load (+optional crop) -> ``list[(data, profile)]``."""
    func = functools.partial(
        _load_image_partial,
        shapes_gdf=shapes_gdf,
        nodata=nodata,
        all_touched=all_touched,
        raise_error=raise_error,
    )
    return _pmap(func, src_filepaths, njobs, print_messages)


def modify_image(
    src_filepath: str,
    dst_filepath: str,
    sequence: list,
    raise_error: bool = True,
) -> bool:
    """Read ``src_filepath``, apply ``sequence``, write ``dst_filepath``.

    If the first op is ``crop``, it is performed straight from disk (only the
    relevant window is read) rather than loading the full raster into memory.
    Returns whether the destination was written.
    """
    failed = False
    first_func, first_kwargs = sequence[0]
    if first_func is crop:
        try:
            data, profile = crop_tif(src_filepath, **first_kwargs)
            sequence = sequence[1:]
        except Exception:
            if raise_error:
                raise
            failed = True
    else:
        with rasterio.open(src_filepath) as src:
            data = src.read()
            profile = src.meta.copy()

    if not failed and len(sequence) > 0:
        data, profile = modify_image_inplace(
            data=data, profile=profile, sequence=sequence, raise_error=raise_error
        )
        failed = data is None or profile is None

    if not failed:
        dst_folderpath = os.path.split(dst_filepath)[0]
        if dst_folderpath:
            os.makedirs(dst_folderpath, exist_ok=True)
        profile.update(count=data.shape[0])
        with rasterio.open(dst_filepath, "w", **profile) as dst:
            dst.write(data)
        delete_aux_xml(dst_filepath)

    return os.path.exists(dst_filepath) and not failed


def _modify_image_by_tuple(src_dst, sequence, raise_error):
    src_filepath, dst_filepath = src_dst
    return modify_image(
        src_filepath=src_filepath,
        dst_filepath=dst_filepath,
        sequence=sequence,
        raise_error=raise_error,
    )


def modify_images(
    src_filepaths: list[str],
    dst_filepaths: list[str],
    sequence: list,
    njobs: int = 1,
    raise_error: bool = True,
    print_messages: bool = True,
):
    """Apply an op sequence over many files (read -> ops -> write)."""
    if len(src_filepaths) != len(dst_filepaths):
        raise ValueError("Size of src_filepaths and dst_filepaths do not match.")
    func = functools.partial(
        _modify_image_by_tuple, sequence=sequence, raise_error=raise_error
    )
    return _pmap(func, zip(src_filepaths, dst_filepaths), njobs, print_messages)


def read_tif(filepath: str) -> tuple[np.ndarray, dict]:
    with rasterio.open(filepath) as src:
        return src.read(), src.meta.copy()


# --- helpers -----------------------------------------------------------------


def driver_specific_meta_updates(meta: dict, driver: str = None) -> dict:
    """Apply driver-specific profile fixes (compression / quality)."""
    if driver is None:
        driver = meta["driver"]
    if driver == "GTiff":
        meta.update({"driver": "GTiff", "compress": "lzw"})
    elif driver == "JP2OpenJPEG":
        # https://github.com/rasterio/rasterio/issues/1677#issuecomment-488597072
        meta.update({"driver": "JP2OpenJPEG", "QUALITY": "100", "REVERSIBLE": "YES"})
    return meta


def image_to_memfile(data: np.ndarray, profile: dict) -> rasterio.io.MemoryFile:
    memfile = rasterio.io.MemoryFile()
    with memfile.open(**profile) as dataset:
        dataset.write(data)
    return memfile


def images_to_memfiles(data_profile_list) -> list[rasterio.io.MemoryFile]:
    return [image_to_memfile(data=d, profile=p) for d, p in data_profile_list]


def delete_aux_xml(filepath: str) -> None:
    aux_xml_filepath = filepath + ".aux.xml"
    if os.path.exists(aux_xml_filepath):
        os.remove(aux_xml_filepath)


def modify_filepath(
    filepath: str,
    prefix: str = "",
    suffix: str = "",
    new_folderpath: str = None,
    new_ext: str = None,
    truncate_upto: int = None,
) -> str:
    """Derive a new path from ``filepath`` (prefix/suffix/folder/ext changes).

    ``truncate_upto`` caps the basename length — band-derived filenames can grow
    too long for the filesystem to create.
    """
    folderpath, filename = os.path.split(filepath)
    if new_folderpath is not None:
        folderpath = new_folderpath
    filename_splits = filename.split(".")
    filename = filename_splits[0]
    truncated_filename = filename[:truncate_upto]
    ext = ".".join(filename_splits[1:])
    if new_ext is not None:
        ext = new_ext
    return os.path.join(folderpath, f"{prefix}{truncated_filename}{suffix}.{ext}")


def get_random_alnum_str(length: int = 5) -> str:
    return "".join(
        random.choice(string.ascii_letters + string.digits) for _ in range(length)
    )


def get_epochs_str(add_random_alnum: bool = True, length: int = 5) -> str:
    random_alnum = get_random_alnum_str(length=length) if add_random_alnum else ""
    return f"{int(datetime.datetime.now().timestamp() * 1000000)}{random_alnum}"


def add_epochs_prefix(
    filepath: str,
    prefix: str = "",
    new_folderpath: str = None,
    add_random_alnum: bool = True,
    length: int = 5,
    truncate_upto: int = None,
) -> str:
    """Prefix a path with a (near-)unique epoch+random token, for temp staging."""
    epoch_str = get_epochs_str(add_random_alnum=add_random_alnum, length=length)
    return modify_filepath(
        filepath=filepath,
        prefix=f"{prefix}{epoch_str}_",
        new_folderpath=new_folderpath,
        truncate_upto=truncate_upto,
    )
