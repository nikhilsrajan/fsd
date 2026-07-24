# Spec 39 — create_training_data end-to-end on Azure ML: the flatten → land-local half

> **Status: 🚧 DRAFT — grilled 2026-07-24 (Opus@high, `/grill-with-docs`), awaiting final sign-off.**
> Design is settled across the five branches below; do **not** implement until the user signs off.
> This is the currently-missing half of "create training data on the cloud": the **build** fan-out is
> proven at scale (spec 36 / runbook 36), but the **flatten → single training array → landed on the
> user's laptop** half has never been run or specced. Cross-validated (numpy concat memory model; AML
> v2 single-node command job — §9, per-source credit). Baton: `runbooks/HANDOFF-flatten-training-data-spec.md`.
> Records **ADR-0020** (general-purpose images emit raw; the adapter transform runs only at
> model-specific endpoints).
>
> **Grill outcomes that shaped this spec (2026-07-24):**
> - **Q1 → driver-side feature transform, `features.npy` stays.** The feature transform already runs on
>   the driver today (`api.py:416→427`), not on any cluster node. Cluster images stay general-purpose
>   (flatten emits raw); `create_training_data` runs `_apply_training_features` on the driver after
>   land-local, unchanged. **ADR-0018, spec 18 F1, the Adapter glossary, and `eurocrops_rf.py` need no
>   revision.** (ADR-0020.)
> - **Q2 → local `export_folderpath` + blob `root` in `runner_kwargs`.** The verb auto-lands the compact
>   final array locally; the driver stays control-plane-only (ADR-0004) — cubes never come home.
> - **Q3 → accept an in-memory GeoDataFrame; the verb auto-stages it to the blob root** as the one
>   GeoJSON serving both the download ROI and the build shapefile.
> - **D-labels → `label_col` is optional.** Labels are a separable overlay joined via `ids.npy` and
>   re-derived across experiments without re-flattening (CONTEXT.md "Label").
> - **Q4 → prove with Phase 1 (flatten-reduce at 900, scale) + Phase 2 (small fresh e2e, composition);
>   no redundant full-scale Phase 3.**
>
> **Relationship to prior specs (all prerequisites, all landed):**
> - **Spec 05** built `datacube.flatten.flatten` (cubes → `(pixels,t,b)` per-pixel arrays via the
>   storage seam). **This spec adds no flatten pipeline** — it dispatches + lands it.
> - **Spec 15** (calendar mosaic) is the invariant flatten requires: all cubes over one
>   start/end/mosaic_days share one `timestamps` axis. Unchanged here.
> - **Spec 16** built the `api.*` verb façade. This spec **grows `create_training_data` into the
>   full-pipeline façade** and adds a sibling `flatten_training_data`.
> - **Spec 18 / ADR-0018** (ModelAdapter / F1 anti-skew) — **preserved unchanged** (Q1). The feature
>   transform still runs by fsd at both endpoints; ADR-0020 only pins *where* (the driver, never a
>   general-purpose node).
> - **Spec 36** built the AML dispatch machinery (`runners.run_aml`, `_aml_submit_and_wait`,
>   `shard_units`, the identity env var, the general-purpose Environment, `_status/*.json`). Reused:
>   a single-node "reduce" job for flatten, `n=1`, no fan-out.
> - **Spec 37** built `api.download(runner="aml")` + factored `_aml_submit_and_wait`/
>   `_aml_preflight_common` out of `run_aml`. **This spec's façade calls `api.download`** for its
>   download phase and reuses the shared submit/wait helper for the reduce.

---

## 1. The problem, stated honestly

The end-to-end demo pipeline is **download → datacube → flatten → train → inference**. Download-at-scale
(runbook 37) and datacube-build-at-scale (runbook 36) are proven, and spec 38 (inference at scale) is
merged. But inference needs a **trained bundle**, and the step that feeds training — turn the ~900
per-field datacubes already on blob into **one training array on the user's machine** — has never been
run. Two things are missing:

1. **A verb that flattens *already-built* blob cubes into one array and lands it locally, without
   rebuilding.** `api.create_training_data` always runs the build fan-out first — there is no "cubes
   exist, here's their `input.csv`, just flatten + bring it home" entry point. Runbook 36 Phase 3 left
   an `input.csv` on blob listing every cell's `datacube_filepath` + `id` + `label` — that df is
   *exactly* `flatten`'s input.
2. **A full one-verb end-to-end** (user, 2026-07-24): `create_training_data(label_polygons, dates,
   mosaic_days, bands, source="mpc", download=True, runner="aml")` → MPC download → datacube build →
   flatten → **array on the laptop**, in one call. Today `create_training_data` **does not download** —
   its preflight hard-fails if the catalog is missing ("run `fsd.download` first; spec 23 D13").

**The gap is orchestration + land-local, not flatten.** `datacube.flatten` already concatenates cubes
over the storage seam. This spec (a) lets flatten run **on the cluster** as a single-node reduce and
**transfers the compact result down**, keeping the driver control-plane-only, and (b) makes
`create_training_data` the one-verb façade that chains download → build → flatten → land-local.

---

## 2. Scope

**In scope**
- `create_training_data` grows an **optional download phase** (D1) — becomes the full-pipeline façade.
- A new sibling verb **`flatten_training_data`** (D5): flatten-only over an existing `input.csv` of blob
  cube paths; `runner="aml"` (cluster reduce + land-local) or `"local"` (read blob, write local).
- A **cluster flatten reduce job** (D3): `workflows/flatten.py` CLI + `runners.run_aml_flatten`, on the
  **general-purpose** fsd Environment (no adapter — ADR-0020/0002).
- **Land-local** (D4): after the reduce, transfer the compact array files blob → the local
  `export_folderpath` via `storage.transfer`.
- **`label_col` optional** (D-labels) in both verbs.
- **Feature transform stays fsd's, on the driver** (D2/ADR-0020): `create_training_data` keeps
  `adapter=` and emits `features.npy` — computed on the driver after land-local, exactly as today.
- Runbook `39-training-data-on-aml.md` (Phases 0–2, §6). ADR-0020.

**Out of scope**
- **Model training + metrics** — permanently user-side (ADR-0018 / CLAUDE.md). This spec ends at the
  **training array (+ optional `features.npy`) on the laptop**; train + metrics is a runbook/example
  step (step 2), not fsd.
- **A model-specific flatten image.** Flatten stays general-purpose (ADR-0020). The *inference* image
  is the only model-specific one (spec 38 / runbook 38).
- **Rebuilding the blob cubes.** DemoRF is retrained at the cubes' own `T` (D6) — no rebuild.
- **Fan-out flatten.** Flatten is a *reduce* (all cubes → one array); a single node is correct (D3).
- **Spec 18 / F1 / the Adapter glossary / `apply_feature_sequence` helper** — no change / not needed
  (Q1 made D2's earlier "drop features" idea moot).

---

## 3. Decisions

### D1 — `create_training_data` becomes the one-verb end-to-end façade (download → build → flatten → land-local)

Today (`api.py:299`) the verb is build-**then**-flatten and requires a pre-existing `catalog_filepath`.
It gains an **optional download phase**:

- **New params** (mirroring `api.download`): `source="mpc"` (demo default; anonymous, no creds),
  `download: bool = False`, `max_tiles`, `max_cloudcover`, `cog`, `creds` (only `source="cdse"`).
- **Behavior:** when `download=True`, the verb first calls **`api.download`** with `roi=label_polygons`
  into the catalog's `dst_folderpath`, then proceeds to build + flatten. When `download=False`
  (back-compat default), the existing "catalog must exist" preflight stands.
- **D13 is not violated.** The *build* step still reads only from the catalog — it never fetches from a
  provider. Download is a **separate orchestrated phase** the façade runs first (CLAUDE.md: "a
  high-level verb hides the plumbing"). The `create_datacube` "run `fsd.download` first" message is
  retained for the `download=False` path.
- **The blob-vs-local split (Q2).** For `runner="aml"`, `export_folderpath` is the **LOCAL** landing
  target; the **blob working root** comes from `runner_kwargs["root"]` (spec-36/37 convention) and holds
  the catalog, cubes, `input.csv`, and the raw reduce output. The verb **auto-lands** the compact array
  to `export_folderpath` (D4). `run_folderpath = export_folderpath/run` stays the default **only for
  `runner="local"`**.
- **Polygons as an in-memory GeoDataFrame (Q3).** For `runner="aml"`, `label_polygons` may be an
  in-memory `GeoDataFrame`; the verb **materializes it once to a GeoJSON under the blob `root`** and
  uses that single blob URL as **both** the download ROI **and** the per-cell build shapefile (both read
  it off blob via the seam — spec 37 `_roi_gdf` fix + spec 36 D6a). A path/URL `label_polygons` is used
  as-is. (`api.download`'s own aml path requires a URL; the façade is kinder and stages it for you.)
- **Runner threading:** `runner="aml"` dispatches download (spec 37), build (spec 36), and flatten (D3)
  each onto the cluster **sequentially** (a data dependency — flatten needs cubes built; the build
  dispatcher already raises on any failed shard, spec 36 D9, so flatten only runs if every cube exists).
  `runner_kwargs` (root/cluster/environment/identity) is shared across all three phases.

**Preflight order (fail-fast, before any cluster spend):** window/bands/columns/polygons → if
`download=True` resolve download preflight (source/creds/max_tiles) → else assert catalog exists.

### D2 — feature transform stays fsd's job, on the driver; general-purpose images emit raw (ADR-0020)

The feature transform **already runs on the driver** today (`create_training_data` calls `flatten`
then `_apply_training_features` in-process — `api.py:416→427`); no cluster node ever imports the adapter.
So the general-purpose-image constraint and the anti-skew invariant are **both** satisfied without
changing anything about features:

- **Cluster flatten (D3) emits raw** `data.npy` (+ `coords`/`ids`/`labels?`/`metadata`) — the flatten
  reduce runs on the **general-purpose** fsd Environment and never imports an adapter.
- **After land-local (D4)**, if an `adapter=`/`feature_sequence=` is passed, `create_training_data` runs
  `_apply_training_features` **on the driver** (the operator's laptop, which has the adapter installed)
  → emits `features.npy` locally, unchanged from today.
- **`create_training_data` keeps `adapter=`/`feature_sequence=`/`aggregate=`.** The only change is
  *where* the transform runs for `runner="aml"`: on the driver after land-local, not on a node.
- **F1 anti-skew is preserved by fsd** — the same adapter transform runs at training-data generation
  (driver) and inference (inference image). **Spec 18, ADR-0018, the Adapter glossary, and
  `eurocrops_rf.py` are unchanged.** See **ADR-0020**.

### D3 — cluster flatten is a single-node AML **reduce** job (keeps the driver control-plane-only)

Flatten concatenates **all** cubes into **one** array — a reduce, not a per-cell map. The cluster form
is **one command job on one node** (AML v2 default `instance_count=1`, §9) that reads every cube from
blob via the storage seam and writes the array to a **blob** export prefix. **Why on a node at all,
when the array is small?** To keep the **driver control-plane-only** (ADR-0004 / CONTEXT.md Driver): a
driver-side flatten would pull ~900 raw cubes over VPN — the source→relay antipattern spec 37 killed
for download. Only the compact *result* comes home (D4).

- New `workflows/flatten.py` — a thin in-job CLI: `--input-csv <blob url>` `--filepath-col` `--id-col`
  `--label-col` (optional) `--export <blob prefix>` `--nodata`. Reads the CSV (blob), calls
  `datacube.flatten.flatten(...)` unchanged. Mirrors `workflows/download.py`'s shape.
- New `runners.run_aml_flatten(input_csv, export_folderpath, *, id_col, label_col=None, filepath_col,
  cluster, environment, root, identity_client_id, ...)` — builds **one** `command(...)` job
  (`python -m fsd.workflows.flatten …`, `AZURE_CLIENT_ID` set) and submits via the shared
  **`_aml_submit_and_wait`** (spec 37). No `shard_units`. Reuses `_aml_preflight_common` + a small
  flatten preflight (input.csv exists + has the id col; `label_col` present only if requested).
- **Environment:** the **existing general-purpose fsd Environment** (spec 36) — flatten is pure `fsd`,
  no adapter, no new image (ADR-0020).
- **Loudness on a lost cube (ADR-0013):** the reduce reads every row of `input.csv`; a missing cube
  (a build that silently failed) makes `fs.load_npy` raise — it does **not** quietly drop the cube. In
  the e2e path this cannot happen (the build dispatcher raised already); for flatten-only over a
  user-supplied `input.csv` it is the correct fail-loud behavior.
- **Memory feasibility (single node):** `np.concatenate` allocates one new contiguous array and copies
  every input (§9), so peak ≈ Σ per-cube arrays + the result ≈ **2× the flattened total**. For the 900
  `AT_2018_TRAIN` fields (small cubes `(T=8,H,W,b=3)`), the flattened total is **~tens to low-hundreds
  of MB**, comfortably within one node's RAM. Phase 1 **records `data.npy` bytes** to replace the
  estimate with a measurement. **At P4/P5 scale (10⁴–10⁵ cells) revisit** (streaming/blocked concat or
  partial-reduce) — logged as a TODO, not built now (YAGNI).

### D4 — land-local: `storage.transfer` the compact array files from blob to the local `export_folderpath`

After the reduce writes to the **blob** export prefix, the driver copies the outputs to the **local**
`export_folderpath` so the verb returns with the array on the user's machine:

- Files: `data.npy`, `coords.npy`, `ids.npy`, `metadata.pickle.npy`, and `labels.npy` **iff present**
  (D-labels). These are the compact result — control-plane-appropriate to bring home; the raw cubes are
  not.
- `storage.transfer(src_blob_url, local_url)` **once per file** (single-object; `njobs` reserved).
  `transfer` is atomic (`.part` + rename) and provider-agnostic — a failed copy never leaves a truncated
  `.npy` (existence = "already landed", safe to re-run).
- `runner="local"` skips D4 — `datacube.flatten` already wrote straight to the local `export_folderpath`
  (reading cubes over the seam).
- **Driver-side features (D2)** run *after* land-local, reading/writing the now-local `export_folderpath`.

### D5 — `flatten_training_data`: the flatten-only sibling verb (over already-built blob cubes)

```python
def flatten_training_data(
    input_csv: str,                 # blob url of an input.csv (id, [label], datacube_filepath)
    export_folderpath: str,         # LOCAL destination for the array
    *,
    id_col: str = "id",
    label_col: str | None = None,   # optional (D-labels)
    filepath_col: str = "datacube_filepath",
    nodata: int = config.NODATA,
    adapter=None,                   # optional driver-side features (D2), like create_training_data
    feature_sequence=None,
    aggregate=None,
    runner: str = "local",          # "aml" = cluster reduce + land-local; "local" = read-blob-write-local
    runner_kwargs: dict | None = None,
    storage=None,
) -> TrainingData
```

- `runner="aml"`: dispatch the D3 reduce (array → blob prefix) → D4 land-local → (driver features if
  `adapter`). **This is the demo path** (Phase 1).
- `runner="local"`: call `datacube.flatten.flatten(...)` in-process (cubes stream over the seam, array
  written locally) → (driver features). KISS fallback for small/local cases.
- `create_training_data`'s flatten phase **calls this verb** over the build's `input.csv` (no
  duplicated reduce/land/features logic).
- Returns the same `TrainingData` handle (`n_pixels`, `n_timestamps`, `bands`, `feature_bands`).

### D6 — `T` is caller-set; no adapter/`n_timestamps` preflight

The window (`startdate`/`enddate`/`mosaic_days`) is whatever the caller passes; DemoRF is **retrained at
the resulting `T`** (T=8 for Apr–Sep 2018 @ 20-day mosaic — user, 2026-07-24). The handoff's
`n_timestamps=10` was a template bundle, not a constraint, so the adapter `n_timestamps` **preflight**
(`api.py:348-354`) is dropped (it presumed a fixed-shape adapter). The `required_bands` preflight can
stay (it is cheap and correct: features need their input bands present). The **calendar-mosaic
same-`timestamps` invariant still holds** — flatten raises if cubes disagree (`flatten.py:82`,
unchanged); it is a cross-cube consistency check, not a match against any model.

### D-labels — `label_col` is optional

`create_training_data` and `flatten_training_data` accept `label_col: str | None = None`. When omitted,
no `labels.npy`; per-pixel `ids.npy` is the join key. Labels are a **separable overlay** (CONTEXT.md
"Label") — the common workflow is download+flatten once, then iterate labels (combine/split/invent
classes) by joining on `id` **without re-flattening**. `datacube.flatten` already supports this
(`label_col: str | None`); the change is dropping the required-`label_col` preflight check
(`api.py:368-369` guards `id_col` only). `id_col` stays required.

### D7 — layout, idempotency, and the blob-cleanup gotcha

- **Blob intermediates (aml):** under `runner_kwargs["root"]` — download → `catalog.parquet` + cubes;
  build → `run/input.csv` + per-cell folders; flatten reduce → a sibling `run/_flatten/` prefix. D4
  lands the array under the **local** `export_folderpath`. Distinct prefixes so a re-run of one phase
  does not clobber another's inputs.
- **Idempotency:** `transfer`'s existence-check makes D4 re-runnable; the build phase skips-if-final-
  exists (spec 36 D7); `api.download` skips existing (append upserts + transfer existence-check). The
  reduce recomputes (cheap; overwriting one array).
- **Do not clear prefixes with `fs.rm(..., recursive=True)`** — deletes-then-raises on `abfss://`
  (TODO #50). Re-running is self-healing.

---

## 4. Reuse ledger (the "no new pipeline code" claim, checkable)

| component | change |
|---|---|
| `datacube/flatten.py::flatten` | **unchanged** — reduce (on-node) + local both call it as-is. |
| `api.download` | **unchanged** — called by the façade's download phase (D1). |
| `api.py::_apply_training_features`, `_apply_features` | **unchanged** — still run **on the driver** (D2), now *after* land-local for aml. Not moved, not promoted (no public helper needed — Q1). |
| `workflows/runners.py::_aml_submit_and_wait`, `_aml_preflight_common` | **reused unchanged** — `run_aml_flatten` (new) is built on them (spec 37 factored them out for this). |
| `workflows/runners.py::shard_units` | **not used** — flatten is a reduce, `n=1`. |
| `storage/fs.py::transfer` | **unchanged** — land-local (D4). Single-object, atomic. |
| `workflows/create_datacube.py::run_create_datacube` | **unchanged** — the build phase. |
| `raster/`, `bands/`, `catalog/`, `sources/`, `datacube/builder.py`, `fsd.model` | **untouched.** |
| `specs/18-*.md`, `examples/eurocrops_rf.py`, `CONTEXT.md` Adapter | **untouched** (Q1). |
| `api.py::create_training_data` | **changed** — download phase + blob/local split + gdf auto-stage (D1); `label_col` optional (D-labels); adapter `n_timestamps` preflight dropped (D6); flatten phase delegates to `flatten_training_data` (D5). Keeps `adapter`/`features.npy` (D2). |
| **new:** `api.py::flatten_training_data` (D5) | flatten-only verb. |
| **new:** `workflows/flatten.py` (D3) | in-job CLI. |
| **new:** `workflows/runners.py::run_aml_flatten` (D3) | single-node reduce dispatcher. |
| **new:** `api.py::_land_local(...)` helper (D4) | loops `storage.transfer`. |
| `azure-ai-ml` | still imported **lazily, only inside `runners.py`** (job build via `_import_aml_command`) — `import fsd` works without it. |

---

## 5. Deliverables

1. **`api.create_training_data`** — download phase + blob/local split + gdf auto-stage (D1); flatten
   delegated to `flatten_training_data` (D5); `label_col` optional (D-labels); adapter `n_timestamps`
   preflight dropped (D6); **`adapter`/`features.npy` kept, driver-side (D2)**. Back-compat:
   `download=False` default keeps catalog-must-exist behavior; existing adapter callers unaffected.
2. **`api.flatten_training_data`** (D5) — new flatten-only verb, `runner="aml"|"local"`, optional
   driver-side features.
3. **`workflows/flatten.py`** (D3) — in-job CLI.
4. **`workflows/runners.py::run_aml_flatten`** (D3) — single command job via `_aml_submit_and_wait`,
   `AZURE_CLIENT_ID`, reuses `_aml_preflight_common` + a flatten preflight.
5. **`api.py::_land_local`** (D4) — per-file `storage.transfer` of the compact array; wired into
   `flatten_training_data(runner="aml")`.
6. **Runbook** `runbooks/39-training-data-on-aml.md` — Phases 0–2 (§6). Operator-run.
7. **ADR-0020** (done, this session) + **`CONTEXT.md`** "Label" (done). Docs: `CHANGES.md`
   (create_training_data grows download / blob-local split / label optional; features move to
   driver-post-land for aml), `CONTEXT.md` (add "reduce job", "land-local"), `LIMITATIONS.md`
   (single-node reduce memory ceiling at 10⁴–10⁵ cells), `TODO.md` (streaming/partial-reduce at scale),
   `RECIPES.md` (flatten-only + full-e2e commands), `ROADMAP.md` (create-training-data-at-scale →
   partially done).

---

## 6. Runbook phases (`runbooks/39-training-data-on-aml.md`) — operator-run, straight to AML (Q4)

Per the working contract, Claude never runs networked/pipeline scripts — these are operator phases with
`_result.json` PASS/FAIL. No local-first e2e phase; no redundant full-scale Phase 3.

- **Phase 0 — preconditions.** Confirm on blob: the runbook-36 Phase-3 cubes + their `input.csv`
  (id/label/datacube_filepath) exist; the general-purpose fsd Environment + cluster + identity are the
  spec-36/37 ones. PASS: `fs.exists(input_csv)` and a sample cube reads.
- **Phase 1 — flatten-reduce over the existing 900 blob cubes → local** (`flatten_training_data(
  input_csv, export_folderpath=<LOCAL>, runner="aml", runner_kwargs={"root":…,"cluster":…,…})`). Proves
  the reduce + land-local **at scale**. PASS: **one** AML job (not 16); local `data.npy` shape
  `(pixels, 8, 3)`; `ids.npy` length == pixels; `labels.npy` present (input.csv has labels) and same
  length; `coords.npy` in EPSG:4326; **record `data.npy` bytes** (validates the D3 memory estimate).
  FAIL signature: `_check_metadata_consistency` raise → a cube with a different window slipped in.
- **Phase 2 — full one-verb e2e on a SMALL fresh subset** (`create_training_data(label_polygons=<a few
  AT_2018_TRAIN fields, in-memory gdf>, startdate, enddate, mosaic_days, bands=[B04,B08,B8A,SCL], id_col,
  source="mpc", download=True, runner="aml", runner_kwargs={"root":…,…}, export_folderpath=<LOCAL>)`). A
  small subset bounds MPC download cost while proving the **composition** the façade now owns. PASS:
  catalog + cubes appear under the blob `root`; local array lands; `T` == `compute_n_timestamps(start,
  end,mosaic_days)`; band count == requested − SCL (masked). Optional: pass `adapter=DemoRF()` → assert
  local `features.npy` written on the driver.

---

## 7. Tests (`tests/test_training_data_aml.py`) — no test requires Azure

AML client faked at the `run_aml_flatten` `ml_client=` boundary + `_import_aml_command` (spec-36
pattern); blob is `memory://`. Fast + synthetic.

1. **`flatten_training_data(runner="local")`** over synthetic cubes on `memory://` → `data.npy`
   (pixels,t,b), `ids`/`coords`/`metadata`; **`labels.npy` only when `label_col` given** (pins
   D-labels); **no `features.npy` unless `adapter=` given**.
2. **`run_aml_flatten` builds exactly ONE job** (not a fan-out) whose command carries `--input-csv`,
   `--export`, and `AZURE_CLIENT_ID`; submitted via the faked `_aml_submit_and_wait`. Non-vacuous:
   `n_jobs == 1` at both 1 and 900 input rows.
3. **Land-local (D4):** after the fake reduce writes the ~5 files to a `memory://` prefix, they appear
   at the local `export_folderpath`; `labels.npy` transferred iff present; a truncated `.part` never
   lands (atomicity).
4. **`create_training_data(download=True)`** orchestrates `api.download` → build → flatten **in order**
   (mock each): catalog created **before** the build reads it; `runner_kwargs` threads to all three; an
   in-memory gdf is staged to the blob `root` and that URL feeds both download-roi and build-shapefile
   (Q3).
5. **Driver-side features (D2):** `create_training_data(runner="aml", adapter=A)` — after a faked reduce
   + land-local, `features.npy` is written **locally** (the reduce output had none); no adapter reaches
   the faked job's `environment`/command (pins the general-purpose-image invariant, ADR-0020).
6. **D6:** a window whose `T` matches no model is accepted (no `n_timestamps` preflight); cubes
   disagreeing on `timestamps` still raise (invariant intact).
7. **`workflows/flatten.py` CLI** parses args, reads `input.csv`, calls `datacube.flatten.flatten`
   (mockable; no Azure).
8. **Non-vacuousness:** a deliberately-wrong expectation fails (asserting 2 jobs fails; asserting
   `features.npy` without an adapter fails).

Full suite stays green on a bare `pip install -e ".[dev]"` (no `[aml]`/`[azure]`), `ruff` clean.

---

## 8. Resolved decisions (was "open"; closed at the 2026-07-24 grill)

1. **Feature transform / `features.npy`** — kept, driver-side (Q1 / D2 / ADR-0020). *Not* dropped; spec
   18 unchanged.
2. **Blob-vs-local split** — local `export_folderpath`, blob `root` in `runner_kwargs`, auto-land (Q2 /
   D1 / D4).
3. **`label_polygons` form** — accept an in-memory gdf, auto-stage to the blob root (Q3 / D1).
4. **Labels** — `label_col` optional; `id` is the join key (D-labels).
5. **Proof scope** — Phase 1 (scale) + Phase 2 (composition), no Phase 3 (Q4 / §6).

**Still worth a glance at implementation time (not blockers):** the `run/_flatten/` prefix name
(cosmetic); whether `required_bands` preflight stays (recommended: yes, cheap); the small-subset size
for Phase 2 (operator's call, bound the MPC cost).

---

## 9. Best-practice alignment / sources

- **Single-node reduce is memory-feasible for the demo, not free at scale.** `np.concatenate` allocates
  **one new contiguous array and copies every input** — linear-time, memory-heavy; large concatenations
  make memory "soar" (numpy maintainers). *Contributed:* the D3 peak-memory model (≈ inputs + result ≈
  2×), the requirement to **measure `data.npy` bytes in Phase 1**, and the LIMITATIONS caveat that
  10⁴–10⁵ cells need a streaming/partial-reduce. Sources:
  [numpy/numpy#14597 "np.concatenate is super memory consuming"](https://github.com/numpy/numpy/issues/14597);
  [numpy/numpy#13279 "In-place numpy array concatenation?"](https://github.com/numpy/numpy/issues/13279)
  (confirms a new buffer is unavoidable — no in-place concat).
- **A flatten "reduce" is naturally one AML node.** An Azure ML v2 command job defaults to
  `instance_count = 1`. *Contributed:* D3's "one command job, not a fan-out" (`shard_units` unused) on
  the existing general-purpose Environment. Sources:
  [Azure ML — Create a training job with the Job Creation UI (default instance count = 1)](https://learn.microsoft.com/en-us/azure/machine-learning/how-to-train-with-ui?view=azureml-api-2);
  [CLI (v2) command job YAML schema — `resources.instance_count`](https://learn.microsoft.com/en-us/azure/machine-learning/reference-yaml-job-command?view=azureml-api-2).
- **Internal contracts (load-bearing):** `storage.transfer` is single-object + atomic (`.part` +
  rename), so D4 is a safe per-file loop (`fs.py:282`); the calendar-mosaic same-`timestamps` invariant
  flatten enforces is spec 15 / `flatten.py:82`; `_aml_submit_and_wait` / `_aml_preflight_common` were
  factored out for reuse in spec 37; the driver-stays-control-plane rule is ADR-0004 / CONTEXT.md.

---

## 10. What this spec deliberately does **not** change

- **`datacube.flatten.flatten`** — zero lines. The reduce wraps it.
- **The build fan-out (spec 36) and download (spec 37)** — reused as-is; the façade only *orchestrates*.
- **Spec 18 / F1 / ADR-0018 / the Adapter glossary / `eurocrops_rf.py`** — unchanged (Q1). The feature
  transform stays fsd's, at both endpoints; ADR-0020 only pins *where* (the driver, never a
  general-purpose node).
- **Model training** — stays user-side, permanently (ADR-0018). Spec 39 ends at the local array.
- **The inference image / spec 38** — untouched; it remains the one model-specific image.
