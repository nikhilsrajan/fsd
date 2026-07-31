# Datacubes are built in memory with the `(data, profile)` op convention

**Status:** accepted (spec 00 requirements interview; spec 03)

**Context.** The legacy datacube engine (`core/create_datacube.py`) staged intermediate GeoTIFFs to
a working directory between steps — extra disk, extra I/O, and steps that could only be composed by
writing and re-reading files.

**Decision.** The builder assembles the cube **in memory**. Every raster op takes and returns
`(data, profile)`, so ops compose as an explicit `sequence=[(func, kwargs), ...]`. `profile` carries
the rasterio transform/CRS through the chain; nodata is `0`.

**Considered options.** The **file-staging engine** (legacy). Superseded: intermediate tiffs are
slower, disk-heavy, and make each op a file boundary rather than a function.

**Consequences.** Ops are composable and unit-testable purely in memory. The user's geospatial
principles are expressed as ops in the chain — reference-image resampling (resample to a real 10 m
B08, not an abstract grid) and single-CRS merge (collapse to the max-mean-`area_contribution` zone
before `rasterio.merge`). Band math then operates on the 5-D array contract `(samples, timestamps,
height, width, bands)` with a `band_indices` map.
