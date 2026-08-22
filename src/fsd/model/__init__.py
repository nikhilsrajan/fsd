"""fsd model contract (spec 18): plug a model into fsd via a small ModelAdapter.

Public surface:
    ModelAdapter, BaseModelAdapter, Output  — the contract (adapter.py).
    apply_features, median_per_id            — the F1 chokepoint + F4 reducer (features.py).
    infer_datacube, run_local                — the inference engine (engine.py).
    bundle                                   — save/load the self-describing model bundle.
    verify_image                             — does an inference image run this bundle? (spec 45 D4)
    registry                                 — a resolvable name for a published bundle (spec 51)
"""

from fsd.model import bundle, registry
from fsd.model.adapter import BaseModelAdapter, ModelAdapter, Output
from fsd.model.engine import infer_datacube, infer_datacube_to_cog, run_local
from fsd.model.features import apply_features, median_per_id, resolve_aggregate
from fsd.model.verify_image import verify_image

load_bundle = bundle.load
save_bundle = bundle.save

__all__ = [
    "ModelAdapter",
    "BaseModelAdapter",
    "Output",
    "apply_features",
    "median_per_id",
    "resolve_aggregate",
    "infer_datacube",
    "infer_datacube_to_cog",
    "run_local",
    "bundle",
    "load_bundle",
    "save_bundle",
    "verify_image",
    "registry",
]
