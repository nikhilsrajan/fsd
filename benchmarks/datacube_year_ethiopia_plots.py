"""Render the 3 NDVI figures from the saved arrays. Plots scoped to the growing
season (May-Oct); stats/build cover the full year."""
# ruff: noqa: E702  (compact `a; b` plotting lines are intentional here)
import json

import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = "/Users/nikhilsrajan/NASA-Harvest/project/fetch_satdata_claude"
OUT = f"{ROOT}/fsd/notebooks/outputs/datacube_fullyear"


def load(name):
    return np.load(f"{OUT}/{name}.npy", allow_pickle=True)


stats = json.load(open(f"{OUT}/heavy_stats.json"))
raw_t = pd.to_datetime(load("raw_times"))
mos_t = pd.to_datetime(load("mosaic_times"))
raw_m, nomask_m, mask_m = load("raw_median"), load("nomask_median"), load("mask_median")

SEASON = range(5, 11)
sr = np.array([t.month in SEASON for t in raw_t])
sm = np.array([t.month in SEASON for t in mos_t])

# --- Figure 1: 3-way median comparison ---------------------------------------
fig, ax = plt.subplots(figsize=(11, 5))
ax.plot(raw_t[sr], raw_m[sr], "o-", color="0.6", ms=3, lw=0.8, alpha=0.7,
        label=f"Raw per-acquisition (no mask, no mosaic) — {sr.sum()} dates")
ax.plot(mos_t[sm], nomask_m[sm], "s--", color="#d95f02", lw=1.6, ms=5,
        label="20-day median mosaic, NO cloud mask")
ax.plot(mos_t[sm], mask_m[sm], "^-", color="#1b9e77", lw=2.2, ms=6,
        label="20-day median mosaic + SCL cloud mask")
ax.set_ylabel("area-median NDVI"); ax.set_xlabel("2018")
ax.set_title("NDVI cleaning: raw → mosaic → cloud-masked mosaic "
             "(ROI s2grid=165bca4, May–Oct)")
ax.legend(loc="lower center"); ax.grid(alpha=0.3)
fig.autofmt_xdate(); fig.tight_layout()
fig.savefig(f"{OUT}/ndvi_compare.png", dpi=110); plt.close(fig)

# --- Figure 2: spaghetti (final masked cube, demo style) ---------------------
spag, spag_med = load("spaghetti"), load("spaghetti_median")
fig, ax = plt.subplots(figsize=(11, 5))
for ts in spag[:, sm]:
    ax.plot(mos_t[sm], ts, color="green", lw=1, alpha=0.2)
ax.plot(mos_t[sm], spag_med[sm], "k--", lw=1.5, label="median")
ax.set_ylabel("NDVI (interpolated)"); ax.set_xlabel("2018")
ax.set_title(f"First {len(spag)} per-pixel NDVI time series — final masked mosaic (May–Oct)")
ax.legend(); ax.grid(alpha=0.3)
fig.autofmt_xdate(); fig.tight_layout()
fig.savefig(f"{OUT}/ndvi_spaghetti.png", dpi=110); plt.close(fig)

# --- Figure 3: spatial triptych (cloud-mask effect) --------------------------
ms = stats["map_selection"]
maps = [("Raw single date\n" + ms["raw_date"][:10] + f" ({ms['raw_cloud_px']} cloud px)", "map_raw"),
        ("20-day mosaic, NO mask\n" + ms["bucket_date"][:10], "map_nomask"),
        ("20-day mosaic + cloud mask\n" + ms["bucket_date"][:10], "map_mask")]
fig, axes = plt.subplots(1, 3, figsize=(15, 5.2))
for ax, (title, arr) in zip(axes, maps):
    im = ax.imshow(load(arr), vmin=0, vmax=0.8, cmap="RdYlGn")
    ax.set_title(title); ax.axis("off")
fig.colorbar(im, ax=axes, fraction=0.025, pad=0.02, label="NDVI")
fig.suptitle("Cloud masking, spatially — same ROI, growing-season bucket", y=0.98)
fig.savefig(f"{OUT}/ndvi_maps.png", dpi=110, bbox_inches="tight"); plt.close(fig)

print("wrote ndvi_compare.png, ndvi_spaghetti.png, ndvi_maps.png to", OUT)
print("raw NDVI (season) range  %.3f..%.3f" % (raw_m[sr].min(), raw_m[sr].max()))
print("mask NDVI (season) range %.3f..%.3f" % (np.nanmin(mask_m[sm]), np.nanmax(mask_m[sm])))
