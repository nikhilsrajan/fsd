"""Source -> builder declaration contract (spec 34 §2a, persisted by spec 35).

`build_datacube` (fsd.datacube.builder) is a generic engine: it has no
`if source == "s2"` anywhere. Instead it reads what it needs from a
`SourceDeclaration`, attached to the flattened, band-exploded catalog it is
given as the JSON-able `GeoDataFrame.attrs["fsd:declaration"]` (`ATTRS_KEY`,
set by `flatten_catalog` and restored from the catalog Parquet's footer by
`fsd.storage.fs.read_parquet` — never the dataclass itself, spec 35 §2a), or
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
    "FSD_DECLARATION_VERSION",
    "ATTRS_KEY",
    "to_json",
    "from_json",
    "to_attrs",
    "from_attrs",
]

# Persistence (spec 35). `ATTRS_KEY` is the key under which the plain-dict JSON
# form of a `SourceDeclaration` lives inside `GeoDataFrame.attrs` (never the
# dataclass itself -- spec 35 §2a); `fsd.storage.fs` serializes that whole
# `.attrs` dict to the Parquet footer's `PANDAS_ATTRS` key.
FSD_DECLARATION_VERSION = 1
ATTRS_KEY = "fsd:declaration"

_DECLARATION_FIELDS = (
    "reference_band", "native_grid", "mask_spec", "mask_keep", "nodata",
    "mosaic_method",
)
_MASK_SPEC_FIELDS = ("band", "mask_type", "classes")

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


# --- serialization (spec 35 §2a/§3) -------------------------------------------
#
# Pure functions, no I/O. `to_json`/`from_json` convert a `SourceDeclaration` to
# and from a plain JSON-able dict (field-for-field, `fsd_declaration_version`
# required); `to_attrs`/`from_attrs` place that dict under `ATTRS_KEY` on a
# GeoDataFrame's `.attrs` -- the *typed* representation never goes in `.attrs`
# directly (a dataclass there is a future crash once a JSON-encoding writer
# touches it, see §2a).


def _mask_spec_to_json(mask_spec: MaskSpec | None) -> dict | None:
    if mask_spec is None:
        return None
    return {
        "band": mask_spec.band,
        "mask_type": mask_spec.mask_type,
        "classes": list(mask_spec.classes),
    }


def _mask_spec_from_json(raw: dict | None) -> MaskSpec | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ValueError(
            f"declaration.mask_spec must be a JSON object or null, got "
            f"{type(raw).__name__}: {raw!r}."
        )
    unknown = set(raw) - set(_MASK_SPEC_FIELDS)
    if unknown:
        raise ValueError(
            f"declaration.mask_spec has unknown field(s) {sorted(unknown)}; "
            f"known fields are {_MASK_SPEC_FIELDS}."
        )
    if "band" not in raw:
        raise ValueError("declaration.mask_spec is missing required field 'band'.")
    kwargs: dict = {"band": raw["band"]}
    if "mask_type" in raw:
        kwargs["mask_type"] = raw["mask_type"]
    if "classes" in raw:
        kwargs["classes"] = tuple(raw["classes"])
    return MaskSpec(**kwargs)


def to_json(decl: SourceDeclaration) -> dict:
    """`SourceDeclaration` -> a plain JSON-able dict, field-for-field (spec 35 §3).

    Tuples (`MaskSpec.classes`) become JSON arrays; `from_json` rehydrates them
    back into tuples, keeping the dataclass frozen/hashable.
    """
    return {
        "fsd_declaration_version": FSD_DECLARATION_VERSION,
        "reference_band": decl.reference_band,
        "native_grid": decl.native_grid,
        "mask_spec": _mask_spec_to_json(decl.mask_spec),
        "mask_keep": decl.mask_keep,
        "nodata": decl.nodata,
        "mosaic_method": decl.mosaic_method,
    }


def from_json(raw: dict) -> SourceDeclaration:
    """Inverse of `to_json`. Raises on a version newer than this fsd supports, an
    unknown field at a known version, or a `mask_spec` object missing `band`
    (spec 35 §3, the `[G4]` "fail loudly, don't half-understand" rule) -- a
    missing *optional* field takes the dataclass default (forward-compat for a
    future v2)."""
    if not isinstance(raw, dict):
        raise ValueError(
            f"declaration JSON must be a JSON object, got {type(raw).__name__}: {raw!r}."
        )
    version = raw.get("fsd_declaration_version")
    if version is None:
        raise ValueError(
            "declaration JSON is missing required field 'fsd_declaration_version'."
        )
    if version > FSD_DECLARATION_VERSION:
        raise ValueError(
            f"declaration JSON was written by a newer fsd (version {version}) than "
            f"this one supports (version {FSD_DECLARATION_VERSION}); upgrade fsd "
            "before reading this catalog."
        )
    unknown = set(raw) - {"fsd_declaration_version", *_DECLARATION_FIELDS}
    if unknown:
        raise ValueError(
            f"declaration JSON (version {version}) has unknown field(s) "
            f"{sorted(unknown)}; known fields are {_DECLARATION_FIELDS}."
        )

    kwargs: dict = {}
    if "reference_band" in raw:
        kwargs["reference_band"] = raw["reference_band"]
    if "native_grid" in raw:
        kwargs["native_grid"] = raw["native_grid"]
    if "mask_spec" in raw:
        kwargs["mask_spec"] = _mask_spec_from_json(raw["mask_spec"])
    if "mask_keep" in raw:
        kwargs["mask_keep"] = raw["mask_keep"]
    if "nodata" in raw:
        kwargs["nodata"] = raw["nodata"]
    if "mosaic_method" in raw:
        kwargs["mosaic_method"] = raw["mosaic_method"]
    return SourceDeclaration(**kwargs)


def to_attrs(gdf, decl: SourceDeclaration) -> None:
    """Stamp `decl` onto `gdf.attrs[ATTRS_KEY]` as a plain JSON-able dict (never
    the dataclass itself, spec 35 §2a). Mutates `gdf.attrs` in place."""
    gdf.attrs[ATTRS_KEY] = to_json(decl)


def from_attrs(gdf) -> SourceDeclaration | None:
    """Read the stamped declaration back off `gdf.attrs[ATTRS_KEY]`, or `None`
    if `gdf` carries no stamp."""
    raw = gdf.attrs.get(ATTRS_KEY)
    if raw is None:
        return None
    return from_json(raw)
