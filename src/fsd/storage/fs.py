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
import json
import os
import shutil
from typing import Any

import fsspec
import numpy as np

from fsd.storage.azure import to_vsi

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
    "peek_parquet_attrs",
    "rename",
    "transfer",
    "to_vsi",
    "is_local",
    "SOURCE_PATH_ATTRS_KEY",
]

# spec 35 §2/§5a. `PANDAS_ATTRS_FOOTER_KEY` is the upstream pandas/geopandas
# convention (pandas issue #54321, geopandas PR #3597) that `.attrs` is
# JSON-encoded under -- reusing it means fsd converges with a future geopandas
# release instead of forking a second convention (spec 35 §2).
PANDAS_ATTRS_FOOTER_KEY = b"PANDAS_ATTRS"

# `read_parquet` stamps this onto the returned `.attrs` so downstream code can
# tell "read from a file" apart from "hand-built in this process" (spec 35 §5a).
# It is bookkeeping, not data: `write_parquet` always strips it before writing
# (spec 35 §10), so it never leaks an absolute local path into a written artifact.
SOURCE_PATH_ATTRS_KEY = "fsd:source_path"


# --- internal helpers --------------------------------------------------------


def _fs_and_path(url: str, storage_options: dict | None = None):
    """Resolve a URL/path to (filesystem, path-on-that-filesystem)."""
    return fsspec.core.url_to_fs(url, **(storage_options or {}))


def is_local(path: str) -> bool:
    """True if `path` resolves to the local filesystem (vs. an `abfss://`/`s3://`/...
    URL). Guards code that must not apply local-path-only operations (`os.path.abspath`,
    `os.makedirs`, bare `open`) to a remote URL — see specs/31 §6."""
    import fsspec.utils

    return fsspec.utils.get_protocol(path) in ("file", "local")


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


def rm(path: str, recursive: bool = False, **storage_options: Any) -> None:
    fs, p = _fs_and_path(path, storage_options)
    fs.rm(p, recursive=recursive)


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


def rename(src_path: str, dst_path: str, **storage_options: Any) -> None:
    """Move `src_path` onto `dst_path` on one fsspec filesystem, in a single `mv`.

    The atomic-publish primitive for D7 (spec 36): on an HNS Azure account rename is a
    single metadata operation, and locally it is `os.rename` -- so a writer that saves
    to `src_path` and renames onto `dst_path` at the end leaves no window where a reader
    can observe a partial artifact.
    """
    fs, spath = _fs_and_path(src_path, storage_options)
    _, dpath = _fs_and_path(dst_path, storage_options)
    _ensure_parent(fs, dpath)
    fs.mv(spath, dpath)


def ls(url: str, **storage_options: Any) -> list[str]:
    fs, p = _fs_and_path(url, storage_options)
    return fs.ls(p, detail=False)


def glob(pattern: str, **storage_options: Any) -> list[str]:
    fs, p = _fs_and_path(pattern, storage_options)
    return fs.glob(p)


def size(url: str, **storage_options: Any) -> int:
    """Byte size of a file (0 if empty). Used to distinguish a real download from a
    zero-byte "touched" leftover."""
    fs, p = _fs_and_path(url, storage_options)
    return fs.size(p)


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


def _decode_pandas_attrs(footer_metadata: dict | None) -> dict:
    """`pyarrow` schema/file metadata -> the restored `.attrs` dict, or `{}` if
    there is no `PANDAS_ATTRS` footer key (spec 35 §2)."""
    if not footer_metadata:
        return {}
    raw = footer_metadata.get(PANDAS_ATTRS_FOOTER_KEY)
    if raw is None:
        return {}
    return json.loads(raw.decode("utf-8"))


def read_parquet(path: str, **storage_options: Any):
    """Read a (Geo)Parquet file -> GeoDataFrame.

    Restores `.attrs` from the Parquet footer's `PANDAS_ATTRS` key if present
    (spec 35 §2 -- geopandas' own writer/reader does not do this, unlike
    pandas'), and always stamps `attrs[SOURCE_PATH_ATTRS_KEY] = path` so
    downstream code can tell this GeoDataFrame came from a file (spec 35 §5a).
    """
    import geopandas as gpd

    fs, p = _fs_and_path(path, storage_options)
    with fs.open(p, "rb") as f:
        raw = f.read()
    gdf = gpd.read_parquet(io.BytesIO(raw))
    import pyarrow.parquet as pq

    attrs = _decode_pandas_attrs(pq.read_metadata(io.BytesIO(raw)).metadata)
    if attrs:
        gdf.attrs.update(attrs)
    gdf.attrs[SOURCE_PATH_ATTRS_KEY] = path
    return gdf


def write_parquet(path: str, df, **storage_options: Any) -> None:
    """Write a (Geo)DataFrame to `path` as (Geo)Parquet.

    If `df.attrs` is non-empty (minus `SOURCE_PATH_ATTRS_KEY`, always stripped
    -- spec 35 §10, it is read-side bookkeeping that would otherwise leak a
    local path into a written artifact), the attrs are JSON-encoded into the
    footer under `PANDAS_ATTRS` (spec 35 §2): `to_parquet` -> `pq.read_table` ->
    `replace_schema_metadata` -> `pq.write_table`. Empty attrs skip this
    entirely -- byte-for-byte today's write path at today's cost.

    Note: the attrs-present path re-encodes the table through pyarrow, so
    row-group layout/compression follow pyarrow's defaults rather than
    necessarily being byte-identical to plain `to_parquet` output -- harmless
    for catalog-sized data (KB-MB), but don't route a large dataframe through
    this expecting zero extra cost (spec 35 §10).
    """
    fs, p = _fs_and_path(path, storage_options)
    _ensure_parent(fs, p)
    buf = io.BytesIO()
    df.to_parquet(buf)

    attrs = {k: v for k, v in df.attrs.items() if k != SOURCE_PATH_ATTRS_KEY}
    if attrs:
        import pyarrow.parquet as pq

        buf.seek(0)
        table = pq.read_table(buf)
        metadata = dict(table.schema.metadata or {})
        metadata[PANDAS_ATTRS_FOOTER_KEY] = json.dumps(attrs).encode("utf-8")
        buf = io.BytesIO()
        pq.write_table(table.replace_schema_metadata(metadata), buf)

    with fs.open(p, "wb") as f:
        f.write(buf.getvalue())


def peek_parquet_attrs(path: str, **storage_options: Any) -> dict:
    """Read only the Parquet footer -- no row group -- and return the restored
    `.attrs` dict, or `{}` if there is none (spec 35 §1/§6: cheap inspection of
    the declaration stamp, e.g. for `fsd-catalog-inspect`)."""
    import pyarrow.parquet as pq

    fs, p = _fs_and_path(path, storage_options)
    with fs.open(p, "rb") as f:
        metadata = pq.read_metadata(f)
    return _decode_pandas_attrs(metadata.metadata)


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

    **Atomic:** bytes are streamed to a `.part` sidecar and renamed onto `dst_url`
    only after the copy fully succeeds. A failed/timed-out/killed transfer therefore
    never leaves a 0-byte or truncated file at the destination path — so an
    existence check is a safe "already downloaded" signal on resume.
    """
    src_fs, spath = _fs_and_path(src_url, src_options)
    dst_fs, dpath = _fs_and_path(dst_url, dst_options)
    _ensure_parent(dst_fs, dpath)
    tmp = f"{dpath}.part"
    try:
        with src_fs.open(spath, "rb") as fsrc, dst_fs.open(tmp, "wb") as fdst:
            shutil.copyfileobj(fsrc, fdst)
        dst_fs.mv(tmp, dpath)  # atomic on a local fs (os.rename)
    except BaseException:
        try:
            dst_fs.rm(tmp)
        except Exception:
            pass
        raise
