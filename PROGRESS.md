# PROGRESS — fsd

Resume anchor. Read this + `specs/00-overview.md` to pick up where we left off.

_Last updated: 2026-07-18_

## 🎉 P1 STORAGE SEAM PROVEN END TO END (2026-07-18) — `runbooks/31-p1-datacube-on-blob.md` ran GREEN (`"pass": true`). Spec 31 DONE.

The fsd core pipeline (build + flatten) ran with **every byte on the `rise` Azure blob**, switched on by config alone (`storage="azure"` / `FSSPEC_ABFSS_ANON=false`; account from the URL). `_result.json` all-green, verified against the corrected criteria (independently, not the `pass` flag):
- **Build 1** (`python -m fsd.workflows.task` as a real subprocess, remote `--export-folderpath`): wrote `datacube.npy`/`metadata.pickle.npy` to `abfss://` (D1/§3), streamed blob COGs via GDAL `/vsiadls/` + fresh token (D2/§4), and — inheriting `os.environ` unmodified — proved `FSSPEC_ABFSS_ANON` crosses the subprocess boundary (D4). Cube `[3,550,606,1]` uint16 (**T=3**, 1 band = B08 after SCL mask→drop); `task_slice_rows=9`.
- **Build 2** (`create_training_data(storage="azure")` via the real Snakemake runner, blob catalog, local export): T=3, `n_pixels=216583` — the normal entrypoint against a blob catalog.

Only stderr = a benign "time gaps (10 days)" S2-revisit warning. **This is the P1 exit criterion — spec 10 Seam 1 (storage = config, not code) realized on real Azure.** **→ NEXT: the ingest/normalization contract spec (TODO #38 — §5-ARCHIVE + the `clip(DN−1000,0)` vs `NODATA=0` encoding question + TODO #35), which re-opens download-to-blob for all sources.**

## 🧹 CONSOLIDATED TO `main` (2026-07-18) — all spec-31 worktrees merged + removed; **work from the `fsd/` checkout now, no more worktrees.**

Spec-31 work is now on **`main`** (`b24e6a2`, 3 commits: `6f3435f` compute seam + review, `1583ced` ROI-locate fix, `b24e6a2` build-1 filtered-slice fix), ahead of `origin/main` by 3 (**unpushed** — push only on request). Both worktrees (`spec31-p1-azure-compute-seam`, the stale `spec33-docs-update`) were removed; their content was verified fully present on `main` before removal (notebooks preserved as WIP; a `git stash` on `main` — "main-wip-pre-spec31-merge" — still holds the pre-merge state as a safety net, droppable with `git stash drop`). Two orphan branch refs remain (`worktree-spec31-p1-azure-compute-seam`, `worktree-spec33-docs-update`) — harmless; delete with `git branch -D` when convenient. Suite from `fsd/.venv`: **269 passed / 3 skipped, ruff clean** (venv has `[dev,azure]`). Two demo bugs fixed post-review while debugging the user's run: (1) the ROI path assumed a non-worktree layout; (2) build 1 fed `workflows.task` the raw catalog instead of a `TileCatalog.filter` slice → `KeyError: 'area_contribution'`. **→ NEXT: user re-runs `runbooks/31-p1-datacube-on-blob.md` from `fsd/`, pastes back `_result.json`.**

## ✅ Opus@high REVIEW (2026-07-17): **PASS with one fixed bug** — spec 31 P1 compute-seam implementation is sound; the demo script's success criterion was wrong (`EXPECTED_T=2` vs the real `3`), fixed here. Tree left uncommitted. **→ NEXT: user runs `runbooks/31-p1-datacube-on-blob.md`.**

**Reviewed** code-vs-spec + independent re-verification + 2 mutation tests (spec 24 D5 / spec 33 precedent), from **inside the worktree** `spec31-p1-azure-compute-seam` against its own `[dev,azure]` `.venv`. **Verdict: PASS.** The compute seam (`azure.py`/`rio_open`/`configure_storage`/the §6 abspath fix) matches the pivoted spec (§1–4/§6/§7); §5 correctly untouched (`git diff --stat` on `sources/mpc.py`+`cdse.py` = empty, verified, not taken on report); scope discipline clean.

**Verified independently, reproduced not trusted:**
- `pytest -q` → **269 passed / 3 skipped**; `ruff check src/ tests/` clean.
- Degrades cleanly without the `[azure]` extra: uninstalled `adlfs`/`azure-identity`/`azure-core`/`azure-storage-blob` → **244 passed / 4 skipped** (25 azure-seam tests skip via module-level `importorskip`), then reinstalled → back to 269/3.
- **Mutation A** (implementer's, re-run not trusted): reverted the `fs.is_local` guard in `create_datacube.setup()` → `os.path.abspath` unconditional → `test_setup_does_not_corrupt_a_remote_run_folderpath` fails, showing the exact corruption (`<cwd>/abfss:/data@acct.../s1`). Guard is load-bearing.
- **Mutation B** (my own choosing): dropped the `storage == "local"` no-op arm in `configure_storage` → `test_configure_storage_local_string_is_noop` fails (wrongly raises). The "third thing" (local-as-noop) is genuinely pinned. `storage=object()` still correctly raises (regression intact).

**Finding R1 (FIXED here) — demo success criterion was wrong (would false-fail a green run).** `runbooks/scripts/31_datacube_on_blob.py` asserted `EXPECTED_T = 2` and `runbooks/31-p1-datacube-on-blob.md` listed `timestamps_len == 2`. Calendar windows tile `[startdate, enddate)` in `mosaic_days` steps anchored at startdate, so 2018-07-01..2018-09-01 (62 days) at `mosaic_days=30` = **`ceil(62/30)=3`** windows, **not 2** — verified against `fsd.datacube.ops._calendar_windows` and `api.compute_n_timestamps` (both return 3). The spec's own "T=2 at mosaic_days=30" prose is an arithmetic slip that propagated into the implementer's PROGRESS entry (below) and the script. A perfectly successful demo run would have reported `"pass": false`. **Fixed** the script (`EXPECTED_T=3` + a comment explaining the data-independent count) and the run-book table (`3`, with a note). Count is deterministic regardless of granule dates (the calendar scheme emits every window, empty trailing one as an all-mask slice). **Also patched the two "T=2" references in the spec body (`specs/31`, §The demo slice-rationale + step 2) to "T=3" with a dated correction note (user-approved 2026-07-17); the upload run-book has no T claim to fix.**

**Finding R2 (ACCEPT — no new spec needed) — the Snakemake-sentinel gap (implementer's finding #2 / TODO #41).** The two-build demo workaround **adequately proves spec 31's intent.** Build 1 (`python -m fsd.workflows.task` as a real subprocess, remote `--export-folderpath`) proves the whole compute seam *including the write side* — D1 (`abfss://` artifacts), D2/§4 (GDAL `/vsiadls/` streaming reads), §3 (`fs.save_npy` writes to blob), D4 (`FSSPEC_*` inherited across the subprocess boundary — this *is* the exact CLI the Snakemake runner shells out to). Build 2 (`create_training_data(storage="azure")` through the real Snakemake runner, blob catalog, local export) proves the normal entrypoint reads blob through the child subprocess. The uncovered piece — Snakemake's own `start.txt`/`done.txt` bookkeeping can't live on blob — is a **runner-seam (spec 10 Seam 2) concern, which spec 31 explicitly scopes OUT** (P1 = local runner + blob storage). Making it fail-loud (`RuntimeError`) instead of silent-corrupt + logging TODO #41 (folded into the Batch-runner redesign) is the correct handling. **P1 is genuinely "done" for what it claims; this does not block sign-off.**

**Also spot-checked:** `rio_open` keeps the `rasterio.Env` alive for the dataset lifetime + tears it down on `close()` (correct — GDAL range-reads after open); `configure_storage` sets both `os.environ` and `fsspec.config.conf` (the import-time-vs-runtime hazard); `_check_local_seams(storage_allowed=False)` on `run_inference`/`deploy` keeps inference local. Band list `['B08','SCL']` correct per TODO #35 (SCL mandatory via `build_datacube`'s hardcoded mask→drop; B08 = `config.REFERENCE_BAND`).

## PRIOR (2026-07-17, implementation) — ✅ **spec 31 P1 Azure COMPUTE SEAM IMPLEMENTED (Sonnet@medium)** — 269 passed/3 skipped, ruff clean. **→ Opus@high review** (done above), then the user runs the datacube-on-blob demo.

**Implemented to the pivoted spec** (`specs/31-p1-azure-storage-seam.md` §1–4/§6/§7; **§5 NOT
implemented**, as instructed — download-to-blob stays suspended). Deliverables: `fsd/storage/
azure.py` (new — `to_vsi`, `account_from_url`, `storage_token` off a single module-cached
`DefaultAzureCredential`, `configure_storage`); `fsd/storage/fs.py` re-exports `to_vsi` + gained
`is_local` (see finding below); `fsd/raster/__init__.py` gained `rio_open` (local passthrough;
`abfss://`/`az://` → GDAL `/vsiadls/` under a fresh-token `rasterio.Env` kept alive for the
dataset's lifetime; `mode="w"` on remote raises), swapped into the 3 pixel-read sites
(`raster/images.py`, `raster/cog.py`, `catalog/stac.py`); `api.py`'s `_check_local_seams` gained
`storage_allowed` (default True; `download`/`create_training_data` accept `storage="azure"` +
call the new `configure_storage`; `run_inference`/`deploy` pass `storage_allowed=False` — stay
local, per §Scope); `pyproject.toml` gained `azure-identity` in `[azure]`. 27 new tests
(`tests/test_azure_seam.py` + 2 in `test_workflows.py`), all mutation-tested non-vacuous (mutated
`to_vsi`, `rio_open`, the `os.path.abspath` guard, and the Snakefile guard — each mutation broke
exactly the test meant to catch it). `[dev,azure]` installed into this session's `.venv` so the
adlfs-introspection tests (pinning the installed `adlfs 2026.5.0`/`fsspec 2026.6.0` facts §1
cites) actually run rather than skip; also verified the suite degrades cleanly to **244
passed/4 skipped** with `adlfs`/`azure-identity` **uninstalled** (the `[dev]`-only baseline a
fresh clone would actually have), then reinstalled.

**Also caught by re-tracing the spec's own §Tests wording (not just "does the function exist"):
`storage="local"` was being REJECTED, not treated as a no-op like `None`.** The spec's Tests
section says explicitly `storage="local"`/`None` leaves `FSSPEC_ABFSS_*` unset — my first pass of
`_check_local_seams`/`configure_storage` only special-cased `None`, so `storage="local"` fell
through to "not 'azure' → raise". Fixed (`storage != "local"` added to both guards); a test now
pins it (`storage=object()` still correctly raises, confirmed unaffected).

**⚠️ New finding beyond the spec's own §6 grep head-start (which only checked `os.path.exists`/
`os.makedirs`/bare `open(` and missed both of these):**
1. **`workflows/create_datacube.py`'s `setup()` + its Snakefile both called `os.path.abspath()`
   on `export_folderpath` unconditionally.** `os.path.isabs("abfss://...")` is `False`, so
   `abspath` silently prepended the local cwd and mangled the scheme into `abfss:/` — a real
   **silent corruption bug**, not a style nit, that would have broken the datacube-on-blob demo
   at the first URL it touched. **Fixed** with a new `fsd.storage.fs.is_local(path)` guard at
   both sites (mirrors `sources/cdse._is_local_path`'s existing `fsspec.utils.get_protocol`
   pattern) — zero behavior change for local paths (mutation-tested).
2. **Deeper, NOT fixed: the local Snakemake runner's own `start.txt`/`done.txt` resumability
   sentinels (`Snakefile`'s `touch()`) are plain `os.makedirs`/`open`, not `fsd.storage`-routed.**
   Even with (1) fixed, a remote `export_folderpath` would make Snakemake's own DAG tracking
   silently create a garbage **local** sentinel directory (a valid-if-bizarre local relative path
   like `./abfss:/data@acct.dfs.core.windows.net/.../done.txt`) rather than crash — worse than a
   raise. This is a genuine limitation of the local runner (where does Snakemake's own bookkeeping
   live when artifacts are remote?), not something a "swap bare `rasterio.open`" pass can fix, and
   not in spec 31's stated scope. **Made it fail loud instead of silently corrupting**: the
   Snakefile now raises a clear `RuntimeError` for a remote `export_folderpath`. Logged as
   **TODO #41** (folded into the Batch-runner item — a real fix likely arrives with that redesign).

**Spec-section → implementation trace** (the spec-32 lesson: check the call chain, not just
that functions exist):
- **§1 config seam** → `storage/azure.py::configure_storage` sets both `os.environ` and
  `fsspec.config.conf["abfss"]["anon"]`; `test_configure_storage_azure_string_sets_env_and_conf`
  + the `[dev,azure]`-only adlfs-introspection tests pin the exact library facts (`protocol`
  tuple, `apply_config`, `_get_kwargs_from_urls`) §1 cites, against the *installed* versions, not
  assumed ones.
- **§2 `to_vsi`** → `storage/azure.py::to_vsi`/`account_from_url`; traced against
  `31_upload_slice.py`'s own `_to_vsi` (the pre-existing, real-data-proven reference) —
  same regex shape, same translation. `os.path.join` URL-safety pinned by a direct unit test.
- **§3 adlfs reads/writes** → "no new code" per the spec; confirmed true — `fs.*`'s 94 call
  sites are untouched (`git diff` on `storage/fs.py` shows only the `to_vsi`/`is_local`
  additions, no edits to `_fs_and_path` or any existing function body).
- **§4 `rio_open` + token** → `raster/__init__.py::rio_open`/`storage/azure.py::storage_token`;
  traced call-by-call against the 3 named sites (`raster/images.py` 7 call sites,
  `raster/cog.py` 2, `catalog/stac.py` 2 — every bare `rasterio.open(` in those files, confirmed
  by `grep`, none left). Local-passthrough + remote-Env-with-parsed-account + write-guard each
  have a dedicated mutation-tested unit test.
- **§5** → not implemented, confirmed by `git diff` showing zero changes to `sources/mpc.py`/
  `sources/cdse.py`.
- **§6 audit** → confirmed the reviewer's grep head-start (builder.py/workflows/*.py clean of
  `os.path.exists`/`os.makedirs`/bare `open(`) AND found what it missed (`os.path.abspath`,
  finding 1 above — a different grep pattern than the one the head-start ran). The remaining
  `rasterio.open(` sites (`api.py`'s inference-merge, `model/engine.py`'s inference write) are
  confirmed out-of-P1-scope by tracing `_check_local_seams(..., storage_allowed=False)` on both
  `run_inference` and `deploy`.
- **§7 packaging** → `azure-identity` added to `[azure]`; confirmed importable + functional by
  actually installing `[dev,azure]` into `.venv` and running the full suite against it (not just
  reading the toml).
- **Deliverables' Tests list** → every named test scenario has a corresponding test in
  `tests/test_azure_seam.py`/`test_workflows.py`, cross-checked line-by-line against the spec's
  §Tests bullet list while writing them (not written from memory of the summary above).

**Consequence for the demo run-book** (`runbooks/31-p1-datacube-on-blob.md` +
`runbooks/scripts/31_datacube_on_blob.py`, written, **not yet run** — that's the user's next
step): it proves every claim spec 31's demo cares about via **two builds** instead of the
spec's literal "run one cell through the Snakemake runner writing to blob" — (1) `python -m
fsd.workflows.task` invoked **directly as a real subprocess** with a remote
`export_folderpath` (this *is* the exact CLI unit-of-work Snakemake shells out to, so it still
proves D4's env-inheritance-across-subprocess claim, plus D1/D2/§3/§4 on the write side); (2)
`create_training_data(storage="azure")` through the **real** Snakemake runner, catalog on blob
but the per-cell working directory kept local (proves the same D2/D4 claims through the normal
entrypoint, avoiding finding #2 above). Both builds assert `timestamps` axis length `== 3`
(**corrected from `== 2` by the Opus review — R1 above; `ceil(62/30)=3` for the Jul 1–Sep 1 window**)
— the `mosaic_days=30` calendar-mosaic contract, a criterion that can actually fail, not the
degenerate T=1 runbook 32 v1 tripped on. Band list `['B08','SCL']` per TODO #35 (unchanged).

**Traced against the spec's own de-risking, not re-derived:** the upload run-book (below) already
proved D1 (catalog paths `abfss://`) and D2/§4 (GDAL `/vsiadls/` read of an uploaded COG) on real
blob data before this session started — this implementation's job was the *code*, not
re-verifying those claims, so `rio_open`/`to_vsi`/`storage_token` are a faithful port of
`31_upload_slice.py`'s own `_to_vsi` + `rasterio.Env(...)` block (same shape, same library facts).

**Living docs updated:** `CHANGES.md` (the seam + the two §6 findings), `TODO.md` (#38 ingest
spec, #39 inference/serving-on-blob, #40 ROI-geometry-on-blob, #41 Batch runner + the sentinel
finding), `RECIPES.md` (a `storage="azure"` recipe), `specs/10-storage-and-scale.md` (pointers to
spec 31 realizing Seam 1). Tree left **uncommitted** (commit only when asked).

**→ NEXT:** the user runs `/handoff` → a fresh **Opus@high** session reviews (code-vs-spec +
independent re-verification + a mutation test, per spec 33's review precedent — this session
already ran the mutation tests inline, but an independent pass should re-check them, not take
the report on faith) — **and should look hard at finding #2 above**, since it's a real,
newly-discovered scope question (does the demo's two-build workaround adequately prove the
spec's intent, or does the Snakemake-sentinel gap need its own follow-up spec before P1 is truly
"done"?). Then the user runs `runbooks/31-p1-datacube-on-blob.md` (not yet run) and pastes back
its `_result.json`. Then Opus writes the **ingest/normalization contract spec** (TODO #38 —
§5-ARCHIVE + the `clip(DN-1000,0)` vs `NODATA=0` encoding question + TODO #35 are its inputs).

---

## PRIOR (2026-07-17, later) — 🔄 **ROADMAP PIVOT (user): the DOWNLOADER should normalize, not the datacube builder.** Spec 31's seam survives; its §5 + download-demo are SUSPENDED into a new ingest-contract spec. **Run-book `31-p1-upload-slice.md` is written and ready for the user to run NOW (on wifi).**

**The user's argument, and it is correct** (verified against the code, not accepted on assertion):
`build_datacube`'s chain is
`load_images → _apply_boa_offsets → dst_crs → reference(B08) → resample → stack →
apply_cloud_mask_scl → drop_bands(["SCL"]) → median_mosaic`
— steps 2, 7, 8 are **Sentinel-2 semantics hardcoded into the generic builder**, plus
`REFERENCE_BAND="B08"`. It is an S2 L2A builder wearing a generic name, so every new source must
either cosplay as S2 or force a builder rewrite. **We already logged the consequence without seeing
the pattern: TODO #35 (CHIRPS/ERA5 have no SCL) is this same issue, filed as a one-off.**

**The sharpest version, from our own history:** spec 31's original §5 was `stage-local → convert →
put-to-blob`. The MPC pivot **deleted** it ("MPC is already COG, no conversion needed") — but MPC
didn't remove normalization, it **moved** it from *format* (jp2→COG) to *radiometry* (baseline
offset), and we put the radiometry in the **builder** instead of keeping §5's shape. So §5's shape
was right and deleting it was the error. The user's "intermediate process" = generalize it:
`stage → normalize → put`, per source (CDSE=format, MPC=radiometry, ERA5=netCDF→COG).

**Direction agreed:** ship the seam (architecture-neutral — it's about *where bytes live*, not what
they contain, and the user's own "pull → process → upload to Azure" **requires** it), suspend §5 +
the download demo into a new **ingest/normalization contract spec**, and prove the seam against
**data we upload by hand** rather than a download. Open design questions for that spec, **not
settled**: bake-at-ingest vs a per-source read adapter (baking kills MPC's byte-copy advantage);
the normalized **encoding** (`clip(DN-1000,0,65535)` vs `NODATA=0` **eats real pixels in (0,1000]**
— baking makes that permanent and silent); absorbing TODO #35. Note **normalize-at-ingest forecloses
TODO #31's `/vsicurl` stream arm — but ERA5 forecloses it anyway** (you cannot stream a netCDF as a
COG), which strengthens the case rather than weakening it.

**⚠️ Governance note:** the 2026-07-15 diagnostic found this project keeps working *around* P1. A
well-argued "redesign ingest first" is exactly that pattern's shape. **Guard: the seam still ships.**
This is not the avoidance pattern *provided* the upload + seam land before the ingest spec.

### ⚠️ `satellite_benchmark/` IS GONE — docs were stale, and a session planned against it

Discovered when sizing the upload: **`satellite_benchmark/` does not exist on any mounted volume**
(no external drives). Deleted deliberately for disk pressure (it was 159 GiB; disk is at **96%, 36
GiB free**), and **CLAUDE.md + memory both still described it as the test set** — so this session
built a plan on data that wasn't there. **Now corrected in CLAUDE.md + RECIPES.md.**

**What survives** (`fsd/tests/outputs/`, 83 GB, gitignored):
- **`demo_e2e/imagery/` = the real-data test set now** — Austria e2e: **207 granules, 74 GB**,
  Apr–Sep 2018, 4 MGRS tiles (T33UVP 54 / T33UWP 52 / T33UVQ 52 / T33UWQ 49), B04/B08/B8A/SCL,
  already COG, with `catalog.parquet`.
- `mpc_baseline/imagery/` — 1.7 GB, 9 granules, 33UWP, B04+SCL (runbook 32's over-fetch).
- **Verified geometry:** `s2grid=476da24` is **100% inside T33UWP**; `AT_ROI` straddles all four
  tiles ~evenly (32.7/32.7/32.7/32.6%) → **AT_ROI is now the multi-tile/multi-CRS case**, since
  Ethiopia's `s2grid=165bca4` has **no imagery behind it any more**.
- Per-band totals across 207 granules: B08 34.2 GB (avg 165 MB), B04 31.7 GB, B8A 9.2 GB,
  **SCL 0.54 GB (avg 2.6 MB)**.

### ⚠️ NEW FINDING — our Austria archive is radiometrically WRONG (#10/#30, live)

**Every granule is baseline `N0500`** (05.00 ≥ 04.00 → ESA `BOA_ADD_OFFSET = -1000`), but
`sources/cdse.py:514` writes **`boa_add_offset = 0`** for every CDSE row (TODO #30 open), and this
catalog **predates the column entirely** so `TileCatalog.read` fills 0. **So every datacube ever
built from the Austria archive is ~1000 DN too high** — including the 300-cell e2e crop map. Not a
seam problem (harmless for P1, whose PASS criteria are all seam properties), but it is **correctness
debt #10 sitting live in our own test data**, and it is the single best exhibit for the pivot above:
the downloader didn't normalize, the wrongness got baked into an artifact, and the catalog asserts
it needs no fix.

### → The thing to run NOW (user, on wifi): `runbooks/31-p1-upload-slice.md`

Uploads **T33UWP × Jul–Aug 2018 × [B08, SCL] = 20 granules / 40 files / 2.27 GB** to the `rise`
blob and writes a `catalog.parquet` **on blob with every band path an `abfss://` URL**. Chosen
because 476da24 is 100% inside T33UWP and two months gives a real **T=2** mosaic axis at
`mosaic_days=30` (not a degenerate T=1 — the trap runbook 32 v1 fell into).

- **Needs NO spec-31 code:** `fs.put`/`fs.write_parquet` already route fsspec→adlfs; only
  `azure-identity` + **`FSSPEC_ABFSS_ANON=false`** are required (the account is parsed from the URL).
- Script `runbooks/scripts/31_upload_slice.py` follows the committed-script pattern (no
  `export`+heredoc), is **idempotent/resumable**, prints live MB/s + ETA ([[long-process-progress]]),
  and writes `_result.json` **unconditionally**. **Verified offline:** ruff clean; `--dry-run`
  reports exactly 20/40/2.27 GB; the missing-`FSSPEC_ABFSS_ANON` guard and the bad-URL guard both
  fire and still write `_result.json`; `_to_vsi` translates correctly.
- **It also proves spec 31 D2/§4 before any code is written for it** — reads our own uploaded COG
  through `/vsiadls/` + a fresh `AZURE_STORAGE_ACCESS_TOKEN` (`gdal_vsiadls_read_ok` +
  `gdal_sample_nonzero` are the load-bearing PASS keys).
- **A seam finding the spec got wrong:** the catalog column is **`local_folderpath`** (name becomes a
  lie on blob) and `builder.py:72` joins it with `files` to make each band path. **Spec 31 §2 claims a
  catalog `filepath` column — there is none**; `filepath` is derived in `flatten_catalog`. The upload
  script rewrites `local_folderpath` → the blob folder and narrows `files` to `B08.tif,SCL.tif` so the
  blob catalog is self-consistent.

**✅ UPLOAD RAN GREEN (user, 2026-07-17): `"pass": true`.** 20 granules / 40 files / **2.27 GB** on
`rise` at `data@…/fsd-tests/p1-demo/imagery/`, ~13.4 MB/s over VPN (170 s). All 20 catalog rows on
blob carry `abfss://` paths (`every_catalog_path_is_abfss: true`); **GDAL read our uploaded COG via
`/vsiadls/`** and got real uint16 256×256 pixels (`gdal_vsiadls_read_ok` + `gdal_sample_nonzero`).
So **D1 + D2/§4 — the spec's riskiest claims — are proven on real data before any seam code exists.**
(One untested path: `files_skipped_already_present: 0`, so idempotent-resume never fired in the wild.)

**✅ Spec 31 rewritten end-to-end for the pivot (same session).** The spec was signed off with §5 =
MPC-copy-to-blob + a download demo; the pivot suspends both. Now consistent throughout: a **⚠️ pivot
banner** at the top of the status block (download-to-blob OUT → ingest spec; this is a *compute-seam*
spec); **D3 marked obsolete**; **§5 SUSPENDED** with the MPC-copy design preserved as **§5-ARCHIVE**
for the ingest spec; **Scope, Tests, the demo, and Deliverables** all rewritten to "build over
hand-staged blob data, no download" (`mpc.py`/`cdse.py` **not touched**, both guards stay); the demo
gained an explicit **D4 subprocess-safety** step (run one cell through the Snakemake runner). Also
fixed a real spec error the upload surfaced: **there is no catalog `filepath` column** — it's
`local_folderpath` (joined at `builder.py:72`); `filepath` is only `flatten_catalog`'s transient
output. Suite still 242/3, ruff clean.

**→ NEXT:** **Sonnet@medium implements the spec-31 compute seam** (§1 config, §2 `to_vsi`, §3 adlfs,
§4 `rio_open`/`/vsiadls/`, §6 audit, §7 packaging — **not** §5) against the uploaded blob data → then
the user runs the datacube-on-blob demo run-book → then **Opus writes the ingest/normalization
contract spec** (§5-ARCHIVE + the encoding/`(0,1000]`-clip question + TODO #35 are its inputs).
Nothing committed (no ask).

---

## PRIOR (2026-07-17) — ✅ **spec 31 (P1 Azure storage seam) REVIEWED, REWRITTEN, SIGNED OFF** (Opus@high, independent of the draft's author) → NEXT = **Sonnet@medium implements**. ⚠️ **Also found: concrete `rise` values leaked into the PUBLIC repo — user decision needed.**

**Sign-off is real this time and independently checked:** the draft was Opus (`030f6ac`, trailer
verified `Claude Opus 4.8` — not a repeat of spec 33's F1); this review was a **separate** Opus@high
session that did not write it. Draft → **revised** → signed off.

**The review caught the spec-32 failure mode recurring verbatim: the demo was structurally impossible
against our own code.** Spec 31's exit demo downloads to blob, but **both** sources hard-refuse a
remote dst today — `mpc.py:294` raises *"MPC source is local-only in Phase 1"*, and `cdse.py:645`
raises on remote + `cog=True`. Meanwhile the one section that would have fixed it (**§5**) had been
marked **DELETED** by the 2026-07-16 retarget banner and **never rewritten** ("a future session's
job"). So the spec deleted its own download-to-blob design and still depended on it — and its Scope /
Tests / Demo / Deliverables all still encoded the deleted CDSE design. Handed to Sonnet (which
implements to the letter, as 32 and 33 both did) it would have implemented the deleted §5.

**Two user decisions taken (2026-07-17), both as recommended:**
1. **Demo copies MPC → `rise` blob, then streams back via `/vsiadls/`.** Streaming MPC in place via
   `/vsicurl` would be smaller but would **never exercise `/vsiadls/`** — i.e. would not test D2/§4
   at all. TODO #31's *production* stream-vs-copy question stays **"measure, don't argue"**; this
   just builds the copy arm so the later measurement has a comparison.
2. **CDSE download-to-blob dropped from P1** → new TODO (next to #30). MPC is already-COG, so the
   jp2→COG dance the MPC pivot removed is not reimported. `sources/cdse.py` is not to be touched.

**What the rewrite changed:** §5 is now **"MPC copy straight to blob — pure byte-copy"**, written
against the actual guard it must lift (delete `mpc.py:294`; everything else in that path — `fs.makedirs`,
`_select_item_files`'s `os.path.join`, `_transfer_one`'s already-cross-backend, `.part`-atomic
`fs.transfer` — is already URL-safe, traced claim by claim). §1/§3's "registry + credential object"
language removed. **Demo band list pinned to `['B08','SCL']`** — TODO #35 (hardcoded SCL mask/drop)
is still open and `config.REFERENCE_BAND == 'B08'`, so any other list reproduces runbook 32 v1's
crash. Byte budget stated honestly (~0.5–1 GB, full-tile COGs) rather than v1's false "a few MB".

**All 5 open items RESOLVED at sign-off** — none left for the implementer. The two fsspec ones were
closed by **direct introspection of the installed libraries** (`fsspec 2026.6.0`, `adlfs 2026.5.0`),
now a "Verified against the installed libraries" section in the spec with per-fact credit:
- **`AzureBlobFileSystem.protocol == ('abfs','az','abfss')`** and `apply_config` keys on the **class's**
  protocol tuple, not the URL scheme → **set exactly one key, `FSSPEC_ABFSS_ANON=false`**. Setting
  several is a *hazard* (last proto silently wins), not thoroughness.
- **`_get_kwargs_from_urls('abfss://data@acct.dfs.core.windows.net/…') == {'account_name': 'acct'}`**
  → **D1 confirmed**; the account rides in the URL and beats conf, so `FSSPEC_ABFSS_ACCOUNT_NAME` is
  redundant. **D1–D4 all survive independent review** (D2's token handling and D3's "GDAL never
  writes `/vsiadls/`" both hold — with MPC, GDAL is never on the write path at all).
- Scratch-dir question **moot** (no staging without conversion); atomicity question **resolved** by
  `fs.transfer` already doing `.part`+rename (the residual — is adlfs's `mv` atomic on HNS — is a
  runbook *observation*, step 2's "no `.part` leftovers").

### ⚠️ LEAK — concrete `rise` values are in the PUBLIC repo (`git@github.com:nikhilsrajan/fsd.git`)

Found while auditing spec 31 for placeholder discipline. **The handoff's claim that spec 31 was
verified clean was wrong** — and `PROGRESS.md` was worse:
- `specs/31…md` §1 named the **storage account**. → **scrubbed** to a pointer.
- `PROGRESS.md` (this file, 2026-07-15 entry) named the **storage account, the user's identity
  (`…@raapid.org`), the subscription name AND its GUID, and the resource group**. → **scrubbed** to
  pointers at `../P1_AZURE_SETUP.md`.
- **Introduced by `030f6ac`, which is an ancestor of `origin/main` → already on GitHub.** Scrubbing
  the working copy does **not** remove it from history; `git show 030f6ac:PROGRESS.md` still has it.

**Severity, stated honestly: no credential leaked.** Account keys are disabled (Entra-only), storage
is RBAC-gated and VPN/firewalled, and subscription/RG/account names are identifiers, not secrets. The
most sensitive item is the **identity email** — a valid Entra username is a phishing/spray target. So
this is a genuine **hard-constraint violation** to decide on deliberately, not an emergency.
**Open for the user:** leave history as-is (scrub going forward), or rewrite history / rotate the repo.
Claude did not touch git history — that is destructive and the repo is public/shared.

**Also corrected:** the handoff said "3 unpushed commits, nothing has been pushed." **False** —
`origin/main` is at `14781c1`; all three spec-33 commits are pushed.

**Nothing committed** (no ask). Working tree still carries the deliberate `TODO.md` #26-reflow WIP +
the two notebooks, untouched.

**→ NEXT:** `/handoff` → **Sonnet@medium** implements `specs/31-p1-azure-storage-seam.md` against the
signed-off text (§Deliverables is the checklist; the runbook must follow the **committed-script**
pattern of `runbooks/scripts/33_probe_dedup.py`, not v1's `export`+heredoc that silently produced
nothing). Then Opus review, then the **user runs** `runbooks/31-p1-datacube-on-blob.md` (VPN on,
~0.5–1 GB). **Decide the leak question** at some point before the next push.

---

## PRIOR (2026-07-16) — ✅ spec 32 DONE: runbook v2 FULLY VALIDATED on real MPC data. **Correctness debt #10 is fixed for MPC and proven end to end.**

**All three steps PASS.** Verified independently from the artifacts on disk (not from the `pass`
flag — v1 proved that flag could lie):

- **The cutover boundary was hit exactly.** Real items: `20220107` baseline **`03.00`** → offset
  `0`; `20220127` baseline **`04.00`** → offset `−1000`. `04.00` is the *first* offset baseline, so
  this exercises `_baseline_tuple(...) >= (4, 0)` **precisely on the boundary** — `>` instead of
  `>=` would have silently returned 0. Real data landed on the one value that tells them apart.
- **Step 3 A/B vs unharmonized control** (cube `(2, 550, 606, 1)`): `pre_identical_to_control =
  true`; post slice equals the control **exactly −1000** across **202 831** non-clipping pixels
  (`np.array_equal`, no tolerance); **zero** pixels in `(0, 1000]` → nothing clipped → mean delta
  exactly **1000.0**.
- **The science:** pre-vs-post gap **2187.1 DN** unharmonized → **1187.1 DN** harmonized. The fix
  removed exactly the 1000 DN artifact; the 1187 remainder is real January scene change. That *is*
  #10: a mosaic spanning both dates would have blended 400 with 2587 where the truth is 400/1587.
- **Both open items resolved:** `s2:processing_baseline` + `s2:mgrs_tile` confirmed live;
  `storage.transfer` streamed signed MPC HTTPS cleanly — **no `aiohttp` fallback needed**.

**Getting here took a runbook v2** — v1's steps 2–3 were defective, and the fault was **spec 32's
Tests section (mine), not the implementation**: it prescribed "band B04 only" *and* "build a
2-timestamp datacube", which are mutually impossible since `build_datacube` hardcodes
`apply_cloud_mask_scl` → `drop_bands(["SCL"])`. That survived sign-off, cross-validation,
implementation **and the Opus code review** (which checked code-vs-spec but never traced the runbook
against the builder's op chain — the guard test's own B04+SCL was the tell). **Lesson: cross-
validating *external* facts doesn't catch inconsistency with our *own* code.** v1's other three
defects: it over-fetched **9 items / 1.7 GB** (downloaded the whole range *between* pre and post);
claimed "a few MB / no full-tile download" when **MPC assets are full-tile COGs (one B04 = 96–272
MB)**; and had PASS criteria that couldn't fail (`pass` only checked `failed_count`;
`mosaic_days=120` over 120 days gives **T=1**, not the 2 it compared). v2 fixed all four and
replaced the vague check with the A/B above.

**Follow-ons logged (none blocking):**
- **#34 — MPC serves duplicate reprocessed acquisitions.** `20220301T100029` came back **twice**
  (processed `20220303` *and* reprocessed `20240604`) — same sensing time + tile, different item
  ids, so the id-uniqueness check passes. Both downloaded (224+272 MB), both catalogued;
  `_stack_datacube` merges two copies of one scene with an arbitrary tie-break. **Not
  radiometrically wrong** — spec 32 offsets each processing on its own baseline before the merge
  (the design earning its keep) — but wasted bytes + a silent arbitrary pick.
- **#35 — `build_datacube` requires SCL even when masking isn't wanted** (root of the v1 crash).
  Own spec needed: it changes a core contract, and TODO #11's non-optical sources (CHIRPS/ERA5) have
  **no SCL at all**, so they're blocked on it.
- **#36 — CDSE-vs-MPC speed: PARKED by the user.** Recorded with confounds so they aren't
  re-derived: VPN × 9-items-not-2 × a duplicate × **full-tile copy for a 0.18 % ROI** (21.5 km² read
  from a 12 100 km² tile). TODO #24 already establishes the local result is link-bound and **doesn't
  generalize to Azure**; the dominant lever is plausibly windowed `/vsicurl` vs full-tile copy
  (TODO #31), not the source choice.
- **Pin `planetary-computer`** — the spec's open item; the resolved version is now observable from
  the runbook's install.

**All committed + pushed** — `main` @ `8d91510`, in sync with `origin`. Spec 32's last open item
closed too: **`planetary-computer>=1,<2`** pinned (the runbook's install resolved **1.0.0**, so the
bound came from a verified fact, not a guess; verified it accepts 1.0.0/1.x and rejects 0.9.0/2.0.0).
Uncommitted WIP, deliberately untouched: the `TODO.md` item-#26 reflow + the two notebooks.

---

## PRIOR (2026-07-17) — ✅ spec 33 (MPC reprocessing dedup, TODO #34) CLOSED: implemented (Sonnet@medium) + Opus@high review PASS + **runbook 33 VALIDATED on live MPC data** (`"pass": true`, duplicate still live upstream so the test was real). NEXT = spec 31 (P1 Azure seam)

**Implemented to the letter of `specs/33-mpc-reprocessing-dedup.md`** — no redesign, no forks
reopened. `sources/mpc.py`: new `_generation_time(item) -> str` (reads `s2:generation_time`,
raises with the item id + property name if missing) and `_dedupe_reprocessed_items(items) -> list`
(groups by `(item.datetime, _mgrs_tile_from_item(item))`, `max` by `_generation_time` breaks ties,
singleton groups pass through untouched). Wired in as `items = _dedupe_reprocessed_items(items)`
immediately after each of the two existing `_search_items(...)` calls, in both `query_catalog`
(before `_items_to_gdf`) and `download` (before `_finalize_catalog_gdf`) — so a duplicate is never
even queued for transfer, which is the actual byte-saving TODO #34 asked for.

**Tests** — 8 new cases in `tests/test_mpc.py` (existing `_FakeItem`/`_fake_item` fixtures
extended with an optional `generation_time` kwarg, no new fixture style): no-duplicates no-op,
duplicate-pair latest-wins (+ order-independence), three-way group, missing-`s2:generation_time`
on a duplicate group raises, singleton missing the property does *not* raise, key falls back to
`item.id` when `s2:mgrs_tile` is absent, and two integration tests (`query_catalog` and `download`)
using the real spec-32 runbook duplicate pair (`S2B_MSIL2A_20220301T100029_R122_T33UWP_...`,
fabricated `s2:generation_time`s matching the real `20220303`/`20240604` ordering) plus a distinct
control item — asserting exactly 2 rows survive (never 3) and the loser's asset href is never
passed to `fs.transfer`. Followed the process guard from the handoff: duplicate-group fake items
share one identical `datetime` object per group (not just close), so the dedup path is genuinely
exercised, not silently skipped by a spurious microsecond mismatch.

**Verification:** `pytest -q` → **242 passed, 3 skipped** (was 234 passed/3 skipped before this
spec; +8 new tests, zero regressions). `ruff check src/ tests/` → clean. No runbook needed (pure
in-memory filter, no new network behavior) — matches the spec's own "why safe without a runbook"
note.

**Untouched, as the spec required:** `pyproject.toml`, `catalog.COLUMNS` (no new `mgrs_tile`
column), `datacube/builder.py`, `sources/cdse.py`. `_items_to_gdf`/`_finalize_catalog_gdf` unaware
of the dedup step — they simply never see a loser item now.

**Living docs updated:** `CHANGES.md` (new entry), `TODO.md` #34 → DONE (pointing at the spec + the
8-test count), this `PROGRESS.md` entry. Work done in worktree `spec33-docs-update`; **not
committed** (user asked to implement, not to commit — per CLAUDE.md's "commit only when asked").

## ✅ Opus@high REVIEW (2026-07-16): **PASS** — merged to `main`, 4 findings (none blocking)

**Reviewed** code-vs-spec + independent correctness, per spec 24 D5. **Verdict: PASS.** The
implementation matches the spec's pseudocode essentially verbatim; scope discipline is clean
(`pyproject.toml`, `catalog/`, `datacube/builder.py`, `sources/cdse.py` all untouched, verified by
diff); dedup provably runs before `_items_to_gdf`/`_finalize_catalog_gdf` at **both** call sites.

**Verified independently, not taken on report:** `pytest -q` → **242 passed / 3 skipped** and
`ruff` clean, reproduced from the worktree with `PYTHONPATH=src` (confirmed the loaded `mpc.py` was
the worktree's, not `main`'s — the trap noted in the spec-32 review). **Mutation test:** disabling
both dedup call sites fails exactly the two integration tests (`assert 3 == 2`) → the guard tests
are non-vacuous, not merely passing.

**Findings:**
- **F1 (fixed)** — `PROGRESS.md` claimed this spec was "SIGNED OFF (Opus@high)"; the commit trailer
  says **Sonnet 5**. Sonnet wrote, self-signed-off, and implemented its own spec. Corrected in the
  entry below; this review is the compensating control.
- **F2 (fixed)** — the dedup key silently dropped `relative_orbit`, which the spec's **own**
  research doc recommends. The narrowing is correct (orbit is determined by sensing instant + tile)
  but was undocumented; now recorded in spec 33 Fork 2.
- **F3 (open, non-blocking)** — the tie-break compares `s2:generation_time` as **strings**
  (lexicographic). Safe for the observed uniform format (`2024-06-08T13:16:56.674469Z`), would
  misorder if MPC ever mixed `+00:00`/`Z` or precision. `runbooks/33-mpc-dedup-live.md` now checks
  format uniformity empirically on live items; parse-to-datetime is the cheap hardening if it ever
  varies.
- **F4 (open, non-blocking, unreachable today)** — a `None` `item.datetime` would collapse every
  such item on one tile into a single group and dedup them wrongly. MPC S2 L2A always populates
  `datetime`, so it is not reachable; noted rather than guarded.

**New: `runbooks/33-mpc-dedup-live.md`** — the spec said "no runbook needed" and is right that
pytest covers the *logic*, but pytest **cannot** prove `s2:generation_time` is populated on the
**live** duplicate pair, because the fake items only have it since we put it there. The runbook
closes that gap: **discovery-only, zero imagery bytes**, seconds. Validated offline before handoff —
it **passes** against the fixed code (3 raw → 2 catalog, loser gone) and **fails** against
simulated pre-fix code (`loser_present=True`), so it is non-vacuous. Reports `inconclusive` (not a
false pass) if MPC has since cleaned the duplicate upstream.

**Merged to `main`** at the review (was uncommitted in worktree `spec33-docs-update`): the 4 code/doc
files applied as a 3-way patch; `TODO.md` #34 swapped by hand so `main`'s uncommitted item-#26
reflow WIP survived. Runbook rewritten to run from `main` + the normal `.venv` (no `PYTHONPATH`).
**Still uncommitted** — awaiting the user's ask.

## ✅ runbook 33 VALIDATED on live MPC data (2026-07-17) — dedup proven end to end

**`runbooks/33-mpc-dedup-live.md` ran green: `"pass": true`, every criterion met.** Discovery-only,
zero imagery bytes. The result is **not** the `inconclusive` fallback — **the duplicate is still
live upstream**, so this genuinely exercised the fix rather than passing vacuously:

- **`duplicate_groups_upstream: 1`** — MPC still serves both `..._20220303T182540` (original) and
  `..._20240604T180322` (2024 reprocessing) for sensing instant `2022-03-01 10:00:29.024+00:00` on
  tile `33UWP`. (So MPC's cleanup per discussion #275 did **not** remove this pair — the spec's
  premise still holds on live data today.)
- **`raw_item_count: 2` → `catalog_row_count: 1`** — dedup collapsed the pair; `catalog_ids` equals
  `independently_expected_ids` (recomputed by the probe, not taken from fsd's own answer).
  `known_winner_present: true`, `known_loser_present: false` — the 2024 reprocessing won, the
  original's ~224 MB is never queued.
- **Finding F3 empirically resolved (for this data):** `generation_time_format_shapes` = exactly
  one shape, `NNNN-NN-NNTNN:NN:NN.NNNNNNZ`. Live values are uniform RFC-3339 with microseconds +
  `Z`, so the string tie-break is sound — and it's a real ordering test, since the winner's
  `.000000Z` vs the loser's `.834434Z` differ in precision-of-content while sharing a format.
  Caveat: n=2. F3 stays noted (not reopened) as "verified on the only live pair we have".
- **Guard confirmed:** `mpc_module_loaded_from` = `.../fsd/src/fsd/sources/mpc.py` — `main`'s code,
  not a worktree's.

**New real-data fact (no action needed, recorded so nobody re-derives it):** live MPC's
`s2:mgrs_tile` is **`"33UWP"` — no `T` prefix** (the `T` lives only in the item id). This is
**consistent with fsd's own convention**: both `catalog.stac._parse_mgrs` and
`datacube.builder._mgrs_tile` also yield `33UWP` (verified directly). So there is **no mismatch and
no latent bug** — the three representations agree. The one wart is that `tests/test_mpc.py`'s
fixtures use the *unrealistic* `"T33UWP"`; harmless (dedup only needs the key self-consistent within
a run, and the tests still exercise the real path), but a reader could wrongly infer live MPC
returns a `T` prefix. Fixture-realism nit only — **not** a defect, logged here rather than as a TODO.

**→ NEXT:** **spec 31** (`specs/31-p1-azure-storage-seam.md`, DRAFT awaiting sign-off) — the P1
Azure storage seam. This is the critical path the 2026-07-15 diagnostic named (the project keeps
finishing work *around* P1); spec 33 was its last legitimate prerequisite, and it is now closed.
**Opus@high reviews/signs off spec 31 → then Sonnet@medium implements.** Given F1, verify the model
from the commit trailer, not the heading.

---

## PRIOR (2026-07-16) — ✅ spec 33 (MPC reprocessing dedup, TODO #34) SIGNED OFF (⚠️ **Sonnet@medium, not Opus — process deviation, see below**) — implemented same-day

> ⚠️ **CORRECTED 2026-07-16 at the Opus review (finding F1).** This entry originally read
> "SIGNED OFF (Opus@high)". **That was false.** Commit `e5d3e6c`'s trailer is
> `Co-Authored-By: Claude Sonnet 5` — a **Sonnet** session ran the interview → grill →
> cross-validate → spec → sign-off flow that spec 24 D3/D5 reserves for Opus, recorded the
> sign-off as Opus@high, and then implemented against its own spec. The prior handoff
> (`9ec060d`) was explicit: *"Opus@high writes spec 33 → sign-off → Sonnet@medium implements"*.
> Every other spec sign-off on record (`030f6ac`, `50749e8`, `6e1e9f0`, `4a81cd9`, `96d02b0`) is
> genuinely Opus; this is the one deviation.
> **Likely cause:** the model switch at `/handoff` (D6) is a manual step with nothing enforcing
> it — a session started at `/model sonnet` picks up the handoff doc and proceeds regardless.
> **Compensating control:** a full Opus@high review was run after the fact (see the LATEST entry) —
> code-vs-spec, independent re-verification, and a mutation test. **Verdict: PASS**, so the
> *outcome* was sound; the *process* was not, and the record now says so.
> **Lesson (new, alongside spec 32's "cross-validating external facts doesn't catch inconsistency
> with our own code"):** a self-signed-off spec has no independent check — the session that owns
> the design blind spots is the one grading them. Neither the spec text nor `PROGRESS.md` can be
> trusted to report which model actually did the work; **the commit trailer is the only ground
> truth.** Check it, don't read the heading.

**`specs/33-mpc-reprocessing-dedup.md` SIGNED OFF.** Interview → grill → cross-validate (standing
practice) → spec, per the handoff `/tmp/fsd-handoff-spec33-mpc-dedup.md`. **All 5 design forks
resolved, no open items blocked sign-off:**

1. **Where dedup lives → MPC-only (`sources/mpc.py`), not shared `cdse._finalize_catalog_gdf`.**
   Decided by researching Fork 4 first: CDSE has its **own**, structurally different multi-item
   issue (ESA-confirmed datastrip-split near-duplicates that can carry legitimate different pixel
   coverage/border artefacts) — a shared dedup rule risked silently dropping real CDSE data, so
   CDSE stays untouched.
2. **Key → in-memory `(item.datetime, mgrs_tile)`, no new catalog column.** Dedup runs on the raw
   STAC item list before any catalog row exists (right after `_search_items`, before
   `_items_to_gdf`), so `_mgrs_tile_from_item` (spec-32 dead code) gets its first real caller
   in-memory only — no `catalog.COLUMNS` change, no back-compat migration.
3. **Winner → latest `s2:generation_time`, NOT the item id's trailing field.** Reverses the
   handoff's suspected id-string-parsing approach: a live MPC STAC query confirmed
   `s2:generation_time` is a real, populated RFC-3339 property, while ESA's own SentiWiki
   naming-convention page explicitly declines to guarantee the id's trailing "Product
   Discriminator" field is monotonically increasing.
4. **Does CDSE have the same duplication? Yes, but differently** (see #1) — CDSE's own mechanism
   is catalogue-level deletion of old-baseline products, not a queryable "pick latest" property;
   confirms the two providers' problems aren't the same fix.
5. **Applied at discovery time** (both `query_catalog` and `download`, right after
   `_search_items`) — the loser is never even queued for transfer, which is the actual byte
   savings TODO #34 asked for. Existing test artifacts with a stale duplicate (e.g.
   `tests/outputs/mpc_baseline/catalog.parquet`) are **not migrated** — discovery-time fix only,
   explicitly out of scope.

**Cross-validation** — full detail + per-source credit in the spec's own §"Best-practice
alignment" + supporting file `specs/research-s2-reprocessing-dedup.md`: live MPC STAC item query,
`stac-extensions/sentinel-2` + `stac-extensions/processing`, the CDSE community forum
duplicate-products thread, CDSE's old-baseline-deletion notices, SentiWiki's S2 Products page,
`stactools-packages/sentinel2` issues #130/#5, and `microsoft/PlanetaryComputer` discussion #275.

**No runbook needed** — pure in-memory filter over STAC search results, fully synthetic-testable
(duck-typed fake items matching `tests/test_mpc.py`'s existing fixtures); no new network behavior.

**→ NEXT:** hand to a **Sonnet@medium** session to implement `specs/33-mpc-reprocessing-dedup.md`
(new `_generation_time` + `_dedupe_reprocessed_items` in `sources/mpc.py`, one call-site edit each
in `query_catalog`/`download`, tests per its §Tests, living-doc updates per its §Deliverables).
Then Opus review, then **spec 31** (Phase 2, Azure at scale) — the task after this one (unchanged
from the prior entry below). `TODO.md` #34 updated to point at the signed-off spec; nothing
committed this session (user asked only for the TODO/PROGRESS update, not a commit — per
CLAUDE.md's "commit only when asked").

---

## PRIOR (2026-07-16) — spec 33 scoped: TODO #34 (MPC reprocessing dedup), THEN spec 31 (Phase 2 Azure)

**Then spec 31 (Phase 2, Azure at scale) — the north star.** Status: **DRAFT, awaiting sign-off**,
already **de-risked by a green access probe** (`runbooks/31-p1-access-probe.md`, 2026-07-15:
`az login` done, personal identity has **Storage Blob Data Contributor**, adlfs
`DefaultAzureCredential` round-trips, GDAL 3.10.3 opens via `/vsiadls/` **and** `/vsiaz/`).
⚠️ **The 2026-07-15 diagnostic's "P1 blocked on user" is STALE — that blocker cleared.** The rewrite
must: (a) rewrite **§5**, flagged deleted/retargeted when MPC removed the `jp2→COG` conversion
problem but never actually rewritten; (b) **decide TODO #31's stream-in-place (`/vsicurl`) vs
copy-to-`rise` fork** — spec 32 explicitly deferred it to *this* Phase-1→2 boundary, which is now;
(c) note that **TODO #36** (CDSE-vs-MPC speed) becomes answerable here, since a local measurement is
link-bound and doesn't generalize (TODO #24's precedent). The **rslearn Plan B/C call does not gate
this** — the comparison concluded **scale-out is ours regardless** ([[fsd-rslearn-comparison]]).
Concrete `rise` names/IDs live **only** in `../P1_AZURE_SETUP.md` + `../AZURE_INFRA_PRIVATE.md`
(workspace root, never in the public repo).

**Parked, named so they don't get re-derived:** #35 (optional SCL — own spec; gates #11's SCL-less
CHIRPS/ERA5), #36 (source speed — parked by the user, confounds recorded), rslearn Plan B/C.

### Previous entry (spec 32 runbook v1 run — step 3 crash + diagnosis)

**The fix works on real MPC data.** Step 2's live catalog is the proof of D3: `20220107` (baseline
<04.00) → `boa_add_offset = 0`; `20220127`, two days after the cutover → `−1000`. The spec's two
flagged open items are also confirmed live: `s2:processing_baseline` and `s2:mgrs_tile` exist as
assumed, and `storage.transfer` streamed signed MPC HTTPS fine (no `aiohttp` fallback needed).

**Step 3 crashed — and the fault is spec 32's, not the implementation's.** `ValueError: SCL band
not present in datacube`. `build_datacube` hardcodes `apply_cloud_mask_scl` → `drop_bands(["SCL"])`,
so SCL is structurally required, but the spec's Tests section prescribed **"band B04 only"** *and*
"build a 2-timestamp datacube" — mutually impossible. That inconsistency survived sign-off,
cross-validation, implementation, **and the Opus code review** (which checked code-vs-spec but never
traced the runbook against `build_datacube`'s op chain — the reviewed guard test uses B04+SCL, which
was the tell). The implementer followed the spec faithfully. **No implementation defect was found by
the real run; the code verdict stands.**

**Runbook v2 issued** (`runbooks/32-mpc-baseline.md`) — v1 had four defects, all now fixed:
- **B04-only → `['B04','SCL']`.** Bonus: the band exemption goes from "moot" (the spec's word) to
  **live** — SCL must return `0` while B04 returns `−1000` on real data.
- **Over-fetch.** v1 downloaded the whole date range *between* `pre` and `post` → **9 items /
  1.7 GB**, not the promised 2. v2 uses two tight ±1 h windows.
- **"a few MB / no full-tile download" was false.** MPC assets are **full-tile (~110 km) COGs** —
  a single B04 measured **96–272 MB**. Prerequisites now state ~320 MB honestly.
- **PASS criteria that couldn't fail.** Step 2's `pass` only checked `failed_count == 0` (never the
  offsets); step 3's was a "plausible range" judgement, and its `mosaic_days=120` over a 120-day
  window gives **T=1**, not the "2 timestamps" it compared. v2 asserts the offsets explicitly and
  replaces the vague check with an **A/B against an unharmonized control** (same cube built twice,
  offsets forced to 0 in the control): post-baseline slice must equal control **exactly −1000** on
  non-clipping pixels; pre-baseline slice **bit-identical**. Writes `_result_step3.json`.

**Three findings logged as TODOs:**
- **#34 — MPC serves duplicate reprocessed acquisitions.** `20220301T100029` came back **twice**
  (processed `20220303` *and* reprocessed `20240604`) — same sensing time + MGRS tile, different
  item ids, so `_finalize_catalog_gdf`'s id-uniqueness check passes. Both downloaded (224+272 MB),
  both catalogued; `_stack_datacube` then merges two copies of one scene with an arbitrary
  tie-break. **Not radiometrically wrong** — spec 32 offsets each processing on its own baseline
  before the merge (the design earning its keep) — but wasted bytes + a silent arbitrary pick.
- **#35 — `build_datacube` requires SCL even when masking isn't wanted** (the root of the step-3
  crash). Deferred to its own spec: it changes a core contract, and TODO #11's non-optical sources
  (CHIRPS/ERA5) have **no SCL at all**, so they're blocked on it.
- **#36 — CDSE-vs-MPC speed comparison: PARKED by the user** (nothing to do now). Recorded with its
  confounds so they aren't re-derived: the "MPC is slow" reading is VPN × 9-items-not-2 × a
  duplicate × **full-tile copy for a 0.18 % ROI** (21.5 km² read out of a 12 100 km² tile). TODO #24
  already records that the local CDSE result was **link-bound and does not generalize to Azure** —
  so the honest version of this benchmark is an Azure-side one, and the dominant lever is plausibly
  windowed `/vsicurl` vs full-tile copy (TODO #31), not the source choice.

**Uncommitted** (no commit requested): runbook v2, spec 32 §Tests correction + banner, TODO #34–36,
this entry.

### Previous entry (spec 32 code review — PASS, merged + pushed)

**Review verdict: PASS — no code changes required.** Reviewed the spec-32 implementation
(`1cf1568` + `0da4d15`) against the signed-off spec, then **fast-forward merged
`spec32-mpc-implement` → `main`** and pushed to `origin/main`; the worktree was removed.

- **Independently re-verified** the implementer's claims (not taken on trust): `pytest -q` **234
  passed, 3 skipped**; `ruff check src/ tests/` clean. (Note for future sessions: the `.venv`
  editable install points at **main's** `src/`, so running a worktree's tests needs
  `PYTHONPATH=src` from inside the worktree — otherwise it silently imports the wrong `fsd`.)
- **The #10 guard test is real, not vacuous** — confirmed by mutation: deleting the
  `_apply_boa_offsets` call makes `test_build_datacube_harmonizes_boa_offset_before_median_mosaic`
  fail (restored immediately). Offset-after-median would give `clip(median(200,1200)−1000)=0` ≠ 200.
- **Confirmed against the spec:** D1/D2 ordering (offset applied right after `load_images`, before
  `dst_crs`/reference/resample/`median_mosaic`); D3 keys on `s2:processing_baseline`, not
  `item.datetime`, and **raises** on a missing baseline; `_is_reflectance` matches `^B\d`/`B8A` and
  exempts SCL/AOT/WVP/visual; catalog back-compat fills 0 on both `read` and `append`;
  `api.download`'s `creds` relaxation stays positionally back-compatible and still requires creds
  for `source="cdse"`; no out-of-scope creep (no Azure code, CDSE offset retrofit correctly left
  as TODO #30).
- **A subtle trap the implementation avoided:** rows dropped by `_load_images` get
  `image_index = -1` and are filtered out *before* `_apply_boa_offsets` iterates, so an unreadable
  image can never cause a `data_profile_list[-1]` mis-write.
- **Three minor, non-blocking notes** (logged in spec 32's banner, not fixed — none affect
  correctness): dead `mpc._mgrs_tile_from_item`; a CDSE-worded error message reachable from the MPC
  path via the reused `_finalize_catalog_gdf`; and **`planetary-computer` left unpinned** though the
  spec's open items asked to pin it — **pin it after the runbook's step-1 install reports the
  resolved version** (the one small follow-up worth doing).
- **Merge hygiene:** main's unrelated WIP (the `TODO.md` reflow + the two notebooks) was stashed
  before the merge and popped after — `TODO.md` auto-merged with **no conflict**, and both sides
  survived (reflow of item #26 intact; committed #30–33 + the #10 update present). The reflow and
  notebooks remain **uncommitted WIP**, per CLAUDE.md.

### Previous entry (Sonnet@medium implementation of spec 32)

**Implemented `specs/32-mpc-source-baseline-harmonization.md`** (signed off earlier the same day)
against baseline `030f6ac` on `main`, in an isolated worktree
(`.claude/worktrees/spec32-mpc-implement`, branch `spec32-mpc-implement`). To the letter, no
redesign. `pytest -q` **234 passed, 3 skipped**, `ruff check src/ tests/` clean.

- **New source `sources/mpc.py`** — MPC S2 L2A discovery (`pystac_client` + `planetary_computer`
  sign modifier, anonymous by default) and a **pure COG byte-copy** download (no `jp2->COG`
  conversion, no convert-process-pool — MPC assets are already COG). Reuses CDSE's generic
  `_finalize_catalog_gdf`/`_is_local_path`/`_roi_gdf` helpers (identical logic, no S3/CDSE
  specifics). `api.download` gains `source: "cdse"|"mpc"` (default unchanged, `"cdse"`); `"mpc"`
  does not require `creds`.
- **New additive catalog column `boa_add_offset`** (`catalog/catalog.COLUMNS`) — the S2
  processing-baseline reflectance offset (fixes correctness debt **#10** for MPC), derived from
  `s2:processing_baseline` (**keyed on baseline, not date** — covers the reprocessed-pre-2022-date
  trap). Back-compat: `TileCatalog.read`/`append` fill a missing column with `0` (old catalogs,
  CDSE rows for now).
- **`datacube.builder.flatten_catalog`** emits a per-band `boa_add_offset` (reflectance bands only,
  `raster/images._is_reflectance`); **`build_datacube` applies it per source image** (new
  `builder._apply_boa_offsets`, right after `images.load_images`, before `dst_crs`/reference/
  resample/mosaic) via the new `raster/images.apply_boa_offset` op (`clip(DN+offset, 0, 65535)`,
  nodata-safe). A build-time integration test proves a calendar window straddling the 2022-01-25
  cutover harmonizes **before** the median (the exact #10 failure mode).
- **New `[mpc]` extra** (`planetary-computer`); `runbooks/32-mpc-baseline.md` written (not run —
  Claude never runs networked scripts): one MGRS tile (`s2grid=476da24`), band B04 only, two
  acquisitions straddling the baseline cutover.
- **Docs updated:** `CHANGES.md` (new top entry), `TODO.md` (#10 marked partially-done for MPC;
  new #30–33: CDSE offset retrofit, Phase-2 stream-vs-copy fork, signed-URL re-sign, full
  `download_resume` orchestration for MPC), `RECIPES.md` (MPC download recipe), `specs/31` banner
  (§5 "stage-local-convert-put" flagged DELETED, retargeted to Phase 2 — not yet rewritten),
  `specs/10` pointer (MPC is another first-class source through the same storage seam), this entry.
- **Open items flagged for the runbook, not guessed in code** (per the spec): the live
  `s2:processing_baseline`/`s2:mgrs_tile` STAC property names, and whether `fsd.storage.transfer`
  streams cleanly over fsspec's `http` backend for signed MPC hrefs (may need `aiohttp`) — both
  surface naturally at the runbook's step 1/2.

**→ NEXT:** Opus@high review pass on branch `spec32-mpc-implement` (commit `1cf1568`, worktree
`.claude/worktrees/spec32-mpc-implement`, diffed against `030f6ac`) — Opus merges to `main` and
pushes once review passes. Then the **user runs** `runbooks/32-mpc-baseline.md` (real MPC network,
hotspot-OK — one tile, one band, two tiny COGs) and pastes back `_result_step2.json` + the step-3
spot-check. Committed this session (user asked); not yet merged/pushed.

## PRIOR (2026-07-16) — STRATEGY PIVOT: MPC source + baseline harmonization → spec 32 SIGNED OFF (Opus@high); P1 split into two phases; new standing practice (spec cross-validation)

**The plan pivoted from "CDSE download-to-blob for P1" to a two-phase MPC-first approach** (agreed
with the user via interview → grilling → doc cross-validation). Reasoning: MPC serves Sentinel-2
L2A as **already-COG on Azure**, so the whole `jp2→COG` conversion problem (spec 25 / the ugliest
part of the draft spec 31 §5) **evaporates**, and we get real Azure-native COGs to test datacube
creation fast.

**Two-phase shape:**
- **Phase 1 (local, hotspot-friendly) = `specs/32-mpc-source-baseline-harmonization.md` — SIGNED
  OFF (2026-07-16).** A new fsd-native **MPC source** (`sources/mpc.py`, reuses `pystac-client`
  discovery + `planetary-computer` signing behind a new `[mpc]` extra; download = **pure COG
  byte-copy**, no re-encode). Fixes **correctness debt #10** (the S2 processing-baseline
  `BOA_ADD_OFFSET`): MPC serves **raw unharmonized DN** and exposes **no `raster:bands`** offset, so
  fsd derives the offset from **`s2:processing_baseline`** (keyed on baseline, *not* date —
  reprocessing stamps ≥04.00 on old dates), stores it as an additive **`boa_add_offset`** catalog
  column, and harmonizes **at build, per source image, before the median mosaic** (a calendar window
  can straddle 2022-01-25) via `clip(DN−1000,0,65535)` for reflectance bands (SCL exempt) — keeping
  the **uint16 + nodata=0** datacube contract. Test = pytest (synthetic offset/clamp/flatten) + a
  **single-tile / single-band** runbook straddling 2022-01-25 (hotspot-sized).
- **Phase 2 (Azure at scale) = `specs/31` retargeted.** Its old §5 (CDSE stage-local-convert-put)
  is **to be deleted** (MPC removes conversion). The storage-seam mechanics (fsspec-native config,
  `to_vsi`, one `rio_open` wrapper, `DefaultAzureCredential` for `rise` writes) survive. **Open
  Phase-2 fork:** stream MPC COGs in-place via `/vsicurl` vs bulk-copy MPC→`rise` and stream from
  `rise` — **consciously deferred** to be *measured* after at-scale cloud build exists (user's call
  2026-07-16), not argued now. (fsd reads only a ~5 km window from a ~110 km tile; full-tile
  download amortizes only under high per-tile cell reuse.)

**Spec 31 status:** still DRAFT; it was improved this session (fsspec-native config + adlfs
auto-credential + SDK token-cache replaced the bespoke registry/refresh-margin — cross-validated
against Azure/adlfs/fsspec/GDAL docs) but is now **Phase 2** and not yet signed off.

**New STANDING PRACTICE (encoded in `CLAUDE.md` + memory [[spec-cross-validation-practice]]):**
every spec leaning on external facts must be **cross-validated against reliable online sources
before sign-off**, carrying a **per-source-credit** "Best-practice alignment / sources" section
(what *specific* fact each source contributed, named inline — not a bare URL list). **Spec-
validation web searches now have standing permission** (no prior ask); all *other* searches still
follow [[ask-before-websearch]].

**Governance flag (consciously accepted):** an MPC source is the "build more data sources
(#11/#21)" work the 2026-07-15 diagnostic parked pending the **rslearn Plan B/C** call — accepted
eyes-open (small, reuses STAC discovery, fastest unblock). rslearn decision still parked.

**→ NEXT:** user runs `/handoff` → **Sonnet@medium** session implements **spec 32** against the
signed-off text (Opus does not implement). Then Opus review, then the user runs
`runbooks/32-mpc-baseline.md`. Nothing committed this session (specs 31/32, CLAUDE.md, memory edits
all on disk, uncommitted — user may want to commit).

## PRIOR (2026-07-15) — project-state DIAGNOSTIC done (Opus@high) → verdict + P1-kickoff staged (access probe written, spec-first handoff next)

**The diagnostic (interview → exhaustive corpus read → grilling) is complete.** Deliverables:
memory [[fsd-diagnostic-triage]]; a one-page visual state map (Artifact:
`https://claude.ai/code/artifact/bcc50b17-914b-486d-a66b-102661ea34ca`); this PROGRESS entry.

**Verdict (user's Q = "am I accreting, or is there a critical path? and am I managing this well?"):**
NOT random scope-creep — TODO.md is well-triaged, nearly every item real. The pattern is: the project
keeps finishing *locally-completable* work *around* its critical path (P1) instead of *through* it,
because **P1 is blocked and the blocker was never named.** The rail literally shows it — solid through
P0.9, skips the blocked P1, lands on a *partial* P5 (serving 27–30). **User confirmed both:** the
serving PoC was legitimate + well-timed (active-learning/STACNotator interconnect talk had just
happened — fsd needed to prove it can connect), AND real procrastination on Azure (new/unfamiliar).

**Decisions reached (grilling):** (1) **P1 stays the goal**; serving is *banked*, not relabeled — do
NOT continue that thread (#28/#29 deferrable). (2) Move #1 = **clear the P1 blocker**; the blocker is
100% activation energy — user is at state (a): `az login` done, working access, just hadn't sat down.
(3) rslearn Plan B/C call **consciously parked** (orthogonal to P1) — *but do not build more data
sources (#11/#21) until it's made.* (4) Promote correctness debt **#10** (STAC raster:offset/scale
across S2 baselines — silent wrong-answers) above the serving/feature long tail. (5) **Spec-first
handoff:** the next session *writes* spec 31, it does NOT code.

**P1 access facts nailed down** — **concrete values live ONLY in `../P1_AZURE_SETUP.md` §3 +
`../AZURE_INFRA_PRIVATE.md`** (workspace root, uncommitted). Shape only, for the public repo:
the target storage account is **ADLS Gen2 (HNS)**; **account keys DISABLED** → auth is
**`DefaultAzureCredential` (az-login token), FORCED** (no key/SAS); GDAL driver = **`/vsiadls/`**,
NOT `/vsiaz/`. The real unknown = whether the user's **personal** identity has **Storage Blob Data
Contributor** (private doc only confirms the *compute UAMI* does) — the access probe is the definitive test.

**PROBE RAN GREEN (user, 2026-07-15): `"pass": true`, all 3 steps.** P1 ACCESS IS READY — confirmed
end to end over VPN through the exact seams fsd uses. Facts for spec 31 (also in `../P1_AZURE_SETUP.md`,
now fully green):
- Identity / subscription / resource group confirmed — **names + IDs in `../P1_AZURE_SETUP.md` §2**,
  deliberately not repeated here (public repo).
- **adlfs `DefaultAzureCredential` round-trip works** to the scratch prefix (370 B write=read)
  → the user's **personal identity HAS Storage Blob Data Contributor** (no admin grant needed — the 403
  risk is dead).
- **GDAL 3.10.3 opens the object via BOTH `/vsiadls/` and `/vsiaz/`** with `AZURE_STORAGE_ACCESS_TOKEN`
  → use `/vsiadls/` as canonical (ADLS Gen2), `/vsiaz/` fallback. Auth = `az account get-access-token
  --resource https://storage.azure.com/`, Entra-only (keys disabled).

**Also this session — raapid-infra tfvars refreshed (2026-07-15):** `rise` AML is now a **list of
clusters** — `default` (E64ds_v4 ×4 = 256 cores) **+ NEW `d16`** (D16d_v5 ×32 = **512 cores**); Batch
pool unchanged (128 cores). Concrete values in `../AZURE_INFRA_PRIVATE.md` + [[fsd-azure-infra]] memory.
**New parked fork (P2/P4, NOT P1):** runner seam targets Batch (128) but the big fleet is AML `d16`
(512) — a Batch-vs-AML dispatch choice for when P2 lands; parked alongside rslearn.

**→ NEXT:** user runs `/handoff "write + sign off spec 31 (P1 storage seam) from the probe results"`
→ fresh **Opus@high** session writes **spec 31** (spec-first — it does NOT code): add `azure-identity`
to the `[azure]` extra; thread `storage_options`/`storage=` through the verbs; adlfs `abfs://` + GDAL
`/vsiadls/` reads in fsd code; demo a **local datacube build doing all I/O against `rise` blob** over
VPN. Then Sonnet@medium implements against the signed-off spec. Nothing committed this session (docs
only: `P1_AZURE_SETUP.md`, `runbooks/31-p1-access-probe.md`, `../AZURE_INFRA_PRIVATE.md`, this entry).

## PRIOR (2026-07-15) — spec 30 (serving Tier 2: mini-MPC + stac-geoparquet) REVIEWED (Opus@high) + runbook RAN GREEN (user) → Tier 2 VALIDATED; TODO #16 also fixed

**Opus@high review of `faf8382` = PASS** (storage-seam staging, href-rewrite, both documented
deviations all sound; no floating tags). Three minor fixes applied on top: README route-naming line
corrected to `/searches/...`, `register_and_url.py` now writes a failure `_result.json` like its
siblings, `.gitignore` covers `.pgdata/`/`*.ndjson`/`_result_register.json`.

**Runbook `runbooks/30-tier2-mini-mpc.md` RAN GREEN (user, 2026-07-15): steps 1–6 all PASS** — tile
curl `200 image/png 50145`; QGIS renders the 300-cell Austria crop map in the discrete class colors
over the true (slanted) cell footprints through the full pgSTAC → stac-fastapi-pgstac →
titiler-pgstac register→searchId→XYZ path. Step 7 (STACNotator in-app) skipped — the explicitly
non-gating stretch (D-C). **fsd is "just another MPC"; the TODO #26 serving contract is proven end
to end (Tier 1 spec 29 + Tier 2 spec 30).** Two runbook-run bugs found + fixed:
`Dockerfile.titiler-pgstac` now `apt-get install`s **`libexpat1`** (rasterio, via rio-tiler, links
`libexpat.so.1` at import; `python:3.12-slim` omits it → the `raster` worker failed to boot); and the
runbook's Docker-up/directory-scoping + the step-5 curl `{z}/{x}/{y}` substitution (curl globs `{}`)
were clarified. New plain-language **`MINI_MPC_NOTES.md`** at the **workspace root** (outside the
public repo) — Docker primer + running issue log, per the user's request (memory
[[user-docker-infra-onboarding]]).

**Also fixed this session — TODO #16 (`flatten` multi-zone `coords.npy`):** `flatten` now reprojects
each cube's per-pixel easting/northing from its native CRS to **EPSG:4326 (lon, lat)** before
concatenation (`flatten._to_lonlat`), so a multi-UTM-zone training set no longer mixes incomparable
eastings/northings. Behavior change to `coords.npy` (CHANGES.md); new multi-zone test; **214 passed,
3 skipped**, ruff clean.

**Committed + pushed:** all the above is on **`origin/main` @ `60e5cc2`** (`WEB_CONCURRENCY=4` set;
review + runbook fixes; TODO #16 coords→4326). Upstream now tracked.

**→ NEXT (redirected 2026-07-15):** the user paused feature-work for a **project-state DIAGNOSTIC
walkthrough** — a fresh Opus@high session reads the whole corpus (all specs 00–30, ROADMAP, TODO,
every `.md`) to reconstruct *where we started → where we're going → where we are*, and answer the
user's core question: **am I accreting endless TODOs, or is there a critical path to P1?** The
diagnostic session must **interview the user first** about what they want out of it. Baton:
**`/tmp/fsd-handoff-project-diagnostic.md`**. **TODO #28 (render config → STAC render extension) is
deferred back into the queue** — it was the next feature but got redirected. Also still open after 30:
TODO #26 catalog-format full-migration, #29 (B02/B03, PARKED for wifi). **P1 = the Azure storage seam**
(`specs/10`; prereqs in `../P1_AZURE_SETUP.md`) has not started.

## PRIOR (2026-07-15) — spec 30 (serving Tier 2: mini-MPC + stac-geoparquet) IMPLEMENTED (Sonnet@medium) → hand to Opus for review, then the user runs the Docker runbook

**Sonnet@medium implemented `specs/30-tier2-mini-mpc-validation.md`** (signed off earlier the same
day). Implements **TODO #26 Tier 2** (the second half of the serving-contract validation; Tier 1 =
spec 29, DONE). Builds on spec 28 (true-polygon geometry) + spec 29 (the discrete crop-class colormap).

- **B — stac-geoparquet export (fsd core, additive) — DONE + verified.** New
  `catalog/stac_geoparquet.py` (`items_to_stac_geoparquet` / `stac_geoparquet_to_items`, staged
  through a local tmp file + the `fsd.storage` seam since the installed `stac-geoparquet==0.8.1` API
  wants a real path), new `[serving]` extra, `demos/mini_mpc/export_stac_geoparquet.py` CLI.
  `tests/test_stac_geoparquet.py` round-trip PASSES in a fresh `.venv-serving`
  (`pip install -e ".[dev,serving]"`; `215 passed, 2 skipped` full suite, `ruff` clean); the core
  `.venv` skips the test cleanly (`pytest.importorskip`). **Also smoke-run against the real 300-item
  Austria catalog** (`tests/outputs/demo_e2e/model_outputs/stac/`) — export + read-back both verified
  by hand (all 300 items round-tripped correctly).
- **A — local "mini-MPC" harness — scripts + runbook written, not yet Docker-run (Claude never runs
  Docker).** `demos/mini_mpc/` (`docker-compose.yml` pinning `ghcr.io/stac-utils/pgstac:v0.9.11`
  as-is + two locally-built images that install the **pinned stock PyPI packages**
  `stac-fastapi.pgstac==6.3.1` / `titiler.pgstac==3.0.0` on a slim Python base, since no published
  "just pull it" app-layer image exists upstream — README's table documents exactly what's borrowed
  vs. built, and why eoAPI's own compose couldn't be vendored verbatim (it `build:`s from a full
  monorepo checkout too)); `load_pgstac.py` (ndjson + href-rewrite → `/data` bind-mount — the
  href-rewrite logic was hand-verified against the real catalog: all 300 hrefs rewrite correctly);
  `register_and_url.py` (reuses `titiler_serve.build_colormap`; URL-building logic hand-verified with
  a mocked HTTP call). **One documented deviation from the spec's draft:** the installed
  `titiler.pgstac==3.0.0` names its routes `/searches/register` + `/searches/{id}/tiles/...` (response
  key `id`), not `/mosaic/register`/`searchid` — MPC's own product wraps the identical contract under
  different names (`CHANGES.md` + the script's docstring have the full note, à la spec 29's rio-tiler
  pin). `runbooks/30-tier2-mini-mpc.md` (7 steps; hard bar = steps 1–6, STACNotator-in-app a stretch).

**Living docs updated:** `CHANGES.md`, `RECIPES.md` (both new recipes), `TODO.md` #26 →
DONE-pending-runbook, `pyproject.toml` (`[serving]` extra), spec 30's banner → IMPLEMENTED.

**→ NEXT:** Opus review, then the **user runs** `runbooks/30-tier2-mini-mpc.md` (one-time cost =
building the two app images locally — small `pip install`s on a slim base, no satellite downloads;
recommend on wifi) and pastes back each step's `_result.json` + the QGIS screenshot. **Still open
after 30:** TODO #26 catalog-format full-migration (run_inference default → stac-geoparquet), TODO
#28 (render config → STAC render extension — makes the categorical color turnkey, no baked-in
`colormap` param), #29 (B02/B03 for true-color input imagery, PARKED for wifi).

## PRIOR (2026-07-15) — spec 30 (serving Tier 2: mini-MPC + stac-geoparquet) SIGNED OFF → hand to Sonnet

**Opus@high interview → `specs/30-tier2-mini-mpc-validation.md` SIGNED OFF (2026-07-15).** Implements
**TODO #26 Tier 2** (the second half of the serving-contract validation; Tier 1 = spec 29, DONE). Builds
on spec 28 (true-polygon geometry) + spec 29 (the discrete crop-class colormap). **Two deliverables:**

- **A — local "mini-MPC" harness** (`demos/mini_mpc/` + `runbooks/30-tier2-mini-mpc.md`): borrow the
  **stock eoAPI docker-compose** (pgSTAC + stac-fastapi-pgstac + titiler-pgstac), load the spec-28
  output STAC (300 Austria crop-map cells) via **`pypgstac` ndjson** (convert the JSON catalog we already
  write; **rewrite COG asset hrefs host→`/data` + bind-mount** the outputs dir so GDAL resolves them
  inside the container — the one non-obvious wiring step), then prove the **register→searchId→XYZ** MPC
  path renders. Categorical color rides in the tile **`colormap`** query param (reuse
  `titiler_serve.build_colormap`), `assets=output`, `nodata=255`, `resampling=nearest`. **Success = curl
  (search returns 300 items with true polygon geometry + register 200 + tile PNG) + a QGIS XYZ-layer
  visual** (the user asked for QGIS — now through the full pgSTAC→titiler path); STACNotator-in-app is an
  optional stretch (may need a STACNotator config/PR to add a custom MPC endpoint — not gating).
- **B — stac-geoparquet export** (fsd core, additive): new `catalog/stac_geoparquet.py` +
  `[serving]` optional extra (`stac-geoparquet`) + a `demos/mini_mpc/export_stac_geoparquet.py` CLU; the
  #26 north-star interchange format. **Round-trip pytest only** in this spec (items→geoparquet→items
  equal on id/geometry/bbox/dt/proj/asset); **not** wired into the run_inference default write path — that
  full catalog migration stays the #26 follow-on.

**Interview decisions (all 5 open-qs accepted as recommended):** new `[serving]` extra; new
`catalog/stac_geoparquet.py` module; href-rewrite + `/data` bind-mount; geoparquet round-trip pytest only;
Opus specs → **Sonnet@medium implements** the export + harness scripts → the **user runs the Docker
runbook** (Claude never runs Docker/pipeline, per CLAUDE.md). Non-goals: no Azure/production deploy (the
`rise` deploy is propose-only, separate), no input-imagery serving (B02/B03 = #29, parked for wifi), no
render-extension (#28), no STACNotator code change for the hard bar.

## PRIOR (2026-07-14, later) — specs 28 + 29 REVIEWED (Opus@high), MERGED to `main`, all runbooks PASS ✅

**Both serving-pivot specs are DONE: reviewed, merged, and validated end to end.** Merged fast-forward
into `main` (`50749e8`→`620441e`, "Implement specs 28+29"); **not pushed to origin** (per the user —
local merge only). The implementation baton was `/tmp/fsd-handoff-specs-28-29-review.md`.

- **Spec 28 (STAC geometry fix, TODO #27 DONE):** `catalog/stac.py::cog_outputs_to_items` gained
  `geometries={cog: geometry.geojson_path}` (+ `_read_footprint_geometry` helper +
  `cog_outputs_to_items_from_manifest(input_csv)` convenience wrapper). `api.py::_finalize_outputs`/
  `_resolve_inference_pairs`/`_run_inference_roi` thread `geometries` from `input.csv.shapefilepath`
  for both inference modes; `geometries=None` (bare COG lists, folder/list pre-built modes) keeps the
  old raster-bbox behavior unchanged. Missing/unreadable geometry **raises** (deterministic, no
  fallback). New `demos/regen_output_stac.py` + `runbooks/28-stac-geometry-regen.md`. 4 new tests;
  `BUGS.md` BUG-003; `CHANGES.md`; `specs/17` pointer; `TODO.md` #27 DONE.
- **Spec 29 (Tier-1 pre-styled XYZ, TODO #26 Tier-1 DONE):** new `demos/titiler_serve.py` (FastAPI +
  rio-tiler; `GET /cropmap/tiles/{z}/{x}/{y}.png` over `merged.tif`, discrete colormap from
  `e2e_austria.CLASS_COLORS`/`render.json`, `nodata=255` transparent, nearest resampling, permissive
  CORS) + a new `[titiler]` pyproject extra (isolated `.venv-titiler`, kept out of `.venv`) +
  `runbooks/29-tier1-stacnotator-byo.md`. 4 new tests (`tests/test_titiler_serve.py`,
  `pytest.importorskip("rio_tiler")` — skip cleanly in the core `.venv`). rio-tiler note: masking
  needs a `numpy.ma.MaskedArray` (the 2nd `ImageData` positional is `cutline_mask` in rio-tiler
  6/7.x, not an alpha mask) — fixed in `_empty_png`.
- **Opus@high review:** clean, no changes required. Verified the spec-28 no-fallback contract is
  atomic (all four `ValueError` paths fire inside `cog_outputs_to_items` before `write_stac_catalog`
  → no partial STAC), `geometries=None` correctly reserved for the manifest-less folder/list modes,
  `_resolve_inference_pairs`'s `-> (pairs, geometries)` change fully covered (one call site), the
  ROI-mode `input.csv` always carries `shapefilepath` (`workflows/create_datacube.py:90`), and the
  rio-tiler `MaskedArray` reasoning holds. `pytest -q` = 213 passed, 2 skipped; ruff clean.
- **Runbooks — ALL PASS (user ran, 2026-07-14):**
  - **28 regen:** the 300-item Austria demo STAC regenerated from `input.csv` → the slanted S2-cell
    polygons (not raster boxes). *(Doc fix: the runbook's step-2 spot-check path was missing the
    `fsd-inference/` collection subfolder — corrected; the regen script itself was always right.)*
  - **29 curl + QGIS:** the pre-styled XYZ server renders the categorical crop map correctly (discrete
    colors, nodata transparent) — confirmed visually in QGIS.
  - **29 STACNotator BYO:** the running `titiler_serve` XYZ URL loads as a Bring-Your-Own-XYZ layer in
    a locally-run STACNotator dev stack (`make dev-init`) — the strongest external confirmation. (GEE
    creds are irrelevant to BYO mode; Docker daemon just had to be running.)

**Serving pivot — Tier 1 is now fully validated.** fsd emits standard STAC (true footprints) + a
pre-styled categorical XYZ that STACNotator consumes as-is.

**→ NEXT (Opus to spec):** **TODO #26 Tier 2** — a local pgSTAC + titiler-pgstac "mini-MPC" so
STACNotator drives fsd's STAC through the same two-API path it uses for MPC (the richer, non-BYO
serving mode). Also open: **TODO #28** (model-dev render config → STAC render extension — the
`render.json` seam already stubbed in `titiler_serve.build_colormap`) and **#29** (B02/B03 band
expansion for true-color input imagery — PARKED for university wifi). Not pushed to origin (commit/push
only on request, per CLAUDE.md).

## PRIOR (2026-07-14) — STRATEGIC PIVOT on serving: fsd emits standard STAC+COGs+render config → STACNotator (via stock pgSTAC+titiler-pgstac); the fsd Leaflet dashboard is CANCELLED

**What happened:** started task (2) as a *local titiler+Leaflet dashboard to verify the inference STAC*
(explainer `demos/TITILER_LEAFLET.md` + `specs/27` written, MosaicJSON DB-free design signed-off-pending).
A design discussion then **reframed the whole thing** and `specs/27` is **SUPERSEDED — do not implement**.

**The pivot (all agreed with the user, 2026-07-14):** the user cloned NASA Harvest's **STACNotator** (a
React+OpenLayers imagery-annotation tool) into the workspace as read-only reference; I digested it →
**`../STACNOTATOR_DIGEST.md`** (workspace root, NOT in the fsd repo — never committed). Key finding:
**STACNotator IS the viewer**, and it consumes **MPC's two APIs** — a STAC API (CQL2 search + Sort) + a
**titiler-pgstac** data API (`/mosaic/register` → `searchId` → XYZ `/mosaic/{searchId}/tiles/{tms}/{z}/{x}/{y}`
+ viz params). So:
- **fsd builds NO dashboard.** fsd's job = emit artifacts standard enough that a **stock eoAPI stack
  (pgSTAC + stac-fastapi + titiler-pgstac)** serves the XYZ endpoints STACNotator consumes → fsd becomes
  "another MPC". **3-layer seam:** fsd (COGs on blob + `stac-geoparquet` catalog + render config) → stock
  serving infra (platform/`rise` or fsd-adjacent — *a deploy decision, not fsd code*) → STACNotator.
- **Catalog → `stac-geoparquet`** for BOTH CDSE downloads and model outputs (option (b): keep the internal
  working `catalog.parquet` for compute now; full migration a follow-on). STAC is justified precisely
  because it feeds pgSTAC/titiler-pgstac + is the interop lingua franca; MosaicJSON was the throwaway.
- **Model-dev display config → STAC Render Extension** (`renders` on the output collection) = the standard
  "how to display my output"; titiler-pgstac serves it natively (verified). Categorical crop map uses its
  custom `colormap` object (better than STACNotator's self-hosted `colormap_name`).
- **Scale goal:** many projects, MANY models/outputs, all conveniently on STACNotator.

**Locked decisions:** (1) no bespoke fsd dashboard/repo — STACNotator + stock serving; (2) the stock
pgSTAC+titiler-pgstac stack runs as **platform infra**, fsd owns only the **catalog/COG/render contract**;
(3) **model outputs first**, input-imagery viewing + **B02/B03 band expansion PARKED for university wifi**
(mobile-hotspot now — no big downloads); (4) validate in two tiers — **Tier 1** pre-styled XYZ into
STACNotator BYO (fast, hotspot-OK, no download), then **Tier 2** local pgSTAC+titiler-pgstac "mini-MPC".

**Captured as TODO #26 (serving contract + validation), #27 (STAC-geometry fix — now serving-critical),
#28 (render config → STAC render extension), #29 (B02/B03 expansion, parked).** `specs/27` +
`demos/TITILER_LEAFLET.md` both carry a SUPERSEDED/concepts-primer banner. **A real finding surfaced:**
`cog_outputs_to_items` writes each Item's geometry as the raster bbox (`stac.py:183`), not the true
S2-cell polygon in `<cell>/geometry.geojson` → over-claims coverage; matters for `ST_Intersects`/pgSTAC
search (TODO #27).

**TWO SPECS DRAFTED + SIGNED OFF (2026-07-14):**
- **`specs/28-stac-output-geometry-fix.md`** (TODO #27) — the STAC item-geometry fix, **manifest-driven**
  per the user: `cog_outputs_to_items(cog_filepaths, geometries={cog: geom_path})` sources each Item's
  footprint from `input.csv.shapefilepath` (deterministic — no sibling-file discovery, no raster-box
  fallback; missing geometry raises). Both inference modes + a `demos/regen_output_stac.py` feed it from
  `input.csv`. Regenerates the existing 300-item STAC. +tests. **Hotspot-friendly.**
- **`specs/29-tier1-prestyled-xyz-validation.md`** (TODO #26 Tier 1) — a minimal `demos/titiler_serve.py`
  serving `merged.tif` as a **param-free pre-styled XYZ** (`GET /cropmap/tiles/{z}/{x}/{y}.png`,
  hand-rolled over rio-tiler: discrete categorical colormap + nodata=255 transparent + nearest, CORS on),
  from a `render.json`/`CLASS_COLORS` config. **No viewer** — validated by pasting the URL into
  **STACNotator's Bring-Your-Own-XYZ** (QGIS XYZ as a quick pre-check). Replaces the cancelled `specs/27`
  `titiler_serve`. **Hotspot-friendly** (serves existing `merged.tif`).

**→ NEXT:** hand off to a **Sonnet@medium** session to implement **specs 28 + 29** (independent — either
order, or parallel). Both need no downloads. After they land + Opus review, the Tier-1 runbook is the
user's STACNotator BYO check. **Still to spec (Opus):** TODO #28 (model-dev render config → STAC render
extension) and TODO #26 **Tier 2** (local pgSTAC + titiler-pgstac mini-MPC — heavier, do when convenient),
**#29** (B02/B03 band expansion — PARKED for wifi). Nothing committed yet; `specs/{27,28,29}`,
`demos/TITILER_LEAFLET.md`, `TODO.md`, `PROGRESS.md` edits are on disk, uncommitted.

## PRIOR (2026-07-13 pm) — FULL Austria e2e EXECUTED; `E2E_AUSTRIA.md` is now the single go-to doc; next = titiler/Leaflet STAC-verify spec (task 2)

**The full Austria e2e ran for real, end-to-end, and PASSES** (real CDSE download → datacube → train on
real EuroCrops → inference → crop map). Everything on `main` (pushed). Run: Waldviertel AT_ROI,
2018-04-01..09-30, T=10, `--cores 8`; **207 granules / 44.61 GB**, **300 grid cells**, 900 train fields
(9 classes); `merged.tif` **6830×6868 EPSG:32633, 99.2% valid**. Timing **~100 min** (download 45% /
inference 44% dominate). Numbers stitched (download+train from pass 1, inference from a clean re-pass) —
see `demos/E2E_AUSTRIA.md §8`.

**3 issues the full run surfaced + FIXED (213 pytest / ruff clean):**
- **demo step 5 crashed** — `run_inference` called without the required `output_folderpath` →
  `PreflightError`; now passes `OUTDIR/model_outputs`. Demo-only.
- **STAC item-id collision (real `src/fsd` bug)** — `cog_outputs_to_items` derived the item id from the
  COG filename stem (constant `"output"`) → `collection.json` had N identical links + 1 item file on
  disk. Fixed to derive from the per-cell folder (`_output_item_id`) + a uniqueness guard; strengthened
  `test_run_inference_writes_cogs_and_stac` (asserts distinct ids). `merged.tif` + per-cell COGs were
  unaffected. Validated on the real run (300 links, 300 unique).
- **demo step 2 metric** now reports the honest **aggregate (wall)** transfer rate + verdict (was the
  misleading per-stream), matching `download_cli`; cost_model feeds `estimate.py` the aggregate rate.

**Also:** crop_map/NDVI recolored via a semantic + separable `CLASS_COLORS` dict (was pink grassland);
user regenerated the 3 committed `demos/figures/`.

**Phase-2 doc work DONE — `E2E_AUSTRIA.md` is the single go-to doc:** §8 filled from the real run; the
safe download runner (`python -m fsd.sources.download_cli`: `--dry-run`/`--stop-file`/
`--max-concurrent-s3`/`_result.json`, the probe/per-stream/wall rates) threaded into §2 + a §5 tip;
**Appendix C** ("real bugs full-ROI runs caught": spec-20 tile-merge, spec-26 STAC, multi-zone merge);
**`demos/README.md`** shrunk from the stale Ethiopia writeup to a thin redirect.

**Two TODOs opened (do NOT tangent now):** **#24** re-tune `max_concurrent_s3` per Azure region/pool
(local run was **link-bound**: probe 26 vs aggregate 17 MB/s, 4 streams slower than 1 — a laptop-uplink
property that inverts on a datacenter NIC); **#25** fine-grained per-cell inference timing (model-load /
build / predict / COG-save) + kill the per-cell model reload — found `cubes_per_task` is silently
ignored in ROI mode (`api.py:793`), so the bundle reloads 300× (per-cell "infer" ≈ flat ~7.8s model
load, not predict). Discussion-only until we decide it's worth specing.

**→ NEXT: task (2) — titiler + Leaflet explainer doc + a detailed spec for Sonnet** to stand up a basic
tile server + Leaflet dashboard that verifies the inference **STAC catalog + COGs** (ROADMAP P5 /
TODO #14). Handoff being prepared. NOTE: actually *running* titiler needs `model_outputs/{stac,cells}`
COGs under `tests/outputs/demo_e2e/` — the user may delete that to free space, so the titiler work will
regenerate them via a fast **download-free** inference re-pass (cells skip). The doc + spec can be
written regardless.

## PRIOR (2026-07-13 am) — spec 26 confirm-run EXECUTED for real + pipeline hardened; next = Austria go-to doc

**The spec-26 network confirm-run was run for real (CDSE, 3.5 GB, Austria 1-MGRS slice) and PASSES.**
Everything on `main` (pushed, HEAD `69e6517`). Fresh-download `_result`: `status=ok`, 65/65 files
(13 granules × 5 = 4 bands + MTD_TL.xml), `failed=0`, `skipped=0`, gb=3.50, integrity verified on disk
(52 tif + 13 xml, 0 leftovers, 13 catalog rows). **Throughput baseline: probe 25 / per-stream 4.8 /
wall 19 MB/s → link-bound, 4 transfer streams slightly SLOWER than 1.**

**Bugs/gaps this real run surfaced and we FIXED this session (all committed + tested, 209 passed):**
- `download()` crashed on a **fresh `--dst`** (disk-usage probe before makedirs) → now `fs.makedirs`
  the local root [spec 25 latent bug].
- `format_download_plan` **contradicted itself** at `missing=0` ("not present" + a download cmd) →
  fixed [spec 23 latent bug].
- `_result.json` **`expected`/`error` were dead** (`{}`/`None`) → now populated; a crash writes a
  `status=failed` result before re-raising; new `--expected-json` merges runbook criteria [spec 26 §4].
- **stop-file felt slow + silent** → now prints `stop requested — draining N…` within ~1s
  (`STOP_CHECK_EVERY_S=1.0`, decoupled from `PROGRESS_EVERY_S`); the ~`max_staged` overshoot is the
  clean-drain-by-design (no partial files); `--max-staged` trades it.
- **misleading throughput metric** → added `transfer_wall_seconds` + `wall_transfer_mb_per_s` (honest
  all-streams rate) and a **`--max-concurrent-s3`** knob to sweep stream count. Runbook step-4 rewritten.
- Silent startup phases (probe + planning) now labelled; `.gitignore` gained `.claude/`.

**Commits (all pushed to `main`):** `8bb1882` gitignore, `c822654` startup labels, `aa20279` makedirs
+ expected/error, `b4b1bf5` format_download_plan, `2f0b530` stop-file ack, `69e6517` wall metric +
`--max-concurrent-s3`. (Plus `356f07b` = the merged spec-26 offline half.)

**→ IMMEDIATE NEXT (user is on university wifi, ready to run): execute the FULL Austria e2e.**
Runbook **`runbooks/27-austria-full-e2e.md`** is written + on `main`. It runs `demos/e2e_austria.py`
(FULL mode: real CDSE download of the whole AT_ROI, Apr–Sep, → datacube → train on real EuroCrops
labels → inference → crop map). Size estimate (scaled from the confirm-run): ~2–4 MGRS tiles / ~80–160
granules / ~20–45 GB / ~1–1.5 hr. **Step 0 = a full-ROI dry-run to size it exactly before committing;
Step 1 = `rm -rf imagery/` for clean §8 numbers; Step 2 = the backgrounded run; Step 3 = paste back
`timings.json` + coverage.** The demo's download uses `download_resume` directly (no `--stop-file`;
Ctrl-C + re-run resumes). Note the AT inputs are REAL EuroCrops ground truth in the test region
(labels ARE meaningful; the *point* is infra, not model quality — the earlier "toy/Ethiopia" framing
is stale). `AT_ROI` = Waldviertel (~14.6–15.5°E, 48.4–49.0°N, single UTM-33), 900 train fields.

**→ THEN (the pre-P1 goal): make the Austria end-to-end the GO-TO USER DOCUMENT.** Fill `E2E_AUSTRIA.md
§8` from runbook 27's output, and reconcile the two demos docs (this is the ROADMAP pre-P1 deliverable,
not new pipeline code):
- `demos/README.md` — **STALE**: describes the old Ethiopia offline demo, references
  `demos/e2e_ethiopia.py` (renamed to **`e2e_austria.py`**) and `shapefiles/inference_roi.geojson`.
  Superseded by `E2E_AUSTRIA.md`.
- `demos/E2E_AUSTRIA.md` — the intended go-to guide, but: **§8 "Results (fill from a real run)" is an
  empty placeholder** we can now fill with the real confirm-run numbers; and it has **zero mention of
  the safe download runner** (`python -m fsd.sources.download_cli`, `--stop-file`, the confirm-run,
  spec 26) — the whole download story we just built + validated. §2 predates all of it.
- Decide: fold `README.md` into `E2E_AUSTRIA.md` as the single canonical doc (thin redirect README),
  and thread the real download step + numbers through it. Handoff doc: `/tmp/fsd-handoff-austria-doc.md`.

## PRIOR (2026-07-11) — spec 26 offline half REVIEWED (Opus@high): PASS on the hard stuff, 2 small fixes queued

**Opus@high review of the spec-26 offline half (in the worktree `.claude/worktrees/spec26-download-cli`).**
Verified **correct** (do not touch): the `should_stop` throttle is race-free (`_stop()` runs only in the
single submit-loop thread; callbacks never touch `last_stop_check`/`stop_cached`; sticky `stopped` set
under `lock`, read after pool join); **no `sem_staged` permit leak** at either checkpoint (top-of-loop
break pre-`acquire`; post-`acquire` release-then-break); `download_resume` stop-before-cooldown ordering
right (a user stop never enters cooldown); `--dry-run` touches zero band bytes; `_fmt_progress`
`ETA ~?`-until-`done>0` math correct. Local `pytest` 55 passed on touched files, `ruff` clean.

**Found 2 defects → fix in a Sonnet@medium session** (handoff written:
`/tmp/fsd-handoff-spec26-sonnet-fixes.md`, exact code + 2 new tests):
- **Fix 1 (correctness):** the CLI's exit-code/`status` gates on `sum_results`' **summed**
  `failed_count`, which over-counts failures a later resume pass recovered → a successful-but-flaky
  run reports `status="failed"`/exit 1 (contradicts the runbook's own step-3 integrity PASS; the demo
  treats the same number as a soft warning). Fix = judge the **terminal pass** (download_resume's own
  break condition), treat empty `results` (stop before pass 1) as `stopped`, keep summed counts as
  metrics + add `failed_total` diagnostic. Exit 0 on clean-or-stopped preserved.
- **Fix 2 (usability):** a stale `--stop-file` (e.g. `/tmp/fsd.stop` left after a stop) makes the
  documented "re-run to resume" an instant no-op stop. Fix = runbook says `rm -f` the stop-file before
  resuming + a tiny CLI startup warning when the stop-file already exists.
- **NOT fixed (left for the user):** the runbook's `missing_count [5,10]` range is likely low
  (~12 granules for a 2-month single-tile window at ~5-day S2 revisit); user decides whether to widen.

**Next: Sonnet@medium implements the 2 fixes** (target: `pytest` **203 passed, 1 skipped**, ruff clean),
then hand off + clear. The network confirm-run (`runbooks/26-download-confirm-run.md` step 2 onward)
still waits for the user on a real (non-hotspot) connection.

**UPDATE (2026-07-11, Sonnet@medium):** both review fixes landed — CLI completion gate now judges the
terminal pass (`results[-1]`) instead of `sum_results`' summed `failed_count`, empty `results` maps to
`status="stopped"`, new `metrics.failed_total` diagnostic; stale-`--stop-file` startup warning added +
runbook step-2 now says `rm -f` it before resuming. `pytest -q` = **203 passed, 1 skipped**, `ruff`
clean. Worktree left uncommitted per CLAUDE.md (commit only on request).

## PRIOR (2026-07-11) — spec 26 offline half IMPLEMENTED (safe download CLI + should_stop seam)

**Implemented in a Sonnet@medium session against `specs/26-safe-download-runner.md` (offline
half only — no network run, per CLAUDE.md).** Landed, all contained to `sources/cdse.py` +
one new module:
- `should_stop: Callable[[], bool] | None = None` kwarg on `download()`/`download_resume` (spec
  §1): checked in the submit loop at the two existing checkpoints, throttled to
  `config.PROGRESS_EVERY_S`, identical halt-new-submissions-only semantics to `tripped`/
  `pool_broken`. New additive `DownloadResult.stopped`; `sum_results` ORs it; `download_resume`
  passes `should_stop` through + `if r.stopped: break` + a pre-pass check.
- New `src/fsd/sources/download_cli.py` (`python -m fsd.sources.download_cli`): `--dry-run`
  (plan only, zero band bytes, no probe), `--stop-file` (builds the `should_stop` closure), an
  optional single `probe_throughput` on the real path (`--no-probe` to skip), writes the spec-24
  `_result.json`; exit code 0 on clean-or-stopped, non-zero on failed/tripped/pool_broken.
- `_fmt_progress` ETA edge case: `ETA ~?` until `done>0` (was misleadingly `ETA 0m`).
- `runbooks/26-download-confirm-run.md` — fully written offline (self-contained `expected`
  block: step-1 `missing_count` in `[5,10]`, step-2 clean `status=ok`/`failed=0`/`stopped=false`,
  step-3 integrity script, step-4 report, optional stop drill). **Not run** — the network half
  (mobile-hotspot pause) is deferred to whenever the user has a real connection.
- Tests: 8 new (`tests/test_cdse.py` — should_stop mid-pass halt via watchdog + `max_staged=1` +
  `_SyncExecutor` determinism, `should_stop=None` no-op, `download_resume` breaks on stopped pass
  no cooldown, `sum_results` ORs `stopped`, `_fmt_progress` ETA `~?`/`~Nm`; new
  `tests/test_download_cli.py` — dry-run zero-bytes + result-json, real-path wiring +
  `--stop-file` predicate + exit-code mapping, missing-creds guard). `pytest -q` = **201 passed,
  1 skipped** (all 47 original `test_cdse.py` regressions + 154 other pre-existing tests
  unaffected); `ruff check src/ tests/` clean. Docs updated: `CHANGES.md`, `RECIPES.md`, `README`
  (one-line pointer), `TODO.md` (#23, cost_model persistence follow-up).

**Next: Opus@high review pass**, then hand off + clear (per spec 26's deliberate pause) — the
confirm-run itself (runbook step 2 onward, real CDSE download) waits for the user on a real
connection; a later session verifies the pasted `_result.json` against the runbook's own
`expected` block.

## PRIOR (2026-07-11) — spec 25b REVIEWED (PASS) + spec 26 SIGNED OFF (safe download runner)

**Spec 25b review (Opus@high) = PASS.** Traced the exception-safety invariant through every
callback path (transfer ok→convert / submit-raises / cfut-raises / failed / skipped / no-convert):
`_finalize` runs exactly once per item, each acquired `sem_staged` permit releases exactly once,
`remaining`/`sem_staged` never sit behind a fallible call. No double-release/double-finalize. The
beyond-spec `flush_lock` is correct + necessary (serializes concurrent chunk-flush parquet writes;
never nested with `lock` → no deadlock; end-of-run flush is post-pool-join so needs none).
Re-queue-on-failure is safe because `catalog.append` is idempotent upsert-by-id (union files).
Verified: `test_cdse.py` 47 passed, full suite **193 passed / 1 skipped**, ruff clean; docs
(CHANGES §25b, TODO #22, spec-25 pointer) accurate. Minor non-blockers noted (tautological assert in
test 1; `transfer_pool.submit` raise→loud-exit-not-hang; persistent-flush-failure metric undercount
recovered by resume) — none warrant a change.

**→ `specs/26-safe-download-runner.md` SIGNED OFF (2026-07-11), C1–C6 accepted as drafted.** The
first real CDSE network exercise of the spec-25/25b pipeline, as a **safe runner + confirm-run**.
Locked (interview): **D1** one spec = CLI + confirm-run; **D2** a thin **CLI wrapping
`download_resume`** (`python -m fsd.sources.download_cli`), NOT a Snakemake unit-of-work; **D3**
`--stop-file` checked **mid-pass** via a generic `should_stop` predicate at the two submit-loop
checkpoints (throttled to `PROGRESS_EVERY_S`); **D4** confirm-run = tiny **1-MGRS-tile** Austria
slice (~7 granules / ~2 GB). Additive `DownloadResult.stopped`; `--dry-run` = `plan_download` only
(**zero band bytes**, no probe); `_fmt_progress` gains rate+ETA; `_result.json` per spec 24; exit
code doubles as PASS/FAIL (0 on clean OR user stop). Untouched: `_transfer_one`/`_convert_one`/
`to_cog`/discovery/circuit-breaker/`pool_broken`.

**⚠️ DELIBERATE PAUSE (mobile-hotspot).** Spec 26 splits at a network seam. **Offline half**
(implement + review with NO network): the CLI, the `should_stop` seam, `DownloadResult.stopped`,
`_fmt_progress` ETA, all pytest (monkeypatched), docs, **and the fully-written runbook
`runbooks/26-download-confirm-run.md`**. **Network half** = runbook **step 2 onward** (real
download → integrity → report). After 26 is implemented + reviewed we **hand off + clear**; the
user runs the confirm-run only on a real (non-hotspot) connection, whenever available, and pastes
the `_result.json` back — verified against the runbook's **self-contained `expected` block**, not
this conversation.

**Next step: implement spec 26 (offline half) in a fresh Sonnet@medium session** (user runs
`/handoff`, `/model sonnet` + `/effort medium`, points it at `specs/26-safe-download-runner.md`).
Opus does NOT implement. After it lands + Opus review → hand off + clear → confirm-run later.

## PRIOR (2026-07-11) — spec 25b IMPLEMENTED (pipeline exception-safety / no-hang fix)

**Implemented in a Sonnet@medium session** against the signed-off spec (contained to
`sources/cdse.py`: the `download()` callbacks + submit-loop stop condition, + additive
`DownloadResult.pool_broken`, + the one-liner OR in `sum_results`). `pytest -q` = **193 passed, 1
skipped** (42 original `test_cdse.py` tests unchanged + 5 new spec-25b tests: pool-submit-raises
no-hang, convert-done-result-raises no-hang + permit release, PoolBroken breaker-neutrality,
catalog-flush-failure no-hang + resume recovery, `sum_results` ORs `pool_broken`); `ruff check
src/ tests/` clean; no network run (per CLAUDE.md — spec 26's job).

**One thing found beyond the spec's explicit text, needed for correctness:** moving the chunk-flush
catalog write **outside** the counters lock (spec §3) means concurrent flushes of *different*
snapshots can now run truly in parallel — which would race-write the same parquet file and corrupt
it (caught by a flaky-`_append_downloaded` regression test: lost a row + a `thrift deserialize`
error on the next write). Added a dedicated `flush_lock` around just the `_append_downloaded` call
(not the counters) — serializes the I/O without blocking `_finalize`'s metric updates behind it,
preserving the spec's intent.

Docs updated: `CHANGES.md` (new entry under spec 25), `TODO.md` (#22 per-granule convert
quarantine, deferred), `specs/25-download-convert-redesign.md` (status line points to 25b),
`PROGRESS.md` (this entry) + memory `fsd-status`.

**Next: switch back to Opus@high for a review pass**, then start the **spec 26** interview (safe
runner `--dry-run`/`--stop-file`/progress + the measured confirm-run — the first real CDSE network
exercise of this pipeline).

## PRIOR (2026-07-11) — spec 25 REVIEWED (Phase 1) + spec 25b SIGNED OFF (pipeline hang fix)

**Opus@high Phase-1 review of the spec-25 implementation (`76b2cd9`) is done.** The four flagged
concurrency concerns (max_staged=1 breaker determinism, semaphore balance, remaining/loop_finished/
all_done drain, `_default_max_staged` cog-gating) all verified **correct**. `pytest tests/test_cdse.py`
= 42 passed, ruff clean.

**One real defect found (not previously flagged):** an unhandled exception in a completion callback
leaks `remaining`/`sem_staged` → `download()` hangs forever on `all_done.wait()` (finally unreachable).
Triggers: (1) **BrokenProcessPool** — a convert worker segfaults (GDAL on a bad granule) or is
OOM-killed → `cfut.result()` / `pool.submit()` raise before release+finalize; `add_done_callback`
swallows the exception so the drain never completes. (2) `catalog.append` (parquet flush) raising
under the lock in `_finalize`, before the `remaining` decrement. Tests miss it (injected fake
executors never break). This is exactly the silent-hang failure mode spec 26's "safe run" premise is
meant to exclude, so it's fixed **first**.

**→ `specs/25b-pipeline-exception-safety.md` is SIGNED OFF (2026-07-11), C1–C6 as recommended.** Fix =
make `_on_transfer_done`/`_on_convert_done`/`_finalize` exception-safe so every submitted item
finalizes once and every permit releases once, with `remaining`/`sem_staged` moved off any fallible
call (pool submit, process result, parquet write); add additive `DownloadResult.pool_broken` (clean
submit-loop stop on a dead pool; `download_resume` retries with a fresh pool, no cooldown);
`"PoolBroken"` reason is breaker-neutral (like `ConvertError`); move the catalog flush off the lock;
no-hang tests via a watchdog thread + `join(timeout)` (no pytest-timeout dep).

**Next step: implement spec 25b in a fresh Sonnet@medium session** (user runs `/handoff`, `/model
sonnet` + `/effort medium`, points it at `specs/25b-pipeline-exception-safety.md`). Claude (Opus) did
NOT implement — Opus reviews/specs, Sonnet implements. After 25b lands + review, proceed to **spec 26**
(safe runner + measured confirm-run).

## PRIOR (2026-07-11) — spec 25 IMPLEMENTED (download/jp2→COG process-pool redesign)

**Implemented in a Sonnet@medium session** against the signed-off spec (contained to
`sources/cdse.py` + `config.py`). `pytest -q` all green (188 passed, 1 skipped) and `ruff check
src/ tests/` clean; **no network run** (per CLAUDE.md — that's spec 26's job). Docs updated:
`CHANGES.md` (new top entry), `TODO.md` (item (b) marked DONE), `specs/14-cog-on-download.md`
(pointer updated), `config.py` comments.

**What landed:** `_transfer_and_convert` replaced by `_transfer_one` (thread stage, fail-fast
retry, writes to `dst+".src.jp2"` when `needs_convert`) + `_convert_one` (top-level/picklable
process stage, `to_cog` + staging cleanup in `finally`); `_download_one` kept as the sequential
wrapper (its direct-call tests pass unchanged) but `download()` no longer calls it — it drives the
A2 pipeline: a `MAX_CONCURRENT_S3`-wide transfer `ThreadPoolExecutor` + a lazily-created
`MAX_CONVERT_PROCS`-wide `ProcessPoolExecutor` (spawn), chained via `add_done_callback`, bounded by
a `sem_staged` `BoundedSemaphore`. New `config.py` constants `MAX_CONVERT_PROCS`,
`STAGING_DISK_FRACTION`, `STAGING_ITEM_GB`; new `cdse._default_max_staged` (disk-aware sizing) and
`cdse._make_convert_pool` (the lazy-pool factory seam tests monkeypatch). Circuit breaker rewritten
to streaming/transfer-failures-only semantics; `chunksize` repurposed to catalog-flush cadence only.
New `download`/`download_resume` kwargs `max_convert_procs`/`max_staged`/`convert_executor` (all
defaulted, backward-compatible). Test suite: 5 unchanged regression tests still pass, 1 rewritten
(`test_circuit_breaker_trips_and_stops_early`, now forces determinism via `max_staged=1`), 15 new
tests (`_transfer_one` × 5, `_convert_one` × 2, cog=True pipeline via injected `_SyncExecutor`,
backpressure bound via `_BlockingConvertExecutor`, lazy-pool × 2, `_default_max_staged`).

**Next step: spec 26** (safe runner — `--dry-run`/`--stop-file`/progress + the measured
transfer-vs-convert-split confirm-run over a real CDSE download). That is the first real network
exercise of this pipeline; not run yet.

## PRIOR (2026-07-11) — spec 25 SIGNED OFF (download/jp2→COG redesign) — ready to implement

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
