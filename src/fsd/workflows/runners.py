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
from fsd.catalog.catalog import TileCatalog as _TileCatalog
from fsd.model import bundle as _bundle
from fsd.sources import mpc as _mpc
from fsd.sources.cdse import CdseCredentials as _CdseCredentials
from fsd.sources.cdse import query_catalog as _cdse_query_catalog
from fsd.storage import fs

_SNAKEFILE = "workflows/_snakefiles/create_datacube/Snakefile"
_INFER_SNAKEFILE = "workflows/_snakefiles/create_inference/Snakefile"
_INFER_ONLY_SNAKEFILE = "workflows/_snakefiles/infer_only/Snakefile"

# D13 (spec 38, TODO #53): a unit's content identity -- kept in sync with
# `create_datacube._UNIT_IDENTITY_COLS` (not imported from there: `create_datacube`
# already imports this module, and importing back would be circular).
_UNIT_IDENTITY_COLS = (
    "id", "startdate", "enddate", "bands", "mosaic_days", "mosaic_scheme", "scl_mask_classes",
)


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
    cubes_per_task: int = 1,
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

    Same seam as `run_local` — `cores` = how many groups run at once — but each job shells one
    `fsd.workflows.infer_task` group process (build each cell's datacube, then infer ->
    output.tif) instead of the build-only task. `bundle_path` is the model the workers reload.
    `cubes_per_task` (spec 38 D7, closes TODO #25's root cause: this used to be silently
    dropped) groups K cells per job so the bundle loads once per group, not once per cell --
    default 1 (today's per-cell behaviour). `overwrite` forces a recompute of every cell
    (`--forceall` **and** `infer_task`'s own per-cell skip is bypassed, config `overwrite=1`);
    otherwise each cell's `output.tif` existence (D6) makes it resumable, decoupled from group
    size. Azure Batch (P4) dispatches this same task; only this runner is swapped.

    D13: raises before dispatch if `input_csv` has two distinct-content rows sharing an
    `export_folderpath` (a malformed manifest -- same exposure as `run_aml`/`run_aml_inference`).
    """
    with fs.open(input_csv, "r") as f:
        _dupe_errs = _duplicate_unit_errors(pd.read_csv(f).to_dict("records"))
    if _dupe_errs:
        raise ValueError("run_local_inference preflight failed:\n  - " + "\n  - ".join(_dupe_errs))

    conf = {
        "input_csv": input_csv,
        "bundle_path": bundle_path,
        "cubes_per_task": max(int(cubes_per_task), 1),
        "skip_nan": 1 if skip_nan else 0,
        "overwrite": 1 if overwrite else 0,
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


def _duplicate_export_folderpaths(rows: list[dict]) -> list[str]:
    """D13 (spec 38, TODO #53): `export_folderpath` is keyed by `id` ALONE
    (`create_datacube.setup`), a narrower key than the content-identity dedupe
    (`_UNIT_IDENTITY_COLS`) -- so two rows can pass the dedupe (distinct content) and
    still collide on the SAME folder (a malformed manifest: which content should that
    folder hold?). Returns the offending `export_folderpath`s, or `[]` if none."""
    seen: dict[str, set] = {}
    for r in rows:
        identity = tuple(str(r.get(c)) for c in _UNIT_IDENTITY_COLS)
        seen.setdefault(str(r.get("export_folderpath")), set()).add(identity)
    return sorted(p for p, ids in seen.items() if len(ids) > 1)


def _duplicate_unit_errors(rows: list[dict]) -> list[str]:
    """D13 aggregatable-error form of `_duplicate_export_folderpaths`, shared by every
    dispatcher (`run_aml`, `run_aml_inference`, `run_local_inference`) -- same exposure."""
    dupes = _duplicate_export_folderpaths(rows)
    if not dupes:
        return []
    shown = dupes[:5]
    more = f" (+{len(dupes) - 5} more)" if len(dupes) > 5 else ""
    return [
        "duplicate unit dispatch (D13): distinct-content rows share an export_folderpath "
        f"-- malformed manifest: {shown}{more}"
    ]


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
            rows = pd.read_csv(f).to_dict("records")
        if len(rows) == 0:
            errs.append(f"input_csv is empty: {input_csv!r}")
        else:
            errs += _duplicate_unit_errors(rows)
    if n_shards is not None and int(n_shards) < 1:
        errs.append(f"n_shards must be >= 1, got {n_shards!r}.")
    if errs:
        raise ValueError("run_aml preflight failed:\n  - " + "\n  - ".join(errs))


def _aml_download_preflight(
    ml_client, *, cluster: str, environment: str, root: str, source: str,
    n_assets: int, vault_url: str | None, secret_name: str | None,
    get_secret, remaining_quota_gb: float | None, estimated_gb: float | None,
    creds_url: str | None = None,
    n_tiles: int | None = None,
    max_tiles: int | None = None,
) -> list[str]:
    """D7: know before you spend, for a download dispatch. Cluster/environment/root
    (shared, `_aml_preflight_common`) + discovery non-emptiness + the `max_tiles`
    guardrail + (CDSE-only) the supplied creds source resolves/parses and its S3 keys
    are not expired. Raises on any hard failure; returns a (possibly empty) list of
    **warnings** (non-fatal) -- today just the CDSE quota estimate (D1/D7).

    D5 REVISED: CDSE creds come from **exactly one** of two mutually exclusive
    sources -- Key Vault (`vault_url`+`secret_name`) or a blob JSON (`creds_url`).
    Neither or both supplied is a hard preflight error. `source='mpc'` is anonymous
    and refuses all three (TODO #49).

    `max_tiles` is enforced **here, on the driver**, for both sources, mirroring the
    guard the local paths already apply (`sources/mpc.py`, `sources/cdse.py`): the
    runner must not change what a call means (spec 36 D3). It previously reached
    only CDSE -- via `--max-tiles` on the node, i.e. after the cluster had already
    spun up -- and the MPC path dropped it entirely, so an `api.download(source=
    'mpc', max_tiles=N)` that raises locally would silently download everything on
    AML. Checking at dispatch time also fails before a single node starts."""
    errs = _aml_preflight_common(ml_client, cluster=cluster, environment=environment, root=root)
    if n_assets < 1:
        errs.append("discovery matched 0 assets for this roi/date-window.")
    if n_tiles is not None and max_tiles is not None and n_tiles > max_tiles:
        errs.append(
            f"{n_tiles} matched tiles exceed max_tiles={max_tiles}. Narrow the query "
            "or raise max_tiles."
        )
    warnings: list[str] = []
    if source == "cdse":
        kv_given = bool(vault_url) or bool(secret_name)
        blob_given = bool(creds_url)
        if kv_given and blob_given:
            errs.append(
                "source='cdse' requires exactly one CDSE creds source, got both: "
                "vault_url/secret_name (Key Vault) and creds_url (blob JSON)."
            )
        elif not kv_given and not blob_given:
            errs.append(
                "source='cdse' requires exactly one CDSE creds source: "
                "vault_url+secret_name (Key Vault) or creds_url (blob JSON)."
            )
        elif kv_given and not (vault_url and secret_name):
            errs.append("source='cdse' requires both vault_url and secret_name (D5 Key Vault creds).")
        else:
            try:
                if blob_given:
                    creds = _CdseCredentials.from_json(creds_url)
                else:
                    creds = _CdseCredentials.from_json_str(get_secret(vault_url, secret_name))
                creds.require_s3()
                if creds.is_expired():
                    errs.append(
                        f"CDSE S3 keys expired (s3_keys_expire={creds.s3_keys_expire!r})."
                    )
            except Exception as exc:  # noqa: BLE001 - report, don't crash on a preflight check
                source_desc = f"blob {creds_url!r}" if blob_given else \
                    f"Key Vault secret {secret_name!r} at {vault_url!r}"
                errs.append(f"CDSE creds ({source_desc}) did not resolve/parse: {exc}")
        if remaining_quota_gb is not None and estimated_gb is not None and estimated_gb > remaining_quota_gb:
            warnings.append(
                f"estimated download (~{estimated_gb:.0f} GB) exceeds the ~{remaining_quota_gb:.0f} GB "
                "remaining CDSE 30-day quota -- expect throttling to 1 MB/s partway through "
                "(https://documentation.dataspace.copernicus.eu/Quotas.html)."
            )
    else:
        # MPC is anonymous (D4/D5): it reads no credentials at all, so a creds
        # argument here is not merely inert -- `creds_url` would put the secret on
        # blob for the whole run in exchange for nothing. Refuse it rather than
        # ignore it (TODO #49; found when a hand-written Phase 3 script did exactly
        # this against a full-year archive run).
        supplied = [
            name for name, value in (
                ("creds_url", creds_url), ("vault_url", vault_url), ("secret_name", secret_name),
            ) if value
        ]
        if supplied:
            errs.append(
                f"source='mpc' is anonymous and reads no credentials, but {', '.join(supplied)} "
                "was supplied -- remove it. (Passing creds_url to an MPC run stages the secret on "
                "blob for the run's duration and never reads it.)"
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


# --- P4: the Azure ML inference dispatcher (spec 38) --------------------------


def _stage_bundle(bundle_path: str, dst_url: str) -> str:
    """D3: stage a bundle (local, or already on some `fsd.storage` backend) to `dst_url`
    -- copy `bundle.json` + every file its `artifacts` map names. No directory
    listing/new primitive: the manifest already enumerates every file the bundle needs
    (spec 18 §3.4 -- relative hrefs, no absolute path baked in), so this is the same
    manifest-driven shape the node uses to fetch it back down (`infer_shard.
    fetch_bundle_to_scratch`). Returns `dst_url`."""
    manifest = _bundle.read_spec(bundle_path)
    with fs.open(os.path.join(bundle_path, _bundle.BUNDLE_MANIFEST), "r") as f:
        raw = f.read()
    with fs.open(os.path.join(dst_url, _bundle.BUNDLE_MANIFEST), "w") as f:
        f.write(raw)
    for rel in manifest.get("artifacts", {}).values():
        fs.transfer(os.path.join(bundle_path, rel), os.path.join(dst_url, rel))
    return dst_url


def _aml_inference_preflight(
    ml_client, *, cluster: str, environment: str, root: str,
    input_csv: str, n_shards: int | None, max_cells: int | None,
) -> None:
    """D11: every check that CAN run on the driver MUST run on the driver, before any
    AML job is submitted (node cold-start is 40-380s, TODO #48) -- cluster/environment/
    root (shared, `_aml_preflight_common`), input_csv non-empty, the D13 duplicate-unit
    guard, and the `max_cells` guardrail (mirrors spec 37's `max_tiles`: refuse an ROI
    that tiles into more cells than intended, before dispatching thousands of jobs).
    Model-spec checks (bands/T) already run in `api._run_inference_roi`'s own preflight,
    ahead of this call (hoisted, not duplicated here)."""
    errs = _aml_preflight_common(ml_client, cluster=cluster, environment=environment, root=root)
    if not fs.exists(input_csv):
        errs.append(f"input_csv does not exist: {input_csv!r}")
    else:
        with fs.open(input_csv, "r") as f:
            rows = pd.read_csv(f).to_dict("records")
        if len(rows) == 0:
            errs.append(f"input_csv is empty: {input_csv!r}")
        else:
            errs += _duplicate_unit_errors(rows)
            if max_cells is not None and len(rows) > max_cells:
                errs.append(
                    f"{len(rows)} cells exceed max_cells={max_cells}. Narrow the ROI or "
                    "raise max_cells."
                )
    if n_shards is not None and int(n_shards) < 1:
        errs.append(f"n_shards must be >= 1, got {n_shards!r}.")
    if errs:
        raise ValueError("run_aml_inference preflight failed:\n  - " + "\n  - ".join(errs))


def run_aml_inference(
    input_csv: str,
    bundle_path: str,
    *,
    cluster: str,
    environment: str,
    root: str,
    identity_client_id: str,
    run_id: str | None = None,
    n_shards: int | None = None,
    cores: int = 1,
    cubes_per_task: int | None = None,
    predict_batch_size: int | None = None,
    skip_nan: bool = True,
    overwrite: bool = False,
    max_cells: int | None = None,
    skip_smoke: bool = False,
    ml_client=None,
    subscription_id: str | None = None,
    resource_group_name: str | None = None,
    workspace_name: str | None = None,
    poll_interval_seconds: int = 30,
) -> dict:
    """AML inference dispatcher (spec 38 D1/D1a/D2/D11): the **thin step-4 swap** over
    the spec-21 per-cell build+infer unit. Receives the already-produced `input_csv`
    (tiling + `setup` already ran on the driver -- `api._run_inference_roi` steps 1-3)
    and `bundle_path`, and does only: stage the bundle to blob (D3) -> shard the cells
    (reusing `shard_units`, same self-balancing dispatch spec 36 proved) -> submit one
    job per shard running `python -m fsd.workflows.infer_shard` -> wait -> aggregate
    `_status/<k>.json` -> raise on any failure. Mirrors `run_aml` almost exactly; the
    only difference is what each node runs and that a bundle is staged first.

    `identity_client_id`/`ml_client`/`root` follow spec 36 D4'/D3 exactly (see `run_aml`'s
    docstring) -- no storage-seam or identity-mechanism change for inference.

    `skip_smoke=False` (default, D11) runs a one-node adapter-import smoke BEFORE the
    N-node fan-out -- the only preflight check that needs a real node (the driver's venv
    is not guaranteed to mirror the inference Environment, ADR 0002); pass `True` once an
    Environment is already proven, to skip the extra node spin-up on repeat runs.
    """
    if ml_client is None:
        from azure.ai.ml import MLClient
        from azure.identity import DefaultAzureCredential

        ml_client = MLClient(
            DefaultAzureCredential(), subscription_id, resource_group_name, workspace_name
        )

    _aml_inference_preflight(ml_client, cluster=cluster, environment=environment, root=root,
                             input_csv=input_csv, n_shards=n_shards, max_cells=max_cells)

    if n_shards is None:
        compute = ml_client.compute.get(cluster)
        n_shards = getattr(compute, "max_instances", None) or 1

    run_id = run_id or pd.Timestamp.now(tz="UTC").strftime("%Y%m%dT%H%M%SZ")
    run_root = f"{root.rstrip('/')}/runs/{run_id}"

    bundle_url = _stage_bundle(bundle_path, f"{run_root}/_bundle")

    aml_command = _import_aml_command()

    if not skip_smoke:
        smoke_status_url = f"{run_root}/_status/smoke.json"
        smoke_job = aml_command(
            command=(
                f"python -m fsd.workflows.adapter_smoke {bundle_url} "
                f"--status-url {smoke_status_url}"
            ),
            environment=environment, compute=cluster,
            environment_variables={"AZURE_CLIENT_ID": identity_client_id},
            display_name=f"fsd-infer-smoke-{run_id}", experiment_name=f"fsd-infer-{run_id}",
        )
        _aml_submit_and_wait(ml_client, {"smoke": smoke_job}, run_root, f"{run_id}-smoke",
                             poll_interval_seconds=poll_interval_seconds)

    with fs.open(input_csv, "r") as f:
        units = pd.read_csv(f).to_dict("records")
    shards = shard_units(units, n_shards)

    jobs: dict[int, object] = {}
    for k, rows in enumerate(shards):
        shard_url = f"{run_root}/shards/{k}.csv"
        with fs.open(shard_url, "w") as f:
            pd.DataFrame(rows).to_csv(f, index=False)

        cmd = f"python -m fsd.workflows.infer_shard {shard_url} {bundle_url} --cores {cores}"
        if cubes_per_task:
            cmd += f" --cubes-per-task {cubes_per_task}"
        if predict_batch_size is not None:
            cmd += f" --predict-batch-size {predict_batch_size}"
        if not skip_nan:
            cmd += " --no-skip-nan"
        if overwrite:
            cmd += " --overwrite"

        jobs[k] = aml_command(
            command=cmd,
            environment=environment,
            compute=cluster,
            environment_variables={"AZURE_CLIENT_ID": identity_client_id},
            display_name=f"fsd-infer-{run_id}-{k}",
            experiment_name=f"fsd-infer-{run_id}",
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
    creds_url: str | None = None,
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

    `vault_url`/`secret_name` (D5, CDSE only) are Key Vault coordinates, and
    `creds_url` (D5 REVISED, CDSE only) is a blob JSON location -- **exactly one**
    of the two CDSE creds sources is required (mutually exclusive; preflight errs
    on neither and on both). Neither is a concrete `rise` identifier hardcoded here
    (public repo) -- caller-supplied. Secrets never ride in the job spec: only
    these non-secret names/locations go into the command args; the node reads the
    value itself at run time -- via `fsd.secrets.get_secret` (KV, substitutable
    here via `get_secret`, the D5 test seam) or `fsd.storage.fs.open` (blob, via
    `cdse.CdseCredentials.from_json`). The same `identity_client_id` (D4) that
    authorises blob also authorises Key Vault.

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
            creds_url=creds_url, n_tiles=len(tiles), max_tiles=max_tiles,
        )

        timeout = timeout_seconds or _estimate_timeout_seconds(estimated_gb)
        creds_arg = f"--creds-url {creds_url}" if creds_url else \
            f"--vault-url {vault_url} --secret-name {secret_name}"
        command = (
            f"python -m fsd.workflows.download --roi {roi} "
            f"--startdate {_iso(startdate)} --enddate {_iso(enddate)} "
            f"--bands {','.join(bands)} --dst {dst_folderpath} --catalog {catalog_filepath} "
            f"--max-tiles {max_tiles} {creds_arg} "
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
            creds_url=creds_url,
            # one row per asset -> collapse to distinct MGRS tiles, the unit
            # `max_tiles` counts in `sources/mpc.download`'s own guard.
            n_tiles=len({r["tile_id"] for r in rows}), max_tiles=max_tiles,
        )

        if n_shards is None:
            compute = ml_client.compute.get(cluster)
            n_shards = getattr(compute, "max_instances", None) or 1
        shards = shard_units(rows, n_shards)
        timeout = timeout_seconds or _estimate_timeout_seconds(
            n_assets * config.APPROX_GB_PER_TILE / max(len(bands), 1)
        )

        # D8 (spec 38, TODO #51 -- MPC only): each shard writes its OWN catalog file
        # (single writer, no lock) instead of all N shards racing an unsynchronised
        # read-whole-parquet -> concat -> write-whole-parquet against the SAME
        # `catalog_filepath` (`TileCatalog.append`, last-writer-wins on blob -- a
        # silent lost update that under-declares the archive). The driver merges them
        # sequentially below, after every shard has finished. CDSE is untouched: it
        # runs as one job writing the canonical catalog directly (D1's asymmetry), so
        # the race cannot occur there.
        shard_catalog_urls: dict[int, str] = {}
        jobs = {}
        for k, shard_rows in enumerate(shards):
            shard_url = f"{run_root}/shards/{k}.csv"
            with fs.open(shard_url, "w") as f:
                pd.DataFrame(shard_rows).to_csv(f, index=False)

            shard_catalog_url = f"{run_root}/shards/catalog-{k}.parquet"
            shard_catalog_urls[k] = shard_catalog_url
            jobs[k] = aml_command(
                command=(
                    f"python -m fsd.workflows.download --shard {shard_url} "
                    f"--dst {dst_folderpath} --catalog {shard_catalog_url} "
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

    if source == "mpc":
        _merge_shard_catalogs(shard_catalog_urls, catalog_filepath)

    return {"run_id": run_id, "source": source, "n_jobs": len(jobs),
            "job_statuses": result["job_statuses"], "reports": result["reports"]}


def _merge_shard_catalogs(shard_catalog_urls: dict[int, str], canonical_filepath: str) -> None:
    """D8 (spec 38, TODO #51): sequentially `TileCatalog.append` each MPC shard's own
    catalog file into the canonical one, in shard order -- a deliberate single-writer
    SERIALIZATION (no lock, no ETag/lease -- TODO #50 shows those go badly on
    `abfss://`), run once after every shard has already finished, so it is not a race.
    A shard that produced no assets (e.g. every asset in it failed) writes no catalog
    file at all -- skipped, not an error."""
    canonical = _TileCatalog(canonical_filepath)
    for k in sorted(shard_catalog_urls):
        shard_url = shard_catalog_urls[k]
        if not fs.exists(shard_url):
            continue
        shard_catalog = _TileCatalog(shard_url)
        rows = shard_catalog.read().to_dict("records")
        canonical.append(rows, declaration=shard_catalog.declaration)
