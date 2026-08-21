"""Spec 50 — resolve `create_training_data` backwards from the target.

Step 0 (D6/#83): the deterministic run folder. Step 1 (D3): request-derived flatten
identity. Step 2 (phase 1): the top-level short-circuit. Step 4 (phase 2): the full
backward walk. Step 3 (D9) is blocked on #84 and is NOT implemented here.
"""

from __future__ import annotations

import datetime
import os

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import box

from fsd import api, config
from fsd.storage import fs
from fsd.workflows import create_datacube


def _make_catalog(cat_path, tmp_path):
    rows = []
    for i, mgrs in enumerate(["T33UVP", "T33UVP"]):
        tif = tmp_path / f"tile_{i}.tif"
        tif.write_bytes(b"\x00")
        rows.append({
            "mgrs_tile": mgrs, "timestamp": pd.Timestamp("2018-04-01", tz="UTC"),
            "band": "B04", "filepath": str(tif),
            "geometry": box(0, 0, 10, 10),
        })
    gdf = gpd.GeoDataFrame(rows, crs="EPSG:4326")
    gdf["area_contribution"] = 1.0
    fs.write_parquet(str(cat_path), gdf)


def _two_shapes(path):
    gdf = gpd.GeoDataFrame(
        {"id": [0, 1], "label": ["a", "b"],
         "geometry": [box(1, 1, 2, 2), box(3, 3, 4, 4)]},
        crs="EPSG:4326",
    )
    gdf.to_file(path, driver="GeoJSON")


# --- AC7b: two requests differing only in `bands` resolve to different cube paths -----

def test_params_key_differs_when_bands_differ():
    a = create_datacube.params_key(["B04"], config.MOSAIC_SCHEME, [8, 9])
    b = create_datacube.params_key(["B04", "B08"], config.MOSAIC_SCHEME, [8, 9])
    assert a != b


def test_params_key_stable_for_same_params():
    a = create_datacube.params_key(["B04", "B08"], config.MOSAIC_SCHEME, [8, 9])
    b = create_datacube.params_key(["B04", "B08"], config.MOSAIC_SCHEME, [8, 9])
    assert a == b


def test_setup_with_different_bands_writes_to_different_window_folders(tmp_path):
    cat = tmp_path / "catalog.parquet"
    shapes = tmp_path / "shapes.geojson"
    _make_catalog(cat, tmp_path)
    _two_shapes(shapes)
    run_folder = tmp_path / "run"

    csv_a = tmp_path / "a.csv"
    create_datacube.setup(
        catalog_filepath=str(cat), timestamp_col="timestamp",
        shapefilepath=str(shapes), id_col="id", run_folderpath=str(run_folder),
        startdate=datetime.datetime(2018, 1, 1), enddate=datetime.datetime(2019, 1, 1),
        bands=["B04"], scl_mask_classes=[8, 9], mosaic_days=20,
        csv_filepath=str(csv_a), label_col="label",
    )
    csv_b = tmp_path / "b.csv"
    create_datacube.setup(
        catalog_filepath=str(cat), timestamp_col="timestamp",
        shapefilepath=str(shapes), id_col="id", run_folderpath=str(run_folder),
        startdate=datetime.datetime(2018, 1, 1), enddate=datetime.datetime(2019, 1, 1),
        bands=["B04", "B08"], scl_mask_classes=[8, 9], mosaic_days=20,
        csv_filepath=str(csv_b), label_col="label",
    )

    paths_a = set(pd.read_csv(csv_a)["export_folderpath"])
    paths_b = set(pd.read_csv(csv_b)["export_folderpath"])
    assert paths_a.isdisjoint(paths_b), (
        "two requests differing only in bands must resolve to different cube paths (D6)"
    )
