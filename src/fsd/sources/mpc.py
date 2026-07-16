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
from the item property `s2:processing_baseline` (§2 below) and is stored as the
additive `boa_add_offset` catalog column, applied at build time (spec 32 D1/D2;
see `fsd.datacube.builder`), not here.
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


# --- baseline -> offset (spec 32 D2/D3, correctness debt #10) -----------------


def _baseline_tuple(baseline: str) -> tuple[int, int]:
    """Parse an S2 `s2:processing_baseline` string ("04.00", "05.09", "02.14")
    into a comparable `(major, minor)` int tuple."""
    major, minor = baseline.split(".")
    return (int(major), int(minor))


def _offset_for_item(item) -> int:
    """The additive reflectance-band offset for one MPC item (spec 32 D2/D3),
    keyed on **baseline**, not acquisition date (MPC reprocessing can stamp a
    >=04.00 baseline on a pre-2022 date; the offset still applies). Raises if
    `s2:processing_baseline` is missing — deterministic, no silent 0 (this is
    the correctness-critical field, spec 32 §2)."""
    baseline = item.properties.get("s2:processing_baseline")
    if baseline is None:
        raise ValueError(
            f"MPC item {item.id!r} has no 's2:processing_baseline' property; "
            "cannot derive the reflectance offset (spec 32 §2)."
        )
    return -1000 if _baseline_tuple(baseline) >= (4, 0) else 0


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
            "boa_add_offset": _offset_for_item(it),
            "geometry": shapely.geometry.shape(it.geometry),
        }
        for it in items
    ]
    gdf = gpd.GeoDataFrame(
        rows, columns=["id", "satellite", "timestamp", "s3url", "cloud_cover",
                       "boa_add_offset", "geometry"], geometry="geometry",
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
    boa_add_offset, geometry (EPSG:4326). Asserts tile id uniqueness.
    """
    roi_gdf = _roi_gdf(roi)
    items = _search_items(roi_gdf, startdate, enddate, max_cloudcover=max_cloudcover)
    gdf = _items_to_gdf(items)
    return _finalize_catalog_gdf(gdf, roi_gdf, max_cloudcover)


# --- tile download (pure COG byte-copy; no conversion, spec 32 §1) -----------


def _select_item_files(
    item, bands: list[str], root_folderpath: str
) -> list[tuple[str, str]]:
    """Select download files from an MPC item's `assets` — MPC keys bands
    directly (`"B04"`, `"SCL"`, …), simpler than CDSE's `Bxx_YYm`. Returns
    `[(signed_href, local_dst_path), ...]`."""
    dst_folder = os.path.join(root_folderpath, item.id)
    selected = []
    for band in bands:
        asset = item.assets.get(band)
        if asset is None:
            continue  # band not available for this item
        selected.append((asset.href, os.path.join(dst_folder, f"{band}.tif")))
    return selected


def _transfer_one(
    src_url: str, dst_path: str, *, tries: int = 3, base_delay: float = 0.5,
) -> tuple[bool, str]:
    """Pure byte-copy of one already-COG asset (no conversion). Idempotent skip
    on an existing non-empty `dst_path`. Returns `(ok, reason)`."""
    import time

    if fs.exists(dst_path) and fs.size(dst_path) > 0:
        return True, "skipped"
    last: Exception | None = None
    for attempt in range(tries):
        try:
            fs.transfer(src_url, dst_path)
            return True, "ok"
        except Exception as e:  # noqa: BLE001 - retried below; final failure reported
            last = e
            if attempt == tries - 1:
                break
            time.sleep(base_delay * (2**attempt))
    return False, str(last) if last else "unknown"


def _append_downloaded(catalog, tile_meta: dict, results: list[tuple]) -> int:
    """Group successful (tile_id, dst, ok) downloads by tile and upsert catalog
    rows. Mirrors `cdse._append_downloaded`, plus `boa_add_offset`."""
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
            "boa_add_offset": r["boa_add_offset"],
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
    *,
    max_tiles: int,
    max_cloudcover: float | None = None,
    progress: bool = False,
    max_concurrent: int | None = None,
    should_stop: Callable[[], bool] | None = None,
) -> DownloadResult:
    """Discover matching MPC S2 L2A tiles and download the requested band files
    to `root_folderpath` (spec 32). Local-only in Phase 1 (mirrors CDSE's local
    ingest contract); no credentials required (anonymous MPC access, D4).

    Unlike `cdse.download`, this is a **pure COG byte-copy** — no jp2->COG
    conversion, so Phase 1 uses a straightforward thread-pool transfer (no
    convert-process-pool, no disk-aware staging cap; a single tile/band run is
    trivial — spec 32 §1 scope note). Idempotent (skips files already on disk).

    `should_stop` (optional) is checked in the submit loop, same halt-new-
    submissions-only semantics as `cdse.download` — not exercised by the
    Phase-1 single-tile runbook but kept for interface parity.
    """
    import concurrent.futures
    import time

    if not _is_local_path(root_folderpath):
        raise ValueError(
            "MPC source is local-only in Phase 1; got remote root_folderpath "
            f"{root_folderpath!r}. Azure-native streaming/copy is a Phase-2 "
            "decision (spec 32 §Scope; deferred fork, stream-in-place vs "
            "copy-to-rise)."
        )
    fs.makedirs(root_folderpath, exist_ok=True)

    roi_gdf = _roi_gdf(roi)
    items = _search_items(roi_gdf, startdate, enddate, max_cloudcover=max_cloudcover)
    tiles = _finalize_catalog_gdf(_items_to_gdf(items), roi_gdf, max_cloudcover)

    if len(tiles) > max_tiles:
        raise ValueError(
            f"{len(tiles)} matched tiles exceed max_tiles={max_tiles}. Narrow "
            "the query or raise max_tiles."
        )

    tile_meta = {row["id"]: row for _, row in tiles.iterrows()}
    kept_items = [it for it in items if it.id in tile_meta]

    work: list[tuple[str, str, str]] = []
    for it in kept_items:
        for src, dst in _select_item_files(it, bands, root_folderpath):
            work.append((src, dst, it.id))

    workers = max_concurrent if max_concurrent is not None else config.MPC_MAX_CONCURRENT
    start = time.time()
    results: list[tuple[str, str, bool]] = []
    failures: list[tuple[str, str]] = []
    skipped = 0

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {}
        for src, dst, tid in work:
            if should_stop is not None and should_stop():
                break
            futs[pool.submit(_transfer_one, src, dst)] = (src, dst, tid)
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
