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
import shutil

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
        """`storage_options` for the CDSE S3 endpoint, for `fsd.storage` calls.

        Includes connect/read timeouts so a stalled connection (common during CDSE's
        flaky windows, BUG-001) raises instead of hanging a worker forever; botocore's
        own retries are disabled so our `_download_one` layer owns retry/labeling.
        """
        return {
            "key": self.s3_access_key,
            "secret": self.s3_secret_key,
            "client_kwargs": {"endpoint_url": config.CDSE_S3_ENDPOINT_URL},
            "config_kwargs": {
                "connect_timeout": config.S3_CONNECT_TIMEOUT,
                "read_timeout": config.S3_READ_TIMEOUT,
                "retries": {"max_attempts": 1},
            },
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
    successful_count: int          # files on disk after the run (new + already-present)
    total_count: int              # files attempted
    skipped_count: int = 0        # already on disk (idempotent skip)
    failed_count: int = 0         # files that failed after retries (fast-fails)
    elapsed_s: float = 0.0
    failures: list = dataclasses.field(default_factory=list)   # (src_url, reason)
    reason_counts: dict = dataclasses.field(default_factory=dict)  # {reason: count}
    circuit_tripped: bool = False  # stopped early: too many consecutive failures
    # --- timing decomposition (spec 23, D1/D11) — summed across worker threads, so
    # transfer_seconds + convert_seconds may exceed elapsed_s (they overlap). bytes_downloaded is
    # the JP2 bytes actually pulled from CDSE (basis for throughput MB/s); skips contribute 0. ---
    bytes_downloaded: int = 0            # JP2 bytes transferred this run (excludes skipped)
    transfer_seconds: float = 0.0        # summed CDSE byte-transfer wall-time
    convert_seconds: float = 0.0         # summed local JP2->COG conversion wall-time
    bytes_by_band: dict = dataclasses.field(default_factory=dict)  # {band: bytes} for extrapolation


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
    item, bands: list[str], root_folderpath: str, *, cog: bool = True
) -> list[tuple[str, str]]:
    """Select download files from a STAC item's `assets` (no S3 listing).

    For each requested band, pick the highest-resolution asset (`{band}_{res}`,
    smallest `_NNm`) and take its S3 `href`; add `MTD_TL.xml` from the
    `granule_metadata` asset. Returns `[(src_s3_url, local_filepath), ...]` with
    short band filenames, matching the on-disk layout. The band source href is always
    the `.jp2` asset; when `cog` the local destination is `Bxx.tif` (converted on
    arrival, spec 14), else `Bxx.jp2`.
    """
    dst_folder = _download_folderpath(_safe_root_from_item(item), root_folderpath)
    band_ext = "tif" if cog else "jp2"

    selected = []
    for band in bands:
        # asset keys are "{BAND}_{res}"; sorted lexically 10m < 20m < 60m.
        keys = sorted(k for k in item.assets if k.split("_")[0] == band)
        if not keys:
            continue  # band not available for this item
        selected.append(
            (item.assets[keys[0]].href, os.path.join(dst_folder, f"{band}.{band_ext}"))
        )

    granule = item.assets.get("granule_metadata")
    if granule is not None:
        selected.append((granule.href, os.path.join(dst_folder, "MTD_TL.xml")))
    return selected


# CDSE S3 auth errors that are transient (permanent on real AWS) — see BUGS.md
# BUG-001. Retryable ONLY because this is the CDSE-specific source: on CDSE these are
# transient (node-inconsistency roulette), whereas on real AWS they'd be permanent.
# `Forbidden`/403 and `InvalidAccessKeyId` were both observed at scale 2026-07-02 —
# retrying re-rolls onto a (possibly good) node, so include them.
_RETRYABLE_S3 = (
    "InvalidAccessKeyId",
    "SignatureDoesNotMatch",
    "SlowDown",
    "AccessDenied",
    "Forbidden",
    # transient connection/timeout errors (a stalled transfer that hit the timeout)
    "ReadTimeout",
    "ConnectTimeout",
    "ConnectionError",
    "EndpointConnection",
    "timed out",
)


def _is_retryable_s3(exc: Exception) -> bool:
    return any(code in str(exc) for code in _RETRYABLE_S3)


# Short reason labels for the failure report.
_S3_ERROR_CODES = _RETRYABLE_S3 + ("NoSuchKey",)


def _error_reason(exc: Exception) -> str:
    s = str(exc)
    for code in _S3_ERROR_CODES:
        if code in s:
            return code
    if isinstance(exc, PermissionError):
        return "Forbidden"  # s3fs raises bare PermissionError for 403s
    return type(exc).__name__


def _is_local_path(path: str) -> bool:
    """True if `path` resolves to the local filesystem (vs an `s3://`/`az://` URL)."""
    import fsspec.utils

    return fsspec.utils.get_protocol(path) in ("file", "local")


def _transfer_one(
    src_url: str,
    dst_path: str,
    s3opts: dict,
    *,
    needs_convert: bool,
    tries: int = 3,
    base_delay: float = 0.5,
) -> tuple[bool, str, float, int]:
    """THREAD stage (spec 25). Idempotent skip on the **final** `dst_path`
    (`size > 0`, never a 0-byte "touched" leftover — that re-transfers). Otherwise
    transfers with the **fail-fast** retry loop on CDSE's transient S3 auth errors
    (BUG-001: a few quick re-rolls recover a *partial* bad window; a *sustained* one
    is not worth grinding — `download_resume` is the real recovery).

    When `needs_convert` (cog and a `.jp2` band), the byte transfer lands at the
    local staging sibling `dst_path + ".src.jp2"` (converted later by `_convert_one`,
    off this thread); otherwise (sidecar, or `cog=False`) it transfers straight to
    `dst_path`. No conversion here.

    Returns `(ok, reason, transfer_s, jp2_bytes)`; `reason` is ``"skipped"``/``"ok"``
    on success or a short error label on failure. Zeros on skip/failure.
    """
    import random
    import time

    if fs.exists(dst_path) and fs.size(dst_path) > 0:
        return True, "skipped", 0.0, 0
    target = dst_path + ".src.jp2" if needs_convert else dst_path
    last: Exception | None = None
    for attempt in range(tries):
        try:
            t0 = time.time()
            fs.transfer(src_url, target, src_options=s3opts)
            t1 = time.time()
            return True, "ok", t1 - t0, fs.size(target)
        except Exception as e:
            last = e
            if attempt == tries - 1 or not _is_retryable_s3(e):
                break
            time.sleep(min(base_delay * (2**attempt), 4.0) + random.uniform(0, 0.5))
    return False, _error_reason(last) if last else "unknown", 0.0, 0


def _convert_one(staging: str, dst_path: str) -> tuple[bool, str, float]:
    """PROCESS stage (spec 25). `to_cog(staging, dst_path)` (spec 14, lossless COG
    with overviews) then remove `staging` (`finally` — `to_cog` is atomic, so a crash
    leaves at most the staging JP2, never a half-written `.tif`; the next resume pass
    re-transfers and re-converts).

    Top-level & picklable (`ProcessPoolExecutor`, spawn) — operates only on real local
    files, so it never needs a parent-process monkeypatch. A failure here is a local/
    data fault (``"ConvertError"``), never a CDSE window — the caller must not fold it
    into the transfer-failure circuit breaker (spec 25 C4).

    Returns `(ok, reason, convert_s)`.
    """
    import time

    from fsd.raster.cog import to_cog

    try:
        t0 = time.time()
        to_cog(staging, dst_path)
        return True, "ok", time.time() - t0
    except Exception:
        return False, "ConvertError", 0.0
    finally:
        if fs.exists(staging):
            try:
                fs.rm(staging)
            except Exception:
                pass


def _download_one(
    src_url: str,
    dst_path: str,
    s3opts: dict,
    *,
    cog: bool = True,
    tries: int = 3,
    base_delay: float = 0.5,
) -> tuple[bool, str, tuple[float, float, int]]:
    """Sequential reference wrapper (spec 25) = `_transfer_one` then, inline,
    `_convert_one`. Kept for its direct-call unit tests and as the single-worker
    reference unit; `download()` no longer calls this — it drives the two stages
    across a transfer thread pool and a convert process pool instead (see `download`).

    Returns `(ok, reason, metrics)` where `reason` is ``"skipped"``/``"ok"`` on
    success or a short error label (transfer or ``"ConvertError"``) on failure, and
    `metrics` is `(transfer_s, convert_s, bytes)` (spec 23) — zeros on skip/failure.
    """
    needs_convert = cog and src_url.endswith(".jp2")
    ok, reason, t_s, nbytes = _transfer_one(
        src_url, dst_path, s3opts, needs_convert=needs_convert,
        tries=tries, base_delay=base_delay,
    )
    if not ok or reason == "skipped" or not needs_convert:
        return ok, reason, (t_s, 0.0, nbytes)
    c_ok, c_reason, c_s = _convert_one(dst_path + ".src.jp2", dst_path)
    return c_ok, c_reason, (t_s, c_s, nbytes)


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


def _default_max_staged(root_folderpath: str, max_convert_procs: int) -> int:
    """Disk-aware `MAX_STAGED` sizing (spec 25 D5/D6): a **safety cap** on
    staged-but-unconverted JP2s, not a throughput lever — past `floor` a bigger
    buffer gives no throughput gain (bounded-buffer queueing), so free disk only
    *shrinks* the cap, never grows it beyond the saturation target `headroom`.
    Sized **once** at `download()` start from `shutil.disk_usage(root_folderpath)`.
    """
    floor = config.MAX_CONCURRENT_S3 + max_convert_procs
    headroom = config.MAX_CONCURRENT_S3 + 2 * max_convert_procs
    free = shutil.disk_usage(root_folderpath).free
    disk_cap = int(free * config.STAGING_DISK_FRACTION / (config.STAGING_ITEM_GB * 1e9))
    staged = max(config.MAX_CONCURRENT_S3, min(headroom, disk_cap))
    if staged < floor:
        print(
            f"[fsd.download] warning: disk-limited staging={staged} < {floor} "
            "(convert pool may under-saturate)",
            flush=True,
        )
    return staged


def _make_convert_pool(max_workers: int):
    """Default convert-process-pool factory (spec 25). A module-level seam: tests
    monkeypatch this to assert a `cog=False` / all-skip `download()` run never spawns
    a process pool. **Spawn** start-method (GDAL-safe; `fork` + GDAL's internal
    threads can deadlock on Linux/Batch)."""
    import concurrent.futures
    import multiprocessing

    return concurrent.futures.ProcessPoolExecutor(
        max_workers=max_workers, mp_context=multiprocessing.get_context("spawn"),
    )


def _fmt_progress(done, total, ok_n, fail_n, skipped, elapsed_s) -> str:
    """A single newline-terminated progress line (log-friendly, with ETA)."""
    rate = done / elapsed_s if elapsed_s > 0 else 0.0
    eta_s = (total - done) / rate if rate > 0 else 0.0
    pct = 100 * done // max(1, total)
    return (
        f"[{int(elapsed_s // 60):3d}m{int(elapsed_s % 60):02d}s] "
        f"{done}/{total} ({pct:2d}%) ok={ok_n} fail={fail_n} skip={skipped} | "
        f"{rate:.1f} file/s | ETA {int(eta_s // 60)}m"
    )


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
    progress: bool = False,
    max_consecutive_failures: int | None = None,
    cog: bool = True,
    max_convert_procs: int | None = None,
    max_staged: int | None = None,
    convert_executor=None,
) -> DownloadResult:
    """THE SOURCE CONTRACT (documented signature; see specs/01-sources.md).

    Discover matching tiles and download the requested band files (+ MTD_TL.xml) to
    `root_folderpath` via a **pipeline** (spec 25): a `MAX_CONCURRENT_S3`-wide thread
    pool transfers bytes while a separate process pool converts fetched JP2s to COGs
    concurrently, chained by `add_done_callback` and bounded by a `max_staged`
    backpressure semaphore (staged-but-unconverted JP2s on disk). Idempotent (skips
    files already on disk); the catalog is upserted every `chunksize` completions so a
    crash doesn't lose progress; refuses if matched tiles exceed `max_tiles`.

    `cog` (default True, spec 14): convert each fetched JP2 band to a lossless COG
    (`Bxx.tif`, with overviews) on arrival — the native ingest format, which the
    datacube build reads far faster (spec 13). `cog=False` keeps the native `.jp2`
    (and never staggers a convert pool). Conversion needs a **local**
    `root_folderpath`; a remote (`s3://`/`az://`) dst with `cog=True` raises (the
    stage-local→convert→upload path is deferred).

    `max_convert_procs` (default `config.MAX_CONVERT_PROCS`), `max_staged` (default:
    `_default_max_staged`, disk-aware) and `convert_executor` (default: a real
    `ProcessPoolExecutor`, spawn context) are optional knobs — `convert_executor` is
    the test seam (inject a synchronous stand-in to exercise the pipeline in-process,
    no subprocess). The convert pool is created **lazily**, on the first file that
    actually needs conversion — a `cog=False` run or an all-skip resume pass spawns
    zero processes.

    `max_consecutive_failures` is the **circuit breaker**, keyed on consecutive
    **transfer** failures only (a `_convert_one` failure is a local fault, not a CDSE
    window, spec 25 C4): if that many transfers fail back-to-back (a bad CDSE window,
    BUG-001), the submit loop stops queuing new work, in-flight transfers/converts
    drain, and the pass returns with `circuit_tripped=True` instead of grinding — it
    stops within roughly `max_staged` items of the trip (streaming, no exact chunk
    boundary). Pair with `download_resume` to retry the remainder later — the catalog
    makes it a clean resume.
    """
    import collections
    import concurrent.futures
    import threading
    import time
    from functools import partial

    creds.require_s3()  # discovery (STAC) is anonymous; only download needs S3 keys

    if cog and not _is_local_path(root_folderpath):
        raise ValueError(
            "COG-on-download (cog=True) needs a local root_folderpath in v1; got "
            f"{root_folderpath!r}. Use cog=False to keep native JP2, or wait for the "
            "stage-local->convert->upload path (Azure milestone)."
        )

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
        for src, dst in _select_item_files(it, bands, root_folderpath, cog=cog):
            work.append((src, dst, it.id))

    total = len(work)
    start = time.time()

    procs = max_convert_procs if max_convert_procs is not None else config.MAX_CONVERT_PROCS
    staged_cap = max_staged
    if staged_cap is None:
        # _default_max_staged needs a real local path; only cog=True can reach here
        # with a local root (cog=False + remote root is otherwise legal and sem_staged
        # is never acquired for it, so skip the disk probe entirely).
        staged_cap = _default_max_staged(root_folderpath, procs) if cog else config.MAX_CONCURRENT_S3
    sem_staged = threading.BoundedSemaphore(staged_cap)

    lock = threading.Lock()
    all_done = threading.Event()
    pending_results: list[tuple[str, str, bool]] = []
    failures: list[tuple[str, str]] = []
    reason_counts: collections.Counter = collections.Counter()
    bytes_by_band: collections.Counter = collections.Counter()
    state = {
        "done": 0, "skipped": 0, "successful": 0,
        "consecutive": 0, "tripped": False,
        "transfer_seconds": 0.0, "convert_seconds": 0.0, "bytes_downloaded": 0,
        "remaining": 0, "loop_finished": False, "last_print": 0.0,
    }
    convert_pool_holder: dict = {"pool": None}
    pool_create_lock = threading.Lock()

    def _emit():
        if progress:
            print(
                _fmt_progress(state["done"], total, reason_counts["ok"] + state["skipped"],
                              len(failures), state["skipped"], time.time() - start),
                flush=True,
            )

    def _get_convert_pool():
        with pool_create_lock:
            if convert_pool_holder["pool"] is None:
                convert_pool_holder["pool"] = (
                    convert_executor if convert_executor is not None
                    else _make_convert_pool(procs)
                )
            return convert_pool_holder["pool"]

    def _finalize(tid, src, dst, ok, reason):
        with lock:
            pending_results.append((tid, dst, ok))
            reason_counts[reason] += 1
            if reason == "skipped":
                state["skipped"] += 1
            if not ok:
                failures.append((src, reason))
            state["done"] += 1
            # Catalog-flush cadence (spec 25 §4): chunksize no longer batches the
            # executor (one continuous pipeline) — it now only controls how often the
            # buffer flushes to the catalog (crash resilience).
            if len(pending_results) >= chunksize:
                state["successful"] += _append_downloaded(catalog, tile_meta, pending_results)
                pending_results.clear()
            if progress and time.time() - state["last_print"] >= config.PROGRESS_EVERY_S:
                state["last_print"] = time.time()
                _emit()
            state["remaining"] -= 1
            drained = state["loop_finished"] and state["remaining"] == 0
        if drained:
            all_done.set()

    def _on_convert_done(src, tid, dst, cfut):
        ok, reason, c_s = cfut.result()
        sem_staged.release()
        with lock:
            state["convert_seconds"] += c_s
        _finalize(tid, src, dst, ok, reason)

    def _on_transfer_done(src, dst, tid, needs_convert, fut):
        ok, reason, t_s, nbytes = fut.result()
        with lock:
            state["transfer_seconds"] += t_s
            if nbytes:
                state["bytes_downloaded"] += nbytes
                bytes_by_band[os.path.splitext(os.path.basename(dst))[0]] += nbytes
            if ok:
                state["consecutive"] = 0
            else:
                state["consecutive"] += 1
                if (max_consecutive_failures is not None
                        and state["consecutive"] >= max_consecutive_failures):
                    state["tripped"] = True
        if ok and reason != "skipped" and needs_convert:
            pool = _get_convert_pool()
            cfut = pool.submit(_convert_one, dst + ".src.jp2", dst)
            cfut.add_done_callback(partial(_on_convert_done, src, tid, dst))
        else:
            if needs_convert:
                sem_staged.release()
            _finalize(tid, src, dst, ok, reason)

    transfer_pool = concurrent.futures.ThreadPoolExecutor(max_workers=config.MAX_CONCURRENT_S3)
    try:
        for src, dst, tid in work:
            if state["tripped"]:
                break
            needs_convert = cog and src.endswith(".jp2")
            if needs_convert:
                sem_staged.acquire()  # BLOCKS at max_staged in-flight -> backpressure
                if state["tripped"]:
                    sem_staged.release()
                    break
            with lock:
                state["remaining"] += 1
            fut = transfer_pool.submit(_transfer_one, src, dst, s3opts, needs_convert=needs_convert)
            fut.add_done_callback(partial(_on_transfer_done, src, dst, tid, needs_convert))

        with lock:
            state["loop_finished"] = True
            drained = state["remaining"] == 0
        if drained:
            all_done.set()
        all_done.wait()
    finally:
        transfer_pool.shutdown(wait=True)
        if convert_pool_holder["pool"] is not None:
            convert_pool_holder["pool"].shutdown(wait=True)

    with lock:
        if pending_results:
            state["successful"] += _append_downloaded(catalog, tile_meta, pending_results)
            pending_results.clear()

    _emit()  # final line

    return DownloadResult(
        successful_count=state["successful"],
        total_count=state["successful"] + len(failures),   # files actually attempted
        skipped_count=state["skipped"],
        failed_count=len(failures),
        elapsed_s=time.time() - start,
        failures=failures,
        reason_counts=dict(reason_counts),
        circuit_tripped=state["tripped"],
        bytes_downloaded=state["bytes_downloaded"],
        transfer_seconds=state["transfer_seconds"],
        convert_seconds=state["convert_seconds"],
        bytes_by_band=dict(bytes_by_band),
    )


def download_resume(
    roi,
    startdate: datetime.datetime,
    enddate: datetime.datetime,
    bands: list[str],
    root_folderpath: str,
    catalog,
    creds: CdseCredentials,
    *,
    max_tiles: int,
    chunksize: int = 100,
    max_cloudcover: float | None = None,
    progress: bool = False,
    max_consecutive_failures: int = 15,
    max_passes: int = 10,
    cooldown_s: float = 60.0,
    on_pass=None,
    cog: bool = True,
    max_convert_procs: int | None = None,
    max_staged: int | None = None,
    convert_executor=None,
) -> list[DownloadResult]:
    """Resume-loop: run `download` repeatedly until every file is present (a full pass
    with no failures) or `max_passes` is reached.

    Each pass is idempotent (skips files already on disk) and trips the circuit breaker
    on a bad CDSE window (`max_consecutive_failures`); on a trip we wait `cooldown_s`
    then try again — the *fail-fast + resume-later* strategy (BUG-001). A partial
    window (scattered fast-fails, no trip) loops immediately to retry the remainder.

    `on_pass(pass_index, DownloadResult)` is called after each pass (e.g. to persist
    stats), keeping file I/O out of the library. Returns the per-pass results.

    `max_convert_procs`/`max_staged`/`convert_executor` pass through to each `download`
    call unchanged (spec 25) — see its docstring.
    """
    import time

    results: list[DownloadResult] = []
    for p in range(max_passes):
        r = download(
            roi, startdate, enddate, bands, root_folderpath, catalog, creds,
            max_tiles=max_tiles, chunksize=chunksize, max_cloudcover=max_cloudcover,
            progress=progress, max_consecutive_failures=max_consecutive_failures,
            cog=cog, max_convert_procs=max_convert_procs, max_staged=max_staged,
            convert_executor=convert_executor,
        )
        results.append(r)
        if on_pass is not None:
            on_pass(p, r)
        if r.failed_count == 0 and not r.circuit_tripped:
            break  # complete: a full pass attempted everything and nothing failed
        if r.circuit_tripped and cooldown_s:
            time.sleep(cooldown_s)  # bad window — back off, then resume
    return results


def sum_results(results: list[DownloadResult]) -> DownloadResult:
    """Aggregate the per-pass results of `download_resume` into one `DownloadResult` (spec 23).

    Counts/bytes/seconds add; a later pass that skips an already-downloaded file contributes 0
    bytes/seconds, so the sum is the true one-time cost. `elapsed_s` is the sum of pass wall-times.
    """
    import collections

    agg = DownloadResult(successful_count=0, total_count=0)
    by_band: collections.Counter = collections.Counter()
    reasons: collections.Counter = collections.Counter()
    for r in results:
        agg.successful_count += r.successful_count
        agg.total_count += r.total_count
        agg.skipped_count += r.skipped_count
        agg.failed_count += r.failed_count
        agg.elapsed_s += r.elapsed_s
        agg.failures.extend(r.failures)
        agg.bytes_downloaded += r.bytes_downloaded
        agg.transfer_seconds += r.transfer_seconds
        agg.convert_seconds += r.convert_seconds
        agg.circuit_tripped = agg.circuit_tripped or r.circuit_tripped
        reasons.update(r.reason_counts)
        by_band.update(r.bytes_by_band)
    agg.reason_counts = dict(reasons)
    agg.bytes_by_band = dict(by_band)
    return agg


def probe_throughput(
    roi,
    startdate: datetime.datetime,
    enddate: datetime.datetime,
    bands: list[str],
    creds: CdseCredentials,
    *,
    max_cloudcover: float | None = None,
) -> tuple[float, int, float]:
    """Measure achievable CDSE **byte** throughput right now with a single-threaded fetch of ONE
    representative band file (spec 23, D2). Returns `(mb_per_s, bytes, seconds)`.

    A baseline to compare against a run's *aggregate effective* MB/s: probe≈aggregate → CDSE/link
    bound; probe≫aggregate → local contention / concurrency. Transfers the JP2 to a temp path and
    removes it (isolates network from COG-conversion; a fresh sample each call).
    """
    import tempfile
    import time

    creds.require_s3()
    roi_gdf = _roi_gdf(roi)
    items = _search_items(roi_gdf, startdate, enddate)
    tiles = _finalize_catalog_gdf(_items_to_gdf(items), roi_gdf, max_cloudcover)
    if not len(tiles):
        return (0.0, 0, 0.0)
    tile_ids = set(tiles["id"])
    item = next(it for it in items if it.id in tile_ids)
    band = bands[0]
    keys = sorted(k for k in item.assets if k.split("_")[0] == band)
    if not keys:
        return (0.0, 0, 0.0)
    src = item.assets[keys[0]].href
    s3opts = creds.s3_storage_options()
    tmp = os.path.join(tempfile.gettempdir(), f"fsd_probe_{item.id}_{band}.jp2")
    try:
        t0 = time.time()
        fs.transfer(src, tmp, src_options=s3opts)
        dt = time.time() - t0
        nbytes = fs.size(tmp)
    finally:
        if fs.exists(tmp):
            try:
                fs.rm(tmp)
            except Exception:
                pass
    return (nbytes / 1e6 / dt if dt > 0 else 0.0, nbytes, dt)


def plan_download(
    roi,
    startdate: datetime.datetime,
    enddate: datetime.datetime,
    bands: list[str],
    *,
    catalog_filepath: str | None = None,
    dst_folderpath: str | None = None,
    max_cloudcover: float | None = None,
    cost_model: dict | None = None,
) -> dict:
    """Compute an actionable download plan **without downloading** (spec 23, D13).

    Queries the CDSE STAC (anonymous, no bytes) for the tiles this request needs, diffs them
    against what is already in `catalog_filepath` (if given), and returns a plan dict: needed /
    present / missing tile counts + ids, the exact `fsd.download(...)` params to satisfy it
    (`max_tiles` = needed count), and — when a `cost_model` is supplied — the estimated GB + ETA
    for the missing tiles. This is the CDSE (materializing-source) arm of the guardrail; a
    streamable source (MPC) would never need it (TODO #21).
    """
    needed = query_catalog(roi, startdate, enddate, max_cloudcover=max_cloudcover)
    needed_ids = list(needed["id"])
    needed_set = set(needed_ids)

    present_ids: list[str] = []
    if catalog_filepath is not None and fs.exists(catalog_filepath):
        try:
            from fsd.catalog.catalog import TileCatalog

            existing = TileCatalog(catalog_filepath).read()
            present_ids = [i for i in existing["id"] if i in needed_set]
        except Exception:  # noqa: BLE001 - a missing/unreadable catalog just means "all missing"
            present_ids = []
    present_set = set(present_ids)
    missing_ids = [i for i in needed_ids if i not in present_set]

    plan = {
        "needed_count": len(needed_ids),
        "present_count": len(present_ids),
        "missing_count": len(missing_ids),
        "missing_ids": missing_ids,
        "download_params": {
            "roi": roi if isinstance(roi, str) else "<GeoDataFrame>",
            "startdate": startdate.isoformat() if hasattr(startdate, "isoformat") else str(startdate),
            "enddate": enddate.isoformat() if hasattr(enddate, "isoformat") else str(enddate),
            "bands": list(bands),
            "max_tiles": max(len(needed_ids), 1),
            "max_cloudcover": max_cloudcover,
            "dst_folderpath": dst_folderpath,
        },
    }
    if cost_model:
        mean_by_band = cost_model.get("mean_bytes_by_band") or {}
        per_granule = sum(mean_by_band.get(b, 0) for b in bands)
        est_bytes = plan["missing_count"] * per_granule
        mbps = cost_model.get("transfer_mb_per_s") or 0.0
        plan["estimate"] = {
            "gb": round(est_bytes / 1e9, 2),
            "download_minutes": round((est_bytes / 1e6 / mbps) / 60, 1) if mbps else None,
        }
    return plan


def format_download_plan(plan: dict) -> str:
    """Render a `plan_download` dict as a copy-pasteable message (spec 23, D13)."""
    p = plan["download_params"]
    lines = [
        "imagery for this run is not (fully) present in the catalog.",
        f"  needed: {plan['needed_count']} granules | present: {plan['present_count']} | "
        f"missing: {plan['missing_count']}",
    ]
    est = plan.get("estimate")
    if est:
        eta = f", ~{est['download_minutes']} min" if est.get("download_minutes") else ""
        lines.append(f"  estimated: ~{est['gb']} GB{eta} (at last measured throughput)")
    band_list = ", ".join(f'"{b}"' for b in p["bands"])
    lines += [
        "  run fsd.download(",
        f'      roi={p["roi"]!r}, startdate="{p["startdate"]}", enddate="{p["enddate"]}",',
        f"      bands=[{band_list}], max_tiles={p['max_tiles']}, "
        f"max_cloudcover={p['max_cloudcover']}, dst_folderpath={p['dst_folderpath']!r})",
    ]
    return "\n".join(lines)
