# Spec 38 — inference at scale on Azure ML (P4): dispatch the per-cell build+infer unit onto the cluster

> **Status: ✅ SIGNED OFF (user, 2026-07-23) — cross-validated + grilled (Q1–Q11). → NEXT: implement in a
> Sonnet@medium session against this spec** (§3 D1–D14, §4 reuse ledger, §5 deliverables, §7 tests; ADRs
> `docs/adr/0001`+`0002`; glossary `CONTEXT.md`). A later
> Sonnet@medium session implements against the signed-off text. This is the **inference sibling of
> spec 37** (download-on-AML): it dispatches the **already-built, already-proven-local** per-cell
> **build+infer** unit-of-work (spec 21 / P0.75) onto the same `rise` AML cluster, reusing spec 36's
> P2 datacube-fan-out runner. **Mode C** in `ROADMAP.md` §5.
>
> **Headline:** P4 is a **runner/dispatch swap** (`runner="aml"` config, no new *pipeline* algorithm)
> **plus the fixes the swap exposes** — three of which are *mandatory* (the node cannot otherwise
> produce a result on blob), and three cross-cutting correctness folds the user pulled in (a silent
> lost-update race, date-window type-safety, and a duplicate-dispatch race). Decisions locked with the
> user 2026-07-23 are marked **[LOCKED]**.
>
> **Prerequisites, all landed on `main`:** spec 21 (the local ROI verb this scales), spec 36 (the AML
> datacube runner + `shard_units` + Environment/identity/preflight/telemetry machinery), spec 37 (the
> download dispatcher this mirrors, incl. the input-staging-to-blob pattern), spec 35 (catalogs
> self-describe). Baseline to preserve: **382 passed / 3 skipped, ruff clean.**

---

## 1. The problem, stated honestly

`run_inference(roi=…)` already turns an ROI GeoJSON into per-cell crop-class COGs + a STAC catalog in
one call, **all local** (spec 21, verified). Its per-cell **build+infer** work is *already* a
runner-dispatched unit-of-work (`workflows/infer_task.py` + the `create_inference` Snakefile +
`runners.run_local_inference`) — deliberately, so P4 would be "just a runner swap" (spec 21 §Motivation,
SO-3). Spec 36 then built and **proved on the real cluster** the machinery that does the swap for the
*datacube build*: shard an `input.csv`, submit one command job per shard running the existing local
Snakemake orchestration on a node, aggregate `_status/<k>.json`, raise on failure — byte-identical
AML-vs-local across OS and architecture (PROGRESS ⭐, Phase 3b).

**The gap is dispatch — but not *only* dispatch.** Swapping the runner drags the per-cell task from a
laptop (local disk, one model, one Python env) onto a cold cluster node (blob I/O, the user's model,
a built Environment). Four things that were free locally are not free on a node, and the local synthetic
suite is green through every one of them (exactly the spec-36/37 lesson — *"an interface promising
something it does not deliver"*, only surfaced by real blob + a real cluster):

1. **The node cannot write the inference COG to blob.** `engine._write_output_cog` is **local-dst
   only** (TODO #17): it `os.makedirs(dirname(dst))` + `rasterio.open(raw_tif, "w")` + `os.remove` on
   the dst path. At scale `output.tif`'s dst is an `abfss://` URL → it fails. Mode C produces *nothing*
   on blob without a stage-local→convert→push (the pattern spec 34 uses for download COGs and spec 36
   D7 uses for `datacube.npy`).
2. **The `create_inference` Snakefile never got spec 36's D7 blob-safety fix.** It does *unconditional*
   `os.path.abspath(export_folderpath)` (breaks an `abfss://` path) and writes its `start.txt` /
   `done_infer.txt` sentinels **into** `export_folderpath` (a blob write per cell, and the wrong place
   for one-invocation bookkeeping). The datacube Snakefile was fixed to guard `abspath` behind
   `_fs.is_local` and move sentinels to node-local scratch, with `output` existence on blob as the
   durable resume signal. The inference Snakefile predates that fix (spec 21 < spec 36).
3. **The model + adapter code + its runtime deps must reach the node.** `bundle.load` resolves the
   adapter by `importlib.import_module(<module:attr>)` and `adapter.load()` reads its artifact by a
   **local** path (`joblib.load`). The spec-36 Environment (`fsd[azure,mpc]`) carries neither the user's
   adapter package nor its deps (`scikit-learn`/`joblib` live in the `model-example` extra, not
   `[azure]`/`[aml]`). A missing import surfaces as a node-side `ModuleNotFoundError` *after* cluster
   spin-up.
4. **The bundle lives on the laptop.** A node cannot see it (same lesson as spec 37's roi + creds) — it
   must be staged to blob and read on the node.

And the swap makes two *pre-existing latent* races **reachable at inference scale**, plus a type-safety
divergence — the three the user folded in (§ D8–D10).

**None of this changes the science.** The datacube build and the inference algorithm are byte-for-byte
the code spec 21/36 proved. P4 adds a dispatcher, a node entrypoint, and the I/O-seam fixes that let the
*existing* task run where its inputs and outputs are on blob.

---

## 2. Scope

**In scope**
- An **AML inference dispatcher** — `runners.run_aml_inference(...)`: a **thin step-4 swap** (D1a). It
  receives the **already-produced per-cell `input.csv` + `bundle_path`** from `_run_inference_roi`
  (tiling + `setup` + collect/STAC stay runner-agnostic on the driver), and does only: stage the bundle
  to blob → `shard_units` the cells → submit **N** per-shard jobs each running a node-side inference
  entrypoint → wait → aggregate `_status/<k>.json` → raise on failure. Reuses spec 36's
  `_aml_submit_and_wait` / Environment (D4) / identity (D4′) / preflight scaffold / telemetry, and
  `shard_units`.
- A **node-side inference entrypoint** — `python -m fsd.workflows.infer_shard …`: `fs.get` the shard
  CSV + bundle to node-local scratch, call the existing `run_local_inference`, write `_status/<k>.json`.
  Thin, mirrors `workflows/shard.py` (D2).
- `api.run_inference(roi=…, runner="aml", runner_kwargs=…, storage="abfss://…")` end-to-end (D14).
- **Three mandatory I/O-seam fixes** the swap exposes: remote-dst inference COG (D5, TODO #17), the
  `create_inference` Snakefile D7 blob-safety fix + a skip-if-final-exists in `infer_task` (D6), and
  bundle staging + `fs.get`-to-scratch (D3).
- A **dedicated inference Environment** carrying the adapter + its deps, with a **model-free driver
  preflight + a one-node adapter-import smoke** before the fan-out (D4, D11).
- **Bundle loaded once per job**, reused across the job's cells — closes TODO #25's root cause (D7).
- A **preflight** (D11) + a **`max_cells` guardrail** that fails cheap on the driver.
- **Three cross-cutting folds pulled in by the user (2026-07-23):** fix the download-path catalog
  lost-update race (D8, TODO #51 — *actually* fixed, not just named); normalize date windows to
  `Timestamp` at the API boundary with fail-fast validation, and sweep the repo for other
  natural-datatype smells (D9/D10, TODO #52); dedupe the setup manifest + a dispatch-time duplicate
  guard (D13, TODO #53).

**Not in scope — and deliberately so**
- **`create_training_data(roi=…)` at scale.** Labelled field shapes *are* the geometries — no ROI→cell
  tiling — so there is nothing new to fan out (spec 21 note). **[LOCKED]** P4 is the *inference* ROI verb.
- **Infer-only (pre-built cubes) fan-out on AML** (spec 22). A trivial variant of this dispatcher
  (skip the build), but the demo target is the ROI build+infer path; noted as Open Q, not built.
- **Model *training* on the cluster.** Permanently the user's side (ROADMAP §1). fsd runs inference.
- **A serving dashboard / tile server** (P5, spec 29/30). P4 lands COGs + STAC on blob; serving is next.
- **Any `raapid-infra` change beyond building the inference Environment.** Cluster + identity already
  exist and are proven (spec 36 Phase 0). The inference Environment is an `az ml`/`az acr` build the
  operator runs — same shape spec 36/37's Environment build already is.
- **GDAL VSI *writes* to blob** (TODO #39). D5 deliberately writes the COG on node-local scratch and
  `storage.transfer`s it — no remote `rasterio.open(mode="w")`.

---

## 3. Decisions

### D1a — `run_aml_inference` is the **thin step-4 dispatcher**; tiling/setup/collect stay in `_run_inference_roi` [LOCKED 2026-07-23]

`_run_inference_roi` is already cleanly staged: (1) preflight, (2) `_ensure_bundle`, (3) tile + `setup`
→ `input.csv`, (4) `run_local_inference(input.csv, …)`, (5) collect + STAC. Steps 1–3 and 5 are
**runner-agnostic**; only step 4 is the runner (spec 21 SO-3 built it exactly for this). P4 **swaps step
4** for `run_aml_inference(input_csv, bundle_path, …)` — the AML dispatcher receives the
already-produced manifest + bundle and owns *only* stage-bundle → shard → submit → aggregate → raise. It
does **not** re-tile or re-`setup` (that would duplicate driver logic and drift from the local path).
This is the same sibling shape spec 37's `run_aml_download` has to the local download path, and it keeps
the local↔AML equivalence a one-call difference (the property spec 36 Phase 3b proved for datacubes).
Consequence inherited, not re-litigated: `setup` writes each cell's `geometry.geojson` + catalog slice
to blob **from the driver** (TODO #54, measured ~79 ms/cell parallelized — fine to low-thousands of
cells; cluster-side setup stays parked until tens of thousands).

### D1 — Dispatch shape: fan out over **cells**, reuse spec 36's runner verbatim

The datacube fan-out (spec 36 Phase 3) showed per-field build is **compute-bound and near-uniform** —
straggler spread only **1.62×** at 16 nodes (vs 16.7× for the download I/O fan-out), because each cell's
build is roughly equal work. Inference adds a fixed model-eval per cell on top of the identical build,
so the per-cell cost stays near-uniform → **round-robin `shard_units` self-balances**, no oversubscription
needed. `run_aml_inference` therefore mirrors `run_aml`: shard the per-cell `input.csv` into
`n_shards` (default the cluster's `max_instances`), one command job per shard. **No CDSE, ever** — the
cells read imagery from the blob catalog (SO-6 / spec 21), so there is no per-credential connection cap
to reason about (spec 37 D1's CDSE concern does not apply). This is the simplest possible dispatch, and
it is the *same* dispatch spec 36 proved.

### D2 — The node entrypoint: `python -m fsd.workflows.infer_shard` (mirrors `shard.py`)

`workflows/infer_shard.py` (new) carries **no pipeline logic** (the property that kept spec 36 D2/D3
honest). It: `fs.get`s the shard CSV to node-local scratch; `fs.get`s the staged bundle folder to
node-local scratch (D3); calls the **existing** `runners.run_local_inference(local_csv, cores,
bundle_path=local_bundle, cubes_per_task=…)`; and writes `<root>/runs/<run_id>/_status/<k>.json` (D9,
the spec-24/36 `_result.json` shape). `run_local_inference`, `infer_task`, and the `create_inference`
Snakefile are the code spec 21 proved — this entrypoint only invokes them on a node. Its docstring
already promises this contract (`runners.py:115`: *"Azure Batch (P4) dispatches this same task; only
this runner is swapped"*) — D2 honours it.

### D3 — Bundle staging: driver uploads to blob; node `fs.get`s to local scratch, then `bundle.load` [LOCKED]

A node cannot see the laptop's bundle (spec 37's roi/creds lesson). Design:
- **Where:** `{root}/runs/{run_id}/_bundle/`. The bundle is **self-describing** — `bundle.json` +
  artifacts referenced by **relative** hrefs (spec 18 §3.4, confirmed: `bundle.py` records
  `os.path.basename(src)`, hardcodes no absolute path).
- **Who uploads:** the driver, before submitting (spec 37 Phase-0 shape). `_ensure_bundle` already
  writes through `fsd.storage` (`bundle.save` uses `fs.open` for the manifest and dst artifacts), so a
  live adapter auto-saves **straight to blob**; a pre-existing local bundle is uploaded folder-wise. So
  `_ensure_bundle(model, output_folderpath=<blob root>, …)` needs **no new write code** — it already
  targets the storage seam.
- **Why fetch-to-scratch, not read-in-place:** `bundle.load` reads `bundle.json` via `fs.open` (blob-OK),
  **but** it then injects `os.path.join(bundle_path, rel)` onto `adapter.artifacts` and calls
  `adapter.load()`, which for the demo RF adapter is `joblib.load(<path>)` — a **local** read. So the
  node **materialises the bundle to node-local scratch**, then calls `bundle.load(<local_dir>)` — the
  same "materialise the input to scratch, then run the unmodified reader" move `infer_shard` uses for
  the CSV.
- **Fetch = manifest-driven, no new primitive [LOCKED 2026-07-23].** `fsd.storage.get` is **single-file**
  (`fs.get_file`, `fs.py:128`), **not** recursive — so "get the whole `_bundle/` prefix" is not one call.
  The node instead: `fs.open`s the staged `bundle.json`, and for the manifest + each file the
  **`artifacts` map names** (`bundle.json` *is* the bundle's table of contents — see the glossary),
  `fs.get`s it to scratch, then `bundle.load(<local_dir>)`. The manifest already enumerates every file in
  the bundle, so **no directory walk / listing is needed** and **no new seam surface** is added. Rejected
  alternative: a recursive `fs.get(..., recursive=True)` (native to fsspec/adlfs) — a cleaner *general*
  primitive, but a seam expansion to justify only when a second caller needs a recursive fetch (YAGNI);
  noted as the fallback. Either way the **loader is untouched** — teaching `bundle.load` to stream
  artifacts through `fs.open` is a larger, model-agnostic change (every adapter's `.load()` would have to
  use the seam) and stays **out of scope** (Open Q, cf. TODO #47's "one shared reader").

### D4 — A **dedicated inference Environment** carries the adapter + its deps [LOCKED]

The spec-36 datacube Environment is `fsd[azure,mpc]` — generic build infra, no model. Inference needs
the **user's adapter package** (resolvable by the bundle's `module:attr`) *and* its runtime deps (the
demo needs `scikit-learn` + `joblib`; a deep model would need `torch`, multi-GB). **[LOCKED]** these go in
a **second, inference-specific AML Environment** = `fsd[azure,mpc]` **+ the adapter installed as a pip
package + its deps**, rather than bloating the generic build image with one model's dependency closure.
Rationale: keeps the build image lean and model-independent; makes "swap the model" = "build a new
inference Environment", a clean unit; matches "model training stays on the user's side" — the user
delivers an installable adapter package, fsd builds an Environment from it. The adapter is **not** shipped
inside the bundle (the bundle carries weights + a code *reference*, spec 18 §3.4) — it is a pip
dependency of the Environment, exactly like `fsd` itself is.

> **Mechanism = the spec-36/37 Docker build context, extended (cross-validated 2026-07-23).** fsd is on
> the **v2** AML SDK (`azure-ai-ml`), where an Environment is built from a **Docker build context**
> (`build.path` + `dockerfile_path`) — established when spec 36 proved *"the Environment must contain
> fsd itself"* (PROGRESS). The MS "private Python packages" guidance (`Environment.add_private_pip_wheel`
> + `CondaDependencies`) is the **v1** API and does **not** apply here. So the inference Environment is
> the spec-36 Dockerfile with two added `pip install` lines — the adapter package + its deps — not a new
> mechanism. For the EuroCrops demo whose adapter is a single file in `examples/`, "installable package"
> may mean a thin local package (or a `pip install .` of a tiny wheel); a real user brings their own.

**Responsibility split — bundle and image stay decoupled [LOCKED 2026-07-23]:**
- The **model author owns the image's *contents*** — their adapter must be an **installable package with
  pinned deps**, alongside the **bundle** (weights + `module:attr` ref + spec). These are the author's
  two deliverables; the adapter code is a **pip dependency of the Environment**, never shipped inside the
  bundle (spec 18 §3.4).
- The **operator owns the *act* of building + registering** the AML inference Environment — a **Phase-0
  run-book step** (§6), identical in shape to how the fsd datacube Environment is already built in
  spec 36/37. Claude never runs `az ml`/`az acr` (`CLAUDE.md`).
- The **dispatcher references the Environment by name** (`run_aml_inference(environment=<name>, …)`),
  exactly as `run_aml` takes `environment=` today — **no per-run image build**. An image is built once
  per adapter-version and serves many runs/bundles of that model family.
- **Why decoupled, not "bundling builds the image":** an image built at bundle-time or node-cold-start
  would rebuild per run / `pip install` per node, losing build-time validation and slowing every cold
  node. D4/D11 front-load dep installation to **build time**, gated by the D11 one-node adapter-import
  smoke — a missing `sklearn` fails once at build/smoke, not on every fan-out node.
- **Where the coupling lands later: P6 `deploy()` [LOCKED — user, 2026-07-23].** `deploy(bundle)`
  (today a stub, `api.py:899`) is the appropriate home for *building the image*: it will "register the
  bundle **and** build/ensure an inference Environment for its adapter", fusing the author's two
  deliverables into one call. **For P4 the two stay separate** (bundle = portable data staged per run;
  Environment = an operator run-book step); P6 automates the build that P4 does by run-book. The bundle
  **format** does not change (spec 18 F5) — `deploy` adds image-build + registration around it.

> **The failure this pre-empts:** a missing `sklearn` or an un-importable adapter is a node-side
> `ModuleNotFoundError` *after* the cluster spins up — the precise failure spec 37's smoke job exists to
> catch. D11's one-node adapter-import smoke is the gate.

### D4′ — Node identity: reuse spec 36 D4 verbatim (`AZURE_CLIENT_ID`, no storage change)

Every job reads the catalog + imagery + bundle from blob and writes COGs + STAC to blob. This is the
exact need spec 36 D4 solved and proved on the cluster (Phase 0): the dispatcher sets `AZURE_CLIENT_ID =
<compute identity client id>` in the job env; `storage/azure.py`'s bare `DefaultAzureCredential()`
honours it. **`storage/azure.py` changes by zero lines.** `identity_client_id` is caller-supplied, never
hardcoded (public repo). No Key Vault is needed (inference reads no CDSE creds — SO-6), so spec 37 D5's
secret machinery is **not** reused here.

### D5 — Remote-dst COG lives in `raster.cog.to_cog`, not `engine` (closes TODO #17) — MANDATORY [LOCKED 2026-07-23]

**`raster.cog.to_cog` — the single "produce a COG at `dst`" chokepoint — learns a remote-dst path**;
`engine` and `api` stay unchanged callers. When `dst` is a remote `fsd.storage` URL: convert on
**node-local scratch** (the existing local path, byte-for-byte), `storage.transfer` to a remote `.part`,
then `fs.rename` onto the final path (atomic, reusing spec 36 D7's rename primitive) and clean up
scratch. Local dst = today's `os.replace` behaviour, unchanged.

**Why `to_cog`, not `engine._write_output_cog` (Q4):**
- One chokepoint fixes **both** inference-output-to-blob sites: the per-cell `output.tif`
  (`engine._write_output_cog` → `to_cog`, on the **node**) **and** the `merged.tif`
  (`api._merge_outputs` → `to_cog`, `api.py:593`, on the **driver**) — the second of which D5's earlier
  engine-local draft *missed*, and which fails identically on a blob `output_folderpath`.
- Keeps `engine`/`api` **storage-agnostic** — the "pixel I/O is local; publish via the seam" exception
  (`CLAUDE.md`) lives next to the pixel I/O, in `raster/cog`.
- **Reusable** for TODO #15b (remote-dst *download* COG), the same pattern.
- **No download regression:** `cdse`'s `to_cog` calls always target *local* scratch (`cdse.py:490`; the
  whole-run upload is `_push_scratch_to_remote`), so a remote-aware `to_cog` never changes them.

This is the *third* instance of the "pixel I/O local, publish via the seam" pattern (spec 34
`_push_scratch_to_remote`, spec 36 D7 `_save_npy_atomic`, now `to_cog`) — now unified in the raster
layer. Nodata/dtype/CRS/transform are unchanged (from the datacube metadata, spec 28). Closing #17 is
what lets Mode C put a result — per-cell or merged — on blob at all.

### D6 — `create_inference` Snakefile D7 fix + `infer_task` skip-if-final-exists — MANDATORY

Apply spec 36 D7's treatment to the inference Snakefile, so a remote `export_folderpath` is safe and a
fresh-node resume works:
- Guard `os.path.abspath(export_folderpath)` behind `_fs.is_local(...)` (idempotent for local; never
  corrupts an `abfss://` path) — the exact guard the datacube Snakefile uses.
- Move `start.txt` / `done_infer.txt` sentinels to **node-local scratch** keyed by
  `sha1(export_folderpath)` — they are one invocation's bookkeeping, not durable state.
- The **durable** "this cell is already inferred" signal becomes the **`output.tif` existence on blob**,
  checked by a new **first-line skip in `infer_task.run_infer_task`**: `if not overwrite and
  fs.exists(output_filepath): return output_filepath` (mirrors `task.run_task`'s first-line
  skip-if-`datacube.npy`-exists, `task.py:64`). Today `infer_task` has **no** such skip — resume relies
  entirely on the Snakemake sentinel, which a fresh node does not have. This is what lets a shard retried
  on a fresh node skip every cell it already finished (spec 36 D7's whole point, not yet true for infer).
- **Resume granularity is per-cell, decoupled from group size (D7) [LOCKED 2026-07-23].** Because D7
  groups K cells into one process, the `output.tif`-existence skip runs **per cell inside the group's
  loop** — so a group that crashes at cell *i* of K, re-run or re-dispatched to a fresh node, skips
  cells `0..i-1` (their `output.tif` exists on blob) and redoes only the unfinished tail. A finished cell
  is never re-inferred merely because it shares a group with a failed one. The Snakemake group sentinel
  stays pure intra-invocation bookkeeping (node-local scratch); the per-cell `output.tif` is the only
  durable signal. Cost: one `fs.exists` blob HEAD per cell before build+infer — cheap, and only
  meaningful on re-runs.

### D7 — Bundle loaded **once per job**, reused across the job's cells (closes TODO #25 root cause) [LOCKED]

Today ROI mode reloads the bundle **once per cell**: `_run_inference_roi` calls `run_local_inference`
**without forwarding `cubes_per_task`** (`api.py`, the exact bug TODO #25 root-caused), the
`create_inference` Snakefile runs **one cell per job**, and `infer_task` calls `bundle.load` **directly**
(not the cached `engine._adapter_from_bundle_cached`). At AML scale with a cold node per shard, that is
one bundle load **per cell** — negligible for the RF demo (sub-second `joblib.load`) but ruinous for a
heavy model (multi-GB load × cells-per-node). **[LOCKED]** fix it now:
- `run_local_inference` **forwards `cubes_per_task`** into the Snakefile config (stop silently dropping it).
- The `create_inference` Snakefile **groups `cubes_per_task` cells per job**, each job one `infer_task`
  process that **loops** its group, loading the bundle **once** via the per-process cache
  (`engine._adapter_from_bundle_cached`, already used by the infer-only path spec 22) instead of
  `bundle.load` per cell. `cores` = how many groups run **concurrently** on the node.
- **The goal is "not once per *cell*", not "once per node" [LOCKED 2026-07-23].** On a node with
  `cells_on_node` cells and `node_cores` cores: bundle loads = `ceil(cells_on_node / cubes_per_task)`,
  intra-node parallelism = `min(cores, n_groups)` — a direct trade-off. **Default: load-per-core** —
  group size ≈ `ceil(cells_on_node / node_cores)`, `cores = node_cores`, so the node runs `node_cores`
  groups in parallel and the bundle loads `node_cores` times per node (negligible for the RF demo's
  sub-second `joblib.load`, and the node stays fully busy). **Opt-out for heavy models: load-once-per-node**
  — `cores=1` + one whole-shard group loads the bundle once, accepting serial cells (right when a
  multi-GB load dominates and a single predict already uses all cores/GPU). `infer_shard` computes the
  default group size from the shard size and the node's core count; both are exposed as knobs.

Net: bundle loads drop from **once per cell** (today's #25 pathology — N cells → N loads) to **once per
core per node** (default) or **once per node** (heavy-model opt-out). This is a real pipeline change (the
Snakefile grouping + `infer_task`'s cached loader), justified by the user's decision that reload economics
matter at scale — but it *unifies* with the infer-only path's existing grouping rather than inventing a
mechanism.

### D8 — Fix the download-path catalog lost-update race (TODO #51) — *actually* fixed [LOCKED]

**Folded in at the user's decision** ("a silent lost-update race is unacceptable"). `run_aml_download`
(spec 37) hands every MPC shard the **same** `--catalog` path; each shard finishes and calls
`TileCatalog.append`, an unsynchronised **read-whole-parquet → concat → write-whole-parquet**
(`catalog/catalog.py:112-136`) with last-writer-wins blob semantics — so two shards whose appends overlap
produce a catalog that declares only one of them. The **bytes** land (each transfer is independent), so
nothing errors; the archive silently **under-declares itself** and every downstream datacube omits the
lost granules' timestamps. Measured *not* to have fired on one 16-shard run (PROGRESS) — negative evidence
from a single trial, **not** safety.

**Fix [TODO #51 candidate (1); MPC-only — LOCKED 2026-07-23]:** each MPC shard's `run_shard` writes its
**own** `{root}/runs/{run_id}/shards/catalog-<k>.parquet` (single writer, no lock); the **driver merges**
them into the canonical `catalog.parquet` after `_aml_submit_and_wait` by reading each shard catalog and
calling the **existing** `TileCatalog.append` (upsert-by-id, `catalog.py:112`) **sequentially** — a
deliberate single-writer *serialization*, precisely so it is not a race. This matches the existing
`_status/<k>.json` per-shard pattern — no locking primitive, no ETag/lease (which TODO #50 shows goes
badly on `abfss://`).
- **CDSE is untouched (single writer).** Spec 37 runs CDSE as **one** job writing the canonical catalog
  directly, so the lost-update cannot occur; adding a merge step to a proven single-writer path buys
  nothing. Only MPC's `run_shard` changes — matching spec 37's deliberate per-source asymmetry (D1),
  not forcing uniformity.
- **Invariant the merge relies on:** every shard's `catalog-<k>.parquet` is stamped with the **same**
  source declaration (spec 35), so the sequential `append` into the canonical never trips `append`'s
  "declaration mismatch" `ValueError`. Tested in D10-adjacent test 10.
- It also removes the append as a fan-in serialization point at large N.

**Scope note — this is the download path, not inference.** P4 inference has **no** catalog-append race:
`setup` **reads** the catalog (never appends), each cell writes `datacube.npy`/`output.tif` to
**distinct** paths, and the run-level STAC assembly (`_finalize_outputs` → `write_stac_catalog`) runs on
the **driver after fan-in** = **single writer**. So the "no unsynchronised fan-in write" audit across P4
comes back clean for inference by construction; the only instance to fix is the download dispatcher. The
single-shard CDSE path and all local runs are one-writer and unaffected.

### D9 — Normalize date windows to `Timestamp` at the API boundary, fail-fast (TODO #52) [LOCKED]

**Folded in at the user's decision** (*"a variable should carry the datatype natural to it — dates are
`datetime`/`Timestamp`, never strings"*). Today `api.download` / `api.run_inference` forward the caller's
`startdate`/`enddate` **raw** to the sources, which hand them straight to
`pystac_client.search(datetime=[start, end])`. pystac applies STAC's rule: a date-only **string**
expands to the **end** of its day (`2019-01-01T23:59:59Z`) while a **`datetime`/`Timestamp`** is an exact
instant (`2019-01-01T00:00:00Z`) — so the **same call means a one-day-different window depending on the
caller's *type***, and depending on the *runner* (the CDSE AML node path normalises in
`workflows/download.py`; the MPC path does not — the concrete divergence TODO #52 documents). Worse,
`_check_window` / `compute_n_timestamps` currently call `pd.to_datetime(..., utc=True)` **for validation
only and throw the parsed value away** (`api.py:76-77,120-121`).

**Fix [strategy LOCKED 2026-07-23]:** coerce at each boundary where a value enters the Python domain,
`Timestamp`-typed and trusting inward:
- **API verbs** (`api.download`, `api.run_inference`): a shared `_normalize_window(startdate, enddate) →
  (Timestamp, Timestamp)` helper, called as the **first** thing, tz-aware UTC via `pd.to_datetime`.
- **Node CLIs** (`workflows/download.py`, `infer_task`): parse argv → `Timestamp` immediately (CDSE's node
  path already does; the `#52` bug is that MPC's did not — this makes both identical). This is a *second*
  boundary that protects direct CLI use; it is **not** the fail-fast the API path relies on (see below).
- **Inward is typed and trusting:** `_check_window`/`compute_n_timestamps` receive the parsed `Timestamp`
  (kill the parse-then-discard); sources (`cdse.download`/`mpc.download`) are typed to accept
  `datetime`/`Timestamp` and do **not** re-coerce — re-coercing inward would mask a boundary bug. A string
  reaching a source is a boundary defect to fix, not to absorb.

**Fail-fast means fail *on the driver, before any AML job* [LOCKED 2026-07-23].** `_normalize_window`
raises a clean **`PreflightError`** (`"startdate=… is not a valid date"`), not a raw pandas traceback, and
does so **before** `run_aml_inference`/`run_aml_download` dispatch — because an AML **node cold-start is
40–380 s** (TODO #48), so a check that only fires *after* a node starts is not "fast." Validating an
unparseable date must abort on the driver, at the API entry, in milliseconds. This also gates the other
window checks (`compute_n_timestamps` cannot run on garbage), so the coercion is *upstream* of the
aggregated preflight. The window is then identical regardless of caller type **or** runner — closing the
CDSE/MPC divergence at the source.

### D10 — Sweep the repo for other natural-datatype smells (TODO #52 generalised) [LOCKED]

**Folded in at the user's decision** (*"if there are other places where natural datatypes are not being
used, highlight them"*). The **principle**: *normalize to the natural type at the Python API boundary; at
process/serialization boundaries (argv, CSV, JSON) parse into the natural type immediately on read, and
never pass the raw string deeper.*

**The sweep's target [scoped 2026-07-23, grep-verified]:** the *specific* `#52` antipattern — **a value
whose natural type is `datetime`/`Timestamp` forwarded in a raw/looser form into a type-sensitive API, or
coerced-then-discarded.** It does **not** license refactoring the legitimate string-at-CLI/CSV boundaries
(those are correct). Deliverable: a short **audited** table — each candidate marked *violation* (fix) or
*verified-clean* (log, with why).

| Candidate | Where | Verdict (grep-checked 2026-07-23) |
|---|---|---|
| **`startdate`/`enddate`** | `api.download`/`run_inference` → sources → pystac | **VIOLATION → fix** (D9): coercion in `_check_window` was **discarded**, raw string forwarded into pystac's type-divergent `datetime=`. |
| **`dt`** (STAC output-item datetime) | `run_inference` → `_finalize_outputs` → `cog_outputs_to_items` | **Audit** — check for the same raw-forward smell; fix if found. |
| `bands` `list[str]` | `api`/`create_datacube`/`task`/`infer_task`/`download` | **VERIFIED CLEAN → log.** Typed `list[str]` in every signature; string only at CSV (`",".join`) + argv (`--bands …`), coerced back on read (`.split(",")`). Round-trips list→(serialized)→list; no internal violation. |
| `scl_mask_classes` `list[int]` | same | **VERIFIED CLEAN → log.** Same shape; parse-on-read is `[int(v) for v in …split(",")]` (`task.py:127`, `infer_task.py:120`). |
| `mosaic_scheme`/`source`/`merge`/`runner` | multiple | **Not datetime-typed** — out of this sweep's target; already validated sets (`merge` ∈ {False,True,"reproject"}; `runner`/`source` checked). Log. |

So "fix dates, log the rest" is **evidence-based, not conservative**: dates (+ whatever `dt` turns out to
be) are the only genuine violations; `bands`/`scl` already follow the principle. The type-safety win lands
exactly where the cluster surprise lived.

### D11 — Preflight before the fan-out (§2.6/§2.7): fail cheap on the driver

**The invariant [LOCKED 2026-07-23]: every check that *can* run on the driver *must* run on the driver,
before any AML job is submitted.** An AML node cold-start is **40–380 s** (TODO #48), so a check that only
fires after a node starts is not "failing fast" — it burns minutes and cluster spend to report what a
millisecond driver-side check would have caught. The **only** check that genuinely needs a node is the
adapter-import smoke (it validates the *node's* Environment), and it is run **once on one node** before
the N-node fan-out. Mirror spec 36/37's driver-side cheap checks, plus inference specifics — all *before*
a node is paid for:
- **Compute/env:** cluster ready; the **inference** Environment resolves (D4); blob `root` reachable
  **and writable**.
- **Model (model-free):** `bundle.read_spec` parses; `T == n_timestamps` and `bands ⊇ required_bands`
  (these already exist in `_run_inference_roi`'s preflight — **hoist them ahead of dispatch**).
- **Imagery present:** the catalog covers the ROI/window (the D13-guardrail message already built,
  `api._imagery_missing_message`) — **inference never calls CDSE** (SO-6), so a gap is "run download
  first", not a fetch.
- **Guardrail:** a `max_cells` cap (analogous to spec 37's `max_tiles`) refuses an ROI that tiles into
  more cells than intended — fail before dispatching thousands of jobs.
- **Adapter-import smoke (the one that needs a node) — on by default, `skip_smoke` opt-out [LOCKED 2026-07-23]:**
  a **one-node** job that `fs.get`s the bundle, `bundle.load`s it (resolving the adapter import in the
  *real* Environment), and runs a trivial predict — run **once before the N-node fan-out** as a
  *separate* job (folding it into the first shard would fail *after* a node starts, breaking the D11
  invariant). This is the only check the driver cannot do alone (D4 — the driver's venv is not guaranteed
  to mirror the Environment image). **Default on** (the first run of a new/changed Environment must catch
  a node-side `ModuleNotFoundError` before paying for N nodes); **`skip_smoke=True`** lets an operator who
  has already proven an Environment good skip the ~40–380 s spin-up on repeat runs. Not off-by-default —
  the demo's first cluster run is exactly when the Environment is unproven.

### D12 — Idempotency & resume: `output.tif`-existence + the #53 dedupe/guard

Resume rests on two things: D6's `output.tif`-existence skip (a fresh-node re-dispatch skips finished
cells), and **D13** (no cell is dispatched twice). A job that runs to completion is safely re-runnable; a
crash mid-cell loses only that cell's un-pushed scratch (each cell publishes atomically, D5). Same honest
limitation shape as spec 37 D8, but cheaper (a crashed shard re-runs only its cells).

### D13 — Fold in TODO #53: dedupe the setup manifest + a dispatch-time duplicate guard [LOCKED]

`create_datacube.setup` **appends** to `input.csv` with no dedupe (`create_datacube.py:196`), and
`shard_units` round-robins — so a duplicated cell lands on **two shards running concurrently**, both
building+inferring the same cell and writing the same `output.tif`/`datacube.npy` with **no lock**
(the D8 lost-update shape, on the **inference output** this time). Reachable by re-running a
partially-failed run — exactly when an operator re-runs. P4 rides the same `setup()` path, so **this is
P4's race, not a background nit.**

**The keying makes two distinct hazards [analysed 2026-07-23].** `setup` keys `export_folderpath =
run_folderpath/<id>` — by **`id` alone** (`create_datacube.py:121-124`), not by the params. So:
1. **True duplicate** — same `id` *and* same params → identical work, same folder → collapse to one.
2. **Conflict** — same `id`, *different* params → **same `export_folderpath`, different intended content**
   → a malformed manifest (which `datacube.npy` should that folder hold?); today silent last-writer-wins
   or the concurrent double-write. TODO #53's "dedupe on id+params" treats these as distinct and **keeps
   both** — which does **not** prevent the collision, since both still target the same `id`-keyed folder.

**Fix — two parts, each keyed on the right thing [LOCKED 2026-07-23]:**
- **Dedupe on the full content identity** — `id` + `startdate` + `enddate` + `bands` + `mosaic_days` +
  `mosaic_scheme` + `scl_mask_classes` — keeping the newest. Collapses exact re-run duplicates (idempotent
  re-run) while preserving the deliberate "top up with new shapes" feature.
- **Guard on `export_folderpath` uniqueness** (≡ `id`, given the keying): after dedupe, if two
  *distinct-content* rows still map to the same `export_folderpath`, **raise a `PreflightError`** on the
  **driver** (D11 invariant) — a malformed manifest that would be a concurrent write. Keying the guard on
  the **actual shared resource** (the output folder) is stronger than TODO #53's literal "refuse duplicate
  unit ids": it makes the dangerous *two-units-one-folder* case impossible to dispatch. Applies in
  `run_aml_inference` / `run_local_inference` / `run_aml` (same exposure). *(Supporting
  same-`id`-different-params in one run would need per-params subfolders — out of scope; rejecting it is
  correct until then.)*

Regression tests modelled on the fresh harness in `tests/test_workflows.py`
(`test_setup_manifest_order_is_shapefile_order_not_completion_order`,
`test_setup_reads_catalog_once_regardless_of_shape_count`).

### D14 — `api.run_inference(runner="aml")` end-to-end

`run_inference` gains `runner="aml"` + `runner_kwargs` for **ROI mode** (mirrors spec 37's `api.download`
change). Today it forces `_check_local_seams(runner, storage, storage_allowed=False)` — inference-on-blob
was explicitly P4 (`api.py:97-98`). P4 **is** that phase: relax the guard so ROI mode + `runner="aml"`
accepts `storage="azure"`/an `abfss://` root and routes to `run_aml_inference`; the pre-built-cubes path
and local ROI mode are unchanged. Unknown runners still rejected.

---

## 4. What this does *not* change (the reuse ledger)

| Component | Change |
|---|---|
| `workflows/infer_task.py` (the build+infer unit) | `+` first-line skip-if-`output.tif`-exists (D6); `+` a grouped/cached-bundle loop for `cubes_per_task` (D7). **No build or inference *algorithm* change.** |
| `workflows/task.py`, `datacube/`, `raster/`, `bands/`, `catalog/` query | **none** — the build path is spec 36's proven code (`catalog.append` changes only for D8's per-shard-merge on the *download* path) |
| `raster/cog.py::to_cog` | `+` remote-dst branch (convert-local → transfer → atomic `fs.rename`) — D5, TODO #17; local path unchanged. `engine._write_output_cog` and `api._merge_outputs` are **unchanged** callers that now get blob-dst for free |
| `model/bundle.py` | **none** — `fs.get`-to-scratch is in `infer_shard`, not the loader (D3) |
| `workflows/_snakefiles/create_inference/Snakefile` | D7 blob-safety (is_local guard + node-local sentinels), `cubes_per_task` grouping (D6/D7) |
| `workflows/runners.py::run_local_inference` | `+` forward `cubes_per_task` (D7); `+` duplicate-identity guard (D13) |
| `workflows/runners.py` | `+` `run_aml_inference`; reuse `_aml_submit_and_wait` / `shard_units` / preflight scaffold |
| `workflows/runners.py::run_aml_download` | D8: per-shard `catalog-<k>.parquet` + driver merge (TODO #51) |
| `workflows/infer_shard.py` | new, thin node entrypoint (D2) |
| `workflows/create_datacube.py::setup` | D13 dedupe on unit identity |
| `api.py` | `run_inference(runner="aml", runner_kwargs, storage)` (D14); date-boundary normalization for `download`+`run_inference` (D9) |
| `storage/*` (incl. `azure.py`) | **none** — D4′ is an env var; `transfer`/`get` already exist |
| AML Environment | a **second** inference Environment (D4) — additive to spec 36's |

---

## 5. Deliverables

| # | Deliverable |
|---|---|
| 1 | `workflows/infer_shard.py`: node entrypoint — `fs.get` shard CSV + bundle → local, call `run_local_inference`, write `_status/<k>.json` (D2/D9) |
| 2 | `workflows/runners.py::run_aml_inference`: stage bundle+roi, tile+setup (driver), shard cells, submit N jobs, wait, aggregate, raise (D1/D2/D11); reuse `_aml_submit_and_wait` |
| 3 | `raster/cog.py::to_cog`: remote-dst branch (convert-local → `storage.transfer` → atomic `fs.rename`) — fixes both per-cell `output.tif` and `merged.tif` on blob (D5, closes TODO #17) |
| 4 | `create_inference` Snakefile D7 fix + `infer_task` skip-if-final-exists (D6); `cubes_per_task` grouping with the cached bundle loader (D7, closes TODO #25 root cause) |
| 5 | `run_local_inference` forwards `cubes_per_task` (D7) + duplicate-identity guard (D13) |
| 6 | `create_datacube.setup` dedupe on unit identity (D13, TODO #53) |
| 7 | `api.run_inference(roi=…, runner="aml", runner_kwargs, storage)` end-to-end (D14) |
| 8 | Date-boundary normalization + fail-fast for `api.download`/`run_inference` (D9, TODO #52); the natural-datatype **sweep findings** list (D10) |
| 9 | `run_aml_download` per-shard `catalog-<k>.parquet` + driver merge (D8, TODO #51) |
| 10 | Preflight (D11) incl. `max_cells`; the one-node adapter-import smoke |
| 11 | The **inference Environment** build (D4) — a run-book step + a smoke job that imports the adapter on a node |
| 12 | Docs: `ROADMAP.md` (P4 → done), `AZURE_INFRA.md` (inference-on-AML, the inference Environment), `LIMITATIONS.md` (D12 crash-resume; `fs.get` bundle staging), `CHANGES.md`, `RECIPES.md`, `TODO.md` (#17/#25/#51/#52/#53 closed; #39/#47 cross-refs), the private-identifier sweep before any push |
| 13 | Run-book `38-inference-on-aml.md`: Phases 0–3 (§6), user-run |

---

## 6. Validation — phased (Claude never runs these; each is a run-book, user pastes back `_result.json`)

- **Phase 0 — the inference Environment + adapter-import smoke.** Build the inference Environment (D4);
  a one-node job `fs.get`s a staged bundle, `bundle.load`s it (resolves the adapter import in the real
  Environment), and runs a trivial predict. Proves D4 (deps + adapter present) and D3 (bundle staging +
  `fs.get`) **before** any cube is built — the check that pre-empts the node-side `ModuleNotFoundError`.
- **Phase 1 — one cell to blob.** A single-cell ROI (`s2grid=476da24`, verified 100% inside T33UWP),
  the Austria archive catalog, `runner="aml"`, `storage=abfss://…`. Proves the CLI wiring, the D5
  remote-dst COG (an `output.tif` **on blob** with correct nodata/CRS/transform), D6 (Snakefile blob
  safety + resume), and the end-to-end `run_aml_inference` for N=1. Compare the blob `output.tif` +
  STAC item against a **local** `run_inference(roi=…)` of the same cell — the seam-equivalence check
  spec 36 Phase 3b established for datacubes, now for inference outputs.
- **Phase 2 — resume + the #53 guard.** Re-run Phase 1 (D12): every cell skips via the `output.tif`
  blob-existence check (D6), `n_units` is stable (no `setup` duplication — D13), and a deliberately
  duplicated manifest is **refused** by the dispatch guard (D13).
- **Phase 3 — the real fan-out.** `AT_ROI` (or a chosen multi-cell ROI) → N shards across AML nodes →
  per-cell crop-class COGs + a STAC collection on blob. Records `wall_seconds` / `slowest_shard_seconds`
  / `driver_overhead_seconds` (the spec-36 Phase-3 gap, now fixed in the template) **plus
  `node_startup_seconds` and `image_build_seconds`** (the two estimates the future timed-demo report + docs
  refactor will want — TODO #55; `image_build_seconds` is captured at the Phase-0 Environment build, the
  rest at run), the exact-partition check, 0 failed, and **bundle-loads == n_nodes** (not n_cells — D7
  proven). This is the deliverable that demonstrates **Mode C end to end**, and its report is a direct
  input to TODO #55's "story since inception".

---

## 7. Tests (fast, synthetic, deterministic — no Azure, no network)

Reuse spec 36's injection pattern: `_FakeMLClient` + the `fake_aml_command` fixture; a fake bundle +
a trivial adapter for the engine/Snakefile paths.

1. `infer_shard` `fs.get`s the CSV + bundle and calls `run_local_inference` with the local paths +
   `cubes_per_task` (real inference mocked); writes a D9 `_status/*.json`.
2. `run_aml_inference` stages the bundle to `{root}/runs/{run_id}/_bundle`, tiles+`setup`s, `shard_units`
   the cells, submits **N** jobs each carrying `AZURE_CLIENT_ID` (D4′) and a command referencing the
   staged bundle URL; **no secret** anywhere (there is none). Non-vacuous across cell counts.
3. **Cell sharding is a partition** (reuse `shard_units` tests) — no cell lost/duplicated; `K>N` degrades
   to `N` non-empty shards.
4. `run_aml_inference` raises on a Failed job **and** on `_status/*.json` `status!="ok"` even if AML says
   Completed (D9).
5. `api.run_inference` accepts `runner="aml"` (threads `runner_kwargs`, `storage="azure"`) for ROI mode
   and rejects it for the pre-built-cubes path; rejects unknown runners.
6. **D5:** `raster.cog.to_cog` to a `memory://…/out.tif` writes a valid COG at the remote URL
   (convert-local → transfer → atomic `fs.rename`), and to a local path is byte-identical to today (no
   regression); `engine._write_output_cog` and `api._merge_outputs` (unchanged callers) both land a COG
   on a `memory://` dst through it.
7. **D6:** `infer_task.run_infer_task` returns early (no build, no infer) when `output.tif` exists and
   `overwrite=False`; the Snakefile keeps a blob `export_folderpath` intact (is_local guard) — a unit
   test on the abspath guard.
8. **D7:** with `cubes_per_task=K`, a K-cell group loads the bundle **once** (assert
   `engine._adapter_from_bundle_cached` called once, or `bundle.load` called once per group not per cell);
   `run_local_inference` forwards `cubes_per_task` (regression: a mutation dropping it fails this).
9. **D9:** `api.download`/`run_inference` coerce `startdate="2018-01-01"` and
   `startdate=pd.Timestamp("2018-01-01")` to the **same** forwarded `Timestamp`; an invalid
   `startdate="2018-13-01"` raises a **preflight** error (fail-fast), not a downstream one. A mutation
   forwarding the raw string fails the equivalence assertion.
10. **D8:** two MPC shards writing `catalog-0.parquet`/`catalog-1.parquet` + a driver merge yields a
    catalog with **both** tiles' rows (the lost-update cannot occur — distinct files); a single-writer
    upsert-by-id is preserved. Non-vacuous: a mutation reverting to a shared `--catalog` reintroduces the
    shared write (assert per-shard files are distinct).
11. **D13:** `setup` called twice with the same shapes yields **one** row per unit (dedupe on identity),
    order preserved; `run_aml_inference`/`run_local_inference` **raise** on an `input.csv` with duplicate
    unit identities. Non-vacuous: a mutation removing the dedupe fails the row-count assertion.
12. **Non-vacuousness** (project standard) across the above, called out per test.

**No test may require Azure** (spec 36 §7) — `azure-ai-ml`, `adlfs`, the adapter's deps stay runtime-only;
`memory://` stands in for blob.

---

## 8. Open questions (resolve during implementation; do not block sign-off)

1. **`cubes_per_task` default on a node.** Whole-shard (one bundle load per node, D7) vs a smaller group
   (cap peak memory for a heavy model that also wants `cores>1`). Lean: whole-shard for the RF demo;
   expose the knob, tune at Phase 3.
2. **`bundle.load` streaming vs `fs.get`** (D3). `fs.get`-to-scratch is the adapter-agnostic minimum;
   teaching every adapter's `.load()` to read via `fsd.storage` is the "one shared reader" generalisation
   (cf. TODO #47). Defer; keep `fs.get`.
3. **The inference Environment's cadence** (D4). One Environment per adapter version vs a base +
   a thin per-model layer. Ops detail; the run-book builds one for the demo.
4. **Infer-only (pre-built cubes) fan-out on AML** (spec 22). A `run_aml_infer_only` that skips the build
   — trivial given this dispatcher, but out of the demo's ROI path. Spec it if a caller needs it.
5. **`n_shards` / oversubscription.** `max_instances` default (D1); whether fatter/fewer shards help is a
   Phase-3 measurement (spec 36 saw 1.62× straggler spread → self-balancing), not a design guess.

---

## 9. Best-practice alignment / sources

Per `CLAUDE.md`'s standing practice: what each source actually contributed. Searched (standing
spec-cross-validation permission): pystac-client date-vs-datetime `datetime=` expansion; Azure ML custom
pip-package / private-wheel Environments.

- **[pystac-client — `ItemSearch` / issue #644 "search result depends on datetime format"](https://github.com/stac-utils/pystac-client/issues/644)**
  and **[the `item_search` API docs](https://pystac-client.readthedocs.io/en/stable/api.html)** — the
  load-bearing fact behind **D9**: a **date-only string** `2017-06-10` is expanded to
  `2017-06-10T00:00:00Z/2017-06-10T23:59:59Z` (the *whole day*), while a `datetime.datetime` /
  RFC-3339 timestamp is treated as an **instant** and not expanded. Issue #644 is this exact
  divergence ("search result depends on datetime format"). This is precisely why passing a bare string
  vs a `Timestamp` yields a one-day-different window, and why normalizing to `Timestamp` at the boundary
  (D9) removes the type- and runner-dependence. Corroborates the local evidence already in PROGRESS (the
  spec-37 "3432 vs 3456" investigation: bare strings → 3456, `pd.Timestamp` → 3432, one 2019-01-01
  acquisition of difference).
- **[Use private Python packages — Azure Machine Learning (v1)](https://learn.microsoft.com/en-us/azure/machine-learning/how-to-use-private-python-packages?view=azureml-api-1)**
  — consulted for **D4**; contributed the **negative** finding that its mechanism
  (`Environment.add_private_pip_wheel` + `CondaDependencies.add_pip_package`) is the **v1** SDK, which
  fsd does **not** use. It confirms AML *supports* a custom package in an Environment (the design is
  sound) but is **not** the API to reach for — the v2 path is the Docker build context spec 36/37
  already established, so D4 extends that Dockerfile rather than introducing v1 plumbing.
- **[fsspec `AbstractFileSystem.get` / `get_file`](https://filesystem-spec.readthedocs.io/en/latest/api.html)**
  — basis for the **D3 correction**: `get`/`get_file` fetch a **single** file; recursive fetch of a
  directory tree needs `get(..., recursive=True)`. `fsd.storage.get` wraps `get_file` (single-file), so
  the bundle fetch is manifest-driven (option a) or needs a recursive-`get` addition (option b) — not a
  single existing call.
- **Internal precedent (why this spec is mostly reuse):** **spec 21** built the local per-cell
  build+infer unit-of-work + `run_local_inference` (the code P4 dispatches unchanged); **spec 36** built
  and **proved on the cluster** the dispatch machinery reused here (`run_aml`, `shard_units`,
  `_aml_submit_and_wait`, `_import_aml_command`, the Docker-build-context Environment, the D4′
  `AZURE_CLIENT_ID` identity, the **D7 atomic-publish + node-local-sentinel** pattern D6 mirrors, and the
  1.62× straggler-spread measurement behind **D1**); **spec 34**'s `_push_scratch_to_remote` is the
  stage-local→push pattern **D5** follows for the inference COG; **spec 37** is the sibling dispatcher
  whose input-staging-to-blob, per-shard `_status/<k>.json`, and preflight shape P4 mirrors, and whose
  Phase-3 run is the concrete evidence behind **D8** (TODO #51). TODO **#17/#25/#51/#52/#53** are the
  registered defects D5/D7/D8/D9/D13 close.
