"""Session-wide state isolation for the process-globals `configure_storage` mutates (#150)."""

from __future__ import annotations

import os

import fsspec
import pytest


@pytest.fixture(autouse=True)
def clean_fsspec_conf():
    """Snapshot and restore `fsspec.config.conf` and `FSSPEC_ABFSS_ANON` around every test.

    `rise_eo.storage.azure.configure_storage` writes both process-globally (spec 31 P1), so a
    test that reaches it leaks into every later test in the session: #150 was that leak
    reaching `tests/test_azure_seam.py`'s noop checks from `tests/test_infer_aml.py`,
    hidden only by alphabetical file order. The per-module copies of this fixture that
    contained it (`_clean_fsspec_conf`) covered only the tests that requested them, so it
    lives here, autouse, for every test.
    """
    before = {k: dict(v) for k, v in fsspec.config.conf.items()}
    before_env = os.environ.get("FSSPEC_ABFSS_ANON")
    yield
    fsspec.config.conf.clear()
    fsspec.config.conf.update(before)
    if before_env is None:
        os.environ.pop("FSSPEC_ABFSS_ANON", None)
    else:
        os.environ["FSSPEC_ABFSS_ANON"] = before_env
