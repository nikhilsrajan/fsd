"""Satellite data sources. v1: CDSE only. See specs/01-sources.md.

OQ-3 decided: the source contract is a documented function signature (duck
typing), NOT an abstract base class. A "source" is any module exposing a
`download(...)` with the shape documented in `cdse.download`. Promote to an ABC
in `base.py` only when a second source actually exists.
"""
