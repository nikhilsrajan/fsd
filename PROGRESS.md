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
| **8** | **[spec 58](specs/58-collection-agnostic-verbs.md)** — **CURRENT.** Collection-agnostic verbs: P1 contract → P2 `sentinel-1-rtc` → P3 HLS | spec **SIGNED OFF 2026-09-04**; next: P1 green on S2 alone (network-free) | → **9** |
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

_Last updated: 2026-09-04 (**SPEC 58 DRAFTED — the verbs become collection-agnostic.** Branch
merged to `main` as `6926982` and pushed. A full grilling session with the user
produced 18 decisions, 4 ADRs (0028-0031), 3 new issues (#98/#99/#100), 4 new `CONTEXT.md` terms and
`specs/58-collection-agnostic-verbs.md`. **SIGNED OFF; no code written — P1 is next.**)_

_**The axis is Collection, not satellite.** `source` conflated provider with product; the catalog
column named `satellite` has always held a STAC collection id. Source (`cdse`/`mpc`) and Collection
(`sentinel-2-l2a`/`sentinel-1-rtc`/`hls2-s30`/`hls2-l30`) become two orthogonal parameters, and
`SourceDeclaration` is renamed `CollectionDeclaration` (ADR 0030)._

_**Scope: S1 RTC + HLS. MODIS deferred** (needs `native_grid`, unimplemented). **S1 = RTC, not GRD**
(ADR 0028) — GRD needs a per-pixel range-dependent calibration LUT and declares no `raster:bands` at
all. My "GRD isn't map-projected" objection was **checked and false**; the decision rests on
calibration, self-description and grid instead._

_**Two silent bugs found by reading the code, both landing the moment HLS does:** the cube path
digest has **no collection in it** (`params_key`), and HLS bands are named `B04`/`B08`/`B8A`
identically to S2 — so an HLS cube and an S2 cube over the same cell/window resolve to the **same
path**. And `_select_item_files` **silently drops** a requested band an item lacks._

_**Two of my own prep-brief claims were wrong and are recorded in the spec §8:** the pipeline is
**not** integer-only (`_stack_datacube` takes dtype from the loaded image; `apply_offset`
early-returns at offset 0), which shrank the radiometry work from a rewrite to four small moves. The
user corrected a third: the EuroCrops labels **are** 2018 (`GEOM_DATE_`), deliberately matched to the
imagery — `MFA-2021` is the publication version. That reversed a plan to move everything to 2021._

_**Don't-reinvent-the-wheel research paid off twice.** NASA's `hls-vi` and GEE both use
`fmask & bitmask` with bits 1/2/3 — so the proposed design was already the standard idiom. And STAC's
`eo:bands.common_name` is the right vocabulary, but **MPC's values are wrong for HLS**: it names
`nir` on both L30 `B05` and S30 `B08`, pairing the two bands NASA's correspondence table explicitly
declines to pair, and contradicting its own `landsat-c2-l2` which names OLI band 5 `nir08`. fsd
declares its own alias map._

_**Sentinel-1 orbit mixing is enforced, not warned** (ADR 0029). `mosaic_partition` is a per-collection
declaration; S1 declares `sat:orbit_state`, optical declares nothing (optical products are harmonized
for compositing; radar is not). `sat:relative_orbit` is offered and reported but not enforced —
WorldCereal deliberately does not fix it, and a 250 km swath caps the ROI if you do._

_**The registry cannot live on the nodes** (ADR 0031). An in-process `register()` dict would raise
`KeyError` ~30 min into an AML dispatch — the #80 failure shape. The driver resolves `collection=`
and the declaration travels as JSON in a control file; nodes never consult a registry._

_**Validation needs two windows** because MPC's HLS archive starts 2020-01-01 while the labels are
2018: Window A (2018, labelled, S2+S1) and Window B (2021, unlabelled, HLS+S2). One grid cell, not
the 74 GB four-tile ROI. **The user chose to re-download and rebuild on AML** rather than ship a
migration CLI — which also retires the Austria archive's ~1000 DN radiometry debt._

_**Known gap, not fixed here:** `specs/README.md`'s index table stops at spec 47 — specs 48-57 are
missing entirely. Its own convention says regenerate rather than hand-patch, so 58 was not added to
it either. That regeneration is a separate job._
