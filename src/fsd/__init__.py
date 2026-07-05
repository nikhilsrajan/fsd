"""fsd — fetch satellite tiles and build datacubes.

Clean rewrite combining the useful parts of the legacy fetch_satdata / rsutils /
cdseutils repos. v1 scope: Sentinel-2 L2A via CDSE -> per-geometry datacubes ->
flattened training arrays. See specs/ for the design.

High-level API (specs/16): `fsd.download`, `fsd.create_training_data` (+ `run_inference` /
`deploy` stubs). These are the verbs users call; the modules under fsd.* are the internals.
"""

from fsd.api import (
    PreflightError,
    TrainingData,
    compute_n_timestamps,
    create_training_data,
    deploy,
    download,
    run_inference,
)

__version__ = "0.1.0"

__all__ = [
    "PreflightError",
    "TrainingData",
    "compute_n_timestamps",
    "create_training_data",
    "deploy",
    "download",
    "run_inference",
    "__version__",
]
