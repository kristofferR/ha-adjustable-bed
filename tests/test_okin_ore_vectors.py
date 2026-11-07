"""Okin ORE frames: the frozen BOX1220 literals round-trip through ``codec/okin_ore.py``.

The literals are the pre-v5 payloads of the Sleepy's Elite and AdjustableM5X4
BOX1220 route tables, which the codec now builds.
"""

from __future__ import annotations

import pytest

from custom_components.adjustable_bed.beds.okin_ore import OkinOreCommands
from custom_components.adjustable_bed.codec import okin_ore

BOX1220_FRAMES: frozenset[str] = frozenset(
    {
        "a55adf00002000",
        "a55ade00002001",
        "a55add00002002",
        "a55adc00002003",
        "a55adb00002004",
        "a55a7900002066",
        "a55a7a00002065",
        "a55a7b00002064",
        "a55a7c00002063",
        "a55a7d00002062",
        "a55a7e00002061",
        "a55a7f00002060",
        "a55a5f00002080",
    }
)


@pytest.mark.parametrize("literal", sorted(BOX1220_FRAMES))
def test_literal_round_trips(literal: str) -> None:
    frame = bytes.fromhex(literal)
    assert okin_ore.frame(int.from_bytes(frame[5:7], "big")) == frame


def test_controller_stop_is_a_frozen_frame() -> None:
    assert okin_ore.frame(OkinOreCommands.CMD_STOP).hex() in BOX1220_FRAMES


@pytest.mark.parametrize("command", [-1, 0x10000, True])
def test_rejects_commands_outside_16_bits(command: int) -> None:
    with pytest.raises(ValueError):
        okin_ore.frame(command)
