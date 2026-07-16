"""Tests for fsd.sources.mpc (spec 32).

No network — duck-typed fake items (mirrors tests/test_cdse.py's `_FakeItem`).
"""

import datetime
import types

import geopandas as gpd
import pytest
import shapely.geometry as sg

from fsd.sources import mpc


class _FakeItem:
    """Duck-typed stand-in for an MPC pystac `Item` (no network)."""

    def __init__(self, id, dt, geom, cloud, baseline, mgrs_tile=None, assets=None):
        self.id = id
        self.datetime = dt
        self.geometry = sg.mapping(geom)
        self.properties = {"eo:cloud_cover": cloud}
        if baseline is not None:
            self.properties["s2:processing_baseline"] = baseline
        if mgrs_tile is not None:
            self.properties["s2:mgrs_tile"] = mgrs_tile
        self.assets = {k: types.SimpleNamespace(href=v) for k, v in (assets or {}).items()}


def _fake_item(id, dt, lon, lat, cloud, baseline="05.09", mgrs_tile=None, assets=None):
    if assets is None:
        assets = {"B04": f"https://example/{id}/B04.tif?sig=abc"}
    dt = datetime.datetime.fromisoformat(dt.replace("Z", "+00:00"))
    return _FakeItem(id, dt, sg.box(lon, lat, lon + 1, lat + 1), cloud, baseline,
                     mgrs_tile=mgrs_tile, assets=assets)


# --- baseline -> offset (spec 32 D2/D3, correctness debt #10) ----------------


def test_baseline_tuple_parses_major_minor():
    assert mpc._baseline_tuple("04.00") == (4, 0)
    assert mpc._baseline_tuple("05.09") == (5, 9)
    assert mpc._baseline_tuple("02.14") == (2, 14)


def test_offset_for_item_pre_and_post_04():
    pre = _fake_item("pre", "2021-06-01T00:00:00Z", 0, 0, 5.0, baseline="02.14")
    post = _fake_item("post", "2022-06-01T00:00:00Z", 0, 0, 5.0, baseline="04.00")
    assert mpc._offset_for_item(pre) == 0
    assert mpc._offset_for_item(post) == -1000


def test_offset_for_item_reprocessed_pre_2022_date_still_yields_offset():
    # the date-vs-baseline trap: an old acquisition reprocessed at a >=04.00
    # baseline must still get the offset (keyed on baseline, not date).
    reprocessed = _fake_item(
        "old-but-reprocessed", "2019-01-01T00:00:00Z", 0, 0, 5.0, baseline="05.09",
    )
    assert mpc._offset_for_item(reprocessed) == -1000


def test_offset_for_item_missing_baseline_raises():
    it = _fake_item("no-baseline", "2021-06-01T00:00:00Z", 0, 0, 5.0, baseline=None)
    with pytest.raises(ValueError, match="s2:processing_baseline"):
        mpc._offset_for_item(it)


# --- items -> catalog gdf -----------------------------------------------------


def test_items_to_gdf_carries_boa_add_offset():
    items = [
        _fake_item("pre", "2021-06-01T00:00:00Z", 16.0, 48.0, 5.0, baseline="02.14"),
        _fake_item("post", "2022-06-01T00:00:00Z", 16.0, 48.0, 5.0, baseline="04.00"),
    ]
    gdf = mpc._items_to_gdf(items)
    assert list(gdf["id"]) == ["pre", "post"]
    assert list(gdf["boa_add_offset"]) == [0, -1000]
    assert gdf.crs.to_epsg() == 4326
    assert str(gdf["timestamp"].dt.tz) == "UTC"


def test_mgrs_tile_from_item_prefers_property_falls_back_to_id():
    with_tile = _fake_item("x", "2021-06-01T00:00:00Z", 0, 0, 1.0, mgrs_tile="T33UWP")
    without_tile = _fake_item("y", "2021-06-01T00:00:00Z", 0, 0, 1.0)
    assert mpc._mgrs_tile_from_item(with_tile) == "T33UWP"
    assert mpc._mgrs_tile_from_item(without_tile) == "y"


def test_select_item_files_maps_requested_bands_to_asset_hrefs(tmp_path):
    it = _fake_item(
        "t1", "2021-06-01T00:00:00Z", 0, 0, 1.0,
        assets={"B04": "https://example/t1/B04.tif?sig=1",
                "SCL": "https://example/t1/SCL.tif?sig=2"},
    )
    selected = mpc._select_item_files(it, ["B04", "SCL", "B02"], str(tmp_path))
    assert selected == [
        ("https://example/t1/B04.tif?sig=1", str(tmp_path / "t1" / "B04.tif")),
        ("https://example/t1/SCL.tif?sig=2", str(tmp_path / "t1" / "SCL.tif")),
    ]  # B02 not in assets -> skipped, no KeyError


def test_finalize_filters_cloud_and_roi_reused_from_cdse():
    items = [
        _fake_item("hit", "2021-06-01T00:00:00Z", 0.0, 0.0, 10.0),
        _fake_item("cloudy", "2021-06-01T00:00:00Z", 0.0, 0.0, 90.0),
    ]
    gdf = mpc._items_to_gdf(items)
    roi = gpd.GeoDataFrame(geometry=[sg.box(0.2, 0.2, 0.5, 0.5)], crs="EPSG:4326")
    out = mpc._finalize_catalog_gdf(gdf, roi, max_cloudcover=50.0)
    assert list(out["id"]) == ["hit"]


# --- download (pure copy, mocked transfer) ------------------------------------


def test_transfer_one_skips_existing_final(tmp_path):
    dst = tmp_path / "B04.tif"
    dst.write_bytes(b"already-here")
    ok, reason = mpc._transfer_one("https://example/B04.tif", str(dst))
    assert ok is True
    assert reason == "skipped"


def test_download_end_to_end_mocked(monkeypatch, tmp_path):
    items = [
        _fake_item(
            "pre", "2021-06-01T00:00:00Z", 0.0, 0.0, 5.0, baseline="02.14",
            assets={"B04": "https://example/pre/B04.tif?sig=1"},
        ),
        _fake_item(
            "post", "2022-06-01T00:00:00Z", 0.0, 0.0, 5.0, baseline="04.00",
            assets={"B04": "https://example/post/B04.tif?sig=2"},
        ),
    ]
    monkeypatch.setattr(mpc, "_search_items", lambda *a, **k: items)

    written = []

    def _fake_transfer(src_url, dst_url, **kw):
        written.append((src_url, dst_url))
        import os
        os.makedirs(os.path.dirname(dst_url), exist_ok=True)
        with open(dst_url, "wb") as f:
            f.write(b"cog-bytes")

    monkeypatch.setattr(mpc.fs, "transfer", _fake_transfer)

    from fsd.catalog.catalog import TileCatalog

    catalog_fp = str(tmp_path / "catalog.parquet")
    catalog = TileCatalog(catalog_fp)
    roi = gpd.GeoDataFrame(geometry=[sg.box(0.2, 0.2, 0.5, 0.5)], crs="EPSG:4326")

    result = mpc.download(
        roi, datetime.datetime(2021, 1, 1), datetime.datetime(2022, 12, 31),
        ["B04"], str(tmp_path / "imagery"), catalog, max_tiles=10,
    )
    assert result.successful_count == 2
    assert result.failed_count == 0
    assert len(written) == 2

    gdf = catalog.read()
    assert set(gdf["id"]) == {"pre", "post"}
    offsets = dict(zip(gdf["id"], gdf["boa_add_offset"]))
    assert offsets == {"pre": 0, "post": -1000}


def test_download_rejects_remote_root(tmp_path):
    from fsd.catalog.catalog import TileCatalog

    catalog = TileCatalog(str(tmp_path / "catalog.parquet"))
    roi = gpd.GeoDataFrame(geometry=[sg.box(0, 0, 1, 1)], crs="EPSG:4326")
    with pytest.raises(ValueError, match="local-only"):
        mpc.download(
            roi, datetime.datetime(2021, 1, 1), datetime.datetime(2022, 1, 1),
            ["B04"], "s3://some-bucket/imagery", catalog, max_tiles=10,
        )
