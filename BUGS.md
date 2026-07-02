# BUGS — manual-review register

Living record of bugs that need **human evaluation** (esp. anything touching real
credentials, live services, or geospatial correctness the user wants to eyeball).
Add a section per bug. Status: `OPEN` · `INVESTIGATING` · `RESOLVED` · `WONTFIX`.

---

## BUG-001 — CDSE S3 intermittent auth errors (server-side, not fsd)

**Status:** ROOT CAUSE IDENTIFIED (CDSE server-side infra) → **largely designed out.**
The worst offender was the recursive **S3 `.SAFE` listing** during file-selection;
`fsd` now discovers band S3 hrefs from the **CDSE STAC API** (`pystac-client`,
anonymous) instead, so it **never lists over S3**. The only remaining S3-auth op is
the per-file byte `transfer`, which retains a **fail-fast retry** (`_download_one`)
for the residual intermittency. Full analysis:
`debug-attempts/s3_paths_fetch/cdse_s3_intermittent_auth_report.md` (+ repro script
`s3_paths_fetch_test.py`).
**Found:** 2026-07-01, live-testing `fsd.sources.cdse.download`.
**Resolved (listing):** 2026-07-01 via the STAC pivot (see CHANGES.md).

### Root cause (from the user's multi-run debug)
Listing CDSE S3 objects intermittently returns `SignatureDoesNotMatch` **or**
`InvalidAccessKeyId`, yet the **same keys + same code fully succeed on other runs**
(the run table shows success interleaved with both error codes). The decisive
evidence: the repro uses the **legacy boto3** `Bucket("eodata").objects.filter(
Prefix=...)` — the known-good reference — and it **also fails intermittently**. So
the earlier "s3fs recursive-signing" hypothesis is **wrong**; my shallow-ls-ok /
recursive-glob-fail observation was good-window vs bad-window luck, not a
delimiter/recursion effect.

Three distinct outcomes (success / `SignatureDoesNotMatch` / `InvalidAccessKeyId`)
from identical inputs can only come from **inconsistent credential state across
CDSE's load-balanced cluster nodes** (node fully replicated → success; node missing
key → `InvalidAccessKeyId`; node with stale/partial state → `SignatureDoesNotMatch`).
Service moves in good/bad **windows** (bad windows stack retries → ~120 s/URL).
Corroborated by a CDSE community-forum report of the same pattern (~June 2026).

### Also cleared up along the way
- The initial `InvalidAccessKeyId` was **not** simply stale keys (regenerating did
  not stop the alternation) — it's the same intermittent server-side issue.
- The catalog's `L2A_N0500` s3url is **correct** (the `L2A`-without-baseline variant
  404s). URL was never the problem.

### Ruled out (do NOT re-investigate — settled in the report)
S3 key validity/expiry · wrong/special-char secret · clock skew · rate-limit math
(429 ≠ these errors) · boto3≥1.36 checksum change · missing session token · boto3
resource-vs-client / pagination · s3fs-vs-boto3 signing · the URL/region/addressing.

### Fix direction — client resilience (accepted approach from the report)
Make the S3 listing/transfer resilient to transient failures rather than trying to
eliminate them:
- Treat `{SignatureDoesNotMatch, InvalidAccessKeyId, SlowDown, AccessDenied}` as
  **retryable** (permanent on real AWS, transient on CDSE).
- **Fail fast per URL** (~3 tries, 2s/4s backoff + jitter), then skip.
- **Checkpoint** completed work so reruns resume and skip done items.
- **Circuit breaker**: after ~N consecutive failures, stop (bad window) and rerun
  later.
- **Parallelize** good windows; pin the OTC endpoint
  (`https://eodata.ams.dataspace.copernicus.eu/`) + reuse one client to cut routing
  variance.

### Done (2026-07-01)
- ✅ **Listing eliminated** — discovery + band hrefs now come from the STAC API; no
   S3 `.SAFE` listing (removes most S3-auth exposure).
- ✅ **Retry lives in `sources/cdse`** (`_download_one` + `_RETRYABLE_S3`), not the
   provider-agnostic storage seam — so a future AWS/Azure backend won't retry genuine
   auth errors. Custom retry (botocore treats these codes as non-retryable).
- ✅ **Fail-fast per file** — 3 tries, `2s·2^n` + jitter, on the 4 CDSE-transient codes.
- ✅ **OTC-pinned endpoint** — `config.CDSE_S3_ENDPOINT_URL = eodata.ams…`.
   Live-confirmed 2026-07-01: OTC endpoint did `ls`+`GET` fine while the GSLB alias
   (`eodata.dataspace…`) returned `SignatureDoesNotMatch`/`Forbidden` in the same
   minute — and OTC itself 403'd 5× then cleared (the windowing). A 1-file B08
   download succeeded through `_download_one`.
- ✅ **Catalog is the checkpoint** — chunked, `files`-unioning append; idempotent
   (skips files already on disk).

### Measured at scale (2026-07-02) — see `benchmarks/download_report_2018_ethiopia.md`
First 1-year batch (579 tiles, 4 bands): during a **sustained bad window**, file-level
success was only **~22.5%** (623 ok / 2152 fail of 2776), **80/579 tiles complete** in
one pass. Making `Forbidden` retryable moved an earlier **0%** pass to ~22.5%, but
in-run retries can't beat a bad window — confirms **fail-fast + resume-later** over
grinding. Idempotent per-chunk catalog made the killed run fully resumable.

### Still open (revisit if downloads prove flaky at scale)
- ✅ **Circuit breaker + resume-loop DONE (2026-07-02).** `download(max_consecutive_failures=N)`
  trips (`circuit_tripped`) on a bad window; `download_resume(...)` re-runs idempotently
  until a clean pass (trip → `cooldown_s` back-off, partial → immediate retry), with an
  `on_pass` hook to persist per-pass stats. Needs a real at-scale re-run in a good window
  to confirm convergence.
- **Concurrency**: currently `config.MAX_CONCURRENT_S3 = 4` (CDSE's documented quota);
  the report ran `≈6` fine. Keep configurable; tune with real runs.
- **Retryable set**: bad windows also surface a bare `Forbidden`/`403` (seen
  2026-07-01), which `_RETRYABLE_S3` does NOT currently include (to avoid masking
  genuine permission errors). Reconsider adding it during at-scale tuning (TODO #9).
- **Per-tile restructure**: `download` still builds one flat work list then chunks it.
  Fine for now; per-tile atomic units would make partial-window resume cleaner.

### Actions outside fsd (user)
- Report the run log to CDSE (their infra; only they can fix server-side).
