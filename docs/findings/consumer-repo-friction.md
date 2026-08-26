---
status: current
summary: What a consumer of the fsd package actually hits when reconstructing the AML e2e notebook from a pip install — eight friction points, four of them hard stops, logged while standing up a separate repo. Opened 2026-08-26.
---

# Finding — what a consumer of the fsd *package* hits

**Observed:** 2026-08-26, standing up `rise/` — a separate repository that consumes fsd as an
installed dependency (phase 2).
**Method:** `pip install git+https://github.com/nikhilsrajan/fsd` into a clean Python 3.11 venv,
then attempt to reconstruct `notebooks/e2e_austria_aml.ipynb` from what the install and the public
GitHub repo actually provide. No cluster time spent.
**Tracking issues:** [#78](https://github.com/nikhilsrajan/fsd/issues/78),
[#80](https://github.com/nikhilsrajan/fsd/issues/80),
[#82](https://github.com/nikhilsrajan/fsd/issues/82),
[#79](https://github.com/nikhilsrajan/fsd/issues/79),
[#81](https://github.com/nikhilsrajan/fsd/issues/81).

> **This finding is a log, not a single measurement.** Unlike `cloud-overhead.md` and
> `workload-regimes.md`, it is appended to as the consumer repo is built — the friction *is* the
> deliverable of phase 2 (MEMORY `fsd-notebook-usability-sprint`, build-order decision
> 2026-08-21: *file issues, build nothing; phase-2 fixes should be designed against lived
> experience*). Entries carry their own observation date. Numbers already recorded are not edited.

## The starting position, exactly

`rise/` on 2026-08-26: an empty git repo (no commits), a `.venv`, a three-command `README.md`, a
blank one-cell `notebooks/e2e_austria_aml.ipynb`, and a one-line `requirements.txt`:

```
git+https://github.com/nikhilsrajan/fsd
```

That install yields **fsd 0.1.0, 135 packages, no extras**. The wheel's `RECORD` contains
`fsd/**` plus `fsd-0.1.0.dist-info/**` and nothing else — no notebooks, no `env.example.sh`, no
`_config.py`, no shapefiles, no docs. `[tool.setuptools.packages.find] where = ["src"]` is why.

## The frame: two users, one repo, one package

Established by the user, 2026-08-26:

- A **developer user** clones the repo. They get everything — notebooks, docs, tutorials, test
  geometries, image build contexts.
- A **consumer user** `pip install`s. They get **code and dependencies only**. The package should
  be as small as it can be; every non-code asset stays *discoverable in the GitHub repo* rather
  than shipped.
- The two have **separate how-to documents**. A consumer how-to that says `pip install -e ".[…]"`
  is a developer document wearing the wrong label.

The current wheel already satisfies the package half of this. What does not yet hold is the other
half: several assets a consumer must fetch by hand are **not in the GitHub repo either**, so
"go look in the repo" is not yet true advice.

## Friction log — 2026-08-26

| # | what happens | class | approach | issue |
|---|---|---|---|---|
| P1 | `env.example.sh` is not in the install and is never named by install-facing docs | **hard stop** | superseded by `fsd init` + user-level config | [#78](https://github.com/nikhilsrajan/fsd/issues/78) |
| P2 | `_config.py` raises at **import time** outside a checkout | **hard stop** | same — `find_repo()` goes away | [#78](https://github.com/nikhilsrajan/fsd/issues/78) |
| P3 | `notebooks/shapefiles/*.geojson` is gitignored, so the training data is not on GitHub | **hard stop** | track it in git; keep it out of the wheel | — |
| P4 | the extras set is undiscoverable and the three documented sets disagree | **hard stop** | consumer how-to, distinct from the developer one | — |
| P5 | no tag exists; `@main` is not a pin | friction | tag `v0.1.0` **after** the first consumer notebook works | [#82](https://github.com/nikhilsrajan/fsd/issues/82) |
| P6 | `README.md`'s install line uses `git+ssh://` | friction | — | — |
| P7 | image versions are hand-pasted integers from another notebook | friction | a build-images notebook on the **consumer** side too | — |
| P8 | `ipykernel` is undeclared | friction | — | — |

### P1 — `env.example.sh` is unreachable from an install

The documented bootstrap is `cp env.example.sh env.local.sh`. `env.example.sh` lives at the fsd
**repo root**; it is tracked in git, so it is visible on GitHub, but it is not in the wheel and
nothing a consumer reads points at it. `README.md`'s install section does not mention it;
`docs/howto/run-at-scale.md` does, once, in a prerequisites bullet — a developer document.

The failure mode is circular: `_config.env_local()` raises
`FileNotFoundError: … Create it once: cp {REPO}/env.example.sh {path}` where `REPO` is a checkout
the consumer does not have.

**This was already decided.** Issue #78 (user, 2026-08-21) replaces both the template and the
loader with `fsd init` writing `~/.config/fsd/config.toml`, read back by `fsd.config.load()`.
The cross-validation is recorded in the issue: the six `AZ_*` values are **addresses, not
secrets** — `az login` + `DefaultAzureCredential` carry the actual credential — and a user-level
config location makes the gitignore problem *disappear* rather than become fsd's to manage,
"which is why `az`, `gcloud` and `earthengine` all store config outside the project tree."
That decision **overturns spec 41 D7**, which put the template at the repo root, and it needs a
spec of its own before implementation.

*Open, for that spec:* whether `env.example.sh` + `_config.NOTEBOOK_VARS` +
`tests/test_docs.py::test_env_example_declares_exactly_the_notebook_vars` are retired outright or
kept as the checkout-only developer path (#78 lists this as an explicit undecided consequence).

### P2 — `_config.py` cannot be imported outside a checkout

```python
REPO = find_repo()        # module scope — crashes on import
```

`find_repo()` walks upward for `pyproject.toml` **and** `src/fsd/`. A consumer repo has neither,
so copying `_config.py` next to the notebook does not rescue it: cell 3 raises `RuntimeError`
before a single line of user code runs. `REPO`, `NOTEBOOKS`, `ENV_LOCAL` and the notebook's
`SHAPEFILES` all derive from it. Same fix as P1.

### P3 — the training data is not on GitHub

`.gitignore:26` is a blanket `*.geojson`. It catches `notebooks/shapefiles/` — `AT_2018_TRAIN.geojson`
(900 fields, 938 KB), `AT_ROI.geojson`, `s2grid=476da24.geojson`. The notebook's first data cell
reads a file that exists only on the author's machine, and no substitute is named.

**Approach (user, 2026-08-26):** the test geometries **must exist on GitHub** — un-ignore them —
**and must not travel in a package install**. Those two are not in tension here: git tracking and
wheel contents are set by different mechanisms, and `packages.find where = ["src"]` already
excludes anything outside `src/` from the wheel unconditionally.

**The precedent is in-repo:** spec 42's tutorial fixture does exactly this.

```gitignore
# .gitignore:32-38 — the existing pattern to copy
!tests/data/tutorial/
!tests/data/tutorial/**
```

`tests/data/tutorial/` holds tracked `fields.geojson` + `roi.geojson` + `catalog.parquet` and a
`NOTICE` reading *"Contains modified Copernicus Sentinel data 2018"*. It is in git, absent from
the wheel, and carries its attribution. `notebooks/shapefiles/` should follow it — including the
`NOTICE`, which **`CLAUDE.md` already claims exists there and does not** (the Austria fields are
EuroCrops-derived, so attribution is owed).

*Note for whoever does it:* the exception must un-exclude the directory **before** its contents,
as lines 36–37 do; a bare `!notebooks/shapefiles/**` under a `*.geojson` rule does not work.

### P4 — the extras are undiscoverable, and the three sources disagree

| source | what it says |
|---|---|
| `README.md` install section | `[notebooks]` · `[azure]` · `[dev]` |
| `docs/howto/run-at-scale.md` | `pip install -e ".[dev,azure,aml,mpc,grid,model-example]"` |
| `e2e_austria_aml.ipynb` cell 0 | `pip install -e ".[dev,aml,mpc,azure,grid]"` |

The last two disagree on `model-example`, and **all three are the editable, checkout-only form.**
Nowhere in the repo is there a git-URL-plus-extras line — which is the only line a consumer can
use.

Measured need, by probing the `rise` venv against the notebook's imports and call arguments:

| notebook does | needs | in extra |
|---|---|---|
| `AZ_ROOT` is an `abfss://` URL | `adlfs`, `azure-identity` | `azure` |
| `runner="aml"` | `azure-ai-ml` | `aml` |
| `source="mpc"` | `planetary-computer` | `mpc` |
| ROI → grid cells for inference | `s2`, `s2cell` | `grid` |
| trains a RandomForest, `joblib.dump` | `scikit-learn`, `joblib` | *the user's own, not fsd's* |
| runs as a notebook | `ipykernel` | *not declared anywhere* |

`sklearn`/`joblib` are deliberately listed as the consumer's own dependencies rather than pulled
via fsd's `[model-example]` or `[notebooks]` extra: **fsd does not train models**, so a consumer
declaring its own training stack is the honest expression of that boundary. This is what the
consumer how-to should show:

```
fsd[azure,aml,mpc,grid] @ git+https://github.com/nikhilsrajan/fsd@main
scikit-learn
joblib
ipykernel
```

Interaction with [#80](https://github.com/nikhilsrajan/fsd/issues/80): moving `snakemake` → `[local]`
and `s3fs` → `[s3]` (−53 packages / −111 MB, zero code change) changes this line's meaning, since
a consumer on the AML path needs neither. #80 lands **before** any tag, because a tag pins the
dependency set.

### P5 — nothing to pin to

`git tag` is empty; no release has ever been cut. `pyproject.toml` already declares
`version = "0.1.0"`, so `v0.1.0` is the consistent first tag, and #82's stated blocker (unpushed
commits) is gone as of 2026-08-26.

**Approach (user, 2026-08-26):** cut the tag **after the first consumer-side notebook is working**,
not before. Reasoning: a tag pins the dependency set and the asset layout, and both are still
moving — P3's un-ignore and #80's extras split should land inside `v0.1.0`, not force a `v0.2.0`
and an edit in every consumer.

Until then `@main` is the honest spelling, and the consumer how-to should say it is not a pin.

### P6 — `README.md` advertises the SSH URL

```bash
pip install "git+ssh://git@github.com/nikhilsrajan/fsd.git"
```

Requires an SSH key registered with GitHub. For a public MIT repo, `https://` is the form that
works for a stranger; `rise` used it without being told to.

### P7 — hand-pasted image versions

```python
AZ_ENV_VERSION       = "8"   # <- paste from 00_build_images.ipynb Part C
AZ_INFER_ENV_VERSION = "6"   # <- paste from 00_build_images.ipynb Part C
```

AML auto-increments on every register, so these change on every rebuild, and nothing checks that
the integer in the notebook is the image the bundle was verified against. `verify_image` catches a
*stale* image, not a *mistyped version*.

**Approach (user, 2026-08-26):** the consumer side probably needs its **own build-images
notebook** — the images are built from `notebooks/images/base/` and `notebooks/images/sklearn/`,
whose Dockerfiles are tracked but whose `fsd-*.whl` is gitignored (`.gitignore:90`), so a consumer
cannot currently reproduce a build context. Scope call still open: does the consumer repo build
its own images, or consume images built by a platform admin? That decides whether
[#79](https://github.com/nikhilsrajan/fsd/issues/79) is inside phase 2 or after it.

### P8 — `ipykernel` undeclared

`rise/.venv` has `ipykernel 7.3.0` only because VS Code injected it. A clean
`pip install -r requirements.txt` from that repo produces a venv with no kernel.

## What is *not* wrong

- **The wheel is already code-only.** 135 packages is dependency weight, not payload; the payload
  is `fsd/**` plus `workflows/_snakefiles/**`. "Ship less" is about dependencies
  ([#80](https://github.com/nikhilsrajan/fsd/issues/80), [#81](https://github.com/nikhilsrajan/fsd/issues/81)),
  not about files.
- **~420 MB is the dependency floor** — pyarrow 127, scipy 99, pyogrio 74, pandas 73, rasterio 61,
  numpy 36. 689 → ~420 MB is reachable; "tiny" is not (#80).
- **Azure prerequisites are not fsd's to fix.** A workspace, a cluster, a UAMI with blob RBAC and
  VPN are platform-admin actions (spec 41 D2). A stranger cannot run this notebook, and that is by
  design — the runnable stranger path is `docs/tutorial.md`. Do not confuse *hard because Azure*
  with *hard because fsd*.

## Method notes

Everything above is read-only inspection: `pip show` / `pip list` in `rise/.venv`, the installed
`RECORD`, `git ls-files` and `git check-ignore -v` in the fsd checkout, and the notebook JSON.
Nothing was downloaded, dispatched or built.
