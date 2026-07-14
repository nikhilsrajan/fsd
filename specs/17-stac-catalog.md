# Spec 17 — STAC-aligned catalog (thin)

> **Status: SIGNED OFF + IMPLEMENTED + VERIFIED (2026-07-06).** SO-1..SO-7 approved as drafted.
> `src/fsd/catalog/stac.py` + `TileCatalog.to_stac` + `tests/test_catalog_stac.py` (7 tests; 140
> total, ruff clean); `pystac` promoted to a direct dep. **Real-data smoke:** the 579-tile
> benchmark catalog → 579 STAC Items in 0.06 s with **no raster reads**, both UTM zones correct
> (289× EPSG:32637, 290× EPSG:32636), round-trip lossless. (pystac proj ext v2.0 → `proj:code`,
> not `proj:epsg`.) Roadmap phase **P0**, split out of spec 16.
> Makes fsd's tile catalog **STAC-valid and round-trippable** — get-it-right-early surface #1
> (catalog format), cloud-agnostic, locally testable. **Scope guard (ROADMAP §6): "STAC-valid +
> round-trips to STAC Items" — NOT a STAC API server** (that's L4/infra, later). Defines the
> **canonical fsd↔STAC mapping** so both the download catalog *and* the future inference-output
> catalog (P4/P5) share one abstraction.
>
> Decisions flagged **[SO-n]** need explicit sign-off (see checklist).

## Motivation

The catalog format ripples into inference outputs, cross-source catalogs, and TiTiler (which
expects STAC). Deciding it late means migrating data *and* rewriting the reader twice
(ROADMAP §6). The legacy deploy notebook already hand-built a `pystac` catalog of output COGs;
fsd should have **one** canonical mapping. Doing it now is cheap (pure metadata; `pystac`
already a transitive dep via `pystac-client`) and pins the decision without a risky rewrite.
This also advances TODO #14 (the STAC half of "COG + STAC → TiTiler").

## Design stance — additive export, not a schema swap [SO-1]

`TileCatalog`'s GeoParquet stays the **working/query format** — `filter()` (spatial/temporal +
`area_contribution`) and the datacube builder depend on it, and it is *not* changed. STAC is an
**export/interchange view** produced from it. Two formats for two jobs, with a pinned mapping:
- **GeoParquet (`TileCatalog`)** — internal build-time queries. Unchanged.
- **STAC** — interchange/serving (TiTiler, pgstac, cross-tool), produced on demand.

(We deliberately do **not** replace the schema with `stac-geoparquet` now — that would rewrite
the reader/builder path for a consumer that doesn't exist yet. `stac-geoparquet` is deferred to
when pgstac/TiTiler actually needs it. [SO-2])

## What changes (additive, contained)

1. **New `src/fsd/catalog/stac.py`** — the canonical mapping + serialization:
   - `tile_catalog_to_items(gdf, *, collection_id=None, read_proj=False) -> list[pystac.Item]`
   - `write_stac_catalog(items, dst_folderpath, *, catalog_id="fsd", collection_id="sentinel-2-l2a") -> str`
     — a **static, self-contained STAC catalog** (JSON: `catalog.json` + collection + item JSONs)
     via `pystac` (no new dep). [SO-2]
   - `items_to_rows(items) -> pandas.DataFrame` — inverse, for round-trip validation. [SO-5]
2. **`TileCatalog.to_stac(dst_folderpath, **kw) -> str`** — convenience: `read()` → items →
   `write_stac_catalog`. Writes next to the parquet by default.
3. **`pyproject.toml`** — promote `pystac` to a **direct** dependency (already transitive). No
   other new deps; `stac-geoparquet` deferred.
4. Write via **`fsd.storage`** (the JSON files land through the storage seam, so a blob/S3
   destination works later unchanged).

## Canonical fsd → STAC mapping [SO-3, SO-4]

One **Item per catalog row** (a tile-product acquisition, e.g.
`S2B_MSIL2A_20181231T080329_..._T37PBP_...`); one **asset per band file**.

| STAC field | Source (catalog column / derivation) |
|---|---|
| `Item.id` | `id` (the S2 product name) |
| `Item.datetime` | `timestamp` (UTC) |
| `Item.geometry`, `Item.bbox` | `geometry` (EPSG:4326 footprint) |
| `Item.collection` | `satellite` (`"sentinel-2-l2a"`) |
| `properties.eo:cloud_cover` | `cloud_cover` |
| `properties.proj:code` | **UTM EPSG derived from the MGRS tile in `id`** (e.g. `T37PBP` → `EPSG:32637`) — **no file I/O**. (pystac proj ext v2.0 serialises as `proj:code`, not the deprecated `proj:epsg`; set via `ProjectionExtension.ext(item).epsg`.) |
| `properties.grid:code` / `s2:mgrs_tile` | MGRS tile parsed from `id` (e.g. `MGRS-37PBP`) |
| `assets[<band>]` | each entry in `files` under `local_folderpath`; `href` = the file path (storage-aware); `media_type` by extension (**COG** for `.tif`, JP2 for `.jp2`, XML for `MTD_TL.xml`); `roles=["data"]` for bands, `["metadata"]` for `MTD_TL.xml`; `eo:bands` set for optical bands |
| `links` (source) | `s3url` (the source `.SAFE`) as a `rel="via"`/`derived_from` link |
| `properties.proj:shape`, `proj:transform` | **per-asset, opt-in** via `read_proj=True` (opens each raster). **Default `read_proj=False` → zero file I/O** (band resolutions differ, so these are per-asset, not item-level). |

Everything except the opt-in `proj:shape/transform` is derivable from the catalog columns +
the product-name MGRS tile with **no raster reads** — so `to_stac` on the 579-tile benchmark is
a pure-metadata pass.

### Asset hrefs [SO-4]
For local runs, `href` = the absolute local file path (`local_folderpath`/`<file>`). Href
construction goes through a small seam so blob/S3 destinations produce `abfss://`/`https://`
hrefs later (P1) without changing the mapping. `.tif` assets get the **COG** media type
(`image/tiff; application=geotiff; profile=cloud-optimized`).

## Shared abstraction for the inference-output catalog [SO-6]

`stac.py` is designed so the future **inference-output** catalog (P4/P5: one Item per output
COG, `proj:*` free because we just wrote the COG and hold its transform/crs) reuses the same
`write_stac_catalog` + asset/media-type helpers via a second item-builder
`cog_outputs_to_items(...)`. **Only the tile-catalog path is implemented in spec 17**; the
output-catalog builder is designed-for but deferred.

## Out of scope (explicit)
- **A STAC API server** / pgstac / dynamic search — infra, later.
- **`stac-geoparquet` serialization** — deferred to when a consumer needs it [SO-2].
- **Replacing `TileCatalog`'s schema** — it stays the query format [SO-1].
- **The inference-output catalog builder** — designed-for, implemented at P4/P5 [SO-6].
- **Blob/S3 hrefs** — the href seam exists; non-local wiring lands with storage (P1).
- **Reprojecting geometries** — footprints are already EPSG:4326 (STAC's required CRS).

## Ripple effects
- `pyproject.toml` — `pystac` promoted to a direct dep.
- `RECIPES.md` — add `TileCatalog(...).to_stac(dst)` / `fsd.catalog.stac` recipe.
- `CHANGES.md` — note the additive STAC export (GeoParquet unchanged).
- `TODO.md` #14 — mark the **STAC half** addressed by spec 17 (COG done spec 14; TiTiler still future).
- `specs/02-catalog.md` — add a pointer to spec 17 (STAC export view).
- No change to `filter`/builder/workflows/flatten behavior.

## Tests (`tests/test_catalog_stac.py`, new; synthetic)
- **Mapping**: a synthetic 2–3 row catalog → items; assert `id`/`datetime`/`bbox`/`collection`/
  `eo:cloud_cover`/`proj:epsg` (from a known MGRS tile, e.g. `T37PBP`→`32637`) and one asset per
  `files` entry with correct media types (`.tif`→COG, `MTD_TL.xml`→metadata role).
- **Validity**: items construct as `pystac.Item` and pass structural checks; run
  `pystac`'s validator **only if `jsonschema` is importable and offline** (no network in CI). [SO-7]
- **Round-trip**: `items_to_rows(tile_catalog_to_items(gdf))` reconstructs the 8 catalog columns
  equal to the input (lossless mapping). [SO-5]
- **Static catalog**: `write_stac_catalog` emits a self-contained catalog (`catalog.json` +
  item JSONs) readable back by `pystac.Catalog.from_file`; `read_proj=False` opens **no** rasters
  (assert no file reads / runs without the band files present).
- **`TileCatalog.to_stac`** end-to-end on a synthetic parquet.

## Sign-off checklist
- [x] **[SO-1]** Additive STAC **export** (`stac.py` + `to_stac`); `TileCatalog` GeoParquet schema unchanged.
- [x] **[SO-2]** Serialization = static self-contained STAC **JSON catalog** via `pystac` (no new dep); `stac-geoparquet` **deferred**.
- [x] **[SO-3]** One Item per catalog row; one asset per band file; media types by extension (COG for `.tif`).
- [x] **[SO-4]** Field mapping per the table; `proj:epsg` from MGRS (**no I/O**); `proj:shape/transform` opt-in `read_proj`; href seam for blob later.
- [x] **[SO-5]** Round-trip reconstructs the 8 catalog columns losslessly (validation, not a general importer).
- [x] **[SO-6]** `stac.py` shaped so the inference-output catalog reuses it; only tile-catalog path built now. **(Output builder `cog_outputs_to_items` since implemented in spec 18 / P0.5, reusing `write_stac_catalog`. Its Item `geometry` was later corrected from the raster bbox to the true S2-cell polygon — spec 28, 2026-07-14 — see `CHANGES.md`/`BUGS.md` BUG-003.)**
- [x] **[SO-7]** Tests: structural validity always; `pystac.validate()` only if offline `jsonschema` present (no network).
- [x] `pystac` promoted to a direct dep; living docs (CHANGES/RECIPES/TODO #14/spec 02) updated.
