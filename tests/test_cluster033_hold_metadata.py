"""Approved flat hold metadata; admission races remain a separate root dependency."""

from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.adjustable_bed.beds.base import (
    ControllerButtonSpec,
    ControllerHoldSpec,
    ControllerMotorHoldSpec,
)
from custom_components.adjustable_bed.beds.cluster033 import AppController
from custom_components.adjustable_bed.beds.serta_mp_remote import SertaMPRemoteController
from custom_components.adjustable_bed.button import (
    ControllerActionButton,
    _combined_motor_buttons_for,
)
from custom_components.adjustable_bed.cluster033_profiles import APP_LAYOUTS, app_profile
from custom_components.adjustable_bed.cover import AdjustableBedCover, _build_cover_description

from .test_cluster033 import coordinator


def entity_runtime():
    return SimpleNamespace(
        entity_side="left",
        device_info={},
        name="App left",
        entity_unique_id=lambda key: "left_" + key,
        entity_translation_key=lambda key: key + "_left",
        async_execute_controller_command=AsyncMock(),
    )


@pytest.mark.parametrize(
    "app,layout", [(app, layout) for app, layouts in APP_LAYOUTS.items() for layout in layouts]
)
def test_source_owned_specs_project_flat_metadata_and_keep_side(app, layout):
    ctrl = AppController(coordinator(), app_profile(app, layout))
    runtime = entity_runtime()
    delay = 300 if app == "qplus_app" and layout == "MX" else 0
    source_actions = {action.key: action for action in ctrl.profile.actions}
    for spec in ctrl.controller_button_specs:
        button = ControllerActionButton(runtime, spec)
        attrs = button.extra_state_attributes
        assert attrs["bed_side"] == "left"
        if spec.key in source_actions and source_actions[spec.key].mode in ("held", "held_zeros"):
            assert spec.hold == ControllerHoldSpec(spec.key, 0, delay)
            assert attrs == {
                "bed_side": "left",
                "held_control": spec.key,
                "hold_start_delay_ms": 0,
                "hold_release_delay_ms": delay,
            }
            assert attrs["held_control"] in ctrl.held_control_options
        else:
            assert spec.hold is None
            assert attrs == {"bed_side": "left"}
    for spec in ctrl.motor_control_specs:
        cover = AdjustableBedCover(runtime, _build_cover_description(spec))
        up, down = ("head_up", "head_down") if spec.key == "back" else ("foot_up", "foot_down")
        assert cover.entity_description.hold == ControllerMotorHoldSpec(up, down, 0, delay)
        assert cover.extra_state_attributes == {
            "bed_side": "left",
            "held_control_up": up,
            "held_control_down": down,
            "hold_start_delay_ms": 0,
            "hold_release_delay_ms": delay,
        }


def test_serta_local_angle_hold_metadata_is_distinct_from_remote_motor_keys():
    ctrl = SertaMPRemoteController(coordinator())
    for axis in ("head", "foot"):
        for direction in ("up", "down"):
            key = f"{axis}_target_{direction}"
            spec = next(s for s in ctrl.controller_button_specs if s.key == key)
            assert spec.hold == ControllerHoldSpec(key, 0, 0)
            assert key in ctrl.held_control_options
    assert next(s for s in ctrl.motor_control_specs if s.key == "back").hold.up_control == "head_up"


async def test_mixed_parent_hold_intersection_retains_finite_commands_and_own_resource():
    left = AppController(coordinator(), app_profile("qplus_app", "M2"))
    right = AppController(coordinator(), app_profile("qplus_app", "MX"))
    parent = MagicMock(pair_id="pair", device_info={}, children={}, connection_mode="concurrent")
    parent.async_execute_controller_command = AsyncMock()
    runtimes = [SimpleNamespace(capability_controller=ctrl) for ctrl in (left, right)]
    buttons = _combined_motor_buttons_for(parent, runtimes)
    assert len(buttons) == 4
    for button in buttons:
        # Same key names do not erase P1 immediate-zero vs MX delayed-query release.
        assert "held_control" not in button.extra_state_attributes
        await button.async_press()
        kwargs = parent.async_execute_controller_command.await_args.kwargs
        assert kwargs["side"] == "both" and kwargs["cancel_running"] is True
    assert (
        _combined_motor_buttons_for(
            parent, [runtimes[0], SimpleNamespace(capability_controller=None)]
        )
        == []
    )


def test_parent_hold_intersection_is_direction_specific_and_requires_all_sides():
    ctrl = AppController(coordinator(), app_profile("tempur_curve"))
    left = ctrl.motor_control_specs[0]
    right = replace(left, hold=replace(left.hold, up_control="different_up"))
    parent = MagicMock(pair_id="pair", device_info={}, children={}, connection_mode="concurrent")

    def sides(specs):
        return [
            SimpleNamespace(
                capability_controller=SimpleNamespace(
                    supports_motor_control=True,
                    has_discrete_motor_control=False,
                    motor_control_specs=(spec,),
                )
            )
            for spec in specs
        ]

    buttons = _combined_motor_buttons_for(parent, sides((left, right)))
    up = next(b for b in buttons if b._direction == "up")
    down = next(b for b in buttons if b._direction == "down")
    assert "held_control" not in up.extra_state_attributes
    assert down.extra_state_attributes["held_control"] == "head_down"
    assert down.extra_state_attributes["hold_release_delay_ms"] == 0
    buttons = _combined_motor_buttons_for(parent, sides((left, replace(left, hold=None))))
    assert len(buttons) == 2
    assert all("held_control" not in b.extra_state_attributes for b in buttons)


def test_legacy_entities_without_optional_hold_keep_base_attributes():
    runtime = entity_runtime()
    # Use the real defaulted spec for action projection and a duck description
    # for the older cover-description shape that predates the optional field.
    button = ControllerActionButton(runtime, ControllerButtonSpec("legacy", "Legacy", AsyncMock()))
    assert button.extra_state_attributes == {"bed_side": "left"}
    ctrl = AppController(coordinator(), app_profile("tempur_curve"))
    cover = AdjustableBedCover(
        runtime, replace(_build_cover_description(ctrl.motor_control_specs[0]), hold=None)
    )
    assert cover.extra_state_attributes == {"bed_side": "left"}


async def test_sequential_parent_with_identical_capabilities_keeps_only_finite_fallback():
    ctrl = AppController(coordinator(), app_profile("tempur_curve"))
    parent = MagicMock(pair_id="pair", device_info={}, children={}, connection_mode="sequential")
    parent.async_execute_controller_command = AsyncMock()
    runtimes = [SimpleNamespace(capability_controller=ctrl)] * 2
    buttons = _combined_motor_buttons_for(parent, runtimes)
    assert len(buttons) == 4
    assert all("held_control" not in button.extra_state_attributes for button in buttons)
    await buttons[0].async_press()
    parent.async_execute_controller_command.assert_awaited_once()


def test_legacy_entity_without_base_attribute_dictionary_does_not_break_projection():
    runtime = entity_runtime()
    runtime.entity_side = None
    button = ControllerActionButton(runtime, ControllerButtonSpec("legacy", "Legacy", AsyncMock()))
    assert button.extra_state_attributes == {}
    ctrl = AppController(coordinator(), app_profile("tempur_curve"))
    cover = AdjustableBedCover(
        runtime, replace(_build_cover_description(ctrl.motor_control_specs[0]), hold=None)
    )
    assert cover.extra_state_attributes is None


def test_legacy_motor_spec_without_new_field_keeps_cover_and_parent_finite_fallback():
    from dataclasses import fields

    ctrl = AppController(coordinator(), app_profile("tempur_curve"))
    spec = ctrl.motor_control_specs[0]
    legacy = SimpleNamespace(
        **{field.name: getattr(spec, field.name) for field in fields(spec) if field.name != "hold"}
    )
    assert _build_cover_description(legacy).hold is None
    parent = MagicMock(pair_id="pair", device_info={}, children={}, connection_mode="concurrent")
    child = SimpleNamespace(
        capability_controller=SimpleNamespace(
            supports_motor_control=True,
            has_discrete_motor_control=False,
            motor_control_specs=(legacy,),
        )
    )
    buttons = _combined_motor_buttons_for(parent, [child, child])
    assert len(buttons) == 2
    assert all("held_control" not in button.extra_state_attributes for button in buttons)
