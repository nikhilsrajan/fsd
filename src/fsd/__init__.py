"""fsd — fetch satellite tiles and build datacubes.

Clean rewrite combining the useful parts of the legacy fetch_satdata / rsutils /
cdseutils repos. v1 scope: Sentinel-2 L2A via CDSE -> per-geometry datacubes ->
flattened training arrays. See specs/ for the design.

High-level API (specs/16): `fsd.download`, `fsd.create_training_data` (+ `run_inference` /
`deploy` stubs). These are the verbs users call; the modules under fsd.* are the internals.
"""

from fsd import config
from fsd.api import (
    InferenceResult,
    PreflightError,
    TrainingData,
    compute_n_timestamps,
    create_training_data,
    deploy,
    download,
    flatten_training_data,
    run_inference,
    verify_adapter,
)
from fsd.model import BaseModelAdapter, ModelAdapter, Output, load_bundle, save_bundle

__version__ = "0.1.0"

__all__ = [
    "BaseModelAdapter",
    "InferenceResult",
    "ModelAdapter",
    "Output",
    "PreflightError",
    "TrainingData",
    "__version__",
    "compute_n_timestamps",
    "config",
    "create_training_data",
    "deploy",
    "download",
    "flatten_training_data",
    "load_bundle",
    "run_inference",
    "save_bundle",
    "verify_adapter",
]
