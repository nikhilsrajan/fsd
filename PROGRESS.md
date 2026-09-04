# PROGRESS — fsd

**Resume anchor.** Read this, then `specs/00-overview.md`. This file is the *current state* plus the
most recent entry — **not the log.** Older entries are moved verbatim to
[`docs/progress-archive.md`](docs/progress-archive.md) (spec 41 D12; split re-run 2026-09-03 for
[#94](https://github.com/nikhilsrajan/fsd/issues/94)). For the narrative — why the code looks like
this — read [`docs/history.md`](docs/history.md).

## Resuming after a break — start here

**One thing is in flight: spec 58 P1, implemented and awaiting review.** As of **2026-09-05**
worktree `spec58-p1` (branch `worktree-spec58-p1`) holds a complete, green P1 implementation, not
yet merged to `main` — the next step is an Opus review pass (standards + spec against
`specs/58-collection-agnostic-verbs.md` §5's acceptance criteria), then `git merge --no-ff` +
prune the worktree, per the standing worktree-merge-prune practice. `main` itself is otherwise
clean and unmerged-branch-free except `spike/rslearn` (intentional). **`v0.1.0` is cut and pushed.**

1. Read this file top to bottom. It is ~2k words by design; it is the whole picture.
2. If picking up spec 58 P1: review the worktree's diff against `main`, re-run
   `.venv/bin/python -m pytest -q` and `.venv/bin/ruff check src tests demos examples` inside it,
   then merge if clean.
3. `gh issue list` — the open work. Nothing here is blocked on a decision you have to remember.
4. Otherwise pick from **THE ORDER** below, which is still sequenced.

**Before trusting anything below, re-verify rather than assume.** Every dated claim was true when
written. Cheap checks (on `main`, pre-merge; the P1 worktree's own numbers are in "Most recent
entry" below): `.venv/bin/python -m pytest -q` (expect **1083 passed / 103 skipped**),
`.venv/bin/ruff check src tests demos examples`, `git log --oneline -5`, `gh issue list`.
A quiet stretch in the git log is a break, not a stall — do not read it as a problem to diagnose.

### ⚠️ Two obligations OUTSIDE this repo, still open

These will not fail loudly until something real runs, so they are recorded here rather than in an
entry that gets archived:

1. **The consumer repo `rise/` will break on its next cluster run.** It installs
   `fsd[azure,aml,mpc,grid]` and builds its image with `extras=("azure","mpc")`. Since **#80**,
   **both need `local` added** — the AML in-job entrypoints run the same Snakemake orchestration a
   laptop does, so without it the image builds fine and the dispatch fails ~30 min in. The image
   digest changes, so **the images must be rebuilt**, not just re-tagged.
2. **The workspace `CLAUDE.md` dev line still reads `pip install -e ".[dev]"`.** `pytest` passes on
   that, but `docs/tutorial.md` and any `runner="local"` work now need `.[dev,local]`. That file is
   outside the repo, so no commit here can fix it.

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
| **Release** | **`v0.1.0` cut 2026-09-04.** SemVer 0.y.z on purpose — the `Source` abstraction does not exist and S1 is coming, so the API will break |
| **Deferred work** | **GitHub Issues**, number-aligned with the old `TODO.md` rows (`gh issue list`) |
| **rslearn** | **decision CLOSED 2026-07-31** — no rslearn for download; rslearn-on-Azure is a separate, unstarted project. `spike/rslearn` stays unmerged |

**What is not met, stated plainly:** the pipeline is **S2 L2A only** (the `Source` abstraction is
implied but does not exist); the **radiometry debt** is fixed in code but still live in the Austria
test archive (cubes ~1000 DN high — fine for infrastructure, not for science); the cluster's
dominant cost is **warm-up, not work** (36 % of the demo run) and nothing has been done about it;
and the pipeline still **dispatches on a hardcoded pair of source names**. The tag is no longer
outstanding: `v0.1.0` was cut 2026-09-04 once both things a tag pins — the dependency set and
the asset layout — had stopped moving.

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
| ~~**6**~~ | ~~**[#80](https://github.com/nikhilsrajan/fsd/issues/80)** — snakemake/s3fs → extras~~ | **DONE 2026-09-04** — core 689 → 578 MB; **AML node images need `local` and must be rebuilt** | → **7** |
| ~~**7**~~ | ~~**[#82](https://github.com/nikhilsrajan/fsd/issues/82)** — cut + push `v0.1.0`~~ | **DONE 2026-09-04** — the tag is cut | → **8** |
| **8** | **[spec 58](specs/58-collection-agnostic-verbs.md)** — **CURRENT.** Collection-agnostic verbs: P1 contract → P2 `sentinel-1-rtc` → P3 HLS | **P1 IMPLEMENTED 2026-09-05** (worktree `spec58-p1`, unmerged — awaiting Opus review); pytest+ruff clean; next: review → merge → re-download run-book → P2 | → **9** |
| **9** | **[#93](https://github.com/nikhilsrajan/fsd/issues/93)** — Front door: README → tutorial → how-tos | **wants its own spec** (touches spec 41 D1's audience table + ADR 0026) | → `v0.2.0` is cut after spec 58 P3 |

**⚠️ The order changed again (user, 2026-09-04).** #93 was step 8 and CURRENT; the user promoted
**spec 58** ahead of it after the grilling session. Reason: spec 58 rewrites four verb signatures,
the README and the tutorial, so writing the front door first would document an API about to break
twice. Recorded rather than silently re-sequenced, per the standing instruction.

**Rider on step 2 — DISCHARGED 2026-09-04.** #80 and #82 both landed **inside** `v0.1.0`, as
the rule required. The rule itself (user, 2026-08-26): a tag pins the dependency set *and* the
asset layout, so it waits until both stop moving. **Layout** stopped on 2026-09-02 (the
consumer-repo run); **dependencies** stopped with #80. **#93 was dropped from the tag's
prerequisites** — it is documentation, and docs pin nothing.
**One correction to the rider's own text:** it said #80 *"cannot alter runtime behaviour"*. It
does — an AML node image without `[local]` now fails mid-dispatch. The rider was written from
the issue's "never imported by `src/fsd/`", which is true and still misleads, because the in-job
entrypoints call the local runner. **#79** is wanted-not-blocking; **#81 must not block**.

**Why #92 goes first, not after the run:** it edits `notebooks/e2e_austria_aml.ipynb`'s prose and
`docs/howto/run-at-scale.md`'s config example — cheaper to fix before the run than to re-touch a
notebook that has just been validated.

## Most recent entry

_Last updated: 2026-09-05 (**SPEC 58 P1 IMPLEMENTED — the contract lands, S2 L2A only.**
Built in worktree `spec58-p1` (branch `worktree-spec58-p1`), not yet merged — **awaiting Opus
review** per the standing implementation-note order (P1 → review → merge `--no-ff` → prune,
then the re-download run-book, then P2). `pytest -q` **1093 passed / 102 skipped / 0 failed**
(excludes `test_tutorial_fixture.py`'s 4 real-fixture tests, run separately: also green, ~2.5
min); `ruff check src tests demos examples` clean. All 18 D-decisions D1-D16 implemented except
D9/D10/D17 (P2-scoped, correctly deferred) and D7's bitmask *implementation* (P3-scoped; the
`bits` field + version bump landed now, per spec)._

_**What changed, concretely:** `fsd/collections/` registry (`register`/`get`); `SourceDeclaration`
→ `CollectionDeclaration` (D2); 7 new declaration fields + `FSD_DECLARATION_VERSION` 2 (D5-D10);
catalog `satellite`→`collection`, `+scale`, `+properties`, no read-time shim (D12); `download`'s
default `source` → `"mpc"`, `+collection` on all four verbs, `-scl_mask_classes` everywhere (D1/D3);
`params_key`/`window_folder_segment` keyed on `collection` + a declaration digest, not mask classes
(D4); `create_datacube.setup` writes `<run_folderpath>/declaration.json`, every node reads it, none
consult the registry (D13); `source×collection` validity + `reference_band∉bands` + a missing-band
raise, all naming what's wrong (D15/D11/D8); band-alias canonicalization so `bands=["B8A"]` and
`bands=["nir08"]` hit the same cube path (D8, AC5); `apply_offset` clips to the loaded array's own
dtype range, not a hardcoded uint16 one (D5.2)._

_**One real bug found and fixed mid-implementation, not in the spec:** the first S2 declaration draft
set `radiometry_bands=None` ("all bands get the offset") — which would have radiometrically offset
SCL (a classification, not a DN) the moment any collection declared a non-zero offset. Caught by
`tests/test_mpc.py::test_transfer_and_stamp_one_never_offsets_mask_band`, which is exactly the kind
of existing-fixture regression AC3 exists to catch. Fixed: S2's `radiometry_bands` is now the
explicit reflectance-band tuple (mirrors the old `_is_reflectance` regex exactly, as declared data
instead of a global pattern)._

_**AC5 (band-alias → same path) was not free** — it required adding canonicalization at every entry
point that touches `bands` before the digest sees it (`create_datacube.setup`/
`build_shortfall_only`/`run_create_datacube`, and `api.py`'s three verbs' adapter-required-bands
checks), not just at the source-module asset-selection layer the spec text focuses on. Recorded here
because a narrower reading of D8 would have shipped AC5 broken._

_**One real-data fixture required migration, not just a test-signature fix:**
`tests/data/tutorial/catalog.parquet` (the tutorial's real, checked-in fixture) was stamped with a
declaration whose `scale`/`radiometry_bands`/`band_aliases` were pre-spec-58 dataclass defaults, not
real S2 facts — D14's new artifact-fact-mismatch guard correctly caught the disagreement.
Migrated in place (column rename + 2 new columns + re-stamp with the real
`S2_L2A_DECLARATION`, no re-download — same technique `restamp_cli` already used) rather than
regenerating from the VM, since only metadata needed to change, not the granules._

_**Scoped out of P1, documented, not silently dropped:** the AML `download` dispatch path
(`workflows.download`'s CLI, `run_aml_download`'s shard commands) does not yet carry a non-default
`collection=` to the node — it always resolves `sentinel-2-l2a` correctly by omission, but a
user-facing override there is P2/P3 work, when a second collection actually needs cluster-scale
download. P1 is network-free/cluster-free by the spec's own design, so this path has no AC coverage
either way._

_**Two out-of-repo obligations, unchanged, still open** (see below): `rise/`'s AML extras, and this
workspace `CLAUDE.md`'s dev line._
