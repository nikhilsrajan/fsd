# Download is one continuous pipeline with disk-aware `MAX_STAGED` backpressure; the convert pool is processes

**Status:** accepted (spec 25, decisions locked 2026-07-11)

**Context.** A CDSE tile download has two stages with different profiles: **transfer** (S3, I/O-bound,
GIL-light — threads) and **jp2→COG convert** (CPU + GDAL, GIL-heavy, ~15 s/file with overviews). A
naive design lets staged JP2s pile up to ~`chunksize` (~4–8 GB peak) — unsafe on a tight disk (the
workspace runs near full).

**Decision.** One **continuous pipeline** (transfer stage → convert stage) with an explicit
**`MAX_STAGED` cap** — a **safety cap, not a throughput lever** — sized **once at `download()` start
from free disk** (disk-aware, not a static constant). Throughput is `min(transfer_cap, convert_cap)`
once both pools are fed, so a larger buffer buys no throughput; free disk therefore *caps* the buffer.
The **convert pool is processes** (`ProcessPoolExecutor`), `MAX_CONVERT_PROCS = min(cpu_count(), 8)`
(measured knee at 8), **spawn** start-method (GDAL-safe, portable to Linux/Batch). Ingest keeps
overviews (`COG_OVERVIEWS="AUTO"`) — the price of TiTiler-ready raw-band COGs.

**Considered options.** **Per-chunk drain (A1)** — rejected: lets staged files reach ~`chunksize`,
unsafe on a tight disk. **Grow the buffer for throughput** — rejected: no gain once pools are fed;
it trades disk for nothing. **Drop ingest overviews to speed convert** — rejected: the user wants
TiTiler-ready COGs.

**Consequences.** Disk stays bounded regardless of throughput or CDSE flaky-window stalls. The lone
benefit of a fuller buffer (riding out transfer stalls while converts drain) is exposed as a
`max_staged=` override, not the default. The production-optimal value is a **measured** question,
deferred to the instrumented confirm-run in spec 26.
