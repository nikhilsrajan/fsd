# Run-books — index & execution order

> **Why this file:** run-book *numbers* track the spec that motivated them, **not** the order you
> run them in — so the demo pipeline reads out of order (you run 37 → 36 → 39 → 40 → 38). This README
> is the map until the planned C4-model docs refactor (TODO #55) replaces it. A run-book is what
> Claude hands you instead of running a pipeline/networked script itself (spec 24): you run the
> commands, paste back each step's `_result.json`, Claude diffs it. Template: `TEMPLATE.md`.

## ⭐ The demo pipeline (Azure ML scale-out) — run in THIS order

The north-star demo is **download → build → flatten → train+bundle → inference**, all on Azure ML.
The run-books that realise it, in dependency order (not numeric order):

| # | run-book | what it does | consumes | status |
|---|----------|--------------|----------|--------|
| 0a | `36-phase0-identity-smoke.md` | RBAC gate: can an AML job auth to blob as the compute identity? | — | ✅ proven |
| 0b | **Build the general-purpose AML Environment** (step inside `36-aml-runner.md` setup) | bakes the fsd wheel into the image every node uses for download/build/flatten | current `main` | ✅ (rebuild after any `src/fsd/` change — see 39 prereqs) |
| 1 | `37-download-on-aml.md` | download the S2 archive to blob (CDSE one-job + MPC fan-out) | ROI + creds | ✅ Phases 0–3 green |
| 2 | `37-verify-archive.md` | prove the landed archive is trustworthy (radiometry, catalog completeness, byte-identical) | 37's archive | ✅ green |
| 3 | `36-aml-runner.md` | datacube build **fan-out** across N nodes (the 900-field set) | 37's verified archive | ✅ Phases 1–3b green |
| 4 | `39-training-data-on-aml.md` | flatten the 900 cubes → **land-local** training arrays (`create_training_data` façade) | 36's cubes + `input.csv` | ✅ P0–1 green; P2 re-run pending |
| 5 | `40-train-and-bundle.md` | features (driver-side) → **train `adapters:DemoRF` @ T=8** → **bundle** | 39's landed arrays | 🆕 not yet run |
| 6 | `38-inference-on-aml.md` | `run_inference(roi=…, runner="aml")` at scale → per-cell COGs + STAC | 40's bundle + 37's archive | 🟡 impl+reviewed, cluster run pending |

**Data hand-offs to remember:** 37 writes `$AZ_ROOT/archive/catalog.parquet` (36/38 read it — **not**
the `mpc/` prefix from runbook 34); 36 Phase 3 writes `runs/<id>/input.csv` (39 reads it); 39 lands
`tests/outputs/p39_training_data_aml/landed/` (40 reads it); 40 writes `demo_rf_bundle/` (38 Phase 0
stages it, `AZ_BUNDLE_LOCAL`). 38 builds a **second, inference-specific** Environment (its own setup
section) that `COPY`s `demos/adapters.py` so `adapters:DemoRF` resolves on a node.

## Track B — local pipeline & serving (foundational; mostly done before the AML move)

The pipeline was proven **locally** first; these stay as reference and for local re-validation.

| run-book | what it proves | status |
|----------|----------------|--------|
| `26-download-confirm-run.md` | safe CDSE download (resume + `--dry-run`/`--stop-file` seams), tiny Austria slice | ✅ local |
| `27-austria-full-e2e.md` | the full Austria end-to-end local showcase run | ✅ local |
| `32-mpc-baseline.md` | `sources.mpc.download` vs real MPC + processing-baseline harmonization | ✅ local |
| `33-mpc-dedup-live.md` | reprocessing-dedup fires on the real duplicate acquisition (live MPC) | ✅ local |
| `34-download-to-blob.md` | download-to-blob (CDSE + MPC), cloud-VM-first (predecessor of the AML download path) | ✅ |
| `34-mini-mpc-cross-baseline.md` | cross-baseline render proof (the `-0.1`-offset black-tile branch) — still the only coverage of that fix | ✅ |
| `28-stac-geometry-regen.md` | regenerate the demo STAC with the true slanted cell footprint (not the bbox) | ✅ |
| `29-tier1-stacnotator-byo.md` | Tier-1 serving: a pre-styled XYZ URL consumed by STACNotator BYO-XYZ | ✅ |
| `30-tier2-mini-mpc.md` | Tier-2 serving: outputs load into stock pgSTAC + titiler-pgstac (fsd = "just another MPC") | ✅ |

## Track C — Azure P1 access probes & exploratory (one-offs)

| run-book | what it is |
|----------|-----------|
| `31-p1-access-probe.md` | "hello Azure": `az` + adlfs blob round-trip + `/vsiadls/` raster read (the first RBAC/seam probe) |
| `31-p1-upload-slice.md` | upload a real S2 slice to the `rise` blob + repoint the catalog |
| `31-p1-datacube-on-blob.md` | build a datacube reading + writing the `rise` blob |
| `36-runner-fork-probe.md` | Batch-vs-AML exploration: what does `rise` actually give us today? |

## Track D — the docs refactor (spec 41)

| run-book | what it is | status |
|----------|-----------|--------|
| `43-build-tutorial-fixture.md` | build spec 42's committed **tutorial micro-fixture**: derive ROI+labels on the laptop, clip pixels in-region on a VM, land ~20 MB and commit it | 🆕 not yet run; **needs the generator implemented first** |

## Not run-books
- `TEMPLATE.md` — the spec-24 skeleton to copy for a new run-book.
- `HANDOFF-*.md` — ephemeral session batons (handoff protocol); safe to delete once the step lands.
- `scripts/` — helper scripts some run-books invoke.

## Conventions (all run-books)
- **Concrete `rise` values live in `../../AZURE_INFRA_PRIVATE.md`** (uncommitted, workspace root) —
  paste them as env vars; never hardcode them here (public MIT repo). Run the `RECIPES.md`
  identifier sweep before pushing.
- Each step writes `_result.json` (`{step,status,pass,metrics,expected,error}`) — **paste that back,
  not the logs.**
- **VPN + `az login`** are required wherever the driver or a node touches blob.
- Re-running is self-healing (idempotent skips); **never** `fs.rm(prefix, recursive=True)` on
  `abfss://` (TODO #50 — it deletes then raises, reading as "nothing happened").
