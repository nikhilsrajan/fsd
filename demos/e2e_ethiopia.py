"""End-to-end demo (spec 19): demo_01 + demo_02 + demo_03 as one fsd flow.

Runs on the EXISTING Ethiopia `satellite_benchmark/` data (no download):
  1. ROI -> S2 grids (fsd.grid) + save GeoJSON/PNG for QGIS
  2. training data (create_training_data with the adapter -> features.npy)
  3. train an RF (sklearn)
  4. inference datacubes over the grids (workflows.create_datacube)
  5. run_inference -> COG per grid + STAC + merged crop map
  6. plots: per-class NDVI timeseries + categorical model-output map

Model quality is NOT meaningful here (Austrian labels on Ethiopian pixels) — this validates the
pipeline and yields QGIS artifacts. Run in the isolated venv:

    python3.11 -m venv .venv-modeldeploy
    .venv-modeldeploy/bin/pip install -e ".[dev,grid,model-example]"
    .venv-modeldeploy/bin/python demos/e2e_ethiopia.py            # full run
    .venv-modeldeploy/bin/python demos/e2e_ethiopia.py --fast     # quick smoke
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import sys
import time

import geopandas as gpd
import numpy as np
import pandas as pd

# make `adapters:DemoRF` importable when run as a script from anywhere.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from adapters import DemoRF  # noqa: E402

import fsd  # noqa: E402
from fsd import grid  # noqa: E402
from fsd.model import bundle  # noqa: E402
from fsd.workflows import create_datacube  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))                      # workspace root
CATALOG = os.path.join(ROOT, "satellite_benchmark/sentinel-2-l2a/catalog.parquet")
FIELDS = os.path.join(ROOT, "shapefiles/austria_eurocrops_sampled_ethiopia_translated.geojson")
ROI = os.path.join(ROOT, "shapefiles/inference_roi.geojson")
OUTDIR = os.path.join(HERE, "..", "tests/outputs/demo_e2e")       # heavy artifacts (gitignored)
FIGDIR = os.path.join(HERE, "figures")                            # small PNGs (committable)
BANDS = ["B04", "B08", "B8A", "SCL"]
SCL_MASK = [0, 1, 3, 7, 8, 9, 10]
MOSAIC_DAYS = 20


STEP_TIMES: list = []   # [(label, seconds), ...] — filled by timed_step, dumped at the end


def log(msg):
    print(f"\n=== {msg} ===", flush=True)


def timed_step(label, fn, *args, **kwargs):
    """Run a step, record its wall-clock, and return its result (see the breakdown table)."""
    t = time.time()
    out = fn(*args, **kwargs)
    dt = time.time() - t
    STEP_TIMES.append((label, dt))
    print(f"  [{label}] took {dt:.1f}s", flush=True)
    return out


def _write_timing_breakdown(total):
    """Print the per-step breakdown table and write timings.json next to the outputs."""
    print("\n=== timing breakdown ===")
    print(f"{'step':<28}{'seconds':>10}{'share':>8}")
    for label, dt in STEP_TIMES:
        print(f"{label:<28}{dt:>10.1f}{100 * dt / total:>7.0f}%")
    print(f"{'TOTAL':<28}{total:>10.1f}{100:>7.0f}%")
    payload = {"total_seconds": round(total, 1),
               "steps": [{"step": s, "seconds": round(dt, 1)} for s, dt in STEP_TIMES]}
    with open(os.path.join(OUTDIR, "timings.json"), "w") as fh:
        json.dump(payload, fh, indent=2)


def step_tiling(fast):
    log("1. ROI -> S2 grids (fsd.grid.roi_to_s2_grids + overlay clip)")
    grids = grid.roi_to_s2_grids(ROI, grid_size_km=5, scale_fact=1.1)
    if fast:
        grids = grids.iloc[:6].reset_index(drop=True)
    grids_fp = os.path.join(OUTDIR, "inference_s2_grids.geojson")
    grids.to_file(grids_fp, driver="GeoJSON")
    print(f"grids: {len(grids)} cells -> {grids_fp}")
    _plot_grids(grids, grids_fp)
    return grids, grids_fp


def step_training_data(fast, adapter):
    log("2. training data (create_training_data with adapter -> features.npy)")
    fields_fp = FIELDS
    if fast:
        g = gpd.read_file(FIELDS)
        g = g.groupby("EC_hcat_n", group_keys=False).sample(n=3, random_state=7)
        fields_fp = os.path.join(OUTDIR, "train_fields_subset.geojson")
        g.to_file(fields_fp, driver="GeoJSON")
    td = fsd.create_training_data(
        label_polygons=fields_fp, catalog_filepath=CATALOG,
        startdate=START, enddate=END, mosaic_days=MOSAIC_DAYS, bands=BANDS,
        id_col="fid", label_col="EC_hcat_n",
        export_folderpath=os.path.join(OUTDIR, "training_data"),
        run_folderpath=os.path.join(OUTDIR, "training_run"),
        adapter=adapter, cores=CORES,
    )
    d = td.load()
    print(f"features: {d['features'].shape} {td.feature_bands} | raw: {d['data'].shape}")
    return td, d


def step_train(d):
    log("3. train RandomForest (sklearn — fsd does not train)")
    import joblib
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.preprocessing import LabelEncoder

    X = d["features"].reshape(len(d["features"]), -1)
    y_raw = d["feature_labels"]
    keep = ~np.isnan(X).any(axis=1)                       # RF can't take NaN
    X, y_raw = X[keep], np.asarray(y_raw)[keep]
    le = LabelEncoder()
    y = le.fit_transform(y_raw)
    clf = RandomForestClassifier(n_estimators=200, n_jobs=-1, random_state=42).fit(X, y)
    model_fp = os.path.join(OUTDIR, "rf.joblib")
    joblib.dump((clf, le), model_fp)
    print(f"trained on {len(X)} samples, {len(le.classes_)} classes -> {model_fp}")
    return model_fp, list(le.classes_)


def step_inference_datacubes(fast, grids_fp):
    log("4. inference datacubes over the grids (workflows.create_datacube)")
    infer_run = os.path.join(OUTDIR, "inference_datacubes")
    infer_csv = os.path.join(infer_run, "input.csv")
    create_datacube.run_create_datacube(
        catalog_filepath=CATALOG, timestamp_col="timestamp",
        shapefilepath=grids_fp, id_col="id", run_folderpath=infer_run,
        startdate=START, enddate=END, bands=BANDS, scl_mask_classes=SCL_MASK,
        mosaic_days=MOSAIC_DAYS, csv_filepath=infer_csv, label_col=None, cores=CORES,
    )
    n = len(pd.read_csv(infer_csv))
    print(f"inference cubes: {n} -> {infer_csv}")
    return infer_csv


def step_inference(adapter, model_fp, infer_csv):
    log("5. run_inference -> COG per grid + STAC + merged crop map")
    adapter.artifacts = {"model": model_fp}
    # showcase the bundle format (spec 18 F5): save + model-free read_spec.
    bundle_dir = bundle.save(adapter, {"model": model_fp}, os.path.join(OUTDIR, "bundle"))
    print("bundle spec:", bundle.read_spec(bundle_dir)["adapter"],
          "T=", bundle.read_spec(bundle_dir)["n_timestamps"])
    # merge=False: the ROI straddles the S2 zone-36/37 boundary, so per-grid datacubes land in
    # BOTH EPSG:32636 and 32637 (the builder picks each grid's dominant zone). fsd's single-CRS
    # merge rightly refuses that; for a display map we reproject to the dominant zone (below).
    result = fsd.run_inference(
        model=adapter,                                    # live adapter (sequential; robust)
        inference_datacubes=infer_csv,
        output_folderpath=os.path.join(OUTDIR, "model_outputs"),
        merge=False, progress=True,
    )
    merged_fp = _merge_for_display(
        result.output_filepaths, os.path.join(OUTDIR, "model_outputs", "merged.tif")
    )
    print(f"outputs: {len(result.output_filepaths)} COGs | stac: {result.stac_catalog_filepath}")
    print(f"merged (display, dominant-zone): {merged_fp}")
    return result, merged_fp


def step_plots(d, merged_fp, classes):
    log("6. plots: per-class NDVI timeseries + categorical model-output map")
    _plot_ndvi_timeseries(d)
    if merged_fp:
        _plot_crop_map(merged_fp, classes)


# --- display merge (reproject to the dominant zone) --------------------------

def _merge_for_display(filepaths, dst, nodata=255):
    """Merge output COGs into one raster for the map. The ROI spans two UTM zones, so reproject
    every output to the **most common** CRS (nearest, categorical-safe) then mosaic — the
    fsd "collapse to the dominant zone before merge" principle, applied to outputs for display."""
    import rasterio
    from rasterio.merge import merge as rio_merge
    from rasterio.warp import Resampling, calculate_default_transform, reproject

    counts = {}
    for fp in filepaths:
        with rasterio.open(fp) as s:
            counts[s.crs.to_string()] = counts.get(s.crs.to_string(), 0) + 1
    target = max(counts, key=counts.get)

    datasets, tmps = [], []
    for fp in filepaths:
        src = rasterio.open(fp)
        if src.crs.to_string() == target:
            datasets.append(src)
            continue
        transform, w, h = calculate_default_transform(
            src.crs, target, src.width, src.height, *src.bounds)
        prof = src.profile.copy()
        prof.update(driver="GTiff", crs=target, transform=transform, width=w, height=h,
                    nodata=nodata)
        tmp = f"{fp}.reproj.tif"
        tmps.append(tmp)
        with rasterio.open(tmp, "w", **prof) as d:
            reproject(rasterio.band(src, 1), rasterio.band(d, 1),
                      src_transform=src.transform, src_crs=src.crs,
                      dst_transform=transform, dst_crs=target,
                      src_nodata=nodata, dst_nodata=nodata, resampling=Resampling.nearest)
        src.close()
        datasets.append(rasterio.open(tmp))

    mosaic, out_t = rio_merge(datasets, nodata=nodata)
    prof = datasets[0].profile.copy()
    prof.update(driver="GTiff", height=mosaic.shape[1], width=mosaic.shape[2],
                transform=out_t, crs=target, nodata=nodata)
    for d in datasets:
        d.close()
    with rasterio.open(dst, "w", **prof) as d:
        d.write(mosaic)
    for t in tmps:
        os.remove(t)
    print(f"  display merge -> {len(counts)} zone(s) {sorted(counts)}, dominant {target}")
    return dst


# --- plotting helpers --------------------------------------------------------

def _plot_grids(grids, grids_fp):
    import matplotlib.pyplot as plt
    roi = gpd.read_file(ROI)
    fig, ax = plt.subplots(figsize=(8, 7))
    roi.boundary.plot(ax=ax, color="black", linewidth=1.5, label="ROI")
    grids.boundary.plot(ax=ax, color="tab:blue", linewidth=0.6)
    ax.set_title(f"ROI → {len(grids)} S2 grids (5 km, 10% overlap, clipped)")
    ax.set_xlabel("lon")
    ax.set_ylabel("lat")
    _save(fig, "s2_grids.png")


def _plot_ndvi_timeseries(d):
    import matplotlib.pyplot as plt
    feats, labels = d["features"], np.asarray(d["feature_labels"])
    ts = d["metadata"]["timestamps"]
    fb = d["metadata"]["feature_bands"]
    ndvi = feats[:, :, fb.index("NDVI")]                 # (pixels, T)
    fig, ax = plt.subplots(figsize=(11, 6))
    for lab in sorted(set(labels)):
        med = np.nanmedian(ndvi[labels == lab], axis=0)
        ax.plot(ts, med, marker="o", markersize=3, linewidth=1.2, label=lab)
    ax.set_title("Per-class median NDVI over the season (training features)")
    ax.set_ylabel("NDVI")
    ax.set_xlabel("mosaic window")
    ax.legend(bbox_to_anchor=(1.02, 1), loc="upper left", fontsize=7)
    fig.autofmt_xdate()
    _save(fig, "ndvi_timeseries.png")


def _plot_crop_map(merged_fp, classes):
    import matplotlib.patches as mpatches
    import matplotlib.pyplot as plt
    import rasterio
    from matplotlib.colors import BoundaryNorm, ListedColormap

    with rasterio.open(merged_fp) as src:
        arr = src.read(1)
    arr = np.ma.masked_equal(arr, 255)
    values = list(range(len(classes)))
    cmap = ListedColormap(plt.cm.tab20(np.linspace(0, 1, len(values))))
    norm = BoundaryNorm(np.array(values + [values[-1] + 1]) - 0.5, cmap.N)
    fig, ax = plt.subplots(figsize=(10, 9))
    ax.imshow(arr, cmap=cmap, norm=norm)
    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_title("Model output — crop class map (merged over ROI)")
    handles = [mpatches.Patch(color=cmap(i), label=classes[i]) for i in values]
    ax.legend(handles=handles, bbox_to_anchor=(1.02, 1), loc="upper left", fontsize=7)
    _save(fig, "crop_map.png")


def _save(fig, name):
    import matplotlib.pyplot as plt
    os.makedirs(FIGDIR, exist_ok=True)
    path = os.path.join(FIGDIR, name)
    fig.savefig(path, dpi=140, bbox_inches="tight")
    plt.close(fig)
    print(f"  figure -> demos/figures/{name}")


def main():
    ap = argparse.ArgumentParser(description="fsd end-to-end demo (spec 19).")
    ap.add_argument("--fast", action="store_true",
                    help="quick smoke: 4-month window, 33 fields, 6 grids.")
    ap.add_argument("--cores", type=int, default=8)
    args = ap.parse_args()

    global START, END, CORES
    CORES = args.cores
    START = datetime.datetime(2018, 1, 1)
    END = datetime.datetime(2018, 5, 1) if args.fast else datetime.datetime(2018, 12, 31)
    T = fsd.compute_n_timestamps(START, END, MOSAIC_DAYS)

    os.makedirs(OUTDIR, exist_ok=True)
    print(f"mode: {'FAST' if args.fast else 'FULL'} | window {START:%Y-%m-%d}..{END:%Y-%m-%d} "
          f"| T={T} | cores={CORES}\nOUTDIR={os.path.abspath(OUTDIR)}")

    adapter = DemoRF()
    adapter.n_timestamps = T                              # match the chosen window

    t0 = time.time()
    grids, grids_fp = timed_step("1_tiling", step_tiling, args.fast)
    td, d = timed_step("2_training_data", step_training_data, args.fast, adapter)
    model_fp, classes = timed_step("3_train_rf", step_train, d)
    infer_csv = timed_step("4_inference_datacubes", step_inference_datacubes, args.fast, grids_fp)
    _result, merged_fp = timed_step("5_run_inference", step_inference, adapter, model_fp, infer_csv)
    timed_step("6_plots", step_plots, d, merged_fp, classes)
    total = time.time() - t0
    _write_timing_breakdown(total)
    log(f"DONE in {total:.0f}s — outputs under {os.path.abspath(OUTDIR)}")


if __name__ == "__main__":
    main()
