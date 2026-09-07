"""Service validation and serialized dispatch for the Logicdata app controllers."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import voluptuous as vol
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError

from custom_components.adjustable_bed.const import (
    BED_TYPE_LINAK,
    BED_TYPE_LOGICDATA_APP,
    DOMAIN,
    SIDE_BOTH,
    SIDE_RIGHT,
)
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.paired_coordinator import PairedBedCoordinator
from custom_components.adjustable_bed.services import (
    SERVICE_LOGICDATA_HOLD_PRESET,
    SERVICE_LOGICDATA_RENAME,
    SERVICE_LOGICDATA_SET_ALARM,
    async_register_services,
)


@pytest.fixture
async def service_target(hass: HomeAssistant):
    """Use real registered schemas and dispatch with a client-free controller."""
    await async_register_services(hass)
    controller = SimpleNamespace(
        supports_clock_alarm=True,
        supports_device_rename=True,
        supports_preset_hold=True,
        configure_clock_alarm=AsyncMock(),
        rename_device=AsyncMock(),
        hold_preset=AsyncMock(),
    )
    coordinator = MagicMock(spec=AdjustableBedCoordinator)
    coordinator.name = "Logicdata bed"
    coordinator.bed_type = BED_TYPE_LOGICDATA_APP
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
        SERVICE_LOGICDATA_SET_ALARM,
        {
            "device_id": "bed",
            "enabled": True,
            "time": "07:35:00",
            "weekdays": ["monday", "friday", "sunday"],
            "preset": "anti_snore",
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
        preset="anti_snore",
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
        SERVICE_LOGICDATA_SET_ALARM,
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


async def test_rename_is_serialized_as_configuration(hass: HomeAssistant, service_target):
    coordinator, controller, _ = service_target
    await hass.services.async_call(
        DOMAIN,
        SERVICE_LOGICDATA_RENAME,
        {"device_id": "bed", "name": "My Bed"},
        blocking=True,
    )
    controller.rename_device.assert_awaited_once_with("My Bed")
    kwargs = coordinator.async_execute_controller_command.await_args.kwargs
    assert kwargs["cancel_running"] is False
    assert kwargs["resource"] == "configuration"


@pytest.mark.parametrize(
    ("service", "data", "capability"),
    [
        (SERVICE_LOGICDATA_SET_ALARM, {"enabled": True}, "supports_clock_alarm"),
        (SERVICE_LOGICDATA_RENAME, {"name": "Bed"}, "supports_device_rename"),
        (
            SERVICE_LOGICDATA_HOLD_PRESET,
            {"preset": "memory_1", "duration": 1},
            "supports_preset_hold",
        ),
    ],
)
async def test_all_targets_are_validated_before_writing(
    hass: HomeAssistant, service_target, service, data, capability
):
    coordinator, _, resolve = service_target
    unsupported = MagicMock(spec=AdjustableBedCoordinator)
    unsupported.name = "Unsupported bed"
    unsupported.bed_type = BED_TYPE_LOGICDATA_APP
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
        (SERVICE_LOGICDATA_SET_ALARM, {"enabled": True, "weekdays": ["holiday"]}),
        (SERVICE_LOGICDATA_SET_ALARM, {"enabled": True, "time": "25:00:00"}),
        (SERVICE_LOGICDATA_SET_ALARM, {"enabled": True, "head_level": 4}),
        (SERVICE_LOGICDATA_SET_ALARM, {"enabled": True, "preset": "yoga"}),
        (SERVICE_LOGICDATA_SET_ALARM, {"enabled": True, "foot_level": -1}),
        (SERVICE_LOGICDATA_RENAME, {"name": ""}),
        (SERVICE_LOGICDATA_RENAME, {"name": "a" * 256}),
        (SERVICE_LOGICDATA_RENAME, {"name": "SengÅ"}),
        (SERVICE_LOGICDATA_RENAME, {"name": "BED\n"}),
        (SERVICE_LOGICDATA_SET_ALARM, {"enabled": True, "device_id": []}),
    ],
)
async def test_invalid_fields_do_not_dispatch(hass: HomeAssistant, service_target, service, data):
    coordinator, _, resolve = service_target
    with pytest.raises(vol.Invalid):
        await hass.services.async_call(DOMAIN, service, {"device_id": "bed", **data}, blocking=True)
    resolve.assert_not_called()
    coordinator.async_execute_controller_command.assert_not_awaited()


async def test_rename_rejects_other_protocol_even_if_capable(hass: HomeAssistant, service_target):
    coordinator, controller, _ = service_target
    coordinator.bed_type = BED_TYPE_LINAK
    await_call = hass.services.async_call(
        DOMAIN, SERVICE_LOGICDATA_RENAME, {"device_id": "bed", "name": "Bed"}, blocking=True
    )
    with pytest.raises(ServiceValidationError, match="not a Logicdata app controller"):
        await await_call
    coordinator.async_execute_controller_command.assert_not_awaited()
    controller.rename_device.assert_not_awaited()


async def test_missing_device_prevents_partial_dispatch(hass: HomeAssistant, service_target):
    coordinator, _, resolve = service_target
    resolve.return_value = ([(coordinator, SIDE_BOTH)], ["missing"])
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_LOGICDATA_SET_ALARM,
            {"device_id": ["bed", "missing"], "enabled": True},
            blocking=True,
        )
    coordinator.async_execute_controller_command.assert_not_awaited()


async def test_alarm_preserves_paired_side_dispatch(hass: HomeAssistant, service_target):
    coordinator, controller, resolve = service_target
    pair = MagicMock(spec=PairedBedCoordinator)
    pair.child_for_side.return_value = coordinator

    async def execute(command, **kwargs):
        await command(controller)

    pair.async_execute_controller_command = AsyncMock(side_effect=execute)
    resolve.return_value = ([(pair, SIDE_RIGHT)], [])
    await hass.services.async_call(
        DOMAIN,
        SERVICE_LOGICDATA_SET_ALARM,
        {"device_id": "pair", "side": SIDE_RIGHT, "enabled": False},
        blocking=True,
    )
    kwargs = pair.async_execute_controller_command.await_args.kwargs
    assert kwargs["side"] == SIDE_RIGHT
    assert kwargs["cancel_running"] is False
    assert kwargs["resource"] == "configuration"
    controller.configure_clock_alarm.assert_awaited_once_with(
        enabled=False, weekdays=(), hour=0, minute=0, preset="flat", head_level=0, foot_level=0
    )
    coordinator.async_execute_controller_command.assert_not_awaited()


@pytest.mark.parametrize(
    ("preset", "seconds", "duration_ms"),
    [("flat", 0.2, 200), ("memory_1", 1.001, 1001), ("memory_2", 60, 60000)],
)
async def test_hold_preset_converts_duration_exactly_and_cancels_motion(
    hass: HomeAssistant, service_target, preset, seconds, duration_ms
):
    coordinator, controller, _ = service_target
    await hass.services.async_call(
        DOMAIN,
        SERVICE_LOGICDATA_HOLD_PRESET,
        {"device_id": "bed", "preset": preset, "duration": seconds},
        blocking=True,
    )
    controller.hold_preset.assert_awaited_once_with(preset, duration_ms)
    kwargs = coordinator.async_execute_controller_command.await_args.kwargs
    assert kwargs["cancel_running"] is True
    assert kwargs["resource"] is None
    assert kwargs["resources"] is None


@pytest.mark.parametrize(
    "duration",
    [
        0.199,
        60.001,
        1.0001,
        "1.00000000000000000000000000000001",
        float("nan"),
        float("inf"),
        True,
        "invalid",
    ],
)
async def test_hold_preset_rejects_invalid_duration_before_dispatch(
    hass: HomeAssistant, service_target, duration
):
    coordinator, _, resolve = service_target
    with pytest.raises(vol.Invalid):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_LOGICDATA_HOLD_PRESET,
            {"device_id": "bed", "preset": "flat", "duration": duration},
            blocking=True,
        )
    resolve.assert_not_called()
    coordinator.async_execute_controller_command.assert_not_awaited()


@pytest.mark.parametrize("preset", ["zero_g", "memory_3", "yoga", 1])
async def test_hold_preset_rejects_unsupported_presets(hass: HomeAssistant, service_target, preset):
    _, _, resolve = service_target
    with pytest.raises(vol.Invalid):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_LOGICDATA_HOLD_PRESET,
            {"device_id": "bed", "preset": preset, "duration": 1},
            blocking=True,
        )
    resolve.assert_not_called()


async def test_hold_preset_preserves_paired_dispatch(hass: HomeAssistant, service_target):
    coordinator, controller, resolve = service_target
    pair = MagicMock(spec=PairedBedCoordinator)
    pair.child_for_side.return_value = coordinator

    async def execute(command, **kwargs):
        await command(controller)

    pair.async_execute_controller_command = AsyncMock(side_effect=execute)
    resolve.return_value = ([(pair, SIDE_RIGHT)], [])
    await hass.services.async_call(
        DOMAIN,
        SERVICE_LOGICDATA_HOLD_PRESET,
        {"device_id": "pair", "side": SIDE_RIGHT, "preset": "flat", "duration": 0.2},
        blocking=True,
    )
    kwargs = pair.async_execute_controller_command.await_args.kwargs
    assert kwargs["side"] == SIDE_RIGHT
    assert kwargs["cancel_running"] is True
    controller.hold_preset.assert_awaited_once_with("flat", 200)
    coordinator.async_execute_controller_command.assert_not_awaited()
