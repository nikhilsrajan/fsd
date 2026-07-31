"""Tests for spec 40 D12 (deliverable 4): both timing figures render from a synthetic
`timings.json` alone -- no cluster, no network. Covers the degenerate cases spec 40 §6
calls out: a run with one job, and a run with zero spread (every job identical).
"""

from __future__ import annotations

import importlib
import os
import sys

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_DEMOS_DIR = os.path.join(os.path.dirname(_HERE), "demos")
sys.path.insert(0, _DEMOS_DIR)
plot_aml_timings = importlib.import_module("plot_aml_timings")


def _job(admission, work=10.0):
    return {"job_admission_seconds": admission, "work_seconds": work}


def _wall(**overrides):
    wall = {"driver_prep_seconds": 2.0, "first_admission_seconds": 8.0,
            "execution_window_seconds": 17.0, "teardown_detect_seconds": 3.0,
            "post_collect_seconds": 5.0}
    wall.update(overrides)
    return wall


def _synthetic_timings() -> dict:
    """Two runs: `2_download` has ONE job (degenerate); `5_run_inference` has several
    jobs all with the SAME admission (zero spread, degenerate)."""
    return {
        "run_id": "synthetic", "total_seconds": 100.0,
        "steps": [
            {"step": "2_download", "status": "ok", "seconds": 35.0,
             "dispatch_timings": [{"run_id": "r-dl", "jobs": {"0": _job(9.0)},
                                   "wall": _wall()}]},
            {"step": "5_run_inference", "status": "ok", "seconds": 60.0,
             "dispatch_timings": [{"run_id": "r-inf", "jobs": {
                 str(i): _job(12.0) for i in range(6)  # zero spread: identical admission
             }, "wall": _wall(driver_prep_seconds=1.0)}]},
        ],
    }


def test_extract_runs_labels_single_and_multi_dispatch_steps():
    timings = _synthetic_timings()
    timings["steps"].append({
        "step": "3_training_data", "status": "ok", "seconds": 40.0,
        "dispatch_timings": [
            {"run_id": "r-build", "jobs": {"0": _job(5.0)}, "wall": _wall()},
            {"run_id": "r-flatten", "jobs": {"0": _job(3.0)}, "wall": _wall()},
        ],
    })
    runs = plot_aml_timings._extract_runs(timings)
    labels = [r["label"] for r in runs]
    assert labels == ["2_download", "5_run_inference", "3_training_data[0]", "3_training_data[1]"]


def test_plot_job_admission_renders_one_job_and_zero_spread_runs(tmp_path):
    timings = _synthetic_timings()
    out_fp = str(tmp_path / "aml_job_admission.png")
    result = plot_aml_timings.plot_job_admission(timings, out_fp)
    assert result == out_fp
    assert os.path.exists(out_fp) and os.path.getsize(out_fp) > 0


def test_plot_where_the_wall_went_renders(tmp_path):
    timings = _synthetic_timings()
    out_fp = str(tmp_path / "aml_where_the_wall_went.png")
    result = plot_aml_timings.plot_where_the_wall_went(timings, out_fp)
    assert result == out_fp
    assert os.path.exists(out_fp) and os.path.getsize(out_fp) > 0


def test_plot_where_the_wall_went_clamps_negative_leg_without_raising(tmp_path):
    """spec 40 D11: a leg can go negative (skew exceeded the bound) -- the bar must not
    crash trying to draw a negative width."""
    timings = _synthetic_timings()
    timings["steps"][0]["dispatch_timings"][0]["wall"]["first_admission_seconds"] = -3.0
    out_fp = str(tmp_path / "neg.png")
    result = plot_aml_timings.plot_where_the_wall_went(timings, out_fp)
    assert result == out_fp
    assert os.path.exists(out_fp)


def test_plot_job_gantt_renders_and_skips_over_max_rows(tmp_path):
    timings = _synthetic_timings()
    out_fp = str(tmp_path / "gantt.png")
    result = plot_aml_timings.plot_job_gantt(timings, out_fp)
    assert result == out_fp
    assert os.path.exists(out_fp)

    # Over the row cap: dropped (D12), not a giant unreadable figure.
    big = {"steps": [{"step": "huge", "dispatch_timings": [
        {"jobs": {str(i): _job(1.0) for i in range(100)}, "wall": _wall()}
    ]}]}
    assert plot_aml_timings.plot_job_gantt(big, str(tmp_path / "huge.png"), max_rows=80) is None


def test_plots_return_none_with_no_dispatch_data(tmp_path):
    empty = {"steps": [{"step": "0_preflight", "status": "ok", "seconds": 1.0}]}
    assert plot_aml_timings.plot_job_admission(empty, str(tmp_path / "a.png")) is None
    assert plot_aml_timings.plot_where_the_wall_went(empty, str(tmp_path / "b.png")) is None
    assert plot_aml_timings.plot_job_gantt(empty, str(tmp_path / "c.png")) is None


def test_render_all_writes_all_three_figures(tmp_path):
    timings = _synthetic_timings()
    written = plot_aml_timings.render_all(timings, str(tmp_path))
    assert set(written) == {"aml_job_admission.png", "aml_where_the_wall_went.png",
                            "aml_job_gantt.png"}
    assert all(written.values())
    for name in written:
        assert os.path.exists(tmp_path / name)


@pytest.fixture(autouse=True, scope="module")
def _matplotlib_agg_backend():
    """Headless-safe: force the non-interactive backend before any test in this module
    touches pyplot (mirrors how CI runs `demos/e2e_austria.py`'s own plotting)."""
    import matplotlib
    matplotlib.use("Agg")


# --- the gantt's two very different Nones (2026-07-29) -----------------------

def _timings_with_n_jobs(n):
    return {"run_id": "r", "steps": [{"step": "5_run_inference", "dispatch_timings": [
        {"run_id": "x", "wall": _wall(),
         "jobs": {str(i): _job(30.0 + i) for i in range(n)}}]}]}


def test_gantt_renders_a_full_32_node_run():
    """The real cluster (max 32 nodes) makes a demo run 97 jobs -- D12's implied ~49 came
    from the spec's 16-per-run assumption, and the old max_rows=80 silently dropped the
    figure on every real run."""
    import os
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        out = os.path.join(d, "g.png")
        assert plot_aml_timings.plot_job_gantt(_timings_with_n_jobs(97), out) == out
        assert os.path.getsize(out) > 0


def test_gantt_skip_reason_distinguishes_too_many_rows_from_no_data():
    """`main` printed "skipped (no data)" for both, which sends a reader hunting for
    missing telemetry when the real answer is a row cap."""
    reason = plot_aml_timings.gantt_skip_reason(_timings_with_n_jobs(500))
    assert "500" in reason and "max_rows" in reason

    empty = {"run_id": "r", "steps": [{"step": "s", "dispatch_timings": [
        {"run_id": "x", "wall": _wall(), "jobs": {
            "0": {"job_admission_seconds": None, "work_seconds": None}}}]}]}
    reason = plot_aml_timings.gantt_skip_reason(empty)
    assert "in-job stamps" in reason and "predates spec 40" in reason


def test_gantt_skip_reason_is_none_when_the_figure_renders():
    assert plot_aml_timings.gantt_skip_reason(_timings_with_n_jobs(40)) is None
