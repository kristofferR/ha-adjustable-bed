"""A declared capability has a command behind it.

The wire snapshot runs every command against every controller and marks the
ones the controller declares. A declared command that fails with a programming
error (a missing protocol key, say) is a capability inferred from a method the
controller merely inherited, and the button it creates fails when pressed.
"""

from __future__ import annotations

import json
from pathlib import Path

_SNAPSHOT = Path(__file__).parent / "fixtures" / "wire_snapshot.json"
_PROGRAMMING_ERRORS = frozenset({"AttributeError", "IndexError", "KeyError", "TypeError"})


def test_no_declared_command_fails_with_a_programming_error() -> None:
    scenarios = json.loads(_SNAPSHOT.read_text())["scenarios"]
    broken = {
        f"{name}:{command}": result["error"]
        for name, scenario in scenarios.items()
        for command in scenario["info"].get("gaps", ())
        if (result := scenario["commands"].get(command, {})).get("error") in _PROGRAMMING_ERRORS
    }
    assert not broken
