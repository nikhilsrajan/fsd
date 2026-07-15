# mini-MPC — spec 30 (Tier 2 serving validation)

A **local, throwaway** stack proving fsd's inference outputs load into a stock
pgSTAC + stac-fastapi-pgstac + titiler-pgstac catalog and serve through the same
**register → searchId → XYZ** flow Microsoft Planetary Computer (MPC) uses — the path
STACNotator treats as a first-class fast path (`../../STACNOTATOR_DIGEST.md §3`, workspace
root, not part of this repo). See `specs/30-tier2-mini-mpc-validation.md` for the full design;
run it via `runbooks/30-tier2-mini-mpc.md`.

**No production/Azure deploy** — this is a dev-only harness (spec 30 non-goals). No private
infra values live here (this repo is public MIT).

## What's borrowed vs. locally built

| Service | Image | Source |
|---|---|---|
| `database` (pgSTAC) | `ghcr.io/stac-utils/pgstac:v0.9.11` | **pulled as-is**, no fork — the official published pgSTAC (Postgres + PostGIS + schema) image. |
| `stac` (stac-fastapi-pgstac) | built from `dockerfiles/Dockerfile.stac-fastapi-pgstac` | installs the **pinned stock PyPI package** `stac-fastapi.pgstac[server]==6.3.1` on a slim Python base and runs its own unmodified entrypoint (`python -m stac_fastapi.pgstac.app`). |
| `raster` (titiler-pgstac) | built from `dockerfiles/Dockerfile.titiler-pgstac` | installs the **pinned stock PyPI package** `titiler.pgstac[psycopg-binary]==3.0.0`, run with the exact same `gunicorn -k uvicorn.workers.UvicornWorker titiler.pgstac.main:app` command upstream's own Dockerfile uses. |

**Why not eoAPI's own `docker-compose.yml` verbatim?** eoAPI's (and titiler-pgstac's, and
stac-fastapi-pgstac's) own compose files all `build:` their app images **from a full monorepo
source checkout** — there's no published "just `docker pull`" image for the app layer, only for
`database` (the pgSTAC image). Vendoring/cloning those repos' build contexts would mean carrying
(and staying in sync with) someone else's source tree under `fsd/` — the opposite of "no fork of
the images." Installing the **same pinned PyPI packages** those images install, via a two-line
Dockerfile that runs their own unmodified entrypoint, gets the identical stock software with a
much smaller footprint and a version pin that's trivial to bump (spec 30 D-A: "no fork of the
images" — this reads that as "run the stock software," not "must literally reuse upstream's
Dockerfile"). Version pins are cross-checked for compatibility: `stac-fastapi.pgstac` and
`titiler.pgstac` both pin `pypgstac>=0.9.11,<0.10`, matching the `pgstac:v0.9.11` DB image.

## Services / ports (all bound to `127.0.0.1` only by default — see `.env.example`)

- `database` — Postgres/pgSTAC, `localhost:5439` (DSN: `postgresql://username:password@localhost:5439/postgis`).
- `stac` — the STAC API, `http://localhost:8081` (`POST /search`, collections, items).
- `raster` — titiler-pgstac, `http://localhost:8082` (`POST /mosaic/register`, `GET /mosaic/{searchid}/tiles/...`).

## Scripts

- `load_pgstac.py` — reads fsd's existing static STAC catalog (`catalog.json` tree), rewrites
  each output COG's asset `href` to the container-visible `/data/...` path, emits
  `collections.ndjson` + `items.ndjson`, and `pypgstac load`s both into `database`.
- `register_and_url.py` — registers a `collections=["fsd-inference"]` search against `raster`,
  bakes in the discrete crop-class colormap (reused from `demos/titiler_serve.build_colormap`),
  and prints the full XYZ template for curl / QGIS.
- `export_stac_geoparquet.py` (spec 30 Deliverable B, fsd-core-adjacent, not part of the Docker
  bring-up) — converts the same static catalog to a single `catalog.parquet`; documented as an
  alternate (not-yet-exercised) load path for pgSTAC in the runbook.

## Bring-up

See `../../runbooks/30-tier2-mini-mpc.md` for the full step-by-step (this is a summary):

`load_pgstac.py`/`register_and_url.py` import `fsd` itself (for `fsd.catalog.stac`,
`demos.titiler_serve.build_colormap`), so run them from a venv that has fsd installed — reuse
`.venv-serving` (Deliverable B's venv: `pip install -e ".[dev,serving]"`) and add the two extra
packages these scripts need on top:

```bash
cd fsd   # repo root
.venv-serving/bin/pip install "pypgstac[psycopg]==0.9.11" requests

cd demos/mini_mpc
cp .env.example .env   # adjust FSD_OUTPUTS_DIR if your outputs live elsewhere
docker compose up --build -d
# wait for `database` healthy, then (from fsd/ repo root, so `demos.*`/`fsd.*` import):
cd ../..
.venv-serving/bin/python demos/mini_mpc/load_pgstac.py \
    --stac-dir tests/outputs/demo_e2e/model_outputs/stac \
    --outputs-dir tests/outputs/demo_e2e/model_outputs/cells
.venv-serving/bin/python demos/mini_mpc/register_and_url.py
```

## Teardown

```bash
docker compose down        # keep the pgdata volume (./.pgdata) for a re-run
docker compose down -v     # or wipe it too
```
