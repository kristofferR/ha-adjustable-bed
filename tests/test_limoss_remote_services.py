"""Public local-memory/profile actions with all-target validation."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import voluptuous as vol
from homeassistant.exceptions import ServiceValidationError

from custom_components.adjustable_bed.const import BED_TYPE_LIMOSS_REMOTE, DOMAIN, SIDE_BOTH
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.limoss_remote_state import LimossRemoteMemory
from custom_components.adjustable_bed.services import async_register_services
from tests.test_limoss_remote import make_controller


def target(*, memory=8):
    controller = make_controller(memory=memory)
    coordinator = MagicMock(spec=AdjustableBedCoordinator)
    coordinator.name = "App target"
    coordinator.bed_type = BED_TYPE_LIMOSS_REMOTE
    coordinator.entry = SimpleNamespace(data={})
    coordinator.capability_controller = controller

    async def execute(command, **kwargs):
        return await command(controller)

    coordinator.async_execute_controller_command = AsyncMock(side_effect=execute)
    coordinator.async_execute_controller_query = AsyncMock(side_effect=execute)
    controller.start_notify = AsyncMock()  # This dispatch fixture represents a ready session.
    return coordinator, controller


@pytest.fixture
async def service_target(hass):
    await async_register_services(hass)
    coordinator, controller = target()
    with patch(
        "custom_components.adjustable_bed.services._resolve_sided_targets",
        return_value=([(coordinator, SIDE_BOTH)], []),
    ) as resolve:
        yield coordinator, controller, resolve


@pytest.mark.parametrize(
    ("service", "data", "method", "args", "kwargs"),
    [
        (
            "limoss_remote_hold_control",
            {"control": "motor_1_up", "duration": 0.125},
            "hold_control",
            ("motor_1_up", 125),
            {},
        ),
        (
            "limoss_remote_recall_memory",
            {"preset": 8, "duration": 0.5},
            "hold_memory",
            (8, 500),
            {},
        ),
        ("limoss_remote_rename_memory", {"preset": 8, "name": ""}, "rename_memory", (8, ""), {}),
        (
            "limoss_remote_calibrate",
            {"confirmed": True, "duration": 0.5},
            "hold_calibration",
            (500,),
            {"confirmed": True},
        ),
        (
            "limoss_remote_features",
            {"underbed_light": True, "massage": False},
            "set_optional_features",
            (True, False),
            {"persist": False},
        ),
    ],
)
async def test_public_actions_dispatch_live_controller(
    hass, service_target, service, data, method, args, kwargs
):
    coordinator, controller, _ = service_target
    controller.memories.slots[8] = LimossRemoteMemory("", ((0, -2147483648),))
    action = AsyncMock()
    setattr(controller, method, action)
    await hass.services.async_call(DOMAIN, service, {"device_id": "app", **data}, blocking=True)
    action.assert_awaited_once_with(*args, **kwargs)
    if service in ("limoss_remote_rename_memory", "limoss_remote_features"):
        coordinator.async_execute_controller_command.assert_not_awaited()
    else:
        assert coordinator.async_execute_controller_command.await_args.kwargs["cancel_running"] is True


@pytest.mark.parametrize(
    ("service", "data"),
    [
        ("limoss_remote_hold_control", {"control": "motor_1_up", "duration": True}),
        ("limoss_remote_hold_control", {"control": "motor_1_up", "duration": 0.099}),
        ("limoss_remote_hold_control", {"control": "motor_1_up", "duration": 60.001}),
        ("limoss_remote_hold_control", {"control": "motor_1_up", "duration": float("nan")}),
        ("limoss_remote_recall_memory", {"preset": 9, "duration": 1}),
        ("limoss_remote_recall_memory", {"preset": True, "duration": 1}),
        ("limoss_remote_calibrate", {"confirmed": "true", "duration": 1}),
        ("limoss_remote_calibrate", {"confirmed": 1, "duration": 1}),
        ("limoss_remote_features", {"underbed_light": 1, "massage": False}),
    ],
)
async def test_invalid_inputs_never_resolve_or_write(hass, service_target, service, data):
    coordinator, controller, resolve = service_target
    with pytest.raises(vol.Invalid):
        await hass.services.async_call(DOMAIN, service, {"device_id": "app", **data}, blocking=True)
    resolve.assert_not_called()
    controller.client.write_gatt_char.assert_not_called()
    coordinator.async_execute_controller_command.assert_not_awaited()


@pytest.mark.parametrize(
    ("service", "data", "invalid"),
    [
        ("limoss_remote_hold_control", {"control": "motor_3_up", "duration": 1}, "layout"),
        ("limoss_remote_recall_memory", {"preset": 8, "duration": 1}, "capacity"),
        ("goto_preset", {"preset": 8}, "empty"),
        ("limoss_remote_calibrate", {"confirmed": False, "duration": 1}, "confirm"),
    ],
)
async def test_all_targets_preflight_before_first_action(
    hass, service_target, service, data, invalid
):
    first, controller, resolve = service_target
    controller.memories.slots[8] = LimossRemoteMemory("Eight", ((0, -1),))
    second, other = target(memory=7 if invalid == "capacity" else 8)
    if invalid == "layout":
        # First device has the requested channel; the second only renders 1/2.
        from custom_components.adjustable_bed.beds.limoss_remote_protocol import (
            LimossRemoteCapabilities,
        )

        controller.capabilities = LimossRemoteCapabilities(12, 0x14, 0, 0, 8)
    if invalid != "empty":
        other.memories.slots[8] = LimossRemoteMemory("Eight", ((0, -1),))
    resolve.return_value = ([(first, SIDE_BOTH), (second, SIDE_BOTH)], [])
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN, service, {"device_id": ["first", "second"], **data}, blocking=True
        )
    first.async_execute_controller_command.assert_not_awaited()
    second.async_execute_controller_command.assert_not_awaited()
    controller.client.write_gatt_char.assert_not_called()
    other.client.write_gatt_char.assert_not_called()


async def test_rename_eighth_memory_preserves_signed_positions_without_ble(hass, service_target):
    _, controller, _ = service_target
    controller.memories.slots[8] = LimossRemoteMemory("Before", ((0, -2147483648), (1, 2147483647)))
    await hass.services.async_call(
        DOMAIN,
        "limoss_remote_rename_memory",
        {"device_id": "app", "preset": 8, "name": ""},
        blocking=True,
    )
    assert controller.memories.slots[8] == LimossRemoteMemory(
        "", ((0, -2147483648), (1, 2147483647))
    )
    controller.client.write_gatt_char.assert_not_called()
