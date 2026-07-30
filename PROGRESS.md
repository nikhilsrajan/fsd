# PROGRESS — fsd

**Resume anchor.** Read this, then `specs/00-overview.md`. Older entries moved to
[`docs/progress-archive.md`](docs/progress-archive.md) (spec 41 D12) — this file is the *current*
state plus the most recent entry, not the log.

_Last updated: 2026-07-30 (P6 step 1 **reviewed** — 8 findings, 2 blocking, all fixed; spec 42 amendment **A2 is proposed and needs sign-off** before this merges)_

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

**Next up:** sign off **spec 42 amendment A2** (§8 — moves A1's source-equality check off the
offline suite and onto the generator's `_result.json`), then merge `worktree-p6-build-fixture` into
`main`. After that the user runs `runbooks/43-build-tutorial-fixture.md` on an Azure ML compute
instance inside the `rise` VNet (Steps 1-6), pastes back the `_result_step*.json` files, and commits
the real fixture (Step 7). That lands spec 42, closing spec 41 **P6** and unblocking **P7**
(`docs/tutorial.md` + `docs/howto/*`).

---

## Most recent entry

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

**Resolution — spec 42 amendment A2 (⏳ PROPOSED, needs sign-off).** The source-equality gate moves
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

**Not merged yet** — A2 is a change to a signed-off acceptance criterion, so it waits on the user's
sign-off (working contract: spec sign-off before implementing against it). Everything else is done
and green on the branch.

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
