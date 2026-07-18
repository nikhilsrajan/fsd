"""Cloud-Optimized GeoTIFF conversion. See specs/14-cog-on-download.md.

One canonical `to_cog(src, dst, ...)`: convert a **local** raster to a lossless COG
(DEFLATE + PREDICTOR=2, tiled), optionally with overviews. This is the single home
for the COG creation profile — the CDSE ingest path (`sources.cdse.download`) and the
spec-13 benchmark prep both go through here.

Lossless by construction: DEFLATE + PREDICTOR=2 is a reversible integer-differencing
pre-step (not a quality knob); for `uint16` sources — S2 reflectance declares NBITS=15
in a uint16 container, which PREDICTOR=2 rejects — we set `NBITS=16`, promoting only the
*declared* bit depth (pixel values are unchanged). Verified bit-identical in specs/13.

NOTE (specs/10): like all pixel I/O, conversion reads/writes **local** paths through
rasterio/GDAL (VSI), not fsspec — the documented raster-I/O exception. A remote source
must be fetched to local scratch first (`fsd.storage.get`).
"""

from __future__ import annotations

import os

import numpy as np
import rasterio
import rasterio.shutil

from fsd import config
from fsd.raster import rio_open

__all__ = ["to_cog", "cog_creation_opts"]


def cog_creation_opts(
    src_path: str,
    *,
    compress: str = config.COG_COMPRESS,
    predictor: int = config.COG_PREDICTOR,
    blocksize: int = config.COG_BLOCKSIZE,
    overviews: str = config.COG_OVERVIEWS,
) -> dict:
    """COG driver creation options for `src_path`. Adds `NBITS=16` for uint16 sources
    (PREDICTOR=2 needs an 8/16/32/64-bit declared depth; S2 declares NBITS=15) — a
    lossless promotion of the *declared* depth only."""
    with rio_open(src_path) as s:
        dtype = s.dtypes[0]
    opts = dict(
        driver="COG",
        COMPRESS=compress,
        PREDICTOR=predictor,
        BLOCKSIZE=blocksize,
        OVERVIEWS=overviews,
    )
    if dtype == "uint16":
        opts["NBITS"] = 16
    return opts


def to_cog(
    src_path: str,
    dst_path: str,
    *,
    compress: str = config.COG_COMPRESS,
    predictor: int = config.COG_PREDICTOR,
    blocksize: int = config.COG_BLOCKSIZE,
    overviews: str = config.COG_OVERVIEWS,
    verify: bool = False,
) -> int:
    """Convert a local raster `src_path` -> Cloud-Optimized GeoTIFF `dst_path`.

    Lossless (DEFLATE + PREDICTOR, NBITS=16 for uint16). Overviews per `overviews`
    (``"AUTO"`` builds them, ``"NONE"`` skips). **Atomic:** writes a sibling
    ``dst.part`` then ``os.replace`` onto ``dst`` — a crash never leaves a truncated
    ``.tif`` that a resume would mistake for done. Returns bytes written.

    `verify=True` reads both rasters back and asserts they are bit-identical (used in
    tests / a paranoid ingest); off by default since the conversion is deterministic
    and proven lossless (specs/13).
    """
    opts = cog_creation_opts(
        src_path,
        compress=compress,
        predictor=predictor,
        blocksize=blocksize,
        overviews=overviews,
    )
    parent = os.path.dirname(dst_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    tmp = f"{dst_path}.part"
    try:
        rasterio.shutil.copy(src_path, tmp, **opts)  # GDAL picks format from driver=
        os.replace(tmp, dst_path)
    except BaseException:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass
        raise

    if verify:
        with rio_open(src_path) as s, rio_open(dst_path) as d:
            if not np.array_equal(s.read(), d.read()):
                raise ValueError(f"to_cog: {dst_path} is not bit-identical to {src_path}")

    return os.path.getsize(dst_path)
