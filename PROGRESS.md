# PROGRESS — fsd

**Resume anchor.** Read this, then `specs/00-overview.md`. This file is the *current state* plus the
most recent entry — **not the log.** Older entries are moved verbatim to
[`docs/progress-archive.md`](docs/progress-archive.md) (spec 41 D12; split re-run 2026-09-03 for
[#94](https://github.com/nikhilsrajan/fsd/issues/94)). For the narrative — why the code looks like
this — read [`docs/history.md`](docs/history.md).

## Resuming after a break — start here

**Spec 58 P1 is implemented, reviewed and merged into `main` — the one open action is pushing it.**
As of **2026-09-05** P1 landed on `main` via `--no-ff` (worktree + branch pruned); review found and
fixed one real bug and two untested acceptance criteria, all recorded in "Most recent entry" below.
**The merge is local and unpushed** — pushing is outward-facing and waits on the user. `main` is
otherwise clean and unmerged-branch-free except `spike/rslearn` (intentional). **`v0.1.0` is cut and
pushed.**

1. Read this file top to bottom. It is ~2k words by design; it is the whole picture.
2. Push `main` if the user agrees, then start the **re-download run-book** (it could not begin before
   P1 merged — P1 is what changes the catalog schema), then spec 58 **P2** (`sentinel-1-rtc`).
3. `gh issue list` — the open work. Nothing here is blocked on a decision you have to remember.
4. Otherwise pick from **THE ORDER** below, which is still sequenced.

**Before trusting anything below, re-verify rather than assume.** Every dated claim was true when
written. Cheap checks (on `main`, spec 58 P1 merged):
`.venv/bin/python -m pytest -q` (expect **1100 passed / 102 skipped**),
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
| **Current work** | **spec 58** — P1 merged 2026-09-05 (unpushed); next the re-download run-book, then P2 `sentinel-1-rtc`. See THE ORDER below |
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
| **8** | **[spec 58](specs/58-collection-agnostic-verbs.md)** — **CURRENT.** Collection-agnostic verbs: P1 contract → P2 `sentinel-1-rtc` → P3 HLS | **P1 IMPLEMENTED + REVIEWED + MERGED 2026-09-05** (`--no-ff` onto `main`, worktree pruned; **local, unpushed**). Review fixed one real bug + two untested ACs; pytest **1100 passed / 102 skipped**, ruff clean. Next: push → re-download run-book → P2 | → **9** |
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

_Last updated: 2026-09-05 (**SPEC 58 P1 REVIEWED — one real bug found and fixed, two acceptance
criteria were claimed but untested.** Reviewed in worktree `spec58-p1` against
`specs/58-collection-agnostic-verbs.md` §4/§5. Independently re-ran `pytest -q`
(**1100 passed / 102 skipped / 0 failed**, +3 tests added by this review; the tutorial fixture's
4 real-data tests are included, not run separately) and `ruff check src tests demos examples`
(clean). **Verdict: mergeable after the fixes below**, which are in the same branch. The P1
implementation entry moved verbatim to [`docs/progress-archive.md`](docs/progress-archive.md).)_

_**The bug: the D13 control file was addressed per RUN, not per unit.** `setup` wrote the resolved
declaration to `<run_folderpath>/declaration.json` — one file for a whole run folder. But a run
folder holds rows from many `setup` calls (`_UNIT_IDENTITY_COLS` carries `collection` precisely so
different collections coexist in one `input.csv`), and `_build_shortfall` dispatches **every**
still-missing row in that file regardless of which call wrote it. So a second `setup` with a
different collection silently overwrote the file the first call's nodes still point at → the wrong
mask/radiometry, written to a cube path that names a different collection, with the build-skip then
treating it as valid. Not reachable in P1 (one collection is registered) and certain to bite in P2.
**Fixed:** the control file now lives at `<run_folderpath>/<window_segment>/declaration.json` — the
window segment already digests `collection` + the declaration (D4), so it is exactly the right
granularity. Same failure shape as [[fsd-addressing-granularity]]: address per unit path, never one
file per run._

_**Two ACs were claimed met but had no test.** **AC9**'s driver half ("the control file carries the
declaration JSON") was untested — only the node's *read* was covered, by hand-written fixtures.
**AC10**'s first half ("`from_json` on a v1 footer still parses") was untested — the nearest test
deletes one optional field from a **v2** footer. Both now have tests: `test_backward_walk.py::
test_setup_writes_a_window_scoped_declaration_control_file` (which is also the regression guard for
the bug above) and two in `test_declaration.py` pinning a frozen v1 footer literal + the
version-check-before-unknown-field-check ordering. AC1-AC8 verified as claimed; **AC3 (bit-identical
S2) re-derived independently rather than trusted** — `radiometry_bands` equals the old
`_is_reflectance` regex over every band in `S2L2A_ALL_BANDS`, and `apply_offset`'s new dtype-range
clip is identical to the old literal `0..65535` for `uint16`._

_**Two smaller fixes:** both new tests that register throwaway collections leaked them into the
global in-process `fsd.collections.REGISTRY` (which `restamp_cli`'s `--declaration` choices are a
view over) — now torn down in a `finally`. And `tests/data/tutorial/catalog.parquet`'s in-place
migration left `scale`/`properties` appended after `geometry`, so the fixture did not match the
`catalog.COLUMNS` order every real `TileCatalog.append` produces — reordered, values/geometry/CRS/
stamp asserted unchanged._

_**Three things flagged, deliberately NOT changed** (two need the user, one is P2 scope): (1) **D14's
field table is not exhaustive** — `native_grid`, `mask_keep` and `supports_cloud_cover` are in
neither the artifact-fact nor the build-policy group, so a variant may currently differ from the
catalog's stamp on `native_grid` without raising. The code matches the spec's table exactly, so this
is a **spec** gap, not an implementation one, and a spec change needs sign-off. (2) **The STAC export
drops the catalog's new `properties` column** — `tile_catalog_to_items` builds items with
`properties={}`, so a catalog round-tripped through STAC loses the `sat:orbit_state` D9 will need in
P2. Outside P1's ACs. (3) `stac.tile_catalog_to_items`'s `row_scale` fallback uses `if not
row_scale`, which lets a `NaN` through (`not nan` is `False`); only reachable from a hand-built
catalog, since `append` defaults the column. **The P1-scoped-out AML download path was checked and
is genuinely safe**, not a silent gap: both sources' `SERVED_COLLECTIONS` is `("sentinel-2-l2a",)`,
so a non-default `collection` cannot reach it at all today._

