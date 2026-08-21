"""High-level batch entrypoint: setup work-units, then run via a runner.

Spec: specs/08-workflows.md. Preserves the demo_01 UX of run_create_datacube.

Setup reads the catalog once, then pre-slices it per shape (via `catalog.filter_gdf`)
so each parallel build job reads only its small subset — no shared-file contention. The
per-row start/end dates written to `input.csv` are the caller's requested window (the
calendar mosaic anchor, spec 15) — the run-folder name is derived from that same window
too (spec 46 D1). This is the shape-centric workflow TODO #15 will later optimize.
"""

from __future__ import annotations

import concurrent.futures
import datetime
import hashlib
import io
import json
import os
import tempfile

import geopandas as gpd
import pandas as pd

from fsd import config
from fsd import progress as _progress
from fsd.catalog.catalog import TileCatalog, filter_gdf
from fsd.storage import fs
from fsd.workflows import runners

COL_ID = "id"
COL_LABEL = "label"

# D13 (spec 38, TODO #53): a unit's CONTENT identity -- same id+params means the same
# work, safe to collapse to one row. `export_folderpath` is keyed by `id` ALONE
# (below), a narrower thing than this tuple -- two rows can share this identity and
# still collide on folder (that's the guard in `workflows.runners`, not this dedupe).
_UNIT_IDENTITY_COLS = (
    COL_ID, "startdate", "enddate", "bands", "mosaic_days", "mosaic_scheme", "scl_mask_classes",
)


class NoWorkUnitsError(ValueError):
    """`setup` was handed shapes but none of them had tiles in range/overlap.

    A `ValueError` subclass so every existing `except ValueError` caller (notably
    `api.verify_adapter`, which turns it into an actionable `PreflightError`) keeps
    working unchanged. It exists so `build_shortfall_only` can catch THIS condition --
    an entirely out-of-coverage shortfall, D5's known-empty case -- without also
    swallowing `setup`'s OTHER `ValueError`, the duplicate-`id_col` guard, which is a
    loud refusal that must never be silently reinterpreted as "no imagery".
    """


def params_key(bands: list[str], mosaic_scheme: str, scl_mask_classes: list[int]) -> str:
    """Spec 50 D6: a short digest of the params EVERY cell in a run shares (never the
    set of ids -- that is the thing Q1 rejected). Folded into the `<window>` path
    segment so path granularity matches `_UNIT_IDENTITY_COLS`: two requests differing
    only in `bands` must resolve to different paths, or the second silently overwrites
    the first and the build skip reads the wrong-band cube as "present" (D6). Same
    string form `setup` already writes to `input.csv` (`",".join(...)`), so a digest
    computed here and one computed from a read-back `input.csv` row agree byte-for-byte."""
    raw = "|".join([
        ",".join(bands), mosaic_scheme, ",".join(str(v) for v in scl_mask_classes),
    ])
    return hashlib.sha1(raw.encode()).hexdigest()[:8]


def window_folder_segment(
    startdate: datetime.datetime, enddate: datetime.datetime, mosaic_days: int, *,
    bands: list[str], mosaic_scheme: str, scl_mask_classes: list[int],
) -> str:
    """The one run-folder segment shared by every cell of a request (spec 46 D1/D2,
    extended by spec 50 D6): `<startdate>_<enddate>_m<mosaic_days>_<params_key>`. Callers
    that need to name an expected cube path WITHOUT running `setup` (D3/D4) call this with
    the same arguments `setup` was given -- same inputs, same string, no catalog access."""
    startdate = pd.to_datetime(startdate, utc=True)
    enddate = pd.to_datetime(enddate, utc=True)
    key = params_key(bands, mosaic_scheme, scl_mask_classes)
    return f"{startdate.strftime('%Y%m%d')}_{enddate.strftime('%Y%m%d')}_m{mosaic_days}_{key}"


def cube_export_folderpath(run_folderpath: str, window_segment: str, id_value) -> str:
    """A cube's `export_folderpath` is derivable from `(run_folderpath, window, id)` and
    NOTHING else (spec 50 D3) -- no catalog access is needed to NAME it, only to BUILD it.
    Shared by `setup`'s `_prepare` and by `api._flatten_identity_from_request`, which must
    compute the exact same string without reading `input.csv`."""
    export_folderpath = os.path.join(run_folderpath, window_segment, str(id_value))
    if fs.is_local(export_folderpath):
        # os.path.abspath is only meaningful (and safe) for a local path — on a
        # URL (e.g. abfss://...) it would corrupt the host/scheme (specs/31 §6).
        export_folderpath = os.path.abspath(export_folderpath)
    return export_folderpath


def setup(
    catalog_filepath: str,
    timestamp_col: str,
    shapefilepath: str,
    id_col: str,
    run_folderpath: str,
    startdate: datetime.datetime,
    enddate: datetime.datetime,
    bands: list[str],
    scl_mask_classes: list[int],
    mosaic_days: int,
    csv_filepath: str,
    label_col: str | None,
    mosaic_scheme: str = config.MOSAIC_SCHEME,
    max_concurrent: int = config.SETUP_MAX_CONCURRENT,
) -> None:
    """Per geometry: write geometry.geojson + catalog.parquet slice + input.csv row.

    Reads the catalog **once**, then reuses `catalog.filter_gdf` for each shape's
    date+overlap slice (which also persists `area_contribution`). Shapes with no
    intersecting tiles are skipped with a note. Prints live progress + ETA: the
    per-shape writes are network I/O on a remote run folder, so this can run for
    minutes and must not look like a hang.

    Shapes are prepared concurrently (`max_concurrent` threads) because that work is
    latency-bound blob I/O, not CPU. `input.csv` row order still follows the
    shapefile's order. Pass `max_concurrent=1` for the old serial behaviour.

    The mosaic anchor written to each row is the caller's `startdate`/`enddate` (not
    the per-shape actual acquisition min/max), so every shape mosaics on the same
    calendar grid and the resulting cubes share a `timestamps` axis that `flatten` can
    concatenate (spec 15). The run-folder name is now built from that same requested
    window + `mosaic_days` (spec 46 D1/D2), not the per-shape actual acquisition
    range, so every cell of one run lands under one folder that identifies the cube
    contract it was built against. `timestamp_col` no longer feeds the folder name
    (`actual_start`/`actual_end` moved into the cube's own metadata, spec 46 Q3) but
    stays a parameter — `filter_gdf`'s catalog rows already fix "timestamp" as the
    column, so this is unused today; kept for the caller-facing signature.
    """
    startdate = pd.to_datetime(startdate, utc=True)
    enddate = pd.to_datetime(enddate, utc=True)
    # D6a (spec 36, TODO #40): read via fsd.storage + BytesIO -- a local path behaves
    # exactly as before (fsd.storage routes file:// transparently), and this closes the
    # last raw-path geometry read that a cluster node (no `shapefiles/` checkout) can't do.
    with fs.open(shapefilepath, "rb") as f:
        shapes_gdf = gpd.read_file(io.BytesIO(f.read()))

    # `export_folderpath` is derived from `srow[id_col]`, so two shapes sharing an id are two
    # work-units writing the SAME folder -- concurrently, once `max_concurrent > 1`. On blob
    # that collides on the block-blob commit (`InvalidBlockList`) and the surviving
    # geometry.geojson is whichever shape committed last; locally it silently overwrites.
    # Either way the run is wrong, so refuse it here rather than race. (Found 2026-07-28: a
    # multi-polygon ROI made `roi_to_s2_grids` repeat cell ids -- fixed at source in grid.py,
    # but the guard belongs here too, for every caller.)
    if shapes_gdf[id_col].duplicated().any():
        counts = shapes_gdf[id_col].value_counts()
        repeated = counts[counts > 1]
        worst = ", ".join(f"{i}x{n}" for i, n in repeated.head(3).items())
        raise ValueError(
            f"shapes have duplicate '{id_col}' values: {len(repeated)} of "
            f"{shapes_gdf[id_col].nunique()} ids repeated across {len(shapes_gdf)} shapes "
            f"(worst: {worst}). Each id becomes one export folder, so duplicates make "
            f"multiple work-units write the same files concurrently. Deduplicate the shapes "
            f"(or pass an id column that is unique per shape) before calling setup()."
        )

    # Read the catalog ONCE for the whole run, then filter it in memory per shape
    # (`filter_gdf`). `TileCatalog.filter` re-reads the file on every call, which on a
    # remote catalog made setup cost one full download per shape: 900 shapes over
    # `abfss://` = 900 downloads of the same ~121 KiB parquet (~106 MiB, ~900 VPN
    # round-trips) before a single job was submitted. Same rows out, one read in.
    catalog_gdf = TileCatalog(catalog_filepath).read()

    window_segment = window_folder_segment(startdate, enddate, mosaic_days,
                                            bands=bands, mosaic_scheme=mosaic_scheme,
                                            scl_mask_classes=scl_mask_classes)

    n_shapes = len(shapes_gdf)
    print(f"[setup] catalog read once: {len(catalog_gdf)} rows, for {n_shapes} shapes",
          flush=True)

    # D4 (spec 47): the throttle + rate + ETA math itself now lives in `fsd.progress`
    # (extracted verbatim from what was here) so every driver-side loop shares one
    # implementation and one output format -- setup does per-shape network I/O and can
    # run for many minutes on a remote run folder; silence is indistinguishable from a hang.
    _tick = _progress.ticker(n_shapes, "setup", unit="shapes")

    def _prepare(srow) -> dict | None:
        """One shape's control files + its input.csv row. Pure per-shape work: it
        touches only this shape's own folder, and reads (never mutates) the shared
        `catalog_gdf` — which is what makes the pool below safe."""
        shape_gdf = gpd.GeoDataFrame(
            {"geometry": [srow["geometry"].buffer(0)], COL_ID: [srow[id_col]]},
            crs=shapes_gdf.crs,
        )
        if label_col is not None:
            shape_gdf[COL_LABEL] = srow[label_col]

        subset = filter_gdf(catalog_gdf, shape_gdf, startdate, enddate)
        if subset.shape[0] == 0:
            print(f"[setup] skip id={srow[id_col]}: no tiles in range/overlap", flush=True)
            return None

        export_folderpath = cube_export_folderpath(run_folderpath, window_segment, srow[id_col])
        fs.makedirs(export_folderpath)
        shape_path = os.path.join(export_folderpath, "geometry.geojson")
        catalog_path = os.path.join(export_folderpath, "catalog.parquet")
        # D6a (spec 36): write via fsd.storage rather than gpd.to_file(path) directly, so
        # this per-unit geometry lands correctly on a remote export_folderpath too.
        # write_text (not fs.open) so a concurrent adlfs InvalidBlockList retries (TODO #57).
        fs.write_text(shape_path, shape_gdf.to_json())
        fs.write_parquet(catalog_path, subset)

        row = {
            "shapefilepath": shape_path,
            # Calendar anchor = the caller's window (spec 15), not per-shape actual
            # acquisition min/max — so all shapes mosaic on the same grid. actual_start/
            # actual_end are used above for the run-folder name only.
            "startdate": startdate,
            "enddate": enddate,
            "catalog_filepath": catalog_path,
            "export_folderpath": export_folderpath,
            "datacube_filepath": os.path.join(export_folderpath, "datacube.npy"),
            "images_count": int(subset.shape[0]),
            COL_ID: srow[id_col],
        }
        if label_col is not None:
            row[COL_LABEL] = srow[label_col]
        return row

    # Threads, not processes: every shape costs ~4-7 tiny blob round-trips
    # (`makedirs` + `geometry.geojson` + the `catalog.parquet` slice), so the loop is
    # latency-bound and the GIL is released for the duration of each call. Same
    # pattern `sources.mpc.download`/`download_shard` already run concurrently through
    # `fsd.storage` against blob. Measured 2026-07-22: 900 shapes serially = ~1.8
    # s/shape (~27 min) on `rise` over VPN.
    #
    # Results are placed BY INDEX and compacted afterwards, so `input.csv` row order
    # is the shapefile's order regardless of completion order — parallelism must not
    # change the manifest. (An exception in a worker still propagates out of
    # `fut.result()`, as before; the pool's `__exit__` lets in-flight shapes finish
    # first, so slightly more work lands before it surfaces.)
    prepared: list[dict | None] = [None] * n_shapes
    _tick(0, force=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_concurrent) as pool:
        futures = {
            pool.submit(_prepare, srow): i
            for i, (_, srow) in enumerate(shapes_gdf.iterrows())
        }
        done = 0
        for fut in concurrent.futures.as_completed(futures):
            prepared[futures[fut]] = fut.result()
            done += 1
            _tick(done)

    rows = [r for r in prepared if r is not None]
    _tick(n_shapes, force=True)

    if not rows:
        raise NoWorkUnitsError("setup produced no work-units (no shape had tiles in range).")

    input_df = pd.DataFrame(rows)
    input_df["added_on"] = pd.Timestamp.now(tz="UTC")
    input_df["mosaic_days"] = mosaic_days
    input_df["mosaic_scheme"] = mosaic_scheme
    input_df["scl_mask_classes"] = ",".join(str(v) for v in scl_mask_classes)
    input_df["bands"] = ",".join(bands)

    if fs.exists(csv_filepath):
        with fs.open(csv_filepath, "r") as f:
            input_df = pd.concat([pd.read_csv(f), input_df], ignore_index=True)
    input_df = _dedupe_on_unit_identity(input_df)
    with fs.open(csv_filepath, "w") as f:
        input_df.to_csv(f, index=False)


def _dedupe_on_unit_identity(input_df: pd.DataFrame) -> pd.DataFrame:
    """D13 (spec 38, TODO #53): collapse rows sharing the same content identity
    (`_UNIT_IDENTITY_COLS`) to one, keeping the NEWEST (`added_on`) -- an idempotent
    re-run of `setup` (which appends unconditionally) must not grow `input.csv` by one
    duplicate copy of every unit each time. A re-run adding a genuinely new shape (or a
    changed window/params for an existing id) still adds a distinct row -- this is a
    dedupe, not a "one row per id" collapse. Order otherwise preserved (`setup`'s own
    manifest-order contract, `test_setup_manifest_order_is_shapefile_order_not_completion_order`)."""
    cols = [c for c in _UNIT_IDENTITY_COLS if c in input_df.columns]
    if not cols:
        return input_df
    # A prior run's rows round-tripped through CSV (dates/added_on came back as
    # strings); this run's freshly-prepared rows are still in-memory Timestamps. Build
    # a canonicalized identity key per row (dates normalized to a comparable ISO
    # string) rather than comparing the raw columns, so the two never fail to match on
    # type/format alone.
    date_cols = {"startdate", "enddate"} & set(cols)
    key_df = input_df[cols].copy()
    for c in date_cols:
        key_df[c] = pd.to_datetime(key_df[c], utc=True).astype(str)
    identity_key = key_df.astype(str).agg("|".join, axis=1)

    if "added_on" not in input_df.columns:
        return input_df.loc[~identity_key.duplicated(keep="last")]
    sort_key = pd.to_datetime(input_df["added_on"], utc=True)
    order = sort_key.argsort(kind="stable")
    keep_last = ~identity_key.iloc[order].duplicated(keep="last")
    keep_index = identity_key.iloc[order].index[keep_last.to_numpy()]
    return input_df.loc[input_df.index.isin(keep_index)]  # restore manifest order


def _cube_present(datacube_filepath: str) -> bool:
    """D2 (spec 49): a cube counts as present only when BOTH `datacube.npy` and its
    `metadata.pickle.npy` sibling exist and are non-empty -- a half-written cube is the
    same class of defect spec 47 §3a documented for downloads (#74), and this must not
    repeat it."""
    metadata_filepath = os.path.join(os.path.dirname(datacube_filepath), "metadata.pickle.npy")
    for filepath in (datacube_filepath, metadata_filepath):
        if not fs.exists(filepath) or fs.size(filepath) == 0:
            return False
    return True


def _load_shapes_gdf(shapefilepath: str) -> gpd.GeoDataFrame:
    with fs.open(shapefilepath, "rb") as f:
        return gpd.read_file(io.BytesIO(f.read()))


def _row_matches_window(
    row, *, bands: list[str], mosaic_days: int, startdate, enddate,
    mosaic_scheme: str, scl_mask_classes: list[int],
) -> bool:
    """Does an existing `input.csv` row belong to THIS request's window/params? Same
    canonicalization `_dedupe_on_unit_identity` uses (dates -> comparable ISO strings)
    so a row that round-tripped through CSV still compares correctly against in-memory
    request values."""
    want = {
        "bands": ",".join(bands),
        "mosaic_days": str(mosaic_days),
        "startdate": str(pd.to_datetime(startdate, utc=True)),
        "enddate": str(pd.to_datetime(enddate, utc=True)),
        "mosaic_scheme": mosaic_scheme,
        "scl_mask_classes": ",".join(str(v) for v in scl_mask_classes),
    }
    for col, want_val in want.items():
        if col not in row.index:
            continue
        got = row[col]
        if col in ("startdate", "enddate"):
            got = str(pd.to_datetime(got, utc=True))
        else:
            # F5: `",".join([])` -> `""` -> an empty CSV field -> read back as NaN,
            # not `""`. Without this, `scl_mask_classes=[]` ("mask nothing", a
            # legitimate request) round-trips to "nan" and never matches its own
            # freshly-written request value, purging every row on every call.
            got = "" if pd.isna(got) else str(got)
        if got != want_val:
            return False
    return True


def _manifest_filepath(run_folderpath: str) -> str:
    return os.path.join(run_folderpath, "_manifest.json")


def _read_known_empty(run_folderpath: str, window_segment: str) -> set[str]:
    """D5/§7 Q2: the known-empty manifest, keyed to the window/params segment (which
    already carries the request identity D6 needs -- reusing it here keeps ONE identity
    granularity for both the cube path and the known-empty record, per D5's risk note: a
    changed window or band set clears it automatically, because the key itself changes)."""
    path = _manifest_filepath(run_folderpath)
    if not fs.exists(path):
        return set()
    try:
        with fs.open(path, "r") as f:
            manifest = json.load(f)
    except Exception:  # noqa: BLE001 - a corrupt manifest is "no information", not a crash
        return set()
    entry = manifest.get(window_segment) if isinstance(manifest, dict) else None
    if not isinstance(entry, dict):
        return set()
    return {str(v) for v in entry.get("ids", [])}


def _load_manifest(run_folderpath: str) -> dict:
    path = _manifest_filepath(run_folderpath)
    if not fs.exists(path):
        return {}
    try:
        with fs.open(path, "r") as f:
            loaded = json.load(f)
    except Exception:  # noqa: BLE001 - a corrupt manifest is replaced, not fatal
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _write_known_empty(run_folderpath: str, window_segment: str, ids: set[str]) -> None:
    manifest = _load_manifest(run_folderpath)
    if ids:
        manifest[window_segment] = {"ids": sorted(ids)}
    else:
        manifest.pop(window_segment, None)
    fs.write_text(_manifest_filepath(run_folderpath),
                  json.dumps(manifest, indent=2, sort_keys=True))


def _record_known_empty(run_folderpath: str, window_segment: str, new_ids) -> None:
    if not new_ids:
        return
    existing = _read_known_empty(run_folderpath, window_segment)
    _write_known_empty(run_folderpath, window_segment,
                       existing | {str(v) for v in new_ids})


def _forget_known_empty(run_folderpath: str, window_segment: str, recovered_ids) -> None:
    """The manifest must not be write-only. An id recorded known-empty that LATER gets
    an `input.csv` row -- because the archive was re-ingested, or because a forced
    rebuild (`overwrite="datacubes"`/`True`) re-derived every shape from the catalog --
    is no longer empty, and leaving it recorded makes `api._flatten_identity_from_request`
    subtract an id that `input.csv` genuinely names. The two identities could then never
    agree again and the top-level short-circuit would be dead for that request forever:
    the exact failure D5's manifest was introduced to remove, relocated (Opus re-review
    2026-08-21).
    """
    recovered = {str(v) for v in recovered_ids}
    if not recovered:
        return
    existing = _read_known_empty(run_folderpath, window_segment)
    remaining = existing - recovered
    if remaining != existing:
        _write_known_empty(run_folderpath, window_segment, remaining)


def _clear_known_empty(run_folderpath: str, window_segment: str) -> None:
    """Drop this window's whole known-empty entry -- for a caller that has just
    re-derived every shape from the catalog and whose `input.csv` is therefore the
    authority. See `_forget_known_empty`."""
    if _read_known_empty(run_folderpath, window_segment):
        _write_known_empty(run_folderpath, window_segment, set())


def build_shortfall_only(
    *, catalog_filepath: str, timestamp_col: str, shapefilepath: str, id_col: str,
    run_folderpath: str, startdate, enddate, bands: list[str],
    scl_mask_classes: list[int], mosaic_days: int, csv_filepath: str,
    label_col: str | None, mosaic_scheme: str = config.MOSAIC_SCHEME,
    max_concurrent: int = config.SETUP_MAX_CONCURRENT,
) -> tuple[int, int, int]:
    """D2/D3/D4/D5 (spec 50 §9 step 4) -- the backward walk's build leg. Every id's cube
    target is named from the REQUEST alone (D3: `window_folder_segment` +
    `cube_export_folderpath`), so `setup` is called only for shapes whose cube is
    genuinely missing and not already recorded as known-empty (D5) -- not for the whole
    shapefile every time (D4).

    Rows in an existing `csv_filepath` for a DIFFERENT window/params are dropped before
    anything else: this function only ever GROWS `input.csv` within ONE window. Full
    cross-window accumulation is D9 (§9 step 3), deliberately BLOCKED on #84 (two
    windows of one id would collide in `ids.npy`) -- this stays inside one window on
    purpose, so it delivers D4's cost reduction without reaching into D9's territory.

    Prints the D7 `[plan]` build line before any `setup` call. Returns
    `(n_present, n_missing, n_known_empty)`.
    """
    shapes_gdf = _load_shapes_gdf(shapefilepath)
    window_segment = window_folder_segment(
        startdate, enddate, mosaic_days, bands=bands, mosaic_scheme=mosaic_scheme,
        scl_mask_classes=scl_mask_classes,
    )
    known_empty = _read_known_empty(run_folderpath, window_segment)

    existing_df = None
    existing_ids: set[str] = set()
    if fs.exists(csv_filepath):
        with fs.open(csv_filepath, "r") as f:
            existing_df = pd.read_csv(f)
        if len(existing_df):
            keep_mask = existing_df.apply(
                lambda row: _row_matches_window(
                    row, bands=bands, mosaic_days=mosaic_days, startdate=startdate,
                    enddate=enddate, mosaic_scheme=mosaic_scheme,
                    scl_mask_classes=scl_mask_classes,
                ),
                axis=1,
            )
            existing_df = existing_df.loc[keep_mask]
        # `input.csv` rows are always written under `COL_ID` ("id") by `setup`,
        # regardless of the caller's own `id_col` name (e.g. "fid") -- `shapes_gdf`
        # below is the only frame that still uses the caller's `id_col`.
        if len(existing_df) and COL_ID in existing_df.columns:
            existing_ids = set(existing_df[COL_ID].astype(str))

    present_ids: list[str] = []
    missing_srows: list = []
    for _, srow in shapes_gdf.iterrows():
        id_value = str(srow[id_col])
        if id_value in existing_ids:
            present_ids.append(id_value)
            continue
        cube_folder = cube_export_folderpath(run_folderpath, window_segment, srow[id_col])
        datacube_filepath = os.path.join(cube_folder, "datacube.npy")
        if _cube_present(datacube_filepath):
            # F1: a cube with no row is not "satisfied" -- nothing downstream (the
            # build leg, flatten) ever looks at the cube directly, only at
            # `input.csv` rows, and nothing else ever calls `setup` for this id. Route
            # it through `setup` (idempotent, and `_build_shortfall` still skips the
            # cube itself) so the row comes back.
            missing_srows.append(srow)
        elif id_value in known_empty:
            pass  # D5: known-empty, satisfied -- never rediscovered
        else:
            missing_srows.append(srow)

    # F3: `present_ids`/`missing_srows` above answer "does setup need to run for this
    # id" (a ROW question) -- but the announced plan must match what `_build_shortfall`
    # actually dispatches next (a CUBE question). An interrupted prior run can have a
    # row with no cube behind it yet; count that as missing for the printed line
    # without changing whether `setup` reruns for it (it doesn't need to -- the row is
    # already correct, only the runner needs to build the cube).
    cube_missing_ids = {
        id_value for id_value in present_ids
        if not _cube_present(os.path.join(
            cube_export_folderpath(run_folderpath, window_segment, id_value), "datacube.npy"
        ))
    }
    n_total = len(shapes_gdf)
    n_missing = len(missing_srows)
    n_known_empty = n_total - len(present_ids) - n_missing
    n_missing_for_plan = n_missing + len(cube_missing_ids)
    n_present_for_plan = len(present_ids) - len(cube_missing_ids)
    print(f"[plan]   build: {n_present_for_plan} present, {n_missing_for_plan} missing, "
          f"{n_known_empty} known-empty -> will build {n_missing_for_plan}", flush=True)

    # Persist the window-scoped purge even when nothing is missing -- an existing
    # `input.csv` carrying a DIFFERENT window's rows must never leak into this window's
    # flatten (which requires every cube to share bands/timestamps).
    if existing_df is not None:
        with fs.open(csv_filepath, "w") as f:
            existing_df.to_csv(f, index=False)

    if not missing_srows:
        return len(present_ids), n_missing, n_known_empty

    shortfall_gdf = gpd.GeoDataFrame(missing_srows, crs=shapes_gdf.crs)
    with tempfile.TemporaryDirectory() as tmp:
        shortfall_shapefilepath = os.path.join(tmp, "shortfall.geojson")
        shortfall_gdf.to_file(shortfall_shapefilepath, driver="GeoJSON")
        try:
            setup(
                catalog_filepath=catalog_filepath, timestamp_col=timestamp_col,
                shapefilepath=shortfall_shapefilepath, id_col=id_col,
                run_folderpath=run_folderpath, startdate=startdate, enddate=enddate,
                bands=bands, scl_mask_classes=scl_mask_classes, mosaic_days=mosaic_days,
                csv_filepath=csv_filepath, label_col=label_col, mosaic_scheme=mosaic_scheme,
                max_concurrent=max_concurrent,
            )
        except NoWorkUnitsError:
            # F2: `setup` raises when NONE of the shapes it was handed have tiles in
            # range -- reachable here because this call is scoped to just the
            # shortfall, unlike the old whole-shapefile path where one out-of-coverage
            # polygon among hundreds could never trigger it. Record the whole
            # shortfall as known-empty (D5) and let the caller's request converge,
            # rather than crashing the entire `create_training_data` call.
            #
            # Deliberately NOT `except ValueError`: `setup`'s duplicate-`id_col` guard
            # raises that too, and swallowing it would silently record a caller's
            # duplicated shapes as "no imagery" -- turning a loud refusal into missing
            # training data (Opus re-review 2026-08-21).
            newly_empty = [str(srow[id_col]) for srow in missing_srows]
            _record_known_empty(run_folderpath, window_segment, newly_empty)
            print(f"[setup] shortfall of {len(missing_srows)} had no tiles in range/overlap "
                  f"-- recorded known-empty", flush=True)
            return len(present_ids), n_missing, n_known_empty

    with fs.open(csv_filepath, "r") as f:
        after_df = pd.read_csv(f)
    built_ids = set(after_df[COL_ID].astype(str)) if len(after_df) else set()
    newly_empty = [str(srow[id_col]) for srow in missing_srows
                   if str(srow[id_col]) not in built_ids]
    _record_known_empty(run_folderpath, window_segment, newly_empty)
    # ...and the converse: anything that now HAS a row is not empty any more.
    _forget_known_empty(run_folderpath, window_segment, built_ids)

    return len(present_ids), n_missing, n_known_empty


def _build_shortfall(csv_filepath: str, *, force: bool) -> tuple[str, int, int]:
    """D1 (spec 49): which `input.csv` rows still need a cube built -- the driver-side
    analogue of spec 47 D8's download diff, one level up. Returns `(dispatch_csv_filepath,
    n_total, n_missing)`. `force=True` (an `overwrite=` rebuild) treats every row as
    missing without touching the filesystem (the driver dispatches every row again; the
    node then actually rebuilds only because the caller is expected to have cleared the
    old artifacts -- see `_force_rebuild`).

    When nothing is missing, or NOTHING is present yet (today's full-dispatch shape),
    `dispatch_csv_filepath` is `csv_filepath` itself -- no temp file, no extra write. Only
    a PARTIAL shortfall gets its own sibling CSV holding just the missing rows, so a run
    that is 95% built does not fan out 100% (spec 47's own reasoning, D1)."""
    with fs.open(csv_filepath, "r") as f:
        df = pd.read_csv(f)
    n_total = len(df)
    if force:
        return csv_filepath, n_total, n_total
    missing_mask = ~df["datacube_filepath"].apply(_cube_present)
    n_missing = int(missing_mask.sum())
    if n_missing in (0, n_total):
        return csv_filepath, n_total, n_missing
    shortfall_csv_filepath = f"{csv_filepath}.shortfall.csv"
    with fs.open(shortfall_csv_filepath, "w") as f:
        df.loc[missing_mask].to_csv(f, index=False)
    return shortfall_csv_filepath, n_total, n_missing


def _force_rebuild(csv_filepath: str) -> None:
    """D4 (spec 49): `overwrite="datacubes"`/`True` forces a rebuild. `workflows.task`'s
    own node-side skip (`fs.exists(datacube.npy)`) would otherwise no-op every row whose
    cube still exists, so the driver clears each row's existing cube files FIRST -- this is
    still an identity-free operation (no mtime read anywhere, D3/AC6): it removes whatever
    is there, unconditionally, for exactly the rows this run addresses."""
    with fs.open(csv_filepath, "r") as f:
        df = pd.read_csv(f)
    for datacube_filepath in df["datacube_filepath"]:
        metadata_filepath = os.path.join(os.path.dirname(datacube_filepath), "metadata.pickle.npy")
        for filepath in (datacube_filepath, metadata_filepath):
            if fs.exists(filepath):
                fs.rm(filepath)


def run_create_datacube(
    catalog_filepath: str,
    timestamp_col: str,
    shapefilepath: str,
    id_col: str,
    run_folderpath: str,
    startdate: datetime.datetime,
    enddate: datetime.datetime,
    bands: list[str],
    scl_mask_classes: list[int],
    mosaic_days: int,
    csv_filepath: str,
    label_col: str | None,
    cores: int,
    *,
    mosaic_scheme: str = config.MOSAIC_SCHEME,
    dry_run: bool = False,
    unlock: bool = False,
    overwrite_setup_csv: bool = True,
    overwrite: bool = False,
    runner: str = "local",
    runner_kwargs: dict | None = None,
):
    """Run setup (unless csv exists), then dispatch only the cubes that are still missing.

    `runner_kwargs` (spec 36 D3) is forwarded to `runners.run_aml` when `runner="aml"`
    (e.g. `cluster=`, `environment=`, `root=`, `identity_client_id=`) -- the local runner
    takes no extra kwargs, so it is ignored for `runner="local"`.

    `overwrite=True` (spec 49 D1/D4/§7 Q1) forces every cube in `csv_filepath` to be
    rebuilt (clearing existing artifacts first, `_force_rebuild`); `False` (default) skips
    per-cell (`_build_shortfall`): a shortfall of 0 prints and returns WITHOUT submitting a
    single job; a partial shortfall dispatches only the missing rows. No modification time
    is read anywhere in this decision (D3/AC6) -- presence is `datacube.npy` +
    `metadata.pickle.npy`, both non-empty (D2).

    `overwrite_setup_csv` (spec 50 D4/§9 step 4): `True` (default, unchanged -- no
    production caller sets this) keeps the legacy behaviour, delete-then-regenerate the
    whole `input.csv` every call. `False` -- which is what `create_training_data` now
    passes -- runs `build_shortfall_only` instead: `setup` is called ONLY for shapes
    whose cube target (named from the request, D3, no catalog access) is missing and not
    already known-empty (D5). `overwrite_setup_csv` itself is not removed here -- that is
    D9/§9 step 3, blocked on #84.
    """
    if overwrite_setup_csv:
        if fs.exists(csv_filepath):
            fs.rm(csv_filepath)
        if not fs.exists(csv_filepath):
            setup(
                catalog_filepath=catalog_filepath, timestamp_col=timestamp_col,
                shapefilepath=shapefilepath, id_col=id_col, run_folderpath=run_folderpath,
                startdate=startdate, enddate=enddate, bands=bands,
                scl_mask_classes=scl_mask_classes, mosaic_days=mosaic_days,
                csv_filepath=csv_filepath, label_col=label_col, mosaic_scheme=mosaic_scheme,
            )
            # This pass just re-derived every shape straight from the catalog, so any
            # known-empty record for this window is superseded by what `input.csv` now
            # says. Clearing it here is what makes a forced rebuild the escape hatch
            # from a stale manifest (D5's risk note) rather than a way to leave the
            # manifest disagreeing with `input.csv` (Opus re-review 2026-08-21).
            _clear_known_empty(
                run_folderpath,
                window_folder_segment(startdate, enddate, mosaic_days, bands=bands,
                                      mosaic_scheme=mosaic_scheme,
                                      scl_mask_classes=scl_mask_classes),
            )
    else:
        build_shortfall_only(
            catalog_filepath=catalog_filepath, timestamp_col=timestamp_col,
            shapefilepath=shapefilepath, id_col=id_col, run_folderpath=run_folderpath,
            startdate=startdate, enddate=enddate, bands=bands,
            scl_mask_classes=scl_mask_classes, mosaic_days=mosaic_days,
            csv_filepath=csv_filepath, label_col=label_col, mosaic_scheme=mosaic_scheme,
        )

    if overwrite:
        _force_rebuild(csv_filepath)

    dispatch_csv_filepath, n_total, n_missing = _build_shortfall(csv_filepath, force=overwrite)
    if n_missing == 0:
        print(f"[build] 0 of {n_total} cubes missing; nothing to build", flush=True)
        return None
    if 0 < n_missing < n_total:
        print(f"[build] {n_missing} of {n_total} cubes missing; dispatching {n_missing}",
              flush=True)

    if runner == "local":
        return runners.run_local(dispatch_csv_filepath, cores=cores, dry_run=dry_run,
                                 unlock=unlock)
    if runner == "aml":
        return runners.run_aml(dispatch_csv_filepath, **(runner_kwargs or {}))
    raise ValueError(f"Unknown runner={runner!r}; valid values: 'local', 'aml'.")
