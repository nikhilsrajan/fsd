# How to: build the two AML node images

> **Last verified:** 2026-08-20 @ `7b26b89`. Re-verify after any change to
> `fsd.model.verify_image`, to the extras in `pyproject.toml`, or to the base image.

Everything on an Azure ML cluster runs inside a container. fsd needs **two**, and neither of them
is per-model. This page is what to build, which files each build needs, and — the part that is
easy to get wrong — **why the fsd wheel has to sit next to a Dockerfile and not next to your
model**.

Do this **before** [`run-at-scale.md`](run-at-scale.md). That page assumes both images exist.

## The two images

| image | used by | what it adds |
|---|---|---|
| **`fsd-aml-env`** | download shards, datacube builds, `create_training_data`'s flatten | fsd + `[azure,mpc]` |
| **`fsd-infer-sklearn`** | the `run_inference` fan-out, `verify_image`'s smoke job | the same, **plus** `scikit-learn` + `joblib` |

The inference image is generic **per dependency family**, never per model. Since spec 44 the
adapter's *source* travels inside the bundle, so the image copies no adapter and sets no
`PYTHONPATH`. Every sklearn model you ever bundle runs on this one image. A torch model needs an
`fsd-infer-torch` built identically with the last two dependencies swapped — that is the only
difference between the two Dockerfiles here.

## Which files each thing needs

Three folders, one job each. They used to be one folder, which is why the wheel's role was
unclear.

```
notebooks/
  images/
    base/                    <- BUILD CONTEXT for fsd-aml-env
      Dockerfile                 what to install
      .dockerignore              keeps stray artifacts out of the context
      environment.yml            the AML asset definition
      fsd-0.1.0-*.whl            <- built by you, step 2; gitignored
    sklearn/                 <- BUILD CONTEXT for fsd-infer-sklearn
      Dockerfile   .dockerignore   environment.yml   fsd-0.1.0-*.whl
  demo_model/                <- YOUR MODEL. No Docker files, no wheel.
      my_adapter.py              -> bundle.save(code=[...])
      rf.joblib                  -> bundle.save(artifacts={"model": ...})
```

The real files are in the repo:
[`notebooks/images/base/Dockerfile`](../../notebooks/images/base/Dockerfile) and
[`notebooks/images/sklearn/Dockerfile`](../../notebooks/images/sklearn/Dockerfile). Read them —
they are commented line by line.

### Why the wheel sits beside the Dockerfile, not beside the model

Three separate facts, which the old single-folder layout blurred into one confusing rule:

1. **`bundle.save` never reads the wheel.** Bundling takes your adapter source (`code=`) and your
   trained artifacts (`artifacts=`). That is all. A wheel in the model folder does nothing at all.
2. **The wheel is what gets installed into the image.** `COPY fsd-*.whl /tmp/` only works if the
   wheel is inside the Docker *build context* — Docker cannot read a file outside it. That is the
   only reason the wheel must be in one specific folder.
3. **`verify_image(build_context=...)` re-reads that same folder afterwards.** It opens the wheel
   and checks whether it carries spec 44's `manifest_code_files`. If it does not, the registered
   image was built from a pre-spec-44 fsd; the node would raise `ModuleNotFoundError` however good
   your bundle is, and an old fsd has none of the code that would report that. Catching it on the
   driver costs ~2 s instead of a cold start.

So `build_context` means **"the folder I built this image from"**, and it must still hold the
wheel afterwards.

> ⚠️ **`verify_image` raises `ValueError` if `build_context` holds no `fsd-*.whl`** — it does not
> return `pass: False`. A missing wheel is a mistake in your *call*; `pass: False` is a verdict
> about the *image*, and a run where nothing was verified must not look like a run where the image
> genuinely failed (spec 47 D10/D11). Practical consequence: **do not clean the wheel out of the
> build context after building.**

## Prerequisites

- `az login` into the tenant hosting the workspace, plus the `ml` extension (`az extension add -n ml`).
- An AML workspace and resource group — a platform-admin action, not something this repo
  provisions. Ask for them by name; see [`run-at-scale.md`](run-at-scale.md).
- A local fsd checkout with its venv (`pip install -e ".[dev,aml,mpc,azure,grid]"`).
- Your Azure coordinates in `~/.config/fsd/config.toml`:
  ```bash
  fsd init      # interactive; fill in all six -- `load()` requires every one of them
  ```
  Every variable is documented in [`../reference/environment.md`](../reference/environment.md).

## Prefer to run it than read it?

[`notebooks/00_build_images.ipynb`](../../notebooks/00_build_images.ipynb) is this page as a
runnable notebook, and is **the one notebook this repo tracks**. It reads `AZ_RG` and
`AZ_ML_WORKSPACE` from `~/.config/fsd/config.toml` via `fsd.config.load()` rather than carrying
them, and `tests/test_notebooks.py` fails the build if it ever gains a saved output or a
hardcoded identifier — that guard is why it can be public at all. Clear its outputs
(*Kernel → Restart & Clear All Outputs*) before committing.

Its Part A / Part B split is the same one described in step 3 below, plus a status cell per image
that compares your current git state against a local record of what was last registered.

## Step 1 — Confirm what you are about to package

**The wheel is built from your working tree, not from a release.** Whatever is checked out and
uncommitted right now is what lands on the nodes. A stale checkout here is the single most common
cause of "the fix I just made isn't on the cluster".

```bash
cd /path/to/fsd
git log --oneline -3
git status --porcelain
```

## Step 2 — Build the wheel into both contexts

```bash
rm -f notebooks/images/*/fsd-*.whl          # never leave two: `ls fsd-*.whl` would pick one
.venv/bin/pip wheel . --no-deps -w notebooks/images/base/
cp notebooks/images/base/fsd-*.whl notebooks/images/sklearn/
ls notebooks/images/*/fsd-*.whl
```

`--no-deps` on purpose: we want the fsd wheel alone, and the Dockerfiles resolve its dependencies
inside the image.

Confirm the wheel is current before spending 20 minutes of ACR time on it:

```bash
python - <<'PY'
import glob, zipfile
w = glob.glob("notebooks/images/base/fsd-*.whl")[0]
with zipfile.ZipFile(w) as zf:
    src = zf.read("fsd/model/bundle.py").decode()
print(w, "| wheel_has_spec44:", "def manifest_code_files" in src)
PY
```

If that prints `False`, `verify_image` will (correctly) reject every image built from it.

## Step 3 — Register the environment(s) you need — **one at a time**

> ⚠️ **Registering always creates a new version, even when nothing changed.**
> `az ml environment create` has no no-op mode: AML auto-increments unconditionally. That is
> deliberate — a version can never mutate under a run that already referenced it — but it means
> **registering both images every time churns the version of one you never touched.**

The two images are rebuilt on **different schedules**. Decide per image:

| you changed | `fsd-aml-env` | `fsd-infer-sklearn` |
|---|---|---|
| the fsd source | rebuild | rebuild |
| your model's runtime deps (sklearn → torch) | leave alone | rebuild (as a new family) |
| your trained model | leave alone | leave alone — it rides in the bundle |
| your adapter code | leave alone | leave alone — it rides in the bundle (spec 44) |

Most users who are only iterating on their own model never rebuild `fsd-aml-env` after the first
time.

**`fsd-aml-env`** — only when the fsd source changed:

```bash
az ml environment create -f notebooks/images/base/environment.yml \
  -g <resource-group> -w <workspace> --query version -o tsv
```

**`fsd-infer-sklearn`** — when the fsd source *or* your dependency family changed:

```bash
az ml environment create -f notebooks/images/sklearn/environment.yml \
  -g <resource-group> -w <workspace> --query version -o tsv
```

**No `version:` is set in `environment.yml` on purpose** — see the warning above. Capture what
each call assigns; you paste both into the run notebook.

**To find the version of the image you did *not* rebuild:**

```bash
az ml environment list -n fsd-aml-env -g <resource-group> -w <workspace> \
  --query "[].version" -o tsv | sort -V | tail -1
```

`notebooks/00_build_images.ipynb` automates exactly this split: Part A and Part B are independent,
each opens with a status cell that compares your current git state against a local record of what
was last registered from that build context, and Part C resolves both versions whether you ran one
part or both.

> **Keep the two images on the same fsd where you can.** Rebuilding only the inference image from
> a newer checkout leaves your datacubes built by one fsd and your inference run by another.
> Usually fine — the artifacts on disk are the contract — but it is the first thing to check if a
> cube and a model disagree.

> **Do not write `export V="$(az ...)"`.** `export` always returns 0, so a broken `az` silently
> assigns its own error text and every later command uses a garbage version. Seen live: `built
> fsd-aml-env:No module named 'rpds.rpds'`. Capture first, check it is digits, then export.

## Step 4 — Wait for the ACR builds ⚠️

**This is the step people skip, and it is the expensive one to skip.**

`az ml environment create` registers the *asset* and returns immediately; the image builds
asynchronously in ACR (~10–20 min each, occasionally flaky). The v2 `Environment` object carries
**no build state whatsoever**, so `ml_client.environments.get(name, version)` succeeds against a
half-built image and every fsd preflight goes green regardless. Submit early and jobs do not
fail — they sit in *Preparing* until ACR is done, and that wait lands inside
`job_admission_seconds`. A 15-minute image build then reads as 15 minutes of slow cluster.

**This gate is manual, and there is no way around that.** Nothing reports it programmatically:

- the `Environment` object has no build state, as above;
- the build is an **ACR task run, not an AML job**, so it does **not** appear in `az ml job list`.
  Do not try to poll `--query "[?contains(name,'prepare_image')]"` — it matches nothing whether
  the build is running, finished or failed. Observed live 2026-08-20: a poll loop built on that
  query printed `0/0 builds terminal` for ten minutes while both builds completed normally in
  Studio;
- `az ml environment show` proves the **asset** is registered, never that the image is built.

So open the version page and read it. Get the workspace ARM id from `az` rather than assembling
the URL path by hand:

```bash
WSID="$(az ml workspace show -n <workspace> -g <resource-group> --query id -o tsv)"
TID="$(az account show --query tenantId -o tsv)"
echo "https://ml.azure.com/environments/fsd-aml-env/version/<version>?wsid=$WSID&tid=$TID"
echo "https://ml.azure.com/environments/fsd-infer-sklearn/version/<version>?wsid=$WSID&tid=$TID"
```

Wait for **Build status: Succeeded** on *both* before running anything against them. The build log
is on the same page.

## Step 5 — Use them

```python
runner_kwargs = dict(environment="fsd-aml-env:<version>", ...)
infer_kwargs  = dict(runner_kwargs, environment="fsd-infer-sklearn:<version>")

vres = verify_image(bundle_dir,
                    environment="fsd-infer-sklearn:<version>",
                    runner="aml", runner_kwargs=infer_kwargs,
                    build_context="./images/sklearn")
assert vres["pass"], vres
```

## When to rebuild

See the table in [step 3](#step-3--register-the-environments-you-need--one-at-a-time) — and
remember that "rebuild" means *register that one image*, not both. Registering an image you did
not change costs you a version number for nothing.

## Troubleshooting

**`az` returned something that is not a version.** `az ml` tries to auto-upgrade itself and cannot
on an AML compute instance: the extension there lives system-wide at `/opt/az/extensions/ml`,
owned by root, while you run as `azureuser`. It fails with `Permission denied` and leaves the
extension **half-deleted**, after which every `az ml` command breaks. Run these steps from your
laptop, or reinstall the extension with `sudo`.

**Lost a version number.**

```bash
az ml environment list -n fsd-infer-sklearn -g <resource-group> -w <workspace> \
  --query "[].version" -o tsv | sort -V | tail -1
```

**Checking one version exists.** `--version` is required — without it the CLI fails with `Must
provide either version or label`. Do not query `provisioning_state`: it is not in the environment
schema, and `--query` on a missing field prints an empty line that reads like a failure.

**`verify_image` returns `wheel_has_spec44: False`.** The image was built from a pre-spec-44 fsd.
Redo steps 1–4 from a current checkout.

**`verify_image` raises `ValueError: build_context=... contains no fsd-*.whl`.** The wheel was
cleaned out of the build context. Redo step 2; do not delete it afterwards.

**A build failed.** Studio → Environments → the version → build log. Re-running step 3 registers a
fresh version, which is cheap and never mutates the old one.
