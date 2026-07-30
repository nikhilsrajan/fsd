"""Tests for tests/data/tutorial/derive_roi_and_labels.py (spec 42 step 0 /
run-book 43 Step 0) against a synthetic ROI + fields set -- the real
`shapefiles/AT_ROI.geojson`/`AT_2018_TRAIN.geojson` live outside this repo at
the workspace root, so this exercises the same selection/clip/collapse logic
on synthetic data instead."""

import importlib.util
import os
import sys

import geopandas as gpd
import pytest
from shapely.geometry import Point, box

_MODULE_PATH = os.path.join(
    os.path.dirname(__file__), "data", "tutorial", "derive_roi_and_labels.py"
)
_spec = importlib.util.spec_from_file_location("derive_roi_and_labels", _MODULE_PATH)
derive_mod = importlib.util.module_from_spec(_spec)
sys.modules["derive_roi_and_labels"] = derive_mod
_spec.loader.exec_module(derive_mod)


def _make_at_roi(tmp_path):
    # A small square straddling multiple S2 res-11 cells (~5 km) so
    # roi_to_s2_grids returns more than one candidate id.
    roi = gpd.GeoDataFrame(
        {"name": ["AT_ROI"]}, geometry=[box(15.30, 48.40, 15.60, 48.60)], crs="EPSG:4326"
    )
    path = str(tmp_path / "AT_ROI.geojson")
    roi.to_file(path, driver="GeoJSON")
    return path


def _make_fields(tmp_path, cell_geom):
    minx, miny, maxx, maxy = cell_geom.bounds
    cx, cy = (minx + maxx) / 2, (miny + maxy) / 2
    fields = gpd.GeoDataFrame(
        {
            "fid": [1, 2, 3, 4],
            "EC_hcat_n": ["maize", "hemp", "alfalfa", "mustard"],
        },
        geometry=[
            Point(cx - 0.001, cy).buffer(0.0005),
            Point(cx, cy).buffer(0.0005),
            Point(cx + 0.001, cy).buffer(0.0005),
            Point(cx, cy + 0.001).buffer(0.0005),
        ],
        crs="EPSG:4326",
    )
    path = str(tmp_path / "AT_2018_TRAIN.geojson")
    fields.to_file(path, driver="GeoJSON")
    return path


def test_collapse_label_keeps_maize_and_hemp_collapses_rest():
    assert derive_mod.collapse_label("maize") == "maize"
    assert derive_mod.collapse_label("Hemp") == "hemp"
    assert derive_mod.collapse_label("alfalfa") == "other"
    assert derive_mod.collapse_label("winter wheat") == "other"


def test_derive_selects_cell_and_collapses_fields(tmp_path):
    at_roi_path = _make_at_roi(tmp_path)
    grids = derive_mod.roi_to_s2_grids(at_roi_path, grid_size_km=5)
    assert len(grids) > 0
    target_id = grids["id"].iloc[0]
    fields_path = _make_fields(tmp_path, grids.geometry.iloc[0])

    cell, fields = derive_mod.derive(at_roi_path, fields_path, target_id)
    assert len(cell) == 1
    assert str(cell["id"].iloc[0]) == str(target_id)
    assert set(fields.columns) >= {"fid", "crop", "label", "geometry"}
    assert set(fields["label"]) <= {"maize", "hemp", "other"}
    assert len(fields) >= 1


def test_derive_raises_on_unknown_cell_id(tmp_path):
    at_roi_path = _make_at_roi(tmp_path)
    grids = derive_mod.roi_to_s2_grids(at_roi_path, grid_size_km=5)
    fields_path = _make_fields(tmp_path, grids.geometry.iloc[0])

    with pytest.raises(ValueError, match="not found"):
        derive_mod.derive(at_roi_path, fields_path, "not-a-real-cell-id")


def test_derive_raises_on_missing_required_columns(tmp_path):
    at_roi_path = _make_at_roi(tmp_path)
    grids = derive_mod.roi_to_s2_grids(at_roi_path, grid_size_km=5)
    target_id = grids["id"].iloc[0]

    bad_fields = gpd.GeoDataFrame(
        {"not_fid": [1]}, geometry=[grids.geometry.iloc[0].centroid], crs="EPSG:4326"
    )
    bad_path = str(tmp_path / "bad_fields.geojson")
    bad_fields.to_file(bad_path, driver="GeoJSON")

    with pytest.raises(ValueError, match="fid"):
        derive_mod.derive(at_roi_path, bad_path, target_id)


def test_main_writes_roi_and_fields_and_result(tmp_path):
    at_roi_path = _make_at_roi(tmp_path)
    grids = derive_mod.roi_to_s2_grids(at_roi_path, grid_size_km=5)
    target_id = grids["id"].iloc[0]
    fields_path = _make_fields(tmp_path, grids.geometry.iloc[0])

    out_dir = str(tmp_path / "out")
    result_path = str(tmp_path / "outputs" / "_result_step0.json")

    rc = derive_mod.main([
        "--at-roi", at_roi_path, "--fields", fields_path,
        "--cell-id", str(target_id), "--out", out_dir, "--result", result_path,
    ])
    assert rc == 0
    assert os.path.exists(os.path.join(out_dir, "roi.geojson"))
    assert os.path.exists(os.path.join(out_dir, "fields.geojson"))

    import json
    with open(result_path) as f:
        result = json.load(f)
    assert result["pass"] is True
    assert result["metrics"]["cell_id"] == str(target_id)
    assert result["metrics"]["fields"] >= 1
    assert result["metrics"]["n_classes"] == derive_mod.EXPECTED_N_CLASSES


def test_main_fails_when_the_collapse_yields_one_class(tmp_path):
    """`_result.json`'s `pass` is what gets pasted back (spec 24), so it must be
    computed, not hardcoded. If `EC_hcat_n`'s real values are not literally
    "maize"/"hemp", every field collapses to "other" -- one class, untrainable,
    and run-book 43 Step 0 must read FAIL rather than PASS."""
    at_roi_path = _make_at_roi(tmp_path)
    grids = derive_mod.roi_to_s2_grids(at_roi_path, grid_size_km=5)
    target_id = grids["id"].iloc[0]
    cell_geom = grids.geometry.iloc[0]
    cx, cy = cell_geom.centroid.x, cell_geom.centroid.y
    fields = gpd.GeoDataFrame(
        {"fid": [1, 2], "EC_hcat_n": ["common_maize", "industrial_hemp"]},
        geometry=[Point(cx, cy).buffer(0.0005), Point(cx + 0.001, cy).buffer(0.0005)],
        crs="EPSG:4326",
    )
    fields_path = str(tmp_path / "AT_2018_TRAIN.geojson")
    fields.to_file(fields_path, driver="GeoJSON")

    result_path = str(tmp_path / "outputs" / "_result_step0.json")
    rc = derive_mod.main([
        "--at-roi", at_roi_path, "--fields", fields_path,
        "--cell-id", str(target_id), "--out", str(tmp_path / "out"),
        "--result", result_path,
    ])
    assert rc == 1

    import json
    with open(result_path) as f:
        result = json.load(f)
    assert result["pass"] is False
    assert result["status"] == "failed"
    assert result["metrics"]["n_classes"] == 1
