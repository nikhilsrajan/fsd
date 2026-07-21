"""Automated mirror of tests/manual/storage.md Section A (local backend).

Section B (S3-compatible transport) stays manual — it needs credentials and a
network endpoint. These exercise the fsspec seam end-to-end on the local backend:
the same code paths a remote backend uses, just with `file://`.
"""

import geopandas as gpd
import numpy as np
import shapely.geometry as sg

from fsd.storage import fs


def test_makedirs_and_exists(tmp_path):
    sub = tmp_path / "a/b/c"
    fs.makedirs(str(sub))
    assert fs.exists(str(sub))
    assert not fs.exists(str(tmp_path / "nope"))


def test_open_write_read_text(tmp_path):
    p = str(tmp_path / "hello.txt")
    with fs.open(p, "w") as f:
        f.write("hi fsd")
    with fs.open(p, "r") as f:
        assert f.read() == "hi fsd"
    assert fs.exists(p)


def test_save_load_npy_array(tmp_path):
    arr = np.arange(12).reshape(3, 4)
    p = str(tmp_path / "arr.npy")
    fs.save_npy(p, arr)
    out = fs.load_npy(p)
    assert out.shape == (3, 4)
    assert out.dtype == np.int64
    assert (out == arr).all()


def test_save_load_npy_pickled_metadata(tmp_path):
    # How datacube metadata.pickle.npy round-trips (note the [()] unwrap).
    meta = {"bands": ["B02", "B08"], "timestamps": 3}
    p = str(tmp_path / "meta.pickle.npy")
    fs.save_npy(p, meta, allow_pickle=True)
    loaded = fs.load_npy(p, allow_pickle=True)[()]
    assert loaded == meta


def test_write_read_geoparquet(tmp_path):
    # GeoParquet stores CRS as PROJJSON, so compare the EPSG code, not str(crs).
    gdf = gpd.GeoDataFrame(
        {"id": ["t1", "t2"]},
        geometry=[sg.Point(0, 0), sg.Point(1, 1)],
        crs="EPSG:4326",
    )
    p = str(tmp_path / "catalog.parquet")
    fs.write_parquet(p, gdf)
    back = fs.read_parquet(p)
    assert len(back) == 2
    assert back.crs.to_epsg() == 4326
    assert list(back["id"]) == ["t1", "t2"]
    assert back.geometry.iloc[0].wkt == "POINT (0 0)"


# --- .attrs footer preservation (spec 35 §2) ----------------------------------


def test_write_read_parquet_preserves_attrs(tmp_path):
    gdf = gpd.GeoDataFrame(
        {"id": ["t1"]}, geometry=[sg.Point(0, 0)], crs="EPSG:4326",
    )
    gdf.attrs["fsd:declaration"] = {"reference_band": "B04"}
    p = str(tmp_path / "catalog.parquet")
    fs.write_parquet(p, gdf)
    back = fs.read_parquet(p)
    assert back.attrs["fsd:declaration"] == {"reference_band": "B04"}


def test_read_parquet_stamps_source_path(tmp_path):
    gdf = gpd.GeoDataFrame({"id": ["t1"]}, geometry=[sg.Point(0, 0)], crs="EPSG:4326")
    p = str(tmp_path / "catalog.parquet")
    fs.write_parquet(p, gdf)
    back = fs.read_parquet(p)
    assert back.attrs[fs.SOURCE_PATH_ATTRS_KEY] == p


def test_write_parquet_strips_source_path_before_writing(tmp_path):
    """spec 35 §10: fsd:source_path is read-side bookkeeping -- it must never be
    serialized into a written artifact (it would leak a local absolute path)."""
    gdf = gpd.GeoDataFrame({"id": ["t1"]}, geometry=[sg.Point(0, 0)], crs="EPSG:4326")
    p1 = str(tmp_path / "a.parquet")
    fs.write_parquet(p1, gdf)
    read_back = fs.read_parquet(p1)
    assert fs.SOURCE_PATH_ATTRS_KEY in read_back.attrs

    p2 = str(tmp_path / "b.parquet")
    fs.write_parquet(p2, read_back)  # write what we just read back
    fresh = fs.read_parquet(p2)
    # p2's own read stamps fsd:source_path = p2 (not p1, and it must not have
    # been serialized as leftover data from read_back.attrs).
    assert fresh.attrs[fs.SOURCE_PATH_ATTRS_KEY] == p2
    assert fs.peek_parquet_attrs(p2) == {}  # nothing else got written to the footer


def test_write_parquet_empty_attrs_is_the_zero_cost_fast_path(tmp_path):
    """No PANDAS_ATTRS footer key at all when attrs is empty (spec 35 §8.5) --
    proves the fast path is byte-for-byte the pre-spec-35 write."""
    import pyarrow.parquet as pq

    gdf = gpd.GeoDataFrame({"id": ["t1"]}, geometry=[sg.Point(0, 0)], crs="EPSG:4326")
    p = str(tmp_path / "catalog.parquet")
    fs.write_parquet(p, gdf)
    with open(p, "rb") as f:
        metadata = pq.read_metadata(f)
    assert fs.PANDAS_ATTRS_FOOTER_KEY not in (metadata.metadata or {})


def test_stamped_file_is_still_valid_geoparquet(tmp_path):
    """spec 35 §8.3: a stamped file reads with stock gpd.read_parquet; the `geo`
    key survives; geometry/CRS are unaffected by the footer rewrite."""
    gdf = gpd.GeoDataFrame(
        {"id": ["t1", "t2"]},
        geometry=[sg.Point(0, 0), sg.Point(1, 1)],
        crs="EPSG:4326",
    )
    gdf.attrs["fsd:declaration"] = {"reference_band": "B04"}
    p = str(tmp_path / "catalog.parquet")
    fs.write_parquet(p, gdf)

    stock_back = gpd.read_parquet(p)  # stock geopandas, not fsd.storage.fs
    assert stock_back.crs.to_epsg() == 4326
    assert list(stock_back["id"]) == ["t1", "t2"]

    import pyarrow.parquet as pq

    with open(p, "rb") as f:
        metadata = pq.read_metadata(f)
    assert b"geo" in (metadata.metadata or {})

    fsd_back = fs.read_parquet(p)
    assert fsd_back.crs.to_epsg() == stock_back.crs.to_epsg()
    assert list(fsd_back.geometry) == list(stock_back.geometry)


def test_peek_parquet_attrs_footer_only(tmp_path):
    gdf = gpd.GeoDataFrame({"id": ["t1"]}, geometry=[sg.Point(0, 0)], crs="EPSG:4326")
    gdf.attrs["fsd:declaration"] = {"reference_band": "B04"}
    p = str(tmp_path / "catalog.parquet")
    fs.write_parquet(p, gdf)
    assert fs.peek_parquet_attrs(p) == {"fsd:declaration": {"reference_band": "B04"}}


def test_peek_parquet_attrs_on_a_non_local_filesystem():
    """`TileCatalog.append`'s conflict check reads the stamp through
    `peek_parquet_attrs` on every append — including against an `abfss://`
    catalog (the `rise` blob ingest). Pin that the footer-only read works on a
    non-local fsspec filesystem, not just a local path."""
    import uuid

    gdf = gpd.GeoDataFrame({"id": ["t1"]}, geometry=[sg.Point(0, 0)], crs="EPSG:4326")
    gdf.attrs["fsd:declaration"] = {"reference_band": "B04"}
    p = f"memory://{uuid.uuid4()}/catalog.parquet"
    fs.write_parquet(p, gdf)
    assert fs.peek_parquet_attrs(p) == {"fsd:declaration": {"reference_band": "B04"}}


def test_ls_and_glob(tmp_path):
    import os

    fs.save_npy(str(tmp_path / "arr.npy"), np.zeros(3))
    fs.save_npy(str(tmp_path / "meta.pickle.npy"), {"x": 1}, allow_pickle=True)
    with fs.open(str(tmp_path / "hello.txt"), "w") as f:
        f.write("hi")

    names = sorted(os.path.basename(x) for x in fs.ls(str(tmp_path)))
    assert {"arr.npy", "meta.pickle.npy", "hello.txt"}.issubset(set(names))

    npys = sorted(
        os.path.basename(x) for x in fs.glob(str(tmp_path / "*.npy"))
    )
    assert npys == ["arr.npy", "meta.pickle.npy"]


def test_put_get_transfer(tmp_path):
    arr = np.arange(12).reshape(3, 4)
    p_arr = str(tmp_path / "arr.npy")
    fs.save_npy(p_arr, arr)

    p_put = str(tmp_path / "uploaded/arr_copy.npy")
    fs.put(p_arr, p_put)
    assert fs.exists(p_put)

    p_get = str(tmp_path / "downloaded/arr_back.npy")
    fs.get(p_put, p_get)
    assert np.array_equal(fs.load_npy(p_get), arr)

    p_xfer = str(tmp_path / "transferred/arr_t.npy")
    fs.transfer(p_arr, p_xfer)
    assert np.array_equal(fs.load_npy(p_xfer), arr)


def test_transfer_is_atomic_on_failure(tmp_path, monkeypatch):
    """A transfer that fails mid-copy leaves NO file at the destination (no 0-byte or
    truncated leftover) and cleans up its .part sidecar."""
    import pytest

    src = tmp_path / "src.bin"
    src.write_bytes(b"x" * 100)
    dst = tmp_path / "out" / "dst.bin"

    class _Boom:
        @staticmethod
        def copyfileobj(a, b):
            raise OSError("connection reset mid-copy")

    monkeypatch.setattr(fs, "shutil", _Boom)
    with pytest.raises(OSError):
        fs.transfer(str(src), str(dst))
    assert not dst.exists()
    assert not (tmp_path / "out" / "dst.bin.part").exists()


def test_size(tmp_path):
    p = str(tmp_path / "f.bin")
    with open(p, "wb") as f:
        f.write(b"abc")
    assert fs.size(p) == 3
    empty = str(tmp_path / "e.bin")
    open(empty, "wb").close()
    assert fs.size(empty) == 0
