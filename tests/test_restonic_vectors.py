"""All independently frozen Restonic 1.0.1 literals through production encoders."""

import json
from pathlib import Path

import pytest

from custom_components.adjustable_bed.beds.restonic.protocol import Parser
from custom_components.adjustable_bed.profiles import restonic as app

FRAMES = json.loads((Path(__file__).parent / "fixtures/restonic/frames.json").read_text())


@pytest.mark.parametrize(
    "action,branch", [(action, branch) for action in FRAMES for branch in app.TRANSPORTS]
)
def test_frozen_literal(action, branch):
    assert app.encode(branch, action) == bytes.fromhex(
        FRAMES[action][{"box15": "P1", "box1220": "P2", "box24": "P3"}[branch]]
    )


@pytest.mark.parametrize(
    "name,branch",
    [
        ("Smartbed1", "box24"),
        ("BLE001", "box1220"),
        ("smartbed", "box15"),
        ("ble", "box15"),
        ("other", "box15"),
        ("", None),
    ],
)
def test_exact_source_selector(name, branch):
    assert app.branch_for_name(name) == branch


def test_box24_every_raw_field_byte():
    parser = Parser("box24")
    for value in range(256):
        parsed = parser.feed(bytes((0xA5, 0x0B, 0x0E, 0, value, 0, value, value, value)))

        def strength(x):
            return x % 3 + x // 3 + (1 if x > 1 else 0)

        assert parsed == {
            "b": (value & 15) // 2,
            "23": value - 1,
            "13": strength(value & 15),
            "1b": strength(value),
        }
    for kind, expected in ((5, 17), (6, 19), (7, 9)):
        assert parser.feed(bytes((0xA5, 0x0C, 0, 0, 4, kind, 6, 7))) == {
            "2b": 6,
            "43": 4,
            "33": 7,
            "3b": expected,
        }


def test_box15_raw_fields_reassembly_and_retention():
    parser = Parser("box15")
    assert parser.feed(bytes.fromhex("ed800001020304000000")) == {
        "2b": 1,
        "43": 3,
        "33": 2,
        "3b": 4,
    }
    d = bytearray(23)
    d[:3] = bytes.fromhex("f4fe16")
    d[11], d[12], d[19], d[21] = 3, 6, 0x21, 9
    assert parser.feed(d[:20]) == {}
    expected = {"b": 1, "23": 9, "13": 2, "1b": 3}
    assert parser.feed(d[20:]) == expected
    assert parser.feed(d[20:]) == expected
    d = bytearray(16)
    d[7], d[8], d[14] = 6, 3, 0x32
    assert parser.feed(d) == {"b": 2, "23": 3, "13": 3, "1b": 2}
    d = bytearray(10)
    d[8] = 0x23
    assert parser.feed(d) == {"b": 3, "23": 1, "13": 0, "1b": 0}
    assert Parser("box15").feed(b"unknown") == {"b": 0, "23": 1, "13": 0, "1b": 0}
    assert Parser("box15").feed(b"\xed\x80\0\0") == {}
    assert Parser("box24").feed(b"\xa5\x0c") == {}
    assert Parser("box24").feed(b"\xa5\x0b\x0e") == {}
    assert Parser("box1220").feed(bytes(d)) == {}


@pytest.mark.parametrize(
    "branch,packet,expected",
    [
        ("box15", "ed800001020304", {"2b": 1, "43": 3, "33": 2, "3b": 4}),
        (
            "box15",
            "0000000000000000000000030600000000000021001e00",
            {"b": 1, "23": 30, "13": 2, "1b": 3},
        ),
        ("box15", "00000000000000060300000000003200", {"b": 2, "23": 3, "13": 3, "1b": 2}),
        ("box15", "00000000000000000f00", {"b": 15, "23": 1, "13": 0, "1b": 0}),
        ("box24", "a50c000001050203", {"2b": 2, "43": 1, "33": 3, "3b": 17}),
        ("box24", "a50c000001060203", {"2b": 2, "43": 1, "33": 3, "3b": 19}),
        ("box24", "a50c000001000203", {"2b": 2, "43": 1, "33": 3, "3b": 9}),
        ("box24", "a50b0e002100030306", {"b": 0, "23": 2, "13": 2, "1b": 3}),
        ("box24", "a50b0e000200030306", {"b": 1, "23": 2, "13": 2, "1b": 3}),
        ("box24", "a50b0e002f00030306", {"b": 7, "23": 2, "13": 2, "1b": 3}),
        ("box24", "000000", {}),
        ("box15", "000000", {"b": 0, "23": 1, "13": 0, "1b": 0}),
    ],
)
def test_original_twelve_source_derived_parser_cases(branch, packet, expected):
    assert Parser(branch).feed(bytes.fromhex(packet)) == expected
