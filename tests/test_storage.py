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
