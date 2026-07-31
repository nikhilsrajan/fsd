"""Azure ADLS Gen2 compute seam — `to_vsi`, the GDAL VSI token, and `storage=` config.

Spec: specs/31-p1-azure-storage-seam.md (compute seam only; §5 download-to-blob is SUSPENDED
into the ingest/normalization contract spec, not implemented here).

There is no bespoke storage-options registry and no credential object passed around: adlfs,
given only `account_name` + `anon=False`, auto-resolves `DefaultAzureCredential` itself (§1),
and fsspec's native per-protocol config (`fsspec.config.conf` / `FSSPEC_{PROTOCOL}_*` env)
already does what a registry would. This module supplies the two things fsspec/adlfs cannot:
the deterministic `abfss://` -> `/vsiadls/` URL translation GDAL needs (adlfs is not on GDAL's
pixel-read path), and a token for GDAL's own Azure VSI handler (which, unlike adlfs, never
refreshes a token it's been given).
"""

from __future__ import annotations

import os
import re
import threading
from typing import Any

import fsspec

__all__ = ["to_vsi", "account_from_url", "storage_token", "configure_storage"]

# abfss://<filesystem>@<account>.dfs.core.windows.net/<path>
_ABFSS_RE = re.compile(r"^abfss://([^@/]+)@([^./]+)\.dfs\.core\.windows\.net/(.*)$")
# az://<filesystem>/<path> (alias; account comes from ambient config, not the URL)
_AZ_RE = re.compile(r"^az://([^/]+)/(.*)$")

_credential_lock = threading.Lock()
_credential = None


def _get_credential():
    """The single module-cached `DefaultAzureCredential` (§4 — reuse is the documented best
    practice: it shares the token cache and avoids Entra 429 throttling)."""
    global _credential
    if _credential is None:
        with _credential_lock:
            if _credential is None:  # pragma: no branch - re-check under the lock
                from azure.identity import DefaultAzureCredential

                _credential = DefaultAzureCredential()
    return _credential


def storage_token() -> str:
    """A fresh Storage-scoped bearer token from the module-cached credential.

    `DefaultAzureCredential.get_token` caches + auto-refreshes internally (thread-safe MSAL
    cache), so calling this before every GDAL VSI open is cheap and always-valid — GDAL's own
    `AZURE_STORAGE_ACCESS_TOKEN` is a static token it does not refresh, so the caller (us) owns
    the refresh by re-fetching one per open rather than a hand-rolled expiry margin.
    """
    return _get_credential().get_token("https://storage.azure.com/.default").token


def to_vsi(url: str) -> str:
    """Translate a canonical blob URL to a GDAL VSI path. Local paths pass through unchanged.

    - `abfss://<fs>@<account>.dfs.core.windows.net/<path>` -> `/vsiadls/<fs>/<path>`
    - `az://<fs>/<path>` (alias)                            -> `/vsiadls/<fs>/<path>`
    - anything else (a local path, `file://`, ...)           -> returned unchanged

    A string that declares itself `abfss://`/`az://` but doesn't match the expected shape
    raises rather than being silently treated as local.
    """
    if url.startswith("abfss://"):
        m = _ABFSS_RE.match(url)
        if not m:
            raise ValueError(f"malformed abfss:// URL (expected fs@account.dfs.core.windows.net/path): {url!r}")
        filesystem, _account, path = m.groups()
        return f"/vsiadls/{filesystem}/{path}"
    if url.startswith("az://"):
        m = _AZ_RE.match(url)
        if not m:
            raise ValueError(f"malformed az:// URL (expected fs/path): {url!r}")
        filesystem, path = m.groups()
        return f"/vsiadls/{filesystem}/{path}"
    return url


def account_from_url(url: str) -> str | None:
    """The storage account name from a fully-qualified `abfss://` URL host, or `None` for any
    other URL shape (including the `az://` alias, whose account comes from ambient config)."""
    m = _ABFSS_RE.match(url)
    return m.group(2) if m else None


def configure_storage(storage: Any) -> None:
    """Apply a verb's `storage=` kwarg: sets **both** `os.environ` and `fsspec.config.conf`.

    fsspec populates `fsspec.config.conf` from `FSSPEC_*` env **at import time**; mutating
    `os.environ` after that does not retroactively update the already-imported parent process's
    `conf`, so both must be set explicitly. `os.environ` is what a Snakemake-subprocess child (or
    a Batch task at P4) inherits and re-reads on its own import — no live credential object
    crosses that boundary (D4).

    `storage=None` or `storage="local"` are no-ops. `storage="azure"` or
    `{"backend": "azure", ...}` sets `FSSPEC_ABFSS_ANON=false` (the one config key that
    matters — §1: `apply_config` keys on `AzureBlobFileSystem.protocol`, which covers
    `abfs`/`az`/`abfss` from one key; the account comes from the URL host, not from
    config). Any other backend raises.
    """
    if storage is None or storage == "local":
        return
    if isinstance(storage, str):
        backend = storage
    elif isinstance(storage, dict):
        backend = storage.get("backend")
    else:
        backend = None
    if backend != "azure":
        raise ValueError(f"storage backend {backend!r} not supported (only 'azure' in P1).")
    os.environ["FSSPEC_ABFSS_ANON"] = "false"
    fsspec.config.conf.setdefault("abfss", {})["anon"] = False
