# CHANGES vs legacy

Living record of how `fsd` differs from the legacy repos for behavior that **is**
carried over (renames, restructures, behavioral tweaks). Pure removals go in
`DROPPED.md`.

## Declaration persistence — the collection declaration survives write→read (spec 35, 2026-07-21)

Amends spec 34 §2a/§4, closing TODO #42 (below): the collection-level `SourceDeclaration`
now survives every catalog write→read hop, not just the per-row `offset`/`nodata` columns.

- **Authority moved from `GeoDataFrame.attrs["declaration"]` (in-memory only, a typed
  dataclass) to the catalog Parquet file's own footer**, as a JSON dict under
  `attrs["fsd:declaration"]` (versioned, `fsd_declaration_version`). `fsd.storage.fs`'s
  `write_parquet`/`read_parquet` gained generic `.attrs` <-> `PANDAS_ATTRS` footer
  preservation (the upstream pandas/geopandas convention, geopandas PR #3597) — the fix
  lives at the storage seam so it covers all three write→read hops (ingest catalog,
  per-cell slice, builder entry) at one choke point, not just `TileCatalog`.
- **`TileCatalog.append` now stamps a declaration** (`declaration=` kwarg, constructor
  default); one catalog file = one collection = one declaration — a conflicting append
  raises. `sources.cdse.download`/`sources.mpc.download` stamp `S2_L2A_DECLARATION` at
  their existing `catalog.append` call (this is the change that makes hop 1 real — before
  this, *nothing* in the ingest path declared anything).
- **Behavior change, intentional (spec 34 `[G4]`'s "fail loudly, don't half-understand"
  rule applied here too): a catalog read from a file with no declaration stamp now
  raises** at `flatten_catalog`/`build_datacube`, naming the file and the re-stamp
  command (`python -m fsd.catalog.restamp_cli <catalog.parquet> --declaration s2_l2a`,
  a sub-second rewrite of the catalog Parquet alone — the imagery is untouched, nothing
  is re-downloaded). A **hand-built** `GeoDataFrame` (never through
  `fs.read_parquet`) keeps the S2 L2A default — an explicit in-process call is treated as
  an explicit choice, preserving synthetic-test/notebook ergonomics. The four catalogs
  written before this spec (`demo_e2e`, `mpc_baseline`, the `rise` blob catalog, old
  per-cell slices) need re-stamping before they build again; folded into TODO #44's
  re-ingest, not a separate migration.
- **STAC gets an additive Collection mirror** (`TileCatalog.to_stac`/`write_stac_catalog`):
  the mask band's classes as the standard `classification:classes` on an `item_assets`
  entry, plus `fsd:declaration` for the fields STAC has no vocabulary for. Read back via
  `fsd.catalog.stac.collection_to_declaration`. The Parquet footer stays authoritative —
  the mirror cannot drift because both are written from the same object.
- **`GeoDataFrame.attrs["declaration"]` (the typed dataclass key) is retired** — a
  dataclass must never sit in `.attrs` once any writer JSON-encodes it (verified: a future
  geopandas raises `TypeError` on write). Use `fsd.catalog.declaration.from_attrs`/
  `to_attrs` instead of touching `.attrs["declaration"]` directly.
- Was logged as TODO #42 (review pass, 2026-07-20; corrected 2026-07-21 while writing this
  spec — the gap was **not** latent on the production path, `run_task` used
  `S2_L2A_DECLARATION` unconditionally). Pinned meanwhile by
  `tests/test_catalog.py::test_declaration_does_not_survive_catalog_roundtrip_todo_42`,
  deleted and replaced by `test_declaration_survives_catalog_roundtrip` + the spec 35 §8
  test suite (`tests/test_declaration.py`, `tests/test_restamp_cli.py`, and additions to
  `test_storage.py`/`test_catalog.py`/`test_datacube_builder.py`/`test_catalog_stac.py`).

## Ingest/normalization contract: `stage → normalize → put`, declaration-driven builder (spec 34, 2026-07-20)

- **`apply_boa_offset`'s lossy `clip(DN−1000, 0, 65535)` is dropped from the store path**
  (it was never actually called there — spec 32 only used it at build/read time — but
  the function itself is renamed `fsd.raster.images.apply_offset` and documented as
  read-time-only, generalized past S2's BOA-specific name). The on-disk COG is now
  explicitly the lossless artifact; the offset is metadata, applied at read time by the
  builder and, independently, by an `unscale`-aware viewer (spec 34 §1).
- **`boa_add_offset` catalog column retired; `offset` + `nodata` replace it** (spec 34
  §1/`[G4]`) — `fsd.catalog.catalog.COLUMNS`. `offset` is the same additive-DN semantics,
  renamed generic (not S2-BOA-specific); `nodata` is new (spec 34 §1c — some MPC COGs
  omit a nodata tag; ingest now declares one, defaulting to 0). **No back-compat shim:**
  `TileCatalog.read()` does not backfill a legacy catalog missing these columns
  (`fsd/catalog/catalog.py`); a pre-spec-34 catalog is disposable, not migrated.
- **CDSE now derives `offset` from `s2:processing_baseline`** (`fsd.sources._s2_radiometry
  .offset_for_item`, shared with MPC) — closes #30/#10 (CDSE previously hardcoded 0/never
  harmonized). CDSE's jp2→COG conversion (`_convert_one`) now also stamps the GDAL
  scale/offset + nodata-if-missing tag (`fsd.raster.cog.stamp_or_reencode`) — free, since
  it already re-encodes.
- **MPC's download is no longer a pure byte-copy** — after `fs.transfer`, it stamps the
  same GDAL tags on the local file (`_transfer_and_stamp_one`) before the file is
  considered done. Still cheap (a header-only edit, `IGNORE_COG_LAYOUT_BREAK=YES`; no
  pixel decode) unless the in-place stamp breaks COG validity, in which case
  `stamp_or_reencode` falls back to a GDAL-COG-driver re-encode.
- **Both CDSE's and MPC's local-only download guards are lifted** (spec 31 §5-ARCHIVE
  suspended these) — a remote (`abfss://`) `root_folderpath` now works for both. MPC
  streams each file through local scratch before pushing (`fs.put`); CDSE reuses its
  entire existing local pipeline unchanged against a temp scratch root, then does one
  whole-run batch push + catalog-rewrite at the end (`_push_scratch_to_remote`) — **not**
  per-file streaming (that's TODO #31, still out of scope), so a CDSE run against a
  remote root is not yet crash-resumable the way a local-root run is.
- **`build_datacube` is declaration-driven, not S2-hardcoded** (spec 34 §2, closes #35):
  a new `fsd.catalog.declaration.SourceDeclaration` (+ `MaskSpec`) carries reference
  band, mask spec, mask-keep, nodata default, mosaic method. Resolved from the explicit
  `declaration=` kwarg, else `catalog_subset.attrs["declaration"]` (set by
  `flatten_catalog`), else the S2 L2A default (`S2_L2A_DECLARATION`) — so every existing
  caller (`workflows/task.py`, `api.py`, `create_datacube.py`) is unchanged. The mask
  step is skipped entirely (not just tolerated) when the declared mask band isn't in the
  requested `bands` — `bands=["B04"]` no longer raises `ValueError: SCL band not present`.
  A `mask_type` other than `"categorical_classes"`, or `native_grid=True`, raises
  `NotImplementedError` (loud, documented gaps — `[G2]`/`[G3]`) instead of silently
  mis-assembling or mis-collapsing. `ops.apply_cloud_mask_scl` gained a `mask_band="SCL"`
  parameter (default preserves old behavior) so the same op works for any categorical
  mask band, not just SCL.
- **STAC export carries `raster:bands` + role-tagged asset `roles`**
  (`fsd.catalog.stac.tile_catalog_to_items`) — every raster asset gets `offset`/`scale`/
  `nodata` (pystac `raster` extension) and a role (`reflectance`/`mask`/`reference`)
  alongside `"data"`. `items_to_rows` recovers `offset`/`nodata` on the reverse mapping.
- **New:** `fsd/catalog/declaration.py` (`SourceDeclaration`, `MaskSpec`,
  `S2_L2A_DECLARATION`), `fsd/sources/_s2_radiometry.py` (shared baseline→offset),
  `fsd/raster/cog.py::stamp_gdal_tags`/`stamp_or_reencode`, `fsd/docs/adding-a-source.md`.

## P1 Azure compute seam: `storage=` is now meaningful (spec 31, 2026-07-17)
- **`storage=` on `download`/`create_training_data` now does something** — previously
  `_check_local_seams` (`api.py`) rejected any non-`None` `storage` unconditionally ("blob lands
  in P1"). It now accepts `storage="azure"` or `{"backend": "azure", ...}`, which sets
  `FSSPEC_ABFSS_ANON=false` in **both** `os.environ` (for Snakemake-subprocess children, which
  re-read `FSSPEC_*` at their own import) and `fsspec.config.conf` (for the already-imported
  parent — fsspec only reads env at import time, so a later `os.environ` mutation alone would not
  be seen in-process). `runner!="local"` and any other `storage` backend still raise.
  `run_inference`/`deploy` are **unchanged** — `_check_local_seams` gained a `storage_allowed`
  flag and those two verbs pass `storage_allowed=False`: inference/serving-on-blob is P4/P5, out
  of P1 scope, and stays rejected exactly as before.
- **No new registry, no credential object.** adlfs, given only `account_name` (parsed from the
  `abfss://` URL host) + `anon=False`, builds its own `DefaultAzureCredential`. All ~94 existing
  `fs.<fn>` call sites in `fsd.storage.fs` are untouched — an `abfss://…` URL now simply resolves
  through `fsspec.core.url_to_fs` to a credentialed adlfs filesystem, no fsd code in the path.
- **New `fsd/storage/azure.py`**: `to_vsi(url)` (deterministic `abfss://<fs>@<account>.dfs.core
  .windows.net/<path>` -> `/vsiadls/<fs>/<path>`; local paths pass through unchanged; `az://<fs>/
  <path>` accepted as an alias), `account_from_url(url)`, `storage_token()` (a fresh
  Storage-scoped bearer token from a single **module-cached** `DefaultAzureCredential` — reused
  across calls per the documented best practice; the SDK's own token cache/refresh means "fetch a
  fresh one per open" is cheap and correct, no hand-rolled expiry margin), and
  `configure_storage(storage)` (the `storage=` -> env/`conf` helper above). `fsd.storage.fs.to_vsi`
  re-exports it.
- **Raster pixel reads now route through `fsd.raster.rio_open`** in the three pixel-read modules
  (`raster/images.py`, `raster/cog.py`, `catalog/stac.py`), replacing bare `rasterio.open`. For a
  local path it is a **byte-for-byte passthrough** (no `Env`, no translation — the regression
  hinge). For an `abfss://`/`az://` path it opens via GDAL's `/vsiadls/` handler inside a
  `rasterio.Env(AZURE_STORAGE_ACCESS_TOKEN=…, AZURE_STORAGE_ACCOUNT=…)` — the account comes from
  the URL host (D1), not ambient config — and keeps that `Env` alive for the dataset's lifetime
  (closed when the dataset is closed), since GDAL may issue further range-reads after open.
  `mode="w"` on a remote path **raises** rather than silently half-writing: P1 has no write path
  to blob (MPC-to-blob, when it lands, is a byte-copy via `fs.transfer`, never a GDAL write; CDSE-
  to-blob is out of P1 scope). `raster/cog.py`'s `to_cog` **write** path (`rasterio.shutil.copy`)
  is unchanged — it is local-only by design (CDSE's jp2->COG conversion; CDSE is untouched by P1).
- **Not changed, deliberately**: `sources/mpc.py` (`mpc.py:294`'s local-only guard stays) and
  `sources/cdse.py` (its `cog=True`-needs-local guard stays) — download-to-blob is **suspended**
  into the next spec (the ingest/normalization contract); P1's blob data is hand-staged
  (`runbooks/31-p1-upload-slice.md`). `datacube/builder.py` and `workflows/*.py` needed **no**
  fixes for the §6 URL-safety audit — both were already clean (`fs.*` throughout, `os.path.join`
  on catalog rows is posix-safe on an `abfss://…` host per §2). The remaining bare
  `rasterio.open(...)` sites (`api.py`'s inference-merge path, `model/engine.py`'s inference-output
  write) are **out of P1 scope** (inference/serving-on-blob is P4/P5) and were not touched.
- **New optional dependency**: `azure-identity` added to the `[azure]` extra (alongside `adlfs`) —
  `DefaultAzureCredential` construction needs it directly for the GDAL VSI token path (adlfs
  resolves its own copy internally, but `fsd.storage.azure` also needs one for `rio_open`).
- **New §6 audit finding + fix (beyond the spec's own grep head-start, which only checked
  `os.path.exists`/`os.makedirs`/bare `open(` and missed this): `workflows/create_datacube.py`'s
  `setup()` and its Snakefile both called `os.path.abspath()` on `export_folderpath` unconditionally.**
  `os.path.abspath` does not recognize a URL as absolute (`os.path.isabs("abfss://...")` is `False`),
  so it silently prepended the local cwd and mangled the `abfss://` scheme into `abfss:/` — a real,
  silent corruption bug for a blob `export_folderpath`, not just a style nit. Fixed with a new
  `fsd.storage.fs.is_local(path)` guard (both call sites) — no behavior change for local paths.
- **New, deliberately-not-fixed finding: the local Snakemake runner's own `start.txt`/`done.txt`
  sentinel bookkeeping (`create_datacube/Snakefile`'s `touch()`) is plain `os.makedirs`/`open`, not
  routed through `fsd.storage`.** Even with the `os.path.abspath` bug fixed, a remote
  `export_folderpath` would make Snakemake's own DAG/resumability tracking silently create a garbage
  local sentinel directory (not a crash — `open("abfss://.../done.txt", "w")` is a valid, if bizarre,
  *local* relative path). This is a **real limitation of the local runner**, not something spec 31's
  scope (§1–§4/§6/§7) covers or that a "swap bare `rasterio.open`" pass can fix — it needs a design
  decision about where Snakemake's own bookkeeping lives when artifacts are remote (candidates: keep
  it always-local via a separate scratch dir, or a proper Snakemake remote-storage plugin). **The
  Snakefile now raises a clear `RuntimeError` instead of silently corrupting** (fail loud, per the
  project's `rio_open`-write-guard precedent) — the workaround today is to keep `run_folderpath` local
  (the datacube/flatten artifact writes themselves are fully storage-seam-safe on blob regardless) or
  to invoke `python -m fsd.workflows.task` directly for a single remote build (no Snakemake
  involved — this is exactly what the demo run-book does). Logged as TODO #41 (folded into the Batch
  runner item, since a real fix likely arrives with that redesign anyway).
- See `specs/31-p1-azure-storage-seam.md` (realizes spec 10 Seam 1: storage = config, not code).

## MPC discovery dedupes reprocessed acquisitions (spec 33, 2026-07-16)
- **`sources/mpc.py`** now de-duplicates STAC items at discovery time: `query_catalog` and
  `download` both call a new `_dedupe_reprocessed_items(items)` immediately after `_search_items`,
  before any catalog row is built. MPC can serve >1 STAC item for the same physical acquisition
  (a one-off `sen2cor` reprocessing pipeline bug, since cleaned up on MPC's side, per spec 33's
  cross-validation) — same sensing `item.datetime` + same `s2:mgrs_tile`, different item id. Prior
  behavior: both items downloaded (redundant bytes) and both catalogued, with
  `datacube.builder._stack_datacube`'s CRS/`image_index` tie-break arbitrarily picking a winner at
  merge time. Grouping key is in-memory `(item.datetime, _mgrs_tile_from_item(item))` — no new
  catalog column. Winner = the item with the latest `s2:generation_time` (a populated STAC
  property; reversing the id-string-parsing approach the runbook originally suspected, since ESA's
  naming-convention doc does not guarantee the id's trailing field is monotonic). A duplicate group
  missing `s2:generation_time` on any member raises (deterministic, no silent pick); a singleton
  item is never affected even if it lacks the property. **MPC-only** — `sources/cdse.py` and
  `_finalize_catalog_gdf` are untouched; CDSE's own multi-item surfacing (datastrip-split
  near-duplicates) is a structurally different, ESA-by-design case that can carry legitimate
  different pixel coverage, so a shared rule risked dropping real CDSE data. See
  `specs/33-mpc-reprocessing-dedup.md`.

## MPC source + S2 processing-baseline harmonization (spec 32, 2026-07-16)
- **New source `sources/mpc.py`** — Sentinel-2 L2A discovery + download against Microsoft
  Planetary Computer (MPC), signed via the official `planetary-computer` package (new `[mpc]`
  extra), anonymous by default. Unlike CDSE (spec 01/14/25), MPC assets are **already COG on
  Azure**, so `mpc.download` is a **pure byte-copy** (`fsd.storage.transfer`, signed HTTPS ->
  local) — no `jp2->COG` conversion, no convert-process-pool. `api.download` gains
  `source: "cdse" | "mpc"` (default `"cdse"`, unchanged); `source="mpc"` does not require `creds`.
- **New catalog column `boa_add_offset`** (`catalog/catalog.COLUMNS`, before `geometry`) — the
  additive S2 processing-baseline reflectance offset (fixes correctness debt #10: baseline 04.00,
  introduced 2022-01-25, adds `BOA_ADD_OFFSET=-1000` to L2A reflectance DN; MPC serves raw,
  unharmonized DN and does not expose the offset in STAC `raster:bands`, so it's derived from the
  item property `s2:processing_baseline`, **keyed on baseline not acquisition date** — MPC
  reprocessing can stamp a >=04.00 baseline on a pre-2022 date). **Backward-compatible**:
  `TileCatalog.read`/`append` fill a missing/absent column with `0` — old catalogs and CDSE rows
  (which don't yet set it, see `TODO.md`) are unaffected.
- **`datacube.builder.flatten_catalog`** now emits a per-band `boa_add_offset` output column:
  the tile-row's offset for reflectance bands (`B01`…`B12`/`B8A`), `0` for non-reflectance
  (`SCL`/`AOT`/`WVP`/`visual`/…) — `raster/images._is_reflectance`. **`build_datacube` applies the
  offset per source image** (new `builder._apply_boa_offsets`, called right after
  `images.load_images` returns, before `dst_crs`/reference/resample/mosaic) via the new
  `raster/images.apply_boa_offset(data, profile, *, offset)` op
  (`clip(DN + offset, 0, 65535)`, dtype-preserved, nodata-safe). This guarantees a calendar window
  straddling the baseline cutover is harmonized to one scale **before** `median_mosaic` collapses
  it — a datacube-level op would be too late (the median would already have mixed baselines).
- **Not yet done** (see `TODO.md`): CDSE rows still default `boa_add_offset=0` unconditionally
  (wiring CDSE's own baseline capture is a follow-on); MPC stays local-download-only (Phase 2 /
  spec 31 decides stream-in-place vs copy-to-`rise`).

## flatten `coords.npy` reprojected to EPSG:4326 (TODO #16, 2026-07-15)
- **`datacube.flatten` now emits `coords.npy` as `(lon, lat)` in EPSG:4326**, not raw per-cube
  easting/northing in the cube's native UTM CRS. Each cube's kept-pixel coords are reprojected
  from `geotiff_metadata["crs"]` to EPSG:4326 (`rasterio.warp.transform`) before concatenation, so
  a training set spanning multiple UTM zones (e.g. EuroCrops west EPSG:32636 / east EPSG:32637) no
  longer mixes incomparable eastings/northings in one array (the same easting number in two zones
  is two different places). No-op when a cube's metadata carries no CRS (synthetic/legacy) or is
  already EPSG:4326. **Behavior change to the `coords.npy` artifact** — downstream code that read
  coords as native UTM must now expect lon/lat; the spectral arrays (`data`/`ids`/`labels`) are
  unaffected. Multi-zone reprojection covered by a new test in `tests/test_datacube_flatten.py`.

## stac-geoparquet export + Tier-2 mini-MPC harness (spec 30, 2026-07-15)
- **New, additive module `catalog/stac_geoparquet.py`** — `items_to_stac_geoparquet(items,
  dst_filepath)` writes a `list[pystac.Item]` to a single GeoParquet file via the `stac-geoparquet`
  library (new optional `[serving]` extra); `stac_geoparquet_to_items(src_filepath)` is the inverse
  (round-trip validation). Both stage through a local tmp file + the `fsd.storage` seam
  (`fs.put`/`fs.open`), since the installed `stac-geoparquet==0.8.1` API always wants a real
  filesystem path, not an fsspec handle. Not wired into any default write path — `run_inference`
  still writes the JSON STAC catalog as before; the full catalog-format migration is TODO #26's
  follow-on. Round-trip-tested (`tests/test_stac_geoparquet.py`, `pytest.importorskip`-guarded so
  the core `.venv` skips it) and smoke-run against the real 300-item Austria catalog via the new
  `demos/mini_mpc/export_stac_geoparquet.py` CLI.
- **New `demos/mini_mpc/` — the Tier-2 "mini-MPC" validation harness**, a local, throwaway
  pgSTAC + stac-fastapi-pgstac + titiler-pgstac stack proving fsd's inference outputs load and
  serve through the same register→searchId→XYZ flow MPC uses. `docker-compose.yml` pins the
  `pgstac:v0.9.11` DB image as-is; the two app services (`dockerfiles/Dockerfile.{stac-fastapi-pgstac,
  titiler-pgstac}`) install the **pinned stock PyPI packages** (`stac-fastapi.pgstac==6.3.1`,
  `titiler.pgstac==3.0.0`) on a slim Python base rather than forking a Dockerfile/source
  checkout — no published "just pull it" app-layer image exists upstream (see the README's table
  for the full rationale). `load_pgstac.py` converts the existing static STAC catalog to ndjson,
  rewriting each output COG's href to the container-visible `/data/<path>` the compose bind-mount
  exposes (the one non-obvious wiring step — 500s without it), and `pypgstac load`s it.
  `register_and_url.py` reuses spec 29's `build_colormap`, registers a
  `collections=["fsd-inference"]` search, and prints the XYZ tile template. **Deviates from spec
  30's draft assumption:** the installed `titiler.pgstac==3.0.0`'s own routes are
  `/searches/register` + `/searches/{id}/tiles/...` (response key `id`), not `/mosaic/register` /
  `searchid` — that's MPC's own product naming around the identical underlying contract
  (`STACNOTATOR_DIGEST.md §3`); documented in `register_and_url.py`'s docstring, à la spec 29's
  rio-tiler pin. Scripts + `runbooks/30-tier2-mini-mpc.md` only — Claude never runs Docker; the
  href-rewrite/ndjson-emission logic was smoke-tested directly (no Docker) against the real
  300-item catalog before handoff.
- **Runbook-run fix (2026-07-15):** the `raster` (titiler-pgstac) container crashed at startup with
  `ImportError: libexpat.so.1` — `python:3.12-slim` doesn't ship the system lib rasterio (via
  rio-tiler) links at import. `dockerfiles/Dockerfile.titiler-pgstac` now `apt-get install -y
  libexpat1` before pip. Runbook clarified: bring the stack up with `docker compose up --build -d`
  and keep it running for steps 2–6, run all `docker compose` commands from `demos/mini_mpc/` (it's
  directory-scoped), and `docker compose ps -a` to catch a crashed/exited container. Plain-language
  primer + running issue log kept at the workspace root in `MINI_MPC_NOTES.md` (outside the public
  repo).

## STAC inference-output Item geometry: true cell polygon, not raster bbox (spec 28, 2026-07-14)
- **Behavior change:** `catalog/stac.py::cog_outputs_to_items` gains a `geometries=` kwarg — a
  `{output_cog_filepath: geometry.geojson_path}` mapping sourced from the `run_inference` build
  manifest (`input.csv.shapefilepath`). When given, every output Item's `geometry`/`bbox` is now the
  **true S2-cell polygon** (CRS84, read straight from the manifest's `geometry.geojson`) instead of
  the raster bounding box — the old behavior over-claimed coverage past the ROI's slanted edges
  (BUG entry). `bbox` is tightened to the polygon's own bounds (still STAC-valid: `bbox` contains
  `geometry`). **Deterministic, manifest-driven, no fallback:** a COG missing a geometry entry, or
  one whose `geometry.geojson` is unreadable/empty, **raises** — this is not a per-item best-effort.
  `geometries=None` (the default) is unchanged: the raster-bbox path, for geometry-less callers
  (bare COG lists, unit tests, the pre-built folder/list inference modes with no manifest).
- `api.py::_finalize_outputs` gains a matching `geometries=` passthrough. Both `run_inference` modes
  now supply it: ROI mode (`_run_inference_roi`) builds it from the `input.csv` rows it already
  reads back; the pre-built `input.csv` mode (`_resolve_inference_pairs`) now also captures
  `shapefilepath` alongside `datacube_filepath`/`id` when present. Folder/list pre-built modes have
  no manifest and keep passing `geometries=None` (raster bbox, unchanged).
- New convenience wrapper `catalog/stac.py::cog_outputs_to_items_from_manifest(input_csv)` — reads
  an `input.csv`, builds the `geometries` map, calls `cog_outputs_to_items`. Used by the new
  `demos/regen_output_stac.py` (regenerates an existing output STAC from its manifest, no
  re-inference) and available to any future caller that only has an `input.csv` path.

## Titiler demo server: Tier-1 pre-styled XYZ for STACNotator BYO (spec 29, 2026-07-14)
- Purely additive (`demos/` + a new `[titiler]` optional extra) — no `src/fsd/` change. New
  `demos/titiler_serve.py`: a minimal FastAPI app serving `merged.tif` as a param-free pre-styled
  XYZ (`GET /cropmap/tiles/{z}/{x}/{y}.png`) via `rio-tiler` — discrete categorical colormap (from
  `demos/e2e_austria.py::CLASS_COLORS`, overridable by a `render.json`), `nodata=255` -> transparent,
  `resampling_method="nearest"` (categorical codes must never interpolate), permissive CORS.
  Validates fsd's serving-contract with the real consumer (STACNotator's Bring-Your-Own-XYZ mode)
  before the heavier Tier-2 pgSTAC + titiler-pgstac stack. Not part of fsd's core `.venv` — installs
  into an isolated `.venv-titiler`.

## Download pipeline: transfer/convert process-pool split (spec 25, 2026-07-11)
- **Conversion decoupled onto a process pool.** `sources/cdse.py::download` previously ran
  transfer+convert serially on one of `MAX_CONCURRENT_S3=4` worker threads
  (`_transfer_and_convert`); GDAL's `to_cog` holds the GIL, so a few converting threads starved the
  rest and collapsed download concurrency (~0.2 file/s observed, spec 23 instrumentation). Now a
  `MAX_CONCURRENT_S3`-wide **thread** pool only transfers bytes, while a separate
  `MAX_CONVERT_PROCS`-wide **process** pool (`spawn`, GDAL-safe) converts JP2→COG concurrently —
  chained via `add_done_callback` and bounded by a `sem_staged` backpressure semaphore (staged-but-
  unconverted JP2s on disk). Behavior kept: conversion is still lossless COG **with overviews**
  (`COG_OVERVIEWS="AUTO"` unchanged, D2). `_transfer_and_convert` is removed, replaced by
  `_transfer_one` (thread stage) + `_convert_one` (process stage, top-level & picklable);
  `_download_one` survives as the sequential reference wrapper (`_transfer_one` then inline
  `_convert_one`) but `download()` no longer calls it. New optional `download`/`download_resume`
  kwargs: `max_convert_procs`, `max_staged`, `convert_executor` (all defaulted, backward-compatible;
  `convert_executor` is the test seam — inject a synchronous stand-in to exercise the pipeline
  without a subprocess). The convert pool is created **lazily** (first file needing conversion) —
  `cog=False` or an all-skip resume pass spawns zero processes.
- **`MAX_STAGED` is disk-aware, not a static constant** (D5/D6): `cdse._default_max_staged` helper
  sizes the backpressure cap once at `download()` start from
  `shutil.disk_usage(root_folderpath).free` (`STAGING_DISK_FRACTION=0.25`,
  `STAGING_ITEM_GB=0.2`), targeting `headroom = MAX_CONCURRENT_S3 + 2*MAX_CONVERT_PROCS`. Disk is a
  **cap, not a lever** — a larger buffer past the saturation floor gives no throughput gain (bounded-
  buffer queueing), so free disk only shrinks the cap, never grows it. New `config.py` constants:
  `MAX_CONVERT_PROCS = min(os.cpu_count(), 8)`, `STAGING_DISK_FRACTION`, `STAGING_ITEM_GB`.
- **Circuit breaker → streaming stop, transfer-failures-only** (conscious semantics change). The old
  breaker "finished the current chunk, then stopped" (`ThreadPoolExecutor` per file-chunk); the new
  one continuous pipeline has no chunk boundary. The breaker now keys on **consecutive transfer
  failures only** — a `_convert_one` failure is a local/data fault (`"ConvertError"`), not a CDSE
  window, and does not touch the consecutive counter. On trip, the submit loop stops queuing new
  work; in-flight transfers/converts drain; the pass returns `circuit_tripped=True`, stopping within
  roughly `max_staged` items of the trip (no exact chunk count — `download_resume` is still the real
  recovery). `test_circuit_breaker_trips_and_stops_early` rewritten to monkeypatch `_transfer_one`
  and assert early stop, not the old exact "4 of 6" chunk count.
- **`chunksize` repurposed.** No longer batches the executor (there is one continuous pipeline); it
  now controls only the catalog-flush cadence (flush every `chunksize` completed files). Default
  stays `100`; callers (`download_resume`, api, demos) are unaffected.

## Download pipeline: exception-safe callbacks, no silent hang (spec 25b, 2026-07-11)
- **`download()`'s inner callbacks are now exception-safe.** A Phase-1 review of spec 25 found that
  `_on_transfer_done`/`_on_convert_done`/`_finalize` assumed the happy path — a **broken convert
  process pool** (GDAL segfault / OOM-kill) or a **catalog-flush write error** raised *before* the
  `remaining` decrement / `sem_staged` release, and `add_done_callback` swallows callback exceptions,
  so the drain never completed and `download()` hung forever on `all_done.wait()`. Fixed: `remaining`
  and `sem_staged` accounting no longer sit behind any fallible call (`pool.submit`, `cfut.result()`,
  the parquet write) — `fut.result()`, the convert hand-off, and `cfut.result()` are all wrapped, and
  the `sem_staged` release in `_on_convert_done` moved to a `finally`.
- **New `DownloadResult.pool_broken`** (additive, defaults `False`): set when the convert process pool
  dies mid-run. On a broken pool, the submit loop halts cleanly (no more new work queued; in-flight
  transfers still drain) instead of transferring granules that can no longer be converted.
  `sum_results` ORs it across passes, like `circuit_tripped`.
- **New `"PoolBroken"` failure reason** — counted in `failed_count`/`failures`/`reason_counts`, but
  **breaker-neutral** (does not touch the transfer circuit breaker's consecutive counter), same
  rationale as `"ConvertError"` (spec 25 C4): a broken local process pool is not a bad CDSE window.
  `download_resume` already retries a `pool_broken` pass with no cooldown (its completion check is
  keyed on `failed_count`/`circuit_tripped`, unaffected by this new reason) — bounded by `max_passes`
  as before; a deterministically-crashing granule re-breaks the pool each pass (TODO: per-granule
  quarantine).
- **Chunk-flush moved off the counters lock.** `_finalize` now snapshots-and-clears `pending_results`
  under `lock`, then calls `_append_downloaded` (the parquet write) outside it — serialized by a
  dedicated `flush_lock` (needed because concurrent flushes of *different* snapshots would otherwise
  race-write the same catalog file). A flush failure logs a warning and re-queues the snapshot for a
  later flush (recovered by `download_resume`'s idempotent-skip on the next pass if it's never
  retried within the run). The end-of-run flush is likewise wrapped.

## Safe download runner CLI + should_stop seam (spec 26, 2026-07-11)
- **New `should_stop: Callable[[], bool] | None = None` kwarg on `download()`/`download_resume`**
  (additive, default `None` = unchanged behavior). A generic user-stop predicate — not a hard-coded
  stop-file — checked in `download()`'s submit loop at the two existing checkpoints (top-of-loop and
  post-`sem_staged.acquire()`), alongside `tripped`/`pool_broken`, throttled to at most once per
  `config.PROGRESS_EVERY_S` (a filesystem `os.path.exists` isn't stat-ed per granule). Semantics are
  identical to `tripped`/`pool_broken`: halts **new** submissions only, every already-submitted
  transfer/convert finalizes normally and drains, a stopped item is never attempted (not a failure,
  not counted). New **`DownloadResult.stopped: bool = False`** (additive); `sum_results` ORs it.
  `download_resume` passes `should_stop` through to each pass, adds `if r.stopped: break` (a user
  stop ends the resume loop immediately — no cooldown, not a completion), and checks `should_stop()`
  once before starting each new pass.
- **New CLI `python -m fsd.sources.download_cli`** (`src/fsd/sources/download_cli.py`) — a thin
  driver wrapping `download_resume`: `--dry-run` (metadata-only preview via `plan_download` +
  `format_download_plan`, **zero band bytes**, no `probe_throughput`), `--stop-file` (builds the
  `should_stop` closure), an optional single `probe_throughput` baseline on the real path
  (skippable `--no-probe`), and a spec-24 `_result.json` per run. Exit code doubles as PASS/FAIL:
  `0` on clean completion **or** a user stop, non-zero on `failed_count>0`/`circuit_tripped`/
  unresolved `pool_broken`.
- **`_fmt_progress` ETA edge case fixed.** Rate/ETA were already reported (`N.N file/s | ETA ~Xm`);
  now `ETA ~?` is shown until `done > 0` (previously `ETA 0m`, misleadingly precise with no
  completions yet to extrapolate from). All existing fields/tokens unchanged (spec 23 assertions
  still hold).
- **Confirm-run runbook** `runbooks/26-download-confirm-run.md` — the first real CDSE network
  exercise of the spec-25/25b pipeline, over the tiny 1-MGRS-tile Austria slice (~7 granules/~2 GB,
  reusing `demos/e2e_austria.py::_single_tile_roi`). Not run yet (mobile-hotspot pause, spec 26) —
  self-contained `expected` block so a later session can verify the user's pasted `_result.json`
  without this conversation's memory.
- **Review fix (2026-07-11): CLI completion gate is now the terminal pass, not the summed
  `failed_count`.** `sum_results` sums `failed_count` across passes, so a resume that hit a
  transient failure on an earlier pass and recovered it on a later, clean pass previously reported
  `status="failed"`/exit 1 even though every file landed — the CLI was stricter than
  `download_resume`'s own completion semantics. `download_cli.main` now judges `status`/exit code
  from `results[-1]` (the terminal pass); an empty `results` list (stop-file already present before
  pass 1) is now `status="stopped"`, not a false "ok". `metrics.failed` reflects the terminal pass;
  a new `metrics.failed_total` keeps the historical sum as a diagnostic. Plus: a stale `--stop-file`
  silently turned "re-run to resume" into an instant no-op — the CLI now warns on startup if the
  stop-file already exists, and the runbook's step-2 failure guidance now says to `rm -f` it before
  resuming.
- **UX fix (2026-07-13): label the two silent startup phases.** `probe_throughput` silently
  downloads one full JP2 (~50–150 MB) and `download_resume` does its own STAC search before the
  first progress line, so a real run looked hung for up to a minute at launch. `download_cli` now
  prints `probing throughput (downloads 1 band file)…` / `probe: N.N MB/s` around the probe and
  `discovering + planning download…` before the download loop (all gated by `--quiet`, like the
  live progress lines). The runbook's step-2 "Expect" and "Stop / observe" wording — which had
  promised a standalone probe line that the code never emitted — now match.
- **Runbook criteria fix (2026-07-13), after the first real confirm-run (13-granule Austria slice).**
  Two defects in `runbooks/26-download-confirm-run.md`, both found while verifying the pasted
  `_result.json`: (a) the step-2 PASS formula `successful + skipped == missing_count` was wrong —
  `missing_count` is **granules** while `successful`/`skipped` are **files** (`len(bands)+1` per
  granule, the +1 being `MTD_TL.xml`), and `successful` already *includes* the skipped files, so the
  sum double-counted and mixed units; corrected to `successful == missing_count × (len(bands)+1)`
  with `failed == 0`. (b) the step-1 `missing_count` range `[5,10]` (assumed ~7) was too low — the
  real slice is **13 granules** (single MGRS tile, S2A+S2B ~5-day revisit over 2 months), so the
  range is now `[10,15]` and `--max-tiles` bumped `10 → 15` (13 would trip the old guardrail). Also
  documented that a real throughput measurement (step 4) needs a **fresh** download (`skipped == 0`),
  not a resume — a resume yields `transfer_s == aggregate == 0`.
- **Bugfix (2026-07-13): `download()` creates a missing local output root.** A fresh `--dst`
  `FileNotFoundError`'d because `_default_max_staged`'s `shutil.disk_usage(root_folderpath)` disk
  probe runs before any write, and nothing created the root (leaf dirs auto-create on write, but the
  probe is earlier). `cdse.download` now `fs.makedirs(root_folderpath, exist_ok=True)` for a local
  root right after the cog/local guard — creating the destination root is part of `download()`'s
  contract, not the caller's job, so this fixes the CLI, `fsd.download`, and workflows at once.
- **`_result.json` fix (2026-07-13): populate `expected` and `error`** (they were hardcoded `{}` /
  `None`, defeating spec 26 §4's self-contained-diff design). `download_cli` now (a) auto-fills the
  real-run `expected` with the universal success invariants (`failed=0, stopped=false,
  circuit_tripped=false, pool_broken=false`) and merges the runbook's run-specific criteria from a
  new `--expected-json PATH` flag; (b) sets `error` to a short reason on a non-exception
  `status="failed"`; and (c) wraps the run so a crash (network/creds/disk) still writes a
  `status="failed"` result with `error=repr(exc)` **before** re-raising — the runbook flow always has
  a result to paste. The confirm-run runbook now writes an `expected.json` and passes `--expected-json`
  to steps 1–2.
- **Stop-file UX (2026-07-13): acknowledge the stop + tighten the poll.** Two issues with
  `touch <stop-file>`: it was silent (no sign the stop was seen), and it appeared to take "too long"
  (progress kept climbing well past the touch). `download()` now (a) prints
  `stop requested — halting new submissions; draining N in-flight …` the moment the stop is first
  seen (N = in-flight count), and (b) polls the stop-file on a dedicated `STOP_CHECK_EVERY_S = 1.0`s
  interval (was coupled to `PROGRESS_EVERY_S = 5`s) so new submissions halt within ~1s of the touch.
  The *overshoot itself is by design*: a clean stop drains everything already in flight (≈ `max_staged`
  ≈ `MAX_CONCURRENT_S3 + 2×MAX_CONVERT_PROCS` ≈ 20 files) so no partial `.part`/`.src.jp2` is left —
  lower `--max-staged` to trade throughput for a tighter stop. Runbook stop-drill + "Stop / observe"
  updated accordingly.
- **Throughput metric honesty (2026-07-13), after the first fresh-download measurement.** The first
  real confirm-run read as `aggregate 4.83` vs `probe 25.4 MB/s` — alarming until you notice they
  aren't measured the same way. `aggregate_mb_per_s = bytes / thread-summed transfer_s` is a
  **per-stream** rate; comparing it to the single-stream probe is fine, but it isn't the effective
  throughput. `DownloadResult` gains **`transfer_wall_seconds`** (the wall-clock span the transfer
  phase actually occupied, earliest-start..latest-end, tracked in `_on_transfer_done`), and
  `download_cli` now reports **`wall_transfer_mb_per_s = bytes / transfer_wall_seconds`** — the
  honest all-streams effective rate. `wall ≥ probe` ⇒ concurrency helped; `wall < probe` ⇒ it didn't.
  First run: probe 25 / per-stream 4.8 / **wall 19** MB/s → link-bound, 4 streams slower than 1.
- **New `--max-concurrent-s3` knob (2026-07-13).** `download()`/`download_resume()`/`download_cli`
  gained `max_concurrent_s3` (default `config.MAX_CONCURRENT_S3=4`), threaded through the transfer
  `ThreadPoolExecutor` and `_default_max_staged` sizing, so a link-bound run can sweep stream count
  (`--max-concurrent-s3 1|2`) without editing `config.py`. Runbook step-4 rewritten to explain the
  three rates (probe / per-stream / wall) and which pair to compare.
- **`demos/e2e_austria.py` crop-map/NDVI colors (2026-07-13):** replaced the arbitrary `tab20`
  class colormap (which painted pasture/grassland pink) with a curated `CLASS_COLORS` dict —
  semantic where possible (grass→green, mustard→yellow, sunflower→orange, alfalfa→violet, …) and
  spread across hue/lightness for separability. Applied to **both** the crop map and the NDVI
  timeseries so each class has one consistent color; unlisted classes fall back to `tab20`. Cosmetic
  (demo-only); regenerate `demos/figures/{crop_map,ndvi_timeseries}.png` by re-running the demo.
- **`demos/E2E_AUSTRIA.md §8` filled from the real 2026-07-13 full run** (stitched: download+train
  from pass 1, inference from a clean re-pass) — timing table, download transfer/convert/wall block,
  per-cell build-vs-infer decomposition, and merged-map coverage (6830×6868, EPSG:32633, 99.2% valid).
- **`E2E_AUSTRIA.md` is now the single go-to doc (2026-07-13).** Threaded the safe download runner
  (`python -m fsd.sources.download_cli`: `--dry-run` sizing, `--stop-file`, `--max-concurrent-s3`,
  `_result.json`/`--expected-json`, the probe/per-stream/wall rates) into §2 + a §5 dry-run tip; added
  **Appendix C** ("why run the full ROI") capturing the real bugs full-ROI runs caught — spec-20
  tile-merge, spec-26 STAC id collision, the multi-UTM-zone display merge. **`demos/README.md`**
  rewritten from the stale Ethiopia writeup (referenced the renamed `e2e_ethiopia.py` /
  `inference_roi.geojson`) into a **thin redirect** to `E2E_AUSTRIA.md` (driver/adapter/estimator/
  figures pointers + a one-paragraph history note).
- **STAC inference-output item-id collision fixed (2026-07-13).** `catalog.stac.cog_outputs_to_items`
  derived each Item id from the COG **filename stem** (`os.path.basename → splitext`), but fsd writes
  every output as `<cube_id>/output.tif` — so all N items got the constant id `"output"`.
  `write_stac_catalog`'s `normalize_hrefs` then mapped them all to `./output/output.json`, producing a
  `collection.json` with **N identical item links** and **one** item file on disk (all others
  overwritten). Surfaced on the full Austria run (300 cells → 300 dup links, 1 file). Fix: id now comes
  from the **parent directory** (`_output_item_id`, the cube id — unique by fsd's `<cube_id>/output.tif`
  layout in both ROI and prebuilt-cubes modes), plus a **uniqueness guard** that raises if ids ever
  collide again instead of silently emitting a corrupt catalog. `merged.tif` + per-cell COGs were
  unaffected (they use `output_filepaths`, not the ids). Regression: `test_run_inference_writes_cogs_and_stac`
  now asserts **distinct** item ids (the old `len(items)==2` passed on the bug because
  `get_items(recursive=True)` followed the duplicate links to the same file twice). 213 passed.
- **`demos/e2e_austria.py` step 5 bugfix (2026-07-13): pass the required `output_folderpath`.**
  `step_inference` called `fsd.run_inference(...)` without `output_folderpath`, so ROI-mode preflight
  aborted with `PreflightError: output_folderpath is required.` — surfaced on the first full run to
  reach step 5 (smoke levels never exercised it end-to-end). Now passes
  `output_folderpath=OUTDIR/model_outputs`, matching the runbook 27 / `E2E_AUSTRIA.md §5` output paths
  (`model_outputs/<cell>/output.tif`, `stac/`, `merged.tif`). Demo-only; no `src/fsd/` change.
- **`demos/e2e_austria.py` step 2 now reports the aggregate (wall) transfer rate (2026-07-13)**, to
  match `download_cli` and the wall metric above. It divided `bytes_downloaded / transfer_seconds`
  (the thread-summed **per-stream** rate) everywhere; now the console `transfer` line shows the
  transfer-only wall seconds + **both** rates (`X MB/s aggregate / Y per stream`), the
  probe-vs-effective verdict compares the probe against the **aggregate** rate, and
  `cost_model["transfer_mb_per_s"]` (→ `demos/estimate.py` ETAs) is the aggregate rate
  (`per_stream_mb_per_s` kept as a diagnostic). Rationale: per-stream understated throughput ~4×
  (confirm-run 4.8 vs 19 MB/s) → the demo printed the wrong link-vs-contention verdict and
  `estimate.py` predicted download times ~4× too slow. Reporting/calibration only — no pipeline
  behavior change; `E2E_AUSTRIA.md §8`'s "MB/s summed" template line follows when §8 is filled.

## e2e Austria local-completeness gate + download instrumentation (spec 23, 2026-07-10)
- **`DownloadResult` gained decomposed metrics** (`fsd.sources.cdse`): `bytes_downloaded`,
  `transfer_seconds`, `convert_seconds`, `bytes_by_band`. `_transfer_and_convert` now times the CDSE
  byte-transfer separately from the local jp2→COG conversion (interleaved per file in worker
  threads, so the summed seconds may exceed wall-time). `_download_one` returns `(ok, reason,
  metrics)` — a **signature change** (its 4 call-site tests updated). New `sum_results` aggregates
  `download_resume`'s per-pass results.
- **New `cdse.probe_throughput`** — single-threaded one-file fetch → achievable MB/s baseline, so a
  run can tell CDSE/link-bound from local contention (VPN/background load).
- **New `cdse.plan_download` + `format_download_plan`** (the D13 guardrail) — query STAC + diff
  needed-vs-present tiles → an actionable `fsd.download(...)` plan (JSON + printed command, +GB/ETA
  when a cost model is known). Wired into the `create_training_data` / `run_inference` preflight:
  **missing imagery now raises a clear "run fsd.download first" with the exact params**, not a deep
  file-not-found. Compute verbs still never auto-fetch (quota + the Batch download-once model).
- **`run_inference` merge is now cross-UTM-zone-safe by default policy.** `_merge_outputs`
  `"reproject"` picks the target CRS by **max total cell area** (was most-cells; correct for clipped
  ROI-edge cells) and accepts a **`merge_crs=`** override (EPSG/CRS string). It is **lossless where a
  cell already matches the target** (single-zone ROIs like Austria don't resample). `run_inference`
  gained `merge_crs`.
- **`demos/e2e_ethiopia.py` → `demos/e2e_austria.py`** — now a **reusable template** that starts from
  a real CDSE **download** (step 2, probe + `download_resume` + decomposed timing), uses ROI-mode
  `run_inference(merge="reproject")`, and is driven by `--roi/--train/--id-col/--label-col/--creds`.
  New `demos/estimate.py` (no-download ETA) + `demos/E2E_AUSTRIA.md` (the go-to local-run doc).

## Inference parallelism: retire `mp.Pool`, unify on the runner seam + idempotent outputs (spec 22, 2026-07-07)
- **`engine.run_local` no longer uses `multiprocessing.Pool`.** It is now the **in-process
  sequential** path only (`cores=1` / live adapter / tests / debug). Parallel pre-built-cube
  inference (`cores>1`) fans out through the **Snakemake infer-only runner**
  (`workflows/infer_only_task.py` + `_snakefiles/infer_only/Snakefile` +
  `runners.run_local_infer_only`), routed from `api.run_inference` (kept out of `engine` to avoid a
  model→workflows import cycle). So **all** parallel fan-out (build, ROI, pre-built inference) now
  goes through the runner seam → Batch (P4) can dispatch pre-built inference too, as a pure
  `runner=` swap. **No `mp.Pool` anywhere in fsd.**
- **Inference is now idempotent.** Both paths **skip existing outputs unless `overwrite=True`** —
  a re-run of `run_inference` over an already-inferred set does nothing (fixes the observed
  behaviour where the engine re-inferred every cube despite existing `output.tif`). `cores>1`
  resumes via per-group sentinels; `cores=1` via an `fs.exists` check.
- **New `cubes_per_task` knob (default 1)** groups K cubes per Snakemake job so the one-per-job
  bundle load amortises (recovers the pool's economics without a pool — the intra-task loop is
  sequential). `overwrite=True` forces recompute (`--forceall`). `run_inference` gains
  `overwrite` + `cubes_per_task`; **default `cores=1` → fully backward-compatible** (only new
  default behaviour is skip-existing).
- **Behaviour preserved:** `cores=1` stays no-bundle in-process; `cores>1` requires a bundle (a live
  adapter is auto-saved), same as the old pool. Positional calls `run_inference(model, cubes, out)`
  unchanged.
- **Bundle drift-check relaxed for *unset* spec fields (`model/bundle.py::load`).** A field the
  adapter class leaves unset — `None`, an empty list, or `n_timestamps == 0` (the base default) — is
  now **skipped** by the code/bundle drift check; the bundle value is authoritative. This lets **one
  adapter class back models trained on different `T`** (n_timestamps is a trained-model property, not
  a code constant) — surfaced when the demo's `cores>1` path first exercised `bundle.load` in a
  worker. Fields the class *does* pin are still drift-checked (real drift still raises).
- **Demo (`demos/e2e_ethiopia.py`) now infers via the bundle at `cores>0`** (`model=bundle_dir,
  cores=CORES, cubes_per_task=20`) instead of a live sequential adapter — so step 5 is parallel +
  resumable and the demo is real coverage for spec 22. `demos/adapters.py::DemoRF` no longer
  hardcodes `n_timestamps` (model-determined). The demo exports its dir to `PYTHONPATH` so the
  runner's subprocesses can import `adapters:DemoRF`.

## run_inference: ROI mode + three merge modes (spec 21 / P0.75, 2026-07-07)
- **`api.run_inference`** now has two mutually-exclusive modes. Old (spec 18): pass
  `inference_datacubes=` (pre-built cubes, engine `mp.Pool`). New (spec 21): pass `roi=`
  (+ `catalog_filepath`/`startdate`/`enddate`/`mosaic_days`/`bands`) → fsd tiles the ROI
  (`fsd.grid`), then fans out a per-cell **build-datacube + infer → COG** task via the **runner
  seam** (`workflows/infer_task.py` + `_snakefiles/create_inference/Snakefile` +
  `runners.run_local_inference`). `inference_datacubes` + `output_folderpath` are now optional
  (both default `None`, validated) — **positional calls `run_inference(model, cubes, out)` still
  work**. `InferenceResult` gains `grids_filepath`.
- **Why the runner seam, not the existing pool:** the per-cell unit-of-work is what Azure Batch
  dispatches at P4, so folding inference into the runner keeps P4 a pure `runner=` swap. (The
  pre-built `mp.Pool` path was **subsequently retired too** — see the spec-22 entry above.)
- **`merge=` is now tri-state:** `False` (per-cell COGs only) | `True` (**strict single-CRS**,
  refuses cross-CRS, error points at `"reproject"`) | `"reproject"` (**display** merge: reproject
  to the dominant zone, nearest-neighbour, lossy). The demo's ad-hoc reproject-merge moved into
  `api._merge_outputs`; `demos/e2e_ethiopia.py` now calls `merge="reproject"`.
- **CDSE quota (SO-6):** ROI inference **never downloads from CDSE** — imagery is assumed present
  in the catalog (download is a separate up-front phase). On cloud (P4) this means Batch tasks read
  imagery from blob, never CDSE.

## Datacube builder: merge multiple tiles per acquisition (spec 20 bugfix, 2026-07-07)
- **`datacube/builder.py::_stack_datacube`** — when a shape is covered by several tiles of the
  **same acquisition** (it straddles an MGRS tile boundary), all of them are now **nodata-fill
  merged** onto the reference grid. Previously `ts_band_index` was a `dict((timestamp, band) ->
  image_index)`, which silently kept **one** tile and nodata-filled the shape's other portions —
  a faithfully-ported legacy bug (see `BUGS.md` BUG-002). Overlap tie-break: `dst_crs`-native
  tiles win over reprojected ones, then lower `image_index`.
- **Behavior change:** boundary-straddling shapes (e.g. the 5 km inference grids) now get full
  coverage instead of partial/mostly-nodata (worst spec-19 grid: 0.6 % → 82.8 % valid).
  Small single-tile shapes are largely unaffected (one image per `(timestamp, band)` → the merge
  is a no-op), but a **minority of training fields do straddle boundaries** — the spec-19 demo's
  cold rebuild recovered ~6 % more training pixels (217,914 → 230,567) on top of rescuing the
  inference grids. Output shape/axes unchanged.

## ROI→S2-grid tiling + end-to-end demo (spec 19, 2026-07-06)
- **New `src/fsd/grid.py`** — `roi_to_s2_grids(roi, grid_size_km=5, scale_fact=1.1)`: clean-room
  port of `rsutils.s2_grid_utils.get_s2_grids_gdf` (polyfill the ROI's convex hull at S2 res 11,
  keep intersecting cells, scale 1.1 for 10 % overlap, `gpd.overlay` clip to the ROI). `s2`+`s2cell`
  live in the optional **`[grid]`** extra so fsd core stays lean. This is the ROADMAP §4 / P4
  groundwork; the `run_inference(roi=…)` front-end that consumes it is still P4.
- **`demos/`** — `e2e_ethiopia.py` runs demo_01+02+03 as one flow (tiling → `create_training_data`
  → RF → inference datacubes → `run_inference` → COG/STAC + a crop map) on the existing Ethiopia
  data; `adapters.py::DemoRF` (NDVI+SAVI, band-limited to what the benchmark has); `README.md` is
  the report. Runs in an **isolated `.venv-modeldeploy`** (`[dev,grid,model-example]`).
- **Real finding:** the inference ROI straddles the S2 MGRS zone-36/37 boundary in practice, so
  per-grid datacubes land in **both** EPSG:32636 and 32637. `run_inference(merge=True)` refuses the
  cross-CRS merge (the single-CRS-merge principle, spec 18); the demo reprojects outputs to the
  **dominant** zone and mosaics that for the display map.
- New extras: `[grid]` (s2, s2cell); `matplotlib`/`seaborn` added to `[model-example]` for the plots.

## ModelAdapter contract + local train/deploy (spec 18 / P0.5, 2026-07-06)
- **New `src/fsd/model/`** (`adapter`/`features`/`engine`/`bundle`) generalizes the legacy
  `demo_02_model_train` + `model/demo_model_deploy.py` into a plug-in **ModelAdapter** contract.
  The feature transform (`mask_invalid_and_interpolate → NDVI/NDRE/… → remove raw bands`) that
  was **copy-pasted** between the train notebook and the deploy script now has **one** definition
  (the adapter's `feature_sequence`), run by fsd in **both** `create_training_data` and
  `run_inference` — the F1 anti-skew fix.
- **`create_training_data` wiring:** the previously-stubbed `feature_sequence`/`aggregate` params
  are live, plus a new `adapter=` (preferred). When any is given, fsd writes `features.npy`
  (+ `feature_ids`/`feature_labels`) **additively**; raw `data.npy` is kept. `aggregate ∈
  {None, "median_per_id", callable}` (the `np.nanmedian`-per-id reducer from demo_02 cell-3).
- **`run_inference` is real (was a P4 stub):** local engine over **pre-built inference datacubes**
  (input.csv / folder / list) → one COG per cube + a STAC catalog (+ optional merged map). fsd
  owns the predict loop (drop-NaN → chunked `predict` → nodata scatter → `(bands,H,W)`). Output
  COGs use **`raster.cog.to_cog`** (lossless + overviews) — **not** the legacy `rio_cogeo`/
  `cog_translate` path (see DROPPED.md). The ROI→S2-tiling front-end stays P4 and will call this
  same engine. Preflight asserts bands + `T` before any predict.
- **`catalog.stac.cog_outputs_to_items`** implemented (spec 17 SO-6, was designed-for): one STAC
  Item per output COG, `proj:*` read straight from the COG we just wrote.
- **Bug fixed:** `engine.infer_datacube` now **copies `band_indices`** before `modify_bands`,
  which mutates its `band_indices` argument in place — reusing one dict across cubes could
  otherwise corrupt it (caught by `test_predict_batch_size_matches_whole_tile`).
- **Deps:** no new *core* dep (sklearn/joblib live in the `[model-example]` extra for the example
  + runbook only). Exports: `fsd.ModelAdapter/BaseModelAdapter/Output/load_bundle/save_bundle`.

## STAC export view of the tile catalog (spec 17 / P0, 2026-07-06)
- **New (additive), `TileCatalog` GeoParquet schema unchanged:** `src/fsd/catalog/stac.py` maps
  catalog rows → **STAC Items** (one Item per tile-product acquisition, one asset per band file)
  and writes a **static, self-contained STAC catalog (JSON)** via `pystac`, through the
  `fsd.storage` seam. `TileCatalog.to_stac(dst)` is the convenience entrypoint.
- **Pure-metadata by default:** `proj:code` (EPSG) is derived from the **MGRS tile in the product
  id** (e.g. `T37PBP`→`EPSG:32637`), so `to_stac` reads **no rasters** (579-tile benchmark → 579
  items in 0.06 s, both UTM zones correct). Per-asset `proj:shape`/`proj:transform` are opt-in
  (`read_proj=True`). Media types by extension (COG for `.tif`); `eo:cloud_cover` from
  `cloud_cover`; `MTD_TL.xml` as a metadata asset; source `.SAFE` as a `via` link.
- **Round-trippable:** `stac.items_to_rows(...)` reconstructs the catalog columns losslessly.
- `pystac` promoted to a **direct** dependency (was transitive via `pystac-client`).
  `stac-geoparquet` deferred (add when pgstac/TiTiler needs it). Advances TODO #14 (STAC half).

## High-level API façade — `fsd.*` verbs (spec 16 / P0, 2026-07-06)
- **New (additive), no behavior change to existing modules:** `src/fsd/api.py` adds the
  user-facing verbs `fsd.download`, `fsd.create_training_data` (+ `run_inference` / `deploy`
  stubs, `compute_n_timestamps`, `TrainingData`, `PreflightError`), re-exported at top level so
  `import fsd; fsd.create_training_data(...)` works. It is a **façade** over
  `sources.cdse` / `workflows.create_datacube` / `datacube.flatten` — the legacy-derived
  entrypoints (`run_create_datacube`, `flatten`) are unchanged and still public.
- **Scope raised (ROADMAP §2.5):** `create_training_data` hides `input.csv` + the word
  "flatten"; the user provides label polygons + a catalog and gets back
  `data/ids/labels/coords/metadata`.
- **Seams present from day one:** every verb takes `runner="local"` / `storage=None`; non-local
  values raise (Azure Batch / blob land in P1/P2 as config, not API changes).
- **Preflight (ROADMAP §2.6):** cheap checks (window/`T`/bands/columns/catalog) run *before*
  any download or build and raise `PreflightError`, aggregating all failures.
- **`feature_sequence` / `aggregate`** are pinned in the `create_training_data` signature but
  raise `NotImplementedError` until P0.5 (ModelAdapter). Version bumped `0.0.1 → 0.1.0`.

## Calendar-interval median mosaic — new default (spec 15, 2026-07-05)
- **Behavior change (kept-but-changed): `median_mosaic` now buckets acquisitions into fixed
  calendar windows by default** (`mosaic_scheme="calendar"`, `config.MOSAIC_SCHEME`). Windows are
  `[startdate + k·mosaic_days, …)` over `[startdate, enddate)`; **labels are window-start
  boundaries** (not the first acquisition date); **empty windows are emitted as all-nodata slices**.
  So every datacube built over the same `startdate`/`enddate`/`mosaic_days` has an **identical
  `timestamps` axis regardless of tile/orbit/UTM zone** — which is what lets `flatten` (spec 05)
  concatenate cubes across a multi-tile training set. `mosaic_scheme="acquisition"` restores the
  exact legacy labeling (first-acquisition labels, occupied buckets only, gap-opens-interval quirk).
- **Resolves the TODO #2 anchor caveat.** The workflow `create_datacube.setup` now threads the
  **caller's calendar `startdate`/`enddate`** into each work-unit's mosaic anchor (the per-shape
  actual acquisition min/max is kept only for the run-folder name). Previously it threaded the
  actual first/last acquisition, so windows shifted shape-to-shape.
- **Threading:** `mosaic_scheme` added to `build_datacube`, `workflows.task` (`--mosaic-scheme`
  CLI, default from config), `create_datacube.setup`/`run_create_datacube` (+ an `input.csv`
  column), and the bundled Snakefile. Boundary rule is half-open `[lo, hi)` (a timestamp on a
  boundary lands in the later window; the final window is upper-inclusive so a timestamp exactly at
  `enddate` isn't dropped) — differs from legacy's `<=` walk only for an on-boundary timestamp.
- **Ripple:** mosaic timestamp *labels* change (calendar boundaries), but the pixel groupings /
  medians for a dense window are unchanged, so `datacube.md`'s numeric NDVI references still hold;
  the runbook carries a note. Legacy outputs are reproducible via `mosaic_scheme="acquisition"`.
- **Known limitation logged (TODO #16):** `flatten` concatenates per-cube `coords.npy` but a
  multi-zone training set mixes eastings/northings from different UTM zones (west→32636, east→32637)
  — fine as pixel identifiers, wrong if used spatially. Not fixed here.

## satellite_benchmark migrated JP2 → COG in place (spec 14 follow-up, 2026-07-04)
- **Data change (not code):** the real test archive `satellite_benchmark/` was converted from
  native JP2 to **COG (+ overviews), in place** — every `Bxx.jp2` → `Bxx.tif`, the `.jp2` deleted
  (no duplicate copies), and its `catalog.parquet` `files` column rewritten to `.tif`. 2316 band
  files, 0 failed, lossless (bit-identical verified); archive grew 94 → 159 GiB (COG+overviews ≈
  1.70× JP2). Downstream is unaffected — rasterio reads `.tif` transparently, so datacube builds /
  throughput runs work unchanged (they now read COG, i.e. faster; see the throughput runbook note).
- **New tool `benchmarks/migrate_jp2_to_cog.py`** (reusable): in-place JP2→COG migrator built on
  `fsd.raster.cog.to_cog`. Resumable (skips already-`.tif`), disk-safety floor (aborts before free
  space hits `--floor-gib`), live progress bar + ETA, catalog resynced from actual on-disk state,
  and a `--verify {full,quick,none}` pre-delete gate (default `quick` = readback + shape/dtype +
  overviews check; `full` re-decodes for bit-identical). Conversion is memory-bandwidth-bound → 8
  workers (the perf cores) is the knee; 10 gave no gain.

## COG-on-download — native ingest format (spec 14, 2026-07-04)
- **Behavior change (kept-but-changed): `sources.cdse.download` now converts each fetched JP2
  band to a lossless COG by default** (`cog: bool = True`). On-disk band files are `Bxx.tif`
  (was `Bxx.jp2`) and the catalog `files` column records `.tif`. `cog=False` restores the exact
  prior behavior (native `Bxx.jp2`). Turns the spec-13 finding (COG builds 1.58×–3.46× faster,
  lossless) into the ingest default so downloads are build-fast from the start.
- **COGs carry overviews** (`OVERVIEWS="AUTO"`) for the future TiTiler XYZ/WMTS goal (TODO #14).
  The datacube build reads full-res and never uses them; they cost ~+38% on top of base COG (so
  ingest COGs are ~1.7× JP2 storage — a deliberate tiling-readiness cost, not a build cost).
- **New `src/fsd/raster/cog.py::to_cog`** — one canonical local raster → COG primitive: lossless
  (DEFLATE + PREDICTOR=2; `NBITS=16` promotes S2's declared 15-bit depth so PREDICTOR=2 is legal —
  pixels unchanged), **atomic** (`.part` + `os.replace`, mirroring `storage.transfer`), optional
  overviews, optional `verify` (bit-identical read-back). COG profile constants live in `config`.
- **Download flow:** a band is fetched to a local staging sibling (`Bxx.tif.src.jp2`) via
  `storage.transfer`, converted with `to_cog`, staging removed; `MTD_TL.xml` transfers as-is.
  Idempotency keys on the final `.tif`; a crash leaves at most the staging JP2 (atomic convert),
  so resume re-fetches cleanly. Conversion runs inline in the existing S3 worker threads (GDAL
  releases the GIL) — a dedicated conversion process pool is a noted future optimization.
- **Seam boundary:** `cog=True` requires a **local** `root_folderpath`; a remote (`s3://`/`az://`)
  dst raises a clear error (the stage-local→convert→upload path is deferred to the Azure milestone).
- **`benchmarks/prep_cog_dataset.py` refactored** to delegate its conversion to `to_cog` (one
  source of truth for the COG profile); behavior identical (it still pins `OVERVIEWS="NONE"`).
- The read/build/datacube/workflow path is untouched — rasterio reads `.tif` transparently (spec 13).

## COG vs JP2 storage/time experiment (spec 13, 2026-07-04)
- **New (no legacy equivalent), no `src/fsd/` change:** measures what storing S2 tiles as
  **COG** vs native **JP2** buys in build time and costs in disk. Three additive benchmark
  scripts + harness CLI knobs; the read path is already format-agnostic (rasterio detects
  JP2/GTiff), so the switch is pure data + catalog.
  - `benchmarks/prep_cog_dataset.py` — converts the first N months of `satellite_benchmark`
    JP2 → **base COG** (DEFLATE + PREDICTOR=2, tiled 512, **no overviews**) into a mirror tree
    `satellite_benchmark_cog/` + a parallel `catalog.parquet`. Lossless: `NBITS=16` promotes S2's
    declared 15-bit depth (in a uint16 container) so PREDICTOR=2 is legal — pixel values
    unchanged; a bit-identical assert guards it. Includes a **disk pre-flight** (sample-estimate +
    free-space check, aborts before writing) and live progress/ETA. Emits `cog_vs_jp2_storage.md`
    (JP2 → base COG → COG+overviews, overview row estimated from a sample).
  - `datacube_throughput_sweep.py` gained **`--catalog` / `--start` / `--end` / `--tag`** so the
    Part-1/2 harness A/Bs JP2 vs COG with non-clobbering tagged outputs (report/stats/figures).
    Report image links now derive from `FIG_DIR` (tag-aware); added a `STATS` constant (replaces
    the fragile `FIG_DIR.replace("_figures", …)` derivation).
  - `benchmarks/compare_cog_jp2.py` — merges the two tagged `stats.json` + storage json into the
    team report `cog_vs_jp2_report.md`: time table, the **JP2-vs-COG duration-vs-concurrency
    overlay** (the decode-bound test), storage table, verdict.
  - Runbook `tests/manual/cog_experiment.md`. Measured on this data: base COG ≈ **1.23× JP2**
    (S2 JP2 barely out-compresses DEFLATE), overview delta ~+38%.

## Datacube throughput benchmark, Part 1 + `write_timings` seam (2026-07-03)
- **New (no legacy equivalent):** `benchmarks/datacube_throughput_sweep.py` — a reusable
  harness (spec 11 · Part 1) that sweeps build parallelism (`cores`) over the 100-grid ROI
  set and reports throughput + per-step timing + static grid×tile overlap. Baseline lives
  in `benchmarks/datacube_throughput_report.md` (+ `*_stats.json` for cross-run diffing).
- `datacube.builder.build_datacube` gained a **`write_timings: bool = False`** flag (off by
  default → no extra file in normal runs): when set, it writes a `timings.json` sidecar
  (per-phase wall-seconds + sizing counts) next to `datacube.npy`. The workflow enables it
  via the **`FSD_WRITE_TIMINGS=1`** env var (read in `workflows.task.main`), so the harness
  toggles it with zero runner/Snakefile plumbing. Phases are wrapped in a `_timed` ctx mgr.
- Read-path instrumentation (per-read parallel-reads / duration-vs-concurrency) is **not**
  here — deferred to Part 2 (spec 12); tile-splitting to Part 3 (spec 13).

## Datacube throughput benchmark, Part 2 — per-read instrumentation (2026-07-04)
- `datacube.builder.build_datacube` gained a **`write_read_log: bool = False`** flag (off by
  default → no extra file), mirroring `write_timings`. When set (and `njobs_load_images == 1`)
  it times each windowed read with **wall-clock `time.time()`** (comparable across grid
  processes) and writes a **`reads.jsonl`** sidecar next to `datacube.npy` — one row per read:
  `id` (grid), `mgrs_tile`, `product_id`, `band`, `filepath`, epoch `start`/`end`, `duration`.
  The workflow enables it via **`FSD_WRITE_READ_LOG=1`** (read in `workflows.task.main`). With
  `njobs_load_images > 1` the log is skipped with a `RuntimeWarning` (reads fan out to a Pool).
  The load loop was refactored: `_load_images` returns `(catalog_gdf, data_profile_list, reads)`
  and, on the logging path, reads each file serially via new `_load_images_logged`.
- `benchmarks/datacube_throughput_sweep.py` gained a **`--read-log`** flag (spec 12): it sets
  the env var, collects every grid's `reads.jsonl`, and computes **read conflicts** (overlapping
  read pairs from different grids), a **read-duration-vs-concurrency** curve (the direct test of
  the "parallel reads block each other" hypothesis), and a **same-file / same-tile / different-
  tile** classification — only *same-file* conflicts are what Part-3 tile-splitting can remove.
  Adds a "Read contention" section + 4 plots to the same living report and a `read_contention`
  block per `cores` to `stats.json`. Pure analysis (`conflict_stats`, `duration_vs_concurrency`,
  `_annotate_reads`) is unit-tested; `--read-log` is off by default so the baseline is unchanged.
- Concurrency is **instantaneous peak-in-flight** (bounded by `cores`), not overlap-degree — the
  metric the hypothesis needs. Tile-splitting itself stays deferred to Part 3 (spec 13).

## Workflows: task/runner split + fsd seams (2026-07-03)
- `workflows/create_datacube.py` + `setup_datacube_run.py` + the in-memory Snakefile →
  `fsd.workflows` as **task** (`task.py`, build one datacube, CLI `python -m
  fsd.workflows.task`) + **runner** (`runners.run_local`, drives the bundled Snakefile) +
  **entrypoint** (`create_datacube.run_create_datacube`: setup → runner). Same
  start.txt/done.txt sentinels + deterministic jitter.
- **Subset catalog is GeoParquet** (`catalog.parquet`) written via `TileCatalog.filter`
  (which already persists `area_contribution`), not legacy `catalog.geojson` + a separate
  `calculate_area_contribution` — the builder consumes the slice directly.
- **Task defaults `if_missing_files="warn"`** (legacy builder defaulted `raise_error`): at
  batch scale one partial-coverage shape shouldn't abort its job.
- **Snakemake and the task are invoked via `sys.executable -m …`** (not bare `snakemake`
  / `python`), so the workflow runs regardless of PATH / venv activation and the task
  always runs in the same interpreter as the runner.
- CLI passes `--bands` / `--scl-mask-classes` as **comma-strings** (single tokens) rather
  than legacy space-separated `nargs` (simpler Snakemake shell quoting).
- Added `storage.fs.rm` (delete through the seam; used to overwrite `input.csv`).

## Datacube builder: missing-band nodata fill shape (2026-07-02)
- Legacy `create_datacube_inmemory_single` filled a missing `(timestamp, band)` with
  `np.full((height, width), 0)` — a **2-D** array, while present bands are **3-D**
  `(1, H, W)` (rasterio single-band read). `np.stack`-ing them together would raise a
  shape error, and the fill defaulted to `float64` (promoting the whole cube). `fsd`
  fills with `(1, H, W)` in the present bands' dtype so the stack actually works.
- **Why it never bit legacy:** with `if_missing_files='raise_error'` (the default),
  any partially-missing band raises *before* stacking, so the buggy branch was
  unreachable. `fsd` fixes it so `warn`/`None` modes produce a valid cube. Same
  `datacube.npy` output on the complete-data path.

## Discovery: STAC API instead of Sentinel Hub (2026-07-01)
- Legacy discovered tiles via `sentinelhub.SentinelHubCatalog` (SH OAuth creds) and
  then listed each `.SAFE` over **S3** to find band files. `fsd` instead queries the
  **CDSE STAC API** (`pystac-client`, anonymous) and reads each item's `assets` to
  get the **per-band S3 hrefs directly** — no SH creds, no S3 listing.
- **Why:** the S3 `.SAFE` listing failed intermittently (`SignatureDoesNotMatch` /
  `InvalidAccessKeyId`) — a CDSE server-side issue (BUG-001). STAC sidesteps it; the
  only remaining S3-auth op is the per-file byte `transfer`, wrapped in fail-fast
  retry. Discovery no longer needs credentials at all.
- **Behavioral parity:** same catalog columns (`id, timestamp, geometry, s3url,
  cloud_cover`), same highest-res-per-band + `MTD_TL.xml` selection, same flattened
  on-disk layout. Note: STAC `item.id` has **no `.SAFE` suffix** (SH ids did); the
  `s3url` still carries `.SAFE`.

## Structure
- Three repos (`fetch_satdata` + `rsutils` + `cdseutils`) → one `src`-layout
  package `fsd` with functional modules: `sources/ catalog/ datacube/ bands/
  raster/ workflows/`.
- `cdseutils.*` → `fsd.sources.cdse` (+ shared bits in `fsd.config`).
- `rsutils.modify_images` (+ raster helpers from `rsutils.utils`) → `fsd.raster.images`.
- `rsutils.modify_bands` → `fsd.bands.modify`.
- `fetch_satdata.datacube.create_datacube_inmemory_single` → `fsd.datacube.builder`.
- `fetch_satdata.core.datacube_ops` → `fsd.datacube.ops`.
- `fetch_satdata.datacube.datacube_flatten_2d` → `fsd.datacube.flatten`.
- `fetch_satdata.workflows.create_datacube` + `setup_datacube_run` → `fsd.workflows.create_datacube`.

## Behavioral
- Catalog is the single file-based store (**GeoParquet**); the in-memory datacube
  builder reads it directly. No SQLite, no separate datacube/config DBs.
- Datacube builder is exposed behind a stable `build_datacube(...)` seam so an
  alternate engine (e.g. `rslearn`) can emit the same artifacts.
- **All file I/O via `fsspec`** (`fsd.storage`) — local in v1, Azure Blob / S3
  additive. No module touches raw paths directly.
- **S3 download generalized**: legacy's CDSE-private `boto3` download → a first-class,
  provider-agnostic S3 transport in `fsd.storage` (fsspec/`s3fs`, any `endpoint_url`:
  AWS, CDSE EODATA, MinIO…). CDSE keeps only STAC discovery + S2 file-selection. No
  direct `boto3`.
- Datacube creation restructured into **task + runner seam**: Snakemake becomes the
  *local* runner; the datacube task is CLI-invokable and runner-agnostic so an Azure
  Batch runner can dispatch it unchanged (Phase 2).
- CDSE catalog-query disk cache **removed** (always query live).
- Python floor raised 3.10 → **3.11**.
- Plotting / sklearn moved out of core into notebook extras.
- **`raster.images` parallel helpers run serially when `njobs == 1`** (no
  `multiprocessing.Pool`), instead of legacy's always-Pool. Same results; usable
  inside tests/other already-parallel contexts and avoids pickling/process
  overhead for the common single-job case. `njobs > 1` still uses a Pool.
- **`raster.images.reproject` now guards its output fill against `nodata=None`**
  (falls back to 0, matching the guard `resample_by_ref_meta` already had);
  legacy `reproject` would build an all-None-filled array if `nodata` was unset.
- `raster.images` follows the locked in-memory `(data, profile)` op convention for
  `crop`/`reproject`/`resample_by_ref_meta`/`merge_inplace` (the spec-phase scaffold
  had sketched some as file-in/file-out; corrected to match what the datacube
  builder actually chains via op `sequence`s).
- `bands.modify` carries only the demo-path ops (`modify_bands`,
  `mask_invalid_and_interpolate`, `compute_bands`, `remove_bands`, `scale_bands`) plus
  `expand_datacube`/`expand_flattened`. The `mask_interpolate` numba kernel that
  `mask_invalid_and_interpolate` needed (was in `rsutils.utils_preprocess`) is folded
  in as a private helper. All spectral indices from the legacy table are kept
  (NDVI/NDRE/GCVI/SAVI + NDWI/LSWI/BSI/PSRI/NDTI). Off-path ops deferred — see
  DROPPED.md (`median_mosaic`, `sav_gol`, `trim_bands`, `modify_bands_chunkwise`,
  preprocess-log (de)serialization).

## Kept identical (intentionally, for notebook portability)
- Datacube artifact format: `datacube.npy` + `metadata.pickle.npy` and the
  metadata dict keys.
- Flattened-data artifact set: `data.npy / ids.npy / labels.npy / metadata.pickle.npy`.
- 5-D band-array contract for `bands.modify`.
- Default bands, `scl_mask_classes`, `mosaic_days`, reference band B08, nodata 0.
