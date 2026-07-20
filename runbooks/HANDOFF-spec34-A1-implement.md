# Handoff — implement spec 34 Amendment A1 (baseline property per provider)

**For:** a fresh **Sonnet@medium** session. This is spec-following implementation against a
drafted amendment — small, well-bounded, no design decisions left open.
**Parent session:** an Opus@high session is running in parallel on docs/runbooks. See
**"File ownership"** below before touching anything — stay in your lane so the merge is clean.

## One-line goal

Make `offset_for_item` resolve the S2 processing baseline from **either** provider's property
(`s2:processing_baseline` for MPC, `processing:version` for CDSE STAC v1), preserving the
hard-fail when neither is present.

## Read first

1. **`specs/34-ingest-normalization-contract.md` §3a "Amendment A1"** — THE spec for this
   change. It has the property table, the exact `_BASELINE_PROPS` tuple, the rationale, and
   an explicit list of what must **not** change. Implement to it; do not re-derive.
2. §3's table rows for CDSE/MPC (already updated to name the fields).
3. This file's "Gotchas" section — one existing test *will* fail if you are careless.

## Why (the 30-second version)

`runbooks/34-download-to-blob.md --source cdse` hard-failed on every item:

```
ValueError: STAC item 'S2B_MSIL2A_20220619T100029_N0510_R122_T33UWP_20240628T011619'
has no 's2:processing_baseline' property; cannot derive the reflectance offset (spec 34 §1).
```

`config.CDSE_STAC_URL` is `https://stac.dataspace.copernicus.eu/v1/`. CDSE's v1 catalogue
(Feb 2025) **removed the satellite-specific `s2:` STAC extensions** in favour of generic ones.
A live probe of 8 items confirmed: no `s2:` keys at all; the baseline is in
**`processing:version` = `"05.10"`**, matching `N0510` in the product id. The STAC Processing
extension defines that field as *"the version of the primary processing software … for example,
this could be the processing baseline for the Sentinel missions"* — so this is the field's
documented purpose, not a coincidence. The spec's old claim that both providers carry
`s2:processing_baseline` was simply false for this endpoint. **MPC is unaffected and its
runbook leg already PASSED.**

## The change

**File: `src/fsd/sources/_s2_radiometry.py`** (the only source file that must change)

1. Add the ordered lookup tuple, first hit wins:
   ```python
   _BASELINE_PROPS = (
       "s2:processing_baseline",  # MPC / legacy CDSE — S2 STAC extension
       "processing:version",      # CDSE STAC v1 — STAC Processing extension
   )
   ```
2. Rewrite `offset_for_item` to walk `_BASELINE_PROPS` and use the first property present.
   Keep `baseline_tuple` **unchanged** — both providers use the identical `"MM.mm"` format.
3. Keep the `raise ValueError(...)` when **none** are found. See Gotchas for the message.
4. **Fix the module docstring.** Lines 2-4 currently assert *"CDSE's STAC items carry the same
   `s2:processing_baseline` property, per the S2 STAC extension both providers implement"* —
   that is the false claim that caused this bug. Replace it with the A1 fact (per-provider
   property names, same format/semantics), and reference `§3a A1`.
5. Optional, same reason: `sources/cdse.py:235`'s docstring says the offset is derived from
   "`s2:processing_baseline`, the same mechanism MPC uses". Correct it to name
   `processing:version`.

**Do NOT** add a product-id regex fallback (`N0510`), even though the id always carries the
baseline. A1 rejects it explicitly and gives the reasoning — two documented standard
properties beat a filename convention, and a silent regex would mask the next provider
metadata migration.

## Tests to add (per A1's "Tests" paragraph)

Add to **`tests/test_mpc.py`**, next to the existing baseline block (~lines 45-75). It already
holds the `_s2_radiometry` tests, so keep them together rather than starting a new file.

1. resolves from `s2:processing_baseline` alone → existing tests already cover this; keep green.
2. resolves from `processing:version` alone (the CDSE v1 shape) → `-1000` for `"05.10"`,
   `0` for `"02.14"`.
3. **precedence**: when both are present *and disagree*, `s2:processing_baseline` wins. This
   pins the ordering as a decision rather than an accident.
4. still raises when neither property is present.

`_FakeItem` (`tests/test_mpc.py:17`) hardcodes `s2:processing_baseline` in its constructor.
Extend it to also accept a `processing_version=None` kwarg that sets `processing:version`,
rather than building a second fake class. Keep it duck-typed and network-free, matching the
file's existing style.

## Gotchas (these will bite)

- **`tests/test_mpc.py:69-72` asserts `pytest.raises(ValueError, match="s2:processing_baseline")`.**
  If your new error message stops containing that literal string, this **existing test fails**.
  Simplest fix: have the message name all tried properties, e.g.
  `"... has none of ('s2:processing_baseline', 'processing:version'); cannot derive …"` —
  which keeps the substring and is genuinely more useful. Update the test if you word it
  differently, but do not weaken the assertion to a bare `pytest.raises(ValueError)`.
- **Do not switch to acquisition-date logic.** The real CDSE items are June-2022 acquisitions
  **reprocessed in June 2024** to baseline 05.10 — date-keyed logic gets all 8 wrong. A1 §
  "what does NOT change" is explicit.
- **Do not default a missing baseline to `0`.** That is literally TODO #30/#10, the bug that
  makes the `demo_e2e` archive scientifically unusable (cubes ~1000 DN high). Loud failure
  beats a quiet wrong number.
- **No network in tests.** `tests/` is fast + synthetic; the credentialed paths are runbooks.

## Verify before handing back

```bash
cd fsd
.venv/bin/python -m pytest -q            # expect 289 passed + your new tests, 3 skipped
.venv/bin/ruff check src/ tests/         # must be clean
```

Baseline before your change is **289 passed / 3 skipped**. There is one checkout, no worktree —
plain commands work, no `PYTHONPATH=src`.

## File ownership (parallel session — READ THIS)

The Opus session is editing docs/runbooks concurrently. Keep to your files and the merge is
trivial.

**Yours to edit:**
- `src/fsd/sources/_s2_radiometry.py`
- `tests/test_mpc.py`
- `src/fsd/sources/cdse.py` (docstring line ~235 only — nothing functional)

**NOT yours — the Opus session owns these, do not touch:**
- `specs/34-ingest-normalization-contract.md` (A1 is already drafted there; it is your input)
- `runbooks/34-download-to-blob.md`
- `runbooks/scripts/34_download_to_blob.py` — **already has an uncommitted local fix**
  (`_StorageStacIO` passed to `pystac.Catalog.from_file`, needed for `abfss://` hrefs). Leave it.
- `TODO.md`, `PROGRESS.md`, `MEMORY.md`

**Do not commit or push.** The user merges both sessions afterwards. If asked to commit, end
the message with `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.

## Definition of done

- `_BASELINE_PROPS` implemented; both providers resolve; hard-fail preserved.
- 4 test cases added; full suite green; ruff clean.
- The false docstring claim in `_s2_radiometry.py` is gone.
- Report back: test count before/after, and the final error-message wording (the Opus session
  needs it to confirm the CDSE runbook leg's failure mode is now the intended one).

## Out of scope (do not fix these while you are in there)

- **TODO #42** — `SourceDeclaration` does not survive a catalog write→read. Needs its own spec
  amendment; pinned by `tests/test_catalog.py::test_declaration_does_not_survive_catalog_roundtrip_todo_42`.
- **TODO #43** — `_search_items` has no retry/backoff around CDSE's flaky STAC pagination.
  Real, logged, separate; touching the call chain now would invalidate the passed MPC leg.
- Anything else in `sources/cdse.py` beyond the one docstring.
