# Spec 06 — Band math (`bands/modify.py`)

Folds in: `rsutils/modify_bands.py`.

## Responsibility

Composable transforms over a **5-D** band array
`(samples, timestamps, height, width, bands)` plus a `band_indices` dict
`{band_name: index}`. Used by data-prep (NDVI plotting), training, and deploy.

```python
def modify_bands(bands, band_indices, sequence) -> (bands, band_indices)
# sequence = [(func, kwargs), ...]
```

Helpers in the demo notebooks expand 4-D datacubes / 3-D flattened arrays to 5-D
before calling this — provide small `expand_*` conveniences so notebooks stay tiny.

## Ops to carry over
- **`mask_invalid_and_interpolate`** — mask nodata/invalid then temporally
  interpolate gaps.
- **`compute_bands(bands_to_compute)`** — spectral indices: **NDVI, NDRE, GCVI,
  SAVI** (at minimum; carry whatever legacy supports).
- **`remove_bands(bands_to_remove)`** / **`scale_bands(bands_to_scale, std)`**.

## Decisions / drops
- Carry only the ops the three demo notebooks use; list any legacy ops left behind
  in DROPPED.md (decide per-op when implementing).
- Keep the 5-D contract (don't redesign array dims) so notebook code ports 1:1.

## Tests
- NDVI/NDRE/GCVI/SAVI numeric correctness on a hand-checked tiny array.
- Interpolation fills only masked positions; band add/remove keeps `band_indices`
  consistent.
