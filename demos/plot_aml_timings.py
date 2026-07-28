"""Spec 40 D12: the AML timing figures, rendered **off-box, from `timings.json` alone**
-- no cluster, no network, runs anywhere. Kept separate from `e2e_austria_aml.py` (which
writes only the data figures, mirroring the local demo) so the VM needs no chart code and
figures can be restyled without re-running anything.

Three figures, all reading `_extract_runs(timings)` -- one entry per dispatched **run**
(CONTEXT.md), i.e. every `dispatch_timings` block a step recorded (spec 40's discovery
helper in `e2e_austria_aml.py`, since `_aml_submit_and_wait` writes its own telemetry
file rather than returning it, ADR 0021):

  - `aml_job_admission.png`        Figure 1: horizontal strip plot, one dot per job.
  - `aml_where_the_wall_went.png`  Figure 2: horizontal stacked bar, D11's additive split.
  - `aml_job_gantt.png`            Figure 3 (optional): per-job admission + work.

Palette: the dataviz skill's validated categorical order, slots 1-5 (blue, orange, aqua,
yellow, magenta) -- `node scripts/validate_palette.js` (dataviz skill) on all five: every
hard gate PASSes, one WARN (aqua/yellow/magenta below 3:1 on the light surface), which is
why Figure 2 carries a direct label on every segment (the relief the WARN requires) rather
than relying on color alone. Do not substitute by eye.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics

PALETTE = {
    "blue": "#2a78d6", "orange": "#eb6834", "aqua": "#1baf7a",
    "yellow": "#eda100", "magenta": "#e87ba4",
}
INK = "#0b0b0b"
GRID = "#e1e0d9"
SURFACE = "#fcfcfb"

# D11's additive split, fixed slot order (categorical hues are never cycled).
WALL_SEGMENTS = [
    ("driver_prep_seconds", "driver prep", PALETTE["blue"]),
    ("first_admission_seconds", "first admission", PALETTE["orange"]),
    ("execution_window_seconds", "execution window", PALETTE["aqua"]),
    ("teardown_detect_seconds", "teardown detect", PALETTE["yellow"]),
    ("post_collect_seconds", "post collect", PALETTE["magenta"]),
]


def _extract_runs(timings: dict) -> list[dict]:
    """One entry per dispatched run: `{"label": ..., "jobs": {...}, "wall": {...}}`.
    Labeled by its owning step, `[i]`-suffixed when a step dispatched more than one run
    (`3_training_data`'s build fan-out + flatten reduce, D1)."""
    runs = []
    for step in timings.get("steps", []):
        dts = step.get("dispatch_timings") or []
        for i, dt in enumerate(dts):
            label = step.get("step", "?") if len(dts) == 1 else f"{step.get('step', '?')}[{i}]"
            runs.append({"label": label, "jobs": dt.get("jobs") or {}, "wall": dt.get("wall") or {}})
    return runs


def _new_axes(n_rows: int, height_per_row: float = 0.6):
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(9, max(2.0, height_per_row * n_rows + 1)))
    ax.grid(axis="x", color=GRID, linewidth=0.8, zorder=0)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    return fig, ax


def plot_job_admission(timings: dict, out_fp: str) -> str | None:
    """Figure 1: a horizontal STRIP plot, not a histogram -- n is ~16 per run, where
    binning invents structure and hides the tail that IS the scale-out signal (D12)."""
    runs = _extract_runs(timings)
    if not runs:
        return None

    fig, ax = _new_axes(len(runs))
    for row, run in enumerate(runs):
        admissions = [j["job_admission_seconds"] for j in run["jobs"].values()
                     if j.get("job_admission_seconds") is not None]
        if not admissions:
            continue
        ax.scatter(admissions, [row] * len(admissions), color=PALETTE["blue"],
                  s=36, alpha=0.85, zorder=3)
        # statistics.median, not sorted(...)[n//2]: the latter is the UPPER median for
        # even n, and even n is the expected case here (16 jobs per run, D11).
        med = statistics.median(admissions)
        ax.plot([med, med], [row - 0.3, row + 0.3], color=INK, linewidth=2, zorder=4)
    ax.set_yticks(range(len(runs)))
    ax.set_yticklabels([r["label"] for r in runs])
    ax.set_xlabel("job admission (seconds)")
    ax.set_title("AML job admission -- one dot per job, median marked (spec 40 D11)")
    fig.tight_layout()
    fig.savefig(out_fp, dpi=140)
    _close(fig)
    return out_fp


def plot_where_the_wall_went(timings: dict, out_fp: str) -> str | None:
    """Figure 2: a horizontal STACKED bar (part-to-whole -> stacked bar, D12) over D11's
    5-segment additive split. Every segment carries a direct label -- the relief the
    palette's contrast WARN obligates -- plus a legend and a 2px surface gap between
    segments. A negative leg (clock skew exceeding the bound, D11) is clamped to 0 for
    the bar's WIDTH only; the signed value stays in `timings.json`, the table view."""
    runs = _extract_runs(timings)
    if not runs:
        return None

    fig, ax = _new_axes(len(runs))
    max_total = max((sum(max(run["wall"].get(k) or 0.0, 0.0) for k, _, _ in WALL_SEGMENTS)
                    for run in runs), default=0.0)
    for row, run in enumerate(runs):
        wall = run["wall"]
        left = 0.0
        for key, seg_label, color in WALL_SEGMENTS:
            val = wall.get(key)
            if val is None:
                continue
            width = max(val, 0.0)  # D11: never floor the signed value, only the drawn width
            ax.barh(row, width, left=left, height=0.6, color=color,
                   edgecolor=SURFACE, linewidth=2)  # 2px surface gap between segments
            # D12: never draw a label inside a segment too small to hold it -- gate on
            # width relative to the widest bar (a small-run segment vs a big-run segment
            # need the SAME absolute room to fit "label\nNNs" without colliding).
            if max_total > 0 and width / max_total >= 0.06:
                ax.text(left + width / 2, row, f"{seg_label}\n{val:.0f}s", ha="center",
                       va="center", fontsize=7, color=INK)
            left += width
    ax.set_yticks(range(len(runs)))
    ax.set_yticklabels([r["label"] for r in runs])
    ax.set_xlabel("seconds")
    ax.set_title("Where the AML run wall went (spec 40 D11 additive split)")
    handles = [_patch(c) for _, _, c in WALL_SEGMENTS]
    ax.legend(handles, [lbl for _, lbl, _ in WALL_SEGMENTS],
             bbox_to_anchor=(1.02, 1), loc="upper left", fontsize=8)
    fig.tight_layout()
    fig.savefig(out_fp, dpi=140)
    _close(fig)
    return out_fp


def plot_job_gantt(timings: dict, out_fp: str, *, max_rows: int = 80) -> str | None:
    """Figure 3 (optional, D12): one row per job, admission then work, two shades of one
    hue -- makes "38% of node-time idle" (TODO #60) visible. Ships only if it reads
    cleanly (<= `max_rows`); returns `None` above that (drop it, per D12) or with no data."""
    runs = _extract_runs(timings)
    rows = []
    for run in runs:
        for k in sorted(run["jobs"], key=str):
            j = run["jobs"][k]
            admission, work = j.get("job_admission_seconds"), j.get("work_seconds")
            if admission is None or work is None:
                continue
            rows.append((f"{run['label']}/{k}", admission, work))
    if not rows or len(rows) > max_rows:
        return None

    fig, ax = _new_axes(len(rows), height_per_row=0.22)
    admitted_color, work_color = "#86b6ef", PALETTE["blue"]
    for row, (label, admission, work) in enumerate(rows):
        admission = max(admission, 0.0)
        ax.barh(row, admission, color=admitted_color, height=0.6)          # queued/admitted
        ax.barh(row, work, left=admission, color=work_color, height=0.6)   # working
    ax.set_yticks(range(len(rows)))
    ax.set_yticklabels([r[0] for r in rows], fontsize=6)
    ax.set_xlabel("seconds")
    ax.set_title("Per-job admission + work (spec 40 D12 Figure 3, optional)")
    ax.legend([_patch(admitted_color), _patch(work_color)], ["admission", "work"],
             bbox_to_anchor=(1.02, 1), loc="upper left", fontsize=8)
    fig.tight_layout()
    fig.savefig(out_fp, dpi=140)
    _close(fig)
    return out_fp


def _patch(color):
    import matplotlib.patches as mpatches

    return mpatches.Rectangle((0, 0), 1, 1, color=color)


def _close(fig):
    import matplotlib.pyplot as plt

    plt.close(fig)


def render_all(timings: dict, outdir: str) -> dict:
    os.makedirs(outdir, exist_ok=True)
    written = {}
    for fn, name in (
        (plot_job_admission, "aml_job_admission.png"),
        (plot_where_the_wall_went, "aml_where_the_wall_went.png"),
        (plot_job_gantt, "aml_job_gantt.png"),
    ):
        written[name] = fn(timings, os.path.join(outdir, name))
    return written


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Render spec-40 AML timing figures from a timings.json (D12).")
    ap.add_argument("timings_json", help="path to a demo run's timings.json (D9: self-contained)")
    ap.add_argument("--outdir", default=os.path.join(os.path.dirname(__file__), "figures"))
    args = ap.parse_args(argv)

    with open(args.timings_json) as f:
        timings = json.load(f)

    written = render_all(timings, args.outdir)
    for name, out_fp in written.items():
        print(f"{'wrote' if out_fp else 'skipped (no data)'}: {name}")


if __name__ == "__main__":
    main()
