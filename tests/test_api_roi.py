"""Spec 21 — run_inference(roi=…) preflight guards + the three merge modes.

Preflight-guard tests fail *before* tiling, so they need neither the [grid] extra nor real
imagery. The merge tests build small synthetic single-band COGs in two UTM zones.
"""

import datetime

import geopandas as gpd
import numpy as np
import pytest
import rasterio
from rasterio.crs import CRS
from rasterio.transform import from_origin
from shapely.geometry import box

import fsd
from fsd.api import _merge_outputs
from fsd.model import BaseModelAdapter


class _Tiny(BaseModelAdapter):
    required_bands = ["B04", "B08"]
    n_timestamps = 2
    output_dtype = "uint8"
    output_nodata = 255
    output_band_names = ["c"]
    feature_sequence = []

    def load(self):
        pass

    def predict(self, X):
        return X[:, 0].astype("uint8")


ROI = gpd.GeoDataFrame({"geometry": [box(0, 0, 1, 1)]}, crs="EPSG:4326")


# --- entry-point guards (before any build) -----------------------------------

def test_roi_and_cubes_mutually_exclusive(tmp_path):
    with pytest.raises(fsd.PreflightError, match="not both"):
        fsd.run_inference(
            _Tiny(), inference_datacubes=["x"], output_folderpath=str(tmp_path),
            roi=ROI, catalog_filepath="c.parquet",
            startdate=datetime.datetime(2018, 6, 1), enddate=datetime.datetime(2018, 7, 11),
            mosaic_days=20, bands=["B04", "B08"],
        )


def test_neither_roi_nor_cubes(tmp_path):
    with pytest.raises(fsd.PreflightError, match="pass roi="):
        fsd.run_inference(_Tiny(), output_folderpath=str(tmp_path))


def test_output_folderpath_required():
    with pytest.raises(fsd.PreflightError, match="output_folderpath is required"):
        fsd.run_inference(_Tiny(), inference_datacubes=["x"])


def test_bad_merge_value(tmp_path):
    with pytest.raises(fsd.PreflightError, match="merge must be"):
        fsd.run_inference(_Tiny(), inference_datacubes=["x"],
                          output_folderpath=str(tmp_path), merge="bogus")


def test_roi_preflight_t_mismatch(tmp_path):
    # 2018-06-01..06-11 @ 20d -> T=1, but the model wants T=2 -> refuse before tiling
    with pytest.raises(fsd.PreflightError, match="needs T=2"):
        fsd.run_inference(
            _Tiny(), output_folderpath=str(tmp_path), roi=ROI, catalog_filepath="c.parquet",
            startdate=datetime.datetime(2018, 6, 1), enddate=datetime.datetime(2018, 6, 11),
            mosaic_days=20, bands=["B04", "B08"],
        )


def test_roi_preflight_missing_bands(tmp_path):
    with pytest.raises(fsd.PreflightError, match="missing model-required"):
        fsd.run_inference(
            _Tiny(), output_folderpath=str(tmp_path), roi=ROI, catalog_filepath="c.parquet",
            startdate=datetime.datetime(2018, 6, 1), enddate=datetime.datetime(2018, 7, 11),
            mosaic_days=20, bands=["B04"],                       # missing B08
        )


# --- merge modes -------------------------------------------------------------

def _write_cog(path, epsg, x0, y0, val, size=8, res=10, nodata=255):
    with rasterio.open(
        path, "w", driver="GTiff", height=size, width=size, count=1, dtype="uint8",
        crs=CRS.from_epsg(epsg), transform=from_origin(x0, y0, res, res), nodata=nodata,
    ) as d:
        d.write(np.full((1, size, size), val, dtype="uint8"))


def test_merge_strict_refuses_mixed_crs(tmp_path):
    a, b = tmp_path / "a.tif", tmp_path / "b.tif"
    _write_cog(a, 32636, 500000, 1300000, 1)
    _write_cog(b, 32637, 400000, 1300000, 2)
    with pytest.raises(fsd.PreflightError, match="multiple CRS"):
        _merge_outputs([str(a), str(b)], str(tmp_path / "m.tif"), nodata=255)


def test_merge_reproject_to_dominant_zone(tmp_path):
    # two cells in 32636 (dominant) + one in 32637 -> reproject merge into 32636
    a, b, c = tmp_path / "a.tif", tmp_path / "b.tif", tmp_path / "c.tif"
    _write_cog(a, 32636, 500000, 1300000, 1)
    _write_cog(b, 32636, 500080, 1300000, 1)
    _write_cog(c, 32637, 400000, 1300000, 2)
    dst = tmp_path / "merged.tif"
    out = _merge_outputs([str(a), str(b), str(c)], str(dst), nodata=255,
                         reproject_to_dominant=True)
    with rasterio.open(out) as s:
        assert s.crs.to_epsg() == 32636                        # dominant zone
        assert s.count == 1 and s.nodata == 255


def test_merge_reproject_area_dominant_beats_count(tmp_path):
    """spec 23 D7: the target is the max-total-AREA zone, not the most-cells zone."""
    a, b, c = tmp_path / "a.tif", tmp_path / "b.tif", tmp_path / "c.tif"
    _write_cog(a, 32636, 500000, 1300000, 1, size=4)          # two small cells (count favours 36)
    _write_cog(b, 32636, 500040, 1300000, 1, size=4)
    _write_cog(c, 32637, 400000, 1300000, 2, size=40)         # one big cell (area favours 37)
    out = _merge_outputs([str(a), str(b), str(c)], str(tmp_path / "m.tif"), nodata=255,
                         reproject_to_dominant=True)
    with rasterio.open(out) as s:
        assert s.crs.to_epsg() == 32637                        # area wins over cell count


def test_merge_reproject_merge_crs_override(tmp_path):
    """spec 23 D7: merge_crs forces the target CRS regardless of area/count."""
    a, b = tmp_path / "a.tif", tmp_path / "b.tif"
    _write_cog(a, 32636, 500000, 1300000, 1, size=4)
    _write_cog(b, 32637, 400000, 1300000, 2, size=40)         # bigger, would be area-dominant
    out = _merge_outputs([str(a), str(b)], str(tmp_path / "m.tif"), nodata=255,
                         reproject_to_dominant=True, merge_crs=32636)
    with rasterio.open(out) as s:
        assert s.crs.to_epsg() == 32636                        # forced target
