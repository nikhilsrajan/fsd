# Spec 24 — working contract: I don't run scripts; you run run-books

**Status:** SIGNED OFF + IMPLEMENTED (C1 pytest-ok, C2 `runbooks/`, C3 ok, C4 25→26, C5 ok).
Landed: `CLAUDE.md` (run policy + model-split/effort + handoff) + `fsd/runbooks/TEMPLATE.md`.
**Why:** the spec-23 tiny-download run went wrong in ways that were *process* failures, not code
failures — I launched a long download, you couldn't stop it or see progress, and I burned your
tokens polling its log. This codifies a safer division of labour. Small + self-contained.

## Locked decisions (from the interview)

- **D1 — Run policy.** I **never** run pipeline / long / networked / side-effecting scripts (demos,
  downloads, snakemake, anything more than a few seconds, anything that touches the network or
  writes real data). I **may** still run fast, read-only, un-babysat checks: `ruff`, `pytest`,
  `grep`/`rg`, `ls`, `git status`, file reads. I **never** background (`nohup`/`&`) a script and
  **never** poll a running process's logs.
- **D2 — Results via a compact `_result.json`.** Anything you run emits a small machine-readable
  result file; you paste that (or the traceback). I diff it against the run-book's success criteria.
  I do **not** read live logs.
- **D3 — Model split.** Opus (me) does interview → spec → sign-off → debug → review. Implementation
  happens in a **Sonnet** session you switch to (`/model`). No subagent spawning for coding (that
  re-derives context and costs tokens — the thing we're fixing).
- **D5 — Effort & token policy** (from the Anthropic docs review). Effort is set per session with
  `/effort` (levels: low, medium, high=default, max, plus xhigh). Ours:
  | role | model | effort |
  |---|---|---|
  | interview / spec / **debug** | Opus 4.8 | **high** (xhigh/max only for a genuinely hard bug) |
  | implement a signed-off spec | Sonnet 5 | **medium** (following a clear spec is mechanical) |
  | review / lint-fix | Sonnet 5 | medium |
  Principle: **never pay Opus-max for boilerplate, never pay Sonnet-high for spec-following code** —
  a signed-off spec is what lets Sonnet run at medium safely. Plus: context window is *the*
  constraint (quality degrades as it fills) → `_result.json` not live logs (D2); handoff between
  sessions via **files** (specs / `PROGRESS.md` / `MEMORY.md`), not chat; `/compact` or a fresh
  session between workstreams.
- **D6 — Handoff protocol (uses the installed `/handoff` skill).** At a session boundary (context
  getting heavy, or plan→implement handoff, or Opus→Sonnet switch), the **user** runs
  `/handoff <what the next session does>` (the skill is user-invocable only — Claude cannot trigger
  it). It writes a distilled handoff doc (to the OS temp dir) that *references* the spec/PROGRESS/
  MEMORY by path rather than duplicating them, and lists suggested skills. The user then starts a
  **fresh** session (clean context = no rot), switches model/effort per D5, and points it at the
  handoff doc + the spec. **Durable state stays in `PROGRESS.md` / `MEMORY.md` / `specs/`** (the
  system of record); the handoff doc is the *ephemeral baton*, not a replacement for those.
- **D4 — This is spec 24, the first of a small series.** Next, separately: **spec 25** (download +
  jp2→COG redesign — conversion currently runs inline on the transfer threads and GDAL holds the
  GIL, starving downloads) and **spec 26** (a `--dry-run`/`--stop-file`/progress "safe runner"
  wrapper for the e2e). Not in this spec.

## SO-1 — Run policy in CLAUDE.md (hard rule)

Add to `CLAUDE.md` "Working style & preferences":
> **Claude never runs pipeline/long/networked/side-effecting scripts (demos, downloads, snakemake,
> anything > a few seconds or with network/side effects), and never backgrounds a script or polls
> its logs.** Claude may run fast read-only checks it doesn't babysit (`ruff`, `pytest`, `grep`,
> `ls`, `git status`, reads). Everything else is handed to the user as a **run-book** (below); the
> user runs it and pastes back the `_result.json` / error.

## SO-2 — Run-book format

Runnable work ships as a Markdown run-book (in `fsd/runbooks/<name>.md`, or the task's doc). Each has:
1. **Purpose** (one line) + **prerequisites** (venv, creds, inputs).
2. **Commands, in order** — copy-pasteable, one block per step, each with the **expected output** and
   an explicit **PASS/FAIL** condition.
3. **Success criteria** — the `_result.json` fields that must hold (SO-3), so success is *determined*,
   not eyeballed.
4. **Stop / observe** — how to see progress and how to abort cleanly (SO-4).

## SO-3 — The `_result.json` contract

Every runnable step writes (or appends to) `<outdir>/_result.json`:
```json
{ "step": "download", "status": "ok|fail", "pass": true,
  "metrics": { "granules": 7, "tiles": 1, "gb": 2.1 },
  "expected": { "tiles": 1, "granules_max": 12 },
  "error": null }
```
- `pass` = the step met its `expected`. `status` = did it complete without crashing.
- You paste this file (small); I diff `metrics` vs `expected` and report PASS/FAIL per step.
- A run writes one `_result.json` per step (array) or a top-level `{steps:[...], pass: all}`.

## SO-4 — Progress + termination requirements (for any script we ship)

Any script a run-book asks you to run **must**:
- print a **live progress line with ETA** (already the norm — `[[long-process-progress]]`);
- support **`--dry-run`/`--plan`**: print the counts + GB + ETA it *would* incur and exit **with
  zero network bytes**, so you can see the cost before committing;
- be **Ctrl-C safe** (atomic writes; a re-run resumes) **and** honor a **`--stop-file PATH`** (checks
  each iteration; exits cleanly if the file appears) so a background run is stoppable without hunting
  a PID;
- run **foreground by default** and print its PID, so you always have a kill handle.

*(The e2e already had atomic/idempotent download + progress; it was missing `--dry-run`, a stop-file,
and a compact result — those land in spec 26. Spec 24 only sets the contract.)*

## SO-5 — Model split in CLAUDE.md

Add:
> **Opus** does interview/spec/sign-off/debug/review. **Implementation runs in a Sonnet session**
> the user switches to (`/model sonnet`), against a signed-off spec; switch back to Opus for review
> and debugging. Don't spawn subagents just to write code.

## SO-6 — Effort & token policy in CLAUDE.md (D5)

Add the D5 effort table + the "context is the constraint" line to `CLAUDE.md`: Opus@high for
plan/spec/debug (xhigh/max only for hard bugs), Sonnet@medium for spec-following implementation,
`/effort` to set; `_result.json` not logs; handoff via files.

## SO-7 — Handoff protocol in CLAUDE.md (D6)

Document the `/handoff` flow in `CLAUDE.md`: **user** runs `/handoff <next-session goal>` at a
session boundary → fresh session → set model/effort (D5) → point it at the handoff doc + the spec.
Durable state stays in `PROGRESS.md`/`MEMORY.md`/`specs/`; the handoff doc is the ephemeral baton.
A tiny **handoff checklist** goes at the top of the run-book template (SO-2).

## SO-8 — Deliverables

- Edit `CLAUDE.md`: SO-1 (run policy), SO-5 (model split), SO-6 (effort/token), SO-7 (handoff) +
  note the run-book/`_result.json` contract.
- Add `fsd/runbooks/TEMPLATE.md` (the SO-2/SO-3 skeleton + the SO-7 handoff checklist).
- No code run. No pipeline touched. (Spec 25/26 do the download + runner work.)

## Confirm at sign-off (small, so nothing's missed)

- **C1** `pytest` is on my "may run" list — OK? (It's local + seconds; but it *can* import heavy
  modules. Say if you'd rather I never run it either — that was your "never run anything" option.)
- **C2** Run-book location = `fsd/runbooks/`? (vs the task's own doc, e.g. `demos/E2E_AUSTRIA.md`.)
- **C3** `_result.json` shape above good enough, or do you want a stricter schema?
- **C4** Order after this: **spec 25 (download/convert redesign)** before **spec 26 (safe runner)**?
- **C5** Handoff (D6): split right — `/handoff` doc = ephemeral baton, `PROGRESS.md`/`MEMORY.md`/
  `specs/` = durable system of record?
