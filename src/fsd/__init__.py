"""fsd — fetch satellite tiles and build datacubes.

Clean rewrite combining the useful parts of the legacy fetch_satdata / rsutils /
cdseutils repos. v1 scope: Sentinel-2 L2A via CDSE -> per-geometry datacubes ->
flattened training arrays. See specs/ for the design.
"""

__version__ = "0.0.1"
