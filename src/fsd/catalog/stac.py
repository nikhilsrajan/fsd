"""STAC export view over the tile catalog (spec 17).

The `TileCatalog` GeoParquet stays the working/query format; this module is an **additive**
STAC interchange view: one STAC Item per catalog row, one asset per band file. The mapping is
pure-metadata (no raster reads) by default — `proj:epsg` is derived from the MGRS tile in the
product id; per-asset `proj:shape`/`proj:transform` are opt-in (`read_proj=True`).

Serialization is a static, self-contained STAC catalog (JSON) via `pystac`, written through the
`fsd.storage` seam so a blob/S3 destination works later unchanged. `stac-geoparquet` is deferred.

Designed so the future inference-output catalog (P4/P5, one Item per output COG) reuses
`write_stac_catalog` + the asset helpers via a second item-builder; only the tile-catalog path
is implemented here.
"""

from __future__ import annotations

import os
import re

import pystac
import shapely.geometry
from pystac.extensions.eo import EOExtension
from pystac.extensions.projection import ProjectionExtension
from pystac.extensions.raster import RasterBand, RasterExtension
from pystac.stac_io import DefaultStacIO

from fsd import config
from fsd.raster.images import _is_reflectance
from fsd.storage import fs

# Bands with a categorical mask/QA role (spec 34 §2a) rather than a continuous
# reflectance value — never radiometrically offset, and the default S2 declaration's
# mask band. Not exhaustive for future non-S2 sources (a source with its own QA band
# naming supplies its own declaration; this module only needs to render the S2
# ingest path's roles today, spec 34 §3).
_MASK_BANDS = {"SCL"}

# STAC extension URIs we populate beyond eo/proj (added via their helper classes).
_GRID_EXT = "https://stac-extensions.github.io/grid/v1.1.0/schema.json"

# MGRS tile in an S2 product id, e.g. "..._T37PBP_..." -> zone=37, band=P, square=BP.
_MGRS_RE = re.compile(r"_T(\d{2})([C-X])([A-Z]{2})_")

_SOURCE_LINK_REL = "via"  # the source .SAFE product this row was downloaded from


class _StorageStacIO(DefaultStacIO):
    """Route pystac's JSON read/write through `fsd.storage` (local now, blob/S3 later)."""

    def read_text(self, source, *args, **kwargs) -> str:
        with fs.open(str(source), "r") as f:
            return f.read()

    def write_text(self, dest, txt, *args, **kwargs) -> None:
        parent = os.path.dirname(str(dest))
        if parent:
            fs.makedirs(parent)
        with fs.open(str(dest), "w") as f:
            f.write(txt)


# --- mapping helpers ---------------------------------------------------------

def _parse_mgrs(item_id: str) -> tuple[str, int] | None:
    """Return (mgrs_tile, epsg) from an S2 product id, or None if not parseable.

    UTM EPSG from the latitude band: bands C..M are southern (327xx), N..X northern (326xx).
    """
    m = _MGRS_RE.search(item_id)
    if not m:
        return None
    zone, band, square = m.group(1), m.group(2), m.group(3)
    north = band >= "N"
    epsg = int(f"{'326' if north else '327'}{int(zone):02d}")
    return f"{zone}{band}{square}", epsg


def _band_role(band: str, reference_band: str = "B08") -> str:
    """Spec 34 §2a role classification for a band name: `"mask"` (SCL/QA),
    `"reference"` (the resample-reference band), else `"reflectance"` for an S2
    optical band, else the generic `"data"` (e.g. AOT/WVP/visual — present in a
    tile's `files` but not consumed by the builder's radiometry/mask/reference
    logic)."""
    if band in _MASK_BANDS:
        return "mask"
    if band == reference_band:
        return "reference"
    if _is_reflectance(band):
        return "reflectance"
    return "data"


def _media_type_and_roles(filename: str, band: str | None = None) -> tuple[str | None, list[str]]:
    lower = filename.lower()
    role = [_band_role(band)] if band else []
    # spec 34 §2a: the role classification rides alongside "data" (never replaces it,
    # and never duplicates it when _band_role already returned "data").
    data_roles = ["data", *role] if role and role[0] != "data" else ["data"]
    if lower.endswith((".tif", ".tiff")):
        return pystac.MediaType.COG, data_roles
    if lower.endswith(".jp2"):
        return pystac.MediaType.JPEG2000, data_roles
    if lower.endswith(".xml"):
        return pystac.MediaType.XML, ["metadata"]
    return None, ["data"]


def _asset_href(local_folderpath: str, filename: str) -> str:
    # Local runs: the recorded file path. (Blob/S3 hrefs arrive with the storage seam, P1.)
    return os.path.join(str(local_folderpath), filename)


def _read_proj_fields(href: str) -> dict:
    """Open a raster to read per-asset proj:shape / proj:transform (opt-in; I/O)."""
    from fsd.raster import rio_open

    with rio_open(href) as src:
        return {"shape": [src.height, src.width], "transform": list(src.transform)[:6]}


# --- tile catalog -> STAC items ----------------------------------------------

def tile_catalog_to_items(
    gdf, *, collection_id=None, read_proj=False, reference_band: str = "B08",
) -> list[pystac.Item]:
    """Map `TileCatalog` rows (a GeoDataFrame from `.read()`) to STAC Items.

    One Item per row (a tile-product acquisition); one asset per band file in `files`.
    Pure-metadata unless `read_proj=True` (which opens each raster for proj:shape/transform).

    Spec 34 §1a/§2a: every raster asset (a `.tif`/`.jp2` band file) gets a `raster:bands`
    entry with the row's declared `offset`/`nodata` (`.get(...)`, defaulting to 0 for a
    catalog row without them) and the constant reflectance `scale`
    (`config.S2_REFLECTANCE_SCALE`) for reflectance bands (`scale=1` for mask/other
    bands — a no-op). This is the *interchange* declaration the builder/other tools
    read; the load-bearing one for a viewer is the COG's own GDAL tag (stamped at
    ingest, `fsd.raster.cog.stamp_gdal_tags`) — the two are written with identical
    values so there is no drift (§1a "no double-application").
    """
    items: list[pystac.Item] = []
    for _, row in gdf.iterrows():
        geom = row["geometry"]
        dt = row["timestamp"].to_pydatetime()
        coll = collection_id if collection_id is not None else row["satellite"]
        row_offset = row.get("offset", 0) or 0
        row_nodata = row.get("nodata", 0)
        row_nodata = 0 if row_nodata is None else row_nodata

        item = pystac.Item(
            id=str(row["id"]),
            geometry=shapely.geometry.mapping(geom),
            bbox=list(geom.bounds),
            datetime=dt,
            properties={},
            collection=coll,
        )

        EOExtension.ext(item, add_if_missing=True).cloud_cover = float(row["cloud_cover"])

        mgrs = _parse_mgrs(str(row["id"]))
        if mgrs is not None:
            tile, epsg = mgrs
            ProjectionExtension.ext(item, add_if_missing=True).epsg = epsg
            if _GRID_EXT not in item.stac_extensions:
                item.stac_extensions.append(_GRID_EXT)
            item.properties["grid:code"] = f"MGRS-{tile}"

        files = [f for f in str(row["files"]).split(",") if f]
        for filename in files:
            band = filename.rsplit(".", 1)[0]
            href = _asset_href(row["local_folderpath"], filename)
            media_type, roles = _media_type_and_roles(filename, band)
            asset = pystac.Asset(href=href, media_type=media_type, roles=roles, title=band)
            item.add_asset(band, asset)  # sets asset.owner=item, required before ext(add_if_missing=True)
            if "data" in roles:
                asset.extra_fields["eo:bands"] = [{"name": band}]
                if read_proj and media_type != pystac.MediaType.XML:
                    asset.extra_fields.update(
                        {f"proj:{k}": v for k, v in _read_proj_fields(href).items()}
                    )
                if media_type in (pystac.MediaType.COG, pystac.MediaType.JPEG2000):
                    is_reflectance = _band_role(band, reference_band) in ("reflectance", "reference")
                    RasterExtension.ext(asset, add_if_missing=True).bands = [
                        RasterBand.create(
                            nodata=row_nodata,
                            offset=row_offset if is_reflectance else 0,
                            scale=config.S2_REFLECTANCE_SCALE if is_reflectance else 1,
                        )
                    ]

        if row.get("s3url"):
            item.add_link(pystac.Link(rel=_SOURCE_LINK_REL, target=str(row["s3url"])))

        items.append(item)
    return items


def _output_item_id(fp) -> str:
    """STAC item id for an inference-output COG.

    fsd writes every output as ``<cube_id>/output.tif`` (the per-cell/-cube folder *is* the id),
    so the id is the **parent directory** name — not the constant ``output`` filename stem, which
    would collide across all outputs. Falls back to the filename stem when there is no parent dir.
    """
    return (os.path.basename(os.path.dirname(str(fp)))
            or os.path.splitext(os.path.basename(str(fp)))[0])


def _read_footprint_geometry(geom_path):
    """Read the polygon + `properties.id` from a `geometry.geojson` (CRS84, one Feature),
    through the `fsd.storage` seam. Returns `(None, None)` if the FeatureCollection is empty."""
    import json

    with fs.open(str(geom_path), "r") as f:
        fc = json.load(f)
    features = fc.get("features") or []
    if not features:
        return None, None
    feat = features[0]
    geom = shapely.geometry.shape(feat["geometry"])
    feat_id = (feat.get("properties") or {}).get("id")
    return geom, feat_id


def cog_outputs_to_items(cog_filepaths, *, geometries=None, collection_id="fsd-inference",
                         band_names=None, dt=None) -> list[pystac.Item]:
    """Map inference-output COGs to STAC Items (spec 17 SO-6; used by run_inference, spec 18).

    One Item per output COG. `proj:*` is read straight from the COG we just wrote (cheap, no
    ambiguity). `dt` is the Item datetime for all outputs (defaults to now, UTC) — outputs are
    mosaics over a window, not a single acquisition.

    `geometries` (spec 28): an optional `{output_cog_filepath: geometry.geojson_path}` mapping —
    the **true S2-cell footprint** (CRS84, from the build manifest's `shapefilepath` column), used
    as the Item geometry/bbox instead of the raster bbox. This is a **deterministic, manifest-driven
    contract, not a per-item fallback**: when `geometries` is given, every `fp` in `cog_filepaths`
    must have a readable polygon entry — a missing/unreadable/empty one raises (a manifest that
    lists an output but no footprint is a real inconsistency; fail loud, don't silently box).
    `geometries=None` (the default) keeps the raster-bbox behavior, for geometry-less callers
    (unit tests; a bare list of COGs; pre-built folder/list inference modes with no manifest).
    """
    import datetime as _datetime

    from rasterio.warp import transform_bounds

    from fsd.raster import rio_open

    if dt is None:
        dt = _datetime.datetime.now(_datetime.timezone.utc)

    items: list[pystac.Item] = []
    for fp in cog_filepaths:
        with rio_open(fp) as src:
            epsg = src.crs.to_epsg() if src.crs else None
            shape = [src.height, src.width]
            transform = list(src.transform)[:6]

            if geometries is not None:
                geom_path = geometries.get(str(fp), geometries.get(fp))
                if geom_path is None:
                    raise ValueError(
                        f"cog_outputs_to_items: geometries has no entry for output COG {fp!r}; "
                        "the manifest-driven contract requires every output to have a footprint "
                        "(pass geometries=None to fall back to the raster bbox for ALL outputs)."
                    )
                try:
                    geom, feat_id = _read_footprint_geometry(geom_path)
                except (OSError, ValueError) as exc:
                    raise ValueError(
                        f"cog_outputs_to_items: could not read geometry {geom_path!r} for "
                        f"output COG {fp!r}: {exc}"
                    ) from exc
                if geom is None or geom.is_empty:
                    raise ValueError(
                        f"cog_outputs_to_items: geometry.geojson at {geom_path!r} (for {fp!r}) "
                        "has no readable polygon feature."
                    )
                item_id = _output_item_id(fp)
                if feat_id is not None and str(feat_id) != item_id:
                    raise ValueError(
                        f"cog_outputs_to_items: geometry.geojson id {feat_id!r} at {geom_path!r} "
                        f"disagrees with output item id {item_id!r} for {fp!r}."
                    )
                bbox = list(geom.bounds)
            else:
                bounds4326 = transform_bounds(src.crs, "EPSG:4326", *src.bounds, densify_pts=21)
                geom = shapely.geometry.box(*bounds4326)
                bbox = list(bounds4326)

        item = pystac.Item(
            id=_output_item_id(fp),
            geometry=shapely.geometry.mapping(geom),
            bbox=bbox,
            datetime=dt,
            properties={},
            collection=collection_id,
        )
        if epsg is not None:
            ProjectionExtension.ext(item, add_if_missing=True).epsg = epsg
        item.properties["proj:shape"] = shape
        item.properties["proj:transform"] = transform

        asset = pystac.Asset(
            href=str(fp), media_type=pystac.MediaType.COG, roles=["data"], title="output"
        )
        if band_names:
            asset.extra_fields["eo:bands"] = [{"name": b} for b in band_names]
        item.add_asset("output", asset)
        items.append(item)
    # STAC item ids must be unique: write_stac_catalog's normalize_hrefs maps id -> <id>/<id>.json,
    # so a collision silently overwrites all-but-one item on disk AND duplicates the collection link
    # (the spec-26 bug). fsd writes every output as <cube_id>/output.tif, so ids come from the parent
    # dir and are unique by construction; guard loudly if a layout ever breaks that invariant.
    ids = [it.id for it in items]
    if len(set(ids)) != len(ids):
        dupes = sorted({i for i in ids if ids.count(i) > 1})
        raise ValueError(
            f"cog_outputs_to_items: item ids are not unique ({dupes}); each output must live in "
            "its own per-cube folder (<cube_id>/output.tif)."
        )
    return items


def cog_outputs_to_items_from_manifest(input_csv_filepath, **kwargs) -> list[pystac.Item]:
    """Convenience wrapper (spec 28): build `geometries` from a `run_inference` build manifest
    (`input.csv`, columns `export_folderpath, shapefilepath, …`) and call `cog_outputs_to_items`.

    Only COGs that exist on disk are included (a manifest row's build may not have produced an
    output, e.g. a partial/resumed run). `kwargs` forwards to `cog_outputs_to_items`
    (`collection_id`, `band_names`, `dt`).
    """
    import pandas as pd

    with fs.open(str(input_csv_filepath), "r") as f:
        rows = pd.read_csv(f)
    geometries = {
        os.path.join(str(exp), "output.tif"): str(sp)
        for exp, sp in zip(rows["export_folderpath"], rows["shapefilepath"])
    }
    cogs = [cog for cog in geometries if fs.exists(cog)]
    return cog_outputs_to_items(cogs, geometries=geometries, **kwargs)


def items_to_rows(items: list[pystac.Item]):
    """Inverse mapping — reconstruct the `TileCatalog` columns from Items (round-trip check)."""
    import geopandas as gpd
    import pandas as pd

    rows = []
    for item in items:
        hrefs = [a.href for a in item.assets.values()]
        filenames = sorted(os.path.basename(h) for h in hrefs)
        folders = {os.path.dirname(h) for h in hrefs}
        source = next((lk.get_href() for lk in item.get_links(_SOURCE_LINK_REL)), None)
        # Spec 34: recover the declared offset/nodata from any asset's raster:bands
        # (all assets on one item share the same tile-level values, §1) — 0 if the
        # item predates the extension (no raster:bands asset at all).
        offset, nodata = 0, 0
        if RasterExtension.has_extension(item):  # item-level: hoisted out of the loop
            for asset in item.assets.values():
                bands = RasterExtension.ext(asset).bands
                if bands:
                    nodata = bands[0].nodata or 0
                    if bands[0].offset:
                        offset = bands[0].offset
        rows.append({
            "id": item.id,
            "satellite": item.collection_id,
            "timestamp": pd.to_datetime(item.datetime, utc=True),
            "s3url": source,
            "local_folderpath": folders.pop() if len(folders) == 1 else ",".join(sorted(folders)),
            "files": ",".join(filenames),
            "cloud_cover": item.properties.get("eo:cloud_cover"),
            "offset": offset,
            "nodata": nodata,
            "geometry": shapely.geometry.shape(item.geometry),
        })
    return gpd.GeoDataFrame(rows, geometry="geometry", crs="EPSG:4326")


# --- serialization -----------------------------------------------------------

def write_stac_catalog(
    items: list[pystac.Item],
    dst_folderpath: str,
    *,
    catalog_id: str = "fsd",
    collection_id: str | None = None,
    description: str = "fsd tile catalog (STAC export).",
) -> str:
    """Write a static, self-contained STAC catalog (catalog.json + collection + item JSONs).

    Returns the catalog.json path. Written through `fsd.storage`.
    """
    if not items:
        raise ValueError("write_stac_catalog: no items to write.")
    coll_id = collection_id or items[0].collection_id or "default"

    bboxes = [it.bbox for it in items if it.bbox]
    spatial = pystac.SpatialExtent([[
        min(b[0] for b in bboxes), min(b[1] for b in bboxes),
        max(b[2] for b in bboxes), max(b[3] for b in bboxes),
    ]])
    dts = [it.datetime for it in items if it.datetime]
    temporal = pystac.TemporalExtent([[min(dts), max(dts)]])

    collection = pystac.Collection(
        id=coll_id, description=description,
        extent=pystac.Extent(spatial=spatial, temporal=temporal),
    )
    collection.add_items(items)

    catalog = pystac.Catalog(id=catalog_id, description=description)
    catalog.add_child(collection)

    catalog.normalize_hrefs(str(dst_folderpath))
    catalog.save(catalog_type=pystac.CatalogType.SELF_CONTAINED, stac_io=_StorageStacIO())
    return os.path.join(str(dst_folderpath), "catalog.json")
