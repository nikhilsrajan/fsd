# Spec 31 — P1 Azure storage seam (adlfs + `/vsiadls/`, config-not-code)

> **Status: SIGNED OFF + PIVOTED (2026-07-17) — ready for a Sonnet@medium implementation of the
> compute seam only.** Drafted by Opus@high (probe → interview → spec, commit `030f6ac` — trailer
> verified `Claude Opus 4.8`, per spec 33's F1 lesson that only the trailer is ground truth);
> **independently reviewed, revised, and signed off by a separate Opus@high session** (2026-07-17)
> that did not write the draft; **then narrowed the same day by a roadmap pivot** — download-to-blob
> is now the *next* spec's job (ingest/normalization contract), and this spec proves only the
> **compute seam** against hand-staged blob data (see the ⚠️ pivot banner below). This is the
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
> ## ⚠️ READ FIRST — ROADMAP PIVOT (2026-07-17): download-to-blob is OUT; this is a compute-seam spec
>
> After sign-off, the user reframed the roadmap: **the downloader normalizes, the datacube builder
> does not** (see the top of `PROGRESS.md`). Consequence for this spec:
> - **§5 (download-to-blob) is SUSPENDED** into the next spec (the ingest/normalization contract).
>   Neither `mpc.py` nor `cdse.py` is touched; both keep their local-only guards.
> - **The blob data is staged BY HAND** — `runbooks/31-p1-upload-slice.md` **ran green 2026-07-17**
>   (20 granules / 2.27 GB on `rise`; `/vsiadls/` read of an uploaded COG confirmed **D1 + D2/§4 on
>   real data before any code was written**). This spec now proves only the **compute seam** (build +
>   flatten reading/writing blob), which is strictly better: it is independent of the ingest design.
> - **D3 below is therefore OBSOLETE as written** (it describes a download demo). The live demo is
>   §"The demo" — a *datacube-on-blob build*, no download. D1/D2/D4 stand unchanged.
>
> Everything from here to "RETARGET RESOLVED" is the **pre-pivot sign-off record**, kept for
> provenance; where D3 / §5 / "copy arm" language appears, the pivot above overrides it.
>
> **Interview decisions locked (2026-07-16), all as recommended:**
> - **D1 — canonical URL = fully-qualified `abfss://`** (`abfss://<fs>@<account>.dfs.core.windows.net/<path>`).
>   Self-describing; the `/vsiadls/` translation is a deterministic host→account string rewrite
>   needing no ambient config. The account name lands in catalog rows — fine (artifacts, not the repo).
>   **✅ confirmed on real blob artifacts by the 2026-07-17 upload.**
> - **D2 — raster pixel reads STREAM via GDAL `/vsiadls/`** + a refreshed `AZURE_STORAGE_ACCESS_TOKEN`
>   (range-reads only the COG blocks the crop window needs; the P4 Batch-node behavior we want).
>   A token provider refreshes so a long build outlives the ~1 h Entra token. **✅ the upload's
>   `/vsiadls/` read of an uploaded COG proved this end to end before any code.**
> - **D3 — ~~the P1 exit demo is a real download straight to blob~~ — OBSOLETE (see the pivot banner
>   above).** Download-to-blob moved to the ingest spec; the P1 demo is a datacube build over
>   hand-staged blob data. The invariant that mattered still holds trivially: **GDAL never writes
>   `/vsiadls/`** (P1 does no download and no convert at all).
> - **D4 — `storage=` normalizes to ENV VARS.** `fsd.storage` builds the fsspec filesystem +
>   `DefaultAzureCredential` from env, so every Snakemake subprocess (and a Batch node) reconstructs
>   it identically — **no live credential object crosses a process boundary**. Same idiom `task.py`
>   already uses for `FSD_WRITE_TIMINGS`.
>
> **RETARGET RESOLVED + SIGNED OFF (2026-07-17, Opus@high review session).** The 2026-07-16 spec-32
> sign-off retargeted this spec to **Phase 2** (MPC-first: Phase 1 is MPC local, already-COG, no
> conversion) and flagged its **§5 "stage-local-convert-put" as DELETED but did not rewrite it** —
> leaving the spec depending on a design it had deleted. **That rewrite is done here.** What changed
> at this review:
> - **§5 is now "MPC copy straight to blob"** — the CDSE jp2→COG→blob dance is gone (user decision,
>   2026-07-17). MPC assets are already COG, so download-to-blob is a **pure byte-copy**
>   (`fs.transfer`, already cross-backend + atomic). **CDSE-download-to-blob is dropped from P1** and
>   logged as a TODO.
> - **D2's `/vsiadls/` pixel reads stay in the demo** (user decision, 2026-07-17, TODO #31 fork scoped
>   *to the demo only*): the demo **copies MPC → `rise` blob, then streams from `rise`**. Streaming
>   MPC in place via `/vsicurl` would never exercise `/vsiadls/` — i.e. would not test D2/§4 at all.
>   The production stream-vs-copy question stays **TODO #31: measure, don't argue**, and this demo
>   makes the copy arm real so the measurement has something to compare against.
> - **§1/§3 de-staled** — the "registry + credential object" language the cross-validation had already
>   superseded is removed, and the fsspec protocol/config open items are **resolved by direct
>   verification against the installed libraries** (below).
> - **Demo band list pinned to `['B08','SCL']`** — closing the TODO #35 trap that broke runbook 32 v1.
>
> **Review findings that forced the above** (recorded so they are not re-derived): the drafted demo was
> **structurally impossible against our own code** — `sources/mpc.py:294` raises
> `"MPC source is local-only in Phase 1"` on a non-local `root_folderpath`, and `sources/cdse.py:645`
> raises when `cog=True` and the root is remote. **Neither source could download to blob**, while the
> one section that would have fixed it (§5) was marked deleted. This is the **spec-32 failure mode
> recurring verbatim** (a Tests/demo section that cannot run against the real call chain); it is the
> reason §5 below is written against the actual guard it must lift.
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
   threading is a non-starter; the backend must be resolved *below* those call sites, once per
   process, from inherited config. **fsspec does this natively** (§1) — `fs._fs_and_path` already
   delegates to `fsspec.core.url_to_fs`, which applies `fsspec.config.conf` at instantiation. All 94
   sites stay untouched, and fsd ships **no registry of its own**.

`storage=` already exists as a **pinned-but-rejected** seam on every verb (`_check_local_seams` →
`"non-local storage not supported in P0 (local only; blob lands in P1)"`). P1's job is to give it
meaning, not to change the API.

## Scope

**In (P1 core pipeline on blob):** `create_training_data`/datacube build **reading a blob catalog +
COGs via `/vsiadls/`** and writing `catalog.parquet` / `datacube.npy` / `metadata.pickle.npy` to
blob → `flatten` (reads/writes blob). Plus the config seam, the URL/VSI translation, the token
provider, the URL-safety audit, and the demo runbook. The blob data itself is **staged by hand**
(`runbooks/31-p1-upload-slice.md`, done) — this spec proves the *compute* seam, not ingest.

**Out (deferred, name them):**
- **ALL download-to-blob** (both MPC and CDSE) — **removed from P1 by the 2026-07-17 pivot.** Getting
  bytes onto blob is a *normalization* concern (CDSE=format, MPC=radiometry, ERA5=netCDF→COG), and
  designing it inside a storage-seam spec would bake in the source-specific split the pivot exists to
  remove. It becomes the **ingest/normalization contract spec** (the very next spec). Both `mpc.py`
  and `cdse.py` keep their local-only guards; P1's blob data is hand-staged instead. The suspended
  §5 MPC-copy design is archived in §5-ARCHIVE for that spec to draw on.
- **TODO #31's stream-vs-copy question** — untouched by this spec now (no download here at all).
  Stays "measure, don't argue" until at-scale Azure exists.
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

So the backend config is just **one env var**:

```
FSSPEC_ABFSS_ANON=false     # adlfs then builds DefaultAzureCredential itself
```

(values are JSON-serializable strings — nothing non-picklable, so it crosses the subprocess boundary
natively.)

**Verified directly against the installed libraries at the 2026-07-17 review** (`fsspec 2026.6.0`,
`adlfs 2026.5.0` in `.venv`) — these resolve the draft's two open items and shrink the config to the
single line above:

- **`AzureBlobFileSystem.protocol == ('abfs', 'az', 'abfss')`** — all three schemes are **one class**
  (`adl` is a *different*, legacy Gen1 class: `AzureDatalakeFileSystem` — do not configure it).
  `fsspec.config.apply_config` keys on **`cls.protocol`**, *not* on the URL's scheme, and merges
  every proto in that tuple. So **setting one key is enough and covers all three schemes**, and
  setting several is a **hazard**, not thoroughness: on conflicting values the tuple's **last**
  entry (`abfss`) silently wins. *Set only `FSSPEC_ABFSS_*`.*
- **`AzureBlobFileSystem._get_kwargs_from_urls("abfss://data@acct.dfs.core.windows.net/p/x.tif")` →
  `{'account_name': 'acct'}`** (and `_strip_protocol` → `data/p/x.tif`). URL-inferred kwargs reach
  `__init__` as **explicit** kwargs, and `apply_config` does `kw.update(**kwargs)` — **explicit beats
  conf**. So with D1's fully-qualified URLs the account **comes from the URL** and
  `FSSPEC_ABFSS_ACCOUNT_NAME` is **redundant** (and would lose to the URL anyway if they disagreed —
  the correct precedence: the self-describing URL wins). Only `anon` is load-bearing.
- **`anon` is worth setting explicitly even though `False` is the default.** adlfs's default is
  `anon=None` → it consults the **`AZURE_STORAGE_ANON` env var**, where *anything* other than
  `false/0/f` resolves to **True** (anonymous → our reads fail). `FSSPEC_ABFSS_ANON=false` is the
  guard against a stray ambient value; with it, adlfs "will use `DefaultAzureCredential` for
  authentication" (its own docstring).

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
  - as a convenience it **sets the `FSSPEC_ABFSS_*` env** for the run *and* writes `fsspec.config.conf`
    directly (⚠ fsspec loads env **at import time**, so mutating `os.environ` after import does not
    re-read in the *current* process — set both; children inherit the env and re-read on their own
    import). Equivalently the user just `export`s the `FSSPEC_*` vars in the runbook (true
    config-not-code) and `storage="azure"` is a pure assertion they're set.
- **Most routing is already scheme-driven.** Because the user passes `abfss://…` dst/export
  folders and the catalog then stores `abfss://…` band `filepath`s, artifacts are emitted to blob
  and read back from blob **by URL scheme alone** — `storage=` does not have to thread a backend
  through the call tree. This is the cleanest possible realization of spec 10's "config, not code."
- **No secret anywhere.** Account keys are disabled on the target storage account (see
  `../P1_AZURE_SETUP.md` §3 — Entra-only, no key/SAS exists); adlfs's `DefaultAzureCredential`
  uses the az-login token (laptop) or node identity (Batch). Nothing key/SAS to leak.

### 2. Canonical URL scheme + `/vsiadls/` translation (D1)

- fsd **emits and stores** fully-qualified `abfss://<fs>@<account>.dfs.core.windows.net/<path>`
  when the backend is azure (the catalog **`local_folderpath` column**, datacube artifact paths, dst
  folders). adlfs opens these directly (it parses the account from the host); the account travels
  with the path, so nothing downstream needs ambient config to know where a file lives.
  - ⚠ **Corrected 2026-07-17 (found during the hand-upload):** the draft said "the catalog
    `filepath` column". **There is no `filepath` column** — the catalog stores **`local_folderpath`**
    (+ a comma-joined `files`), and `builder.py:72` does `os.path.join(row["local_folderpath"], file)`
    to form each band path; `filepath` only exists *transiently* as `flatten_catalog`'s output. So it
    is `local_folderpath` that must hold the `abfss://` URL — which is exactly what
    `31_upload_slice.py` rewrote, and the green run confirms it flows through the build. The column
    name becoming a misnomer on blob is noted for the ingest spec (a rename is a catalog-format change,
    out of P1 scope).
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

**No new code at all beyond §1.** Once `FSSPEC_ABFSS_ANON=false` is set, an `abfss://…` URL resolves
through `fs._fs_and_path` → `fsspec.core.url_to_fs` to an adlfs filesystem that took its
`account_name` **from the URL host** and built its **own** `DefaultAzureCredential` — so the existing
`fs.write_parquet` / `fs.read_parquet` / `fs.save_npy` / `fs.load_npy` / `fs.exists` / `fs.makedirs` /
`fs.open` / `fs.rm` calls work against `abfss://` unchanged. The probe's `adlfs_roundtrip` step proved
the round-trip. adlfs's credential refreshes its own token, so long builds are fine on the adlfs path
(the GDAL path is the one needing §4's token care — GDAL, unlike the SDK, will not refresh).

> **Superseded (kept as a signpost, per CHANGES-style discipline):** the draft described a bespoke
> registry supplying `{account_name, anon:False, credential:DefaultAzureCredential()}`. There is **no
> registry and no credential object** — adlfs + fsspec-native config do both. Do not implement one.

This is the bulk of "all I/O on blob" and it is essentially free once §1 lands.

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
- **GDAL writes stay local (D3, §5)** — `rio_open(..., "w")` is only ever called on local paths in
  P1. With MPC the write path is a **byte-copy through `fs.transfer`**, so GDAL is not merely
  *unneeded* for writing `/vsiadls/` — it is **never invoked on the write path at all**. `to_vsi` on
  a local path is a passthrough, so `mode="w"` on a remote path is out of scope: **guard it with an
  explicit raise** rather than silently trying (a silent attempt would half-work and fail late).

### 5. ⛔ SUSPENDED (2026-07-17) — moved to the ingest/normalization contract spec

> **DO NOT IMPLEMENT §5. It is out of spec 31's scope as of the 2026-07-17 roadmap pivot.**
>
> **Why.** The user's argument (accepted, and verified against the code): the **downloader** should
> normalize, so the datacube builder sees one input contract regardless of source. Today
> `build_datacube` hardcodes `_apply_boa_offsets` + `apply_cloud_mask_scl` + `drop_bands(["SCL"])`
> + `REFERENCE_BAND="B08"` — it is an **S2 builder wearing a generic name** (TODO #35 is this same
> issue, filed as a one-off). Getting bytes onto blob is therefore **an ingest concern, not a
> storage-seam concern**, and designing it here would bake in the very split we are trying to remove.
>
> Note the irony this pivot corrects: §5's **original** shape (`stage-local → convert → put`) was
> right. The MPC pivot deleted it because "MPC is already COG" — but MPC only **moved** normalization
> from *format* (jp2→COG) to *radiometry* (baseline offset), and we put the radiometry in the builder.
> The ingest spec generalizes the original shape: **`stage → normalize → put`**, per source
> (CDSE = format, MPC = radiometry, ERA5 = netCDF→COG).
>
> **What replaces it in P1:** nothing — the seam is proven against **hand-uploaded** real data
> (`runbooks/31-p1-upload-slice.md`, **ran green 2026-07-17**), which is strictly better for this
> spec's purpose: it tests the seam *independently* of any ingest design. `sources/mpc.py`'s
> local-only guard (`mpc.py:294`) **stays**; `sources/cdse.py` stays untouched.
>
> The suspended design is preserved below and in git history for the ingest spec to draw on.

### 5-ARCHIVE (suspended, for the ingest spec's reference). MPC download straight to blob — pure byte-copy (D3)

`api.download(source="mpc", dst_folderpath="abfss://…")` must land **COGs + `catalog.parquet` on
blob**. Because **MPC assets are already COG**, this is a byte-copy — there is no conversion, no
staging, no scratch dir, and no GDAL involvement on the write path. The work is **lifting one guard**
and confirming the existing helpers are already URL-safe.

**The guard to lift.** `sources/mpc.py` currently opens `download()` with:

```python
if not _is_local_path(root_folderpath):
    raise ValueError("MPC source is local-only in Phase 1; ...")   # mpc.py:294
```

That guard *is* Phase 1's scope note (spec 32 §Scope), and Phase 2 is exactly what it deferred to.
**Delete it** (and the now-false "Local-only in Phase 1" clause in `download`'s docstring, which must
instead say: local or `abfss://`, chosen by the dst URL scheme).

**Why nothing else in that path needs to change** — each claim traced against the code, not assumed:

- **`fs.makedirs(root_folderpath, exist_ok=True)`** (`mpc.py:301`) — already goes through the storage
  seam; a no-op-ish `makedirs` on adlfs, and `_ensure_parent` swallows object-store dir semantics.
- **`_select_item_files`** (`mpc.py:194`) builds dsts with `os.path.join(root_folderpath, item.id)`
  then `f"{band}.tif"`. Per §2 this is **posix-safe on an `abfss://` URL** (the `fs@account.dfs…`
  host has `@` and dots but no backslashes), so it yields a correct `abfss://…/<item_id>/B08.tif`.
  **No change** — but the URL-safety audit (§6) must confirm it, and a test pins it.
- **`_transfer_one`** (`mpc.py:210`) is already **`fs.transfer(src_url, dst_path)`** + an idempotent
  skip on an existing non-empty dst. `fs.transfer` **streams between two fsspec filesystems** and is
  **atomic** (`.part` sidecar + `mv`) — its own docstring names "CDSE S3 → Azure Blob" as the case it
  was built for, and spec 32's runbook proved it streams **signed MPC HTTPS** cleanly (no `aiohttp`
  fallback needed). The skip check (`fs.exists`/`fs.size`) works on adlfs, so **resume still works**
  on blob.
  - ⚠ **The one thing to verify at the runbook, not to assume:** `transfer`'s atomicity rests on
    `dst_fs.mv(tmp, dpath)`, whose docstring says "atomic on a local fs (os.rename)". On **ADLS Gen2
    (HNS)** rename is a real atomic metadata operation (this is precisely what HNS buys, and why
    `/vsiadls/` advertises atomic rename) — but adlfs's `mv` implementing it as such is the assumption.
    If `mv` proves slow/absent on adlfs, `fs.put`-style direct write is the fallback; the demo's
    step-2 success (COGs present, non-zero, no `.part` leftovers) is what settles it.
- **Catalog rows carry `abfss://` filepaths automatically** — `_finalize_catalog_gdf` stores the dst
  paths it was given, so D1's fully-qualified URLs land in the catalog and the datacube build reads
  them back by scheme alone. This is the "config, not code" property doing the work.
- **`should_stop`, the thread pool, `MPC_MAX_CONCURRENT`** — untouched.

**Signed-URL lifetime (TODO #32).** MPC hrefs are SAS-signed. At demo scale (~2 granules × 2 bands,
seconds) expiry is a non-issue, which is exactly what TODO #32 records; a long Phase-2 copy would need
re-signing. **Not in scope here** — but the implementer must not "helpfully" add re-signing: it is a
separate, already-logged item.

**CDSE is untouched.** `cdse.download`'s `cog=True`-needs-local guard (`cdse.py:645`) **stays as is** —
CDSE-download-to-blob is dropped from P1 (§Scope) and logged as a TODO. Do not edit `sources/cdse.py`.

### 6. URL-safety audit (spec 10 obligation #3 + the seam guard)

Blob paths are URLs; several spots may still assume local. A required audit pass (grep-guided,
fix what breaks):

- **`os.path.*` on paths that may be URLs** — `os.path.join` is tolerable (posix, §2), but any
  `os.path.exists` / `os.makedirs` / `os.path.isfile` / `open(` on a maybe-remote path must go
  through `fs.*`. Known suspects: `datacube/builder.py` (`local_folderpath`, `os.path.join` on
  catalog rows), `workflows/create_datacube.py`, `api._merge_outputs`, and **`sources/mpc.py`
  `_select_item_files`** (§5 — now reached with a remote root for the first time). Inference/serving
  paths are out of P1 scope but note any found.
  - **Reviewer's head start (2026-07-17, grep-verified):** `datacube/builder.py` and `workflows/*.py`
    are **already clean** — a grep for `os.path.exists` / `os.makedirs` / bare `open(` across them
    returns **nothing** but `subprocess.Popen` in `runners.py`. The audit is therefore expected to be
    largely a **confirmation**, not a fix-fest; the live risks are the `rasterio.open` sites (§4) and
    `api.py`/`model/engine.py`'s inference writes, which are **out of P1 scope** — note them, don't
    fix them here.
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
  `FSSPEC_ABFSS_*` env **and** `fsspec.config.conf` (scoped/restored in the test — this test **must**
  clean up, since `fsspec.config.conf` is process-global and would leak into every later test);
  `storage="local"`/`None` leaves them unset; a bad backend raises in `_check_local_seams`;
  `runner!="local"` still rejected.
- **the config seam resolves as claimed (pins §1's verified facts so a library upgrade can't silently
  break them)** — `AzureBlobFileSystem.protocol` contains `abfss`; `apply_config(AzureBlobFileSystem,
  {}, {"abfss": {"anon": False}})` returns `anon=False` (i.e. one key covers the class); and
  `_get_kwargs_from_urls("abfss://fs@acct.dfs.core.windows.net/p/x.tif") == {"account_name": "acct"}`.
  Pure introspection — **no instantiation, no network, no credential** (constructing the filesystem
  would try to authenticate; these tests must not).
- **token** — with a **mock `DefaultAzureCredential`**, `storage_token()` reuses **one** cached
  credential instance across calls (assert single construction) and returns `.token`; no network,
  no bespoke clock/margin (we rely on the SDK's own cache).
- **`rio_open` routing** — with a **mock `rasterio.open`**, a local path is a straight passthrough
  (no Env, no translation); an `abfss://` path translates to `/vsiadls/` and opens under an Env
  carrying the token + the account **parsed from the URL host**. `mode="w"` on a remote path
  guards/raises.
- **round-trip on `memory://`** — the registry/seam plumbs a non-local fsspec backend end to end
  without Azure (proves scheme-routing, not credentials): write+read a parquet/npy over `memory://`.
- **`os.path.join` is URL-safe (the §2/§6 posix claim, pinned)** — a direct unit case that
  `os.path.join("abfss://fs@acct.dfs.core.windows.net/a", "b.tif")` yields
  `abfss://fs@acct.dfs.core.windows.net/a/b.tif` (the host has `@` and dots but no backslash, so
  posix join is correct). This is what `builder.py:72` relies on to build band paths from a blob
  `local_folderpath`; the hand-upload already proved it end to end (all 40 paths resolved), but a
  unit test pins it against a regression. **NB:** the download-to-remote test the draft listed here
  is **removed** — §5 is suspended (`mpc.download`'s local-only guard stays), so there is no
  guard-lift to test.
- **regression:** the full existing suite stays green (local paths are untouched — `rio_open`
  passthrough, registry empty by default). Target: `pytest -q` all green + the new tests; `ruff`
  clean.

## The demo — `runbooks/31-p1-datacube-on-blob.md` (Claude writes it; the USER runs it)

The P1 exit proof. Placeholders only in the repo; the user passes the concrete `rise` URL from
`../P1_AZURE_SETUP.md` §3 as an argument. Self-contained `expected` block per spec 24/26.

> **REVISED 2026-07-17 (roadmap pivot).** The drafted demo *downloaded* from MPC to blob — that is
> now the **ingest spec's** job (§5 suspended). **Step 1 already happened**: the data is on blob,
> put there by hand. So this demo is now **purely a seam proof**, which is what it should always
> have been: it tests "can the fsd pipeline run with every byte on `rise`" **independently of any
> ingest design**, so the ingest rewrite cannot invalidate it.

**Step 1 — DONE (2026-07-17), `runbooks/31-p1-upload-slice.md` ran GREEN (`"pass": true`).** Real
data is on the `rise` blob, uploaded by hand via `fs.put` — **no fsd code change was needed**
(`fs.put`/`fs.write_parquet` already route fsspec→adlfs; only `azure-identity` +
`FSSPEC_ABFSS_ANON=false`). What it established, measured not assumed:

- **20 granules / 40 files / 2.27 GB** on blob (T33UWP × Jul–Aug 2018 × `['B08','SCL']`), at
  **~13.4 MB/s** over VPN (170 s).
- **`catalog.parquet` on blob with all 20 rows' paths `abfss://…`** (`every_catalog_path_is_abfss`)
  → **D1 confirmed on real artifacts**.
- **`gdal_vsiadls_read_ok` + `gdal_sample_nonzero`** — GDAL read our own uploaded COG through
  `/vsiadls/` with a fresh `AZURE_STORAGE_ACCESS_TOKEN`, returning real `uint16` 256×256 pixels →
  **D2/§4 proven on real data *before any code was written for it***. This was the spec's riskiest
  claim; it is no longer a risk.
- Slice rationale: `s2grid=476da24` is **100% inside T33UWP** (verified), and a Jul 1–Sep 1 window
  gives a real **T=3** mosaic axis at `mosaic_days=30` — not the degenerate T=1 that runbook 32 v1
  tripped on. (⚠ **Corrected 2026-07-17, Opus review:** earlier drafts said "T=2"; that was an
  arithmetic slip — calendar windows tile `[startdate, enddate)` in `mosaic_days` steps anchored at
  `startdate`, so `ceil((Sep1−Jul1)/30) = ceil(62/30) = 3` windows, verified against
  `fsd.datacube.ops._calendar_windows`. The count is data-independent; the trailing window is emitted
  even if empty.)

**What remains for the demo run-book** (`runbooks/31-p1-datacube-on-blob.md`, written after the seam
lands):

1. **Setup** — VPN up; `az login`; `pip install -e ".[dev,azure]"` (**no `[mpc]`** — nothing is
   downloaded); `export FSSPEC_ABFSS_ANON=false` (**the only backend env var** — §1; the account
   comes from the URL, and `FSD_STORAGE_BACKEND`/`FSD_AZURE_ACCOUNT` **do not exist**).
2. **Build a datacube on blob** — `create_training_data` (or `workflows.task`) pointed at the
   **uploaded blob catalog**, `bands=['B08','SCL']`, all paths `abfss://…`: proves `/vsiadls/`
   streaming reads in the *real* builder + `datacube.npy` / `metadata.pickle.npy` / flatten writes
   on blob. `_result.json`: artifacts exist on blob, shapes sane, **`timestamps` axis length == 3**
   (the calendar-mosaic contract — `ceil(62/30)=3` for the Jul 1–Sep 1 window, corrected from a "2"
   slip 2026-07-17; a criterion that can actually fail).
3. **Sanity read-back** — `fs.load_npy` one `datacube.npy` back from blob; assert non-empty +
   expected dtype. Optional: pull one COG for a QGIS eyeball (visual-validation principle).
4. **Subprocess-safety check (the D4 claim, worth one explicit assertion)** — the workflow path runs
   `python -m fsd.workflows.task` in a **subprocess**, so this is where "`FSSPEC_*` is inherited and
   re-read by children" is proven rather than argued. Run at least one cell **through the Snakemake
   runner**, not only in-process.

> ### ⚠️ Band list is load-bearing — `['B08','SCL']`, not one band (TODO #35)
>
> **This is the spec-32 trap, and it is still live** — TODO #35 is open. Traced against the real call
> chain at this review, both constraints are structural, not stylistic:
> - **`build_datacube` hardcodes** `apply_cloud_mask_scl` → `drop_bands(["SCL"])`
>   (`datacube/builder.py`), so **SCL is mandatory**: `bands=['B08']` raises
>   `ValueError: SCL band not present in datacube`. This is exactly what killed runbook 32 v1 *after*
>   that spec passed sign-off, cross-validation, implementation **and** an Opus code review.
> - **`config.REFERENCE_BAND == "B08"`** — the build resamples everything to a real B08 image (the
>   user's reference-image-resampling principle), so **B08 must be present**, which is why the upload
>   staged it.
>
> The datacube build (step 2 above) **must use `['B08','SCL']`** — that is exactly why the upload
> staged those two bands and no others. The run-book writer must not "simplify" to one band.

Success = all `_result.json` green → **P1 storage seam proven end to end**: the fsd core pipeline
ran with every byte on the `rise` blob, switched on by config alone. Since the data is already on
blob (step 1, done), the remaining run is small and token-lifetime is a non-issue at this scale (the
upload's own `/vsiadls/` read already validated the token path).

## Deliverables (for the Sonnet@medium implement session)

- `fsd/storage/azure.py` (new) — the single module-cached `DefaultAzureCredential` + `storage_token()`
  (for the GDAL VSI path) + `to_vsi()` + the `storage=`→`FSSPEC_*`/`fsspec.config.conf` helper.
  **No bespoke storage-options registry** — adlfs + fsspec-native config do that (§1).
- `fsd/storage/fs.py` — export `to_vsi` (re-export from `azure.py`); otherwise unchanged (the 94
  sites route via `fsspec.config.conf`, no `_fs_and_path` edit needed).
- `fsd/raster/__init__.py` (or `raster/vsi.py`) — `rio_open`; swap bare `rasterio.open` in
  `raster/images.py`, `raster/cog.py`, `catalog/stac.py` (pixel-read sites only).
- `fsd/api.py` — `storage=` sets `FSSPEC_ABFSS_*` env + `fsspec.config.conf`; relax
  `_check_local_seams` (`api.py:81` — today it rejects **any** non-`None` `storage`).
- **`fsd/sources/mpc.py` — DO NOT TOUCH.** §5 is suspended (2026-07-17 pivot): the local-only guard
  at `mpc.py:294` **stays**. Getting bytes onto blob is the ingest spec's job, not this one's.
- **`fsd/sources/cdse.py` — DO NOT TOUCH.** Same reason — its `cog=True`-needs-local guard stays.
  Neither downloader gains a remote-dst path in P1.
- `fsd/pyproject.toml` — `azure-identity` in `[azure]`.
- URL-safety audit fixes (§6) — expected to be mostly confirmation; see the grep head start there.
- `fsd/runbooks/31-p1-datacube-on-blob.md` (placeholders only) — the **datacube-on-blob** demo
  (build reading the already-uploaded blob catalog; **no download step**). **Build it the way
  `runbooks/31-p1-upload-slice.md` + `runbooks/scripts/31_upload_slice.py` already work** (they ran
  green 2026-07-17): a **committed script** under `runbooks/scripts/`, no `export`-dependent
  heredocs, paths derived from `__file__`, everything in try/except, `_result.json` written
  **unconditionally including on hard failure**, `--dst` passed as an argument (no `rise` values in
  the repo).
- Tests per the Tests section.
- Living docs: `CHANGES.md` (behavior kept-but-changed: `storage=` now meaningful; blob paths read
  via `/vsiadls/`), `specs/10` pointer (→ 31 realizes Seam 1), `TODO.md` — the **ingest/normalization
  contract** is the next spec (download-to-blob for *all* sources lives there, not here; #37 already
  logs the CDSE case), plus inference/serving-on-blob, ROI-geometry-on-blob, Batch runner as explicit
  follow-ons; `RECIPES.md` (the `FSSPEC_ABFSS_ANON` + `abfss://` recipe), `PROGRESS.md`, memory
  `[[fsd-status]]`.

## Open items — RESOLVED at sign-off (2026-07-17)

Every item the draft carried is closed below. **Nothing here is left for the implementer to decide.**

- ✅ **Exact fsspec protocol strings — RESOLVED by direct verification** (§1): `AzureBlobFileSystem.
  protocol == ('abfs','az','abfss')`, and `apply_config` keys on the **class's** protocol tuple, not
  the URL scheme. **Set exactly one key, `FSSPEC_ABFSS_ANON=false`.** Do *not* set the `abfs`/`az`
  variants "for safety" — on a conflict the tuple's last entry wins silently. Do not configure `adl`
  (a different, legacy Gen1 class). `FSSPEC_ABFSS_ACCOUNT_NAME` is **redundant** — the account comes
  from the URL host and would beat conf anyway.
- ✅ **fsspec import-time vs runtime — CONFIRMED** (verified at review: `fsspec.config.conf` is
  populated from env **at module import**; a later `os.environ` mutation needs a module reload to be
  seen). `storage=` therefore sets **both** `os.environ` (for children, which re-read on their own
  import) **and** `fsspec.config.conf` (for the already-imported parent). Locked by a test (§Tests).
- ✅ **Write atomicity — RESOLVED, and the question changed shape.** The drafted `fs.put` path is
  gone: §5 copies via **`fs.transfer`**, which **already** does `.part`+rename. So the safe default
  the draft asked for is what the code does today. The residual — whether adlfs's `mv` is genuinely
  atomic on HNS — is a **runbook observation** (step 2's "no `.part` leftovers"), not a design
  choice; §5 names the fallback if it disappoints.
- ✅ **Local scratch location — MOOT.** MPC assets are already COG → **there is no staging and no
  conversion**, so there is no scratch dir to size or configure. (This is the concrete dividend of
  the MPC pivot; the draft's `FSD_SCRATCH_DIR` question existed only for CDSE's jp2→COG.)
- ✅ **`_check_local_seams` shape — DECIDED: accept both.** `storage="azure"` (string) and
  `storage={"backend":"azure", ...}` (dict) both pass; anything else still raises; `runner!="local"`
  still rejected (Batch is P2). The string form needs no account — it comes from the URL (§1).

**Deliberately still open (carried, not resolved — do not close these while implementing):**
- **TODO #31** production stream-vs-copy — **no longer touched by this spec** (the pivot removed all
  download-to-blob from P1). It belongs to the ingest spec; still "measure, don't argue" at scale.
- **TODO #32** MPC signed-URL re-signing for long copies — a non-issue at demo scale; do not add it.
- **TODO #35** `build_datacube`'s hardcoded SCL requirement — worked *around* here (the demo's band
  list), not fixed; it needs its own spec because it changes a core contract.

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

### Verified against the installed libraries (2026-07-17 review) — primary source, per-fact credit

The 2026-07-16 pass cross-validated **external** facts against docs. Spec 32's lesson is that this
**does not catch inconsistency with our own code or with the exact library versions we run**, so the
review added a direct-introspection pass. Each fact, and what produced it:

- **`AzureBlobFileSystem.protocol == ('abfs','az','abfss')`; `adl` is a separate legacy class.**
  → §1 (one config key covers all three; don't configure `adl`). — `adlfs 2026.5.0` in `.venv`, class
  attribute read directly.
- **`fsspec.config.apply_config` keys on `cls.protocol` (all protos merged, later wins) and does
  `kw.update(**kwargs)` so explicit kwargs beat conf.** → §1 (setting several keys is a hazard;
  URL-derived account beats env). — `fsspec 2026.6.0` source, `fsspec/config.py`; call site
  `fsspec/spec.py:66`.
- **`AzureBlobFileSystem._get_kwargs_from_urls('abfss://data@acct.dfs.core.windows.net/p/x.tif')
  == {'account_name': 'acct'}`, `_strip_protocol` → `data/p/x.tif`.** → **D1 confirmed**: the
  fully-qualified URL is self-describing; adlfs parses the account from the host exactly as claimed.
  — `adlfs 2026.5.0`, executed against both the `.dfs.` and `.blob.` host forms.
- **adlfs `anon` defaults to `None` → consults `AZURE_STORAGE_ANON`, where anything but `false/0/f`
  resolves to `True`; otherwise `DefaultAzureCredential` is used.** → §1 (why `anon=false` is set
  explicitly despite being the effective default). — `AzureBlobFileSystem.__init__` docstring.
- **`fsspec.config.conf` is populated from env at import.** → §1 / the resolved open item (`storage=`
  must set both env and `conf`). — observed directly (a `conf` refresh required an `importlib.reload`).
- **`mpc.download` raises on a non-local root (`mpc.py:294`); `cdse.download` raises on remote +
  `cog=True` (`cdse.py:645`); `fs.transfer` is cross-backend + `.part`-atomic; `build_datacube`
  hardcodes the SCL mask/drop; `config.REFERENCE_BAND == 'B08'`.** → the §5 rewrite, the demo's band
  list, and the Scope decisions. — **fsd's own source**, read at the review. *This is the class of
  fact the spec-32 post-mortem says no amount of external cross-validation would have surfaced.*

Sources:
- https://learn.microsoft.com/en-us/dotnet/azure/sdk/authentication/best-practices
- https://github.com/Azure/azure-sdk-for-net/blob/main/sdk/identity/Azure.Identity/samples/TokenCache.md
- https://fsspec.github.io/adlfs/
- https://filesystem-spec.readthedocs.io/en/latest/features.html
- https://gdal.org/user/virtual_file_systems.html
- https://learn.microsoft.com/en-us/azure/storage/common/identity-library-acquire-token
