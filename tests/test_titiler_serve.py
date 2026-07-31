"""Tests for the Tier-1 pre-styled XYZ demo server (spec 29). Pure; TestClient only, no real
uvicorn/network. Skips when the `[titiler]` extra (rio-tiler/fastapi/uvicorn) isn't installed —
run these from `.venv-titiler` (`pip install -e ".[titiler]"`).
"""

from __future__ import annotations

import json
import os
import sys

import pytest

pytest.importorskip("rio_tiler", reason="needs the [titiler] extra (rio-tiler/fastapi/uvicorn)")

_HERE = os.path.dirname(os.path.abspath(__file__))
_DEMOS = os.path.join(os.path.dirname(_HERE), "demos")
if _DEMOS not in sys.path:
    sys.path.insert(0, _DEMOS)

import titiler_serve  # noqa: E402

# --- colormap builder ---------------------------------------------------------

def test_build_colormap_from_class_colors_is_sorted_and_9_wide():
    cmap = titiler_serve.build_colormap()
    assert set(cmap) == set(range(9))
    assert 255 not in cmap
    class_colors = titiler_serve.load_class_colors()
    names = sorted(class_colors)
    assert cmap[0] == titiler_serve._hex_to_rgba(class_colors[names[0]])
    assert names[0] == "alfalfa_lucerne"
    assert cmap[8] == titiler_serve._hex_to_rgba(class_colors[names[8]])
    assert names[8] == "winter_common_soft_wheat"


def test_build_colormap_render_json_overrides_class_colors(tmp_path):
    render_fp = str(tmp_path / "render.json")
    with open(render_fp, "w") as f:
        json.dump([{"code": 0, "name": "custom", "color": "#010203"}], f)
    cmap = titiler_serve.build_colormap(render_fp)
    assert cmap == {0: (1, 2, 3, 255)}

    # a missing/absent path falls back to CLASS_COLORS.
    fallback = titiler_serve.build_colormap(str(tmp_path / "missing.json"))
    assert len(fallback) == 9


# --- tile render (TestClient) -------------------------------------------------

def _make_class_cog(fp, *, size=32, epsg=32633):
    import numpy as np
    import rasterio
    from rasterio.transform import from_origin

    data = np.zeros((1, size, size), dtype="uint8")
    data[:, : size // 2, :] = 3           # some class code
    data[:, size // 2 :, :] = 255         # nodata
    with rasterio.open(
        fp, "w", driver="GTiff", height=size, width=size, count=1, dtype="uint8",
        crs=f"EPSG:{epsg}", transform=from_origin(500000, 5200000, 10, 10), nodata=255,
    ) as dst:
        dst.write(data)


def test_tile_route_in_bounds_and_out_of_bounds(tmp_path):
    from fastapi.testclient import TestClient

    cog_fp = str(tmp_path / "merged.tif")
    _make_class_cog(cog_fp)
    app = titiler_serve.create_app(cog_fp)
    client = TestClient(app)

    # the native-zoom tile covering the COG (EPSG:32633, origin near 15E/47N) should render.
    # Origin header simulates a real cross-origin browser fetch (CORSMiddleware only stamps the
    # allow-origin header when a request actually carries one).
    resp = client.get("/cropmap/tiles/13/4437/2882.png", headers={"origin": "http://localhost:5173"})
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/png"
    assert len(resp.content) > 0
    assert resp.headers["access-control-allow-origin"] == "*"

    # a tile far from the data -> outside bounds -> a transparent (but still 200) PNG.
    resp2 = client.get("/cropmap/tiles/0/0/0.png")
    assert resp2.status_code == 200
    assert resp2.headers["content-type"] == "image/png"
    assert len(resp2.content) > 0


def test_create_app_missing_merged_raises(tmp_path):
    with pytest.raises(SystemExit, match="not found"):
        titiler_serve.create_app(str(tmp_path / "nope.tif"))
