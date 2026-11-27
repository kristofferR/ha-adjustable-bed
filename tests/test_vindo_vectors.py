"""Frozen Vindö 1.0.18 row A63 values checked through the shipping codec."""

import pytest

from custom_components.adjustable_bed.beds.linak.controller import LinakCommands
from custom_components.adjustable_bed.codec.linak import control_frame, parse_vindo_position
from custom_components.adjustable_bed.profiles import vindo
from custom_components.adjustable_bed.profiles.vindo import Opcode


@pytest.mark.parametrize(
    ("back", "legs", "expected"),
    [
        (True, None, "0b00"),
        (False, None, "0a00"),
        (None, True, "0900"),
        (None, False, "0800"),
        (True, True, "3700"),
        (True, False, "3500"),
        (False, True, "3600"),
        (False, False, "3400"),
        (None, None, "ff00"),
    ],
)
def test_motion(back, legs, expected):
    assert vindo.motion(back, legs) == bytes.fromhex(expected)


@pytest.mark.parametrize(
    ("action", "legacy", "expected"),
    [
        (Opcode.FLAT, LinakCommands.MOVE_ALL_DOWN, "0000"),
        (Opcode.STOP, LinakCommands.MOVE_STOP, "ff00"),
        (Opcode.MASSAGE_HEAD_UP, LinakCommands.MASSAGE_HEAD_UP, "8d00"),
        (Opcode.MASSAGE_HEAD_DOWN, LinakCommands.MASSAGE_HEAD_DOWN, "8e00"),
        (Opcode.MASSAGE_FOOT_UP, LinakCommands.MASSAGE_FOOT_UP, "8f00"),
        (Opcode.MASSAGE_FOOT_DOWN, LinakCommands.MASSAGE_FOOT_DOWN, "9000"),
        (Opcode.MASSAGE_TOGGLE, LinakCommands.MASSAGE_PERFORMANCE_START, "9100"),
        (Opcode.LIGHT_TOGGLE, LinakCommands.LIGHTS_TOGGLE, "9400"),
        (Opcode.LIGHT_ON, LinakCommands.LIGHTS_ON, "9200"),
        (Opcode.LIGHT_OFF, LinakCommands.LIGHTS_OFF, "9300"),
        (Opcode.LIGHT_STEP_UP, None, "9e00"),
        (Opcode.LIGHT_STEP_DOWN, None, "9f00"),
    ],
)
def test_actions(action, legacy, expected):
    assert control_frame(action) == bytes.fromhex(expected)
    if legacy is not None:
        assert legacy == bytes.fromhex(expected)


@pytest.mark.parametrize(
    ("current", "target", "expected"),
    [
        ((100, 100), (200, 200), "3700"),
        ((100, 100), (116, 115), "0b00"),
        ((100, 100), (84, 117), "3600"),
        ((100, 100), (85, 115), "ff00"),
    ],
)
def test_raw_target(current, target, expected):
    assert vindo.seek(current, target) == bytes.fromhex(expected)


@pytest.mark.parametrize(
    ("index", "expected"),
    [
        (0, "8000 9100 8100"),
        (1, "8000 9100 8100 8100"),
        (2, "8000 9100 8100 8100 8100"),
        (3, "8000 9100 8100 8100 8100 8100"),
        (4, "8000 9100 8100 8100 8100 8100 8100"),
    ],
)
def test_default_favourite(index, expected):
    assert b"".join(vindo.massage_pattern(index)) == bytes.fromhex(expected)


@pytest.mark.parametrize(
    ("data", "expected"),
    [("341299", 4660), ("ffff", 65535), ("ff", None)],
)
def test_unsigned_raw_position(data, expected):
    assert parse_vindo_position(bytes.fromhex(data)) == expected
