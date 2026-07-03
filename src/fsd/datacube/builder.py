"""Datacube builder — general seam + S2-L2A in-memory implementation.

Spec: specs/03-datacube.md. Folds in the working in-memory builder
(create_datacube_inmemory_single). `build_datacube` is the stable seam; an
alternate engine (e.g. rslearn) must emit the same datacube.npy + metadata.

Artifact contract (specs/00 §6):
  datacube.npy        : 4-D (timestamps|ids, height, width, bands)
  metadata.pickle.npy : {geotiff_metadata, timestamps, ids, bands,
                         data_shape_desc, geometry{shape, crs}, ...}
"""

from __future__ import annotations

import datetime
import json
import os
import time
import warnings
from contextlib import contextmanager

import geopandas as gpd
import numpy as np
import shapely
from rasterio.crs import CRS

from fsd import config
from fsd.datacube import ops
from fsd.raster import images
from fsd.storage import fs

_RASTER_EXTS = (".jp2", ".tif", ".tiff")
_VALID_IF_MISSING = ("raise_error", "warn", None)
TIMINGS_FILENAME = "timings.json"


@contextmanager
def _timed(store: dict, name: str):
    """Record wall-seconds for a build phase into `store` (benchmark seam, spec 11)."""
    t0 = time.perf_counter()
    yield
    store[name] = round(time.perf_counter() - t0, 4)


# --- caller helper: TileCatalog rows -> band-flattened rows -------------------

def flatten_catalog(catalog_gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Explode a filtered `TileCatalog` (one row per tile, with
    `area_contribution` from `TileCatalog.filter`) into one row per raster band
    file — the band-flattened form `build_datacube` consumes.

    Output cols: `id, filepath, band, timestamp, geometry, area_contribution`.
    Non-raster files (e.g. `MTD_TL.xml`) are skipped; `band` = filename minus ext.
    """
    data = {k: [] for k in
            ("id", "filepath", "band", "timestamp", "geometry", "area_contribution")}
    for _, row in catalog_gdf.iterrows():
        for file in str(row["files"]).split(","):
            band = next((file[:-len(e)] for e in _RASTER_EXTS if file.endswith(e)),
                        None)
            if band is None:
                continue
            data["id"].append(row["id"])
            data["filepath"].append(os.path.join(row["local_folderpath"], file))
            data["band"].append(band)
            data["timestamp"].append(row["timestamp"])
            data["geometry"].append(row["geometry"])
            data["area_contribution"].append(row["area_contribution"])
    return gpd.GeoDataFrame(data=data, crs=catalog_gdf.crs)


# --- the seam ----------------------------------------------------------------

def build_datacube(
    catalog_subset: gpd.GeoDataFrame,   # band-flattened tiles for this shape
    shape_gdf: gpd.GeoDataFrame,        # single geometry (+ id, optional label)
    startdate: datetime.datetime,
    enddate: datetime.datetime,
    bands: list[str],
    *,
    mosaic_days: int = config.MOSAIC_DAYS,
    scl_mask_classes: list[int] | None = None,
    reference_band: str = config.REFERENCE_BAND,
    export_folderpath: str,
    njobs: int = 1,
    njobs_load_images: int = 1,
    if_missing_files: str | None = "raise_error",   # raise_error | warn | None
    max_timedelta_days: int = config.MAX_TIMEDELTA_DAYS,
    write_timings: bool = False,
) -> None:
    """Assemble one cloud-masked, time-mosaicked datacube and save it.

    Steps (specs/03): missing-files check -> load+crop -> dst_crs (max mean area
    contribution) -> reference profile (merge B08) -> resample all to ref -> stack
    by timestamp x band -> SCL mask -> drop SCL -> median mosaic -> save.

    `startdate` must be on/before the first acquisition and `enddate` on/after the
    last (median_mosaic requirement); the workflow layer threads the actual first
    acquisition date in for `startdate` (anchor caveat, spec 04 / TODO #2).

    `write_timings=True` writes a `timings.json` sidecar (per-phase wall-seconds +
    counts) next to the artifact — the benchmark seam for spec 11. Off by default so
    normal builds leave no extra file; the workflow path enables it via the
    `FSD_WRITE_TIMINGS` env var (see workflows.task).
    """
    if scl_mask_classes is None:
        scl_mask_classes = config.SCL_MASK_CLASSES
    nodata = config.NODATA
    timings: dict[str, float] = {}
    t_all = time.perf_counter()

    with _timed(timings, "missing_check"):
        _missing_files_action(
            catalog_gdf=catalog_subset, shape_gdf=shape_gdf, startdate=startdate,
            enddate=enddate, bands=bands, if_missing_files=if_missing_files,
            max_timedelta_days=max_timedelta_days,
        )

    # Load + crop each (tile, band) to the shape; adds crs/image_index, drops
    # unreadable rows. Raster pixel reads use rasterio directly (documented seam
    # exception in CLAUDE.md). This is the read phase spec 11/12 scrutinise.
    with _timed(timings, "load_images"):
        catalog_gdf, data_profile_list = _load_images(
            catalog_gdf=catalog_subset, shape_gdf=shape_gdf, nodata=nodata,
            njobs=njobs_load_images,
        )

    # Collapse into a single UTM zone so rasterio.merge (single-CRS) can run.
    with _timed(timings, "dst_crs"):
        dst_crs = _get_dst_crs(catalog_gdf)

    # Reference grid = the merged reference-band (B08, 10 m) profile. Everything is
    # resampled TO this real known-10 m image, not to an abstract target grid.
    with _timed(timings, "reference_profile"):
        ref_indices = catalog_gdf.loc[catalog_gdf["band"] == reference_band, "image_index"]
        reference_profile = _get_merged_profile(
            indices=ref_indices, data_profile_list=data_profile_list, dst_crs=dst_crs,
            nodata=nodata, njobs=njobs,
        )

    with _timed(timings, "resample"):
        resample_indices = _get_indices_to_resample(
            indices=catalog_gdf["image_index"], data_profile_list=data_profile_list,
            reference_profile=reference_profile,
        )
        _resample_by_indices(
            indices=resample_indices, data_profile_list=data_profile_list,
            reference_profile=reference_profile, njobs=njobs,
        )

    with _timed(timings, "stack"):
        datacube, metadata = _stack_datacube(
            catalog_gdf=catalog_gdf, data_profile_list=data_profile_list, bands=bands,
            reference_profile=reference_profile, shape_gdf=shape_gdf, nodata=nodata,
        )

    with _timed(timings, "ops"):
        datacube, metadata = ops.run_ops(datacube, metadata, sequence=[
            (ops.apply_cloud_mask_scl, dict(mask_classes=scl_mask_classes)),
            (ops.drop_bands, dict(bands_to_drop=["SCL"])),
            (ops.median_mosaic, dict(startdate=startdate, enddate=enddate,
                                     mosaic_days=mosaic_days)),
        ])

    with _timed(timings, "save"):
        fs.makedirs(export_folderpath)
        fs.save_npy(os.path.join(export_folderpath, "datacube.npy"), datacube)
        # Metadata is a dict (geometry, per-timestamp mapping, dim names) — things that
        # don't fit in the numpy array. It's pickled via np.save (allow_pickle) rather
        # than raw pickle because a raw pickle written on macOS could not be read on
        # Ubuntu (and vice versa) — np.save's pickling proved cross-platform stable.
        # (xarray is a possible future alternative; see TODO.)
        fs.save_npy(os.path.join(export_folderpath, "metadata.pickle.npy"),
                    metadata, allow_pickle=True)

    if write_timings:
        _write_timings_sidecar(
            export_folderpath, timings, round(time.perf_counter() - t_all, 4),
            shape_gdf=shape_gdf, catalog_subset=catalog_subset, catalog_gdf=catalog_gdf,
            n_resampled=len(resample_indices), datacube=datacube, metadata=metadata,
            dst_crs=dst_crs,
        )


def _write_timings_sidecar(export_folderpath, timings, total_seconds, *, shape_gdf,
                           catalog_subset, catalog_gdf, n_resampled, datacube, metadata,
                           dst_crs):
    """Dump per-phase timings + a few sizing counts as `timings.json` (spec 11)."""
    payload = {
        "id": (str(shape_gdf["id"].iloc[0]) if "id" in shape_gdf.columns else None),
        "total_seconds": total_seconds,
        "phase_seconds": timings,
        "n_band_rows": int(len(catalog_subset)),
        "n_images_loaded": int(len(catalog_gdf)),
        "n_images_resampled": int(n_resampled),
        "n_mosaic_timestamps": int(len(metadata["timestamps"])),
        "datacube_shape": list(datacube.shape),
        "dst_crs": str(dst_crs),
    }
    with fs.open(os.path.join(export_folderpath, TIMINGS_FILENAME), "w") as f:
        json.dump(payload, f, indent=2)


# --- missing-files check -----------------------------------------------------

def _query_stats(catalog_gdf: gpd.GeoDataFrame, shape_gdf: gpd.GeoDataFrame) -> dict:
    stats = {"tile_count": 0, "area_coverage": None, "timedelta_days": None,
             "timestamp_range": None, "band_counts": {}}
    if catalog_gdf.shape[0] == 0:
        return stats

    shape_gdf = shape_gdf.to_crs(catalog_gdf.crs)
    target = shapely.unary_union(shape_gdf["geometry"])
    queried = shapely.unary_union(catalog_gdf["geometry"])
    stats["area_coverage"] = round(1 - (target - queried).area / target.area, 4)

    ts = np.array(sorted(catalog_gdf["timestamp"].tolist()))
    deltas = [td.round("D").days for td in (ts[1:] - ts[:-1])]
    stats["timedelta_days"] = dict(zip(*np.unique(deltas, return_counts=True)))
    stats["timestamp_range"] = (ts.min(), ts.max())

    stats["band_counts"] = catalog_gdf["band"].value_counts().to_dict()
    stats["tile_count"] = max(stats["band_counts"].values())
    return stats


def _check_missing(shape_gdf, catalog_gdf, startdate, enddate, bands,
                   max_timedelta_days):
    stats = _query_stats(catalog_gdf=catalog_gdf, shape_gdf=shape_gdf)
    flags = {"all": False, "area": False, "time": False, "bands": False}
    msgs = []

    if stats["tile_count"] == 0:
        for k in flags:
            flags[k] = True
        return stats, flags, "No tiles found."

    if stats["area_coverage"] < 1:
        flags["area"] = True
        msgs.append(f"Incomplete area coverage: {stats['area_coverage'] * 100:.2f}%")

    gaps = [td for td in stats["timedelta_days"] if td > max_timedelta_days]
    if gaps:
        flags["time"] = True
        msgs.append("Unusual time gaps found (days): " + ", ".join(map(str, gaps)))

    first_gap = (stats["timestamp_range"][0] - ops._dt2ts(startdate)).days
    last_gap = (ops._dt2ts(enddate) - stats["timestamp_range"][1]).days
    if first_gap > max_timedelta_days:
        flags["time"] = True
        msgs.append(f"First available image is {first_gap} days from startdate")
    if last_gap > max_timedelta_days:
        flags["time"] = True
        msgs.append(f"Last available image is {last_gap} days from enddate")

    completely = [b for b in bands if b not in stats["band_counts"]]
    partially = [b for b in bands if b in stats["band_counts"]
                 and stats["band_counts"][b] < stats["tile_count"]]
    if completely or partially:
        flags["bands"] = True
        if completely:
            msgs.append(f"Completely missing bands: {completely}")
        if partially:
            msgs.append(f"Partially missing bands: {partially}")

    return stats, flags, "; ".join(msgs)


def _missing_files_action(catalog_gdf, shape_gdf, startdate, enddate, bands,
                          if_missing_files="raise_error", max_timedelta_days=5):
    if not any(if_missing_files is x for x in _VALID_IF_MISSING):
        raise ValueError(
            f"Invalid if_missing_files={if_missing_files}. "
            f"Must be one of {_VALID_IF_MISSING}"
        )
    _, flags, msg = _check_missing(
        shape_gdf=shape_gdf, catalog_gdf=catalog_gdf, startdate=startdate,
        enddate=enddate, bands=bands, max_timedelta_days=max_timedelta_days,
    )
    if flags["all"]:
        raise ValueError("Missing files error -- " + msg)
    if any(flags.values()):
        if if_missing_files == "raise_error":
            raise ValueError("Missing files error -- " + msg)
        if if_missing_files == "warn":
            warnings.warn("Missing files warning\n" + msg, RuntimeWarning, stacklevel=2)


# --- load / dst_crs / reference / resample -----------------------------------

def _load_images(catalog_gdf, shape_gdf, nodata, njobs=1):
    """Crop every (tile, band) to the shape; return (kept rows, data_profile_list).
    Adds `image_index` (position in the list) and `crs` (str, for grouping); drops
    rows that failed to read. `image_index` still indexes the full list."""
    catalog_gdf = catalog_gdf.copy()
    data_profile_list = images.load_images(
        src_filepaths=catalog_gdf["filepath"].tolist(), shapes_gdf=shape_gdf,
        raise_error=False, nodata=nodata, all_touched=True, njobs=njobs,
        print_messages=False,
    )

    idx = [i if dp[0] is not None else -1 for i, dp in enumerate(data_profile_list)]
    if all(i == -1 for i in idx):
        raise ValueError("No valid images found.")

    catalog_gdf["image_index"] = idx
    catalog_gdf["crs"] = [str(p["crs"]) if p is not None else None
                          for _, p in data_profile_list]
    catalog_gdf = catalog_gdf[catalog_gdf["image_index"] != -1]
    return catalog_gdf, data_profile_list


def _get_dst_crs(catalog_gdf) -> CRS:
    """The CRS with the highest mean area contribution (single-zone collapse)."""
    means = catalog_gdf.groupby("crs")["area_contribution"].mean()
    return CRS.from_string(means.sort_values(ascending=False).index[0])


def _get_merged_profile(indices, data_profile_list, dst_crs, nodata=None, njobs=1):
    """Merge the reference-band images into one profile: reproject any off-CRS ones
    to `dst_crs` first, then rasterio.merge (needs a uniform CRS)."""
    selected = [data_profile_list[i] for i in indices]

    diff = [i for i, (_, p) in enumerate(selected) if p["crs"] != dst_crs]
    if diff:
        reproj = images.modify_images_inplace(
            data_profile_list=[selected[i] for i in diff],
            sequence=[(images.reproject, dict(dst_crs=dst_crs))],
            njobs=njobs, print_messages=False,
        )
        for i, dp in zip(diff, reproj):
            selected[i] = dp

    _, merged_profile = images.merge_inplace(data_profile_list=selected, nodata=nodata)
    return merged_profile


def _get_indices_to_resample(indices, data_profile_list, reference_profile) -> list:
    out = []
    for i in indices:
        _, p = data_profile_list[i]
        if (p["crs"] != reference_profile["crs"]
                or p["height"] != reference_profile["height"]
                or p["width"] != reference_profile["width"]):
            out.append(i)
    return out


def _resample_by_indices(indices, data_profile_list, reference_profile, njobs=1):
    resampled = images.modify_images_inplace(
        data_profile_list=[data_profile_list[i] for i in indices],
        sequence=[(images.resample_by_ref_meta, dict(ref_meta=reference_profile))],
        njobs=njobs, print_messages=False,
    )
    for i, dp in zip(indices, resampled):
        data_profile_list[i] = dp
    return data_profile_list


# --- stack -------------------------------------------------------------------

def _stack_datacube(catalog_gdf, data_profile_list, bands, reference_profile,
                    shape_gdf, nodata):
    """Stack aligned images into (timestamps, H, W, bands). Every present band is
    (1, H, W) on the reference grid; a missing (ts, band) is nodata-filled to the
    same shape (legacy filled (H, W), which could not stack — fixed, see CHANGES)."""
    timestamps = sorted(catalog_gdf["timestamp"].unique().tolist())
    ts_band_index = dict(zip(zip(catalog_gdf["timestamp"], catalog_gdf["band"]),
                             catalog_gdf["image_index"]))
    ts_id = dict(zip(catalog_gdf["timestamp"], catalog_gdf["id"]))

    ref_h, ref_w = reference_profile["height"], reference_profile["width"]
    fill_dtype = data_profile_list[int(catalog_gdf["image_index"].iloc[0])][0].dtype
    missing = np.full((1, ref_h, ref_w), nodata, dtype=fill_dtype)

    datacube, ids = [], []
    for ts in timestamps:
        stack = [
            data_profile_list[ts_band_index[(ts, b)]][0]
            if (ts, b) in ts_band_index else missing
            for b in bands
        ]
        datacube.append(np.stack(stack, axis=-1))   # (1, H, W, bands)
        ids.append(ts_id[ts])
    datacube = np.concatenate(datacube, axis=0)      # (timestamps, H, W, bands)

    metadata = {
        "geotiff_metadata": reference_profile,
        "timestamps": timestamps,
        "ids": ids,
        "bands": list(bands),
        "data_shape_desc": ("timestamps|ids", "height", "width", "bands"),
        "geometry": {"shape": shape_gdf["geometry"].to_list(), "crs": shape_gdf.crs},
    }
    return datacube, metadata
