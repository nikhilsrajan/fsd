# PROGRESS — fsd

**Resume anchor.** Read this, then `specs/00-overview.md`. Older entries moved to
[`docs/progress-archive.md`](docs/progress-archive.md) (spec 41 D12) — this file is the *current*
state plus the most recent entry, not the log.

_Last updated: 2026-08-22 (**spec 51 §9 step 2 (`fsd.deploy`, D5/D6/D7) implemented — Sonnet
`/effort medium`, NOT YET REVIEWED by Opus, NOT merged.** Work is on worktree branch
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
