"""Spec 44 phase 1 — prove the adapter imports inside a **generic** inference Environment.

Run-book: `runbooks/45-verify-bundle-carried-code.md` (Phase 1c). Mirrors `runbooks/
38-inference-on-aml.md` Phase 0 exactly, with one difference that is the entire point: the image
this runs against has **no adapter source in it**. If the smoke passes, the adapter reached the
node from inside the bundle.

**The smoke MUST run as an AML job, not on your laptop.** Your driver venv has the adapter module
on `sys.path` and its deps installed, so a local run passes trivially while proving nothing about
the image (ADR 0002: the driver's venv is not guaranteed to mirror the node's image). This script
submits a one-node job and waits.

Costs: one bundle upload + one node cold start (~40-380 s). Everything that CAN be checked on the
driver IS checked first, before anything is submitted (spec 38 D11's rule).

Required env vars -- paste them from the uncommitted `../../AZURE_INFRA_PRIVATE.md`:
    AZ_SUBSCRIPTION_ID  AZ_RG  AZ_ML_WORKSPACE  AZ_CLUSTER  AZ_UAMI_CLIENT_ID
    AZ_ROOT  AZ_INFER_ENV_NAME  AZ_INFER_ENV_VERSION  AZ_BUNDLE_LOCAL

Optional but strongly recommended:
    AZ_INFER_BUILD_CONTEXT  -- the folder holding the fsd wheel your image was built from.
                               Set it and this script refuses to submit against an image built
                               from a pre-spec-44 wheel, which is the commonest failure and the
                               one the node CANNOT report on its own.

Usage, from the `fsd/` package root:
    .venv/bin/python runbooks/scripts/45_phase1_generic_image_smoke.py

In a Jupyter notebook use `%run`, NOT `!python` -- the `!` form needs `{var}` substitution and is
where the `f"{AZ_ROOT}/..."` mistake comes from (IPython's `!` is not an f-string; a literal `f`
glued to the URL yields `Protocol not known: fabfss`):
    %run runbooks/scripts/45_phase1_generic_image_smoke.py
"""

import json
import os
import pathlib
import traceback

# fsd/runbooks/scripts/45_phase1_generic_image_smoke.py -> parents[2] == fsd/
FSD_ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = FSD_ROOT / "tests" / "outputs" / "spec44_verify"

REQUIRED = (
    "AZ_SUBSCRIPTION_ID", "AZ_RG", "AZ_ML_WORKSPACE", "AZ_CLUSTER", "AZ_UAMI_CLIENT_ID",
    "AZ_ROOT", "AZ_INFER_ENV_NAME", "AZ_INFER_ENV_VERSION", "AZ_BUNDLE_LOCAL",
)

result = {
    "step": "spec44-phase1-generic-image-smoke",
    "status": "ok",
    "pass": False,
    "metrics": {},
    "expected": {"bundle_version": 2, "code_block_present": True, "smoke_status": "ok"},
    "error": None,
}

try:
    OUT.mkdir(parents=True, exist_ok=True)

    # --- driver-side preflight: everything checkable for free, before any cost ---------------
    missing = [k for k in REQUIRED if not os.environ.get(k)]
    if missing:
        raise SystemExit(
            "missing env vars: " + ", ".join(missing)
            + "\nSource them from env.example.sh + AZURE_INFRA_PRIVATE.md first. "
            "AZ_INFER_ENV_VERSION comes back EMPTY if the Environment does not exist yet -- "
            "build it (run-book Phase 1b) before running this."
        )

    from fsd.model import bundle as fsd_bundle
    from fsd.storage import fs
    from fsd.workflows import runners

    bundle_local = os.environ["AZ_BUNDLE_LOCAL"]
    manifest = fsd_bundle.read_spec(bundle_local)      # model-free: no import, no model load
    version = manifest.get("fsd_bundle_version")
    code = manifest.get("code")

    result["metrics"]["bundle_local"] = bundle_local
    result["metrics"]["bundle_version"] = version
    result["metrics"]["adapter_ref"] = manifest.get("adapter")
    result["metrics"]["code_block_present"] = bool(code)
    result["metrics"]["code_files"] = (code or {}).get("files")
    result["metrics"]["requirements"] = manifest.get("requirements")

    # THE spec-44 precondition. Without it the job is guaranteed to fail with
    # ModuleNotFoundError on the node, after paying for a cold start.
    if not code:
        raise SystemExit(
            f"{bundle_local} is a version-{version} bundle with no `code` block, so it does NOT "
            "carry its adapter. On a generic image this WILL fail with ModuleNotFoundError. "
            "Re-save it with a post-2026-08-19 fsd (run-book Phase 1c step 1) -- that is the whole "
            "migration. See run-book Phase 3."
        )

    # --- optional but strongly recommended: is the IMAGE's fsd new enough? ------------------
    # The commonest spec-44 failure is a generic image built from a STALE fsd wheel. Its
    # `fetch_bundle_to_scratch` never downloads `code/` and its `bundle.load` never touches
    # `sys.path`, so the node raises `ModuleNotFoundError: <adapter>` even though the bundle
    # staged perfectly (`code_files_staged: N/N`). The node cannot self-diagnose this -- an old
    # fsd has none of the code that would report it -- so the check has to happen here.
    ctx = os.environ.get("AZ_INFER_BUILD_CONTEXT")
    if ctx:
        import glob
        import zipfile

        wheels = sorted(glob.glob(os.path.join(ctx, "fsd-*.whl")))
        result["metrics"]["build_context_wheel"] = wheels[-1] if wheels else None
        if not wheels:
            raise SystemExit(
                f"AZ_INFER_BUILD_CONTEXT={ctx!r} contains no fsd-*.whl. The image cannot have "
                "installed fsd from there."
            )
        wheel_src = zipfile.ZipFile(wheels[-1]).read("fsd/model/bundle.py").decode()
        fresh = "def manifest_code_files" in wheel_src
        result["metrics"]["wheel_has_spec44"] = fresh
        if not fresh:
            raise SystemExit(
                f"{wheels[-1]} PREDATES spec 44 -- it has no `manifest_code_files`, so the image's "
                "fetch_bundle_to_scratch will not download `code/` and its bundle.load will not put "
                "it on sys.path. The node will raise ModuleNotFoundError however good the bundle "
                "is. Rebuild the wheel and the image:\n"
                f"    .venv/bin/pip wheel . --no-deps -w {ctx}\n"
                "    az ml environment create --file <your infer-environment.yml> "
                '-g "$AZ_RG" -w "$AZ_ML_WORKSPACE"\n'
                "then re-read AZ_INFER_ENV_VERSION and re-run this script."
            )

    from azure.ai.ml import MLClient
    from azure.identity import DefaultAzureCredential

    ml_client = MLClient(
        DefaultAzureCredential(),
        os.environ["AZ_SUBSCRIPTION_ID"], os.environ["AZ_RG"], os.environ["AZ_ML_WORKSPACE"],
    )

    # --- stage the bundle exactly the way run_aml_inference will (spec 38 D3) ---------------
    staged = runners._stage_bundle(bundle_local, f"{os.environ['AZ_ROOT']}/_spec44_bundle")
    result["metrics"]["staged_bundle_url"] = staged

    # Prove the code files actually landed -- this is the transport half of the change.
    staged_code = fsd_bundle.manifest_code_files(manifest)
    landed = [rel for rel in staged_code if fs.exists(f"{staged}/{rel}")]
    result["metrics"]["code_files_staged"] = f"{len(landed)}/{len(staged_code)}"
    if len(landed) != len(staged_code):
        raise SystemExit(
            f"only {len(landed)}/{len(staged_code)} code files reached {staged}: "
            f"missing {[r for r in staged_code if r not in landed]}"
        )

    # --- submit the one-node smoke INTO the generic image and wait --------------------------
    env_ref = f"{os.environ['AZ_INFER_ENV_NAME']}:{os.environ['AZ_INFER_ENV_VERSION']}"
    status_url = f"{os.environ['AZ_ROOT']}/_status/spec44_smoke.json"
    result["metrics"]["environment"] = env_ref

    aml_command = runners._import_aml_command()
    job = aml_command(
        command=f"python -m fsd.workflows.adapter_smoke {staged} --status-url {status_url}",
        environment=env_ref,
        compute=os.environ["AZ_CLUSTER"],
        environment_variables={"AZURE_CLIENT_ID": os.environ["AZ_UAMI_CLIENT_ID"]},
        display_name="fsd-spec44-generic-image-smoke",
        experiment_name="fsd-spec44-verify",
    )
    print(f"submitting the smoke into {env_ref} on {os.environ['AZ_CLUSTER']} ...")
    print("a cold node takes 40-380 s; this blocks until the job finishes.")
    submit_error = None
    try:
        runners._aml_submit_and_wait(
            ml_client, {"smoke": job}, os.environ["AZ_ROOT"], "spec44-smoke",
        )
    except Exception as exc:  # noqa: BLE001 - a failed job is an EXPECTED outcome here
        # `_aml_submit_and_wait` raises when the job fails, but the useful error is the one the
        # NODE wrote to `status_url` -- naming the missing dependency or the un-importable module.
        # Never let the driver's "job(s) failed" wrapper hide it: that is a dead-end message.
        submit_error = str(exc)

    result["metrics"]["status_url"] = status_url
    if fs.exists(status_url):
        with fs.open(status_url, "r") as f:
            smoke = json.load(f)
        result["metrics"]["smoke_status"] = smoke.get("status")
        result["metrics"]["smoke_error"] = smoke.get("error")
    else:
        # No status file => the job died BEFORE the entrypoint ran (bad image, fsd not installed,
        # blob auth). adapter_smoke always writes its status before exiting, so its absence is
        # itself the diagnosis.
        result["metrics"]["smoke_status"] = "no status file written"
        result["metrics"]["smoke_error"] = (
            "the job failed before `python -m fsd.workflows.adapter_smoke` could write its status. "
            "That points at the IMAGE or node auth, not at the adapter: fsd not installed in the "
            "environment, a broken entrypoint, or the node failing to reach blob (check "
            "AZURE_CLIENT_ID / the compute identity's RBAC). Open the job in AML studio -> "
            "Outputs+logs -> user_logs/std_log.txt for the node's traceback."
        )
    if submit_error:
        result["metrics"]["driver_error"] = submit_error

    result["pass"] = result["metrics"]["smoke_status"] == "ok" and version == 2
    result["status"] = "ok" if result["pass"] else "fail"

except SystemExit as exc:
    result["status"] = "fail"
    result["pass"] = False
    result["error"] = str(exc)
except Exception:  # noqa: BLE001 - spec 24: ALWAYS write _result.json, never a bare traceback
    result["status"] = "fail"
    result["pass"] = False
    result["error"] = traceback.format_exc()[-2000:]

OUT.mkdir(parents=True, exist_ok=True)
with open(OUT / "_result_phase1.json", "w") as f:
    json.dump(result, f, indent=2)
print(json.dumps(result, indent=2))
print(f"\nwrote {OUT / '_result_phase1.json'}")
