# Dispatch telemetry is a durable file beside `_status/`, not a value returned to the caller

**Status:** accepted (spec 40, grilled + agreed 2026-07-28)

**Context.** How long a dispatch spent queueing, admitting jobs, doing work, and collecting results
was, until now, never written down. It existed only in the driver process's memory: the run-books
computed `wall - slowest_shard` at the end and stored the difference, and everything finer was gone
the moment the script exited. When the local-vs-AML timing report needed that detail, recovering it
took **four separate probes** — AML's job-history API (whose `properties.StartTimeUtc`/`EndTimeUtc`
keys are undocumented), the `_result.json` files' own mtimes, blob `last_modified` stamps, and a
per-attempt reconstruction to separate three re-runs that shared one experiment name. Two of the
four numbers we most wanted were unrecoverable at any price, and one intermediate conclusion drawn
from the incomplete picture ("the overhead is the bundle upload") was simply wrong — refuted later
by a measurement showing the stage took 13 s, not 627.

The obvious fix is to return the timings: give `TrainingData` / `InferenceResult` a `timing` field.
It reads well (`result.timing.job_admission`) and needs no path construction.

**Decision.** **The dispatcher writes its own telemetry to `<run_root>/_timing.json`, beside
`_status/`, as the run proceeds. No public verb returns it and no public dataclass carries it.**
Callers that want it read the file; they already know `root` and `run_id`, because they passed them.

**Considered options.** **A `timing` field on the returned dataclasses** — rejected: it reproduces
the exact failure being fixed. A dispatch that raises returns nothing, so the timings for the work
that *did* complete die with the exception — and a failed run is precisely when you want to know
where the time went. It also changes the public API of every verb, and `create_training_data`
performs *two* dispatches inside one call, so a single returned block would have to flatten or nest
them anyway. **Both file and field** — rejected as two representations of one truth to keep in sync,
for a convenience the caller does not need.

**Consequences.** Timing survives crashes, survives the process, and stays readable months later —
`runbooks/41-recover-aml-job-timings.md` becomes a historical record rather than a procedure anyone
repeats. Because the file is written by the dispatcher rather than derived from AML, it is
**runner-agnostic**: the Azure Batch dispatcher writes the same file, and nothing depends on
undocumented AML fields (which is why the in-job entrypoints stamp their own start/end rather than
the driver reading them from the job object). The cost is that timing is no longer visible at the
call site — a caller must know the file exists — and `_timing.json` becomes a schema that anything
reading it depends on, so changing its shape is a breaking change to the demo script, the plotter,
and any future report generator.
