---
status: current
summary: The AML image recipe lives in `00_build_images.ipynb` as 110 lines of helpers keyed on the git state of an fsd CHECKOUT, so no consumer can use it. Move it into fsd as a declarative `ImageDefinition` (D1), digest the RESOLVED definition (D2), publish definitions to a storage-seam registry mirroring `fsd.model.registry` (D3), and make `ensure_environment` check-then-build (D4). Eight decisions. Closes #79.
---

# Spec 56 — image definitions, and a registry to keep them in

**Status:** DRAFT — awaiting sign-off. · **Opened:** 2026-08-26
**Closes:** [#79](https://github.com/nikhilsrajan/fsd/issues/79).
**Origin:** the user, 2026-08-26: *"the helper functions written in 00_build_images notebook are
still within the notebook and they need to be selectively pushed into the fsd module so that a
consumer user can also use it. images, just like models, need to be registered. there needs to be a
registry where the definitions are maintained."*
**Related:** [spec 51](51-deploy-model-registry.md) (the model registry this mirrors),
[spec 52](52-registry-on-blob.md) (the same registry on blob), [spec 44](44-inference-image-per-family.md)
(one image per dependency family, not per model), [spec 47](47-verify-image.md) (`verify_image`'s
wheel-staleness gate, which D8 has to replace), [spec 55](55-root-leaves-the-config.md) (the
registry path is *passed*, never configured).

---

## 1. The problem

`notebooks/00_build_images.ipynb` is a hard prerequisite for every AML run, and it is unusable
outside an fsd checkout. Concretely, from the notebook as it stands:

- **The recipe is a Dockerfile in the fsd repo.** `notebooks/images/{base,sklearn}/` — a
  `Dockerfile` plus an `environment.yml` — ships in no wheel (`packages.find where = ["src"]`).
- **The wheel is built from the working tree.** Cell 7 runs
  `{FSD_REPO}/.venv/bin/pip wheel {FSD_REPO} --no-deps` and copies the result into both build
  contexts. A consumer has no `FSD_REPO`.
- **Staleness is keyed on git.** `git_state()` returns `<short sha>[-dirty]` from
  `git -C FSD_REPO status --porcelain -- src pyproject.toml notebooks/images`, and `status()`
  compares it against `.last_registered.json` in the build context. A consumer has no checkout to
  ask, and `.last_registered.json` is a single file on one laptop — nobody else can see what any
  image was built from.
- **110 lines of real logic sit in a notebook cell** — `wheel_digest`, `git_state`,
  `read_record`/`write_record`, `latest_registered`, `status`, `register`, `build_link`, `resolve`
  — several of them carrying scars worth keeping (see D6), none of them importable.

And the thing the user actually asked for is not in there at all: **there is no registry of image
definitions.** AML knows it holds `fsd-aml-env:7`. Nothing anywhere records *what `:7` was built
from* except a JSON file in one developer's build-context folder — the exact gap
`fsd.model.registry` exists to close for models.

## 2. Scope

**In:**

- A declarative image definition in Python, and its content digest.
- An image **definition registry** on the storage seam, mirroring `fsd.model.registry`'s layout.
- `ensure_environment()`: digest → look up → reuse or build → publish the definition.
- Moving the notebook helpers worth keeping into `src/fsd/`, and deleting the rest.
- What replaces `git_state()` as the staleness key, for a consumer and for an fsd developer.
- What `00_build_images.ipynb` becomes.

**Out:**

- **Building images anywhere but AML in v1.** The definition and the registry are backend-agnostic
  by construction (`fsd.image`); the builder is not (`fsd.aml`). A second builder is a later
  module, not a v1 abstraction — YAGNI, per [[fsd-demo-target]]'s standing rule.
- **A local Docker daemon.** The build is AML-side over a zipped context, as today. fsd never
  shells out to `docker`.
- **Publishing prebuilt fsd images to a public registry.** #79's cross-validation notes that
  prebuilt-default is the dominant shape (SageMaker, AzureML curated, Modal), and that it is *"a
  cache in front of this API, not a competing design"*. Still true; still later.
- **Replacing AML's own environment versioning.** AML remains the thing that holds the built
  image and assigns `:N`. This registry holds *definitions*, and the mapping to `name:version`.
- Changing `fsd.model.registry`'s on-disk layout or its public functions.

## 3. Decisions

### D1 — An image is declared in Python, as data

```python
from fsd.image import ImageDefinition

BASE = ImageDefinition(
    name="fsd-aml-env",
    base="mcr.microsoft.com/azureml/openmpi4.1.0-ubuntu22.04:latest",
    fsd="git+https://github.com/nikhilsrajan/fsd@9a00f2b",
    extras=("azure", "mpc"),
)
INFER = BASE.derive(name="fsd-infer-sklearn", extra_pip=("scikit-learn", "joblib"))
```

A frozen dataclass, no methods that touch the network. It renders a Dockerfile
(`render_dockerfile()`) and a build context (`write_context(dir)`); it does not build one. The two
Dockerfiles in `notebooks/images/` become the two-line template this renders, and their comments —
which explain *why* `[azure,mpc]` and not `[aml]` or `[grid]` — move into the module docstring
where a consumer can read them.

*Why a dataclass and not a file the user writes:* every tool surveyed in §8 makes the user declare,
not write a Dockerfile — that is the single most consistent finding across six of them, and #79
already recorded it. A dataclass is also what makes D2 possible: a hashable, comparable value.

**The escape hatch stays** (#79: *"caller may pass their own build context"*).
`ImageDefinition(build_context="./images/mine")` takes a directory the caller owns; fsd digests its
contents (D2) and builds it unchanged. A user whose image needs `apt-get` or a private base is not
blocked on fsd growing a field for it.

### D2 — The digest is of the RESOLVED definition, and of file contents

The digest is what decides "have I already built this", so what goes into it is the whole design.

**Resolve before hashing.** A definition that says `fsd="git+…@main"` is not a definition — `main`
moves. Before digesting, `resolve()` turns every moving reference into a fixed one:

| field | as declared | as resolved |
|---|---|---|
| `fsd` | `git+…@main`, or `path:/Users/…/fsd` | `git+…@<40-char sha>`, or `wheel:<content digest>` |
| `base` | `…ubuntu22.04:latest` | `…ubuntu22.04@sha256:…` when the registry can be asked; the tag as given when it cannot, **recorded as unresolved** |
| `build_context` | a directory path | a digest of its file contents |

This is apko's lesson and Flyte's, arrived at independently by both (§8): apko pins *"exact package
versions and checksums"* into a lock file and Chainguard's `locked_config.json` is *"a fully
resolved apko configuration"*; flytekit replaces `requirements` with a hash of the file's contents
and `source_root` with a digest before computing the tag. **Hash content, never paths.** flytekit
goes further and explicitly nullifies `registry_config` *"won't rebuild the image if we change the
registry_config path"* — the same rule stated as an exclusion.

**Exclude what does not change the image.** Following flytekit's `parameters_to_exclude`, the
digest ignores `name` (renaming an image does not change its contents — it changes where it is
registered) and any purely informational field. The exclusion list is a named constant with a
comment, not an implicit consequence of what happens to be in the dataclass.

**The wheel digest survives, unchanged.** For `fsd="path:…"` — the fsd developer's case — the
existing `wheel_digest()` is exactly right and its docstring already explains why: `pip wheel`
stamps timestamps so two wheels from identical source are never byte-identical, and hashing
`(member name, CRC)` pairs compares *"what is actually INSIDE the wheel"*. That function moves into
`fsd/image/digest.py` verbatim, comment included.

**An unresolved base is a warning, not a silent pass.** If the base image tag could not be resolved
to a digest, the definition is still usable and the entry records `base_resolved: false`. Two
builds of the "same" definition can then differ, and the registry says so rather than implying a
reproducibility it does not have.

### D3 — Definitions are published to a registry on the storage seam

Mirrors `fsd.model.registry` (spec 51 D1), because the user asked for *"a registry ... just like
models"* and because the shape is already proven on blob (spec 52):

```
<registry>/
  fsd-aml-env/
    _aliases.json                 {"current": 7}
    v7/
      image.json                  the resolved definition + the digest + the AML asset it became
      _complete.json              written last; the all-or-nothing marker
    v8/ …
```

`image.json` carries the resolved definition plus provenance, and its provenance fields are **named
after the OCI image-spec annotation keys** rather than invented:

```json
{
  "digest": "9f3c1a…",
  "definition": {"base": "…@sha256:…", "fsd": "git+…@9a00f2b", "extras": ["azure","mpc"],
                 "extra_pip": [], "base_resolved": true},
  "aml": {"name": "fsd-aml-env", "version": "7", "workspace": "…"},
  "org.opencontainers.image.revision": "9a00f2b",
  "org.opencontainers.image.source": "https://github.com/nikhilsrajan/fsd",
  "org.opencontainers.image.base.name": "mcr.microsoft.com/azureml/openmpi4.1.0-ubuntu22.04:latest",
  "org.opencontainers.image.base.digest": "sha256:…",
  "org.opencontainers.image.created": "2026-08-26T14:02:11Z"
}
```

Everything goes through `fsd.storage.fs`, so a local registry and an `abfss://` registry are the
same code — the property spec 52 established and the reason this is not a new storage problem.

**The registry path is an argument.** `fsd.image.registry.publish(registry=..., ...)` takes it;
nothing reads it from config. That is spec 55 D1's rule and spec 54 D3's before it. In practice a
user points it at `f"{ROOT}/image_registry"`, next to `model_registry`.

**Reuse, not re-implementation.** `fsd/model/registry.py` already implements immutable versions,
`_aliases.json` staged-and-renamed, content-digest idempotency, `_complete.json` written last, and
the collision retry — with its concurrency guarantees written down. The generic half of that
(version allocation, alias read/write, completeness marking) moves to `fsd/registry/_core.py` and
both registries call it; the model-specific half (bundle digesting, `_deploy.json`) stays put.
See §7 Q1 — this is the one decision with a cheaper alternative.

### D4 — `ensure_environment()` is check-then-build

```python
env = fsd.aml.ensure_environment(BASE, registry=f"{ROOT}/image_registry", **cfg_kwargs)
#   spec 9f3c1a  ->  fsd-aml-env:7  (registered 2026-08-24, reusing)
```

In order:

1. **Resolve + digest** the definition (D2).
2. **Look it up** in the registry by digest. A hit gives a `name:version`.
3. **Confirm the AML asset still exists** — `az ml environment show`. A registry entry whose asset
   was deleted is stale; do not hand back a version that will fail at job submission. On a miss
   here, fall through to build and publish a new version.
4. **On no hit: build.** Render the context, `az ml environment create`, capture the assigned
   version — with the existing guard from the notebook's `register()`, which exists because
   `v = !az …` cannot fail and a broken `az` once produced
   `built fsd-aml-env:No module named 'rpds.rpds'`. Non-numeric version → raise, loudly.
5. **Publish** the definition at `v<N+1>` and set the `current` alias.

`force=True` rebuilds regardless — flytekit ships the same escape hatch as `force_push()` /
`FLYTE_FORCE_PUSH_IMAGE_SPEC`, and it is needed for the same reason: a base image moved under a
tag you did not pin.

**What `ensure_environment` never does:** wait for the build. An AML v2 image build is an ACR task
run, not an AML job — the notebook's `build_link()` comment records that an earlier version *"polled
for one and printed `0/0` forever"*. It returns immediately with the version and the Studio URL;
the caller waits for `Build status: Succeeded` in the browser. Blocking on a 10–20 minute ACR build
inside a function that looks like a lookup is worse than not blocking at all.

### D5 — The staleness key is the digest, and `git_state()` dies

`git_state()` answers "did anything that goes into this image change?" by asking git about an fsd
checkout. Its replacement answers the same question by asking the definition: the resolved `fsd`
reference *is* the git revision, for anyone installing fsd from a ref, and it is a wheel content
digest for anyone building from a tree. Either way the key travels with the definition instead of
living in one working copy.

This is flytekit's design and #79 already named it: *"`00_build_images.ipynb` already hand-rolls
Flyte's pattern. `status()` + `.last_registered.json` is check-then-build — keyed on git state.
Flyte keys the same check on the spec hash, which is the better key and needs no checkout."*

**`-dirty` does not disappear, it changes meaning.** For `fsd="path:…"` the wheel digest is
computed from the built wheel, so uncommitted edits change the digest — a dirty tree gets a
different image rather than a warning about one. What is lost is the *cheap* dirty check (a
`git status` versus a `pip wheel`), so `ImageDefinition.resolve()` for a `path:` fsd is the one
slow path, and it says so while it runs.

### D6 — What moves, what dies

| notebook helper | fate |
|---|---|
| `wheel_digest` | → `fsd/image/digest.py`, verbatim + its comment (D2) |
| `git_state`, `_IMAGE_INPUTS` | **deleted** — replaced by the resolved `fsd` reference (D5) |
| `read_record` / `write_record` / `RECORD_NAME` | **deleted** — the registry is the record (D3) |
| `latest_registered` | → `fsd/aml/environment.py`, as the AML-asset query |
| `status` | → `fsd.image.status(defn, registry)`, returning a value; printing is the caller's |
| `register` | → folded into `ensure_environment` (D4), guard included |
| `build_link` | → `fsd/aml/environment.py`, returning a **URL string**; the notebook does the `display(Markdown(...))`. A library function must not import IPython. Its WSID/tenant lookup moves with it, including the comment on why `wsid` is asked for rather than string-built |
| `resolve` (version precedence) | **deleted** — `ensure_environment` returns the version; there is nothing to reconcile between a local record and AML |

`status()` returning a value rather than printing is the one behavioural change in the move: the
notebook's version prints six lines and decides nothing, which is right for a notebook and wrong
for a library. It returns a small dataclass (`state`, `digest`, `registered`, `reason`) and the
notebook prints it.

### D7 — `00_build_images.ipynb` becomes a thin caller

Both Parts collapse to a definition and one call each; the wheel-build cell, the git-state cells,
the helpers cell and the Part C "paste these versions" cell all go. Part C is worth keeping in
spirit — carrying versions into the e2e notebook — but it becomes `ensure_environment` returning
them, and the e2e notebook calling `ensure_environment` itself and getting the same answer without
a paste. **That is the actual usability win in this spec:** the paste step between two notebooks
disappears, because both sides can ask the registry the same question.

The notebook keeps: the `az account show` prerequisite check, the prose explaining which image you
need, and Troubleshooting.

### D8 — What replaces `verify_image(build_context=…)`

`verify_image` (spec 47 D11) takes an optional `build_context` and, when given, finds the
`fsd-*.whl` in it and refuses if the wheel predates spec 44. That gate assumes the wheel sits in a
folder on the caller's disk, which is true only for the checkout path.

With a definition-built image the equivalent question — *was this image built from a current fsd?* —
is answered from the registry entry: `image.json`'s resolved `fsd` reference names the exact commit
or wheel digest. So `verify_image` gains an alternative input (`image_ref="fsd-infer-sklearn:4"` +
`registry=`) that resolves through the registry, and `build_context` stays for the checkout path
and for a caller who brought their own context. Neither is removed; the spec-47 behaviour is
unchanged when `build_context` is passed.

*This is the seam most likely to be got wrong in implementation* — `verify_image` is a gate that
`deploy` depends on (spec 51 D5), and loosening it silently would let an unverifiable image through.
Its existing failure modes must keep failing.

## 4. Acceptance criteria

1. **A consumer can build both images with no fsd checkout.** In a venv with fsd installed from a
   git URL, from a directory with no `pyproject.toml` above it: declaring `BASE`/`INFER` and
   calling `ensure_environment` twice registers two AML environments and publishes two definitions.
   (The AML half needs a workspace; the registry/digest half must be exercisable against a
   `tmp_path` registry with the builder stubbed — see 8.)
2. **Digest stability.** The same definition digests identically across processes and machines:
   no `id()`, no dict ordering, no absolute paths in the hashed payload. Two definitions differing
   only in `name` digest **the same**; differing in any resolved field digest differently.
3. **Resolution is real.** `fsd="git+…@main"` resolves to a 40-char sha; `fsd="path:…"` resolves to
   `wheel:<digest>` and equals `wheel_digest()` of the built wheel; an unresolvable base tag sets
   `base_resolved: false` and still digests deterministically.
4. **Check-then-build.** With a registry entry present and the AML asset present, `ensure_environment`
   builds nothing and returns the existing version. With the entry present and the asset **absent**,
   it builds. With `force=True`, it builds even on a hit.
5. **Registry parity with models.** Versions are immutable, `_complete.json` is written last, an
   incomplete version is never resolved, and `_aliases.json` is staged-and-renamed — the same
   guarantees `fsd.model.registry` documents, tested by the same kinds of tests.
6. **Round-trip.** `publish` → `resolve` returns a definition equal to what was published, over a
   local registry and (in the manual runbook) an `abfss://` one.
7. **`verify_image` is not loosened.** Every existing `verify_image` test still passes unchanged;
   the new `image_ref=` path is tested to refuse a definition whose fsd reference predates spec 44,
   the same way `build_context` refuses an old wheel.
8. **No test requires Azure or a network.** The AML builder is behind a seam that tests stub;
   digesting, resolving-from-a-fixture, publishing and looking up all run against `tmp_path`.
   No test may reach a real workspace or a real registry.
9. `pytest -q` and `ruff check src/ tests/` clean; identifier sweep clean (this touches a notebook
   and the docs that name images).
10. `00_build_images.ipynb` has no saved outputs, no hardcoded identifiers, and no `git`/`pip wheel`
    subprocess call left in it.

## 5. Risks

- **Two registries, one shape, and only one of them battle-tested.** Spec 51/52's registry took two
  specs and a real blob run to get right. D3's reuse plan (a shared `_core`) is how this spec avoids
  repeating that, and it is also a refactor of working code that `deploy` depends on — the reason
  §7 Q1 offers the cheaper alternative.
- **A digest that changes when it should not** rebuilds a 10–20 minute image for nothing; a digest
  that *fails* to change when it should silently runs old code on the nodes. The second is far
  worse, which is why D2 excludes conservatively (only `name`) and resolves aggressively.
- **`:latest` in the default base.** The current Dockerfiles use
  `openmpi4.1.0-ubuntu22.04:latest`, and D2 resolves it to a digest when it can. When it cannot,
  two builds of one definition differ. Recorded (`base_resolved: false`), not hidden.
- **The build still is not watched.** D4 returns immediately; a user who does not check Studio will
  submit a job against an environment whose build failed. This is today's behaviour and today's
  documented trap, carried forward — not made worse, not fixed here.
- **Scope creep into a build system.** Multi-arch, SBOMs, apt packages, private bases, a second
  builder. §2 names them out. The escape hatch (`build_context=`) is the pressure valve that keeps
  them out of the dataclass.

## 6. Alternatives considered

- **AML environment tags as the registry** (offered at the decision point, not chosen). Tag each
  AML environment with `fsd_spec=<digest>` and look it up with `az ml environment list`. Cheapest
  possible: no second registry, no storage. Rejected by the user in favour of the storage-seam
  registry. It also ties the record to one workspace — the definition disappears with the
  workspace, cannot be read from a node, and cannot be diffed against a model registry entry
  sitting next to it.
- **Definitions as checked-in files in the consumer repo** (`images/base.toml`). Git is then the
  version history. Rejected: it puts the definition back inside a git tree — the same class of
  place spec 55 just took `root` out of — and it makes "what is `fsd-aml-env:7`?" answerable only
  by whoever has that repo at that commit.
- **Push the definition to ACR as an OCI artifact (ORAS).** Genuinely apt: ORAS exists to *"push a
  file with a custom manifest config"* and ACR documents managing arbitrary artifacts this way, so
  the definition would live *beside the image it describes* — the tightest possible coupling.
  Rejected for v1 on two grounds: it is a second storage backend outside `fsd.storage` (a registry
  auth path, not an `fsspec` URL), and it is Azure-shaped at exactly the layer this spec is trying
  to keep cloud-agnostic. Worth revisiting if fsd ever pushes images itself rather than asking AML
  to build them.
- **Keep `.last_registered.json`, just move it into fsd.** Rejected: it is per-machine, and the
  user's ask was explicitly for a registry.
- **Make `ensure_environment` wait for the ACR build.** Rejected: see D4. The notebook already
  learned this the expensive way.
- **Have the Dockerfile `pip install fsd` from PyPI.** Not yet possible — #82 (the `v0.1.0` tag) is
  deliberately last on the phase-2 path, and a git ref works today (verified 2026-08-26). The
  definition's `fsd` field takes any pip-installable reference, so PyPI is a value change, not a
  design change.

## 7. Questions at sign-off

**Q1 — extract `fsd/registry/_core.py`, or copy the ~120 lines?** D3 assumes extraction: one
implementation of version allocation, aliases, completeness and the collision retry, used by both
registries. *For:* one place to fix a concurrency bug; the model registry's guarantees are
documented and hard-won, and a copy will drift. *Against:* it refactors a module `deploy` depends
on, in the same spec that adds a new one — and spec 52's own §5 shows how subtle that code is.
**Recommendation: extract, but as step 0 of §9, with the model registry's existing tests green and
unmodified before anything image-related is written.** If step 0 turns out to touch more than
mechanical moves, stop and copy instead.

**Q2 — where does the registry live by default?** `f"{ROOT}/image_registry"` next to
`model_registry` is the obvious answer and the one D3 assumes. But images outlive runs even more
than models do (spec 51's `REGISTRY = f"{AZ_ROOT}/model_registry"` comment already makes this
argument), and a single image registry per *platform* — shared by every project under that storage
account — would mean the second project reuses the first's images instead of rebuilding them.
*Proposal:* take no default. `registry=` is required, the two notebooks pass
`f"{ROOT}/image_registry"`, and platform-wide sharing is something a user opts into by passing a
path that is not under their run root. **This is a question about your intent, not about code.**

**Q3 — does `ImageDefinition` cover apt packages in v1?** The current Dockerfiles need none, and
`build_context=` is the escape hatch. *Proposal:* no `apt` field in v1; add one when a real image
needs it.

## 8. Best-practice alignment / sources

Per-source credit — what each source specifically contributed. #79 already carried a six-tool
survey (Flyte, Modal, SageMaker, Azure ML curated, Ray, Coiled) establishing that **no popular
package makes the user write the Dockerfile** and that **Coiled's `gdal` caveat rules out
"replicate my local env" for fsd**; that survey is not repeated here. What follows is the second
round the user asked for — *how have other projects solved the specific problems this spec has*:
keying a rebuild, storing a definition, and making a definition reproducible.

**flytekit `image_spec.py` — the source, not the docs**
([github.com/flyteorg/flytekit/blob/master/flytekit/image_spec/image_spec.py](https://github.com/flyteorg/flytekit/blob/master/flytekit/image_spec/image_spec.py),
fetched 2026-08-26). Contributed **D2's three rules, each of which is a line in that file**.
(1) *Hash the dataclass, minus an explicit exclusion list* —
`parameters_to_exclude = ["pip_secret_mounts", "builder", "runtime_packages"]`, applied via
`asdict(..., dict_factory=...)` — which is why D2's exclusions are a named constant rather than an
accident. (2) *Digest file contents, never paths* — before the tag is computed, `requirements` is
replaced by a SHA1 of the file's contents and `source_root` by a digest. (3) *A path that does not
affect the image must not affect the key* — `registry_config` is explicitly nullified so flytekit
*"won't rebuild the image if we change the registry_config path"*. Its `exist()` — ask the registry
for the tag before building — is D4's step 2.

**Flyte ImageSpec documentation**
([docs-legacy.flyte.org/en/latest/user_guide/customizing_dependencies/imagespec.html](https://docs-legacy.flyte.org/en/latest/user_guide/customizing_dependencies/imagespec.html),
fetched 2026-08-26). Contributed **the check-then-build statement D4 is modelled on** — *"Before
building the image, Flytekit checks the container registry first to see if the image already
exists. By doing so, it avoids having to rebuild the image over and over again"* — and **the
force-rebuild escape hatch** (`FLYTE_FORCE_PUSH_IMAGE_SPEC=True` / `force_push()`), which is why
D4 has `force=True` rather than treating a digest hit as final.

**Metaflow — technical overview / datastore**
([docs.metaflow.org/internals/technical-overview](https://docs.metaflow.org/internals/technical-overview),
fetched 2026-08-26). Contributed **the independent precedent for D3's shape**: Metaflow *"uses [the
data store] as a content-addressed storage. Both code and data are identified by a hash of their
contents, similar to Git"*, persisted to *"an object store"* (S3, with local disk for development),
storing *"an immutable snapshot of the relevant code in the working directory ... at the time when
the run was started"*, with *"equal copies of data deduplicated automatically"*. That is
digest-keyed, immutable, object-store-backed — the same three properties `fsd.model.registry`
already has and this spec reuses, from a project that arrived at them for the same reason (an
execution environment that must be reconstructable later, from a machine that is not the one that
built it). It is also the direct answer to *"is a registry on blob the normal thing to do"*: yes.

**apko / Chainguard — declarative image definitions and lock files**
([github.com/chainguard-dev/apko](https://github.com/chainguard-dev/apko) +
[edu.chainguard.dev](https://edu.chainguard.dev/open-source/build-tools/apko/getting-started-with-apko/),
[chainguard.dev/unchained/reproducing-chainguards-reproducible-image-builds](https://www.chainguard.dev/unchained/reproducing-chainguards-reproducible-image-builds),
fetched 2026-08-26). Contributed **D2's resolve-before-hashing rule and the vocabulary for it**.
apko builds *"OCI images from APK packages directly without Dockerfile"* from *"a YAML based
declarative definition"* — the same declaration-not-Dockerfile move as D1, from outside the Python
ML world, which is what makes it evidence rather than fashion. The load-bearing part is the lock
file: `apko resolve` produces `apko.lock.json`, which *"pins the exact versions and checksums of
all packages required to build your image"*, and Chainguard's published images carry a
`locked_config.json` — *"a fully resolved apko configuration ... Because the package versions are
pinned, builds are reproducible: the same locked_config.json produces the same image content."*
That is exactly D2's declared-vs-resolved table, and the reason `image.json` stores the **resolved**
definition rather than the one the user typed.

**OCI Image Specification — pre-defined annotation keys**
([github.com/opencontainers/image-spec/blob/main/annotations.md](https://github.com/opencontainers/image-spec/blob/main/annotations.md),
fetched 2026-08-26). Contributed **D3's field names**. The notebook's `.last_registered.json`
hand-rolled `git_state` / `registered_at`; the standard already has names for these:
`org.opencontainers.image.revision` (*"Source control revision identifier for the packaged
software"*), `org.opencontainers.image.source` (*"URL to get source code for building the image"*),
`org.opencontainers.image.created` (*"date and time on which the image was built, conforming to RFC
3339"*), plus `org.opencontainers.image.base.name` / `.base.digest` for the base image. Using them
means a later tool that reads image provenance finds keys it recognises, and it settles a naming
argument with a citation instead of taste.

**ORAS / OCI artifacts — the alternative that was weighed**
([oras.land/docs/how_to_guides/manifest_config](https://oras.land/docs/how_to_guides/manifest_config/),
[learn.microsoft.com/azure/container-registry/container-registry-manage-artifact](https://learn.microsoft.com/en-us/azure/container-registry/container-registry-manage-artifact),
fetched 2026-08-26). Contributed **§6's ORAS alternative and the grounds for declining it**. ORAS
pushes arbitrary files with a custom manifest config (`oras push --config
config.json:application/vnd.oras.config.v1+json …`), and ACR documents this as a supported way to
manage non-image artifacts — so storing the definition next to the image is a real, vendor-blessed
option. It is declined because it is a storage backend outside `fsd.storage`'s `fsspec` seam and it
is Azure-shaped at the one layer this spec keeps cloud-agnostic.

**Azure ML environments** — carried over from #79's survey (curated environments, workspace-scoped
asset versioning). Contributes the constraint that **AML assigns the version**, which is why D3's
`image.json` records `aml.version` rather than fsd inventing one, and why D4 step 3 has to confirm
the asset still exists.

## 9. Implementation note — build order

Each step is independently testable; do not start the next until the previous is green. Steps 0–3
need no Azure at all.

0. **`fsd/registry/_core.py`** (§7 Q1) — move version allocation, `_aliases.json`, `_complete.json`
   and the collision retry out of `fsd/model/registry.py`. **`fsd/model/registry.py`'s public
   functions and its tests must not change.** If this step grows beyond mechanical moves, stop and
   take Q1's fallback (copy).
1. **`fsd/image/definition.py`** — `ImageDefinition`, `derive`, `render_dockerfile`,
   `write_context`. No network, no digest yet.
2. **`fsd/image/digest.py`** — `wheel_digest` (moved verbatim), `resolve()`, `digest()`. The
   exclusion list as a named constant. Tests: AC 2 and 3.
3. **`fsd/image/registry.py`** — `publish`, `resolve`, `find_by_digest`, `status`, on `_core`.
   Tests: AC 5 and 6 against `tmp_path`.
4. **`fsd/aml/environment.py`** — `latest_registered`, `build_link` (returning a URL),
   `create_environment` (the `az` call + the non-numeric-version guard). This is the only module
   that touches Azure; it sits behind a seam the tests stub (AC 8).
5. **`fsd/aml/__init__.py` + `ensure_environment`** — D4's five steps. Tests with the builder
   stubbed: AC 4.
6. **`verify_image`** — the `image_ref=` + `registry=` path (D8). **Run the existing spec 47 tests
   first and confirm they are green and unmodified after.**
7. **`00_build_images.ipynb`** — D7. Delete the wheel-build, git-state and helper cells; two
   definitions, two calls. Clear outputs.
8. **`notebooks/images/`** — delete `base/` and `sklearn/` once the rendered Dockerfile is proven
   equivalent (diff the rendered text against the current file before deleting; they must match
   modulo comments). `DROPPED.md` gets the entry.
9. **Docs** — `docs/howto/build-the-images.md` rewritten around `ensure_environment`; `CHANGES.md`;
   `RECIPES.md` gets the "what was this image built from" one-liner.
10. **Full suite + ruff + identifier sweep**, then a real AML run of the rewritten notebook —
    **this spec is not done on green tests** (MEMORY `real-run-beats-review`: the last two specs
    were both caught by a real run, not by review).
