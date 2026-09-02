---
status: current
summary: The consumer-repo run — reinstall `rise/.venv` from `fsd@main`, run `build_images.ipynb` then `e2e_austria_aml.ipynb` end to end, capture `[collect]`/`[stac]` against the 616 s / 161 s baseline (spec 57 §9 step 5), and force a stale-entry image rebuild (spec 56 §9 step 10).
---

# Run-book 57 — the consumer-repo e2e run

> Spec 24 run-book. Claude does not run this: it is a credentialed, hours-long, cluster-dispatching
> notebook run. You run it; you paste back each step's `_result.json`; Claude diffs it against the
> success criteria below. **Do not paste logs** — paste the `_result.json`.

## Purpose

Discharge the two spec obligations that only a real run can close, from a **consumer** repo
(`rise/`) installing fsd as a dependency rather than from an fsd checkout:

| | obligation | what it proves |
|---|---|---|
| **A** | **spec 57 §9 step 5** | the 777 s → <100 s post-run window is a *performance claim*. Unmeasured, it is a hypothesis. Needs `[collect]`/`[stac]` timings on a ~300-cell run against the **616 s / 161 s** baseline |
| **B** | **spec 56 §9 step 10** | the **forced stale-entry rebuild** — a registry entry whose AML asset is gone must *build*, then *reuse*. Nothing in the 1068-test suite covers it |

Secondary, and free while you are there: this is the first end-to-end exercise of specs 54/55/56/57
and #92 **as a consumer sees them** — `fsd init` config, `root` as an argument, `ensure_environment`
in place of pasted versions.

## ⚠️ Read before you start

- **Steps run in order and step 6 must be last.** Step 6 deliberately creates a *new* AML
  environment version and starts a real ACR build. Running it before step 5 would leave the e2e
  notebook resolving a half-built image.
- **Cost.** Step 5 is the full e2e (~40–70 min of wall clock, ~300 cluster tasks). Step 6 costs one
  extra 10–20 min ACR build. Nothing else is expensive.
- **Everything you paste back is a leak risk.** `rise/` has no leak-guard equivalent to fsd's
  `tests/test_notebooks.py`, and all four recorded leaks came from prose written about a real run.
  **Scrub before pasting:** no subscription id, resource group, workspace, cluster name, storage
  account, container, UAMI client id, or `abfss://` URL. The `_result.json` templates below are
  already shaped to hold numbers only.

## Prerequisites

- **Repo:** `rise/` — the consumer repo. Working dir for every shell command below is `rise/`.
- **fsd:** `main` @ `f7d4bd0`, **pushed** (`ensure_environment` resolves `@main` through
  `git ls-remote`, so an unpushed commit is invisible to it).
- **Azure:** `az login` done in a terminal, `az extension add -n ml` once per machine.
- **Config:** `~/.config/fsd/config.toml` with all five required keys **plus** `model_registry`
  and `image_registry`.
- **`AZ_ROOT`** exported in the shell that starts the Jupyter kernel — it is *not* config
  (spec 55 D1), the notebook reads it from the environment.
- **Where results go:** `rise/_runbook57/`. Create it; `rise/.gitignore` already excludes it, so
  nothing you paste back can be committed by accident.

---

## Step 0 — patch the e2e notebook's config cell ⚠️ BLOCKER

**`rise/notebooks/e2e_austria_aml.ipynb` cannot run as it stands.** It is a verbatim copy of fsd's
own developer notebook (33 of 34 cells identical), and **code cell 3** carries two fsd-checkout
assumptions that are wrong in a consumer repo:

```python
REPO = pathlib.Path.cwd().parent
assert (REPO / "pyproject.toml").exists(), f"expected an fsd checkout at {REPO}"   # (1)
...
BASE = ImageDefinition(
    name="fsd-aml-env",
    fsd=f"path:{REPO}",                                                            # (2)
    extras=("azure", "mpc"),
)
```

1. `rise/` has no `pyproject.toml`, so **cell 3 raises `AssertionError` immediately**.
2. Worse if you only delete the assert: `fsd="path:{REPO}"` digests a wheel built from *that
   directory* (`digest.py:_resolve_fsd` → `wheel:<hash>`), whereas `rise/notebooks/build_images.ipynb`
   declares `fsd="git+https://github.com/nikhilsrajan/fsd@main"` → `git+…@<40-char sha>`. **Different
   payloads, different digests, different images** — the e2e notebook would not reuse what
   `build_images.ipynb` just built, would start its own ACR build, and would then trip its own
   `assert _r.reused` twenty lines later.

### The edit

In **code cell 3** only, make these two changes:

```diff
 REPO = pathlib.Path.cwd().parent
-assert (REPO / "pyproject.toml").exists(), f"expected an fsd checkout at {REPO}"
 NOTEBOOKS = REPO / "notebooks"
```

```diff
 BASE = ImageDefinition(
     name="fsd-aml-env",
-    fsd=f"path:{REPO}",
+    fsd="git+https://github.com/nikhilsrajan/fsd@main",
     extras=("azure", "mpc"),      # see build_images.ipynb for why not [aml] or [grid]
 )
```

Leave `NOTEBOOKS`, `INFER`, and everything else in the cell alone. Cell 3's comment block above
`BASE` still describes `path:` hashing a wheel — it now describes `git+`, which pins a commit; that
prose is worth a one-line correction but does not affect the run.

**Also fix cell 0's markdown** while you are in there: it says *"Run
[`build_images.ipynb`](./build_images.ipynb) first"* — correct for `rise` — but the body of the
notebook refers to `00_build_images.ipynb` (fsd's filename) in four places. Cosmetic; skip it if you
would rather not touch a notebook you are about to run.

**Verify the patch without opening Jupyter:**

```bash
cd rise
python3 - <<'PY'
import json
nb = json.load(open("notebooks/e2e_austria_aml.ipynb"))
src = "".join(nb["cells"][3]["source"])
ok_no_assert = "pyproject.toml" not in src
ok_git_ref   = 'fsd="git+https://github.com/nikhilsrajan/fsd@main"' in src or \
               "fsd='git+https://github.com/nikhilsrajan/fsd@main'" in src
ok_no_path   = "path:{REPO}" not in src and 'path:{REPO}' not in src
print(json.dumps({"step":"0-patch-notebook",
                  "status":"ok" if (ok_no_assert and ok_git_ref and ok_no_path) else "fail",
                  "pass": bool(ok_no_assert and ok_git_ref and ok_no_path),
                  "metrics":{"assert_removed":ok_no_assert,"git_ref_present":ok_git_ref,
                             "path_ref_removed":ok_no_path},
                  "expected":{"assert_removed":True,"git_ref_present":True,
                              "path_ref_removed":True},
                  "error":None}, indent=2))
PY
```

- **Expect:** `"pass": true`.
- **PASS if:** all three booleans are `true`. Save the output as `_runbook57/step0_result.json`.
- **If it fails:** you edited a different cell. Cell 3 is the long one that starts
  `# Your Azure settings live in ~/.config/fsd/config.toml`.

---

## Step 1 — rebuild `rise/.venv` from `fsd@main`

`rise/.venv` predates specs 55/56/57 and #92. **pip will not refetch a git URL it believes it
already has**, so a plain `pip install -r requirements.txt` is a no-op. A fresh venv is the honest
option and is what this step does; the `--force-reinstall` alternative is below it.

```bash
cd rise
rm -rf .venv
python3.11 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt
```

<details><summary>Alternative: keep the venv, force just the fsd line</summary>

```bash
cd rise && source .venv/bin/activate
pip install --force-reinstall --no-deps \
  "fsd[azure,aml,mpc,grid] @ git+https://github.com/nikhilsrajan/fsd@main"
```
`--no-deps` keeps it from churning the whole tree; it also means a **new** transitive dependency
added since your last install will be missing. If step 2 or 3 raises `ModuleNotFoundError`, take
the fresh-venv path above.
</details>

**Then check what actually landed:**

```bash
cd rise && source .venv/bin/activate
python - <<'PY'
import json, subprocess, importlib.metadata as md
want = "f7d4bd06e3606151ddbb1004086b5fcba58c4fb0"
direct = json.loads(md.distribution("fsd").read_text("direct_url.json") or "{}")
got = (direct.get("vcs_info") or {}).get("commit_id", "")
remote = subprocess.run(["git","ls-remote","https://github.com/nikhilsrajan/fsd","main"],
                        capture_output=True, text=True).stdout.split()
remote_sha = remote[0] if remote else ""
mods = {}
for m in ("fsd.image","fsd.aml","fsd.config","fsd.progress"):
    try:
        __import__(m); mods[m] = True
    except Exception as e:
        mods[m] = f"{type(e).__name__}: {e}"
ok = got == want == remote_sha and all(v is True for v in mods.values())
print(json.dumps({"step":"1-venv","status":"ok" if ok else "fail","pass":ok,
                  "metrics":{"installed_commit":got[:12],"origin_main":remote_sha[:12],
                             "fsd_version":md.version("fsd"),"imports":mods},
                  "expected":{"installed_commit":want[:12],"origin_main":want[:12],
                              "imports":"all True"},
                  "error":None}, indent=2))
PY
```

- **Expect:** `installed_commit` == `origin_main` == `f7d4bd06e360`, every import `true`.
- **PASS if:** `"pass": true`. Save as `_runbook57/step1_result.json`.
- **If `installed_commit` is empty:** pip installed from a cached wheel, not the VCS URL. Take the
  fresh-venv path.
- **If `origin_main` differs from `f7d4bd06e360`:** `main` moved since this run-book was written.
  Stop and say so — the timings would not be measuring spec 57's `main`.

---

## Step 2 — config + Azure preflight

```bash
cd rise && source .venv/bin/activate
python - <<'PY'
import json, os, subprocess
import fsd
keys_ok, missing = True, []
try:
    cfg = fsd.config.load()
except Exception as e:
    keys_ok, cfg = False, None
    missing = [str(e)[:200]]
have = {}
if cfg is not None:
    for k in ("subscription_id","resource_group","workspace","cluster","uami_client_id",
              "model_registry","image_registry"):
        have[k] = bool(getattr(cfg, k, None))
        if not have[k]: missing.append(k)
az = subprocess.run(["az","account","show","--query","id","-o","tsv"],
                    capture_output=True, text=True)
az_ok = bool(az.stdout.strip())
mlext = subprocess.run(["az","extension","show","-n","ml","--query","name","-o","tsv"],
                       capture_output=True, text=True)
ml_ok = mlext.stdout.strip() == "ml"
root_ok = bool(os.environ.get("AZ_ROOT"))
ok = keys_ok and not missing and az_ok and ml_ok and root_ok
print(json.dumps({"step":"2-preflight","status":"ok" if ok else "fail","pass":ok,
                  "metrics":{"config_keys_set":have,"az_logged_in":az_ok,
                             "az_ml_extension":ml_ok,"AZ_ROOT_exported":root_ok},
                  "expected":{"config_keys_set":"all 7 true","az_logged_in":True,
                              "az_ml_extension":True,"AZ_ROOT_exported":True},
                  "error":None if ok else f"missing: {missing}"}, indent=2))
PY
```

- **Expect:** all seven config keys `true`, `az_logged_in` / `az_ml_extension` / `AZ_ROOT_exported`
  `true`. **Nothing above prints a value** — only booleans; that is deliberate.
- **PASS if:** `"pass": true`. Save as `_runbook57/step2_result.json`.
- **If a registry key is unset:** `fsd init --set image_registry=abfss://…/image_registry`
  (same for `model_registry`). `root` is **not** a config key and `fsd init` will not ask for it.

---

## Step 3 — `build_images.ipynb`

Start Jupyter **from the shell that has `AZ_ROOT` exported and `.venv` active**, then run
`rise/notebooks/build_images.ipynb` top to bottom.

```bash
cd rise && source .venv/bin/activate
export AZ_ROOT=abfss://…            # already set from step 2; the kernel inherits this shell
jupyter lab                          # or: code . — whatever you normally use
```

- **Expect,** from Part A and Part B respectively:
  ```
  spec sha256:xxxxxxxxx  ->  fsd-aml-env:N        (reusing; registry fsd-aml-env:M)
  spec sha256:yyyyyyyyy  ->  fsd-infer-sklearn:N  (reusing; registry fsd-infer-sklearn:M)
  ```
- **PASS if:** both cells complete. **`reusing` and `just built` are both passes** — but if either
  says `just built`, open the printed Studio link, wait for **`Build status: Succeeded`** (10–20
  min of ACR time, occasionally flaky), then **re-run that cell** and confirm it now says `reusing`
  before going on. Nothing downstream can run against an image that has not finished.
- **Record** `_runbook57/step3_result.json`:
  ```json
  { "step": "3-build-images", "status": "ok", "pass": true,
    "metrics": { "base_reused": true, "base_aml_version": 0, "base_registry_version": 0,
                 "infer_reused": true, "infer_aml_version": 0, "infer_registry_version": 0,
                 "rebuilt_and_waited": false },
    "expected": { "base_reused": true, "infer_reused": true },
    "error": null }
  ```
  Version *numbers* are fine to paste; the digests and the Studio URLs are not needed.

---

## Step 4 — the e2e notebook, sections 0 → 3

Run `rise/notebooks/e2e_austria_aml.ipynb` from the top, through section 3.5 (`fsd.deploy`).

**One decision before you start.** Cell 3 pins:

```python
RESUME_RUN = 'demo-20260824T121435Z'
```

- **Keep it** to re-enter that archive: the download leg short-circuits (`[download] 0 of 828 assets
  missing; nothing to download`) and section 1 finishes in minutes. **This is the recommended
  choice** — the measurement in step 5 is about `[collect]`/`[stac]`, not about re-downloading
  828 assets.
- **Set it to `None`** only if that run folder no longer exists under your `AZ_ROOT`, or you
  deliberately want a cold archive. That turns step 4 into a multi-hour download.

Check it exists before you commit to it:

```bash
cd rise && source .venv/bin/activate
python - <<'PY'
import json, os
from fsd.storage import fs
from fsd.storage.azure import configure_storage
configure_storage("azure")           # forbid the anonymous fallback, as every verb does
root = f"{os.environ['AZ_ROOT']}/demo-20260824T121435Z"
cat  = f"{root}/imagery/catalog.parquet"
print(json.dumps({"resume_root_exists": fs.exists(root),
                  "catalog_exists": fs.exists(cat)}, indent=2))
PY
```

If both are `true`, keep `RESUME_RUN` as it is.

- **Expect,** as you go:
  - §1 `create_training_data` — `[plan] … CURRENT` or a small shortfall; not the measurement.
  - §3.2 `verify_adapter` — `report["pass"]` true; **open the printed `output.tif` in QGIS**. The
    verdict line is assistive; the raster is the deliverable.
  - §3.4 `verify_image` — `vres["pass"]` true.
  - §3.5 `fsd.deploy` — prints `crop-rf:N` and a `Resolved(...)` line.
- **PASS if:** every assert in sections 0–3 passes and 3.5 prints a model ref.
- **Record** `_runbook57/step4_result.json`:
  ```json
  { "step": "4-e2e-sections-0-3", "status": "ok", "pass": true,
    "metrics": { "resume_run_used": true, "training_fields": 900,
                 "verify_adapter_pass": true, "verify_adapter_cube_t": 10,
                 "verify_image_pass": true, "model_version": 0,
                 "qgis_output_eyeballed": true },
    "expected": { "verify_adapter_pass": true, "verify_adapter_cube_t": 10,
                  "verify_image_pass": true },
    "error": null }
  ```

---

## Step 5 — ⭐ the measurement: sections 4.1 + 4.2

**This is obligation A.** Run §4.1 (`fsd.download`, seconds under `RESUME_RUN`) then §4.2
(`fsd.run_inference` over `AT_ROI`, 299 cells, `merge="reproject"`).

**The two lines to capture** are printed by spec 57 D1's segment ticker, at the very end of the
run, after the fan-out finishes. Their exact shape (`fsd/progress.py:ticker`) is:

```
[collect] 299/299 outputs (100%) | 3.4 outputs/s | elapsed 88s | eta 0s
[stac] 301/301 objects (100%) | 12.0 objects/s | elapsed 25s | eta 0s
[merge] 299/299 inputs (100%) | … | elapsed …s | eta 0s
```

Take **`elapsed`** from the final (100%) line of each. `[merge]` is context, not the claim — it is
299 real pixel reads and spec 57 does not touch it.

### The baseline and the prediction

| segment | baseline (pre-D1, #61's measurement, 300 cells) | spec 57 predicts |
|---|---|---|
| `[collect]` | **616 s** (2.05 s/output) | |
| `[stac]` | **161 s** (0.53 s/object) | |
| **combined** | **777 s** | **< 100 s** |

### How to grade it

| combined `[collect]` + `[stac]` | verdict |
|---|---|
| **< 100 s** | **prediction met.** Obligation A discharged as specified |
| **100–250 s** | **PASS with a finding** — a ≥3× win, prediction missed. Paste both numbers; this becomes a GitHub issue, not a re-run |
| **> 250 s** | **the optimisation did not land.** A finding, not a failure to hide — spec 57 D1 exists precisely because #61 spent a cycle blaming a "627 s bundle upload" that measurement showed to be 13 s. Paste the numbers and stop |

- **PASS if:** `run_inference` returns, `len(result.output_filepaths)` is 299, and a
  `stac_catalog_filepath` is printed. The timing verdict is reported separately from pass/fail —
  **a slow run that completes is still a pass for the pipeline and a finding for the spec.**
- **Expected side-effect, already filed:** re-running §4.2 starts ~299 tasks even when nearly
  everything is done — the per-output skip happens on the node *after* dispatch
  ([#77](https://github.com/nikhilsrajan/fsd/issues/77)). Not a defect of this run.
- **Record** `_runbook57/step5_result.json`:
  ```json
  { "step": "5-inference-timings", "status": "ok", "pass": true,
    "metrics": { "cells": 299, "outputs": 299, "stac_objects": 301,
                 "collect_elapsed_s": 0, "collect_rate_outputs_per_s": 0.0,
                 "stac_elapsed_s": 0, "stac_rate_objects_per_s": 0.0,
                 "merge_elapsed_s": 0, "wall_clock_min": 0,
                 "driver_location": "laptop-over-vpn" },
    "expected": { "collect_elapsed_s": 616, "stac_elapsed_s": 161,
                  "combined_prediction_s": 100 },
    "error": null }
  ```
  `expected` here carries the **baseline** for `collect`/`stac` and the spec's **prediction** for
  the combination — that is what Claude diffs against.

### Stop / observe

- **Progress:** every long leg prints a throttled ticker line (≤ one per 2 s) with rate, elapsed
  and ETA. Silence for more than ~30 s on a leg that had been ticking is worth noting.
- **Abort:** interrupt the kernel. `run_inference` resumes: `output_folderpath` is the identity of
  the run, so re-running the same cell picks up where it stopped (at the cost of #77's re-dispatch).
- **Do not** delete `output_folderpath` to "start clean" — that is the resume cache.

---

## Step 6 — ⭐ the forced stale-entry rebuild (**LAST**)

**This is obligation B, spec 56 §9 step 10 / D4 step 3.** It proves that a registry entry whose AML
asset no longer exists **rebuilds**, and that the rebuild **repoints `_aml.json`** so the very next
call **reuses** instead of rebuilding forever.

**Cost: one real 10–20 min ACR build.** Run it after step 5, never before — it creates a new AML
environment version, and an image mid-build must not be what the e2e notebook resolves.

Run this in the **same kernel** as the notebook (the storage seam is already configured by cell 3's
`ensure_environment(storage="azure")` calls) — a new cell at the bottom, in three parts.

### 6a — break it

```python
import json
from fsd.image import registry as ireg

NAME = "fsd-aml-env"
V    = _env.registry_version            # from cell 3's EnsureResult
before = ireg.read_aml_record(NAME, V, IMAGE_REGISTRY)
print("before:", {"aml_version": before["version"]})     # the real AML version

ireg.write_aml_record(NAME, V, {**before, "version": "999999"}, IMAGE_REGISTRY)
print("broken: _aml.json now points at version 999999")
```

`999999` is a version `az ml environment show` will not find, which is exactly D4 step 3's
"the asset was deleted" case. `_aml.json` is a mutable sidecar *outside* `image.json`, so this
cannot disturb the content digest — the definition is unchanged, only its pointer is wrong.

### 6b — first call: expect a BUILD

```python
r1 = fsd.aml.ensure_environment(
    BASE, registry=IMAGE_REGISTRY,
    resource_group=cfg.resource_group, workspace=cfg.workspace, storage="azure",
)
print("reused:", r1.reused, "| aml:", r1.version, "| registry:", r1.registry_version)
assert not r1.reused, "expected a BUILD: the registry pointed at a nonexistent AML asset"
assert r1.registry_version == V, (
    "publish is idempotent by digest, so an unchanged definition must return the SAME "
    f"registry version: got {r1.registry_version}, expected {V}")
```

- **Expect:** `reused: False`, a **new** AML version, `registry_version` **unchanged** (the
  definition did not change, only its asset).
- A `build_url` is printed by the notebook's own helper if you re-use that pattern. You do **not**
  need to wait for the ACR build to finish before 6c: `az ml environment create` registers the
  asset immediately and `environment_exists` queries the asset, not the build.

### 6c — second call: expect a REUSE

```python
r2 = fsd.aml.ensure_environment(
    BASE, registry=IMAGE_REGISTRY,
    resource_group=cfg.resource_group, workspace=cfg.workspace, storage="azure",
)
print("reused:", r2.reused, "| aml:", r2.version)
assert r2.reused, "expected a REUSE: 6b should have repointed _aml.json"
assert r2.version == r1.version, "reuse must hand back 6b's asset, not a third one"

after = ireg.read_aml_record(NAME, V, IMAGE_REGISTRY)
print("after :", {"aml_version": after["version"]})
assert str(after["version"]) == str(r1.version)
```

- **Expect:** `reused: True`, the same AML version 6b created, `_aml.json` healed.
- **This is the whole point:** without `write_aml_record` the registry would keep pointing at the
  broken asset and every subsequent call would rebuild a 10–20 minute image forever.

**Then, once the ACR build finishes,** open the Studio link and confirm `Build status: Succeeded`
so the new version is usable. If it fails, that is an ACR flake, not a spec-56 finding — re-run 6b.

- **PASS if:** 6b is a build with an unchanged `registry_version`, and 6c is a reuse of 6b's asset.
- **Record** `_runbook57/step6_result.json`:
  ```json
  { "step": "6-stale-entry-rebuild", "status": "ok", "pass": true,
    "metrics": { "aml_version_before": 0, "aml_version_after_build": 0,
                 "registry_version_before": 0, "registry_version_after": 0,
                 "first_call_reused": false, "second_call_reused": true,
                 "aml_record_healed": true, "acr_build_succeeded": true },
    "expected": { "first_call_reused": false, "second_call_reused": true,
                  "registry_version_after": "same as before",
                  "aml_record_healed": true },
    "error": null }
  ```

---

## Success criteria

The run passes when **every** step's `"pass"` is `true`. Concatenate the seven files and paste that:

```bash
cd rise && python3 -c "
import json,glob
print(json.dumps([json.load(open(f)) for f in sorted(glob.glob('_runbook57/step*_result.json'))], indent=2))"
```

Steps 0–4 and 6 are binary. **Step 5 is the one with a graded outcome** — its `"pass"` covers
*did the pipeline complete*, and the timing verdict is read separately from its `metrics` against
the baseline in `expected`.

## What this unblocks

- **#55** (docs refactor, step 3 of THE ORDER) is gated on step 5's timed report.
- **#80** (snakemake → `[local]`, s3fs → `[s3]`) may land any time after; it cannot change runtime
  behaviour, so it never forces a re-run of this.
- **#82** (cut + push `v0.1.0`) — **the tag is last**, and only once this notebook has actually run.

## Related

- `specs/57-collect-and-stac-round-trips.md` §9 step 5, D1 — the segment ticker this measures.
- `specs/56-image-definitions-and-registry.md` §9 step 10, D4 — the stale-entry contract step 6 proves.
- `specs/55-root-leaves-the-config.md` D1/D3 — why `AZ_ROOT` is exported and not configured.
- `runbooks/38-inference-on-aml.md` — the fsd-side ancestor of step 5.
- `docs/reference/environment.md` — every `AZ_*` name, what sets it, and how to verify it.
