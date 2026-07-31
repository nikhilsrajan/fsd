"""Node-side adapter-import smoke (spec 38 D11).

The ONE check the driver cannot do alone: whether the adapter (module:attr) actually
imports and its artifact actually loads **inside the real inference Environment** -- the
driver's own venv is not guaranteed to mirror the node's image (ADR 0002). Runs as a
single one-node job, once, before the N-node fan-out (`run_aml_inference`); a missing
`sklearn` or an un-importable adapter fails here in ~40-380s (one node's cold start)
instead of on every fan-out node.

No pipeline logic: fetch the staged bundle to scratch (reuses
`infer_shard.fetch_bundle_to_scratch`), `bundle.load` it (resolves the import + reads the
artifact), and confirm `predict` is callable. Writes a `_status/*.json` (spec 24/36 shape).

Run as: python -m fsd.workflows.adapter_smoke <bundle_url> --status-url <url>
"""

from __future__ import annotations

import argparse
import json
import shutil
import tempfile

from fsd.model import bundle as _bundle
from fsd.storage import fs
from fsd.workflows.infer_shard import fetch_bundle_to_scratch


def run_smoke(bundle_url: str, status_url: str) -> dict:
    scratch_dir = tempfile.mkdtemp(prefix="fsd-smoke-bundle-")
    error = None
    try:
        local_bundle = fetch_bundle_to_scratch(bundle_url, scratch_dir)
        adapter = _bundle.load(local_bundle)
        if not callable(getattr(adapter, "predict", None)):
            raise TypeError(f"{type(adapter).__name__}.predict is not callable")
    except Exception as exc:  # noqa: BLE001 - always report, never crash the job silently
        error = str(exc)
    finally:
        shutil.rmtree(scratch_dir, ignore_errors=True)

    status = {"status": "ok" if error is None else "failed", "error": error}
    with fs.open(status_url, "w") as f:
        json.dump(status, f, indent=2)
    return status


def _parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="python -m fsd.workflows.adapter_smoke",
        description="One-node adapter-import smoke, run once before the AML inference "
                     "fan-out (spec 38 D11).",
    )
    p.add_argument("bundle_url", help="the staged bundle folder (any fsd.storage URL)")
    p.add_argument("--status-url", required=True)
    return p.parse_args(argv)


def main(argv=None) -> None:
    args = _parse_args(argv)
    status = run_smoke(args.bundle_url, args.status_url)
    if status["status"] != "ok":
        raise SystemExit(f"adapter-import smoke failed: {status}")


if __name__ == "__main__":
    main()
