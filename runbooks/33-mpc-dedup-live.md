# Run-book: spec 33 — MPC reprocessing dedup, proven on live MPC data

> Spec 24 template. A run-book is what Claude hands the user instead of running a
> pipeline/long/networked script itself. The user runs the commands and pastes back the
> `_result.json`; Claude diffs it against the success criteria below.

> **Why this exists even though spec 33 says "no runbook needed."** The spec is right that the
> logic is fully covered by synthetic pytest (8 tests, all verified non-vacuous by a mutation test
> at Opus review). What pytest *cannot* prove is the one thing this fix rests on: that
> **`s2:generation_time` is really populated on the live MPC items** for the exact duplicate pair
> that started this, and that `query_catalog` really collapses it **in the real world** — the fake
> items in `tests/test_mpc.py` have that property because *we put it there*. This run-book closes
> that gap. It is **discovery-only: zero bytes of imagery are downloaded** (~kilobytes of STAC
> JSON, a few seconds) — unlike runbook 32's ~320 MB.

## Handoff checklist (before starting a fresh session)
- [x] Claude has flushed durable state to `fsd/PROGRESS.md`.
- [ ] Fresh session started; model/effort set for the verifying session (Opus/high to diff the
      pasted `_result.json` against this doc).

## Purpose
Prove on **live MPC traffic** that spec 33's dedup fires on the real duplicate acquisition found
by runbook 32 (`20220301T100029` / `T33UWP`, served twice: original `20220303T182540` +
reprocessing `20240604T180322`), that the winner is the later processing, and that the loser's
bytes are never queued. Also empirically checks the one soft finding from the Opus review: that
live `s2:generation_time` values share a **single uniform RFC-3339 format** (the tie-break compares
them as strings).

## Prerequisites
- venv: `fsd/.venv` with `[dev,mpc]` extras (already installed if you ran runbook 32).
- creds: **none** — MPC discovery is anonymous.
- free disk: **~0**. Nothing is downloaded. No `download()` call is made anywhere in this run-book.
- network: a real connection, but **hotspot-trivial** (a few STAC API calls, kilobytes).
- ROI: `../shapefiles/s2grid=476da24.geojson` (the single-MGRS-tile Austria ROI covering T33UWP —
  the same ROI runbook 32 used when it surfaced the duplicate).

ℹ️ **The code under test is now on `main`** (spec 33's implementation was merged out of the
worktree `spec33-docs-update` at the Opus review, 2026-07-16). `fsd/.venv`'s editable install
points at `main`'s `src/`, so this run-book needs **no `PYTHONPATH` juggling** — just the normal
venv. **Step 0 still exists to make a wrong-code run impossible** — do not skip it.

## Setup
```bash
cd /Users/nikhilsrajan/NASA-Harvest/project/fetch_satdata_claude/fsd
export OUT="$PWD/tests/outputs/spec33_dedup"   # gitignored
mkdir -p "$OUT"
```

## Steps

### Step 0 — prove the spec-33 dedup code is what's loaded
```bash
.venv/bin/python -c "
import fsd.sources.mpc as m
print('loaded from:', m.__file__)
print('has _dedupe_reprocessed_items:', hasattr(m, '_dedupe_reprocessed_items'))
assert hasattr(m, '_dedupe_reprocessed_items'), \
    'WRONG CODE: dedup absent — is spec 33 actually merged to main?'
print('OK: spec-33 code loaded')
"
```
- **Expect:** `loaded from: .../fsd/src/fsd/sources/mpc.py`, `has ...: True`, `OK`.
- **PASS if:** it prints `OK` and does not assert. **If it asserts**, the merge didn't land — stop;
  every later step is meaningless otherwise.

### Step 1 — write the probe script
```bash
cat > "$OUT/probe.py" <<'PY'
import json, os
import geopandas as gpd
from fsd.sources import mpc

OUT = os.environ["OUT"]
ROI_PATH = "../shapefiles/s2grid=476da24.geojson"

# The exact acquisition runbook 32 found duplicated (spec 33 Motivation).
START, END = "2022-03-01", "2022-03-02"
WINNER = "S2B_MSIL2A_20220301T100029_R122_T33UWP_20240604T180322"  # 2024 reprocessing
LOSER  = "S2B_MSIL2A_20220301T100029_R122_T33UWP_20220303T182540"  # original

roi = gpd.read_file(ROI_PATH)
result = {"step": "spec33-live-dedup", "status": "ok", "pass": False,
          "metrics": {}, "expected": {}, "error": None}

try:
    # --- A: RAW discovery (dedup bypassed) — does the duplicate still exist upstream? ---
    raw = mpc._search_items(roi, START, END, max_cloudcover=None)
    groups = {}
    for it in raw:
        key = (str(it.datetime), mpc._mgrs_tile_from_item(it))
        groups.setdefault(key, []).append(it)
    dup_groups = {k: v for k, v in groups.items() if len(v) > 1}
    gen = {it.id: it.properties.get("s2:generation_time") for it in raw}

    # Format check (Opus review soft finding): the tie-break compares these as STRINGS,
    # which is only safe if every live value shares one format. Shape = digits masked.
    import re
    shapes = sorted({re.sub(r"\d", "N", v) for v in gen.values() if v is not None})

    # --- B: through query_catalog (dedup ON) ---
    cat = mpc.query_catalog(roi, START, END)
    cat_ids = sorted(cat["id"].tolist())

    # --- C: independent expectation — recompute the winner ourselves, from the raw items ---
    expected_ids = sorted(
        (g[0] if len(g) == 1 else max(g, key=lambda i: i.properties["s2:generation_time"])).id
        for g in groups.values()
    )

    result["metrics"] = {
        "raw_item_count": len(raw),
        "distinct_acquisition_groups": len(groups),
        "duplicate_groups_upstream": len(dup_groups),
        "duplicate_group_ids": {str(k): sorted(i.id for i in v) for k, v in dup_groups.items()},
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
        # MPC has cleaned up its duplicates (discussion #275 says the sen2cor bug was fixed).
        # Not a failure of the fix — but this run then proves nothing about dedup firing.
        result["status"] = "inconclusive"
        result["pass"] = False
        result["error"] = ("No duplicate group upstream anymore — MPC appears to have cleaned up "
                           "this pair. Dedup could not be exercised on live data; the synthetic "
                           "pytest remains the guarantee. NOT a code failure.")
    else:
        result["pass"] = bool(dedup_correct and uniform_format and LOSER not in cat_ids)
        if not result["pass"]:
            result["status"] = "fail"
            result["error"] = (f"dedup_correct={dedup_correct} uniform_format={uniform_format} "
                               f"loser_present={LOSER in cat_ids}")
except Exception as e:
    import traceback
    result["status"] = "fail"
    result["error"] = traceback.format_exc()[-1500:]

with open(os.path.join(OUT, "_result.json"), "w") as f:
    json.dump(result, f, indent=2, default=str)
print(json.dumps(result, indent=2, default=str)[:3000])
PY
```
- **PASS if:** the file is written (no output expected).

### Step 2 — run the probe (discovery only, no downloads)
```bash
.venv/bin/python "$OUT/probe.py"
```
- **Expect:** a JSON dump ending in `"pass": true`, with `duplicate_groups_upstream: 1`, a
  `duplicate_group_ids` entry listing **both** `..._20220303T182540` and `..._20240604T180322`,
  `catalog_row_count` **one less than** `raw_item_count`, `known_winner_present: true`,
  `known_loser_present: false`, and `generation_time_format_shapes` containing exactly one entry
  (e.g. `["NNNN-NN-NNTNN:NN:NN.NNNNNNZ"]`).
- **PASS if:** `_result.json` has `"pass": true`. Writes `$OUT/_result.json`.
- **If `status` is `inconclusive`:** that is **not** a failure — it means MPC fixed the duplicate
  upstream and the live data can no longer exercise dedup. Paste it back anyway; we record it and
  fall back to the synthetic tests as the guarantee.
- **If it hangs:** Ctrl-C is safe — nothing is written, nothing is downloaded.

### Step 3 — the synthetic suite, for the record
```bash
.venv/bin/python -m pytest -q tests/test_mpc.py
```
- **Expect:** `19 passed`.
- **PASS if:** 19 passed, 0 failed. (Already run at review — this is your independent confirmation.)

## Success criteria (`_result.json`)
```json
{ "step": "spec33-live-dedup", "status": "ok", "pass": true,
  "metrics": { "duplicate_groups_upstream": 1, "catalog_row_count": 0, "known_loser_present": false },
  "expected": { "known_loser_present": false },
  "error": null }
```
The run passes when step 2's `pass` is `true` **and** step 3 is `19 passed`. **Paste
`_result.json` back** (not the logs).

## Stop / observe
- Runtime: seconds. No progress line needed; no ETA to report.
- Abort: Ctrl-C. Nothing is downloaded, so there is nothing to clean up or resume.
