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
import pandas as pd

from fsd import config
from fsd.catalog.catalog import TileCatalog
from fsd.datacube import flatten as _flatten
from fsd.sources.cdse import CdseCredentials
from fsd.sources.cdse import download as _cdse_download
from fsd.storage import fs
from fsd.workflows import create_datacube as _create_datacube

__all__ = [
    "PreflightError",
    "TrainingData",
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

    def load(self) -> dict:
        """Load the arrays into memory: data/ids/coords/metadata (+ labels if present)."""
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
        return out


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

    `feature_sequence`/`aggregate` are pinned in the signature (stable API) but land in P0.5
    (ModelAdapter); passing a non-None value raises. `runner`/`storage` are local-only in P0.
    """
    if feature_sequence is not None:
        raise NotImplementedError("feature_sequence lands in P0.5 (ModelAdapter); leave it None.")
    if aggregate is not None:
        raise NotImplementedError("aggregate lands in P0.5 (ModelAdapter); leave it None.")

    errs = _check_local_seams(runner, storage) + _check_window(
        startdate, enddate, mosaic_days, bands
    )
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
    return TrainingData(
        export_folderpath=export_folderpath, run_folderpath=run_folderpath,
        n_pixels=int(data.shape[0]), n_timestamps=len(metadata["timestamps"]),
        bands=list(metadata["bands"]),
    )


def run_inference(roi, startdate, enddate, mosaic_days, model_bundle,
                  *, runner="local", storage=None, **kw):
    """Run a model over an ROI at scale -> COG + STAC. Lands in P4."""
    raise NotImplementedError(
        "run_inference lands in P4. Contract: ROI -> S2-grid tiles (ROADMAP §4, port "
        "s2_grid_utils) -> per-grid inference datacubes -> model_bundle (ModelAdapter, P0.5) "
        "-> COG + STAC (spec 17). Preflight will assert T == model.n_timestamps and bands."
    )


def deploy(model_bundle, *, storage=None, **kw):
    """Register a self-describing model bundle for scaled inference. Lands in P6."""
    raise NotImplementedError(
        "deploy lands in P6. Contract: register a self-describing model bundle "
        "(adapter code + artifact + spec) for scaled inference (ROADMAP §3.4)."
    )
