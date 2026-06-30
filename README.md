# fsd

A small, clean toolkit to **fetch satellite tiles and build datacubes** for
geospatial ML. It is a clean-room rewrite that combines only the necessary parts
of the legacy `fetch_satdata`, `rsutils`, and `cdseutils` repos.

**v1 scope:** Sentinel-2 **L2A** from **CDSE** → per-geometry **datacubes** →
flattened **training arrays**. Model training/deployment live in `notebooks/`,
not in the core package.

> Status: **spec phase**. The design lives in [`specs/`](specs/). No
> implementation has been written yet — see `specs/00-overview.md` for the plan
> and open questions awaiting sign-off.

## Documents
- [`specs/`](specs/) — compartmentalized design specs (start at `00-overview.md`).
- [`DROPPED.md`](DROPPED.md) — what legacy capabilities were left out / deferred.
- [`CHANGES.md`](CHANGES.md) — how `fsd` differs from legacy for what's kept.

## Planned usage (from notebooks, once implemented)
```python
import fsd.sources.cdse
import fsd.workflows.create_datacube
import fsd.datacube.flatten
# download -> build datacubes -> flatten -> train (sklearn, in-notebook)
```
