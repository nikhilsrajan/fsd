---
status: current
summary: Close the gap between "the adapter imports" and a 299-cell fan-out — fsd.verify_adapter builds ONE real datacube on AML, lands it locally, and runs the adapter over it through the same code the cluster runs, so the output.tif can be eyeballed before bundling is trusted.
---

# Spec 48 — `fsd.verify_adapter`: one real cube, locally, before the fan-out

**Status: ✅ SIGNED OFF 2026-08-20 — NOT YET IMPLEMENTED.** Raised by the user 2026-08-20, from
the same AML e2e session that produced specs 45–47. **All six §7 questions were answered by the
user at sign-off**; Q1 (the name) was then reopened by the user and settled a second time — see
D1. §8's external cross-validation was run at sign-off and is complete: it confirmed §1's
taxonomy, validated D7's metric set with no gap, and its finding about pytest collection is what
retired the interim `test_adapter` name. Nothing in `src/` is touched yet.

> **The one sentence:** every gate fsd has today asks *"would the adapter import?"*; none asks
> *"does `predict` produce sensible output on real pixels?"* — and the first thing that does is a
> 299-cell cluster run.

---

## 1. The gap

fsd already has a ladder of pre-fan-out checks. Each one is real, and each stops short of the same
place.

| gate | where | what it actually proves |
|---|---|---|
| `bundle.save` refusals (#70/#71/#72, spec 45) | driver | the bundle is well-formed: the adapter sits at the top of `code/`, no embedded file imports an unembedded sibling |
| `_find_wheel` / `_wheel_has_spec44` (spec 45 D4, spec 47 D11) | driver | the *image* was built from an fsd that can read the bundle |
| `adapter_smoke` (spec 38 D11) | one AML node | the adapter **imports**, its artifact **loads**, and `predict` is **callable** — inside the real Environment |
| `verify_image` (spec 45) | driver + one node | orchestrates the above, ~40–380 s |
| **the fan-out** | N nodes | **the first time `predict` ever receives an array of real pixels** |

`adapter_smoke`'s own docstring is explicit that it carries "No pipeline logic". So the questions
it cannot answer are exactly the ones that make an adapter *wrong* rather than *broken*:

- does `feature_sequence` produce the band set `predict` expects, on a cube with **real** SCL
  masking, real nodata and real interpolation gaps?
- is `n_timestamps` right for this window — does the cube's `T` match what the adapter was trained
  against? (`compute_n_timestamps` is a driver-side helper the user calls **by hand** today;
  nothing checks the answer against a real cube.)
- does `predict` return the declared `output_dtype`, with values in the declared range?
- do the outputs *look* right — the fsd principle that raster ops get eyeballed in QGIS, not just
  unit-tested?

An adapter that fails any of these imports perfectly and smokes green.

### Why the existing local path is not the answer

`run_inference(runner="local", roi=…)` exists and would run the adapter locally. It is not a
substitute, for one reason: **local inference needs a local datacube, and building one needs the
imagery.** The archive lives on blob; the Austria ROI's imagery is 74 GB. A user cannot build a
cube on their laptop without first pulling granules they do not want. That is why the loop today
is "bundle it and dispatch 299 cells" — not laziness, but the absence of a cheap way to get **one
real cube** onto the laptop.

`create_training_data` already solves the analogous problem for *training* data: build on AML,
land the compact array locally (`export_folderpath`). Nothing does it for a **datacube**.

---

## 2. Scope

**In:** a way to (a) choose one grid cell from an ROI, (b) build **that one cell's datacube** on
AML, (c) land it locally, and (d) run a **bundle or live adapter** over it locally **through the
same code path the cluster runs**, producing the same artifacts (COG + STAC) plus a report the
user can act on.

**Out:** changing what a datacube is or how it is built; a new inference engine (the whole point
is reusing the existing one); model *training* (permanently the user's side); making the local run
a substitute for `verify_image` (D2 — they answer different questions and both stay); QGIS plugins
or any GUI (fsd emits files QGIS opens, spec 41 D2).

---

## 3. Decisions

### D1 — one new verb, `fsd.verify_adapter`, not a flag on `run_inference` [Q1: name chosen by the user]

`run_inference` already carries two modes (ROI and CSV) and four runners. A third mode meaning "do
one cell, land it, and tell me about it" would worsen an already-branchy preflight for a case that
is *pedagogically* separate: this is the step you run **once, before** you trust a bundle, and its
output is a **verdict**, not a map.

```python
report = fsd.verify_adapter(
    model,                                   # a live adapter OR a bundle path
    roi="...", catalog_filepath="...",
    startdate=..., enddate=..., mosaic_days=20, bands=[...],
    cell="476da24",                          # or None -> D3 picks one; "random" opt-in
    export_folderpath="./verify_adapter",      # where the cube + output land LOCALLY
    runner="aml", runner_kwargs={...},       # how the CUBE gets built
)
```

**The name took three passes, and the reasoning is worth keeping** (Q1):

1. the draft proposed **`dry_run`** — retired, because §8 confirmed `--dry-run` means *"show me
   what would happen, execute nothing"* everywhere it is established (`make -n`, `terraform plan`,
   `kubectl --dry-run`, Snakemake), and this verb runs a real build and a real inference;
2. **`test_adapter`** — retired, because pytest collects on *name*: any `test_*` callable is
   collected even when merely **imported** into a test module, so fsd's own
   `from fsd import test_adapter` would have produced a fixture error in a file containing no bug.
   That is fixable with `__test__ = False`, but it is a workaround for a name, not a reason for one;
3. **`adapter_smoke`** — considered and rejected on two independent grounds. It is **already taken**
   by `fsd.workflows.adapter_smoke` (spec 38 D11's node-side import check), and §8 established that
   a *smoke test* means end-to-end on tiny **synthetic** data proving only that formats hold —
   which is exactly what that existing module does, and exactly what this verb is not.

**`verify_adapter` is the repo's own convention.** `verify_image` already returns a
`_result.json`-shaped verdict rather than raising, and `fsd/model/__init__.py` describes it as
"does an inference image run this bundle?". The pair now reads as one family, and the name carries
no pytest hazard:

- `fsd.verify_adapter` — does this adapter **compute the right thing**? (local, real cube)
- `fsd.model.verify_image` — does this **image** run this bundle? (one node)

It stays a **top-level verb** rather than moving into `fsd.model`, because it is a step in the
user's workflow (`download` → `create_training_data` → `verify_adapter` → `run_inference`), not a
model-module utility.

### D2 — this does not replace `verify_image`, and the spec says so out loud

Spec 45 D5 **rejects `runner="local"` for image verification**, because the driver already has the
adapter's source on `sys.path` and its dependencies installed (ADR 0002), so a local pass is a
false positive *about the image*. That reasoning is correct and unchanged.

`verify_adapter` answers a **different question**: not "will this image run the adapter?" but "does this
adapter compute the right thing?". A local run is the *right* venue for that — the user can drop
into a debugger, inspect the array, and open the COG in QGIS. Both gates stay, and the docs place
them in order:

1. `verify_adapter` — is my adapter's **logic** right? (local, minutes, iterate here)
2. `verify_image` — will the **image** run it? (one node, ~40–380 s)
3. `run_inference` — the fan-out.

Stating this is load-bearing: without it, D1 reads as reopening a decision spec 45 deliberately
closed.

### D3 — cell selection: explicit id, else a deterministic pick, and always write `grids.geojson`

`fsd.grid.roi_to_s2_grids` already produces the cells, and `_run_inference_roi` already writes them
to `grids.geojson` for exactly this kind of inspection. `verify_adapter`:

- `cell="476da24"` → use it; raise `PreflightError` naming the available ids (bounded) if it is not
  in the ROI;
- `cell=None` → pick **deterministically** (largest in-window catalog coverage, tie-broken by id)
  and **print which cell and why**;
- `cell="random"` → opt-in random pick **which prints the chosen id**, so a run worth keeping can be
  pinned by pasting that id back as `cell=` (Q2, user, 2026-08-20);
- **always** writes `grids.geojson` next to the output and prints its path, so the QGIS route the
  user described is first-class: open it, pick an id, re-run with `cell=`.

**Deterministic by default, random by opt-in** (Q2, confirmed by the user). A run that picks a
different cell every time cannot be compared against its own previous result, and "it worked
yesterday" stops being a usable statement — so the default is reproducible. Largest-coverage also
fails *usefully*: an empty or half-empty cube is the commonest real defect, so picking the best cell
means a failure is the adapter's, not the cell's. `cell="random"` remains available for deliberately
sampling the ROI, and printing the id is what keeps it reproducible after the fact.

### D4 — the cube is built by the existing per-cell unit of work, unchanged

Building one cell is `fsd.workflows.task` — the same unit `create_datacube` fans out, dispatched
through the same runner seam with an `input.csv` of exactly one row. No new build path and no
"special" single-cell code. `runner="local"` is allowed and does the obvious thing (build from a
local catalog); `runner="aml"` is the case that matters and the one the docs lead with.

### D5 — landing is `storage.transfer`, and the local cube is a first-class artifact

The cube (`datacube.npy` + `metadata.pickle.npy`) is transferred to `export_folderpath` through the
storage seam, exactly as `create_training_data` lands its compact array. Two consequences worth
stating:

- the user keeps a **real cube on their laptop**, so the second and later iterations of an adapter
  need **no cluster at all** — `verify_adapter` with the cube already present skips straight to inference.
  This is what makes the loop tight enough to actually iterate in;
- that resume must key on the cube's **identity** (roi/window/bands/mosaic_days), not its mere
  existence. Spec 47 D1 is the precedent, and repeating that mistake here would be worse: a dry
  run's whole purpose is to be trusted.

### D6 — the local inference runs through `infer_only_task`, not a new code path

This is the user's stated requirement — *"a local run deploy using the subset of the exact code
which is used for aml batch scaled inference"* — and fsd already has the piece.
`fsd.workflows.infer_only_task` is the infer-a-pre-built-cube unit of work, the same one the
Snakemake infer-only runner and the AML shard drive through `fsd.model.engine`, and it already
takes a CSV of `datacube_filepath` / `output_filepath`.

So `verify_adapter`'s inference leg is: write a one-row `input.csv` and call `run_infer_only`. **No branch
anywhere may say "if verify_adapter".** If the local result and the cluster result can differ, the run
is worthless.

A live adapter is auto-saved to a temp bundle first (`_ensure_bundle`, as `run_inference` already
does) — so the run also exercises **bundling itself**, which is half of what the user asked to
test.

### D7 — the report is a `_result.json`-shaped verdict that names what it could NOT check

Returns the spec 24 shape (`{step, status, pass, metrics, expected, error}`), with metrics
answering §1's questions: cube shape, cube `T` vs the adapter's declared `n_timestamps`, the band
set after `feature_sequence` vs `required_bands`, output dtype vs `output_dtype`, output value
range, nodata fraction, and the paths of the cube, the COG and `grids.geojson`.

It must also state its own limits, in the return and in the docstring: this run says **nothing
about the image** (that is `verify_image`), **nothing about scale** (one cell is not 299), and
nothing about cells other than the one it ran. Spec 47 Part D's rule applies — caller misuse
raises; only statements about the *adapter* come back as `pass: False`.

**No flattened/feature array is written** (Q3, user, 2026-08-20 — the draft proposed one and the
user overturned it). The adapter is for **inference**; an inference output is the grid cell's
raster, and **`output.tif` is what gets checked**. Writing `features.npy` would add a second thing
to look at that no acceptance criterion depends on, and the metrics in this decision already carry
the post-`feature_sequence` band set — which is the part of the feature pipeline that actually
mismatches. Revisit only when a concrete need appears.

### D8 — outputs land where QGIS can open them, and the spec names the files

`export_folderpath/` gets: `datacube.npy` + `metadata.pickle.npy` (the cube), `output.tif` (the
COG), `grids.geojson` (all cells, for the QGIS pick), and `_result.json`. The printed summary ends
with the two paths worth opening. Per the user's standing principle — LLMs are unreliable on
GeoTIFFs, so raster output gets eyeballed in QGIS — the verdict is **assistive**, and the COG is the
actual deliverable.

---

## 4. Acceptance criteria

1. `fsd.verify_adapter(model, roi=…, cell="476da24", runner="aml", …)` builds exactly **one** datacube,
   dispatches exactly **one** AML job, and lands `datacube.npy` + `metadata.pickle.npy` locally.
2. `cell=None` picks deterministically: two runs over the same ROI/window pick the same cell, and
   the printed line names the cell and the reason.
3. `cell=` naming an id not in the ROI raises `PreflightError` listing available ids (bounded).
4. `grids.geojson` is always written and its path printed, whether or not `cell=` was given.
5. A second `verify_adapter` with the cube already local and the same roi/window/bands/mosaic_days
   **submits no job** and goes straight to inference; a *changed* window or band set is detected and
   refused rather than silently reusing the old cube (D5, spec 47 D1's precedent).
6. The inference leg calls `fsd.workflows.infer_only_task.run_infer_only` — asserted by test, with
   no `verify_adapter`-specific branch in `engine`, `infer_only_task` or `bundle`.
7. A **live adapter** is accepted and auto-saved to a bundle; the bundle it produces is the same one
   `run_inference` would use (asserted by comparing `bundle.read_spec`).
8. The returned dict is `_result.json`-shaped and carries: cube shape, cube `T`, adapter
   `n_timestamps`, post-`feature_sequence` band set, `required_bands`, output dtype, output value
   range, nodata fraction, and the cube/COG/grids paths.
9. A `T` mismatch between the cube and the adapter's `n_timestamps` comes back as `pass: False` with
   an `error` naming both numbers — it does not raise, and it does not pass.
10. `runner="local"` works end-to-end against a local catalog (the tutorial fixture), so the test
    suite covers the whole verb with no network (spec 36 D3 invariant 3).
11. The docstring and `docs/howto/bundle-your-model.md` place `verify_adapter` → `verify_image` →
    `run_inference` in order, and say what each does **not** check.
12. `pytest -q` and `ruff check src/ tests/ demos/ examples/` clean.
13. `cell="random"` prints the chosen id, and passing that id back as `cell=` reproduces the same
    cell (Q2).
14. **No** `features.npy` (or any flattened array) is written — the artifacts are exactly those in
    D8 (Q3).

---

## 5. Risks

- **A green `verify_adapter` reads as "ready to scale".** One cell is not 299: it says nothing about per-cell
  variance, cold starts, quota or the multi-CRS seam. D7 makes the return state this, but the docs
  must repeat it or the verb over-promises — the same failure mode spec 47 Part D fixed for
  `verify_image`.
- **The local cube ages.** A cube built once and reused for weeks will not reflect a changed catalog
  or a re-ingested archive. D5's identity check covers the *request*, not the *archive*. Related:
  #74 (a truncated download can be catalogued as complete).
- **`verify_adapter` becomes a fourth mode of `run_inference` by accretion.** If it grows a `cells=` list
  or an `roi=` fan-out, it *is* `run_inference` and should be deleted. The one-cell constraint is the
  design, not a limitation.
- **Adapter iteration on one cell overfits to that cell.** Mitigated by D3's largest-coverage pick
  (a *good* cell, so failures are the adapter's) — but a user who tunes until that cell looks right
  has tuned on n=1.

---

## 6. Alternatives considered

- **A flag on `run_inference` (`n_cells=1`).** Rejected: D1 — it worsens an already-branchy preflight,
  and the output is a verdict, not a map.
- **Extend `verify_image` to run one real cube.** Rejected: it would need the cube on the *node*,
  turning a ~40 s import check into a build+infer job, and it conflates "is the image right" with
  "is the adapter right" — the exact conflation D2 exists to prevent.
- **Ship a small committed datacube fixture and infer against that.** Rejected as insufficient: a
  fixture cannot carry the user's own ROI, window, bands or `mosaic_days`, which is where
  `n_timestamps` and band-set mismatches actually come from. (It remains right for the *test suite* —
  AC10 uses the tutorial fixture.)
- **Let the user download one cube by hand and call `infer_only_task` themselves.** Rejected: that is
  today's situation minus the documentation. The whole cost is knowing which cell, getting it built,
  and getting it down.

---

## 7. Questions at sign-off — ALL RESOLVED (user, 2026-08-20)

1. **[RESOLVED — user, 2026-08-20, after two reopenings]** **Verb name.** → **`fsd.verify_adapter`**. `dry_run` (draft) means "execute nothing" by established convention; `test_adapter` (interim) collides with pytest collection; `adapter_smoke` is already taken by `fsd.workflows.adapter_smoke` and means synthetic-data format checking. `verify_adapter` follows the repo's own `verify_image` precedent. Full reasoning in **D1**.
2. **[RESOLVED — user, 2026-08-20: default stands]** **Deterministic or random?** →
   **deterministic, with `cell="random"` opt-in that prints the chosen id so it can be pinned.**
   Folded into D3.
3. **[RESOLVED — user, 2026-08-20: default OVERTURNED]** **Save the flattened/feature array?** →
   **no.** *"The adapter is for inference. Inference output is the s2grid. `output.tif` is what we
   check to see if all is good. If this changes we shall get back later when it is required."*
   Folded into D7 and AC15.
4. **[RESOLVED — user, 2026-08-20: default stands]** **Refuse a bundle `verify_image` never
   passed?** → **no — print a reminder that `verify_image` is still required.** The point is to
   iterate on the adapter *before* paying for an image check.
5. **[RESOLVED — user, 2026-08-20: default stands]** **Where does the cube land?** → **an explicit
   `export_folderpath`, no hidden cache.**
6. **[RESOLVED — user, 2026-08-20: default stands]** **Is `runner="local"` first-class?** →
   **both supported, AML documented as the common case.**

---

## 8. Best-practice alignment / sources

Cross-validation run at sign-off (2026-08-20). It did three things: it **confirmed** §1's taxonomy
of what a "smoke" test is and is not, it **validated** D7's metric set against standard practice
without finding a gap, and it **retired one candidate name outright** (`test_adapter`, on the
pytest collision) while confirming a second was unusable (`adapter_smoke`, already taken and the
wrong word). The searches run were: pytest collection of imported `test_*` callables; TorchGeo /
rslearn single-tile predict flows; and ML-deployment terminology for pre-production checks on real
data (sanity check vs smoke test) including which output properties are conventionally asserted.

### External

- **[pytest — how to capture warnings](https://docs.pytest.org/en/stable/how-to/capture-warnings.html)**
  and **[pytest-dev/pytest #6154](https://github.com/pytest-dev/pytest/issues/6154)**: supplied
  **D1's rejection of `test_adapter`**. These establish (a) that pytest collects on *name* — a `test_*` function or
  `Test*` class is collected even when it was only **imported** into a test module, which is the
  exact shape of `from fsd import test_adapter`; and (b) that the documented escape hatch is
  setting **`__test__ = False`** on the object. Without this search the chosen verb name would have
  produced a fixture error in fsd's own suite, in a file containing no actual bug. This is the
  single highest-value finding of the cross-validation.
- **[MLOps Community — Smoke Testing for ML Pipelines](https://mlops.community/blog/smoke-testing-for-ml-pipelines)**:
  supplied the **vocabulary check that confirms §1's framing**. It defines a smoke test as running
  the pipeline end-to-end on **tiny, synthetic** data where "the goal isn't to prove the model is
  good — it's to prove the pipeline still runs and still respects its expected input and output
  formats." That is precisely and only what `adapter_smoke` does, so fsd's existing gate is
  correctly named — and it independently confirms that the gap this spec fills is a *different*
  category of check, not a better smoke test.
- **[Intuit Engineering — Automated Sanity Checks for ML Model Deployment](https://medium.com/intuit-engineering/how-to-streamline-ml-model-deployment-automated-sanity-checks-64a23166fdc5)**:
  supplied the **category this verb belongs to** — a *sanity check* is a set of tests run in a
  **pre-production environment on real data** to catch systematic errors before deployment. That is
  exactly `verify_adapter`'s job, and it is why D2's insistence that this does not replace
  `verify_image` is the standard split rather than an fsd quirk.
- The same two sources supplied **D7's validation**: schema/dtype checking, **value-range
  validation**, and **null/nodata counts** are all named as the conventional minimum for asserting
  an inference is sane. D7's metric set (output dtype vs declared `output_dtype`, output value
  range, nodata fraction, band set vs `required_bands`) maps onto that list with **no gap found** —
  so the metric set is adopted as-drafted rather than extended.
- **[TorchGeo — Introduction / inference tutorial](https://docs.torchgeo.org/en/stable/tutorials/torchgeo.html)**
  and **[PyTorch blog — Geospatial deep learning with TorchGeo](https://pytorch.org/blog/geospatial-deep-learning-with-torchgeo/)**:
  supplied the **shape check for D8**. TorchGeo's canonical end-to-end demonstration is gridded
  inference over **one Sentinel-2 scene**, saved as **a single GeoTIFF** to be looked at. So
  "one cell in, one COG out, open it and look" is the established teaching *and* validation unit in
  this field, not an fsd invention — which is what makes D8's artifact list (and Q3's decision that
  `output.tif` is the thing checked) the conventional choice.
- **Naming (`make -n`, `terraform plan`, `kubectl --dry-run`, Snakemake `--dry-run`)**: the
  established meaning of "dry run" is *show what would happen, execute nothing*. This verb executes
  a real build and a real inference. This retired the draft's `dry_run` name (Q1, D1).
- **[PEP 8](https://peps.python.org/pep-0008/)** plus the surveyed Python naming discussions:
  supplied the (negative) finding that `verify_` / `check_` / `validate_` are **not** crisply
  distinguished in general Python practice — the only clear signal is that a function returning a
  *report of issues* rather than raising is conventionally `validate_`/`verify_`, and that `test_`
  is the one prefix with a hard framework collision. Since external convention does not decide
  between the survivors, D1 falls back on **internal** consistency with `verify_image`, which is
  the stronger signal.

### Internal

- `src/fsd/workflows/adapter_smoke.py`: its docstring's own words — "No pipeline logic" — establish
  §1's central claim that the existing node-side gate proves importability and nothing about
  computed output. Load-bearing evidence for the entire spec.
- `src/fsd/workflows/infer_only_task.py`: supplied D6. It is already "infer one or more PRE-BUILT
  datacubes -> COG(s)", already the unit both the Snakemake infer-only runner and the AML shard
  drive through `fsd.model.engine`, and it already takes a CSV of
  `datacube_filepath`/`output_filepath` — exactly the interface a one-row run needs. This is what
  makes D6 a reuse rather than a new code path, and therefore what makes this verb's result
  trustworthy as a predictor of the cluster's.
- `src/fsd/workflows/task.py` + `infer_task.py`: established the build/infer split D4 relies on —
  `infer_task` is "a superset of `fsd.workflows.task`". A single-cell build is an existing unit with
  a one-row input, not new code.
- `specs/45-bundle-transparency-and-image-verification.md` D5: supplied D2's constraint. Its
  rejection of `runner="local"` for *image* verification is what forces this spec to state
  explicitly that it answers a different question, rather than appearing to reopen a closed one.
- `specs/38-inference-at-scale.md` D11, via `adapter_smoke`: the ~40–380 s one-node smoke cost in
  §1's table.
- `specs/47-driver-side-honesty.md` D1 + Part D: supplied D5's resume-identity requirement
  (existence is not identity) and D7's rule that caller misuse raises while only statements about
  the thing under test become `pass: False`.
- `src/fsd/api.py::_run_inference_roi`: already writes `grids.geojson` for inspection — D3 adopts
  that existing artifact rather than inventing a cell-listing format.
- `CLAUDE.md` "Geospatial principles" (the user's): "visual validation is essential … raster ops get
  eyeballed in QGIS, not just unit-tested" is the direct source of D8, and of the decision that the
  verdict is assistive rather than authoritative.
- `specs/23-e2e-austria-local-gate.md` + `AZURE_INFRA.md`: the 74 GB / 299-cell figures in §1 that
  make "just build it locally" untenable.

## 9. Implementation note

Per `CLAUDE.md`'s model split, implementation is a **Sonnet session at `/effort medium`** against
this spec once signed off. Suggested landing order:

0. **Cell selection + `grids.geojson`** (D3) — pure driver-side, no dispatch, fully testable offline.
   Lands the preflight and the error messages.
1. **The build + land legs** (D4/D5) — a one-row `input.csv` through the existing runner seam, then
   `storage.transfer`. The resume-identity check lands here.
2. **The inference leg** (D6) — the smallest piece, because it is a call into `run_infer_only`.
3. **The report** (D7/D8) — metrics, the printed summary, and the docs ordering in AC11.

Steps 0 and 3 are where the value is; 1 and 2 are plumbing over code that already exists.
