"""The self-describing model **bundle** (spec 18, F5; see the bundle explainer).

A bundle is a folder carrying the three things fsd needs to run a model anywhere: the
**code** (an adapter class, referenced by a `module:attribute` import string), the
**artifact(s)** (weights, referenced by paths relative to the bundle), and the **spec**
(required bands, T, output dtype/nodata/names) — mirrored as plain text so fsd can validate a
run *without* importing the code or loading the model (model-free preflight).

    bundle/
      bundle.json     # manifest (below)
      rf.joblib       # artifact(s)

`save` derives the `module:attr` string from the adapter object automatically; `load` resolves
it back to a class, instantiates it, injects absolute artifact paths, and calls `.load()`.
Registration/push (to ACR/blob/a registry) is P6 — this is the local, loadable format it pins.
"""

from __future__ import annotations

import importlib
import json
import os

from fsd.storage import fs

__all__ = ["resolve_ref", "adapter_ref", "read_spec", "save", "load"]

BUNDLE_MANIFEST = "bundle.json"
BUNDLE_VERSION = 1

_SPEC_FIELDS = (
    "required_bands", "n_timestamps", "output_dtype", "output_nodata", "output_band_names",
)


def resolve_ref(ref: str):
    """`'crop_mapper.adapters:CropRF'` -> the `CropRF` class object (not an instance).

    An import path in `module:attribute` form (the setuptools entry-point / gunicorn
    convention). `module` must be importable (i.e. on `sys.path` — `pip install`ed).
    """
    module_path, sep, attr = ref.partition(":")
    if not sep or not attr:
        raise ValueError(f"adapter ref must be 'module:attribute', got {ref!r}")
    module = importlib.import_module(module_path)
    return getattr(module, attr)


def adapter_ref(adapter) -> str:
    """Derive the `module:attribute` string for an adapter instance/class."""
    cls = adapter if isinstance(adapter, type) else type(adapter)
    return f"{cls.__module__}:{cls.__qualname__}"


def _feature_descriptor(adapter) -> dict:
    """Human-readable provenance for the transform (the executable version is the code)."""
    seq = getattr(adapter, "feature_sequence", None)
    if seq is None:
        return {"kind": "callable", "steps": ["<adapter.features>"]}
    steps = [getattr(fn, "__name__", repr(fn)) for fn, _ in seq]
    return {"kind": "sequence", "steps": steps}


def _manifest_from_adapter(adapter, artifacts_rel: dict[str, str]) -> dict:
    manifest = {
        "fsd_bundle_version": BUNDLE_VERSION,
        "adapter": adapter_ref(adapter),
        "artifacts": artifacts_rel,
        "feature": _feature_descriptor(adapter),
    }
    for field in _SPEC_FIELDS:
        val = getattr(adapter, field, None)
        manifest[field] = list(val) if isinstance(val, (list, tuple)) else val
    return manifest


def read_spec(bundle_path: str) -> dict:
    """Read just `bundle.json` — the spec, with NO import/model-load (model-free preflight)."""
    with fs.open(os.path.join(str(bundle_path), BUNDLE_MANIFEST), "r") as f:
        return json.load(f)


def save(adapter, artifacts: dict[str, str], dst: str, *, overwrite: bool = True) -> str:
    """Write a bundle at `dst`: copy each artifact in, record its relative href, and dump the
    manifest read off `adapter`. Returns the bundle folder path. Storage-seam aware (blob later).

    `artifacts` maps a name -> a local source filepath, e.g. `{"model": "rf.joblib"}`.
    """
    dst = str(dst)
    fs.makedirs(dst)
    artifacts_rel: dict[str, str] = {}
    for name, src in artifacts.items():
        rel = os.path.basename(src)
        dst_path = os.path.join(dst, rel)
        if fs.exists(dst_path) and not overwrite:
            raise FileExistsError(dst_path)
        with open(src, "rb") as fsrc, fs.open(dst_path, "wb") as fdst:
            fdst.write(fsrc.read())
        artifacts_rel[name] = rel

    manifest = _manifest_from_adapter(adapter, artifacts_rel)
    with fs.open(os.path.join(dst, BUNDLE_MANIFEST), "w") as f:
        json.dump(manifest, f, indent=2)
    return dst


def load(bundle_path: str, *, validate: bool = True):
    """Turn a bundle folder back into a ready-to-use adapter.

    Resolves the adapter `module:attr` -> class, instantiates it, injects **absolute** artifact
    paths onto `adapter.artifacts`, (optionally) checks the class's declared spec matches the
    manifest (catches code/bundle drift), and calls `adapter.load()`.
    """
    bundle_path = str(bundle_path)
    manifest = read_spec(bundle_path)

    cls = resolve_ref(manifest["adapter"])
    adapter = cls()
    adapter.artifacts = {
        name: os.path.join(bundle_path, rel) for name, rel in manifest["artifacts"].items()
    }

    if validate:
        for field in _SPEC_FIELDS:
            declared = getattr(adapter, field, None)
            declared = list(declared) if isinstance(declared, (list, tuple)) else declared
            # Skip fields the class leaves UNSET (it defers them to the trained model / bundle):
            # None, an empty list, or n_timestamps==0 (the base default). This lets ONE adapter
            # class back models trained on different T without hardcoding it — the bundle is
            # authoritative. Fields the class *does* pin are still drift-checked.
            if declared is None or declared == [] or (field == "n_timestamps" and declared == 0):
                continue
            if manifest.get(field) is not None and declared != manifest[field]:
                raise ValueError(
                    f"bundle.json {field}={manifest[field]!r} disagrees with "
                    f"{manifest['adapter']}.{field}={declared!r} (code/bundle drift)."
                )

    adapter.load()
    return adapter
