"""Tests for the high-level API façade (specs/16).

Fast + synthetic: preflight, seam guards, stubs, and the orchestration wiring of
`create_training_data` (with the heavy build/flatten monkeypatched). The real end-to-end
against downloaded tiles is a manual runbook (tests/manual/flatten.md), not a unit test.
"""

from __future__ import annotations

import datetime

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
import shapely.geometry

import fsd
from fsd import api

JAN1 = datetime.datetime(2018, 1, 1)
JAN1_NEXT = datetime.datetime(2019, 1, 1)


def _polys(tmp_path, id_col="fid", label_col="crop", n=2):
    gdf = gpd.GeoDataFrame(
        {
            id_col: list(range(n)),
            label_col: ["a", "b"][:n],
            "geometry": [shapely.geometry.box(i, 0, i + 1, 1) for i in range(n)],
        },
        crs="EPSG:4326",
    )
    return gdf


def _touch(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("")
    return str(path)


# --- compute_n_timestamps ----------------------------------------------------

def test_compute_n_timestamps_calendar_identity():
    # full 2018, 20-day windows -> ceil(365/20) = 19 (matches the spec-15 benchmark).
    assert fsd.compute_n_timestamps(JAN1, JAN1_NEXT, 20) == 19
    # exact multiple: Jan 1 -> Feb 10 is 40 days, /10 = 4 windows.
    assert fsd.compute_n_timestamps(JAN1, datetime.datetime(2018, 2, 10), 10) == 4
    # one short window.
    assert fsd.compute_n_timestamps(JAN1, datetime.datetime(2018, 1, 6), 20) == 1


# --- preflight ---------------------------------------------------------------

def test_preflight_rejects_bad_window_and_makes_nothing(tmp_path):
    cat = _touch(tmp_path / "catalog.parquet")
    export = tmp_path / "export"
    with pytest.raises(api.PreflightError):
        fsd.create_training_data(
            label_polygons=_polys(tmp_path), catalog_filepath=cat,
            startdate=JAN1_NEXT, enddate=JAN1,  # reversed
            mosaic_days=0, bands=[],            # bad mosaic + empty bands
            id_col="fid", label_col="crop", export_folderpath=str(export),
        )
    assert not export.exists()  # failed before any work


def test_preflight_missing_catalog(tmp_path):
    with pytest.raises(api.PreflightError, match="catalog_filepath"):
        fsd.create_training_data(
            label_polygons=_polys(tmp_path),
            catalog_filepath=str(tmp_path / "nope.parquet"),
            startdate=JAN1, enddate=JAN1_NEXT, mosaic_days=20, bands=["B04"],
            id_col="fid", label_col="crop", export_folderpath=str(tmp_path / "e"),
        )


def test_preflight_missing_columns(tmp_path):
    cat = _touch(tmp_path / "catalog.parquet")
    with pytest.raises(api.PreflightError, match="not in label_polygons"):
        fsd.create_training_data(
            label_polygons=_polys(tmp_path), catalog_filepath=cat,
            startdate=JAN1, enddate=JAN1_NEXT, mosaic_days=20, bands=["B04"],
            id_col="MISSING", label_col="crop", export_folderpath=str(tmp_path / "e"),
        )


# --- seam guards -------------------------------------------------------------

@pytest.mark.parametrize("kwargs", [{"runner": "batch"}, {"storage": object()}])
def test_seam_guard_local_only(tmp_path, kwargs):
    cat = _touch(tmp_path / "catalog.parquet")
    with pytest.raises(api.PreflightError):
        fsd.create_training_data(
            label_polygons=_polys(tmp_path), catalog_filepath=cat,
            startdate=JAN1, enddate=JAN1_NEXT, mosaic_days=20, bands=["B04"],
            id_col="fid", label_col="crop", export_folderpath=str(tmp_path / "e"),
            **kwargs,
        )


# --- pinned-but-deferred params ----------------------------------------------

def test_feature_sequence_and_aggregate_not_implemented(tmp_path):
    cat = _touch(tmp_path / "catalog.parquet")
    base = dict(
        label_polygons=_polys(tmp_path), catalog_filepath=cat,
        startdate=JAN1, enddate=JAN1_NEXT, mosaic_days=20, bands=["B04"],
        id_col="fid", label_col="crop", export_folderpath=str(tmp_path / "e"),
    )
    with pytest.raises(NotImplementedError, match="feature_sequence"):
        fsd.create_training_data(**base, feature_sequence=[("x", {})])
    with pytest.raises(NotImplementedError, match="aggregate"):
        fsd.create_training_data(**base, aggregate="median_per_id")


# --- stubs -------------------------------------------------------------------

def test_run_inference_and_deploy_are_stubs():
    with pytest.raises(NotImplementedError, match="run_inference lands in P4"):
        fsd.run_inference("roi", JAN1, JAN1_NEXT, 20, model_bundle=None)
    with pytest.raises(NotImplementedError, match="deploy lands in P6"):
        fsd.deploy(model_bundle=None)


# --- orchestration wiring (build + flatten monkeypatched) --------------------

def test_create_training_data_orchestration(tmp_path, monkeypatch):
    cat = _touch(tmp_path / "catalog.parquet")
    export = tmp_path / "export"
    n_px, T, bands = 7, 19, ["B04", "B08"]

    def fake_run_create_datacube(*, csv_filepath, **kw):
        # the workflow would build datacubes + write input.csv; we just write the csv.
        pd.DataFrame(
            {"datacube_filepath": ["x/datacube.npy"], "id": [0], "label": ["a"]}
        ).to_csv(csv_filepath, index=False)

    def fake_flatten(*, export_folderpath, **kw):
        from fsd.storage import fs
        fs.makedirs(export_folderpath)
        fs.save_npy(f"{export_folderpath}/data.npy", np.zeros((n_px, T, len(bands))))
        fs.save_npy(f"{export_folderpath}/ids.npy", np.zeros(n_px))
        fs.save_npy(f"{export_folderpath}/coords.npy", np.zeros((n_px, 2)))
        fs.save_npy(f"{export_folderpath}/labels.npy", np.array(["a"] * n_px))
        fs.save_npy(
            f"{export_folderpath}/metadata.pickle.npy",
            {"timestamps": list(range(T)), "bands": bands}, allow_pickle=True,
        )

    monkeypatch.setattr(api._create_datacube, "run_create_datacube", fake_run_create_datacube)
    monkeypatch.setattr(api._flatten, "flatten", fake_flatten)

    td = fsd.create_training_data(
        label_polygons=_polys(tmp_path), catalog_filepath=cat,
        startdate=JAN1, enddate=JAN1_NEXT, mosaic_days=20, bands=bands,
        id_col="fid", label_col="crop", export_folderpath=str(export),
    )
    assert isinstance(td, fsd.TrainingData)
    assert td.n_pixels == n_px
    assert td.n_timestamps == T
    assert td.bands == bands

    loaded = td.load()
    assert loaded["data"].shape == (n_px, T, len(bands))
    assert set(loaded) == {"data", "ids", "coords", "metadata", "labels"}
