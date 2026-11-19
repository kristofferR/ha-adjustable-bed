"""Accepted RX/repair/preferences through production state consumers, not the analyst evaluator."""

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

import pytest

from custom_components.adjustable_bed.beds.keeson.betterliving2_state import (
    AlarmView,
    alarm_fields,
    consume_p1,
    massage_fields,
    restore_actions,
)
from custom_components.adjustable_bed.profiles.betterliving2 import (
    command,
    manufacturer_route,
    weekday_mask,
)

FIXTURES = Path(__file__).parent / "fixtures/betterliving2"
RX = json.loads((FIXTURES / "receive.json").read_text())
REPAIRS = json.loads((FIXTURES / "state_cases.json").read_text())
PREFERENCES = json.loads((FIXTURES / "alarm_preferences.json").read_text())


def view(fields, **changes):
    known = {key: value for key, value in fields.items() if key in AlarmView.__dataclass_fields__}
    known.update(changes)
    if "weeks" in known:
        known["weeks"] = tuple(known["weeks"])
    return AlarmView(**known)


@pytest.mark.parametrize("row", RX, ids=lambda row: row["id"])
def test_five_original_receive_field_projections(row):
    packet = bytes.fromhex(row["expected_bytes"])
    parser = massage_fields if row["kind"] == "massage" else alarm_fields
    result = parser(row["protocol"], packet)
    assert result is not None
    actual = asdict(result)
    actual["enabled"] = result.enabled
    assert {key: actual[key] for key in row["expected_state"]} == row["expected_state"]


@pytest.mark.parametrize("row", REPAIRS["alarm_consumer"], ids=lambda row: row["id"])
def test_six_repaired_consumer_transitions(row):
    prior = view(REPAIRS["prior_ui"], switch_selected=row["prior_switch_selected"])
    saved = view(REPAIRS["saved_preferences"])
    actual, preferences = consume_p1(bytes.fromhex(row["notification"]), prior, saved)
    expected = prior if isinstance(row["expected_ui"], str) else view(row["expected_ui"])
    expected_saved = (
        saved if isinstance(row["expected_preferences"], str) else view(row["expected_preferences"])
    )
    assert actual == expected
    assert preferences == expected_saved


@pytest.mark.parametrize("row", PREFERENCES)
def test_eight_persisted_action_priorities(row):
    assert restore_actions(*row["inputs"]) == tuple(row["expected"])


@pytest.mark.parametrize(
    "protocol,packet",
    [
        ("P1", "0000003d0700be1111f8"),
        ("P1", "000000ff8000be1111f8"),
        ("P2", "ed800307"),
        ("P3", "a50c0000be05071e00"),
    ],
)
def test_malformed_alarm_fields_never_partially_apply(protocol, packet):
    assert alarm_fields(protocol, bytes.fromhex(packet)) is None


def test_signed_massage_is_not_clamped_into_a_guessed_hardware_level():
    fields = massage_fields("P3", bytes.fromhex("00000000800080fe80"))
    assert fields is not None
    assert (fields.timer_level, fields.wave, fields.head_level, fields.foot_level) == (
        0,
        -128,
        0,
        -63,
    )
    assert massage_fields("P1", bytes(16)) is None
    assert massage_fields("P2", bytes(15)) is None


@pytest.mark.parametrize(
    "value,route",
    ((None, None), (b" \0DewertOKIN\0 ", "P2"), (b"BLE-4.0 Module", "P2"), (b"dewertokin", "P1")),
)
def test_manufacturer_selector_is_case_sensitive_and_not_an_advertisement(value, route):
    assert manufacturer_route(value) == route


def test_selected_week_masks_and_strict_next_day_wrap():
    assert weekday_mask(frozenset(range(7)), 7, 30, datetime(2026, 7, 14, 12)) == 255
    assert weekday_mask(frozenset({1, 2, 3, 4, 5}), 7, 30, datetime(2026, 7, 14, 12)) == 190
    assert weekday_mask(frozenset(), 7, 30, datetime(2026, 7, 18, 7, 30)) == 1
    assert weekday_mask(frozenset(), 7, 30, datetime(2026, 7, 18, 7, 29, 59)) == 64


@pytest.mark.parametrize("protocol", ("P1", "P2", "P3"))
def test_signed_command_conversion_preserves_low_32_bits(protocol):
    assert command(protocol, -1) == command(protocol, 0xFFFFFFFF)
    assert command(protocol, -0x100000000) == command(protocol, 0)
