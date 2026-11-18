"""BetterLiving2 1.3.0 literals against production packet encoders.

Receive fixtures and repaired consumer observations are intentionally separate
from outbound codec fit. No analyst evaluator or hardware execution is used.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal, TypedDict, cast

import pytest

from custom_components.adjustable_bed.profiles import betterliving2 as app


class CalendarFields(TypedDict):
    year: int
    month: int
    day: int
    weekday: int
    hour: int
    minute: int
    second: int


class Inputs(TypedDict, total=False):
    opcode: int
    now: CalendarFields
    hour: int
    minute: int
    week: int
    massage: int
    kind: int
    enabled: bool
    query: Literal["clock", "massage"]


class Vector(TypedDict):
    id: str
    protocol: app.Protocol
    kind: Literal["command", "time", "clock", "query", "massage", "parse_clock"]
    inputs: Inputs
    expected_bytes: str


FIXTURES = Path(__file__).parent / "fixtures/betterliving2"
VECTORS = cast(list[Vector], json.loads((FIXTURES / "vectors.json").read_text()))
OUTBOUND = tuple(row for row in VECTORS if row["kind"] in ("command", "time", "clock", "query"))


@pytest.mark.parametrize("vector", OUTBOUND, ids=lambda row: row["id"])
def test_all_accepted_outbound_literals(vector: Vector) -> None:
    protocol, fields, kind = vector["protocol"], vector["inputs"], vector["kind"]
    if kind == "command":
        actual = app.command(protocol, fields["opcode"])
    elif kind == "time":
        actual = app.current_time(protocol, app.Calendar(**fields["now"]))
    elif kind == "clock":
        actual = app.alarm(
            protocol,
            hour=fields["hour"],
            minute=fields["minute"],
            week=fields["week"],
            massage=fields["massage"],
            kind=fields["kind"],
            now=app.Calendar(**fields["now"]),
            enabled=fields.get("enabled", True),
        )
    else:
        assert kind == "query"
        actual = (
            app.massage_query(protocol)
            if fields["query"] == "massage"
            else app.alarm_query(protocol, app.Calendar(2026, 7, 14, 2, 12, 30, 45))
        )
    assert actual == bytes.fromhex(vector["expected_bytes"])
