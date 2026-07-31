# Orchestration is a runner seam over one CLI unit-of-work; Snakemake is only the local runner

**Status:** accepted (spec 00 requirements interview; spec 08; spec 36 / P2)

**Context.** The pipeline must fan a per-work-unit task out over many geometries — locally today,
across a cloud cluster later — without rewriting the pipeline when the executor changes.

**Decision.** The **unit-of-work is a single CLI task** (build one datacube; later, build+infer one
grid cell — spec 21). A **swappable runner** dispatches that task over N inputs. **Snakemake is the
*local* runner only**; the cloud runner (spec 36) dispatches the *same* task unchanged. The
`runner=` choice never leaks into the task CLI — the task has no idea who is running it.

**Considered options.** Bake orchestration into the pipeline code (a `multiprocessing` pool or a
Snakemake dependency inside the builder). Rejected: it couples the algorithm to one scheduler, so
scaling out becomes a rewrite instead of a config swap.

**Consequences.** Cloud scale-out is a **runner swap, not new pipeline code** (the P2/P4 promise).
Every parallel fan-out in fsd must go through this seam — which is why the last in-process pool was
later retired onto it (see ADR 0015). The concrete scale backend chosen is AML, not Batch (see
ADR 0005).
