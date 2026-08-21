---
status: current
summary: Re-run notebooks/e2e_austria_aml.ipynb on the specs 48+49 code — adds the fsd.verify_adapter gate before bundling, and exercises spec 49's build/flatten skips via RESUME_RUN. Two passes: one fresh, one resumed.
---

# Run-book 48 — e2e Austria AML, with `verify_adapter` and the spec 49 skips

> Spec 24: Claude does not run notebooks, downloads, or cluster jobs. You run these; paste back
> each step's `_result.json` (or the printed block the step names) and Claude diffs it against the
> success criteria below. **Do not paste logs** — paste the result blocks.

## Purpose

Prove, on the real cluster, that (1) `fsd.verify_adapter` catches adapter problems on one real
cube before the fan-out, and (2) spec 49's skips make a re-run cheap. The second pass is what
actually demonstrates spec 49 — the first pass has nothing to skip.

## Prerequisites

- venv `fsd/.venv`, extras `[dev,aml,mpc,azure,grid]`, VPN up, `az login` current.
- `notebooks/env.local.sh` filled in (the six values `_config.py` reads).
- **`00_build_images.ipynb` already run**, both images registered and *finished building*. Paste
  the two versions its Part C prints into cell 3 (`AZ_ENV_VERSION`, `AZ_INFER_ENV_VERSION`).
- fsd at `main` ≥ `126c75f` — the three spec-48 review fixes are required, in particular
  `verify_adapter(runner="aml")` building on blob. On an older commit step A4 fails on the node.

Confirm the code is current before starting:

```bash
cd fsd && git log --oneline -1 && .venv/bin/python -c "
import inspect, fsd
src = inspect.getsource(fsd.verify_adapter)
print('aml-root fix present:', '_verify_adapter' in src)
print('result.json written :', '_finish_verify_adapter' in src)"
```
- **PASS if:** both print `True`.

---

## Pass A — fresh run (`RESUME_RUN = None`)

### Step A1 — Setup cells (0–7)

Run every cell down to and including the `fsd.workflows.runners` probe.

- **Expect:** `RUN = demo-2026... (fresh)`, then `ROOT = abfss://...`, then `900` fields, then
  `has spec-47 code: True`.
- **PASS if:** `RUN` prints `(fresh)` and the fields count is 900.
- **RECORD:** the `RUN` value. **You need it for Pass B.** Copy it now.

### Step A2 — `create_training_data` (cell 8)

- **Expect:** `[download] ... assets missing; dispatching ...`, then `[setup] n/900 shapes`, then
  `[aml] run_id=... run_root=...` **before** any job submits, then `[aml] k/32 jobs terminal`.
  On a fresh run **there is nothing to skip** — `[build]` prints a dispatch line, not a skip line.
- **PASS if:** it completes without raising and `td.load()` works in cell 12.
- **~21 min** on the 2026-07-29 shape.
- **If it hangs:** the `run_root` line names the prefix — watch `_status/*.json` there from
  another shell. Ctrl-C on the driver does **not** cancel submitted AML jobs.
- **RECORD:**
  ```
  {"step":"A2_create_training_data","download_line":"<the [download] line>",
   "build_line":"<the [build] line, or 'none printed'>",
   "flatten_line":"<the [flatten] line, or 'none printed'>","wall_clock":"<mm:ss>"}
  ```

### Step A3 — Train (cells 9–15)

- **Expect:** `field-wise CV: 0.6x`-ish, then `demo_model/rf.joblib` written.
- **PASS if:** `model_fp` exists and CV is not NaN.

### Step A4 — **`verify_adapter`** (cells 16–19) ← the new gate

This is the step this run-book exists for. Cell 19 builds ONE cell's cube on AML, lands it here,
and runs your adapter over it through the same unit the cluster runs.

- **Expect, in order:**
  - `[verify_adapter] roi -> 299 grid cells; wrote ./demo_verify_adapter/<RUN>/grids.geojson`
  - `[verify_adapter] cell='...' picked deterministically (largest in-window catalog coverage: N
    intersecting tiles).` — the deterministic pick filters the catalog once per cell on the
    driver, so **allow it a minute or two of silence** before the AML job appears.
  - one `[aml]` job, then the metrics block, then
    `[verify_adapter] pass -- open ... in QGIS.`
- **PASS if:** `report["pass"]` is `True` **and** `cube_t == adapter_n_timestamps == 10` **and**
  `output_dtype == "uint8"`.
- **A `pass: False` here is a real finding about your adapter, not a broken run** — the verdict
  names both numbers. It does **not** raise; the `assert` in the cell is what stops the notebook.
- **THEN — the part that matters:** open `./demo_verify_adapter/<RUN>/output.tif` **in QGIS**
  alongside `grids.geojson`. The verdict is assistive; the raster is the deliverable. Check the
  class values look like crops and not noise, and that the cell is not mostly nodata.
- **RECORD:** paste `./demo_verify_adapter/<RUN>/_result.json` **verbatim** — it is written on
  every exit, pass or fail. Add one line: *does the tif look right in QGIS, yes/no.*

### Step A5 — Bundle + final checks (cells 20–23)

- **Expect:** `my_adapter:CropRF`, then `my_adapter:CropRF 10 ['B04', 'B08']`, and
  `carries its adapter: {'root': 'code', 'files': ['my_adapter.py']}`.
- **PASS if:** `n_timestamps` is exactly `10` and `code` lists `my_adapter.py`.

### Step A6 — Inference download + `verify_image` (cells 24–29)

- **Expect:** `[download] 0 of N assets missing; nothing to download` (the training leg already
  fetched these), then `verify_image` returning `pass: True` in ~40–380 s.
- **PASS if:** `vres["pass"]` is `True`.
- **If it raises `ValueError` about a missing `fsd-*.whl`:** your *call* is wrong, nothing was
  verified — re-run `00_build_images.ipynb` step 3. Do not delete the wheel from the build context.
- **RECORD:** `vres["metrics"]`.

### Step A7 — The fan-out (cell 30)

- **Expect:** `[collect]`, then `[merge] k/299 inputs`, then a count, the merged tif and the STAC
  catalog path. ~30 min historically.
- **PASS if:** `len(result.output_filepaths) == 299` and both paths are non-empty.
- **RECORD:**
  ```
  {"step":"A7_run_inference","n_outputs":0,"merged":"<path>","wall_clock":"<mm:ss>"}
  ```

---

## Pass B — resumed run (this is the spec 49 test)

**Two variables have to be pinned, not one.** Pinning only `RESUME_RUN` makes `[download]` skip
while the build and flatten legs still redo all 900 — which is exactly what happened on the first
attempt at this run-book (2026-08-21) and is now **#83**.

Restart the kernel and set both in cell 3:

```python
RESUME_RUN = "demo-2026...Z"   # <- the RUN from step A1: pins ROOT, i.e. the IMAGERY
TRAIN_RUN  = "train"           # <- pins the CUBE folder: {ROOT}/runs/train
```

**Why `TRAIN_RUN` exists.** `create_training_data`'s `run_folderpath` defaults to
`{root}/runs/{run_id}`, and `run_id` is a **fresh UTC timestamp on every call**. So by default
every re-run addresses cube paths that have never existed: the shortfall is always 900 of 900 and
no stamp can ever match. Worse, `_build_shortfall` prints nothing in the N-of-N case (a full
dispatch is not a skip), so it fails **silently** — you see a fan-out and no explanation. The
notebook now passes `run_folderpath=f"{ROOT}/runs/{TRAIN_RUN}"` explicitly.

**Pass A must have used the same `TRAIN_RUN`** for Pass B to have anything to skip. If Pass A ran
with the default timestamp folder, set `TRAIN_RUN` to that run's id (the `run_root` line in A2
names it: `.../runs/<id>`) to adopt the cubes it already built.

**Update (spec 50, 2026-08-21): the pin is no longer required.** `run_folderpath`'s default for
`runner="aml"` is now the plain stable name `{ROOT}/runs/train` (#83 fixed, D6) — the SAME string
`TRAIN_RUN = "train"` above already pinned by hand. The notebook can now drop the explicit
`run_folderpath=` line and rely on the default; `TRAIN_RUN` is kept here as an explicit override
(e.g. to run two training sets side by side under one `ROOT`), not because it is required to make
the skip reachable at all. A partial re-run also no longer redoes `setup` for cells whose cube
already exists — `setup` runs only for the missing shapes.

### Step B1 — Setup (cells 0–7)

- **PASS if:** `RUN = demo-... (resumed)` and it is the **same string** you recorded, **and**
  `cube folder = .../runs/<TRAIN_RUN>` names the folder whose cubes you expect to reuse.

### Step B2 — `create_training_data` again (cell 8) ← the point of Pass B

- **Expect three skip lines, and no AML job at all for download or build:**
  ```
  [download] 0 of N assets missing; nothing to download
  [build]    0 of 900 cubes missing; nothing to build
  ```
- **The flatten is the one exception, once.** `_flatten_stamp.json` did not exist before spec 49,
  so on the **first** resume the flatten leg **re-runs** and writes the stamp. That is expected.
  If you run Pass B a second time you should then see:
  ```
  [flatten]  arrays match the current 900 cubes; skipping
  ```
- **PASS if:** the `[build]` line says `0 of 900 ... nothing to build` **and** the whole cell
  returns in **well under 5 minutes** (versus ~21 min in A2), **and** `td.load()` in cell 12
  returns arrays of the same shape as Pass A.
- **FAIL and stop if:** `[build]` reports a non-zero shortfall on an unchanged request, **or
  prints no line at all and dispatches a fan-out** — the silent case means the shortfall was
  900 of 900, i.e. the cube folder is not the one you think it is (#83). Check the
  `cube folder =` line from B1 against the `run_root` in A2 before re-running.
- **RECORD:**
  ```
  {"step":"B2_resume","download_line":"...","build_line":"...","flatten_line":"...",
   "wall_clock":"<mm:ss>","td_load_shape":[0,0,0]}
  ```

### Step B3 — `verify_adapter` again (cell 19)

- **Expect:** `[verify_adapter] cube for cell='...' already landed at ... and matches this
  request; skipping the build.` — **no AML job**, straight to local inference.
- **PASS if:** no `[aml]` line appears and the cell returns in seconds.
- **RECORD:** the skip line, and the wall clock.

### Step B4 — optional: prove `overwrite=` still forces the work

Only if B2 passed. In cell 8, set `overwrite = "flatten"`, re-run **that cell only**.

- **Expect:** no `[flatten] ... skipping` line; the reduce runs again.
- **PASS if:** the flatten leg actually dispatches. Set it back to `False` afterwards.

---

## Success criteria

The run passes when **all** of:

1. A4's `_result.json` has `"pass": true` with `cube_t == adapter_n_timestamps == 10`, and the
   `output.tif` looks right in QGIS.
2. A7 produced 299 output COGs plus a merged tif and a STAC catalog.
3. B2 printed `[build] 0 of 900 cubes missing; nothing to build` and submitted no build job.
4. B3 printed the `verify_adapter` cube-resume line and submitted no job.
5. B2's wall clock is dramatically under A2's.

## Stop / observe

- Every long leg prints a live `label done/total (pct%) | rate | elapsed | eta` line.
- The `[aml] run_root=...` line names the prefix to watch `_status/*.json` under.
- **Ctrl-C on the driver does not cancel submitted AML jobs** — cancel those in the AML studio.

## Known rough edges you may hit

- **#76** — a truncated cube reads as "present", so spec 49's build skip would skip the row that
  would fix it. If a cube looks wrong, `overwrite="datacubes"` is the hammer.
- **#77** — cell 30's per-cell skip is still decided on the node, after dispatch. A 95%-complete
  re-run of the fan-out still starts ~299 tasks.
- **#83 — FIXED (spec 50 step 0, 2026-08-21).** `run_folderpath` no longer defaults to a fresh
  timestamp for `runner="aml"`; the default is now the stable `{ROOT}/runs/train`, the same string
  `TRAIN_RUN` pinned by hand. The explicit pin above is now an optional override, not a requirement.
- **A `verify_adapter` cube does not know which archive it came from** — the resume stamp covers
  the request, not `catalog_filepath`. This is why `export_folderpath` is keyed to `RUN`.
