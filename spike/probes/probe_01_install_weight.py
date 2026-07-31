"""Probe 01 — rslearn install weight + whether the acquisition path imports torch.

Spike questions Q3a and Q2a (`../RSLEARN_READ_2026-07-31.md` §6). Runs **offline** once
rslearn is installed; consumes zero satellite data.

Two things are measured:

1. **Weight** — venv size on disk, and (passed in by the run-book, which is the only thing
   that can time it) the cold-install wall time and downloaded bytes.
2. **Torch at import time** — `rslearn/utils/array.py` guards its torch import behind
   `if TYPE_CHECKING:`, and nothing outside `models/`+`train/` imports torch, so the
   materialize path *should* be torch-free at runtime even though torch is a core install
   dependency. That is a static reading of 81 torch-importing files. This checks it for real
   by importing the acquisition path into a clean interpreter and inspecting `sys.modules`.

Usage (see `../RUNBOOK-rslearn-spike.md` Step 1):

    python spike/probes/probe_01_install_weight.py \
        --out tests/outputs/rslearn_spike \
        --install-seconds 412 --download-mb 2610
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

# The import chain the spike actually cares about: query -> materialize -> composite ->
# read back as numpy. If torch is absent from sys.modules after these, the acquisition
# path is genuinely torch-free at runtime.
ACQUISITION_IMPORTS = [
    "rslearn.config",
    "rslearn.data_sources.utils",
    "rslearn.dataset.materialize",
    "rslearn.dataset.compositing",
    "rslearn.utils.raster_format",
]

HEAVY = ["torch", "lightning", "torchvision", "torchmetrics", "flask", "boto3"]


def _venv_size_mb(prefix: Path) -> float:
    """Size of the environment on disk, in MB."""
    out = subprocess.run(
        ["du", "-sk", str(prefix)], capture_output=True, text=True, check=True
    )
    return int(out.stdout.split()[0]) / 1024.0


def _import_probe() -> dict:
    """Import the acquisition path in a FRESH interpreter and report heavy modules.

    A subprocess is essential: this module's own interpreter may already have imported
    something heavy, which would make the result a false positive.
    """
    code = (
        "import sys, json, time\n"
        f"mods = {ACQUISITION_IMPORTS!r}\n"
        "t0 = time.perf_counter()\n"
        "for m in mods:\n"
        "    __import__(m)\n"
        "elapsed = time.perf_counter() - t0\n"
        f"heavy = {HEAVY!r}\n"
        "loaded = sorted(h for h in heavy if h in sys.modules)\n"
        "print(json.dumps({'import_seconds': round(elapsed, 3), 'heavy_loaded': loaded}))\n"
    )
    out = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True
    )
    return json.loads(out.stdout.strip().splitlines()[-1])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", required=True, help="output directory for _result.json")
    ap.add_argument(
        "--install-seconds",
        type=float,
        default=None,
        help="cold `pip install rslearn` wall time, from the run-book's `time` output",
    )
    ap.add_argument(
        "--download-mb",
        type=float,
        default=None,
        help="MB downloaded during the install, from the pip log",
    )
    args = ap.parse_args()

    outdir = Path(args.out)
    outdir.mkdir(parents=True, exist_ok=True)

    t0 = time.perf_counter()
    try:
        import rslearn

        version = getattr(rslearn, "__version__", "unknown")
    except ImportError as exc:
        result = {
            "step": "probe_01_install_weight",
            "status": "fail",
            "pass": False,
            "metrics": {},
            "expected": {},
            "error": f"rslearn not importable -- is .venv-rslearn active? ({exc})",
        }
        (outdir / "_result_probe01.json").write_text(json.dumps(result, indent=2))
        print(json.dumps(result, indent=2))
        return 1

    venv_mb = _venv_size_mb(Path(sys.prefix))
    imp = _import_probe()

    metrics = {
        "rslearn_version": version,
        "venv_size_mb": round(venv_mb, 1),
        "install_seconds": args.install_seconds,
        "download_mb": args.download_mb,
        "acquisition_import_seconds": imp["import_seconds"],
        "heavy_modules_loaded_by_acquisition_path": imp["heavy_loaded"],
        "torch_free_acquisition_path": "torch" not in imp["heavy_loaded"],
        "probe_wall_seconds": round(time.perf_counter() - t0, 2),
    }

    # The probe PASSES as long as it produced its measurements. It is descriptive, not a
    # gate -- a heavy venv is a finding, not a failure. The one thing that would make the
    # numbers meaningless is rslearn not importing at all, handled above.
    result = {
        "step": "probe_01_install_weight",
        "status": "ok",
        "pass": True,
        "metrics": metrics,
        "expected": {
            "torch_free_acquisition_path": True,
            "note": (
                "torch/lightning are CORE install deps (pyproject.toml:11-31) so venv_size_mb "
                "is expected to be large regardless; the prediction under test is that the "
                "acquisition path does not IMPORT torch (utils/array.py:10-11 is TYPE_CHECKING-"
                "guarded). If torch_free_acquisition_path is False, RSLEARN_READ section 4.3 is wrong."
            ),
        },
        "error": None,
    }
    (outdir / "_result_probe01.json").write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
