# COG vs JP2 — storage (spec 13)
_generated 2026-07-04T12:07:34.991758Z · first 4 months · 192 products_
Base COG = DEFLATE + PREDICTOR=2, tiled 512, **no overviews** (the build never reads overviews). The COG+overviews column is the *estimated* extra cost if these same files were also made XYZ-tiling-ready (e.g. for TiTiler) — measured from a sample, not materialised.

| band | JP2 (GiB) | base COG (GiB) | COG ratio | +overviews (GiB, est) |
|---|---|---|---|---|
| B04 | 13.72 | 17.09 | 1.25× | 23.66 |
| B08 | 14.32 | 17.32 | 1.21× | 24.09 |
| B8A | 3.90 | 4.82 | 1.23× | 6.53 |
| SCL | 0.18 | 0.14 | 0.76× | 0.21 |
| **total** | **32.13** | **39.37** | **1.225×** | **54.49** |

- **Base COG costs 1.225× the JP2 storage** (+23%). Overviews would add ~38.4% on top (tiling-only; the build can't use them).
- Extrapolated to the full year (×3): JP2 ≈ 96.38 GiB, base COG ≈ 118.11 GiB.
- **Lossless** (DEFLATE+PREDICTOR, NBITS=16 promotion): pixels are bit-identical.
