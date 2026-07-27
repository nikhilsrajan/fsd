# The scale runner is Azure ML (AML), not Azure Batch — the seam is what's locked

**Status:** accepted (spec 36; `ROADMAP.md`; `runbooks/36-runner-fork-probe.md`; widened 2026-07-21)

**Context.** The roadmap originally promised "Azure **Batch** at scale" with `runner="batch"`, and
much of the strategy framing (and the `rise` Terraform reference) assumed Batch. Before committing,
`36-runner-fork-probe.md` measured what the `rise` platform could actually run.

**Decision.** The scale-out backend is the **`rise` AML cluster** (`runner="aml"`). What is being
locked is **the seam** — cloud as a swappable backend behind the runner interface (ADR 0004) — **not
a product name**. Batch is dropped as the target.

**Considered options.** Azure **Batch** (the original plan). Rejected after the fork probe: the seam
is already demonstrated end-to-end by local-Snakemake ↔ AML, and the Batch path carried avoidable
friction (quota bumps, `max_tasks_per_node`) for no additional capability the demo needs.

**Consequences.** P2 (datacube fan-out) and P4 (inference at scale) both target the AML cluster; P4
reuses the P2 runner. Roadmap wording was widened from "on Azure Batch at scale" / `runner="batch"`
to "the same pipeline on Azure at scale" / `runner="aml"`. Revisit only if a concrete need appears
that only Batch satisfies — YAGNI until then. AML's identity model then forced ADR 0017.
