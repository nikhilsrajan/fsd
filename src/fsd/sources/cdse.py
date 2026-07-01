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
import json
import os

from fsd import config
from fsd.storage import fs

# Environment-variable names for the cloud/Batch path (CdseCredentials.from_env).
ENV_SH_CLIENT_ID = "CDSE_SH_CLIENT_ID"
ENV_SH_CLIENT_SECRET = "CDSE_SH_CLIENT_SECRET"
ENV_S3_ACCESS_KEY = "CDSE_S3_ACCESS_KEY"
ENV_S3_SECRET_KEY = "CDSE_S3_SECRET_KEY"
ENV_S3_KEYS_EXPIRE = "CDSE_S3_KEYS_EXPIRE"

# JSON keys of the legacy `cdse_credentials.json` (kept for compatibility).
_JSON_SH_CLIENT_ID = "sh_clientid"
_JSON_SH_CLIENT_SECRET = "sh_clientsecret"
_JSON_S3_ACCESS_KEY = "s3_access_key"
_JSON_S3_SECRET_KEY = "s3_secret_key"


@dataclasses.dataclass
class CdseCredentials:
    """CDSE credentials: SH client id/secret (catalog) + S3 keys (download).

    See specs/01-sources.md. Load from a gitignored JSON file (`from_json`, local
    dev) or from environment variables (`from_env`, cloud/Batch). Secret values are
    never printed — `__repr__` masks them.
    """

    sh_client_id: str | None = None       # catalog (Sentinel Hub)
    sh_client_secret: str | None = None
    s3_access_key: str | None = None      # tile download (S3)
    s3_secret_key: str | None = None
    s3_keys_expire: str | None = None     # optional ISO date (YYYY-MM-DD), informational
    note: str | None = None               # optional free text

    def __repr__(self) -> str:
        def m(v):
            return "set" if v else "unset"

        return (
            f"CdseCredentials(sh_client_id={m(self.sh_client_id)}, "
            f"sh_client_secret={m(self.sh_client_secret)}, "
            f"s3_access_key={m(self.s3_access_key)}, "
            f"s3_secret_key={m(self.s3_secret_key)}, "
            f"s3_keys_expire={self.s3_keys_expire!r}, note={self.note!r})"
        )

    @classmethod
    def from_json(cls, filepath: str, **storage_options) -> "CdseCredentials":
        """Load from a JSON file using the legacy `cdse_credentials.json` keys.

        Tolerates extra keys; picks up optional `s3_keys_expire` / `note`.
        """
        with fs.open(filepath, "r", **storage_options) as f:
            data = json.load(f)
        return cls(
            sh_client_id=data.get(_JSON_SH_CLIENT_ID),
            sh_client_secret=data.get(_JSON_SH_CLIENT_SECRET),
            s3_access_key=data.get(_JSON_S3_ACCESS_KEY),
            s3_secret_key=data.get(_JSON_S3_SECRET_KEY),
            s3_keys_expire=data.get("s3_keys_expire"),
            note=data.get("note"),
        )

    def to_json(self, filepath: str, **storage_options) -> None:
        """Write to JSON in the legacy key format (round-trips with `from_json`)."""
        data = {
            _JSON_SH_CLIENT_ID: self.sh_client_id,
            _JSON_SH_CLIENT_SECRET: self.sh_client_secret,
            _JSON_S3_ACCESS_KEY: self.s3_access_key,
            _JSON_S3_SECRET_KEY: self.s3_secret_key,
        }
        if self.s3_keys_expire is not None:
            data["s3_keys_expire"] = self.s3_keys_expire
        if self.note is not None:
            data["note"] = self.note
        with fs.open(filepath, "w", **storage_options) as f:
            json.dump(data, f, indent=2)

    @classmethod
    def from_env(cls, environ: dict | None = None) -> "CdseCredentials":
        """Load from environment variables (cloud/Batch path)."""
        e = environ if environ is not None else os.environ
        return cls(
            sh_client_id=e.get(ENV_SH_CLIENT_ID),
            sh_client_secret=e.get(ENV_SH_CLIENT_SECRET),
            s3_access_key=e.get(ENV_S3_ACCESS_KEY),
            s3_secret_key=e.get(ENV_S3_SECRET_KEY),
            s3_keys_expire=e.get(ENV_S3_KEYS_EXPIRE),
        )

    def s3_storage_options(self) -> dict:
        """`storage_options` for the CDSE S3 endpoint, for `fsd.storage` calls."""
        return {
            "key": self.s3_access_key,
            "secret": self.s3_secret_key,
            "client_kwargs": {"endpoint_url": config.CDSE_S3_ENDPOINT_URL},
        }

    def require_complete(self) -> None:
        """Raise if any of the four core credential fields is missing."""
        missing = [
            name
            for name in (
                "sh_client_id",
                "sh_client_secret",
                "s3_access_key",
                "s3_secret_key",
            )
            if not getattr(self, name)
        ]
        if missing:
            raise ValueError(f"CdseCredentials missing required fields: {missing}")

    def is_expired(self, as_of: datetime.date | None = None) -> bool | None:
        """Whether the S3 keys are past `s3_keys_expire`. None if unknown."""
        if not self.s3_keys_expire:
            return None
        as_of = as_of or datetime.date.today()
        return datetime.date.fromisoformat(self.s3_keys_expire) < as_of


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
