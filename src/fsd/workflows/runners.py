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
_INFER_SNAKEFILE = "workflows/_snakefiles/create_inference/Snakefile"
_INFER_ONLY_SNAKEFILE = "workflows/_snakefiles/infer_only/Snakefile"


def _snakefile_path(rel: str = _SNAKEFILE) -> str:
    """Locate a bundled Snakefile (package-data) at runtime."""
    return str(files("fsd").joinpath(rel))


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


def run_local_inference(
    input_csv: str,
    *,
    cores: int,
    bundle_path: str,
    predict_batch_size: int | None = None,
    skip_nan: bool = True,
    overwrite: bool = False,
    dry_run: bool = False,
    unlock: bool = False,
    njobs: int = 1,
    njobs_load_images: int = 1,
    jitter_span: int = 1,
) -> subprocess.CompletedProcess:
    """Local runner for ROI inference (spec 21): drive the per-cell **build+infer** Snakefile
    over `input_csv` rows.

    Same seam as `run_local` — `cores` = how many cells run at once — but each job shells
    `fsd.workflows.infer_task` (build the cell's datacube, then infer -> output.tif) instead of
    the build-only task. `bundle_path` is the model the workers reload. `overwrite` forces a
    recompute (`--forceall`); otherwise `done_infer.txt` sentinels make it resumable. Azure Batch
    (P4) dispatches this same task; only this runner is swapped.
    """
    conf = {
        "input_csv": input_csv,
        "bundle_path": bundle_path,
        "skip_nan": 1 if skip_nan else 0,
        "njobs": njobs,
        "njobs_load_images": njobs_load_images,
        "jitter_span": jitter_span,
    }
    if predict_batch_size is not None:  # snakemake parses an empty `key=` as None -> omit it
        conf["predict_batch_size"] = int(predict_batch_size)
    return _run_snakemake(_INFER_SNAKEFILE, cores, conf,
                          overwrite=overwrite, dry_run=dry_run, unlock=unlock)


def run_local_infer_only(
    input_csv: str,
    *,
    cores: int,
    bundle_path: str,
    cubes_per_task: int = 1,
    overwrite: bool = False,
    predict_batch_size: int | None = None,
    skip_nan: bool = True,
    dry_run: bool = False,
    unlock: bool = False,
) -> subprocess.CompletedProcess:
    """Local runner for **infer-only** fan-out over pre-built datacubes (spec 22) — the replacement
    for `engine.run_local`'s retired `mp.Pool`.

    `input_csv` has `datacube_filepath`, `output_filepath`. `cores` = how many groups run at once
    (Snakemake — the only parallel primitive); `cubes_per_task` groups K cubes per sequential job to
    amortise the one-per-job bundle load. `overwrite` forces recompute (`--forceall`); otherwise
    per-group sentinels + the task's skip-existing make it resumable. Azure Batch (P4) dispatches
    this same task.
    """
    conf = {
        "input_csv": input_csv,
        "bundle_path": bundle_path,
        "cubes_per_task": max(int(cubes_per_task), 1),
        "skip_nan": 1 if skip_nan else 0,
        "overwrite": 1 if overwrite else 0,
    }
    if predict_batch_size is not None:
        conf["predict_batch_size"] = int(predict_batch_size)
    return _run_snakemake(_INFER_ONLY_SNAKEFILE, cores, conf,
                          overwrite=overwrite, dry_run=dry_run, unlock=unlock)


def _run_snakemake(snakefile_rel, cores, conf, *, overwrite=False, dry_run=False, unlock=False):
    """Build + run a snakemake command over `conf` (shared by the inference runners)."""
    cmd = [
        sys.executable, "-m", "snakemake",
        "--snakefile", _snakefile_path(snakefile_rel),
        "--cores", str(cores),
        "--config", *[f"{k}={v}" for k, v in conf.items()],
    ]
    if overwrite:
        cmd.append("--forceall")
    if dry_run:
        cmd.append("--dry-run")
    if unlock:
        cmd.append("--unlock")
    returncode = _run(cmd)
    return subprocess.CompletedProcess(args=cmd, returncode=returncode)


# Phase 2 / P4 (not implemented in v1): an azure-batch runner dispatches the SAME
# fsd.workflows.task / fsd.workflows.infer_task / fsd.workflows.infer_only_task CLI on pool VMs.
# def run_azure_batch(input_csv, *, pool_id, ...): ...
