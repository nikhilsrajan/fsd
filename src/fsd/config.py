"""Shared constants and defaults.

These are decided contracts (see specs/00-overview.md §6), not implementation
logic, so they are filled in. Anything requiring real logic lives in its module.
"""

import os

# --- Satellite ---------------------------------------------------------------
SATELLITE_S2L2A = "sentinel-2-l2a"

# All Sentinel-2 L2A bands available from CDSE.
S2L2A_ALL_BANDS = [
    "B01", "B02", "B03", "B04", "B05", "B06", "B07",
    "B08", "B8A", "B09", "B11", "B12", "SCL",
]

# Default bands used by the demo pipeline (demo_01_data_prep).
BANDS_DEFAULT = ["B02", "B03", "B04", "B05", "B06", "B07", "B08", "B11", "B12", "SCL"]

# --- Datacube defaults -------------------------------------------------------
SCL_MASK_CLASSES = [
    0,   # No data
    1,   # Saturated / defective
    3,   # Cloud shadows
    7,   # Unclassified
    8,   # Cloud medium probability
    9,   # Cloud high probability
    10,  # Thin cirrus
]
MOSAIC_DAYS = 20
# Mosaic window scheme (spec 15). "calendar" buckets acquisitions into fixed calendar
# windows anchored at the caller's startdate — so every datacube built over the same
# startdate/enddate/mosaic_days shares an identical `timestamps` axis regardless of
# which tiles/orbits/zones a shape hits (required to `flatten` across shapes). Empty
# windows are emitted as all-nodata slices, labels are window-start boundaries.
# "acquisition" = legacy behavior (windows track actual acquisition dates; labels =
# first acquisition per window; empty windows skipped).
MOSAIC_SCHEME = "calendar"
REFERENCE_BAND = "B08"   # 10 m; used for resampling/merge reference
NODATA = 0
MAX_TIMEDELTA_DAYS = 5   # acceptable gap when checking for missing acquisitions

# --- Radiometry / ingest normalization (spec 34) -----------------------------
# ESA S2 L2A: reflectance = (DN + offset) / QUANTIFICATION_VALUE. `offset` is the
# per-item declared value (0, or -1000 for processing baseline >= 04.00); this
# scale is the constant half of the pair, stamped into the on-disk COG GDAL tag
# AND STAC raster:bands (spec 34 §1a) so unscale=true (titiler) yields physical
# reflectance regardless of which baseline an item was processed with.
S2_REFLECTANCE_SCALE = 1 / 10000

# --- CDSE endpoints ----------------------------------------------------------
# STAC catalog (discovery). Anonymous — no credentials needed. Queried via
# pystac-client. Each item's `assets` give the per-band S3 hrefs directly, so we
# never list the .SAFE over S3 (see BUGS.md BUG-001).
CDSE_STAC_URL = "https://stac.dataspace.copernicus.eu/v1/"
# S3-compatible object store (tile bytes). Just an endpoint to s3fs. The OTC-pinned
# host reduces load-balancer routing variance vs the GSLB alias (BUG-001).
CDSE_S3_ENDPOINT_URL = "https://eodata.ams.dataspace.copernicus.eu"
CDSE_S3_REGION = "default"

# CDSE caps concurrent S3 connections at 4.
# https://documentation.dataspace.copernicus.eu/Quotas.html
MAX_CONCURRENT_S3 = 4

# --- MPC (Microsoft Planetary Computer) endpoints (spec 32) -------------------
# STAC catalog (discovery). Anonymous by default (optional PC_SDK_SUBSCRIPTION_KEY
# env var, read by the `planetary-computer` package itself, raises rate limits).
# Assets are already COG on Azure — download is a pure byte-copy, no conversion.
MPC_STAC_URL = "https://planetarycomputer.microsoft.com/api/stac/v1"

# Phase-1 default concurrency for the (no-convert) MPC transfer pool — a single
# tile/band runbook is trivial either way; kept small and hotspot-friendly.
MPC_MAX_CONCURRENT = 4

# Concurrency for `workflows.create_datacube.setup`'s per-shape control-file writes.
# Unlike MAX_CONCURRENT_S3 (a CDSE *credential* cap) this bounds nothing but our own
# round-trips: each shape is ~4-7 tiny blob calls whose cost is pure latency, so the
# loop is latency-bound and scales with threads. Measured 2026-07-22 on `rise`: 900
# shapes serially = ~1.8 s/shape (~27 min) with the catalog already read once.
SETUP_MAX_CONCURRENT = 16

# S3 transport timeouts (seconds). Without these a stalled connection hangs a worker
# forever during a flaky CDSE window (BUG-001); with them it raises and our retry
# layer handles it. read_timeout is per-socket-read, not total transfer time.
S3_CONNECT_TIMEOUT = 10
S3_READ_TIMEOUT = 30

# How often download(progress=True) prints a newline progress line (seconds).
PROGRESS_EVERY_S = 5

# How often the download submit-loop re-checks the stop-file (seconds). Decoupled from
# PROGRESS_EVERY_S and much shorter: os.path.exists is cheap, and a shorter interval cuts
# how far past a `touch <stop-file>` new submissions keep starting (the in-flight drain is
# separate — see download()'s cooperative-stop docstring).
STOP_CHECK_EVERY_S = 1.0

# Rough size guard for the download safety check (~GB per tile).
APPROX_GB_PER_TILE = 0.725

# CDSE's rolling 30-day S3 transfer quota (spec 37 D1/D7): past this, every transfer
# drops to 1 MB/s / 1 connection. https://documentation.dataspace.copernicus.eu/Quotas.html
CDSE_MONTHLY_QUOTA_GB = 12 * 1000

# --- COG conversion (convert-on-download; spec 14) ---------------------------
# Native on-disk format at ingest. DEFLATE + PREDICTOR=2 is fully lossless
# (reversible integer differencing); uint16 S2 reflectance declares NBITS=15, which
# PREDICTOR=2 rejects, so to_cog promotes the *declared* depth to NBITS=16 (pixels
# unchanged) — see specs/13, specs/14. Overviews are materialized at ingest for the
# downstream XYZ/WMTS (TiTiler) goal; the datacube build reads full-res and never
# uses them (they cost ~+38% on top of base COG).
COG_COMPRESS = "DEFLATE"
COG_PREDICTOR = 2
COG_BLOCKSIZE = 512
COG_OVERVIEWS = "AUTO"   # "AUTO" builds overviews; "NONE" skips them

# --- Convert process pool (spec 25) -------------------------------------------
# Convert-on-download runs GDAL COG-translate (GIL-holding, CPU-bound) in a PROCESS pool,
# decoupled from the 4 transfer threads (spec 25). Knee is 8 workers (migration report).
MAX_CONVERT_PROCS = min(os.cpu_count() or 1, 8)

# Staging backpressure is sized at download() START from FREE DISK (not a static constant): it is a
# safety CAP, not a throughput lever (D5). Throughput plateaus once the buffer keeps both pools fed.
STAGING_DISK_FRACTION = 0.25   # use at most 25% of free space on root_folderpath for in-flight staging
STAGING_ITEM_GB = 0.2          # rough disk per in-flight band file (the JP2 + its COG coexist mid-convert)
