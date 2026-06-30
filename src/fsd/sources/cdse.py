"""CDSE source: Sentinel-2 L2A discovery + tile download. See specs/01-sources.md.

CDSE owns ONLY: STAC discovery (via sentinelhub) and the Sentinel-2 `.SAFE`
file-selection logic. The byte transfer is delegated to the generic, provider-
agnostic S3 transport in `fsd.storage` (no direct boto3).

This module also defines the documented `download(...)` source contract (OQ-3:
function-signature, not an ABC).
"""

from __future__ import annotations

import dataclasses
import datetime


@dataclasses.dataclass
class CdseCredentials:
    """Two credential pairs, both required. See specs/01-sources.md."""

    sh_client_id: str | None = None       # catalog (Sentinel Hub)
    sh_client_secret: str | None = None
    s3_access_key: str | None = None      # tile download (S3)
    s3_secret_key: str | None = None

    @classmethod
    def from_json(cls, filepath: str) -> "CdseCredentials":
        raise NotImplementedError

    def to_json(self, filepath: str) -> None:
        raise NotImplementedError


@dataclasses.dataclass
class DownloadResult:
    successful_count: int
    total_count: int


def query_catalog(
    roi,
    startdate: datetime.datetime,
    enddate: datetime.datetime,
    creds: CdseCredentials,
    *,
    max_cloudcover: float | None = None,
):
    """Discover S2 L2A tiles intersecting `roi` within the date range.

    Returns a GeoDataFrame: id, timestamp, geometry, s3url, cloud_cover.
    Asserts tile id uniqueness. No disk cache (decision).
    """
    raise NotImplementedError


def download(
    roi,
    startdate: datetime.datetime,
    enddate: datetime.datetime,
    bands: list[str],
    root_folderpath: str,
    catalog,                      # fsd.catalog.catalog.TileCatalog (appended in place)
    creds: CdseCredentials,
    *,
    max_tiles: int,
    chunksize: int = 100,
) -> DownloadResult:
    """THE SOURCE CONTRACT (documented signature; see specs/01-sources.md).

    Discover matching tiles, download the requested band files (+ MTD_TL.xml) to
    `root_folderpath` via `fsd.storage.transfer`, and append per-tile records to
    `catalog`. Idempotent; chunked so a crash doesn't lose progress; refuses if
    matched tiles exceed `max_tiles`.
    """
    raise NotImplementedError
