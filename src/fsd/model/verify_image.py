"""`fsd.model.verify_image` — does an inference IMAGE actually run THIS bundle? (spec 45 D4/#67)

Promotes `runbooks/scripts/45_phase1_generic_image_smoke.py` (the spec-44 phase-1 verification
job) into a public, reusable library call. Since spec 44 an inference image is generic per
*dependency family* (sklearn/xgboost/torch/keras), never per model — so "does this image run
this bundle?" is now a question worth asking as a function call, not a nine-env-var script.

Behavior is the run-book script's, lifted verbatim and generalised (spec 45 D4):

1. driver-side first, free: manifest is v2, a `code` block exists, `check_requirements` against
   the declared list, and — when `build_context` is given — the wheel-staleness gate that refuses
   a pre-spec-44 image in ~2 s instead of paying for a 40-380 s cold start;
2. stage the bundle exactly as `run_aml_inference` does (`runners._stage_bundle`);
3. submit **one node** running the existing `python -m fsd.workflows.adapter_smoke`;
4. always read `_status/*.json` back, and treat a *missing* status file as its own diagnosis (the
   job died before the entrypoint ran -> image or node auth, not the adapter).

Three properties are non-negotiable (each a defect the run-book already paid for): it must run as
a JOB, never on the driver (a local run passes trivially -- ADR 0002); the returned dict is
`_result.json`-shaped (spec 24) so a run-book can paste it straight back; and it is meant to be
called at the step it protects (immediately before `run_inference`), not hoisted into an upfront
gate that hardcodes paths a later step creates.
"""

from __future__ import annotations

import glob
import json
import os
import uuid
import zipfile

from fsd.model import bundle as _bundle
from fsd.storage import fs

__all__ = ["verify_image"]


def _find_wheel(build_context: str) -> str:
    """A caller who passes `build_context` has asserted the folder holds the wheel the image was
    built from (spec 47 D11). An absent wheel is a statement about the CALL, not the image, so
    this raises rather than returning a verdict -- it must run before `verify_image`'s `try`."""
    wheels = sorted(glob.glob(os.path.join(build_context, "fsd-*.whl")))
    if not wheels:
        raise ValueError(f"build_context={build_context!r} contains no fsd-*.whl.")
    return wheels[-1]


def _wheel_has_spec44(wheel: str) -> bool:
    """D4 step 1's wheel-staleness gate: does the fsd wheel this image was built from already
    carry `manifest_code_files` (spec 44)? A pre-spec-44 wheel's `fetch_bundle_to_scratch` never
    downloads `code/` and its `bundle.load` never touches `sys.path` -- the node then raises
    `ModuleNotFoundError` however good the bundle is, and cannot self-diagnose it (an old fsd has
    none of the code that would report it), so this has to be checked here, on the driver. Unlike
    an absent wheel, a stale one IS a statement about the image -- it stays inside the `try`."""
    with zipfile.ZipFile(wheel) as zf:
        src = zf.read("fsd/model/bundle.py").decode()
    return "def manifest_code_files" in src


def verify_image(
    bundle_path: str,
    *,
    environment: str,
    runner: str = "aml",
    runner_kwargs: dict | None = None,
    build_context: str | None = None,
) -> dict:
    """Does `environment` actually run `bundle_path`? Submits one real node and reports.

    `bundle_path` is a local bundle folder or an already-staged URL. `environment` is the
    inference Environment reference to verify (e.g. `"fsd-infer-sklearn:3"`).

    `runner` must be `"aml"` (D5) -- `runner="local"` **raises** rather than returning a pass,
    because "verified locally" is the exact false positive this helper exists to prevent: the
    driver's venv already has the adapter's source on `sys.path` and its dependencies installed
    (ADR 0002), so a local run tells you nothing about the image.

    `runner_kwargs` carries the AML dispatch parameters, the same names `run_aml_inference` takes:
    required `cluster`, `root`, `identity_client_id`; optional `ml_client` (spec 36 D3 invariant 3
    -- inject one for tests, otherwise a real `MLClient` is built from `subscription_id`/
    `resource_group_name`/`workspace_name`), `poll_interval_seconds` (default 30), and `run_id`
    (an opaque tag under `root` that namespaces the staged bundle + status file for this call --
    defaults to a fresh uuid; pass one explicitly to make the status URL predictable).

    `build_context`, if given, is the folder holding the fsd wheel the image was built from --
    enables the wheel-staleness gate (see `_check_wheel_has_spec44`).

    Returns a `_result.json`-shaped dict (spec 24): `{"step", "status", "pass", "metrics",
    "expected", "error"}`. Every driver-detectable failure (no `code` block, a stale wheel, a
    partial stage, a missing node status file) sets `pass=False` with a populated `error`.
    `verify_image` raises only on caller misuse it cannot report as a verification result --
    a non-`"aml"` `runner`, or `runner_kwargs` missing `cluster`/`root`/`identity_client_id`.
    """
    if runner != "aml":
        raise ValueError(
            f"verify_image(runner={runner!r}) is not a verification -- only 'aml' actually runs "
            "the bundle inside the target image on a real node. A local run passes trivially "
            "because the driver already has the adapter's source on sys.path and its "
            "dependencies installed (ADR 0002), which is the exact false positive this helper "
            "exists to prevent."
        )
    kwargs = dict(runner_kwargs or {})
    missing_kwargs = [k for k in ("cluster", "root", "identity_client_id") if not kwargs.get(k)]
    if missing_kwargs:
        raise ValueError(
            f"verify_image(runner='aml') requires runner_kwargs{sorted(missing_kwargs)!r}."
        )
    # D11: a caller who passes build_context has asserted the folder holds the wheel -- an
    # absent wheel is caller misuse and must raise here, before the try, not become pass=False.
    wheel = _find_wheel(build_context) if build_context else None

    result: dict = {
        "step": "verify_image",
        "status": "ok",
        "pass": False,
        "metrics": {},
        "expected": {"bundle_version": _bundle.BUNDLE_VERSION, "code_block_present": True,
                     "smoke_status": "ok"},
        "error": None,
    }
    try:
        # --- driver-side, free -----------------------------------------------------------
        manifest = _bundle.read_spec(bundle_path)   # model-free: no import, no model load
        version = manifest.get("fsd_bundle_version")
        code = manifest.get("code")
        result["metrics"].update({
            "bundle_path": str(bundle_path),
            "bundle_version": version,
            "adapter_ref": manifest.get("adapter"),
            "code_block_present": bool(code),
            "code_files": (code or {}).get("files"),
            "requirements": manifest.get("requirements"),
            "environment": environment,
        })
        if not code:
            raise ValueError(
                f"{bundle_path} is a version-{version} bundle with no `code` block, so it does "
                "not carry its adapter -- on a generic image this WILL fail with "
                "ModuleNotFoundError. Re-save it with fsd.model.bundle.save so the adapter's "
                "source is embedded."
            )
        # Informational, not fatal: the driver's venv need not mirror the image (ADR 0002) --
        # the real check is `check_requirements` running INSIDE the smoke job, below.
        result["metrics"]["requirement_problems_here"] = _bundle.check_requirements(
            manifest.get("requirements"))

        if wheel:
            fresh = _wheel_has_spec44(wheel)
            result["metrics"]["build_context_wheel"] = wheel
            result["metrics"]["wheel_has_spec44"] = fresh
            if not fresh:
                raise ValueError(
                    f"{wheel} predates spec 44 -- it has no `manifest_code_files`, so the "
                    "image's fetch_bundle_to_scratch will not download code/ and bundle.load "
                    "will not put it on sys.path. Rebuild the wheel and the image, then re-run "
                    "verify_image."
                )

        # --- stage + submit ----------------------------------------------------------------
        from fsd.workflows import (
            runners,  # lazy: keeps fsd.model import-light (no azure at import time)
        )

        ml_client = kwargs.get("ml_client")
        if ml_client is None:
            from azure.ai.ml import MLClient
            from azure.identity import DefaultAzureCredential

            ml_client = MLClient(
                DefaultAzureCredential(), kwargs.get("subscription_id"),
                kwargs.get("resource_group_name"), kwargs.get("workspace_name"),
            )

        root = str(kwargs["root"]).rstrip("/")
        # A deterministic tag can be supplied via runner_kwargs["run_id"] -- lets a caller (or a
        # test, injecting a fake ml_client per spec 36 D3 invariant 3) predict status_url ahead of
        # the call; otherwise a fresh one per call, same as run_aml_inference's own run_id.
        run_tag = str(kwargs.get("run_id") or uuid.uuid4().hex[:8])
        staged = runners._stage_bundle(bundle_path, f"{root}/_verify_image/{run_tag}/bundle")
        result["metrics"]["staged_bundle_url"] = staged

        # Prove the code files actually landed -- the transport half of the change.
        staged_code = _bundle.manifest_code_files(manifest)
        landed = [rel for rel in staged_code if fs.exists(f"{staged}/{rel}")]
        result["metrics"]["code_files_staged"] = f"{len(landed)}/{len(staged_code)}"
        if len(landed) != len(staged_code):
            raise ValueError(
                f"only {len(landed)}/{len(staged_code)} code files reached {staged}: "
                f"missing {[r for r in staged_code if r not in landed]}"
            )

        status_url = f"{root}/_verify_image/{run_tag}/_status/smoke.json"
        aml_command = runners._import_aml_command()
        job = aml_command(
            command=f"python -m fsd.workflows.adapter_smoke {staged} --status-url {status_url}",
            environment=environment,
            compute=kwargs["cluster"],
            environment_variables={"AZURE_CLIENT_ID": kwargs["identity_client_id"]},
            display_name=f"fsd-verify-image-{run_tag}",
            experiment_name="fsd-verify-image",
        )
        result["metrics"]["status_url"] = status_url
        submit_error = None
        try:
            runners._aml_submit_and_wait(
                ml_client, {"smoke": job}, root, f"verify-image-{run_tag}",
                poll_interval_seconds=kwargs.get("poll_interval_seconds", 30),
            )
        except Exception as exc:  # noqa: BLE001 - the useful error lives on status_url, not here
            submit_error = str(exc)

        if fs.exists(status_url):
            with fs.open(status_url, "r") as f:
                smoke = json.load(f)
            result["metrics"]["smoke_status"] = smoke.get("status")
            result["metrics"]["smoke_error"] = smoke.get("error")
        else:
            # No status file => the job died BEFORE the entrypoint ran (bad image, fsd not
            # installed, blob auth). adapter_smoke always writes its status before exiting, so
            # its absence is itself the diagnosis.
            result["metrics"]["smoke_status"] = "no status file written"
            result["metrics"]["smoke_error"] = (
                "the job failed before `python -m fsd.workflows.adapter_smoke` could write its "
                "status. That points at the IMAGE or node auth, not the adapter: fsd not "
                "installed in the environment, a broken entrypoint, or the node failing to reach "
                "blob (check the compute identity's RBAC)."
            )
        if submit_error:
            result["metrics"]["driver_error"] = submit_error

        result["pass"] = (
            result["metrics"]["smoke_status"] == "ok" and version == _bundle.BUNDLE_VERSION
        )
        result["status"] = "ok" if result["pass"] else "fail"
    except Exception as exc:  # noqa: BLE001 - spec 24: always return a shaped result, never a bare traceback
        result["status"] = "fail"
        result["pass"] = False
        result["error"] = str(exc)
    return result
