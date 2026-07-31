"""Spec 33 — prove MPC reprocessing dedup fires on LIVE MPC data.

Run-book: `runbooks/33-mpc-dedup-live.md`. Discovery-only: this script makes a
few STAC API calls and downloads **zero bytes of imagery**.

Self-contained by design (a prior heredoc+`$OUT` version silently wrote nothing
when the env var didn't survive into a fresh shell):
  - no env vars, no arguments — paths derive from this file's location;
  - **everything** is inside try/except, so `_result.json` is written even if
    the imports or the ROI read blow up. A traceback with no `_result.json`
    breaks the spec-24 D2 contract ("paste the result file, not the logs").

Usage, from the `fsd/` package root:
    .venv/bin/python runbooks/scripts/33_probe_dedup.py
"""

import json
import os
import pathlib
import sys
import traceback

# fsd/runbooks/scripts/33_probe_dedup.py -> parents[2] == fsd/
FSD_ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = FSD_ROOT / "tests" / "outputs" / "spec33_dedup"
ROI_PATH = FSD_ROOT.parent / "shapefiles" / "s2grid=476da24.geojson"

# The exact acquisition runbook 32 found duplicated (spec 33 Motivation).
START, END = "2022-03-01", "2022-03-02"
WINNER = "S2B_MSIL2A_20220301T100029_R122_T33UWP_20240604T180322"  # 2024 reprocessing
LOSER = "S2B_MSIL2A_20220301T100029_R122_T33UWP_20220303T182540"  # original

result = {
    "step": "spec33-live-dedup",
    "status": "ok",
    "pass": False,
    "metrics": {},
    "expected": {},
    "error": None,
}

try:
    import re

    import geopandas as gpd

    from fsd.sources import mpc

    # Guard: prove the spec-33 code is what's loaded (not a pre-fix mpc.py).
    if not hasattr(mpc, "_dedupe_reprocessed_items"):
        raise RuntimeError(
            f"WRONG CODE: {mpc.__file__} has no _dedupe_reprocessed_items — "
            "is spec 33 actually merged into the src/ this venv points at?"
        )
    if not ROI_PATH.exists():
        raise FileNotFoundError(f"ROI not found: {ROI_PATH}")

    roi = gpd.read_file(ROI_PATH)

    # --- A: RAW discovery (dedup bypassed) — does the duplicate still exist upstream? ---
    raw = mpc._search_items(roi, START, END, max_cloudcover=None)
    groups = {}
    for it in raw:
        key = (str(it.datetime), mpc._mgrs_tile_from_item(it))
        groups.setdefault(key, []).append(it)
    dup_groups = {k: v for k, v in groups.items() if len(v) > 1}
    gen = {it.id: it.properties.get("s2:generation_time") for it in raw}

    # Format check (Opus review finding F3): the tie-break compares these as
    # STRINGS, which is only safe if every live value shares one format.
    shapes = sorted({re.sub(r"\d", "N", v) for v in gen.values() if v is not None})

    # --- B: through query_catalog (dedup ON) ---
    cat = mpc.query_catalog(roi, START, END)
    cat_ids = sorted(cat["id"].tolist())

    # --- C: independent expectation — recompute the winner ourselves ---
    expected_ids = sorted(
        (
            g[0]
            if len(g) == 1
            else max(g, key=lambda i: i.properties["s2:generation_time"])
        ).id
        for g in groups.values()
    )

    result["metrics"] = {
        "mpc_module_loaded_from": mpc.__file__,
        "raw_item_count": len(raw),
        "distinct_acquisition_groups": len(groups),
        "duplicate_groups_upstream": len(dup_groups),
        "duplicate_group_ids": {
            str(k): sorted(i.id for i in v) for k, v in dup_groups.items()
        },
        "generation_times": gen,
        "generation_time_format_shapes": shapes,
        "catalog_row_count": len(cat),
        "catalog_ids": cat_ids,
        "independently_expected_ids": expected_ids,
        "known_winner_present": WINNER in cat_ids,
        "known_loser_present": LOSER in cat_ids,
    }
    result["expected"] = {
        "catalog_row_count == distinct_acquisition_groups": True,
        "catalog_ids == independently_expected_ids": True,
        "known_loser_present": False,
        "generation_time_format_shapes": "exactly 1 shape",
    }

    dedup_correct = (len(cat) == len(groups)) and (cat_ids == expected_ids)
    uniform_format = len(shapes) <= 1

    if not dup_groups:
        # MPC has cleaned up its duplicates (discussion #275: the sen2cor bug was
        # fixed). Not a failure of the fix — but this run then proves nothing
        # about dedup firing on live data.
        result["status"] = "inconclusive"
        result["pass"] = False
        result["error"] = (
            "No duplicate group upstream anymore — MPC appears to have cleaned up "
            "this pair. Dedup could not be exercised on live data; the synthetic "
            "pytest remains the guarantee. NOT a code failure."
        )
    else:
        result["pass"] = bool(
            dedup_correct and uniform_format and LOSER not in cat_ids
        )
        if not result["pass"]:
            result["status"] = "fail"
            result["error"] = (
                f"dedup_correct={dedup_correct} uniform_format={uniform_format} "
                f"loser_present={LOSER in cat_ids}"
            )
except Exception:
    result["status"] = "fail"
    result["pass"] = False
    result["error"] = traceback.format_exc()[-1500:]

# Always write the result file — even on a hard failure above. This is the
# spec-24 D2 contract: the user pastes _result.json, never the logs.
try:
    os.makedirs(OUT, exist_ok=True)
    with open(OUT / "_result.json", "w") as f:
        json.dump(result, f, indent=2, default=str)
    print(json.dumps(result, indent=2, default=str)[:3000])
    print(f"\n--- wrote {OUT / '_result.json'} ---")
except Exception:
    print("FATAL: could not write _result.json:\n" + traceback.format_exc())
    print("\nPaste THIS output instead:\n" + json.dumps(result, indent=2, default=str)[:3000])
    sys.exit(2)

sys.exit(0 if result["pass"] else 1)
