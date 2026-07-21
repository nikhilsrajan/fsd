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
| **There is no Azure Batch runner.** Snakemake-on-this-laptop is the only runner; the runner seam exists but nothing dispatches through it. | **this is the P2/P4 gate** — the whole scale-out story | TODO #41; `ROADMAP.md` P2 |
| **The local Snakemake runner's `start.txt`/`done.txt` sentinels are not blob-safe** — a remote `export_folderpath` raises rather than silently corrupting. | running the local runner with artifacts on blob | TODO #41 |
| **Inference/serving output writes are local-only** (`storage_allowed=False` for `run_inference`/`deploy`). | inference outputs need to land on blob | TODO #39 |
| **ROI geometry inputs are read locally**, bypassing `fsd.storage`. | a Batch node with no `shapefiles/` checkout | TODO #40 |

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
| **Inference reloads the model per grid cell.** | per-cell inference time is dominated by load | TODO #25 |
| **One worked example: single-band classification (EuroCrops RF).** No regression / multi-band-output example. | first regression or multi-output model | TODO #18 |

## Data on disk (not code — state)

| Limitation | Trigger to fix | Detail |
|---|---|---|
| **The Austria `demo_e2e` archive is radiometrically un-harmonized** — every granule is baseline N0500 but the CDSE rows hardcode `boa_add_offset=0`, so cubes built from it are ~1000 DN high. Fine for infra/seam tests; **not for science.** | any science claim off that archive | `CLAUDE.md`; TODO #30/#10 history |
| **The four catalogs written before spec 35 carry no declaration stamp and now raise at build time** (`demo_e2e`, `mpc_baseline`, the `rise` blob catalog, old per-cell slices). | next build against any of them — re-stamp is one command | spec 35 §6; `RECIPES.md` |
| **The `rise` blob COGs carry the pre-fix (wrong) GDAL offset tag** — a titiler `unscale=true` render of them would be all black. | before ever serving those blob COGs | TODO #44 |
