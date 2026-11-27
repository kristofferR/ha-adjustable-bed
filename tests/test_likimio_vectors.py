"""Independent packet literals from the frozen Likimio 1.0.2 report."""

import json
from pathlib import Path

import pytest

from custom_components.adjustable_bed.beds.dreamsense.protocol import light_seconds
from custom_components.adjustable_bed.codec import richmat as codec
from custom_components.adjustable_bed.profiles.likimio import ABM10, PROFILES

VECTORS = json.loads((Path(__file__).parent / "fixtures/likimio/vectors.json").read_text())
CONTROLS = {
    "head_up": "HeadUp",
    "head_down": "HeadDown",
    "foot_up": "FootUp",
    "foot_down": "FootDown",
    "head_and_foot_up": "HeadAndFootUp",
    "head_and_foot_down": "HeadAndFootDown",
    "flat": "MotorReset",
    "underbed_light": "BedLight",
    "massage_head_increase": "MassageHeadInstensityStrengthen",
    "massage_foot_increase": "MassageFootInstensityStrengthen",
    "massage_mode_cycle": "MassageModeChange",
    "massage_all_off": "MassageModeAllOff",
    "massage_timer_10_min": "Massage10MinuteTimer",
    "massage_timer_20_min": "Massage20MinuteTimer",
    "massage_timer_30_min": "Massage30MinuteTimer",
    "zero_gravity": "ZeroGravity",
    "anti_snore": "AntiSnoring",
    "memory_1": "MemoryPosition1",
    "memory_2": "MemoryPosition2",
}
FUNCTIONS = {
    "exit_limit": (0, "deviceFunctionItemExitLimit"),
    "check_clock": (1, "deviceFunctionItemCheckClock"),
    "check_light": (1, "deviceFunctionItemCheckLight"),
    "check_music": (1, "deviceFunctionItemCheckMusic"),
    "light_close": (0x75, ""),
    "stop": (codec.STOP, ""),
}


@pytest.mark.parametrize(
    "action,single,inputs,expected", [row[1:] for row in VECTORS], ids=[row[0] for row in VECTORS]
)
def test_frozen_packets(action, single, inputs, expected):
    profile = PROFILES[ABM10]
    if action == "light_timeout":
        actual = light_seconds(inputs["seconds"])
    elif action == "light_rgb":
        actual = codec.rgb(*inputs["rgb"])
    elif action == "single_alarm_cancel_default":
        low, high = codec.countdown(0, 0)
        actual = low if inputs["clock_half"] == "low" else high
    elif action in FUNCTIONS:
        code, function = FUNCTIONS[action]
        actual = profile.frame(code, single=single, action=function)
    else:
        control = CONTROLS[action.removesuffix("_recall").removesuffix("_save")]
        row = next(row for row in profile.controls if row.action == control)
        code = row.save if action.endswith("_save") else row.code
        assert code is not None
        actual = profile.frame(code, single=single)
    assert actual == bytes.fromhex(expected)
