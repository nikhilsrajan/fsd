"""#150: a test that reaches `configure_storage` must not leak into the next test.

`configure_storage` writes `fsspec.config.conf` and `FSSPEC_ABFSS_ANON` process-globally
(spec 31 P1). Before `tests/conftest.py` gained its autouse snapshot/restore, only the
tests that requested the per-module `_clean_fsspec_conf` fixtures were cleaned up, so
`tests/test_azure_seam.py`'s noop checks passed only while they ran first alphabetically.
Two tests in definition order reproduce that leak deterministically: the first stands in
for the leaky caller (`tests/test_infer_aml.py`), the second is what the alphabetical
order used to protect.
"""

from __future__ import annotations

import os

import fsspec

from rise_eo.storage import azure as rise_eo_azure


def test_a_leaky_caller_configures_azure():
    rise_eo_azure.configure_storage("azure")
    assert os.environ["FSSPEC_ABFSS_ANON"] == "false"


def test_b_the_leak_does_not_reach_the_next_test():
    assert "FSSPEC_ABFSS_ANON" not in os.environ
    assert "abfss" not in fsspec.config.conf
