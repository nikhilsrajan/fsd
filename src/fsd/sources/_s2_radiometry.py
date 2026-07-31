"""S2 processing-baseline -> radiometric-offset derivation, shared by CDSE + MPC
(spec 34 §1/§3, generalizing spec 32's MPC-only version). The baseline property
name is provider-specific — MPC's S2 STAC extension uses `s2:processing_baseline`,
while CDSE's v1 catalogue uses the generic STAC Processing extension's
`processing:version` — but the value format (`"MM.mm"`) and semantics are
identical across both (spec 34 §3a Amendment A1).

ESA: reflectance = (DN + offset) / QUANTIFICATION_VALUE; offset = -1000 for
processing baseline >= 04.00 (2022-01-25), else 0 (spec 34 Best-practice
alignment, ESA S2 L2A algorithm docs).
"""

from __future__ import annotations

__all__ = ["baseline_tuple", "offset_for_item"]

_BASELINE_PROPS = (
    "s2:processing_baseline",  # MPC / legacy CDSE — S2 STAC extension
    "processing:version",      # CDSE STAC v1 — STAC Processing extension
)


def baseline_tuple(baseline: str) -> tuple[int, int]:
    """Parse an S2 baseline string ("04.00", "05.09", "02.14") into a
    comparable `(major, minor)` int tuple."""
    major, minor = baseline.split(".")
    return (int(major), int(minor))


def offset_for_item(item) -> int:
    """The additive reflectance-band offset for one STAC item (spec 34 §1/§3a
    A1, spec 32 D2/D3), keyed on **baseline**, not acquisition date
    (reprocessing can stamp a >=04.00 baseline on a pre-2022 date; the offset
    still applies). Resolves the baseline from the first of `_BASELINE_PROPS`
    present on the item — the property name differs per provider, but the
    format/semantics are identical. Raises if none is present — deterministic,
    no silent 0 (this is the correctness-critical field)."""
    baseline = None
    for prop in _BASELINE_PROPS:
        baseline = item.properties.get(prop)
        if baseline is not None:
            break
    if baseline is None:
        raise ValueError(
            f"STAC item {item.id!r} has none of {_BASELINE_PROPS!r}; "
            "cannot derive the reflectance offset (spec 34 §3a A1)."
        )
    return -1000 if baseline_tuple(baseline) >= (4, 0) else 0
