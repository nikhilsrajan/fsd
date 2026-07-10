# Run-book: <name>

> Spec 24 template. A run-book is what Claude hands the user instead of running a
> pipeline/long/networked script itself. The user runs the commands and pastes back each step's
> `_result.json`; Claude diffs it against the success criteria.

## Handoff checklist (before starting a fresh session)
- [ ] Claude has flushed durable state to `fsd/PROGRESS.md` (+ `MEMORY.md` if needed).
- [ ] User ran `/handoff <goal>`; noted the handoff-doc path.
- [ ] Fresh session started (not `/compact`); model + effort set (Opus/high plan+debug,
      Sonnet/medium implement); pointed at the handoff doc + this spec.

## Purpose
<one line>

## Prerequisites
- venv: `.venv-modeldeploy` (or `.venv`), extras: `...`
- creds / inputs: `...`

## Steps
Each step: the exact command, what you should see, and its PASS/FAIL condition.

### Step 1 — <name>
```bash
<exact command>
```
- **Expect:** `<the key line(s) you should see>`
- **PASS if:** `<condition>` — writes `<outdir>/_result.json`.
- **If it fails / hangs:** `<how to stop — Ctrl-C is resume-safe / --stop-file>`; then paste the
  error or `_result.json`.

### Step 2 — ...

## Success criteria (`_result.json`)
Each step writes/appends to `<outdir>/_result.json`:
```json
{ "step": "<name>", "status": "ok|fail", "pass": true,
  "metrics": { "<k>": 0 },
  "expected": { "<k>": 0 },
  "error": null }
```
The run passes when every step's `pass` is true. **Paste this file back** (not the logs).

## Stop / observe
- Progress: each long step prints a live line with ETA.
- Dry-run (if supported): `<cmd> --dry-run` prints counts + cost + ETA with **zero** side effects.
- Abort: `<Ctrl-C (resume-safe) | touch <stop-file>>`.
