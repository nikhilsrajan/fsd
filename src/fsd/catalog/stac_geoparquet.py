"""stac-geoparquet export (spec 30 Deliverable B) — the #26 north-star catalog interchange.

Additive: a list of `pystac.Item` (e.g. from `catalog.stac.cog_outputs_to_items`) -> one compact
GeoParquet file via the **`stac-geoparquet`** library (optional `[serving]` extra, isolated here
like `grid.py` so the core `.venv` stays lean). Not wired into any default write path — the
full catalog-format migration (`run_inference` writing this instead of the JSON STAC catalog) is
the #26 follow-on.

Pinned API (installed `stac-geoparquet==0.8.1`, the source of truth per spec 29's rio-tiler note):
`stac_geoparquet.arrow.parse_stac_items_to_parquet(items, output_path=...)` takes
`Iterable[pystac.Item | dict]` and writes local GeoParquet directly (it opens `output_path` itself
via `pyarrow.parquet.ParquetWriter`, so there is no in-memory bytes handle to hand to
`fsd.storage`); `stac_geoparquet.arrow.stac_table_to_items(table)` is the inverse, yielding STAC
Item `dict`s from a `pyarrow.Table`/`RecordBatchReader` read off a GeoParquet file.

Both directions go through the `fsd.storage` seam by **staging a local tmp file**: the lib always
wants a real filesystem path, so we write/read that local path and `storage.put`/read-bytes it to
the (possibly remote) `dst_filepath`/`src_filepath` — the same stage-local pattern spec 29 used for
rio-tiler's COG reads.
"""

from __future__ import annotations

import io
import os
import tempfile

import pystac

from fsd.storage import fs


def items_to_stac_geoparquet(items: list[pystac.Item], dst_filepath: str) -> str:
    """Write `items` to a single GeoParquet file at `dst_filepath` (local or fsspec URL).

    Returns `dst_filepath`. Raises `ValueError` on an empty `items` (nothing to export — same
    contract as `catalog.stac.write_stac_catalog`).
    """
    if not items:
        raise ValueError("items_to_stac_geoparquet: no items to export.")

    from stac_geoparquet.arrow import parse_stac_items_to_parquet

    with tempfile.TemporaryDirectory() as tmpdir:
        local_fp = os.path.join(tmpdir, "catalog.parquet")
        parse_stac_items_to_parquet([it.to_dict() for it in items], output_path=local_fp)
        fs.put(local_fp, str(dst_filepath))
    return str(dst_filepath)


def stac_geoparquet_to_items(src_filepath: str) -> list[pystac.Item]:
    """Read a GeoParquet file at `src_filepath` (local or fsspec URL) back to `pystac.Item`s
    (the inverse of `items_to_stac_geoparquet`, for round-trip validation)."""
    import pyarrow.parquet as pq
    from stac_geoparquet.arrow import stac_table_to_items

    with fs.open(str(src_filepath), "rb") as f:
        table = pq.read_table(io.BytesIO(f.read()))
    return [pystac.Item.from_dict(d) for d in stac_table_to_items(table)]
