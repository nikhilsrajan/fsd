# fsd — domain glossary

The ubiquitous language for the fsd pipeline (download → datacube → flatten → inference at scale). A
glossary only: terms specific to this project, defined by what they *are*. Design lives in `specs/`,
decisions in `docs/adr/`, terminology gotchas also in `CLAUDE.md`.

## Model & packaging

**Bundle**:
A portable, self-describing folder — trained weights + a `module:attr` adapter code *reference* + the
model spec (bands, T, output dtype/nodata/names). fsd stages and loads it to run a model; it does **not**
contain the adapter code or its dependencies.
_Avoid_: model package, model artifact (overloaded).

**Manifest** (`bundle.json`):
The bundle's self-declaration: a `module:attr` adapter code reference, an `artifacts` map (name →
relative file path — the bundle's *table of contents*), and the model spec. Lets fsd list a bundle's
files and validate a run **without loading the model** (model-free preflight), and lets a node fetch
exactly the files the bundle names.
_Avoid_: index, metadata (too generic).

**Adapter** (`ModelAdapter`):
The user's class declaring required bands / T / output spec + the one feature transform + `load`/predict.
Referenced by a bundle; installed as a package in the inference Environment. Feature transform is run by
fsd at *both* training-data generation and inference (the anti-skew invariant).
_Avoid_: model (that's the weights), wrapper.

**Inference Environment** (a.k.a. inference image):
The AML Docker Environment a node runs inside = `fsd[azure,mpc]` + the user's adapter package + its
runtime deps. Built once per adapter version, referenced by name. Distinct from the generic datacube
build Environment.
_Avoid_: container (too generic), bundle (that's weights+reference, not the image).

## Grids & work units

**Grid cell** (a.k.a. S2 grid cell):
The ~5 km ROI subdivision on the S2-geometry grid (`fsd.grid.roi_to_s2_grids`), id like `165b09c`. One
grid cell = one inference datacube = one build+infer unit-of-work = one `output.tif`. See `CLAUDE.md` for
the MGRS-tile-vs-grid-cell distinction.
_Avoid_: bare "tile" (ambiguous with MGRS tile).

**MGRS tile** (a.k.a. satellite / Sentinel-2 tile):
The ~110 km source granule on the military MGRS grid, id like `T33UWP`. What fsd downloads and merges
across; catalog column `mgrs_tile`.
_Avoid_: bare "tile".

**Unit-of-work**:
The runner-dispatched task. For inference it is the per-cell **build-the-datacube-then-infer** step
(`workflows.infer_task`). The property that keeps "scale = swap the runner, not the code" honest.
_Avoid_: job (a job carries a *shard* of units, not one unit).

**Shard**:
A slice of the per-cell work list (`input.csv`) assigned to one node by `shard_units` (round-robin). One
shard = one AML job. Within a shard, cells are further grouped for bundle-load amortization.
_Avoid_: batch, partition (the shards *form* a partition; a shard is one slice of it).

**Run**:
One dispatched execution, identified by `run_id`, with all its inputs/outputs/telemetry laid out under
`<root>/runs/<run_id>/` (`shards/`, `_status/`, `_bundle/`).

**Reduce job**:
A dispatched unit that collapses MANY inputs into ONE output, run as a single node — the opposite shape
from a fan-out. The flatten reduce (`workflows.runners.run_aml_flatten`, spec 39 D3) reads every cube
named in `input.csv` and writes one training array; no `shard_units`, `n=1` always.
_Avoid_: shard (a shard is one slice of a fan-out; a reduce job is not sharded).

## Training data

**Label** (as a separable overlay):
The class assigned to a training polygon. **Separable from training-data generation** — the flattened
training array is keyed by per-pixel `id`; labels attach by joining on `id`, and can be re-derived
(combine classes, split/invent classes) across experiment iterations **without re-flattening**. Required
for model deploy / supervised training; **optional** when *generating* training data (you often download
+ flatten once, then iterate labels many times).
_Avoid_: target, y (fine in code, not the domain term).

## Control plane vs data plane

**Driver**:
The machine that orchestrates a run — tiles the ROI, runs `setup`, stages inputs, submits jobs,
aggregates `_status/*.json`, assembles the run-level STAC. Typically the operator's laptop on VPN.
Preflight and fan-in happen here.
_Avoid_: client, control node.

**Node**:
An AML cluster worker executing one shard's units, reading imagery/catalog/bundle from blob and writing
COGs + STAC items back to blob. Runs the *same* local orchestration a laptop runs — the runner is the
only thing that differs.
_Avoid_: worker (ambiguous), instance.

**Dispatcher**:
The `runners.run_aml*` function on the driver that shards a work list, submits one job per shard, waits,
and raises on any failure. The only place that knows about AML; the unit-of-work never does.
_Avoid_: runner (the *local* Snakemake orchestration is also a "runner"; the dispatcher is the *cloud*
one).

**Land-local**:
Bringing a run's compact output home to the operator's laptop after a cloud dispatch, via
`storage.transfer` (single-object, atomic) — never the raw inputs, only the small result (spec 39 D4:
the flatten reduce's `data.npy`/`coords.npy`/`ids.npy`/`metadata.pickle.npy`/`labels.npy?`). Keeps the
driver control-plane-only: it orchestrates and receives results, it does not pull bulk data over the WAN.
_Avoid_: download (ambiguous with `fsd.download`, the imagery-fetch verb).
