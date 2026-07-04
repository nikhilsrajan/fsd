"""Pure-core tests for the spec-13 COG experiment scripts (prep + compare).

The conversion/harness themselves are manual/benchmark runs against real data
(benchmarks/cog_vs_jp2_report.md); only the file-free logic is unit-tested here.
"""
import importlib.util
import pathlib

import pandas as pd


def _load(name):
    p = pathlib.Path(__file__).parents[1] / "benchmarks" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


prep = _load("prep_cog_dataset")
cmp = _load("compare_cog_jp2")


def test_jp2_to_tif():
    assert prep.jp2_to_tif("B04.jp2") == "B04.tif"
    assert prep.jp2_to_tif("MTD_TL.xml") == "MTD_TL.xml"   # sidecar unchanged


def test_rewrite_paths():
    folder, files = prep.rewrite_paths(
        "/x/satellite_benchmark/sentinel-2-l2a/2018/01/PROD",
        "B04.jp2,B08.jp2,MTD_TL.xml", "satellite_benchmark", "satellite_benchmark_cog",
    )
    assert folder == "/x/satellite_benchmark_cog/sentinel-2-l2a/2018/01/PROD"
    assert files == "B04.tif,B08.tif,MTD_TL.xml"


def test_first_n_months():
    df = pd.DataFrame({"timestamp": pd.to_datetime(
        ["2018-01-05", "2018-02-10", "2018-06-01"], utc=True)})
    sub, first, cutoff = prep.first_n_months(df, 4)
    assert len(sub) == 2                       # Jan + Feb kept, June dropped
    assert first == pd.Timestamp("2018-01-05", tz="UTC")
    assert cutoff == pd.Timestamp("2018-05-05", tz="UTC")


def test_rewrite_catalog():
    df = pd.DataFrame({
        "id": ["p1"],
        "local_folderpath": ["/x/satellite_benchmark/s/PROD"],
        "files": ["B04.jp2,MTD_TL.xml"],
        "timestamp": pd.to_datetime(["2018-01-05"], utc=True),
    })
    out = prep.rewrite_catalog(df, "satellite_benchmark", "satellite_benchmark_cog")
    assert out["local_folderpath"].iloc[0] == "/x/satellite_benchmark_cog/s/PROD"
    assert out["files"].iloc[0] == "B04.tif,MTD_TL.xml"
    assert df["files"].iloc[0] == "B04.jp2,MTD_TL.xml"   # original untouched


def test_summarize_storage():
    by_band = {"B04": {"jp2": 100, "cog": 120, "cog_ovr": 160},
               "B08": {"jp2": 100, "cog": 130, "cog_ovr": 170}}
    s = prep.summarize_storage(by_band)
    assert s["total_jp2"] == 200 and s["total_cog"] == 250 and s["total_cog_ovr"] == 330
    assert s["cog_ratio"] == 1.25
    assert s["overview_delta_pct"] == 32.0


def test_compare_time():
    jp2 = [{"cores": 1, "total_seconds": 100.0, "phase_sum": {"load_images": 60.0},
            "mean_load_per_grid": 6.0}]
    cog = [{"cores": 1, "total_seconds": 50.0, "phase_sum": {"load_images": 25.0},
            "mean_load_per_grid": 2.5}]
    rows = cmp.compare_time(jp2, cog)
    assert len(rows) == 1
    r = rows[0]
    assert r["cores"] == 1
    assert r["wall_speedup"] == 2.0        # 100/50
    assert r["load_speedup"] == 2.4        # 60/25
    assert r["jp2_mean_load"] == 6.0 and r["cog_mean_load"] == 2.5
