"""Spec 44 phase 1 — a real ROI inference run on the **generic** image (run-book 45, Phase 2).

Phase 1 proved the adapter *imports* on a node with no adapter in the image. This proves the whole
pipeline still *works* through it: tile the ROI into grid cells, build a datacube per cell, predict,
write one COG per cell + a STAC catalog -- all with `bundle.load` resolving the adapter from the
bundle's `code/` on every node.

Deliberately a **small, single-MGRS-tile ROI** so this is minutes, not an hour:
`shapefiles/s2grid=476da24.geojson` sits 100% inside T33UWP (verified 2026-07-17), so it exercises
the simple single-tile path. Point AZ_ROI elsewhere for a bigger run.

The date window defaults to the demo's: 2018-04-01 -> 2018-09-30 at mosaic_days=20, which gives
**T=10** -- and the bundle must declare n_timestamps=10 to match. That is checked on the driver
before anything is dispatched, because a T mismatch after the cubes are built is money wasted.

Required env vars (same set as Phase 1, plus the catalog + an output root):
    AZ_SUBSCRIPTION_ID  AZ_RG  AZ_ML_WORKSPACE  AZ_CLUSTER  AZ_UAMI_CLIENT_ID
    AZ_ROOT  AZ_INFER_ENV_NAME  AZ_INFER_ENV_VERSION  AZ_BUNDLE_LOCAL  AZ_ARCHIVE_CATALOG

Optional:
    AZ_ROI          default ../shapefiles/s2grid=476da24.geojson
    AZ_OUT_SUFFIX   default a UTC timestamp. The output folder IS the run id -- a FRESH one every
                    time, because a stale `input.csv` in an existing folder silently ignores a
                    changed ROI (issue #66). Do not reuse one to "resume" unless you mean to.
    AZ_MERGE        set to 1 to also produce the merged crop map (adds a driver-side download of
                    every output COG over VPN -- slow; issue #65)

Usage, from the `fsd/` package root:
    .venv/bin/python runbooks/scripts/45_phase2_roi_inference.py
"""

import datetime
import json
import os
import pathlib
import traceback

# fsd/runbooks/scripts/45_phase2_roi_inference.py -> parents[2] == fsd/
FSD_ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = FSD_ROOT / "tests" / "outputs" / "spec44_verify"
DEFAULT_ROI = FSD_ROOT.parent / "shapefiles" / "s2grid=476da24.geojson"

# Naive on purpose: fsd localizes user dates to UTC itself (`dt2ts`), and this is exactly what the
# demo notebook passes. Do not "fix" these to tz-aware -- match the API's documented contract.
STARTDATE = datetime.datetime(2018, 4, 1)   # noqa: DTZ001
ENDDATE = datetime.datetime(2018, 9, 30)    # noqa: DTZ001
MOSAIC_DAYS = 20
BANDS = ["B04", "B08"]

REQUIRED = (
    "AZ_SUBSCRIPTION_ID", "AZ_RG", "AZ_ML_WORKSPACE", "AZ_CLUSTER", "AZ_UAMI_CLIENT_ID",
    "AZ_ROOT", "AZ_INFER_ENV_NAME", "AZ_INFER_ENV_VERSION", "AZ_BUNDLE_LOCAL",
    "AZ_ARCHIVE_CATALOG",
)

result = {
    "step": "spec44-phase2-roi-inference",
    "status": "ok",
    "pass": False,
    "metrics": {},
    "expected": {"n_outputs_gt_0": True, "all_cells_have_output": True},
    "error": None,
}

try:
    OUT.mkdir(parents=True, exist_ok=True)

    missing = [k for k in REQUIRED if not os.environ.get(k)]
    if missing:
        raise SystemExit(
            "missing env vars: " + ", ".join(missing)
            + "\nSource env.example.sh + AZURE_INFRA_PRIVATE.md. Run Phase 1 first -- if its "
            "smoke did not pass, this run will fail the same way on every node instead of once."
        )

    import fsd
    from fsd.model import bundle as fsd_bundle
    from fsd.storage import fs

    roi = os.environ.get("AZ_ROI") or str(DEFAULT_ROI)
    if not os.path.exists(roi):
        raise SystemExit(f"ROI not found: {roi!r}. Set AZ_ROI to a geojson you have.")

    # --- driver preflight: the T contract, and that the bundle still carries its code -------
    manifest = fsd_bundle.read_spec(os.environ["AZ_BUNDLE_LOCAL"])   # model-free, no import
    want_t = fsd.compute_n_timestamps(STARTDATE, ENDDATE, MOSAIC_DAYS)
    declared_t = manifest.get("n_timestamps")

    result["metrics"]["roi"] = roi
    result["metrics"]["bundle_version"] = manifest.get("fsd_bundle_version")
    result["metrics"]["adapter_ref"] = manifest.get("adapter")
    result["metrics"]["code_block_present"] = bool(manifest.get("code"))
    result["metrics"]["n_timestamps_window"] = want_t
    result["metrics"]["n_timestamps_bundle"] = declared_t

    if not manifest.get("code"):
        raise SystemExit(
            "this bundle carries no `code` block, so it does not exercise spec 44 at all. "
            "Re-save it (run-book Phase 1d)."
        )
    if declared_t and declared_t != want_t:
        raise SystemExit(
            f"T mismatch: {STARTDATE:%Y-%m-%d}..{ENDDATE:%Y-%m-%d} at mosaic_days={MOSAIC_DAYS} "
            f"gives T={want_t}, but the bundle declares n_timestamps={declared_t}. Fix the window "
            "or use a bundle trained on this T -- a mismatch after the cubes are built is money "
            "already spent."
        )
    if not fs.exists(os.environ["AZ_ARCHIVE_CATALOG"]):
        raise SystemExit(
            f"catalog not found: {os.environ['AZ_ARCHIVE_CATALOG']!r}. Inference never downloads "
            "(SO-6) -- the imagery must already be on blob (run-book 37)."
        )

    # The output folder IS the run id. Fresh every time (issue #66).
    suffix = os.environ.get("AZ_OUT_SUFFIX") or datetime.datetime.now(
        datetime.UTC
    ).strftime("%Y%m%dT%H%M%SZ")
    out_url = f"{os.environ['AZ_ROOT']}/runs/spec44-phase2-{suffix}"
    result["metrics"]["output_folderpath"] = out_url

    env_ref = f"{os.environ['AZ_INFER_ENV_NAME']}:{os.environ['AZ_INFER_ENV_VERSION']}"
    result["metrics"]["environment"] = env_ref
    print(f"ROI      : {roi}")
    print(f"window   : {STARTDATE:%Y-%m-%d}..{ENDDATE:%Y-%m-%d} @ {MOSAIC_DAYS}d -> T={want_t}")
    print(f"image    : {env_ref}   (no adapter baked in -- that is the point)")
    print(f"output   : {out_url}")
    print("dispatching; a cold cluster adds 40-380 s before anything appears.\n")

    t0 = datetime.datetime.now(datetime.UTC)
    inference = fsd.run_inference(
        os.environ["AZ_BUNDLE_LOCAL"],
        output_folderpath=out_url,
        roi=roi,
        catalog_filepath=os.environ["AZ_ARCHIVE_CATALOG"],
        startdate=STARTDATE,
        enddate=ENDDATE,
        mosaic_days=MOSAIC_DAYS,
        bands=BANDS,
        merge=bool(os.environ.get("AZ_MERGE")),
        runner="aml",
        runner_kwargs={
            "cluster": os.environ["AZ_CLUSTER"],
            "environment": env_ref,
            "identity_client_id": os.environ["AZ_UAMI_CLIENT_ID"],
        },
        storage=os.environ["AZ_ROOT"],
        progress=True,
    )
    elapsed = (datetime.datetime.now(datetime.UTC) - t0).total_seconds()

    outputs = list(getattr(inference, "output_filepaths", []) or [])
    result["metrics"]["n_outputs"] = len(outputs)
    result["metrics"]["wall_seconds"] = round(elapsed, 1)
    result["metrics"]["first_output"] = outputs[0] if outputs else None
    result["metrics"]["stac_catalog"] = getattr(inference, "stac_catalog_filepath", None)
    if getattr(inference, "merged_filepath", None):
        result["metrics"]["merged_filepath"] = inference.merged_filepath

    landed = sum(1 for p in outputs if fs.exists(p))
    result["metrics"]["outputs_on_blob"] = f"{landed}/{len(outputs)}"
    result["pass"] = len(outputs) > 0 and landed == len(outputs)
    result["status"] = "ok" if result["pass"] else "fail"

except SystemExit as exc:
    result["status"] = "fail"
    result["pass"] = False
    result["error"] = str(exc)
except Exception:  # noqa: BLE001 - spec 24: ALWAYS write _result.json, never a bare traceback
    result["status"] = "fail"
    result["pass"] = False
    result["error"] = traceback.format_exc()[-2000:]

OUT.mkdir(parents=True, exist_ok=True)
with open(OUT / "_result_phase2.json", "w") as f:
    json.dump(result, f, indent=2)
print(json.dumps(result, indent=2))
print(f"\nwrote {OUT / '_result_phase2.json'}")
