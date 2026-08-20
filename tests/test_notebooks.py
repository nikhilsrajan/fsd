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
NOTEBOOKS = REPO_ROOT / "notebooks"

# Every notebook `.gitignore` explicitly un-ignores. Add a name here in the same commit
# that un-ignores it, or it goes public unguarded.
TRACKED_NOTEBOOKS = ["00_build_images.ipynb"]


def _cells(name):
    return json.loads((NOTEBOOKS / name).read_text())["cells"]


def _source(name) -> str:
    return "\n".join("".join(c["source"]) for c in _cells(name))


def _whole_file(name) -> str:
    """Source AND outputs, as raw JSON.

    The identifier scan deliberately covers both. Outputs are already banned outright by
    `test_no_saved_outputs`, but that makes the two tests overlap rather than depend on
    each other: if the outputs rule is ever relaxed, an identifier still cannot ride in.
    """
    return (NOTEBOOKS / name).read_text()


@pytest.mark.parametrize("name", TRACKED_NOTEBOOKS)
def test_the_tracked_notebook_exists(name):
    """If this fails the file was renamed or re-ignored — fix the guard with it, don't
    delete it, or the exception in `.gitignore` silently stops being enforced."""
    assert (NOTEBOOKS / name).exists(), f"{NOTEBOOKS / name} is missing"


@pytest.mark.parametrize("name", TRACKED_NOTEBOOKS)
def test_no_saved_outputs(name):
    """An executed notebook must be cleared before commit.

    This is the leak that matters most: the cell that prints a Studio URL embeds the
    workspace's full ARM id — subscription included — in its output, and nothing about
    the source would tell you.
    """
    dirty = [
        i for i, c in enumerate(_cells(name))
        if c.get("cell_type") == "code"
        and (c.get("outputs") or c.get("execution_count") is not None)
    ]
    assert not dirty, (
        f"{name}: cells {dirty} carry saved outputs or execution counts. Run "
        "Kernel > Restart & Clear All Outputs, then re-commit."
    )


# Each pattern is a thing cloud tooling prints that must never be committed. Named
# rather than lumped together so a failure says which class of identifier leaked.
_FORBIDDEN = {
    "an Azure GUID (subscription / tenant / client id)":
        r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b",
    "an email address": r"\b[\w.+-]+@[\w-]+\.[\w.]{2,}\b",
    "a local home directory": r"/(?:Users|home)/[a-zA-Z0-9._-]+",
    # `abfss://` alone is a generic URL scheme and appears legitimately in prose and in
    # placeholder sample output (`run_root=abfss://.../runs/...`). What must never appear is
    # a CONCRETE storage host: a real container@account, or the account-bearing hostname.
    "a storage account URL": (
        r"abfss://[^\s./@]+@|\.dfs\.core\.windows\.net|\.blob\.core\.windows\.net"
    ),
    "a concrete resource group or workspace name": r"\brg-[a-z0-9-]+|\bmlw-[a-z0-9-]+",
    "a concrete compute cluster name": r"\bcluster-[a-z0-9-]+",
}


@pytest.mark.parametrize("name", TRACKED_NOTEBOOKS)
@pytest.mark.parametrize("what, pattern", sorted(_FORBIDDEN.items()))
def test_file_carries_no_identifiers(what, pattern, name):
    """The notebook's private values come from `env.local.sh` at run time.

    Anything matching here has been baked into a public file — in a cell, or in an output.
    """
    hits = sorted(set(re.findall(pattern, _whole_file(name))))
    assert not hits, (
        f"notebooks/{name} hardcodes {what}: {hits}. "
        "Read it from env.local.sh through _config.load() instead."
    )


@pytest.mark.parametrize("name", TRACKED_NOTEBOOKS)
def test_private_values_still_come_from_env_local(name):
    """The positive half of the rule above.

    Without this, deleting the `env_local()` plumbing and replacing it with literals would
    still pass every pattern check right up until someone filled in a real name.
    """
    src = _source(name)
    assert "_config" in src, f"{name} no longer goes through notebooks/_config.py"
    assert re.search(r"\bload\(", src), f"{name} no longer calls _config.load()"


# --- notebooks/_config.py ---------------------------------------------------------
# The module both tracked notebooks import to read `env.local.sh`. It is the single point
# where a private value enters a public notebook, so its parsing is worth pinning: the
# trailing-comment case below is not hypothetical — it shipped broken once and reported a
# fully filled-in file as empty.


@pytest.fixture
def config_mod():
    """Import `notebooks/_config.py` by path — `notebooks/` is not a package."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("_nb_config", NOTEBOOKS / "_config.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_config_parses_env_local_forms(config_mod, tmp_path):
    """Quoted, double-quoted and bare values, each with an optional trailing comment.

    `env.example.sh` writes every line as `export AZ_RG=''   # what it means`, so anchoring
    the value to end-of-line makes EVERY line fail to match.
    """
    f = tmp_path / "env.local.sh"
    f.write_text(
        "# a comment line\n"
        "export AZ_RG='my-rg'                 # resource group\n"
        'export AZ_ML_WORKSPACE="my-ws"       # workspace\n'
        "export AZ_CLUSTER=bare-value         # unquoted\n"
        "not an export line\n"
    )
    assert config_mod.env_local(f) == {
        "AZ_RG": "my-rg", "AZ_ML_WORKSPACE": "my-ws", "AZ_CLUSTER": "bare-value",
    }


def test_config_skips_empty_and_derived_values(config_mod, tmp_path):
    """An empty value must be *absent*, so `load()` reports it missing rather than handing a
    notebook a blank that fails somewhere further on. `$` entries are skipped so what a
    notebook uses is exactly what is visible in the file — no shell is ever run.
    """
    f = tmp_path / "env.local.sh"
    f.write_text(
        "export AZ_RG=''\n"
        'export AZ_DERIVED="${AZ_RG}/x"\n'
        'export AZ_FROM_CMD="$(az account show --query id -o tsv)"\n'
        "export AZ_REAL='kept'\n"
    )
    assert config_mod.env_local(f) == {"AZ_REAL": "kept"}


def test_config_load_reports_every_missing_name_at_once(config_mod, tmp_path):
    """Filling one blank, re-running a cell, and being told about the next is a bad loop."""
    f = tmp_path / "env.local.sh"
    f.write_text("export AZ_RG='set'\n")
    with pytest.raises(KeyError) as exc:
        config_mod.load("AZ_RG", "AZ_MISSING_ONE", "AZ_MISSING_TWO", path=f)
    msg = str(exc.value)
    assert "AZ_MISSING_ONE" in msg and "AZ_MISSING_TWO" in msg


def test_config_missing_file_says_how_to_create_it(config_mod, tmp_path):
    with pytest.raises(FileNotFoundError, match="env.example.sh"):
        config_mod.env_local(tmp_path / "absent.sh")


def test_config_find_repo_is_marker_based(config_mod, tmp_path):
    """A bare `Path("..")` silently resolves to the wrong tree whenever the kernel's cwd is
    not `notebooks/`; the marker search either finds the checkout or raises."""
    assert config_mod.find_repo(NOTEBOOKS) == REPO_ROOT
    assert config_mod.find_repo(REPO_ROOT) == REPO_ROOT
    with pytest.raises(RuntimeError, match="no fsd checkout"):
        config_mod.find_repo(tmp_path)
