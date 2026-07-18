# Run-book 31b — build a Sentinel-2 datacube reading + writing the `rise` blob

**You run this; Claude never runs pipeline/networked/long scripts (spec 24).** Paste back
`tests/outputs/spec31_datacube_on_blob/_result.json` when it finishes.

**What it does.** Proves the **P1 Azure compute seam** (spec 31 §1–§4/§6/§7): the fsd
pipeline — not just raw `fsspec`/`adlfs` I/O — reads a blob catalog + streams blob COGs
via GDAL `/vsiadls/`, then writes `datacube.npy`/`metadata.pickle.npy` back to blob.
**No download involved** — the imagery is already on blob from
`runbooks/31-p1-upload-slice.md` (T33UWP, Jul–Aug 2018, B08+SCL, 20 granules), deliberately,
so this proves the seam independently of the ingest/normalization redesign that comes next.

**Two builds** (see `runbooks/scripts/31_datacube_on_blob.py`'s docstring for the full
rationale):

1. **A filtered catalog slice on blob, then `python -m fsd.workflows.task` invoked
   directly, as a real subprocess, writing `datacube.npy`/`metadata.pickle.npy` to blob.**
   `workflows.task` consumes a per-shape *filtered* slice (the `TileCatalog.filter` output
   — date+overlap filtered, carrying the `area_contribution` column the builder requires),
   not the raw imagery catalog, so the script first filters the blob catalog against the
   ROI and writes that slice back to blob (`fs.write_parquet` → adlfs), then runs `task` on
   it. `task` is the actual CLI unit-of-work the Snakemake runner shells out to (spec 10
   Seam 2) — running it as a genuine subprocess proves **D4** (the `FSSPEC_ABFSS_ANON` env
   var crosses the subprocess boundary and is re-read by the child) alongside **D2/§4**
   (GDAL streams blob COGs via `/vsiadls/` with a fresh token).
2. **`fsd.create_training_data(..., storage="azure")` through the real local Snakemake
   runner**, catalog on blob but the build's own working directory kept **local**.

**⚠️ Why build 2 doesn't write its *own* datacube.npy to blob (a finding, not a
simplification):** implementing this spec surfaced that the local Snakemake runner's
`start.txt`/`done.txt` resumability sentinels are plain `os.makedirs`/`open` calls, not
routed through `fsd.storage` — a remote per-cube working directory now raises a clear
error (a real bug was fixed first: `os.path.abspath` was silently corrupting the
`abfss://` URL; see `CHANGES.md`) rather than the sentinels being made blob-safe, which
is a larger design question logged as **TODO #41**. Build 1 is what actually proves the
write-to-blob claim; build 2 proves the pipeline's normal entrypoint (preflight, catalog
read, `flatten`, `TrainingData`) still works unchanged against a blob catalog. Both
together cover every claim spec 31's demo cares about.

- **Time:** seconds — one ROI cell, 20 small COGs, no download.
- **Cost:** trivial (a few KB written to `rise`).
- **Prerequisite:** `runbooks/31-p1-upload-slice.md` has run green (its `_result.json`
  `"pass": true`) — this run-book reads the catalog it wrote.

---

## Prerequisites

- [ ] **VPN connected.**
- [ ] `az login` done, `rise` subscription selected (`../P1_AZURE_SETUP.md` §2).
- [ ] `runbooks/31-p1-upload-slice.md` ran green — you have its blob catalog URL.

## Step 0 — install (one-time, if not already from run-book 31a)

```bash
cd fsd
source .venv/bin/activate
pip install -e ".[dev,azure]"
```

`azure-identity` is now in the `[azure]` extra (spec 31 §7) — no separate install needed.

## Step 1 — the one env var

```bash
export FSSPEC_ABFSS_ANON=false
```

The storage account comes from the URL itself; there is no account env var.

## Step 2 — run

```bash
.venv/bin/python runbooks/scripts/31_datacube_on_blob.py \
  --catalog "abfss://<filesystem>@<account>.dfs.core.windows.net/<path>/imagery/catalog.parquet" \
  --out "abfss://<filesystem>@<account>.dfs.core.windows.net/<path>/build/"
```

(`--catalog` = the URL `runbooks/31-p1-upload-slice.md` printed as `wrote catalog -> ...`
— e.g. `.../fsd-tests/p1-demo/imagery/catalog.parquet`; `--out` = any blob prefix this run
can write scratch output under — take the account/filesystem/path from `../P1_AZURE_SETUP.md`
§3, never commit the concrete values.) The ROI geometry is auto-located from the workspace-root
`shapefiles/` (works from the main checkout **or** a worktree); pass `--roi <path.geojson>`
to override.

**Progress:** two stages printed to stdout (`[1/2]`, `[2/2]`); each is seconds, not
minutes — small ROI, imagery already local to Azure. No background process, nothing to
tail.

## Success criteria (what Claude will diff `_result.json` against)

| key | expected | proves |
|---|---|---|
| `task_subprocess_returncode` | `0` | build 1 (direct subprocess) succeeded |
| `task_datacube_on_blob_exists` + `task_metadata_on_blob_exists` | `true` | **D1/§3**: `fs.save_npy` wrote real artifacts to `abfss://` |
| `task_timestamps_len` | `3` | the `mosaic_days=30` calendar-mosaic contract over 2018-07-01..2018-09-01 = `ceil(62/30)=3` windows — a criterion that can actually fail (not a degenerate T=1). NB: `3`, not `2` — the spec's "T=2" prose was an arithmetic slip; the count is verified against `_calendar_windows`. |
| `task_readback_dtype_is_uint16_or_float` | `true` | the blob-written `datacube.npy` reads back as real pixel data, not garbage |
| `snakemake_build_returncode` | `0` | build 2 (through `create_training_data` + the real Snakemake runner) succeeded |
| `snakemake_timestamps_len` | `3` | same calendar-mosaic contract, proven again through the normal entrypoint |

Every key implicitly depends on **D2/§4** (GDAL `/vsiadls/` + a fresh
`AZURE_STORAGE_ACCESS_TOKEN` streaming the uploaded COGs) — the builder cannot produce a
non-degenerate datacube without successfully reading the blob pixels.

## If it fails

- **`FSSPEC_ABFSS_ANON is not set`** → `export FSSPEC_ABFSS_ANON=false` in *this* shell
  (the script checks its own process env, not a file).
- **`ROI geometry not found`** → the script walks up from its own location to find the
  workspace-root `shapefiles/s2grid=476da24.geojson` (works from the main checkout or a
  `.claude/worktrees/` copy). If your `shapefiles/` lives elsewhere, pass `--roi <path>`.
- **403 / `AuthorizationPermissionMismatch`** → VPN down or `az login` expired
  (`az account show -o table`).
- **`task_subprocess_returncode` non-zero** → read `task_subprocess_stderr_tail` in
  `_result.json` (captured, not just printed).
- **`snakemake_build_error` present** → `create_training_data`'s own exception message,
  captured before re-raising.
- Anything else → paste `_result.json`; it is written **even on a hard failure**, with
  the exception in `error`.

---

## ⚠️ Known caveat — inherited from the uploaded imagery

Same as `runbooks/31-p1-upload-slice.md`: this slice is radiometrically un-harmonized
(baseline `N0500`, `boa_add_offset` hardcoded 0 for CDSE rows, TODO #30 open) — fine for
proving the storage seam, not for reading science off the resulting cube.
