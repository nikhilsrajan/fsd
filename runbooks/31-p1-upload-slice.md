# Run-book 31 — upload a real S2 slice to the `rise` blob + repoint the catalog

**You run this; Claude never runs networked/long scripts (spec 24).** Paste back
`tests/outputs/spec31_upload/_result.json` when it finishes.

**What it does.** Uploads 20 real, already-COG Sentinel-2 granules (T33UWP, Jul–Aug 2018,
bands B08+SCL, **2.27 GB**) from the local Austria archive to the `rise` ADLS Gen2 blob,
then writes a `catalog.parquet` **on blob whose every band path is an `abfss://` URL**.
That gives the P1 storage seam real data to run against **without any download from
CDSE/MPC** — deliberately, so the seam is proven independently of the ingest/normalization
redesign we're about to spec.

**Why no fsd code changes are needed first:** `fsd.storage.put`/`write_parquet` already
route through fsspec → adlfs. The only requirements are `azure-identity` installed and
`FSSPEC_ABFSS_ANON=false` exported — adlfs then builds `DefaultAzureCredential` itself
(verified against adlfs 2026.5.0 / fsspec 2026.6.0). The script also proves GDAL
`/vsiadls/` reads **our own uploaded COG** before anyone writes code for it.

- **Time:** ~10–25 min on university wifi + VPN (2.27 GB up), plus a few seconds of verify.
- **Cost:** ~2.3 GB stored on `rise`. Trivial, but it is real.
- **Safe to interrupt.** Ctrl-C and re-run the same command — it skips blobs already
  present at the right size and resumes.

---

## Prerequisites

- [ ] **VPN connected** (the seam cannot detect this; storage is firewalled).
- [ ] `az login` done, `rise` subscription selected (see `../P1_AZURE_SETUP.md` §2).
- [ ] On **wifi**, not the hotspot.
- [ ] The local archive exists: `fsd/tests/outputs/demo_e2e/imagery/catalog.parquet`.

## Step 0 — install (one-time)

```bash
cd fsd
source .venv/bin/activate
pip install -e ".[dev,azure]" azure-identity
```

`azure-identity` is installed explicitly because spec 31 §7 (adding it to the `[azure]`
extra) is not implemented yet.

## Step 1 — set the one env var + your dst prefix

```bash
export FSSPEC_ABFSS_ANON=false
```

That is **the only backend config** — the storage account is parsed from the URL itself,
so there is no account env var. (`FSD_STORAGE_BACKEND`/`FSD_AZURE_ACCOUNT` from older spec
drafts **do not exist**.)

Take the concrete `abfss://` prefix from **`../P1_AZURE_SETUP.md` §3** — the real account and
filesystem names live only there, never in this repo. It looks like:

```
abfss://<filesystem>@<account>.dfs.core.windows.net/p1-demo/imagery/
```

## Step 2 — dry run (uploads nothing)

```bash
.venv/bin/python runbooks/scripts/31_upload_slice.py \
  --dst "abfss://<filesystem>@<account>.dfs.core.windows.net/p1-demo/imagery/" \
  --dry-run
```

**Expect:** `20 granules -> 40 files, 2.27 GB`, `"pass": true`, `"dry_run": true`.
If the granule/file counts differ, **stop** — the local archive isn't what we sized against.

## Step 3 — the real upload

```bash
.venv/bin/python runbooks/scripts/31_upload_slice.py \
  --dst "abfss://<filesystem>@<account>.dfs.core.windows.net/p1-demo/imagery/"
```

**Progress:** one line per file with running total, MB/s and ETA. **To stop:** Ctrl-C
(safe — `transfer`/`put` land whole files; re-run to resume). **To see progress:** it's on
stdout; nothing to tail.

## Success criteria (what Claude will diff `_result.json` against)

| key | expected |
|---|---|
| `status` | `"ok"` |
| `pass` | `true` |
| `granules` | `20` |
| `files_total` | `40` |
| `files_uploaded` + `files_skipped_already_present` | `40` |
| `catalog_rows_on_blob` | `20` |
| `every_catalog_path_is_abfss` | `true` |
| `blob_sample_exists` | `true` |
| `gdal_vsiadls_read_ok` | `true` |
| `gdal_sample_nonzero` | `true` — real pixels, not an empty window |

`gdal_vsiadls_read_ok` + `gdal_sample_nonzero` are the load-bearing ones: they prove
**spec 31 D2/§4** (GDAL streams `rise` blob COGs via `/vsiadls/` with a fresh
`AZURE_STORAGE_ACCESS_TOKEN`) against real uploaded data, before any code is written for it.

## If it fails

- **403 / `AuthorizationPermissionMismatch`** → VPN down, or `az login` expired
  (`az account show -o table`), or `FSSPEC_ABFSS_ANON` unset (the script guards this and
  says so).
- **`ModuleNotFoundError: azure.identity`** → step 0 wasn't run in this venv.
- **`FileNotFoundError` on a local band** → the local archive was pruned; re-check
  `tests/outputs/demo_e2e/imagery/`.
- Anything else → paste `_result.json`; it is written **even on a hard failure**, with the
  exception in `error`.

---

## ⚠️ Known caveat — this imagery is radiometrically un-harmonized

Every granule in the Austria archive is processing baseline **`N0500` (05.00 ≥ 04.00)**, so
its DN carry ESA's `BOA_ADD_OFFSET = -1000`. But `sources/cdse.py` writes
`boa_add_offset = 0` for every CDSE row (**TODO #30**, the CDSE-side retrofit of correctness
debt **#10**, still open), and this catalog predates the column entirely, so
`TileCatalog.read` fills `0`.

**Consequence:** datacubes built from this slice are **~1000 DN too high**. That is fine for
proving the *storage seam* (which does not care what the pixels mean) and is exactly why
this run-book's PASS criteria are all seam properties, not radiometric ones. **Do not read
science off these cubes.** It is also the sharpest live example of why ingest should
normalize: the wrongness is baked into an artifact and the catalog asserts it needs no fix.
