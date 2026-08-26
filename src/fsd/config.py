"""Shared constants and defaults, and the user-level config loader (spec 54).

The constants above the "User config" section are decided contracts (see
specs/00-overview.md §6), not implementation logic, so they are filled in. Anything
requiring real logic lives in its module — except the user config below, which is small
enough (D2) to live here rather than earn its own module.
"""

from __future__ import annotations

import os
import re
import tomllib
from pathlib import Path
from types import SimpleNamespace

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

# ==============================================================================
# User config (spec 54) — an operator-facing helper, NOT read by the library.
#
# `fsd.download` / `create_training_data` / `run_inference` take every storage location as
# an argument and never look here (D3). This section exists so an operator can write
# `cfg = fsd.config.load()` at the top of a notebook and pass `cfg.root` etc down explicitly
# -- the seam spec 41 D7 wanted, with the bootstrap moved to a place a `pip install`
# consumer can actually reach.
# ==============================================================================

# The six values, and their bare-env-var spelling (D4). Order here is the order they are
# written to config.toml and reported in `MissingConfig` / `fsd config`.
KEYS = ("subscription_id", "resource_group", "workspace", "cluster", "uami_client_id", "root")

_KEY_TO_ENV = {
    "subscription_id": "AZ_SUBSCRIPTION_ID",
    "resource_group": "AZ_RG",
    "workspace": "AZ_ML_WORKSPACE",
    "cluster": "AZ_CLUSTER",
    "uami_client_id": "AZ_UAMI_CLIENT_ID",
    "root": "AZ_ROOT",
}
ENV_TO_KEY = {env: key for key, env in _KEY_TO_ENV.items()}


class MissingConfig(KeyError):
    """One or more config values are unset in every source `load()` checks.

    Subclasses `KeyError` so an existing `except KeyError` in a notebook still catches it.
    Reports every missing name at once (D7): filling one blank, re-running a cell, and being
    told about the next is a bad loop when each round trip costs a notebook cell.
    """

    def __init__(self, missing: list[str]):
        self.missing = list(missing)
        names = ", ".join(missing)
        env_names = ", ".join(_KEY_TO_ENV[k] for k in missing)
        self._message = (
            f"{names} — not set.\n\n"
            f"  Run `fsd init` to fill them in (writes {config_path()}),\n"
            f"  or set {env_names} in your environment.\n\n"
            "  These are addresses, not secrets — your credential is `az login`.\n"
            "  Concrete values come from your platform admin. See docs/reference/environment.md."
        )
        super().__init__(self._message)

    def __str__(self) -> str:
        # KeyError.__str__ reprs a single arg (quoting it); this message is prose, not a key.
        return self._message


def config_dir() -> Path:
    """The config directory, per D1's resolution order.

    1. `$FSD_CONFIG_DIR`, if set and absolute.
    2. `$XDG_CONFIG_HOME/fsd`, if `XDG_CONFIG_HOME` is set and absolute.
    3. POSIX: `~/.config/fsd`. Windows: `%APPDATA%\\fsd`.

    A relative path in either override variable is ignored, not resolved -- the XDG spec's
    own rule, which stops a stray `FSD_CONFIG_DIR=.` from silently writing into whatever
    directory a notebook kernel happened to start in.
    """
    fsd_dir = os.environ.get("FSD_CONFIG_DIR")
    if fsd_dir and Path(fsd_dir).is_absolute():
        return Path(fsd_dir)
    xdg_dir = os.environ.get("XDG_CONFIG_HOME")
    if xdg_dir and Path(xdg_dir).is_absolute():
        return Path(xdg_dir) / "fsd"
    if os.name == "nt":
        appdata = os.environ.get("APPDATA")
        if appdata:
            return Path(appdata) / "fsd"
    return Path.home() / ".config" / "fsd"


def config_path() -> Path:
    """`config.toml` inside `config_dir()`."""
    return config_dir() / "config.toml"


# TOML basic-string escapes this schema actually needs: backslash, double quote, and the
# control characters TOML forbids unescaped in a basic string -- U+0000-U+0008, U+000A-U+001F
# AND U+007F (DEL), which is easy to miss because it sits above the printable range: emitting
# it raw produces a file `tomllib` then refuses to parse. Tractable because the schema is
# closed and flat (D2) -- if it ever grows nesting, arrays, or user-supplied keys, switch to
# `tomli-w` instead of extending this.
_TOML_ESCAPES = {"\\": "\\\\", '"': '\\"', "\b": "\\b", "\t": "\\t", "\n": "\\n", "\f": "\\f", "\r": "\\r"}


def _toml_escape(value: str) -> str:
    out = []
    for ch in value:
        if ch in _TOML_ESCAPES:
            out.append(_TOML_ESCAPES[ch])
        elif ord(ch) < 0x20 or ord(ch) == 0x7F:
            out.append(f"\\u{ord(ch):04x}")
        else:
            out.append(ch)
    return "".join(out)


def _emit_toml(values: dict[str, str]) -> str:
    """Render the `[azure]` table as TOML text. Stdlib `tomllib` cannot write (D2's
    constraint); this is the ~20-line emitter that stands in for `tomli-w` while the schema
    stays six flat strings.
    """
    width = max(len(k) for k in KEYS)
    lines = [
        "# ~/.config/fsd/config.toml — written by `fsd init`.",
        "# These are addresses, not secrets. Your credential is `az login`.",
        "[azure]",
    ]
    for key in KEYS:
        lines.append(f'{key.ljust(width)} = "{_toml_escape(values.get(key, ""))}"')
    return "\n".join(lines) + "\n"


def _read_file_values() -> dict[str, str]:
    """The `[azure]` table on disk, or `{}` if the file does not exist."""
    path = config_path()
    if not path.exists():
        return {}
    with path.open("rb") as f:
        data = tomllib.load(f)
    azure = data.get("azure", {})
    return {k: v for k, v in azure.items() if k in _KEY_TO_ENV}


def write_config(updates: dict[str, str]) -> Path:
    """Read-modify-write `config.toml`: merge `updates` over whatever is already there.

    Used by every `fsd init` form (D5) -- interactive, `--from-env-file`, and `--set` all
    reduce to "here are some keys, keep the rest." Creates `config_dir()` if needed.
    """
    values = _read_file_values()
    values.update({k: v for k, v in updates.items() if v})
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_emit_toml(values))
    return path


# `export NAME='value'`, `export NAME="value"`, or `export NAME=value`, each optionally
# followed by a comment -- moved verbatim from the retired `notebooks/_config.py` (D6). The
# trailing-comment part is load-bearing: an earlier version of this pattern anchored the
# value to end-of-line, so a line with a trailing comment never matched and a fully filled-in
# file was reported as empty.
_EXPORT_RE = re.compile(
    r"""\s*export\s+(\w+)=(?:"([^"]*)"|'([^']*)'|([^#\s]*))\s*(?:\#.*)?$"""
)


def parse_env_file(path: Path | str) -> dict[str, str]:
    """Parse an `env.local.sh`-shaped file into `{AZ_NAME: value}`. No shell is spawned.

    Deliberately **not** `source`d: sourcing would run arbitrary shell from a file whose
    whole purpose is holding credential-adjacent values, and it would resolve `$(...)`
    entries whose values this has no business capturing. Entries containing `$` are skipped
    for the same reason. Empty values are omitted rather than returned as `""`, so a caller
    reports them as missing instead of writing a blank into `config.toml`.
    """
    out: dict[str, str] = {}
    for line in Path(path).read_text().splitlines():
        m = _EXPORT_RE.match(line)
        if not m:
            continue
        value = next((g for g in m.groups()[1:] if g is not None), "")
        if value and "$" not in value:
            out[m.group(1)] = value
    return out


def load(**kwargs: str) -> SimpleNamespace:
    """Resolve the six config values: explicit kwarg, then `AZ_*` env var, then `config.toml`.

    `src/fsd/` never calls this (D3) -- it is an operator-facing helper, called explicitly:

        cfg = fsd.config.load()
        fsd.download(..., dst_folderpath=f"{cfg.root}/imagery", ...)

    Raises `MissingConfig` naming every key still unset after all three sources. Reads
    `os.environ` (that is precedence level 2) but never assigns to it (D4) -- the environment
    is read, never written.
    """
    unknown = sorted(set(kwargs) - set(KEYS))
    if unknown:
        raise TypeError(f"load() got unexpected keyword argument(s): {unknown}")
    file_values = _read_file_values()
    resolved: dict[str, str] = {}
    for key in KEYS:
        value = kwargs.get(key) or os.environ.get(_KEY_TO_ENV[key]) or file_values.get(key)
        if value:
            resolved[key] = value
    missing = [k for k in KEYS if not resolved.get(k)]
    if missing:
        raise MissingConfig(missing)
    return SimpleNamespace(**resolved)
