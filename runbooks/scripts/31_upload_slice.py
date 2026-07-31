"""Spec 31 / P1 — upload a real Sentinel-2 slice to the `rise` blob + repoint the catalog.

Run-book: `runbooks/31-p1-upload-slice.md`. This is the **data-staging step** for the
P1 storage seam: it puts real, already-COG Austria imagery on Azure and rewrites the
catalog so every band path is an `abfss://` URL. The datacube-on-blob demo (and the
`fsd.storage` seam work) then has something real to run against, with **no download
from CDSE/MPC involved** — deliberately, so the seam is proven independently of the
ingest/normalization redesign.

Why this needs no spec-31 code: `fsd.storage.put`/`write_parquet` already route
through fsspec -> adlfs. All that's required is `azure-identity` installed and
`FSSPEC_ABFSS_ANON=false` exported (adlfs then builds `DefaultAzureCredential`
itself). Verified against adlfs 2026.5.0 / fsspec 2026.6.0.

Self-contained by design (a prior heredoc+`$OUT` run-book silently wrote nothing when
the env var didn't survive into a fresh shell):
  - source paths derive from this file's location; the only input is `--dst`, because
    the concrete `rise` URL must never be committed to this public repo;
  - **everything** is inside try/except, so `_result.json` is written even on a hard
    failure. A traceback with no `_result.json` breaks the spec-24 D2 contract.

Idempotent: re-running skips any blob that already exists at the right size, so an
interrupted upload resumes by re-running the same command.

Usage, from the `fsd/` package root (see the run-book for the real --dst):
    .venv/bin/python runbooks/scripts/31_upload_slice.py --dst "abfss://<fs>@<account>.dfs.core.windows.net/p1-demo/imagery/" --dry-run
    .venv/bin/python runbooks/scripts/31_upload_slice.py --dst "abfss://<fs>@<account>.dfs.core.windows.net/p1-demo/imagery/"
"""

import argparse
import json
import os
import pathlib
import re
import sys
import time
import traceback

# fsd/runbooks/scripts/31_upload_slice.py -> parents[2] == fsd/
FSD_ROOT = pathlib.Path(__file__).resolve().parents[2]
SRC_CATALOG = FSD_ROOT / "tests" / "outputs" / "demo_e2e" / "imagery" / "catalog.parquet"
OUT = FSD_ROOT / "tests" / "outputs" / "spec31_upload"

# The slice (agreed 2026-07-17): test ROI `s2grid=476da24` sits 100% inside T33UWP,
# and Jul-Aug gives a real 2-window mosaic axis at mosaic_days=30 (not a degenerate T=1).
MGRS_TILE = "T33UWP"
MONTHS = (7, 8)
BANDS = ("B08", "SCL")  # B08 = config.REFERENCE_BAND; SCL is structurally required
                        # by build_datacube's hardcoded mask->drop chain (TODO #35).

result = {
    "step": "spec31-upload-slice",
    "status": "ok",
    "pass": False,
    "metrics": {},
    "expected": {
        "granules": 20,
        "files_total": 40,
        "bytes_total_gb_approx": 2.27,
        "catalog_rows_on_blob": 20,
        "every_catalog_path_is_abfss": True,
        "gdal_vsiadls_read_ok": True,
    },
    "error": None,
}


ABFSS_RE = re.compile(r"^abfss://([^@]+)@([^.]+)\.dfs\.core\.windows\.net/(.*)$")


def _fmt(n):
    return f"{n / 1e9:.2f} GB" if n >= 1e9 else f"{n / 1e6:.0f} MB"


def _to_vsi(url: str) -> str:
    """abfss://<fs>@<account>.dfs.core.windows.net/<path> -> /vsiadls/<fs>/<path>.

    A stand-in for spec 31 §2's `fsd.storage.to_vsi`, which doesn't exist yet — this
    script deliberately predates the implementation so the seam's central claim
    (D2: GDAL streams our blob COGs via /vsiadls/) is tested on real uploaded data
    before anyone writes code against it.
    """
    m = ABFSS_RE.match(url)
    if not m:
        raise ValueError(f"not a fully-qualified abfss:// URL: {url!r}")
    filesystem, _account, path = m.groups()
    return f"/vsiadls/{filesystem}/{path}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dst", required=True,
                    help="abfss://<fs>@<account>.dfs.core.windows.net/<prefix>/ (trailing / optional)")
    ap.add_argument("--dry-run", action="store_true", help="plan only; upload zero bytes")
    args = ap.parse_args()

    import geopandas as gpd

    from fsd.storage import fs

    dst = args.dst.rstrip("/")
    m = ABFSS_RE.match(dst)
    if not m:
        raise ValueError(
            f"--dst must be a fully-qualified abfss:// URL "
            f"(abfss://<fs>@<account>.dfs.core.windows.net/<path>); got {dst!r}"
        )
    filesystem, account, prefix = m.group(1), m.group(2), m.group(3)
    result["metrics"]["dst_filesystem"] = filesystem
    result["metrics"]["dst_prefix"] = prefix
    # NB: the account name is deliberately NOT recorded in _result.json — that file
    # gets pasted into the chat/repo. Presence-only.
    result["metrics"]["dst_account_resolved"] = bool(account)

    if os.environ.get("FSSPEC_ABFSS_ANON", "").lower() not in ("false", "0", "f"):
        raise RuntimeError(
            "FSSPEC_ABFSS_ANON is not set to 'false'. Without it adlfs may attempt "
            "anonymous access (its default consults AZURE_STORAGE_ANON, where anything "
            "but false/0/f means True) and every write will 403. "
            "Run: export FSSPEC_ABFSS_ANON=false"
        )

    # --- select the slice ----------------------------------------------------
    g = gpd.read_parquet(SRC_CATALOG)
    g["_mgrs"] = g.id.str.extract(r"_(T\d{2}[A-Z]{3})_")
    sel = g[(g._mgrs == MGRS_TILE) & (g.timestamp.dt.month.isin(MONTHS))].copy()
    sel = sel.drop(columns=["_mgrs"])
    if sel.empty:
        raise RuntimeError(f"No granules matched {MGRS_TILE} months={MONTHS}.")

    work = []          # (local_src, blob_dst, nbytes)
    new_folder = {}    # granule id -> blob folder
    for _, row in sel.iterrows():
        folder = f"{dst}/{row['id']}"
        new_folder[row["id"]] = folder
        for band in BANDS:
            src = os.path.join(row["local_folderpath"], f"{band}.tif")
            if not os.path.exists(src):
                raise FileNotFoundError(
                    f"Expected local band file missing: {src}. The source archive "
                    "may have been pruned; re-check tests/outputs/demo_e2e/imagery/."
                )
            work.append((src, f"{folder}/{band}.tif", os.path.getsize(src)))

    total = sum(w[2] for w in work)
    result["metrics"]["granules"] = int(len(sel))
    result["metrics"]["files_total"] = len(work)
    result["metrics"]["bytes_total"] = int(total)
    print(f"slice: {MGRS_TILE} months={MONTHS} bands={list(BANDS)}")
    print(f"  {len(sel)} granules -> {len(work)} files, {_fmt(total)}")

    if args.dry_run:
        result["metrics"]["dry_run"] = True
        result["pass"] = True
        print("\nDRY RUN — nothing uploaded.")
        return

    # --- upload (idempotent, resumable) --------------------------------------
    done_bytes = 0
    uploaded = skipped = 0
    t0 = time.time()
    for i, (src, blob, nbytes) in enumerate(work, 1):
        try:
            if fs.exists(blob) and fs.size(blob) == nbytes:
                skipped += 1
                done_bytes += nbytes
                print(f"[{i}/{len(work)}] skip (already on blob) {os.path.basename(blob)}")
                continue
        except Exception:
            pass  # treat any probe failure as "not there"; the put below is authoritative

        fs.put(src, blob)
        uploaded += 1
        done_bytes += nbytes
        el = time.time() - t0
        rate = done_bytes / el if el > 0 else 0
        eta = (total - done_bytes) / rate if rate > 0 else 0
        print(f"[{i}/{len(work)}] put {os.path.basename(blob)} "
              f"({_fmt(nbytes)}) | {_fmt(done_bytes)}/{_fmt(total)} "
              f"| {rate / 1e6:.1f} MB/s | ETA {eta / 60:.1f} min")

    result["metrics"]["files_uploaded"] = uploaded
    result["metrics"]["files_skipped_already_present"] = skipped
    result["metrics"]["upload_seconds"] = round(time.time() - t0, 1)

    # --- rewrite the catalog to point at blob --------------------------------
    # `local_folderpath` is the column build_datacube joins with `files` to get each
    # band path (builder.py:72). Repoint it at the blob folder. `files` is narrowed to
    # the bands we actually uploaded, so the blob catalog is self-consistent — leaving
    # B04/B8A/MTD_TL.xml listed would flatten into paths that don't exist on blob.
    sel["local_folderpath"] = sel["id"].map(new_folder)
    sel["files"] = ",".join(f"{b}.tif" for b in BANDS)

    blob_catalog = f"{dst}/catalog.parquet"
    fs.write_parquet(blob_catalog, sel)
    print(f"\nwrote catalog -> {blob_catalog}")

    # --- verify from the blob side, independently ----------------------------
    back = fs.read_parquet(blob_catalog)
    paths = [os.path.join(r["local_folderpath"], f)
             for _, r in back.iterrows() for f in str(r["files"]).split(",")]
    all_abfss = all(p.startswith("abfss://") for p in paths)
    result["metrics"]["catalog_rows_on_blob"] = int(len(back))
    result["metrics"]["every_catalog_path_is_abfss"] = bool(all_abfss)

    sample = paths[0]
    result["metrics"]["blob_sample_exists"] = bool(fs.exists(sample))

    # --- prove the GDAL pixel-read seam on the uploaded data -----------------
    # This is spec 31 D2/§4's claim, checked here BEFORE any code is written for it:
    # /vsiadls/ + a fresh AZURE_STORAGE_ACCESS_TOKEN reads our own uploaded COG.
    import rasterio
    from azure.identity import DefaultAzureCredential
    from rasterio.windows import Window

    b08 = next(p for p in paths if p.endswith("B08.tif"))
    vsi = _to_vsi(b08)
    result["metrics"]["gdal_vsi_shape_ok"] = vsi.startswith(f"/vsiadls/{filesystem}/")
    token = DefaultAzureCredential().get_token("https://storage.azure.com/.default").token
    with rasterio.Env(AZURE_STORAGE_ACCESS_TOKEN=token, AZURE_STORAGE_ACCOUNT=account):
        with rasterio.open(vsi) as src:
            arr = src.read(1, window=Window(0, 0, 256, 256))
            result["metrics"]["gdal_vsiadls_read_ok"] = True
            result["metrics"]["gdal_sample_shape"] = list(arr.shape)
            result["metrics"]["gdal_sample_dtype"] = str(arr.dtype)
            result["metrics"]["gdal_sample_nonzero"] = bool((arr != 0).any())

    result["pass"] = bool(
        len(sel) == 20
        and len(work) == 40
        and result["metrics"]["catalog_rows_on_blob"] == 20
        and all_abfss
        and result["metrics"]["blob_sample_exists"]
        and result["metrics"]["gdal_vsiadls_read_ok"]
        and result["metrics"]["gdal_sample_nonzero"]
    )


if __name__ == "__main__":
    try:
        main()
    except BaseException as e:
        result["status"] = "failed"
        result["pass"] = False
        result["error"] = f"{type(e).__name__}: {e}"
        traceback.print_exc()
    finally:
        try:
            OUT.mkdir(parents=True, exist_ok=True)
            (OUT / "_result.json").write_text(json.dumps(result, indent=2))
            print(f"\n_result.json -> {OUT / '_result.json'}")
            print(json.dumps(result, indent=2))
        except Exception:
            traceback.print_exc()
        sys.exit(0 if result["pass"] else 1)
