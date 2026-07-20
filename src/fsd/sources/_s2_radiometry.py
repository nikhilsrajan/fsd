"""S2 processing-baseline -> radiometric-offset derivation, shared by CDSE + MPC
(spec 34 §1/§3, generalizing spec 32's MPC-only version — CDSE's STAC items carry
the same `s2:processing_baseline` property, per the S2 STAC extension both
providers implement, so the same derivation closes CDSE's #30/#10).

ESA: reflectance = (DN + offset) / QUANTIFICATION_VALUE; offset = -1000 for
processing baseline >= 04.00 (2022-01-25), else 0 (spec 34 Best-practice
alignment, ESA S2 L2A algorithm docs).
"""

from __future__ import annotations

__all__ = ["baseline_tuple", "offset_for_item"]


def baseline_tuple(baseline: str) -> tuple[int, int]:
    """Parse an S2 `s2:processing_baseline` string ("04.00", "05.09", "02.14")
    into a comparable `(major, minor)` int tuple."""
    major, minor = baseline.split(".")
    return (int(major), int(minor))


def offset_for_item(item) -> int:
    """The additive reflectance-band offset for one STAC item (spec 34 §1, spec
    32 D2/D3), keyed on **baseline**, not acquisition date (reprocessing can
    stamp a >=04.00 baseline on a pre-2022 date; the offset still applies).
    Raises if `s2:processing_baseline` is missing — deterministic, no silent 0
    (this is the correctness-critical field)."""
    baseline = item.properties.get("s2:processing_baseline")
    if baseline is None:
        raise ValueError(
            f"STAC item {item.id!r} has no 's2:processing_baseline' property; "
            "cannot derive the reflectance offset (spec 34 §1)."
        )
    return -1000 if baseline_tuple(baseline) >= (4, 0) else 0
