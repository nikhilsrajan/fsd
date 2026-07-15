# Spec 05 — Flatten datacubes → training arrays

Folds in: `datacube/datacube_flatten_2d.py`.

## Responsibility

Turn a set of per-geometry datacubes into stacked, model-ready 2-D-per-pixel
arrays for training.

```python
def flatten(
    filepaths_df: pd.DataFrame,   # one row per datacube
    filepath_col: str,            # path to datacube.npy
    id_col: str,
    export_folderpath: str,
    label_col: str | None = None,
) -> None   # writes data.npy, ids.npy, [labels.npy], coords.npy(?), metadata.pickle.npy
```

## Behavior to preserve
- For each datacube `(t,H,W,b)`: keep pixels that are **not entirely nodata**
  across time+band → `(pixels, t, b)`.
- Concatenate across datacubes; `ids` (and `labels`) repeated per pixel.
- **Consistency check**: all datacubes must share the same `bands` and
  `timestamps` (raise otherwise). Carry common metadata; set
  `data_shape_desc = ('pixel','timestamps','bands')`.
- Outputs: `data.npy (pixels,t,b)`, `coords.npy (pixels,2)`, `ids.npy`,
  `labels.npy` (if `label_col`), `metadata.pickle.npy`. Written via `fsd.storage`.

## coords.npy (kept)
- `coords.npy` (per-pixel `(lon, lat)` in **EPSG:4326**) is **kept** — cheap and useful
  for mapping predictions back to geography. Emit it alongside `data.npy`. Per-pixel
  easting/northing is read from the geotransform, then **reprojected from each cube's
  native CRS to EPSG:4326** before concatenation (TODO #16, done) so a training set
  spanning multiple UTM zones shares one common CRS instead of mixing incomparable
  eastings/northings.

## Drops vs legacy
- `PLANET_NODATA` naming / Planet assumptions — generalize to a `nodata` param
  (default 0).

## Tests
- Two small datacubes → correct stacked shapes, id/label repetition, nodata-pixel
  exclusion.
- Mismatched bands/timestamps → raises.
