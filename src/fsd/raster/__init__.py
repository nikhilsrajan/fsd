"""Raster primitives (rasterio). See specs/07-raster.md, specs/31-p1-azure-storage-seam.md.

`rio_open` is the one sanctioned exception to "all I/O via fsd.storage" (specs/10): rasterio
reads pixels through GDAL's VSI layer, not fsspec. It is a plain passthrough for local paths
(the regression-safety hinge — zero behavior change to every existing read/write) and routes an
`abfss://`/`az://` source through GDAL's `/vsiadls/` handler with a fresh access token (spec 31
§4). Writing to a remote path is out of scope for P1 and raises rather than silently attempting
a partial write.
"""

from __future__ import annotations

import rasterio

from fsd.storage.azure import account_from_url, storage_token, to_vsi

__all__ = ["rio_open"]


def rio_open(path: str, mode: str = "r", **kwargs):
    """`rasterio.open`, transparently routed to `/vsiadls/` for an `abfss://`/`az://` `path`.

    Local paths (the overwhelming common case) are a straight passthrough — no VSI translation,
    no `rasterio.Env`, no token fetch. A remote `path` opened with `mode="w"` raises: P1 writes
    stay local everywhere (MPC-to-blob would be a byte-copy via `fs.transfer`, never a GDAL
    write; CDSE-to-blob is out of P1 scope) — silently attempting one would half-work and fail
    late.
    """
    vsi = to_vsi(path)
    if vsi == path:
        return rasterio.open(path, mode, **kwargs)

    if mode not in ("r", "rb"):
        raise ValueError(
            f"rio_open: mode={mode!r} on a remote path is not supported in P1 "
            f"(GDAL writes stay local): {path!r}"
        )

    account = account_from_url(path)
    env_kwargs = {"AZURE_STORAGE_ACCESS_TOKEN": storage_token()}
    if account is not None:
        env_kwargs["AZURE_STORAGE_ACCOUNT"] = account
    env = rasterio.Env(**env_kwargs)
    env.__enter__()
    try:
        src = rasterio.open(vsi, mode, **kwargs)
    except BaseException:
        env.__exit__(None, None, None)
        raise
    src._fsd_vsi_env = env  # keep the Env alive for the dataset's lifetime; released on close()
    _wrap_close(src, env)
    return src


def _wrap_close(src, env) -> None:
    """Make `src.close()` (and `with src:` exit) also tear down its `rasterio.Env`."""
    orig_close = src.close

    def close(*args, **kwargs):
        try:
            orig_close(*args, **kwargs)
        finally:
            env.__exit__(None, None, None)

    src.close = close
