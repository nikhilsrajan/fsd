"""Spec 51 §9 step 2 — `fsd.deploy` (D5/D6/D7).

One test group per acceptance criterion this step owns (handoff-spec51-step2-deploy.md):
AC1, AC2, AC3, AC5, AC7, AC8, AC9, AC10 (the record half), AC13. D6's live-adapter refusal
is included too (small, and the natural place to check it against the real verb).

A bundle deployable end-to-end needs BOTH a `code` block and `requirements` (D6), so fixtures
here write a real importable adapter module (mirrors `tests/test_bundle_transparency.py`)
rather than `test_registry.py`'s `code=False` shortcut, which is deliberately undeployable.

AC7's "runs verify_image itself" path is exercised with the same fake `MLClient` +
`azure.ai.ml.command` injection seam `tests/test_bundle_transparency.py`/`test_infer_aml.py`
use (spec 36 D3 invariant 3): no network, no Azure SDK import. Every other AC uses
`verified=<dict>` (D5's other path) instead, which needs no AML machinery at all -- that is
what makes AC7 the one test that actually proves the enforcement gate calls `verify_image`.
"""

from __future__ import annotations

import json
import os
import sys
import textwrap
import types

import pytest

from fsd import api
from fsd.model import bundle, registry
from fsd.storage import fs
from fsd.workflows import runners

ADAPTER_SRC = '''
from fsd.model.adapter import BaseModelAdapter


class TinyAdapter(BaseModelAdapter):
    required_bands = ["B04", "B08"]
    output_dtype = "uint8"
    output_nodata = 255
    output_band_names = ["klass"]

    def load(self):
        self.loaded = True

    def predict(self, X):
        return X
'''


@pytest.fixture
def importable(tmp_path, monkeypatch):
    def _make(rel: str, src: str = ADAPTER_SRC, root: str | None = None) -> str:
        root_dir = tmp_path / (root or "srcroot")
        target = root_dir / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(textwrap.dedent(src))
        monkeypatch.syspath_prepend(str(root_dir))
        return str(root_dir)

    yield _make


def _purge(*names: str) -> None:
    for n in names:
        sys.modules.pop(n, None)


def _deployable_bundle(tmp_path, importable, dst="b", requirements=("packaging",), modname="tdmod") -> str:
    """A bundle with both a `code` block and `requirements` -- the only shape `deploy` accepts."""
    importable(f"{modname}.py")
    mod = sys.modules.get(modname) or __import__(modname)
    try:
        return bundle.save(
            mod.TinyAdapter(), {}, str(tmp_path / dst),
            requirements=list(requirements) if requirements else None, verbose=False,
        )
    finally:
        _purge(modname)


def _matching_verified(bundle_path: str, environment: str) -> dict:
    """A `verified=` dict that D5 will accept for THIS bundle/environment -- no AML call."""
    return {
        "step": "verify_image", "status": "ok", "pass": True,
        "metrics": {"bundle_path": bundle_path, "environment": environment},
        "expected": {}, "error": None,
    }


# --- AC1: deploy publishes v1 and the ref works through the public verb ------------------


def test_deploy_publishes_v1_and_run_inference_accepts_the_ref(tmp_path, importable):
    bpath = _deployable_bundle(tmp_path, importable)
    registry_root = str(tmp_path / "registry")

    ref = api.deploy(
        bpath, name="crop-rf", registry=registry_root, environment="fsd-infer-sklearn:6",
        verified=_matching_verified(bpath, "fsd-infer-sklearn:6"),
    )

    assert ref == "crop-rf:1"
    resolved = registry.resolve(ref, registry_root)
    assert resolved.version == 1
    assert fs.exists(os.path.join(resolved.path, bundle.BUNDLE_MANIFEST))

    # AC6's own proof pattern: reaching a LATER preflight error is what shows the ref resolved
    # (an unresolved ref dies at `_model_spec`'s `bundle.json` read, not here).
    cubes = tmp_path / "cubes"
    cubes.mkdir()
    with pytest.raises(api.PreflightError, match="no inference datacubes"):
        api.run_inference(
            model=ref, registry=registry_root,
            inference_datacubes=str(cubes), output_folderpath=str(tmp_path / "out"),
        )


# --- AC2: deploying identical content twice is idempotent -------------------------------


def test_deploy_identical_content_twice_is_idempotent(tmp_path, importable):
    bpath = _deployable_bundle(tmp_path, importable)
    registry_root = str(tmp_path / "registry")
    verified = _matching_verified(bpath, "env:1")

    ref1 = api.deploy(bpath, name="crop-rf", registry=registry_root, environment="env:1",
                      verified=verified)
    before = fs.ls(os.path.join(registry_root, "crop-rf"))

    ref2 = api.deploy(bpath, name="crop-rf", registry=registry_root, environment="env:1",
                      verified=verified)
    after = fs.ls(os.path.join(registry_root, "crop-rf"))

    assert ref2 == ref1
    assert len(after) == len(before)


# --- AC3: deploying changed content creates v2; v1 is untouched -------------------------


def test_deploy_changed_content_creates_v2_and_leaves_v1_untouched(tmp_path, importable):
    registry_root = str(tmp_path / "registry")
    b1 = _deployable_bundle(tmp_path, importable, dst="b1", modname="tdmod1")
    ref1 = api.deploy(b1, name="crop-rf", registry=registry_root, environment="env:1",
                      verified=_matching_verified(b1, "env:1"))
    assert ref1 == "crop-rf:1"

    b2 = _deployable_bundle(tmp_path, importable, dst="b2", requirements=["packaging", "numpy"],
                            modname="tdmod2")
    ref2 = api.deploy(b2, name="crop-rf", registry=registry_root, environment="env:1",
                      verified=_matching_verified(b2, "env:1"))
    assert ref2 == "crop-rf:2"

    v1_path = registry.version_path(registry_root, "crop-rf", 1)
    with fs.open(os.path.join(v1_path, bundle.BUNDLE_MANIFEST), "r") as f:
        v1_manifest_in_registry = json.load(f)
    with open(os.path.join(b1, bundle.BUNDLE_MANIFEST)) as f:
        v1_manifest_source = json.load(f)
    assert v1_manifest_in_registry == v1_manifest_source


# --- AC5: alias is written on deploy; redeploying with the same alias just repoints -----


def test_deploy_alias_repoints_without_touching_either_version(tmp_path, importable):
    registry_root = str(tmp_path / "registry")
    b1 = _deployable_bundle(tmp_path, importable, dst="b1", modname="tdmod3")
    api.deploy(b1, name="crop-rf", registry=registry_root, environment="env:1", alias="champion",
              verified=_matching_verified(b1, "env:1"))
    v1_manifest_path = os.path.join(registry.version_path(registry_root, "crop-rf", 1),
                                    bundle.BUNDLE_MANIFEST)
    with fs.open(v1_manifest_path, "r") as f:
        v1_before = f.read()

    b2 = _deployable_bundle(tmp_path, importable, dst="b2", requirements=["packaging", "numpy"],
                            modname="tdmod4")
    api.deploy(b2, name="crop-rf", registry=registry_root, environment="env:1", alias="champion",
              verified=_matching_verified(b2, "env:1"))

    assert registry.resolve("crop-rf@champion", registry_root).version == 2
    with fs.open(v1_manifest_path, "r") as f:
        v1_after = f.read()
    assert v1_after == v1_before


# --- AC7: deploy runs verify_image itself and refuses on pass=False ---------------------


class _NS(types.SimpleNamespace):
    pass


class _FakeMLClient:
    def __init__(self, job_statuses: dict[str, str]):
        self._job_statuses = job_statuses
        self.submitted: list = []
        self.compute = _NS(get=lambda cluster: _NS(provisioning_state="Succeeded", max_instances=4))
        self.environments = _NS(get=lambda **kw: _NS())
        self.jobs = _NS(create_or_update=self._create_or_update, get=self._get)

    def _create_or_update(self, job):
        idx = len(self.submitted)
        name = f"job-{idx}"
        self.submitted.append((name, job))
        return _NS(name=name)

    def _get(self, name):
        idx = int(name.rsplit("-", 1)[1])
        return _NS(status=list(self._job_statuses.values())[idx])


@pytest.fixture
def fake_aml_command(monkeypatch):
    def _cmd(**kwargs):
        return types.SimpleNamespace(**kwargs)

    monkeypatch.setattr(runners, "_import_aml_command", lambda: _cmd)
    return _cmd


def _status_url(root: str, run_id: str) -> str:
    return f"{root}/_verify_image/{run_id}/_status/smoke.json"


def test_deploy_runs_verify_image_and_publishes_on_pass(tmp_path, importable, fake_aml_command):
    bpath = _deployable_bundle(tmp_path, importable, modname="tdmod5")
    registry_root = str(tmp_path / "registry")
    aml_root = "memory://deploy_ok/root"
    ml_client = _FakeMLClient({"smoke": "Completed"})
    with fs.open(_status_url(aml_root, "runok"), "w") as f:
        json.dump({"status": "ok", "error": None}, f)

    ref = api.deploy(
        bpath, name="crop-rf", registry=registry_root, environment="fsd-infer-sklearn:3",
        runner_kwargs=dict(cluster="c", root=aml_root, identity_client_id="x",
                           ml_client=ml_client, run_id="runok"),
    )

    assert ref == "crop-rf:1"
    v1_path = registry.version_path(registry_root, "crop-rf", 1)
    with fs.open(os.path.join(v1_path, registry.DEPLOY_FILE), "r") as f:
        record = json.load(f)
    assert record["verified"]["pass"] is True


def test_deploy_refuses_on_verify_image_failure_and_creates_no_version(
    tmp_path, importable, fake_aml_command,
):
    bpath = _deployable_bundle(tmp_path, importable, modname="tdmod6")
    registry_root = str(tmp_path / "registry")
    aml_root = "memory://deploy_fail/root"
    ml_client = _FakeMLClient({"smoke": "Completed"})
    with fs.open(_status_url(aml_root, "runfail"), "w") as f:
        json.dump({"status": "fail", "error": "predict() raised"}, f)

    # verify_image only populates the top-level `error` on a driver-detected failure (bad
    # code, stale wheel, no status file) -- a smoke job that itself ran and reported
    # pass=False leaves `error=None` and the diagnosis in `metrics["smoke_error"]` instead.
    # D5's contract is still "surfaces that result's own error" -- here that is None, and
    # deploy must still refuse.
    with pytest.raises(api.PreflightError, match="has not been proven to run this bundle"):
        api.deploy(
            bpath, name="crop-rf", registry=registry_root, environment="fsd-infer-sklearn:3",
            runner_kwargs=dict(cluster="c", root=aml_root, identity_client_id="x",
                               ml_client=ml_client, run_id="runfail"),
        )

    assert not fs.exists(os.path.join(registry_root, "crop-rf"))


# --- AC8: verified= only skips re-verification when digest AND environment both match ---


def test_deploy_accepts_a_matching_verified_result_without_running_verify_image(
    tmp_path, importable, monkeypatch,
):
    bpath = _deployable_bundle(tmp_path, importable, modname="tdmod7")
    registry_root = str(tmp_path / "registry")

    def _forbidden(*a, **kw):
        raise AssertionError("verify_image was called despite a matching verified= result")

    monkeypatch.setattr(api, "_verify_image", _forbidden)

    ref = api.deploy(
        bpath, name="crop-rf", registry=registry_root, environment="env:1",
        verified=_matching_verified(bpath, "env:1"),
    )
    assert ref == "crop-rf:1"


def test_deploy_refuses_a_verified_result_from_a_different_environment(tmp_path, importable):
    bpath = _deployable_bundle(tmp_path, importable, modname="tdmod8")
    registry_root = str(tmp_path / "registry")

    with pytest.raises(api.PreflightError, match="stale or does not match"):
        api.deploy(
            bpath, name="crop-rf", registry=registry_root, environment="env:1",
            verified=_matching_verified(bpath, "env:OTHER"),
        )
    assert not fs.exists(os.path.join(registry_root, "crop-rf"))


def test_deploy_refuses_a_verified_result_for_different_bundle_content(tmp_path, importable):
    registry_root = str(tmp_path / "registry")
    b1 = _deployable_bundle(tmp_path, importable, dst="b1", modname="tdmod9")
    b2 = _deployable_bundle(tmp_path, importable, dst="b2", requirements=["packaging", "numpy"],
                            modname="tdmod10")

    with pytest.raises(api.PreflightError, match="stale or does not match"):
        api.deploy(
            b1, name="crop-rf", registry=registry_root, environment="env:1",
            verified=_matching_verified(b2, "env:1"),  # verified a DIFFERENT bundle's content
        )
    assert not fs.exists(os.path.join(registry_root, "crop-rf"))


def test_deploy_surfaces_a_matched_but_failing_verified_results_own_error(tmp_path, importable):
    """A `verified=` result that DOES match this bundle/environment but failed must still be
    honoured (D5) -- refused with ITS error, not folded into the generic mismatch message."""
    bpath = _deployable_bundle(tmp_path, importable, modname="tdmod11")
    registry_root = str(tmp_path / "registry")
    failing = {
        "step": "verify_image", "status": "fail", "pass": False,
        "metrics": {"bundle_path": bpath, "environment": "env:1"},
        "expected": {}, "error": "ModuleNotFoundError: no module named tinyadapter",
    }

    with pytest.raises(api.PreflightError, match="ModuleNotFoundError"):
        api.deploy(bpath, name="crop-rf", registry=registry_root, environment="env:1",
                  verified=failing)
    assert not fs.exists(os.path.join(registry_root, "crop-rf"))


# --- AC9: refuses a bundle with no requirements / no code block -------------------------


def test_deploy_refuses_a_bundle_with_no_requirements(tmp_path, importable):
    importable("tdreqmod.py")
    import tdreqmod
    try:
        bpath = bundle.save(tdreqmod.TinyAdapter(), {}, str(tmp_path / "b"), verbose=False)
    finally:
        _purge("tdreqmod")
    registry_root = str(tmp_path / "registry")

    with pytest.raises(api.PreflightError, match=r"bundle\.save\(\.\.\., requirements="):
        api.deploy(bpath, name="crop-rf", registry=registry_root, environment="env:1",
                  verified=_matching_verified(bpath, "env:1"))
    assert not fs.exists(os.path.join(registry_root, "crop-rf"))


def test_deploy_refuses_a_bundle_with_no_code_block(tmp_path):
    joblib = pytest.importorskip("joblib")
    bpath = bundle.save(joblib.Parallel, {}, str(tmp_path / "b"), code=False,
                        requirements=["packaging"], verbose=False)
    registry_root = str(tmp_path / "registry")

    with pytest.raises(api.PreflightError, match=r"bundle\.save\(\.\.\., code="):
        api.deploy(bpath, name="crop-rf", registry=registry_root, environment="env:1",
                  verified=_matching_verified(bpath, "env:1"))
    assert not fs.exists(os.path.join(registry_root, "crop-rf"))


# --- D6: a live adapter is refused, naming fsd.model.bundle.save ------------------------


def test_deploy_refuses_a_live_adapter(tmp_path, importable):
    importable("tdlivemod.py")
    import tdlivemod
    try:
        with pytest.raises(api.PreflightError, match="fsd.model.bundle.save"):
            api.deploy(tdlivemod.TinyAdapter(), name="crop-rf", registry=str(tmp_path / "registry"),
                      environment="env:1")
    finally:
        _purge("tdlivemod")


# --- AC10 (record half): _deploy.json records name/version/digest/environment/verified --


def test_deploy_writes_the_deploy_record(tmp_path, importable):
    bpath = _deployable_bundle(tmp_path, importable, modname="tdmod12")
    registry_root = str(tmp_path / "registry")
    verified = _matching_verified(bpath, "fsd-infer-sklearn:6")

    ref = api.deploy(bpath, name="crop-rf", registry=registry_root,
                     environment="fsd-infer-sklearn:6", verified=verified)

    v1_path = registry.version_path(registry_root, "crop-rf", 1)
    with fs.open(os.path.join(v1_path, registry.DEPLOY_FILE), "r") as f:
        record = json.load(f)

    assert record["name"] == "crop-rf"
    assert record["version"] == 1
    assert record["digest"] == registry.content_digest(bpath)
    assert record["environment"] == "fsd-infer-sklearn:6"
    assert record["verified"] == verified
    assert "deployed_at" in record and "fsd_version" in record
    assert ref == "crop-rf:1"


# --- AC13a: nothing deploy writes contains the registry root, an absolute path, or a URL ---


def test_deploy_writes_no_file_containing_the_registry_root(tmp_path, importable):
    bpath = _deployable_bundle(tmp_path, importable, modname="tdmod13")
    registry_root = str(tmp_path / "registry")

    api.deploy(bpath, name="crop-rf", registry=registry_root, environment="env:1",
              alias="champion", verified=_matching_verified(bpath, "env:1"))

    root_str = registry_root
    for path, _size in fs.find_sizes(registry_root).items():
        if not (path.endswith(".json") or os.path.basename(path).startswith("_")):
            continue
        with open(path, "rb") as f:
            text = f.read().decode("utf-8", errors="replace")
        assert root_str not in text
