"""Tests for tests/data/tutorial/derive_roi_and_labels.py (spec 42 step 0 /
run-book 43 Step 0) against a synthetic ROI + fields set -- the real
`shapefiles/AT_ROI.geojson`/`AT_2018_TRAIN.geojson` live outside this repo at
the workspace root, so this exercises the same selection/clip/collapse logic
on synthetic data instead.

The synthetic labels deliberately use **HCAT compound names**
(`grain_maize_corn_popcorn`, not `maize`), because assuming the short form is
the defect amendment A3 fixed: the original code hardcoded `{"maize", "hemp"}`
and collapsed all 43 real fields to `"other"`."""

import importlib.util
import json
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

MAIZE = "grain_maize_corn_popcorn"
HEMP = "hemp_cannabis"


def _make_at_roi(tmp_path):
    # A small square straddling multiple S2 res-11 cells (~5 km) so
    # roi_to_s2_grids returns more than one candidate id.
    roi = gpd.GeoDataFrame(
        {"name": ["AT_ROI"]}, geometry=[box(15.30, 48.40, 15.60, 48.60)], crs="EPSG:4326"
    )
    path = str(tmp_path / "AT_ROI.geojson")
    roi.to_file(path, driver="GeoJSON")
    return path


def _make_fields(tmp_path, cell_geom, crops=None, name="AT_2018_TRAIN.geojson"):
    """Fields inside `cell_geom` with DESCENDING areas, so the area-derived major
    ranking is deterministic: crops[0] biggest, crops[-1] smallest.

    Clustered tightly around the centroid and asserted `within` the cell: an S2
    cell clipped to an ROI is **not** a rectangle, so a field placed by bounds
    alone can straddle the cut corner, get clipped, and silently reorder the
    ranking this fixture exists to pin.
    """
    crops = crops or [MAIZE, HEMP, "alfalfa_lucerne", "mustard"]
    centroid = cell_geom.centroid
    radii = [0.0010, 0.00075, 0.0005, 0.0003]
    geoms = [
        Point(centroid.x + (i - (len(crops) - 1) / 2) * 0.0025, centroid.y)
        .buffer(radii[i % len(radii)])
        for i in range(len(crops))
    ]
    for crop, geom in zip(crops, geoms):
        assert geom.within(cell_geom), f"synthetic field {crop!r} falls outside the cell"
    fields = gpd.GeoDataFrame(
        {"fid": list(range(1, len(crops) + 1)), "crop": crops},
        geometry=geoms, crs="EPSG:4326",
    )
    path = str(tmp_path / name)
    fields.to_file(path, driver="GeoJSON")
    return path


# --- the collapse -----------------------------------------------------------


def test_collapse_label_keeps_majors_and_collapses_the_rest():
    majors = [MAIZE, HEMP]
    assert derive_mod.collapse_label(MAIZE, majors) == MAIZE
    assert derive_mod.collapse_label(HEMP.upper(), majors) == HEMP.lower()
    assert derive_mod.collapse_label("alfalfa_lucerne", majors) == "other"
    assert derive_mod.collapse_label("mustard", majors) == "other"


def test_collapse_label_does_not_match_a_substring():
    """The A3 defect in miniature: "maize" must NOT match
    `grain_maize_corn_popcorn`. Fuzzy matching here would have hidden the bug
    instead of failing loudly at the Step 0 gate."""
    assert derive_mod.collapse_label(MAIZE, ["maize"]) == "other"


def test_pick_major_crops_ranks_by_area_not_field_count():
    """One big block outranks several small strips -- area is what the datacube's
    pixels actually are."""
    big = box(0.0, 0.0, 0.01, 0.01)
    smalls = [box(0.02 + i * 0.002, 0.0, 0.021 + i * 0.002, 0.001) for i in range(5)]
    gdf = gpd.GeoDataFrame(
        {"crop": ["big_crop"] + ["small_crop"] * 5 + ["tiny_crop"]},
        geometry=[big, *smalls, box(0.05, 0.0, 0.0501, 0.0001)],
        crs="EPSG:4326",
    )
    assert derive_mod.pick_major_crops(gdf, "crop", 1) == ["big_crop"]
    assert derive_mod.pick_major_crops(gdf, "crop", 2) == ["big_crop", "small_crop"]


def test_pick_major_crops_refuses_when_other_would_be_empty():
    gdf = gpd.GeoDataFrame(
        {"crop": [MAIZE, HEMP]},
        geometry=[box(0, 0, 0.01, 0.01), box(0.02, 0, 0.03, 0.01)],
        crs="EPSG:4326",
    )
    with pytest.raises(ValueError, match="would leave 'other' empty"):
        derive_mod.pick_major_crops(gdf, "crop", 2)


# --- derive -----------------------------------------------------------------


def test_derive_selects_cell_and_derives_majors(tmp_path):
    at_roi_path = _make_at_roi(tmp_path)
    grids = derive_mod.roi_to_s2_grids(at_roi_path, grid_size_km=5)
    assert len(grids) > 0
    target_id = grids["id"].iloc[0]
    fields_path = _make_fields(tmp_path, grids.geometry.iloc[0])

    cell, fields, majors = derive_mod.derive(at_roi_path, fields_path, target_id)
    assert len(cell) == 1
    assert str(cell["id"].iloc[0]) == str(target_id)
    assert set(fields.columns) >= {"fid", "crop", "label", "geometry"}
    assert majors == [MAIZE, HEMP]  # derived by area, largest first
    assert set(fields["label"]) == {MAIZE, HEMP, "other"}


def test_derive_honours_n_major(tmp_path):
    at_roi_path = _make_at_roi(tmp_path)
    grids = derive_mod.roi_to_s2_grids(at_roi_path, grid_size_km=5)
    target_id = grids["id"].iloc[0]
    fields_path = _make_fields(tmp_path, grids.geometry.iloc[0])

    _, fields, majors = derive_mod.derive(at_roi_path, fields_path, target_id, n_major=1)
    assert majors == [MAIZE]
    assert set(fields["label"]) == {MAIZE, "other"}


def test_derive_raises_on_unknown_cell_id(tmp_path):
    at_roi_path = _make_at_roi(tmp_path)
    grids = derive_mod.roi_to_s2_grids(at_roi_path, grid_size_km=5)
    fields_path = _make_fields(tmp_path, grids.geometry.iloc[0])

    with pytest.raises(ValueError, match="not found"):
        derive_mod.derive(at_roi_path, fields_path, "not-a-real-cell-id")


def test_derive_raises_on_missing_label_column_and_names_the_alternatives(tmp_path):
    """The A3 root cause: the code required `EC_hcat_n`, a column of a DIFFERENT
    workspace file. The error must name what the file actually has."""
    at_roi_path = _make_at_roi(tmp_path)
    grids = derive_mod.roi_to_s2_grids(at_roi_path, grid_size_km=5)
    target_id = grids["id"].iloc[0]
    fields_path = _make_fields(tmp_path, grids.geometry.iloc[0])

    with pytest.raises(ValueError, match="EC_hcat_n"):
        derive_mod.derive(at_roi_path, fields_path, target_id, label_col="EC_hcat_n")
    with pytest.raises(ValueError, match="'crop'"):
        derive_mod.derive(at_roi_path, fields_path, target_id, label_col="EC_hcat_n")


def test_derive_raises_on_missing_fid(tmp_path):
    at_roi_path = _make_at_roi(tmp_path)
    grids = derive_mod.roi_to_s2_grids(at_roi_path, grid_size_km=5)
    target_id = grids["id"].iloc[0]

    bad = gpd.GeoDataFrame(
        {"not_fid": [1], "crop": [MAIZE]},
        geometry=[grids.geometry.iloc[0].centroid.buffer(0.001)], crs="EPSG:4326",
    )
    bad_path = str(tmp_path / "bad_fields.geojson")
    bad.to_file(bad_path, driver="GeoJSON")

    with pytest.raises(ValueError, match="fid"):
        derive_mod.derive(at_roi_path, bad_path, target_id)


def test_derive_raises_when_the_cell_holds_no_field(tmp_path):
    """Most cells over an ROI hold none -- run-book 43 Step 0's documented trap
    (a wrong-but-existing cell id used to yield an empty, silently-passing set)."""
    at_roi_path = _make_at_roi(tmp_path)
    grids = derive_mod.roi_to_s2_grids(at_roi_path, grid_size_km=5)
    fields_path = _make_fields(tmp_path, grids.geometry.iloc[0])
    empty_cell = grids["id"].iloc[-1]

    with pytest.raises(ValueError, match="contains no field"):
        derive_mod.derive(at_roi_path, fields_path, empty_cell)


# --- the CLI / _result.json gate --------------------------------------------


def test_main_writes_roi_fields_and_a_computed_pass(tmp_path):
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

    with open(result_path) as f:
        result = json.load(f)
    assert result["pass"] is True
    assert result["metrics"]["cell_id"] == str(target_id)
    assert result["metrics"]["n_classes"] == 3
    assert result["metrics"]["label_col"] == "crop"
    assert result["metrics"]["major_crops"] == [MAIZE, HEMP]


def test_main_leaves_a_failed_result_when_the_collapse_cannot_yield_3_classes(tmp_path):
    """`_result.json`'s `pass` is what gets pasted back (spec 24), so a failure
    must still leave a pasteable FAIL rather than only a traceback."""
    at_roi_path = _make_at_roi(tmp_path)
    grids = derive_mod.roi_to_s2_grids(at_roi_path, grid_size_km=5)
    target_id = grids["id"].iloc[0]
    fields_path = _make_fields(
        tmp_path, grids.geometry.iloc[0], crops=[MAIZE, MAIZE, MAIZE, MAIZE]
    )

    result_path = str(tmp_path / "outputs" / "_result_step0.json")
    with pytest.raises(ValueError, match="would leave 'other' empty"):
        derive_mod.main([
            "--at-roi", at_roi_path, "--fields", fields_path,
            "--cell-id", str(target_id), "--out", str(tmp_path / "out"),
            "--result", result_path,
        ])
    with open(result_path) as f:
        result = json.load(f)
    assert result["pass"] is False
    assert result["status"] == "failed"


def test_main_n_major_1_gives_two_classes(tmp_path):
    at_roi_path = _make_at_roi(tmp_path)
    grids = derive_mod.roi_to_s2_grids(at_roi_path, grid_size_km=5)
    target_id = grids["id"].iloc[0]
    fields_path = _make_fields(tmp_path, grids.geometry.iloc[0])

    result_path = str(tmp_path / "outputs" / "_result_step0.json")
    rc = derive_mod.main([
        "--at-roi", at_roi_path, "--fields", fields_path,
        "--cell-id", str(target_id), "--n-major", "1",
        "--out", str(tmp_path / "out"), "--result", result_path,
    ])
    assert rc == 0
    with open(result_path) as f:
        result = json.load(f)
    assert result["metrics"]["n_classes"] == 2
    assert result["expected"]["n_classes"] == 2
