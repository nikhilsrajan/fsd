"""Runner seam — execute the datacube task across many work-units.

Spec: specs/08-workflows.md, specs/10-storage-and-scale.md.

v1 backend: local (Snakemake). Phase 2 backend: azure-batch (dispatches the same
`fsd.workflows.task` CLI on pool VMs). Same interface; runner is swappable.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
from importlib.resources import files

_SNAKEFILE = "workflows/_snakefiles/create_datacube/Snakefile"


def _snakefile_path() -> str:
    """Locate the bundled Snakefile (package-data) at runtime."""
    return str(files("fsd").joinpath(_SNAKEFILE))


def _run(cmd: list[str]) -> int:
    """Run `cmd`, isolated in its own process group so Ctrl-C stops the whole
    Snakemake tree cleanly (port of legacy run_snakemake)."""
    process = subprocess.Popen(cmd, start_new_session=True)
    try:
        process.wait()
    except KeyboardInterrupt:
        print("\nInterrupt received, stopping Snakemake...")
        os.killpg(process.pid, signal.SIGINT)
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
    return process.returncode


def run_local(
    input_csv: str,
    *,
    cores: int,
    dry_run: bool = False,
    unlock: bool = False,
    njobs: int = 1,
    njobs_load_images: int = 1,
    jitter_span: int = 1,
) -> subprocess.CompletedProcess:
    """Local runner: drive the bundled Snakefile over `input_csv` rows.

    `cores` = Snakemake parallelism (how many datacubes build at once); `njobs` /
    `njobs_load_images` = intra-build parallelism passed to each task.
    """
    config = {
        "input_csv": input_csv,
        "njobs": njobs,
        "njobs_load_images": njobs_load_images,
        "jitter_span": jitter_span,
    }
    # Invoke via the running interpreter so it resolves regardless of PATH /
    # venv activation (and the task shells out with the same sys.executable).
    cmd = [
        sys.executable, "-m", "snakemake",
        "--snakefile", _snakefile_path(),
        "--cores", str(cores),
        "--config", *[f"{k}={v}" for k, v in config.items()],
    ]
    if dry_run:
        cmd.append("--dry-run")
    if unlock:
        cmd.append("--unlock")

    returncode = _run(cmd)
    return subprocess.CompletedProcess(args=cmd, returncode=returncode)


# Phase 2 (not implemented in v1):
# def run_azure_batch(input_csv, *, pool_id, ...): ...
