"""First real batch-download run (TODO #9): 1 year of the Ethiopia multi-CRS ROI,
4 bands. Exercises fsd.sources.cdse.download end-to-end and records fast-fail stats.

Run: .venv/bin/python benchmarks/download_year_ethiopia.py
Writes a stats JSON next to this file; the .md report is composed from it.
"""

import datetime
import json
import os
import time

from fsd.catalog.catalog import TileCatalog
from fsd.sources import cdse

WS = "/Users/nikhilsrajan/NASA-Harvest/project/fetch_satdata_claude"
ROI = f"{WS}/shapefiles/s2grid=165bca4.geojson"
# Dedicated benchmark tree so the real `satellite/` data stays unpolluted.
ROOT = f"{WS}/satellite_benchmark/sentinel-2-l2a"
CATALOG = f"{ROOT}/catalog.parquet"            # fresh fsd GeoParquet catalog
BANDS = ["B04", "B08", "B8A", "SCL"]
START = datetime.datetime(2018, 1, 1)
END = datetime.datetime(2019, 1, 1)
STATS_JSON = os.path.join(os.path.dirname(__file__), "download_year_ethiopia_stats.json")


def dir_bytes(path):
    total = 0
    for r, _, files in os.walk(path):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(r, f))
            except OSError:
                pass
    return total


def main():
    creds = cdse.CdseCredentials.from_json(f"{WS}/secrets/cdse_credentials.json")
    catalog = TileCatalog(CATALOG)

    t0 = time.time()
    result = cdse.download(
        ROI, START, END, BANDS, ROOT, catalog, creds,
        max_tiles=600, chunksize=100, progress=True,
    )
    wall = time.time() - t0

    nbytes = dir_bytes(ROOT)
    stats = {
        "run_utc": datetime.datetime.utcnow().isoformat() + "Z",
        "roi": os.path.basename(ROI),
        "window": [START.isoformat(), END.isoformat()],
        "bands": BANDS,
        "concurrency": None,  # filled from config below
        "chunksize": 100,
        "wall_s": round(wall, 1),
        "download_elapsed_s": round(result.elapsed_s, 1),
        "total_files": result.total_count,
        "successful": result.successful_count,
        "skipped": result.skipped_count,
        "failed": result.failed_count,
        "reason_counts": result.reason_counts,
        "bytes_on_disk": nbytes,
        "gb_on_disk": round(nbytes / 1e9, 2),
        "catalog_rows": (len(catalog.read()) if os.path.exists(CATALOG) else 0),
        # keep only a sample of failures to stay small
        "failures_sample": result.failures[:40],
    }
    from fsd import config
    stats["concurrency"] = config.MAX_CONCURRENT_S3

    with open(STATS_JSON, "w") as f:
        json.dump(stats, f, indent=2, default=str)
    print("DONE", json.dumps({k: stats[k] for k in
          ("total_files", "successful", "skipped", "failed", "gb_on_disk",
           "wall_s", "reason_counts")}, default=str))


if __name__ == "__main__":
    main()
