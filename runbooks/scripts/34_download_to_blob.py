"""Spec 34 / download-to-blob — CDSE and/or MPC land a self-describing artifact on
Azure Blob (`--dst`), then verify the GDAL scale/offset/nodata tag + STAC raster:bands.

Run-book: `runbooks/34-download-to-blob.md`. This is the credentialed/networked step
Claude never runs itself (CLAUDE.md) — run it on a cloud VM near the `rise` blob
account (see the run-book for why: `fs.transfer` streams through the launching
machine, so running here keeps the bytes off your laptop/hotspot).

Self-contained by design (spec-31 runbook pattern): everything is inside try/except so
`_result.json` is written even on a hard failure; `--dst` is the only input (no `rise`
values committed to this public repo); idempotent (both `fsd.sources.cdse.download`
and `fsd.sources.mpc.download` skip files already present).

Usage (see the run-book for the real --dst):
    .venv/bin/python runbooks/scripts/34_download_to_blob.py \\
        --dst "abfss://<fs>@<account>.dfs.core.windows.net/spec34-demo/" \\
        --source cdse --cdse-creds ~/cdse_credentials.json
    .venv/bin/python runbooks/scripts/34_download_to_blob.py \\
        --dst "abfss://<fs>@<account>.dfs.core.windows.net/spec34-demo/" \\
        --source mpc
"""

import argparse
import datetime
import json
import os
import pathlib
import sys
import traceback

# fsd/runbooks/scripts/34_download_to_blob.py -> parents[2] == fsd/
FSD_ROOT = pathlib.Path(__file__).resolve().parents[2]
ROI_PATH = FSD_ROOT.parent / "shapefiles" / "s2grid=476da24.geojson"  # single-tile, T33UWP
OUT = FSD_ROOT / "tests" / "outputs" / "spec34_download_to_blob"

# Small + cheap: one band + the mask band, one short window (a handful of granules).
BANDS = ["B04", "SCL"]
STARTDATE = datetime.datetime(2022, 6, 1)
ENDDATE = datetime.datetime(2022, 6, 20)

result = {
    "step": "spec34-download-to-blob",
    "status": "ok",
    "pass": False,
    "metrics": {},
    "expected": {
        "cog_present": True,
        "cog_nonzero_bytes": True,
        "gdal_offset_or_scale_tag_present": True,
        "gdal_nodata_declared": True,
        "catalog_local_folderpath_is_abfss": True,
        "stac_raster_bands_present": True,
    },
    "error": None,
}


def _verify_on_blob(catalog_filepath: str, dst_folderpath: str) -> dict:
    """Independent read-back from the blob side: COG present + non-zero, the GDAL
    tag declares scale/offset + nodata, catalog paths are all abfss://, and the STAC
    export carries raster:bands (spec 34 §4 download-to-blob acceptance)."""
    from fsd.catalog.catalog import TileCatalog
    from fsd.raster import rio_open
    from fsd.storage import fs

    metrics = {}
    gdf = TileCatalog(catalog_filepath).read()
    metrics["catalog_rows"] = int(len(gdf))
    paths = [
        os.path.join(str(r["local_folderpath"]), f)
        for _, r in gdf.iterrows() for f in str(r["files"]).split(",")
    ]
    metrics["catalog_local_folderpath_is_abfss"] = bool(
        all(str(r["local_folderpath"]).startswith("abfss://") for _, r in gdf.iterrows())
    )

    b04 = next((p for p in paths if p.endswith("B04.tif")), None)
    metrics["cog_present"] = bool(b04 and fs.exists(b04))
    if b04:
        metrics["cog_nonzero_bytes"] = fs.size(b04) > 0
        with rio_open(b04) as src:
            metrics["gdal_offset_or_scale_tag_present"] = bool(
                (src.offsets and src.offsets[0] != 0) or (src.scales and src.scales[0] != 1)
            )
            metrics["gdal_nodata_declared"] = src.nodata is not None

    stac_dst = os.path.join(dst_folderpath, "stac")
    catalog_json = TileCatalog(catalog_filepath).to_stac(stac_dst)
    import pystac
    from pystac.extensions.raster import RasterExtension

    cat = pystac.Catalog.from_file(catalog_json)
    items = list(cat.get_items(recursive=True))
    metrics["stac_items"] = len(items)
    has_raster_bands = any(
        RasterExtension.has_extension(it) and any(
            RasterExtension.ext(a).bands for a in it.assets.values()
            if RasterExtension.has_extension(it)
        )
        for it in items
    )
    metrics["stac_raster_bands_present"] = bool(has_raster_bands)
    return metrics


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dst", required=True,
                    help="abfss://<fs>@<account>.dfs.core.windows.net/<prefix>/ (trailing / optional)")
    ap.add_argument("--source", required=True, choices=["cdse", "mpc"])
    ap.add_argument("--cdse-creds", default=None,
                    help="path to a gitignored cdse_credentials.json (required for --source cdse)")
    args = ap.parse_args()

    if os.environ.get("FSSPEC_ABFSS_ANON", "").lower() not in ("false", "0", "f"):
        raise RuntimeError(
            "FSSPEC_ABFSS_ANON is not set to 'false'. Without it adlfs may attempt "
            "anonymous access and every write will 403. Run: export FSSPEC_ABFSS_ANON=false"
        )

    dst = args.dst.rstrip("/") + f"/{args.source}"
    result["metrics"]["source"] = args.source
    result["metrics"]["dst_is_abfss"] = dst.startswith("abfss://")

    import fsd
    from fsd.sources.cdse import CdseCredentials

    creds = None
    if args.source == "cdse":
        if not args.cdse_creds:
            raise ValueError("--cdse-creds is required for --source cdse")
        creds = CdseCredentials.from_json(args.cdse_creds)

    catalog_filepath = fsd.download(
        roi=str(ROI_PATH), startdate=STARTDATE, enddate=ENDDATE, bands=BANDS,
        dst_folderpath=dst, creds=creds, source=args.source, max_tiles=10,
        storage="azure", progress=True,
    )
    result["metrics"]["catalog_filepath"] = catalog_filepath

    result["metrics"].update(_verify_on_blob(catalog_filepath, dst))
    result["pass"] = bool(
        result["metrics"].get("catalog_rows", 0) > 0
        and result["metrics"]["cog_present"]
        and result["metrics"]["cog_nonzero_bytes"]
        and result["metrics"]["gdal_offset_or_scale_tag_present"]
        and result["metrics"]["gdal_nodata_declared"]
        and result["metrics"]["catalog_local_folderpath_is_abfss"]
        and result["metrics"]["stac_raster_bands_present"]
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
            OUT.mkdir(parents=True, exist_ok=True)
            (OUT / f"_result_{result['metrics'].get('source', 'unknown')}.json").write_text(
                json.dumps(result, indent=2)
            )
            print(json.dumps(result, indent=2))
        except Exception:
            traceback.print_exc()
        sys.exit(0 if result["pass"] else 1)
