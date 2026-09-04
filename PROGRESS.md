# PROGRESS — fsd

**Resume anchor.** Read this, then `specs/00-overview.md`. This file is the *current state* plus the
most recent entry — **not the log.** Older entries are moved verbatim to
[`docs/progress-archive.md`](docs/progress-archive.md) (spec 41 D12; split re-run 2026-09-03 for
[#94](https://github.com/nikhilsrajan/fsd/issues/94)). For the narrative — why the code looks like
this — read [`docs/history.md`](docs/history.md).

## Resuming after a break — start here

**Nothing is in flight.** As of **2026-09-04** the tree is clean, `main` == `origin/main`, there are
no worktrees and no unmerged branches except `spike/rslearn` (intentional, pushed, and closed as a
decision). **`v0.1.0` is cut and pushed.** There is no handoff document, because there was no goal
in progress when work stopped — that is the normal state, not a gap.

1. Read this file top to bottom. It is ~1.8k words by design; it is the whole picture.
2. `gh issue list` — the open work. Nothing here is blocked on a decision you have to remember.
3. Pick from **THE ORDER** below, which is still sequenced. **#93 (the front door) is next**, and it
   wants its own spec before implementation.

**Before trusting anything below, re-verify rather than assume.** Every dated claim was true when
written. Cheap checks: `.venv/bin/python -m pytest -q` (expect **1083 passed / 103 skipped**),
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
| **8** | **[#93](https://github.com/nikhilsrajan/fsd/issues/93)** — **CURRENT.** Front door: README → tutorial → how-tos | **wants its own spec** (touches spec 41 D1's audience table + ADR 0026) | → next era: Sentinel-1 as the generalization probe |

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

_Last updated: 2026-09-04 (**THE README IS MPC-FIRST AND THREE OF ITS CLAIMS WERE WRONG.**
`main` @ `333a0d1`, clean, pushed. `pytest -q` **1083 passed / 103 skipped**, ruff clean.
**Work stopped here deliberately, with no goal in flight** — see the resume block at the top.)_

_**The quickstart now needs no account and no credentials.** `source="mpc"` is the default path;
the creds guard only fires for `source="cdse"` with `runner="local"`. That removed the
`CdseCredentials` import and the entire credentials prerequisite from the first thing a reader
runs — and it matches the flagship run, which was **213 MPC granules**, not CDSE._

_**Three factual corrections, each found by checking the code rather than reading the prose:**_

- _**`fsd.deploy` was described as "the one verb still a stub."** It has not been since spec 51.
  **`test_readme_verbs_exist` could not catch this** — it proves a verb *binds* to a live
  signature, which `deploy` always did. Nothing tests whether the sentence around a call is true.
  That is the residual gap, and it is the same shape as #95: the check exists, but not for this._
- _**`demos/E2E_AUSTRIA.md` was labelled the 300-cell benchmark.** It is the *local* walkthrough;
  the 300-cell run is `E2E_AUSTRIA_AML.md`. Both are now linked and labelled._
- _**The install line under-specified the quickstart printed directly beneath it.** Step 3 passes
  `roi=`, which routes through `roi_to_s2_grids` → `[grid]`; MPC needs `[mpc]`. Now
  `fsd[local,mpc,grid]`, pinned at `v0.1.0`, over **https** rather than ssh._

_**`[mpc]` now names itself** (`sources/mpc._import_pc`, the single guarded entry that
`_import_pc_sign` also routes through). `planetary_computer` was imported lazily at two bare sites,
so a user without the extra got a `ModuleNotFoundError` naming a package they never typed, from a
call they made as `source="mpc"`._

_**⚠️ A claim I wrote and then disproved, worth keeping.** The `CHANGES.md` draft said "nothing else
is imported lazily behind an extra." Checking it found **15 bare `azure.ai.ml` / `azure.identity`
imports** across `workflows/runners.py` and `secrets.py` — so **`[azure]` and `[aml]` still do not
name themselves**, filed as **[#97](https://github.com/nikhilsrajan/fsd/issues/97)**. It is the
expensive one: the others fail on a laptop in a second, while `runner="aml"` fails only after
someone has stood up a workspace, a cluster and images, where a bare import error reads as a broken
install. `storage.fs` already maps `abfss://` → `[azure]`, so the storage half is covered; the
**dispatch** half is not._

_**Also added to the README:** `fsd init` / `fsd config` (spec 54/55, previously absent entirely),
the `deploy` → `"name:version"` → `run_inference(ref, registry=...)` loop, `verify_adapter`, the
AML-image `[local]` warning, and a **Known limits** section — S2 L2A only, warm-up dominates cluster
cost, `0.y.z` deliberate. A README that lists only wins is a brochure._

_**Worth not re-deriving:** `tests/test_docs.py` parses the README's Python and binds it against
live signatures. It rejected a literal `...` placed after a keyword argument in the `deploy`
example — that is a **SyntaxError**, not a stylistic choice, so README snippets must be valid
Python even where they are illustrative._
