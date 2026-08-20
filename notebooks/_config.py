"""Config loading shared by the notebooks in this folder.

The notebooks here are **public** — they are committed to a public MIT repo — so they carry
no resource group, workspace, subscription id, cluster name or storage URL. Those live in
`env.local.sh` at the repo root, which is gitignored, and this module is how a notebook
reads them.

Why a module rather than a cell in each notebook: there are two notebooks and there will be
more, the parser has real edge cases (see `env_local`), and a copy in each would drift.
`tests/test_notebooks.py` tests this file directly.

Why not `fsd.config`: every `AZ_*` value here is **operator-facing** — consumed by a
notebook, a run-book shell or the `az` CLI. `src/fsd/` never reads the environment for a
storage location; it takes one as an argument (spec 41 D7). Putting these in the library
would blur that line.

    from _config import load, REPO, NOTEBOOKS
    cfg = load("AZ_RG", "AZ_ML_WORKSPACE")
    print(cfg.AZ_RG)
"""

from __future__ import annotations

import pathlib
import re
from types import SimpleNamespace

__all__ = ["find_repo", "env_local", "load", "REPO", "NOTEBOOKS", "ENV_LOCAL"]


def find_repo(start: pathlib.Path | None = None) -> pathlib.Path:
    """The fsd checkout, found by marker rather than by a relative `..`.

    A bare `Path("..")` is silently wrong the moment a kernel's cwd is not `notebooks/` —
    it resolves to the parent of wherever you happen to be, and every path below it is then
    subtly off with no error until something far away fails.
    """
    start = (start or pathlib.Path.cwd()).resolve()
    for d in [start, *start.parents]:
        if (d / "pyproject.toml").exists() and (d / "src" / "fsd").is_dir():
            return d
    raise RuntimeError(f"no fsd checkout at or above {start} — run this from inside the repo.")


REPO = find_repo()
NOTEBOOKS = REPO / "notebooks"
ENV_LOCAL = REPO / "env.local.sh"

# `export NAME='value'`, `export NAME="value"`, or `export NAME=value`, each optionally
# followed by a comment. The trailing-comment part is load-bearing: `env.example.sh` writes
# `export AZ_RG=''   # resource group ...`, and an earlier version of this pattern anchored
# the value to end-of-line, so EVERY line failed to match and a filled-in file was reported
# as empty.
_EXPORT_RE = re.compile(
    r"""\s*export\s+(\w+)=(?:"([^"]*)"|'([^']*)'|([^#\s]*))\s*(?:\#.*)?$"""
)


def env_local(path: pathlib.Path | str | None = None) -> dict[str, str]:
    """Parse `env.local.sh` into a dict. No shell is spawned.

    Deliberately **not** `source`d: sourcing would run arbitrary shell from a file whose
    whole purpose is holding credentials-adjacent values, and it would resolve `$(...)`
    entries whose values this module has no business capturing. Entries containing `$` are
    skipped for the same reason — every value a notebook reads must be a literal, so what
    the notebook uses is exactly what you can see in the file.

    Empty values are omitted rather than returned as `""`, so `load()` reports them as
    missing instead of handing a notebook a blank that fails somewhere further on.
    """
    path = pathlib.Path(path) if path else ENV_LOCAL
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found. Create it once:\n"
            f"    cp {REPO / 'env.example.sh'} {path}\n"
            f"    $EDITOR {path}\n"
            "It is gitignored. Concrete values come from your platform admin, never from "
            "this repo."
        )
    out: dict[str, str] = {}
    for line in path.read_text().splitlines():
        m = _EXPORT_RE.match(line)
        if not m:
            continue
        value = next((g for g in m.groups()[1:] if g is not None), "")
        if value and "$" not in value:
            out[m.group(1)] = value
    return out


def load(*required: str, path: pathlib.Path | str | None = None) -> SimpleNamespace:
    """Return the named variables as attributes, or raise naming every one that is missing.

    Reports **all** missing names at once: filling one blank, re-running, and being told
    about the next is a bad loop when each round trip is a notebook cell.
    """
    values = env_local(path)
    missing = [k for k in required if not values.get(k)]
    if missing:
        raise KeyError(
            f"{', '.join(missing)} — not set in {path or ENV_LOCAL}. "
            f"Fill {'them' if len(missing) > 1 else 'it'} in and re-run this cell. "
            "Every variable is documented in docs/reference/environment.md."
        )
    return SimpleNamespace(**{k: values[k] for k in required})
