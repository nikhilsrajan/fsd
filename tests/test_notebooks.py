"""Guards for the one notebook this repo tracks.

`notebooks/00_build_images.ipynb` is the how-to for building the two AML node images, and
is deliberately public (`.gitignore` un-ignores it explicitly). Every other notebook stays
ignored precisely because notebooks leak: a saved output carries whatever the cell printed,
and cloud tooling prints subscription ids, tenant ids, workspace URLs and home directories
without being asked.

So the exception needs teeth. These tests are the reason the file can be tracked at all:

  * no saved outputs and no execution counts -- an executed notebook must be cleared before
    it is committed (Kernel > Restart & Clear All Outputs);
  * no identifiers in the source -- the private values come from the gitignored
    `env.local.sh` at run time, never from the file itself.

Synthetic and offline: this reads the checked-in JSON, it never runs a cell.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
TRACKED_NOTEBOOK = REPO_ROOT / "notebooks" / "00_build_images.ipynb"


def _cells():
    nb = json.loads(TRACKED_NOTEBOOK.read_text())
    return nb["cells"]


def _source() -> str:
    return "\n".join("".join(c["source"]) for c in _cells())


def _whole_file() -> str:
    """Source AND outputs, as raw JSON.

    The identifier scan deliberately covers both. Outputs are already banned outright by
    `test_no_saved_outputs`, but that makes the two tests overlap rather than depend on
    each other: if the outputs rule is ever relaxed, an identifier still cannot ride in.
    """
    return TRACKED_NOTEBOOK.read_text()


def test_the_tracked_notebook_exists():
    """If this fails the file was renamed or re-ignored — fix the guard with it, don't
    delete it, or the exception in `.gitignore` silently stops being enforced."""
    assert TRACKED_NOTEBOOK.exists(), f"{TRACKED_NOTEBOOK} is missing"


def test_no_saved_outputs():
    """An executed notebook must be cleared before commit.

    This is the leak that matters most: the cell that prints a Studio URL embeds the
    workspace's full ARM id — subscription included — in its output, and nothing about
    the source would tell you.
    """
    dirty = [
        i for i, c in enumerate(_cells())
        if c.get("cell_type") == "code"
        and (c.get("outputs") or c.get("execution_count") is not None)
    ]
    assert not dirty, (
        f"cells {dirty} carry saved outputs or execution counts. Run "
        "Kernel > Restart & Clear All Outputs, then re-commit."
    )


# Each pattern is a thing cloud tooling prints that must never be committed. Named
# rather than lumped together so a failure says which class of identifier leaked.
_FORBIDDEN = {
    "an Azure GUID (subscription / tenant / client id)":
        r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b",
    "an email address": r"\b[\w.+-]+@[\w-]+\.[\w.]{2,}\b",
    "a local home directory": r"/(?:Users|home)/[a-zA-Z0-9._-]+",
    "a storage account URL": r"abfss://|\.dfs\.core\.windows\.net|\.blob\.core\.windows\.net",
    "a concrete resource group or workspace name": r"\brg-[a-z0-9-]+|\bmlw-[a-z0-9-]+",
    "a concrete compute cluster name": r"\bcluster-[a-z0-9-]+",
}


@pytest.mark.parametrize("what, pattern", sorted(_FORBIDDEN.items()))
def test_file_carries_no_identifiers(what, pattern):
    """The notebook's private values come from `env.local.sh` at run time.

    Anything matching here has been baked into a public file — in a cell, or in an output.
    """
    hits = sorted(set(re.findall(pattern, _whole_file())))
    assert not hits, (
        f"notebooks/00_build_images.ipynb hardcodes {what}: {hits}. "
        "Read it from env.local.sh instead (see the 0.2 config cell)."
    )


def test_private_values_still_come_from_env_local():
    """The positive half of the rule above.

    Without this, deleting the `env_local()` plumbing and replacing it with literals would
    still pass every pattern check right up until someone filled in a real name.
    """
    src = _source()
    assert "env.local.sh" in src, "the config cell no longer references env.local.sh"
    for var in ("AZ_RG", "AZ_ML_WORKSPACE"):
        assert re.search(rf'{var}\s*=\s*need\(["\']{var}["\']', src), (
            f"{var} is no longer read from env.local.sh via need()"
        )
