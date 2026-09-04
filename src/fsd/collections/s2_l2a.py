"""The `sentinel-2-l2a` collection declaration -- the only one P1 ships.

Spec: specs/58-collection-agnostic-verbs.md.
"""

from __future__ import annotations

from fsd.catalog.declaration import S2_L2A_DECLARATION

COLLECTION_ID = "sentinel-2-l2a"

# The declaration itself is defined in `fsd.catalog.declaration` (not re-defined here) to
# avoid a declaration<->collections import cycle: `builder._resolve_declaration`'s
# hand-built-GeoDataFrame fallback needs a concrete S2 default without importing the
# registry package.
DECLARATION = S2_L2A_DECLARATION
