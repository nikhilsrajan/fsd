"""Datacube ops — pure transforms over (t, H, W, bands) + metadata.

Spec: specs/04-datacube-ops.md. Folds in the L2A-relevant subset of
core/datacube_ops.py. Each op: (datacube, metadata, **kwargs) -> (datacube, metadata).

Dropped vs legacy: run_s2cloudless / CMK-based apply_cloud_mask (L1C-only).
"""

from __future__ import annotations

import datetime


def run_ops(datacube, metadata, sequence):
    """Run a sequence of (func, kwargs) ops, threading (datacube, metadata)."""
    raise NotImplementedError


def apply_cloud_mask_scl(datacube, metadata, *, mask_classes, bands_to_modify=None,
                         mask_value=0):
    raise NotImplementedError


def drop_bands(datacube, metadata, *, bands_to_drop):
    raise NotImplementedError


def median_mosaic(datacube, metadata, *, startdate: datetime.datetime,
                  enddate: datetime.datetime, mosaic_days=20, mask_value=0):
    """Bucket timestamps into mosaic_days windows; per-bucket nanmedian.

    Numba-accelerated core (carry the @njit kernel from legacy).
    """
    raise NotImplementedError


def area_median(datacube, metadata=None, *, mask_value=0):
    """Collapse H x W to a single median pixel per timestamp (deploy helper)."""
    raise NotImplementedError
