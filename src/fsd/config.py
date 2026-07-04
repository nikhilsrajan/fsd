"""Shared constants and defaults.

These are decided contracts (see specs/00-overview.md §6), not implementation
logic, so they are filled in. Anything requiring real logic lives in its module.
"""

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
REFERENCE_BAND = "B08"   # 10 m; used for resampling/merge reference
NODATA = 0
MAX_TIMEDELTA_DAYS = 5   # acceptable gap when checking for missing acquisitions

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

# S3 transport timeouts (seconds). Without these a stalled connection hangs a worker
# forever during a flaky CDSE window (BUG-001); with them it raises and our retry
# layer handles it. read_timeout is per-socket-read, not total transfer time.
S3_CONNECT_TIMEOUT = 10
S3_READ_TIMEOUT = 30

# How often download(progress=True) prints a newline progress line (seconds).
PROGRESS_EVERY_S = 5

# Rough size guard for the download safety check (~GB per tile).
APPROX_GB_PER_TILE = 0.725

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
