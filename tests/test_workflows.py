"""Tests for fsd.workflows (spec 08): setup, task, local dry-run."""

import datetime
import importlib.util

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
import rasterio
from rasterio.transform import from_origin
from shapely.geometry import box

from fsd.storage import fs
from fsd.workflows import create_datacube, runners, task

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
    rows = []
    for i, ts in enumerate(TS):
        r = {"id": f"T_{i}", "satellite": "sentinel-2-l2a", "timestamp": ts,
             "s3url": f"s3://eodata/x{i}", "local_folderpath": str(tmp / f"prod{i}"),
             "files": files, "cloud_cover": 0.0, "geometry": TILE_4326}
        if with_ac:
            r["area_contribution"] = 100.0
        rows.append(r)
    fs.write_parquet(str(path), gpd.GeoDataFrame(rows, crs="EPSG:4326"))


def _two_shapes(path):
    g1 = gpd.GeoSeries([box(500005, 4999965, 500035, 4999995)], crs=CRS).to_crs("EPSG:4326")
    g2 = gpd.GeoSeries([box(500010, 4999970, 500030, 4999990)], crs=CRS).to_crs("EPSG:4326")
    gdf = gpd.GeoDataFrame({"id": ["s1", "s2"], "label": [0, 1],
                            "geometry": [g1.iloc[0], g2.iloc[0]]}, crs="EPSG:4326")
    gdf.to_file(str(path), driver="GeoJSON")


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
