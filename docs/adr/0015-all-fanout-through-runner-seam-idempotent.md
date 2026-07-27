# All parallel fan-out goes through the runner seam; the in-process `mp.Pool` is retired and outputs are idempotent

**Status:** accepted (spec 22, signed off 2026-07-07)

**Context.** After the local ROI-inference verb (spec 21), the datacube build (spec 08) and ROI
inference (spec 21) both parallelised through the **runner seam** (ADR 0004) — but
`run_inference(inference_datacubes=…)` still fanned out with an in-process `multiprocessing.Pool`
inside `engine.run_local`. That was a **second** parallelism mechanism that scale-out (P4) would have
to *replace* rather than *swap*. Separately, `engine.run_local` had **no idempotency** — a re-run
re-inferred every `(datacube, output)` pair and overwrote.

**Decision.** Route the `cores>1` inference fan-out through **Snakemake** (like the build and ROI
paths), and keep the `cores==1` / live-adapter path **in-process sequential**. Both paths **skip
existing outputs** (idempotent / resumable).

**Considered options.** Keep the `mp.Pool`. Rejected: it is the one fan-out not on the seam, so P4
would have to special-case it — the exact thing the runner seam exists to avoid.

**Consequences.** P4 (inference at scale) stays a pure `runner=` / `storage=` swap with no new
pipeline code. Re-runs skip already-computed cells for free, closing the gap the P0.75 demo exposed
(build skipped existing cubes, but inference re-did everything).
