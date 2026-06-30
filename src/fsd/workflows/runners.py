"""Runner seam — execute the datacube task across many work-units.

Spec: specs/08-workflows.md, specs/10-storage-and-scale.md.

v1 backend: local (Snakemake). Phase 2 backend: azure-batch (dispatches the same
`fsd.workflows.task` CLI on pool VMs). Same interface; runner is swappable.
"""

from __future__ import annotations


def run_local(
    input_csv: str,
    *,
    cores: int,
    dry_run: bool = False,
    unlock: bool = False,
):
    """Local runner: drive the bundled Snakefile over input_csv rows."""
    raise NotImplementedError


# Phase 2 (not implemented in v1):
# def run_azure_batch(input_csv, *, pool_id, ...): ...
