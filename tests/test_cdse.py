"""Tests for fsd.sources.cdse (spec 01).

Credential loading only (no network). Uses DUMMY values — never the real
secrets/cdse_credentials.json.
"""

import datetime
import json
import types

import geopandas as gpd
import shapely.geometry as sg

from fsd.sources import cdse
from fsd.sources.cdse import CdseCredentials


class _FakeItem:
    """Duck-typed stand-in for a pystac `Item` (no network)."""

    def __init__(self, id, dt, geom, cloud, assets):
        self.id = id
        self.datetime = dt
        self.geometry = sg.mapping(geom)
        self.properties = {"eo:cloud_cover": cloud}
        self.assets = {k: types.SimpleNamespace(href=v) for k, v in assets.items()}


def _fake_item(id, dt, lon, lat, cloud, safe=None, assets=None):
    """A STAC item over box (lon,lat)-(lon+1,lat+1); default asset is one B02 href."""
    safe = safe or f"s3://eodata/{id}.SAFE"
    if assets is None:
        assets = {"B02_10m": f"{safe}/GRANULE/G/IMG_DATA/R10m/T_D_B02_10m.jp2"}
    dt = datetime.datetime.fromisoformat(dt.replace("Z", "+00:00"))
    return _FakeItem(id, dt, sg.box(lon, lat, lon + 1, lat + 1), cloud, assets)

# DUMMY = legacy JSON-key form; DUMMY_FIELDS = the dataclass field form of the same.
DUMMY = {
    "sh_clientid": "id-123",
    "sh_clientsecret": "secret-abc",
    "s3_access_key": "akia-xyz",
    "s3_secret_key": "s3secret-789",
}
DUMMY_FIELDS = {
    "sh_client_id": "id-123",
    "sh_client_secret": "secret-abc",
    "s3_access_key": "akia-xyz",
    "s3_secret_key": "s3secret-789",
}


def test_from_json_reads_legacy_keys(tmp_path):
    p = tmp_path / "cdse_credentials.json"
    p.write_text(json.dumps(DUMMY))
    creds = CdseCredentials.from_json(str(p))
    assert creds.sh_client_id == "id-123"
    assert creds.sh_client_secret == "secret-abc"
    assert creds.s3_access_key == "akia-xyz"
    assert creds.s3_secret_key == "s3secret-789"


def test_from_json_tolerates_extra_and_optional_keys(tmp_path):
    p = tmp_path / "c.json"
    p.write_text(json.dumps({**DUMMY, "s3_keys_expire": "2026-08-01",
                             "note": "rotate soon", "unknown": "ignored"}))
    creds = CdseCredentials.from_json(str(p))
    assert creds.s3_keys_expire == "2026-08-01"
    assert creds.note == "rotate soon"


def test_to_json_round_trip(tmp_path):
    p = tmp_path / "out.json"
    original = CdseCredentials(**{
        "sh_client_id": "id-123", "sh_client_secret": "secret-abc",
        "s3_access_key": "akia-xyz", "s3_secret_key": "s3secret-789",
        "s3_keys_expire": "2026-08-01", "note": "hi",
    })
    original.to_json(str(p))
    # written in legacy key format
    on_disk = json.loads(p.read_text())
    assert set(["sh_clientid", "sh_clientsecret", "s3_access_key", "s3_secret_key"]) \
        <= set(on_disk)
    # and reads back equal
    assert CdseCredentials.from_json(str(p)) == original


def test_from_env():
    env = {
        "CDSE_SH_CLIENT_ID": "id-123",
        "CDSE_SH_CLIENT_SECRET": "secret-abc",
        "CDSE_S3_ACCESS_KEY": "akia-xyz",
        "CDSE_S3_SECRET_KEY": "s3secret-789",
        "CDSE_S3_KEYS_EXPIRE": "2026-08-01",
    }
    creds = CdseCredentials.from_env(env)
    assert creds.s3_access_key == "akia-xyz"
    assert creds.s3_keys_expire == "2026-08-01"


def test_repr_masks_secrets():
    creds = CdseCredentials(**DUMMY_FIELDS)
    r = repr(creds)
    # no secret value leaks into the repr
    for v in ("id-123", "secret-abc", "akia-xyz", "s3secret-789"):
        assert v not in r
    assert "set" in r  # shows presence, not value


def test_s3_storage_options_shape():
    creds = CdseCredentials(**DUMMY_FIELDS)
    opts = creds.s3_storage_options()
    assert opts["key"] == "akia-xyz"
    assert opts["secret"] == "s3secret-789"
    assert "endpoint_url" in opts["client_kwargs"]


def test_require_complete():
    import pytest

    CdseCredentials(**DUMMY_FIELDS).require_complete()  # no raise
    with pytest.raises(ValueError):
        CdseCredentials(sh_client_id="only-one").require_complete()


def test_is_expired():
    assert CdseCredentials().is_expired() is None  # unknown
    past = CdseCredentials(s3_keys_expire="2020-01-01")
    future = CdseCredentials(s3_keys_expire="2999-01-01")
    ref = datetime.date(2026, 7, 1)
    assert past.is_expired(as_of=ref) is True
    assert future.is_expired(as_of=ref) is False


# --- query_catalog pure helpers (no network) ---------------------------------


def test_items_to_gdf_parses_stac():
    items = [
        _fake_item("t1", "2018-06-30T09:57:22Z", 16.0, 48.0, 12.5),
        _fake_item("t2", "2018-07-05T09:57:22Z", 17.0, 48.0, 80.0),
    ]
    gdf = cdse._items_to_gdf(items)
    assert list(gdf["id"]) == ["t1", "t2"]
    assert list(gdf.columns) == ["id", "satellite", "timestamp", "s3url",
                                 "cloud_cover", "geometry"]
    assert gdf.crs.to_epsg() == 4326
    assert str(gdf["timestamp"].dt.tz) == "UTC"
    assert gdf["s3url"].iloc[0].startswith("s3://eodata/")
    assert gdf["s3url"].iloc[0].endswith(".SAFE")  # derived from an asset href
    assert gdf["satellite"].iloc[0] == "sentinel-2-l2a"


def test_safe_root_from_item_derives_from_asset_href():
    it = _fake_item(
        "x", "2018-06-30T00:00:00Z", 0, 0, 1.0,
        safe="s3://eodata/Sentinel-2/MSI/L2A_N0500/2018/01/30/S2A_X.SAFE",
    )
    assert cdse._safe_root_from_item(it) == (
        "s3://eodata/Sentinel-2/MSI/L2A_N0500/2018/01/30/S2A_X.SAFE"
    )


def test_finalize_filters_cloud_and_roi():
    items = [
        _fake_item("hit", "2018-06-30T00:00:00Z", 0.0, 0.0, 10.0),   # overlaps, clear
        _fake_item("cloudy", "2018-06-30T00:00:00Z", 0.0, 0.0, 90.0),  # overlaps, cloudy
        _fake_item("far", "2018-06-30T00:00:00Z", 50.0, 50.0, 5.0),  # no overlap
    ]
    gdf = cdse._items_to_gdf(items)
    roi = gpd.GeoDataFrame(geometry=[sg.box(0.2, 0.2, 0.5, 0.5)], crs="EPSG:4326")
    out = cdse._finalize_catalog_gdf(gdf, roi, max_cloudcover=50.0)
    assert list(out["id"]) == ["hit"]


def test_finalize_raises_on_duplicate_ids():
    items = [
        _fake_item("dup", "2018-06-30T00:00:00Z", 0.0, 0.0, 10.0),
        _fake_item("dup", "2018-07-01T00:00:00Z", 0.0, 0.0, 10.0),
    ]
    gdf = cdse._items_to_gdf(items)
    roi = gpd.GeoDataFrame(geometry=[sg.box(0.2, 0.2, 0.5, 0.5)], crs="EPSG:4326")
    import pytest

    with pytest.raises(ValueError):
        cdse._finalize_catalog_gdf(gdf, roi, max_cloudcover=None)


def test_require_s3():
    import pytest

    CdseCredentials(**DUMMY_FIELDS).require_s3()  # no raise
    # SH-only creds are fine for discovery but must fail the download S3 check
    with pytest.raises(ValueError):
        CdseCredentials(sh_client_id="only-sh").require_s3()


# --- download helpers --------------------------------------------------------

SAFE = ("s3://eodata/Sentinel-2/MSI/L2A_N0500/2018/01/30/"
        "S2A_MSIL2A_20180130T080151_N0500_R035_T36PZT_20230915T000622.SAFE")


def test_download_folderpath_strips_prefix_and_safe():
    out = cdse._download_folderpath(SAFE, "/data/root")
    assert out == ("/data/root/Sentinel-2/MSI/L2A_N0500/2018/01/30/"
                   "S2A_MSIL2A_20180130T080151_N0500_R035_T36PZT_20230915T000622")


def test_download_folderpath_rejects_bad_url():
    import pytest

    with pytest.raises(ValueError):
        cdse._download_folderpath("s3://other-bucket/x.SAFE", "/data")


def test_select_item_files_picks_highest_res_and_xml():
    granule = f"{SAFE}/GRANULE/L2A_T36PZT_A013_20180130T080151"
    it = _fake_item(
        "S2A_T36PZT", "2018-01-30T08:00:00Z", 36.0, 11.0, 5.0, safe=SAFE,
        assets={
            # B02 only at 10m; B05 at both 20m and 60m -> keep 20m
            "B02_10m": f"{granule}/IMG_DATA/R10m/T36PZT_20180130T080151_B02_10m.jp2",
            "B05_20m": f"{granule}/IMG_DATA/R20m/T36PZT_20180130T080151_B05_20m.jp2",
            "B05_60m": f"{granule}/IMG_DATA/R60m/T36PZT_20180130T080151_B05_60m.jp2",
            # a band we didn't request
            "B03_10m": f"{granule}/IMG_DATA/R10m/T36PZT_20180130T080151_B03_10m.jp2",
            "granule_metadata": f"{granule}/MTD_TL.xml",
        },
    )

    selected = cdse._select_item_files(it, ["B02", "B05"], "/root")
    dsts = {dst for _, dst in selected}
    folder = ("/root/Sentinel-2/MSI/L2A_N0500/2018/01/30/"
              "S2A_MSIL2A_20180130T080151_N0500_R035_T36PZT_20230915T000622")
    assert dsts == {f"{folder}/B02.jp2", f"{folder}/B05.jp2", f"{folder}/MTD_TL.xml"}
    # highest-res B05 is the 20m source, not 60m
    b05_src = next(src for src, dst in selected if dst.endswith("B05.jp2"))
    assert "R20m" in b05_src and b05_src.startswith("s3://")


def test_error_reason_maps_known_codes():
    assert cdse._error_reason(Exception("boom SignatureDoesNotMatch x")) == \
        "SignatureDoesNotMatch"
    assert cdse._error_reason(PermissionError("Forbidden")) == "Forbidden"
    assert cdse._error_reason(ValueError("weird")) == "ValueError"


def test_download_one_skips_and_reports_reason(monkeypatch, tmp_path):
    import os

    monkeypatch.setattr(cdse.fs, "exists", lambda p, **k: os.path.exists(p))
    existing = tmp_path / "x.jp2"
    existing.write_bytes(b"data")
    assert cdse._download_one("s3://eodata/a.jp2", str(existing), {}) == (True, "skipped")

    def boom(src, dst, **kw):
        raise PermissionError("An error occurred (Forbidden) ...")

    monkeypatch.setattr(cdse.fs, "transfer", boom)
    ok, reason = cdse._download_one(
        "s3://eodata/b.jp2", str(tmp_path / "nope.jp2"), {}, tries=1
    )
    assert (ok, reason) == (False, "Forbidden")
    assert "Forbidden" in cdse._RETRYABLE_S3  # 403 is transient on CDSE (BUG-001)


def test_download_raises_when_over_max_tiles(monkeypatch, tmp_path):
    import pytest

    from fsd.catalog.catalog import TileCatalog

    # 3 fake items overlapping the ROI, max_tiles=2 -> raise before any download
    items = [_fake_item(i, "2018-01-01T00:00:00Z", 0.0, 0.0, 0.0) for i in "abc"]
    monkeypatch.setattr(cdse, "_search_items", lambda *a, **k: items)
    roi = gpd.GeoDataFrame(geometry=[sg.box(0.2, 0.2, 0.5, 0.5)], crs="EPSG:4326")
    cat = TileCatalog(str(tmp_path / "c.parquet"))
    with pytest.raises(ValueError, match="exceed max_tiles"):
        cdse.download(roi, datetime.datetime(2018, 1, 1),
                      datetime.datetime(2018, 2, 1), ["B02"], str(tmp_path),
                      cat, CdseCredentials(**DUMMY_FIELDS), max_tiles=2)


def test_download_end_to_end_mocked(monkeypatch, tmp_path):
    """Full download flow with storage mocked — no network, real catalog write."""
    from fsd.catalog.catalog import TileCatalog

    item = _fake_item("S2A_T36PZT", "2018-01-30T08:00:00Z", 36.0, 11.0, 5.0, safe=SAFE)
    monkeypatch.setattr(cdse, "_search_items", lambda *a, **k: [item])
    monkeypatch.setattr(
        cdse, "_select_item_files",
        lambda it, bands, root: [
            (f"{cdse._safe_root_from_item(it)}/B02.jp2", str(tmp_path / "tile/B02.jp2")),
            (f"{cdse._safe_root_from_item(it)}/SCL.jp2", str(tmp_path / "tile/SCL.jp2")),
        ],
    )
    # "transfer" just creates the destination file
    def fake_transfer(src, dst, **kw):
        import os
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        open(dst, "wb").close()
    monkeypatch.setattr(cdse.fs, "transfer", fake_transfer)
    monkeypatch.setattr(cdse.fs, "exists", lambda p, **k: __import__("os").path.exists(p))

    roi = gpd.GeoDataFrame(geometry=[sg.box(36.0, 11.0, 37.0, 12.0)], crs="EPSG:4326")
    cat = TileCatalog(str(tmp_path / "c.parquet"))
    result = cdse.download(roi, datetime.datetime(2018, 1, 1),
                           datetime.datetime(2018, 2, 1), ["B02", "SCL"],
                           str(tmp_path), cat, CdseCredentials(**DUMMY_FIELDS),
                           max_tiles=10)
    assert (result.successful_count, result.total_count) == (2, 2)
    assert (result.failed_count, result.skipped_count) == (0, 0)
    assert result.reason_counts == {"ok": 2}
    gdf = cat.read()
    assert len(gdf) == 1
    assert gdf["files"].iloc[0] == "B02.jp2,SCL.jp2"  # unioned + sorted
