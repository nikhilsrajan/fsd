"""fsd high-level API — the verbs users call.

Spec: specs/16-packaging-and-api.md (P0). A thin façade over the internal modules
(`sources`, `catalog`, `datacube`, `workflows`, `flatten`) that raises the scope from
implementation vocabulary ("flatten", "input.csv") to user intent ("make training data").
Adds no pipeline logic.

- `download(...)`            -> fetch S2 L2A tiles + build a TileCatalog (its own verb).
- `create_training_data(...)`-> label polygons + catalog -> datacubes -> flattened arrays.
- `run_inference(...)`       -> model over pre-built cubes (spec 18) OR an ROI (spec 21,
                               tile -> per-cell build+infer via the runner seam) -> COG + STAC.
- `deploy(...)`              -> stub (P6): register a model bundle.

`runner=`/`storage=` are the seams (ROADMAP §2.2/§2.3): only `runner="local"` and local
`storage` are wired in P0; Azure Batch / blob arrive in P1/P2 as config, not API changes.
Every verb runs a cheap **preflight** (ROADMAP §2.6) before any heavy work.
"""

from __future__ import annotations

import datetime
import math
import os
from dataclasses import dataclass

import geopandas as gpd
import numpy as np
import pandas as pd

from fsd import config
from fsd import progress as _progress
from fsd.bands import modify as _modify
from fsd.catalog import stac as _stac
from fsd.catalog.catalog import TileCatalog
from fsd.datacube import flatten as _flatten
from fsd.model import bundle as _bundle
from fsd.model import engine as _engine
from fsd.model.features import apply_features as _apply_features
from fsd.model.features import resolve_aggregate as _resolve_aggregate
from fsd.raster.cog import to_cog as _to_cog
from fsd.sources.cdse import CdseCredentials
from fsd.sources.cdse import download as _cdse_download
from fsd.sources.mpc import download as _mpc_download
from fsd.storage import fs
from fsd.storage.azure import configure_storage as _configure_storage
from fsd.workflows import create_datacube as _create_datacube

__all__ = [
    "InferenceResult",
    "PreflightError",
    "TrainingData",
    "compute_n_timestamps",
    "create_training_data",
    "deploy",
    "download",
    "flatten_training_data",
    "run_inference",
]


# D2 (spec 47): a cached work list that is a strict superset of the freshly tiled grids by no
# more than this many ids is named as a probable spec-46 D4 cell-count drift (AT_ROI dropped 1,
# s2grid=476da24 dropped 8, measured 2026-08-19) rather than a different roi.
_RESUME_DRIFT_SAMPLE = 10


class PreflightError(ValueError):
    """Raised when a cheap pre-flight check fails, before any download/build.

    Aggregates all failures so the caller fixes their config in one pass (ROADMAP §2.6).
    """


# --- helpers -----------------------------------------------------------------

def compute_n_timestamps(
    startdate: datetime.datetime, enddate: datetime.datetime, mosaic_days: int
) -> int:
    """`T` for a calendar-mosaic build: ceil((enddate - startdate) / mosaic_days).

    Pure function of the caller's window (spec 15) — computable with no download. This is
    the hook P4 will use to assert `T == model.n_timestamps` before an inference run.
    """
    start = pd.to_datetime(startdate, utc=True)
    end = pd.to_datetime(enddate, utc=True)
    total_days = (end - start) / pd.Timedelta(days=1)
    return math.ceil(total_days / mosaic_days)


_VALID_RUNNERS = ("local", "aml")


def _check_local_seams(runner: str, storage, *, storage_allowed: bool = True) -> list[str]:
    """`runner` is `"local"` (Snakemake) or `"aml"` (spec 36 P2: the Azure ML scale
    runner). `storage` is wired to the Azure compute seam in P1 (spec 31) for the verbs
    that read/write the pipeline's own artifacts (`download`, `create_training_data`) —
    pass `storage_allowed=False` for verbs that are explicitly out of P1 scope
    (`run_inference`/`deploy`: inference/serving-on-blob is P4/P5, stays local for now)."""
    errs = []
    if runner not in _VALID_RUNNERS:
        errs.append(f"runner={runner!r} not supported (valid: {list(_VALID_RUNNERS)}).")
    if storage is not None and storage != "local":
        if not storage_allowed:
            errs.append(
                "non-local storage not supported here yet (inference/serving-on-blob is "
                "P4/P5; storage= is wired for download/create_training_data in P1)."
            )
        else:
            if isinstance(storage, str):
                backend = storage
            elif isinstance(storage, dict):
                backend = storage.get("backend")
            else:
                backend = None
            if backend != "azure":
                errs.append(f"storage backend {backend!r} not supported (only 'azure' in P1).")
    return errs


def _as_gdf(label_polygons) -> gpd.GeoDataFrame:
    """A GeoDataFrame, or a path/url to one. Read via the storage seam (`fs.read_geo`),
    never `gpd.read_file(path)` — GDAL has no `abfss://` driver and reports a blob-hosted
    file as "No such file or directory" (TODO #47)."""
    if isinstance(label_polygons, gpd.GeoDataFrame):
        return label_polygons
    return fs.read_geo(label_polygons)


def _check_window(startdate, enddate, mosaic_days, bands) -> list[str]:
    errs = []
    start = pd.to_datetime(startdate, utc=True)
    end = pd.to_datetime(enddate, utc=True)
    if not (start < end):
        errs.append(f"startdate ({start}) must be before enddate ({end}).")
    if mosaic_days < 1:
        errs.append(f"mosaic_days ({mosaic_days}) must be >= 1.")
    if not bands:
        errs.append("bands must be a non-empty list.")
    if start < end and mosaic_days >= 1 and compute_n_timestamps(start, end, mosaic_days) < 1:
        errs.append("date window yields T < 1 timestamps.")
    return errs


def _raise_preflight(errs: list[str]) -> None:
    if errs:
        raise PreflightError("preflight failed:\n  - " + "\n  - ".join(errs))


def _check_resume_identity(csv_filepath: str, grids: gpd.GeoDataFrame, output_folderpath: str) -> None:
    """D1 (spec 47): `input.csv` resumes by EXISTENCE, not identity -- a cached work list from a
    prior, different roi must not silently win over the freshly tiled grids (#66). Compares the
    `id` sets; ANY difference raises rather than repairing, because both repairs are worse:
    rewriting `input.csv` in place orphans every cell already written under the old id set, and
    deleting the folder is not reliable on blob (#50). Detect-and-refuse is the honest subset of
    Snakemake's detect-and-rerun (D1)."""
    with fs.open(csv_filepath, "r") as f:
        cached_ids = set(pd.read_csv(f)["id"].astype(str))
    fresh_ids = set(grids["id"].astype(str))
    if cached_ids == fresh_ids:
        return
    only_cached = sorted(cached_ids - fresh_ids)
    only_fresh = sorted(fresh_ids - cached_ids)
    sample = (only_cached + only_fresh)[:10]
    msg = (
        f"output_folderpath={output_folderpath!r} already holds a work list "
        f"({len(cached_ids)} cell ids, in {os.path.join(output_folderpath, 'cells', 'input.csv')}) "
        f"that does not match the freshly tiled roi ({len(fresh_ids)} cell ids). "
        f"output_folderpath is the identity of a run (spec 47 D3) -- reusing one for a different "
        f"roi (or a different grid_size_km/scale_fact) would silently resume the OLD work list. "
        f"Sample of the differing ids: {sample}. Fix: use a new output_folderpath for this roi."
    )
    # D2: name the spec-46 D4 cell-count drift explicitly when it is plausibly the cause -- the
    # cached set is a strict superset missing only a handful of ids, not a disjoint id set from a
    # genuinely different roi. Any run folder created before 2026-08-19 hits this.
    if not only_fresh and 0 < len(only_cached) <= _RESUME_DRIFT_SAMPLE:
        msg += (
            f" This looks like the spec-46 D4 cell-count change (2026-08-19, e.g. 300->299 "
            f"cells for AT_ROI): the cached set is a strict superset missing only "
            f"{len(only_cached)} id(s), rather than a disjoint set from an unrelated roi. If so, "
            f"the fix is the same: use a new output_folderpath."
        )
    raise PreflightError(msg)


def _normalize_window(startdate, enddate) -> tuple[pd.Timestamp | None, pd.Timestamp | None, list[str]]:
    """D9 (spec 38, TODO #52): coerce the caller's dates to tz-aware UTC `Timestamp`s
    ONCE, at the API boundary -- the first thing `download`/`run_inference` do -- so
    every downstream call (window checks, sources, the AML dispatch) forwards the SAME
    typed value regardless of whether the caller passed a string or a `Timestamp`.
    Closes the `pystac_client` string-vs-datetime search-window divergence (issue #644:
    a date-only STRING expands to end-of-day, a `datetime`/`Timestamp` does not) at its
    source, and the CDSE/MPC runner asymmetry it caused (only the CDSE AML node path
    normalized before this fix).

    Returns errors instead of raising so callers aggregate them with the rest of
    preflight in one pass; an unparseable date is reported here, not by pandas/pystac
    downstream. `(None, None, [...])` on failure -- callers must skip any check that
    needs the parsed values when errs is non-empty.
    """
    errs = []
    try:
        start = pd.to_datetime(startdate, utc=True)
    except (ValueError, TypeError) as exc:
        errs.append(f"startdate={startdate!r} is not a valid date: {exc}")
        start = None
    try:
        end = pd.to_datetime(enddate, utc=True)
    except (ValueError, TypeError) as exc:
        errs.append(f"enddate={enddate!r} is not a valid date: {exc}")
        end = None
    return start, end, errs


# --- result handle -----------------------------------------------------------

@dataclass
class TrainingData:
    """Handle to a completed training-data build (paths; lazy-load arrays)."""

    export_folderpath: str      # data.npy / ids.npy / labels.npy / coords.npy / metadata.pickle.npy
    run_folderpath: str         # per-field datacubes + input.csv
    n_pixels: int
    n_timestamps: int
    bands: list[str]
    feature_bands: list[str] | None = None   # set when a feature transform was applied (P0.5)

    def load(self) -> dict:
        """Load the arrays into memory: data/ids/coords/metadata (+ labels if present).

        When a feature transform was applied (via `adapter=`/`feature_sequence=`), also loads
        `features`/`feature_ids`/`feature_labels` (the model-ready, possibly aggregated arrays).
        """
        out = {
            "data": fs.load_npy(os.path.join(self.export_folderpath, "data.npy")),
            "ids": fs.load_npy(os.path.join(self.export_folderpath, "ids.npy")),
            "coords": fs.load_npy(os.path.join(self.export_folderpath, "coords.npy")),
            "metadata": fs.load_npy(
                os.path.join(self.export_folderpath, "metadata.pickle.npy"), allow_pickle=True
            )[()],
        }
        labels_path = os.path.join(self.export_folderpath, "labels.npy")
        if fs.exists(labels_path):
            out["labels"] = fs.load_npy(labels_path)
        features_path = os.path.join(self.export_folderpath, "features.npy")
        if fs.exists(features_path):
            out["features"] = fs.load_npy(features_path)
            out["feature_ids"] = fs.load_npy(
                os.path.join(self.export_folderpath, "feature_ids.npy")
            )
            fl = os.path.join(self.export_folderpath, "feature_labels.npy")
            if fs.exists(fl):
                out["feature_labels"] = fs.load_npy(fl)
        return out


@dataclass
class InferenceResult:
    """Handle to a completed local inference run (spec 18)."""

    output_folderpath: str
    output_filepaths: list[str]
    stac_catalog_filepath: str
    merged_filepath: str | None = None
    grids_filepath: str | None = None  # ROI mode: the saved gridded-ROI GeoJSON (spec 21)


# --- verbs -------------------------------------------------------------------

def download(
    roi,
    startdate: datetime.datetime,
    enddate: datetime.datetime,
    bands: list[str],
    dst_folderpath: str,
    creds: CdseCredentials | None = None,
    *,
    source: str = "cdse",
    max_tiles: int,
    max_cloudcover: float | None = None,
    cog: bool = True,
    progress: bool = True,
    storage=None,
    runner: str = "local",
    runner_kwargs: dict | None = None,
) -> str:
    """Fetch S2 L2A tiles for the ROI/date range into `dst_folderpath`, build/append its
    TileCatalog, and return the catalog filepath (feed it to `create_training_data`).

    `source` (spec 32): `"cdse"` (default) wraps `sources.cdse.download` and requires
    `creds`; `"mpc"` wraps `sources.mpc.download` (Microsoft Planetary Computer,
    anonymous by default — `creds` is not required and `cog` is ignored, MPC assets
    are already COG). Preflighted. `storage` is a seam (local only in P0). See specs/16.

    `runner="local"` (default) downloads in-process, as above. `runner="aml"` (spec
    37 P2) dispatches onto an Azure ML cluster instead, colocated with blob: CDSE
    runs as **one** job; MPC **fans out** across N (D1). `runner_kwargs` carries
    `cluster=`/`environment=`/`root=`/`identity_client_id=`/ and, for CDSE, exactly
    one of `vault_url=`+`secret_name=` (Key Vault) or `creds_url=` (blob JSON) — D5
    REVISED, see `workflows.runners.run_aml_download`. `creds` is ignored for
    `runner="aml"`: the dispatched job reads them on the node instead, so `roi`
    must be a url the node can also read (not an in-memory GeoDataFrame).

    `dst_folderpath` is the identity of this download (spec 47 D3): its `TileCatalog` is what a
    re-run diffs against to skip what is already there, so re-running with a different `roi`/
    `startdate`/`enddate`/`bands` into the same `dst_folderpath` appends into one shared catalog
    rather than starting a new one.
    """
    startdate, enddate, date_errs = _normalize_window(startdate, enddate)
    errs = _check_local_seams(runner, storage) + date_errs
    if not date_errs:
        errs += _check_window(startdate, enddate, 20, bands)
    if source not in ("cdse", "mpc"):
        errs.append(f"source={source!r} must be one of 'cdse', 'mpc'.")
    if max_tiles < 1:
        errs.append(f"max_tiles ({max_tiles}) must be >= 1.")
    if runner == "local" and source == "cdse" and creds is None:
        errs.append("creds (CdseCredentials) required for source='cdse' with runner='local'.")
    _raise_preflight(errs)

    _configure_storage(storage)
    fs.makedirs(dst_folderpath)
    catalog_filepath = os.path.join(dst_folderpath, "catalog.parquet")

    if runner == "aml":
        from fsd.workflows import runners as _runners

        _runners.run_aml_download(
            roi=roi, startdate=startdate, enddate=enddate, bands=bands,
            dst_folderpath=dst_folderpath, catalog_filepath=catalog_filepath,
            source=source, max_tiles=max_tiles, max_cloudcover=max_cloudcover, cog=cog,
            **(runner_kwargs or {}),
        )
        return catalog_filepath

    catalog = TileCatalog(catalog_filepath)
    if source == "mpc":
        _mpc_download(
            roi=roi, startdate=startdate, enddate=enddate, bands=bands,
            root_folderpath=dst_folderpath, catalog=catalog,
            max_tiles=max_tiles, max_cloudcover=max_cloudcover, progress=progress,
        )
    else:
        _cdse_download(
            roi=roi, startdate=startdate, enddate=enddate, bands=bands,
            root_folderpath=dst_folderpath, catalog=catalog, creds=creds,
            max_tiles=max_tiles, max_cloudcover=max_cloudcover, cog=cog, progress=progress,
        )
    return catalog_filepath


_download_verb = download  # internal alias: `create_training_data`'s `download` bool param
                           # shadows the module-level `download` verb within its own body.


def create_training_data(
    label_polygons,
    catalog_filepath: str,
    startdate: datetime.datetime,
    enddate: datetime.datetime,
    mosaic_days: int,
    bands: list[str],
    id_col: str,
    export_folderpath: str,
    *,
    label_col: str | None = None,
    scl_mask_classes: list[int] = config.SCL_MASK_CLASSES,
    adapter=None,
    feature_sequence=None,
    aggregate=None,
    cores: int = 1,
    source: str = "mpc",
    download: bool = False,
    max_tiles: int | None = None,
    max_cloudcover: float | None = None,
    cog: bool = True,
    creds: CdseCredentials | None = None,
    runner: str = "local",
    runner_kwargs: dict | None = None,
    storage=None,
    run_folderpath: str | None = None,
) -> TrainingData:
    """Label polygons (+ imagery) -> flattened, locally-landed training arrays: the
    full-pipeline façade (spec 39 D1).

    Orchestrates an optional download phase, `workflows.create_datacube` (one datacube per
    polygon, calendar mosaic), then `flatten_training_data` — the user never types "flatten".
    Returns a `TrainingData` handle.

    **Download phase (D1):** `download=False` (default, back-compat) requires `catalog_filepath`
    to already exist (run `fsd.download` first — compute never fetches from a provider
    implicitly, spec 23 D13). `download=True` first calls `fsd.download(roi=label_polygons, ...)`
    into `catalog_filepath`'s folder (`source="mpc"` demo default; `"cdse"` needs `creds` for
    `runner="local"`), then proceeds to build + flatten. `max_tiles` is required when
    `download=True` (spec 37 D7 guardrail — no silent default).

    **Blob-vs-local split (Q2, `runner="aml"` only):** `export_folderpath` is always the LOCAL
    landing target for the compact array; the blob working root is `runner_kwargs["root"]`
    (catalog/cubes/`input.csv`/the raw flatten output all live there). `run_folderpath` defaults
    to a folder under that blob root for `runner="aml"`, and to `export_folderpath/run` only for
    `runner="local"`.

    **In-memory polygons (Q3):** for `runner="aml"`, an in-memory `label_polygons` GeoDataFrame
    is materialized once to a GeoJSON under the blob `root` and that one URL serves as both the
    download ROI and the per-cell build shapefile. A path/URL `label_polygons` is used as-is.

    Feature engineering (P0.5, spec 18 / ADR-0020): pass an `adapter` (preferred — its
    `feature_sequence` is the *same* one used at inference, the F1 anti-skew guarantee) **or** a
    raw `feature_sequence` (adapter-less/exploratory). `aggregate` ∈ {None, "median_per_id",
    callable} reduces per-pixel samples before the transform. When any is given, fsd writes
    `features.npy` (+ `feature_ids`/`feature_labels`) additively **on the driver, after
    land-local** — the raw `data.npy` is kept; cluster images stay general-purpose.

    `label_col` (D-labels) is optional: when omitted, no `labels.npy` is written and `ids.npy`
    is the join key for labels joined in later, without re-flattening.

    `runner="local"` (default) or `"aml"` (spec 36/37/39 P2: dispatches download + the build
    fan-out + the flatten reduce onto an Azure ML cluster, `runner_kwargs` carries its
    `cluster=`/`environment=`/`root=`/`identity_client_id=`, see `workflows.runners`).
    """
    if adapter is not None and feature_sequence is not None:
        raise PreflightError(
            "pass either `adapter` or `feature_sequence`, not both (ambiguous feature transform)."
        )

    startdate, enddate, date_errs = _normalize_window(startdate, enddate)
    errs = _check_local_seams(runner, storage) + date_errs
    if not date_errs:
        errs += _check_window(startdate, enddate, mosaic_days, bands)
    if adapter is not None:
        req = list(getattr(adapter, "required_bands", []) or [])
        missing = [b for b in req if b not in bands]
        if missing:
            errs.append(f"adapter.required_bands not in requested bands: {missing}")
        # D6: no n_timestamps preflight -- T is caller-set; DemoRF retrains at whatever
        # T the window/mosaic_days produce. The calendar-mosaic same-timestamps
        # cross-cube invariant (spec 15) still holds -- flatten raises on disagreement.
    try:
        _resolve_aggregate(aggregate)
    except ValueError as exc:
        errs.append(str(exc))

    gdf = None
    try:
        gdf = _as_gdf(label_polygons)
        if id_col not in gdf.columns:
            errs.append(f"column {id_col!r} not in label_polygons.")
        if label_col is not None and label_col not in gdf.columns:
            errs.append(f"column {label_col!r} not in label_polygons.")
        if len(gdf) == 0:
            errs.append("label_polygons is empty.")
        elif gdf.geometry.isna().any():
            errs.append("label_polygons has null geometries.")
    except Exception as exc:  # unreadable polygons is a preflight failure, not a crash
        errs.append(f"could not read label_polygons: {exc}")

    root = (runner_kwargs or {}).get("root")
    if runner == "aml" and not root:
        errs.append("runner_kwargs['root'] (the blob working root) is required for runner='aml'.")

    if download:
        if source not in ("cdse", "mpc"):
            errs.append(f"source={source!r} must be one of 'cdse', 'mpc'.")
        if max_tiles is None or max_tiles < 1:
            errs.append(f"max_tiles (>= 1) is required when download=True (got {max_tiles!r}).")
        if runner == "local" and source == "cdse" and creds is None:
            errs.append("creds (CdseCredentials) required for source='cdse' with runner='local'.")
    else:
        catalog_present = fs.exists(catalog_filepath)
        if not catalog_present:
            errs.append(
                f"catalog_filepath does not exist: {catalog_filepath} "
                "— run fsd.download first, or pass download=True (compute never fetches "
                "from a provider implicitly; spec 23 D13)."
            )
        # D13 guardrail: catalog exists but covers NONE of the fields in-window -> actionable
        # download plan (the offline .filter is cheap; the STAC-backed plan only fires on the
        # empty case). Only meaningful when NOT auto-downloading.
        if catalog_present and gdf is not None and len(gdf) and not gdf.geometry.isna().any():
            try:
                covered = TileCatalog(catalog_filepath).filter(gdf, startdate, enddate)
            except Exception:  # noqa: BLE001 - a bad filter just means "skip the coverage hint"
                covered = None
            if covered is not None and len(covered) == 0:
                errs.append(_imagery_missing_message(
                    gdf, startdate, enddate, bands, catalog_filepath=catalog_filepath,
                    why="no catalog tiles intersect the label polygons in-window",
                ))
    _raise_preflight(errs)

    _configure_storage(storage)

    run_id = None
    if runner == "aml":
        run_id = (runner_kwargs or {}).get("run_id") or pd.Timestamp.now(tz="UTC").strftime(
            "%Y%m%dT%H%M%SZ"
        )
        if run_folderpath is None:
            run_folderpath = f"{root.rstrip('/')}/runs/{run_id}"
    elif run_folderpath is None:
        run_folderpath = os.path.join(export_folderpath, "run")

    fs.makedirs(run_folderpath)
    fs.makedirs(export_folderpath)

    # Materialize an in-memory GeoDataFrame once, under run_folderpath (the blob root for
    # aml, per Q3) -- the SAME url feeds both the download ROI and the build shapefile.
    # Written via the storage seam (not gdf.to_file, which needs a real local path) so
    # this lands correctly on a blob run_folderpath too (mirrors create_datacube.setup).
    if isinstance(label_polygons, gpd.GeoDataFrame):
        shapefilepath = os.path.join(run_folderpath, "label_polygons.geojson")
        with fs.open(shapefilepath, "w") as f:
            # `default=str` so Timestamp/datetime property columns (e.g. EuroCrops' obs
            # date) serialize -- gdf.to_json() routes through json.dumps, which (unlike
            # the GDAL GeoJSON driver the old gdf.to_file used) can't encode a Timestamp.
            f.write(gdf.to_json(default=str))
    else:
        shapefilepath = label_polygons

    if download:
        dst_folderpath = os.path.dirname(catalog_filepath.rstrip("/")) or "."
        _download_verb(
            roi=shapefilepath, startdate=startdate, enddate=enddate, bands=bands,
            dst_folderpath=dst_folderpath, creds=creds, source=source,
            max_tiles=max_tiles, max_cloudcover=max_cloudcover, cog=cog,
            storage=storage, runner=runner, runner_kwargs=runner_kwargs,
        )

    csv_filepath = os.path.join(run_folderpath, "input.csv")
    _create_datacube.run_create_datacube(
        catalog_filepath=catalog_filepath, timestamp_col="timestamp",
        shapefilepath=shapefilepath, id_col=id_col, run_folderpath=run_folderpath,
        startdate=startdate, enddate=enddate, bands=bands,
        scl_mask_classes=scl_mask_classes, mosaic_days=mosaic_days,
        csv_filepath=csv_filepath, label_col=label_col, cores=cores, runner=runner,
        runner_kwargs=runner_kwargs,
    )

    # Flatten phase delegates to `flatten_training_data` (D5) -- no duplicated reduce/
    # land/features logic. Reuse the SAME run_id (aml) so the flatten reduce writes to a
    # sibling `.../_flatten` prefix under the build's own run_folderpath (D7).
    flatten_runner_kwargs = runner_kwargs
    if runner == "aml":
        flatten_runner_kwargs = dict(runner_kwargs or {})
        flatten_runner_kwargs["run_id"] = run_id

    td = flatten_training_data(
        csv_filepath, export_folderpath,
        id_col="id", label_col=("label" if label_col is not None else None),
        filepath_col="datacube_filepath",
        adapter=adapter, feature_sequence=feature_sequence, aggregate=aggregate,
        runner=runner, runner_kwargs=flatten_runner_kwargs,
    )

    return TrainingData(
        export_folderpath=td.export_folderpath, run_folderpath=run_folderpath,
        n_pixels=td.n_pixels, n_timestamps=td.n_timestamps, bands=td.bands,
        feature_bands=td.feature_bands,
    )


def flatten_training_data(
    input_csv: str,
    export_folderpath: str,
    *,
    id_col: str = "id",
    label_col: str | None = None,
    filepath_col: str = "datacube_filepath",
    nodata: int = config.NODATA,
    adapter=None,
    feature_sequence=None,
    aggregate=None,
    runner: str = "local",
    runner_kwargs: dict | None = None,
    storage=None,
) -> TrainingData:
    """Flatten already-built cubes (an `input_csv` of `datacube_filepath`s) into one training
    array, landed locally (spec 39 D5) — the flatten-only sibling of `create_training_data`, for
    cubes that already exist on blob (e.g. runbook 36 Phase 3's `input.csv`).

    `runner="local"` (default): `datacube.flatten.flatten` runs in-process (cubes stream over the
    storage seam) straight to the local `export_folderpath`. `runner="aml"`: dispatches the D3
    single-node cluster reduce (writes to a blob prefix under `runner_kwargs["root"]`, no
    `shard_units` fan-out — flatten concatenates ALL cubes into ONE array), then `storage.transfer`s
    the compact result down to the local `export_folderpath` (D4 land-local; the driver never pulls
    the raw cubes itself, ADR-0004). Both branches then apply the optional driver-side feature
    transform (D2/ADR-0020: general-purpose cluster images emit raw; `adapter`/`feature_sequence`
    only ever runs on the driver).

    `label_col` (D-labels) optional: `labels.npy` is written only when given.
    """
    if adapter is not None and feature_sequence is not None:
        raise PreflightError(
            "pass either `adapter` or `feature_sequence`, not both (ambiguous feature transform)."
        )

    errs = _check_local_seams(runner, storage)
    try:
        _resolve_aggregate(aggregate)
    except ValueError as exc:
        errs.append(str(exc))
    if runner == "aml":
        rk = runner_kwargs or {}
        for key in ("cluster", "environment", "root", "identity_client_id"):
            if not rk.get(key):
                errs.append(f"runner_kwargs[{key!r}] is required for runner='aml'.")
    if not fs.exists(input_csv):
        errs.append(f"input_csv does not exist: {input_csv!r}")
    _raise_preflight(errs)

    _configure_storage(storage)
    fs.makedirs(export_folderpath)

    if runner == "aml":
        from fsd.workflows import runners as _runners

        rk = dict(runner_kwargs or {})
        aml_root = rk.pop("root")
        run_id = rk.pop("run_id", None) or pd.Timestamp.now(tz="UTC").strftime("%Y%m%dT%H%M%SZ")
        blob_export = f"{aml_root.rstrip('/')}/runs/{run_id}/_flatten"

        _runners.run_aml_flatten(
            input_csv, blob_export, id_col=id_col, label_col=label_col,
            filepath_col=filepath_col, nodata=nodata, root=aml_root, run_id=run_id, **rk,
        )
        files = ["data.npy", "coords.npy", "ids.npy", "metadata.pickle.npy"]
        if label_col is not None:
            files.append("labels.npy")
        _land_local(blob_export, export_folderpath, files)
    else:
        with fs.open(input_csv, "r") as f:
            filepaths_df = pd.read_csv(f)
        _flatten.flatten(
            filepaths_df=filepaths_df, filepath_col=filepath_col, id_col=id_col,
            export_folderpath=export_folderpath, label_col=label_col, nodata=nodata,
        )

    data = fs.load_npy(os.path.join(export_folderpath, "data.npy"))
    metadata = fs.load_npy(
        os.path.join(export_folderpath, "metadata.pickle.npy"), allow_pickle=True
    )[()]

    feature_bands = None
    if adapter is not None or feature_sequence is not None or aggregate is not None:
        feature_bands = _apply_training_features(
            export_folderpath, metadata, adapter=adapter,
            feature_sequence=feature_sequence, aggregate=aggregate,
        )

    return TrainingData(
        export_folderpath=export_folderpath, run_folderpath=os.path.dirname(input_csv),
        n_pixels=int(data.shape[0]), n_timestamps=len(metadata["timestamps"]),
        bands=list(metadata["bands"]), feature_bands=feature_bands,
    )


def _land_local(blob_prefix: str, local_folder: str, files: list[str]) -> None:
    """D4: bring the compact flatten-reduce output home. One `storage.transfer` per file
    (`data.npy`/`coords.npy`/`ids.npy`/`metadata.pickle.npy` + `labels.npy` iff present) --
    `transfer` is single-object + atomic (`.part` + rename, `fs.py:282`), so a failed copy
    never leaves a truncated `.npy` and this loop is safe to re-run (existence = already landed)."""
    fs.makedirs(local_folder)
    for name in files:
        dst = os.path.join(local_folder, name)
        if fs.exists(dst):
            continue
        fs.transfer(os.path.join(blob_prefix, name), dst)


def _apply_training_features(export_folderpath, metadata, *, adapter, feature_sequence,
                             aggregate) -> list[str]:
    """Apply optional aggregation + the feature transform to flattened arrays (F1/F4).

    Writes `features.npy` (+ `feature_ids`/`feature_labels`) additively, records `feature_bands`
    + `aggregate` in metadata, and returns the feature band names. The raw `data.npy` is kept.
    """
    data = fs.load_npy(os.path.join(export_folderpath, "data.npy"))        # (pixels, T, B)
    ids = fs.load_npy(os.path.join(export_folderpath, "ids.npy"))
    labels_path = os.path.join(export_folderpath, "labels.npy")
    labels = fs.load_npy(labels_path) if fs.exists(labels_path) else None

    reducer = _resolve_aggregate(aggregate)
    if reducer is not None:
        ids, data, labels = reducer(ids, data.astype(float), labels)

    band_indices = {b: i for i, b in enumerate(metadata["bands"])}
    feats5d, feat_bi = _apply_features(
        _modify.expand_flattened(data.astype(float)), band_indices,
        adapter=adapter, feature_sequence=feature_sequence,
    )
    features = np.squeeze(feats5d, axis=(2, 3))                            # (pixels, T, Bf)
    feature_bands = [b for b, _ in sorted(feat_bi.items(), key=lambda kv: kv[1])]

    fs.save_npy(os.path.join(export_folderpath, "features.npy"), features)
    fs.save_npy(os.path.join(export_folderpath, "feature_ids.npy"), np.asarray(ids))
    if labels is not None:
        fs.save_npy(os.path.join(export_folderpath, "feature_labels.npy"), np.asarray(labels))

    agg_name = aggregate if isinstance(aggregate, str) else (
        getattr(aggregate, "__name__", "callable") if aggregate else None
    )
    metadata = dict(metadata)
    metadata["feature_bands"] = feature_bands
    metadata["aggregate"] = agg_name
    fs.save_npy(
        os.path.join(export_folderpath, "metadata.pickle.npy"), metadata, allow_pickle=True
    )
    return feature_bands


def _model_spec(model) -> dict:
    """Read the declared spec (required_bands, n_timestamps, output_*) from a live adapter or,
    for a bundle path, from `bundle.json` alone (model-free — no import, no model load)."""
    if isinstance(model, str):
        return _bundle.read_spec(model)
    return {
        "required_bands": list(getattr(model, "required_bands", []) or []),
        "n_timestamps": int(getattr(model, "n_timestamps", 0) or 0),
        "output_dtype": getattr(model, "output_dtype", None),
        "output_nodata": getattr(model, "output_nodata", None),
        "output_band_names": list(getattr(model, "output_band_names", []) or []),
    }


def _resolve_inference_pairs(inference_datacubes, output_folderpath):
    """-> (pairs, geometries). `pairs` = [(datacube_filepath, output_filepath)]. Accepts an
    input.csv, a folder of datacube subfolders, or an explicit list of `datacube.npy` filepaths.

    `geometries` (spec 28) = `{output_filepath: shapefilepath}` when the source is an `input.csv`
    with a `shapefilepath` column (the manifest-driven STAC-geometry contract); `None` for the
    folder/list modes, which have no manifest to source a footprint from (STAC falls back to the
    raster bbox for those).
    """
    ids = None
    shapefilepaths = None
    if isinstance(inference_datacubes, (list, tuple)):
        dc_filepaths = [str(p) for p in inference_datacubes]
    elif isinstance(inference_datacubes, str) and inference_datacubes.endswith(".csv"):
        with fs.open(inference_datacubes, "r") as f:
            df = pd.read_csv(f)
        col = "datacube_filepath" if "datacube_filepath" in df.columns else df.columns[0]
        dc_filepaths = [str(p) for p in df[col]]
        if "id" in df.columns:
            ids = [str(i) for i in df["id"]]
        if "shapefilepath" in df.columns:
            shapefilepaths = [str(p) for p in df["shapefilepath"]]
    else:  # a folder: each subfolder holds a datacube.npy
        dc_filepaths = sorted(fs.glob(os.path.join(str(inference_datacubes), "*", "datacube.npy")))

    pairs = []
    geometries = {} if shapefilepaths is not None else None
    for i, dc in enumerate(dc_filepaths):
        stem = ids[i] if ids is not None else os.path.basename(os.path.dirname(dc))
        out = os.path.join(str(output_folderpath), stem, "output.tif")
        pairs.append((dc, out))
        if shapefilepaths is not None:
            geometries[out] = shapefilepaths[i]
    return pairs, geometries


def _merge_outputs(filepaths, dst, nodata, *, reproject_to_dominant: bool = False,
                   merge_crs=None) -> str:
    """Merge output COGs into one COG (spec 21/23).

    `reproject_to_dominant=False` (``merge=True``) — **strict single-CRS** merge; multi-CRS
    **raises** (the per-output COGs + STAC are the multi-zone answer; fsd single-CRS-merge
    principle). Data-faithful: no resampling.

    `reproject_to_dominant=True` (``merge="reproject"``) — reproject every output to one CRS with
    **nearest-neighbour** (categorical output must not be interpolated), then mosaic. The target is
    ``merge_crs`` if given (EPSG int or CRS string), else the **max-total-area** CRS across cells
    (spec 23, D7 — correct for clipped ROI-edge cells; falls back to most-cells). **Lossless where a
    cell already matches the target** (no resampling); reprojected only for cells changing zone.
    Cross-UTM-zone-safe; the per-cell COGs stay authoritative.
    """
    import tempfile
    import uuid as _uuid

    import rasterio

    from fsd.raster import rio_env

    # The outputs may live on `abfss://`, which GDAL has no driver for, so every READ goes through
    # the VSI seam (CLAUDE.md: raster pixel reads use rasterio/GDAL VSI). Bare `rasterio.open(fp)`
    # here is why merging blob-hosted outputs failed -- the 5th instance of the repo's
    # "GDAL assumed to handle abfss://" class (after cdse `_roi_gdf`, `task.py`, spec-39 gdf
    # staging, and grids.geojson `9422a1a`).
    #
    # `rio_env(filepaths)` + `rasterio.open(to_vsi(fp))`, NOT `rio_open` per file: `rio_open` owns
    # a `rasterio.Env` per handle, and merge holds every input open at once. rasterio's env stack
    # is LIFO, so closing 300 of them in creation order tears down the root env first and the next
    # close raises `EnvError: No GDAL environment exists` (run-book 38 Phase 4, 2026-07-28). One env
    # for the whole merge is both correct and cheaper -- one token fetch, not N. It is a null
    # context for local paths, so local merges are unchanged.
    with rio_env(filepaths):
        mosaic, out_transform, profile = _merge_mosaic(
            filepaths, nodata, reproject_to_dominant=reproject_to_dominant, merge_crs=merge_crs,
        )

    # D5 (spec 38, ADR 0001): the raw scratch tif must be LOCAL regardless of `dst` -- a
    # remote `dst` (e.g. abfss://.../merged.tif) would otherwise get "merged.tif.raw.tif"
    # appended onto the same remote URL, which rasterio (local/VSI-write only) cannot
    # open. `to_cog` itself already knows how to publish a local raw file to a remote
    # `dst` (its own remote-dst branch); this only needs to give it a local source.
    if fs.is_local(dst):
        raw = f"{dst}.raw.tif"
    else:
        raw = os.path.join(tempfile.gettempdir(), f"fsd-merge-{_uuid.uuid4().hex}.raw.tif")
    try:
        with rasterio.open(raw, "w", **profile) as d:
            d.write(mosaic)
        _to_cog(raw, dst)
    finally:
        if os.path.exists(raw):
            os.remove(raw)
    return dst


def _merge_mosaic(filepaths, nodata, *, reproject_to_dominant: bool, merge_crs):
    """The mosaic itself. Must run inside a `rio_env(filepaths)` -- every `rasterio.open` below
    is on a VSI-translated path whose credentials live in that env."""
    import tempfile
    import uuid as _uuid

    import rasterio
    from rasterio.merge import merge as rio_merge

    from fsd.storage.azure import to_vsi

    # D5 (spec 47): tick per input opened -- this is the WAN-latency-bound part (every
    # per-cell COG read over /vsiadls/, measured ~1000s on 300 cells), matching [setup]'s
    # shape exactly.
    tick = _progress.ticker(len(filepaths), "merge", unit="inputs")
    tick(0, force=True)

    if reproject_to_dominant:
        from rasterio.crs import CRS as _RioCRS
        from rasterio.warp import Resampling, calculate_default_transform
        from rasterio.warp import reproject as rio_reproject

        area_by_crs: dict[str, float] = {}
        for i, fp in enumerate(filepaths, 1):
            with rasterio.open(to_vsi(fp)) as s:
                key = s.crs.to_string()
                # extent area in the cell's own (metric UTM) CRS — comparable across UTM zones
                area_by_crs[key] = area_by_crs.get(key, 0.0) + (
                    abs(s.transform.a * s.transform.e) * s.width * s.height
                )
            tick(i)
        if merge_crs is not None:
            target = _RioCRS.from_user_input(merge_crs).to_string()   # user-forced target CRS
        elif any(area_by_crs.values()):
            target = max(area_by_crs, key=area_by_crs.get)            # dominant zone = max total area
        else:
            target = max(area_by_crs, key=lambda k: len(k))          # degenerate fallback

        datasets, tmps = [], []
        try:
            for fp in filepaths:
                src = rasterio.open(to_vsi(fp))
                if src.crs.to_string() == target:
                    datasets.append(src)
                    continue
                transform, w, h = calculate_default_transform(
                    src.crs, target, src.width, src.height, *src.bounds)
                prof = src.profile.copy()
                prof.update(driver="GTiff", crs=target, transform=transform,
                            width=w, height=h, nodata=nodata)
                # Local scratch, never `f"{fp}.reproj.tif"`: a remote `fp` would put the
                # temp on the remote URL, and rasterio cannot open a remote path for WRITE
                # (D5 / ADR-0001 -- the same lesson the `raw` file below already applies).
                tmp = os.path.join(tempfile.gettempdir(),
                                   f"fsd-reproj-{_uuid.uuid4().hex}.tif")
                tmps.append(tmp)
                with rasterio.open(tmp, "w", **prof) as d:
                    rio_reproject(
                        rasterio.band(src, 1), rasterio.band(d, 1),
                        src_transform=src.transform, src_crs=src.crs,
                        dst_transform=transform, dst_crs=target,
                        src_nodata=nodata, dst_nodata=nodata,
                        resampling=Resampling.nearest,  # categorical-safe
                    )
                src.close()
                datasets.append(rasterio.open(tmp))  # local scratch -- bare open is right
            mosaic, out_transform = rio_merge(datasets, nodata=nodata)
            profile = datasets[0].profile.copy()
            profile.update(driver="GTiff", height=mosaic.shape[1], width=mosaic.shape[2],
                           transform=out_transform, crs=target, nodata=nodata)
        finally:
            for d in datasets:
                d.close()
            for t in tmps:
                if os.path.exists(t):
                    os.remove(t)
    else:
        srcs = []
        for i, fp in enumerate(filepaths, 1):
            srcs.append(rasterio.open(to_vsi(fp)))
            tick(i)
        try:
            crs_set = {s.crs.to_string() for s in srcs}
            if len(crs_set) > 1:
                raise PreflightError(
                    f"cannot merge outputs across multiple CRS {sorted(crs_set)}; pass "
                    'merge="reproject" for a display map (reprojects to the dominant zone, '
                    "lossy), or use the per-output COGs + STAC (fsd single-CRS-merge principle)."
                )
            mosaic, out_transform = rio_merge(srcs, nodata=nodata)
            profile = srcs[0].profile.copy()
            profile.update(driver="GTiff", height=mosaic.shape[1], width=mosaic.shape[2],
                           transform=out_transform, nodata=nodata)
        finally:
            for s in srcs:
                s.close()

    tick(len(filepaths), force=True)
    return mosaic, out_transform, profile


def _finalize_outputs(output_filepaths, output_folderpath, spec, merge, collection_id, dt,
                      *, grids_filepath=None, merge_crs=None, geometries=None) -> InferenceResult:
    """Shared tail for both inference modes: STAC catalog + optional merge -> InferenceResult.

    `geometries` (spec 28): `{output_filepath: geometry.geojson_path}` sourced from the build
    manifest — the true per-cell footprint, forwarded to `cog_outputs_to_items` in place of the
    raster bbox. `None` for geometry-less callers (see `_resolve_inference_pairs`).
    """
    items = _stac.cog_outputs_to_items(
        output_filepaths, geometries=geometries, collection_id=collection_id,
        band_names=spec.get("output_band_names") or None, dt=dt,
    )
    stac_catalog_filepath = _stac.write_stac_catalog(
        items, os.path.join(output_folderpath, "stac"),
        catalog_id="fsd-inference", collection_id=collection_id,
        description="fsd inference outputs (STAC).",
    )
    merged_filepath = None
    if merge:
        merged_filepath = _merge_outputs(
            output_filepaths, os.path.join(output_folderpath, "merged.tif"),
            nodata=spec.get("output_nodata"),
            reproject_to_dominant=(merge == "reproject"), merge_crs=merge_crs,
        )
    return InferenceResult(
        output_folderpath=output_folderpath, output_filepaths=sorted(output_filepaths),
        stac_catalog_filepath=stac_catalog_filepath, merged_filepath=merged_filepath,
        grids_filepath=grids_filepath,
    )


def run_inference(
    model,
    inference_datacubes=None,
    output_folderpath: str | None = None,
    *,
    # --- ROI mode (spec 21) — mutually exclusive with inference_datacubes ---
    roi=None,
    catalog_filepath: str | None = None,
    startdate: datetime.datetime | None = None,
    enddate: datetime.datetime | None = None,
    mosaic_days: int | None = None,
    bands: list[str] | None = None,
    grid_size_km: float = 5,
    scale_fact: float = 1.1,
    scl_mask_classes: list[int] | None = None,
    # --- shared ---
    predict_batch_size: int | None = None,
    skip_nan: bool = True,
    merge=False,
    merge_crs=None,
    cores: int | None = None,
    cubes_per_task: int | None = None,
    overwrite: bool = False,
    runner: str = "local",
    runner_kwargs: dict | None = None,
    storage=None,
    collection_id: str = "fsd-inference",
    dt=None,
    progress: bool = True,
) -> InferenceResult:
    """Run a model over inference datacubes -> one COG per cube + a STAC catalog (+ optional merge).

    Two mutually-exclusive modes:

    - **pre-built cubes** (spec 18): pass ``inference_datacubes`` — an ``input.csv``, a folder of
      datacube subfolders, or a list of ``datacube.npy`` filepaths. ``cores=1`` infers in-process
      (sequential); ``cores>1`` fans out via the Snakemake **infer-only** runner (spec 22 — fsd has
      no in-process pool; ``cubes_per_task`` groups cubes per job to amortise the bundle load).

    ``cores``/``cubes_per_task`` default to ``None`` = **auto**: for the local/pre-built paths that
    means today's ``1`` (sequential, one cube per job); for **ROI mode + ``runner="aml"``** it means
    D7's *load-per-core* default — the node picks ``cores = os.cpu_count()`` and groups cells so the
    bundle loads once per core (not once per cell, TODO #25), computed on the node from the shard size
    (`workflows.infer_shard`). Pass ``cores=1`` there for the heavy-model *load-once-per-node* opt-out
    (one whole-shard group, one bundle load).
    - **ROI** (spec 21, P0.75 — completes Mode A): pass ``roi`` (+ ``catalog_filepath``,
      ``startdate``/``enddate``/``mosaic_days``/``bands``). fsd tiles the ROI into S2 grid cells
      (``fsd.grid``), then fans out a per-cell **build-datacube + infer -> COG** task through the
      **runner seam** (Snakemake locally; Batch swaps in at P4 unchanged). Imagery is assumed
      already present in ``catalog_filepath`` — inference never touches CDSE (conserve quota).
      **``output_folderpath`` is the identity of the run** (spec 47 D3): re-running ROI mode into
      the same ``output_folderpath`` resumes the cached per-cell work list, so it must name this
      exact ``roi``/``grid_size_km``/``scale_fact`` — reusing it for a different roi raises
      ``PreflightError`` (D1) rather than silently mixing work lists.

    `model` is a live `ModelAdapter` or a **bundle path**; a bundle is required for ROI mode and for
    ``cores>1`` (both cross a subprocess) — a live adapter is auto-saved to a temp bundle. Preflight
    (before any build) asserts bands ⊇ ``required_bands`` and ``T == n_timestamps``. Inference is
    **idempotent**: existing outputs are skipped unless ``overwrite=True`` (spec 22). ``merge``:
    ``False`` | ``True`` (strict single-CRS) | ``"reproject"`` (cross-UTM-zone-safe merge to one
    CRS — ``merge_crs`` if given, else the max-total-area zone; lossless where a cell already
    matches the target). `runner`/`storage` are local-only for the pre-built-cubes path and for
    local ROI mode; **ROI mode + ``runner="aml"``** (spec 38 P4) accepts ``storage="azure"``/an
    ``abfss://`` root and dispatches the per-cell build+infer task onto an Azure ML cluster
    instead (`runner_kwargs` carries `cluster=`/`environment=`/`root=`/`identity_client_id=`,
    see `workflows.runners.run_aml_inference`) — the local↔AML equivalence spec 36 Phase 3b
    proved for datacubes, now for inference.
    """
    # D14 (spec 38): storage-on-blob is P4's own scope -- allowed for ROI mode +
    # runner="aml" (routes to run_aml_inference), unchanged (local only) for the
    # pre-built-cubes path and for local ROI mode.
    roi_mode = roi is not None
    errs = _check_local_seams(runner, storage, storage_allowed=(roi_mode and runner == "aml"))
    if output_folderpath is None:
        errs.append("output_folderpath is required.")
    if merge not in (False, True, "reproject"):
        errs.append(f'merge must be False, True, or "reproject" (got {merge!r}).')
    # D10 (spec 38): `dt` (the STAC output-item datetime) is natural-typed `datetime`/
    # `Timestamp` -- coerce a caller-supplied string at this boundary rather than forward
    # it raw into `pystac.Item(datetime=...)`, which expects a real datetime object.
    if dt is not None:
        try:
            dt = pd.to_datetime(dt, utc=True).to_pydatetime()
        except (ValueError, TypeError) as exc:
            errs.append(f"dt={dt!r} is not a valid date: {exc}")

    if roi_mode and inference_datacubes is not None:
        errs.append("pass either roi= or inference_datacubes=, not both.")
    if not roi_mode and inference_datacubes is None:
        errs.append("pass roi= (ROI mode) or inference_datacubes= (pre-built cubes).")

    spec = _model_spec(model)

    if roi_mode:
        return _run_inference_roi(
            model, spec, roi, output_folderpath, errs,
            catalog_filepath=catalog_filepath, startdate=startdate, enddate=enddate,
            mosaic_days=mosaic_days, bands=bands, grid_size_km=grid_size_km,
            scale_fact=scale_fact, scl_mask_classes=scl_mask_classes,
            predict_batch_size=predict_batch_size, skip_nan=skip_nan, merge=merge,
            merge_crs=merge_crs, cores=cores, cubes_per_task=cubes_per_task, overwrite=overwrite,
            collection_id=collection_id, dt=dt, runner=runner, runner_kwargs=runner_kwargs,
        )

    # --- pre-built cubes path (spec 18) ---
    required = set(spec.get("required_bands") or [])
    want_t = int(spec.get("n_timestamps") or 0)
    pairs, geometries = _resolve_inference_pairs(inference_datacubes, output_folderpath)
    if not pairs:
        errs.append(f"no inference datacubes found under {inference_datacubes!r}.")
    for dc_fp, _ in pairs:
        md_fp = os.path.join(os.path.dirname(dc_fp), "metadata.pickle.npy")
        if not fs.exists(dc_fp) or not fs.exists(md_fp):
            errs.append(f"missing datacube/metadata for {dc_fp}.")
            continue
        md = fs.load_npy(md_fp, allow_pickle=True)[()]
        missing = required - set(md["bands"])
        if missing:
            errs.append(f"{dc_fp}: datacube lacks required bands {sorted(missing)}.")
        if want_t and len(md["timestamps"]) != want_t:
            errs.append(
                f"{dc_fp}: datacube T={len(md['timestamps'])} but model needs T={want_t}."
            )
    _raise_preflight(errs)

    fs.makedirs(output_folderpath)
    # `None` = auto; the pre-built path has no node to interrogate, so auto == today's default (1).
    pb_cores = 1 if cores is None else cores
    pb_cubes_per_task = 1 if cubes_per_task is None else cubes_per_task
    if pb_cores > 1:
        # cores>1 fans out via the Snakemake infer-only runner (spec 22 — no in-process pool)
        output_filepaths = _run_prebuilt_via_runner(
            model, pairs, output_folderpath, cores=pb_cores, cubes_per_task=pb_cubes_per_task,
            overwrite=overwrite, predict_batch_size=predict_batch_size, skip_nan=skip_nan,
        )
    else:
        output_filepaths = _engine.run_local(
            model, pairs, predict_batch_size=predict_batch_size, skip_nan=skip_nan,
            overwrite=overwrite, progress=progress,
        )
    return _finalize_outputs(output_filepaths, output_folderpath, spec, merge, collection_id, dt,
                             merge_crs=merge_crs, geometries=geometries)


def _ensure_bundle(model, output_folderpath, *, why):
    """Return a bundle path for `model`, auto-saving a live adapter (needs an importable class)."""
    if isinstance(model, str):
        return model
    try:
        return _bundle.save(
            model, getattr(model, "artifacts", {}) or {},
            os.path.join(output_folderpath, "_bundle"),
        )
    except Exception as exc:
        raise PreflightError(
            f"{why} needs a model bundle; auto-saving the live adapter failed ({exc}). Pass a "
            "bundle path (fsd.model.bundle.save) whose adapter class is importable by module:attr "
            "(not a __main__/interactive class)."
        ) from exc


def _run_prebuilt_via_runner(model, pairs, output_folderpath, *, cores, cubes_per_task,
                             overwrite, predict_batch_size, skip_nan) -> list[str]:
    """Fan out pre-built-cube inference through the Snakemake infer-only runner (spec 22)."""
    from fsd.workflows import runners as _runners

    bundle_path = _ensure_bundle(model, output_folderpath, why="cores>1 inference")
    run_dir = os.path.join(output_folderpath, "_infer_run")
    fs.makedirs(run_dir)
    csv_fp = os.path.join(run_dir, "input.csv")
    df = pd.DataFrame({"datacube_filepath": [dc for dc, _ in pairs],
                       "output_filepath": [out for _, out in pairs]})
    with fs.open(csv_fp, "w") as f:
        df.to_csv(f, index=False)

    result = _runners.run_local_infer_only(
        csv_fp, cores=cores, bundle_path=bundle_path, cubes_per_task=cubes_per_task,
        overwrite=overwrite, predict_batch_size=predict_batch_size, skip_nan=skip_nan,
    )
    if result.returncode != 0:
        raise RuntimeError(f"inference runner failed (snakemake exit {result.returncode}).")
    return [out for _, out in pairs if fs.exists(out)]


def _output_key(path: str) -> str:
    """`…/<window>/<cell_id>/output.tif` -> `<window>/<cell_id>/output.tif`.

    The trailing components are the only scheme-independent part of the path, and that
    is the whole point: `fs.glob` returns the *filesystem's* path form (adlfs gives
    `container/path/…`, with no `abfss://` scheme), so a globbed hit never string-equals
    the url a caller built with `os.path.join`. Matching on the tail makes the two
    comparable under either form — and cell ids are unique within a run (spec 21
    D-GRID-1), so `<window>/<cell_id>/output.tif` is unique too.
    """
    return "/".join(str(path).rstrip("/").replace("\\", "/").split("/")[-3:])


def _existing_outputs(candidates, *, run_folderpath: str) -> list[str]:
    """Which of `candidates` (per-cell `output.tif` urls) exist — in ONE listing rather
    than one `fs.exists` per cell (TODO #61).

    Measured on run-book 38 Phase 3: the driver's post-run collect was **729 s of a
    2066.9 s wall**, roughly three sequential blob round-trips per cell over VPN. This
    removes one of the three. Order follows `candidates`, as the per-cell `fs.exists`
    comprehension it replaces did.

    A pattern that matches nothing yields an empty list, and the caller already raises
    "no per-cell outputs were produced" on that — a loud failure, not a silent one.

    ⚠️ The `*/*` depth is a **contract with `create_datacube.setup`**, which builds
    `export_folderpath = run_folderpath/<window>/<id>` (`workflows/create_datacube.py`).
    Since spec 46 D1/D2 the `<window>` folder is derived from the run's *requested*
    `startdate`/`enddate`/`mosaic_days` — one window per run, shared by every cell —
    rather than each shape's actual acquisition range, so it no longer varies between
    cells of the same run. The glob still spans any middle component (old archives keep
    their pre-spec-46 actual-date folder names, spec 46 D3 — forward-only, no
    migration), so previously written outputs are still found; a further change to this
    layout must still change this pattern too.
    """
    # D5 (spec 47): TODO #61 already collapsed this to ONE `fs.glob` round trip, so there
    # is no per-candidate loop left to tick against -- print before/after instead, in the
    # same `[label] done/total (...) | elapsed` shape, rather than inventing a per-item
    # loop that no longer exists.
    tick = _progress.ticker(len(candidates), "collect", unit="candidates", show_rate=False)
    tick(0, force=True)
    hits = {
        _output_key(h)
        for h in fs.glob(os.path.join(str(run_folderpath), "*", "*", "output.tif"))
    }
    found = [c for c in candidates if _output_key(c) in hits]
    tick(len(found), force=True)
    return found


def _imagery_missing_message(roi, startdate, enddate, bands, *, catalog_filepath, why) -> str:
    """Build the D13 guardrail message: the plumbing found no imagery for this request, so turn the
    error into an actionable `fsd.download(...)` plan (spec 23). Degrades gracefully if the STAC
    query itself fails (still says clearly: run download first)."""
    base = (f"imagery for this ROI/window is not present in the catalog "
            f"({catalog_filepath!r}) — run fsd.download first, then re-run. [{why}]")
    try:
        from fsd.sources import cdse as _cdse

        plan = _cdse.plan_download(
            roi, startdate, enddate, bands, catalog_filepath=catalog_filepath,
        )
        return base + "\n" + _cdse.format_download_plan(plan)
    except Exception:  # noqa: BLE001 - the plan is a nicety; never mask the real "run download"
        return base


def _run_inference_roi(
    model, spec, roi, output_folderpath, errs, *,
    catalog_filepath, startdate, enddate, mosaic_days, bands,
    grid_size_km, scale_fact, scl_mask_classes,
    predict_batch_size, skip_nan, merge, merge_crs, cores, cubes_per_task, overwrite,
    collection_id, dt, runner="local", runner_kwargs=None,
) -> InferenceResult:
    """ROI mode (spec 21): preflight -> tile -> per-cell setup -> runner build+infer -> STAC/merge."""
    from fsd import grid as _grid
    from fsd.workflows import runners as _runners

    # --- preflight (cheap, before any build) ---
    for name, val in [("catalog_filepath", catalog_filepath), ("startdate", startdate),
                      ("enddate", enddate), ("mosaic_days", mosaic_days), ("bands", bands)]:
        if val is None:
            errs.append(f"roi mode requires {name}=.")
    # D9 (spec 38): normalize dates to Timestamp HERE, before compute_n_timestamps or any
    # dispatch -- this is the driver, before any AML job (D11 invariant: an unparseable date
    # must abort in milliseconds, not after a 40-380s node cold-start).
    if startdate is not None and enddate is not None:
        startdate, enddate, date_errs = _normalize_window(startdate, enddate)
        errs += date_errs
    required = set(spec.get("required_bands") or [])
    want_t = int(spec.get("n_timestamps") or 0)
    if bands is not None:
        missing = required - set(bands)
        if missing:
            errs.append(f"bands is missing model-required {sorted(missing)}.")
    if want_t and None not in (startdate, enddate, mosaic_days):
        got_t = compute_n_timestamps(startdate, enddate, mosaic_days)
        if got_t != want_t:
            errs.append(
                f"startdate/enddate/mosaic_days give T={got_t} but the model needs T={want_t}."
            )
    roi_gdf = None
    try:
        if isinstance(roi, gpd.GeoDataFrame):
            roi_gdf = roi
        elif isinstance(roi, str):
            roi_gdf = fs.read_geo(roi)   # storage seam, not gpd.read_file (TODO #47)
    except Exception as exc:  # noqa: BLE001 - surfaced as a preflight error
        errs.append(f"could not read roi: {exc}.")
    if roi_gdf is not None and len(roi_gdf) == 0:
        errs.append("roi is empty.")

    # 1) Tile the ROI -> S2 grid cells, INSIDE preflight (spec 21 D-GRID-1). Tiling is
    #    local, CPU-only work, so doing it here rather than after `_ensure_bundle` means a
    #    bad ROI costs seconds instead of: a blob `makedirs`, a bundle upload (measured 627 s
    #    for 13 MB over VPN), setup's N per-cell blob writes, and an AML dispatch.
    #    What it catches: an ROI that tiles to nothing, and DUPLICATE CELL IDS -- `id` is the
    #    work-unit key (`setup` derives `export_folderpath` from it), so duplicates put N
    #    tasks on one folder, which on blob is a concurrent same-blob write (`InvalidBlockList`,
    #    the 2026-07-28 Phase 3 failure) and locally a silent overwrite. `roi_to_s2_grids` now
    #    prevents them at source; this is the seatbelt, and it fires before any spend.
    grids = None
    if not errs:
        try:
            grids = _grid.roi_to_s2_grids(
                roi_gdf if roi_gdf is not None else roi,
                grid_size_km=grid_size_km, scale_fact=scale_fact,
            )
        except ImportError:
            raise  # the [grid] extra is missing -- spec 19's own message is the clear one
        except Exception as exc:  # noqa: BLE001 - surfaced as a preflight error
            errs.append(f"could not tile roi into grid cells: {exc}.")
    if grids is not None:
        if len(grids) == 0:
            errs.append(
                f"roi tiled into 0 grid cells at grid_size_km={grid_size_km} -- the roi is "
                f"smaller than one cell, or its geometry is degenerate."
            )
        elif grids["id"].duplicated().any():
            counts = grids["id"].value_counts()
            repeated = counts[counts > 1]
            errs.append(
                f"roi tiled into {len(grids)} rows but only {grids['id'].nunique()} distinct "
                f"cell ids ({len(repeated)} repeated, worst {int(counts.iloc[0])}x). One cell "
                f"must be one work-unit; duplicates would make several tasks write the same "
                f"output folder concurrently. Is `roi=` a REGION? Passing a per-feature file "
                f"(a label/field set) tiles per (cell x feature) pair -- see spec 21 D-GRID-1."
            )
    _raise_preflight(errs)

    # Cell count IS the cluster workload and the cost -- say it before spending anything.
    print(f"[run_inference] roi -> {len(grids)} grid cells at grid_size_km={grid_size_km} "
          f"(one build+infer task each)", flush=True)

    fs.makedirs(output_folderpath)

    # model must be a bundle (it crosses a subprocess); auto-save a live adapter.
    bundle_path = _ensure_bundle(model, output_folderpath, why="roi mode")

    grids_filepath = os.path.join(output_folderpath, "grids.geojson")
    # GDAL/pyogrio has no abfss:// write driver, so a blob output_folderpath makes
    # grids.to_file(grids_filepath) fail ("Failed to create GeoJSON datasource"). Stage via the
    # storage seam instead -- mirrors create_training_data's gdf staging and the seam READ in
    # create_datacube.setup (create_datacube.py:79). to_json(default=str) guards any non-JSON-native
    # column (spec 39 lesson); grids carry only id + geometry, but keep the guard for safety.
    with fs.open(grids_filepath, "w") as f:
        f.write(grids.to_json(default=str))

    # 2) per-cell setup (reuse the build workflow's setup; no labels). Skip if input.csv exists
    #    so a re-run resumes (Snakemake then skips already-inferred cells) -- but ONLY if that
    #    cached work list still corresponds to THIS request (D1/#66): resume-by-existence alone
    #    let a stale input.csv from a prior, different roi silently win.
    run_folderpath = os.path.join(output_folderpath, "cells")
    csv_filepath = os.path.join(run_folderpath, "input.csv")
    if scl_mask_classes is None:
        scl_mask_classes = list(config.SCL_MASK_CLASSES)
    if fs.exists(csv_filepath):
        _check_resume_identity(csv_filepath, grids, output_folderpath)
    if not fs.exists(csv_filepath):
        try:
            _create_datacube.setup(
                catalog_filepath=catalog_filepath, timestamp_col="timestamp",
                shapefilepath=grids_filepath, id_col="id", run_folderpath=run_folderpath,
                startdate=startdate, enddate=enddate, bands=bands,
                scl_mask_classes=scl_mask_classes, mosaic_days=mosaic_days,
                csv_filepath=csv_filepath, label_col=None,
            )
        except ValueError as exc:
            raise PreflightError(_imagery_missing_message(
                roi_gdf if roi_gdf is not None else roi, startdate, enddate, bands,
                catalog_filepath=catalog_filepath, why=str(exc),
            )) from exc

    # 3) fan out the per-cell build+infer task via the runner seam -- D1a (spec 38): this is
    #    the ONLY step that swaps; tiling/setup/collect (steps 1-2, 4) are runner-agnostic.
    if runner == "aml":
        # `cores`/`cubes_per_task` pass through as-is: `None` lets the AML node compute D7's
        # load-per-core default from its own core count + the shard size (`infer_shard`).
        _runners.run_aml_inference(
            csv_filepath, bundle_path, cubes_per_task=cubes_per_task, cores=cores,
            predict_batch_size=predict_batch_size, skip_nan=skip_nan, overwrite=overwrite,
            **(runner_kwargs or {}),
        )
    else:
        # local has no node to interrogate, so auto (`None`) == today's default (1).
        result = _runners.run_local_inference(
            csv_filepath, cores=(1 if cores is None else cores), bundle_path=bundle_path,
            cubes_per_task=(1 if cubes_per_task is None else cubes_per_task),
            predict_batch_size=predict_batch_size, skip_nan=skip_nan, overwrite=overwrite,
        )
        if result.returncode != 0:
            raise RuntimeError(f"inference runner failed (snakemake exit {result.returncode}).")

    # 4) collect the per-cell outputs (+ each cell's true footprint, for STAC geometry — spec 28)
    with fs.open(csv_filepath, "r") as f:
        rows = pd.read_csv(f)
    geometries = {
        os.path.join(str(exp), "output.tif"): str(sp)
        for exp, sp in zip(rows["export_folderpath"], rows["shapefilepath"])
    }
    output_filepaths = _existing_outputs(list(geometries), run_folderpath=run_folderpath)
    if not output_filepaths:
        raise RuntimeError("no per-cell outputs were produced.")

    return _finalize_outputs(
        output_filepaths, output_folderpath, spec, merge, collection_id, dt,
        grids_filepath=grids_filepath, merge_crs=merge_crs, geometries=geometries,
    )


def deploy(model_bundle, *, storage=None, **kw):
    """Register a self-describing model bundle for scaled inference. Lands in P6.

    The bundle format is pinned now (spec 18, F5): a folder with `bundle.json` (adapter
    `module:attr` ref + relative artifact hrefs + the spec) that `fsd.model.bundle.load` turns
    back into a live adapter. P6 adds *registration/push* (to ACR/blob/a registry) so cloud
    workers can fetch it; the format does not change.
    """
    raise NotImplementedError(
        "deploy lands in P6. The bundle format exists now (fsd.model.bundle.save/load); "
        "deploy adds registration/push of that bundle for scaled inference (ROADMAP §3.4)."
    )
