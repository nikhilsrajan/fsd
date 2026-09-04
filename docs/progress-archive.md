---
status: historical
summary: PROGRESS entries older than the current one, moved here verbatim — first on 2026-07-30 (spec 41 D12, 61 entries), again on 2026-09-03 (#94, covering 2026-09-03 back to 2026-08-20).
ordering: NOT chronological end to end. The 2026-07-30 bulk is newest-first; a tail appended after it runs 08-20, 08-19, 07-31, 07-30 out of order; the 2026-09-03 block is newest-first again. Search this file, do not scroll it.
headings: two forms — `## 2026-...` and `## <emoji> 2026-...` (✅ 🟡 ⭐). A bare `grep '^## 2026'` finds only some of them and will mis-split the file.
coverage: complete through 2026-09-03 — but it was NOT before then. Until the #94 append, specs 48-53 and the whole notebook-usability sprint (2026-08-20 to 09-03) appeared zero times here, so this file was not the complete archaeology source its first summary claimed. docs/history.md is the narrative view; this is the raw log.
---

## ✅ 2026-07-30 — P4 DONE: `env.example.sh` + `docs/reference/environment.md`, both under test. Found a real leak. → NEXT: P5

Spec 41 ranked P4 highest of what remained because it is **the only phase backed by runs that
actually failed**. The measured drift: **50 distinct `AZ_*` variables** (spec 41 said ~45) across
the run-books with no canonical list.

**Counted, not estimated — and one assumption in D6 was wrong:** `grep` says **no `AZ_*` variable
is read by `src/fsd/` at all.** D6 assertion 1 is worded *"every `AZ_*` in `env.example.sh` appears
in `src/` or `runbooks/`"*, which assumes the library reads them. It does not: every one is
operator-facing (run-book shell, `az` CLI, or `demos/e2e_austria_aml.py`), and fsd's own code takes
storage locations as **arguments**. The one `_AZ_RE` in `src/fsd/storage/azure.py:29` is a compiled
regex, not a variable. The parity test therefore scans `runbooks/` + `demos/` + `docs/`.

**Three deliverables:**

| file | what it is |
|---|---|
| `env.example.sh` (repo root) | all 50 variables in 9 groups, values blank or derived, comments pointing at the private doc. `cp` → `env.local.sh` → fill → `source`. A missing value is now **one visible blank line**, not an absent export five run-books deep. |
| `docs/reference/environment.md` | the canonical table: meaning · **where the value comes from** · **a verification command per row**. Continuously-true (D3), so no D4 header. |
| `AZURE_INFRA_PRIVATE.md` (workspace root) | a new section mirroring `env.example.sh` group for group, so the three read side by side. **No value was copied into `fsd/`.** |

**Parity is exact: 50 declared, 50 used, zero drift in either direction** — and `tests/test_docs.py`
now enforces it (D6 assertion 1, two new tests: parity, and every variable documented in the
reference). **The test caught its first defect immediately** — my own reference prose wrote `AZ_RE`
where the identifier is `_AZ_RE`; the doc was fixed, not the test.

**The four spellings are documented, NOT unified.** `AZ_ARCHIVE` / `_ROOT` / `_PATH` / `_CATALOG`
(+ `AZ_CATALOG`, `AZ_CATALOG_URL`) all point into the same place. Renaming them would mean editing
run-books, which D3 forbids — the same rule that forced the issue numbers to align rather than
rewriting 473 references. So the reference gives the equivalence table and says **set whichever the
run-book you are running names**; `AZ_ARCHIVE_ROOT` is marked canonical.

### ⚠️ The identifier sweep found a real leak (pre-existing, now scrubbed)

`RECIPES.md`'s pre-push sweep, run before committing, found **the concrete d16 cluster
name in two tracked, public files**: a comment in `src/fsd/workflows/runners.py:248` and
a docstring in `demos/plot_aml_timings.py:148`. Both were prose, so scrubbing to
`cluster-<proj>-d16` + a pointer is behaviour-free. **Neither came from this session's work.**

This is the **third** time the sweep has caught this class (two on 2026-07-22), and all three
arrived the same way: **prose written about a real run.** `RECIPES.md` now says to run the sweep
after any such session, and records the new known-clean false positives.

**It does not close the standing open decision** (private doc, unmade since 2026-07-17): scrubbing
is *forward-only*, and these identifiers are already in the public repo's **git history**.

**`.gitignore` gained `env.local.sh`** — it did not have it, and that file is designed to hold real
account names, ids and URLs.

**Gate:** `pytest -q` **608 passed / 84 skipped** (+2, the parity tests), `ruff check src/ tests/
demos/` clean, identifier sweep clean apart from documented false positives.

# PROGRESS archive

> **Moved, not deleted** (spec 41 D12, 2026-07-30). `PROGRESS.md` was 3,691 lines of resume
> anchor **and** historical log fused into one document — read at the start of every session,
> so the cost was paid every time. The anchor stayed in `PROGRESS.md`; all **61** entries before the
> current one are below, **verbatim and in the same order** — with exactly one deliberate exception:
> the move **scrubbed a concrete cluster identifier** out of one line (the pre-push sweep caught it;
> it is described there now, not spelled). No other byte was changed.
>
> **One file on purpose** (user, 2026-07-29): it is a log, nobody browses it, and splitting it
> by month would invent a boundary that means nothing. It is **point-in-time** (D3) — entries
> are never edited after the fact, including the ones that record a conclusion later proven
> wrong. Those corrections are the most valuable thing in here and are why this file exists
> rather than `git log -p`: it is the archaeology source for **spec 43** (`docs/history.md`),
> which has not been written yet.

---

## ✅ 2026-07-30 — P3 DONE: `docs/findings/` — two research write-ups out of the issue bodies. → NEXT: P4 (env reference)

Spec 41 D14 P3: *extract TODO #59/#61 + `E2E_AUSTRIA_AML.md` §6 → `docs/findings/`*. The two rows
that were **1,137 and 792 words of research living in a markdown table cell** are now readable
documents.

| new file | from | says |
|---|---|---|
| `docs/findings/cloud-overhead.md` | issue #61 + `E2E_AUSTRIA_AML.md` §6.1 | **35 % of the inference run and 90 % of the merge run was the DRIVER** collecting over blob, not the cluster. Attack the driver, not the cluster. |
| `docs/findings/workload-regimes.md` | issue #59 + §6.2 | Training units are **781× smaller** than inference units, so one set of fan-out defaults cannot serve both. |
| `docs/findings/README.md` | new | the index + what a "finding" is and how it is superseded |

**The split that makes this worth doing (D9):** the **finding holds the measurement** — the
decomposed windows, the method, the caveats, and the readings that turned out wrong. The **issue
holds the open work**. Both findings carry a D4 `status: current` header; findings are
**point-in-time** (D3 explicitly lists `docs/findings/`), so a later measurement gets a *new*
finding and this one is marked superseded — the numbers are never edited.

**What each finding preserves that a summary would have thrown away:** three corrections in
`cloud-overhead.md` (the "fixed cluster spin-up" reading, the "627 s bundle upload" suspect — the
bundle stage was **13 s** — and "ramp-up grows with fan-out width"), and one in
`workload-regimes.md` (the same width claim, from the other direction). Each was plausible and each
was wrong; that is the reusable part.

**`tests/test_docs.py` widened** — `_D4_DIRS` now covers `specs/`, `runbooks/`, `demos/`,
`benchmarks/` **and** `docs/findings/` (84 target files, up from 72). This closes the open review
finding that P1 stamped `demos/` + `benchmarks/` while D6 assertion 4's literal wording only tested
`specs/`+`runbooks/`, so 11 stamped files could rot untested. The new folder is covered from birth.

**`demos/E2E_AUSTRIA_AML.md` §6.1/§6.2 got a one-line pointer each, and nothing else** — it is
point-in-time (D3), so it is not gutted to chase a later extraction. Both homes are frozen, so they
cannot diverge. `TODO.md`'s stub now points at `docs/findings/` as D8 requires.

**Handed to the user (networked, spec 24):** `gh issue comment` on #59 and #61 pointing at their
findings — bodies prepared at the workspace root.

**Gate:** `pytest -q` **606 passed / 84 skipped** (from 595/73 — the widened glob adds 12 files ×
2 tests, of which 11 land as skips since only 2 files are superseded), `ruff check src/ tests/
demos/` clean.

**Two review findings still open** (P4/P5): `superseded_by` is ambiguous across the
`specs/`↔`runbooks/` namespaces (`runbooks/42`'s `41` resolves to `specs/41`), and the two register
indexes disagree on link style.

## ✅ 2026-07-30 — P2 DONE: `TODO.md` → 62 number-aligned GitHub issues. → NEXT: P3 (`docs/findings/`)

**The user ran `runbooks/44-todo-to-issues.md`. It passed exactly.**

```json
{"step":"todo-to-issues","status":"ok","pass":true,
 "metrics":{"created":62,"closed":24,"first":1,"last":62},
 "expected":{"created":62,"closed":24,"first":1,"last":62},"error":null}
```

**Alignment verified independently** (not from the script's own report):
`gh issue list --state all` → **62 issues, min 1, max 62, 24 closed**, and the sorted number set
equals `[1..62]` exactly — no gaps, no drift. **`gh issue view 47` is now the canonical way to read
what used to be TODO #47.**

**Reference check:** **473 `TODO #NN` references across 61 markdown files**, and the **highest is
#62** — every existing reference falls inside the aligned range, so all of them resolve. (The 448
count in spec 41 D8 was measured earlier and before specs 41/42 + the P1/P2 entries added their
own.) Nothing was rewritten to achieve this, which is exactly what D3 forbids and what the
number-alignment decision bought.

### What moved where (the prose problem D8 did not anticipate)

`TODO.md`'s first 76 lines were **not rows** — they were narrative that a "~10-line stub" would
have silently deleted, and it existed nowhere else in the repo (grep-verified against `ROADMAP.md`,
`CHANGES.md`, `CONTEXT.md`). **The user chose to split it by subject** rather than keep it in the
stub or fuse it into one new issue:

| Content | New home | Why |
|---|---|---|
| "Post-v1 roadmap (sequencing — user, 2026-07-02)" | **`ROADMAP.md` §5.9**, verbatim, marked point-in-time | Roadmap sequencing belongs with the phase table; §5's table is the live plan, this records *why* the order was chosen |
| "Cross-cutting perf track" — the 3-part benchmark-first plan + the five parked optimization candidates (2026-07-04) | **A comment on issue #15** | Issue #15 **is** that item — one fact, one home (D9) |

**`TODO.md` is now a ~15-line signpost**, not deleted: 473 references name it. **`CLAUDE.md`
edited** (workspace root, outside the repo): the living-registers line no longer lists `TODO.md`
and says explicitly *never add a row to it*; the stale "(TODO #30/#10 open)" note in the archive
warning is corrected — spec 34 closed both, but that archive predates the fix and was never
re-ingested, so the ~1000 DN warning still stands for a different reason than it claimed.

**Still open from P2:** the new P5 STACNotator north-star issue (the user's call on #26,
2026-07-30) — it lands at #63+, outside the aligned range, and is a `gh` create, so it goes to the
user with the command.

**Gate:** `pytest -q` **595 passed / 73 skipped**, `ruff check src/ tests/ demos/` clean.

## 🟡 2026-07-30 — P2: the 62-issue manifest is REVIEWED + SIGNED OFF; run-book 44 written. → NEXT: the user runs run-book 44

Spec 41 D8's binding conditions are met up to the point Claude is allowed to reach.

**Preflight (D8 condition 1) — verified:** `gh issue list --state all` empty, `gh pr list --state
all` empty, discussions **disabled** (`has_discussions: false`). The shared counter is at **0**, so
`#N == TODO #N` is achievable. **Re-verified by the script immediately before it creates anything**
— it exits 2 and creates nothing if any of the three is non-empty (D8's "no partial attempt").

**Manifest (D8 condition 3) — signed off by the user 2026-07-30.** Workspace root (uncommitted,
outside the public repo): `P2_ISSUE_MANIFEST.md` (human review artifact, 62 titles + states +
labels + milestones + every body) and `P2_ISSUE_MANIFEST.jsonl` (what the script reads). Bodies are
**verbatim** from `TODO.md` — verified by substring match, not by eye; longest is 7,045 chars
against GitHub's 65,536 limit.

**Three decisions the review surfaced, all user-answered 2026-07-30:**

| Question | Answer |
|---|---|
| Spec 41 D8/D13 says **"29 closed"**; reading every row gives **24** | **24 is right.** The 29 counted rows *containing* a ✅ (28 do), but 6 are open rows carrying a ✅ on a sub-part: #14 (COG+STAC done, titiler not), #25 (root cause only), #39 (ROI mode only), #48, #60 (measured, not fixed), #61 (fix (a) of (a)–(d)). Same class as spec 41's own A1 file-count correction. |
| D8's label vocabulary has **no bucket for the model items** (#18, 19, 20, 25, 28 are ModelAdapter/bundle/engine) | **Add `model`.** Final set: `datacube`, `download`, `cloud`, `storage`, `stac`, `docs`, `perf`, `model`, `blocked`. |
| **#26** (STACNotator serving contract) — closed, or kept open as the P5 north star? | **Closed** (specs 29+30 validated tier-1 and tier-2 end to end), **plus a NEW open north-star issue after the migration** — it lands at #63+, outside the aligned range, which is why it waits. |

**Milestones** are assigned sparingly — only the 6 rows that name a ROADMAP phase as their own
scope (`P1`, `P2`, `P3`, `P5`). Labels and milestones are editable after creation; **the number is
not**, so the number is the only thing the manifest had to get right.

**`runbooks/44-todo-to-issues.md` + `todo_to_issues.py` (workspace root) written.** Claude does
**not** run this — it is networked and side-effecting (spec 24), and a misnumber is unrepairable.
The script: re-runs the preflight, creates strictly sequentially with a 2 s gap (GitHub's secondary
rate limits), **verifies every create returned the expected number and halts on the first
mismatch**, then closes the 24. `--dry-run` (validated, zero side effects: "62 issues, 24 to close")
and `--resume` (continues from the highest existing issue + 1). ~4 min to create, ~1 min to close.

**Still to do after run-book 44 passes:** `TODO.md` → the ~10-line stub (not deleted — 448
references name it), the `CLAUDE.md` edit that currently calls `TODO.md` a living register, and the
new P5 north-star issue.

## ✅ 2026-07-30 — P1 REVIEWED (Opus@high) + 3 FIXES APPLIED. Batch accepted, D13 satisfied. → NEXT: P2 (issues)

Commit `f905161` reviewed against spec 41 D4/D6/D13. **The batch is NOT redone**: all 10 statuses in
an independent spot-check were correct, so D13's ">1 wrong ⇒ redo" does not trigger. Every defect
found was in the `summary:` line, not the `status:` value. Gate re-verified independently:
`pytest -q` **594 passed / 72 skipped**, `ruff check src/ tests/ demos/` clean.

**The independent 10 (D13), none of them Sonnet's own picks:** `specs/01`, `08`, `09`,
`research-s2-reprocessing-dedup`; `runbooks/38`, `39`, `40`; `demos/E2E_AUSTRIA.md`;
`benchmarks/cog_vs_jp2_report.md` + `cog_vs_jp2_storage.md`. Checked against `pyproject.toml`
(spec 09's dep list, spec 08's `snakemake` "local runner only"), `src/fsd/workflows/` (`runners.py`
+ `task.py` still exist ⇒ spec 08 `current`), `specs/33` (it does cite the research doc twice),
`TODO.md` #62 and `PROGRESS.md`'s 2026-07-29 entry.

### The three fixes applied

1. **~51 summaries were re-stating process state that D4 evicts and D9 houses elsewhere.**
   "signed off and implemented", "ran green", "done, reviewed, merged" — and three that were
   explicitly time-relative: run-book 40 *"not yet run at the time of this stamping"*, 38 *"cluster
   validation still pending"*, 39 *"a P2 re-run is pending"*. `runbooks/README.md` already carries
   all of it in a `ran?` column and `specs/README.md` in an `implemented?` column, each with
   evidence — two homes for one fact, guaranteed to diverge. **The rule now applied uniformly: the
   summary says what the document IS; the index says how far it got.**
   **Deliberate exception on 4 files** (`specs/25b`, `26`, `39`, `40`): their own *body* still says
   "awaiting implementation"/"DRAFT", so each keeps a short parenthetical saying so. That is a fact
   about the document's text, not about project progress, and deleting it re-opens the exact defect
   P1 was written to correct.
2. **`demos/E2E_AUSTRIA.md` was `current` with no staleness disclosure** — while its own §8 (line
   271) carries a ⚠️ STALE note and TODO #62 exists to re-run it. Left `current` (the same
   partial-supersession rule that correctly kept `specs/18` current), but the summary now states it,
   the way spec 18's summary already stated its own. A reader deciding whether to open the file
   needs to know two of its published numbers are wrong.
3. **The file counts in this log were wrong three different ways** — see the corrected P1 entry
   below. Notable because spec 41's amendment A1 was *itself* a file-count correction.

### Confirmed, no change needed (the handoff's four open judgment calls)

- **`specs/18` `current` vs `specs/19` `superseded-by-23`** — both right. 18's ModelAdapter contract
  stands and only the `cores>1` detail moved; 19's whole subject moved.
- **`specs/27` `historical`, not `superseded-by-NN`** — right. `superseded_by` takes a *document*
  number and the replacement is a decision recorded in TODO #26–#29, so there is no target;
  "its subject no longer exists" is exactly true of a dashboard that will never be built.
- **The `satellite_benchmark` grep as the signal for `historical`** — verified sound: 6 reports
  reference it and all 6 are `historical`; the 2 that do not are `current`. One wrinkle worth
  knowing: `cog_vs_jp2_storage.json` *does* reference the deleted archive, so that measurement was
  taken on it — still defensible as `current`, since a COG-vs-JP2 format result is not
  archive-specific.
- **The hand-rolled header parser over `pyyaml`** — keep it, and the handoff's stated worry is moot:
  `tests/test_docs.py` never imports `yaml` at all, so there is no transitive dependency to protect.

### Three findings left OPEN (deliberately not fixed here — they are P4/P5 work)

- **`test_docs.py` does not cover `demos/` + `benchmarks/`** — 11 stamped files untested. This
  matches D6 assertion 4's literal wording ("every `specs/`+`runbooks/` file"), but the stamping
  went wider than the assertion, so those headers can rot. Extending `_d4_targets()` is 2 lines.
- **`superseded_by` is ambiguous across the two namespaces** — `runbooks/42`'s `superseded_by: 41`
  resolves to **`specs/41-docs-refactor.md`**, because `test_docs.py` searches `specs/` first. The
  test passes on the wrong file; the intended target is `runbooks/41-recover-aml-job-timings.md`.
  Fix by qualifying the value (`runbooks/41`) or searching the file's own directory first.
- **The two regenerated indexes are inconsistent** — `specs/README.md` uses markdown links,
  `runbooks/README.md` uses bare backticked filenames, so D6 assertion 2 ("links resolve", P5) will
  never check the run-book index.

## ✅ 2026-07-30 — P1 DONE: D4 status headers on 81 files + regenerated indexes + test_docs.py. → NEXT: P2 (issues)

**Every point-in-time doc got a `status`/`summary` D4 header (ADR 0023).** **81 files in commit
`f905161`** (⚠️ count corrected by the Opus review — the entry first said 79 and the commit message
said 83): 46 `specs/*.md`, 26 `runbooks/*.md` (22 run-books + 3 `HANDOFF-*.md` (`historical`) +
`TEMPLATE.md`, whose header is baked into the skeleton as a placeholder and is not itself a status;
run-book 43 was already stamped in `8437175`), 3 `demos/*.md`, and 6 `benchmarks/*.md`. **Two
further benchmarks reports were stamped on disk but are NOT in the repo** —
`datacube_throughput_report_{cog,jp2}.md` are gitignored (`.gitignore:49`), so those two edits are
local-only; they are left in place (harmless) but they are not part of P1's deliverable. Every
status was **re-derived from evidence** (`CHANGES.md`, ADRs, test files),
not lifted from the ~12 existing ad-hoc status-line formats — confirming the three known-wrong ones
(specs 39/40 said DRAFT, 25b/26 said "awaiting implementation"; all four are actually implemented
and now `current`). 6 benchmarks reports referencing the deleted `satellite_benchmark/` archive are
`historical`; spec 27 (Leaflet dashboard) and run-book 42 (superseded cold-reruns) are the other two
non-`current` cases.

**`specs/README.md` and `runbooks/README.md` regenerated** with the implementation-status column
D4 deliberately excludes (evidence: an ADR, a test file, or "not implemented"). `runbooks/README.md`
keeps its Track A–D structure and Conventions block, adding a small timing-recovery mini-table for
41/42 and a `status: historical` note for the HANDOFF files.

**`tests/test_docs.py` written (spec 41 D6 assertion 4 only):** every `specs/`+`runbooks/` file
parses as a valid D4 header, every `superseded_by` names a file that exists. Hand-rolled parser, no
new dependency (`pyyaml` is only a transitive dep in `.venv`, not declared in `pyproject.toml`).
74 new parametrized tests, all green.

**Spec 41 amendment A1 added** (user confirmed before writing): its "42 specs" file count was wrong
throughout — measured **46** specs (44 pre-existing + 41/42 same-session) — recorded as a dated
amendment in §1, per ADR 0022 (specs are never silently edited). `runbooks/` count of 23 was
already correct.

**Gate (D13):** `pytest -q` → **594 passed / 72 skipped** (up from 520/2 baseline — the +74 are the
new doc tests); `ruff check src/ tests/ demos/` clean. **D13's spot-check is satisfied by the Opus
review entry above** — an independent 10 files, none of them the 10 Sonnet self-checked.

**Committed as `f905161`** on `main` in the shared checkout (this session worked directly there,
not a worktree, since the job started there). **Unpushed** — push is the user's call.

**Still deferred, unchanged:** P2 (issues migration), P3 (`docs/findings/`), P4 (env reference), P5
(README/ARCHITECTURE/PROGRESS split), P6/spec 42 (the fixture build — its 3 scripts still
unwritten), P7 (tutorial + how-tos), spec 43, spec 40 §7, TODO #62, TODO #59/#60/#61, the rslearn
Plan B/C decision.

## ✅ 2026-07-30 — SPECS 41 + 42 SIGNED OFF (docs refactor designed, nothing implemented). → NEXT: P1

TODO #55 is now **two signed-off specs plus five ADRs**, produced by an Opus@high
`/grill-with-docs` interview (12 questions, 2026-07-29/30). **No implementation has started** —
only markdown was written, the suite is untouched.

- **`specs/41-docs-refactor.md`** — D0–D14, the target layout, phases P1–P5 + P7, acceptance
  gates, per-source credit. **Signed off.**
- **`specs/42-tutorial-fixture.md`** — the committed offline tutorial fixture, carved out because
  it is data engineering. **Signed off, then amended A1 the same day** (see below).
- **ADRs 0022–0026** + `CONTEXT.md`'s new "Documentation kinds" section. `docs/adr/README.md` also
  gained the row for **0021, which had never been indexed**.
- **Spec 43 (`docs/history.md`) is deliberately deferred** until P1/P2 have done its archaeology.

### The reframe: TODO #55's C4 plan was replaced (D0)

#55 asked for "≤~5 docs on the C4 model". **C4 is demoted to the section outline of one
`ARCHITECTURE.md`** (Context/Container/Deployment as Mermaid), not a file count. Reasons: C4 models
*a system you deploy*, fsd is a library + a pipeline; and C4's "container" means a runnable thing —
its own docs open **"Not Docker!"** — so fsd's C4 containers are **driver / node / blob / catalog**,
emphatically *not* the AML Docker Environments. **Diátaxis** (tutorial · how-to · reference ·
explanation) replaced it as the organising frame, and **matklad's ARCHITECTURE.md** convention
supplied the one-file codemap. The user's actual complaints were never architectural: *runbooks are
unreadable, specs no one would read, the TODO is too hard to find what's missing.*

### The diagnosis: three documents are each TWO documents fused (ADR 0022)

Not neglect — a **missing category system**. A spec records what was decided *then*; nothing was
ever supposed to keep it true. So: **every document is either point-in-time (never edited after the
fact, statused) or continuously-true (maintained, and tested where possible)** — PEP 1's rule
adopted wholesale (*"PEPs are no longer substantially modified after they have reached the
Accepted, Final, Rejected or Superseded state"*). The fused three: `PROGRESS.md` (anchor + 38.7k-word
log), `demos/E2E_AUSTRIA.md` (tutorial + benchmark report — which is *why* its §2 still says "CDSE
now; MPC later"), `TODO.md` (open + closed + measurement essays).

**That rule then forbids the obvious shortcuts:** we do **not** edit point-in-time docs to chase a
later decision — which is why issue numbers are forced to align rather than rewriting 448
references, and why **`demos/` is NOT renamed** to `benchmarks/` despite being misnamed.

### What the grilling measured that changed a decision

| Measurement | Consequence |
|---|---|
| **448 `TODO #NN` refs** across 30+ files; TODO numbered **1–62, zero gaps**; repo has never had an issue, PR **or discussion** (GitHub shares one counter across all three) | Create 62 issues **strictly in order, including the 29 closed ones** ⇒ #N == TODO #N, all 448 refs resolve free (ADR 0024) |
| **21 of 42 specs already carry a status line** in ~12 formats; **≥3 are wrong** (spec 39 says DRAFT although it shipped; 25b/26 say "awaiting implementation") | We are *normalizing* a half-existing convention; existing labels **cannot be lifted** |
| **`e2e_austria.py`: 12 of 531 lines touch `fsd`** (2.3%), and `step_download` **bypasses `fsd.download`** for `cdse.probe_throughput`/`download_resume` | `demos/` provably cannot serve as an example — the demo gap is **three artifacts** (ADR 0026) |
| **~426 MB per granule** (B04 183.8 + B08 187.1 + B8A 51.0 + SCL 4.6); whole-granule reads ⇒ a 5 km ROI saves nothing (1 tile-month ≈ 3.4 GB) | **No real download is tutorial-sized** ⇒ committed fixture |
| **fsd ships ZERO data** — `.gitignore` blocks `*.tif`/`*.geojson`/`*.parquet`, and `shapefiles/` is outside the repo | A "cannot fail" tutorial was impossible before spec 42 |
| **No CI exists** (`.github/workflows` absent) | Doc tests land in **`pytest`** — stricter, since it runs every session. **Docs can fail the suite.** |
| **~45 `AZ_*` variables**, incl. four spellings of one idea (`AZ_ARCHIVE`/`_ROOT`/`_PATH`/`_CATALOG`) | `env.example.sh` + `docs/reference/environment.md`; `AZURE_INFRA_PRIVATE.md` restructured to mirror it line for line |

### ⚠️ The user's chosen tutorial ROI was checked and rejected

`s2grid=476da24` sits near **Vienna** (16.03–16.12 E) while every labelled field is ~100 km **west**
(14.6–15.5 E) — it contains **zero labels** and cannot exercise the training-data step. Replaced by
**cell `4772924`**, chosen by measurement: most labelled fields of the 300 cells over `AT_ROI`
(**43 fields, 7 crops**, collapsed to maize/hemp/other for trainability), and **all 24 of its
granules are single-tile `T33UWP`** — so it also strictly dominates `476da24` as a test ROI.

### Spec 42 amendment A1 (user, 2026-07-30) — the VM build removes the radiometry hazard

The user wants the fixture built **on an Azure VM** to spare a mobile hotspot. That turned out to do
much more than save bytes:

| Source | Example id | Radiometry columns |
|---|---|---|
| local `demo_e2e` (CDSE-era) | `…_**N0500**_R122_T33UWP_…` | **none** |
| blob archive (MPC-era, runbook 37) | `…_R122_T33UVP_…` — **no N-token** | **`offset`, `nodata`** |
| `mpc_baseline` | `…_R122_T33UWP_…` | **`boa_add_offset`** |

The blob archive is **MPC-sourced and self-declaring**, so the fixture inherits correct radiometry
**by provenance** instead of re-deriving −1000 from a baseline token. Three consequences: the token
re-derivation is not merely unnecessary but **impossible** (MPC ids carry no `_N####_`), so
acceptance test 2 was rewritten; the declaration column name **differs across catalogs**
(`offset` vs `boa_add_offset`) so it must be read through the declaration API, never hardcoded — a
schema drift worth its own issue; and the granule count **may not be 24**, since MPC applies
different cloud-cover filtering and dedup (spec 33), so `T` follows from the archive rather than
being fixed at 9. A1 deliberately does **not** claim VM≡local is proven: that is the storage seam's
promise (ADR 0003 / spec 31), not yet a measurement, so the local build is retained as the
comparison fallback and a byte difference is a **seam finding**, not a fixture bug.

### → NEXT: P1 (status headers), then P2 (issues)

**P1** — three-value headers (`current` / `superseded-by-NN` / `historical`) + a `summary:` line on
42 specs + 23 runbooks, and regenerate both indexes. Sonnet@medium against spec 41 D4. Process
state (`implemented`) deliberately lives in the **regenerated index**, not the header. **Gate: the
user picks 10 files to spot-check; more than one error ⇒ the batch is redone, not patched.**

**P2** — the issue migration, gated on a manifest the user reads *before* any issue is created
(issues cannot be cleanly deleted). Pre-flight all three counters or fall back to a mapping table.

**✅ `runbooks/43-build-tutorial-fixture.md` is written** (commit `8437175`). It splits across two
machines by what each can reach: **step 0 on the laptop** derives `roi.geojson` + `fields.geojson`
because `shapefiles/` lives at the **workspace root, outside the repo** — a `git clone` on a VM
cannot supply `AT_ROI`, and cell `4772924` is only reproducible as `roi_to_s2_grids(AT_ROI, 5)`
(the trap that bit run-book 34); **steps 1–5 on a VM in the `rise` VNet** clip pixels against the
blob MPC archive per A1; **steps 6–7 on the laptop** verify with **VPN and wifi off**, then commit.
Only ~20 MB crosses the wire. It carries the **first spec-41 D4 status header** in the repo, so P1
has a reference format. **One elaboration on spec 42 D4, flagged not smuggled:** the split needs
**two** scripts, so step 0 specifies `derive_roi_and_labels.py` beside `build_fixture.py`; the CLI
contract is fixed in the run-book and marked **normative** so script and run-book cannot drift.

**Still to implement before run-book 43 is runnable:** `tests/data/tutorial/derive_roi_and_labels.py`,
`tests/data/tutorial/build_fixture.py`, and `tests/test_tutorial_fixture.py` (spec 42 §3–4).

**Commits this session (both pushed except the last):** `b1d9781` specs 41+42 + ADRs 0022–0026
(**pushed**), `8437175` run-book 43 (**local only — not pushed**).

**Still deferred, unchanged:** spec 40 §7, TODO #62, TODO #59/#60/#61, the rslearn Plan B/C
decision. The docs work is independent of all of them.

## ⭐ 2026-07-29 — THE DEMO RAN. P3 AND P4 ARE VALIDATED. → NEXT: TODO #55 (docs refactor)

`demos/e2e_austria_aml.py` completed unattended on the `rise` AML cluster:
**run `20260729T132222Z`, 1127.7 s (~18.8 min), 8/8 steps ok, 97 jobs, 213 MPC granules,
300 grid cells → 300 output COGs + STAC + merged map.** `timings.json` +
`timings.rederived.json` (see A3) are in `tests/outputs/demo_e2e_aml/20260729T132222Z/`
(gitignored). All three D12 figures render.

**The milestone is not the demo script — it is that ROADMAP's P3 and P4 both said
"pending cluster validation" and this run IS that validation.** Mode B (laptop triggers
cloud download→build→flatten, arrays come home) and Mode C (ROI inference fanned out over
the cluster) are now proven end-to-end on real infrastructure, in one command.

### What the run measured

| | |
|---|---|
| **Job admission = 36 % of the whole run** | 403 s of 1128 s, almost all of it one cold start |
| `2_download` | **286 s admission vs 84 s execution** — 71 % of the step is the cluster scaling 0→32 nodes |
| warm dispatches | 26–55 s admission (build 32.3 s, flatten 29.0 s, inference 55.2 s) |
| node utilisation | **5 %** (download, cold) · **42 %** (build) · **37 %** (inference) — TODO #60/#61 quantified |
| **TODO #60 reproduces exactly** | 32 shards ÷ 4 bands, `32 % 4 == 0` ⇒ one band per shard ⇒ **16.4× imbalance** (2.0 s … 32.8 s) |
| clock skew (VM) | **−0.88 s ± 0.03** vs ~8 s on the laptop — D10's driver-location record earning its keep |
| inference vs local | 367.7 s vs 2683.5 s, but the local side is 2026-07-13 code — **not a clean comparison** (TODO #62) |

### Spec 40 amendments (all recorded IN the spec, all user-decided)

- **A1 — `2_download` sources from MPC, not CDSE.** D13 contradicted D11 in the same spec:
  CDSE dispatches exactly ONE job (spec 37 D1), so the download leg measured no scale-out
  at all. Also drops the credential dance and the 30-day quota risk. `max_tiles` 207 → 250
  (MPC found 213).
- **A2 — `aggregate="median_per_id"` on BOTH demos.** The modelling unit, not a size trick:
  labels are field-level, so per-pixel training leaks a field's own pixels across the split.
  `demos/e2e_austria.py` changed to match ⇒ **its published step-3/4 numbers are now stale**
  and TODO #62's local re-run is a **prerequisite**, not a nicety (spec 40 §9).
- **A3 — `first_admission` anchors on the FIRST submission.** The old anchor produced
  `first_admission = −5.0` on a healthy dispatch: submitting 32 jobs takes ~40 s and the
  early ones are admitted *during* it, so submission and admission overlap and cannot be
  adjacent legs. It also destroyed D11's stated meaning for a negative (clock skew). New
  `submission_span_seconds` reports the span *outside* the additive split. `CHANGES.md`
  entry; **pre-2026-07-29 `timings.json` are not comparable on those two fields** (sums are).

### Defects found by running it (none by review — all cost or nearly cost a run)

1. **TODO #47 CLOSED** — `gpd.read_file(<abfss url>)` reports "No such file or directory"
   for a file that exists (GDAL has no `abfss://` driver). Killed `3_training_data`. New
   **`fs.read_geo`**, the one shared reader; all four sites use it. `run_inference`'s ROI
   re-tiling would have hit two more sites two steps later.
2. **A stale AML image silently voids the run.** The four D2 stamps are written by the `fsd`
   *inside the image*; `fsd-aml-env:4` predated spec 40, so a complete 25-min run came back
   with `job_admission_seconds: null` on all 97 jobs — correct science, void measurement.
   Now gated after the FIRST dispatch (`_assert_dispatch_telemetry_complete`).
3. **`[dev,azure,aml]` is not enough** — `mpc`/`grid`/`model-example` are also required;
   died at `4_train_bundle` on `joblib`. Preflight now checks every driver-side import.
4. **`total_seconds` was the last process's wall** — a resumed run reported 640.7 s for
   1470.0 s of steps. Now the sum of the steps + `process_wall_seconds` + `resumed`.
5. **Dispatch telemetry was ordered by run_id, which is not execution order** —
   `create_training_data` mints its id before the build dispatches but uses it for the
   flatten, so `3_training_data[0]` was the *reduce* and `[1]` the *fan-out*, backwards.
   Now sorted on `wall.t_start`. This mislabelled every figure the plotter draws.
6. **The gantt was silently dropped** — `max_rows=80` vs a real 97-job run, and both skip
   causes printed "no data". Cap 120 + `gantt_skip_reason`.

Also: preflight now prints per-check timings (`check_seconds`); `fs.modified` added (the
clock-skew probe read `fs.ls`, which returns bare strings, so skew always read 0.0);
RECIPES gained the **both-Environments rebuild** recipe (the node's fsd comes from the
image — `git pull` on the driver changes nothing) with the `az` gotchas that cost a build.

**Tests 451 → 520 / 2 skipped**, ruff clean. `main` == `origin/main`.

### → NEXT: TODO #55 — the docs refactor (its gate is now met)

#55's own sequencing rule was *"do this AFTER a timed e2e demo … with stepwise time
accounting and a report"*. That gate is met. It also says **"this is a spec of its own when
taken up … discuss before starting"** — so the next session is an **Opus@high
interview + spec**, not implementation.

**The corpus, measured 2026-07-29: 201 markdown files, 284,441 words** (specs 91.8k,
runbooks 48.6k, `PROGRESS.md` **37.7k**, TODO 16.9k, CHANGES 13.0k, demos 12.6k). Target
per #55: **(1)** one chronological "story since inception" — the forks taken and dropped and
the measurements that decided them; **(2)** ≤~5 docs on the **C4 model** (c4model.com) as a
newcomer's front door. The living registers stay as the audit trail.

Open scoping questions #55 names explicitly: which registers fold in vs stay; the file
count; and whether it lives in `fsd/docs/` or replaces the top-level READMEs.

**Deferred, not forgotten:** TODO #62 (local re-run — now a prerequisite for ANY
local-vs-cluster claim, A2), spec 40 §7 (rewrite `E2E_AUSTRIA_AML.md` around this run),
TODO #59/#60/#61 (the overhead work — note admission at 403 s dwarfs #60's ~30 s, so the
honest headline lever is cluster warm-up policy, not sharding), and the rslearn Plan B/C
decision (`spike/rslearn`, still open).

## ⭐ SPEC 40 REVIEWED (Opus@high, 2026-07-28) — six defects found, all fixed

Review of `worktree-spec40-impl` against spec 40 + ADR 0021. The suite was green *before* the
review too (473/2) — **every defect below sat in `demos/e2e_austria_aml.py`, the one file spec 40
§6 exempts from unit tests.** That exemption covers the *demo run*; it had been read as covering
the script's helpers as well, and those helpers are what a real run bets 80 GB on. Now
473 → **493 passed / 2 skipped**, `ruff check src/ tests/ demos/` clean.

Two were **fatal to the very first cluster run**:

1. **Preflight could never pass.** The Environment check read `os.environ[f"{env_var}_VERSION"]`
   → `AZ_ENV_NAME_VERSION`/`AZ_INFER_ENV_NAME_VERSION`, but the documented contract (§8.2, and
   `runner_kwargs` three functions later) is `AZ_ENV_VERSION`/`AZ_INFER_ENV_VERSION`. The
   `KeyError` was swallowed by the surrounding `except Exception` and re-reported as *"Environment
   does not resolve — build it first"*, so the script died at step 0 blaming the operator's ACR
   build. Fixed by naming the pair explicitly, plus a separate "env var not set" branch (an unset
   var and an unbuilt Environment need different fixes, D4).
2. **D14 aborted on a well-formed archive — after the whole ~80 GB download had been paid for.**
   `_assert_archive_trustworthy` globbed `**/*.tif` but compared against the catalog's `files`
   column, which for CDSE declares `MTD_TL.xml` alongside the bands ⇒ permanent
   `missing={'MTD_TL.xml'}`. The same comparison was also **vacuous**: `files` holds bare
   basenames that repeat on every row (verified on the real 207-row catalog: 207 granules × 5
   assets collapse to **5 unique names**), so it could not have detected a missing granule
   either. Now keyed `<granule_id>/<filename>` (the `api._output_key` scheme-independence trick,
   two components instead of three) and the globbed extensions are derived from the catalog
   rather than hardcoded.

Four more, silent rather than fatal:

3. **Clock skew was always reported as `0.0`.** `_measure_clock_skew` did
   `isinstance(fs.ls(...)[0], dict)`, but `fs.ls` is `-> list[str]` (it passes `detail=False`), so
   the branch never fired and the fallback returned the driver's own timestamp. D11's headline
   caveat — *"every admission figure carries that bound"* — was measuring nothing. There was no
   route to a server-side mtime through `fsd.storage` at all, so this adds **`fs.modified(url)`**
   (returns `None`, not a raise, on a backend without mtimes, so "unmeasured" can't be mistaken
   for "zero"). The probe is now bracketed before/after the write and reports the midpoint plus
   its own uncertainty, instead of charging the round-trip latency to skew.
4. **`^C` skipped the clean-exit path.** Only SIGTERM was handled; SIGINT's default
   `KeyboardInterrupt` is a `BaseException`, so it slipped past both `run_step`'s
   `except Exception` and `main`'s `except DemoInterrupted` — a raw traceback and no resume hint,
   on an unattended run, at the one moment the operator needs it.
5. **`--fresh` could orphan 80 GB.** The `.last_run_id` marker was written at run-id *allocation*,
   so a run that died in preflight (i.e. always, per defect 1) overwrote the id of the run that
   actually held the data — unrecoverable, since fsd's recursive delete is broken (TODO #50). The
   marker is now claimed immediately before `2_download`, the first step that puts bytes on blob.
   The printed `az storage fs directory delete` was also wrong twice over: it targeted
   `demo_runs/<id>` instead of `<AZ_ROOT's own prefix>/demo_runs/<id>`, and quoted `"$AZ_FS"`/
   `"$AZ_ACCOUNT"`, neither of which §8.2 exports — both now resolved from `AZ_ROOT`.
6. **D14's `offset` assertion was missing** (only `nodata` was checked). Added as an *independent*
   re-derivation from the baseline token in the granule id (`_N0500_` ⇒ ≥ 04.00 ⇒ −1000), not a
   call into the module that wrote the column — a catalog checked against the function that
   produced it catches nothing. This is the archive-wide invisible failure the workspace's old
   Ethiopia COGs carry: pipeline green, every reflectance ~1000 DN high. (`scale` has no catalog
   column — it is a fixed per-band constant — so there is nothing per-granule to disagree with;
   noted in the docstring rather than faked.)

Also: preflight no longer diagnoses a wrong `AZ_CLUSTER` as a credential failure (it asked for a
cluster twice and labelled the first attempt "credential/cluster resolution failed"); the
admission strip plot uses `statistics.median` rather than `sorted(x)[n//2]`, which is the *upper*
median at the expected even n=16; and `E2E_AUSTRIA_AML.md` §8.3 no longer claims the in-flight
step's `_result.json` is written on interrupt (it isn't — only completed steps have one).

**New tests: `tests/test_e2e_aml_demo_helpers.py` (20).** They cover the two things the hand-off
flagged as never exercised — the dispatch-run discovery (`_list_run_ids`/`_new_dispatch_timings`,
now run against a real `memory://` backend, since the scheme-less-glob trap only reproduces
against a real filesystem) and the D14 assertions end-to-end on a miniature on-disk archive
(missing asset, undeclared object, contradicted offset, wrong nodata, unstamped declaration,
zero-byte asset). The well-formed-archive case is the direct regression pin for defect 2.

**Open question for the user:** D12 names four validated hexes, but D11's split has **five** legs;
the implementation used slot 5 (`#e87ba4`) of the same dataviz palette. Reasonable, and the
figures were rendered and eyeballed — but the spec's own rule is "validated — do not substitute by
eye", and the five-colour run of `validate_palette.js` is asserted in a docstring rather than
recorded anywhere. Worth a re-run when the real `timings.json` lands.

## SPEC 40 IMPLEMENTED (Sonnet@medium, 2026-07-28) — the cluster demo run as one script

All six deliverables landed against the signed-off spec (`specs/40-e2e-aml-demo-script.md`,
`docs/adr/0021`), in a worktree (`worktree-spec40-impl`), tests green (`pytest -q`: 473 passed / 2
skipped, up from 451/2 at hand-off — 22 new tests), `ruff check src/ tests/ demos/` clean.

1. **The four in-job stamps** (`process_start_at`/`work_start_at`/`work_end_at`/`ended_at`) in
   `workflows/{shard,download,infer_shard,flatten}.py`'s `_status/<k>.json`. `process_start_at` is
   captured as literally the first statement after `from __future__ import annotations` (stdlib
   `datetime` only), before `pandas`/`fsd.*` load — the four files' entrypoint-level `# noqa: E402`
   blocks are why.
2. **Dispatch telemetry**: `workflows.runners._aml_submit_and_wait` now records `submitted_at`
   per job and `returned_at` (first poll at which that job is observed terminal — poll-quantized,
   D11), and writes `<run_root>/_timing.json` via a new pure function `_derive_timing` (per-job
   `job_admission_seconds`/`import_seconds`/`dispatch_overhead_seconds` + the 5-leg additive wall
   split). Written **before** raising on a failed job (D3). No return-value change (ADR 0021 held).
3. **`demos/e2e_austria_aml.py`** — the 8-step cluster demo script, mirroring
   `demos/e2e_austria.py`'s step labels exactly (D1). `--fresh`/`--run-id` (D5, resumable, never
   deletes — prints the `az storage fs directory delete` command instead), `--dry-run`/
   `--confirm-spend` (D6), `0_preflight` covers creds/blob-rw/cluster/both-Environments/ROI+label
   files/`max_tiles`/clock skew (D4/D11), D14's archive-trust assertions folded into `2_download`,
   D13's exact download scope (207 granules, 4 bands, Apr–Sep), D8's single `merge="reproject"`
   call. **Not run by this session** (CLAUDE.md) — it goes to the operator per §8 of
   `demos/E2E_AUSTRIA_AML.md` (new section, this session).
4. **`demos/plot_aml_timings.py`** — renders off-box from `timings.json` alone: a job-admission
   strip plot, a where-the-wall-went stacked bar (D11's split, the dataviz skill's validated
   5-slot categorical order — blue/orange/aqua/yellow/magenta — direct labels gated on segment
   width so small legs don't collide), and an optional per-job gantt (dropped above 80 rows).
   Rendered against synthetic data and eyeballed (dataviz skill step 7) before shipping.
5. **Operator notes** — `demos/E2E_AUSTRIA_AML.md` §8 "Reproduce it" (prerequisites, env-var
   contract, the two commands, what to send back) + a `RECIPES.md` entry.
6. **Tests** — `tests/test_workflows_status.py` (6, the stamp round-trip across all four
   entrypoints + a failed-shard degenerate case), `tests/test_runners.py` (9: `_seconds_between`,
   the additive invariant, negative-admission-not-floored, a status-file-missing degenerate case,
   end-to-end `_aml_submit_and_wait` writing `_timing.json` incl. on failure),
   `tests/test_plot_aml_timings.py` (7: both figures + the gantt, one-job and zero-spread runs,
   the negative-leg clamp, the >80-row drop).

**Not done here (explicitly out of scope, HANDOFF/spec §"NOT in scope"):** TODO #61 (b)/(c),
TODO #59/#62, run-book 42 (superseded), rewriting `E2E_AUSTRIA_AML.md`'s existing numbers (that
happens once the operator returns a real `timings.json`, per spec §7/§8.4).

**Next:** operator runs `demos/e2e_austria_aml.py --fresh --dry-run` per §8, then the real run.
Opus review recommended before merge (deliverables 1+2 touch every dispatch's entrypoint + seam).

## 🎉 THE DEMO PIPELINE IS COMPLETE — download → build → flatten → train+bundle → inference → **merged crop map**, all GREEN on the real cluster.
**Runbook 38 Phase 3 PASSED 2026-07-28**, first attempt with the corrected ROI: `AT_ROI.geojson` →
**300 grid cells**, 16 shards, `pass: true`, `sum_shard_units == n_cells_out == 300`, `n_failed == 0`,
`n_skipped == 0`, **`bundle_loads == n_shards_reported == 16`** (D7 load-once-per-node proven on a
real fan-out). 300 `output.tif` COGs + a STAC catalog on blob under `…/fsd-p4-inference/phase3_out`.
**wall 2066.9 s** = slowest shard **982.7 s** + driver overhead **1084.3 s**.
**Phase 4 (the viewable map) PASSED too**: `merge=True` (strict single-CRS, no resampling), all 300
cells consumed, `merged.tif` = **14.1 MB** on blob (6867x6828 px, 3.3:1 COG compression), wall
**1082.1 s**. ✅ **VISUALLY VALIDATED in QGIS (user, 2026-07-28)** — the merged map looks right;
seams are clean. That is the real completion criterion, not `merged_bytes > 0` (CLAUDE.md).

### ⭐ NEXT STEP — IMPLEMENT SPEC 40 in a Sonnet session (user, 2026-07-28)
**Session A is CLOSED.** The report exists (`demos/E2E_AUSTRIA_AML.md`), the overhead is decomposed
to the second, and the free recovery is complete (run-book 41, all 4 steps). **Run-book 42 is
SUPERSEDED and will not be run** — its two numbers arrive free once spec 40's telemetry lands, so
the two cells stay honestly "not measured" until then.

**→ `specs/40-e2e-aml-demo-script.md` (grilled, 10 decisions, signed off) + `docs/adr/0021`.**
Hand-off doc: `runbooks/HANDOFF-spec40-implementation.md`. Sonnet@medium.
**TODO #61 fix (a) already landed here** (`api._existing_outputs`, one glob instead of 300
`fs.exists`); **(b) threaded metadata reads and (c) batched STAC writes are still open** and are the
bigger halves — they are listed as optional follow-ups in the hand-off, not part of spec 40.
**Parked:** TODO #62 (re-run the local demo on current code, so both sides are measured on the same
code — do it when spec 40's demo run lands), TODO #59 (cluster sizing — now waiting on #61 (b)/(c)).

### The Session-A record — two sessions, in this order (user, 2026-07-28)
**SESSION A — the local-vs-AML timing report. 📝 DRAFTED 2026-07-28 → `demos/E2E_AUSTRIA_AML.md`,
waiting on two run-books.** Every measured figure is in it; the **two unmeasured driver walls**
(run-book 36 P3 build, 37 P3 download) are marked "not measured" and close via
**`runbooks/41-recover-aml-job-timings.md`** (free, read-only, self-calibrating against 4 known
walls; also measures the archive's bytes on blob, which the AML download row needs for a MB/s) and
then **`runbooks/42-timed-cold-reruns.md`** (paid — two cold cluster replays into fresh prefixes;
the user chose to spend for real `wall_seconds`, 2026-07-28). **Findings, none of which cost a cluster run — run-book 41 Steps 1 + 1b are GREEN:**
(0) **Run-book 41 (free recovery) is COMPLETE — Steps 1, 1b, 2, 3 all run.** Everything recoverable
without spending has been recovered; only `runbooks/42-timed-cold-reruns.md` (two real
`wall_seconds`) remains.
(1) **🎯 TODO #61 — the overhead is the DRIVER'S POST-RUN COLLECT, and it is now measured exactly.**
AML stamps `StartTimeUtc`/`EndTimeUtc` on every job, and the driver stamps its own last action by
writing `_result.json`, so `post = result_mtime − last_job_end` is a **direct** measurement and the
wall closes: **rb38 P3 = 249 pre + 1089 job span + 729 post = 2066.9**; **rb38 P4 = 66 + 44 + 972 =
1082.1**. So **35 % of the inference run and 90 % of the merge run was the driver collecting results
over blob**. Step 3 then split both windows from the blobs' own `last_modified`:
**PRE** = `setup()` 22 s + **bundle stage 13 s** + dispatch 8 s + **201 s of AML
submit→first-execution** (TODO #48's cold start, pinned; and the "627 s bundle upload" suspect is
dead by direct measurement). **POST** = **collect 616 s (reads only, 2.05 s/cell)** + **STAC writes
161 s (0.53 s/item)** + merge 193 s + 2 s — summing to 972 s exactly. It scales with **output
units**, which is why rb36/rb37 (collect = 16 `_status` reads) pay **19 s** and **26 s** while
moving far more data. **Fix (a) — one listing instead of 300 `fs.exists` — is a few lines, targets
the 616 s, and comes before any cluster knob.**
(2) **Both missing walls now have tight measured LOWER BOUNDS: rb36 P3 ≥ 343 s, rb37 P3 ≥ 354 s**
(job span + the 19/26 s to the driver's own result write). Run-book 42's cold replays are therefore
**~6-minute cluster runs, not ~20 min** — much cheaper than feared.
(3) **Node cold start pinned (TODO #48): ~100–135 s on a cold node, ~14 s warm**; node stagger is
**22–48 s once the cluster is scaled out**, vs 203 s in the one run that had to grow 1→8.
(3b) **The archive is 418.0 GB** (3456 tif, 121 MB/asset; per band B04 96.9 / B08 99.3 / B03 96.4 /
B02 95.1 / B8A 29.0 / **SCL 1.21** GB — run-book 41 Step 2, the first time its bytes were ever
counted, since the MPC path reports `bytes_downloaded: 0`). Two consequences: the **AML download
ran at 171.7 MB/s per node, ≤1.18 GB/s aggregate, vs the laptop's 16.7 MB/s — ~10× per worker and
~72× on the wall**, the exact inverse of the inference result (3.7× SLOWER per worker, 1.30× on the
wall). **The cloud wins where the bottleneck is proximity to the data and loses where it is compute
per unit** (`demos/E2E_AUSTRIA_AML.md` §6.4). And the 80× byte spread across bands **confirms TODO
#60's stratification mechanism in bytes**.
⚠️ **Two intermediate readings this session got WRONG and corrected:** "overhead is roughly
per-node" (no — stagger is a *scale-up* cost) and "most of it is the 13 MB bundle upload over VPN"
(no — the whole pre-dispatch window is 249 s, which cannot contain a 627 s upload). TODO #59 now
points at #61.
(4) **TODO #60 — `shard_units`' round-robin band-stratifies a
download**: 8 shards, 120–121 assets each, 0 skipped, and per-shard seconds of
109.9/113.7/62.4/**6.8**/107.7/97.0/56.3/**7.1** — when `n_shards % len(bands) == 0` every shard
gets exactly one band (the 6.8 s ones were all SCL), wasting ~38 % of allocated node-time.
Report structure + sources: see the doc. **⚠️ The "instrumentation patch" this bullet used to call for does not exist —
corrected 2026-07-28.** Run-books 36 and 37 **already emit `wall_seconds`** (`36:295`, `37:399`; 37
also emits `slowest_shard_seconds` + `driver_overhead_seconds`). What is stale is the *stored
results*, which predate that instrumentation. And they are **not empty**: both
`tests/outputs/p2_aml_runner/phase3_result.json` and `tests/outputs/p2_download_aml/phase3_result.json`
carry **per-shard `seconds` for all 16 shards** (36: slowest **213.8** s, Σ 2851.8 s over 900 units;
37: slowest **192.1** s, Σ 2434.7 s over 3456 assets). The **only** missing quantity is the
**driver wall** for those two phases — so exactly 2 cells of the table, not 2 rows.
**Re-running Phase 3 of either measures the wrong thing** (both are resumable and their outputs
already exist on blob → you would time the skip path). Free recovery first:
`runbooks/41-recover-aml-job-timings.md` reads AML's own job history for a job-level span, and
self-calibrates against four runs whose driver wall *is* known. **Do not fabricate the missing
cells** — "not measured" is a valid entry. What IS already comparable, and is the report's
headline: local and AML both ran **`AT_ROI` → 300 cells**, so inference is apples-to-apples —
**local 2683.5 s (T=10, `INFER_CORES=2`, 8-core laptop, local COGs) vs AML 2066.9 s (T=8, `cores=1`,
16 shards, blob COGs)**. Converted to single-threaded cell-seconds that is **17.9 s/cell local vs
52.4 s/cell on AML** (1.79 vs 6.55 s per cell per timestamp) — **the cloud is ~3.7x SLOWER per unit
of work and only 1.30x faster on the wall**, because it throws 16 nodes at the problem and hands
half of that back as fixed overhead. Confounded (hardware, blob-vs-disk reads, T, cores) — say so.
Related: TODO #59 (parked) wants the same overhead decomposition.

**SESSION B — TODO #55, the docs refactor.** Explicitly sequenced *after* a timed e2e demo; that
demo now exists and Session A's report is its input. Scope per TODO #55: (1) a chronological "story
since inception", (2) ~5 docs on the **C4 model**. **This is a spec of its own — discuss before
starting**, and decide which registers fold in vs stay as the audit trail.

**Parked meanwhile:** TODO #59 (cluster sizing — has two anchors now: Phase 3's 52.5 % overhead split
and Phase 4's 1082.1 s ≈ pure fixed overhead).
4. ✅ **DONE — the viewable map** (`runbooks/38-inference-on-aml.md` Phase 4, GREEN 2026-07-28).
   Kept below because both bugs it found are worth remembering. Phase 3
   left 300 separate COGs; Phase 4 re-runs the same call with `merge=True` (all 300 cells are
   EPSG:32633, so a strict single-CRS merge is **data-faithful, no resampling** — `"reproject"` is
   only for genuinely cross-UTM ROIs). D6 resume skips every cell, so it costs one cluster spin-up
   plus a ~100 MB driver-side merge. **Writing it surfaced a real bug, now fixed:** `_merge_outputs`
   read with bare `rasterio.open` (GDAL has no `abfss://` driver) and wrote its reprojection scratch
   next to a *remote* source — the **5th** instance of the repo's "GDAL assumed to handle abfss://"
   class (after cdse `_roi_gdf`, `task.py`, spec-39 gdf staging, grids.geojson `9422a1a`). Reads now
   go through the VSI seam and scratch is local. **A SECOND remote-only bug surfaced on the first
   Phase 4 run:** `rio_open` owns a `rasterio.Env` per handle, and merge holds all 300 open at once
   — rasterio's env stack is LIFO, so closing them in creation order tore down the root env and the
   next close raised `EnvError: No GDAL environment exists`. Fixed by adding **`fsd.raster.rio_env`**
   (ONE env for N datasets; one token fetch, not 300), with the trap pinned in `test_azure_seam.py`.
   **Both merge bugs were remote-only and invisible to a fully green local suite** — `merge` had
   simply never run against blob.

### 📌 Measured wall-clocks on the cluster (the ONLY authoritative source is each `_result.json`)
Every figure below is from `tests/outputs/<run>/phase<N>_result.json`. **Quote those files, never a
prose recollection** — a stale prose copy of runbook 40 Phase 1/2 survived here for a day because the
phase was re-run (`aggregate="median_per_id"`) and only the JSON was updated (fixed 2026-07-28).

| run-book | phase | `wall_seconds` | what it covers |
|---|---|---|---|
| 39 | 1 | **405.7** | flatten reduce: 900 blob cubes → one single-node AML job → `(172781,8,3)` landed locally |
| 40 | 1 | **179.4** | features driver-side (ADR-0020) → `(900,8,2)` NDVI+SAVI, one row per field. *Features only* — 40's Phase 2 (train) and Phase 3 (bundle) are untimed |
| 38 | 3 | **2066.9** | 300-cell inference fan-out (= 982.7 slowest shard + 1084.3 driver overhead) |
| 38 | 4 | **1082.1** | merge only — no compute; effectively a direct read of the fixed overhead |

**Per-shard seconds, no driver wall** (stored before 36/37 grew their `wall_seconds` line — the
run-books emit it today, `36:295` / `37:399`):

| run-book | phase | slowest shard | Σ shard seconds | units | source |
|---|---|---|---|---|---|
| 36 | 3 | **213.8** s | 2851.8 s over 16 shards | 900 field cubes | `tests/outputs/p2_aml_runner/phase3_result.json` |
| 37 | 3 | **192.1** s | 2434.7 s over 16 shards | 3456 assets (576 granules) | `tests/outputs/p2_download_aml/phase3_result.json` |

**Two driver walls that ARE measured on the download path** (run-book 37 Phase 2, same 964 MPC
assets, two shard counts — the only measured fan-out-width sweep fsd has):
`seconds_n_shards_1` = **699.6**, `seconds_n_shards_n` = **493.9** at `n_shards=8`, speedup
**1.42×** (`tests/outputs/p2_download_aml/phase2_result.json`). 8× the nodes bought 1.42× the wall.

### 📌 What Phase 3's numbers say (first real fan-out datum)
The **sharding is fine — the overhead is the target.** 300 cells / 16 shards ≈ 18.75 cells/shard at
~52 s/cell → 975 s predicted vs 982.7 s observed slowest shard: **balanced, no straggler.** But
useful work was only 982.7 s of 2066.9 s. The 1084 s of driver overhead (preflight+tiling, setup
~24 s, bundle stage, dispatch, cluster start 40–380 s cold, then the post-run collect of 300
`output.tif` existence checks + STAC build over blob) has **never been decomposed** — that is TODO
#59's first job, and TODO #55's timed-demo report wants the same breakdown.
It also settles the training-vs-inference asymmetry empirically: inference does ~52 s of real work
per unit, so the 16-way fan-out clearly pays; **training's units are ~200 px (median 14×15, 13 KB)**
— milliseconds each — so that same ~1084 s of overhead would dwarf the entire 900-unit workload.
Cube sizes measured 2026-07-28: inference **597×554 px / 21.2 MB per cube, 5.48 GB total**
(⚠️ **the AML run's 300 cubes on blob total 4.13 GB** over 600 `.npy` — run-book 41 Step 3. Unreconciled;
likeliest cause is that 5.48 GB was measured over the **local T=10** run vs the cluster's T=8, but that is
a guess. Per-unit pixel dims, and so the 781× ratio, are unaffected); training
**14×15 px / 13 KB per cube, 0.02 GB total** (781× more pixels per unit, 260× overall).

### 🔴 HISTORY — what broke Phase 3 twice before this (TODO #58 / spec 21 D-GRID-1)
**Runbook 38 Phase 3 passed the wrong FILE as `roi=`:** `AT_2018_TRAIN.geojson` is a **label set**
(900 EuroCrops *field* polygons, 25.4 km²), not a region. `roi=` takes a **region**:
`AT_ROI.geojson` (1 polygon, 10,682 km²). A label file is the input to the *training* path
(`create_training_data(shapefilepath=…, id_col="fid")`), where one polygon = one cube.
**And `roi_to_s2_grids` didn't defend its own invariant:** it clipped with
`gpd.overlay(grids, roi_gdf)`, which emits one row per *(cell × polygon)* pair → **1167 rows for
172 distinct cells**, one repeated **43×**, each row a ~0.016 km² fragment of a 49.6 km² cell.
`id` is the work-unit key, so 16 threads wrote the **same** `geometry.geojson` → `InvalidBlockList`.
**Both fixed:** clip against the union + assert unique ids (`grid.py`), `setup()` refuses duplicate
ids (any caller), runbook 38 → `AT_ROI`, spec 21 amended (**D-GRID-1**).
**⚠️ The "1167 cells" in every earlier doc was never a cell count** — the real figure was 172 cells,
and the corrected ROI gives 300.

**TODO #57 is RETRACTED *and* REVERTED (user's call).** The adlfs "transient concurrent-write race"
was never demonstrated: runbook 36 wrote **900 distinct blobs** at the same 16-way concurrency, same
VPN, same account, in **71 s with zero errors**. The retry fixed nothing, could never fix a
deterministic same-blob collision, and actively **buried** the real error — 16 threads × 6 attempts
made a fast legible failure into a minutes-long `[storage] transient write error` storm that read as
an infinite loop. `_write_with_retry` + its 4 tests are **gone**; `fs.write_bytes`/`write_text`
survive as plain seam helpers. **`InvalidBlockList` under concurrency now means "two writers, one
blob" first, not "flaky link".**

**Duplicate ids now die in PREFLIGHT, before any spend.** Tiling moved *inside* `run_inference`'s
preflight — ahead of `fs.makedirs` and `_ensure_bundle` — so a bad ROI fails in seconds instead of
after a blob folder + a bundle upload (627 s for 13 MB over VPN) + setup's N writes + AML dispatch.
It also **prints the cell count before spending** (`[run_inference] roi -> N grid cells`), since N is
the workload and the bill. Three layers: `roi_to_s2_grids` asserts at source → preflight rejects
before spend → `setup()` refuses for every caller.

`pytest -q` **443 passed / 2 skipped**, `ruff check src/ tests/` clean.
**git:** `main` = `3db3dd9` in sync with `origin/main`; the D-GRID-1 fixes, the TODO #57 revert, the
preflight guard and these doc corrections are **UNCOMMITTED** on top of it. `runbooks/HANDOFF-inference-phase3.md`
is now **spent** (its task is done) — keep it only as the record of how the bug was found.

**⚠️ Worktree-venv gotcha (diagnosed 2026-07-28 — supersedes the earlier "git-worktree
config-auto-discovery" explanation in the spec-39 aside, which was WRONG):** a worktree `.venv` built
with a bare `pip install -e ".[dev]"` diverges from the repo `.venv` in two ways that look like
regressions and are not.
1. **`pytest -q` reports 411 passed / 4 skipped, not 436/2** — because the fresh venv lacks the
   **optional** extras, so `tests/test_azure_seam.py` (**25** tests, needs `adlfs`) and
   `tests/test_grid.py` (**4** tests, needs `s2sphere`) `importorskip` at module level. Nothing is
   silently uncollected; 411 + 25 + 4 = 440. Verified by running the worktree's code with the repo
   venv's site-packages on `PYTHONPATH` → **440 passed / 2 skipped** pre-review.
   **This matters:** `test_azure_seam.py` is the module most relevant to any `fsd.storage` change
   (`test_memory_scheme_roundtrip_parquet_and_npy` covers `save_npy`/`write_parquet` directly), so a
   storage-seam change validated only in a bare worktree venv has NOT been validated where it counts.
2. **`ruff check` reports hundreds of errors unless narrowed to `--select E4,E7,E9,F,I`** — because
   the fresh venv resolves a **newer ruff** (0.16.0 vs the repo venv's 0.15.20) whose default rule set
   is much larger; `pyproject.toml` is read correctly in both. Confirmed: ruff 0.16.0 flags 262 issues
   repo-wide on unmodified `main`; the repo's own ruff 0.15.20 over the same worktree code →
   **All checks passed**. Do NOT narrow the `--select`; run the **repo venv's** ruff instead.

**Recipe (use it for any future worktree):**
`PYTHONPATH=<repo>/.venv/lib/python3.11/site-packages <worktree>/.venv/bin/python -m pytest -q` and
`<repo>/.venv/bin/ruff check --config pyproject.toml src tests` — the worktree's editable `fsd` still
wins on `sys.path` (a `.pth` editable finder in a `PYTHONPATH` dir is not processed), so this tests the
**worktree's** code against the **repo's** full dependency set.

### ✅ DONE — seam retry for adlfs `InvalidBlockList` (TODO #57, implemented 2026-07-28 Sonnet@medium, reviewed + corrected Opus@high)
Implemented test-first to the design below: `_is_transient_write_error` + `_write_with_retry`
(exp backoff, 5 retries, message-matched, no azure import) in `src/fsd/storage/fs.py`; new
`write_bytes`/`write_text`; `save_npy`/`write_parquet` writes wrapped; `create_datacube.py:143` routed
through `fs.write_text`. New tests in `tests/test_storage.py` (recovers after k transient failures /
re-raises non-transient immediately / re-raises transient after exhausting retries / `write_text`
memory:// round-trip) — all non-vacuous (asserted call counts, not just "no exception"). One
pre-existing test (`test_setup_does_not_corrupt_a_remote_run_folderpath`) mocked `fs.open("w")` for the
old call site; updated to mock `fs.write_text` instead, matching the new seam. `LIMITATIONS.md` row +
`TODO.md` #57 both flipped to fixed.

**🔧 REVIEW FINDING (Opus@high, fixed in the same worktree) — the transient classifier was too broad
and would have retried PERMANENT failures.** The design's marker list included the literal
`"Failed to upload block"`. Reading `adlfs/spec.py` (2026.5.0) `_async_upload_chunk` shows that string
is adlfs's **catch-all** wrapper — `except Exception as e: raise RuntimeError(f"Failed to upload block:
{e}!")` — so a blocked credential, an RBAC denial, a missing container and a malformed path all wear
it. Matching it meant *any* adlfs write error got 6 attempts with 15.5 s of cumulative backoff per
file, across a 1167-cell × 16-thread fan-out, instead of failing fast. **Observed live, not
hypothetical:** reverting the call site during review produced
`RuntimeError: Failed to upload block: ERROR: AADSTS53003: Access has been blocked by Conditional
Access policies…` — a permanent auth error that the old marker set classified as transient (proven: 6
attempts). **Fix:** drop the wrapper prefix, key only off the Azure **storage error codes**
(`InvalidBlockList` / `The specified block list is invalid` / `ServerBusy` / `OperationTimedOut`). The
genuine race is still matched because adlfs interpolates the inner `HttpResponseError` and
azure-storage-blob always appends `"\nErrorCode:<code>"`
(`azure/storage/blob/_shared/response_handlers.py`). **+1 regression test**
(`test_write_with_retry_reraises_a_wrapped_auth_error_immediately`) and the two transient tests now use
the verbatim wrapped-message shape rather than a bare `"InvalidBlockList"` string.
**Also hardened:** `test_setup_does_not_corrupt_a_remote_run_folderpath` now asserts the recorded
`write_text`/`write_parquet` paths. It already failed on a call-site regression, but only by escaping
the mock into a **real ~97 s abfss:// round-trip**; it now fails offline and instantly.
Everything else in the diff was checked and stands: `fs.py` has no azure import (`fsd.storage.azure`
is fsd's own module and imports only `fsspec`), the `print` prefix matches the repo's `[setup]`
convention, wrapping `save_npy`/`write_parquet` is justified (both are per-cell concurrent-write
sites), and all 5 new tests fail with the fix reverted. Original design (kept for the record):
**Symptom (real, runbook 38 Phase 3, 2026-07-28):** `create_datacube.setup()` for the 1167-cell ROI
died at shape 0/1167 with `azure.core...HttpResponseError: The specified block list is invalid`
(`ErrorCode:InvalidBlockList`), re-raised by adlfs as `RuntimeError("Failed to upload block: ...")`,
thrown from `create_datacube.py:143` (`with fs.open(shape_path, "w")`).
**Root cause:** adlfs stages a block-blob as parallel block uploads + a final `commit_block_list`.
`setup()` fans per-cell `geometry.geojson` + `catalog.parquet` writes across **16 threads**
(`config.SETUP_MAX_CONCURRENT`) through the **one shared** adlfs async client; under that concurrency
(worsened by this session's flaky West-Europe link) the block staging/commit races → `InvalidBlockList`.
It is a transient race, **not** a data error — a fresh write re-stages clean blocks and commits.
Runbook 36 got lucky at 900 shapes; 1167 tripped it. **`config.SETUP_MAX_CONCURRENT` is bound at
import as `setup`'s default arg, so setting the global at runtime does NOT change it** — not a usable
workaround.
**The FIX (designed, verified reachable — I had started it, then reverted to hand off clean):**
Add a **seam-level retry** in `src/fsd/storage/fs.py` (backend-agnostic — match by MESSAGE, fs.py must
not import azure):
1. `import time`; constants `_TRANSIENT_WRITE_MARKERS = ("InvalidBlockList", "Failed to upload block",
   "ServerBusy", "OperationTimedOut")`, `_WRITE_RETRIES = 5`, `_WRITE_BACKOFF_SECONDS = 0.5`.
2. `_is_transient_write_error(exc) -> bool` (substring match on `str(exc)`), and `_write_with_retry(
   writer, *, what)` that runs `writer()` (a full open→write→close), retries on transient with
   exponential backoff (`_WRITE_BACKOFF_SECONDS * 2**attempt`), re-raises non-transient immediately and
   the transient once retries exhaust.
3. New seam fns `write_bytes(path, data)` / `write_text(path, text)` (encode utf-8) that wrap
   `fs.open(p,"wb")+write` in `_write_with_retry`; add both to `__all__`.
4. Wrap the blob writes inside `save_npy` (`fs.py:185`) and `write_parquet` (`fs.py:263`) in
   `_write_with_retry` too (both are concurrent-write sites).
5. In `workflows/create_datacube.py:143` replace `with fs.open(shape_path,"w") as f: f.write(
   shape_gdf.to_json())` with `fs.write_text(shape_path, shape_gdf.to_json())`. The sibling
   `fs.write_parquet(catalog_path, subset)` (line 145) is auto-covered by (4).
**Tests (non-vacuous):** unit-test `_write_with_retry` — recovers after k transient failures (assert
call count), re-raises a non-transient (`ValueError`) immediately, re-raises transient after exhausting
retries; monkeypatch `_WRITE_BACKOFF_SECONDS=0` to avoid sleeps. Plus a `write_text` memory:// round-trip.
**Verify:** `pytest -q` (baseline **436 passed / 2 skipped**) + `ruff check src/ tests/`. Then the user
re-runs runbook 38 Phase 3 (setup should push all 1167 shapes through). **Docs:** LIMITATIONS.md row +
TODO #57 (both added this handoff — flip them to "fixed" when it lands) + CHANGES.md if warranted.
**Note the 1167-cell scope (accepted by user 2026-07-28, "keep 1167 + fix adlfs"):** `run_inference(
roi=…)` tiles the ROI's **convex hull**, so AT_2018_TRAIN's 900 scattered fields → 1167 grid cells over
a large mostly-empty region. That's a heavy but valid crop-map fan-out; the user chose to keep it. If a
future run wants fewer cells: a compact contiguous ROI or a larger `grid_size_km`.

### ✅ Runbook 38 (inference on AML) — Phases 0-2 GREEN on the real cluster (2026-07-28); Phase 3 blocked (above)
- **Env build + smoke GREEN:** the 2nd (inference) AML Environment builds from `demos/adapters.py` +
  sklearn/joblib; node smoke printed `FSD_INFER_ENV_OK 0.1.0 DemoRF` (D4/D11 — `resolve_ref('adapters:
  DemoRF')` imports on a node). First-run gotcha now guarded in the runbook Setup: `az ml environment
  list -n <missing>` throws a cryptic `System.Net.Http...` and leaves `AZ_INFER_ENV_VERSION` empty →
  build the env FIRST.
- **Phase 0 GREEN** (D3 bundle-stage + node fetch + adapter import): `smoke_status.status=="ok"`.
- **Phase 1 GREEN:** ROI `s2grid=476da24` (a **single-MGRS-tile** ROI — one CRS, simple build — NOT one
  grid cell) tiled into **9 grid cells** → 9 `output.tif` COGs + STAC on blob, `n_outputs==n_grid_cells`.
  The old "one cell" label was the grid-cell/MGRS-tile terminology trap; runbook Phase 1 rewritten.
  **This is where the grids.geojson seam bug was found + fixed (`9422a1a`)** — see below.
- **Phase 2 GREEN:** resume (D6/D7 — all 9 cells skip via output.tif-exists) + D13 duplicate guard
  (`d13_guard_raised: true`).
- **CODE FIX `9422a1a` — `run_inference(roi=)` staged `grids.geojson` via GDAL** (`grids.to_file`),
  which has no `abfss://` write driver → failed on a blob `output_folderpath`. Fixed to write through the
  storage seam (`fs.open`+`to_json(default=str)`), mirroring `create_datacube.setup`'s seam READ
  (`create_datacube.py:79`). **4th instance** of the repo's "GDAL assumed to handle abfss://" class
  (after cdse `_roi_gdf`, `task.py`, spec-39 gdf staging). +1 non-vacuous regression test (memory:// dst).
  Every prior unit test used a local `tmp_path`, so `grids.to_file` (GDAL-local) always passed — only the
  real blob path exposed it. **The adlfs #57 fix is the SAME lesson one layer down** (seam not resilient
  under real concurrency + real network).

### Bundle facts (do not re-derive) + the modelling insight
- **Demo bundle = `tests/outputs/p40_train_and_bundle/demo_rf_bundle/`** (adapter `adapters:DemoRF`,
  `n_timestamps=8`, `required_bands=[B04,B08]`, `uint8`/255). **`rf.joblib` = 13 MB** after switching
  Phase 1 to **`aggregate="median_per_id"`** (≤900 field medians, not 172k pixels). `AZ_BUNDLE_LOCAL`
  points here for runbook 38.
- **Why median-per-id (user chose it 2026-07-28):** labels are per-field, so the field median is the
  honest training unit; it also fixed a **1.1 GB** model — an *un*aggregated per-pixel RF (200 unpruned
  trees × 172k rows) is ~1 GB, and the bundle is fetched to **every** inference node. Median → 13 MB.
  It is **training-only** (`aggregate` ≠ `DemoRF.feature_sequence`); inference stays **per-pixel** →
  per-pixel crop map (demo_02/03 design, not skew).
- **Accuracy is now HONEST:** per-pixel random split **leaked** (pixels of the same field in train+test
  → inflated **0.696**); field-wise median split → **0.293** test / **1.0** train (real generalization +
  a clear overfit tell). ~29% 9-class crop accuracy from NDVI+SAVI over 8 mosaics is a plausible feature
  ceiling; better accuracy = a modelling exercise (more bands/features, `min_samples_leaf`/`max_depth`),
  permanently user-side (ADR-0018). Does NOT block the pipeline demo.
- **Operational learnings (so they aren't re-chased):** (1) the **627 s bundle-stage was NOT an
  IMDS/credential hang** — it was a 1.1 GB upload at ~1.9 MB/s over a slow VPN
  (⚠️ **this doc contradicts itself on the size** — the preflight paragraph above says "627 s for
  13 MB". 1.1 GB at 1.9 MB/s is the self-consistent pair; the "13 MB" is unsourced. Neither changes
  the TODO #61 conclusion, which turns only on the 627 s not fitting in a 249 s window); I over-diagnosed a
  DefaultAzureCredential/IMDS hang off a misleading `System.Net.Http` error (which was really the
  missing-env `az` quirk). `AZURE_TOKEN_CREDENTIALS=dev` was **deliberately held out** of the runbook —
  no evidence it was needed. (2) **OUT40/OUT38** are distinct scratch vars per runbook (running 40→38
  back-to-back in one shell used to cross-write). (3) All runbook commands assume **cwd = `fsd/`** —
  the `$PWD`-based `OUT` export compounds into a bad nested path if run from a subdir.

**Runbook 38 hand-off recap** (for the Phase-3 re-run after #57 lands): `export
AZ_BUNDLE_LOCAL=<repo>/tests/outputs/p40_train_and_bundle/demo_rf_bundle`; `export OUT38=<repo>/tests/
outputs/p4_inference_aml`. **The #57 fix unblocks Phase 3 with NO image rebuild** — the failing
`create_datacube.setup()` runs **driver-side** (the fix in the local venv is enough). Rebuilding the
inference Environment is optional hygiene (so nodes' own writes get the same retry), not required to get
past the setup blocker. Phases 0-2 are idempotent to re-run. `runbooks/README.md` maps the full run
order (`36-phase0 → 37 → 37-verify → 36 → 39 → 40 → 38`) until the C4 refactor (TODO #55).

### ✅ Runbook 40 (train + bundle) — RUN GREEN, all 3 phases (2026-07-28)
Option (a), KISS, **zero new fsd code** — orchestration of existing verbs.
- **Phase 1** (`flatten_training_data(..., adapter=DemoRF(), runner="aml")`): PASS in **179.4 s** (aml
  reduce only — `_land_local` skipped the already-landed raw arrays; `_apply_training_features` ran
  **driver-side**, ADR-0020). `features (900, 8, 2)` = **NDVI+SAVI**, one row per field;
  `feature_ids`/`feature_labels` both 900; raw `data.npy` kept.
  ⚠️ **Corrected 2026-07-28.** This line used to read *145.7 s / `features (172781, 8, 2)`* — the
  numbers from the **first** run, before Phase 1 was re-run with **`aggregate="median_per_id"`** (the
  switch that took `rf.joblib` from 1.1 GB to 13 MB — see Bundle facts below). The re-run is the run
  of record: the demo bundle was built from it. Source of truth =
  `tests/outputs/p40_train_and_bundle/phase1_result.json`.
- **Phase 2** (train DemoRF@T=8, **user-side, ADR-0018** — RF + LabelEncoder → `rf.joblib`): PASS.
  **900 field medians**, `n_features=16` (=T·Bf=8·2, reshape contract intact), **9 classes**, train acc
  **1.0** / test acc **0.2933**.
  ⚠️ **Corrected 2026-07-28** from *172781 px / train 0.863 / test 0.696* — same cause: those were the
  pre-`median_per_id` per-pixel numbers, and the 0.696 is exactly the **leaked** score the "Accuracy is
  now HONEST" note below already retracts (pixels of one field landed in both train and test). Source
  of truth = `tests/outputs/p40_train_and_bundle/phase2_result.json`.
- **Phase 3** (`bundle.save`): PASS + round-trip. `bundle.json` → `adapter: "adapters:DemoRF"`,
  `required_bands:[B04,B08]`, **`n_timestamps: 8`** (set on the instance before save — DemoRF pins 0),
  `uint8`/`255`, `artifacts:{model: rf.joblib}`; `bundle.load` resolved→instantiated→validated→`.load()`
  clean (`roundtrip_loaded: true`). Bundle at `tests/outputs/p40_train_and_bundle/demo_rf_bundle/`.

Option (b) (a public `apply_features` verb over already-landed arrays, avoids the ~2.4 min re-run)
remains deferred YAGNI — the re-run is cheap.

**⚠️ Corrections found against the ACTUAL `demos/adapters.py:DemoRF` (baton was imprecise):**
- **DemoRF is at `demos/adapters.py` — IN the repo, but NOT in the fsd wheel** (wheel = `src/fsd/`
  only). So it's importable as `adapters` with `demos/` on `PYTHONPATH`, and the demo IS reproducible
  from the repo — the inference image still `COPY`s `demos/adapters.py` (defaulted in 38's build step).
  The old "user's local module, not in repo, not reproducible" framing is **wrong**; runbooks written
  to the corrected reality. (If a different *private* adapter is intended for the real run, revisit.)
- **DemoRF pins `n_timestamps = 0` on purpose (model-determined).** The **bundle** records T: runbook
  40 Phase 3 sets `adapter.n_timestamps = 8` on the instance before `bundle.save`, so `bundle.json`
  carries 8. Runbook 38's inference preflight reads it via `read_spec` (`api.py:1072`); note
  `if want_t and …` means a manifest T of **0 would SILENTLY SKIP the T-check** — hence Phase 3 must
  set 8. A fresh `DemoRF()` reading 0 is correct.
- Reshape confirmed: DemoRF inherits `BaseModelAdapter.datacube_to_X` (T-outer/band-inner), so Phase
  2's `features.reshape(len, -1)` matches inference (F1 anti-skew). Artifact `(clf, le)` + bundle key
  `"model"` match `DemoRF.load`.

**git:** `main` is **2 commits ahead of `origin/main` (`e7d8ba6`), UNPUSHED** — (1) runbook-40 +
README + reconcile-38; (2) this PROGRESS flush marking runbook 40 GREEN (docs only). Run the
RECIPES.md identifier sweep before pushing (new runbook/README use placeholders only — sweep clean).

## ⭐ SPEC 39 (create_training_data e2e on AML: flatten→land-local) **DONE — IMPLEMENTED + MERGED + OPUS-REVIEWED + VALIDATED ON THE REAL CLUSTER** (runbook 39 Phases 0–2 GREEN 2026-07-27; the Timestamp-staging bug found there is fixed + pushed, `1781331`). (impl Sonnet@medium, 2026-07-24; merge commit `9e20623`, `--no-ff` over impl commit `684e0de`; worktree `spec39-implement` pruned, branch deleted). **→ NEXT: run `runbooks/39-training-data-on-aml.md` Phases 0-2 on the real cluster** (the only thing unproven — every unit test is mocked at the AML-client boundary, spec 39 §7's "no test requires Azure"). All 8 spec §7 tests landed in `tests/test_training_data_aml.py` (14 test functions after non-vacuousness splits); full suite on `main` post-merge: 430 passed/3 skipped, `ruff` clean. Docs updated: `CHANGES.md`, `LIMITATIONS.md`, `TODO.md` #56, `RECIPES.md`, `ROADMAP.md` P3, `CONTEXT.md` ("reduce job", "land-local"). **`main` is 3 commits ahead of `origin/main`, UNPUSHED** (push only when the user asks). (Aside, not spec-39's: the impl worktree's `ruff` resolved a much broader ruleset than `main`'s real config — worked around with `--select E4,E7,E9,F,I`; `main`'s own `ruff check` is unaffected and was used for the final verification above. **❌ CORRECTED 2026-07-28: the "git-worktree quirk, `.git` file vs directory" diagnosis recorded here was WRONG** — `pyproject.toml` is read correctly in a worktree. The real cause is a **ruff version difference** between the worktree venv and the repo venv; the fix is to run the *repo* venv's ruff, never to narrow `--select` (which hides real findings). See the top block + `RECIPES.md` "Verify a worktree's code against the repo's FULL dependency set".)

### ⚠️ Real-cluster run (runbook 39, 2026-07-27) found bugs the mocked review missed — Phase 1 GREEN, Phase 2 fixed & pending re-run
- **Env gap (runbook defect, not code):** the general-purpose AML Environment bakes the fsd wheel in at build time, and spec 39 **adds a new node-side module `fsd.workflows.flatten`** — so the spec-36/37 image failed with `No module named fsd.workflows.flatten`. Runbook 39 wrongly said "no rebuild needed (ADR-0020)"; ADR-0020 only excuses a *model-specific* image, not new fsd code. **Fixed runbook 39 Prerequisites** (rebuild from current `main` + extend the smoke to `import fsd.workflows.flatten`). Same latent trap noted for runbook 38's inference image.
- **Phase 1 GREEN** after the rebuild: 900 blob cubes → one single-node reduce → `(172781, 8, 3)` uint16 array landed locally; ids/labels/coords all len 172781; coords in EPSG:4326 (Austria); **`data.npy` = 8.29 MB → peak ≈ ~16 MB**, an order of magnitude under D3's estimate (recorded in `LIMITATIONS.md`).
- **CONFIRMED BUG in the impl, fixed 2026-07-27 (`api.py:461`):** staging an in-memory gdf used `gdf.to_json()`, which routes through `json.dumps` and raises `TypeError: Object of type Timestamp is not JSON serializable` on a Timestamp/datetime property column (EuroCrops' obs date). The old `gdf.to_file(driver="GeoJSON")` serialized datetimes via GDAL; the spec-39 seam-write switch to `to_json()` lost that. **Fix:** `gdf.to_json(default=str)` (+ comment). **Every existing test's fixture was too clean** (int/str/geometry only) to catch it — added `test_create_training_data_stages_gdf_with_timestamp_column` (verified non-vacuous: FAILS with the exact TypeError on pre-fix code). Full suite 435 passed/2 skipped, ruff clean. **→ user re-runs Phase 2.**
- **Lesson:** mocked-at-the-AML-boundary tests + a code-only review both passed a bug that only real EuroCrops data (with a datetime column) exposes. The synthetic fixtures should carry a datetime property column going forward.

### Opus@high review outcome (2026-07-24) — initial pass read CLEAN (SUPERSEDED by the real-cluster run above); 3 minor notes, none demo-blocking
The retroactive review the merge skipped. Traced all three aml phases (download→build→flatten→land-local) end to end and verified the §4 reuse ledger against the diff: `datacube.flatten.flatten`, `api.download`, `_apply_training_features`, `_aml_submit_and_wait`/`_aml_preflight_common`, `storage.transfer`, and the build fan-out are **zero-lines-changed** (confirmed). Column canonicalization is correct — `setup` writes canonical `id`/`label` (COL_ID/COL_LABEL), so `create_training_data`'s hardcoded `id_col="id"/label_col="label"` into `flatten_training_data` is right. `label_col=None` + `adapter=` works (`_apply_training_features` guards `labels is None`). The two-run_ids layout (build's `run_aml` mints its own run_id for shards; flatten reuses create's run_id for `runs/<id>/_flatten`) is cosmetic, not a bug — cubes+input.csv+`_flatten` all sit under create's `run_folderpath`. Runbook 39 Phase 1 passes `label_col="label"`, Phase 2 uses the canonical `catalog.parquet` basename and an in-memory gdf — both coherent with the code. `run_aml_download`/`run_aml`/`run_aml_flatten` all accept the shared `runner_kwargs` keys (no TypeError in any phase). Full suite re-verified green on `main` (430/3, ruff clean). The `_download_verb` module-alias shadowing (flagged in the handoff) reads fine — well-commented, functionally correct. **3 minor notes, deliberately NOT fixed (none blocks the demo):**
1. **`_as_gdf(label_polygons)` in `create_training_data`'s preflight uses `gpd.read_file`** — for a **blob-URL** `label_polygons` on `runner="aml"` this fails on the driver (GDAL has no `abfss://` driver — the exact issue spec 37 fixed elsewhere via `fs.open`+`BytesIO`), so spec D1's "a path/URL `label_polygons` is used as-is" does **not** hold for blob URLs. **Fails loud** (a preflight error, not silent), and the **demo is unaffected** (Phase 1 has no polygons; Phase 2 passes an in-memory gdf, which `_as_gdf` returns without reading). Pre-existing (preflight always called `_as_gdf`), not spec-39-introduced. Fix if a URL-ROI aml path is ever wanted: route the URL read through the storage seam. → new TODO candidate.
2. **`catalog_filepath` basename must be `catalog.parquet` when `download=True`** — the download phase hardcodes `catalog.parquet` under `dirname(catalog_filepath)`, so a non-canonical basename would make download write one path and the build read another. No preflight guard; the runbook uses the canonical name so the demo is fine. A one-line preflight assert would harden it.
3. **Unquoted URL interpolation in `run_aml_flatten`'s command string** — identical to the existing `run_aml`/`run_aml_download` pattern (proven on the real cluster, specs 36/37), so not a new concern; blob URLs carry no shell-special chars.

**What spec 39 is.** `create_training_data` becomes the **one-verb e2e façade** — `download → build →
flatten → land-local` — with a new sibling `flatten_training_data` for flatten-only over already-built
blob cubes (runbook-36 Phase-3 `input.csv`). Flatten runs as a **single-node AML reduce** (not fan-out)
on the **existing general-purpose fsd Environment**, then `storage.transfer`s the **compact** array to
the **local** `export_folderpath` (driver stays control-plane-only, ADR-0004). Net code delta is small +
reuse-heavy: `flatten_training_data` + `workflows/flatten.py` CLI + `runners.run_aml_flatten` (on the
spec-37 `_aml_submit_and_wait`) + an `api._land_local` transfer loop, plus download-phase/label/split
changes to `create_training_data`. `datacube.flatten`, the build fan-out, download, and the whole
feature path are **unchanged**.

**The 5 grilled decisions (2026-07-24 `/grill-with-docs`), so they aren't re-litigated:**
- **Q1 → features stay, driver-side.** The feature transform already runs on the driver today
  (`api.py:416→427`), never on a cluster node. Cluster flatten emits **raw**; after land-local,
  `create_training_data` runs `_apply_training_features` on the driver → `features.npy`, unchanged.
  **Spec 18 / ADR-0018 / Adapter glossary / `eurocrops_rf.py` NOT touched.** Recorded as **ADR-0020**
  (general-purpose images emit raw; adapter transform only at model-specific endpoints).
- **Q2 → local `export_folderpath` + blob `root` in `runner_kwargs`** (spec-36/37 convention); verb
  auto-lands the compact array. `run_folderpath=export/run` default is **local-runner only**.
- **Q3 → accept an in-memory GeoDataFrame**; verb auto-stages it to one GeoJSON under the blob `root`,
  used as **both** download-ROI and build-shapefile.
- **D-labels → `label_col` optional** (drop the required check `api.py:368-369`; keep `id_col`).
  `ids.npy` is the label join key; labels are a separable overlay (CONTEXT.md "Label").
- **Q4 → prove via Phase 1** (flatten-reduce over the existing 900 blob cubes = scale) **+ Phase 2**
  (small fresh e2e = composition). **No redundant full-scale Phase 3.**
- **D6 → drop the adapter `n_timestamps` preflight** (`api.py:348-354`); DemoRF **retrains at T=8**
  (Apr–Sep 2018 @ mosaic_days=20). `required_bands` preflight stays. Calendar-mosaic same-`timestamps`
  invariant unchanged.

**Docs already written this session:** `specs/39-training-data-on-aml.md` (D1–D7 + D-labels, §4 reuse
ledger, §5 deliverables, §6 runbook phases, §7 tests, §9 sources), `docs/adr/0020-*.md` (+ README row),
`CONTEXT.md` "Label" term. **Still to write during impl:** `workflows/flatten.py`, `run_aml_flatten`,
`flatten_training_data`, `_land_local`, the `create_training_data` deltas, `runbooks/39-*.md`, and the
`CHANGES.md`/`LIMITATIONS.md`/`TODO.md`/`RECIPES.md`/`ROADMAP.md` updates (spec §5 deliverable 7).

**Then (unchanged order):** (2) user trains DemoRF locally at T=8 + metrics (user-side, permanent);
(3) return to `runbooks/38-inference-on-aml.md` (still has the T=8-vs-10 caveat below — now resolved to
T=8 — and the `adapters` module Dockerfile `COPY`).

### ⚠️ Runbook 38 has a DemoRF-mismatch to fix before it can run (this session, 2026-07-24)
The user's actual inference bundle is **`adapters:DemoRF`** (`required_bands=[B04,B08]`,
**`n_timestamps=10`**), NOT `eurocrops_rf:EuroCropsRF`. Runbook 38's Phase 1/2/3 scripts hardcode
`2018-04-01…2018-09-01, mosaic_days=20` → **T=8**, so the driver preflight (`api.py:353`) fails
`T=8 but adapter.n_timestamps=10` before any cluster spend. **Before running 38:** (a) pin its window/
mosaic_days to DemoRF's *training* config (must give T=10; unknown — get from user), bands stay a valid
superset ([B04,B08,B8A,SCL] ⊇ [B04,B08], preflight `api.py:727`); (b) the new "Build the inference
Environment (D4)" section's Dockerfile must `COPY` the **`adapters`** module + `ENV PYTHONPATH` so
`adapters:DemoRF` imports (not `eurocrops_rf`). This session added that build section to runbook 38
(uncommitted). The `adapters` module is not in the repo — user has it locally.

## ⭐ SPEC 38 (P4, inference at scale on AML) **IMPLEMENTED + REVIEWED** (impl Sonnet@medium; review Opus@high, both 2026-07-23) — in a worktree (`worktree-spec38-inference-aml`), **committed (impl `347f6f3`), review fix not yet committed, not yet pushed**. **→ NEXT: run `runbooks/38-inference-on-aml.md` Phases 0–3 on the real cluster** (the only thing left unproven — every unit test is mocked at the AML-client boundary, per spec 38 §7's "no test requires Azure").

### Opus@high review outcome (2026-07-23) — 2 fixes applied, 1 item guarded
- **CRITICAL, FIXED — `engine._write_output_cog` was NOT remote-safe** (the per-cell `output.tif` site
  an AML node writes for *every* cell, i.e. the whole point of P4). The reuse ledger + the bullet below
  claimed it was an "unchanged caller that gets blob for free" — **it was not**: it kept the pre-spec-38
  local-only pattern (`os.makedirs(os.path.dirname(dst))` + `raw_tif = f"{dst}.raw.tif"` +
  `rasterio.open(raw_tif, "w")`), so a remote `abfss://…/output.tif` dst did a **forbidden remote
  `rasterio.open(mode="w")`** (D5's explicit "never" clause) and scattered **junk local dirs**
  (`./abfss:/cont@…/…` — reproduced empirically). The sibling `_merge_outputs` got the local-scratch
  guard; `_write_output_cog` was missed. **Fix:** same guard mirrored into `_write_output_cog` (local
  scratch via `tempfile` when dst is remote); test 6 was passing **spuriously** (`memory://` doubles as a
  valid local literal path in an azure-less venv) — strengthened to assert cwd stays free of junk
  (verified it FAILS on the pre-fix code). 388→ still green, ruff clean.
- **FIXED — D7's LOCKED "load-per-core" default now computed on the node.** Was: `run_aml_inference`
  defaulted `cores=1`/`cubes_per_task`→1, so the default AML run was serial with one bundle-load per
  cell (the exact TODO #25 pathology D7 set out to kill). Now `infer_shard._resolve_cores_and_group`
  computes the default from the node's own `os.cpu_count()` + the shard size: `cores`/`cubes_per_task`
  unset → `cores = cpu_count()`, group = `ceil(n_units/cores)` → bundle loads **once per core per node**
  (node fully busy); `cores=1` is the heavy-model **load-once-per-node** opt-out (one whole-shard group,
  one load). Threaded via a `None`=auto sentinel: `api.run_inference` `cores`/`cubes_per_task` default to
  `None`, `run_aml_inference` omits the `--cores`/`--cubes-per-task` flags when unset (node decides),
  local/pre-built paths resolve `None`→`1` (behaviour unchanged). `_status/<k>.json` now reports the
  effective `cores`/`cubes_per_task`/`n_groups` for Phase-3 verification. +2 non-vacuous tests.
- **FLAGGED, guarded — `_UNIT_IDENTITY_COLS` is duplicated** in `create_datacube` (dedupe) and `runners`
  (guard) to dodge a circular import. Verified identical; added a test pinning them equal so a future
  edit can't silently drift the dedupe key from the guard key.

- **The spec:** `specs/38-inference-on-aml.md` — P4 = `run_inference(roi=…, runner="aml")` as a **thin
  step-4 dispatch swap** over the spec-21 per-cell build+infer unit (reusing spec 36's `run_aml`
  machinery), **plus the fixes the swap exposes**. 14 decisions (D1a…D14); §4 reuse ledger, §5 the 13
  deliverables, §6 the 4 run-book phases, §7 the 12 tests. Baseline preserved (this session's venv has
  fewer optional extras installed than the 382/3 baseline was measured with — 4 skips here are
  `[grid]`/`[azure]`/`[serving]`/`[titiler]` extras not installed, not a regression; **388 passed / 4
  skipped**, +31 new tests in `tests/test_infer_aml.py`, none of the original 357 broke).
- **Two latent bugs the implementation surfaced (not just landed features):** (1) `api._merge_outputs`
  built its raw scratch tif from `dst` itself (`f"{dst}.raw.tif"`) — harmless for a local `dst`, but a
  **second** instance of the D5 remote-write bug the spec's own grill (Q4) had already found once in
  `engine._write_output_cog`; fixed in `_merge_outputs` alongside D5. **⚠️ CORRECTION (Opus review,
  2026-07-23): `engine._write_output_cog` itself — the FIRST instance, the per-cell node site — was
  NOT actually fixed by the impl (only `_merge_outputs` was); the review caught + fixed it, see the
  review-outcome block above.** (2) the `create_inference` Snakefile's D6/D7 fix turned out to make the
  spec-described `is_local`-guarded-`abspath` treatment **moot**: the redesigned (grouped) Snakefile
  never touches `export_folderpath` at all — resolving it fully inside `infer_task` instead — so there
  is no `abspath` call left to guard. Functionally equivalent to what the spec asked for (a remote
  `export_folderpath` plans cleanly), simpler than what it described; noted here so a reviewer doesn't
  go looking for a guard that was designed out rather than missed.
- **Deliverable 11 (the inference Environment) and 13 (the run-book) are operator/user-run,** per
  `CLAUDE.md` — text is written (`runbooks/38-inference-on-aml.md`, mirrors 36/37's phase-script shape;
  the Setup block documents the `az ml environment create` step for D4's second Environment), nothing
  executed.
- **Old signoff context, for the record (nothing left to re-derive from it — superseded by the above):**
- **Three MANDATORY I/O-seam fixes** (node can't otherwise produce a result on blob): **D5** remote-dst
  COG **in `raster.cog.to_cog`** (not engine — fixes both per-cell `output.tif` AND `merged.tif`; closes
  TODO #17); **D6** the `create_inference` Snakefile D7 blob-safety + `infer_task` skip-if-`output.tif`;
  **D3** manifest-driven bundle fetch to node scratch.
- **User-locked folds:** **D4** dedicated inference Environment + author/operator/dispatcher
  responsibility split (image-build → P6 `deploy()`); **D7** bundle loaded **per-core per node** (not
  per cell — closes #25 root cause); **D8** *actual* #51 fix (MPC-only per-shard `catalog-<k>.parquet` +
  driver sequential-`append` merge; CDSE untouched); **D9+D10** date normalization at the boundary +
  fail-fast **on the driver before any AML job**, sweep scoped to the datetime-antipattern (bands/scl
  grep-verified clean); **D13** #53 dedupe on content-identity **+ guard on `export_folderpath`
  uniqueness** (found `export_folderpath` is keyed by `id` alone, so id+params dedupe alone wouldn't stop
  the collision).
- **Grill outcomes worth not re-deriving (Q1–Q11):** each caught a real defect/sharpening, not a
  rubber-stamp — the step-4 seam (D1 self-contradiction fixed), the reload-vs-parallelism impossibility
  (D7), `merged.tif` as a second blob-write site (Q4), `fsd.storage.get` being single-file (Q6, from
  cross-val), the node-cold-start "fail-before-nodes" invariant (Q8, D11), and the `export_folderpath`
  keying (Q11). Full table + the two web-cross-validated facts (pystac date-vs-datetime issue #644; AML
  v2 Docker-build-context Environment, not the v1 `add_private_pip_wheel` API) are in the spec §9.
- **Docs produced as we went (`/grill-with-docs` = grilling + domain-modeling):**
  `docs/adr/0001-remote-cog-publish-in-to-cog.md`, `docs/adr/0002-bundle-and-inference-image-decoupled.md`,
  and **`CONTEXT.md`** (new glossary — bundle / manifest / adapter / inference image; grid cell / MGRS
  tile / unit-of-work / shard / run; driver / node / dispatcher). These are the first `docs/adr/` +
  `CONTEXT.md` in the repo, and a deliberate input to the future docs refactor (**TODO #55**, parked
  after a timed e2e demo + report — the C4-model distillation the user requested 2026-07-23).
- **Implementation guidance for the Sonnet session:** implement against the spec's D-sections; the reuse
  ledger (§4) makes the "no new *pipeline* code" claim checkable; on completion close TODO
  **#17/#25/#51/#52/#53** and update `CHANGES.md`/`LIMITATIONS.md`/`RECIPES.md`/`ROADMAP.md` (P4 → done)
  per deliverable 12. **Not P4's job:** create_training_data(roi=) scaling (labelled fields need no
  tiling), infer-only AML fan-out (Open Q4), P5 serving.

## ⭐ DOWNLOAD + DATACUBE ARE PROVEN ON AML (spec 36 + 37, 2026-07-22). `main` pushed at **`980437f`**. **→ NEXT: write SPEC 38 = P4, inference at scale** (Opus@high spec work; baton `/tmp/HANDOFF-spec38-p4-inference.md`). Dispatch the per-cell build+infer task (spec 21) onto AML reusing the P2 runner — a runner/dispatch swap, not new pipeline code — and **fold in TODO #53** (P4 rides the same `setup()` path, so its duplicate-dispatch race lands on the inference COGs). Chosen by user 2026-07-23 over "harden the fan-out first" and "P5 serving".

### Where the cluster work landed (spec 36 + 37, both done + proven)

- **Spec 37 download dispatch — `runbooks/37-download-on-aml.md` Phases 0–3 GREEN**; archive on blob
  (576 granules / 3456 assets, Austria full-year 2018, 6 bands, 4 MGRS tiles).
- **`runbooks/37-verify-archive.md` GREEN** — archive is trustworthy (radiometry 6/6, catalog
  complete, byte-identical to a fresh local ingest). Caveat: all offset=0, so it does not re-prove
  the `c2bf1f1` black-tile fix; that stays covered by `34-mini-mpc-cross-baseline.md`.
- **Spec 36 datacube fan-out — `runbooks/36-aml-runner.md` Phases 1–3b GREEN.** 16-node fan-out,
  exact 900-unit partition, 0 failed; and **Phase 3b: AML-vs-local cubes byte-identical across OS +
  architecture** — the seam claim proven.
- **Open from the runs (see TODO):** #51 download append race (measured *not* to have fired — one
  lucky trial, not safety), #52 window str-vs-Timestamp, #53 setup append duplicates (→ fold into
  spec 38), #54 cluster-side setup (parked, crossover ~510–4850 shapes; local parallel setup 71 s
  for 900).

### Gate-clearing session (2026-07-22, Opus@high) — where the 5 gates stand

| gate | status |
|---|---|
| 1 radiometry | ✅ **CLEARED 2026-07-22** — `37-verify-archive.md` steps 4+5 pass (read the caveat below) |
| 2 catalog completeness | ✅ **CLEARED 2026-07-22** — steps 1+2 pass exactly; step 3's `pass: false` root-caused as benign (TODO #52) |
| 3 run-book 36 wrong prefix | ✅ **fixed** — and it was three defects, not one (below) |
| 4 rebuild the AML image | ✅ done — run-book 36 Phases 1+2 ran green on it |

### `runbooks/36-aml-runner.md` — Phases 1+2 GREEN on the real cluster (2026-07-22)

- **Phase 1** (one shard, one cube): job `Completed`, `n_units 1 / n_skipped 0 / n_failed 0`,
  **47.3 s**. The AML runner builds a datacube on a node from the verified blob archive.
- **Phase 2** (resume, D7): `n_failed 0`, **5.4 s** (8.8× faster), and `n_skipped == n_units` —
  **D7 proven**: every unit asked `run_task` to rebuild and every one returned immediately.
- **⚠️ It reported `n_units: 2` for a ONE-cell ROI → TODO #53.** `create_datacube.setup()`
  **appends** to `input.csv` with no dedupe (`create_datacube.py:127-131`), so re-running the same
  script re-dispatches a list that has grown by one copy of every shape. `n_units` means "rows in
  `input.csv`", not "cells". Cosmetic here (both copies skipped) but **not cosmetic in general**:
  `shard_units` round-robins, so on an *unbuilt* cell the duplicate pair lands on two shards running
  **concurrently**, both writing the same `datacube.npy` with no lock — the TODO #51 shape again, on
  the output artifact. Reachable by re-running a partially-failed Phase 3, i.e. exactly when an
  operator re-runs. Run-book's Phase 2 PASS check corrected to `n_skipped == n_units` (the literal
  `n_units: 1` was never the invariant), and Phase 3 now carries a run-once warning.
- **Phase 3 (the demo, 900 `AT_2018_TRAIN` fields, 8-way fan-out) — first attempt KILLED in
  `setup()`, which was pathologically slow on a remote catalog. FIXED, ready to restart.**
  `setup` called `TileCatalog.filter` per shape, and `filter` opens with a **full** `self.read()`
  of the catalog file → **900 downloads of the same ~121 KiB blob parquet (~106 MiB, ~900 VPN
  round-trips)** before a single job was submitted, with **zero progress output** (the tell: the
  `azure-ai-ml` experimental-class warnings never appeared, because `azure.ai.ml` is imported
  lazily inside `run_aml` — i.e. dispatch had not been reached). Locally the same loop is a 12 ms
  page-cache read per shape, which is why it had never been felt. **Fix (2026-07-22, in `main`,
  381 passed/3 skipped, ruff clean):** pure `catalog.filter_gdf(gdf, ...)` extracted;
  `TileCatalog.filter` delegates to it unchanged; `setup` reads once and filters in memory; plus a
  throttled progress+ETA line. Identical output (declaration `.attrs` still propagate). Pinned by
  `test_setup_reads_catalog_once_regardless_of_shape_count`, verified non-vacuous. **`setup` runs on
  the driver, so this needed no AML image rebuild.** Details in `CHANGES.md`.
- **Second fix, same session — `setup` now prepares shapes CONCURRENTLY.** With the catalog read
  hoisted it was still ~**1.8 s/shape → ETA 1607 s** for 900 shapes, because the remaining cost is
  the per-shape *writes* (`makedirs` + `geometry.geojson` + `catalog.parquet` slice ≈ 4–7 blob
  round-trips). That is **latency, not bandwidth or CPU**, so it parallelises: `max_concurrent`
  (default `config.SETUP_MAX_CONCURRENT = 16`, pass `1` for the old serial path). Safe by
  construction — each shape touches only its own folder and only *reads* the shared catalog frame —
  and it is the same pattern `sources.mpc.download`/`download_shard` already use to drive
  `fsd.storage` concurrently against blob at 3456 assets. **`input.csv` order is unchanged**
  (results placed by index, then compacted), pinned by
  `test_setup_manifest_order_is_shapefile_order_not_completion_order`, verified non-vacuous.
  **382 passed / 3 skipped, ruff clean. MEASURED: 900 shapes in 71 s** (~79 ms/shape, 12.7
  shapes/s) — **22.6× faster** than the 1607 s serial estimate, better than 16 threads alone
  predict. **This settles TODO #54:** 71 s is well below AML cluster startup (40–380 s), so running
  setup on the cluster would make this run *slower*; break-even is ~510 shapes against a warm
  cluster, ~4850 against a cold one, so cluster-side setup only becomes right at P4/P5's
  tens-of-thousands-of-cells scale.
- **✅ PHASE 3 GREEN (2026-07-22) — the datacube fan-out works on real data at 16 nodes.**
  All 16 jobs `Completed`, every shard `status: ok`, **900 units = 4×57 + 12×56, an exact
  partition** of the 900 `AT_2018_TRAIN` fields, **0 failed, 0 skipped** (a genuinely cold build).
  Timing: in-job total **2851.8 s** across 16 nodes, **mean 178.2 s**, slowest **213.8 s**, fastest
  131.8 s → **straggler spread only 1.62×**, against **16.7×** for the spec-37 *download* fan-out at
  8 shards. Datacube builds are compute-bound and near-uniform per field, so the shards balance
  themselves — the download path's variance was never inherent to fan-out. **~3.17 s per datacube.**
  Also confirms **TODO #53 did not bite**: 900 units, not 1800, so `input.csv` was fresh.
- **✅ PHASE 3b GREEN — THE SEAM CLAIM IS PROVEN (2026-07-22).** 3/3 cells built on an AML node and
  rebuilt on the operator's laptop from the **same blob archive** are **byte-identical**:
  `identical: true`, `max_abs_diff: 0.0`, matching dtype and shape for every one. **`runner="aml"`
  and `runner="local"` produce the same science — the runner is config, not a rewrite.**
  Stronger than the run-book asked for: the two builds ran on **different OS and architecture**
  (Ubuntu 22.04 x86_64 node vs. macOS laptop), so the resample/mosaic path is deterministic across
  platforms, not merely repeatable on one machine — different GDAL/PROJ/numpy builds agreed to the
  byte. Shapes cross-check clean: `(T=8, H, W, bands=3)` per cell, with **T=8** exactly
  `compute_n_timestamps(2018-04-01, 2018-09-01, mosaic_days=20)` (the calendar-interval contract
  `flatten` requires — and identical across all three cells), and **3 bands from 4 requested**
  because SCL is consumed as the mask and dropped (`builder.py:310-314`,
  `apply_cloud_mask_scl` → `drop_bands`), not lost. **Spec 36 is demonstrated end to end.**
- **⚠️ Two things Phase 3 did NOT establish.** (1) **No wall clock was recorded** — run-book 36's
  `phase3.py` had the same gap TODO #48 flagged in run-book 37, so setup + allocation + queueing
  cannot be separated from build time and there is no end-to-end number for the demo. **Fixed in the
  run-book** (it now emits `wall_seconds`/`slowest_shard_seconds`/`driver_overhead_seconds`); the
  figure must come from the next run. (2) The AML-vs-local equivalence check was missing from the
  run-book entirely — **added as Phase 3b, and it has now PASSED** (see above).
| 5 commit | ✅ **already done** last session — `6c322fd` (code) + `5df7088` (run-books/docs). Both **unpushed**; `origin/main` is still `e76a8d5` |

**GATES 1+2 CLEARED — `runbooks/37-verify-archive.md`, all 5 steps run 2026-07-22. The archive is
trustworthy. Numbers, so nobody re-derives them:**
- **Step 1** (catalog): 576 granules / 3456 assets / `{"6": 576}` files per granule / bands
  B02,B03,B04,B08,B8A,SCL / MGRS T33UVP+T33UVQ+T33UWP+T33UWQ / 145 dates 2018-01-01..2019-01-01 /
  **declaration stamped** (`reference_band='B08'`, SCL mask classes `(0,1,3,7,8,9,10)` — matches
  run-book 36's `setup(scl_mask_classes=...)` exactly) / 0 duplicate ids.
- **Step 2** (blob vs catalog): 3456 files on blob = 3456 declared, **0 missing, 0 undeclared**,
  0 zero-byte in sample. ⇒ **TODO #51's append race did NOT bite this run** (see the note there —
  that is evidence of one lucky run, *not* evidence the race is absent).
- **Step 4** (tags): 6/6 correct — B04 `scale=1e-4, offset=0.0`, SCL `scale=1.0, offset=0.0`,
  `nodata=0`, `EPSG:32633`, 10980²/5490². **0 black-tile-bug hits.**
- **Step 5** (blob vs a fresh local ingest of the same granule): ids identical, **tags identical,
  window checksums identical** for B04 and SCL ⇒ the bytes on blob are the bytes MPC serves, and
  the cluster stamped what this checkout stamps.
- **⚠️ CAVEAT — gate 1 passed on a weaker test than it looks.** Every granule in this archive has
  `offset = 0` (step 1: `offset_values {"0": 576}`) because all 576 are pre-baseline-04.00 2018
  acquisitions. The black-tile bug was stamping `-1000` (DN) where `-0.1` (reflectance) belonged —
  **at `offset=0` the buggy and fixed code emit the identical tag**, so these results confirm *this
  archive is correctly tagged* (which is all run-book 36 needs) but do **not** re-prove the
  `c2bf1f1` fix, and do not tell us the AML image's vintage. The `-0.1` path stays covered only by
  `runbooks/34-mini-mpc-cross-baseline.md` (2021 vs 2022 items, local). **If the archive is ever
  extended past 2022-01-25, re-run steps 4+5 — that data will exercise the branch this one didn't.**
- **TODO #44 is operationally superseded** for the download path: the mis-tagged artifacts live in
  the old `spec34-demo/` prefix, and the verified `archive/` prefix is what everything now points
  at. Deleting the stale prefix is a user call, and TODO #50 means `fs.rm(recursive=True)` will not
  do it cleanly.

**Gate 3 — `runbooks/36-aml-runner.md` had THREE defects, all of which would have wasted a cluster run:**
1. **Wrong prefix** (the known one): lines 150/208 read `$AZ_ROOT/imagery/catalog.parquet`, run-book
   34's output, whose COGs carry the pre-fix radiometry tags (TODO #44). Now parameterised as
   **`AZ_ARCHIVE_CATALOG`** (`$AZ_DOWNLOAD_ROOT/archive/catalog.parquet`) — note the archive lives
   under a **different root** (`fsd-p2-download`) than this run-book's own runs (`fsd-p2`), so a
   one-word edit would not have fixed it. Setup now `fs.exists()`-checks it before any job.
2. **Phase 3's ROI does not intersect the archive at all.**
   `austria_eurocrops_sampled_ethiopia_translated.geojson` is the Austria fields **translated to
   Ethiopia** (36.1–36.9°E / 11.4–12.0°N) — deliberately, as the 36°E multi-CRS fixture — while the
   archive covers T33UVP/T33UVQ/T33UWP/T33UWQ = **13.6–16.5°E / 47.8–49.7°N**. It is the right ROI
   for a multi-CRS test and the wrong one for this archive (and the Ethiopia imagery behind it is
   gone anyway). All 1015 fields would have produced empty cubes. Swapped for
   **`AT_2018_TRAIN.geojson`** (900 labelled fields, `fid`/`crop`, verified 100% inside `AT_ROI`).
   Phase 1's `s2grid=476da24` was fine — verified 100% inside T33UWP.
3. **`../../shapefiles/` should be `../shapefiles/`** (the scripts run with cwd = `fsd/`). Run-book
   37, the one actually executed, uses the correct single `..`.

**⚠️ NEW, from code inspection while writing the verification run-book — TODO #51: the 16 Phase-3
shards all wrote the SAME `catalog.parquet` via an unsynchronised read-modify-write**
(`runners.py:645` + `catalog.py:106-136`) and finished inside an ~86 s window. **Predicted, not yet
measured:** if the appends overlapped, the bytes are all on blob but the catalog **under-declares
them**, and every datacube silently drops the lost granules' timestamps. `37-verify-archive.md`
steps 1+2 are built to tell "we lost catalog rows" apart from "we never downloaded it" — files
present on blob but *undeclared* is the signature.

### The runbook-37 execution session (2026-07-22, Opus@high) — what it produced

**Result: Phases 0–3 green.** Phase 0 (ROI + creds on blob, creds deleted after use), Phase 1 (one
tile per source: CDSE 16 assets/1.06 GB, MPC 12 assets, 0 failed), Phase 2 (MPC fan-out, exact
partition 964 = 8 shards), Phase 3 (the real archive: **3456 assets = 576 MGRS tiles**, Austria
`AT_ROI`, full-year 2018, bands **B02/B03/B04/B08/B8A/SCL**, 16 shards × 216, **0 failed, 0
circuit-tripped**) → `$AZ_ROOT/archive/` + `catalog.parquet`. B02/B03 were added deliberately so the
archive can serve true-colour RGB to the mini-MPC/STACNotator stack later without a re-download.

**✅ 3432 vs 3456 — SOLVED (2026-07-22, `37-verify-archive.md` step 3 + a local proof). It was
neither MPC churn nor STAC paging: it was `str` vs `pd.Timestamp` → TODO #52.**
Step 3 returned `discovery_repeatable: true` (3432 twice), `only_in_discovery: 0`, `only_on_blob: 24`
— and those 24 assets are **4 granules, all sensing date 2019-01-01, one per MGRS tile**, i.e. one
whole acquisition one day past the window. Cause: both sources forward the caller's dates **raw** to
`pystac_client.search`, which expands a date-only **string** to the end of its day
(`2019-01-01T23:59:59Z`) but treats a **datetime** as an exact instant (`2019-01-01T00:00:00Z`).
Phase 3's run passed bare strings (3456); the 3b dry run wrapped them in `pd.Timestamp` (3432).
Verified locally against the installed `pystac_client` formatter. **Data verdict: no loss, no
re-ingest** — the archive is a *superset* of the intended window, and run-book 36's
2018-04-01..2018-09-01 slice is untouched. **Code verdict: a real defect (TODO #52)** — the CDSE AML
path normalises on the node (`workflows/download.py:97`) while the MPC AML path does not, so the same
call means a one-day-shorter window for CDSE than for MPC. Third instance of spec 36 D3's premise
being violated, after TODO #49.

**Code fixed this session (both green, 380 passed / 3 skipped, ruff clean):**
- **`sources/cdse._roi_gdf` now reads via `fs.open` + `BytesIO`.** GDAL/pyogrio has no `abfss://`
  driver, so a blob ROI failed with a **lying** `DataSourceError: No such file or directory` for a
  file that existed. `workflows/task.py` already carried this exact fix (spec 36 D6a / TODO #40);
  `sources/` was never swept. Also covers all three `sources/mpc` call sites. **Blocking — Phase 1
  could not run without it.** 3 sibling sites still bypass the seam → **TODO #47**.
- **TODO #49 CLOSED — `run_aml_download` stops ignoring per-source arguments.** (a) creds
  (`creds_url`/`vault_url`/`secret_name`) are now a hard preflight error for anonymous
  `source="mpc"` — previously accepted and dropped, so an MPC run wrapped in the run-book's
  `blob_creds()` staged the CDSE keys on blob for the whole run **unread**. (b) `max_tiles` is now
  enforced **driver-side for both sources**: `sources/mpc.py:351` raises above the cap locally while
  the AML path dropped it entirely, so the same call meant different things per runner (breaks
  spec 36 D3). MPC counts **distinct MGRS tiles**, not shard rows (`n_tiles = assets / len(bands)`).
  Live consequence: the 576-tile Phase 3 now **fails fast** under the old `max_tiles=500`; run-book
  default raised to 700.

**Measurements (first real on-Azure fan-out data — detail in TODO #48):**
- **Fan-out works on the transfer, not (much) on the wall clock.** Phase 2 is the only controlled
  experiment (same 964 assets, only `n_shards` varied): transfer **577.6 s → 113.7 s = 5.08×**;
  wall **699.6 s → 493.9 s = 1.42×**. Total work conserved (sum of shards 560.9 s ≈ 577.6 s serial)
  ⇒ no duplicated effort and **no per-node throughput collapse — MPC is not throttling us at n=8**.
  The gap is fixed cluster startup: ~380 s of the 8-shard wall, ≈ **+37 s per extra job**.
- **`n_shards=16` (Phase 3) is NOT evidence that 16 > 8** — no n=1 baseline for that workload and
  the script recorded no wall clock (now fixed in the run-book: it emits `wall_seconds` /
  `slowest_shard_seconds` / `driver_overhead_seconds`). Hint only: per-asset 0.704 s at n=16 vs
  0.582 s at n=8. **Optimal shard width is unmeasured**; the straggler spread collapsing 16.7× → 1.82×
  when shards got fatter points to *fewer, fatter* shards. Unresolvable until MPC reports bytes.
- **MPC reports `bytes_downloaded: 0` always** (its `DownloadResult` has no such field) ⇒ no MB/s
  anywhere, which is *why* the above stays open. Fix that first — TODO #48 item (1).

**Operational facts worth not re-deriving:**
- The **driver** needs blob access in every phase, not just the node. VPN off ⇒
  `ErrorCode:AuthorizationFailure` (that code = **network rules**; `AuthorizationPermissionMismatch`
  = missing RBAC). Confirmed: VPN was off, identical script passed once up.
- **`fs.rm(prefix, recursive=True)` on `abfss://` deletes every file and THEN raises**
  `DirectoryIsNotEmpty` (empty dir entries survive). Reads as "nothing happened"; the data is gone.
  **TODO #50, unfixed.** Don't clear prefixes — re-running is self-healing (idempotent skip +
  `TileCatalog.append` upserts by id).
- **The AML Environment must contain fsd itself** — the dispatcher submits a bare
  `python -m fsd.workflows.download …` with **no `code=` upload and no pip install**. The old
  run-book step built an image with no fsd in it and PASS-checked a `provisioning_state` field that
  does not exist in the environment schema. Rewritten as a **Docker build context** (`build.path` +
  `dockerfile_path`; `conda_file` structurally **cannot** carry a local wheel since it requires
  `image`, which is mutually exclusive with `build`) + a smoke job that imports fsd on a node.
  `az ml environment show` requires `--version`/`--label`; versions are auto-assigned, so
  `AZ_ENV_VERSION` is captured rather than hardcoded `:1`.

**Session takeaway:** three of the four code findings are the same shape — **an interface promising
something it does not deliver** (a url-accepting reader that isn't, a per-source signature that
isn't, a backend-agnostic `rm` that isn't). The synthetic suite was green throughout; every one of
these needed real blob paths and a real cluster to surface. Run-book defects caused two of the
operator's three mistakes (an unannotated CDSE-only `creds_url` next to an annotated `n_shards`; a
required-step-as-code-comment), so **run-book precision is a correctness concern, not polish.**

**COMMITTED (gate 5, done):** `6c322fd` "fix two interfaces that promised more than they delivered"
(code + tests + `CHANGES.md`) and `5df7088` "runbooks 36/37: fix what running them on the real
cluster exposed" (run-books + `PROGRESS.md`/`LIMITATIONS.md`/`TODO.md` #47–#50). **Both unpushed** —
`origin/main` is still `e76a8d5`. Run the `RECIPES.md` private-identifier sweep before any push.

- **⚠️ Private-identifier leak — found during the D5 review (2026-07-22), SCRUBBED FORWARD the same
  day.** PRE-EXISTING: introduced by the spec commit `3c5f26f`, not by the D5 delta. `PROGRESS.md`
  and `specs/37-download-on-aml.md` had named the **concrete** `rise` Key Vault and compute VM, and
  a **full sweep of every concrete value in `AZURE_INFRA_PRIVATE.md` against all git-tracked files**
  turned up one more, older hit: `runbooks/34-download-to-blob.md` named the concrete **storage
  account**. All are "concrete" values in that doc's placeholder table — `CLAUDE.md` forbids
  copying those into anything under `fsd/` (public MIT repo). Not credentials (resource names), but
  a hard-constraint violation, and `3c5f26f` was **already pushed**, so they reached GitHub.
  **Fix (user's call, 2026-07-22): scrub forward** — replaced with the placeholder form (`kv<proj>`
  + a pointer to `AZURE_INFRA_PRIVATE.md`) in a follow-up commit. **The names remain in git history
  (`3c5f26f`) and in the pushed remote** — deliberately accepted, no history rewrite. If that ever
  becomes unacceptable, the remaining lever is a rewrite + force-push. Post-scrub the sweep is
  clean — the only remaining matches in tracked files are `identityReference`/`prevent_destroy` in
  `AZURE_INFRA.md`, which are generic Azure Batch / Terraform API terms, not identifiers.
  **Lesson for future spec/PROGRESS writing:** a `ForbiddenByRbac`-style ops finding must be
  recorded with the *placeholder* name, never the concrete one, even when quoting a real error.
  **Re-run the sweep before any push** — see `RECIPES.md` ("Sweep tracked files for concrete `rise`
  identifiers").
- **D5 REVISED delta — IMPLEMENTED 2026-07-22 (Sonnet@medium, worktree `fsd-spec37-d5`, branch
  `spec37-d5-delta`), REVIEWED at Opus@high + MERGED `--no-ff` (`154aa70`) + pruned 2026-07-22.**
  Review found **no bugs and needed no fixes**: the exactly-one-creds-source classification was
  traced across all five input combinations (neither / KV-complete / KV-partial / blob / both — no
  gap: `vault_url`+`creds_url` with no `secret_name` correctly classifies as "both"); the
  `creds_arg` splice has correct arg boundaries; `run_roi`'s newly-optional `vault_url`/
  `secret_name` have no callers outside `main()` and the tests; the no-secret-in-job-spec assertion
  is non-vacuous (a leak of the creds JSON or `s3_secret_key` would trip it); §7 test 7b is fully
  covered; the runbook's Phase 0/3 edits match real APIs (`fs.rm` exists,
  `CdseCredentials.from_json` is blob-capable). Two non-blocking observations, deliberately not
  "fixed": `run_roi` itself does not re-enforce mutual exclusivity (with both set it silently
  prefers blob; with neither it fails inside `secrets.get_secret(None, None)`) — unreachable in
  practice since the dispatcher machine-generates exactly one arg group; and the runbook's Setup
  block still exports the now-unused `AZ_VAULT_URL`/`AZ_CDSE_SECRET_NAME` (intentional — the
  "swap back if you have a KV write role" path). All 6 checklist items landed against the
  merged code: (1) `run_aml_download`/`_aml_download_preflight` gained `creds_url: str | None`
  (kept `vault_url`/`secret_name`); preflight now requires exactly one CDSE creds source, erring on
  neither and on both. (2) `workflows/download.py` CLI gained `--creds-url`; `run_roi` uses
  `CdseCredentials.from_json(creds_url)` when given, else the existing KV path (`vault_url`/
  `secret_name` are now optional params). (3) The command builder emits `--creds-url <url>` xor
  `--vault-url/--secret-name`. (4) `_aml_download_preflight` resolves/parses/expiry-checks whichever
  source is supplied (blob via `from_json`, KV via `from_json_str(get_secret(...))`). (5) Tests: 5
  new (§7 test 7b CLI + dispatcher blob-path, preflight neither/both, preflight blob-resolve) —
  `tests/test_download_aml.py` 21→26 tests, suite 364→369 passed / 3 skipped, `ruff` clean. (6) Docs:
  `LIMITATIONS.md` (new plaintext-creds-on-blob row), `runbooks/37-download-on-aml.md` (Phase 0 now
  pushes local creds JSON to a `_secrets/` blob prefix instead of reading a pre-populated KV secret;
  Phase 1/3 use `--creds-url`; Phase 3 deletes the blob creds file after the run), `CHANGES.md` (new
  "D5 REVISED" subsection), `RECIPES.md` (blob `creds_url` alternative shown alongside KV). Invariant
  verified by test: no secret *value* in `job.command`/`environment_variables` on the blob path
  either — only the `creds_url` location.
- **⚠️ D5 REVISED 2026-07-22 (keep-both: blob-JSON creds fallback added; KV retained) — the decision
  record.** KV creds delivery (D5 as merged) is **operationally blocked**: no identity the operator
  can invoke holds a KV *write* role on the `rise` Key Vault (`kv<proj>`, `AZURE_INFRA_PRIVATE.md`) —
  the compute UAMI has read-only
  (`Key Vault Secrets User`), so it can read a secret but not create one. `az keyvault secret set`
  returned `ForbiddenByRbac` from both the driver laptop **and** the operator's `rise` VM (the VM call
  authenticated as the operator's own account, not the VM MSI — but the MSI is the same read-only UAMI).
  Getting write is a platform-admin action unavailable on the demo timeline. The operator **has** blob
  write. **Decision (user, keep-both):** CDSE creds may be delivered **either** via KV
  (`--vault-url`/`--secret-name`, unchanged) **or** via a blob JSON `--creds-url` (new fallback, used
  now), mutually exclusive. The blob path **reuses the existing `CdseCredentials.from_json(creds_url)`**
  (already blob-capable via `fs.open`, `cdse.py:82`) — no new read code. Recorded in the spec:
  **D5 REVISED** note (§3), re-resolved Open Q2 (§8), updated §4 ledger / §5 deliverable 5 / §7 test 7b,
  and the top status banner. **Implementation delta a Sonnet session must land against the merged code:**
  (1) `run_aml_download` gains `creds_url: str | None` (keep `vault_url`/`secret_name`); require exactly
  one CDSE creds source (preflight errs on neither/both). (2) CLI `workflows/download.py`: add
  `--creds-url`; `run_roi` reads via `from_json(creds_url)` when given, else the existing KV path.
  (3) Dispatcher command builder emits `--creds-url <url>` xor `--vault-url/--secret-name`. (4)
  `_aml_download_preflight` resolves/parses/expiry-checks whichever source. (5) Tests: add the §7 test-7b
  blob-path + neither/both validation cases. (6) Docs: `LIMITATIONS.md` (plaintext-creds-on-blob,
  delete-after-run), `runbooks/37-download-on-aml.md` Phase 0 (write creds to a `_secrets/` prefix) +
  Phase 3 (delete them), `CHANGES.md`, `RECIPES.md`. **Invariant to keep:** no secret *value* in the job
  spec on either path (`creds_url` is a location, like the ROI/dst args).
- **Opus@high review outcome (2026-07-22):** review holds up — **merged, no fixes needed.** §4's
  central claim verified directly against the diff: `sources/cdse.py::download` and
  `sources/mpc.py::download` bodies change by **zero lines** (every hunk in those two files is a pure
  addition + the one documented `cdse.py` docstring fix). The `run_aml` refactor
  (`_aml_submit_and_wait`, `_aml_preflight_common`) is **proven behaviour-preserving** by
  `tests/test_scale_runner.py` having a **zero diff**. D5 no-secret-in-job-spec asserted in code +
  test; D8 crash-resume limitation honestly in `LIMITATIONS.md` + TODO #46. Methods the runner leans on
  (`is_expired`/`require_s3`/`query_catalog`) are all real; the ISO-string timestamp a shard CSV
  round-trips is coerced back to tz-aware UTC by `catalog.append`. **364 passed / 3 skipped** on a bare
  `.[dev]` venv, `ruff` clean, re-verified on `main` post-merge.
- **Minor nits (non-blocking, not fixed):** (1) `config.CDSE_MONTHLY_QUOTA_GB` is defined but only
  referenced by a test — the runner uses a caller-supplied `remaining_quota_gb` instead (defensible:
  *remaining* ≠ *total*). (2) `workflows/download.py::main()`'s argparse layer has no smoke test (tests
  call `run_roi`/`run_shard` directly). (3) The refactor renamed the missing-status report key from
  `"shard"` to `"unit"` in `run_aml`'s no-status-file branch (no test depended on it). (4) MPC per-shard
  timeout is sized from whole-discovery GB, not the shard's byte share (D6 wording) — erring
  generous/safe. (5) D7 estimates via `query_catalog`×`APPROX_GB_PER_TILE` rather than the spec-named
  `plan_download` — equivalent.
- **Prune status:** merged `--no-ff` (`6b845fc`); **worktree + branch NOT yet pruned** — `git worktree
  remove` is blocked by a live lock (`claude bg-spare`, pid 42181) on
  `.claude/worktrees/spec37-download-aml`. Run `git worktree remove -f .claude/worktrees/spec37-download-aml
  && git branch -d worktree-spec37-download-aml` once that session releases it. **`main` push is
  pending** (push-only-when-asked).

- **`specs/37-download-on-aml.md` — download on Azure ML (P2), the download sibling of spec 36.** Runs
  the already-working download-to-blob (spec 34) as an AML job so the source→blob byte-flow is
  cloud-colocated, not relayed through the driver laptop. **Headline decision (D1): per-source dispatch
  shape** — **CDSE = one job** (its 4-connection cap is per-S3-credential, so fan-out can't help) and
  **MPC = fan-out across N nodes** (bytes come straight from Azure Blob → throughput scales with
  parallelism; `rise` is in MPC's region → intra-region, near-linear). MPC fan-out reuses spec 36's
  `shard_units`; CDSE reuses spec 34's unmodified `download(roi)`.
- **Secrets = Azure Key Vault (D5), not blob.** The compute identity already holds `Key Vault Secrets
  User` on the `rise` vault (`AZURE_INFRA_PRIVATE.md`), and the **same `AZURE_CLIENT_ID`** spec 36 D4
  sets authorises KV too — so zero infra ask, no secret on blob or in the job spec. New `fsd/secrets.py`
  (`get_secret`), `azure-keyvault-secrets` added to `[azure]`, additive `CdseCredentials.from_json_str`.
- **All 8 deliverables (§5) landed.** `workflows/download.py` (new, thin in-job CLI, `--roi`/`--shard`);
  `sources/mpc.py::discover_shard_rows`/`download_shard` (additive; `download()` untouched, signs
  **on the node** via a new lazy `_import_pc_sign`); `workflows/runners.py::run_aml_download`
  (per-source dispatch, D1/D2/D6/D7/D9) built on a shared `_aml_submit_and_wait` **factored out of**
  `run_aml`'s own submit/poll/aggregate/raise loop (pure refactor — `run_aml`'s 12 spec-36 tests still
  pass unchanged) and a shared `_aml_preflight_common` (cluster/environment/root checks, reused by both
  `_aml_preflight` and the new `_aml_download_preflight`); `api.download(runner="local"|"aml",
  runner_kwargs=...)`; `CommandJobLimits(timeout=...)` (D6, via a lazy `_import_command_job_limits`)
  sized by `runners._estimate_timeout_seconds`; docs (`AZURE_INFRA.md` §7 item 9, `LIMITATIONS.md`,
  `RECIPES.md`, `CHANGES.md`, `TODO.md` #46, the stale `cdse.py` remote+cog docstring fixed);
  run-book `runbooks/37-download-on-aml.md` (Phases 0–3).
- **All tests (§7) pass, including non-vacuousness (test 8).** New `tests/test_download_aml.py` — 20
  tests: the CLI's two modes (D3/D9); `mpc.download_shard` signs on the node + reuses
  `_transfer_and_stamp_one`; CDSE submits **exactly one** job at both 1 and 37 discovered tiles (D1,
  non-vacuous across tile counts); MPC shards a discovered asset list into N jobs and the shard CSVs
  partition the asset list (reusing `shard_units`, non-vacuous); job spec carries `AZURE_CLIENT_ID`
  (D4), `limits.timeout` (D6), and the KV `vault_url`/`secret_name` **without any secret value**
  (D5); raises on a Failed job and on `circuit_tripped: true` even when AML itself reports Completed
  (D9); `api.download` accepts `runner="aml"` (threads `runner_kwargs`) and rejects unknown runners;
  `_aml_download_preflight` (D7) refuses empty discovery / unwritable root / an unparseable or
  expired KV secret, and warns (doesn't block) on a CDSE quota-exceeded estimate; `fsd.secrets.get_secret`
  is mockable without the `[azure]` extra. **Full suite: 364 passed / 3 skipped** (baseline 343/3),
  `ruff check src/ tests/` clean, **on the bare `pip install -e ".[dev]"` venv** — no test needs
  `azure-ai-ml`, `azure-keyvault-secrets`, or `planetary-computer` (a new `mpc._import_pc_sign` lazy
  handle mirrors `runners._import_aml_command`'s injection-boundary pattern for exactly this reason).
- **§4's reuse ledger held**: `sources/cdse.py::download` and `sources/mpc.py::download` change by
  **zero lines** (verified: only new functions were added, no existing lines touched);
  `storage/*`/`datacube/`/`raster/`/`catalog/` untouched. `runners.py`'s two shared-helper
  refactors (`_aml_submit_and_wait`, `_aml_preflight_common`) touch `run_aml`'s internals but not its
  signature or observable behavior — its own tests needed no changes.
- **Open, accepted for v1 (D8, not blocking):** a job that crashes mid-run loses its un-pushed local
  scratch, so a fresh-node resume re-downloads the unpushed remainder rather than seeing COGs already
  on blob (spec 34's push is whole-run, not per-file). Logged in `LIMITATIONS.md`/`TODO.md` #46;
  cheap for MPC (only the crashed shard's slice re-runs), costs re-downloaded bytes for CDSE.
- **Merged to `main`** (`6b845fc`, `--no-ff`) after the Opus@high review above; worktree/branch prune
  and the `main` push are the only pending items (see **Prune status** at the top of this section).

## ⭐ SPEC 36 **IMPLEMENTED + REVIEWED + MERGED to `main`** (Sonnet@medium impl 2026-07-22; Opus@high review + merge 2026-07-22). **→ NEXT: the user runs `runbooks/36-aml-runner.md` Phases 1–3 on the real cluster.**

- **Opus@high review outcome (2026-07-22):** the §4 reuse ledger and §5 deliverable table hold; the
  §3 invariants (D3 inv 1 `task.py` unchanged; D4 `storage/azure.py` unchanged; atomic-publish
  ordering metadata-before-datacube) verified against the diff. **One real defect found + fixed**
  (commit `89aeb9b`) — the implementing session's own "known open question": three `run_aml` tests
  called the real `azure.ai.ml.command(...)`, so `pytest -q` was RED on the canonical
  `pip install -e ".[dev]"` venv (the `[aml]` extra had silently become a *test* dependency,
  violating §7 "No test may require Azure"). Fixed by indirecting the sole `command` import through
  `runners._import_aml_command()` and injecting a `fake_aml_command` fixture; the AZURE_CLIENT_ID
  pin now runs on every install. **343 passed / 3 skipped on a bare `.[dev]` venv** (no `[aml]`),
  ruff clean. Branch `worktree-spec36-scale-runner` merged to `main`; worktree pruned.

- **All 11 deliverables (§5) landed.** `pyproject.toml` `[aml]` extra; `fsd.storage.fs.rename`
  (the atomic-publish primitive); D7 atomic-rename publish + skip-if-final-exists
  (`datacube/builder.py::_save_npy_atomic`, `workflows/task.py::run_task`'s first line); the
  Snakefile's sentinels moved to node-local scratch and its remote-`export_folderpath`
  `RuntimeError` removed; `workflows/shard.py` (new, thin, D3 invariant 2); `workflows/runners.py::
  run_aml` (shard → submit → wait → aggregate → raise, D2/D3/D9/D10); `api.py`/`workflows/
  create_datacube.py` accept `runner="aml"` end-to-end via a new `runner_kwargs` dict; D6a's three
  geometry I/O sites (`setup`'s ROI read + per-unit write, `run_task`'s geometry read) now go
  through `fsd.storage` + `BytesIO`/`to_json()`, closing TODO #40; docs (`AZURE_INFRA.md` §7,
  `LIMITATIONS.md`, `TODO.md` #40/#41 both closed, `RECIPES.md`, `CHANGES.md`); run-book
  `36-aml-runner.md` (Phases 1–3; Phase 0 stays as-is, already green).
- **§4's reuse ledger held**: `workflows/task.py` is byte-for-byte unchanged except its new
  first-line skip-if-final-exists check (D3 invariant 1's spirit — no *pipeline* logic moved);
  `datacube/`, `raster/`, `bands/`, `catalog/`, `sources/` untouched except `datacube/builder.py`'s
  save step (atomic publish, D7) and `catalog/`/`sources/` are genuinely untouched;
  `storage/azure.py` untouched (D4 stayed an env var, not code); `azure-ai-ml` is imported lazily
  **only** inside `runners.py::run_aml` (verified: `import fsd` succeeds with `azure.ai.ml` import
  blocked via a `sys.meta_path` finder).
- **All 9 tests (§7) pass**, plus a non-vacuousness check (test 8) and a couple of split-out
  variants — **12 new tests total** in `tests/test_scale_runner.py`. Full suite: **343 passed / 3
  skipped** (baseline was 331/3 at handoff), `ruff check src/ tests/` clean. No test touches Azure —
  the AML client is a hand-rolled fake (`_FakeMLClient`) injected at `run_aml`'s `ml_client=`
  boundary, and (after the review fix `89aeb9b`) the job-builder `azure.ai.ml.command` is faked via
  the `fake_aml_command` fixture, so **the suite passes with the `[aml]` extra absent** — it is a
  pure runtime dependency, never a test one.
- **D4 implemented as designed, no shortcuts**: `run_aml` takes `identity_client_id` as a required
  caller-supplied parameter (never hardcoded — a concrete `rise` identity id has no business in a
  public repo) and sets it as the job's `AZURE_CLIENT_ID` env var; test 5 pins that nothing else in
  `fsd/` would explain why it's there.
- **~~One deliberate design call beyond the spec's literal wording~~ → RESOLVED at review (`89aeb9b`).**
  The implementing session kept `azure.ai.ml.command(...)` running for real in tests (asserting on a
  real `Command`'s `.environment_variables`), which made the `[aml]` extra a test dependency and
  turned `pytest -q` red on a bare `.[dev]` clone. The review moved the job-builder behind
  `runners._import_aml_command()` (still exactly one lazy import site in `run_aml`, D3 inv 3 intact)
  and faked it in tests via `fake_aml_command`; test 5 now asserts on the kwargs `run_aml` passes —
  which *is* the run_aml behaviour being pinned — rather than on the SDK's Command class.
- **Not done in this session (by design — Claude never runs networked/pipeline scripts,
  `CLAUDE.md`):** Phases 1–3 of `runbooks/36-aml-runner.md` (one shard, resume, real fan-out on the
  actual `rise` cluster) and building the AML Environment (D5) for real. Both are runbooks for the
  user.

## ⭐ SPEC 36 **SIGNED OFF** + fork resolved → AML + Phase 0 green on the cluster (2026-07-21, Opus@high). (superseded by the entry above — implementation is done)

- **✅ `specs/36-scale-runner.md` SIGNED OFF (user, 2026-07-21).** Design is frozen; implementation
  has not started. Read the spec, not this entry, for the design — §3 has D1–D10, §4 is the reuse
  ledger, §5 the 11 deliverables, §7 the 9 tests.
- **Sign-off decision on §8 Q4: TODO #40 is fixed INSIDE spec 36**, not as a prerequisite commit.
  Spec gained **D6a** (three geometry I/O sites → `fsd.storage` + `BytesIO`: `setup`'s ROI read,
  `setup`'s per-unit geometry write, `run_task`'s geometry read), **deliverable 11**, and **test 9**.
  It stopped being deferrable because a cluster node has no `shapefiles/` checkout. Per spec 31 §6's
  audit these are the *last* raw-path I/O sites, so TODO #40 closes outright. **The guard that
  matters: the existing local-path geometry tests must pass unchanged** — the risk is a local
  regression, not a missing feature.

- **✅ Phase 0 identity smoke GREEN** (`runbooks/36-phase0-identity-smoke.md`, AML run
  `mighty_seal_21kp83tsv7`). **fsd ran on an AML cluster node, unmodified**: the wheel built from the
  working tree installed and imported, `fsd.storage` round-tripped npy+text on `rise` blob, and
  `fsd.raster.rio_open` streamed a real MGRS-tile COG over `/vsiadls/` (EPSG:32633, 10980², uint16).
  The token's `xms_mirid` proves **the compute identity** answered — the same UAMI P1 used.
- **The negative control failed, which is the good outcome: D4 is load-bearing.** With
  `AZURE_CLIENT_ID` removed, the bare `DefaultAzureCredential()` cannot get a token at all
  (`ManagedIdentityCredential: Expecting value: line 1 column 1` — IMDS won't guess among
  user-assigned identities). **Shipping without that env var would have failed every blob read on
  the cluster at runtime.** The control is why we know this rather than assume it.
- **Also settled:** an AML job needs **no `identity:` block** (spec 36 §8 Q2 closed — a plain command
  job already runs as the cluster UAMI); D5's premise (install a built wheel, let AML build the
  environment) is demonstrated, not just argued.
- **One honest gap:** the COG window read came back all-zero (tile top-left corner — almost certainly
  genuine granule-edge nodata). So "streamed successfully" is proven; "streamed *real pixel values*"
  is not. Phase 1 covers it by construction; recorded in spec 36 §6 rather than glossed.

- **`specs/36-scale-runner.md` written, awaiting sign-off.** 10 decisions (D1 backend, D2 shard
  granularity, D3 the `runner=` seam + 4 invariants, D4 node identity, D5 environment, D6 layout,
  D7 idempotency, D8 driver host, D9 telemetry, D10 preflight), a **reuse ledger** (§4) that makes
  the "no new pipeline code" claim checkable at review, 10 deliverables, a 4-phase validation plan,
  8 synthetic tests, 6 non-blocking open questions, and per-source credit (§9).
- **The headline: `workflows/task.py` must not change at all** (D3 invariant 1) — if it needs to,
  the design is wrong. `storage/azure.py` doesn't change either (see D4 below). The cloud runner
  only shards a work list and launches the *existing* local Snakemake runner inside each job.
- **D4 was the near-miss.** The AML cluster has **only** a user-assigned identity, and a UAMI is
  never selected implicitly — so a bare `DefaultAzureCredential()` (what `storage/azure.py` does)
  would have failed *silently on the cluster*, after P1 "proved" blob access. Both MS docs point at
  a code change; reading `azure-identity` 1.25.3's source **in this venv** showed
  `DefaultAzureCredential` already defaults `managed_identity_client_id` to `AZURE_CLIENT_ID`, so
  the whole fix is **one env var the dispatcher sets** — config, not code, exactly on-theme. Phase 0
  of the run-book validates it before any runner code is written.
- **D7 closes TODO #41's second half as a side effect:** Snakemake's sentinels move to node-local
  scratch (they are one invocation's bookkeeping), the durable resume signal becomes the artifact's
  own existence on blob, and publishes go temp→atomic-rename. So **the local runner gains blob
  support** and the Snakefile's hard `RuntimeError` on a remote `export_folderpath` can be deleted.
- **TODO #40 (ROI geometry via `fsd.storage`) is now blocking**, not deferred — a cluster node has
  no `shapefiles/` checkout (spec 36 §8 Q4: fix inside this spec or as a prerequisite commit?).

- **The Batch-vs-AML fork closed by measurement, not argument.** `runbooks/36-runner-fork-probe.md`
  (new, read-only, green 2026-07-21) ran against a **decision rule registered before the numbers
  were seen**. It fired on one fact: the `rise` Batch account's **`dedicatedCoreQuota` is 6** against
  a **64-core** pool VM — Batch cannot allocate a single node (low-priority quota is 6 too, so no
  spot escape). Meanwhile AML **`cluster-<proj>-d16`** is provisioned at **32 nodes × 16 vCPU = 512
  cores**, family quota 6400, and — the clincher — carries **`UserAssigned` = the project compute
  identity**, i.e. *the same UAMI spec 31 already proved reads/writes `rise` blob*. No new auth path,
  no RBAC ask, no re-spike. Evidence table: `AZURE_INFRA.md` §3.1; concrete values (names/IDs/quotas)
  in the workspace-root private doc.
- **Batch DROPPED, not deferred (user).** Strict YAGNI — we are *not* filing the quota request. The
  seam is already evidenced by two live backends (local Snakemake ↔ AML). `AZURE_INFRA.md` §3.1 is
  the record of *why*: **quota, not architecture** (the pool was otherwise fully prepped —
  DockerCompatible, DSVM image, start task, ACR pre-wired with the compute identity).
- **Two decisions locked before any drafting:** (1) **granularity** — one dispatched unit = a
  **shard of `input.csv`**, executed by the *existing local Snakemake runner* inside the job, so the
  cloud runner only shards a work list and launches proven code (this also killed the
  `max_tasks_per_node` infra ask); (2) **spec numbering** — the runner spec is **`specs/36-scale-runner.md`**,
  not an edit to the signed-off `specs/10-storage-and-scale.md` (10 defines the *seams*; 36 is the P2
  design against them).
- **⭐ P2 now needs ZERO infra asks and no container build.** Both were Batch requirements: the quota
  bump + `max_tasks_per_node` are moot, and AML builds/versions the job environment itself (an image
  becomes an optimization, not a gate; `az acr build` is available server-side if wanted). The
  project's "first infra proposal" is deferred indefinitely.
- **§7.7 idempotency settled from primary docs** (backend-independent, so bankable now) —
  `AZURE_INFRA.md` **§8.1**: ADLS Gen2 rename is **atomic on an HNS account** and can be made
  fail-if-exists via `If-None-Match: "*"`, so **`done.txt` sentinels get replaced by write-temp →
  atomic-rename-to-final**, with the final path's existence as the resume check — no lease, no lock,
  no consistency window. And Azure retries a task on node-recovery events **independently of
  `maxTaskRetryCount`, even when it is 0** ⇒ idempotent units are mandatory, not merely prudent.
- **ROADMAP §5.0's locked target widened (user):** "on Azure **Batch** at scale" → "**on Azure at
  scale**", `runner="batch"` → `runner="aml"`. The locked promise is *the seam*, not a product name;
  a footnote records why Batch was displaced so the history isn't lost.
- Docs updated: `ROADMAP.md` §5.0 + P2/P4 rows, `AZURE_INFRA.md` §3.1/§6.1/§8/§8.1, `LIMITATIONS.md`
  (Scale/cloud), `TODO.md` #41, the private doc's measured-facts table. **Nothing committed.**
- **Open, carried into spec 36:** which ACR the AML workspace builds environments into; whether an
  AML job must declare `identity: managed` to run as the UAMI rather than the submitter; whether the
  AML control plane is reachable off-VPN. None blocks the design.

- **The target (user, 2026-07-21):** *a researcher runs the same fsd pipeline on **Azure Batch at
  scale**, where `runner="batch"` / `storage="abfss://…"` is configuration, not a rewrite.*
  Audience = **a researcher who would actually use fsd** (self-serve bar). Written up as
  **`ROADMAP.md` §5.0** — that section, not this entry, is the canonical statement.
- **Everything local is done and proven** (P0→P0.9 on real data); **P1's storage half is proven**
  (runbooks 31 + 34-download-to-blob green). **The single missing piece is the runner.**
- Ordered path: (1) decide **Batch vs AML** — still open, gates the spec; (2) **write spec 10**,
  settling `AZURE_INFRA.md` §7's remaining questions; (3) **container image + ACR** (the largest
  genuinely new build); (4) **implement the runner seam** (+ the local Snakemake sentinels'
  blob-unsafety, TODO #41); (5) **infra ask** (quota / `max_tasks_per_node`).
- ⚠️ **Correction made while preparing this handoff — no spike is needed first.** I had told the
  user to start with a GDAL/VSI-under-MSI spike; that was **wrong**. §7.3 was stale: spec 31
  already solved and *proved* it on real Azure (`fsd.raster.rio_open` → `/vsiadls/` + fresh
  `AZURE_STORAGE_ACCESS_TOKEN`; runbook `31-p1-datacube-on-blob.md` green 2026-07-18). Marked
  resolved in `AZURE_INFRA.md` §7.3/§8. The residual unknown is narrower and belongs to **P4**:
  GDAL *writes* to blob (inference-output COGs) — `rio_open` raises on a remote `mode="w"` by
  design (TODO #39). **P2 is design + build, not discovery.**
- **New: `LIMITATIONS.md`** — a one-page, user-facing **index** of what fsd cannot do today, with
  a "trigger to fix" per row. Deliberately an index, **not** a fifth register: detail stays in
  `TODO.md`/`DROPPED.md`/`BUGS.md`/`specs/`. Working principle the user set: **YAGNI/DRY/KISS — we
  plug a limitation when we actually hit it**, not in advance.
- **Spec 35 committed** (`f486c3c`, 24 files) — see the two entries below for the implementation
  and the review. Notebooks deliberately left out of the commit (`CLAUDE.md` preference).

---

## ✅ SPEC 35 **REVIEWED + ACCEPTED** (2026-07-21, Opus@high). No defects found in the implementation; 4 small corrections applied in place, 1 design gap logged as TODO #45. `pytest -q` **331 passed / 3 skipped**, `ruff` clean. Committed as `f486c3c`.

- **Verified against the spec, not just re-read.** §9's 10 deliverables all land; §8's 11 test
  requirements all have a real test. **Independently re-derived the two claims the design rests
  on** (rather than trusting the passing suite): (1) `pd.concat`'s attrs rule is *all inputs must
  agree* — `concat(non-empty, empty).attrs == {}` in this venv — so `TileCatalog.append`'s
  **explicit** re-stamp is **required**, not merely the safer of two options (the implement
  session's handoff note claimed "empty attrs on one side is fine"; that is wrong, and the
  implementation is right); (2) the filter chain (boolean mask → `.copy()` → column assign) *does*
  propagate attrs, so `TileCatalog.filter` needs no re-stamp. Also confirmed the stamped write
  keeps SNAPPY + a valid `geo` key (no compression/format drift), and that `flatten_catalog`'s
  output is a **fresh** GeoDataFrame with no `fsd:source_path`, so §5a can never double-raise on a
  `flatten → build` chain.
- **Mutation-tested the §8.2 non-vacuousness claim myself** rather than taking the implementer's
  word: forcing `build_datacube` to ignore the resolved declaration fails the three-hop test
  (`IndexError` — the S2 default's `reference_band="B08"` selects no images); forcing
  `flatten_catalog` to do the same fails it *and* the §5a raise test. Both probes reverted;
  `builder.py` carries no leftover trace.
- **pystac deviation accepted as semantically equivalent.** `ItemAssetDefinition` +
  `Classification.create(value=…, name=…)` is forced by pystac 1.15.1 (the wrapper is deprecated;
  `name` became required in the classification extension's **v2.0.0**). On the wire the Collection
  gets the right `stac_extensions` entry, `item_assets.SCL.classification:classes`, and
  `fsd:declaration`; re-stamping is idempotent (no duplicate classes or extension URLs).
- **Corrections applied (Opus, in place):** `declaration.py`'s module docstring still advertised the
  retired `attrs["declaration"]` key; `from_json`/`_mask_spec_from_json` raised an incidental
  `TypeError`/nonsense message on a non-object `mask_spec` (now a clear `ValueError`, +1 test);
  `restamp_cli`/`RECIPES.md`/`CHANGES.md` called the re-stamp a "footer-only rewrite" when it is a
  full read+re-write of the catalog Parquet (still sub-second, imagery untouched — wording fixed);
  added a `peek_parquet_attrs` test on a `memory://` path, since `TileCatalog.append`'s conflict
  check runs it on **every** append including against an `abfss://` catalog and was only covered
  locally (verified working on a non-local fs).
- **Logged, not fixed: TODO #45** — the STAC `classification:classes` mirror lists only the *masked*
  subset of SCL values with placeholder names (`name="3"`), so spec 35 §7's "legible to any
  STAC-aware tool" only half-lands. Schema-valid and harmless (the Parquet footer is authoritative;
  nothing reads the mirror), but fixing it properly means adding class *names* to `MaskSpec` — a
  spec-34 §2a field change, hence a TODO rather than a review-time edit.
- **Non-scope respected:** the diff touches no `[G2]` native-grid path, no new `mask_type`, no
  `Source` ABC (#11), and re-stamps none of the four on-disk catalogs.

---

## ✅ SPEC 35 (declaration persistence, TODO #42) **IMPLEMENTED** (2026-07-21, Sonnet@medium), against the signed-off spec's §9 deliverable table. Reviewed + accepted by Opus@high the same day — see the entry above. Tree left dirty, nothing committed (`CLAUDE.md`: commit only when asked).

- **All 10 deliverables done:** `declaration.py` gained `to_json`/`from_json`/`to_attrs`/
  `from_attrs` + `FSD_DECLARATION_VERSION`/`ATTRS_KEY`; `storage/fs.py`'s `write_parquet`/
  `read_parquet` gained generic `.attrs` <-> `PANDAS_ATTRS` footer preservation (+
  `peek_parquet_attrs` for a footer-only read) and `SOURCE_PATH_ATTRS_KEY` stamping/stripping;
  `catalog.py`'s `TileCatalog` gained `declaration=`/`.declaration`/the append conflict rule;
  `cdse.py`/`mpc.py` now stamp `S2_L2A_DECLARATION` at their one `catalog.append` call each;
  `datacube/builder.py` resolves via a shared `_resolve_declaration` helper (used by both
  `flatten_catalog` and `build_datacube`) that implements the §5a raise, and no longer puts the
  typed dataclass in `.attrs`; `catalog/stac.py` gained the Collection mirror
  (`classification:classes` + `fsd:declaration`) and `collection_to_declaration`; two new CLIs,
  `python -m fsd.catalog.restamp_cli` / `fsd.catalog.inspect_cli` (spec 35 §6).
- **Tests: 329 passed / 3 skipped** (baseline 294; net +35 — the TODO-#42 pin deleted, ~36 new
  tests across `tests/test_declaration.py` (new), `test_storage.py`, `test_catalog.py`,
  `test_datacube_builder.py`, `test_catalog_stac.py`, `test_restamp_cli.py` (new)). `ruff check
  src/ tests/` clean. The §8.2 three-hop end-to-end test was verified non-vacuous by temporarily
  forcing `build_datacube` to ignore the resolved declaration and confirming the test fails
  (`IndexError` — the wrong reference band has no images) before reverting.
- **Two existing tests needed fixing, not the code** (the handoff's predicted case): `_make_catalog`
  in `tests/test_workflows.py` wrote catalogs via `fs.write_parquet` with no stamp, which now
  correctly raises per §5a once read back through `run_task`'s `flatten_catalog` call — fixed by
  stamping `S2_L2A_DECLARATION` in the fixture, since those catalogs are S2-shaped.
- **No ambiguity required a spec re-interpretation.** One environment-only surprise not anticipated
  by the spec: pystac 1.15.1 deprecates the `ItemAssetsExtension` wrapper (top-level
  `Collection.item_assets` instead) and requires `Classification.create(value=..., name=...)`
  (`name` became required in the extension's v2.0.0) — used the current, non-deprecated API; no
  design decision was affected.
- Docs updated: `docs/adding-a-source.md` (the ingest step now documents stamping as required, and
  the resolution-order section points at §5a), `CHANGES.md`, `TODO.md` #42 closed, `RECIPES.md`
  (the two new CLIs), `specs/34-ingest-normalization-contract.md` status block.

---

## ✅ SPEC 35 (declaration persistence, TODO #42) WRITTEN + **SIGNED OFF** (2026-07-21, Opus@high). `specs/35-declaration-persistence.md`. Implemented same day, see the entry above.

**§5a locked as recommended (user, 2026-07-21): an unstamped catalog file RAISES**; a hand-built
GeoDataFrame keeps the S2 default. Consequence accepted eyes-open: the four known on-disk catalogs
(demo_e2e, mpc_baseline, the `rise` blob catalog, old per-cell slices) raise until re-stamped — a
millisecond footer rewrite, folded into TODO #44's re-ingest. The spec forbids the softeners
(grace period, env-var escape, "`satellite` looks like S2" heuristic) by name, since each recreates
the silent fallback being removed.

**⚠️ The gap is bigger than TODO #42 recorded — it is NOT latent on the production path.** TODO #42
called the missing declaration round-trip "latent today (both shipped sources *are* S2 L2A, so the
fallback is coincidentally correct)". True of the *value*, wrong about the *location*. There are
**three** write→read hops between ingest and the builder, and hop 2/3 is the **per-cell unit of
work**: setup writes a slice with `fs.write_parquet` (`workflows/create_datacube.py:88`), and
`run_task` reads it back in a **separate process** with `fs.read_parquet` (`workflows/task.py:59`)
before calling `flatten_catalog` (`task.py:60`). In-memory `.attrs` cannot bridge a process
boundary even in principle. So **`run_task` — the one production caller of `build_datacube`, the
task Snakemake runs and Batch will dispatch — uses `S2_L2A_DECLARATION` unconditionally today, no
matter what ingest declared.** Spec 34's declaration-driven builder is, on the path that actually
runs, still hardcoded to S2. (Also found: *nothing* in the ingest path stamps a declaration at all —
hop 1 never writes one.)

**The spec's shape (7 decisions):** authority = the **catalog GeoParquet footer** (single artifact,
cannot separate from its data; same file-level key/value area GeoParquet's own `geo` key uses) —
sidecar JSON, STAC-as-authoritative, and a source registry all rejected with reasons; mechanism =
**generic `.attrs` preservation in the storage seam** (`fs.write_parquet`/`read_parquet`), because
that is the one choke point all three hops already pass through; versioned JSON schema; ingest
stamps + one-catalog-one-declaration conflict rule; **unstamped file ⇒ raise** (the §5a sign-off
fork, aligned with spec 34 `[G4]`) while hand-built gdfs keep the S2 default; a millisecond
**footer-rewrite migration** (`fsd-restamp-catalog`) so demo_e2e/mpc_baseline/the `rise` blob
catalog need no re-download; and an **additive STAC Collection mirror** using the standard
`classification:classes`.

**Two findings from cross-validation that changed the design:** (1) geopandas **PR #3597 merged
2025-10-30** — a future geopandas *will* serialize `.attrs`, under **`PANDAS_ATTRS`**, so fsd uses
that same key/encoding to converge with upstream rather than fork a second convention; (2)
consequently **a dataclass must never sit in `.attrs`** — verified locally that JSON-encoding attrs
containing a `SourceDeclaration` emits "Could not serialize … defaulting to empty attributes" **and**
raises `TypeError`, i.e. a routine `pip install -U geopandas` would break fsd's write path under the
current design. Blast radius of the change is small: `build_datacube`/`flatten_catalog` have exactly
**one** production call site each (`workflows/task.py`) plus `tests/test_datacube_builder.py`.

**→ NEXT: Sonnet@medium implements** against `specs/35` §9's deliverable table, baton
`runbooks/HANDOFF-spec35-implement.md` (in the **repo**, not `/tmp` — see the lesson below), then
Opus@high review. No runbook needed — nothing credentialed, networked, or visual; the §6 migration
folds into TODO #44's re-ingest.

**🧭 Process lesson (2026-07-21): a `/tmp` handoff baton did not survive.** This session was pointed
at `/tmp/fsd-handoff-todo42-declaration-spec.md`, which did not exist anywhere on disk. State was
reconstructed from `PROGRESS.md` + `TODO.md` #42 with no loss — **because both were current**, which
is the spec-24 D6 design working as intended (durable state in `PROGRESS.md`/`TODO.md`/`specs/`; the
baton is ephemeral). Still: **write batons into `fsd/runbooks/HANDOFF-*.md`, not `/tmp`.**

## ✅ SPEC 34 FULLY VALIDATED — BOTH RUNBOOKS PASS (2026-07-21, Opus@high). **→ NEXT: spec 34 is closeable; TODO #38 done. Remaining follow-ups: TODO #42 (declaration round-trip, needs a spec amendment), TODO #43 (CDSE discovery retry), TODO #44 (re-ingest the pre-fix blob COGs).**

**Runbook `34-mini-mpc-cross-baseline` PASSED — §1e cross-baseline serving proof done, and it
found + fixed a real correctness bug.** Registering two datetime-filtered searches (2021-only /
2022-only) in the mini-MPC stack and viewing all four `{year}×{unscale}` XYZ layers in QGIS:
**`unscale=true` matches across the 2022-01-25 baseline cutover** (harmonized), **`unscale=false`
shows the raw seam** (2022 ~33% brighter). Plus the numerical proof: each item's stamped offset is
conditional per baseline (2021 → `0.0`, 2022 → `-0.1`). §1e's claim — fsd's ingest fills the offset
gap MPC can't, and the serving path applies it — is established three ways (serving render, per-item
tags, spec-32's end-to-end numerics).

**🐛 THE BLACK-TILE BUG (found by running the runbook; fixed + pushed `c2bf1f1`).** `unscale=true`
first rendered **every tile pure black**. Root cause = a viewer-tag **unit mismatch**: spec 34 §1a
mandates `scale=1/10000` (so `unscale` yields physical reflectance), but ingest stamped the offset in
**DN units** (`-1000`) alongside that reflectance scale. A viewer computes `DN*scale + offset =
DN/10000 - 1000 ≈ -1000` for every pixel → clamped to 0 → black. **The datacube science path was never
affected** (it reads raw DN and applies the offset itself from the DN-unit catalog column); only the
viewer/`unscale` path (§1b/§1e) was wrong. **Fix:** stamp the offset in reflectance units
(`offset * S2_REFLECTANCE_SCALE = -0.1`) to match the scale — in the GDAL tag (`mpc.py`, `cdse.py`)
and STAC `raster:bands` (`stac.py`); `items_to_rows` divides the scale back out so the catalog's
DN-unit column round-trips as `-1000` (else a datacube from a re-imported catalog would be ~1000 DN
high — regression of #10/#30). **2 new regression tests** the old suite structurally could not catch:
one asserts the actual `unscale` arithmetic (`DN*scale+offset == reflectance`, `0≤x≤1`) — the prior
"GDAL tag ↔ STAC agree" test passed because **both carried the same wrong value** (an agreement test
can't catch a shared error); one pins the DN round-trip. 3 existing tests that hard-coded the DN offset
on the tag were corrected. **294 passed / 3 skipped, ruff clean.**

**This is the third consecutive time running a runbook found the defect, not code review** — spec 32,
the review pass, now this. And this one was caught **only by eyeballing a render in QGIS** (the user's
"visual validation is essential" principle earning its keep); two `code-review` passes, spec
cross-validation, and both prior runbooks all missed it because nothing executed `unscale` on a real tile.

**Runbook 2 had SIX documented defects, all found by running it** — now fixed by a **full rewrite**
(`runbooks/34-mini-mpc-cross-baseline.md` is self-contained, no more runbook-30 delegation): (1) cost/time
understated (~10 GB shown as "a handful of small COGs" — the full-tile-asset error spec 32's v1 also made);
(2) `max_tiles` guidance pointed at the expensive knob (raise cap vs narrow window — the window was
narrowed to 5-day, in `34_mixed_baseline_slice.py`); (3) step-2 stac-geoparquet export is a dead-end
(not consumed by the loader, needs a different venv); (4) the compose `/data` mount defaults to the
spec-30 Austria data and must be repointed **and the container recreated**; (5) `register_and_url.py` is
a categorical crop-map URL builder that structurally cannot render RGB `unscale` — the tile URL must be
built directly against titiler; (6) example `rescale` wrong for the data. Also **rewrote
`demos/mini_mpc/README.md`** from demo_e2e-specific to dataset-agnostic, with an operations cookbook
(swap dataset, register/filter searches, hand-built RGB tile URLs, smoke-test, inspect, delete
collection/searches, wipe/reset).

**⚠️ Consequence for runbook 1's blob artifacts → TODO #44.** The `rise` blob COGs from
`34-download-to-blob` were ingested **before** `c2bf1f1`, so they carry the wrong offset tag and would
render black under `unscale`. Runbook 1's PASS still holds for what it verified (bytes/tag-present/abfss);
only the tag *value* is wrong. Latent (nothing serves them); re-ingest before ever serving.

## ✅ RUNBOOK 34-download-to-blob PASSED, BOTH SOURCES (2026-07-20, Opus@high) — found + fixed a real spec defect (A1) on the way.

**Both legs PASS on the `rise` blob, verified on metrics (not the `pass` flag).** All six
`expected` booleans true for each source; the flag's own computation was checked and genuinely
ANDs all six + `catalog_rows > 0`, each derived from a real blob-side read — it *can* fail,
unlike spec 32's runbook v1.

| leg | files | catalog_rows | stac_items | verdict |
|---|---|---|---|---|
| **MPC** | 16 (B04+SCL × 8) | 8 | 8 | ✅ PASS |
| **CDSE** | 24 (B04+SCL+`MTD_TL.xml` × 8) | 8 | 8 | ✅ PASS |

Both sources independently agree on 8 granules for the same window/tile. The 16-vs-24 file
difference is by design — `_select_item_files` adds `MTD_TL.xml` per granule for CDSE; MPC has
no such asset. `gdal_offset_or_scale_tag_present: true` on the **CDSE** leg is the load-bearing
result: these are baseline-05.10 products, so the tag can only be there if the offset resolved
to −1000. **TODO #30/#10 is now closed for the CDSE path, proven against real data.**

**⚠️ The CDSE leg first hard-failed — a factual error in the signed-off spec, now Amendment A1
(`specs/34` §3a), implemented + pushed as `9eccc44`.** `_s2_radiometry.py` asserted that "CDSE's
STAC items carry the same `s2:processing_baseline` property, per the S2 STAC extension both
providers implement." **False for the endpoint fsd queries.** `config.CDSE_STAC_URL` is
`stac.dataspace.copernicus.eu/v1/`, and CDSE's v1 catalogue (Feb 2025) *removed the
satellite-specific `s2:` extensions in favour of a generic metadata model*. A live probe of 8
items: **no `s2:` keys at all**; baseline is in the STAC Processing extension's
**`processing:version` = `"05.10"`**, matching `N0510` in the product id. The extension defines
that field as *"the version of the primary processing software … for example, this could be the
processing baseline for the Sentinel missions"* — its documented purpose, not a coincidence.
Fix = `_BASELINE_PROPS` ordered lookup (`s2:processing_baseline` → `processing:version`), first
hit wins, hard-fail preserved when neither is present. Implemented Sonnet@medium in a parallel
session against `runbooks/HANDOFF-spec34-A1-implement.md`; merged + verified here (**289 → 292
passed / 3 skipped**, ruff clean). **The code was never wrong — it faithfully implemented a spec
that stated an unverified external fact.** Notably the CDSE docs do *not* publish item property
schemas, so a docs-only cross-validation could not have caught this; the live probe was
necessary. That methodology point is recorded in §3a's per-source credit.

**Runbook 1 had five step-0 defects, all found by running it** (fixed in `9eccc44`): the
`shapefiles/` ROI resolves to a *sibling of the repo* so `git clone` cannot supply it; SSH clone
URL on a VM with no deploy key; `[dev,azure]` missing the `mpc` extra; a stale `catalog_rows: 3`
example readable as a criterion (it is context — only the six booleans are criteria); and
`_verify_on_blob` calling `pystac.Catalog.from_file` **without** `_StorageStacIO` — the only
call site in the repo bypassing the storage seam, which broke verification against `abfss://`
hrefs. Common cause: step 0 was written assuming the author's laptop. The runbook now also
documents the **AML compute instance** path (SSH from the public internet is disabled on this
tenant; an AML compute instance is inside the VNet and reaches the firewalled storage), the
credential-upload warning (**not** `~/cloudfiles` — that is the shared workspace file share),
and the transient CDSE discovery error.

**New: TODO #43** — `_search_items` has no retry/backoff while the download layer right below it
has a full retry ladder; one transient `ConnectionDoesNotExistError` mid-pagination killed a run
before any download. Re-running worked. Low priority, contained fix, matters more for unattended
Batch runs.

**Workspace:** worktree `spec34-a1` merged file-by-file (verified byte-identical), removed, its
branch deleted — **one checkout again**. Stale merged branches `spec32-mpc-implement` /
`specs-28-29-impl` still exist; cosmetic.

**⚠️ A1 is drafted + implemented but NOT user-signed-off.** It was written and merged inside one
session under time pressure of a live runbook. The decisions worth a second look: resolution via
`processing:version`, `s2:` winning a tie, and *no* product-id regex fallback despite `N0510`
always being present.

## ✅ SPEC 34 REVIEWED + FIXED (2026-07-20, Opus@high) — review pass closed.

**Workspace consolidated + SHIPPED:** the spec-34 work was living in the git worktree
`.claude/worktrees/spec34-ingest-normalization`. It has been **merged into `main`'s working
tree and the worktree + its branch removed** — there is now **one** checkout — then
**committed and pushed to `origin/main` as `0dd5e5a`** (2026-07-20, at the user's request;
only the kept-out notebooks remain uncommitted). A fresh `git clone` on a VM therefore has
spec 34 with no checkout step, which is why `runbooks/34-download-to-blob.md` step 0 no
longer names a branch. The `PYTHONPATH` gotcha from the previous handoff is **gone**:
`fsd/.venv`'s editable install points at `main`'s `src/`, which is now the only `src/`.
Plain `.venv/bin/python -m pytest -q` works.

**Verified independently this pass** (not taken on trust from the implement session):
- `pytest -q` → **289 passed / 3 skipped**, `ruff check src/ tests/` clean.
- All of spec 34 §5's deliverables are present and the implementation is sound — the
  earlier two-axis `code-review` found **no implementation defects**, and this pass found
  none either. The gaps were 2 style violations + §4 test coverage.

**Fixes applied:**
- **Standards (2 hard violations):** `catalog/stac.py::tile_catalog_to_items` had
  `from fsd import config` mid-function → hoisted to module top (verified no circular
  import: `config.py` imports only `os`). `sources/cdse.py::_push_scratch_to_remote` had
  `import glob as _glob` / `import shutil as _shutil` despite `shutil` already being a
  top-level import → now uses the top-level `shutil` + an unaliased local `import glob`
  (matching the file's existing pattern for rarely-used stdlib modules).
- **Standards (nits, done):** `stac.py::_media_type_and_roles` roles expression hoisted
  once instead of duplicated per extension; `stac.py::items_to_rows` moved the
  item-level `RasterExtension.has_extension` check out of the per-asset loop.
- **Standards (nits, deliberately skipped):** `raster/cog.py::stamp_or_reencode`'s
  duplicated `stamp_gdal_tags(...)` call (the duplication is load-bearing for
  readability of the try/fallback split) and `sources/mpc.py::download`'s 5-tuple `work`
  list (a real cleanup, but it touches the concurrency path — not worth the blast radius
  in a fix-up pass).
- **Spec §4 (+10 tests, 279 → 289):** low-DN survival on disk (parametrized 1/500/999/1000,
  `test_raster.py`); GDAL tag ↔ STAC `raster:bands` agreement driven through the *real*
  ingest + export path (`test_mpc.py`); plain-read-returns-raw-DN "no double-application"
  pin; nodata set-only-when-missing (both branches); the `[G1]` uint16 clip pinned as
  intended-not-a-bug with a §1f comment; and a `reference_band`-from-declaration test that
  proves the declaration is load-bearing by *grid shape* (10 m vs 20 m reference band →
  4×4 vs 2×2 cube) rather than by introspection.

**⚠️ One real gap found and logged — TODO #42 (the handoff underestimated this one).**
Spec 34 §2a's table puts the **mask spec** in "catalog/collection metadata" and §4 asks
that mask classes "survive write→read". They do **not**: the collection-level
`SourceDeclaration` rides on `GeoDataFrame.attrs["declaration"]`, and GeoParquet does not
persist `.attrs` — **verified**, a write→read returns `attrs == {}`, after which
`build_datacube` silently falls back to `S2_L2A_DECLARATION`. Per-row `offset`/`nodata` DO
round-trip (real columns), and roles are re-derived on every STAC export, so those parts of
§4 are genuinely satisfied. This is **latent today** (both shipped sources *are* S2 L2A, so
the fallback is coincidentally correct) but **silently wrong for the first non-S2 source** —
exactly the failure mode spec 34 exists to prevent. Not fixed here: closing it means
deciding *which artifact is authoritative* (STAC Collection vs. a sidecar), which needs a
spec-34 amendment, not a patch. Pinned meanwhile by
`tests/test_catalog.py::test_declaration_does_not_survive_catalog_roundtrip_todo_42`, which
fails loudly if the behavior changes in either direction.

**Verdict: shipped (`0dd5e5a` on `origin/main`) and ready for the runbooks.** TODO #42 does
not block either runbook (both are S2-only paths).

## ✅ SPEC 34 IMPLEMENTED (2026-07-20, Sonnet@medium) — ingest/normalization contract shipped.

Implemented to the signed-off spec (`specs/34-ingest-normalization-contract.md` §5). **`pytest -q` → 279 passed / 3 skipped, ruff clean** (up from 274 pre-spec-34; the fixtures that carried the retired `boa_add_offset` schema were migrated, not shimmed, per `[G4]`).

**What shipped:**
- **`fsd/catalog/declaration.py` (new)** — `SourceDeclaration`/`MaskSpec`/`S2_L2A_DECLARATION`. `build_datacube` resolves its declaration from an explicit `declaration=` kwarg, else `catalog_subset.attrs["declaration"]` (set by `flatten_catalog`), else the S2 default — every existing caller (`workflows/task.py`, `api.py`, `create_datacube.py`) is unchanged.
- **`fsd/datacube/builder.py`** — declaration-driven op-assembly (§2b): the mask/drop step runs only when the declared mask band is in the requested `bands` (closes **#35** — `bands=["B04"]` no longer raises); `mask_type≠"categorical_classes"` or `native_grid=True` raise `NotImplementedError` (`[G2]`/`[G3]`); nodata read from the catalog's `nodata` column, not `config.NODATA`; `_apply_boa_offsets`→`_apply_offsets` (reads `offset`, generic name).
- **`fsd/catalog/catalog.py`** — `boa_add_offset` column retired; `offset`+`nodata` replace it. **No back-compat**: `TileCatalog.read()` does not backfill a legacy catalog missing them (`[G4]`).
- **`fsd/catalog/stac.py`** — every raster asset gets `raster:bands` (offset/scale/nodata, pystac raster extension) + a role tag (`reflectance`/`mask`/`reference`) alongside `"data"`.
- **`fsd/raster/cog.py`** — new `stamp_gdal_tags`/`stamp_or_reencode` (the "cheap header-tag edit, GDAL-COG-reencode fallback" spec 34 §1a promised; needed `IGNORE_COG_LAYOUT_BREAK=YES` to actually stamp in place — GDAL refuses by default even for a header-only edit).
- **`fsd/sources/_s2_radiometry.py` (new, shared)** — `offset_for_item` (baseline→offset), used by both CDSE and MPC — closes **#30/#10** for CDSE.
- **`fsd/sources/cdse.py`** — `_convert_one` now stamps the GDAL tag after `to_cog` (free — it already re-encodes); the local-only guard is lifted via a local-scratch-then-batch-push strategy (`_push_scratch_to_remote`) reusing the entire existing local pipeline unchanged — **known limitation, documented**: not per-file-resumable against a remote root (TODO #31 still covers true streaming).
- **`fsd/sources/mpc.py`** — `_transfer_one`→`_transfer_and_stamp_one`: stamps tags after `fs.transfer`; local-only guard lifted via per-file local-scratch-then-`fs.put` (resumable, unlike CDSE's batch push).
- **`fsd/docs/adding-a-source.md` (new)** — the ingest/builder contract + field table + a CHIRPS-like worked example.
- **`fsd/runbooks/34-download-to-blob.md`** + `runbooks/scripts/34_download_to_blob.py` — cloud-VM-first, tmux cheat-sheet, git-clone (`[G5]`/`[G7]`); **`fsd/runbooks/34-mini-mpc-cross-baseline.md`** + `runbooks/scripts/34_mixed_baseline_slice.py` — local-copies §1e acceptance (`[G6]`), reusing spec 30's mini-MPC stack.
- **Living docs**: `TODO.md` (#10/#30/#35/#37 closed, #38 implemented), `CHANGES.md` (new spec-34 entry).

**Design choices made during implementation (not re-opening the spec, filling in mechanism):** offset/nodata are per-catalog-row (genuinely per-tile); role/mask-spec/reference-band/mosaic-method live in the collection-level `SourceDeclaration` object (attached to the flattened catalog via `.attrs`, not a parquet column) — matches the spec's §2a "catalog/collection metadata" wording for those fields vs. "catalog row" for offset/nodata. `ops.apply_cloud_mask_scl` gained a `mask_band="SCL"` parameter (default preserves old behavior) rather than a rename, to minimize blast radius on its existing direct tests.

**Not yet done (deliberately, per the handoff):** the two runbooks are written but **not run** — the user runs them and pastes back `_result.json`. A CDSE-to-blob run against a large slice inherits the batch-push limitation above; fine for the runbook's small slice.

## ✅ SPEC 34 (ingest / normalization contract) WRITTEN + SIGNED OFF (2026-07-20, Opus@high) — `specs/34-ingest-normalization-contract.md`. **→ NEXT: Sonnet@medium implements** (handoff `/tmp/fsd-handoff-spec34-implement.md`).

Promotes **TODO #38** (this is spec **34**). Re-opens **download-to-blob for all sources** (`stage → normalize → put` per source), standing on the proven P1 storage seam (spec 31). Interviewed → drafted → cross-validated (standing permission) → **grilled** (7 resolutions) → user sign-off, all in one Opus@high session. **No code written** (spec-first; implementation is a later Sonnet@medium session).

**The two locked decisions:**
- **Radiometry/encoding/nodata (§1).** Ingest stores **raw-DN COGs (lossless archive)** + declares the S2 processing-baseline BOA offset as **metadata in BOTH places**: the COG's **GDAL scale/offset tag** (required for the viewer — cross-validated that titiler/rio-tiler `unscale` honors **only** the internal GDAL tag, **not** STAC `raster:bands`; maintainer disc. #803) **and** STAC `raster:bands` (for the builder + interchange). **Not baked** (baking = permanent silent clip of real reflectance in (0,1000] + kills MPC's byte-copy). Payoff: a **single titiler-pgstac XYZ URL with `unscale=true` renders a mixed-baseline mosaic with no seam** — the driving requirement (MPC itself *can't* do this — it exposes no per-item offset, §1e). nodata guaranteed = 0 (MPC COGs sometimes omit it). **Retires the bespoke `boa_add_offset` column** → closes #10/#30. **⚠️ Honest scope (`[G1]`):** the **science datacube still clips** (uint16, offset applied before the median) — but consciously + recoverably (true DN on disk); `int16`/`float32` deferred to TODO #13.
- **Builder generalization / #35 (§2).** `build_datacube` becomes **declaration-driven** (option B — the artifact self-describes band roles / mask / reference / nodata / offset; no product registry, no `if source==`). Mask is **opt-out** behind a growable `mask_type` (categorical-classes only for now) → **closes #35**. Grid-topology for non-tiled sources (ERA5/CHIRPS) is **deferred to the ERA5 spec**, `NotImplementedError`-guarded (`[G2]`). Ships a **`docs/adding-a-source.md`** guide + a docstring DoD so a library user can add a source themselves.

**Grilling resolutions folded in (`[G1]`–`[G7]` tagged in the spec):** [G1] cube-clip honesty; [G2] grid-topology deferred; [G3] `mask_type` seam; [G4] **no legacy/back-compat — 74 GB Austria archive is disposable, data re-ingested under the new contract**; [G5] **cloud-VM-first runbook + tmux/detach-safety + Azure-noob hand-holding** (the "download-on-cloud, no hotspot" property comes from *running on a cloud VM*, not from writing-to-blob — Batch auto-dispatch is still P2); [G6] cross-baseline acceptance runs on **local copies** (titiler-serves-blob deferred to P5); [G7] code onto VM via **git-clone** (Batch dress rehearsal), rsync for debug.

**Scope:** Contract + **MPC** (copy + GDAL-tag stamp) + **CDSE** (jp2→COG + declare) implemented; **ERA5** designed-for, built later. **Living docs updated on sign-off:** `TODO.md` (#38 signed off; #35 closed; #37/#30/#10 folded), `PROGRESS.md`, memory `[[fsd-status]]`. **`CHANGES.md` deferred to implementation** (it records shipped behavior; nothing's built yet).

## 🎉 P1 STORAGE SEAM PROVEN END TO END (2026-07-18) — `runbooks/31-p1-datacube-on-blob.md` ran GREEN (`"pass": true`). Spec 31 DONE.

The fsd core pipeline (build + flatten) ran with **every byte on the `rise` Azure blob**, switched on by config alone (`storage="azure"` / `FSSPEC_ABFSS_ANON=false`; account from the URL). `_result.json` all-green, verified against the corrected criteria (independently, not the `pass` flag):
- **Build 1** (`python -m fsd.workflows.task` as a real subprocess, remote `--export-folderpath`): wrote `datacube.npy`/`metadata.pickle.npy` to `abfss://` (D1/§3), streamed blob COGs via GDAL `/vsiadls/` + fresh token (D2/§4), and — inheriting `os.environ` unmodified — proved `FSSPEC_ABFSS_ANON` crosses the subprocess boundary (D4). Cube `[3,550,606,1]` uint16 (**T=3**, 1 band = B08 after SCL mask→drop); `task_slice_rows=9`.
- **Build 2** (`create_training_data(storage="azure")` via the real Snakemake runner, blob catalog, local export): T=3, `n_pixels=216583` — the normal entrypoint against a blob catalog.

Only stderr = a benign "time gaps (10 days)" S2-revisit warning. **This is the P1 exit criterion — spec 10 Seam 1 (storage = config, not code) realized on real Azure.** **→ NEXT: the ingest/normalization contract spec (TODO #38 — §5-ARCHIVE + the `clip(DN−1000,0)` vs `NODATA=0` encoding question + TODO #35), which re-opens download-to-blob for all sources.**

## 🧹 CONSOLIDATED TO `main` (2026-07-18) — all spec-31 worktrees merged + removed; **work from the `fsd/` checkout now, no more worktrees.**

Spec-31 work is now on **`main`** (`b24e6a2`, 3 commits: `6f3435f` compute seam + review, `1583ced` ROI-locate fix, `b24e6a2` build-1 filtered-slice fix), ahead of `origin/main` by 3 (**unpushed** — push only on request). Both worktrees (`spec31-p1-azure-compute-seam`, the stale `spec33-docs-update`) were removed; their content was verified fully present on `main` before removal (notebooks preserved as WIP; a `git stash` on `main` — "main-wip-pre-spec31-merge" — still holds the pre-merge state as a safety net, droppable with `git stash drop`). Two orphan branch refs remain (`worktree-spec31-p1-azure-compute-seam`, `worktree-spec33-docs-update`) — harmless; delete with `git branch -D` when convenient. Suite from `fsd/.venv`: **269 passed / 3 skipped, ruff clean** (venv has `[dev,azure]`). Two demo bugs fixed post-review while debugging the user's run: (1) the ROI path assumed a non-worktree layout; (2) build 1 fed `workflows.task` the raw catalog instead of a `TileCatalog.filter` slice → `KeyError: 'area_contribution'`. **→ NEXT: user re-runs `runbooks/31-p1-datacube-on-blob.md` from `fsd/`, pastes back `_result.json`.**

## ✅ Opus@high REVIEW (2026-07-17): **PASS with one fixed bug** — spec 31 P1 compute-seam implementation is sound; the demo script's success criterion was wrong (`EXPECTED_T=2` vs the real `3`), fixed here. Tree left uncommitted. **→ NEXT: user runs `runbooks/31-p1-datacube-on-blob.md`.**

**Reviewed** code-vs-spec + independent re-verification + 2 mutation tests (spec 24 D5 / spec 33 precedent), from **inside the worktree** `spec31-p1-azure-compute-seam` against its own `[dev,azure]` `.venv`. **Verdict: PASS.** The compute seam (`azure.py`/`rio_open`/`configure_storage`/the §6 abspath fix) matches the pivoted spec (§1–4/§6/§7); §5 correctly untouched (`git diff --stat` on `sources/mpc.py`+`cdse.py` = empty, verified, not taken on report); scope discipline clean.

**Verified independently, reproduced not trusted:**
- `pytest -q` → **269 passed / 3 skipped**; `ruff check src/ tests/` clean.
- Degrades cleanly without the `[azure]` extra: uninstalled `adlfs`/`azure-identity`/`azure-core`/`azure-storage-blob` → **244 passed / 4 skipped** (25 azure-seam tests skip via module-level `importorskip`), then reinstalled → back to 269/3.
- **Mutation A** (implementer's, re-run not trusted): reverted the `fs.is_local` guard in `create_datacube.setup()` → `os.path.abspath` unconditional → `test_setup_does_not_corrupt_a_remote_run_folderpath` fails, showing the exact corruption (`<cwd>/abfss:/data@acct.../s1`). Guard is load-bearing.
- **Mutation B** (my own choosing): dropped the `storage == "local"` no-op arm in `configure_storage` → `test_configure_storage_local_string_is_noop` fails (wrongly raises). The "third thing" (local-as-noop) is genuinely pinned. `storage=object()` still correctly raises (regression intact).

**Finding R1 (FIXED here) — demo success criterion was wrong (would false-fail a green run).** `runbooks/scripts/31_datacube_on_blob.py` asserted `EXPECTED_T = 2` and `runbooks/31-p1-datacube-on-blob.md` listed `timestamps_len == 2`. Calendar windows tile `[startdate, enddate)` in `mosaic_days` steps anchored at startdate, so 2018-07-01..2018-09-01 (62 days) at `mosaic_days=30` = **`ceil(62/30)=3`** windows, **not 2** — verified against `fsd.datacube.ops._calendar_windows` and `api.compute_n_timestamps` (both return 3). The spec's own "T=2 at mosaic_days=30" prose is an arithmetic slip that propagated into the implementer's PROGRESS entry (below) and the script. A perfectly successful demo run would have reported `"pass": false`. **Fixed** the script (`EXPECTED_T=3` + a comment explaining the data-independent count) and the run-book table (`3`, with a note). Count is deterministic regardless of granule dates (the calendar scheme emits every window, empty trailing one as an all-mask slice). **Also patched the two "T=2" references in the spec body (`specs/31`, §The demo slice-rationale + step 2) to "T=3" with a dated correction note (user-approved 2026-07-17); the upload run-book has no T claim to fix.**

**Finding R2 (ACCEPT — no new spec needed) — the Snakemake-sentinel gap (implementer's finding #2 / TODO #41).** The two-build demo workaround **adequately proves spec 31's intent.** Build 1 (`python -m fsd.workflows.task` as a real subprocess, remote `--export-folderpath`) proves the whole compute seam *including the write side* — D1 (`abfss://` artifacts), D2/§4 (GDAL `/vsiadls/` streaming reads), §3 (`fs.save_npy` writes to blob), D4 (`FSSPEC_*` inherited across the subprocess boundary — this *is* the exact CLI the Snakemake runner shells out to). Build 2 (`create_training_data(storage="azure")` through the real Snakemake runner, blob catalog, local export) proves the normal entrypoint reads blob through the child subprocess. The uncovered piece — Snakemake's own `start.txt`/`done.txt` bookkeeping can't live on blob — is a **runner-seam (spec 10 Seam 2) concern, which spec 31 explicitly scopes OUT** (P1 = local runner + blob storage). Making it fail-loud (`RuntimeError`) instead of silent-corrupt + logging TODO #41 (folded into the Batch-runner redesign) is the correct handling. **P1 is genuinely "done" for what it claims; this does not block sign-off.**

**Also spot-checked:** `rio_open` keeps the `rasterio.Env` alive for the dataset lifetime + tears it down on `close()` (correct — GDAL range-reads after open); `configure_storage` sets both `os.environ` and `fsspec.config.conf` (the import-time-vs-runtime hazard); `_check_local_seams(storage_allowed=False)` on `run_inference`/`deploy` keeps inference local. Band list `['B08','SCL']` correct per TODO #35 (SCL mandatory via `build_datacube`'s hardcoded mask→drop; B08 = `config.REFERENCE_BAND`).

## PRIOR (2026-07-17, implementation) — ✅ **spec 31 P1 Azure COMPUTE SEAM IMPLEMENTED (Sonnet@medium)** — 269 passed/3 skipped, ruff clean. **→ Opus@high review** (done above), then the user runs the datacube-on-blob demo.

**Implemented to the pivoted spec** (`specs/31-p1-azure-storage-seam.md` §1–4/§6/§7; **§5 NOT
implemented**, as instructed — download-to-blob stays suspended). Deliverables: `fsd/storage/
azure.py` (new — `to_vsi`, `account_from_url`, `storage_token` off a single module-cached
`DefaultAzureCredential`, `configure_storage`); `fsd/storage/fs.py` re-exports `to_vsi` + gained
`is_local` (see finding below); `fsd/raster/__init__.py` gained `rio_open` (local passthrough;
`abfss://`/`az://` → GDAL `/vsiadls/` under a fresh-token `rasterio.Env` kept alive for the
dataset's lifetime; `mode="w"` on remote raises), swapped into the 3 pixel-read sites
(`raster/images.py`, `raster/cog.py`, `catalog/stac.py`); `api.py`'s `_check_local_seams` gained
`storage_allowed` (default True; `download`/`create_training_data` accept `storage="azure"` +
call the new `configure_storage`; `run_inference`/`deploy` pass `storage_allowed=False` — stay
local, per §Scope); `pyproject.toml` gained `azure-identity` in `[azure]`. 27 new tests
(`tests/test_azure_seam.py` + 2 in `test_workflows.py`), all mutation-tested non-vacuous (mutated
`to_vsi`, `rio_open`, the `os.path.abspath` guard, and the Snakefile guard — each mutation broke
exactly the test meant to catch it). `[dev,azure]` installed into this session's `.venv` so the
adlfs-introspection tests (pinning the installed `adlfs 2026.5.0`/`fsspec 2026.6.0` facts §1
cites) actually run rather than skip; also verified the suite degrades cleanly to **244
passed/4 skipped** with `adlfs`/`azure-identity` **uninstalled** (the `[dev]`-only baseline a
fresh clone would actually have), then reinstalled.

**Also caught by re-tracing the spec's own §Tests wording (not just "does the function exist"):
`storage="local"` was being REJECTED, not treated as a no-op like `None`.** The spec's Tests
section says explicitly `storage="local"`/`None` leaves `FSSPEC_ABFSS_*` unset — my first pass of
`_check_local_seams`/`configure_storage` only special-cased `None`, so `storage="local"` fell
through to "not 'azure' → raise". Fixed (`storage != "local"` added to both guards); a test now
pins it (`storage=object()` still correctly raises, confirmed unaffected).

**⚠️ New finding beyond the spec's own §6 grep head-start (which only checked `os.path.exists`/
`os.makedirs`/bare `open(` and missed both of these):**
1. **`workflows/create_datacube.py`'s `setup()` + its Snakefile both called `os.path.abspath()`
   on `export_folderpath` unconditionally.** `os.path.isabs("abfss://...")` is `False`, so
   `abspath` silently prepended the local cwd and mangled the scheme into `abfss:/` — a real
   **silent corruption bug**, not a style nit, that would have broken the datacube-on-blob demo
   at the first URL it touched. **Fixed** with a new `fsd.storage.fs.is_local(path)` guard at
   both sites (mirrors `sources/cdse._is_local_path`'s existing `fsspec.utils.get_protocol`
   pattern) — zero behavior change for local paths (mutation-tested).
2. **Deeper, NOT fixed: the local Snakemake runner's own `start.txt`/`done.txt` resumability
   sentinels (`Snakefile`'s `touch()`) are plain `os.makedirs`/`open`, not `fsd.storage`-routed.**
   Even with (1) fixed, a remote `export_folderpath` would make Snakemake's own DAG tracking
   silently create a garbage **local** sentinel directory (a valid-if-bizarre local relative path
   like `./abfss:/data@acct.dfs.core.windows.net/.../done.txt`) rather than crash — worse than a
   raise. This is a genuine limitation of the local runner (where does Snakemake's own bookkeeping
   live when artifacts are remote?), not something a "swap bare `rasterio.open`" pass can fix, and
   not in spec 31's stated scope. **Made it fail loud instead of silently corrupting**: the
   Snakefile now raises a clear `RuntimeError` for a remote `export_folderpath`. Logged as
   **TODO #41** (folded into the Batch-runner item — a real fix likely arrives with that redesign).

**Spec-section → implementation trace** (the spec-32 lesson: check the call chain, not just
that functions exist):
- **§1 config seam** → `storage/azure.py::configure_storage` sets both `os.environ` and
  `fsspec.config.conf["abfss"]["anon"]`; `test_configure_storage_azure_string_sets_env_and_conf`
  + the `[dev,azure]`-only adlfs-introspection tests pin the exact library facts (`protocol`
  tuple, `apply_config`, `_get_kwargs_from_urls`) §1 cites, against the *installed* versions, not
  assumed ones.
- **§2 `to_vsi`** → `storage/azure.py::to_vsi`/`account_from_url`; traced against
  `31_upload_slice.py`'s own `_to_vsi` (the pre-existing, real-data-proven reference) —
  same regex shape, same translation. `os.path.join` URL-safety pinned by a direct unit test.
- **§3 adlfs reads/writes** → "no new code" per the spec; confirmed true — `fs.*`'s 94 call
  sites are untouched (`git diff` on `storage/fs.py` shows only the `to_vsi`/`is_local`
  additions, no edits to `_fs_and_path` or any existing function body).
- **§4 `rio_open` + token** → `raster/__init__.py::rio_open`/`storage/azure.py::storage_token`;
  traced call-by-call against the 3 named sites (`raster/images.py` 7 call sites,
  `raster/cog.py` 2, `catalog/stac.py` 2 — every bare `rasterio.open(` in those files, confirmed
  by `grep`, none left). Local-passthrough + remote-Env-with-parsed-account + write-guard each
  have a dedicated mutation-tested unit test.
- **§5** → not implemented, confirmed by `git diff` showing zero changes to `sources/mpc.py`/
  `sources/cdse.py`.
- **§6 audit** → confirmed the reviewer's grep head-start (builder.py/workflows/*.py clean of
  `os.path.exists`/`os.makedirs`/bare `open(`) AND found what it missed (`os.path.abspath`,
  finding 1 above — a different grep pattern than the one the head-start ran). The remaining
  `rasterio.open(` sites (`api.py`'s inference-merge, `model/engine.py`'s inference write) are
  confirmed out-of-P1-scope by tracing `_check_local_seams(..., storage_allowed=False)` on both
  `run_inference` and `deploy`.
- **§7 packaging** → `azure-identity` added to `[azure]`; confirmed importable + functional by
  actually installing `[dev,azure]` into `.venv` and running the full suite against it (not just
  reading the toml).
- **Deliverables' Tests list** → every named test scenario has a corresponding test in
  `tests/test_azure_seam.py`/`test_workflows.py`, cross-checked line-by-line against the spec's
  §Tests bullet list while writing them (not written from memory of the summary above).

**Consequence for the demo run-book** (`runbooks/31-p1-datacube-on-blob.md` +
`runbooks/scripts/31_datacube_on_blob.py`, written, **not yet run** — that's the user's next
step): it proves every claim spec 31's demo cares about via **two builds** instead of the
spec's literal "run one cell through the Snakemake runner writing to blob" — (1) `python -m
fsd.workflows.task` invoked **directly as a real subprocess** with a remote
`export_folderpath` (this *is* the exact CLI unit-of-work Snakemake shells out to, so it still
proves D4's env-inheritance-across-subprocess claim, plus D1/D2/§3/§4 on the write side); (2)
`create_training_data(storage="azure")` through the **real** Snakemake runner, catalog on blob
but the per-cell working directory kept local (proves the same D2/D4 claims through the normal
entrypoint, avoiding finding #2 above). Both builds assert `timestamps` axis length `== 3`
(**corrected from `== 2` by the Opus review — R1 above; `ceil(62/30)=3` for the Jul 1–Sep 1 window**)
— the `mosaic_days=30` calendar-mosaic contract, a criterion that can actually fail, not the
degenerate T=1 runbook 32 v1 tripped on. Band list `['B08','SCL']` per TODO #35 (unchanged).

**Traced against the spec's own de-risking, not re-derived:** the upload run-book (below) already
proved D1 (catalog paths `abfss://`) and D2/§4 (GDAL `/vsiadls/` read of an uploaded COG) on real
blob data before this session started — this implementation's job was the *code*, not
re-verifying those claims, so `rio_open`/`to_vsi`/`storage_token` are a faithful port of
`31_upload_slice.py`'s own `_to_vsi` + `rasterio.Env(...)` block (same shape, same library facts).

**Living docs updated:** `CHANGES.md` (the seam + the two §6 findings), `TODO.md` (#38 ingest
spec, #39 inference/serving-on-blob, #40 ROI-geometry-on-blob, #41 Batch runner + the sentinel
finding), `RECIPES.md` (a `storage="azure"` recipe), `specs/10-storage-and-scale.md` (pointers to
spec 31 realizing Seam 1). Tree left **uncommitted** (commit only when asked).

**→ NEXT:** the user runs `/handoff` → a fresh **Opus@high** session reviews (code-vs-spec +
independent re-verification + a mutation test, per spec 33's review precedent — this session
already ran the mutation tests inline, but an independent pass should re-check them, not take
the report on faith) — **and should look hard at finding #2 above**, since it's a real,
newly-discovered scope question (does the demo's two-build workaround adequately prove the
spec's intent, or does the Snakemake-sentinel gap need its own follow-up spec before P1 is truly
"done"?). Then the user runs `runbooks/31-p1-datacube-on-blob.md` (not yet run) and pastes back
its `_result.json`. Then Opus writes the **ingest/normalization contract spec** (TODO #38 —
§5-ARCHIVE + the `clip(DN-1000,0)` vs `NODATA=0` encoding question + TODO #35 are its inputs).

---

## PRIOR (2026-07-17, later) — 🔄 **ROADMAP PIVOT (user): the DOWNLOADER should normalize, not the datacube builder.** Spec 31's seam survives; its §5 + download-demo are SUSPENDED into a new ingest-contract spec. **Run-book `31-p1-upload-slice.md` is written and ready for the user to run NOW (on wifi).**

**The user's argument, and it is correct** (verified against the code, not accepted on assertion):
`build_datacube`'s chain is
`load_images → _apply_boa_offsets → dst_crs → reference(B08) → resample → stack →
apply_cloud_mask_scl → drop_bands(["SCL"]) → median_mosaic`
— steps 2, 7, 8 are **Sentinel-2 semantics hardcoded into the generic builder**, plus
`REFERENCE_BAND="B08"`. It is an S2 L2A builder wearing a generic name, so every new source must
either cosplay as S2 or force a builder rewrite. **We already logged the consequence without seeing
the pattern: TODO #35 (CHIRPS/ERA5 have no SCL) is this same issue, filed as a one-off.**

**The sharpest version, from our own history:** spec 31's original §5 was `stage-local → convert →
put-to-blob`. The MPC pivot **deleted** it ("MPC is already COG, no conversion needed") — but MPC
didn't remove normalization, it **moved** it from *format* (jp2→COG) to *radiometry* (baseline
offset), and we put the radiometry in the **builder** instead of keeping §5's shape. So §5's shape
was right and deleting it was the error. The user's "intermediate process" = generalize it:
`stage → normalize → put`, per source (CDSE=format, MPC=radiometry, ERA5=netCDF→COG).

**Direction agreed:** ship the seam (architecture-neutral — it's about *where bytes live*, not what
they contain, and the user's own "pull → process → upload to Azure" **requires** it), suspend §5 +
the download demo into a new **ingest/normalization contract spec**, and prove the seam against
**data we upload by hand** rather than a download. Open design questions for that spec, **not
settled**: bake-at-ingest vs a per-source read adapter (baking kills MPC's byte-copy advantage);
the normalized **encoding** (`clip(DN-1000,0,65535)` vs `NODATA=0` **eats real pixels in (0,1000]**
— baking makes that permanent and silent); absorbing TODO #35. Note **normalize-at-ingest forecloses
TODO #31's `/vsicurl` stream arm — but ERA5 forecloses it anyway** (you cannot stream a netCDF as a
COG), which strengthens the case rather than weakening it.

**⚠️ Governance note:** the 2026-07-15 diagnostic found this project keeps working *around* P1. A
well-argued "redesign ingest first" is exactly that pattern's shape. **Guard: the seam still ships.**
This is not the avoidance pattern *provided* the upload + seam land before the ingest spec.

### ⚠️ `satellite_benchmark/` IS GONE — docs were stale, and a session planned against it

Discovered when sizing the upload: **`satellite_benchmark/` does not exist on any mounted volume**
(no external drives). Deleted deliberately for disk pressure (it was 159 GiB; disk is at **96%, 36
GiB free**), and **CLAUDE.md + memory both still described it as the test set** — so this session
built a plan on data that wasn't there. **Now corrected in CLAUDE.md + RECIPES.md.**

**What survives** (`fsd/tests/outputs/`, 83 GB, gitignored):
- **`demo_e2e/imagery/` = the real-data test set now** — Austria e2e: **207 granules, 74 GB**,
  Apr–Sep 2018, 4 MGRS tiles (T33UVP 54 / T33UWP 52 / T33UVQ 52 / T33UWQ 49), B04/B08/B8A/SCL,
  already COG, with `catalog.parquet`.
- `mpc_baseline/imagery/` — 1.7 GB, 9 granules, 33UWP, B04+SCL (runbook 32's over-fetch).
- **Verified geometry:** `s2grid=476da24` is **100% inside T33UWP**; `AT_ROI` straddles all four
  tiles ~evenly (32.7/32.7/32.7/32.6%) → **AT_ROI is now the multi-tile/multi-CRS case**, since
  Ethiopia's `s2grid=165bca4` has **no imagery behind it any more**.
- Per-band totals across 207 granules: B08 34.2 GB (avg 165 MB), B04 31.7 GB, B8A 9.2 GB,
  **SCL 0.54 GB (avg 2.6 MB)**.

### ⚠️ NEW FINDING — our Austria archive is radiometrically WRONG (#10/#30, live)

**Every granule is baseline `N0500`** (05.00 ≥ 04.00 → ESA `BOA_ADD_OFFSET = -1000`), but
`sources/cdse.py:514` writes **`boa_add_offset = 0`** for every CDSE row (TODO #30 open), and this
catalog **predates the column entirely** so `TileCatalog.read` fills 0. **So every datacube ever
built from the Austria archive is ~1000 DN too high** — including the 300-cell e2e crop map. Not a
seam problem (harmless for P1, whose PASS criteria are all seam properties), but it is **correctness
debt #10 sitting live in our own test data**, and it is the single best exhibit for the pivot above:
the downloader didn't normalize, the wrongness got baked into an artifact, and the catalog asserts
it needs no fix.

### → The thing to run NOW (user, on wifi): `runbooks/31-p1-upload-slice.md`

Uploads **T33UWP × Jul–Aug 2018 × [B08, SCL] = 20 granules / 40 files / 2.27 GB** to the `rise`
blob and writes a `catalog.parquet` **on blob with every band path an `abfss://` URL**. Chosen
because 476da24 is 100% inside T33UWP and two months gives a real **T=2** mosaic axis at
`mosaic_days=30` (not a degenerate T=1 — the trap runbook 32 v1 fell into).

- **Needs NO spec-31 code:** `fs.put`/`fs.write_parquet` already route fsspec→adlfs; only
  `azure-identity` + **`FSSPEC_ABFSS_ANON=false`** are required (the account is parsed from the URL).
- Script `runbooks/scripts/31_upload_slice.py` follows the committed-script pattern (no
  `export`+heredoc), is **idempotent/resumable**, prints live MB/s + ETA ([[long-process-progress]]),
  and writes `_result.json` **unconditionally**. **Verified offline:** ruff clean; `--dry-run`
  reports exactly 20/40/2.27 GB; the missing-`FSSPEC_ABFSS_ANON` guard and the bad-URL guard both
  fire and still write `_result.json`; `_to_vsi` translates correctly.
- **It also proves spec 31 D2/§4 before any code is written for it** — reads our own uploaded COG
  through `/vsiadls/` + a fresh `AZURE_STORAGE_ACCESS_TOKEN` (`gdal_vsiadls_read_ok` +
  `gdal_sample_nonzero` are the load-bearing PASS keys).
- **A seam finding the spec got wrong:** the catalog column is **`local_folderpath`** (name becomes a
  lie on blob) and `builder.py:72` joins it with `files` to make each band path. **Spec 31 §2 claims a
  catalog `filepath` column — there is none**; `filepath` is derived in `flatten_catalog`. The upload
  script rewrites `local_folderpath` → the blob folder and narrows `files` to `B08.tif,SCL.tif` so the
  blob catalog is self-consistent.

**✅ UPLOAD RAN GREEN (user, 2026-07-17): `"pass": true`.** 20 granules / 40 files / **2.27 GB** on
`rise` at `data@…/fsd-tests/p1-demo/imagery/`, ~13.4 MB/s over VPN (170 s). All 20 catalog rows on
blob carry `abfss://` paths (`every_catalog_path_is_abfss: true`); **GDAL read our uploaded COG via
`/vsiadls/`** and got real uint16 256×256 pixels (`gdal_vsiadls_read_ok` + `gdal_sample_nonzero`).
So **D1 + D2/§4 — the spec's riskiest claims — are proven on real data before any seam code exists.**
(One untested path: `files_skipped_already_present: 0`, so idempotent-resume never fired in the wild.)

**✅ Spec 31 rewritten end-to-end for the pivot (same session).** The spec was signed off with §5 =
MPC-copy-to-blob + a download demo; the pivot suspends both. Now consistent throughout: a **⚠️ pivot
banner** at the top of the status block (download-to-blob OUT → ingest spec; this is a *compute-seam*
spec); **D3 marked obsolete**; **§5 SUSPENDED** with the MPC-copy design preserved as **§5-ARCHIVE**
for the ingest spec; **Scope, Tests, the demo, and Deliverables** all rewritten to "build over
hand-staged blob data, no download" (`mpc.py`/`cdse.py` **not touched**, both guards stay); the demo
gained an explicit **D4 subprocess-safety** step (run one cell through the Snakemake runner). Also
fixed a real spec error the upload surfaced: **there is no catalog `filepath` column** — it's
`local_folderpath` (joined at `builder.py:72`); `filepath` is only `flatten_catalog`'s transient
output. Suite still 242/3, ruff clean.

**→ NEXT:** **Sonnet@medium implements the spec-31 compute seam** (§1 config, §2 `to_vsi`, §3 adlfs,
§4 `rio_open`/`/vsiadls/`, §6 audit, §7 packaging — **not** §5) against the uploaded blob data → then
the user runs the datacube-on-blob demo run-book → then **Opus writes the ingest/normalization
contract spec** (§5-ARCHIVE + the encoding/`(0,1000]`-clip question + TODO #35 are its inputs).
Nothing committed (no ask).

---

## PRIOR (2026-07-17) — ✅ **spec 31 (P1 Azure storage seam) REVIEWED, REWRITTEN, SIGNED OFF** (Opus@high, independent of the draft's author) → NEXT = **Sonnet@medium implements**. ⚠️ **Also found: concrete `rise` values leaked into the PUBLIC repo — user decision needed.**

**Sign-off is real this time and independently checked:** the draft was Opus (`030f6ac`, trailer
verified `Claude Opus 4.8` — not a repeat of spec 33's F1); this review was a **separate** Opus@high
session that did not write it. Draft → **revised** → signed off.

**The review caught the spec-32 failure mode recurring verbatim: the demo was structurally impossible
against our own code.** Spec 31's exit demo downloads to blob, but **both** sources hard-refuse a
remote dst today — `mpc.py:294` raises *"MPC source is local-only in Phase 1"*, and `cdse.py:645`
raises on remote + `cog=True`. Meanwhile the one section that would have fixed it (**§5**) had been
marked **DELETED** by the 2026-07-16 retarget banner and **never rewritten** ("a future session's
job"). So the spec deleted its own download-to-blob design and still depended on it — and its Scope /
Tests / Demo / Deliverables all still encoded the deleted CDSE design. Handed to Sonnet (which
implements to the letter, as 32 and 33 both did) it would have implemented the deleted §5.

**Two user decisions taken (2026-07-17), both as recommended:**
1. **Demo copies MPC → `rise` blob, then streams back via `/vsiadls/`.** Streaming MPC in place via
   `/vsicurl` would be smaller but would **never exercise `/vsiadls/`** — i.e. would not test D2/§4
   at all. TODO #31's *production* stream-vs-copy question stays **"measure, don't argue"**; this
   just builds the copy arm so the later measurement has a comparison.
2. **CDSE download-to-blob dropped from P1** → new TODO (next to #30). MPC is already-COG, so the
   jp2→COG dance the MPC pivot removed is not reimported. `sources/cdse.py` is not to be touched.

**What the rewrite changed:** §5 is now **"MPC copy straight to blob — pure byte-copy"**, written
against the actual guard it must lift (delete `mpc.py:294`; everything else in that path — `fs.makedirs`,
`_select_item_files`'s `os.path.join`, `_transfer_one`'s already-cross-backend, `.part`-atomic
`fs.transfer` — is already URL-safe, traced claim by claim). §1/§3's "registry + credential object"
language removed. **Demo band list pinned to `['B08','SCL']`** — TODO #35 (hardcoded SCL mask/drop)
is still open and `config.REFERENCE_BAND == 'B08'`, so any other list reproduces runbook 32 v1's
crash. Byte budget stated honestly (~0.5–1 GB, full-tile COGs) rather than v1's false "a few MB".

**All 5 open items RESOLVED at sign-off** — none left for the implementer. The two fsspec ones were
closed by **direct introspection of the installed libraries** (`fsspec 2026.6.0`, `adlfs 2026.5.0`),
now a "Verified against the installed libraries" section in the spec with per-fact credit:
- **`AzureBlobFileSystem.protocol == ('abfs','az','abfss')`** and `apply_config` keys on the **class's**
  protocol tuple, not the URL scheme → **set exactly one key, `FSSPEC_ABFSS_ANON=false`**. Setting
  several is a *hazard* (last proto silently wins), not thoroughness.
- **`_get_kwargs_from_urls('abfss://data@acct.dfs.core.windows.net/…') == {'account_name': 'acct'}`**
  → **D1 confirmed**; the account rides in the URL and beats conf, so `FSSPEC_ABFSS_ACCOUNT_NAME` is
  redundant. **D1–D4 all survive independent review** (D2's token handling and D3's "GDAL never
  writes `/vsiadls/`" both hold — with MPC, GDAL is never on the write path at all).
- Scratch-dir question **moot** (no staging without conversion); atomicity question **resolved** by
  `fs.transfer` already doing `.part`+rename (the residual — is adlfs's `mv` atomic on HNS — is a
  runbook *observation*, step 2's "no `.part` leftovers").

### ⚠️ LEAK — concrete `rise` values are in the PUBLIC repo (`git@github.com:nikhilsrajan/fsd.git`)

Found while auditing spec 31 for placeholder discipline. **The handoff's claim that spec 31 was
verified clean was wrong** — and `PROGRESS.md` was worse:
- `specs/31…md` §1 named the **storage account**. → **scrubbed** to a pointer.
- `PROGRESS.md` (this file, 2026-07-15 entry) named the **storage account, the user's identity
  (`…@raapid.org`), the subscription name AND its GUID, and the resource group**. → **scrubbed** to
  pointers at `../P1_AZURE_SETUP.md`.
- **Introduced by `030f6ac`, which is an ancestor of `origin/main` → already on GitHub.** Scrubbing
  the working copy does **not** remove it from history; `git show 030f6ac:PROGRESS.md` still has it.

**Severity, stated honestly: no credential leaked.** Account keys are disabled (Entra-only), storage
is RBAC-gated and VPN/firewalled, and subscription/RG/account names are identifiers, not secrets. The
most sensitive item is the **identity email** — a valid Entra username is a phishing/spray target. So
this is a genuine **hard-constraint violation** to decide on deliberately, not an emergency.
**Open for the user:** leave history as-is (scrub going forward), or rewrite history / rotate the repo.
Claude did not touch git history — that is destructive and the repo is public/shared.

**Also corrected:** the handoff said "3 unpushed commits, nothing has been pushed." **False** —
`origin/main` is at `14781c1`; all three spec-33 commits are pushed.

**Nothing committed** (no ask). Working tree still carries the deliberate `TODO.md` #26-reflow WIP +
the two notebooks, untouched.

**→ NEXT:** `/handoff` → **Sonnet@medium** implements `specs/31-p1-azure-storage-seam.md` against the
signed-off text (§Deliverables is the checklist; the runbook must follow the **committed-script**
pattern of `runbooks/scripts/33_probe_dedup.py`, not v1's `export`+heredoc that silently produced
nothing). Then Opus review, then the **user runs** `runbooks/31-p1-datacube-on-blob.md` (VPN on,
~0.5–1 GB). **Decide the leak question** at some point before the next push.

---

## PRIOR (2026-07-16) — ✅ spec 32 DONE: runbook v2 FULLY VALIDATED on real MPC data. **Correctness debt #10 is fixed for MPC and proven end to end.**

**All three steps PASS.** Verified independently from the artifacts on disk (not from the `pass`
flag — v1 proved that flag could lie):

- **The cutover boundary was hit exactly.** Real items: `20220107` baseline **`03.00`** → offset
  `0`; `20220127` baseline **`04.00`** → offset `−1000`. `04.00` is the *first* offset baseline, so
  this exercises `_baseline_tuple(...) >= (4, 0)` **precisely on the boundary** — `>` instead of
  `>=` would have silently returned 0. Real data landed on the one value that tells them apart.
- **Step 3 A/B vs unharmonized control** (cube `(2, 550, 606, 1)`): `pre_identical_to_control =
  true`; post slice equals the control **exactly −1000** across **202 831** non-clipping pixels
  (`np.array_equal`, no tolerance); **zero** pixels in `(0, 1000]` → nothing clipped → mean delta
  exactly **1000.0**.
- **The science:** pre-vs-post gap **2187.1 DN** unharmonized → **1187.1 DN** harmonized. The fix
  removed exactly the 1000 DN artifact; the 1187 remainder is real January scene change. That *is*
  #10: a mosaic spanning both dates would have blended 400 with 2587 where the truth is 400/1587.
- **Both open items resolved:** `s2:processing_baseline` + `s2:mgrs_tile` confirmed live;
  `storage.transfer` streamed signed MPC HTTPS cleanly — **no `aiohttp` fallback needed**.

**Getting here took a runbook v2** — v1's steps 2–3 were defective, and the fault was **spec 32's
Tests section (mine), not the implementation**: it prescribed "band B04 only" *and* "build a
2-timestamp datacube", which are mutually impossible since `build_datacube` hardcodes
`apply_cloud_mask_scl` → `drop_bands(["SCL"])`. That survived sign-off, cross-validation,
implementation **and the Opus code review** (which checked code-vs-spec but never traced the runbook
against the builder's op chain — the guard test's own B04+SCL was the tell). **Lesson: cross-
validating *external* facts doesn't catch inconsistency with our *own* code.** v1's other three
defects: it over-fetched **9 items / 1.7 GB** (downloaded the whole range *between* pre and post);
claimed "a few MB / no full-tile download" when **MPC assets are full-tile COGs (one B04 = 96–272
MB)**; and had PASS criteria that couldn't fail (`pass` only checked `failed_count`;
`mosaic_days=120` over 120 days gives **T=1**, not the 2 it compared). v2 fixed all four and
replaced the vague check with the A/B above.

**Follow-ons logged (none blocking):**
- **#34 — MPC serves duplicate reprocessed acquisitions.** `20220301T100029` came back **twice**
  (processed `20220303` *and* reprocessed `20240604`) — same sensing time + tile, different item
  ids, so the id-uniqueness check passes. Both downloaded (224+272 MB), both catalogued;
  `_stack_datacube` merges two copies of one scene with an arbitrary tie-break. **Not
  radiometrically wrong** — spec 32 offsets each processing on its own baseline before the merge
  (the design earning its keep) — but wasted bytes + a silent arbitrary pick.
- **#35 — `build_datacube` requires SCL even when masking isn't wanted** (root of the v1 crash).
  Own spec needed: it changes a core contract, and TODO #11's non-optical sources (CHIRPS/ERA5) have
  **no SCL at all**, so they're blocked on it.
- **#36 — CDSE-vs-MPC speed: PARKED by the user.** Recorded with confounds so they aren't
  re-derived: VPN × 9-items-not-2 × a duplicate × **full-tile copy for a 0.18 % ROI** (21.5 km² read
  from a 12 100 km² tile). TODO #24 already establishes the local result is link-bound and **doesn't
  generalize to Azure**; the dominant lever is plausibly windowed `/vsicurl` vs full-tile copy
  (TODO #31), not the source choice.
- **Pin `planetary-computer`** — the spec's open item; the resolved version is now observable from
  the runbook's install.

**All committed + pushed** — `main` @ `8d91510`, in sync with `origin`. Spec 32's last open item
closed too: **`planetary-computer>=1,<2`** pinned (the runbook's install resolved **1.0.0**, so the
bound came from a verified fact, not a guess; verified it accepts 1.0.0/1.x and rejects 0.9.0/2.0.0).
Uncommitted WIP, deliberately untouched: the `TODO.md` item-#26 reflow + the two notebooks.

---

## PRIOR (2026-07-17) — ✅ spec 33 (MPC reprocessing dedup, TODO #34) CLOSED: implemented (Sonnet@medium) + Opus@high review PASS + **runbook 33 VALIDATED on live MPC data** (`"pass": true`, duplicate still live upstream so the test was real). NEXT = spec 31 (P1 Azure seam)

**Implemented to the letter of `specs/33-mpc-reprocessing-dedup.md`** — no redesign, no forks
reopened. `sources/mpc.py`: new `_generation_time(item) -> str` (reads `s2:generation_time`,
raises with the item id + property name if missing) and `_dedupe_reprocessed_items(items) -> list`
(groups by `(item.datetime, _mgrs_tile_from_item(item))`, `max` by `_generation_time` breaks ties,
singleton groups pass through untouched). Wired in as `items = _dedupe_reprocessed_items(items)`
immediately after each of the two existing `_search_items(...)` calls, in both `query_catalog`
(before `_items_to_gdf`) and `download` (before `_finalize_catalog_gdf`) — so a duplicate is never
even queued for transfer, which is the actual byte-saving TODO #34 asked for.

**Tests** — 8 new cases in `tests/test_mpc.py` (existing `_FakeItem`/`_fake_item` fixtures
extended with an optional `generation_time` kwarg, no new fixture style): no-duplicates no-op,
duplicate-pair latest-wins (+ order-independence), three-way group, missing-`s2:generation_time`
on a duplicate group raises, singleton missing the property does *not* raise, key falls back to
`item.id` when `s2:mgrs_tile` is absent, and two integration tests (`query_catalog` and `download`)
using the real spec-32 runbook duplicate pair (`S2B_MSIL2A_20220301T100029_R122_T33UWP_...`,
fabricated `s2:generation_time`s matching the real `20220303`/`20240604` ordering) plus a distinct
control item — asserting exactly 2 rows survive (never 3) and the loser's asset href is never
passed to `fs.transfer`. Followed the process guard from the handoff: duplicate-group fake items
share one identical `datetime` object per group (not just close), so the dedup path is genuinely
exercised, not silently skipped by a spurious microsecond mismatch.

**Verification:** `pytest -q` → **242 passed, 3 skipped** (was 234 passed/3 skipped before this
spec; +8 new tests, zero regressions). `ruff check src/ tests/` → clean. No runbook needed (pure
in-memory filter, no new network behavior) — matches the spec's own "why safe without a runbook"
note.

**Untouched, as the spec required:** `pyproject.toml`, `catalog.COLUMNS` (no new `mgrs_tile`
column), `datacube/builder.py`, `sources/cdse.py`. `_items_to_gdf`/`_finalize_catalog_gdf` unaware
of the dedup step — they simply never see a loser item now.

**Living docs updated:** `CHANGES.md` (new entry), `TODO.md` #34 → DONE (pointing at the spec + the
8-test count), this `PROGRESS.md` entry. Work done in worktree `spec33-docs-update`; **not
committed** (user asked to implement, not to commit — per CLAUDE.md's "commit only when asked").

## ✅ Opus@high REVIEW (2026-07-16): **PASS** — merged to `main`, 4 findings (none blocking)

**Reviewed** code-vs-spec + independent correctness, per spec 24 D5. **Verdict: PASS.** The
implementation matches the spec's pseudocode essentially verbatim; scope discipline is clean
(`pyproject.toml`, `catalog/`, `datacube/builder.py`, `sources/cdse.py` all untouched, verified by
diff); dedup provably runs before `_items_to_gdf`/`_finalize_catalog_gdf` at **both** call sites.

**Verified independently, not taken on report:** `pytest -q` → **242 passed / 3 skipped** and
`ruff` clean, reproduced from the worktree with `PYTHONPATH=src` (confirmed the loaded `mpc.py` was
the worktree's, not `main`'s — the trap noted in the spec-32 review). **Mutation test:** disabling
both dedup call sites fails exactly the two integration tests (`assert 3 == 2`) → the guard tests
are non-vacuous, not merely passing.

**Findings:**
- **F1 (fixed)** — `PROGRESS.md` claimed this spec was "SIGNED OFF (Opus@high)"; the commit trailer
  says **Sonnet 5**. Sonnet wrote, self-signed-off, and implemented its own spec. Corrected in the
  entry below; this review is the compensating control.
- **F2 (fixed)** — the dedup key silently dropped `relative_orbit`, which the spec's **own**
  research doc recommends. The narrowing is correct (orbit is determined by sensing instant + tile)
  but was undocumented; now recorded in spec 33 Fork 2.
- **F3 (open, non-blocking)** — the tie-break compares `s2:generation_time` as **strings**
  (lexicographic). Safe for the observed uniform format (`2024-06-08T13:16:56.674469Z`), would
  misorder if MPC ever mixed `+00:00`/`Z` or precision. `runbooks/33-mpc-dedup-live.md` now checks
  format uniformity empirically on live items; parse-to-datetime is the cheap hardening if it ever
  varies.
- **F4 (open, non-blocking, unreachable today)** — a `None` `item.datetime` would collapse every
  such item on one tile into a single group and dedup them wrongly. MPC S2 L2A always populates
  `datetime`, so it is not reachable; noted rather than guarded.

**New: `runbooks/33-mpc-dedup-live.md`** — the spec said "no runbook needed" and is right that
pytest covers the *logic*, but pytest **cannot** prove `s2:generation_time` is populated on the
**live** duplicate pair, because the fake items only have it since we put it there. The runbook
closes that gap: **discovery-only, zero imagery bytes**, seconds. Validated offline before handoff —
it **passes** against the fixed code (3 raw → 2 catalog, loser gone) and **fails** against
simulated pre-fix code (`loser_present=True`), so it is non-vacuous. Reports `inconclusive` (not a
false pass) if MPC has since cleaned the duplicate upstream.

**Merged to `main`** at the review (was uncommitted in worktree `spec33-docs-update`): the 4 code/doc
files applied as a 3-way patch; `TODO.md` #34 swapped by hand so `main`'s uncommitted item-#26
reflow WIP survived. Runbook rewritten to run from `main` + the normal `.venv` (no `PYTHONPATH`).
**Still uncommitted** — awaiting the user's ask.

## ✅ runbook 33 VALIDATED on live MPC data (2026-07-17) — dedup proven end to end

**`runbooks/33-mpc-dedup-live.md` ran green: `"pass": true`, every criterion met.** Discovery-only,
zero imagery bytes. The result is **not** the `inconclusive` fallback — **the duplicate is still
live upstream**, so this genuinely exercised the fix rather than passing vacuously:

- **`duplicate_groups_upstream: 1`** — MPC still serves both `..._20220303T182540` (original) and
  `..._20240604T180322` (2024 reprocessing) for sensing instant `2022-03-01 10:00:29.024+00:00` on
  tile `33UWP`. (So MPC's cleanup per discussion #275 did **not** remove this pair — the spec's
  premise still holds on live data today.)
- **`raw_item_count: 2` → `catalog_row_count: 1`** — dedup collapsed the pair; `catalog_ids` equals
  `independently_expected_ids` (recomputed by the probe, not taken from fsd's own answer).
  `known_winner_present: true`, `known_loser_present: false` — the 2024 reprocessing won, the
  original's ~224 MB is never queued.
- **Finding F3 empirically resolved (for this data):** `generation_time_format_shapes` = exactly
  one shape, `NNNN-NN-NNTNN:NN:NN.NNNNNNZ`. Live values are uniform RFC-3339 with microseconds +
  `Z`, so the string tie-break is sound — and it's a real ordering test, since the winner's
  `.000000Z` vs the loser's `.834434Z` differ in precision-of-content while sharing a format.
  Caveat: n=2. F3 stays noted (not reopened) as "verified on the only live pair we have".
- **Guard confirmed:** `mpc_module_loaded_from` = `.../fsd/src/fsd/sources/mpc.py` — `main`'s code,
  not a worktree's.

**New real-data fact (no action needed, recorded so nobody re-derives it):** live MPC's
`s2:mgrs_tile` is **`"33UWP"` — no `T` prefix** (the `T` lives only in the item id). This is
**consistent with fsd's own convention**: both `catalog.stac._parse_mgrs` and
`datacube.builder._mgrs_tile` also yield `33UWP` (verified directly). So there is **no mismatch and
no latent bug** — the three representations agree. The one wart is that `tests/test_mpc.py`'s
fixtures use the *unrealistic* `"T33UWP"`; harmless (dedup only needs the key self-consistent within
a run, and the tests still exercise the real path), but a reader could wrongly infer live MPC
returns a `T` prefix. Fixture-realism nit only — **not** a defect, logged here rather than as a TODO.

**→ NEXT:** **spec 31** (`specs/31-p1-azure-storage-seam.md`, DRAFT awaiting sign-off) — the P1
Azure storage seam. This is the critical path the 2026-07-15 diagnostic named (the project keeps
finishing work *around* P1); spec 33 was its last legitimate prerequisite, and it is now closed.
**Opus@high reviews/signs off spec 31 → then Sonnet@medium implements.** Given F1, verify the model
from the commit trailer, not the heading.

---

## PRIOR (2026-07-16) — ✅ spec 33 (MPC reprocessing dedup, TODO #34) SIGNED OFF (⚠️ **Sonnet@medium, not Opus — process deviation, see below**) — implemented same-day

> ⚠️ **CORRECTED 2026-07-16 at the Opus review (finding F1).** This entry originally read
> "SIGNED OFF (Opus@high)". **That was false.** Commit `e5d3e6c`'s trailer is
> `Co-Authored-By: Claude Sonnet 5` — a **Sonnet** session ran the interview → grill →
> cross-validate → spec → sign-off flow that spec 24 D3/D5 reserves for Opus, recorded the
> sign-off as Opus@high, and then implemented against its own spec. The prior handoff
> (`9ec060d`) was explicit: *"Opus@high writes spec 33 → sign-off → Sonnet@medium implements"*.
> Every other spec sign-off on record (`030f6ac`, `50749e8`, `6e1e9f0`, `4a81cd9`, `96d02b0`) is
> genuinely Opus; this is the one deviation.
> **Likely cause:** the model switch at `/handoff` (D6) is a manual step with nothing enforcing
> it — a session started at `/model sonnet` picks up the handoff doc and proceeds regardless.
> **Compensating control:** a full Opus@high review was run after the fact (see the LATEST entry) —
> code-vs-spec, independent re-verification, and a mutation test. **Verdict: PASS**, so the
> *outcome* was sound; the *process* was not, and the record now says so.
> **Lesson (new, alongside spec 32's "cross-validating external facts doesn't catch inconsistency
> with our own code"):** a self-signed-off spec has no independent check — the session that owns
> the design blind spots is the one grading them. Neither the spec text nor `PROGRESS.md` can be
> trusted to report which model actually did the work; **the commit trailer is the only ground
> truth.** Check it, don't read the heading.

**`specs/33-mpc-reprocessing-dedup.md` SIGNED OFF.** Interview → grill → cross-validate (standing
practice) → spec, per the handoff `/tmp/fsd-handoff-spec33-mpc-dedup.md`. **All 5 design forks
resolved, no open items blocked sign-off:**

1. **Where dedup lives → MPC-only (`sources/mpc.py`), not shared `cdse._finalize_catalog_gdf`.**
   Decided by researching Fork 4 first: CDSE has its **own**, structurally different multi-item
   issue (ESA-confirmed datastrip-split near-duplicates that can carry legitimate different pixel
   coverage/border artefacts) — a shared dedup rule risked silently dropping real CDSE data, so
   CDSE stays untouched.
2. **Key → in-memory `(item.datetime, mgrs_tile)`, no new catalog column.** Dedup runs on the raw
   STAC item list before any catalog row exists (right after `_search_items`, before
   `_items_to_gdf`), so `_mgrs_tile_from_item` (spec-32 dead code) gets its first real caller
   in-memory only — no `catalog.COLUMNS` change, no back-compat migration.
3. **Winner → latest `s2:generation_time`, NOT the item id's trailing field.** Reverses the
   handoff's suspected id-string-parsing approach: a live MPC STAC query confirmed
   `s2:generation_time` is a real, populated RFC-3339 property, while ESA's own SentiWiki
   naming-convention page explicitly declines to guarantee the id's trailing "Product
   Discriminator" field is monotonically increasing.
4. **Does CDSE have the same duplication? Yes, but differently** (see #1) — CDSE's own mechanism
   is catalogue-level deletion of old-baseline products, not a queryable "pick latest" property;
   confirms the two providers' problems aren't the same fix.
5. **Applied at discovery time** (both `query_catalog` and `download`, right after
   `_search_items`) — the loser is never even queued for transfer, which is the actual byte
   savings TODO #34 asked for. Existing test artifacts with a stale duplicate (e.g.
   `tests/outputs/mpc_baseline/catalog.parquet`) are **not migrated** — discovery-time fix only,
   explicitly out of scope.

**Cross-validation** — full detail + per-source credit in the spec's own §"Best-practice
alignment" + supporting file `specs/research-s2-reprocessing-dedup.md`: live MPC STAC item query,
`stac-extensions/sentinel-2` + `stac-extensions/processing`, the CDSE community forum
duplicate-products thread, CDSE's old-baseline-deletion notices, SentiWiki's S2 Products page,
`stactools-packages/sentinel2` issues #130/#5, and `microsoft/PlanetaryComputer` discussion #275.

**No runbook needed** — pure in-memory filter over STAC search results, fully synthetic-testable
(duck-typed fake items matching `tests/test_mpc.py`'s existing fixtures); no new network behavior.

**→ NEXT:** hand to a **Sonnet@medium** session to implement `specs/33-mpc-reprocessing-dedup.md`
(new `_generation_time` + `_dedupe_reprocessed_items` in `sources/mpc.py`, one call-site edit each
in `query_catalog`/`download`, tests per its §Tests, living-doc updates per its §Deliverables).
Then Opus review, then **spec 31** (Phase 2, Azure at scale) — the task after this one (unchanged
from the prior entry below). `TODO.md` #34 updated to point at the signed-off spec; nothing
committed this session (user asked only for the TODO/PROGRESS update, not a commit — per
CLAUDE.md's "commit only when asked").

---

## PRIOR (2026-07-16) — spec 33 scoped: TODO #34 (MPC reprocessing dedup), THEN spec 31 (Phase 2 Azure)

**Then spec 31 (Phase 2, Azure at scale) — the north star.** Status: **DRAFT, awaiting sign-off**,
already **de-risked by a green access probe** (`runbooks/31-p1-access-probe.md`, 2026-07-15:
`az login` done, personal identity has **Storage Blob Data Contributor**, adlfs
`DefaultAzureCredential` round-trips, GDAL 3.10.3 opens via `/vsiadls/` **and** `/vsiaz/`).
⚠️ **The 2026-07-15 diagnostic's "P1 blocked on user" is STALE — that blocker cleared.** The rewrite
must: (a) rewrite **§5**, flagged deleted/retargeted when MPC removed the `jp2→COG` conversion
problem but never actually rewritten; (b) **decide TODO #31's stream-in-place (`/vsicurl`) vs
copy-to-`rise` fork** — spec 32 explicitly deferred it to *this* Phase-1→2 boundary, which is now;
(c) note that **TODO #36** (CDSE-vs-MPC speed) becomes answerable here, since a local measurement is
link-bound and doesn't generalize (TODO #24's precedent). The **rslearn Plan B/C call does not gate
this** — the comparison concluded **scale-out is ours regardless** ([[fsd-rslearn-comparison]]).
Concrete `rise` names/IDs live **only** in `../P1_AZURE_SETUP.md` + `../AZURE_INFRA_PRIVATE.md`
(workspace root, never in the public repo).

**Parked, named so they don't get re-derived:** #35 (optional SCL — own spec; gates #11's SCL-less
CHIRPS/ERA5), #36 (source speed — parked by the user, confounds recorded), rslearn Plan B/C.

### Previous entry (spec 32 runbook v1 run — step 3 crash + diagnosis)

**The fix works on real MPC data.** Step 2's live catalog is the proof of D3: `20220107` (baseline
<04.00) → `boa_add_offset = 0`; `20220127`, two days after the cutover → `−1000`. The spec's two
flagged open items are also confirmed live: `s2:processing_baseline` and `s2:mgrs_tile` exist as
assumed, and `storage.transfer` streamed signed MPC HTTPS fine (no `aiohttp` fallback needed).

**Step 3 crashed — and the fault is spec 32's, not the implementation's.** `ValueError: SCL band
not present in datacube`. `build_datacube` hardcodes `apply_cloud_mask_scl` → `drop_bands(["SCL"])`,
so SCL is structurally required, but the spec's Tests section prescribed **"band B04 only"** *and*
"build a 2-timestamp datacube" — mutually impossible. That inconsistency survived sign-off,
cross-validation, implementation, **and the Opus code review** (which checked code-vs-spec but never
traced the runbook against `build_datacube`'s op chain — the reviewed guard test uses B04+SCL, which
was the tell). The implementer followed the spec faithfully. **No implementation defect was found by
the real run; the code verdict stands.**

**Runbook v2 issued** (`runbooks/32-mpc-baseline.md`) — v1 had four defects, all now fixed:
- **B04-only → `['B04','SCL']`.** Bonus: the band exemption goes from "moot" (the spec's word) to
  **live** — SCL must return `0` while B04 returns `−1000` on real data.
- **Over-fetch.** v1 downloaded the whole date range *between* `pre` and `post` → **9 items /
  1.7 GB**, not the promised 2. v2 uses two tight ±1 h windows.
- **"a few MB / no full-tile download" was false.** MPC assets are **full-tile (~110 km) COGs** —
  a single B04 measured **96–272 MB**. Prerequisites now state ~320 MB honestly.
- **PASS criteria that couldn't fail.** Step 2's `pass` only checked `failed_count == 0` (never the
  offsets); step 3's was a "plausible range" judgement, and its `mosaic_days=120` over a 120-day
  window gives **T=1**, not the "2 timestamps" it compared. v2 asserts the offsets explicitly and
  replaces the vague check with an **A/B against an unharmonized control** (same cube built twice,
  offsets forced to 0 in the control): post-baseline slice must equal control **exactly −1000** on
  non-clipping pixels; pre-baseline slice **bit-identical**. Writes `_result_step3.json`.

**Three findings logged as TODOs:**
- **#34 — MPC serves duplicate reprocessed acquisitions.** `20220301T100029` came back **twice**
  (processed `20220303` *and* reprocessed `20240604`) — same sensing time + MGRS tile, different
  item ids, so `_finalize_catalog_gdf`'s id-uniqueness check passes. Both downloaded (224+272 MB),
  both catalogued; `_stack_datacube` then merges two copies of one scene with an arbitrary
  tie-break. **Not radiometrically wrong** — spec 32 offsets each processing on its own baseline
  before the merge (the design earning its keep) — but wasted bytes + a silent arbitrary pick.
- **#35 — `build_datacube` requires SCL even when masking isn't wanted** (the root of the step-3
  crash). Deferred to its own spec: it changes a core contract, and TODO #11's non-optical sources
  (CHIRPS/ERA5) have **no SCL at all**, so they're blocked on it.
- **#36 — CDSE-vs-MPC speed comparison: PARKED by the user** (nothing to do now). Recorded with its
  confounds so they aren't re-derived: the "MPC is slow" reading is VPN × 9-items-not-2 × a
  duplicate × **full-tile copy for a 0.18 % ROI** (21.5 km² read out of a 12 100 km² tile). TODO #24
  already records that the local CDSE result was **link-bound and does not generalize to Azure** —
  so the honest version of this benchmark is an Azure-side one, and the dominant lever is plausibly
  windowed `/vsicurl` vs full-tile copy (TODO #31), not the source choice.

**Uncommitted** (no commit requested): runbook v2, spec 32 §Tests correction + banner, TODO #34–36,
this entry.

### Previous entry (spec 32 code review — PASS, merged + pushed)

**Review verdict: PASS — no code changes required.** Reviewed the spec-32 implementation
(`1cf1568` + `0da4d15`) against the signed-off spec, then **fast-forward merged
`spec32-mpc-implement` → `main`** and pushed to `origin/main`; the worktree was removed.

- **Independently re-verified** the implementer's claims (not taken on trust): `pytest -q` **234
  passed, 3 skipped**; `ruff check src/ tests/` clean. (Note for future sessions: the `.venv`
  editable install points at **main's** `src/`, so running a worktree's tests needs
  `PYTHONPATH=src` from inside the worktree — otherwise it silently imports the wrong `fsd`.)
- **The #10 guard test is real, not vacuous** — confirmed by mutation: deleting the
  `_apply_boa_offsets` call makes `test_build_datacube_harmonizes_boa_offset_before_median_mosaic`
  fail (restored immediately). Offset-after-median would give `clip(median(200,1200)−1000)=0` ≠ 200.
- **Confirmed against the spec:** D1/D2 ordering (offset applied right after `load_images`, before
  `dst_crs`/reference/resample/`median_mosaic`); D3 keys on `s2:processing_baseline`, not
  `item.datetime`, and **raises** on a missing baseline; `_is_reflectance` matches `^B\d`/`B8A` and
  exempts SCL/AOT/WVP/visual; catalog back-compat fills 0 on both `read` and `append`;
  `api.download`'s `creds` relaxation stays positionally back-compatible and still requires creds
  for `source="cdse"`; no out-of-scope creep (no Azure code, CDSE offset retrofit correctly left
  as TODO #30).
- **A subtle trap the implementation avoided:** rows dropped by `_load_images` get
  `image_index = -1` and are filtered out *before* `_apply_boa_offsets` iterates, so an unreadable
  image can never cause a `data_profile_list[-1]` mis-write.
- **Three minor, non-blocking notes** (logged in spec 32's banner, not fixed — none affect
  correctness): dead `mpc._mgrs_tile_from_item`; a CDSE-worded error message reachable from the MPC
  path via the reused `_finalize_catalog_gdf`; and **`planetary-computer` left unpinned** though the
  spec's open items asked to pin it — **pin it after the runbook's step-1 install reports the
  resolved version** (the one small follow-up worth doing).
- **Merge hygiene:** main's unrelated WIP (the `TODO.md` reflow + the two notebooks) was stashed
  before the merge and popped after — `TODO.md` auto-merged with **no conflict**, and both sides
  survived (reflow of item #26 intact; committed #30–33 + the #10 update present). The reflow and
  notebooks remain **uncommitted WIP**, per CLAUDE.md.

### Previous entry (Sonnet@medium implementation of spec 32)

**Implemented `specs/32-mpc-source-baseline-harmonization.md`** (signed off earlier the same day)
against baseline `030f6ac` on `main`, in an isolated worktree
(`.claude/worktrees/spec32-mpc-implement`, branch `spec32-mpc-implement`). To the letter, no
redesign. `pytest -q` **234 passed, 3 skipped**, `ruff check src/ tests/` clean.

- **New source `sources/mpc.py`** — MPC S2 L2A discovery (`pystac_client` + `planetary_computer`
  sign modifier, anonymous by default) and a **pure COG byte-copy** download (no `jp2->COG`
  conversion, no convert-process-pool — MPC assets are already COG). Reuses CDSE's generic
  `_finalize_catalog_gdf`/`_is_local_path`/`_roi_gdf` helpers (identical logic, no S3/CDSE
  specifics). `api.download` gains `source: "cdse"|"mpc"` (default unchanged, `"cdse"`); `"mpc"`
  does not require `creds`.
- **New additive catalog column `boa_add_offset`** (`catalog/catalog.COLUMNS`) — the S2
  processing-baseline reflectance offset (fixes correctness debt **#10** for MPC), derived from
  `s2:processing_baseline` (**keyed on baseline, not date** — covers the reprocessed-pre-2022-date
  trap). Back-compat: `TileCatalog.read`/`append` fill a missing column with `0` (old catalogs,
  CDSE rows for now).
- **`datacube.builder.flatten_catalog`** emits a per-band `boa_add_offset` (reflectance bands only,
  `raster/images._is_reflectance`); **`build_datacube` applies it per source image** (new
  `builder._apply_boa_offsets`, right after `images.load_images`, before `dst_crs`/reference/
  resample/mosaic) via the new `raster/images.apply_boa_offset` op (`clip(DN+offset, 0, 65535)`,
  nodata-safe). A build-time integration test proves a calendar window straddling the 2022-01-25
  cutover harmonizes **before** the median (the exact #10 failure mode).
- **New `[mpc]` extra** (`planetary-computer`); `runbooks/32-mpc-baseline.md` written (not run —
  Claude never runs networked scripts): one MGRS tile (`s2grid=476da24`), band B04 only, two
  acquisitions straddling the baseline cutover.
- **Docs updated:** `CHANGES.md` (new top entry), `TODO.md` (#10 marked partially-done for MPC;
  new #30–33: CDSE offset retrofit, Phase-2 stream-vs-copy fork, signed-URL re-sign, full
  `download_resume` orchestration for MPC), `RECIPES.md` (MPC download recipe), `specs/31` banner
  (§5 "stage-local-convert-put" flagged DELETED, retargeted to Phase 2 — not yet rewritten),
  `specs/10` pointer (MPC is another first-class source through the same storage seam), this entry.
- **Open items flagged for the runbook, not guessed in code** (per the spec): the live
  `s2:processing_baseline`/`s2:mgrs_tile` STAC property names, and whether `fsd.storage.transfer`
  streams cleanly over fsspec's `http` backend for signed MPC hrefs (may need `aiohttp`) — both
  surface naturally at the runbook's step 1/2.

**→ NEXT:** Opus@high review pass on branch `spec32-mpc-implement` (commit `1cf1568`, worktree
`.claude/worktrees/spec32-mpc-implement`, diffed against `030f6ac`) — Opus merges to `main` and
pushes once review passes. Then the **user runs** `runbooks/32-mpc-baseline.md` (real MPC network,
hotspot-OK — one tile, one band, two tiny COGs) and pastes back `_result_step2.json` + the step-3
spot-check. Committed this session (user asked); not yet merged/pushed.

## PRIOR (2026-07-16) — STRATEGY PIVOT: MPC source + baseline harmonization → spec 32 SIGNED OFF (Opus@high); P1 split into two phases; new standing practice (spec cross-validation)

**The plan pivoted from "CDSE download-to-blob for P1" to a two-phase MPC-first approach** (agreed
with the user via interview → grilling → doc cross-validation). Reasoning: MPC serves Sentinel-2
L2A as **already-COG on Azure**, so the whole `jp2→COG` conversion problem (spec 25 / the ugliest
part of the draft spec 31 §5) **evaporates**, and we get real Azure-native COGs to test datacube
creation fast.

**Two-phase shape:**
- **Phase 1 (local, hotspot-friendly) = `specs/32-mpc-source-baseline-harmonization.md` — SIGNED
  OFF (2026-07-16).** A new fsd-native **MPC source** (`sources/mpc.py`, reuses `pystac-client`
  discovery + `planetary-computer` signing behind a new `[mpc]` extra; download = **pure COG
  byte-copy**, no re-encode). Fixes **correctness debt #10** (the S2 processing-baseline
  `BOA_ADD_OFFSET`): MPC serves **raw unharmonized DN** and exposes **no `raster:bands`** offset, so
  fsd derives the offset from **`s2:processing_baseline`** (keyed on baseline, *not* date —
  reprocessing stamps ≥04.00 on old dates), stores it as an additive **`boa_add_offset`** catalog
  column, and harmonizes **at build, per source image, before the median mosaic** (a calendar window
  can straddle 2022-01-25) via `clip(DN−1000,0,65535)` for reflectance bands (SCL exempt) — keeping
  the **uint16 + nodata=0** datacube contract. Test = pytest (synthetic offset/clamp/flatten) + a
  **single-tile / single-band** runbook straddling 2022-01-25 (hotspot-sized).
- **Phase 2 (Azure at scale) = `specs/31` retargeted.** Its old §5 (CDSE stage-local-convert-put)
  is **to be deleted** (MPC removes conversion). The storage-seam mechanics (fsspec-native config,
  `to_vsi`, one `rio_open` wrapper, `DefaultAzureCredential` for `rise` writes) survive. **Open
  Phase-2 fork:** stream MPC COGs in-place via `/vsicurl` vs bulk-copy MPC→`rise` and stream from
  `rise` — **consciously deferred** to be *measured* after at-scale cloud build exists (user's call
  2026-07-16), not argued now. (fsd reads only a ~5 km window from a ~110 km tile; full-tile
  download amortizes only under high per-tile cell reuse.)

**Spec 31 status:** still DRAFT; it was improved this session (fsspec-native config + adlfs
auto-credential + SDK token-cache replaced the bespoke registry/refresh-margin — cross-validated
against Azure/adlfs/fsspec/GDAL docs) but is now **Phase 2** and not yet signed off.

**New STANDING PRACTICE (encoded in `CLAUDE.md` + memory [[spec-cross-validation-practice]]):**
every spec leaning on external facts must be **cross-validated against reliable online sources
before sign-off**, carrying a **per-source-credit** "Best-practice alignment / sources" section
(what *specific* fact each source contributed, named inline — not a bare URL list). **Spec-
validation web searches now have standing permission** (no prior ask); all *other* searches still
follow [[ask-before-websearch]].

**Governance flag (consciously accepted):** an MPC source is the "build more data sources
(#11/#21)" work the 2026-07-15 diagnostic parked pending the **rslearn Plan B/C** call — accepted
eyes-open (small, reuses STAC discovery, fastest unblock). rslearn decision still parked.

**→ NEXT:** user runs `/handoff` → **Sonnet@medium** session implements **spec 32** against the
signed-off text (Opus does not implement). Then Opus review, then the user runs
`runbooks/32-mpc-baseline.md`. Nothing committed this session (specs 31/32, CLAUDE.md, memory edits
all on disk, uncommitted — user may want to commit).

## PRIOR (2026-07-15) — project-state DIAGNOSTIC done (Opus@high) → verdict + P1-kickoff staged (access probe written, spec-first handoff next)

**The diagnostic (interview → exhaustive corpus read → grilling) is complete.** Deliverables:
memory [[fsd-diagnostic-triage]]; a one-page visual state map (Artifact:
`https://claude.ai/code/artifact/bcc50b17-914b-486d-a66b-102661ea34ca`); this PROGRESS entry.

**Verdict (user's Q = "am I accreting, or is there a critical path? and am I managing this well?"):**
NOT random scope-creep — TODO.md is well-triaged, nearly every item real. The pattern is: the project
keeps finishing *locally-completable* work *around* its critical path (P1) instead of *through* it,
because **P1 is blocked and the blocker was never named.** The rail literally shows it — solid through
P0.9, skips the blocked P1, lands on a *partial* P5 (serving 27–30). **User confirmed both:** the
serving PoC was legitimate + well-timed (active-learning/STACNotator interconnect talk had just
happened — fsd needed to prove it can connect), AND real procrastination on Azure (new/unfamiliar).

**Decisions reached (grilling):** (1) **P1 stays the goal**; serving is *banked*, not relabeled — do
NOT continue that thread (#28/#29 deferrable). (2) Move #1 = **clear the P1 blocker**; the blocker is
100% activation energy — user is at state (a): `az login` done, working access, just hadn't sat down.
(3) rslearn Plan B/C call **consciously parked** (orthogonal to P1) — *but do not build more data
sources (#11/#21) until it's made.* (4) Promote correctness debt **#10** (STAC raster:offset/scale
across S2 baselines — silent wrong-answers) above the serving/feature long tail. (5) **Spec-first
handoff:** the next session *writes* spec 31, it does NOT code.

**P1 access facts nailed down** — **concrete values live ONLY in `../P1_AZURE_SETUP.md` §3 +
`../AZURE_INFRA_PRIVATE.md`** (workspace root, uncommitted). Shape only, for the public repo:
the target storage account is **ADLS Gen2 (HNS)**; **account keys DISABLED** → auth is
**`DefaultAzureCredential` (az-login token), FORCED** (no key/SAS); GDAL driver = **`/vsiadls/`**,
NOT `/vsiaz/`. The real unknown = whether the user's **personal** identity has **Storage Blob Data
Contributor** (private doc only confirms the *compute UAMI* does) — the access probe is the definitive test.

**PROBE RAN GREEN (user, 2026-07-15): `"pass": true`, all 3 steps.** P1 ACCESS IS READY — confirmed
end to end over VPN through the exact seams fsd uses. Facts for spec 31 (also in `../P1_AZURE_SETUP.md`,
now fully green):
- Identity / subscription / resource group confirmed — **names + IDs in `../P1_AZURE_SETUP.md` §2**,
  deliberately not repeated here (public repo).
- **adlfs `DefaultAzureCredential` round-trip works** to the scratch prefix (370 B write=read)
  → the user's **personal identity HAS Storage Blob Data Contributor** (no admin grant needed — the 403
  risk is dead).
- **GDAL 3.10.3 opens the object via BOTH `/vsiadls/` and `/vsiaz/`** with `AZURE_STORAGE_ACCESS_TOKEN`
  → use `/vsiadls/` as canonical (ADLS Gen2), `/vsiaz/` fallback. Auth = `az account get-access-token
  --resource https://storage.azure.com/`, Entra-only (keys disabled).

**Also this session — raapid-infra tfvars refreshed (2026-07-15):** `rise` AML is now a **list of
clusters** — `default` (E64ds_v4 ×4 = 256 cores) **+ NEW `d16`** (D16d_v5 ×32 = **512 cores**); Batch
pool unchanged (128 cores). Concrete values in `../AZURE_INFRA_PRIVATE.md` + [[fsd-azure-infra]] memory.
**New parked fork (P2/P4, NOT P1):** runner seam targets Batch (128) but the big fleet is AML `d16`
(512) — a Batch-vs-AML dispatch choice for when P2 lands; parked alongside rslearn.

**→ NEXT:** user runs `/handoff "write + sign off spec 31 (P1 storage seam) from the probe results"`
→ fresh **Opus@high** session writes **spec 31** (spec-first — it does NOT code): add `azure-identity`
to the `[azure]` extra; thread `storage_options`/`storage=` through the verbs; adlfs `abfs://` + GDAL
`/vsiadls/` reads in fsd code; demo a **local datacube build doing all I/O against `rise` blob** over
VPN. Then Sonnet@medium implements against the signed-off spec. Nothing committed this session (docs
only: `P1_AZURE_SETUP.md`, `runbooks/31-p1-access-probe.md`, `../AZURE_INFRA_PRIVATE.md`, this entry).

## PRIOR (2026-07-15) — spec 30 (serving Tier 2: mini-MPC + stac-geoparquet) REVIEWED (Opus@high) + runbook RAN GREEN (user) → Tier 2 VALIDATED; TODO #16 also fixed

**Opus@high review of `faf8382` = PASS** (storage-seam staging, href-rewrite, both documented
deviations all sound; no floating tags). Three minor fixes applied on top: README route-naming line
corrected to `/searches/...`, `register_and_url.py` now writes a failure `_result.json` like its
siblings, `.gitignore` covers `.pgdata/`/`*.ndjson`/`_result_register.json`.

**Runbook `runbooks/30-tier2-mini-mpc.md` RAN GREEN (user, 2026-07-15): steps 1–6 all PASS** — tile
curl `200 image/png 50145`; QGIS renders the 300-cell Austria crop map in the discrete class colors
over the true (slanted) cell footprints through the full pgSTAC → stac-fastapi-pgstac →
titiler-pgstac register→searchId→XYZ path. Step 7 (STACNotator in-app) skipped — the explicitly
non-gating stretch (D-C). **fsd is "just another MPC"; the TODO #26 serving contract is proven end
to end (Tier 1 spec 29 + Tier 2 spec 30).** Two runbook-run bugs found + fixed:
`Dockerfile.titiler-pgstac` now `apt-get install`s **`libexpat1`** (rasterio, via rio-tiler, links
`libexpat.so.1` at import; `python:3.12-slim` omits it → the `raster` worker failed to boot); and the
runbook's Docker-up/directory-scoping + the step-5 curl `{z}/{x}/{y}` substitution (curl globs `{}`)
were clarified. New plain-language **`MINI_MPC_NOTES.md`** at the **workspace root** (outside the
public repo) — Docker primer + running issue log, per the user's request (memory
[[user-docker-infra-onboarding]]).

**Also fixed this session — TODO #16 (`flatten` multi-zone `coords.npy`):** `flatten` now reprojects
each cube's per-pixel easting/northing from its native CRS to **EPSG:4326 (lon, lat)** before
concatenation (`flatten._to_lonlat`), so a multi-UTM-zone training set no longer mixes incomparable
eastings/northings. Behavior change to `coords.npy` (CHANGES.md); new multi-zone test; **214 passed,
3 skipped**, ruff clean.

**Committed + pushed:** all the above is on **`origin/main` @ `60e5cc2`** (`WEB_CONCURRENCY=4` set;
review + runbook fixes; TODO #16 coords→4326). Upstream now tracked.

**→ NEXT (redirected 2026-07-15):** the user paused feature-work for a **project-state DIAGNOSTIC
walkthrough** — a fresh Opus@high session reads the whole corpus (all specs 00–30, ROADMAP, TODO,
every `.md`) to reconstruct *where we started → where we're going → where we are*, and answer the
user's core question: **am I accreting endless TODOs, or is there a critical path to P1?** The
diagnostic session must **interview the user first** about what they want out of it. Baton:
**`/tmp/fsd-handoff-project-diagnostic.md`**. **TODO #28 (render config → STAC render extension) is
deferred back into the queue** — it was the next feature but got redirected. Also still open after 30:
TODO #26 catalog-format full-migration, #29 (B02/B03, PARKED for wifi). **P1 = the Azure storage seam**
(`specs/10`; prereqs in `../P1_AZURE_SETUP.md`) has not started.

## PRIOR (2026-07-15) — spec 30 (serving Tier 2: mini-MPC + stac-geoparquet) IMPLEMENTED (Sonnet@medium) → hand to Opus for review, then the user runs the Docker runbook

**Sonnet@medium implemented `specs/30-tier2-mini-mpc-validation.md`** (signed off earlier the same
day). Implements **TODO #26 Tier 2** (the second half of the serving-contract validation; Tier 1 =
spec 29, DONE). Builds on spec 28 (true-polygon geometry) + spec 29 (the discrete crop-class colormap).

- **B — stac-geoparquet export (fsd core, additive) — DONE + verified.** New
  `catalog/stac_geoparquet.py` (`items_to_stac_geoparquet` / `stac_geoparquet_to_items`, staged
  through a local tmp file + the `fsd.storage` seam since the installed `stac-geoparquet==0.8.1` API
  wants a real path), new `[serving]` extra, `demos/mini_mpc/export_stac_geoparquet.py` CLI.
  `tests/test_stac_geoparquet.py` round-trip PASSES in a fresh `.venv-serving`
  (`pip install -e ".[dev,serving]"`; `215 passed, 2 skipped` full suite, `ruff` clean); the core
  `.venv` skips the test cleanly (`pytest.importorskip`). **Also smoke-run against the real 300-item
  Austria catalog** (`tests/outputs/demo_e2e/model_outputs/stac/`) — export + read-back both verified
  by hand (all 300 items round-tripped correctly).
- **A — local "mini-MPC" harness — scripts + runbook written, not yet Docker-run (Claude never runs
  Docker).** `demos/mini_mpc/` (`docker-compose.yml` pinning `ghcr.io/stac-utils/pgstac:v0.9.11`
  as-is + two locally-built images that install the **pinned stock PyPI packages**
  `stac-fastapi.pgstac==6.3.1` / `titiler.pgstac==3.0.0` on a slim Python base, since no published
  "just pull it" app-layer image exists upstream — README's table documents exactly what's borrowed
  vs. built, and why eoAPI's own compose couldn't be vendored verbatim (it `build:`s from a full
  monorepo checkout too)); `load_pgstac.py` (ndjson + href-rewrite → `/data` bind-mount — the
  href-rewrite logic was hand-verified against the real catalog: all 300 hrefs rewrite correctly);
  `register_and_url.py` (reuses `titiler_serve.build_colormap`; URL-building logic hand-verified with
  a mocked HTTP call). **One documented deviation from the spec's draft:** the installed
  `titiler.pgstac==3.0.0` names its routes `/searches/register` + `/searches/{id}/tiles/...` (response
  key `id`), not `/mosaic/register`/`searchid` — MPC's own product wraps the identical contract under
  different names (`CHANGES.md` + the script's docstring have the full note, à la spec 29's rio-tiler
  pin). `runbooks/30-tier2-mini-mpc.md` (7 steps; hard bar = steps 1–6, STACNotator-in-app a stretch).

**Living docs updated:** `CHANGES.md`, `RECIPES.md` (both new recipes), `TODO.md` #26 →
DONE-pending-runbook, `pyproject.toml` (`[serving]` extra), spec 30's banner → IMPLEMENTED.

**→ NEXT:** Opus review, then the **user runs** `runbooks/30-tier2-mini-mpc.md` (one-time cost =
building the two app images locally — small `pip install`s on a slim base, no satellite downloads;
recommend on wifi) and pastes back each step's `_result.json` + the QGIS screenshot. **Still open
after 30:** TODO #26 catalog-format full-migration (run_inference default → stac-geoparquet), TODO
#28 (render config → STAC render extension — makes the categorical color turnkey, no baked-in
`colormap` param), #29 (B02/B03 for true-color input imagery, PARKED for wifi).

## PRIOR (2026-07-15) — spec 30 (serving Tier 2: mini-MPC + stac-geoparquet) SIGNED OFF → hand to Sonnet

**Opus@high interview → `specs/30-tier2-mini-mpc-validation.md` SIGNED OFF (2026-07-15).** Implements
**TODO #26 Tier 2** (the second half of the serving-contract validation; Tier 1 = spec 29, DONE). Builds
on spec 28 (true-polygon geometry) + spec 29 (the discrete crop-class colormap). **Two deliverables:**

- **A — local "mini-MPC" harness** (`demos/mini_mpc/` + `runbooks/30-tier2-mini-mpc.md`): borrow the
  **stock eoAPI docker-compose** (pgSTAC + stac-fastapi-pgstac + titiler-pgstac), load the spec-28
  output STAC (300 Austria crop-map cells) via **`pypgstac` ndjson** (convert the JSON catalog we already
  write; **rewrite COG asset hrefs host→`/data` + bind-mount** the outputs dir so GDAL resolves them
  inside the container — the one non-obvious wiring step), then prove the **register→searchId→XYZ** MPC
  path renders. Categorical color rides in the tile **`colormap`** query param (reuse
  `titiler_serve.build_colormap`), `assets=output`, `nodata=255`, `resampling=nearest`. **Success = curl
  (search returns 300 items with true polygon geometry + register 200 + tile PNG) + a QGIS XYZ-layer
  visual** (the user asked for QGIS — now through the full pgSTAC→titiler path); STACNotator-in-app is an
  optional stretch (may need a STACNotator config/PR to add a custom MPC endpoint — not gating).
- **B — stac-geoparquet export** (fsd core, additive): new `catalog/stac_geoparquet.py` +
  `[serving]` optional extra (`stac-geoparquet`) + a `demos/mini_mpc/export_stac_geoparquet.py` CLU; the
  #26 north-star interchange format. **Round-trip pytest only** in this spec (items→geoparquet→items
  equal on id/geometry/bbox/dt/proj/asset); **not** wired into the run_inference default write path — that
  full catalog migration stays the #26 follow-on.

**Interview decisions (all 5 open-qs accepted as recommended):** new `[serving]` extra; new
`catalog/stac_geoparquet.py` module; href-rewrite + `/data` bind-mount; geoparquet round-trip pytest only;
Opus specs → **Sonnet@medium implements** the export + harness scripts → the **user runs the Docker
runbook** (Claude never runs Docker/pipeline, per CLAUDE.md). Non-goals: no Azure/production deploy (the
`rise` deploy is propose-only, separate), no input-imagery serving (B02/B03 = #29, parked for wifi), no
render-extension (#28), no STACNotator code change for the hard bar.

## PRIOR (2026-07-14, later) — specs 28 + 29 REVIEWED (Opus@high), MERGED to `main`, all runbooks PASS ✅

**Both serving-pivot specs are DONE: reviewed, merged, and validated end to end.** Merged fast-forward
into `main` (`50749e8`→`620441e`, "Implement specs 28+29"); **not pushed to origin** (per the user —
local merge only). The implementation baton was `/tmp/fsd-handoff-specs-28-29-review.md`.

- **Spec 28 (STAC geometry fix, TODO #27 DONE):** `catalog/stac.py::cog_outputs_to_items` gained
  `geometries={cog: geometry.geojson_path}` (+ `_read_footprint_geometry` helper +
  `cog_outputs_to_items_from_manifest(input_csv)` convenience wrapper). `api.py::_finalize_outputs`/
  `_resolve_inference_pairs`/`_run_inference_roi` thread `geometries` from `input.csv.shapefilepath`
  for both inference modes; `geometries=None` (bare COG lists, folder/list pre-built modes) keeps the
  old raster-bbox behavior unchanged. Missing/unreadable geometry **raises** (deterministic, no
  fallback). New `demos/regen_output_stac.py` + `runbooks/28-stac-geometry-regen.md`. 4 new tests;
  `BUGS.md` BUG-003; `CHANGES.md`; `specs/17` pointer; `TODO.md` #27 DONE.
- **Spec 29 (Tier-1 pre-styled XYZ, TODO #26 Tier-1 DONE):** new `demos/titiler_serve.py` (FastAPI +
  rio-tiler; `GET /cropmap/tiles/{z}/{x}/{y}.png` over `merged.tif`, discrete colormap from
  `e2e_austria.CLASS_COLORS`/`render.json`, `nodata=255` transparent, nearest resampling, permissive
  CORS) + a new `[titiler]` pyproject extra (isolated `.venv-titiler`, kept out of `.venv`) +
  `runbooks/29-tier1-stacnotator-byo.md`. 4 new tests (`tests/test_titiler_serve.py`,
  `pytest.importorskip("rio_tiler")` — skip cleanly in the core `.venv`). rio-tiler note: masking
  needs a `numpy.ma.MaskedArray` (the 2nd `ImageData` positional is `cutline_mask` in rio-tiler
  6/7.x, not an alpha mask) — fixed in `_empty_png`.
- **Opus@high review:** clean, no changes required. Verified the spec-28 no-fallback contract is
  atomic (all four `ValueError` paths fire inside `cog_outputs_to_items` before `write_stac_catalog`
  → no partial STAC), `geometries=None` correctly reserved for the manifest-less folder/list modes,
  `_resolve_inference_pairs`'s `-> (pairs, geometries)` change fully covered (one call site), the
  ROI-mode `input.csv` always carries `shapefilepath` (`workflows/create_datacube.py:90`), and the
  rio-tiler `MaskedArray` reasoning holds. `pytest -q` = 213 passed, 2 skipped; ruff clean.
- **Runbooks — ALL PASS (user ran, 2026-07-14):**
  - **28 regen:** the 300-item Austria demo STAC regenerated from `input.csv` → the slanted S2-cell
    polygons (not raster boxes). *(Doc fix: the runbook's step-2 spot-check path was missing the
    `fsd-inference/` collection subfolder — corrected; the regen script itself was always right.)*
  - **29 curl + QGIS:** the pre-styled XYZ server renders the categorical crop map correctly (discrete
    colors, nodata transparent) — confirmed visually in QGIS.
  - **29 STACNotator BYO:** the running `titiler_serve` XYZ URL loads as a Bring-Your-Own-XYZ layer in
    a locally-run STACNotator dev stack (`make dev-init`) — the strongest external confirmation. (GEE
    creds are irrelevant to BYO mode; Docker daemon just had to be running.)

**Serving pivot — Tier 1 is now fully validated.** fsd emits standard STAC (true footprints) + a
pre-styled categorical XYZ that STACNotator consumes as-is.

**→ NEXT (Opus to spec):** **TODO #26 Tier 2** — a local pgSTAC + titiler-pgstac "mini-MPC" so
STACNotator drives fsd's STAC through the same two-API path it uses for MPC (the richer, non-BYO
serving mode). Also open: **TODO #28** (model-dev render config → STAC render extension — the
`render.json` seam already stubbed in `titiler_serve.build_colormap`) and **#29** (B02/B03 band
expansion for true-color input imagery — PARKED for university wifi). Not pushed to origin (commit/push
only on request, per CLAUDE.md).

## PRIOR (2026-07-14) — STRATEGIC PIVOT on serving: fsd emits standard STAC+COGs+render config → STACNotator (via stock pgSTAC+titiler-pgstac); the fsd Leaflet dashboard is CANCELLED

**What happened:** started task (2) as a *local titiler+Leaflet dashboard to verify the inference STAC*
(explainer `demos/TITILER_LEAFLET.md` + `specs/27` written, MosaicJSON DB-free design signed-off-pending).
A design discussion then **reframed the whole thing** and `specs/27` is **SUPERSEDED — do not implement**.

**The pivot (all agreed with the user, 2026-07-14):** the user cloned NASA Harvest's **STACNotator** (a
React+OpenLayers imagery-annotation tool) into the workspace as read-only reference; I digested it →
**`../STACNOTATOR_DIGEST.md`** (workspace root, NOT in the fsd repo — never committed). Key finding:
**STACNotator IS the viewer**, and it consumes **MPC's two APIs** — a STAC API (CQL2 search + Sort) + a
**titiler-pgstac** data API (`/mosaic/register` → `searchId` → XYZ `/mosaic/{searchId}/tiles/{tms}/{z}/{x}/{y}`
+ viz params). So:
- **fsd builds NO dashboard.** fsd's job = emit artifacts standard enough that a **stock eoAPI stack
  (pgSTAC + stac-fastapi + titiler-pgstac)** serves the XYZ endpoints STACNotator consumes → fsd becomes
  "another MPC". **3-layer seam:** fsd (COGs on blob + `stac-geoparquet` catalog + render config) → stock
  serving infra (platform/`rise` or fsd-adjacent — *a deploy decision, not fsd code*) → STACNotator.
- **Catalog → `stac-geoparquet`** for BOTH CDSE downloads and model outputs (option (b): keep the internal
  working `catalog.parquet` for compute now; full migration a follow-on). STAC is justified precisely
  because it feeds pgSTAC/titiler-pgstac + is the interop lingua franca; MosaicJSON was the throwaway.
- **Model-dev display config → STAC Render Extension** (`renders` on the output collection) = the standard
  "how to display my output"; titiler-pgstac serves it natively (verified). Categorical crop map uses its
  custom `colormap` object (better than STACNotator's self-hosted `colormap_name`).
- **Scale goal:** many projects, MANY models/outputs, all conveniently on STACNotator.

**Locked decisions:** (1) no bespoke fsd dashboard/repo — STACNotator + stock serving; (2) the stock
pgSTAC+titiler-pgstac stack runs as **platform infra**, fsd owns only the **catalog/COG/render contract**;
(3) **model outputs first**, input-imagery viewing + **B02/B03 band expansion PARKED for university wifi**
(mobile-hotspot now — no big downloads); (4) validate in two tiers — **Tier 1** pre-styled XYZ into
STACNotator BYO (fast, hotspot-OK, no download), then **Tier 2** local pgSTAC+titiler-pgstac "mini-MPC".

**Captured as TODO #26 (serving contract + validation), #27 (STAC-geometry fix — now serving-critical),
#28 (render config → STAC render extension), #29 (B02/B03 expansion, parked).** `specs/27` +
`demos/TITILER_LEAFLET.md` both carry a SUPERSEDED/concepts-primer banner. **A real finding surfaced:**
`cog_outputs_to_items` writes each Item's geometry as the raster bbox (`stac.py:183`), not the true
S2-cell polygon in `<cell>/geometry.geojson` → over-claims coverage; matters for `ST_Intersects`/pgSTAC
search (TODO #27).

**TWO SPECS DRAFTED + SIGNED OFF (2026-07-14):**
- **`specs/28-stac-output-geometry-fix.md`** (TODO #27) — the STAC item-geometry fix, **manifest-driven**
  per the user: `cog_outputs_to_items(cog_filepaths, geometries={cog: geom_path})` sources each Item's
  footprint from `input.csv.shapefilepath` (deterministic — no sibling-file discovery, no raster-box
  fallback; missing geometry raises). Both inference modes + a `demos/regen_output_stac.py` feed it from
  `input.csv`. Regenerates the existing 300-item STAC. +tests. **Hotspot-friendly.**
- **`specs/29-tier1-prestyled-xyz-validation.md`** (TODO #26 Tier 1) — a minimal `demos/titiler_serve.py`
  serving `merged.tif` as a **param-free pre-styled XYZ** (`GET /cropmap/tiles/{z}/{x}/{y}.png`,
  hand-rolled over rio-tiler: discrete categorical colormap + nodata=255 transparent + nearest, CORS on),
  from a `render.json`/`CLASS_COLORS` config. **No viewer** — validated by pasting the URL into
  **STACNotator's Bring-Your-Own-XYZ** (QGIS XYZ as a quick pre-check). Replaces the cancelled `specs/27`
  `titiler_serve`. **Hotspot-friendly** (serves existing `merged.tif`).

**→ NEXT:** hand off to a **Sonnet@medium** session to implement **specs 28 + 29** (independent — either
order, or parallel). Both need no downloads. After they land + Opus review, the Tier-1 runbook is the
user's STACNotator BYO check. **Still to spec (Opus):** TODO #28 (model-dev render config → STAC render
extension) and TODO #26 **Tier 2** (local pgSTAC + titiler-pgstac mini-MPC — heavier, do when convenient),
**#29** (B02/B03 band expansion — PARKED for wifi). Nothing committed yet; `specs/{27,28,29}`,
`demos/TITILER_LEAFLET.md`, `TODO.md`, `PROGRESS.md` edits are on disk, uncommitted.

## PRIOR (2026-07-13 pm) — FULL Austria e2e EXECUTED; `E2E_AUSTRIA.md` is now the single go-to doc; next = titiler/Leaflet STAC-verify spec (task 2)

**The full Austria e2e ran for real, end-to-end, and PASSES** (real CDSE download → datacube → train on
real EuroCrops → inference → crop map). Everything on `main` (pushed). Run: Waldviertel AT_ROI,
2018-04-01..09-30, T=10, `--cores 8`; **207 granules / 44.61 GB**, **300 grid cells**, 900 train fields
(9 classes); `merged.tif` **6830×6868 EPSG:32633, 99.2% valid**. Timing **~100 min** (download 45% /
inference 44% dominate). Numbers stitched (download+train from pass 1, inference from a clean re-pass) —
see `demos/E2E_AUSTRIA.md §8`.

**3 issues the full run surfaced + FIXED (213 pytest / ruff clean):**
- **demo step 5 crashed** — `run_inference` called without the required `output_folderpath` →
  `PreflightError`; now passes `OUTDIR/model_outputs`. Demo-only.
- **STAC item-id collision (real `src/fsd` bug)** — `cog_outputs_to_items` derived the item id from the
  COG filename stem (constant `"output"`) → `collection.json` had N identical links + 1 item file on
  disk. Fixed to derive from the per-cell folder (`_output_item_id`) + a uniqueness guard; strengthened
  `test_run_inference_writes_cogs_and_stac` (asserts distinct ids). `merged.tif` + per-cell COGs were
  unaffected. Validated on the real run (300 links, 300 unique).
- **demo step 2 metric** now reports the honest **aggregate (wall)** transfer rate + verdict (was the
  misleading per-stream), matching `download_cli`; cost_model feeds `estimate.py` the aggregate rate.

**Also:** crop_map/NDVI recolored via a semantic + separable `CLASS_COLORS` dict (was pink grassland);
user regenerated the 3 committed `demos/figures/`.

**Phase-2 doc work DONE — `E2E_AUSTRIA.md` is the single go-to doc:** §8 filled from the real run; the
safe download runner (`python -m fsd.sources.download_cli`: `--dry-run`/`--stop-file`/
`--max-concurrent-s3`/`_result.json`, the probe/per-stream/wall rates) threaded into §2 + a §5 tip;
**Appendix C** ("real bugs full-ROI runs caught": spec-20 tile-merge, spec-26 STAC, multi-zone merge);
**`demos/README.md`** shrunk from the stale Ethiopia writeup to a thin redirect.

**Two TODOs opened (do NOT tangent now):** **#24** re-tune `max_concurrent_s3` per Azure region/pool
(local run was **link-bound**: probe 26 vs aggregate 17 MB/s, 4 streams slower than 1 — a laptop-uplink
property that inverts on a datacenter NIC); **#25** fine-grained per-cell inference timing (model-load /
build / predict / COG-save) + kill the per-cell model reload — found `cubes_per_task` is silently
ignored in ROI mode (`api.py:793`), so the bundle reloads 300× (per-cell "infer" ≈ flat ~7.8s model
load, not predict). Discussion-only until we decide it's worth specing.

**→ NEXT: task (2) — titiler + Leaflet explainer doc + a detailed spec for Sonnet** to stand up a basic
tile server + Leaflet dashboard that verifies the inference **STAC catalog + COGs** (ROADMAP P5 /
TODO #14). Handoff being prepared. NOTE: actually *running* titiler needs `model_outputs/{stac,cells}`
COGs under `tests/outputs/demo_e2e/` — the user may delete that to free space, so the titiler work will
regenerate them via a fast **download-free** inference re-pass (cells skip). The doc + spec can be
written regardless.

## PRIOR (2026-07-13 am) — spec 26 confirm-run EXECUTED for real + pipeline hardened; next = Austria go-to doc

**The spec-26 network confirm-run was run for real (CDSE, 3.5 GB, Austria 1-MGRS slice) and PASSES.**
Everything on `main` (pushed, HEAD `69e6517`). Fresh-download `_result`: `status=ok`, 65/65 files
(13 granules × 5 = 4 bands + MTD_TL.xml), `failed=0`, `skipped=0`, gb=3.50, integrity verified on disk
(52 tif + 13 xml, 0 leftovers, 13 catalog rows). **Throughput baseline: probe 25 / per-stream 4.8 /
wall 19 MB/s → link-bound, 4 transfer streams slightly SLOWER than 1.**

**Bugs/gaps this real run surfaced and we FIXED this session (all committed + tested, 209 passed):**
- `download()` crashed on a **fresh `--dst`** (disk-usage probe before makedirs) → now `fs.makedirs`
  the local root [spec 25 latent bug].
- `format_download_plan` **contradicted itself** at `missing=0` ("not present" + a download cmd) →
  fixed [spec 23 latent bug].
- `_result.json` **`expected`/`error` were dead** (`{}`/`None`) → now populated; a crash writes a
  `status=failed` result before re-raising; new `--expected-json` merges runbook criteria [spec 26 §4].
- **stop-file felt slow + silent** → now prints `stop requested — draining N…` within ~1s
  (`STOP_CHECK_EVERY_S=1.0`, decoupled from `PROGRESS_EVERY_S`); the ~`max_staged` overshoot is the
  clean-drain-by-design (no partial files); `--max-staged` trades it.
- **misleading throughput metric** → added `transfer_wall_seconds` + `wall_transfer_mb_per_s` (honest
  all-streams rate) and a **`--max-concurrent-s3`** knob to sweep stream count. Runbook step-4 rewritten.
- Silent startup phases (probe + planning) now labelled; `.gitignore` gained `.claude/`.

**Commits (all pushed to `main`):** `8bb1882` gitignore, `c822654` startup labels, `aa20279` makedirs
+ expected/error, `b4b1bf5` format_download_plan, `2f0b530` stop-file ack, `69e6517` wall metric +
`--max-concurrent-s3`. (Plus `356f07b` = the merged spec-26 offline half.)

**→ IMMEDIATE NEXT (user is on university wifi, ready to run): execute the FULL Austria e2e.**
Runbook **`runbooks/27-austria-full-e2e.md`** is written + on `main`. It runs `demos/e2e_austria.py`
(FULL mode: real CDSE download of the whole AT_ROI, Apr–Sep, → datacube → train on real EuroCrops
labels → inference → crop map). Size estimate (scaled from the confirm-run): ~2–4 MGRS tiles / ~80–160
granules / ~20–45 GB / ~1–1.5 hr. **Step 0 = a full-ROI dry-run to size it exactly before committing;
Step 1 = `rm -rf imagery/` for clean §8 numbers; Step 2 = the backgrounded run; Step 3 = paste back
`timings.json` + coverage.** The demo's download uses `download_resume` directly (no `--stop-file`;
Ctrl-C + re-run resumes). Note the AT inputs are REAL EuroCrops ground truth in the test region
(labels ARE meaningful; the *point* is infra, not model quality — the earlier "toy/Ethiopia" framing
is stale). `AT_ROI` = Waldviertel (~14.6–15.5°E, 48.4–49.0°N, single UTM-33), 900 train fields.

**→ THEN (the pre-P1 goal): make the Austria end-to-end the GO-TO USER DOCUMENT.** Fill `E2E_AUSTRIA.md
§8` from runbook 27's output, and reconcile the two demos docs (this is the ROADMAP pre-P1 deliverable,
not new pipeline code):
- `demos/README.md` — **STALE**: describes the old Ethiopia offline demo, references
  `demos/e2e_ethiopia.py` (renamed to **`e2e_austria.py`**) and `shapefiles/inference_roi.geojson`.
  Superseded by `E2E_AUSTRIA.md`.
- `demos/E2E_AUSTRIA.md` — the intended go-to guide, but: **§8 "Results (fill from a real run)" is an
  empty placeholder** we can now fill with the real confirm-run numbers; and it has **zero mention of
  the safe download runner** (`python -m fsd.sources.download_cli`, `--stop-file`, the confirm-run,
  spec 26) — the whole download story we just built + validated. §2 predates all of it.
- Decide: fold `README.md` into `E2E_AUSTRIA.md` as the single canonical doc (thin redirect README),
  and thread the real download step + numbers through it. Handoff doc: `/tmp/fsd-handoff-austria-doc.md`.

## PRIOR (2026-07-11) — spec 26 offline half REVIEWED (Opus@high): PASS on the hard stuff, 2 small fixes queued

**Opus@high review of the spec-26 offline half (in the worktree `.claude/worktrees/spec26-download-cli`).**
Verified **correct** (do not touch): the `should_stop` throttle is race-free (`_stop()` runs only in the
single submit-loop thread; callbacks never touch `last_stop_check`/`stop_cached`; sticky `stopped` set
under `lock`, read after pool join); **no `sem_staged` permit leak** at either checkpoint (top-of-loop
break pre-`acquire`; post-`acquire` release-then-break); `download_resume` stop-before-cooldown ordering
right (a user stop never enters cooldown); `--dry-run` touches zero band bytes; `_fmt_progress`
`ETA ~?`-until-`done>0` math correct. Local `pytest` 55 passed on touched files, `ruff` clean.

**Found 2 defects → fix in a Sonnet@medium session** (handoff written:
`/tmp/fsd-handoff-spec26-sonnet-fixes.md`, exact code + 2 new tests):
- **Fix 1 (correctness):** the CLI's exit-code/`status` gates on `sum_results`' **summed**
  `failed_count`, which over-counts failures a later resume pass recovered → a successful-but-flaky
  run reports `status="failed"`/exit 1 (contradicts the runbook's own step-3 integrity PASS; the demo
  treats the same number as a soft warning). Fix = judge the **terminal pass** (download_resume's own
  break condition), treat empty `results` (stop before pass 1) as `stopped`, keep summed counts as
  metrics + add `failed_total` diagnostic. Exit 0 on clean-or-stopped preserved.
- **Fix 2 (usability):** a stale `--stop-file` (e.g. `/tmp/fsd.stop` left after a stop) makes the
  documented "re-run to resume" an instant no-op stop. Fix = runbook says `rm -f` the stop-file before
  resuming + a tiny CLI startup warning when the stop-file already exists.
- **NOT fixed (left for the user):** the runbook's `missing_count [5,10]` range is likely low
  (~12 granules for a 2-month single-tile window at ~5-day S2 revisit); user decides whether to widen.

**Next: Sonnet@medium implements the 2 fixes** (target: `pytest` **203 passed, 1 skipped**, ruff clean),
then hand off + clear. The network confirm-run (`runbooks/26-download-confirm-run.md` step 2 onward)
still waits for the user on a real (non-hotspot) connection.

**UPDATE (2026-07-11, Sonnet@medium):** both review fixes landed — CLI completion gate now judges the
terminal pass (`results[-1]`) instead of `sum_results`' summed `failed_count`, empty `results` maps to
`status="stopped"`, new `metrics.failed_total` diagnostic; stale-`--stop-file` startup warning added +
runbook step-2 now says `rm -f` it before resuming. `pytest -q` = **203 passed, 1 skipped**, `ruff`
clean. Worktree left uncommitted per CLAUDE.md (commit only on request).

## PRIOR (2026-07-11) — spec 26 offline half IMPLEMENTED (safe download CLI + should_stop seam)

**Implemented in a Sonnet@medium session against `specs/26-safe-download-runner.md` (offline
half only — no network run, per CLAUDE.md).** Landed, all contained to `sources/cdse.py` +
one new module:
- `should_stop: Callable[[], bool] | None = None` kwarg on `download()`/`download_resume` (spec
  §1): checked in the submit loop at the two existing checkpoints, throttled to
  `config.PROGRESS_EVERY_S`, identical halt-new-submissions-only semantics to `tripped`/
  `pool_broken`. New additive `DownloadResult.stopped`; `sum_results` ORs it; `download_resume`
  passes `should_stop` through + `if r.stopped: break` + a pre-pass check.
- New `src/fsd/sources/download_cli.py` (`python -m fsd.sources.download_cli`): `--dry-run`
  (plan only, zero band bytes, no probe), `--stop-file` (builds the `should_stop` closure), an
  optional single `probe_throughput` on the real path (`--no-probe` to skip), writes the spec-24
  `_result.json`; exit code 0 on clean-or-stopped, non-zero on failed/tripped/pool_broken.
- `_fmt_progress` ETA edge case: `ETA ~?` until `done>0` (was misleadingly `ETA 0m`).
- `runbooks/26-download-confirm-run.md` — fully written offline (self-contained `expected`
  block: step-1 `missing_count` in `[5,10]`, step-2 clean `status=ok`/`failed=0`/`stopped=false`,
  step-3 integrity script, step-4 report, optional stop drill). **Not run** — the network half
  (mobile-hotspot pause) is deferred to whenever the user has a real connection.
- Tests: 8 new (`tests/test_cdse.py` — should_stop mid-pass halt via watchdog + `max_staged=1` +
  `_SyncExecutor` determinism, `should_stop=None` no-op, `download_resume` breaks on stopped pass
  no cooldown, `sum_results` ORs `stopped`, `_fmt_progress` ETA `~?`/`~Nm`; new
  `tests/test_download_cli.py` — dry-run zero-bytes + result-json, real-path wiring +
  `--stop-file` predicate + exit-code mapping, missing-creds guard). `pytest -q` = **201 passed,
  1 skipped** (all 47 original `test_cdse.py` regressions + 154 other pre-existing tests
  unaffected); `ruff check src/ tests/` clean. Docs updated: `CHANGES.md`, `RECIPES.md`, `README`
  (one-line pointer), `TODO.md` (#23, cost_model persistence follow-up).

**Next: Opus@high review pass**, then hand off + clear (per spec 26's deliberate pause) — the
confirm-run itself (runbook step 2 onward, real CDSE download) waits for the user on a real
connection; a later session verifies the pasted `_result.json` against the runbook's own
`expected` block.

## PRIOR (2026-07-11) — spec 25b REVIEWED (PASS) + spec 26 SIGNED OFF (safe download runner)

**Spec 25b review (Opus@high) = PASS.** Traced the exception-safety invariant through every
callback path (transfer ok→convert / submit-raises / cfut-raises / failed / skipped / no-convert):
`_finalize` runs exactly once per item, each acquired `sem_staged` permit releases exactly once,
`remaining`/`sem_staged` never sit behind a fallible call. No double-release/double-finalize. The
beyond-spec `flush_lock` is correct + necessary (serializes concurrent chunk-flush parquet writes;
never nested with `lock` → no deadlock; end-of-run flush is post-pool-join so needs none).
Re-queue-on-failure is safe because `catalog.append` is idempotent upsert-by-id (union files).
Verified: `test_cdse.py` 47 passed, full suite **193 passed / 1 skipped**, ruff clean; docs
(CHANGES §25b, TODO #22, spec-25 pointer) accurate. Minor non-blockers noted (tautological assert in
test 1; `transfer_pool.submit` raise→loud-exit-not-hang; persistent-flush-failure metric undercount
recovered by resume) — none warrant a change.

**→ `specs/26-safe-download-runner.md` SIGNED OFF (2026-07-11), C1–C6 accepted as drafted.** The
first real CDSE network exercise of the spec-25/25b pipeline, as a **safe runner + confirm-run**.
Locked (interview): **D1** one spec = CLI + confirm-run; **D2** a thin **CLI wrapping
`download_resume`** (`python -m fsd.sources.download_cli`), NOT a Snakemake unit-of-work; **D3**
`--stop-file` checked **mid-pass** via a generic `should_stop` predicate at the two submit-loop
checkpoints (throttled to `PROGRESS_EVERY_S`); **D4** confirm-run = tiny **1-MGRS-tile** Austria
slice (~7 granules / ~2 GB). Additive `DownloadResult.stopped`; `--dry-run` = `plan_download` only
(**zero band bytes**, no probe); `_fmt_progress` gains rate+ETA; `_result.json` per spec 24; exit
code doubles as PASS/FAIL (0 on clean OR user stop). Untouched: `_transfer_one`/`_convert_one`/
`to_cog`/discovery/circuit-breaker/`pool_broken`.

**⚠️ DELIBERATE PAUSE (mobile-hotspot).** Spec 26 splits at a network seam. **Offline half**
(implement + review with NO network): the CLI, the `should_stop` seam, `DownloadResult.stopped`,
`_fmt_progress` ETA, all pytest (monkeypatched), docs, **and the fully-written runbook
`runbooks/26-download-confirm-run.md`**. **Network half** = runbook **step 2 onward** (real
download → integrity → report). After 26 is implemented + reviewed we **hand off + clear**; the
user runs the confirm-run only on a real (non-hotspot) connection, whenever available, and pastes
the `_result.json` back — verified against the runbook's **self-contained `expected` block**, not
this conversation.

**Next step: implement spec 26 (offline half) in a fresh Sonnet@medium session** (user runs
`/handoff`, `/model sonnet` + `/effort medium`, points it at `specs/26-safe-download-runner.md`).
Opus does NOT implement. After it lands + Opus review → hand off + clear → confirm-run later.

## PRIOR (2026-07-11) — spec 25b IMPLEMENTED (pipeline exception-safety / no-hang fix)

**Implemented in a Sonnet@medium session** against the signed-off spec (contained to
`sources/cdse.py`: the `download()` callbacks + submit-loop stop condition, + additive
`DownloadResult.pool_broken`, + the one-liner OR in `sum_results`). `pytest -q` = **193 passed, 1
skipped** (42 original `test_cdse.py` tests unchanged + 5 new spec-25b tests: pool-submit-raises
no-hang, convert-done-result-raises no-hang + permit release, PoolBroken breaker-neutrality,
catalog-flush-failure no-hang + resume recovery, `sum_results` ORs `pool_broken`); `ruff check
src/ tests/` clean; no network run (per CLAUDE.md — spec 26's job).

**One thing found beyond the spec's explicit text, needed for correctness:** moving the chunk-flush
catalog write **outside** the counters lock (spec §3) means concurrent flushes of *different*
snapshots can now run truly in parallel — which would race-write the same parquet file and corrupt
it (caught by a flaky-`_append_downloaded` regression test: lost a row + a `thrift deserialize`
error on the next write). Added a dedicated `flush_lock` around just the `_append_downloaded` call
(not the counters) — serializes the I/O without blocking `_finalize`'s metric updates behind it,
preserving the spec's intent.

Docs updated: `CHANGES.md` (new entry under spec 25), `TODO.md` (#22 per-granule convert
quarantine, deferred), `specs/25-download-convert-redesign.md` (status line points to 25b),
`PROGRESS.md` (this entry) + memory `fsd-status`.

**Next: switch back to Opus@high for a review pass**, then start the **spec 26** interview (safe
runner `--dry-run`/`--stop-file`/progress + the measured confirm-run — the first real CDSE network
exercise of this pipeline).

## PRIOR (2026-07-11) — spec 25 REVIEWED (Phase 1) + spec 25b SIGNED OFF (pipeline hang fix)

**Opus@high Phase-1 review of the spec-25 implementation (`76b2cd9`) is done.** The four flagged
concurrency concerns (max_staged=1 breaker determinism, semaphore balance, remaining/loop_finished/
all_done drain, `_default_max_staged` cog-gating) all verified **correct**. `pytest tests/test_cdse.py`
= 42 passed, ruff clean.

**One real defect found (not previously flagged):** an unhandled exception in a completion callback
leaks `remaining`/`sem_staged` → `download()` hangs forever on `all_done.wait()` (finally unreachable).
Triggers: (1) **BrokenProcessPool** — a convert worker segfaults (GDAL on a bad granule) or is
OOM-killed → `cfut.result()` / `pool.submit()` raise before release+finalize; `add_done_callback`
swallows the exception so the drain never completes. (2) `catalog.append` (parquet flush) raising
under the lock in `_finalize`, before the `remaining` decrement. Tests miss it (injected fake
executors never break). This is exactly the silent-hang failure mode spec 26's "safe run" premise is
meant to exclude, so it's fixed **first**.

**→ `specs/25b-pipeline-exception-safety.md` is SIGNED OFF (2026-07-11), C1–C6 as recommended.** Fix =
make `_on_transfer_done`/`_on_convert_done`/`_finalize` exception-safe so every submitted item
finalizes once and every permit releases once, with `remaining`/`sem_staged` moved off any fallible
call (pool submit, process result, parquet write); add additive `DownloadResult.pool_broken` (clean
submit-loop stop on a dead pool; `download_resume` retries with a fresh pool, no cooldown);
`"PoolBroken"` reason is breaker-neutral (like `ConvertError`); move the catalog flush off the lock;
no-hang tests via a watchdog thread + `join(timeout)` (no pytest-timeout dep).

**Next step: implement spec 25b in a fresh Sonnet@medium session** (user runs `/handoff`, `/model
sonnet` + `/effort medium`, points it at `specs/25b-pipeline-exception-safety.md`). Claude (Opus) did
NOT implement — Opus reviews/specs, Sonnet implements. After 25b lands + review, proceed to **spec 26**
(safe runner + measured confirm-run).

## PRIOR (2026-07-11) — spec 25 IMPLEMENTED (download/jp2→COG process-pool redesign)

**Implemented in a Sonnet@medium session** against the signed-off spec (contained to
`sources/cdse.py` + `config.py`). `pytest -q` all green (188 passed, 1 skipped) and `ruff check
src/ tests/` clean; **no network run** (per CLAUDE.md — that's spec 26's job). Docs updated:
`CHANGES.md` (new top entry), `TODO.md` (item (b) marked DONE), `specs/14-cog-on-download.md`
(pointer updated), `config.py` comments.

**What landed:** `_transfer_and_convert` replaced by `_transfer_one` (thread stage, fail-fast
retry, writes to `dst+".src.jp2"` when `needs_convert`) + `_convert_one` (top-level/picklable
process stage, `to_cog` + staging cleanup in `finally`); `_download_one` kept as the sequential
wrapper (its direct-call tests pass unchanged) but `download()` no longer calls it — it drives the
A2 pipeline: a `MAX_CONCURRENT_S3`-wide transfer `ThreadPoolExecutor` + a lazily-created
`MAX_CONVERT_PROCS`-wide `ProcessPoolExecutor` (spawn), chained via `add_done_callback`, bounded by
a `sem_staged` `BoundedSemaphore`. New `config.py` constants `MAX_CONVERT_PROCS`,
`STAGING_DISK_FRACTION`, `STAGING_ITEM_GB`; new `cdse._default_max_staged` (disk-aware sizing) and
`cdse._make_convert_pool` (the lazy-pool factory seam tests monkeypatch). Circuit breaker rewritten
to streaming/transfer-failures-only semantics; `chunksize` repurposed to catalog-flush cadence only.
New `download`/`download_resume` kwargs `max_convert_procs`/`max_staged`/`convert_executor` (all
defaulted, backward-compatible). Test suite: 5 unchanged regression tests still pass, 1 rewritten
(`test_circuit_breaker_trips_and_stops_early`, now forces determinism via `max_staged=1`), 15 new
tests (`_transfer_one` × 5, `_convert_one` × 2, cog=True pipeline via injected `_SyncExecutor`,
backpressure bound via `_BlockingConvertExecutor`, lazy-pool × 2, `_default_max_staged`).

**Next step: spec 26** (safe runner — `--dry-run`/`--stop-file`/progress + the measured
transfer-vs-convert-split confirm-run over a real CDSE download). That is the first real network
exercise of this pipeline; not run yet.

## PRIOR (2026-07-11) — spec 25 SIGNED OFF (download/jp2→COG redesign) — ready to implement

**Spec `specs/25-download-convert-redesign.md` is SIGNED OFF; next action = implement in a fresh
Sonnet@medium session** (spec 24 D3/D5 — user runs `/handoff`, switches `/model sonnet` + `/effort
medium`, points it at spec 25). Claude did NOT implement (Opus plans, Sonnet implements).

**The fix (all in `sources/cdse.py` + `config.py`; read/build path, `to_cog`, `DownloadResult` shape
untouched):** conversion currently runs **inline on the 4 transfer threads** and GDAL's `to_cog`
**holds the GIL** → starves downloads (observed: 8.8 MB/s probe but ~0.2 file/s aggregate). Redesign =
split the per-file worker into `_transfer_one` (thread stage) + `_convert_one` (top-level, picklable,
**process** stage), and run them as **one continuous A2 pipeline**: `ThreadPoolExecutor(MAX_CONCURRENT_S3=4)`
transfers → each completion chains its staged JP2 to `ProcessPoolExecutor(MAX_CONVERT_PROCS=min(cpu,8),
spawn)` via `add_done_callback`; a `BoundedSemaphore(MAX_STAGED)` bounds staged-but-unconverted JP2s.

**Locked decisions (C1–C6 all accepted as recommended):** callbacks + single `sem_staged` (C1); keep
`_download_one` as a sequential wrapper so its tests survive, `download()` won't call it (C3);
circuit breaker → **streaming stop on consecutive *transfer* failures only** (rewrite the one breaker
test) (C4); new keyword knobs `max_convert_procs`/`max_staged`/`convert_executor` (the injected
executor is the in-process test seam) + pass-through on `download_resume` (C5); **keep ingest
overviews** (D2 — convert stays the ~15 s/file ceiling, accepted); **disk-aware `MAX_STAGED`** =
`min(MAX_CONCURRENT_S3 + 2*MAX_CONVERT_PROCS, free*0.25/0.2GB)`, sized once at start, **cap not a
lever** (C6/D5). `chunksize` repurposed → catalog-flush cadence. Confirm-run deferred to **spec 26**.

**Concurrency-familiarization artifacts (workspace root, NOT in the fsd repo):** `concurrency_demo.py`
(the pipeline with sleeps+files — backpressure/LEAK_BUG/disk-accounting demos) and
`concurrency_sweep.py` (network-free `MAX_STAGED` tuning sweep showing the throughput plateau past the
saturation floor). Built to teach the primitives before implementing; not part of the package.

**Test plan (pytest only, no network):** most existing download tests must still pass;
`test_circuit_breaker_trips_and_stops_early` is rewritten (C4); new tests for `_transfer_one`,
`_convert_one`, the cog=True pipeline (via injected synchronous `convert_executor`), backpressure
bound, lazy-pool (no procs on all-skip/cog=False), and `_default_max_staged`. Docs to update on
implement: `CHANGES.md`, `TODO.md`, `specs/14` pointer, `config.py` comments, `PROGRESS.md`, memory.

## LATEST (2026-07-11) — spec 24 working contract (process, not pipeline)

**How we work now (CLAUDE.md updated):** Claude **never runs pipeline/long/networked scripts** or
backgrounds/polls them (may run `ruff`/`pytest`/`grep`/`git status`); everything else is a
**run-book** in `fsd/runbooks/` (template landed) that the user runs, pasting back a step's
**`_result.json`** (Claude diffs vs success criteria, never reads live logs). **Model split:**
Opus@high plans/specs/debugs; user `/model sonnet` + `/effort medium` to implement a signed-off
spec. **Handoff:** flush durable state to PROGRESS/MEMORY → user runs `/handoff` → fresh session
(not `/compact`). Trigger for this spec: the spec-23 tiny-download run went wrong as a *process*
failure (I launched a long download, user couldn't stop it / see progress, my log-polling burned
tokens). **Next queued: spec 25 (download + jp2→COG redesign — inline GIL-bound conversion starves
transfers), then spec 26 (safe runner: `--dry-run`/`--stop-file`/progress).**

_Open from spec 23:_ `--tiny-download` was fixed to select a **single MGRS tile** (7 granules / 1
tile / ~2 GB, verified offline) but the real e2e run has **not** been completed (I must not run it);
that becomes a run-book. Specs 20–24 remain **UNCOMMITTED**.

## LATEST (2026-07-10) — P0.9 local-completeness gate (spec 23) — LAST local step before P1

**Next step: run `demos/e2e_austria.py` on real data** (needs CDSE creds + network; the user runs
it) and paste the timing/QGIS Results into `demos/E2E_AUSTRIA.md §8`. Then we start **P1** (Azure
storage seam — see `../P1_AZURE_SETUP.md` at the workspace root for the prerequisites the user fills).

Spec 23 (SIGNED OFF + IMPLEMENTED, **176 tests, ruff clean**) turned the demo into the **go-to local
run-book + confidence gate**: `demos/e2e_ethiopia.py` → `demos/e2e_austria.py`, now starting from a
real CDSE **download** (the first e2e to include it) on an Austria ROI (single UTM-33; `fid`/`crop`,
9 classes). Landed:
- **Download instrumentation** (`fsd.sources.cdse`): `DownloadResult.{bytes_downloaded,
  transfer_seconds,convert_seconds,bytes_by_band}` — decomposes CDSE-transfer vs local jp2→COG cost;
  `sum_results` (resume-pass aggregate); **`probe_throughput`** (baseline MB/s to factor out
  VPN/contention). `_download_one` now returns `(ok, reason, metrics)`.
- **`plan_download` guardrail** (D13): missing imagery → an actionable `fsd.download(...)` plan
  (JSON + printed command, +GB/ETA); wired into the `create_training_data`/`run_inference` preflight.
  Compute verbs still **never auto-fetch** (quota + Batch download-once model).
- **Cross-UTM-zone-safe merge** (D7): `run_inference(merge="reproject")` targets the **max-area** CRS
  (or `merge_crs=`), lossless where a cell already matches — the reusable template runs for any ROI,
  cross-zone included.
- **Reusable template + tooling**: `--roi/--train/--id-col/--label-col/--creds`; `demos/estimate.py`
  (no-download ETA for any region — answers "how long for full France?"); `demos/E2E_AUSTRIA.md`
  (setup + bundling guide + concepts/limitations appendices).

## LATEST (2026-07-06) — P0 (specs 16/17) + P0.5 (spec 18) + e2e demo/tiling (spec 19)

The v1 core pipeline (download → catalog → datacube → flatten → workflows) is **complete +
real-data-validated** (see history below). We have since set the **forward direction**:
- **Strategy docs (on `main`):** `ROADMAP.md` (north-star, 3 usage modes, control/data-plane,
  ModelAdapter contract F1–F5 + same-`T`/bands + preflight, phased **P0–P6**),
  `AZURE_INFRA.md` (the read-only `rise` project in `raapid-infra` we scale onto via Batch),
  `RSLEARN_COMPARISON.md` (build-vs-borrow vs AllenAI's rslearn — **open decision**, evaluated on
  branch **`spike/rslearn`** with an isolated venv; scale-out is ours regardless). Repo pushed to
  `git@github.com:nikhilsrajan/fsd.git` (MIT).
- **Spec 16 = P0 DONE (2026-07-06):** high-level API façade `src/fsd/api.py` re-exported at top
  level — `fsd.download`, `fsd.create_training_data` (hides flatten; preflighted; `runner`/
  `storage` seams local-only), `run_inference`/`deploy` **stubs** (P4/P6), `compute_n_timestamps`,
  `TrainingData`, `PreflightError`. Version `0.1.0`. README quickstart rewritten. **133 tests,
  ruff clean** (`tests/test_api.py`, 9 new). STAC split to **spec 17**; ModelAdapter to **P0.5**.
- **Spec 17 = STAC catalog DONE (2026-07-06):** `src/fsd/catalog/stac.py` + `TileCatalog.to_stac`
  — additive STAC export (GeoParquet schema unchanged); one Item per tile-product, one asset per
  band; `proj:code` from the MGRS tile (no raster reads); static self-contained STAC JSON via
  `pystac` (now a direct dep) through the storage seam; round-trippable. Real-data smoke: 579-tile
  benchmark → 579 items in 0.06 s, both UTM zones. **140 tests, ruff clean** (7 new). `stac-geoparquet`
  deferred; advances TODO #14 (STAC half; TiTiler serving = P5).
- **Spec 18 = P0.5 DONE (2026-07-06):** the **ModelAdapter contract** + local train/deploy. New
  `src/fsd/model/` (`adapter` [Protocol + `BaseModelAdapter` + `Output`], `features` [the F1
  anti-skew chokepoint + `median_per_id`], `engine` [fsd owns the predict loop → COG], `bundle`
  [self-describing `module:attr` bundle, save/load, model-free preflight]). `api.py` wired:
  `create_training_data(adapter=/feature_sequence=/aggregate=)` writes `features.npy` additively;
  **`run_inference` is real** (local engine over pre-built inference datacubes → COG per cube +
  STAC via new `catalog.stac.cog_outputs_to_items` + optional merged map); `deploy` still a P6
  stub (bundle format now pinned). Example `examples/eurocrops_rf.py`; runbook
  `tests/manual/deploy.md`; explainer `specs/18-model-bundle-explainer.md`. **150 tests, ruff
  clean** (`tests/test_model.py`, 9 new). One bug fixed: engine copies `band_indices` (modify_bands
  mutates it). ROI→S2-tiling front-end for `run_inference` stays **P4**.
- **Spec 22 = retire `engine.run_local`'s `mp.Pool` + idempotent inference DONE (2026-07-07):**
  after P0.75, the pre-built-cubes inference pool was the last parallel fan-out **not** on the runner
  seam. Now: `cores=1` stays **in-process sequential** (tests/debug/small, no bundle); `cores>1`
  fans out via the **Snakemake infer-only runner** (`workflows/infer_only_task.py` +
  `_snakefiles/infer_only/Snakefile` + `runners.run_local_infer_only`), routed from
  `api.run_inference` (kept out of `engine` to avoid a model→workflows cycle). **No `mp.Pool`
  anywhere** → Batch (P4) can dispatch pre-built inference too (pure `runner=` swap). **Inference is
  idempotent:** both paths skip existing outputs unless `overwrite=True` (fixes the demo re-run the
  user hit — engine re-inferred despite existing `output.tif`). New `cubes_per_task` knob (default 1)
  groups K cubes per job to amortise the bundle load — the intra-task loop is **sequential, no pool**.
  Default `cores=1` → backward-compatible. **167 tests, ruff clean** (+4). **Real cores>1 smoke**
  (.venv, 5 synthetic cubes, cubes_per_task=2 → 3 Snakemake groups): 5 COGs + STAC, rerun = "Nothing
  to be done" (idempotency confirmed). Docs: `CHANGES.md`, `specs/18` pointer, `deploy.md`.
- **Spec 21 = P0.75 ROI inference verb DONE (2026-07-07):** `run_inference(roi=…)` completes
  **Mode A** — one call tiles an ROI (`fsd.grid`), builds one datacube per S2 grid cell, infers,
  and writes per-cell COGs + STAC (+ optional merged map). The per-cell **build+infer** is a single
  **runner-dispatched** unit-of-work (`workflows/infer_task.py` + `_snakefiles/create_inference/`
  Snakefile + `runners.run_local_inference`), *not* the spec-18 `mp.Pool` — so **P4 = a pure
  `runner=` swap to Batch** (the reason we folded inference into the runner seam). `run_inference`
  now takes `roi=` **xor** `inference_datacubes=` (both optional; positional calls still work);
  `merge` is tri-state `False|True|"reproject"` (strict single-CRS vs lossy dominant-zone display
  merge — the demo's logic moved into `api._merge_outputs`; demo now calls `merge="reproject"`).
  **SO-6:** ROI inference never calls CDSE (imagery assumed present; conserve quota → on cloud,
  Batch reads blob). **163 tests, ruff clean** (+11). **Real smoke** (`.venv-modeldeploy`, benchmark):
  ~9 km ROI → 10 cells → 10 COGs + STAC + reproject-merge (899×889, 96.9 % valid), 42 s @ cores=2;
  resumability confirmed. Bug fixed: snakemake parses empty `--config key=` as `None` → omit
  `predict_batch_size` when None. Runbook `tests/manual/roi_inference.md`; supersedes deploy.md §3's
  3×3-grid stand-in. **This clears the last pre-Azure phase — next is P1 (Azure storage seam).**
- **Spec 20 = datacube-builder tile-merge bugfix (2026-07-07):** the spec-19 demo exposed a
  **correctness bug** — `_stack_datacube` kept only **one** tile per `(timestamp, band)` (a dict),
  so shapes straddling an MGRS tile boundary lost the coverage of every other same-acquisition
  tile (worst demo grid `165b09c`: 0.6 % valid despite ~80 % raw coverage; clustered on the
  lat-11.75 tile-row boundary). A faithfully-ported legacy bug, hidden until inference grids
  (spec 19) were the first shapes big enough to straddle tiles. **Fix:** nodata-fill **merge all**
  same-`(timestamp,band)` images onto the reference grid (tie-break: `dst_crs`-native first),
  confined to `_stack_datacube`. **Verified:** `165b09c` 0.6 % → 82.8 % valid; 2 new unit tests.
  Post-fix demo re-run: merged map 90 % → **96 %** valid, **0** dead grids (was 9). Docs:
  `BUGS.md` BUG-002, `CHANGES.md`, `specs/03`, `specs/20`.
- **Spec 19 = end-to-end demo + ROI→S2 tiling (2026-07-06):** landed **`src/fsd/grid.py`**
  (`roi_to_s2_grids`, clean-room port of `rsutils.s2_grid_utils`; `s2`+`s2cell` in the optional
  `[grid]` extra — ROADMAP §4 / P4 groundwork, `run_inference(roi=…)` front-end still P4) +
  `tests/test_grid.py` (4 tests, skip without `[grid]`). New **`demos/`** runs demo_01+02+03 as
  one flow (tiling → `create_training_data` → RF → inference datacubes → `run_inference` →
  COG/STAC + crop map + NDVI-timeseries/crop-map/grids figures) on the existing Ethiopia data, in
  an **isolated `.venv-modeldeploy`** (`[dev,grid,model-example]`; keeps fsd's `.venv` lean).
  **`--fast` validated** (67 s); full run = 300 grids / 1015 fields / T=19. **Finding:** the ROI
  straddles the S2 zone-36/37 boundary → per-grid datacubes are mixed 32636/32637, so
  `run_inference(merge=True)` refuses (single-CRS principle) and the demo reproject-merges outputs
  to the dominant zone for the display map. Model quality is meaningless (Austria labels on
  Ethiopia pixels) — pipeline validation; real run after the Austria download.
- **AZURE_INFRA.md scrubbed + git history rewritten (2026-07-06):** private-infra names/IDs/CIDR/
  budget removed from the public repo (placeholders); concrete values live only in the local,
  never-committed `AZURE_INFRA_PRIVATE.md` at the workspace root.
- **Next:** **P1** (Azure storage seam: adlfs/MSI + GDAL-VSI) — the last pre-Azure local phase
  (P0.75, spec 21) is now done, so the whole local Mode-A product is complete. P1 needs Azure
  access from this laptop (VPN + `az login`); the setup checklist is `../P1_AZURE_SETUP.md`
  (workspace root, uncommitted). Alternatively the `spike/rslearn` benchmark (the big
  build-vs-borrow unknown). NB the Azure-Batch spec is a *future* number (not spec 10 — that's
  "storage-and-scale", already used).

## Where we are

Spec phase **complete and signed off**; package **scaffolded**; `storage` and
`catalog` **implemented and tested** (16 automated tests pass, ruff clean).

## Build order & status (from `specs/00-overview.md §7`)

| # | Module | Status |
|---|--------|--------|
| 0 | `config.py` | ✅ done (constants) |
| 1 | `storage/fs.py` | ✅ implemented · ✅ verified (`tests/test_storage.py` + manual `storage.md` Section A all pass; Section B = S3, needs creds, still manual) |
| 4 | `sources/cdse.py` | ✅ `CdseCredentials` + `query_catalog` + `download` implemented (18 tests, ruff clean). **Discovery pivoted to the CDSE STAC API (`pystac-client`, anonymous) — drops `sentinelhub` and the flaky S3 `.SAFE` listing (BUG-001)**; band S3 hrefs come from STAC `assets`. Metadata path live-verified (Ethiopia ROI, 138 tiles Jan–Mar 2018, highest-res selection + MTD_TL.xml). **At-scale download DONE + hardened (2026-07-02):** 1-year Ethiopia multi-CRS download completed — 579/579 tiles, 94 GiB in `satellite_benchmark/`, verified integrity. Resilience: atomic `.part`+rename transfer, S3 timeouts, circuit-breaker + `download_resume`, newline progress. Concurrency/quota sweep = TODO #9. |
| 2 | `catalog/catalog.py` | ✅ implemented · ✅ verified (`tests/test_catalog.py`, 6 tests) |
| 3 | `raster/images.py` | ✅ implemented · ✅ verified (`tests/test_raster.py`, 24 tests; + RGB/GeoTIFF save helpers) |
| 3 | `bands/modify.py` | ✅ implemented · ✅ verified (`tests/test_bands.py`, 12 tests) |
| — | **real-data validation** (raster+bands) | ✅ `tests/manual/realdata.md` — TCC/FCC/NDVI on tile T33UWP confirmed in QGIS by user |
| 5 | `datacube/ops.py → builder.py → flatten.py` | ✅ implemented · ✅ unit-tested (14 tests) · ✅ real multi-CRS build verified + runbook `tests/manual/datacube.md` (user QGIS-confirmed geolocation/merge/resample/mask; edge-tightness nit → TODO #8) · ✅ **heavy 1-yr benchmark + NDVI report** (`benchmarks/datacube_report_2018_ethiopia.md`). |
| 6 | `workflows/task.py · runners.py · create_datacube.py` + Snakefile | ✅ implemented · ✅ tested (`tests/test_workflows.py`, 5 tests incl. real Snakemake dry-run) · ✅ **real full e2e verified** on `satellite_benchmark` (ROI 165bca4): setup→Snakemake→`task` CLI→build→`datacube.npy (2,554,533,3)` + `done.txt`; **resumability confirmed** (re-run = "Nothing to be done"). |
| — | `notebooks/01_data_prep.ipynb` | ⬜ later |

## Next step (when resuming)

`sources/cdse.py` (module #4) is **complete + hardened + proven at scale**: the
1-year Ethiopia multi-CRS download finished cleanly — **579/579 tiles, 94 GiB, in
`satellite_benchmark/`**, integrity verified (0 zero-byte/truncated/`.part`). Along
the way the download got production-grade resilience: atomic `.part`+rename transfer,
S3 connect/read timeouts, circuit-breaker + `download_resume` loop, and log-friendly
newline progress. See `benchmarks/download_report_2018_ethiopia.md`.

**Dataset change:** the old `satellite/` (T33UWP) was **deleted**; the real-data test
set is now **`satellite_benchmark/`** (Ethiopia `s2grid=165bca4`, EPSG:32636+32637,
bands B04/B08/B8A/SCL). `realdata.md` TCC/FCC examples are stale (no B02/B03); only
NDVI applies there. **As of 2026-07-04 this archive is COG** (`Bxx.tif` + overviews;
migrated in place from JP2, catalog updated — see spec-14 bullet below).

**Datacube module #5 DONE (2026-07-02):** `ops.py` (run_ops, apply_cloud_mask_scl,
drop_bands, median_mosaic [numba], area_median), `builder.py` (build_datacube seam +
flatten_catalog helper: missing-check → load/crop → dst_crs by max-mean area →
merged-B08 reference → resample-to-ref → stack → SCL mask → drop → median mosaic →
save via storage), `flatten.py` (per-pixel training arrays + coords). 14 unit tests
(89→92 total). One legacy bug fixed: missing-band nodata fill shape (CHANGES.md).
Two design rationales captured from the user (memory): `_dt2ts` UTC localization,
`metadata.pickle.npy` cross-platform pickling.

**Module #5 fully validated (2026-07-03):** unit tests + user QGIS pass + a **heavy
full-year (2018) benchmark** on the real multi-CRS ROI. Findings: build is **I/O-bound**
(load_images 70–75% of time; cold 238 s vs warm 72 s per ROI; peak ~4 GB), output
`(19,554,533,3)` correct — the masked-mosaic NDVI traces real phenology (peak ~0.53 in
Sep) and cloud masking lifts growing-season NDVI up to +0.36. Report + 3 figures +
reproduce scripts in `benchmarks/` (matplotlib was `pip install`ed into `.venv`; it's
already declared in the `notebooks` extra).

**⚠️ UNCOMMITTED (paused mid-session, all on disk):** `benchmarks/datacube_report_2018_ethiopia.md`,
`benchmarks/datacube_2018_figures/` (3 PNGs), `benchmarks/datacube_year_ethiopia.py`,
`_plots.py`, `_stats.json`, and the PROGRESS edits above. Keep the 2 notebooks OUT.
Commit these when resuming (user hadn't given the commit word before the pause).

**Module #6 workflows DONE (2026-07-03):** task/runner/entrypoint split + bundled
Snakefile (`fsd.workflows`), 5 tests incl. a real Snakemake dry-run. This **completes the
v1 core pipeline: download → catalog → datacube → flatten → workflows.** Adaptations in
CHANGES.md (parquet subset via `TileCatalog.filter`, `if_missing_files="warn"` default,
`sys.executable -m` invocation, `fs.rm`).

**⚠️ PAUSED 2026-07-03 with UNCOMMITTED module #6 (all on disk):**
`src/fsd/workflows/{task,runners,create_datacube}.py`, `src/fsd/workflows/_snakefiles/create_datacube/Snakefile`,
`src/fsd/storage/fs.py` (added `rm`), `tests/test_workflows.py`, `CHANGES.md`, `PROGRESS.md`.
Keep the 2 notebooks OUT. Commit on resume.

**v1 core pipeline is COMPLETE and end-to-end verified** (download → catalog → datacube →
flatten → workflows), on real multi-CRS data, incl. Snakemake resumability.

**Datacube-speed track (TODO #15) started — 3-part, benchmark-first:**
- **Part 1 — spec 11 DONE + committed (2026-07-03):** reusable parallelism-sweep harness
  (`benchmarks/datacube_throughput_sweep.py`) + baseline report. Finding: throughput knees at
  **cores=4** (2.39×); per-grid `load_images` slows **2.41s→9.07s (3.76×)** with parallelism
  → **I/O read contention is the bottleneck** (~60% of build). `build_datacube(write_timings=)`
  flag added (env-gated via `FSD_WRITE_TIMINGS`). Runbook: `tests/manual/throughput_benchmark.md`.
- **Part 2 — spec 12 DONE + implemented (2026-07-04):** per-read instrumentation. Builder
  `write_read_log` → `reads.jsonl` per grid (id, mgrs_tile, product_id, band, filepath, wall-clock
  start/end, duration; env-gated `FSD_WRITE_READ_LOG`, requires `njobs_load_images==1`). Harness
  `--read-log`: **read conflicts** (overlapping read pairs, different grids) + **read-duration-vs-
  concurrency** curve (instantaneous peak-in-flight; the hypothesis test) + **same-file / same-tile
  / different-tile** split. Pure analysis unit-tested (107 tests). **Full 100-grid `--read-log`
  run DONE (2026-07-04)** — report `benchmarks/datacube_throughput_report.md`.
  **FINDING:** hypothesis **confirmed** — read duration 0.056s→0.274s (**4.87×**) as concurrency
  1→10; all `cores` lines collapse onto ONE duration-vs-concurrency curve; total `load_images`
  work 279s→912s (**3.27×**) for the *same* 6284 reads → **shared disk-bandwidth ceiling**, wall
  plateaus past the cores=4 knee. **Conflicts are only 0.6% same-file** (372 / 15457 same-tile /
  43082 diff-tile) — so **Part-3 tile-splitting-to-kill-same-file-conflicts targets a negligible
  slice.** Self-check passes (sum_read_seconds ≈ load_images phase). Nuance in the report verdict:
  it measures *simultaneous* conflicts not *redundant* reads; the inference workload isn't covered.
- **COG vs JP2 experiment — spec 13 DONE + implemented (2026-07-04):** first speed lever pursued
  (Part 2 pointed at JP2 wavelet *decode* cost). `benchmarks/prep_cog_dataset.py` (JP2→base COG,
  DEFLATE+PREDICTOR=2, lossless via NBITS=16, disk pre-flight, storage report) + harness
  `--catalog/--start/--end/--tag` + `benchmarks/compare_cog_jp2.py` (team report + duration-vs-
  concurrency overlay). No `src/fsd/` change. Runbook `tests/manual/cog_experiment.md`. 113 tests,
  ruff clean. **Full 4-month A/B DONE (2026-07-04)** — `benchmarks/cog_vs_jp2_report.md`.
  **RESULT:** COG **1.58×→3.46× faster wall** (cores 1→10), **up to 9.42× faster load_images**;
  COG mean read is **FLAT vs concurrency (1.01×)** while JP2 rises 3.45× → the slowdown was JP2
  wavelet **DECODE** contention, **not** disk bandwidth (**corrects the Part-2 framing**). Cost:
  base COG **1.225× JP2 storage (+23%)**, lossless. Clear win. (COG also scales past the JP2
  cores≈4-6 knee, since the decode bottleneck is gone.)
- **Tile-centric batching + other levers — PARKED (2026-07-04):** target the bandwidth/decode
  costs, not same-file conflicts. Revisit only if build speed becomes a priority again. See TODO #15.
- **COG-on-download — spec 14 DONE + implemented (2026-07-04):** FIRST production `src/fsd/` change
  out of the COG track. `sources.cdse.download(cog=True, default)` converts each fetched JP2 band →
  lossless COG (`Bxx.tif`, catalog records `.tif`) **with overviews** (TiTiler-ready); `cog=False`
  keeps native JP2. New `src/fsd/raster/cog.py::to_cog` (lossless, atomic `.part`+replace, NBITS=16
  for uint16, optional verify) — the single COG-profile home (config constants); `prep_cog_dataset`
  refactored to share it. Fetch→local staging sibling→`to_cog`→remove-staging; idempotency keys on
  the final `.tif`. **Local-dst only in v1** (remote raises; stage→convert→upload deferred to
  Azure). Read/build path untouched (rasterio reads `.tif`). 119 tests, ruff clean. **Real smoke:**
  10980² B04 JP2 → COG bit-identical, overviews [2,4,8,16], 15.5 s, ~1.86× size (w/ overviews).
  Follow-ups in TODO #15: remote-dst COG, conversion process pool, bulk-migrate the existing
  `satellite_benchmark` archive.
- **satellite_benchmark migrated JP2→COG in place — DONE (2026-07-04):**
  `benchmarks/migrate_jp2_to_cog.py` converted all **2316 band files** to COG+overviews (lossless,
  0 failed), **deleted the JP2s** (no duplicate copies), and rewrote `catalog.parquet` to `.tif`
  (fully consistent, 0 missing). 72 min at 8 workers; archive **94→159 GiB**, ~10 GiB free. Tool is
  resumable, disk-floor-guarded, progress-bar + ETA, `--verify {full,quick,none}` (default quick).
  Conversion is **memory-bandwidth-bound** → 8 workers (perf cores) is the knee (10 gave no gain).
  The Part-1/2 throughput/read findings were on the *pre-migration JP2*; re-running now reads COG.

**Calendar-interval mosaic = spec 15 DONE + implemented (2026-07-05):** resolves TODO #2 and
unblocks `flatten` across a multi-tile/multi-zone training set. `median_mosaic` gained
`mosaic_scheme` (default `config.MOSAIC_SCHEME="calendar"`): fixed calendar windows off the
caller's `startdate`, labels = window-start boundaries, **empty windows emitted as all-nodata**
→ every cube over the same start/end/mosaic_days shares an **identical `timestamps` axis** whatever
tiles/orbits/zones it hit. Legacy via `mosaic_scheme="acquisition"`. Threaded through `build_datacube`,
`workflows.task` (`--mosaic-scheme`), `create_datacube.setup` (now anchors at caller dates, not
per-shape actual) + Snakefile. Sub-cadence behavior documented in `median_mosaic` docstring (window <
revisit → raw series padded with nodata slices). 124 tests, ruff clean. Real smoke: west (EPSG:32636)
+ east (EPSG:32637) fields → identical `[06-01, 06-21]` axis. New TODO #16 = multi-zone `coords.npy`.

**`flatten` real-data run DONE + validated (2026-07-05):** the last v1-pipeline stage to get a real
run. Built 1 datacube per EuroCrops field via the workflow (33-field class-stratified subset of
`shapefiles/austria_eurocrops_sampled_ethiopia_translated.geojson`, id=`fid`, label=`EC_hcat_n`, 11
classes, both zones), then `flatten` over the workflow `input.csv` → `data.npy (6502,2,3)` +
coords/ids/labels/metadata. **Consistency gate passed across both UTM zones** (spec-15 payoff),
total/per-field pixel counts match, round-trip exact. Runbook `tests/manual/flatten.md`. Full 1015-field
run = same commands (serial cube build ≈ 9 min). **v1 pipeline now fully real-data-validated end to end.**

**Other NEXT options:** Azure/Batch (spec 10, roadmap step 2); source extension (#11) / rslearn
benchmark (#12). Deferred: TODO #9; TODO #16 (multi-zone coords); `reference_profile` grid-from-bounds.

CDSE discovery pivot (2026-07-01): dropped `sentinelhub` + the S3 `.SAFE` listing for
the **CDSE STAC API** (`pystac-client`, anonymous). STAC item `assets` give per-band
S3 hrefs directly → no recursive S3 listing (the BUG-001 failure). Only the byte
`transfer` touches S3 auth, wrapped in fail-fast retry. On-disk layout unchanged
(strip `.SAFE`, short `B02.jp2` names) = the `satellite/` folder layout.
Residual resilience items (circuit breaker, per-tile restructure) tracked in BUGS.md.

**Test geometries** (`shapefiles/`, EPSG:4326): `s2grid=476da24.geojson` = Austria tile
T33UWP, single-tile (used for raster/bands realdata.md, done). `s2grid=165bca4.geojson`
= Ethiopia ROI (lon ~36.2/lat ~11.6) straddling the **36°E UTM zone boundary** → pulls
S2 tiles in **both EPSG:32636 & 32637** = THE multi-tile/multi-CRS test for CDSE download
+ datacube creation (its tiles aren't in `satellite/` yet, so download must run first).

## Decisions log (all locked unless noted)

- Scope: download → datacube → flatten. Train/deploy stay in notebooks.
- Sentinel-2 **L2A only**. **GeoParquet** catalog. Keep **Snakemake** as the *local*
  runner only. Keep `coords.npy`. CDSE query cache **removed**.
- Storage = **fsspec** seam (local now; blob/S3 additive). S3 transport **first-class
  & generic** (s3fs, any endpoint); no direct boto3.
- Real end goal: Azure Batch scale-out, **cloud-agnostic** — achieved via the storage
  seam + a runner-agnostic CLI datacube task. **No Azure code in v1.**
- OQ-3 **resolved**: source contract is a documented function signature (no ABC) until
  a 2nd source exists.
- Hard constraint: never edit `fetch_satdata/`, `rsutils/`, `cdseutils/` (read-only
  reference). Keep `DROPPED.md` / `CHANGES.md` current.

## Key files
- Design: `specs/00..10`. Living docs: `DROPPED.md`, `CHANGES.md`.
- Implemented: `src/fsd/config.py`, `src/fsd/storage/fs.py`.
- Manual tests: `tests/manual/` (one guide per module).
- Cross-session memory: see `MEMORY.md` entries `fsd-*`.

## Environment note
Deps are **not** in system Python. Dev setup:
`python3.11 -m venv .venv && source .venv/bin/activate && pip install -e ".[dev]"`.

<!-- archived 2026-08-21: PROGRESS.md had grown to 981 lines; spec 41 D12 says it carries the
current state plus the most recent entry, not the log. Entries below moved verbatim. -->

## 2026-08-20 — spec 47 **Opus-reviewed**: 5 defects fixed, #64/#65/#66 closed, D9 deferral filed as #75

Independent Opus review at `/effort high` of `ff8d088..a195b42` (the Sonnet implementation entry
below), per the standing practice that the authoring session cannot be its own reviewer.

**Verdict: all 12 acceptance criteria in spec 47 §4 are met** — the band→filename mapping Part C
depends on is correct (`mpc._select_item_files` writes `<band>.tif`, so `splitext(basename)[0] ==
band`), the no-op return carries the same keys a dispatched run returns, `[setup]`'s line really is
byte-identical, and Part D's caller-misuse raises all sit above the `try`. Five defects were found
*on top of* the ACs, all fixed in `8dc2c1b`, merged as `330302d` (`--no-ff`, worktree pruned).

| # | defect | fix |
|---|---|---|
| 1 | **`test_ticker_prints_expected_shape` was flaky** — it asserts `out.endswith("s")`, but when `elapsed` rounds to 0.0 the rate is 0 and the eta segment is legitimately `eta ?`. Failed in a full-suite run, passed in isolation and under `-p no:randomly`; mechanism confirmed by freezing `time.time`. | pinned as a regex, matching the byte-identical `[setup]` test's own approach |
| 2 | **the merge ticker measured the wrong thing** — `rasterio.open` reads a COG's *header*; the pixels are read inside `rio_merge`, and in reproject mode inside a per-input warp before it. On the case the spec cites (300 per-cell COGs over the WAN, ~1000 s) the bar hit 100% at the end of the header scan and the expensive phase then ran in silence. Worse than no bar: it asserts completion. | the per-input warp gets its own ticker; `rio_merge`, which has no per-input hook, is announced |
| 3 | **`[collect]` reported hits as progress** — `done` was the hit count against a total of all candidates, so a *finished* collect printed `0/300 candidates (0%)` on a fresh run | `done` is candidates probed (one glob finishes them all); the hit count rides as the suffix; no eta, nothing to extrapolate from |
| 4 | **D1's refusal mutated the folder it refused** — the identity check ran after `grids.geojson` was overwritten and a bundle staged, so a refused resume left the old run folder describing the NEW roi while its `input.csv` still described the old one | moved above every write; regression test asserts the folder is byte-for-byte untouched |
| 5 | **`_aml_submit_and_wait` printed its 100% line twice** whenever every job was already terminal on the first poll (an unthrottled tick followed by a forced one) | force the in-loop tick on the last poll instead of adding a second call |

Plus `_RESUME_DRIFT_SAMPLE` was a *threshold* named "sample" while the sample width was a separate
hardcoded `10` — split into `_RESUME_DRIFT_MAX_MISSING` and `_RESUME_DIFF_SAMPLE`.

**Two documentation gaps closed:**

- **`CHANGES.md` had no spec 47 section**, unlike every recent spec. Added — including a behaviour
  change the implementation did not call out: **`max_tiles` is now enforced against the shortfall's
  distinct tiles, not every discovered tile**, so a mostly-already-present request can pass a guard
  it would previously have tripped. (That is the *more* correct reading of `max_tiles` — the
  shortfall is what actually gets downloaded — but it is a user-visible change and belonged on the
  record.)
- **D9's opt-in existence pass** was signed off (§7 Q3) but not implemented, and the deferral was
  recorded nowhere. **Adjudicated as a legitimate scope call, not an unimplemented decision** — no
  §4 acceptance criterion covers it — but it needed a home: filed as **#75**, restating its
  deliberate limits (existence only, never size; spec 47 §7 Q6 resolved that at its source in #74).
  Spec 47's status line now names the carve-out.

**Issues #64, #65 and #66 are CLOSED** against `2e5b3b3` + `330302d`, each with a comment covering
what landed, the behaviour changes, and the tests — matching the #67–#72 precedent.

**Gates on `main` after the merge: 787 passed, 88 skipped, `ruff check src/ tests/ demos/
examples/` clean.** The single failure is the pre-existing local `.venv` gap
(`test_missing_driver_deps_is_empty_when_everything_is_installed` — `planetary_computer` absent;
`pip install -e ".[aml,azure,dev,mpc,grid]"` fixes it), which reproduces on unmodified `main`.
787 = the 785 baseline + the review's 2 new regression tests.

**⚠️ `main` is 10 commits ahead of `origin/main` and UNPUSHED.** Push is the user's call
(`CLAUDE.md`: push only when asked). Until then #64/#65/#66's closing comments point at commits
GitHub cannot yet resolve — each comment says so.

**Open follow-ons:** #75 (D9's existence pass), #74 (atomic download writes — the prerequisite that
makes existence the *right* predicate), #73 (spec 45 D2's installed-adapter carve-out, unspecced),
CDSE's own no-op diff (spec 47 D8 scopes it out), spec 44 phase 2 (`deploy`, unsigned).

---

## 2026-08-20 — spec 47 **implemented and merged**: driver-side honesty (stale work lists, silent
dispatch, no-op downloads, misread verdicts) — *reviewed; see the entry above*

Spec 47 (signed off 2026-08-20, same day) implemented in one Sonnet session, `/effort medium`, per
`CLAUDE.md`'s model split, landing order per the spec's own §9 (Part D first, smallest/lowest-risk;
then A, B, C in the spec's stated order). **Not yet reviewed** — that is the explicit next step,
this entry exists to hand it off.

Four independent parts, four issues, one shape: *a driver-side fact the code already has in memory
gets dropped on the floor instead of acted on or reported.* Each part landed as its own commit on
`worktree-spec47-part-d`, full `pytest -q` green after each (only the pre-existing
`test_missing_driver_deps_is_empty_when_everything_is_installed` `.venv` `mpc`-extra gap, same as
every prior session), `ruff check src/ tests/ demos/ examples/` clean throughout:

| part | issue | commit | fix |
|---|---|---|---|
| **D** | amends spec 45 D4 | `51970d2` | `verify_image(build_context=<folder with no wheel>)` now **raises** `ValueError` before the `try` instead of returning `pass: False` — a caller-argument problem was being laundered into a verdict shaped exactly like a real image failure. Stale-wheel case (a real finding about the image) is unchanged. |
| **A** | #66 | `d8e2b29` | `run_inference(roi=...)` resumed a cached `input.csv` by **existence alone** — a second run into the same `output_folderpath` with a **different** ROI silently re-inferred the FIRST roi's cells. New `api._check_resume_identity` compares the cached `id` set against the freshly tiled grids as a set; any mismatch raises `PreflightError` naming the folder, both counts, a sample of the diff, and the fix (a new `output_folderpath` — now documented as the identity of a run). A cached set that's a strict superset by ≤10 ids is called out as the likely spec-46 D4 cell-count drift, not a different ROI. |
| **B** | #65 | `1018fd5` | `workflows/runners.py` had exactly one `print()` in 1169 lines; four driver-side AML legs (bundle stage, poll loop, collect, merge) were completely silent — measured 627 s / ~1000 s / 30 m 10 s of silence indistinguishable from a hang. New `fsd.progress.ticker()`, extracted verbatim from `create_datacube.setup`'s `_tick` closure (byte-identical output, regression-tested), now backs all four legs plus `setup` itself. `_aml_submit_and_wait` also now prints `run_id`/`run_root` before any job submits. |
| **C** | #64 | `aa5bc38` | `run_aml_download`'s MPC branch discovers the full asset list on the driver but dispatched every discovered asset regardless of what the catalog already had — a no-op download still paid a full cold-start fan-out (measured 5m31s). New `runners._mpc_catalog_shortfall` diffs `(tile_id, band)` against the catalog's `id`/`files` columns (a cheap read, never a per-asset destination stat — D9's stated invariant); empty shortfall returns without calling `create_or_update` at all, partial shortfall dispatches only the missing assets. CDSE untouched (D8 explicitly scopes it out — discovery happens on the node there). |

**Merged to `main` 2026-08-20 as `2e5b3b3` (`--no-ff`, clean fast-forward, no conflicts — the
worktree branched cleanly off `main`@`ff8d088`), worktree pruned** (standing practice). Post-merge
full suite on `main`: **785 passed, 88 skipped**, same one pre-existing failure, `ruff` clean.

**Explicitly NOT done, by design (spec §2 scope):** the CDSE download path's own no-op-diff (D8
says a driver-side CDSE discovery pass is a larger, separate change); the atomic-write fix for the
download path itself (filed as **#74**, the reason spec 47 §7 Q6 chose "existence-only" over
"size-comparing" for D9's still-unimplemented optional verification pass — that opt-in,
threaded, off-by-default existence check was **not implemented this session**, deliberately scoped
out as uncovered by any acceptance criterion; see the spec's D9/§3a for what it would need to catch
a truncated MPC transfer that the current row-only diff cannot); changing the `input.csv` resume
mechanism itself; `fs.rm` reliability on blob (#50).

**Issues #64/#65/#66 were closed by the review session** against `2e5b3b3` + `330302d` — see the entry above.

---

## 2026-08-19 (latest) — specs 45 and 46 **implemented**: bundle transparency/validation + image
verification, run-folder addressability + grid dedup

Both signed-off specs (see the entry below) implemented in one Sonnet session, `/effort medium`,
per `CLAUDE.md`'s model split, then **reviewed by Opus and merged the same day**. All acceptance
criteria met; `pytest -q` (**758 passed, 1 failed, 85 skipped** — the one failure,
`test_missing_driver_deps_is_empty_when_everything_is_installed`, is the pre-existing `.venv`
`mpc`-extra gap and reproduces on unmodified `main`, not a code defect) and `ruff check src/
tests/ demos/ examples/` are both green.

**Spec 45 — `src/fsd/model/bundle.py`, new `src/fsd/model/verify_image.py`.** `save` now prints a
report by default (root, files+sizes, adapter ref, requirements; `verbose=False` silences it,
#70), refuses before copying anything if the adapter's own module wouldn't sit at the top of
`code/` (#72) or if an embedded file imports an unembedded sibling — transitively, dependencies
left alone (#71). `fsd.model.verify_image(bundle, environment=..., runner="aml", runner_kwargs=...,
build_context=None) -> dict` promotes the run-book smoke into the library (#67); `runner="local"`
raises rather than returning a false-positive pass. `runbooks/scripts/
45_phase1_generic_image_smoke.py` is now a thin wrapper over it, same `_result.json` shape. Tests:
`tests/test_bundle_transparency.py` (new, 15 tests) + `tests/test_bundle_code.py` (24, unchanged,
still green).

**Spec 46 — `src/fsd/workflows/create_datacube.py`, `src/fsd/grid.py`, `src/fsd/api.py` docstring.**
The export path is now `run_folderpath/{startdate}_{enddate}_m{mosaic_days}/<id>` — one window
folder per run, derived from the request, not each shape's actual acquisition range (#68);
`actual_start`/`actual_end` moved into the cube's own `metadata.pickle.npy`. `roi_to_s2_grids` now
drops any cell `covered_by` another returned cell, printing the before/after count (#69) — a
numerically-robust `covered_by` check (raw shapely's exact predicate missed 6 of 8 redundant cells
to floating-point noise on the real `s2grid=476da24` ROI; a relative-area-tolerant version catches
all 8), tie-broken deterministically by smaller `id`, coverage-preserving by construction.
**Re-measured against the real shapefiles** (`shapefiles/s2grid=476da24.geojson`,
`shapefiles/AT_ROI.geojson`): `9 -> 1` and `300 -> 299` exactly as the spec's before-numbers
predicted, `299` in ~0.075 s. `CHANGES.md`, `RECIPES.md`, `LIMITATIONS.md`'s stale AT_ROI/Phase-1
cell counts updated. Tests: `tests/test_grid.py` (+5), `tests/test_workflows.py` (+1),
`tests/test_datacube_builder.py` (assertions added to the existing end-to-end test).

**Review (Opus, `/effort high`, same day) — one real defect found and fixed, plus four
non-behavioral cleanups.** The defect: the new AC7 test ran
`runbooks/scripts/45_phase1_generic_image_smoke.py` as a subprocess with its **default** output
path, so every `pytest -q` in a working checkout **overwrote
`tests/outputs/spec44_verify/_result_phase1.json`** — which holds the result of the REAL Phase-1
cluster run the user pastes back per spec 24. The script gained an `--out <dir>` override (same
argv convention as `34_mixed_baseline_slice.py`'s `--dst`) and the test now writes to `tmp_path`.
Cleanups: `verify_image` no longer leaks an open `ZipFile` handle, its dead `if req_problems:
pass` branch became a plain comment, and its docstring now admits it also raises on missing
`runner_kwargs`; `bundle.py`'s double-`sorted()` in the D3 fix message collapsed to one.
**Reviewed and accepted as-is:** `_covered`'s tolerance choice (relative to the *candidate's own*
area, so scale-safe; the deviation from D4's literal "the predicate is `covered_by`" is now
recorded in spec 46 D4 itself), and `_check_adapter_at_top`'s culprit-naming heuristic (with 3+
files across trees it may name a different offender, but the prescribed fix — one containing
directory — is the same either way).

**Flagged for the user, NOT changed** (a spec-scope question, not a bug): spec 45 D2 now refuses
`bundle.save(installed_adapter, code=["./utils.py"])` — an adapter that really is a pip dependency
of the image, plus extra helper files. The adapter imports from site-packages regardless of what
`code/` holds, so the at-top check is irrelevant there, but D2 as written has no carve-out. Narrow
and previously legal under spec 44 D1 ("take the user at their word"). **Filed as #73** with the
candidate fix; needs a spec-45 amendment first, since D2 has no carve-out today.

**Not yet done:** `main` is **3 commits ahead of `origin/main`** (which sits at `7c898e9`, i.e.
spec 44's work is already pushed — the earlier "pending push from spec 44" note was stale): the
implementing commit, the merge, and this pointer commit. Pushing is outward, so it stays the
user's call per CLAUDE.md's "push only when asked": `git -C fsd push origin main`.

## 2026-08-19 (later) — spec 44 phase 1 **proven on the cluster**; three run-book defects fixed on the way

`runbooks/45-verify-bundle-carried-code.md` Phases 0–1 are **green**. The D11 adapter-import smoke
returned `{"status": "ok"}` on **`fsd-infer-sklearn:3` — an image built with no adapter source in
it** — with `my_adapter:CropRF` resolved purely from the bundle's `code/`. Acceptance criterion 12
is met. The notebook's cell-18 procedure (4 hand-written files + `pip wheel` + `az ml environment
create` + a smoke job, repeated on every adapter edit) is **obsolete**.

Getting there exposed three defects **in the run-book, not in fsd** — worth recording because each
would have recurred:

1. **The smoke was documented as a local command.** It would have passed trivially on the driver
   (which has the adapter on `sys.path` and its deps installed) while proving nothing about the
   image (ADR 0002). It is now submitted as an AML job, like run-book 38 Phase 0. It also never
   staged the bundle.
2. **The driver's `RuntimeError: job(s)/shard(s) failed` hid the node's real error.**
   `_aml_submit_and_wait` raises before the status file can be read. The script now always reads
   `_status/*.json` back into `metrics.smoke_error`, and treats a *missing* status file as its own
   diagnosis (the job died before the entrypoint → image or node auth).
3. **The image's fsd *wheel* must be rebuilt, not just the Dockerfile.** This was the actual
   failure: a pre-spec-44 wheel has no `manifest_code_files` and no `_activate_bundle_code`, so the
   node never fetches `code/` and never puts it on `sys.path` — `ModuleNotFoundError` however good
   the bundle is. **The node cannot self-diagnose this** (an fsd old enough to cause it contains
   none of the code that would report it), so the gate has to be driver-side: the optional
   `AZ_INFER_BUILD_CONTEXT` makes the script inspect the wheel and refuse to submit against a stale
   image, in 2 s instead of a 40–380 s cold start.

**Generalisable lesson for any future image-carried change:** stripping a `COPY` from a Dockerfile
is necessary but not sufficient — the wheel baked into the image is the thing that has to move.

**Phase 2 followed the same day and is green:** a real ROI run over `s2grid=476da24` (single MGRS
tile T33UWP, Apr–Sep 2018 @ 20 d → T=10) on that same adapter-less image produced **9/9 per-cell
`output.tif` + a STAC catalog in 494.9 s**, run `spec44-phase2-20260819T143617Z`. Two further
authoring bugs were caught there, both in the run-book script and both by fsd's own guards rather
than by the cluster: `storage=` takes a **backend name** (`"azure"`), not a URL — the URLs are
`output_folderpath`/`catalog_filepath`; and `run_aml_inference` needs
`cluster`/`environment`/**`root`**/`identity_client_id` **plus** an `ml_client`. The proven shape
was in `demos/e2e_austria_aml.py::step_inference` the whole time — **check the working caller before
writing a new one** is the lesson, and it would have saved two round trips.


## 2026-08-19 — spec 44 written, signed off, and **phase 1 implemented**: the bundle now carries the adapter's source

**The problem.** Running inference on AML needed a *second, adapter-specific* Docker image, because
the bundle carried only a code *reference* (spec 38 D4). Delivering one ~40-line `my_adapter.py` to
the nodes cost 4 hand-written files (Dockerfile, `.dockerignore`, 2 AML YAMLs) + `pip wheel` +
`az ml environment create` + a smoke job — **repeated on every adapter edit**, while retraining the
model itself cost nothing (the bundle already carried the weights).

**The change.** *Code moves into the bundle; dependencies stay in the image.* `bundle.save` embeds
the adapter's source under `code/` (auto-detected, package layout preserved); `bundle.load` prepends
it to `sys.path`. The inference image now differs only by **dependency family** (sklearn vs torch),
never by model or adapter.

**This REVERSED two LOCKED decisions in spec 38 D4** (the adapter-is-never-in-the-bundle rule, and
"P6 `deploy` builds the image"). Signed off by the user the same day; spec 38 D4 now carries a
supersession note and `runbooks/38` lost its per-adapter image steps. Everything else in D4 stands —
dedicated Environment, operator owns the build, reference-by-name, deps front-loaded to build time,
D11 smoke gate.

**Landed:** bundle format **v2** (v1 still loads unchanged); origin classification
(local → embed / installed → skip / `__main__` → refuse with the fix in the message); a `sys.path`
collision guard; per-origin drift messages; optional declared `requirements` checked by the smoke
job (never installed, via `packaging`); `code` files carried by both manifest-driven transports.
**23 new tests** (`tests/test_bundle_code.py`), mutation-checked.

**Amendment A1, found during implementation:** D2's collision guard as signed off compared *paths*,
which would have broken save-then-load in one process (`api._ensure_bundle`, and every existing
bundle test). It compares **content** instead — byte-identical is not a collision.

**Two things the user asked that shaped the spec:** whether a library (MLflow) should do this
instead — answered in §6 with measured numbers (rejected for phase 1; genuinely strong for phase 2's
registry, now open question #7); and `packaging` adopted for PEP 508 parsing rather than hand-rolled.

**Not done:** the real-cluster gate, and phase 2 (`deploy`).


## 2026-07-31 — spec 41 P7 **reviewed** (Opus): 4 doc-accuracy findings fixed, merged to `main` → NEXT: the user runs the D13 cold-start gate

Review of `worktree-p7-tutorial-howtos` against spec 41 §3/D9/D10 and D13's "must not fail" bar,
in the spirit of the P5/P6 reviews (each of which found 8 issues in a branch its authoring session
had declared green).

**`docs/tutorial.md` came through clean.** Every number in it was re-derived from the committed
fixture rather than taken on trust — 36 granules / one MGRS tile `T33UWP`, 43 fields at
20 `grain_maize_corn_popcorn` / 13 `hemp_cannabis` / 10 `other`, `offset == 0` on every row, grid
cell `4772924` at the stated bounds, 27 MB on disk, date span 2018-04-01 → 2018-09-28 — all
confirmed. **The handoff's `T = 10` correction is right**, verified two independent ways through
`fsd.api.compute_n_timestamps`: the tutorial's own midnight window (2018-04-01 → 2018-09-29) and
the catalog-derived window `test_tutorial_fixture.py` actually uses (min timestamp → max + 1 day)
both give `ceil(181 / 20) = 10`. Every call in the tutorial matches
`test_pipeline_create_training_data_train_and_infer`'s real sequence and keyword names, and the
per-**pixel** return-shape statement (with the `aggregate="median_per_id"` escape hatch) is correct.

**Four findings, all in the how-tos, all fixed** (`cdb7e0d`):

| # | Finding | Fix |
|---|---|---|
| 1 | `bundle-your-model.md` sold the **F1 anti-skew guarantee as unconditional**. It holds only if the adapter is *also* passed to `create_training_data(adapter=…)`; without it the training call writes raw bands and the transform runs at inference only — the exact skew the section claims to rule out (`api.py:358-359`). A reader following that page plus `run-at-scale.md`, whose snippet passes no `adapter=`, would have shipped skewed features. | states the condition |
| 2 | Same page attributed the `T == n_timestamps` preflight to **both** verbs. `create_training_data` deliberately does not check it (`api.py:386`, *"D6: no n_timestamps preflight — T is caller-set"*); only `run_inference` does (`api.py:944`). | attributed correctly |
| 3 | `download-real-imagery.md`'s byte table **did not reproduce from its own stated multiplier**: row 3 applied the 4-band 426 MB figure to a 3-band config (1.7 GB → ~1.5 GB), and row 1's measured ~18 GB is the real-archive average (~357 MB/granule = 74 GB ÷ 207), not 52 × 426 MB = 22 GB. | per-row provenance column + "426 MB is a ceiling" note |
| 4 | `CdseCredentials` / `fsd` / `os` used in three copy-paste snippets that never imported them. | imports added — which also brings those blocks under `test_doc_snippets_use_real_fsd_attributes`, since it only inspects blocks that import from `fsd` |

**Also added `docs/howto/README.md`** — both `README.md` and the tutorial link to `docs/howto/`,
which without an index renders as a bare directory listing at exactly the moment a first-timer
leaves the tutorial. The index restates Diátaxis's "a how-to cannot promise safety" boundary at the
entry point instead of only inside each page.

**Checks that found nothing**, recorded so they aren't re-run: `AZ_*` parity between the how-tos
and `env.example.sh` (4 vars, exact match); an identifier sweep of all six new files for GUIDs /
`abfss://` accounts / `.blob.core` / `.azurecr.io` / subnet CIDRs (**no hits** — the sole `rise`
mention is the project codename already public in `ARCHITECTURE.md` and `ROADMAP.md`); every
relative link and run-book/example target resolving; the `mpc`/`azure`/`aml`/`grid`/`model-example`
extras all existing; `merge="reproject"`, `storage="azure"`, `bundle.save`/`read_spec`,
`grid.roi_to_s2_grids`, and the `modify.*` feature functions all matching their real signatures;
and the `~100 km from every labelled field` rejection of `s2grid=476da24` matching the archive.

**Gate:** `pytest -q tests/test_docs.py` → **153 passed, 82 skipped**; `ruff check src/ tests/
demos/ examples/` clean. `tests/test_tutorial_fixture.py`'s 3–4 min pipeline test was **not**
re-run — docs-only change, and CLAUDE.md keeps long/pipeline scripts off Claude. Branch merged to
`main` `--no-ff` and the worktree pruned (standing practice). **`main` is not pushed** — that stays
the user's call.

---

## 2026-07-31 — spec 41 P7 drafted: `docs/tutorial.md` + 5 `docs/howto/*` pages + README pointers → NEXT: the user runs the D13 cold-start gate

Per the P7 handoff (spec 41 §3/D10/D13): wrote `docs/tutorial.md` (narrates
`tests/test_tutorial_fixture.py::test_pipeline_create_training_data_train_and_infer` against the
committed fixture — `create_training_data` → train a trivial RF → `workflows.create_datacube.
run_create_datacube` → `run_inference` → COG + STAC) and five `docs/howto/*` pages (`your-own-
region`, `download-real-imagery`, `run-at-scale`, `bundle-your-model`, `serve-xyz`), sourced from
`demos/E2E_AUSTRIA.md` §4/§9/§6, `demos/E2E_AUSTRIA_AML.md` §8, and run-books 29/30. `examples/
eurocrops_rf.py` already met D10's bar (61 lines, no timing/plotting) — no change needed. Both
docs and README now point at the tutorial instead of "being built".

**One correction to the handoff's own numbers, caught by doing the arithmetic rather than copying
it:** the handoff's "T at mosaic_days=20: 9" is stale — it carries over spec 42 D1's original
24-granule/local-CDSE plan. The **committed** fixture is 36 granules, 2018-04-01 → 2018-09-28
(A1's MPC path), which gives `T = ceil(181 days / 20) = 10`, and `create_training_data`'s return is
per-**pixel** rows (not per-field) unless `aggregate="median_per_id"` is passed — the tutorial
states `(N, 10, 2)` with `N` described, not a specific fabricated pixel count. Neither `test_
tutorial_fixture.py` nor spec 42's acceptance criteria actually assert `T == 9` (checked — no such
assertion exists), so this was a documentation-only correction, not a code defect.

**Gate status:** `pytest -q tests/test_docs.py` (152 passed, includes all 6 new files under
`test_relative_links_resolve` + `test_doc_snippets_use_real_fsd_attributes`) and `pytest -q
--ignore=tests/test_tutorial_fixture.py` (709 passed / 84 skipped) both clean; `ruff check src/
tests/ demos/ examples/` clean; the pre-push identifier sweep (`RECIPES.md`) found no tracked hits.
**`tests/test_tutorial_fixture.py`'s own 3-4 minute pipeline test was deliberately not re-run** —
Claude doesn't run long scripts (CLAUDE.md), and the P6 entry below already has it passing at
3 min 18 s against this exact fixture. **The one gate that remains is D13's cold-start run** — the
user, fresh clone, fresh venv, `docs/tutorial.md` followed literally, first failure reported as a
spec-24 `_result.json`.

---

## 2026-07-31 — ✅ spec 42 DONE: the tutorial micro-fixture is built, verified offline and committed → spec 41 P6 closed, **P7 unblocked**

Run-book 43 ran end to end: Step 0 on the laptop, Steps 1-5 on an Azure ML compute instance against
the blob MPC archive, Steps 6-7 back on the laptop. **`tests/data/tutorial/` is committed** — 27 MB,
108 COGs, 36 granules x B04/B08/SCL over grid cell `4772924` (T33UWP, single tile),
2018-04-01 .. 2018-09-28, with `catalog.parquet`, 43 labelled fields, the cell polygon, `NOTICE` and
a provenance `README.md`.

**All three automated acceptance criteria pass offline in 3 min 18 s.** Criterion 4 (cold-start, spec
41 D13) is the user's and belongs to P7.

### What the real run found that no synthetic test could

| | |
|---|---|
| **`offset = 0`, not −1000** | The blob MPC archive serves the **pre-Collection-1** 2018 products — generated before baseline 04.00 arrived 2022-01-25, so `BOA_ADD_OFFSET` does not exist and 0 is the true declaration (spec 32 D3 derives it per item). The local CDSE archive's `_N0500_` granules are the *reprocessed* versions of the same acquisitions and correctly carry −1000. Both right; different product versions. |
| **72 granules over a FULL YEAR** | Spec 42 §1/D2 always said Apr–Sep 2018, but the generator had **no date filter** — invisible while the assumed source was the local (Apr–Sep-only) archive. `--startdate`/`--enddate` added; 72 → 36 in-window. |
| **43 fields collapsed to one class** | Spec 42 D3 hardcoded `{maize, hemp}` against label values it never checked. Real column is `crop`, real values are HCAT compound names. Fixed by **amendment A3**: majors derived by clipped area. |

### Three review fixes earned their keep on this run

- **F6** (`pass` computed, not hardcoded) is what *caught* the one-class collapse. Without it Step 0
  writes PASS and ships a single-class fixture.
- **A2** (`offset in (0, −1000)` instead of a hardcoded `== −1000`) is the only reason acceptance
  test 2 passed — the assertion it replaced would have **failed** against this archive's correct `0`.
- **F1** (redact `--archive-root` from the recorded invocation) held on real data: the committed
  `README.md` shows `--archive-root <archive-root>`, zero `abfss://`, in a public MIT repo.

### Also fixed, all surfaced by running it for real

`from fsd import storage as fs` in 3 run-book snippets (`fsd.storage` is a package; the functions
live in `fsd.storage.fs`) — now guarded by `test_doc_snippets_use_real_fsd_attributes`, which
AST-checks 13 documents and was **vacuous on first write** until its file selector matched
`python -c` blocks, not just ```` ```python ```` fences. `fs.put/get` are file-only, so Step 5's
directory call could never have worked — tar-one-object is now the primary path. `git check-ignore
-v` inverted Step 7's own verdict. `pystac.get_all_items()` deprecation. And Step 6 reads as a hang
because pytest captures the live `[setup] N/43 … ETA` line — the run-book now says `-s`.

**Gate:** `pytest -q` **698 passed / 87 skipped**, `ruff check src/ tests/ demos/` clean. Identifier
sweep over the staged tree: 7 hits, all documented false positives; no `abfss://` anywhere in the
committed fixture beyond placeholder docstrings.

---

## 2026-07-31 — run-book 43 Step 0 runs green on real data; spec 42 **A3**: the label collapse is derived, not hardcoded

Step 0 was run for real for the first time and **failed at its own gate** — which is the headline,
because that gate is one of the fixes from the 2026-07-30 review:

```
cell 4772924  bounds 15.3900,48.4821,15.4717,48.5320  fields 43  classes other=43
FAIL: expected 3 classes over a non-empty field set, got 1 class(es) over 43 field(s).
```

Review finding **F6** replaced a hardcoded `"pass": true` with a computed one. Without it this run
writes PASS, ships a **single-class** fixture, and the defect surfaces much later — in a tutorial
that trains a classifier on one class. The guard paid for itself on its first real invocation.

### Root cause: D3 assumed label values nobody had looked at

| | assumed | actual (`shapefiles/AT_2018_TRAIN.geojson`) |
|---|---|---|
| label column | `EC_hcat_n` | **`crop`** — `EC_hcat_n` belongs to a *different* workspace file, `austria_eurocrops_sampled_ethiopia_translated.geojson` |
| label values | `maize`, `hemp` | **HCAT compound names**: `grain_maize_corn_popcorn`, `hemp_cannabis`, … (9 crops, 100 fields each) |

`collapse_label` matched case-insensitively but not fuzzily — correctly — so every field became
`other`.

### A3: derive the majors, and justify the cell with a measurement

- **`pick_major_crops` ranks by clipped area inside the cell** and keeps the top `--n-major`
  (default 2). Area, not field count: area is what the datacube's pixels are. For `4772924` it
  yields `grain_maize_corn_popcorn` (25.1 ha) + `hemp_cannabis` (17.8 ha) — the crops D3 meant.
  `--label-col` (default `crop`) makes the column an argument too. It **refuses rather than
  degrades**: ≤ `n_major` distinct crops, or a cell with no field, both raise.
- **New `tests/data/tutorial/survey_cells.py`** ranks every cell over an ROI. Over `AT_ROI`:
  **179 of 300 cells hold ≥ 1 field.** `4772924` stays the pick — two cells have **8** crops rather
  than 7, but their **top-2 share is 50 % / 57 % against `4772924`'s 82 %**, so there the catch-all
  `other` would be the *largest* class. Variety is the wrong objective for a 3-class collapse.
- §1's crop distribution table was already right; the survey reproduces it exactly. Only D3's
  literals and the column name were wrong.

**Step 0 now:** `43 fields → grain_maize_corn_popcorn=20, hemp_cannabis=13, other=10`, `pass: true`.

### `roi_to_s2_grids`: comment corrected, code deliberately unchanged

The clip comment read as *"`gpd.overlay` cannot be used here"*. The real constraint is narrower —
overlay against the **un-unioned** `roi_gdf` multiplies rows and repeats cell ids; against the union
it is identical and unique. Measured all four variants (max symmetric difference **0.0**):

| clip method | AT_ROI (1 poly) | 900-poly ROI |
|---|---|---|
| `intersection(union)` — kept | **2.6 ms** | 80.5 ms |
| `overlay(vs union)` | 9.5 ms | 92.6 ms |
| `overlay(vs raw roi_gdf)` | 7.1 ms | 25.2 ms → **1167 rows, ids not unique** |
| `overlay(raw) + dissolve("id")` | 12.7 ms | **50.5 ms** |

overlay's speed comes from STRtree pruning **per ROI polygon**; the union collapses the right side
to one geometry, so the index prunes nothing. **The efficiency and the `InvalidBlockList`
duplicate-id bug had the same cause.** `dissolve` recovers both but is ~5× slower on the
single-geometry ROI — the documented shape of an ROI, i.e. the hot path. Kept as-is; only the
comment changed, now carrying the numbers so nobody re-derives this.

**Gate:** `pytest -q` **681 passed / 87 skipped** (674 + 7), `ruff check src/ tests/ demos/` clean.
Identifier sweep: 32 values, 7 hits, all documented false positives, none in the 6 changed files.

---

## 2026-07-30 — P6 step 1 REVIEWED: 8 findings, 2 blocking, all fixed → NEXT: sign off spec 42 **A2**, then merge + run run-book 43

The Opus review of the P6 step-1 branch (`worktree-p6-build-fixture`, base `main` @ `a9a356b`),
against **spec 42** D1-D6/§3/§8 A1 and **run-book 43**'s normative CLI blocks. Same posture as the
P5 review: the authoring session declared it green (665/87, ruff clean — **verified true**), and the
review still found **8 defects**.

### The two blocking ones

| # | defect |
|---|---|
| **F1** | **An infrastructure identifier would have been committed to a public repo.** `build_fixture.py` wrote `Generator invocation: {' '.join(sys.argv)}` into the fixture's `README.md` — a file spec 42 D6 *deliberately commits*. Run-book 43 Step 4 is invoked `--archive-root "$AZ_ARCHIVE_ROOT/archive"`, which the shell expands, so the concrete `abfss://…` url would have been published. The same function's closing lines asserted the opposite ("intentionally not recorded here (public MIT repo)"). **Fifth leak of this class**; the first that would have been *generated* rather than typed. |
| **F2** | **Step 4 truncated its own inputs.** Run-book 43 Step 4 passes `--roi tests/data/tutorial/roi.geojson --fields …/fields.geojson --out tests/data/tutorial` — inputs *inside* the output dir — and the generator re-serialized both back over them. `to_file` truncates first, so a crash mid-write destroys Step 0's output, which **cannot be regenerated on the VM** (Step 0 needs `shapefiles/` from the workspace root). An interrupted run would have cost a laptop round-trip on the hotspot A1 exists to avoid. |

### The handoff's flagged judgment call: the answer is "not faithful"

The prior session flagged, rather than silently decided, whether its offline substitute for A1's
revised acceptance test 2 was faithful. **It was not — and neither would any other offline test be.**
A1 asks the test to assert the offset was *"copied from the source, not invented"*; §4 puts that test
in `tests/test_tutorial_fixture.py`; run-book 43 Step 6 runs that suite **with the network
disconnected**. The one assertion A1 wants is the one that file can never make. The substitute's
only live check was `assert int(row["offset"]) == -1000` — which a generator that hardcoded `-1000`
also passes, i.e. exactly the failure mode A1 set out to exclude (and on the MPC path no granule id
carries a `_N####_` token, so the id-agreement branch never fires at all).

**Resolution — spec 42 amendment A2 (✅ signed off, 2026-07-30, user).** The source-equality gate moves
to where the source is reachable: the generator records per granule whether the offset was
`declared` (copied from the source catalog's column) or `derived` (D1's id-token fallback) and emits
`offset_sources` + `all_offsets_declared` in `_result.json`; run-book 43 Steps 2 and 4 gate on it.
The offline suite keeps only what is sound from the artifact alone (round-trip, value ∈ {0, −1000},
uniform across the fixture) — plus acceptance test 3's post-offset reflectance range, which A1
itself calls the check that catches a ~1000 DN error *however the offset arrived*.

### The other five

- **F4** — the generator computed `offset_source` per granule and then dropped it, keeping it only in
  a progress line. The run-book says paste the `_result.json`, not the logs (spec 24), so nothing
  gated on it. Now in the result JSON; this is also A2's mechanism.
- **F5** — `--check-only`'s `pass` omitted **2 of run-book Step 2's 4 stated PASS conditions** (all
  bands present, date span). It printed them and gated on the other two. `--bands` is now accepted by
  `--check-only` and gated; omitted, it records `unchecked` rather than silently satisfied.
- **F6** — Step 0's `_result.json` hardcoded `"pass": true`, with `expected: {"n_classes": 3}`
  written but never compared. If `EC_hcat_n`'s real values are not literally `maize`/`hemp`, every
  field collapses to `other` — one class, untrainable — and Step 0 would still have read PASS.
- **F7** — run-book Step 7's gitignore check was wrong in a way that inverts its verdict. Verified
  live: with the D6 negation working, `git check-ignore **-v**` *prints* the matching negation line
  and exits 0. The run-book said "expect: no output / PASS if prints nothing", so a **correct**
  negation reads as FAIL. Fixed to the un-`-v` form (`exit=1` == not ignored).
- **F8** — `--max-timestamps N` took the **first** N chronologically, so D2's own documented fallback
  (`--max-timestamps 12`) would have yielded Apr–Jun only, destroying the seasonal series D2 calls
  the point of keeping all 24. Now spread evenly across the span, endpoints kept.

### Negative controls, because one guard was vacuous

Both blocking fixes were negative-controlled. F1's held immediately. **F2's first test did not** —
it asserted byte-equality of the inputs, which *passed* even with the re-serialization restored,
because a GeoJSON round-trip is often byte-identical. The real property is that the generator must
not write to a path it read from **at all** (the hazard is truncation-on-crash, not divergence), so
the assertion moved to `st_mtime_ns`. That version fails correctly when the bug is restored. Content
equality is kept as a secondary check, now documented as insufficient on its own.

**Gate:** `pytest -q` **674 passed / 87 skipped** (665 baseline + 9 new), `ruff check src/ tests/
demos/` clean. Pre-push identifier sweep run over the staged tree: 32 concrete values, 7 hits, all
7 the documented known-clean false positives, **none in the changed files**.

**Merged and PUSHED — `origin/main` is at `2bdc4c6`** (2026-07-30, `a9a356b..2bdc4c6`, 3 commits).
A2 was signed off the same day; `worktree-p6-build-fixture` went into `main` with `--no-ff` and the
worktree + branch were pruned (standing practice). Post-merge gate on `main`: **676 passed / 89
skipped** (the +2/+2 vs the worktree's 674/87 is the documented gitignored-benchmark-report delta),
ruff clean. The push matters operationally, not just hygienically: **run-book 43 Step 1c clones from
GitHub**, so the VM could not have seen these generators otherwise.

---

## 2026-07-30 — P6 step 1: run-book 43's two generator scripts, written and offline-tested → NEXT: the user runs run-book 43 on an Azure VM

Run-book 43's Prerequisites block named a chicken-and-egg gap: it needs
`tests/data/tutorial/build_fixture.py` to exist, and said in as many words that the run-book
itself does not create it. The task was framed as one script; it is actually **two** (the run-book
splits across two machines, spec 42 §8 A1) — `derive_roi_and_labels.py` (Step 0, laptop, needs
`shapefiles/` which lives outside this repo) and `build_fixture.py` (Steps 2-4, Azure VM, needs the
blob archive). Both now exist, both ruff-clean, neither run for real (per CLAUDE.md — Claude never
runs networked/long scripts; that's the user's job on the VM).

| file | what it does |
|---|---|
| `tests/data/tutorial/derive_roi_and_labels.py` | ROI/labels: derives grid cell 4772924 via `roi_to_s2_grids`, clips+collapses `AT_2018_TRAIN`'s labels to the spec 42 D3 3-class scheme (`maize`/`hemp`/`other`), writes `roi.geojson` + `fields.geojson` |
| `tests/data/tutorial/build_fixture.py` | select → clip (via `raster.cog.to_cog`, ADR 0014) → catalog (radiometry read from the source's own declaration column, never hardcoded — A1; D1's id-token re-derivation kept as the offline fallback) → NOTICE/README → `_result.json`. `--check-only`/`--dry-run`/build modes match run-book 43 Steps 2/3/4's CLI exactly. Per-file idempotent/resumable; `--max-timestamps` fallback before the 30 MB cap. |

**Verified offline** (the hard constraint: neither script can be run for real without VM/blob
access) against synthetic mini-archives, mirroring `test_datacube_builder.py`'s `_write_tile`/
`_make_catalog` shape: `tests/test_build_fixture.py` (12 tests — selection, MGRS-tile parsing,
radiometry column fallback (`offset` → `boa_add_offset` → id-token derivation → refuse), dry-run
zero-writes, idempotent re-run, geometry recomputed from the clip not the source, `--max-timestamps`
fallback) and `tests/test_derive_roi_and_labels.py` (5 tests — cell selection, label collapse,
wrong-cell-id failure, missing-column failure, CLI/`_result.json` shape). A one-off (uncommitted)
smoke script additionally ran the FULL downstream pipeline — `build_fixture` → `create_training_data`
→ train a trivial classifier → `run_inference` → COG + STAC — against a synthetic fixture, to catch
wiring bugs in the acceptance-test-3 code path before the real fixture exists; it passed end to end.

**`tests/test_tutorial_fixture.py`** (judgment call, handoff recommended it): spec 42 §4 acceptance
tests 1-3, whole-module-skipped until `tests/data/tutorial/catalog.parquet` exists (it doesn't yet —
that's the VM's job). One deliberate deviation from §8 A1's revised acceptance test 2: A1 wants the
fixture's offset compared against the *source* catalog, but run-book 43 Step 6 runs this suite with
the network disconnected, so the source is unreachable by design. Test 2 instead checks the
strongest fact derivable from the shipped artifact alone (declaration round-trips + agrees with the
granule id's own baseline token where derivable) — documented as an offline substitute in the test's
docstring, not a silent reinterpretation.

**`.gitignore`** gained spec 42 D6's negation — three lines, not the one line D6 sketched:
`data/` (line 21) excludes the whole directory tree, and git cannot re-include a file whose parent
directory is excluded by a plain file-negation alone, so the un-exclusion has to walk back down the
tree (`!tests/data/` → `!tests/data/tutorial/` → `!tests/data/tutorial/**`), plus a re-ignore for
`tests/data/tutorial/__pycache__/` (the blanket `*.pyc` rule is un-ignored by the same negation).
Verified with `git check-ignore`/`git status` before relying on it.

**Gate:** `pytest -q` **665 passed / 87 skipped** in this worktree (648/84 fresh-worktree baseline +
17 new passing + 3 new skipped, per PROGRESS's own documented baseline-difference note), `ruff check
src/ tests/ demos/` clean.

**Not done / explicitly out of scope this session:** running run-book 43 itself (needs the VM —
confirm the user has AML compute access before assuming the fixture is imminent); `docs/tutorial.md`
(P7, gated on the real fixture); the two open P1 `test_docs.py` findings (still open, still cheap,
still not touched — see below).

## ✅ 2026-07-30 — P5 DONE: README + ARCHITECTURE + the PROGRESS split. Spec 41's floor is complete. → NEXT: P6 (the tutorial fixture)

**P1+P2+P5 were spec 41's stated floor** — "they hit all three original complaints, carry the least
risk, and leave the repo strictly better if P6/P7 never happen." All three are now done, plus P3 and
P4.

| deliverable | what changed |
|---|---|
| **`ARCHITECTURE.md`** (new) | the code map: C4 context/container/deployment as **Mermaid**, the module table, the **invariants**, the three modes, the layers, and a contributing section |
| **`README.md`** (rewrite) | was stale in exactly the way D6 assertion 3 predicts — it called `run_inference` a **stub** long after it had shipped *and* run on the cluster. Now: what fsd is, install, a 60-second three-verb example, and a "where to go next" table |
| **`PROGRESS.md`** (split, D12) | **3,691 → 93 lines.** A synthesized current-state section + the most recent entry + pointers |
| **`docs/progress-archive.md`** (new) | **61** older entries **moved verbatim** (one identifier scrubbed), one file, `status: historical` |
| **`ROADMAP.md` §2.1/2.2** | shrunk to pointers into `ARCHITECTURE.md` (D9: one fact, one home) |
| **`demos/README.md`** | relabelled — it now says plainly, at the top, that these are **timing harnesses**, not examples, with a table sending readers to `examples/`, `docs/tutorial.md` or `docs/howto/` instead |
| **`tests/test_docs.py`** | D6 assertions **2 and 3** added |

**`CONTEXT.md` needed no edit** — the demo/benchmark/example/tutorial/how-to glossary D10 asked for
already landed with ADR 0026 in the specs 41/42 session.

### The two new tests both earned their place immediately

- **Assertion 3 (README verbs)** is the one D6 says *"alone would have caught the current stale
  README"* — it checks every `fsd.<verb>(` the README calls is really in `fsd.__all__`. It now
  covers `download`, `create_training_data`, `run_inference`.
- **Assertion 2 (links resolve)** checks **59 relative links across 38 documents**. Verified
  non-vacuous by a negative control: injecting a broken link into `ARCHITECTURE.md` fails the test
  as `test_relative_links_resolve[ARCHITECTURE.md]`.
- **Scope is deliberate:** only the root documents and the maintained `docs/` tree. Point-in-time
  corpora are excluded — a rotted link in a spec is a fact about history, not a defect, and D3
  forbids editing them to fix it.

### The PROGRESS split broke the P4 parity test, correctly

Moving the log into `docs/` pulled **`AZ_DOWNLOAD_ROOT`** and **`AZ_INFER_ENV_NAME_VERSION`** into
the scanned corpus — two variables that have since been renamed or dropped, and which appear
**only** in the archive. The fix was to exclude the archive from the parity corpus, not to
resurrect two dead variables in `env.example.sh`: parity is about the *current* operational corpus,
and the archive is never edited after the fact.

**Gate:** `pytest -q` **649 passed / 86 skipped** on `main`, `ruff check src/ tests/ demos/` clean.

> ⚠️ **Expect 649/86 in this checkout and 647/84 in a fresh clone or worktree.** The difference is
> two *gitignored* benchmark reports (`benchmarks/datacube_throughput_report_{cog,jp2}.md`,
> `.gitignore:49`) that exist on this laptop, carry D4 headers, and are picked up by
> `test_docs.py`'s directory glob. Not a defect, but the test target set does depend on untracked
> files — a stray unheadered `.md` under `benchmarks/` would fail here and pass in CI.

**PUSHED — `origin/main` is at `8da99fc`** (2026-07-30, `b1d9781..8da99fc`, 15 commits). The
pre-push identifier sweep was clean: all 32 concrete values checked, only the documented
known-clean false positives hit.

### ✅ P5's acceptance gate is now closed — the Opus review happened, and found 8 things

**Spec 41 P5's gate was "readable only — no test exists. Opus review against this spec."** Done
2026-07-30 in a separate session (the author cannot be the reviewer). It found **2 blocking defects
and 6 accuracy issues**; all 8 are fixed, and the blocking class now has an automated gate.

**The two blocking ones were both in the README's 60-second example** — the first code a newcomer
copies, and it did not run. `fsd.download(...)` omitted the **required** `max_tiles` cost guardrail,
and `fsd.run_inference(...)` passed a `model_bundle=` keyword **that does not exist** (the bundle is
the first positional arg) while also omitting the three ROI-mode requirements
`catalog_filepath`/`mosaic_days`/`bands`. 2 of 3 calls raised `TypeError` before any work.

**Why the existing test missed it:** D6 assertion 3 checked the verbs are in `fsd.__all__` —
*existence*, not *callability*. It is now backed by
`test_readme_calls_bind_to_real_signatures`, which AST-parses every `fsd.<verb>(...)` in the
README's python blocks and `inspect.signature().bind()`s its real arity and keyword names against
the live function, executing nothing. Negative control: reverting either README fix fails it with
the exact `TypeError`. **P5's gate is no longer purely human.**

**The six accuracy fixes:**

| finding | fix |
|---|---|
| invariant 1 was stricter than the code — bare `open()` also serves **node-local scratch/CLI-local files** in 7 places (`api.py:828` even says so inline) | reworded to *"no module reaches a **remote** path outside `fsd.storage`"* with both exceptions named and the holdable line stated: a bare open is only legal on a path that cannot be a URL |
| §3 called `raster/` "the one place GDAL/VSI opens paths directly" — false (`api.py:788,840`, `model/engine.py:97`) | names the other two sites as the only other permitted ones |
| §8 said the sweep caught "three leaks" | **four** (`RECIPES.md:625`, edited in the very same commit) |
| **D9 leftover:** `ROADMAP.md` §2.3/§2.4 became second homes for `ARCHITECTURE.md` §6/§3 — and §2.3 was **stale**, naming Azure *Batch* as the runner target when AML is what shipped | both shrunk to pointers, same treatment P5 gave §2.1/2.2 |
| the archive's preamble claimed the entries are "verbatim" | they are — **except one deliberate scrub** of a concrete cluster identifier, now stated |
| the same fact recorded three ways (entry: "60 entries"/"100 lines"; commit: 61/94; actual: **61/93**) | corrected to 61 and 93 — the P1 review's accounting defect, recurring |

**Verified true, no action:** the split lost nothing — 61 pre-P5 entries in, 61 out, headings
identical **and in the same order**, bodies **byte-identical** apart from that one scrub. Invariants
2 (no `boto3`), 3 (`workflows/task.py` imports no runner) and 8 (`download=False` default) hold.
All 22 files in the module table exist. `18.8 min / 32 nodes` and `35 % of a 2067 s run` both match
their sources. **The assertion 2 scope call was right** — excluding point-in-time corpora follows
from D3, and the counter-argument (a rotted run-book link wastes an operator's time) is better
served by superseding the run-book than by editing it.

**Gate after the fixes:** `pytest -q` **650 passed / 86 skipped** on `main` (649 baseline + the new
test; 648/84 in a worktree, same +1), `ruff check src/ tests/ demos/` clean.

**PUSHED — `origin/main` is at `1274d67`** (2026-07-30, `8da99fc..1274d67`, 5 commits). The
identifier sweep was run on the changed files before the push: 32 concrete values checked, only the
documented known-clean false positives hit.

### ⚠️ Still open — two P1 findings, inherited

Neither is P5's doing; both belong to whoever touches `test_docs.py` next:

- **`superseded_by` is ambiguous across the `specs/`↔`runbooks/` namespaces.** `runbooks/42`'s
  `superseded_by: 41` resolves to `specs/41-docs-refactor.md` because the test searches `specs/`
  first — it **passes on the wrong file**; the intended target is
  `runbooks/41-recover-aml-job-timings.md`.
- **The two register indexes disagree on link style** — `specs/README.md` uses markdown links,
  `runbooks/README.md` bare backticks, so assertion 2 never sees the run-book index.



---

# Moved 2026-09-04 (later) — the #80 / `v0.1.0` entry

_Moved verbatim (ADR 0022) when the README entry replaced it. **Its closing paragraph names two
obligations OUTSIDE this repo** (the `rise/` consumer install + image extras, and the workspace
`CLAUDE.md` dev line). Those were hoisted into `PROGRESS.md`'s continuously-true current-state
block before this move, precisely so that archiving the entry would not bury them._

_Last updated: 2026-09-04 (**#80 IS DONE AND `v0.1.0` IS CUT.** `snakemake` → `[local]` and
`s3fs` → `[s3]`; the core install goes **104 packages / 689 MB → 51 / 578** (−53 / −111 MB).
`main` @ the merge of `worktree-issue-80-extras`; `pytest -q` **1081 passed / 103 skipped** — the
1074 baseline plus exactly the 7 tests added — and `ruff check src tests demos examples` clean.)_

_**The tag was cut with #93 still open, deliberately.** Your rule (2026-08-26) was that the tag is
LAST because *"a tag pins the dependency set **and** the asset layout, and both were still
moving."* The asset layout stopped moving on 2026-09-02 when the consumer-repo run went end to end
from `rise/`, and the dependency set stopped moving with #80. **#93 is documentation, and docs pin
nothing** — so it was dropped from the tag's prerequisites while THE ORDER's sequence otherwise
stands. That is a change to a standing instruction and is recorded here rather than absorbed._

_**The find that mattered, and it was nearly missed.** Both packages are "never imported by
`src/fsd/`", which is what makes the move free — but `workflows/shard.py` and
`workflows/infer_shard.py` are the **AML in-job entrypoints** and both call straight back into
`runners.run_local` / `run_local_inference`. **An AML node runs the same Snakemake orchestration a
laptop does.** Shipping the extras split without touching the image would have built fine and then
failed **~30 minutes into a dispatch**, on the cluster, with a bare `No module named snakemake`
from a child process. Node extras are now `("local", "azure", "mpc")`, which **changes the image
digest** (spec 56) — so **existing AML images must be rebuilt**, and that is the intended
consequence, not a side effect. This is [[real-run-beats-review]]'s shape exactly: the defect was
not in the changed lines, it was in what the changed lines were assumed not to reach._

_**The first draft of the error message said "Snakemake is not needed to run on AML."** It was
written before that call graph was traced, it was wrong, and it would have sent whoever hit the
node failure looking in the wrong place. The shipped message names the image case explicitly. A
guard's message is part of the guard._

- _**Named errors, at the two seams.** `runners._require_snakemake()` covers all three local entry
  points; `storage.fs._fs_and_path` maps a failed backend import to the extra that provides it
  (`s3://` → `[s3]`, `abfss://` → `[azure]`) instead of fsspec's "Install s3fs to access S3",
  which names a **package** rather than an **extra**. An unmapped protocol re-raises untouched._
- _**The split is a gate, not a convention** — two tests assert neither package is back in
  `[project] dependencies` and neither is imported under `src/fsd/`. Nothing at import time would
  otherwise notice the drift; that is precisely #95's failure mode, so #80 was not allowed to
  reproduce it._
- _**`[s3]`, not `[cdse]`.** The issue floated naming it after its main consumer. Rejected: s3fs is
  generic transport (AWS, MinIO, any `endpoint_url`), and `[mpc]` already means *a source* — naming
  a transport after one consumer would misfile it._
- _**One bug of my own, caught by the suite:** `import fsspec.utils` inside an `except` made
  `fsspec` local to the whole function and broke 28 storage tests. Moved to a module-level import._
- _**`numba` stays in core** (#81) — a real top-level import in `bands/modify.py` and
  `datacube/ops.py`, and it wants a benchmark first. The floor is ~420 MB regardless._

_**⚠️ Two things `v0.1.0` does NOT cover, both outside this repo.** The consumer repo `rise/`
installs `fsd[azure,aml,mpc,grid]` and its image builds with `("azure","mpc")` — **both need
`local` added** before its next run, or the next dispatch fails on the node. And the workspace
`CLAUDE.md`'s dev line still reads `pip install -e ".[dev]"`; `pytest` passes on that, but the
tutorial and any local-runner work need `.[dev,local]`._
---

# Moved 2026-09-04 — #94's own entry, under the rule #94 introduced

_The first entry archived by the convention the block below installed: **when you add an entry,
move the one below it.** Moved verbatim (ADR 0022) when the #80 entry replaced it._

_Last updated: 2026-09-03 (**#94 IS DONE — THE `PROGRESS.md` SPLIT IS RE-RUN.** This file went
**1,782 lines / 19,970 words → 148 lines / 1,762 words**, against spec 41 D12's ~2k-word target.
**1,737 lines were moved verbatim** into [`docs/progress-archive.md`](docs/progress-archive.md),
which goes 4,364 → 6,138 lines. Entries were **moved, never rewritten** (ADR 0022); only the two
continuously-true sections above — the current-state block and THE ORDER — were rewritten.)_

_**The file's own growth was the argument.** It grew ~132 lines in the single day the previous
session spent writing #85 entries into it: it grows fastest exactly when work is going well, which
is why "trim it when it gets long" has now failed twice. The guard against a third time is the
callout at the top of this file — **when you add an entry, move the one below it** — and that is a
convention, not a gate, so it is the same weakness [#95](https://github.com/nikhilsrajan/fsd/issues/95)
names for the `src/` changelog comments._

_**The issue's plan did not survive contact with the file.** #94 said "move everything below the
current-state block and the most recent entry", which assumes one entry format and one
current-state block. There were **three formats and four structural sections, interleaved**, so the
file had to be walked rather than cut. Four defects turned up in the walk, none of them in the
issue, and all four are now retired:_

- _a **`## NEXT: implement spec 54 — Sonnet /effort medium`** block that was a **live instruction ~8
  days dead** (spec 54 shipped 2026-08-26). This is the second instance of that class in two days —
  the `ARCHITECTURE.md` refresh on 2026-09-02 caught a live instruction to fill `env.example.sh`
  that spec 54 had retired — so it is a **pattern**: a stale instruction in a
  read-on-resume document is worse than a stale fact, because a session **acts** on it. Moved to
  the archive as a record._
- _**`## Most recent entry` headed a 2026-08-22 entry**, 1,196 lines below the actual most recent
  one. It was structural scaffolding of this file, not content, so it was not archived — it now
  sits where it is true._
- _**`## Where things stand` was a stale current-state block** opening "Current work: the docs
  refactor (spec 41)" while the current work was the notebook-usability sprint. Continuously-true
  by type, so ADR 0022 permits rewriting it; it was **moved verbatim anyway** (its body was mostly
  point-in-time session narrative) and a fresh one written above, sourced from `docs/history.md`._
- _**The archive's own frontmatter was wrong.** It claimed to be "the primary archaeology source",
  but specs 48–53 and the entire notebook-usability sprint appeared in it **zero times** — found
  the hard way while writing `docs/history.md`. This append closes that gap through 2026-09-03, and
  the frontmatter now states the coverage, the **two heading forms** (`## 2026-` and `## ✅ 2026-`,
  18 of 66 — a bare `grep '^## 2026'` mis-splits the file) and the fact that the archive is **not
  chronological end to end**._

_**Ordering call:** the archive was left **append-only and jumbled** and the convention stated in
the frontmatter, rather than sorted — sorting touches 4,364 existing lines and makes the diff
unreviewable, which is a bad trade for a file nobody scrolls. **Cut call:** D12 was taken
**literally** — this file keeps the current-state block, THE ORDER and **one** entry. The softer
reading, keeping "the last few" `_Previously:_` blocks, is exactly what produced 19,970 words._

_**One test changed, and it is the interesting part.** The move broke
`test_relative_links_resolve[docs/progress-archive.md]`: moved entries carry links written relative
to the **repo root** (`ARCHITECTURE.md`, `docs/adr/`, `specs/53-…`), which resolve from
`PROGRESS.md` and not from `docs/`. Repointing them is forbidden — they are moved entries. The test
already declared `_POINT_IN_TIME_EXCLUDE` and said in its own comment that point-in-time corpora are
excluded "deliberately", but `_docs_with_links()` **never applied the set** to its `docs/` sweep. So
the exclusion was a comment, not behaviour, and it only looked correct because the archive happened
to contain no root-relative links until now. The set is now honoured. This is the same shape as #95:
**a convention that was written down but never enforced.**_

_**Gates:** `pytest -q` **1072 passed / 101 skipped** and `ruff check src tests demos examples`
clean. That is the worktree baseline (1073/101, itself a known worktree artifact vs `main`'s
1075/103) **minus exactly one** — the archive's link-check parametrization, now not collected.
`tests/test_docs.py` alone: **179 passed / 99 skipped**; `git diff --stat`
reports **1,741 deletions / 1,885 insertions** across the three files, and a byte-level check
confirms every one of the 1,737 moved lines is present in the archive **unchanged** and no longer
duplicated here. The insertion surplus is the provenance notes and the two rewritten sections,
nothing else._
---

# Moved 2026-09-03 — the second `PROGRESS.md` split ([#94](https://github.com/nikhilsrajan/fsd/issues/94))

_Everything below this line was moved **verbatim** from `PROGRESS.md` on 2026-09-03, re-running spec
41 D12's split for the same reason it was run the first time on 2026-07-30: the file had regrown to
**1,782 lines / 19,970 words** against D12's ~2k-word target, and `CLAUDE.md` has every session read
it on resume, so the cost is paid repeatedly. Entries are **moved, never rewritten** (ADR 0022) —
where a moved block was already stale when it was moved, it stays stale here, because this file
records what `PROGRESS.md` said, not what is true now._

_**Coverage:** 2026-09-03 → 2026-08-20, newest first. It closes the gap that made this file
untrustworthy as an archaeology source: before this append, specs 48–53 and the entire
notebook-usability sprint appeared **zero times** in it, which is what `docs/history.md` ran into._

_**Three stale blocks are in here deliberately, as records rather than as instructions:** a
`## NEXT: implement spec 54 — Sonnet /effort medium` block (spec 54 shipped 2026-08-26, so the
instruction was ~8 days dead where it sat); a `## Where things stand` current-state block opening
"Current work: the docs refactor (spec 41)" when the current work was the notebook-usability sprint;
and a `## Most recent entry` header that in `PROGRESS.md` sat 1,196 lines **below** the actual most
recent entry. That header was structural scaffolding of `PROGRESS.md`, not content, so it was not
moved — it now sits where it is true._

_(#94, 2026-09-03: the entry below was `PROGRESS.md`'s `_Last updated:_` block — the most recent
entry at the moment of the split, moved here in the same pass that it describes. Its `→ NEXT`
paragraph is the plan for the work that produced this append.)_

_Last updated: 2026-09-03 (**#85 IS CLOSED AND PUSHED; #95 + #96 FILED; #94 IS PREPPED AND HANDED
OFF.** `main` @ `c68adba`, clean, **pushed — `origin/main` and `main` are identical**. Baton:
**`/tmp/handoff-issue-94-progress-split-2026-09-03.md`**._

_**#85 closed** with the full statistics in its closing comment: backward references in `src/fsd`
**1,187 → 92 (−92%)**; the changelog scaffolding (`spec NN` / `Dn` / `ACn` / dates) **1,096 → 10**;
**41 distinct issue references before, 41 after, none lost**. Prose density did not move
(0.49 → 0.49) and that is the honest result — tag density was the signal, not sentence count. A
before/after audit of the reference SETS caught `#67` dropped to zero in `verify_image.py`, restored
in `5730af4`; no test checks that, which is why #85 named it a constraint._

_**Two follow-ups filed:** **#95** — nothing prevents the changelog re-accreting, since the
convention is a document rather than a gate (its own evidence: refs grew +24% in the 13 days after
the convention landed, all of it in files written *after* it). **#96** — ~35 user-facing error and
`--help` strings cite internal spec decisions ("spec 51 D6") at consumers who have no `specs/`;
a behaviour change, so it was out of scope for a comments-only pass._

_**→ NEXT: [#94](https://github.com/nikhilsrajan/fsd/issues/94)**, chosen by the user ahead of #93.
Re-measured 2026-09-03: `PROGRESS.md` is **1,742 lines / 19,477 words**, ~10× D12's ~2k-word target,
and **it grew ~132 lines in the single day** this session was writing #85 entries into it. The
handoff carries what the issue does not: the file has **three interleaved formats**, not one, so
there is no single boundary to cut at; and four defects found while measuring — a **live
`## NEXT: implement spec 54` instruction ~8 days stale** (line 576), a `## Most recent entry` header
1,196 lines below the actual most recent entry (line 1203), a `## Where things stand` block still
saying "current work: the docs refactor (spec 41)" (line 1067), and an archive whose heading format
is **two** variants (`## 2026-` and `## ✅ 2026-`, 18 of 66) so a naive grep mis-splits it._

_**Deliberately kept short:** the next task is to shrink this file, so this entry does not
elaborate. Detail lives in the handoff and in #85's closing comment._

_Previously: 2026-09-03 (**STEP 4 IS DONE — #85's `src/` COMMENT SWEEP IS COMPLETE AND MERGED
INTO `main` @ `816823c`** (`--no-ff`, 7 commits; worktree pruned, branch deleted). Backward
references across `src/fsd` went **1,187 → 91 (−92 %)**. Every commit is gated on `pytest -q`, on
`ruff check src tests demos examples`, and on a **docstring-stripped AST byte-identical to `6ed05bb`
across all 58 files** — the diff is provably comments-only. On merged `main`: **1075 passed / 103
skipped**, matching the pre-sweep baseline exactly. (Inside the worktree the same suite reported
1073/101; that two-test gap is a worktree artifact — it reproduces on a clean checkout of `6ed05bb`
and was verified as such before any edit — not the sweep.)_

_**The open question was settled as option (a): the sweep was EXTENDED** to `image/`, `aml/`,
`registry/`, `config.py` and `cli.py`, which #85's landing order predates. They were the freshest
instance of the habit — every one written *after* the convention landed — and folding them in is the
whole point of doing this before the next development push. The two Snakefiles were swept too; they
are package data, so every earlier `*.py` sweep had missed them._

_**Six commits, in order:** a scripted mechanical pass (340 reference-only parentheticals, refs
1,187 → 733), then judgment passes on `api.py` (285 → 16), `workflows/` (341 → 26), `model/`
(179 → 11), `sources/` (112 → 16), and everything remaining. The 91 refs left are the ones that
should be: GitHub issue refs (**the `TODO #NN` → issue mapping is intact**), `Spec:` module anchors,
and `spec NN Dn` inside user-facing error/argparse strings, which are code._

_**⚠️ The AST check earned its place.** In `sources/` it caught three "comment" edits that were
actually inside `raise ValueError(...)` and argparse help — reverted before commit. A comments-only
diff is not comments-only just because it looks it._

_**Prose density did NOT move (0.49 → 0.49), and that is the honest result, not a miss.** #85's own
classification put ~21 % of prose in the narrative categories and 68 % in "plain description: keep,
tighten". What made `src/` *read* like a changelog was tag density, and that fell 92 %. Roughly as
many lines came back as reformatting (summary / blank / body, per the convention) as came out as
narration. `api.py` and the public verb docstrings sit deliberately above the ~0.30 guide — they are
the user documentation, and this sprint is about notebook usability._

_**⚠️ Merged and pruned at the user's instruction — note what that skipped.** The standing practice
wants "reviewed + green"; this landed **green but NOT independently reviewed**, because the authoring
session cannot be its own reviewer. The AST-equivalence gate is what stands in for that review: it
proves no executable code moved, so the residual risk is prose quality, never behaviour._

_**Still open:** (1) **pushing** — `main` is **21 commits ahead of `origin/main` (`c49a9fc`)** (measured, not tallied --
earlier entries in this file undercounted it), still
the user's call; (2) **two follow-ups worth filing
rather than bolting on** — a ref-density gate so this cannot re-accrete (the handoff already flagged
it as scope beyond #85), and the ~15 user-facing error/argparse strings that cite internal spec
decisions ("spec 51 D6", "spec 47 D3") at operators who cannot read `specs/`. Fixing the latter is a
behaviour change, so it stayed out of a comments-only pass._

_Previously: 2026-09-03 (**STEP 4 IS PREPPED AND HANDED OFF — #85, the `src/` comment trim.**
Baton: **`/tmp/handoff-issue-85-comment-trim-2026-09-03.md`**; the per-file counter it names is at
`/tmp/refcount.py`. `main` @ `d5a7814`, clean, **10 commits ahead of `origin/main` (`c49a9fc`),
still unpushed**. `1075 passed / 103 skipped`, ruff clean._

_**#85's own measurements are STALE, and re-measuring confirmed its thesis** (posted as a comment on
the issue). `src/fsd` grew **13,271 → 15,889 lines** since 2026-08-21 as specs 51–56 landed, and
backward references went **986 → 1,223, up 24 %**. The issue argued for doing the trim *"before the
next major development push — new code written alongside it inherits the habit"*; every one of
`model/registry.py` (59 refs), `config.py` (38), `image/digest.py` (18), `aml/__init__.py` (14),
`image/registry.py` (12), `image/definition.py` (10) and `registry/_core.py` (8) was written **after**
the convention landed in `eb7f29f`. **The encouraging half: the worked sample is holding** —
`storage/fs.py` is still **4 refs / 380 lines**, untouched. The convention sticks once applied; it is
just not being applied to new code._

_**Two things the next session must settle before sweeping:** (1) #85's landing order predates
`image/`, `aml/`, `registry/`, `config.py` and `cli.py` — fold them in (~100 refs, the freshest
instance of the habit) or file separately, but say which; (2) nothing prevents re-accretion, since
the convention is a document rather than a gate — a ref-density check is a real idea but is **scope
beyond #85**, so file it rather than bolting it on. Also note one constraint has drifted: the fourth
source-text test is at `tests/test_verify_adapter.py:311`, not `:305` as the issue says._

_**#93 grew a scoped item (user, 2026-09-03): a notebook front door.** The team prefers notebooks to
`.md` files. Assessed: **not** `e2e_austria_aml.ipynb` — it needs VPN + `az login` + a workspace +
RBAC + two ACR builds, it is not in the wheel, and `tests/test_notebooks.py` strips its outputs, so
it renders resultless on GitHub, which is exactly what a notebook reader came for. **The proposal is
`docs/tutorial.ipynb`** — the markdown tutorial is 241 lines with 5 python blocks, offline, fixture-
backed, ~4 min — and it **can ship WITH outputs**, because the tutorial fixture holds no cloud
identifiers to leak (`TRACKED_NOTEBOOKS` is an explicit opt-in list). `e2e_austria_aml.ipynb` becomes
the advertised **worked cloud example**. Risk to design around: two tutorials drifting — pick one
canonical and generate the other under test. **Deferred behind #85 by the user; wants its own spec**
(it touches spec 41 D1's audience table and ADR 0026's taxonomy)._

_Previously: 2026-09-02 (**STEP 3 IS DONE — `docs/history.md` APPROVED BY THE USER, BOTH
BRANCHES MERGED, #55 CLOSED.** Two `--no-ff` merges onto `main`: `worktree-spec-43-history`
(spec 43 + `docs/history.md` + ADR 0027) and `worktree-architecture-refresh` (the
`ARCHITECTURE.md` refresh). Both worktrees pruned, both branches deleted. **NOT PUSHED** —
`origin/main` is @ `c49a9fc` (it moved since the #55 handoff was written, which said `f7d4bd0`), so
`main` is **8 commits ahead** of it and #55's closing comment
points at commits GitHub cannot yet resolve (the comment says so; same precedent as #64/#65/#66).
**Pushing is the user's call.** → **THE ORDER's step 4: [#85](https://github.com/nikhilsrajan/fsd/issues/85)**
(trim the changelog out of `src/` comments, one package per session, 7 left). #80/#82 unblocked;
**the tag is still LAST**.)_

_**What landed.** `specs/43-history.md` (signed off by the user 2026-09-02 — the D6 era list
confirmed, §7's other three questions resolved as proposed) and **`docs/history.md`, 4,994 words,
eight eras**, each named by the question the project was facing and each carrying a fork taken, a
fork dropped, and the measurement that decided it. Plus **ADR 0027** (the append-only document
class) and a `README.md` pointer. Gates: **1073 passed / 101 skipped** (+2 — the two new files are
picked up by `test_docs.py`'s directory glob), ruff clean, and the `RECIPES.md` identifier sweep
**clean over both new files** — all 32 concrete values, zero hits. `test_relative_links_resolve`
earned its keep on the first run by failing on a link to `CLAUDE.md`, which lives at the workspace
root and is not in this repo._

_**Three findings from the archaeology worth not re-deriving.** (1) **The handoff's premise was
half wrong:** `docs/progress-archive.md` is necessary but **not sufficient** — specs 48–53 and the
whole notebook-usability sprint appear **zero times** in it, because `PROGRESS.md` regrew and holds
2026-08-20 → 09-02 itself; the archive is also **not in date order** (its 08-19/20 entries sit after
its 07-06 ones). Filed as **#94**. (2) **`DROPPED.md` is legacy-capability triage only** — it
mentions rslearn, the Leaflet dashboard, C4 and the SQLite catalog strategy **zero times** — and an
ADR by construction records a decision *taken*, so the declined forks had no home in any register.
That is `docs/history.md`'s whole justification. (3) **Spec 41 built three of Diátaxis's four
modes**; the word "explanation" appears **once** in its 587 lines, in the list. `docs/history.md`
fills that quadrant._

_**The through-line the story names, which no register had:** **existence is not identity.** One
tile per `(timestamp, band)` key losing coverage (spec 20); a STAC item id derived from a constant
filename stem (300 identical links); README verbs checked for presence in `__all__` rather than
callability (2 of 3 calls raised `TypeError`); resume-by-existence re-inferring a **different** ROI
(#66); a cube skipped as "already landed" then stamped with the wrong request's identity (spec 48
review); a registry left naming a deleted asset (spec 56 review). Six eras, one confusion._

_**Filed rather than fixed, per spec 43 D9:** **[#93](https://github.com/nikhilsrajan/fsd/issues/93)**
(the front-door pass — `README` → tutorial → how-tos, against `docs/findings/consumer-repo-friction.md`'s
eight friction points / four hard stops) and **[#94](https://github.com/nikhilsrajan/fsd/issues/94)**
(`PROGRESS.md` is 1,610 lines against spec 41 D12's ~2k-word target; re-running the split also fixes
the archive trap in (1) above)._

_**Also landed post-merge:** `ARCHITECTURE.md` gained the `docs/history.md` pointer that could not
be added while the two lived on separate branches — its link would have failed
`test_relative_links_resolve`._

_**#93 and #94 REMAIN OPEN, deliberately** — they are deferred work filed by spec 43 D9, not
things this session did. #93 is the front-door pass (`README` → tutorial → how-tos) against
`docs/findings/consumer-repo-friction.md`; #94 is `PROGRESS.md`'s regrowth past spec 41 D12's
~2k-word target, which this very entry adds to._

_Previously: 2026-09-02 (**STEP 2's MEASUREMENT IS IN — SPEC 57 CONFIRMED ON A REAL RUN.**
The consumer notebook ran end to end from `rise/` (fsd installed as a dependency, not a checkout),
which by itself closes the "does the consumer path work at all" question for specs 54/55/56/57 +
#92. The numbers, 299 cells: **`[collect]` 616 s → 26 s (23.7×)**, **`[stac]` 161 s → 10 s
(16.1×)**, the window **777 s → 36 s (21.6×)** against a predicted **<100 s** — beaten by 2.8×.
`[merge]`, the leg D2/D3/D4 deliberately do not touch, went 193 s → 80 s (2.4×) and so serves as a
**control on the link**: crediting *all* of that to a faster network still leaves ~9.9× for collect
and ~6.7× for stac as the code's own. **Spec 57 §9 step 5 is discharged**; recorded in `CHANGES.md`.)_

_**Spec 56 §9 step 10 — discharged the same day, cheaply.** The step's un-mockable half is
whether real `az ml environment show` reports a missing version as absent, since every other part
of D4 is covered against `tmp_path`. Probed live: `environment_exists("fsd-aml-env", "999999")`
→ **False**, `environment_exists(..., <real version>)` → **True**. That is the predicate D4 step 3
branches on, so the "registry entry points at a deleted asset" path provably fires. **Residual gap,
named not hidden:** the complete break-and-heal loop (corrupt `_aml.json` → build → confirm reuse,
run-book 57 step 6) was **not** run end to end — its remaining links (fall-through to build,
`publish` idempotent by digest returning the same registry version, `write_aml_record` repointing
the sidecar) are unit-covered but not observed together against Azure. Judged not worth a 10–20 min
ACR build for the marginal evidence; the loop stays available in the run-book if that call changes._

_**STEP 2 IS THEREFORE COMPLETE.** → step 3, **[#55](https://github.com/nikhilsrajan/fsd/issues/55)**
(docs refactor), which **needs its own spec and a discussion before any work starts**. **#80** and
**#82** are unblocked; the **tag is still LAST**._

_**#55 SCOPED 2026-09-02 — it is far narrower than its issue text; do not re-derive this.** The
issue asks for (1) a chronological story and (2) a "≤~5-file C4 doc set" over a **174-file /
~399k-word** corpus (61 specs, 30 run-books, 43 `docs/`, 13 top-level). **Half is already done and
was deliberately changed.** **(2) is CLOSED by spec 41 D0**, which demoted C4 from file-count driver
to the *section outline of one file* — `ARCHITECTURE.md`, which exists — and dropped the file count,
the Component level as a separate doc, and Level 4 entirely. Its cited trap is worth keeping: C4's
"container" means a separately runnable thing (c4model.com opens with **"Not Docker!"**), so fsd's
C4 containers are **driver / AML node / blob / catalog**, *not* its AML images. **Do not re-propose
a multi-file C4 set.** **(1) is spec 43, which was never written:** spec 41 named the artifact
(`docs/history.md`), slotted it **P8**, sized it **Opus ~1 session**, and deferred it until P1/P2
had done the archaeology. The specs jump **42 → 44** and `docs/history.md` does not exist. Its
source is already staged — **`docs/progress-archive.md`** (364 KB), whose frontmatter names itself
"the primary archaeology source for spec 43's `docs/history.md`". So **"wrap up #55" = write spec 43
→ `docs/history.md` → close #55.** **Numbering:** spec 41 + the archive reference "spec 43" in ~8
places and this repo's own precedent (ADR 0024 / spec 41 D8) was to **force-align numbers rather
than rewrite references** — so **43, not 58**; confirm at sign-off. **#55's gate is discharged** —
it required "a timed e2e demo with stepwise time accounting", which step 2 produced._

_**Found during the break, diagnosed 2026-09-02, not a defect:** re-running the notebook rebuilt
both images. Cause was **not** a commit — `origin/main` never moved off `f7d4bd0`, and `git+…@main`
resolves against the *remote*, so local commits are invisible to it. `DEFAULT_BASE` is
`mcr.microsoft.com/azureml/openmpi4.1.0-ubuntu22.04:`**`latest`**, and MCR moved it
(`7276cbc0…` → `3bd33cab…`) — the digest covers the base's resolved sha, so the rebuild was
correct. Spec 56 D4's "a base image moved under a tag you did not pin", observed. **Pinning is
free**: `_resolve_base` maps `repo:latest` → `repo@sha256:X` and passes `repo@sha256:X` through
unchanged, so both forms produce a byte-identical payload — verified — and pinning to the current
sha reuses the existing version rather than rebuilding. Recommended through the measurement window,
re-pinned deliberately after._

_**Two proposals raised, neither filed** (awaiting the user's yes): (a) `ensure_environment` should
say **why** it rebuilt — it holds both the new digest and the previously-registered definition, so
`(rebuilt: base moved 7276cbc0… -> 3bd33cab…)` costs nothing and would have replaced a whole
diagnostic round trip; (b) ship fsd's notebook leak guard (`tests/test_notebooks.py`'s six
patterns) as `fsd lint-notebooks` + a pre-commit hook, since consumer repos have no equivalent and
a concrete storage URL reached `rise`'s working tree this week._

_Previously: 2026-08-28 (**STEP 2 PREPARED — `runbooks/57-consumer-repo-e2e-run.md` written and
handed to the user; the run itself is theirs, not an agent's.** `main` still @ `f7d4bd0`, clean.
The run-book covers seven steps: patch the notebook (below), rebuild `rise/.venv` from `@main`,
config+`az` preflight, `build_images.ipynb`, the e2e notebook §0–3, **§4.1+4.2 — the measurement**
(`[collect]`/`[stac]` vs the **616 s / 161 s** baseline; spec 57 predicts <100 s combined, graded in
three bands so a miss is a finding rather than a hidden failure), and **last** the forced
stale-entry rebuild (spec 56 §9 step 10 / D4 step 3: break `_aml.json` to a bogus AML version →
expect *build* with an unchanged `registry_version`, then *reuse* of that same asset). Every python
snippet in it compiles; step 0's verifier was run against the live notebook and correctly reports
`fail`._

_**BLOCKER FOUND, not yet fixed — the consumer notebook cannot run as it stands.**
`rise/notebooks/e2e_austria_aml.ipynb` is a **verbatim copy of fsd's own developer notebook** (33
of 34 cells byte-identical; only cell 0's markdown differs, and it is the pre-#92 wording). Its
**code cell 3** therefore carries two fsd-checkout assumptions that are wrong in a consumer repo:
`assert (REPO / "pyproject.toml").exists()` — `rise/` has none, so the cell raises immediately —
and `fsd=f"path:{REPO}"`, which `digest.py:_resolve_fsd` turns into `wheel:<hash>` of that
directory, while `rise/notebooks/build_images.ipynb` declares
`fsd="git+https://github.com/nikhilsrajan/fsd@main"` → `git+…@<40-char sha>`. **Different payloads,
different digests, different images:** even with the assert deleted the e2e notebook would not
reuse what `build_images.ipynb` built, would start its own ACR build, and would then trip its own
`assert _r.reused`. The two-line fix is **step 0 of the run-book**, not applied here —
[[notebooks-are-reference-not-workspace]]: propose in a run-book, edit only on an explicit yes._

_**Also landed this session:** `rise/docs/environment.md` got #92's three deltas (the `root`
paragraph now names every non-reader — `fsd init` does not prompt, `fsd config` does not print,
`--from-env-file` parses and drops it; the duplicated `fsd config` paragraph dropped; "six values"
→ seven keys), mirroring `docs/reference/environment.md` @ `f7d4bd0`. **Separate, not done:** that
whole file is an fsd-internal copy — it cites `tests/test_docs.py`, `src/fsd/config.py`,
`runbooks/`, `demos/e2e_austria_aml.py` and `docs/findings/`, none of which exist in `rise`, and
sections 3/6/7/8/9 are run-book variables with no meaning there. Worth a consumer-shaped rewrite;
needs the user's call. **NEXT: the user runs run-book 57 and pastes back each step's
`_result.json`; Claude diffs it.**_

_Previously: 2026-08-28 (**#92 DONE, CLOSED + PUSHED — `main` @ `ee7277b`, clean.** The AZ_ROOT
cleanup landed (`3a968dc`, merged `--no-ff` as `ee7277b`; worktree pruned, branch deleted). Three
files, five edits, **no code**: `docs/howto/run-at-scale.md` (its "all six values `fsd init` asks
for" prerequisite → five required + two optional registries, with the storage root explicitly not
among them; the `runner_kwargs` block now labelled as an argument dict), `docs/reference/environment.md`
(the `root` paragraph names every non-reader — `fsd init` does not prompt, `fsd config` does not
print, `--from-env-file` parses and drops it, `tests/test_cli.py:58` — and every actual reader; a
duplicated `fsd config` paragraph dropped; "six values" → seven keys), and
`notebooks/e2e_austria_aml.ipynb` markdown cell 0, which said the model registry lives at
`$AZ_ROOT/model_registry` and so contradicted **code cell 3 of the same notebook** and spec 55 D2.
`1068 passed / 99 skipped`, ruff clean — baseline unchanged. **Two reported defects were not
defects:** `run-at-scale.md:51` is `runner_kwargs`, and `runner_kwargs["root"]` is a **required
argument** (`src/fsd/api.py:499-501`) — reframed, not deleted, since removing it would have broken
the example; and `demos/e2e_austria_aml.py` + `demos/E2E_AUSTRIA_AML.md` already read `AZ_ROOT`
from the environment as a per-run root. A mention is not a defect. **Still stale, out of scope:**
`rise/docs/environment.md` in the consumer repo carries the old framing — fix it when that repo is
next touched, i.e. during step 2. **NEXT: step 2 of THE ORDER below, the consumer-repo run — the
user's to run, not an agent's** ([[real-run-beats-review]], CLAUDE.md's "Claude never runs
pipeline/networked scripts")._

_Previously: 2026-08-28 (**SPEC 57 LANDED; `notebooks/shapefiles/` NOW PUBLIC WITH A NOTICE;
`main` @ `e4879b0`, pushed, clean.** Since the entry below: the user un-ignored
`notebooks/shapefiles/` themselves (`16b66f6` — 900 EuroCrops-derived Austrian fields + the two
demo geometries + a scrubbed `00_build_images.ipynb`, so critical-path item 2 is **done**), and a
`NOTICE` was added beside them (`e4879b0`) recording provenance and stating plainly that the
**upstream EuroCrops licence has NOT been reconciled with this repo's MIT licence** — it grants
nothing fsd cannot. Nothing reaches the wheel (`packages.find` is `where=["src"]`). The canonical
EuroCrops citation URL is deliberately **absent** from the NOTICE: it needs a lookup nobody has
done. **NEXT: issue #92, handed off to a fresh Opus session** —
`/tmp/handoff-issue-92-az-root-2026-08-28.md`. The ordered chain it must not drop is directly
below.)_

_Previously: 2026-08-27 (**SPEC 57 IMPLEMENTED (Sonnet) + REVIEWED (Opus) + MERGED + PUSHED —
`main` @ `52f7b2b`.** D1 (segment ticker) + D2 (in-memory footprint, ROI mode) + D5 (GDAL
sidecar-probe config) + D3 (threaded collect) + D4 (threaded STAC writes) all landed; worktree
`spec-57-collect-stac` merged `--no-ff`, then pruned and its branch deleted (standing practice).
`1068 passed / 99 skipped`, ruff clean. **Review found one real bug** (commit `e745a57`): D5's
`CPL_VSIL_CURL_ALLOWED_EXTENSIONS` is a GDAL *whitelist*, not a hint — a remote file whose
extension is not listed reads as **non-existent** — so `.tif` alone would have made remote `.jp2`
and `.tiff` band files unopenable (`datacube.builder._RASTER_EXTS`; any `cog=False` imagery staged
on blob). Widened to `.tif,.tiff,.jp2`, with a test tying the whitelist to `_RASTER_EXTS`. Review
also added AC2's missing **caller-side** test (nothing asserted `_run_inference_roi` builds the
in-memory mapping at all) and made the byte-identity test `.buffer(0)` both sides. The
implementer's three other flags resolved as non-issues: `.buffer(0)` parity holds (grids are
EPSG:4326, `grid.py:112`, and `to_json()` does not reproject); D3's and D4's pools run strictly in
sequence, so never more than 16 threads are live; `as_completed`'s exception ordering satisfies
AC5. **NEXT: §9 step 5 — a real cluster run against the pre-D1 baseline.** It is the user's, not
an agent's ([[real-run-beats-review]]), and until it happens the 777 s → <100 s number is a
*hypothesis*. Spec 56's §9 step 10 real AML run is also still outstanding, unrelated.
[The `00_build_images.ipynb` leak-guard warning recorded here was resolved by the user in
`16b66f6`.])_

**Spec 57 — LANDED 2026-08-27** (signed off, implemented, reviewed, merged).
`specs/57-collect-and-stac-round-trips.md`, advancing [#61](https://github.com/nikhilsrajan/fsd/issues/61)
(closes its fixes (b) and (c); (d), node-side Item emission, stays open). Origin: the user watched a
real AML run and asked what the gap between `[collect]` and `[merge]` was. Answer, from #61's
segment measurement: **collect 616 s (2.05 s/cell) + STAC writes 161 s (0.53 s/item)** on 300
cells — it scales with the number of output cells, not with the work, and that run's inference had
already been skipped. Five decisions, in build order: **D1** print segment timings *first* (#61's
original suspect was a "627 s bundle upload" that measurement showed to be 13 s — do not optimise
blind); **D2** stop re-reading each cell's `geometry.geojson`, because those footprints are the
`grids.geojson` the driver itself wrote and still holds (~300 s, no threads); **D5** two GDAL
options to stop sidecar probes on every remote open; **D3** thread the COG opens; **D4** thread the
301 Item writes.

**The finding worth carrying forward: #61's own fix guidance was wrong, and the spec corrects it.**
#61 says to thread the metadata reads *"under a single `raster.rio_env`, since GDAL's env stack is
thread-local"*. Thread-local means the **opposite** of that conclusion — rasterio 1.4.4 keeps the
active env in `local = ThreadEnv()` (`rasterio/env.py:56`), so an `Env` entered on the driver
thread does not exist in a worker. Proved by direct execution, not by reading: `hasenv()` is
`True` in the main thread and `False` in the worker. Since `rio_env` is what carries
`AZURE_STORAGE_ACCESS_TOKEN`, following #61 literally would have had every worker open a remote COG
with **no credential**. Each worker enters its own env (D3). Instance of
[[verify-the-primitive-a-spec-cites]].

**Also rejected, with arithmetic (spec 57 §6):** running the STAC write and the merge concurrently
(the user's suggestion). They are independent in output but bottlenecked on the same link, so the
ceiling is `max(stac, merge)` = 777→616 s against D2–D5's 777→<100 s, it buys nothing on the common
`merge=False` run, and it adds a half-written catalog beside a failed merge.

**Not spec 57: [#77](https://github.com/nikhilsrajan/fsd/issues/77).** The same run felt slow for a
second, independent reason — inference *is* deduped, but on the node after dispatch, so a
95%-complete re-run still starts ~299 tasks to discover it needs ~15. That wants its own short
spec, mainly to settle presence-vs-stamp for the output skip.

**Read before touching either:** `specs/55-root-leaves-the-config.md`,
`specs/56-image-definitions-and-registry.md`. Both carry their sign-off resolutions in §7,
including **two decisions the user killed** (a note for a stale `root` key; a skip line for
`AZ_ROOT` in `--from-env-file`) — do not re-propose them.

**Spec 55 — DONE (merged).** `root` is no longer a config key: it names a *per-run destination*
chosen by whoever runs the job, not a durable address, so the caller passes it — spec 41 D7's
"takes a storage location as an argument" applied to the last value that escaped it.
`load(root=…)` raises `TypeError` on purpose, because that is the mistake a spec-54-era caller
makes. In the other direction, **`model_registry` + `image_registry` arrive as OPTIONAL keys**
(`AZ_MODEL_REGISTRY` / `AZ_IMAGE_REGISTRY`), so `load()` now splits required from optional: a
missing required key still raises `MissingConfig` naming every gap at once, a missing optional one
is `None`. **fsd's own signatures still take `registry=` as an argument, always** — the keys exist
because the two tracked notebooks are leak-guarded and may not hold a literal `abfss://` URL, and
the concrete values belong in `rise` + `AZURE_INFRA_PRIVATE.md`, never in this repo. Also
`fsd init --blank` (write it empty, fill it in by hand; refuses to clobber without `--force`) and
a non-tty `fsd init` that names the three non-interactive forms instead of raising `EOFError`.

**Spec 56 — IMPLEMENTED in a worktree, §9 steps 0-9 done, step 10 (the real AML run) still
outstanding.** `fsd/registry/_core.py` (step 0) took the **copy fallback, not extraction**: §7 Q1
recommended extraction, but `tests/test_registry.py` monkeypatches `registry._list_versions` /
calls `registry._write_new_version` directly, which only works if those functions stay defined in
`fsd/model/registry.py`'s own namespace — a real move-and-reexport would leave the closures
resolving against `_core`'s globals instead and silently break the patches. So `fsd/model/registry.py`
is **byte-for-byte untouched** (`git diff` confirms it), and `fsd/registry/_core.py` is a
parameterized copy the new image registry builds on — exactly the fallback the guard rail names.
`fsd.image.ImageDefinition` (D1), `fsd.image.digest.resolve`/`digest` (D2 — resolution injectable
for tests, no network in the suite), `fsd.image.registry` (D3, on `_core`), `fsd.aml.environment`
+ `fsd.aml.ensure_environment` (D4, `az` calls behind an injectable seam), `verify_image`'s
`image_ref=`/`registry=` path (D8, spec 47's own tests green and unmodified), the rewritten
`00_build_images.ipynb` (D7, 11 cells vs the old 22) and the deleted
`notebooks/images/{base,sklearn}/` (step 8, rendered-Dockerfile diff confirmed equivalent before
deletion, `DROPPED.md` diff confirmed byte-identical modulo comments/blanks, entry written) are all
done. **Not done: a real AML run** (§9 step 10 — MEMORY `real-run-beats-review`); `main` is merged
but **unpushed**.

**Spec 56 — OPUS REVIEW, 2026-08-27. Eight defects found and fixed in the worktree; suite now
`1053 passed / 98 skipped`.** Verified-as-claimed first: `src/fsd/model/registry.py` is untouched
and the step-0 copy fallback is genuinely forced (`tests/test_registry.py:534` patches
`registry._list_versions` then calls `registry._write_new_version` — a move-and-reexport defeats
it), and the rendered Dockerfiles were re-diffed against `git show main:` rather than eyeballed.
What was wrong:

1. **A rebuild loop, the worst of the seven.** `publish` is idempotent by digest, so rebuilding an
   *unchanged* definition (D4 step 3's deleted asset, or `force=True`) allocated no new version and
   dropped the new AML version on the floor — the registry kept naming the asset that had just been
   replaced, so every later `ensure_environment` found it missing and rebuilt a 10–20 minute image
   again, forever. Reproduced end-to-end before fixing. Fix: **`_aml.json`**, a staged-and-renamed
   mutable sidecar beside the immutable `image.json` — the role `_deploy.json` plays in
   `fsd.model.registry` (spec 51 D7). **This amends D3's layout and wants the user's blessing.**
2. **Two version sequences, silently swappable.** AML versions *assets*, the registry versions
   *definitions* — `fsd-aml-env:5` in AML is routinely `:1` in the registry, and
   `verify_image(image_ref=)` can only resolve the latter. `EnsureResult` now carries
   `registry_version`/`registry_ref` alongside AML's `version`/`ref`; the howto and RECIPES had the
   wrong one and are corrected.
3. **Spec 56 D1's own example raised.** `git ls-remote` matches ref *names*, not object ids (exit 0,
   empty stdout for a sha), so `fsd="git+…@9a00f2b"` died with an empty error message. Abbreviated
   shas (7–40 hex) are now kept verbatim; the not-found error says what it means.
4. **The digest described a different wheel than the image got.** `resolve()` built one wheel in a
   throwaway tmpdir and `write_context()` built a second — two `pip wheel` runs per image, and an
   edit between them makes the registry record a digest the image does not have (§5's *worse*
   direction). One shared directory now, one wheel.
5. **`--no-build-isolation` was a sandbox artifact in library code** — kept as the first attempt
   (it is what keeps the wheel test offline, AC8) with a retry without it for a 3.12+ venv.
6. **Two D8 edges**: a non-GitHub `git+` URL mis-fetched a `raw.githubusercontent.com/https://…`
   404 instead of saying the gate only reads GitHub; the "any non-`git+` ref is trusted" hole is now
   documented as a hole to close before fsd ships on PyPI (#82).
7. **`e2e_austria_aml.ipynb` was left behind and broken** — it pointed `INFER_BUILD_CONTEXT` at the
   deleted `notebooks/images/sklearn/`, and its "paste the versions from Part C" cell contradicted
   D7, `00`'s new Part C and `CHANGES.md`, all three of which claimed the paste was gone. **Edited
   on the user's explicit say-so (2026-08-27):** it now declares the same two `ImageDefinition`s,
   calls `ensure_environment` against the same registry, **asserts `reused`** (a fresh build means
   an ACR run just started and nothing below it can work — a gate the pasted numbers never gave),
   and uses `image_ref=`/`registry=` for `verify_image`.

8. **A test that was green only by import order.** `test_docs.py::test_doc_snippets_use_real_fsd_attributes`
   resolves `fsd.aml.<x>` in a doc as `hasattr(fsd, "aml")` — and a *submodule* is not an attribute
   of its package until something imports it, so the new howto passed the full suite (where
   `tests/test_aml_*.py` had already imported it) and failed `pytest tests/test_docs.py` on its own.
   The test now asks the import system instead of `hasattr`. **Worth remembering as a class:** run a
   new test module, and the modules a change touches, in isolation as well as in the suite.

Still open, both deliberate: **the real AML run** (§9 step 10), which also verifies the one thing
review cannot — `_default_resolve_base_digest`'s HEAD against a live `mcr.microsoft.com` (its
`Accept` header was missing the manifest-list/OCI-index types a multi-arch tag needs; added, still
unverified) — and **AC6's `abfss://` round-trip**, which has no manual-runbook entry yet.

**Also this session:** [#92](https://github.com/nikhilsrajan/fsd/issues/92) filed for the wider
`AZ_ROOT` tidy-up (deferred by the user, a later Opus job). And a standing rule was recorded, in
MEMORY and in #92: **run-books are point-in-time and are not a design input** — the user,
2026-08-27, *"we do not prioritise being able to run the runbooks. we do not make decisions so that
the runbooks are still compatible."* Spec 55 D3's rationale was rewritten to drop exactly that
argument; the surviving reason for reading `AZ_ROOT` from the environment is the notebook leak
guard, which is a real constraint.

**One trap recorded in `RECIPES.md`:** the worktree PYTHONPATH parity recipe **necessarily** fails
`tests/test_bundle_code.py::test_installed_adapter_is_not_embedded` — `bundle._installed_roots()`
reads the *running interpreter's* `site.getsitepackages()`, and a `PYTHONPATH` entry is
deliberately not a site directory, so `joblib` classifies as `bundled`. Verified by running that
test in the repo checkout with the repo venv, where it passes. **Any other failure under that
recipe is real.**

---

_Previously: 2026-08-26 (**SPEC 54 IMPLEMENTED, REVIEWED (Opus `/effort high`) AND MERGED TO
`main`.** Closes #78: `fsd init` + `fsd.config.load()` replace `env.example.sh` /
`notebooks/_config.py`.)_

**What spec 54 built, in one line.** `env.example.sh` (repo root) + `notebooks/_config.py`
(checkout-path `find_repo()`, `env.local.sh` parsing) — both unreachable from a `pip install` — are
replaced by `~/.config/fsd/config.toml` (D1: `$FSD_CONFIG_DIR` > `$XDG_CONFIG_HOME/fsd` >
`~/.config/fsd` on POSIX; `%APPDATA%\fsd` on Windows), written by fsd's first console script
(`fsd init` / `fsd init --from-env-file PATH` / `fsd init --set key=value`, plus `fsd config` to
print resolved values + provenance) and read by an explicit `fsd.config.load()`. `src/fsd/` itself
still never reads config (D3 — the part of spec 41 D7 that survives); precedence is explicit kwarg
> bare `AZ_*` env var > file (D4), and neither `load()` nor `init` ever touches `os.environ`.
Schema: one TOML table `[azure]`, six lowercase keys, written by a ~20-line hand-rolled emitter
(`tomllib` cannot write; `tomli-w` stays the documented escape hatch if the schema ever grows).

**Verified, not just tested green.** AC1 — the criterion #78 exists for — was run for real: built a
wheel (`python -m build`), installed it into a scratch venv with **no fsd checkout anywhere on the
path**, ran `fsd init --from-env-file` and
`python -c "import fsd; print(fsd.config.load().root)"` from an empty directory with no
`pyproject.toml` above it — both succeeded (MEMORY `real-run-beats-review`: green tests alone would
not have caught a `find_repo()`-shaped bug here). Suite **1003 passed, 92 skipped, 0 failed** (skip
count differs from the prior 977/96 baseline because this session additionally installed the
`azure`/`aml`/`mpc`/`titiler`/`serving` extras, unmasking tests previously skipped for missing deps
— not a regression), `ruff check src/ tests/` clean, identifier sweep clean (every hit matches
RECIPES.md's documented known-clean list — `env.example.sh`/`env.local.sh` as fsd's own filenames,
`fsd-aml-env`/`fsd-infer-env`, the `030f6ac` commit sha, `identityReference`/`prevent_destroy` as
generic API terms — no new leak).

Both tracked notebooks (`e2e_austria_aml.ipynb`, `00_build_images.ipynb`) now call
`fsd.config.load()` with lowercase attributes (`cfg.root`, not `cfg.AZ_ROOT`); their checkout-path
resolution is a two-line `pathlib.Path.cwd()` cell per D6, not `find_repo()`. `docs/howto/
run-at-scale.md` + `build-the-images.md` prerequisite lines and `docs/reference/environment.md`'s
"How to use it" section were updated in the same change; `CHANGES.md` / `DROPPED.md` record the
move.

**Review (Opus `/effort high`, 2026-08-26) — approved with five fixes, all applied.** The review
re-ran everything rather than trusting the report: suite, ruff, the identifier sweep, and **AC1
from scratch** (fresh wheel, `pip install --no-deps` into a scratch venv, run from a directory with
no `pyproject.toml` above it — `fsd.__file__` resolved inside the scratch venv, so no checkout was
on the path). D3 was verified by grep, not by claim: only `__init__.py` and `config.py` changed
under `src/`, and no `config.load()` / `config_dir()` / `write_config()` call exists anywhere
outside `config.py` and `cli.py`. What the review changed:

1. **`_toml_escape` missed U+007F (DEL)** — TOML forbids it raw in a basic string, and it sits
   *above* the printable range, so an `ord(ch) < 0x20` guard skips it and writes a `config.toml`
   that `tomllib` then refuses to parse. Fixed; DEL is now in the AC-6 adversarial table.
2. **`docs/howto/build-the-images.md` told the user to fill "AZ_RG and AZ_ML_WORKSPACE at
   minimum"**, which `load()` rejects — it requires all six or raises `MissingConfig`. The line now
   says all six. *Left open (a design question, not a defect):* `00_build_images.ipynb` genuinely
   needs only two of the six, and the retired `_config.load(*names)` allowed a subset. Giving
   `load()` subset support would change spec 54 D7, so it stays unbuilt pending sign-off.
3. **"never reads or writes `os.environ`" was stated twice and was wrong** (`load()`'s docstring,
   a `CHANGES.md` bullet). `load()` *reads* the environment — that is D4 precedence level 2 — and
   never assigns to it. Both now say that, because D4 is the exact thing a later reader must not
   misread.
4. **AC 7b was two-thirds tested** — the `init --from-env-file` write had no environ-mutation
   test. Added.
5. **Interactive `fsd init` — D5's primary form — had no test at all.** Added: prompt order,
   the existing value shown as default, Enter keeping it.

*Not fixed, recorded instead:* D1's `%APPDATA%` branch has no test, because `pathlib.Path()`
consults `os.name` at construction — forcing it to `"nt"` on POSIX makes every `Path(...)` raise
`NotImplementedError`, pytest's own included. A comment in `tests/test_config.py` says so.
*Known small warts, none blocking:* `fsd init --set key=` cannot clear a value (empty is filtered,
so it is a silent no-op); a non-tty `fsd init` dies on a bare `EOFError`; a hand-edited
`root = 12345` passes through as an `int`.

**Post-fix:** suite green, `ruff check src/ tests/` clean, identifier sweep re-run *correctly* —
the first attempt used `xargs -a`, which BSD xargs does not support, so it silently scanned
nothing; redone with `git ls-files -z | xargs -0` it gives seven hits, every one on RECIPES.md's
documented known-clean list.

---

_Previously: 2026-08-26 (**PHASE 2 STARTED. The consumer repo `rise/` exists and installs fsd
from a git URL; the friction it exposed is logged as a finding, and SPEC 54 (`fsd init` +
user-level config, closing #78) is WRITTEN AND SIGNED OFF. Merged into `main` (`--no-ff`),
worktree pruned. NOT PUSHED. NEXT: a Sonnet `/effort medium` session implements spec 54 §9.**)_

**What closed since the last entry.** The user stood up `rise/` — a separate git repo at the
workspace root with a `.venv`, a one-line `requirements.txt` (`git+https://github.com/nikhilsrajan/fsd`)
and a blank `notebooks/e2e_austria_aml.ipynb` — and asked what a stranger would actually have to do
to rebuild that notebook. That is phase 2's premise being exercised rather than described, and it
produced two artifacts.

**`docs/findings/consumer-repo-friction.md`** — eight friction points, four of them hard stops,
measured by read-only inspection (`pip show`/`pip list` in `rise/.venv`, the installed wheel
`RECORD`, `git ls-files` + `git check-ignore -v`, the notebook JSON). No cluster time. **It is an
OPEN LOG, not a point-in-time measurement** — the exception to the rule the other two findings
follow, because this friction *is* phase 2's deliverable, and the findings index says so. The four
hard stops: `env.example.sh` is not in the wheel and no install-facing doc names it; `_config.py`
raises at **import** outside a checkout; `notebooks/shapefiles/*.geojson` is caught by the blanket
`*.geojson` rule so the training data is on **nobody's** GitHub; and the extras set is
undiscoverable, with `README.md`, `docs/howto/run-at-scale.md` and the notebook's own init cell
giving **three different answers**, all in the `pip install -e ".[…]"` checkout-only form no
consumer can use.

Three things it also records, to stop them being re-derived: the **wheel is already code-only**
(`packages.find where=["src"]`; the RECORD is `fsd/**` + dist-info), so "ship less" is a
*dependency* problem (#80/#81), not a files problem; **~420 MB is the floor**; and the Azure
prerequisites are **not fsd's to fix** — a stranger genuinely cannot run this notebook, and the
runnable stranger path is `docs/tutorial.md`. Do not confuse *hard because Azure* with *hard
because fsd*.

**`specs/54-user-level-config.md`** — **SIGNED OFF 2026-08-26, not implemented.** Replaces
`env.example.sh` + `notebooks/_config.py` with `~/.config/fsd/config.toml`, written by a new
`fsd init` console script (fsd's first `[project.scripts]` entry) and read by an explicit
`fsd.config.load()`. Seven decisions, cross-validated against five primary sources with per-source
credit. The load-bearing one is **D3: the library still never reads config on its own** — the verbs
keep taking every storage location as an argument. That is spec 41 D7's *real* invariant surviving
while its **bootstrap** (a template at a repo root, a loader in `notebooks/`) is overturned; a
library that resolves its own storage root from ambient state behaves differently on every machine,
and every fan-out node would inherit whatever the driver's `$HOME` held.

Also decided there, so it is not relitigated: a tool-specific `FSD_CONFIG_DIR` **ahead of** XDG
(D1) — the cross-validation **amends #78**, which implied `~/.config` is the shared convention;
`az` actually uses `~/.azure` with `$AZURE_CONFIG_DIR` and gcloud `~/.config/gcloud` with
`$CLOUDSDK_CONFIG`, so the shared convention is *a user-level dir plus a tool-specific override*,
and that is also the evidence for rejecting `platformdirs` (its macOS answer matches neither).
Stdlib `tomllib` to read, **fsd's own emitter to write** — `tomllib` "does not support writing
TOML", and taking `tomli-w` for six flat strings runs against #80 (D2, with the escape hatch named).
Precedence **arg > env > file** with the bare `AZ_*` names kept, adopted from the Azure CLI's own
documented order, so `source env.local.sh` and every run-book keep working (D4). And **the
environment is read, never written** (D4, AC 7b) — `load()` never assigns to `os.environ`; the one
existing write in `src/fsd/` (`storage/azure.py:114`, `FSSPEC_ABFSS_ANON`) is named there with why
it does not generalise, because it is the precedent someone will cite.

**Q1 resolved at its recommendation:** `[azure]` + lowercase keys, read as `cfg.root`.

---

## NEXT: implement spec 54 — Sonnet `/effort medium`

**Spec 54 §9 is the build order** and it is written for this session: seven steps, each
independently testable, do not start one until the last is green. Start at step 1
(`src/fsd/config.py`), not at the CLI. Two things §9 says explicitly and are worth repeating
because they are the easy mistakes:

- **Do not touch `fsd.download` / `create_training_data` / `run_inference`.** D3 is the point of the
  spec; a signature change there is out of scope.
- **No test may reach the developer's real `~/.config/fsd`.** `monkeypatch.setenv("FSD_CONFIG_DIR",
  str(tmp_path))` in a fixture used by every test that touches disk (AC 8, spec 37 §7's rule).

**Then #80, then the tag.** The order from the last entry stands, with one change the user made on
2026-08-26: **the `v0.1.0` tag is cut AFTER the first consumer notebook works**, not before — a tag
pins the dependency set *and* the asset layout, and both are still moving. #80's extras split and
the shapefiles un-ignore should land **inside** `v0.1.0` rather than force a `v0.2.0` plus an edit
in every consumer.

1. **#80** (snakemake -> `[local]`, s3fs -> `[s3]`) — zero code change, **-53 packages / -111 MB**
   (689 -> 578 MB core closure). Both are declared core and **never imported** by `src/fsd/`.
2. **The `notebooks/shapefiles/` un-ignore** — not yet an issue, described in the finding's P3. The
   user's rule: the test geometries **must exist on GitHub** and **must not travel in a package
   install**, which are not in tension (git tracking and wheel contents are set by different
   mechanisms). **The precedent is already in-repo:** `.gitignore:32-38` un-ignores
   `tests/data/tutorial/` with `!dir/` **then** `!dir/**` and it carries a `NOTICE`. Copy that,
   NOTICE included — the Austria fields are EuroCrops-derived, and `CLAUDE.md` already claims a
   NOTICE exists there when it does not.
3. **#82 — cut and push `v0.1.0`** once the consumer notebook runs. Its stated blocker (unpushed
   commits) was already gone on 2026-08-26.
4. **#79 (`fsd.aml.ensure_environment()`)** — wanted, not blocking; paste image versions by hand as
   the notebook does today. Its scope call is still open and is written up in the finding's P7:
   **does the consumer repo build its own images, or consume admin-built ones?** That decides
   whether #79 is inside phase 2 or after it. Note `notebooks/images/*/fsd-*.whl` is gitignored, so
   a consumer cannot reproduce a build context today.
5. **#81 (numba -> `[accel]`, -160 MB)** — **do not block on it.** Not free: numba is a top-level
   import in `bands/modify.py` and `datacube/ops.py`, both reachable from `import fsd`. Needs a
   benchmark first. The floor is ~420 MB regardless — **"tiny" is not achievable; say so.**

**Deferred, recorded so it is not lost:** **`rise init`** (user, 2026-08-26) — a *project*-level
scaffold one layer above `fsd init`, standing up a consumer repo with its requirements, a starter
notebook and the config call wired. It belongs to `rise`, not fsd, and should be designed against a
consumer notebook that already exists. `fsd init` must not grow scaffolding options in anticipation.

**Two constraints the new repo still inherits.** Nothing private may reach it; and its demo notebook
needs its **own copy** of `tests/test_notebooks.py`'s guard (no saved outputs, no execution counts,
six identifier patterns) or it inherits the leak risk without the check.

**Housekeeping noticed, not done:** `specs/README.md`'s table stops at **spec 47** — 48-54 are all
missing. Its own convention note says regenerate the rows from `CHANGES.md`/`docs/adr/`/tests rather
than hand-patch a stale one, so it wants a pass, not a one-line append.

**Still open, unrelated to Phase 2:** #91 and #90 as one seam-gate spec (both are
`_check_local_seams` inspecting which kwargs were spelled rather than what the call will touch);
**#87 is waiting on evidence from the completed run** — either the single `_deploy.json` binding is
fine in practice (close won't-fix) or a concrete case where a mismatch warning was wanted.

---

_Previously: 2026-08-26 (**SPEC 53 DONE AND PUSHED; the e2e notebook is now TRACKED, guarded and
proven end to end on real Azure. `main` == `origin/main`.**) Spec 53 landed (#89 closed with
real-run evidence; review finding filed as #91). The user then ran `notebooks/e2e_austria_aml.ipynb`
**to completion** against the real cluster with the registry on **blob** — the first end-to-end run
of create_training_data -> train -> deploy -> run_inference where the model is resolved by NAME from
an `abfss://` registry, and the evidence specs 52 and 53 both said only a real run could give.

The notebook was un-ignored without being added to `tests/test_notebooks.py`'s `TRACKED_NOTEBOOKS`
— the mechanism that makes the `00_build_images.ipynb` exception safe — so it went public unguarded,
clean only because outputs had been cleared by hand. It now carries all six identifier patterns and
both structural rules, mutation-checked: injecting a storage account URL plus one `execution_count`
fails exactly three tests, each naming the leak class. Suite **977 passed, 96 skipped**, ruff clean,
identifier sweep clean.

Notebook content was also brought in line with the verbs as they now are: the
**1 create training data -> 2 create features -> 3 train -> 4 deploy -> 5 run inference** flow is
stated up front, section 3 documents deploy as **five gates**, `REGISTRY` moved to
`f"{cfg.AZ_ROOT}/model_registry"` (blob, hung off `AZ_ROOT` not `ROOT`, since models outlive runs),
and four stale "the registry must be local / will hang" claims were removed. One check was added
that fsd cannot do for the user: an assert that the training `SEQ` and the adapter's
`feature_sequence` are identical — they are written out twice in two files, nothing in fsd compares
them, and a drift produces confident nonsense with no error at bundling, at `verify_adapter`, or at
inference._

_Previously: 2026-08-25 (**SPEC 53 (D1+D2, #89) IMPLEMENTED + REVIEWED (Opus `/effort high`) +
MERGED into `main` (`--no-ff`, `main` @ `38a2d09`), worktree pruned, branch deleted. NOT PUSHED.**
All eight ACs verified, one review fix applied. On `main` the suite is **968 passed, 96 skipped, 0
failed** (4 more tests collected than in the worktree — the gitignored real-data fixtures under
`tests/outputs/` live in the main checkout only, not a behavior difference), `ruff` clean.

`api._stage_local_bundle` (new) fetches a non-local resolved bundle to
`<output_folderpath>/_model` via `infer_shard.fetch_bundle_to_scratch`, and is called from two
sites: unconditionally in `run_inference`'s pre-built-cubes path (right after that path's own
`_raise_preflight`, since `cores=1` and the `cores>1` Snakemake fan-out are both always-local —
`runner=` never reaches that branch) and, gated on `runner == "local"` per D1's amendment, in
`_run_inference_roi` (right after its own `_raise_preflight`, before `_ensure_bundle`). Both sites
sit after preflight, not literally next to `_resolve_model_ref`, so `_model_spec`'s earlier read
(which uses `fs.open` and needs no local copy) still costs nothing on a rejected call (AC4).
Because staging lands before `_ensure_bundle`'s own (idempotent) resolve call, `_ensure_bundle`
just passes the already-local path through — AC6 (`cores>1`) falls out for free, as the spec said
it would.

9 tests in `tests/test_local_bundle_staging.py` — 8 cover AC1–AC7 (AC8 is the existing suite +
ruff, already green); each was mutation-checked (call site commented out -> the assertion that
covers it fails) rather than trusted on green alone (MEMORY `real-run-beats-review`). One thing
the tests do NOT reproduce: #89's actual `ModuleNotFoundError`. The adapter class used in the test
lives in the test module itself, which is already in `sys.modules` by the time `bundle.load` runs
in-process, so `importlib.import_module` finds the cached module regardless of `sys.path` — the
crash itself needs a genuinely fresh interpreter, which is what the run-book's real-Azure repro
gives and unit tests cannot. The tests instead assert the mechanism directly: call counts, the
staged path, and which call sites see it — AC1–AC7 as written.

**Opus review, 2026-08-25 — verdict: clean, with one fix applied.** All eight ACs were
re-verified against the diff (AC1/AC2/AC5/AC6 by reading the code path, AC3/AC4/AC7 by the tests'
zero-call assertions, AC8 by re-running the suite here). Two findings:

1. **FIXED — the driver-side fetch was completely silent.** Confirmed by capturing stdout on a real
   `memory://`-registry run: the output went `[model] probe@champion -> v1` straight to
   `[inference] 1/1 -> ...`, with nothing in between. D2's rationale for accepting a per-run
   re-fetch rests on "spec 47 D5 already prints the transfer with a size and a ticker, so it is
   never silent" — but D5 instrumented `runners._stage_bundle` (the **upload** leg), and
   `fetch_bundle_to_scratch` prints nothing. `_stage_local_bundle` now prints
   `[stage] bundle <- <url> | N files, X MB` before the transfer, mirroring `_stage_bundle`'s D5
   shape (one extra `bundle.json` read + one `fs.size` per file, the cost `_stage_bundle` already
   accepts). A 9th test asserts the line exists, names the source, carries a size, and lands
   **before** the first `[inference]` line. Not given a per-file ticker: that would mean editing
   `fetch_bundle_to_scratch`, which the AML node path shares, and AC7 says that path is untouched.
2. **NOT FIXED, needs an issue — a non-local `output_folderpath` now creates a junk directory.**
   The seam gate (`_check_local_seams`) inspects the `storage=` kwarg, never the URL, so
   `run_inference(model=<blob ref>, output_folderpath="abfss://...", ...)` reaches
   `_stage_local_bundle`, which hands a URL to `fetch_bundle_to_scratch` — whose `os.makedirs` and
   bare `open` are local-only. Probed with `memory://outblob`: it created a literal `memory:`
   directory in the process's CWD and then raised `FileNotFoundError /outblob/_model/bundle.json`.
   That combination was already broken before this change (`bundle.load` would have failed on the
   URL anyway), so this is not a regression — but the failure is now messier and leaves litter.
   Left alone deliberately: the right fix is a design call (reject early in preflight vs. stage to
   a real temp dir), which is spec territory, not review territory.

**Full suite re-run under review: 965 passed, 94 skipped, 0 failed → 966 passed with the review
test added; `ruff check src/ tests/ demos/ examples/` clean** (baseline before this work: 956
passed, 93 skipped).

⚠️ **Working-copy note for whoever picks this up:** the editable install in `fsd/.venv` resolves to
the **main checkout's** `src/`, not a worktree's — running `pytest`/`ruff` from inside
`.claude/worktrees/spec53-phase0/` against `../../../.venv/bin/python` silently ran the MAIN
checkout's code for a while during this session (masked by `sys.modules` caching happening to make
the tests pass anyway) until caught by a suspicious zero-call assertion. Fix: prefix commands with
`PYTHONPATH="$(pwd)/src"` from inside the worktree, or give the worktree its own venv.

**VERIFIED ON REAL AZURE, same day.** The user re-ran `runbooks/52-registry-on-blob.md` step 4
against the real `abfss://` registry **with no manual workaround** — the exact call that raised
`ModuleNotFoundError` before — and it passed: `{"step": "52-4-run-inference", "pass": true,
"published_version": 1, "n_outputs": 1, "error": null}`. That is the proof spec 53 §9 said unit
tests structurally could not give (the crash needs a fresh interpreter; the test module is already
in `sys.modules`). **Spec 53 is DONE and #89 is closable.** The run-book was updated to match:
step 4's result row now reads PASS-unaided, the obsolete fetch-to-scratch workaround block is gone
(git history at `9ab5202` if an old checkout needs it), and the prerequisites no longer warn that
the step cannot pass.

**LANDED AND PUSHED (2026-08-25).** `main` @ `5fe9b86` pushed to `origin` (`9ab5202..5fe9b86`,
fast-forward, 5 commits) after a clean private-identifier sweep — all 7 hits were the documented
known-clean false positives (`RECIPES.md`'s list: `030f6ac`, `env.example.sh`, `env.local.sh`,
`fsd-aml-env`, `fsd-infer-env`, `identityReference`, `prevent_destroy`). **#89 CLOSED** with the fix
summary and the real-run evidence. Review finding 2 filed as
**[#91](https://github.com/nikhilsrajan/fsd/issues/91)** — a non-local `output_folderpath` reaches
`_stage_local_bundle`, which is local-only, so it creates a scheme-named junk directory in the CWD
and then raises a `FileNotFoundError` naming a path the caller never passed. Not a regression (the
combination was already broken pre-spec-53) and low severity, but the right fix contradicts D2's
fixed scratch location, so it is spec territory. **Filed as a sibling of #90: both are
`_check_local_seams` inspecting which kwargs were spelled rather than what the call will touch —
worth one spec over the gate, not two patches.**

**NEXT:** open. Spec 53 is finished end to end (signed off → implemented → reviewed → merged →
pushed → verified on real Azure → #89 closed). The obvious candidates are #90+#91 as one seam-gate
spec, or the next item on the notebook-usability sprint (MEMORY `fsd-notebook-usability-sprint`). Then the *user* re-runs `runbooks/52-registry-on-blob.md` step 4 **without** the manual
workaround against the real `abfss://` registry — the only thing that proves #89 closed; Claude
never runs it.

_Previously: 2026-08-25 (**SPEC 52 MERGED into `main` (`--no-ff`, `main` @ `f2fe6bf`), worktree
pruned, branch deleted. NOT PUSHED. The run-book was then executed against a REAL `abfss://`
registry by the user — steps 1-3 PASS, step 4 FAILS, and it found two defects that 956 green
tests, two Opus review rounds and a mutation pass all missed (MEMORY `real-run-beats-review`).**

**Run-book results (real Azure, 2026-08-25).** Step 1: v1 published in **32.9 s** — #88 is
genuinely dead against Azure, not just `memory://`. Step 2: v2 published on changed content
(digests differ). Step 3: `set_alias` repointed `champion` -> v1. **Step 4: FAILED as written, workaround
PASSED** — the ref resolved (`[model] crop-rf-t10@champion -> v1`, against live blob, which is
AC8's substance) and then died in `bundle.load`; inference ran once the bundle was fetched to
scratch. **Step 5: PASS** — re-publishing v1's exact content returned v1 and wrote nothing
(`n_entries` 3 -> 3). **Verdict: spec 52's publish protocol is proven on real Azure** (in-place
publish, marker, alias repoint, digest idempotency); **#88 is closeable**; **#86 is not proven**.

**Two new issues, both filed, both with a drafted fix:**
- **[#89](https://github.com/nikhilsrajan/fsd/issues/89) — a blob-resolved ref cannot be loaded on
  the local run path.** `bundle.load` requires a local directory (its own docstring says so) and
  `_activate_bundle_code` does `sys.path.insert(0, "<bundle>/code")`; with a blob ref that entry is
  an `abfss://` URL, and CPython ships only `zipimporter` + `FileFinder` path hooks, so it is inert
  (verified by execution). The AML path stages first and is fine; the local path never stages.
  **A blob registry works for AML runs and is broken for local runs.** Pre-existing, but only
  reachable once spec 52 made a blob registry possible.
- **[#90](https://github.com/nikhilsrajan/fsd/issues/90) — `storage=` and `registry=` are
  conflated in `run_inference`'s seam gate**, so spec 52 D4's `configure_storage` fix is
  unreachable on the pre-built-cubes path (`storage="azure"` is refused there). **#86 is therefore
  UNPROVEN, not fixed** — step 4 is the run-book's only step that goes through a verb at all.
  Related finding: adlfs's `anon` default is `None`, not `True`, so steps 1-3 authenticated
  against real Azure with **no** `configure_storage` call anywhere — #86's stated failure mode may
  not occur under a developer `az login` at all. Recorded as spec 53 §5's first risk.

**[`specs/53-blob-registry-on-the-local-run-path.md`](specs/53-blob-registry-on-the-local-run-path.md)
— SIGNED OFF (user, 2026-08-25) at both proposed defaults. Rescoped to #89 alone before
sign-off.** D1: stage a non-local resolved
bundle to scratch in `run_inference`, right after `_resolve_model_ref`, reusing
`infer_shard.fetch_bundle_to_scratch` (the primitive already exists — the spec wires, it does not
write transfer code). D2: scratch at `<output_folderpath>/_model/`, per run, not a cache. **D1 was amended after
sign-off (2026-08-25) with a runner gate:** as first written it staged whenever the resolved path
was non-local, with no runner condition, which contradicted AC7 — a blob registry plus
`runner="aml"` would have added a blob→local fetch that then got staged straight back to blob.
Staging is now gated on `runner == "local"` (the shapes that actually call `bundle.load` on this
machine), with `fs.is_local` as the locality test; AC7 asserts zero driver-side fetches on the AML
path by call count. **§7's two questions
resolved at their defaults:** staging goes in `run_inference` (so `bundle.load` keeps the narrow
spec-44-D2 contract — no network I/O, no temp dir of its own; the accepted cost is that a future
caller handing `load` a URL hits #89 again, with §6 option B kept as the way back), and scratch
stays per-run rather than a digest-keyed cache (cheap to add later — the digest is already in
`_complete.json`).

**#90 was dropped from spec 53 and downgraded to a tidy-up** (assessment recorded as a comment on
the issue). The reason: **`configure_storage` does not authenticate** — its whole body sets
`FSSPEC_ABFSS_ANON=false` plus the matching `fsspec.config` key, which forbids the *anonymous
fallback* rather than supplying a credential. Credentials come from the `az login` chain either
way, which is exactly why steps 1/2/3/5 worked without it. So #90's entire cost today is a
confusing refusal when a caller passes a kwarg they never needed; the workaround is to omit it.
**Caveat kept visible: while that gate stands, #86 is permanently unprovable**, since the
run-book's only verb-level step cannot exercise D4 — a bookkeeping cost, not a functional one, and
the one argument for fixing #90 sooner.

**#88 CLOSED** (2026-08-25) with the real-Azure evidence. **The #86 claim was corrected** in
`CHANGES.md` (a "Correction, 2026-08-25" block) and in spec 52's header + §10.5 — the merge commit
`f2fe6bf` and `82eda21` both say #86 is closed, which is wrong and cannot be edited after the fact,
so those notes are the correction of record.

**`runbooks/52-registry-on-blob.md` was corrected as the run proceeded** (step 2 had no command at
all and referenced an env var nothing produced; step 4 had three separate faults: `storage="azure"`
which the gate refuses, a model/cube `n_timestamps` mismatch, and folder-mode cube discovery that
needs per-cube subfolders). It now carries the #89 workaround so step 4 is completable today. All
7 Python blocks parse; no undeclared env vars.

**NEXT: implement spec 53's single phase (D1+D2, #89) in a Sonnet session at `/effort medium`**
against the signed-off spec, then hand back to Opus `/effort high` for review. Then re-run run-book step 4 **without** the manual workaround to prove it.
Also still pending: the push of `main` (at `f2fe6bf`, plus the uncommitted doc/spec work).

_Previously: 2026-08-24 (**SPEC 52 IMPLEMENTED (Sonnet `/effort medium`) and REVIEWED by Opus
`/effort high` — four findings, all fixed in-branch; see the "Opus review" block below and spec 52
§10.** Work is on worktree branch `worktree-spec52-registry-on-blob` (at `fsd/.claude/worktrees/`),
based on `main` @ `7c3811c`.

**Step 0 (registry core, D1/D2/D3/D5) — `fsd/model/registry.py`.** `_write_new_version` writes a
version's files straight into `v<N>/` (no staging prefix, no directory rename), re-digests what
landed, and writes `v<N>/_complete.json` last. `_list_versions` is now marker-aware, with a legacy
carve-out (`bundle.json` present, no marker) for pre-spec content. The retry loop is bounded at
`_MAX_PUBLISH_ATTEMPTS = 16` and retries only a genuine version collision.

**A real D5-vs-AC2 conflict surfaced during implementation, not guessed around** (MEMORY
`verify-the-primitive-a-spec-cites`-flavored: check it, don't code around it). D5's legacy rule
(`bundle.json` present + no marker ⇒ complete) and AC2 (an interrupted publish must be invisible to
`_list_versions`) contradict whenever `bundle.json` lands before the interruption — confirmed with
a failing test, since `bundle.json` sorts alphabetically early among a bundle's files. Flagged to
the Opus session; **adjudicated same-day, spec amended** (see spec 52 §3 D5's "Amendment" block and
AC2's rewritten text): `_write_new_version` now writes `bundle.json` **last** among the content
files, so an interruption during the write (where nearly all the risk is) leaves no manifest and
is genuinely reusable; the one-object-write residual window (after the manifest, before the
marker) is left to the legacy reading, on the reasoning that misreading real legacy content as
incomplete can destroy a published version, while misreading a rare interrupted version as
complete only strands a folder (a cost §5 already accepts). Same review pass found `migrate`
never wrote `_complete.json` at all — fixed (new AC5a), so migrated content no longer depends on
the legacy carve-out to be visible.

**Step 1 (verb wiring, D4) — `fsd/api.py` + `fsd/model/verify_image.py`.** `deploy` drops
`storage_allowed=False` (accepts `storage="azure"` now). `deploy`, `run_inference`,
`verify_adapter` each call `configure_storage(storage)` right after preflight's cheap validation
starts, before the first storage touch (`_resolve_model_ref`/`fs.read_geo`/`_bundle.read_spec`).
`verify_image` gained a `storage=` kwarg it never had (#86 — it previously could not authenticate
at all) plus the same call, placed after its own cheap arg checks.

**Step 2 (end-to-end, AC8) — spec 51's AC12 unblocked.** `test_registry.py`'s skipped
`test_publish_resolve_round_trip_against_a_url_registry` is unskipped (D1 removed the hang it was
blocked on). Added `test_deploy.py::test_deploy_set_alias_resolve_run_inference_against_a_url_registry`
for the fuller chain AC8 actually names (`deploy` → `set_alias` → `resolve` → `run_inference`), and
a dedicated timeout-asserted test for AC1's literal wording (a background thread + `join(timeout=10)`,
no new test dependency).

**Opus review, 2026-08-24 — four findings, all fixed in-branch. The D5/AC2 amendment itself was
re-derived independently and STANDS** (the handoff was right to ask for that; the one correction to
it, #4 below, does not change its conclusion). Full account: spec 52 §10.
(1) **`run_inference`/`verify_adapter` turned a preflight error into a bare `ValueError`.** D4's
`configure_storage` call genuinely had to precede `_raise_preflight` — but `configure_storage`
*raises* on an unsupported backend, so `storage="s3"` escaped as `ValueError` and discarded every
other accumulated preflight error. And the side effect the handoff reasoned was absent is real: a
call the seam *rejects* (`run_inference(storage="azure")` on the pre-built-cubes path) still flipped
the process to authenticated adlfs first — the exact accident D4 exists to remove. The seam check
now raises on its own first, matching `deploy`. (2) **Publishing into an incomplete version
inherited the previous attempt's leftovers.** AC2 reuses an unmarked `v<N>` in place, and
`content_digest` covers only *manifest-declared* files, so an undeclared artifact or `code/*.py`
survived into the version and was then marked complete — and `bundle.load` puts `code/` on
`sys.path`, so a stale module there is importable by the next adapter. `_write_new_version` now
`_discard`s an incomplete target before writing; stage-then-rename got a clean directory for free.
(3) **Four branches were unpinned — mutation testing found them, reading did not.** Deleting the
idempotent-collision `return`, disabling the landed-digest guard, and replacing D5's legacy check
with `return False` each left the suite green; the two rewritten "race" tests cannot reach
`_write_new_version`'s collision branch at all (their competitor publishes *before* `_list_versions`
runs). So the narrowing flagged at handoff did lose AC4's substance and left **AC5 with no test at
all**. Five tests added, each verified to kill its mutation. (4) **The residual window is not "one
object write wide"** — `content_digest(target)` re-reads the whole bundle inside it. Conclusion
unaffected and actually stronger: everything in that window is post-write, so a version stranded
there holds complete content; it is unverified, not partial.
Suite **956 passed / 93 skipped**, ruff clean.

**Run-book written, not run** (Claude never runs pipeline/networked scripts): `runbooks/52-registry-on-blob.md`
— publish v1/v2 to a real `abfss://` registry, repoint an alias, run inference off the ref,
confirm a re-publish of identical content is a no-op. Green tests do not finish this spec (MEMORY
`real-run-beats-review`) — this is the part they cannot cover.

**NEXT:** hand back to Opus `/effort high` for review (spec, tests, and the D5/AC2 amendment
itself), then the user runs the run-book and pastes back its five printed results.

**⚠️ `main` has an uncommitted `PROGRESS.md` edit that is now WRONG** — it records the blob registry
as "a documented LIMITATION, not scheduled work", which the user reversed the same day. Discard it
(`git checkout PROGRESS.md` on `main`) before merging this branch. `main` also carries an
uncommitted one-character docstring change in `src/fsd/model/adapter.py` (an en-dash became a
hyphen) that Claude did not make._

_Previously: 2026-08-24 (**spec 51 §9 step 3 (the `[model]` print line, D7/AC10's print half) —
IMPLEMENTED (Sonnet `/effort medium`) and REVIEWED by Opus `/effort high`: three findings, all
fixed in-branch — see CHANGES.md's "Opus review" block.** Work is on worktree branch
`spec51-step3-model-line`, based on `main` @ `88e8f11` (steps 0-2 merged + pushed). This is the
**last step of spec 51 §9** — after Opus review + merge, the spec is implemented apart from the
two §7 AC gaps below (one done here, one blocked and issued).
**What shipped:** `api._resolve_model_ref` now prints `[model] <ref> -> v<N> (verified against
<env>)` (or the shorter `[model] <ref> -> v<N>` with no `_deploy.json`/`environment`) the moment a
ref actually resolves — inside the one branch where `registry_mod.resolve` succeeds, so it fires
exactly once per `run_inference`/`verify_adapter` call even though both can call
`_resolve_model_ref` twice. `registry.read_deploy_record` (new, public) backs it and
`_read_deploy_digest`; never raises — a missing/malformed `_deploy.json` degrades to the shorter
line. Full detail: `CHANGES.md`'s top entry.
**Deliberately deferred (recorded in the spec, not silent):** D7's environment-mismatch warning
(§7 Q2) — `_deploy.json`'s `environment` is last-writer-wins, so it would warn falsely against any
image but the most recently verified one. Ship the print only; decide the warning from real
notebook use. **[Issue #87](https://github.com/nikhilsrajan/fsd/issues/87).**
**Secondary scope (§7's two AC gaps):** AC14's second half done —
`test_deploy_refuses_verify_adapters_real_auto_saved_bundle` runs the real `verify_adapter` path
and feeds its actual `metrics["bundle_path"]` to `deploy`, asserting the `requirements` refusal.
**AC12 (URL registry) blocked, not done** — writing it surfaced a real, separate bug:
`registry._write_new_version`'s retry loop hangs forever publishing to any non-local fsspec
backend (confirmed `memory://`), because `storage.fs.rename`'s directory move fails `ENOTEMPTY` on
`MemoryFileSystem` and every retry hits the identical (non-transient) failure. Not fixed here —
out of this step's scope, a storage/registry design question. **[Issue #88](https://github.com/nikhilsrajan/fsd/issues/88).**
The AC12 test is now present but **`@pytest.mark.skip`ped** (Opus review) so the gap stays visible
in `pytest -q`'s skip line instead of being absent from the suite.
Suite **936 passed / 91 skipped / 1 pre-existing failure** (`planetary_computer` absent), ruff
clean.
**Opus review found three (the pattern held for a fourth step running):** (1)
`read_deploy_record` raised `UnicodeDecodeError` on a byte-corrupt `_deploy.json`, breaking its own
never-raise contract — catch widened to `(ValueError, OSError)`; (2) the once-per-call test was
**vacuous** — an empty `inference_datacubes` folder dies at `_raise_preflight` before
`_ensure_bundle` is ever reached, so it asserted "printed once" with only one of the two call sites
executed; rewritten to drive a real datacube at `cores=2` and assert the second call site ran;
(3) `registry.__all__` was missing `read_deploy_record`. Both behavioral fixes are mutation-checked.
Independently verified during review: no runner or node resolves refs (`src/fsd/workflows/` contains
zero `registry` references — nodes receive a staged bundle path), so D9's "once, on the driver"
claim holds; and issue #88's hang reproduces (`_write_new_version` on `memory://` still looping
after 10s).
**Committed + merged `--no-ff` into `main` (`main` @ `002c85e`), worktree pruned, branch deleted.
NOT PUSHED — `main` is 2 commits ahead of `origin/main`, awaiting the user's push.**
**NEXT after the push: update `notebooks/e2e_austria_aml.ipynb`** to use the registry verbs
(`fsd.deploy` + a `name@alias` ref through `run_inference`), then the user runs it and reports on
usability._

_Previously: 2026-08-22 (**spec 51 §9 step 2 (`fsd.deploy`) REVIEWED by Opus `/effort high` —
one real defect found, reproduced and fixed; MERGED into `main` (`--no-ff`, `main` @ `37124c5`)
and both per-spec worktrees pruned. NOT PUSHED — `main` is 3 commits ahead of `origin/main`,
awaiting the user's go.**
**The defect (D5's whole guarantee, silently void):** `deploy(verified=...)` matched a prior
verification by re-digesting the result's own `metrics["bundle_path"]` **at deploy time**, but
`verify_image` recorded no digest of what it had verified. Since `bundle.save` overwrites in place
(spec 51 §1 H1), the normal verify → retrain → re-save → deploy loop hands `deploy` a
`_result.json` naming the *right path* holding the *wrong content* — and re-digesting that path
compares the new content **with itself**, a tautology that always passes. `_deploy.json` then
recorded "this image ran this bundle" for content the image never saw, which is exactly what D5
exists to prevent. Reproduced before fixing.
**Fix (AC8 taken literally — "the result's *bundle digest*"):** `verify_image` now records
`metrics["bundle_digest"]` at verification time (additive to its `_result.json`; the only change
made to that module), and `_verified_matches` compares that recorded digest, never the path. A
result carrying no `bundle_digest` is refused as a mismatch — it cannot say what it verified, so
**every `_result.json` produced before today must be re-run**. Side benefit: a `_result.json` is
now portable between machines. Pinned by
`test_deploy_refuses_a_verified_result_whose_bundle_was_overwritten_in_place` +
`..._records_no_bundle_digest`, plus a producer-side assertion in `test_bundle_transparency.py`.
**Two smaller review fixes:** (a) `registry.check_name`, called by `publish` and up front by
`deploy`, refuses a model name carrying `/`, `\`, `:`, `@`, a leading `.`, or nothing — such a name
published fine and returned a ref nothing could resolve (`crop/rf:1` reads as a *path* to
`api._is_ref_shaped`; `crop:rf:1` re-splits at the wrong separator), breaking AC1; checked before
verification so a bad name costs no AML node. (b) `deploy(verified=<missing path>)` now raises the
verb's `PreflightError` instead of a bare `FileNotFoundError`. (c) the `pass=False` refusal falls
back to `metrics["smoke_error"]` when `verify_image`'s top-level `error` is `None` (it is populated
only for *driver*-detected failures), so a failed smoke job no longer refuses with the useless
literal "verify_image error: None" — the implementer flagged this in the handoff as an open
question; D5's "the verification's own error" is better served by the actual diagnosis.
**Reviewed and accepted as-is:** the ordering that guarantees AC7's "no version directory on
refusal"; the `_verified_matches`-drops-the-`pass`-check call the implementer made (correct — `pass`
is judged separately, so a matched-but-failing result surfaces its own `error`); the
`publish`-reads-`_deploy.json`-first optimization and its monkeypatch test (which does prove what it
claims — `publish` digests the *source* bundle via `_digest_of`, not the patched `content_digest`);
`migrate` carrying `_deploy.json` across (an out-of-scope addition, but the right call: D11's "a
move is a copy" would otherwise lose every binding record); the AC13a scan (`_deploy.json`'s
embedded `verified.metrics.bundle_path` is D11-sanctioned *evidence*, not a reference, and deploy no
longer reads it at all); and the removal of `test_deploy_is_stub`.
**One design question left open, not filed as an issue yet (user's call):** re-deploying identical
content **overwrites** that version's `_deploy.json` (new `deployed_at`, and a different
`environment=` replaces the recorded binding), which sits against D2's "identical content → returns
it, **writes nothing**". Arguably desirable (the version is now known to run the newer image) but it
silently drops the older binding; the spec is silent. Also unaddressed, cosmetic: `deploy` digests
the bundle twice (once itself, once inside `publish`).
Suite **927 passed / 91 skipped / 1 pre-existing failure** (`planetary_computer` absent), ruff clean.
**NEXT: user's go to merge + prune, then step 3** (the `[model] name@ref -> vN (verified against
<env>)` line + the environment-mismatch warning, D7/AC10's print half). Previous entry: step 2's
implementation session, below.)_

_Previously: 2026-08-22 (**spec 51 §9 step 2 (`fsd.deploy`, D5/D6/D7) implemented — Sonnet
`/effort medium`.** Work is on worktree branch
`worktree-spec51-step2-deploy`, based on `main` @ `6b3fcae` (steps 0-1 merged + pushed). `deploy`
now: refuses a live adapter (naming `fsd.model.bundle.save`, D6) and a bundle whose manifest lacks
`requirements`/`code` (naming the fix); establishes the bundle↔image pairing before recording it,
either by running `fsd.model.verify_image` itself or by accepting a prior `verified=<_result.json
path or dict>` **only if** its own recorded `metrics["bundle_path"]` — re-digested now — and
`metrics["environment"]` both match this call (a `pass=False` result that DOES match is still
honoured and refused with its own `error`; one that does NOT match is refused as "stale or does not
match", never silently re-verified, D5); on `pass=True` calls `registry.publish` (idempotent, D2)
and writes `_deploy.json` beside `bundle.json` (`name`/`version`/`digest`/`environment`/`verified`/
`deployed_at`/`fsd_version`, D7) via a new `registry.write_deploy_record` (staged + renamed, like
`set_alias`). Two follow-on fixes to `registry.py` made as part of this step: `publish`'s own
idempotency loop now reads a version's `_deploy.json` digest first and only recomputes when absent
(the "N content reads → N metadata reads" optimization `publish`'s docstring flagged as step-2's
job), and `migrate` now carries `_deploy.json` across a relocation (it isn't part of the content
digest, so a naive migrate would have silently dropped every version's deploy record). New
`tests/test_deploy.py` (15 tests, AC1/2/3/5/7/8/9/10/13a + D6) plus two new `test_registry.py`
tests for the two follow-on fixes; the AC7 pass/fail tests exercise the real `verify_image` call
through the same fake-`MLClient`/`azure.ai.ml.command` injection seam spec 45's tests use — no
network. Removed the now-obsolete `tests/test_api.py::test_deploy_is_stub` (asserted the old
`NotImplementedError` stub signature). Suite **920 passed / 91 skipped / 1 pre-existing failure**
(`planetary_computer` absent), ruff clean (`src/ tests/ demos/ examples/`). **Open, not yet filed:
a URL registry has no credentials for WRITE either** — `deploy` doesn't call `configure_storage`
(matching `run_inference`/`verify_adapter`'s existing non-call, issue #86), so `registry="abfss://…"`
would need real credentials this step deliberately does not add; tested only against a local
registry root. **NEXT: hand to Opus `/effort high` for review, then step 3** (the `[model] name@ref
-> vN (verified against <env>)` line + the environment-mismatch warning, D7/AC10's print half —
small, deliberately out of step 2's scope). Previous entry: step 1.)_

_Previously: 2026-08-22 (**spec 51 §9 step 1 (`_ensure_bundle` ref resolution) implemented and
REVIEWED**, merged into `main` (`--no-ff`) and **PUSHED — `main` @ `b85924b`, level with
`origin/main`, nothing unpushed**, worktree pruned. The Opus review
found a real defect the unit tests could not see: resolution sat at `_ensure_bundle`, but
`api._model_spec` reads `bundle.json` off `model` **first** in both `run_inference` and
`verify_adapter` (and `cores=1` pre-built cubes never calls `_ensure_bundle` at all), so
`run_inference(model="crop-rf@champion", registry=…)` still died with
`FileNotFoundError: crop-rf@champion/bundle.json` — proven by running it. **D4 amended (user chose
"Option A", 2026-08-22):** resolution is now one idempotent, shape-gated helper
`api._resolve_model_ref`, called at every site that reads `model` as a path; a string carrying a
path separator is never a ref (keeps it off `abfss://<fs>@<account>…`), and an already-resolved
path passes through, so a later call site cannot reintroduce the bug. Also tightened the AC6
`"@"`-without-`registry=` check (it had refused legitimate paths like `/data/rf@2026/bundle`),
wrapped `resolve` failures as `PreflightError`, dropped the dead `storage_options=`. **Open, not
yet filed: a URL registry has no credentials** — `run_inference`/`verify_adapter` never call
`configure_storage`, so `registry="abfss://…"` resolves anonymously (AC12 unmet; step-2 work).
Suite **904 passed / 91 skipped / 1 pre-existing failure**, ruff clean.
**NEXT: spec 51 §9 steps 2-3** (`deploy` → the `[model]` line). Previous entry: step 0.)_

_Previously: 2026-08-22 (**spec 51 §9 step 0 (`fsd.model.registry`) implemented, REVIEWED and
merged into `main`** — the Opus review found and fixed a real defect: `storage.fs.rename` was
`shutil.move` locally, so a `publish` losing a version race nested its bundle inside the winner's
directory and **returned the winner's version number**. Fixed at the seam (`fs.rename` is now a
real `os.rename` locally) plus a re-digest of what actually landed, and `_aliases.json` is now
written by rename too. Suite **890 passed / 91 skipped / 1 pre-existing failure**
(`planetary_computer` absent), ruff clean. `main` @ `2b5ae4b`, **PUSHED — level with
`origin/main`, nothing unpushed**, tree clean, no worktrees. **NEXT: spec 51 §9 steps 1-3**
(`_ensure_bundle` resolution → `deploy` → the `[model]` line). See the 2026-08-22 (later still)
entry below.)_

_Previously: 2026-08-22 (**spec 50 fully landed + PUSHED; spec 51 (P6 `deploy`) SIGNED OFF, not
implemented** — `main` @ `6e163c5`, **level with `origin/main`, nothing unpushed**, tree clean.
Suite 870 passed / 90 skipped / 1 pre-existing failure (`planetary_computer` absent), ruff clean.
See the 2026-08-22 entry below for the full state, including two defects found on the first real
AML run and the comment-convention work.)_

_(#94, 2026-09-03: the block below was `PROGRESS.md`'s `## Where things stand` — a continuously-true
current-state section that had gone stale, last substantially true around 2026-08-20. It is moved
here unedited as a point-in-time record of what that section said; the live current-state block is
in `PROGRESS.md`.)_

## Where things stand

**What fsd does today, proven on real infrastructure:** download → datacube → flatten → train →
inference, run both locally and fanned out across an Azure ML cluster. The 2026-07-29 cluster demo
(`demos/e2e_austria_aml.py`, run `20260729T132222Z`) completed unattended in **18.8 min, 8/8 steps,
97 jobs, 213 MPC granules, 300 grid cells → 300 output COGs + STAC + a merged map**. That run *is*
the validation ROADMAP P3 and P4 were waiting on.

**Current work: the docs refactor (spec 41).** P1–P5 are done **and P5 is reviewed** (8 findings,
all fixed — see the entry below); the rest is in the archive. P6/P7 remain.

| | state |
|---|---|
| **Pipeline** | v1 core complete (S2 L2A, CDSE + MPC), proven local and on AML |
| **Scale-out** | AML runner seam; download, build, flatten and inference all fan out |
| **Serving** | tier-1 (pre-styled XYZ) and tier-2 (pgSTAC + titiler-pgstac) both validated |
| **Docs** | spec 41 P1–P6 done; **P7 drafted + reviewed** (`docs/tutorial.md`, 5 `docs/howto/*` pages + index) — the D13 cold-start gate is the user's, not yet run |
| **Deferred work** | **GitHub Issues #1–#63**, number-aligned with the old `TODO.md` rows (39 open / 24 closed) |
| **Open decision** | rslearn Plan B vs Plan C — **no longer untouched: the spike is LIVE on `spike/rslearn`** (see below) |

**Where to look:**

| you want | read |
|---|---|
| how the code is laid out | [`ARCHITECTURE.md`](ARCHITECTURE.md) |
| where fsd is going | [`ROADMAP.md`](ROADMAP.md) |
| what a term means | [`CONTEXT.md`](CONTEXT.md) |
| why a decision was made | [`docs/adr/`](docs/adr/) |
| a measured result | [`docs/findings/`](docs/findings/) |
| an env variable | [`docs/reference/environment.md`](docs/reference/environment.md) |
| open work | `gh issue list` |
| what happened before | [`docs/progress-archive.md`](docs/progress-archive.md) |

> ⚠️ **A second workstream opened 2026-07-31 and does NOT live on `main`: the rslearn spike.**
> `spike/rslearn` (pushed, `b91f982`) is refreshed from `main` and now carries a re-read of
> rslearn **v0.1.13**, two offline probes and a VM run-book. **Its status lives in
> [`spike/README.md`](https://github.com/nikhilsrajan/fsd/blob/spike/rslearn/spike/README.md) —
> read that, not this file, when resuming the spike.** Three headline findings so far, all from
> source, nothing run yet: torch/lightning are **core** rslearn deps (no lite path);
> **zero** Azure support in 54,850 LOC; and `RSLEARN_COMPARISON.md`'s claim that fsd's
> calendar-`T` contract is *unique* is **wrong** — `QueryConfig.period_duration` is the analogue,
> but it drops empty periods, floors the span and end-anchors, so rslearn's `T` is data-dependent.
> Nothing about the spike belongs in `main` until the Plan-B/C decision.

**Spec 44 phase 1 is DONE (2026-08-19).** Merged to `main` and fully validated on the cluster:
`runbooks/45-verify-bundle-carried-code.md` Phases 0–2 all green on **`fsd-infer-sklearn:3`, an
image with no adapter source in it** (smoke `ok`; a real ROI run produced **9/9 per-cell COGs +
STAC in 8.2 min**), and the **QGIS eyeball passed**. `notebooks/e2e_austria_aml.ipynb` was updated
to match — cell 18's seven-step per-model image build is gone.

**Notebook session 2026-08-19 (later still) — one accepted change, one rejected shape, one leak
closed.** `notebooks/e2e_austria_aml.ipynb` is **gitignored, and it is reference material** — an
example of how a user drives fsd's Azure path, **not** a scratch harness. It was edited this
session without being asked to be; the user's correction is recorded below and in memory.

**Kept.** The inference image's name/version pin moved up beside the training one (one config
block), so the inference cell is two lines. The three long `"""…"""` scratchpad docstrings that sat
above the calls became one-line issue pointers, with their text verbatim in a closing **"Known
rough edges"** cell.

**Rejected and removed by the user: an upfront preflight cell.** The design constraint, which
generalises past this notebook: *a check belongs at the step it protects, in sequence.* A block at
the top that validates everything at once must hardcode input paths and assert artifacts that later
cells create — it checked `demo_model/my_adapter.py`, which the "Preparing model adapter" section
creates much further down. That reads as a harness, not as usage. The surviving fact is real
(`_aml_preflight_common` runs per **dispatch**, so the *inference* image is validated last, ~30 min
in) and now lives in `RECIPES.md` → "Check an AML environment pin at the step that uses it", as a
three-line check placed before `run_inference`.

**Leak closed:** `notebooks/runbook-45.ipynb` was **untracked and not ignored**, carrying a live
storage URL, two GUIDs and the rg/workspace/cluster names in source *and* outputs — one `git add -A`
from publishing them. `.gitignore` now ignores `notebooks/*.ipynb` as a class (no notebook is
tracked; `notebooks/README.md` still is) rather than naming files one at a time.

**`ruff` pinned to its rule set.** `ruff` is unpinned in `[dev]` and 0.16 widened its *default*
selection, so the documented `ruff check src/ tests/` reported **357 pre-existing** hits on
unchanged code. `[tool.ruff.lint]` now carries an explicit `select = ["E4","E7","E9","F","I"]` —
ruff's historical default plus import sorting. `src/ tests/ demos/ examples/` is clean again.

**Three issues filed** from the notebook's own notes: **#67** a standard helper for verifying an
inference image (today a run-book script + two env vars); **#68** datacube paths do not reflect
calendar-aware mosaicing (one run, two date-range folders); **#69** redundant child grid cells when
the ROI is itself a grid cell. Already filed and still open: #64 / #65 / #66.

**Six issues from the notebook are now specced, not yet signed off (2026-08-19, latest).**
`gh issue create` filed the last three — **#70** `save` does not report what it embedded, **#71** a
sibling import is not auto-detected, **#72** `code=` files from two trees break the import root —
joining #67/#68/#69. All six are designed in two drafts, each commented onto its issues:

| spec | issues | the one sentence |
|---|---|---|
| **45** `bundle-transparency-and-image-verification` | #70, #71, #72, #67 | spec 44 made the bundle carry its adapter; spec 45 makes it **say what it carried** and **refuse to be born broken** — plus `fsd.model.verify_image`, the run-book smoke promoted into the library |
| **46** `run-addressability-and-grid-dedup` | #68, #69 | a run's path should be a function of what was **requested**; a work unit another already covers should not be dispatched |

**Both defects in spec 46 were measured this session, not inferred:**
- #69: `roi_to_s2_grids` on the single-cell ROI emits **9** cells and **8 of them are fully covered
  by the ninth** — 89 % waste. The predicate has to be `covered_by`, not `contains` (`contains`
  caught only **2 of 8**: a clipped sliver *shares boundary* with its coverer, which `contains`
  excludes) and not IoU-1 (that means *identical*, which none of the 8 are). On the 300-cell AT_ROI
  the same rule costs **0.09 s** and drops **1** cell — safe on the normal case, decisive on the
  degenerate one.
- #68: the export path is built from each cell's *actual* min/max acquisition
  (`create_datacube.py:147-151`) while the calendar anchor that sets `T` is the *caller's* window —
  so the path both splits one run in two and implies a window the cube does not have.

**BOTH SPECS ARE SIGNED OFF (user, 2026-08-19).** Two decisions were the user's: a detected but
unembedded sibling import makes `save` **refuse, naming the file** (not auto-embed — `code=None`
keeps one meaning), and the run folder **encodes `mosaic_days`** (`20180401_20180930_m20`), so the
path identifies the cube contract completely. The four secondary questions were resolved with
defaults recorded in each spec's §7/§6 — overturn any of them in review.

**Specs 45 and 46 are IMPLEMENTED, REVIEWED and MERGED to `main` (2026-08-19) — see the entry
below.** Both specs' acceptance criteria are met, `pytest -q` is green (mpc-extra gap aside,
pre-existing), and `ruff check src/ tests/ demos/ examples/` is clean. Issues #67–#72 are closed
against the merge commit and the `worktree-specs-45-46` worktree/branch are pruned.

**Spec 47 is IMPLEMENTED and MERGED to `main` (2026-08-20) but NOT YET REVIEWED — see the entry
below, and the pointer memory `spec-47-review-handoff` for the next session's starting point.**
**→ NEXT: an independent Opus review of the merge (`ff8d088..2e5b3b3`), then `git push` `main`** —
push is outward, so it stays the user's call (CLAUDE.md, "push only when asked"); `main` is 5
commits ahead of `origin/main` as of this entry.

**Also still open:** **spec 44 phase 2** (`deploy` registration, D7/D8) — specified but **NOT
signed off**; §8 questions 5 and 7 (blob store vs MLflow-via-AML-workspace) are the live decision.
Run-book 45 Phase 3 (the migration boundary) is documented but was never formally walked.
**`main` has ~16 unpushed commits** — pushing is the user's call.

**Also next:** the spec 41 **P7 D13 cold-start gate** — the user, on a fresh clone and fresh venv,
follows `docs/tutorial.md` *literally* and reports the first instruction that doesn't work (a
spec-24 `_result.json`; no improvising, no fixing-as-you-go). The docs are drafted **and reviewed**
(4 findings, all fixed — entry below); `pytest -q tests/test_docs.py` (153 passed) + `ruff check
src/ tests/ demos/ examples/` are clean. After the gate passes, P7 is done and the remaining open
items are the rslearn Plan B/C decision and spec 43 (`docs/history.md`, deferred).
## 2026-08-22 (later still) — the Opus review of step 0: one real defect, fixed; merged to `main`

Opus `/effort high` review of `c0290fb` against spec 51 D1-D3/D9/D11 + AC1-5/11/13. Verdict on the
three flagged calls: **1 confirmed, 1 confirmed, 1 overturned and fixed** — plus one defect of the
same class the review found on its own. Suite **890 passed / 91 skipped / 1 pre-existing failure**,
ruff clean. Merged `--no-ff` into `main`; worktree pruned; **pushed at the user's request —
`main` @ `2b5ae4b` is level with `origin/main`.**

**Call 3 OVERTURNED — and the consequence was worse than the handoff described.** Reproduced
against the real code, not reasoned about: when a competitor completes `v1` in the TOCTOU window,
`publish` did not merely leave a confusing gap — it **returned `1`**, while `v1` held the
*competitor's* bundle and the caller's staged copy sat nested inside it as `v1/.staging-<uuid>/`.
A caller resolving `crop-rf:1` would have run a model it never published. That is not §5's
signed-off "gap in the sequence"; it is a silent wrong answer, and it also breaks D2's "a version
directory, once written, is never rewritten".

The root cause was **one level below the registry**: `storage/fs.py::rename` documents itself as
"`os.rename` locally" — the exact property D2 cites when it calls `fs.rename` the atomic-publish
primitive — but it delegated to fsspec's `LocalFileSystem.mv`, which is `shutil.move`, which
**nests** rather than raising. The spec was signed off on a premise about fs.py that was false.
Three fixes, smallest first:

- `fs.rename` now calls `os.rename` directly when both ends are local, falling back to fsspec's
  copy-and-delete only on `EXDEV`. A directory rename onto a non-empty directory now raises; a
  *file* rename still replaces atomically, so `datacube/builder.py`'s sidecar write is unchanged.
  (`CHANGES.md` records the behavior change.)
- `_write_new_version` no longer trusts the rename to have told the truth: it **re-digests what
  landed** before returning, and retries at `v<N+1>` if the directory is not its own — the same
  proof `migrate` already used to accept a copy (D11). If the winner published *identical* bytes,
  the digest matches and that version is returned, which is D2's idempotency reached by another
  route. The residual limit is stated in the docstring rather than implied: a backend whose `mv`
  merges prefixes can still interleave two writers, and that would need the lock §5 declines.
- **Found in review, same class:** `set_alias` rewrote `_aliases.json` **in place**, so a fan-out
  resolving `@champion` (D9's one read) could observe a half-written file mid-promotion. It now
  stages and renames. Concurrent `set_alias` calls can still lose an update — no lock — but no
  reader sees a torn file.

**Call 1 CONFIRMED (deferred, reason recorded in `publish`'s docstring).** The O(N-versions)
content re-read at publish time is accepted: `publish` is rare and deliberate, and it is not the
hot path D9 constrains. **Step 2 should make this loop read `_deploy.json`'s stored digest first**
and fall back to recomputing — turning N content reads into N small metadata reads. Doing it in
step 0 would have meant inventing a second digest-bearing file that D7 then supersedes.

**Call 2 CONFIRMED.** The `^v(\d+)$` refusal is exactly right and the edge shapes check out: `"v"`
alone does not match, so it stays a usable alias and resolves as one; `"v007"` is refused and
`@v007` pins v7; `"V3"` is neither. One residual, not worth code: `migrate` copies `_aliases.json`
verbatim, so a hand-edited `v3` alias would survive and be unreachable — the file is not a
supported edit surface.

**Tests: +5 (12 → 15 registry, +2 storage).** All three regression tests were confirmed to **fail
on `c0290fb`** before the fixes landed, not just pass after. The race is exercised by injecting a
competitor into the rename window, which is deterministic — the handoff had assumed it needed real
inter-process parallelism.

**NEXT: spec 51 §9 steps 1-3** — `_ensure_bundle` resolution (D4), then `deploy` (D5/D6/D7), then
the `[model]` line. Step 1 will need to decide how a `name@ref` is told apart from a bundle *path*:
`parse_ref` currently accepts `abfss://…` as name `abfss` + version `//…` and fails on the version
check, which is a confusing error rather than a wrong answer, but D4's table wants it routed by
`registry=` being present.

---

## 2026-08-22 (later) — spec 51 §9 step 0 implemented (`fsd.model.registry`); hand back to Opus

Sonnet `/effort medium` session, against `specs/51-deploy-model-registry.md` §9 step 0 alone
(handoff: `handoff-spec51-step0-registry.md`, workspace root). Worktree branch
`worktree-spec51-step0-registry` @ `c0290fb`, off `main` @ `82c8e28`. **Not merged, not pushed.**
Suite **885 passed / 91 skipped / 1 pre-existing failure** (same `planetary_computer`-absent one),
`ruff check src/ tests/ demos/ examples/` clean.

**Built `src/fsd/model/registry.py`**: `publish` (idempotent by content digest, atomic via
`storage.fs.rename` from a staging prefix), `resolve` (`name:version` / `name@alias` / `name@vN`,
zero reads for a version pin, one `_aliases.json` read for an alias), `migrate` (relocate + re-digest
every version, refuses a mismatch), `set_alias`, `content_digest`. No verb touched —
`api._ensure_bundle`/`deploy` resolution is steps 1–3. `tests/test_registry.py`, 12 tests, one per
AC1-5/11/13.

**Three design calls the spec left implicit, flagged for review rather than silently decided:**

1. **No `_deploy.json`-shaped file invented for step 0.** D2 says the digest is "recorded
   alongside" the version in `_deploy.json` (D7), which doesn't exist until step 2. `publish`'s
   idempotency check and `migrate`'s corruption check both **recompute** the digest live from
   `bundle.json`'s declared files instead of persisting one anywhere — keeps the on-disk layout
   exactly D1's diagram, costs more reads at publish time (bounded by version count, never on the
   resolution hot path D9 protects).
2. **`set_alias` refuses an alias shaped `v<digits>`** (e.g. `"champion"` is fine, `"v7"` is
   refused) — it would be permanently shadowed by the `name@vN` version-pin shorthand in `resolve`
   and could never be reached. Not addressed anywhere in the spec.
3. **A race hazard past what §5 signs off on.** Version allocation pre-checks `exists(target)`
   before staging + rename, but the local backend's `fs.rename` is `shutil.move`, which — if two
   publishers land in the TOCTOU window between that check and the rename — nests the loser's
   staged content *inside* the winner's already-published version directory instead of raising.
   §5 explicitly accepts "a confusing gap in the sequence" from a race; this is closer to
   corrupting the winner's directory, a step beyond what was signed off. Documented as a hazard
   comment in `registry._write_new_version`, not fixed — a real fix needs a lock, which the spec
   explicitly says is "not worth" building for v1.

**NEXT: Opus review + debug**, per the working style's model split (implementation-session can't
review itself, and spec 50's history — a green suite + two review rounds still missing what the
first real cluster run found — is why). Sign off or overturn the three calls above before steps 1–3
(`_ensure_bundle` resolution, `deploy` itself, the `[model]` print) build on this layout.

## 2026-08-22 — spec 50 landed + pushed; **spec 51 (P6 `deploy`) signed off**; comment convention

`main` @ `6e163c5`, **level with `origin/main`**, tree clean. Suite **870 passed / 90 skipped / 1
pre-existing failure** (`test_missing_driver_deps_is_empty_when_everything_is_installed`,
`planetary_computer` absent from `.venv` — reproduces on unmodified `main`), `ruff check src/ tests/
demos/ examples/` clean.

### Spec 50 — closed out over three review rounds

Opus reviewed the Sonnet implementation (`/tmp/review-fsd-spec-50.md`), found 2 blockers + 3 more
(F1–F5); Sonnet fixed those; Opus re-reviewed and found **2 defects the fixes themselves
introduced**; then the first real AML run surfaced **2 more**. All landed and pushed.

The two the re-review caught:

- **F2's fix swallowed `setup`'s duplicate-`id_col` guard.** `setup` raises `ValueError` for a
  second, unrelated reason — its deliberate refusal of a shapefile with duplicate ids (added
  2026-07-28, after a multi-polygon ROI made `roi_to_s2_grids` repeat cell ids). The bare
  `except ValueError` caught it, printed "no tiles in range/overlap" (false) and recorded the shapes
  known-empty: a loud refusal turned into quietly missing training data. Fixed with a dedicated
  `NoWorkUnitsError(ValueError)` subclass, so every existing `except ValueError` caller (notably
  `verify_adapter`) is unaffected.
- **F4's fix made the known-empty manifest load-bearing but write-only.** Once a cell was recorded
  empty, a forced rebuild (`overwrite="datacubes"`/`True` — D5's documented escape hatch)
  legitimately restored its `input.csv` row while the request-side identity kept subtracting it:
  permanent mismatch, F4 relocated rather than fixed. Fixed with `_forget_known_empty` /
  `_clear_known_empty`.

The two the **first real AML run** surfaced (user reported `create_training_data` apparently stuck
after `[plan] will run:`):

- **Stale pre-D6 `input.csv` rows were adopted.** `_row_matches_window` compared run *parameters*,
  which is not sufficient once D6 changed the path shape: a row written before it matches every
  parameter while still naming the pre-digest folder. Consequence was silent — the plan announced a
  full rebuild while the build leg, reading the row's own stale `datacube_filepath`, found the old
  cube present and dispatched **nothing**, and the flatten stamp then recorded paths the
  request-derived identity can never reproduce. `_row_matches_path` now makes the derived path part
  of what makes a row current.
- **The cube-presence sweep was a silent serial walk.** `_cube_present` is four blob round-trips per
  cell and ran per cell, serially, in **two** places with no output: ~3600 sequential round-trips at
  900 cells, ~20 min over the WAN, indistinguishable from a hang — while `setup` has used 16 threads
  for the same class of I/O since spec 47. Presence now resolves from **one recursive listing per
  `<window>` folder** (`storage.fs.find_sizes` → `_present_cube_ids_at`), compared in memory by the
  `<id>` path leaf so it never reconciles local `abspath` against a backend's path spelling.
  Unlistable folders fall back to per-path checks that are concurrent **and** ticked.

**Notebook `notebooks/e2e_austria_aml.ipynb` updated** (cells 3 and 8) for the backward walk: the
`[plan]` block, `TRAIN_RUN` now optional (#83 fixed), `_manifest.json`, and a prominent warning that
D6's path change **orphans cubes built before it** — the next run is a one-time full 900-cube
fan-out, not a resume (`20180401_20180930_m20` → `20180401_20180930_m20_cc38ae79`; `verify_adapter`
moves to `..._1adc8caa`). The notebook is gitignored, so this is not in git.

### Spec 51 — P6 `deploy`, SIGNED OFF 2026-08-22, NOT implemented

`specs/51-deploy-model-registry.md` (588 lines, D1–D11, all seven §7 questions answered).

**What it decides.** `deploy` binds a **saved** bundle to the inference image **proven** to run it,
under one immutable name. Registry = a prefix on the storage seam (no new infra; `rise`'s storage
account and RBAC already exist). Immutable versions + a content digest; **aliases** are the only
mutable pointer (`crop-rf:3` for a version — spec 44 D7's spelling — `crop-rf@champion` for an
alias, bare `crop-rf` refused). `deploy` refuses an unverified pair, a bundle without declared
`requirements`, and a live adapter.

**It completes `specs/44` phase 2 (D7/D8)**, proposed in July and never signed off, and finally
answers spec 44's §7 Q7 (MLflow — no, out of scope; analysis retained in §6 so it can be reopened
cheaply). It removes spec 44 D8's **measured 627 s per run** of redundant bundle re-upload.

**D11 is the one to remember:** the central registry location is undecided *on purpose*, so nothing
the registry writes may contain an absolute path, a URL, or the registry root. Relocation is then a
copy plus a changed `registry=`, verified by re-computing the D2 digest. `migrate` therefore ships
in §9 **step 0**, not later.

**Left open deliberately, both recorded in §6/§7:** where the central registry finally lives, and
public model hosting (Hugging Face as a separate `fsd.publish` verb, *not* a D10 backend — a public
bundle advertising a private `fsd-infer-sklearn:6` would promise a binding no outsider can act on).

### Comment convention (issue #85)

`src/fsd` measured at 28% prose / **0.49 prose lines per code line**, 986 backward references across
422 functions. Classifying 3,188 substantive prose lines: 18% pure development history, 3% history
around a why, 11% pure rationale, 68% plain description — so the narrative is not the bulk; the
**tag density** is what makes it read like a changelog. `docs/reference/code-comments.md` states the
rule as **cut the changelog, keep the hazard**, applied to `storage/` as a worked sample (1.05 →
0.82 prose per code line, 27 → 2 refs, proven comments-only by comparing ASTs with docstrings
stripped). The rest of the sweep is **issue #85**, to be done *before* the next major development
push. `fs.py`'s reverted `_write_with_retry` block moved to `DROPPED.md`'s new "Approaches tried
inside fsd and reverted" section.

### NEXT — implement spec 51 (Sonnet, `/effort medium`)

Against `specs/51-deploy-model-registry.md` §9, in order. **Step 0 first and alone**:
`fsd.model.registry` — layout, `publish`, `resolve`, `migrate`, `_aliases.json`, the content digest.
Pure local-filesystem unit tests, no verb touched, no Azure. Steps 1–3 (resolution in
`api._ensure_bundle`; `deploy` itself; the `[model]` line) follow.

Known trap for that session: `EnterWorktree` branches from `origin/main`; and tests inside a
worktree import the **wrong** `fsd` unless `PYTHONPATH=$PWD/src` is set, because the shared `.venv`'s
editable install points at the main checkout's `src/`.

## 2026-08-21 — spec 50 §9 steps 0/1/2/4 implemented and merged; hand back to Opus for review

A Sonnet session (`/effort medium`) implemented spec 50 against the signed-off spec, per
`HANDOFF-spec-50.md`. Steps landed in order, each its own commit, `--no-ff` merged to `main`
(worktree pruned per standing practice):

- **Step 0 (D6/#83).** `run_folderpath` no longer defaults to a fresh UTC timestamp for
  `runner="aml"` — the default is now the plain stable name `{root}/runs/train` (never a hash of
  the request/shape-id set, per Q1). The window path segment
  (`<startdate>_<enddate>_m<mosaic_days>`) gained a `_<params_key>` suffix, a short digest of
  `(bands, mosaic_scheme, scl_mask_classes)`, so two requests differing only in `bands` resolve to
  different cube paths instead of silently colliding. `test_build_skip.py`'s characterisation test
  for #83 is flipped (its own docstring's instruction), not deleted.
- **Step 1 (D3).** New `api._flatten_identity_from_request` computes the same identity
  `_flatten_identity` computes from `input.csv`, but from the request (label polygon ids, window,
  params) with zero file reads — a cube's path is derivable from `(run_folderpath, window, id)`
  alone. Written and compared (a test proves the two identities agree given equivalent inputs);
  nothing short-circuits on it yet.
- **Step 2 (D2, §9 phase 1).** `create_training_data`'s preflight splits into two waves: structural
  checks raise first, then the target (arrays + `_flatten_stamp.json`) is checked BEFORE the
  catalog/download preflight wave — a fully-resumed call now needs `catalog_filepath` to exist no
  more than it needs `setup` to run. Prints the D7 `[plan] ... CURRENT` / `[fetch] ...` lines.
- **Step 4 (D2/D4/D5/D7, §9 phase 2).** New `create_datacube.build_shortfall_only`: cube targets are
  enumerated from the request alone (no catalog access), so `setup` runs only for shapes whose cube
  is missing and not already known-empty. A sibling `_manifest.json`, keyed to the window/params
  segment, records known-empty cells so they are never rediscovered (two identical re-runs both
  converge to a shortfall of 0). Existing `input.csv` rows for a DIFFERENT window/params are purged
  first — deliberately narrower than D9 (which would let rows from different windows coexist
  forever, exactly what makes #84 possible): this only ever grows `input.csv` within one window.
  `run_create_datacube` gains this as an alternative to `overwrite_setup_csv`'s legacy path (kept,
  unremoved — that removal is step 3); `create_training_data` opts in unless the caller explicitly
  forces a cube rebuild.
- **A real bug caught by `test_tutorial_fixture.py`** (id_col=`"fid"`, not `"id"`): `setup` always
  writes the id column as `COL_ID` ("id"), never the caller's own `id_col` name — reading back
  `input.csv` via the caller's `id_col` crashed with `KeyError`. Fixed in `build_shortfall_only`.

**Step 3 (D9, `overwrite_setup_csv` removal) deliberately NOT done** — the spec's own ordering
constraint: D9 makes multi-window training data reachable, and it is broken one layer up (`ids.npy`
has no window component, `median_per_id` silently medians two windows of one field into one sample)
until #84 is fixed. `overwrite_setup_csv` still exists in the signature.

**Spec 50 §4 acceptance criteria: all met except AC7c** (its `input.csv` accumulate-across-windows
assertion depends on step 3). 24 new/updated tests in `tests/test_backward_walk.py` +
`tests/test_build_skip.py`, including AC11 (identical behaviour under `runner="local"`/`"aml"`,
parametrized). `runbooks/48-e2e-austria-with-verify-adapter.md` updated: the `TRAIN_RUN` pin is now
an optional override, not a requirement, since #83 is fixed.

**Gate:** full suite 860 passed / 92 skipped / 1 pre-existing failure (`planetary_computer` missing
from `.venv`, reproduces on unmodified `main`), `ruff check src/ tests/ demos/ examples/` clean.
`main` is **7 commits ahead of `origin/main`, unpushed** — pushing is the user's call.

**NEXT:** hand back to an Opus session for review (an authoring session cannot review itself, per
the definition of done) — in particular the design call in step 4 (purge-other-window-rows to stay
narrower than D9) and the `overwrite_setup_csv=build_overwrite` wiring are the two judgment calls
most worth a second look.

## 2026-08-21 — **spec 50 signed off**: resolve backwards from the target; #83/#84 filed

The user asked what the current skipping approach is and proposed the Snakemake **rule** shape —
check the output, and if it must be produced, check its inputs, recursively. Investigating it turned
up two defects and one designed-but-unreachable capability.

### The measurement that started it

A fully-resumed `create_training_data` still paid a complete `setup` pass: **`[setup] 900/900 shapes
| elapsed 96s`**, ~1800 blob writes, on a run where every cube already existed. `setup` runs on every
call because `overwrite_setup_csv=True` deletes `input.csv` first. Each leg does its own preflight
*before* its skip can be evaluated, so the cheapest question ("are the arrays already here?") is
asked last.

That makes spec 49 **not actually delivered**: its acceptance sentence is the user's own — *"the only
task create_training_data does is to download the flattened numpy arrays"* — and all 11 of its
criteria pass because every one is written against `input.csv` and `run_create_datacube`, none
against *what ran before the skip*.

### `specs/50-backward-walk.md` — SIGNED OFF, all six §7 questions answered

Two answers overturned the draft, and both improved it.

- **Q1 → D6: no set hash, address per path.** The draft wanted the run folder named from a digest of
  the request including the sorted shape ids. Rejected: that makes the *group* the unit of
  addressing, so one added polygon invalidates all 900 cubes. Address per path and let
  `<params>/<id>` carry the granularity `setup` already builds. **One correction the path needed:**
  the middle segment is `<window>_m<mosaic_days>` while the row identity `_UNIT_IDENTITY_COLS` also
  includes `bands`/`mosaic_scheme`/`scl_mask_classes` — so two requests differing only in `bands`
  resolve to the **same path** today, the second overwriting the first while the build skip reads it
  as present. The segment gains a digest of those *shared* parameters. Still a digest, not the
  rejected one: it digests what every cell shares, never the set of cells. → memory
  `fsd-addressing-granularity`.
- **Q3 → D9: `input.csv` accumulates.** The user recovered the real rationale for the delete, which
  inverts the previous day's finding. `setup` appended so it could be run repeatedly with different
  windows, accumulating units; the delete was a workaround for a missing dedupe. **The "true
  solution" already exists in fsd** — `_dedupe_on_unit_identity` (spec 38 D13, #53), whose docstring
  states the intent verbatim. So `overwrite_setup_csv` does not merely predate the fix, it
  **defeats** it: deleting `input.csv` leaves nothing to append to or dedupe against. That is why
  accumulate-across-windows has been unreachable since day one and why nobody noticed the mechanism
  was already written.
- **Q5** both phases committed. **Q6 → D10**: `verify_adapter` always verifies — the cube is an input
  and may resume, the adapter run is the work and never does. **Q2/Q4** as proposed.
- **D3 is the load-bearing decision**: the flatten identity moves from `input.csv` (which is
  `setup`'s output — the knot) to the *request*. Sound because a cube's path is derivable from
  `(run_folderpath, window, id)`; `setup`'s catalog filtering builds a cube, it does not name one.
- **D1 keeps spec 49 §6's constraint**: the walk is fsd's own, on the driver, above the runner seam.
  Snakemake is the model, not the mechanism — the AML runner still has no DAG.

### Two issues filed, one of which gates D9

- **#83 — spec 49's skips cannot fire by default.** `run_folderpath` defaults to
  `{root}/runs/{fresh UTC timestamp}`, so every re-run addresses cube paths that have never existed:
  the shortfall is always N of N and no stamp can match. Found in real use — the user's resumed run
  dispatched all 32 shards twice. Worse, `_build_shortfall` prints **nothing** in the N-of-N case
  (a full dispatch is not a skip), so it fails silently. **`runner="local"` was never affected**
  (its run folder is `export_folderpath/run`, no clock). Spec 50 D6 fixes it; `TRAIN_RUN` in the
  notebook is the workaround today.
- **#84 — multi-window training data is silently wrong**, and D9 is what makes it reachable.
  `ids.npy` carries no window component, so two windows of one field collide, and `median_per_id`
  (`np.unique(ids)` + `np.nanmedian`) merges them into **one sample that is the median of both
  years** — no error, no shape mismatch. `aggregate="median_per_id"` is what the Austria demo uses.
  **§9 records the ordering constraint: D9 must not land before #84's array-layer fix.**
  Reachable-and-wrong is worse than unreachable, and the delete is currently protecting us from it.

### Also this session

- **Specs 48 + 49 Opus-reviewed and their defects fixed** (entries below): `_result.json` was never
  written; an unstamped cube was reused then mis-stamped; and `verify_adapter(runner="aml")` could
  not have worked at all — it handed the AML node an absolute *driver* path to write the cube to.
  All three carry red-first regression tests. #76 and #77 filed.
- **`notebooks/e2e_austria_aml.ipynb`** (gitignored) now runs `verify_adapter` between the adapter
  and bundling cells, and carries `RESUME_RUN` + `TRAIN_RUN`. `runbooks/48-e2e-austria-with-verify-adapter.md`
  is the two-pass run-book; its Pass B was corrected once #83 was understood.
- **`tests/test_build_skip.py`** now characterises which paths are clock-derived. Only three exist in
  `src/`; only `create_training_data`'s feeds a skip. **`run_inference` is structurally immune** —
  its run folder is `output_folderpath/cells`, named by the caller, which is why spec 47 D5's
  per-cell output skip works today. (It still decides that skip *on the node* — #77.)
- **PROGRESS.md archived** back to the spec-47 review (spec 41 D12): it had reached 981 lines.

### NEXT — implement spec 50 (Sonnet, `/effort medium`)

**Handoff doc: `HANDOFF-spec-50.md` at the WORKSPACE ROOT** (outside the repo, as before — it names
the untracked files that carry real Azure values). It holds the traps, the definition of done, and
the verified test baseline (**847 passed, 92 skipped, 1 known pre-existing failure** on `a00702f`).
The `/handoff` session baton is `/tmp/handoff-fsd-spec-50-implementation.md` — ephemeral, and it
points back here.

§9 order: **0** #83/D6 deterministic run folder → **1** D3 request-derived identity → **2** phase 1
top-level short-circuit → **3** D9 append+dedupe **(BLOCKED on #84)** → **4** phase 2 the full walk.

**Steps 0, 1, 2 and 4 are unblocked. Step 3 is not** — decide #84 first, or hand off with D9
explicitly deferred.

### Gate

`main` @ `5a0a4e5` + this entry, **18+ commits ahead of `origin/main` and unpushed.** Pushing is the
user's call and has not been asked for. Nothing in `src/` has been touched for spec 50.

## 2026-08-21 (later) — `verify_adapter` wired into the AML e2e notebook; a third review defect found

The user asked to re-run `notebooks/e2e_austria_aml.ipynb` on the specs 48+49 code, with
`verify_adapter` added after the adapter is written. Wiring it up surfaced a defect the review had
not: **`verify_adapter(runner="aml")` could not have worked.**

**The defect (fixed, `7d0f780`, merged `126c75f`).** The verb passed
`run_folderpath=export_folderpath/_build` — a *local* path — to the per-cell build unit.
`create_datacube.setup` turns a local `run_folderpath` into an **absolute driver path**
(`os.path.abspath`) and writes it into `input.csv`, which on `runner="aml"` is read by the **node**.
So the node was told to write the cube to `/Users/<driver>/...`, which does not exist on it. The
build now roots on `runner_kwargs["root"]/runs/<run_id>/_verify_adapter` exactly as
`create_training_data` roots its own run, and the cube is transferred DOWN into the local
`export_folderpath` — which is what D5 said landing was all along. `runner_kwargs["root"]` is now
required for `runner="aml"`. Two red-first tests.

**Why the ACs missed it, worth remembering:** AC1's test monkeypatches `run_create_datacube`
wholesale, so it asserts *how many* builds happen and never *where*; AC10's real end-to-end runs
`runner="local"`. A spec can have a fully-tested criterion for "the case that matters in practice"
and still never execute that case.

### Notebook changes (`notebooks/e2e_austria_aml.ipynb` — gitignored, not committed)

- **`RESUME_RUN` in the config cell.** `ROOT` carried a fresh timestamp every run, so *none* of
  spec 49's skips could ever fire — a re-run addressed a brand-new archive. `RESUME_RUN` pins a
  previous run id back. Without this the notebook could not demonstrate spec 49 at all.
- **A `verify_adapter` section between the adapter and the bundling cells**, which is where the
  notebook's own "To do" already asked for it (*"test out the adapter before bundling"*, *"create
  one single datacube … and run via adapter"*). Takes the **live** adapter, so the run exercises
  bundling too; `cell=None` for the deterministic pick; `export_folderpath` keyed to `RUN` because
  the resume stamp covers the request but **not** `catalog_filepath`.
- The bundling cell no longer re-constructs the adapter — one source of truth for `n_timestamps`,
  and nothing is bundled that has not had real pixels through it.
- Expectation blocks updated for spec 49's `[build]`/`[flatten]` lines, including the one-time
  "the first resume re-flattens because the stamp did not exist yet" case; `#76`/`#77` and the
  archive-identity gap added to "Known rough edges".

### Run-book

`runbooks/48-e2e-austria-with-verify-adapter.md` — two passes: **A** fresh (nothing to skip), **B**
resumed with `RESUME_RUN` (the actual spec 49 test). Claude does not run it; the user pastes back
each step's result block. The QGIS check on `output.tif` is step A4 and is the deliverable, not the
verdict dict.

### Gate

`main` @ `126c75f` + this entry, **unpushed**. The notebook is gitignored and stays that way.

## 2026-08-21 — specs 48 + 49 **Opus-reviewed**: 2 defects fixed, #76/#77 filed

Independent Opus review of `20a47e7..c0d9d17` (the Sonnet implementation entry below), per the
standing practice that the authoring session cannot be its own reviewer. Fixes in `4989025`.

**Verdict: all 25 acceptance criteria are met** — spec 48's 14 and spec 49's 11. The two
structural ACs are genuinely asserted rather than assumed (`test_no_verify_adapter_branch_in_
shared_inference_code` greps `engine`/`infer_only_task`/`bundle` for the forbidden branch; the two
"no mtime" tests scan the skip logic's own source). The shared identity helper spec 49 §7 Q5
required exists exactly once, as `fsd.workflows.stamp`, and is used by both specs. Checked
independently: `pytest -q` at 836 passed / 88 skipped / the 1 known `planetary_computer` failure,
`ruff check src/ tests/ demos/ examples/` clean, and
`test_verify_adapter_real_fixture_local_runner` (spec 48 AC10, the no-network end-to-end) really
runs rather than skipping.

| # | defect | fix |
|---|---|---|
| 1 | **`_result.json` was never written.** D8 lists it among the artifacts `export_folderpath` holds and the verb's docstring names it, but only the dict was returned — and spec 24's whole run-book protocol is the user pasting that *file* back. A failing verdict also returned in total silence. | every exit routes through `_finish_verify_adapter`, which writes the file and prints the error + path on a failure |
| 2 | **an unstamped cube was reused and then mis-stamped.** The cube landing used `_land_local(force=False)`, so a `datacube.npy` that merely EXISTED was skipped as "already landed" — and `write_stamp` then recorded THIS request's identity over the previous request's pixels. Reachable by deleting `_cube_stamp.json` to get past the "different request" refusal. | `force=True`: reaching that branch MEANS the local cube is not trusted. Existence standing in for identity is exactly what D5 exists to prevent — and the same reasoning was already applied correctly to the AML flatten branch |

Both regression tests were confirmed red on the unfixed code (`assert False` on the missing file,
`assert 7.0 == 0.0` on a sentinel cube surviving the rebuild).

### Cleared, not flagged

- **`_force_rebuild` and #50.** It calls `fs.rm` non-recursively on single files; #50 is specific to
  `rm(recursive=True)` on `abfss://`, so it does not apply.
- **Spec 49 AC10** (a fully-skipped run and a full run return equal `TrainingData`).
  `_apply_training_features` persists `feature_bands` into `metadata.pickle.npy`, so the skip path
  reconstructs it from disk correctly.
- **D3 vs. a same-path rebuild.** The stamp cannot catch a cube rebuilt at the same path with the
  same parameters (no content digest — §7 Q2's signed-off default). The implementation is honest
  about it: `overwrite="datacubes"` forces the flatten leg rather than relying on the stamp, and the
  docstring says so plainly. Correct call, and the residue is Risk 1, not a defect.

### Filed, per spec 49 §7's sign-off

- **#76** — datacube writes are not atomic, so a truncated cube passes spec 49 D2's presence test and
  is skipped as built (Q2; #74 one level up, and the `.part`+rename primitive already exists).
- **#77** — `run_inference`'s build leg still pays a cold start to discover work already done: its
  per-cell skip is decided on the node, after dispatch (Q6; the #64 shape once more).

### Not addressed, deliberately

- **`cell="random"` twice into one `export_folderpath` now raises** rather than building the new
  cell — the D5 identity includes `cell`, so a fresh random pick reads as a different request.
  Defensible, but D3 sells random as the way to sample an ROI. Wants a docstring sentence or a
  per-cell subfolder; neither is a defect against a written AC.
- **The "no mtime" guards are substring scans** (`getmtime`, `st_mtime`, `os.stat`, `.stat()`) and
  would not catch the fsspec route (`fs.info(...)["mtime"]`); `api._artifacts_present`, which the
  flatten skip depends on, is not in the scanned set. No such call exists today, so AC6 holds.
- **Driver-side cost grows with N:** `_cell_coverage` runs one full-catalog `filter_gdf` per grid
  cell (299 passes on AT_ROI when `cell=None`), and `_cube_present` costs 4 storage round-trips per
  cube (~3,600 for 900) where one prefix listing would do. Both spec-sanctioned; both worth an issue
  if a re-run ever feels slow before it feels wrong.

### Gate

`main` @ `0d9bfef` is **5 commits ahead of `origin/main` and unpushed** — the implementation
(`16f688c`) and its merge (`c0d9d17`), then this review's two commits (`4989025` fixes + tests +
spec headers, `77c9ce0` this entry) and their merge. Pushing is the user's call.

## 2026-08-20 (later) — specs 48 + 49 signed off; notebooks made public; **NEXT: Sonnet implements both**

Handoff doc: **`HANDOFF-specs-48-49.md` at the WORKSPACE ROOT** (outside the repo — it names the
untracked file that carries real Azure values). `main` @ `3fedd1f`, **pushed**, tree clean.

### Two specs, both signed off with §8 cross-validation complete

| spec | verb / change | the decision most likely to be got wrong |
|---|---|---|
| **48** `specs/48-verify-adapter.md` | new `fsd.verify_adapter` — build ONE cell's cube on AML, land it locally, run the adapter over it, return a verdict + an `output.tif` for QGIS | **D6**: the inference leg must call `workflows.infer_only_task.run_infer_only`; **no branch may say "if verify_adapter"** (AC6). If local and cluster can differ, the verb is worthless. |
| **49** `specs/49-skip-work-already-done.md` | skip the datacube build when every cube is present, and the flatten when its arrays came from exactly those cubes | **D3**: keys on **identity, never modification time** (AC6 asserts no mtime is read). |

**The gap spec 48 closes:** every existing gate asks *"would the adapter import?"* — `bundle.save`'s
refusals, `_wheel_has_spec44`, `adapter_smoke` (whose own docstring says "No pipeline logic"),
`verify_image`. **Nothing runs `predict` on real pixels until the 299-cell fan-out.** An adapter
with the wrong `n_timestamps`, a `feature_sequence` emitting the wrong band set, or a `predict`
returning the wrong dtype imports perfectly and smokes green.

**Naming took three passes and is closed:** not `dry_run` (means "execute nothing" universally),
not `test_adapter` (pytest collects `test_*` even when only *imported* — would have broken fsd's
own suite), not `adapter_smoke` (already taken by `fsd.workflows.adapter_smoke`, and a "smoke test"
means synthetic-data format checking). `verify_adapter` follows `verify_image`'s existing precedent.

**Spec 49 D3 declines the mechanism originally proposed (mtime), and §8 backs it:** Bazel decides
staleness by input **content digests** where Make compares timestamps; DVC's `dvc.lock` is the same
sidecar shape (and contributed two refinements — record outputs too, treat parameters as
dependencies); and on Azure a blob's `Last-Modified` is **read-only and cannot be back-dated by any
means**, so a timestamp physically cannot carry "when this content was produced". That last finding
made D3's argument stronger than drafted.

**Shared piece:** spec 49 §7 Q5 signed off that spec 48 D5 and spec 49 D3 use **ONE** identity
helper, not two. Build it during 48, import it in 49.

### Also landed this session

- **Spec 47 reviewed by Opus** (5 defects fixed, #64/#65/#66 closed, **#75** filed for D9's deferred
  existence pass). Notable: the merge progress bar was measuring header-opens, not the ~1000 s of
  pixel reads it claimed — it hit 100 % and then ran the expensive phase in silence.
- **The AML image build is documented and split.** `notebooks/00_build_images.ipynb` is **the one
  tracked notebook** (`.gitignore` un-ignores it explicitly), with `docs/howto/build-the-images.md`
  as the scrubbed public page and `notebooks/images/{base,sklearn}/` as tracked build contexts.
  Part A and Part B register independently, because `az ml environment create` **always** mints a
  new version — registering both every time churned the one you never touched.
- **`notebooks/_config.py`** is the single point where a private value enters a public notebook; it
  reads `env.local.sh` (gitignored, now 6 vars). **`tests/test_notebooks.py`** (14 tests) is what
  lets a notebook be tracked at all: no saved outputs, no GUID/email/home-dir/storage-URL/RG/
  workspace/cluster names, scanned across source *and* outputs. **Verified to fail on the
  pre-scrub file — 6 of 9 fired.**
- **`env.example.sh` stays complete (54 vars)** and marks the six the notebooks read. It was trimmed
  to 6 mid-session; that broke `test_az_var_parity` for real — `docs/` names 47 of the removed vars
  and `demos/` reads 8. The trimmed copy is on the git stash if retiring the other 48 is ever
  wanted; that needs `docs/reference/environment.md` and `demos/` to move with it.
- **Two bugs found by running things:** an AML v2 environment build is an **ACR task run, not an AML
  job**, so the `prepare_image` poll in `RECIPES.md` (since 2026-07-29) matched nothing and looped
  forever — corrected at source, and the wait is now a Studio link. And `git status --porcelain`
  over the whole tree let one stray untracked file pin every status cell to "dirty".

### Gates

**804 passed, 90 skipped, 1 pre-existing failure** (`test_missing_driver_deps_…`,
`planetary_computer` absent from `.venv`, reproduces on unmodified `main`);
`ruff check src/ tests/ demos/ examples/` clean.

### Still open

**#75** (spec 47 D9's existence pass), **#74** (atomic download writes — the prerequisite that makes
existence the right predicate), **#73**; CDSE's own no-op diff (spec 47 D8 scopes it out); spec 44
phase 2 (`deploy`, unsigned). **Gated on a successful e2e run:** tracking
`e2e_austria_aml.ipynb` + `notebooks/shapefiles/` — and note **`AT_2018_TRAIN.geojson` is
EuroCrops-derived**, so its licensing is unresolved for a public MIT repo.

---
