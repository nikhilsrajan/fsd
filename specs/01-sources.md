# Spec 01 — Sources (seam + CDSE)

Folds in: `cdseutils/{utils,sentinel2,constants,mydataclasses,evalscripts}.py`,
`fetch_satdata/download/download_sentinel2_from_s3.py`,
`fetch_satdata/core/sentinel2_via_s3.py`.

## Responsibility

Given an ROI + date range + bands, **discover** matching Sentinel-2 L2A tiles and
**download** the requested band files to disk, then hand the per-tile records to
the catalog module (`02-catalog.md`) for persistence.

## The source seam (thin)

A source is anything that can implement this contract (only CDSE in v1):

```python
def download(
    roi: gpd.GeoDataFrame | str,     # geometry or path
    startdate, enddate,
    bands: list[str],
    root_folderpath: str,            # where tiles land on disk
    catalog: TileCatalog,            # 02-catalog.md, appended in-place
    *,
    max_tiles: int,                  # safety guard (~700MB/tile)
    chunksize: int = 100,            # files per download+catalog-update batch
) -> DownloadResult                  # (successful_count, total_count)
```

> OQ-3: implement as an ABC (`sources/base.py: Source`) or just this documented
> function signature. Recommendation: documented signature now; promote to ABC
> when a 2nd source appears.

## CDSE implementation (`sources/cdse.py`)

Two CDSE subsystems, two credential pairs (both required), stored in one JSON:

- **Catalog search** — `sentinelhub.SentinelHubCatalog` (SH client id/secret).
  Base/token URLs in `config.py`. Returns per-tile: `id, timestamp, geometry,
  s3url, cloud_cover`. **No disk cache** (decision: always query live; the legacy
  cache is dropped).
- **Tile download** — via the **generic S3 transport** in `fsd.storage`
  (fsspec/`s3fs`), configured with the CDSE endpoint
  (`endpoint_url=https://eodata.dataspace.copernicus.eu`) + S3 keys. For each tile
  `.SAFE` s3url: `ls` the objects, select the requested band `.jp2` files
  (highest-res per band for L2A) + `MTD_TL.xml`, then `transfer(...)` them under
  `root_folderpath` (local in v1, blob/S3 later). **CDSE owns only discovery +
  S2 file-selection + endpoint config; the byte-transfer is provider-agnostic and
  reusable** (see `10-storage-and-scale.md`). No direct `boto3`.

### Behavior to preserve

- ROI → bbox via convex-hull union, reprojected to EPSG:4326 for the query.
- Download is the embarrassingly-parallel-over-tiles step but is **quota-bound**
  (CDSE caps concurrency at 4), so it stays one coordinated job — it is *not* the
  thing Azure Batch fans out (that's datacube creation; see `10-storage-and-scale.md`).
- Keep only tiles intersecting the ROI; **assert tile `id` uniqueness** (legacy
  raised if violated — keep the guard).
- Optional `max_cloudcover_threshold` filter.
- `max_tiles` guard: refuse (raise) if matched tiles exceed it; message estimates
  GB (~0.725 GB/tile).
- Download in chunks; after each chunk, append successes to the catalog so a crash
  doesn't lose progress. Skip files already on disk (idempotent re-runs).
- Parallel S3 downloads, but cap concurrency at CDSE's limit (**4** connections).

## Credentials

```python
@dataclass
class CdseCredentials:
    sh_client_id, sh_client_secret      # catalog
    s3_access_key, s3_secret_key        # download
# load_from_json(path) / to_json(path)
```

## Drops vs legacy (record in DROPPED.md)

- L1C path, `evalscripts`, Sentinel-Hub **Process API** download
  (`download_data*`, the WMS-style request) — v1 only does S3 tile download.
- `username/password` CDSE creds (already unused in legacy).
- **Catalog-query disk cache** (legacy cached SH search results) — removed.

## Out of scope / deferred

- Any non-CDSE source (Planet, MPC/STAC, GEE).

## Tests (smoke)

- `CdseCredentials` round-trips through JSON.
- s3url ↔ s3path parsing and band-filename parsing (pure functions, no network).
- Tile selection picks highest-res band asset for L2A.
- (Networked, opt-in/marked) tiny 1-tile download.
