"""The sixteen retained MLILY parser scenarios through production consumers."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import MagicMock

import pytest

from custom_components.adjustable_bed.beds.richmat_mh import protocol
from custom_components.adjustable_bed.beds.richmat_mh.app_controller import RichmatMHAppClassifier
from tests.test_richmat_cluster022 import FIXTURES, make
from tests.test_richmat_cluster022_sleep import receiver
from tests.test_richmat_mh import sleeps as sleeps

PARSERS = [row for row in json.loads((FIXTURES / "mlily_supreme_vectors.json").read_text())
           if row["builder"].startswith("parse_")]


@pytest.mark.parametrize("row", PARSERS, ids=lambda row: row["id"])
async def test_retained_parser_scenario(row, sleeps) -> None:
    raw = bytes(row["inputs"]["args"][0])
    expected, builder = row["expected"], row["builder"]
    if builder == "parse_p2":
        controller = receiver("mlily_supreme")
        controller._apply_frame = MagicMock()
        controller._notify(None, bytearray(raw))
        if expected is None:
            controller._apply_frame.assert_not_called()
        else:
            observed = controller._apply_frame.call_args.args[0]
            assert {"type": observed[3], "payload_hex": observed[4:].hex()} == expected
        return
    events = RichmatMHAppClassifier("mlily_supreme").feed(raw)
    if expected is None:
        assert not events
        return
    if builder == "parse_motor_angle":
        assert [(event.data, event.extra[0]) for event in events] == [
            (expected["axis_bits"], expected["value_string"])
        ]
    elif builder == "parse_motor_mode":
        assert [int(event.data, 2) for event in events] == [expected]
    elif builder == "parse_massage":
        assert [event.data for event in events] == [expected]
    else:
        controller = make("mlily_supreme", "garm_mattress")
        controller._version, controller._call_page = "0001", True
        controller._normal_ready = builder == "parse_mattress_update"
        for event in events:
            controller._apply(event)
        if controller._delayed_consumers:
            await asyncio.gather(*controller._delayed_consumers)
        state = controller._coordinator.controller_state
        if builder == "parse_mattress_init":
            assert controller._normal_ready
            side = expected["side"]
            assert {str(key): value for (recipient, key), value in controller._normal_values.items()
                    if recipient == side and key != expected["alarm_key"]} == expected["pairs"]
            assert state[f"ruf_richmat_mattress_{'left' if side == 1 else 'right'}_alarm"] == "07:30"
            assert sleeps == [0.3]
        elif builder == "parse_mattress_update":
            assert controller._normal_values[expected["side"], expected["key"]] == int(expected["value_hex"], 16)
            # Android's selected-side view is bounded evidence. HA retains each
            # physical receiver's reported side without moving another cache.
            assert len(controller._normal_values) == 1
        elif builder == "parse_waist_init":
            assert controller._waist
            assert state["richmat_mh_waist_mode"] == protocol.WAIST_MODES[expected["mode"]]
            assert state["richmat_mh_waist_left_heat"] == "2_hours"
            assert state["richmat_mh_waist_right_heat"] == "4_hours"
            assert state["richmat_mh_waist_both_heat"] == "8_hours"
            assert state["richmat_mh_waist_left_pressure"] == "level_1"
            assert state["richmat_mh_waist_right_pressure"] == "level_2"
            assert state["richmat_mh_waist_both_pressure"] == "level_3"
            assert state["richmat_mh_waist_left_duration"] == "15_minutes"
            assert state["richmat_mh_waist_right_duration"] == "20_minutes"
            assert state["richmat_mh_waist_both_duration"] == "30_minutes"
            assert sleeps == [0.3]


def test_nisco_and_mlily_combined_waist_forms_are_separate() -> None:
    one = protocol.mattress_frame(3, 1, 2)
    combined = one * 3
    nisco = RichmatMHAppClassifier("nisco")
    mlily = RichmatMHAppClassifier("mlily_supreme")
    assert [event.kind for event in nisco.feed(combined)] == ["waist"] * 3
    assert not mlily.feed(combined)
    assert mlily.buffer == ""


async def test_nisco_keeps_shared_mattress_effect_without_mlily_cache(sleeps) -> None:
    raw = next(row for row in PARSERS if row["id"] == "p3-parse-init-1")["inputs"]["args"][0]
    controller = make("nisco")
    for event in controller._classifier.feed(bytes(raw)):
        controller._apply(event)
    state = controller._coordinator.controller_state
    assert state["richmat_mh_mattress_available"] is True
    assert state["richmat_mh_mattress_frame"] == bytes(raw).hex()
    assert not controller._normal_ready and not controller._normal_values
    assert not controller._delayed_consumers
