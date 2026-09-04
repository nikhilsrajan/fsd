"""Spec 58 P1 acceptance criteria not already covered by the per-module test suites.

AC numbering follows specs/58-collection-agnostic-verbs.md §5. AC1 (pytest+ruff clean)
and AC3 (bit-identical S2) are proven by the unchanged synthetic expectations across the
existing suite, not by a dedicated test here. AC2 is a grep, not a pytest assertion.
AC4/AC5 live in tests/test_backward_walk.py (they need `create_datacube.setup`'s
fixtures). AC9/AC10 live in tests/test_workflows.py and tests/test_declaration.py
respectively as part of the existing coverage they extended.
"""

from __future__ import annotations

import pytest

from fsd import api
from fsd.catalog.declaration import CollectionDeclaration, MaskSpec
from fsd.datacube import builder
from fsd.sources import cdse, mpc

# --- AC6: a requested band absent from an item raises, naming the band + collection ---

def test_ac6_mpc_missing_band_raises_naming_band_and_collection():
    class _Item:
        id = "t1"
        assets = {"B04": type("A", (), {"href": "https://x/B04.tif"})()}

    with pytest.raises(ValueError, match=r"B02.*sentinel-2-l2a"):
        mpc._select_item_files(_Item(), ["B04", "B02"], "/tmp", collection="sentinel-2-l2a")


def test_ac6_cdse_missing_band_raises_naming_band_and_collection():
    class _Item:
        id = "t1"
        assets = {
            "B04_10m": type("A", (), {"href": "https://x/B04.jp2"})(),
            "granule_metadata": type(
                "A", (), {"href": "s3://eodata/x/S2A_x.SAFE/MTD_TL.xml"}
            )(),
        }

    with pytest.raises(ValueError, match=r"B02.*sentinel-2-l2a"):
        cdse._select_item_files(_Item(), ["B04", "B02"], "/tmp", collection="sentinel-2-l2a")


# --- AC7: a declared non-None reference_band absent from bands raises at preflight ----

def test_ac7_reference_band_not_in_bands_raises():
    decl = CollectionDeclaration(reference_band="B08", mask_spec=None)
    with pytest.raises(ValueError, match="reference_band"):
        builder.build_datacube(
            catalog_subset=__import__("geopandas").GeoDataFrame(
                {"id": [], "filepath": [], "band": [], "timestamp": [], "geometry": [],
                 "area_contribution": []}
            ),
            shape_gdf=__import__("geopandas").GeoDataFrame({"geometry": []}),
            startdate=__import__("datetime").datetime(2018, 1, 1),
            enddate=__import__("datetime").datetime(2018, 2, 1),
            bands=["B04"],  # B08 (the declared reference) is not requested
            declaration=decl,
            export_folderpath="/tmp/unused",
            if_missing_files=None,
        )


# --- AC8: source="cdse", collection="sentinel-1-rtc" raises, naming CDSE's served ------

def test_ac8_unserved_source_collection_pair_raises_naming_served_collections():
    with pytest.raises(api.PreflightError, match=r"sentinel-2-l2a"):
        api.download(
            roi=None, startdate=None, enddate=None, bands=["B04"],
            dst_folderpath="/tmp/unused", source="cdse", collection="sentinel-1-rtc",
            max_tiles=1,
        )


# --- D6: max_cloudcover against a collection with no cloud-cover capability raises -----

def test_max_cloudcover_against_a_no_cloudcover_collection_raises():
    import dataclasses

    from fsd import collections as _collections

    no_cc_id = "spec58-p1-test-no-cloudcover"
    base = _collections.get("sentinel-2-l2a")
    _collections.register(
        no_cc_id, dataclasses.replace(base, supports_cloud_cover=False), force=True)
    # `REGISTRY` is a global in-process dict -- tear the throwaway id down, or it leaks
    # into every later test in the session (and into `restamp_cli`'s `--declaration`
    # choices, a view over the same dict).
    try:
        errs = api._check_cloudcover_capability(no_cc_id, 50.0)
        assert errs and "supports_cloud_cover" in errs[0]
        assert api._check_cloudcover_capability("sentinel-2-l2a", 50.0) == []
    finally:
        _collections.REGISTRY.pop(no_cc_id, None)


# --- D15: mpc/cdse each declare a fixed served-collections set -----------------------

def test_served_collections_are_disjoint_from_unknown_names():
    assert "sentinel-2-l2a" in mpc.SERVED_COLLECTIONS
    assert "sentinel-2-l2a" in cdse.SERVED_COLLECTIONS
    assert "sentinel-1-rtc" not in cdse.SERVED_COLLECTIONS


# --- D14: a build variant may not lie about artifact facts -----------------------------

def test_build_variant_with_differing_artifact_fact_raises():
    import geopandas as gpd

    from fsd.catalog import declaration as declaration_module

    stamped = declaration_module.S2_L2A_DECLARATION
    variant = CollectionDeclaration(
        reference_band=stamped.reference_band, mask_spec=None,
        nodata=-9999,  # lies about the artifact
    )
    gdf = gpd.GeoDataFrame({"id": []})
    declaration_module.to_attrs(gdf, stamped)
    with pytest.raises(ValueError, match="artifact fact"):
        builder._resolve_build_declaration(gdf, variant)


def test_build_variant_with_only_policy_difference_is_accepted():
    import geopandas as gpd

    from fsd.catalog import declaration as declaration_module

    stamped = declaration_module.S2_L2A_DECLARATION
    variant = CollectionDeclaration(
        reference_band=stamped.reference_band, native_grid=stamped.native_grid,
        mask_spec=MaskSpec(band="SCL", classes=(8, 9)),  # a different mask -- build policy
        mask_keep=stamped.mask_keep, nodata=stamped.nodata, mosaic_method=stamped.mosaic_method,
        scale=stamped.scale, radiometry_bands=stamped.radiometry_bands,
        band_aliases=stamped.band_aliases,
        requires_subscription_key=stamped.requires_subscription_key,
        supports_cloud_cover=stamped.supports_cloud_cover,
        mosaic_partition=stamped.mosaic_partition, partition_policy=stamped.partition_policy,
    )
    gdf = gpd.GeoDataFrame({"id": []})
    declaration_module.to_attrs(gdf, stamped)
    resolved = builder._resolve_build_declaration(gdf, variant)
    assert resolved is variant
