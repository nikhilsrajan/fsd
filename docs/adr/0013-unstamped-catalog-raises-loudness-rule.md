# A file-backed catalog with no radiometry stamp raises; only an in-process gdf gets the S2 default

**Status:** accepted (spec 35, §5a "the loudness rule" — LOCKED 2026-07-21)

**Context.** With the builder now reading declared radiometry (ADR 0011/0012), the question is what
to do when the declaration is *missing*. A silent "assume S2 defaults" fallback is precisely the
"coincidentally correct" behaviour that hid a radiometry bug for a whole spec cycle.

**Decision.** A **catalog read from a file that carries no stamp is a build-time error**, with a
message naming the offending path and the re-stamp recipe. A **hand-built `GeoDataFrame` passed
in-process** (to `flatten_catalog`/`build_datacube`) **keeps the S2 default**, because an explicit
in-process call *is* an explicit choice (and it keeps synthetic-test and notebook ergonomics intact).
The distinction is carried mechanically: `fs.read_parquet` stamps `attrs["fsd:source_path"]`, so
"came from a file" is a fact, not a guess.

**Considered options.** **Warn + S2 fallback** — rejected: a warning in a Snakemake/Batch log is a
warning nobody reads, and this bug's whole nature is being invisible. **Keep the silent fallback** —
rejected: it *is* the bug. (Same call spec 34 `[G4]` made for the retired `boa_add_offset` column:
no back-compat shim, fail loudly, re-ingest.)

**Consequences.** The four known on-disk catalogs raise until re-stamped — **intended**, and cheap (a
footer rewrite measured in milliseconds, not a re-download). No grace period, no env-var escape hatch,
no silent fallback is to be added back.
