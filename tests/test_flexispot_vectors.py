"""All 77 immutable source literals, plus the app's parser boundaries."""

import json
from pathlib import Path

import pytest

from custom_components.adjustable_bed.codec import flexispot as codec

VECTORS = json.loads((Path(__file__).parent / "fixtures/flexispot_vectors.json").read_text())


@pytest.mark.parametrize("row", VECTORS, ids=lambda row: row["id"])
def test_frozen_literal(row):
    assert (
        codec.frame(
            row["opcode"], row["key"], {int(k): v for k, v in row["extra"].items()}, row["num"]
        ).hex()
        == row["expected_bytes"]
    )


def test_parser_signed_arithmetic_and_unchecked_crc():
    raw = bytes.fromhex("9b002701651e02061eff01072d8002239500009d")
    status = codec.parse(raw)
    assert status == codec.Status(
        1, 6, 5, 30, 2, 2, 3, 9, 5, (codec.Alarm(6, 30, 255, 1), codec.Alarm(7, 45, 128, 2))
    )
    raw = bytearray(raw)
    raw[4], raw[15] = 0xFF, 0x80
    result = codec.parse(bytes(raw))
    assert (result.upper, result.feet, result.right, result.snore_mask) == (0, -1, -8, 0)
    assert codec.parse(bytes(raw[:-1])) is None
    raw[-1] = 0
    assert codec.parse(bytes(raw)) is None
    assert codec.parse(codec.frame(4, 2)) == codec.Status(2)
    assert codec.parse(codec.frame(1, 1)) is None


def test_alarm_flags_and_unprotected_slot():
    for value in range(256):
        assert (
            codec.flags(bool(value & 128), tuple(day for day in range(7) if value & 1 << day))
            == value
        )
    slots = (codec.Alarm(6, 30, 255, 1), codec.Alarm(7, 45, 128, 2))
    first, second = codec.alarm(slots, 1, 1), codec.alarm(slots, 2, 1)
    assert first[:1] + first[2:] == second[:1] + second[2:]
    for left in range(3):
        for right in range(3):
            assert codec.unpair(codec.pair(left, right)) == (left, right)
