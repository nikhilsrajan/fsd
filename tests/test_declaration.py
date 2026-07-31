"""Tests for fsd.catalog.declaration's serialization (spec 35 §2a/§3).

Pure functions, no I/O: `to_json`/`from_json` (dataclass <-> JSON dict) and
`to_attrs`/`from_attrs` (JSON dict <-> `GeoDataFrame.attrs`).
"""

import json

import geopandas as gpd
import pytest
import shapely

from fsd.catalog import declaration as declaration_module
from fsd.catalog.declaration import (
    S2_L2A_DECLARATION,
    MaskSpec,
    SourceDeclaration,
)


def test_to_json_from_json_round_trip_exact():
    decl = SourceDeclaration(
        reference_band="B04",
        mask_spec=MaskSpec(band="QA", classes=(1, 2, 3)),
        mask_keep=True,
        nodata=7,
        mosaic_method="median",
    )
    assert declaration_module.from_json(declaration_module.to_json(decl)) == decl
    # JSON-level round trip too (spec 35 §3): to_json(from_json(x)) == x.
    raw = declaration_module.to_json(decl)
    assert declaration_module.to_json(declaration_module.from_json(raw)) == raw


def test_to_json_from_json_round_trip_s2_default():
    assert declaration_module.from_json(declaration_module.to_json(S2_L2A_DECLARATION)) == S2_L2A_DECLARATION


def test_mask_spec_classes_rehydrate_as_tuple_not_list():
    decl = SourceDeclaration(mask_spec=MaskSpec(band="SCL", classes=(0, 1, 3)))
    raw = declaration_module.to_json(decl)
    assert raw["mask_spec"]["classes"] == [0, 1, 3]  # JSON array on the wire
    back = declaration_module.from_json(raw)
    assert isinstance(back.mask_spec.classes, tuple)
    assert back.mask_spec.classes == (0, 1, 3)
    # frozen/hashable (a list would break this).
    hash(back)


def test_no_mask_source_mask_spec_null_round_trips_as_none():
    decl = SourceDeclaration(reference_band=None, mask_spec=None)
    raw = declaration_module.to_json(decl)
    assert raw["mask_spec"] is None
    back = declaration_module.from_json(raw)
    assert back.mask_spec is None
    assert back == decl


def test_to_json_is_plain_json_able_dict():
    """spec 35 §2a: everything to_json produces must survive json.dumps -- no
    dataclass leaks into the wire format."""
    raw = declaration_module.to_json(S2_L2A_DECLARATION)
    json.dumps(raw)  # must not raise


def test_from_json_missing_version_raises():
    raw = declaration_module.to_json(S2_L2A_DECLARATION)
    del raw["fsd_declaration_version"]
    with pytest.raises(ValueError, match="fsd_declaration_version"):
        declaration_module.from_json(raw)


def test_from_json_newer_version_raises():
    raw = declaration_module.to_json(S2_L2A_DECLARATION)
    raw["fsd_declaration_version"] = declaration_module.FSD_DECLARATION_VERSION + 1
    with pytest.raises(ValueError, match="newer fsd"):
        declaration_module.from_json(raw)


def test_from_json_unknown_field_raises():
    raw = declaration_module.to_json(S2_L2A_DECLARATION)
    raw["not_a_real_field"] = 1
    with pytest.raises(ValueError, match="unknown field"):
        declaration_module.from_json(raw)


def test_from_json_non_object_raises_clearly():
    """A hand-edited/corrupt footer must fail with a message about the shape, not
    an incidental TypeError from iterating an int (spec 35 §3's fail-loudly rule)."""
    with pytest.raises(ValueError, match="must be a JSON object"):
        declaration_module.from_json([1, 2, 3])

    raw = declaration_module.to_json(S2_L2A_DECLARATION)
    raw["mask_spec"] = 5
    with pytest.raises(ValueError, match="mask_spec must be a JSON object"):
        declaration_module.from_json(raw)


def test_from_json_missing_optional_field_takes_dataclass_default():
    raw = declaration_module.to_json(S2_L2A_DECLARATION)
    del raw["mask_keep"]
    back = declaration_module.from_json(raw)
    assert back.mask_keep == SourceDeclaration.__dataclass_fields__["mask_keep"].default


def test_to_attrs_from_attrs_round_trip():
    gdf = gpd.GeoDataFrame({"id": ["a"]}, geometry=[shapely.box(0, 0, 1, 1)], crs="EPSG:4326")
    decl = SourceDeclaration(reference_band="B04")
    declaration_module.to_attrs(gdf, decl)
    assert declaration_module.from_attrs(gdf) == decl


def test_from_attrs_no_stamp_returns_none():
    gdf = gpd.GeoDataFrame({"id": ["a"]}, geometry=[shapely.box(0, 0, 1, 1)], crs="EPSG:4326")
    assert declaration_module.from_attrs(gdf) is None


def test_to_attrs_never_puts_the_dataclass_in_attrs():
    """spec 35 §2a's future-geopandas guard: the on-attrs value is a dict, and
    it (and everything fsd puts in .attrs) must be JSON-able."""
    gdf = gpd.GeoDataFrame({"id": ["a"]}, geometry=[shapely.box(0, 0, 1, 1)], crs="EPSG:4326")
    declaration_module.to_attrs(gdf, S2_L2A_DECLARATION)
    assert not isinstance(gdf.attrs[declaration_module.ATTRS_KEY], SourceDeclaration)
    for value in gdf.attrs.values():
        json.dumps(value)  # must not raise
