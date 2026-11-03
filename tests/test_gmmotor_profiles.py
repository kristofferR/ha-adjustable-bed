"""Product admission, nested membership and actual GM Control UI transitions."""

import pytest

from custom_components.adjustable_bed.gmmotor_catalog import PROFILES, ROUTES
from custom_components.adjustable_bed.gmmotor_profiles import load_profile


def test_host_admission_and_nested_profiles() -> None:
    assert len(ROUTES) == 834
    assert len(PROFILES) == 824
    assert "QLRN" not in ROUTES  # Compiled into the library, not admitted by this app.
    assert ROUTES["ZRS3"] == ("remote_choice", ("APRM", "AQRM"))
    with pytest.raises(ValueError):
        load_profile("ZRS3")
    with pytest.raises(ValueError):
        load_profile("QLRN")
    default = load_profile("V9RM")
    standard, split = load_profile("V9RM:0"), load_profile("V9RM:1")
    assert len(standard.controls) != len(split.controls)
    assert standard.sides == (0,)
    assert split.sides == (0, 1)
    assert default.key != standard.key


def test_repeat_light_sleep_fields_are_independent() -> None:
    ftrn = load_profile("FTRN")
    assert ftrn.repeat_alarm
    assert ftrn.sleep_kind == "none"
    assert load_profile("6BRM").has_light
    assert not load_profile("6BRM").repeat_alarm


def test_brrm_visible_preset_uses_captured_material_in_each_state() -> None:
    profile = load_profile("BRRM")
    controls = [
        action
        for action in profile.controls
        if action.material.name == "deviceFunctionItemZeroGravity"
    ]
    # This visible button is state-dependent: the app can replace its material
    # with None and send opcode zero. Using the visible enum's 0x45 is wrong.
    action = next(
        a
        for a in controls
        if a.apply(1, "normal", side=0, single=False)[1] == bytes.fromhex("6e0100006f")
    )
    assert action.apply(1, "normal", side=1, single=False) == (1, bytes.fromhex("6e01010070"))
    assert action.apply(1, "normal", side=1, single=True) == (1, b"\x00")


def test_arm_memory_transition_and_next_action_clears_it() -> None:
    profile = load_profile("E3RM")
    arm = next(a for a in profile.controls if a.material.name == "deviceFunctionItemMemory")
    assert arm.apply(0, "normal", side=0, single=False) == (4, bytes.fromhex("6e0100006f"))
    preset = next(
        a for a in profile.controls if a.material.name == "deviceFunctionItemMemoryPosition1"
    )
    assert preset.apply(4, "normal", side=0, single=False) == (0, bytes.fromhex("6e01002b9a"))
    assert preset.apply(0, "normal", side=0, single=False) == (0, bytes.fromhex("6e01002e9d"))


def test_sustain_release_is_side_scoped_and_single_override_is_short_only() -> None:
    profile = load_profile("6BRM")
    action = next(
        a for a in profile.controls if a.material.name == "deviceFunctionItemHeadAndFootDown"
    )
    assert action.gesture == 1
    assert action.apply(0, "normal", side=0, single=False)[1] == bytes.fromhex("6e01002a99")
    assert action.apply(0, "normal", side=0, single=True)[1] == b"\x39"
    assert action.apply(0, "release", side=2, single=False)[1] == bytes.fromhex("6e01026edf")
    with pytest.raises(ValueError):
        action.apply(0, "long", side=0, single=False)
