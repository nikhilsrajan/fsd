"""TileCatalog — read/append/filter the downloaded-tile catalog.

Spec: specs/02-catalog.md. GeoParquet, read/written via fsd.storage.

Columns: id (unique), satellite, timestamp (UTC), s3url, local_folderpath,
files (comma-joined band filenames), cloud_cover, geometry (EPSG:4326).
"""

from __future__ import annotations

import datetime


class TileCatalog:
    def __init__(self, filepath: str):
        self.filepath = filepath

    def append(self, rows: list[dict]) -> None:
        """Upsert by id; union `files` for an existing tile (don't overwrite)."""
        raise NotImplementedError

    def read(self):
        """Return the full catalog as a GeoDataFrame."""
        raise NotImplementedError

    def filter(self, shapes_gdf, startdate: datetime.datetime, enddate: datetime.datetime):
        """Date-range (inclusive) + spatial-overlap filter against the ROI union.

        Adds `area_contribution` (% of ROI each tile covers). This is exactly the
        query the datacube builder consumes.
        """
        raise NotImplementedError
