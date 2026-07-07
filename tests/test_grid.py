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
