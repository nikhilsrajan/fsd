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
# Sentinel Hub (catalog/STAC discovery)
SH_BASE_URL = "https://sh.dataspace.copernicus.eu"
SH_TOKEN_URL = (
    "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/"
    "openid-connect/token"
)
# S3-compatible object store (tile bytes). Just an endpoint to s3fs.
CDSE_S3_ENDPOINT_URL = "https://eodata.dataspace.copernicus.eu"
CDSE_S3_REGION = "default"

# CDSE caps concurrent S3 connections at 4.
# https://documentation.dataspace.copernicus.eu/Quotas.html
MAX_CONCURRENT_S3 = 4

# Rough size guard for the download safety check (~GB per tile).
APPROX_GB_PER_TILE = 0.725
