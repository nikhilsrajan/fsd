"""Census of rslearn's data-source classes -- the number behind the breadth argument.

`RSLEARN_SPIKE_REPORT.md` §3.1 claims rslearn ships **50 distinct concrete (module, class)
data-source entry points** against fsd's 2. That is the single most consequential number in
the case *for* Plan C, so it must be re-derivable rather than taken on trust.

This is **not** one of the run-book probes. It runs offline against the read-only `rslearn/`
checkout at the workspace root, needs nothing installed beyond the stdlib, and writes no
`_result.json` -- it just prints. Run it any time rslearn is bumped:

    python spike/probes/census_data_sources.py
    python spike/probes/census_data_sources.py --rslearn-root ../rslearn

## Method (stated so the number can be challenged)

Parse every module in `rslearn/data_sources/*.py` with `ast` -- no imports, so no torch, no
install. Resolve class bases transitively by name. Keep a class if it reaches `DataSource`
and is neither private (`_`-prefixed) nor one of the six abstract bases below.

Two honest caveats, both of which the report repeats:

  * Base resolution is **by name across the whole package**, not by import graph. Two unrelated
    classes sharing a name would be conflated. Checked at v0.1.13: the duplicated names
    (`Sentinel2` x5, `Sentinel1` x3, `LandsatOliTirs`, `Naip`, `Hls2S30`, `Hls2L30`) are all
    genuinely independent implementations of the same dataset, which is why the headline count
    is over **(module, class) pairs**, not over names.
  * "Concrete" here means *not abstract and not private*. It does not prove every class works;
    several need credentials (Planet, EarthDaily, GEE, Climate Data Store).
"""

from __future__ import annotations

import argparse
import ast
import collections
import pathlib
import sys

# The generic scaffolding in `data_sources/`, excluded from the concrete count. `DataSource`
# is the ABC; the next two are role mixins (`data_source.py:125,134`); `DirectMaterialize-
# DataSource` is the ingest-skipping base (`direct_materialize_data_source.py:26`); the two
# STAC ones are usable directly against an arbitrary STAC API but are bases for the MPC and
# Element84 sources, so counting them as products would double-count.
ABSTRACT_BASES = {
    "DataSource",
    "ItemLookupDataSource",
    "RetrieveItemDataSource",
    "DirectMaterializeDataSource",
    "StacDataSource",
    "AxisAlignedStacDataSource",
}


def _base_names(node: ast.ClassDef) -> set[str]:
    """The bare names of a class's bases, unwrapping `Generic[...]`-style subscripts."""
    names = set()
    for base in node.bases:
        if isinstance(base, ast.Name):
            names.add(base.id)
        elif isinstance(base, ast.Attribute):
            names.add(base.attr)
        elif isinstance(base, ast.Subscript):
            value = base.value
            names.add(value.id if isinstance(value, ast.Name) else getattr(value, "attr", "?"))
    return names


def census(data_sources_dir: pathlib.Path) -> dict:
    bases: dict[str, set[str]] = collections.defaultdict(set)
    modules: dict[str, set[str]] = collections.defaultdict(set)

    module_paths = sorted(data_sources_dir.glob("*.py"))
    for path in module_paths:
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                bases[node.name] |= _base_names(node)
                modules[node.name].add(path.name)

    def reaches_data_source(name: str, seen: frozenset[str] = frozenset()) -> bool:
        if name in seen:
            return False
        if name == "DataSource":
            return True
        return any(reaches_data_source(b, seen | {name}) for b in bases.get(name, ()))

    subclasses = [c for c in bases if reaches_data_source(c)]
    concrete = sorted(
        c for c in subclasses if c not in ABSTRACT_BASES and not c.startswith("_")
    )
    pairs = sorted((m, c) for c in concrete for m in modules[c])

    return {
        "modules": len(module_paths),
        "subclasses_incl_abstract": len(subclasses),
        "concrete_names": concrete,
        "pairs": pairs,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--rslearn-root",
        default="../rslearn",
        help=(
            "path to the read-only rslearn checkout. The default assumes you are in the fsd "
            "repo root, where `../rslearn` is the workspace's read-only checkout; pass it "
            "explicitly from a git worktree."
        ),
    )
    args = parser.parse_args()

    root = pathlib.Path(args.rslearn_root).expanduser().resolve()
    data_sources = root / "rslearn" / "data_sources"
    if not data_sources.is_dir():
        print(f"not found: {data_sources}", file=sys.stderr)
        return 2

    result = census(data_sources)
    print(f"rslearn root                          : {root}")
    print(f"modules in data_sources/              : {result['modules']}")
    print(f"classes reaching DataSource           : {result['subclasses_incl_abstract']}")
    print(f"concrete public names                 : {len(result['concrete_names'])}")
    print(f"concrete (module, class) entry points : {len(result['pairs'])}")
    print()
    for module, cls in result["pairs"]:
        print(f"  {module:42s} {cls}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
