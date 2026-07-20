# Run-book 34 — download-to-blob (CDSE + MPC), cloud-VM-first

**You run this; Claude never runs networked/long scripts (spec 24).** Paste back
`tests/outputs/spec34_download_to_blob/_result_<source>.json` when each source finishes.

**What it does.** Downloads a small Sentinel-2 L2A slice (one band + SCL, ~3-week
window, single MGRS tile `T33UWP`) straight to Azure Blob for **CDSE** and/or **MPC**,
via `fsd.download(..., storage="azure")` — this is spec 34's re-opened download-to-blob
path (suspended out of spec 31). Each artifact lands as a self-describing COG: the GDAL
scale/offset + nodata tag is stamped at ingest, and the STAC export carries the same
values in `raster:bands` (spec 34 §1a). The script verifies all of that from the blob
side and writes `_result.json`.

**Where this runs (spec 34 "execution model", `[G5]`).** `fs.transfer` streams bytes
through whichever machine launches it — CDSE/MPC → that machine → blob. Run this on a
**cloud VM** on/near the `rise` account, not your laptop: then your laptop only carries
the SSH session, and the actual GB volume never touches your hotspot/wifi. This run-book
is written for someone who has never touched an Azure VM before.

- **Time:** a few minutes per source (small slice — a handful of granules).
- **Cost:** a few hundred MB stored on `rise`. Trivial.
- **Safe to interrupt** for MPC (per-file idempotent skip). **CDSE with a remote `--dst`
  is NOT yet resumable** — see the limitation note at the end; re-run from scratch if it
  fails partway (it's a small slice, so this is cheap).

---

## Prerequisites

- [ ] A cloud VM you can SSH into, in/near the `rise` subscription/region (ask if
      unsure which one — see `../P1_AZURE_SETUP.md`).
- [ ] For CDSE: a `cdse_credentials.json` (gitignored) with your CDSE S3 keys — copy
      it to the VM (`scp`), never commit it.
- [ ] For MPC: nothing — anonymous access.

## Step 0 — reach the VM and set it up (one-time, Azure-noob pace)

```bash
# from your laptop: SSH to the VM (substitute your VM's connection details)
ssh <you>@<vm-host>

# on the VM: log in to Azure so DefaultAzureCredential (used by adlfs/GDAL) can find a token
az login
# if the VM has a system-assigned managed identity instead, this may already be
# non-interactive -- `az account show` tells you which identity is active.

# clone the fsd repo (this IS the Batch dress rehearsal, spec 34 [G7] --
# the same "code arrives via git-clone" path the Batch runner will use later)
git clone git@github.com:nikhilsrajan/fsd.git
cd fsd
# spec 34 is on `main` (pushed 2026-07-20) -- a fresh clone already has it, no
# checkout needed. Sanity-check you got it before going further:
test -f src/fsd/catalog/declaration.py && echo "spec 34 present" || echo "WRONG COMMIT"

python3.11 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,azure]"

# the one env var that matters for writing to blob (see storage/azure.py):
export FSSPEC_ABFSS_ANON=false
```

- **Expect:** `pip install` finishes with no errors; `python -c "import fsd"` succeeds.
- **PASS if:** the venv is active and `fsd` imports.

## Step 1 — run the download **inside `tmux`** (detach-safe)

Why `tmux`: an SSH drop mid-download would otherwise kill the process. `tmux` keeps it
running on the VM even if your laptop/SSH session dies.

**tmux cheat-sheet:**
| Action | Command |
|---|---|
| start a named session | `tmux new -s dl` |
| detach (leave it running) | `Ctrl-b` then `d` |
| reattach after a dropped SSH | `tmux attach -t dl` |
| list sessions | `tmux ls` |

```bash
tmux new -s dl
# --- inside the tmux session ---
source .venv/bin/activate
export FSSPEC_ABFSS_ANON=false

# MPC (anonymous, no creds file needed):
.venv/bin/python runbooks/scripts/34_download_to_blob.py \
    --dst "abfss://<fs>@<account>.dfs.core.windows.net/spec34-demo/" \
    --source mpc

# CDSE (needs your creds file on the VM):
.venv/bin/python runbooks/scripts/34_download_to_blob.py \
    --dst "abfss://<fs>@<account>.dfs.core.windows.net/spec34-demo/" \
    --source cdse --cdse-creds ~/cdse_credentials.json
```

If you need to step away: `Ctrl-b` `d` to detach, close your laptop, come back later
and `tmux attach -t dl` to see it still running (or finished).

- **Expect:** progress lines, then a JSON dump ending `"pass": true` for each source.
- **PASS if:** `_result_<source>.json`'s `"pass"` is `true` — writes
  `tests/outputs/spec34_download_to_blob/_result_<source>.json`.
- **If it fails:** paste the error/`_result.json` back. For CDSE, a remote `--dst` run
  that fails partway is not resumable (see the limitation below) — just re-run.

## Step 2 — monitor progress (from a second terminal, optional)

```bash
ssh <you>@<vm-host>
tmux attach -t dl        # see the live progress lines
# or, without attaching:
cat fsd/tests/outputs/spec34_download_to_blob/_result_*.json 2>/dev/null
```

## Step 3 — verify on blob independently (optional spot-check)

The script already verifies this and puts it in `_result.json`, but to eyeball it
yourself:

```bash
.venv/bin/python -c "
from fsd.storage import fs
print(fs.ls('abfss://<fs>@<account>.dfs.core.windows.net/spec34-demo/mpc/'))
"
```

**`rsync` as the pre-push debug shortcut** (spec 34 `[G7]`): if you want to inspect the
locally-staged files (CDSE stages to a local scratch dir before pushing, MPC too when
`--dst` is remote) before they get pushed/cleaned up, add a breakpoint or check
`/tmp/fsd_cdse_*` / `/tmp/fsd_mpc_*` while the tmux session is paused — or, for a repeat
debug run, `rsync -av <scratch-dir>/ <local-mirror>/` to keep a local copy before it's
pushed.

## Success criteria (`_result.json`)

```json
{ "step": "spec34-download-to-blob", "status": "ok", "pass": true,
  "metrics": {
    "source": "mpc",
    "catalog_rows": 3,
    "cog_present": true,
    "cog_nonzero_bytes": true,
    "gdal_offset_or_scale_tag_present": true,
    "gdal_nodata_declared": true,
    "catalog_local_folderpath_is_abfss": true,
    "stac_raster_bands_present": true
  },
  "expected": { "...": "same keys, all true" },
  "error": null }
```

Paste this file back for **each source you ran** — that's what a later Opus review
session diffs against.

## Known limitation (honest, not swept under the rug)

**CDSE download-to-blob is a whole-run batch push, not per-file streaming.** When
`--dst` is remote, CDSE stages the entire pass to local scratch (reusing the existing,
heavily-tested local pipeline unchanged) and pushes the whole tree to blob only once
the pass completes — so a crash mid-pass loses that pass's progress (nothing partial
lands on blob), and the idempotent-skip check only sees files already pushed from a
*prior completed* pass, not an in-progress one. **MPC does not have this limitation** —
each file is pushed individually as it's stamped, so it resumes cleanly. True per-file
streaming-to-blob for CDSE is TODO #31 (production stream-vs-copy), explicitly out of
this spec's scope. For this run-book's small slice, this is a non-issue (worst case:
re-run the whole thing); flag it if you try a much larger slice.
