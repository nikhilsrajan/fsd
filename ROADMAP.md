# fsd — north-star, roadmap & model contract

> **Status: DRAFT for sign-off (2026-07-05).** This is the strategic umbrella doc: where
> fsd is going (the north-star), how we get there in small releases (the roadmap), and the
> **model contract** that lets project teams plug their own models into fsd. It feeds the
> numbered specs in `fsd/specs/` — decisions here graduate into specs before implementation.
> Infra ground-truth for the cloud phases lives in **`fsd/AZURE_INFRA.md`** (the `rise`
> project). Read `fsd/PROGRESS.md` for current build status.
>
> The F1–F5 decisions baked into §3 are **proposed**, pending the user's sign-off.

---

## 1. North-star — THE GOAL

A researcher developing a crop/land model for some region (say Afghanistan) can, with
minimal cloud setup:

1. `pip install fsd` (a GitHub link first; PyPI later).
2. **Create training data** from a list of known-label polygons (e.g. farm plots), possibly
   across different years / date ranges / mosaic intervals depending on the model: fsd
   downloads the satellite data → builds datacubes for those polygons → flattens them into
   training arrays. The user never has to think about "flattening."
3. **Train their own model** — sklearn, PyTorch, TensorFlow, anything. **fsd does not care.**
   Training stays permanently on the user's side.
4. **Write a small model adapter** (see §3): declare the feature transform, load the model,
   run predict, shape the output.
5. **Run inference at scale** by giving fsd a **region of interest + startdate + enddate +
   mosaic interval**: fsd tiles the ROI into S2-geometry grids, downloads the imagery,
   builds inference datacubes for each grid, runs the model over them, and writes the
   results as **COGs + a STAC catalog**. The user never has to think about "tiling the ROI."
6. **View outputs** as XYZ map tiles through a hosted TiTiler (infra-side, raapid).

**The invariant that makes this tractable:** every stage works **locally (Mode A)** *and*
**scaled on the cloud (Mode B/C)** with the **same code**. Cloud is a *backend*, never a
rewrite. This is the promise we protect at every step.

---

## 2. Organizing principles (the anti-rewrite frame)

### 2.1 Three usage modes
- **Mode A — fully local.** Laptop does everything: download → datacube → flatten → train →
  **inference/deploy**. This is fsd today (minus deploy). The escape hatch for
  Azure-hesitant colleagues; it never goes away.
- **Mode B — cloud data+compute, local control + local training.** The laptop is a *thin
  remote control*: it triggers download/datacube/flatten **in the cloud** (raw tiles never
  touch the laptop), then pulls back only the **compact flattened arrays** to train locally.
  Coherent precisely because flattened data is small.
- **Mode C — fully cloud inference.** Register model + adapter, trigger by ROI+dates, cloud
  fans out over S2 tiles, runs the model, writes COGs + STAC, TiTiler serves XYZ.

The "downloading raw data to a laptop defeats cloud speed-up" worry is really *Mode A data
locality with Mode C speed* — incoherent. Resolution: in Mode B you download the *flattened
result*, not the raw imagery.

### 2.2 Control plane vs data plane (data gravity)
The **driver** (control plane) is a thin, portable, authenticated *job submitter* — it can
run on a **laptop** (VPN + `az login`), the user's **VM**, an **AML job**, or later an
**Azure Function** ("lambda equivalent"). The **data plane** (download, datacube, flatten,
inference) is heavy and **must be cloud-colocated** (compute next to storage). Keeping the
driver thin is *why* "all three driver locations" is cheap to support.

### 2.3 Layers (swap backends without touching the core)
- **L0 — fsd core library**: pure pipeline functions. Cloud-agnostic; never imports Azure.
- **L1 — seams**: storage (fsspec, exists), runner (Snakemake exists → +Azure Batch), and a
  new **control/trigger seam** (submit-a-job, backend-agnostic).
- **L2 — deployment backends**: local, Azure Batch, later inference/deploy backends.
- **L3 — project contract**: the user-supplied **ModelAdapter** (§3).
- **L4 — product surfaces**: pip UX, config files, hosted TiTiler/STAC. fsd *produces* the
  STAC+COG; infra *hosts* the tiler.

### 2.4 Two datacube types, one builder
- **Training datacubes** — from known-label polygons → flatten → arrays.
- **Inference datacubes** — from S2 res-11 grids tiling an ROI → model → COG.

Same `build_datacube`; what differs is the *source of geometries* and *what happens after*.

### 2.5 Scope goes UP — high-level verbs hide the plumbing
Intended users shouldn't say "flatten" or "tile the ROI." fsd grows a high-level API (§4);
today's `flatten` / ROI-tiling / builder become its internals.

### 2.6 Preflight before the fan-out (fail cheap, before you pay)
Download + datacube creation are the **expensive, billable** operations. So fsd runs every
**cheaply-computable check up front** and **refuses to trigger** the heavy fan-out if any
fails — a "preflight." The goal: *know before you spend* whether a run can succeed. Checks
that cost nothing (no download) include:
- **`T` match** — inference `T = ceil((enddate-startdate)/mosaic_days)` (calendar mosaic)
  equals the model's `n_timestamps` (§3.3). This alone catches the most common deploy failure.
- **band availability** — `required_bands` are obtainable from the source.
- **ROI sanity** — non-empty, intersects the source's data coverage / catalog.
- **adapter loads** and declares a coherent, self-consistent spec (bands, output, T).
- **storage + credentials reachable** (blob writable, secrets present).

Preflight is a first-class product feature (users iterate on config safely) *and* a cost
guardrail (no surprise Batch bills for runs that were doomed at config time).

### 2.7 The five "get-it-right-early" surfaces (these gate specs)
A wrong early choice here forces broad rewrites, so each gets a deliberate spec **before**
we scale:
1. **Catalog format** → STAC (§6).
2. **Storage URI abstraction** → fsspec (good) + MSI/adlfs + GDAL-VSI auth (to prove).
3. **The model contract (ModelAdapter)** → §3.
4. **Runner / control-plane seam boundary** → `runner=local|batch` never leaks into the task CLI.
5. **Model-artifact packaging** → the model *bundle* (§3.4).

---

## 3. The model contract (L3 — `ModelAdapter`)

Extracted from the legacy `demo_02_model_train` + `model/demo_model_deploy.py`, generalized.

### 3.1 The anti-skew invariant
The **feature transform** (e.g. `mask_invalid_and_interpolate → compute NDVI/NDRE/GCVI/SAVI
→ remove raw bands`) appears **identically** in the legacy train and deploy code, copy-pasted
— a classic train/serve-skew trap. **Rule: exactly one feature-transform definition, run by
fsd in BOTH training-data-generation and inference.** [F1]

### 3.2 The interface (strawman)
```python
class ModelAdapter(Protocol):
    # --- declarations fsd reads to build compatible datacubes & outputs ---
    required_bands: list[str]            # e.g. ["B02","B03","B04","B05","B06","B07","B08","B11","B12"]
    n_timestamps: int                    # T — the number of mosaic windows the model was trained on.
                                         #     fsd DERIVES T from startdate/enddate/mosaic_days (calendar
                                         #     mosaic, spec 15) and requires an exact match. [contract = same T + bands]
    output_dtype: str                    # e.g. "uint8"
    output_nodata: int | float           # e.g. 255
    output_band_names: list[str]         # 1 name = categorical map; N = probabilities/regression

    # --- feature engineering: ONE definition, used at train AND inference [F1] ---
    feature_sequence: list[tuple[callable, dict]]        # fsd bands.modify vocabulary (primary)
    # def features(self, datacube, band_indices) -> (data, band_indices): ...   # arbitrary escape hatch

    # --- model lifecycle ---
    def load(self) -> None: ...                          # load artifact ONCE per worker
    def datacube_to_X(self, features, band_indices): ... # reshape features → model input
    def predict(self, X_chunk): ...                      # raw output; fsd owns the chunk loop [F2]
    def to_output(self, raw) -> "Output": ...            # → (bands, H, W) + dtype/nodata/names [F3]
```

**fsd owns** (both modes): datacube/array I/O via the storage seam; running `feature_sequence`;
the predict **chunking loop** (`predict_batch_size`, default = whole tile) [F2]; assembling
the output array into a **COG** using the datacube's `transform`/`crs`; and building the
**STAC catalog** over the outputs. **The user owns** only: the feature declaration, the
reshape, the model call, and the output shaping.

### 3.3 Requirements declaration + validation (preflight — see §2.7)
The model's input width is fixed at train time (e.g. RF sees `T×B`). **The contract is: same
`T` and same `bands`.** fsd **validates this before any download/build**:
- **`T` (timestamps):** thanks to spec-15 **calendar** mosaicing, `T` is a pure function of
  `startdate`/`enddate`/`mosaic_days` — `T = ceil((enddate - startdate) / mosaic_days)`
  (final window upper-inclusive). So fsd computes the inference `T` from the user's chosen
  dates/interval and checks `T == adapter.n_timestamps` **at config time, before a single
  tile is fetched.** (This is a concrete payoff of the calendar-mosaic decision.)
- **bands:** `adapter.required_bands` must be obtainable from the requested source.

A mismatch **refuses to trigger the run** with an explanatory error ("your startdate/enddate/
mosaic_days give T=18 but the model needs T=19") — never a silent reshape failure deep in a
fan-out after money has been spent on downloads.

**Honest asymmetry (surfaced, not prevented):** the demo trains on per-field *median* samples
[F4] but predicts per *pixel*. That's a legitimate modeling choice — fsd documents it, doesn't
block it.

### 3.4 The model bundle (packaging — surface #5)
For deploy, especially on cloud workers, the adapter **code** + model **artifact(s)** + the
**spec** (required bands, output spec, feature sequence) must travel together and be loadable
anywhere. fsd defines a self-describing **bundle** and can push/register it (later: to ACR /
blob / an AML-registry-like store). [F5: code-first — a Python class referenced by
import-path/entry-point in config; no no-code path early.]

### 3.5 Division of labor (summary)
| Concern | Owner |
|---|---|
| Feature engineering *definition* | user (declared) |
| Running the feature transform (train + inference) | **fsd** |
| Reshape features → model input | user (`datacube_to_X`) |
| Model load / predict | user (any framework) |
| Predict chunking/batching loop | **fsd** |
| Output → `(bands,H,W)` + dtype/nodata/names | user (`to_output`) |
| Array → COG (+ transform/crs) | **fsd** |
| STAC catalog of outputs | **fsd** |
| Training the model | user (permanent) |
| ROI → S2 tiles, download, datacube, flatten | **fsd** (hidden behind verbs) |

---

## 4. High-level user API (the new verbs — §2.5)

Sketch (signatures to be firmed in specs):
```python
fsd.create_training_data(
    label_polygons, dates, mosaic_days, bands,
    feature_sequence, aggregate=None,       # "median_per_id" | None | callable  [F4]
    runner="local", storage=...,            # runner + storage are seams (local|batch, local|blob)
) -> TrainingArrays                         # data/ids/labels/metadata  (hides flatten)

fsd.run_inference(
    roi, dates, mosaic_days, model_bundle,
    runner="local", storage=...,
) -> COGs + STAC catalog                    # hides ROI→S2 tiling, datacube build, COG/STAC

fsd.deploy(model_bundle, ...)               # register a bundle for scaled inference
```
`runner=` and `storage=` are the seams: the **same call** runs Mode A (local, local disk) or
Mode B/C (Batch, blob) by config alone — no code change.

**ROI → S2-grid tiling** (inside `run_inference(roi=…)`, **P0.75** — the tiling itself landed as
`fsd.grid`, spec 19) is a **port, not an invention** — the
legacy `rsutils.s2_grid_utils.get_s2_grids_gdf` already does it, and
`fetch_satdata/notebooks/demo_preparation.ipynb` pins the intended recipe:
1. `get_s2_grids_gdf(roi_geojson_4326, grid_size_km=5, scale_fact=1.1, res=None)` — map
   `grid_size_km`→S2 level (**5 km → res 11**, as in the legacy `100_random_grids`),
   `s2.polyfill` the ROI's **convex hull** at that level, keep cells that **intersect** the
   ROI, then **scale each cell by `scale_fact` (1.1 → 10 % overlap per side)** so adjacent
   grid cells don't leave seams at mosaic time.
2. `gpd.overlay(grids_gdf, roi_gdf)` — clip the scaled grids to the ROI → the per-cell
   geometries that feed datacube creation (each **grid cell** = one inference datacube = one
   **per-cell task**).
3. Deps: `s2` (`from s2 import s2`, gives `polyfill`) + `s2cell`. ✅ ported into `fsd/grid.py`
   (spec 19); consumed by the **P0.75** wrapper, not P4. Not needed for P0's `create_training_data`.

---

## 5. Roadmap — small, demoable releases

Each phase is a shippable release to show the team. **Infra-ask** flags where we must *propose*
a `raapid-infra` change to the admin (we never edit it ourselves).

| Phase | Ships | Demo | Infra-ask |
|---|---|---|---|
| **P0** | fsd pip-installable (GitHub); high-level verb *skeletons*; STAC-aligned catalog (§6) | `pip install fsd`, local download→datacube→flatten via `create_training_data` | none |
| **P0.5** | ✅ **DONE (spec 18, 2026-07-06)** — **ModelAdapter contract** + legacy train/deploy reimplemented on it, **fully local**. `src/fsd/model/` (adapter/features/engine/bundle), `run_inference` real, `create_training_data(adapter=…)`, self-describing bundle. | Mode A end-to-end: EuroCrops RF train → inference → COG + STAC, one plug-in adapter (`tests/manual/deploy.md`) | none |
| **P0.75** | ✅ **DONE (spec 21, 2026-07-07)** — **Local ROI inference verb (completes Mode A).** `run_inference(roi=…)` chains **tile the ROI (`fsd.grid.roi_to_s2_grids`) → build one datacube per grid cell → infer → COG + STAC (+ optional display merge)** in a single call, all local. The per-cell **build+infer** is one runner-dispatched unit-of-work (`workflows/infer_task.py` + Snakefile → **Batch swaps in at P4 unchanged**, not a second pool). `merge=True\|"reproject"` (strict vs lossy display merge). Imagery assumed present in the catalog — **inference never calls CDSE** (conserve quota, SO-6). *(`create_training_data(roi=…)` deferred — labelled field shapes need no ROI→cell tiling.)* | Mode A: one call turns an ROI GeoJSON into per-cell crop-class COGs (`tests/manual/roi_inference.md`) | none |
| **P0.9** | ✅ **DONE (spec 23, 2026-07-10)** — **Local-completeness gate + team run-book.** `demos/e2e_austria.py` runs the *whole* local pipeline on **fresh real CDSE data** (download → jp2→COG → datacube → flatten → train → bundle → ROI build+infer → COG/STAC/merged), a **reusable template** (swap `--roi/--train`), **cross-UTM-zone-safe** (`merge="reproject"` area-dominant/`merge_crs`). Adds **decomposed download timing** (transfer vs COG-convert) + a **throughput probe** (factor out link/VPN), the **`plan_download` guardrail** (missing imagery → actionable `fsd.download` plan; verbs never auto-fetch), and a **no-download `estimate_run`** (ETA for any region/window/bands). Doc: `demos/E2E_AUSTRIA.md`. | the go-to "how fsd runs locally" doc + trustworthy timings | none | 
| **P1** | Storage seam on Azure: adlfs/MSI read+write to the `rise` project storage; GDAL-VSI auth proven | build a datacube locally but I/O against `rise` blob (over VPN) | none (uses existing) |
| **P2** | Azure Batch runner for datacube fan-out (the runner seam) | N datacubes built across the autoscaled `rise` Batch pool | **quota bump; likely `max_tasks_per_node`** |
| **P3** | Thin control plane ("trigger from laptop"): submit-a-job UX + config files | Mode B: laptop triggers cloud build, pulls flattened arrays | none new |
| **P4** | **Inference at scale.** Dispatch the **per-cell** build+infer unit-of-work from P0.75 onto the **`rise` Batch pool** (reusing the P2 datacube-fan-out runner), I/O against blob. Algorithm unchanged — this phase is **only** the runner/dispatch swap (`runner=`/`storage=` config, no new pipeline code). | Mode C: the P0.75 ROI verb fanned out across Batch nodes | maybe scale `max_nodes` |
| **P5** | Output STAC + hosted TiTiler / XYZ | outputs viewable as web tiles | TiTiler hosting (infra) |
| **P6** | Deploy/registration UX; model-bundle push/register | one-command deploy of a bundle | model store (infra) |

**P0–P1 need zero infra changes** — pure de-risking, two team-visible releases before we're
ever blocked on someone else's `terraform apply`. The first infra proposal is P2 (Batch quota).

---

## 6. STAC decision — now, but deliberately thin

**Do it in P0, before Azure.** Rationale: the catalog format is surface #1 — it ripples into
inference outputs, cross-source catalogs (CDSE + future sources), and TiTiler (which expects
STAC). Deciding late = migrating data *and* rewriting the reader twice. It's cloud-agnostic and
locally testable, and there's a natural bridge (our catalog is GeoParquet; STAC has the
`stac-geoparquet` serialization; the legacy deploy notebook already builds a `pystac` catalog
of output COGs).

**Scope guard:** "our catalog is STAC-*valid* and round-trips to STAC Items" — **not** "we run
a STAC API server" (that's L4/infra/later). A tight spec will name exactly which STAC fields we
populate (`proj:epsg`, `proj:shape`, `proj:transform`, datetime, bbox, COG asset) and stop.
Applies to **both** the post-download catalog *and* the inference-output catalog (one catalog
abstraction).

---

## 7. Open questions / to-confirm

- **F1–F5 sign-off** (§3) — the proposed contract decisions.
- ~~`timestamp_contract` strictness~~ — **RESOLVED (2026-07-06): same `T` + same bands**;
  `T` derived from calendar params and checked in preflight before download (§2.6, §3.3).
- **Coupling of `TileCatalog`** to its current schema — determines how cheap the STAC move is.
- **Where the model bundle is stored/registered** on cloud (ACR? blob? AML registry?) — P6.
- **Multi-band feature vocab limits** — is `bands.modify` expressive enough, or is the callable
  escape hatch load-bearing from day one?
- Everything in `AZURE_INFRA.md` §7–§8 (Batch task granularity, driver host, GDAL-VSI auth,
  data layout, container image, idempotency at scale).

---

*Maintenance: update phase status as releases ship; fold each resolved decision into its
numbered spec. Cross-refs: `AZURE_INFRA.md` (infra), `PROGRESS.md` (build status),
`specs/` (signed-off designs).*
