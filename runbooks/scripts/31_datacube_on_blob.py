"""Spec 31 / P1 — build a Sentinel-2 datacube reading + writing the `rise` blob.

Run-book: `runbooks/31-p1-datacube-on-blob.md`. This is the **compute-seam demo**:
step 1 (`runbooks/31-p1-upload-slice.md`) already put real, already-COG imagery on
blob with a catalog whose every band path is `abfss://`; this script proves the fsd
*pipeline* — not just raw fsspec I/O — reads and writes that blob data end to end,
with **no download involved** (deliberately: the seam is proven independently of the
ingest/normalization redesign, spec 31's roadmap pivot).

Two builds, for two different reasons (see PROGRESS.md / CHANGES.md 2026-07-17 for the
full finding):

1. **`python -m fsd.workflows.task` invoked directly, as a real subprocess, with a
   REMOTE `--export-folderpath`.** Proves the actual claim spec 31 §"The demo" step 2
   cares about — `datacube.npy`/`metadata.pickle.npy` written to blob by the real
   builder, GDAL `/vsiadls/` streaming reads of blob COGs (D2/§4) — AND proves D4
   (FSSPEC_* env inheritance across a subprocess boundary), since this *is* the exact
   CLI unit-of-work the Snakemake runner itself shells out to (spec 10 Seam 2).
2. **`fsd.create_training_data(..., storage="azure")` through the REAL local Snakemake
   runner, catalog on blob but `export_folderpath` LOCAL.** Proves the same D2/D4
   claims through the "official" orchestration layer (not just a bare CLI call).
   `export_folderpath` is deliberately kept local here: the local Snakemake runner's
   own start.txt/done.txt resumability sentinels are plain os.makedirs/open, not
   fsd.storage-routed, so a remote `export_folderpath` now raises a clear error
   (fixed a silent-corruption bug in `os.path.abspath` first — see CHANGES.md) rather
   than one being fully supported. Build (1) is what actually proves the write-to-blob
   claim; build (2) proves the pipeline's normal entrypoint still works unchanged
   against a blob catalog.

Self-contained by design (spec 24 D2): try/except around everything, `_result.json`
written unconditionally, `--catalog`/`--out` passed as arguments (no `rise` values
committed to this public repo).

Usage, from the `fsd/` package root (see the run-book for the real --catalog/--out):
    .venv/bin/python runbooks/scripts/31_datacube_on_blob.py \\
        --catalog "abfss://<fs>@<account>.dfs.core.windows.net/p1-demo/imagery/catalog.parquet" \\
        --out "abfss://<fs>@<account>.dfs.core.windows.net/p1-demo/build/"
"""

import argparse
import json
import os
import pathlib
import subprocess
import sys
import traceback

# fsd/runbooks/scripts/31_datacube_on_blob.py -> parents[2] == fsd/
FSD_ROOT = pathlib.Path(__file__).resolve().parents[2]
ROI_PATH = FSD_ROOT.parent / "shapefiles" / "s2grid=476da24.geojson"
OUT = FSD_ROOT / "tests" / "outputs" / "spec31_datacube_on_blob"

# Must match the uploaded slice (runbooks/31-p1-upload-slice.md): T33UWP, Jul-Aug 2018,
# B08+SCL. Calendar windows tile [startdate, enddate) in mosaic_days steps anchored at
# startdate, so 2018-07-01..2018-09-01 (62 days) at mosaic_days=30 yields ceil(62/30)=3
# windows ([Jul01,Jul31), [Jul31,Aug30), [Aug30,...]) -- a data-INDEPENDENT count (the
# calendar scheme emits every window, even an empty trailing one as an all-mask slice).
# This is verified against fsd.datacube.ops._calendar_windows, NOT eyeballed: the spec's
# own "T=2 at mosaic_days=30" prose was an arithmetic slip (62/30 rounds up to 3, not 2).
# A real multi-window axis regardless, not the degenerate T=1 runbook 32 v1 tripped on.
# B08 = REFERENCE_BAND; SCL is structurally required by build_datacube's hardcoded
# mask->drop chain (TODO #35) -- do not simplify to 1 band.
STARTDATE = "2018-07-01"
ENDDATE = "2018-09-01"
BANDS = "B08,SCL"
MOSAIC_DAYS = 30
EXPECTED_T = 3

result = {
    "step": "spec31-datacube-on-blob",
    "status": "ok",
    "pass": False,
    "metrics": {},
    "expected": {
        "task_subprocess_returncode": 0,
        "task_datacube_on_blob_exists": True,
        "task_timestamps_len": EXPECTED_T,
        "task_readback_dtype_is_uint16_or_float": True,
        "snakemake_build_returncode": 0,
        "snakemake_timestamps_len": EXPECTED_T,
    },
    "error": None,
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--catalog", required=True,
                    help="abfss://<fs>@<account>.dfs.core.windows.net/.../catalog.parquet "
                         "(the catalog runbooks/31-p1-upload-slice.md wrote)")
    ap.add_argument("--out", required=True,
                    help="abfss://<fs>@<account>.dfs.core.windows.net/<prefix>/ "
                         "(trailing / optional) -- a scratch prefix this run owns")
    args = ap.parse_args()

    if os.environ.get("FSSPEC_ABFSS_ANON", "").lower() not in ("false", "0", "f"):
        raise RuntimeError(
            "FSSPEC_ABFSS_ANON is not set to 'false'. Run: export FSSPEC_ABFSS_ANON=false"
        )
    if not ROI_PATH.exists():
        raise FileNotFoundError(f"ROI geometry not found: {ROI_PATH}")

    out = args.out.rstrip("/")
    remote_export = f"{out}/task-direct/cube"

    # --- build 1: `workflows.task` invoked directly, as a real subprocess, writing to blob
    print(f"[1/2] python -m fsd.workflows.task -> {remote_export}")
    cmd = [
        sys.executable, "-m", "fsd.workflows.task",
        str(ROI_PATH), args.catalog, STARTDATE, ENDDATE, remote_export,
        "--bands", BANDS, "--mosaic-days", str(MOSAIC_DAYS),
    ]
    # No env= override: this subprocess inherits os.environ as-is, so a successful run
    # is itself the D4 proof that FSSPEC_ABFSS_ANON crosses the subprocess boundary.
    proc = subprocess.run(cmd, capture_output=True, text=True)
    result["metrics"]["task_subprocess_returncode"] = proc.returncode
    result["metrics"]["task_subprocess_stderr_tail"] = proc.stderr[-2000:]
    if proc.returncode != 0:
        raise RuntimeError("workflows.task subprocess failed (see task_subprocess_stderr_tail)")

    from fsd.storage import fs

    cube_path = f"{remote_export}/datacube.npy"
    meta_path = f"{remote_export}/metadata.pickle.npy"
    result["metrics"]["task_datacube_on_blob_exists"] = bool(fs.exists(cube_path))
    result["metrics"]["task_metadata_on_blob_exists"] = bool(fs.exists(meta_path))

    cube = fs.load_npy(cube_path)
    meta = fs.load_npy(meta_path, allow_pickle=True)[()]
    result["metrics"]["task_datacube_shape"] = list(cube.shape)
    result["metrics"]["task_datacube_dtype"] = str(cube.dtype)
    result["metrics"]["task_timestamps_len"] = len(meta["timestamps"])
    result["metrics"]["task_readback_dtype_is_uint16_or_float"] = str(cube.dtype) in (
        "uint16", "float32", "float64",
    )
    print(f"  datacube.npy shape={cube.shape} dtype={cube.dtype} T={len(meta['timestamps'])}")

    # --- build 2: create_training_data through the REAL Snakemake runner, catalog on
    # blob, export_folderpath LOCAL (the sentinel-bookkeeping limitation -- see module
    # docstring). Proves D2/D4 through the normal entrypoint, not just a bare CLI call.
    print("[2/2] fsd.create_training_data(storage='azure') via the local Snakemake runner")
    import geopandas as gpd

    import fsd

    roi_gdf = gpd.read_file(ROI_PATH)
    roi_gdf["label"] = "na"

    local_out = OUT / "snakemake-run"
    try:
        training = fsd.create_training_data(
            label_polygons=roi_gdf, catalog_filepath=args.catalog,
            startdate=STARTDATE, enddate=ENDDATE, mosaic_days=MOSAIC_DAYS,
            bands=BANDS.split(","), id_col="id", label_col="label",
            export_folderpath=str(local_out), storage="azure",
        )
        result["metrics"]["snakemake_build_returncode"] = 0
        result["metrics"]["snakemake_timestamps_len"] = training.n_timestamps
        result["metrics"]["snakemake_n_pixels"] = training.n_pixels
    except Exception as exc:
        result["metrics"]["snakemake_build_returncode"] = 1
        result["metrics"]["snakemake_build_error"] = f"{type(exc).__name__}: {exc}"
        raise

    result["pass"] = bool(
        result["metrics"]["task_subprocess_returncode"] == 0
        and result["metrics"]["task_datacube_on_blob_exists"]
        and result["metrics"]["task_metadata_on_blob_exists"]
        and result["metrics"]["task_timestamps_len"] == EXPECTED_T
        and result["metrics"]["task_readback_dtype_is_uint16_or_float"]
        and result["metrics"]["snakemake_build_returncode"] == 0
        and result["metrics"]["snakemake_timestamps_len"] == EXPECTED_T
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
            (OUT / "_result.json").write_text(json.dumps(result, indent=2))
            print(f"\n_result.json -> {OUT / '_result.json'}")
            print(json.dumps(result, indent=2))
        except Exception:
            traceback.print_exc()
        sys.exit(0 if result["pass"] else 1)
