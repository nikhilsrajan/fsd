# Spec 08 — Batch datacube workflow (Snakemake)

Folds in: `workflows/create_datacube.py`, `datacube/setup_datacube_run.py`,
`snakefiles/create_datacube_inmemory/Snakefile`.

## Responsibility

Build datacubes for **many** geometries in parallel, resumably — same UX as
`demo_01`'s `run_create_datacube(...)`. Structured as **task + runner seam** so the
*same* work runs locally now and on Azure Batch later (see `10-storage-and-scale.md`).

## Task / runner separation (the key structure)

- **`workflows/task.py`** — the unit-of-work: *build ONE datacube*. Pure,
  CLI-invokable (`python -m fsd.workflows.task <args>`), reads its inputs and writes
  its artifact via `fsd.storage`. Knows nothing about how it was scheduled. This is
  what Azure Batch will dispatch unchanged.
- **`workflows/runners.py`** — the runner seam: takes the list of work-units
  (`input.csv` rows) and executes the task across them. v1 backend: **local
  (Snakemake)**. Phase 2 backend: **azure-batch**. Same interface.
- **`workflows/create_datacube.py`** — high-level entrypoint: run *setup*, then
  hand the work-units to a chosen runner.

## Entry point (preserve signature shape)

```python
def run_create_datacube(
    catalog_filepath, timestamp_col,
    shapefilepath, id_col,
    run_folderpath,
    startdate, enddate,
    bands, scl_mask_classes, mosaic_days,
    csv_filepath, label_col,
    cores,
    dry_run=False, unlock=False, overwrite_setup_csv=True,
) -> CompletedProcess
```

## Two stages

1. **Setup** (`setup_datacube_run`): for each geometry, write a per-shape
   `geometry.geojson` + subset `catalog.geojson` (date+overlap filtered) into a run
   folder `{run}/{start}_{end}/{id}/`, and append a row to `input.csv` with columns
   `shapefilepath, startdate, enddate, catalog_filepath, export_folderpath,
   datacube_filepath, images_count, id[, label], mosaic_days, scl_mask_classes,
   bands`.
2. **Run** (via a runner): one work-unit per `input.csv` row → invokes
   `fsd.workflows.task` (which calls the builder, `03-datacube.md`). The **local
   runner** = Snakemake: `start.txt`/`done.txt` sentinels for resumability + a small
   deterministic jitter to stagger parallel starts.

## Packaging note
- Snakefile ships inside the package (`workflows/_snakefiles/...`) and is located
  via `importlib.resources` — mirror legacy `pyproject` `package-data`.

## Decisions / drops
- Snakemake is the **local runner only** (explicit decision); the task is
  runner-agnostic so Azure Batch (Phase 2) dispatches the same `python -m
  fsd.workflows.task ...` without Snakemake.
- Drop the unrelated snakefiles (`create_planet_datacube`,
  `create_masked_output_malawi`, `demo_model_deploy`, `create_s2l2a_datacube`
  legacy variant) — keep only the in-memory S2 datacube one.

## Tests
- `setup` produces correct `input.csv` + per-shape files for 2 geometries.
- `--dry-run` plans the expected number of jobs.
- (heavier, marked) end-to-end on tiny synthetic catalog.
