"""Frozen Dreamlab Control 5.1.8 command literals, checked on the shared codec."""

import pytest

from custom_components.adjustable_bed.beds.richmat_classic import protocol as frames
from custom_components.adjustable_bed.codec.richmat import light_timer


@pytest.mark.parametrize(
    ("wire", "mode", "operand", "expected"),
    [
        ("FRAMED", 0, "24", "6e01002493"),
        ("FRAMED", 0, "25", "6e01002594"),
        ("FRAMED", 1, "24", "6e01012494"),
        ("FRAMED", 0, "84", "6e010084f3"),
        ("RAW", 0, "84", "84"),
        ("RAW", 0, "34", "34"),
        ("RAW", 0, "42", "42"),
        ("RAW", 0, "2b", "2b"),
        ("FRAMED", 0, "21", "6e01002190"),
        ("FRAMED", 0, "22", "6e01002291"),
        ("RAW", 0, "21", "21"),
        ("RAW", 0, "22", "22"),
    ],
)
def test_dreamlab_control(wire: frames.Wire, mode: int, operand: str, expected: str) -> None:
    assert frames.control(bytes.fromhex(operand), wire, mode) == bytes.fromhex(expected)


def test_dreamlab_release() -> None:
    assert frames.release("FRAMED") == bytes.fromhex("6e01006edd")
    assert frames.release("FRAMED", 2) == bytes.fromhex("6e01026edf")
    assert frames.release("RAW") == bytes.fromhex("6e")


def test_dreamlab_direct_frames() -> None:
    assert bytes.fromhex("6e02010071") == frames.INITIALIZE
    assert bytes.fromhex("6e08010178") == frames.ALARM_QUERY
    assert bytes.fromhex("6e0a000179") == frames.LAMP_QUERY
    assert bytes.fromhex("6e1a000088") == frames.AROMA_QUERY
    assert frames.rgb(255, 128, 1) == bytes.fromhex("6e0cffff786e0d8001fc")
    assert light_timer(1, 44) == bytes.fromhex("6e0b012ca6")
    assert frames.alarm(1440, 0x58) == (bytes.fromhex("6e05a00013"), bytes.fromhex("6e060558d1"))
    assert frames.alarm(0, 0) == (bytes.fromhex("6e05000073"), bytes.fromhex("6e06000074"))
    assert tuple(frames.aroma(op, value) for op, value in ((0x1B, 10), (0x1C, 60), (0x1D, 12))) == (
        bytes.fromhex("6e1b000a93"),
        bytes.fromhex("6e1c003cc6"),
        bytes.fromhex("6e1d000c97"),
    )
    assert [frames.control(bytes((op,)), "FRAMED") for op in (0x5F, 0x63, 0x61)] == [
        bytes.fromhex("6e01005fce"),
        bytes.fromhex("6e010063d2"),
        bytes.fromhex("6e010061d0"),
    ]
