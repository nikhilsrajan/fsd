"""Flatten datacubes -> stacked training arrays.

Spec: specs/05-flatten.md. Folds in datacube_flatten_2d.

Outputs (via fsd.storage): data.npy (pixels,t,b), coords.npy (pixels,2) [kept],
ids.npy, labels.npy (optional), metadata.pickle.npy. Raises if datacubes disagree
on bands/timestamps.
"""

from __future__ import annotations

import os

import numpy as np
import rasterio.transform

from fsd import config
from fsd.storage import fs

_METADATA_NAME = "metadata.pickle.npy"


def flatten(
    filepaths_df,                # one row per datacube
    filepath_col: str,
    id_col: str,
    export_folderpath: str,
    label_col: str | None = None,
    *,
    nodata: int = config.NODATA,
) -> None:
    """Stack per-geometry datacubes into model-ready per-pixel arrays.

    For each datacube `(t, H, W, b)`, keep pixels that are not entirely nodata
    across time+band -> `(pixels, t, b)`, concatenate across datacubes, and repeat
    `id` (and `label`) per pixel. All datacubes must share the same `bands` and
    `timestamps` (raises otherwise).
    """
    metadata_filepaths = [
        os.path.join(os.path.dirname(fp), _METADATA_NAME)
        for fp in filepaths_df[filepath_col]
    ]
    common_metadata = _check_metadata_consistency(metadata_filepaths)

    data_list, coords_list, id_list = [], [], []
    label_list = [] if label_col is not None else None

    for _, row in filepaths_df.iterrows():
        data_2d, coords_2d = _read_datacube_2d(row[filepath_col], nodata=nodata)
        data_list.append(data_2d)
        coords_list.append(coords_2d)

        n_pixels = data_2d.shape[0]
        id_list += [row[id_col]] * n_pixels
        if label_col is not None:
            label_list += [row[label_col]] * n_pixels

    data = np.concatenate(data_list, axis=0)         # (pixels, t, b)
    coords = np.concatenate(coords_list, axis=0)     # (pixels, 2)
    common_metadata["data_shape_desc"] = ("pixel", "timestamps", "bands")

    fs.makedirs(export_folderpath)
    fs.save_npy(os.path.join(export_folderpath, "data.npy"), data)
    fs.save_npy(os.path.join(export_folderpath, "coords.npy"), coords)
    fs.save_npy(os.path.join(export_folderpath, "ids.npy"), np.array(id_list))
    fs.save_npy(os.path.join(export_folderpath, _METADATA_NAME),
                common_metadata, allow_pickle=True)
    if label_col is not None:
        fs.save_npy(os.path.join(export_folderpath, "labels.npy"),
                    np.array(label_list))


# --- helpers -----------------------------------------------------------------

def _check_metadata_consistency(metadata_filepaths, check_attributes=("bands",
                                                                       "timestamps")):
    """All datacubes must agree on `bands` and `timestamps`; return the common ones."""
    common = {attr: None for attr in check_attributes}
    for mfp in metadata_filepaths:
        metadata = fs.load_npy(mfp, allow_pickle=True)[()]
        for attr in check_attributes:
            cur = metadata[attr]
            if common[attr] is None:
                common[attr] = cur
            elif cur != common[attr]:
                raise ValueError(f"Attribute {attr} are not consistent.")
    return common


def _read_datacube_2d(filepath: str, nodata: int = 0):
    """Load a `(t, H, W, b)` datacube, keep pixels that aren't entirely nodata across
    time+band -> `(pixels, t, b)`, and return their easting/northing coords."""
    datacube = fs.load_npy(filepath)
    nt, _, _, nb = datacube.shape  # asserts 4-D

    # pixels whose nodata count across time(0)+band(3) is below the max => keep.
    h_idx, w_idx = np.where((datacube == nodata).sum(axis=(0, 3)) < nt * nb)
    data_2d = datacube[:, h_idx, w_idx, :].swapaxes(0, 1)  # (pixels, t, b)

    metadata = fs.load_npy(os.path.join(os.path.dirname(filepath), _METADATA_NAME),
                           allow_pickle=True)[()]
    gt = metadata["geotiff_metadata"]
    en = _easting_northing_array(width=gt["width"], height=gt["height"],
                                 transform=gt["transform"])
    coords_2d = en[h_idx, w_idx, :]                        # (pixels, 2)
    return data_2d, coords_2d


def _easting_northing_array(width: int, height: int, transform):
    """Per-pixel (easting, northing) at pixel centers -> (H, W, 2)."""
    X, Y = np.meshgrid(np.arange(width), np.arange(height))
    xy_flat = np.column_stack((X.ravel(), Y.ravel()))
    eastings, northings = rasterio.transform.xy(
        transform=transform, rows=xy_flat[:, 1], cols=xy_flat[:, 0], offset="center",
    )
    en = np.array(list(zip(eastings, northings)))
    return en.reshape(*X.shape, 2)
