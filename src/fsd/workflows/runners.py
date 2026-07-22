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

from fsd import config
from fsd import secrets as _secrets
from fsd.sources import mpc as _mpc
from fsd.sources.cdse import CdseCredentials as _CdseCredentials
from fsd.sources.cdse import query_catalog as _cdse_query_catalog
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


def _aml_preflight_common(ml_client, *, cluster: str, environment: str, root: str) -> list[str]:
    """Cluster/environment/storage-root checks shared by `run_aml` (spec 36 D10)
    and `run_aml_download` (spec 37 D7). Returns error strings; never raises --
    each caller aggregates alongside its own source-specific checks."""
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
    return errs


def _aml_preflight(ml_client, *, cluster: str, environment: str, root: str,
                    input_csv: str, n_shards: int | None) -> None:
    """D10: know before you spend. Cheap checks that turn a 20-minutes-later cluster
    failure into an instant one."""
    errs = _aml_preflight_common(ml_client, cluster=cluster, environment=environment, root=root)
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


def _aml_download_preflight(
    ml_client, *, cluster: str, environment: str, root: str, source: str,
    n_assets: int, vault_url: str | None, secret_name: str | None,
    get_secret, remaining_quota_gb: float | None, estimated_gb: float | None,
) -> list[str]:
    """D7: know before you spend, for a download dispatch. Cluster/environment/root
    (shared, `_aml_preflight_common`) + discovery non-emptiness + (CDSE-only) the KV
    secret resolves/parses and its S3 keys are not expired. Raises on any hard
    failure; returns a (possibly empty) list of **warnings** (non-fatal) -- today
    just the CDSE quota estimate (D1/D7)."""
    errs = _aml_preflight_common(ml_client, cluster=cluster, environment=environment, root=root)
    if n_assets < 1:
        errs.append("discovery matched 0 assets for this roi/date-window.")
    warnings: list[str] = []
    if source == "cdse":
        if not vault_url or not secret_name:
            errs.append("source='cdse' requires vault_url and secret_name (D5 Key Vault creds).")
        else:
            try:
                creds = _CdseCredentials.from_json_str(get_secret(vault_url, secret_name))
                creds.require_s3()
                if creds.is_expired():
                    errs.append(
                        f"CDSE S3 keys expired (s3_keys_expire={creds.s3_keys_expire!r})."
                    )
            except Exception as exc:  # noqa: BLE001 - report, don't crash on a preflight check
                errs.append(
                    f"Key Vault secret {secret_name!r} at {vault_url!r} did not resolve/parse: {exc}"
                )
        if remaining_quota_gb is not None and estimated_gb is not None and estimated_gb > remaining_quota_gb:
            warnings.append(
                f"estimated download (~{estimated_gb:.0f} GB) exceeds the ~{remaining_quota_gb:.0f} GB "
                "remaining CDSE 30-day quota -- expect throttling to 1 MB/s partway through "
                "(https://documentation.dataspace.copernicus.eu/Quotas.html)."
            )
    if errs:
        raise ValueError("run_aml_download preflight failed:\n  - " + "\n  - ".join(errs))
    return warnings


def _aml_submit_and_wait(
    ml_client, jobs: dict, run_root: str, run_id: str, *, poll_interval_seconds: int = 30,
) -> dict:
    """Submit each prebuilt AML `command(...)` job in `jobs` (`{k: job}`), wait for
    all to reach a terminal status, aggregate `<run_root>/_status/<k>.json`, and
    raise on any failed/circuit-tripped job. Shared by `run_aml` (spec 36 -- one job
    per datacube shard) and `run_aml_download` (spec 37 -- one CDSE job or N MPC
    shard jobs, D1/D9); the only difference between the two callers is how `jobs`
    gets built, not how submission/waiting/aggregation works."""
    job_names: dict[int, str] = {}
    for k, job in jobs.items():
        submitted = ml_client.jobs.create_or_update(job)
        job_names[k] = submitted.name

    statuses: dict[int, str] = {}
    while True:
        statuses = {k: ml_client.jobs.get(name).status for k, name in job_names.items()}
        if all(s in _TERMINAL_JOB_STATUSES for s in statuses.values()):
            break
        time.sleep(poll_interval_seconds)

    failed = [k for k, s in statuses.items() if s != "Completed"]
    reports: dict[int, dict] = {}
    for k in job_names:
        status_url = f"{run_root}/_status/{k}.json"
        if fs.exists(status_url):
            with fs.open(status_url, "r") as f:
                report = json.load(f)
            reports[k] = report
            if (report.get("status") != "ok" or report.get("circuit_tripped")) and k not in failed:
                failed.append(k)
        else:
            reports[k] = {"unit": k, "aml_job_status": statuses[k]}
    failed = sorted(set(failed))

    if failed:
        raise RuntimeError(f"job(s)/shard(s) failed: {failed} (run_id={run_id!r})")

    return {"run_id": run_id, "job_statuses": statuses, "reports": reports}


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

    jobs: dict[int, object] = {}
    for k, rows in enumerate(shards):
        shard_url = f"{run_root}/shards/{k}.csv"
        with fs.open(shard_url, "w") as f:
            pd.DataFrame(rows).to_csv(f, index=False)

        jobs[k] = aml_command(
            command=f"python -m fsd.workflows.shard {shard_url} --cores {cores}",
            environment=environment,
            compute=cluster,
            environment_variables={"AZURE_CLIENT_ID": identity_client_id},
            display_name=f"fsd-shard-{run_id}-{k}",
            experiment_name=f"fsd-{run_id}",
        )

    result = _aml_submit_and_wait(ml_client, jobs, run_root, run_id,
                                   poll_interval_seconds=poll_interval_seconds)
    return {"run_id": run_id, "n_shards": len(shards),
            "job_statuses": result["job_statuses"], "shards": result["reports"]}


# --- P2: the Azure ML download dispatcher (spec 37) --------------------------


def _import_command_job_limits():
    """Lazy handle to `azure.ai.ml.entities.CommandJobLimits` (D6) -- same
    injection-boundary pattern as `_import_aml_command` (spec 36 D3 invariant 3),
    so tests substitute a fake and never require the `[aml]` extra."""
    from azure.ai.ml.entities import CommandJobLimits

    return CommandJobLimits


def _estimate_timeout_seconds(
    estimated_gb: float, *, conservative_mb_per_s: float = 10.0, floor_seconds: int = 1800,
) -> int:
    """D6: size an explicit job timeout from a GB estimate at a conservative
    throughput (well under CDSE's 4x20 MB/s ceiling and MPC's blob throughput, so a
    healthy transfer never trips it), with a floor so a tiny/empty estimate still
    gets a sane timeout."""
    return max(int(estimated_gb * 1024 / conservative_mb_per_s), floor_seconds)


def _iso(dt) -> str:
    return pd.Timestamp(dt).isoformat()


def run_aml_download(
    roi: str,
    startdate,
    enddate,
    bands: list[str],
    dst_folderpath: str,
    catalog_filepath: str,
    *,
    source: str,
    cluster: str,
    environment: str,
    root: str,
    identity_client_id: str,
    max_tiles: int,
    vault_url: str | None = None,
    secret_name: str | None = None,
    max_cloudcover: float | None = None,
    cog: bool = True,
    n_shards: int | None = None,
    remaining_quota_gb: float | None = None,
    timeout_seconds: int | None = None,
    run_id: str | None = None,
    ml_client=None,
    subscription_id: str | None = None,
    resource_group_name: str | None = None,
    workspace_name: str | None = None,
    poll_interval_seconds: int = 30,
    get_secret=None,
) -> dict:
    """AML download dispatcher (spec 37 D1/D2/D3/D5/D6/D7/D9): per-source dispatch
    shape -- CDSE submits **exactly one** whole-ROI job; MPC discovers on the
    driver, `shard_units` the asset list, and submits **N** per-shard jobs. Both
    wait, aggregate `_status/<k>.json`, and raise on any failed/circuit-tripped job
    (`_aml_submit_and_wait`, shared with `run_aml`).

    `roi` must be a url (any `fsd.storage`/geopandas-readable path) rather than an
    in-memory GeoDataFrame -- the job that reads it runs on a different machine.

    `vault_url`/`secret_name` (D5, CDSE only) are Key Vault coordinates -- caller-
    supplied, never a concrete `rise` identifier hardcoded here (public repo).
    Secrets never ride in the job spec: only these non-secret names go into the
    command args; the node reads the value itself via `fsd.secrets.get_secret`
    (substitutable here via `get_secret`, the D5 test seam) at run time. The same
    `identity_client_id` (D4) that authorises blob also authorises Key Vault.

    `ml_client` is the test/injection seam (D3 invariant 3, mirrors `run_aml`): pass
    a fake with `.compute.get`, `.environments.get`, `.jobs.create_or_update`,
    `.jobs.get` to avoid any network call.
    """
    if source not in ("cdse", "mpc"):
        raise ValueError(f"source={source!r} must be one of 'cdse', 'mpc'.")

    get_secret = get_secret or _secrets.get_secret

    if ml_client is None:
        from azure.ai.ml import MLClient
        from azure.identity import DefaultAzureCredential

        ml_client = MLClient(
            DefaultAzureCredential(), subscription_id, resource_group_name, workspace_name
        )

    run_id = run_id or pd.Timestamp.now(tz="UTC").strftime("%Y%m%dT%H%M%SZ")
    run_root = f"{root.rstrip('/')}/runs/{run_id}"
    aml_command = _import_aml_command()
    limits_cls = _import_command_job_limits()

    if source == "cdse":
        tiles = _cdse_query_catalog(roi, startdate, enddate, max_cloudcover=max_cloudcover)
        n_assets = len(tiles)
        estimated_gb = len(tiles) * config.APPROX_GB_PER_TILE

        _aml_download_preflight(
            ml_client, cluster=cluster, environment=environment, root=root,
            source="cdse", n_assets=n_assets, vault_url=vault_url, secret_name=secret_name,
            get_secret=get_secret, remaining_quota_gb=remaining_quota_gb, estimated_gb=estimated_gb,
        )

        timeout = timeout_seconds or _estimate_timeout_seconds(estimated_gb)
        command = (
            f"python -m fsd.workflows.download --roi {roi} "
            f"--startdate {_iso(startdate)} --enddate {_iso(enddate)} "
            f"--bands {','.join(bands)} --dst {dst_folderpath} --catalog {catalog_filepath} "
            f"--max-tiles {max_tiles} --vault-url {vault_url} --secret-name {secret_name} "
            f"--status-url {run_root}/_status/0.json"
        )
        if max_cloudcover is not None:
            command += f" --max-cloudcover {max_cloudcover}"
        if not cog:
            command += " --no-cog"

        jobs = {0: aml_command(
            command=command, environment=environment, compute=cluster,
            environment_variables={"AZURE_CLIENT_ID": identity_client_id},
            display_name=f"fsd-download-cdse-{run_id}", experiment_name=f"fsd-download-{run_id}",
            limits=limits_cls(timeout=timeout),
        )}
    else:
        rows = _mpc.discover_shard_rows(
            roi, startdate, enddate, bands, dst_folderpath, max_cloudcover=max_cloudcover
        )
        n_assets = len(rows)

        _aml_download_preflight(
            ml_client, cluster=cluster, environment=environment, root=root,
            source="mpc", n_assets=n_assets, vault_url=vault_url, secret_name=secret_name,
            get_secret=get_secret, remaining_quota_gb=None, estimated_gb=None,
        )

        if n_shards is None:
            compute = ml_client.compute.get(cluster)
            n_shards = getattr(compute, "max_instances", None) or 1
        shards = shard_units(rows, n_shards)
        timeout = timeout_seconds or _estimate_timeout_seconds(
            n_assets * config.APPROX_GB_PER_TILE / max(len(bands), 1)
        )

        jobs = {}
        for k, shard_rows in enumerate(shards):
            shard_url = f"{run_root}/shards/{k}.csv"
            with fs.open(shard_url, "w") as f:
                pd.DataFrame(shard_rows).to_csv(f, index=False)

            jobs[k] = aml_command(
                command=(
                    f"python -m fsd.workflows.download --shard {shard_url} "
                    f"--dst {dst_folderpath} --catalog {catalog_filepath} "
                    f"--status-url {run_root}/_status/{k}.json"
                ),
                environment=environment, compute=cluster,
                environment_variables={"AZURE_CLIENT_ID": identity_client_id},
                display_name=f"fsd-download-mpc-{run_id}-{k}",
                experiment_name=f"fsd-download-{run_id}",
                limits=limits_cls(timeout=timeout),
            )

    result = _aml_submit_and_wait(ml_client, jobs, run_root, run_id,
                                   poll_interval_seconds=poll_interval_seconds)
    return {"run_id": run_id, "source": source, "n_jobs": len(jobs),
            "job_statuses": result["job_statuses"], "reports": result["reports"]}
