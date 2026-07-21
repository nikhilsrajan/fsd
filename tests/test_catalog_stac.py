"""Tests for the STAC export view of the tile catalog (spec 17).

Synthetic + pure-metadata: no raster files are read (read_proj defaults False).
"""

from __future__ import annotations

import json
import os

import pandas as pd
import pystac
import pytest
import shapely.geometry
from pystac.extensions.projection import ProjectionExtension
from pystac.extensions.raster import RasterExtension

from fsd import config
from fsd.catalog import stac
from fsd.catalog.catalog import TileCatalog


def _catalog_gdf():
    import geopandas as gpd

    rows = [
        {
            "id": "S2B_MSIL2A_20181231T080329_N0500_R035_T37PBP_20230726T205809",
            "satellite": "sentinel-2-l2a",
            "timestamp": pd.Timestamp("2018-12-31T08:03:29", tz="UTC"),
            "s3url": "s3://eodata/Sentinel-2/MSI/L2A/.../S2B_...T37PBP.SAFE",
            "local_folderpath": "/data/s2/T37PBP_20181231",
            "files": "B04.tif,B08.tif,MTD_TL.xml,SCL.tif",
            "cloud_cover": 1.5,
            "offset": -1000,
            "nodata": 0,
            "geometry": shapely.geometry.box(36.6, 12.6, 37.0, 13.0),
        },
        {
            "id": "S2A_MSIL2A_20180601T075611_N0500_R035_T36PZU_20230101T000000",
            "satellite": "sentinel-2-l2a",
            "timestamp": pd.Timestamp("2018-06-01T07:56:11", tz="UTC"),
            "s3url": "s3://eodata/.../T36PZU.SAFE",
            "local_folderpath": "/data/s2/T36PZU_20180601",
            "files": "B04.tif,B08.tif,SCL.tif",
            "cloud_cover": 0.0,
            "offset": 0,
            "nodata": 0,
            "geometry": shapely.geometry.box(35.6, 11.6, 36.0, 12.0),
        },
    ]
    return gpd.GeoDataFrame(rows, geometry="geometry", crs="EPSG:4326")


# --- mapping -----------------------------------------------------------------

def test_mgrs_to_epsg_northern_zones():
    # T37PBP -> zone 37, band P (northern) -> 32637; T36PZU -> 32636.
    assert stac._parse_mgrs("x_T37PBP_y") == ("37PBP", 32637)
    assert stac._parse_mgrs("x_T36PZU_y") == ("36PZU", 32636)
    # a southern-band tile -> 327xx.
    assert stac._parse_mgrs("x_T36GZU_y") == ("36GZU", 32736)
    assert stac._parse_mgrs("no_tile_here") is None


def test_tile_catalog_to_items_core_and_assets():
    items = stac.tile_catalog_to_items(_catalog_gdf())
    assert len(items) == 2
    it = items[0]
    assert it.id.endswith("T37PBP_20230726T205809")
    assert it.collection_id == "sentinel-2-l2a"
    assert it.datetime.year == 2018
    assert it.properties["eo:cloud_cover"] == 1.5
    # pystac proj ext v2.0 serialises EPSG as proj:code="EPSG:32637"; .epsg reads it back.
    assert ProjectionExtension.ext(it).epsg == 32637
    assert it.properties["proj:code"] == "EPSG:32637"
    assert it.properties["grid:code"] == "MGRS-37PBP"
    # one asset per file, correct media types + roles.
    assert set(it.assets) == {"B04", "B08", "MTD_TL", "SCL"}
    assert it.assets["B04"].media_type == pystac.MediaType.COG
    # spec 34 §2a: role classification rides alongside "data" (reflectance/mask/
    # reference); B08 is the reference band by default.
    assert it.assets["B04"].roles == ["data", "reflectance"]
    assert it.assets["B08"].roles == ["data", "reference"]
    assert it.assets["SCL"].roles == ["data", "mask"]
    assert it.assets["B04"].extra_fields["eo:bands"] == [{"name": "B04"}]
    assert it.assets["MTD_TL"].media_type == pystac.MediaType.XML
    assert it.assets["MTD_TL"].roles == ["metadata"]
    # no per-asset proj without read_proj (I/O-free).
    assert "proj:shape" not in it.assets["B04"].extra_fields
    # source link recorded.
    assert it.get_links("via")[0].get_href().endswith("T37PBP.SAFE")


def test_tile_catalog_to_items_raster_bands_carry_declared_offset_scale_nodata():
    """spec 34 §1a: reflectance/reference bands get the row's declared offset (scaled
    to reflectance units to pair with scale=1/10000, so unscale=true yields physical
    reflectance) + the constant reflectance scale; the mask band (SCL) gets
    offset=0/scale=1 (a no-op) — both in the COG GDAL tag AND here, the STAC interchange."""
    it = stac.tile_catalog_to_items(_catalog_gdf())[0]  # row declares offset=-1000 (DN)
    b04_bands = RasterExtension.ext(it.assets["B04"]).bands
    # reflectance-unit: -1000 DN * 1/10000 = -0.1 (NOT the DN value -- the black-tile bug)
    assert b04_bands[0].offset == pytest.approx(-1000 * config.S2_REFLECTANCE_SCALE)
    assert b04_bands[0].scale == pytest.approx(1 / 10000)
    assert b04_bands[0].nodata == 0
    scl_bands = RasterExtension.ext(it.assets["SCL"]).bands
    assert scl_bands[0].offset == 0
    assert scl_bands[0].scale == 1


def test_items_are_structurally_valid():
    for it in stac.tile_catalog_to_items(_catalog_gdf()):
        assert it.bbox is not None and len(it.bbox) == 4
        assert it.geometry["type"] == "Polygon"
        d = it.to_dict()  # serialisable
        assert d["stac_version"]
        assert any("projection" in e for e in it.stac_extensions)
        assert any("/eo/" in e for e in it.stac_extensions)


# --- round-trip --------------------------------------------------------------

def test_round_trip_reconstructs_catalog_columns():
    gdf = _catalog_gdf()
    back = stac.items_to_rows(stac.tile_catalog_to_items(gdf))
    for col in ["id", "satellite", "s3url", "files", "cloud_cover", "offset", "nodata"]:
        assert list(back[col]) == list(gdf[col]), col
    assert list(back["timestamp"]) == list(gdf["timestamp"])
    # local_folderpath reconstructed from the (single) asset folder.
    assert list(back["local_folderpath"]) == list(gdf["local_folderpath"])
    for a, b in zip(back["geometry"], gdf["geometry"]):
        assert a.equals(b)


# --- static catalog serialization --------------------------------------------

def test_write_stac_catalog_self_contained(tmp_path):
    items = stac.tile_catalog_to_items(_catalog_gdf())
    dst = str(tmp_path / "stac")
    catalog_json = stac.write_stac_catalog(items, dst)
    assert catalog_json.endswith("catalog.json")
    # readable back by pystac; has the collection + both items.
    cat = pystac.Catalog.from_file(catalog_json)
    all_items = list(cat.get_items(recursive=True))
    assert len(all_items) == 2
    assert {i.id for i in all_items} == {it.id for it in items}


def test_write_stac_catalog_empty_raises():
    with pytest.raises(ValueError, match="no items"):
        stac.write_stac_catalog([], "irrelevant")


# --- TileCatalog.to_stac end to end ------------------------------------------

def test_tilecatalog_to_stac(tmp_path):
    from fsd.storage import fs

    cat_path = str(tmp_path / "catalog.parquet")
    fs.write_parquet(cat_path, _catalog_gdf())
    catalog_json = TileCatalog(cat_path).to_stac(str(tmp_path / "stac"))
    cat = pystac.Catalog.from_file(catalog_json)
    assert len(list(cat.get_items(recursive=True))) == 2


# --- declaration mirror on the Collection (spec 35 §7/§8.10) -----------------


def test_write_stac_catalog_mirrors_declaration_on_collection(tmp_path):
    from fsd.catalog.declaration import MaskSpec, SourceDeclaration

    decl = SourceDeclaration(
        reference_band="B08", mask_spec=MaskSpec(band="SCL", classes=(3, 8, 9)),
    )
    items = stac.tile_catalog_to_items(_catalog_gdf())
    dst = str(tmp_path / "stac")
    catalog_json = stac.write_stac_catalog(items, dst, declaration=decl)

    cat = pystac.Catalog.from_file(catalog_json)
    collection = next(cat.get_children())
    assert isinstance(collection, pystac.Collection)

    from fsd.catalog import declaration as declaration_module

    assert collection.extra_fields[declaration_module.ATTRS_KEY] == declaration_module.to_json(decl)

    from pystac.extensions.classification import ClassificationExtension

    scl_asset = collection.item_assets["SCL"]
    classes = ClassificationExtension.ext(scl_asset).classes
    assert sorted(c.value for c in classes) == [3, 8, 9]


def test_collection_to_declaration_round_trips():
    from fsd.catalog.declaration import MaskSpec, SourceDeclaration
    from fsd.catalog.stac import collection_to_declaration

    decl = SourceDeclaration(
        reference_band="B04", mask_spec=MaskSpec(band="QA", classes=(1, 2)),
        mosaic_method="median",
    )
    collection = pystac.Collection(
        id="x", description="x",
        extent=pystac.Extent(
            spatial=pystac.SpatialExtent([[0, 0, 1, 1]]),
            temporal=pystac.TemporalExtent([[None, None]]),
        ),
    )
    stac._stamp_collection_declaration(collection, decl)
    assert collection_to_declaration(collection) == decl


def test_collection_to_declaration_no_stamp_returns_none():
    from fsd.catalog.stac import collection_to_declaration

    collection = pystac.Collection(
        id="x", description="x",
        extent=pystac.Extent(
            spatial=pystac.SpatialExtent([[0, 0, 1, 1]]),
            temporal=pystac.TemporalExtent([[None, None]]),
        ),
    )
    assert collection_to_declaration(collection) is None


def test_tilecatalog_to_stac_mirrors_the_catalogs_stamp(tmp_path):
    from fsd.catalog import declaration as declaration_module
    from fsd.catalog.declaration import SourceDeclaration
    from fsd.catalog.stac import collection_to_declaration

    decl = SourceDeclaration(reference_band="B04")
    cat_path = str(tmp_path / "catalog.parquet")
    gdf = _catalog_gdf()
    declaration_module.to_attrs(gdf, decl)
    from fsd.storage import fs

    fs.write_parquet(cat_path, gdf)

    catalog_json = TileCatalog(cat_path).to_stac(str(tmp_path / "stac"))
    cat = pystac.Catalog.from_file(catalog_json)
    collection = next(cat.get_children())
    assert collection_to_declaration(collection) == decl


# --- cog_outputs_to_items geometry (spec 28) ---------------------------------

def _make_output_cog(folder, *, epsg=32637):
    import numpy as np
    import rasterio
    from rasterio.transform import from_origin

    os.makedirs(folder, exist_ok=True)
    fp = os.path.join(folder, "output.tif")
    data = np.zeros((1, 4, 4), dtype="uint8")
    with rasterio.open(
        fp, "w", driver="GTiff", height=4, width=4, count=1, dtype="uint8",
        crs=f"EPSG:{epsg}", transform=from_origin(500000, 4000000, 10, 10),
    ) as dst:
        dst.write(data)
    return fp


_SLANTED_POLYGON = shapely.geometry.Polygon(
    [(14.766, 48.492), (14.789, 48.534), (14.847, 48.526), (14.825, 48.484)]
)


def _write_geometry_geojson(folder, *, feature_id="cell-1", geom=_SLANTED_POLYGON):
    fp = os.path.join(folder, "geometry.geojson")
    fc = {
        "type": "FeatureCollection",
        "features": [{
            "type": "Feature",
            "properties": {"id": feature_id},
            "geometry": shapely.geometry.mapping(geom),
        }],
    }
    with open(fp, "w") as f:
        json.dump(fc, f)
    return fp


def test_cog_outputs_to_items_uses_manifest_geometry_not_raster_box(tmp_path):
    cell_dir = str(tmp_path / "cell-1")
    cog = _make_output_cog(cell_dir)
    geom_path = _write_geometry_geojson(cell_dir, feature_id="cell-1")

    items = stac.cog_outputs_to_items([cog], geometries={cog: geom_path})
    assert len(items) == 1
    it = items[0]
    assert shapely.geometry.shape(it.geometry).equals(_SLANTED_POLYGON)
    assert list(it.bbox) == list(_SLANTED_POLYGON.bounds)
    # not an axis-aligned rectangle: more than 2 distinct x's and y's among the corners.
    xs, ys = zip(*it.geometry["coordinates"][0])
    assert len(set(xs)) > 2
    assert len(set(ys)) > 2


def test_cog_outputs_to_items_missing_geometry_raises(tmp_path):
    cell_dir = str(tmp_path / "cell-1")
    cog = _make_output_cog(cell_dir)
    with pytest.raises(ValueError, match="no entry"):
        stac.cog_outputs_to_items([cog], geometries={})


def test_cog_outputs_to_items_geometries_none_keeps_raster_box(tmp_path):
    cell_dir = str(tmp_path / "cell-1")
    cog = _make_output_cog(cell_dir)

    items = stac.cog_outputs_to_items([cog])
    assert len(items) == 1
    geom = shapely.geometry.shape(items[0].geometry)
    minx, miny, maxx, maxy = geom.bounds
    # axis-aligned rectangle: exactly 4 corners with 2 distinct x's x 2 distinct y's.
    xs, ys = zip(*items[0].geometry["coordinates"][0][:-1])
    assert set(xs) == {minx, maxx}
    assert set(ys) == {miny, maxy}
