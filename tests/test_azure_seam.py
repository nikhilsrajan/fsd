"""Spec 31 (P1 Azure compute seam) — synthetic/local only, no credentials, no network.

Covers: `to_vsi` translation, the `storage=` config seam (env + `fsspec.config.conf`),
the config-seam facts pinned against the installed adlfs/fsspec (`[azure]` extra —
skips if not installed), `storage_token` (mocked credential), `rio_open` routing
(mocked `rasterio.open`), a `memory://` scheme-routing round-trip, and the
`os.path.join` URL-safety claim §2/§6 relies on.
"""

from __future__ import annotations

import os
import sys
import types

import fsspec
import pytest

from fsd.storage import azure as fsd_azure
from fsd.storage.fs import to_vsi

pytest_adlfs = pytest.importorskip("adlfs", reason="needs the [azure] extra (adlfs)")


# --- to_vsi --------------------------------------------------------------------


def test_to_vsi_abfss_translates():
    assert (
        to_vsi("abfss://fs@acct.dfs.core.windows.net/a/b.tif")
        == "/vsiadls/fs/a/b.tif"
    )


def test_to_vsi_local_passthrough():
    assert to_vsi("/local/a/b.tif") == "/local/a/b.tif"
    assert to_vsi("file:///local/a/b.tif") == "file:///local/a/b.tif"


def test_to_vsi_az_alias():
    assert to_vsi("az://fs/a/b.tif") == "/vsiadls/fs/a/b.tif"


def test_to_vsi_account_extractable():
    assert fsd_azure.account_from_url("abfss://fs@acct.dfs.core.windows.net/a/b.tif") == "acct"
    assert fsd_azure.account_from_url("/local/a/b.tif") is None
    assert fsd_azure.account_from_url("az://fs/a/b.tif") is None


def test_to_vsi_malformed_abfss_raises():
    with pytest.raises(ValueError):
        to_vsi("abfss://not-a-real-host/a/b.tif")


def test_to_vsi_malformed_az_raises():
    with pytest.raises(ValueError):
        to_vsi("az://missing-path")


# --- storage= config seam -------------------------------------------------------


@pytest.fixture()
def _clean_fsspec_conf(monkeypatch):
    """`fsspec.config.conf` is process-global — snapshot + restore around each test."""
    before = {k: dict(v) for k, v in fsspec.config.conf.items()}
    before_env = os.environ.get("FSSPEC_ABFSS_ANON")
    yield
    fsspec.config.conf.clear()
    fsspec.config.conf.update(before)
    if before_env is None:
        os.environ.pop("FSSPEC_ABFSS_ANON", None)
    else:
        os.environ["FSSPEC_ABFSS_ANON"] = before_env


def test_configure_storage_azure_string_sets_env_and_conf(_clean_fsspec_conf):
    fsd_azure.configure_storage("azure")
    assert os.environ["FSSPEC_ABFSS_ANON"] == "false"
    assert fsspec.config.conf["abfss"]["anon"] is False


def test_configure_storage_azure_dict_form(_clean_fsspec_conf):
    fsd_azure.configure_storage({"backend": "azure"})
    assert os.environ["FSSPEC_ABFSS_ANON"] == "false"
    assert fsspec.config.conf["abfss"]["anon"] is False


def test_configure_storage_none_is_noop(_clean_fsspec_conf):
    os.environ.pop("FSSPEC_ABFSS_ANON", None)
    fsd_azure.configure_storage(None)
    assert "FSSPEC_ABFSS_ANON" not in os.environ
    assert "abfss" not in fsspec.config.conf


def test_configure_storage_bad_backend_raises(_clean_fsspec_conf):
    with pytest.raises(ValueError):
        fsd_azure.configure_storage("s3")
    with pytest.raises(ValueError):
        fsd_azure.configure_storage({"backend": "gcs"})


def test_api_storage_local_or_none_leaves_env_unset(tmp_path, monkeypatch):
    """`storage="local"`/`None` on a verb must not touch FSSPEC_ABFSS_*."""
    monkeypatch.delenv("FSSPEC_ABFSS_ANON", raising=False)
    from fsd import api

    assert api._check_local_seams("local", None) == []
    assert api._check_local_seams("local", "local") == []
    assert "FSSPEC_ABFSS_ANON" not in os.environ


def test_configure_storage_local_string_is_noop(_clean_fsspec_conf):
    os.environ.pop("FSSPEC_ABFSS_ANON", None)
    fsd_azure.configure_storage("local")
    assert "FSSPEC_ABFSS_ANON" not in os.environ
    assert "abfss" not in fsspec.config.conf


def test_api_check_local_seams_accepts_azure_storage():
    from fsd import api

    assert api._check_local_seams("local", "azure") == []
    assert api._check_local_seams("local", {"backend": "azure"}) == []


def test_api_check_local_seams_rejects_bad_backend():
    from fsd import api

    errs = api._check_local_seams("local", "s3")
    assert errs and "s3" in errs[0]


def test_api_check_local_seams_runner_still_rejected():
    from fsd import api

    errs = api._check_local_seams("batch", None)
    assert errs and "batch" in errs[0]


def test_api_check_local_seams_storage_allowed_false_rejects_azure():
    """run_inference/deploy pass storage_allowed=False — inference-on-blob stays out of P1."""
    from fsd import api

    errs = api._check_local_seams("local", "azure", storage_allowed=False)
    assert errs and "not supported here yet" in errs[0]


# --- config-seam facts (pins the library behavior spec 31 §1 relies on) --------


def test_azureblobfilesystem_protocol_covers_all_three_schemes():
    from adlfs import AzureBlobFileSystem

    assert AzureBlobFileSystem.protocol == ("abfs", "az", "abfss")


def test_apply_config_one_key_covers_the_class():
    from adlfs import AzureBlobFileSystem
    from fsspec.config import apply_config

    out = apply_config(AzureBlobFileSystem, {}, {"abfss": {"anon": False}})
    assert out == {"anon": False}


def test_get_kwargs_from_urls_extracts_account():
    from adlfs import AzureBlobFileSystem

    kw = AzureBlobFileSystem._get_kwargs_from_urls(
        "abfss://data@acct.dfs.core.windows.net/p/x.tif"
    )
    assert kw == {"account_name": "acct"}


# --- storage_token ---------------------------------------------------------------


def test_storage_token_reuses_one_credential_instance(monkeypatch):
    constructed = []

    class _FakeCredential:
        def __init__(self):
            constructed.append(self)

        def get_token(self, scope):
            assert scope == "https://storage.azure.com/.default"
            return types.SimpleNamespace(token="fake-token-123")

    fake_identity_mod = types.ModuleType("azure.identity")
    fake_identity_mod.DefaultAzureCredential = _FakeCredential
    fake_azure_pkg = types.ModuleType("azure")
    monkeypatch.setitem(sys.modules, "azure", fake_azure_pkg)
    monkeypatch.setitem(sys.modules, "azure.identity", fake_identity_mod)
    monkeypatch.setattr(fsd_azure, "_credential", None)

    t1 = fsd_azure.storage_token()
    t2 = fsd_azure.storage_token()

    assert t1 == t2 == "fake-token-123"
    assert len(constructed) == 1  # one credential instance, reused


# --- rio_open routing --------------------------------------------------------------


def test_rio_open_local_path_is_plain_passthrough(monkeypatch):
    from fsd import raster

    calls = []

    def fake_open(path, mode="r", **kw):
        calls.append((path, mode, kw))
        return "SENTINEL_DATASET"

    monkeypatch.setattr(raster.rasterio, "open", fake_open)
    result = raster.rio_open("/local/a.tif")

    assert result == "SENTINEL_DATASET"
    assert calls == [("/local/a.tif", "r", {})]


def test_rio_open_remote_path_translates_and_uses_env(monkeypatch):
    from fsd import raster

    calls = []
    env_calls = []

    class _FakeDataset:
        def close(self):
            pass

    def fake_open(path, mode="r", **kw):
        calls.append((path, mode, kw))
        return _FakeDataset()

    class _FakeEnv:
        def __init__(self, **kw):
            env_calls.append(kw)

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(raster.rasterio, "open", fake_open)
    monkeypatch.setattr(raster.rasterio, "Env", _FakeEnv)
    monkeypatch.setattr(raster, "storage_token", lambda: "tok-abc")

    src = raster.rio_open("abfss://data@acct.dfs.core.windows.net/p/x.tif")

    assert calls == [("/vsiadls/data/p/x.tif", "r", {})]
    assert env_calls == [
        {"AZURE_STORAGE_ACCESS_TOKEN": "tok-abc", "AZURE_STORAGE_ACCOUNT": "acct"}
    ]
    src.close()


def test_rio_open_write_mode_on_remote_raises():
    from fsd import raster

    with pytest.raises(ValueError):
        raster.rio_open("abfss://data@acct.dfs.core.windows.net/p/x.tif", mode="w")


# --- memory:// round-trip (proves scheme-routing without Azure) ------------------


def test_memory_scheme_roundtrip_parquet_and_npy():
    import geopandas as gpd
    import numpy as np
    import shapely.geometry as sg

    from fsd.storage import fs

    gdf = gpd.GeoDataFrame({"id": ["a"]}, geometry=[sg.Point(0, 0)], crs="EPSG:4326")
    fs.write_parquet("memory://cat/catalog.parquet", gdf)
    back = fs.read_parquet("memory://cat/catalog.parquet")
    assert list(back["id"]) == ["a"]

    arr = np.arange(6).reshape(2, 3)
    fs.save_npy("memory://cat/arr.npy", arr)
    out = fs.load_npy("memory://cat/arr.npy")
    assert (out == arr).all()


# --- os.path.join URL-safety (§2/§6, pinned) -------------------------------------


def test_os_path_join_is_url_safe_on_abfss():
    joined = os.path.join("abfss://fs@acct.dfs.core.windows.net/a", "b.tif")
    assert joined == "abfss://fs@acct.dfs.core.windows.net/a/b.tif"
