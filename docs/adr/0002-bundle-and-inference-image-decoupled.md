# The model bundle and the inference image are decoupled artifacts

**Status:** accepted (2026-07-23, spec 38 / P4)

**Context.** Running a user's trained model on a cluster node needs two things: the trained **weights**
and the **adapter code + its runtime dependencies** (e.g. scikit-learn/joblib, or torch). A bundle
(spec 18) is a self-describing folder carrying weights + a `module:attr` code *reference* + the spec — it
does **not** carry the code or the deps.

**Decision.** Keep the two decoupled. The **bundle** (weights + code reference + spec) is portable data,
staged to blob per run and fetched to a node's scratch. The adapter code + deps live in a separate,
dedicated **AML inference Environment/image** — the author's *installable package*, pip-installed at
image-build time on top of `fsd[azure,mpc]`. The dispatcher references the image **by name**
(`run_aml_inference(environment=…)`). Responsibility split: the **model author** owns the image's
contents (installable adapter + pinned deps) and the bundle; the **operator** builds/registers the image
(a run-book step); the **dispatcher** just names it — no per-run image build.

**Considered options.** Ship the adapter code + deps *inside* the bundle and run a generic fsd image that
`pip install`s them at node cold-start. Rejected: runtime dependency resolution on every cold node, no
build-time validation of the adapter import, and slower startup.

**Consequences.** Dependency installation and adapter-import validation are front-loaded to image-build
time, gated by a one-node adapter-import smoke (spec 38 D11) — a missing `sklearn` fails once at
build/smoke, not on every fan-out node. One image serves many runs and bundles of a model family. For P4
the image is built by an operator run-book step; **P6 `deploy()` is the home where image-build later gets
automated** (register the bundle + build/ensure its inference Environment) — the bundle *format* does not
change.
