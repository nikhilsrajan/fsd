# Spec 02 — Tile catalog (file-based)

Folds in: catalog-writing parts of `core/sentinel2_via_s3.py` and the
*file-mode* of `core/catalogmanager.py` (SQLite parts dropped).

## Responsibility

A single file recording which tiles have been downloaded and where their band
files live on disk. Read/append/filter — no concurrency-heavy DB layer.

## Format

**GeoParquet** (decided). Read/written via `fsd.storage` (fsspec) so the catalog
file may live locally or on blob/S3. Columns:

| col | type | notes |
|-----|------|-------|
| `id` | str | tile id, **unique** (primary key) |
| `satellite` | str | e.g. `sentinel-2-l2a` |
| `timestamp` | datetime (UTC) | acquisition time |
| `s3url` | str | source `.SAFE` url |
| `local_folderpath` | str | absolute folder holding band files |
| `files` | str | comma-joined band filenames present (e.g. `B02.jp2,...,SCL.jp2`) |
| `cloud_cover` | float | from catalog search |
| `geometry` | polygon | tile footprint, EPSG:4326 |

## API

```python
class TileCatalog:
    def __init__(self, filepath: str): ...
    def append(self, rows: list[dict]) -> None        # upsert by id; merge `files`
    def read(self) -> gpd.GeoDataFrame
    def filter(self, shapes_gdf, startdate, enddate) -> gpd.GeoDataFrame
        # date BETWEEN + spatial overlap; adds `area_contribution` (% of ROI)
```

## Behavior to preserve

- Appending the same tile with new band files **unions** the `files` list
  (re-download of more bands extends, not overwrites).
- `filter` is the exact query the datacube builder consumes (date range inclusive,
  spatial overlay against ROI union, per-tile area contribution).

## Drops vs legacy

- SQLite `CatalogManager`/`sqlite_db_utils`, `DTYPE_*` machinery,
  `configurations.db`, `geometries.db`, datacube-catalog/registry DBs.
- The `last_update` bookkeeping column unless we find we need it.

## Tests

- append → read round-trip; `files` union on re-append.
- `filter` returns only in-range, overlapping tiles with correct
  `area_contribution`.
