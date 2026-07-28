"""ROI → S2-geometry grid tiling (spec 19; ROADMAP §4 / P4 groundwork).

Cover a region of interest with fixed-size S2 cells — one cell = one inference datacube = one
task when `run_inference(roi=…)` lands (P4). Cells are scaled up slightly so adjacent tiles
overlap (no seams at mosaic time) and clipped to the ROI so they don't spill outside it.

Clean-room port of `rsutils.s2_grid_utils.get_s2_grids_gdf` (read-only reference). Needs the
optional `[grid]` extra (`pip install -e ".[grid]"`: `s2` + `s2cell`) — kept out of fsd core so
the base install stays lean.
"""

from __future__ import annotations

import geopandas as gpd
import pandas as pd
import shapely.affinity
import shapely.geometry
from shapely.ops import unary_union

__all__ = ["roi_to_s2_grids", "grid_size_to_res", "RES_TO_KM_RANGE"]

# S2 cell edge-length range (km) per level — from s2geometry.io/resources/s2cell_statistics
# (carried wholesale from the legacy reference). Used to map a target grid size → S2 level.
RES_TO_KM_RANGE = {
    0: (7842, 7842), 1: (3921, 5004), 2: (1825, 2489), 3: (840, 1167),
    4: (432, 609), 5: (210, 298), 6: (108, 151), 7: (54, 76),
    8: (27, 38), 9: (14, 19), 10: (7, 9), 11: (3, 5),
    12: (1.699, 2), 13: (0.850, 1.185), 14: (0.425, 0.593), 15: (0.212, 0.296),
}


def grid_size_to_res(grid_size_km: float) -> int:
    """Nearest S2 level whose cell edge-length range brackets `grid_size_km` (5 km → 11)."""
    best_res, best_diff = None, None
    for res, (lo, hi) in RES_TO_KM_RANGE.items():
        for km in (lo, hi):
            diff = abs(km - grid_size_km)
            if best_diff is None or diff < best_diff:
                best_res, best_diff = res, diff
    return best_res


def _as_gdf_4326(roi) -> gpd.GeoDataFrame:
    """Accept a GeoDataFrame, a file path, or a geojson/geometry mapping → GeoDataFrame(4326)."""
    if isinstance(roi, gpd.GeoDataFrame):
        gdf = roi
    elif isinstance(roi, str):
        gdf = gpd.read_file(roi)
    else:  # a geojson dict / __geo_interface__ / shapely geometry
        geom = shapely.geometry.shape(roi["geometry"]) if isinstance(roi, dict) and "geometry" in roi \
            else shapely.geometry.shape(roi)
        gdf = gpd.GeoDataFrame(geometry=[geom], crs="EPSG:4326")
    if gdf.crs is None:
        gdf = gdf.set_crs("EPSG:4326")
    elif gdf.crs.to_epsg() != 4326:
        gdf = gdf.to_crs("EPSG:4326")
    return gdf


def roi_to_s2_grids(roi, *, grid_size_km: float = 5, scale_fact: float = 1.1,
                    res: int | None = None, clip: bool = True) -> gpd.GeoDataFrame:
    """Tile an ROI into overlapping S2 cells, clipped to the ROI.

    Steps (per the ROADMAP §4 recipe): S2-`polyfill` the ROI's **convex hull** at the level for
    `grid_size_km` (5 km → res 11), keep cells that **intersect** the ROI, **scale** each by
    `scale_fact` (1.1 → 10 % overlap per side), then **clip** to the ROI so grids stay inside it
    (`clip=False` keeps the scaled, unclipped cells).

    **An ROI is one region, not a list of shapes.** A multi-row `roi` is `unary_union`-ed into a
    single (multi)polygon *first*, and every step — hull, intersect, clip — works against that
    union. So the output is **one row per S2 cell, ids unique**, whether you pass 1 polygon or
    900 (spec 21 D-GRID-1). If you want one datacube per *shape*, that is not this function:
    pass your shapefile straight to `workflows.create_datacube` with your own `id_col`.

    `roi` is a GeoDataFrame, a file path, or a geojson mapping. Returns a GeoDataFrame with
    columns `id` (the S2 cell id) + `geometry`, in EPSG:4326 — feed it straight to
    `workflows.create_datacube` as the inference shapes (`id_col="id"`).
    """
    try:
        from s2 import s2
    except ImportError as exc:  # pragma: no cover - env-dependent
        raise ImportError(
            "roi_to_s2_grids needs the optional '[grid]' extra: pip install -e '.[grid]' "
            "(brings s2 + s2cell)."
        ) from exc

    roi_gdf = _as_gdf_4326(roi)
    shape = unary_union(list(roi_gdf.geometry.values))
    if res is None:
        res = grid_size_to_res(grid_size_km)

    cells = s2.polyfill(
        geo_json=shapely.geometry.mapping(shape.convex_hull),
        res=res, geo_json_conformant=True, with_id=True,
    )
    df = pd.DataFrame(cells)
    df["geometry"] = df["geometry"].apply(shapely.geometry.Polygon)
    df = df[df["geometry"].apply(shape.intersects)].reset_index(drop=True)
    df["geometry"] = df["geometry"].apply(
        lambda g: shapely.affinity.scale(g, xfact=scale_fact, yfact=scale_fact)
    )
    grids = gpd.GeoDataFrame(df, geometry="geometry", crs="EPSG:4326")

    if clip:
        # Clip to the ROI's UNION (`shape`), never to its individual rows. This is the
        # invariant the rest of this function already assumes -- the polyfill and the
        # `intersects` filter above both go through `shape`.
        #
        # `gpd.overlay(grids, roi_gdf, how="intersection")` emits one row per
        # (cell x roi-polygon) PAIR, so a multi-polygon ROI silently multiplies rows and
        # REPEATS each cell's id. `id` is the work-unit key downstream -- one cell = one
        # datacube = one task, and `create_datacube.setup(id_col="id")` derives
        # `export_folderpath` from it -- so repeated ids mean N tasks writing the SAME
        # folder concurrently. On blob that is a guaranteed `InvalidBlockList` block-commit
        # collision, and the surviving `geometry.geojson` is whichever fragment committed
        # last. Measured 2026-07-28 on a 900-field ROI: 1167 rows for 172 cells, one cell
        # repeated 43x, each row ~0.016 km2 of a 49.6 km2 cell (spec 21 D-GRID-1).
        grids["geometry"] = grids.geometry.intersection(shape)
        # A cell that only *touches* the ROI can intersect to a line/point; drop those
        # (and any empties) so every returned row is a real polygonal work unit.
        grids = grids[
            ~grids.geometry.is_empty
            & grids.geometry.notna()
            & grids.geom_type.isin(("Polygon", "MultiPolygon"))
        ].reset_index(drop=True)

    if grids["id"].duplicated().any():  # pragma: no cover - structurally impossible now
        dupes = grids["id"].value_counts()
        raise AssertionError(
            f"roi_to_s2_grids produced duplicate cell ids "
            f"({int((dupes > 1).sum())} of {grids['id'].nunique()} repeated, worst "
            f"{dupes.iloc[0]}x) -- one cell must be exactly one row (spec 21 D-GRID-1)."
        )
    return grids
