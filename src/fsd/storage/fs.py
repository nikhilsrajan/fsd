"""fsspec-based storage seam + first-class S3-compatible transport.

Spec: specs/10-storage-and-scale.md

Rule: no other module in fsd opens files directly. Everything (catalog, tiles,
datacubes, training arrays) reads/writes through here, so local -> Azure Blob / S3
is a config change, not a code change.

Any S3-compatible store (AWS, CDSE EODATA, MinIO, ...) is just an s3fs filesystem
distinguished by `endpoint_url` + keys passed via `storage_options`. A tile
download is therefore `transfer(src_s3_url, dst_url)` -- a copy between fsspec
filesystems.

`path` everywhere may be a plain local path or an fsspec URL
(`file://`, `s3://`, `az://`, ...). `storage_options` are backend kwargs, e.g.
for CDSE S3:
    {"key": access, "secret": secret,
     "client_kwargs": {"endpoint_url": config.CDSE_S3_ENDPOINT_URL}}
"""

from __future__ import annotations

import io
import os
import shutil
from typing import Any

import fsspec
import numpy as np

__all__ = [
    "open",
    "exists",
    "makedirs",
    "put",
    "get",
    "ls",
    "glob",
    "save_npy",
    "load_npy",
    "read_parquet",
    "write_parquet",
    "transfer",
]


# --- internal helpers --------------------------------------------------------


def _fs_and_path(url: str, storage_options: dict | None = None):
    """Resolve a URL/path to (filesystem, path-on-that-filesystem)."""
    return fsspec.core.url_to_fs(url, **(storage_options or {}))


def _ensure_parent(fs, path: str) -> None:
    """Best-effort create of the parent directory (no-op on object stores)."""
    parent = path.rsplit("/", 1)[0] if "/" in path else ""
    if parent and parent != path:
        try:
            fs.makedirs(parent, exist_ok=True)
        except Exception:
            # Object stores have no real directories; ignore.
            pass


# --- generic I/O -------------------------------------------------------------


def open(path: str, mode: str = "rb", **storage_options: Any):
    """Open a file on any fsspec backend. Returns a context manager.

    >>> with open("out.txt", "w") as f: f.write("hi")
    """
    return fsspec.open(path, mode, **storage_options)


def exists(path: str, **storage_options: Any) -> bool:
    fs, p = _fs_and_path(path, storage_options)
    return fs.exists(p)


def makedirs(path: str, exist_ok: bool = True, **storage_options: Any) -> None:
    fs, p = _fs_and_path(path, storage_options)
    fs.makedirs(p, exist_ok=exist_ok)


def put(local_path: str, remote_path: str, **storage_options: Any) -> None:
    """Upload a local file to a (possibly remote) destination."""
    fs, rpath = _fs_and_path(remote_path, storage_options)
    _ensure_parent(fs, rpath)
    fs.put_file(local_path, rpath)


def get(remote_path: str, local_path: str, **storage_options: Any) -> None:
    """Download a (possibly remote) file to local disk.

    Needed because some tools (rasterio/GDAL) want a real local path rather than
    an fsspec handle.
    """
    fs, rpath = _fs_and_path(remote_path, storage_options)
    parent = os.path.dirname(local_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    fs.get_file(rpath, local_path)


def ls(url: str, **storage_options: Any) -> list[str]:
    fs, p = _fs_and_path(url, storage_options)
    return fs.ls(p, detail=False)


def glob(pattern: str, **storage_options: Any) -> list[str]:
    fs, p = _fs_and_path(pattern, storage_options)
    return fs.glob(p)


# --- typed helpers -----------------------------------------------------------


def save_npy(
    path: str, arr, allow_pickle: bool = False, **storage_options: Any
) -> None:
    """Save a numpy array (or pickled object, if allow_pickle) to `path`.

    `path` must include the `.npy` extension (numpy does not append one when
    writing to a file object).
    """
    fs, p = _fs_and_path(path, storage_options)
    _ensure_parent(fs, p)
    with fs.open(p, "wb") as f:
        np.save(f, arr, allow_pickle=allow_pickle)


def load_npy(path: str, allow_pickle: bool = False, **storage_options: Any):
    """Load a `.npy` file. For a pickled object saved as a 0-d array, the caller
    extracts it with `[()]` (kept explicit to avoid surprising unwrapping)."""
    fs, p = _fs_and_path(path, storage_options)
    with fs.open(p, "rb") as f:
        return np.load(io.BytesIO(f.read()), allow_pickle=allow_pickle)


def read_parquet(path: str, **storage_options: Any):
    """Read a (Geo)Parquet file -> GeoDataFrame."""
    import geopandas as gpd

    fs, p = _fs_and_path(path, storage_options)
    with fs.open(p, "rb") as f:
        return gpd.read_parquet(io.BytesIO(f.read()))


def write_parquet(path: str, df, **storage_options: Any) -> None:
    """Write a (Geo)DataFrame to `path` as (Geo)Parquet."""
    fs, p = _fs_and_path(path, storage_options)
    _ensure_parent(fs, p)
    buf = io.BytesIO()
    df.to_parquet(buf)
    with fs.open(p, "wb") as f:
        f.write(buf.getvalue())


# --- first-class S3-compatible transport -------------------------------------


def transfer(
    src_url: str,
    dst_url: str,
    *,
    src_options: dict | None = None,
    dst_options: dict | None = None,
    njobs: int = 1,  # reserved for future directory/bulk transfers
) -> None:
    """Copy one object between fsspec filesystems (provider-agnostic).

    A satellite tile band file download is `transfer(s3_src, local_or_blob_dst)`.
    `src_url` may be an S3-compatible store configured via `src_options`, e.g. CDSE
    EODATA: ``{"key": ..., "secret": ...,
    "client_kwargs": {"endpoint_url": config.CDSE_S3_ENDPOINT_URL}}``.

    Streams bytes, so it works across different backends (e.g. CDSE S3 -> Azure
    Blob) without a common-filesystem assumption.
    """
    src_fs, spath = _fs_and_path(src_url, src_options)
    dst_fs, dpath = _fs_and_path(dst_url, dst_options)
    _ensure_parent(dst_fs, dpath)
    with src_fs.open(spath, "rb") as fsrc, dst_fs.open(dpath, "wb") as fdst:
        shutil.copyfileobj(fsrc, fdst)
