"""Safe download runner CLI (spec 26). A thin driver over `cdse.download_resume` —
no download logic of its own: parse args, build the `should_stop` closure, call
`download_resume` (or `plan_download` for `--dry-run`), write the spec-24
`_result.json`.

Run as:  python -m fsd.sources.download_cli --roi roi.geojson --start 2018-04-01 \\
             --end 2018-06-01 --bands B04 B08 --dst /data/austria --catalog \\
             /data/austria/catalog.parquet --max-tiles 5 --dry-run
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

import pandas as pd

from fsd.catalog.catalog import TileCatalog
from fsd.sources import cdse
from fsd.sources.cdse import CdseCredentials


def _parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="python -m fsd.sources.download_cli",
        description="Safe CDSE download runner: --dry-run preview, --stop-file clean stop, "
                    "progress + ETA, and a spec-24 _result.json.",
    )
    p.add_argument("--roi", required=True, help="ROI GeoJSON path")
    p.add_argument("--start", required=True, help="window start, YYYY-MM-DD")
    p.add_argument("--end", required=True, help="window end, YYYY-MM-DD")
    p.add_argument("--bands", required=True, nargs="+", help="band list, e.g. B04 B08")
    p.add_argument("--dst", required=True, help="root download folder")
    p.add_argument("--catalog", required=True, help="catalog parquet path")
    p.add_argument("--creds", default=os.environ.get("CDSE_CREDENTIALS_JSON"),
                   help="CDSE credentials json (default $CDSE_CREDENTIALS_JSON)")
    p.add_argument("--max-tiles", type=int, required=True, help="guardrail (as fsd.download)")
    p.add_argument("--max-cloudcover", type=float, default=None)
    p.add_argument("--dry-run", action="store_true",
                   help="print the plan (metadata only, zero band bytes) and exit")
    p.add_argument("--stop-file", default=None,
                   help="when this file appears, stop cleanly (touch it to stop)")
    p.add_argument("--max-passes", type=int, default=10)
    p.add_argument("--no-cog", action="store_true", help="keep native JP2 (default converts to COG)")
    p.add_argument("--max-convert-procs", type=int, default=None)
    p.add_argument("--max-staged", type=int, default=None)
    p.add_argument("--no-probe", action="store_true",
                   help="skip the single baseline probe_throughput on the real path")
    p.add_argument("--result-json", default=None,
                   help="write the _result.json here (default <dst>/_result.json)")
    p.add_argument("--expected-json", default=None,
                   help="JSON file of the runbook's success criteria; echoed into the "
                        "_result.json 'expected' block for a self-contained diff (spec 26 §4)")
    p.add_argument("--quiet", action="store_true", help="suppress live progress lines")
    return p.parse_args(argv)


def _write_result(path: str, result: dict) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w") as f:
        json.dump(result, f, indent=2, default=str)


def _expected_block(expected_json: str | None, *, run_invariants: bool) -> dict:
    """The `_result.json` 'expected' block (spec 26 §4). Starts from the universal
    success invariants the CLI itself gates exit-0 on (a real run only), then merges in
    the runbook's run-specific criteria from `--expected-json` (which wins on overlap).
    """
    expected: dict = {}
    if run_invariants:
        expected = {"failed": 0, "stopped": False, "circuit_tripped": False, "pool_broken": False}
    if expected_json:
        with open(expected_json) as f:
            expected.update(json.load(f))
    return expected


def _stop_predicate(stop_file: str | None):
    if stop_file is None:
        return None
    return lambda: os.path.exists(stop_file)


def main(argv=None) -> int:
    args = _parse_args(argv)
    result_json = args.result_json or os.path.join(args.dst, "_result.json")
    cog = not args.no_cog

    if not args.dry_run and not args.creds:
        raise SystemExit(
            "--creds is required (or set $CDSE_CREDENTIALS_JSON) for a real download"
        )

    try:
        return _run(args, result_json, cog)
    except Exception as e:  # noqa: BLE001 - any failure must still leave a pasteable result
        # spec 26 §4: on a crash (network, creds, disk, …) still write a _result.json so
        # the runbook flow has something to paste, then re-raise so the traceback shows.
        _write_result(result_json, {
            "step": "download-confirm-run",
            "status": "failed",
            "pass": 0,
            "metrics": {},
            "expected": _expected_block(args.expected_json, run_invariants=not args.dry_run),
            "error": repr(e),
        })
        raise


def _run(args, result_json: str, cog: bool) -> int:
    if args.dry_run:
        plan = cdse.plan_download(
            args.roi, pd.to_datetime(args.start), pd.to_datetime(args.end), args.bands,
            catalog_filepath=args.catalog, dst_folderpath=args.dst,
            max_cloudcover=args.max_cloudcover,
        )
        print(cdse.format_download_plan(plan))
        _write_result(result_json, {
            "step": "download-confirm-run",
            "status": "dry-run",
            "pass": 0,
            "metrics": {
                "needed": plan["needed_count"],
                "present": plan["present_count"],
                "missing": plan["missing_count"],
            },
            "expected": _expected_block(args.expected_json, run_invariants=False),
            "error": None,
        })
        return 0

    creds = CdseCredentials.from_json(args.creds)
    verbose = not args.quiet

    probe_mb_per_s = 0.0
    if not args.no_probe:
        # The probe silently downloads one full JP2 band file (~50-150 MB) to measure
        # throughput; without these lines the run looks hung during that transfer.
        if verbose:
            print("[fsd.download_cli] probing throughput (downloads 1 band file)…", flush=True)
        probe_mb_per_s, _, _ = cdse.probe_throughput(
            args.roi, pd.to_datetime(args.start), pd.to_datetime(args.end), args.bands,
            creds, max_cloudcover=args.max_cloudcover,
        )
        if verbose:
            print(f"[fsd.download_cli] probe: {probe_mb_per_s:.1f} MB/s", flush=True)

    catalog = TileCatalog(args.catalog)
    should_stop = _stop_predicate(args.stop_file)
    if args.stop_file and os.path.exists(args.stop_file):
        print(
            f"[fsd.download_cli] warning: stop-file {args.stop_file} already exists — this run "
            f"will stop immediately without downloading. rm it first to actually download.",
            file=sys.stderr, flush=True,
        )
    if verbose:
        # download_resume does its own STAC search + planning before the first granule
        # completes; label that second silent gap so it doesn't read as a hang either.
        print("[fsd.download_cli] discovering + planning download…", flush=True)
    t0 = time.time()
    results = cdse.download_resume(
        args.roi, pd.to_datetime(args.start), pd.to_datetime(args.end), args.bands,
        args.dst, catalog, creds,
        max_tiles=args.max_tiles, max_cloudcover=args.max_cloudcover,
        progress=not args.quiet, max_passes=args.max_passes, cog=cog,
        max_convert_procs=args.max_convert_procs, max_staged=args.max_staged,
        should_stop=should_stop,
    )
    agg = cdse.sum_results(results)
    elapsed_s = time.time() - t0

    aggregate_mb_per_s = (
        agg.bytes_downloaded / 1e6 / agg.transfer_seconds if agg.transfer_seconds > 0 else 0.0
    )
    # spec 26 review, finding 1: sum_results SUMS failed_count across passes, so a resume that
    # recovers a transient failure on a later pass has agg.failed_count > 0 even though every file
    # ultimately landed. Judge completion by the TERMINAL pass (download_resume's own break
    # condition — a clean final pass), NOT the historical sum. An empty results list means
    # download_resume stopped before pass 1 (stop-file already present) → treat as a user stop.
    terminal = results[-1] if results else agg
    stopped = agg.stopped or not results
    unresolved_pool_broken = terminal.pool_broken and terminal.failed_count > 0
    failed = terminal.failed_count > 0 or terminal.circuit_tripped or unresolved_pool_broken
    if stopped:
        status = "stopped"
    elif failed:
        status = "failed"
    else:
        status = "ok"

    error = None
    if status == "failed":
        reasons = []
        if terminal.failed_count > 0:
            reasons.append(f"{terminal.failed_count} file(s) failed on the terminal pass")
        if terminal.circuit_tripped:
            reasons.append("circuit breaker tripped")
        if unresolved_pool_broken:
            reasons.append("convert pool broken with unresolved failures")
        error = "; ".join(reasons) or "download reported failure"

    print(
        f"\n[fsd.download_cli] {status}: successful={agg.successful_count} "
        f"failed={terminal.failed_count} (total across passes {agg.failed_count}) "
        f"skipped={agg.skipped_count} "
        f"({agg.bytes_downloaded/1e9:.2f} GB) | transfer={agg.transfer_seconds:.1f}s "
        f"convert={agg.convert_seconds:.1f}s | probe={probe_mb_per_s:.1f} MB/s "
        f"aggregate={aggregate_mb_per_s:.1f} MB/s | stopped={stopped} "
        f"circuit_tripped={terminal.circuit_tripped} pool_broken={terminal.pool_broken}",
        flush=True,
    )

    _write_result(result_json, {
        "step": "download-confirm-run",
        "status": status,
        "pass": len(results),
        "metrics": {
            "successful": agg.successful_count,
            "failed": terminal.failed_count,      # terminal pass = the completion gate
            "failed_total": agg.failed_count,     # transient failures across all passes (diagnostic)
            "skipped": agg.skipped_count,
            "gb": round(agg.bytes_downloaded / 1e9, 3),
            "transfer_s": round(agg.transfer_seconds, 1),
            "convert_s": round(agg.convert_seconds, 1),
            "probe_mb_per_s": round(probe_mb_per_s, 2),
            "aggregate_mb_per_s": round(aggregate_mb_per_s, 2),
            "elapsed_s": round(elapsed_s, 1),
            "stopped": stopped,
            "circuit_tripped": terminal.circuit_tripped,
            "pool_broken": terminal.pool_broken,
        },
        "expected": _expected_block(args.expected_json, run_invariants=True),
        "error": error,
    })
    # spec 26 C4: exit 0 on clean completion OR a user stop; non-zero otherwise.
    return 0 if (stopped or not failed) else 1


if __name__ == "__main__":
    raise SystemExit(main())
