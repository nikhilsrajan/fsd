# demo ≠ benchmark ≠ example ≠ tutorial — the "demo" gap is three artifacts, not one document

**Status:** accepted (spec 41 D10, grilled + agreed 2026-07-29)

**Context.** `demos/` was believed to be fsd's demonstration and on-ramp; `demos/README.md` calls
`E2E_AUSTRIA.md` *"the go-to end-to-end guide"*. The user disagreed with their own earlier framing
(2026-07-29): *"even though we stated that e2e_austria\* are demo docs, their primary purpose was to
time the individual steps involved. A true demo doc to me is not simply run, but something people can
read and follow and write their own demos with."*

The measurements confirm it decisively. **`e2e_austria.py` is 531 lines of which 12 touch `fsd` at
all** (2.3%), exercising three public functions; the rest is logging, `timed_step`, preflight,
plotting, ROI construction and report writing. Worse, **`step_download` bypasses `fsd.download`
entirely**, calling `cdse.probe_throughput` and `cdse.download_resume` directly — because it wants
the single-stream baseline probe and the transfer-vs-convert split, which are *measurement*
concerns. So the one worked reference implementation teaches **the wrong API**. Meanwhile
`benchmarks/` already exists holding exactly this pattern (harness + `*_report.md` + stats JSON)
eight times over, and `examples/` exists containing **one** file.

Diátaxis explains why the documents failed as well as the code did: *"tutorials are
learning-oriented, and how-to guides are task-oriented"*; a tutorial promises *"if the reader follows
those steps, they'll arrive at a successful conclusion"* while *"a how-to guide cannot promise
safety"*; in a tutorial *"responsibility lies with the teacher"*, in a how-to *"the user has
responsibility"*. `E2E_AUSTRIA.md` is a tutorial fused to a benchmark report, which is why its §2
heading reads *"CDSE now; MPC later"* — it narrates one week's run inside a document people read as
instructions.

**Decision.** **Four distinct artifact kinds, named in `CONTEXT.md`, and the missing on-ramp is
three of them, not one document.**

- **`examples/*.py`** — minimal, readable, copy-paste scripts. No timing, resume, signal handling or
  plotting. ~60–80 lines, pure verb composition. The thing you copy and edit.
- **`docs/tutorial.md`** — narrates one example on **fixed** data (spec 42's committed fixture).
  Teaches the mental model. **Must not fail.**
- **`docs/howto/your-own-region.md`** — "now point it at your region": what to change, sizing,
  cross-UTM, diagnosis. May fail, and says how to tell.
- **`demos/` + `benchmarks/`** — **timing harnesses** and their **benchmark reports**,
  point-in-time (ADR 0022), keeping their results, timings and appendices.

**`demos/` is deliberately NOT renamed to `benchmarks/`** despite being misnamed, because renaming
churns references across point-in-time documents, which ADR 0022 forbids. `demos/README.md` states
what the directory actually is instead, and the two `.md` files get status headers with their
prerequisites/env-var/run-it sections replaced by links to the extracted docs.

**Considered options.** **One combined "demo guide"** — rejected: it is precisely the fusion being
undone, and Diátaxis names the failure mode (a document that hand-holds the expert and abandons the
beginner). **Make `e2e_austria.py` readable enough to serve as the example** — rejected: the harness
concerns are the *point* of that file, and stripping them destroys the benchmark. **Rename `demos/`
to `benchmarks/`** — rejected on ADR 0022. **A cookbook of examples instead of a linear tutorial** —
not rejected, deferred: `examples/` may grow to several small scripts, but a first-timer needs one
guaranteed path before a menu.

**Consequences.** The extraction is largely **de-duplication rather than authoring**, because the
missing documents partly exist inside the benchmark reports already — `E2E_AUSTRIA.md` §3–5 is the
tutorial, §4+§9 the your-own-region how-to, and `E2E_AUSTRIA_AML.md` §8.1–8.3 the cloud how-to plus
the env-var reference. That materially lowers the risk of the writing phase. It also shrinks the
deferred spec 40 §7 (rewrite `E2E_AUSTRIA_AML.md` around the new run) to "update the numbers in a
report". The tutorial's must-not-fail promise is what forces a committed offline fixture (spec 42),
which is the largest single piece of new engineering the docs refactor requires — a cost traceable
entirely to this ADR. And `demos/` stays permanently misnamed, a wart accepted on purpose: the
directory name says "demo" while `CONTEXT.md` and its own README say "benchmark harness", which is a
small standing confusion in exchange for not rewriting history.
