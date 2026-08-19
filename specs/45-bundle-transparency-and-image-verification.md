---
status: current
summary: Make `bundle.save` say what it embedded and refuse the two bundles that save fine and die on a node (#70/#71/#72), and promote the run-book's image smoke into a public `fsd.model.verify_image` helper (#67).
---

# Spec 45 — bundle transparency, bundle validation, and image verification

**Status: ✅ SIGNED OFF 2026-08-19 — NOT YET IMPLEMENTED.** Written against issues **#70, #71,
#72, #67**, all raised by the user while driving `notebooks/e2e_austria_aml.ipynb`. The one
load-bearing question (§7 Q1) was answered by the user at sign-off: **refuse, naming the file** —
D3 stands as written. The two secondary questions were resolved with the defaults recorded in §7.
Implementation is a **Sonnet session at `/effort medium`** (§9); nothing in `src/` is touched yet.

> **The one sentence:** spec 44 made the bundle carry its adapter's source; this spec makes the
> bundle **tell you what it carried** and **refuse to be born broken**.

---

## 1. The problem

Spec 44 shipped `code=` embedding and it works — the cluster run proved it. What it did not ship is
any way for the person calling `save` to *see* or *trust* the result. Three defects, all reported
from the notebook, all sharing one root cause: **`save` makes a consequential decision in silence.**

| # | defect | when it bites |
|---|---|---|
| **#70** | `save` never reports what it embedded. Verbatim: *"i don't like the autodetection of my_adapter.py because i don't understand the mechanism."* | immediately — as distrust |
| **#71** | a sibling import (`from helper import V`) is not auto-detected; `save` succeeds, the node raises `ModuleNotFoundError: helper` | after a 40–380 s cold start |
| **#72** | `code=[...]` files from two different trees push the common root up, so the adapter no longer sits at the top of `<bundle>/code`; `save` succeeds, the node cannot import it | after a cold start |

The current answer to all three is **documentation** (`RECIPES.md` → "What `bundle.save(...,
code=...)` actually embeds", measured 2026-08-19). That was the right emergency response and it is
the wrong permanent layer: it requires the user to know the doc exists, and it cannot fire at the
moment the mistake is made.

A fourth, adjacent gap: **#67 — verifying an inference image is a run-book script**
(`runbooks/scripts/45_phase1_generic_image_smoke.py`, nine env vars), not a library call. Since
spec 44 an image is generic per *dependency family*, so "does this image run this bundle?" is now a
question asked once per family (sklearn, xgboost, torch, keras) — i.e. exactly the kind of thing
that should be a function.

## 2. Scope

**In:** `fsd.model.bundle.save` reporting + two validations; one new public helper
`fsd.model.verify_image`. **Out:** changing what auto-detection *picks* by default (the walk-up
rule stays, spec 44 D1); the `deploy` registration store (spec 44 phase 2, still unsigned);
anything that installs dependencies (spec 38 D4's front-loading is untouched).

## 3. Decisions

### D1 — `save` reports what it embedded, on the call, by default

`save` prints one block before it returns:

```
[bundle] code root ./demo_model -> code/
[bundle]   my_adapter.py (2.1 kB)
[bundle] 1 file, 2.1 kB | adapter my_adapter:CropRF | requirements: scikit-learn>=1.5, joblib
```

- **Print, not `logging`.** The audience is a notebook cell, and the repo's standing rule is that a
  long or consequential operation must show what it is doing rather than go quiet (memory
  `long-process-progress`; `create_datacube.py`'s `_tick` is the precedent).
- **On by default**, suppressible with `verbose=False`. A silent default is what produced #70.
- The block always names the **resolved import root**, because the root — not the file list — is the
  thing users cannot infer (spec 44 D1's walk-up rule).
- `save` keeps returning `str` (the bundle path). Callers depend on it; the report is a side effect,
  not a new return type. The same content is already recoverable from `read_spec` for programmatic
  use.

### D2 — `save` refuses a bundle whose adapter would not be importable (#72)

After resolving `(root, rels)` and **before copying anything**, check that the adapter's own module
lands at the top level of `<bundle>/code`:

- module `my_adapter` must appear as `my_adapter.py` in `rels`;
- module `my_pkg.adapters` must appear as `my_pkg/adapters.py` (its package root at the top).

If not, raise, naming the file that pulled the root upward and the fix ("keep every embedded file
under one directory"). This is a pure path computation — no imports, no network, no node — and it
closes the whole class, including a user embedding a file from a parent of the adapter's own root.

**Rejected alternative:** silently re-rooting each file so everything flattens into `code/`.
Friendlier for the two-file case, but it destroys the package layout that a `my_pkg.adapters`
adapter depends on, and it makes `code/` contents depend on file order. Refusing is honest.

### D3 — `save` detects an unembedded sibling import (#71) and refuses, naming it

Parse each embedded `.py` with `ast` (never import it — the module may need deps the driver lacks).
For every `import X` / `from X import ...` where `X` is a **top-level** name:

1. skip it if it is a stdlib module, an installed distribution, or `fsd` itself;
2. if `X` resolves to a file under the resolved import root that is **not** in `rels` → **refuse**,
   naming the file and the one-line fix (`code=["./demo_model/my_adapter.py",
   "./demo_model/helper.py"]`);
3. otherwise leave it alone — it is a dependency, and dependencies are declared via
   `requirements=` (spec 44 D5), never embedded.

**Refuse rather than auto-embed [SIGNED OFF — user, 2026-08-19].** The user chose refusal over
auto-embed-and-report, so `code=None` keeps meaning exactly one thing: the adapter's own module.
The message must carry the fix, not just the diagnosis:

```
ValueError: my_adapter.py imports 'helper', which resolves to ./demo_model/helper.py
but is not embedded. The node would raise ModuleNotFoundError after a cold start.
Fix: code=["./demo_model/my_adapter.py", "./demo_model/helper.py"]
```
 Auto-embedding would widen
what `code=None` means without the user asking, and the two established libraries in this space both
warn against exactly that: MLflow's `infer_code_paths` documentation carries an explicit
sensitive-data warning (an inferred sweep can log credential strings into the artifact store), and
cloudpickle refuses to infer at all, requiring per-module opt-in via `register_pickle_by_value`.
fsd's position lands between them: **infer to detect, not to decide.**

Scanning is **transitive** over embedded files (a sibling that imports a sibling), bounded by the
existing `MAX_CODE_FILES` / `MAX_CODE_BYTES` limits.

**Known limits, stated rather than hidden** (all shared with MLflow's inference):
- a module imported dynamically (`importlib.import_module(name)`) is invisible to an ast scan;
- non-Python data files a module opens by relative path are not detected;
- `__main__`-defined adapters are already refused earlier (spec 44 D3).

### D4 — `fsd.model.verify_image(...)` promotes the smoke job into the library (#67)

```python
fsd.model.verify_image(
    bundle,                      # local bundle path or an already-staged URL
    environment="fsd-infer-sklearn:3",
    runner="aml", runner_kwargs=infer_kwargs,
    build_context=None,          # optional: the folder holding the fsd wheel the image was built from
) -> dict                        # {"status": ..., "pass": bool, "metrics": {...}, "error": ...}
```

Behaviour is the run-book script's, lifted verbatim and generalised:

1. **driver-side first, free:** manifest is v2, a `code` block exists, `check_requirements` against
   the declared list, and — when `build_context` is given — the wheel-staleness gate that refuses a
   pre-spec-44 image in ~2 s instead of a 40–380 s cold start;
2. stage the bundle exactly as `run_aml_inference` does;
3. submit **one node** running the existing `python -m fsd.workflows.adapter_smoke`;
4. always read `_status/*.json` back, and treat a *missing* status file as its own diagnosis (the
   job died before the entrypoint → image or node auth).

Three properties are non-negotiable, each a defect the run-book already paid for:
- **it must run as a job, never on the driver** — a local run passes trivially because the driver
  has the adapter on `sys.path` (ADR 0002);
- **the returned dict is `_result.json`-shaped** (spec 24), so a run-book can paste it back;
- **the helper is called at the step it protects** — immediately before `run_inference` — not
  hoisted into an upfront gate (user, 2026-08-19; see `RECIPES.md`).

The run-book script becomes a thin wrapper over the helper, so the verification path keeps exactly
one implementation.

### D5 — `runner="local"` is not a verification

`verify_image` requires a real runner. Asked for `local`, it raises rather than returning a pass —
"verified locally" is the false positive this whole helper exists to prevent.

## 4. Acceptance criteria

1. `save` prints the root, the file list with sizes, the adapter ref and the declared requirements;
   `verbose=False` silences it; the return value is still the bundle path.
2. A bundle whose adapter would not sit at the top of `code/` raises at `save`, naming the offending
   file. Regression test with two files from two trees.
3. `my_adapter.py` containing `from helper import V`, with `code=None`, raises at `save` naming
   `helper` and the fix. Regression test, plus one that a *dependency* import (e.g. `sklearn`) does
   **not** raise.
4. A transitive sibling chain (`a` imports `b`, `b` imports `c`) is detected.
5. `verify_image` returns `pass: True` against a known-good image + bundle, and `pass: False` with a
   populated `error` when the image is stale — the stale case detected **before** submission when
   `build_context` is passed.
6. `verify_image(runner="local")` raises.
7. `runbooks/scripts/45_phase1_generic_image_smoke.py` calls the helper and its `_result.json` is
   unchanged in shape.
8. `pytest -q` and `ruff check src/ tests/ demos/ examples/` clean; no network in the unit tests
   (the AML client is injected, per spec 36 D3 invariant 3).

## 5. Risks

- **D3 false positives block a working save.** A name that looks like a sibling but is genuinely an
  installed distribution would refuse a legitimate bundle. Mitigated by checking installed
  distributions first (`_is_installed` already exists) and by `code=[...]` remaining an explicit
  override that skips inference.
- **Printing by default is a behaviour change** for anyone parsing `save`'s stdout. Nothing in the
  repo does; `verbose=False` is the escape hatch. Record in `CHANGES.md`.
- **`verify_image` adds a public API surface** that must keep working across runners. Kept minimal:
  one function, one dict, no new abstractions.

## 6. Alternatives considered

- **Leave it as documentation.** Rejected: it is the current state, and it is what produced #70/#71.
- **Make `code=[...]` mandatory** (drop auto-detection). Rejected: it forces every user to learn the
  import-root rule, which is the thing they were confused by; and spec 44's auto-detection is right
  for the common single-module case.
- **Auto-embed detected siblings.** See D3 — deferred to §7 Q1, not rejected outright.

## 7. Questions at sign-off — all resolved

1. **D3: refuse, or auto-embed and report?** → **REFUSE** (user, 2026-08-19). `code=None` keeps a
   single meaning; the error carries the one-line fix. Folded into D3.
2. **D1: print always, or only when auto-detection ran?** → **always**, `verbose=False` to silence.
   The resolved import **root** is the part no caller can infer — including one who passed
   `code=[...]`, since the root is computed from their paths, not chosen by them (#72 is exactly
   that surprise). Default resolved by Claude; overturn it in review if you disagree.
3. **`verify_image` namespace?** → **`fsd.model.verify_image`**. It answers a question about the
   *image*, taking a bundle as one input; `fsd.model` is already the public namespace users import
   from (`from fsd.model import bundle`). Default resolved by Claude.

## 8. Best-practice alignment / sources

- [MLflow — model dependencies / `infer_code_paths`](https://mlflow.org/docs/latest/ml/model/dependencies/)
  and [PR #11997](https://github.com/mlflow/mlflow/pull/11997) / [PR #11806](https://github.com/mlflow/mlflow/pull/11806):
  established that automatic *dependent-module* inference is a real, shipped feature (so D3's
  detection is not exotic), and supplied its documented limitation set — cwd-only, `__main__` not
  inferable, non-Python relative files not inferable, and the **sensitive-data warning** that is the
  main argument for D3 refusing rather than sweeping files in.
- [cloudpickle README](https://github.com/cloudpipe/cloudpickle) / `register_pickle_by_value` (2.0.0+):
  supplied the opposite pole — a mature library that deliberately does **not** infer local modules
  and requires explicit per-module opt-in, because serialization *by reference* silently assumes the
  module is importable in the remote environment. This is the exact failure mode of #71, described
  by a third party, and it is why D3 stops at detection.
- `mlflow#12377` (already cited in `bundle._guard_module_collision`): the same-name-different-code
  hazard fsd guards; D2/D3 extend the same "catch it at build time, not on the node" posture.

## 9. Implementation note

Per `CLAUDE.md`'s model split, implementation is a **Sonnet session at `/effort medium`** against
this spec once signed off. Everything it touches is in `src/fsd/model/bundle.py` (D1–D3) plus one
new module for D4 and a rewrite of `runbooks/scripts/45_phase1_generic_image_smoke.py` to call it.
