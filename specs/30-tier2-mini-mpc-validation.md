# Spec 30 — Serving contract Tier 2: local pgSTAC + titiler-pgstac "mini-MPC" (+ stac-geoparquet export)

> **Status: SIGNED OFF (2026-07-15) — ready to implement.** Opus@high (interview → spec → sign-off). All
> five open-questions accepted as recommended (new `[serving]` extra; new `catalog/stac_geoparquet.py`
> module; href-rewrite + `/data` bind-mount; geoparquet round-trip pytest only in this spec; Opus specs →
> Sonnet implements → user runs the Docker runbook). Implements **TODO #26 Tier 2**
> (the second half of the serving-contract validation; Tier 1 = spec 29, DONE). Builds directly on
> **spec 28** (inference Items now carry the true S2-cell polygon geometry — the thing pgSTAC search and
> the tiler's `ST_Intersects` key off) and **spec 29** (the discrete crop-class colormap, reused here).
> Context: the serving pivot (memory [[fsd-serving-stacnotator]], `../STACNOTATOR_DIGEST.md`) — fsd emits
> standard STAC+COGs; a **stock** pgSTAC + stac-fastapi-pgstac + titiler-pgstac stack serves the XYZ
> endpoints STACNotator already consumes for MPC. This spec stands that stock stack up **locally** to
> prove fsd is "just another MPC," and adds the **stac-geoparquet** interchange export (the #26 north-star
> catalog format). **Implementation lands in a Sonnet@medium session** against this spec (spec 24 D5);
> Opus does not implement. **The bring-up itself is a runbook the user runs** (Docker/servers — Claude
> never runs pipeline/networked/long processes, per CLAUDE.md); the only Claude-run part is the
> stac-geoparquet export + its pytest.

## What Tier 2 proves (and why it's separate from Tier 1)

Tier 1 (spec 29) served **one pre-styled crop-map COG** at a param-free `GET /…/{z}/{x}/{y}.png` and fed
it to STACNotator's **Bring-Your-Own-XYZ** mode — a fully pre-rendered image, no catalog, no search. That
validated the *pixels*, not the *plumbing*.

Tier 2 validates the **plumbing that mirrors MPC** — the path STACNotator treats as a first-class fast
path (`../STACNOTATOR_DIGEST.md §3`):

1. **A STAC API** (`stac-fastapi-pgstac`) over a **pgSTAC** database — browse collections + **search
   items** (CQL2 + sortby).
2. **A data/tiler API** (`titiler-pgstac`) — **`POST /mosaic/register`** a search → get a **`searchid`** →
   serve **XYZ mosaic tiles** at `/mosaic/{searchid}/tiles/{TileMatrixSet}/{z}/{x}/{y}` with viz params.

If fsd's outputs load into that stack and render through register→searchId→XYZ, then **fsd is "another
MPC"** and the whole "many projects, MANY models on STACNotator" story (TODO #26) holds structurally: each
model's outputs = one STAC **collection** in the same pgSTAC. We only have one model's outputs (the 300-cell
Austria crop map, spec-28-regenerated with true geometry), so we validate with **one collection**; the
many-models claim is the collection-per-model shape, not a per-model code path.

## Interview decisions (2026-07-15 — locked)

- **D-A. Serving stack = borrow the official eoAPI stock compose.** eoAPI already packages pgSTAC +
  stac-fastapi-pgstac + titiler-pgstac with a ready docker-compose. We **vendor + version-pin** it under
  `demos/mini_mpc/` and write only a loader + a runbook. Maximal build-vs-borrow; mirrors "*stock software,
  a deploy decision not fsd code*" ([[fsd-serving-stacnotator]]). No fork of the images.
- **D-B. Categorical color = baked into the tile request.** The discrete class→color table rides as
  titiler-pgstac's urlencoded **`colormap`** query param in the register/tile calls (reusing spec 29's
  `build_colormap`). Works today; **no dependency on TODO #28** (the render-extension) and **no STACNotator
  change**. The colors live in the request, not stored with the data — acceptable for a validation demo;
  the turnkey "stored with the collection" version is #28's job.
- **D-C. Success bar = command-line first; QGIS visual included; STACNotator is a stretch.** "Done" =
  curl-verifiable in a runbook (search returns the items with true geometry; register→searchId→tile PNG
  renders) **+ a QGIS XYZ-layer visual check** (the user's visual-validation principle — the Tier-2 analog
  of spec 29's QGIS step, now through the full pgSTAC→titiler-pgstac path). The **live STACNotator catalog
  integration** is an optional user-run stretch (§Verification step 7) — it may need a STACNotator
  config/PR to register a custom MPC-shaped endpoint, and we don't gate "done" on a repo we don't own.
- **D-D. Load format = convert the STAC JSON we already produce (ndjson), AND additionally build the
  stac-geoparquet export.** Tier-2 loading stays contained: convert the existing static STAC catalog to
  ndjson and `pypgstac load` it. Separately, this spec **also** adds the compact **stac-geoparquet** export
  (the #26 north-star interchange) as an additive fsd-core capability, validated by round-trip. The two are
  decoupled so the harness doesn't block on the catalog-format migration.

## Non-goals (explicitly out)

- **No production / Azure deploy.** The mini-MPC is a **local, throwaway validation harness**. The real
  serving deploy is platform infra (the `rise` project, `raapid-infra` — propose-only, a platform admin
  applies it), out of scope here. Do **not** put any private-infra values in `demos/mini_mpc/` (fsd is a
  public MIT repo — [[fsd-azure-infra]]).
- **No input-imagery serving.** Outputs-only. True-color input imagery needs B02/B03 (TODO #29), parked
  for university wifi.
- **No default-pipeline catalog migration.** `run_inference` keeps writing the JSON STAC catalog +
  `catalog.parquet` as today. The stac-geoparquet export is **additive** (a new function + CLI, not wired
  into the default write path) — the full migration is the #26 follow-on.
- **No render-extension (#28).** Categorical color via the baked-in `colormap` param (D-B).
- **No STACNotator code changes** required for the hard success bar (D-C).

## Design

### Deliverable A — the mini-MPC harness (`demos/mini_mpc/` + a runbook)

**A1 — borrowed, pinned compose.** `demos/mini_mpc/docker-compose.yml` (+ `.env`) vendored from the
official **eoAPI** docker-compose, **image tags/digests pinned** for reproducibility, running four
services: the **pgSTAC** Postgres/PostGIS DB, **stac-fastapi-pgstac** (STAC API), **titiler-pgstac** (data
API), and (as needed) a one-shot **pypgstac** loader/migrate container. A short `README.md` records the
eoAPI source + pinned versions. We borrow the images as-is (no fork).

**A2 — load path (ndjson via pypgstac).** `demos/mini_mpc/load_pgstac.py`:
- Reads the existing **static STAC catalog** produced by spec 28's regen
  (`tests/outputs/demo_e2e/model_outputs/stac/`, `catalog.json` → collection → 300 item JSONs) through the
  **`fsd.storage`** seam.
- Emits `collections.ndjson` (the `fsd-inference` collection) + `items.ndjson` (the 300 items), one JSON
  record per line — the format `pypgstac load` ingests.
- **Rewrites each item's COG asset `href`** from the host absolute path (`/Users/.../<cell>/output.tif`,
  what `cog_outputs_to_items` writes) to a **container-visible path** (`/data/<cell>/output.tif`). The
  compose **bind-mounts** the outputs folder → `/data` in the titiler-pgstac container so GDAL resolves the
  COG inside the container. *(Without this the tiler 500s on every tile — the host path doesn't exist in
  the Linux container. This is the one non-obvious wiring step.)*
- Runs `pypgstac load collections collections.ndjson` then `pypgstac load items items.ndjson` against the
  pgSTAC DSN (via the pinned pgstac container or a harness venv — the runbook picks one).

**A3 — categorical render via baked-in colormap.** `demos/mini_mpc/register_and_url.py`:
- Reuses `demos.titiler_serve.build_colormap()` → discrete `{code: [r,g,b,a]}` for the crop classes →
  `json.dumps` → urlencoded as titiler-pgstac's **`colormap`** query param. Also emits `assets=output`
  (the single asset key `cog_outputs_to_items` writes), `nodata=255`, `resampling=nearest` (class codes
  must never be interpolated — same categorical trio as spec 29).
- **`POST /mosaic/register`** with the search body (A4) → parses `{searchid}` from the response.
- Prints the full **XYZ template**
  `…/mosaic/{searchid}/tiles/WebMercatorQuad/{z}/{x}/{y}.png?assets=output&colormap=…&nodata=255&resampling=nearest`
  — the single string used by both the curl smoke and the QGIS XYZ layer.

**A4 — the search body.** A deterministic STAC/CQL2 search selecting **`collections: ["fsd-inference"]`**
over the full bbox/time (no cloud filter — outputs have none). This is the same register→searchId contract
MPC uses (`../STACNOTATOR_DIGEST.md §3`).

### Deliverable B — stac-geoparquet export (fsd core, additive)

**B1 — the export.** New module `catalog/stac_geoparquet.py` (isolates the optional dep, like `grid.py`),
`items_to_stac_geoparquet(items, dst_filepath)` — writes a list of `pystac.Item` to a single **GeoParquet**
file via the **`stac-geoparquet`** library, written through the **`fsd.storage`** seam (stage-local then
`storage.transfer` if the lib needs a direct path — document the exact call the implementer pins, à la spec
29's rio-tiler note). New optional extra **`[serving]` = `stac-geoparquet`** in `pyproject.toml` (keeps the
core `.venv` lean; matches the `[grid]`/`[titiler]` pattern). A thin CLI
`demos/mini_mpc/export_stac_geoparquet.py` (reads the catalog, writes `catalog.parquet` next to the JSON
STAC) makes it runnable.

**B2 — round-trip contract (the test).** `items_to_stac_geoparquet` then read back (via
`stac-geoparquet` → items / `pystac`) yields items **equal** on `id`, `geometry`, `bbox`, `datetime`,
`proj:shape`/`proj:transform`/`proj:code`, and the `output` asset. `pytest.importorskip("stac_geoparquet")`
so it skips cleanly in the core `.venv` (run from a `[serving]` venv).

**B3 — relationship to loading (documented, not required here).** pgSTAC can ingest stac-geoparquet
directly, so the export **is** a valid alternate load path; Tier-2 validation deliberately uses ndjson
(D-D) to stay contained. The runbook notes the geoparquet path as the north-star direction; exercising it
as a second pgSTAC load is an optional stretch, not a success criterion.

## Verification

**pytest (Deliverable B — fast, Claude may run):** the B2 round-trip test; `pytest -q` green (core `.venv`
skips it cleanly), `ruff check src/ tests/ demos/` clean.

**Runbook (Deliverable A — the user runs; spec-24, each step pastes back `_result.json`):**
`runbooks/30-tier2-mini-mpc.md` (template `runbooks/TEMPLATE.md`). One-time cost = pulling the eoAPI Docker
images (hundreds of MB, **one-time**; no satellite downloads) — recommend on wifi (Docker already proven
working 2026-07-15 via the STACNotator dev stack).

1. **Bring up** — `docker compose up` the mini-MPC; wait for all services healthy.
2. **Load** — `load_pgstac.py` → pgSTAC holds **1 collection + 300 items**. `_result.json`:
   `{collections: 1, items: 300}`.
3. **STAC search** — `POST /search {"collections":["fsd-inference"]}` → **300** items; spot-check one
   item's `geometry` is a **polygon** (>2 distinct x's and y's among the ring), **not a box** — proves
   spec 28's true geometry survived the round-trip into pgSTAC (this is what drives `ST_Intersects` +
   search). `_result.json`: `{searched_items: 300, geometry_is_polygon: true}`.
4. **Register** — `POST /mosaic/register` → **200** + a `searchid`. `_result.json`: `{searchid_present: true}`.
5. **Tile render (curl)** — `GET` the XYZ tile over Austria → **200**, `image/png`, non-empty.
   `_result.json`: `{tile_status: 200, tile_nonempty: true}`.
6. **QGIS visual (the user's principle)** — add the titiler-pgstac mosaic XYZ URL (colormap baked in) as an
   **XYZ layer** in QGIS → the crop map renders **in the real class colors**, over the **true cell
   footprints** (not boxy), through the full pgSTAC→titiler-pgstac path. PASS/FAIL + a screenshot.
7. **(Stretch) STACNotator** — add the local mini-MPC as a catalog/custom MPC-shaped endpoint in a locally
   running STACNotator → register→searchId→XYZ works **in-app**. User-run; may need a STACNotator
   config/PR; **not gating** for "done".

**Success (hard bar, D-C):** steps 1–6 pass. Step 7 is a bonus.

## Living docs to update (on implement)
- **`CHANGES.md`** — stac-geoparquet export added (additive); Tier-2 mini-MPC harness landed.
- **`RECIPES.md`** — mini-MPC launch + load + register + curl + QGIS recipe (append, per CLAUDE.md).
- **`TODO.md`** — #26 Tier 2 → DONE-pending-runbook; note the **catalog-format full-migration** (run_inference
  default → stac-geoparquet) remains the #26 follow-on; #28 (render extension) still open.
- **`pyproject.toml`** — new `[serving]` extra (`stac-geoparquet`).
- **`PROGRESS.md`** + memory [[fsd-status]], [[fsd-serving-stacnotator]] — checkpoint on merge/runbook.

## Open questions for sign-off
1. **`[serving]` extra name** (vs. folding `stac-geoparquet` into `[titiler]`). Rec: a new `[serving]` extra
   (distinct concern; keeps `[titiler]` = the Tier-1 tile server).
2. **Export location** — `catalog/stac_geoparquet.py` (new module) vs. a fn in `catalog/stac.py`. Rec: new
   module, so the optional-dep import stays isolated (like `grid.py`).
3. **Href-rewrite convention** (`/data/<cell>/output.tif` + bind-mount) — confirm acceptable, vs. mounting
   host paths at their exact absolute path (messier on macOS). Rec: rewrite + `/data` mount.
4. **Geoparquet as a second pgSTAC load path in the runbook** — include as an extra step, or pytest
   round-trip only for this spec? Rec: round-trip only here; note the load path (B3).
5. **Model split** — Opus specs (this), Sonnet implements the export + harness scripts; the user runs the
   Docker runbook. Confirm.
