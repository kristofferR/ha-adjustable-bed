"""Prove the shared carriers against independent Ormatek packet literals."""

from datetime import datetime

import pytest

from custom_components.adjustable_bed.profiles import ormatek as app
from tests.ormatek_vectors import VECTORS


@pytest.mark.parametrize(("wire", "action", "inputs", "expected"), VECTORS)
def test_frozen_frames(wire, action, inputs, expected):
    if "body_literal" in inputs:
        frame = app.normal(wire, action)
    elif action == "clock":
        frame = app.clock(wire, datetime(*inputs["local"]))
    else:
        args = {k: v for k, v in inputs.items() if k != "type"}
        args["wake"] = {"m1": "memory_1", "flat": "flat"}.get(inputs.get("type"), "none")
        frame = app.alarm(wire, **args)
    assert frame.hex() == expected


def test_clock_sunday_is_seven_while_alarm_weekday_uses_bit_zero():
    now = datetime(2026, 11, 22, 6, 7, 8)
    assert app.clock("okin24", now).hex() == "07041a0b1607060708"
    assert app.weekday(0, 7, 0, now) == 1


def test_queries_bypass_the_ordinary_command_carriers():
    assert app.alarm_queries("okin15") == (bytes.fromhex("00c0"),)
    assert app.alarm_queries("okin15", after_set=True) == (bytes.fromhex("e28003009a"),)
    assert app.alarm_queries("okin24") == (bytes.fromhex("00c0"), bytes.fromhex("00d0"))
    assert app.massage_query("okin15").hex() == "e6fe16000000000005"
    assert app.massage_query("okin24").hex() == "00b0"


@pytest.mark.parametrize(
    ("wire", "wake", "expected"),
    [
        ("okin15", "flat", "ed8003061eff1c000000000000000050"),
        ("okin15", "massage", "ed8003061eff09000000000000000063"),
        ("okin15", "zero_g", "ed8003061eff0d00000000000000005f"),
        ("okin15", "tv", "ed8003061eff0f00000000000000005d"),
        ("okin24", "flat", "0705ff09061e000100"),
        ("okin24", "massage", "0705ff08061e000100"),
        ("okin24", "zero_g", "0705ff01061e000100"),
        ("okin24", "tv", "0705ff03061e000100"),
    ],
)
def test_remaining_ui_wake_actions_have_independent_literal_frames(wire, wake, expected):
    assert app.alarm(wire, enabled=True, hour=6, minute=30, wake=wake).hex() == expected
