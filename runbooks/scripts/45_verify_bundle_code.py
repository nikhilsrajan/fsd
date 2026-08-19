"""Spec 44 phase 1 — prove the bundle carries its adapter, **offline**.

Run-book: `runbooks/45-verify-bundle-carried-code.md` (Phase 0). No cloud, no credentials, no
network, no imagery — a few seconds. This is the whole phase-1 contract checked locally, so that
Phase 1's `az ml` image build only ever fails for infrastructure reasons.

The load-bearing check is C: build a bundle, **delete the adapter's source directory from disk**,
then load the bundle in a **fresh subprocess**. If the adapter still resolves, it came out of the
bundle and nothing else — which is exactly what a cluster node does, and exactly what used to
require baking the `.py` into a per-adapter Docker image (spec 38 D4).

Self-contained by design (same rules as `33_probe_dedup.py`): no env vars, no arguments, paths
derive from this file's location, and **everything** is inside try/except so `_result.json` is
written even if an import blows up. A traceback with no `_result.json` breaks the spec-24 contract.

Usage, from the `fsd/` package root:
    .venv/bin/python runbooks/scripts/45_verify_bundle_code.py
"""

import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import traceback

# fsd/runbooks/scripts/45_verify_bundle_code.py -> parents[2] == fsd/
FSD_ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = FSD_ROOT / "tests" / "outputs" / "spec44_verify"

# Mirrors the demo notebook's `demo_model/my_adapter.py` — a plain module on sys.path, which is
# the shape a real user brings.
ADAPTER_SRC = '''
from fsd.model.adapter import BaseModelAdapter


class CropRF(BaseModelAdapter):
    required_bands = ["B04", "B08"]
    n_timestamps = 0
    output_dtype = "uint8"
    output_nodata = 255
    output_band_names = ["crop_class"]

    def load(self):
        with open(self.artifacts["model"]) as f:
            self.threshold = float(f.read())

    def predict(self, X):
        return X
'''

result = {
    "step": "spec44-phase0-offline",
    "status": "ok",
    "pass": False,
    "metrics": {},
    "expected": {
        "a_code_embedded": True,
        "b_layout_preserved": True,
        "c_loads_with_source_deleted": True,
        "d_main_refused": True,
        "e_v1_bundle_still_loads": True,
        "f_missing_requirement_named": True,
        "fsd_bundle_version": 2,
    },
    "error": None,
}

try:
    OUT.mkdir(parents=True, exist_ok=True)
    work = pathlib.Path(tempfile.mkdtemp(prefix="spec44-verify-"))

    from fsd.model import bundle

    result["metrics"]["fsd_bundle_module"] = str(pathlib.Path(bundle.__file__).resolve())

    # --- set up a throwaway adapter module + artifact, exactly like the notebook does ---------
    srcdir = work / "demo_model"
    srcdir.mkdir(parents=True)
    (srcdir / "my_adapter.py").write_text(ADAPTER_SRC)
    artifact = work / "model.txt"
    artifact.write_text("0.5")

    sys.path.insert(0, str(srcdir))
    from my_adapter import CropRF

    adapter = CropRF()
    adapter.n_timestamps = 10
    bundle_dir = bundle.save(adapter, {"model": str(artifact)}, str(work / "demo_bundle"))
    manifest = bundle.read_spec(bundle_dir)

    # --- A: the source is embedded, and the manifest still says what it always said ----------
    a_ok = (
        manifest.get("code_origin") == "bundled"
        and manifest.get("code", {}).get("files") == ["my_adapter.py"]
        and (pathlib.Path(bundle_dir) / "code" / "my_adapter.py").exists()
        and manifest["adapter"] == "my_adapter:CropRF"      # unchanged for the user
        and manifest["n_timestamps"] == 10                  # unchanged for the user
    )
    result["metrics"]["a_code_embedded"] = bool(a_ok)
    result["metrics"]["fsd_bundle_version"] = manifest.get("fsd_bundle_version")
    result["metrics"]["adapter_ref"] = manifest.get("adapter")
    result["metrics"]["code_files"] = manifest.get("code", {}).get("files")

    # --- B: a PACKAGE keeps its layout (MLflow's code_paths flattens; fsd must not) ----------
    pkgroot = work / "pkgsrc"
    (pkgroot / "cropkit").mkdir(parents=True)
    (pkgroot / "cropkit" / "__init__.py").write_text("")
    (pkgroot / "cropkit" / "helpers.py").write_text("BANDS = ['B04', 'B08']\n")
    (pkgroot / "cropkit" / "adapters.py").write_text(
        "from fsd.model.adapter import BaseModelAdapter\n"
        "from cropkit.helpers import BANDS\n\n\n"
        "class PkgRF(BaseModelAdapter):\n"
        "    required_bands = BANDS\n"
        "    output_dtype = 'uint8'\n"
        "    output_nodata = 255\n"
        "    output_band_names = ['k']\n\n"
        "    def load(self):\n"
        "        self.ok = True\n"
    )
    sys.path.insert(0, str(pkgroot))
    from cropkit.adapters import PkgRF

    pkg_bundle = bundle.save(PkgRF(), {}, str(work / "pkg_bundle"))
    pkg_files = bundle.read_spec(pkg_bundle)["code"]["files"]
    b_ok = pkg_files == ["cropkit/__init__.py", "cropkit/adapters.py", "cropkit/helpers.py"]
    result["metrics"]["b_layout_preserved"] = bool(b_ok)
    result["metrics"]["package_code_files"] = pkg_files

    # --- C: THE check. Delete the source from disk, load in a fresh interpreter. -------------
    shutil.rmtree(srcdir)
    probe = work / "probe.py"
    probe.write_text(
        "import sys\n"
        "from fsd.model import bundle\n"
        "try:\n"
        "    import my_adapter\n"
        "except ImportError:\n"
        "    pass\n"
        "else:\n"
        "    raise SystemExit('FAIL: my_adapter was importable outside the bundle')\n"
        f"a = bundle.load({str(bundle_dir)!r})\n"
        "assert type(a).__name__ == 'CropRF', type(a).__name__\n"
        "assert a.threshold == 0.5, a.threshold\n"
        "print('LOADED_FROM_BUNDLE_ONLY')\n"
    )
    env = dict(os.environ)
    # Deliberately do NOT put `srcdir` on the child's path — it no longer exists anyway.
    env.pop("PYTHONPATH", None)
    proc = subprocess.run(
        [sys.executable, str(probe)],
        capture_output=True, text=True, cwd=str(work), check=False,
    )
    c_ok = proc.returncode == 0 and "LOADED_FROM_BUNDLE_ONLY" in proc.stdout
    result["metrics"]["c_loads_with_source_deleted"] = bool(c_ok)
    if not c_ok:
        result["metrics"]["c_stdout"] = proc.stdout[-800:]
        result["metrics"]["c_stderr"] = proc.stderr[-800:]

    # --- D: a class defined in __main__ / a notebook cell is refused, with the fix named -----
    class Inline:
        pass

    Inline.__module__ = "__main__"
    try:
        bundle.adapter_code_files(Inline)
        d_ok, d_msg = False, "no error raised"
    except ValueError as exc:
        d_msg = str(exc)
        d_ok = "notebook" in d_msg and ".py file" in d_msg
    result["metrics"]["d_main_refused"] = bool(d_ok)
    result["metrics"]["d_message"] = d_msg[:200]

    # --- E: a pre-spec-44 (v1) bundle still loads when the module IS importable --------------
    sys.path.insert(0, str(pkgroot))
    v1_dir = work / "v1_bundle"
    shutil.copytree(pkg_bundle, v1_dir)
    v1_manifest_fp = v1_dir / "bundle.json"
    with open(v1_manifest_fp) as f:
        v1 = json.load(f)
    v1["fsd_bundle_version"] = 1
    v1.pop("code", None)
    v1.pop("code_origin", None)
    shutil.rmtree(v1_dir / "code")
    with open(v1_manifest_fp, "w") as f:
        json.dump(v1, f)
    try:
        loaded = bundle.load(str(v1_dir))
        e_ok = type(loaded).__name__ == "PkgRF"
        e_err = None
    except Exception as exc:  # noqa: BLE001 - the point is to report, not to crash
        e_ok, e_err = False, str(exc)
    result["metrics"]["e_v1_bundle_still_loads"] = bool(e_ok)
    if e_err:
        result["metrics"]["e_error"] = e_err[:200]

    # --- F: an unsatisfied declared requirement is reported BY NAME, not as a traceback ------
    problems = bundle.check_requirements(["definitely-not-a-real-package-xyz", "packaging"])
    f_ok = len(problems) == 1 and "definitely-not-a-real-package-xyz" in problems[0]
    result["metrics"]["f_missing_requirement_named"] = bool(f_ok)
    result["metrics"]["f_problems"] = problems

    checks = [a_ok, b_ok, c_ok, d_ok, e_ok, f_ok]
    result["pass"] = all(checks) and manifest.get("fsd_bundle_version") == 2
    result["status"] = "ok" if result["pass"] else "fail"
    result["metrics"]["checks_passed"] = f"{sum(bool(c) for c in checks)}/6"

    shutil.rmtree(work, ignore_errors=True)

except Exception:  # noqa: BLE001 - spec 24: ALWAYS write _result.json, never a bare traceback
    result["status"] = "fail"
    result["pass"] = False
    result["error"] = traceback.format_exc()[-2000:]

OUT.mkdir(parents=True, exist_ok=True)
with open(OUT / "_result.json", "w") as f:
    json.dump(result, f, indent=2)
print(json.dumps(result, indent=2))
print(f"\nwrote {OUT / '_result.json'}")
