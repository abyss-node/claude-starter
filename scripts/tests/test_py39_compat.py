"""The scripts promise Python 3.9. A 3.10-only keyword (`Path.write_text(newline=...)`) once shipped and
broke the failure reporter on 3.9 while every test passed on 3.12, so the 3.10+ constructs a model tends
to reach for are refused here by reading the source, whatever interpreter runs the suite."""
import ast
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
GUARD = SCRIPTS.parent / "plugins" / "starter" / "hooks" / "commit-guard"
SOURCES = (sorted(SCRIPTS.glob("*.py")) + sorted((SCRIPTS / "tests").glob("*.py"))
           + sorted(GUARD.glob("*.py")) + sorted((GUARD / "tests").glob("*.py")))


def _calls(tree):
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            yield node


def _name(func) -> str:
    return func.attr if isinstance(func, ast.Attribute) else func.id if isinstance(func, ast.Name) else ""


@pytest.mark.parametrize("path", SOURCES, ids=lambda p: p.name)
def test_source_parses_as_python_39(path):
    ast.parse(path.read_text(encoding="utf-8"), filename=str(path), feature_version=(3, 9))


@pytest.mark.parametrize("path", SOURCES, ids=lambda p: p.name)
def test_no_310_only_calls(path):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    bad = []
    for call in _calls(tree):
        kw = {k.arg for k in call.keywords}
        name = _name(call.func)
        if name in ("write_text", "read_text") and "newline" in kw:
            bad.append(f"line {call.lineno}: Path.{name}(newline=...) needs 3.10 (use open(..., newline=))")
        if name == "zip" and "strict" in kw:
            bad.append(f"line {call.lineno}: zip(strict=) needs 3.10")
        if name == "dataclass" and kw & {"kw_only", "slots", "match_args"}:
            bad.append(f"line {call.lineno}: dataclass({', '.join(sorted(kw))}) needs 3.10")
    for node in ast.walk(tree):
        if isinstance(node, ast.Match if hasattr(ast, "Match") else ()):
            bad.append(f"line {node.lineno}: match statement needs 3.10")
    assert not bad, f"{path.name}: " + "; ".join(bad)


@pytest.mark.parametrize("path", SOURCES, ids=lambda p: p.name)
def test_tomllib_is_never_a_top_level_import(path):
    """tomllib is 3.11+: it may only be imported inside a function, behind a version check."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in tree.body:
        names = []
        if isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = [node.module or ""]
        assert "tomllib" not in names, f"{path.name} line {node.lineno}: top-level tomllib import"
