"""Tests for fsd.sources.mpc (spec 32/34).

No network — duck-typed fake items (mirrors tests/test_cdse.py's `_FakeItem`).
"""

import datetime
import types

import geopandas as gpd
import pytest
import shapely.geometry as sg
from pystac.extensions.raster import RasterExtension

from fsd import config
from fsd.sources import _s2_radiometry, mpc


class _FakeItem:
    """Duck-typed stand-in for an MPC pystac `Item` (no network)."""

    def __init__(self, id, dt, geom, cloud, baseline, mgrs_tile=None, assets=None,
                 generation_time=None, processing_version=None):
        self.id = id
        self.datetime = dt
        self.geometry = sg.mapping(geom)
        self.properties = {"eo:cloud_cover": cloud}
        if baseline is not None:
            self.properties["s2:processing_baseline"] = baseline
        if processing_version is not None:
            self.properties["processing:version"] = processing_version
        if mgrs_tile is not None:
            self.properties["s2:mgrs_tile"] = mgrs_tile
        if generation_time is not None:
            self.properties["s2:generation_time"] = generation_time
        self.assets = {k: types.SimpleNamespace(href=v) for k, v in (assets or {}).items()}


def _fake_item(id, dt, lon, lat, cloud, baseline="05.09", mgrs_tile=None, assets=None,
                generation_time=None, processing_version=None):
    if assets is None:
        assets = {"B04": f"https://example/{id}/B04.tif?sig=abc"}
    dt = datetime.datetime.fromisoformat(dt.replace("Z", "+00:00"))
    return _FakeItem(id, dt, sg.box(lon, lat, lon + 1, lat + 1), cloud, baseline,
                     mgrs_tile=mgrs_tile, assets=assets, generation_time=generation_time,
                     processing_version=processing_version)


# --- baseline -> offset (spec 34 §1, generalizing spec 32 D2/D3) -------------


def test_baseline_tuple_parses_major_minor():
    assert _s2_radiometry.baseline_tuple("04.00") == (4, 0)
    assert _s2_radiometry.baseline_tuple("05.09") == (5, 9)
    assert _s2_radiometry.baseline_tuple("02.14") == (2, 14)


def test_offset_for_item_pre_and_post_04():
    pre = _fake_item("pre", "2021-06-01T00:00:00Z", 0, 0, 5.0, baseline="02.14")
    post = _fake_item("post", "2022-06-01T00:00:00Z", 0, 0, 5.0, baseline="04.00")
    assert mpc.offset_for_item(pre) == 0
    assert mpc.offset_for_item(post) == -1000


def test_offset_for_item_reprocessed_pre_2022_date_still_yields_offset():
    # the date-vs-baseline trap: an old acquisition reprocessed at a >=04.00
    # baseline must still get the offset (keyed on baseline, not date).
    reprocessed = _fake_item(
        "old-but-reprocessed", "2019-01-01T00:00:00Z", 0, 0, 5.0, baseline="05.09",
    )
    assert mpc.offset_for_item(reprocessed) == -1000


def test_offset_for_item_missing_baseline_raises():
    it = _fake_item("no-baseline", "2021-06-01T00:00:00Z", 0, 0, 5.0, baseline=None)
    with pytest.raises(ValueError, match="s2:processing_baseline"):
        mpc.offset_for_item(it)


# --- provider-specific baseline property (spec 34 §3a Amendment A1) ----------


def test_offset_for_item_resolves_from_processing_version_alone():
    pre = _fake_item(
        "cdse-pre", "2021-06-01T00:00:00Z", 0, 0, 5.0, baseline=None,
        processing_version="02.14",
    )
    post = _fake_item(
        "cdse-post", "2022-06-01T00:00:00Z", 0, 0, 5.0, baseline=None,
        processing_version="05.10",
    )
    assert mpc.offset_for_item(pre) == 0
    assert mpc.offset_for_item(post) == -1000


def test_offset_for_item_prefers_s2_processing_baseline_when_both_present():
    # both properties present and disagreeing — s2:processing_baseline wins
    # (pins the ordering as a decision, not an accident).
    it = _fake_item(
        "both", "2022-06-01T00:00:00Z", 0, 0, 5.0, baseline="02.14",
        processing_version="05.10",
    )
    assert mpc.offset_for_item(it) == 0


def test_offset_for_item_missing_both_baseline_props_raises():
    it = _fake_item(
        "no-baseline-either", "2021-06-01T00:00:00Z", 0, 0, 5.0, baseline=None,
        processing_version=None,
    )
    with pytest.raises(ValueError, match="s2:processing_baseline"):
        mpc.offset_for_item(it)


# --- items -> catalog gdf -----------------------------------------------------


def test_items_to_gdf_carries_offset_and_nodata():
    items = [
        _fake_item("pre", "2021-06-01T00:00:00Z", 16.0, 48.0, 5.0, baseline="02.14"),
        _fake_item("post", "2022-06-01T00:00:00Z", 16.0, 48.0, 5.0, baseline="04.00"),
    ]
    gdf = mpc._items_to_gdf(items)
    assert list(gdf["id"]) == ["pre", "post"]
    assert list(gdf["offset"]) == [0, -1000]
    assert list(gdf["nodata"]) == [0, 0]
    assert gdf.crs.to_epsg() == 4326
    assert str(gdf["timestamp"].dt.tz) == "UTC"


def test_mgrs_tile_from_item_prefers_property_falls_back_to_id():
    with_tile = _fake_item("x", "2021-06-01T00:00:00Z", 0, 0, 1.0, mgrs_tile="T33UWP")
    without_tile = _fake_item("y", "2021-06-01T00:00:00Z", 0, 0, 1.0)
    assert mpc._mgrs_tile_from_item(with_tile) == "T33UWP"
    assert mpc._mgrs_tile_from_item(without_tile) == "y"


# --- reprocessing dedup (spec 33) ---------------------------------------------


def test_dedupe_no_duplicates_is_noop():
    items = [
        _fake_item("a", "2021-06-01T00:00:00Z", 0, 0, 1.0, mgrs_tile="T33UWP"),
        _fake_item("b", "2021-06-08T00:00:00Z", 0, 0, 1.0, mgrs_tile="T33UWP"),
    ]
    out = mpc._dedupe_reprocessed_items(items)
    assert {it.id for it in out} == {"a", "b"}
    assert len(out) == 2


def test_dedupe_duplicate_pair_latest_generation_time_wins():
    same_dt = "2022-03-01T10:00:29Z"
    original = _fake_item(
        "S2B_MSIL2A_20220301T100029_R122_T33UWP_20220303T182540", same_dt, 0, 0, 1.0,
        mgrs_tile="T33UWP", generation_time="2022-03-03T18:25:40Z",
    )
    reprocessed = _fake_item(
        "S2B_MSIL2A_20220301T100029_R122_T33UWP_20240604T180322", same_dt, 0, 0, 1.0,
        mgrs_tile="T33UWP", generation_time="2024-06-04T18:03:22Z",
    )
    out = mpc._dedupe_reprocessed_items([original, reprocessed])
    assert len(out) == 1
    assert out[0].id == "S2B_MSIL2A_20220301T100029_R122_T33UWP_20240604T180322"

    # order-independence
    out2 = mpc._dedupe_reprocessed_items([reprocessed, original])
    assert len(out2) == 1
    assert out2[0].id == "S2B_MSIL2A_20220301T100029_R122_T33UWP_20240604T180322"


def test_dedupe_three_way_group_latest_wins_regardless_of_order():
    same_dt = "2022-03-01T10:00:29Z"
    v1 = _fake_item("v1", same_dt, 0, 0, 1.0, mgrs_tile="T33UWP",
                     generation_time="2022-03-03T18:25:40Z")
    v2 = _fake_item("v2", same_dt, 0, 0, 1.0, mgrs_tile="T33UWP",
                     generation_time="2023-01-01T00:00:00Z")
    v3 = _fake_item("v3", same_dt, 0, 0, 1.0, mgrs_tile="T33UWP",
                     generation_time="2024-06-04T18:03:22Z")
    for ordering in ([v1, v2, v3], [v3, v1, v2], [v2, v3, v1]):
        out = mpc._dedupe_reprocessed_items(ordering)
        assert len(out) == 1
        assert out[0].id == "v3"


def test_dedupe_missing_generation_time_on_duplicate_group_raises():
    same_dt = "2022-03-01T10:00:29Z"
    a = _fake_item("a", same_dt, 0, 0, 1.0, mgrs_tile="T33UWP",
                    generation_time="2022-03-03T18:25:40Z")
    b = _fake_item("b", same_dt, 0, 0, 1.0, mgrs_tile="T33UWP")  # no generation_time
    with pytest.raises(ValueError, match="s2:generation_time"):
        mpc._dedupe_reprocessed_items([a, b])


def test_dedupe_singleton_missing_generation_time_does_not_raise():
    it = _fake_item("solo", "2021-06-01T00:00:00Z", 0, 0, 1.0, mgrs_tile="T33UWP")
    out = mpc._dedupe_reprocessed_items([it])
    assert len(out) == 1
    assert out[0].id == "solo"


def test_dedupe_key_falls_back_to_item_id_for_missing_mgrs_tile():
    same_dt = "2022-03-01T10:00:29Z"
    # no mgrs_tile -> key falls back to item.id, so distinct ids never collide
    a = _fake_item("a", same_dt, 0, 0, 1.0)
    b = _fake_item("b", same_dt, 0, 0, 1.0)
    out = mpc._dedupe_reprocessed_items([a, b])
    assert {it.id for it in out} == {"a", "b"}


def test_select_item_files_maps_requested_bands_to_asset_hrefs(tmp_path):
    it = _fake_item(
        "t1", "2021-06-01T00:00:00Z", 0, 0, 1.0,
        assets={"B04": "https://example/t1/B04.tif?sig=1",
                "SCL": "https://example/t1/SCL.tif?sig=2"},
    )
    selected = mpc._select_item_files(it, ["B04", "SCL", "B02"], str(tmp_path))
    assert selected == [
        ("https://example/t1/B04.tif?sig=1", str(tmp_path / "t1" / "B04.tif"), "B04"),
        ("https://example/t1/SCL.tif?sig=2", str(tmp_path / "t1" / "SCL.tif"), "SCL"),
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


# --- download (byte-copy + GDAL tag stamp, spec 34 §3) -----------------------


def _write_fake_cog(path, value=100, nodata=None):
    """A minimal real single-band uint16 GeoTIFF — stand-in for an MPC asset,
    so `stamp_or_reencode` (real GDAL open) has something valid to open."""
    import numpy as np
    import rasterio
    from rasterio.transform import from_origin

    with rasterio.open(
        str(path), "w", driver="GTiff", height=2, width=2, count=1,
        dtype="uint16", crs="EPSG:32633", transform=from_origin(0, 2, 1, 1),
        nodata=nodata,
    ) as dst:
        dst.write(np.full((1, 2, 2), value, dtype="uint16"))


def test_transfer_one_skips_existing_final(tmp_path):
    dst = tmp_path / "B04.tif"
    dst.write_bytes(b"already-here")
    ok, reason = mpc._transfer_and_stamp_one(
        "https://example/B04.tif", str(dst), band="B04", offset=0,
    )
    assert ok is True
    assert reason == "skipped"


def test_transfer_and_stamp_one_stamps_reflectance_offset_and_nodata(tmp_path, monkeypatch):
    dst = tmp_path / "B04.tif"

    def _fake_transfer(src_url, dst_url, **kw):
        _write_fake_cog(dst_url, value=1500)

    monkeypatch.setattr(mpc.fs, "transfer", _fake_transfer)
    ok, reason = mpc._transfer_and_stamp_one(
        "https://example/B04.tif", str(dst), band="B04", offset=-1000,
    )
    assert ok is True and reason == "ok"
    import rasterio

    with rasterio.open(str(dst)) as d:
        # reflectance-unit tag (spec 34 §1a): -1000 DN * 1/10000 -> -0.1, paired with
        # scale=1/10000 so unscale=true yields physical reflectance (not the black-tile
        # unit mismatch that stamped -1000 alongside scale=1/10000).
        assert d.offsets[0] == pytest.approx(-1000 * config.S2_REFLECTANCE_SCALE)
        assert d.scales[0] == pytest.approx(config.S2_REFLECTANCE_SCALE)
        assert d.nodata == 0  # stamped, was missing


def test_transfer_and_stamp_one_never_offsets_mask_band(tmp_path, monkeypatch):
    dst = tmp_path / "SCL.tif"

    def _fake_transfer(src_url, dst_url, **kw):
        _write_fake_cog(dst_url, value=4)

    monkeypatch.setattr(mpc.fs, "transfer", _fake_transfer)
    ok, _ = mpc._transfer_and_stamp_one(
        "https://example/SCL.tif", str(dst), band="SCL", offset=-1000,
    )
    assert ok is True
    import rasterio

    with rasterio.open(str(dst)) as d:
        assert d.offsets[0] == 0  # SCL is never radiometrically offset


def _reprocessing_pair_plus_control(cloud=5.0):
    """The real spec-32 runbook duplicate pair (fabricated generation_times
    matching the real 20220303/20240604 ordering) plus one distinct control
    item, all in the ROI used by these tests."""
    same_dt = "2022-03-01T10:00:29Z"
    original = _fake_item(
        "S2B_MSIL2A_20220301T100029_R122_T33UWP_20220303T182540", same_dt, 0.0, 0.0, cloud,
        mgrs_tile="T33UWP", generation_time="2022-03-03T18:25:40Z",
        assets={"B04": "https://example/orig/B04.tif?sig=1"},
    )
    reprocessed = _fake_item(
        "S2B_MSIL2A_20220301T100029_R122_T33UWP_20240604T180322", same_dt, 0.0, 0.0, cloud,
        mgrs_tile="T33UWP", generation_time="2024-06-04T18:03:22Z",
        assets={"B04": "https://example/reproc/B04.tif?sig=2"},
    )
    control = _fake_item(
        "control", "2022-06-01T00:00:00Z", 0.0, 0.0, cloud, mgrs_tile="T34UWA",
        assets={"B04": "https://example/control/B04.tif?sig=3"},
    )
    return [original, reprocessed, control]


def test_query_catalog_drops_the_duplicate(monkeypatch):
    items = _reprocessing_pair_plus_control()
    monkeypatch.setattr(mpc, "_search_items", lambda *a, **k: items)

    roi = gpd.GeoDataFrame(geometry=[sg.box(0.2, 0.2, 0.5, 0.5)], crs="EPSG:4326")
    gdf = mpc.query_catalog(roi, datetime.datetime(2021, 1, 1), datetime.datetime(2022, 12, 31))

    assert len(gdf) == 2
    assert set(gdf["id"]) == {
        "S2B_MSIL2A_20220301T100029_R122_T33UWP_20240604T180322", "control",
    }


def test_download_drops_the_duplicate_before_transfer(monkeypatch, tmp_path):
    items = _reprocessing_pair_plus_control()
    monkeypatch.setattr(mpc, "_search_items", lambda *a, **k: items)

    written = []

    def _fake_transfer(src_url, dst_url, **kw):
        written.append((src_url, dst_url))
        import os
        os.makedirs(os.path.dirname(dst_url), exist_ok=True)
        _write_fake_cog(dst_url)

    monkeypatch.setattr(mpc.fs, "transfer", _fake_transfer)

    from fsd.catalog.catalog import TileCatalog

    catalog = TileCatalog(str(tmp_path / "catalog.parquet"))
    roi = gpd.GeoDataFrame(geometry=[sg.box(0.2, 0.2, 0.5, 0.5)], crs="EPSG:4326")

    result = mpc.download(
        roi, datetime.datetime(2021, 1, 1), datetime.datetime(2022, 12, 31),
        ["B04"], str(tmp_path / "imagery"), catalog, max_tiles=10,
    )
    assert result.successful_count == 2  # winner + control, never the loser

    gdf = catalog.read()
    assert set(gdf["id"]) == {
        "S2B_MSIL2A_20220301T100029_R122_T33UWP_20240604T180322", "control",
    }
    # loser's asset href was never even queued for transfer
    written_srcs = {src for src, _ in written}
    assert "https://example/orig/B04.tif?sig=1" not in written_srcs
    assert "https://example/reproc/B04.tif?sig=2" in written_srcs
    assert "https://example/control/B04.tif?sig=3" in written_srcs


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
        _write_fake_cog(dst_url)

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
    offsets = dict(zip(gdf["id"], gdf["offset"]))
    assert offsets == {"pre": 0, "post": -1000}


def test_download_accepts_remote_root_and_stamps_via_local_scratch(tmp_path, monkeypatch):
    """spec 34 §3/§5: lifts spec 32's local-only guard — a remote (here,
    fsspec `memory://`, standing in for `abfss://`) root_folderpath must still
    get a stamped COG, staged through local scratch."""
    items = [
        _fake_item("t1", "2022-06-01T00:00:00Z", 0.0, 0.0, 5.0, baseline="04.00",
                   assets={"B04": "https://example/t1/B04.tif?sig=1"}),
    ]
    monkeypatch.setattr(mpc, "_search_items", lambda *a, **k: items)

    def _fake_transfer(src_url, dst_url, **kw):
        _write_fake_cog(dst_url, value=1500)

    monkeypatch.setattr(mpc.fs, "transfer", _fake_transfer)

    from fsd.catalog.catalog import TileCatalog

    catalog = TileCatalog(str(tmp_path / "catalog.parquet"))
    roi = gpd.GeoDataFrame(geometry=[sg.box(0.2, 0.2, 0.5, 0.5)], crs="EPSG:4326")
    remote_root = "memory://fsd-mpc-test/imagery"

    result = mpc.download(
        roi, datetime.datetime(2021, 1, 1), datetime.datetime(2022, 12, 31),
        ["B04"], remote_root, catalog, max_tiles=10,
    )
    assert result.successful_count == 1
    assert result.failed_count == 0

    import fsspec

    memfs = fsspec.filesystem("memory")
    assert memfs.exists("fsd-mpc-test/imagery/t1/B04.tif")


def test_gdal_tag_and_stac_raster_bands_agree(tmp_path, monkeypatch):
    """spec 34 §4: ingest writes offset/scale/nodata to **both** the COG's GDAL tag
    and STAC `raster:bands`, with equal values — the two declarations are written
    from the same source of truth, so a viewer reading the tag (`unscale=true`) and
    a tool reading the STAC item can never disagree.

    Drives the real ingest stamp (`mpc._transfer_and_stamp_one`) and the real STAC
    export (`stac.tile_catalog_to_items`) over the same declared offset, rather than
    asserting each side separately against a literal.
    """
    import geopandas as gpd
    import pandas as pd
    import rasterio
    import shapely.geometry

    from fsd.catalog import stac

    offset = -1000  # baseline >= 04.00
    dst = tmp_path / "B04.tif"

    def _fake_transfer(src_url, dst_url, **kw):
        _write_fake_cog(dst_url, value=1500)

    monkeypatch.setattr(mpc.fs, "transfer", _fake_transfer)
    ok, _ = mpc._transfer_and_stamp_one(
        "https://example/B04.tif", str(dst), band="B04", offset=offset,
    )
    assert ok is True

    row = {
        "id": "S2A_MSIL2A_20220601T075611_N0500_R035_T33UWP_20220601T120000",
        "satellite": "sentinel-2-l2a",
        "timestamp": pd.Timestamp("2022-06-01T07:56:11", tz="UTC"),
        "s3url": "", "local_folderpath": str(tmp_path), "files": "B04.tif",
        "cloud_cover": 0.0, "offset": offset, "nodata": 0,
        "geometry": shapely.geometry.box(15.0, 48.0, 15.4, 48.4),
    }
    item = stac.tile_catalog_to_items(
        gpd.GeoDataFrame([row], geometry="geometry", crs="EPSG:4326")
    )[0]
    stac_band = RasterExtension.ext(item.assets["B04"]).bands[0]

    with rasterio.open(str(dst)) as d:
        # both declarations carry the SAME reflectance-unit offset (-1000 DN * 1/10000
        # = -0.1), not the DN offset — so a viewer (GDAL tag) and a STAC reader agree
        # AND are unit-consistent with scale=1/10000 (spec 34 §1a).
        expected_refl_offset = offset * config.S2_REFLECTANCE_SCALE
        assert d.offsets[0] == pytest.approx(stac_band.offset)
        assert d.offsets[0] == pytest.approx(expected_refl_offset)
        assert d.scales[0] == pytest.approx(stac_band.scale)
        assert d.nodata == stac_band.nodata == 0


def test_stamped_tag_unscales_to_physical_reflectance_not_black(tmp_path, monkeypatch):
    """Regression for the black-tile bug found in runbook 34b (2026-07-20). The GDAL
    SCALE/OFFSET a viewer's `unscale=true` reads must be UNIT-CONSISTENT: unscale
    computes ``DN*scale + offset``, and with ``scale=1/10000`` (physical reflectance,
    spec 34 §1a) the stamped offset must be reflectance-unit too. The bug stamped the
    raw DN offset (-1000) alongside ``scale=1/10000``, so unscale gave
    ``1500/10000 - 1000 ~= -1000`` for *every* pixel → every tile rendered pure black.
    This asserts the actual unscale arithmetic, which the agreement test above cannot
    (both sides shared the same wrong value, so they agreed while both being wrong)."""
    import rasterio

    dst = tmp_path / "B04.tif"
    monkeypatch.setattr(mpc.fs, "transfer", lambda s, d, **k: _write_fake_cog(d, value=1500))
    ok, _ = mpc._transfer_and_stamp_one(
        "https://example/B04.tif", str(dst), band="B04", offset=-1000,
    )
    assert ok is True
    with rasterio.open(str(dst)) as d:
        unscaled = 1500 * d.scales[0] + d.offsets[0]   # what titiler unscale=true computes
        assert unscaled == pytest.approx((1500 - 1000) / 10000)   # 0.05 reflectance
        assert 0.0 <= unscaled <= 1.0                              # sane, NOT ~-1000 (black)


def test_stac_roundtrip_preserves_dn_offset_for_builder(tmp_path):
    """The catalog `offset` column is DN-unit (the builder applies it in DN space,
    `clip(DN + offset)`), but raster:bands stores it reflectance-unit (spec 34 §1a).
    A ``to_stac`` → ``items_to_rows`` round-trip must recover the DN offset (-1000), or
    a datacube built from a re-imported catalog would silently be ~1000 DN high — the
    exact #10/#30 failure spec 34 exists to close."""
    import geopandas as gpd
    import pandas as pd
    import shapely.geometry

    from fsd.catalog import stac

    row = {
        "id": "S2A_MSIL2A_20220601T075611_N0500_R035_T33UWP_20220601T120000",
        "satellite": "sentinel-2-l2a",
        "timestamp": pd.Timestamp("2022-06-01T07:56:11", tz="UTC"),
        "s3url": "", "local_folderpath": str(tmp_path), "files": "B04.tif",
        "cloud_cover": 0.0, "offset": -1000, "nodata": 0,
        "geometry": shapely.geometry.box(15.0, 48.0, 15.4, 48.4),
    }
    items = stac.tile_catalog_to_items(
        gpd.GeoDataFrame([row], geometry="geometry", crs="EPSG:4326")
    )
    back = stac.items_to_rows(items)
    assert back.iloc[0]["offset"] == pytest.approx(-1000)   # DN-unit recovered, not -0.1
