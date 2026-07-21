"""MPC source: Sentinel-2 L2A discovery + pure-copy tile download. See specs/32.

Microsoft Planetary Computer (MPC) serves S2 L2A assets **already as COG on
Azure** — unlike CDSE (spec 01/14/25) there is no `jp2->COG` conversion, so a
download here is a pure byte copy via `fsd.storage.transfer` (signed HTTPS ->
local). Discovery mirrors CDSE's STAC-item pattern (`pystac_client`), signed via
the official `planetary-computer` package (anonymous by default; an optional
`PC_SDK_SUBSCRIPTION_KEY` env var, read by that package itself, raises rate
limits — no `CdseCredentials` for this source).

MPC serves raw, unharmonized DN and does not expose the per-band S2
processing-baseline offset in STAC (`raster:bands` absent) — it must be derived
from the item property `s2:processing_baseline` (`_s2_radiometry.offset_for_item`)
and is stored as the additive `offset` catalog column (spec 34 §1, generalizing
spec 32's `boa_add_offset`). Since spec 34, MPC's download is no longer a *pure*
byte-copy: after `fs.transfer`, ingest stamps the GDAL scale/offset + nodata-if-
missing tags on the local COG (`fsd.raster.cog.stamp_or_reencode`) and pushes the
result to `root_folderpath` (local or blob) — a cheap header edit, no pixel
decode (spec 34 §3).
"""

from __future__ import annotations

import dataclasses
import datetime
import os
from typing import Callable

import geopandas as gpd
import pandas as pd
import shapely

from fsd import config
from fsd.catalog.declaration import S2_L2A_DECLARATION
from fsd.raster.cog import stamp_or_reencode
from fsd.raster.images import _is_reflectance
from fsd.sources._s2_radiometry import offset_for_item
from fsd.sources.cdse import _finalize_catalog_gdf, _is_local_path, _roi_gdf
from fsd.storage import fs

__all__ = [
    "DownloadResult",
    "query_catalog",
    "download",
]


@dataclasses.dataclass
class DownloadResult:
    successful_count: int
    total_count: int
    skipped_count: int = 0
    failed_count: int = 0
    elapsed_s: float = 0.0
    failures: list = dataclasses.field(default_factory=list)  # (src_url, reason)


# --- catalog discovery -------------------------------------------------------


def _item_self_href(item) -> str:
    """Best-effort item self-href (informational `s3url` column); "" if unset."""
    getter = getattr(item, "get_self_href", None)
    if callable(getter):
        try:
            return getter() or ""
        except Exception:  # noqa: BLE001 - purely informational, never fatal
            return ""
    return getattr(item, "self_href", None) or ""


def _mgrs_tile_from_item(item) -> str:
    """`s2:mgrs_tile` (spec 32 §1), falling back to the item id if absent."""
    return item.properties.get("s2:mgrs_tile") or item.id


def _generation_time(item) -> str:
    """`s2:generation_time` (RFC-3339 str) — the reliable "which processing pass"
    property (cross-validated over the id's trailing field, which ESA's own
    naming-convention doc does not guarantee is monotonic). Raises if missing -
    only called when a duplicate group actually needs a tie-break (spec 33)."""
    gt = item.properties.get("s2:generation_time")
    if gt is None:
        raise ValueError(
            f"MPC item {item.id!r} is one of >1 items for the same "
            "acquisition (same sensing time + MGRS tile) but has no "
            "'s2:generation_time' property; cannot pick the latest processing "
            "(spec 33 Fork 3)."
        )
    return gt


def _dedupe_reprocessed_items(items: list) -> list:
    """Collapse multiple STAC items covering the SAME acquisition (identical
    sensing `item.datetime` + MGRS tile, spec 33) down to one - the item with
    the latest `s2:generation_time` wins. A no-op for items with distinct
    (timestamp, tile) keys (the overwhelmingly common case)."""
    groups: dict[tuple, list] = {}
    for it in items:
        key = (it.datetime, _mgrs_tile_from_item(it))
        groups.setdefault(key, []).append(it)
    return [
        group[0] if len(group) == 1 else max(group, key=_generation_time)
        for group in groups.values()
    ]


def _search_items(roi_gdf: gpd.GeoDataFrame, startdate, enddate, max_cloudcover=None):
    """Query the MPC STAC API for S2 L2A items intersecting the ROI, signed via
    the official `planetary-computer` package (spec 32 D4)."""
    import planetary_computer as pc
    import pystac_client

    geom = shapely.unary_union(roi_gdf.to_crs("EPSG:4326")["geometry"])
    client = pystac_client.Client.open(config.MPC_STAC_URL, modifier=pc.sign_inplace)
    query = None
    if max_cloudcover is not None:
        query = {"eo:cloud_cover": {"lt": max_cloudcover}}
    search = client.search(
        collections=[config.SATELLITE_S2L2A],
        datetime=[startdate, enddate],
        intersects=geom,
        query=query,
        limit=200,
    )
    return list(search.items())


def _items_to_gdf(items) -> gpd.GeoDataFrame:
    """Parse MPC STAC items into a catalog GeoDataFrame. Pure — no network — so
    it is unit-testable with duck-typed fake items (`.id`, `.datetime`,
    `.geometry`, `.properties`, `.assets[*].href`)."""
    rows = [
        {
            "id": it.id,
            "satellite": config.SATELLITE_S2L2A,
            "timestamp": it.datetime,
            "s3url": _item_self_href(it),
            "cloud_cover": it.properties.get("eo:cloud_cover"),
            "offset": offset_for_item(it),
            "nodata": config.NODATA,
            "geometry": shapely.geometry.shape(it.geometry),
        }
        for it in items
    ]
    gdf = gpd.GeoDataFrame(
        rows, columns=["id", "satellite", "timestamp", "s3url", "cloud_cover",
                       "offset", "nodata", "geometry"], geometry="geometry",
        crs="EPSG:4326",
    )
    gdf["timestamp"] = pd.to_datetime(gdf["timestamp"], utc=True)
    return gdf


def query_catalog(
    roi,
    startdate: datetime.datetime,
    enddate: datetime.datetime,
    *,
    max_cloudcover: float | None = None,
) -> gpd.GeoDataFrame:
    """Discover S2 L2A tiles intersecting `roi` within the date range, via the
    MPC STAC API (anonymous by default).

    Returns a GeoDataFrame: id, satellite, timestamp, s3url, cloud_cover,
    offset, nodata, geometry (EPSG:4326). Asserts tile id uniqueness.
    """
    roi_gdf = _roi_gdf(roi)
    items = _search_items(roi_gdf, startdate, enddate, max_cloudcover=max_cloudcover)
    items = _dedupe_reprocessed_items(items)  # spec 33
    gdf = _items_to_gdf(items)
    return _finalize_catalog_gdf(gdf, roi_gdf, max_cloudcover)


# --- tile download (byte-copy + GDAL metadata stamp, spec 34 §3) -------------


def _select_item_files(
    item, bands: list[str], root_folderpath: str
) -> list[tuple[str, str, str]]:
    """Select download files from an MPC item's `assets` — MPC keys bands
    directly (`"B04"`, `"SCL"`, …), simpler than CDSE's `Bxx_YYm`. Returns
    `[(signed_href, local_dst_path, band), ...]`."""
    dst_folder = os.path.join(root_folderpath, item.id)
    selected = []
    for band in bands:
        asset = item.assets.get(band)
        if asset is None:
            continue  # band not available for this item
        selected.append((asset.href, os.path.join(dst_folder, f"{band}.tif"), band))
    return selected


def _transfer_and_stamp_one(
    src_url: str, dst_path: str, *, band: str, offset: int,
    tries: int = 3, base_delay: float = 0.5,
) -> tuple[bool, str]:
    """Byte-copy one already-COG asset (`fs.transfer`), then stamp the declared
    GDAL scale/offset (reflectance bands only) + nodata-if-missing tags (spec 34
    §1a/§3) — a cheap header edit, not a pixel-decoding re-encode
    (`fsd.raster.cog.stamp_or_reencode`, whose documented fallback is a
    GDAL-COG-driver re-encode if the in-place stamp breaks COG validity).

    Stamping needs a real local file, so when `dst_path` is remote (blob) the
    transfer lands in local scratch first, gets stamped there, then `fs.put`
    pushes it to `dst_path` (lifts spec 31/32's local-only guard, spec 34 §5).
    Idempotent skip on an existing non-empty `dst_path`. Returns `(ok, reason)`.
    """
    import shutil
    import tempfile
    import time

    if fs.exists(dst_path) and fs.size(dst_path) > 0:
        return True, "skipped"

    local = _is_local_path(dst_path)
    scratch_dir = None
    scratch = dst_path
    if not local:
        scratch_dir = tempfile.mkdtemp(prefix="fsd_mpc_")
        scratch = os.path.join(scratch_dir, os.path.basename(dst_path))

    is_reflectance = _is_reflectance(band)
    last: Exception | None = None
    try:
        for attempt in range(tries):
            try:
                fs.transfer(src_url, scratch)
                stamp_or_reencode(
                    scratch,
                    # reflectance-unit offset to match scale=1/10000 (spec 34 §1a): a
                    # viewer's unscale=true computes DN*scale + offset, so the DN-space
                    # offset (-1000) must be scaled to reflectance too (-> -0.1), else
                    # unscale yields DN/10000 - 1000 ~= -1000 for every pixel (black tile).
                    offset=offset * config.S2_REFLECTANCE_SCALE if is_reflectance else 0.0,
                    scale=config.S2_REFLECTANCE_SCALE if is_reflectance else 1.0,
                    set_nodata_if_missing=config.NODATA,
                )
                if not local:
                    fs.put(scratch, dst_path)
                return True, "ok"
            except Exception as e:  # noqa: BLE001 - retried below; final failure reported
                last = e
                if attempt == tries - 1:
                    break
                time.sleep(base_delay * (2**attempt))
        return False, str(last) if last else "unknown"
    finally:
        if scratch_dir is not None:
            shutil.rmtree(scratch_dir, ignore_errors=True)


def _append_downloaded(catalog, tile_meta: dict, results: list[tuple]) -> int:
    """Group successful (tile_id, dst, ok) downloads by tile and upsert catalog
    rows. Mirrors `cdse._append_downloaded`, plus `offset`/`nodata`."""
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
            "offset": r["offset"],
            "nodata": r["nodata"],
            "geometry": r["geometry"],
        })
    if rows:
        # spec 35 §4: MPC is also S2 L2A -- stamp the collection-level declaration
        # at the one place this source appends to the catalog.
        catalog.append(rows, declaration=S2_L2A_DECLARATION)
    return sum(len(f) for f in files_by_tile.values())


def download(
    roi,
    startdate: datetime.datetime,
    enddate: datetime.datetime,
    bands: list[str],
    root_folderpath: str,
    catalog,                      # fsd.catalog.catalog.TileCatalog (appended in place)
    *,
    max_tiles: int,
    max_cloudcover: float | None = None,
    progress: bool = False,
    max_concurrent: int | None = None,
    should_stop: Callable[[], bool] | None = None,
) -> DownloadResult:
    """Discover matching MPC S2 L2A tiles and download the requested band files
    to `root_folderpath`, local or remote/blob (spec 34 §3/§5 — lifts spec 32's
    local-only guard). No credentials required (anonymous MPC access, D4).

    Unlike `cdse.download`, source assets are already COG — no jp2->COG
    conversion, so this uses a straightforward thread-pool transfer + stamp (no
    convert-process-pool, no disk-aware staging cap; a single tile/band run is
    trivial — spec 32 §1 scope note, still true post-spec-34). Idempotent (skips
    files already on disk).

    `should_stop` (optional) is checked in the submit loop, same halt-new-
    submissions-only semantics as `cdse.download` — not exercised by the
    Phase-1 single-tile runbook but kept for interface parity.
    """
    import concurrent.futures
    import time

    if _is_local_path(root_folderpath):
        fs.makedirs(root_folderpath, exist_ok=True)

    roi_gdf = _roi_gdf(roi)
    items = _search_items(roi_gdf, startdate, enddate, max_cloudcover=max_cloudcover)
    items = _dedupe_reprocessed_items(items)  # spec 33
    tiles = _finalize_catalog_gdf(_items_to_gdf(items), roi_gdf, max_cloudcover)

    if len(tiles) > max_tiles:
        raise ValueError(
            f"{len(tiles)} matched tiles exceed max_tiles={max_tiles}. Narrow "
            "the query or raise max_tiles."
        )

    tile_meta = {row["id"]: row for _, row in tiles.iterrows()}
    kept_items = [it for it in items if it.id in tile_meta]

    work: list[tuple[str, str, str, str, int]] = []
    for it in kept_items:
        offset = tile_meta[it.id]["offset"]
        for src, dst, band in _select_item_files(it, bands, root_folderpath):
            work.append((src, dst, it.id, band, offset))

    workers = max_concurrent if max_concurrent is not None else config.MPC_MAX_CONCURRENT
    start = time.time()
    results: list[tuple[str, str, bool]] = []
    failures: list[tuple[str, str]] = []
    skipped = 0

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {}
        for src, dst, tid, band, offset in work:
            if should_stop is not None and should_stop():
                break
            futs[pool.submit(_transfer_and_stamp_one, src, dst, band=band, offset=offset)] = (src, dst, tid)
        for fut in concurrent.futures.as_completed(futs):
            src, dst, tid = futs[fut]
            ok, reason = fut.result()
            if reason == "skipped":
                skipped += 1
            if not ok:
                failures.append((src, reason))
            results.append((tid, dst, ok))
            if progress:
                print(
                    f"[fsd.mpc.download] {len(results)}/{len(work)} "
                    f"ok={sum(1 for *_, o in results if o)} fail={len(failures)}",
                    flush=True,
                )

    successful = _append_downloaded(catalog, tile_meta, results)

    return DownloadResult(
        successful_count=successful,
        total_count=successful + len(failures),
        skipped_count=skipped,
        failed_count=len(failures),
        elapsed_s=time.time() - start,
        failures=failures,
    )
