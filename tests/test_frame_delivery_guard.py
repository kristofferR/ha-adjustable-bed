"""Every BLE write tells the running command that a frame reached the bed.

Entities show a cancelled command's state from what was actually sent, so a
writer that skips the marker makes its bed look as if nothing was sent.
"""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).parent.parent / "custom_components" / "adjustable_bed"


def _direct_calls(function: ast.AST) -> list[ast.Call]:
    """Calls in ``function`` itself, not in functions nested inside it."""
    calls: list[ast.Call] = []
    pending = list(ast.iter_child_nodes(function))
    while pending:
        node = pending.pop()
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            continue
        if isinstance(node, ast.Call):
            calls.append(node)
        pending.extend(ast.iter_child_nodes(node))
    return calls


def _name(call: ast.Call) -> str | None:
    if isinstance(call.func, ast.Attribute):
        return call.func.attr
    if isinstance(call.func, ast.Name):
        return call.func.id
    return None


def test_every_function_that_writes_marks_the_frame() -> None:
    unmarked = []
    for path in sorted(ROOT.rglob("*.py")):
        tree = ast.parse(path.read_text(), filename=str(path))
        for function in ast.walk(tree):
            if not isinstance(function, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            names = {_name(call) for call in _direct_calls(function)}
            if "write_gatt_char" in names and "note_frame_written" not in names:
                unmarked.append(f"{path.relative_to(ROOT)}:{function.lineno} {function.name}")
    assert not unmarked, "Call note_frame_written() after each write_gatt_char:\n" + "\n".join(
        unmarked
    )
