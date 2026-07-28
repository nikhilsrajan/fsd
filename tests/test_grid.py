"""Tests for ROI → S2-grid tiling (spec 19). Synthetic, no network.

Skips when the optional `[grid]` extra (`s2`/`s2cell`) isn't installed — e.g. in fsd's lean
`.venv`; run these from the `.venv-modeldeploy` that has `.[grid]`.
"""

from __future__ import annotations

import geopandas as gpd
import pytest
import shapely.geometry

from fsd import grid

pytest.importorskip("s2", reason="needs the [grid] extra (s2 + s2cell)")


def test_grid_size_to_res_5km_is_11():
    # 5 km falls in the res-11 range (3–5 km).
    assert grid.grid_size_to_res(5) == 11
    assert grid.grid_size_to_res(1000) == 3     # 840–1167 km


def _roi(minx=36.1, miny=11.4, maxx=36.9, maxy=12.0):
    return gpd.GeoDataFrame(
        geometry=[shapely.geometry.box(minx, miny, maxx, maxy)], crs="EPSG:4326"
    )


def test_roi_to_s2_grids_clipped_contained():
    roi = _roi()
    grids = grid.roi_to_s2_grids(roi, grid_size_km=5, scale_fact=1.1)

    assert isinstance(grids, gpd.GeoDataFrame)
    assert len(grids) > 0
    assert grids.crs.to_epsg() == 4326
    assert "id" in grids.columns and "geometry" in grids.columns

    roi_geom = roi.geometry.iloc[0]
    # every clipped grid intersects the ROI and (clip=True) is contained within it.
    assert grids.geometry.intersects(roi_geom).all()
    assert grids.geometry.apply(lambda g: roi_geom.buffer(1e-9).contains(g)).all()


def test_scale_fact_enlarges_unclipped_cells():
    roi = _roi()
    small = grid.roi_to_s2_grids(roi, scale_fact=1.0, clip=False)
    big = grid.roi_to_s2_grids(roi, scale_fact=1.3, clip=False)
    # same cell count (same polyfill), but scaled cells are larger on average.
    assert len(small) == len(big) > 0
    assert big.geometry.area.mean() > small.geometry.area.mean()


def test_deterministic_count():
    roi = _roi()
    a = grid.roi_to_s2_grids(roi)
    b = grid.roi_to_s2_grids(roi)
    assert len(a) == len(b)
    assert sorted(a["id"]) == sorted(b["id"])


# --- spec 21 D-GRID-1: an ROI is one region, so ids are unique ----------------


def _scattered_roi(n=40):
    """A multi-polygon ROI: n small squares scattered inside one 5 km cell's footprint --
    the shape of a field collection (e.g. AT_2018_TRAIN's 900 EuroCrops fields)."""
    step = 0.004
    boxes = [
        shapely.geometry.box(36.10 + (i % 8) * step, 11.40 + (i // 8) * step,
                             36.10 + (i % 8) * step + step / 2,
                             11.40 + (i // 8) * step + step / 2)
        for i in range(n)
    ]
    return gpd.GeoDataFrame(geometry=boxes, crs="EPSG:4326")


def test_multipolygon_roi_yields_one_row_per_cell_with_unique_ids():
    """The 2026-07-28 bug: clipping with `gpd.overlay(grids, roi_gdf)` emitted one row per
    (cell x roi-polygon) PAIR, so a 900-field ROI produced 1167 rows for 172 cells -- and
    `id` is the work-unit key, so N rows sharing an id meant N tasks writing the same
    export folder concurrently (`InvalidBlockList` on blob). Clipping to the ROI's UNION
    keeps it one row per cell however many polygons come in."""
    roi = _scattered_roi(40)
    grids = grid.roi_to_s2_grids(roi, grid_size_km=5, scale_fact=1.1)

    assert len(grids) > 0
    assert not grids["id"].duplicated().any()
    assert len(grids) == grids["id"].nunique()
    # and the cell count is a property of the REGION, not of how many polygons describe it
    assert len(grids) <= len(grid.roi_to_s2_grids(roi, grid_size_km=5, scale_fact=1.1,
                                                 clip=False))


def test_multipolygon_roi_clips_to_the_union_not_the_bounding_shape():
    """Clipping to the union must still *clip* -- the returned cells stay inside the ROI
    (this is what distinguishes it from `clip=False`), and cover the same area the ROI's
    polygons do within those cells."""
    roi = _scattered_roi(40)
    union = roi.geometry.union_all()
    grids = grid.roi_to_s2_grids(roi, grid_size_km=5, scale_fact=1.1)

    assert grids.geometry.apply(lambda g: union.buffer(1e-9).contains(g)).all()
    # nothing dropped: the clipped cells together cover the whole ROI
    assert grids.geometry.union_all().area == pytest.approx(union.area, rel=1e-6)


def test_single_polygon_roi_is_unchanged_by_the_union_clip():
    """Regression guard for the fix itself: a single-polygon ROI (the case runbook 38
    Phase 1 ran GREEN on) must tile exactly as before."""
    roi = _roi()
    grids = grid.roi_to_s2_grids(roi, grid_size_km=5, scale_fact=1.1)
    roi_geom = roi.geometry.iloc[0]

    assert not grids["id"].duplicated().any()
    assert grids.geometry.apply(lambda g: roi_geom.buffer(1e-9).contains(g)).all()
    assert grids.geometry.union_all().area == pytest.approx(roi_geom.area, rel=1e-6)
