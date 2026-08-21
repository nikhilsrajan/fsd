"""Spec 50 — resolve `create_training_data` backwards from the target.

Step 0 (D6/#83): the deterministic run folder. Step 1 (D3): request-derived flatten
identity. Step 2 (phase 1): the top-level short-circuit. Step 4 (phase 2): the full
backward walk. Step 3 (D9) is blocked on #84 and is NOT implemented here.
"""

from __future__ import annotations

import datetime
import os

import geopandas as gpd
import numpy as np
import pandas as pd
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


def _shapes(path, ids, *, outside_ids=()):
    """`ids` inside the `_make_catalog` bbox (`box(0, 0, 10, 10)`), except any in
    `outside_ids` -- placed far away so they have no intersecting tile (D5's known-empty
    case)."""
    geoms = []
    for i in ids:
        if i in outside_ids:
            geoms.append(box(1000 + i, 1000, 1001 + i, 1001))
        else:
            geoms.append(box(i + 1, i + 1, i + 2, i + 2))
    gpd.GeoDataFrame(
        {"id": list(ids), "label": [f"l{i}" for i in ids], "geometry": geoms}, crs="EPSG:4326",
    ).to_file(path, driver="GeoJSON")


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


# --- Step 1 / D3: the flatten identity is computable from the REQUEST -----------------

def test_request_identity_matches_the_input_csv_identity(tmp_path):
    """D3's load-bearing claim: `_flatten_identity_from_request` (reads nothing) must
    compute the SAME identity `_flatten_identity` computes from a real `input.csv` --
    otherwise a walk that trusts the request-derived one would (mis)match a stamp the
    old, csv-derived one would not."""
    cat = tmp_path / "catalog.parquet"
    shapes = tmp_path / "shapes.geojson"
    _make_catalog(cat, tmp_path)
    _two_shapes(shapes)
    run_folder = tmp_path / "run"
    csv = tmp_path / "input.csv"

    kwargs = dict(
        startdate=datetime.datetime(2018, 1, 1), enddate=datetime.datetime(2019, 1, 1),
        mosaic_days=20, bands=["B04", "B08"], scl_mask_classes=[8, 9],
    )
    create_datacube.setup(
        catalog_filepath=str(cat), timestamp_col="timestamp",
        shapefilepath=str(shapes), id_col="id", run_folderpath=str(run_folder),
        csv_filepath=str(csv), label_col="label", **kwargs,
    )
    input_df = pd.read_csv(csv)

    from_csv = api._flatten_identity(
        input_df, id_col="id", filepath_col="datacube_filepath",
        adapter=None, feature_sequence=None, aggregate=None,
    )

    gdf = gpd.read_file(shapes)
    from_request = api._flatten_identity_from_request(
        gdf, id_col="id", run_folderpath=str(run_folder),
        mosaic_scheme=config.MOSAIC_SCHEME,
        adapter=None, feature_sequence=None, aggregate=None, **kwargs,
    )

    assert from_request == from_csv


def test_request_identity_reads_no_input_csv(tmp_path):
    """AC4: computed with no `input.csv` on disk at all -- proof the identity no longer
    needs `setup` to have run."""
    assert not (tmp_path / "input.csv").exists()
    gdf = gpd.GeoDataFrame(
        {"id": [0, 1], "geometry": [box(1, 1, 2, 2), box(3, 3, 4, 4)]}, crs="EPSG:4326",
    )
    identity = api._flatten_identity_from_request(
        gdf, id_col="id", run_folderpath=str(tmp_path / "run"),
        startdate=datetime.datetime(2018, 1, 1), enddate=datetime.datetime(2019, 1, 1),
        mosaic_days=20, bands=["B04"], scl_mask_classes=[8, 9],
        mosaic_scheme=config.MOSAIC_SCHEME,
        adapter=None, feature_sequence=None, aggregate=None,
    )
    assert not (tmp_path / "input.csv").exists()
    assert len(identity["cubes"]) == 2


# --- Step 2 / phase 1: the top-level short-circuit ------------------------------------

def _fake_run_create_datacube(
    *, csv_filepath, run_folderpath, startdate, enddate, mosaic_days, bands,
    scl_mask_classes, mosaic_scheme=config.MOSAIC_SCHEME, **kw,
):
    """A `run_create_datacube` stand-in that writes an `input.csv` row whose
    `datacube_filepath` is the SAME path `create_datacube.cube_export_folderpath` (and
    therefore `_flatten_identity_from_request`) would derive -- otherwise the two
    identities would legitimately disagree and the short-circuit correctly would not
    fire. Real `setup` is not exercised here; only its output shape is."""
    window_segment = create_datacube.window_folder_segment(
        startdate, enddate, mosaic_days, bands=bands, mosaic_scheme=mosaic_scheme,
        scl_mask_classes=scl_mask_classes,
    )
    cube_folder = create_datacube.cube_export_folderpath(run_folderpath, window_segment, 0)
    fs.makedirs(os.path.dirname(csv_filepath))
    pd.DataFrame({
        "datacube_filepath": [os.path.join(cube_folder, "datacube.npy")],
        "id": [0], "label": ["a"], "bands": [",".join(bands)], "mosaic_days": [mosaic_days],
        "startdate": [str(pd.to_datetime(startdate, utc=True))],
        "enddate": [str(pd.to_datetime(enddate, utc=True))],
        "scl_mask_classes": [",".join(str(v) for v in scl_mask_classes)],
        "mosaic_scheme": [mosaic_scheme],
    }).to_csv(csv_filepath, index=False)


def _fake_flatten(*, export_folderpath, label_col=None, **kw):
    fs.makedirs(export_folderpath)
    fs.save_npy(os.path.join(export_folderpath, "data.npy"), np.zeros((1, 1, 1)))
    fs.save_npy(os.path.join(export_folderpath, "ids.npy"), np.array([0]))
    fs.save_npy(os.path.join(export_folderpath, "coords.npy"), np.zeros((1, 2)))
    fs.save_npy(os.path.join(export_folderpath, "metadata.pickle.npy"),
                {"timestamps": [0], "bands": ["B04"]}, allow_pickle=True)
    if label_col is not None:
        fs.save_npy(os.path.join(export_folderpath, "labels.npy"), np.array(["a"]))


def test_top_level_short_circuit_skips_setup_and_catalog(tmp_path, monkeypatch):
    """AC1/AC2: a fully-resumed `create_training_data` call performs no catalog read, no
    `setup` call, and no dispatch (D2) -- it lands the arrays and returns, off the
    request-derived identity alone, and the returned `TrainingData` matches the first
    run's."""
    cat = tmp_path / "catalog.parquet"
    cat.write_text("")  # exists for call #1's preflight; contents are never real parquet
    export = tmp_path / "export"

    monkeypatch.setattr(api._create_datacube, "run_create_datacube", _fake_run_create_datacube)
    monkeypatch.setattr(api._flatten, "flatten", _fake_flatten)

    gdf = gpd.GeoDataFrame(
        {"fid": [0], "crop": ["a"], "geometry": [box(0, 0, 1, 1)]}, crs="EPSG:4326",
    )
    kwargs = dict(
        label_polygons=gdf, catalog_filepath=str(cat),
        startdate=datetime.datetime(2018, 1, 1), enddate=datetime.datetime(2019, 1, 1),
        mosaic_days=20, bands=["B04"], id_col="fid", label_col="crop",
        export_folderpath=str(export),
    )
    td1 = api.create_training_data(**kwargs)

    # Prove call #2 needs neither `setup` nor the catalog: move the catalog file away,
    # and make `run_create_datacube` (the build leg, which is what would call `setup`)
    # and `TileCatalog.filter` (the D13 guardrail's catalog read) both raise if reached.
    cat.rename(tmp_path / "moved.parquet")

    def _raise_build(*a, **kw):
        raise AssertionError("run_create_datacube must not run when the target is CURRENT")

    def _raise_filter(*a, **kw):
        raise AssertionError("the catalog must not be read when the target is CURRENT")

    monkeypatch.setattr(api._create_datacube, "run_create_datacube", _raise_build)
    monkeypatch.setattr(api.TileCatalog, "filter", _raise_filter)

    td2 = api.create_training_data(**kwargs)

    assert td2.n_pixels == td1.n_pixels
    assert td2.n_timestamps == td1.n_timestamps
    assert td2.bands == td1.bands


def test_top_level_short_circuit_prints_plan_and_fetch(tmp_path, monkeypatch, capsys):
    """AC9/D7: the satisfied case prints `[plan] ... CURRENT` then `[fetch] ...`."""
    cat = tmp_path / "catalog.parquet"
    cat.write_text("")
    export = tmp_path / "export"

    monkeypatch.setattr(api._create_datacube, "run_create_datacube", _fake_run_create_datacube)
    monkeypatch.setattr(api._flatten, "flatten", _fake_flatten)

    gdf = gpd.GeoDataFrame(
        {"fid": [0], "crop": ["a"], "geometry": [box(0, 0, 1, 1)]}, crs="EPSG:4326",
    )
    kwargs = dict(
        label_polygons=gdf, catalog_filepath=str(cat),
        startdate=datetime.datetime(2018, 1, 1), enddate=datetime.datetime(2019, 1, 1),
        mosaic_days=20, bands=["B04"], id_col="fid", label_col="crop",
        export_folderpath=str(export),
    )
    api.create_training_data(**kwargs)
    capsys.readouterr()
    api.create_training_data(**kwargs)
    out = capsys.readouterr().out
    assert "[plan] target:" in out and "CURRENT" in out
    assert "[fetch] export ->" in out


# --- Step 4 / phase 2: the full backward walk (D2/D4/D5/D7) ---------------------------

def _walk_kwargs(cat, run_folder, csv_fp, **extra):
    kwargs = dict(
        catalog_filepath=str(cat), timestamp_col="timestamp", id_col="id",
        run_folderpath=str(run_folder),
        startdate=datetime.datetime(2018, 1, 1), enddate=datetime.datetime(2019, 1, 1),
        bands=["B04"], scl_mask_classes=[8, 9], mosaic_days=20,
        csv_filepath=csv_fp, label_col="label",
    )
    kwargs.update(extra)
    return kwargs


def _spy_on_setup(monkeypatch):
    """Records the ids `setup` was called with. Reads `shapefilepath` INSIDE the spy --
    `build_shortfall_only` writes it to a `tempfile.TemporaryDirectory()` that is gone by
    the time `setup` returns."""
    calls = []
    orig_setup = create_datacube.setup

    def spy(**kw):
        calls.append(sorted(gpd.read_file(kw["shapefilepath"])["id"]))
        return orig_setup(**kw)

    monkeypatch.setattr(create_datacube, "setup", spy)
    return calls


def test_build_shortfall_only_calls_setup_for_missing_ids_only(tmp_path, monkeypatch):
    """AC3: a partial run calls `setup` only for the missing ids -- scaled down from
    spec 50's own 900/40 example: 3 already have rows, 2 more are requested, `setup`
    receives exactly those 2 shapes."""
    cat = tmp_path / "catalog.parquet"
    _make_catalog(cat, tmp_path)
    run_folder = tmp_path / "run"
    csv_fp = str(run_folder / "input.csv")
    kwargs = _walk_kwargs(cat, run_folder, csv_fp)

    shapes3 = tmp_path / "shapes3.geojson"
    _shapes(shapes3, [0, 1, 2])
    create_datacube.build_shortfall_only(shapefilepath=str(shapes3), **kwargs)

    calls = _spy_on_setup(monkeypatch)
    shapes5 = tmp_path / "shapes5.geojson"
    _shapes(shapes5, [0, 1, 2, 3, 4])
    n_present, n_missing, n_known_empty = create_datacube.build_shortfall_only(
        shapefilepath=str(shapes5), **kwargs,
    )

    assert (n_present, n_missing, n_known_empty) == (3, 2, 0)
    assert calls == [[3, 4]]


def test_build_shortfall_only_no_setup_call_when_nothing_missing(tmp_path, monkeypatch):
    """AC5, in spirit: cube targets are enumerated with no catalog access -- `setup` (the
    only catalog reader in this module) is proven never called on a fully-satisfied
    request."""
    cat = tmp_path / "catalog.parquet"
    shapes = tmp_path / "shapes.geojson"
    _make_catalog(cat, tmp_path)
    _shapes(shapes, [0, 1])
    run_folder = tmp_path / "run"
    csv_fp = str(run_folder / "input.csv")
    kwargs = _walk_kwargs(cat, run_folder, csv_fp, shapefilepath=str(shapes))

    create_datacube.build_shortfall_only(**kwargs)  # first call builds the real rows

    def _raise(*a, **kw):
        raise AssertionError("setup (the only catalog reader here) must not run")

    monkeypatch.setattr(create_datacube, "setup", _raise)
    n_present, n_missing, n_known_empty = create_datacube.build_shortfall_only(**kwargs)
    assert n_missing == 0


def test_adding_one_polygon_rebuilds_exactly_one_cube(tmp_path, monkeypatch):
    """AC7a/D6 Q1: 3 shapes built, then a 4th requested -> the shortfall is 1 and `setup`
    receives exactly 1 shape. No set-level hash appears anywhere: the new id gets its own
    leaf, everything else is untouched."""
    cat = tmp_path / "catalog.parquet"
    _make_catalog(cat, tmp_path)
    run_folder = tmp_path / "run"
    csv_fp = str(run_folder / "input.csv")
    kwargs = _walk_kwargs(cat, run_folder, csv_fp)

    shapes3 = tmp_path / "shapes3.geojson"
    _shapes(shapes3, [0, 1, 2])
    create_datacube.build_shortfall_only(shapefilepath=str(shapes3), **kwargs)
    with fs.open(csv_fp, "r") as f:
        paths_before = set(pd.read_csv(f)["export_folderpath"])

    calls = _spy_on_setup(monkeypatch)
    shapes4 = tmp_path / "shapes4.geojson"
    _shapes(shapes4, [0, 1, 2, 3])
    n_present, n_missing, n_known_empty = create_datacube.build_shortfall_only(
        shapefilepath=str(shapes4), **kwargs,
    )

    assert n_missing == 1
    assert calls == [[3]]

    with fs.open(csv_fp, "r") as f:
        paths_after = set(pd.read_csv(f)["export_folderpath"])
    assert paths_before <= paths_after  # the 3 existing cube paths are untouched
    assert len(paths_after) == 4


def test_known_empty_recorded_once_and_shortfall_converges_to_zero(tmp_path):
    """AC6/D5: a cell with no in-window imagery is recorded once and reported as
    known-empty on the next run; two consecutive identical runs both report a shortfall
    of 0 -- the non-convergence case the manifest exists to prevent."""
    cat = tmp_path / "catalog.parquet"
    shapes = tmp_path / "shapes.geojson"
    _make_catalog(cat, tmp_path)
    _shapes(shapes, [0, 1], outside_ids=[1])  # id 1 has no intersecting tile
    run_folder = tmp_path / "run"
    csv_fp = str(run_folder / "input.csv")
    kwargs = _walk_kwargs(cat, run_folder, csv_fp, shapefilepath=str(shapes))

    n_present1, n_missing1, n_known_empty1 = create_datacube.build_shortfall_only(**kwargs)
    assert (n_present1, n_missing1, n_known_empty1) == (0, 2, 0)  # neither seen before

    n_present2, n_missing2, n_known_empty2 = create_datacube.build_shortfall_only(**kwargs)
    assert (n_present2, n_missing2, n_known_empty2) == (1, 0, 1)  # id 1 now known-empty

    n_present3, n_missing3, n_known_empty3 = create_datacube.build_shortfall_only(**kwargs)
    assert n_missing3 == 0  # converges: stays 0, never rediscovered
