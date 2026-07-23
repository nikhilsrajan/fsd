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
| **Inference-on-blob (`run_inference(roi=…, runner="aml")`) is implemented but not yet validated on the real cluster** (spec 38 P4, `runners.run_aml_inference`); all 31 unit tests are mocked at the AML-client boundary. Run-book `runbooks/38-inference-on-aml.md` Phases 0-3 are written but not yet run. `deploy` and the pre-built-cubes `run_inference` path stay local-only (unchanged, D14 scope). | someone runs Phases 0-3 and reports back | spec 38; TODO #17 (closed as implemented) |
| **P4's crash-resume is per-cell, not per-shard-atomic**: a shard that crashes mid-cell loses only that cell's un-pushed scratch (each cell publishes atomically via D5's `to_cog` remote branch); a re-dispatch skips every cell whose `output.tif` already exists on blob (D6) and rebuilds only the unfinished tail. Same honest limitation shape as spec 37 D8's download resume, cheaper here (a crashed shard re-runs only its cells, not the whole download). | a crash-resume actually happens on the cluster | spec 38 D6/D12 |
| **The inference AML Environment is a *second*, model-specific image** (D4) — `fsd[azure,mpc]` + the adapter's installable package + its runtime deps, built by an operator run-book step (not automated). Swapping the model means building a new Environment; P6 `deploy()` is where this later gets automated (bundle registration + Environment build fused into one call), not P4. | a second/updated model needs to run at scale | spec 38 D4; ADR `docs/adr/0002-bundle-and-inference-image-decoupled.md`; `ROADMAP.md` P6 |
| **The AML *download* dispatcher (`api.download(runner="aml")`) is implemented but not yet validated on the real cluster**, and a job that crashes mid-run loses its un-pushed scratch — a fresh-node resume re-downloads the unpushed remainder (it can't see COGs already on blob, since spec 34's push is whole-run). Cheap for MPC (only the crashed shard's slice re-runs); costs re-downloaded bytes for CDSE. | someone runs `runbooks/37-download-on-aml.md` Phases 0–3; or a crash-resume actually happens | spec 37 D8; TODO (open, composes with #31) |
| **CDSE creds delivered via blob JSON (`--creds-url`) sit as plaintext at rest on blob**, unlike the Key Vault path — used only because the operator has no KV *write* role on the demo timeline (`ForbiddenByRbac`). Mitigated by writing to a `_secrets/` prefix and scoping the file to **one run** — `runbooks/37-download-on-aml.md`'s `blob_creds()` context manager pushes it immediately before the run and deletes it in a `finally` immediately after, so it goes away on the failure path too. Switch back to Key Vault once a write role lands; **rotate the CDSE keys** if a run was long or the prefix is broadly readable. | a KV write role becomes available, or the blob creds file outlives a single run | spec 37 D5 REVISED |

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
