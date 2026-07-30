---
status: current
summary: The end-to-end AML demo script tying download/build/flatten/train/infer together; header still reads DRAFT but it ran end to end on the cluster (2026-07-29) and carries its own recorded amendments A1-A3.
---

# Spec 40 — `demos/e2e_austria_aml.py`: the cluster demo run as one script

**Status:** DRAFT — grilled 2026-07-28, ten decisions agreed; awaiting final sign-off.
**Model/effort:** spec Opus@high; implementation Sonnet@medium against this file.
**Vocabulary:** this spec uses `CONTEXT.md` terms exactly — **demo run**, **step**, **run**,
**dispatch telemetry**, **job admission**. See §2.

## 1. Why

`demos/e2e_austria.py` runs the whole pipeline on a laptop in one command and emits a
`timings.json` that `E2E_AUSTRIA.md` §8 turns into a step/seconds/share table. **The cluster has no
equivalent.** Reproducing it means running run-books 36 → 37 → 39 → 40 → 38 by hand, each with its
own env vars, each pasting a `_result.json` back. That is a debugging apparatus, not a demo — and it
is why `demos/E2E_AUSTRIA_AML.md` had to be assembled by forensics
(`runbooks/41-recover-aml-job-timings.md`) rather than read off a file.

This spec defines the sibling: **one script, one command, unattended, from an empty Azure**,
emitting a JSON of the same shape so local-vs-cluster is a diff rather than an essay.

Two secondary payoffs:

- **It retires the forensics.** Everything run-book 41 reconstructed after the fact becomes dispatch
  telemetry the run writes down as it happens (D2, ADR 0021).
- **It makes the download step comparable for the first time.** D13 drops the demo run's download to
  the local demo's exact scope, which turns the report's largest "not comparable" row into a
  measured one — and costs 5× less.

## 2. Vocabulary (agreed 2026-07-28; `CONTEXT.md` is authoritative)

| Term | Means here |
|---|---|
| **Demo run** | one end-to-end execution of this script; contains four *runs* plus driver-only work |
| **Step** | one of the eight labelled parts a demo run is timed by (`0_preflight` … `7_report`) |
| **Run** | one dispatched execution under `<root>/runs/<run_id>/` — unchanged meaning |
| **Job admission** | submit → that job's code executing: queue + allocation + image pull + process start |
| **Dispatch telemetry** | `<run_root>/_timing.json`, the dispatcher's own durable record |

**"Phase" is not used in this spec.** It means a run-book's manual stage ("run-book 38 Phase 3") and
nothing else.

## 3. Scope

**In:** the cluster path end to end — the eight steps, dispatch telemetry, unattended execution on a
VM, resumability, an archive-trust gate, a cost guard.

**Out:** re-running the local demo (§9); rendering the timing figures (D12) or writing the report
(D9); building the AML Environments (D4); anything touching `raapid-infra` Terraform.

## 4. Decisions

### D1 — Mirror the local demo: same step labels, same harness, same JSON shape
The script uses the **same eight step labels** as `demos/e2e_austria.py` and the same `timed_step`
accumulator. `timings.json` keeps the local schema and adds the cluster detail (D10).

> **AMENDMENT A2 (2026-07-28, user's call).** The mirror is **step labels and harness**, not every
> argument. Two steps now deliberately differ from the local demo, both to match the run-books:
> `2_download` sources from MPC (D13 A1), and `3_training_data` passes
> **`aggregate="median_per_id"`** (run-books 39/40).
>
> `median_per_id` is *"the modelling unit, not just a size trick"* (`runbooks/40-train-and-bundle.md`):
> one `np.nanmedian` row per labelled field rather than one per pixel. The labels are field-level, so
> training per-pixel leaks a field's own pixels across the split — the difference between the
> discredited **0.696** and the honest field-wise **~0.29** already recorded in `PROGRESS.md`. It also
> cuts the flatten reduce and the driver-side fit from ~172k rows to ~900.
>
> **`demos/e2e_austria.py` was changed to match** (same call, same reason), so D1's mirror still
> holds for step 3: both sides now reduce to field medians before the adapter's transform. The
> alternative — leaving the local demo per-pixel — would have made a step-3 row compare a
> field-median reduce against a per-pixel one, which is not a comparison.
>
> ⚠️ **This invalidates the local demo's published step-3 and step-4 numbers.** Everything in
> `E2E_AUSTRIA.md` and the 2026-07-13 `timings.json` was measured with `aggregate=None`: step 3's
> flatten is now over ~900 rows rather than ~172k, step 4 trains on field medians, and any accuracy
> figure quoted from that run is the leaky per-pixel one. **The local demo must be re-run before
> local-vs-cluster means anything** — §9's open question is now a prerequisite, not a nicety.

*Why:* the comparison is only honest if both sides are cut the same way.

Two correspondences confirmed by reading the code, both of which must be **preserved, not
"fixed"**:

- **`3_training_data` is ONE call on both sides.** `api.create_training_data(runner="aml")` already
  dispatches the cube-build fan-out *and* the flatten reduce internally (`api.py:326`), so the
  script does not orchestrate them by hand. It does mean one step contains **two runs** — which is
  exactly why D2's telemetry must be a file rather than a return value (ADR 0021).
- **`1_tiling` duplicates work that `run_inference` re-tiles internally — on both sides.** The local
  demo tiles for the cell count and figure, then passes `roi=` (not the grids) to `run_inference`,
  which tiles again in preflight. Symmetric, cheap (0.8 s locally), and load-bearing for the
  comparison. **Add a comment saying so** — it looks like a bug and is not.

### D2 — Timing is stamped by the unit of work and persisted by the dispatcher (ADR 0021)
Each in-job entrypoint that already writes `_status/<k>.json` — `workflows/shard.py`,
`workflows/download.py`, `workflows/infer_shard.py`, `workflows/flatten.py` — adds four stamps:

| stamp | written | where |
|---|---|---|
| `process_start_at` | node | **first line of the entrypoint module**, before any heavy import |
| `work_start_at` / `work_end_at` | node | around the existing work timer |
| `ended_at` | node | after the work, before the `_status` write |

`_aml_submit_and_wait` records `submitted_at` **per job** (as each `create_or_update` returns) and
`returned_at`, then writes **`<run_root>/_timing.json`**. Nothing is returned; no public dataclass
changes. See ADR 0021 for why.

**Deliberately not read from AML's `properties.StartTimeUtc`/`EndTimeUtc`.** They exist — this
session measured them on 113 jobs — but no official `azure-ai-ml` reference documents them, and they
are AML-specific: an Azure Batch dispatcher has no equivalent, and the runner seam is the point.

### D3 — Every step writes its `_result.json` when it completes
A crash in `5_run_inference` must still leave the earlier steps' numbers on disk. Each step writes
`<outdir>/<step>_result.json` (spec-24 shape) as it finishes, and `timings.json` is rewritten after
every step.

### D4 — Preflight is total and cheap; it fails in seconds, never 20 minutes in
`0_preflight` verifies, before any spend, naming the exact fix for each failure:

| check | failure means |
|---|---|
| a credential resolves | no `az login` on this VM, and no managed identity |
| a blob **read and write** succeeds | the storage firewall is denying this host (§8) — **a distinct message from an auth failure** |
| cluster exists, `provisioning_state == Succeeded` | wrong name / not deployed |
| **both Environments exist** | build them first — the script does not (D4 is verify-only) |
| ROI + label files readable; band/window/T consistent | a bad input |
| `max_tiles` ≥ discovered tile count | the ROI × window is bigger than intended |
| **clock skew** vs blob (D11) | recorded, not fatal, unless it exceeds the admission numbers |

Environments stay an operator step: an ACR build is 10–20 min and occasionally flaky, and one bad
build must not kill a 40-minute unattended demo run.

### D5 — Resumable across steps; never destructive
- `--run-id` resumes: completed steps skip instantly (their `_result.json` already holds the
  timings), so a failed demo run restarts cheaply.
- **`--fresh` allocates a run-stamped prefix and deletes nothing.** An unattended script that can
  erase 80 GB is a bad idea, and fsd's own recursive delete is broken (TODO #50). The demo run ends
  by **printing the exact `az storage fs directory delete`** for the previous prefix. The operator
  remains the only thing that deletes.
- A step that **failed** part-way is re-run on a fresh prefix, not resumed — a half-skip is not a
  measurement (D15).

### D6 — Cost guard: `--dry-run` first, `--confirm-spend` to proceed
`--dry-run` prints granule count, cell count, field count, estimated GB and estimated wall with
**zero side effects**. The real demo run refuses to start without `--confirm-spend`.

### D7 — Built for unattended operation
For `nohup`/`tmux`: no interactive prompts after `--confirm-spend`, timestamped stdout, and **every
long loop prints a throttled progress line with an ETA** (standing user preference — a stage line is
not progress). SIGINT/SIGTERM finish the current step's `_result.json` before exiting.

### D8 — One `run_inference(..., merge=True)` call, not a second dispatch for the merge
Run-book 38 split these, and the measurement showed the cost: a second dispatch paid another ~200 s
of job admission and a full 972 s collect to run 44 s of no-op jobs.

### D9 — The script emits data; it does not write the report or the timing figures
`timings.json` plus the per-step `_result.json`s are the deliverable. **`timings.json` is
self-contained** — it embeds each step's result — because the operator hands over *one file*.

### D10 — Driver location is recorded; no causal claim is derived from it
The demo run stamps where the driver ran (VM vs laptop, region, whether on VPN) in `timings.json`.
Every existing cluster number was measured with the driver on a laptop over VPN; this run will not
be. **The report presents them as two configurations and does not compute a ratio between them**
(§7) — a VM run differs on driver location *and* download scope at once, so any single ratio would
be uninterpretable.

### D11 — Job admission is the headline metric; scale-out is read from its spread
**`job_admission_seconds[k]` = `process_start_at[k] − submitted_at[k]`** — queue + allocation +
image pull + process start, per job. A demo run yields ~49 samples (16 download + 16 build + 1
flatten + 16 inference). **Cluster scale-out is not measured separately**; it is the spread and tail
of that distribution, since late-admitted jobs are the ones that waited for a node.

Also derived per job: `import_seconds` (`work_start_at − process_start_at`), `work_seconds` (the
existing `seconds`), and **`dispatch_overhead_seconds[k]` = `(returned_at − submitted_at[k]) −
work_seconds[k]`** — everything paid to run *k* that was not *k* running.

Per run, an **additive** split summing to the run's wall: `driver_prep` + `first_admission` +
`execution_window` + `teardown_detect` + `post_collect`.

> **AMENDMENT A3 (2026-07-29) — `first_admission` is anchored on the FIRST submission.**
> The spec named the five legs but not their breakpoints; the implementation chose
> `driver_prep = t_start → last submission` and `first_admission = last submission → earliest
> `process_start_at``. Run `20260729T132222Z` showed why that is wrong: it reported
> `driver_prep=40.1, first_admission=**-5.0**` on a completely healthy dispatch.
>
> Submitting 32 jobs takes ~40 s and is **sequential**, while the jobs submitted first are being
> admitted *during* it. Submission and admission overlap, so they cannot be adjacent legs — anchor
> on the last submission and the leg goes negative whenever a node starts before the final job is
> submitted, which is the normal case on a warm cluster.
>
> Worse, it destroyed a signal: D11 says a negative admission *"is the signal the [clock-skew]
> bound was exceeded"*. With the overlap artefact also producing negatives, that meaning was gone.
>
> **Revised:** `driver_prep = t_start → first submission` (genuinely pre-dispatch driver work),
> `first_admission = first submission → earliest process_start_at` (genuinely "how long until a
> node was executing", with the submission loop correctly *inside* that wait). Still additive, and
> a negative once again means only clock skew. The submission span is not lost — it is reported as
> **`submission_span_seconds`, deliberately outside the additive split**, because it overlaps
> `first_admission` rather than partitioning it.
>
> ⚠️ **`timings.json` files from before 2026-07-29 carry the old definition.** Their
> `driver_prep`/`first_admission` are not comparable to later runs; their *sum* is.

Two measurement hazards, handled rather than ignored:

- **Cross-clock subtraction.** `submitted_at` is the driver's clock, `process_start_at` the node's;
  this session already hit **~8 s of laptop-vs-Azure skew**, which would be a third of a warm
  admission. `0_preflight` **measures it** — write a scratch blob, read back its `last_modified`,
  compare — and records `clock_skew_seconds`. Every admission figure carries that bound. A negative
  admission is reported as negative, never floored at zero: it is the signal the bound was exceeded.
- **Poll quantization.** The dispatcher polls every `poll_interval_seconds` (default 30), so
  `teardown_detect` carries up to that much error. The demo passes **10** and records the value.

### D12 — Timing figures render off-box, from `timings.json` alone
`6_plots` keeps **only the data figures** (per-class NDVI, the crop map), mirroring local. The timing
charts live in a separate **`demos/plot_aml_timings.py`** that reads `timings.json` and runs
anywhere — so the VM needs no chart code, and figures can be restyled without re-running anything.

**Figure 1 — `aml_job_admission.png`.** A **horizontal strip plot**: one dot per job, one row per
run, x = admission seconds, median marked. **Not a histogram** — n ≈ 16 per run, where binning
invents structure and hides the tail that *is* the scale-out signal. One hue; a single series needs
no legend.

**Figure 2 — `aml_where_the_wall_went.png`.** A **horizontal stacked bar**, one per run, using
D11's additive split. Part-to-whole ⇒ stacked bar; four-plus segments ⇒ categorical, fixed slot
order.

**Palette (validated — do not substitute by eye):** `#2a78d6`, `#eb6834`, `#1baf7a`, `#eda100`
(`node scripts/validate_palette.js "…" --mode light`: all checks PASS, worst adjacent CVD ΔE 9.1
protan, normal-vision 22.9). It returns one **WARN** — aqua and yellow fall below 3:1 against the
surface — which **obligates relief**: every segment carries a visible direct label, and
`timings.json` is the table view. Also required: a legend, a **2px surface gap between segments**,
and no label drawn inside a segment too small to hold it.

**Figure 3 — `aml_job_gantt.png` (optional).** One row per job, admission then work, two shades of
one hue. It is what makes "38 % of node-time idle" (TODO #60) visible. Ship it if it reads cleanly
at ~49 rows; drop it if not.

**Look at every figure before calling it done** — the validator checks color, not layout.

### D13 — The demo run downloads the local demo's scope, **from MPC**

> **AMENDMENT A1 (2026-07-28, user's call, after implementation review).** The source is **MPC**,
> not CDSE. The window, bands and cloud filter are unchanged. Reasons, in order of weight:
>
> 1. **D13 as originally written contradicted D11.** D11 sizes a demo run at *"~49 samples (16
>    download + 16 build + 1 flatten + 16 inference)"*, but **CDSE dispatches exactly one job**
>    (spec 37 D1 — `_aml_submit_and_wait`: *"one CDSE job or N MPC shard jobs"*). With CDSE the
>    download leg contributes **1** admission sample and measures **no scale-out at all** — the
>    headline metric this spec exists to produce. MPC fans out to the cluster's `max_instances`.
> 2. **Continuity with the runbooks.** Every cluster run since P1 sourced from MPC
>    (run-book 37 Phase 3; the 418 GB archive is *"576 MPC granules"*). Keeping the source fixed
>    means `2_download` is comparable to that series — which is the series the report is about.
> 3. **Operational risk.** CDSE needs the credential-staging dance (`_blob_creds`, a secret on
>    blob for the run) and `run_aml_download`'s own preflight warns about the **30-day quota**
>    throttling to 1 MB/s partway through — a bad failure mode 60 GB into an unattended run. MPC
>    is anonymous and copies inside West Europe.
>
> **What A1 gives up, knowingly:** `2_download` is no longer a like-for-like row against the local
> demo's 207 CDSE granules — the one thing the original D13 was for. §7 already said this demo run
> is not comparable to the existing *cluster* numbers; now the download row is not comparable to
> the *local* ones either. That is the accepted price of measuring download scale-out at all.
> `max_tiles` moves 207 → **250** as a guardrail (not a prediction): MPC queries a different
> catalogue and de-duplicates reprocessed acquisitions (spec 33), so its count for the same window
> will differ. `--dry-run` reports the real number before any spend.

`2_download` uses the local demo's scope: **2018-04-01…09-30, bands `B04 B08 B8A SCL`,
`max_cloudcover=70`** (`demos/e2e_austria.py:64-70`), from MPC. ~80 GB, not the 418 GB
full-year six-band archive run-book 37 built.

*Why:* five times cheaper and faster, and — more importantly — it makes `2_download` a **like-for-
like row** against the local run's 207 granules for the first time. The existing archive's extra
bands and full year were built for a different purpose (B02/B03 serve true-colour RGB to
mini-MPC/STACNotator, `runbooks/37-download-on-aml.md:382`).

⚠️ **Consequence to accept knowingly:** a from-scratch demo run does **not** reproduce that shared
418 GB archive. Deleting everything on Azure destroys it, and rebuilding it for the STACNotator tier
is a separate run-book-37 job.

### D14 — `2_download` asserts the archive is trustworthy before anything consumes it
Run-book 36 refuses to start unless `37-verify-archive.md` has passed, because a mis-tagged archive
is an **invisible** failure: the pipeline goes green and the science is wrong. A from-scratch demo
run must re-establish that itself. Folded **into `2_download` as assertions** (not a new step, so D1
survives):

- catalog rows == objects on blob, and no undeclared objects;
- the source declaration is stamped on the catalog;
- `scale` / `offset` / `nodata` correct on a **sample** of granules, and no zero-byte assets.

Seconds of listing and tag reads. The expensive cross-source pixel comparison stays in
`runbooks/37-verify-archive.md`.

### D15 — A failed dispatch aborts the demo run, loudly
Keep today's raise-on-failure. Completed steps keep their timings (D3); the operator restarts with
the same `--run-id`, finished steps skip, and the failed step re-runs on a fresh prefix (D5).

**No retries.** Two reasons: TODO #57 was a retry that was retracted *and* reverted for burying the
real error behind a minutes-long storm; and this script is a **measurement instrument** — a retried
job pollutes its own data, putting a dead attempt inside the run's wall and a second sample in the
admission distribution. Continuing past a partial failure is worse still: inference over 280 of 300
cells merges into a map that looks entirely fine.

## 5. Deliverables

| # | item | files |
|---|---|---|
| 1 | the four in-job stamps in every `_status/<k>.json` | `workflows/{shard,download,infer_shard,flatten}.py` |
| 2 | per-job `submitted_at`, `returned_at`, and `<run_root>/_timing.json` | `workflows/runners.py` (`_aml_submit_and_wait`) |
| 3 | the demo script (8 steps, D4 preflight incl. clock skew, D6 guards, D14 assertions) | `demos/e2e_austria_aml.py` |
| 4 | the timing plotter | `demos/plot_aml_timings.py` → `demos/figures/` |
| 5 | operator notes: VM placement, `az login`, `nohup`, what to send back | `demos/E2E_AUSTRIA_AML.md` "Reproduce it" + `RECIPES.md` |
| 6 | tests for 1 + 2 + 4 (synthetic, no cloud) | `tests/test_runners.py`, `tests/test_workflows_status.py` |

## 6. Testing

- **Unit, synthetic:** `_status` round-trips the new stamps; `_timing.json` computes
  `job_admission`, `import`, `dispatch_overhead` and the stagger correctly from hand-written stamps.
  Degenerate cases: one unit; a failed unit with no `ended_at`; **skew large enough to make
  admission negative — reported as negative with a flag, never floored at 0**.
- **Unit, additive invariant:** D11's split sums to the run wall within tolerance. This property is
  the only reason this session's forensics were trustworthy — pin it.
- **Unit, plots:** both figures render from a synthetic `timings.json` with no cluster and no
  network, including a run with one job and a run with zero spread.
- **Unit, guards:** `--dry-run` writes nothing (assert against a fake `fs`); `--fresh` never issues a
  delete.
- **Not unit-testable, by design:** the demo run itself, validated by being run (§8).

## 7. What this demo run is and is not comparable to

**Comparable:** the local demo, step for step, by construction (D1) — and `2_download` genuinely so
for the first time (D13).

**NOT comparable to the existing cluster numbers** in `E2E_AUSTRIA_AML.md`: those were measured with
the driver on a laptop over VPN *and* against the 418 GB archive. Two variables move at once. When
the JSON arrives, that document is **rewritten around this demo run**, with the laptop-driver
decomposition retained as a clearly-labelled appendix — it is the evidence behind TODO #60 and #61
and must not be lost, but it stops competing with the headline numbers.

## 8. Operator prerequisites (the VM)

1. **Create the VM inside the project's compute subnet** (`snet<proj>-compute`) or another subnet
   carrying the storage service endpoint. Project storage is deny-by-default firewalled
   (`AZURE_INFRA.md:117`); a VM outside those ranges gets **403 on every blob call regardless of
   credentials**, because network rules and authorization are enforced independently.
2. **`az login`** once over SSH. The CLI refreshes tokens silently, so a multi-hour unattended demo
   run is fine. *(Upgrade: give the VM a managed identity with Storage Blob Data Contributor + an
   AML submit role and skip the login — an admin action, not a prerequisite.)*
3. Clone, `python3.11 -m venv .venv`, `pip install -e ".[dev,azure,aml]"`.
4. Both AML Environments already built (D4).
5. `--dry-run`, read the estimate, then run under `tmux` with `--confirm-spend`. Close the laptop.
6. Send back **`timings.json`** (self-contained, D9).

## 9. ~~Open question~~ → RESOLVED as a prerequisite (A2, 2026-07-29)

**Do we also re-run `demos/e2e_austria.py` locally on current code?** Originally: *"yes eventually,
not blocking"* — the report would otherwise compare a 2026-07-13 laptop run against a 2026-07-28+
cluster run across several fixes (D-GRID-1, `rio_env`, the merge fixes), which was a version gap to
state rather than a blocker.

**A2 turned it into a blocker.** The local demo now passes `aggregate="median_per_id"` too, so its
published step-3/step-4 numbers were measured by code that no longer exists: step 3 flattens ~900
field medians rather than ~172k pixels, and step 4 trains on those. A local-vs-cluster table built
from the old `timings.json` would not be a version gap — it would compare two different
computations and label them the same. **Re-run the local demo before writing any comparison** (74 GB
local archive, ~100 min of laptop).

Note this cuts the other way on cost: step 3's local flatten and step 4's fit both get *cheaper*, so
the re-run is not simply the old ~100 min repeated.

## 10. Best-practice alignment / sources

- **Microsoft Learn, "Azure Storage firewall rules and network access"** — established that a
  deny-by-default account returns **403 to any subnet not explicitly allowed**, that VNet rules work
  via **service endpoints on the subnet**, and that **network rules and authorization are
  independent**. That is what makes §8 step 1 a prerequisite rather than a nicety, and why D4 reports
  a firewall denial and an auth failure as *different* errors.
  https://learn.microsoft.com/en-us/azure/storage/common/storage-network-security
- **`azure-ai-ml` API reference / package docs** — searched for an official definition of the job
  `properties.StartTimeUtc` / `EndTimeUtc` keys this session relied on and **found none**. That
  absence is the reason D2 stamps timings in the unit of work rather than reading AML's property bag.
  https://pypi.org/project/azure-ai-ml/ ·
  https://learn.microsoft.com/en-us/azure/machine-learning/concept-v2?view=azureml-api-2
- **The `dataviz` skill** (`references/choosing-a-form.md`, `references/palette.md`,
  `scripts/validate_palette.js`) — supplied D12's forms and palette: the job→form table gave
  *part-to-whole ⇒ horizontal stacked bar*; the series-count ladder put 4 segments at "direct labels
  mandatory"; and the validator was **run** on the four hexes rather than eyeballed, returning
  all-PASS with a contrast WARN that is what makes the direct labels a requirement.
- **This repo's own measurements** (`demos/E2E_AUSTRIA_AML.md` §6.1, via
  `runbooks/41-recover-aml-job-timings.md`) — supplied every quantity the design reacts to: the 616 s
  collect and 13 s bundle stage (D2/ADR 0021), the ~200 s admission toll (D8/D11), the resume-path
  trap (D5), and the ~8 s clock skew (D11).
- **`AZURE_INFRA.md` §"Firewalled storage"** and **`demos/e2e_austria.py:64-70`** — the concrete VM
  placement rule (§8) and the exact download scope D13 must match.
