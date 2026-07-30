"""Spec 42 step 0 / run-book 43 Step 0: derive the tutorial cell's ROI + labels
from the workspace shapefiles.

Laptop-only, offline, seconds. `shapefiles/` lives at the workspace root, outside
this repo, so a `git clone` on a VM cannot supply it -- this script writes two
small GeoJSONs (`roi.geojson`, `fields.geojson`) that run-book 43 Steps 2-4
(on the Azure VM) consume instead, so the VM never needs the workspace root.

CLI is normative (run-book 43 Step 0) -- match these flags exactly:

    python tests/data/tutorial/derive_roi_and_labels.py \\
        --at-roi   ../shapefiles/AT_ROI.geojson \\
        --fields   ../shapefiles/AT_2018_TRAIN.geojson \\
        --cell-id  4772924 \\
        --out      tests/data/tutorial \\
        --result   tests/outputs/p6_tutorial_fixture/_result_step0.json

Not part of the fsd wheel; not run by the test suite (spec 42 D4) -- its output
(`roi.geojson`, `fields.geojson`) is the artifact, committed alongside it.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

import geopandas as gpd

from fsd.grid import roi_to_s2_grids

# spec 42 D3: the raw 7-class EuroCrops label collapses to 3 trainable classes.
# maize/hemp are the two largest classes and keep their identity; alfalfa,
# mustard, winter wheat, pasture and spring wheat are four near-singletons over
# 43 samples -- not trainable on their own -- and collapse to "other". This is
# the one greppable home for the mapping; docs/tutorial.md (spec 41 P7) states it
# by citing this table, not by re-deriving it.
CROP_LABEL_KEEP = {"maize", "hemp"}
CROP_LABEL_OTHER = "other"
# The collapse must yield exactly this many classes for Step 0 to PASS
# (run-book 43 Step 0; spec 42 D3's maize/hemp/other).
EXPECTED_N_CLASSES = 3

__all__ = [
    "CROP_LABEL_KEEP", "CROP_LABEL_OTHER", "EXPECTED_N_CLASSES",
    "collapse_label", "derive", "main",
]


def collapse_label(raw_crop: str) -> str:
    """spec 42 D3's 3-class collapse, case-insensitive against the raw
    `EC_hcat_n` value: `maize`/`hemp` keep their name, everything else becomes
    `"other"`."""
    key = str(raw_crop).strip().lower()
    return key if key in CROP_LABEL_KEEP else CROP_LABEL_OTHER


def derive(
    at_roi_path: str, fields_path: str, cell_id: str, *, grid_size_km: float = 5.0
) -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame]:
    """Returns `(cell_gdf, fields_gdf)`: the one S2 grid cell matching `cell_id`
    (derived via `roi_to_s2_grids`, never hand-picked) and its fields, clipped to
    the cell with `fid` + `crop` (raw) + `label` (collapsed) columns.

    Raises `ValueError` if `cell_id` is not among the cells `roi_to_s2_grids`
    derives from `at_roi_path` -- the documented trap (run-book 43 Step 0): the
    wrong cell id (e.g. one ~0.6 degrees east) silently selects a cell with zero
    labelled fields rather than failing, so this at least fails loudly on a
    typo'd id that doesn't exist at all.
    """
    grids = roi_to_s2_grids(at_roi_path, grid_size_km=grid_size_km)
    cell = grids[grids["id"].astype(str) == str(cell_id)]
    if len(cell) == 0:
        raise ValueError(
            f"cell id {cell_id!r} not found among the {len(grids)} cells "
            f"roi_to_s2_grids derived from {at_roi_path!r} at "
            f"grid_size_km={grid_size_km} -- check the id, don't hand-pick one."
        )
    if len(cell) > 1:  # pragma: no cover - roi_to_s2_grids guarantees unique ids
        raise AssertionError(f"cell id {cell_id!r} matched {len(cell)} rows, expected 1.")
    cell = cell.reset_index(drop=True)

    fields = gpd.read_file(fields_path)
    for col in ("fid", "EC_hcat_n"):
        if col not in fields.columns:
            raise ValueError(f"{fields_path!r}: missing required column {col!r}.")
    if fields.crs is None:
        fields = fields.set_crs("EPSG:4326")
    elif fields.crs.to_epsg() != 4326:
        fields = fields.to_crs("EPSG:4326")

    cell_shape = cell.geometry.iloc[0]
    clipped = fields[fields.intersects(cell_shape)].copy()
    clipped["geometry"] = clipped.geometry.intersection(cell_shape)
    clipped = clipped[~clipped.geometry.is_empty].reset_index(drop=True)

    out_fields = gpd.GeoDataFrame(
        {
            "fid": clipped["fid"].values,
            "crop": clipped["EC_hcat_n"].values,
            "label": [collapse_label(c) for c in clipped["EC_hcat_n"]],
        },
        geometry=clipped.geometry.values,
        crs="EPSG:4326",
    )
    return cell, out_fields


def _write_result(path: str, result: dict) -> None:
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w") as f:
        json.dump(result, f, indent=2, default=str)


def _parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="python tests/data/tutorial/derive_roi_and_labels.py",
        description="Spec 42 step 0: derive the tutorial ROI cell + its labelled "
                     "fields from the workspace shapefiles (run-book 43 Step 0).",
    )
    p.add_argument("--at-roi", required=True, help="path to AT_ROI.geojson")
    p.add_argument("--fields", required=True, help="path to AT_2018_TRAIN.geojson")
    p.add_argument("--cell-id", required=True, help="the S2 grid cell id to select")
    p.add_argument("--grid-size-km", type=float, default=5.0)
    p.add_argument("--out", required=True, help="output dir for roi.geojson + fields.geojson")
    p.add_argument("--result", required=True, help="path to write the _result.json")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = _parse_args(argv)
    try:
        cell, fields = derive(
            args.at_roi, args.fields, args.cell_id, grid_size_km=args.grid_size_km
        )
    except Exception as e:  # noqa: BLE001 - still leave a pasteable result, then re-raise
        _write_result(args.result, {
            "step": "step0_derive_roi_and_labels",
            "status": "failed",
            "pass": False,
            "metrics": {},
            "expected": {},
            "error": repr(e),
        })
        raise

    os.makedirs(args.out, exist_ok=True)
    roi_path = os.path.join(args.out, "roi.geojson")
    fields_path = os.path.join(args.out, "fields.geojson")
    cell[["id", "geometry"]].to_file(roi_path, driver="GeoJSON")
    fields.to_file(fields_path, driver="GeoJSON")

    minx, miny, maxx, maxy = cell.total_bounds
    counts = fields["label"].value_counts().to_dict()
    class_str = " ".join(f"{k}={v}" for k, v in sorted(counts.items(), key=lambda kv: -kv[1]))
    print(
        f"cell {args.cell_id}  bounds {minx:.4f},{miny:.4f},{maxx:.4f},{maxy:.4f}  "
        f"fields {len(fields)}  classes {class_str}"
    )

    # Run-book 43 Step 0's stated PASS conditions, actually evaluated. A
    # hardcoded `"pass": True` here would report success even when the collapse
    # produced one class -- the exact failure mode if `EC_hcat_n`'s real values
    # are not literally "maize"/"hemp" (everything would become "other"), and
    # `_result.json` is what gets pasted back, not the logs (spec 24).
    n_classes = len(counts)
    passed = bool(len(fields) > 0 and n_classes == EXPECTED_N_CLASSES)
    _write_result(args.result, {
        "step": "step0_derive_roi_and_labels",
        "status": "ok" if passed else "failed",
        "pass": passed,
        "metrics": {
            "cell_id": str(args.cell_id),
            "bounds": [round(minx, 4), round(miny, 4), round(maxx, 4), round(maxy, 4)],
            "fields": int(len(fields)),
            "n_classes": int(n_classes),
            "classes": {str(k): int(v) for k, v in counts.items()},
            "roi_path": roi_path,
            "fields_path": fields_path,
        },
        "expected": {"n_classes": EXPECTED_N_CLASSES, "fields_non_empty": True},
        "error": None,
    })
    if not passed:
        print(
            f"FAIL: expected {EXPECTED_N_CLASSES} classes over a non-empty field "
            f"set, got {n_classes} class(es) over {len(fields)} field(s). If every "
            f"field collapsed to {CROP_LABEL_OTHER!r}, the raw EC_hcat_n values do "
            f"not literally match {sorted(CROP_LABEL_KEEP)} -- check them before "
            "editing the mapping.",
            file=sys.stderr,
        )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
