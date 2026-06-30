"""TileCatalog — read/append/filter the downloaded-tile catalog.

Spec: specs/02-catalog.md. GeoParquet, read/written via fsd.storage.

Columns: id (unique), satellite, timestamp (UTC), s3url, local_folderpath,
files (comma-joined band filenames), cloud_cover, geometry (EPSG:4326).
"""

from __future__ import annotations

import datetime

import geopandas as gpd
import pandas as pd
import shapely

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


class TileCatalog:
    def __init__(self, filepath: str):
        self.filepath = filepath

    def append(self, rows: list[dict]) -> None:
        """Upsert by id; union `files` for an existing tile (don't overwrite).

        A re-download of more bands extends the recorded `files` list rather than
        replacing it; all other columns take the newest value.
        """
        if not rows:
            return

        new = gpd.GeoDataFrame(rows, crs=CRS)
        # Normalize timestamp to tz-aware UTC for a stable on-disk dtype.
        new["timestamp"] = pd.to_datetime(new["timestamp"], utc=True)

        if fs.exists(self.filepath):
            existing = self.read()
            combined = pd.concat([existing, new], ignore_index=True)
        else:
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
        fs.write_parquet(self.filepath, out)

    def read(self) -> gpd.GeoDataFrame:
        """Return the full catalog as a GeoDataFrame."""
        gdf = fs.read_parquet(self.filepath)
        gdf["timestamp"] = pd.to_datetime(gdf["timestamp"], utc=True)
        return gdf

    def filter(
        self,
        shapes_gdf: gpd.GeoDataFrame,
        startdate: datetime.datetime,
        enddate: datetime.datetime,
    ) -> gpd.GeoDataFrame:
        """Date-range (inclusive) + spatial-overlap filter against the ROI union.

        Adds `area_contribution` (% of the ROI union each tile covers). This is
        exactly the query the datacube builder consumes.
        """
        gdf = self.read()

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
