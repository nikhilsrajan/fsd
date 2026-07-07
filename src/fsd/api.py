"""fsd high-level API — the verbs users call.

Spec: specs/16-packaging-and-api.md (P0). A thin façade over the internal modules
(`sources`, `catalog`, `datacube`, `workflows`, `flatten`) that raises the scope from
implementation vocabulary ("flatten", "input.csv") to user intent ("make training data").
Adds no pipeline logic.

- `download(...)`            -> fetch S2 L2A tiles + build a TileCatalog (its own verb).
- `create_training_data(...)`-> label polygons + catalog -> datacubes -> flattened arrays.
- `run_inference(...)`       -> stub (P4): ROI -> S2 tiles -> model -> COG + STAC.
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


# --- verbs -------------------------------------------------------------------

def download(
    roi,
    startdate: datetime.datetime,
    enddate: datetime.datetime,
    bands: list[str],
    dst_folderpath: str,
    creds: CdseCredentials,
    *,
    max_tiles: int,
    max_cloudcover: float | None = None,
    cog: bool = True,
    progress: bool = True,
    storage=None,
) -> str:
    """Fetch S2 L2A tiles for the ROI/date range into `dst_folderpath`, build/append its
    TileCatalog, and return the catalog filepath (feed it to `create_training_data`).

    Thin wrapper over `sources.cdse.download`. Preflighted. `storage` is a seam (local only
    in P0). See specs/16.
    """
    errs = _check_local_seams("local", storage) + _check_window(startdate, enddate, 20, bands)
    if max_tiles < 1:
        errs.append(f"max_tiles ({max_tiles}) must be >= 1.")
    if creds is None:
        errs.append("creds (CdseCredentials) required for download.")
    _raise_preflight(errs)

    fs.makedirs(dst_folderpath)
    catalog_filepath = os.path.join(dst_folderpath, "catalog.parquet")
    catalog = TileCatalog(catalog_filepath)
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
    if not fs.exists(catalog_filepath):
        errs.append(f"catalog_filepath does not exist: {catalog_filepath}")
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


def _resolve_inference_pairs(inference_datacubes, output_folderpath) -> list[tuple[str, str]]:
    """-> [(datacube_filepath, output_filepath)]. Accepts an input.csv, a folder of datacube
    subfolders, or an explicit list of `datacube.npy` filepaths."""
    ids = None
    if isinstance(inference_datacubes, (list, tuple)):
        dc_filepaths = [str(p) for p in inference_datacubes]
    elif isinstance(inference_datacubes, str) and inference_datacubes.endswith(".csv"):
        with fs.open(inference_datacubes, "r") as f:
            df = pd.read_csv(f)
        col = "datacube_filepath" if "datacube_filepath" in df.columns else df.columns[0]
        dc_filepaths = [str(p) for p in df[col]]
        if "id" in df.columns:
            ids = [str(i) for i in df["id"]]
    else:  # a folder: each subfolder holds a datacube.npy
        dc_filepaths = sorted(fs.glob(os.path.join(str(inference_datacubes), "*", "datacube.npy")))

    pairs = []
    for i, dc in enumerate(dc_filepaths):
        stem = ids[i] if ids is not None else os.path.basename(os.path.dirname(dc))
        pairs.append((dc, os.path.join(str(output_folderpath), stem, "output.tif")))
    return pairs


def _merge_outputs(filepaths, dst, nodata) -> str:
    """Merge single-CRS output COGs into one COG (the legacy merged map). Multi-CRS raises —
    the per-tile COGs + STAC are the multi-zone answer (fsd single-CRS-merge principle)."""
    import rasterio
    from rasterio.merge import merge as rio_merge

    srcs = [rasterio.open(fp) for fp in filepaths]
    try:
        crs_set = {s.crs.to_string() for s in srcs}
        if len(crs_set) > 1:
            raise PreflightError(
                f"cannot merge outputs across multiple CRS {sorted(crs_set)}; use the per-tile "
                "COGs + STAC catalog instead (collapse to one zone first for a merged map)."
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


def run_inference(
    model,
    inference_datacubes,
    output_folderpath: str,
    *,
    predict_batch_size: int | None = None,
    skip_nan: bool = True,
    merge: bool = False,
    cores: int = 1,
    runner: str = "local",
    storage=None,
    collection_id: str = "fsd-inference",
    dt=None,
    progress: bool = True,
) -> InferenceResult:
    """Run a model over **pre-built inference datacubes** -> one COG per cube + a STAC catalog.

    P0.5 (spec 18): the local inference engine (Mode A deploy). `model` is a live `ModelAdapter`
    or a **bundle path**. `inference_datacubes` is an `input.csv`, a folder of datacube
    subfolders, or a list of `datacube.npy` filepaths. Preflight asserts every datacube's bands
    ⊇ `required_bands` and `len(timestamps) == n_timestamps` **before any predict**. The
    ROI→S2-tiling→download front-end that *builds* the datacubes lands in P4 and calls this same
    engine; `runner`/`storage` are local-only here.
    """
    errs = _check_local_seams(runner, storage)
    spec = _model_spec(model)
    required = set(spec.get("required_bands") or [])
    want_t = int(spec.get("n_timestamps") or 0)

    pairs = _resolve_inference_pairs(inference_datacubes, output_folderpath)
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
    output_filepaths = _engine.run_local(
        model, pairs, cores=cores,
        predict_batch_size=predict_batch_size, skip_nan=skip_nan, progress=progress,
    )

    items = _stac.cog_outputs_to_items(
        output_filepaths, collection_id=collection_id,
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
        )

    return InferenceResult(
        output_folderpath=output_folderpath, output_filepaths=sorted(output_filepaths),
        stac_catalog_filepath=stac_catalog_filepath, merged_filepath=merged_filepath,
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
