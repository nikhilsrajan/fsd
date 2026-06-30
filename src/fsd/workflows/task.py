"""The unit-of-work: build ONE datacube. Runner-agnostic, CLI-invokable.

Spec: specs/08-workflows.md, specs/10-storage-and-scale.md.

This is what an Azure Batch task (Phase 2) dispatches unchanged. It must:
- read its inputs and write its artifact only via fsd.storage,
- know nothing about how it was scheduled.

Run as:  python -m fsd.workflows.task <args>
"""

from __future__ import annotations

import argparse


def run_task(input_row: dict) -> None:
    """Build one datacube from a single input.csv row (see setup in
    create_datacube). Thin wrapper over fsd.datacube.builder.build_datacube."""
    raise NotImplementedError


def _parse_args(argv=None) -> argparse.Namespace:
    raise NotImplementedError


def main(argv=None) -> None:
    raise NotImplementedError


if __name__ == "__main__":
    main()
