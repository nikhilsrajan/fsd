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

> ## ⚠️ READ THIS FIRST — the stack must be UP for steps 2–6
> Step 1 (`docker compose up --build -d`) starts three long-running server containers (a
> database + two web APIs) **in the background** and returns immediately. Steps 2–6 are
> *clients* that talk to those servers over `localhost` — **they only work while the step-1
> stack is still running.** Do **not** run `docker compose down` (or quit Docker Desktop)
> until after step 6.
>
> **Two different working directories, don't mix them up:**
> - **`docker compose …` commands** (up/ps/logs/down) must be run from **`demos/mini_mpc/`**
>   — that's where `docker-compose.yml` lives, and `docker compose` only sees the stack when
>   run from that folder. Run it elsewhere and `docker compose ps` shows *nothing* (it's
>   looking at the wrong/empty project — a common confusion).
> - **The Python scripts** (`load_pgstac.py`, `register_and_url.py`) run from the **`fsd/`
>   repo root** (so `fsd`/`demos` import). They reach the servers via `127.0.0.1:PORT`
>   regardless of directory.
>
> New to Docker / don't know what `compose`, `--build`, `-d`, `ps`, or "reading the logs"
> mean? See **`../../MINI_MPC_NOTES.md`** (workspace root, outside the repo) — a plain-language
> primer + a running log of every issue hit on this harness.

## Steps

### Step 1 — bring up the mini-MPC
```bash
cd demos/mini_mpc
cp -n .env.example .env   # adjust FSD_OUTPUTS_DIR if your outputs live elsewhere
docker compose up --build -d    # builds images (first run / after a Dockerfile change), starts all 3 in the background
docker compose ps -a            # -a also shows crashed/exited containers — check ALL three
cd ../..
```
- **Expect (`docker compose ps -a`):** all three containers present and healthy —
  `fsd-mini-mpc-db` = `running (healthy)`, `fsd-mini-mpc-stac` = `running`,
  `fsd-mini-mpc-raster` = **`running`** (with a `127.0.0.1:8082->8082/tcp` port shown).
- **PASS if:** all three are `running` (db `healthy`) within ~2 min. **`raster` must say
  `running`, not `exited`** — if it exited, step 4/5 will get "Connection refused" on port 8082.
- **If a container shows `exited (…)`:** read *its* startup crash with
  `docker compose logs <service> --tail 60` (e.g. `docker compose logs raster --tail 60`). Look
  for the last Python `Traceback` / `ImportError` / "Worker failed to boot". Known issues + fixes
  are logged in `../../MINI_MPC_NOTES.md`. After changing a `dockerfiles/Dockerfile.*`, re-run
  `docker compose up --build -d` (the `--build` rebuilds; `.pgdata` + already-loaded data persist).
- **Other likely causes:** a host port already in use (change the host-side port in
  `docker-compose.yml`), or a bad version pin (compare `dockerfiles/Dockerfile.*` vs
  `demos/mini_mpc/README.md`'s table). Stop with `docker compose down` (resume-safe; `.pgdata`
  persists unless you add `-v`).

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
# Substitute a real z/x/y over Austria (Waldviertel) for the template's {z}/{x}/{y}
# — e.g. zoom 13 tile 4437/2819. THREE things that matter (see "If it fails" below):
#   1) wrap the WHOLE url in SINGLE quotes  2) add -g (--globoff)  3) no {} left in it.
curl -s -g --max-time 120 -o /tmp/mini_mpc_tile.png \
    -w '%{http_code} %{content_type} %{size_download}\n' \
    '<paste the XYZ template from step 4, with {z}/{x}/{y} replaced by 13/4437/2819>'

python3 -c "
import json, os
size = os.path.getsize('/tmp/mini_mpc_tile.png') if os.path.exists('/tmp/mini_mpc_tile.png') else 0
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
- **If it prints `000  0` and writes no file:** curl never sent the request — almost always its
  **URL globbing** choking on leftover `{` `}` braces (or an unquoted `&`). Fixes, all three
  together: (a) replace `{z}/{x}/{y}` with real numbers (e.g. `13/4437/2819`); (b) add `-g`
  (`--globoff`); (c) wrap the whole URL in **single** quotes. Re-run once without `-s` to see curl's
  own error (`curl: (3) …`). QGIS (step 6) works with the literal `{z}/{x}/{y}` because *it*
  substitutes them — curl does not.
- **If it fails otherwise:** a 500 with no `/data` bind-mount is the classic miss (re-check `.env`'s
  `FSD_OUTPUTS_DIR` == step 2's `--outputs-dir`, and that `docker compose up` picked it up —
  `docker compose up -d` again after editing `.env`); a 404/204/empty tile means the `z/x/y` you
  picked doesn't intersect the Austria ROI — use QGIS (step 6) to find a colored spot first, then
  pick a tile there. (Tiles are **slow** when zoomed out — titiler mosaics up to 300 COGs per tile
  on the fly; that's expected, see `../../MINI_MPC_NOTES.md`.)

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
