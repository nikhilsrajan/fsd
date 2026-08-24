---
status: current
summary: P6 — `fsd.deploy` turns a bundle plus the inference image that has been PROVEN to run it into one immutable, resolvable name. The registry is a prefix on the storage seam (no new service); versions are immutable, aliases are the only mutable pointer; deploy refuses to register a pair it cannot verify. Completes spec 44's un-signed-off phase 2 (D7/D8), closes ROADMAP §7's open "where is the bundle registered" question and ADR 0002's forward reference, and removes spec 44 D8's measured 627 s per run of redundant bundle upload.
supersedes: specs/44-bundle-carried-adapter-code.md D7, D8 (phase 2, proposed and never signed off)
---

# Spec 51 — `fsd.deploy`: a verified bundle+image pair, under one name (P6)

**Status: ✅ SIGNED OFF 2026-08-22 — NOT YET IMPLEMENTED.** Three structural
questions were put to the user before drafting (2026-08-22) and answered: the registry is a
**storage-seam prefix** (not ACR/ORAS, not the AML registry); `deploy()` **requires a verified
image** rather than building one; versioning is **immutable versions + mutable aliases**, the shape
MLflow moved to after stages. Those are D1, D5 and D3. **All seven §7 questions were then answered
(user, 2026-08-22)** — one against the draft's proposal (**Q4**: `deploy` takes a saved bundle only,
never a live adapter, rewriting D6), one reframed into a new decision (**Q6**: the central location
is undecided *on purpose*, so **D11** makes the registry relocatable instead of blocking on it), and
**Q7** finally answering the MLflow question spec 44 left open in July. Nothing in `src/` is touched
yet.

> **⚠️ This spec supersedes `specs/44-bundle-carried-adapter-code.md` D7 and D8**, which proposed
> phase-2 `deploy` registration and were explicitly left un-signed-off ("*Sign this off separately
> from phase 1 if you would rather not settle it yet*", spec 44 §7 Q5). Spec 44 phase 1 — the
> bundle carrying its adapter source — is implemented and unaffected. **Where this spec agrees with
> D7 it says so rather than re-deciding**: the blob-via-storage-seam store, immutability, and the
> ACR/AML rejections are spec 44's calls, confirmed by the user again on 2026-08-22. What is new
> here is the bundle↔image **binding** (D5/D6/D7), aliases generalising D7's single `latest`
> pointer (D3), and answers to spec 44's own open questions Q5 and Q7.

> **The one sentence:** running a model at scale needs a bundle, an image that can run it, and the
> knowledge that the two go together — fsd produces all three today and then throws the third one
> away, so `deploy` is the verb that makes it a durable fact instead of a notebook constant.

---

## 1. The gap

P4 made inference-at-scale work. It did not make it *nameable*. Three things must line up before a
fan-out is safe, and fsd currently tracks only the first two:

| | what it is | where it lives today |
|---|---|---|
| the bundle | adapter code ref + artifacts + spec | a local folder path the caller remembers |
| the image | an AML Environment with the deps installed | a string the caller pastes |
| **the pairing** | *this image can run this bundle* | **nowhere** |

`fsd.model.verify_image` establishes the pairing — one real node, ~40–380 s — and writes the proof
to a `_result.json` on the operator's laptop. Nothing consumes it. The very next call passes the
environment by hand. The e2e notebook is explicit about the cost, in its own configuration cell:

```python
AZ_INFER_ENV_NAME    = "fsd-infer-sklearn"
AZ_INFER_ENV_VERSION = "6"   # <- paste from 00_build_images.ipynb Part C
# AML auto-increments on every register, so these change every time you rebuild.
```

That is the pairing, encoded as a human copy-paste with a comment warning it goes stale.

Three specific holes follow.

**H1 — a bundle has no identity.** `bundle.save(adapter, artifacts, "./demo_bundle")` overwrites in
place. Two different models, or the same model retrained, can occupy the same path on different
days. A run cannot be reproduced from the model's name, because the name is a mutable directory.

**H2 — the pairing is folklore.** Nothing records that `fsd-infer-sklearn:6` was verified against
*this* bundle. Rebuild the image (version 7) and every previously-verified bundle silently refers to
a version that no longer exists; nothing notices until a node fails.

**H1a — and it costs real money.** Because a bundle has no registered location, the dispatcher
re-uploads it on **every run**. Spec 44 D8 measured that at **627 s per run**. Registration deletes
it outright: the nodes read the bundle from where it already lives.

**H3 — nothing enforces deployability.** `api._ensure_bundle` auto-saves a live adapter with
`code=None` and **no `requirements=`** — a bundle that loads fine locally and declares no
dependencies at all. It is indistinguishable, by inspection, from one a human bundled deliberately.
The notebook works around this by keeping a separate `bundle.save` cell whose only real job is to
supply `requirements=`, which reads as redundant and is not.

### Why this is P6 and not a patch

ROADMAP §7 has carried *"Where the model bundle is stored/registered on cloud (ACR? blob? AML
registry?) — P6"* as an open question since P0. ADR 0002 and ADR 0018 both forward-reference P6 as
the home for registration. `api.deploy` already exists as a stub that raises `NotImplementedError`
with the scope written into it. This spec is that stub, filled in.

---

## 2. Scope

**In:** an immutable, resolvable name for a bundle (D2/D3/D4); the bundle↔image binding as a
recorded artifact (D7); refusing to register an unverified or undeployable pair (D5/D6); resolution
at the one existing chokepoint (D4); the registry layout documented well enough that a second
backend is additive (D10).

**Out:** **building or registering the inference image** — ADR 0002 says P6 is where image-build
gets automated *later*, and D8 keeps that "later" (`00_build_images.ipynb` stays the operator step).
**An OCI/ACR-backed registry** — evaluated, deferred, §6. **The AML model registry** — rejected,
§6, it breaks the runner seam. **Serving/endpoints** — that is P5, and the user has explicitly
sequenced P5 after this. **Model training** — permanently out of scope (ADR 0018). **Changing the
bundle format** — pinned by spec 18 / F5; this spec adds a sibling record, never a manifest field.
**Access control** — the registry is a storage prefix and inherits exactly the storage's ACLs; it
is not a security boundary (§5).

---

## 3. Decisions

### D1 — the registry is a prefix on the storage seam, not a service [Q1: user, 2026-08-22]

```
<registry>/                        e.g. ./models   or   abfss://.../<root>/models
  crop-rf/
    _aliases.json                  {"champion": 3, "current": 4}
    v1/  bundle.json, code/, artifacts…, _deploy.json
    v2/  …
```

Everything reads and writes through `fsd.storage.fs`, so a local registry and a blob registry are
the same code and the same layout. This is CLAUDE.md's storage-seam rule applied to one more
artifact class, and it needs **no new infrastructure on `rise`** — the project storage account
already exists and the compute identity already has Storage Blob Data Contributor on it.

The alternatives were real and are recorded in §6: ACR via ORAS (the registry `rise` *also* already
has, with AcrPush already granted) and the AML model registry. Both were rejected for v1, for
different reasons — but note what D10 preserves.

### D2 — a version is immutable; publishing is atomic; identical content is a no-op

A version directory, once written, is never rewritten. `deploy` computes a **content digest** over
the bundle's files (sorted relative path + bytes, SHA-256) and:

- if a version with that digest already exists → **returns it**, writes nothing. `deploy` is
  idempotent, which is what makes it safe in a notebook people re-run.
- otherwise → allocates the next integer version and publishes.

Version numbers are monotonic integers because humans read them; the digest is recorded alongside
because integers do not detect tampering. Both go in `_deploy.json` (D7).

**Publishing is a `storage.fs.rename`.** The bundle is staged to a sibling `.staging-<uuid>` prefix
and renamed onto `v<N>` only when complete — `fs.rename` is documented in `storage/fs.py` as the
atomic-publish primitive (one metadata operation on an HNS account, `os.rename` locally), so a
reader never observes a half-published version. A losing racer on `v<N>` retries at `v<N+1>`.

### D3 — versions are immutable, aliases are the only mutable pointer [Q3: user, 2026-08-22]

`_aliases.json` maps a name to a version integer. `deploy(..., alias="champion")` publishes and
repoints in one call. Promotion is an alias reassignment, never a state transition, and multiple
aliases may point at one version.

**This generalises spec 44 D7 rather than contradicting it.** D7 already had exactly one mutable
name — a `latest` pointer file — and immutable versions underneath. Aliases are that idea with the
count relaxed from one to N, so `latest` becomes an ordinary alias with no special status.

**Ref syntax follows MLflow's own split**, which also keeps D7's spelling intact:

| ref | means | from |
|---|---|---|
| `"crop-rf:3"` | version 3, exactly | **spec 44 D7, unchanged** |
| `"crop-rf@champion"` | whatever `champion` points at | new (MLflow's `models:/name@alias`) |
| `"crop-rf"` | error — ambiguous, names the two forms | new |

A bare name is refused rather than defaulting to `latest`: a default that silently follows a moving
pointer is the failure mode aliases exist to make *visible*.

This is deliberately the shape MLflow arrived at *after* trying the other one: its lifecycle
**Stages** (`None`/`Staging`/`Production`) are deprecated in favour of aliases, precisely because a
fixed one-of-N state machine could not express "this version is both the champion and the thing
QA is testing" (§8). fsd adopts the destination rather than repeating the journey.

The cost is honest and is §5's first risk: an alias makes a run's meaning time-dependent. D7's
recorded resolution is the mitigation.

### D4 — resolution is one idempotent step, applied wherever `model` is first read as a path

> **Amended 2026-08-22 (user, at step-1 review).** The original heading read "resolution happens at
> `_ensure_bundle`, the one chokepoint that already exists", and its premise was **wrong**:
> `_ensure_bundle` is the one place that turns `model` into a bundle path *for a subprocess*, but
> it is **not** the first place a verb reads `model` as a path. `api._model_spec` — which reads
> `bundle.json` to preflight `required_bands`/`n_timestamps` — runs **before** it in both
> `run_inference` (`api.py`, pre-dispatch) and `verify_adapter`, and the `cores=1` pre-built-cubes
> path hands `model` straight to `engine.run_local` without calling `_ensure_bundle` at all. Step 1
> implemented resolution only at `_ensure_bundle` and was green in unit tests, yet
> `run_inference(model="crop-rf@champion", registry=…)` still died with
> `FileNotFoundError: crop-rf@champion/bundle.json` — proven by running it, not by reading it.
> The fix below is what the user signed off ("Option A") at review.

Resolution is therefore **one helper, `api._resolve_model_ref(model, registry, *, why)`, that is
idempotent and shape-gated**, called at *every* site that reads `model` as a path — today
`_model_spec`'s two call sites and `_ensure_bundle`:

- **shape-gated:** a string is ref-shaped only if it carries **no path separator** (`/` or `\`) and
  parses as `name:value` / `name@value`. That is what keeps resolution off `abfss://<fs>@<account>…`
  (which embeds `@` legitimately), off `s3://`/`https://`, and off local paths that merely contain
  `@` (`/data/rf@2026/bundle`). A bare `rf@v1` *is* ambiguous and is treated as a ref; `./rf@v1`
  says "path, literally".
- **idempotent:** an already-resolved version path is not ref-shaped, so a second call passes it
  through untouched. This is the point of Option A — a fourth call site added later cannot
  reintroduce the bug above by running before the resolving one.
- The cost, accepted: `registry=` given alongside a real *path* is silently ignored rather than
  refused, because "ignore what does not apply" is what makes repeat calls safe. `registry=` given
  alongside a **live adapter** is still a `PreflightError` (nothing to resolve, and the combination
  can only be a mistake).

The behaviour table is unchanged:

| `model=` | behaviour |
|---|---|
| a live adapter | auto-save (unchanged, spec 48) |
| a bundle path or URL | used as-is (unchanged) |
| `"crop-rf@champion"` / `"crop-rf@v3"` **and** `registry=` given | **new** — resolved to a version path |

A `name@ref` string **without** `registry=` is a `PreflightError` naming the missing argument, never
a silent fallback to treating it as a path. fsd names its inputs explicitly everywhere else
(`catalog_filepath`, `run_folderpath`, `export_folderpath`); an ambient default registry would be
the one piece of magic in the API.

### D5 — `deploy` refuses a pair it cannot verify [Q2: user, 2026-08-22]

```python
fsd.deploy(bundle_or_adapter, name="crop-rf", registry=..., environment="fsd-infer-sklearn:6",
           runner="aml", runner_kwargs=..., alias="champion")
```

`deploy` establishes the pairing before it records it, in one of two ways:

- **runs `verify_image`** itself (the default) — one node, the cost gate 2 already charges; or
- **accepts a prior verification** via `verified=<_result.json path or dict>`, which is honoured
  **only if** its recorded bundle digest and environment both match what is being deployed.
  A stale or mismatched result is refused, not ignored.

`pass=False` refuses the deployment and returns the verification's own `error`. This is what makes
`deploy` an enforcement point rather than a filing cabinet: the registry's guarantee is not "these
bytes exist" but "**this image ran this bundle**".

### D6 — `deploy` takes a SAVED bundle only, and it must declare its dependencies
[Q4: user, 2026-08-22 — default overturned]

`deploy(bundle_path, ...)`. **A live adapter is refused**, with an error naming
`fsd.model.bundle.save`. The draft proposed accepting both via `_ensure_bundle`; the user overturned
it, and the result is simpler than the thing it replaces:

- no `requirements=` passthrough on `deploy` (the draft's own §7 Q4 noted it would be needed,
  because an auto-saved bundle can never satisfy the rule below);
- one obvious place where a deployable bundle is constructed, and it is the place that already takes
  `code=` and `requirements=`;
- `deploy` keeps exactly one job. Auto-saving is a convenience for *running* something now
  (`_ensure_bundle`, gate 1); publishing something others will fetch by name is a deliberate act.

`deploy` then refuses a bundle whose manifest has no `requirements`, naming the fix
(`bundle.save(..., requirements=[...])`), and one with no `code` block, which `verify_image` already
treats as fatal on a node.

This closes H3, and it is the reason the notebook's separate `bundle.save` cell stops looking
redundant: `_ensure_bundle`'s auto-bundle is fine for gate 1, which runs in-process on the driver
and never reads `requirements`, and is *not* fine for something another machine will fetch by name.
D6 makes that distinction enforced rather than conventional.

### D7 — `_deploy.json` is the binding, and it is what a run reports

Written into the version directory beside `bundle.json`:

```json
{
  "name": "crop-rf", "version": 3,
  "digest": "sha256:…",
  "environment": "fsd-infer-sklearn:6",
  "verified": {"step": "verify_image", "pass": true, "metrics": {…}},
  "deployed_at": "2026-08-22T…Z",
  "fsd_version": "…"
}
```

**Does this re-couple bundle to image, which spec 44 phase 1 exists to break?** No, and the
distinction is the whole reason `_deploy.json` is a sibling record rather than a manifest field.
Phase 1 broke a *packaging* coupling: the image no longer has to be rebuilt per adapter, so
retraining costs a bundle publish rather than a `docker push`. `_deploy.json` records a *fact about
a test that was run* — "this image ran this bundle once, and here is the result". Retraining still
costs one publish; the new version simply carries its own verification. The coupling phase 1 killed
was build-time; this is bookkeeping.

Two consequences beyond the record itself:

- **A run says what it resolved.** `run_inference` prints `[model] crop-rf@champion -> v3
  (verified against fsd-infer-sklearn:6)`. This is spec 47 D5's rule — announce what was resolved,
  before the work — applied to the model. It is also the only thing that makes an alias auditable
  after the fact.
- **A mismatch is named.** Passing `environment=` that differs from the one the version was
  verified against **warns loudly** and continues (it is a legitimate thing to do deliberately —
  e.g. a rebuilt image — and refusing would make an image upgrade impossible without a re-deploy).
  §7 Q2 asks whether that should instead refuse.

**§9 step 3 deferral (user, 2026-08-24):** the mismatch warning above is **not implemented**.
`_deploy.json`'s `environment` field is overwritten on every re-deploy of identical content, so it
can only ever record the *last* image that ran a version — a model verified against a rebuilt
image would make the warning fire falsely for every other image that genuinely ran it. The
user's position: images and models are orthogonal (one image runs many models, one model runs on
many images), and the only thing that blocks a pairing is incompatibility, which `verify_image`
already tests. Designing a multi-binding `_deploy.json` schema for a problem nobody has hit yet is
premature; the decision is to ship the print line only, run the notebook, and decide from real
use. Tracked as issue #87.

### D8 — `deploy` does not build images — already settled, recorded here so it stays settled

This is **not a fresh deferral**. ADR 0002 called P6 *"the home where image-build later gets
automated"*, and spec 44 §0 records the full history: *"Where the coupling lands later: P6
`deploy()` **[LOCKED — user, 2026-07-23]** … is the appropriate home for building the image"* was
subsequently **reversed by the user on 2026-08-18**, on the grounds that image-building is
Azure-specific plumbing which *"fights the runner/storage seam and would make `deploy`
un-runnable on any other backend"*. The user's 2026-08-22 answer picked the same side a third time.

So: building stays `00_build_images.ipynb` plus an operator run-book step, and `deploy` never calls
`az ml`/`az acr`. What `deploy` does instead is **refuse to register an image it has not seen
work** (D5) — enforcement, not construction.

What would have to be true to automate it, so a later spec does not re-derive it: AML's SDK v2
already supports `Environment(build=BuildContext(path=…))` + `ml_client.environments.create_or_update()`,
which is exactly what the notebook does by hand; the missing pieces are deciding who owns the
Dockerfile per dependency family (spec 44's "generic per dependency family, never per model") and
what `deploy` should do when the build succeeds but verification then fails. Any such work belongs
behind the backend interface of D10, not in `fsd.api.deploy`.

### D9 — resolution is one small read, and never lists the registry

`"crop-rf@champion"` costs one `_aliases.json` read; `"crop-rf@v3"` costs none. Version *allocation*
(deploy only) is the sole operation that lists. This keeps the hot path — inference on N nodes, each
resolving a model — off any listing call, which is the same reasoning spec 50 applied to the cube
presence sweep after a per-cell walk turned into ~3600 sequential round-trips.

### D11 — the registry is RELOCATABLE: nothing inside it names where it lives [Q6: user, 2026-08-22]

The final home of the shared registry is not agreed yet, so the spec must not make choosing it
irreversible. It does not have to, provided one invariant holds:

> **No file the registry writes may contain an absolute path, a URL, or the registry root.**

Then relocation is a copy. `storage.transfer` the tree to the new prefix, hand callers a different
`registry=`, and every ref that worked before works after — because a ref is
`<name>:<version>` / `<name>@<alias>`, resolved *against* a root supplied at call time (D4), never
baked into an artifact.

What this constrains, concretely:

- `_deploy.json` (D7) records `name`, `version`, `digest`, `environment`, the verification result —
  all location-free. The verification's own `metrics` may carry paths from the machine that ran it;
  those are **evidence, not references**, and resolution must never read them.
- `_aliases.json` (D3) maps alias -> version **integer**. Never a path.
- `bundle.json` already stores **relative** artifact hrefs (spec 18 / F5), which is what makes the
  bundle itself relocatable and is why this invariant is cheap to keep.
- The **content digest (D2) is what makes a move verifiable**: re-computing it after a copy proves
  the tree arrived intact, so migration is checkable rather than hopeful.

`fsd.model.registry.migrate(src, dst)` is therefore a thin helper — copy, re-digest each version,
refuse on any mismatch — not a schema rewrite. It is a §9 step 0 deliverable, because a migration
tool written *after* the first non-relocatable file is added is a rewrite instead of a copy.

**Consequence for §7 Q6:** the notebook can point at `{AZ_ROOT}/models` now, and moving to whatever
central location is agreed later costs a copy plus one changed `registry=` argument. Choosing the
location is explicitly *not* a precondition for implementing this spec.

### D10 — the layout is the contract, so a second backend is additive

Resolution goes through one function (`fsd.model.registry.resolve`) and publication through one
(`publish`). The storage-seam layout is v1's only backend, but the *interface* is what callers see,
so an OCI/ORAS backend against `acr<proj>` — or an AML-registry backend — can be added later without
touching `run_inference`, `verify_adapter` or `deploy`'s signature.

This is not speculative generality: OCI registries are a vendor-neutral standard that ACR, GHCR, ECR
and Harbor all implement (§8), so that backend is the one with a genuine anti-lock-in argument, and
§6 records why it lost *for v1* rather than on the merits.

---

## 4. Acceptance criteria

1. `deploy` publishes a bundle to `<registry>/<name>/v1/` and returns a ref that
   `run_inference(model=ref)` accepts unchanged.
2. Deploying **identical content twice** returns the same version and writes no new directory
   (idempotent, D2) — asserted by comparing the version integer and a listing count.
3. Deploying **changed content** creates `v2`; `v1`'s bytes are untouched (D2).
4. A published version directory is never partially visible: publication goes through
   `storage.fs.rename` from a staging prefix (D2) — asserted by a test that fails the copy midway
   and checks no `v<N>` exists.
5. `deploy(..., alias="champion")` writes `_aliases.json`; re-deploying with the same alias
   repoints it without touching either version (D3).
6. `_ensure_bundle` resolves `"name@alias"` and `"name@vN"` when `registry=` is given; a `name@ref`
   **without** `registry=` raises `PreflightError` naming the missing argument (D4). Asserted
   **through the public verbs**, not only on the helper: `run_inference(model=ref, registry=…)` and
   `verify_adapter(model=ref, registry=…)` must get past `_model_spec`'s `bundle.json` read, which
   is what the amended D4 records as the failure a helper-only test cannot see.
7. `deploy` runs `verify_image` and **refuses** on `pass=False`, surfacing that result's own `error`
   (D5). No version directory is created on refusal.
8. `deploy(verified=<prior result>)` skips re-verification **only** when the result's bundle digest
   and environment both match; a mismatched or stale result is refused (D5).
9. `deploy` refuses a bundle whose manifest lacks `requirements`, naming
   `bundle.save(..., requirements=[…])` as the fix; likewise one lacking `code` (D6).
10. `_deploy.json` records name/version/digest/environment/verification, and `run_inference` prints
    the `[model] … -> v<N> (verified against <env>)` line before dispatching (D7).
11. Resolving an alias performs exactly one read and no listing (D9) — asserted with a counting
    fake over `fsd.storage.fs`.
12. Behaviour is identical for a local registry path and a URL registry (D1), and identical under
    `runner="local"` and `runner="aml"` for everything except the verification step, which is
    AML-only by `verify_image`'s own design.
13. **The registry is relocatable (D11)** — asserted two ways, because this is what makes §7 Q6's
    "decide the location later" safe:
    a. **No file the registry writes contains the registry root, an absolute path, or a URL** — a
       test scans every written file (`_aliases.json`, `_deploy.json`) for the root string.
    b. `migrate(src, dst)` copies a registry with several versions and aliases; every ref that
       resolved against `src` resolves identically against `dst`, and each version's re-computed
       digest matches (D2). A corrupted copy is refused, not silently accepted.
14. `deploy` **refuses a live adapter**, naming `fsd.model.bundle.save` (D6/Q4), and refuses
    `verify_adapter`'s auto-saved bundle for the same reason (Q5) — the latter asserted through the
    real `metrics["bundle_path"]`, not a hand-built folder.
15. `pytest -q` and `ruff check src/ tests/ demos/ examples/` clean; no network in unit tests
    (verification mocked at the AML-client boundary, as spec 38/48 already do).

---

## 5. Risks

- **An alias makes a run's meaning time-dependent.** `crop-rf@champion` in a notebook cell means
  something different after someone promotes v4. This is inherent to the pattern and is why D7
  records the resolved version and D3's print exists. Anyone needing bit-reproducibility pins
  `@v3`.
- **Version allocation races.** Two `deploy` calls against one name can pick the same integer. D2's
  atomic rename makes the loser fail rather than corrupt, and it retries — but the registry has no
  lock, and a pathological interleaving could still produce a confusing gap in the sequence. Worth
  a test; not worth a lock service.
- **The registry is not a security boundary.** It is a storage prefix and inherits the account's
  ACLs exactly. Anyone who can write the run root can publish a model. Acceptable for a
  single-project research platform, and it must be stated rather than assumed the moment a second
  team shares the storage.
- **Verification proves one node, once.** `verify_image`'s own docstring is careful about this: it
  says nothing about scale, quota or cold starts. `deploy` inherits that limit and must not imply a
  stronger guarantee than "this image ran this bundle, once".
- **Storage-backed immutability is a convention, not a mechanism.** Nothing at the blob level stops
  a `fs.rm` + rewrite of `v1`. A digest mismatch on load would catch it (§7 Q3 asks whether to check
  on every load or only on demand).

---

## 6. Alternatives considered

- **MLflow Model Registry — the one that would genuinely save work, and it is still open.**
  Spec 44 §6.3 called this out and asked for it to be settled separately (its §7 Q7, never
  answered). The case for it is real: D2/D3 are hand-rolled versioning and aliasing, MLflow does
  both properly and is an industry interface rather than an fsd invention, and **an Azure ML
  workspace is an MLflow server with no extra configuration** — on `rise` that is versioned
  registration essentially free, with no database to run. The case against is equally real and is
  spec 44's: self-hosting the registry **requires a database-backed store** (a file store does not
  support the registry), so the portable path costs Postgres. That is *"a lock-in gradient, not
  lock-in freedom"*. **Position taken here, unchanged from spec 44's recommendation:** the
  storage-seam store is the default because it is small and works everywhere identically; MLflow is
  a candidate **backend** behind D10, not a replacement for `deploy`'s definition. §7 Q7 puts it
  back on the table for this sign-off, since spec 44's was never given.
- **ACR via ORAS / OCI artifacts** — attractive on mechanics: `rise` already provisions
  `acr<proj>` with AcrPush granted, and OCI gives real content-addressed immutability rather than a
  convention (§8). **Rejected, and on stronger grounds than convenience** — spec 44 D7's: putting
  the bundle in the image registry *"pairs bundle with image, which is precisely the coupling phase
  1 exists to break; retraining would become a `docker push`."* Retraining must cost a bundle
  publish, not an image build. Secondarily it adds an `oras` dependency and a code path outside the
  storage seam. D10 still allows it as a backend, but the phase-1 argument means it should never
  become the default.
- **The AML model registry** — most native: versions, lineage and cross-workspace promotion in the
  studio UI, all solved (§8). **Rejected on the runner seam**, following spec 44 D7: a model ref
  resolvable only through an `MLClient` cannot be resolved by a Batch runner, a local run, or any
  future backend. It *"can be added later as a storage backend, not as `deploy`'s definition."*
- **Public model hosting (Hugging Face Hub or similar)** — raised by the user at sign-off,
  2026-08-22, and **not an alternative to D1 at all**: it answers a different question. D1's
  registry is *operational* — private, next to the data, read by every node of a fan-out, and
  carrying an image binding (`fsd-infer-sklearn:6`) that is meaningless outside this organisation.
  Public hosting is *distribution*: discovery, citation, and third-party reproduction. The two do
  not substitute for each other, and a bundle published publicly while advertising a private image
  ref would promise a binding nobody outside can act on.

  The good news is that fsd is already shaped for it, and **spec 44 phase 1 is what made it
  possible**: a bundle that carries its own adapter source is exactly what an outsider needs, where
  a bundle that imports a private module would be useless to them. So this is plausibly a small
  follow-on verb (`fsd.publish`, stripping `_deploy.json`'s image binding and emitting a model card
  from `bundle.json`'s spec) rather than a D10 backend. Deliberately **not specified here** — see
  §7's closing note for what would have to be settled first.
- **Lifecycle stages instead of aliases** — rejected on MLflow's own experience of deprecating them
  (§8, D3).
- **`deploy` builds the image too** — deferred to a later spec, D8; the coupling argument is in §8.

---

## 7. Questions at sign-off — ALL RESOLVED (user, 2026-08-22)

1. **[RESOLVED — default stands]** **Is `registry=` a parameter, or does it ride in
   `runner_kwargs`?** → an **explicit `registry=`** on `deploy`/`run_inference`/`verify_adapter`.
   Resolving a model is not a runner concern (a local run resolves models too), and `runner_kwargs`
   is already the parameter most likely to accumulate unrelated keys. Folded into **D4**.
2. **[RESOLVED — default stands, then deferred at implementation]** **On an environment mismatch at
   run time, warn or refuse?** → **warn, loudly, and continue.** Refusing would make "I rebuilt the
   image, I will re-verify later" impossible without a re-deploy, and D7's printed line makes the
   mismatch visible. The counter-argument is recorded rather than dismissed: spec 47 D1 chose to
   *refuse* on the analogous cached-cell-id drift, because there it would orphan outputs already
   written. Nothing is orphaned here. Folded into **D7**. **§9 step 3 (user, 2026-08-24): the warn
   half is deferred, not implemented** — `_deploy.json`'s single, last-writer-wins `environment`
   field cannot distinguish "this image never ran this model" from "a different image ran it after
   the record was written", so implementing the warning now would fire falsely. Ship the print
   half only; decide the warning from real notebook evidence. Tracked as issue #87.
3. **[RESOLVED — default stands]** **Is the content digest checked on every load, or only by
   `deploy`?** → **only by `deploy`** (and by `migrate`, D11). A load-time check re-reads every
   artifact byte on every node of a fan-out — the same cost argument spec 49 §7 Q2 used to reject
   per-cube content digests. A `verify=True` opt-in on `bundle.load` covers the paranoid case.
   Folded into **D2**.
4. **[RESOLVED — default OVERTURNED]** **Does `deploy` accept a live adapter, or only a saved
   bundle?** → **a saved bundle only.** The draft proposed accepting both. The user's answer is
   narrower and removes the tension the draft had already noticed: an auto-saved bundle carries no
   `requirements`, so accepting one would have forced a `requirements=` passthrough on `deploy` and
   split bundle construction across two places. Auto-saving stays what it is — a convenience for
   *running* something now — while publishing stays a deliberate act. Folded into **D6**.
5. **[RESOLVED — default stands]** **Should `verify_adapter`'s auto-bundle be publishable?** →
   **no.** Gate 1's bundle is a means to run gate 1; it reports its path
   (`metrics["bundle_path"]`, 2026-08-22) so it can be *inspected*, not promoted. D6's saved-bundle
   rule now refuses it structurally rather than by a special case, which is the better shape.
6. **[RESOLVED — reframed into a constraint]** **Where does the registry live?** → **not decided,
   and deliberately not a precondition.** Deployed models need a *centralised* home; that location
   is not agreed yet. Rather than block on it, the spec makes relocation cheap: **D11** requires
   that nothing the registry writes names where it lives, so moving is a copy plus a changed
   `registry=` argument, with the D2 digest making the move verifiable. The notebook uses
   `{AZ_ROOT}/models` in the meantime — sibling to the runs, since a model outlives the run that
   trained it. `migrate` ships in §9 step 0, not later.
7. **[RESOLVED — spec 44's Q7 finally answered]** **Should MLflow-via-the-AML-workspace be an
   alternative backend?** → **no, and not within this scope.** This closes the question spec 44
   §6.3 raised on 2026-07-23 and left open, which is part of why its phase 2 stalled. The analysis
   in §6 stands on the record — an AML workspace is an MLflow server for free, and self-hosting
   costs a Postgres-backed store — so a future spec can reopen it with the reasoning already done,
   but it is out of scope here and D10's backend interface is the only accommodation made for it.

### Raised at sign-off, not yet a decision

**Public model hosting (e.g. Hugging Face Hub).** Asked by the user, 2026-08-22. Not folded into a
decision because it answers a *different question* from this spec's: the registry in D1 is
**operational** (private, next to the data, read by nodes, carrying an image binding that is
meaningless outside this org), whereas public hosting is **distribution** — discovery, citation and
third-party reproduction. Recorded as §6's last entry and as a candidate follow-on verb
(`fsd.publish`), explicitly *not* as a D10 backend, since a publicly hosted bundle whose
`_deploy.json` names a private `fsd-infer-sklearn:6` would advertise a binding nobody outside can
act on. Worth its own spec if it becomes a goal.

## 8. Best-practice alignment / sources

Cross-validation run at draft (2026-08-22), under CLAUDE.md's standing permission for spec searches.
Searches run: ORAS/OCI artifact push to Azure Container Registry; Azure ML workspace vs cross-
workspace registries for model promotion; MLflow model registry stages vs aliases and their
deprecation; Azure ML SDK v2 `Environment` from a Dockerfile `BuildContext`; model-registry /
image-build coupling and digest pinning.

### External

- **[MLflow — Model Registry](https://mlflow.org/docs/latest/ml/model-registry/)** and
  **[Model Registry Workflows](https://mlflow.org/docs/latest/ml/model-registry/workflow/)**:
  supplied **D3 in full**, and §6's rejection of stages. These establish that lifecycle **Stages are
  deprecated in favour of aliases** — mutable named references such as `@champion`, set via
  `set_registered_model_alias()` — and give the reason fsd inherits without re-deriving: aliases are
  *pointers rather than one-of-N states*, so several can coexist on a version and promotion is a
  reassignment, not a state transition. They also supplied D3's ergonomic argument, that deployment
  code pointing at an alias *"never needs to change version numbers"*.
- **[Azure Container Registry — Manage OCI artifacts with ORAS](https://learn.microsoft.com/en-us/azure/container-registry/container-registry-manage-artifact)**:
  supplied **§6's ORAS alternative and D10's claim that a second backend is standard-shaped**. It
  establishes that ACR stores and manages *arbitrary* OCI artifacts alongside container images — not
  only images — and that `oras login` authenticates with a Microsoft Entra identity, which is what
  makes it viable against `rise`'s existing `acr<proj>` and its already-granted AcrPush. This is the
  runner-up design, recorded so the deferral is on cost rather than ignorance.
- **[Azure Machine Learning — registries for MLOps](https://learn.microsoft.com/en-us/azure/machine-learning/concept-machine-learning-registries-mlops)**
  and **[Share models across workspaces with registries](https://learn.microsoft.com/en-us/azure/machine-learning/how-to-share-models-pipelines-across-workspaces-with-registries)**:
  supplied **§6's AML-registry alternative and the precise reason it is rejected**. They establish
  that an AML registry *"decouples assets from workspaces"* and is the supported path for promoting
  a model from dev to test to prod with end-to-end lineage — a real benefit fsd is choosing to
  forgo — and, critically for the rejection, that resolution is an Azure ML concept reached through
  a workspace/registry client, which a non-AML runner has no way to honour.
- **[Azure ML — manage environments with CLI & SDK v2](https://learn.microsoft.com/en-us/azure/machine-learning/how-to-manage-environments-v2)**:
  supplied **D8's description of what automating the image build would take** — `Environment(build=BuildContext(path=…))`
  plus `ml_client.environments.create_or_update()`, with AML building from a `Dockerfile` at the
  build-context root. That this is a handful of lines is precisely why D8 defers it on *coupling*
  grounds rather than difficulty.
- **[Red Hat — reproducible container builds](https://docs.redhat.com/en/documentation/red_hat_enterprise_linux/10/html/building_running_and_managing_containers/introduction-to-reproducible-container-builds)**:
  supplied **D2's digest-alongside-integer decision**. It establishes that image *tags are mutable
  references that can be overwritten* and that reproducible deployment requires pinning by immutable
  digest — the same hazard `AZ_INFER_ENV_VERSION = "6"` embodies, and the reason a human-readable
  version integer is not sufficient on its own. It also supplied **D8/§6's coupling argument**, that
  separate lifecycles (model publication vs image build) should not be fused.

### Internal

- **`specs/44-bundle-carried-adapter-code.md` — the spec this one completes.** Its **D7** supplied
  D1's store (blob via the storage seam), D2's immutability, D3's single mutable pointer that D3
  generalises into aliases, and the ACR + AML-registry rejections in §6 — including the ACR
  argument this spec adopts over its own weaker one (*"pairs bundle with image, which is precisely
  the coupling phase 1 exists to break"*). Its **D8** supplied §1's **measured 627 s per run** of
  redundant bundle upload, which is the quantified payoff. Its **§0** supplied D8's LOCKED→REVERSED
  history on image building. Its **§6.3** supplied §6's MLflow entry in full, including the
  database-backed-store catch and the phrase *"a lock-in gradient, not lock-in freedom"*. Its **§7
  Q5 and Q7** are what this spec exists to answer.
- `docs/adr/0002-bundle-and-inference-image-decoupled.md`: supplied **D8** verbatim — *"P6
  `deploy()` is the home where image-build later gets automated … the bundle format does not
  change"* — and the bundle/image split this spec binds together rather than merges.
- `docs/adr/0018-training-stays-user-side-modeladapter-contract.md`: supplied §2's out-of-scope line
  and the framing of `deploy` as *"the P6 contract-pinning stub"*.
- `ROADMAP.md` §3.4 + §7: supplied §1's framing and the open question D1 answers.
- `src/fsd/api.py::deploy` (the stub) and `::_ensure_bundle`: supplied D4's chokepoint and **H3** —
  `_ensure_bundle` passes no `requirements=`, which is exactly what D6 refuses to register.
- `src/fsd/model/verify_image.py`: supplied **D5**. Its `_result.json` shape is what `verified=`
  consumes, and its `runner="local"` refusal is the precedent for D5 refusing rather than
  soft-passing.
- `src/fsd/storage/fs.py::rename`: supplied **D2's atomic publish** — already documented there as
  one metadata operation on an HNS account and `os.rename` locally.
- `specs/47-driver-side-honesty.md` D5: supplied **D7's printed `[model]` line**.
  Its **D1** supplied §7 Q2's counter-argument (fsd already chose to *refuse* on cached-id drift).
- `specs/49-skip-work-already-done.md` §7 Q2 and `specs/50-backward-walk.md` D9: supplied §7 Q3's
  cost argument against digesting content on every load, and D9's "never list on the hot path".
- `notebooks/e2e_austria_aml.ipynb` config cell: supplied **§1's evidence** — the pasted
  `AZ_INFER_ENV_VERSION` with its own comment that it goes stale on every rebuild.

## 9. Implementation note

Per CLAUDE.md's model split, implementation is a **Sonnet session at `/effort medium`** once signed
off. Phased so each step is independently revertible and useful:

0. **`fsd.model.registry`** — layout, `publish`, `resolve`, `migrate`, `_aliases.json`, the digest.
   Pure local-filesystem unit tests, no verbs touched. This is most of D1/D2/D3/D9/D11.
   **`migrate` ships here, not later:** the moment one non-relocatable file exists, migration stops
   being a copy and becomes a rewrite (D11).
1. **`_ensure_bundle` resolution (D4)** — one function, one new branch, plus the `PreflightError`.
   Makes refs usable before anything produces them.
2. **`deploy` (D5/D6/D7)** — the enforcement and the record. Depends on 0 and on `verify_image`,
   which already exists; verification mocked at the AML-client boundary in tests.
3. **The `[model]` line + mismatch warning (D7)** — small, and it is what makes an alias auditable.

Steps 0 and 1 are safe to land before the §7 questions are all resolved; step 2 is where Q2/Q4
bite, so it should follow sign-off.
