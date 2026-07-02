"""Tests for fsd.datacube.builder (spec 03). Synthetic GeoTIFF tiles on disk."""

import datetime

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
import rasterio
from rasterio.transform import from_origin
from shapely.geometry import box

from fsd.datacube import builder
from fsd.storage import fs

CRS = "EPSG:32633"
TRANSFORM = from_origin(500000, 5000000, 10, 10)  # 10 m pixels
TILE_BOX = box(500000, 4999960, 500040, 5000000)  # 4x4 @ 10 m


def _write_tile(path, arr):
    arr = arr[np.newaxis].astype(np.uint16)  # (1, H, W)
    with rasterio.open(path, "w", driver="GTiff", height=4, width=4, count=1,
                       dtype="uint16", crs=CRS, transform=TRANSFORM, nodata=0) as dst:
        dst.write(arr)


def _band_row(id_, path, band, ts):
    return {"id": id_, "filepath": str(path), "band": band, "timestamp": ts,
            "geometry": TILE_BOX, "area_contribution": 100.0}


def _make_catalog(tmp_path):
    """One tile, two timestamps, bands B04/B08/SCL. ts1 has a cloud (SCL=8) at (0,0)."""
    ts1 = pd.Timestamp("2018-06-01", tz="UTC")
    ts2 = pd.Timestamp("2018-07-01", tz="UTC")
    rows = []
    for ts, tag, b04v, b08v in [(ts1, "t1", 100, 200), (ts2, "t2", 110, 210)]:
        scl = np.full((4, 4), 4, dtype=np.uint16)  # 4 = vegetation (not masked)
        if tag == "t1":
            scl[0, 0] = 8  # cloud medium prob -> masked
        for band, val in [("B04", b04v), ("B08", b08v)]:
            p = tmp_path / f"{tag}_{band}.tif"
            _write_tile(p, np.full((4, 4), val, dtype=np.uint16))
            rows.append(_band_row(f"tile_{tag}", p, band, ts))
        p = tmp_path / f"{tag}_SCL.tif"
        _write_tile(p, scl)
        rows.append(_band_row(f"tile_{tag}", p, "SCL", ts))
    gdf = gpd.GeoDataFrame(rows, crs=CRS)
    shape = gpd.GeoDataFrame({"geometry": [TILE_BOX]}, crs=CRS)
    return gdf, shape


def test_build_datacube_end_to_end(tmp_path):
    catalog, shape = _make_catalog(tmp_path)
    out = tmp_path / "cube"
    builder.build_datacube(
        catalog_subset=catalog, shape_gdf=shape,
        startdate=datetime.datetime(2018, 5, 31), enddate=datetime.datetime(2018, 7, 2),
        bands=["B04", "B08", "SCL"], mosaic_days=20, scl_mask_classes=[8, 9],
        export_folderpath=str(out), if_missing_files=None,
    )

    dc = fs.load_npy(str(out / "datacube.npy"))
    md = fs.load_npy(str(out / "metadata.pickle.npy"), allow_pickle=True)[()]

    assert dc.shape == (2, 4, 4, 2)          # 2 mosaic buckets, SCL dropped
    assert md["bands"] == ["B04", "B08"]
    assert len(md["timestamps"]) == 2
    # ts1: cloud pixel (0,0) masked to 0; a clear pixel keeps its value
    assert dc[0, 0, 0, 0] == 0 and dc[0, 0, 0, 1] == 0
    assert dc[0, 1, 1, 0] == 100 and dc[0, 1, 1, 1] == 200
    # ts2: clear, values preserved
    assert dc[1, 0, 0, 0] == 110 and dc[1, 2, 2, 1] == 210
    assert md["geotiff_metadata"]["height"] == 4


def test_flatten_catalog_skips_non_raster(tmp_path):
    gdf = gpd.GeoDataFrame(
        [{"id": "x", "local_folderpath": str(tmp_path), "timestamp": 0,
          "files": "B04.jp2,B08.jp2,MTD_TL.xml", "area_contribution": 50.0,
          "geometry": TILE_BOX}], crs=CRS,
    )
    flat = builder.flatten_catalog(gdf)
    assert sorted(flat["band"]) == ["B04", "B08"]      # xml skipped
    assert flat["filepath"].iloc[0].endswith("B04.jp2")


def test_get_dst_crs_picks_max_mean_area():
    gdf = gpd.GeoDataFrame({
        "crs": ["EPSG:32636", "EPSG:32636", "EPSG:32637"],
        "area_contribution": [10.0, 10.0, 80.0],
        "geometry": [TILE_BOX] * 3,
    }, crs=CRS)
    # 32637 has the higher *mean* (80 vs 10) despite fewer tiles
    assert builder._get_dst_crs(gdf).to_epsg() == 32637


def test_missing_files_raises_on_incomplete_area():
    tile = gpd.GeoDataFrame(
        [{"band": "B04", "timestamp": pd.Timestamp("2018-06-01", tz="UTC"),
          "geometry": box(0, 0, 1, 1)}], crs="EPSG:32633",
    )
    shape = gpd.GeoDataFrame({"geometry": [box(0, 0, 4, 4)]}, crs="EPSG:32633")
    with pytest.raises(ValueError, match="area coverage"):
        builder._missing_files_action(
            catalog_gdf=tile, shape_gdf=shape,
            startdate=datetime.datetime(2018, 5, 30),
            enddate=datetime.datetime(2018, 6, 2), bands=["B04"],
            if_missing_files="raise_error",
        )
