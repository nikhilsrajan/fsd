# Spec 14 — COG-on-download (CDSE ingest)

> **Status: signed off + implemented (2026-07-04).** First **production** `src/fsd/` change out
> of the COG track (specs 12/13 were benchmark-only). Turns the spec-13 finding (COG is
> decode-cheap, lossless, ~1.58×–3.46× faster build) into the default ingest format:
> `sources.cdse.download(cog=True)` converts each fetched JP2 band → COG on the way to disk,
> **with overviews** (for the future TiTiler XYZ goal). `cog=False` keeps native JP2.
> New `src/fsd/raster/cog.py::to_cog` (lossless, atomic, NBITS=16 for uint16); `config` COG
> profile constants; prep script refactored to share `to_cog`. Guarded to local `root_folderpath`.
> **Real smoke (2026-07-04):** a 10980² B04 JP2 → COG bit-identical, overviews [2,4,8,16],
> DEFLATE/tiled, 15.5 s. 119 tests, ruff clean. See `CHANGES.md`.

## Motivation
Spec 13 settled that the datacube build's `load_images` cost is **JP2 wavelet-decode-bound**:
storing tiles as COG (DEFLATE, tiled) makes reads 1.58×–3.46× faster wall (up to 9.42× on
`load_images`), read cost flat vs concurrency, **losslessly**, for ~+23% base storage. The
experiment proved it by A/B-ing a *parallel* COG dataset (no core change). This spec makes COG
the **native on-disk format at ingest**, so every download is build-fast from the start — no
second conversion pass, no duplicate JP2+COG trees.

The user also wants downloaded COGs to carry **overviews** so the archive is directly usable for
**XYZ/WMTS tiling (TiTiler)** later (TODO #14). Overviews are *not* used by the datacube build
(it reads full-res) — they are a deliberate storage cost for downstream serving.

## What changes (small, contained)
1. **New module `src/fsd/raster/cog.py`** — one canonical `to_cog(src, dst, ...)` (local raster →
   COG, lossless, atomic). This is the single home for the COG creation profile.
2. **`sources/cdse.py`** — `download(..., cog: bool = True)` and `download_resume(..., cog=True)`;
   band files are transferred then converted to `Bxx.tif`; the catalog records `.tif`.
3. **`config.py`** — COG profile constants (compress/predictor/blocksize/overviews).
4. **`benchmarks/prep_cog_dataset.py`** — refactor its `_cog_opts`/`_convert_file` to delegate to
   `fsd.raster.cog` (one source of truth; behavior identical — prep stays `OVERVIEWS="NONE"`).

The read path is already format-agnostic (`rasterio.open` sniffs JP2 vs GeoTIFF; spec 13). So
**builder / datacube / raster ops / workflows are untouched** — a `.tif` catalog flows through
unchanged.

## `to_cog` — the conversion primitive (`src/fsd/raster/cog.py`)
```python
def to_cog(src_path, dst_path, *, overviews=config.COG_OVERVIEWS,
           compress=config.COG_COMPRESS, predictor=config.COG_PREDICTOR,
           blocksize=config.COG_BLOCKSIZE, verify=False) -> int:
    """Convert a LOCAL raster to a Cloud-Optimized GeoTIFF. Lossless. Atomic. Returns bytes."""
```
- **Lossless by construction:** `COMPRESS=DEFLATE`, `PREDICTOR=2` (reversible integer
  differencing), and — for `uint16` sources (S2 reflectance declares NBITS=15) — **`NBITS=16`**
  (promotes the *declared* depth only; pixels unchanged). Applied conditionally on `src` dtype, as
  in spec 13. SCL (uint8) and other depths skip NBITS.
- **Overviews:** `OVERVIEWS="AUTO"` by default (COG driver builds power-of-two overviews) — the
  ingest default. `"NONE"` for callers that don't want them (prep script).
- **Atomic:** writes to a sibling `dst.part` then `os.replace` onto `dst` — so a crash never
  leaves a truncated `.tif` that the resume path would mistake for done (mirrors
  `storage.transfer`'s `.part` discipline).
- **`verify=True`** (off by default) reads both rasters back and asserts `np.array_equal` — used in
  tests and available for a paranoid ingest; skipped in production for speed (conversion is
  deterministic + proven lossless in spec 13).
- **Raster-I/O exception (specs/10):** reads/writes **local** paths via rasterio/GDAL, not fsspec —
  the same documented carve-out as all pixel I/O.

Config constants (new, `config.py`):
```python
COG_COMPRESS   = "DEFLATE"
COG_PREDICTOR  = 2
COG_BLOCKSIZE  = 512
COG_OVERVIEWS  = "AUTO"   # materialize overviews at ingest (downstream XYZ/TiTiler, TODO #14)
```

## Download flow (`sources/cdse.py`)
`download(..., cog: bool = True)`:
- **`cog=True` (default):** each band file is fetched as JP2 to a **local staging sibling**
  (`Bxx.tif.src.jp2`) via `storage.transfer`, converted with `to_cog` → `Bxx.tif`, and the staging
  JP2 removed (`storage.rm`). The catalog `files` records `Bxx.tif`. `MTD_TL.xml` is a plain
  transfer (non-raster, unchanged).
- **`cog=False`:** current behavior verbatim — JP2 lands as `Bxx.jp2`, catalog records `.jp2`.

Concretely:
- `_select_item_files(item, bands, root, *, cog)` — band `dst` = `Bxx.tif` if `cog` else `Bxx.jp2`
  (the S3 `href` is still the `.jp2` asset either way); sidecar unchanged.
- `_download_one(src, dst, s3opts, *, cog)` — idempotent skip keys on the **final** path (`.tif`
  when cog). On a miss: if `cog and src endswith .jp2` → transfer-to-staging + `to_cog` +
  remove-staging; else plain `transfer`. Returns `(ok, reason)` as today, so
  `_append_downloaded` / circuit-breaker / progress are unchanged.

**Idempotency / resume:** the skip check is `exists(final) and size(final) > 0`. A crash between
transfer and convert leaves only the staging JP2 (final `.tif` absent) → the next pass re-fetches
and re-converts (cheap, correct). No half-written `.tif` survives (atomic replace).

## Seam boundary — local dst only (v1)
COG conversion needs a **local** file for GDAL. If `cog=True` and `root_folderpath` is a **remote**
fsspec URL (`s3://`, `az://`, …), `download` **raises a clear error** at the top (before any
fetch): *"COG-on-download needs a local root_folderpath in v1; use cog=False, or the future
stage-local→convert→upload path."* This is the honest seam edge — the Azure/Blob path
(stage-locally, convert, `storage.put`) is deferred to the Batch milestone (TODO), not faked here.
Local ingest (today's reality) works fully.

## Cost & performance notes (call out, don't re-measure)
- **Storage:** base COG ≈ 1.225× JP2 (spec 13); **with overviews ≈ +38% on top → ~1.7× JP2**.
  This is the price of tiling-readiness the user chose; flagged in the download report / docs.
- **CPU at download time:** conversion (DEFLATE + overview build) ran **inline in the download
  worker threads** (`MAX_CONCURRENT_S3=4`) at this spec's implementation — GDAL's `to_cog` in fact
  **holds the GIL** (not releases it, contra the original note here), so a few converting threads
  starved the rest and collapsed download concurrency. **Decoupled onto a dedicated convert process
  pool → spec 25** (2026-07-11): a `MAX_CONCURRENT_S3`-wide transfer thread pool now runs
  continuously against a separate `MAX_CONVERT_PROCS`-wide process pool for conversion, bounded by a
  disk-aware `sem_staged` backpressure cap. See `specs/25-download-convert-redesign.md` + CHANGES.md.

## Validation
- **Unit (pure/local, no network):**
  - `to_cog` on a synthetic `uint16` GeoTIFF → output opens as a COG, is **bit-identical** to the
    source (`verify`), and **has overviews** with `OVERVIEWS="AUTO"` / **none** with `"NONE"`.
  - `to_cog` atomicity: no `.part` left on success; failure leaves no `.tif`.
  - `_select_item_files(cog=True)` → band dst ends `.tif`; `cog=False` → `.jp2` (duck-typed item).
  - `_download_one(cog=True)` with `storage.transfer` monkeypatched to drop a small synthetic
    raster at the staging path → produces `Bxx.tif`, removes the staging JP2, records ok; a second
    call **skips**. (Uses a `.jp2`-named GeoTIFF fixture so no OpenJPEG codec is needed.)
  - Non-local `root_folderpath` + `cog=True` → raises the seam error.
- **Manual runbook** (`tests/manual/realdata.md` addendum or the download runbook): a tiny real
  CDSE download with `cog=True` → confirm `.tif` COGs on disk (`gdalinfo` shows `LAYOUT=COG`,
  overviews present), catalog lists `.tif`, and a datacube build over them succeeds (QGIS eyeball
  parity vs a `cog=False` build).
- **Regression:** full `pytest` + `ruff` green; the existing download/datacube/workflow tests
  unchanged (cog defaults on but they use synthetic paths / `cog` is exercised in the new tests).

## Explicitly OUT (deferred)
- Remote-dst (Blob/S3) COG conversion — stage-local→convert→upload (Azure milestone).
- Sourcing AWS `sentinel-2-l2a-cogs` instead of converting CDSE JP2 (a different discovery source;
  TODO #11 source-extension territory).
- A conversion process pool / decoupled CPU fan-out (perf tuning) → **DONE, spec 25**.
- Re-downloading / migrating the existing `satellite_benchmark` JP2 archive to COG (this changes
  *new* ingest only; a bulk migration is a separate op).
- ZSTD/LZW alternatives, offset/DN decisions (TODO #10), STAC-geoparquet (TODO #14).

## Docs to update on implement
`CHANGES.md` (download now COG-by-default, kept-but-changed catalog `files` = `.tif`),
`TODO.md` (mark the "adopt COG in ingest" lever done; add the process-pool + remote-dst follow-ups),
`PROGRESS.md`, memory `fsd-status`. Runbook addendum as above.
