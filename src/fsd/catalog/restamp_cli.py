"""Stamp/re-stamp a catalog Parquet file's collection-level `SourceDeclaration`
footer (spec 35 §6, `fsd-restamp-catalog`).

Every catalog written before spec 35 carries no stamp and will raise at build
time (spec 35 §5a). No re-download is needed -- only the catalog Parquet is
rewritten (read + re-write in place, through `fsd.storage`, so it works on any
backend: `abfss://`, `s3://`, ...); the imagery it points at is untouched.
Catalogs are KB-MB (one row per granule), so this is a sub-second operation.
`inspect_cli` is the genuinely footer-only counterpart -- it reads no row group.

Run as:  python -m fsd.catalog.restamp_cli <catalog.parquet> [--declaration s2_l2a] [--force]
"""

from __future__ import annotations

import argparse

from fsd.catalog import declaration as declaration_module
from fsd.catalog.declaration import S2_L2A_DECLARATION, SourceDeclaration
from fsd.storage import fs

# Convenience-only (spec 35 §1's rejected-alternatives note): NOT the persistence
# mechanism, just named declarations this CLI can stamp without the caller
# constructing a `SourceDeclaration` by hand.
DECLARATIONS: dict[str, SourceDeclaration] = {"s2_l2a": S2_L2A_DECLARATION}


def restamp_catalog(path: str, declaration_name: str = "s2_l2a", *, force: bool = False) -> None:
    """Stamp `path` with the named declaration. Idempotent (re-stamping with the
    same declaration is a no-op change in content); refuses to overwrite a
    *different* existing stamp unless `force=True`."""
    if declaration_name not in DECLARATIONS:
        raise ValueError(
            f"restamp_catalog: unknown declaration {declaration_name!r}; known: "
            f"{sorted(DECLARATIONS)}."
        )
    new_declaration = DECLARATIONS[declaration_name]

    gdf = fs.read_parquet(path)
    existing = declaration_module.from_attrs(gdf)
    if existing is not None and existing != new_declaration and not force:
        raise ValueError(
            f"restamp_catalog: {path!r} already carries a different stamp "
            f"({existing!r} != {new_declaration!r}); pass --force to overwrite."
        )
    declaration_module.to_attrs(gdf, new_declaration)
    fs.write_parquet(path, gdf)


def _parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="python -m fsd.catalog.restamp_cli",
        description="Stamp/re-stamp a catalog's collection-level SourceDeclaration (spec 35 §6).",
    )
    p.add_argument("catalog", help="catalog.parquet path (any fsd.storage URL)")
    p.add_argument("--declaration", default="s2_l2a", choices=sorted(DECLARATIONS),
                   help="the named declaration to stamp (default: s2_l2a)")
    p.add_argument("--force", action="store_true",
                   help="overwrite a differing existing stamp")
    return p.parse_args(argv)


def main(argv=None) -> None:
    args = _parse_args(argv)
    restamp_catalog(args.catalog, declaration_name=args.declaration, force=args.force)
    print(f"Stamped {args.catalog} with declaration={args.declaration!r}.")


if __name__ == "__main__":
    main()
