---
status: current
summary: Name a datacube run folder from the requested window rather than each cell's actual acquisitions (#68), and drop grid cells that another cell already fully covers (#69).
---

# Spec 46 — run addressability + grid-cell de-duplication

**Status: ✅ SIGNED OFF 2026-08-19 — NOT YET IMPLEMENTED.** Written against issues **#68** and
**#69**, both raised by the user from the AT_ROI cluster run. Both numbers below were **measured
this session**, not inferred. §6 Q1 was answered by the user at sign-off: **the folder name encodes
`mosaic_days`** — D2 is in. The two secondary questions were resolved with the defaults recorded in
§6. Implementation is a **Sonnet session at `/effort medium`** (§8); nothing in `src/` is touched
yet.

> **The one sentence:** a run's path should be a function of what was **requested**, and a work
> unit that another work unit already covers should not be dispatched.

---

## 1. Two defects, measured

### #68 — one run, two date-range folders

`workflows/create_datacube.py:147-151` builds each cell's export path as

```
run_folderpath / f"{actual_start:%Y%m%d}_{actual_end:%Y%m%d}" / <id>
```

where `actual_start` / `actual_end` are that **cell's own** min/max acquisition in the filtered
catalog. The calendar anchor that decides the cube's shape is *not* those dates — the same function
passes the **caller's** `startdate`/`enddate` into the task row, with the comment "so all shapes
mosaic on the same grid" (spec 15). So the axis is request-derived and the path is data-derived.

Observed on AT_ROI (300 grid cells), verbatim from the notebook: two folders for one run —
`20180404_20180928` and `20180406_20180928`. Consequences:

- a run is not addressable by the parameters that defined it;
- cells of one run look like two runs to anything walking the tree;
- the folder name implies a window the cube does not actually have (the cube's `T` comes from the
  requested window), so the path **misinforms**.

This was harmless while cubes did not respect the requested window. Calendar-aware mosaicing
(spec 15) made it wrong.

### #69 — 8 of 9 dispatched cells were redundant

Measured on `shapefiles/s2grid=476da24.geojson` with `fsd.grid.roi_to_s2_grids` (default
`grid_size_km=5` → res 11, `scale_fact=1.1`, `clip=True`):

| cells emitted | share of the ROI each covers | fully covered by another cell |
|---|---|---|
| 9 | one at 100 %, eight at 0.8–9.1 % | **8 of 8** non-central cells, all by `476da24` |

The mechanism: the ROI *is* cell `476da24`; `polyfill` runs on its **convex hull**, so the cell's 8
neighbours come back too; `intersects` keeps them (they share a boundary); scaling by 1.1 and
clipping to the ROI leaves them as slivers **inside** the ROI — every one of which the scaled
central cell already covers. Nine per-cell tasks, one cell's worth of information: **89 % waste**,
and on a small ROI that is the entire run.

## 2. Scope

**In:** the export-path template in `create_datacube.setup`; a de-duplication step at the end of
`grid.roi_to_s2_grids`. **Out:** the S2 level/scale/clip policy itself (unchanged); `#66`'s stale
`input.csv` (a different mechanism); any change to the calendar-mosaic contract (spec 15).

## 3. Decisions

### D1 — the run folder is named from the requested window (#68)

```
run_folderpath / f"{startdate:%Y%m%d}_{enddate:%Y%m%d}" / <id>
```

One folder per run, for every cell, derived from the same pair that determines `T =
ceil((end-start)/mosaic_days)`. The **depth stays two levels**, which matters: `api.py:1105` globs
`run_folderpath/*/*/output.tif` and its docstring already carries a ⚠️ naming this layout a
*contract* with `create_datacube.setup`. D1 keeps that contract; it only makes the middle component
constant within a run.

`actual_start`/`actual_end` are not lost — they are properties of the data and belong in the cube's
metadata, where a consumer can read them, not in the path, where they masquerade as the request.

### D2 — the window component encodes `mosaic_days` too [SIGNED OFF — user, 2026-08-19]

`{start:%Y%m%d}_{end:%Y%m%d}_m{mosaic_days}`, e.g. `20180401_20180930_m20`. Two runs over the same window with different `mosaic_days` produce
cubes with **different `T`** and today would collide cell-for-cell inside one run folder. Naming
`mosaic_days` makes the folder identify the cube contract completely. Costs one uglier path
component; the glob depth is unchanged.

### D3 — back-compat: forward-only, no migration

Existing archives keep their actual-date folder names. Nothing rewrites them.

- **Inference-output reuse survives**: the `*/*` glob spans any middle component, so previously
  written `output.tif`s are still found (`api.py:1099` says so explicitly).
- **Datacube reuse does not exist** to break: `setup` has no "cube already present, skip" path — it
  re-prepares every shape and the runner decides. Verified this session.

So the observable cost is that a re-run of an *old* run under the new name writes a new folder.
That is acceptable and must be stated in `CHANGES.md`.

### D4 — `roi_to_s2_grids` drops a cell that another cell already fully covers (#69)

After clipping, remove any cell whose geometry is **covered by** another cell in the same set.

- **The predicate is `covered_by`, not `contains`, and not IoU.** Measured: on the 476da24 case
  `contains` caught only **2 of the 8** redundant cells, because a clipped sliver *shares boundary*
  with the cell covering it and `contains` excludes boundary (shapely/DE-9IM: `covers` is
  `[T*****FF*]`, the boundary-inclusive form; `contains` is not). The user's original suggestion —
  "remove the smaller geometries which have IoU of 1" — is the right instinct with the wrong metric:
  IoU is 1 only for *identical* geometries, which none of the 8 are.
- **Ties are broken deterministically**: of two mutually covering (i.e. equal) cells, keep the
  smaller id. Without this a naive pass drops **both**.
- **Coverage is provably preserved**: a dropped cell is a subset of a kept cell, so the union of the
  output is unchanged. That is the whole safety argument.

**Cost, measured:** on the 300-cell AT_ROI the same rule runs in **0.09 s** (shapely STRtree) and
drops **1** cell — a genuine redundancy, not a regression. So D4 is ~a no-op on normal ROIs and
removes 89 % of the work on the degenerate one.

### D5 — the drop is reported, never silent

`roi_to_s2_grids` prints e.g. `[grid] 9 cells -> 1 after dropping 8 already covered`. A function
that quietly returns fewer work units than the geometry suggests is its own debugging problem, and
the repo's rule is that consequential decisions are visible (memory `long-process-progress`).

## 4. Acceptance criteria

1. Every cell of one `create_training_data` / `create_datacube` run lands under **one** window
   folder, named from the caller's `startdate`/`enddate` (+ `mosaic_days` if Q1 says so).
2. `api.py`'s `*/*/output.tif` glob and its ⚠️ docstring are updated in the same commit, and
   previously written outputs are still found.
3. `roi_to_s2_grids(shapefiles/s2grid=476da24.geojson)` returns **1** cell, id `476da24`.
4. `roi_to_s2_grids(shapefiles/AT_ROI.geojson)` returns **299** (300 − 1), and the union of the
   returned geometries equals the union before de-duplication (to a tolerance).
5. A synthetic test covers the mutual/equal-cell tie-break: two identical cells → exactly one kept,
   deterministically.
6. `pytest -q` and `ruff check src/ tests/ demos/ examples/` clean.
7. `CHANGES.md` records both behaviour changes; `RECIPES.md`'s AT_ROI cell counts are re-checked.

## 5. Risks

- **A path change invalidates muscle memory and any external script** that globs the old layout.
  Mitigated by keeping the depth identical (D3) and by `CHANGES.md`.
- **D4 could drop a cell a user wanted** if they deliberately passed overlapping ROIs expecting one
  task each. `roi_to_s2_grids` is explicitly not that function — its docstring already says an ROI
  is one region and "if you want one datacube per *shape*, that is not this function". Related and
  already closed: #58 (duplicate ids for a multi-polygon ROI), the same function, a different
  duplication mode.
- **O(n²) worst case** if the STRtree degenerates. Bounded in practice: 300 cells → 0.09 s.

## 6. Questions at sign-off — all resolved

1. **D2: include `mosaic_days` in the folder name?** → **YES** (user, 2026-08-19). The folder now
   identifies the cube contract completely: same window + different `mosaic_days` = different `T` =
   a different folder, instead of a silent cell-for-cell overwrite. Folded into D2.
2. **Skip gridding when the ROI is exactly one S2 cell?** → **NO** — do not special-case it. D4
   already collapses that ROI to its single cell, and a dedicated "is this ROI exactly a cell?"
   predicate is a second code path to keep correct for a case the general rule handles (KISS/YAGNI,
   `fsd-demo-target`). Default resolved by Claude.
3. **Write `actual_start`/`actual_end` into the cube's metadata?** → **YES, in the same change.**
   They are real information about the data, and D1 removes their only current home. Losing them
   would make the rename a net information loss rather than a correction. Default resolved by
   Claude; it is one key each in `metadata.pickle.npy`.

## 7. Best-practice alignment / sources

- [shapely — `covered_by`](https://shapely.readthedocs.io/en/stable/reference/shapely.covered_by.html)
  and [`contains`](https://shapely.readthedocs.io/en/stable/reference/shapely.contains.html),
  plus [DE-9IM](https://en.wikipedia.org/wiki/DE-9IM): supplied the decisive distinction in D4 —
  `covers`/`covered_by` are the boundary-inclusive predicates (`[T*****FF*]`), while `contains`
  excludes the boundary, which is exactly why a boundary-sharing clipped sliver escapes `contains`.
  This turned a measurement (2 of 8 caught) into a rule.
- `specs/15-calendar-mosaic.md` + ADR 0010 (internal): the calendar-`T` contract that makes the
  requested window — not the observed acquisitions — the identity of a run, which is D1's premise.
- `src/fsd/api.py:1096-1101` (internal): the existing ⚠️ that names the `*/*` depth a contract with
  `create_datacube.setup`; D1/D3 are written to keep that contract rather than break it.

## 8. Implementation note

Per `CLAUDE.md`'s model split, implementation is a **Sonnet session at `/effort medium`** against
this spec once signed off. Two files carry almost all of it: `src/fsd/workflows/create_datacube.py`
(D1–D3) and `src/fsd/grid.py` (D4–D5), plus the glob docstring in `src/fsd/api.py`.
