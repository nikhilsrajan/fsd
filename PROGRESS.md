# PROGRESS — fsd

**Resume anchor.** Read this, then `specs/00-overview.md`. Older entries moved to
[`docs/progress-archive.md`](docs/progress-archive.md) (spec 41 D12) — this file is the *current*
state plus the most recent entry, not the log.

_Last updated: 2026-08-28 (**#92 DONE, CLOSED + PUSHED — `main` @ `ee7277b`, clean.** The AZ_ROOT
cleanup landed (`3a968dc`, merged `--no-ff` as `ee7277b`; worktree pruned, branch deleted). Three
files, five edits, **no code**: `docs/howto/run-at-scale.md` (its "all six values `fsd init` asks
for" prerequisite → five required + two optional registries, with the storage root explicitly not
among them; the `runner_kwargs` block now labelled as an argument dict), `docs/reference/environment.md`
(the `root` paragraph names every non-reader — `fsd init` does not prompt, `fsd config` does not
print, `--from-env-file` parses and drops it, `tests/test_cli.py:58` — and every actual reader; a
duplicated `fsd config` paragraph dropped; "six values" → seven keys), and
`notebooks/e2e_austria_aml.ipynb` markdown cell 0, which said the model registry lives at
`$AZ_ROOT/model_registry` and so contradicted **code cell 3 of the same notebook** and spec 55 D2.
`1068 passed / 99 skipped`, ruff clean — baseline unchanged. **Two reported defects were not
defects:** `run-at-scale.md:51` is `runner_kwargs`, and `runner_kwargs["root"]` is a **required
argument** (`src/fsd/api.py:499-501`) — reframed, not deleted, since removing it would have broken
the example; and `demos/e2e_austria_aml.py` + `demos/E2E_AUSTRIA_AML.md` already read `AZ_ROOT`
from the environment as a per-run root. A mention is not a defect. **Still stale, out of scope:**
`rise/docs/environment.md` in the consumer repo carries the old framing — fix it when that repo is
next touched, i.e. during step 2. **NEXT: step 2 of THE ORDER below, the consumer-repo run — the
user's to run, not an agent's** ([[real-run-beats-review]], CLAUDE.md's "Claude never runs
pipeline/networked scripts")._

_Previously: 2026-08-28 (**SPEC 57 LANDED; `notebooks/shapefiles/` NOW PUBLIC WITH A NOTICE;
`main` @ `e4879b0`, pushed, clean.** Since the entry below: the user un-ignored
`notebooks/shapefiles/` themselves (`16b66f6` — 900 EuroCrops-derived Austrian fields + the two
demo geometries + a scrubbed `00_build_images.ipynb`, so critical-path item 2 is **done**), and a
`NOTICE` was added beside them (`e4879b0`) recording provenance and stating plainly that the
**upstream EuroCrops licence has NOT been reconciled with this repo's MIT licence** — it grants
nothing fsd cannot. Nothing reaches the wheel (`packages.find` is `where=["src"]`). The canonical
EuroCrops citation URL is deliberately **absent** from the NOTICE: it needs a lookup nobody has
done. **NEXT: issue #92, handed off to a fresh Opus session** —
`/tmp/handoff-issue-92-az-root-2026-08-28.md`. The ordered chain it must not drop is directly
below.)_

## THE ORDER — four tasks, and what follows each (user, 2026-08-28)

The user's standing instruction: **record what comes after finishing a task, so it is not
forgotten at the boundary.** Do not reorder without saying so.

| # | task | done when | → then |
|---|---|---|---|
| ~~**1**~~ | ~~**[#92](https://github.com/nikhilsrajan/fsd/issues/92)** — AZ_ROOT cleanup~~ | **DONE 2026-08-28** — `3a968dc` / `ee7277b`, issue closed + pushed | → **2**, now current |
| **2** | **The consumer-repo run** — reinstall `rise/.venv` from `@main`, run `rise/notebooks/e2e_austria_aml.ipynb` end to end | `[collect]`/`[stac]` numbers captured against the **616 s / 161 s** baseline, and spec 56 §9 step 10's forced stale-entry rebuild checked | → **3**; also **unblocks #80 + #82** (see the rider below) |
| **3** | **[#55](https://github.com/nikhilsrajan/fsd/issues/55)** — docs refactor (story + C4 set) | its own gate is step 2's timed report; **needs its OWN spec and a discussion before starting** | → **4** |
| **4** | **[#85](https://github.com/nikhilsrajan/fsd/issues/85)** — trim the changelog out of `src/` comments | 7 packages left, **one per session**; `storage/` is the done sample (`eb7f29f`) | → the next spec / ROADMAP |

**Rider on step 2 — do not lose these.** #80 (snakemake → `[local]`, s3fs → `[s3]`; zero code
change, −53 packages / −111 MB) and #82 (cut + push `v0.1.0`) both belong **inside** `v0.1.0`, and
the **tag is LAST** — cut only once the consumer notebook actually runs (user, 2026-08-26: a tag
pins the dependency set *and* the asset layout, and both were still moving). #80 may land any time
before the tag; it cannot alter runtime behaviour, so it does not require re-running step 2.
**#79** is wanted-not-blocking; **#81 must not block** (numba is a real top-level import).

**Why #92 goes first, not after the run:** it edits `notebooks/e2e_austria_aml.ipynb`'s prose and
`docs/howto/run-at-scale.md`'s config example — cheaper to fix before the run than to re-touch a
notebook that has just been validated.

_Previously: 2026-08-27 (**SPEC 57 IMPLEMENTED (Sonnet) + REVIEWED (Opus) + MERGED + PUSHED —
`main` @ `52f7b2b`.** D1 (segment ticker) + D2 (in-memory footprint, ROI mode) + D5 (GDAL
sidecar-probe config) + D3 (threaded collect) + D4 (threaded STAC writes) all landed; worktree
`spec-57-collect-stac` merged `--no-ff`, then pruned and its branch deleted (standing practice).
`1068 passed / 99 skipped`, ruff clean. **Review found one real bug** (commit `e745a57`): D5's
`CPL_VSIL_CURL_ALLOWED_EXTENSIONS` is a GDAL *whitelist*, not a hint — a remote file whose
extension is not listed reads as **non-existent** — so `.tif` alone would have made remote `.jp2`
and `.tiff` band files unopenable (`datacube.builder._RASTER_EXTS`; any `cog=False` imagery staged
on blob). Widened to `.tif,.tiff,.jp2`, with a test tying the whitelist to `_RASTER_EXTS`. Review
also added AC2's missing **caller-side** test (nothing asserted `_run_inference_roi` builds the
in-memory mapping at all) and made the byte-identity test `.buffer(0)` both sides. The
implementer's three other flags resolved as non-issues: `.buffer(0)` parity holds (grids are
EPSG:4326, `grid.py:112`, and `to_json()` does not reproject); D3's and D4's pools run strictly in
sequence, so never more than 16 threads are live; `as_completed`'s exception ordering satisfies
AC5. **NEXT: §9 step 5 — a real cluster run against the pre-D1 baseline.** It is the user's, not
an agent's ([[real-run-beats-review]]), and until it happens the 777 s → <100 s number is a
*hypothesis*. Spec 56's §9 step 10 real AML run is also still outstanding, unrelated.
[The `00_build_images.ipynb` leak-guard warning recorded here was resolved by the user in
`16b66f6`.])_

**Spec 57 — LANDED 2026-08-27** (signed off, implemented, reviewed, merged).
`specs/57-collect-and-stac-round-trips.md`, advancing [#61](https://github.com/nikhilsrajan/fsd/issues/61)
(closes its fixes (b) and (c); (d), node-side Item emission, stays open). Origin: the user watched a
real AML run and asked what the gap between `[collect]` and `[merge]` was. Answer, from #61's
segment measurement: **collect 616 s (2.05 s/cell) + STAC writes 161 s (0.53 s/item)** on 300
cells — it scales with the number of output cells, not with the work, and that run's inference had
already been skipped. Five decisions, in build order: **D1** print segment timings *first* (#61's
original suspect was a "627 s bundle upload" that measurement showed to be 13 s — do not optimise
blind); **D2** stop re-reading each cell's `geometry.geojson`, because those footprints are the
`grids.geojson` the driver itself wrote and still holds (~300 s, no threads); **D5** two GDAL
options to stop sidecar probes on every remote open; **D3** thread the COG opens; **D4** thread the
301 Item writes.

**The finding worth carrying forward: #61's own fix guidance was wrong, and the spec corrects it.**
#61 says to thread the metadata reads *"under a single `raster.rio_env`, since GDAL's env stack is
thread-local"*. Thread-local means the **opposite** of that conclusion — rasterio 1.4.4 keeps the
active env in `local = ThreadEnv()` (`rasterio/env.py:56`), so an `Env` entered on the driver
thread does not exist in a worker. Proved by direct execution, not by reading: `hasenv()` is
`True` in the main thread and `False` in the worker. Since `rio_env` is what carries
`AZURE_STORAGE_ACCESS_TOKEN`, following #61 literally would have had every worker open a remote COG
with **no credential**. Each worker enters its own env (D3). Instance of
[[verify-the-primitive-a-spec-cites]].

**Also rejected, with arithmetic (spec 57 §6):** running the STAC write and the merge concurrently
(the user's suggestion). They are independent in output but bottlenecked on the same link, so the
ceiling is `max(stac, merge)` = 777→616 s against D2–D5's 777→<100 s, it buys nothing on the common
`merge=False` run, and it adds a half-written catalog beside a failed merge.

**Not spec 57: [#77](https://github.com/nikhilsrajan/fsd/issues/77).** The same run felt slow for a
second, independent reason — inference *is* deduped, but on the node after dispatch, so a
95%-complete re-run still starts ~299 tasks to discover it needs ~15. That wants its own short
spec, mainly to settle presence-vs-stamp for the output skip.

**Read before touching either:** `specs/55-root-leaves-the-config.md`,
`specs/56-image-definitions-and-registry.md`. Both carry their sign-off resolutions in §7,
including **two decisions the user killed** (a note for a stale `root` key; a skip line for
`AZ_ROOT` in `--from-env-file`) — do not re-propose them.

**Spec 55 — DONE (merged).** `root` is no longer a config key: it names a *per-run destination*
chosen by whoever runs the job, not a durable address, so the caller passes it — spec 41 D7's
"takes a storage location as an argument" applied to the last value that escaped it.
`load(root=…)` raises `TypeError` on purpose, because that is the mistake a spec-54-era caller
makes. In the other direction, **`model_registry` + `image_registry` arrive as OPTIONAL keys**
(`AZ_MODEL_REGISTRY` / `AZ_IMAGE_REGISTRY`), so `load()` now splits required from optional: a
missing required key still raises `MissingConfig` naming every gap at once, a missing optional one
is `None`. **fsd's own signatures still take `registry=` as an argument, always** — the keys exist
because the two tracked notebooks are leak-guarded and may not hold a literal `abfss://` URL, and
the concrete values belong in `rise` + `AZURE_INFRA_PRIVATE.md`, never in this repo. Also
`fsd init --blank` (write it empty, fill it in by hand; refuses to clobber without `--force`) and
a non-tty `fsd init` that names the three non-interactive forms instead of raising `EOFError`.

**Spec 56 — IMPLEMENTED in a worktree, §9 steps 0-9 done, step 10 (the real AML run) still
outstanding.** `fsd/registry/_core.py` (step 0) took the **copy fallback, not extraction**: §7 Q1
recommended extraction, but `tests/test_registry.py` monkeypatches `registry._list_versions` /
calls `registry._write_new_version` directly, which only works if those functions stay defined in
`fsd/model/registry.py`'s own namespace — a real move-and-reexport would leave the closures
resolving against `_core`'s globals instead and silently break the patches. So `fsd/model/registry.py`
is **byte-for-byte untouched** (`git diff` confirms it), and `fsd/registry/_core.py` is a
parameterized copy the new image registry builds on — exactly the fallback the guard rail names.
`fsd.image.ImageDefinition` (D1), `fsd.image.digest.resolve`/`digest` (D2 — resolution injectable
for tests, no network in the suite), `fsd.image.registry` (D3, on `_core`), `fsd.aml.environment`
+ `fsd.aml.ensure_environment` (D4, `az` calls behind an injectable seam), `verify_image`'s
`image_ref=`/`registry=` path (D8, spec 47's own tests green and unmodified), the rewritten
`00_build_images.ipynb` (D7, 11 cells vs the old 22) and the deleted
`notebooks/images/{base,sklearn}/` (step 8, rendered-Dockerfile diff confirmed equivalent before
deletion, `DROPPED.md` diff confirmed byte-identical modulo comments/blanks, entry written) are all
done. **Not done: a real AML run** (§9 step 10 — MEMORY `real-run-beats-review`); `main` is merged
but **unpushed**.

**Spec 56 — OPUS REVIEW, 2026-08-27. Eight defects found and fixed in the worktree; suite now
`1053 passed / 98 skipped`.** Verified-as-claimed first: `src/fsd/model/registry.py` is untouched
and the step-0 copy fallback is genuinely forced (`tests/test_registry.py:534` patches
`registry._list_versions` then calls `registry._write_new_version` — a move-and-reexport defeats
it), and the rendered Dockerfiles were re-diffed against `git show main:` rather than eyeballed.
What was wrong:

1. **A rebuild loop, the worst of the seven.** `publish` is idempotent by digest, so rebuilding an
   *unchanged* definition (D4 step 3's deleted asset, or `force=True`) allocated no new version and
   dropped the new AML version on the floor — the registry kept naming the asset that had just been
   replaced, so every later `ensure_environment` found it missing and rebuilt a 10–20 minute image
   again, forever. Reproduced end-to-end before fixing. Fix: **`_aml.json`**, a staged-and-renamed
   mutable sidecar beside the immutable `image.json` — the role `_deploy.json` plays in
   `fsd.model.registry` (spec 51 D7). **This amends D3's layout and wants the user's blessing.**
2. **Two version sequences, silently swappable.** AML versions *assets*, the registry versions
   *definitions* — `fsd-aml-env:5` in AML is routinely `:1` in the registry, and
   `verify_image(image_ref=)` can only resolve the latter. `EnsureResult` now carries
   `registry_version`/`registry_ref` alongside AML's `version`/`ref`; the howto and RECIPES had the
   wrong one and are corrected.
3. **Spec 56 D1's own example raised.** `git ls-remote` matches ref *names*, not object ids (exit 0,
   empty stdout for a sha), so `fsd="git+…@9a00f2b"` died with an empty error message. Abbreviated
   shas (7–40 hex) are now kept verbatim; the not-found error says what it means.
4. **The digest described a different wheel than the image got.** `resolve()` built one wheel in a
   throwaway tmpdir and `write_context()` built a second — two `pip wheel` runs per image, and an
   edit between them makes the registry record a digest the image does not have (§5's *worse*
   direction). One shared directory now, one wheel.
5. **`--no-build-isolation` was a sandbox artifact in library code** — kept as the first attempt
   (it is what keeps the wheel test offline, AC8) with a retry without it for a 3.12+ venv.
6. **Two D8 edges**: a non-GitHub `git+` URL mis-fetched a `raw.githubusercontent.com/https://…`
   404 instead of saying the gate only reads GitHub; the "any non-`git+` ref is trusted" hole is now
   documented as a hole to close before fsd ships on PyPI (#82).
7. **`e2e_austria_aml.ipynb` was left behind and broken** — it pointed `INFER_BUILD_CONTEXT` at the
   deleted `notebooks/images/sklearn/`, and its "paste the versions from Part C" cell contradicted
   D7, `00`'s new Part C and `CHANGES.md`, all three of which claimed the paste was gone. **Edited
   on the user's explicit say-so (2026-08-27):** it now declares the same two `ImageDefinition`s,
   calls `ensure_environment` against the same registry, **asserts `reused`** (a fresh build means
   an ACR run just started and nothing below it can work — a gate the pasted numbers never gave),
   and uses `image_ref=`/`registry=` for `verify_image`.

8. **A test that was green only by import order.** `test_docs.py::test_doc_snippets_use_real_fsd_attributes`
   resolves `fsd.aml.<x>` in a doc as `hasattr(fsd, "aml")` — and a *submodule* is not an attribute
   of its package until something imports it, so the new howto passed the full suite (where
   `tests/test_aml_*.py` had already imported it) and failed `pytest tests/test_docs.py` on its own.
   The test now asks the import system instead of `hasattr`. **Worth remembering as a class:** run a
   new test module, and the modules a change touches, in isolation as well as in the suite.

Still open, both deliberate: **the real AML run** (§9 step 10), which also verifies the one thing
review cannot — `_default_resolve_base_digest`'s HEAD against a live `mcr.microsoft.com` (its
`Accept` header was missing the manifest-list/OCI-index types a multi-arch tag needs; added, still
unverified) — and **AC6's `abfss://` round-trip**, which has no manual-runbook entry yet.

**Also this session:** [#92](https://github.com/nikhilsrajan/fsd/issues/92) filed for the wider
`AZ_ROOT` tidy-up (deferred by the user, a later Opus job). And a standing rule was recorded, in
MEMORY and in #92: **run-books are point-in-time and are not a design input** — the user,
2026-08-27, *"we do not prioritise being able to run the runbooks. we do not make decisions so that
the runbooks are still compatible."* Spec 55 D3's rationale was rewritten to drop exactly that
argument; the surviving reason for reading `AZ_ROOT` from the environment is the notebook leak
guard, which is a real constraint.

**One trap recorded in `RECIPES.md`:** the worktree PYTHONPATH parity recipe **necessarily** fails
`tests/test_bundle_code.py::test_installed_adapter_is_not_embedded` — `bundle._installed_roots()`
reads the *running interpreter's* `site.getsitepackages()`, and a `PYTHONPATH` entry is
deliberately not a site directory, so `joblib` classifies as `bundled`. Verified by running that
test in the repo checkout with the repo venv, where it passes. **Any other failure under that
recipe is real.**

---

_Previously: 2026-08-26 (**SPEC 54 IMPLEMENTED, REVIEWED (Opus `/effort high`) AND MERGED TO
`main`.** Closes #78: `fsd init` + `fsd.config.load()` replace `env.example.sh` /
`notebooks/_config.py`.)_

**What spec 54 built, in one line.** `env.example.sh` (repo root) + `notebooks/_config.py`
(checkout-path `find_repo()`, `env.local.sh` parsing) — both unreachable from a `pip install` — are
replaced by `~/.config/fsd/config.toml` (D1: `$FSD_CONFIG_DIR` > `$XDG_CONFIG_HOME/fsd` >
`~/.config/fsd` on POSIX; `%APPDATA%\fsd` on Windows), written by fsd's first console script
(`fsd init` / `fsd init --from-env-file PATH` / `fsd init --set key=value`, plus `fsd config` to
print resolved values + provenance) and read by an explicit `fsd.config.load()`. `src/fsd/` itself
still never reads config (D3 — the part of spec 41 D7 that survives); precedence is explicit kwarg
> bare `AZ_*` env var > file (D4), and neither `load()` nor `init` ever touches `os.environ`.
Schema: one TOML table `[azure]`, six lowercase keys, written by a ~20-line hand-rolled emitter
(`tomllib` cannot write; `tomli-w` stays the documented escape hatch if the schema ever grows).

**Verified, not just tested green.** AC1 — the criterion #78 exists for — was run for real: built a
wheel (`python -m build`), installed it into a scratch venv with **no fsd checkout anywhere on the
path**, ran `fsd init --from-env-file` and
`python -c "import fsd; print(fsd.config.load().root)"` from an empty directory with no
`pyproject.toml` above it — both succeeded (MEMORY `real-run-beats-review`: green tests alone would
not have caught a `find_repo()`-shaped bug here). Suite **1003 passed, 92 skipped, 0 failed** (skip
count differs from the prior 977/96 baseline because this session additionally installed the
`azure`/`aml`/`mpc`/`titiler`/`serving` extras, unmasking tests previously skipped for missing deps
— not a regression), `ruff check src/ tests/` clean, identifier sweep clean (every hit matches
RECIPES.md's documented known-clean list — `env.example.sh`/`env.local.sh` as fsd's own filenames,
`fsd-aml-env`/`fsd-infer-env`, the `030f6ac` commit sha, `identityReference`/`prevent_destroy` as
generic API terms — no new leak).

Both tracked notebooks (`e2e_austria_aml.ipynb`, `00_build_images.ipynb`) now call
`fsd.config.load()` with lowercase attributes (`cfg.root`, not `cfg.AZ_ROOT`); their checkout-path
resolution is a two-line `pathlib.Path.cwd()` cell per D6, not `find_repo()`. `docs/howto/
run-at-scale.md` + `build-the-images.md` prerequisite lines and `docs/reference/environment.md`'s
"How to use it" section were updated in the same change; `CHANGES.md` / `DROPPED.md` record the
move.

**Review (Opus `/effort high`, 2026-08-26) — approved with five fixes, all applied.** The review
re-ran everything rather than trusting the report: suite, ruff, the identifier sweep, and **AC1
from scratch** (fresh wheel, `pip install --no-deps` into a scratch venv, run from a directory with
no `pyproject.toml` above it — `fsd.__file__` resolved inside the scratch venv, so no checkout was
on the path). D3 was verified by grep, not by claim: only `__init__.py` and `config.py` changed
under `src/`, and no `config.load()` / `config_dir()` / `write_config()` call exists anywhere
outside `config.py` and `cli.py`. What the review changed:

1. **`_toml_escape` missed U+007F (DEL)** — TOML forbids it raw in a basic string, and it sits
   *above* the printable range, so an `ord(ch) < 0x20` guard skips it and writes a `config.toml`
   that `tomllib` then refuses to parse. Fixed; DEL is now in the AC-6 adversarial table.
2. **`docs/howto/build-the-images.md` told the user to fill "AZ_RG and AZ_ML_WORKSPACE at
   minimum"**, which `load()` rejects — it requires all six or raises `MissingConfig`. The line now
   says all six. *Left open (a design question, not a defect):* `00_build_images.ipynb` genuinely
   needs only two of the six, and the retired `_config.load(*names)` allowed a subset. Giving
   `load()` subset support would change spec 54 D7, so it stays unbuilt pending sign-off.
3. **"never reads or writes `os.environ`" was stated twice and was wrong** (`load()`'s docstring,
   a `CHANGES.md` bullet). `load()` *reads* the environment — that is D4 precedence level 2 — and
   never assigns to it. Both now say that, because D4 is the exact thing a later reader must not
   misread.
4. **AC 7b was two-thirds tested** — the `init --from-env-file` write had no environ-mutation
   test. Added.
5. **Interactive `fsd init` — D5's primary form — had no test at all.** Added: prompt order,
   the existing value shown as default, Enter keeping it.

*Not fixed, recorded instead:* D1's `%APPDATA%` branch has no test, because `pathlib.Path()`
consults `os.name` at construction — forcing it to `"nt"` on POSIX makes every `Path(...)` raise
`NotImplementedError`, pytest's own included. A comment in `tests/test_config.py` says so.
*Known small warts, none blocking:* `fsd init --set key=` cannot clear a value (empty is filtered,
so it is a silent no-op); a non-tty `fsd init` dies on a bare `EOFError`; a hand-edited
`root = 12345` passes through as an `int`.

**Post-fix:** suite green, `ruff check src/ tests/` clean, identifier sweep re-run *correctly* —
the first attempt used `xargs -a`, which BSD xargs does not support, so it silently scanned
nothing; redone with `git ls-files -z | xargs -0` it gives seven hits, every one on RECIPES.md's
documented known-clean list.

---

_Previously: 2026-08-26 (**PHASE 2 STARTED. The consumer repo `rise/` exists and installs fsd
from a git URL; the friction it exposed is logged as a finding, and SPEC 54 (`fsd init` +
user-level config, closing #78) is WRITTEN AND SIGNED OFF. Merged into `main` (`--no-ff`),
worktree pruned. NOT PUSHED. NEXT: a Sonnet `/effort medium` session implements spec 54 §9.**)_

**What closed since the last entry.** The user stood up `rise/` — a separate git repo at the
workspace root with a `.venv`, a one-line `requirements.txt` (`git+https://github.com/nikhilsrajan/fsd`)
and a blank `notebooks/e2e_austria_aml.ipynb` — and asked what a stranger would actually have to do
to rebuild that notebook. That is phase 2's premise being exercised rather than described, and it
produced two artifacts.

**`docs/findings/consumer-repo-friction.md`** — eight friction points, four of them hard stops,
measured by read-only inspection (`pip show`/`pip list` in `rise/.venv`, the installed wheel
`RECORD`, `git ls-files` + `git check-ignore -v`, the notebook JSON). No cluster time. **It is an
OPEN LOG, not a point-in-time measurement** — the exception to the rule the other two findings
follow, because this friction *is* phase 2's deliverable, and the findings index says so. The four
hard stops: `env.example.sh` is not in the wheel and no install-facing doc names it; `_config.py`
raises at **import** outside a checkout; `notebooks/shapefiles/*.geojson` is caught by the blanket
`*.geojson` rule so the training data is on **nobody's** GitHub; and the extras set is
undiscoverable, with `README.md`, `docs/howto/run-at-scale.md` and the notebook's own init cell
giving **three different answers**, all in the `pip install -e ".[…]"` checkout-only form no
consumer can use.

Three things it also records, to stop them being re-derived: the **wheel is already code-only**
(`packages.find where=["src"]`; the RECORD is `fsd/**` + dist-info), so "ship less" is a
*dependency* problem (#80/#81), not a files problem; **~420 MB is the floor**; and the Azure
prerequisites are **not fsd's to fix** — a stranger genuinely cannot run this notebook, and the
runnable stranger path is `docs/tutorial.md`. Do not confuse *hard because Azure* with *hard
because fsd*.

**`specs/54-user-level-config.md`** — **SIGNED OFF 2026-08-26, not implemented.** Replaces
`env.example.sh` + `notebooks/_config.py` with `~/.config/fsd/config.toml`, written by a new
`fsd init` console script (fsd's first `[project.scripts]` entry) and read by an explicit
`fsd.config.load()`. Seven decisions, cross-validated against five primary sources with per-source
credit. The load-bearing one is **D3: the library still never reads config on its own** — the verbs
keep taking every storage location as an argument. That is spec 41 D7's *real* invariant surviving
while its **bootstrap** (a template at a repo root, a loader in `notebooks/`) is overturned; a
library that resolves its own storage root from ambient state behaves differently on every machine,
and every fan-out node would inherit whatever the driver's `$HOME` held.

Also decided there, so it is not relitigated: a tool-specific `FSD_CONFIG_DIR` **ahead of** XDG
(D1) — the cross-validation **amends #78**, which implied `~/.config` is the shared convention;
`az` actually uses `~/.azure` with `$AZURE_CONFIG_DIR` and gcloud `~/.config/gcloud` with
`$CLOUDSDK_CONFIG`, so the shared convention is *a user-level dir plus a tool-specific override*,
and that is also the evidence for rejecting `platformdirs` (its macOS answer matches neither).
Stdlib `tomllib` to read, **fsd's own emitter to write** — `tomllib` "does not support writing
TOML", and taking `tomli-w` for six flat strings runs against #80 (D2, with the escape hatch named).
Precedence **arg > env > file** with the bare `AZ_*` names kept, adopted from the Azure CLI's own
documented order, so `source env.local.sh` and every run-book keep working (D4). And **the
environment is read, never written** (D4, AC 7b) — `load()` never assigns to `os.environ`; the one
existing write in `src/fsd/` (`storage/azure.py:114`, `FSSPEC_ABFSS_ANON`) is named there with why
it does not generalise, because it is the precedent someone will cite.

**Q1 resolved at its recommendation:** `[azure]` + lowercase keys, read as `cfg.root`.

---

## NEXT: implement spec 54 — Sonnet `/effort medium`

**Spec 54 §9 is the build order** and it is written for this session: seven steps, each
independently testable, do not start one until the last is green. Start at step 1
(`src/fsd/config.py`), not at the CLI. Two things §9 says explicitly and are worth repeating
because they are the easy mistakes:

- **Do not touch `fsd.download` / `create_training_data` / `run_inference`.** D3 is the point of the
  spec; a signature change there is out of scope.
- **No test may reach the developer's real `~/.config/fsd`.** `monkeypatch.setenv("FSD_CONFIG_DIR",
  str(tmp_path))` in a fixture used by every test that touches disk (AC 8, spec 37 §7's rule).

**Then #80, then the tag.** The order from the last entry stands, with one change the user made on
2026-08-26: **the `v0.1.0` tag is cut AFTER the first consumer notebook works**, not before — a tag
pins the dependency set *and* the asset layout, and both are still moving. #80's extras split and
the shapefiles un-ignore should land **inside** `v0.1.0` rather than force a `v0.2.0` plus an edit
in every consumer.

1. **#80** (snakemake -> `[local]`, s3fs -> `[s3]`) — zero code change, **-53 packages / -111 MB**
   (689 -> 578 MB core closure). Both are declared core and **never imported** by `src/fsd/`.
2. **The `notebooks/shapefiles/` un-ignore** — not yet an issue, described in the finding's P3. The
   user's rule: the test geometries **must exist on GitHub** and **must not travel in a package
   install**, which are not in tension (git tracking and wheel contents are set by different
   mechanisms). **The precedent is already in-repo:** `.gitignore:32-38` un-ignores
   `tests/data/tutorial/` with `!dir/` **then** `!dir/**` and it carries a `NOTICE`. Copy that,
   NOTICE included — the Austria fields are EuroCrops-derived, and `CLAUDE.md` already claims a
   NOTICE exists there when it does not.
3. **#82 — cut and push `v0.1.0`** once the consumer notebook runs. Its stated blocker (unpushed
   commits) was already gone on 2026-08-26.
4. **#79 (`fsd.aml.ensure_environment()`)** — wanted, not blocking; paste image versions by hand as
   the notebook does today. Its scope call is still open and is written up in the finding's P7:
   **does the consumer repo build its own images, or consume admin-built ones?** That decides
   whether #79 is inside phase 2 or after it. Note `notebooks/images/*/fsd-*.whl` is gitignored, so
   a consumer cannot reproduce a build context today.
5. **#81 (numba -> `[accel]`, -160 MB)** — **do not block on it.** Not free: numba is a top-level
   import in `bands/modify.py` and `datacube/ops.py`, both reachable from `import fsd`. Needs a
   benchmark first. The floor is ~420 MB regardless — **"tiny" is not achievable; say so.**

**Deferred, recorded so it is not lost:** **`rise init`** (user, 2026-08-26) — a *project*-level
scaffold one layer above `fsd init`, standing up a consumer repo with its requirements, a starter
notebook and the config call wired. It belongs to `rise`, not fsd, and should be designed against a
consumer notebook that already exists. `fsd init` must not grow scaffolding options in anticipation.

**Two constraints the new repo still inherits.** Nothing private may reach it; and its demo notebook
needs its **own copy** of `tests/test_notebooks.py`'s guard (no saved outputs, no execution counts,
six identifier patterns) or it inherits the leak risk without the check.

**Housekeeping noticed, not done:** `specs/README.md`'s table stops at **spec 47** — 48-54 are all
missing. Its own convention note says regenerate the rows from `CHANGES.md`/`docs/adr/`/tests rather
than hand-patch a stale one, so it wants a pass, not a one-line append.

**Still open, unrelated to Phase 2:** #91 and #90 as one seam-gate spec (both are
`_check_local_seams` inspecting which kwargs were spelled rather than what the call will touch);
**#87 is waiting on evidence from the completed run** — either the single `_deploy.json` binding is
fine in practice (close won't-fix) or a concrete case where a mismatch warning was wanted.

---

_Previously: 2026-08-26 (**SPEC 53 DONE AND PUSHED; the e2e notebook is now TRACKED, guarded and
proven end to end on real Azure. `main` == `origin/main`.**) Spec 53 landed (#89 closed with
real-run evidence; review finding filed as #91). The user then ran `notebooks/e2e_austria_aml.ipynb`
**to completion** against the real cluster with the registry on **blob** — the first end-to-end run
of create_training_data -> train -> deploy -> run_inference where the model is resolved by NAME from
an `abfss://` registry, and the evidence specs 52 and 53 both said only a real run could give.

The notebook was un-ignored without being added to `tests/test_notebooks.py`'s `TRACKED_NOTEBOOKS`
— the mechanism that makes the `00_build_images.ipynb` exception safe — so it went public unguarded,
clean only because outputs had been cleared by hand. It now carries all six identifier patterns and
both structural rules, mutation-checked: injecting a storage account URL plus one `execution_count`
fails exactly three tests, each naming the leak class. Suite **977 passed, 96 skipped**, ruff clean,
identifier sweep clean.

Notebook content was also brought in line with the verbs as they now are: the
**1 create training data -> 2 create features -> 3 train -> 4 deploy -> 5 run inference** flow is
stated up front, section 3 documents deploy as **five gates**, `REGISTRY` moved to
`f"{cfg.AZ_ROOT}/model_registry"` (blob, hung off `AZ_ROOT` not `ROOT`, since models outlive runs),
and four stale "the registry must be local / will hang" claims were removed. One check was added
that fsd cannot do for the user: an assert that the training `SEQ` and the adapter's
`feature_sequence` are identical — they are written out twice in two files, nothing in fsd compares
them, and a drift produces confident nonsense with no error at bundling, at `verify_adapter`, or at
inference._

_Previously: 2026-08-25 (**SPEC 53 (D1+D2, #89) IMPLEMENTED + REVIEWED (Opus `/effort high`) +
MERGED into `main` (`--no-ff`, `main` @ `38a2d09`), worktree pruned, branch deleted. NOT PUSHED.**
All eight ACs verified, one review fix applied. On `main` the suite is **968 passed, 96 skipped, 0
failed** (4 more tests collected than in the worktree — the gitignored real-data fixtures under
`tests/outputs/` live in the main checkout only, not a behavior difference), `ruff` clean.

`api._stage_local_bundle` (new) fetches a non-local resolved bundle to
`<output_folderpath>/_model` via `infer_shard.fetch_bundle_to_scratch`, and is called from two
sites: unconditionally in `run_inference`'s pre-built-cubes path (right after that path's own
`_raise_preflight`, since `cores=1` and the `cores>1` Snakemake fan-out are both always-local —
`runner=` never reaches that branch) and, gated on `runner == "local"` per D1's amendment, in
`_run_inference_roi` (right after its own `_raise_preflight`, before `_ensure_bundle`). Both sites
sit after preflight, not literally next to `_resolve_model_ref`, so `_model_spec`'s earlier read
(which uses `fs.open` and needs no local copy) still costs nothing on a rejected call (AC4).
Because staging lands before `_ensure_bundle`'s own (idempotent) resolve call, `_ensure_bundle`
just passes the already-local path through — AC6 (`cores>1`) falls out for free, as the spec said
it would.

9 tests in `tests/test_local_bundle_staging.py` — 8 cover AC1–AC7 (AC8 is the existing suite +
ruff, already green); each was mutation-checked (call site commented out -> the assertion that
covers it fails) rather than trusted on green alone (MEMORY `real-run-beats-review`). One thing
the tests do NOT reproduce: #89's actual `ModuleNotFoundError`. The adapter class used in the test
lives in the test module itself, which is already in `sys.modules` by the time `bundle.load` runs
in-process, so `importlib.import_module` finds the cached module regardless of `sys.path` — the
crash itself needs a genuinely fresh interpreter, which is what the run-book's real-Azure repro
gives and unit tests cannot. The tests instead assert the mechanism directly: call counts, the
staged path, and which call sites see it — AC1–AC7 as written.

**Opus review, 2026-08-25 — verdict: clean, with one fix applied.** All eight ACs were
re-verified against the diff (AC1/AC2/AC5/AC6 by reading the code path, AC3/AC4/AC7 by the tests'
zero-call assertions, AC8 by re-running the suite here). Two findings:

1. **FIXED — the driver-side fetch was completely silent.** Confirmed by capturing stdout on a real
   `memory://`-registry run: the output went `[model] probe@champion -> v1` straight to
   `[inference] 1/1 -> ...`, with nothing in between. D2's rationale for accepting a per-run
   re-fetch rests on "spec 47 D5 already prints the transfer with a size and a ticker, so it is
   never silent" — but D5 instrumented `runners._stage_bundle` (the **upload** leg), and
   `fetch_bundle_to_scratch` prints nothing. `_stage_local_bundle` now prints
   `[stage] bundle <- <url> | N files, X MB` before the transfer, mirroring `_stage_bundle`'s D5
   shape (one extra `bundle.json` read + one `fs.size` per file, the cost `_stage_bundle` already
   accepts). A 9th test asserts the line exists, names the source, carries a size, and lands
   **before** the first `[inference]` line. Not given a per-file ticker: that would mean editing
   `fetch_bundle_to_scratch`, which the AML node path shares, and AC7 says that path is untouched.
2. **NOT FIXED, needs an issue — a non-local `output_folderpath` now creates a junk directory.**
   The seam gate (`_check_local_seams`) inspects the `storage=` kwarg, never the URL, so
   `run_inference(model=<blob ref>, output_folderpath="abfss://...", ...)` reaches
   `_stage_local_bundle`, which hands a URL to `fetch_bundle_to_scratch` — whose `os.makedirs` and
   bare `open` are local-only. Probed with `memory://outblob`: it created a literal `memory:`
   directory in the process's CWD and then raised `FileNotFoundError /outblob/_model/bundle.json`.
   That combination was already broken before this change (`bundle.load` would have failed on the
   URL anyway), so this is not a regression — but the failure is now messier and leaves litter.
   Left alone deliberately: the right fix is a design call (reject early in preflight vs. stage to
   a real temp dir), which is spec territory, not review territory.

**Full suite re-run under review: 965 passed, 94 skipped, 0 failed → 966 passed with the review
test added; `ruff check src/ tests/ demos/ examples/` clean** (baseline before this work: 956
passed, 93 skipped).

⚠️ **Working-copy note for whoever picks this up:** the editable install in `fsd/.venv` resolves to
the **main checkout's** `src/`, not a worktree's — running `pytest`/`ruff` from inside
`.claude/worktrees/spec53-phase0/` against `../../../.venv/bin/python` silently ran the MAIN
checkout's code for a while during this session (masked by `sys.modules` caching happening to make
the tests pass anyway) until caught by a suspicious zero-call assertion. Fix: prefix commands with
`PYTHONPATH="$(pwd)/src"` from inside the worktree, or give the worktree its own venv.

**VERIFIED ON REAL AZURE, same day.** The user re-ran `runbooks/52-registry-on-blob.md` step 4
against the real `abfss://` registry **with no manual workaround** — the exact call that raised
`ModuleNotFoundError` before — and it passed: `{"step": "52-4-run-inference", "pass": true,
"published_version": 1, "n_outputs": 1, "error": null}`. That is the proof spec 53 §9 said unit
tests structurally could not give (the crash needs a fresh interpreter; the test module is already
in `sys.modules`). **Spec 53 is DONE and #89 is closable.** The run-book was updated to match:
step 4's result row now reads PASS-unaided, the obsolete fetch-to-scratch workaround block is gone
(git history at `9ab5202` if an old checkout needs it), and the prerequisites no longer warn that
the step cannot pass.

**LANDED AND PUSHED (2026-08-25).** `main` @ `5fe9b86` pushed to `origin` (`9ab5202..5fe9b86`,
fast-forward, 5 commits) after a clean private-identifier sweep — all 7 hits were the documented
known-clean false positives (`RECIPES.md`'s list: `030f6ac`, `env.example.sh`, `env.local.sh`,
`fsd-aml-env`, `fsd-infer-env`, `identityReference`, `prevent_destroy`). **#89 CLOSED** with the fix
summary and the real-run evidence. Review finding 2 filed as
**[#91](https://github.com/nikhilsrajan/fsd/issues/91)** — a non-local `output_folderpath` reaches
`_stage_local_bundle`, which is local-only, so it creates a scheme-named junk directory in the CWD
and then raises a `FileNotFoundError` naming a path the caller never passed. Not a regression (the
combination was already broken pre-spec-53) and low severity, but the right fix contradicts D2's
fixed scratch location, so it is spec territory. **Filed as a sibling of #90: both are
`_check_local_seams` inspecting which kwargs were spelled rather than what the call will touch —
worth one spec over the gate, not two patches.**

**NEXT:** open. Spec 53 is finished end to end (signed off → implemented → reviewed → merged →
pushed → verified on real Azure → #89 closed). The obvious candidates are #90+#91 as one seam-gate
spec, or the next item on the notebook-usability sprint (MEMORY `fsd-notebook-usability-sprint`). Then the *user* re-runs `runbooks/52-registry-on-blob.md` step 4 **without** the manual
workaround against the real `abfss://` registry — the only thing that proves #89 closed; Claude
never runs it.

_Previously: 2026-08-25 (**SPEC 52 MERGED into `main` (`--no-ff`, `main` @ `f2fe6bf`), worktree
pruned, branch deleted. NOT PUSHED. The run-book was then executed against a REAL `abfss://`
registry by the user — steps 1-3 PASS, step 4 FAILS, and it found two defects that 956 green
tests, two Opus review rounds and a mutation pass all missed (MEMORY `real-run-beats-review`).**

**Run-book results (real Azure, 2026-08-25).** Step 1: v1 published in **32.9 s** — #88 is
genuinely dead against Azure, not just `memory://`. Step 2: v2 published on changed content
(digests differ). Step 3: `set_alias` repointed `champion` -> v1. **Step 4: FAILED as written, workaround
PASSED** — the ref resolved (`[model] crop-rf-t10@champion -> v1`, against live blob, which is
AC8's substance) and then died in `bundle.load`; inference ran once the bundle was fetched to
scratch. **Step 5: PASS** — re-publishing v1's exact content returned v1 and wrote nothing
(`n_entries` 3 -> 3). **Verdict: spec 52's publish protocol is proven on real Azure** (in-place
publish, marker, alias repoint, digest idempotency); **#88 is closeable**; **#86 is not proven**.

**Two new issues, both filed, both with a drafted fix:**
- **[#89](https://github.com/nikhilsrajan/fsd/issues/89) — a blob-resolved ref cannot be loaded on
  the local run path.** `bundle.load` requires a local directory (its own docstring says so) and
  `_activate_bundle_code` does `sys.path.insert(0, "<bundle>/code")`; with a blob ref that entry is
  an `abfss://` URL, and CPython ships only `zipimporter` + `FileFinder` path hooks, so it is inert
  (verified by execution). The AML path stages first and is fine; the local path never stages.
  **A blob registry works for AML runs and is broken for local runs.** Pre-existing, but only
  reachable once spec 52 made a blob registry possible.
- **[#90](https://github.com/nikhilsrajan/fsd/issues/90) — `storage=` and `registry=` are
  conflated in `run_inference`'s seam gate**, so spec 52 D4's `configure_storage` fix is
  unreachable on the pre-built-cubes path (`storage="azure"` is refused there). **#86 is therefore
  UNPROVEN, not fixed** — step 4 is the run-book's only step that goes through a verb at all.
  Related finding: adlfs's `anon` default is `None`, not `True`, so steps 1-3 authenticated
  against real Azure with **no** `configure_storage` call anywhere — #86's stated failure mode may
  not occur under a developer `az login` at all. Recorded as spec 53 §5's first risk.

**[`specs/53-blob-registry-on-the-local-run-path.md`](specs/53-blob-registry-on-the-local-run-path.md)
— SIGNED OFF (user, 2026-08-25) at both proposed defaults. Rescoped to #89 alone before
sign-off.** D1: stage a non-local resolved
bundle to scratch in `run_inference`, right after `_resolve_model_ref`, reusing
`infer_shard.fetch_bundle_to_scratch` (the primitive already exists — the spec wires, it does not
write transfer code). D2: scratch at `<output_folderpath>/_model/`, per run, not a cache. **D1 was amended after
sign-off (2026-08-25) with a runner gate:** as first written it staged whenever the resolved path
was non-local, with no runner condition, which contradicted AC7 — a blob registry plus
`runner="aml"` would have added a blob→local fetch that then got staged straight back to blob.
Staging is now gated on `runner == "local"` (the shapes that actually call `bundle.load` on this
machine), with `fs.is_local` as the locality test; AC7 asserts zero driver-side fetches on the AML
path by call count. **§7's two questions
resolved at their defaults:** staging goes in `run_inference` (so `bundle.load` keeps the narrow
spec-44-D2 contract — no network I/O, no temp dir of its own; the accepted cost is that a future
caller handing `load` a URL hits #89 again, with §6 option B kept as the way back), and scratch
stays per-run rather than a digest-keyed cache (cheap to add later — the digest is already in
`_complete.json`).

**#90 was dropped from spec 53 and downgraded to a tidy-up** (assessment recorded as a comment on
the issue). The reason: **`configure_storage` does not authenticate** — its whole body sets
`FSSPEC_ABFSS_ANON=false` plus the matching `fsspec.config` key, which forbids the *anonymous
fallback* rather than supplying a credential. Credentials come from the `az login` chain either
way, which is exactly why steps 1/2/3/5 worked without it. So #90's entire cost today is a
confusing refusal when a caller passes a kwarg they never needed; the workaround is to omit it.
**Caveat kept visible: while that gate stands, #86 is permanently unprovable**, since the
run-book's only verb-level step cannot exercise D4 — a bookkeeping cost, not a functional one, and
the one argument for fixing #90 sooner.

**#88 CLOSED** (2026-08-25) with the real-Azure evidence. **The #86 claim was corrected** in
`CHANGES.md` (a "Correction, 2026-08-25" block) and in spec 52's header + §10.5 — the merge commit
`f2fe6bf` and `82eda21` both say #86 is closed, which is wrong and cannot be edited after the fact,
so those notes are the correction of record.

**`runbooks/52-registry-on-blob.md` was corrected as the run proceeded** (step 2 had no command at
all and referenced an env var nothing produced; step 4 had three separate faults: `storage="azure"`
which the gate refuses, a model/cube `n_timestamps` mismatch, and folder-mode cube discovery that
needs per-cube subfolders). It now carries the #89 workaround so step 4 is completable today. All
7 Python blocks parse; no undeclared env vars.

**NEXT: implement spec 53's single phase (D1+D2, #89) in a Sonnet session at `/effort medium`**
against the signed-off spec, then hand back to Opus `/effort high` for review. Then re-run run-book step 4 **without** the manual workaround to prove it.
Also still pending: the push of `main` (at `f2fe6bf`, plus the uncommitted doc/spec work).

_Previously: 2026-08-24 (**SPEC 52 IMPLEMENTED (Sonnet `/effort medium`) and REVIEWED by Opus
`/effort high` — four findings, all fixed in-branch; see the "Opus review" block below and spec 52
§10.** Work is on worktree branch `worktree-spec52-registry-on-blob` (at `fsd/.claude/worktrees/`),
based on `main` @ `7c3811c`.

**Step 0 (registry core, D1/D2/D3/D5) — `fsd/model/registry.py`.** `_write_new_version` writes a
version's files straight into `v<N>/` (no staging prefix, no directory rename), re-digests what
landed, and writes `v<N>/_complete.json` last. `_list_versions` is now marker-aware, with a legacy
carve-out (`bundle.json` present, no marker) for pre-spec content. The retry loop is bounded at
`_MAX_PUBLISH_ATTEMPTS = 16` and retries only a genuine version collision.

**A real D5-vs-AC2 conflict surfaced during implementation, not guessed around** (MEMORY
`verify-the-primitive-a-spec-cites`-flavored: check it, don't code around it). D5's legacy rule
(`bundle.json` present + no marker ⇒ complete) and AC2 (an interrupted publish must be invisible to
`_list_versions`) contradict whenever `bundle.json` lands before the interruption — confirmed with
a failing test, since `bundle.json` sorts alphabetically early among a bundle's files. Flagged to
the Opus session; **adjudicated same-day, spec amended** (see spec 52 §3 D5's "Amendment" block and
AC2's rewritten text): `_write_new_version` now writes `bundle.json` **last** among the content
files, so an interruption during the write (where nearly all the risk is) leaves no manifest and
is genuinely reusable; the one-object-write residual window (after the manifest, before the
marker) is left to the legacy reading, on the reasoning that misreading real legacy content as
incomplete can destroy a published version, while misreading a rare interrupted version as
complete only strands a folder (a cost §5 already accepts). Same review pass found `migrate`
never wrote `_complete.json` at all — fixed (new AC5a), so migrated content no longer depends on
the legacy carve-out to be visible.

**Step 1 (verb wiring, D4) — `fsd/api.py` + `fsd/model/verify_image.py`.** `deploy` drops
`storage_allowed=False` (accepts `storage="azure"` now). `deploy`, `run_inference`,
`verify_adapter` each call `configure_storage(storage)` right after preflight's cheap validation
starts, before the first storage touch (`_resolve_model_ref`/`fs.read_geo`/`_bundle.read_spec`).
`verify_image` gained a `storage=` kwarg it never had (#86 — it previously could not authenticate
at all) plus the same call, placed after its own cheap arg checks.

**Step 2 (end-to-end, AC8) — spec 51's AC12 unblocked.** `test_registry.py`'s skipped
`test_publish_resolve_round_trip_against_a_url_registry` is unskipped (D1 removed the hang it was
blocked on). Added `test_deploy.py::test_deploy_set_alias_resolve_run_inference_against_a_url_registry`
for the fuller chain AC8 actually names (`deploy` → `set_alias` → `resolve` → `run_inference`), and
a dedicated timeout-asserted test for AC1's literal wording (a background thread + `join(timeout=10)`,
no new test dependency).

**Opus review, 2026-08-24 — four findings, all fixed in-branch. The D5/AC2 amendment itself was
re-derived independently and STANDS** (the handoff was right to ask for that; the one correction to
it, #4 below, does not change its conclusion). Full account: spec 52 §10.
(1) **`run_inference`/`verify_adapter` turned a preflight error into a bare `ValueError`.** D4's
`configure_storage` call genuinely had to precede `_raise_preflight` — but `configure_storage`
*raises* on an unsupported backend, so `storage="s3"` escaped as `ValueError` and discarded every
other accumulated preflight error. And the side effect the handoff reasoned was absent is real: a
call the seam *rejects* (`run_inference(storage="azure")` on the pre-built-cubes path) still flipped
the process to authenticated adlfs first — the exact accident D4 exists to remove. The seam check
now raises on its own first, matching `deploy`. (2) **Publishing into an incomplete version
inherited the previous attempt's leftovers.** AC2 reuses an unmarked `v<N>` in place, and
`content_digest` covers only *manifest-declared* files, so an undeclared artifact or `code/*.py`
survived into the version and was then marked complete — and `bundle.load` puts `code/` on
`sys.path`, so a stale module there is importable by the next adapter. `_write_new_version` now
`_discard`s an incomplete target before writing; stage-then-rename got a clean directory for free.
(3) **Four branches were unpinned — mutation testing found them, reading did not.** Deleting the
idempotent-collision `return`, disabling the landed-digest guard, and replacing D5's legacy check
with `return False` each left the suite green; the two rewritten "race" tests cannot reach
`_write_new_version`'s collision branch at all (their competitor publishes *before* `_list_versions`
runs). So the narrowing flagged at handoff did lose AC4's substance and left **AC5 with no test at
all**. Five tests added, each verified to kill its mutation. (4) **The residual window is not "one
object write wide"** — `content_digest(target)` re-reads the whole bundle inside it. Conclusion
unaffected and actually stronger: everything in that window is post-write, so a version stranded
there holds complete content; it is unverified, not partial.
Suite **956 passed / 93 skipped**, ruff clean.

**Run-book written, not run** (Claude never runs pipeline/networked scripts): `runbooks/52-registry-on-blob.md`
— publish v1/v2 to a real `abfss://` registry, repoint an alias, run inference off the ref,
confirm a re-publish of identical content is a no-op. Green tests do not finish this spec (MEMORY
`real-run-beats-review`) — this is the part they cannot cover.

**NEXT:** hand back to Opus `/effort high` for review (spec, tests, and the D5/AC2 amendment
itself), then the user runs the run-book and pastes back its five printed results.

**⚠️ `main` has an uncommitted `PROGRESS.md` edit that is now WRONG** — it records the blob registry
as "a documented LIMITATION, not scheduled work", which the user reversed the same day. Discard it
(`git checkout PROGRESS.md` on `main`) before merging this branch. `main` also carries an
uncommitted one-character docstring change in `src/fsd/model/adapter.py` (an en-dash became a
hyphen) that Claude did not make._

_Previously: 2026-08-24 (**spec 51 §9 step 3 (the `[model]` print line, D7/AC10's print half) —
IMPLEMENTED (Sonnet `/effort medium`) and REVIEWED by Opus `/effort high`: three findings, all
fixed in-branch — see CHANGES.md's "Opus review" block.** Work is on worktree branch
`spec51-step3-model-line`, based on `main` @ `88e8f11` (steps 0-2 merged + pushed). This is the
**last step of spec 51 §9** — after Opus review + merge, the spec is implemented apart from the
two §7 AC gaps below (one done here, one blocked and issued).
**What shipped:** `api._resolve_model_ref` now prints `[model] <ref> -> v<N> (verified against
<env>)` (or the shorter `[model] <ref> -> v<N>` with no `_deploy.json`/`environment`) the moment a
ref actually resolves — inside the one branch where `registry_mod.resolve` succeeds, so it fires
exactly once per `run_inference`/`verify_adapter` call even though both can call
`_resolve_model_ref` twice. `registry.read_deploy_record` (new, public) backs it and
`_read_deploy_digest`; never raises — a missing/malformed `_deploy.json` degrades to the shorter
line. Full detail: `CHANGES.md`'s top entry.
**Deliberately deferred (recorded in the spec, not silent):** D7's environment-mismatch warning
(§7 Q2) — `_deploy.json`'s `environment` is last-writer-wins, so it would warn falsely against any
image but the most recently verified one. Ship the print only; decide the warning from real
notebook use. **[Issue #87](https://github.com/nikhilsrajan/fsd/issues/87).**
**Secondary scope (§7's two AC gaps):** AC14's second half done —
`test_deploy_refuses_verify_adapters_real_auto_saved_bundle` runs the real `verify_adapter` path
and feeds its actual `metrics["bundle_path"]` to `deploy`, asserting the `requirements` refusal.
**AC12 (URL registry) blocked, not done** — writing it surfaced a real, separate bug:
`registry._write_new_version`'s retry loop hangs forever publishing to any non-local fsspec
backend (confirmed `memory://`), because `storage.fs.rename`'s directory move fails `ENOTEMPTY` on
`MemoryFileSystem` and every retry hits the identical (non-transient) failure. Not fixed here —
out of this step's scope, a storage/registry design question. **[Issue #88](https://github.com/nikhilsrajan/fsd/issues/88).**
The AC12 test is now present but **`@pytest.mark.skip`ped** (Opus review) so the gap stays visible
in `pytest -q`'s skip line instead of being absent from the suite.
Suite **936 passed / 91 skipped / 1 pre-existing failure** (`planetary_computer` absent), ruff
clean.
**Opus review found three (the pattern held for a fourth step running):** (1)
`read_deploy_record` raised `UnicodeDecodeError` on a byte-corrupt `_deploy.json`, breaking its own
never-raise contract — catch widened to `(ValueError, OSError)`; (2) the once-per-call test was
**vacuous** — an empty `inference_datacubes` folder dies at `_raise_preflight` before
`_ensure_bundle` is ever reached, so it asserted "printed once" with only one of the two call sites
executed; rewritten to drive a real datacube at `cores=2` and assert the second call site ran;
(3) `registry.__all__` was missing `read_deploy_record`. Both behavioral fixes are mutation-checked.
Independently verified during review: no runner or node resolves refs (`src/fsd/workflows/` contains
zero `registry` references — nodes receive a staged bundle path), so D9's "once, on the driver"
claim holds; and issue #88's hang reproduces (`_write_new_version` on `memory://` still looping
after 10s).
**Committed + merged `--no-ff` into `main` (`main` @ `002c85e`), worktree pruned, branch deleted.
NOT PUSHED — `main` is 2 commits ahead of `origin/main`, awaiting the user's push.**
**NEXT after the push: update `notebooks/e2e_austria_aml.ipynb`** to use the registry verbs
(`fsd.deploy` + a `name@alias` ref through `run_inference`), then the user runs it and reports on
usability._

_Previously: 2026-08-22 (**spec 51 §9 step 2 (`fsd.deploy`) REVIEWED by Opus `/effort high` —
one real defect found, reproduced and fixed; MERGED into `main` (`--no-ff`, `main` @ `37124c5`)
and both per-spec worktrees pruned. NOT PUSHED — `main` is 3 commits ahead of `origin/main`,
awaiting the user's go.**
**The defect (D5's whole guarantee, silently void):** `deploy(verified=...)` matched a prior
verification by re-digesting the result's own `metrics["bundle_path"]` **at deploy time**, but
`verify_image` recorded no digest of what it had verified. Since `bundle.save` overwrites in place
(spec 51 §1 H1), the normal verify → retrain → re-save → deploy loop hands `deploy` a
`_result.json` naming the *right path* holding the *wrong content* — and re-digesting that path
compares the new content **with itself**, a tautology that always passes. `_deploy.json` then
recorded "this image ran this bundle" for content the image never saw, which is exactly what D5
exists to prevent. Reproduced before fixing.
**Fix (AC8 taken literally — "the result's *bundle digest*"):** `verify_image` now records
`metrics["bundle_digest"]` at verification time (additive to its `_result.json`; the only change
made to that module), and `_verified_matches` compares that recorded digest, never the path. A
result carrying no `bundle_digest` is refused as a mismatch — it cannot say what it verified, so
**every `_result.json` produced before today must be re-run**. Side benefit: a `_result.json` is
now portable between machines. Pinned by
`test_deploy_refuses_a_verified_result_whose_bundle_was_overwritten_in_place` +
`..._records_no_bundle_digest`, plus a producer-side assertion in `test_bundle_transparency.py`.
**Two smaller review fixes:** (a) `registry.check_name`, called by `publish` and up front by
`deploy`, refuses a model name carrying `/`, `\`, `:`, `@`, a leading `.`, or nothing — such a name
published fine and returned a ref nothing could resolve (`crop/rf:1` reads as a *path* to
`api._is_ref_shaped`; `crop:rf:1` re-splits at the wrong separator), breaking AC1; checked before
verification so a bad name costs no AML node. (b) `deploy(verified=<missing path>)` now raises the
verb's `PreflightError` instead of a bare `FileNotFoundError`. (c) the `pass=False` refusal falls
back to `metrics["smoke_error"]` when `verify_image`'s top-level `error` is `None` (it is populated
only for *driver*-detected failures), so a failed smoke job no longer refuses with the useless
literal "verify_image error: None" — the implementer flagged this in the handoff as an open
question; D5's "the verification's own error" is better served by the actual diagnosis.
**Reviewed and accepted as-is:** the ordering that guarantees AC7's "no version directory on
refusal"; the `_verified_matches`-drops-the-`pass`-check call the implementer made (correct — `pass`
is judged separately, so a matched-but-failing result surfaces its own `error`); the
`publish`-reads-`_deploy.json`-first optimization and its monkeypatch test (which does prove what it
claims — `publish` digests the *source* bundle via `_digest_of`, not the patched `content_digest`);
`migrate` carrying `_deploy.json` across (an out-of-scope addition, but the right call: D11's "a
move is a copy" would otherwise lose every binding record); the AC13a scan (`_deploy.json`'s
embedded `verified.metrics.bundle_path` is D11-sanctioned *evidence*, not a reference, and deploy no
longer reads it at all); and the removal of `test_deploy_is_stub`.
**One design question left open, not filed as an issue yet (user's call):** re-deploying identical
content **overwrites** that version's `_deploy.json` (new `deployed_at`, and a different
`environment=` replaces the recorded binding), which sits against D2's "identical content → returns
it, **writes nothing**". Arguably desirable (the version is now known to run the newer image) but it
silently drops the older binding; the spec is silent. Also unaddressed, cosmetic: `deploy` digests
the bundle twice (once itself, once inside `publish`).
Suite **927 passed / 91 skipped / 1 pre-existing failure** (`planetary_computer` absent), ruff clean.
**NEXT: user's go to merge + prune, then step 3** (the `[model] name@ref -> vN (verified against
<env>)` line + the environment-mismatch warning, D7/AC10's print half). Previous entry: step 2's
implementation session, below.)_

_Previously: 2026-08-22 (**spec 51 §9 step 2 (`fsd.deploy`, D5/D6/D7) implemented — Sonnet
`/effort medium`.** Work is on worktree branch
`worktree-spec51-step2-deploy`, based on `main` @ `6b3fcae` (steps 0-1 merged + pushed). `deploy`
now: refuses a live adapter (naming `fsd.model.bundle.save`, D6) and a bundle whose manifest lacks
`requirements`/`code` (naming the fix); establishes the bundle↔image pairing before recording it,
either by running `fsd.model.verify_image` itself or by accepting a prior `verified=<_result.json
path or dict>` **only if** its own recorded `metrics["bundle_path"]` — re-digested now — and
`metrics["environment"]` both match this call (a `pass=False` result that DOES match is still
honoured and refused with its own `error`; one that does NOT match is refused as "stale or does not
match", never silently re-verified, D5); on `pass=True` calls `registry.publish` (idempotent, D2)
and writes `_deploy.json` beside `bundle.json` (`name`/`version`/`digest`/`environment`/`verified`/
`deployed_at`/`fsd_version`, D7) via a new `registry.write_deploy_record` (staged + renamed, like
`set_alias`). Two follow-on fixes to `registry.py` made as part of this step: `publish`'s own
idempotency loop now reads a version's `_deploy.json` digest first and only recomputes when absent
(the "N content reads → N metadata reads" optimization `publish`'s docstring flagged as step-2's
job), and `migrate` now carries `_deploy.json` across a relocation (it isn't part of the content
digest, so a naive migrate would have silently dropped every version's deploy record). New
`tests/test_deploy.py` (15 tests, AC1/2/3/5/7/8/9/10/13a + D6) plus two new `test_registry.py`
tests for the two follow-on fixes; the AC7 pass/fail tests exercise the real `verify_image` call
through the same fake-`MLClient`/`azure.ai.ml.command` injection seam spec 45's tests use — no
network. Removed the now-obsolete `tests/test_api.py::test_deploy_is_stub` (asserted the old
`NotImplementedError` stub signature). Suite **920 passed / 91 skipped / 1 pre-existing failure**
(`planetary_computer` absent), ruff clean (`src/ tests/ demos/ examples/`). **Open, not yet filed:
a URL registry has no credentials for WRITE either** — `deploy` doesn't call `configure_storage`
(matching `run_inference`/`verify_adapter`'s existing non-call, issue #86), so `registry="abfss://…"`
would need real credentials this step deliberately does not add; tested only against a local
registry root. **NEXT: hand to Opus `/effort high` for review, then step 3** (the `[model] name@ref
-> vN (verified against <env>)` line + the environment-mismatch warning, D7/AC10's print half —
small, deliberately out of step 2's scope). Previous entry: step 1.)_

_Previously: 2026-08-22 (**spec 51 §9 step 1 (`_ensure_bundle` ref resolution) implemented and
REVIEWED**, merged into `main` (`--no-ff`) and **PUSHED — `main` @ `b85924b`, level with
`origin/main`, nothing unpushed**, worktree pruned. The Opus review
found a real defect the unit tests could not see: resolution sat at `_ensure_bundle`, but
`api._model_spec` reads `bundle.json` off `model` **first** in both `run_inference` and
`verify_adapter` (and `cores=1` pre-built cubes never calls `_ensure_bundle` at all), so
`run_inference(model="crop-rf@champion", registry=…)` still died with
`FileNotFoundError: crop-rf@champion/bundle.json` — proven by running it. **D4 amended (user chose
"Option A", 2026-08-22):** resolution is now one idempotent, shape-gated helper
`api._resolve_model_ref`, called at every site that reads `model` as a path; a string carrying a
path separator is never a ref (keeps it off `abfss://<fs>@<account>…`), and an already-resolved
path passes through, so a later call site cannot reintroduce the bug. Also tightened the AC6
`"@"`-without-`registry=` check (it had refused legitimate paths like `/data/rf@2026/bundle`),
wrapped `resolve` failures as `PreflightError`, dropped the dead `storage_options=`. **Open, not
yet filed: a URL registry has no credentials** — `run_inference`/`verify_adapter` never call
`configure_storage`, so `registry="abfss://…"` resolves anonymously (AC12 unmet; step-2 work).
Suite **904 passed / 91 skipped / 1 pre-existing failure**, ruff clean.
**NEXT: spec 51 §9 steps 2-3** (`deploy` → the `[model]` line). Previous entry: step 0.)_

_Previously: 2026-08-22 (**spec 51 §9 step 0 (`fsd.model.registry`) implemented, REVIEWED and
merged into `main`** — the Opus review found and fixed a real defect: `storage.fs.rename` was
`shutil.move` locally, so a `publish` losing a version race nested its bundle inside the winner's
directory and **returned the winner's version number**. Fixed at the seam (`fs.rename` is now a
real `os.rename` locally) plus a re-digest of what actually landed, and `_aliases.json` is now
written by rename too. Suite **890 passed / 91 skipped / 1 pre-existing failure**
(`planetary_computer` absent), ruff clean. `main` @ `2b5ae4b`, **PUSHED — level with
`origin/main`, nothing unpushed**, tree clean, no worktrees. **NEXT: spec 51 §9 steps 1-3**
(`_ensure_bundle` resolution → `deploy` → the `[model]` line). See the 2026-08-22 (later still)
entry below.)_

_Previously: 2026-08-22 (**spec 50 fully landed + PUSHED; spec 51 (P6 `deploy`) SIGNED OFF, not
implemented** — `main` @ `6e163c5`, **level with `origin/main`, nothing unpushed**, tree clean.
Suite 870 passed / 90 skipped / 1 pre-existing failure (`planetary_computer` absent), ruff clean.
See the 2026-08-22 entry below for the full state, including two defects found on the first real
AML run and the comment-convention work.)_

## Where things stand

**What fsd does today, proven on real infrastructure:** download → datacube → flatten → train →
inference, run both locally and fanned out across an Azure ML cluster. The 2026-07-29 cluster demo
(`demos/e2e_austria_aml.py`, run `20260729T132222Z`) completed unattended in **18.8 min, 8/8 steps,
97 jobs, 213 MPC granules, 300 grid cells → 300 output COGs + STAC + a merged map**. That run *is*
the validation ROADMAP P3 and P4 were waiting on.

**Current work: the docs refactor (spec 41).** P1–P5 are done **and P5 is reviewed** (8 findings,
all fixed — see the entry below); the rest is in the archive. P6/P7 remain.

| | state |
|---|---|
| **Pipeline** | v1 core complete (S2 L2A, CDSE + MPC), proven local and on AML |
| **Scale-out** | AML runner seam; download, build, flatten and inference all fan out |
| **Serving** | tier-1 (pre-styled XYZ) and tier-2 (pgSTAC + titiler-pgstac) both validated |
| **Docs** | spec 41 P1–P6 done; **P7 drafted + reviewed** (`docs/tutorial.md`, 5 `docs/howto/*` pages + index) — the D13 cold-start gate is the user's, not yet run |
| **Deferred work** | **GitHub Issues #1–#63**, number-aligned with the old `TODO.md` rows (39 open / 24 closed) |
| **Open decision** | rslearn Plan B vs Plan C — **no longer untouched: the spike is LIVE on `spike/rslearn`** (see below) |

**Where to look:**

| you want | read |
|---|---|
| how the code is laid out | [`ARCHITECTURE.md`](ARCHITECTURE.md) |
| where fsd is going | [`ROADMAP.md`](ROADMAP.md) |
| what a term means | [`CONTEXT.md`](CONTEXT.md) |
| why a decision was made | [`docs/adr/`](docs/adr/) |
| a measured result | [`docs/findings/`](docs/findings/) |
| an env variable | [`docs/reference/environment.md`](docs/reference/environment.md) |
| open work | `gh issue list` |
| what happened before | [`docs/progress-archive.md`](docs/progress-archive.md) |

> ⚠️ **A second workstream opened 2026-07-31 and does NOT live on `main`: the rslearn spike.**
> `spike/rslearn` (pushed, `b91f982`) is refreshed from `main` and now carries a re-read of
> rslearn **v0.1.13**, two offline probes and a VM run-book. **Its status lives in
> [`spike/README.md`](https://github.com/nikhilsrajan/fsd/blob/spike/rslearn/spike/README.md) —
> read that, not this file, when resuming the spike.** Three headline findings so far, all from
> source, nothing run yet: torch/lightning are **core** rslearn deps (no lite path);
> **zero** Azure support in 54,850 LOC; and `RSLEARN_COMPARISON.md`'s claim that fsd's
> calendar-`T` contract is *unique* is **wrong** — `QueryConfig.period_duration` is the analogue,
> but it drops empty periods, floors the span and end-anchors, so rslearn's `T` is data-dependent.
> Nothing about the spike belongs in `main` until the Plan-B/C decision.

**Spec 44 phase 1 is DONE (2026-08-19).** Merged to `main` and fully validated on the cluster:
`runbooks/45-verify-bundle-carried-code.md` Phases 0–2 all green on **`fsd-infer-sklearn:3`, an
image with no adapter source in it** (smoke `ok`; a real ROI run produced **9/9 per-cell COGs +
STAC in 8.2 min**), and the **QGIS eyeball passed**. `notebooks/e2e_austria_aml.ipynb` was updated
to match — cell 18's seven-step per-model image build is gone.

**Notebook session 2026-08-19 (later still) — one accepted change, one rejected shape, one leak
closed.** `notebooks/e2e_austria_aml.ipynb` is **gitignored, and it is reference material** — an
example of how a user drives fsd's Azure path, **not** a scratch harness. It was edited this
session without being asked to be; the user's correction is recorded below and in memory.

**Kept.** The inference image's name/version pin moved up beside the training one (one config
block), so the inference cell is two lines. The three long `"""…"""` scratchpad docstrings that sat
above the calls became one-line issue pointers, with their text verbatim in a closing **"Known
rough edges"** cell.

**Rejected and removed by the user: an upfront preflight cell.** The design constraint, which
generalises past this notebook: *a check belongs at the step it protects, in sequence.* A block at
the top that validates everything at once must hardcode input paths and assert artifacts that later
cells create — it checked `demo_model/my_adapter.py`, which the "Preparing model adapter" section
creates much further down. That reads as a harness, not as usage. The surviving fact is real
(`_aml_preflight_common` runs per **dispatch**, so the *inference* image is validated last, ~30 min
in) and now lives in `RECIPES.md` → "Check an AML environment pin at the step that uses it", as a
three-line check placed before `run_inference`.

**Leak closed:** `notebooks/runbook-45.ipynb` was **untracked and not ignored**, carrying a live
storage URL, two GUIDs and the rg/workspace/cluster names in source *and* outputs — one `git add -A`
from publishing them. `.gitignore` now ignores `notebooks/*.ipynb` as a class (no notebook is
tracked; `notebooks/README.md` still is) rather than naming files one at a time.

**`ruff` pinned to its rule set.** `ruff` is unpinned in `[dev]` and 0.16 widened its *default*
selection, so the documented `ruff check src/ tests/` reported **357 pre-existing** hits on
unchanged code. `[tool.ruff.lint]` now carries an explicit `select = ["E4","E7","E9","F","I"]` —
ruff's historical default plus import sorting. `src/ tests/ demos/ examples/` is clean again.

**Three issues filed** from the notebook's own notes: **#67** a standard helper for verifying an
inference image (today a run-book script + two env vars); **#68** datacube paths do not reflect
calendar-aware mosaicing (one run, two date-range folders); **#69** redundant child grid cells when
the ROI is itself a grid cell. Already filed and still open: #64 / #65 / #66.

**Six issues from the notebook are now specced, not yet signed off (2026-08-19, latest).**
`gh issue create` filed the last three — **#70** `save` does not report what it embedded, **#71** a
sibling import is not auto-detected, **#72** `code=` files from two trees break the import root —
joining #67/#68/#69. All six are designed in two drafts, each commented onto its issues:

| spec | issues | the one sentence |
|---|---|---|
| **45** `bundle-transparency-and-image-verification` | #70, #71, #72, #67 | spec 44 made the bundle carry its adapter; spec 45 makes it **say what it carried** and **refuse to be born broken** — plus `fsd.model.verify_image`, the run-book smoke promoted into the library |
| **46** `run-addressability-and-grid-dedup` | #68, #69 | a run's path should be a function of what was **requested**; a work unit another already covers should not be dispatched |

**Both defects in spec 46 were measured this session, not inferred:**
- #69: `roi_to_s2_grids` on the single-cell ROI emits **9** cells and **8 of them are fully covered
  by the ninth** — 89 % waste. The predicate has to be `covered_by`, not `contains` (`contains`
  caught only **2 of 8**: a clipped sliver *shares boundary* with its coverer, which `contains`
  excludes) and not IoU-1 (that means *identical*, which none of the 8 are). On the 300-cell AT_ROI
  the same rule costs **0.09 s** and drops **1** cell — safe on the normal case, decisive on the
  degenerate one.
- #68: the export path is built from each cell's *actual* min/max acquisition
  (`create_datacube.py:147-151`) while the calendar anchor that sets `T` is the *caller's* window —
  so the path both splits one run in two and implies a window the cube does not have.

**BOTH SPECS ARE SIGNED OFF (user, 2026-08-19).** Two decisions were the user's: a detected but
unembedded sibling import makes `save` **refuse, naming the file** (not auto-embed — `code=None`
keeps one meaning), and the run folder **encodes `mosaic_days`** (`20180401_20180930_m20`), so the
path identifies the cube contract completely. The four secondary questions were resolved with
defaults recorded in each spec's §7/§6 — overturn any of them in review.

**Specs 45 and 46 are IMPLEMENTED, REVIEWED and MERGED to `main` (2026-08-19) — see the entry
below.** Both specs' acceptance criteria are met, `pytest -q` is green (mpc-extra gap aside,
pre-existing), and `ruff check src/ tests/ demos/ examples/` is clean. Issues #67–#72 are closed
against the merge commit and the `worktree-specs-45-46` worktree/branch are pruned.

**Spec 47 is IMPLEMENTED and MERGED to `main` (2026-08-20) but NOT YET REVIEWED — see the entry
below, and the pointer memory `spec-47-review-handoff` for the next session's starting point.**
**→ NEXT: an independent Opus review of the merge (`ff8d088..2e5b3b3`), then `git push` `main`** —
push is outward, so it stays the user's call (CLAUDE.md, "push only when asked"); `main` is 5
commits ahead of `origin/main` as of this entry.

**Also still open:** **spec 44 phase 2** (`deploy` registration, D7/D8) — specified but **NOT
signed off**; §8 questions 5 and 7 (blob store vs MLflow-via-AML-workspace) are the live decision.
Run-book 45 Phase 3 (the migration boundary) is documented but was never formally walked.
**`main` has ~16 unpushed commits** — pushing is the user's call.

**Also next:** the spec 41 **P7 D13 cold-start gate** — the user, on a fresh clone and fresh venv,
follows `docs/tutorial.md` *literally* and reports the first instruction that doesn't work (a
spec-24 `_result.json`; no improvising, no fixing-as-you-go). The docs are drafted **and reviewed**
(4 findings, all fixed — entry below); `pytest -q tests/test_docs.py` (153 passed) + `ruff check
src/ tests/ demos/ examples/` are clean. After the gate passes, P7 is done and the remaining open
items are the rslearn Plan B/C decision and spec 43 (`docs/history.md`, deferred).

---

## Most recent entry

## 2026-08-22 (later still) — the Opus review of step 0: one real defect, fixed; merged to `main`

Opus `/effort high` review of `c0290fb` against spec 51 D1-D3/D9/D11 + AC1-5/11/13. Verdict on the
three flagged calls: **1 confirmed, 1 confirmed, 1 overturned and fixed** — plus one defect of the
same class the review found on its own. Suite **890 passed / 91 skipped / 1 pre-existing failure**,
ruff clean. Merged `--no-ff` into `main`; worktree pruned; **pushed at the user's request —
`main` @ `2b5ae4b` is level with `origin/main`.**

**Call 3 OVERTURNED — and the consequence was worse than the handoff described.** Reproduced
against the real code, not reasoned about: when a competitor completes `v1` in the TOCTOU window,
`publish` did not merely leave a confusing gap — it **returned `1`**, while `v1` held the
*competitor's* bundle and the caller's staged copy sat nested inside it as `v1/.staging-<uuid>/`.
A caller resolving `crop-rf:1` would have run a model it never published. That is not §5's
signed-off "gap in the sequence"; it is a silent wrong answer, and it also breaks D2's "a version
directory, once written, is never rewritten".

The root cause was **one level below the registry**: `storage/fs.py::rename` documents itself as
"`os.rename` locally" — the exact property D2 cites when it calls `fs.rename` the atomic-publish
primitive — but it delegated to fsspec's `LocalFileSystem.mv`, which is `shutil.move`, which
**nests** rather than raising. The spec was signed off on a premise about fs.py that was false.
Three fixes, smallest first:

- `fs.rename` now calls `os.rename` directly when both ends are local, falling back to fsspec's
  copy-and-delete only on `EXDEV`. A directory rename onto a non-empty directory now raises; a
  *file* rename still replaces atomically, so `datacube/builder.py`'s sidecar write is unchanged.
  (`CHANGES.md` records the behavior change.)
- `_write_new_version` no longer trusts the rename to have told the truth: it **re-digests what
  landed** before returning, and retries at `v<N+1>` if the directory is not its own — the same
  proof `migrate` already used to accept a copy (D11). If the winner published *identical* bytes,
  the digest matches and that version is returned, which is D2's idempotency reached by another
  route. The residual limit is stated in the docstring rather than implied: a backend whose `mv`
  merges prefixes can still interleave two writers, and that would need the lock §5 declines.
- **Found in review, same class:** `set_alias` rewrote `_aliases.json` **in place**, so a fan-out
  resolving `@champion` (D9's one read) could observe a half-written file mid-promotion. It now
  stages and renames. Concurrent `set_alias` calls can still lose an update — no lock — but no
  reader sees a torn file.

**Call 1 CONFIRMED (deferred, reason recorded in `publish`'s docstring).** The O(N-versions)
content re-read at publish time is accepted: `publish` is rare and deliberate, and it is not the
hot path D9 constrains. **Step 2 should make this loop read `_deploy.json`'s stored digest first**
and fall back to recomputing — turning N content reads into N small metadata reads. Doing it in
step 0 would have meant inventing a second digest-bearing file that D7 then supersedes.

**Call 2 CONFIRMED.** The `^v(\d+)$` refusal is exactly right and the edge shapes check out: `"v"`
alone does not match, so it stays a usable alias and resolves as one; `"v007"` is refused and
`@v007` pins v7; `"V3"` is neither. One residual, not worth code: `migrate` copies `_aliases.json`
verbatim, so a hand-edited `v3` alias would survive and be unreachable — the file is not a
supported edit surface.

**Tests: +5 (12 → 15 registry, +2 storage).** All three regression tests were confirmed to **fail
on `c0290fb`** before the fixes landed, not just pass after. The race is exercised by injecting a
competitor into the rename window, which is deterministic — the handoff had assumed it needed real
inter-process parallelism.

**NEXT: spec 51 §9 steps 1-3** — `_ensure_bundle` resolution (D4), then `deploy` (D5/D6/D7), then
the `[model]` line. Step 1 will need to decide how a `name@ref` is told apart from a bundle *path*:
`parse_ref` currently accepts `abfss://…` as name `abfss` + version `//…` and fails on the version
check, which is a confusing error rather than a wrong answer, but D4's table wants it routed by
`registry=` being present.

---

## 2026-08-22 (later) — spec 51 §9 step 0 implemented (`fsd.model.registry`); hand back to Opus

Sonnet `/effort medium` session, against `specs/51-deploy-model-registry.md` §9 step 0 alone
(handoff: `handoff-spec51-step0-registry.md`, workspace root). Worktree branch
`worktree-spec51-step0-registry` @ `c0290fb`, off `main` @ `82c8e28`. **Not merged, not pushed.**
Suite **885 passed / 91 skipped / 1 pre-existing failure** (same `planetary_computer`-absent one),
`ruff check src/ tests/ demos/ examples/` clean.

**Built `src/fsd/model/registry.py`**: `publish` (idempotent by content digest, atomic via
`storage.fs.rename` from a staging prefix), `resolve` (`name:version` / `name@alias` / `name@vN`,
zero reads for a version pin, one `_aliases.json` read for an alias), `migrate` (relocate + re-digest
every version, refuses a mismatch), `set_alias`, `content_digest`. No verb touched —
`api._ensure_bundle`/`deploy` resolution is steps 1–3. `tests/test_registry.py`, 12 tests, one per
AC1-5/11/13.

**Three design calls the spec left implicit, flagged for review rather than silently decided:**

1. **No `_deploy.json`-shaped file invented for step 0.** D2 says the digest is "recorded
   alongside" the version in `_deploy.json` (D7), which doesn't exist until step 2. `publish`'s
   idempotency check and `migrate`'s corruption check both **recompute** the digest live from
   `bundle.json`'s declared files instead of persisting one anywhere — keeps the on-disk layout
   exactly D1's diagram, costs more reads at publish time (bounded by version count, never on the
   resolution hot path D9 protects).
2. **`set_alias` refuses an alias shaped `v<digits>`** (e.g. `"champion"` is fine, `"v7"` is
   refused) — it would be permanently shadowed by the `name@vN` version-pin shorthand in `resolve`
   and could never be reached. Not addressed anywhere in the spec.
3. **A race hazard past what §5 signs off on.** Version allocation pre-checks `exists(target)`
   before staging + rename, but the local backend's `fs.rename` is `shutil.move`, which — if two
   publishers land in the TOCTOU window between that check and the rename — nests the loser's
   staged content *inside* the winner's already-published version directory instead of raising.
   §5 explicitly accepts "a confusing gap in the sequence" from a race; this is closer to
   corrupting the winner's directory, a step beyond what was signed off. Documented as a hazard
   comment in `registry._write_new_version`, not fixed — a real fix needs a lock, which the spec
   explicitly says is "not worth" building for v1.

**NEXT: Opus review + debug**, per the working style's model split (implementation-session can't
review itself, and spec 50's history — a green suite + two review rounds still missing what the
first real cluster run found — is why). Sign off or overturn the three calls above before steps 1–3
(`_ensure_bundle` resolution, `deploy` itself, the `[model]` print) build on this layout.

## 2026-08-22 — spec 50 landed + pushed; **spec 51 (P6 `deploy`) signed off**; comment convention

`main` @ `6e163c5`, **level with `origin/main`**, tree clean. Suite **870 passed / 90 skipped / 1
pre-existing failure** (`test_missing_driver_deps_is_empty_when_everything_is_installed`,
`planetary_computer` absent from `.venv` — reproduces on unmodified `main`), `ruff check src/ tests/
demos/ examples/` clean.

### Spec 50 — closed out over three review rounds

Opus reviewed the Sonnet implementation (`/tmp/review-fsd-spec-50.md`), found 2 blockers + 3 more
(F1–F5); Sonnet fixed those; Opus re-reviewed and found **2 defects the fixes themselves
introduced**; then the first real AML run surfaced **2 more**. All landed and pushed.

The two the re-review caught:

- **F2's fix swallowed `setup`'s duplicate-`id_col` guard.** `setup` raises `ValueError` for a
  second, unrelated reason — its deliberate refusal of a shapefile with duplicate ids (added
  2026-07-28, after a multi-polygon ROI made `roi_to_s2_grids` repeat cell ids). The bare
  `except ValueError` caught it, printed "no tiles in range/overlap" (false) and recorded the shapes
  known-empty: a loud refusal turned into quietly missing training data. Fixed with a dedicated
  `NoWorkUnitsError(ValueError)` subclass, so every existing `except ValueError` caller (notably
  `verify_adapter`) is unaffected.
- **F4's fix made the known-empty manifest load-bearing but write-only.** Once a cell was recorded
  empty, a forced rebuild (`overwrite="datacubes"`/`True` — D5's documented escape hatch)
  legitimately restored its `input.csv` row while the request-side identity kept subtracting it:
  permanent mismatch, F4 relocated rather than fixed. Fixed with `_forget_known_empty` /
  `_clear_known_empty`.

The two the **first real AML run** surfaced (user reported `create_training_data` apparently stuck
after `[plan] will run:`):

- **Stale pre-D6 `input.csv` rows were adopted.** `_row_matches_window` compared run *parameters*,
  which is not sufficient once D6 changed the path shape: a row written before it matches every
  parameter while still naming the pre-digest folder. Consequence was silent — the plan announced a
  full rebuild while the build leg, reading the row's own stale `datacube_filepath`, found the old
  cube present and dispatched **nothing**, and the flatten stamp then recorded paths the
  request-derived identity can never reproduce. `_row_matches_path` now makes the derived path part
  of what makes a row current.
- **The cube-presence sweep was a silent serial walk.** `_cube_present` is four blob round-trips per
  cell and ran per cell, serially, in **two** places with no output: ~3600 sequential round-trips at
  900 cells, ~20 min over the WAN, indistinguishable from a hang — while `setup` has used 16 threads
  for the same class of I/O since spec 47. Presence now resolves from **one recursive listing per
  `<window>` folder** (`storage.fs.find_sizes` → `_present_cube_ids_at`), compared in memory by the
  `<id>` path leaf so it never reconciles local `abspath` against a backend's path spelling.
  Unlistable folders fall back to per-path checks that are concurrent **and** ticked.

**Notebook `notebooks/e2e_austria_aml.ipynb` updated** (cells 3 and 8) for the backward walk: the
`[plan]` block, `TRAIN_RUN` now optional (#83 fixed), `_manifest.json`, and a prominent warning that
D6's path change **orphans cubes built before it** — the next run is a one-time full 900-cube
fan-out, not a resume (`20180401_20180930_m20` → `20180401_20180930_m20_cc38ae79`; `verify_adapter`
moves to `..._1adc8caa`). The notebook is gitignored, so this is not in git.

### Spec 51 — P6 `deploy`, SIGNED OFF 2026-08-22, NOT implemented

`specs/51-deploy-model-registry.md` (588 lines, D1–D11, all seven §7 questions answered).

**What it decides.** `deploy` binds a **saved** bundle to the inference image **proven** to run it,
under one immutable name. Registry = a prefix on the storage seam (no new infra; `rise`'s storage
account and RBAC already exist). Immutable versions + a content digest; **aliases** are the only
mutable pointer (`crop-rf:3` for a version — spec 44 D7's spelling — `crop-rf@champion` for an
alias, bare `crop-rf` refused). `deploy` refuses an unverified pair, a bundle without declared
`requirements`, and a live adapter.

**It completes `specs/44` phase 2 (D7/D8)**, proposed in July and never signed off, and finally
answers spec 44's §7 Q7 (MLflow — no, out of scope; analysis retained in §6 so it can be reopened
cheaply). It removes spec 44 D8's **measured 627 s per run** of redundant bundle re-upload.

**D11 is the one to remember:** the central registry location is undecided *on purpose*, so nothing
the registry writes may contain an absolute path, a URL, or the registry root. Relocation is then a
copy plus a changed `registry=`, verified by re-computing the D2 digest. `migrate` therefore ships
in §9 **step 0**, not later.

**Left open deliberately, both recorded in §6/§7:** where the central registry finally lives, and
public model hosting (Hugging Face as a separate `fsd.publish` verb, *not* a D10 backend — a public
bundle advertising a private `fsd-infer-sklearn:6` would promise a binding no outsider can act on).

### Comment convention (issue #85)

`src/fsd` measured at 28% prose / **0.49 prose lines per code line**, 986 backward references across
422 functions. Classifying 3,188 substantive prose lines: 18% pure development history, 3% history
around a why, 11% pure rationale, 68% plain description — so the narrative is not the bulk; the
**tag density** is what makes it read like a changelog. `docs/reference/code-comments.md` states the
rule as **cut the changelog, keep the hazard**, applied to `storage/` as a worked sample (1.05 →
0.82 prose per code line, 27 → 2 refs, proven comments-only by comparing ASTs with docstrings
stripped). The rest of the sweep is **issue #85**, to be done *before* the next major development
push. `fs.py`'s reverted `_write_with_retry` block moved to `DROPPED.md`'s new "Approaches tried
inside fsd and reverted" section.

### NEXT — implement spec 51 (Sonnet, `/effort medium`)

Against `specs/51-deploy-model-registry.md` §9, in order. **Step 0 first and alone**:
`fsd.model.registry` — layout, `publish`, `resolve`, `migrate`, `_aliases.json`, the content digest.
Pure local-filesystem unit tests, no verb touched, no Azure. Steps 1–3 (resolution in
`api._ensure_bundle`; `deploy` itself; the `[model]` line) follow.

Known trap for that session: `EnterWorktree` branches from `origin/main`; and tests inside a
worktree import the **wrong** `fsd` unless `PYTHONPATH=$PWD/src` is set, because the shared `.venv`'s
editable install points at the main checkout's `src/`.

## 2026-08-21 — spec 50 §9 steps 0/1/2/4 implemented and merged; hand back to Opus for review

A Sonnet session (`/effort medium`) implemented spec 50 against the signed-off spec, per
`HANDOFF-spec-50.md`. Steps landed in order, each its own commit, `--no-ff` merged to `main`
(worktree pruned per standing practice):

- **Step 0 (D6/#83).** `run_folderpath` no longer defaults to a fresh UTC timestamp for
  `runner="aml"` — the default is now the plain stable name `{root}/runs/train` (never a hash of
  the request/shape-id set, per Q1). The window path segment
  (`<startdate>_<enddate>_m<mosaic_days>`) gained a `_<params_key>` suffix, a short digest of
  `(bands, mosaic_scheme, scl_mask_classes)`, so two requests differing only in `bands` resolve to
  different cube paths instead of silently colliding. `test_build_skip.py`'s characterisation test
  for #83 is flipped (its own docstring's instruction), not deleted.
- **Step 1 (D3).** New `api._flatten_identity_from_request` computes the same identity
  `_flatten_identity` computes from `input.csv`, but from the request (label polygon ids, window,
  params) with zero file reads — a cube's path is derivable from `(run_folderpath, window, id)`
  alone. Written and compared (a test proves the two identities agree given equivalent inputs);
  nothing short-circuits on it yet.
- **Step 2 (D2, §9 phase 1).** `create_training_data`'s preflight splits into two waves: structural
  checks raise first, then the target (arrays + `_flatten_stamp.json`) is checked BEFORE the
  catalog/download preflight wave — a fully-resumed call now needs `catalog_filepath` to exist no
  more than it needs `setup` to run. Prints the D7 `[plan] ... CURRENT` / `[fetch] ...` lines.
- **Step 4 (D2/D4/D5/D7, §9 phase 2).** New `create_datacube.build_shortfall_only`: cube targets are
  enumerated from the request alone (no catalog access), so `setup` runs only for shapes whose cube
  is missing and not already known-empty. A sibling `_manifest.json`, keyed to the window/params
  segment, records known-empty cells so they are never rediscovered (two identical re-runs both
  converge to a shortfall of 0). Existing `input.csv` rows for a DIFFERENT window/params are purged
  first — deliberately narrower than D9 (which would let rows from different windows coexist
  forever, exactly what makes #84 possible): this only ever grows `input.csv` within one window.
  `run_create_datacube` gains this as an alternative to `overwrite_setup_csv`'s legacy path (kept,
  unremoved — that removal is step 3); `create_training_data` opts in unless the caller explicitly
  forces a cube rebuild.
- **A real bug caught by `test_tutorial_fixture.py`** (id_col=`"fid"`, not `"id"`): `setup` always
  writes the id column as `COL_ID` ("id"), never the caller's own `id_col` name — reading back
  `input.csv` via the caller's `id_col` crashed with `KeyError`. Fixed in `build_shortfall_only`.

**Step 3 (D9, `overwrite_setup_csv` removal) deliberately NOT done** — the spec's own ordering
constraint: D9 makes multi-window training data reachable, and it is broken one layer up (`ids.npy`
has no window component, `median_per_id` silently medians two windows of one field into one sample)
until #84 is fixed. `overwrite_setup_csv` still exists in the signature.

**Spec 50 §4 acceptance criteria: all met except AC7c** (its `input.csv` accumulate-across-windows
assertion depends on step 3). 24 new/updated tests in `tests/test_backward_walk.py` +
`tests/test_build_skip.py`, including AC11 (identical behaviour under `runner="local"`/`"aml"`,
parametrized). `runbooks/48-e2e-austria-with-verify-adapter.md` updated: the `TRAIN_RUN` pin is now
an optional override, not a requirement, since #83 is fixed.

**Gate:** full suite 860 passed / 92 skipped / 1 pre-existing failure (`planetary_computer` missing
from `.venv`, reproduces on unmodified `main`), `ruff check src/ tests/ demos/ examples/` clean.
`main` is **7 commits ahead of `origin/main`, unpushed** — pushing is the user's call.

**NEXT:** hand back to an Opus session for review (an authoring session cannot review itself, per
the definition of done) — in particular the design call in step 4 (purge-other-window-rows to stay
narrower than D9) and the `overwrite_setup_csv=build_overwrite` wiring are the two judgment calls
most worth a second look.

## 2026-08-21 — **spec 50 signed off**: resolve backwards from the target; #83/#84 filed

The user asked what the current skipping approach is and proposed the Snakemake **rule** shape —
check the output, and if it must be produced, check its inputs, recursively. Investigating it turned
up two defects and one designed-but-unreachable capability.

### The measurement that started it

A fully-resumed `create_training_data` still paid a complete `setup` pass: **`[setup] 900/900 shapes
| elapsed 96s`**, ~1800 blob writes, on a run where every cube already existed. `setup` runs on every
call because `overwrite_setup_csv=True` deletes `input.csv` first. Each leg does its own preflight
*before* its skip can be evaluated, so the cheapest question ("are the arrays already here?") is
asked last.

That makes spec 49 **not actually delivered**: its acceptance sentence is the user's own — *"the only
task create_training_data does is to download the flattened numpy arrays"* — and all 11 of its
criteria pass because every one is written against `input.csv` and `run_create_datacube`, none
against *what ran before the skip*.

### `specs/50-backward-walk.md` — SIGNED OFF, all six §7 questions answered

Two answers overturned the draft, and both improved it.

- **Q1 → D6: no set hash, address per path.** The draft wanted the run folder named from a digest of
  the request including the sorted shape ids. Rejected: that makes the *group* the unit of
  addressing, so one added polygon invalidates all 900 cubes. Address per path and let
  `<params>/<id>` carry the granularity `setup` already builds. **One correction the path needed:**
  the middle segment is `<window>_m<mosaic_days>` while the row identity `_UNIT_IDENTITY_COLS` also
  includes `bands`/`mosaic_scheme`/`scl_mask_classes` — so two requests differing only in `bands`
  resolve to the **same path** today, the second overwriting the first while the build skip reads it
  as present. The segment gains a digest of those *shared* parameters. Still a digest, not the
  rejected one: it digests what every cell shares, never the set of cells. → memory
  `fsd-addressing-granularity`.
- **Q3 → D9: `input.csv` accumulates.** The user recovered the real rationale for the delete, which
  inverts the previous day's finding. `setup` appended so it could be run repeatedly with different
  windows, accumulating units; the delete was a workaround for a missing dedupe. **The "true
  solution" already exists in fsd** — `_dedupe_on_unit_identity` (spec 38 D13, #53), whose docstring
  states the intent verbatim. So `overwrite_setup_csv` does not merely predate the fix, it
  **defeats** it: deleting `input.csv` leaves nothing to append to or dedupe against. That is why
  accumulate-across-windows has been unreachable since day one and why nobody noticed the mechanism
  was already written.
- **Q5** both phases committed. **Q6 → D10**: `verify_adapter` always verifies — the cube is an input
  and may resume, the adapter run is the work and never does. **Q2/Q4** as proposed.
- **D3 is the load-bearing decision**: the flatten identity moves from `input.csv` (which is
  `setup`'s output — the knot) to the *request*. Sound because a cube's path is derivable from
  `(run_folderpath, window, id)`; `setup`'s catalog filtering builds a cube, it does not name one.
- **D1 keeps spec 49 §6's constraint**: the walk is fsd's own, on the driver, above the runner seam.
  Snakemake is the model, not the mechanism — the AML runner still has no DAG.

### Two issues filed, one of which gates D9

- **#83 — spec 49's skips cannot fire by default.** `run_folderpath` defaults to
  `{root}/runs/{fresh UTC timestamp}`, so every re-run addresses cube paths that have never existed:
  the shortfall is always N of N and no stamp can match. Found in real use — the user's resumed run
  dispatched all 32 shards twice. Worse, `_build_shortfall` prints **nothing** in the N-of-N case
  (a full dispatch is not a skip), so it fails silently. **`runner="local"` was never affected**
  (its run folder is `export_folderpath/run`, no clock). Spec 50 D6 fixes it; `TRAIN_RUN` in the
  notebook is the workaround today.
- **#84 — multi-window training data is silently wrong**, and D9 is what makes it reachable.
  `ids.npy` carries no window component, so two windows of one field collide, and `median_per_id`
  (`np.unique(ids)` + `np.nanmedian`) merges them into **one sample that is the median of both
  years** — no error, no shape mismatch. `aggregate="median_per_id"` is what the Austria demo uses.
  **§9 records the ordering constraint: D9 must not land before #84's array-layer fix.**
  Reachable-and-wrong is worse than unreachable, and the delete is currently protecting us from it.

### Also this session

- **Specs 48 + 49 Opus-reviewed and their defects fixed** (entries below): `_result.json` was never
  written; an unstamped cube was reused then mis-stamped; and `verify_adapter(runner="aml")` could
  not have worked at all — it handed the AML node an absolute *driver* path to write the cube to.
  All three carry red-first regression tests. #76 and #77 filed.
- **`notebooks/e2e_austria_aml.ipynb`** (gitignored) now runs `verify_adapter` between the adapter
  and bundling cells, and carries `RESUME_RUN` + `TRAIN_RUN`. `runbooks/48-e2e-austria-with-verify-adapter.md`
  is the two-pass run-book; its Pass B was corrected once #83 was understood.
- **`tests/test_build_skip.py`** now characterises which paths are clock-derived. Only three exist in
  `src/`; only `create_training_data`'s feeds a skip. **`run_inference` is structurally immune** —
  its run folder is `output_folderpath/cells`, named by the caller, which is why spec 47 D5's
  per-cell output skip works today. (It still decides that skip *on the node* — #77.)
- **PROGRESS.md archived** back to the spec-47 review (spec 41 D12): it had reached 981 lines.

### NEXT — implement spec 50 (Sonnet, `/effort medium`)

**Handoff doc: `HANDOFF-spec-50.md` at the WORKSPACE ROOT** (outside the repo, as before — it names
the untracked files that carry real Azure values). It holds the traps, the definition of done, and
the verified test baseline (**847 passed, 92 skipped, 1 known pre-existing failure** on `a00702f`).
The `/handoff` session baton is `/tmp/handoff-fsd-spec-50-implementation.md` — ephemeral, and it
points back here.

§9 order: **0** #83/D6 deterministic run folder → **1** D3 request-derived identity → **2** phase 1
top-level short-circuit → **3** D9 append+dedupe **(BLOCKED on #84)** → **4** phase 2 the full walk.

**Steps 0, 1, 2 and 4 are unblocked. Step 3 is not** — decide #84 first, or hand off with D9
explicitly deferred.

### Gate

`main` @ `5a0a4e5` + this entry, **18+ commits ahead of `origin/main` and unpushed.** Pushing is the
user's call and has not been asked for. Nothing in `src/` has been touched for spec 50.

## 2026-08-21 (later) — `verify_adapter` wired into the AML e2e notebook; a third review defect found

The user asked to re-run `notebooks/e2e_austria_aml.ipynb` on the specs 48+49 code, with
`verify_adapter` added after the adapter is written. Wiring it up surfaced a defect the review had
not: **`verify_adapter(runner="aml")` could not have worked.**

**The defect (fixed, `7d0f780`, merged `126c75f`).** The verb passed
`run_folderpath=export_folderpath/_build` — a *local* path — to the per-cell build unit.
`create_datacube.setup` turns a local `run_folderpath` into an **absolute driver path**
(`os.path.abspath`) and writes it into `input.csv`, which on `runner="aml"` is read by the **node**.
So the node was told to write the cube to `/Users/<driver>/...`, which does not exist on it. The
build now roots on `runner_kwargs["root"]/runs/<run_id>/_verify_adapter` exactly as
`create_training_data` roots its own run, and the cube is transferred DOWN into the local
`export_folderpath` — which is what D5 said landing was all along. `runner_kwargs["root"]` is now
required for `runner="aml"`. Two red-first tests.

**Why the ACs missed it, worth remembering:** AC1's test monkeypatches `run_create_datacube`
wholesale, so it asserts *how many* builds happen and never *where*; AC10's real end-to-end runs
`runner="local"`. A spec can have a fully-tested criterion for "the case that matters in practice"
and still never execute that case.

### Notebook changes (`notebooks/e2e_austria_aml.ipynb` — gitignored, not committed)

- **`RESUME_RUN` in the config cell.** `ROOT` carried a fresh timestamp every run, so *none* of
  spec 49's skips could ever fire — a re-run addressed a brand-new archive. `RESUME_RUN` pins a
  previous run id back. Without this the notebook could not demonstrate spec 49 at all.
- **A `verify_adapter` section between the adapter and the bundling cells**, which is where the
  notebook's own "To do" already asked for it (*"test out the adapter before bundling"*, *"create
  one single datacube … and run via adapter"*). Takes the **live** adapter, so the run exercises
  bundling too; `cell=None` for the deterministic pick; `export_folderpath` keyed to `RUN` because
  the resume stamp covers the request but **not** `catalog_filepath`.
- The bundling cell no longer re-constructs the adapter — one source of truth for `n_timestamps`,
  and nothing is bundled that has not had real pixels through it.
- Expectation blocks updated for spec 49's `[build]`/`[flatten]` lines, including the one-time
  "the first resume re-flattens because the stamp did not exist yet" case; `#76`/`#77` and the
  archive-identity gap added to "Known rough edges".

### Run-book

`runbooks/48-e2e-austria-with-verify-adapter.md` — two passes: **A** fresh (nothing to skip), **B**
resumed with `RESUME_RUN` (the actual spec 49 test). Claude does not run it; the user pastes back
each step's result block. The QGIS check on `output.tif` is step A4 and is the deliverable, not the
verdict dict.

### Gate

`main` @ `126c75f` + this entry, **unpushed**. The notebook is gitignored and stays that way.

## 2026-08-21 — specs 48 + 49 **Opus-reviewed**: 2 defects fixed, #76/#77 filed

Independent Opus review of `20a47e7..c0d9d17` (the Sonnet implementation entry below), per the
standing practice that the authoring session cannot be its own reviewer. Fixes in `4989025`.

**Verdict: all 25 acceptance criteria are met** — spec 48's 14 and spec 49's 11. The two
structural ACs are genuinely asserted rather than assumed (`test_no_verify_adapter_branch_in_
shared_inference_code` greps `engine`/`infer_only_task`/`bundle` for the forbidden branch; the two
"no mtime" tests scan the skip logic's own source). The shared identity helper spec 49 §7 Q5
required exists exactly once, as `fsd.workflows.stamp`, and is used by both specs. Checked
independently: `pytest -q` at 836 passed / 88 skipped / the 1 known `planetary_computer` failure,
`ruff check src/ tests/ demos/ examples/` clean, and
`test_verify_adapter_real_fixture_local_runner` (spec 48 AC10, the no-network end-to-end) really
runs rather than skipping.

| # | defect | fix |
|---|---|---|
| 1 | **`_result.json` was never written.** D8 lists it among the artifacts `export_folderpath` holds and the verb's docstring names it, but only the dict was returned — and spec 24's whole run-book protocol is the user pasting that *file* back. A failing verdict also returned in total silence. | every exit routes through `_finish_verify_adapter`, which writes the file and prints the error + path on a failure |
| 2 | **an unstamped cube was reused and then mis-stamped.** The cube landing used `_land_local(force=False)`, so a `datacube.npy` that merely EXISTED was skipped as "already landed" — and `write_stamp` then recorded THIS request's identity over the previous request's pixels. Reachable by deleting `_cube_stamp.json` to get past the "different request" refusal. | `force=True`: reaching that branch MEANS the local cube is not trusted. Existence standing in for identity is exactly what D5 exists to prevent — and the same reasoning was already applied correctly to the AML flatten branch |

Both regression tests were confirmed red on the unfixed code (`assert False` on the missing file,
`assert 7.0 == 0.0` on a sentinel cube surviving the rebuild).

### Cleared, not flagged

- **`_force_rebuild` and #50.** It calls `fs.rm` non-recursively on single files; #50 is specific to
  `rm(recursive=True)` on `abfss://`, so it does not apply.
- **Spec 49 AC10** (a fully-skipped run and a full run return equal `TrainingData`).
  `_apply_training_features` persists `feature_bands` into `metadata.pickle.npy`, so the skip path
  reconstructs it from disk correctly.
- **D3 vs. a same-path rebuild.** The stamp cannot catch a cube rebuilt at the same path with the
  same parameters (no content digest — §7 Q2's signed-off default). The implementation is honest
  about it: `overwrite="datacubes"` forces the flatten leg rather than relying on the stamp, and the
  docstring says so plainly. Correct call, and the residue is Risk 1, not a defect.

### Filed, per spec 49 §7's sign-off

- **#76** — datacube writes are not atomic, so a truncated cube passes spec 49 D2's presence test and
  is skipped as built (Q2; #74 one level up, and the `.part`+rename primitive already exists).
- **#77** — `run_inference`'s build leg still pays a cold start to discover work already done: its
  per-cell skip is decided on the node, after dispatch (Q6; the #64 shape once more).

### Not addressed, deliberately

- **`cell="random"` twice into one `export_folderpath` now raises** rather than building the new
  cell — the D5 identity includes `cell`, so a fresh random pick reads as a different request.
  Defensible, but D3 sells random as the way to sample an ROI. Wants a docstring sentence or a
  per-cell subfolder; neither is a defect against a written AC.
- **The "no mtime" guards are substring scans** (`getmtime`, `st_mtime`, `os.stat`, `.stat()`) and
  would not catch the fsspec route (`fs.info(...)["mtime"]`); `api._artifacts_present`, which the
  flatten skip depends on, is not in the scanned set. No such call exists today, so AC6 holds.
- **Driver-side cost grows with N:** `_cell_coverage` runs one full-catalog `filter_gdf` per grid
  cell (299 passes on AT_ROI when `cell=None`), and `_cube_present` costs 4 storage round-trips per
  cube (~3,600 for 900) where one prefix listing would do. Both spec-sanctioned; both worth an issue
  if a re-run ever feels slow before it feels wrong.

### Gate

`main` @ `0d9bfef` is **5 commits ahead of `origin/main` and unpushed** — the implementation
(`16f688c`) and its merge (`c0d9d17`), then this review's two commits (`4989025` fixes + tests +
spec headers, `77c9ce0` this entry) and their merge. Pushing is the user's call.

## 2026-08-20 (later) — specs 48 + 49 signed off; notebooks made public; **NEXT: Sonnet implements both**

Handoff doc: **`HANDOFF-specs-48-49.md` at the WORKSPACE ROOT** (outside the repo — it names the
untracked file that carries real Azure values). `main` @ `3fedd1f`, **pushed**, tree clean.

### Two specs, both signed off with §8 cross-validation complete

| spec | verb / change | the decision most likely to be got wrong |
|---|---|---|
| **48** `specs/48-verify-adapter.md` | new `fsd.verify_adapter` — build ONE cell's cube on AML, land it locally, run the adapter over it, return a verdict + an `output.tif` for QGIS | **D6**: the inference leg must call `workflows.infer_only_task.run_infer_only`; **no branch may say "if verify_adapter"** (AC6). If local and cluster can differ, the verb is worthless. |
| **49** `specs/49-skip-work-already-done.md` | skip the datacube build when every cube is present, and the flatten when its arrays came from exactly those cubes | **D3**: keys on **identity, never modification time** (AC6 asserts no mtime is read). |

**The gap spec 48 closes:** every existing gate asks *"would the adapter import?"* — `bundle.save`'s
refusals, `_wheel_has_spec44`, `adapter_smoke` (whose own docstring says "No pipeline logic"),
`verify_image`. **Nothing runs `predict` on real pixels until the 299-cell fan-out.** An adapter
with the wrong `n_timestamps`, a `feature_sequence` emitting the wrong band set, or a `predict`
returning the wrong dtype imports perfectly and smokes green.

**Naming took three passes and is closed:** not `dry_run` (means "execute nothing" universally),
not `test_adapter` (pytest collects `test_*` even when only *imported* — would have broken fsd's
own suite), not `adapter_smoke` (already taken by `fsd.workflows.adapter_smoke`, and a "smoke test"
means synthetic-data format checking). `verify_adapter` follows `verify_image`'s existing precedent.

**Spec 49 D3 declines the mechanism originally proposed (mtime), and §8 backs it:** Bazel decides
staleness by input **content digests** where Make compares timestamps; DVC's `dvc.lock` is the same
sidecar shape (and contributed two refinements — record outputs too, treat parameters as
dependencies); and on Azure a blob's `Last-Modified` is **read-only and cannot be back-dated by any
means**, so a timestamp physically cannot carry "when this content was produced". That last finding
made D3's argument stronger than drafted.

**Shared piece:** spec 49 §7 Q5 signed off that spec 48 D5 and spec 49 D3 use **ONE** identity
helper, not two. Build it during 48, import it in 49.

### Also landed this session

- **Spec 47 reviewed by Opus** (5 defects fixed, #64/#65/#66 closed, **#75** filed for D9's deferred
  existence pass). Notable: the merge progress bar was measuring header-opens, not the ~1000 s of
  pixel reads it claimed — it hit 100 % and then ran the expensive phase in silence.
- **The AML image build is documented and split.** `notebooks/00_build_images.ipynb` is **the one
  tracked notebook** (`.gitignore` un-ignores it explicitly), with `docs/howto/build-the-images.md`
  as the scrubbed public page and `notebooks/images/{base,sklearn}/` as tracked build contexts.
  Part A and Part B register independently, because `az ml environment create` **always** mints a
  new version — registering both every time churned the one you never touched.
- **`notebooks/_config.py`** is the single point where a private value enters a public notebook; it
  reads `env.local.sh` (gitignored, now 6 vars). **`tests/test_notebooks.py`** (14 tests) is what
  lets a notebook be tracked at all: no saved outputs, no GUID/email/home-dir/storage-URL/RG/
  workspace/cluster names, scanned across source *and* outputs. **Verified to fail on the
  pre-scrub file — 6 of 9 fired.**
- **`env.example.sh` stays complete (54 vars)** and marks the six the notebooks read. It was trimmed
  to 6 mid-session; that broke `test_az_var_parity` for real — `docs/` names 47 of the removed vars
  and `demos/` reads 8. The trimmed copy is on the git stash if retiring the other 48 is ever
  wanted; that needs `docs/reference/environment.md` and `demos/` to move with it.
- **Two bugs found by running things:** an AML v2 environment build is an **ACR task run, not an AML
  job**, so the `prepare_image` poll in `RECIPES.md` (since 2026-07-29) matched nothing and looped
  forever — corrected at source, and the wait is now a Studio link. And `git status --porcelain`
  over the whole tree let one stray untracked file pin every status cell to "dirty".

### Gates

**804 passed, 90 skipped, 1 pre-existing failure** (`test_missing_driver_deps_…`,
`planetary_computer` absent from `.venv`, reproduces on unmodified `main`);
`ruff check src/ tests/ demos/ examples/` clean.

### Still open

**#75** (spec 47 D9's existence pass), **#74** (atomic download writes — the prerequisite that makes
existence the right predicate), **#73**; CDSE's own no-op diff (spec 47 D8 scopes it out); spec 44
phase 2 (`deploy`, unsigned). **Gated on a successful e2e run:** tracking
`e2e_austria_aml.ipynb` + `notebooks/shapefiles/` — and note **`AT_2018_TRAIN.geojson` is
EuroCrops-derived**, so its licensing is unresolved for a public MIT repo.

---
