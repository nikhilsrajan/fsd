# LIMITATIONS — what fsd cannot do today

**The one-page honest answer to "can fsd do X?"** — written for a *user* of the system
(and for anyone sizing a demo), not for an implementer.

**This is an index, not a register.** One line per limitation, no detail. The detail
already lives elsewhere and must not be copied here:

- `TODO.md` — the deferred *work item* (why it's parked, what the fix looks like)
- `DROPPED.md` — capabilities from the legacy repos deliberately not carried over
- `BUGS.md` — defects that need a human to evaluate
- `specs/` — the signed-off design that drew the boundary in the first place

**Maintenance rule (keep it stupid simple):** a limitation is worth a row here only if a
user could *hit* it. Add the row when you find it; delete the row when it's fixed. If a
row grows past two lines, it belongs in `TODO.md` and this row should just point there.
**We plug a limitation when we actually hit it**, not in advance (YAGNI) — the "Trigger"
column is what "hitting it" means for each row.

---

## Data sources

| Limitation | Trigger to fix | Detail |
|---|---|---|
| **Sentinel-2 L2A only.** No S1, L1C, CHIRPS, ERA5, or any non-optical source. | the first real non-S2 use case | TODO #11; `DROPPED.md` (L1C) |
| **Two providers: CDSE + MPC.** Both S2 L2A, so no cross-source catalog has ever been built. | a third provider, or a genuinely different collection | TODO #11 |
| **MPC returns multiple processings of the same acquisition and fsd does not de-duplicate them.** | an MPC-sourced cube looks double-counted | TODO #34 |
| **CDSE discovery has no retry** — one transient API blip kills a run before any download. | a long/unattended run (i.e. Batch) | TODO #43 |
| **Downloads are whole-MGRS-tile.** No windowed/partial read of a granule. | download cost dominates a small-ROI job | TODO #36 |

## Datacube

| Limitation | Trigger to fix | Detail |
|---|---|---|
| **Output resolution is the reference band's** (10 m for S2) — not configurable. | a model wants 20 m/60 m native, or a non-10 m source | TODO #1 |
| **`mosaic_method="median"` is the only one implemented.** A declared-but-unimplemented value raises. | a source/model needs mean, max-NDVI, best-pixel… | spec 34 §2a |
| **`mask_type="categorical_classes"` is the only one implemented.** No bitmask (Landsat/HLS QA) or threshold (cloud-probability) masking. | first Landsat/HLS/probability-mask source | spec 34 `[G3]` |
| **`native_grid=True` raises `NotImplementedError`** — there is no non-tiled (global-grid) build path. | first ERA5/CHIRPS-style source | spec 34 `[G2]` |
| **Multi-CRS ROIs collapse to the single max-mean-area UTM zone** before merging; contributions from the other zone are dropped. | an ROI genuinely straddling a UTM boundary with data on both sides | TODO #5 |
| **The artifact is `datacube.npy` + `metadata.pickle.npy`**, not xarray/zarr — no lazy/chunked access, no partial read. | cubes stop fitting in memory | TODO #13 |

## Scale / cloud

| Limitation | Trigger to fix | Detail |
|---|---|---|
| **The AML runner (`runner="aml"`) is implemented but not yet validated on the real cluster.** `workflows.runners.run_aml` shards `input.csv`, submits one command job per shard, waits, and raises on failure; all 12 unit tests (spec 36 §7) are mocked at the AML-client boundary. `runbooks/36-aml-runner.md` Phases 1–3 (one shard, resume, real fan-out) are written but not yet run. | someone runs Phases 1–3 and reports back | TODO #41 (closed as implemented); spec 36; `ROADMAP.md` P2 |
| **There will be no Azure *Batch* runner.** The project's Batch account has a 6 vCPU quota against a 64-core pool VM, so it cannot allocate a node; dropped rather than quota-requested. | someone needs Batch specifically (or a generic task-queue backend: AWS Batch, k8s) | `AZURE_INFRA.md` §3.1 |
| **Inference-on-blob (`run_inference(roi=…, runner="aml")`) is FULLY VALIDATED on the real cluster (2026-07-28) — Phases 0-3 all GREEN.** Phase 0 (env + adapter smoke, D3/D4), Phase 1 (single-MGRS-tile ROI → 9 cells → 9 COGs + STAC; found + fixed the grids.geojson GDAL-on-blob bug, `9422a1a`), Phase 2 (D6/D7 resume + D13 guard), and **Phase 3 (`AT_ROI` → 300 cells, 16 shards, 300 COGs + STAC, `n_failed == 0`, `bundle_loads == 16`, wall 2066.9 s)** and **Phase 4 (strict single-CRS `merge` -> one 14.1 MB `merged.tif` on blob, wall 1082.1 s)**. Phase 3's two earlier failures were a *label set* passed as `roi=` (spec 21 D-GRID-1), not an infrastructure limit. **Known cost shape: 52.5 % of wall was driver overhead, undecomposed** (TODO #59). `deploy` and the pre-built-cubes `run_inference` path stay local-only (unchanged, D14 scope). | the overhead share matters, or a non-demo-scale ROI | spec 38; spec 21 D-GRID-1; TODO #59 |
| **P4's crash-resume is per-cell, not per-shard-atomic**: a shard that crashes mid-cell loses only that cell's un-pushed scratch (each cell publishes atomically via D5's `to_cog` remote branch); a re-dispatch skips every cell whose `output.tif` already exists on blob (D6) and rebuilds only the unfinished tail. Same honest limitation shape as spec 37 D8's download resume, cheaper here (a crashed shard re-runs only its cells, not the whole download). | a crash-resume actually happens on the cluster | spec 38 D6/D12 |
| **The inference AML Environment is a *second*, model-specific image** (D4) — `fsd[azure,mpc]` + the adapter's installable package + its runtime deps, built by an operator run-book step (not automated). Swapping the model means building a new Environment; P6 `deploy()` is where this later gets automated (bundle registration + Environment build fused into one call), not P4. | a second/updated model needs to run at scale | spec 38 D4; ADR `docs/adr/0002-bundle-and-inference-image-decoupled.md`; `ROADMAP.md` P6 |
| **The AML *download* dispatcher (`api.download(runner="aml")`) is implemented but not yet validated on the real cluster**, and a job that crashes mid-run loses its un-pushed scratch — a fresh-node resume re-downloads the unpushed remainder (it can't see COGs already on blob, since spec 34's push is whole-run). Cheap for MPC (only the crashed shard's slice re-runs); costs re-downloaded bytes for CDSE. | someone runs `runbooks/37-download-on-aml.md` Phases 0–3; or a crash-resume actually happens | spec 37 D8; TODO (open, composes with #31) |
| **CDSE creds delivered via blob JSON (`--creds-url`) sit as plaintext at rest on blob**, unlike the Key Vault path — used only because the operator has no KV *write* role on the demo timeline (`ForbiddenByRbac`). Mitigated by writing to a `_secrets/` prefix and scoping the file to **one run** — `runbooks/37-download-on-aml.md`'s `blob_creds()` context manager pushes it immediately before the run and deletes it in a `finally` immediately after, so it goes away on the failure path too. Switch back to Key Vault once a write role lands; **rotate the CDSE keys** if a run was long or the prefix is broadly readable. | a KV write role becomes available, or the blob creds file outlives a single run | spec 37 D5 REVISED |
| **`flatten_training_data`'s `runner="aml"` flatten reduce (`runners.run_aml_flatten`, spec 39 D3) is VALIDATED on the real cluster** (runbook 39 **Phase 1 GREEN, 2026-07-27**: 900 blob cubes → one single-node reduce → 172,781-pixel `(pixels,8,3)` array landed locally in **405.7 s**, labels/coords/ids all consistent, one AML job not a fan-out). **`create_training_data(download=True, runner="aml")` end-to-end (Phase 2) is still unrun.** Unit tests are mocked at the AML-client boundary. | someone runs Phase 2 and reports back | spec 39 |
| **The single-node flatten reduce has a memory ceiling** — `np.concatenate` allocates one new contiguous array and copies every input, so peak memory ≈ 2x the flattened total (all per-cube arrays + the result). **MEASURED (runbook 39 Phase 1, 2026-07-27): 900 `AT_2018_TRAIN` cubes → `data.npy` = 8.29 MB (172,781×8×3 uint16), so peak ≈ ~16 MB** — an order of magnitude below the spec's "tens-to-low-hundreds of MB" estimate, trivially within one node's RAM. Untested at 10⁴–10⁵ cells, where a streaming/partial-reduce would be needed. | someone flattens 10⁴+ cells in one call | spec 39 D3 §9; TODO #56 |
| **There is NO write-retry in the storage seam** — a failed blob write raises on the first attempt. A `_write_with_retry` was added 2026-07-28 for a misdiagnosed "transient adlfs race" and **reverted the same day**: the real failure was duplicate work-unit ids making threads write one blob (spec 21 D-GRID-1), which retrying cannot fix — every writer just retried into every other writer — and the resulting error storm actively **buried** the real cause under minutes of log noise, turning a fast legible failure into a crawl that read as an infinite loop. **No transient adlfs race has ever been demonstrated here:** runbook 36 wrote 900 *distinct* blobs at the same 16-way concurrency, same VPN, same account, in 71 s with zero errors. If one is ever observed (distinct paths, monotonic attempt numbers), retry only on the Azure **storage error codes**, never on adlfs's catch-all `"Failed to upload block"` prefix — that comes from an `except Exception` in `adlfs/spec.py::_async_upload_chunk`, so permanent auth/RBAC failures wear it too. `fs.write_bytes`/`write_text` survive the revert as plain seam helpers. | a genuine transient write error is observed on DISTINCT blobs | TODO #57 (reverted) / #58 |
| **`run_inference(roi=…)` tiles the ROI's CONVEX HULL into grid cells**, so a sparse ROI still yields a contiguous, partly-empty cell set — a region-wide crop-map fan-out, not one-cell-per-feature. Not a bug (it's how you get a contiguous map), but a cost surprise: each cell is a **full ~49 km² datacube** at `grid_size_km=5`. **`AT_ROI.geojson` → 300 cells** (measured 2026-07-28; **299 as of spec 46 D4, 2026-08-19** — one cell was fully covered by another and is now dropped). For fewer cells: a smaller/compacter ROI, a larger `grid_size_km`, or `inference_datacubes=` mode over pre-built cubes. **⚠️ `roi=` takes a REGION, not a label set** — passing `AT_2018_TRAIN.geojson` (900 field polygons) there is what produced the bogus "1167 cells" figure in earlier docs; see the row below. | a roi-mode run costs more than expected | spec 21 D-GRID-1; PROGRESS 2026-07-28; spec 46 |
| **✅ FIXED (spec 21 D-GRID-1) — `roi_to_s2_grids` repeated cell ids for a multi-polygon ROI.** The clip used `gpd.overlay(grids, roi_gdf, how="intersection")`, which emits one row per *(cell × roi-polygon)* pair — so a 900-field ROI gave **1167 rows for 172 distinct cells** (one repeated 43×), each row a ~0.016 km² fragment of a 49.6 km² cell, with the ROI's attributes dropped so fragments had no identity. `id` is the work-unit key (`export_folderpath` derives from it), so N rows/id = N tasks writing the SAME folder concurrently → guaranteed `InvalidBlockList` on blob, last-writer-wins geometry locally. Now clipped to the ROI's **union** (one row per cell, ids asserted unique) + `setup()` refuses duplicate ids for any caller. **A single-polygon ROI's cell COUNT changed under a separate fix, spec 46 D4** — Phase 1's single-MGRS-tile ROI polyfills its 8 neighbours too, all 8 fully covered by the central cell once clipped, so what was 9 cells is now correctly deduplicated to **1**; the id-uniqueness fix recorded here is otherwise unaffected. | — | spec 21 D-GRID-1; found by runbook 38 Phase 3, 2026-07-28 |

## Serving / outputs

| Limitation | Trigger to fix | Detail |
|---|---|---|
| **fsd serves nothing.** It emits COGs + STAC; a stock pgSTAC + titiler-pgstac is what turns those into XYZ tiles, and it is not stood up. | someone needs to *look* at an output on a map | TODO #26; `ROADMAP.md` P5 |
| **No render config on outputs** — nothing tells a viewer how to colour a class raster. | first output shown to a non-author | TODO #28 |
| **The STAC Collection's `classification:classes` lists only the *masked* SCL values, with placeholder names.** Misleading to an external STAC consumer; fsd itself is unaffected. | an external tool actually reads our STAC | TODO #45 |

## Models

| Limitation | Trigger to fix | Detail |
|---|---|---|
| **A model adapter is hand-written Python.** No config-only path. | a non-programmer needs to plug a model in | TODO #19 |
| **✅ Root cause closed (spec 38 D7)**: the bundle now loads once per core per node (default, `cubes_per_task` groups cells) or once per node (`cores=1` heavy-model opt-out), not once per cell. The fine-grained per-phase timing breakdown (load/build/predict/save) TODO #25 also asked for is still open. | per-cell inference time is dominated by load | TODO #25 |
| **One worked example: single-band classification (EuroCrops RF).** No regression / multi-band-output example. | first regression or multi-output model | TODO #18 |

## Data on disk (not code — state)

| Limitation | Trigger to fix | Detail |
|---|---|---|
| **The Austria `demo_e2e` archive is radiometrically un-harmonized** — every granule is baseline N0500 but the CDSE rows hardcode `boa_add_offset=0`, so cubes built from it are ~1000 DN high. Fine for infra/seam tests; **not for science.** | any science claim off that archive | `CLAUDE.md`; TODO #30/#10 history |
| **The four catalogs written before spec 35 carry no declaration stamp and now raise at build time** (`demo_e2e`, `mpc_baseline`, the `rise` blob catalog, old per-cell slices). | next build against any of them — re-stamp is one command | spec 35 §6; `RECIPES.md` |
| **The `rise` blob COGs carry the pre-fix (wrong) GDAL offset tag** — a titiler `unscale=true` render of them would be all black. | before ever serving those blob COGs | TODO #44 |
