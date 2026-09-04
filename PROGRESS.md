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
