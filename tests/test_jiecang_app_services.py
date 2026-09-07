"""Service validation and serialized dispatch for the Jiecang app controllers."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import voluptuous as vol
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError

from custom_components.adjustable_bed.const import (
    BED_TYPE_JIECANG_APP,
    BED_TYPE_LINAK,
    DOMAIN,
    SIDE_BOTH,
    SIDE_RIGHT,
)
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.paired_coordinator import PairedBedCoordinator
from custom_components.adjustable_bed.services import (
    SERVICE_JIECANG_RENAME,
    SERVICE_JIECANG_SET_ALARM,
    SERVICE_JIECANG_STOP_WAKE,
    SERVICE_JIECANG_WAKE,
    async_register_services,
)


@pytest.fixture
async def service_target(hass: HomeAssistant):
    """Use real registered schemas and dispatch with a client-free controller."""
    await async_register_services(hass)
    controller = SimpleNamespace(
        supports_clock_alarm=True,
        supports_wake_routine=True,
        supports_device_rename=True,
        configure_clock_alarm=AsyncMock(),
        execute_wake_routine=AsyncMock(),
        stop_wake_routine=AsyncMock(),
        rename_device=AsyncMock(),
    )
    coordinator = MagicMock(spec=AdjustableBedCoordinator)
    coordinator.name = "Jiecang bed"
    coordinator.bed_type = BED_TYPE_JIECANG_APP
    coordinator.capability_controller = controller

    async def execute(command, **kwargs):
        await command(controller)

    coordinator.async_execute_controller_command = AsyncMock(side_effect=execute)
    with patch(
        "custom_components.adjustable_bed.services._resolve_sided_targets",
        return_value=([(coordinator, SIDE_BOTH)], []),
    ) as resolve:
        yield coordinator, controller, resolve


async def test_alarm_converts_weekdays_and_time_without_interrupting_motion(
    hass: HomeAssistant, service_target
):
    coordinator, controller, _ = service_target
    await hass.services.async_call(
        DOMAIN,
        SERVICE_JIECANG_SET_ALARM,
        {
            "device_id": "bed",
            "enabled": True,
            "time": "07:35:00",
            "weekdays": ["monday", "friday", "sunday"],
            "preset": "yoga",
            "head_level": 3,
            "foot_level": 2,
        },
        blocking=True,
    )
    controller.configure_clock_alarm.assert_awaited_once_with(
        enabled=True,
        weekdays=(0, 4, 6),
        hour=7,
        minute=35,
        preset="yoga",
        head_level=3,
        foot_level=2,
    )
    kwargs = coordinator.async_execute_controller_command.await_args.kwargs
    assert kwargs["cancel_running"] is False
    assert kwargs["resource"] == "configuration"


async def test_alarm_can_be_disabled_with_default_fields(hass: HomeAssistant, service_target):
    _, controller, _ = service_target
    await hass.services.async_call(
        DOMAIN,
        SERVICE_JIECANG_SET_ALARM,
        {"device_id": "bed", "enabled": False},
        blocking=True,
    )
    controller.configure_clock_alarm.assert_awaited_once_with(
        enabled=False,
        weekdays=(),
        hour=0,
        minute=0,
        preset="flat",
        head_level=0,
        foot_level=0,
    )


async def test_wake_uses_coordinator_cancellation(hass: HomeAssistant, service_target):
    coordinator, controller, _ = service_target
    await hass.services.async_call(
        DOMAIN,
        SERVICE_JIECANG_WAKE,
        {
            "device_id": "bed",
            "preset": "memory_2",
            "head_level": 1,
            "foot_level": 2,
        },
        blocking=True,
    )
    controller.execute_wake_routine.assert_awaited_once_with(
        preset="memory_2", head_level=1, foot_level=2
    )
    assert coordinator.async_execute_controller_command.await_args.kwargs["cancel_running"]


async def test_rename_is_serialized_as_configuration(hass: HomeAssistant, service_target):
    coordinator, controller, _ = service_target
    await hass.services.async_call(
        DOMAIN,
        SERVICE_JIECANG_RENAME,
        {"device_id": "bed", "name": "MyBed"},
        blocking=True,
    )
    controller.rename_device.assert_awaited_once_with("MyBed")
    kwargs = coordinator.async_execute_controller_command.await_args.kwargs
    assert kwargs["cancel_running"] is False
    assert kwargs["resource"] == "configuration"


@pytest.mark.parametrize(
    ("service", "data", "capability"),
    [
        (SERVICE_JIECANG_SET_ALARM, {"enabled": True}, "supports_clock_alarm"),
        (SERVICE_JIECANG_WAKE, {}, "supports_wake_routine"),
        (SERVICE_JIECANG_STOP_WAKE, {}, "supports_wake_routine"),
        (SERVICE_JIECANG_RENAME, {"name": "Bed"}, "supports_device_rename"),
    ],
)
async def test_all_targets_are_validated_before_writing(
    hass: HomeAssistant, service_target, service, data, capability
):
    coordinator, _, resolve = service_target
    unsupported = MagicMock(spec=AdjustableBedCoordinator)
    unsupported.name = "Unsupported bed"
    unsupported.bed_type = BED_TYPE_JIECANG_APP
    unsupported.capability_controller = SimpleNamespace(**{capability: False})
    resolve.return_value = ([(coordinator, SIDE_BOTH), (unsupported, SIDE_BOTH)], [])
    with pytest.raises(ServiceValidationError, match="does not support"):
        await hass.services.async_call(
            DOMAIN, service, {"device_id": ["bed", "other"], **data}, blocking=True
        )
    coordinator.async_execute_controller_command.assert_not_awaited()
    unsupported.async_execute_controller_command.assert_not_called()


@pytest.mark.parametrize(
    ("service", "data"),
    [
        (SERVICE_JIECANG_SET_ALARM, {"enabled": True, "weekdays": ["holiday"]}),
        (SERVICE_JIECANG_SET_ALARM, {"enabled": True, "time": "25:00:00"}),
        (SERVICE_JIECANG_SET_ALARM, {"enabled": True, "head_level": 4}),
        (SERVICE_JIECANG_WAKE, {"preset": "yoga"}),
        (SERVICE_JIECANG_WAKE, {"right_level": -1}),
        (SERVICE_JIECANG_WAKE, {"head_level": 4}),
        (SERVICE_JIECANG_RENAME, {"name": ""}),
        (SERVICE_JIECANG_RENAME, {"name": "a" * 21}),
        (SERVICE_JIECANG_RENAME, {"name": "SengÅ"}),
        (SERVICE_JIECANG_RENAME, {"name": "My Bed"}),
        (SERVICE_JIECANG_WAKE, {"device_id": []}),
    ],
)
async def test_invalid_fields_do_not_dispatch(hass: HomeAssistant, service_target, service, data):
    coordinator, _, resolve = service_target
    with pytest.raises(vol.Invalid):
        await hass.services.async_call(DOMAIN, service, {"device_id": "bed", **data}, blocking=True)
    resolve.assert_not_called()
    coordinator.async_execute_controller_command.assert_not_awaited()


async def test_wake_preserves_paired_side_dispatch(hass: HomeAssistant, service_target):
    coordinator, controller, resolve = service_target
    pair = MagicMock(spec=PairedBedCoordinator)
    pair.child_for_side.return_value = coordinator

    async def execute(command, **kwargs):
        await command(controller)

    pair.async_execute_controller_command = AsyncMock(side_effect=execute)
    resolve.return_value = ([(pair, SIDE_RIGHT)], [])
    await hass.services.async_call(
        DOMAIN,
        SERVICE_JIECANG_WAKE,
        {"device_id": "pair", "side": SIDE_RIGHT},
        blocking=True,
    )
    kwargs = pair.async_execute_controller_command.await_args.kwargs
    assert kwargs["side"] == SIDE_RIGHT
    assert kwargs["cancel_running"] is True
    controller.execute_wake_routine.assert_awaited_once_with(
        preset="flat", head_level=0, foot_level=0
    )
    coordinator.async_execute_controller_command.assert_not_awaited()


async def test_stop_wake_interrupts_through_coordinator(hass: HomeAssistant, service_target):
    coordinator, controller, _ = service_target
    await hass.services.async_call(
        DOMAIN, SERVICE_JIECANG_STOP_WAKE, {"device_id": "bed"}, blocking=True
    )
    controller.stop_wake_routine.assert_awaited_once_with()
    assert coordinator.async_execute_controller_command.await_args.kwargs["cancel_running"]
    controller.configure_clock_alarm.assert_not_awaited()


async def test_rename_rejects_other_protocol_even_if_capable(hass: HomeAssistant, service_target):
    coordinator, controller, _ = service_target
    coordinator.bed_type = BED_TYPE_LINAK
    await_call = hass.services.async_call(
        DOMAIN, SERVICE_JIECANG_RENAME, {"device_id": "bed", "name": "Bed"}, blocking=True
    )
    with pytest.raises(ServiceValidationError, match="not a Jiecang app controller"):
        await await_call
    coordinator.async_execute_controller_command.assert_not_awaited()
    controller.rename_device.assert_not_awaited()


async def test_missing_device_prevents_partial_dispatch(hass: HomeAssistant, service_target):
    coordinator, _, resolve = service_target
    resolve.return_value = ([(coordinator, SIDE_BOTH)], ["missing"])
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_JIECANG_WAKE,
            {"device_id": ["bed", "missing"]},
            blocking=True,
        )
    coordinator.async_execute_controller_command.assert_not_awaited()
