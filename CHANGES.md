# CHANGES vs legacy

Living record of how `fsd` differs from the legacy repos for behavior that **is**
carried over (renames, restructures, behavioral tweaks). Pure removals go in
`DROPPED.md`.

## Image builds become `fsd.image`/`fsd.aml`, with a registry (spec 56, 2026-08-27)

The AML image recipe stops being 110 lines of notebook helpers keyed on the git state of an fsd
checkout, and becomes a declarative `fsd.image.ImageDefinition` whose **resolved** form is
digested, looked up in a storage-seam registry mirroring `fsd.model.registry`, and built only if
absent. Closes #79.

- **`fsd.image.ImageDefinition`** (frozen dataclass) replaces the checked-in
  `notebooks/images/{base,sklearn}/Dockerfile`. `render_dockerfile()`/`write_context()` generate
  what those files held; `.derive()` makes the inference image from the general-purpose one
  without repeating `base`/`fsd`/`extras`. The `build_context=` escape hatch takes a caller-owned
  directory unchanged, for an image fsd's fields cannot express.
- **The staleness key changes from git state to the resolved definition's digest**
  (`fsd.image.digest.resolve`/`digest`). `git_state()` and `.last_registered.json` are gone
  (see `DROPPED.md`): the resolved `fsd` reference — a 40-char git sha, or a wheel content
  digest for `fsd="path:..."` — travels with the definition instead of living in one working
  copy. `-dirty` does not disappear for the checkout case, it changes meaning: an uncommitted
  edit changes the wheel's content digest rather than triggering a separate "dirty" flag.
- **`fsd.image.registry`** (built on the new `fsd.registry._core`, shared mechanism with
  `fsd.model.registry` — see that module for why it is a parameterized copy, not an import) is a
  registry of *definitions*, keyed by digest — not AML's own `name:version` asset versioning,
  which fsd still leaves entirely to AML.
- **`fsd.aml.ensure_environment`** is check-then-build (D4): resolve, look up by digest, confirm
  the AML asset still exists, build only on a miss, publish. It never waits for the build — an AML
  v2 image build is an ACR task run, not an AML job — so it returns the version and the Studio URL
  immediately, same as the notebook always had to do manually.
- **`verify_image` gains `image_ref=`/`registry=`** (D8) alongside `build_context=`: the same
  wheel-staleness gate (spec 47), driven by the image registry's resolved `fsd` reference instead
  of a wheel sitting in a folder on disk. `build_context` is unchanged and wins if both are given.
- **A published definition carries a mutable `_aml.json` beside its immutable `image.json`**
  (Opus review, 2026-08-27, amending D3's layout). `publish` is idempotent by digest, so
  rebuilding an *unchanged* definition — D4 step 3's deleted asset, or `force=True` — can never
  allocate a new version to record the new AML version in. Without the sidecar the registry keeps
  naming the asset that was just replaced, `ensure_environment` finds it missing on every later
  call, and rebuilds a 10–20 minute image forever. `_aml.json` is staged-and-renamed and sits
  outside `image.json`, so it never touches the bytes the content digest covers — exactly the role
  `_deploy.json` plays in `fsd.model.registry` (spec 51 D7). `registry.resolve(...).aml` prefers it
  and falls back to `image.json`'s frozen `aml` block.
- **`ensure_environment` reports two version numbers, and they are not interchangeable** (Opus
  review, 2026-08-27). AML versions *assets*; the image registry versions *definitions*, in its
  own integer sequence — `fsd-aml-env:5` in AML is routinely `fsd-aml-env:1` in the registry.
  `EnsureResult.version`/`.ref` are AML's (what `environment=` and `runner_kwargs` want);
  `.registry_version`/`.registry_ref` are the registry's (the only thing
  `verify_image(image_ref=..., registry=...)` can resolve). Passing one where the other belongs
  fails as a missing `v<N>` directory rather than as a type error.
- **`00_build_images.ipynb` collapses to two declarations and two calls** (D7). The old
  wheel-build, git-state and helper cells are gone; Part C's "paste these versions into the e2e
  notebook" step is gone too — the e2e notebook now calls `ensure_environment` itself and gets the
  same answer by asking the same registry.

## `root` leaves the config; the registries enter it (spec 55, 2026-08-27)

Amends spec 54's schema, one day old, in both directions. Spec 54's location rule, explicitness
rule and precedence rule are unchanged.

- **`root` is no longer a config key.** `fsd.config.load()` returns no `root`, `fsd init` does not
  prompt for one, and `load(root=…)` raises `TypeError`. The test that decides what belongs in the
  file: a **durable address** (stable for this user across runs and mostly across projects) belongs
  in it; a **per-run destination** does not. `root` is chosen per run by whoever runs the job, so
  the caller passes it — which is spec 41 D7's *"takes a storage location as an argument"* applied
  to the last value that escaped it.
- **`model_registry` and `image_registry` are new, and OPTIONAL.** With `AZ_MODEL_REGISTRY` /
  `AZ_IMAGE_REGISTRY` as their env spellings. An unset required key still raises `MissingConfig`
  naming every gap; an unset optional key is simply `None`. Registries are named rather than chosen
  per run, and both models and images outlive the runs that made them.
  **fsd's own signatures still take `registry=` as an argument, always** — the keys exist so an
  operator has somewhere to keep the value, notably the two tracked notebooks, which are
  leak-guarded and may not hold a literal `abfss://` URL.
- **`fsd init --blank`** writes `config.toml` with every key present and empty and prompts for
  nothing — `env.example.sh`'s one genuine affordance, at a location a `pip install` consumer can
  reach. It refuses to overwrite a file that already holds values unless `--force`. Keys are
  present-and-empty rather than commented out so the file parses and `load()` names the gaps
  instead of `tomllib` reporting a syntax error.
- **A non-tty `fsd init` explains itself** instead of raising `EOFError` out of `input()`: it exits
  non-zero naming `--blank`, `--set` and `--from-env-file`.
- **`AZ_ROOT` still works, and fsd still never reads it.** `e2e_austria_aml.ipynb` reads it from
  the environment in a visible cell. Note the reason is the notebook leak guard and *only* that:
  run-book compatibility is explicitly not a design input (user, 2026-08-27 — run-books are
  point-in-time documents and are not kept runnable). The wider `AZ_ROOT` tidy-up is
  [#92](https://github.com/nikhilsrajan/fsd/issues/92).

## Config bootstrap moves to a user-level file + `fsd init` (spec 54, 2026-08-26)

- **The operator config bootstrap moves out of the checkout.** `env.example.sh` (repo root) +
  `notebooks/_config.py` (checkout-path discovery, `env.local.sh` parsing) are replaced by
  `~/.config/fsd/config.toml` (or `$FSD_CONFIG_DIR` / `$XDG_CONFIG_HOME/fsd`; `%APPDATA%\fsd` on
  Windows), written by the new `fsd init` console script and read by `fsd.config.load()`. Fixes
  [#78](https://github.com/nikhilsrajan/fsd/issues/78): both halves of the old bootstrap were only
  reachable from an fsd checkout, so a `pip install`ed consumer (phase 2's `rise/`) could not use
  either.
- **`fsd.config.load()` is still explicit, never called by the library.** `fsd.download` /
  `create_training_data` / `run_inference` gain no config awareness — this is the part of spec 41
  D7 that survives unchanged: the library takes every storage location as an argument. What moved
  is only the bootstrap: the template's location and the loader's home.
- **Precedence: explicit kwarg > bare `AZ_*` env var > `config.toml`.** The `AZ_*` names
  (`AZ_SUBSCRIPTION_ID`, `AZ_RG`, `AZ_ML_WORKSPACE`, `AZ_CLUSTER`, `AZ_UAMI_CLIENT_ID`, `AZ_ROOT`)
  are unchanged and still work — `source env.local.sh` in a shell still overrides the file, so no
  existing run-book needs editing. `load()` reads `os.environ` (that is the precedence rule) but
  never assigns to it, and neither does `fsd init`.
- **New:** `fsd`'s first console script (`[project.scripts]`, `fsd = "fsd.cli:main"`). `fsd init`
  (interactive, `--from-env-file PATH`, or `--set key=value`) writes the file; `fsd config` prints
  the resolved value of each key and which of the three sources it came from.
- **Schema:** one TOML table, `[azure]`, six lowercase string keys (`subscription_id`,
  `resource_group`, `workspace`, `cluster`, `uami_client_id`, `root`) — read with stdlib
  `tomllib`, written by a small hand-rolled emitter (`tomllib` cannot write; taking `tomli-w` as a
  dependency for six flat strings was rejected, see specs/54 D2).
- **Both tracked notebooks** (`e2e_austria_aml.ipynb`, `00_build_images.ipynb`) now call
  `fsd.config.load()` and use the lowercase attribute names (`cfg.root` etc, not `cfg.AZ_ROOT`);
  their checkout-path resolution is now a two-line `pathlib.Path.cwd()` cell (they are developer
  artifacts that genuinely live in the checkout) rather than `_config.find_repo()`'s upward marker
  search.

## The local run path stages a non-local resolved bundle before loading it (spec 53, 2026-08-25)

- **`run_inference` now fetches a non-local resolved bundle to `<output_folderpath>/_model` before
  any local shape (`cores=1`, the `cores>1` Snakemake fan-out, local ROI mode) loads it.** Fixes
  [issue #89](https://github.com/nikhilsrajan/fsd/issues/89): `bundle.load` puts a bundle's
  `code/` on `sys.path` (`_activate_bundle_code`), and CPython's import machinery has no path hook
  for a URL, so a blob-resolved ref (spec 52 made these possible) was inert there — a
  `ModuleNotFoundError` that had nothing to do with the adapter itself. The AML path already staged
  (`runners._stage_bundle`) so it was never affected; only the local path was missing it.
- **New:** `api._stage_local_bundle`, a thin wrapper around the existing
  `infer_shard.fetch_bundle_to_scratch` (manifest-driven, no directory listing — spec 38 D3). It is
  a no-op for a path already local (a local registry costs nothing extra) and for anything that
  isn't a path at all (a live adapter, handled by `_ensure_bundle`'s own auto-save).
- **Placement is after each path's own preflight, not literally next to `_resolve_model_ref`** —
  `_model_spec` still reads a non-local bundle's `bundle.json` directly via `fs.open`, so a call
  rejected in preflight still costs no transfer. Staging happens once per `run_inference` call,
  before `_ensure_bundle` gets a chance to resolve again, so that second (idempotent) call just
  passes the now-local path through — the `cores>1` fan-out gets the staged path for free.
- **Gated on `runner == "local"` for ROI mode** (an amendment made after the spec's sign-off,
  before implementation): `runner="aml"` never loads the bundle on the driver — it stages its own
  copy to blob and each node fetches from there — so staging on the driver too would be a wasted
  blob→local→blob round trip and a behavior change to a path spec 53 promised not to touch. The
  pre-built-cubes path has no AML shape at all, so it stages unconditionally there.
- **The driver-side fetch announces itself** — `[stage] bundle <- <url> | N files, X MB`, printed
  before the transfer starts (Opus review, 2026-08-25). Spec 53 D2's rationale assumed spec 47 D5
  already covered this; it did not — D5 instrumented the **upload** leg (`runners._stage_bundle`),
  and `infer_shard.fetch_bundle_to_scratch` prints nothing. On an AML node that silence was
  invisible; on the driver it sat between `[model] <ref> -> vN` and the first `[inference]` line
  for the whole download (spec 47 measured 13 MB at 627 s over VPN on the mirror-image leg). The
  node-side leg is still silent — unchanged here so the AML path stays byte-identical.

## The registry publishes in place, no directory rename (spec 52, 2026-08-24)

- **`registry._write_new_version` no longer stages then renames.** It writes a version's files
  straight into `v<N>/`, re-digests what landed against the caller's digest, and writes
  `v<N>/_complete.json` last — a single-object write is atomic on every backend fsd targets, so
  that marker is the all-or-nothing moment the directory rename used to provide. This fixes
  [issue #88](https://github.com/nikhilsrajan/fsd/issues/88): `storage.fs.rename`'s directory move
  falls back to fsspec's copy-then-`rm` on any non-local backend, which is not atomic, so the old
  retry loop misread that deterministic failure as "lost a race" and looped forever. No file in
  `storage/fs.py` changed — `registry.py:394` was the only directory rename in the codebase.
- **`_list_versions` is now marker-aware**, with a legacy carve-out: a `v<N>` directory with
  `bundle.json` but no marker still counts as complete, so a version published before this spec
  (the old stage-then-rename protocol never left a partial `vN`) keeps resolving and keeps
  migrating. `migrate` now writes `_complete.json` too, so migrated content no longer depends on
  that carve-out to stay visible.
- **A spec amendment landed mid-implementation, not silently coded around:** the legacy rule as
  first written (D5) contradicted the "an interrupted publish is invisible" guarantee (AC2)
  whenever `bundle.json` had already landed — which is most interruptions, since `bundle.json`
  sorts alphabetically early among a bundle's files. `_write_new_version` now writes `bundle.json`
  **last**, so an interruption during the write leaves no manifest at all; the one-object-write
  residual window is deliberately resolved in favor of the legacy reading (destroying a real
  published version is worse than stranding an unmarked folder, a cost spec 52 §5 already
  accepts). See `specs/52-registry-on-blob.md` §3 D5's amendment block for the full reasoning.
- **`deploy`, `run_inference`, `verify_adapter`, `verify_image` each call `configure_storage`
  now** — *intended* to fix [issue #86](https://github.com/nikhilsrajan/fsd/issues/86)
  (**UNPROVEN — #86 stays open, see the correction at the end of this entry**): a blob registry was
  read/written anonymously, because authentication worked only when some *earlier* verb in the
  same process happened to set a process-global fsspec flag as a side effect. `deploy` also drops
  its `storage_allowed=False` gate (a blob registry can now actually work); `verify_image` gained
  a `storage=` kwarg it never had.

**Opus review, 2026-08-24 — two behavior fixes on top of the above** (full account:
`specs/52-registry-on-blob.md` §10):

- **A bad `storage=` backend is a `PreflightError` again, not a bare `ValueError`.** D4's
  `configure_storage` call had to sit *before* `run_inference`/`verify_adapter`'s
  `_raise_preflight` (both touch storage earlier than the raise point) — but `configure_storage`
  itself raises on an unsupported backend, so `storage="s3"` escaped as a `ValueError` and took
  every other accumulated preflight error with it. The seam check now raises on its own first, as
  `deploy` already did. Second half of the same fix: a call the seam *rejects* no longer switches
  the process to authenticated adlfs on its way to being rejected — that global side effect is the
  accident D4 exists to remove. `verify_adapter`'s date errors are no longer reported alongside
  seam errors; a seam misconfiguration now raises by itself.
- **Reusing an interrupted version clears it first.** AC2 has the next `publish` write into an
  unmarked `v<N>` in place, and the re-digest cannot police what it inherits — `content_digest`
  covers only *manifest-declared* files, so an artifact or a `code/*.py` the new bundle does not
  declare survived into the version and was then marked complete. `bundle.load` puts a version's
  `code/` on `sys.path`, so a stale module there is importable by the adapter that lands next.
  `_write_new_version` now `_discard`s an existing incomplete target before writing (best-effort,
  like every other `_discard`). The old stage-then-rename never had this problem — each attempt
  got a fresh staging prefix.
- **Five tests added for branches mutation testing showed were unpinned** — the
  idempotent-collision return, the collision-with-different-content advance, the landed-digest
  guard, D5's legacy carve-out (**which had no test at all**), and the leftovers fix above. Each
  was verified to fail against a mutation of the line it covers. The two "race" tests rewritten
  during implementation cannot reach `_write_new_version`'s collision branch — their competitor
  publishes before `_list_versions` runs, so allocation starts past it — so the new pair simulates
  the stale listing that *is* the race.

**Correction, 2026-08-25 — #86 is NOT fixed by this work.** The run-book was executed against a
real `abfss://` registry (results in `runbooks/52-registry-on-blob.md`). The publish protocol
passed and **#88 is closed**, but the `configure_storage` half was never exercised, and cannot be:

- `run_inference` accepts `storage="azure"` only when `roi is not None and runner == "aml"`. On
  the pre-built-cubes path the seam gate refuses it, so D4's call is unreachable there —
  **[#90](https://github.com/nikhilsrajan/fsd/issues/90)**. Step 4 is the run-book's only step
  that goes through a verb at all (1/2/3/5 call `registry.*` directly), so nothing in the run
  touched `configure_storage`.
- The premise may also be weaker than assumed: adlfs's `anon` default is `None`, not `True`, and
  its anonymous branch is a *fallback* reached only when credential discovery fails. Steps 1-3
  read and wrote a real storage account with **no** `configure_storage` call anywhere — the
  `az login` chain was found on its own. "A blob registry would be read anonymously" is not what
  happens under a normal developer login.
- The same run found that a blob-resolved ref cannot be loaded on the local run path at all
  (`sys.path` cannot hold an `abfss://` entry) — **[#89](https://github.com/nikhilsrajan/fsd/issues/89)**.

Both are addressed in `specs/53-blob-registry-on-the-local-run-path.md` (DRAFT). The merge commit
`f2fe6bf` and `82eda21`'s message both say #86 is closed; they are wrong and cannot be edited
after the fact — this note is the correction of record.

## A resolved model ref announces itself before dispatch (spec 51 step 3, 2026-08-24)

- **`_resolve_model_ref` prints `[model] <ref> -> v<N> (verified against <env>)`** the moment a
  registry ref actually resolves — once per `run_inference`/`verify_adapter` call, even though
  both can reach `_resolve_model_ref` twice (`run_inference` itself, then `_ensure_bundle`): the
  second call sees an already-resolved path, which is not ref-shaped, and returns early before
  the print. Nothing is printed for a plain bundle path or a live adapter, since nothing was
  resolved. `registry.read_deploy_record` (new, public) reads `_deploy.json`'s `environment`
  for the parenthetical; a missing, empty, or malformed `_deploy.json` degrades to the shorter
  `[model] <ref> -> v<N>` line rather than failing the run.
- **Deferred, deliberately: the environment-mismatch warning (D7's other half, §7 Q2).**
  `_deploy.json`'s `environment` field is last-writer-wins, so it can only ever name the most
  recently verified image — implementing the warning today would fire falsely for every other
  image that has genuinely run a version. Shipping the print line only, deciding the warning
  from real notebook evidence. Tracked as
  [issue #87](https://github.com/nikhilsrajan/fsd/issues/87).
- **Found, not fixed here:** `registry._write_new_version`'s retry loop hangs forever when
  `storage.fs.rename` can't atomically move a staged directory on a non-local fsspec backend
  (confirmed for `memory://`, likely `abfss://`/`s3://` too) — `MemoryFileSystem.mv`'s
  copy-then-`rm` leaves the source non-empty, `fs.rename` raises `OSError`, and
  `_write_new_version` treats every `OSError` as "lost a race" and retries at `v<N+1>` forever,
  since the real cause recurs identically on every attempt. Surfaced while writing an AC12 test
  (a `memory://` registry through `deploy`/`resolve`/`run_inference`); that test is not included
  because it would run forever; it is present as a **skipped** test
  (`test_publish_resolve_round_trip_against_a_url_registry`) so `pytest -q`'s skip line keeps
  naming the gap. Tracked as [issue #88](https://github.com/nikhilsrajan/fsd/issues/88).

**Opus review, 2026-08-24 — three fixes on top of the above:**

- **`read_deploy_record` no longer raises on a byte-corrupt record.** It caught
  `(json.JSONDecodeError, OSError)`, which misses `UnicodeDecodeError` — a truncated or
  byte-corrupted `_deploy.json` decodes as neither JSON nor UTF-8, so it escaped and killed a
  run whose model had already resolved, breaking the function's own never-raise contract. The
  catch is now `(ValueError, OSError)`; `ValueError` is `UnicodeDecodeError`'s and
  `JSONDecodeError`'s common base.
- **The once-per-call test was vacuous.** It drove `run_inference` with an *empty*
  `inference_datacubes` folder, which dies at `_raise_preflight` **before** `_ensure_bundle` is
  ever reached — so it asserted "printed once" while only one of the two call sites had run, and
  could never have caught a double print. It now supplies a real datacube with `cores=2` (stubbed
  runner + finalizer), and asserts that the second call site genuinely executed and received an
  already-resolved path. Mutation-checked: re-introducing a print in `_ensure_bundle` fails it.
- **`registry.__all__` gained `read_deploy_record`** — the module lists every public name and the
  new one was missing.

## `verify_image` records WHAT it verified, not just where (spec 51 step 2 review, 2026-08-22)

- **`verify_image`'s `_result.json` gains `metrics["bundle_digest"]`** — the D2 content digest
  of the bundle it verified, computed at verification time. Additive: every other field is
  unchanged, and nothing that only reads `pass`/`error`/`smoke_*` is affected.
- **`fsd.deploy(verified=...)` matches on that recorded digest**, where it previously
  re-digested the result's own `metrics["bundle_path"]` at deploy time.
  **Why it mattered:** `bundle.save` overwrites in place (spec 51 §1 H1), so the normal
  verify → retrain → re-save → deploy loop hands `deploy` a `_result.json` naming the *right
  path* holding the *wrong content*. Re-digesting the path then compared the new content with
  itself — a tautology that always passed — and `_deploy.json` recorded "this image ran this
  bundle" for content the image had never seen, which is the one guarantee D5 exists to make.
  Found in review of `72b56ce`, reproduced, pinned by
  `tests/test_deploy.py::test_deploy_refuses_a_verified_result_whose_bundle_was_overwritten_in_place`.
  Side benefit: a `_result.json` is now portable — a colleague's result is honourable on a
  machine where their `bundle_path` does not exist.
- **A `verified=` result carrying no `bundle_digest` is refused**, not accepted: it cannot say
  what it verified. Any `_result.json` produced before this change must be re-run.
- **`deploy`'s refusal now reads `metrics["smoke_error"]` when the top-level `error` is `None`.**
  `verify_image` populates `error` only for a *driver*-detected failure; a smoke job that ran and
  reported a failure leaves it `None`, so the refusal used to read literally "verify_image error:
  None" — D5's "the verification's own error" with the actual diagnosis dropped.
- **`registry.publish` (and so `deploy`) refuses a model name carrying `/`, `\`, `:`, `@`, a
  leading `.`, or nothing at all** (`registry.check_name`). Such a name published fine and
  returned a ref nothing could resolve — `crop/rf:1` reads as a *path* to `api._is_ref_shaped`,
  `crop:rf:1` re-splits at the wrong separator — breaking AC1's "a ref `run_inference` accepts
  unchanged". `deploy` checks it up front, so a bad name costs no AML verification node.

## `storage.fs.rename` is a real `os.rename` locally (spec 51 step 0 review, 2026-08-22)

- **`fs.rename` no longer inherits `shutil.move`'s directory semantics.** fsspec's
  `LocalFileSystem.mv` is `shutil.move`, which moves the source *inside* the destination when
  that already exists as a directory, and reports success. `fs.rename`'s own docstring had
  always claimed "locally it is `os.rename`" — it now is one, falling back to fsspec's
  copy-and-delete only on `EXDEV` (a cross-device move, which has no atomic form anyway).
  **Behavior change:** renaming a directory onto an existing non-empty directory now raises
  `OSError` instead of silently nesting. Renaming a *file* onto an existing file still replaces
  it atomically, so the datacube sidecar write (`datacube/builder.py`) is unaffected.
- **Why it mattered:** spec 51 D2 makes `fs.rename` the atomic-publish primitive, so a
  `publish` that lost a version race did not fail-and-retry as §5 promises — it nested its
  staged bundle inside the winner's version directory and **returned that version number**.
  A caller resolving `crop-rf:1` would then have run a model it never published. Found in
  review of `c0290fb`, reproduced, and pinned by
  `tests/test_storage.py::test_rename_refuses_to_nest_a_directory_into_an_existing_one`.

## `create_training_data` resolves backwards from the target (spec 50, 2026-08-21)

- **A re-run stops paying for `setup` before it can even be skipped.** Spec 49 taught each leg to
  skip finished work, but every leg still ran its own preflight first — `run_create_datacube`
  defaulted to `overwrite_setup_csv=True`, which deleted `input.csv` and re-ran `setup` (reading the
  catalog, filtering 900 shapes, writing 1800 control files) on every call, even when every cube
  already existed (measured: 96 s on the Austria e2e). `create_training_data` now resolves the walk
  **backwards**: it checks whether the requested arrays are already current *before* touching the
  catalog or the build leg at all. A fully-resumed call performs zero catalog reads, zero `setup`
  calls, zero dispatch — it lands the arrays and returns.
- **The flatten identity is now computed from the REQUEST, not from `input.csv`.** `input.csv` is
  `setup`'s own output, so the old skip could only be evaluated *after* paying for the work it was
  meant to skip. `api._flatten_identity_from_request` computes the same identity `_flatten_identity`
  does — off the caller's label polygons, window, and params — with zero file reads. A cube's export
  path is fully derivable from `(run_folderpath, window, id)` alone; naming a cube never requires
  building one.
- **`run_folderpath` is no longer clock-based (#83).** It used to default to a fresh UTC timestamp
  for `runner="aml"`, so every artifact path was missing on every call and no skip — spec 49's or
  spec 50's — could ever fire. The default is now the plain stable name `runs/train` (never a hash
  of the request or the shape-id set: addressing stays per-path, so one new polygon touches only its
  own cube, not the whole run). The window path segment also gained a short digest of `(bands,
  mosaic_scheme, scl_mask_classes)`, so two requests differing only in `bands` resolve to different
  cube paths instead of silently colliding.
- **On a partial re-run, `setup` now runs only for the missing shapes** — 900 shapes with 40
  missing costs `setup` 40 shapes and 80 control-file writes, not 1800. A cell with no in-window
  imagery is recorded once (a sibling `_manifest.json` in the run folder) and reported as
  known-empty on later runs, rather than being retried forever. This new scoped path is used
  whenever the caller does not explicitly force a cube rebuild; `overwrite="datacubes"`/`True` still
  fall back to the original delete-and-regenerate `setup` pass, since a forced rebuild should also
  refresh a possibly-stale per-shape catalog slice.
- **Not done:** `overwrite_setup_csv` still exists and multi-window accumulation
  (`input.csv` growing across different start/end dates for the same run folder) is not enabled —
  that is spec 50 D9, deliberately deferred until #84 (the array layer's window-collision bug) is
  fixed first.
- **Migration note:** the window path segment gaining a `_<params_key>` suffix (above) means cubes
  already on disk under the OLD path shape (e.g. `20180101_20190101_m20/`, no params suffix) are no
  longer addressed by the new one and will rebuild from scratch on first use. Correct, but a
  one-time cost worth knowing about before re-running an existing root.
- **Preflight error batching changed.** `download=True` validation (`source`, `max_tiles`, `creds`)
  moved into wave 2 of preflight, so it now fires *after* the `[plan]` line is printed and
  `run_folderpath`/`export_folderpath` are created, and no longer batches together with the
  structural (wave-1) errors. Cosmetic (both waves still raise before any build/flatten work), but
  intentional-looking enough to call out here.
- **Opus review, 2026-08-21 — 5 bugs fixed before push** (`/tmp/review-fsd-spec-50.md`):
  - **A cube with no `input.csv` row was counted "present" and its row was never rebuilt.**
    `build_shortfall_only` treated a cube that exists on disk but has no current-window row as
    fully satisfied, but everything downstream (`_build_shortfall`, `run_local`/`run_aml`,
    `flatten`) reads rows, not cubes, and nothing else ever calls `setup` for that id. Reachable by
    deleting `input.csv` for a "clean rebuild" (crashes `_build_shortfall` with `FileNotFoundError`
    on the next call), and — worse, silently — once the aml run folder became shared
    (`runs/train`, above): switching between two windows' requests against the same root purged the
    first window's rows and never restored them, so a resumed call for that window built an
    `input.csv` with 0 rows and `flatten_training_data` got handed an empty CSV with no error.
    Fixed: a rowless-but-built cube is now routed back through `setup` (idempotent) so its row
    comes back, instead of being treated as done.
  - **A shortfall whose shapes ALL lack imagery raised `ValueError` and crashed the whole
    `create_training_data` call.** The old whole-shapefile `setup` call could absorb one
    out-of-coverage polygon among hundreds; `build_shortfall_only` can hand `setup` a shortfall
    that is *entirely* out-of-coverage (e.g. one new polygon added to an otherwise-complete run),
    and `setup`'s own `ValueError` propagated uncaught, before D5's known-empty manifest was ever
    written — so the request could never converge. Fixed: `build_shortfall_only` now catches that
    `ValueError`, records the shortfall as known-empty, and continues.
  - **The `[plan] build:` line could claim `0 missing` while the build leg dispatched every row.**
    The plan line counted `input.csv` rows, not cubes — an interrupted run (rows written, cubes not
    yet built, exactly the case a resume exists for) printed `will build 0` and then dispatched
    everything anyway. Fixed: the printed line now separately checks cube presence for rows that
    already exist, so it agrees with what `_build_shortfall` actually finds (whether `setup` is
    rerun for those ids is unaffected — the row was already correct).
  - **A known-empty cell made the top-level short-circuit unmatchable forever.** `input.csv` never
    gets a row for a shape `setup` found no imagery for, so `_flatten_identity` (computed from
    `input.csv`) never names it — but `_flatten_identity_from_request` (computed from the request
    alone) named every requested id, including known-empty ones, so the two identities could never
    agree once a single cell in a request had no imagery. Fixed: `_flatten_identity_from_request`
    now subtracts D5's recorded known-empty ids before building its cube list.
  - **`scl_mask_classes=[]` purged every row on every call.** `",".join([])` writes `""` to the
    CSV, which reads back as `NaN`, not `""` — so a legitimate "mask nothing" request could never
    match its own freshly-written window/params and every row was dropped and (with the F1 bug)
    the file ended up empty. Fixed: NaN/empty are now normalized consistently everywhere a
    `scl_mask_classes` (or similarly-joined) field is compared or re-derived.
- **Opus re-review, 2026-08-21 — 2 defects the fixes above introduced**:
  - **The duplicate-`id_col` guard was being silently swallowed.** The fix for the crashing
    out-of-coverage shortfall caught a bare `ValueError`, but `setup` raises `ValueError` for a
    second, unrelated reason: its deliberate refusal of a shapefile with duplicate ids (added
    2026-07-28, after a multi-polygon ROI made `roi_to_s2_grids` repeat cell ids). A duplicated
    shapefile therefore stopped raising and was recorded as "no imagery" instead, printing a false
    reason and dropping those shapes from `input.csv` — a loud refusal turned into quietly missing
    training data. Fixed: `setup` now raises a dedicated `NoWorkUnitsError` (a `ValueError`
    subclass, so every existing `except ValueError` caller is unaffected) and only that is caught.
  - **The known-empty manifest was write-only, so a recovered cell stayed subtracted forever.**
    Excluding known-empty ids from the request-side identity made the manifest load-bearing for
    identity equality, but nothing ever removed an id from it. Once a cell was recorded empty, a
    later forced rebuild (`overwrite="datacubes"`/`True`, the legacy full-`setup` pass — which is
    D5's documented escape hatch from a stale manifest) legitimately gave it an `input.csv` row
    again, while the request-side identity kept subtracting it: the two identities could never
    agree and the top-level short-circuit was dead for that request forever. The same failure the
    known-empty exclusion was introduced to remove, relocated. Fixed: ids that regain a row are
    forgotten, and a forced rebuild clears that window's entry outright — so the escape hatch
    actually escapes. (The *scoped* walk still never rediscovers a known-empty cell; that is D5
    working as designed, and D5's own risk note says a re-ingested archive under an unchanged
    request needs the forced rebuild.)
  - Note: the manifest is maintained by `run_create_datacube`, not by `create_datacube.setup`
    itself — `setup` cannot tell an authoritative full pass from a scoped shortfall one. Calling
    `setup` directly (below that layer) does not update it, the same way it does not do the
    window-scoped `input.csv` purge.
- **First real AML run after D6, 2026-08-21 — 2 more**:
  - **A pre-D6 `input.csv` row was adopted even though it named the OLD path.** A row is only
    current if its `export_folderpath`/`datacube_filepath` are the ones THIS request derives —
    matching on the run *parameters* alone is not enough, because D6 changed the path shape and a
    row written before it matches every parameter while still pointing at the pre-digest folder.
    Adopting it meant the new addressing silently never took effect: the plan announced a full
    rebuild while the build leg, reading the row's own stale path, found the old cube present and
    dispatched **nothing** — and the flatten stamp then recorded paths the request-derived identity
    can never reproduce, so the top-level short-circuit was dead for that request forever. Such
    rows are now purged and their ids go back into the shortfall, which regenerates them at the
    right path. Effect on an existing run folder: the first call after upgrading rebuilds its
    cubes once, which is the migration note above actually happening.
  - **The driver-side cube-presence sweep was a silent serial walk.** `_cube_present` costs four
    blob round-trips per cell (`exists` + `size`, twice), and it ran per cell, serially, in two
    separate places (the announced plan and the dispatch decision) with no progress output: ~3600
    sequential round-trips at 900 cells, ~20 minutes over the WAN, indistinguishable from a hang —
    while `setup`, doing the same class of I/O, has used 16 threads since spec 47. Presence is now
    resolved by **one recursive listing per `<window>` folder** (`storage.fs.find_sizes`), compared
    in memory by the `<id>` path leaf so it never has to reconcile local `abspath` against a
    backend's own path spelling. Folders that cannot be listed — including the ordinary "nothing
    built yet" case — fall back to per-path checks that are now concurrent and ticked, so no sweep
    is silent either way.

## `fsd.verify_adapter`: one real cube, locally, before the fan-out (spec 48, 2026-08-20)

- **New top-level verb, `fsd.verify_adapter`.** Closes the gap every existing gate stopped short
  of: `bundle.save`'s refusals prove a bundle is well-formed, `adapter_smoke` proves it imports and
  `predict` is callable, `verify_image` proves an inference image can run it — none of them ever
  hands `predict` a real array of pixels before a 299-cell cluster fan-out does. `verify_adapter`
  builds ONE grid cell's datacube (on `runner="aml"` for the case that matters, `runner="local"`
  end-to-end with no network for the test suite), lands it locally, and runs it through
  `fsd.workflows.infer_only_task.run_infer_only` — the SAME unit the cluster runs, not a new
  inference path — so `output.tif` and `grids.geojson` can be eyeballed in QGIS before a bundle is
  trusted. Returns a `_result.json`-shaped verdict naming what it did NOT check (the image, scale,
  any other cell) — and **writes that verdict to `export_folderpath/_result.json`** on every exit,
  passing or failing, so it can be pasted back into a run-book (spec 24) rather than dying with the
  process. On `runner="aml"` the one cell is built under
  `runner_kwargs["root"]/runs/<run_id>/_verify_adapter` on blob (so `runner_kwargs["root"]` is now
  required for `runner="aml"`, as it already was for `create_training_data`) and transferred DOWN
  into the local `export_folderpath` — building under the local folder would have written an
  absolute *driver* path into `input.csv` for the node to write the cube to.
- **Cell selection is deterministic by default** (largest in-window catalog coverage, tie-broken by
  id) so two runs over the same roi/window pick the same cell; `cell="random"` opts in to a random
  pick and prints the chosen id so it can be pinned back with `cell=`. `grids.geojson` is always
  written, so the QGIS pick-and-rerun loop is first-class.
- **A landed cube resumes by REQUEST identity, never by mere existence** — a second call with the
  same roi/window/bands/mosaic_days/cell skips straight to inference; a call whose
  `export_folderpath` already holds a cube for a *different* request raises rather than silently
  reusing it (the shared `fsd.workflows.stamp` helper, also used by spec 49's flatten skip).
- **`docs/howto/bundle-your-model.md`** now places `verify_adapter` → `fsd.model.verify_image` →
  `fsd.run_inference` in order, each section naming what that gate does not check.
- **Does NOT replace `verify_image`** (spec 45 D5 stands: a local run of the image check would be a
  false positive) — both gates stay, answering different questions.

## Skip the work that is already done: cubes, then flatten (spec 49, 2026-08-20)

- **`create_training_data`'s build leg now skips per-cell** — `run_create_datacube` diffs
  `input.csv`'s `datacube_filepath` column against what already exists (both `datacube.npy` and its
  `metadata.pickle.npy`, non-empty) *before* dispatching: a shortfall of 0 submits no job at all
  (`[build] 0 of N cubes missing; nothing to build`); a partial shortfall dispatches only the
  missing rows. Mirrors spec 47 D8's download diff one level up, and converts `workflows.task`'s
  existing node-side skip from a cold-start-priced no-op into a driver-side one (closes the #64
  shape for the build leg).
- **The flatten leg now skips when nothing changed** — on completion, `flatten_training_data` writes
  `_flatten_stamp.json` recording the identity of the cube set it was derived from (sorted
  `(id, datacube_filepath)` pairs) plus the run parameters that shape the arrays (`bands`,
  `mosaic_days`, the window, `aggregate`, the feature transform fingerprinted by qualname+kwargs). A
  later call whose identity matches AND whose arrays are still present skips the reduce entirely and
  returns the existing arrays as a working `TrainingData`. **The comparison never reads a
  modification time** (deliberately declines the mechanism originally proposed): the cubes live on
  blob, the arrays land locally, the two clocks are unsynchronised, and a blob's `Last-Modified` is
  read-only and cannot carry "when this content was produced" across any copy. Any mismatch, missing
  stamp, or missing array fails towards *running*, never towards a wrong skip.
- **New `overwrite=` on `create_training_data`**: `False` (default, skip whatever is already done),
  `"datacubes"` (rebuild cubes, and re-flatten), `"flatten"` (keep cubes, redo the flatten), `True`
  (both). An invalid value raises naming the valid ones.
- **Consequence:** when every cube and array is already present and current, `create_training_data`
  now does only what the user described it as doing — land the already-flattened arrays — instead of
  paying for a fan-out and a reduce it doesn't need. Every skip prints one line naming what it
  skipped and why, so a fast re-run is never mistaken for one that silently did nothing.

## Driver-side honesty: stale work lists, silent dispatch, no-op downloads (spec 47, 2026-08-20)

- **`run_inference(roi=...)` now REFUSES a resume whose cached work list is not this roi's**
  (#66). `output_folderpath/cells/input.csv` used to resume by *existence* alone, so re-running
  into a reused `output_folderpath` with a different `roi` silently re-inferred the OLD roi's
  cells. The freshly tiled cell-id set is now compared against the cached one and any difference
  raises `PreflightError` before anything is written into the folder. **Consequence:** every run
  folder created before 2026-08-19 mismatches its own freshly tiled grids (spec 46 D4 changed
  cell counts) and can no longer be resumed into — the error names that cause explicitly. The
  fix in every case is a new `output_folderpath`, which is now documented as the identity of a
  run.
- **An MPC `download` whose assets are all already catalogued no longer dispatches anything**
  (#64). `run_aml_download`'s MPC branch diffs the driver-side discovered `(tile_id, band)` list
  against the existing catalog before preflight: an empty shortfall returns the same result shape
  a dispatched run returns with `n_jobs=0` and no `jobs.create_or_update` call at all; a partial
  shortfall shards **only the missing assets**. **Consequence:** `max_tiles` is now enforced
  against the shortfall's distinct tiles rather than every discovered tile, so a request that is
  mostly already-present can pass a guard it would previously have tripped. CDSE is unchanged —
  its discovery runs on the node inside a single whole-ROI job (spec 47 D8).
- **The four silent AML legs print progress** (#65) — bundle staging, the job poll loop, output
  collection and the per-cell merge, all in `[setup]`'s established
  `[label] done/total unit (pct%) | rate | elapsed | eta` shape, now shared from `fsd.progress.ticker`
  rather than a closure inside `create_datacube.setup`. `[setup]`'s own line is byte-identical.
  The run id + run root are printed before the first job is submitted.
- **`verify_image(build_context=<folder with no fsd-*.whl>)` now raises `ValueError`** instead of
  returning `pass: False` (amends spec 45 D4). The returned `_result.json`-shaped dict is reserved
  for verdicts *about the image*; a bad argument is caller misuse and must not be indistinguishable
  from a genuinely failing image. A wheel that is present but pre-spec-44 still returns
  `pass: False` — that is a real finding about the image.

## Datacube run-folder naming + grid-cell de-duplication (spec 46, 2026-08-19)

- **`create_datacube.setup`'s export path is now named from the REQUESTED window, not each
  shape's actual acquisition min/max** (#68). Previously
  `run_folderpath/{actual_start}_{actual_end}/<id>` — data-derived, so two shapes in the same run
  could (and on AT_ROI did) land under two different `<window>` folders even though both mosaic on
  the same calendar grid. Now `run_folderpath/{startdate}_{enddate}_m{mosaic_days}/<id>` — one
  folder per run, for every cell, naming exactly the parameters that determine the cube's `T`
  (spec 15). `actual_start`/`actual_end` are not lost: they move into the cube's own
  `metadata.pickle.npy` (new keys, additive). **Consequence:** a run built under the OLD naming
  keeps its old folder name (forward-only, no migration) — `api.py`'s `*/*/output.tif` glob still
  finds it (any middle component matches), but a re-run of an old run under the new fsd writes a
  NEW folder rather than reusing the old one.
- **`grid.roi_to_s2_grids` now drops any cell fully covered by another cell in the result** (#69).
  `polyfill`ing an ROI's convex hull can re-discover neighbours that, after scale+clip, land as
  slivers wholly inside another returned cell — measured 89 % waste on an ROI that is itself one S2
  cell (9 cells emitted, 8 fully redundant). The predicate is a numerically-robust `covered_by`
  (not `contains`, which misses a boundary-sharing sliver; not IoU, which only catches exact
  duplicates) with a tie-break that keeps the smaller `id` when two cells are geometrically equal.
  Always prints the before/after count (`[grid] N cells -> M after dropping K already covered`),
  never silent. **Coverage is provably unchanged**: a dropped cell is always a subset of a kept
  one, so the union of the returned cells equals the union before de-duplication. Costs ~0.09 s on
  a 300-cell ROI (drops 1); on the degenerate single-cell-ROI case it removes 8/9 of the dispatched
  work. `roi_to_s2_grids` is unaffected in the normal (non-overlapping-cell) case.

## Bundle transparency + validation, and image verification promoted to a library call (spec 45, 2026-08-19)

- **`bundle.save` now prints a report by default** (`verbose=True`): the resolved code root, the
  embedded file list with sizes, the adapter ref, and declared requirements (#70). Pass
  `verbose=False` for the old silent behavior. **Consequence for anyone parsing `save`'s stdout**
  (nothing in this repo does): the call now writes to stdout unless silenced.
- **`bundle.save` now REFUSES a bundle whose adapter's own module would not sit at the top of
  `code/`** (#72) — e.g. `code=[...]` files drawn from two different directory trees, which pushes
  the common import root above the adapter's own directory. Raised before anything is copied,
  naming the file that pulled the root up and the one-line fix.
- **`bundle.save` now REFUSES a bundle whose embedded `.py` files import an unembedded sibling
  module** (#71) — e.g. `from helper import V` where `helper.py` sits next to the adapter but
  wasn't passed to `code=`. Detected by parsing (never importing) each embedded file with `ast`;
  transitive (a sibling that imports a sibling); a genuine dependency (stdlib, an installed
  distribution, `fsd` itself) is left alone. The error names the missing file and the fix
  (`code=[...]` with every file included). Previously this saved fine and only failed on a cluster
  node, ~40-380 s later, as `ModuleNotFoundError`.
- **New public helper `fsd.model.verify_image`** (#67): promotes
  `runbooks/scripts/45_phase1_generic_image_smoke.py`'s driver-checks-first, one-node-job,
  read-status-back logic into a reusable library call
  (`verify_image(bundle, environment=..., runner="aml", runner_kwargs=..., build_context=None) ->
  dict`, `_result.json`-shaped). `runner="local"` **raises** rather than returning a pass — a local
  run passes trivially because the driver already has the adapter's deps installed and its source
  on `sys.path` (ADR 0002), which is the false positive this helper exists to prevent. The run-book
  script is now a thin wrapper over this helper; its `_result.json` shape is unchanged.

## The model bundle now carries the adapter's source (spec 44 phase 1, 2026-08-19)

`fsd.model.bundle` gained bundle format **version 2**. Three behavior changes, all in `save`/`load`:

- **`save` now embeds the adapter's source** under `code/` by default (auto-detected from the
  adapter class, package layout preserved), and `load` prepends `<bundle>/code` to `sys.path`
  before resolving `module:attr`. **Consequence:** an adapter no longer has to be `pip install`ed
  into a per-adapter Docker image (spec 38 D4) — the inference image now differs only by
  *dependency family*. Opt out with `save(..., code=False)`; override with `code=[paths]`.
- **`save` now RAISES for an adapter class defined in `__main__`** (a script, or in practice a
  notebook cell). It previously wrote a manifest saying `adapter: "__main__:CropRF"` that could
  only fail later, on a cluster node, with a `ModuleNotFoundError` after a cold start. The error
  names the fix: put the class in a `.py` file and import it.
- **`load`'s drift-check message is now per-origin.** For a bundle carrying its own code, a
  manifest/class disagreement can only mean the bundle was edited, and the message says so
  ("the bundle has been edited"). For an installed-package adapter the original
  "code/bundle drift" wording is kept, because there the check still catches genuine version skew
  between the image and the bundle. The check itself, and the instance-vs-class `n_timestamps`
  skip rule, are unchanged.

**Backward compatible:** a version-1 bundle (no `code` block) loads exactly as before —
it is indistinguishable from a version-2 installed-package bundle, and both mean "resolve the ref
from the environment". `load` accepts versions 1 and 2 and refuses anything else.

Also additive: an optional `requirements` list in the manifest (`save(..., requirements=[...])`),
**declared and checked, never installed** — the D11 one-node smoke job now reports an unsatisfied
dependency by name instead of surfacing an `ImportError` traceback.

## `_timing.json`'s `first_admission` leg is anchored on the FIRST submission (spec 40 A3, 2026-07-29)

`<run_root>/_timing.json` (ADR 0021) is a schema other things read, so this records a change in
what two existing fields *mean* — the keys are unchanged and nothing breaks on read.

- **`driver_prep_seconds`** was `t_start → last submission` (i.e. it contained the whole submission
  loop). It is now `t_start → first submission`: driver work done before any job went out.
- **`first_admission_seconds`** was `last submission → earliest process_start_at`. It is now
  `first submission → earliest process_start_at`.

*Why:* submitting N jobs is sequential (~40 s for 32) and the early jobs are admitted **during**
it, so the two overlap and could not be adjacent legs. Run `20260729T132222Z` reported
`driver_prep=40.1, first_admission=-5.0` on a healthy dispatch — arithmetically additive, but
neither number meant what its name said. It also destroyed a signal: D11 defines a negative
admission as *the clock-skew bound being exceeded*, and the overlap artefact was producing
negatives too.

- **New `submission_span_seconds`** (first → last submission) and **`t_first_submit`**, both in
  `wall`. `submission_span_seconds` is deliberately **not** one of the five additive legs — it
  overlaps `first_admission` rather than partitioning it — but it answers the obvious follow-up to
  a large `first_admission`.

The split still telescopes to `t_end - t_start`. ⚠️ **`timings.json` from before 2026-07-29 carries
the old definition:** those two fields are not comparable across the boundary, though their sum is.

## `create_training_data` becomes the download→build→flatten→land-local façade (spec 39, 2026-07-24)

The flatten → single-array → land-local half of "training data on the cloud" (the build fan-out
was already proven, spec 36/37): `create_training_data` grows an optional download phase, and
flatten gains its own AML dispatch + a local-landing step, so the full pipeline runs as one call.

- **New verb `flatten_training_data`** (D5) — the flatten-only sibling: an `input_csv` of
  already-built `datacube_filepath`s -> one training array. `runner="local"` calls
  `datacube.flatten.flatten` in-process (unchanged); `runner="aml"` dispatches the new single-node
  cluster reduce (D3) then lands the compact result locally (D4). `create_training_data`'s own
  flatten phase now delegates here instead of calling `datacube.flatten.flatten` directly.
- **New `workflows/flatten.py` + `runners.run_aml_flatten`** (D3) — a thin in-job CLI (mirrors
  `workflows/download.py`'s shape) + a dispatcher that submits **exactly ONE** `command(...)` job
  (`n=1`, no `shard_units` — flatten is a reduce, not a per-cell fan-out), reusing
  `_aml_preflight_common`/`_aml_submit_and_wait` (spec 37) unchanged. Runs on the **existing
  general-purpose fsd Environment** — no adapter, no new image (ADR-0020).
- **New `api._land_local`** (D4) — after the reduce writes to a blob export prefix, one
  `storage.transfer` per compact array file (`data.npy`/`coords.npy`/`ids.npy`/
  `metadata.pickle.npy` + `labels.npy` iff present) brings it down to the local
  `export_folderpath`. `transfer` is already single-object + atomic, so this loop is a safe re-run.
- **`create_training_data` gains an optional download phase** (D1): new `source="mpc"` (demo
  default), `download: bool = False`, `max_tiles`, `max_cloudcover`, `cog`, `creds`. When
  `download=True` it calls `api.download(roi=label_polygons, …)` into `catalog_filepath`'s folder
  before building — `download=False` (the back-compat default) keeps the existing "catalog must
  already exist" preflight. The *build* step still never fetches from a provider itself (spec 23
  D13 unchanged) — download is an explicit prior phase the façade now orchestrates, not a change
  to what the build reads.
- **Blob-vs-local split for `runner="aml"`** (D1/D4): `export_folderpath` is always the LOCAL
  landing target; the blob working root comes from `runner_kwargs["root"]` (catalog, cubes,
  `input.csv`, and the raw flatten output all live there, under `root/runs/<run_id>/…`).
  `run_folderpath` defaults to a folder under that blob root for `runner="aml"`, and to
  `export_folderpath/run` (unchanged) only for `runner="local"`.
- **In-memory `label_polygons` auto-staged for `runner="aml"`** (Q3): the GeoDataFrame is written
  once, via the storage seam (`fs.open` + `gdf.to_json()`, not `gdf.to_file` — which needs a real
  local path and cannot target a blob `run_folderpath`), to one GeoJSON under the blob root that
  serves as both the download ROI and the per-cell build shapefile. `runner="local"` still writes
  it the same way (behavior-preserving; previously used `gdf.to_file(driver="GeoJSON")` on a
  guaranteed-local path).
- **`label_col` is now optional** (D-labels) in both `create_training_data` and
  `flatten_training_data` — `label_col: str | None = None`. When omitted, no `labels.npy` is
  written; `ids.npy` is the join key for labels joined in later without re-flattening. The
  required-`label_col` preflight check is dropped (`id_col` stays required).
- **Adapter `n_timestamps` preflight dropped** (D6): `create_training_data` no longer asserts
  `compute_n_timestamps(...) == adapter.n_timestamps` — `T` is whatever the caller's window/
  `mosaic_days` produce; a model is retrained at that `T`, not the other way around. The
  cross-cube calendar-mosaic invariant flatten enforces (spec 15) is unchanged and still raises.
- **Driver-side features unchanged, now explicitly after land-local** (D2/ADR-0020): the feature
  transform (`adapter=`/`feature_sequence=` -> `features.npy`) already ran on the driver before
  this spec; for `runner="aml"` it now runs *after* `flatten_training_data` lands the array
  locally, reading/writing the local `export_folderpath` — no cluster node ever imports an
  adapter. Behavior for `runner="local"` is unchanged.

Reuse ledger (spec 39 §4): `datacube/flatten.py::flatten`, `api.download`,
`api._apply_training_features`, `workflows/runners.py::_aml_submit_and_wait`/
`_aml_preflight_common`, `storage/fs.py::transfer`, `workflows/create_datacube.py`, and
`raster/`/`bands/`/`catalog/`/`sources/`/`fsd.model` are **unchanged** — spec 39 is orchestration +
land-local, not new pipeline code. Docs: `docs/adr/0020`, `CONTEXT.md` ("reduce job",
"land-local").

## Inference at scale on Azure ML — `runner="aml"` for ROI-mode `run_inference` (spec 38, 2026-07-23)

P4: `run_inference(roi=…, runner="aml")` dispatches the per-cell build+infer unit (spec 21)
onto the `rise` AML cluster, reusing spec 36's runner machinery — a **thin step-4 dispatch
swap**, no new pipeline algorithm — plus the I/O-seam fixes the swap exposed:

- **`raster.cog.to_cog` learns a remote-dst branch** (D5, closes TODO #17): when `dst` is a
  remote `fsd.storage` URL, GDAL still converts on node-local scratch, then `storage.transfer`
  publishes it. `model.engine._write_output_cog` and `api._merge_outputs` land on blob through
  it. **Two instances of the same latent bug had to be fixed at the callers** (both derived a
  raw scratch tif from `dst` itself, `f"{dst}.raw.tif"`, + did `os.makedirs(dirname(dst))` — for
  a remote `dst` that is a forbidden `rasterio.open("abfss://…","w")` on a remote-looking path
  that scatters junk local dirs): `api._merge_outputs` (the driver-side `merged.tif`) **and**
  `model.engine._write_output_cog` (the per-cell `output.tif` an AML node writes — the primary
  site; the latter was caught in the Opus review, not the initial impl). Both now stage the raw
  tif on node-local scratch (`tempfile`) regardless of `dst`; `to_cog` handles the remote publish.
- **Bundle loads once per core per node, not once per cell** (D7, closes TODO #25's root
  cause): `run_local_inference` now forwards `cubes_per_task` (previously silently dropped);
  the `create_inference` Snakefile groups `cubes_per_task` cells per job instead of one job per
  cell; `infer_task.run_infer_task` resolves the adapter via `engine._adapter_from_bundle_cached`
  (the per-process cache spec 22's infer-only path already used) instead of a fresh
  `bundle.load` per cell. `infer_task.run_infer_group(input_csv, (lo, hi), bundle_path, …)` is
  the new grouped entrypoint (mirrors `infer_only_task.run_infer_only`'s shape); the CLI grows an
  `--input-csv`/`--rows` mode alongside the original single-cell positional-args mode. **The
  load-per-core default is computed on the node** (`infer_shard._resolve_cores_and_group`): with
  `cores`/`cubes_per_task` unset the node picks `cores = os.cpu_count()` and groups cells into
  `ceil(n_units/cores)` so the bundle loads once per core (heavy-model opt-out: `cores=1` →
  one whole-shard group, one load). `api.run_inference`'s `cores`/`cubes_per_task` now default to
  `None` (= auto); local/pre-built paths still behave as the old `1`.
- **`infer_task.run_infer_task` gains a first-line skip-if-`output.tif`-exists** (D6, `overwrite=`
  kwarg to force a rebuild) — the durable per-cell resume signal, mirroring `task.run_task`'s
  existing `datacube.npy`-exists skip. The `create_inference` Snakefile no longer touches
  `export_folderpath` at all (grouping/sentinels are keyed by row-range + node-local scratch), so
  the D7-style `is_local`-guarded `abspath` this Snakefile predated is now moot rather than
  reproduced — a remote `export_folderpath` plans cleanly with no special-casing.
- **New:** `workflows/infer_shard.py` (node entrypoint, mirrors `workflows/shard.py`) and
  `workflows/adapter_smoke.py` (D11: a one-node adapter-import smoke run once before the N-node
  fan-out, `skip_smoke=True` opt-out). Bundle staging is manifest-driven (D3): the driver's
  `runners._stage_bundle` and the node's `infer_shard.fetch_bundle_to_scratch` both walk
  `bundle.json`'s `artifacts` map — no recursive directory listing, no change to `bundle.load`.
- **New:** `workflows.runners.run_aml_inference` (D1/D1a/D2/D11) — stages the bundle, shards the
  already-tiled+`setup`'d cells (`shard_units`, reused verbatim), submits one job per shard (+ the
  smoke job), waits, aggregates `_status/<k>.json`, raises on failure. `api.run_inference` gains
  `runner="aml"`/`runner_kwargs` for ROI mode only (D14) — `_check_local_seams`'s
  `storage_allowed` is now `roi_mode and runner=="aml"` (was unconditionally `False`); the
  pre-built-cubes path and local ROI mode are unchanged.
- **Three cross-cutting folds, not P4-specific but surfaced by it:**
  - **D8 (closes TODO #51, MPC-only):** each MPC AML shard now writes its own
    `{root}/runs/{run_id}/shards/catalog-<k>.parquet` instead of all shards racing an
    unsynchronised read-modify-write against the same `catalog.parquet`; the driver
    sequentially `TileCatalog.append`s each shard catalog into the canonical one after every
    shard finishes (`runners._merge_shard_catalogs`) — a deliberate serialization, not a lock.
    CDSE (single job, already single-writer) is untouched.
  - **D9/D10 (closes TODO #52):** `api._normalize_window` coerces `startdate`/`enddate` to
    tz-aware UTC `Timestamp`s once, as the first thing `download`/`run_inference` do, raising a
    `PreflightError` on the driver for an unparseable date — before any AML job, not after a
    40-380s node cold-start. Closes the CDSE/MPC divergence (only the CDSE AML node path
    normalized before) and the type-dependent pystac search-window bug (issue #644: a date
    string expands to end-of-day, a `Timestamp` does not). `run_inference`'s `dt` (the STAC
    output-item datetime) is coerced too (a minor instance of the same smell); `bands`/
    `scl_mask_classes`/`mosaic_scheme`/`source`/`merge`/`runner` audited and verified clean.
  - **D13 (closes TODO #53):** `create_datacube.setup` dedupes `input.csv` on a unit's content
    identity (`id`+`startdate`+`enddate`+`bands`+`mosaic_days`+`mosaic_scheme`+
    `scl_mask_classes`, keeping the newest) instead of appending unconditionally forever; **and**
    `run_aml`/`run_aml_inference`/`run_local_inference` all raise before dispatch if two
    distinct-content rows still share an `export_folderpath` (keyed by `id` alone — dedupe on
    content identity does not by itself prevent that collision).

Reuse ledger (spec 38 §4): `workflows/task.py`, `datacube/`, `raster/` (besides `to_cog`),
`bands/`, `catalog/` query, `model/bundle.py`, and `storage/*` (incl. `azure.py`) are **unchanged**
— P4 is a dispatcher + a node entrypoint + the I/O-seam fixes above, not a rewrite of the
build/inference algorithm spec 21/36 already proved. Docs: `docs/adr/0001`, `docs/adr/0002`,
`CONTEXT.md` (new glossary).

## `create_datacube.setup` reads the catalog once, and reports progress (2026-07-22)

Two changes to `workflows/create_datacube.py::setup`, both provoked by running
`runbooks/36-aml-runner.md` Phase 3 (900 labelled fields, catalog on `abfss://`), where setup ran
for many minutes with **no output at all** before submitting a single AML job.

- **One catalog read per run, not one per shape.** `setup` called `TileCatalog.filter(...)` inside
  its per-shape loop, and `filter` opens with `gdf = self.read()` -- a *full* read of the catalog
  file (`fs.read_parquet` does `raw = f.read()`, no range read, no cache). Locally that is a ~12 ms
  page-cache hit and nobody notices; on a remote catalog it is one full download per shape: **900
  shapes = 900 downloads of the same ~121 KiB parquet, ~106 MiB of redundant transfer and ~900 VPN
  round-trips** before any work started. The pure filtering logic is now
  **`catalog.filter_gdf(gdf, shapes_gdf, startdate, enddate)`**, a module-level function;
  `TileCatalog.filter` is unchanged behaviourally and simply delegates
  (`return filter_gdf(self.read(), ...)`), while `setup` reads once and calls `filter_gdf` per
  shape. **Identical output** -- same rows, same files, same order, and `.attrs` (the spec-35
  declaration stamp) still propagates to each slice, since the same operations run on the same
  frame. Pinned by `tests/test_workflows.py::test_setup_reads_catalog_once_regardless_of_shape_count`,
  verified non-vacuous (restoring the per-shape `filter` call makes it fail).
- **Live progress + ETA.** `setup` now prints a throttled (2 s) `[setup] i/N shapes (p%) | r
  shapes/s | elapsed Xs | eta Ys` line, plus a one-line note that the catalog was read once. The
  per-shape writes are genuine network I/O on a remote run folder, so the loop can legitimately run
  for minutes -- and silence there is indistinguishable from a hang (which is exactly how it was
  first reported).

- **Shapes are prepared concurrently** (`max_concurrent`, default `config.SETUP_MAX_CONCURRENT =
  16`; pass `1` for the old serial behaviour). With the catalog read hoisted, the remaining cost is
  the per-shape *writes* -- `makedirs` + `geometry.geojson` + the `catalog.parquet` slice, ~4-7 tiny
  blob calls -- which measured **~1.8 s/shape serially on `rise` over VPN (~27 min for 900 shapes)**.
  That is latency, not bandwidth or CPU, so it parallelises nearly linearly with threads. Each shape
  touches only its own folder and only *reads* the shared catalog frame, so there is no shared
  mutable state; this is the same pattern `sources.mpc.download`/`download_shard` already use to
  drive `fsd.storage` concurrently against blob (proven at 3456 assets on the cluster).
  **`input.csv` row order is unchanged** -- results are placed by index and compacted, so the
  manifest follows the shapefile's order, not completion order. Pinned by
  `test_setup_manifest_order_is_shapefile_order_not_completion_order` (verified non-vacuous: writing
  results in completion order makes it fail). One behavioural nuance: when a shape raises, the pool
  lets in-flight shapes finish before the exception propagates, so slightly more work lands than in
  the serial version -- the exception itself still surfaces from `setup`.

Further collapsing the per-shape writes (batching them into fewer objects) is a design change, not a
fix -- see TODO #15.

## Download on Azure ML — `runner="aml"` for `api.download`, per-source dispatch (spec 37, 2026-07-22)

The download sibling of spec 36: dispatches the **already-working** download-to-blob path (spec 34)
onto the same `rise` AML cluster, colocated with blob, instead of relaying every byte through the
driver machine. `sources/cdse.py`'s `download()` and `sources/mpc.py`'s `download()` change by
**zero lines** (spec 37 §4's reuse ledger) — this only adds a dispatcher and two additive source
entries.

- **Dispatch shape is per-source, not uniform fan-out (D1):** CDSE always submits **exactly one**
  whole-ROI job (`sources.cdse.download` called unmodified) — its S3 concurrency cap is per
  credential (4 connections, CDSE *Quotas and Limitations*), so more nodes contend for the same
  connections rather than adding throughput. MPC **fans out across N shards** — its bytes come
  straight from Azure Blob (no per-credential cap), so parallel nodes scale near-linearly.
- **`workflows/runners.py::run_aml_download`** is the new dispatcher; it reuses spec 36's
  `shard_units`, D5 Environment, D4 identity, D10-style preflight, and D9 telemetry. A shared
  `_aml_submit_and_wait` was factored out of `run_aml`'s submit/poll/aggregate/raise loop and is
  now used by both `run_aml` (spec 36) and `run_aml_download` (spec 37) — a pure refactor, `run_aml`'s
  own tests are unchanged. `_aml_preflight`'s cluster/environment/storage-root checks were
  similarly split into a shared `_aml_preflight_common`, reused by a new download-specific
  `_aml_download_preflight` (D7: also checks discovery non-emptiness, the Key Vault secret
  resolves/parses and isn't expired, and warns — doesn't block — when a CDSE GB estimate exceeds an
  injected remaining-quota threshold).
- **`workflows/download.py`** (new): the thin in-job CLI, mirroring `workflows/shard.py`'s role for
  spec 36. `--roi` mode is the CDSE job (calls `sources.cdse.download` unmodified, reading S3 creds
  from Key Vault on the node); `--shard` mode is one MPC shard (calls the new
  `sources.mpc.download_shard` over a pre-discovered, pre-partitioned asset-row CSV). Both write a
  `_status/<k>.json` (D9), same `_result.json` shape as spec 24/36.
- **`sources/mpc.py` gained two additive entries** (the ROI-based `download()` is untouched):
  `discover_shard_rows(...)` — driver-side STAC discovery **without** eager SAS-signing (a new
  `_search_items_unsigned`, sibling of `_search_items`), flattened to one row per asset; and
  `download_shard(rows, ...)` — signs each asset's href **on the node** (`_import_pc_sign`, lazy,
  mirrors `runners._import_aml_command`'s injection pattern) right before the transfer, so a SAS
  token never sits idle between AML job submit and the job actually starting, then reuses the
  existing `_transfer_and_stamp_one` per asset.
- **`sources/cdse.py` gained one additive entry:** `CdseCredentials.from_json_str(s)`, a sibling of
  `from_json` that parses an in-memory JSON string (the Key Vault secret value) instead of a file
  path. The stale `download()` docstring line claiming a remote+`cog=True` dst "raises... deferred"
  (predating spec 34's `_push_scratch_to_remote` fix) is corrected to describe the actual
  stage→convert→push behavior.
- **New `fsd/secrets.py`:** `get_secret(vault_url, name)`, a thin `SecretClient(vault_url,
  DefaultAzureCredential()).get_secret(name).value` (D5) — lazy-imports `azure-keyvault-secrets`
  (new dependency, added to the `[azure]` extra) so `import fsd` never needs it; substitutable in
  tests via `get_secret=` on `run_aml_download`/directly monkeypatched on the CLI. Both the CDSE S3
  creds and (optionally) `PC_SDK_SUBSCRIPTION_KEY` ride this one path, under the **same**
  `AZURE_CLIENT_ID` identity spec 36 D4 already sets for blob — no new infra grant needed (the
  compute identity already holds `Key Vault Secrets User` on the `rise` vault).
- **`api.download` accepts `runner="local"|"aml"` + `runner_kwargs`**, mirroring
  `create_training_data`'s existing pattern. `creds` is ignored for `runner="aml"` (the dispatched
  job reads them from Key Vault instead), and `roi` must be a url the node can also read, not an
  in-memory GeoDataFrame.
- **Job timeout (D6):** each submitted job now carries `limits=CommandJobLimits(timeout=...)`,
  sized from a GB estimate at a conservative throughput (`runners._estimate_timeout_seconds`) —
  `run_aml` (spec 36) had no explicit timeout; `run_aml_download` always sets one.
- **New `config.CDSE_MONTHLY_QUOTA_GB`** (12,000 — CDSE's rolling-30-day cap) backs the D7 quota
  warning.
- **Idempotency/crash-resume limitation, stated plainly (D8):** the skip check is against local
  scratch, and spec 34's push is whole-run, so a job that crashes mid-run loses its un-pushed
  scratch — a fresh-node resume re-downloads the unpushed remainder rather than seeing what already
  landed on blob. Accepted for v1 (see `LIMITATIONS.md`); MPC's fan-out makes this cheap (only the
  crashed shard's slice re-runs).

### `run_aml_download` stops ignoring per-source arguments (TODO #49, 2026-07-22)

One signature serves both sources, and two arguments were being accepted and dropped:

- **Credentials are now refused for `source="mpc"`.** MPC is anonymous; supplying `creds_url` /
  `vault_url` / `secret_name` is a hard preflight error naming the argument, rather than a silent
  no-op. This was not cosmetic — a run written as `source="mpc"` but wrapped in the run-book's
  `blob_creds()` staged the CDSE S3 keys in plaintext on blob for the whole run and never read them.
- **`max_tiles` is now enforced on the driver, for both sources.** Previously it reached CDSE only,
  via `--max-tiles` on the node (i.e. after the cluster had spun up), and the MPC path dropped it
  entirely. Since `sources/mpc.download` *does* raise on `len(tiles) > max_tiles`, the same call
  meant different things by runner — `api.download(source="mpc", max_tiles=N)` raised locally and
  downloaded everything on AML, breaking spec 36 D3's premise that the runner is not part of the
  semantics. Preflight now raises before any node starts. **MPC counts distinct MGRS tiles**, not
  shard rows (assets = tiles x bands), matching the unit the local guard counts.

**Behaviour change to expect:** an MPC AML run whose ROI x window matches more tiles than
`max_tiles` now fails fast instead of downloading everything. Real case: a 2018 full-year Austria
run = 572 tiles, which a nominal `max_tiles=500` now refuses.

### `sources/cdse._roi_gdf` reads the roi through the storage seam (2026-07-22)

`_roi_gdf` (used by `cdse.query_catalog`/`download` **and** all three `sources/mpc` entry points)
passed its path straight to `gpd.read_file`. GDAL/pyogrio has no `abfss://` driver, so a roi on
blob failed with `DataSourceError: <url>: No such file or directory` — for a file that was
demonstrably there. It now reads via `fs.open` + `BytesIO`, the same fix `workflows/task.py`
already carried (spec 36 D6a, TODO #40); local paths and in-memory GeoDataFrames behave exactly as
before. **Found live** in `runbooks/37-download-on-aml.md` Phase 1, on the first CDSE dispatch with
the roi on blob — spec 37 is what made a remote roi mandatory (the node has no `shapefiles/`).
⚠️ **The node runs the wheel baked into the AML image, so the image must be rebuilt** for the fix
to reach the job. Three sibling sites still bypass the seam — TODO #47.

### D5 REVISED (keep-both): blob-JSON `--creds-url` CDSE creds fallback (2026-07-22)

Key Vault *write* turned out operationally blocked for the operator (`ForbiddenByRbac` from both the
driver laptop and the compute VM — the identity only holds *read*), so CDSE creds delivery now
accepts **either** source, caller's choice, **mutually exclusive**:

- `run_aml_download`/`workflows/download.py`'s `run_roi` gained `creds_url: str | None` alongside the
  existing `vault_url`/`secret_name`. Exactly one must be supplied — `_aml_download_preflight` raises
  on neither and on both.
- The blob path reuses the **existing** `CdseCredentials.from_json(creds_url)` (already blob-capable
  via `fs.open`) — no new read code, unlike the KV path which needed the additive `from_json_str`.
- `run_aml_download`'s command builder emits `--creds-url <url>` **xor** `--vault-url <url>
  --secret-name <name>` — never both, and never a secret *value* (unchanged invariant, now asserted
  for the blob path too, spec 37 §7 test 7b).
- KV stays wired unchanged for when a write role lands; blob creds are a documented plaintext-at-rest
  trade-off (`LIMITATIONS.md`), mitigated by the runbook writing to a `_secrets/` prefix and deleting
  the file once the run completes.

## The AML scale runner — `runner="aml"`, plus local resumability on blob (spec 36, 2026-07-21/22)

Closes TODO #40/#41. Gives the runner seam (spec 10 Seam 2) a second backend without touching the
unit of work: `workflows/task.py::run_task` is byte-for-byte the function spec 08 defined, and
`datacube/`, `raster/`, `bands/`, `catalog/`, `sources/` are untouched (spec 36 §4's reuse ledger).

- **`runner="aml"` dispatches shards of `input.csv` onto the `rise` AML cluster**
  (`workflows/runners.py::run_aml`): shard → submit one command job per shard (each running
  `python -m fsd.workflows.shard <shard_csv_url> --cores N`, which calls back into the **existing**
  `run_local`) → wait → aggregate `_status/<k>.json` → raise, listing which shards failed. The AML
  SDK (`azure-ai-ml`) is imported lazily inside `run_aml` only — `import fsd` never requires it (new
  `[aml]` extra, opt-in, not in the default install).
- **Idempotency changed for both runners, not just AML** (D7): a task whose `datacube.npy` already
  exists at `export_folderpath` now returns immediately (`run_task`'s first line) instead of
  rebuilding, and each artifact publish is temp-path-then-`fs.rename` (`datacube/builder.py::
  _save_npy_atomic`) rather than a direct write — a reader never observes a partial artifact, and a
  recovery-retried shard skips every cube it already finished. Metadata publishes before the
  datacube (the datacube's existence is the resume signal, so it must imply the metadata is done).
- **The local Snakemake runner's own `start.txt`/`done.txt` sentinels moved to node-local scratch**
  (`_snakefiles/create_datacube/Snakefile`), keyed by a hash of `export_folderpath` instead of
  living inside it. **Behavior change:** the Snakefile's `RuntimeError` on a remote
  `export_folderpath` is gone — the local runner now works with artifacts on blob (durable resume
  is `run_task`'s own existence check, not Snakemake's DAG, across separate invocations/machines).
- **ROI/label geometry I/O now goes through `fsd.storage`** (TODO #40, closing the last raw-path
  I/O the spec-31 §6 audit found): `workflows/create_datacube.py::setup`'s two geometry sites and
  `workflows/task.py::run_task`'s geometry read all go via `fs.open` + `BytesIO`/`to_json()` instead
  of `gpd.read_file(path)`/`gdf.to_file(path)` directly. A local path behaves exactly as before
  (`fsd.storage` already routes `file://` transparently) — this closes the gap that made ROI inputs
  unreadable from a cluster node with no `shapefiles/` checkout.
- **`fsd.storage.fs` gained `rename(src, dst)`** — the atomic-publish primitive (`fs.mv` under the
  hood), generalizing the temp-then-rename pattern `fs.transfer` already used for downloads.
- **`api.create_training_data`/`workflows.create_datacube.run_create_datacube` accept
  `runner="aml"`** end-to-end, with a new `runner_kwargs` dict forwarded to `run_aml` (`cluster=`,
  `environment=`, `root=`, `identity_client_id=`, ...). `_check_local_seams` now validates against
  `("local", "aml")` instead of hardcoding `"local"`.
- Azure **Batch** was evaluated and dropped, not deferred (quota: 6 dedicated cores vs. a 64-core
  pool VM cannot allocate one node) — `AZURE_INFRA.md` §3.1, spec 36 D1.

## Declaration persistence — the collection declaration survives write→read (spec 35, 2026-07-21)

Amends spec 34 §2a/§4, closing TODO #42 (below): the collection-level `SourceDeclaration`
now survives every catalog write→read hop, not just the per-row `offset`/`nodata` columns.

- **Authority moved from `GeoDataFrame.attrs["declaration"]` (in-memory only, a typed
  dataclass) to the catalog Parquet file's own footer**, as a JSON dict under
  `attrs["fsd:declaration"]` (versioned, `fsd_declaration_version`). `fsd.storage.fs`'s
  `write_parquet`/`read_parquet` gained generic `.attrs` <-> `PANDAS_ATTRS` footer
  preservation (the upstream pandas/geopandas convention, geopandas PR #3597) — the fix
  lives at the storage seam so it covers all three write→read hops (ingest catalog,
  per-cell slice, builder entry) at one choke point, not just `TileCatalog`.
- **`TileCatalog.append` now stamps a declaration** (`declaration=` kwarg, constructor
  default); one catalog file = one collection = one declaration — a conflicting append
  raises. `sources.cdse.download`/`sources.mpc.download` stamp `S2_L2A_DECLARATION` at
  their existing `catalog.append` call (this is the change that makes hop 1 real — before
  this, *nothing* in the ingest path declared anything).
- **Behavior change, intentional (spec 34 `[G4]`'s "fail loudly, don't half-understand"
  rule applied here too): a catalog read from a file with no declaration stamp now
  raises** at `flatten_catalog`/`build_datacube`, naming the file and the re-stamp
  command (`python -m fsd.catalog.restamp_cli <catalog.parquet> --declaration s2_l2a`,
  a sub-second rewrite of the catalog Parquet alone — the imagery is untouched, nothing
  is re-downloaded). A **hand-built** `GeoDataFrame` (never through
  `fs.read_parquet`) keeps the S2 L2A default — an explicit in-process call is treated as
  an explicit choice, preserving synthetic-test/notebook ergonomics. The four catalogs
  written before this spec (`demo_e2e`, `mpc_baseline`, the `rise` blob catalog, old
  per-cell slices) need re-stamping before they build again; folded into TODO #44's
  re-ingest, not a separate migration.
- **STAC gets an additive Collection mirror** (`TileCatalog.to_stac`/`write_stac_catalog`):
  the mask band's classes as the standard `classification:classes` on an `item_assets`
  entry, plus `fsd:declaration` for the fields STAC has no vocabulary for. Read back via
  `fsd.catalog.stac.collection_to_declaration`. The Parquet footer stays authoritative —
  the mirror cannot drift because both are written from the same object.
- **`GeoDataFrame.attrs["declaration"]` (the typed dataclass key) is retired** — a
  dataclass must never sit in `.attrs` once any writer JSON-encodes it (verified: a future
  geopandas raises `TypeError` on write). Use `fsd.catalog.declaration.from_attrs`/
  `to_attrs` instead of touching `.attrs["declaration"]` directly.
- Was logged as TODO #42 (review pass, 2026-07-20; corrected 2026-07-21 while writing this
  spec — the gap was **not** latent on the production path, `run_task` used
  `S2_L2A_DECLARATION` unconditionally). Pinned meanwhile by
  `tests/test_catalog.py::test_declaration_does_not_survive_catalog_roundtrip_todo_42`,
  deleted and replaced by `test_declaration_survives_catalog_roundtrip` + the spec 35 §8
  test suite (`tests/test_declaration.py`, `tests/test_restamp_cli.py`, and additions to
  `test_storage.py`/`test_catalog.py`/`test_datacube_builder.py`/`test_catalog_stac.py`).

## Ingest/normalization contract: `stage → normalize → put`, declaration-driven builder (spec 34, 2026-07-20)

- **`apply_boa_offset`'s lossy `clip(DN−1000, 0, 65535)` is dropped from the store path**
  (it was never actually called there — spec 32 only used it at build/read time — but
  the function itself is renamed `fsd.raster.images.apply_offset` and documented as
  read-time-only, generalized past S2's BOA-specific name). The on-disk COG is now
  explicitly the lossless artifact; the offset is metadata, applied at read time by the
  builder and, independently, by an `unscale`-aware viewer (spec 34 §1).
- **`boa_add_offset` catalog column retired; `offset` + `nodata` replace it** (spec 34
  §1/`[G4]`) — `fsd.catalog.catalog.COLUMNS`. `offset` is the same additive-DN semantics,
  renamed generic (not S2-BOA-specific); `nodata` is new (spec 34 §1c — some MPC COGs
  omit a nodata tag; ingest now declares one, defaulting to 0). **No back-compat shim:**
  `TileCatalog.read()` does not backfill a legacy catalog missing these columns
  (`fsd/catalog/catalog.py`); a pre-spec-34 catalog is disposable, not migrated.
- **CDSE now derives `offset` from `s2:processing_baseline`** (`fsd.sources._s2_radiometry
  .offset_for_item`, shared with MPC) — closes #30/#10 (CDSE previously hardcoded 0/never
  harmonized). CDSE's jp2→COG conversion (`_convert_one`) now also stamps the GDAL
  scale/offset + nodata-if-missing tag (`fsd.raster.cog.stamp_or_reencode`) — free, since
  it already re-encodes.
- **MPC's download is no longer a pure byte-copy** — after `fs.transfer`, it stamps the
  same GDAL tags on the local file (`_transfer_and_stamp_one`) before the file is
  considered done. Still cheap (a header-only edit, `IGNORE_COG_LAYOUT_BREAK=YES`; no
  pixel decode) unless the in-place stamp breaks COG validity, in which case
  `stamp_or_reencode` falls back to a GDAL-COG-driver re-encode.
- **Both CDSE's and MPC's local-only download guards are lifted** (spec 31 §5-ARCHIVE
  suspended these) — a remote (`abfss://`) `root_folderpath` now works for both. MPC
  streams each file through local scratch before pushing (`fs.put`); CDSE reuses its
  entire existing local pipeline unchanged against a temp scratch root, then does one
  whole-run batch push + catalog-rewrite at the end (`_push_scratch_to_remote`) — **not**
  per-file streaming (that's TODO #31, still out of scope), so a CDSE run against a
  remote root is not yet crash-resumable the way a local-root run is.
- **`build_datacube` is declaration-driven, not S2-hardcoded** (spec 34 §2, closes #35):
  a new `fsd.catalog.declaration.SourceDeclaration` (+ `MaskSpec`) carries reference
  band, mask spec, mask-keep, nodata default, mosaic method. Resolved from the explicit
  `declaration=` kwarg, else `catalog_subset.attrs["declaration"]` (set by
  `flatten_catalog`), else the S2 L2A default (`S2_L2A_DECLARATION`) — so every existing
  caller (`workflows/task.py`, `api.py`, `create_datacube.py`) is unchanged. The mask
  step is skipped entirely (not just tolerated) when the declared mask band isn't in the
  requested `bands` — `bands=["B04"]` no longer raises `ValueError: SCL band not present`.
  A `mask_type` other than `"categorical_classes"`, or `native_grid=True`, raises
  `NotImplementedError` (loud, documented gaps — `[G2]`/`[G3]`) instead of silently
  mis-assembling or mis-collapsing. `ops.apply_cloud_mask_scl` gained a `mask_band="SCL"`
  parameter (default preserves old behavior) so the same op works for any categorical
  mask band, not just SCL.
- **STAC export carries `raster:bands` + role-tagged asset `roles`**
  (`fsd.catalog.stac.tile_catalog_to_items`) — every raster asset gets `offset`/`scale`/
  `nodata` (pystac `raster` extension) and a role (`reflectance`/`mask`/`reference`)
  alongside `"data"`. `items_to_rows` recovers `offset`/`nodata` on the reverse mapping.
- **New:** `fsd/catalog/declaration.py` (`SourceDeclaration`, `MaskSpec`,
  `S2_L2A_DECLARATION`), `fsd/sources/_s2_radiometry.py` (shared baseline→offset),
  `fsd/raster/cog.py::stamp_gdal_tags`/`stamp_or_reencode`, `fsd/docs/adding-a-source.md`.

## P1 Azure compute seam: `storage=` is now meaningful (spec 31, 2026-07-17)
- **`storage=` on `download`/`create_training_data` now does something** — previously
  `_check_local_seams` (`api.py`) rejected any non-`None` `storage` unconditionally ("blob lands
  in P1"). It now accepts `storage="azure"` or `{"backend": "azure", ...}`, which sets
  `FSSPEC_ABFSS_ANON=false` in **both** `os.environ` (for Snakemake-subprocess children, which
  re-read `FSSPEC_*` at their own import) and `fsspec.config.conf` (for the already-imported
  parent — fsspec only reads env at import time, so a later `os.environ` mutation alone would not
  be seen in-process). `runner!="local"` and any other `storage` backend still raise.
  `run_inference`/`deploy` are **unchanged** — `_check_local_seams` gained a `storage_allowed`
  flag and those two verbs pass `storage_allowed=False`: inference/serving-on-blob is P4/P5, out
  of P1 scope, and stays rejected exactly as before.
- **No new registry, no credential object.** adlfs, given only `account_name` (parsed from the
  `abfss://` URL host) + `anon=False`, builds its own `DefaultAzureCredential`. All ~94 existing
  `fs.<fn>` call sites in `fsd.storage.fs` are untouched — an `abfss://…` URL now simply resolves
  through `fsspec.core.url_to_fs` to a credentialed adlfs filesystem, no fsd code in the path.
- **New `fsd/storage/azure.py`**: `to_vsi(url)` (deterministic `abfss://<fs>@<account>.dfs.core
  .windows.net/<path>` -> `/vsiadls/<fs>/<path>`; local paths pass through unchanged; `az://<fs>/
  <path>` accepted as an alias), `account_from_url(url)`, `storage_token()` (a fresh
  Storage-scoped bearer token from a single **module-cached** `DefaultAzureCredential` — reused
  across calls per the documented best practice; the SDK's own token cache/refresh means "fetch a
  fresh one per open" is cheap and correct, no hand-rolled expiry margin), and
  `configure_storage(storage)` (the `storage=` -> env/`conf` helper above). `fsd.storage.fs.to_vsi`
  re-exports it.
- **Raster pixel reads now route through `fsd.raster.rio_open`** in the three pixel-read modules
  (`raster/images.py`, `raster/cog.py`, `catalog/stac.py`), replacing bare `rasterio.open`. For a
  local path it is a **byte-for-byte passthrough** (no `Env`, no translation — the regression
  hinge). For an `abfss://`/`az://` path it opens via GDAL's `/vsiadls/` handler inside a
  `rasterio.Env(AZURE_STORAGE_ACCESS_TOKEN=…, AZURE_STORAGE_ACCOUNT=…)` — the account comes from
  the URL host (D1), not ambient config — and keeps that `Env` alive for the dataset's lifetime
  (closed when the dataset is closed), since GDAL may issue further range-reads after open.
  `mode="w"` on a remote path **raises** rather than silently half-writing: P1 has no write path
  to blob (MPC-to-blob, when it lands, is a byte-copy via `fs.transfer`, never a GDAL write; CDSE-
  to-blob is out of P1 scope). `raster/cog.py`'s `to_cog` **write** path (`rasterio.shutil.copy`)
  is unchanged — it is local-only by design (CDSE's jp2->COG conversion; CDSE is untouched by P1).
- **Not changed, deliberately**: `sources/mpc.py` (`mpc.py:294`'s local-only guard stays) and
  `sources/cdse.py` (its `cog=True`-needs-local guard stays) — download-to-blob is **suspended**
  into the next spec (the ingest/normalization contract); P1's blob data is hand-staged
  (`runbooks/31-p1-upload-slice.md`). `datacube/builder.py` and `workflows/*.py` needed **no**
  fixes for the §6 URL-safety audit — both were already clean (`fs.*` throughout, `os.path.join`
  on catalog rows is posix-safe on an `abfss://…` host per §2). The remaining bare
  `rasterio.open(...)` sites (`api.py`'s inference-merge path, `model/engine.py`'s inference-output
  write) are **out of P1 scope** (inference/serving-on-blob is P4/P5) and were not touched.
- **New optional dependency**: `azure-identity` added to the `[azure]` extra (alongside `adlfs`) —
  `DefaultAzureCredential` construction needs it directly for the GDAL VSI token path (adlfs
  resolves its own copy internally, but `fsd.storage.azure` also needs one for `rio_open`).
- **New §6 audit finding + fix (beyond the spec's own grep head-start, which only checked
  `os.path.exists`/`os.makedirs`/bare `open(` and missed this): `workflows/create_datacube.py`'s
  `setup()` and its Snakefile both called `os.path.abspath()` on `export_folderpath` unconditionally.**
  `os.path.abspath` does not recognize a URL as absolute (`os.path.isabs("abfss://...")` is `False`),
  so it silently prepended the local cwd and mangled the `abfss://` scheme into `abfss:/` — a real,
  silent corruption bug for a blob `export_folderpath`, not just a style nit. Fixed with a new
  `fsd.storage.fs.is_local(path)` guard (both call sites) — no behavior change for local paths.
- **New, deliberately-not-fixed finding: the local Snakemake runner's own `start.txt`/`done.txt`
  sentinel bookkeeping (`create_datacube/Snakefile`'s `touch()`) is plain `os.makedirs`/`open`, not
  routed through `fsd.storage`.** Even with the `os.path.abspath` bug fixed, a remote
  `export_folderpath` would make Snakemake's own DAG/resumability tracking silently create a garbage
  local sentinel directory (not a crash — `open("abfss://.../done.txt", "w")` is a valid, if bizarre,
  *local* relative path). This is a **real limitation of the local runner**, not something spec 31's
  scope (§1–§4/§6/§7) covers or that a "swap bare `rasterio.open`" pass can fix — it needs a design
  decision about where Snakemake's own bookkeeping lives when artifacts are remote (candidates: keep
  it always-local via a separate scratch dir, or a proper Snakemake remote-storage plugin). **The
  Snakefile now raises a clear `RuntimeError` instead of silently corrupting** (fail loud, per the
  project's `rio_open`-write-guard precedent) — the workaround today is to keep `run_folderpath` local
  (the datacube/flatten artifact writes themselves are fully storage-seam-safe on blob regardless) or
  to invoke `python -m fsd.workflows.task` directly for a single remote build (no Snakemake
  involved — this is exactly what the demo run-book does). Logged as TODO #41 (folded into the Batch
  runner item, since a real fix likely arrives with that redesign anyway).
- See `specs/31-p1-azure-storage-seam.md` (realizes spec 10 Seam 1: storage = config, not code).

## MPC discovery dedupes reprocessed acquisitions (spec 33, 2026-07-16)
- **`sources/mpc.py`** now de-duplicates STAC items at discovery time: `query_catalog` and
  `download` both call a new `_dedupe_reprocessed_items(items)` immediately after `_search_items`,
  before any catalog row is built. MPC can serve >1 STAC item for the same physical acquisition
  (a one-off `sen2cor` reprocessing pipeline bug, since cleaned up on MPC's side, per spec 33's
  cross-validation) — same sensing `item.datetime` + same `s2:mgrs_tile`, different item id. Prior
  behavior: both items downloaded (redundant bytes) and both catalogued, with
  `datacube.builder._stack_datacube`'s CRS/`image_index` tie-break arbitrarily picking a winner at
  merge time. Grouping key is in-memory `(item.datetime, _mgrs_tile_from_item(item))` — no new
  catalog column. Winner = the item with the latest `s2:generation_time` (a populated STAC
  property; reversing the id-string-parsing approach the runbook originally suspected, since ESA's
  naming-convention doc does not guarantee the id's trailing field is monotonic). A duplicate group
  missing `s2:generation_time` on any member raises (deterministic, no silent pick); a singleton
  item is never affected even if it lacks the property. **MPC-only** — `sources/cdse.py` and
  `_finalize_catalog_gdf` are untouched; CDSE's own multi-item surfacing (datastrip-split
  near-duplicates) is a structurally different, ESA-by-design case that can carry legitimate
  different pixel coverage, so a shared rule risked dropping real CDSE data. See
  `specs/33-mpc-reprocessing-dedup.md`.

## MPC source + S2 processing-baseline harmonization (spec 32, 2026-07-16)
- **New source `sources/mpc.py`** — Sentinel-2 L2A discovery + download against Microsoft
  Planetary Computer (MPC), signed via the official `planetary-computer` package (new `[mpc]`
  extra), anonymous by default. Unlike CDSE (spec 01/14/25), MPC assets are **already COG on
  Azure**, so `mpc.download` is a **pure byte-copy** (`fsd.storage.transfer`, signed HTTPS ->
  local) — no `jp2->COG` conversion, no convert-process-pool. `api.download` gains
  `source: "cdse" | "mpc"` (default `"cdse"`, unchanged); `source="mpc"` does not require `creds`.
- **New catalog column `boa_add_offset`** (`catalog/catalog.COLUMNS`, before `geometry`) — the
  additive S2 processing-baseline reflectance offset (fixes correctness debt #10: baseline 04.00,
  introduced 2022-01-25, adds `BOA_ADD_OFFSET=-1000` to L2A reflectance DN; MPC serves raw,
  unharmonized DN and does not expose the offset in STAC `raster:bands`, so it's derived from the
  item property `s2:processing_baseline`, **keyed on baseline not acquisition date** — MPC
  reprocessing can stamp a >=04.00 baseline on a pre-2022 date). **Backward-compatible**:
  `TileCatalog.read`/`append` fill a missing/absent column with `0` — old catalogs and CDSE rows
  (which don't yet set it, see `TODO.md`) are unaffected.
- **`datacube.builder.flatten_catalog`** now emits a per-band `boa_add_offset` output column:
  the tile-row's offset for reflectance bands (`B01`…`B12`/`B8A`), `0` for non-reflectance
  (`SCL`/`AOT`/`WVP`/`visual`/…) — `raster/images._is_reflectance`. **`build_datacube` applies the
  offset per source image** (new `builder._apply_boa_offsets`, called right after
  `images.load_images` returns, before `dst_crs`/reference/resample/mosaic) via the new
  `raster/images.apply_boa_offset(data, profile, *, offset)` op
  (`clip(DN + offset, 0, 65535)`, dtype-preserved, nodata-safe). This guarantees a calendar window
  straddling the baseline cutover is harmonized to one scale **before** `median_mosaic` collapses
  it — a datacube-level op would be too late (the median would already have mixed baselines).
- **Not yet done** (see `TODO.md`): CDSE rows still default `boa_add_offset=0` unconditionally
  (wiring CDSE's own baseline capture is a follow-on); MPC stays local-download-only (Phase 2 /
  spec 31 decides stream-in-place vs copy-to-`rise`).

## flatten `coords.npy` reprojected to EPSG:4326 (TODO #16, 2026-07-15)
- **`datacube.flatten` now emits `coords.npy` as `(lon, lat)` in EPSG:4326**, not raw per-cube
  easting/northing in the cube's native UTM CRS. Each cube's kept-pixel coords are reprojected
  from `geotiff_metadata["crs"]` to EPSG:4326 (`rasterio.warp.transform`) before concatenation, so
  a training set spanning multiple UTM zones (e.g. EuroCrops west EPSG:32636 / east EPSG:32637) no
  longer mixes incomparable eastings/northings in one array (the same easting number in two zones
  is two different places). No-op when a cube's metadata carries no CRS (synthetic/legacy) or is
  already EPSG:4326. **Behavior change to the `coords.npy` artifact** — downstream code that read
  coords as native UTM must now expect lon/lat; the spectral arrays (`data`/`ids`/`labels`) are
  unaffected. Multi-zone reprojection covered by a new test in `tests/test_datacube_flatten.py`.

## stac-geoparquet export + Tier-2 mini-MPC harness (spec 30, 2026-07-15)
- **New, additive module `catalog/stac_geoparquet.py`** — `items_to_stac_geoparquet(items,
  dst_filepath)` writes a `list[pystac.Item]` to a single GeoParquet file via the `stac-geoparquet`
  library (new optional `[serving]` extra); `stac_geoparquet_to_items(src_filepath)` is the inverse
  (round-trip validation). Both stage through a local tmp file + the `fsd.storage` seam
  (`fs.put`/`fs.open`), since the installed `stac-geoparquet==0.8.1` API always wants a real
  filesystem path, not an fsspec handle. Not wired into any default write path — `run_inference`
  still writes the JSON STAC catalog as before; the full catalog-format migration is TODO #26's
  follow-on. Round-trip-tested (`tests/test_stac_geoparquet.py`, `pytest.importorskip`-guarded so
  the core `.venv` skips it) and smoke-run against the real 300-item Austria catalog via the new
  `demos/mini_mpc/export_stac_geoparquet.py` CLI.
- **New `demos/mini_mpc/` — the Tier-2 "mini-MPC" validation harness**, a local, throwaway
  pgSTAC + stac-fastapi-pgstac + titiler-pgstac stack proving fsd's inference outputs load and
  serve through the same register→searchId→XYZ flow MPC uses. `docker-compose.yml` pins the
  `pgstac:v0.9.11` DB image as-is; the two app services (`dockerfiles/Dockerfile.{stac-fastapi-pgstac,
  titiler-pgstac}`) install the **pinned stock PyPI packages** (`stac-fastapi.pgstac==6.3.1`,
  `titiler.pgstac==3.0.0`) on a slim Python base rather than forking a Dockerfile/source
  checkout — no published "just pull it" app-layer image exists upstream (see the README's table
  for the full rationale). `load_pgstac.py` converts the existing static STAC catalog to ndjson,
  rewriting each output COG's href to the container-visible `/data/<path>` the compose bind-mount
  exposes (the one non-obvious wiring step — 500s without it), and `pypgstac load`s it.
  `register_and_url.py` reuses spec 29's `build_colormap`, registers a
  `collections=["fsd-inference"]` search, and prints the XYZ tile template. **Deviates from spec
  30's draft assumption:** the installed `titiler.pgstac==3.0.0`'s own routes are
  `/searches/register` + `/searches/{id}/tiles/...` (response key `id`), not `/mosaic/register` /
  `searchid` — that's MPC's own product naming around the identical underlying contract
  (`STACNOTATOR_DIGEST.md §3`); documented in `register_and_url.py`'s docstring, à la spec 29's
  rio-tiler pin. Scripts + `runbooks/30-tier2-mini-mpc.md` only — Claude never runs Docker; the
  href-rewrite/ndjson-emission logic was smoke-tested directly (no Docker) against the real
  300-item catalog before handoff.
- **Runbook-run fix (2026-07-15):** the `raster` (titiler-pgstac) container crashed at startup with
  `ImportError: libexpat.so.1` — `python:3.12-slim` doesn't ship the system lib rasterio (via
  rio-tiler) links at import. `dockerfiles/Dockerfile.titiler-pgstac` now `apt-get install -y
  libexpat1` before pip. Runbook clarified: bring the stack up with `docker compose up --build -d`
  and keep it running for steps 2–6, run all `docker compose` commands from `demos/mini_mpc/` (it's
  directory-scoped), and `docker compose ps -a` to catch a crashed/exited container. Plain-language
  primer + running issue log kept at the workspace root in `MINI_MPC_NOTES.md` (outside the public
  repo).

## STAC inference-output Item geometry: true cell polygon, not raster bbox (spec 28, 2026-07-14)
- **Behavior change:** `catalog/stac.py::cog_outputs_to_items` gains a `geometries=` kwarg — a
  `{output_cog_filepath: geometry.geojson_path}` mapping sourced from the `run_inference` build
  manifest (`input.csv.shapefilepath`). When given, every output Item's `geometry`/`bbox` is now the
  **true S2-cell polygon** (CRS84, read straight from the manifest's `geometry.geojson`) instead of
  the raster bounding box — the old behavior over-claimed coverage past the ROI's slanted edges
  (BUG entry). `bbox` is tightened to the polygon's own bounds (still STAC-valid: `bbox` contains
  `geometry`). **Deterministic, manifest-driven, no fallback:** a COG missing a geometry entry, or
  one whose `geometry.geojson` is unreadable/empty, **raises** — this is not a per-item best-effort.
  `geometries=None` (the default) is unchanged: the raster-bbox path, for geometry-less callers
  (bare COG lists, unit tests, the pre-built folder/list inference modes with no manifest).
- `api.py::_finalize_outputs` gains a matching `geometries=` passthrough. Both `run_inference` modes
  now supply it: ROI mode (`_run_inference_roi`) builds it from the `input.csv` rows it already
  reads back; the pre-built `input.csv` mode (`_resolve_inference_pairs`) now also captures
  `shapefilepath` alongside `datacube_filepath`/`id` when present. Folder/list pre-built modes have
  no manifest and keep passing `geometries=None` (raster bbox, unchanged).
- New convenience wrapper `catalog/stac.py::cog_outputs_to_items_from_manifest(input_csv)` — reads
  an `input.csv`, builds the `geometries` map, calls `cog_outputs_to_items`. Used by the new
  `demos/regen_output_stac.py` (regenerates an existing output STAC from its manifest, no
  re-inference) and available to any future caller that only has an `input.csv` path.

## Titiler demo server: Tier-1 pre-styled XYZ for STACNotator BYO (spec 29, 2026-07-14)
- Purely additive (`demos/` + a new `[titiler]` optional extra) — no `src/fsd/` change. New
  `demos/titiler_serve.py`: a minimal FastAPI app serving `merged.tif` as a param-free pre-styled
  XYZ (`GET /cropmap/tiles/{z}/{x}/{y}.png`) via `rio-tiler` — discrete categorical colormap (from
  `demos/e2e_austria.py::CLASS_COLORS`, overridable by a `render.json`), `nodata=255` -> transparent,
  `resampling_method="nearest"` (categorical codes must never interpolate), permissive CORS.
  Validates fsd's serving-contract with the real consumer (STACNotator's Bring-Your-Own-XYZ mode)
  before the heavier Tier-2 pgSTAC + titiler-pgstac stack. Not part of fsd's core `.venv` — installs
  into an isolated `.venv-titiler`.

## Download pipeline: transfer/convert process-pool split (spec 25, 2026-07-11)
- **Conversion decoupled onto a process pool.** `sources/cdse.py::download` previously ran
  transfer+convert serially on one of `MAX_CONCURRENT_S3=4` worker threads
  (`_transfer_and_convert`); GDAL's `to_cog` holds the GIL, so a few converting threads starved the
  rest and collapsed download concurrency (~0.2 file/s observed, spec 23 instrumentation). Now a
  `MAX_CONCURRENT_S3`-wide **thread** pool only transfers bytes, while a separate
  `MAX_CONVERT_PROCS`-wide **process** pool (`spawn`, GDAL-safe) converts JP2→COG concurrently —
  chained via `add_done_callback` and bounded by a `sem_staged` backpressure semaphore (staged-but-
  unconverted JP2s on disk). Behavior kept: conversion is still lossless COG **with overviews**
  (`COG_OVERVIEWS="AUTO"` unchanged, D2). `_transfer_and_convert` is removed, replaced by
  `_transfer_one` (thread stage) + `_convert_one` (process stage, top-level & picklable);
  `_download_one` survives as the sequential reference wrapper (`_transfer_one` then inline
  `_convert_one`) but `download()` no longer calls it. New optional `download`/`download_resume`
  kwargs: `max_convert_procs`, `max_staged`, `convert_executor` (all defaulted, backward-compatible;
  `convert_executor` is the test seam — inject a synchronous stand-in to exercise the pipeline
  without a subprocess). The convert pool is created **lazily** (first file needing conversion) —
  `cog=False` or an all-skip resume pass spawns zero processes.
- **`MAX_STAGED` is disk-aware, not a static constant** (D5/D6): `cdse._default_max_staged` helper
  sizes the backpressure cap once at `download()` start from
  `shutil.disk_usage(root_folderpath).free` (`STAGING_DISK_FRACTION=0.25`,
  `STAGING_ITEM_GB=0.2`), targeting `headroom = MAX_CONCURRENT_S3 + 2*MAX_CONVERT_PROCS`. Disk is a
  **cap, not a lever** — a larger buffer past the saturation floor gives no throughput gain (bounded-
  buffer queueing), so free disk only shrinks the cap, never grows it. New `config.py` constants:
  `MAX_CONVERT_PROCS = min(os.cpu_count(), 8)`, `STAGING_DISK_FRACTION`, `STAGING_ITEM_GB`.
- **Circuit breaker → streaming stop, transfer-failures-only** (conscious semantics change). The old
  breaker "finished the current chunk, then stopped" (`ThreadPoolExecutor` per file-chunk); the new
  one continuous pipeline has no chunk boundary. The breaker now keys on **consecutive transfer
  failures only** — a `_convert_one` failure is a local/data fault (`"ConvertError"`), not a CDSE
  window, and does not touch the consecutive counter. On trip, the submit loop stops queuing new
  work; in-flight transfers/converts drain; the pass returns `circuit_tripped=True`, stopping within
  roughly `max_staged` items of the trip (no exact chunk count — `download_resume` is still the real
  recovery). `test_circuit_breaker_trips_and_stops_early` rewritten to monkeypatch `_transfer_one`
  and assert early stop, not the old exact "4 of 6" chunk count.
- **`chunksize` repurposed.** No longer batches the executor (there is one continuous pipeline); it
  now controls only the catalog-flush cadence (flush every `chunksize` completed files). Default
  stays `100`; callers (`download_resume`, api, demos) are unaffected.

## Download pipeline: exception-safe callbacks, no silent hang (spec 25b, 2026-07-11)
- **`download()`'s inner callbacks are now exception-safe.** A Phase-1 review of spec 25 found that
  `_on_transfer_done`/`_on_convert_done`/`_finalize` assumed the happy path — a **broken convert
  process pool** (GDAL segfault / OOM-kill) or a **catalog-flush write error** raised *before* the
  `remaining` decrement / `sem_staged` release, and `add_done_callback` swallows callback exceptions,
  so the drain never completed and `download()` hung forever on `all_done.wait()`. Fixed: `remaining`
  and `sem_staged` accounting no longer sit behind any fallible call (`pool.submit`, `cfut.result()`,
  the parquet write) — `fut.result()`, the convert hand-off, and `cfut.result()` are all wrapped, and
  the `sem_staged` release in `_on_convert_done` moved to a `finally`.
- **New `DownloadResult.pool_broken`** (additive, defaults `False`): set when the convert process pool
  dies mid-run. On a broken pool, the submit loop halts cleanly (no more new work queued; in-flight
  transfers still drain) instead of transferring granules that can no longer be converted.
  `sum_results` ORs it across passes, like `circuit_tripped`.
- **New `"PoolBroken"` failure reason** — counted in `failed_count`/`failures`/`reason_counts`, but
  **breaker-neutral** (does not touch the transfer circuit breaker's consecutive counter), same
  rationale as `"ConvertError"` (spec 25 C4): a broken local process pool is not a bad CDSE window.
  `download_resume` already retries a `pool_broken` pass with no cooldown (its completion check is
  keyed on `failed_count`/`circuit_tripped`, unaffected by this new reason) — bounded by `max_passes`
  as before; a deterministically-crashing granule re-breaks the pool each pass (TODO: per-granule
  quarantine).
- **Chunk-flush moved off the counters lock.** `_finalize` now snapshots-and-clears `pending_results`
  under `lock`, then calls `_append_downloaded` (the parquet write) outside it — serialized by a
  dedicated `flush_lock` (needed because concurrent flushes of *different* snapshots would otherwise
  race-write the same catalog file). A flush failure logs a warning and re-queues the snapshot for a
  later flush (recovered by `download_resume`'s idempotent-skip on the next pass if it's never
  retried within the run). The end-of-run flush is likewise wrapped.

## Safe download runner CLI + should_stop seam (spec 26, 2026-07-11)
- **New `should_stop: Callable[[], bool] | None = None` kwarg on `download()`/`download_resume`**
  (additive, default `None` = unchanged behavior). A generic user-stop predicate — not a hard-coded
  stop-file — checked in `download()`'s submit loop at the two existing checkpoints (top-of-loop and
  post-`sem_staged.acquire()`), alongside `tripped`/`pool_broken`, throttled to at most once per
  `config.PROGRESS_EVERY_S` (a filesystem `os.path.exists` isn't stat-ed per granule). Semantics are
  identical to `tripped`/`pool_broken`: halts **new** submissions only, every already-submitted
  transfer/convert finalizes normally and drains, a stopped item is never attempted (not a failure,
  not counted). New **`DownloadResult.stopped: bool = False`** (additive); `sum_results` ORs it.
  `download_resume` passes `should_stop` through to each pass, adds `if r.stopped: break` (a user
  stop ends the resume loop immediately — no cooldown, not a completion), and checks `should_stop()`
  once before starting each new pass.
- **New CLI `python -m fsd.sources.download_cli`** (`src/fsd/sources/download_cli.py`) — a thin
  driver wrapping `download_resume`: `--dry-run` (metadata-only preview via `plan_download` +
  `format_download_plan`, **zero band bytes**, no `probe_throughput`), `--stop-file` (builds the
  `should_stop` closure), an optional single `probe_throughput` baseline on the real path
  (skippable `--no-probe`), and a spec-24 `_result.json` per run. Exit code doubles as PASS/FAIL:
  `0` on clean completion **or** a user stop, non-zero on `failed_count>0`/`circuit_tripped`/
  unresolved `pool_broken`.
- **`_fmt_progress` ETA edge case fixed.** Rate/ETA were already reported (`N.N file/s | ETA ~Xm`);
  now `ETA ~?` is shown until `done > 0` (previously `ETA 0m`, misleadingly precise with no
  completions yet to extrapolate from). All existing fields/tokens unchanged (spec 23 assertions
  still hold).
- **Confirm-run runbook** `runbooks/26-download-confirm-run.md` — the first real CDSE network
  exercise of the spec-25/25b pipeline, over the tiny 1-MGRS-tile Austria slice (~7 granules/~2 GB,
  reusing `demos/e2e_austria.py::_single_tile_roi`). Not run yet (mobile-hotspot pause, spec 26) —
  self-contained `expected` block so a later session can verify the user's pasted `_result.json`
  without this conversation's memory.
- **Review fix (2026-07-11): CLI completion gate is now the terminal pass, not the summed
  `failed_count`.** `sum_results` sums `failed_count` across passes, so a resume that hit a
  transient failure on an earlier pass and recovered it on a later, clean pass previously reported
  `status="failed"`/exit 1 even though every file landed — the CLI was stricter than
  `download_resume`'s own completion semantics. `download_cli.main` now judges `status`/exit code
  from `results[-1]` (the terminal pass); an empty `results` list (stop-file already present before
  pass 1) is now `status="stopped"`, not a false "ok". `metrics.failed` reflects the terminal pass;
  a new `metrics.failed_total` keeps the historical sum as a diagnostic. Plus: a stale `--stop-file`
  silently turned "re-run to resume" into an instant no-op — the CLI now warns on startup if the
  stop-file already exists, and the runbook's step-2 failure guidance now says to `rm -f` it before
  resuming.
- **UX fix (2026-07-13): label the two silent startup phases.** `probe_throughput` silently
  downloads one full JP2 (~50–150 MB) and `download_resume` does its own STAC search before the
  first progress line, so a real run looked hung for up to a minute at launch. `download_cli` now
  prints `probing throughput (downloads 1 band file)…` / `probe: N.N MB/s` around the probe and
  `discovering + planning download…` before the download loop (all gated by `--quiet`, like the
  live progress lines). The runbook's step-2 "Expect" and "Stop / observe" wording — which had
  promised a standalone probe line that the code never emitted — now match.
- **Runbook criteria fix (2026-07-13), after the first real confirm-run (13-granule Austria slice).**
  Two defects in `runbooks/26-download-confirm-run.md`, both found while verifying the pasted
  `_result.json`: (a) the step-2 PASS formula `successful + skipped == missing_count` was wrong —
  `missing_count` is **granules** while `successful`/`skipped` are **files** (`len(bands)+1` per
  granule, the +1 being `MTD_TL.xml`), and `successful` already *includes* the skipped files, so the
  sum double-counted and mixed units; corrected to `successful == missing_count × (len(bands)+1)`
  with `failed == 0`. (b) the step-1 `missing_count` range `[5,10]` (assumed ~7) was too low — the
  real slice is **13 granules** (single MGRS tile, S2A+S2B ~5-day revisit over 2 months), so the
  range is now `[10,15]` and `--max-tiles` bumped `10 → 15` (13 would trip the old guardrail). Also
  documented that a real throughput measurement (step 4) needs a **fresh** download (`skipped == 0`),
  not a resume — a resume yields `transfer_s == aggregate == 0`.
- **Bugfix (2026-07-13): `download()` creates a missing local output root.** A fresh `--dst`
  `FileNotFoundError`'d because `_default_max_staged`'s `shutil.disk_usage(root_folderpath)` disk
  probe runs before any write, and nothing created the root (leaf dirs auto-create on write, but the
  probe is earlier). `cdse.download` now `fs.makedirs(root_folderpath, exist_ok=True)` for a local
  root right after the cog/local guard — creating the destination root is part of `download()`'s
  contract, not the caller's job, so this fixes the CLI, `fsd.download`, and workflows at once.
- **`_result.json` fix (2026-07-13): populate `expected` and `error`** (they were hardcoded `{}` /
  `None`, defeating spec 26 §4's self-contained-diff design). `download_cli` now (a) auto-fills the
  real-run `expected` with the universal success invariants (`failed=0, stopped=false,
  circuit_tripped=false, pool_broken=false`) and merges the runbook's run-specific criteria from a
  new `--expected-json PATH` flag; (b) sets `error` to a short reason on a non-exception
  `status="failed"`; and (c) wraps the run so a crash (network/creds/disk) still writes a
  `status="failed"` result with `error=repr(exc)` **before** re-raising — the runbook flow always has
  a result to paste. The confirm-run runbook now writes an `expected.json` and passes `--expected-json`
  to steps 1–2.
- **Stop-file UX (2026-07-13): acknowledge the stop + tighten the poll.** Two issues with
  `touch <stop-file>`: it was silent (no sign the stop was seen), and it appeared to take "too long"
  (progress kept climbing well past the touch). `download()` now (a) prints
  `stop requested — halting new submissions; draining N in-flight …` the moment the stop is first
  seen (N = in-flight count), and (b) polls the stop-file on a dedicated `STOP_CHECK_EVERY_S = 1.0`s
  interval (was coupled to `PROGRESS_EVERY_S = 5`s) so new submissions halt within ~1s of the touch.
  The *overshoot itself is by design*: a clean stop drains everything already in flight (≈ `max_staged`
  ≈ `MAX_CONCURRENT_S3 + 2×MAX_CONVERT_PROCS` ≈ 20 files) so no partial `.part`/`.src.jp2` is left —
  lower `--max-staged` to trade throughput for a tighter stop. Runbook stop-drill + "Stop / observe"
  updated accordingly.
- **Throughput metric honesty (2026-07-13), after the first fresh-download measurement.** The first
  real confirm-run read as `aggregate 4.83` vs `probe 25.4 MB/s` — alarming until you notice they
  aren't measured the same way. `aggregate_mb_per_s = bytes / thread-summed transfer_s` is a
  **per-stream** rate; comparing it to the single-stream probe is fine, but it isn't the effective
  throughput. `DownloadResult` gains **`transfer_wall_seconds`** (the wall-clock span the transfer
  phase actually occupied, earliest-start..latest-end, tracked in `_on_transfer_done`), and
  `download_cli` now reports **`wall_transfer_mb_per_s = bytes / transfer_wall_seconds`** — the
  honest all-streams effective rate. `wall ≥ probe` ⇒ concurrency helped; `wall < probe` ⇒ it didn't.
  First run: probe 25 / per-stream 4.8 / **wall 19** MB/s → link-bound, 4 streams slower than 1.
- **New `--max-concurrent-s3` knob (2026-07-13).** `download()`/`download_resume()`/`download_cli`
  gained `max_concurrent_s3` (default `config.MAX_CONCURRENT_S3=4`), threaded through the transfer
  `ThreadPoolExecutor` and `_default_max_staged` sizing, so a link-bound run can sweep stream count
  (`--max-concurrent-s3 1|2`) without editing `config.py`. Runbook step-4 rewritten to explain the
  three rates (probe / per-stream / wall) and which pair to compare.
- **`demos/e2e_austria.py` crop-map/NDVI colors (2026-07-13):** replaced the arbitrary `tab20`
  class colormap (which painted pasture/grassland pink) with a curated `CLASS_COLORS` dict —
  semantic where possible (grass→green, mustard→yellow, sunflower→orange, alfalfa→violet, …) and
  spread across hue/lightness for separability. Applied to **both** the crop map and the NDVI
  timeseries so each class has one consistent color; unlisted classes fall back to `tab20`. Cosmetic
  (demo-only); regenerate `demos/figures/{crop_map,ndvi_timeseries}.png` by re-running the demo.
- **`demos/E2E_AUSTRIA.md §8` filled from the real 2026-07-13 full run** (stitched: download+train
  from pass 1, inference from a clean re-pass) — timing table, download transfer/convert/wall block,
  per-cell build-vs-infer decomposition, and merged-map coverage (6830×6868, EPSG:32633, 99.2% valid).
- **`E2E_AUSTRIA.md` is now the single go-to doc (2026-07-13).** Threaded the safe download runner
  (`python -m fsd.sources.download_cli`: `--dry-run` sizing, `--stop-file`, `--max-concurrent-s3`,
  `_result.json`/`--expected-json`, the probe/per-stream/wall rates) into §2 + a §5 dry-run tip; added
  **Appendix C** ("why run the full ROI") capturing the real bugs full-ROI runs caught — spec-20
  tile-merge, spec-26 STAC id collision, the multi-UTM-zone display merge. **`demos/README.md`**
  rewritten from the stale Ethiopia writeup (referenced the renamed `e2e_ethiopia.py` /
  `inference_roi.geojson`) into a **thin redirect** to `E2E_AUSTRIA.md` (driver/adapter/estimator/
  figures pointers + a one-paragraph history note).
- **STAC inference-output item-id collision fixed (2026-07-13).** `catalog.stac.cog_outputs_to_items`
  derived each Item id from the COG **filename stem** (`os.path.basename → splitext`), but fsd writes
  every output as `<cube_id>/output.tif` — so all N items got the constant id `"output"`.
  `write_stac_catalog`'s `normalize_hrefs` then mapped them all to `./output/output.json`, producing a
  `collection.json` with **N identical item links** and **one** item file on disk (all others
  overwritten). Surfaced on the full Austria run (300 cells → 300 dup links, 1 file). Fix: id now comes
  from the **parent directory** (`_output_item_id`, the cube id — unique by fsd's `<cube_id>/output.tif`
  layout in both ROI and prebuilt-cubes modes), plus a **uniqueness guard** that raises if ids ever
  collide again instead of silently emitting a corrupt catalog. `merged.tif` + per-cell COGs were
  unaffected (they use `output_filepaths`, not the ids). Regression: `test_run_inference_writes_cogs_and_stac`
  now asserts **distinct** item ids (the old `len(items)==2` passed on the bug because
  `get_items(recursive=True)` followed the duplicate links to the same file twice). 213 passed.
- **`demos/e2e_austria.py` step 5 bugfix (2026-07-13): pass the required `output_folderpath`.**
  `step_inference` called `fsd.run_inference(...)` without `output_folderpath`, so ROI-mode preflight
  aborted with `PreflightError: output_folderpath is required.` — surfaced on the first full run to
  reach step 5 (smoke levels never exercised it end-to-end). Now passes
  `output_folderpath=OUTDIR/model_outputs`, matching the runbook 27 / `E2E_AUSTRIA.md §5` output paths
  (`model_outputs/<cell>/output.tif`, `stac/`, `merged.tif`). Demo-only; no `src/fsd/` change.
- **`demos/e2e_austria.py` step 2 now reports the aggregate (wall) transfer rate (2026-07-13)**, to
  match `download_cli` and the wall metric above. It divided `bytes_downloaded / transfer_seconds`
  (the thread-summed **per-stream** rate) everywhere; now the console `transfer` line shows the
  transfer-only wall seconds + **both** rates (`X MB/s aggregate / Y per stream`), the
  probe-vs-effective verdict compares the probe against the **aggregate** rate, and
  `cost_model["transfer_mb_per_s"]` (→ `demos/estimate.py` ETAs) is the aggregate rate
  (`per_stream_mb_per_s` kept as a diagnostic). Rationale: per-stream understated throughput ~4×
  (confirm-run 4.8 vs 19 MB/s) → the demo printed the wrong link-vs-contention verdict and
  `estimate.py` predicted download times ~4× too slow. Reporting/calibration only — no pipeline
  behavior change; `E2E_AUSTRIA.md §8`'s "MB/s summed" template line follows when §8 is filled.

## e2e Austria local-completeness gate + download instrumentation (spec 23, 2026-07-10)
- **`DownloadResult` gained decomposed metrics** (`fsd.sources.cdse`): `bytes_downloaded`,
  `transfer_seconds`, `convert_seconds`, `bytes_by_band`. `_transfer_and_convert` now times the CDSE
  byte-transfer separately from the local jp2→COG conversion (interleaved per file in worker
  threads, so the summed seconds may exceed wall-time). `_download_one` returns `(ok, reason,
  metrics)` — a **signature change** (its 4 call-site tests updated). New `sum_results` aggregates
  `download_resume`'s per-pass results.
- **New `cdse.probe_throughput`** — single-threaded one-file fetch → achievable MB/s baseline, so a
  run can tell CDSE/link-bound from local contention (VPN/background load).
- **New `cdse.plan_download` + `format_download_plan`** (the D13 guardrail) — query STAC + diff
  needed-vs-present tiles → an actionable `fsd.download(...)` plan (JSON + printed command, +GB/ETA
  when a cost model is known). Wired into the `create_training_data` / `run_inference` preflight:
  **missing imagery now raises a clear "run fsd.download first" with the exact params**, not a deep
  file-not-found. Compute verbs still never auto-fetch (quota + the Batch download-once model).
- **`run_inference` merge is now cross-UTM-zone-safe by default policy.** `_merge_outputs`
  `"reproject"` picks the target CRS by **max total cell area** (was most-cells; correct for clipped
  ROI-edge cells) and accepts a **`merge_crs=`** override (EPSG/CRS string). It is **lossless where a
  cell already matches the target** (single-zone ROIs like Austria don't resample). `run_inference`
  gained `merge_crs`.
- **`demos/e2e_ethiopia.py` → `demos/e2e_austria.py`** — now a **reusable template** that starts from
  a real CDSE **download** (step 2, probe + `download_resume` + decomposed timing), uses ROI-mode
  `run_inference(merge="reproject")`, and is driven by `--roi/--train/--id-col/--label-col/--creds`.
  New `demos/estimate.py` (no-download ETA) + `demos/E2E_AUSTRIA.md` (the go-to local-run doc).

## Inference parallelism: retire `mp.Pool`, unify on the runner seam + idempotent outputs (spec 22, 2026-07-07)
- **`engine.run_local` no longer uses `multiprocessing.Pool`.** It is now the **in-process
  sequential** path only (`cores=1` / live adapter / tests / debug). Parallel pre-built-cube
  inference (`cores>1`) fans out through the **Snakemake infer-only runner**
  (`workflows/infer_only_task.py` + `_snakefiles/infer_only/Snakefile` +
  `runners.run_local_infer_only`), routed from `api.run_inference` (kept out of `engine` to avoid a
  model→workflows import cycle). So **all** parallel fan-out (build, ROI, pre-built inference) now
  goes through the runner seam → Batch (P4) can dispatch pre-built inference too, as a pure
  `runner=` swap. **No `mp.Pool` anywhere in fsd.**
- **Inference is now idempotent.** Both paths **skip existing outputs unless `overwrite=True`** —
  a re-run of `run_inference` over an already-inferred set does nothing (fixes the observed
  behaviour where the engine re-inferred every cube despite existing `output.tif`). `cores>1`
  resumes via per-group sentinels; `cores=1` via an `fs.exists` check.
- **New `cubes_per_task` knob (default 1)** groups K cubes per Snakemake job so the one-per-job
  bundle load amortises (recovers the pool's economics without a pool — the intra-task loop is
  sequential). `overwrite=True` forces recompute (`--forceall`). `run_inference` gains
  `overwrite` + `cubes_per_task`; **default `cores=1` → fully backward-compatible** (only new
  default behaviour is skip-existing).
- **Behaviour preserved:** `cores=1` stays no-bundle in-process; `cores>1` requires a bundle (a live
  adapter is auto-saved), same as the old pool. Positional calls `run_inference(model, cubes, out)`
  unchanged.
- **Bundle drift-check relaxed for *unset* spec fields (`model/bundle.py::load`).** A field the
  adapter class leaves unset — `None`, an empty list, or `n_timestamps == 0` (the base default) — is
  now **skipped** by the code/bundle drift check; the bundle value is authoritative. This lets **one
  adapter class back models trained on different `T`** (n_timestamps is a trained-model property, not
  a code constant) — surfaced when the demo's `cores>1` path first exercised `bundle.load` in a
  worker. Fields the class *does* pin are still drift-checked (real drift still raises).
- **Demo (`demos/e2e_ethiopia.py`) now infers via the bundle at `cores>0`** (`model=bundle_dir,
  cores=CORES, cubes_per_task=20`) instead of a live sequential adapter — so step 5 is parallel +
  resumable and the demo is real coverage for spec 22. `demos/adapters.py::DemoRF` no longer
  hardcodes `n_timestamps` (model-determined). The demo exports its dir to `PYTHONPATH` so the
  runner's subprocesses can import `adapters:DemoRF`.

## run_inference: ROI mode + three merge modes (spec 21 / P0.75, 2026-07-07)
- **`api.run_inference`** now has two mutually-exclusive modes. Old (spec 18): pass
  `inference_datacubes=` (pre-built cubes, engine `mp.Pool`). New (spec 21): pass `roi=`
  (+ `catalog_filepath`/`startdate`/`enddate`/`mosaic_days`/`bands`) → fsd tiles the ROI
  (`fsd.grid`), then fans out a per-cell **build-datacube + infer → COG** task via the **runner
  seam** (`workflows/infer_task.py` + `_snakefiles/create_inference/Snakefile` +
  `runners.run_local_inference`). `inference_datacubes` + `output_folderpath` are now optional
  (both default `None`, validated) — **positional calls `run_inference(model, cubes, out)` still
  work**. `InferenceResult` gains `grids_filepath`.
- **Why the runner seam, not the existing pool:** the per-cell unit-of-work is what Azure Batch
  dispatches at P4, so folding inference into the runner keeps P4 a pure `runner=` swap. (The
  pre-built `mp.Pool` path was **subsequently retired too** — see the spec-22 entry above.)
- **`merge=` is now tri-state:** `False` (per-cell COGs only) | `True` (**strict single-CRS**,
  refuses cross-CRS, error points at `"reproject"`) | `"reproject"` (**display** merge: reproject
  to the dominant zone, nearest-neighbour, lossy). The demo's ad-hoc reproject-merge moved into
  `api._merge_outputs`; `demos/e2e_ethiopia.py` now calls `merge="reproject"`.
- **CDSE quota (SO-6):** ROI inference **never downloads from CDSE** — imagery is assumed present
  in the catalog (download is a separate up-front phase). On cloud (P4) this means Batch tasks read
  imagery from blob, never CDSE.

## Datacube builder: merge multiple tiles per acquisition (spec 20 bugfix, 2026-07-07)
- **`datacube/builder.py::_stack_datacube`** — when a shape is covered by several tiles of the
  **same acquisition** (it straddles an MGRS tile boundary), all of them are now **nodata-fill
  merged** onto the reference grid. Previously `ts_band_index` was a `dict((timestamp, band) ->
  image_index)`, which silently kept **one** tile and nodata-filled the shape's other portions —
  a faithfully-ported legacy bug (see `BUGS.md` BUG-002). Overlap tie-break: `dst_crs`-native
  tiles win over reprojected ones, then lower `image_index`.
- **Behavior change:** boundary-straddling shapes (e.g. the 5 km inference grids) now get full
  coverage instead of partial/mostly-nodata (worst spec-19 grid: 0.6 % → 82.8 % valid).
  Small single-tile shapes are largely unaffected (one image per `(timestamp, band)` → the merge
  is a no-op), but a **minority of training fields do straddle boundaries** — the spec-19 demo's
  cold rebuild recovered ~6 % more training pixels (217,914 → 230,567) on top of rescuing the
  inference grids. Output shape/axes unchanged.

## ROI→S2-grid tiling + end-to-end demo (spec 19, 2026-07-06)
- **New `src/fsd/grid.py`** — `roi_to_s2_grids(roi, grid_size_km=5, scale_fact=1.1)`: clean-room
  port of `rsutils.s2_grid_utils.get_s2_grids_gdf` (polyfill the ROI's convex hull at S2 res 11,
  keep intersecting cells, scale 1.1 for 10 % overlap, `gpd.overlay` clip to the ROI). `s2`+`s2cell`
  live in the optional **`[grid]`** extra so fsd core stays lean. This is the ROADMAP §4 / P4
  groundwork; the `run_inference(roi=…)` front-end that consumes it is still P4.
- **`demos/`** — `e2e_ethiopia.py` runs demo_01+02+03 as one flow (tiling → `create_training_data`
  → RF → inference datacubes → `run_inference` → COG/STAC + a crop map) on the existing Ethiopia
  data; `adapters.py::DemoRF` (NDVI+SAVI, band-limited to what the benchmark has); `README.md` is
  the report. Runs in an **isolated `.venv-modeldeploy`** (`[dev,grid,model-example]`).
- **Real finding:** the inference ROI straddles the S2 MGRS zone-36/37 boundary in practice, so
  per-grid datacubes land in **both** EPSG:32636 and 32637. `run_inference(merge=True)` refuses the
  cross-CRS merge (the single-CRS-merge principle, spec 18); the demo reprojects outputs to the
  **dominant** zone and mosaics that for the display map.
- New extras: `[grid]` (s2, s2cell); `matplotlib`/`seaborn` added to `[model-example]` for the plots.

## ModelAdapter contract + local train/deploy (spec 18 / P0.5, 2026-07-06)
- **New `src/fsd/model/`** (`adapter`/`features`/`engine`/`bundle`) generalizes the legacy
  `demo_02_model_train` + `model/demo_model_deploy.py` into a plug-in **ModelAdapter** contract.
  The feature transform (`mask_invalid_and_interpolate → NDVI/NDRE/… → remove raw bands`) that
  was **copy-pasted** between the train notebook and the deploy script now has **one** definition
  (the adapter's `feature_sequence`), run by fsd in **both** `create_training_data` and
  `run_inference` — the F1 anti-skew fix.
- **`create_training_data` wiring:** the previously-stubbed `feature_sequence`/`aggregate` params
  are live, plus a new `adapter=` (preferred). When any is given, fsd writes `features.npy`
  (+ `feature_ids`/`feature_labels`) **additively**; raw `data.npy` is kept. `aggregate ∈
  {None, "median_per_id", callable}` (the `np.nanmedian`-per-id reducer from demo_02 cell-3).
- **`run_inference` is real (was a P4 stub):** local engine over **pre-built inference datacubes**
  (input.csv / folder / list) → one COG per cube + a STAC catalog (+ optional merged map). fsd
  owns the predict loop (drop-NaN → chunked `predict` → nodata scatter → `(bands,H,W)`). Output
  COGs use **`raster.cog.to_cog`** (lossless + overviews) — **not** the legacy `rio_cogeo`/
  `cog_translate` path (see DROPPED.md). The ROI→S2-tiling front-end stays P4 and will call this
  same engine. Preflight asserts bands + `T` before any predict.
- **`catalog.stac.cog_outputs_to_items`** implemented (spec 17 SO-6, was designed-for): one STAC
  Item per output COG, `proj:*` read straight from the COG we just wrote.
- **Bug fixed:** `engine.infer_datacube` now **copies `band_indices`** before `modify_bands`,
  which mutates its `band_indices` argument in place — reusing one dict across cubes could
  otherwise corrupt it (caught by `test_predict_batch_size_matches_whole_tile`).
- **Deps:** no new *core* dep (sklearn/joblib live in the `[model-example]` extra for the example
  + runbook only). Exports: `fsd.ModelAdapter/BaseModelAdapter/Output/load_bundle/save_bundle`.

## STAC export view of the tile catalog (spec 17 / P0, 2026-07-06)
- **New (additive), `TileCatalog` GeoParquet schema unchanged:** `src/fsd/catalog/stac.py` maps
  catalog rows → **STAC Items** (one Item per tile-product acquisition, one asset per band file)
  and writes a **static, self-contained STAC catalog (JSON)** via `pystac`, through the
  `fsd.storage` seam. `TileCatalog.to_stac(dst)` is the convenience entrypoint.
- **Pure-metadata by default:** `proj:code` (EPSG) is derived from the **MGRS tile in the product
  id** (e.g. `T37PBP`→`EPSG:32637`), so `to_stac` reads **no rasters** (579-tile benchmark → 579
  items in 0.06 s, both UTM zones correct). Per-asset `proj:shape`/`proj:transform` are opt-in
  (`read_proj=True`). Media types by extension (COG for `.tif`); `eo:cloud_cover` from
  `cloud_cover`; `MTD_TL.xml` as a metadata asset; source `.SAFE` as a `via` link.
- **Round-trippable:** `stac.items_to_rows(...)` reconstructs the catalog columns losslessly.
- `pystac` promoted to a **direct** dependency (was transitive via `pystac-client`).
  `stac-geoparquet` deferred (add when pgstac/TiTiler needs it). Advances TODO #14 (STAC half).

## High-level API façade — `fsd.*` verbs (spec 16 / P0, 2026-07-06)
- **New (additive), no behavior change to existing modules:** `src/fsd/api.py` adds the
  user-facing verbs `fsd.download`, `fsd.create_training_data` (+ `run_inference` / `deploy`
  stubs, `compute_n_timestamps`, `TrainingData`, `PreflightError`), re-exported at top level so
  `import fsd; fsd.create_training_data(...)` works. It is a **façade** over
  `sources.cdse` / `workflows.create_datacube` / `datacube.flatten` — the legacy-derived
  entrypoints (`run_create_datacube`, `flatten`) are unchanged and still public.
- **Scope raised (ROADMAP §2.5):** `create_training_data` hides `input.csv` + the word
  "flatten"; the user provides label polygons + a catalog and gets back
  `data/ids/labels/coords/metadata`.
- **Seams present from day one:** every verb takes `runner="local"` / `storage=None`; non-local
  values raise (Azure Batch / blob land in P1/P2 as config, not API changes).
- **Preflight (ROADMAP §2.6):** cheap checks (window/`T`/bands/columns/catalog) run *before*
  any download or build and raise `PreflightError`, aggregating all failures.
- **`feature_sequence` / `aggregate`** are pinned in the `create_training_data` signature but
  raise `NotImplementedError` until P0.5 (ModelAdapter). Version bumped `0.0.1 → 0.1.0`.

## Calendar-interval median mosaic — new default (spec 15, 2026-07-05)
- **Behavior change (kept-but-changed): `median_mosaic` now buckets acquisitions into fixed
  calendar windows by default** (`mosaic_scheme="calendar"`, `config.MOSAIC_SCHEME`). Windows are
  `[startdate + k·mosaic_days, …)` over `[startdate, enddate)`; **labels are window-start
  boundaries** (not the first acquisition date); **empty windows are emitted as all-nodata slices**.
  So every datacube built over the same `startdate`/`enddate`/`mosaic_days` has an **identical
  `timestamps` axis regardless of tile/orbit/UTM zone** — which is what lets `flatten` (spec 05)
  concatenate cubes across a multi-tile training set. `mosaic_scheme="acquisition"` restores the
  exact legacy labeling (first-acquisition labels, occupied buckets only, gap-opens-interval quirk).
- **Resolves the TODO #2 anchor caveat.** The workflow `create_datacube.setup` now threads the
  **caller's calendar `startdate`/`enddate`** into each work-unit's mosaic anchor (the per-shape
  actual acquisition min/max is kept only for the run-folder name). Previously it threaded the
  actual first/last acquisition, so windows shifted shape-to-shape.
- **Threading:** `mosaic_scheme` added to `build_datacube`, `workflows.task` (`--mosaic-scheme`
  CLI, default from config), `create_datacube.setup`/`run_create_datacube` (+ an `input.csv`
  column), and the bundled Snakefile. Boundary rule is half-open `[lo, hi)` (a timestamp on a
  boundary lands in the later window; the final window is upper-inclusive so a timestamp exactly at
  `enddate` isn't dropped) — differs from legacy's `<=` walk only for an on-boundary timestamp.
- **Ripple:** mosaic timestamp *labels* change (calendar boundaries), but the pixel groupings /
  medians for a dense window are unchanged, so `datacube.md`'s numeric NDVI references still hold;
  the runbook carries a note. Legacy outputs are reproducible via `mosaic_scheme="acquisition"`.
- **Known limitation logged (TODO #16):** `flatten` concatenates per-cube `coords.npy` but a
  multi-zone training set mixes eastings/northings from different UTM zones (west→32636, east→32637)
  — fine as pixel identifiers, wrong if used spatially. Not fixed here.

## satellite_benchmark migrated JP2 → COG in place (spec 14 follow-up, 2026-07-04)
- **Data change (not code):** the real test archive `satellite_benchmark/` was converted from
  native JP2 to **COG (+ overviews), in place** — every `Bxx.jp2` → `Bxx.tif`, the `.jp2` deleted
  (no duplicate copies), and its `catalog.parquet` `files` column rewritten to `.tif`. 2316 band
  files, 0 failed, lossless (bit-identical verified); archive grew 94 → 159 GiB (COG+overviews ≈
  1.70× JP2). Downstream is unaffected — rasterio reads `.tif` transparently, so datacube builds /
  throughput runs work unchanged (they now read COG, i.e. faster; see the throughput runbook note).
- **New tool `benchmarks/migrate_jp2_to_cog.py`** (reusable): in-place JP2→COG migrator built on
  `fsd.raster.cog.to_cog`. Resumable (skips already-`.tif`), disk-safety floor (aborts before free
  space hits `--floor-gib`), live progress bar + ETA, catalog resynced from actual on-disk state,
  and a `--verify {full,quick,none}` pre-delete gate (default `quick` = readback + shape/dtype +
  overviews check; `full` re-decodes for bit-identical). Conversion is memory-bandwidth-bound → 8
  workers (the perf cores) is the knee; 10 gave no gain.

## COG-on-download — native ingest format (spec 14, 2026-07-04)
- **Behavior change (kept-but-changed): `sources.cdse.download` now converts each fetched JP2
  band to a lossless COG by default** (`cog: bool = True`). On-disk band files are `Bxx.tif`
  (was `Bxx.jp2`) and the catalog `files` column records `.tif`. `cog=False` restores the exact
  prior behavior (native `Bxx.jp2`). Turns the spec-13 finding (COG builds 1.58×–3.46× faster,
  lossless) into the ingest default so downloads are build-fast from the start.
- **COGs carry overviews** (`OVERVIEWS="AUTO"`) for the future TiTiler XYZ/WMTS goal (TODO #14).
  The datacube build reads full-res and never uses them; they cost ~+38% on top of base COG (so
  ingest COGs are ~1.7× JP2 storage — a deliberate tiling-readiness cost, not a build cost).
- **New `src/fsd/raster/cog.py::to_cog`** — one canonical local raster → COG primitive: lossless
  (DEFLATE + PREDICTOR=2; `NBITS=16` promotes S2's declared 15-bit depth so PREDICTOR=2 is legal —
  pixels unchanged), **atomic** (`.part` + `os.replace`, mirroring `storage.transfer`), optional
  overviews, optional `verify` (bit-identical read-back). COG profile constants live in `config`.
- **Download flow:** a band is fetched to a local staging sibling (`Bxx.tif.src.jp2`) via
  `storage.transfer`, converted with `to_cog`, staging removed; `MTD_TL.xml` transfers as-is.
  Idempotency keys on the final `.tif`; a crash leaves at most the staging JP2 (atomic convert),
  so resume re-fetches cleanly. Conversion runs inline in the existing S3 worker threads (GDAL
  releases the GIL) — a dedicated conversion process pool is a noted future optimization.
- **Seam boundary:** `cog=True` requires a **local** `root_folderpath`; a remote (`s3://`/`az://`)
  dst raises a clear error (the stage-local→convert→upload path is deferred to the Azure milestone).
- **`benchmarks/prep_cog_dataset.py` refactored** to delegate its conversion to `to_cog` (one
  source of truth for the COG profile); behavior identical (it still pins `OVERVIEWS="NONE"`).
- The read/build/datacube/workflow path is untouched — rasterio reads `.tif` transparently (spec 13).

## COG vs JP2 storage/time experiment (spec 13, 2026-07-04)
- **New (no legacy equivalent), no `src/fsd/` change:** measures what storing S2 tiles as
  **COG** vs native **JP2** buys in build time and costs in disk. Three additive benchmark
  scripts + harness CLI knobs; the read path is already format-agnostic (rasterio detects
  JP2/GTiff), so the switch is pure data + catalog.
  - `benchmarks/prep_cog_dataset.py` — converts the first N months of `satellite_benchmark`
    JP2 → **base COG** (DEFLATE + PREDICTOR=2, tiled 512, **no overviews**) into a mirror tree
    `satellite_benchmark_cog/` + a parallel `catalog.parquet`. Lossless: `NBITS=16` promotes S2's
    declared 15-bit depth (in a uint16 container) so PREDICTOR=2 is legal — pixel values
    unchanged; a bit-identical assert guards it. Includes a **disk pre-flight** (sample-estimate +
    free-space check, aborts before writing) and live progress/ETA. Emits `cog_vs_jp2_storage.md`
    (JP2 → base COG → COG+overviews, overview row estimated from a sample).
  - `datacube_throughput_sweep.py` gained **`--catalog` / `--start` / `--end` / `--tag`** so the
    Part-1/2 harness A/Bs JP2 vs COG with non-clobbering tagged outputs (report/stats/figures).
    Report image links now derive from `FIG_DIR` (tag-aware); added a `STATS` constant (replaces
    the fragile `FIG_DIR.replace("_figures", …)` derivation).
  - `benchmarks/compare_cog_jp2.py` — merges the two tagged `stats.json` + storage json into the
    team report `cog_vs_jp2_report.md`: time table, the **JP2-vs-COG duration-vs-concurrency
    overlay** (the decode-bound test), storage table, verdict.
  - Runbook `tests/manual/cog_experiment.md`. Measured on this data: base COG ≈ **1.23× JP2**
    (S2 JP2 barely out-compresses DEFLATE), overview delta ~+38%.

## Datacube throughput benchmark, Part 1 + `write_timings` seam (2026-07-03)
- **New (no legacy equivalent):** `benchmarks/datacube_throughput_sweep.py` — a reusable
  harness (spec 11 · Part 1) that sweeps build parallelism (`cores`) over the 100-grid ROI
  set and reports throughput + per-step timing + static grid×tile overlap. Baseline lives
  in `benchmarks/datacube_throughput_report.md` (+ `*_stats.json` for cross-run diffing).
- `datacube.builder.build_datacube` gained a **`write_timings: bool = False`** flag (off by
  default → no extra file in normal runs): when set, it writes a `timings.json` sidecar
  (per-phase wall-seconds + sizing counts) next to `datacube.npy`. The workflow enables it
  via the **`FSD_WRITE_TIMINGS=1`** env var (read in `workflows.task.main`), so the harness
  toggles it with zero runner/Snakefile plumbing. Phases are wrapped in a `_timed` ctx mgr.
- Read-path instrumentation (per-read parallel-reads / duration-vs-concurrency) is **not**
  here — deferred to Part 2 (spec 12); tile-splitting to Part 3 (spec 13).

## Datacube throughput benchmark, Part 2 — per-read instrumentation (2026-07-04)
- `datacube.builder.build_datacube` gained a **`write_read_log: bool = False`** flag (off by
  default → no extra file), mirroring `write_timings`. When set (and `njobs_load_images == 1`)
  it times each windowed read with **wall-clock `time.time()`** (comparable across grid
  processes) and writes a **`reads.jsonl`** sidecar next to `datacube.npy` — one row per read:
  `id` (grid), `mgrs_tile`, `product_id`, `band`, `filepath`, epoch `start`/`end`, `duration`.
  The workflow enables it via **`FSD_WRITE_READ_LOG=1`** (read in `workflows.task.main`). With
  `njobs_load_images > 1` the log is skipped with a `RuntimeWarning` (reads fan out to a Pool).
  The load loop was refactored: `_load_images` returns `(catalog_gdf, data_profile_list, reads)`
  and, on the logging path, reads each file serially via new `_load_images_logged`.
- `benchmarks/datacube_throughput_sweep.py` gained a **`--read-log`** flag (spec 12): it sets
  the env var, collects every grid's `reads.jsonl`, and computes **read conflicts** (overlapping
  read pairs from different grids), a **read-duration-vs-concurrency** curve (the direct test of
  the "parallel reads block each other" hypothesis), and a **same-file / same-tile / different-
  tile** classification — only *same-file* conflicts are what Part-3 tile-splitting can remove.
  Adds a "Read contention" section + 4 plots to the same living report and a `read_contention`
  block per `cores` to `stats.json`. Pure analysis (`conflict_stats`, `duration_vs_concurrency`,
  `_annotate_reads`) is unit-tested; `--read-log` is off by default so the baseline is unchanged.
- Concurrency is **instantaneous peak-in-flight** (bounded by `cores`), not overlap-degree — the
  metric the hypothesis needs. Tile-splitting itself stays deferred to Part 3 (spec 13).

## Workflows: task/runner split + fsd seams (2026-07-03)
- `workflows/create_datacube.py` + `setup_datacube_run.py` + the in-memory Snakefile →
  `fsd.workflows` as **task** (`task.py`, build one datacube, CLI `python -m
  fsd.workflows.task`) + **runner** (`runners.run_local`, drives the bundled Snakefile) +
  **entrypoint** (`create_datacube.run_create_datacube`: setup → runner). Same
  start.txt/done.txt sentinels + deterministic jitter.
- **Subset catalog is GeoParquet** (`catalog.parquet`) written via `TileCatalog.filter`
  (which already persists `area_contribution`), not legacy `catalog.geojson` + a separate
  `calculate_area_contribution` — the builder consumes the slice directly.
- **Task defaults `if_missing_files="warn"`** (legacy builder defaulted `raise_error`): at
  batch scale one partial-coverage shape shouldn't abort its job.
- **Snakemake and the task are invoked via `sys.executable -m …`** (not bare `snakemake`
  / `python`), so the workflow runs regardless of PATH / venv activation and the task
  always runs in the same interpreter as the runner.
- CLI passes `--bands` / `--scl-mask-classes` as **comma-strings** (single tokens) rather
  than legacy space-separated `nargs` (simpler Snakemake shell quoting).
- Added `storage.fs.rm` (delete through the seam; used to overwrite `input.csv`).

## Datacube builder: missing-band nodata fill shape (2026-07-02)
- Legacy `create_datacube_inmemory_single` filled a missing `(timestamp, band)` with
  `np.full((height, width), 0)` — a **2-D** array, while present bands are **3-D**
  `(1, H, W)` (rasterio single-band read). `np.stack`-ing them together would raise a
  shape error, and the fill defaulted to `float64` (promoting the whole cube). `fsd`
  fills with `(1, H, W)` in the present bands' dtype so the stack actually works.
- **Why it never bit legacy:** with `if_missing_files='raise_error'` (the default),
  any partially-missing band raises *before* stacking, so the buggy branch was
  unreachable. `fsd` fixes it so `warn`/`None` modes produce a valid cube. Same
  `datacube.npy` output on the complete-data path.

## Discovery: STAC API instead of Sentinel Hub (2026-07-01)
- Legacy discovered tiles via `sentinelhub.SentinelHubCatalog` (SH OAuth creds) and
  then listed each `.SAFE` over **S3** to find band files. `fsd` instead queries the
  **CDSE STAC API** (`pystac-client`, anonymous) and reads each item's `assets` to
  get the **per-band S3 hrefs directly** — no SH creds, no S3 listing.
- **Why:** the S3 `.SAFE` listing failed intermittently (`SignatureDoesNotMatch` /
  `InvalidAccessKeyId`) — a CDSE server-side issue (BUG-001). STAC sidesteps it; the
  only remaining S3-auth op is the per-file byte `transfer`, wrapped in fail-fast
  retry. Discovery no longer needs credentials at all.
- **Behavioral parity:** same catalog columns (`id, timestamp, geometry, s3url,
  cloud_cover`), same highest-res-per-band + `MTD_TL.xml` selection, same flattened
  on-disk layout. Note: STAC `item.id` has **no `.SAFE` suffix** (SH ids did); the
  `s3url` still carries `.SAFE`.

## Structure
- Three repos (`fetch_satdata` + `rsutils` + `cdseutils`) → one `src`-layout
  package `fsd` with functional modules: `sources/ catalog/ datacube/ bands/
  raster/ workflows/`.
- `cdseutils.*` → `fsd.sources.cdse` (+ shared bits in `fsd.config`).
- `rsutils.modify_images` (+ raster helpers from `rsutils.utils`) → `fsd.raster.images`.
- `rsutils.modify_bands` → `fsd.bands.modify`.
- `fetch_satdata.datacube.create_datacube_inmemory_single` → `fsd.datacube.builder`.
- `fetch_satdata.core.datacube_ops` → `fsd.datacube.ops`.
- `fetch_satdata.datacube.datacube_flatten_2d` → `fsd.datacube.flatten`.
- `fetch_satdata.workflows.create_datacube` + `setup_datacube_run` → `fsd.workflows.create_datacube`.

## Behavioral
- Catalog is the single file-based store (**GeoParquet**); the in-memory datacube
  builder reads it directly. No SQLite, no separate datacube/config DBs.
- Datacube builder is exposed behind a stable `build_datacube(...)` seam so an
  alternate engine (e.g. `rslearn`) can emit the same artifacts.
- **All file I/O via `fsspec`** (`fsd.storage`) — local in v1, Azure Blob / S3
  additive. No module touches raw paths directly.
- **S3 download generalized**: legacy's CDSE-private `boto3` download → a first-class,
  provider-agnostic S3 transport in `fsd.storage` (fsspec/`s3fs`, any `endpoint_url`:
  AWS, CDSE EODATA, MinIO…). CDSE keeps only STAC discovery + S2 file-selection. No
  direct `boto3`.
- Datacube creation restructured into **task + runner seam**: Snakemake becomes the
  *local* runner; the datacube task is CLI-invokable and runner-agnostic so an Azure
  Batch runner can dispatch it unchanged (Phase 2).
- CDSE catalog-query disk cache **removed** (always query live).
- Python floor raised 3.10 → **3.11**.
- Plotting / sklearn moved out of core into notebook extras.
- **`raster.images` parallel helpers run serially when `njobs == 1`** (no
  `multiprocessing.Pool`), instead of legacy's always-Pool. Same results; usable
  inside tests/other already-parallel contexts and avoids pickling/process
  overhead for the common single-job case. `njobs > 1` still uses a Pool.
- **`raster.images.reproject` now guards its output fill against `nodata=None`**
  (falls back to 0, matching the guard `resample_by_ref_meta` already had);
  legacy `reproject` would build an all-None-filled array if `nodata` was unset.
- `raster.images` follows the locked in-memory `(data, profile)` op convention for
  `crop`/`reproject`/`resample_by_ref_meta`/`merge_inplace` (the spec-phase scaffold
  had sketched some as file-in/file-out; corrected to match what the datacube
  builder actually chains via op `sequence`s).
- `bands.modify` carries only the demo-path ops (`modify_bands`,
  `mask_invalid_and_interpolate`, `compute_bands`, `remove_bands`, `scale_bands`) plus
  `expand_datacube`/`expand_flattened`. The `mask_interpolate` numba kernel that
  `mask_invalid_and_interpolate` needed (was in `rsutils.utils_preprocess`) is folded
  in as a private helper. All spectral indices from the legacy table are kept
  (NDVI/NDRE/GCVI/SAVI + NDWI/LSWI/BSI/PSRI/NDTI). Off-path ops deferred — see
  DROPPED.md (`median_mosaic`, `sav_gol`, `trim_bands`, `modify_bands_chunkwise`,
  preprocess-log (de)serialization).

## Kept identical (intentionally, for notebook portability)
- Datacube artifact format: `datacube.npy` + `metadata.pickle.npy` and the
  metadata dict keys.
- Flattened-data artifact set: `data.npy / ids.npy / labels.npy / metadata.pickle.npy`.
- 5-D band-array contract for `bands.modify`.
- Default bands, `scl_mask_classes`, `mosaic_days`, reference band B08, nodata 0.
