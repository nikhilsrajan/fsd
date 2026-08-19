# Specs — index

> **Why this file:** specs are point-in-time design documents (spec 41 D3/ADR 0022) — each records
> what was decided *then* and is never substantially edited after the fact. Every spec below carries
> a D4 status header (`current` / `superseded-by-NN` / `historical`, ADR 0023); this table adds the
> thing the header deliberately excludes — **implementation status and its evidence** — because that
> field is process state that goes stale (three specs' hand-written headers already had, before this
> refactor). This index is **regenerated**, not hand-maintained forever; re-derive it rather than
> patching it piecemeal.

| # | spec | status | implemented? | evidence |
|---|------|--------|---------------|----------|
| 00 | [overview.md](00-overview.md) | current | across `src/fsd/` | the package itself |
| 01 | [sources.md](01-sources.md) | current | yes | `tests/test_cdse.py`, `tests/test_mpc.py` |
| 02 | [catalog.md](02-catalog.md) | current | yes | `tests/test_catalog.py`; ADR 0006 |
| 03 | [datacube.md](03-datacube.md) | current | yes | `tests/test_datacube_builder.py`; ADR 0007 |
| 04 | [datacube-ops.md](04-datacube-ops.md) | current | yes | `tests/test_datacube_ops.py` |
| 05 | [flatten.md](05-flatten.md) | current | yes | `tests/test_datacube_flatten.py` |
| 06 | [bands.md](06-bands.md) | current | yes | `tests/test_bands.py` |
| 07 | [raster.md](07-raster.md) | current | yes | `tests/test_raster.py` |
| 08 | [workflows.md](08-workflows.md) | current | yes | `tests/test_workflows.py`, `tests/test_scaffold.py`; ADR 0004 |
| 09 | [notebooks.md](09-notebooks.md) | current | yes | `pyproject.toml` (src-layout, extras) |
| 10 | [storage-and-scale.md](10-storage-and-scale.md) | current | yes | `tests/test_azure_seam.py`; ADR 0003 |
| 11 | [benchmark-throughput-sweep.md](11-benchmark-throughput-sweep.md) | current | yes | `tests/test_benchmark_throughput.py`, `benchmarks/datacube_throughput_report.md` |
| 12 | [benchmark-read-instrumentation.md](12-benchmark-read-instrumentation.md) | current | yes | same harness as spec 11 |
| 13 | [cog-vs-jp2-experiment.md](13-cog-vs-jp2-experiment.md) | current | yes | `tests/test_prep_cog.py`, `benchmarks/cog_vs_jp2_report.md` |
| 14 | [cog-on-download.md](14-cog-on-download.md) | current | yes | `src/fsd/raster/cog.py`; ADR 0001, ADR 0014 |
| 15 | [calendar-mosaic.md](15-calendar-mosaic.md) | current | yes | ADR 0010 |
| 16 | [packaging-and-api.md](16-packaging-and-api.md) | current | yes | `tests/test_api.py` |
| 17 | [stac-catalog.md](17-stac-catalog.md) | current | yes | `tests/test_catalog_stac.py`; ADR 0016 |
| 18 | [model-adapter.md](18-model-adapter.md) | current | yes | `tests/test_model.py`; ADR 0018 |
| 18 | [model-bundle-explainer.md](18-model-bundle-explainer.md) | current | n/a (companion explainer) | see spec 18 evidence |
| 19 | [e2e-demo.md](19-e2e-demo.md) | superseded-by-23 | superseded | `demos/e2e_austria.py` replaced `demos/e2e_ethiopia.py` |
| 20 | [datacube-tile-merge-bug.md](20-datacube-tile-merge-bug.md) | current | yes | `tests/test_datacube_builder.py` (merge fix) |
| 21 | [roi-inference-verb.md](21-roi-inference-verb.md) | current | yes | `tests/test_api_roi.py` |
| 22 | [unify-inference-runner.md](22-unify-inference-runner.md) | current | yes | `tests/test_runners.py`; ADR 0015 |
| 23 | [e2e-austria-local-gate.md](23-e2e-austria-local-gate.md) | current | yes | `demos/e2e_austria.py`, `demos/E2E_AUSTRIA.md` |
| 24 | [working-contract.md](24-working-contract.md) | current | yes | `CLAUDE.md`, `runbooks/TEMPLATE.md` |
| 25 | [download-convert-redesign.md](25-download-convert-redesign.md) | current | yes | `tests/test_download_cli.py`; ADR 0019 |
| 25b | [pipeline-exception-safety.md](25b-pipeline-exception-safety.md) | current | yes | `tests/test_download_cli.py` |
| 26 | [safe-download-runner.md](26-safe-download-runner.md) | current | yes | `tests/test_download_cli.py`; `runbooks/26-download-confirm-run.md` |
| 27 | [titiler-leaflet-stac-verify.md](27-titiler-leaflet-stac-verify.md) | historical | not implemented (rejected at sign-off) | replacement plan: `demos/TITILER_LEAFLET.md`, TODO #26-#29 |
| 28 | [stac-output-geometry-fix.md](28-stac-output-geometry-fix.md) | current | yes | `tests/test_catalog_stac.py` |
| 29 | [tier1-prestyled-xyz-validation.md](29-tier1-prestyled-xyz-validation.md) | current | yes | `tests/test_titiler_serve.py`, `demos/titiler_serve.py` |
| 30 | [tier2-mini-mpc-validation.md](30-tier2-mini-mpc-validation.md) | current | yes | `demos/mini_mpc/`; `runbooks/30-tier2-mini-mpc.md` |
| 31 | [p1-azure-storage-seam.md](31-p1-azure-storage-seam.md) | current | yes | `tests/test_azure_seam.py`; ADR 0003 |
| 32 | [mpc-source-baseline-harmonization.md](32-mpc-source-baseline-harmonization.md) | current | yes | `tests/test_mpc.py`, `tests/test_declaration.py` |
| 33 | [mpc-reprocessing-dedup.md](33-mpc-reprocessing-dedup.md) | current | yes | `tests/test_mpc.py`; `runbooks/33-mpc-dedup-live.md` |
| 34 | [ingest-normalization-contract.md](34-ingest-normalization-contract.md) | current | yes | `tests/test_declaration.py`; ADR 0011, ADR 0012 |
| 35 | [declaration-persistence.md](35-declaration-persistence.md) | current | yes | `tests/test_declaration.py`; ADR 0013 |
| 36 | [scale-runner.md](36-scale-runner.md) | current | yes | `tests/test_scale_runner.py`; ADR 0005, ADR 0017 |
| 37 | [download-on-aml.md](37-download-on-aml.md) | current | yes | `tests/test_download_aml.py` |
| 38 | [inference-on-aml.md](38-inference-on-aml.md) | current | implemented; cluster validation run pending | `tests/test_infer_aml.py`; `runbooks/38-inference-on-aml.md` |
| 39 | [training-data-on-aml.md](39-training-data-on-aml.md) | current | yes | `tests/test_training_data_aml.py` |
| 40 | [e2e-aml-demo-script.md](40-e2e-aml-demo-script.md) | current | yes | `tests/test_e2e_aml_demo_helpers.py`, `tests/test_plot_aml_timings.py`, `tests/test_restamp_cli.py`; ADR 0021 |
| 41 | [docs-refactor.md](41-docs-refactor.md) | current | P1 (this batch) done; P2-P5, P7 not started | `tests/test_docs.py`; ADRs 0022-0026 |
| 42 | [tutorial-fixture.md](42-tutorial-fixture.md) | current | not implemented | `runbooks/43-build-tutorial-fixture.md` written; generator scripts + `tests/test_tutorial_fixture.py` not yet written |
| 44 | [bundle-carried-adapter-code.md](44-bundle-carried-adapter-code.md) | current | **phase 1 implemented** (D1–D6 + amendment A1); phase 2 (D7/D8 `deploy`) not started | `tests/test_bundle_code.py` (23 tests); supersedes spec 38 D4 (§0); phase 2 would close `ROADMAP.md` §7 model-store question |
| — | [research-s2-reprocessing-dedup.md](research-s2-reprocessing-dedup.md) | current | n/a (research notes) | cited by spec 33 |

## Conventions
- **Numbers are never reused or renumbered.** A superseded spec keeps its number; read the one
  named in `superseded_by` instead.
- **`25b` and `research-s2-reprocessing-dedup`** are non-numeric-suffix filenames; `superseded_by`
  (when used) names the file's stem exactly as it appears in `specs/`, not a bare two-digit number.
- Status header format and rules: spec 41 D4 / ADR 0023. To regenerate this table: re-derive each
  row from `CHANGES.md`, `docs/adr/`, and the tests directory — do not hand-patch a stale row.
