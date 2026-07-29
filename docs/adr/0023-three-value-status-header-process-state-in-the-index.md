# Point-in-time documents carry a three-value status header; process state lives in a regenerated index

**Status:** accepted (spec 41 D4, grilled + agreed 2026-07-29)

**Context.** Given ADR 0022, every point-in-time document needs a machine-readable label. The
obvious vocabulary is the process one — `draft` → `signed-off` → `implemented` — because that is how
the work actually flows, and because 21 of 42 specs already carry an ad-hoc version of it
(`Status: SIGNED OFF + IMPLEMENTED + VERIFIED (2026-07-06)`, `🚧 DRAFT — awaiting final sign-off`,
and ten more spellings).

But process state is exactly what went stale. Spec 39 shipped and its header still said DRAFT; 25b
and 26 still said "awaiting implementation". And process state is not what a reader wants. A reader
opening `specs/33-*.md` has one question: **can I trust this as a description of fsd today?** Any
field that does not answer that question is a field that will drift, because nothing forces a
hand-edited header to be revisited when the code moves.

**Decision.** **Three values, plus a summary line. Process state is demoted to a regenerated
index.**

```yaml
---
status: current | superseded-by-NN | historical
superseded_by: 40          # only when status is superseded-by-NN
summary: One sentence — what a reader needs to decide whether to open this file.
---
```

- `current` — no known contradiction; still describes the system.
- `superseded-by-NN` — read NN instead.
- `historical` — its subject no longer exists (the deleted `satellite_benchmark/` archive;
  CDSE-as-demo-source per spec 40 A1; the retired in-process `mp.Pool` per ADR 0015).

**Implementation status** (`implemented`, `not implemented`, `partially implemented`) moves to
`specs/README.md` and `runbooks/README.md`, which are **regenerated**, and sits beside its evidence
(an ADR, a test file, or an explicit "not implemented"). An index is rebuilt; a header is
hand-edited and therefore forgotten.

**Excluded from the header:** dates, sign-off records, model/effort notes. Git has all of them and
each would be a future stale line.

**Considered options.** **PEP 1's full vocabulary** (Draft · Active · Accepted · Provisional ·
Deferred · Rejected · Withdrawn · Final · Superseded) — rejected as nine values for a corpus of 65
documents with one author; the distinctions it draws are about a public review process fsd does not
run. **A fourth `unverified` value** for documents where no positive evidence was found either way —
rejected (user, 2026-07-29): on 42 files it would land on the majority, tell the reader nothing they
did not already know, and reduce the whole exercise to a shrug. `current` is a *falsifiable* claim
that can be corrected; `unverified` cannot be wrong and therefore cannot be useful. **Keeping
implementation status in the header** — rejected: it is the specific field that is already wrong on
three files.

**Consequences.** Determining a status needs no code archaeology — all three values are derivable
from evidence already written down in `CHANGES.md`, the ADRs, and the "Superseded in part" notes
several specs already carry. The corpus becomes greppable by trustworthiness, which is the whole
point: `status: current` is the filter a newcomer applies. `test_docs.py` can assert the header
parses and that every `superseded_by` names a file that exists, so the *shape* is enforced even
though the *judgement* is not. The accepted risk is that `current` is inferred from absence of
contradiction, so a spec that is subtly wrong in a way nothing recorded contradicts will be stamped
`current` and be wrong — mitigated by a sampling gate (the user picks 10; more than one error means
the batch is redone rather than patched), not by hedging the vocabulary.
