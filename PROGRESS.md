# PROGRESS — fsd

Resume anchor. Read this + `specs/00-overview.md` to pick up where we left off.

_Last updated: 2026-07-11_

## LATEST (2026-07-11) — spec 25 SIGNED OFF (download/jp2→COG redesign) — ready to implement

**Spec `specs/25-download-convert-redesign.md` is SIGNED OFF; next action = implement in a fresh
Sonnet@medium session** (spec 24 D3/D5 — user runs `/handoff`, switches `/model sonnet` + `/effort
medium`, points it at spec 25). Claude did NOT implement (Opus plans, Sonnet implements).

**The fix (all in `sources/cdse.py` + `config.py`; read/build path, `to_cog`, `DownloadResult` shape
untouched):** conversion currently runs **inline on the 4 transfer threads** and GDAL's `to_cog`
**holds the GIL** → starves downloads (observed: 8.8 MB/s probe but ~0.2 file/s aggregate). Redesign =
split the per-file worker into `_transfer_one` (thread stage) + `_convert_one` (top-level, picklable,
**process** stage), and run them as **one continuous A2 pipeline**: `ThreadPoolExecutor(MAX_CONCURRENT_S3=4)`
transfers → each completion chains its staged JP2 to `ProcessPoolExecutor(MAX_CONVERT_PROCS=min(cpu,8),
spawn)` via `add_done_callback`; a `BoundedSemaphore(MAX_STAGED)` bounds staged-but-unconverted JP2s.

**Locked decisions (C1–C6 all accepted as recommended):** callbacks + single `sem_staged` (C1); keep
`_download_one` as a sequential wrapper so its tests survive, `download()` won't call it (C3);
circuit breaker → **streaming stop on consecutive *transfer* failures only** (rewrite the one breaker
test) (C4); new keyword knobs `max_convert_procs`/`max_staged`/`convert_executor` (the injected
executor is the in-process test seam) + pass-through on `download_resume` (C5); **keep ingest
overviews** (D2 — convert stays the ~15 s/file ceiling, accepted); **disk-aware `MAX_STAGED`** =
`min(MAX_CONCURRENT_S3 + 2*MAX_CONVERT_PROCS, free*0.25/0.2GB)`, sized once at start, **cap not a
lever** (C6/D5). `chunksize` repurposed → catalog-flush cadence. Confirm-run deferred to **spec 26**.

**Concurrency-familiarization artifacts (workspace root, NOT in the fsd repo):** `concurrency_demo.py`
(the pipeline with sleeps+files — backpressure/LEAK_BUG/disk-accounting demos) and
`concurrency_sweep.py` (network-free `MAX_STAGED` tuning sweep showing the throughput plateau past the
saturation floor). Built to teach the primitives before implementing; not part of the package.

**Test plan (pytest only, no network):** most existing download tests must still pass;
`test_circuit_breaker_trips_and_stops_early` is rewritten (C4); new tests for `_transfer_one`,
`_convert_one`, the cog=True pipeline (via injected synchronous `convert_executor`), backpressure
bound, lazy-pool (no procs on all-skip/cog=False), and `_default_max_staged`. Docs to update on
implement: `CHANGES.md`, `TODO.md`, `specs/14` pointer, `config.py` comments, `PROGRESS.md`, memory.

## LATEST (2026-07-11) — spec 24 working contract (process, not pipeline)

**How we work now (CLAUDE.md updated):** Claude **never runs pipeline/long/networked scripts** or
backgrounds/polls them (may run `ruff`/`pytest`/`grep`/`git status`); everything else is a
**run-book** in `fsd/runbooks/` (template landed) that the user runs, pasting back a step's
**`_result.json`** (Claude diffs vs success criteria, never reads live logs). **Model split:**
Opus@high plans/specs/debugs; user `/model sonnet` + `/effort medium` to implement a signed-off
spec. **Handoff:** flush durable state to PROGRESS/MEMORY → user runs `/handoff` → fresh session
(not `/compact`). Trigger for this spec: the spec-23 tiny-download run went wrong as a *process*
failure (I launched a long download, user couldn't stop it / see progress, my log-polling burned
tokens). **Next queued: spec 25 (download + jp2→COG redesign — inline GIL-bound conversion starves
transfers), then spec 26 (safe runner: `--dry-run`/`--stop-file`/progress).**

_Open from spec 23:_ `--tiny-download` was fixed to select a **single MGRS tile** (7 granules / 1
tile / ~2 GB, verified offline) but the real e2e run has **not** been completed (I must not run it);
that becomes a run-book. Specs 20–24 remain **UNCOMMITTED**.

## LATEST (2026-07-10) — P0.9 local-completeness gate (spec 23) — LAST local step before P1

**Next step: run `demos/e2e_austria.py` on real data** (needs CDSE creds + network; the user runs
it) and paste the timing/QGIS Results into `demos/E2E_AUSTRIA.md §8`. Then we start **P1** (Azure
storage seam — see `../P1_AZURE_SETUP.md` at the workspace root for the prerequisites the user fills).

Spec 23 (SIGNED OFF + IMPLEMENTED, **176 tests, ruff clean**) turned the demo into the **go-to local
run-book + confidence gate**: `demos/e2e_ethiopia.py` → `demos/e2e_austria.py`, now starting from a
real CDSE **download** (the first e2e to include it) on an Austria ROI (single UTM-33; `fid`/`crop`,
9 classes). Landed:
- **Download instrumentation** (`fsd.sources.cdse`): `DownloadResult.{bytes_downloaded,
  transfer_seconds,convert_seconds,bytes_by_band}` — decomposes CDSE-transfer vs local jp2→COG cost;
  `sum_results` (resume-pass aggregate); **`probe_throughput`** (baseline MB/s to factor out
  VPN/contention). `_download_one` now returns `(ok, reason, metrics)`.
- **`plan_download` guardrail** (D13): missing imagery → an actionable `fsd.download(...)` plan
  (JSON + printed command, +GB/ETA); wired into the `create_training_data`/`run_inference` preflight.
  Compute verbs still **never auto-fetch** (quota + Batch download-once model).
- **Cross-UTM-zone-safe merge** (D7): `run_inference(merge="reproject")` targets the **max-area** CRS
  (or `merge_crs=`), lossless where a cell already matches — the reusable template runs for any ROI,
  cross-zone included.
- **Reusable template + tooling**: `--roi/--train/--id-col/--label-col/--creds`; `demos/estimate.py`
  (no-download ETA for any region — answers "how long for full France?"); `demos/E2E_AUSTRIA.md`
  (setup + bundling guide + concepts/limitations appendices).

## LATEST (2026-07-06) — P0 (specs 16/17) + P0.5 (spec 18) + e2e demo/tiling (spec 19)

The v1 core pipeline (download → catalog → datacube → flatten → workflows) is **complete +
real-data-validated** (see history below). We have since set the **forward direction**:
- **Strategy docs (on `main`):** `ROADMAP.md` (north-star, 3 usage modes, control/data-plane,
  ModelAdapter contract F1–F5 + same-`T`/bands + preflight, phased **P0–P6**),
  `AZURE_INFRA.md` (the read-only `rise` project in `raapid-infra` we scale onto via Batch),
  `RSLEARN_COMPARISON.md` (build-vs-borrow vs AllenAI's rslearn — **open decision**, evaluated on
  branch **`spike/rslearn`** with an isolated venv; scale-out is ours regardless). Repo pushed to
  `git@github.com:nikhilsrajan/fsd.git` (MIT).
- **Spec 16 = P0 DONE (2026-07-06):** high-level API façade `src/fsd/api.py` re-exported at top
  level — `fsd.download`, `fsd.create_training_data` (hides flatten; preflighted; `runner`/
  `storage` seams local-only), `run_inference`/`deploy` **stubs** (P4/P6), `compute_n_timestamps`,
  `TrainingData`, `PreflightError`. Version `0.1.0`. README quickstart rewritten. **133 tests,
  ruff clean** (`tests/test_api.py`, 9 new). STAC split to **spec 17**; ModelAdapter to **P0.5**.
- **Spec 17 = STAC catalog DONE (2026-07-06):** `src/fsd/catalog/stac.py` + `TileCatalog.to_stac`
  — additive STAC export (GeoParquet schema unchanged); one Item per tile-product, one asset per
  band; `proj:code` from the MGRS tile (no raster reads); static self-contained STAC JSON via
  `pystac` (now a direct dep) through the storage seam; round-trippable. Real-data smoke: 579-tile
  benchmark → 579 items in 0.06 s, both UTM zones. **140 tests, ruff clean** (7 new). `stac-geoparquet`
  deferred; advances TODO #14 (STAC half; TiTiler serving = P5).
- **Spec 18 = P0.5 DONE (2026-07-06):** the **ModelAdapter contract** + local train/deploy. New
  `src/fsd/model/` (`adapter` [Protocol + `BaseModelAdapter` + `Output`], `features` [the F1
  anti-skew chokepoint + `median_per_id`], `engine` [fsd owns the predict loop → COG], `bundle`
  [self-describing `module:attr` bundle, save/load, model-free preflight]). `api.py` wired:
  `create_training_data(adapter=/feature_sequence=/aggregate=)` writes `features.npy` additively;
  **`run_inference` is real** (local engine over pre-built inference datacubes → COG per cube +
  STAC via new `catalog.stac.cog_outputs_to_items` + optional merged map); `deploy` still a P6
  stub (bundle format now pinned). Example `examples/eurocrops_rf.py`; runbook
  `tests/manual/deploy.md`; explainer `specs/18-model-bundle-explainer.md`. **150 tests, ruff
  clean** (`tests/test_model.py`, 9 new). One bug fixed: engine copies `band_indices` (modify_bands
  mutates it). ROI→S2-tiling front-end for `run_inference` stays **P4**.
- **Spec 22 = retire `engine.run_local`'s `mp.Pool` + idempotent inference DONE (2026-07-07):**
  after P0.75, the pre-built-cubes inference pool was the last parallel fan-out **not** on the runner
  seam. Now: `cores=1` stays **in-process sequential** (tests/debug/small, no bundle); `cores>1`
  fans out via the **Snakemake infer-only runner** (`workflows/infer_only_task.py` +
  `_snakefiles/infer_only/Snakefile` + `runners.run_local_infer_only`), routed from
  `api.run_inference` (kept out of `engine` to avoid a model→workflows cycle). **No `mp.Pool`
  anywhere** → Batch (P4) can dispatch pre-built inference too (pure `runner=` swap). **Inference is
  idempotent:** both paths skip existing outputs unless `overwrite=True` (fixes the demo re-run the
  user hit — engine re-inferred despite existing `output.tif`). New `cubes_per_task` knob (default 1)
  groups K cubes per job to amortise the bundle load — the intra-task loop is **sequential, no pool**.
  Default `cores=1` → backward-compatible. **167 tests, ruff clean** (+4). **Real cores>1 smoke**
  (.venv, 5 synthetic cubes, cubes_per_task=2 → 3 Snakemake groups): 5 COGs + STAC, rerun = "Nothing
  to be done" (idempotency confirmed). Docs: `CHANGES.md`, `specs/18` pointer, `deploy.md`.
- **Spec 21 = P0.75 ROI inference verb DONE (2026-07-07):** `run_inference(roi=…)` completes
  **Mode A** — one call tiles an ROI (`fsd.grid`), builds one datacube per S2 grid cell, infers,
  and writes per-cell COGs + STAC (+ optional merged map). The per-cell **build+infer** is a single
  **runner-dispatched** unit-of-work (`workflows/infer_task.py` + `_snakefiles/create_inference/`
  Snakefile + `runners.run_local_inference`), *not* the spec-18 `mp.Pool` — so **P4 = a pure
  `runner=` swap to Batch** (the reason we folded inference into the runner seam). `run_inference`
  now takes `roi=` **xor** `inference_datacubes=` (both optional; positional calls still work);
  `merge` is tri-state `False|True|"reproject"` (strict single-CRS vs lossy dominant-zone display
  merge — the demo's logic moved into `api._merge_outputs`; demo now calls `merge="reproject"`).
  **SO-6:** ROI inference never calls CDSE (imagery assumed present; conserve quota → on cloud,
  Batch reads blob). **163 tests, ruff clean** (+11). **Real smoke** (`.venv-modeldeploy`, benchmark):
  ~9 km ROI → 10 cells → 10 COGs + STAC + reproject-merge (899×889, 96.9 % valid), 42 s @ cores=2;
  resumability confirmed. Bug fixed: snakemake parses empty `--config key=` as `None` → omit
  `predict_batch_size` when None. Runbook `tests/manual/roi_inference.md`; supersedes deploy.md §3's
  3×3-grid stand-in. **This clears the last pre-Azure phase — next is P1 (Azure storage seam).**
- **Spec 20 = datacube-builder tile-merge bugfix (2026-07-07):** the spec-19 demo exposed a
  **correctness bug** — `_stack_datacube` kept only **one** tile per `(timestamp, band)` (a dict),
  so shapes straddling an MGRS tile boundary lost the coverage of every other same-acquisition
  tile (worst demo grid `165b09c`: 0.6 % valid despite ~80 % raw coverage; clustered on the
  lat-11.75 tile-row boundary). A faithfully-ported legacy bug, hidden until inference grids
  (spec 19) were the first shapes big enough to straddle tiles. **Fix:** nodata-fill **merge all**
  same-`(timestamp,band)` images onto the reference grid (tie-break: `dst_crs`-native first),
  confined to `_stack_datacube`. **Verified:** `165b09c` 0.6 % → 82.8 % valid; 2 new unit tests.
  Post-fix demo re-run: merged map 90 % → **96 %** valid, **0** dead grids (was 9). Docs:
  `BUGS.md` BUG-002, `CHANGES.md`, `specs/03`, `specs/20`.
- **Spec 19 = end-to-end demo + ROI→S2 tiling (2026-07-06):** landed **`src/fsd/grid.py`**
  (`roi_to_s2_grids`, clean-room port of `rsutils.s2_grid_utils`; `s2`+`s2cell` in the optional
  `[grid]` extra — ROADMAP §4 / P4 groundwork, `run_inference(roi=…)` front-end still P4) +
  `tests/test_grid.py` (4 tests, skip without `[grid]`). New **`demos/`** runs demo_01+02+03 as
  one flow (tiling → `create_training_data` → RF → inference datacubes → `run_inference` →
  COG/STAC + crop map + NDVI-timeseries/crop-map/grids figures) on the existing Ethiopia data, in
  an **isolated `.venv-modeldeploy`** (`[dev,grid,model-example]`; keeps fsd's `.venv` lean).
  **`--fast` validated** (67 s); full run = 300 grids / 1015 fields / T=19. **Finding:** the ROI
  straddles the S2 zone-36/37 boundary → per-grid datacubes are mixed 32636/32637, so
  `run_inference(merge=True)` refuses (single-CRS principle) and the demo reproject-merges outputs
  to the dominant zone for the display map. Model quality is meaningless (Austria labels on
  Ethiopia pixels) — pipeline validation; real run after the Austria download.
- **AZURE_INFRA.md scrubbed + git history rewritten (2026-07-06):** private-infra names/IDs/CIDR/
  budget removed from the public repo (placeholders); concrete values live only in the local,
  never-committed `AZURE_INFRA_PRIVATE.md` at the workspace root.
- **Next:** **P1** (Azure storage seam: adlfs/MSI + GDAL-VSI) — the last pre-Azure local phase
  (P0.75, spec 21) is now done, so the whole local Mode-A product is complete. P1 needs Azure
  access from this laptop (VPN + `az login`); the setup checklist is `../P1_AZURE_SETUP.md`
  (workspace root, uncommitted). Alternatively the `spike/rslearn` benchmark (the big
  build-vs-borrow unknown). NB the Azure-Batch spec is a *future* number (not spec 10 — that's
  "storage-and-scale", already used).

## Where we are

Spec phase **complete and signed off**; package **scaffolded**; `storage` and
`catalog` **implemented and tested** (16 automated tests pass, ruff clean).

## Build order & status (from `specs/00-overview.md §7`)

| # | Module | Status |
|---|--------|--------|
| 0 | `config.py` | ✅ done (constants) |
| 1 | `storage/fs.py` | ✅ implemented · ✅ verified (`tests/test_storage.py` + manual `storage.md` Section A all pass; Section B = S3, needs creds, still manual) |
| 4 | `sources/cdse.py` | ✅ `CdseCredentials` + `query_catalog` + `download` implemented (18 tests, ruff clean). **Discovery pivoted to the CDSE STAC API (`pystac-client`, anonymous) — drops `sentinelhub` and the flaky S3 `.SAFE` listing (BUG-001)**; band S3 hrefs come from STAC `assets`. Metadata path live-verified (Ethiopia ROI, 138 tiles Jan–Mar 2018, highest-res selection + MTD_TL.xml). **At-scale download DONE + hardened (2026-07-02):** 1-year Ethiopia multi-CRS download completed — 579/579 tiles, 94 GiB in `satellite_benchmark/`, verified integrity. Resilience: atomic `.part`+rename transfer, S3 timeouts, circuit-breaker + `download_resume`, newline progress. Concurrency/quota sweep = TODO #9. |
| 2 | `catalog/catalog.py` | ✅ implemented · ✅ verified (`tests/test_catalog.py`, 6 tests) |
| 3 | `raster/images.py` | ✅ implemented · ✅ verified (`tests/test_raster.py`, 24 tests; + RGB/GeoTIFF save helpers) |
| 3 | `bands/modify.py` | ✅ implemented · ✅ verified (`tests/test_bands.py`, 12 tests) |
| — | **real-data validation** (raster+bands) | ✅ `tests/manual/realdata.md` — TCC/FCC/NDVI on tile T33UWP confirmed in QGIS by user |
| 5 | `datacube/ops.py → builder.py → flatten.py` | ✅ implemented · ✅ unit-tested (14 tests) · ✅ real multi-CRS build verified + runbook `tests/manual/datacube.md` (user QGIS-confirmed geolocation/merge/resample/mask; edge-tightness nit → TODO #8) · ✅ **heavy 1-yr benchmark + NDVI report** (`benchmarks/datacube_report_2018_ethiopia.md`). |
| 6 | `workflows/task.py · runners.py · create_datacube.py` + Snakefile | ✅ implemented · ✅ tested (`tests/test_workflows.py`, 5 tests incl. real Snakemake dry-run) · ✅ **real full e2e verified** on `satellite_benchmark` (ROI 165bca4): setup→Snakemake→`task` CLI→build→`datacube.npy (2,554,533,3)` + `done.txt`; **resumability confirmed** (re-run = "Nothing to be done"). |
| — | `notebooks/01_data_prep.ipynb` | ⬜ later |

## Next step (when resuming)

`sources/cdse.py` (module #4) is **complete + hardened + proven at scale**: the
1-year Ethiopia multi-CRS download finished cleanly — **579/579 tiles, 94 GiB, in
`satellite_benchmark/`**, integrity verified (0 zero-byte/truncated/`.part`). Along
the way the download got production-grade resilience: atomic `.part`+rename transfer,
S3 connect/read timeouts, circuit-breaker + `download_resume` loop, and log-friendly
newline progress. See `benchmarks/download_report_2018_ethiopia.md`.

**Dataset change:** the old `satellite/` (T33UWP) was **deleted**; the real-data test
set is now **`satellite_benchmark/`** (Ethiopia `s2grid=165bca4`, EPSG:32636+32637,
bands B04/B08/B8A/SCL). `realdata.md` TCC/FCC examples are stale (no B02/B03); only
NDVI applies there. **As of 2026-07-04 this archive is COG** (`Bxx.tif` + overviews;
migrated in place from JP2, catalog updated — see spec-14 bullet below).

**Datacube module #5 DONE (2026-07-02):** `ops.py` (run_ops, apply_cloud_mask_scl,
drop_bands, median_mosaic [numba], area_median), `builder.py` (build_datacube seam +
flatten_catalog helper: missing-check → load/crop → dst_crs by max-mean area →
merged-B08 reference → resample-to-ref → stack → SCL mask → drop → median mosaic →
save via storage), `flatten.py` (per-pixel training arrays + coords). 14 unit tests
(89→92 total). One legacy bug fixed: missing-band nodata fill shape (CHANGES.md).
Two design rationales captured from the user (memory): `_dt2ts` UTC localization,
`metadata.pickle.npy` cross-platform pickling.

**Module #5 fully validated (2026-07-03):** unit tests + user QGIS pass + a **heavy
full-year (2018) benchmark** on the real multi-CRS ROI. Findings: build is **I/O-bound**
(load_images 70–75% of time; cold 238 s vs warm 72 s per ROI; peak ~4 GB), output
`(19,554,533,3)` correct — the masked-mosaic NDVI traces real phenology (peak ~0.53 in
Sep) and cloud masking lifts growing-season NDVI up to +0.36. Report + 3 figures +
reproduce scripts in `benchmarks/` (matplotlib was `pip install`ed into `.venv`; it's
already declared in the `notebooks` extra).

**⚠️ UNCOMMITTED (paused mid-session, all on disk):** `benchmarks/datacube_report_2018_ethiopia.md`,
`benchmarks/datacube_2018_figures/` (3 PNGs), `benchmarks/datacube_year_ethiopia.py`,
`_plots.py`, `_stats.json`, and the PROGRESS edits above. Keep the 2 notebooks OUT.
Commit these when resuming (user hadn't given the commit word before the pause).

**Module #6 workflows DONE (2026-07-03):** task/runner/entrypoint split + bundled
Snakefile (`fsd.workflows`), 5 tests incl. a real Snakemake dry-run. This **completes the
v1 core pipeline: download → catalog → datacube → flatten → workflows.** Adaptations in
CHANGES.md (parquet subset via `TileCatalog.filter`, `if_missing_files="warn"` default,
`sys.executable -m` invocation, `fs.rm`).

**⚠️ PAUSED 2026-07-03 with UNCOMMITTED module #6 (all on disk):**
`src/fsd/workflows/{task,runners,create_datacube}.py`, `src/fsd/workflows/_snakefiles/create_datacube/Snakefile`,
`src/fsd/storage/fs.py` (added `rm`), `tests/test_workflows.py`, `CHANGES.md`, `PROGRESS.md`.
Keep the 2 notebooks OUT. Commit on resume.

**v1 core pipeline is COMPLETE and end-to-end verified** (download → catalog → datacube →
flatten → workflows), on real multi-CRS data, incl. Snakemake resumability.

**Datacube-speed track (TODO #15) started — 3-part, benchmark-first:**
- **Part 1 — spec 11 DONE + committed (2026-07-03):** reusable parallelism-sweep harness
  (`benchmarks/datacube_throughput_sweep.py`) + baseline report. Finding: throughput knees at
  **cores=4** (2.39×); per-grid `load_images` slows **2.41s→9.07s (3.76×)** with parallelism
  → **I/O read contention is the bottleneck** (~60% of build). `build_datacube(write_timings=)`
  flag added (env-gated via `FSD_WRITE_TIMINGS`). Runbook: `tests/manual/throughput_benchmark.md`.
- **Part 2 — spec 12 DONE + implemented (2026-07-04):** per-read instrumentation. Builder
  `write_read_log` → `reads.jsonl` per grid (id, mgrs_tile, product_id, band, filepath, wall-clock
  start/end, duration; env-gated `FSD_WRITE_READ_LOG`, requires `njobs_load_images==1`). Harness
  `--read-log`: **read conflicts** (overlapping read pairs, different grids) + **read-duration-vs-
  concurrency** curve (instantaneous peak-in-flight; the hypothesis test) + **same-file / same-tile
  / different-tile** split. Pure analysis unit-tested (107 tests). **Full 100-grid `--read-log`
  run DONE (2026-07-04)** — report `benchmarks/datacube_throughput_report.md`.
  **FINDING:** hypothesis **confirmed** — read duration 0.056s→0.274s (**4.87×**) as concurrency
  1→10; all `cores` lines collapse onto ONE duration-vs-concurrency curve; total `load_images`
  work 279s→912s (**3.27×**) for the *same* 6284 reads → **shared disk-bandwidth ceiling**, wall
  plateaus past the cores=4 knee. **Conflicts are only 0.6% same-file** (372 / 15457 same-tile /
  43082 diff-tile) — so **Part-3 tile-splitting-to-kill-same-file-conflicts targets a negligible
  slice.** Self-check passes (sum_read_seconds ≈ load_images phase). Nuance in the report verdict:
  it measures *simultaneous* conflicts not *redundant* reads; the inference workload isn't covered.
- **COG vs JP2 experiment — spec 13 DONE + implemented (2026-07-04):** first speed lever pursued
  (Part 2 pointed at JP2 wavelet *decode* cost). `benchmarks/prep_cog_dataset.py` (JP2→base COG,
  DEFLATE+PREDICTOR=2, lossless via NBITS=16, disk pre-flight, storage report) + harness
  `--catalog/--start/--end/--tag` + `benchmarks/compare_cog_jp2.py` (team report + duration-vs-
  concurrency overlay). No `src/fsd/` change. Runbook `tests/manual/cog_experiment.md`. 113 tests,
  ruff clean. **Full 4-month A/B DONE (2026-07-04)** — `benchmarks/cog_vs_jp2_report.md`.
  **RESULT:** COG **1.58×→3.46× faster wall** (cores 1→10), **up to 9.42× faster load_images**;
  COG mean read is **FLAT vs concurrency (1.01×)** while JP2 rises 3.45× → the slowdown was JP2
  wavelet **DECODE** contention, **not** disk bandwidth (**corrects the Part-2 framing**). Cost:
  base COG **1.225× JP2 storage (+23%)**, lossless. Clear win. (COG also scales past the JP2
  cores≈4-6 knee, since the decode bottleneck is gone.)
- **Tile-centric batching + other levers — PARKED (2026-07-04):** target the bandwidth/decode
  costs, not same-file conflicts. Revisit only if build speed becomes a priority again. See TODO #15.
- **COG-on-download — spec 14 DONE + implemented (2026-07-04):** FIRST production `src/fsd/` change
  out of the COG track. `sources.cdse.download(cog=True, default)` converts each fetched JP2 band →
  lossless COG (`Bxx.tif`, catalog records `.tif`) **with overviews** (TiTiler-ready); `cog=False`
  keeps native JP2. New `src/fsd/raster/cog.py::to_cog` (lossless, atomic `.part`+replace, NBITS=16
  for uint16, optional verify) — the single COG-profile home (config constants); `prep_cog_dataset`
  refactored to share it. Fetch→local staging sibling→`to_cog`→remove-staging; idempotency keys on
  the final `.tif`. **Local-dst only in v1** (remote raises; stage→convert→upload deferred to
  Azure). Read/build path untouched (rasterio reads `.tif`). 119 tests, ruff clean. **Real smoke:**
  10980² B04 JP2 → COG bit-identical, overviews [2,4,8,16], 15.5 s, ~1.86× size (w/ overviews).
  Follow-ups in TODO #15: remote-dst COG, conversion process pool, bulk-migrate the existing
  `satellite_benchmark` archive.
- **satellite_benchmark migrated JP2→COG in place — DONE (2026-07-04):**
  `benchmarks/migrate_jp2_to_cog.py` converted all **2316 band files** to COG+overviews (lossless,
  0 failed), **deleted the JP2s** (no duplicate copies), and rewrote `catalog.parquet` to `.tif`
  (fully consistent, 0 missing). 72 min at 8 workers; archive **94→159 GiB**, ~10 GiB free. Tool is
  resumable, disk-floor-guarded, progress-bar + ETA, `--verify {full,quick,none}` (default quick).
  Conversion is **memory-bandwidth-bound** → 8 workers (perf cores) is the knee (10 gave no gain).
  The Part-1/2 throughput/read findings were on the *pre-migration JP2*; re-running now reads COG.

**Calendar-interval mosaic = spec 15 DONE + implemented (2026-07-05):** resolves TODO #2 and
unblocks `flatten` across a multi-tile/multi-zone training set. `median_mosaic` gained
`mosaic_scheme` (default `config.MOSAIC_SCHEME="calendar"`): fixed calendar windows off the
caller's `startdate`, labels = window-start boundaries, **empty windows emitted as all-nodata**
→ every cube over the same start/end/mosaic_days shares an **identical `timestamps` axis** whatever
tiles/orbits/zones it hit. Legacy via `mosaic_scheme="acquisition"`. Threaded through `build_datacube`,
`workflows.task` (`--mosaic-scheme`), `create_datacube.setup` (now anchors at caller dates, not
per-shape actual) + Snakefile. Sub-cadence behavior documented in `median_mosaic` docstring (window <
revisit → raw series padded with nodata slices). 124 tests, ruff clean. Real smoke: west (EPSG:32636)
+ east (EPSG:32637) fields → identical `[06-01, 06-21]` axis. New TODO #16 = multi-zone `coords.npy`.

**`flatten` real-data run DONE + validated (2026-07-05):** the last v1-pipeline stage to get a real
run. Built 1 datacube per EuroCrops field via the workflow (33-field class-stratified subset of
`shapefiles/austria_eurocrops_sampled_ethiopia_translated.geojson`, id=`fid`, label=`EC_hcat_n`, 11
classes, both zones), then `flatten` over the workflow `input.csv` → `data.npy (6502,2,3)` +
coords/ids/labels/metadata. **Consistency gate passed across both UTM zones** (spec-15 payoff),
total/per-field pixel counts match, round-trip exact. Runbook `tests/manual/flatten.md`. Full 1015-field
run = same commands (serial cube build ≈ 9 min). **v1 pipeline now fully real-data-validated end to end.**

**Other NEXT options:** Azure/Batch (spec 10, roadmap step 2); source extension (#11) / rslearn
benchmark (#12). Deferred: TODO #9; TODO #16 (multi-zone coords); `reference_profile` grid-from-bounds.

CDSE discovery pivot (2026-07-01): dropped `sentinelhub` + the S3 `.SAFE` listing for
the **CDSE STAC API** (`pystac-client`, anonymous). STAC item `assets` give per-band
S3 hrefs directly → no recursive S3 listing (the BUG-001 failure). Only the byte
`transfer` touches S3 auth, wrapped in fail-fast retry. On-disk layout unchanged
(strip `.SAFE`, short `B02.jp2` names) = the `satellite/` folder layout.
Residual resilience items (circuit breaker, per-tile restructure) tracked in BUGS.md.

**Test geometries** (`shapefiles/`, EPSG:4326): `s2grid=476da24.geojson` = Austria tile
T33UWP, single-tile (used for raster/bands realdata.md, done). `s2grid=165bca4.geojson`
= Ethiopia ROI (lon ~36.2/lat ~11.6) straddling the **36°E UTM zone boundary** → pulls
S2 tiles in **both EPSG:32636 & 32637** = THE multi-tile/multi-CRS test for CDSE download
+ datacube creation (its tiles aren't in `satellite/` yet, so download must run first).

## Decisions log (all locked unless noted)

- Scope: download → datacube → flatten. Train/deploy stay in notebooks.
- Sentinel-2 **L2A only**. **GeoParquet** catalog. Keep **Snakemake** as the *local*
  runner only. Keep `coords.npy`. CDSE query cache **removed**.
- Storage = **fsspec** seam (local now; blob/S3 additive). S3 transport **first-class
  & generic** (s3fs, any endpoint); no direct boto3.
- Real end goal: Azure Batch scale-out, **cloud-agnostic** — achieved via the storage
  seam + a runner-agnostic CLI datacube task. **No Azure code in v1.**
- OQ-3 **resolved**: source contract is a documented function signature (no ABC) until
  a 2nd source exists.
- Hard constraint: never edit `fetch_satdata/`, `rsutils/`, `cdseutils/` (read-only
  reference). Keep `DROPPED.md` / `CHANGES.md` current.

## Key files
- Design: `specs/00..10`. Living docs: `DROPPED.md`, `CHANGES.md`.
- Implemented: `src/fsd/config.py`, `src/fsd/storage/fs.py`.
- Manual tests: `tests/manual/` (one guide per module).
- Cross-session memory: see `MEMORY.md` entries `fsd-*`.

## Environment note
Deps are **not** in system Python. Dev setup:
`python3.11 -m venv .venv && source .venv/bin/activate && pip install -e ".[dev]"`.
