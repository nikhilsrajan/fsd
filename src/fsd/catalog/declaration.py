"""Source -> builder declaration contract (spec 34 §2a).

`build_datacube` (fsd.datacube.builder) is a generic engine: it has no
`if source == "s2"` anywhere. Instead it reads what it needs from a
`SourceDeclaration`, attached to the flattened, band-exploded catalog it is
given (`GeoDataFrame.attrs["declaration"]`, set by `flatten_catalog`) or
passed explicitly. A new source (ERA5/CHIRPS/S1/...) that wants a *different*
mask/reference/mosaic behavior supplies its own `SourceDeclaration` — no
change to `builder.py` is required. See `fsd/docs/adding-a-source.md`.

Per-tile/per-band values that genuinely vary row-to-row (the radiometric
`offset`, the declared `nodata`) are NOT here — they live as catalog columns
(`fsd.catalog.catalog.COLUMNS`), carried through `flatten_catalog`. This
module only holds the *collection-level* declaration: which band is the
mask/reference, how to interpret the mask, whether the source's grid needs
the S2-style multi-tile collapse.
"""

from __future__ import annotations

import dataclasses

from fsd import config

__all__ = [
    "MASK_TYPE_CATEGORICAL_CLASSES",
    "MaskSpec",
    "SourceDeclaration",
    "S2_L2A_DECLARATION",
]

# The only implemented `MaskSpec.mask_type` (spec 34 [G3]): mask wherever the
# mask band's pixel value is one of `classes` (covers S2 SCL). `bitmask`
# (Landsat/HLS QA) and `threshold` (continuous cloud-probability) are the
# named-but-unimplemented seam for a later source — see `SourceDeclaration`.
MASK_TYPE_CATEGORICAL_CLASSES = "categorical_classes"


@dataclasses.dataclass(frozen=True)
class MaskSpec:
    """Which band to read, how to interpret it, and which values mean "masked".

    `band` — the mask band's name (e.g. ``"SCL"``). `mask_type` — one of the
    growable `MASK_TYPE_*` constants; only `categorical_classes` is
    implemented (`builder.build_datacube` raises `NotImplementedError` for
    any other value — a loud, documented gap, not a silent wrong mask).
    `classes` — for `categorical_classes`, the pixel values that mean
    "masked" (e.g. S2 SCL cloud/shadow/nodata classes).
    """

    band: str
    mask_type: str = MASK_TYPE_CATEGORICAL_CLASSES
    classes: tuple[int, ...] = ()


@dataclasses.dataclass(frozen=True)
class SourceDeclaration:
    """What `build_datacube` needs to know about a source, read once per build
    instead of hardcoded (spec 34 §2a/§2b).

    `reference_band` — the band whose grid (10 m B08 for S2) every other band
    is resampled onto; `None` together with `native_grid=True` means "this
    source has one native global/regional grid, skip the multi-tile
    single-CRS collapse" — **designed-for, not implemented** (`[G2]`):
    `build_datacube` raises `NotImplementedError` when `native_grid=True`,
    because the non-tiled path needs a real non-S2 source to build+test
    against (the ERA5/CHIRPS spec).

    `mask_spec` — `None` means "no mask" (closes #35: a source with no
    cloud/QA band, e.g. CHIRPS, skips both the mask and the mask-band-drop
    op). A `MaskSpec` whose `band` is not in the build's requested `bands`
    also results in no masking (the caller opted the mask band out of this
    particular build) — this is how the S2 declaration's default mask is
    "closed" for a `bands=["B04"]` build without needing a second
    declaration.

    `mask_keep` — spec 34 §2c: default False drops the mask band after
    masking (today's behavior); True keeps it in the output cube (e.g. for a
    workflow that wants SCL/QA available downstream).

    `nodata` — the fallback nodata value when the catalog rows being built
    don't carry a `nodata` column (older/hand-built catalogs); a real
    ingested catalog carries `nodata` per row (spec 34 §1c) and that value
    wins over this default.

    `mosaic_method` — currently only "median" is implemented by
    `fsd.datacube.ops.median_mosaic`; kept as a declared field (not a magic
    string in the builder) for the next mosaic method to slot in without an
    `if source ==` branch.
    """

    reference_band: str | None = None
    native_grid: bool = False
    mask_spec: MaskSpec | None = None
    mask_keep: bool = False
    nodata: int = 0
    mosaic_method: str = "median"


# The only declaration this spec ships code for (spec 34 §3): both CDSE and
# MPC are S2 L2A, so both go through this same declaration/generic path —
# the "no hollow contract" requirement (spec-32/33 lesson).
S2_L2A_DECLARATION = SourceDeclaration(
    reference_band=config.REFERENCE_BAND,
    native_grid=False,
    mask_spec=MaskSpec(
        band="SCL",
        mask_type=MASK_TYPE_CATEGORICAL_CLASSES,
        classes=tuple(config.SCL_MASK_CLASSES),
    ),
    mask_keep=False,
    nodata=config.NODATA,
    mosaic_method="median",
)
