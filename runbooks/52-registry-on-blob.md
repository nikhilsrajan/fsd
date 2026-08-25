---
status: current
summary: Prove the model registry actually works on real Azure Blob storage — publish two versions, repoint an alias, run inference off the ref, and confirm a re-publish of identical content is a no-op. The part spec 52's unit tests cannot cover (memory:// exercises the same code, but is not abfss://).
---

# Run-book: 52 — the registry on blob

> Spec-24 run-book for **spec 52** (signed off 2026-08-24). **You** run this; paste back each
> step's result. Claude diffs it against the success criteria below and never reads your logs.
>
> **What this is proving:** spec 52's own §5 says it plainly — "the `abfss://` path is still not
> proven by this suite. `memory://` exercises the same code, and after D1 there is no
> backend-specific branch left to diverge... but 'no branch' is not 'tested'." This run-book is
> that proof. Green `pytest -q` is not this spec's finish line.
>
> **Concrete `rise` values are NOT in this file** (public repo). Paste them as env vars from the
> uncommitted `../../AZURE_INFRA_PRIVATE.md` (workspace root). Run the private-identifier sweep
> (`RECIPES.md`) before pushing anything derived from this run-book.

> **Running this from a Jupyter notebook?** Every command below is **bash**, except the inline
> `python - <<'PY' ... PY` blocks, which are Python — paste those into a cell body directly
> (drop the heredoc wrapper) rather than running them with `%run`.

## Results — executed against a real `abfss://` registry, 2026-08-25

| Step | Verdict | Evidence |
|---|---|---|
| **1** publish v1 | **PASS** | `version=1`, `elapsed_s=32.9` (bar: < 60). **#88 is dead against real Azure**, not just `memory://` |
| **2** publish v2 | **PASS** | `version=2`; v1/v2 content digests differ |
| **3** repoint alias | **PASS** | `resolved_version=1` after `set_alias`; neither version touched |
| **4** infer off the ref | **FAILED 2026-08-25 as written; PASSED unaided after spec 53** | First run: `[model] crop-rf-t10@champion -> v1` proved the ref resolved against live blob (AC8's substance), then `bundle.load` raised `ModuleNotFoundError` — **[#89](https://github.com/nikhilsrajan/fsd/issues/89)**. Re-run after spec 53 merged (`main` @ `38a2d09`), **with no workaround**: `n_outputs=1`, `published_version=1`, no exception |
| **5** idempotent re-publish | **PASS** | `version=1` returned, `n_entries` 3 -> 3 — nothing written |

**Verdict: spec 52's publish protocol is proven on real Azure.** In-place publish, the completion
marker, alias repointing and content-digest idempotency all behave against `abfss://` exactly as
they do on `memory://` — which was D1's whole argument (no backend-specific branch left to
diverge), now with "no branch" backed by an actual run.

**Two things this run did NOT prove, both filed:**

- **#86 is unproven.** Step 4 is the only step that goes through a verb at all (1/2/3/5 call
  `registry.*` directly), and it cannot pass `storage="azure"` —
  **[#90](https://github.com/nikhilsrajan/fsd/issues/90)**. So `configure_storage` was never
  exercised anywhere in this run. Note also that steps 1-3 authenticated fine **without** it:
  adlfs's `anon` default is `None`, so the `az login` credential chain was found on its own.
- ~~**A blob registry is unusable on the local run path** — #89.~~ **RESOLVED 2026-08-25.**
  `specs/53-blob-registry-on-the-local-run-path.md` D1/D2 shipped (`run_inference` stages a
  non-local bundle to `<output_folderpath>/_model` before any local shape loads it), and step 4
  was re-run against the same real `abfss://` registry **without** the manual workaround: PASS.
  That re-run is what closes #89 — unit tests structurally cannot, since the crash needs a fresh
  interpreter.

---

## Purpose

| Step | Proves |
|---|---|
| **1** | `deploy` publishes v1 to a real `abfss://` registry and returns quickly — #88 (the infinite retry loop) is actually gone against Azure, not just against `memory://` |
| **2** | `deploy` with changed content publishes v2 and repoints `alias=` in one call |
| **3** | `set_alias` repoints an existing alias without touching either version |
| **4** | `run_inference(model="name@alias", registry=...)` resolves the ref against blob and runs |
| **5** | Re-`deploy`ing v1's exact content again is a no-op: same version returned, nothing new written |

## Prerequisites

- VPN connected, `az login` done, correct subscription selected.
- The fsd venv:
  ```bash
  cd fsd && source .venv/bin/activate && pip install -e ".[dev]"
  ```
- A deployable bundle (has both a `code` block and `requirements` — spec 51 D6). Reuse the demo
  bundle from `runbooks/40-train-and-bundle.md` Phase 3, or your own.
- Env vars (from `AZURE_INFRA_PRIVATE.md`):
  ```bash
  export AZ_ACCOUNT='<storage account>'
  export AZ_FS='<filesystem/container>'
  export AZ_REGISTRY="abfss://${AZ_FS}@${AZ_ACCOUNT}.dfs.core.windows.net/<your-prefix>/fsd-registry-52"
  export AZ_BUNDLE_LOCAL="$PWD/tests/outputs/p40_train_and_bundle/demo_rf_bundle"   # or your own
  export AZ_BUNDLE_LOCAL_V2="$PWD/tests/outputs/p52_registry_on_blob/demo_rf_bundle_v2"  # step 2 creates this
  export AZ_INFERENCE_CUBES="$PWD/tests/outputs/demo_e2e/inference_datacubes"   # step 4; use your own
  ```
  `AZ_BUNDLE_LOCAL_V2` must **not** exist yet — step 2 creates it with `cp -r`.
  `AZ_INFERENCE_CUBES` is a folder of pre-built `datacube.npy` + `metadata.pickle.npy` pairs.
  Step 4 passes as written from spec 53 onward (`main` @ `38a2d09`); on an older checkout it
  raises `ModuleNotFoundError` — see that step's own note.
  `AZ_REGISTRY` should be a prefix nothing else is using — this run-book publishes real content
  under it and does not clean up after itself (spec 52 §5: stranded/legacy content is cheap and
  harmless, but pick a throwaway name, not a shared registry).

---

## Step 1 — publish v1 to `abfss://` and confirm it returns quickly

```bash
cd fsd
.venv/bin/python - <<'PY'
import os
import time
from fsd.model import registry

t0 = time.monotonic()
v = registry.publish(
    os.environ["AZ_BUNDLE_LOCAL"], "crop-rf", os.environ["AZ_REGISTRY"], alias="champion",
)
elapsed = time.monotonic() - t0
print({"step": "52-1-publish-v1", "status": "ok", "pass": v == 1 and elapsed < 60,
       "metrics": {"version": v, "elapsed_s": round(elapsed, 1)},
       "expected": {"version": 1, "elapsed_s": "< 60"}, "error": None})
PY
```

- **Expect:** `{"version": 1, "elapsed_s": <a small number>}`.
- **PASS if:** `version == 1` **and** `elapsed_s` is seconds, not minutes. A regression to #88
  hangs here — if this step is still running after a couple of minutes, Ctrl-C and paste what
  printed (or didn't).
- **Sanity-check on the storage account** (optional, via Azure Storage Explorer or `az storage
  fs directory show`): `<prefix>/fsd-registry-52/crop-rf/v1/_complete.json` should exist.

---

## Step 2 — publish v2 (changed content) and confirm `alias=` repoints in one call

Change the bundle's content first. **Copy the bundle and add a `requirements` entry** — a
manifest-visible change, so the content digest changes, and it needs no adapter import (the demo
bundle's `adapters:DemoRF` is not importable from an arbitrary cwd, which is why this does not go
through `bundle.save`). Verified locally 2026-08-25 against
`tests/outputs/p40_train_and_bundle/demo_rf_bundle`: the digest changes and `read_spec` still
reads the result.

```bash
mkdir -p "$(dirname "$AZ_BUNDLE_LOCAL_V2")"
rm -rf "$AZ_BUNDLE_LOCAL_V2"          # re-runnable: cp -r onto an existing dir nests instead
cp -r "$AZ_BUNDLE_LOCAL" "$AZ_BUNDLE_LOCAL_V2"
.venv/bin/python - <<'PY'
import json
import os
from fsd.model import bundle, registry

dst = os.environ["AZ_BUNDLE_LOCAL_V2"]
manifest_path = os.path.join(dst, bundle.BUNDLE_MANIFEST)
with open(manifest_path) as f:
    manifest = json.load(f)
manifest["requirements"] = sorted(set(manifest.get("requirements") or []) | {"packaging"})
with open(manifest_path, "w") as f:
    json.dump(manifest, f, indent=2, sort_keys=True)

print({"v1_digest": registry.content_digest(os.environ["AZ_BUNDLE_LOCAL"]),
       "v2_digest": registry.content_digest(dst)})
PY
```

The two digests must differ. If they do not, `publish` returns v1 by idempotency (D2) and step 2
fails for the right reason. Now publish the changed bundle:

```bash
.venv/bin/python - <<'PY'
import os
from fsd.model import registry

v = registry.publish(
    os.environ["AZ_BUNDLE_LOCAL_V2"],   # the re-saved bundle from the step above
    "crop-rf", os.environ["AZ_REGISTRY"], alias="champion",
)
print({"step": "52-2-publish-v2", "status": "ok", "pass": v == 2,
       "metrics": {"version": v}, "expected": {"version": 2}, "error": None})
PY
```

- **PASS if:** `version == 2`. `_aliases.json` under `crop-rf/` should now read
  `{"champion": 2}` — `deploy`'s `alias=` repoints on every publish, per spec 51 D3.

---

## Step 3 — `set_alias` repoints an existing alias, touching neither version

```bash
.venv/bin/python - <<'PY'
import os
from fsd.model import registry

registry.set_alias("crop-rf", "champion", 1, os.environ["AZ_REGISTRY"])
resolved = registry.resolve("crop-rf@champion", os.environ["AZ_REGISTRY"])
print({"step": "52-3-set-alias", "status": "ok", "pass": resolved.version == 1,
       "metrics": {"resolved_version": resolved.version},
       "expected": {"resolved_version": 1}, "error": None})
PY
```

- **PASS if:** `resolved_version == 1`. `crop-rf/v1/` and `crop-rf/v2/` are both still on blob and
  unchanged — `set_alias` only ever rewrites `_aliases.json` (staged + renamed as a single file,
  spec 52 §1 — unaffected by this spec).

---

## Step 4 — `run_inference` resolves the ref against blob and runs

> **Corrected 2026-08-25, after this step failed twice in a real run.** Three things were wrong
> and all three are fixed below. (1) **Do NOT pass `storage="azure"` here.** `run_inference`
> allows non-local storage only when `roi is not None and runner == "aml"`; on the pre-built-cubes
> path the seam gate refuses it with *"non-local storage not supported here yet"*. The registry
> may still be `abfss://` — `storage=` and `registry=` are independent axes. (2) **The cubes must
> be local**, for the same reason. (3) **The model you infer with must match the cubes' `T`** —
> preflight rejects a mismatch with *"datacube T=N but model needs T=M"*, and the demo bundles in
> this repo disagree (`p40_train_and_bundle/demo_rf_bundle` is T=8; the `demo_e2e` and
> `demo_verify_adapter` bundles and cubes are T=10).
>
> **Honest scope note.** Because `storage="azure"` cannot be passed here, this step does **not**
> exercise `configure_storage`, so it does **not** prove D4/#86 — it proves a ref resolves off a
> blob registry and drives a real run. Resolution works anyway because adlfs's `anon` default is
> `None`, so it falls through to your `az login` credential chain (which is also why steps 1-3
> authenticated with no `configure_storage` call at all). **#86 remains unproven by this
> run-book.**

Publish a bundle whose `n_timestamps` matches your cubes, then infer off that ref. `_bundle` from
a previous `verify_adapter` run is a good choice — it is T=10, has an embedded `code/`, and sits
next to the cube it was verified against:

```bash
export AZ_CUBE_DIR="$PWD/notebooks/demo_verify_adapter/demo-20260820T175606Z"   # or your own
.venv/bin/python - <<'PY'
import os
from fsd import api
from fsd.model import registry

cube_dir = os.environ["AZ_CUBE_DIR"]
v = registry.publish(
    os.path.join(cube_dir, "_bundle"), "crop-rf-t10", os.environ["AZ_REGISTRY"],
    alias="champion",
)

# NOTE: no storage= kwarg (see the correction above). An explicit LIST of datacube.npy paths --
# folder mode expects each cube in its own SUBfolder, which this layout is not.
result = api.run_inference(
    model="crop-rf-t10@champion", registry=os.environ["AZ_REGISTRY"],
    inference_datacubes=[os.path.join(cube_dir, "datacube.npy")],
    output_folderpath=os.environ.get(
        "AZ_INFER_OUT", "./tests/outputs/p52_registry_on_blob/step4_out"),
)
print({"step": "52-4-run-inference", "status": "ok",
       "pass": len(result.output_filepaths) > 0,
       "metrics": {"published_version": v, "n_outputs": len(result.output_filepaths)},
       "expected": {"n_outputs": "> 0"}, "error": None})
PY
```

- **PASS if:** `n_outputs > 0` and no exception — a `name@alias` ref resolved against an
  `abfss://` registry and drove a real inference run.
- **If it raises `non-local storage not supported here yet`:** you still have `storage="azure"`
  in the call. Remove it.
- **If it raises `datacube T=N but model needs T=M`:** the bundle you published does not match
  these cubes. Publish the one that sits beside them (`<cube_dir>/_bundle`).
- **If it raises `no inference datacubes found`:** you passed a folder whose cubes are not in
  per-cube subfolders. Pass an explicit list of `datacube.npy` paths, as above.
- **If it raises `ModuleNotFoundError` on the adapter module:** you are on a checkout older than
  spec 53 (`main` @ `38a2d09`). That was **[#89](https://github.com/nikhilsrajan/fsd/issues/89)** —
  `bundle.load` needs a *local* directory and `sys.path` cannot hold an `abfss://` entry, so a
  blob-resolved ref resolved and then failed to load on the local run path. Fixed by spec 53 D1/D2:
  `run_inference` now stages a non-local bundle to `<output_folderpath>/_model` first. Update, do
  not work around it. (The manual fetch-to-scratch workaround this step used to carry is in git
  history at `9ab5202` if you need it for an old checkout.)
- **You should see a `[stage] bundle <- ... | N files, X MB` line** between `[model] ... -> v1` and
  the first `[inference]` line. That is spec 53's staging fetch announcing itself; its absence on a
  blob registry means staging did not run.
- **Open an output `.tif` in QGIS.** Visual validation is the standard here, per `CLAUDE.md`.

---

## Step 5 — re-publishing v1's exact content is a no-op

```bash
.venv/bin/python - <<'PY'
import os
from fsd.storage import fs
from fsd.model import registry

before = sorted(fs.ls(os.path.join(os.environ["AZ_REGISTRY"], "crop-rf")))
v = registry.publish(os.environ["AZ_BUNDLE_LOCAL"], "crop-rf", os.environ["AZ_REGISTRY"])
after = sorted(fs.ls(os.path.join(os.environ["AZ_REGISTRY"], "crop-rf")))

print({"step": "52-5-idempotent-republish", "status": "ok",
       "pass": v == 1 and before == after,
       "metrics": {"version": v, "n_entries_before": len(before), "n_entries_after": len(after)},
       "expected": {"version": 1, "n_entries_before": "== n_entries_after"}, "error": None})
PY
```

- **PASS if:** `version == 1` (the original, unchanged content) **and** nothing new was written
  (`before == after`) — spec 51 D2's idempotency, now proven against a real backend instead of
  `memory://`.

---

## Success criteria

Every step above prints its own PASS/FAIL inline (no `_result.json` file — these are one-line
Python snippets, not scripts). **Paste back the five printed dicts.** The run passes when all
five say `"pass": true`.

The single sentence that means this worked: **a blob-backed registry publishes, resolves, and
serves inference exactly like a local one, and nothing hangs.**

## Stop / observe

- **Step 1** is the one that can hang on a regression — if it does, Ctrl-C and paste whatever
  printed (or the fact that nothing did). Nothing here is resume-sensitive: re-running any step is
  safe (publish is idempotent; set_alias just overwrites the pointer).
- Nothing here writes outside `$AZ_REGISTRY` on blob and `tests/outputs/` locally.
- **Cleanup (optional):** this run-book does not delete `$AZ_REGISTRY` afterward — issue #50
  (`fs.rm(recursive=True)` unreliable on `abfss://`) makes that unreliable to script, so remove it
  by hand in Storage Explorer if you want the prefix back.
