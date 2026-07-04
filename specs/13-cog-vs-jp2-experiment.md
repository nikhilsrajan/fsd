# Spec 13 — COG vs JP2 storage/time experiment

> **Status: signed off + implemented (2026-07-04).** `benchmarks/prep_cog_dataset.py`
> (JP2→base COG, DEFLATE+PREDICTOR=2 lossless via NBITS=16, disk pre-flight, storage report),
> harness `--catalog/--start/--end/--tag`, `benchmarks/compare_cog_jp2.py` (team report +
> duration-vs-concurrency overlay). No `src/fsd/` change. Runbook `tests/manual/cog_experiment.md`;
> pure logic unit-tested. **Full 4-month A/B DONE (2026-07-04):** COG 1.58×→3.46× faster wall,
> up to 9.42× faster `load_images`, COG read cost FLAT vs concurrency (1.01× vs JP2 3.45×) →
> decode-bound confirmed (corrects Part-2). Cost: base COG 1.225× JP2 storage (+23%), lossless.
> Report `benchmarks/cog_vs_jp2_report.md`. See `CHANGES.md`.


A **measurement experiment** (not a production change) to give the team the numbers for a
**space-vs-time** decision: if Sentinel-2 tiles were stored as **COGs** instead of the native
CDSE **JP2** (JPEG2000), how much **build time** do we save, and how much **disk** do we lose?

Motivated by the Part-2 finding (spec 12): datacube build is dominated by `load_images`, whose
per-read cost rises sharply with parallelism. JP2's **wavelet decode is CPU-heavy**; COG
(DEFLATE, tiled) decodes far cheaper. So the open question is whether the `load_images` slowdown
is **decode-bound** (→ COG is a big win *and* flattens the duration-vs-concurrency curve) or
truly disk-bandwidth-bound (→ COG helps little). This experiment settles it with the existing
Part-1/2 harness, and prices the storage trade-off.

## Non-negotiable: no `src/fsd/` changes
The read path is already format-agnostic — `rasterio.open` detects JP2 vs GeoTIFF from the file,
and the build writes `datacube.npy`, not rasters. So the switch is **pure data + catalog**. The
only code touched: a **new prep script**, a **new compare script**, and **CLI knobs on the
benchmark harness** (itself a benchmark, not core). Builder / workflows / raster untouched.

## Inputs & fixed choices
- Source: `satellite_benchmark/sentinel-2-l2a/` (the 1-year Ethiopia download, 4 MGRS tiles).
- **Convert the first 4 months only** (bounds disk use; extrapolate ×3 for the year).
- **COG profile — locked:** `COMPRESS=DEFLATE`, `PREDICTOR=2`, `BLOCKSIZE=512`,
  **`OVERVIEWS=NONE`**. DEFLATE+PREDICTOR is **fully lossless** (bit-identical pixels; PREDICTOR
  is a reversible integer-differencing pre-step, not a quality knob) — a hard requirement.
- **Overviews are NOT generated for the dataset** (the build reads full-res and never uses them);
  their storage cost is **measured on a sample and reported as a separate delta** (for the future
  TiTiler XYZ-tiling goal, which *does* want overviews).
- Grids: the same `shapefiles/100_random_grids.geojson`.
- **Timed A/B window:** a representative **~6-week slice** within the 4 months (keeps the double —
  JP2 + COG — × `cores[1,2,4,6,8,10]` sweep to a sane runtime). Configurable.

## Part A — prep script (`benchmarks/prep_cog_dataset.py`)
Builds the parallel COG dataset + catalog and the storage report. Steps, in order:

1. **Tooling check (step 0):** confirm the `.venv` GDAL exposes the COG driver
   (`gdal_translate -of COG` or the rasterio COG driver); fail early with guidance if not.
2. **Select** the first-4-months rows from the JP2 catalog (`TileCatalog` / `read_parquet`,
   filter by `timestamp`).
3. **Pre-flight disk safety (the user's explicit worry):** convert a small **sample** (a couple
   of products, covering the 10 m and 20 m bands) to base-COG; from the sample derive per-band
   COG/JP2 size ratios; **extrapolate** the full-4-month base-COG size from the full JP2 byte
   sums; check `shutil.disk_usage(target).free` ≥ estimate × 1.2. **Abort with a clear
   "needs X GiB, free Y GiB" message if insufficient** — before writing the bulk.
4. **Convert** every selected band file JP2 → base COG into a **mirror tree**
   `satellite_benchmark_cog/…` (same relative layout, `Bxx.tif`). Copy non-raster sidecars
   (`MTD_TL.xml`) for fidelity. **Live progress + ETA** (files done/total, elapsed, ~ETA) — this
   is a long process ([[long-process-progress]]).
5. **Losslessness check:** for a sample of files, assert the COG pixels are **bit-identical** to
   the JP2 pixels (`np.array_equal` on full reads) — proves zero information loss. Report pass.
6. **Write the COG catalog** `satellite_benchmark_cog/sentinel-2-l2a/catalog.parquet`: the same
   rows/schema as the JP2 subset with only `local_folderpath` → the mirror folder and `files` →
   `.tif` names. (Same geometry/timestamp/crs/area_contribution ⇒ `setup`/`filter` select the
   identical (tile, band, acquisition) set — a fair A/B.)
7. **Storage report** `benchmarks/cog_vs_jp2_storage.md` (+ json): total & per-band bytes for
   **JP2 → base COG → COG+overviews**, with ratios. The overview row is estimated from the
   sample (base-COG + `gdaladdo`/`OVERVIEWS=AUTO` on the sample → measured delta, typically
   ~+25–33%). Three rows = the space axis of the team's trade-off, including the tiling future.

## Part B — timed A/B (harness CLI knobs, `datacube_throughput_sweep.py`)
Add flags so the **same** harness runs against either dataset with tagged, non-clobbering outputs:
- `--catalog PATH` — overrides the module `CATALOG` (→ flows into `create_datacube.setup`).
- `--start / --end` — the timed window.
- `--tag STR` — suffixes the scratch `OUT`, `REPORT`, `FIG_DIR`, and `stats.json` (e.g.
  `…_jp2` / `…_cog`) so the two runs coexist.

Run both with `--read-log` (Part 2) so we capture the **duration-vs-concurrency** curve for each:
```
… --tag jp2 --catalog <jp2 catalog>  --start S --end E --read-log
… --tag cog --catalog <cog catalog>  --start S --end E --read-log
```
Identical grids/window/cores ⇒ identical read *sets*, differing only in format.

## Part C — compare script (`benchmarks/compare_cog_jp2.py`)
Reads the two tagged `stats.json` + the storage json → one **team-facing report**
`benchmarks/cog_vs_jp2_report.md`:
- **Time table** per `cores`: total wall, summed `load_images`, mean `load_images`/grid — JP2 vs
  COG, with speedup.
- **The decode-bound test:** overlay the JP2 and COG **duration-vs-concurrency** curves. *If COG's
  curve is both lower and flatter, the Part-2 slowdown was JP2 wavelet-decode contention* (COG
  frees the CPU); if it barely moves, it was genuinely disk/bandwidth.
- **Storage table:** JP2 → base COG → COG+overviews (bytes, ratio, extrapolated ×3 to the year).
- **One-paragraph verdict:** the space-vs-time summary for the team (e.g. "COG cut build wall N%
  and mean read M×, costing K× the disk; the concurrency curve flattened → decode-bound").

## Cache handling — measure, don't force (unchanged)
Warm-as-is, no `sudo purge`. To keep the A/B fair, run **JP2 and COG under the same cache regime**
(back-to-back, same machine, same window); `--read-log` exposes any residual cache effect.

## Explicitly OUT (deferred)
- Any `src/fsd/` change / production cutover to COG (this only measures).
- Full-year conversion (4 months only); overview generation for the *dataset* (sample-only, for
  the delta); ZSTD/LZW/uncompressed sweeps (DEFLATE-only for v1 — one clean point).
- Azure/remote-Blob read regime (that's where COG's fewer-bytes/range-request win dominates; here
  we measure the *local* decode/IO regime).

## Validation
- Unit tests (pure): the catalog-rewrite (JP2 row → COG row: path + `.jp2`→`.tif` mapping) and the
  storage-summary aggregation, on synthetic rows.
- Runtime checks in the prep script: tooling check, disk pre-flight, and the **losslessness
  assert** (bit-identical sample) — the guard for "no loss of information".
- Smoke: prep on **one product** (tiny), then the harness A/B `--smoke` on both tags → the compare
  script emits a populated report. Full run after sign-off.

## Manual runbook
New `tests/manual/cog_experiment.md`: prerequisites (GDAL COG driver in `.venv`), the disk
pre-flight, the convert command (with progress), the two tagged harness runs, the compare step,
how to read the space-vs-time report, and how to clean up the COG tree to reclaim disk.
