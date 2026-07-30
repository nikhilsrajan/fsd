"""Doc-corpus checks (spec 41 D6). Synthetic, no network.

Implemented here:
  * assertion 4 (P1) - every point-in-time doc parses as a valid D4 status
    header, and every `superseded_by` names a file that exists.
  * assertion 1 (P4) - every `AZ_*` in `env.example.sh` is named somewhere in
    the corpus, and vice versa, and every one is documented in
    `docs/reference/environment.md`.

Assertions 2 and 3 (link resolution, README verb existence) belong to P5.
"""

from __future__ import annotations

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

_AZ_VAR_RE = re.compile(r"\bAZ_[A-Z0-9_]+")
# Directories whose text is allowed to name an AZ_* variable. `src/` is NOT one:
# no AZ_* is read by library code (the `_AZ_RE` in storage/azure.py is a regex
# name, and the leading underscore keeps it out of this pattern anyway).
_AZ_CORPUS_DIRS = ("runbooks", "demos", "docs")
# The progress archive is point-in-time history (D3/D12) and names variables that
# have since been renamed or dropped -- AZ_DOWNLOAD_ROOT, AZ_INFER_ENV_NAME_VERSION.
# Those are facts about what was true then, not drift to fix, and the file is never
# edited after the fact. Parity is about the CURRENT operational corpus.
_AZ_CORPUS_EXCLUDE = {REPO_ROOT / "docs" / "progress-archive.md"}
_ENV_EXAMPLE = REPO_ROOT / "env.example.sh"
_ENV_REFERENCE = REPO_ROOT / "docs" / "reference" / "environment.md"


def _declared_vars() -> set[str]:
    return set(re.findall(r"^export (AZ_[A-Z0-9_]+)", _ENV_EXAMPLE.read_text(), re.M))


def _corpus_vars() -> set[str]:
    found: set[str] = set()
    for d in _AZ_CORPUS_DIRS:
        for p in (REPO_ROOT / d).rglob("*"):
            if p.is_file() and p.suffix in {".md", ".py", ".sh"} and p not in _AZ_CORPUS_EXCLUDE:
                found |= set(_AZ_VAR_RE.findall(p.read_text(errors="ignore")))
    return found


def test_az_var_parity():
    """Every declared variable is used, and every used variable is declared."""
    declared, used = _declared_vars(), _corpus_vars()
    assert declared, "env.example.sh declares no AZ_* variables"
    undeclared = used - declared
    assert not undeclared, (
        f"used in {'/, '.join(_AZ_CORPUS_DIRS)}/ but missing from env.example.sh: "
        f"{sorted(undeclared)}"
    )
    unused = declared - used
    assert not unused, (
        f"declared in env.example.sh but named nowhere in the corpus: {sorted(unused)}"
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
