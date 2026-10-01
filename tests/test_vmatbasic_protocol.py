"""Static V-MAT Basic vectors, with independent shipped-bytecode color oracle."""

import hashlib
import json
from pathlib import Path

import pytest

from custom_components.adjustable_bed.beds import vmatbasic_protocol as protocol

FIXTURES = json.loads((Path(__file__).parent / "fixtures/vmatbasic-vectors.json").read_text())


@pytest.mark.parametrize("vector", FIXTURES["packets"], ids=lambda row: row["id"])
def test_all_93_frozen_packet_vectors(vector):
    args = vector["args"]
    match vector["builder"]:
        case "motor":
            actual = bytes((args[0] & 255,))
        case "literal":
            actual = bytes(args)
        case "floor":
            actual = protocol.floor(*args)
        case "xt_floor":
            actual = protocol.xt_floor(*args)
        case "rgb":
            actual = protocol.rgb(*args)
        case "effect":
            actual = protocol.effect(*args)
        case "speed":
            actual = protocol.speed(*args)
        case "color_action":
            actual = protocol.color_action(*args)
        case "rename":
            actual = protocol.rename(*args)
        case _:
            pytest.fail("Unknown frozen vector builder")
    assert actual.hex() == vector["expected"]


def test_all_2020_palette_brightness_cases_match_independent_dalvik_oracle():
    packets = b"".join(
        protocol.color_action(color, brightness)
        for color in protocol.PALETTE
        for brightness in range(101)
    )
    assert len(packets) == 2020 * 7
    assert hashlib.sha256(packets).hexdigest() == FIXTURES["palette_all_2020_sha256"]


@pytest.mark.parametrize(
    ("data", "accepted"),
    [
        ("09ff3412babea1f10000", True),
        ("09ff3412babe01020000", False),
        ("09ff341200000101000009ff3412babe01010000", False),
        ("09ff9999babe01010000", True),
        ("0106" + "09ff3412babe01010000", True),
        ("", False),
        ("01", False),
        ("09ff3412babe0101", False),
        ("02ff341209ff3412babe01010000", False),
    ],
)
def test_raw_first_ad_predicate_and_safe_short_input(data, accepted):
    assert protocol.first_manufacturer_matches(bytes.fromhex(data)) is accepted


def test_five_frozen_response_vectors():
    assert protocol.temperature(bytes.fromhex("80000000")) == 25.0
    assert protocol.temperature(bytes.fromhex("f0ffffff")) == -11.0
    status = protocol.light_status(bytes.fromhex("ff059f"))
    assert (status.level, status.timer_minutes, status.display_percent) == (255, 1439, 100.0)
    assert protocol.motor_status(b"\x03") is True
    assert protocol.motor_status(b"\x02") is False


@pytest.mark.parametrize(
    "parser,maximum",
    [
        (protocol.temperature, 4),
        (protocol.light_status, 3),
        (protocol.motor_status, 1),
    ],
)
def test_short_response_never_becomes_observed_feedback(parser, maximum):
    for length in range(maximum):
        with pytest.raises(ValueError):
            parser(bytes(length))


@pytest.mark.parametrize("value", [True, False, -1, 256, 1.5, float("nan"), float("inf"), "1"])
def test_public_integer_domain_rejects_wrapping_and_nonintegers(value):
    with pytest.raises(ValueError):
        protocol.integer(value, 0, 255)


def test_rename_java_trim_and_utf16_boundaries():
    assert protocol.rename("\x00 Bed\x1f ") == b"Bed"
    assert protocol.rename("   ") == b""
    assert protocol.rename("\u00a0Bed\u00a0") == "\u00a0Bed\u00a0".encode()
    assert protocol.rename("\U0001f600" * 5) == ("\U0001f600" * 5).encode()
    with pytest.raises(ValueError):
        protocol.rename("\U0001f600" * 5 + "a")


def test_frozen_exact_gatt_role_catalog_and_diagnostic_order():
    suffix = "-9f03-0de5-96c5-b8f4f3081186"
    standard = "-0000-1000-8000-00805f9b34fb"
    assert (
        "00001525" + suffix,
        "00001527" + suffix,
        "00001800" + standard,
    ) == protocol.REQUIRED_SERVICES
    assert "00001526" + suffix == protocol.MOTOR_CHAR
    assert "00001529" + suffix == protocol.FLOOR_CHAR
    assert "00001550" + suffix == protocol.XT_CHAR
    assert "00002a00" + standard == protocol.NAME_CHAR
    assert (
        ("model", "0000180a" + standard, "00002a24" + standard),
        ("temperature", "00001527" + suffix, "00001532" + suffix),
        ("floor", "00001525" + suffix, "00001529" + suffix),
        ("firmware", "0000180a" + standard, "00002a26" + standard),
        ("ed", "00001527" + suffix, "00001531" + suffix),
    ) == protocol.READ_ROLES
