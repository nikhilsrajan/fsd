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
  ```
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

Change the bundle's content first (any manifest-visible change — re-saving with a different
`requirements=` list is the cheapest):

```bash
.venv/bin/python - <<'PY'
import os
from fsd.model import bundle, registry

# re-save the SAME adapter with a trivially different requirements list, so the digest changes
src = bundle.read_spec(os.environ["AZ_BUNDLE_LOCAL"])
print("adapter:", src.get("adapter"))
PY
```

Then, using whatever adapter class the bundle above names, re-save it to a new local folder with
one extra requirement (e.g. `requirements=[..., "packaging"]`), and publish that:

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

Pick whichever is cheaper for you: pre-built cubes (fastest) or a small ROI. Pre-built cubes shown;
swap in your own `inference_datacubes=` folder or an `roi=`/`catalog_filepath=` pair per
`runbooks/48-e2e-austria-with-verify-adapter.md` if you'd rather prove the ROI path.

```bash
.venv/bin/python - <<'PY'
import os
from fsd import api

result = api.run_inference(
    model="crop-rf@champion", registry=os.environ["AZ_REGISTRY"], storage="azure",
    inference_datacubes=os.environ["AZ_INFERENCE_CUBES"],   # a folder of pre-built datacube.npy
    output_folderpath=os.environ.get("AZ_INFER_OUT", "./tests/outputs/p52_infer"),
)
print({"step": "52-4-run-inference", "status": "ok", "pass": len(result.output_filepaths) > 0,
       "metrics": {"n_outputs": len(result.output_filepaths)},
       "expected": {"n_outputs": "> 0"}, "error": None})
PY
```

- **PASS if:** `n_outputs > 0` and no exception. This is spec 52 AC8 for real: `crop-rf@champion`
  resolved against blob (v1, per step 3's repoint) without `storage="azure"` needing to be set
  anywhere else in the process first — `run_inference` authenticates itself now (D4, #86).
- **If it raises before reaching inference:** check `_configure_storage` actually ran — the
  fastest sanity check is `import os; print(os.environ.get("FSSPEC_ABFSS_ANON"))` right after the
  call starts raising; it should be `"false"`.
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
