# PROGRESS — fsd

**Resume anchor.** Read this, then `specs/00-overview.md`. Older entries moved to
[`docs/progress-archive.md`](docs/progress-archive.md) (spec 41 D12) — this file is the *current*
state plus the most recent entry, not the log.

_Last updated: 2026-07-30 (✅ P5 DONE **and reviewed** — the Opus review found 8 things, all fixed; spec 41's floor is complete)_

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
| **Docs** | spec 41 P1–P5 done; **P6 (tutorial fixture) and P7 (tutorial + how-tos) open** |
| **Deferred work** | **GitHub Issues #1–#62**, number-aligned with the old `TODO.md` rows |
| **Open decision** | rslearn Plan B vs Plan C (`RSLEARN_COMPARISON.md`), untouched |

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

**Next up:** spec 41 **P6** — build spec 42's committed tutorial micro-fixture (`runbooks/43`),
which unblocks **P7** (`docs/tutorial.md` + `docs/howto/*`). P6 is the risky one: it needs an
in-region Azure VM.

---

## Most recent entry

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

**Gate after the fixes:** `pytest -q` **648 passed / 84 skipped** in a worktree (647 baseline + the
new test), `ruff check src/ tests/ demos/` clean.

### ⚠️ Still open — two P1 findings, inherited

Neither is P5's doing; both belong to whoever touches `test_docs.py` next:

- **`superseded_by` is ambiguous across the `specs/`↔`runbooks/` namespaces.** `runbooks/42`'s
  `superseded_by: 41` resolves to `specs/41-docs-refactor.md` because the test searches `specs/`
  first — it **passes on the wrong file**; the intended target is
  `runbooks/41-recover-aml-job-timings.md`.
- **The two register indexes disagree on link style** — `specs/README.md` uses markdown links,
  `runbooks/README.md` bare backticks, so assertion 2 never sees the run-book index.
