"""Spec 11 · Part 1 — datacube-creation throughput sweep (reusable harness).

Measures how the wall-time to build N datacubes scales with build parallelism
(`cores`), over a fixed set of geometries, and where the time goes per step. Emits a
baseline report + a stats JSON we re-run to track future speedups. No read-path
instrumentation (that is Part 2 / spec 12); this only reads the per-build `timings.json`
sidecar (builder `write_timings`, enabled here via the `FSD_WRITE_TIMINGS` env var) and
the Snakemake `start.txt`/`done.txt` sentinels.

Run:  python -m benchmarks.datacube_throughput_sweep            # full: 100 grids, cores 1..10
      python -m benchmarks.datacube_throughput_sweep --smoke    # 3 grids, cores 1,2

Cache: measure-don't-force (spec 11). Runs warm-as-is; the report notes the caveat.
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import platform
import shutil
import threading
import time

import geopandas as gpd
import pandas as pd

from fsd.storage import fs
from fsd.workflows import create_datacube, runners

ROOT = "/Users/nikhilsrajan/NASA-Harvest/project/fetch_satdata_claude"
CATALOG = f"{ROOT}/satellite_benchmark/sentinel-2-l2a/catalog.parquet"
GRIDS = f"{ROOT}/shapefiles/100_random_grids.geojson"
OUT = f"{ROOT}/fsd/tests/outputs/throughput_sweep"
FIG_DIR = f"{ROOT}/fsd/benchmarks/datacube_throughput_figures"
REPORT = f"{ROOT}/fsd/benchmarks/datacube_throughput_report.md"

BANDS = ["B04", "B08", "B8A", "SCL"]
SCL = [0, 1, 3, 7, 8, 9, 10]
MOSAIC_DAYS = 20
# Short representative window (spec 11): keeps 100 grids x 6 cores feasible.
START = datetime.datetime(2018, 6, 1)
END = datetime.datetime(2018, 7, 10)
ID_COL = "id"

_SENTINELS = ("start.txt", "done.txt")
_WIPE = ("datacube.npy", "metadata.pickle.npy", "timings.json", *_SENTINELS)


# --- static characterization (pure core is unit-tested) ----------------------

def tile_of(product_id: str) -> str:
    """MGRS tile (e.g. '36NXF') from an S2 product id like '..._T36NXF_...'."""
    return product_id.split("_T")[1][:5]


def overlap_stats(grid_to_tiles: dict[str, set[str]]) -> dict:
    """PURE: from {grid_id: {mgrs_tile, ...}} derive shareability metrics.

    - tiles_per_grid: how many MGRS tiles each grid straddles (build heaviness).
    - grids_per_tile: how many grids read each tile (potential shared reads).
    """
    tiles_per_grid = {g: len(t) for g, t in grid_to_tiles.items()}
    grids_per_tile: dict[str, int] = {}
    for tiles in grid_to_tiles.values():
        for t in tiles:
            grids_per_tile[t] = grids_per_tile.get(t, 0) + 1
    shared = {t: n for t, n in grids_per_tile.items() if n > 1}
    dist: dict[int, int] = {}
    for n in tiles_per_grid.values():
        dist[n] = dist.get(n, 0) + 1
    return {
        "n_grids": len(grid_to_tiles),
        "n_tiles": len(grids_per_tile),
        "tiles_per_grid": tiles_per_grid,
        "tiles_per_grid_dist": dict(sorted(dist.items())),
        "grids_per_tile": grids_per_tile,
        "n_shared_tiles": len(shared),
        "max_grids_per_tile": max(grids_per_tile.values(), default=0),
        "hottest_tiles": dict(sorted(shared.items(), key=lambda kv: -kv[1])[:10]),
    }


def characterize(input_df: pd.DataFrame) -> dict:
    """Read each grid's setup catalog.parquet slice -> overlap stats (no raster reads)."""
    grid_to_tiles: dict[str, set[str]] = {}
    for _, row in input_df.iterrows():
        sub = fs.read_parquet(row["catalog_filepath"])
        grid_to_tiles[str(row[ID_COL])] = {tile_of(pid) for pid in sub["id"]}
    return overlap_stats(grid_to_tiles)


# --- sweep -------------------------------------------------------------------

def _wipe_build_outputs(input_df: pd.DataFrame) -> None:
    """Remove artifacts + sentinels so Snakemake actually rebuilds (keeps setup slices)."""
    for _, row in input_df.iterrows():
        for name in _WIPE:
            p = os.path.join(row["export_folderpath"], name)
            if os.path.exists(p):
                os.remove(p)


def _collect(input_df: pd.DataFrame) -> list[dict]:
    """Per-grid records for the last run: wall (done-start) + timings.json phases."""
    recs = []
    for _, row in input_df.iterrows():
        folder = row["export_folderpath"]
        rec: dict = {"id": str(row[ID_COL])}
        try:
            with fs.open(os.path.join(folder, "start.txt")) as f:
                t0 = pd.Timestamp(f.read().decode().strip())
            with fs.open(os.path.join(folder, "done.txt")) as f:
                t1 = pd.Timestamp(f.read().decode().strip())
            rec["wall_seconds"] = (t1 - t0).total_seconds()
        except FileNotFoundError:
            rec["wall_seconds"] = None
        tpath = os.path.join(folder, "timings.json")
        if os.path.exists(tpath):
            with fs.open(tpath) as f:
                rec["timings"] = json.load(f)
        recs.append(rec)
    return recs


def _bar(done: int, n: int, width: int = 24) -> str:
    filled = int(width * done / n) if n else 0
    return "[" + "#" * filled + "-" * (width - filled) + "]"


def _fmt(sec: float) -> str:
    return "?" if sec != sec else (f"{sec/60:.1f}m" if sec >= 90 else f"{sec:.0f}s")


def _progress(folders: list[str], n: int, t0: float, tag: str, stop: list) -> None:
    """Daemon: every ~10s print done/total + elapsed + ETA by counting done.txt."""
    while not stop[0]:
        done = sum(1 for f in folders if os.path.exists(os.path.join(f, "done.txt")))
        el = time.perf_counter() - t0
        eta = (n - done) / (done / el) if done and el else float("nan")
        print(f"[progress] {tag} {_bar(done, n)} {done}/{n} | {_fmt(el)} elapsed | "
              f"ETA ~{_fmt(eta)}", flush=True)
        if done >= n:
            return
        for _ in range(10):          # responsive to stop, tick ~10s
            if stop[0]:
                return
            time.sleep(1)


def run_sweep(input_df: pd.DataFrame, cores_list: list[int], repeats: int) -> list[dict]:
    os.environ["FSD_WRITE_TIMINGS"] = "1"
    folders = input_df["export_folderpath"].tolist()
    n = len(input_df)
    total_runs = len(cores_list) * repeats
    sweep_t0 = time.perf_counter()
    print(f"[sweep] START {total_runs} runs × {n} grids | cores={cores_list} "
          f"repeats={repeats}", flush=True)
    results, run_i = [], 0
    for cores in cores_list:
        for rep in range(repeats):
            run_i += 1
            _wipe_build_outputs(input_df)
            t0 = time.perf_counter()
            stop = [False]
            watcher = threading.Thread(
                target=_progress,
                args=(folders, n, t0, f"run {run_i}/{total_runs} cores={cores}", stop),
                daemon=True,
            )
            watcher.start()
            cp = runners.run_local(str(OUT_CSV), cores=cores, jitter_span=1)
            stop[0] = True
            watcher.join(timeout=2)

            total = round(time.perf_counter() - t0, 2)
            recs = _collect(input_df)
            walls = [r["wall_seconds"] for r in recs if r.get("wall_seconds") is not None]
            built = sum(1 for r in recs if r.get("timings"))
            sweep_eta = (time.perf_counter() - sweep_t0) / run_i * (total_runs - run_i)
            print(f"[sweep] DONE run {run_i}/{total_runs} cores={cores} rep={rep}: "
                  f"total={_fmt(total)} built={built}/{n} rc={cp.returncode} | "
                  f"sweep ETA ~{_fmt(sweep_eta)}", flush=True)
            results.append({"cores": cores, "rep": rep, "total_seconds": total,
                            "returncode": cp.returncode, "n_built": built,
                            "sum_grid_wall": round(sum(walls), 2), "records": recs})
    return results


# --- aggregate ---------------------------------------------------------------

_PHASES = ["missing_check", "load_images", "dst_crs", "reference_profile",
           "resample", "stack", "ops", "save"]


def aggregate(results: list[dict]) -> list[dict]:
    """One row per cores setting (min total over repeats) with phase-sum breakdown."""
    by_cores: dict[int, list[dict]] = {}
    for r in results:
        by_cores.setdefault(r["cores"], []).append(r)
    base = None
    rows = []
    for cores in sorted(by_cores):
        runs = by_cores[cores]
        best = min(runs, key=lambda r: r["total_seconds"])
        recs = best["records"]
        phase_sum = {p: 0.0 for p in _PHASES}
        load_walls = []
        for rec in recs:
            t = rec.get("timings")
            if not t:
                continue
            for p, s in t.get("phase_seconds", {}).items():
                phase_sum[p] = phase_sum.get(p, 0.0) + s
            load_walls.append(t["phase_seconds"].get("load_images", 0.0))
        total = best["total_seconds"]
        base = base if base is not None else total
        rows.append({
            "cores": cores,
            "total_seconds": total,
            "throughput_per_min": round(best["n_built"] / total * 60, 2) if total else 0,
            "speedup": round(base / total, 2) if total else 0,
            "efficiency": round(base / total / cores, 2) if total else 0,
            "n_built": best["n_built"],
            "sum_grid_wall": best["sum_grid_wall"],
            "phase_sum": {p: round(v, 1) for p, v in phase_sum.items()},
            "load_images_frac": (round(phase_sum["load_images"]
                                       / max(sum(phase_sum.values()), 1e-9), 3)),
            "mean_load_per_grid": round(sum(load_walls) / max(len(load_walls), 1), 2),
        })
    return rows


# --- plots + report ----------------------------------------------------------

def make_plots(rows: list[dict], char: dict, base_recs: list[dict]) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    os.makedirs(FIG_DIR, exist_ok=True)
    cores = [r["cores"] for r in rows]

    # 1) throughput + total wall vs cores
    fig, ax1 = plt.subplots(figsize=(8, 5))
    ax1.plot(cores, [r["total_seconds"] for r in rows], "o-", color="#d95f02",
             label="total wall (s)")
    ax1.set_xlabel("cores (parallel builds)")
    ax1.set_ylabel("total wall-time (s)", color="#d95f02")
    ax2 = ax1.twinx()
    ax2.plot(cores, [r["throughput_per_min"] for r in rows], "s--", color="#1b9e77",
             label="throughput")
    ax2.set_ylabel("datacubes / min", color="#1b9e77")
    ax1.set_title("Throughput vs build parallelism")
    ax1.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(f"{FIG_DIR}/throughput_vs_cores.png", dpi=110)
    plt.close(fig)

    # 2) per-phase aggregate stacked bars per cores
    fig, ax = plt.subplots(figsize=(9, 5))
    bottom = [0.0] * len(cores)
    for p in _PHASES:
        vals = [r["phase_sum"].get(p, 0.0) for r in rows]
        if sum(vals) < 0.5:
            continue
        ax.bar([str(c) for c in cores], vals, bottom=bottom, label=p)
        bottom = [b + v for b, v in zip(bottom, vals)]
    ax.set_xlabel("cores")
    ax.set_ylabel("summed per-grid phase seconds")
    ax.set_title("Where the time goes (sum across grids) vs cores")
    ax.legend(fontsize=8, ncol=2)
    fig.tight_layout()
    fig.savefig(f"{FIG_DIR}/phase_breakdown.png", dpi=110)
    plt.close(fig)

    # 3) load_images: total summed + mean per grid vs cores (the contention signal)
    fig, ax1 = plt.subplots(figsize=(8, 5))
    ax1.plot(cores, [r["phase_sum"]["load_images"] for r in rows], "o-", color="#7570b3",
             label="summed load_images (s)")
    ax1.set_xlabel("cores")
    ax1.set_ylabel("summed load_images (s)", color="#7570b3")
    ax2 = ax1.twinx()
    ax2.plot(cores, [r["mean_load_per_grid"] for r in rows], "^--", color="#e7298a",
             label="mean load_images / grid (s)")
    ax2.set_ylabel("mean load_images per grid (s)", color="#e7298a")
    ax1.set_title("load_images cost vs parallelism (contention signal → Part 2)")
    ax1.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(f"{FIG_DIR}/load_images_vs_cores.png", dpi=110)
    plt.close(fig)

    # 4) per-grid wall vs #tiles (baseline cores=1 run)
    tpg = char["tiles_per_grid"]
    xs, ys = [], []
    for rec in base_recs:
        if rec.get("wall_seconds") is not None and rec["id"] in tpg:
            xs.append(tpg[rec["id"]])
            ys.append(rec["wall_seconds"])
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.scatter(xs, ys, alpha=0.5, color="#1b9e77")
    ax.set_xlabel("# MGRS tiles the grid straddles")
    ax.set_ylabel("build wall-time (s), cores=1")
    ax.set_title("Per-grid build cost vs tiles touched")
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(f"{FIG_DIR}/wall_vs_tiles.png", dpi=110)
    plt.close(fig)


def _knee_cores(rows: list[dict], min_gain: float = 0.05) -> int:
    """Smallest `cores` past which the next step cuts total wall by < min_gain (5%)."""
    for i in range(len(rows) - 1):
        prev, nxt = rows[i]["total_seconds"], rows[i + 1]["total_seconds"]
        if prev and (prev - nxt) / prev < min_gain:
            return rows[i]["cores"]
    return rows[-1]["cores"]


def write_report(rows: list[dict], char: dict, meta: dict) -> None:
    best = min(rows, key=lambda r: r["total_seconds"])
    knee = _knee_cores(rows)
    L = []
    L.append("# Datacube throughput benchmark — Part 1 (parallelism sweep)\n")
    L.append(f"_Spec 11 · generated {meta['run_utc']}_\n")
    L.append("**Reusable baseline** — re-run `python -m benchmarks.datacube_throughput_sweep` "
             "after any speedup and diff against `datacube_throughput_stats.json`.\n")
    L.append("## Config\n")
    L.append(f"- machine: `{meta['platform']}`, {meta['cpu_count']} logical CPUs\n"
             f"- grids: `{os.path.basename(GRIDS)}` (n={char['n_grids']} with tiles), "
             f"catalog `satellite_benchmark` ({meta['catalog_tiles']} tile-rows)\n"
             f"- window: {meta['window'][0]} → {meta['window'][1]}, bands {BANDS}, "
             f"mosaic_days={MOSAIC_DAYS}\n"
             f"- cores swept: {meta['cores_list']}, repeats={meta['repeats']}\n")
    L.append("## Grid characterization (static — potential shared reads)\n")
    L.append(f"- MGRS tiles covered: **{char['n_tiles']}**; shared by >1 grid: "
             f"**{char['n_shared_tiles']}**; max grids on one tile: "
             f"**{char['max_grids_per_tile']}**\n")
    L.append(f"- tiles-per-grid distribution: `{char['tiles_per_grid_dist']}` "
             "(1 = grid inside a single tile → no cross-tile merge)\n")
    L.append(f"- hottest tiles (grids sharing them): `{char['hottest_tiles']}`\n")
    L.append("## Throughput vs parallelism\n")
    L.append("| cores | total (s) | cubes/min | speedup | efficiency | mean load/grid (s) "
             "| load_images frac |\n|---|---|---|---|---|---|---|\n")
    for r in rows:
        L.append(f"| {r['cores']} | {r['total_seconds']} | {r['throughput_per_min']} | "
                 f"{r['speedup']}× | {r['efficiency']} | {r['mean_load_per_grid']} | "
                 f"{r['load_images_frac']} |\n")
    knee_row = next(r for r in rows if r["cores"] == knee)
    L.append(f"\n**Best total wall: cores={best['cores']}** "
             f"({best['total_seconds']}s, {best['throughput_per_min']} cubes/min) — but "
             f"throughput **plateaus at the knee cores={knee}** "
             f"({knee_row['total_seconds']}s): beyond it each extra process buys <5% total "
             f"while per-build `load_images` keeps rising (efficiency "
             f"{rows[0]['efficiency']}→{rows[-1]['efficiency']}). **Recommended ≈ {knee} "
             f"parallel builds** on this machine; the real win is cutting read contention "
             f"(Parts 2–3), not more processes.\n")
    L.append("\n![throughput](datacube_throughput_figures/throughput_vs_cores.png)\n")
    L.append("## Where the time goes\n")
    L.append("Summed per-grid phase seconds at each parallelism. If `load_images` swells "
             "with `cores` while other phases stay flat, that is the read-contention "
             "signal Part 2 (spec 12) will instrument per-read.\n")
    L.append("\n![phases](datacube_throughput_figures/phase_breakdown.png)\n")
    L.append("\n![load_images](datacube_throughput_figures/load_images_vs_cores.png)\n")
    lo, hi = rows[0]["mean_load_per_grid"], rows[-1]["mean_load_per_grid"]
    L.append(f"\nMean per-grid `load_images` went {lo}s (cores={rows[0]['cores']}) → "
             f"{hi}s (cores={rows[-1]['cores']}) — "
             f"{'a ' + str(round(hi / lo, 2)) + '× slowdown' if lo else 'n/a'}.\n")
    L.append("## Per-grid cost vs tiles touched\n")
    L.append("![wall_vs_tiles](datacube_throughput_figures/wall_vs_tiles.png)\n")
    L.append("## Caveats\n")
    L.append("- **Cache: measured, not forced** (spec 11). Runs are warm-as-is; re-running "
             "the same grids across settings can warm shared file blocks, though the grids "
             "read mostly-disjoint windows so reuse is limited. Part 2's per-read timings "
             "disentangle cache vs contention.\n")
    L.append("- Per-grid `wall_seconds` = `done.txt − start.txt` (excludes jitter, which is "
             "off here). Per-phase seconds come from the builder `timings.json` sidecar.\n")
    with fs.open(REPORT, "w") as f:
        f.write("".join(L))


# --- main --------------------------------------------------------------------

OUT_CSV = None  # set in main (module-level so run_sweep can reach it)


def main(argv=None) -> None:
    global OUT_CSV
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cores", default="1,2,4,6,8,10",
                    help="comma-separated parallelism settings")
    ap.add_argument("--n-grids", type=int, default=None, help="subset first N grids")
    ap.add_argument("--repeats", type=int, default=1)
    ap.add_argument("--smoke", action="store_true", help="3 grids, cores 1,2")
    ap.add_argument("--report-only", action="store_true",
                    help="rebuild report.md from the saved stats.json (reuses figures); "
                         "no sweep")
    args = ap.parse_args(argv)

    if args.report_only:
        stats_path = FIG_DIR.replace("_figures", "_stats.json")
        with fs.open(stats_path) as f:
            saved = json.load(f)
        write_report(saved["sweep"], saved["characterization"], saved["meta"])
        print(f"[report-only] regenerated {REPORT} from {os.path.basename(stats_path)}",
              flush=True)
        return

    if args.smoke:
        args.cores, args.n_grids = "1,2", 3
    cores_list = [int(c) for c in args.cores.split(",")]

    os.makedirs(OUT, exist_ok=True)
    grids_path = GRIDS
    if args.n_grids is not None:
        g = gpd.read_file(GRIDS).iloc[: args.n_grids]
        grids_path = os.path.join(OUT, "grids_subset.geojson")
        g.to_file(grids_path, driver="GeoJSON")

    OUT_CSV = os.path.join(OUT, "input.csv")
    if os.path.exists(OUT_CSV):
        fs.rm(OUT_CSV)

    print("[setup] slicing catalog per grid ...", flush=True)
    create_datacube.setup(
        catalog_filepath=CATALOG, timestamp_col="timestamp", shapefilepath=grids_path,
        id_col=ID_COL, run_folderpath=OUT, startdate=START, enddate=END, bands=BANDS,
        scl_mask_classes=SCL, mosaic_days=MOSAIC_DAYS, csv_filepath=OUT_CSV, label_col=None,
    )
    input_df = pd.read_csv(OUT_CSV)
    print(f"[setup] {len(input_df)} work-units", flush=True)

    char = characterize(input_df)
    results = run_sweep(input_df, cores_list, args.repeats)
    rows = aggregate(results)

    base_recs = min((r for r in results if r["cores"] == cores_list[0]),
                    key=lambda r: r["total_seconds"])["records"]
    make_plots(rows, char, base_recs)

    meta = {
        "run_utc": datetime.datetime.utcnow().isoformat() + "Z",
        "platform": platform.platform(), "cpu_count": os.cpu_count(),
        "window": [str(START.date()), str(END.date())], "cores_list": cores_list,
        "repeats": args.repeats, "catalog_tiles": int(len(fs.read_parquet(CATALOG))),
    }
    stats = {"meta": meta, "characterization": char, "sweep": rows}
    with fs.open(os.path.join(FIG_DIR.replace("_figures", "_stats.json")), "w") as f:
        json.dump(stats, f, indent=2, default=str)
    write_report(rows, char, meta)

    # tidy the snakemake scratch dir it drops in cwd
    if os.path.isdir(".snakemake"):
        shutil.rmtree(".snakemake", ignore_errors=True)
    print(f"\n[done] report -> {REPORT}", flush=True)


if __name__ == "__main__":
    import multiprocessing

    multiprocessing.freeze_support()
    main()
