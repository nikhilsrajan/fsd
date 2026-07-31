# The default cube time axis is a calendar-interval median mosaic

**Status:** accepted (spec 15, signed off + implemented 2026-07-05)

**Context.** `flatten` and preflight require that datacubes built over the same `start`/`end`/
`mosaic_days` share an **identical `timestamps` axis**. Anchoring the mosaic per shape/tile produced
misaligned axes, so cubes from neighbouring grid cells could not be flattened or merged together.

**Decision.** The default mosaic is a **calendar interval anchored at the caller's dates**:
`T = ceil((end − start) / mosaic_days)`. Every cube over the same window therefore shares one
`timestamps` axis, independent of which observations fell in each cell.

**Considered options.** Per-shape / per-tile anchoring (each cube's axis derived from its own
observations). Rejected: neighbouring cubes get different axes, which breaks flatten and cross-cell
merge.

**Consequences.** Grid cells "don't leave seams at mosaic time" — cubes tile cleanly in time. It is
also what lets the pipeline **download only the MGRS tiles a given cell/window needs** rather than a
full stack, since the target axis is known up front. `flatten` depends on this invariant.
