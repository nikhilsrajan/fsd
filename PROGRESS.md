# PROGRESS — fsd

**Resume anchor.** Read this, then `specs/00-overview.md`. Older entries moved to
[`docs/progress-archive.md`](docs/progress-archive.md) (spec 41 D12) — this file is the *current*
state plus the most recent entry, not the log.

_Last updated: 2026-08-19 (**specs 45 and 46 implemented** — bundle transparency/validation +
`fsd.model.verify_image`, and run-folder addressability + grid-cell de-duplication; see the entry
below. Previously same day: **spec 44 phase 1 implemented AND proven on the cluster** — the bundle
carries the adapter's source, killing the per-adapter inference image. Previously: 2026-07-31,
**spec 41 P7 drafted and reviewed** — `docs/tutorial.md` + `docs/howto/*`
(5 pages + an index) + `examples/`, 4 review findings fixed, merged to `main`; awaiting the P7
cold-start gate. Same day: the **project-state diagnostic was re-run** — the locked demo target was
hit 2026-07-29 and has no successor named; and the **rslearn spike opened** on `spike/rslearn`.)_

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
**→ NEXT: `git push` `main` — outward, so the user's call (CLAUDE.md, "push only when asked").**

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

## 2026-08-19 (latest) — specs 45 and 46 **implemented**: bundle transparency/validation + image
verification, run-folder addressability + grid dedup

Both signed-off specs (see the entry below) implemented in one Sonnet session, `/effort medium`,
per `CLAUDE.md`'s model split, then **reviewed by Opus and merged the same day**. All acceptance
criteria met; `pytest -q` (**758 passed, 1 failed, 85 skipped** — the one failure,
`test_missing_driver_deps_is_empty_when_everything_is_installed`, is the pre-existing `.venv`
`mpc`-extra gap and reproduces on unmodified `main`, not a code defect) and `ruff check src/
tests/ demos/ examples/` are both green.

**Spec 45 — `src/fsd/model/bundle.py`, new `src/fsd/model/verify_image.py`.** `save` now prints a
report by default (root, files+sizes, adapter ref, requirements; `verbose=False` silences it,
#70), refuses before copying anything if the adapter's own module wouldn't sit at the top of
`code/` (#72) or if an embedded file imports an unembedded sibling — transitively, dependencies
left alone (#71). `fsd.model.verify_image(bundle, environment=..., runner="aml", runner_kwargs=...,
build_context=None) -> dict` promotes the run-book smoke into the library (#67); `runner="local"`
raises rather than returning a false-positive pass. `runbooks/scripts/
45_phase1_generic_image_smoke.py` is now a thin wrapper over it, same `_result.json` shape. Tests:
`tests/test_bundle_transparency.py` (new, 15 tests) + `tests/test_bundle_code.py` (24, unchanged,
still green).

**Spec 46 — `src/fsd/workflows/create_datacube.py`, `src/fsd/grid.py`, `src/fsd/api.py` docstring.**
The export path is now `run_folderpath/{startdate}_{enddate}_m{mosaic_days}/<id>` — one window
folder per run, derived from the request, not each shape's actual acquisition range (#68);
`actual_start`/`actual_end` moved into the cube's own `metadata.pickle.npy`. `roi_to_s2_grids` now
drops any cell `covered_by` another returned cell, printing the before/after count (#69) — a
numerically-robust `covered_by` check (raw shapely's exact predicate missed 6 of 8 redundant cells
to floating-point noise on the real `s2grid=476da24` ROI; a relative-area-tolerant version catches
all 8), tie-broken deterministically by smaller `id`, coverage-preserving by construction.
**Re-measured against the real shapefiles** (`shapefiles/s2grid=476da24.geojson`,
`shapefiles/AT_ROI.geojson`): `9 -> 1` and `300 -> 299` exactly as the spec's before-numbers
predicted, `299` in ~0.075 s. `CHANGES.md`, `RECIPES.md`, `LIMITATIONS.md`'s stale AT_ROI/Phase-1
cell counts updated. Tests: `tests/test_grid.py` (+5), `tests/test_workflows.py` (+1),
`tests/test_datacube_builder.py` (assertions added to the existing end-to-end test).

**Review (Opus, `/effort high`, same day) — one real defect found and fixed, plus four
non-behavioral cleanups.** The defect: the new AC7 test ran
`runbooks/scripts/45_phase1_generic_image_smoke.py` as a subprocess with its **default** output
path, so every `pytest -q` in a working checkout **overwrote
`tests/outputs/spec44_verify/_result_phase1.json`** — which holds the result of the REAL Phase-1
cluster run the user pastes back per spec 24. The script gained an `--out <dir>` override (same
argv convention as `34_mixed_baseline_slice.py`'s `--dst`) and the test now writes to `tmp_path`.
Cleanups: `verify_image` no longer leaks an open `ZipFile` handle, its dead `if req_problems:
pass` branch became a plain comment, and its docstring now admits it also raises on missing
`runner_kwargs`; `bundle.py`'s double-`sorted()` in the D3 fix message collapsed to one.
**Reviewed and accepted as-is:** `_covered`'s tolerance choice (relative to the *candidate's own*
area, so scale-safe; the deviation from D4's literal "the predicate is `covered_by`" is now
recorded in spec 46 D4 itself), and `_check_adapter_at_top`'s culprit-naming heuristic (with 3+
files across trees it may name a different offender, but the prescribed fix — one containing
directory — is the same either way).

**Flagged for the user, NOT changed** (a spec-scope question, not a bug): spec 45 D2 now refuses
`bundle.save(installed_adapter, code=["./utils.py"])` — an adapter that really is a pip dependency
of the image, plus extra helper files. The adapter imports from site-packages regardless of what
`code/` holds, so the at-top check is irrelevant there, but D2 as written has no carve-out. Narrow
and previously legal under spec 44 D1 ("take the user at their word"). **Filed as #73** with the
candidate fix; needs a spec-45 amendment first, since D2 has no carve-out today.

**Not yet done:** `main` still has the pending push from spec 44 plus this session's work (user's
call, per CLAUDE.md's "push only when asked").

## 2026-08-19 (later) — spec 44 phase 1 **proven on the cluster**; three run-book defects fixed on the way

`runbooks/45-verify-bundle-carried-code.md` Phases 0–1 are **green**. The D11 adapter-import smoke
returned `{"status": "ok"}` on **`fsd-infer-sklearn:3` — an image built with no adapter source in
it** — with `my_adapter:CropRF` resolved purely from the bundle's `code/`. Acceptance criterion 12
is met. The notebook's cell-18 procedure (4 hand-written files + `pip wheel` + `az ml environment
create` + a smoke job, repeated on every adapter edit) is **obsolete**.

Getting there exposed three defects **in the run-book, not in fsd** — worth recording because each
would have recurred:

1. **The smoke was documented as a local command.** It would have passed trivially on the driver
   (which has the adapter on `sys.path` and its deps installed) while proving nothing about the
   image (ADR 0002). It is now submitted as an AML job, like run-book 38 Phase 0. It also never
   staged the bundle.
2. **The driver's `RuntimeError: job(s)/shard(s) failed` hid the node's real error.**
   `_aml_submit_and_wait` raises before the status file can be read. The script now always reads
   `_status/*.json` back into `metrics.smoke_error`, and treats a *missing* status file as its own
   diagnosis (the job died before the entrypoint → image or node auth).
3. **The image's fsd *wheel* must be rebuilt, not just the Dockerfile.** This was the actual
   failure: a pre-spec-44 wheel has no `manifest_code_files` and no `_activate_bundle_code`, so the
   node never fetches `code/` and never puts it on `sys.path` — `ModuleNotFoundError` however good
   the bundle is. **The node cannot self-diagnose this** (an fsd old enough to cause it contains
   none of the code that would report it), so the gate has to be driver-side: the optional
   `AZ_INFER_BUILD_CONTEXT` makes the script inspect the wheel and refuse to submit against a stale
   image, in 2 s instead of a 40–380 s cold start.

**Generalisable lesson for any future image-carried change:** stripping a `COPY` from a Dockerfile
is necessary but not sufficient — the wheel baked into the image is the thing that has to move.

**Phase 2 followed the same day and is green:** a real ROI run over `s2grid=476da24` (single MGRS
tile T33UWP, Apr–Sep 2018 @ 20 d → T=10) on that same adapter-less image produced **9/9 per-cell
`output.tif` + a STAC catalog in 494.9 s**, run `spec44-phase2-20260819T143617Z`. Two further
authoring bugs were caught there, both in the run-book script and both by fsd's own guards rather
than by the cluster: `storage=` takes a **backend name** (`"azure"`), not a URL — the URLs are
`output_folderpath`/`catalog_filepath`; and `run_aml_inference` needs
`cluster`/`environment`/**`root`**/`identity_client_id` **plus** an `ml_client`. The proven shape
was in `demos/e2e_austria_aml.py::step_inference` the whole time — **check the working caller before
writing a new one** is the lesson, and it would have saved two round trips.


## 2026-08-19 — spec 44 written, signed off, and **phase 1 implemented**: the bundle now carries the adapter's source

**The problem.** Running inference on AML needed a *second, adapter-specific* Docker image, because
the bundle carried only a code *reference* (spec 38 D4). Delivering one ~40-line `my_adapter.py` to
the nodes cost 4 hand-written files (Dockerfile, `.dockerignore`, 2 AML YAMLs) + `pip wheel` +
`az ml environment create` + a smoke job — **repeated on every adapter edit**, while retraining the
model itself cost nothing (the bundle already carried the weights).

**The change.** *Code moves into the bundle; dependencies stay in the image.* `bundle.save` embeds
the adapter's source under `code/` (auto-detected, package layout preserved); `bundle.load` prepends
it to `sys.path`. The inference image now differs only by **dependency family** (sklearn vs torch),
never by model or adapter.

**This REVERSED two LOCKED decisions in spec 38 D4** (the adapter-is-never-in-the-bundle rule, and
"P6 `deploy` builds the image"). Signed off by the user the same day; spec 38 D4 now carries a
supersession note and `runbooks/38` lost its per-adapter image steps. Everything else in D4 stands —
dedicated Environment, operator owns the build, reference-by-name, deps front-loaded to build time,
D11 smoke gate.

**Landed:** bundle format **v2** (v1 still loads unchanged); origin classification
(local → embed / installed → skip / `__main__` → refuse with the fix in the message); a `sys.path`
collision guard; per-origin drift messages; optional declared `requirements` checked by the smoke
job (never installed, via `packaging`); `code` files carried by both manifest-driven transports.
**23 new tests** (`tests/test_bundle_code.py`), mutation-checked.

**Amendment A1, found during implementation:** D2's collision guard as signed off compared *paths*,
which would have broken save-then-load in one process (`api._ensure_bundle`, and every existing
bundle test). It compares **content** instead — byte-identical is not a collision.

**Two things the user asked that shaped the spec:** whether a library (MLflow) should do this
instead — answered in §6 with measured numbers (rejected for phase 1; genuinely strong for phase 2's
registry, now open question #7); and `packaging` adopted for PEP 508 parsing rather than hand-rolled.

**Not done:** the real-cluster gate, and phase 2 (`deploy`).


## 2026-07-31 — spec 41 P7 **reviewed** (Opus): 4 doc-accuracy findings fixed, merged to `main` → NEXT: the user runs the D13 cold-start gate

Review of `worktree-p7-tutorial-howtos` against spec 41 §3/D9/D10 and D13's "must not fail" bar,
in the spirit of the P5/P6 reviews (each of which found 8 issues in a branch its authoring session
had declared green).

**`docs/tutorial.md` came through clean.** Every number in it was re-derived from the committed
fixture rather than taken on trust — 36 granules / one MGRS tile `T33UWP`, 43 fields at
20 `grain_maize_corn_popcorn` / 13 `hemp_cannabis` / 10 `other`, `offset == 0` on every row, grid
cell `4772924` at the stated bounds, 27 MB on disk, date span 2018-04-01 → 2018-09-28 — all
confirmed. **The handoff's `T = 10` correction is right**, verified two independent ways through
`fsd.api.compute_n_timestamps`: the tutorial's own midnight window (2018-04-01 → 2018-09-29) and
the catalog-derived window `test_tutorial_fixture.py` actually uses (min timestamp → max + 1 day)
both give `ceil(181 / 20) = 10`. Every call in the tutorial matches
`test_pipeline_create_training_data_train_and_infer`'s real sequence and keyword names, and the
per-**pixel** return-shape statement (with the `aggregate="median_per_id"` escape hatch) is correct.

**Four findings, all in the how-tos, all fixed** (`cdb7e0d`):

| # | Finding | Fix |
|---|---|---|
| 1 | `bundle-your-model.md` sold the **F1 anti-skew guarantee as unconditional**. It holds only if the adapter is *also* passed to `create_training_data(adapter=…)`; without it the training call writes raw bands and the transform runs at inference only — the exact skew the section claims to rule out (`api.py:358-359`). A reader following that page plus `run-at-scale.md`, whose snippet passes no `adapter=`, would have shipped skewed features. | states the condition |
| 2 | Same page attributed the `T == n_timestamps` preflight to **both** verbs. `create_training_data` deliberately does not check it (`api.py:386`, *"D6: no n_timestamps preflight — T is caller-set"*); only `run_inference` does (`api.py:944`). | attributed correctly |
| 3 | `download-real-imagery.md`'s byte table **did not reproduce from its own stated multiplier**: row 3 applied the 4-band 426 MB figure to a 3-band config (1.7 GB → ~1.5 GB), and row 1's measured ~18 GB is the real-archive average (~357 MB/granule = 74 GB ÷ 207), not 52 × 426 MB = 22 GB. | per-row provenance column + "426 MB is a ceiling" note |
| 4 | `CdseCredentials` / `fsd` / `os` used in three copy-paste snippets that never imported them. | imports added — which also brings those blocks under `test_doc_snippets_use_real_fsd_attributes`, since it only inspects blocks that import from `fsd` |

**Also added `docs/howto/README.md`** — both `README.md` and the tutorial link to `docs/howto/`,
which without an index renders as a bare directory listing at exactly the moment a first-timer
leaves the tutorial. The index restates Diátaxis's "a how-to cannot promise safety" boundary at the
entry point instead of only inside each page.

**Checks that found nothing**, recorded so they aren't re-run: `AZ_*` parity between the how-tos
and `env.example.sh` (4 vars, exact match); an identifier sweep of all six new files for GUIDs /
`abfss://` accounts / `.blob.core` / `.azurecr.io` / subnet CIDRs (**no hits** — the sole `rise`
mention is the project codename already public in `ARCHITECTURE.md` and `ROADMAP.md`); every
relative link and run-book/example target resolving; the `mpc`/`azure`/`aml`/`grid`/`model-example`
extras all existing; `merge="reproject"`, `storage="azure"`, `bundle.save`/`read_spec`,
`grid.roi_to_s2_grids`, and the `modify.*` feature functions all matching their real signatures;
and the `~100 km from every labelled field` rejection of `s2grid=476da24` matching the archive.

**Gate:** `pytest -q tests/test_docs.py` → **153 passed, 82 skipped**; `ruff check src/ tests/
demos/ examples/` clean. `tests/test_tutorial_fixture.py`'s 3–4 min pipeline test was **not**
re-run — docs-only change, and CLAUDE.md keeps long/pipeline scripts off Claude. Branch merged to
`main` `--no-ff` and the worktree pruned (standing practice). **`main` is not pushed** — that stays
the user's call.

---

## 2026-07-31 — spec 41 P7 drafted: `docs/tutorial.md` + 5 `docs/howto/*` pages + README pointers → NEXT: the user runs the D13 cold-start gate

Per the P7 handoff (spec 41 §3/D10/D13): wrote `docs/tutorial.md` (narrates
`tests/test_tutorial_fixture.py::test_pipeline_create_training_data_train_and_infer` against the
committed fixture — `create_training_data` → train a trivial RF → `workflows.create_datacube.
run_create_datacube` → `run_inference` → COG + STAC) and five `docs/howto/*` pages (`your-own-
region`, `download-real-imagery`, `run-at-scale`, `bundle-your-model`, `serve-xyz`), sourced from
`demos/E2E_AUSTRIA.md` §4/§9/§6, `demos/E2E_AUSTRIA_AML.md` §8, and run-books 29/30. `examples/
eurocrops_rf.py` already met D10's bar (61 lines, no timing/plotting) — no change needed. Both
docs and README now point at the tutorial instead of "being built".

**One correction to the handoff's own numbers, caught by doing the arithmetic rather than copying
it:** the handoff's "T at mosaic_days=20: 9" is stale — it carries over spec 42 D1's original
24-granule/local-CDSE plan. The **committed** fixture is 36 granules, 2018-04-01 → 2018-09-28
(A1's MPC path), which gives `T = ceil(181 days / 20) = 10`, and `create_training_data`'s return is
per-**pixel** rows (not per-field) unless `aggregate="median_per_id"` is passed — the tutorial
states `(N, 10, 2)` with `N` described, not a specific fabricated pixel count. Neither `test_
tutorial_fixture.py` nor spec 42's acceptance criteria actually assert `T == 9` (checked — no such
assertion exists), so this was a documentation-only correction, not a code defect.

**Gate status:** `pytest -q tests/test_docs.py` (152 passed, includes all 6 new files under
`test_relative_links_resolve` + `test_doc_snippets_use_real_fsd_attributes`) and `pytest -q
--ignore=tests/test_tutorial_fixture.py` (709 passed / 84 skipped) both clean; `ruff check src/
tests/ demos/ examples/` clean; the pre-push identifier sweep (`RECIPES.md`) found no tracked hits.
**`tests/test_tutorial_fixture.py`'s own 3-4 minute pipeline test was deliberately not re-run** —
Claude doesn't run long scripts (CLAUDE.md), and the P6 entry below already has it passing at
3 min 18 s against this exact fixture. **The one gate that remains is D13's cold-start run** — the
user, fresh clone, fresh venv, `docs/tutorial.md` followed literally, first failure reported as a
spec-24 `_result.json`.

---

## 2026-07-31 — ✅ spec 42 DONE: the tutorial micro-fixture is built, verified offline and committed → spec 41 P6 closed, **P7 unblocked**

Run-book 43 ran end to end: Step 0 on the laptop, Steps 1-5 on an Azure ML compute instance against
the blob MPC archive, Steps 6-7 back on the laptop. **`tests/data/tutorial/` is committed** — 27 MB,
108 COGs, 36 granules x B04/B08/SCL over grid cell `4772924` (T33UWP, single tile),
2018-04-01 .. 2018-09-28, with `catalog.parquet`, 43 labelled fields, the cell polygon, `NOTICE` and
a provenance `README.md`.

**All three automated acceptance criteria pass offline in 3 min 18 s.** Criterion 4 (cold-start, spec
41 D13) is the user's and belongs to P7.

### What the real run found that no synthetic test could

| | |
|---|---|
| **`offset = 0`, not −1000** | The blob MPC archive serves the **pre-Collection-1** 2018 products — generated before baseline 04.00 arrived 2022-01-25, so `BOA_ADD_OFFSET` does not exist and 0 is the true declaration (spec 32 D3 derives it per item). The local CDSE archive's `_N0500_` granules are the *reprocessed* versions of the same acquisitions and correctly carry −1000. Both right; different product versions. |
| **72 granules over a FULL YEAR** | Spec 42 §1/D2 always said Apr–Sep 2018, but the generator had **no date filter** — invisible while the assumed source was the local (Apr–Sep-only) archive. `--startdate`/`--enddate` added; 72 → 36 in-window. |
| **43 fields collapsed to one class** | Spec 42 D3 hardcoded `{maize, hemp}` against label values it never checked. Real column is `crop`, real values are HCAT compound names. Fixed by **amendment A3**: majors derived by clipped area. |

### Three review fixes earned their keep on this run

- **F6** (`pass` computed, not hardcoded) is what *caught* the one-class collapse. Without it Step 0
  writes PASS and ships a single-class fixture.
- **A2** (`offset in (0, −1000)` instead of a hardcoded `== −1000`) is the only reason acceptance
  test 2 passed — the assertion it replaced would have **failed** against this archive's correct `0`.
- **F1** (redact `--archive-root` from the recorded invocation) held on real data: the committed
  `README.md` shows `--archive-root <archive-root>`, zero `abfss://`, in a public MIT repo.

### Also fixed, all surfaced by running it for real

`from fsd import storage as fs` in 3 run-book snippets (`fsd.storage` is a package; the functions
live in `fsd.storage.fs`) — now guarded by `test_doc_snippets_use_real_fsd_attributes`, which
AST-checks 13 documents and was **vacuous on first write** until its file selector matched
`python -c` blocks, not just ```` ```python ```` fences. `fs.put/get` are file-only, so Step 5's
directory call could never have worked — tar-one-object is now the primary path. `git check-ignore
-v` inverted Step 7's own verdict. `pystac.get_all_items()` deprecation. And Step 6 reads as a hang
because pytest captures the live `[setup] N/43 … ETA` line — the run-book now says `-s`.

**Gate:** `pytest -q` **698 passed / 87 skipped**, `ruff check src/ tests/ demos/` clean. Identifier
sweep over the staged tree: 7 hits, all documented false positives; no `abfss://` anywhere in the
committed fixture beyond placeholder docstrings.

---

## 2026-07-31 — run-book 43 Step 0 runs green on real data; spec 42 **A3**: the label collapse is derived, not hardcoded

Step 0 was run for real for the first time and **failed at its own gate** — which is the headline,
because that gate is one of the fixes from the 2026-07-30 review:

```
cell 4772924  bounds 15.3900,48.4821,15.4717,48.5320  fields 43  classes other=43
FAIL: expected 3 classes over a non-empty field set, got 1 class(es) over 43 field(s).
```

Review finding **F6** replaced a hardcoded `"pass": true` with a computed one. Without it this run
writes PASS, ships a **single-class** fixture, and the defect surfaces much later — in a tutorial
that trains a classifier on one class. The guard paid for itself on its first real invocation.

### Root cause: D3 assumed label values nobody had looked at

| | assumed | actual (`shapefiles/AT_2018_TRAIN.geojson`) |
|---|---|---|
| label column | `EC_hcat_n` | **`crop`** — `EC_hcat_n` belongs to a *different* workspace file, `austria_eurocrops_sampled_ethiopia_translated.geojson` |
| label values | `maize`, `hemp` | **HCAT compound names**: `grain_maize_corn_popcorn`, `hemp_cannabis`, … (9 crops, 100 fields each) |

`collapse_label` matched case-insensitively but not fuzzily — correctly — so every field became
`other`.

### A3: derive the majors, and justify the cell with a measurement

- **`pick_major_crops` ranks by clipped area inside the cell** and keeps the top `--n-major`
  (default 2). Area, not field count: area is what the datacube's pixels are. For `4772924` it
  yields `grain_maize_corn_popcorn` (25.1 ha) + `hemp_cannabis` (17.8 ha) — the crops D3 meant.
  `--label-col` (default `crop`) makes the column an argument too. It **refuses rather than
  degrades**: ≤ `n_major` distinct crops, or a cell with no field, both raise.
- **New `tests/data/tutorial/survey_cells.py`** ranks every cell over an ROI. Over `AT_ROI`:
  **179 of 300 cells hold ≥ 1 field.** `4772924` stays the pick — two cells have **8** crops rather
  than 7, but their **top-2 share is 50 % / 57 % against `4772924`'s 82 %**, so there the catch-all
  `other` would be the *largest* class. Variety is the wrong objective for a 3-class collapse.
- §1's crop distribution table was already right; the survey reproduces it exactly. Only D3's
  literals and the column name were wrong.

**Step 0 now:** `43 fields → grain_maize_corn_popcorn=20, hemp_cannabis=13, other=10`, `pass: true`.

### `roi_to_s2_grids`: comment corrected, code deliberately unchanged

The clip comment read as *"`gpd.overlay` cannot be used here"*. The real constraint is narrower —
overlay against the **un-unioned** `roi_gdf` multiplies rows and repeats cell ids; against the union
it is identical and unique. Measured all four variants (max symmetric difference **0.0**):

| clip method | AT_ROI (1 poly) | 900-poly ROI |
|---|---|---|
| `intersection(union)` — kept | **2.6 ms** | 80.5 ms |
| `overlay(vs union)` | 9.5 ms | 92.6 ms |
| `overlay(vs raw roi_gdf)` | 7.1 ms | 25.2 ms → **1167 rows, ids not unique** |
| `overlay(raw) + dissolve("id")` | 12.7 ms | **50.5 ms** |

overlay's speed comes from STRtree pruning **per ROI polygon**; the union collapses the right side
to one geometry, so the index prunes nothing. **The efficiency and the `InvalidBlockList`
duplicate-id bug had the same cause.** `dissolve` recovers both but is ~5× slower on the
single-geometry ROI — the documented shape of an ROI, i.e. the hot path. Kept as-is; only the
comment changed, now carrying the numbers so nobody re-derives this.

**Gate:** `pytest -q` **681 passed / 87 skipped** (674 + 7), `ruff check src/ tests/ demos/` clean.
Identifier sweep: 32 values, 7 hits, all documented false positives, none in the 6 changed files.

---

## 2026-07-30 — P6 step 1 REVIEWED: 8 findings, 2 blocking, all fixed → NEXT: sign off spec 42 **A2**, then merge + run run-book 43

The Opus review of the P6 step-1 branch (`worktree-p6-build-fixture`, base `main` @ `a9a356b`),
against **spec 42** D1-D6/§3/§8 A1 and **run-book 43**'s normative CLI blocks. Same posture as the
P5 review: the authoring session declared it green (665/87, ruff clean — **verified true**), and the
review still found **8 defects**.

### The two blocking ones

| # | defect |
|---|---|
| **F1** | **An infrastructure identifier would have been committed to a public repo.** `build_fixture.py` wrote `Generator invocation: {' '.join(sys.argv)}` into the fixture's `README.md` — a file spec 42 D6 *deliberately commits*. Run-book 43 Step 4 is invoked `--archive-root "$AZ_ARCHIVE_ROOT/archive"`, which the shell expands, so the concrete `abfss://…` url would have been published. The same function's closing lines asserted the opposite ("intentionally not recorded here (public MIT repo)"). **Fifth leak of this class**; the first that would have been *generated* rather than typed. |
| **F2** | **Step 4 truncated its own inputs.** Run-book 43 Step 4 passes `--roi tests/data/tutorial/roi.geojson --fields …/fields.geojson --out tests/data/tutorial` — inputs *inside* the output dir — and the generator re-serialized both back over them. `to_file` truncates first, so a crash mid-write destroys Step 0's output, which **cannot be regenerated on the VM** (Step 0 needs `shapefiles/` from the workspace root). An interrupted run would have cost a laptop round-trip on the hotspot A1 exists to avoid. |

### The handoff's flagged judgment call: the answer is "not faithful"

The prior session flagged, rather than silently decided, whether its offline substitute for A1's
revised acceptance test 2 was faithful. **It was not — and neither would any other offline test be.**
A1 asks the test to assert the offset was *"copied from the source, not invented"*; §4 puts that test
in `tests/test_tutorial_fixture.py`; run-book 43 Step 6 runs that suite **with the network
disconnected**. The one assertion A1 wants is the one that file can never make. The substitute's
only live check was `assert int(row["offset"]) == -1000` — which a generator that hardcoded `-1000`
also passes, i.e. exactly the failure mode A1 set out to exclude (and on the MPC path no granule id
carries a `_N####_` token, so the id-agreement branch never fires at all).

**Resolution — spec 42 amendment A2 (✅ signed off, 2026-07-30, user).** The source-equality gate moves
to where the source is reachable: the generator records per granule whether the offset was
`declared` (copied from the source catalog's column) or `derived` (D1's id-token fallback) and emits
`offset_sources` + `all_offsets_declared` in `_result.json`; run-book 43 Steps 2 and 4 gate on it.
The offline suite keeps only what is sound from the artifact alone (round-trip, value ∈ {0, −1000},
uniform across the fixture) — plus acceptance test 3's post-offset reflectance range, which A1
itself calls the check that catches a ~1000 DN error *however the offset arrived*.

### The other five

- **F4** — the generator computed `offset_source` per granule and then dropped it, keeping it only in
  a progress line. The run-book says paste the `_result.json`, not the logs (spec 24), so nothing
  gated on it. Now in the result JSON; this is also A2's mechanism.
- **F5** — `--check-only`'s `pass` omitted **2 of run-book Step 2's 4 stated PASS conditions** (all
  bands present, date span). It printed them and gated on the other two. `--bands` is now accepted by
  `--check-only` and gated; omitted, it records `unchecked` rather than silently satisfied.
- **F6** — Step 0's `_result.json` hardcoded `"pass": true`, with `expected: {"n_classes": 3}`
  written but never compared. If `EC_hcat_n`'s real values are not literally `maize`/`hemp`, every
  field collapses to `other` — one class, untrainable — and Step 0 would still have read PASS.
- **F7** — run-book Step 7's gitignore check was wrong in a way that inverts its verdict. Verified
  live: with the D6 negation working, `git check-ignore **-v**` *prints* the matching negation line
  and exits 0. The run-book said "expect: no output / PASS if prints nothing", so a **correct**
  negation reads as FAIL. Fixed to the un-`-v` form (`exit=1` == not ignored).
- **F8** — `--max-timestamps N` took the **first** N chronologically, so D2's own documented fallback
  (`--max-timestamps 12`) would have yielded Apr–Jun only, destroying the seasonal series D2 calls
  the point of keeping all 24. Now spread evenly across the span, endpoints kept.

### Negative controls, because one guard was vacuous

Both blocking fixes were negative-controlled. F1's held immediately. **F2's first test did not** —
it asserted byte-equality of the inputs, which *passed* even with the re-serialization restored,
because a GeoJSON round-trip is often byte-identical. The real property is that the generator must
not write to a path it read from **at all** (the hazard is truncation-on-crash, not divergence), so
the assertion moved to `st_mtime_ns`. That version fails correctly when the bug is restored. Content
equality is kept as a secondary check, now documented as insufficient on its own.

**Gate:** `pytest -q` **674 passed / 87 skipped** (665 baseline + 9 new), `ruff check src/ tests/
demos/` clean. Pre-push identifier sweep run over the staged tree: 32 concrete values, 7 hits, all
7 the documented known-clean false positives, **none in the changed files**.

**Merged and PUSHED — `origin/main` is at `2bdc4c6`** (2026-07-30, `a9a356b..2bdc4c6`, 3 commits).
A2 was signed off the same day; `worktree-p6-build-fixture` went into `main` with `--no-ff` and the
worktree + branch were pruned (standing practice). Post-merge gate on `main`: **676 passed / 89
skipped** (the +2/+2 vs the worktree's 674/87 is the documented gitignored-benchmark-report delta),
ruff clean. The push matters operationally, not just hygienically: **run-book 43 Step 1c clones from
GitHub**, so the VM could not have seen these generators otherwise.

---

## 2026-07-30 — P6 step 1: run-book 43's two generator scripts, written and offline-tested → NEXT: the user runs run-book 43 on an Azure VM

Run-book 43's Prerequisites block named a chicken-and-egg gap: it needs
`tests/data/tutorial/build_fixture.py` to exist, and said in as many words that the run-book
itself does not create it. The task was framed as one script; it is actually **two** (the run-book
splits across two machines, spec 42 §8 A1) — `derive_roi_and_labels.py` (Step 0, laptop, needs
`shapefiles/` which lives outside this repo) and `build_fixture.py` (Steps 2-4, Azure VM, needs the
blob archive). Both now exist, both ruff-clean, neither run for real (per CLAUDE.md — Claude never
runs networked/long scripts; that's the user's job on the VM).

| file | what it does |
|---|---|
| `tests/data/tutorial/derive_roi_and_labels.py` | ROI/labels: derives grid cell 4772924 via `roi_to_s2_grids`, clips+collapses `AT_2018_TRAIN`'s labels to the spec 42 D3 3-class scheme (`maize`/`hemp`/`other`), writes `roi.geojson` + `fields.geojson` |
| `tests/data/tutorial/build_fixture.py` | select → clip (via `raster.cog.to_cog`, ADR 0014) → catalog (radiometry read from the source's own declaration column, never hardcoded — A1; D1's id-token re-derivation kept as the offline fallback) → NOTICE/README → `_result.json`. `--check-only`/`--dry-run`/build modes match run-book 43 Steps 2/3/4's CLI exactly. Per-file idempotent/resumable; `--max-timestamps` fallback before the 30 MB cap. |

**Verified offline** (the hard constraint: neither script can be run for real without VM/blob
access) against synthetic mini-archives, mirroring `test_datacube_builder.py`'s `_write_tile`/
`_make_catalog` shape: `tests/test_build_fixture.py` (12 tests — selection, MGRS-tile parsing,
radiometry column fallback (`offset` → `boa_add_offset` → id-token derivation → refuse), dry-run
zero-writes, idempotent re-run, geometry recomputed from the clip not the source, `--max-timestamps`
fallback) and `tests/test_derive_roi_and_labels.py` (5 tests — cell selection, label collapse,
wrong-cell-id failure, missing-column failure, CLI/`_result.json` shape). A one-off (uncommitted)
smoke script additionally ran the FULL downstream pipeline — `build_fixture` → `create_training_data`
→ train a trivial classifier → `run_inference` → COG + STAC — against a synthetic fixture, to catch
wiring bugs in the acceptance-test-3 code path before the real fixture exists; it passed end to end.

**`tests/test_tutorial_fixture.py`** (judgment call, handoff recommended it): spec 42 §4 acceptance
tests 1-3, whole-module-skipped until `tests/data/tutorial/catalog.parquet` exists (it doesn't yet —
that's the VM's job). One deliberate deviation from §8 A1's revised acceptance test 2: A1 wants the
fixture's offset compared against the *source* catalog, but run-book 43 Step 6 runs this suite with
the network disconnected, so the source is unreachable by design. Test 2 instead checks the
strongest fact derivable from the shipped artifact alone (declaration round-trips + agrees with the
granule id's own baseline token where derivable) — documented as an offline substitute in the test's
docstring, not a silent reinterpretation.

**`.gitignore`** gained spec 42 D6's negation — three lines, not the one line D6 sketched:
`data/` (line 21) excludes the whole directory tree, and git cannot re-include a file whose parent
directory is excluded by a plain file-negation alone, so the un-exclusion has to walk back down the
tree (`!tests/data/` → `!tests/data/tutorial/` → `!tests/data/tutorial/**`), plus a re-ignore for
`tests/data/tutorial/__pycache__/` (the blanket `*.pyc` rule is un-ignored by the same negation).
Verified with `git check-ignore`/`git status` before relying on it.

**Gate:** `pytest -q` **665 passed / 87 skipped** in this worktree (648/84 fresh-worktree baseline +
17 new passing + 3 new skipped, per PROGRESS's own documented baseline-difference note), `ruff check
src/ tests/ demos/` clean.

**Not done / explicitly out of scope this session:** running run-book 43 itself (needs the VM —
confirm the user has AML compute access before assuming the fixture is imminent); `docs/tutorial.md`
(P7, gated on the real fixture); the two open P1 `test_docs.py` findings (still open, still cheap,
still not touched — see below).

## ✅ 2026-07-30 — P5 DONE: README + ARCHITECTURE + the PROGRESS split. Spec 41's floor is complete. → NEXT: P6 (the tutorial fixture)

**P1+P2+P5 were spec 41's stated floor** — "they hit all three original complaints, carry the least
risk, and leave the repo strictly better if P6/P7 never happen." All three are now done, plus P3 and
P4.

| deliverable | what changed |
|---|---|
| **`ARCHITECTURE.md`** (new) | the code map: C4 context/container/deployment as **Mermaid**, the module table, the **invariants**, the three modes, the layers, and a contributing section |
| **`README.md`** (rewrite) | was stale in exactly the way D6 assertion 3 predicts — it called `run_inference` a **stub** long after it had shipped *and* run on the cluster. Now: what fsd is, install, a 60-second three-verb example, and a "where to go next" table |
| **`PROGRESS.md`** (split, D12) | **3,691 → 93 lines.** A synthesized current-state section + the most recent entry + pointers |
| **`docs/progress-archive.md`** (new) | **61** older entries **moved verbatim** (one identifier scrubbed), one file, `status: historical` |
| **`ROADMAP.md` §2.1/2.2** | shrunk to pointers into `ARCHITECTURE.md` (D9: one fact, one home) |
| **`demos/README.md`** | relabelled — it now says plainly, at the top, that these are **timing harnesses**, not examples, with a table sending readers to `examples/`, `docs/tutorial.md` or `docs/howto/` instead |
| **`tests/test_docs.py`** | D6 assertions **2 and 3** added |

**`CONTEXT.md` needed no edit** — the demo/benchmark/example/tutorial/how-to glossary D10 asked for
already landed with ADR 0026 in the specs 41/42 session.

### The two new tests both earned their place immediately

- **Assertion 3 (README verbs)** is the one D6 says *"alone would have caught the current stale
  README"* — it checks every `fsd.<verb>(` the README calls is really in `fsd.__all__`. It now
  covers `download`, `create_training_data`, `run_inference`.
- **Assertion 2 (links resolve)** checks **59 relative links across 38 documents**. Verified
  non-vacuous by a negative control: injecting a broken link into `ARCHITECTURE.md` fails the test
  as `test_relative_links_resolve[ARCHITECTURE.md]`.
- **Scope is deliberate:** only the root documents and the maintained `docs/` tree. Point-in-time
  corpora are excluded — a rotted link in a spec is a fact about history, not a defect, and D3
  forbids editing them to fix it.

### The PROGRESS split broke the P4 parity test, correctly

Moving the log into `docs/` pulled **`AZ_DOWNLOAD_ROOT`** and **`AZ_INFER_ENV_NAME_VERSION`** into
the scanned corpus — two variables that have since been renamed or dropped, and which appear
**only** in the archive. The fix was to exclude the archive from the parity corpus, not to
resurrect two dead variables in `env.example.sh`: parity is about the *current* operational corpus,
and the archive is never edited after the fact.

**Gate:** `pytest -q` **649 passed / 86 skipped** on `main`, `ruff check src/ tests/ demos/` clean.

> ⚠️ **Expect 649/86 in this checkout and 647/84 in a fresh clone or worktree.** The difference is
> two *gitignored* benchmark reports (`benchmarks/datacube_throughput_report_{cog,jp2}.md`,
> `.gitignore:49`) that exist on this laptop, carry D4 headers, and are picked up by
> `test_docs.py`'s directory glob. Not a defect, but the test target set does depend on untracked
> files — a stray unheadered `.md` under `benchmarks/` would fail here and pass in CI.

**PUSHED — `origin/main` is at `8da99fc`** (2026-07-30, `b1d9781..8da99fc`, 15 commits). The
pre-push identifier sweep was clean: all 32 concrete values checked, only the documented
known-clean false positives hit.

### ✅ P5's acceptance gate is now closed — the Opus review happened, and found 8 things

**Spec 41 P5's gate was "readable only — no test exists. Opus review against this spec."** Done
2026-07-30 in a separate session (the author cannot be the reviewer). It found **2 blocking defects
and 6 accuracy issues**; all 8 are fixed, and the blocking class now has an automated gate.

**The two blocking ones were both in the README's 60-second example** — the first code a newcomer
copies, and it did not run. `fsd.download(...)` omitted the **required** `max_tiles` cost guardrail,
and `fsd.run_inference(...)` passed a `model_bundle=` keyword **that does not exist** (the bundle is
the first positional arg) while also omitting the three ROI-mode requirements
`catalog_filepath`/`mosaic_days`/`bands`. 2 of 3 calls raised `TypeError` before any work.

**Why the existing test missed it:** D6 assertion 3 checked the verbs are in `fsd.__all__` —
*existence*, not *callability*. It is now backed by
`test_readme_calls_bind_to_real_signatures`, which AST-parses every `fsd.<verb>(...)` in the
README's python blocks and `inspect.signature().bind()`s its real arity and keyword names against
the live function, executing nothing. Negative control: reverting either README fix fails it with
the exact `TypeError`. **P5's gate is no longer purely human.**

**The six accuracy fixes:**

| finding | fix |
|---|---|
| invariant 1 was stricter than the code — bare `open()` also serves **node-local scratch/CLI-local files** in 7 places (`api.py:828` even says so inline) | reworded to *"no module reaches a **remote** path outside `fsd.storage`"* with both exceptions named and the holdable line stated: a bare open is only legal on a path that cannot be a URL |
| §3 called `raster/` "the one place GDAL/VSI opens paths directly" — false (`api.py:788,840`, `model/engine.py:97`) | names the other two sites as the only other permitted ones |
| §8 said the sweep caught "three leaks" | **four** (`RECIPES.md:625`, edited in the very same commit) |
| **D9 leftover:** `ROADMAP.md` §2.3/§2.4 became second homes for `ARCHITECTURE.md` §6/§3 — and §2.3 was **stale**, naming Azure *Batch* as the runner target when AML is what shipped | both shrunk to pointers, same treatment P5 gave §2.1/2.2 |
| the archive's preamble claimed the entries are "verbatim" | they are — **except one deliberate scrub** of a concrete cluster identifier, now stated |
| the same fact recorded three ways (entry: "60 entries"/"100 lines"; commit: 61/94; actual: **61/93**) | corrected to 61 and 93 — the P1 review's accounting defect, recurring |

**Verified true, no action:** the split lost nothing — 61 pre-P5 entries in, 61 out, headings
identical **and in the same order**, bodies **byte-identical** apart from that one scrub. Invariants
2 (no `boto3`), 3 (`workflows/task.py` imports no runner) and 8 (`download=False` default) hold.
All 22 files in the module table exist. `18.8 min / 32 nodes` and `35 % of a 2067 s run` both match
their sources. **The assertion 2 scope call was right** — excluding point-in-time corpora follows
from D3, and the counter-argument (a rotted run-book link wastes an operator's time) is better
served by superseding the run-book than by editing it.

**Gate after the fixes:** `pytest -q` **650 passed / 86 skipped** on `main` (649 baseline + the new
test; 648/84 in a worktree, same +1), `ruff check src/ tests/ demos/` clean.

**PUSHED — `origin/main` is at `1274d67`** (2026-07-30, `8da99fc..1274d67`, 5 commits). The
identifier sweep was run on the changed files before the push: 32 concrete values checked, only the
documented known-clean false positives hit.

### ⚠️ Still open — two P1 findings, inherited

Neither is P5's doing; both belong to whoever touches `test_docs.py` next:

- **`superseded_by` is ambiguous across the `specs/`↔`runbooks/` namespaces.** `runbooks/42`'s
  `superseded_by: 41` resolves to `specs/41-docs-refactor.md` because the test searches `specs/`
  first — it **passes on the wrong file**; the intended target is
  `runbooks/41-recover-aml-job-timings.md`.
- **The two register indexes disagree on link style** — `specs/README.md` uses markdown links,
  `runbooks/README.md` bare backticks, so assertion 2 never sees the run-book index.
