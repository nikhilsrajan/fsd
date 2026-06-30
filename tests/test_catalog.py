"""Tests for fsd.catalog.TileCatalog (spec 02).

Covers: append -> read round-trip, `files` union on re-append, and `filter`
(inclusive date range + spatial overlap + area_contribution).
"""

import datetime

import geopandas as gpd
import shapely.geometry as sg

from fsd import config
from fsd.catalog.catalog import TileCatalog


def _box(x0, y0, x1, y1):
    return sg.box(x0, y0, x1, y1)


def _row(id, ts, files, geom, **kw):
    base = dict(
        id=id,
        satellite=config.SATELLITE_S2L2A,
        timestamp=ts,
        s3url=f"s3://eodata/{id}.SAFE",
        local_folderpath=f"/data/{id}",
        files=files,
        cloud_cover=0.0,
        geometry=geom,
    )
    base.update(kw)
    return base


def test_append_read_roundtrip(tmp_path):
    cat = TileCatalog(str(tmp_path / "catalog.parquet"))
    cat.append(
        [
            _row("t1", "2024-08-01T10:00:00Z", "B02.jp2,SCL.jp2", _box(0, 0, 1, 1)),
            _row("t2", "2024-08-05T10:00:00Z", "B02.jp2", _box(1, 1, 2, 2)),
        ]
    )
    gdf = cat.read()
    assert len(gdf) == 2
    assert set(gdf["id"]) == {"t1", "t2"}
    assert gdf.crs.to_epsg() == 4326
    assert str(gdf["timestamp"].dt.tz) == "UTC"


def test_files_union_on_reappend(tmp_path):
    cat = TileCatalog(str(tmp_path / "catalog.parquet"))
    cat.append([_row("t1", "2024-08-01T10:00:00Z", "B02.jp2", _box(0, 0, 1, 1))])
    # Re-download more bands for the same tile + a higher cloud_cover value.
    cat.append(
        [
            _row(
                "t1",
                "2024-08-01T10:00:00Z",
                "B08.jp2,SCL.jp2",
                _box(0, 0, 1, 1),
                cloud_cover=12.5,
            )
        ]
    )
    gdf = cat.read()
    assert len(gdf) == 1  # upsert, not duplicate
    files = gdf.loc[gdf["id"] == "t1", "files"].iloc[0]
    assert files == "B02.jp2,B08.jp2,SCL.jp2"  # unioned + sorted
    # other columns take the newest value
    assert gdf.loc[gdf["id"] == "t1", "cloud_cover"].iloc[0] == 12.5


def test_filter_date_and_spatial(tmp_path):
    cat = TileCatalog(str(tmp_path / "catalog.parquet"))
    cat.append(
        [
            # in range + overlaps ROI
            _row("hit", "2024-08-10T10:00:00Z", "B02.jp2", _box(0, 0, 2, 2)),
            # in range but no spatial overlap
            _row("far", "2024-08-11T10:00:00Z", "B02.jp2", _box(10, 10, 11, 11)),
            # overlaps but before the date range
            _row("early", "2024-07-01T10:00:00Z", "B02.jp2", _box(0, 0, 2, 2)),
            # overlaps but after the date range
            _row("late", "2024-09-01T10:00:00Z", "B02.jp2", _box(0, 0, 2, 2)),
        ]
    )
    roi = gpd.GeoDataFrame(geometry=[_box(0, 0, 1, 1)], crs="EPSG:4326")
    out = cat.filter(
        roi,
        datetime.datetime(2024, 8, 1),
        datetime.datetime(2024, 8, 31),
    )
    assert list(out["id"]) == ["hit"]
    # ROI (1x1) fully inside the 2x2 tile -> 100% contribution.
    assert abs(out["area_contribution"].iloc[0] - 100.0) < 1e-6


def test_filter_partial_area_contribution(tmp_path):
    cat = TileCatalog(str(tmp_path / "catalog.parquet"))
    # Tile covers the left half of a 2x2 ROI -> 50% contribution.
    cat.append([_row("half", "2024-08-10T10:00:00Z", "B02.jp2", _box(0, 0, 1, 2))])
    roi = gpd.GeoDataFrame(geometry=[_box(0, 0, 2, 2)], crs="EPSG:4326")
    out = cat.filter(
        roi,
        datetime.datetime(2024, 8, 1),
        datetime.datetime(2024, 8, 31),
    )
    assert abs(out["area_contribution"].iloc[0] - 50.0) < 1e-6


def test_filter_inclusive_bounds(tmp_path):
    cat = TileCatalog(str(tmp_path / "catalog.parquet"))
    cat.append(
        [
            _row("start", "2024-08-01T00:00:00Z", "B02.jp2", _box(0, 0, 1, 1)),
            _row("end", "2024-08-31T00:00:00Z", "B02.jp2", _box(0, 0, 1, 1)),
        ]
    )
    roi = gpd.GeoDataFrame(geometry=[_box(0, 0, 1, 1)], crs="EPSG:4326")
    out = cat.filter(
        roi,
        datetime.datetime(2024, 8, 1),
        datetime.datetime(2024, 8, 31),
    )
    assert set(out["id"]) == {"start", "end"}


def test_append_empty_is_noop(tmp_path):
    cat = TileCatalog(str(tmp_path / "catalog.parquet"))
    cat.append([])
    from fsd.storage import fs

    assert not fs.exists(cat.filepath)
