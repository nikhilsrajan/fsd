# spike/rslearn — build-vs-borrow evaluation (Plan C)

> **This branch (`spike/rslearn`) only.** `main` continues **Plan B** (spec P0 on fsd's own
> pipeline). This branch evaluates **Plan C** (selective leverage of AllenAI's `rslearn` as a
> library underneath fsd's Azure runner + flatten/ModelAdapter). Motivation & options:
> `../RSLEARN_COMPARISON.md`. Do **not** do P0 spec work here; keep this branch focused on the
> benchmark so the final merge/keep decision is clean.

## Branch discipline
- **Isolated env:** all rslearn work uses a **separate venv `fsd/.venv-rslearn`** (gitignored).
  Never `pip install rslearn` into `fsd/.venv` — main must stay lean (numpy/rasterio/fsspec),
  and install weight is a benchmark metric (Q3).
- **Merge direction:** sync **main → this branch** periodically (absorb P0 progress, stay
  fresh). Only merge **this branch → main** if/when we decide to switch to Plan C.
- **Outputs:** benchmark artifacts under `fsd/tests/outputs/rslearn_spike/` (gitignored);
  committed deliverable = a report + this charter. Log reusable commands in `../RECIPES.md`.

## The questions to answer (from RSLEARN_COMPARISON.md §7)
1. **Acquisition:** can `rslearn.data_sources.copernicus.Sentinel2` (L2A) materialize into
   **`rise` Azure blob** (UPath/fsspec + MSI) and produce COG bands equivalent to fsd's CDSE
   download? (If yes → retire `sources/cdse`, inherit 30 sources + baseline-04.00 harmonization.)
2. **Datacube out, no Lightning:** can rslearn `materialize` + compositors (esp. the SCL
   cloud-aware / MEDIAN ones) yield a **plain numpy time-series datacube** that fsd's `flatten`
   + `ModelAdapter` consume — *without* dragging in torch/lightning?
3. **Install weight:** footprint / install time of `pip install rslearn` (and `[extra]`) for a
   Mode-A laptop user.

## Multi-end benchmark (not just "does it run")
Run rslearn and fsd on the **same ROI** (start with the EuroCrops set on `satellite_benchmark/`,
both UTM zones) and compare:
- **Output equivalence** — does rslearn's median/SCL mosaic match fsd's `datacube.npy` on the
  same bands/dates/mosaic window? (pixel-level diff)
- **Build time** — wall + per-stage, vs fsd's benchmark numbers.
- **Dependency weight** — venv size, install time, import time.
- **Code complexity** — LOC / config to get from geometries → numpy datacube.
- **Blob/MSI compatibility** — does the UPath/fsspec path write to `rise` cleanly (see
  `../AZURE_INFRA.md` for auth model).
- **Harmonization correctness** — rslearn applies the +1000 baseline-04.00 offset; confirm and
  compare against fsd's `sources/cdse` (a correctness item regardless of the decision).

## Verdict
On completion, write `spike/RSLEARN_SPIKE_REPORT.md` with the numbers and a go/no-go on Plan C.
Then either: merge → main (switch to C) or delete the branch (stay B). Record the call in
`../ROADMAP.md` and memory.
