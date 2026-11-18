"""Row082's unchanged literals against candidate production packet encoders.

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


class CommandRow(TypedDict):
    protocol: app.Protocol
    action: str
    bytes: str


FIXTURES = Path(__file__).parent / "fixtures/betterliving2"
VECTORS = cast(list[Vector], json.loads((FIXTURES / "vectors.json").read_text()))
COMMANDS = cast(list[CommandRow], json.loads((FIXTURES / "commands.json").read_text()))
OUTBOUND = tuple(row for row in VECTORS if row["kind"] in ("command", "time", "clock", "query"))


def test_accepted_inventory() -> None:
    """A missing scenario must fail rather than disappear behind a selector."""
    assert len(VECTORS) == 100
    assert len(OUTBOUND) == 95
    assert len({row["id"] for row in VECTORS}) == 100
    assert len(COMMANDS) == 83
    assert {
        protocol: sum(row["protocol"] == protocol for row in COMMANDS)
        for protocol in ("P1", "P2", "P3")
    } == {"P1": 25, "P2": 29, "P3": 29}
    variants = json.loads((FIXTURES / "variants.json").read_text())
    assert {row["id"] for row in variants} == {
        f"bedtype{wire}-motors{motors}" for wire in range(3) for motors in (2, 3)
    }
    receive = cast(list[Vector], json.loads((FIXTURES / "receive.json").read_text()))
    assert receive == [row for row in VECTORS if row["kind"] in ("massage", "parse_clock")]
    assert len(receive) == 5
    repairs = json.loads((FIXTURES / "repair_observations.json").read_text())
    assert len(repairs["alarm_consumer"]) == 6
    assert len(repairs["timer_counterexamples"]) == 8
    assert len(json.loads((FIXTURES / "alarm_preferences.json").read_text())) == 8


def test_every_command_literal_is_in_outbound_proof() -> None:
    """All 69 literal callers are covered; the other 14 rows are formulas."""
    literals = [row for row in COMMANDS if all(char in "0123456789abcdef" for char in row["bytes"])]
    assert len(literals) == 69
    frozen = {(row["protocol"], row["expected_bytes"]) for row in OUTBOUND}
    assert all((row["protocol"], row["bytes"]) in frozen for row in literals)


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
