"""Composable band transforms over 5-D arrays.

Spec: specs/06-bands.md. Folds in rsutils.modify_bands.

Array contract: `(samples, timestamps, height, width, bands)` + a `band_indices`
dict {band_name: index}. Each op is (bands, band_indices, **kwargs) ->
(bands, band_indices) so they compose via `modify_bands`.
"""

from __future__ import annotations


def modify_bands(bands, band_indices, sequence):
    """Run a sequence of (func, kwargs) ops, threading (bands, band_indices)."""
    raise NotImplementedError


def mask_invalid_and_interpolate(bands, band_indices):
    raise NotImplementedError


def compute_bands(bands, band_indices, *, bands_to_compute):
    """Spectral indices: NDVI, NDRE, GCVI, SAVI (at minimum)."""
    raise NotImplementedError


def remove_bands(bands, band_indices, *, bands_to_remove):
    raise NotImplementedError


def scale_bands(bands, band_indices, *, bands_to_scale, std):
    raise NotImplementedError


# --- convenience: expand lower-rank arrays to the 5-D contract ----------------


def expand_datacube(datacube):
    """4-D (t,h,w,b) -> 5-D (1,t,h,w,b)."""
    raise NotImplementedError


def expand_flattened(flattened):
    """3-D (pixels,t,b) -> 5-D (pixels,t,1,1,b)."""
    raise NotImplementedError
