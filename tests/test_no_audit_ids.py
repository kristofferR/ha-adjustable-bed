"""APK audit tracker ids (``row061``, ``cluster018``) never name integration code.

Comments and docstrings may cite an evidence row. Identifiers, string values
(entity keys, unique-id suffixes, state keys, user-visible text), file names and
translation keys may not, except constants named ``*LEGACY*`` that migrations
read.
"""

from __future__ import annotations

import ast
import json
import re
from collections.abc import Iterator
from pathlib import Path

import yaml

ROOT = Path(__file__).parents[1] / "custom_components" / "adjustable_bed"
AUDIT_ID = re.compile(r"row0\d\d|cluster0\d\d", re.IGNORECASE)


def _legacy_constants(tree: ast.Module) -> set[int]:
    """Return ids of the value nodes of ``*LEGACY*`` constant assignments."""
    nodes: set[int] = set()
    for node in ast.walk(tree):
        targets = (
            node.targets if isinstance(node, ast.Assign)
            else [node.target] if isinstance(node, ast.AnnAssign)
            else []
        )
        if any(isinstance(t, ast.Name) and "LEGACY" in t.id for t in targets) and node.value:
            nodes.update(id(child) for child in ast.walk(node.value))
    return nodes


def _docstrings(tree: ast.Module) -> set[int]:
    return {
        id(node.value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant)
    }


def _python_names(path: Path) -> Iterator[str]:
    tree = ast.parse(path.read_text())
    skipped = _legacy_constants(tree) | _docstrings(tree)
    for node in ast.walk(tree):
        if id(node) in skipped:
            continue
        match node:
            case ast.Name(id=name) | ast.Attribute(attr=name) | ast.arg(arg=name):
                yield name
            case ast.FunctionDef(name=name) | ast.AsyncFunctionDef(name=name) | ast.ClassDef(name=name):
                yield name
            case ast.alias(name=name, asname=asname):
                yield name
                if asname:
                    yield asname
            case ast.keyword(arg=str() as name):
                yield name
            case ast.Constant(value=str() as value):
                yield value


def _json_keys(value: object) -> Iterator[str]:
    if isinstance(value, dict):
        for key, child in value.items():
            yield str(key)
            yield from _json_keys(child)
    elif isinstance(value, list):
        for child in value:
            yield from _json_keys(child)
    elif isinstance(value, str):
        yield value


def _offenders() -> Iterator[str]:
    for path in sorted(ROOT.rglob("*")):
        relative = path.relative_to(ROOT)
        if "node_modules" in relative.parts or path.is_dir():
            continue
        if AUDIT_ID.search(str(relative)):
            yield f"file name {relative}"
        if path.suffix == ".py":
            names = _python_names(path)
        elif path.suffix == ".json":
            names = _json_keys(json.loads(path.read_text()))
        elif path.suffix == ".yaml":
            names = _json_keys(yaml.safe_load(path.read_text()))
        elif path.suffix == ".ts" and "src" in relative.parts:
            names = iter(re.findall(r"\"[^\"]*\"|'[^']*'|\b\w+\b", path.read_text()))
        else:
            continue
        for name in names:
            if AUDIT_ID.search(name):
                yield f"{relative}: {name[:80]!r}"


def test_integration_code_carries_no_audit_ids() -> None:
    assert list(_offenders()) == []
