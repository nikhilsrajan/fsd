"""Fast + synthetic tests for `fsd.verify_adapter` (spec 48) — preflight, cell selection,
resume-identity, and the returned verdict shape, with the build/land/infer legs
monkeypatched. The real end-to-end (`runner="local"` against the tutorial fixture, AC10)
lives in `test_tutorial_fixture.py::test_verify_adapter_real_fixture_local_runner`.
"""

from __future__ import annotations

import datetime
import inspect
import os

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
import shapely.geometry

import fsd
from fsd import api
from fsd.model.adapter import BaseModelAdapter
from fsd.storage import fs
from fsd.workflows import create_datacube as _create_datacube
from fsd.workflows import infer_only_task as _infer_only_task

JAN1 = datetime.datetime(2018, 1, 1)
JAN60 = datetime.datetime(2018, 3, 2)  # 60 days later
BANDS = ["B04", "B08"]
T = 3


class _FakeAdapter(BaseModelAdapter):
    """Module-level (spec 44's bundle auto-detect needs a real importable class)."""

    required_bands = BANDS
    n_timestamps = 0  # model-determined -- no T preflight (mirrors the tutorial fixture)
    output_dtype = "uint8"
    output_nodata = 255
    output_band_names = ["output"]
    feature_sequence = None

    def features(self, data5d, band_indices):
        return data5d, band_indices

    def predict(self, X_chunk):
        return np.zeros(X_chunk.shape[0], dtype="uint8")


class _WrongTAdapter(_FakeAdapter):
    n_timestamps = T + 5  # the cube these tests build has T timestamps


ROI = gpd.GeoDataFrame({"geometry": [shapely.geometry.box(0, 0, 2, 1)]}, crs="EPSG:4326")

# Two disjoint grid cells covering the roi -- cell_a intersects more catalog tiles than
# cell_b, so the deterministic default (D3) must always pick cell_a.
_GRIDS = gpd.GeoDataFrame(
    {"id": ["cell_a", "cell_b"]},
    geometry=[shapely.geometry.box(0, 0, 1, 1), shapely.geometry.box(1, 0, 2, 1)],
    crs="EPSG:4326",
)


def _catalog(tmp_path, n_cell_a=3, n_cell_b=1):
    """Tiles whose geometry intersects cell_a more than cell_b -- no imagery, just enough
    for `_filter_gdf`'s date+overlap logic (geometry + timestamp)."""
    rows = []
    for i in range(n_cell_a):
        rows.append({"geometry": shapely.geometry.box(0, 0, 1, 1), "timestamp": JAN1})
    for i in range(n_cell_b):
        rows.append({"geometry": shapely.geometry.box(1, 0, 2, 1), "timestamp": JAN1})
    gdf = gpd.GeoDataFrame(rows, crs="EPSG:4326")
    gdf["timestamp"] = pd.to_datetime(gdf["timestamp"], utc=True)
    fp = str(tmp_path / "catalog.parquet")
    fs.write_parquet(fp, gdf)
    return fp


def _patch_grid(monkeypatch):
    import fsd.grid as grid_mod

    monkeypatch.setattr(grid_mod, "roi_to_s2_grids", lambda *a, **kw: _GRIDS.copy())


def _patch_build_and_infer(monkeypatch, *, output_dtype="uint8"):
    """Stand in for the real per-cell build (`create_datacube.run_create_datacube`) and the
    real inference leg (`infer_only_task.run_infer_only`) so these tests stay fast and
    network-free -- the wiring under test is preflight/selection/resume/report, not the
    (already-tested) build or inference units themselves."""
    calls = {"build": 0, "infer": 0}

    def fake_run_create_datacube(*, csv_filepath, **kw):
        calls["build"] += 1
        cube_dir = os.path.join(os.path.dirname(csv_filepath), "cellbuild")
        fs.makedirs(cube_dir)
        fs.save_npy(os.path.join(cube_dir, "datacube.npy"),
                    np.zeros((T, 2, 2, len(BANDS)), dtype="float32"))
        fs.save_npy(os.path.join(cube_dir, "metadata.pickle.npy"),
                    {"timestamps": list(range(T)), "bands": BANDS}, allow_pickle=True)
        pd.DataFrame(
            {"datacube_filepath": [os.path.join(cube_dir, "datacube.npy")]}
        ).to_csv(csv_filepath, index=False)

    def fake_run_infer_only(input_csv, rows, bundle_path, **kw):
        calls["infer"] += 1
        import rasterio
        from rasterio.transform import from_origin

        df = pd.read_csv(input_csv)
        out_fp = str(df["output_filepath"].iloc[0])
        os.makedirs(os.path.dirname(out_fp), exist_ok=True)
        profile = {
            "driver": "GTiff", "height": 2, "width": 2, "count": 1, "dtype": output_dtype,
            "crs": "EPSG:4326", "transform": from_origin(0, 1, 0.5, 0.5), "nodata": 255,
        }
        with rasterio.open(out_fp, "w", **profile) as dst:
            dst.write(np.zeros((1, 2, 2), dtype=output_dtype))
        return [out_fp]

    monkeypatch.setattr(_create_datacube, "run_create_datacube", fake_run_create_datacube)
    monkeypatch.setattr(_infer_only_task, "run_infer_only", fake_run_infer_only)
    return calls


# --- AC1/AC4/AC8/AC9/AC12/AC14: happy path + report shape --------------------

def test_verify_adapter_happy_path_report_shape(tmp_path, monkeypatch):
    _patch_grid(monkeypatch)
    calls = _patch_build_and_infer(monkeypatch)
    cat = _catalog(tmp_path)
    export = str(tmp_path / "export")

    result = fsd.verify_adapter(
        _FakeAdapter(), roi=ROI, catalog_filepath=cat,
        startdate=JAN1, enddate=JAN60, mosaic_days=20, bands=BANDS,
        export_folderpath=export, cell="cell_a",
    )

    assert calls["build"] == 1  # AC1: exactly one build
    assert calls["infer"] == 1
    assert result["step"] == "verify_adapter"
    assert result["pass"] is True
    assert result["status"] == "ok"
    for key in ("metrics", "expected", "error"):
        assert key in result
    for key in ("cube_shape", "cube_t", "adapter_n_timestamps", "post_feature_sequence_bands",
                "required_bands", "output_dtype", "output_value_min", "output_value_max",
                "output_nodata_fraction", "cube_filepath", "output_filepath", "grids_filepath"):
        assert key in result["metrics"], key

    # AC4: grids.geojson always written and its path printed/returned.
    assert os.path.exists(os.path.join(export, "grids.geojson"))
    assert result["metrics"]["grids_filepath"] == os.path.join(export, "grids.geojson")

    # AC14: no flattened/feature array.
    assert not os.path.exists(os.path.join(export, "features.npy"))
    assert not os.path.exists(os.path.join(export, "data.npy"))
    assert not os.path.exists(os.path.join(export, "ids.npy"))

    # D8: the cube + output land locally.
    assert os.path.exists(os.path.join(export, "datacube.npy"))
    assert os.path.exists(os.path.join(export, "metadata.pickle.npy"))
    assert os.path.exists(os.path.join(export, "output.tif"))


# --- AC2/AC5: deterministic cell selection + resume by identity --------------

def test_verify_adapter_deterministic_cell_and_resume_submits_no_job(tmp_path, monkeypatch, capsys):
    _patch_grid(monkeypatch)
    calls = _patch_build_and_infer(monkeypatch)
    cat = _catalog(tmp_path, n_cell_a=3, n_cell_b=1)
    export = str(tmp_path / "export")

    result1 = fsd.verify_adapter(
        _FakeAdapter(), roi=ROI, catalog_filepath=cat,
        startdate=JAN1, enddate=JAN60, mosaic_days=20, bands=BANDS, export_folderpath=export,
    )
    assert result1["metrics"]["cell"] == "cell_a"  # largest in-window coverage
    out = capsys.readouterr().out
    assert "cell='cell_a'" in out or 'cell_a' in out
    assert calls["build"] == 1

    # AC5: a second call, same roi/window/bands/mosaic_days -> no rebuild, straight to
    # inference (though inference itself always reruns, D-not-in-scope).
    result2 = fsd.verify_adapter(
        _FakeAdapter(), roi=ROI, catalog_filepath=cat,
        startdate=JAN1, enddate=JAN60, mosaic_days=20, bands=BANDS, export_folderpath=export,
    )
    assert result2["metrics"]["cell"] == "cell_a"
    assert calls["build"] == 1  # still 1 -- no second build job
    assert calls["infer"] == 2


def test_verify_adapter_changed_window_refuses_resume(tmp_path, monkeypatch):
    _patch_grid(monkeypatch)
    _patch_build_and_infer(monkeypatch)
    cat = _catalog(tmp_path)
    export = str(tmp_path / "export")

    fsd.verify_adapter(
        _FakeAdapter(), roi=ROI, catalog_filepath=cat,
        startdate=JAN1, enddate=JAN60, mosaic_days=20, bands=BANDS,
        export_folderpath=export, cell="cell_a",
    )
    with pytest.raises(api.PreflightError, match="DIFFERENT request"):
        fsd.verify_adapter(
            _FakeAdapter(), roi=ROI, catalog_filepath=cat,
            startdate=JAN1, enddate=datetime.datetime(2018, 4, 1), mosaic_days=20,
            bands=BANDS, export_folderpath=export, cell="cell_a",
        )


# --- AC3: explicit bad cell id ------------------------------------------------

def test_verify_adapter_unknown_cell_raises_with_available_ids(tmp_path, monkeypatch):
    _patch_grid(monkeypatch)
    _patch_build_and_infer(monkeypatch)
    cat = _catalog(tmp_path)
    export = str(tmp_path / "export")

    with pytest.raises(api.PreflightError, match="cell_a"):
        fsd.verify_adapter(
            _FakeAdapter(), roi=ROI, catalog_filepath=cat,
            startdate=JAN1, enddate=JAN60, mosaic_days=20, bands=BANDS,
            export_folderpath=export, cell="not-a-real-cell",
        )


# --- AC13: cell="random" prints + is pinnable ---------------------------------

def test_verify_adapter_random_cell_prints_and_pins(tmp_path, monkeypatch, capsys):
    _patch_grid(monkeypatch)
    _patch_build_and_infer(monkeypatch)
    cat = _catalog(tmp_path)
    export = str(tmp_path / "export")

    result = fsd.verify_adapter(
        _FakeAdapter(), roi=ROI, catalog_filepath=cat,
        startdate=JAN1, enddate=JAN60, mosaic_days=20, bands=BANDS,
        export_folderpath=export, cell="random",
    )
    chosen = result["metrics"]["cell"]
    assert chosen in ("cell_a", "cell_b")
    out = capsys.readouterr().out
    assert "random" in out and chosen in out

    # pinned: passing the printed id back as cell= reproduces the same cell.
    result2 = fsd.verify_adapter(
        _FakeAdapter(), roi=ROI, catalog_filepath=cat,
        startdate=JAN1, enddate=JAN60, mosaic_days=20, bands=BANDS,
        export_folderpath=str(tmp_path / "export2"), cell=chosen,
    )
    assert result2["metrics"]["cell"] == chosen


# --- AC9: a T mismatch is a verdict, not a raise ------------------------------

def test_verify_adapter_t_mismatch_is_pass_false_not_raised(tmp_path, monkeypatch):
    _patch_grid(monkeypatch)
    _patch_build_and_infer(monkeypatch)
    cat = _catalog(tmp_path)
    export = str(tmp_path / "export")

    result = fsd.verify_adapter(
        _WrongTAdapter(), roi=ROI, catalog_filepath=cat,
        startdate=JAN1, enddate=JAN60, mosaic_days=20, bands=BANDS,
        export_folderpath=export, cell="cell_a",
    )
    assert result["pass"] is False
    assert result["status"] == "fail"
    assert str(T) in result["error"] and str(T + 5) in result["error"]


# --- AC7: the bundle verify_adapter produces == the one run_inference would use ----

def test_verify_adapter_bundle_matches_ensure_bundle(tmp_path, monkeypatch):
    _patch_grid(monkeypatch)
    _patch_build_and_infer(monkeypatch)
    cat = _catalog(tmp_path)
    export = str(tmp_path / "export")

    fsd.verify_adapter(
        _FakeAdapter(), roi=ROI, catalog_filepath=cat,
        startdate=JAN1, enddate=JAN60, mosaic_days=20, bands=BANDS,
        export_folderpath=export, cell="cell_a",
    )
    from fsd.model import bundle as _bundle

    got = _bundle.read_spec(os.path.join(export, "_bundle"))
    want = _bundle.read_spec(
        api._ensure_bundle(_FakeAdapter(), str(tmp_path / "elsewhere"), why="test")
    )
    assert got["adapter"] == want["adapter"]
    assert got["required_bands"] == want["required_bands"] == BANDS


# --- AC6: no branch anywhere says "if verify_adapter" -------------------------

def test_no_verify_adapter_branch_in_shared_inference_code():
    from fsd.model import bundle as bundle_mod
    from fsd.model import engine as engine_mod

    for mod in (engine_mod, _infer_only_task, bundle_mod):
        src = inspect.getsource(mod)
        assert "verify_adapter" not in src


def test_export_folderpath_required(tmp_path, monkeypatch):
    _patch_grid(monkeypatch)
    _patch_build_and_infer(monkeypatch)
    cat = _catalog(tmp_path)
    with pytest.raises(api.PreflightError, match="export_folderpath"):
        fsd.verify_adapter(
            _FakeAdapter(), roi=ROI, catalog_filepath=cat,
            startdate=JAN1, enddate=JAN60, mosaic_days=20, bands=BANDS,
            export_folderpath="",
        )
