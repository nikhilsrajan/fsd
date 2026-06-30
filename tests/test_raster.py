"""Tests for fsd.raster.images (spec 07).

Synthetic in-memory rasters (no real .jp2 files) exercise the (data, profile)
ops, the sequence runners, the file-based round-trip, and the path helpers.
"""

import geopandas as gpd
import numpy as np
import pytest
import rasterio
import rasterio.crs
import rasterio.transform
import shapely.geometry as sg

from fsd.raster import images

UTM = rasterio.crs.CRS.from_epsg(32643)  # metres, so area/extent math is sane


def _synthetic(width=10, height=10, west=0.0, north=100.0, res=10.0, fill=None):
    """A single-band uint16 raster at `res` m/px, top-left at (west, north)."""
    profile = {
        "driver": "GTiff",
        "dtype": "uint16",
        "nodata": 0,
        "width": width,
        "height": height,
        "count": 1,
        "crs": UTM,
        "transform": rasterio.transform.from_origin(west, north, res, res),
    }
    if fill is None:
        data = (np.arange(width * height).reshape(1, height, width) + 1).astype(
            "uint16"
        )
    else:
        data = np.full((1, height, width), fill, dtype="uint16")
    return data, profile


# --- in-memory ops -----------------------------------------------------------


def test_crop_reduces_extent_and_keeps_crs():
    data, profile = _synthetic()
    roi = gpd.GeoDataFrame(geometry=[sg.box(20, 20, 50, 50)], crs=UTM)
    out_data, out_profile = images.crop(data, profile, roi, all_touched=True)
    assert out_profile["height"] < profile["height"]
    assert out_profile["width"] < profile["width"]
    assert out_data.shape == (1, out_profile["height"], out_profile["width"])
    assert out_profile["crs"] == UTM


def test_reproject_changes_crs():
    data, profile = _synthetic()
    out_data, out_profile = images.reproject(data, profile, dst_crs="EPSG:4326")
    assert out_profile["crs"] == rasterio.crs.CRS.from_epsg(4326)
    assert out_data.shape[0] == 1


def test_reproject_same_crs_is_noop():
    data, profile = _synthetic()
    out_data, out_profile = images.reproject(data, profile, dst_crs=profile["crs"])
    assert out_data is data
    assert out_profile is profile


def test_resample_by_ref_meta_matches_ref_grid():
    data, profile = _synthetic(width=10, height=10, res=10.0)
    # Coarser reference covering the same extent: 5x5 @ 20 m.
    _, ref_meta = _synthetic(width=5, height=5, res=20.0)
    out_data, out_profile = images.resample_by_ref_meta(data, profile, ref_meta)
    assert out_profile["height"] == 5
    assert out_profile["width"] == 5
    assert out_data.shape == (1, 5, 5)
    # source nodata/dtype are preserved
    assert out_profile["nodata"] == profile["nodata"]
    assert out_profile["dtype"] == profile["dtype"]


def test_merge_inplace_mosaics_adjacent_tiles():
    # Two 10x10 tiles side by side (east neighbour) -> 20 wide, 10 tall.
    left = _synthetic(width=10, height=10, west=0.0, north=100.0, fill=1)
    right = _synthetic(width=10, height=10, west=100.0, north=100.0, fill=2)
    merged_data, merged_profile = images.merge_inplace([left, right], nodata=0)
    assert merged_profile["width"] == 20
    assert merged_profile["height"] == 10
    assert merged_data.shape == (1, 10, 20)
    # left half came from `left` (1s), right half from `right` (2s)
    assert (merged_data[0, :, :10] == 1).all()
    assert (merged_data[0, :, 10:] == 2).all()


# --- sequence runners --------------------------------------------------------


def _add(data, profile, amount):
    return (data + amount).astype(data.dtype), profile


def _boom(data, profile):
    raise RuntimeError("op failed")


def test_modify_image_inplace_applies_sequence():
    data, profile = _synthetic(fill=5)
    out_data, out_profile = images.modify_image_inplace(
        data, profile, sequence=[(_add, dict(amount=3)), (_add, dict(amount=1))]
    )
    assert (out_data == 9).all()
    assert out_profile is profile


def test_modify_image_inplace_swallows_error_when_not_raising():
    data, profile = _synthetic(fill=5)
    out_data, out_profile = images.modify_image_inplace(
        data, profile, sequence=[(_boom, dict())], raise_error=False
    )
    assert out_data is None and out_profile is None


def test_modify_image_inplace_raises_by_default():
    data, profile = _synthetic(fill=5)
    with pytest.raises(RuntimeError):
        images.modify_image_inplace(data, profile, sequence=[(_boom, dict())])


def test_modify_images_inplace_serial():
    items = [_synthetic(fill=1), _synthetic(fill=2)]
    out = images.modify_images_inplace(
        items, sequence=[(_add, dict(amount=10))], njobs=1, print_messages=False
    )
    assert (out[0][0] == 11).all()
    assert (out[1][0] == 12).all()


# --- file-based round-trip ---------------------------------------------------


def _write_tif(path, data, profile):
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(data)


def test_load_image_roundtrip(tmp_path):
    data, profile = _synthetic(fill=7)
    p = str(tmp_path / "img.tif")
    _write_tif(p, data, profile)
    out_data, out_profile = images.load_image(p)
    assert np.array_equal(out_data, data)
    assert out_profile["crs"] == UTM


def test_load_image_error_returns_none_when_not_raising(tmp_path):
    out = images.load_image(str(tmp_path / "missing.tif"), raise_error=False)
    assert out == (None, None)


def test_load_images_serial(tmp_path):
    paths = []
    for i in range(2):
        data, profile = _synthetic(fill=i + 1)
        p = str(tmp_path / f"img{i}.tif")
        _write_tif(p, data, profile)
        paths.append(p)
    out = images.load_images(paths, njobs=1, print_messages=False)
    assert len(out) == 2
    assert (out[0][0] == 1).all()
    assert (out[1][0] == 2).all()


def test_modify_image_writes_destination(tmp_path):
    data, profile = _synthetic(fill=5)
    src = str(tmp_path / "src.tif")
    dst = str(tmp_path / "out/dst.tif")
    _write_tif(src, data, profile)
    ok = images.modify_image(src, dst, sequence=[(_add, dict(amount=2))])
    assert ok
    out_data, _ = images.read_tif(dst)
    assert (out_data == 7).all()


def test_modify_images_length_mismatch_raises():
    with pytest.raises(ValueError):
        images.modify_images(["a.tif", "b.tif"], ["x.tif"], sequence=[])


# --- helpers -----------------------------------------------------------------


def test_modify_filepath():
    assert (
        images.modify_filepath("/a/b/c.tif", prefix="x_", new_ext="jp2")
        == "/a/b/x_c.jp2"
    )


def test_get_epochs_str_unique():
    assert images.get_epochs_str() != images.get_epochs_str()


def test_driver_specific_meta_updates_gtiff():
    meta = images.driver_specific_meta_updates({"driver": "GTiff"})
    assert meta["compress"] == "lzw"


def test_add_epochs_prefix_changes_basename():
    out = images.add_epochs_prefix("/a/b/c.tif")
    assert out.startswith("/a/b/")
    assert out.endswith("c.tif")
    assert out != "/a/b/c.tif"
