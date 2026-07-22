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

- [ ] A cloud VM **inside the `rise` VNet**, in/near the subscription/region (see
      `../P1_AZURE_SETUP.md`). **The `rise` storage account (`st<proj>`, concrete name in
      `AZURE_INFRA_PRIVATE.md`) is deny-by-default firewalled** — a VM outside the project
      subnets cannot reach it at all, so "any Azure VM" will not do.
- [ ] For CDSE: a `cdse_credentials.json` (gitignored) with your CDSE S3 keys, on the VM.
      Never commit it; see the upload note in Step 0.
- [ ] For MPC: nothing — anonymous access.

> **An AML compute instance works and may be the only option.** On this tenant, plain VMs
> report *"SSH access from the public internet is disabled"* — so `ssh`/`scp` from a laptop
> are unavailable. An **Azure ML compute instance** (Studio → Notebooks → *Terminal*) sits
> inside the VNet, reaches the firewalled storage, and gives you a shell with no SSH at all.
> Validated end-to-end this way on 2026-07-20. Its browser terminal drops more easily than
> SSH would, so `tmux` (Step 1) matters *more*, not less.

## Step 0 — reach the VM and set it up (one-time, Azure-noob pace)

```bash
# Get a shell on the VM. Either SSH (if your VM allows it):
ssh <you>@<vm-host>
# ...or, on an AML compute instance, just open Studio -> Notebooks -> Terminal.

# confirm which identity the shell is acting as -- this is the identity that must hold
# `Storage Blob Data Contributor` on the storage account, NOT necessarily your laptop's.
az account show --query user -o json
# If it is unauthenticated, `az login`. On an AML compute instance you are typically
# already signed in as yourself, and no `az login` is needed.

# clone the fsd repo (this IS the Batch dress rehearsal, spec 34 [G7] --
# the same "code arrives via git-clone" path the Batch runner will use later).
# HTTPS, not SSH: a fresh VM has no GitHub deploy key, and fsd is a public repo.
git clone https://github.com/nikhilsrajan/fsd.git
cd fsd
# spec 34 is on `main` (pushed 2026-07-20) -- a fresh clone already has it, no
# checkout needed. Sanity-check you got it before going further:
test -f src/fsd/catalog/declaration.py && echo "spec 34 present" || echo "WRONG COMMIT"

python3.11 -m venv .venv
source .venv/bin/activate
# NOTE the `mpc` extra -- `planetary-computer` is NOT in core, and `--source mpc` below
# dies with ModuleNotFoundError without it.
pip install -e ".[dev,azure,mpc]"

# the one env var that matters for writing to blob (see storage/azure.py):
export FSSPEC_ABFSS_ANON=false
```

**The ROI lives OUTSIDE this repo — `git clone` cannot give it to you.** The script resolves
`ROI_PATH = <parent-of-fsd>/shapefiles/s2grid=476da24.geojson` (`34_download_to_blob.py:32-33`),
i.e. `shapefiles/` must be a **sibling of the `fsd` checkout**. That folder is part of the
workspace, not the git repo. It is a 490-byte GeoJSON — recreate it rather than fighting with
file transfer:

```bash
mkdir -p ../shapefiles
cat > "../shapefiles/s2grid=476da24.geojson" <<'EOF'
{
"type": "FeatureCollection",
"name": "geometry",
"crs": { "type": "name", "properties": { "name": "urn:ogc:def:crs:OGC:1.3:CRS84" } },
"features": [
{ "type": "Feature", "properties": { "id": "476da24" }, "geometry": { "type": "Polygon", "coordinates": [ [ [ 16.033748282140277, 48.114321242550432 ], [ 16.057710116623269, 48.155721847866374 ], [ 16.115848242509124, 48.147389969624996 ], [ 16.091816009803637, 48.106010155862421 ], [ 16.033748282140277, 48.114321242550432 ] ] ] } }
]
}
EOF
```

**Getting `cdse_credentials.json` onto the VM (CDSE leg only).** If SSH is disabled, `scp` is
out. Do **not** use the AML Studio upload button for this: it writes to `~/cloudfiles/...`,
which is the **shared workspace file share** mounted on every compute instance in the
workspace — wrong place for S3 keys. Paste into local disk instead:

```bash
umask 077
cat > ~/cdse_credentials.json <<'EOF'
<paste the JSON from your laptop here>
EOF
chmod 600 ~/cdse_credentials.json

# verify without printing secrets -- CdseCredentials.__repr__ masks values by design
.venv/bin/python -c "
from fsd.sources.cdse import CdseCredentials
print(CdseCredentials.from_json('$HOME/cdse_credentials.json'))
"
```

Expect `s3_access_key=set`, `s3_secret_key=set`. **Check `s3_keys_expire`** in that output —
CDSE S3 keys expire and nothing in fsd enforces it, so an expired key surfaces as an opaque
S3 auth error much later.

- **Expect:** `pip install` finishes with no errors; `python -c "import fsd"` succeeds.
- **PASS if:** the venv is active, `fsd` imports, and the ROI file exists at `../shapefiles/`.

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

> **Known transient: CDSE discovery can drop mid-pagination.** `APIError: {"code":
> "ConnectionDoesNotExistError","description":"connection was closed in the middle of
> operation"}` from inside `pages_as_dicts` is **CDSE's server, not your setup** — the JSON
> error body proves their API was reached, so it is not an NSG/egress/credential problem.
> `_search_items` has no retry (TODO #43), so one blip kills the invocation before anything
> downloads. **Just re-run.** If it recurs 3+ times consecutively, stop and report it — that
> would suggest something about *this* VM's egress rather than a CDSE hiccup.

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

The **criteria** are the six booleans in the script's own `expected` block. `catalog_rows`,
`stac_items` and `source` are context, **not** pass/fail criteria — the granule count varies
by source and window (an MPC run of this slice returned **8**), so do not treat the
illustrative number below as a target.

```json
{ "step": "spec34-download-to-blob", "status": "ok", "pass": true,
  "metrics": {
    "source": "mpc",
    "catalog_rows": 8,
    "stac_items": 8,
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
