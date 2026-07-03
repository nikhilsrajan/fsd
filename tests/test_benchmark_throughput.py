"""Tests for the pure core of the throughput-sweep harness (spec 11 · Part 1).

Only the file-free logic is unit-tested here; the actual sweep is a manual/benchmark
run against real satellite_benchmark data (benchmarks/datacube_throughput_report.md).
"""
import importlib.util
import pathlib

_MOD = pathlib.Path(__file__).parents[1] / "benchmarks" / "datacube_throughput_sweep.py"
_spec = importlib.util.spec_from_file_location("dts_bench", _MOD)
dts = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dts)


def test_tile_of_extracts_mgrs():
    assert dts.tile_of("S2A_MSIL2A_20180101T073331_N0500_R049_T36NXF_20230101T000000") \
        == "36NXF"
    assert dts.tile_of("S2B_MSIL2A_20180705T075609_N0500_R035_T37NBA_x") == "37NBA"


def test_overlap_stats_counts_sharing():
    # g1,g2 share tile A; g3 straddles C,D alone; B shared by g1,g2 too.
    grid_to_tiles = {
        "g1": {"A", "B"},
        "g2": {"A", "B"},
        "g3": {"C", "D"},
    }
    s = dts.overlap_stats(grid_to_tiles)
    assert s["n_grids"] == 3
    assert s["n_tiles"] == 4                       # A,B,C,D
    assert s["grids_per_tile"] == {"A": 2, "B": 2, "C": 1, "D": 1}
    assert s["n_shared_tiles"] == 2                # A,B
    assert s["max_grids_per_tile"] == 2
    assert s["tiles_per_grid_dist"] == {2: 3}      # every grid touches 2 tiles
    assert s["hottest_tiles"] == {"A": 2, "B": 2}


def test_overlap_stats_no_sharing():
    s = dts.overlap_stats({"g1": {"A"}, "g2": {"B"}})
    assert s["n_shared_tiles"] == 0
    assert s["max_grids_per_tile"] == 1
    assert s["tiles_per_grid_dist"] == {1: 2}
    assert s["hottest_tiles"] == {}
