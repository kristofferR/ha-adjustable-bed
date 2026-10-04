"""Alarm services preflight all physical targets and serialize configuration."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError

from custom_components.adjustable_bed.beds.malouf_app import MaloufAppController
from custom_components.adjustable_bed.const import BED_TYPE_MALOUF_APP, DOMAIN, SIDE_BOTH
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.malouf_app_protocol import TRANSPORTS
from custom_components.adjustable_bed.services import (
    SERVICE_LINAK_MOVE_SIMULTANEOUS,
    SERVICE_MALOUF_SET_ALARM,
    SERVICE_MALOUF_SYNC_CLOCK,
    SERVICE_TIMED_MOVE,
    async_register_services,
)


@pytest.fixture
async def service_target(hass: HomeAssistant):
    await async_register_services(hass)
    controller = SimpleNamespace(
        supports_clock_alarm=True, supports_clock_sync=True,
        clock_alarm_preset_options=("zero_g", "lounge", "tv", "anti_snore", "memory_1"),
        configure_clock_alarm=AsyncMock(), sync_clock=AsyncMock(),
    )
    coordinator = MagicMock(spec=AdjustableBedCoordinator)
    coordinator.name = "App bed"
    coordinator.bed_type = BED_TYPE_MALOUF_APP
    coordinator.capability_controller = controller

    async def execute(command, **kwargs):
        await command(controller)

    coordinator.async_execute_controller_command = AsyncMock(side_effect=execute)
    with patch("custom_components.adjustable_bed.services._resolve_sided_targets",
               return_value=([(coordinator, SIDE_BOTH)], [])) as resolve:
        yield coordinator, controller, resolve


async def test_alarm_dispatches_local_time_and_weekdays(hass, service_target):
    coordinator, controller, _ = service_target
    await hass.services.async_call(DOMAIN, SERVICE_MALOUF_SET_ALARM, {
        "device_id": "bed", "enabled": True, "time": "07:35:00",
        "weekdays": ["monday", "friday", "sunday"], "preset": "lounge",
    }, blocking=True)
    controller.configure_clock_alarm.assert_awaited_once_with(
        enabled=True, weekdays=(0, 4, 6), hour=7, minute=35, preset="lounge")
    kwargs = coordinator.async_execute_controller_command.await_args.kwargs
    assert kwargs["cancel_running"] is False
    assert kwargs["resource"] == "configuration"


async def test_clear_alarm_defaults(hass, service_target):
    _, controller, _ = service_target
    await hass.services.async_call(DOMAIN, SERVICE_MALOUF_SET_ALARM,
                                  {"device_id": "bed", "enabled": False}, blocking=True)
    controller.configure_clock_alarm.assert_awaited_once_with(
        enabled=False, weekdays=(), hour=0, minute=0, preset="zero_g")


async def test_alarm_seconds_rejected_before_target_resolution(hass, service_target):
    coordinator, _, resolve = service_target
    with pytest.raises(ServiceValidationError, match="minute precision"):
        await hass.services.async_call(DOMAIN, SERVICE_MALOUF_SET_ALARM,
                                      {"device_id": "bed", "enabled": True, "time": "07:35:01"},
                                      blocking=True)
    resolve.assert_not_called()
    coordinator.async_execute_controller_command.assert_not_awaited()


async def test_alarm_preset_is_validated_on_every_target_before_writing(hass, service_target):
    coordinator, controller, resolve = service_target
    controller.clock_alarm_preset_options += ("memory_2",)
    second = MagicMock(spec=AdjustableBedCoordinator)
    second.name = "One-slot bed"
    second.bed_type = BED_TYPE_MALOUF_APP
    second.capability_controller = SimpleNamespace(supports_clock_alarm=True,
        clock_alarm_preset_options=("zero_g", "memory_1"))
    resolve.return_value = ([(coordinator, SIDE_BOTH), (second, SIDE_BOTH)], [])
    with pytest.raises(ServiceValidationError, match="unavailable"):
        await hass.services.async_call(DOMAIN, SERVICE_MALOUF_SET_ALARM, {
            "device_id": ["bed", "second"], "enabled": True, "preset": "memory_2",
        }, blocking=True)
    controller.configure_clock_alarm.assert_not_awaited()
    coordinator.async_execute_controller_command.assert_not_awaited()
    second.async_execute_controller_command.assert_not_called()


async def test_clock_sync_is_serialized(hass, service_target):
    coordinator, controller, _ = service_target
    await hass.services.async_call(DOMAIN, SERVICE_MALOUF_SYNC_CLOCK,
                                  {"device_id": "bed"}, blocking=True)
    controller.sync_clock.assert_awaited_once_with()
    assert coordinator.async_execute_controller_command.await_args.kwargs["resource"] == "configuration"


async def test_clock_sync_rejects_transport_without_clock_before_any_write(hass, service_target):
    _, controller, _ = service_target
    controller.supports_clock_sync = False
    with pytest.raises(ServiceValidationError, match="does not support clock synchronization"):
        await hass.services.async_call(DOMAIN, SERVICE_MALOUF_SYNC_CLOCK,
                                      {"device_id": "bed"}, blocking=True)
    controller.sync_clock.assert_not_awaited()


async def test_explicit_split_head_actions_route_main_dual_and_partner_foot(hass):
    """HA's explicit action composition preserves the app's distinct payloads."""
    await async_register_services(hass)
    coordinators = {}
    for name in ("main", "partner"):
        coordinator = MagicMock(spec=AdjustableBedCoordinator)
        coordinator.name = name
        coordinator.address = name
        coordinator.bed_type = BED_TYPE_MALOUF_APP
        coordinator.observed_ble_device_name = "X1RM"
        coordinator.cancel_command = asyncio.Event()
        coordinator.motor_pulse_count = 7
        coordinator.entry = SimpleNamespace(data={"motor_count": 4})
        spec = TRANSPORTS["richmat_framed"]
        characteristic = MagicMock(uuid=spec.command_characteristic, properties=["write"])
        service = MagicMock(uuid=spec.command_service, characteristics=[characteristic])
        coordinator.client = MagicMock(is_connected=True, services=[service])
        coordinator.client.write_gatt_char = AsyncMock()
        controller = MaloufAppController(coordinator, app_profile="lucid", model="S755",
                                        transport="richmat_framed")
        coordinator.controller = controller
        coordinator.capability_controller = controller

        async def execute(command, *, _controller=controller, **kwargs):
            await command(_controller)

        coordinator.async_execute_controller_command = AsyncMock(side_effect=execute)
        coordinators[name] = coordinator

    def resolve(_hass, ids, _side):
        return [(coordinators[name], SIDE_BOTH) for name in ids], []

    with patch("custom_components.adjustable_bed.services._resolve_sided_targets",
               side_effect=resolve):
        await asyncio.gather(
            hass.services.async_call(DOMAIN, SERVICE_LINAK_MOVE_SIMULTANEOUS, {
                "device_id": "main", "first_motor": "back", "first_direction": "up",
                "second_motor": "legs", "second_direction": "up", "duration_ms": 1000,
            }, blocking=True),
            hass.services.async_call(DOMAIN, SERVICE_TIMED_MOVE, {
                "device_id": "partner", "motor": "legs", "direction": "up",
                "duration_ms": 1000,
            }, blocking=True),
        )
    main, partner = coordinators["main"], coordinators["partner"]
    main_frames = [call.args[1].hex() for call in main.client.write_gatt_char.call_args_list]
    partner_frames = [call.args[1].hex() for call in partner.client.write_gatt_char.call_args_list]
    assert main_frames[-1:] == ["6e01006edd"]
    assert 1 <= len(main_frames[:-1]) <= 7
    assert set(main_frames[:-1]) == {"6e01002998"}
    # timed_move also sends its own cancellation-safe terminal STOP.
    assert partner_frames[-2:] == ["6e01006edd"] * 2
    assert 1 <= len(partner_frames[:-2]) <= 7
    assert set(partner_frames[:-2]) == {"6e01002695"}
    assert main.async_execute_controller_command.await_args.kwargs["resources"] == (
        "motor:back", "motor:legs")
    assert partner.async_execute_controller_command.await_args.kwargs["resource"] == "motor:legs"
