"""Tests for fsd.datacube.ops (spec 04). Synthetic, deterministic."""

import datetime

import numpy as np
import pandas as pd
import pytest

from fsd.datacube import ops


def _ts(day):
    return pd.Timestamp(f"2018-01-{day:02d}", tz="UTC")


def test_apply_cloud_mask_scl_masks_only_flagged_pixels():
    # (t=1, H=1, W=2, bands=[B04, SCL]); pixel 0 has SCL=8 (cloud), pixel 1 SCL=4 (ok)
    dc = np.array([[[[100, 8], [200, 4]]]], dtype=np.int32)
    md = {"bands": ["B04", "SCL"]}
    out, _ = ops.apply_cloud_mask_scl(dc, md, mask_classes=[8, 9], mask_value=0)
    assert out[0, 0, 0, 0] == 0     # B04 zeroed where SCL==8
    assert out[0, 0, 1, 0] == 200   # B04 untouched where SCL==4
    assert out[0, 0, 0, 1] == 8 and out[0, 0, 1, 1] == 4  # SCL itself untouched


def test_drop_bands():
    dc = np.arange(2 * 1 * 1 * 3).reshape(2, 1, 1, 3)
    md = {"bands": ["B04", "B08", "SCL"]}
    out, md2 = ops.drop_bands(dc, md, bands_to_drop=["SCL"])
    assert md2["bands"] == ["B04", "B08"]
    assert out.shape == (2, 1, 1, 2)
    assert np.array_equal(out[..., 0], dc[..., 0])  # B04 preserved


def test_median_mosaic_buckets_and_mask():
    # 3 acquisitions: days 1, 6 (bucket 0: [01-01,01-21)) and 26 (bucket 1)
    ts = [_ts(1), _ts(6), _ts(26)]
    dc = np.array([10, 0, 30], dtype=np.int32).reshape(3, 1, 1, 1)  # day6 masked (0)
    md = {"bands": ["B04"], "timestamps": ts}
    out, md2 = ops.median_mosaic(
        dc, md, startdate=datetime.datetime(2018, 1, 1),
        enddate=datetime.datetime(2018, 2, 1), mosaic_days=20, mask_value=0,
    )
    assert out.shape == (2, 1, 1, 1)                 # 2 non-empty buckets
    assert out[0, 0, 0, 0] == 10                     # nanmedian(10, masked) = 10
    assert out[1, 0, 0, 0] == 30
    assert md2["timestamps"] == [ts[0], ts[2]]       # first ts of each bucket
    assert md2["mosaic_index_intervals"] == [(0, 1), (2, 2)]
    assert md2["previous_timestamps"] == ts


def test_median_mosaic_noop_when_days_lt_1():
    dc = np.ones((2, 1, 1, 1), dtype=np.int32)
    md = {"bands": ["B04"], "timestamps": [_ts(1), _ts(2)]}
    out, md2 = ops.median_mosaic(dc, md, startdate=datetime.datetime(2018, 1, 1),
                                 enddate=datetime.datetime(2018, 2, 1), mosaic_days=0)
    assert out is dc and md2 is md


def test_mosaic_ranges_validation():
    ts = [_ts(5), _ts(10)]
    with pytest.raises(ValueError, match="startdate must be"):
        ops._get_mosaic_ts_index_ranges(ts, datetime.datetime(2018, 1, 8),
                                        datetime.datetime(2018, 2, 1), 20)
    with pytest.raises(ValueError, match="not sorted"):
        ops._get_mosaic_ts_index_ranges([_ts(10), _ts(5)],
                                        datetime.datetime(2018, 1, 1),
                                        datetime.datetime(2018, 2, 1), 20)


def test_run_ops_threads_sequence():
    dc = np.array([[[[100, 8]]]], dtype=np.int32)  # (1,1,1,[B04,SCL]) SCL=8
    md = {"bands": ["B04", "SCL"]}
    out, md2 = ops.run_ops(dc, md, [
        (ops.apply_cloud_mask_scl, {"mask_classes": [8]}),
        (ops.drop_bands, {"bands_to_drop": ["SCL"]}),
    ])
    assert md2["bands"] == ["B04"]
    assert out.shape == (1, 1, 1, 1) and out[0, 0, 0, 0] == 0  # masked then SCL dropped


def test_area_median():
    # (t=1, H=2, W=2, b=1) values 10,20,30,0(masked) -> nanmedian(10,20,30)=20
    dc = np.array([10, 20, 30, 0], dtype=np.int32).reshape(1, 2, 2, 1)
    out, md = ops.area_median(dc, {"bands": ["B04"]}, mask_value=0)
    assert out.shape == (1, 1, 1, 1) and out[0, 0, 0, 0] == 20
    assert md["previous_height_width"] == (2, 2)
