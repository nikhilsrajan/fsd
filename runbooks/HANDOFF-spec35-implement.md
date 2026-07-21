# Handoff — implement spec 35 (declaration persistence, TODO #42)

**For:** a fresh **Sonnet@medium** session (`/model sonnet`, `/effort medium`). This is
spec-following implementation against a **signed-off** spec — every design fork is closed, including
the last one (§5a) at sign-off. **Do not re-open a decision; if the spec seems wrong, stop and say
so rather than improvising.**

**Parent session:** Opus@high, wrote spec 35 and this baton. Nothing is in flight elsewhere — you
own the whole tree.

## One-line goal

Make the collection-level `SourceDeclaration` survive every catalog write→read hop, so
`workflows/task.py` builds with the declaration the ingest actually stamped instead of silently
falling back to `S2_L2A_DECLARATION`.

## Read first (in this order)

1. **`specs/35-declaration-persistence.md`** — THE spec. §9 is a deliverable table; work it
   top-to-bottom. §8 is the test list. Implement to it; do not re-derive the design.
2. Its **§2a** (no dataclass in `.attrs`) and **§5a** (unstamped ⇒ raise) — the two places where a
   reasonable-looking shortcut is explicitly wrong.
3. `src/fsd/catalog/declaration.py` — the dataclasses you are serializing. They are `frozen=True`;
   keep them that way (tuples must rehydrate as **tuples**, not lists).
4. `RECIPES.md` → *"Probe: does a GeoDataFrame's `.attrs` survive a GeoParquet write→read?"* — run
   it once before you start. It shows the exact pyarrow calls the fix uses and what they return in
   this venv.

## Why (the 30-second version)

Spec 34 said the builder reads what it needs from a declaration "attached to the artifact." The
per-row half shipped fine (`offset`/`nodata` are real columns). The collection-level half rides on
`GeoDataFrame.attrs`, **which GeoParquet does not persist**. There are three write→read hops from
ingest to builder, and the declaration dies at all three — including the per-cell hop where setup
writes a slice (`workflows/create_datacube.py:88`) and `run_task` reads it back **in a separate
process** (`workflows/task.py:59`). So the only production caller of `build_datacube` is hardcoded
to S2 today. Fixing it at the storage seam fixes all three hops at once.

## Environment

```bash
cd fsd
source .venv/bin/activate            # deps are NOT in system python
.venv/bin/python -m pytest -q        # baseline before you start: 294 passed / 3 skipped
.venv/bin/ruff check src/ tests/
```

Both must be green when you finish (test count will go **up** — §8 adds ~11 tests and deletes 1).

## Order of work (each step leaves the suite green)

1. **`declaration.py`** — `to_json`/`from_json`, `to_attrs`/`from_attrs`, `FSD_DECLARATION_VERSION = 1`,
   `ATTRS_KEY = "fsd:declaration"`. Pure functions, no I/O. Tests §8.1, §8.8, §8.9 pass here.
2. **`storage/fs.py`** — attrs preservation in `write_parquet`/`read_parquet` (spec §2). Tests §8.3,
   §8.5 pass here. **The fast path matters:** empty `attrs` ⇒ today's code path exactly, no pyarrow
   round-trip.
3. **`catalog/catalog.py`** — `TileCatalog(declaration=...)`, `append(declaration=...)`, the conflict
   rule, `.declaration` property (spec §4). Tests §8.7.
4. **`sources/cdse.py` + `sources/mpc.py`** — stamp `S2_L2A_DECLARATION` at the existing
   `catalog.append(rows)` calls (`cdse.py:548`, `mpc.py:281`). Two-line change each.
5. **`datacube/builder.py`** — resolve via `from_attrs`; **delete** the typed `attrs["declaration"]`;
   implement the §5a raise. Tests §8.2 (the one that actually matters), §8.6.
6. **`catalog/stac.py`** — the Collection mirror + `collection_to_declaration` (spec §7). Test §8.10.
7. **`fsd-restamp-catalog` / `fsd-catalog-inspect`** (spec §6). Test §8.11.
8. **Docs** — `docs/adding-a-source.md`, `CHANGES.md`, `TODO.md` (#42 → closed), `PROGRESS.md`,
   `RECIPES.md` (the two new commands).

## Gotchas — each of these has already bitten someone

- **A dataclass in `.attrs` is a future crash, not a style nit** (§2a). pandas/geopandas JSON-encode
  attrs on write; a `SourceDeclaration` object there warns *"defaulting to empty attributes"* **and**
  raises `TypeError`. Put the **plain dict** in attrs under `fsd:declaration`; return the typed
  object from a helper. §8.4 is the test that keeps this true — do not weaken it.
- **Use `PANDAS_ATTRS` as the footer key, JSON-encoded** — not a bespoke `fsd:` footer key. This is
  deliberate convergence with geopandas PR #3597 (merged upstream 2025-10-30, same key). The
  `fsd:declaration` namespacing lives **inside** the attrs dict, not at the footer level.
- **`gdf.to_arrow()` looks like the elegant single-write path. It is not** — it emits geoarrow
  extension metadata and **no `geo` key**, so the file stops being readable by stock
  `gpd.read_parquet` (`ValueError: Missing geo metadata`). Use the `to_parquet` → `pq.read_table` →
  `replace_schema_metadata` → `pq.write_table` route in §2. It was measured: +0.8 ms on a 200-row
  slice.
- **`.attrs` propagates fine in-memory** through boolean masks, `.copy()`, `.intersects()` filters,
  column assignment and `pd.concat` (verified). You do **not** need to re-attach it inside
  `TileCatalog.filter`. The only place it is legitimately rebuilt is `flatten_catalog`, which
  constructs a brand-new GeoDataFrame.
- **§5a must raise, and the message must be actionable** — name the offending path *and* the
  `fsd-restamp-catalog` command. Do **not** add a grace period, an env-var escape, or a
  "`satellite` looks like Sentinel-2 ⇒ default to S2" heuristic. The spec calls these out by name.
- **Existing tests will fail, and mostly they should be fixed, not the code.** `test_datacube_builder.py`
  builds catalogs by hand — those are *hand-built gdfs*, which per §5a keep the S2 default, so they
  should keep passing untouched. If one fails, you have probably applied the raise too broadly
  (it belongs to "came from a file", tracked via `attrs["fsd:source_path"]`).
- **Delete `test_declaration_does_not_survive_catalog_roundtrip_todo_42`** (`tests/test_catalog.py`).
  It pins the bug and is *designed* to fail once fixed. Replace it with §8.1.
- **Strip `fsd:source_path` on write** (spec §10, the resolved open item) — it is read-side
  bookkeeping; letting it serialize would leak a local absolute path into blob artifacts.

## Definition of done

- `pytest -q` green, count up by ~10 net; `ruff check src/ tests/` clean.
- **The §8.2 test exists and is non-vacuous:** a *non-S2* declaration stamped at ingest survives
  ingest → filter → slice write → **fresh process-equivalent read** → `flatten_catalog` → the
  builder. Sanity-check it the way the black-tile bug taught us: temporarily make
  `build_datacube` ignore the resolved declaration and confirm the test **fails**. An agreement
  test that both sides get wrong proves nothing.
- Living docs updated (step 8 above), TODO #42 marked closed with a pointer to spec 35.
- **Nothing committed** unless the user asks (`CLAUDE.md`). Leave the tree dirty.

## Explicitly NOT in scope

The `[G2]` native-grid build path, non-categorical `mask_type`s, the `Source` ABC (#11), any change
to the declaration's fields, per-row schema changes, and the actual **re-stamping of the four
on-disk catalogs** (§6) — that is a user-run migration folded into TODO #44's re-ingest, not
something this session executes.

## When you're done

Hand back to **Opus@high for review**. Flag anything where the spec was ambiguous enough that you
had to choose — that is exactly what review needs to look at hardest.
