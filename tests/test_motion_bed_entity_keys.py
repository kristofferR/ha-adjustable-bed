"""Motion Bed entity identities follow the control's function, not its app screen."""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import replace
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from custom_components.adjustable_bed.beds.motion_bed import (
    MotionBedController,
    button_actions_for,
    motion_bed_button_key,
    motion_bed_cover_key,
)
from custom_components.adjustable_bed.motion_bed_actions import MOTION_BED_ACTIONS, MotionBedAction
from custom_components.adjustable_bed.motion_bed_models import (
    MOVEMENT_LAYOUTS,
    PRESET_VARIANTS,
    select_motion_bed,
)
from custom_components.adjustable_bed.motion_bed_protocol import SOURCE_COMMANDS

ENTITY_STRINGS = json.loads(
    (Path(__file__).parents[1] / "custom_components/adjustable_bed/strings.json").read_text()
)["entity"]
# Covers get a side suffix on single-address paired views; no cover is "both".
SIDE_VIEWS = ("", "_left", "_right")
HOME_MOVEMENTS = tuple(layout for layout in MOVEMENT_LAYOUTS if layout != "modular")
HOME_PRESETS = tuple(preset for preset in PRESET_VARIANTS if preset != "modular")


def controller(name: str = "QMS-IQ", **overrides: str) -> MotionBedController:
    coordinator = MagicMock()
    coordinator.address = "AA:BB:CC:DD:EE:01"
    return MotionBedController(coordinator, selection=select_motion_bed(name, **overrides))


def hub_with_all_modules() -> MotionBedController:
    hub = controller("TL-Q")
    hub._state = replace(
        hub._state, motor_module_present=True, air_module_present=True, thermal_module_present=True
    )
    return hub


def frames(action: MotionBedAction) -> tuple[object, ...]:
    """Frames and their state conditions, as the action would send them."""
    return action.kind, tuple(dict.fromkeys(
        (SOURCE_COMMANDS[p.source_id], p.state_key, p.expected, p.alternate, p.branch)
        for p in action.packets
    ))


def movement_pairs(ctrl: MotionBedController) -> dict[str, list[tuple[MotionBedAction, MotionBedAction]]]:
    held = {a.key: a for a in ctrl.actions if a.kind == "held" and a.owner.startswith("Weitiao")}
    pairs: dict[str, list[tuple[MotionBedAction, MotionBedAction]]] = defaultdict(list)
    for key, up in held.items():
        if key.endswith("_up"):
            pairs[motion_bed_cover_key(up)].append((up, held[key[:-3] + "_down"]))
    return pairs


@pytest.mark.parametrize("movement", HOME_MOVEMENTS)
def test_movement_covers_share_one_key_per_label_and_side(movement: str) -> None:
    ctrl = controller(movement_override=movement)
    keys = [spec.key for spec in ctrl.motor_control_specs]
    pairs = movement_pairs(ctrl)
    assert len(keys) == len(set(keys)) == len(pairs)
    for key, members in pairs.items():
        # Only byte-identical pads (W8's split and coupled LEG) share an entity.
        assert len({(frames(up), frames(down)) for up, down in members}) == 1
        for side in SIDE_VIEWS:
            assert key + side in ENTITY_STRINGS["cover"]
        label = members[0][0].name.removesuffix(" up")
        if not key.startswith(("motion_bed_left_", "motion_bed_right_")):
            assert ENTITY_STRINGS["cover"][key]["name"] == label


def test_split_pads_carry_their_side_and_w18_head_is_its_lift() -> None:
    assert {spec.key for spec in controller(movement_override="W7").motor_control_specs} == {
        "motion_bed_back", "motion_bed_legs",
        "motion_bed_left_back", "motion_bed_right_back",
        "motion_bed_left_legs", "motion_bed_right_legs",
    }
    assert {spec.key for spec in controller(movement_override="W8").motor_control_specs} == {
        "motion_bed_back", "motion_bed_legs", "motion_bed_left_back", "motion_bed_right_back",
    }
    w18 = {spec.key for spec in controller(movement_override="W18").motor_control_specs}
    assert "motion_bed_lift" in w18 and "motion_bed_head" not in w18


def test_cover_translations_are_exactly_the_reachable_keys() -> None:
    used = {
        spec.key
        for movement in HOME_MOVEMENTS
        for spec in controller(movement_override=movement).motor_control_specs
    }
    declared = {key for key in ENTITY_STRINGS["cover"] if key.startswith("motion_bed_")}
    assert declared == {key + side for key in used for side in SIDE_VIEWS}


def _profiles() -> list[MotionBedController]:
    home = [
        controller(preset_override=preset, movement_override=movement)
        for preset in HOME_PRESETS
        for movement in HOME_MOVEMENTS
    ]
    return [*home, hub_with_all_modules(), controller("TL-B"), controller("TL-A"), controller("TL-W")]


def test_buttons_shared_by_visible_screens_send_identical_frames() -> None:
    for ctrl in _profiles():
        owners = ctrl._active_owners()
        specs = ctrl.controller_button_specs
        assert len({spec.key for spec in specs}) == len(specs)
        members: dict[str, set[tuple[object, ...]]] = defaultdict(set)
        for action in MOTION_BED_ACTIONS:
            if action.owner in owners and (key := motion_bed_button_key(action)) in button_actions_for(owners):
                members[key].add(frames(action))
        assert all(len(signatures) == 1 for signatures in members.values()), ctrl.selection


def test_button_identity_survives_layout_changes_and_keeps_module_meaning() -> None:
    k1 = {spec.key for spec in controller(preset_override="K1").controller_button_specs}
    k9 = {spec.key for spec in controller(preset_override="K9").controller_button_specs}
    assert {"motion_bed_flat", "motion_bed_memory1", "motion_bed_sync", "motion_bed_stop"} <= k1 & k9
    home_sync = [spec for spec in controller().controller_button_specs if spec.key == "motion_bed_sync"]
    assert len(home_sync) == 1  # Preset, movement, massage and light screens share it.
    air = {spec.key for spec in controller("TL-A").controller_button_specs}
    assert {"motion_bed_air_yujia", "motion_bed_air_lumbar"} <= air
    assert not {"motion_bed_yujia", "motion_bed_lumbar"} & air
    # The motor module's preview routes the hub to that module before sending.
    motor = button_actions_for(controller("TL-B")._active_owners())
    assert motor["motion_bed_audio_preview_1"].owner == "DianDongSetActivity"
