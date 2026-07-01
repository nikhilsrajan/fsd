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

Two CDSE subsystems. Discovery is **anonymous**; only download needs credentials:

- **Catalog search** — the **CDSE STAC API** (`pystac-client`,
  `config.CDSE_STAC_URL`), **anonymous — no credentials**. Returns per-tile:
  `id, timestamp, geometry, s3url, cloud_cover`. Crucially, each STAC item's
  `assets` already carry the **per-band S3 `href`s**, so file-selection reads them
  directly — we **never list a `.SAFE` over S3** (that recursive listing was the
  flaky path; see `../BUGS.md` BUG-001). **No disk cache** (always query live).
  _(Replaces the legacy `sentinelhub.SentinelHubCatalog`, which needed SH OAuth
  creds and the SH base/token URLs — all dropped.)_
- **Tile download** — via the **generic S3 transport** in `fsd.storage`
  (fsspec/`s3fs`), configured with the CDSE endpoint (`config.CDSE_S3_ENDPOINT_URL`,
  OTC-pinned) + S3 keys. For each STAC item: pick the requested bands' highest-res
  asset hrefs (+ the `granule_metadata` asset = `MTD_TL.xml`), then `transfer(...)`
  them under `root_folderpath` (local in v1, blob/S3 later), each with **fail-fast
  retry** on CDSE's transient S3 auth errors (BUG-001). **CDSE owns only discovery +
  S2 file-selection + endpoint config; the byte-transfer is provider-agnostic and
  reusable** (see `10-storage-and-scale.md`). No direct `boto3`.

### Behavior to preserve

- ROI → union geometry, reprojected to EPSG:4326, passed as STAC `intersects`
  (precise ROI intersection re-applied after the query).
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

Discovery (STAC) is **anonymous**; only `download` needs credentials — just the
**S3 access/secret keys** (tile bytes). The `sh_client_*` fields are retained
(loaded from the legacy JSON, not required for discovery) in case another CDSE
service needs them later.

```python
@dataclass
class CdseCredentials:
    sh_client_id, sh_client_secret      # retained; NOT needed for STAC discovery
    s3_access_key, s3_secret_key        # download (the only creds actually used)
    s3_keys_expire: str | None = None   # optional ISO date, informational
    note: str | None = None             # optional free text

    @classmethod
    def from_json(path) -> CdseCredentials   # reads the legacy cdse_credentials.json keys
    def to_json(path) -> None
    @classmethod
    def from_env() -> CdseCredentials        # CDSE_SH_CLIENT_ID / _SECRET / CDSE_S3_ACCESS_KEY / _SECRET
    def s3_storage_options() -> dict         # {key, secret, client_kwargs:{endpoint_url}} for fsd.storage
    def require_s3() -> None                  # raise if S3 keys missing (download's check)
    def require_complete() -> None            # raise if any of the 4 core fields is missing
    def is_expired(as_of=None) -> bool | None
```

Decisions (2026-07-01, agreed with user):
- **Canonical local format = a gitignored JSON file** (`secrets/cdse_credentials.json`),
  not a `mysecrets.py`. Data, not importable code; matches the user's existing file.
  `from_json` reads the **legacy JSON keys** (`sh_clientid`, `sh_clientsecret`,
  `s3_access_key`, `s3_secret_key`) so the current file works unchanged, tolerates
  extra keys, and picks up optional `s3_keys_expire` / `note`.
- **`from_env` for the cloud/Batch path** — inject secrets as env vars (or a secret
  manager) rather than shipping a file to a node. Local dev → JSON; cloud → env; same
  object. Serves the "Azure Batch, no lock-in" goal.
- **Never log/print secret values.** Custom `__repr__` masks them (shows set/unset +
  expiry/note only). Credential-file reads go through `fsd.storage` like all file I/O.
- Optional expiry: `download` warns if `is_expired()` (keys on CDSE do expire) — this
  replaces the "expiry comment" the legacy `mysecrets.py` carried.

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
