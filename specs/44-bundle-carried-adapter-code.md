---
status: current
summary: Phase 1 — the bundle carries the adapter's source, so the inference image stops being per-adapter and becomes per-dependency-family; supersedes spec 38 D4's "the adapter is never shipped inside the bundle". Phase 2 — P6 `deploy` registers a bundle to a versioned blob store so it stops re-uploading every run.
---

# Spec 44 — bundle-carried adapter source (phase 1) + P6 `deploy` registration (phase 2)

**Status: ✅ PHASE 1 SIGNED OFF, IMPLEMENTED, AND PROVEN ON THE CLUSTER (2026-08-19).**
Signed off by the user ("yes, sign off on the D4 reversal — implement phase 1"); acceptance
criterion 12 was met the same day — the D11 adapter-import smoke returned `status: "ok"` on
**`fsd-infer-sklearn:3`, an image containing no adapter source**, with `my_adapter:CropRF` resolved
purely from the bundle's `code/`. **The per-adapter inference image is dead.** Sign-off covers §0 (the spec 38 D4 reversal) and §3 D1–D6. **Phase 2 (D7/D8) is NOT
signed off** — questions 5 and 7 of §8 remain open. **Amendment A1 (§9) corrects D2 and was written
before implementation began — read it with D2.** Two phases, deliberately separable.
**Phase 1 is the implementable one**; phase 2 is scoped and its store decision is put up for
sign-off here (it closes an open question that has been sitting in `ROADMAP.md` §7), but it is a
later session's build.

> **The one sentence:** **code moves into the bundle; dependencies stay in the image.**
> An inference image then differs only by *dependency family* (sklearn vs torch) — never by model,
> never by adapter. Swapping a model stops being a Docker build.

> **⚠️ This spec REVERSES two LOCKED decisions in `specs/38-inference-on-aml.md` D4.** See §0.
> Nothing may be implemented against spec 44 until §0 is signed off, because D4 is currently the
> authority and says the opposite.

---

## 0. What this supersedes (read first)

`specs/38-inference-on-aml.md` **D4 — "A dedicated inference Environment carries the adapter + its
deps [LOCKED]"** contains two claims spec 44 reverses:

| spec 38 D4 says | spec 44 says | why it changes |
|---|---|---|
| "The adapter is **not** shipped inside the bundle … it is a pip dependency of the Environment, exactly like `fsd` itself is." | The adapter's **source ships inside the bundle**; the Environment carries only its *dependencies*. | Measured cost of the D4 procedure: to deliver **one `.py` file** to the nodes the user hand-wrote **4 files** (Dockerfile, `.dockerignore`, 2 AML YAMLs), built a wheel, ran `az ml environment create`, and ran a smoke job. Per model. See §1. |
| "**Where the coupling lands later: P6 `deploy()` [LOCKED — user, 2026-07-23]** … `deploy(bundle)` … is the appropriate home for *building the image*." | `deploy` **never** builds images or calls `az ml`. It registers a bundle to the storage seam. | Image-building is Azure-specific plumbing; putting it in `fsd.api` fights the runner/storage seam (ADR-0001/0002) and would make `deploy` un-runnable on any other backend. Rejected by the user, 2026-08-18. |

**Everything else in D4 survives unchanged** and this spec depends on it:
- a **dedicated inference Environment**, separate from the generic build image — still yes;
- the **operator** owns building/registering Environments, Claude never runs `az ml` — still yes;
- the dispatcher **references the Environment by name**, no per-run image build — still yes;
- dependency installation is **front-loaded to image build time**, never `pip install` on a cold
  node — still yes, and §3 D5 leans on it;
- the **D11 one-node adapter-import smoke** stays the gate — and gains a job (§3 D5).

What actually changed is *which* of the model author's two deliverables the image encodes. D4 fused
"the adapter" and "its dependency closure" into one immutable unit. They have different change
rates: **the adapter changes every time the model is retrained; its dependency set almost never
does.** Baking the fast-changing thing into the slow-changing artifact is the defect.

**On sign-off, spec 38 gains an amendment note** pointing at this spec (it must not be left reading
as current), and `runbooks/38-inference-on-aml.md` → "Build the inference Environment (D4)" loses
its per-adapter steps. Neither is edited before sign-off.

---

## 1. The problem, measured

**The trigger (user, 2026-08-18, building a live demo).** `notebooks/e2e_austria_aml.ipynb` cell 18
is the D4 procedure written out verbatim. To get `my_adapter.py` — a single file, ~40 lines — onto
the cluster nodes, it requires:

1. `demo_model/Dockerfile` (hand-written)
2. `demo_model/.dockerignore` (hand-written)
3. `demo_model/infer-environment.yml` (hand-written)
4. `demo_model/infer-env-smoke.yml` (hand-written)
5. `pip wheel` of fsd into that folder
6. `az ml environment create`
7. a smoke job to prove the image imports the adapter

…and **all seven repeat whenever the adapter class changes**, because the source is baked into the
image layer. Retraining a model and shipping a new `rf.joblib` needs none of it (the bundle carries
the weights); changing one line of `features` needs all of it.

**Where the code already almost travels.** Three facts, verified in source this session:

| fact | where |
|---|---|
| `bundle.save` copies any local file named in `artifacts` into the bundle, keyed by basename | `src/fsd/model/bundle.py::save` |
| `_stage_bundle` copies `bundle.json` + **every file the manifest names** to blob — manifest-driven, no directory listing | `src/fsd/workflows/runners.py:787` |
| `fetch_bundle_to_scratch` pulls every file the manifest names down to node-local scratch | `src/fsd/workflows/infer_shard.py:49` |

So the transport for arbitrary bundle files **already exists, is manifest-driven, and is proven on
the cluster.** A `.py` file is just another file to it.

**The single gap.** `bundle.load` calls `resolve_ref` → `importlib.import_module(...)` **before**
anything from the bundle is on `sys.path`, and node-local scratch is never added to `sys.path`
(`src/fsd/model/bundle.py::load`, `::resolve_ref`). Both node entrypoints that need an adapter —
`workflows/adapter_smoke.py` and `workflows/infer_shard.py` — go through `bundle.load`.

**Therefore phase 1 is small:** a manifest field, a copy loop in `save`, and a `sys.path` insert in
`load`. No new transport, no new storage primitive, no dispatcher change, no Azure code.

**The second cost, and phase 2's trigger.** Every ROI inference run stages the whole bundle to blob:
a **measured 627 s for 13 MB over VPN** (comment in `api._run_inference_roi`). That is per run, for
a bundle that does not change between runs. Registering a bundle once (phase 2) deletes that cost
*and* gives models versioned refs. `fsd.deploy` is a `NotImplementedError` stub today
(`src/fsd/api.py:1286`) and P6 — "Deploy/registration UX; model-bundle push/register" — is the last
unbuilt roadmap phase (`ROADMAP.md:302`).

---

## 2. Scope

**In scope — phase 1 (implementable on sign-off):**
- A `code` block in `bundle.json` + the files it names, written by `bundle.save`.
- Automatic detection of the adapter's source from the adapter object — **the user's existing
  bundling cell does not change** (D1, D3).
- `sys.path` handling in `bundle.load`, with a defined precedence and a collision guard (D2).
- Classification of adapters that must **not** be embedded (pip-installed) and adapters that
  **cannot** be embedded (notebook `__main__`) (D3).
- What the drift check means once the class ships with the bundle (D4).
- An optional, **informational** `requirements` declaration, checked by the D11 smoke job — fsd
  never installs anything at run time (D5).
- Bundle format version 2, backward-compatible with version 1 (D6).

**In scope — phase 2 (scoped + store decision proposed here; built later):**
- `fsd.deploy(bundle_dir, storage=…) -> "<name>:<version>"` registering to a versioned store (D7).
- `run_inference(model="<name>:<version>")` resolving a ref without re-uploading (D8).

**Not in scope — deliberately:**
- **`deploy` building Docker images or calling `az ml`/`az acr`.** Rejected (§0). The operator
  builds Environments; that stays a run-book step.
- **Installing dependencies at run time.** Spec 38 D4's front-loading rationale is correct and
  survives (§3 D5).
- **Auto-inferring the adapter's dependency set.** MLflow's requirement inference is its most
  fragile surface; fsd declares, it does not guess (D5, §6/§7).
- **Serializing the adapter *object* (cloudpickle by-value).** Considered and rejected — D1
  rationale, §6/§7.
- **Sandboxing / trust boundaries.** A bundle already ships `rf.joblib`, which executes arbitrary
  code on unpickle. Shipping `.py` alongside it adds **no new boundary**. (Settled with the user,
  2026-08-18. One consequence *is* stated: D2's driver rule.)
- **Multi-bundle-per-process serving.** fsd loads one bundle per process today (§3 D2). The guard
  in D2 makes the unsupported case loud instead of silent; it does not make it supported.
- Issues **#64** (no-op download costs a cold start), **#65** (silent AML dispatch/poll/merge),
  **#66** (stale `input.csv` ignores a changed ROI) — adjacent, filed, out of scope.

---

## 3. Decisions

### D1 — `bundle.save` embeds the adapter's source automatically, layout preserved, under `code/`

`save` gains two optional keyword arguments; **all existing call sites keep working unchanged**:

```python
save(adapter, artifacts, dst, *, overwrite=True,
     code=None,           # None = auto-detect (D3); a list of paths = explicit override;
                          # False = never embed (force the spec-38 D4 installed-package path)
     requirements=None)   # D5
```

**Auto-detection.** From `type(adapter)`:
1. `mod = cls.__module__`, `src = inspect.getsourcefile(cls)`.
2. Classify `src` (D3). If not embeddable → record no `code` block (or raise).
3. **Root selection.** `depth = mod.count(".")`; walk `depth + 1` directories up from `src` to get
   the importable root. For a single module `my_adapter` that is the containing directory and the
   embedded set is just `my_adapter.py`. For `my_pkg.adapters` it is the parent of `my_pkg/`, and
   the embedded set is the **whole `my_pkg/` tree, layout preserved**.
4. Copy into `<bundle>/code/`, **preserving the path relative to that root** — so
   `my_pkg/sub/helper.py` lands at `code/my_pkg/sub/helper.py`.
5. Record **every copied file** in the manifest.

> **Layout preservation is the whole point of step 4.** MLflow's `code_paths` *flattens*: a file at
> `src/utils.py` is copied to `code/utils.py`, which is why its own docs tell users to rewrite their
> import statements and warn that relative imports need "a common root path"
> ([MLflow, *Managing Dependencies in MLflow Models*](https://mlflow.org/docs/2.21.3/model/dependencies/)).
> fsd preserves the tree, so a package that imports itself keeps working with no edits.

**Excludes and a cap.** Skip `__pycache__/`, `*.pyc`, `.git/`, `.venv/`, `.ipynb_checkpoints/`, and
dotfiles (Ray's `working_dir` excludes the same class of directory —
[Ray, *Environment Dependencies*](https://docs.ray.io/en/latest/ray-core/handling-dependencies.html)).
**Refuse** an auto-detected code set above **64 files or 5 MB** with an actionable error naming the
explicit `code=[...]` override. Rationale: auto-walking a package root is convenient right up until
it sweeps a `data/` folder into every run's upload; a loud early refusal beats a slow surprise.
(Ray caps `working_dir` at 500 MiB for the same reason; fsd's number is deliberately far smaller
because this is *adapter source*, not a workspace.)

**Why source files and not a pickled object.** `cloudpickle.register_pickle_by_value` would let the
adapter *object* travel with its class by value, and is the obvious alternative. Rejected:
cloudpickle documents the feature as **experimental**, and pickle-by-value couples the artifact to
the interpreter/library versions on both ends
([cloudpickle README](https://github.com/cloudpipe/cloudpickle/blob/master/README.md)) — the exact
coupling a bundle exists to avoid. `bundle.json` + plain `.py` stays inspectable, diffable, and
loadable by a human. It also keeps `read_spec`'s model-free preflight literally free.

**The `feature` descriptor in the manifest stops being the only provenance.** `_feature_descriptor`
records step *names* because "the executable version is the code" and the code was elsewhere. With
D1 the executable version is **in the bundle**. The descriptor stays (it is what model-free
preflight reads), but its docstring should stop implying the code is unavailable.

### D2 — `load` prepends `<bundle>/code` to `sys.path`; bundle wins; collisions are refused

**Precedence: bundle-first.** `sys.path.insert(0, <bundle>/code)` before `resolve_ref`. Python
searches `sys.path` in order and the first match wins
([Python, *The import system*](https://docs.python.org/3/reference/import.html)), so an embedded
`my_adapter` shadows any same-named module in the image. That is the correct answer: the bundle is
the authority on which model this is, and D4's drift check (below) exists precisely because the
image can be stale.

MLflow makes the same choice — code paths are prepended at load time — and the resulting failures
are well documented, so fsd takes the choice **and** the mitigation:

**The collision guard (new; prior art has this bug).** Before inserting, if `manifest["adapter"]`'s
module name is **already in `sys.modules`** and its `__file__` is **not** the file the bundle is
about to provide, `bundle.load` **raises** with both paths named. Without this, the second bundle
loaded into one process silently gets the *first* bundle's class — reported against MLflow as
[mlflow#12377](https://github.com/mlflow/mlflow/issues/12377) ("`code_path` appends to `sys.path`
and imported modules cached in `sys.modules`" → the second model imports the first model's code)
and [mlflow#6028](https://github.com/mlflow/mlflow/issues/6028). MLflow cannot detect it; fsd can,
in four lines, because fsd knows the exact file it intends to provide.

fsd loads **one bundle per process today** — `infer_shard` runs one bundle per job, and
`run_local_inference` with `cores>1` crosses subprocesses (`api._ensure_bundle`). So the guard
should never fire in normal use. It exists so that the day it does, the failure is a loud error
naming two files rather than a model quietly predicting with the wrong weights.

**Idempotence.** Loading the same bundle twice must not push duplicate `sys.path` entries.

**`sys.path` is mutated, and that is a documented side effect.** `load` is not pure; the docstring
must say so. `read_spec` remains untouched and import-free — **model-free preflight on the driver
never puts bundle code on the driver's path.** That is the one trust consequence worth stating: the
driver (the user's laptop) reads manifests; only the process that is *deliberately* about to run the
model imports the model's code.

### D3 — Three origins, three behaviors: embed, skip, refuse

`save` classifies the adapter class's source file:

| origin | test | behavior |
|---|---|---|
| **local source** | resolvable file that exists and is **not** under a site-packages / dist-packages / stdlib root | **Embed** (D1). |
| **installed package** | file is under `site.getsitepackages()`, `site.getusersitepackages()`, or `sysconfig.get_paths()` `purelib`/`platlib`/`stdlib`/`platstdlib` | **Skip.** No `code` block; `"code_origin": "installed"` recorded. This is exactly spec 38 D4's world and it stays valid — an adapter that really is a pip package belongs in the image. |
| **unresolvable** | `__module__ == "__main__"`, or `getsourcefile` raises / returns `None` / returns a path that does not exist (notebook cells give `/tmp/ipykernel_*/1234.py`), or a C extension | **Refuse**, with an actionable message. |

Verified locally (2026-08-19, `fsd/.venv`): `examples/eurocrops_rf.py` → local source;
`numpy`/`joblib` → installed; the walk-up rule yields the right root for a dotted module.

**Why refuse rather than warn on `__main__`.** Today `save` cheerfully writes
`adapter: "__main__:CropRF"` and the run fails on a cluster node with a `ModuleNotFoundError`, after
a cold start. Refusing at `save` converts a slow remote failure into an instant local one. The
message must name the fix the user already uses: *put the class in a `.py` file next to the
notebook and import it.*

**Known classification edge — editable installs.** A package installed with `pip install -e .`
resolves to its source tree, not site-packages, so it classifies as **local source** and gets
embedded. Verified: `fsd.model.bundle` itself classifies that way in this venv. This is the **safe**
answer — an editable install is by definition not the thing that shipped in the image — but it is
surprising, so it is documented and the size cap (D1) is the backstop. `code=False` is the escape.

**`fsd`'s own modules are never embedded**, regardless of classification: an adapter subclassing
`fsd.model.adapter.BaseModelAdapter` must not drag `src/fsd/` into the bundle. Only the module that
*defines the adapter class* (and its package, if any) is a candidate.

### D4 — The drift check keeps running, but means something different per origin

`load`'s existing check compares the freshly-imported class's declared spec fields against
`bundle.json`. Once the class ships **inside** the bundle, both sides came out of the same `save`
call, so disagreement is no longer possible from version skew:

- **Embedded adapters** → the check becomes a **self-consistency / tamper** check. Keep it (it is
  nearly free and catches a hand-edited `bundle.json`), but change the error text: *"bundle.json
  disagrees with the adapter source **inside this bundle** — the bundle has been edited"*, not
  today's "code/bundle drift".
- **Installed-package adapters** → the check keeps its **current** meaning and full value: the
  image's pip version vs. the bundle. This is where it earns its keep, and it is unchanged.

**The instance-vs-class asymmetry is unchanged and must stay.** The user sets `n_timestamps` on the
*instance* before `save` (notebook cell 17), while `load` instantiates a fresh `cls()` whose class
default is `0` — the existing skip rule (`None` / `[]` / `n_timestamps == 0`) is what lets one
adapter class back models trained on different `T`. D1 does not touch it.

**Deferred, not decided here:** recording a `sha256` per embedded code file, which would also give
phase 2 a natural version key. It complicates the manifest's flat file list for a corruption case
the transport does not currently exhibit. **File as a GitHub issue at sign-off**, do not build.

### D5 — Dependencies are *declared* in the manifest and *checked* by the smoke job — never installed

Optional `requirements` in `bundle.json`, **user-supplied** (`save(..., requirements=[...])`),
PEP 508 strings:

```json
"requirements": ["scikit-learn>=1.5", "joblib"]
```

- **fsd never installs them.** Spec 38 D4's rationale — front-load dependency installation to image
  build time so a missing `sklearn` fails once, not on every cold node — is correct and unchanged.
- **The D11 one-node adapter-import smoke gains a check**: for each declared requirement, is it
  satisfied in the node's Environment? Failure names the exact missing/mismatched dependency, once,
  before the fan-out. This is the natural home — the smoke job already exists to catch exactly the
  "`ModuleNotFoundError` on a cold node" failure.
- **Borrow the parser; do not hand-roll PEP 508.** The check is
  `packaging.requirements.Requirement` + `importlib.metadata.version` (stdlib) — about eight lines,
  and it gets extras, environment markers and version specifiers right, which a hand-rolled parser
  will not. Verified in `fsd/.venv` on 2026-08-19: `scikit-learn>=1.5` → satisfied (1.9.0),
  `torch>=2` → correctly reported missing. **`packaging` must be added to `pyproject.toml`
  `dependencies`** — it is present today only transitively (25.0), which is not a contract.
- **Never auto-inferred.** MLflow infers requirements and documents that inference "will not work
  across module boundaries or if your custom code is defined in an entirely different library"; fsd
  declares instead. Absent `requirements` = "not declared", which is silently fine (today's
  behavior).

This decision is what makes the headline true: **code in the bundle, deps in the image.** The image
becomes generic per *dependency family* — one sklearn inference image serves every sklearn adapter
the user will ever write; a torch image serves the torch ones.

### D6 — `fsd_bundle_version` 2, backward-compatible

Bump `BUNDLE_VERSION` to `2`. `load` accepts **1 and 2**. A version-1 bundle has no `code` block,
which is indistinguishable from a version-2 installed-package bundle — both mean "resolve the ref
from the environment", i.e. today's behavior. **No existing bundle breaks.** `_stage_bundle` and
`fetch_bundle_to_scratch` gain the `code` file list alongside `artifacts`; both stay manifest-driven
with no directory listing (the property spec 38 D3 locked).

Proposed manifest shape (additive; nothing existing moves):

```json
{
  "fsd_bundle_version": 2,
  "adapter": "my_adapter:CropRF",
  "artifacts": {"model": "rf.joblib"},
  "code_origin": "bundled",
  "code": {"root": "code", "files": ["my_adapter.py"]},
  "requirements": ["scikit-learn>=1.5", "joblib"],
  "feature": {"...": "unchanged"},
  "required_bands": ["B04", "B08"], "n_timestamps": 10, "...": "unchanged"
}
```

### D7 — [PHASE 2, PROPOSED] `deploy` registers to a **versioned blob path via the storage seam**

This closes `ROADMAP.md` §7's open question, *"Where the model bundle is stored/registered on cloud
(ACR? blob? AML registry?)"*.

**Proposed: blob (via `fsd.storage`), with an fsd-owned immutable version convention.**

```
<root>/models/<name>/<version>/bundle.json + artifacts + code/
<root>/models/<name>/latest            # a pointer file, not a copy
```

`fsd.deploy(bundle_dir, storage=…, name=…) -> "crop-rf:3"`. Versions are **immutable** — deploying
over an existing version is refused; `latest` is the only mutable name.

| option | verdict |
|---|---|
| **blob via the storage seam** | **Chosen.** It is the seam fsd already has, so S3/local work for free and nothing Azure-specific enters `fsd.api`. Versioning is hand-rolled, but "immutable directory + a pointer file" is about 30 lines. |
| **ACR** | Rejected. Pairs bundle with image — which is precisely the coupling phase 1 exists to break. Retraining would become a `docker push`. |
| **AML registry** | Rejected. Versioning is free, but it is Azure lock-in inside the one module that must stay backend-agnostic, and it fights the runner seam. It can be added later as a *storage backend*, not as `deploy`'s definition. |

### D8 — [PHASE 2, PROPOSED] `run_inference(model="<name>:<version>")` resolves without re-uploading

A registered ref resolves to its blob path; the dispatcher stages **nothing** because the bundle is
already where the nodes read from. This is what deletes the **measured 627 s per run**. A local
bundle path keeps working exactly as today, so phase 2 adds a fast path rather than replacing one.

---

## 4. Acceptance criteria

**Phase 1** (synthetic tests unless marked; nothing needs Azure):

1. `save` on an adapter defined in a plain local module writes `code/<module>.py` and a manifest
   naming it; **the user's notebook cell 17 is unchanged** and produces a bundle whose
   `read_spec(...)["adapter"]` still prints `my_adapter:CropRF`.
2. `save` on an adapter from a **package** (`my_pkg.adapters:X`) embeds the whole `my_pkg/` tree
   with layout preserved, and the package's own intra-package imports resolve after `load`.
3. `save` on an adapter whose class comes from an **installed** package writes **no** `code` block
   and `"code_origin": "installed"`; `load` behaves exactly as it does today.
4. `save` on a class with `__module__ == "__main__"` **raises**, and the message names the fix.
5. `load` of an embedded bundle succeeds **in a process where the adapter module is not importable
   from anywhere else** — the test must ensure the module is genuinely absent from `sys.path`. This
   is *the* test: it is the D4-image-replacement proof.
6. `load` **raises** when a different module of the same name is already in `sys.modules`, naming
   both files (D2 collision guard).
7. Loading the same bundle twice adds no duplicate `sys.path` entry.
8. A version-1 bundle (no `code` block) loads unchanged — regression proof for D6.
9. `save` refuses an auto-detected code set over the cap, naming the `code=[...]` override.
10. `_stage_bundle` and `fetch_bundle_to_scratch` (mocked at the storage boundary, as spec 38's
    tests already are) transfer every code file and no others.
11. `adapter_smoke` reports a declared-requirement miss as a named dependency, not a traceback (D5).
12. ✅ **MET 2026-08-19 — Real-cluster gate (user-run, run-book):** the demo runs end to end against an inference
    Environment built **without** `my_adapter.py` baked in. Success = the notebook keeps only
    `bundle.save`, and cell 18's seven steps are deleted. This is a **run-book**, not something
    Claude runs (`CLAUDE.md`) — **`runbooks/45-verify-bundle-carried-code.md`**, whose Phase 0
    (`runbooks/scripts/45_verify_bundle_code.py`) checks criteria 1–9 **offline in ~10 s** before
    any cloud money is spent, and whose Phase 3 covers the one migration step (a bundle saved
    before 2026-08-19 has no `code/` block and must be re-saved).

**Phase 2:** deferred to its own spec section/sign-off; the criterion is "a second run of the same
model stages 0 bytes and the 627 s disappears".

---

## 5. Risks

| risk | mitigation |
|---|---|
| Auto-detection embeds a huge tree (editable install, package with data) | D1 size cap + excludes; `code=[...]` and `code=False` escapes; D3 documents the editable-install edge |
| `sys.path` shadowing surprises a user whose image *also* has the module | D2 makes bundle-first explicit and documented; the collision guard turns the dangerous half into an error |
| Users think fsd now installs their deps | D5 is declare-and-check only; the smoke job's failure message must say "install it in the Environment" |
| Bundle uploads grow (source is small, but the cap is 5 MB) | Phase 2 (D7/D8) removes the per-run upload entirely; until then the delta over 13 MB of weights is noise |
| Spec 38 D4 left reading as current → a future session re-derives the old design | §0 mandates the amendment note **at sign-off**, plus the run-book edit |

---

## 6. Alternatives considered — could a library do this instead? (user, 2026-08-19)

Fair question, and the same build-vs-borrow shape as the rslearn evaluation
(`RSLEARN_COMPARISON.md`). Answered in three tiers, with the numbers that decide it.

### 6.1 Borrow — adopted into this spec

**`packaging` + `importlib.metadata` for D5's requirement check.** Adopted above. Hand-rolling PEP
508 parsing would be the one place in this spec where writing it ourselves is plainly worse.

### 6.2 MLflow for **phase 1** — evaluated and rejected

MLflow is the real contender, not a strawman. `mlflow.pyfunc.save_model` / `load_model` work
**entirely on a local directory with no tracking server**, and they already do four of the five
things phase 1 needs: an `MLmodel` manifest, an `artifacts` dict, `code_paths` file shipping with a
`sys.path` insert at load, and a `requirements.txt`. On overlap alone it is a genuine match.

It is rejected for phase 1 on four measured counts:

1. **The integration is bigger than the thing it replaces.** Phase 1's delta against an
   already-proven transport is one manifest field, a copy loop in `save`, and a `sys.path` insert in
   `load` — call it ~100 lines. Adopting MLflow means rewriting `bundle.save`/`load`/`read_spec`,
   `_stage_bundle`, `fetch_bundle_to_scratch` and `adapter_smoke` around a foreign object model.
   That is spec 18 F5 re-opened, not spec 44 delivered.
2. **Dependency cost, measured 2026-08-19 from PyPI metadata.** `mlflow` 3.15.1 requires 20 packages
   *on top of* `mlflow-skinny` — Flask, gunicorn, waitress, docker, alembic, sqlalchemy, scipy,
   matplotlib, graphene, huey. And **`mlflow-skinny` is not skinny**: 20 required deps of its own,
   including **`fastapi`, `starlette`, `uvicorn`** (a web-server stack), `databricks-sdk`,
   `protobuf`, `pydantic`, `gitpython` and three `opentelemetry-*` packages. fsd core currently
   declares **13** dependencies. Adding a web server and a telemetry SDK to every inference image in
   order to deliver one `.py` file inverts the cost this spec exists to remove.
3. **It brings a second storage abstraction with a worse credential story.** MLflow's artifact store
   is its own layer — **not fsspec** — and its Azure Blob backend resolves credentials in the order
   `AZURE_STORAGE_CONNECTION_STRING` → `AZURE_STORAGE_ACCESS_KEY` → `DefaultAzureCredential()`.
   fsd's entire storage seam is fsspec/adlfs with **managed identity only** (`AZURE_CLIENT_ID` +
   a bare `DefaultAzureCredential()`), proven on the cluster with **`storage/azure.py` unchanged**
   (spec 36 D4, spec 38 D4′) and **no Key Vault**. MLflow would add a parallel path that *prefers
   secrets over MSI*. This is the same objection that decided the rslearn question, and it is the
   strongest one here.
4. **fsd would inherit the two defects spec 44 fixes.** D1 preserves package layout because MLflow's
   `code_paths` flattens; D2 adds a collision guard because MLflow's `sys.path`/`sys.modules`
   handling silently loads the wrong model ([mlflow#12377](https://github.com/mlflow/mlflow/issues/12377)).
   Adopting MLflow means adopting both, and losing the fixes.

**And it would not replace the fsd-specific half anyway.** `required_bands`, `n_timestamps`,
`output_dtype/nodata/band_names`, the `feature` descriptor and **model-free preflight** are fsd's
contract, not MLflow's. Under MLflow they become a free-form `metadata` blob inside someone else's
YAML that fsd still has to write and validate itself.

### 6.3 MLflow for **phase 2** (D7 registry) — genuinely strong, left open

The calculus **flips** here, and D7 should not be signed off without weighing it:

- D7's weakest part is hand-rolled versioning. MLflow Model Registry does versioning, staging and
  aliases properly, and it is an industry-standard interface rather than an fsd invention.
- **Azure ML workspaces are MLflow servers with no extra configuration** — tracking *and* model
  registry, via the workspace's MLflow URI. On the `rise` workspace that means versioned model
  registration essentially for free, with **no database to run**.
- The catch, and why this is a trade rather than a win: self-hosting the registry **requires a
  database-backed store** (PostgreSQL/MySQL/SQLite/MSSQL — a file-based store does *not* support the
  registry). So the portable path costs real infra, and "free on Azure, Postgres everywhere else"
  is a lock-in gradient, not lock-in freedom.

**Recommendation:** keep D7's blob store as the default (it is ~30 lines on a seam fsd already
owns), and add *"register through MLflow when the target is an AML workspace"* as an explicit
**alternative backend** for D7 — a `deploy(storage="mlflow://…")` shaped decision, evaluated on its
own, not folded into phase 1.

### 6.4 Considered and dismissed quickly

| library | why not |
|---|---|
| **BentoML / KServe / Seldon / Ray Serve** | Serving frameworks: they own a long-lived prediction *service*. fsd does batch inference inside an AML job that AML already owns. Wrong shape, not a smaller version of the right one. |
| **`cloudpickle` (by-value)** | Already rejected in D1 — documented as experimental, and couples the artifact to interpreter/library versions on both ends. |
| **`skops`** | Solves safer *sklearn* persistence. Orthogonal to shipping adapter code, and fsd is framework-agnostic by contract. |
| **AML `code:` job snapshot** | Azure-specific, and it would put per-run code shipping in the dispatcher instead of the cloud-agnostic bundle. Credited in §7. |

---

## 7. Best-practice alignment / sources

Every source below was consulted 2026-08-19 under the standing spec-cross-validation permission.
Per-source credit — what each one actually contributed:

- **[MLflow — *Managing Dependencies in MLflow Models*](https://mlflow.org/docs/2.21.3/model/dependencies/)** —
  the closest prior art (`code_paths`). Contributed: (a) the **shape** fsd copies — user code stored
  in a `code/` directory inside the model artifact and added to the system path at load time;
  (b) the **flattening defect fsd fixes** — MLflow copies `src/utils.py` to `code/utils.py`, so its
  docs must instruct users to rewrite imports and to keep relative imports "from a common root
  path"; this is why **D1 preserves layout**; (c) the documented `__main__` limitation (code defined
  in the entry point "cannot be easily inferred", cloudpickle offered as the workaround) — which
  directly motivated **D3's refuse-on-`__main__`**; (d) the statement that dependency inference
  "will not work across module boundaries or if your custom code is defined in an entirely different
  library" — the evidence behind **D5's declare-don't-infer**.
- **[mlflow#12377 — *Load several models with different code in pyfunc code_path*](https://github.com/mlflow/mlflow/issues/12377)** —
  contributed the **exact failure mode D2's collision guard prevents**: "code_path appends to
  sys.path and imported modules cached in sys.modules", so loading a second model whose package has
  the same name silently imports the first model's code. This is a *silent wrong answer*, which is
  why fsd raises instead.
- **[mlflow#6028 — *`load_model()` adding code directories to system path that shouldn't be
  added*](https://github.com/mlflow/mlflow/issues/6028)** — corroborates that path-injection at load
  time shadows the wider environment in practice; contributed the framing of **D2's "`load` mutates
  `sys.path`" as a side effect that must be documented**, and the driver-vs-node rule.
- **[Ray — *Environment Dependencies* (`runtime_env`)](https://docs.ray.io/en/latest/ray-core/handling-dependencies.html)** —
  the other mature answer to "get local code onto remote workers". Contributed: (a) confirmation
  that **inserting delivered code onto the worker's `PYTHONPATH`** (`py_modules`) is the standard
  mechanism, not an fsd invention; (b) the precedent for **default excludes** (`.git`, `.venv`,
  `__pycache__`) adopted in D1; (c) the precedent for a **hard size cap** (`working_dir` ≤ 500 MiB),
  which is why D1 caps rather than warns — fsd's cap is far smaller because the payload is adapter
  source, not a workspace.
- **[cloudpickle README](https://github.com/cloudpipe/cloudpickle/blob/master/README.md)** —
  contributed the **rejection rationale for the by-value alternative**: `register_pickle_by_value`
  is documented as *experimental*, by-reference is the deliberate default because cloudpickle
  "cannot detect locally importable modules", and by-value output is discouraged for long-term
  storage. A bundle is long-term storage, so **D1 ships `.py`, not a pickled class**.
- **[Python — *The import system*](https://docs.python.org/3/reference/import.html)** and
  **[*The initialization of the sys.path module search path*](https://docs.python.org/3/library/sys_path_init.html)** —
  contributed the **precedence guarantee D2 relies on**: `sys.path` is searched in order and the
  first match wins, so `insert(0, …)` deterministically shadows an installed module of the same
  name. Without this, "bundle wins" would be an assumption rather than a documented property.
- **[Azure ML — *CLI (v2) command job YAML schema*](https://github.com/MicrosoftDocs/azure-ai-docs/blob/main/articles/machine-learning/reference-yaml-job-command.md)** —
  contributed the check that AML **already** has a first-class "ship a local code directory with the
  job" mechanism (`code:` — "local path to the source code directory to be uploaded and used for the
  job", uploaded as a snapshot at submission). Credited here for an honest reason: it is a **genuine
  alternative to D1 that this spec does not take**, because it is Azure-specific and would put
  per-run code shipping into the AML dispatcher instead of the cloud-agnostic bundle — the storage
  seam (ADR-0001) carries it for every backend at no extra cost.
- **[MLflow — `mlflow.pyfunc` API](https://mlflow.org/docs/latest/python_api/mlflow.pyfunc.html)** —
  contributed the §6.2 finding that `save_model`/`load_model` work on a **plain local directory with
  no tracking server**, which is what makes MLflow a real contender for phase 1 rather than a
  strawman. Rejecting it required establishing this first.
- **[MLflow — *Model Registry*](https://mlflow.org/docs/3.0.1/model-registry/)** and
  **[*Backend Stores*](https://mlflow.org/docs/latest/self-hosting/architecture/backend-store/)** —
  contributed §6.3's decisive constraint: the registry **requires a database-backed store**
  (PostgreSQL/MySQL/SQLite/MSSQL); a file-based backend store does not support it. This is what
  turns "just use MLflow for D7" into a real infra cost off-Azure.
- **[Microsoft — *MLflow and Azure Machine Learning*](https://learn.microsoft.com/en-us/azure/machine-learning/concept-mlflow?view=azureml-api-2)**
  and **[*Manage models registry with MLflow*](https://learn.microsoft.com/en-us/azure/machine-learning/how-to-manage-models-mlflow?view=azureml-api-2)** —
  contributed the other half of §6.3: **AML workspaces are MLflow servers with no extra
  configuration**, tracking and registry alike. This is the strongest pro-MLflow argument in the
  spec and is recorded as such rather than argued away.
- **[MLflow — *Artifact Stores*](https://mlflow.org/docs/latest/self-hosting/architecture/artifact-store/)** —
  contributed §6.2's third and heaviest objection: MLflow's artifact layer is **not fsspec**, and
  its Azure Blob backend resolves credentials `AZURE_STORAGE_CONNECTION_STRING` →
  `AZURE_STORAGE_ACCESS_KEY` → `DefaultAzureCredential()` — i.e. it **prefers secrets over managed
  identity**, against an fsd cluster deliberately running MSI with no Key Vault.
- **PyPI release metadata for `mlflow` and `mlflow-skinny` 3.15.1** (queried 2026-08-19) —
  contributed §6.2's dependency numbers, which are otherwise easy to hand-wave: `mlflow-skinny`
  requires **20** packages including `fastapi`/`starlette`/`uvicorn`, `databricks-sdk`, `protobuf`,
  `pydantic` and three `opentelemetry-*`; full `mlflow` adds **20 more**. Compared against fsd
  core's 13 declared dependencies.
- **[Python — `importlib.metadata`](https://docs.python.org/3/library/importlib.metadata.html)** +
  **[`packaging` — *Requirements*](https://packaging.pypa.io/en/stable/requirements.html)** — contributed **D5's
  implementation**: parse PEP 508 with `packaging.requirements.Requirement` and resolve installed
  versions with `importlib.metadata.version`, rather than hand-rolling a specifier parser.
- **Verified in this repo, not online** (recorded so the next session need not re-derive):
  `bundle.py::save`/`::load`/`::resolve_ref`, `runners.py:787` `_stage_bundle`,
  `infer_shard.py:49` `fetch_bundle_to_scratch`, `adapter_smoke.py`, `api.py:1286` `deploy` stub,
  `api.py:1174` (the 627 s measurement), `specs/38-inference-on-aml.md` D4, `ROADMAP.md:302`/`:396`.
  Origin classification (local vs installed vs editable) was executed in `fsd/.venv` on 2026-08-19.

---

## 8. Open questions for sign-off

1. **§0 — do you accept reversing spec 38 D4's two LOCKED claims?** Nothing else proceeds until this
   is yes; the rest of D4 is untouched either way.
2. **D1 cap — 64 files / 5 MB.** Right ballpark, or should auto-detection refuse *any* package (more
   than one file) and require an explicit `code=[...]`?
3. **D3 refuse-on-`__main__`** is a behavior change to `save` (today it writes an unusable manifest
   and fails later on a node). Confirm, and it goes in `CHANGES.md`.
4. **D5 — is user-declared `requirements` worth the manifest field now**, or should the smoke job
   simply keep reporting the raw `ImportError` and the field wait for a real need?
5. **D7 — blob-with-immutable-versions as the phase-2 store**, closing `ROADMAP.md` §7. Sign this
   off separately from phase 1 if you would rather not settle it yet.
6. **Sequencing** — implement phase 1 alone (a Sonnet@medium session against §3 D1–D6), or specify
   phase 2 more fully first?
7. **§6.3 — should MLflow-via-the-AML-workspace be specified as an alternative D7 backend** (free,
   proper versioning on Azure; a Postgres dependency anywhere else), or is the blob store enough?
   This is the one place a library would genuinely save real work.

---

## 9. Amendments

### A1 — D2's collision guard compares **content**, not path (found during implementation, 2026-08-19)

**D2 as signed off is wrong and would have broken existing behavior.** As written, the guard fires
when the adapter's module is already in `sys.modules` and its `__file__` differs from the file the
bundle provides. But **save-then-load in one process is a normal, supported flow**, and in it those
two paths *always* differ:

- `api._ensure_bundle` auto-saves a live adapter to a temp bundle and then loads it back — the
  class's module is already imported from its original path, while the bundle serves its **copy**
  under `code/`.
- Every existing bundle test in `tests/test_model.py` does exactly this (adapter classes are defined
  in the test module, saved, then `bundle.load`ed in the same interpreter).

Path comparison would make all of those raise. The guard would be a false-positive machine on the
most common flow, while still being the right idea for the case it targets.

**The correction:** compare the **bytes of the module's source**, not its path.

| already in `sys.modules`? | bundle's copy vs. the imported module's source | behavior |
|---|---|---|
| no | — | insert path, import normally |
| yes | **byte-identical** | **not a collision** — same code under the same name. Proceed; the import cache legitimately satisfies it |
| yes | **differs** | **raise**, naming both files — this is the real mlflow#12377 case (two different implementations under one name) |
| yes | imported module has no resolvable `__file__` (namespace package, builtin, frozen) | **raise** — the identity cannot be verified, and guessing is what the guard exists to prevent |

This keeps every property D2 was signed off for — the silent-wrong-model failure is still refused —
and drops the false positives. It is also *strictly stronger*: two bundles whose code differs are
caught even if they happen to sit at the same path, which path comparison would miss.

**Acceptance criterion 6 (§4) is restated accordingly:** `load` raises when a module of the same name
is already imported **with different source**, and does **not** raise when it is byte-identical. Both
halves are tested.
