"""Spec 51 §9 step 1 — `api._ensure_bundle` registry resolution (D4, AC6).

`_ensure_bundle` already turns "whatever the caller passed" into a bundle path for
`run_inference`/`verify_adapter`/the `cores>1` fan-out; this covers the one new branch it grows:
resolving `"name:N"` / `"name@alias"` against `registry=`.

Bundles are built with `bundle.save(joblib.Parallel, {}, ..., code=False)`, the same fixture
`tests/test_registry.py` uses — an installed class needs no adapter module written to disk.
"""

from __future__ import annotations

import joblib
import pytest

from fsd import api
from fsd.model import bundle, registry


def _make_bundle(tmp_path, subdir="src_bundle") -> str:
    return bundle.save(joblib.Parallel, {}, str(tmp_path / subdir), code=False, verbose=False)


# --- registry= given: "name:N" and "name@alias" both resolve ---------------------------


def test_ensure_bundle_resolves_version_pin_when_registry_given(tmp_path):
    src = _make_bundle(tmp_path)
    registry_root = str(tmp_path / "registry")
    registry.publish(src, "crop-rf", registry_root)

    resolved_path = api._ensure_bundle(
        "crop-rf:1", str(tmp_path / "out"), why="test", registry=registry_root,
    )

    assert resolved_path == registry.version_path(registry_root, "crop-rf", 1)


def test_ensure_bundle_resolves_alias_when_registry_given(tmp_path):
    src = _make_bundle(tmp_path)
    registry_root = str(tmp_path / "registry")
    registry.publish(src, "crop-rf", registry_root, alias="champion")

    resolved_path = api._ensure_bundle(
        "crop-rf@champion", str(tmp_path / "out"), why="test", registry=registry_root,
    )

    assert resolved_path == registry.version_path(registry_root, "crop-rf", 1)


# --- registry= absent: a ref-shaped "@" string is a PreflightError, never a silent path ---


def test_ensure_bundle_refuses_alias_ref_without_registry_naming_the_missing_argument():
    with pytest.raises(api.PreflightError, match="registry="):
        api._ensure_bundle("crop-rf@champion", "/tmp/out", why="test")


def test_ensure_bundle_refuses_alias_ref_without_registry_even_when_live_adapter_absent():
    # a live adapter passed alongside registry= (nonsensical combination) is refused too,
    # naming the same confusion rather than silently ignoring registry=.
    with pytest.raises(api.PreflightError, match="registry="):
        api._ensure_bundle(joblib.Parallel, "/tmp/out", why="test", registry="/tmp/reg")


# --- registry= absent: everything else is unchanged (D4's existing rows) ---------------


def test_ensure_bundle_treats_version_pin_string_as_a_literal_path_without_registry():
    # "crop-rf:1" has no "@", so it is passed through unchanged -- ":" collides with URL
    # schemes and Windows drive letters, so it is never sniffed (spec 51 step-1 handoff).
    assert api._ensure_bundle("crop-rf:1", "/tmp/out", why="test") == "crop-rf:1"


def test_ensure_bundle_passes_through_a_plain_bundle_path_without_registry(tmp_path):
    src = _make_bundle(tmp_path)
    assert api._ensure_bundle(src, str(tmp_path / "out"), why="test") == src


def test_ensure_bundle_passes_through_an_abfss_url_containing_at_sign_without_registry():
    # abfss URLs legitimately embed "@" (<fs>@<account>.dfs.core.windows.net/<path>,
    # storage/azure.py's _ABFSS_RE) -- must not be mistaken for a "name@alias" ref.
    url = "abfss://models@myaccount.dfs.core.windows.net/crop-rf/v1"
    assert api._ensure_bundle(url, "/tmp/out", why="test") == url


@pytest.mark.parametrize("path", [
    "/data/bundles/rf@2026-08/bundle",   # local path whose directory name contains "@"
    "s3://bucket@weird/crop-rf",         # any URL: the "//" alone settles it
    "relative/rf@v1",                    # relative path, "@" in the last component
])
def test_ensure_bundle_passes_through_a_path_containing_at_sign_without_registry(path):
    # only a SEPARATOR-FREE "name@alias" is ref-shaped; anything with a path component is a
    # path, so AC6's error can never refuse a legitimate bundle location.
    assert api._ensure_bundle(path, "/tmp/out", why="test") == path


# --- registry= given but the ref is bad: a PreflightError naming the verb, not a raw ValueError ---


def test_ensure_bundle_leaves_an_already_resolved_path_alone_when_registry_is_given(tmp_path):
    # `_resolve_model_ref` runs at BOTH `_model_spec`'s call sites and `_ensure_bundle`, so the
    # second call sees a path, not a ref -- it must pass through, not fail to "resolve".
    src = _make_bundle(tmp_path)
    registry_root = str(tmp_path / "registry")
    registry.publish(src, "crop-rf", registry_root)
    resolved = registry.version_path(registry_root, "crop-rf", 1)

    assert api._ensure_bundle(
        resolved, str(tmp_path / "out"), why="test", registry=registry_root,
    ) == resolved


def test_run_inference_resolves_a_ref_before_reading_the_model_spec(tmp_path):
    # AC1: `run_inference(model=ref)` accepts a ref unchanged. `_model_spec` reads `bundle.json`
    # off `model` BEFORE any dispatch, so an unresolved ref died there with a FileNotFoundError
    # naming `<ref>/bundle.json`. Reaching the *datacube* preflight is the proof it resolved.
    src = _make_bundle(tmp_path)
    registry_root = str(tmp_path / "registry")
    registry.publish(src, "crop-rf", registry_root, alias="champion")
    cubes = tmp_path / "cubes"
    cubes.mkdir()

    with pytest.raises(api.PreflightError, match="no inference datacubes"):
        api.run_inference(
            model="crop-rf@champion",
            registry=registry_root,
            inference_datacubes=str(cubes),
            output_folderpath=str(tmp_path / "out"),
        )


def test_verify_adapter_resolves_a_ref_before_reading_the_model_spec(tmp_path):
    # same for the other `_model_spec` call site: the error must be about the CALL (a missing
    # export_folderpath), never about `crop-rf@champion/bundle.json`.
    src = _make_bundle(tmp_path)
    registry_root = str(tmp_path / "registry")
    registry.publish(src, "crop-rf", registry_root, alias="champion")

    with pytest.raises(api.PreflightError, match="export_folderpath"):
        api.verify_adapter(
            model="crop-rf@champion",
            registry=registry_root,
            roi=str(tmp_path / "roi.geojson"),
            catalog_filepath=str(tmp_path / "catalog.parquet"),
            startdate="2018-04-01", enddate="2018-09-01",
            mosaic_days=20, bands=["B04", "B08", "SCL"],
            export_folderpath="",
        )


def test_ensure_bundle_wraps_an_unresolvable_ref_in_a_preflight_error(tmp_path):
    src = _make_bundle(tmp_path)
    registry_root = str(tmp_path / "registry")
    registry.publish(src, "crop-rf", registry_root)

    with pytest.raises(api.PreflightError, match="cannot resolve"):
        api._ensure_bundle(
            "crop-rf@nosuchalias", str(tmp_path / "out"), why="test", registry=registry_root,
        )
