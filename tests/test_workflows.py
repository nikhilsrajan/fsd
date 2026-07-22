"""Tests for fsd.workflows (spec 08): setup, task, local dry-run."""

import datetime
import importlib.util
import os
import time
from unittest import mock

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
import rasterio
from rasterio.crs import CRS as RioCRS
from rasterio.transform import from_origin
from shapely.geometry import box

from fsd.bands import modify
from fsd.model import BaseModelAdapter, bundle
from fsd.storage import fs
from fsd.workflows import create_datacube, infer_only_task, infer_task, runners, task


class _NDVIUp(BaseModelAdapter):
    """Tiny adapter: NDVI>0 -> class 1 (spec 21 infer_task test)."""

    required_bands = ["B04", "B08"]
    n_timestamps = 1
    output_dtype = "uint8"
    output_nodata = 255
    output_band_names = ["cls"]
    feature_sequence = [
        (modify.mask_invalid_and_interpolate, {}),
        (modify.compute_bands, dict(bands_to_compute=["NDVI"])),
        (modify.remove_bands, dict(bands_to_remove=["B04", "B08"])),
    ]

    def load(self):
        pass

    def predict(self, X):
        return (X.mean(axis=1) > 0).astype("uint8")

CRS = "EPSG:32633"
TRANSFORM = from_origin(500000, 5000000, 10, 10)
TILE_UTM = box(500000, 4999960, 500040, 5000000)          # 4x4 @ 10 m
TILE_4326 = gpd.GeoSeries([TILE_UTM], crs=CRS).to_crs("EPSG:4326").iloc[0]
TS = [pd.Timestamp("2018-06-01", tz="UTC"), pd.Timestamp("2018-06-11", tz="UTC")]


def _write_tile(path, value):
    with rasterio.open(path, "w", driver="GTiff", height=4, width=4, count=1,
                       dtype="uint16", crs=CRS, transform=TRANSFORM, nodata=0) as dst:
        dst.write(np.full((1, 4, 4), value, dtype=np.uint16))


def _make_catalog(path, tmp, files="B04.jp2,B08.jp2,SCL.jp2,MTD_TL.xml", with_ac=False):
    from fsd.catalog import declaration as declaration_module
    from fsd.catalog.declaration import S2_L2A_DECLARATION

    rows = []
    for i, ts in enumerate(TS):
        r = {"id": f"T_{i}", "satellite": "sentinel-2-l2a", "timestamp": ts,
             "s3url": f"s3://eodata/x{i}", "local_folderpath": str(tmp / f"prod{i}"),
             "files": files, "cloud_cover": 0.0, "geometry": TILE_4326}
        if with_ac:
            r["area_contribution"] = 100.0
        rows.append(r)
    gdf = gpd.GeoDataFrame(rows, crs="EPSG:4326")
    # spec 35 §5a: a catalog read from a file must carry a declaration stamp or
    # `flatten_catalog`/`build_datacube` raise -- these fixtures are S2 L2A.
    declaration_module.to_attrs(gdf, S2_L2A_DECLARATION)
    fs.write_parquet(str(path), gdf)


def _two_shapes(path):
    g1 = gpd.GeoSeries([box(500005, 4999965, 500035, 4999995)], crs=CRS).to_crs("EPSG:4326")
    g2 = gpd.GeoSeries([box(500010, 4999970, 500030, 4999990)], crs=CRS).to_crs("EPSG:4326")
    gdf = gpd.GeoDataFrame({"id": ["s1", "s2"], "label": [0, 1],
                            "geometry": [g1.iloc[0], g2.iloc[0]]}, crs="EPSG:4326")
    gdf.to_file(str(path), driver="GeoJSON")


def test_setup_reads_catalog_once_regardless_of_shape_count(tmp_path, monkeypatch):
    """setup() must read the catalog file ONCE, not once per shape.

    `TileCatalog.filter` re-reads the file on every call, so the old per-shape call
    made setup cost one full catalog download per shape -- invisible locally (page
    cache) and brutal on `abfss://`: 900 shapes = 900 downloads of the same parquet
    before a single job was dispatched (measured 2026-07-22 on the rise cluster).
    Counting reads is the only way to keep that from silently coming back.
    """
    from fsd.storage import fs as storage_fs

    cat = tmp_path / "catalog.parquet"
    shapes = tmp_path / "shapes.geojson"
    _make_catalog(cat, tmp_path)
    _two_shapes(shapes)

    reads: list[str] = []
    real_read_parquet = storage_fs.read_parquet

    def counting_read_parquet(path, **kw):
        reads.append(str(path))
        return real_read_parquet(path, **kw)

    monkeypatch.setattr(storage_fs, "read_parquet", counting_read_parquet)

    create_datacube.setup(
        catalog_filepath=str(cat), timestamp_col="timestamp",
        shapefilepath=str(shapes), id_col="id", run_folderpath=str(tmp_path / "run"),
        startdate=datetime.datetime(2018, 1, 1), enddate=datetime.datetime(2019, 1, 1),
        bands=["B04", "B08", "SCL"], scl_mask_classes=[8, 9], mosaic_days=20,
        csv_filepath=str(tmp_path / "run" / "input.csv"), label_col="label",
    )

    # Two shapes, but the source catalog is read exactly once. (The per-shape slices
    # written under run/ are different files and are not read back here.)
    assert [r for r in reads if r == str(cat)] == [str(cat)]


def test_setup_manifest_order_is_shapefile_order_not_completion_order(tmp_path):
    """Concurrency must not reorder `input.csv`.

    Shapes are prepared in a thread pool, so completion order is nondeterministic;
    rows are placed by index and compacted. Downstream (`shard_units`, the flatten
    concatenation) treats the manifest as ordered, so a reordering would be a silent
    behaviour change. Staggering the per-shape cost makes completion order differ
    from submission order with near-certainty.
    """
    from fsd.storage import fs as storage_fs

    cat = tmp_path / "catalog.parquet"
    shapes = tmp_path / "shapes.geojson"
    _make_catalog(cat, tmp_path)

    # 6 nested boxes, all overlapping the tile -> every shape yields a work-unit.
    ids = [f"s{i}" for i in range(6)]
    geoms = [
        gpd.GeoSeries([box(500005 - i, 4999965 - i, 500035 + i, 4999995 + i)],
                      crs=CRS).to_crs("EPSG:4326").iloc[0]
        for i in range(6)
    ]
    gpd.GeoDataFrame({"id": ids, "geometry": geoms}, crs="EPSG:4326").to_file(
        str(shapes), driver="GeoJSON")

    # Make the first shapes the SLOWEST, so completion order inverts submission order.
    real_write_parquet = storage_fs.write_parquet
    order: list[str] = []

    def staggered_write_parquet(path, df, **kw):
        idx = int(str(path).rsplit("/", 2)[1][1:]) if "/s" in str(path) else 0
        time.sleep(0.05 * (6 - idx))
        order.append(str(path))
        return real_write_parquet(path, df, **kw)

    with mock.patch.object(storage_fs, "write_parquet", staggered_write_parquet):
        create_datacube.setup(
            catalog_filepath=str(cat), timestamp_col="timestamp",
            shapefilepath=str(shapes), id_col="id", run_folderpath=str(tmp_path / "run"),
            startdate=datetime.datetime(2018, 1, 1), enddate=datetime.datetime(2019, 1, 1),
            bands=["B04"], scl_mask_classes=[8], mosaic_days=20,
            csv_filepath=str(tmp_path / "run" / "input.csv"), label_col=None,
            max_concurrent=6,
        )

    df = pd.read_csv(tmp_path / "run" / "input.csv")
    assert df["id"].tolist() == ids                    # shapefile order, not completion order
    assert [o for o in order][0] != df["catalog_filepath"].iloc[0]  # they really did differ


def test_setup_writes_workunits(tmp_path):
    cat = tmp_path / "catalog.parquet"
    shapes = tmp_path / "shapes.geojson"
    _make_catalog(cat, tmp_path)
    _two_shapes(shapes)
    csv = tmp_path / "run" / "input.csv"

    create_datacube.setup(
        catalog_filepath=str(cat), timestamp_col="timestamp",
        shapefilepath=str(shapes), id_col="id", run_folderpath=str(tmp_path / "run"),
        startdate=datetime.datetime(2018, 1, 1), enddate=datetime.datetime(2019, 1, 1),
        bands=["B04", "B08", "SCL"], scl_mask_classes=[8, 9], mosaic_days=20,
        csv_filepath=str(csv), label_col="label",
    )

    df = pd.read_csv(csv)
    assert len(df) == 2                                   # one work-unit per shape
    for col in ["shapefilepath", "startdate", "enddate", "catalog_filepath",
                "export_folderpath", "datacube_filepath", "images_count", "id",
                "label", "mosaic_days", "scl_mask_classes", "bands", "added_on"]:
        assert col in df.columns
    assert (df["images_count"] == 2).all()                # both tiles intersect
    assert df["scl_mask_classes"].iloc[0] == "8,9"
    assert df["bands"].iloc[0] == "B04,B08,SCL"
    # per-shape control files exist
    for _, r in df.iterrows():
        assert fs.exists(r["shapefilepath"]) and fs.exists(r["catalog_filepath"])
    assert set(gpd.read_parquet(df["catalog_filepath"].iloc[0]).columns) >= {
        "id", "timestamp", "files", "local_folderpath", "area_contribution"}


def test_setup_does_not_corrupt_a_remote_run_folderpath(tmp_path, monkeypatch):
    """specs/31 §6 finding: os.path.abspath must not be applied to a URL (it would
    turn `abfss://fs@acct.../x` into a mangled local-cwd-prefixed string). setup()'s
    per-shape export_folderpath must stay a clean abfss:// URL when run_folderpath is
    remote. Real adlfs I/O is mocked out (no credentials/network in this test)."""
    cat = tmp_path / "catalog.parquet"
    shapes = tmp_path / "shapes.geojson"
    _make_catalog(cat, tmp_path)
    _two_shapes(shapes)

    remote_root = "abfss://data@acct.dfs.core.windows.net/p1-demo/run"
    written = {}

    class _FakeWriteHandle:
        def __init__(self, path):
            self._path = path
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False
        def write(self, data):
            written.setdefault("geojson", self._path)

    _real_open = fs.open

    def _open(path, mode="rb", **kw):
        # D6a (spec 36): the per-shape geometry now writes via `fs.open(path, "w")` +
        # `to_json()`, not `gpd.GeoDataFrame.to_file` -- mock only that write; the
        # caller's (local) input geojson still reads for real.
        if mode == "w" and path.startswith(remote_root):
            return _FakeWriteHandle(path)
        return _real_open(path, mode, **kw)

    monkeypatch.setattr(fs, "makedirs", lambda *a, **kw: None)
    monkeypatch.setattr(fs, "write_parquet", lambda path, df, **kw: written.setdefault("parquet", path))
    monkeypatch.setattr(fs, "open", _open)

    csv_local = tmp_path / "input.csv"  # the work-unit ledger itself can stay local
    create_datacube.setup(
        catalog_filepath=str(cat), timestamp_col="timestamp",
        shapefilepath=str(shapes), id_col="id", run_folderpath=remote_root,
        startdate=datetime.datetime(2018, 1, 1), enddate=datetime.datetime(2019, 1, 1),
        bands=["B04", "B08", "SCL"], scl_mask_classes=[8, 9], mosaic_days=20,
        csv_filepath=str(csv_local), label_col="label",
    )

    df = pd.read_csv(csv_local)
    assert len(df) == 2
    for p in df["export_folderpath"]:
        assert p.startswith(remote_root + "/")
        assert "abfss:/" + "/" not in p.replace(remote_root, "")  # no mangled second scheme
        assert str(tmp_path) not in p  # no local-cwd prefix leaked in (the abspath bug)


@pytest.mark.skipif(importlib.util.find_spec("snakemake") is None,
                    reason="snakemake not installed")
def test_snakefile_plans_a_remote_export_folderpath(tmp_path):
    """D7 (spec 36): sentinels move to node-local scratch, decoupled from
    export_folderpath, so a remote (e.g. abfss://) export_folderpath is no longer
    rejected -- dry-run must plan the job instead of raising (specs/31 §6's finding is
    now handled by scratch-dir sentinels, not a guard)."""
    csv = tmp_path / "input.csv"
    pd.DataFrame([{
        "shapefilepath": str(tmp_path / "geometry.geojson"),
        "catalog_filepath": str(tmp_path / "catalog.parquet"),
        "startdate": "2018-01-01", "enddate": "2019-01-01",
        "export_folderpath": "abfss://data@acct.dfs.core.windows.net/p1-demo/run/x/s1",
        "mosaic_days": 20, "mosaic_scheme": "calendar", "scl_mask_classes": "8,9",
        "bands": "B04,B08,SCL",
    }]).to_csv(csv, index=False)

    result = runners.run_local(str(csv), cores=1, dry_run=True)
    assert result.returncode == 0


def test_setup_raises_when_no_workunits(tmp_path):
    cat = tmp_path / "catalog.parquet"
    _make_catalog(cat, tmp_path)
    _two_shapes(tmp_path / "shapes.geojson")
    with pytest.raises(ValueError, match="no work-units"):
        create_datacube.setup(
            catalog_filepath=str(cat), timestamp_col="timestamp",
            shapefilepath=str(tmp_path / "shapes.geojson"), id_col="id",
            run_folderpath=str(tmp_path / "run"),
            startdate=datetime.datetime(2020, 1, 1),   # window with no tiles
            enddate=datetime.datetime(2020, 2, 1),
            bands=["B04"], scl_mask_classes=[8], mosaic_days=20,
            csv_filepath=str(tmp_path / "run" / "input.csv"), label_col=None,
        )


def test_run_task_builds_one_datacube(tmp_path):
    # real synthetic tiles on disk (1 tile, 2 dates, bands B04/B08/SCL as .tif)
    for i in range(2):
        d = tmp_path / f"prod{i}"
        d.mkdir()
        for band, val in [("B04", 100 + i), ("B08", 200 + i), ("SCL", 4)]:
            _write_tile(d / f"{band}.tif", val)
    cat = tmp_path / "subset.parquet"
    _make_catalog(cat, tmp_path, files="B04.tif,B08.tif,SCL.tif", with_ac=True)
    shape = tmp_path / "geometry.geojson"
    gpd.GeoDataFrame({"id": ["s1"], "geometry": [TILE_4326]},
                     crs="EPSG:4326").to_file(str(shape), driver="GeoJSON")
    out = tmp_path / "cube"

    task.run_task(
        str(shape), str(cat), TS[0], TS[1], str(out),
        bands=["B04", "B08", "SCL"], mosaic_days=20, scl_mask_classes=[8],
        if_missing_files="warn",
    )
    dc = fs.load_npy(str(out / "datacube.npy"))
    md = fs.load_npy(str(out / "metadata.pickle.npy"), allow_pickle=True)[()]
    assert dc.shape == (1, 4, 4, 2)                        # 2 dates -> 1 mosaic; SCL dropped
    assert md["bands"] == ["B04", "B08"]


def test_task_parse_args_splits_lists():
    ns = task._parse_args(["g.geojson", "c.parquet", "2018-01-01", "2018-02-01", "o",
                           "--bands", "B04,B08,SCL", "--scl-mask-classes", "3,8,9"])
    assert ns.bands == "B04,B08,SCL" and ns.scl_mask_classes == "3,8,9"


def test_infer_task_builds_and_infers_to_cog(tmp_path):
    """spec 21: the per-cell unit-of-work builds a datacube AND infers it to a COG."""
    for i in range(2):
        d = tmp_path / f"prod{i}"
        d.mkdir()
        for band, val in [("B04", 2000), ("B08", 8000), ("SCL", 4)]:   # NDVI = +0.6
            _write_tile(d / f"{band}.tif", val)
    cat = tmp_path / "subset.parquet"
    _make_catalog(cat, tmp_path, files="B04.tif,B08.tif,SCL.tif", with_ac=True)
    shape = tmp_path / "geometry.geojson"
    gpd.GeoDataFrame({"id": ["s1"], "geometry": [TILE_4326]},
                     crs="EPSG:4326").to_file(str(shape), driver="GeoJSON")
    bundle_dir = bundle.save(_NDVIUp(), {}, str(tmp_path / "bundle"))
    export = tmp_path / "cell"
    out_tif = export / "output.tif"

    infer_task.run_infer_task(
        str(shape), str(cat), TS[0], TS[1], str(export),
        bands=["B04", "B08", "SCL"], mosaic_days=20, scl_mask_classes=[8],
        bundle_path=bundle_dir, output_filepath=str(out_tif), if_missing_files="warn",
    )

    assert (export / "datacube.npy").exists()                 # datacube kept alongside
    with rasterio.open(str(out_tif)) as src:
        assert src.count == 1 and src.nodata == 255
        assert src.read(1)[0, 0] == 1                         # NDVI>0 -> class 1


def test_infer_task_parse_args():
    ns = infer_task._parse_args(
        ["g.geojson", "c.parquet", "2018-01-01", "2018-02-01", "o",
         "--bands", "B04,B08", "--bundle", "b", "--output", "out.tif",
         "--predict-batch-size", "500"])
    assert ns.bundle == "b" and ns.output == "out.tif" and ns.predict_batch_size == 500


def _write_prebuilt_cube(folder, *, T=1, H=4, W=4, bands=("B04", "B08")):
    """A minimal pre-built datacube folder (NDVI>0 everywhere) for infer-only tests."""
    os.makedirs(folder, exist_ok=True)
    dc = np.zeros((T, H, W, len(bands)), dtype=np.uint16)
    dc[..., 0], dc[..., 1] = 2000, 8000                        # NDVI = +0.6 -> class 1
    fs.save_npy(os.path.join(folder, "datacube.npy"), dc)
    md = {"bands": list(bands), "timestamps": list(range(T)),
          "geotiff_metadata": {"width": W, "height": H,
                               "transform": from_origin(500000, 4000000, 10, 10),
                               "crs": RioCRS.from_epsg(32633)}}
    fs.save_npy(os.path.join(folder, "metadata.pickle.npy"), md, allow_pickle=True)
    return os.path.join(folder, "datacube.npy")


def test_infer_only_task_infers_and_is_idempotent(tmp_path):
    """spec 22: infer-only task infers pre-built cubes -> COGs and skips existing unless overwrite."""
    d0 = _write_prebuilt_cube(str(tmp_path / "c0"))
    d1 = _write_prebuilt_cube(str(tmp_path / "c1"))
    bundle_dir = bundle.save(_NDVIUp(), {}, str(tmp_path / "bundle"))
    o0, o1 = str(tmp_path / "o0.tif"), str(tmp_path / "o1.tif")
    csv = tmp_path / "input.csv"
    pd.DataFrame({"datacube_filepath": [d0, d1],
                  "output_filepath": [o0, o1]}).to_csv(csv, index=False)

    written = infer_only_task.run_infer_only(str(csv), (0, 2), bundle_dir)   # process both rows
    assert set(written) == {o0, o1}
    for o in (o0, o1):
        with rasterio.open(o) as s:
            assert s.count == 1 and s.read(1)[0, 0] == 1
    assert infer_only_task.run_infer_only(str(csv), (0, 2), bundle_dir) == []      # skip existing
    assert len(infer_only_task.run_infer_only(str(csv), (0, 2), bundle_dir, overwrite=True)) == 2


def test_infer_only_parse_rows_and_args():
    ns = infer_only_task._parse_args(
        ["--input-csv", "c.csv", "--rows", "0:5", "--bundle", "b", "--overwrite"])
    assert ns.rows == "0:5" and ns.bundle == "b" and ns.overwrite
    assert infer_only_task._parse_rows("2:7") == (2, 7)


@pytest.mark.skipif(importlib.util.find_spec("snakemake") is None,
                    reason="snakemake not installed")
def test_run_local_infer_only_dry_run_groups_jobs(tmp_path):
    """spec 22: infer-only Snakefile chunks rows into cubes_per_task groups (dry-run)."""
    csv = tmp_path / "input.csv"
    pd.DataFrame({"datacube_filepath": ["a", "b", "c"],
                  "output_filepath": ["x.tif", "y.tif", "z.tif"]}).to_csv(csv, index=False)
    result = runners.run_local_infer_only(
        str(csv), cores=1, bundle_path=str(tmp_path / "bundle"),
        cubes_per_task=2, dry_run=True)                        # 3 rows / 2 -> 2 groups
    assert result.returncode == 0


@pytest.mark.skipif(importlib.util.find_spec("snakemake") is None,
                    reason="snakemake not installed")
def test_run_local_inference_dry_run_plans_jobs(tmp_path):
    """spec 21: the ROI-inference Snakefile plans one job per cell (dry-run)."""
    cat = tmp_path / "catalog.parquet"
    _make_catalog(cat, tmp_path)
    _two_shapes(tmp_path / "shapes.geojson")
    csv = tmp_path / "run" / "input.csv"
    create_datacube.setup(
        catalog_filepath=str(cat), timestamp_col="timestamp",
        shapefilepath=str(tmp_path / "shapes.geojson"), id_col="id",
        run_folderpath=str(tmp_path / "run"),
        startdate=datetime.datetime(2018, 1, 1), enddate=datetime.datetime(2019, 1, 1),
        bands=["B04", "B08", "SCL"], scl_mask_classes=[8], mosaic_days=20,
        csv_filepath=str(csv), label_col=None,
    )
    result = runners.run_local_inference(
        str(csv), cores=1, bundle_path=str(tmp_path / "bundle"), dry_run=True)
    assert result.returncode == 0


@pytest.mark.skipif(importlib.util.find_spec("snakemake") is None,
                    reason="snakemake not installed")
def test_run_local_dry_run_plans_jobs(tmp_path):
    cat = tmp_path / "catalog.parquet"
    _make_catalog(cat, tmp_path)
    _two_shapes(tmp_path / "shapes.geojson")
    csv = tmp_path / "run" / "input.csv"
    create_datacube.setup(
        catalog_filepath=str(cat), timestamp_col="timestamp",
        shapefilepath=str(tmp_path / "shapes.geojson"), id_col="id",
        run_folderpath=str(tmp_path / "run"),
        startdate=datetime.datetime(2018, 1, 1), enddate=datetime.datetime(2019, 1, 1),
        bands=["B04", "B08", "SCL"], scl_mask_classes=[8], mosaic_days=20,
        csv_filepath=str(csv), label_col=None,
    )
    result = runners.run_local(str(csv), cores=1, dry_run=True)
    assert result.returncode == 0
