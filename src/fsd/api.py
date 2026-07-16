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
from fsd.workflows import create_datacube as _create_datacube

__all__ = [
    "PreflightError",
    "TrainingData",
    "InferenceResult",
    "download",
    "create_training_data",
    "run_inference",
    "deploy",
    "compute_n_timestamps",
]


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


def _check_local_seams(runner: str, storage) -> list[str]:
    """P0 wires only local execution/storage; anything else is a clear, early error."""
    errs = []
    if runner != "local":
        errs.append(f"runner={runner!r} not supported in P0 (only 'local'; Batch lands in P2).")
    if storage is not None:
        errs.append("non-local storage not supported in P0 (local only; blob lands in P1).")
    return errs


def _as_gdf(label_polygons) -> gpd.GeoDataFrame:
    if isinstance(label_polygons, gpd.GeoDataFrame):
        return label_polygons
    return gpd.read_file(label_polygons)


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
) -> str:
    """Fetch S2 L2A tiles for the ROI/date range into `dst_folderpath`, build/append its
    TileCatalog, and return the catalog filepath (feed it to `create_training_data`).

    `source` (spec 32): `"cdse"` (default) wraps `sources.cdse.download` and requires
    `creds`; `"mpc"` wraps `sources.mpc.download` (Microsoft Planetary Computer,
    anonymous by default — `creds` is not required and `cog` is ignored, MPC assets
    are already COG). Preflighted. `storage` is a seam (local only in P0). See specs/16.
    """
    errs = _check_local_seams("local", storage) + _check_window(startdate, enddate, 20, bands)
    if source not in ("cdse", "mpc"):
        errs.append(f"source={source!r} must be one of 'cdse', 'mpc'.")
    if max_tiles < 1:
        errs.append(f"max_tiles ({max_tiles}) must be >= 1.")
    if source == "cdse" and creds is None:
        errs.append("creds (CdseCredentials) required for source='cdse'.")
    _raise_preflight(errs)

    fs.makedirs(dst_folderpath)
    catalog_filepath = os.path.join(dst_folderpath, "catalog.parquet")
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


def create_training_data(
    label_polygons,
    catalog_filepath: str,
    startdate: datetime.datetime,
    enddate: datetime.datetime,
    mosaic_days: int,
    bands: list[str],
    id_col: str,
    label_col: str,
    export_folderpath: str,
    *,
    scl_mask_classes: list[int] = config.SCL_MASK_CLASSES,
    adapter=None,
    feature_sequence=None,
    aggregate=None,
    cores: int = 1,
    runner: str = "local",
    storage=None,
    run_folderpath: str | None = None,
) -> TrainingData:
    """Turn known-label polygons + a downloaded catalog into flattened training arrays.

    Orchestrates `workflows.create_datacube` (one datacube per polygon, calendar mosaic) then
    `datacube.flatten` — the user never types "flatten". Returns a `TrainingData` handle.

    Feature engineering (P0.5, spec 18): pass an `adapter` (preferred — its `feature_sequence`
    is the *same* one used at inference, the F1 anti-skew guarantee) **or** a raw
    `feature_sequence` (adapter-less/exploratory). `aggregate` ∈ {None, "median_per_id",
    callable} reduces per-pixel samples before the transform. When any is given, fsd writes
    `features.npy` (+ `feature_ids`/`feature_labels`) additively; the raw `data.npy` is kept.
    `runner`/`storage` are local-only in P0.
    """
    if adapter is not None and feature_sequence is not None:
        raise PreflightError(
            "pass either `adapter` or `feature_sequence`, not both (ambiguous feature transform)."
        )

    errs = _check_local_seams(runner, storage) + _check_window(
        startdate, enddate, mosaic_days, bands
    )
    if adapter is not None:
        req = list(getattr(adapter, "required_bands", []) or [])
        missing = [b for b in req if b not in bands]
        if missing:
            errs.append(f"adapter.required_bands not in requested bands: {missing}")
        want_t = int(getattr(adapter, "n_timestamps", 0) or 0)
        if want_t:
            got_t = compute_n_timestamps(startdate, enddate, mosaic_days)
            if got_t != want_t:
                errs.append(
                    f"dates/mosaic_days give T={got_t} but adapter.n_timestamps={want_t}."
                )
    try:
        _resolve_aggregate(aggregate)
    except ValueError as exc:
        errs.append(str(exc))
    catalog_present = fs.exists(catalog_filepath)
    if not catalog_present:
        errs.append(
            f"catalog_filepath does not exist: {catalog_filepath} "
            "— run fsd.download first (compute never fetches from CDSE; spec 23 D13)."
        )
    gdf = None
    try:
        gdf = _as_gdf(label_polygons)
        for col in (id_col, label_col):
            if col not in gdf.columns:
                errs.append(f"column {col!r} not in label_polygons.")
        if len(gdf) == 0:
            errs.append("label_polygons is empty.")
        elif gdf.geometry.isna().any():
            errs.append("label_polygons has null geometries.")
    except Exception as exc:  # unreadable polygons is a preflight failure, not a crash
        errs.append(f"could not read label_polygons: {exc}")
    # D13 guardrail: catalog exists but covers NONE of the fields in-window -> actionable download
    # plan (the offline .filter is cheap; the STAC-backed plan only fires on the empty case).
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

    if run_folderpath is None:
        run_folderpath = os.path.join(export_folderpath, "run")
    fs.makedirs(run_folderpath)
    fs.makedirs(export_folderpath)

    # The workflow reads a path; materialize an in-memory GeoDataFrame to a temp GeoJSON.
    if isinstance(label_polygons, gpd.GeoDataFrame):
        shapefilepath = os.path.join(run_folderpath, "label_polygons.geojson")
        gdf.to_file(shapefilepath, driver="GeoJSON")
    else:
        shapefilepath = label_polygons

    csv_filepath = os.path.join(run_folderpath, "input.csv")
    _create_datacube.run_create_datacube(
        catalog_filepath=catalog_filepath, timestamp_col="timestamp",
        shapefilepath=shapefilepath, id_col=id_col, run_folderpath=run_folderpath,
        startdate=startdate, enddate=enddate, bands=bands,
        scl_mask_classes=scl_mask_classes, mosaic_days=mosaic_days,
        csv_filepath=csv_filepath, label_col=label_col, cores=cores, runner=runner,
    )

    with fs.open(csv_filepath, "r") as f:
        input_df = pd.read_csv(f)
    _flatten.flatten(
        filepaths_df=input_df, filepath_col="datacube_filepath",
        id_col="id", label_col="label", export_folderpath=export_folderpath,
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
        export_folderpath=export_folderpath, run_folderpath=run_folderpath,
        n_pixels=int(data.shape[0]), n_timestamps=len(metadata["timestamps"]),
        bands=list(metadata["bands"]), feature_bands=feature_bands,
    )


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
    import rasterio
    from rasterio.merge import merge as rio_merge

    if reproject_to_dominant:
        from rasterio.crs import CRS as _RioCRS
        from rasterio.warp import Resampling, calculate_default_transform
        from rasterio.warp import reproject as rio_reproject

        area_by_crs: dict[str, float] = {}
        for fp in filepaths:
            with rasterio.open(fp) as s:
                key = s.crs.to_string()
                # extent area in the cell's own (metric UTM) CRS — comparable across UTM zones
                area_by_crs[key] = area_by_crs.get(key, 0.0) + (
                    abs(s.transform.a * s.transform.e) * s.width * s.height
                )
        if merge_crs is not None:
            target = _RioCRS.from_user_input(merge_crs).to_string()   # user-forced target CRS
        elif any(area_by_crs.values()):
            target = max(area_by_crs, key=area_by_crs.get)            # dominant zone = max total area
        else:
            target = max(area_by_crs, key=lambda k: len(k))          # degenerate fallback

        datasets, tmps = [], []
        try:
            for fp in filepaths:
                src = rasterio.open(fp)
                if src.crs.to_string() == target:
                    datasets.append(src)
                    continue
                transform, w, h = calculate_default_transform(
                    src.crs, target, src.width, src.height, *src.bounds)
                prof = src.profile.copy()
                prof.update(driver="GTiff", crs=target, transform=transform,
                            width=w, height=h, nodata=nodata)
                tmp = f"{fp}.reproj.tif"
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
                datasets.append(rasterio.open(tmp))
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
        srcs = [rasterio.open(fp) for fp in filepaths]
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

    raw = f"{dst}.raw.tif"
    try:
        with rasterio.open(raw, "w", **profile) as d:
            d.write(mosaic)
        _to_cog(raw, dst)
    finally:
        if os.path.exists(raw):
            os.remove(raw)
    return dst


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
    cores: int = 1,
    cubes_per_task: int = 1,
    overwrite: bool = False,
    runner: str = "local",
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
    - **ROI** (spec 21, P0.75 — completes Mode A): pass ``roi`` (+ ``catalog_filepath``,
      ``startdate``/``enddate``/``mosaic_days``/``bands``). fsd tiles the ROI into S2 grid cells
      (``fsd.grid``), then fans out a per-cell **build-datacube + infer -> COG** task through the
      **runner seam** (Snakemake locally; Batch swaps in at P4 unchanged). Imagery is assumed
      already present in ``catalog_filepath`` — inference never touches CDSE (conserve quota).

    `model` is a live `ModelAdapter` or a **bundle path**; a bundle is required for ROI mode and for
    ``cores>1`` (both cross a subprocess) — a live adapter is auto-saved to a temp bundle. Preflight
    (before any build) asserts bands ⊇ ``required_bands`` and ``T == n_timestamps``. Inference is
    **idempotent**: existing outputs are skipped unless ``overwrite=True`` (spec 22). ``merge``:
    ``False`` | ``True`` (strict single-CRS) | ``"reproject"`` (cross-UTM-zone-safe merge to one
    CRS — ``merge_crs`` if given, else the max-total-area zone; lossless where a cell already
    matches the target). `runner`/`storage` are local-only here.
    """
    errs = _check_local_seams(runner, storage)
    if output_folderpath is None:
        errs.append("output_folderpath is required.")
    if merge not in (False, True, "reproject"):
        errs.append(f'merge must be False, True, or "reproject" (got {merge!r}).')

    roi_mode = roi is not None
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
            merge_crs=merge_crs, cores=cores, overwrite=overwrite,
            collection_id=collection_id, dt=dt,
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
    if cores > 1:
        # cores>1 fans out via the Snakemake infer-only runner (spec 22 — no in-process pool)
        output_filepaths = _run_prebuilt_via_runner(
            model, pairs, output_folderpath, cores=cores, cubes_per_task=cubes_per_task,
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
    except Exception as exc:  # noqa: BLE001 - surfaced as a preflight error
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
    predict_batch_size, skip_nan, merge, merge_crs, cores, overwrite, collection_id, dt,
) -> InferenceResult:
    """ROI mode (spec 21): preflight -> tile -> per-cell setup -> runner build+infer -> STAC/merge."""
    from fsd import grid as _grid
    from fsd.workflows import runners as _runners

    # --- preflight (cheap, before any build) ---
    for name, val in [("catalog_filepath", catalog_filepath), ("startdate", startdate),
                      ("enddate", enddate), ("mosaic_days", mosaic_days), ("bands", bands)]:
        if val is None:
            errs.append(f"roi mode requires {name}=.")
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
            roi_gdf = gpd.read_file(roi)
    except Exception as exc:  # noqa: BLE001 - surfaced as a preflight error
        errs.append(f"could not read roi: {exc}.")
    if roi_gdf is not None and len(roi_gdf) == 0:
        errs.append("roi is empty.")
    _raise_preflight(errs)

    fs.makedirs(output_folderpath)

    # model must be a bundle (it crosses a subprocess); auto-save a live adapter.
    bundle_path = _ensure_bundle(model, output_folderpath, why="roi mode")

    # 1) tile the ROI -> S2 grid cells (needs the [grid] extra; clean error if absent)
    grids = _grid.roi_to_s2_grids(
        roi_gdf if roi_gdf is not None else roi,
        grid_size_km=grid_size_km, scale_fact=scale_fact,
    )
    grids_filepath = os.path.join(output_folderpath, "grids.geojson")
    grids.to_file(grids_filepath, driver="GeoJSON")

    # 2) per-cell setup (reuse the build workflow's setup; no labels). Skip if input.csv exists
    #    so a re-run resumes (Snakemake then skips already-inferred cells).
    run_folderpath = os.path.join(output_folderpath, "cells")
    csv_filepath = os.path.join(run_folderpath, "input.csv")
    if scl_mask_classes is None:
        scl_mask_classes = list(config.SCL_MASK_CLASSES)
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

    # 3) fan out the per-cell build+infer task via the runner seam
    result = _runners.run_local_inference(
        csv_filepath, cores=cores, bundle_path=bundle_path,
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
    output_filepaths = [cog for cog in geometries if fs.exists(cog)]
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
