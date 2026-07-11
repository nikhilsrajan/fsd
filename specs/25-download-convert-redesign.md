# Spec 25 — download / jp2→COG redesign: pipeline transfer over a convert **process pool**

> **Status: SIGNED OFF (2026-07-11) — awaiting implementation.** Opus@high (spec). C1–C6 resolved as
> recommended (see "Sign-off resolutions" below). Implementation lands in a **Sonnet@medium** session
> the user switches to (spec 24 D3/D5), against this spec. No pipeline/network script is run by Claude;
> a measured confirm-run is **spec 26**'s job, not this one.

## Sign-off resolutions (2026-07-11)

All six confirms accepted as recommended:
- **C1 — accepted:** `add_done_callback` chaining + a **single** `sem_staged` (the transfer pool
  already caps concurrent transfers at `MAX_CONCURRENT_S3`; a second semaphore is redundant).
- **C2 — superseded by C6/D5:** `MAX_STAGED` is disk-aware (a helper), not a static constant.
- **C3 — accepted:** keep `_download_one` as the sequential wrapper (its direct-call tests survive);
  `download()` drives the two stages and no longer calls it.
- **C4 — accepted:** circuit breaker → streaming stop, **transfer-failures-only**; rewrite
  `test_circuit_breaker_trips_and_stops_early` to monkeypatch `_transfer_one` and assert early stop
  (not the old chunk-exact count).
- **C5 — accepted:** add `max_convert_procs` / `max_staged` / `convert_executor` keyword knobs to
  `download` (+ pass-through on `download_resume`); the injected executor is the test seam.
- **C6 — accepted:** disk-aware `MAX_STAGED` (`STAGING_DISK_FRACTION=0.25`, `STAGING_ITEM_GB=0.2`,
  target `headroom = MAX_CONCURRENT_S3 + 2*MAX_CONVERT_PROCS`, disk as a cap not a lever), sized once
  at `download()` start.

## Motivation — the defect (not recorded in any repo artifact until now)

`sources/cdse.py::download` processes each file-chunk with a
`ThreadPoolExecutor(max_workers=config.MAX_CONCURRENT_S3=4)`. Each worker runs `_download_one` →
`_transfer_and_convert` (cdse.py:380), which does, **serially on the one worker thread**:

1. `fs.transfer(src, staging)` — CDSE byte transfer (network / I/O-bound, **releases the GIL**), then
2. `to_cog(staging, dst)` — GDAL COG-translate + DEFLATE/PREDICTOR=2 **+ overviews** (CPU-bound,
   **holds the GIL**).

Two compounding defects:

- **Conversion is inline with the transfer.** A worker in `to_cog` is not transferring — with only
  4 workers, a few converting at once collapse download concurrency.
- **`to_cog` holds the GIL.** Even the transfers that *are* running are starved, because a
  GIL-holding GDAL call on one thread stalls the others. **Threads cannot parallelize this — only
  processes can.**

Observed symptom (spec 23 instrumentation): single-thread probe ≈ **8.8 MB/s** network, but aggregate
crawled to **~0.2 file/s**. The network was never the bottleneck; inline, on-thread, GIL-bound
conversion of full ~110 km granules (with overviews) was.

**Rate sizing** (from `benchmarks/` artifacts, to justify the design, not re-measured here):
a ~72 MB band transfers in **~8 s** (8.8 MB/s); `to_cog` **with overviews** runs **~15 s/file/worker**
(migration report: memory-bandwidth-bound, knee at 8 workers). **Convert is *slower* than transfer
per file** → the convert stage is the pipeline's ceiling, and staged JP2s will accumulate unless we
bound them. Equilibrium with 4 transfer threads (~0.5 file/s) and 8 convert procs (~0.53 file/s) is a
well-matched pipeline; the win is that the 4 transfer threads now run **continuously**, overlapped
with parallel GIL-free conversion, instead of serialized behind GIL-holding converts.

## Decisions (from the 2026-07-11 interview — locked)

- **D1 — Option A2: one continuous pipeline + explicit `MAX_STAGED` backpressure.** Not per-chunk
  drain (A1): A1 lets staged files reach ~`chunksize` (~4–8 GB peak) — unsafe on a tight disk. A2
  caps staged JP2s to a bound that is **disk-aware, sized once at download() start** (§5), not a
  static constant.
- **D5 — `MAX_STAGED` is a safety cap, not a throughput lever (2026-07-11 refinement).** A
  bounded-buffer pipeline's throughput is `min(transfer_cap, convert_cap)` once the buffer clears
  `MAX_CONCURRENT_S3 + MAX_CONVERT_PROCS` (both pools stay fed); a *larger* buffer gives **no**
  throughput gain — it only trades disk for nothing. So free disk **caps** the buffer (shrink it when
  space is tight) rather than growing it. The lone exception — riding out CDSE flaky-window transfer
  stalls by letting converts keep draining a fuller buffer — is a real but diminishing benefit,
  exposed via the `max_staged=` override, **not** the default. The production-optimal value (and
  whether network variance warrants extra headroom) is a **measured** question → the instrumented
  confirm-run in **spec 26**, not a static guess here.
- **D2 — Keep ingest overviews** (Option D rejected). `COG_OVERVIEWS="AUTO"` stays. Convert therefore
  remains the ~15 s/file ceiling — accepted; it is the price of TiTiler-ready raw-band COGs the user
  wants, and A2's backpressure keeps disk bounded regardless.
- **D3 — Convert pool = processes**, `MAX_CONVERT_PROCS = min(os.cpu_count(), 8)` (migration report:
  knee at 8; 10 gave no gain). **Spawn** start-method (GDAL-safe; portable to Linux/Batch).
- **D4 — Confirm-run run-book deferred to spec 26** (the safe-runner). Spec 25 is code + `pytest` only.

## What changes (contained to `sources/cdse.py` + `config.py`)

The read/build path, `to_cog`, discovery, `download_resume`, `sum_results`, `probe_throughput`,
`plan_download`, the catalog, and the `DownloadResult` shape are **untouched**. This spec restructures
only the download **loop** and splits its per-file worker into two stages.

### 1. Split the per-file worker into two stages

Today's `_download_one`/`_transfer_and_convert` bundle transfer+convert on one thread. Split them:

```python
def _transfer_one(src, dst, s3opts, *, needs_convert, tries=3, base_delay=0.5):
    """THREAD stage. Idempotent skip on the FINAL dst; else transfer (with the
    existing fail-fast retry loop) to a local staging sibling (needs_convert) or
    straight to dst (sidecar / cog=False). No conversion.
    Returns (ok, reason, transfer_s, jp2_bytes).  reason ∈ {"skipped","ok",<err>}.
    staging path is dst + ".src.jp2" (implied; caller reconstructs)."""

def _convert_one(staging, dst):
    """PROCESS stage. to_cog(staging, dst) then remove staging (finally).
    Top-level & picklable (ProcessPoolExecutor). Operates on REAL local files only —
    never depends on a parent-process monkeypatch. Returns (ok, reason, convert_s).
    A convert failure ("ConvertError") is a local/data fault, NOT a CDSE window."""
```

- The **fail-fast retry loop** (transient-CDSE re-roll, cdse.py:443–456) moves into `_transfer_one`
  (it retries the *network* part only). `_convert_one` does **not** retry (deterministic local GDAL).
- Skip-check stays keyed on the **final** path with `size > 0` (unchanged idempotency).
- **`_download_one` is kept** as a thin sequential wrapper = `_transfer_one` then inline
  `_convert_one` — so its existing direct-call unit tests (`test_download_one_*`) pass unchanged, and
  it remains the reference/sequential unit. **`download()` no longer calls `_download_one`** — it
  drives the two stages across two pools (below).

### 2. The A2 pipeline in `download()`

Replace the per-chunk `ThreadPoolExecutor` loop with **one** continuous pipeline for the whole work
list, two executors + one semaphore, driven by a throttled submit loop with `add_done_callback`
chaining:

```
transfer_pool = ThreadPoolExecutor(MAX_CONCURRENT_S3)                       # CDSE quota = 4
convert_pool  = convert_executor or ProcessPoolExecutor(
                    max_workers=MAX_CONVERT_PROCS,
                    mp_context=multiprocessing.get_context("spawn"))         # created lazily
sem_staged    = BoundedSemaphore(MAX_STAGED)   # bounds staged-but-unconverted JP2s on disk
lock          = threading.Lock()               # guards counters/results/progress/catalog buffer

needs_convert(item) = cog and item.src.endswith(".jp2")

# --- throttled submit loop (main thread) ---
for (src, dst, tid) in work:
    if tripped: break
    if needs_convert:
        sem_staged.acquire()          # BLOCKS when MAX_STAGED files are in flight → backpressure
        if tripped: sem_staged.release(); break
    fut = transfer_pool.submit(_transfer_one, src, dst, s3opts, needs_convert=needs_convert)
    fut.add_done_callback(partial(_on_transfer_done, src, dst, tid, needs_convert))

# --- transfer callback (runs in a transfer-pool thread) ---
_on_transfer_done(src, dst, tid, needs_convert, fut):
    ok, reason, t_s, nbytes = fut.result()
    <accumulate transfer metrics; update consecutive-transfer-fail → maybe set tripped>   # under lock
    if ok and reason != "skipped" and needs_convert:
        cfut = convert_pool.submit(_convert_one, dst + ".src.jp2", dst)
        cfut.add_done_callback(partial(_on_convert_done, src, dst, tid))
    else:
        if needs_convert: sem_staged.release()     # skip / transfer-fail / no-convert path
        _finalize(tid, dst, ok, reason)

# --- convert callback (runs in a parent-process thread; add_done_callback is parent-side) ---
_on_convert_done(src, dst, tid, cfut):
    ok, reason, c_s = cfut.result()
    sem_staged.release()
    <accumulate convert_s>                                                   # under lock
    _finalize(tid, dst, ok, reason if ok else "ConvertError")

# --- after submit loop: wait for all in-flight to drain, then flush + shutdown ---
```

- **`_finalize`** (under `lock`): append `(tid, dst, ok)` to a buffer + record failure/reason/metrics;
  bump `done`; **flush the buffer to the catalog every `chunksize` completions** via the existing
  `_append_downloaded` (crash resilience); throttled progress `_emit` every `PROGRESS_EVERY_S`. Flush
  the remainder at the end.
- **Draining:** after the submit loop, wait for every outstanding transfer+convert future (track a
  completion count/`Event`, or collect futures and `wait()` them). Then final catalog flush, final
  `_emit`, and `convert_pool.shutdown()` (skip creating/closing the pool if no file needed convert —
  a pure-skip resume pass never spawns processes).
- **Lazy pool:** create `convert_pool` only on the first `needs_convert` submission (a `cog=False`
  run or an all-skip pass spawns **zero** processes).

### 3. Circuit breaker — streaming semantics (a conscious behavior change → CHANGES.md)

Today the breaker "finishes the current chunk, then stops." With one continuous pipeline there is no
chunk boundary. New semantics:

- The breaker keys on **consecutive *transfer* failures only** (a bad CDSE window, BUG-001). A
  `_convert_one` failure is a local fault — it counts in `failed_count`/`failures` but **does not**
  touch the consecutive counter.
- On reaching `max_consecutive_failures`, set `tripped=True`; the submit loop stops submitting new
  work at its next iteration; in-flight transfers/converts drain; `download` returns
  `circuit_tripped=True`. `total_count` = files actually attempted. Because the submit loop's
  look-ahead is bounded (`sem_staged` gates the common needs_convert case), it stops within
  ~`MAX_STAGED` items of the trip — no exact chunk count, which is fine: `download_resume` retries the
  remainder regardless (the resume loop is the real recovery, spec 01/14).

### 4. `chunksize` repurposed (kept in the signature; redocumented → CHANGES.md)

`chunksize` no longer batches the executor (there is one pipeline). It now controls only the
**catalog-flush cadence** (flush every `chunksize` completed files). Default stays `100`; callers
(`download_resume`, api, demos) are unaffected.

### 5. `config.py` additions + disk-aware `MAX_STAGED` (D5)

```python
# Convert-on-download runs GDAL COG-translate (GIL-holding, CPU-bound) in a PROCESS pool,
# decoupled from the 4 transfer threads (spec 25). Knee is 8 workers (migration report).
MAX_CONVERT_PROCS = min(os.cpu_count() or 1, 8)

# Staging backpressure is sized at download() START from FREE DISK (not a static constant): it is a
# safety CAP, not a throughput lever (D5). Throughput plateaus once the buffer keeps both pools fed.
STAGING_DISK_FRACTION = 0.25   # use at most 25% of free space on root_folderpath for in-flight staging
STAGING_ITEM_GB       = 0.2    # rough disk per in-flight band file (the JP2 + its COG coexist mid-convert)
```

(`import os` at top of `config.py`; `import shutil` in `cdse.py`.) The `MAX_STAGED` value is computed
per-run by a helper (not a constant), so a tight disk auto-shrinks it and a roomy disk just uses the
saturation target:

```python
def _default_max_staged(root_folderpath: str, max_convert_procs: int) -> int:
    floor    = config.MAX_CONCURRENT_S3 + max_convert_procs        # keep every convert proc fed
    headroom = config.MAX_CONCURRENT_S3 + 2 * max_convert_procs    # + smoothing for network jitter
    free     = shutil.disk_usage(root_folderpath).free
    disk_cap = int(free * config.STAGING_DISK_FRACTION / (config.STAGING_ITEM_GB * 1e9))
    staged   = max(config.MAX_CONCURRENT_S3, min(headroom, disk_cap))  # never below a working pipeline
    if staged < floor:
        <log a warning: "disk-limited staging=<n> < <floor>; convert pool may under-saturate">
    return staged
```

- **Why disk is a cap, not a lever (D5):** past `floor` a larger buffer yields **no** throughput gain
  (bounded-buffer queueing). So we never grow the buffer just because disk is free — we only *shrink*
  it when disk is tight. With ~170 GB free, `disk_cap ≈ 200+` never binds → `MAX_STAGED = headroom`
  (~20). With ~10 GB free, `disk_cap ≈ 12` and it shrinks safely. `max_staged=` (the override) is the
  escape hatch for a user who knowingly spends spare disk as a flaky-window buffer.
- **Sized once at start** (not re-polled): free space *falls* as final COGs land (the intended
  product), but the `0.25` fraction is margin enough; "does the whole product fit?" is
  `plan_download`'s GB estimate (spec 23), not `MAX_STAGED`'s job.
- `COG_OVERVIEWS` stays `"AUTO"` (D2). `_transfer_and_convert` is removed (its body is redistributed
  into `_transfer_one` + `_convert_one`).

### 6. `download()` optional knobs (all keyword, defaulted → backward-compatible)

```python
def download(..., *, ..., cog=True,
             max_convert_procs: int | None = None,   # None → config.MAX_CONVERT_PROCS
             max_staged: int | None = None,          # None → _default_max_staged(root_folderpath, procs)
             convert_executor=None):                 # None → real ProcessPoolExecutor
```

`convert_executor` is the **testability seam** (codebase-design: inject the expensive collaborator).
Tests pass a trivial **synchronous** executor (runs `_convert_one` inline, returns a done Future) →
the pipeline chaining is exercised in-process with **no subprocess spawn** (fast, deterministic, and
immune to the spawn-vs-monkeypatch problem). `download_resume` gains matching pass-through kwargs.

## Seam / concurrency gotchas (call out; don't fake)

- **Local-dst-only stays** (spec 14). `cog=True` + remote `root_folderpath` still raises up-front.
  The Azure stage-local→convert→**upload** path is still deferred — but this pipeline is exactly the
  seam it will slot into (a convert worker that also `storage.put`s). Note only; don't build (P1/P4).
- **`spawn`** re-imports modules per worker (startup cost paid ~once per worker, amortized over a long
  run). Required: `fork` + GDAL's internal threads can deadlock on Linux/Batch. Use an explicit spawn
  context.
- **Crash/resume:** a crash leaves ≤`MAX_STAGED` orphan `Bxx.tif.src.jp2` (final `.tif` absent) →
  the next `download` pass re-transfers (overwrites staging) + re-converts. No half-written `.tif`
  survives (`to_cog` atomic). Orphans are harmless (overwritten); no startup sweep needed.
- **No secrets to child processes.** `_convert_one` takes only paths; creds/`s3opts` never leave the
  parent (transfers run in parent threads).

## Validation — `pytest` only (Claude may run it; no network)

**Unchanged / must still pass (regression):** `test_download_one_skips_and_reports_reason`,
`test_download_one_redownloads_zero_byte_file`, `test_download_one_cog_converts_and_is_idempotent`
(all call `_download_one`, kept as the sequential wrapper), `test_download_end_to_end_mocked`
(cog=False), `test_download_accumulates_timing_bytes_and_by_band` (cog=False),
`test_download_raises_when_over_max_tiles`, `test_download_cog_rejects_remote_root`,
`test_download_resume_loops_until_complete`, `test_sum_results_aggregates`, `test_select_item_files_*`.

**Rewritten (conscious semantics change):**
- `test_circuit_breaker_trips_and_stops_early` — now monkeypatches **`_transfer_one`** (not
  `_download_one`) to always fail; asserts `circuit_tripped is True` and that it **stopped early**
  (`total_count < len(work)`, `failed_count == total_count`) instead of the old exact "4 of 6" chunk
  count.

**New tests:**
- **`_transfer_one`** unit: skip on existing final; 0-byte leftover re-transfers; retry/fail-fast on a
  retryable error; `needs_convert=True` writes to `dst+".src.jp2"` and returns bytes; sidecar/
  cog=False writes to `dst`.
- **`_convert_one`** unit: converts a real synthetic staged raster → COG `.tif`, removes staging,
  returns `(True,"ok",c_s≥0)`; a bad/missing staging → `(False,"ConvertError",_)` and staging still
  cleaned.
- **cog=True pipeline** (with the injected **synchronous** `convert_executor`): fake `fs.transfer`
  drops a real raster at staging; assert final `.tif` produced, staging removed, `convert_seconds>0`,
  `bytes_by_band` populated, catalog row written, and a rerun **skips** (idempotent). No subprocess.
- **Backpressure**: a controllable fake `convert_executor` whose futures block until released; run
  `download(max_staged=2, cog=True)` over several convert-items; assert **no more than `max_staged`**
  convert jobs are outstanding / staged files exist at once (instrument via the fake executor's
  in-flight count — don't race on the filesystem).
- **Lazy pool**: an all-skip pass and a `cog=False` run spawn **no** `convert_executor` (assert the
  default factory is never invoked, e.g. via a sentinel/monkeypatched factory).
- **`_default_max_staged`** unit (pure, monkeypatch `shutil.disk_usage`): tight disk shrinks toward
  `disk_cap`; roomy disk returns `headroom`; never below `MAX_CONCURRENT_S3`; warns when `< floor`.

**Manual (spec 26, not now):** the measured before/after transfer-vs-convert-split confirm-run.

## Explicitly OUT (deferred)

- The measured confirm-run run-book + `--dry-run`/`--stop-file`/progress safe-runner → **spec 26**.
- Remote-dst COG (stage→convert→**upload**) → Azure/Batch (P1/P4). This pipeline is its seam; not built.
- Dropping ingest overviews / cheaper compress (Option D) — rejected (D2).
- Any change to `to_cog`, the read/build path, discovery, or the `DownloadResult` shape.
- Tuning `MAX_STAGED`/`MAX_CONVERT_PROCS` against real throughput (that's a spec-26 measured pass).

## Docs to update on implement

- **`CHANGES.md`** — (a) conversion decoupled onto a process pool (behavior kept: still lossless COG
  **with** overviews); (b) circuit-breaker stop granularity chunk→streaming (transfer-failures only);
  (c) `chunksize` now = catalog-flush cadence.
- **`TODO.md`** — mark spec-14's "conversion process pool / decoupled CPU fan-out" follow-up **DONE
  (spec 25)**; keep remote-dst COG deferred.
- **`specs/14-cog-on-download.md`** — its "Explicitly OUT: A conversion process pool" + "CPU at
  download time … process pool is a possible future optimization → TODO" → point to spec 25.
- **`config.py`** — the two new constants' comments (above).
- **`PROGRESS.md`** + memory `fsd-status` — on implement.
- `RECIPES.md` — nothing new (no new user-facing command; the confirm-run command is spec 26).

## Confirm at sign-off (small, so nothing's missed)

- **C1** A2 pipeline + `add_done_callback` chaining + one `sem_staged` (drop a separate transfer
  semaphore — the pool already caps concurrent transfers at 4) — is that the structure you want, or
  do you prefer a simpler main-thread `wait(FIRST_COMPLETED)` scheduler (no callbacks)?
- **C2** `MAX_STAGED = MAX_CONCURRENT_S3 + MAX_CONVERT_PROCS + 4` (~16, derived) — OK, or pin a plain
  constant (e.g. 12)?
- **C3** Keep `_download_one` as the sequential wrapper (so its tests survive) even though `download()`
  won't call it — acceptable, or would you rather delete it and rewrite those tests against the two
  new stage functions?
- **C4** Circuit-breaker rewrite (streaming stop, transfer-failures-only) + rewriting
  `test_circuit_breaker_trips_and_stops_early` — good?
- **C5** Add the `max_convert_procs` / `max_staged` / `convert_executor` keyword knobs to `download`
  (+ pass-through on `download_resume`) — OK, or keep the pool purely config-driven and rely on
  monkeypatching a module-level factory in tests instead of an injected executor?
- **C6** Disk-aware `MAX_STAGED` (D5): sized once at `download()` start from
  `shutil.disk_usage(root_folderpath).free`, `STAGING_DISK_FRACTION=0.25`, `STAGING_ITEM_GB=0.2`,
  target `headroom = MAX_CONCURRENT_S3 + 2*MAX_CONVERT_PROCS` (~20), disk as a **cap not a lever** —
  good? Any preference on the fraction (0.25) / per-item estimate (0.2 GB), or would you rather keep a
  plain static `MAX_STAGED` constant and treat disk-awareness as a spec-26 measured follow-up?
