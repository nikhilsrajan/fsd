"""Doc-corpus checks (spec 41 D6). Synthetic, no network.

Implemented here:
  * assertion 4 (P1) - every point-in-time doc parses as a valid D4 status
    header, and every `superseded_by` names a file that exists.
  * assertion 1 (P4) - `env.example.sh` declares exactly the variables the notebooks
    ask a user to fill in (`notebooks/_config.py::NOTEBOOK_VARS`), and every one is
    documented in `docs/reference/environment.md`. Re-scoped 2026-08-20 from a
    whole-corpus parity check -- see the test's own docstring for why.

Assertions 2 and 3 (link resolution, README verb existence) belong to P5.
"""

from __future__ import annotations

import ast
import inspect
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

_VALID_STATUSES = {"current", "historical"}
_SUPERSEDED_RE = re.compile(r"^superseded-by-(.+)$")

# Not point-in-time documents (or not governed by D4): indexes, the template
# skeleton (which carries the header pattern as a placeholder, not a real
# status), and non-run-book support files.
_EXCLUDE_BASENAMES = {"README.md", "TEMPLATE.md"}

# Every directory spec 41 D3 classifies as point-in-time. `specs/` and `runbooks/`
# are D6 assertion 4's literal wording; the other three were stamped in P1/P3 and
# are covered here too, so their headers cannot rot untested.
_D4_DIRS = ("specs", "runbooks", "demos", "benchmarks", "docs/findings")


def _d4_targets() -> list[Path]:
    paths = []
    for d in _D4_DIRS:
        for p in sorted((REPO_ROOT / d).glob("*.md")):
            if p.name in _EXCLUDE_BASENAMES:
                continue
            paths.append(p)
    return paths


def _parse_header(path: Path) -> dict:
    text = path.read_text()
    assert text.startswith("---\n"), f"{path}: missing D4 header (must start with '---')"
    end = text.find("\n---\n", 4)
    assert end != -1, f"{path}: D4 header not terminated with a second '---' line"
    block = text[4:end]
    fields: dict[str, str] = {}
    for line in block.splitlines():
        if not line.strip():
            continue
        assert ":" in line, f"{path}: malformed header line {line!r}"
        key, _, value = line.partition(":")
        fields[key.strip()] = value.strip()
    return fields


@pytest.mark.parametrize("path", _d4_targets(), ids=lambda p: str(p.relative_to(REPO_ROOT)))
def test_d4_header_parses(path: Path):
    fields = _parse_header(path)

    assert "status" in fields, f"{path}: header missing 'status'"
    assert "summary" in fields, f"{path}: header missing 'summary'"
    assert fields["summary"], f"{path}: 'summary' is empty"

    status = fields["status"]
    m = _SUPERSEDED_RE.match(status)
    if m:
        assert "superseded_by" in fields, (
            f"{path}: status is {status!r} but header has no 'superseded_by'"
        )
        assert fields["superseded_by"] == m.group(1), (
            f"{path}: status says superseded-by-{m.group(1)} but "
            f"superseded_by: {fields['superseded_by']!r} disagrees"
        )
    else:
        assert status in _VALID_STATUSES, (
            f"{path}: status {status!r} is not one of "
            f"{_VALID_STATUSES} or 'superseded-by-NN'"
        )
        assert "superseded_by" not in fields, (
            f"{path}: 'superseded_by' set but status is {status!r}, not superseded-by-NN"
        )


@pytest.mark.parametrize("path", _d4_targets(), ids=lambda p: str(p.relative_to(REPO_ROOT)))
def test_d4_superseded_by_target_exists(path: Path):
    fields = _parse_header(path)
    target = fields.get("superseded_by")
    if target is None:
        pytest.skip("not superseded")

    for base_dir in (REPO_ROOT / "specs", REPO_ROOT / "runbooks"):
        matches = list(base_dir.glob(f"{target}-*.md")) + list(base_dir.glob(f"{target}.md"))
        if matches:
            return
    pytest.fail(f"{path}: superseded_by {target!r} names no file in specs/ or runbooks/")


# --------------------------------------------------------------------------
# Assertion 1 (spec 41 D6/D7): AZ_* variable parity.
#
# The drift this kills is measured: ~50 variables accreted across the run-books
# with no canonical list, including four spellings of one idea (AZ_ARCHIVE /
# _ROOT / _PATH / _CATALOG). Every documentation defect that cost a real run was
# of this class.
# --------------------------------------------------------------------------

_ENV_EXAMPLE = REPO_ROOT / "env.example.sh"
_ENV_REFERENCE = REPO_ROOT / "docs" / "reference" / "environment.md"
_CONFIG_PY = REPO_ROOT / "notebooks" / "_config.py"

# Point-in-time corpora are never edited after the fact (spec 41 D3), so what they name is
# a fact about what was true then, not drift to fix. The progress archive in particular
# still names variables since renamed or dropped (AZ_DOWNLOAD_ROOT,
# AZ_INFER_ENV_NAME_VERSION). Excluded from any check that would ask it to keep up.
_POINT_IN_TIME_EXCLUDE = {REPO_ROOT / "docs" / "progress-archive.md"}


def _declared_vars() -> set[str]:
    return set(re.findall(r"^export (AZ_[A-Z0-9_]+)", _ENV_EXAMPLE.read_text(), re.M))


def _notebook_vars() -> set[str]:
    """`notebooks/_config.py::NOTEBOOK_VARS` — read as text, not imported.

    Parsing keeps this test independent of `notebooks/` being importable (it is not a
    package, and `_config` resolves the repo at import time).
    """
    src = _CONFIG_PY.read_text()
    # Split on a closing paren at the START of a line, not the first `)` anywhere: the
    # per-variable comments contain parentheses ("(not your login)"), and slicing at the
    # first one silently truncated the tuple — which this test then reported as the
    # template declaring a variable no notebook reads. Found by the test itself.
    block = src.split("NOTEBOOK_VARS = (", 1)[1].split("\n)", 1)[0]
    return set(re.findall(r'"(AZ_[A-Z0-9_]+)"', block))


def test_env_example_declares_exactly_the_notebook_vars():
    """`env.example.sh` offers exactly what a notebook asks a user to fill in.

    **This deliberately replaced a wider check** (2026-08-20). The earlier version asserted
    parity against every `AZ_*` named anywhere in `runbooks/`, `demos/` and `docs/` — which
    made sense when this template's charter was "every AZ_* the run-books use, in one
    place" (spec 41 D7's original wording). That charter is obsolete:

    * `env.example.sh` is **what a user copies and fills in**, and their entry point is a
      notebook. A variable no notebook reads is a blank they are asked to fill for nothing,
      so the old check actively pushed the file towards being unusable — 54 blanks for the
      six a notebook needs.
    * the run-books that introduced most of those variables are **point-in-time documents**
      (spec 41 D3): never edited after the fact, and progressively stale. Holding a live
      user-facing template hostage to them is backwards. The old check already conceded the
      principle by excluding `docs/progress-archive.md` for exactly this reason.

    What is NOT lost: `docs/reference/environment.md` still documents every variable this
    project has ever used, and `test_az_vars_are_documented` below still requires every
    declared variable to appear there. So the reference stays the complete decode ring; the
    template stays the short thing you fill in.

    Both directions still matter, which is why this is an equality and not a subset:
    a notebook must never read a variable the template does not offer, and the template must
    never accrete one no notebook reads.
    """
    declared, expected = _declared_vars(), _notebook_vars()
    assert expected, "notebooks/_config.py declares no NOTEBOOK_VARS"
    missing = expected - declared
    assert not missing, (
        f"NOTEBOOK_VARS names {sorted(missing)}, which env.example.sh does not declare — "
        "a user copying the template cannot fill in a value the notebook will ask for."
    )
    extra = declared - expected
    assert not extra, (
        f"env.example.sh declares {sorted(extra)}, which no notebook reads — that is a blank "
        "the user is asked to fill for nothing. Drop it, or add it to NOTEBOOK_VARS."
    )


def test_az_vars_are_documented():
    """Every declared variable appears in the environment reference table."""
    reference = _ENV_REFERENCE.read_text()
    missing = sorted(v for v in _declared_vars() if v not in reference)
    assert not missing, f"undocumented in docs/reference/environment.md: {missing}"


# --------------------------------------------------------------------------
# Assertions 2 and 3 (spec 41 D6, P5): links resolve, and the README's verbs
# are real. Assertion 3 alone would have caught the README that called
# `run_inference` a stub for weeks after it shipped and ran on a cluster.
# --------------------------------------------------------------------------

_MD_LINK_RE = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
# Root documents + the maintained docs/ tree. Point-in-time corpora are excluded
# deliberately: they are never edited after the fact (D3), so a link that rots
# there is a fact about history, not a defect to fix.
_LINKED_DOCS = ("README.md", "ARCHITECTURE.md", "CONTEXT.md", "ROADMAP.md", "PROGRESS.md")


def _link_targets(text: str):
    for raw in _MD_LINK_RE.findall(text):
        target = raw.split("#", 1)[0].strip()
        if not target or "://" in target or target.startswith("mailto:"):
            continue
        yield target


def _docs_with_links() -> list[Path]:
    paths = [REPO_ROOT / n for n in _LINKED_DOCS if (REPO_ROOT / n).exists()]
    paths += sorted((REPO_ROOT / "docs").rglob("*.md"))
    return paths


@pytest.mark.parametrize("path", _docs_with_links(), ids=lambda p: str(p.relative_to(REPO_ROOT)))
def test_relative_links_resolve(path: Path):
    broken = [t for t in _link_targets(path.read_text()) if not (path.parent / t).exists()]
    assert not broken, f"{path}: link target(s) do not exist: {broken}"


def test_readme_verbs_exist():
    """Every `fsd.<verb>(` the README calls is really in `fsd.__all__`."""
    import fsd

    called = set(re.findall(r"\bfsd\.([a-z_][a-z0-9_]*)\s*\(", (REPO_ROOT / "README.md").read_text()))
    assert called, "README quickstart calls no fsd verbs — did the example disappear?"
    missing = sorted(v for v in called if v not in fsd.__all__)
    assert not missing, f"README calls fsd.<verb> that is not in fsd.__all__: {missing}"


def _readme_fsd_calls():
    """Every `fsd.<verb>(...)` call in the README's python blocks, as (verb, npos, kwnames).

    Calls that splat (`*args`/`**kwargs`) are skipped — arity is unknowable statically.
    """
    text = (REPO_ROOT / "README.md").read_text()
    for block in re.findall(r"```python\n(.*?)```", text, re.S):
        for node in ast.walk(ast.parse(block)):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            if not (isinstance(fn, ast.Attribute) and isinstance(fn.value, ast.Name)
                    and fn.value.id == "fsd"):
                continue
            if any(isinstance(a, ast.Starred) for a in node.args) or \
                    any(k.arg is None for k in node.keywords):
                continue
            yield fn.attr, len(node.args), [k.arg for k in node.keywords]


def test_readme_calls_bind_to_real_signatures():
    """The README's example calls must actually bind — assertion 3 with teeth.

    Verb *existence* (above) does not prove the call is callable: the P5 review found
    `fsd.download(...)` missing its required `max_tiles` and `fsd.run_inference(...)`
    passing a `model_bundle=` keyword that does not exist. Both raise TypeError on the
    first line a newcomer copies. This binds each call's real arity and keyword names
    against the live signature, without executing anything.
    """
    import fsd

    calls = list(_readme_fsd_calls())
    assert calls, "README's python blocks contain no fsd.<verb>(...) calls to check."
    sentinel = object()
    failures = []
    for verb, npos, kwnames in calls:
        fn = getattr(fsd, verb, None)
        if fn is None:
            failures.append(f"fsd.{verb} does not exist")
            continue
        try:
            inspect.signature(fn).bind(*[sentinel] * npos, **dict.fromkeys(kwnames, sentinel))
        except TypeError as exc:
            failures.append(f"fsd.{verb}(...): {exc}")
    assert not failures, "README example call(s) would raise TypeError:\n  " + "\n  ".join(failures)


# --- run-book python snippets reference real fsd attributes --------------------
#
# Run-book snippets are copy-pasted verbatim onto a remote VM, where a typo costs a
# round-trip through VPN + `az login` + a clone. Three have bitten already:
# `git check-ignore -v` inverting its own PASS verdict; `from fsd import storage as fs`
# (fsd.storage is a PACKAGE -- the functions live in fsd.storage.fs), which raised
# AttributeError at run-book 43 Step 1f; and `fs.put(<dir>, ..., recursive=True)`, where
# put/get are file-only and take no `recursive`.
#
# This checks the class the first two belong to: every attribute a snippet reads off a
# module it imported from `fsd` must actually exist. It imports the module (cheap, no
# side effects) but executes no snippet.

_SNIPPET_DIRS = ("runbooks", "docs")
# The selector MUST match every form `_fsd_attr_uses` parses. Selecting only on
# ```python fences made this test vacuous on its first write: run-book 43 has none
# -- all three of its snippets are `python -c "..."` inside ```bash blocks, i.e.
# exactly the file the test was added for.
_SNIPPET_RE = re.compile(r'```(?:python|py)\n|python -c "\n', re.S)


def _docs_with_python_snippets() -> list[Path]:
    paths = []
    for d in _SNIPPET_DIRS:
        for path in sorted((REPO_ROOT / d).rglob("*.md")):
            if path in _POINT_IN_TIME_EXCLUDE:
                continue  # point-in-time corpus, never edited after the fact (D3)
            if _SNIPPET_RE.search(path.read_text()):
                paths.append(path)
    return paths


def _fsd_attr_uses(text: str):
    """`(module, attr)` for every `alias.attr` where `alias` came from an
    `import fsd...`/`from fsd... import ...` in the SAME snippet.

    Both `python -c "..."` bodies inside bash blocks and plain ```python blocks are
    covered: the former are extracted first, so a snippet's imports and its uses are
    always parsed together.
    """
    blocks = list(re.findall(r"```(?:python|py)\n(.*?)```", text, re.S))
    blocks += re.findall(r'python -c "\n(.*?)"\n', text, re.S)
    for block in blocks:
        try:
            tree = ast.parse(block)
        except SyntaxError:
            continue  # a prose-y or templated snippet; not this test's business
        alias_to_module: dict[str, str] = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("fsd"):
                for a in node.names:
                    alias_to_module[a.asname or a.name] = f"{node.module}.{a.name}"
            elif isinstance(node, ast.Import):
                for a in node.names:
                    if a.name.startswith("fsd"):
                        alias_to_module[a.asname or a.name] = a.name
        if not alias_to_module:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
                module = alias_to_module.get(node.value.id)
                if module:
                    yield module, node.attr


@pytest.mark.parametrize(
    "path", _docs_with_python_snippets(), ids=lambda p: str(p.relative_to(REPO_ROOT))
)
def test_doc_snippets_use_real_fsd_attributes(path: Path):
    import importlib

    failures = []
    for module_path, attr in _fsd_attr_uses(path.read_text()):
        obj = None
        for candidate in (module_path, module_path.rsplit(".", 1)[0]):
            try:
                obj = importlib.import_module(candidate)
                break
            except ImportError:
                continue
        if obj is None:
            continue  # an optional-extra module this env lacks; not a doc defect
        if candidate != module_path:  # imported the parent, so resolve the leaf
            leaf = module_path.rsplit(".", 1)[1]
            if not hasattr(obj, leaf):
                failures.append(f"{module_path} does not exist")
                continue
            obj = getattr(obj, leaf)
        if not hasattr(obj, attr):
            failures.append(
                f"{module_path}.{attr} does not exist "
                f"(is {module_path} a package whose functions live one level deeper?)"
            )
    assert not failures, f"{path.name} snippet references a missing fsd attribute:\n  " + \
        "\n  ".join(sorted(set(failures)))
