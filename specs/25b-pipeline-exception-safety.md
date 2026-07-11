# Spec 25b — download pipeline: exception-safe callbacks (no silent hang)

> **Status: SIGNED OFF (2026-07-11) — awaiting implementation.** Opus@high (review→spec).
> C1–C6 all accepted **as recommended** (clean-stop on broken pool + additive
> `pool_broken`; `"PoolBroken"` breaker-neutral; resume retries no-cooldown; flush off the
> lock; watchdog-thread no-hang tests). A defect found in the Phase-1 review of the spec-25
> implementation (commit `76b2cd9`), not covered by any existing test. Small, contained
> follow-up to spec 25 (same two files). Implementation lands in a **Sonnet@medium** session
> against this spec, per spec 24 D5. No network run (the measured confirm-run is still
> **spec 26**).

## Motivation — the defect (found in Phase-1 review, 2026-07-11)

`sources/cdse.py::download` drives a two-hop pipeline (transfer thread pool → convert
**process** pool) whose completion is tracked by a hand-rolled counter (`state["remaining"]`)
+ a `threading.Event` (`all_done`). The invariant the drain relies on is: **every submitted
work item decrements `remaining` exactly once, and every acquired `sem_staged` permit is
released exactly once.** The current callbacks (`_on_transfer_done`, `_on_convert_done`,
`_finalize`) satisfy this only on the *happy path* — they assume `fut.result()` never raises,
`pool.submit()` never raises, and the catalog flush never raises. For the **process** pool
those assumptions are false:

- **Broken process pool.** If a convert worker dies hard — GDAL **segfault** on a malformed
  granule, or the **OOM-killer** on a ~110 km band (both realistic at the scale spec 25
  exists to fix; `_convert_one`'s `try/except` catches GDAL *exceptions* but not a process
  death) — `concurrent.futures` marks the pool **broken**. Then:
  - `cfut.result()` in `_on_convert_done` raises `BrokenProcessPool` **before**
    `sem_staged.release()` and **before** `_finalize` → the permit leaks *and* `remaining` is
    never decremented.
  - Once broken, `pool.submit(...)` in `_on_transfer_done` raises synchronously → same leak,
    for every subsequent convert-eligible item.
- **Callbacks swallow the exception.** `Future.add_done_callback` logs a callback exception
  and does **not** propagate it. So `remaining` never reaches 0, `all_done.set()` never fires,
  and the main thread blocks on `all_done.wait()` **forever** — the `finally` that shuts the
  pools down is never even reached. A silent, uninterruptible hang.
- **Second trigger, same shape:** `_finalize` calls `_append_downloaded` → `catalog.append`
  (a parquet write) **under the lock**, *before* `state["remaining"] -= 1`. A write error
  (disk full, transient FS fault) on a chunk-flush raises → `remaining` leaks → same hang.

**Why this blocks spec 26.** Spec 26's whole premise is *"a long download run can be started,
monitored, and stopped safely."* A silent hang with no `wait()` timeout and an unreachable
`finally` is exactly that failure mode — and it originates here, in spec-25 code, not in the
runner. Tests miss it because the injected `_SyncExecutor`/`_BlockingConvertExecutor` never
break and never raise on `.result()`. Fix it before the confirm-run rather than discover it
as a mystery hang against real CDSE traffic.

## The invariant to guarantee (the whole point)

> For **every** work item for which `remaining` was incremented, `_finalize` runs **exactly
> once**; for **every** `needs_convert` item that acquired a `sem_staged` permit, that permit
> is released **exactly once** — regardless of any exception raised by `fut.result()`,
> `pool.submit()`, `cfut.result()`, or the catalog flush.

Corollary: the `remaining` decrement and the `sem_staged` release must **never** sit behind a
fallible call (pool submit, process result, parquet write) that can raise before them.

## Changes (contained to `sources/cdse.py` + a 1-field additive change to `DownloadResult`)

Nothing outside `download()`'s inner callbacks + `DownloadResult` changes. `_transfer_one`,
`_convert_one`, `_download_one`, discovery, `to_cog`, `download_resume`'s structure (one new
branch), `sum_results` are untouched except where noted.

### 1. `_on_transfer_done` — guard `fut.result()` and the convert hand-off

- Wrap `fut.result()`: on the (not-expected — `_transfer_one` is fully wrapped) chance it
  raises, treat as a transfer failure (`ok=False`, `reason=_error_reason(e)`, zero metrics)
  and fall through the normal failure path (which releases the permit if `needs_convert` and
  finalizes). Never leak.
- Wrap the convert hand-off (`_get_convert_pool()` + `pool.submit(...)`). If it raises
  (broken pool / interpreter shutdown): set `state["pool_broken"] = True` (under `lock`),
  **release the permit** (this item acquired one — `needs_convert` is True on this branch),
  and `_finalize(tid, src, dst, ok=False, reason="PoolBroken")`. Then return — do **not** add
  a convert callback (there is no `cfut`).

### 2. `_on_convert_done` — guard `cfut.result()`, release in `finally`

- Wrap `cfut.result()`: on `BrokenProcessPool`/any exception, set `ok=False,
  reason="PoolBroken", c_s=0.0` and `state["pool_broken"] = True` (under `lock`).
- Release `sem_staged` in a `finally` so it happens on **every** path (this callback always
  corresponds to a `needs_convert` item that holds a permit).
- Then `_finalize(...)` as today. (If `_finalize` is made leak-proof per §3, an exception in
  it still can't strand `remaining`.)

### 3. `_finalize` — decrement `remaining` before any fallible I/O; flush off the lock

- Under `lock`: append to `pending_results`, bump counters/failures/`done`, decide
  `emit_now`, **decrement `remaining`**, compute `drained`. If the chunk threshold is hit,
  **snapshot `pending_results` into a local list and `clear()` it under the lock** — but do
  **not** call `_append_downloaded` while holding the lock.
- **Outside** the lock: if a snapshot was taken, `_append_downloaded(catalog, tile_meta,
  snapshot)` and add its return to `state["successful"]` (under `lock`). On failure, log a
  warning and re-extend `pending_results` (under `lock`) so the end-of-run flush retries it —
  a dropped row is anyway recovered by `download_resume`'s idempotent-skip on the next pass.
- Set `all_done` if `drained`, as today.

Net effect: `remaining` and `sem_staged` accounting are now **independent of** the parquet
write and the process pool — the two things that can raise. This removes the hang and, as a
bonus, stops serializing every metric update behind the chunk-flush parquet write.

The **end-of-run** flush (after `all_done.wait()`) is likewise wrapped in `try/except` with a
loud warning (it already runs outside the worker threads).

### 4. `DownloadResult` — one additive field + wire it through

```python
pool_broken: bool = False   # convert process pool died mid-run (segfault/OOM); resume with a fresh pool
```

- Additive, defaulted → backward compatible (no existing constructor/asserts change).
- `download()` sets it from `state["pool_broken"]` in the returned result.
- `sum_results` ORs it across passes (same one-liner as `circuit_tripped`).
- Submit loop stop condition becomes `if state["tripped"] or state["pool_broken"]: break`
  (both the top-of-loop check and the post-`acquire` check). A broken pool halts new work
  cleanly; in-flight transfers still drain (their convert hand-off fails fast → `PoolBroken`).

### 5. `"PoolBroken"` reason semantics

- Counted in `failed_count` / `failures` / `reason_counts` — like `"ConvertError"`.
- **Does not** touch the transfer circuit breaker's consecutive counter (it is a local/infra
  fault, not a bad CDSE window — identical rationale to `ConvertError`, spec 25 C4).

### 6. `download_resume` — retry a broken-pool pass (no cooldown)

- Today's completion check is `if r.failed_count == 0 and not r.circuit_tripped: break`.
  A `pool_broken` pass has `failed_count > 0`, so it already loops — **but** confirm it does
  **not** take the `circuit_tripped` cooldown (a broken pool is not a CDSE window; retry
  immediately with a **fresh** pool — each `download()` call builds its own lazy pool).
- Bounded by `max_passes` as today. A *deterministic* crash (one granule always segfaults
  GDAL) will re-break each pass and exhaust `max_passes` with that granule named in
  `failures` — acceptable and surfaced; smarter per-granule quarantine is **out** (TODO).

## Test plan — `pytest` only (Claude may run it; no network)

All new tests use injected fake executors + a **watchdog thread** to prove no-hang without a
`pytest-timeout` dependency: run `download(...)` in a `threading.Thread`, `join(timeout=…)`,
and `assert not thread.is_alive()` (fail = hang) before asserting on the result.

1. **`pool.submit` raises → no hang, finalized as failure.** `convert_executor` whose
   `submit()` raises `BrokenProcessPool`. Several convert-items. Assert: `download` returns
   (watchdog), `result.pool_broken is True`, every item accounted (`successful + failed ==
   total_count`), `reason_counts["PoolBroken"] > 0`, and the submit loop **stopped early**
   (`pool_broken` halts it — `total_count` may be < len(work)). No leaked permit (the run
   completing at all proves the semaphore didn't deadlock).
2. **`cfut.result()` raises → no hang, permit released.** `convert_executor` whose `submit()`
   returns a Future already completed with `BrokenProcessPool` (so `_on_convert_done` fires
   and `.result()` raises). Assert no-hang, `pool_broken`, `"PoolBroken"` recorded, permit
   released (run completes with `max_staged` small so a leak would deadlock).
3. **`PoolBroken` does not trip the transfer breaker.** With `max_consecutive_failures` set,
   a run whose *converts* all fail via a broken pool must have `circuit_tripped is False`
   (consecutive counts only transfer failures).
4. **Catalog-flush failure doesn't hang or lose the drain.** Monkeypatch `_append_downloaded`
   to raise on first call; `chunksize` small so it fires mid-run. Assert `download` returns
   (watchdog), all items finalized, a warning logged; a subsequent normal pass writes the
   catalog (idempotent-skip recovery).
5. **Regression:** all 42 `test_cdse.py` tests still pass unchanged (the happy-path structure
   is preserved; `pool_broken` defaults False everywhere).
6. **`sum_results` ORs `pool_broken`** (extend `test_sum_results_aggregates` or add a case).

## Docs to update on implement

- **`CHANGES.md`** — append under the spec-25 entry: pipeline callbacks are now
  exception-safe (a dead convert pool / catalog-write error can no longer hang `download()`);
  new `DownloadResult.pool_broken`; `"PoolBroken"` reason (breaker-neutral, like
  `ConvertError`); chunk-flush moved off the lock.
- **`TODO.md`** — add "per-granule convert quarantine (a deterministically-crashing granule
  re-breaks the pool every resume pass)" as deferred.
- **`PROGRESS.md`** + memory `fsd-status` — on implement (spec 25b landed; spec 26 next).
- **`specs/25-download-convert-redesign.md`** — one-line pointer to 25b under its status line
  (the hang was a gap in 25's callback design).

## Explicitly OUT (deferred)

- The measured confirm-run / safe-runner (`--dry-run`/`--stop-file`/progress) → **spec 26**.
- Per-granule quarantine of a granule that repeatedly breaks the pool → TODO (bounded by
  `max_passes` for now).
- The `WorkItem` dataclass refactor (unify the `{src,dst,tid}` positional orderings across
  the two callbacks) — a *maintainability* cleanup surfaced in review, not a correctness fix;
  do it here only if trivial, else leave for a later tidy (don't expand this spec's blast
  radius).
- The `MTD_TL.xml` sidecar counting toward `bytes_downloaded` — a metric-purity nit for the
  spec-26 measured pass to be aware of; not changed here.
- Any change to `_transfer_one`, `_convert_one`, `to_cog`, discovery, or the
  transfer-circuit-breaker semantics.

## Confirm at sign-off

- **C1 — the core fix** (§1–§3): exception-safe callbacks so every submitted item finalizes
  once and every permit releases once, with `remaining`/`sem_staged` moved off any fallible
  call (pool submit, process result, parquet write). Structure OK?
- **C2 — broken-pool → clean stop** (§4): add `DownloadResult.pool_broken` (additive) and
  halt the submit loop on a broken pool, rather than the simpler "finalize each as failure
  and keep transferring granules that then can't convert." Recommended: the clean stop (avoids
  transferring hundreds more un-convertible granules; `download_resume` retries with a fresh
  pool). Agree, or prefer the minimal keep-going variant with **no** new field?
- **C3 — `"PoolBroken"` is breaker-neutral** (§5), counted in `failed`/`failures` but not the
  consecutive counter (same as `ConvertError`). Good?
- **C4 — `download_resume` retries a `pool_broken` pass with no cooldown** (§6), bounded by
  `max_passes`, no per-granule quarantine (TODO). Good, or would you rather a broken pool be
  **terminal** (stop the resume loop and report), on the theory it's likely a deterministic
  crash?
- **C5 — flush off the lock** (§3): snapshot-and-clear under `lock`, `catalog.append` outside,
  re-queue on failure. OK, or keep the append under the lock and fix the hang *only* by
  wrapping (smaller diff, but the parquet write keeps serializing with metric updates)?
- **C6 — no-hang test via a watchdog thread + `join(timeout)`** rather than adding a
  `pytest-timeout` dependency. OK?
