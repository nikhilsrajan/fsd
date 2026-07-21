# Spec 35 — Declaration persistence (the collection declaration survives write→read)

> **Status: ✅ SIGNED OFF (2026-07-21, user) → ✅ IMPLEMENTED (2026-07-21, Sonnet@medium).** Written
> 2026-07-21 (Opus@high). **§5a locked as recommended: an unstamped catalog file RAISES**; a
> hand-built GeoDataFrame keeps the S2 default. All other decisions accepted as drafted.
> Implemented against §9's deliverable table in full, then **✅ REVIEWED + ACCEPTED (2026-07-21,
> Opus@high)** — no defects; 4 small corrections applied in place, and §7's `classification:classes`
> mirror logged as **TODO #45** (it publishes only the *masked* subset of SCL values with
> placeholder names, so "legible to any STAC-aware tool" only half-lands; a real fix needs class
> names on `MaskSpec`, i.e. a spec-34 §2a change). `pytest -q` **331 passed / 3 skipped**
> (baseline 294), `ruff check src/ tests/` clean. Closes **TODO #42** and
> is the **spec-34 amendment** that TODO #42 and spec 34's status block call for: it fixes §2a's
> "mask spec → catalog/collection metadata" row, which shipped as *in-memory only*, and makes §4's
> "roles, mask classes, nodata, offset/scale survive write→read of the catalog + STAC export"
> actually true. **Spec-first (spec 24):** this session writes the spec only; implementation is a
> later Sonnet@medium session against the signed-off spec.
>
> **Amends spec 34** §2a (the "where it lives" column for *mask spec* / *reference band* /
> *mosaic method*) and §4 (round-trip test). Does **not** reopen spec 34's Decision 1
> (radiometry/encoding) or its `[G1]`–`[G7]` resolutions; `[G2]`/`[G3]`'s
> `NotImplementedError` seams are preserved verbatim.

## Motivation

Spec 34 Decision 2 made `build_datacube` generic: no `if source == "s2"` anywhere, everything the
builder needs read from a `SourceDeclaration` "attached to the artifact". The **per-row** half of
that shipped correctly (`offset`, `nodata` are real catalog columns; asset roles are re-derived from
the band name on every STAC export). The **collection-level** half did not: `SourceDeclaration`
rides on `GeoDataFrame.attrs["declaration"]`, and neither pandas' nor geopandas' GeoParquet writer
persists `.attrs` (geopandas 1.1.4, verified 2026-07-20 and re-verified 2026-07-21 — write→read
returns `attrs == {}`). Every reader therefore falls back to `S2_L2A_DECLARATION`.

### ⚠️ This is worse than TODO #42 records — it is not latent on the production path

TODO #42 calls the gap "latent today (both shipped sources *are* S2 L2A, so the fallback is
coincidentally correct)". That is true of the *value*, but the reasoning understates *where* the
break is. There are **three** write→read hops between ingest and the builder, and the declaration
is dropped at all three:

| # | Hop | Writer | Reader | Declaration today |
|---|---|---|---|---|
| 1 | ingest catalog | `TileCatalog.append` (`catalog.py:93`) | `TileCatalog.read` (`catalog.py:105`) | **never written** — no source stamps one |
| 2 | per-cell slice | `fs.write_parquet(catalog_path, subset)` (`workflows/create_datacube.py:88`) | `fs.read_parquet` (`workflows/task.py:59`) | dropped by GeoParquet |
| 3 | builder entry | — | `flatten_catalog(subset_gdf)` (`workflows/task.py:60`) | **falls back to S2** |

Hop 2/3 is **the unit of work** — the per-cell task that Snakemake runs locally and that the Azure
Batch runner will dispatch (the whole point of the runner seam). It is a *separate process* reading
a *separate file*, so in-memory `.attrs` propagation cannot help it even in principle. So:

> **`run_task` — the one production call site of `build_datacube` — uses `S2_L2A_DECLARATION`
> unconditionally, today, no matter what the ingest declared.** The declaration-driven builder is,
> on the path that actually runs, still hardcoded to S2.

That is the exact failure spec 34 §1/§2 exists to prevent, and it does not wait for a non-S2
source to become real: it is real now and merely *invisible* because S2 is the only source. The
first ERA5/CHIRPS/S1 catalog would be silently built with an SCL mask spec, a B08 reference band,
and a median mosaic it never declared.

`.attrs` *does* propagate correctly in-memory through the read→filter→flatten chain (verified
2026-07-21: boolean mask, `.copy()`, `.intersects()` filter, column assignment, `pd.concat` all
carry it), which is why the design looked right in review. The break is purely at serialization.

## Scope

**In:** persisting `SourceDeclaration` across every catalog write→read hop; who stamps it and when;
the conflict/absence policy; an additive STAC mirror; the migration path for catalogs already on
disk.

**Out (explicitly):** any change to the declaration's *fields* or semantics (spec 34 §2a owns
those); the `[G2]` native-grid build path; the `[G3]` non-categorical `mask_type`s; the `Source`
ABC (#11) — this spec seeds it but does not build it; per-row schema (`offset`/`nodata` already
round-trip and stay columns).

---

## 1. Decision 1 — the **catalog GeoParquet file itself** is authoritative

The declaration is persisted **inside the catalog Parquet file**, in the file-level key/value
metadata (the footer), not beside it and not in a different artifact.

**Why this one:**

- **It cannot separate from the data it describes.** Every fsd movement of a catalog is a
  single-file operation — `storage.transfer(src, dst)`, the blob upload in runbook 34, the
  per-cell slice written by setup, the file a Batch task will pull. A sidecar would have to be
  found and copied by each of those independently; the first one that forgets reintroduces exactly
  the silent-S2-fallback bug this spec exists to remove.
- **It is the mechanism GeoParquet itself uses.** The `geo` metadata that makes a Parquet file a
  *Geo*Parquet file is a file-level key/value entry; adding a second key alongside it is the same
  move the format already makes, and the Parquet format defines this key/value area as
  user-definable. Verified locally: a file carrying an extra footer key is still read normally by
  stock `gpd.read_parquet` (2026-07-21).
- **It is cheap to read.** `pq.read_metadata` reads only the footer — the declaration can be
  inspected without touching a row group.

**Rejected:**

- **Sidecar JSON** (`catalog.declaration.json`) — human-readable and trivial to write, but two
  files that can separate. Rejected on the separation risk above. (Note: the *cheapness* of the
  human-readable form is recovered by §6's `fsd-catalog-inspect`, without the risk.)
- **STAC Collection as authoritative** — inverts the house convention that GeoParquet is the query
  format and STAC is an *additive interchange view* (`CLAUDE.md`; spec 17). Worse, the ingest path
  writes parquet and never writes STAC, and `items_to_rows` (the STAC→catalog direction) has no
  production caller today — it is exercised only by `tests/test_catalog_stac.py` and
  `tests/test_mpc.py`. Making the authority live in an artifact the pipeline does not produce would
  be a contract that is hollow in exactly the way spec 32/33 taught us to avoid. **STAC gets an
  additive mirror instead — §7.**
- **A registry keyed by the `satellite`/collection column** (`{"sentinel-2-l2a": S2_L2A_DECLARATION}`)
  — no serialization at all, declaration stays typed Python with real defaults. Rejected because it
  makes the artifact stop self-describing: a catalog is then unbuildable without the exact producing
  code version, and a user-added source must mutate global state at import time. Spec 34's premise
  is "the artifact self-describes; the builder reads it." (A registry may still appear later as a
  *convenience* for hand-built catalogs — it is not the persistence mechanism.)

## 2. Decision 2 — the mechanism lives in the **storage seam**, not in `TileCatalog`

`fsd.storage.fs.write_parquet` / `read_parquet` gain **generic `DataFrame.attrs` preservation**:
if `df.attrs` is non-empty, serialize it to the footer on write; restore it on read.

**Why the storage seam and not `TileCatalog`:** hop 2 in the table above is not a `TileCatalog`
write at all — setup calls `fs.write_parquet` directly with a filtered slice, and `run_task` calls
`fs.read_parquet` directly. Fixing only `TileCatalog` leaves the unit-of-work — the one that
matters for Snakemake and Batch — still broken. The house rule "**all file I/O via `fsd.storage`**"
means the seam is the single choke point through which *every* fsd parquet hop already passes, so
one fix covers all three hops and any future one for free.

**Key + encoding: `PANDAS_ATTRS`, JSON-encoded UTF-8 — deliberately the upstream convention.**
pandas already persists `.attrs` under exactly this key via the pyarrow engine (verified in this
venv: pandas 3.0.3 round-trips `attrs` through `to_parquet`; the footer carries `PANDAS_ATTRS`).
geopandas does **not** — that is geopandas issue #3320, whose fix (PR #3597) **was merged to main on
2025-10-30 using the same `PANDAS_ATTRS` key**, and is simply not in the 1.1.4 we pin. So:

> Writing our attrs under `PANDAS_ATTRS` with JSON encoding means that when geopandas ships the
> fix, upstream's writer and ours agree on key *and* format — we converge with it rather than
> ending up with two copies that can disagree. On the read side we tolerate the key being restored
> by geopandas before we look (idempotent).

**Implementation shape** (all public API; verified working 2026-07-21):

```
write: df.to_parquet(buf)                     # geopandas owns GeoParquet correctness
       -> pq.read_table(buf)                  # only when df.attrs is non-empty
       -> .replace_schema_metadata({**existing, b"PANDAS_ATTRS": json.dumps(attrs).encode()})
       -> pq.write_table(...)
read:  gpd.read_parquet(buf)                  # unchanged
       + pq.read_metadata(buf) -> attrs       # restore df.attrs
```

The double-write is **skipped entirely when `attrs` is empty**, so the no-declaration path is
byte-for-byte today's path at today's cost. With attrs present the measured overhead on a 200-row
slice is **1.15 ms → 1.97 ms** (+0.8 ms; 1000 grid cells ⇒ +0.8 s across a whole setup run).
`gdf.to_arrow()` was evaluated as a single-write alternative and **rejected**: it emits geoarrow
extension metadata and no `geo` key, so the resulting file is not readable by stock
`gpd.read_parquet` (verified — `ValueError: Missing geo metadata`).

### 2a. ⚠️ `.attrs` must hold **JSON-able plain data**, never the dataclass

Today `flatten_catalog` puts a frozen `SourceDeclaration` *object* into `attrs["declaration"]`. Once
any writer JSON-encodes attrs, a dataclass in there is a live grenade — verified in this venv:
pandas emits `UserWarning: Could not serialize pd.DataFrame.attrs: Object of type D is not JSON
serializable, defaulting to empty attributes` **and** a `TypeError` propagates. Since geopandas has
already merged the same behavior upstream, **a routine `pip install -U geopandas` would break the
write path** (or silently drop every attr) if we leave a dataclass in `attrs`.

Therefore:

- the on-`attrs` representation is a **plain JSON-able dict** under the key **`fsd:declaration`**
  (namespaced, self-describing, versioned per §3);
- the **typed** object is obtained through a helper — `declaration.from_attrs(gdf)` /
  `declaration.to_attrs(gdf, decl)` — and via `TileCatalog.declaration`;
- `builder.flatten_catalog` / `build_datacube` resolve through that helper instead of reading
  `attrs["declaration"]` directly. **`attrs["declaration"]` (the typed key) is removed** — there is
  one representation in attrs, and it is serializable.
- A test pins this (§8): everything fsd puts in `.attrs` must survive `json.dumps`.

## 3. Decision 3 — serialization schema + versioning

`fsd:declaration` is a JSON object:

```json
{
  "fsd_declaration_version": 1,
  "reference_band": "B08",
  "native_grid": false,
  "mask_spec": {"band": "SCL", "mask_type": "categorical_classes",
                "classes": [0, 1, 3, 7, 8, 9, 10]},
  "mask_keep": false,
  "nodata": 0,
  "mosaic_method": "median"
}
```

- **Field-for-field with the dataclass** — no renaming, no cleverness. `mask_spec: null` when there
  is no mask (the CHIRPS case, spec 34 `[G3]`). Tuples serialize as JSON arrays and rehydrate as
  **tuples** (the dataclass is frozen/hashable — a list would break that contract).
- **`fsd_declaration_version` is required.** A version **greater than** the running fsd's raises a
  clear error naming the writer's version — a newer fsd may have added a field whose *absence of
  meaning* would change the build (the [G4] "fail loudly, don't half-understand" rule).
- **An unknown field at a known version raises** likewise. A missing optional field takes the
  dataclass default, which is what makes v1→v2 additive later.
- Round-trip is **exact**: `to_json(from_json(x)) == x` for every field, including the empty-tuple
  and `None` cases.

## 4. Decision 4 — who stamps it, and the one-catalog-one-collection rule

- `TileCatalog.__init__` gains `declaration: SourceDeclaration | None = None`;
  `TileCatalog.append(rows, declaration=None)` stamps it (constructor value as the default).
- **`sources.cdse.download` and `sources.mpc.download` stamp `S2_L2A_DECLARATION`** at their
  existing `catalog.append(rows)` calls (`cdse.py:548`, `mpc.py:281`). This is the change that
  makes hop 1 real — today *nothing* in the ingest path declares anything.
- **Conflict = error.** Appending a declaration that differs from the one already stamped on an
  existing catalog raises `ValueError` naming both. One catalog file = one collection = one
  declaration; the row schema cannot express two anyway, and silently letting the last writer win
  would recreate this bug with extra steps. Appending with `declaration=None` to a stamped catalog
  **preserves** the existing stamp (so an fsd-agnostic top-up cannot erase it).
- `TileCatalog.filter` and `to_stac` inherit the stamp through `.attrs` (already verified to
  propagate through the filter chain).

## 5. Decision 5 — resolution order, and the unstamped-catalog policy

**Resolution order** (unchanged in spirit, one rung inserted):

1. explicit `declaration=` kwarg to `build_datacube` / `flatten_catalog`;
2. the catalog's own stamp (`fsd:declaration` in `attrs`, restored from the footer by
   `fs.read_parquet`);
3. → **the S2 default, but only under §5a.**

`scl_mask_classes` / `reference_band` keep their current override semantics (back-compat for S2
callers) — untouched.

### 5a. The loudness rule — **LOCKED 2026-07-21 (user): unstamped file ⇒ raise**, hand-built gdf ⇒ S2 default

This was the one fork left open for sign-off; it is now settled as recommended. The rule:

- **A catalog that came from a file and carries no stamp is an error at build time**, with a message
  naming the offending path and the re-stamp recipe (§6). Rationale: it is precisely the
  "coincidentally correct" fallback that hid this bug for a whole spec cycle, and it is the same
  call spec 34 `[G4]` already made for the retired `boa_add_offset` column — *no back-compat shim;
  fail loudly; re-ingest*. Here it is even cheaper than [G4] was: re-stamping is a **footer rewrite
  measured in milliseconds**, not a re-download.
- **A hand-built `GeoDataFrame` passed straight to `flatten_catalog`/`build_datacube` keeps the S2
  default**, because an explicit in-process call *is* an explicit choice, and this keeps the
  synthetic-test ergonomics (and any notebook use) intact.
- The distinction is carried mechanically: `fs.read_parquet` marks what it produced
  (`attrs["fsd:source_path"]`), so "came from a file" is a fact, not a guess.

**Blast radius is small** — `build_datacube` has exactly **one** production caller
(`workflows/task.py:62`) and one test file (`tests/test_datacube_builder.py`); `flatten_catalog`
likewise. The alternatives, **rejected at sign-off**, for the record: **(b) warn + S2 fallback** —
safer for existing runs, but a warning in a Snakemake/Batch log is a warning nobody reads, and this
bug's whole nature is being invisible; **(c) keep silent fallback** — rejected, it is the bug.

**Consequence the implementer must not soften:** the four known on-disk catalogs (§6) will raise
until re-stamped. That is intended. Do **not** add a grace period, an env-var escape, or a
"default to S2 if `satellite` looks like Sentinel-2" heuristic — the migration is a millisecond
footer rewrite, and every one of those softeners recreates the silent fallback this spec removes.

## 6. Decision 6 — migration for catalogs already on disk

Every catalog written before this spec is unstamped, including ones we care about: the Austria
`demo_e2e/imagery/catalog.parquet` (74 GB of imagery behind it), `mpc_baseline/imagery/`, the
`rise` blob catalog from runbook `34-download-to-blob`, and every per-cell slice in old run
folders. **None of them need re-downloading** — the fix is a footer rewrite.

- **`fsd-restamp-catalog <catalog.parquet> [--declaration s2_l2a]`** — reads, stamps, writes back
  through `fsd.storage` (so it works on `abfss://` too, which matters for the `rise` blob copy).
  Idempotent; refuses to overwrite a *different* existing stamp without `--force`.
- **`fsd-catalog-inspect <catalog.parquet>`** — prints the stamped declaration (footer-only read).
  This is what recovers the sidecar's one real advantage, human legibility, without its risk.
- Both go in `RECIPES.md`. The re-stamp of the four known catalogs above is a **runbook step**, not
  something Claude runs (spec 24).
- Sequencing note: TODO #44 already requires re-ingesting the `rise` blob COGs (they predate the
  `c2bf1f1` offset-tag fix). **Fold the re-stamp into that re-ingest** rather than doing it twice.

## 7. Decision 7 — the STAC export mirrors the declaration (additive, not authoritative)

`TileCatalog.to_stac` / `write_stac_catalog` write the declaration onto the **Collection**, so
spec 34 §4's "…survive write→read of the catalog **+ STAC export**" is satisfied on both artifacts.
Two layers, deliberately:

1. **Standard vocabulary where STAC has one.** The mask band's classes go on the Collection's
   `item_assets` entry using the **STAC Classification extension**'s `classification:classes` —
   which is defined for exactly this ("a cloud mask raster that stores values that represent image
   conditions in each pixel") and is explicitly allowed *as an `item-assets` field in a Collection
   object, to indicate that the classification is used across child Items*. This makes the SCL
   semantics legible to any STAC-aware tool, not just fsd. It also independently validates spec 34
   `[G3]`'s growable `mask_type`: the extension's own split is `classification:classes` vs
   `classification:bitfields`, which is the same `categorical_classes` vs `bitmask` seam.
2. **`fsd:declaration` on the Collection** for the fields STAC has no vocabulary for
   (`reference_band`, `mosaic_method`, `mask_keep`, `native_grid`) — same JSON as §3, so the two
   artifacts carry the identical object.

A `stac.collection_to_declaration(collection)` reader makes the STAC→catalog direction
(`items_to_rows`) able to restore it, closing that round trip. **The Collection is a mirror: if the
two ever disagree, the parquet footer wins** (§1), and a test pins that they are written from one
source so they *cannot* drift.

## 8. Tests (pytest — synthetic, fast, deterministic)

The existing `test_declaration_does_not_survive_catalog_roundtrip_todo_42` is **deleted and
replaced** (it pins the bug; it is designed to fail when the bug is fixed).

1. **Footer round-trip** — stamp a non-S2 declaration (reference `B04`, `MaskSpec("QA", classes=(1,2,3))`,
   `mask_keep=True`), write→read, assert the typed object is byte-identical, tuples still tuples.
2. **The three hops, end to end** — the regression test that actually matters: ingest-stamp →
   `TileCatalog.filter` → `fs.write_parquet` slice → *fresh* `fs.read_parquet` → `flatten_catalog`
   → the declaration reaching `build_datacube` is the stamped one, **not** `S2_L2A_DECLARATION`.
   Uses a deliberately non-S2 declaration so a fallback cannot pass by coincidence (the "an
   agreement test can't catch a shared error" lesson from the black-tile bug).
3. **Still valid GeoParquet** — a stamped file reads with stock `gpd.read_parquet`; the `geo` key
   survives; a stamped file written by fsd and read by fsd `read_parquet` has equal geometry/CRS.
4. **`attrs` are JSON-able** — everything fsd puts in `.attrs` survives `json.dumps`; explicitly
   asserts no dataclass leaks into attrs (§2a's future-geopandas guard).
5. **Empty-attrs path is untouched** — a gdf with no attrs produces a file with no `PANDAS_ATTRS`
   key (proves the zero-cost fast path).
6. **Unstamped file ⇒ raises** (§5a) with the path and the re-stamp recipe in the message; a
   hand-built gdf ⇒ S2 default, no raise.
7. **Conflict on append raises**; `declaration=None` append preserves the existing stamp.
8. **Version guard** — `fsd_declaration_version: 2` raises; unknown field raises; missing optional
   field takes the dataclass default.
9. **`mask_spec: null` round-trips** as `None` (the no-mask source — the case `[G3]` exists for).
10. **STAC mirror** — Collection carries `classification:classes` + `fsd:declaration`;
    `collection_to_declaration` returns the same object; catalog→STAC→catalog restores it.
11. **Re-stamp tool** — idempotent; refuses a differing stamp without `--force`; works on a
    memory-filesystem path (the fsspec/non-local proof).

No runbook is required for this spec — there is nothing credentialed, networked, or visual in it.
The *migration* (§6) is a runbook step folded into TODO #44's re-ingest.

## 9. Deliverables (for the Sonnet@medium implement session)

| # | File | Change |
|---|---|---|
| 1 | `src/fsd/storage/fs.py` | `write_parquet`/`read_parquet` attrs preservation via `PANDAS_ATTRS` (§2); `attrs["fsd:source_path"]` on read |
| 2 | `src/fsd/catalog/declaration.py` | `to_json`/`from_json` (§3), `to_attrs`/`from_attrs` (§2a), `FSD_DECLARATION_VERSION = 1`, `ATTRS_KEY = "fsd:declaration"` |
| 3 | `src/fsd/catalog/catalog.py` | `TileCatalog(declaration=...)`, `append(declaration=...)` + conflict rule (§4), `.declaration` property |
| 4 | `src/fsd/sources/cdse.py`, `sources/mpc.py` | stamp `S2_L2A_DECLARATION` at the existing `catalog.append` calls |
| 5 | `src/fsd/datacube/builder.py` | resolve via `from_attrs`; drop the typed `attrs["declaration"]`; §5a raise |
| 6 | `src/fsd/catalog/stac.py` | Collection mirror + `collection_to_declaration` (§7) |
| 7 | `src/fsd/sources/` CLI or `scripts/` | `fsd-restamp-catalog`, `fsd-catalog-inspect` (§6) |
| 8 | `tests/test_catalog.py`, `test_datacube_builder.py`, `test_catalog_stac.py`, `test_storage.py` | §8; delete the TODO-#42 pin |
| 9 | `docs/adding-a-source.md` | the §2a table's "where it lives" row is now true — document the stamp as a required ingest step |
| 10 | `TODO.md` / `CHANGES.md` / `PROGRESS.md` / `specs/34` status | close #42; note the behavior change (unstamped catalog now raises); amend 34 §2a/§4 with a pointer here |

## 10. Risks / open items

- **`pq.write_table` re-encodes the table.** Row-group layout and compression are pyarrow's
  defaults (snappy — same as geopandas'), not necessarily byte-identical to `to_parquet`'s. Harmless
  for catalogs (KB–MB, one row per granule) and verified round-trip-correct; **note it in the
  docstring** so nobody later routes a large dataframe through this path expecting zero cost.
- **geopandas upgrade.** When geopandas ships PR #3597, both it and fsd write `PANDAS_ATTRS`. Ours
  runs last and writes identical JSON, so the file is unambiguous — but the §8.4 test is what keeps
  that true. Revisit (and likely delete our writer half) when the pin moves past that release.
- **`fsd:source_path` in attrs** (§5a) is fsd-internal bookkeeping that will now be serialized into
  files written from a gdf that was read from another file. It is JSON-able and harmless, but it is
  a small provenance leak (an absolute local path could ride into a blob artifact). **Open:** strip
  it on write, or keep it as deliberate provenance? *Recommendation: strip on write* — provenance
  belongs in a designed field, not a side effect.
- **Does the per-cell `input.csv` need the declaration too?** Not for correctness (the slice
  parquet carries it), but a Batch task that is handed only a CSV row would benefit. Deferred —
  raise it with the Batch runner spec.

## Best-practice alignment / sources — per-source credit

Searched 2026-07-21 (standing permission for spec cross-validation, `CLAUDE.md`) plus **local
empirical verification in `fsd/.venv`** — geopandas 1.1.4, pandas 3.0.3, pyarrow 24.0.0 — which is
cited inline as *"verified"* wherever a claim is about *this* environment rather than a document.

- **[GeoParquet v1.1.0 specification](https://geoparquet.org/releases/v1.1.0/)** — supplied
  Decision 1's central precedent: *"A GeoParquet file MUST include a `geo` key in the Parquet
  metadata"*, i.e. the format's own collection-level metadata already lives in the file-level
  key/value area we are proposing to use; and its forward-compatibility posture — *"additional
  implementation-specific fields … MAY be present, and readers should be robust in ignoring those"*
  — which is why an extra `PANDAS_ATTRS` key is a safe, in-idiom extension rather than a hack.
- **[Apache Parquet `FileMetaData` / `key_value_metadata`](https://arrow.apache.org/rust/parquet/file/metadata/struct.FileMetaData.html)**
  (with [pandas' Parquet developer notes](https://pandas.pydata.org/docs/development/developer.html)
  and [MungingData, custom PyArrow metadata](https://www.mungingdata.com/pyarrow/arbitrary-metadata-parquet-table/))
  — established that file-level key/value metadata is **user-definable by design** and lives in the
  footer, which is what makes §1's "cheap to read without touching a row group" and §2's
  `replace_schema_metadata` route legitimate rather than incidental.
- **[pandas issue #54321 — "Allow `to_parquet` to save the metadata from `DataFrame.attrs`"](https://github.com/pandas-dev/pandas/issues/54321)**
  and **[`pandas.DataFrame.attrs` docs](https://pandas.pydata.org/docs/reference/api/pandas.DataFrame.attrs.html)**
  — gave §2 its key name and encoding: pandas settled on **`PANDAS_ATTRS` + JSON** in the pyarrow
  engine, and documents `attrs` as *experimental*. Choosing the same key is what makes fsd converge
  with upstream instead of forking a second convention. (Confirmed locally: pandas 3.0.3 round-trips
  `attrs`, footer shows `PANDAS_ATTRS`.)
- **[geopandas issue #3320 — "BUG: `to_parquet` does not seem to preserve `attrs`"](https://github.com/geopandas/geopandas/issues/3320)**
  — confirmed that the failure is a **known geopandas-specific gap**, not an fsd misuse: pandas
  preserves attrs, geopandas' own arrow writer does not. This is the root cause behind TODO #42.
- **[geopandas PR #3597](https://github.com/geopandas/geopandas/pull/3597)** — the highest-value
  find. Merged **2025-10-30**, using **`PANDAS_ATTRS`**, i.e. a future geopandas release *will*
  serialize `.attrs`. This produced two decisions that would otherwise have been missed:
  §2's key choice (converge, don't fork) and **§2a — no dataclass in `.attrs`**, because upstream
  JSON-encodes attrs and a `SourceDeclaration` object is not JSON-serializable. Verified locally
  that this path emits *"Could not serialize pd.DataFrame.attrs … defaulting to empty attributes"*
  and raises `TypeError`, i.e. a routine dependency upgrade would break fsd's write path under the
  current design.
- **[STAC Classification extension](https://github.com/stac-extensions/classification)** (via
  [pystac's classification API](https://pystac.readthedocs.io/en/latest/api/extensions/classification.html))
  — supplied §7's standard vocabulary: `classification:classes` is defined for *"a cloud mask
  raster that stores values that represent image conditions in each pixel"* and may be used *"as an
  item-assets field in a Collection object, to indicate that the classification is used across child
  Items"* — precisely fsd's collection-level SCL case. Its `classes`/`bitfields` split is also
  independent confirmation of spec 34 `[G3]`'s `categorical_classes` vs `bitmask` seam.
- **[STAC Raster extension](https://github.com/stac-extensions/raster)** — confirmed the division of
  labour this spec must not disturb: per-band `offset`/`scale`/`nodata` belong in `raster:bands` on
  the **item/asset** (where spec 34 §1 already put them), so §7's Collection mirror is correctly
  limited to the *collection-level* fields and does not duplicate per-row radiometry.
