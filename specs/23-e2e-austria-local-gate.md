# Spec 23 — e2e Austria: the local-completeness gate + team report

**Status:** SIGNED OFF + IMPLEMENTED (code + tests + doc; Results in the doc fill from a real run)
**Phase:** P0.9 — the *last* local test before P1 (Azure storage seam).
**Supersedes in part:** spec 19 (`e2e_ethiopia`, now renamed `e2e_austria`). Keeps its shape;
adds a real CDSE **download** at the front, folds the two inference steps into one **ROI-mode
`run_inference`**, and instruments **download-vs-COG timing** + a **bandwidth baseline**.

---

## 1. Real goal (what this is actually for)

Two deliverables, one run:

1. **A confidence gate.** Prove the *entire* local pipeline works on **fresh, real, downloaded**
   data — `download → jp2→COG → datacube → flatten → train → bundle → ROI build+infer → COG +
   STAC + merged map` — end to end, one command. Until now the demo started from pre-downloaded
   `satellite_benchmark/` (deleted); download was never in an e2e. This closes that gap so we
   enter P1 *knowing* local is complete, not assuming it.
2. **The team's go-to local-run doc** (`demos/E2E_AUSTRIA.md`): how to set fsd up locally
   (venv, extras, CDSE creds), what each stage does (incl. a **detailed model-bundling guide** —
   the two developer-owned endpoints), and a **timings report** filled from the real run so the
   numbers are trustworthy — which requires (a) separating CDSE-transfer cost from local
   COG-conversion cost, and (b) a bandwidth baseline so a slow link is not mistaken for slow CDSE.
   **A VPN is NOT an fsd requirement** — it only happens to be on the author's machine, and is
   relevant *only* as a caveat when reading these particular timings (§8 of the doc), never a setup
   step the team must reproduce.

**The script is a reusable template**, not an Austria-only demo: the team changes the **ROI file**,
the **training file**, and its **id/label columns** (CLI args) and gets their own result — and it
**must run seamlessly for a cross-UTM-zone ROI** (e.g. France, Russia), not just Austria's
single-zone happy case. See D7.

Non-goal: model quality. Austrian labels, real Austrian pixels now (an improvement over Ethiopian
translation), but this validates *plumbing + timings*, not accuracy.

---

## 2. Locked decisions (verified with the user)

| # | Decision | Choice |
|---|----------|--------|
| **D1** | Separate download-bytes time from jp2→COG time (they interleave per-file in threads) | **Instrument in-thread**: `_transfer_and_convert` records per-file `transfer_s` / `convert_s` / `bytes`; aggregate into `DownloadResult`. Keeps the real COG-on-arrival path. |
| **D2** | Factor out the user's VPN/background bandwidth | **Probe + effective throughput**: single-threaded one-file probe (achievable MB/s now) vs aggregate effective MB/s (bytes/elapsed). Probe≈aggregate → CDSE-bound; probe≫aggregate → local contention. No new deps, no web. |
| **D3** | Scope of this download | **One season, cloud-filtered**: `2018-04-01..2018-09-30`, `max_cloudcover=70`, `mosaic_days=20`, via `download_resume` (CDSE-flaky-safe). ~30–80 granules, ~1–4 GB. |
| **D4** | Where download lives | **Integrated, idempotent step** inside `e2e_austria.py` (skips files on disk). One command runs the gate; re-runs are cheap. Doc states the creds prerequisite. Mirrors the P4 "download once → compute reads from storage" split. |

### Secondary decisions — **confirm at sign-off** (defaults chosen; say if any is wrong)

- **D5 — CDSE credentials.** Script loads `CdseCredentials.from_json(path)`. Path from
  `--creds` (default `$CDSE_CREDENTIALS_JSON`, else `<workspace-root>/cdse_credentials.json`).
  **Confirm the path to your creds file** (S3 keys required; `require_s3()` enforced). The doc
  lists this as prerequisite #1.
- **D6 — Guardrails + template constants.** `max_tiles=200` (refuses a runaway query),
  `max_cloudcover=70`, `bands=["B04","B08","B8A","SCL"]` (unchanged; adapter needs B04/B08, SCL
  masks, B8A dropped). The "swap these" inputs are **named module constants** at the top of the
  script — `ROI_FP`, `TRAIN_FP`, `ID_COL="fid"`, `LABEL_COL="crop"` — each overridable by the
  matching CLI flag. One obvious config block is what a teammate edits.
- **D13 — Download stays an explicit phase; compute verbs never auto-fetch (confirming, not
  changing).** `create_training_data` / `run_inference` read imagery from `catalog_filepath`; they
  do **not** call CDSE (quota + the Batch "download once → compute reads from storage" model — see
  §6). *Improvement — the `plan_download` guardrail:* when preflight finds imagery missing, emit an
  **actionable download plan** (not just an error). `plan_download(roi, start, end, bands, *,
  catalog_filepath=None, cost_model=None)` queries CDSE STAC (cheap, no bytes), diffs
  **needed-vs-present** tiles against the local catalog, and returns/writes a JSON manifest +
  prints a copy-pasteable `fsd.download(...)` command with `max_tiles` set to exactly the missing
  count and (if a `cost_model` is available) the **GB + ETA** (reuses the §7 estimator — shared
  count/diff helper). The compute-verb preflight raises `PreflightError` carrying this message.
  Never auto-fetches; any download-if-missing convenience stays opt-in + local-only (and see D14
  for why "seamless" is a *source-capability* question, not a quota one).
- **D14 — Forward note (NOT built here): quota-free sources (MPC) → seamless via the seam, not
  auto-download.** See §6 "Future". Recorded now so spec 23's guardrail is designed to compose with
  it; implementation is a later spec.
- **D7 — Merge mode = `"reproject"` (the general, cross-zone-safe default). NO zone assertion.**
  *(Corrected — the earlier "strict `True` + assert zone 33" was wrong: it would refuse a legitimate
  cross-UTM-zone ROI and break the reusable-template goal.)* The architecture is already what we
  want: each **grid cell** builds its datacube in **its own max-area-contribution CRS** (the
  single-CRS-merge principle, per cell), and the per-cell COGs stay **authoritative in their native
  zone**. A single combined image is produced by **reprojecting every cell output to one CRS, then
  merging** (nearest-neighbour — categorical-safe). This is `merge="reproject"`, which the shareable
  script uses **unconditionally**:
  - **Single-zone ROI (Austria):** target CRS == every cell's CRS → **no resampling occurs → the
    merge is lossless.** (So "reproject" is not "always lossy"; it's lossy *only* for cells that
    actually change zone.)
  - **Cross-zone ROI (France/Russia):** minority-zone cells are reprojected to the target; the
    mosaic spans zones seamlessly. **This is the case the template must support** and the reason we
    do not assert a single zone.
  - **Two enhancements to the current `"reproject"`** (which today picks the target by *cell count*
    and offers no override): pick the target CRS by **max total area** across cells (correct for
    clipped ROI-edge cells), and accept an optional **user-provided target CRS** (`merge_crs=`).
  - Austria's data is single-zone, so this *gate run* won't exercise a real reprojection; the
    cross-zone path is covered by an **offline unit test** (two tiny COGs in different EPSGs →
    area-dominant target + `merge_crs` override). Ethiopia/spec 21 previously exercised it on real
    multi-zone data.
- **D8 — smoke levels.** `--fast`: narrow to `2018-04-01..2018-06-01`, sample 3 fields/class, shrink
  the *inference* ROI to a small central slice (still downloads the full ROI). `--tiny-download`
  (added): ALSO clip the *download* ROI to that slice (few granules) and train only on the fields
  inside it — the fastest true end-to-end. No flag = full season over the whole ROI.
- **D9 — Doc location `demos/E2E_AUSTRIA.md`** (lives next to the script it documents).
- **D10 — Timing instrumentation is a core change** to `DownloadResult` + `_transfer_and_convert`
  (`fsd.sources.cdse`), logged in CHANGES.md; the probe + MB/s math live in the demo.
- **D11 — Per-band byte accounting.** `DownloadResult.bytes_by_band: dict[str,int]` (+ implied
  file counts) so a mean file-size per band is known — the unit needed to extrapolate to a
  *different band set*. (Bucketing by band = by native resolution: B04/B08@10m ≈ 4× B8A/SCL@20m.)
- **D12 — A no-download ETA estimator** (§7). The counts that drive runtime (granules, grid cells,
  T) are all cheaply/exactly queryable *without* downloading; this run calibrates the per-unit
  costs. `estimate_run(roi, start, end, bands, …)` multiplies the two together → ETA + bytes for
  *any* region/window/bands (e.g. full France). This is the answer to the recurring "how long
  would X take?" without paying to find out.

---

## 3. The flow (compartmentalised steps, each with a verification check)

`demos/e2e_austria.py`. Every step prints a `✓`/`✗` check; a failed check aborts with a clear
message (this is a gate, not a best-effort demo).

**Step 0 — Preflight / setup.**
Load creds (`from_json`, `require_s3()`); assert ROI + FIELDS exist; print mode/window/T/cores.
✓ check: creds complete, both geojsons readable, `.venv-modeldeploy` interpreter (has `[grid]` +
`[model-example]`).

**Step 1 — ROI → S2 grid cells** (`fsd.grid.roi_to_s2_grids`, for the plot + count).
✓ check: N cells ≥ 1; **report the CRS/zone distribution** across cells (no assertion — a
cross-zone ROI is valid, D7; Austria happens to be all zone 33); PNG saved for QGIS.

**Step 2 — Download (integrated, idempotent, resumable) + timing.**
- 2a **baseline probe**: fetch ONE representative band file single-threaded, `MB/s = bytes/s`.
  (It lands at its real dst, so it's not wasted — step 2b skips it.)
- 2b `sources.cdse.download_resume(... cog=True, progress=True)` → `catalog.parquet`, with
  per-file `transfer_s`/`convert_s`/`bytes` accumulated (D1).
✓ check: catalog has ≥1 tile; every listed file exists on disk & non-empty; report prints
**transfer_s vs convert_s** (summed across threads), **wall_s**, **bytes**, **effective MB/s**
(bytes/wall), **probe MB/s**, and the probe-vs-effective verdict (D2).

**Step 3 — Training data** (`fsd.create_training_data`, `adapter=DemoRF`, `id_col="fid"`,
`label_col="crop"`, `cores=CORES`) → `features.npy` (build datacubes over the 900 fields, then
flatten; user never types "flatten").
✓ check: `features` shape `(n, T, n_feature_bands)` with **T == compute_n_timestamps(window)**;
9 classes present.

**Step 4 — Train RF + save bundle.** sklearn RF (fsd does not train); `bundle.save(adapter,
{"model": rf.joblib}, .../bundle)`.
✓ check: `bundle.read_spec` returns `adapter="adapters:DemoRF"`, `n_timestamps == T`,
`required_bands == ["B04","B08"]` — the **model-free** manifest the team ships.

**Step 5 — ROI inference (build + infer + save, one runner pass).**
`fsd.run_inference(model=bundle_dir, roi=ROI, catalog_filepath=catalog, startdate/enddate/
mosaic_days/bands, merge="reproject", cores=INFER_CORES, cubes_per_task=…, overwrite=False,
progress=True)`. This **replaces old steps 4+5**: fsd tiles ROI→cells, then per cell **builds the
datacube (in the cell's own dominant CRS) and runs the model** as one Snakemake task (spec 21),
reading imagery from the catalog (never CDSE); the merged image reprojects all cells to one CRS
(cross-zone-safe, D7).
✓ check: `len(output_filepaths) == N cells`; each COG opens with a valid CRS, `nodata==255`; STAC
round-trips with one item/output; `merged.tif` exists in a single CRS (for Austria, the cells'
common zone → lossless); **a second call reports "Nothing to be done" with unchanged mtimes**
(spec-22 idempotency, on real data).

**Step 6 — Plots.** Per-class median NDVI timeseries + categorical crop-class map (QGIS + PNG).

**Step 7 — Report.** Print the per-step timing table; write `timings.json`; the numbers flow into
`demos/E2E_AUSTRIA.md` §Results.

`CORES` (train-data build) and `INFER_CORES` (inference build+infer) stay the two independent
knobs added last change — the OOM fix.

---

## 4. Code changes

1. **`fsd.sources.cdse` (core, D1/D10).**
   - `_transfer_and_convert(...)` → returns `(transfer_s, convert_s, bytes)` (time the
     `fs.transfer` and the `to_cog` separately; `bytes = fs.size(dst)`).
   - `_download_one(...)` returns those metrics alongside `(ok, reason)`.
   - `download(...)` accumulates them; `DownloadResult` gains
     `bytes_downloaded: int`, `transfer_seconds: float`, `convert_seconds: float`
     (all default 0.0 → back-compatible). `download_resume` sums across passes.
   - New `probe_throughput(roi, startdate, enddate, bands, creds) -> (mb_per_s, bytes, seconds)`:
     single-threaded fetch of the first matched item's first band to a temp path, timed. Kept in
     `cdse` (CDSE-specific, reusable on Batch later); demo calls it.
2. **`fsd.api.run_inference` / `_merge_outputs`** (core, D7): the `"reproject"` path (a) selects the
   target CRS by **max total cell area** (fall back to cell count if area is unavailable) instead of
   most-cells, and (b) accepts an optional **`merge_crs=<EPSG>`** to force the target CRS; update the
   docstring so `"reproject"` is described as "lossless where a cell already matches the target;
   reprojected (nearest) only for cells changing zone."
   - **(D13) `plan_download` guardrail** used by the `create_training_data` / `run_inference`
     preflight: on missing imagery, build the needed-vs-present tile diff (shared count/diff helper
     with §7's estimator), write `_download_plan.json` + print the exact `fsd.download(...)` command
     (`max_tiles`=missing count) with GB+ETA when a cost model is known; raise `PreflightError`
     carrying it. Pure/queryable (no bytes); no auto-download.
3. **`demos/e2e_ethiopia.py` → `demos/e2e_austria.py`** (rename; already done by user for inputs).
   It is a **reusable template**: a clearly-marked config block + CLI args
   `--roi --train --id-col --label-col --out` (Austria values as defaults) are the *only* things a
   team changes for a new region; `--bands`/adapter are the model-specific part (documented as
   such). Changes: new step 2 (probe + `download_resume`), step 3 uses the `--id-col`/`--label-col`
   (default `fid`/`crop`), step 5 switches to **ROI-mode `run_inference`** with `merge="reproject"`
   (works single- **and** cross-zone; delete the old `create_datacube` step 4 and the pre-built
   step-5). Add the reporting math (transfer/convert/probe/effective).
4. **`demos/E2E_AUSTRIA.md`** (new, D9) — the team doc (§5).
5. **`estimate_run` + `cost_model`** (D12/§7) — the no-download ETA helper + per-band byte
   accounting (D11: `DownloadResult.bytes_by_band`).
6. **Tests.** All offline/synthetic (no real CDSE in pytest):
   - fake `_transfer_and_convert` (monkeypatched) → `DownloadResult.transfer_seconds/
     convert_seconds/bytes_downloaded/bytes_by_band` populate; `download_resume` sums them.
   - **cross-zone merge (D7):** two tiny COGs in different EPSGs → `merge="reproject"` targets the
     **area-dominant** CRS, and `merge_crs=<EPSG>` overrides it; nodata preserved.
   - `estimate_run` math against a synthetic cost model + monkeypatched counts.
7. **Docs:** CHANGES.md (DownloadResult fields + probe + reproject area/`merge_crs`), PROGRESS.md
   (P0.9 gate), RECIPES.md (the one-command run + creds), ROADMAP.md (mark P0.9 done on green),
   spec 19 pointer → 23.

---

## 5. `demos/E2E_AUSTRIA.md` — outline (the go-to doc)

1. **What fsd does locally** — the pipeline in one diagram (download → COG → datacube → flatten →
   train → bundle → ROI infer → COG/STAC/merged). The user-facing surface is **four verbs**
   (`fsd.download`, `fsd.create_training_data`, `fsd.run_inference`, `fsd.deploy` — the last a P6
   stub, spec 16); every verb **preflights** (asserts bands/T/inputs and fails fast with a clear
   message *before* any heavy compute), so most mistakes surface in seconds, not after an hour.
2. **Where the imagery comes from — `fsd.download` is a separate step, and why (CDSE now; MPC
   later).**
   - **Download is its own verb, run once, up front** (`fsd.download` → a `catalog.parquet` + local
     COGs). The compute verbs (`create_training_data`, `run_inference`) **read** that catalog and
     **never call the satellite source themselves.** If imagery is missing they stop with an
     **actionable `plan_download` message** (the exact `fsd.download(...)` params + GB/ETA), never a
     silent auto-fetch. Step 2 of this demo *is* that download.
   - **Why separate — three reasons, not just quota:** (1) **CDSE quota** — one controlled pull, not
     N pulls from N compute workers; (2) **redundant fan-out** — 1,000 grid cells over overlapping
     MGRS tiles would otherwise refetch the same bytes 1,000×; (3) **the Batch model** — download
     once → storage (local now, Azure Blob later) → compute reads from the storage seam.
   - **CDSE needs the download because it serves quota'd S3 `.jp2`**, which fsd **converts to COG on
     arrival** (the native ingest format the datacube build reads fast). No COG = no fast in-place
     read — so with CDSE, `download` is **required** before `create_training_data`/`run_inference`.
   - **How this changes with Microsoft Planetary Computer (MPC), later.** MPC serves **COGs over
     public HTTP + STAC** — no quota, and (crucially) **no conversion needed.** So fsd will read MPC
     pixels **in place** through the same **GDAL VSI** path it already uses for raster reads: an
     MPC-backed catalog is just a `TileCatalog` of remote `/vsicurl/https://…` COG URLs. The verbs
     don't change and there is **no `if source==…` branch** — you point the compute verbs at an MPC
     catalog and it "just works" because **there is nothing to materialize**, so the missing-data
     guardrail simply never fires. fsd still **never fetches behind your back**; a `download` for MPC
     becomes an **optional cache** for Batch efficiency, not a prerequisite.
   - **In one line: CDSE → `download` required; MPC → `download` optional.** *(The MPC path is
     forward design — not built yet; see spec 23 §6 "Future" / TODO #21.)*
   - **CDSE is intermittently flaky (BUG-001), and that's expected — the download is built for it.**
     Discovery (STAC) is **anonymous**; only the byte download needs **S3 keys**. The download is
     **idempotent** (skips files already on disk), fail-fast with a **circuit breaker**, and wrapped
     in a **resume-loop** (`download_resume`): if a pass trips on a bad CDSE window, **just re-run —
     it resumes** and completes the remainder. So a slow/failing pass is not a fsd bug; the catalog
     makes a re-run a clean resume. (`max_tiles` guards against a runaway query; ~0.15–0.2 GB per
     granule for the 4 demo bands.)
3. **Prerequisites** — Python 3.11; `.venv-modeldeploy` = `pip install -e ".[dev,grid,model-example]"`.
   **The extras are deliberately split so core stays lean** (spec 16/18/19): `[grid]` = `s2`/`s2cell`
   (ROI→S2-cell tiling; **not** in core — it's why `fsd.grid` is an optional import); `[model-example]`
   = `scikit-learn`/`joblib`/`matplotlib` (the demo model + plots, **not** fsd itself — fsd never
   trains); `[dev]` = ruff/pytest; `[azure]` = `adlfs` (Phase-2, unused in v1). **CDSE credentials**:
   a gitignored `cdse_credentials.json` (legacy keys `sh_clientid`/`sh_clientsecret` for discovery,
   `s3_access_key`/`s3_secret_key` for download); S3 keys **can expire** — `CdseCredentials.is_expired`
   warns. **No VPN required** (fsd talks to CDSE over the public internet; a VPN only affects *your*
   measured throughput — see §10).
4. **Reuse it for your own region** (front-and-centre, not a footnote) — change **3 things**:
   `--roi your_roi.geojson`, `--train your_fields.geojson`, `--id-col/--label-col`. Everything else
   (download, tiling, build, infer, merge) is unchanged, **including cross-UTM-zone ROIs** (France,
   Russia): each cell builds in its own CRS and the merged map reprojects to one CRS
   (`merge="reproject"`, area-dominant target or `merge_crs=`). The **model** (adapter + bands) is
   the separate, model-developer-owned part (§7).
5. **Inputs** — `shapefiles/AT_ROI.geojson`, `shapefiles/AT_2018_TRAIN.geojson` (fid/crop, 9 classes).
6. **Run it** — `python demos/e2e_austria.py [--fast] [--cores N] [--infer-cores M] [--creds PATH]
   [--roi …] [--train …] [--id-col …] [--label-col …]`; what each of the 7 steps produces and where.
7. **Bundling YOUR model — the step-by-step guide (the heart of the doc).** fsd owns the plumbing
   (download, datacube, flatten, tiling, COG/STAC/merge, runner); **the model developer owns the two
   endpoints that connect their model to fsd.** Write a small adapter (duck-typed `ModelAdapter`
   Protocol; `BaseModelAdapter` gives defaults so it's ~10 lines), then `bundle.save`:
   - **7.1 Declarations (read at preflight, before any heavy compute):** `required_bands`,
     `n_timestamps` (T the model was trained on — leave `0`/model-determined if it varies),
     `output_dtype`, `output_nodata`, `output_band_names` (1 name → categorical map; N → probs/regression).
   - **7.2 Endpoint ①: datacube → model input** (developer-owned). The feature transform, declared
     **once** and run by fsd at **both** train and inference (the F1 anti-skew guarantee):
     - `feature_sequence` — a `fsd.bands.modify` pipeline `[(fn, kwargs), …]` on the 5-D
       `(samples, T, H, W, bands)` contract (the primary, declarative way), **or** override
       `features(data5d, band_indices)` for logic the sequence can't express.
     - `datacube_to_X(feats, band_indices)` — reshape features `(T,H,W,B)` → model input
       `(H*W, T*B)`. Default provided; override if your model wants a different layout.
   - **7.3 `predict(X_chunk)`** — your framework, model input → raw per-pixel predictions. fsd
     handles chunking (`predict_batch_size`) + NaN→nodata scatter.
   - **7.4 Endpoint ②: raw output → standard `Output`** (developer-owned). `to_output(raw, hw)` →
     `Output((bands,H,W), dtype, nodata, band_names)` — how your model's numbers become the COG
     bands fsd writes. Default maps a class/vector per pixel using the 7.1 declarations; override
     for custom band packing.
   - **7.5 `load()`** — read your artifact(s) into memory once per worker; `self.artifacts`
     `{name: absolute path}` is injected by the bundle. (fsd never trains — you bring a trained model.)
   - **7.6 Bundle it:** `bundle.save(adapter, {"model": "rf.joblib"}, "…/bundle")` → a folder with
     `bundle.json` (the manifest: `module:attr` adapter ref + the §7.1 spec + artifact hrefs) and the
     artifact(s). **Why it matters:** it's the shippable, self-describing unit; `read_spec` validates
     a run **without importing the model** (model-free preflight); and the `module:attr` ref must be
     **importable** (installed package / on `PYTHONPATH`) because it crosses a subprocess/Batch
     boundary — a `__main__`/notebook class won't reload. `DemoRF` in `demos/adapters.py` is a
     complete worked example.
8. **The bundle on disk** — annotated `bundle.json`; `read_spec` vs `load`; drift check (bundle is
   authoritative for fields the class leaves unset).
9. **Results** (filled from the run) — timing table; **download**: transfer_s vs convert_s vs
   wall_s, bytes (+ per band), **effective MB/s vs probe MB/s** + verdict; outputs inventory; QGIS
   screenshots.
10. **Trusting the numbers & estimating other regions** — how to read probe-vs-effective (when to
    re-run without background load; VPN is a *your-link* caveat, not CDSE); the **`estimate_run`**
    worked example (**Austria → France**): how counts (exact STAC/grid queries) × this run's
    `cost_model` give an ETA + GB for any region/window/bands, with the caveats from §7.

**Appendix A — Concepts & conventions you'll meet** (surfaced from specs 03/05/14/15/20; a teammate
otherwise learns these by surprise):
- **Time axis is derived, not free-form** (spec 15). `T = ceil((enddate − startdate) / mosaic_days)`;
  windows are **half-open `[start, end)`**, each labelled by its **start boundary**, and **empty
  windows are still emitted** (as nodata). Consequence: **every datacube over the same
  `(start, end, mosaic_days)` has a byte-identical `timestamps` axis** — which is *why* multi-tile /
  multi-CRS cubes can stack and **flatten requires it**. Your adapter's `n_timestamps` must equal
  this `T` (or be left model-determined). Dates are **localized to UTC** to compare against tz-aware
  catalog timestamps.
- **On-disk artifacts.** A datacube = `datacube.npy` + `metadata.pickle.npy` (the metadata is
  `np.save`'d-pickle, not raw pickle — a deliberate cross-platform-corruption fix). **`nodata = 0`**
  throughout. Inference = **one COG per cube** + a **STAC** catalog; the merged map is a display
  product (§ D7).
- **Everything is 10 m, resampled to a *real* B08 image** (spec 03), not an abstract target grid —
  the user's reference-image-resampling rule. Other resolutions need a different known-resolution
  reference band, not just different resample params.
- **Boundary cells don't lose data** (spec 20). When a grid cell straddles an MGRS-tile boundary, all
  covering tiles of the same acquisition are **nodata-fill merged** onto the reference grid (not
  collapsed to one) — the fix behind cross-zone correctness.
- **`flatten` drops all-nodata pixels** and keeps `coords.npy` (per-pixel easting/northing). *Caveat*
  (TODO #16): coords across two UTM zones are fine as per-pixel IDs but **not** as geography.
- **Validate visually in QGIS** — the pipeline saves RGB/composite + categorical outputs precisely
  because rasters must be eyeballed, not just unit-tested.

**Appendix B — Known v1-local limitations** (so these read as *known*, not as bugs you found):
- **COG conversion is local-dst only** — both COG-on-download (spec 14) and the inference-output COG
  (TODO #17) require a **local** path; remote/Blob is the deferred stage-local→convert→upload path
  (a P1/P4 item — the "who converts on Blob?" question §6 raises).
- **`cores > 1` requires a model bundle**, not a live adapter (it crosses a subprocess). The demo
  saves a bundle anyway; live adapters run sequential.
- **The datacube rectangle carries a nodata halo** and can't hug a slanted ROI edge (TODO #8) —
  cosmetic; `flatten` drops the nodata. Don't be alarmed eyeballing a cube in QGIS.
- **`fsd.deploy` is a P6 stub** (registration/push); local train+bundle+infer is the complete path.

---

## 6. What this gate catches — and the gaps it does NOT cover (read before P1)

**Catches (newly, vs prior demo):** real CDSE discovery + S3 transfer + jp2→COG on arrival;
download idempotency/resume under a flaky window; catalog build/append; training-data build over
real fields + flatten; adapter→bundle→**ROI build+infer** on freshly-built cubes; strict
single-CRS merge; end-to-end idempotency on real data; and **real, decomposed timings**.

**Gaps — NOT exercised here (flagged because we're gating P1 on "local is complete"):**
- **The storage seam swap itself (the whole point of P1).** All I/O is still local fsspec. This
  test proves everything *up to* the seam; it does not prove Azure Blob config-only swap. Expected —
  that's P1's job — but state it so "local complete" isn't misread as "cloud ready".
- **COG-on-download requires a LOCAL dst** (`cog=True` refuses `s3://`/`az://`, by design in
  `cdse.download`). On Azure the **stage-local→convert→upload** path is *deferred* — so "who
  converts jp2→COG when imagery lands on blob?" is an **open P1/P4 question this run surfaces but
  cannot answer**. Call it out explicitly in the doc.
- **Runner seam = Snakemake local only.** The Batch runner (P4) is not exercised; ROI fan-out is
  validated locally only.
- **Credential `from_env` / expiry rotation** (the Batch path) is untested; local uses `from_json`.
- **Multi-CRS / zone-straddling ROI** is intentionally *not* covered by Austria (single zone) —
  spec 20/21 + Ethiopia covered it; note the coverage split so it isn't assumed lost.
- **CDSE quota cost is real and one-time** — the doc records bytes/granule count so the team knows
  the price of a re-run.

**Did the user miss anything for the test to run?** Yes — **CDSE credentials** (not in the
request; required, D5) and the **id/label column rename** (`fid`/`crop`, handled in step 3). Both
folded in above. And the current script **never downloaded** (hard-wired to the deleted
`satellite_benchmark/` catalog) — Step 2 introduces download into an e2e for the first time.

### Future (NOT built in spec 23): quota-free sources (MPC) and the "seamless" interface (D14)

The recurring wish — "for a no-quota source, let `create_training_data`/`run_inference` just get the
data" — is best served **not** by auto-download-if-missing, but by recognising it's a
**source-capability** question:

- Explicit download exists for **three** reasons; only one is quota. The other two survive on MPC:
  **redundant fan-out** (1000 Batch cells re-fetching overlapping tiles wastes bandwidth/egress/
  wall-time even when free) and **reproducibility** (a materialized catalog is an audit artifact).
- MPC's real unlock is that it serves **COGs over HTTP+STAC**, so pixels can be **read in place** via
  the **GDAL VSI seam fsd already uses** for raster reads (the documented I/O exception). CDSE needs
  a download step *because* it serves quota'd S3 `.jp2` that must be converted to COG; MPC does not.
- **Design (later spec):** a small **source-capability model** — every source has `query_catalog`;
  *materializing* sources (CDSE) also have `download` (+ the `plan_download` guardrail); *streamable*
  sources (MPC) expose a `TileCatalog` whose asset paths are remote COG URLs (`/vsicurl/https://…`),
  read in place. The verbs stay **source-agnostic** (they consume a catalog; its assets are local or
  remote) — **no `if source==…` branch**. "Seamless for MPC" then means the missing-data guardrail
  **simply never fires** (nothing to materialize), *not* that fsd fetches behind the user's back.
  Explicit materialization stays available as an **opt-in cache** for Batch efficiency.

Spec 23's `plan_download` is designed to compose with this (it's the CDSE materializing-source arm).
Roadmap/TODO entry to follow.

---

## 7. Extrapolation: full-France & arbitrary region / dates / bands

The recurring question ("how long for a full-France deploy?") is answerable **without downloading
France**, because runtime = **counts × per-unit-costs**, and the counts are cheap exact queries
while this gate calibrates the costs.

**Counts (exact, no download):**
- **granules** `= len(query_catalog(roi, start, end, max_cloudcover))` — anonymous STAC, no bytes.
- **band-files** `= granules × len(bands)` (× per-band availability).
- **grid cells** `= len(roi_to_s2_grids(roi, grid_size_km))` — offline.
- **T** `= compute_n_timestamps(start, end, mosaic_days)` — offline.

**Per-unit costs (measured by THIS run, written to `timings.json` as a `cost_model` block):**
- `transfer_mb_per_s` (effective, at `MAX_CONCURRENT_S3`) and `probe_mb_per_s` (single-thread).
- `bytes_by_band` → mean file size per band (D11) → total bytes for any band subset.
- `convert_s_per_file` (COG conversion, CPU/local — machine-bound, not CDSE).
- `build_s_per_cube`, `infer_s_per_cube` (from steps 3 & 5, per-cube at the run's T).

**Estimator** `estimate_run(roi, start, end, bands, *, creds, max_cloudcover, mosaic_days,
grid_size_km, cost_model)`:
1. queries granule & cell counts + T (above);
2. `bytes = granules × Σ_band mean_bytes[band]`;
3. `download_s ≈ bytes / transfer_mb_per_s`; `convert_s ≈ band_files × convert_s_per_file`;
4. `compute_s ≈ cells × (build_s_per_cube + infer_s_per_cube) × (T / T_calib)` (T-linear);
5. returns a dict: counts, bytes (GB), and a low/high ETA band derived from probe-vs-effective.

Lives in the demo/reporting layer first (calls `cdse.query_catalog` + `grid` + the cost model);
graduates to `fsd.estimate` if it proves useful. The doc (§9) shows a worked
**Austria → France** example so the team can self-serve.

**Caveats baked into the estimator's output + doc (so it isn't over-trusted):**
- **Throughput is environment-bound** (VPN, background load, CDSE health, 4-thread cap). Holds
  within the same environment; the probe/effective spread is reported as the ETA band. Convert &
  compute costs are local/CPU-bound and transfer more cleanly than throughput.
- **Bytes/granule vary** at ROI edges (partial tiles) and by latitude — the mean is representative
  ±, not exact.
- **Cloud filter → non-linear granule count** in the date range: handled *exactly* because the
  estimator queries it, not models it.
- **CDSE quota / flaky windows** add resume-pass variance (super-linear tail) — flagged, not modeled.
- **Per-cell compute varies** with how many MGRS tiles a cell merges (zone-boundary/edge cells cost
  more); the mean over Austria's cells is the unit.

## 8. Sign-off checklist

- **SO-1** Instrument `_transfer_and_convert`/`_download_one`/`download`/`download_resume` +
  `DownloadResult` fields (D1/D10); offline unit test.
- **SO-2** `probe_throughput` in `cdse`; demo computes probe vs effective MB/s + verdict (D2).
- **SO-3** `e2e_austria.py`: integrated idempotent `download_resume` step (D3/D4), `fid`/`crop`
  (D6), season window (D3), guardrails (D6).
- **SO-4** Step 5 → ROI-mode `run_inference`, `merge="reproject"` (cross-zone-safe, **no** zone
  assertion; D7); `_merge_outputs` area-dominant target + `merge_crs=` override + cross-zone unit
  test; delete old `create_datacube` + pre-built inference steps; idempotency re-run check.
- **SO-4b** `plan_download` guardrail (D13): needed-vs-present tile diff + JSON manifest + printed
  `fsd.download(...)` command (+GB/ETA when a cost model exists); the compute-verb preflight raises
  a `PreflightError` carrying it; offline unit test (monkeypatched STAC counts + a fake catalog).
- **SO-5** `--fast` = short season + sampled fields/cells (D8); reusable-template args
  `--roi/--train/--id-col/--label-col/--creds` (D5, §1).
- **SO-6** `demos/E2E_AUSTRIA.md` per §5 (incl. the data-source/download-verb §2, the bundling
  guide §7, **Appendix A concepts/conventions + Appendix B known-limitations** distilled from specs
  01/03/05/14/15/16/20), Results filled from a real run.
- **SO-7** CHANGES/PROGRESS/RECIPES/ROADMAP updated; spec 19 → 23 pointer; pytest + ruff green.
- **SO-8** `bytes_by_band` (D11) + `cost_model` block in `timings.json` + `estimate_run`
  (D12/§7) with an Austria→France worked example in the doc; offline unit test for the estimator
  math (fed a synthetic cost model + monkeypatched counts — no network).

**Explicit confirmations wanted before I implement:** D5 (creds path), D6 (guardrail values),
D7 (**`merge="reproject"` cross-zone-safe default** + area-dominant target + `merge_crs=` override,
no zone assertion — corrected), D9 (doc location), D12 (estimator scope — demo-level helper now vs
a first-class `fsd.estimate` verb), and the season window in D3.
