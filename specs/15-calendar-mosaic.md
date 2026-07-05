# Spec 15 — Calendar-interval median mosaic

> **Status: signed off + implemented (2026-07-05).** `median_mosaic` gained
> `mosaic_scheme` (default `config.MOSAIC_SCHEME="calendar"`); calendar windows +
> empty-window emission + window-start labels via new `ops._calendar_windows` /
> `_mosaic_from_intervals`; threaded through `build_datacube`, `task` (`--mosaic-scheme`),
> `create_datacube.setup` (now anchors the mosaic at the caller's dates, not per-shape
> actual) + the Snakefile. **Real smoke (2026-07-05):** a west field (EPSG:32636) and an
> east field (EPSG:32637) with different acquisition dates produced an identical
> `[2018-06-01, 2018-06-21]` timestamps axis. 124 tests, ruff clean. See CHANGES.md.
>
> Makes `median_mosaic` bucket timestamps by
> **fixed calendar windows** derived from the caller's `startdate`/`enddate` (the new
> **default**), instead of by actual satellite-acquisition dates. Resolves TODO #2 and
> **unblocks `flatten` across a multi-tile / multi-zone training set** (spec 05): every
> datacube built over the same `startdate`/`enddate`/`mosaic_days` now yields the
> **identical** `timestamps` axis regardless of which tiles/orbits a shape intersects.
> Legacy acquisition-anchored behavior is preserved behind a flag.

## Motivation

`flatten` (spec 05) concatenates many per-geometry datacubes into per-pixel training
arrays and **requires all cubes to share an identical `timestamps` axis**
(`_check_metadata_consistency`, list equality). Today they don't:

- `median_mosaic` labels each output timestamp with the **first actual acquisition date
  in that window** (`md["timestamps"] = [timestamps[r[0]] for r in ranges]`), and the
  window ranges themselves track *occupied* buckets (with a "gap opens a new interval"
  quirk) — both data-dependent.
- The workflow layer (`create_datacube.setup`) threads each shape's **actual first/last
  acquisition** in as `startdate`/`enddate`, so windows shift shape-to-shape.

Confirmed empirically on the EuroCrops→Ethiopia set (`fid`-keyed, 1015 fields, 80×65 km
across **EPSG:32636 & 32637**): a western field (tile 36PZU, orbit R122) has acquisitions
`06-04, 06-09, …`; an eastern field (37PBN, different orbit) has `06-01, 06-06, …`. Same
`startdate`/`enddate`/`mosaic_days`, **different timestamp labels** → `flatten` raises.

A caller who asks for `[startdate, enddate]` with `mosaic_days=20` should get windows on a
**fixed calendar grid** — the satellite acquisition dates are an implementation detail they
should not have to reconcile. That is this spec.

## What changes (small, contained)

1. **`src/fsd/datacube/ops.py::median_mosaic`** — new `mosaic_scheme` parameter:
   - `"calendar"` (**default**): windows are the fixed intervals
     `[startdate + k·mosaic_days, startdate + (k+1)·mosaic_days)` covering
     `[startdate, enddate)`; **label = the window-start boundary**; **every** window is
     emitted, including empty ones (all-`mask_value` slice). Output `timestamps` are
     therefore a pure function of `(startdate, enddate, mosaic_days)`.
   - `"acquisition"`: the current legacy behavior, unchanged (regression-tested).
2. **`src/fsd/datacube/builder.py::build_datacube`** — accept `mosaic_scheme` (default
   `config.MOSAIC_SCHEME = "calendar"`) and thread it into the `median_mosaic` op.
3. **`src/fsd/workflows/create_datacube.py::setup`** — pass the **caller's**
   `startdate`/`enddate` (calendar window) to the build as the mosaic anchor, **not** the
   per-shape `actual_start`/`actual_end`. Keep `actual_start`/`actual_end` for the run
   folder name and the CSV bookkeeping only. Thread `mosaic_scheme` through
   `run_create_datacube` → `task` → `build_datacube`.
4. **`config.py`** — `MOSAIC_SCHEME = "calendar"`.

The read/stack/mask path is untouched; only how the mosaic step buckets + labels changes.

## `median_mosaic` — calendar scheme (precise semantics)

```python
def median_mosaic(datacube, metadata, *, startdate, enddate, mosaic_days=20,
                  mask_value=0, mosaic_scheme=config.MOSAIC_SCHEME):
```

Calendar windows (deterministic, data-independent):
```
windows = []
cur = _dt2ts(startdate)
end = _dt2ts(enddate)
while cur < end:
    windows.append((cur, cur + timedelta(days=mosaic_days)))   # half-open [lo, hi)
    cur += timedelta(days=mosaic_days)
# n_out = len(windows) = ceil((enddate - startdate) / mosaic_days)
```

Per window `[lo, hi)`:
- **members** = sorted `timestamps[i]` with `lo <= ts < hi` (contiguous, since sorted).
- non-empty → per-pixel `nanmedian` over those slices (existing numba core, unchanged).
- **empty → an all-`mask_value` slice** `(1, H, W, bands)` so the axis length is fixed.
- **label** = `lo` (the window-start `pd.Timestamp`, tz-aware UTC).

Assembled output `(n_out, H, W, bands)`; then:
```
md["timestamps"]            = [lo for (lo, hi) in windows]        # calendar boundaries
md["mosaic_windows"]        = [(lo, hi) for windows]              # NEW, explicit
md["mosaic_index_intervals"]= [(min_i,max_i) | None if empty]    # None marks empty window
md["previous_timestamps"]   = metadata["timestamps"]
md["data_shape_desc"]       = ("timestamps", "height", "width", "bands")
```

Boundary rule is **half-open `[lo, hi)`** (a timestamp exactly on a boundary lands in the
later window) — chosen for determinism; differs from legacy's `ts <= hi` upper-inclusive
walk, which only matters for a timestamp landing exactly on a boundary (rare at S2's ~5-day
cadence). Legacy `"acquisition"` keeps its original `<=` semantics.

Guards unchanged: `startdate <= timestamps[0]` and `enddate >= timestamps[-1]` still
required (the catalog filter already guarantees this when the caller passes the same
`[startdate, enddate]` used for filtering). `mosaic_days < 1` → no-op (as today).

## Caveat — `mosaic_days` smaller than the revisit cadence

Calendar mode is intended for `mosaic_days ≥ revisit` (real temporal compositing). If
`mosaic_days` is set *below* the acquisition cadence (e.g. `mosaic_days=2` with a 10-day
revisit), each acquisition lands alone in its window (median of one image = that image,
unchanged, **no data lost**) and every window with no acquisition is emitted as an
**all-nodata slice**. So the cube degenerates to "the raw time series on a fixed calendar
grid, padded with empty slices" — correct and still cross-shape-consistent, but memory/
storage-heavy. This is the deliberate price of the fixed-calendar guarantee (dropping the
empty slices would reintroduce per-shape axis variability). Pick `mosaic_days` at/above the
revisit. Decision (2026-07-05): **no runtime warning** for this — the window-vs-cadence
behavior is documented inline in `median_mosaic`'s docstring instead.

## Why this makes `flatten` clean (spec 05)

With `mosaic_scheme="calendar"`, two cubes built over the same `(startdate, enddate,
mosaic_days)` have byte-identical `timestamps` lists (calendar boundaries) **and** the same
axis length, whatever tiles/orbits/zones they came from → `flatten`'s strict
`_check_metadata_consistency` passes as-is. **We keep the strict check** (it correctly
rejects flattening cubes built with mismatched windows); we do not weaken it to length-only.

## Out of scope (logged, not fixed here)

- **Multi-zone `coords.npy`.** `flatten` concatenates per-cube easting/northing but only
  checks bands+timestamps, so a west cube (EPSG:32636) and an east cube (EPSG:32637) mix two
  UTM zones in one `coords` array. Fine if coords are pixel identifiers; wrong if used
  spatially. → **new TODO** (store per-pixel CRS, or reproject coords to a common CRS). Does
  not block the spectral training arrays (`data.npy` + `ids` + `labels`).
- The median-anchor **folder naming** in `setup` stays `{actual_start}_{actual_end}`.

## Ripple effects (record in CHANGES.md)

- **`tests/manual/datacube.md` reference values** change: mosaic `timestamps` become
  calendar boundaries (e.g. `2018-06-01`, `2018-06-21`) instead of first-acquisition dates;
  window **count** = `ceil((end-start)/mosaic_days)` (for the 2018-06-01→07-10 window,
  mosaic_days=20 → still 2). Update the runbook's expected prints.
- Benchmarks (spec 11/12 throughput) measure timing, not labels — behavior is equivalent;
  add a one-line note that mosaic anchoring changed.
- Legacy runs can set `mosaic_scheme="acquisition"` to reproduce old outputs exactly.

## Tests (`tests/test_datacube_ops.py`, extend)

- **Cross-shape identity:** two synthetic cubes with *different* acquisition dates but the
  same `(startdate, enddate, mosaic_days)` → identical `timestamps` and equal axis length.
- **Empty window:** a `(startdate, enddate)` spanning a window with no acquisitions → that
  window is emitted as an all-`mask_value` slice at the correct position; `timestamps` has
  the full calendar count; `mosaic_index_intervals` has `None` there.
- **Window count / labels:** `n_out == ceil((end-start)/mosaic_days)`; labels == window
  starts; half-open boundary places an on-boundary timestamp in the later window.
- **Median correctness:** non-empty-window medians match the legacy core on the same members.
- **Regression:** `mosaic_scheme="acquisition"` reproduces current outputs (timestamps,
  shape, values) on the existing fixtures.

## Sign-off checklist
- [ ] `mosaic_scheme="calendar"` default; `"acquisition"` preserves legacy.
- [ ] Empty calendar windows emitted as all-nodata (fixed axis length).
- [ ] Label = window-start boundary; half-open `[lo, hi)`.
- [ ] Workflow `setup` anchors mosaic at caller `startdate`/`enddate`, not actual.
- [ ] `flatten` strict timestamp check kept; multi-zone `coords` logged as TODO.
- [ ] `datacube.md` reference values updated; CHANGES.md notes the behavior change.
