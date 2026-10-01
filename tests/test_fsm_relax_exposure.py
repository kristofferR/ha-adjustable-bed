"""Native entity and action surfaces preserve command serialization and slots7/8."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bleak.exc import BleakError
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed import const, services
from custom_components.adjustable_bed.beds.fsm_relax import FsmRelaxController, build_packet
from custom_components.adjustable_bed.button import (
    BUTTON_DESCRIPTIONS,
    ControllerActionButton,
    _discovered_memory_slot_name,
    _should_add_button,
)
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
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
    ctrl.local.slots[8] = {0: -1}
    ctrl._subscribed = True
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


async def _actual_memory_target(hass: HomeAssistant, address: str) -> AdjustableBedCoordinator:
    entry = MockConfigEntry(domain=const.DOMAIN, data={
        CONF_ADDRESS: address,
        const.CONF_BED_TYPE: const.BED_TYPE_FSM_RELAX,
        const.CONF_FSM_RELAX_LAYOUT: "bed",
        const.CONF_DISCONNECT_AFTER_COMMAND: False,
        const.CONF_MOTOR_PULSE_COUNT: 1,
    })
    entry.add_to_hass(hass)
    coordinator = AdjustableBedCoordinator(hass, entry)
    coordinator._client = make_controller().client
    controller = await create_controller(
        coordinator, const.BED_TYPE_FSM_RELAX, None, coordinator.client
    )
    assert isinstance(controller, FsmRelaxController)
    coordinator._controller = controller
    await controller.start_notify()
    coordinator.client.start_notify.call_args.args[1](
        None, bytearray(build_packet(bytes.fromhex("0208000008"), 9))
    )
    controller.local.slots[8] = {0: -1, 2: -(2**31)}
    return coordinator


async def _close_memory_targets(*targets: AdjustableBedCoordinator) -> None:
    for target in targets:
        target._cancel_disconnect_timer()
        target._cancel_diagnostic_polling()
        await target._command_scheduler.async_shutdown()
        assert target.controller is not None
        await target.controller.stop_notify()


@pytest.mark.parametrize("service", ("goto_preset", "fsm_relax_recall_memory"))
@pytest.mark.parametrize("invalid", (
    "missing", "motor_zero", "raw_overflow", "raw_bool", "index", "quarantined",
    "shared_quarantine", "query_failure", "query_failure_reconstructed", "subscription",
    "capabilities",
))
async def test_registered_memory_preflight_rejects_all_targets_before_writes(
    hass: HomeAssistant, service: str, invalid: str,
):
    first = await _actual_memory_target(hass, "AA:BB:CC:DD:EE:01")
    second = await _actual_memory_target(hass, "AA:BB:CC:DD:EE:02")
    controller = second.controller
    assert isinstance(controller, FsmRelaxController)
    if invalid == "missing":
        controller.local.slots.clear()
    elif invalid == "motor_zero":
        controller.local.slots[8] = {1: 7}
    elif invalid == "raw_overflow":
        controller.local.slots[8] = {0: 2**31}
    elif invalid == "raw_bool":
        controller.local.slots[8] = {0: True}
    elif invalid == "index":
        controller.local.slots[8] = {0: 1, 4: 2}
    elif invalid == "quarantined":
        controller._quarantine()
    elif invalid == "shared_quarantine":
        controller.local.session.quarantine_client = second.client
        assert not controller._quarantined
    elif invalid in ("query_failure", "query_failure_reconstructed"):
        await controller.local.async_save_slot(8, controller.local.slots[8])
        await controller.local.async_save_capabilities(bytes.fromhex("0208000008"))
        second.client.write_gatt_char.side_effect = BleakError("uncertain memory query")
        with pytest.raises(BleakError):
            await controller.program_memory(8)
        assert controller._quarantined
        second.client.write_gatt_char.reset_mock(side_effect=True)
        if invalid == "query_failure_reconstructed":
            await controller.stop_notify()
            controller = await create_controller(
                second, const.BED_TYPE_FSM_RELAX, None, second.client
            )
            assert isinstance(controller, FsmRelaxController)
            second._controller = controller
            assert not controller._quarantined
            assert controller.local.session.quarantine_client is second.client
    elif invalid == "subscription":
        controller._subscribed = False
    else:
        controller._live_capabilities = False
    await services.async_register_services(hass)
    data = {"device_id": ["first", "second"], "preset": 8}
    if service == "fsm_relax_recall_memory":
        data["duration"] = 0.12
    try:
        with (
            patch.object(services, "_resolve_sided_targets", return_value=(
                [(first, const.SIDE_BOTH), (second, const.SIDE_BOTH)], [],
            )),
            pytest.raises(ServiceValidationError),
        ):
            await hass.services.async_call(const.DOMAIN, service, data, blocking=True)
        first.client.write_gatt_char.assert_not_called()
        second.client.write_gatt_char.assert_not_called()
    finally:
        await _close_memory_targets(first, second)


@pytest.mark.parametrize("service", ("goto_preset", "fsm_relax_recall_memory"))
async def test_registered_memory_preflight_preserves_valid_sparse_recall(
    hass: HomeAssistant, service: str,
):
    from tests.test_fsm_relax import bodies

    first = await _actual_memory_target(hass, "AA:BB:CC:DD:EE:01")
    second = await _actual_memory_target(hass, "AA:BB:CC:DD:EE:02")
    await services.async_register_services(hass)
    data = {"device_id": ["first", "second"], "preset": 8}
    if service == "fsm_relax_recall_memory":
        data["duration"] = 0.12
    try:
        with patch.object(services, "_resolve_sided_targets", return_value=(
            [(first, const.SIDE_BOTH), (second, const.SIDE_BOTH)], [],
        )):
            await hass.services.async_call(const.DOMAIN, service, data, blocking=True)
        for target in (first, second):
            assert isinstance(target.controller, FsmRelaxController)
            assert bodies(target.controller) == [
                bytes.fromhex("11ffffffff"), bytes.fromhex("3180000000"),
                *[bytes.fromhex("0300000000")] * 5,
            ]
    finally:
        await _close_memory_targets(first, second)


async def test_memory_preflight_offline_and_bound_views_preserve_device_local_rules(
    hass: HomeAssistant,
):
    target = await _actual_memory_target(hass, "AA:BB:CC:DD:EE:02")
    controller = target.controller
    assert isinstance(controller, FsmRelaxController)
    try:
        await controller.stop_notify()
        target.client.is_connected = False
        for side in (const.SIDE_LEFT, const.SIDE_RIGHT):
            bound = controller.bind_side(side)
            bound.validate_memory_recall(8)
            assert controller.local.slots[8] == {0: -1, 2: -(2**31)}
            assert controller._command_side.get() is None
        controller._quarantine()
        target._client = None
        with pytest.raises(ValueError, match="quarantined"):
            controller.bind_side(const.SIDE_RIGHT).validate_memory_recall(8)
        target._client = make_controller().client
        target.client.is_connected = False
        with pytest.raises(ConnectionError, match="subscription"):
            await controller.recall_memory(8, hold_ms=120)
        target.client.write_gatt_char.assert_not_called()
    finally:
        await _close_memory_targets(target)


@pytest.mark.parametrize("service", ("goto_preset", "fsm_relax_recall_memory"))
async def test_registered_memory_recall_valid_offline_snapshot_reconnects_before_execution(
    hass: HomeAssistant, service: str,
):
    target = await _actual_memory_target(hass, "AA:BB:CC:DD:EE:02")
    controller = target.controller
    assert isinstance(controller, FsmRelaxController)
    client = target.client
    assert isinstance(client, MagicMock)
    await controller.stop_notify()
    client.is_connected = False
    target._controller = None
    target._offline_controller = controller
    target._client = None
    await services.async_register_services(hass)

    async def reconnect(**_kwargs) -> bool:
        # Validation must have kept the client-free snapshot and written nothing.
        client.write_gatt_char.assert_not_called()
        assert not controller._subscribed and not controller._live_capabilities
        target._client = client
        target._controller = controller
        client.is_connected = True
        await controller.start_notify()
        client.start_notify.call_args.args[1](
            None, bytearray(build_packet(bytes.fromhex("0208000008"), 10))
        )
        return True

    data = {"device_id": ["target"], "preset": 8}
    if service == "fsm_relax_recall_memory":
        data["duration"] = 0.12
    try:
        with (
            patch.object(services, "_resolve_sided_targets", return_value=(
                [(target, const.SIDE_BOTH)], [],
            )),
            patch.object(target, "async_ensure_connected", side_effect=reconnect) as ensure,
        ):
            await hass.services.async_call(const.DOMAIN, service, data, blocking=True)
        ensure.assert_called()
        assert client.write_gatt_char.await_count == 7
    finally:
        target._controller = controller
        target._client = client
        await _close_memory_targets(target)
