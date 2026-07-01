"""CDSE source: Sentinel-2 L2A discovery + tile download. See specs/01-sources.md.

Discovery is the **CDSE STAC API** (`pystac-client`, anonymous — no credentials):
each STAC item's `assets` already carry the per-band S3 `href`s, so we never list a
`.SAFE` over S3 (that recursive listing was the flaky path — see BUGS.md BUG-001).
The only S3-authenticated operation is the byte `transfer` of each band file, done
through the generic, provider-agnostic transport in `fsd.storage` (no direct boto3).

This module also defines the documented `download(...)` source contract (OQ-3:
function-signature, not an ABC).
"""

from __future__ import annotations

import dataclasses
import datetime
import json
import os

import geopandas as gpd
import pandas as pd
import shapely

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

    def require_s3(self) -> None:
        """Raise if the S3 keys are missing. Discovery (STAC) is anonymous, so only
        the download step needs credentials — this is the check it uses."""
        missing = [
            name for name in ("s3_access_key", "s3_secret_key")
            if not getattr(self, name)
        ]
        if missing:
            raise ValueError(f"CdseCredentials missing S3 fields: {missing}")

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


# --- catalog discovery -------------------------------------------------------


def _roi_gdf(roi) -> gpd.GeoDataFrame:
    """Accept a GeoDataFrame or a path to one."""
    if isinstance(roi, str):
        return gpd.read_file(roi)
    return roi


def _safe_root_from_item(item) -> str:
    """Derive the `.SAFE` root s3url from any of the item's S3 asset hrefs."""
    for asset in item.assets.values():
        href = asset.href
        if href.startswith("s3://") and ".SAFE/" in href:
            return href.split(".SAFE/")[0] + ".SAFE"
    raise ValueError(f"STAC item {item.id} has no s3 .SAFE asset href")


def _search_items(roi_gdf: gpd.GeoDataFrame, startdate, enddate):
    """Query the CDSE STAC API (anonymous) for S2 L2A items intersecting the ROI."""
    import pystac_client

    geom = shapely.unary_union(roi_gdf.to_crs("EPSG:4326")["geometry"])
    client = pystac_client.Client.open(config.CDSE_STAC_URL)
    search = client.search(
        collections=[config.SATELLITE_S2L2A],
        datetime=[startdate, enddate],
        intersects=geom,
        limit=200,   # page size; pystac-client auto-paginates
    )
    return list(search.items())


def _items_to_gdf(items) -> gpd.GeoDataFrame:
    """Parse STAC items (pystac `Item`s) into a catalog GeoDataFrame.

    Pure — no network — so it is unit-testable with duck-typed fake items
    (`.id`, `.datetime`, `.geometry`, `.properties`, `.assets[*].href`).
    """
    rows = [
        {
            "id": it.id,
            "satellite": config.SATELLITE_S2L2A,
            "timestamp": it.datetime,
            "s3url": _safe_root_from_item(it),
            "cloud_cover": it.properties.get("eo:cloud_cover"),
            "geometry": shapely.geometry.shape(it.geometry),
        }
        for it in items
    ]
    gdf = gpd.GeoDataFrame(
        rows, columns=["id", "satellite", "timestamp", "s3url", "cloud_cover",
                       "geometry"], geometry="geometry", crs="EPSG:4326",
    )
    gdf["timestamp"] = pd.to_datetime(gdf["timestamp"], utc=True)
    return gdf


def _finalize_catalog_gdf(
    gdf: gpd.GeoDataFrame, roi_gdf: gpd.GeoDataFrame, max_cloudcover: float | None
) -> gpd.GeoDataFrame:
    """Apply the cloud filter, keep only tiles intersecting the real ROI, and assert
    tile-id uniqueness."""
    if max_cloudcover is not None:
        gdf = gdf[gdf["cloud_cover"] <= max_cloudcover]

    roi_union = shapely.unary_union(roi_gdf.to_crs(gdf.crs)["geometry"])
    gdf = gdf[gdf.intersects(roi_union)].reset_index(drop=True)

    if len(gdf) and gdf["id"].value_counts().max() > 1:
        raise ValueError(
            "CDSE returned non-unique tile ids; the local folder layout assumes "
            "tile id is unique. This needs handling before proceeding."
        )
    return gdf


def query_catalog(
    roi,
    startdate: datetime.datetime,
    enddate: datetime.datetime,
    *,
    max_cloudcover: float | None = None,
) -> gpd.GeoDataFrame:
    """Discover S2 L2A tiles intersecting `roi` within the date range, via the CDSE
    STAC API (anonymous — no credentials).

    Returns a GeoDataFrame: id, satellite, timestamp, s3url, cloud_cover, geometry
    (EPSG:4326). Asserts tile id uniqueness. No disk cache (decision).
    """
    roi_gdf = _roi_gdf(roi)
    items = _search_items(roi_gdf, startdate, enddate)
    gdf = _items_to_gdf(items)
    return _finalize_catalog_gdf(gdf, roi_gdf, max_cloudcover)


# --- tile download -----------------------------------------------------------

_VALID_S3_PREFIXES = ("s3://eodata/", "s3://EODATA/")


def _download_folderpath(safe_s3url: str, root_folderpath: str) -> str:
    """Map a `.SAFE` s3url to its local folder: strip the `s3://eodata/` prefix and
    the `.SAFE` suffix, then join under `root_folderpath`. Matches the flattened
    on-disk layout (short band names, no `.SAFE`)."""
    for pref in _VALID_S3_PREFIXES:
        if safe_s3url.startswith(pref):
            rel = safe_s3url[len(pref):]
            break
    else:
        raise ValueError(
            f"Unexpected s3url (must start with one of {_VALID_S3_PREFIXES}): "
            f"{safe_s3url}"
        )
    rel = rel.rstrip("/")
    if rel.endswith(".SAFE"):
        rel = rel[: -len(".SAFE")]
    return os.path.join(root_folderpath, *rel.split("/"))


def _select_item_files(
    item, bands: list[str], root_folderpath: str
) -> list[tuple[str, str]]:
    """Select download files from a STAC item's `assets` (no S3 listing).

    For each requested band, pick the highest-resolution asset (`{band}_{res}`,
    smallest `_NNm`) and take its S3 `href`; add `MTD_TL.xml` from the
    `granule_metadata` asset. Returns `[(src_s3_url, local_filepath), ...]` with
    short band filenames (`B02.jp2`), matching the on-disk layout.
    """
    dst_folder = _download_folderpath(_safe_root_from_item(item), root_folderpath)

    selected = []
    for band in bands:
        # asset keys are "{BAND}_{res}"; sorted lexically 10m < 20m < 60m.
        keys = sorted(k for k in item.assets if k.split("_")[0] == band)
        if not keys:
            continue  # band not available for this item
        selected.append(
            (item.assets[keys[0]].href, os.path.join(dst_folder, f"{band}.jp2"))
        )

    granule = item.assets.get("granule_metadata")
    if granule is not None:
        selected.append((granule.href, os.path.join(dst_folder, "MTD_TL.xml")))
    return selected


# CDSE S3 auth errors that are transient (permanent on real AWS) — see BUGS.md
# BUG-001. Retryable ONLY because this is the CDSE-specific source.
_RETRYABLE_S3 = (
    "InvalidAccessKeyId",
    "SignatureDoesNotMatch",
    "SlowDown",
    "AccessDenied",
)


def _is_retryable_s3(exc: Exception) -> bool:
    return any(code in str(exc) for code in _RETRYABLE_S3)


def _download_one(
    src_url: str, dst_path: str, s3opts: dict, *, tries: int = 3, base_delay: float = 2.0
) -> bool:
    """Transfer one file (idempotent: skip if already on disk), with fail-fast retry
    on CDSE's transient S3 auth errors (jittered backoff). Returns success."""
    import random
    import time

    if fs.exists(dst_path):
        return True
    for attempt in range(tries):
        try:
            fs.transfer(src_url, dst_path, src_options=s3opts)
            return True
        except Exception as e:
            if attempt == tries - 1 or not _is_retryable_s3(e):
                return False
            time.sleep(base_delay * (2**attempt) + random.uniform(0, 1))
    return False


def _append_downloaded(catalog, tile_meta: dict, results: list[tuple]) -> int:
    """Group successful (tile_id, dst, ok) downloads by tile and upsert catalog rows
    (`catalog.append` unions `files`, so partially-downloaded tiles complete on a
    later append). Returns the number of successful files."""
    import collections

    files_by_tile = collections.defaultdict(list)
    folder_by_tile: dict[str, str] = {}
    for tile_id, dst, ok in results:
        if not ok:
            continue
        files_by_tile[tile_id].append(os.path.basename(dst))
        folder_by_tile[tile_id] = os.path.dirname(dst)

    rows = []
    for tile_id, files in files_by_tile.items():
        r = tile_meta[tile_id]
        rows.append({
            "id": tile_id,
            "satellite": r["satellite"],
            "timestamp": r["timestamp"],
            "s3url": r["s3url"],
            "local_folderpath": folder_by_tile[tile_id],
            "files": ",".join(sorted(files)),
            "cloud_cover": r["cloud_cover"],
            "geometry": r["geometry"],
        })
    if rows:
        catalog.append(rows)
    return sum(len(f) for f in files_by_tile.values())


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
    max_cloudcover: float | None = None,
) -> DownloadResult:
    """THE SOURCE CONTRACT (documented signature; see specs/01-sources.md).

    Discover matching tiles, download the requested band files (+ MTD_TL.xml) to
    `root_folderpath` via `fsd.storage.transfer`, and append per-tile records to
    `catalog`. Idempotent (skips files already on disk); downloads in file-chunks
    and upserts the catalog after each chunk so a crash doesn't lose progress;
    refuses if matched tiles exceed `max_tiles`. S3 concurrency is capped at CDSE's
    limit.
    """
    import concurrent.futures

    creds.require_s3()  # discovery (STAC) is anonymous; only download needs S3 keys

    roi_gdf = _roi_gdf(roi)
    items = _search_items(roi_gdf, startdate, enddate)
    tiles = _finalize_catalog_gdf(_items_to_gdf(items), roi_gdf, max_cloudcover)

    if len(tiles) > max_tiles:
        est_gb = len(tiles) * config.APPROX_GB_PER_TILE
        raise ValueError(
            f"{len(tiles)} matched tiles exceed max_tiles={max_tiles} "
            f"(~{est_gb:.0f} GB). Narrow the query or raise max_tiles."
        )

    s3opts = creds.s3_storage_options()
    tile_meta = {row["id"]: row for _, row in tiles.iterrows()}
    kept_items = [it for it in items if it.id in tile_meta]

    # Flat work list (src, dst, tile_id) built from STAC assets — no S3 listing.
    work: list[tuple[str, str, str]] = []
    for it in kept_items:
        for src, dst in _select_item_files(it, bands, root_folderpath):
            work.append((src, dst, it.id))

    total = len(work)
    successful = 0
    for i in range(0, total, chunksize):
        chunk = work[i : i + chunksize]
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=config.MAX_CONCURRENT_S3
        ) as pool:
            oks = list(pool.map(lambda w: _download_one(w[0], w[1], s3opts), chunk))
        results = [(tid, dst, ok) for (_, dst, tid), ok in zip(chunk, oks)]
        successful += _append_downloaded(catalog, tile_meta, results)

    return DownloadResult(successful_count=successful, total_count=total)
