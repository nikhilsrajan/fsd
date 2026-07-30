# PROGRESS — fsd

**Resume anchor.** Read this, then `specs/00-overview.md`. Older entries moved to
[`docs/progress-archive.md`](docs/progress-archive.md) (spec 41 D12) — this file is the *current*
state plus the most recent entry, not the log.

_Last updated: 2026-07-30 (✅ P5 DONE — README + ARCHITECTURE + the PROGRESS split; spec 41's floor is complete)_

## Where things stand

**What fsd does today, proven on real infrastructure:** download → datacube → flatten → train →
inference, run both locally and fanned out across an Azure ML cluster. The 2026-07-29 cluster demo
(`demos/e2e_austria_aml.py`, run `20260729T132222Z`) completed unattended in **18.8 min, 8/8 steps,
97 jobs, 213 MPC granules, 300 grid cells → 300 output COGs + STAC + a merged map**. That run *is*
the validation ROADMAP P3 and P4 were waiting on.

**Current work: the docs refactor (spec 41).** P1–P5 are done; see the entry below and the archive.
P6/P7 remain.

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
| **`PROGRESS.md`** (split, D12) | **3,691 → 100 lines.** A synthesized current-state section + the most recent entry + pointers |
| **`docs/progress-archive.md`** (new) | 60 older entries **moved verbatim**, one file, `status: historical` |
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

### ⚠️ The one outstanding acceptance item

**Spec 41 P5's gate is "readable only — no test exists. Opus review against this spec."** That
review **has not happened**: the session that wrote P5 cannot be its reviewer. The precedent is the
P1 review, which found **6 defects** in work its own session had declared green — including a
systemic one (process state re-entering 51 `summary:` lines) and two stamped files that were
gitignored.

**What a reviewer should actually do** (the P1 review's most useful move was the independent
spot-check, not re-reading the diff):

1. Read `ARCHITECTURE.md` and `README.md` **as a newcomer**, against spec 41 D0/D9/D10 — is the
   code map true, are the 8 invariants really invariants, does the README's 60-second example run?
2. Check the **`PROGRESS.md` split (D12)** did not lose or reorder an entry — `docs/progress-archive.md`
   should hold every pre-P5 entry verbatim, newest-first.
3. Confirm the D6 assertion 2 **scope call** was right: link checking covers only the root docs and
   the maintained `docs/` tree, deliberately excluding point-in-time corpora (D3 forbids editing
   those to fix a rotted link). That call was mine, not the spec's.
4. **Two review findings from P1 are still open** and belong to whoever touches this next:
   `superseded_by` is ambiguous across the `specs/`↔`runbooks/` namespaces (`runbooks/42`'s `41`
   resolves to `specs/41-docs-refactor.md`, and the test passes on the wrong file); and the two
   register indexes disagree on link style (`specs/README.md` uses markdown links,
   `runbooks/README.md` bare backticks, so assertion 2 never sees the run-book index).
