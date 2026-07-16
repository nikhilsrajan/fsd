# Spec 31 — P1 Azure storage seam (adlfs + `/vsiadls/`, config-not-code)

> **Status: DRAFT — awaiting sign-off.** Opus@high (probe → interview → spec). This is the
> **Azure realization of spec 10 Seam 1**: the same fsd pipeline, all file I/O routed to the
> `rise` ADLS Gen2 blob over the VPN, chosen by URL scheme + config — **no Azure code on any
> hot path, no lock-in**. The exact same wiring runs unchanged on a `rise` Batch/AML node under
> a managed identity at P4 (the point of the seam).
>
> **De-risked by a green access probe** (`runbooks/31-p1-access-probe.md`, ran 2026-07-15,
> `"pass": true`): the user's *personal* identity has **Storage Blob Data Contributor**; **adlfs
> `DefaultAzureCredential` round-trips**; **GDAL 3.10.3 opens the object via both `/vsiadls/` and
> `/vsiaz/`**. So every seam this spec relies on is already proven end to end. Concrete `rise`
> values live **only** in `../P1_AZURE_SETUP.md` (workspace root, uncommitted) — **never under
> `fsd/`** (public MIT repo); this spec and its runbook use **placeholders only**.
>
> **Interview decisions locked (2026-07-16), all as recommended:**
> - **D1 — canonical URL = fully-qualified `abfss://`** (`abfss://<fs>@<account>.dfs.core.windows.net/<path>`).
>   Self-describing; the `/vsiadls/` translation is a deterministic host→account string rewrite
>   needing no ambient config. The account name lands in catalog rows — fine (artifacts, not the repo).
> - **D2 — raster pixel reads STREAM via GDAL `/vsiadls/`** + a refreshed `AZURE_STORAGE_ACCESS_TOKEN`
>   (range-reads only the COG blocks the crop window needs; the P4 Batch-node behavior we want).
>   A token provider refreshes so a long build outlives the ~1 h Entra token.
> - **D3 — the P1 exit demo is a real CDSE download straight to blob** (transfer S3→blob + COG →
>   blob), then a datacube build reading that blob. Realized as **stage-jp2-local → convert-local →
>   put-COG-to-blob** so GDAL never *writes* `/vsiadls/` (no write-token / subprocess-token wiring).
>   The runbook uses a **tiny 1-MGRS slice** (~7 granules, spec-26 scale) — the point is the seam,
>   not scale.
> - **D4 — `storage=` normalizes to ENV VARS.** `fsd.storage` builds the fsspec filesystem +
>   `DefaultAzureCredential` from env, so every Snakemake subprocess (and a Batch node) reconstructs
>   it identically — **no live credential object crosses a process boundary**. Same idiom `task.py`
>   already uses for `FSD_WRITE_TIMINGS`.
>
> **RETARGETED to Phase 2 (2026-07-16, spec 32 sign-off).** The plan pivoted to a two-phase,
> MPC-first approach (`specs/32-mpc-source-baseline-harmonization.md`): Phase 1 is MPC (local,
> already-COG, no conversion); this spec is now **Phase 2** (Azure at scale). Its **§5
> "Download straight to blob — stage-local-convert-put (D3)" is DELETED** — that whole
> CDSE-jp2→COG→blob dance is exactly the problem MPC (already-COG on Azure) removes. Not yet
> rewritten to reflect that (a future spec-31-revision session's job); flagged here so nobody
> implements §5 as drafted. The storage-seam mechanics elsewhere in this spec (fsspec-native
> config, `to_vsi`, one `rio_open` wrapper, `DefaultAzureCredential` for `rise` writes) still
> stand. Still DRAFT, not signed off.
>
> **Spec-first (spec 24):** this session writes the spec only. Implementation lands in a
> **Sonnet@medium** session against the signed-off spec. The credentialed/networked demo is a
> **runbook** the *user* runs (Claude never runs adlfs/az/CDSE), pasting back `_result.json`.
>
> **Cross-checked against external docs (2026-07-16, cited in "Best-practice alignment" below).**
> Two findings simplified the draft: adlfs **auto-resolves `DefaultAzureCredential`** from just
> `{account_name, anon:False}` (no credential object to construct/pass), and fsspec ships a
> **native per-protocol config seam** (`FSSPEC_{PROTOCOL}` env / `fsspec.config.conf`) that is
> inherited by subprocesses — i.e. D4's "env-based, subprocess-safe backend" is a *library
> feature*, not something fsd must hand-roll. The design below uses those instead of a bespoke
> registry; D4's intent is unchanged.

## Motivation

fsd's real end goal is download + datacube + inference on **Azure Batch at scale without cloud
lock-in** (ROADMAP; spec 10). Spec 10 defined *seams*; it shipped no Azure code. P1 is the first
time we actually flip the storage seam to Azure and prove the whole download→datacube→flatten core
runs against the `rise` blob — with the switch being **config, not a code change**, and with the
laptop-over-VPN path being byte-for-byte what a Batch node does later (only the identity source
differs: az-login token now, node managed identity at P4).

Two facts about the codebase force the shape of this spec:

1. **The datacube build runs in a *subprocess*.** The runner seam dispatches
   `python -m fsd.workflows.task ...` under Snakemake (and Azure Batch later). `task.py` already
   reads its optional config from **env vars** (`FSD_WRITE_TIMINGS`, `FSD_WRITE_READ_LOG`) precisely
   because "the harness can enable them without any runner/Snakefile plumbing." A live
   `DefaultAzureCredential()` object cannot cross that boundary → **the backend must be
   reconstructable from inherited env** (D4).
2. **~94 `fs.<fn>` call sites, none thread a destination `storage_options` today.** Per-call
   threading is a non-starter; the backend must be resolved *inside* `fsd.storage` from a
   **scheme-keyed registry** built once per process. All 94 sites stay untouched.

`storage=` already exists as a **pinned-but-rejected** seam on every verb (`_check_local_seams` →
`"non-local storage not supported in P0 (local only; blob lands in P1)"`). P1's job is to give it
meaning, not to change the API.

## Scope

**In (P1 core pipeline on blob):** `download` (CDSE S3 → blob COGs + catalog on blob) →
`create_training_data`/datacube build (reads blob COGs via `/vsiadls/`, writes `catalog.parquet`,
`datacube.npy`, `metadata.pickle.npy` to blob) → `flatten` (reads/writes blob). Plus the config
seam, the URL/VSI translation, the token provider, the URL-safety audit, and the demo runbook.

**Out (deferred, name them):**
- **Inference / serving on blob** (run_inference COG outputs, STAC export) — P4/P5; keep them
  local for now. P1 exit criterion is a *datacube build*, not inference.
- **Azure Batch/AML dispatch** (the runner seam) — P2/P4; parked (Batch-vs-AML fork noted in
  PROGRESS). P1 uses the **local** Snakemake runner, just with blob storage.
- **S3↔blob `transfer()` as a user-facing verb** beyond what the CDSE download path already needs.
- **rslearn Plan B/C** — orthogonal, parked.

## Design

### 1. Config seam — fsspec-native per-protocol config (D4, improved)

**The adlfs backend is pure configuration — no bespoke registry, no credential object.** Two
library facts (cited below) collapse what the draft hand-rolled:

- adlfs, given only `account_name` + `anon=False` and **no** credential, **auto-resolves
  `DefaultAzureCredential`** — the recommended adlfs pattern, and the one that runs unchanged on a
  Batch node (managed identity) at P4.
- fsspec has a **native per-protocol default-`storage_options` system**: values in
  `fsspec.config.conf[<protocol>]`, sourced from `FSSPEC_{PROTOCOL}` (a JSON dict) or
  `FSSPEC_{PROTOCOL}_{KWARG}` env vars (and `~/.config/fsspec/*.json`), are merged into **every**
  filesystem instantiation *unless the caller passes the kwarg explicitly*. Precedence:
  explicit kwargs > env/`conf` > files.

So the backend config is just:

```
FSSPEC_ABFSS_ACCOUNT_NAME=<account>      # (+ the abfs / az protocol strings adlfs also registers)
FSSPEC_ABFSS_ANON=false                  # adlfs then builds DefaultAzureCredential itself
```

(values are JSON-serializable strings — nothing non-picklable, so it crosses the subprocess boundary
natively.)

- **All 94 `fs.<fn>` sites stay untouched.** `fs._fs_and_path` → `fsspec.core.url_to_fs` already
  applies `fsspec.config.conf` at instantiation; an `abfss://…` URL now resolves against a
  credentialed adlfs filesystem with **no fsd code in the path**. The per-call `storage_options`
  fsd *does* pass (CDSE S3 source keys) are explicit kwargs, so they still win — no conflict.
- **Subprocess-safety is native, not hand-rolled.** `FSSPEC_*` env vars are inherited by the
  `subprocess.Popen(... "-m","fsd.workflows.task" ...)` children (and by a Batch task at P4), and
  fsspec re-reads them at import in each process — exactly the property D4 wanted, delivered by the
  library. This supersedes the draft's `FSD_STORAGE_BACKEND`/`FSD_AZURE_ACCOUNT` + custom
  `resolve_storage_options` registry (deleted).
- **`storage=` on the verbs is the thin ergonomic front door + preflight**, not a new subsystem:
  - it **relaxes `_check_local_seams`** to accept `storage="azure"` / `{"backend":"azure",…}`
    alongside `None`/local (Batch runner still rejected — P2);
  - as a convenience it **sets the `FSSPEC_*` env** for the run *and* writes `fsspec.config.conf`
    directly (⚠ fsspec loads env **at import time**, so mutating `os.environ` after import does not
    re-read in the *current* process — set both; children inherit the env and re-read on their own
    import). Equivalently the user just `export`s the `FSSPEC_*` vars in the runbook (true
    config-not-code) and `storage="azure"` is a pure assertion they're set.
- **Most routing is already scheme-driven.** Because the user passes `abfss://…` dst/export
  folders and the catalog then stores `abfss://…` band `filepath`s, artifacts are emitted to blob
  and read back from blob **by URL scheme alone** — `storage=` does not have to thread a backend
  through the call tree. This is the cleanest possible realization of spec 10's "config, not code."
- **No secret anywhere.** Keys are disabled on `strisewesteurope`; adlfs's `DefaultAzureCredential`
  uses the az-login token (laptop) or node identity (Batch). Nothing key/SAS to leak.

### 2. Canonical URL scheme + `/vsiadls/` translation (D1)

- fsd **emits and stores** fully-qualified `abfss://<fs>@<account>.dfs.core.windows.net/<path>`
  when the backend is azure (the catalog `filepath` column, datacube artifact paths, dst folders).
  adlfs opens these directly (it parses the account from the host); the account travels with the
  path, so nothing downstream needs ambient config to know where a file lives.
- **One translator, `fsd.storage.to_vsi(url) -> str`** (deterministic, no I/O):
  - `abfss://<fs>@<account>.dfs.core.windows.net/<path>` → `/vsiadls/<fs>/<path>`
  - a plain local path / `file://` → the local path unchanged (passthrough).
  - `az://<fs>/<path>` accepted as an alias → `/vsiadls/<fs>/<path>` (account comes from env then).
  Canonical is `/vsiadls/` (ADLS Gen2 dfs endpoint, proven); `/vsiaz/` is a documented fallback,
  not emitted.
- Round-trip note for the audit: `abfss://…` must survive `os.path.join`/`basename`/`dirname`
  (see §6) — the `<fs>@<account>.dfs…` host has an `@` and dots but no back-slashes, so posix
  `os.path.join(url, "x")` yields a correct `…/x`. `os.path.exists`/`os.makedirs` on such a URL
  do **not** work and must already be routed through `fs.*` (audit confirms).

### 3. adlfs reads/writes — catalog / `datacube.npy` / parquet / flatten (proven)

No new code beyond §1: once the registry supplies
`{account_name, anon:False, credential:DefaultAzureCredential()}`, the existing
`fs.write_parquet` / `fs.read_parquet` / `fs.save_npy` / `fs.load_npy` / `fs.exists` /
`fs.makedirs` / `fs.open` / `fs.rm` calls work against `abfss://` unchanged — the probe's
`adlfs_roundtrip` step proved the round-trip. The credential object refreshes its own token, so
long builds are fine on the adlfs path. This is the bulk of "all I/O on blob" and it is essentially
free once §1 lands.

### 4. GDAL `/vsiadls/` raster pixel reads + token refresh (D2)

The documented storage-seam exception (raster pixels go through GDAL VSI, not fsspec) becomes real.
GDAL's `AZURE_STORAGE_ACCESS_TOKEN` is a **static bearer token GDAL does not refresh** — the caller
owns its lifecycle (cited below) — so fsd sets a fresh one per open. This is *not* extra machinery:
`DefaultAzureCredential.get_token(...)` **already caches and auto-refreshes internally** (thread-safe
MSAL cache), so "get a token right before each open" is cheap and always-valid — **no bespoke
refresh-margin logic needed** (the draft's hand-rolled margin is deleted).

- **`fsd.raster.rio_open(path, mode="r", **kw)`** — a thin wrapper replacing bare `rasterio.open`
  in the **pixel-read modules** (`raster/images.py`, `raster/cog.py`, `catalog/stac.py`). It:
  1. is a **plain passthrough** to `rasterio.open(path, mode, **kw)` for local paths — zero behavior
     change to every existing local read/write (the regression-safety hinge);
  2. for an `abfss://`/`az://` source: `to_vsi(path)`→`/vsiadls/…`, and — because the account is in
     the fully-qualified URL host (D1) — extracts `AZURE_STORAGE_ACCOUNT` from the URL itself, then
     opens inside `rasterio.Env(AZURE_STORAGE_ACCESS_TOKEN=<token()>, AZURE_STORAGE_ACCOUNT=<acct>)`.
     No ambient backend config is consulted; the URL carries everything.
- **Token — `fsd.storage.azure.storage_token()`**: `credential.get_token("https://storage.azure.com/.default")`
  on a **single, module-cached `DefaultAzureCredential`** (reusing one instance is the documented
  best practice — it shares the token cache and avoids Entra 429 throttling). Returns `.token`; the
  SDK handles caching + refresh, so a multi-hour streaming build stays valid. **P4 note:** on a
  Batch/AML node GDAL can instead use `AZURE_IMDS_*` / the node managed identity directly (GDAL's
  own auth chain), needing no token env at all — document both realizations.
- **Writes stay local (D3, §5)** — `rio_open(..., "w")` is only ever called on local paths in P1,
  so we never need GDAL to *write* `/vsiadls/`. `to_vsi` on a local path is a passthrough, so
  `mode="w"` on a remote path is out of scope (assert/guard it rather than silently trying).

### 5. Download straight to blob — stage-local-convert-put (D3)

`api.download(dst_folderpath="abfss://…")` must land final **COGs + `catalog.parquet` on blob**.
The spec-25 transfer/convert pipeline changes only in *where staging happens* when the dst is remote:

- **`_transfer_one`** (thread): when `not _is_local_path(dst_path)` **and** `needs_convert`, stage
  the JP2 to a **local scratch** sibling (a temp dir on the node), not to `dst_path + ".src.jp2"`
  on blob. When `cog=False` or a sidecar (MTD xml, `needs_convert=False`), `fs.transfer` streams
  S3→blob **directly** (transfer is already cross-filesystem; the probe/`transfer()` docstring
  cover this). The idempotent skip check (`fs.exists(dst_path) and fs.size(dst_path) > 0`) works on
  blob via adlfs (`exists`/`size`), so **resume still works**.
- **`_convert_one`** (process): `to_cog(local_jp2, local_cog)` — **local→local**, GDAL untouched by
  Azure — then **`fs.put(local_cog, dst_path)`** uploads the finished COG to blob and the `finally`
  cleans up *both* local temps. A crash leaves at most local scratch (self-healing on resume), never
  a half-written blob object (`put` via `put_file` is effectively atomic at our granularity;
  document if adlfs needs a `.part`+rename like `transfer` does — mirror that pattern if so).
- **Local scratch root**: sized/located like the existing spec-25 staging (a node-local temp dir);
  add a small `config` knob if needed. The datacube build (§4) then reads the resulting blob COGs
  by *streaming* — it does **not** re-download them.

This keeps the "new hard problem" (COG-write-to-blob) out of P1 while still delivering a genuine
CDSE-download-to-blob. `download_resume` is unchanged (it just re-drives `download`).

### 6. URL-safety audit (spec 10 obligation #3 + the seam guard)

Blob paths are URLs; several spots may still assume local. A required audit pass (grep-guided,
fix what breaks):

- **`os.path.*` on paths that may be URLs** — `os.path.join` is tolerable (posix, §2), but any
  `os.path.exists` / `os.makedirs` / `os.path.isfile` / `open(` on a maybe-remote path must go
  through `fs.*`. Known suspects: `datacube/builder.py` (`local_folderpath`, `os.path.join` on
  catalog rows), `workflows/create_datacube.py`, `api._merge_outputs`. Inference/serving paths are
  out of P1 scope but note any found.
- **Re-run spec 10's grep/lint guard**: no `open(` / `np.save(` / `gpd.read_*(` / `rasterio.open(`
  on a raw path **outside `fsd.storage` and the documented `fsd.raster` VSI exception**. `rio_open`
  (§4) is the sanctioned raster exception; everything else must be `fs.*`.
- `gpd.read_file(shapefilepath)` in `task.py`/`_as_gdf` reads **local** ROI geometries (test inputs
  under `shapefiles/`), not pipeline artifacts — leave local, but note it (a future ROI-on-blob
  item, not P1).

### 7. Packaging

Add **`azure-identity`** to the `[azure]` extra in `pyproject.toml` (currently just `adlfs`), so
`DefaultAzureCredential` is available whenever the azure backend is selected. `.venv` stays lean;
Azure remains opt-in (`pip install -e ".[dev,azure]"`), mirroring `[grid]`/`[titiler]`/`[serving]`.

## Tests (pytest — synthetic/local only; no credentials, no network)

The credentialed adlfs round-trip and the real download are **runbook** territory (below). pytest
covers the pure logic:

- **`to_vsi`** — `abfss://fs@acct.dfs.core.windows.net/a/b.tif` → `/vsiadls/fs/a/b.tif`; local
  passthrough; `az://` alias; account correctly extractable from the host; malformed URL raises.
- **`storage=` config** — a verb called with `storage={"backend":"azure","account":"x"}` sets the
  `FSSPEC_*` env **and** `fsspec.config.conf` (scoped/restored in the test); `storage="local"`/`None`
  leaves them unset; a bad backend raises in `_check_local_seams`; `runner!="local"` still rejected.
- **token** — with a **mock `DefaultAzureCredential`**, `storage_token()` reuses **one** cached
  credential instance across calls (assert single construction) and returns `.token`; no network,
  no bespoke clock/margin (we rely on the SDK's own cache).
- **`rio_open` routing** — with a **mock `rasterio.open`**, a local path is a straight passthrough
  (no Env, no translation); an `abfss://` path translates to `/vsiadls/` and opens under an Env
  carrying the token + the account **parsed from the URL host**. `mode="w"` on a remote path
  guards/raises.
- **round-trip on `memory://`** — the registry/seam plumbs a non-local fsspec backend end to end
  without Azure (proves scheme-routing, not credentials): write+read a parquet/npy over `memory://`.
- **download stage-local-put** — with injected sync executors + a `memory://` (or tmp) "remote"
  dst, assert a `needs_convert` band stages to **local** scratch, converts local, and the finished
  COG is `put` to the remote dst (mock/spy `fs.put`); `cog=False` transfers straight to remote;
  the idempotent skip fires on a pre-existing remote object. No CDSE, no GDAL-on-blob.
- **regression:** the full existing suite stays green (local paths are untouched — `rio_open`
  passthrough, registry empty by default). Target: `pytest -q` all green + the new tests; `ruff`
  clean.

## The demo — `runbooks/31-p1-datacube-on-blob.md` (Claude writes it; the USER runs it)

The P1 exit proof. Placeholders only in the repo; the user pastes concrete `rise` values as env
vars from `../P1_AZURE_SETUP.md` §3. Shape (self-contained `expected` block per spec 24/26):

1. **Setup** — VPN up; `az login` done; `pip install -e ".[dev,azure]"`;
   `export FSD_STORAGE_BACKEND=azure FSD_AZURE_ACCOUNT=<account>`; a fresh `abfss://…/p1-demo/`
   prefix.
2. **Download a tiny slice to blob** — `fsd.download`/`download_cli` for a **1-MGRS Austria slice**
   (~7 granules, spec-26 scale, `--dst abfss://…/p1-demo/imagery/`): proves S3→blob transfer +
   local-convert + COG `put`, `catalog.parquet` written on blob. `_result.json`: `status=ok`,
   `failed=0`, COGs+catalog exist on blob (adlfs `ls`).
3. **Build a datacube on blob** — `create_training_data` (or `task`) over a couple of grid cells
   with all paths `abfss://…`: proves `/vsiadls/` streaming reads + `datacube.npy` /
   `metadata.pickle.npy` / flatten writes on blob. `_result.json`: artifacts exist on blob, shapes
   sane, timestamps axis correct.
4. **Sanity read-back** — load one `datacube.npy` back from blob (`fs.load_npy`) and one COG via
   `/vsiadls/` locally; assert non-empty / expected dtype. Optional: pull one COG for a QGIS eyeball
   (visual-validation principle).

Success = all `_result.json` green → **P1 storage seam proven end to end**: the fsd core pipeline
ran with every byte on the `rise` blob, switched on by config alone. The runbook notes the
connection cost (a few GB over VPN — not hotspot-friendly; the *seam* is the point, not scale) and
the token-lifetime check (step 3 should comfortably finish inside one token; if it ever doesn't,
the provider's refresh is what covers it).

## Deliverables (for the Sonnet@medium implement session)

- `fsd/storage/azure.py` (new) — the single module-cached `DefaultAzureCredential` + `storage_token()`
  (for the GDAL VSI path) + `to_vsi()` + the `storage=`→`FSSPEC_*`/`fsspec.config.conf` helper.
  **No bespoke storage-options registry** — adlfs + fsspec-native config do that (§1).
- `fsd/storage/fs.py` — export `to_vsi` (re-export from `azure.py`); otherwise unchanged (the 94
  sites route via `fsspec.config.conf`, no `_fs_and_path` edit needed).
- `fsd/raster/__init__.py` (or `raster/vsi.py`) — `rio_open`; swap bare `rasterio.open` in
  `raster/images.py`, `raster/cog.py`, `catalog/stac.py` (pixel-read sites only).
- `fsd/api.py` — `storage=` sets `FSSPEC_*` env + `fsspec.config.conf`; relax `_check_local_seams`.
- `fsd/sources/cdse.py` — `_transfer_one`/`_convert_one` stage-local-convert-put when dst is remote.
- `fsd/pyproject.toml` — `azure-identity` in `[azure]`.
- URL-safety audit fixes (§6).
- `fsd/runbooks/31-p1-datacube-on-blob.md` (placeholders only).
- Tests per the Tests section.
- Living docs: `CHANGES.md` (behavior kept-but-changed: `storage=` now meaningful; download-to-blob
  staging), `specs/10` pointer (→ 31 realizes Seam 1), `TODO.md` (inference/serving-on-blob,
  ROI-geometry-on-blob, Batch runner as explicit follow-ons), `RECIPES.md` (the env-vars +
  `abfss://` recipe), `PROGRESS.md`, memory `[[fsd-status]]`.

## Open items to confirm at sign-off / flag for the implementer

- **Exact fsspec protocol strings** — set `FSSPEC_*` for whichever protocol keys adlfs actually
  registers for the emitted scheme (`abfss`, and likely `abfs`/`az`); the implementer confirms the
  registered names and sets config for each so `url_to_fs("abfss://…")` picks up the credential.
- **fsspec import-time vs runtime** — env is read at fsspec import, so `storage=` must set **both**
  `os.environ` (for children) **and** `fsspec.config.conf` (for the already-imported parent). Confirm
  and lock this in a test.
- **adlfs write atomicity** — does `fs.put`/`put_file` to ADLS Gen2 need the `.part`+rename dance
  `transfer()` uses (so a killed upload never leaves a truncated blob), or is a single `put_file`
  atomic enough at band granularity? `/vsiadls/` advertises atomic rename; adlfs is separate —
  mirror `transfer`'s pattern if in doubt (safe default).
- **Local scratch location for download-to-blob** — reuse the spec-25 staging dir / disk-fraction
  cap, or a dedicated `FSD_SCRATCH_DIR`? (Batch nodes have a task working dir; keep it configurable.)
- **`_check_local_seams` shape** — accept `storage="azure"` string *and* the dict form, or dict
  only? (Recommend: accept both; string reads account from the `FSSPEC_*` env / a passed `account`.)

## Best-practice alignment (external sources, checked 2026-07-16)

Each external practice and how spec 31 conforms:

- **Reuse one `DefaultAzureCredential`; the SDK caches + auto-refreshes tokens; reuse avoids Entra
  429 throttling.** → §1 (adlfs makes its own, once) and §4 (one module-cached instance for the
  GDAL token; `get_token` per open is cheap and always-valid). The draft's hand-rolled refresh
  margin was removed as redundant with the SDK cache.
  — Microsoft Learn, *Authentication best practices with the Azure Identity library*; Azure SDK
  *Token caching in the Azure Identity client library*.
- **adlfs: prefer `anon=False` + `account_name` and let it resolve `DefaultAzureCredential`
  automatically** — works unchanged across laptop / CI / cloud. → §1 (no credential object passed;
  P4 managed-identity parity). — adlfs README / API docs.
- **fsspec: set per-protocol default `storage_options` via `fsspec.config.conf` / `FSSPEC_{PROTOCOL}`
  env / `~/.config/fsspec/*.json`; merged at instantiation unless the caller passes the kwarg;
  JSON-serializable values only.** → §1 (the backend is configuration, inherited by subprocesses;
  our explicit CDSE-S3 kwargs still win). — fsspec *Features / Configuration* docs.
- **GDAL `/vsiadls/` is the ADLS-Gen2 (HNS) handler (true dirs, atomic rename) vs `/vsiaz/` for flat
  blob; `AZURE_STORAGE_ACCESS_TOKEN` is a static bearer token GDAL does not auto-refresh; on Azure
  compute use `AZURE_IMDS_*` / managed identity.** → D1/§2 canonical `/vsiadls/`; §4 caller-set
  fresh token per open + the P4 IMDS note. — GDAL *Virtual File Systems* docs.
- **Token resource/scope for Storage = `https://storage.azure.com/`** (`/.default` for the SDK
  `get_token`). → §4. — Microsoft Learn, *Acquire a token for authorization* (Azure Storage).

Sources:
- https://learn.microsoft.com/en-us/dotnet/azure/sdk/authentication/best-practices
- https://github.com/Azure/azure-sdk-for-net/blob/main/sdk/identity/Azure.Identity/samples/TokenCache.md
- https://fsspec.github.io/adlfs/
- https://filesystem-spec.readthedocs.io/en/latest/features.html
- https://gdal.org/user/virtual_file_systems.html
- https://learn.microsoft.com/en-us/azure/storage/common/identity-library-acquire-token
