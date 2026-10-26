"""Accepted literal vectors and parser boundaries for Adjustable Comfort M1X12."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import TypedDict, cast

import pytest

from custom_components.adjustable_bed.beds.starcode_m1x12_protocol import (
    StateValue,
    clock_packet,
    extended_packet,
    keep_open_packet,
    long_packet,
    manufacturer_dialect,
    normal_packet,
    parse_notification,
    position_packet,
    profile_from_name,
    query_packet,
    time_packet,
)


class VectorInputs(TypedDict, total=False):
    key: int | str
    encoding: str
    command: int
    value: int
    axis: int
    target: int
    yearArgument: int
    localYear: int
    month: int
    day: int
    weekday: int
    hour: int
    minute: int
    second: int
    maker: str


class Vector(TypedDict):
    id: str
    protocol: str
    action: str
    inputs: VectorInputs
    expected_bytes: str


_FIXTURE = Path(__file__).parent / "fixtures" / "starcode_m1x12_vectors.json"
VECTORS = cast(list[Vector], json.loads(_FIXTURE.read_text()))


def _key(value: int | str) -> int:
    return int(value, 16) if isinstance(value, str) else value


def _dialect(value: str) -> str:
    return "star" if value == "S" else "legacy"


def _build_vector(vector: Vector) -> bytes:
    item = vector["inputs"]
    vector_id = vector["id"]
    if vector_id in {"V-LONG-ON", "V-LONG-OFF"}:
        return long_packet(_key(item["key"]))
    if vector_id in {"V-POS", "V-POS-CLAMP"}:
        return position_packet(item["axis"], item["target"], _dialect(item["encoding"]))
    if vector_id == "V-TIME-BUILDER":
        return time_packet(
            item["yearArgument"],
            item["month"],
            item["day"],
            item["weekday"],
            item["hour"],
            item["minute"],
            item["second"],
        )
    if vector_id == "V-TIME-CALLER":
        return clock_packet(
            datetime(
                item["localYear"],
                item["month"],
                item["day"],
                item["hour"],
                item["minute"],
                item["second"],
            )
        )
    if vector_id == "V-P4-QUERY":
        return query_packet("star")
    if "command" in item:
        return extended_packet(item["command"], item["value"], _dialect(item["encoding"]))
    if vector_id == "V-ELEVATE":
        return normal_packet(_key(item["key"]), "star")
    if vector["protocol"] == "P2":
        return keep_open_packet()
    return normal_packet(_key(item["key"]), _dialect(item["encoding"]))


@pytest.mark.parametrize("vector", VECTORS, ids=lambda vector: vector["id"])
def test_every_accepted_packet_vector(vector: Vector) -> None:
    assert _build_vector(vector).hex() == vector["expected_bytes"]


@pytest.mark.parametrize(
    ("name", "profile"),
    [
        ("star252201001", "cb25"),
        ("STAR254205001", "f23"),
        ("star255401001", "f23"),
        ("STAR255402001", "kneading"),
        ("star255403001", "kneading"),
        ("STAR25OTHER", "cb25"),
        ("ELEVATE001", None),
    ],
)
def test_m1x12_profile_prefixes_are_specific_and_case_normalized(
    name: str, profile: str | None
) -> None:
    assert profile_from_name(name) == profile


@pytest.mark.parametrize(
    ("raw", "dialect"),
    [(b"star", "star"), (b"STAR", "star"), (b"star\x00", "legacy"), (b"other", "legacy")],
)
def test_manufacturer_uses_exact_raw_character_codes(raw: bytes, dialect: str) -> None:
    assert manufacturer_dialect(raw) == dialect


def test_m1x12_feedback_uses_raw_parts_and_preserves_variant_gates() -> None:
    motor = bytes.fromhex("a5 0d 00 00 65 66 37 08 2c ff 50 5a 00 00 00 00 00 00")
    assert parse_notification(motor, profile="cb25", dialect="star") == {
        "part_1_position": 100,
        "part_2_position": 55,
        "part_4_position": 44,
        "part_8_position": 80,
        "part_16_position": 100,
        "part_32_position": 8,
        "motor_stopped": True,
    }
    assert (
        parse_notification(b"\xa5\x0f\x00\x00\x01\x01\x00\x01", profile="f23", dialect="legacy")
        == {}
    )
    assert parse_notification(b"\xa5\x0e" + bytes(20), profile="cb25", dialect="legacy") == {}


def test_m1x12_state_parsers_require_safe_complete_frames() -> None:
    cases: tuple[tuple[str, bytes, dict[str, StateValue]], ...] = (
        ("cb25", b"\xa5\x0b" + bytes(17), {}),
        ("cb25", b"\xa5\x0c" + bytes(14), {}),
        ("f23", b"\xa5\x0c" + bytes(22), {}),
        ("f23", b"\xa5\x0e" + bytes(19), {}),
        ("kneading", b"\xa5\x0f" + bytes(5), {}),
    )
    for profile, payload, expected in cases:
        assert parse_notification(payload, profile=profile, dialect="legacy") == expected


def test_complete_motor_and_rgb_notifications_preserve_target_byte_ownership() -> None:
    motor = bytearray.fromhex("a5 0d 00 00 0a 0b 14 15 1e 1f 28 29 00 00 00 00 00 00")
    assert parse_notification(bytes(motor), profile="cb25", dialect="legacy") == {
        "part_1_position": 10,
        "part_2_position": 20,
        "part_4_position": 30,
        "part_8_position": 40,
        "part_16_position": 11,
        "part_32_position": 21,
        "motor_stopped": True,
    }
    motor[17] = 1
    assert (
        parse_notification(bytes(motor), profile="cb25", dialect="legacy")["motor_stopped"] is False
    )

    rgb = bytearray(20)
    rgb[0:2] = b"\xa5\x0b"
    rgb[4:6] = bytes((0x01, 0x2C))
    rgb[6] = 0x13
    rgb[7] = 0x32
    rgb[8] = 0x12
    rgb[9:11] = bytes((0x00, 0x64))
    rgb[11] = 0x34
    rgb[12] = 9
    rgb[14] = 0x33
    rgb[15] = 0x60
    rgb[16:19] = bytes((0xFF, 0xA5, 0x00))
    state = parse_notification(bytes(rgb), profile="cb25", dialect="legacy")
    assert state == {
        "massage_time_raw": 300,
        "massage_mode": 3,
        "massage_head_level": 1,
        "massage_foot_level": 2,
        "massage_active": True,
        "light_mode": 3,
        "light_brightness": 6,
        "light_on": True,
        "light_color_index": 3,
        "light_rgb": 0xFFA500,
        "light_rgb_mode": 0,
        "sonic_head_level": 4,
        "sonic_foot_level": 3,
        "sonic_active": True,
        "sonic_frequency": 40,
        "sonic_time_raw": 100,
        "sonic_mode": 1,
        "sonic_massage_type": 1,
    }


def test_direct_rgb_palette_index_is_zero_based_and_keeps_raw_color() -> None:
    data = bytearray(20)
    data[0:2] = b"\xa5\x0b"
    data[14] = 0x08
    data[16:19] = bytes((0, 0, 255))
    state = parse_notification(bytes(data), profile="f23", dialect="star")
    assert state["light_rgb"] == 0x0000FF
    assert state["light_color_index"] == 5
    assert state["light_rgb_mode"] == 1


def test_alarm_parser_keeps_basic_and_advanced_profiles_separate() -> None:
    basic = bytearray(17)
    basic[0:2] = b"\xa5\x0c"
    basic[4:10] = bytes((0xFF, 9, 7, 59, 0, 1))
    basic[11:17] = bytes((1, 3, 6, 30, 0, 0))
    assert parse_notification(bytes(basic), profile="cb25", dialect="star") == {
        "alarm_0": True,
        "alarm_0_details": {
            "index": 0,
            "repeat_raw": 255,
            "wake": "flat",
            "hour": 7,
            "minute": 59,
            "isOn": True,
        },
        "alarm_1": False,
        "alarm_1_details": {
            "index": 1,
            "repeat_raw": 1,
            "wake": "tv",
            "hour": 6,
            "minute": 30,
            "isOn": False,
        },
    }
    assert parse_notification(bytes(basic), profile="cb25", dialect="legacy").keys() == {
        "alarm_0",
        "alarm_0_details",
        "alarm_1",
        "alarm_1_details",
    }
    assert parse_notification(bytes(basic[:16]), profile="cb25", dialect="legacy") == {}
    assert parse_notification(bytes(basic), profile="f23", dialect="star") == {}

    advanced = bytearray(25)
    advanced[0:2] = b"\xa5\x0c"
    advanced[3:14] = bytes((127, 0, 1, 4, 99, 3, 2, 6, 30, 0, 1))
    advanced[14:25] = bytes((1, 4, 2, 2, 99, 2, 2, 23, 59, 0, 1))
    state = parse_notification(bytes(advanced), profile="f23", dialect="legacy")
    assert state["alarm_0_details"] == {
        "index": 0,
        "repeat_raw": 127,
        "preset": "flat",
        "light": "onOrWhite",
        "sonic": "sonic1",
        "music": "none",
        "massage": "intensity3",
        "duration": "duration20Min",
        "hour": 6,
        "minute": 30,
        "isOn": True,
    }
    assert state["alarm_1_details"] == {
        "index": 1,
        "repeat_raw": 1,
        "preset": "antisnore",
        "light": "red",
        "sonic": "normal2",
        "music": "none",
        "massage": "intensity2",
        "duration": "duration20Min",
        "hour": 23,
        "minute": 59,
        "isOn": True,
    }


def test_eq_and_kneading_notifications_expose_only_read_only_state() -> None:
    eq = bytearray(22)
    eq[0:2] = b"\xa5\x0e"
    eq[11] = 0x02
    eq[13] = 0b10101010
    eq[14:18] = bytes((0x21, 0x43, 0x65, 0x87))
    eq[18] = 0x81
    eq[19] = 0xA5
    eq[20] = 17
    eq[21] = 2
    state = parse_notification(bytes(eq), profile="kneading", dialect="legacy")
    assert state == {
        "usb_on": True,
        "eq_low_frequency": 5,
        "eq_high_frequency": 10,
        "eq_volume": 17,
        "eq_preset": "Classical",
        "eq_band_0": -1,
        "eq_band_1": 2,
        "eq_band_2": -3,
        "eq_band_3": 4,
        "eq_band_4": -5,
        "eq_band_5": 6,
        "eq_band_6": -7,
        "eq_band_7": 8,
    }

    kneading = bytes.fromhex("a5 0f 02 01 01 03 04 b0")
    assert parse_notification(kneading, profile="kneading", dialect="star") == {
        "kneading_on": True,
        "kneading_demo": True,
        "kneading_mode": 2,
        "kneading_time_raw": 1200,
    }


def test_m1x12_rejects_unknown_profile_and_dialect() -> None:
    with pytest.raises(ValueError, match="profile"):
        parse_notification(b"\xa5\x0d" + bytes(16), profile="auto", dialect="star")
    with pytest.raises(ValueError, match="dialect"):
        normal_packet(1, "unknown")
