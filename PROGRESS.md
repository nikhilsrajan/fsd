# PROGRESS — fsd

**Resume anchor.** Read this, then `specs/00-overview.md`. This file is the *current state* plus the
most recent entry — **not the log.** Older entries are moved verbatim to
[`docs/progress-archive.md`](docs/progress-archive.md) (spec 41 D12; split re-run 2026-09-03 for
[#94](https://github.com/nikhilsrajan/fsd/issues/94)). For the narrative — why the code looks like
this — read [`docs/history.md`](docs/history.md).

> **Keep this file small.** D12's target is **~2k words**. It has now blown past that twice, both
> times by accreting `_Previously:_` blocks that nobody deleted. When you add an entry, move the one
> below it into the archive. Entries are **moved, never rewritten** ([ADR 0022](docs/adr/0022-documents-are-point-in-time-or-continuously-true.md));
> the two sections above and below the entry are continuously-true and *are* rewritten.

## Where things stand

**What fsd does today, proven on real infrastructure:** download → datacube → training data →
inference → per-output COGs + STAC, run on a laptop and fanned out across an Azure ML cluster —
and, since **2026-09-02**, driven from a *separate consumer repository* with fsd installed as a
dependency rather than checked out. That run was the goal stated on day one, and it is met.

| | state |
|---|---|
| **Pipeline** | v1 core complete (**Sentinel-2 L2A only**, CDSE + MPC), proven local and on AML |
| **Scale-out** | AML runner seam; download, build, flatten and inference all fan out. Reference run `20260729T132222Z`: 18.8 min, 8/8 steps, 97 jobs, 213 granules, 300 grid cells → 300 COGs + STAC + a merged map |
| **Serving** | tier-1 (pre-styled XYZ) and tier-2 (pgSTAC + titiler-pgstac) both validated |
| **Docs** | spec 41 P1–P7 done; `docs/history.md` written and approved 2026-09-02; `src/` changelog comments swept (#85, refs 1,187 → 92) |
| **Current work** | the **notebook-usability sprint, phase 2** — see THE ORDER below |
| **Deferred work** | **GitHub Issues**, number-aligned with the old `TODO.md` rows (`gh issue list`) |
| **rslearn** | **decision CLOSED 2026-07-31** — no rslearn for download; rslearn-on-Azure is a separate, unstarted project. `spike/rslearn` stays unmerged |

**What is not met, stated plainly:** the pipeline is **S2 L2A only** (the `Source` abstraction is
implied but does not exist); the **radiometry debt** is fixed in code but still live in the Austria
test archive (cubes ~1000 DN high — fine for infrastructure, not for science); the cluster's
dominant cost is **warm-up, not work** (36 % of the demo run) and nothing has been done about it;
and **no tag has been cut** — deliberately, until the asset layout stops moving.

**Where to look:**

| you want | read |
|---|---|
| how the code is laid out | [`ARCHITECTURE.md`](ARCHITECTURE.md) |
| how we got here | [`docs/history.md`](docs/history.md) |
| where fsd is going | [`ROADMAP.md`](ROADMAP.md) |
| what a term means | [`CONTEXT.md`](CONTEXT.md) |
| why a decision was made | [`docs/adr/`](docs/adr/) |
| a measured result | [`docs/findings/`](docs/findings/) |
| an env variable | [`docs/reference/environment.md`](docs/reference/environment.md) |
| open work | `gh issue list` |
| what happened on a given day | [`docs/progress-archive.md`](docs/progress-archive.md) |

## THE ORDER — four tasks, and what follows each (user, 2026-08-28)

The user's standing instruction: **record what comes after finishing a task, so it is not
forgotten at the boundary.** Do not reorder without saying so.

| # | task | done when | → then |
|---|---|---|---|
| ~~**1**~~ | ~~**[#92](https://github.com/nikhilsrajan/fsd/issues/92)** — AZ_ROOT cleanup~~ | **DONE 2026-08-28** — `3a968dc` / `ee7277b`, issue closed + pushed | → **2**, now current |
| ~~**2**~~ | ~~**The consumer-repo run**~~ | **MEASUREMENT DONE 2026-09-02** — `[collect]` 26 s / `[stac]` 10 s vs the 616 s / 161 s baseline; spec 57 §9 step 5 discharged. Spec 56 §9 step 10 discharged by a live `environment_exists` probe | → **3**, now current; **#80 + #82 unblocked** |
| ~~**3**~~ | ~~**[#55](https://github.com/nikhilsrajan/fsd/issues/55)** — spec 43 → `docs/history.md`~~ | **DONE + CLOSED 2026-09-02** — approved, merged, `ARCHITECTURE.md` refreshed alongside | → **4** |
| ~~**4**~~ | ~~**[#85](https://github.com/nikhilsrajan/fsd/issues/85)** — trim the changelog out of `src/` comments~~ | **DONE + CLOSED + PUSHED 2026-09-03** — refs **1,187 → 92 (−92%)**, `816823c` + `c68adba`; swept in one pass, not one package per session, and **extended** to `image/`/`aml/`/`registry/`/`config.py`/`cli.py` | → #93 per this table; **the user chose #94 instead** |

**⚠️ The order changed after step 4 (user, 2026-09-03).** This table said #93 next; the user picked
**#94** (the `PROGRESS.md` split). #93 is not dropped — it keeps the notebook-front-door proposal
and is still the front-door work. Recorded here rather than silently re-sequenced, per the standing
instruction above.

| # | task | done when | → then |
|---|---|---|---|
| ~~**5**~~ | ~~**[#94](https://github.com/nikhilsrajan/fsd/issues/94)** — re-run the `PROGRESS.md` split~~ | **DONE 2026-09-03** — 1,737 lines moved verbatim to the archive; this file **19,970 → 1,762 words**; four defects retired, one of them a test that never ran | → **6**, now current |
| **6** | **[#93](https://github.com/nikhilsrajan/fsd/issues/93)** — **CURRENT.** Front door: README → tutorial → how-tos | **wants its own spec** (touches spec 41 D1's audience table + ADR 0026) | → the tag, which is still LAST |

**Rider on step 2 — do not lose these.** #80 (snakemake → `[local]`, s3fs → `[s3]`; zero code
change, −53 packages / −111 MB) and #82 (cut + push `v0.1.0`) both belong **inside** `v0.1.0`, and
the **tag is LAST** — cut only once the consumer notebook actually runs (user, 2026-08-26: a tag
pins the dependency set *and* the asset layout, and both were still moving). #80 may land any time
before the tag; it cannot alter runtime behaviour, so it does not require re-running step 2.
**#79** is wanted-not-blocking; **#81 must not block** (numba is a real top-level import).

**Why #92 goes first, not after the run:** it edits `notebooks/e2e_austria_aml.ipynb`'s prose and
`docs/howto/run-at-scale.md`'s config example — cheaper to fix before the run than to re-touch a
notebook that has just been validated.

## Most recent entry

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
