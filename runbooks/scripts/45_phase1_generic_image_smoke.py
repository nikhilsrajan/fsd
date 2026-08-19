"""Spec 44 phase 1 — prove the adapter imports inside a **generic** inference Environment.

Run-book: `runbooks/45-verify-bundle-carried-code.md` (Phase 1c). Mirrors `runbooks/
38-inference-on-aml.md` Phase 0 exactly, with one difference that is the entire point: the image
this runs against has **no adapter source in it**. If the smoke passes, the adapter reached the
node from inside the bundle.

Since spec 45 D4 (#67) this script is a **thin wrapper over `fsd.model.verify_image`** — the same
driver-side-first-then-one-node-job behaviour, now a public library call any run-book or notebook
cell can use directly. This script's only remaining job is: read env vars, call the helper, and
write `_result_phase1.json` in the same shape run-book 45 has always expected.

**The smoke MUST run as an AML job, not on your laptop.** Your driver venv has the adapter module
on `sys.path` and its deps installed, so a local run passes trivially while proving nothing about
the image (ADR 0002: the driver's venv is not guaranteed to mirror the node's image) —
`verify_image(runner="local")` refuses outright for exactly this reason (spec 45 D5).

Costs: one bundle upload + one node cold start (~40-380 s). Everything that CAN be checked on the
driver IS checked first, before anything is submitted (spec 38 D11's rule, spec 45 D4 step 1).

Required env vars -- paste them from the uncommitted `../../AZURE_INFRA_PRIVATE.md`:
    AZ_SUBSCRIPTION_ID  AZ_RG  AZ_ML_WORKSPACE  AZ_CLUSTER  AZ_UAMI_CLIENT_ID
    AZ_ROOT  AZ_INFER_ENV_NAME  AZ_INFER_ENV_VERSION  AZ_BUNDLE_LOCAL

Optional but strongly recommended:
    AZ_INFER_BUILD_CONTEXT  -- the folder holding the fsd wheel your image was built from.
                               Set it and verify_image refuses to submit against an image built
                               from a pre-spec-44 wheel, which is the commonest failure and the
                               one the node CANNOT report on its own.

Usage, from the `fsd/` package root:
    .venv/bin/python runbooks/scripts/45_phase1_generic_image_smoke.py

`--out <dir>` writes `_result_phase1.json` somewhere other than the default
`tests/outputs/spec44_verify/` (same argv convention as `34_mixed_baseline_slice.py`'s `--dst`).
The offline shape test in `tests/test_bundle_transparency.py` passes it so that running `pytest`
never overwrites the real Phase-1 result of an actual run.

In a Jupyter notebook use `%run`, NOT `!python` -- the `!` form needs `{var}` substitution and is
where the `f"{AZ_ROOT}/..."` mistake comes from (IPython's `!` is not an f-string; a literal `f`
glued to the URL yields `Protocol not known: fabfss`):
    %run runbooks/scripts/45_phase1_generic_image_smoke.py
"""

import json
import os
import pathlib
import sys

# fsd/runbooks/scripts/45_phase1_generic_image_smoke.py -> parents[2] == fsd/
FSD_ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = (pathlib.Path(sys.argv[sys.argv.index("--out") + 1]) if "--out" in sys.argv
       else FSD_ROOT / "tests" / "outputs" / "spec44_verify")
OUT.mkdir(parents=True, exist_ok=True)

REQUIRED = (
    "AZ_SUBSCRIPTION_ID", "AZ_RG", "AZ_ML_WORKSPACE", "AZ_CLUSTER", "AZ_UAMI_CLIENT_ID",
    "AZ_ROOT", "AZ_INFER_ENV_NAME", "AZ_INFER_ENV_VERSION", "AZ_BUNDLE_LOCAL",
)

# The shape run-book 45 has always expected -- verify_image returns the same shape (spec 24
# _result.json), this script just relabels "step"/"expected" for this specific run-book.
result = {
    "step": "spec44-phase1-generic-image-smoke",
    "status": "ok",
    "pass": False,
    "metrics": {},
    "expected": {"bundle_version": 2, "code_block_present": True, "smoke_status": "ok"},
    "error": None,
}

missing = [k for k in REQUIRED if not os.environ.get(k)]
if missing:
    result["status"] = "fail"
    result["error"] = (
        "missing env vars: " + ", ".join(missing)
        + "\nSource them from env.example.sh + AZURE_INFRA_PRIVATE.md first. "
        "AZ_INFER_ENV_VERSION comes back EMPTY if the Environment does not exist yet -- "
        "build it (run-book Phase 1b) before running this."
    )
else:
    from fsd.model.verify_image import verify_image

    result = verify_image(
        os.environ["AZ_BUNDLE_LOCAL"],
        environment=f"{os.environ['AZ_INFER_ENV_NAME']}:{os.environ['AZ_INFER_ENV_VERSION']}",
        runner="aml",
        runner_kwargs=dict(
            cluster=os.environ["AZ_CLUSTER"],
            root=os.environ["AZ_ROOT"],
            identity_client_id=os.environ["AZ_UAMI_CLIENT_ID"],
            subscription_id=os.environ["AZ_SUBSCRIPTION_ID"],
            resource_group_name=os.environ["AZ_RG"],
            workspace_name=os.environ["AZ_ML_WORKSPACE"],
        ),
        build_context=os.environ.get("AZ_INFER_BUILD_CONTEXT"),
    )
    # relabel to this run-book's own step name; verify_image's own is generic ("verify_image")
    result["step"] = "spec44-phase1-generic-image-smoke"
    result["expected"] = {"bundle_version": 2, "code_block_present": True, "smoke_status": "ok"}

with open(OUT / "_result_phase1.json", "w") as f:
    json.dump(result, f, indent=2)
print(json.dumps(result, indent=2))
print(f"\nwrote {OUT / '_result_phase1.json'}")
