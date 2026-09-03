"""Raster primitives (rasterio). See specs/07-raster.md, specs/31-p1-azure-storage-seam.md.

`rio_open` is the one sanctioned exception to "all I/O via fsd.storage" (specs/10): rasterio
reads pixels through GDAL's VSI layer, not fsspec. It is a plain passthrough for local paths
(the regression-safety hinge — zero behavior change to every existing read/write) and routes an
`abfss://`/`az://` source through GDAL's `/vsiadls/` handler with a fresh access token.
Writing to a remote path raises, rather than silently attempting a partial write.
"""

from __future__ import annotations

import contextlib

import rasterio

from fsd.storage.azure import account_from_url, storage_token, to_vsi

__all__ = ["rio_open", "rio_env"]

# Without these, every remote VSI open costs more than one HTTP request: GDAL lists the
# containing directory looking for sidecars (.aux.xml/.ovr/.msk). fsd writes plain COGs with
# statistics inline and no sidecars, so nothing in-repo depends on one.
#
# ⚠️ The named risk: EMPTY_DIR means a sidecar that DOES exist stops being read. This applies
# to every remote raster open (download, datacube, merge, collect), not just one call site --
# both `rio_env` (N datasets) and `rio_open` (one) build their env_kwargs from this same dict
# so the two cannot drift.
#
# Sources (GDAL config docs, gdal.org/en/stable/user/configoptions.html):
# GDAL_DISABLE_READDIR_ON_OPEN=EMPTY_DIR -- "only the target file is visible; side-car/auxiliary
# files aren't loaded". CPL_VSIL_CURL_ALLOWED_EXTENSIONS -- "Consider that only the files whose
# extension ends up with one that is listed in CPL_VSIL_CURL_ALLOWED_EXTENSIONS exist on the
# server. This can speed up dramatically open experience, in case the server cannot return a
# file list."
#
# ⚠️ That second option is a WHITELIST, not a hint: a remote file whose
# extension is not listed is reported as NOT EXISTING, so the list must cover every extension fsd
# can open remotely -- not just the one at the call site that motivated it. Remote here is always
# `abfss://`/`az://` -> `/vsiadls/` (`storage.to_vsi`), i.e. fsd's own run folders and staged
# imagery: output/mosaic COGs (`.tif`), plus band files, which are `.jp2` whenever imagery was
# downloaded with `cog=False` (`sources.cdse.download`) and `.tiff` for a foreign COG. Keep this
# in sync with `datacube.builder._RASTER_EXTS` -- the set the cube builder hands to `rio_open`.
_REMOTE_OPEN_CONFIG = {
    "GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR",
    "CPL_VSIL_CURL_ALLOWED_EXTENSIONS": ".tif,.tiff,.jp2",
}


def rio_env(paths):
    """ONE `rasterio.Env` covering MANY remote datasets — use this when several must be open
    at the same time (e.g. `rasterio.merge` over N COGs).

    **Why this exists.** `rio_open` enters a
    `rasterio.Env` *per dataset* and exits it on `close()`. rasterio's env stack is LIFO and
    thread-local: the first `Env.__enter__` records `_has_parent_env=False`, and *its* `__exit__`
    sets `local._env = None`. So holding N `rio_open` handles and closing them in creation order
    tears down the root env first, and the next `close()` raises
    `EnvError: No GDAL environment exists`. With 300 merge inputs that is a hard failure.
    `rio_open` is for ONE scoped dataset (`with rio_open(p) as src:`); this is for N.

    Returns a null context for all-local `paths` — same zero-behaviour-change hinge as `rio_open`.
    Open the datasets with `rasterio.open(to_vsi(fp))` *inside* the `with`, and keep every pixel
    read inside it too: the env carries the credentials.
    """
    if isinstance(paths, str):
        paths = [paths]
    remote = [p for p in paths if to_vsi(p) != p]
    if not remote:
        return contextlib.nullcontext()

    accounts = {account_from_url(p) for p in remote} - {None}
    if len(accounts) > 1:
        raise ValueError(
            f"rio_env: cannot cover datasets on multiple storage accounts in one env: "
            f"{sorted(accounts)}. Open them under separate envs."
        )
    env_kwargs = {"AZURE_STORAGE_ACCESS_TOKEN": storage_token(), **_REMOTE_OPEN_CONFIG}
    if accounts:
        env_kwargs["AZURE_STORAGE_ACCOUNT"] = accounts.pop()
    return rasterio.Env(**env_kwargs)


def rio_open(path: str, mode: str = "r", **kwargs):
    """`rasterio.open`, transparently routed to `/vsiadls/` for an `abfss://`/`az://` `path`.

    Local paths (the overwhelming common case) are a straight passthrough — no VSI translation,
    no `rasterio.Env`, no token fetch. A remote `path` opened with `mode="w"` raises: P1 writes
    stay local everywhere (MPC-to-blob would be a byte-copy via `fs.transfer`, never a GDAL
    write; CDSE-to-blob is out of P1 scope) — silently attempting one would half-work and fail
    late.

    ⚠️ **One dataset at a time.** This owns a `rasterio.Env` per handle, so N of them held open
    and closed in creation order breaks the LIFO env stack. To hold several open at once, use
    `rio_env(paths)` + `rasterio.open(to_vsi(fp))`.
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
    env_kwargs = {"AZURE_STORAGE_ACCESS_TOKEN": storage_token(), **_REMOTE_OPEN_CONFIG}
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
