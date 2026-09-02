---
status: current
summary: docs/history.md — the narrative of what happened and why, told as eras defined by their forks. Fills the one Diátaxis quadrant spec 41 named but never built (explanation), and gives the dropped forks their only home: DROPPED.md is legacy-capability triage and mentions rslearn, the Leaflet dashboard and C4 zero times. Append-only, ~5k words, ends at a named milestone.
---

# Spec 43 — `docs/history.md`: the story, told as eras defined by their forks

**Status:** **SIGNED OFF (user, 2026-09-02)** — the D6 era list confirmed ("eras look right"),
and §7's remaining three questions resolved as proposed. Not implemented. · **Opened:** 2026-09-02
**Implements:** [#55](https://github.com/nikhilsrajan/fsd/issues/55), whose remaining half this is.
**Closes:** [spec 41](41-docs-refactor.md) **P8**, its last unbuilt phase.
**Origin:** #55 (user, 2026-07-23) asked for *"a single chronological story of what happened from
inception to now — the why, the forks taken/dropped, the measurements that decided them"*, plus a
C4 doc set. **The C4 half is already closed by spec 41 D0** and is not re-opened here (§2).
**Related:** [spec 41](41-docs-refactor.md) (the parent; D0, D1, D3, D9, D12, P8),
[ADR 0022](../docs/adr/0022-documents-are-point-in-time-or-continuously-true.md) (the class this
spec extends), [ADR 0025](../docs/adr/0025-one-fact-one-home.md) (why this document links rather
than restates).

---

## 1. The problem

fsd's written record is **174 files / ~399k words** built in **382 commits between 2026-07-06 and
2026-09-02** — 61 specs, 30 run-books, 26 ADRs, 4 findings, and two progress logs. Every one of
them answers *what was decided* or *what is true now*. **None of them answers what happened.**

Three gaps, each measured rather than asserted:

**(1) The dropped forks have no home at all.** `DROPPED.md` looks like the register for this and is
not: it is **legacy-capability triage** — what the three legacy repos had that fsd v1 does not
carry. Grepped 2026-09-02: it mentions **rslearn, the Leaflet dashboard, C4 and the SQLite catalog
strategy zero times**. The ADRs cannot hold them either, by construction — Nygard's format records
a decision *taken*, in active voice (*"We will…"*). The fork that was examined for a week and
**not** taken is nobody's row. That covers, among others: the fsd Leaflet dashboard (cancelled
2026-07-14 for STAC+COGs into stock pgSTAC/titiler), rslearn as fsd's download layer (evaluated on
a dedicated branch, declined 2026-07-31), a multi-file C4 doc set (spec 41 D0), and *"the datacube
builder normalizes"* (reversed onto the downloader, 2026-07-17).

**(2) Diátaxis's fourth quadrant was named and never built.** Spec 41 adopted Diátaxis as its
organising frame and built **three** of the four modes — `docs/tutorial.md`, `docs/howto/*`,
`docs/reference/*`. The word *explanation* appears **once** in all 587 lines of spec 41: in the
list of the four modes. Diátaxis defines explanation as *"understanding-oriented"*, with a
perspective *"higher and wider than that of the other three types"*, whose job is to *"explain why
things are so — design decisions, historical reasons, technical constraints"* and which *"can and
must consider alternatives"*. That is #55's request restated in someone else's vocabulary, and it
is the empty slot in fsd's own docs tree.

**(3) The audience is already promised this file.** Spec 41 D1's table serves reader A
(*future-you, months later*) with `PROGRESS.md` + `ARCHITECTURE.md` + **`docs/history.md`**, and
D9's one-fact-one-home table gives *"what happened and why"* a single home: **`docs/history.md`**.
Both have pointed at a file that does not exist for five weeks.

**What this is not.** It is not a changelog — `CHANGES.md` is that, and Keep a Changelog is right
that *"using commit log diffs as changelogs is a bad idea: they're full of noise"*. It is not an
ADR index. It is not a status document; `PROGRESS.md` is, and is read at the start of every
session precisely because it is short.

---

## 2. Scope

**In scope:** one new file, `docs/history.md`, and the two register edits that stop it drifting
(§3 D9). No code. **If a `src/` diff appears, the scope has drifted.**

**Explicitly out of scope, with the reason:**

| Not doing | Why |
|---|---|
| A multi-file C4 doc set | **Closed by spec 41 D0**, deliberately and with reasons. C4 survives as the section outline of `ARCHITECTURE.md`, which exists. Do not re-propose it. |
| A front-door pass (`README` → tutorial → how-tos) | Real work with its own evidence base — `docs/findings/consumer-repo-friction.md`, eight friction points, four hard stops. It gets its own issue and spec (D9). #55 has been open since 2026-07-23 through one scope change already. |
| Retiring or trimming any register | D8. Nothing is deleted. |
| Re-archiving `PROGRESS.md` | It has regrown from D12's ~2k-word target to **1,610 lines**. Observed, filed as an issue (D9), not fixed here. |

---

## 3. Decisions

### D1 — `docs/history.md` is Diátaxis **explanation**, and that is what settles its content

The one test for whether a paragraph belongs: **does it deepen understanding of why fsd is shaped
the way it is?** Not "did it happen" — the archive holds everything that happened. Diátaxis's own
prescriptions become this document's rules:

- *"Provide background and context… explain why things are so"* ⇒ every era answers a question the
  project was facing, not a date range it occupied.
- *"Explanation can and must consider alternatives, counter-examples"* ⇒ **an era with no dropped
  fork is not finished** (AC2).
- *"The perspective… is higher and wider"* ⇒ it never explains *how to* do anything. A reader who
  wants to run something is sent to the tutorial or a how-to.

### D2 — The spine is **eras, told by their forks** (user, 2026-09-02)

Chronological acts; **inside each act, the forks taken and dropped and the measurement that decided
them.** Rejected: strict chronology (the archive already is that, prettier), decision-ordered and
atemporal (loses the arc, overlaps `docs/adr/` hardest), and spec-number order (the repo's filing
system is not a narrative — this spec being numbered 43 in September is proof).

### D3 — The document class is **append-only**, which closes a gap spec 41 left open

Spec 41 D3 classes every document as point-in-time or continuously-true. **`docs/history.md` is in
neither list** — an omission, not a decision, since the file did not exist. Closed here:

> **Append-only** — the file is a *container* that is maintained; each **era section inside it is
> point-in-time** and is never substantially edited once its era has closed. New work appends a new
> era; it does not revise an old one. A correction to a closed era is an inline `**Correction
> (date):**` note, exactly as spec 41 takes amendments (its own A1).

This is PEP 1's rule applied at section granularity rather than file granularity, and it is the
same relationship `PROGRESS.md` already has with `docs/progress-archive.md`. It carries a D4 status
header of `current` (the container is live), and it is **inside `docs/`**, so
`tests/test_docs.py::test_relative_links_resolve` link-checks it from the moment it exists —
mechanically, for free.

### D4 — It ends at a **named milestone**, not at "now"

The story closes at **the consumer-repo run, 2026-09-02** — the first time the full pipeline ran
from a separate repository with fsd installed as a dependency, and the run that discharged #55's
own gate. Ending at "now" would make the file continuously-true, put it in permanent competition
with `PROGRESS.md`, and guarantee it is stale within a week. A named endpoint is what makes D3
work.

### D5 — Target length **~5,000 words** (accept 4,000–6,000)

A 20–30 minute read, from ~399k words of source — a ~80:1 distillation. Budget: ~400 opening,
~550 per era, ~300 closing. **A shorter document is not a better one here**: the first thing cut
under a tight budget is the dropped forks, which are the only thing this file uniquely owns.
Over 6,000 words it stops being read by reader A, which defeats the point.

### D6 — **Eight eras**, each named by its question

The count is a decision, not an accident: it is the number of times the project's central question
actually changed. **±1 is permitted during writing if the evidence demands it, with the reason
recorded in the era's own text.** The forks and measurements below are the **outline**, not
finished claims — each is sourced at writing time from the register named in D7 (AC5).

| # | Era | Span | The question it answers | Fork taken → dropped |
|---|---|---|---|---|
| 1 | The clean-room floor | 07-06 → 07-11 | What does fsd actually have to reproduce? | Port behaviour, not code, from three legacy repos → the SQLite catalog stack, and later `rio_cogeo`. Spec 24 makes the *process* a designed artifact, not just the pipeline. |
| 2 | Austria, and the dashboard nobody built | 07-13 → 07-15 | What does fsd owe a viewer? | fsd emits standard STAC + COGs + a render config into stock pgSTAC/titiler → **the fsd Leaflet dashboard, cancelled**. |
| 3 | Who normalizes? | 07-16 → 07-18 | Where does radiometric truth get established? | The **downloader** normalizes and declares → the datacube builder doing it (a reversal of a shipped design). MPC joins CDSE as a source; the storage seam is proven on blob. |
| 4 | Onto the cluster | 07-20 → 07-29 | Does any of this survive leaving one machine? | The runner seam over a CLI unit-of-work, on AML → Azure Batch as the first scale target. Ends with the merged crop map, green, and a timed demo. |
| 5 | The corpus turns on itself | 07-30 → 07-31 | Can anyone but the author read this? | Point-in-time vs continuously-true; `TODO.md` → 62 **number-aligned** issues → rewriting 448 references. **This spec is that era's last unbuilt phase.** |
| 6 | Build vs borrow | ~07-31 | Should fsd exist at all, given rslearn? | Keep fsd, positioned as a GEE alternative for simpler models → **rslearn as fsd's download layer**; rslearn-on-Azure becomes a separate project. Evaluated on its own branch before deciding. *(Calendar-overlaps era 5 — named, not fudged.)* |
| 7 | Making the cluster path honest | 08-19 → 08-21 | Does the driver tell the truth about what ran? | Bundles carry their adapter's source; runs are addressable; the driver stops reporting work it did not do → silent success on stale work lists. |
| 8 | fsd as an installed package | 08-21 → 09-02 | Is it pleasant to use from outside its own checkout? | A separate consumer repo with fsd pinned as a dependency → doc-following as evidence of usability. Closes on a measurement: the post-run window **777 s → 36 s**. |

### D7 — The source set is the **whole record**, and `git log` is not in it

The handoff into this work named `docs/progress-archive.md` as *the* archaeology source. **Measured
2026-09-02: necessary, not sufficient.** Specs **48–53 and the entire notebook-usability sprint
appear zero times in it** — `PROGRESS.md` regrew to 1,610 lines and holds 2026-08-20 → 09-02
itself. The archive is also **not chronologically ordered**: its 2026-08-19/20 entries sit *after*
its 2026-07-06 ones. Both are traps for a writer who trusts the file's name.

| Source | What it is good for | Words |
|---|---|---|
| `docs/progress-archive.md` | 73 entries, 07-06 → 08-21: the day-by-day *why* | 51k |
| `PROGRESS.md` | 08-20 → 09-02, which the archive does not cover | 18k |
| `CHANGES.md` | behaviour kept-but-changed — the reversals, with reasons | 21k |
| `docs/adr/` (26) | the decisions taken, already distilled | — |
| `docs/findings/` (4) | the measurements, already distilled | — |
| `DROPPED.md` | legacy-capability triage **only** — do not mistake it for the fork register | 1.4k |
| `spike/` + `RSLEARN_COMPARISON.md` | the only record of era 6 | 1.4k+ |
| `ROADMAP.md` | where it was going at each point, vs where it went | 4k |

**`git log` is not a source** (Keep a Changelog: commit diffs are *"full of noise"*). Neither is a
subagent's summary: this is a synthesis judgement, and the accretion #55 exists to undo is exactly
what cold summarisation produces.

### D8 — One fact, one home: history **links**, and never becomes the only home

Per ADR 0025. Every decision's home stays `docs/adr/`; every measurement's home stays
`docs/findings/` or `CHANGES.md`; every design's home stays its spec. `docs/history.md` supplies
the **connective tissue** — the ordering, the causation, and the forks that no register owns —
and links out for the detail. **Nothing may be stated only here** except the narrative itself
(AC6). Nothing is retired when it lands: #55's own text says the living registers stay as the
audit trail, and D3 forbids editing point-in-time documents anyway.

### D9 — Two register edits, and two issues filed rather than fixed

**Edits (part of this spec's delivery):** add `docs/history.md` to spec 41 D3's class table under
the new append-only class, by way of a **new ADR** (`0027-history-is-append-only.md`) rather than
by editing spec 41, which D3 forbids; and add the file to `README.md`'s "Where to go next".

**Filed as issues, not fixed here:** (a) the front-door pass against
`docs/findings/consumer-repo-friction.md`; (b) `PROGRESS.md` has regrown to 1,610 lines against
D12's ~2k-word target, so the split needs re-running.

### D10 — Two prohibitions, one of them evidence-backed

**No concrete Azure identifiers.** This is a public MIT repo and this document is *prose written
about real runs* — the exact class that has leaked live identifiers **four separate times**
(`RECIPES.md`'s sweep caught the last on 2026-07-30, in two tracked public files). The sweep is
therefore an acceptance gate, not a courtesy (AC4). Concrete values stay in
`AZURE_INFRA_PRIVATE.md`, at the workspace root, never here.

**No scoring.** The story records what was decided and what it cost. It does not grade the author,
rate the pace, or read a quiet calendar week as a stall — a working-days count is the only honest
unit, and this is a one-author project. A defect found late is a finding, not a failure.

---

## 4. Acceptance criteria

| # | Criterion | How checked |
|---|---|---|
| AC1 | 4,000–6,000 words; 8 eras (±1, with the reason in the text) | `wc -w` |
| AC2 | **Every era names at least one fork *dropped* and at least one measurement with a number** | Opus review, era by era |
| AC3 | Every relative link resolves | `tests/test_docs.py::test_relative_links_resolve` — automatic, the file is under `docs/` |
| AC4 | `RECIPES.md`'s identifier sweep is clean over the new file | the sweep, before commit |
| AC5 | Every fork and measurement traces to a register named in D7 | Opus review; a claim with no source is cut, not softened |
| AC6 | No fact lives only here (D8) | Opus review against ADR 0025 |
| AC7 | It ends at the 2026-09-02 consumer-repo run and does not describe later work | read the last section |
| AC8 | `pytest -q` and `ruff check src tests` unchanged from the baseline measured 2026-09-02 — **1071 passed / 101 skipped** in a worktree, ruff clean. (A worktree collects **2 fewer** tests than the `fsd/` checkout: `benchmarks/datacube_throughput_report_{cog,jp2}.md` are gitignored, and `test_docs.py` parametrizes over them. Compare like with like.) | run both |

**The gate no test can be:** reader A. Spec 41 D13's honesty applies — the four assertions catch
drift, never unreadability. The user reads it and says whether it is worth the 25 minutes.

---

## 5. Risks

| Risk | Mitigation |
|---|---|
| It becomes a prettier changelog | D1's test applied per paragraph; AC2 makes a fork-free era a defect |
| It duplicates `ARCHITECTURE.md` / the ADRs | D8 + AC6: link, never restate. `ARCHITECTURE.md` says what *is*; this says how it got that way |
| The writer trusts the archive's name and misses eras 7–8 | D7, with the zero-hit measurement in it |
| A live identifier reaches a public file | D10 + AC4 — the failure mode with four prior instances |
| Scope drifts into the front door | §2 + D9(a): it is a separate issue before this one starts |
| It is written, then never appended to | D3 makes appending cheap (a new section); D4 means the current file is never *wrong*, only incomplete |

---

## 6. Alternatives considered

**Generate it from `git log`.** 382 commits, one author. Rejected: Keep a Changelog's objection
(*"full of noise"*), and the causation this document exists to record lives in the PROGRESS
entries, not in commit subjects.

**Fold it into `ARCHITECTURE.md` as a "History" section.** Rejected: different Diátaxis mode
(explanation vs reference/codemap), different document class (append-only vs continuously-true),
and it would push `ARCHITECTURE.md` past the length at which matklad's codemap argument holds.

**Split it per era into `docs/history/`.** Rejected on the same reasoning as spec 41 D12's
one-file archive: nobody browses a history by file, and a directory invents boundaries that the
era headings already carry better.

**Write it with subagents, one per era, merged.** Rejected: the synthesis *is* the deliverable, and
parallel cold summarisation reproduces the accretion #55 was filed to undo.

---

## 7. Questions at sign-off — ALL RESOLVED (user, 2026-09-02)

1. **The era list (D6)** — eight, and their boundaries. **Confirmed as written** ("eras look
   right"). D6 stands, including its ±1 allowance and the era-5/era-6 calendar overlap.
2. **D9's ADR 0027** — a new ADR to record the append-only class, versus amending spec 41.
   **Resolved as proposed: the ADR.** D3 forbids editing a point-in-time document, and spec 41 is
   one.
3. **D9's two issues** — **resolved as proposed: file both** (the front-door pass, and
   `PROGRESS.md`'s regrowth past D12's target).
4. **AC7's endpoint wording** — **resolved as proposed:** the story ends at *the consumer-repo run,
   2026-09-02*.

---

## 8. Best-practice alignment / sources

Per-source credit — what each source specifically contributed.

**Diátaxis — Daniele Procida** ([explanation](https://diataxis.fr/explanation/)). Contributed
**D1 in full**, and thereby the test for what belongs in the file. Verbatim: explanation is
*"understanding-oriented"*; its *"perspective… is higher and wider than that of the other three
types"*; *"provide background and context in your explanation: explain why things are so — design
decisions, historical reasons, technical constraints"*; and *"explanation can and must consider
alternatives, counter-examples or multiple different approaches to the same question"* — which is
the direct authority for **D2's fork-shaped spine and AC2's rule that a fork-free era is
unfinished**. Its listing of *"the bigger picture"*, *"history"*, *"choices, alternatives,
possibilities"* as explanation's proper subjects is why this file, and not `ARCHITECTURE.md`, is
where they go. Spec 41 adopted Diátaxis and built three of its four modes; this closes the fourth.

**"Documenting Architecture Decisions" — Michael Nygard, 2011**
([cognitect.com](https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions)).
Contributed the **precise boundary between `docs/adr/` and this file** (D8, §1(1)). An ADR's
Decision is *"stated in active voice: 'We will…'"* — a record of a fork **taken**, which is
structurally why a fork **declined** has no ADR and needs somewhere else to live. Also supplied the
motivation §1 leans on: *"one of the hardest things to track during the life of a project is the
motivation behind certain decisions"*, and the failure mode of losing it — teams *"afraid to change
anything"* or changing it without understanding the consequences. His *"if a decision is reversed,
we will keep the old one around, but mark it as superseded"* is the same instinct D3 applies at
section granularity.

**Keep a Changelog 1.1.0** ([keepachangelog.com](https://keepachangelog.com/en/1.1.0/)).
Contributed **D7's exclusion of `git log`** and §6's first rejected alternative, verbatim:
*"changelogs are for humans, not machines"*, and *"using commit log diffs as changelogs is a bad
idea: they're full of noise — things like merge commits, commits with obscure titles, documentation
changes"*. Its distinction — commits document *source-code evolution*, entries communicate
*noteworthy differences across multiple commits* — is also the line between `CHANGES.md` and this
document.

**PEP 1** ([peps.python.org/pep-0001](https://peps.python.org/pep-0001/)), via spec 41 D3.
Contributed the rule **D3 extends**: documents are *"no longer substantially modified after they
have reached the Accepted, Final, Rejected or Superseded state"*, and a resolved one is *"a
historical document rather than a living specification"*. D3's only move is to apply it to a
**section** rather than a file, which is what "append-only" means.

**"ARCHITECTURE.md" — Aleksey Kladov (matklad), 2021**
([post](https://matklad.github.io/2021/02/06/ARCHITECTURE.md.html)), via spec 41 D9. Contributed
**the boundary §6 uses to refuse folding this into `ARCHITECTURE.md`**: that file is a coarse
codemap, *"a map of a country, not an atlas of maps of its states"*, and its value depends on
staying short enough to read in one sitting.

---

## 9. Implementation note — build order

**Opus, one session, `/effort high`** (spec 41 P8's own sizing). Not Sonnet: this is synthesis
judgement over ~90k words of primary source, which is the opposite of the spec-following work the
Sonnet lane exists for. **No subagents** (§6).

1. Read `docs/progress-archive.md` end to end, then `PROGRESS.md` 08-20 → 09-02, then `CHANGES.md`.
   Take notes as a **fork ledger**: date · question · taken · dropped · measurement · source.
2. Confirm the era boundaries against the ledger. Report any D6 boundary the evidence contradicts
   **before** writing prose; a boundary that has to be argued for is a boundary that is wrong.
3. Fill gaps era by era from `docs/adr/`, `docs/findings/`, `spike/`, `ROADMAP.md`.
4. Write the eight sections. One era per pass, in order — an era's meaning depends on the one before.
5. Opening (~400 words: what fsd is, for whom, and why the story is worth 25 minutes) and closing
   (~300: where it stood on 2026-09-02, and the named-but-unwalked paths).
6. Run AC1/AC3/AC4/AC8; then Opus review against AC2/AC5/AC6/AC7.
7. `docs/adr/0027-history-is-append-only.md` + the `README.md` pointer (D9).
8. File D9's two issues. Close #55.
