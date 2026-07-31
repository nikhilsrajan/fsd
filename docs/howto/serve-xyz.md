# How to: serve fsd output on an XYZ map viewer

> **Last verified:** 2026-07-31 @ `df98463` (spec 41 D5 tier 2 — "dated"). Re-verify after any
> change to `fsd.run_inference`'s STAC export (`fsd.catalog.stac`) or the mini-MPC serving stack in
> `demos/mini_mpc/`.

`fsd.run_inference` (see [`docs/tutorial.md`](../tutorial.md) §6 and
[`bundle-your-model.md`](bundle-your-model.md)) already produces standard artifacts — COGs +
a STAC catalog. **fsd builds no dashboard and no server of its own.** Serving is stock software
pointed at those artifacts; this page names two proven ways to do it and where the worked examples
live.

## Tier 1 — a single pre-styled XYZ URL (fastest, one output/merged COG)

Serve one COG (e.g. `run_inference`'s `merged_filepath`) directly as pre-styled XYZ tiles, with a
discrete colormap and nearest-neighbor resampling for categorical output. This is the simplest
integration and needs no database — good for a first look or a Bring-Your-Own-XYZ viewer slice.

Fully worked: [`runbooks/29-tier1-stacnotator-byo.md`](../../runbooks/29-tier1-stacnotator-byo.md)
(`.venv-titiler`, `demos/titiler_serve.py`; validated end-to-end against STACNotator's BYO-XYZ mode).
Two things that bite categorical rasters specifically: the colormap must stay **discrete** (a
continuous ramp smears class boundaries), and resampling must be **nearest**, never bilinear.

## Tier 2 — a real STAC API + tile server over many outputs

For serving a whole inference run (many cells, true per-cell geometry, register→searchId→XYZ like
MPC) rather than one flattened mosaic, load the STAC catalog into a **stock** pgSTAC +
stac-fastapi-pgstac + titiler-pgstac stack — the same shape MPC itself uses, so a tool built against
MPC's API (like STACNotator) treats fsd's output as "just another MPC".

Fully worked: [`runbooks/30-tier2-mini-mpc.md`](../../runbooks/30-tier2-mini-mpc.md) (Docker
Compose stack in `demos/mini_mpc/`; loads `run_inference`'s STAC catalog + output COGs, proves a
search → register → tile render round trip, and a QGIS/STACNotator visual check). Validated on the
300-item Austria run: true (non-boxy) per-cell footprints render correctly through the full stack.

**No Docker commands here or in that run-book are run by Claude** — Docker/Compose is handed to you
to run yourself, same as any other run-book (spec 24).

## Which tier for you

| | Tier 1 | Tier 2 |
|---|---|---|
| What it needs | one COG, a Python process | Docker, a Postgres+pgSTAC stack |
| What it serves | one pre-styled mosaic | a real STAC API over N items, per-item geometry |
| Good for | a first look, a BYO-XYZ viewer slice | production-shaped serving, "fsd looks like MPC" |

## Where to go next

- [`bundle-your-model.md`](bundle-your-model.md) — produce the COGs/STAC this page serves.
- [`run-at-scale.md`](run-at-scale.md) — produce hundreds of them instead of one.
