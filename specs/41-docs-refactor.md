---
status: current
summary: This docs refactor itself: point-in-time vs continuously-true classes, the status header, the TODO-to-Issues migration, one-fact-one-home, and the demo/benchmark/example/tutorial split.
---

# Spec 41 — the docs refactor: make the corpus navigable and give fsd a front door

**Status: ✅ SIGNED OFF (2026-07-30, user) — grilled 2026-07-29/30 (Opus@high, `/grill-with-docs`).**
ADRs 0022–0026 and the `CONTEXT.md` glossary entries are written. Implementation (P1–P5, P7) has
not started.

> Implements TODO #55, whose gate (*"do this AFTER a timed e2e demo … with stepwise time
> accounting, structured logging, and a report"*) was met on 2026-07-29 when the cluster demo
> ran end to end and validated ROADMAP P3+P4.
>
> **Two pieces are carved out of this spec** and do not gate it:
> - **Spec 42** — the tutorial micro-fixture build (data engineering, its own acceptance criteria).
> - **Spec 43** (to be written) — `docs/history.md`, deferred until P1/P2 have done its archaeology.
>
> TODO #55 asked for a C4 doc set. **That framing is superseded here** — see D0. C4 survives as
> the section outline inside one file, not as a file count.

---

## 1. The problem, measured

> **AMENDMENT A1 (2026-07-30, user confirmed) — the file counts below are wrong.** This spec says
> "42 specs" throughout (here, D4, D14) and derives "21 of 42 specs already carry a status line"
> from it. **Measured during P1 implementation:** `specs/*.md` is **46 files** (44 pre-existing +
> the two written the same session as this spec, 41 and 42 themselves), not 42; `runbooks/*.md` is
> 28 files total of which **23 are actual run-books** — that 23 was already correct. So every "42
> specs" below should read **44** (the count at the time this spec was written) / **46** (the count
> once 41+42 exist), and the derived claim should read **"21 of 44 specs already carry a status
> line."** Per ADR 0022, this is recorded as an amendment rather than silently correcting the prose
> above and below — a signed-off spec is point-in-time. P1 (spec 41 D14) stamped all 46 specs + 23
> run-books + `demos`/`benchmarks` reports against the corrected count; see the regenerated
> `specs/README.md` / `runbooks/README.md`.

The corpus is **201 markdown files / 284,441 words** (2026-07-29) — roughly a 950-page book:

| Register | words | genre |
|---|---|---|
| `specs/` (42 files) | 91.8k | design proposals, written at decision time |
| `runbooks/` (23) | 48.6k | operator procedures fused to acceptance criteria |
| `PROGRESS.md` | 38.7k | resume anchor **and** append-only historical log |
| `TODO.md` (62 rows) | 16.9k | open work, closed work, and measurement essays |
| `CHANGES.md` | 13.0k | behaviour deltas |
| `demos/` (4 md) | 12.6k | benchmark reports read as if they were guides |
| `docs/adr/` (21) | 5.4k | one decision each — **already correct** |
| `README.md` | 352 | front door; **stale** (says CDSE-only; `run_inference` "a stub") |

The user's three complaints, verbatim: *runbooks are unreadable; specs no one would read; the
TODO is too difficult to go through and find out what exactly is missing* — plus the goal:
*document in a way that allows someone new to pick up the work and continue, including me,
months from now.*

### 1.1 Diagnosis — this is not a documentation shortage

Three findings, each measured, each pointing at the same defect:

1. **Nothing was ever supposed to keep specs and runbooks true.** A spec records what was
   decided *then*; a runbook records a procedure executed *then*. They are **point-in-time**
   artifacts. Reading them as current documentation is a category error — and the corpus has
   never had a category label. Evidence that this is real, not theoretical: **21 of 42 specs
   already carry a status line in ~12 different formats, 21 carry none, and at least three are
   wrong** — spec 39 still reads `🚧 DRAFT — awaiting final sign-off` although it shipped and
   the cluster ran it; 25b and 26 still read "awaiting implementation".

2. **Three separate documents are each two documents fused**, and the fusion is what caused the
   decay in every case:
   - `PROGRESS.md` = always-current resume anchor **+** 38.7k-word historical log.
   - `demos/E2E_AUSTRIA*.md` = tutorial **+** benchmark report. Its §2 heading reads *"CDSE now;
     MPC later"* — stale in the opposite direction, because it narrates one week's run inside a
     document people read as instructions.
   - `TODO.md` = open work **+** closed work **+** multi-page measurement findings (#59 is 1,137
     words, #61 is 792 — these are research write-ups living in table cells).

3. **`demos/` is a benchmark suite, and cannot serve as an example.** `e2e_austria.py` is 531
   lines of which **12 touch `fsd` at all** (2.3%); the distinct public surface it exercises is
   three functions. Worse, `step_download` calls `cdse.probe_throughput` and
   `cdse.download_resume` **directly, bypassing `fsd.download`**, because it wants the
   single-stream baseline probe and the transfer-vs-convert split — measurement concerns. A
   newcomer reading the reference implementation learns *the wrong API*. Meanwhile `benchmarks/`
   already exists holding exactly this pattern (harness + `*_report.md` + stats JSON) eight times
   over, and `examples/` exists with **one** file.

So the gap is not prose that was written badly. It is **a category system that was never
declared, and two artifacts (a tutorial and a readable example) that nothing ever needed.**

---

## 2. Decisions

### D0 — C4 is demoted from file-count driver to section outline

TODO #55 specified "≤~5 docs following the C4 model". C4 is a model for *diagramming a system
you deploy* (c4model.com); fsd is a `pip install`-able library plus a pipeline running in three
modes, and the mapping is awkward. What we keep: **Context / Container / Deployment as the
section outline of one file** (`ARCHITECTURE.md`), rendered as Mermaid. What we drop: the file
count, the Component level as a separate document, and Level 4 entirely.

**A trap this avoids:** C4's "container" means *a separately runnable thing* — the site's own
page opens with **"Not Docker!"**. fsd has real Docker images (the AML Environments), and they
are **not** its C4 containers. fsd's containers are the **driver**, the **AML node**, **blob
storage**, and the **catalog**; `fsd.storage`/`fsd.workflows` are the *same package* running
inside two of them. `CONTEXT.md`'s driver/node/dispatcher vocabulary already maps onto this
level, which is why the file can be written without inventing terminology.

### D1 — Audience: A + B + C. D is explicitly not served

| | Reader | Served how |
|---|---|---|
| **A** | Future-you, months later | `PROGRESS.md` (slimmed, D12) + `ARCHITECTURE.md` + `docs/history.md` (spec 43) |
| **B** | A fresh Claude session | `CLAUDE.md` + `PROGRESS.md` + greppable statuses (D4) |
| **C** | **A colleague running fsd on their own region — real, confirmed by the user** | tutorial → how-tos → env reference |
| **D** | An external OSS contributor | **not a target.** 148 commits, one author. No standalone `CONTRIBUTING.md`; contributing guidance is a *section* of `ARCHITECTURE.md`. |

### D2 — Modes B and C are in scope; the *tutorial's* ceiling is Mode A, offline

Colleague C is expected to run at scale. But the Azure prerequisites are **not fsd's to grant** —
VPN, `az login`, an AML workspace, a UAMI with blob RBAC, two ACR image builds. So:

- **Tutorial** — Mode A, fully offline, zero credentials. Guaranteed to succeed (D11).
- **Cloud how-tos** — written for someone who *already has* a working workspace and identity,
  stating that prerequisite in the first paragraph. **"File a ticket with your platform admin"
  is an acceptable first step** (user, 2026-07-29).
- **No Azure onboarding document.** Out of scope for a public MIT repo. The concrete values live
  in `AZURE_INFRA_PRIVATE.md`, handed to a colleague personally or via a private team folder,
  **never public**.

### D3 — ⭐ Every document is either point-in-time or continuously-true

**The central decision; everything else follows from it.**

| Class | Obligation | Members |
|---|---|---|
| **Point-in-time** | **Never substantially edited after the fact.** Carries a status header (D4). Superseded by a *new* document, not by rewriting. | `specs/`, `runbooks/`, `demos/*.md`, `benchmarks/*.md`, `docs/adr/`, `docs/progress-archive.md`, `docs/findings/` |
| **Continuously-true** | Maintained, and mechanically checked where possible (D5/D6) | `README.md`, `ARCHITECTURE.md`, `CONTEXT.md`, `ROADMAP.md`, `docs/tutorial.md`, `docs/howto/*`, `docs/reference/*`, `PROGRESS.md`, the register indexes |

This is PEP 1's rule, adopted wholesale: *"PEPs are no longer substantially modified after they
have reached the Accepted, Final, Rejected or Superseded state"*, and a resolved PEP is *"a
historical document rather than a living specification"*.

**Consequences that bind the rest of this spec:**
- We do **not** edit 30 point-in-time documents to chase a later renaming. This is why the
  GitHub issue numbers are forced to align instead (D8) and why `demos/` is **not** renamed (D10).
- `docs/findings/` entries are point-in-time: a measurement was true on a date.

### D4 — Status header: three values, plus a summary. Process state goes in the index

Every point-in-time document gains a 4-line YAML header:

```yaml
---
status: current | superseded-by-NN | historical
superseded_by: 40          # only when status is superseded-by-NN
summary: One sentence — what a reader needs to decide whether to open this file.
---
```

The three values answer the only question a reader has — *can I trust this as a description of
fsd today?*

| Value | Meaning | Determined from |
|---|---|---|
| `current` | No known contradiction | nothing in `CHANGES.md`/ADRs/later specs contradicts it |
| `superseded-by-NN` | Read NN instead | `CHANGES.md`, existing "Superseded in part" notes, ADR supersessions |
| `historical` | Its subject no longer exists | `satellite_benchmark/` runbooks; CDSE-as-demo-source (spec 40 A1); the retired `mp.Pool` (ADR 0015) |

**`implemented` / `awaiting implementation` is deliberately excluded** — it is *process* state, it
is already stale on three files, and a hand-edited header is a field that gets forgotten. It moves
to the **regenerated index** (`specs/README.md`, `runbooks/README.md`), where it sits next to the
implementation evidence (ADR, test file, or "not implemented"). `runbooks/README.md` already does
this and says it is *"the map until the planned C4-model docs refactor (TODO #55) replaces it"* —
this replaces it in kind.

**No `unverified` fourth value** (user, 2026-07-29). On 42 files it would land on the majority,
tell the reader nothing, and reduce the exercise to a shrug. `current` is a falsifiable claim that
can be corrected.

**Dates, sign-off records and model/effort notes are excluded from the header.** Git has them, and
each would be a future stale line.

### D5 — Maintenance is tiered: tested, dated, or one narrow rule

A continuously-true document needs a mechanism, not good intentions.

| Tier | Mechanism | Applies to |
|---|---|---|
| 1 | **Tested** — `tests/test_docs.py` (D6) | env-var table, links, README verbs, status headers |
| 2 | **Dated** — `Last verified: <date> @ <commit>` + a re-verification runbook | `docs/tutorial.md`, `docs/howto/*` (need network/Azure) |
| 3 | **Ruled** — one `CLAUDE.md` line | adding/renaming a public verb or an `AZ_*` variable requires the doc edit in the same change |

Tier 3 is deliberately **one narrow rule**; broad documentation rules are the ones that get
ignored. **No generated API reference** — fsd has no docs toolchain, no CI to publish it, and
three readers; it would rot differently.

There is **no CI** (`.github/workflows` does not exist), so tier 1 lands in `pytest`, which is
run every session. That is stricter than CI would be, and it is intentional: **docs can fail the
suite.**

### D6 — `tests/test_docs.py`: four assertions

1. **Variable parity** — every `AZ_*` in `env.example.sh` appears in `src/` or `runbooks/`, and
   vice versa. Permanently kills the drift that produced ~45 variables with four near-duplicate
   spellings (`AZ_ARCHIVE` / `AZ_ARCHIVE_ROOT` / `AZ_ARCHIVE_PATH` / `AZ_ARCHIVE_CATALOG`).
2. **Links resolve** — every relative markdown link in `docs/` and the root points at a file that
   exists.
3. **README verbs exist** — every `fsd.<verb>` in the README quickstart exists in `fsd.__all__`
   with the parameters shown. *(This assertion alone would have caught the current stale README.)*
4. **Headers well-formed** — every `specs/`+`runbooks/` file parses as D4, and every
   `superseded_by` names a file that exists.

Scoped deliberately narrowly, following matklad's maintenance argument: `ARCHITECTURE.md` should
**name** modules and types rather than deep-link them, leaving the reader to symbol-search, so
assertion 2 covers document links only — not code references.

### D7 — Config seam: a template plus a reference, and the private doc mirrors it

**Problem:** ~45 distinct `AZ_*` variables across the runbooks with no canonical list. Every
documentation defect that cost a run this week was of this class — an install line missing three
extras, a missing image-rebuild recipe, an `export VAR="$(az …)"` that silently assigned an error
string.

**Decision:**
- **`env.example.sh`** at the repo root — every variable named, values blank, comments pointing at
  the private doc. C copies it to `env.local.sh` (gitignored) and `source`s it. A missing value is
  one visible blank line, not an absent export five runbooks deep.
- **`docs/reference/environment.md`** — the canonical table: name, meaning, where the value comes
  from (decode ring / `az` query / your choice), and **a verification command per row**.
- **`AZURE_INFRA_PRIVATE.md` is restructured by Claude to mirror `env.example.sh` line for line**
  (user, 2026-07-29). It already has the right shape — a "Placeholder → concrete" decode ring for
  `AZURE_INFRA.md` — so this extends that contract to the variable list. Handing a colleague the
  private doc becomes *"fill in these blanks"*, not *"read this and infer"*.
- **Real config support in fsd (`fsd.toml`) is filed as an issue, not built here.** It is the
  actual fix and it is a code change with its own spec.

The ~45 variables with duplicates are a **design smell**, not merely an undocumented one. Writing
them down faithfully makes the mess legible; consolidating first would put this whole refactor
behind a code change.

### D8 — `TODO.md` → 62 **number-aligned** GitHub issues

**Constraint that drives this:** there are **448 `TODO #NN` cross-references across 30+ files** —
specs, runbooks, ADRs, `PROGRESS.md`, `CHANGES.md`, the demo write-ups. `TODO.md` is numbered
**1–62 with zero gaps**.

**Decision:** create issues **strictly in order 1 → 62, including all 29 already-closed rows**
(create, then immediately close). GitHub uses **one shared counter per repository for issues, pull
requests *and* discussions**, and this repo has never had any of the three — so #N lands on TODO
#N exactly, all 448 references resolve for free and permanently, and `gh issue view 47` becomes
the canonical way to read TODO #47.

Rejected alternatives: accepting an offset plus a 62-row mapping table (a translation layer
forever, to dodge a one-time cost); rewriting the 448 references (would edit 30 point-in-time
documents — forbidden by D3).

Benefit not anticipated when this was sized as "29 rows retired": **the 29 closed rows stop being
deletions.** They become closed issues — searchable, linkable, full text intact. Several are
story-grade for spec 43 (one reads *"✅ CLOSED, but its ROOT CAUSE WAS WRONG — ❌ RETURNED"*).

**Three binding conditions:**
1. **Pre-flight, immediately before creating:** `gh issue list --state all`, `gh pr list --state
   all`, **and** `gh api repos/nikhilsrajan/fsd/discussions` (the counter is shared with
   discussions) must all be empty. If any is not, alignment is impossible → fall back to the
   mapping table. **No partial attempt.**
2. **Strictly sequential creation, never parallel.** Concurrent creates can race, and a misnumber
   is unfixable — GitHub will not renumber. Verify each returns the expected number and **halt on
   the first mismatch.**
3. **The user reviews a manifest file before any issue is created** — all 62 entries in order:
   target number, title, labels, milestone, state, body.

**Labels** by area (`datacube`, `download`, `cloud`, `storage`, `stac`, `docs`, `perf`) plus
`blocked`. **Milestones** mapped to the ROADMAP P-phases.

`TODO.md` becomes a **~10-line stub** pointing at Issues and `docs/findings/` — not deleted,
because 448 references name it. **`CLAUDE.md` is edited in the same phase**, since it currently
names `TODO.md` as a living register to keep current.

**The repo is public: an issue is a publication.** Nothing from `AZURE_INFRA_PRIVATE.md` goes into
an issue body. (Existing `TODO.md` content is already public, so the migration leaks nothing new.)

### D9 — One fact, one home

| Topic | Single home | Everyone else |
|---|---|---|
| Terminology | `CONTEXT.md` | link |
| Lasting decisions + why | `docs/adr/` | link |
| Code map, invariants, modes, driver-vs-node | **`ARCHITECTURE.md`** (new) | `ROADMAP.md` §2.1/2.2 **shrink to a pointer** |
| Where fsd is *going* | `ROADMAP.md` | link |
| Azure ground truth (placeholders) | `AZURE_INFRA.md` | link |
| Azure concrete values | `AZURE_INFRA_PRIVATE.md` (private) | **never** |
| Variable names + verification | `docs/reference/environment.md` + `env.example.sh` | demo docs link, stop restating |
| First successful local run | `docs/tutorial.md` | extracted from `E2E_AUSTRIA.md` §3–5 |
| Task recipes | `docs/howto/*` | extracted from `E2E_AUSTRIA_AML.md` §8 + runbooks |
| Measured findings | `docs/findings/*` | TODO #59/#61 and `E2E_AUSTRIA_AML.md` §6 link to it |
| How *we* work | `CLAUDE.md` | unchanged |
| What happened and why | `docs/history.md` (spec 43) | — |

`ARCHITECTURE.md`'s **invariants** section follows matklad's observation that *"important
invariants are expressed as an absence of something"* — which describes fsd's central rules
exactly: no module opens paths outside `fsd.storage` (except documented rasterio/GDAL VSI reads);
no `boto3`; the unit-of-work never knows about AML; fsd never trains a model.

### D10 — The demo gap is three artifacts, not one document

The user's reclassification (2026-07-29): *"a true demo doc to me is not simply run, but something
people can read and follow and write their own demos with."* Correct, and §1.1(3) proves it
quantitatively.

| Artifact | What it is | Reader | May fail? |
|---|---|---|---|
| **`examples/*.py`** | Minimal, readable, copy-paste scripts. No timing, resume, signal handling or plotting. ~60–80 lines, pure verb composition. | anyone | n/a |
| **`docs/tutorial.md`** | Narrates one example on **fixed** data. Teaches the mental model. | first-timer | **must not** |
| **`docs/howto/your-own-region.md`** | "Now point it at your region" — what to change, sizing, cross-UTM, diagnosis. From `E2E_AUSTRIA.md` §4+§9. | someone who finished the tutorial | yes, and says how to diagnose |

This is Diátaxis's tutorial/how-to split, adopted because its stated reason applies here exactly:
*tutorials are learning-oriented and how-to guides task-oriented*; a tutorial promises *"if the
reader follows those steps, they'll arrive at a successful conclusion"* whereas *"a how-to guide
cannot promise safety"*; in a tutorial *"responsibility lies with the teacher"*, in a how-to *"the
user has responsibility"*. `E2E_AUSTRIA.md` is these two fused, which is why it went stale as
instructions.

**`demos/` is NOT renamed.** It is misnamed — it is a benchmark suite, and `benchmarks/` exists —
but renaming churns references across point-in-time documents, forbidden by D3. Instead:
`demos/README.md` states plainly that these are **timing harnesses** and their `.md` files are
**benchmark reports**; both `.md` files get `status:` headers and keep their results, timings and
appendices, with prerequisites/env-var/run-it sections replaced by links to the extracted docs.

**Interaction with the deferred spec 40 §7** (rewrite `E2E_AUSTRIA_AML.md` around the new run):
extracting first shrinks §7 to "update the numbers in a report", which is a better outcome than
rewriting a document we are about to gut.

**`CONTEXT.md` gains glossary entries for demo · benchmark · example · tutorial · how-to**, so this
collision cannot recur. It was a terminology failure before it was a documentation failure.

### D11 — The tutorial runs on a committed micro-fixture

**The constraint that forces this:** fsd reads **whole 110 km MGRS-tile granules** (no windowed
reads — `LIMITATIONS.md`; TODO #59's ~3500× amplification). Measured from the real archive:
**~426 MB per granule** (B04 183.8 + B08 187.1 + B8A 51.0 + SCL 4.6 MB); 207 granules = 74 GB
over 4 tiles for Apr–Sep. So a 5 km ROI buys **nothing** on download:

| Config | Granules | Download |
|---|---|---|
| 1 MGRS tile, Apr–Sep, 4 bands | ~52 | ~18 GB |
| 1 MGRS tile, 1 month, B04+B08+SCL | ~9 | ~3.4 GB |
| 1 MGRS tile, 2 weeks, B04+B08+SCL | ~4 | ~1.7 GB |

**There is no real-download configuration that is tutorial-sized.** And two further blockers:
`.gitignore` blanket-ignores `*.tif`/`*.geojson`/`*.parquet`/`*.npy`, and `shapefiles/` lives at
the *workspace* root, outside the repo — so **fsd ships zero data** and a `pip install fsd` user
has no ROI at all. The current README quickstart (`roi="my_roi.geojson"`) quietly assumes you
brought your own.

**Decision: a committed micro-fixture (~13 MB) of real COGs clipped to one grid cell.**

- **Cell `4772924`** — chosen by measurement, not convenience: of 300 cells over `AT_ROI` it holds
  the most labelled fields (**43 fields, 7 crops**). *The user's initial pick, `s2grid=476da24`,
  was checked and rejected: it sits near Vienna (16.03–16.12 E) while every labelled field is
  ~100 km west (14.6–15.5 E), so it contains **zero labels** and cannot exercise the
  training-data step.*
- **Labels collapsed to `maize` / `hemp` / `other`** — the raw distribution is 20 maize, 13 hemp,
  4 alfalfa and four near-singletons; a 7-class split over 43 samples is not trainable. The
  tutorial says so, and says why.
- **Offline ⇒ testable.** This is the deciding argument: the tutorial's own code becomes a pytest
  test, satisfying tier 1 of D5 instead of relying on a `Last verified` stamp. No other option on
  the table gives that.
- **`.gitignore` gains explicit negations** (`!tests/data/tutorial/**`). Precedent:
  `demos/figures/*.png` is committed (3.1 MB).
- **The real download becomes `docs/howto/download-real-imagery.md`**, stating the byte budget up
  front and explaining why a small ROI does not shrink it.

**Copernicus licensing — verified, and it corrects the obvious guess.** The EC Legal Notice grants
free access for *(a) reproduction; (b) distribution; (c) communication to the public; (d)
adaptation, modification and combination*. Because clipping **is** modification, the required
notice is **not** the plain form but:

> `Contains modified Copernicus Sentinel data 2018`

That exact string goes in the fixture directory's `NOTICE` and in the tutorial. A single clipped
tile also means the tutorial does not exercise multi-MGRS-tile merge — acceptable for a tutorial,
noted in the how-to.

**Building the fixture is engineering, not writing, and is carved out to spec 42.** Note **spec 42
amendment A1** (user, 2026-07-30) moves that build **in-region onto an Azure VM sourcing the blob
MPC archive**, which removes the radiometry hazard described there — the MPC archive declares its own
offset, so the fixture's correctness is by provenance rather than by re-derivation.

### D12 — `PROGRESS.md` splits; the archive stays one file

`PROGRESS.md` is two documents fused (§1.1(2)). Deferring `history.md` to spec 43 makes its
38.7k words the **primary archaeology source for a spec not yet written**, so "trim and let git
hold it" is the wrong move — it would push spec 43 into `git log -p` spelunking.

- **`PROGRESS.md`** → a synthesized current-state section + the most recent entry verbatim + a
  pointer. ~2k words instead of 38.7k, read at the start of every session.
- **`docs/progress-archive.md`** → older entries **moved** (not deleted), **one file** (user,
  2026-07-29): it is a log, nobody browses it, and splitting by month invents a meaningless
  boundary. Point-in-time per D3.
- `CLAUDE.md`'s *"Read `fsd/PROGRESS.md` first on any resume"* stays valid and gets cheaper.

The synthesized section is itself continuously-true, but it is the safest case on that list — it
is already rewritten at every session boundary under the spec-24 handoff protocol, so no new
machinery is added for it.

### D13 — Acceptance: only one gate can be automated

The four assertions catch **drift**, never **unreadability or being wrong when followed**.

| Phase | Gate |
|---|---|
| P1 | Claude stamps all 65; **the user picks 10** to spot-check; **>1 wrong ⇒ the batch is redone**, not patched. |
| P2 | The manifest review, before creation. After: 62 issues, 1:1 alignment, 29 closed. |
| P3/P4 | `test_docs.py` covers the variable table. The env reference is proven when someone provisions from scratch without asking a question. |
| P5 | Readable-only. No test exists. Opus review against this spec. |
| P7 | **A cold-start run.** Fresh clone, fresh venv, the tutorial followed *literally* — no improvising, no "obviously they meant" — stopping at the first instruction that does not work. **The user is the test subject** (confirmed 2026-07-30) and lets it fail rather than fixing as they go. Reported as a spec-24 `_result.json`. |

Then the real proof, which Claude cannot run: **the first colleague who uses it** — with one rule
attached: **every place they get stuck becomes an issue, not a verbal fix.** Otherwise the docs
accumulate tribal patches instead of improving.

### D14 — Phasing; two pieces carved out

| Phase | Work | Model | Size |
|---|---|---|---|
| **P1** | Status headers on 42 specs + 23 runbooks + `demos`/`benchmarks` reports; regenerate both indexes | Sonnet@medium | ~1 session |
| **P2** | `TODO.md` → 62 aligned issues (manifest → review → sequential creates); labels + milestones; stub; `CLAUDE.md` edit | Sonnet + user review | ~1 |
| **P3** | Extract TODO #59/#61 + `E2E_AUSTRIA_AML.md` §6 → `docs/findings/` | Sonnet@medium | ~0.5 |
| **P4** | `env.example.sh` + `docs/reference/environment.md` + restructure `AZURE_INFRA_PRIVATE.md` + env verification | Sonnet@medium | ~1 |
| **P5** | `README.md` rewrite + `ARCHITECTURE.md` + contributing section + `ROADMAP.md` §2.1/2.2 shrink + `CONTEXT.md` glossary + `demos/README.md` relabel + D12's `PROGRESS.md` split | Sonnet@medium | ~1 |
| **P6** | **Tutorial micro-fixture — spec 42** | Sonnet, Opus on failure | ~1–2, **risky** |
| **P7** | `examples/*.py` + `docs/tutorial.md` + `docs/howto/*` | Sonnet@medium | ~1.5 |
| **P8** | `docs/history.md` — **spec 43, deferred** | Opus | ~1 |

`tests/test_docs.py` is woven into P1/P4/P5, not a standalone phase.

**P1+P2+P5 are the floor** — they hit all three original complaints, carry the least risk, and
leave the repo strictly better if P6/P7 never happen. **P4 ranks high** because it is the only
phase backed by runs that actually failed.

---

## 3. Target layout

```
README.md              front door: what/who/install/60-second example/links     REWRITE (stale)
ARCHITECTURE.md        code map · invariants · modes · driver-vs-node · C4 dgms  NEW ⭐
env.example.sh         every AZ_* named, values blank                           NEW
CONTEXT.md             + demo/benchmark/example/tutorial/how-to entries          EXTEND
ROADMAP.md             §2.1/2.2 shrink to pointers into ARCHITECTURE.md          EDIT
PROGRESS.md            current state + latest entry + pointer (~2k words)        SPLIT
TODO.md                ~10-line stub → Issues + docs/findings/                   STUB
docs/
  tutorial.md          one guaranteed-to-succeed offline run                     NEW
  howto/               your-own-region · download-real-imagery · run-at-scale ·
                       bundle-your-model · serve-xyz                            NEW (from demos/runbooks)
  reference/
    environment.md     canonical AZ_* table + per-row verification               NEW
  findings/            cloud-overhead (#61) · workload-regimes (#59)             MOVED
  progress-archive.md  older PROGRESS entries, one file                          MOVED
  adr/                 + 5 ADRs from this session                                EXTEND
  history.md           spec 43                                                   DEFERRED
specs/                 + status headers, + regenerated README index              STAMP
runbooks/              + status headers, + regenerated README index              STAMP
demos/                 unchanged content; README relabels as benchmark harnesses RELABEL
examples/              minimal readable scripts (currently 1 file)               GROW
tests/
  test_docs.py         the four assertions                                       NEW
  data/tutorial/       the micro-fixture + NOTICE (spec 42)                      NEW
```

Nothing is deleted. Everything either stays, gains a label, or moves.

---

## 4. ADRs this spec generates

To be written on sign-off, in `docs/adr/`:

| # | Decision | From |
|---|---|---|
| 0022 | Documents are either point-in-time (immutable, statused) or continuously-true (maintained, tested) | D3 |
| 0023 | Point-in-time documents carry a three-value status header; process state lives in a regenerated index | D4 |
| 0024 | The TODO migrates to GitHub Issues with forced number alignment; references are never rewritten | D8 |
| 0025 | One fact, one home — each topic has exactly one owning document | D9 |
| 0026 | demo ≠ benchmark ≠ example ≠ tutorial; the demo gap is three artifacts | D10 |

---

## 5. Risks

| Risk | Mitigation |
|---|---|
| **`current` is a claim Claude infers from absence of contradiction** and may be wrong on a subtly-stale spec | D13's spot-check with a redo-the-batch threshold; `current` is falsifiable, unlike `unverified` |
| **A misnumbered issue is unfixable** | D8 conditions: pre-flight all three counters, strictly sequential, halt on first mismatch |
| **The fixture build may surface builder bugs** | Carved to spec 42 with its own runbook and acceptance criteria; does not gate P1–P5 |
| **Docs failing `pytest` will occasionally be annoying mid-refactor** | Accepted deliberately (D5) — it is the only mechanism with teeth |
| **The plan stalls around P5** | P1+P2+P5 declared the floor; each phase independently shippable |
| **Five polished documents nobody reads** | D13's cold-start run + the colleague rule (stumbles become issues) |
| **Committed ESA pixels in a public MIT repo** | Verified against the EC Legal Notice; exact `Contains modified Copernicus Sentinel data 2018` notice required (D11) |

---

## 6. Best-practice alignment / sources

Per-source credit — what each source specifically contributed.

**Diátaxis — Daniele Procida** ([diataxis.fr](https://diataxis.fr/),
[tutorials vs how-to](https://diataxis.fr/tutorials-how-to/)).
Contributed the **four-mode split that replaced C4 as this spec's organising frame** (tutorial ·
how-to · reference · explanation), and thereby the `docs/` sub-directory structure in §3. Its
tutorial/how-to page supplied the specific reasoning behind **D10 and D11**: *"tutorials are
learning-oriented, and how-to guides are task-oriented"*; a tutorial promises *"if the reader
follows those steps, they'll arrive at a successful conclusion"* while *"a how-to guide cannot
promise safety"*; and the responsibility asymmetry — in a tutorial *"responsibility lies with the
teacher"*, in a how-to *"the user has responsibility"*. That last claim is **why D11 commits a
fixture**: guaranteed success requires the teacher to control the data, which a live download
cannot provide. Diagnosing `E2E_AUSTRIA.md` as a tutorial/how-to fusion is a direct application.

**"ARCHITECTURE.md" — Aleksey Kladov (matklad), 2021-02-06**
([post](https://matklad.github.io/2021/02/06/ARCHITECTURE.md.html)).
Contributed **the single-file codebase-map convention itself** (D9's `ARCHITECTURE.md`), against
this spec's earlier five-file C4 plan; the **"codemap"** notion of a coarse module map answering
*"where's the thing that does X?"* — *"a map of a country, not an atlas of maps of its states"*;
the claim that this mental map takes **~10× longer to discover than to read**, which is the
justification for the file existing at all; and two specifics that shaped decisions —
*"important invariants are expressed as an absence of something"* (⇒ D9's invariants section:
fsd's rules are all absences — no I/O outside the storage seam, no `boto3`, the unit-of-work never
knows AML), and **name modules rather than deep-linking them, letting readers symbol-search**
(⇒ D6 assertion 2 is scoped to document links only, not code references).

**PEP 1 — Python Enhancement Proposal Purpose and Guidelines**
([peps.python.org/pep-0001](https://peps.python.org/pep-0001/)).
Contributed **the authority for D3 and D4**. Its status vocabulary (Draft · Active · Accepted ·
Provisional · Deferred · Rejected · Withdrawn · Final · Superseded) is the model fsd's `specs/`
were already imitating without a Status field. Two claims are load-bearing: *"PEPs are no longer
substantially modified after they have reached the Accepted, Final, Rejected or Superseded
state"* — adopted verbatim as D3's rule that point-in-time documents are never edited after the
fact, which is in turn why D8 forces issue numbers to align and D10 declines to rename `demos/`;
and that a resolved PEP is *"a historical document rather than a living specification"*, which is
exactly the point-in-time / continuously-true distinction. PEP 1's practice of superseding rather
than editing supplied `superseded-by-NN`.

**C4 model — Simon Brown** ([c4model.com](https://c4model.com/),
[containers](https://c4model.com/abstractions/container)).
Contributed what **survives** of TODO #55's original framing (D0): Context / Container /
Deployment as `ARCHITECTURE.md`'s section outline, and the existence of **supplementary diagram
types — system landscape, dynamic, deployment** — which is why fsd's *deployment* and *dynamic*
views (Modes A/B/C; the 8-step run) rank above a Component diagram here. It also supplied a trap
this spec explicitly avoids: the container page opens **"Not Docker!"** and notes *"it's
unfortunate that containerisation has become popular, because many software developers now
associate the term 'container' with Docker"* — decisive for fsd, whose AML Docker Environments are
**not** its C4 containers (driver · node · blob · catalog are).

**Legal notice on the use of Copernicus Sentinel Data and Service Information — European
Commission, DG GROW** ([PDF](https://sentinels.copernicus.eu/documents/247904/690755/Sentinel_Data_Legal_Notice)).
Contributed **the legal basis for D11's committed fixture** and a correction. It grants free
access for *"(a) reproduction; (b) distribution; (c) communication to the public; (d) adaptation,
modification and combination with other data and information"*, so redistributing a clipped subset
in a public MIT repo is permitted. Critically, it distinguishes the attribution notices: plain
distribution requires *'Copernicus Sentinel data [Year]'*, but **where the data "have been adapted
or modified"** the notice must be *'Contains modified Copernicus Sentinel data [Year]'*. Since
clipping is modification, D11 requires the **modified** form — which the plain-reading guess would
have got wrong. Read from the primary EC document, not a summary, because it is a legal claim.

**GitHub community discussion #69759 — "How does GitHub assign numbers to issues, pull requests
and discussions?"** ([discussion](https://github.com/orgs/community/discussions/69759)).
Contributed **the mechanism D8 depends on**: a repository uses a **single shared counter** across
issues, pull requests **and discussions**, starting at 1. This is what makes forced alignment
possible at all, and it tightened D8's pre-flight condition — the original plan checked only
issues and PRs, and this source added **discussions** as a third counter that must also be empty.

---

## 7. Deferred / not in scope

- **Spec 42** — the micro-fixture build (P6).
- **Spec 43** — `docs/history.md` (P8), after P1/P2 do its archaeology.
- **`fsd.toml` config support** — filed as an issue in P2 (D7).
- **Consolidating the ~45 `AZ_*` variables** — filed as an issue; documented here, not fixed.
- **A generated API reference** — rejected (D5).
- **An Azure onboarding document** — out of scope (D2); an access problem, not a docs problem.
- **Spec 40 §7** (rewrite `E2E_AUSTRIA_AML.md`) and **TODO #62** (local re-run) — unchanged and
  independent; the docs work does not wait on either (user, 2026-07-29).
- **Renaming `demos/` → `benchmarks/`** — rejected (D10/D3).
- **A standalone `CONTRIBUTING.md`** — rejected (D1); a section of `ARCHITECTURE.md` instead.
