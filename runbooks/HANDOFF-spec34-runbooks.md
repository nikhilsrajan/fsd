# Handoff — RUN the two spec-34 runbooks (clean session)

**For:** a fresh session (Opus@high, or Sonnet@medium — this is run-and-verify, not
design). The spec-34 review-and-fix pass is **DONE**; nothing is left to implement.
Your job is to shepherd the user through the two runbooks and diff the pasted
`_result.json` against each runbook's own success criteria.

## State of the repo (read this first — it changed)

- **ONE checkout, no worktrees.** The spec-34 work used to live in
  `fsd/.claude/worktrees/spec34-ingest-normalization`. That worktree and its branch
  `worktree-spec34-ingest-normalization` were **merged into `main`'s working tree and
  removed** (2026-07-20), content verified identical file-by-file first. Work from
  `fsd/` directly.
- **The `PYTHONPATH=src` gotcha from earlier handoffs is GONE.** `fsd/.venv`'s editable
  install points at `main`'s `src/`, which is now the only `src/`. Plain commands work:
  ```bash
  cd fsd
  .venv/bin/python -m pytest -q          # 289 passed, 3 skipped
  .venv/bin/ruff check src/ tests/       # clean
  ```
- **Spec 34 is COMMITTED AND PUSHED to `main`** (2026-07-20, at the user's request).
  `origin/main` has it, so a fresh `git clone` on a VM gets it with no checkout step.
  Only the two/three kept-out notebooks remain uncommitted (user preference).
- Stale branches `spec32-mpc-implement` and `specs-28-29-impl` are already merged into
  `main` and can be deleted whenever (`git branch -d`), cosmetic only.

## Runbook-1 clone step — RESOLVED

An earlier draft of this handoff flagged a blocker: the runbook said
`git checkout <this-branch>` for a branch that no longer existed, against uncommitted
code. That is fixed — spec 34 is on `origin/main`, and the runbook's step 0 now just
clones and sanity-checks `src/fsd/catalog/declaration.py` exists. Nothing to decide.

## The two runbooks, in order

1. **`runbooks/34-download-to-blob.md`** — cloud-VM-first, CDSE + MPC each land a
   self-describing COG slice (`T33UWP`, one band + SCL) on the `rise` blob. Verifies
   GDAL tag + STAC `raster:bands` offset, nodata declared, `abfss://` catalog paths.
   Writes `tests/outputs/spec34_download_to_blob/_result_<source>.json`.
   - Known limitation, already documented in the runbook: **CDSE with a remote `--dst`
     is not per-file resumable** (whole-run batch push — TODO #31 covers true
     streaming). MPC is idempotent/resumable. Small slice, so a from-scratch retry is
     cheap.
2. **`runbooks/34-mini-mpc-cross-baseline.md`** — local copies + spec 30's mini-MPC
   docker stack (pgSTAC + titiler-pgstac); register one search, request tiles with
   `unscale=true`, eyeball **one XYZ URL with no baseline seam**. This is spec 34 §1e's
   acceptance — the harmonization MPC itself cannot give.

**Process rules (CLAUDE.md / spec 24):** the *user* runs these. Claude never runs
pipeline/networked/long scripts, never backgrounds them, never polls logs. The user
pastes back `_result.json` and you diff it against the runbook's own `expected` block —
never read live logs, never trust a bare `"pass": true` (spec 32's runbook v1 proved a
pass flag can lie; verify the metrics themselves).

## What the review pass found (don't re-derive)

Full detail in `PROGRESS.md`'s top entry. Summary: the implementation is sound — **no
implementation defects** across two independent review passes. Fixed this pass: 2 hard
Standards violations (mid-function imports in `catalog/stac.py` and `sources/cdse.py`)
+ 2 DRY nits in `stac.py`. Added 10 spec-§4 tests (279 → 289).

**One real gap, logged as TODO #42 — know it, but it does not block either runbook.**
The collection-level `SourceDeclaration` (mask band/type/**classes**, reference band,
mosaic method) rides on `GeoDataFrame.attrs["declaration"]`, and GeoParquet does **not**
persist `.attrs` — verified: a catalog write→read returns `attrs == {}`, after which
`build_datacube` silently falls back to `S2_L2A_DECLARATION`. Spec 34 §2a places the
mask spec in "catalog/collection metadata" and §4 asks that mask classes survive
write→read, so this is a genuine spec-vs-implementation gap. Per-row `offset`/`nodata`
**do** round-trip (real catalog columns) and roles are re-derived on every STAC export,
so those parts of §4 genuinely hold. Harmless today (both shipped sources *are* S2 L2A,
so the fallback is coincidentally correct); **silently wrong for the first non-S2
source**. Closing it means deciding which artifact is authoritative (STAC Collection vs.
a sidecar next to the catalog parquet) — a **spec-34 amendment**, not a patch, so it was
deliberately not fixed in a fix-up pass. Pinned meanwhile by
`tests/test_catalog.py::test_declaration_does_not_survive_catalog_roundtrip_todo_42`,
which fails loudly if the behavior moves in either direction.

## Definition of done for that session

- The runbook-1 branch/rsync blocker resolved with the user before any VM work.
- Both runbooks run by the user; both `_result.json` diffed against the runbook
  criteria (metrics, not the pass flag) and reported PASS/FAIL.
- `PROGRESS.md` + memory `[[fsd-status]]` updated with the run outcomes.
- If both pass: spec 34 is closeable → TODO #38 fully closed, and TODO #42 is the
  named follow-up (needs a spec amendment, likely alongside the ERA5/CHIRPS spec that
  first makes it load-bearing).

## Do NOT

- Re-run `code-review` on this diff — two passes are done and captured in `PROGRESS.md`.
- Re-open `grilling`-settled design decisions.
- Commit or push without the user explicitly asking. If asked, end the message with
  `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.
- Edit `fetch_satdata/`, `rsutils/`, `cdseutils/`, `raapid-infra/`, `rslearn/`.
