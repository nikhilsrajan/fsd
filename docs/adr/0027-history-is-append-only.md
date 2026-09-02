# `docs/history.md` is append-only — a maintained container of point-in-time sections

**Status:** accepted (spec 43 D3, signed off 2026-09-02)

**Context.** [ADR 0022](0022-documents-are-point-in-time-or-continuously-true.md) classes every
document in this repo as either **point-in-time** (never substantially edited after the fact;
superseded rather than rewritten) or **continuously-true** (maintained, and mechanically checked
where possible). Spec 41 D3's table enumerates both classes — and `docs/history.md` appears in
**neither**. That is an omission rather than a decision: spec 41 deferred the file to spec 43, so
at the time the table was written there was nothing to class.

The omission has to be closed before the file exists, because the two classes prescribe opposite
maintenance obligations and the wrong one does real damage either way. Class it
**continuously-true** and a narrative of what happened acquires a standing obligation to be
rewritten as the project moves — which both invites the retroactive editing of history that
ADR 0022 exists to forbid, and puts it in permanent competition with `PROGRESS.md`, which is
already the maintained current-state document and is read at the start of every session precisely
because it is short. Class it **point-in-time** and the file can never be extended at all: it would
be frozen at the era it was written in, and a second era would require a second document, which is
the file-count accretion spec 41 D0 declined.

**Decision.** `docs/history.md` is **append-only**: the file is a *container* that is maintained,
and each **era section inside it is point-in-time** and is never substantially edited once its era
has closed. New work **appends a new era**; it does not revise an old one. A correction to a closed
era is recorded as an inline `**Correction (date):**` note, which is the same treatment spec 41
gives its own amendments (its A1) and the same instinct as Nygard's rule for a reversed decision:
*"we will keep the old one around, but mark it as superseded."*

This is [PEP 1](https://peps.python.org/pep-0001/)'s rule — documents are *"no longer substantially
modified"* once resolved, and a resolved one is *"a historical document rather than a living
specification"* — applied at **section** granularity rather than file granularity. It is also
exactly the relationship `PROGRESS.md` already has with
[`docs/progress-archive.md`](../progress-archive.md), so no new mental model is introduced.

The file carries a D4 status header of `current`, because the container is live. It sits inside
`docs/`, so `tests/test_docs.py::test_relative_links_resolve` link-checks it automatically — a
property that caught a broken link on the very first run.

**Considered options.** **Continuously-true**, with the story kept current to "now" — rejected
above: it licenses retroactive editing and duplicates `PROGRESS.md`. **Point-in-time, frozen** —
rejected: a history that cannot be extended forces a second file per era. **A `docs/history/`
directory, one file per era** — rejected on spec 41 D12's reasoning for the single-file archive:
nobody browses a history by file, and a directory invents boundaries the era headings already carry
better. **Amend spec 41 D3's table in place** — rejected because spec 41 is itself a point-in-time
document and ADR 0022 forbids editing it after the fact; recording the new class as a *new* ADR is
what that rule prescribes.

**Consequences.** A third class now exists, so "point-in-time or continuously-true" is no longer an
exhaustive binary and future documents may reasonably ask for it — the bar is that append-only is
for documents whose *content* accumulates in closed, dated units, not for documents that are merely
long. `docs/history.md` also gains an obligation nothing enforces: an era that closes without being
appended leaves the file silently incomplete. That is accepted deliberately. Spec 43 D4's rule —
the story ends at a **named milestone**, not at "now" — is what makes the incompleteness honest
rather than misleading: the file is never *wrong*, only not yet extended, and it says where it
stops.
