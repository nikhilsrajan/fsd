# Adding a new source to fsd

Spec: `specs/34-ingest-normalization-contract.md`. This is the "how do I add a source"
doc that spec 34 §2d requires — read it before implementing a new `fsd.sources.*`
module or wiring a new declaration into `build_datacube`. It has two halves: **ingest**
(getting bytes onto storage as a self-describing artifact) and **builder** (what
`build_datacube` reads off that artifact, and where).

There is **no `Source` ABC yet** (that formalization is TODO #11) — a source today is
just a Python module with a `query_catalog(...)` / `download(...)` pair matching the
documented CDSE/MPC contracts (`fsd/specs/01-sources.md`) plus a `SourceDeclaration`
(below). This doc seeds what #11 will eventually codify as an interface.

## The two halves of the source contract

### 1. Ingest: `stage → normalize → put`

Every source's `download(...)` does three things, in order, for each unit of work
(one tile/granule):

1. **stage** — fetch the source's native bytes (a signed HTTPS href, an S3 object, a
   netCDF file, …) to somewhere the next step can read them.
2. **normalize** — the *only* source-specific step, and the only place a new source
   needs real code:
   - **container transform** (if the native format isn't already a COG): e.g. CDSE's
     jp2→COG (`fsd.raster.cog.to_cog`), a future ERA5 netCDF→COG. Skip if the source is
     already COG (MPC).
   - **radiometry/metadata declaration**: stamp the artifact's GDAL scale/offset tag +
     nodata-if-missing (`fsd.raster.cog.stamp_gdal_tags` / `stamp_or_reencode`) — this
     is what makes the artifact *self-describing* instead of relying on ambient config.
     `stamp_or_reencode` falls back to a GDAL-COG-driver re-encode if the in-place tag
     edit breaks COG validity (a GDAL/source-dependent edge case, not the common path).
3. **put** — write the normalized artifact to `root_folderpath` (local or blob,
   `fsd.storage.fs.transfer`/`fs.put`) and append a row to the `TileCatalog` (below),
   **stamping the source's `SourceDeclaration` at that `catalog.append(...)` call**
   (spec 35 §4) — this is a **required** step, not optional: `TileCatalog.append(rows,
   declaration=YOUR_DECLARATION)`. Without it, the collection-level declaration is never
   persisted (spec 35 §1/§2), and every downstream build against that catalog raises
   (§5a) rather than silently guessing S2. See `sources/cdse.py`/`sources/mpc.py` for the
   two-line pattern (`catalog.append(rows, declaration=S2_L2A_DECLARATION)`).

**Radiometry is metadata, never baked into pixels** (spec 34 §1): the on-disk artifact
stays raw DN; a per-tile additive `offset` and the source's `nodata` value are declared
alongside it. Do not write a source that "corrects" pixel values on ingest — that is the
lossy mistake spec 34 fixed (`apply_boa_offset`'s old `clip(DN-1000, 0, 65535)` on the
*stored* bytes).

### 2. The catalog row (`fsd.catalog.catalog.TileCatalog`)

Every source's `download(...)` appends rows shaped like `fsd.catalog.catalog.COLUMNS`:

| Column | Meaning | Who sets it |
|---|---|---|
| `id` | unique tile/granule id | source |
| `satellite` | collection id | source |
| `timestamp` | acquisition time (UTC) | source |
| `s3url` | informational source href | source |
| `local_folderpath` | where the artifact(s) landed | source (`put` step) |
| `files` | comma-joined filenames in that folder | source |
| `cloud_cover` | optional QA metric | source (0 if N/A) |
| `offset` | additive radiometric offset for reflectance bands (spec 34 §1) | source; **0 for a source with no such concept** |
| `nodata` | declared nodata value | source; **defaults to 0** for the S2 convention — do not assume 0 for an arbitrary new source (spec 34 §1c, ClearSKY warning) |
| `geometry` | footprint, EPSG:4326 | source |

`offset`/`nodata` retire spec 32's bespoke `boa_add_offset` column — **there is no
back-compat shim** (spec 34 `[G4]`): `TileCatalog.read()` does not backfill a legacy
catalog missing these columns. A source that predates this schema is disposable —
re-ingest, don't migrate.

### 3. The builder contract: `SourceDeclaration` (`fsd.catalog.declaration`)

`build_datacube` (`fsd.datacube.builder`) has **no `if source == ...`** anywhere. It
reads a `SourceDeclaration` — the collection-level facts it needs — resolved as
(spec 35 §5): the explicit `declaration=` kwarg to `build_datacube`, else
`catalog_subset`'s own stamp (`attrs["fsd:declaration"]`, restored by `fs.read_parquet`
from the catalog Parquet's footer and set on the flattened output by
`flatten_catalog(catalog_gdf, declaration=...)`), else the S2 L2A default **for a
hand-built `catalog_gdf`** — a `catalog_gdf` that came from a file
(`fs.read_parquet`) and carries no stamp raises instead (spec 35 §5a): the artifact
must self-describe, not be guessed at. This is what step 3 above's required stamping
step exists for — see `specs/35-declaration-persistence.md` for the full design and
`fsd.catalog.restamp_cli` for re-stamping a catalog written before this contract.

This is the field-by-field table (spec 34 §2a) — what the builder reads, and where:

| Field | Meaning | S2 L2A default | Where it's read from |
|---|---|---|---|
| `reference_band` | the band whose grid every other band resamples onto | `"B08"` | `SourceDeclaration.reference_band` |
| `native_grid` | `True` = one native global/regional grid; skip the multi-tile CRS-collapse | `False` | `SourceDeclaration.native_grid` — **`True` raises `NotImplementedError`** today (spec 34 `[G2]`: the non-tiled build path ships with the ERA5/CHIRPS spec, not this one) |
| `mask_spec` | which band is the mask/QA band, how to interpret it, which values mean "masked" | `MaskSpec(band="SCL", mask_type="categorical_classes", classes=SCL_MASK_CLASSES)` | `SourceDeclaration.mask_spec` (`None` = no mask) |
| `mask_spec.mask_type` | how to interpret the mask band | `"categorical_classes"` | **only `"categorical_classes"` is implemented** — anything else raises `NotImplementedError` (spec 34 `[G3]`) |
| `mask_keep` | keep the mask band in the output cube instead of dropping it | `False` | `SourceDeclaration.mask_keep` |
| per-row `offset` | additive radiometric offset, applied read-time before the mosaic | S2 baseline-derived | catalog column, carried by `flatten_catalog` |
| per-row `nodata` | the missing-data sentinel | `0` | catalog column (falls back to `SourceDeclaration.nodata` if the column is absent) |
| `mosaic_method` | how images in a window are combined | `"median"` | `SourceDeclaration.mosaic_method` (only `"median"` is implemented; a declared-but-unimplemented value is a seam for a future op, not silently ignored — see `ops.py` if you add one) |

**The mask is opt-out per build, not per source**: if `mask_spec.band` is not in the
`bands` list you pass to `build_datacube`, the mask/drop ops are skipped entirely —
this is what lets a no-mask build (`bands=["B04"]`) work even against a declaration
that *has* a mask (spec 34 #35).

## Docstring DoD

Every declaration field is documented at its definition in
`fsd/catalog/declaration.py`; the op-assembly logic in `build_datacube`'s docstring
says, for each resolved value, "reads X from Y, falls back to Z." A reviewer/newcomer
should be able to populate a new source's `SourceDeclaration` and ingest path from
those docstrings + this doc, without reading spec 34 itself.

## Worked example: a CHIRPS-like source (single-band, no mask, native grid)

CHIRPS (daily precipitation, global native lat/lon grid) is the shape spec 34 designed
the contract *for*, but does not ship code for (that's a later, real spec — see
`fsd/specs/34-ingest-normalization-contract.md` §3's ERA5 row). Sketch of what it would
look like, to make the contract concrete:

```python
# fsd/sources/chirps.py  (illustrative — not implemented)

from fsd.catalog.declaration import SourceDeclaration

CHIRPS_DECLARATION = SourceDeclaration(
    reference_band=None,   # no resample reference: one native grid
    native_grid=True,       # -> build_datacube raises NotImplementedError today
    mask_spec=None,         # no mask/QA band at all
    nodata=-9999,           # CHIRPS's own declared nodata convention, NOT 0
    mosaic_method="median",
)


def download(roi, startdate, enddate, bands, root_folderpath, catalog, *, max_tiles, **kw):
    # stage: fetch a daily netCDF/GeoTIFF from the CHIRPS archive
    # normalize (container): netCDF -> COG (if not already a GeoTIFF), via a
    #   to_cog-style conversion (no jp2 involved, but the same "get a lossless COG"
    #   goal as CDSE)
    # normalize (radiometry): CHIRPS has no per-item offset -- stamp offset=0, scale=1,
    #   and nodata=-9999 if the source file doesn't already declare it
    # put: fs.transfer/fs.put to root_folderpath; catalog.append([{..., "offset": 0,
    #   "nodata": -9999, ...}], declaration=CHIRPS_DECLARATION)  # spec 35 §4 -- required
    ...
```

Calling `build_datacube(..., bands=["precip"], declaration=CHIRPS_DECLARATION)` on a
catalog flattened with this declaration would, today, raise `NotImplementedError`
immediately (`native_grid=True`) — a loud, documented "not yet" rather than a silent
mis-collapse through the S2-tiled multi-CRS machinery, which assumes tiles. The mask
side of the contract, though, is already exercised: a hypothetical single-band,
**tiled** no-mask source (drop `native_grid=True`) would build today, because #35's
mask-opt-out has real test coverage (`tests/test_datacube_builder.py`).

## Pointer to the future `Source` ABC (#11)

TODO #11 tracks formalizing this contract as a real `fsd.sources.base.Source` ABC
(`query_catalog`, `download`, a declared `SourceDeclaration` property) instead of the
current "a module that happens to match the documented signature." That work should
start from this doc's field tables — they are the interface #11 will type-check.
