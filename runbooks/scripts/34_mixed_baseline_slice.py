"""Spec 34 §1e acceptance, local half — pull a small MPC slice straddling the S2
processing-baseline cutover (2022-01-25) to LOCAL disk, stamped with each item's own
declared offset/scale/nodata. This is the input the mini-MPC cross-baseline run-book
(`runbooks/34-mini-mpc-cross-baseline.md`) registers into pgSTAC.

Deliberately MPC, not CDSE (spec 34 §1e): MPC exposes NO raster:bands/renders offset of
its own, so fsd's ingest-written tag is the only thing that makes a single XYZ URL
render this slice consistently across the baseline. Deliberately local, not blob
(`[G6]`): this proves the offset->unscale mechanism, storage-agnostic; titiler-reads-
blob is a separate P5 serving item.

Usage:
    .venv/bin/python runbooks/scripts/34_mixed_baseline_slice.py --dst tests/outputs/spec34_mixed_baseline
"""

import argparse
import datetime
import json
import pathlib
import sys
import traceback

FSD_ROOT = pathlib.Path(__file__).resolve().parents[2]
ROI_PATH = FSD_ROOT.parent / "shapefiles" / "s2grid=476da24.geojson"  # single-tile, T33UWP

BANDS = ["B04", "B03", "B02", "SCL"]  # a visible-light RGB + mask, for the QGIS eyeball
# Same MGRS tile, one pre-cutover and one post-cutover window (spec 34 §1e).
PRE_WINDOW = (datetime.datetime(2021, 6, 14), datetime.datetime(2021, 6, 19))
POST_WINDOW = (datetime.datetime(2022, 6, 14), datetime.datetime(2022, 6, 19))

result = {
    "step": "spec34-mixed-baseline-slice",
    "status": "ok",
    "pass": False,
    "metrics": {},
    "expected": {
        "pre_items": ">=1", "post_items": ">=1",
        "offsets_differ_across_baseline": True,
    },
    "error": None,
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dst", required=True, help="local output folder")
    args = ap.parse_args()

    import geopandas as gpd

    from fsd.catalog.catalog import TileCatalog
    from fsd.sources import mpc

    dst = pathlib.Path(args.dst)
    dst.mkdir(parents=True, exist_ok=True)
    catalog_fp = str(dst / "catalog.parquet")
    catalog = TileCatalog(catalog_fp)
    roi = gpd.read_file(ROI_PATH)

    for label, (start, end) in [("pre", PRE_WINDOW), ("post", POST_WINDOW)]:
        r = mpc.download(
            roi, start, end, BANDS, str(dst), catalog, max_tiles=5, progress=True,
        )
        result["metrics"][f"{label}_successful"] = r.successful_count
        result["metrics"][f"{label}_failed"] = r.failed_count

    gdf = catalog.read()
    result["metrics"]["catalog_rows"] = int(len(gdf))
    offsets = sorted(set(gdf["offset"].tolist()))
    result["metrics"]["distinct_offsets"] = offsets
    result["metrics"]["offsets_differ_across_baseline"] = len(offsets) > 1

    result["pass"] = bool(
        result["metrics"].get("pre_successful", 0) > 0
        and result["metrics"].get("post_successful", 0) > 0
        and result["metrics"]["offsets_differ_across_baseline"]
    )


if __name__ == "__main__":
    try:
        main()
    except BaseException as e:
        result["status"] = "failed"
        result["pass"] = False
        result["error"] = f"{type(e).__name__}: {e}"
        traceback.print_exc()
    finally:
        try:
            out_dir = pathlib.Path(
                sys.argv[sys.argv.index("--dst") + 1]
            ) if "--dst" in sys.argv else FSD_ROOT / "tests" / "outputs" / "spec34_mixed_baseline"
            out_dir.mkdir(parents=True, exist_ok=True)
            (out_dir / "_result.json").write_text(json.dumps(result, indent=2))
            print(json.dumps(result, indent=2))
        except Exception:
            traceback.print_exc()
        sys.exit(0 if result["pass"] else 1)
