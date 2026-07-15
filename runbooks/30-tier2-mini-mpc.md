# Run-book: spec 30 — Tier-2 mini-MPC (pgSTAC + stac-fastapi-pgstac + titiler-pgstac)

> Spec 24 template. A run-book is what Claude hands the user instead of running a
> pipeline/long/networked script itself. The user runs the commands (including all Docker
> commands — Claude never runs Docker) and pastes back each step's `_result.json` (+ a
> screenshot for step 6); Claude diffs it against the success criteria below.

## Handoff checklist (before starting a fresh session)
- [x] Claude has flushed durable state to `fsd/PROGRESS.md` (+ `MEMORY.md`).
- [ ] User ran `/handoff <goal>` when ready to run this.
- [ ] Fresh session started (not `/compact`); model/effort set for the verifying session
      (Opus/high to diff the pasted `_result.json`/screenshot against this doc).

## Purpose
Prove fsd's inference outputs load into a **stock** pgSTAC + stac-fastapi-pgstac + titiler-pgstac
stack and serve through the same **register → searchId → XYZ** flow MPC uses
(`../STACNOTATOR_DIGEST.md §3`, workspace root) — i.e. fsd is "just another MPC" to a tool like
STACNotator. See `specs/30-tier2-mini-mpc-validation.md` for the full design; `demos/mini_mpc/README.md`
for what's borrowed vs. locally built (and why — no published app-layer images exist upstream, so
the two app services install the pinned stock PyPI packages on a slim base rather than forking a
Dockerfile/source checkout).

## Prerequisites
- Docker + Docker Compose. **One-time cost:** pulling/building the mini-MPC images (a Python base
  image + `pip install`s — no satellite downloads). Recommend on wifi.
- The existing demo output `tests/outputs/demo_e2e/model_outputs/stac/` (the 300-item, spec-28-true-
  geometry STAC catalog) and `tests/outputs/demo_e2e/model_outputs/cells/` (the output COGs it
  references). If missing, re-run `demos/e2e_austria.py` + `demos/regen_output_stac.py` first
  (`demos/E2E_AUSTRIA.md`).
- A scratch venv with fsd + the extra deps this harness needs (Deliverable A's scripts import
  `fsd`/`demos.titiler_serve`, so reuse Deliverable B's `.venv-serving`):
  ```bash
  python3.11 -m venv .venv-serving   # skip if it already exists from spec 30 Deliverable B
  .venv-serving/bin/pip install -e ".[dev,serving]"
  .venv-serving/bin/pip install "pypgstac[psycopg]==0.9.11" requests
  ```
- (Step 6) QGIS, for the XYZ-layer visual check.
- (Step 7, optional stretch) STACNotator running locally per its own README.

All commands below run from the `fsd/` repo root unless a step says otherwise.

## Steps

### Step 1 — bring up the mini-MPC
```bash
cd demos/mini_mpc
cp -n .env.example .env   # adjust FSD_OUTPUTS_DIR if your outputs live elsewhere
docker compose up --build -d
docker compose ps          # wait until `database` is "healthy"
cd ../..
```
- **Expect:** three containers running (`fsd-mini-mpc-db`, `fsd-mini-mpc-stac`,
  `fsd-mini-mpc-raster`); `database` shows `healthy` in `docker compose ps`.
- **PASS if:** all three are `Up` (db `healthy`) within ~2 min of the images being built/pulled.
- **If it fails / hangs:** `docker compose logs stac raster` for the app containers (most likely
  cause: a port already in use — change the host-side port in `docker-compose.yml`, or a bad pin —
  compare the version in `dockerfiles/Dockerfile.*` against `demos/mini_mpc/README.md`'s table).
  Stop with `docker compose down` (resume-safe; `.pgdata` persists unless `-v`).

### Step 2 — load
```bash
.venv-serving/bin/python demos/mini_mpc/load_pgstac.py \
    --stac-dir tests/outputs/demo_e2e/model_outputs/stac \
    --outputs-dir tests/outputs/demo_e2e/model_outputs/cells \
    --result-json tests/outputs/demo_e2e/_result_30_load.json
```
- **Expect:** printed JSON with `"collections": 1, "items": 300`.
- **PASS if:** `_result_30_load.json`'s `pass` is `true` and `metrics == {"collections": 1, "items": 300}`.
- **If it fails:** a `ValueError` about an href "not under --outputs-dir" means `--outputs-dir`
  doesn't match `FSD_OUTPUTS_DIR` in `.env` — they **must** be the same folder (spec 30 A2, the
  one non-obvious wiring step). A connection error means `database` isn't ready yet — re-check
  step 1's healthcheck.

### Step 3 — STAC search (curl, scriptable)
```bash
curl -s -X POST http://127.0.0.1:8081/search \
    -H 'Content-Type: application/json' \
    -d '{"collections": ["fsd-inference"]}' -o /tmp/search_result.json

python3 -c "
import json
d = json.load(open('/tmp/search_result.json'))
feats = d.get('features', [])
geom = feats[0]['geometry']['coordinates'][0] if feats else []
xs = {p[0] for p in geom}; ys = {p[1] for p in geom}
result = {
    'step': 'stac-search', 'status': 'ok',
    'pass': len(feats) == 300 and len(xs) > 2 and len(ys) > 2,
    'metrics': {'searched_items': len(feats), 'geometry_is_polygon': len(xs) > 2 and len(ys) > 2},
    'expected': {'searched_items': 300, 'geometry_is_polygon': True}, 'error': None,
}
with open('tests/outputs/demo_e2e/_result_30_search.json', 'w') as f:
    json.dump(result, f, indent=2)
print(json.dumps(result, indent=2))
"
```
- **Expect:** `searched_items: 300`; the first item's ring has **more than 2** distinct x's and
  y's (a true polygon, not a box) — proves spec 28's true geometry survived ndjson → pgSTAC.
- **PASS if:** `_result_30_search.json`'s `pass` is `true`.
- **If it fails:** 0 items usually means step 2 didn't commit (re-check its `_result.json`); a
  4-corner axis-aligned geometry (`geometry_is_polygon: false`) would mean the ndjson wrote the
  raster bbox instead of the true footprint — a regression, flag it.

### Step 4 — register
```bash
.venv-serving/bin/python demos/mini_mpc/register_and_url.py \
    --result-json tests/outputs/demo_e2e/_result_30_register.json
```
- **Expect:** printed JSON with `"searchid_present": true` + the full XYZ template, e.g.
  `http://127.0.0.1:8082/searches/<id>/tiles/WebMercatorQuad/{z}/{x}/{y}.png?assets=output&colormap=...`.
- **PASS if:** `_result_30_register.json`'s `pass` is `true`. **Copy the printed XYZ template** —
  steps 5/6 need it (substitute a real `{z}/{x}/{y}` for step 5).
- **If it fails:** a 404/connection error means `raster` isn't up (check step 1); a 500 usually
  means the search body / collection id is wrong (`--collection-id` defaults to `fsd-inference`,
  matching step 2's load).

### Step 5 — tile render (curl)
```bash
# pick a z/x/y over Austria (Waldviertel) — e.g. zoom 13 around (14.9E, 48.7N):
curl -s -o /tmp/mini_mpc_tile.png -w '%{http_code} %{content_type} %{size_download}\n' \
    "<paste the XYZ template from step 4, substituting z=13 x=4437 y=2823>"

python3 -c "
import json, os
size = os.path.getsize('/tmp/mini_mpc_tile.png')
result = {
    'step': 'tile-render', 'status': 'ok', 'pass': size > 0,
    'metrics': {'tile_status': 200, 'tile_nonempty': size > 0},
    'expected': {'tile_status': 200, 'tile_nonempty': True}, 'error': None,
}
with open('tests/outputs/demo_e2e/_result_30_tile.json', 'w') as f:
    json.dump(result, f, indent=2)
print(json.dumps(result, indent=2))
"
```
- **Expect:** `200 image/png <nonzero size>`.
- **PASS if:** `_result_30_tile.json`'s `pass` is `true`.
- **If it fails:** a 500 with no `/data` bind-mount is the classic miss (re-check `.env`'s
  `FSD_OUTPUTS_DIR` == step 2's `--outputs-dir`, and that `docker compose up` picked it up —
  `docker compose up -d` again after editing `.env`); a 404 means the `z/x/y` you picked doesn't
  intersect the Austria ROI — widen the search or use QGIS (step 6) to find one visually first.

### Step 6 — QGIS visual (the user's principle)
1. QGIS → Layer → Add Layer → Add XYZ Layer → New → paste the XYZ template from step 4 (as-is,
   with the literal `{z}/{x}/{y}` placeholders) → Add.
2. Pan/zoom to Austria (Waldviertel, ~14.9E/48.7N).
- **PASS if:** the crop map renders in the **real discrete class colors** (not a smeared
  gradient), over the **true, non-boxy cell footprints** (visibly slanted/irregular polygons, not
  rectangles) — the Tier-2 payoff over Tier-1's single pre-styled COG.
- **Paste:** PASS/FAIL + a screenshot.

### Step 7 — (stretch) STACNotator in-app
1. Start STACNotator locally per its own README (`AUTH_PROVIDER=local`, `make dev-init && make dev-up`).
2. Add the local mini-MPC as a catalog/custom MPC-shaped source (the STAC API at
   `http://127.0.0.1:8081`, the tiler at `http://127.0.0.1:8082`) — may need a STACNotator
   config/PR since it isn't literally MPC's URL; **not gating** for "done" (spec 30 D-C).
3. Confirm register→searchId→XYZ works **in-app**.
- **Paste:** PASS/FAIL + a screenshot, or "not attempted" (fine — this step is optional).

### Stop
```bash
cd demos/mini_mpc
docker compose down        # keep ./.pgdata for a re-run
# docker compose down -v   # or wipe the DB too
```

## Success criteria (`_result.json` files + screenshot)
Steps 2–5 each write their own `_result_30_*.json` under `tests/outputs/demo_e2e/` (paths given
above). **Success (hard bar, spec 30 D-C) = steps 1–6 all PASS.** Step 7 is a bonus, not gating.

```json
{ "step": "load-pgstac", "status": "ok", "pass": true,
  "metrics": { "collections": 1, "items": 300 },
  "expected": { "collections": 1, "items": 300 }, "error": null }
```

## Stop / observe
- Progress: `docker compose ps` / `docker compose logs -f <service>` for the running stack;
  each Python script prints its own one-shot `_result.json` (no ongoing log noise).
- Abort: `docker compose down` at any time (the DB volume `./.pgdata` makes a re-`up` resume
  where you left off; `load_pgstac.py`'s `insert_mode=upsert` makes reloading idempotent).
