# Run-book 34b — single-URL cross-baseline render (spec 34 §1e acceptance, local copies)

**You run this; Claude never runs Docker/networked scripts (spec 24).** Paste back
`tests/outputs/spec34_mixed_baseline/_result.json` + a screenshot of the XYZ render.

**What it proves.** A single XYZ URL over a mosaic that spans the S2 processing-
baseline cutover (2022-01-25) renders **consistently** — no visible brightness seam
between pre-/post-2022 tiles — because ingest stamped each item's own offset into its
COG's GDAL tag, and `unscale=true` applies it per-item before mosaicking (spec 34 §1b).
This is **the gap fsd's ingest fills that MPC itself cannot** (spec 34 §1e): MPC's own
`sentinel-2-l2a` collection has no `raster:bands` offset and no `renders` — the proof
therefore runs on **fsd's own** mini-MPC stack (spec 30), not on MPC's.

**Runs on LOCAL copies (`[G6]`)** — this validates the offset→unscale *mechanism*
(storage-agnostic), not blob-serving. Titiler-reads-blob (GDAL Azure auth inside the
tiler container) is a separate P5 serving item, deliberately out of this proof.

- **Time:** a few minutes to pull the slice + a few minutes for the mini-MPC stack to
  come up (spec 30 — mostly `pip install`s, no satellite downloads at that step).
- **Cost:** ~free (MPC anonymous access; a handful of small COGs on local disk).

---

## Prerequisites

- [ ] Docker + Docker Compose (for the mini-MPC stack, spec 30).
- [ ] A scratch venv with `fsd` installed (`pip install -e ".[dev]"` is enough — no
      `[azure]` extra needed, this run-book stays local).
- [ ] Familiarity with `runbooks/30-tier2-mini-mpc.md` — this run-book **reuses that
      stack**, just with a different input dataset (a mixed-baseline MPC slice instead
      of fsd's own inference outputs).

## Step 1 — pull the mixed-baseline slice (local disk)

```bash
cd fsd
.venv/bin/python runbooks/scripts/34_mixed_baseline_slice.py \
    --dst tests/outputs/spec34_mixed_baseline
```

- **Expect:** two short progress runs (pre-2022 window, post-2022 window), then a JSON
  dump ending `"pass": true`.
- **PASS if:** `_result.json`'s `"distinct_offsets"` shows **two different values**
  (e.g. `[-1000, 0]`) and `"pass"` is `true` — proves the two windows really do straddle
  the baseline cutover, not just "downloaded something." Writes
  `tests/outputs/spec34_mixed_baseline/_result.json`.
- **If it fails:** MPC discovery/access issues are usually transient — retry. Paste the
  error / `_result.json` if it persists.

## Step 2 — export a STAC + stac-geoparquet for the slice

```bash
.venv/bin/python -c "
from fsd.catalog.catalog import TileCatalog
cat = TileCatalog('tests/outputs/spec34_mixed_baseline/catalog.parquet')
cat.to_stac('tests/outputs/spec34_mixed_baseline/stac')
"
```

Then follow `demos/mini_mpc/export_stac_geoparquet.py` (per spec 30) to turn that
static STAC catalog into the stac-geoparquet `pypgstac load` expects.

## Step 3 — bring up the mini-MPC stack and load the slice

Follow `runbooks/30-tier2-mini-mpc.md` steps 1–2 **verbatim** (same
`docker compose up --build -d`, same `pypgstac load`), pointing `load_pgstac.py`
(`demos/mini_mpc/load_pgstac.py`) at this run-book's stac-geoparquet output instead of
the spec-28 inference-output one.

- **PASS if:** the collection + both pre/post items appear in pgSTAC (same check as
  spec 30 step 2).

## Step 4 — register one search + request tiles with `unscale=true`

```bash
.venv-serving/bin/python demos/mini_mpc/register_and_url.py \
    --collection <your-mixed-baseline-collection-id> \
    --unscale true --rescale 0,0.3 --assets B04,B03,B02
```

(`register_and_url.py` is the spec-30 helper that POSTs a `/searches` body and prints
the resulting `/searches/{id}/tiles/{z}/{x}/{y}` template — adjust its `--assets`/
`--rescale`/`--unscale` flags to match this run-book's reflectance bands; if it doesn't
already expose `--unscale`, add `"unscale": true` to the tile-request query params by
hand.)

- **Expect:** a printed XYZ URL template.
- **PASS if:** the URL is well-formed and the search registers without error.

## Step 5 — visual acceptance (QGIS or STACNotator, BYO)

Load the XYZ URL as a tile layer over an area covered by **both** the pre- and
post-2022 tiles (or pan between them). **PASS if:** there is no visible brightness
seam / no place where the mosaic looks "half dark, half bright" at the baseline
boundary. Take a screenshot.

- **If you see a seam:** double-check `unscale=true` actually made it into the tile
  request (compare against a request with `unscale=false` — that one SHOULD show the
  seam, confirming the mechanism, not just "nothing changed").

## Success criteria

- Step 1's `_result.json`: `"pass": true`, `"distinct_offsets"` has 2+ entries.
- Step 3: both baseline items visible in pgSTAC.
- Step 5: screenshot showing no visible seam with `unscale=true` (and, ideally, a
  contrasting screenshot *with* the seam at `unscale=false`, as the negative control).

Paste back the `_result.json` + screenshot(s) — a later Opus review session diffs them
against this doc, not raw logs.

## Stop / observe

- Step 1 is short (a handful of granules); Ctrl-C is safe, just re-run.
- Tear down the mini-MPC stack the same way as spec 30: `docker compose down` from
  `demos/mini_mpc/` when you're done (don't run it mid-way through steps 3–5).
