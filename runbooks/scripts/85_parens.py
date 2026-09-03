"""#85 mechanical pass: drop reference-only parentheticals from prose lines.

Only touches lines that tokenize/ast prove are comments or docstrings. Only removes a
`(...)` whose entire content is backward-reference bookkeeping. Never removes a
parenthetical containing `#` — that is the GitHub issue mapping (CLAUDE.md: ~448
`TODO #NN` refs, `TODO #47 == issue #47`).

Usage: parens.py [--apply] <path> ...
"""

import ast
import io
import re
import sys
import tokenize
from pathlib import Path

# A reference token: "spec 50", "D4", "AC6", "§9", "P4", "specs/16-foo.md".
TOKEN = r"(?:spec\s+\d+|\bD\d+\b|\bAC\d+\b|§\s*\d+[a-z]?|\bP\d+\b)"
# A whole parenthetical made only of reference tokens and separators.
REF_ONLY = re.compile(
    rf"\((?:{TOKEN})(?:\s*(?:[,/+;]|and)?\s*(?:{TOKEN}))*\.?\)",
    re.IGNORECASE,
)


def prose_spans(src):
    """{lineno: col_at_which_prose_starts} for every comment/docstring line."""
    spans = {}
    tree = ast.parse(src)
    for n in ast.walk(tree):
        if not isinstance(n, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        b = getattr(n, "body", None)
        if (
            b
            and isinstance(b[0], ast.Expr)
            and isinstance(b[0].value, ast.Constant)
            and isinstance(b[0].value.value, str)
        ):
            d = b[0]
            for ln in range(d.lineno, d.end_lineno + 1):
                # First line of the docstring: start after the opening quote.
                spans[ln] = d.col_offset if ln == d.lineno else 0
    for tok in tokenize.generate_tokens(io.StringIO(src).readline):
        if tok.type == tokenize.COMMENT:
            spans[tok.start[0]] = min(spans.get(tok.start[0], 10**9), tok.start[1])
    return spans


def scrub(line):
    """Remove reference-only parentheticals, then tidy the whitespace they leave."""
    out = REF_ONLY.sub("\x00", line)
    if "\x00" not in out:
        return line
    # " (spec 50)." -> "."   /   "(spec 50) foo" -> "foo"   /   "a (D1) b" -> "a b"
    out = re.sub(r"[ \t]+\x00(?=[ \t]*[.,;:)]?)", "\x00", out)
    out = re.sub(r"\x00[ \t]+", "\x00 ", out)
    out = out.replace("\x00", "")
    return out.rstrip() if out.strip() else out


LOST_ANCHOR = []

BANNER = re.compile(r"^(\s*#\s*-{2,}\s.*?\s)-{2,}(\s*)$")


def repad(new, old):
    """A `# --- Title ------` banner loses dashes with the text; put them back."""
    m = BANNER.match(new)
    if not m or not BANNER.match(old):
        return new
    head, tail = m.group(1), m.group(2)
    return head + "-" * max(3, len(old.rstrip()) - len(head)) + tail


def process(path, apply):
    src = path.read_text()
    try:
        spans = prose_spans(src)
    except SyntaxError as e:
        print(f"SKIP {path}: {e}")
        return 0
    lines = src.splitlines(keepends=True)
    hits = 0
    for ln, col in spans.items():
        raw = lines[ln - 1]
        head, tail = raw[:col], raw[col:]
        new_tail = scrub(tail)
        if new_tail == tail:
            continue
        merged = repad(head + new_tail, raw)
        stripped = merged.strip()
        # A comment line whose only content was the reference is now empty: drop it.
        if stripped in ("#", "") and raw.strip() not in ("#", ""):
            merged = None
        hits += 1
        lines[ln - 1] = "" if merged is None else (merged if merged.endswith("\n") else merged + "\n")
    new_src = "".join(lines)
    if hits:
        before, after = ast.get_docstring(ast.parse(src)), ast.get_docstring(ast.parse(new_src))
        if before and re.search(r"spec", before, re.I) and not re.search(r"spec", after or "", re.I):
            LOST_ANCHOR.append(str(path))
    if hits and apply:
        path.write_text(new_src)
    return hits


apply = "--apply" in sys.argv
targets = [a for a in sys.argv[1:] if a != "--apply"]
total = 0
for t in targets:
    p = Path(t)
    files = sorted(p.rglob("*.py")) if p.is_dir() else [p]
    for f in files:
        n = process(f, apply)
        if n:
            total += n
            print(f"{n:4d}  {f}")
if LOST_ANCHOR:
    print("\nMODULE DOCSTRING LOST ITS SPEC ANCHOR (re-add by hand):")
    for f in LOST_ANCHOR:
        print("  " + f)
print(f"\n{total} parentheticals {'removed' if apply else 'would be removed'}")
