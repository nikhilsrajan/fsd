---
status: historical
summary: Ephemeral session baton for writing the train-and-bundle run-book (run-book 40); it has been written.
---

# Handoff — write the train→bundle runbook (the missing link into runbook 38)

**For:** the next session (Opus@high for the runbook design/sign-off; a Sonnet session may draft the
operator scripts once signed off). This is the ephemeral baton (per `fsd/CLAUDE.md`'s handoff
protocol) — durable state is in `fsd/PROGRESS.md` (top block), `fsd/specs/19-e2e-demo.md` (demo_02
train flow, already designed), and `fsd/specs/39-training-data-on-aml.md`. **Read `PROGRESS.md`
first.**

## Where we are (2026-07-27)
The demo pipeline is **download → build → flatten → [train + bundle] → inference**.
- **download / build / flatten** — proven at scale (runbooks 37 / 36 / **39**).
- **flatten just landed real training arrays** (runbook 39 Phase 1 GREEN): the 900 `AT_2018_TRAIN`
  fields → `tests/outputs/p39_training_data_aml/landed/` — `data.npy` = **(172781, 8, 3)** uint16
  (bands **B04/B08/B8A**, **T=8**), + `labels.npy`/`ids.npy`/`coords.npy`/`metadata.pickle.npy`.
  **No `features.npy`** (Phase 1 passed no adapter).
- **inference (runbook 38)** — ~ready: its "Build the inference Environment (D4)" section is written
  (currently **uncommitted** in `runbooks/38-inference-on-aml.md`, +102 lines), Phase 0 stages a
  bundle, and the T=8 window is now correct (spec 39 D6 retrains DemoRF at T=8 — the old T=8-vs-10
  mismatch is resolved).
- **The one missing link = train + bundle**, which produces the bundle runbook 38 Phase 0 consumes.

## Locked decisions (2026-07-27, user via AskUserQuestion) — do NOT re-litigate
1. **Demo model = `adapters:DemoRF`** — the user's own adapter (`required_bands=[B04,B08]`, retrain at
   **T=8**). It lives in the user's **local `adapters` module, NOT in this repo.** Consequences: the
   train runbook does `from adapters import DemoRF` (user-local); the **inference image must `COPY` the
   `adapters` module** (runbook 38's D4 section already anticipates an adapter package + `ENV
   PYTHONPATH`); the public repo can't reproduce the demo bundle on its own (that's accepted).
   `[B04,B08] ⊆ [B04,B08,B8A]`, so the landed arrays already carry DemoRF's bands.
2. **Structure = a NEW train+bundle runbook feeding an intact runbook 38.** Do **not** delete/rewrite
   38. Commit its image-build section + verify its T=8 / adapter-`COPY` details; leave its tested
   Phases 0–3 alone.

## The next session's job
**Write `runbooks/40-train-and-bundle.md`** (operator-run, spec-24 `_result.json` shape). Proposed phases:
- **Phase 1 — generate `features.npy` for the landed training set.** Re-run
  `flatten_training_data(input_csv=<runbook-36 Phase3 input.csv>, export_folderpath=<the landed
  folder>, id_col="id", label_col="label", adapter=DemoRF(), runner="aml", runner_kwargs={...})`.
  The aml reduce re-runs (~7 min; `data.npy` already landed → `_land_local` skips it) and the feature
  transform runs **driver-side after land-local** (D2/ADR-0020) → `features.npy` (+ `feature_ids`/
  `feature_labels`). PASS: `features.npy` present locally, shape `(pixels, 8, n_feature_bands)`, no
  adapter in the job spec.
  - **Open design choice to settle in the runbook (small):** re-running the whole reduce just to add
    features is wasteful since the raw arrays are already landed. Options: (a) accept the re-run
    (KISS, zero new code); (b) add a tiny verb `fsd.apply_features(export_folderpath, adapter=…)` that
    runs the existing `api._apply_training_features` over already-landed arrays (a ~10-line public
    wrapper — the only candidate fsd code in this whole step; would need a 1-para spec + a test). Lean
    (a) unless the re-run cost annoys; note it, don't over-build (YAGNI).
- **Phase 2 — train DemoRF at T=8** on `features.npy` + `labels.npy` (RF + `LabelEncoder` →
  `joblib.dump`). **User-side, permanent (ADR-0018 / ADR-0018-file / CLAUDE.md) — fsd does NOT train.**
  Already sketched in `specs/19-e2e-demo.md` demo_02. The runbook *guides* the user's own training +
  metrics; it does not add fsd code.
- **Phase 3 — bundle it** via `fsd.model.bundle.save(adapter, artifacts, out_dir)` (exists). PASS:
  `bundle.json` carries the right `adapter` `module:attr` ref + spec (`required_bands=[B04,B08]`,
  `n_timestamps=8`, output_*), and `fsd.load_bundle(dir)` round-trips (model-free `read_spec` too).
  This bundle dir is exactly what **runbook 38 Phase 0** stages to blob.

Then: **commit runbook 38's image-build section** + verify (a) its window/mosaic_days give T=8 (bands a
valid superset of `[B04,B08]`), and (b) the Dockerfile `COPY`s the `adapters` module under the name
`bundle.json`'s `adapter` ref uses. After that, `runbooks/38-inference-on-aml.md` is runnable.

## Does this need a spec?
Probably **not a full spec** — training is user-side, bundling (`fsd.model.bundle`) and the feature path
(`_apply_training_features`) already exist, so runbook 40 is orchestration of existing verbs. Write it
**runbook-first**. The **only** thing that would need a (tiny) spec + test is option (b) above (a public
`apply_features` verb). Cross-validate any external facts per CLAUDE.md if the runbook leans on them.

## Repo / git state at handoff
- `main` @ `a13c98c` (docs: ADRs 0003-0019 + cleanup), **1 commit ahead of `origin/main`, UNPUSHED**.
  Spec 39's `1781331` **is** pushed. So push `a13c98c` when the user asks (run the RECIPES.md
  identifier sweep first — it was clean at last run: only `identityReference`/`prevent_destroy` FPs).
- **`runbooks/38-inference-on-aml.md` is MODIFIED + uncommitted** (the +102-line image-build section) —
  deliberately left for this next step, since it pairs with the DemoRF `COPY` decision.
- Landed training arrays: `tests/outputs/p39_training_data_aml/landed/` (gitignored). The runbook-36
  Phase-3 `input.csv` (900 cubes) is on blob under `${AZ_ROOT}/runs/<phase3-run-id>/input.csv`
  (Phase 0 of runbook 39 confirmed it).

## Suggested `/handoff` goal
"Write `runbooks/40-train-and-bundle.md` (features→train DemoRF at T=8→bundle) feeding runbook 38;
DemoRF + keep-38 are locked. Runbook-first, no fsd code unless the apply-features convenience is chosen."
