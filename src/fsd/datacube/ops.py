"""Datacube ops — pure transforms over (t, H, W, bands) + metadata.

Spec: specs/04-datacube-ops.md. Folds in the L2A-relevant subset of
core/datacube_ops.py. Each op: (datacube, metadata, **kwargs) -> (datacube, metadata),
so they compose via `run_ops`.

Dropped vs legacy: run_s2cloudless / CMK-based apply_cloud_mask (L1C-only) +
run_s2cloudless_core[_chunkwise] (s2cloudless dependency). See DROPPED.md.
"""

from __future__ import annotations

import copy
import datetime

import numba
import numpy as np
import pandas as pd


def run_ops(datacube, metadata, sequence):
    """Run a sequence of (func, kwargs) ops, threading (datacube, metadata)."""
    for func, kwargs in sequence:
        datacube, metadata = func(datacube=datacube, metadata=metadata, **kwargs)
    return datacube, metadata


def apply_cloud_mask_scl(datacube, metadata, *, mask_classes, bands_to_modify=None,
                         mask_value=0):
    """Set pixels to `mask_value` where SCL ∈ `mask_classes`, across the requested
    (non-SCL) bands. SCL itself is left untouched (drop it separately)."""
    band_indices = {band: i for i, band in enumerate(metadata["bands"])}
    if "SCL" not in band_indices:
        raise ValueError("SCL band not present in datacube")

    if bands_to_modify is None:
        bands_to_modify = [b for b in band_indices if b != "SCL"]
    present = [b for b in bands_to_modify if b in band_indices]
    idx_to_modify = [band_indices[b] for b in present]

    scl = datacube[:, :, :, band_indices["SCL"]]
    selected = datacube[:, :, :, idx_to_modify]
    selected[np.where(np.isin(scl, mask_classes))] = mask_value
    datacube[:, :, :, idx_to_modify] = selected
    return datacube, metadata


def drop_bands(datacube, metadata, *, bands_to_drop):
    """Slice out `bands_to_drop`; update `metadata['bands']`."""
    band_indices = {band: i for i, band in enumerate(metadata["bands"])}
    bands_to_keep = [b for b in band_indices if b not in bands_to_drop]
    idx_to_keep = [band_indices[b] for b in bands_to_keep]
    datacube = datacube[:, :, :, idx_to_keep]
    metadata["bands"] = bands_to_keep
    return datacube, metadata


def median_mosaic(datacube, metadata, *, startdate: datetime.datetime,
                  enddate: datetime.datetime, mosaic_days=20, mask_value=0):
    """Bucket timestamps into `mosaic_days` windows from `startdate`; per-bucket
    nanmedian (treating `mask_value` as NaN). Numba-accelerated core.

    Anchor caveat (legacy, TODO #2): the builder threads in the *actual first
    acquisition date*, not the user startdate, so windows shift ROI-to-ROI.
    """
    if mosaic_days < 1:
        return datacube, metadata

    ts_index_ranges = _get_mosaic_ts_index_ranges(
        timestamps=metadata["timestamps"], startdate=startdate, enddate=enddate,
        mosaic_days=mosaic_days,
    )

    dtype = datacube.dtype
    datacube = datacube.astype(float)
    datacube[np.where(datacube == mask_value)] = np.nan

    mosaiced = _median_mosaic_core(datacube, np.array(ts_index_ranges))

    mosaiced[np.isnan(mosaiced)] = mask_value
    mosaiced = mosaiced.astype(dtype)

    md = copy.deepcopy(metadata)
    md["mosaic_index_intervals"] = ts_index_ranges
    md["previous_timestamps"] = metadata["timestamps"]
    md["timestamps"] = [metadata["timestamps"][r[0]] for r in ts_index_ranges]
    md["data_shape_desc"] = ("timestamps", "height", "width", "bands")
    return mosaiced, md


def area_median(datacube, metadata=None, *, mask_value=0):
    """Collapse H×W to a single median pixel per timestamp (deploy helper)."""
    dtype = datacube.dtype
    _, height, width, _ = datacube.shape

    datacube = datacube.astype(float)
    datacube[np.where(datacube == mask_value)] = np.nan
    out = np.expand_dims(np.nanmedian(datacube, axis=(1, 2)), axis=(1, 2))
    out[np.isnan(out)] = mask_value
    out = out.astype(dtype)

    md = None
    if metadata is not None:
        md = copy.deepcopy(metadata)
        md["previous_height_width"] = (height, width)
    return out, md


# --- private helpers (faithful port; preserve legacy bucket behavior) ---------

def _dt2ts(dt: datetime.datetime, tz="UTC") -> pd.Timestamp:
    """Localize a naive datetime to a tz-aware pd.Timestamp (default UTC).

    The catalog stores tz-aware (UTC) acquisition timestamps, but user
    startdate/enddate arrive tz-naive. Comparison ops (== < > >=) raise when
    mixing tz-aware and tz-naive, so we attach UTC here. Attaching the tz is
    easier on a pd.Timestamp than on a datetime; hour/minute granularity is
    irrelevant since S2 revisit is ~5 days.
    """
    if dt.tzinfo is None:
        return pd.Timestamp(dt, tz=tz)
    return pd.Timestamp(dt)


def _is_sorted(seq) -> bool:
    return all(seq[i] <= seq[i + 1] for i in range(len(seq) - 1))


def _get_mosaic_ts_index_ranges(timestamps, startdate, enddate, mosaic_days=20):
    """Map sorted `timestamps` to (start_idx, end_idx) ranges over `mosaic_days`
    windows anchored at `startdate`. Faithful legacy port, including its quirk that a
    gap opens a new interval (advancing one bucket), so ranges track occupied buckets
    rather than every fixed window."""
    startdate = _dt2ts(startdate)
    enddate = _dt2ts(enddate)

    if not _is_sorted(timestamps):
        raise ValueError("timestamps is not sorted.")
    if startdate > timestamps[0]:
        raise ValueError("startdate must be before or on the first timestamp")
    if enddate < timestamps[-1]:
        raise ValueError("enddate must be after or on the last timestamp")

    mosaic_buckets = []
    cur_date = startdate
    while cur_date < enddate:
        next_date = cur_date + datetime.timedelta(days=mosaic_days)
        mosaic_buckets.append((cur_date, next_date))
        cur_date = next_date

    cur = 0
    ts_indexes = [[]]
    for index, ts in enumerate(timestamps):
        lte_date = mosaic_buckets[cur][1]
        if ts <= lte_date:
            ts_indexes[cur].append(index)
        else:
            ts_indexes.append([index])
            cur += 1

    return [(min(g), max(g)) for g in ts_indexes if len(g) > 0]


@numba.njit()
def _median_mosaic_core(datacube: np.ndarray, ts_index_ranges: np.ndarray):
    n_ts, height, width, n_bands = datacube.shape
    n_mosaiced = ts_index_ranges.shape[0]
    out = np.full((n_mosaiced, height, width, n_bands), np.nan)
    for t in numba.prange(n_mosaiced):
        for h in numba.prange(height):
            for w in numba.prange(width):
                for b in numba.prange(n_bands):
                    out[t, h, w, b] = np.nanmedian(
                        datacube[ts_index_ranges[t][0]: ts_index_ranges[t][1] + 1,
                                 h, w, b]
                    )
    return out
