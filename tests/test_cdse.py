"""Tests for fsd.sources.cdse (spec 01).

Credential loading only (no network). Uses DUMMY values — never the real
secrets/cdse_credentials.json.
"""

import datetime
import json

import geopandas as gpd
import shapely.geometry as sg

from fsd.sources import cdse
from fsd.sources.cdse import CdseCredentials


def _stac_item(id, dt, lon, lat, cloud, safe=None):
    """A minimal STAC item shaped like a SH catalog search result."""
    return {
        "id": id,
        "properties": {"datetime": dt, "eo:cloud_cover": cloud},
        "assets": {"data": {"href": safe or f"s3://eodata/{id}.SAFE"}},
        "geometry": sg.mapping(sg.box(lon, lat, lon + 1, lat + 1)),
    }

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
        _stac_item("t1", "2018-06-30T09:57:22Z", 16.0, 48.0, 12.5),
        _stac_item("t2", "2018-07-05T09:57:22Z", 17.0, 48.0, 80.0),
    ]
    gdf = cdse._items_to_gdf(items)
    assert list(gdf["id"]) == ["t1", "t2"]
    assert list(gdf.columns) == ["id", "satellite", "timestamp", "s3url",
                                 "cloud_cover", "geometry"]
    assert gdf.crs.to_epsg() == 4326
    assert str(gdf["timestamp"].dt.tz) == "UTC"
    assert gdf["s3url"].iloc[0].startswith("s3://eodata/")
    assert gdf["satellite"].iloc[0] == "sentinel-2-l2a"


def test_finalize_filters_cloud_and_roi():
    items = [
        _stac_item("hit", "2018-06-30T00:00:00Z", 0.0, 0.0, 10.0),   # overlaps, clear
        _stac_item("cloudy", "2018-06-30T00:00:00Z", 0.0, 0.0, 90.0),  # overlaps, cloudy
        _stac_item("far", "2018-06-30T00:00:00Z", 50.0, 50.0, 5.0),  # no overlap
    ]
    gdf = cdse._items_to_gdf(items)
    roi = gpd.GeoDataFrame(geometry=[sg.box(0.2, 0.2, 0.5, 0.5)], crs="EPSG:4326")
    out = cdse._finalize_catalog_gdf(gdf, roi, max_cloudcover=50.0)
    assert list(out["id"]) == ["hit"]


def test_finalize_raises_on_duplicate_ids():
    items = [
        _stac_item("dup", "2018-06-30T00:00:00Z", 0.0, 0.0, 10.0),
        _stac_item("dup", "2018-07-01T00:00:00Z", 0.0, 0.0, 10.0),
    ]
    gdf = cdse._items_to_gdf(items)
    roi = gpd.GeoDataFrame(geometry=[sg.box(0.2, 0.2, 0.5, 0.5)], crs="EPSG:4326")
    import pytest

    with pytest.raises(ValueError):
        cdse._finalize_catalog_gdf(gdf, roi, max_cloudcover=None)


def test_roi_to_bbox_reprojects_to_wgs84():
    # a UTM (metres) ROI should come back as a WGS84 bbox
    roi = gpd.GeoDataFrame(
        geometry=[sg.box(500000, 5300000, 510000, 5310000)], crs="EPSG:32633"
    )
    bbox = cdse._roi_to_bbox(roi)
    import sentinelhub

    assert bbox.crs == sentinelhub.CRS.WGS84
    # zone-33 easting ~500000 is around 15°E
    assert 14 < bbox.min_x < 16


def test_query_catalog_requires_sh_creds():
    import pytest

    roi = gpd.GeoDataFrame(geometry=[sg.box(0, 0, 1, 1)], crs="EPSG:4326")
    with pytest.raises(ValueError):
        cdse.query_catalog(roi, datetime.datetime(2018, 1, 1),
                           datetime.datetime(2018, 12, 31),
                           CdseCredentials(s3_access_key="only-s3"))
