# The TODO migrates to GitHub Issues with forced number alignment; the 448 existing references are never rewritten

**Status:** accepted (spec 41 D8, grilled + agreed 2026-07-29)

**Context.** `TODO.md` reached **16.9k words across 62 rows** and the user could no longer find what
was outstanding: *"the todo is lengthy and honestly too difficult to go through and find out what
exactly is missing."* Three genres were fused in it — open work, closed work (**29 of the 62 rows**),
and multi-page measurement findings (row #59 is 1,137 words, #61 is 792). In open-source practice
the first genre lives in an issue tracker, where closed items leave the default view for free and
labels and milestones do the slicing a markdown table cannot.

The obstacle is reference integrity. **`TODO #NN` appears 448 times across 30+ files** — specs,
runbooks, ADRs, `PROGRESS.md`, `CHANGES.md`, the demo write-ups. If TODO #61 becomes issue #12,
every one of those becomes a puzzle. Two facts, both measured, open a third way: `TODO.md` is
numbered **1–62 with zero gaps**, and the repository has **never had an issue, a pull request or a
discussion** — and GitHub assigns numbers from a **single shared counter per repository** across all
three ([community discussion #69759](https://github.com/orgs/community/discussions/69759)).

**Decision.** **Create issues strictly in order 1 → 62, including all 29 already-closed rows
(created, then immediately closed), so that GitHub #N lands on TODO #N exactly.** All 448 references
resolve permanently and `gh issue view 47` becomes the canonical way to read TODO #47. `TODO.md`
becomes a ~10-line stub pointing at Issues and `docs/findings/` — kept, not deleted, because 448
references name it. The measurement essays are extracted to `docs/findings/` as point-in-time
documents (ADR 0022) with one-line issues pointing at them.

Three conditions are binding. **(1)** Immediately before creating, `gh issue list --state all`,
`gh pr list --state all` **and** the discussions endpoint must *all* be empty; if any is not,
alignment is impossible and the fallback is a mapping table — no partial attempt. **(2)** Creation is
**strictly sequential, never parallel**: concurrent creates can race and a misnumber is unfixable
because GitHub will not renumber, so each create is verified against its expected number and the run
**halts on the first mismatch**. **(3)** The user reviews a manifest of all 62 entries before any
issue is created, because issues cannot be cleanly deleted afterwards, only closed.

**Considered options.** **Accept an offset and publish a 62-row mapping table** — rejected: a
permanent translation layer imposed on every future reader to avoid a one-time cost. **Rewrite the
448 references** — rejected, and on principle rather than effort: it would edit 30 **point-in-time**
documents to chase a later decision, which ADR 0022 forbids. A runbook written on 2026-07-11 should
not be modified in 2026-07-30. **Keep everything in files, split into open/closed lists** — the
user's own first proposal, and viable; rejected because the tracker gives labels, milestones and
automatic hiding of closed work for free, and `gh` keeps it greppable from the working tree.

**Consequences.** A benefit not anticipated when this was sized as "29 rows retired": the closed
rows **stop being deletions**. They become closed issues — searchable, linkable, full text intact —
and several are story-grade for the deferred history spec (one reads *"✅ CLOSED, but its ROOT CAUSE
WAS WRONG — ❌ RETURNED"*). The costs are real. The repository is **public**, so an issue is a
publication: nothing from `AZURE_INFRA_PRIVATE.md` may appear in an issue body, and that becomes a
standing habit rather than a one-time check. Open work stops being visible in a plain `grep` of the
working tree and needs a `gh` call. `CLAUDE.md` must be edited in the same change, since it names
`TODO.md` as a living register to keep current. And the alignment property is **fragile exactly
once** — if the pre-flight is skipped and any issue, PR or discussion already exists, the whole
scheme silently produces a one-off error in 448 places.
