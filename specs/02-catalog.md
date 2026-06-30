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

## Workflow integration (clarified 2026-07-01)

`filter(shape, startdate, enddate)` **is** the per-shape query the datacube
**setup** stage (spec 08) runs to materialise each subset catalog: date-range +
spatial overlap, with `area_contribution` persisted. The builder (spec 03) then
reads the subset and uses the stored `area_contribution` to pick `dst_crs` — it
does *not* re-filter. (Legacy recomputed `area_contribution` inside the builder via
`calculate_area_contribution`; folding it into `filter` is a small clean-up.)

## Real-catalog notes (from `satellite/.../catalog_sentinel-2.geojson`)

The legacy on-disk catalog is **GeoJSON** (fsd writes GeoParquet) and carries a
`last_update` column fsd still drops. Observed: `id` includes the `.SAFE` suffix and
is unique; `geometry` may be a `MultiPolygon`; `files` is a comma-joined band list
that includes `MTD_TL.xml` and `SCL.jp2`. A real-data notebook will need to read the
GeoJSON and (optionally) convert to the fsd GeoParquet catalog; `local_folderpath`
in the provided file is stale and must be corrected to the `satellite/` location.
