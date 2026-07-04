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


# --- Part 2: read-contention analysis (spec 12) ------------------------------

def _reads():
    # g1 & g2 read the SAME file F1 (same-file); g3 reads F2 (same tile, diff file)
    # overlapping both; g4 is isolated in time (no conflict).
    return [
        {"id": "g1", "filepath": "F1", "mgrs_tile": "T1", "band": "B08",
         "start": 0.0, "end": 10.0, "duration": 10.0},
        {"id": "g2", "filepath": "F1", "mgrs_tile": "T1", "band": "B08",
         "start": 5.0, "end": 15.0, "duration": 10.0},
        {"id": "g3", "filepath": "F2", "mgrs_tile": "T1", "band": "B04",
         "start": 6.0, "end": 8.0, "duration": 2.0},
        {"id": "g4", "filepath": "F9", "mgrs_tile": "T9", "band": "B08",
         "start": 100.0, "end": 101.0, "duration": 1.0},
    ]


def test_conflict_stats_classifies_pairs():
    c = dts.conflict_stats(_reads())
    assert c["n_reads"] == 4
    assert c["n_conflict_pairs"] == 3          # g1-g2, g1-g3, g2-g3
    assert c["same_file_pairs"] == 1           # g1-g2 (both F1)
    assert c["same_tile_diff_file_pairs"] == 2  # g1-g3, g2-g3 (T1, F1 vs F2)
    assert c["different_tile_pairs"] == 0
    assert c["max_concurrency"] == 3           # g1,g2,g3 all in flight at t≈7
    assert c["sum_read_seconds"] == 23.0


def test_conflict_stats_no_overlap():
    reads = [
        {"id": "a", "filepath": "X", "mgrs_tile": "T1", "band": "B08",
         "start": 0.0, "end": 1.0, "duration": 1.0},
        {"id": "b", "filepath": "Y", "mgrs_tile": "T2", "band": "B08",
         "start": 5.0, "end": 6.0, "duration": 1.0},
    ]
    c = dts.conflict_stats(reads)
    assert c["n_conflict_pairs"] == 0
    assert c["max_concurrency"] == 1


def test_duration_vs_concurrency_buckets():
    d = dts.duration_vs_concurrency(_reads())
    # g4 alone in flight (concurrency 1); g1,g2,g3 all in flight together at t≈7 (3).
    assert d["all"][1] == {"n": 1, "mean_s": 1.0, "median_s": 1.0}
    assert d["all"][3]["n"] == 3
    assert d["all"][3]["median_s"] == 10.0     # sorted [2,10,10]
    # same-file slice = only g1,g2 (both touched F1), each peaked at concurrency 3
    assert d["same_file"][3] == {"n": 2, "mean_s": 10.0, "median_s": 10.0}


def test_annotate_reads_does_not_mutate_input():
    reads = _reads()
    dts.conflict_stats(reads)
    assert all("overlaps" not in r for r in reads)   # worked on copies
