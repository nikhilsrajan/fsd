# Findings — index

> **Why this folder:** a *finding* is a measurement write-up — what was measured, on what date,
> by what method, and what it means. These used to live as multi-page cells inside `TODO.md`'s
> table, where nobody would read them (spec 41 §1.1, D14 P3).
>
> Findings are **point-in-time** (spec 41 D3 / ADR 0022): a measurement was true on a date.
> Each carries a D4 status header. When a later measurement overturns one, write a new finding and
> mark this one `superseded-by-NN` — **do not edit the numbers**. The corrections inside these
> files are deliberate: a reading that was plausible and wrong is worth more than a clean summary.
>
> The **open work** each finding implies lives in its GitHub issue, not here.

| finding | measured | issue | what it says |
|---|---|---|---|
| [cloud-overhead.md](cloud-overhead.md) | 2026-07-28 | [#61](https://github.com/nikhilsrajan/fsd/issues/61) | 35 % of an inference run and 90 % of a merge run was the **driver** collecting results over blob — not the cluster. Attack the driver, not the cluster. |
| [workload-regimes.md](workload-regimes.md) | 2026-07-28 | [#59](https://github.com/nikhilsrajan/fsd/issues/59) | Training units are 781× smaller than inference units, so one set of fan-out defaults cannot serve both. Inference is work-bound; training is overhead-bound. |
| [consumer-repo-friction.md](consumer-repo-friction.md) | 2026-08-26, **open log** | [#78](https://github.com/nikhilsrajan/fsd/issues/78), [#80](https://github.com/nikhilsrajan/fsd/issues/80), [#82](https://github.com/nikhilsrajan/fsd/issues/82) | Eight things a `pip install` consumer hits rebuilding the AML e2e notebook — four are hard stops. The wheel is already code-only; what is missing is assets that are in **neither** the wheel nor git. |

The first two were measured from the same two runs, by the same free, read-only recovery method
(`runbooks/41-recover-aml-job-timings.md`) — no cluster time was spent to produce either.

**`consumer-repo-friction.md` is the exception to the point-in-time rule above:** it is an *open
log*, appended to as phase 2's consumer repo is built, because that friction is phase 2's
deliverable. Its individual entries are still dated and still not edited after the fact.
