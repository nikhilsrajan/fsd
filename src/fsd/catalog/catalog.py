"""TileCatalog — read/append/filter the downloaded-tile catalog.

Spec: specs/02-catalog.md; schema per spec 34 §5 `[G4]` (retires spec 32's
`boa_add_offset` column — no back-compat shim, see `read()`).

Columns: id (unique), satellite, timestamp (UTC), s3url, local_folderpath,
files (comma-joined band filenames), cloud_cover, offset (additive declared
radiometric offset for reflectance bands, spec 34 §1; 0 when a source has no
such concept), nodata (declared nodata value, spec 34 §1c; defaults 0),
geometry (EPSG:4326).
"""

from __future__ import annotations

import datetime

import geopandas as gpd
import pandas as pd
import shapely

from fsd.catalog import declaration as declaration_module
from fsd.catalog.declaration import SourceDeclaration
from fsd.storage import fs

# On-disk column order (spec 02). geometry is always last for GeoParquet.
COLUMNS = [
    "id",
    "satellite",
    "timestamp",
    "s3url",
    "local_folderpath",
    "files",
    "cloud_cover",
    "offset",
    "nodata",
    "geometry",
]

CRS = "EPSG:4326"


def _union_files(*files_values: str) -> str:
    """Union comma-joined band-filename lists into one sorted, deduped string."""
    names: set[str] = set()
    for value in files_values:
        if value:
            names.update(part for part in str(value).split(",") if part)
    return ",".join(sorted(names))


def filter_gdf(
    gdf: gpd.GeoDataFrame,
    shapes_gdf: gpd.GeoDataFrame,
    startdate: datetime.datetime,
    enddate: datetime.datetime,
) -> gpd.GeoDataFrame:
    """Date-range (inclusive) + spatial-overlap filter over an **already-read** catalog.

    The pure half of `TileCatalog.filter`, split out so a caller filtering *many*
    shapes against *one* catalog can read the file once instead of once per shape.
    That is not a micro-optimisation on a remote catalog: `create_datacube.setup`
    over 900 shapes was 900 full downloads of the same `abfss://` parquet (~106 MiB
    of redundant transfer, ~900 round-trips) because `filter` re-read the file on
    every call.

    Does not mutate `gdf` — the returned slice is a `.copy()` before the
    `area_contribution` column is added, so one read is safely shared across calls.
    `.attrs` (the spec-35 declaration stamp) propagates to the slice through pandas'
    `__finalize__`, exactly as it did when each call re-read the file.
    """
    startdate = pd.to_datetime(startdate, utc=True)
    enddate = pd.to_datetime(enddate, utc=True)

    in_range = gdf[(gdf["timestamp"] >= startdate) & (gdf["timestamp"] <= enddate)]

    # ROI union in the catalog CRS.
    union_shape = shapely.unary_union(shapes_gdf.to_crs(gdf.crs)["geometry"])

    overlapping = in_range[in_range.intersects(union_shape)].copy()

    union_area = union_shape.area
    overlapping["area_contribution"] = overlapping["geometry"].apply(
        lambda g: g.intersection(union_shape).area / union_area * 100
    )

    return overlapping


class TileCatalog:
    def __init__(self, filepath: str, declaration: SourceDeclaration | None = None):
        self.filepath = filepath
        # `append`'s default when its own `declaration=` kwarg is None (spec 35 §4).
        self._declaration_default = declaration

    def _existing_stamp(self) -> SourceDeclaration | None:
        """The declaration actually stamped on the on-disk file, or `None` if the
        file doesn't exist or carries no stamp (footer-only, cheap)."""
        if not fs.exists(self.filepath):
            return None
        raw = fs.peek_parquet_attrs(self.filepath).get(declaration_module.ATTRS_KEY)
        return declaration_module.from_json(raw) if raw is not None else None

    @property
    def declaration(self) -> SourceDeclaration | None:
        """The declaration a build against this catalog would resolve to right
        now: the on-disk stamp if the file exists, else the constructor default
        (spec 35 §4)."""
        if fs.exists(self.filepath):
            return self._existing_stamp()
        return self._declaration_default

    def append(self, rows: list[dict], declaration: SourceDeclaration | None = None) -> None:
        """Upsert by id; union `files` for an existing tile (don't overwrite).

        A re-download of more bands extends the recorded `files` list rather than
        replacing it; all other columns take the newest value.

        `declaration` (spec 35 §4) stamps the collection-level `SourceDeclaration`
        on this catalog file (constructor's `declaration=` is the default when this
        kwarg is `None`). One catalog file = one collection = one declaration:
        appending a declaration that differs from the one already stamped on an
        existing catalog raises `ValueError`; appending with `declaration=None` to
        an already-stamped catalog preserves the existing stamp (an fsd-agnostic
        top-up cannot erase it).
        """
        if not rows:
            return

        effective = declaration if declaration is not None else self._declaration_default

        new = gpd.GeoDataFrame(rows, crs=CRS)
        # Normalize timestamp to tz-aware UTC for a stable on-disk dtype.
        new["timestamp"] = pd.to_datetime(new["timestamp"], utc=True)
        # offset/nodata are per-row declared values (spec 34 §1); a source that
        # doesn't set one (no radiometric-offset concept, or nodata already
        # implicit) defaults to 0 rather than fail column selection below. This is
        # an ergonomic default for a *fresh* append, not a legacy-catalog shim
        # (see `read()`, which does not backfill these).
        if "offset" not in new.columns:
            new["offset"] = 0
        if "nodata" not in new.columns:
            new["nodata"] = 0

        if fs.exists(self.filepath):
            existing_stamp = self._existing_stamp()
            if effective is not None and existing_stamp is not None and effective != existing_stamp:
                raise ValueError(
                    f"TileCatalog.append: declaration conflict at {self.filepath!r} -- "
                    f"existing stamp {existing_stamp!r} != new {effective!r}. One "
                    "catalog file is one collection with one declaration; write the "
                    "conflicting rows to a different catalog file instead."
                )
            stamp = effective if effective is not None else existing_stamp
            existing = self.read()
            combined = pd.concat([existing, new], ignore_index=True)
        else:
            stamp = effective
            combined = new

        # Union `files` across rows sharing an id (oldest..newest order).
        merged_files = combined.groupby("id")["files"].agg(
            lambda s: _union_files(*s.tolist())
        )

        # Keep the last (newest) row per id for every other column...
        deduped = combined.drop_duplicates(subset="id", keep="last").set_index("id")
        # ...then overwrite `files` with the unioned value.
        deduped["files"] = merged_files
        out = deduped.reset_index()

        out = gpd.GeoDataFrame(out[COLUMNS], geometry="geometry", crs=CRS)
        if stamp is not None:
            declaration_module.to_attrs(out, stamp)
        fs.write_parquet(self.filepath, out)

    def read(self) -> gpd.GeoDataFrame:
        """Return the full catalog as a GeoDataFrame.

        **No back-compat shim (spec 34 `[G4]`):** a catalog written before the
        `offset`/`nodata` columns existed (spec 32's `boa_add_offset` schema) is
        NOT patched up here — it is disposable and must be re-ingested (spec 34
        "Data" section), not silently defaulted, so a stale catalog fails loudly
        downstream (`flatten_catalog`/`build_datacube`) instead of building a cube
        against unfilled/wrong radiometry.
        """
        gdf = fs.read_parquet(self.filepath)
        gdf["timestamp"] = pd.to_datetime(gdf["timestamp"], utc=True)
        return gdf

    def to_stac(self, dst_folderpath: str, **kwargs) -> str:
        """Export the catalog as a static, self-contained STAC catalog (spec 17).

        Additive interchange view — the GeoParquet stays the query format. Returns the
        catalog.json path. See `fsd.catalog.stac`.
        """
        from fsd.catalog import stac

        items = stac.tile_catalog_to_items(self.read(), **kwargs)
        return stac.write_stac_catalog(items, dst_folderpath, declaration=self.declaration)

    def filter(
        self,
        shapes_gdf: gpd.GeoDataFrame,
        startdate: datetime.datetime,
        enddate: datetime.datetime,
    ) -> gpd.GeoDataFrame:
        """Date-range (inclusive) + spatial-overlap filter against the ROI union.

        Adds `area_contribution` (% of the ROI union each tile covers). This is
        exactly the query the datacube builder consumes.

        Reads the catalog file on **every** call. Filtering many shapes against one
        catalog should read once and call `filter_gdf` per shape instead.
        """
        return filter_gdf(self.read(), shapes_gdf, startdate, enddate)
