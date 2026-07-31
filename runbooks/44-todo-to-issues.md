---
status: current
summary: Migrate `TODO.md`'s 62 rows to number-aligned GitHub issues (`#N == TODO #N`) — the one step of spec 41 P2 that Claude cannot run, because a misnumber is permanent.
---

# Run-book: `TODO.md` → 62 number-aligned GitHub issues (spec 41 P2)

> Spec 24 template. A run-book is what Claude hands the user instead of running a
> pipeline/long/networked script itself. You run the commands and paste back each step's
> `_result.json`; Claude diffs it against the success criteria.

## Purpose

Create GitHub issues **1–62** so that **issue #N is TODO row #N**, making the 448 existing
`TODO #NN` references across specs, run-books, ADRs and `PROGRESS.md` resolve for free and
permanently (spec 41 D8).

## ⚠️ Why this one is different

**GitHub never renumbers.** One shared counter serves issues, pull requests *and* discussions.
If anything else claims a number mid-run, alignment is broken **permanently** and the only
remedy is spec 41 D8's rejected fallback (a 62-row mapping table, forever).

So, for the ~5 minutes this takes:

- **Do not open a pull request.**
- **Do not enable Discussions.**
- **Do not let anyone else touch the repo.**
- If the script halts, **stop** and paste the output. Do not "just re-run it".

## Prerequisites

- `gh` authenticated with write access to `nikhilsrajan/fsd`: `gh auth status`
- The reviewed manifest and the script, both at the **workspace root** (one level above `fsd/`):
  - `P2_ISSUE_MANIFEST.md` — the human-readable review artifact (already signed off)
  - `P2_ISSUE_MANIFEST.jsonl` — what the script actually reads
  - `todo_to_issues.py`
- Python 3.11 (`fsd/.venv/bin/python` is fine; the script has no third-party imports)

Decisions already locked (2026-07-30): **24 closed**, the **`model`** label is approved,
**#26 closed** with a fresh north-star issue to be opened *after* the migration.

## Steps

### Step 1 — dry run (zero side effects)

```bash
cd ~/NASA-Harvest/project/fetch_satdata_claude
fsd/.venv/bin/python todo_to_issues.py --dry-run
```

- **Expect:** `manifest: 62 issues, 24 to close after creation`, the label list
  (`blocked, cloud, datacube, docs, download, model, perf, stac, storage`), milestones
  `P1, P2, P3, P5`, and `would create 62 issues, then close 24`.
- **PASS if:** it prints exactly `62 issues, 24 to close` and exits 0. Nothing is created.
- **If it fails:** paste the traceback. Most likely the manifest path — the script expects
  `P2_ISSUE_MANIFEST.jsonl` next to itself.

### Step 2 — the real run

```bash
cd ~/NASA-Harvest/project/fetch_satdata_claude
fsd/.venv/bin/python todo_to_issues.py
```

- **Expect:** `preflight OK — 0 issues, 0 PRs, discussions off. Counter is at 0.`, then a live
  progress line per issue with a shrinking ETA:
  `[7/62] #7 RGB GeoTIFF save helper …  eta 3.4 min`, then `closed #2`, `closed #7`, …
- **Runtime:** ~4 min to create + ~1 min to close (a deliberate 2 s gap between creates —
  GitHub's secondary rate limits are aggressive on content creation).
- **PASS if:** the last line is `wrote …/p2_issues_result.json` and that file has
  `"pass": true` with `created: 62`, `first: 1`, `last: 62`, `closed: 24`.
- **If the preflight fails:** it exits 2 and creates **nothing**. Paste the output — alignment
  is impossible and we fall back to a mapping table.
- **If it halts with `HALT — MISNUMBER`:** it stopped at the first wrong number. **Do not
  re-run.** Paste the line; the remaining rows need the fallback.
- **If it dies partway for any other reason** (network, auth, rate limit): re-run with
  `--resume`, which continues from the highest existing issue + 1:
  ```bash
  fsd/.venv/bin/python todo_to_issues.py --resume
  ```

### Step 3 — verify the alignment independently

```bash
cd ~/NASA-Harvest/project/fetch_satdata_claude
gh issue list --repo nikhilsrajan/fsd --state all --limit 100 \
  --json number,title,state --jq 'length, ([.[].number]|min), ([.[].number]|max),
  ([.[]|select(.state=="CLOSED")]|length)'
```

- **Expect:** `62`, `1`, `62`, `24` on four lines.
- **PASS if:** all four match. Spot-check two: `gh issue view 20` should be the live-adapter
  item and `gh issue view 58` the `roi_to_s2_grids` duplicate-cell-id bug.
- **If the count is 62 but min/max are not 1/62:** alignment broke — paste the output.

## Success criteria (`_result.json`)

Step 2 writes `p2_issues_result.json` at the workspace root:

```json
{ "step": "todo-to-issues", "status": "ok", "pass": true,
  "metrics": { "created": 62, "closed": 24, "first": 1, "last": 62 },
  "expected": { "created": 62, "closed": 24, "first": 1, "last": 62 },
  "error": null }
```

**Paste this file back** (not the logs), plus step 3's four numbers.

## Stop / observe

- Progress: one line per issue with a live ETA.
- Dry-run: step 1 — full plan, zero side effects.
- Abort: Ctrl-C is safe. Whatever was created keeps its number; resume with `--resume`.

## After this passes (Claude does these — not you)

1. `TODO.md` → a ~10-line stub pointing at Issues + `docs/findings/` (D8; it is **not** deleted,
   448 references name it).
2. `CLAUDE.md` edit — it currently names `TODO.md` as a living register to keep current.
3. A new **open** issue for the P5 STACNotator north star (your call on #26, 2026-07-30) — it
   lands at #63+, outside the aligned range, which is exactly why it waits until now.
