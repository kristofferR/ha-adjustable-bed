"""Native entity and action surfaces preserve command serialization and slots7/8."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.exceptions import ServiceValidationError

from custom_components.adjustable_bed import const, services
from custom_components.adjustable_bed.button import (
    BUTTON_DESCRIPTIONS,
    ControllerActionButton,
    _discovered_memory_slot_name,
    _should_add_button,
)
from tests.test_fsm_relax import make_controller


def test_all_eight_memory_buttons_truthful_capability_gating_and_names():
    ctrl = make_controller()
    c = ctrl._coordinator
    c.controller = ctrl
    memory = [d for d in BUTTON_DESCRIPTIONS if d.memory_slot is not None]
    assert {d.memory_slot for d in memory} == set(range(1, 9))
    for description in memory:
        assert _should_add_button(description, ctrl, False)
        assert (
            _discovered_memory_slot_name(c, description)
            == ("Save " if description.is_program_button else "") + f"M{description.memory_slot}"
        )
    ctrl._accept_body(bytes.fromhex("0208000006"))
    for description in memory:
        assert _should_add_button(description, ctrl, False) == (description.memory_slot <= 6)


async def test_named_action_callback_executes_current_controller_through_queue():
    old = make_controller()
    current = make_controller()
    c = old._coordinator
    current.hold_control = AsyncMock()

    async def execute(fn, **_kwargs):
        await fn(current)

    c.async_execute_controller_command = AsyncMock(side_effect=execute)
    c.entity_unique_id.side_effect = lambda key: key
    button = ControllerActionButton(c, old.controller_button_specs[0])
    await button.async_press()
    c.async_execute_controller_command.assert_awaited_once()
    assert c.async_execute_controller_command.call_args.kwargs == {"cancel_running": True}
    current.hold_control.assert_awaited_once_with("command_22", 120)


@pytest.mark.parametrize("calibration", (False, True))
async def test_service_preflight_serialized_current_action(calibration):
    ctrl = make_controller()
    ctrl.calibrate = AsyncMock()
    ctrl.recall_memory = AsyncMock()
    c = ctrl._coordinator
    c.bed_type = const.BED_TYPE_FSM_RELAX
    call = SimpleNamespace(
        hass=MagicMock(),
        data={"device_id": ["device"], "preset": 8, "duration": 0.12, "confirmed": True},
    )

    async def preflight(targets, capability, label, validator):
        validator(ctrl)

    async def execute(coordinator, side, fn, **kwargs):
        assert kwargs["cancel_running"] is True
        await fn(ctrl)

    with (
        patch.object(services, "_resolve_sided_targets", return_value=([(c, "both")], [])),
        patch.object(services, "_command_targets", return_value=[c]),
        patch.object(services, "_preflight_capability", side_effect=preflight),
        patch.object(services, "_execute_sided", side_effect=execute),
    ):
        await services._fsm_relax_operation(call, calibration=calibration)
    if calibration:
        ctrl.calibrate.assert_awaited_once_with(confirmed=True)
    else:
        ctrl.recall_memory.assert_awaited_once_with(8, hold_ms=120)


async def test_false_confirmation_and_wrong_profile_fail_before_execution():
    c = MagicMock(bed_type=const.BED_TYPE_LIMOSS)
    call = SimpleNamespace(hass=MagicMock(), data={"device_id": ["device"], "confirmed": False})
    with (
        patch.object(services, "_resolve_sided_targets", return_value=([(c, "both")], [])),
        patch.object(services, "_command_targets", return_value=[c]),
        patch.object(services, "_execute_sided", AsyncMock()) as execute,
    ):
        with pytest.raises(ServiceValidationError, match="confirmation"):
            await services._fsm_relax_operation(call, calibration=True)
        call.data["confirmed"] = True
        with pytest.raises(ServiceValidationError, match="profile"):
            await services._fsm_relax_operation(call, calibration=True)
        execute.assert_not_called()
