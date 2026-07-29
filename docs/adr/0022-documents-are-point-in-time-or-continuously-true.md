# Every document is either point-in-time (never edited after the fact) or continuously-true (maintained and tested)

**Status:** accepted (spec 41 D3, grilled + agreed 2026-07-29/30)

**Context.** The corpus reached **201 markdown files / 284,441 words** and the user's complaint was
that they could no longer tell what was still true: *"runbooks are unreadable, and specs no one
would read."* The tempting reading is neglect — docs that nobody kept current. The measurements say
otherwise. **21 of 42 specs already carry a status line in about twelve different formats, 21 carry
none, and at least three are wrong** (spec 39 still reads `DRAFT — awaiting final sign-off` although
it shipped and the cluster ran it; specs 25b and 26 still read "awaiting implementation"). Three
other documents turned out to be **two documents fused**: `PROGRESS.md` is an always-current resume
anchor welded to a 38.7k-word historical log; `demos/E2E_AUSTRIA.md` is a tutorial welded to a
benchmark report, whose §2 heading reads *"CDSE now; MPC later"* — stale in the opposite direction
because it narrates one week's run inside a document people read as instructions; `TODO.md` is open
work welded to closed work welded to multi-page measurement findings.

The pattern is not laziness. A spec records what was decided *then*; a runbook records a procedure
executed *then*. **Nothing was ever supposed to keep them true**, and the corpus had no way to say
so. Meanwhile the documents a newcomer actually needs — a front door, a code map, a tutorial — are
the opposite kind, and fsd had never had one of those to maintain.

**Decision.** **Every document in the repo belongs to exactly one of two classes, and the class
determines its obligation.**

- **Point-in-time** — *never substantially edited after the fact.* Carries a status header
  (ADR 0023). Superseded by a *new* document, never by rewriting. Members: `specs/`, `runbooks/`,
  `demos/*.md`, `benchmarks/*.md`, `docs/adr/`, `docs/findings/`, `docs/progress-archive.md`.
- **Continuously-true** — maintained, and mechanically checked wherever a check is possible.
  Members: `README.md`, `ARCHITECTURE.md`, `CONTEXT.md`, `ROADMAP.md`, `docs/tutorial.md`,
  `docs/howto/*`, `docs/reference/*`, `PROGRESS.md`, the regenerated register indexes.

This is PEP 1's rule adopted wholesale: *"PEPs are no longer substantially modified after they have
reached the Accepted, Final, Rejected or Superseded state"*, and a resolved PEP is *"a historical
document rather than a living specification"*.

**Considered options.** **One class, all documents maintained** — rejected: it is what we
implicitly had, it requires editing 42 specs whenever the code moves, and it destroys the audit
trail that makes the specs valuable in the first place. **One class, nothing maintained** — rejected:
it is also what we implicitly had, and it produced a stale front door. **Per-document judgement, no
declared classes** — rejected as the status quo with extra words; the whole failure was that a
reader could not tell which kind of document they were holding.

**Consequences.** The rule binds decisions elsewhere and is why several obvious-looking shortcuts
are forbidden. We do **not** edit 30 point-in-time documents to chase a later rename — which is why
the TODO→Issues migration forces its numbers to align instead of rewriting 448 references
(ADR 0024), and why `demos/` is **not** renamed to `benchmarks/` despite being misnamed (ADR 0026).
Fused documents must be split rather than fixed: `PROGRESS.md` splits, and the demo docs keep their
results while their how-to content is extracted. Continuously-true documents acquire a real cost —
`tests/test_docs.py` means **docs can fail the test suite**, accepted deliberately because there is
no CI and `pytest` is run every session, making it the only mechanism with teeth. The residual
weakness is that class membership is itself a judgement recorded in a spec, so a new document type
(a benchmark report? a findings note?) needs someone to place it, and placing it wrongly reintroduces
exactly the ambiguity this ADR removes.
