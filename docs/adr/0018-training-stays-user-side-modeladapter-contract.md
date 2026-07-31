# Model training stays on the user's side; fsd defines a ModelAdapter contract + portable bundle

**Status:** accepted (spec 18, signed off + implemented + verified 2026-07-06; `ROADMAP.md` F1–F5)

**Context.** fsd is a **data-prep + inference-at-scale** pipeline; the researchers who use it bring
their own trained models (scikit-learn, torch, …). fsd needs to *run* those models at scale without
owning how they are trained or hard-coding any one model.

**Decision.** **Model training is permanently out of fsd's scope.** fsd defines a **`ModelAdapter`
contract** — a `module:attr` code reference the pipeline calls — and a **portable bundle** (weights +
that code reference + the spec; see ADR 0002). `run_inference` is the verb that consumes the contract;
`deploy` is the P6 contract-pinning stub. The pipeline is model-agnostic behind the adapter.

**Considered options.** **Fold training into fsd** — rejected: out of scope and inherently
model-specific. **Pickle a live model object as the portable unit** — rejected: couples the artifact
to the runtime; the bundle carries a code *reference* + weights, and the adapter code + deps live in a
separate image (ADR 0002).

**Consequences.** New model families are onboarded by writing an adapter + bundle, not by changing
fsd. The bundle/image split (ADR 0002) governs how adapter code and dependencies reach a node. P6
`deploy()` is where bundle registration + image build later get automated — the bundle *format* does
not change.
