# Spec 36 — the scale runner (P2): dispatch the existing unit of work onto Azure ML

> **Status: ✅ SIGNED OFF (user, 2026-07-21); IMPLEMENTED (Sonnet@medium, 2026-07-22), pending
> review + Phases 1–3.** Written by Opus@high after the Batch-vs-AML fork was closed by measurement
> (`runbooks/36-runner-fork-probe.md`, `AZURE_INFRA.md` §3.1), and after **Phase 0 validated D4 on
> the cluster** (`runbooks/36-phase0-identity-smoke.md`, green). All 11 deliverables (§5) landed;
> all 9 tests (§7) pass (343 passed / 3 skipped locally, up from the 331/3 baseline; `ruff` clean;
> `import fsd` verified to not require `azure-ai-ml`). Phases 1–3 (`runbooks/36-aml-runner.md`) are
> the real-cluster validation — user-run, not yet executed.
>
> **Sign-off decision on §8 Q4 (user):** **TODO #40 (ROI geometry through `fsd.storage`) is fixed
> inside this spec**, not as a prerequisite commit — see D6a and deliverable 11.
>
> **Relationship to spec 10.** Spec 10 (`10-storage-and-scale.md`) defines the two *seams* (storage,
> compute) and is signed off + realized. **This spec is the P2 design against spec 10's Seam 2** — it
> does not restate or amend it. Spec 31 realized Seam 1 on Azure; this finishes the pair.

---

## 1. The problem, stated honestly

Everything local is proven on real data (P0→P0.9). Blob storage is proven (P1: runbooks 31 + 34
green). **The runner seam has exactly one implementation — Snakemake on one laptop — so the claim
"cloud is a backend, not a rewrite" is currently unfalsified rather than demonstrated.**

The demo target (`ROADMAP.md` §5.0) is a researcher running *the same pipeline* at scale with
`runner=` / `storage=` as configuration. This spec is the smallest design that makes that true.

**The failure mode to avoid is precise:** if the cloud path ends up needing its own pipeline code,
the demo has failed *even if it runs fast*. Every decision below is biased toward reusing code that
already works over writing new code that is better suited.

---

## 2. Scope

**In scope**
- A second runner backend (`runner="aml"`) dispatching the **existing** unit of work.
- Sharding a work list, submitting jobs, collecting status, and failing loudly.
- Making the unit of work **idempotent and resumable on blob** (this also fixes TODO #41's
  local-Snakemake blob-unsafety, which falls out of the same change).
- The job environment (dependencies on the node).
- **ROI/label geometry I/O through `fsd.storage`** (TODO #40) — in scope by sign-off decision, D6a.

**Not in scope** — and deliberately so
- Azure **Batch**. Dropped, not deferred (`AZURE_INFRA.md` §3.1: quota, not architecture).
- Inference at scale (**P4**) — this spec's runner is *reused* there unchanged; `run_inference`'s
  blob-write gap is TODO #39 and stays out.
- A thin control plane / job-submission UX (**P3**).
- Any `raapid-infra` change. **P2 needs none** — the clusters are provisioned, quota'd, and
  identity-attached today.
- Download fan-out. Download stays a single quota-bound job (spec 10 Seam 2); only datacube
  building fans out.

---

## 3. Decisions

### D1 — Backend is **Azure ML**, cluster `<proj>-d16`

Settled by measurement, not preference. Evidence table: `AZURE_INFRA.md` §3.1. In one line: the
Batch account's dedicated core quota is **6** against a **64-core** pool VM (it cannot allocate one
node), while the AML cluster offers **32 nodes × 16 vCPU** today under **the same user-assigned
managed identity spec 31 already proved against blob**.

The 16-vCPU node is a *better* fit than the 64-vCPU Batch node would have been: spec 11/12 measured
the build as I/O- and decode-bound with a throughput knee well below 64 cores, so a 64-core node
would have been substantially idle under one Snakemake.

### D2 — One dispatched unit = **a shard of `input.csv`**, run by the existing local runner

The cloud runner's entire job is: **split the work list, launch N copies of code that already
works.** Inside the job we call `runners.run_local(...)` — the same Snakemake orchestration used on
a laptop, at `--cores` = the node's vCPUs.

- **Why not one job per datacube:** per-job scheduling + container start is tens of seconds to
  minutes; per-cube builds are short. Fine-grained dispatch would spend most of the wall clock on
  scheduling, and on AML would require a parallel-job *entry-script* contract — i.e. exactly the
  "cloud needs its own pipeline code" outcome §1 forbids.
- **Cost accepted:** retry granularity is the shard, not the cube. D7 makes that cheap — a retried
  shard skips every cube it already finished.
- **Sizing:** `n_shards` defaults to the cluster's `max_nodes`; shards are assigned round-robin over
  the work list so a straggler shard isn't systematically the heavy one.

### D3 — The seam: `runner=` selects a **dispatcher**, never leaks into the task

`ROADMAP.md` §2.7 names this as get-it-right-early surface #4. Concretely:

```
fsd.api.create_training_data(runner="local"|"aml", storage=...)
    -> workflows.create_datacube.run_create_datacube(runner=...)
        -> runners.run_local(input_csv, cores=...)          # today, unchanged
        -> runners.run_aml(input_csv, *, n_shards, cluster, ...)   # NEW
             |  splits input_csv into shard CSVs on storage
             |  submits one AML command job per shard:
             |     python -m fsd.workflows.shard <shard_csv_url> --cores N
             v  waits, aggregates status, raises on any failed shard
```

**Invariants (these are the spec's teeth):**
1. `fsd/workflows/task.py` — the unit of work — **must not change at all** for this spec. If it
   needs to, the design is wrong.
2. `fsd/workflows/shard.py` (new) is a *thin* entrypoint: resolve the shard CSV via `fsd.storage`,
   materialize it locally, call `runners.run_local`. No pipeline logic.
3. `runners.run_aml` is the only module in `fsd/` that imports `azure-ai-ml`, and it is imported
   **lazily inside the function** (as `runners` already does for the inference runners), so
   `import fsd` never requires the Azure extra.
4. `_check_local_seams` (api.py) relaxes to accept `runner="aml"`; unknown runners keep raising with
   the list of valid values.

### D4 — Identity on the node: **pure configuration — the storage seam needs no code change**

> ✅ **CONFIRMED ON THE CLUSTER 2026-07-21** — `runbooks/36-phase0-identity-smoke.md` green
> (AML run `mighty_seal_21kp83tsv7`). The token fsd obtained carried
> `xms_mirid = …/userAssignedIdentities/id<proj>-compute` and an `appid` matching `AZURE_CLIENT_ID`,
> so **the compute identity answered, through fsd's unmodified seams**. `fsd.storage` round-tripped
> npy + text on blob, and `rio_open` streamed a real MGRS-tile COG over `/vsiadls/`
> (EPSG:32633, 10980², uint16).
>
> **The negative control failed, which is the result we wanted:** with `AZURE_CLIENT_ID` removed, the
> bare `DefaultAzureCredential()` could not get a token — `ManagedIdentityCredential: Expecting
> value: line 1 column 1 (char 0)` (IMDS declining to guess among user-assigned identities). **So D4
> is load-bearing, not cargo cult** — had we shipped without it, every blob read on the cluster would
> have failed at runtime. Keep the env var, keep §7 test 5, and keep this paragraph as the reason.

⚠️ **This is the one place P1's proven path does not transfer *automatically*, and it would have
surfaced as a silent auth failure on the cluster rather than as an error anyone could predict.**

The problem: `fsd/storage/azure.py::_get_credential()` constructs a bare `DefaultAzureCredential()`.
That is correct on a laptop (`az login`) and on a host with a *system-assigned* identity. The AML
cluster has **only a user-assigned identity and no system-assigned one** (probe: `identityType:
UserAssigned`), and a user-assigned identity must be **selected by client ID** — never implicitly.
AML surfaces that client ID on the node as `DEFAULT_IDENTITY_CLIENT_ID`.

**Decision: the runner sets `AZURE_CLIENT_ID` in the job's environment. No `fsd` code changes.**

Verified against the installed `azure-identity` 1.25.3 rather than assumed —
`DefaultAzureCredential.__init__` already does:

```python
managed_identity_client_id = kwargs.pop(
    "managed_identity_client_id", os.environ.get(EnvironmentVariables.AZURE_CLIENT_ID))
```

So the existing zero-argument call **already honours `AZURE_CLIENT_ID`**, and the entire fix is one
environment variable in the job spec (`AZURE_CLIENT_ID = $DEFAULT_IDENTITY_CLIENT_ID`, or the value
resolved by the driver). Local behaviour is untouched — the variable is unset on a laptop, the kwarg
resolves to `None`, and today's chain runs exactly as before.

- Rejected: hardcoding `ManagedIdentityCredential` on the node — forks the auth path in two and
  breaks running the same image locally.
- Rejected: teaching `fsd` to read `DEFAULT_IDENTITY_CLIENT_ID` — it is an AML-specific variable
  name, and D3 invariant 3 keeps AML knowledge inside the dispatcher. *(If Phase 0 shows a
  researcher plausibly running fsd on AML **without** our runner, revisit — it is three lines. Not
  now: YAGNI.)*
- Rejected: putting the client ID in `fsd` config — it is a concrete `rise` identifier, and `fsd` is
  a public repo.
- **Validated first, before any runner code exists** (§6 Phase 0). It gates every blob read a job
  makes, and it is now the only genuine unknown left in the design.

### D5 — Job environment: **an AML Environment, built once, versioned**

The old plan's "container image + ACR push — the largest genuinely new build" was a *Batch*
requirement. AML builds and versions environments itself, so:

- Define an AML `Environment` from a base image + a conda/pip spec that installs the fsd wheel and
  its `[azure]` extra. AML builds it into the workspace registry and versions it.
- **The job does not carry fsd source.** It installs a built wheel, so what runs on the cluster is
  what `pip install fsd` gives a researcher — the demo's self-serve claim is then literally true
  rather than approximately true.
- Pin GDAL/rasterio via wheels (as the local venv does) rather than system GDAL; the reference-image
  and VSI behaviour spec 31 proved is wheel-GDAL behaviour, and changing GDAL provenance would put
  that evidence in question.
- A prebuilt Docker image in ACR remains available later as a *startup-latency optimization*
  (`az acr build` works server-side, no local Docker — registry is Basic SKU with public access).
  Not now: YAGNI.

### D6 — Data layout: the catalog is already self-describing, so a task needs only its slice

Spec 35 (shipped) made the catalog Parquet carry its declaration in the footer, which **removes the
question** `AZURE_INFRA.md` §7.4 was asking (how does a task learn what collection it is building?).
A task needs its geometry + its catalog slice, and both already travel as files.

Layout under the project container (all `abfss://`, all via `fsd.storage`):

```
<root>/imagery/...                     # source COGs (exists; runbook 34)
<root>/runs/<run_id>/input.csv         # the work list  (setup writes)
<root>/runs/<run_id>/shards/<k>.csv    # D2 shards      (run_aml writes)
<root>/runs/<run_id>/cubes/<cell_id>/  # datacube.npy + metadata.pickle.npy + timings.json
<root>/runs/<run_id>/_status/<k>.json  # per-shard result (D9)
```

`run_id` is caller-supplied or a UTC timestamp.

### D6a — Geometry I/O goes through `fsd.storage` (TODO #40, in scope by sign-off)

A cluster node has no `shapefiles/` checkout, so the three remaining raw-path geometry calls are
**blocking here**, not deferrable:

| Site | Today | Becomes |
|---|---|---|
| `workflows/create_datacube.py::setup` — reads the caller's ROI/label file | `gpd.read_file(shapefilepath)` | read bytes via `fs.open(..., "rb")` → `gpd.read_file(BytesIO(...))` |
| `workflows/create_datacube.py::setup` — writes the per-unit geometry | `shape_gdf.to_file(path, driver="GeoJSON")` | `shape_gdf.to_json()` → `fs.open(..., "w")` |
| `workflows/task.py::run_task` — reads the per-unit geometry | `gpd.read_file(shapefilepath)` | read bytes via `fs.open(..., "rb")` → `gpd.read_file(BytesIO(...))` |

- **A local path must behave exactly as it does today** — `fsd.storage` already routes `file://`
  transparently, so this is a seam correction, not a behaviour change. The existing local tests are
  the regression guard: if any of them change, the fix is wrong.
- Buffer reads (not a temp file) keep it to one code path for local and remote alike.
- This is the **last** raw-path I/O in the pipeline (spec 31 §6's URL-safety audit found no others),
  so it closes TODO #40 outright rather than shrinking it.
- **Not in scope:** the *model bundle* path (P6) and anything under `demos/`.

### D7 — Idempotency: **atomic-rename publish replaces `done.txt` sentinels**

Two facts settled from primary docs (`AZURE_INFRA.md` §8.1) drive this:

1. On an HNS account (ours), **rename is atomic**, and `If-None-Match: "*"` makes it fail-if-exists.
2. Azure **retries a task on node-recovery events independently of the configured retry count —
   even when it is zero.** So idempotency is mandatory, not prudent.

**Design:**
- The task writes artifacts to a per-attempt temp prefix, then **renames into the final path**. A
  reader therefore never observes a partial datacube; there is no window to reason about.
- **The resume signal is the artifact's own existence**, not a sentinel. A task whose final
  `datacube.npy` exists returns immediately.
- **Snakemake's `start.txt`/`done.txt` move to node-local scratch**, decoupled from
  `export_folderpath`. They are one invocation's bookkeeping, not durable state — the artifact on
  blob is the durable state. **This is exactly the fix TODO #41 speculated** ("an always-local
  scratch dir for sentinels, separate from the artifact destination") and it closes that item's
  second half: the local Snakefile's hard `RuntimeError` on a remote `export_folderpath` can then be
  removed, so **the local runner gains blob support as a side effect.**
- Duplicate concurrent execution of the same cube (possible under recovery retries) is harmless:
  the build is deterministic, and last-rename-wins produces an identical artifact.

### D8 — The driver runs on the laptop, over VPN

Simplest thing that works, and it is what `ROADMAP.md` §2.2 already argues for: the driver is a thin
job submitter; the data plane is cloud-colocated. No `vms` capability request (that would be the
infra ask this design otherwise avoids). AML compute instances already exist if a persistent driver
is ever wanted.

**Open (§8):** whether the AML control plane is reachable off-VPN. Does not change the design — it
changes whether the demo needs VPN on the presenting laptop.

### D9 — Telemetry: reuse the spec-11 seam, write it to blob

Each shard writes `_status/<k>.json` — `{shard, status, n_units, n_skipped, n_failed, seconds,
error}` — deliberately the **same shape as a run-book `_result.json`** (spec 24), so a cloud run is
diffed exactly like a local one and no new observability vocabulary is invented. The existing
`FSD_WRITE_TIMINGS` → `timings.json` sidecar already lands next to each cube and needs no change.

`run_aml` aggregates the shard statuses and **raises on any failed shard**, listing which.

### D10 — Preflight before the fan-out

`ROADMAP.md` §2.6's rule ("know before you spend") applies with more force once spend is real. Before
submitting anything, `run_aml` checks: cluster exists and is not deprovisioned; the environment
resolves; `storage` is reachable **and writable** from the driver; the work list is non-empty; and
`n_shards` ≥ 1. Cheap, and it converts a class of 20-minutes-later failures into instant ones.

---

## 4. What this does *not* change (the reuse ledger)

Stated explicitly, because it is the spec's central claim and should be checkable at review:

| Component | Change |
|---|---|
| `datacube/`, `raster/`, `bands/`, `catalog/`, `sources/` | **none** |
| `workflows/task.py` (the unit of work) | **none** (D3 invariant 1) |
| `workflows/_snakefiles/create_datacube/Snakefile` | sentinel path decoupled from artifact path (D7) |
| `storage/azure.py` | **none** — D4 is an env var the dispatcher sets |
| `workflows/runners.py` | `+ run_aml` |
| `workflows/shard.py` | new, thin (D3 invariant 2) |
| `api.py` | accept `runner="aml"` |

---

## 5. Deliverables

| # | Deliverable |
|---|---|
| 1 | ~~`storage/azure.py` change~~ — **none needed**; `run_aml` sets `AZURE_CLIENT_ID` in the job env (D4) |
| 2 | `workflows/shard.py`: in-job entrypoint, CLI-invokable (D3) |
| 3 | `workflows/runners.py::run_aml`: shard → submit → wait → aggregate → raise (D2/D3/D9/D10) |
| 4 | Snakefile: sentinels on local scratch; remove the remote-`export_folderpath` `RuntimeError` (D7) |
| 5 | `task.py`/builder: atomic-rename publish + skip-if-final-exists (D7) — **without changing `run_task`'s signature** |
| 6 | `api.py`: `runner="aml"` accepted end-to-end (D3) |
| 7 | `pyproject.toml`: `[aml]` extra (`azure-ai-ml`), kept out of the default install |
| 8 | AML Environment definition + how to (re)build it (D5) |
| 9 | Docs: `AZURE_INFRA.md` §7 questions marked resolved-by-this-spec; `LIMITATIONS.md` Scale rows; `TODO.md` #40/#41; `RECIPES.md` |
| 10 | Run-book `36-aml-runner.md` (§6 Phases 1–3; Phase 0 is done and green) |
| 11 | **TODO #40:** the three geometry I/O sites routed through `fsd.storage` (D6a); TODO #40 closed |

---

## 6. Validation — phased, because the expensive failure is discovering D4 late

Claude never runs these; each is a run-book the user runs and pastes back `_result.json` (spec 24).

- **Phase 0 — identity smoke.** ✅ **GREEN 2026-07-21** (`runbooks/36-phase0-identity-smoke.md`, AML
  run `mighty_seal_21kp83tsv7`) — D4 confirmed *and* shown to be necessary; the job environment built
  and the fsd wheel installed and imported on a cluster node, so D5's premise holds too.
  **One thing it did not prove:** the COG window it read (tile top-left corner) came back all-zero —
  almost certainly genuine granule-edge nodata, but it means "streamed *real pixel values*" is
  **not** yet evidenced, only "streamed successfully". Phase 1 covers it by construction.
  One AML job, one node, that does nothing but `fsd.storage` round-trip a small blob and `rio_open`
  one existing COG. **Proves D4 or kills it** before any runner code exists. Includes a **negative
  control** (the same credential *without* `AZURE_CLIENT_ID`) so the result distinguishes "the fix
  works" from "no fix was needed" — the latter deletes D4. The run-book maps all six plausible
  outcomes to the specific spec edit each one forces.
- **Phase 1 — one shard, one cube.** `n_shards=1` over a 1-row work list against the Austria
  archive. Proves the job wiring, the environment, and the atomic publish.
- **Phase 2 — resume.** Re-run Phase 1 unchanged; expect `n_skipped=1`, `n_units=1`, and an
  unmodified artifact timestamp. Proves D7 — the property that makes retries safe.
- **Phase 3 — real fan-out.** N shards over a real ROI; compare cube-for-cube against a local build
  of the same ROI (byte-identical `datacube.npy`, or an explained difference). **This is the demo.**

---

## 7. Tests (fast, synthetic, deterministic — `fsd/tests/`)

No test may require Azure. The AML client is injected/mocked at the `runners.run_aml` boundary.

1. Sharding: N units over K shards is a **partition** (no unit lost, none duplicated); round-robin
   assignment; `K > N` degrades to `N` non-empty shards.
2. `shard.py` resolves a `memory://` shard CSV and calls `run_local` with the expected arguments.
3. `run_aml` raises listing exactly the failed shards when a mocked submission reports failures.
4. `_check_local_seams` accepts `"aml"`, still rejects `"batch"`/typos with the valid-value list.
5. D4: the job spec `run_aml` builds carries `AZURE_CLIENT_ID` — asserted against the mocked
   submission, no network. (Pins the contract that would otherwise silently regress: nothing in
   `fsd/` reads that variable, so only this test explains why it is set.)
6. D7: skip-if-final-exists returns early without invoking the builder; a temp-then-rename publish
   leaves no temp path behind; an interrupted write leaves **no** final path.
7. The Snakefile no longer raises on a remote `export_folderpath` and directs sentinels to scratch.
8. **Non-vacuousness:** a mutation that makes sharding drop a unit must fail test 1 (this project's
   review standard — spec 35's review verified its own tests this way).
9. D6a: `setup` + `run_task` round-trip geometry through a **`memory://`** path (proving no raw-path
   dependency), and the existing local-path geometry tests still pass **unchanged** — the latter is
   the real guard, since the risk here is a regression on the local path, not a missing feature.

---

## 8. Open questions (do not block sign-off; resolve during implementation)

1. **Which ACR the AML workspace builds environments into** (workspace registry vs the project ACR).
   **Strong inference from Phase 0, not yet confirmed:** the build log shows a `docker login` using
   `--password`, but the *project* ACR has `adminUserEnabled: false` (fork probe) — so AML is
   near-certainly using its own **workspace** registry, not `acr<proj>`. Affects D5 mechanics only.
2. ~~**Whether an AML job must declare `identity: managed`**~~ ✅ **RESOLVED — no.** Phase 0 submitted
   a plain command job with **no `identity:` block** and the compute cluster's user-assigned identity
   was what answered on the node (`xms_mirid` proves it). Don't add the field.
3. **AML control plane reachable off-VPN?** (D8) — affects demo logistics, not design.
4. ~~**TODO #40 (ROI geometry via `fsd.storage`)** — inside this spec, or a prerequisite commit?~~
   ✅ **RESOLVED at sign-off (user, 2026-07-21): inside this spec.** Design → D6a, deliverable 11,
   test 9.
5. **Subscription VM-family quota (65 vCPU) vs AML cluster quota (6400).** Evidence says AmlCompute
   is governed by the latter; re-check at first scale-up rather than assuming.
6. **`n_shards` default** — `max_nodes` is the obvious choice; whether to oversubscribe (more shards
   than nodes, for straggler smoothing) is a Phase-3 measurement, not a design-time guess.

---

## 9. Best-practice alignment / sources

Per `CLAUDE.md`'s standing practice: what each source actually contributed.

- **[Path - Create, ADLS Gen2 REST](https://learn.microsoft.com/en-us/rest/api/storageservices/datalakestoragegen2/path/create)**
  — supplied the **atomic-publish primitive in D7**: rename via `x-ms-rename-source`, *"By default
  the destination is overwritten… To fail if the destination already exists, use a conditional
  request with `If-None-Match: "*"`"*, with `412 ConditionNotMet` / `409 PathAlreadyExists` as the
  loser's response. This is why D7 needs no lease or lock.
- **[ADLS hierarchical namespace](https://learn.microsoft.com/en-us/azure/storage/blobs/data-lake-storage-namespace)**
  — corroborated that rename is a single metadata operation on an HNS account, and independently
  validated D7's *shape*: it names write-to-temp-then-rename as the pattern Hive and Spark use for
  job output. We are not inventing a scheme.
- **[Error handling and detection in Azure Batch](https://learn.microsoft.com/en-us/azure/batch/error-handling)**
  — supplied the **hard requirement behind D7**: recovery-operation retries are *"independent of and
  are not counted against the `maxTaskRetryCount`. Even if the `maxTaskRetryCount` is 0, an internal
  retry due to a recovery operation may occur… all Tasks should be idempotent."* Turned idempotency
  from a nice-to-have into a non-negotiable, and rules out "just configure retries off."
- **[Set up service authentication, Azure ML](https://learn.microsoft.com/en-us/azure/machine-learning/how-to-identity-based-service-authentication?view=azureml-api-2)**
  — the source of **D4**: to use a user-assigned identity from job code you must supply its
  `client_id`, obtainable on the node from `DEFAULT_IDENTITY_CLIENT_ID`; also that an AML compute
  cluster carries *either* a system-assigned *or* user-assigned identities, which is why our
  UserAssigned-only cluster cannot rely on the default path.
- **[Authenticate Python apps with a user-assigned managed identity](https://learn.microsoft.com/en-us/azure/developer/python/sdk/authentication/user-assigned-managed-identity)**
  — confirmed the general rule beneath D4: a user-assigned identity is selected by client ID /
  resource ID / object ID, **never implicitly**. This is *why* the bare credential would have failed
  on the cluster.
- **`azure-identity` 1.25.3 source, read in this venv** (not a doc claim) — `DefaultAzureCredential.
  __init__` defaults `managed_identity_client_id` to `os.environ["AZURE_CLIENT_ID"]`. This is what
  **collapsed D4 from a code change to an environment variable**, and it is the reason deliverable 1
  is struck. Recorded because the two Microsoft pages above would each have led to a code change.
- **[Train ML models (SDK v2)](https://learn.microsoft.com/en-us/azure/machine-learning/how-to-train-model?view=azureml-api-2)**
  / **[azure.ai.ml.entities.Command](https://learn.microsoft.com/en-us/python/api/azure-ai-ml/azure.ai.ml.entities.command?view=azure-python)**
  — fixed **D3's submission shape**: `command(command=…, environment=…, compute=…)` +
  `ml_client.jobs.create_or_update(...)`, i.e. a plain command job runs an arbitrary CLI. This is
  what lets an AML job invoke our existing entrypoint with **no AML-specific entry-script contract**
  — the fact that makes D2's "reuse the local runner" viable and keeps AML out of the pipeline code.
- **[Manage AML environments (v2)](https://learn.microsoft.com/en-us/azure/machine-learning/how-to-manage-environments-v2?view=azureml-api-2)**
  — basis for **D5**: environments are built and versioned by AML from an image + conda/pip spec and
  referenced as `azureml:<name>:<version>`, which is why "container image + ACR push" is no longer a
  gating build item.
- **Internal, and the reason D1 exists at all:** `runbooks/36-runner-fork-probe.md` (measured quotas
  and identities) and `AZURE_INFRA.md` §3.1. Prior fsd measurements shaping D2's node sizing: specs
  11–13 (I/O- and decode-bound builds; throughput knee well under 64 cores).

*Searched: ADLS Gen2 rename atomicity/concurrency; ADLS Gen2 Path-Create conditional headers; Azure
Batch task retry/idempotency semantics; AML compute-cluster user-assigned identity + storage access;
azure-ai-ml SDK v2 command-job submission; azure-identity `DefaultAzureCredential` / `AZURE_CLIENT_ID`
managed-identity selection.*
