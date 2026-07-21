"""Runner seam — execute the datacube task across many work-units.

Spec: specs/08-workflows.md, specs/10-storage-and-scale.md, specs/36-scale-runner.md.

v1 backend: local (Snakemake). P2 backend: Azure ML (`run_aml`, spec 36) -- shards
`input_csv` and dispatches each shard onto an AML cluster, where it calls back into
this same module's `run_local`. Same interface; runner is swappable.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
import uuid
from importlib.resources import files

import pandas as pd

from fsd.storage import fs

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


# --- P2: the Azure ML runner (spec 36) ---------------------------------------

_TERMINAL_JOB_STATUSES = {"Completed", "Failed", "Canceled"}


def _import_aml_command():
    """Lazy handle to `azure.ai.ml.command` (D3 invariant 3: the sole azure-ai-ml
    import in `fsd/`, inside a function -- `import fsd` never needs the extra). Indirected
    through this helper so the AML job-builder is part of `run_aml`'s injection boundary:
    tests substitute a fake and never require the `[aml]` extra ("no test may require
    Azure", spec 36 §7). Production behaviour is unchanged -- a real `runner="aml"` with
    the extra absent still raises ImportError here, exactly as a direct import would."""
    from azure.ai.ml import command

    return command


def shard_units(units: list, n_shards: int) -> list[list]:
    """Partition `units` into up to `n_shards` non-empty groups, round-robin (spec 36
    D2 / test 1). A partition: every unit appears in exactly one shard. `n_shards` >
    `len(units)` degrades to `len(units)` non-empty shards (no empty shard is ever
    produced)."""
    n_shards = max(int(n_shards), 1)
    n_groups = min(n_shards, len(units)) or 1
    groups: list[list] = [[] for _ in range(n_groups)]
    for i, unit in enumerate(units):
        groups[i % n_groups].append(unit)
    return [g for g in groups if g]


def _aml_preflight(ml_client, *, cluster: str, environment: str, root: str,
                    input_csv: str, n_shards: int | None) -> None:
    """D10: know before you spend. Cheap checks that turn a 20-minutes-later cluster
    failure into an instant one."""
    errs = []
    try:
        compute = ml_client.compute.get(cluster)
        state = getattr(compute, "provisioning_state", None)
        if state not in (None, "Succeeded"):
            errs.append(f"cluster {cluster!r} not ready (provisioning_state={state!r}).")
    except Exception as exc:  # noqa: BLE001 - report, don't crash on a preflight check
        errs.append(f"cluster {cluster!r} not found or unreachable: {exc}")
    try:
        env_name, _, env_version = environment.partition(":")
        if env_version:
            ml_client.environments.get(name=env_name, version=env_version)
        else:
            ml_client.environments.get(name=env_name, label="latest")
    except Exception as exc:  # noqa: BLE001
        errs.append(f"environment {environment!r} does not resolve: {exc}")
    try:
        fs.makedirs(root)
        probe = f"{root.rstrip('/')}/.fsd_preflight_{uuid.uuid4().hex}"
        with fs.open(probe, "w") as f:
            f.write("preflight")
        fs.rm(probe)
    except Exception as exc:  # noqa: BLE001
        errs.append(f"storage root {root!r} not reachable/writable from the driver: {exc}")
    if not fs.exists(input_csv):
        errs.append(f"input_csv does not exist: {input_csv!r}")
    else:
        with fs.open(input_csv, "r") as f:
            n_units = len(pd.read_csv(f))
        if n_units == 0:
            errs.append(f"input_csv is empty: {input_csv!r}")
    if n_shards is not None and int(n_shards) < 1:
        errs.append(f"n_shards must be >= 1, got {n_shards!r}.")
    if errs:
        raise ValueError("run_aml preflight failed:\n  - " + "\n  - ".join(errs))


def run_aml(
    input_csv: str,
    *,
    cluster: str,
    environment: str,
    root: str,
    identity_client_id: str,
    run_id: str | None = None,
    n_shards: int | None = None,
    cores: int = 16,
    ml_client=None,
    subscription_id: str | None = None,
    resource_group_name: str | None = None,
    workspace_name: str | None = None,
    poll_interval_seconds: int = 30,
) -> dict:
    """AML runner (spec 36 D2/D3/D9/D10): shard `input_csv`, submit one command job per
    shard onto `cluster`, wait, aggregate `_status/<k>.json`, raise on any failure.

    Each dispatched unit is a **shard** (D2), not a cube: the job runs
    `python -m fsd.workflows.shard <shard_csv_url> --cores <cores>`, which calls back
    into this module's `run_local` -- the same Snakemake orchestration a laptop runs.
    No AML-specific pipeline code exists; only this dispatcher knows about AML.

    `identity_client_id` (D4) is set as the job's `AZURE_CLIENT_ID` env var -- the AML
    cluster carries only a user-assigned managed identity, which is never selected
    implicitly, so `fsd/storage/azure.py`'s bare `DefaultAzureCredential()` needs this
    to authenticate on the node. **fsd never hardcodes it** (a concrete `rise` identity
    id has no business in a public repo) -- the caller resolves it (e.g. via
    `az identity show --query clientId`) and passes it in.

    `ml_client` is the test/injection seam (D3 invariant 3): pass a fake with
    `.compute.get`, `.environments.get`, `.jobs.create_or_update`, `.jobs.get` to avoid
    any network call; when omitted, a real `azure.ai.ml.MLClient` is constructed here
    (lazy import -- this is the only place in `fsd/` that imports `azure-ai-ml`).

    `root` is the storage root (any `fsd.storage` URL, typically `abfss://...`) under
    which `runs/<run_id>/{shards,_status}/...` (D6) is laid out. `n_shards` defaults to
    the cluster's `max_instances` (D2).
    """
    if ml_client is None:
        from azure.ai.ml import MLClient
        from azure.identity import DefaultAzureCredential

        ml_client = MLClient(
            DefaultAzureCredential(), subscription_id, resource_group_name, workspace_name
        )

    _aml_preflight(ml_client, cluster=cluster, environment=environment, root=root,
                    input_csv=input_csv, n_shards=n_shards)

    if n_shards is None:
        compute = ml_client.compute.get(cluster)
        n_shards = getattr(compute, "max_instances", None) or 1

    run_id = run_id or pd.Timestamp.now(tz="UTC").strftime("%Y%m%dT%H%M%SZ")
    run_root = f"{root.rstrip('/')}/runs/{run_id}"

    with fs.open(input_csv, "r") as f:
        units = pd.read_csv(f).to_dict("records")
    shards = shard_units(units, n_shards)

    aml_command = _import_aml_command()

    job_names: dict[int, str] = {}
    for k, rows in enumerate(shards):
        shard_url = f"{run_root}/shards/{k}.csv"
        with fs.open(shard_url, "w") as f:
            pd.DataFrame(rows).to_csv(f, index=False)

        job = aml_command(
            command=f"python -m fsd.workflows.shard {shard_url} --cores {cores}",
            environment=environment,
            compute=cluster,
            environment_variables={"AZURE_CLIENT_ID": identity_client_id},
            display_name=f"fsd-shard-{run_id}-{k}",
            experiment_name=f"fsd-{run_id}",
        )
        submitted = ml_client.jobs.create_or_update(job)
        job_names[k] = submitted.name

    statuses: dict[int, str] = {}
    while True:
        statuses = {k: ml_client.jobs.get(name).status for k, name in job_names.items()}
        if all(s in _TERMINAL_JOB_STATUSES for s in statuses.values()):
            break
        time.sleep(poll_interval_seconds)

    failed = sorted(k for k, s in statuses.items() if s != "Completed")
    shard_reports: dict[int, dict] = {}
    for k in job_names:
        status_url = f"{run_root}/_status/{k}.json"
        if fs.exists(status_url):
            with fs.open(status_url, "r") as f:
                report = json.load(f)
            shard_reports[k] = report
            if report.get("status") != "ok" and k not in failed:
                failed.append(k)
        else:
            shard_reports[k] = {"shard": k, "aml_job_status": statuses[k]}
    failed = sorted(set(failed))

    if failed:
        raise RuntimeError(f"run_aml: shard(s) failed: {failed} (run_id={run_id!r})")

    return {"run_id": run_id, "n_shards": len(shards), "job_statuses": statuses,
            "shards": shard_reports}
