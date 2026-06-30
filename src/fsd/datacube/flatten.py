"""Flatten datacubes -> stacked training arrays.

Spec: specs/05-flatten.md. Folds in datacube_flatten_2d.

Outputs (via fsd.storage): data.npy (pixels,t,b), coords.npy (pixels,2) [kept],
ids.npy, labels.npy (optional), metadata.pickle.npy. Raises if datacubes disagree
on bands/timestamps.
"""

from __future__ import annotations

from fsd import config


def flatten(
    filepaths_df,                # one row per datacube
    filepath_col: str,
    id_col: str,
    export_folderpath: str,
    label_col: str | None = None,
    *,
    nodata: int = config.NODATA,
) -> None:
    raise NotImplementedError
