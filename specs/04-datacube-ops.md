# Spec 04 — Datacube ops

Folds in: `core/datacube_ops.py` (L2A-relevant subset only).

## Responsibility

Pure array transforms over a 4-D datacube `(t, H, W, bands)` + its metadata dict.
Each op has signature `(datacube, metadata, **kwargs) -> (datacube, metadata)` so
they compose via a small runner.

```python
def run_ops(datacube, metadata, sequence) -> (datacube, metadata)
# sequence = [(func, kwargs), ...]
```

## Ops to carry over (S2 L2A)

- **`apply_cloud_mask_scl(mask_classes, mask_value=0)`** — set pixels to
  `mask_value` where SCL ∈ `mask_classes`, across all non-SCL bands.
- **`drop_bands(bands_to_drop)`** — slice out bands, update `metadata['bands']`.
- **`median_mosaic(startdate, enddate, mosaic_days, mask_value=0)`** — bucket
  timestamps into `mosaic_days` windows from `startdate`; per bucket take
  `nanmedian` (treating `mask_value` as NaN); writes `mosaic_index_intervals`,
  `previous_timestamps`, new `timestamps`. **Numba**-accelerated core (carry the
  `@njit` median kernel).
  > **Anchor caveat (preserve legacy for now, flagged):** the `startdate` threaded
  > in is the **actual first-acquisition date** of the filtered tiles (setup's
  > `actual_startdate` = min catalog timestamp), *not* the user-input startdate.
  > So the 20-day windows shift from ROI to ROI depending on when the first usable
  > tile landed. The user notes this is probably undesirable — anchoring at the
  > user-input `startdate`/`enddate` would be consistent across ROIs. Keep
  > legacy behavior in v1; revisit per TODO.md #2.
- (keep, used by deploy notebooks) **`area_median`** — collapse H×W to a single
  median pixel per timestamp.

## Drops vs legacy
- **`run_s2cloudless` / `apply_cloud_mask` (CMK-based)** — L1C-only; dropped with
  the s2cloudless dependency. Record in DROPPED.md.

## Dependencies
- `numba` (median mosaic kernel). Keep the pin compatible with Python 3.11.

## Tests
- SCL mask zeroes the right pixels only; SCL band untouched until dropped.
- `median_mosaic` bucket boundaries inclusive/exclusive match legacy; NaN handling
  restores `mask_value`; output timestamp count == #non-empty buckets.
