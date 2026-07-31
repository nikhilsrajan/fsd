# On-disk datacube format = `datacube.npy` + `metadata.pickle.npy`

**Status:** accepted (spec 03)

**Context.** A persisted cube needs its raw array **and** the rasterio transform/CRS + band metadata
that make the array geospatially meaningful. Persisting the metadata as a raw `pickle` file was
observed to corrupt across platforms.

**Decision.** Persist the array as **`datacube.npy`** and the metadata as
**`metadata.pickle.npy`** — a `np.save` of a pickled metadata dict. Pickle is kept deliberately
because the metadata carries live rasterio objects (transform/CRS) that JSON cannot represent; the
`np.save` wrapper is what avoids the cross-platform raw-pickle corruption. Nodata = 0.

**Considered options.** **Raw `pickle`** — rejected: cross-platform corruption. **JSON/text
sidecar** — rejected: cannot round-trip rasterio transform/CRS objects without a bespoke
(de)serializer.

**Consequences.** Cube artifacts are portable across the laptop ↔ cluster boundary. The pickle is a
conscious, contained exception to a general "avoid pickle" instinct, justified by the rasterio
payload and quarantined behind `np.save`.
