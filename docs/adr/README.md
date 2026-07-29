# Architecture Decision Records

Each ADR captures one significant, lasting decision: its context, the decision, the options
rejected, and the consequences. Format follows `0001`/`0002`. Numbers are immutable; supersede a
decision with a new ADR that references the old one rather than editing history.

Most ADRs `0003`–`0019` were back-filled from the specs, `DROPPED.md`, `ROADMAP.md`, and the
runbooks — the decision was already made and recorded there; the ADR gives it a single canonical
home. The cited spec/date is the source of record.

| ADR | Decision | Source |
|-----|----------|--------|
| [0001](0001-remote-cog-publish-in-to-cog.md) | Remote-dst COG publishing lives in `raster.cog.to_cog`, not its callers | spec 38 / P4 |
| [0002](0002-bundle-and-inference-image-decoupled.md) | The model bundle and the inference image are decoupled artifacts | spec 38 / P4 |
| [0003](0003-all-file-io-through-storage-seam.md) | All file I/O flows through the `fsd.storage` (fsspec) seam | spec 00 / 10 |
| [0004](0004-runner-seam-over-cli-unit-of-work.md) | Orchestration is a runner seam over one CLI unit-of-work; Snakemake is only the local runner | spec 00 / 08 / 36 |
| [0005](0005-scale-runner-is-aml-not-batch.md) | The scale runner is Azure ML (AML), not Azure Batch — the seam is what's locked | spec 36 |
| [0006](0006-catalog-is-file-based-geoparquet.md) | The tile catalog is a file-based GeoParquet store | spec 00 / 02 |
| [0007](0007-in-memory-datacube-builder.md) | Datacubes are built in memory with the `(data, profile)` op convention | spec 00 / 03 |
| [0008](0008-datacube-on-disk-format.md) | On-disk datacube format = `datacube.npy` + `metadata.pickle.npy` | spec 03 |
| [0009](0009-cdse-discovery-via-anonymous-stac.md) | CDSE discovery via the anonymous STAC API; drop `sentinelhub`/`boto3`/SAFE-listing | DROPPED / BUG-001 |
| [0010](0010-calendar-interval-mosaic-default.md) | The default cube time axis is a calendar-interval median mosaic | spec 15 |
| [0011](0011-ingest-stores-raw-dn-declares-radiometry.md) | Ingest stores raw DN and declares radiometry as metadata; never bakes normalized pixels | spec 34 D1 |
| [0012](0012-builder-generic-via-artifact-self-description.md) | The datacube builder is a generic engine driven by per-artifact self-description | spec 34 D2 |
| [0013](0013-unstamped-catalog-raises-loudness-rule.md) | An unstamped file-backed catalog raises; only an in-process gdf gets the S2 default | spec 35 |
| [0014](0014-single-cog-chokepoint.md) | One COG chokepoint: `raster.cog.to_cog` | spec 14 / 18 |
| [0015](0015-all-fanout-through-runner-seam-idempotent.md) | All fan-out goes through the runner seam; retire the in-process `mp.Pool`; outputs are idempotent | spec 22 |
| [0016](0016-stac-is-thin-additive-export-view.md) | STAC is a thin, additive export view over the GeoParquet catalog — not the store | spec 17 |
| [0017](0017-aml-identity-via-azure-client-id.md) | AML user-assigned identity is selected via `AZURE_CLIENT_ID` set by the runner; no fsd code change | spec 36 D4 |
| [0018](0018-training-stays-user-side-modeladapter-contract.md) | Training stays user-side; fsd defines a ModelAdapter contract + portable bundle | spec 18 |
| [0019](0019-download-pipeline-disk-aware-backpressure.md) | Download is one continuous pipeline with disk-aware `MAX_STAGED` backpressure; convert pool = processes | spec 25 |
| [0020](0020-general-purpose-images-emit-raw-adapter-transform-at-endpoints.md) | General-purpose pipeline images emit raw; the adapter feature transform runs only at model-specific endpoints (driver-side training features + inference image) | spec 39 |
| [0021](0021-dispatch-telemetry-is-a-file-not-a-return-value.md) | Dispatch telemetry is a durable file beside `_status/`, not a value returned to the caller | spec 40 |
| [0022](0022-documents-are-point-in-time-or-continuously-true.md) | Every document is either point-in-time (never edited after the fact) or continuously-true (maintained and tested) | spec 41 D3 |
| [0023](0023-three-value-status-header-process-state-in-the-index.md) | Point-in-time documents carry a three-value status header; process state lives in a regenerated index | spec 41 D4 |
| [0024](0024-todo-migrates-to-issues-with-forced-number-alignment.md) | The TODO migrates to GitHub Issues with forced number alignment; the 448 existing references are never rewritten | spec 41 D8 |
| [0025](0025-one-fact-one-home.md) | One fact, one home — each topic has exactly one owning document; everything else links | spec 41 D9 |
| [0026](0026-demo-benchmark-example-tutorial-are-four-things.md) | demo ≠ benchmark ≠ example ≠ tutorial — the "demo" gap is three artifacts, not one document | spec 41 D10 |
