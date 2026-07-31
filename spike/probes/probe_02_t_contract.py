"""Probe 02 — does rslearn's `period_duration` reproduce fsd's calendar-`T` contract?

Spike question Q2b (`../RSLEARN_READ_2026-07-31.md` §4). This is the **decisive cheap probe**:
it needs rslearn installed but downloads **nothing** -- every item fed to the matcher is
synthetic. It can veto the expensive half of the spike.

## What is under test

fsd's contract (`src/fsd/api.py:69-80`) is that

    T = ceil((enddate - startdate) / mosaic_days)

is a **pure function of the caller's window** -- computable with zero downloads. Two fsd
properties depend on it: preflight (`T == adapter.n_timestamps` asserted *before* spending
money on a fan-out) and cross-cell flatten (all cubes share one `timestamps` axis).

rslearn's analogue is `QueryConfig(space_mode=MOSAIC, period_duration=..., max_matches=...)`,
implemented at `rslearn/data_sources/utils.py:434-485`. Reading that loop predicts **three**
divergences, and this probe tests each in isolation:

  A. **empty periods are dropped** (`utils.py:464`, `if period_groups:`) -> T is data-dependent
  B. **floor, not ceil** -- the guard `period_end - period_duration >= time_range[0]`
     (`utils.py:447`) drops a trailing partial period
  C. **end-anchored, not start-anchored** -- periods walk backwards from `time_range[1]`
     (`utils.py:446,455`), so window boundaries differ in phase from fsd's

The headline case mirrors the committed tutorial fixture (`tests/data/tutorial/`):
2018-04-01 -> 2018-09-29, `mosaic_days=20`. fsd gives `T = ceil(181/20) = 10`. If rslearn
returns 10 too, the read is wrong and section 4.2 must be re-derived.

Usage (see `../RUNBOOK-rslearn-spike.md` Step 2):

    python spike/probes/probe_02_t_contract.py --out tests/outputs/rslearn_spike
"""

from __future__ import annotations

import argparse
import json
import math
import warnings
from datetime import UTC, datetime, timedelta
from pathlib import Path

import shapely
from rasterio.crs import CRS
from rslearn.config import QueryConfig, SpaceMode
from rslearn.data_sources.data_source import Item
from rslearn.data_sources.utils import match_candidate_items_to_window
from rslearn.utils.geometry import Projection, STGeometry

# The tutorial fixture's window: T33UWP, grid cell 4772924, 2018-04-01 .. 2018-09-28.
# fsd's tutorial states the window as [2018-04-01, 2018-09-29) -- 181 days -- so that the
# final acquisition (09-28) falls inside it. Keep these two in lockstep with
# `tests/data/tutorial/README.md`.
WINDOW_START = datetime(2018, 4, 1, tzinfo=UTC)
WINDOW_END = datetime(2018, 9, 29, tzinfo=UTC)
MOSAIC_DAYS = 20

# A UTM-33N projection at 10 m, matching the fixture's B08 reference grid.
PROJECTION = Projection(CRS.from_epsg(32633), 10, -10)
# A small box in projection units. Its exact extent does not matter: every synthetic item
# is given the SAME shape, so spatial matching always succeeds and only the temporal
# behaviour is under test.
BOX = shapely.box(0, 0, 1000, 1000)


def fsd_n_timestamps(start: datetime, end: datetime, mosaic_days: int) -> int:
    """fsd's `T`, reimplemented so the probe needs no fsd import.

    Mirrors `src/fsd/api.py:69-80` exactly: ceil of the span in days over mosaic_days.
    The spike venv (`.venv-rslearn`) deliberately does not have fsd installed -- the
    charter keeps the two environments apart -- so this is duplicated on purpose.
    """
    total_days = (end - start) / timedelta(days=1)
    return math.ceil(total_days / mosaic_days)


def make_items(
    start: datetime, end: datetime, every_days: int, skip_windows: tuple[int, ...] = ()
) -> list[Item]:
    """Synthetic scenes every `every_days`, optionally punching holes.

    Args:
        start: window start.
        end: window end (exclusive).
        every_days: cadence, e.g. 10 for a ~Sentinel-2 revisit over one tile.
        skip_windows: indexes of `MOSAIC_DAYS`-long windows (counted from `start`) to
            leave with no scenes at all, to test divergence A.
    """
    items: list[Item] = []
    t = start
    i = 0
    while t < end:
        window_idx = int((t - start) / timedelta(days=MOSAIC_DAYS))
        if window_idx not in skip_windows:
            # An item's time_range must be a genuine interval; a zero-width range is not
            # reliably "within" a period. One hour is enough and keeps it inside its window.
            items.append(
                Item(f"scene_{i:03d}_{t:%Y%m%d}", STGeometry(PROJECTION, BOX, (t, t + timedelta(hours=1))))
            )
        t += timedelta(days=every_days)
        i += 1
    return items


def run_case(
    name: str,
    start: datetime,
    end: datetime,
    mosaic_days: int,
    items: list[Item],
    reverse_time_order: bool = False,
) -> dict:
    """Match `items` to one window and report how many groups came back."""
    window = STGeometry(PROJECTION, BOX, (start, end))
    query = QueryConfig(
        space_mode=SpaceMode.MOSAIC,
        period_duration=timedelta(days=mosaic_days),
        max_matches=fsd_n_timestamps(start, end, mosaic_days),
        per_period_mosaic_reverse_time_order=reverse_time_order,
    )

    # utils.py:474-483 emits a FutureWarning whenever reverse order is left on. Capture it
    # rather than letting it scroll past -- whether it fires is itself a finding.
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        groups = match_candidate_items_to_window(window, items, query)
        future_warnings = [str(w.message) for w in caught if issubclass(w.category, FutureWarning)]

    group_ranges = [
        (g.time_range[0].isoformat(), g.time_range[1].isoformat()) if g.time_range else None
        for g in groups
    ]
    chronological = group_ranges == sorted(group_ranges, key=lambda r: r[0] if r else "")

    return {
        "case": name,
        "n_items": len(items),
        "fsd_T": fsd_n_timestamps(start, end, mosaic_days),
        "rslearn_n_groups": len(groups),
        "group_time_ranges": group_ranges,
        "chronological_order": chronological,
        "future_warnings": future_warnings,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", required=True, help="output directory for _result.json")
    args = ap.parse_args()
    outdir = Path(args.out)
    outdir.mkdir(parents=True, exist_ok=True)

    cases = []

    # --- Case 1: the headline. Dense coverage, every period populated. -----------------
    # 181 days / 20 -> fsd T = 10. Divergence B predicts rslearn returns 9 (floor), since
    # 9 * 20 = 180 and the trailing 1 day cannot fit a whole period.
    cases.append(
        run_case(
            "dense_tutorial_window",
            WINDOW_START,
            WINDOW_END,
            MOSAIC_DAYS,
            make_items(WINDOW_START, WINDOW_END, every_days=5),
        )
    )

    # --- Case 2: exact multiple of the period. Isolates B from A. ----------------------
    # 180 days / 20 = 9 exactly, so ceil == floor. If rslearn returns 9 here but 9 in case
    # 1 as well, the difference in case 1 is attributable to the dropped partial period.
    exact_end = WINDOW_START + timedelta(days=180)
    cases.append(
        run_case(
            "exact_multiple_no_partial",
            WINDOW_START,
            exact_end,
            MOSAIC_DAYS,
            make_items(WINDOW_START, exact_end, every_days=5),
        )
    )

    # --- Case 3: a hole. Isolates A. ---------------------------------------------------
    # Same exact-multiple window, but two 20-day windows have no scenes at all (a cloudy
    # or gap-filled stretch is completely normal). fsd still emits 9 timestamps, two of
    # them nodata. rslearn is predicted to return 7.
    cases.append(
        run_case(
            "two_empty_periods",
            WINDOW_START,
            exact_end,
            MOSAIC_DAYS,
            make_items(WINDOW_START, exact_end, every_days=5, skip_windows=(3, 6)),
        )
    )

    # --- Case 4: ordering + the deprecation warning. -----------------------------------
    cases.append(
        run_case(
            "default_reverse_time_order",
            WINDOW_START,
            exact_end,
            MOSAIC_DAYS,
            make_items(WINDOW_START, exact_end, every_days=5),
            reverse_time_order=True,
        )
    )

    by_name = {c["case"]: c for c in cases}
    dense = by_name["dense_tutorial_window"]
    exact = by_name["exact_multiple_no_partial"]
    holes = by_name["two_empty_periods"]
    rev = by_name["default_reverse_time_order"]

    findings = {
        # A: empty periods dropped -> T is data-dependent, so preflight cannot fire early
        # and cubes from different cells cannot be stacked.
        "A_empty_periods_dropped": holes["rslearn_n_groups"] < exact["rslearn_n_groups"],
        # B: trailing partial period dropped -> floor rather than fsd's ceil.
        "B_partial_period_dropped": dense["rslearn_n_groups"] < dense["fsd_T"],
        # C: default ordering is reverse-chronological and warns.
        "C_reverse_order_by_default": (not rev["chronological_order"])
        or bool(rev["future_warnings"]),
        "T_matches_fsd_on_dense_window": dense["rslearn_n_groups"] == dense["fsd_T"],
    }

    # This probe is descriptive: it PASSES when all four cases ran and produced a group
    # count. What it is really reporting is `findings`, which decide whether Plan C needs
    # a re-alignment shim. A "pass" here does NOT mean rslearn matched fsd.
    result = {
        "step": "probe_02_t_contract",
        "status": "ok",
        "pass": all(isinstance(c["rslearn_n_groups"], int) for c in cases),
        "metrics": {"cases": cases, "findings": findings},
        "expected": {
            "dense_tutorial_window": {"fsd_T": 10, "rslearn_n_groups_predicted": 9},
            "two_empty_periods": {"fsd_T": 9, "rslearn_n_groups_predicted": 7},
            "note": (
                "Predictions come from reading rslearn/data_sources/utils.py:434-485 "
                "(RSLEARN_READ_2026-07-31.md section 4.2). If T_matches_fsd_on_dense_window "
                "is true, that read is WRONG and must be re-derived before the spike continues."
            ),
        },
        "error": None,
    }
    (outdir / "_result_probe02.json").write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
