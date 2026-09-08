"""Leggett app timer and held-control service validation and dispatch."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import voluptuous as vol
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError

from custom_components.adjustable_bed.const import (
    BED_TYPE_LEGGETT_OKIN,
    BED_TYPE_LEGGETT_PLATT,
    BED_TYPE_LINAK,
    CONF_PROTOCOL_VARIANT,
    DOMAIN,
    LEGGETT_VARIANT_GEN2,
    LEGGETT_VARIANT_MLRM,
    LEGGETT_VARIANT_OKIN,
    SIDE_BOTH,
    SIDE_RIGHT,
)
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.paired_coordinator import PairedBedCoordinator
from custom_components.adjustable_bed.services import (
    LEGGETT_HELD_CONTROLS,
    SERVICE_LEGGETT_ALARM_TIMER,
    SERVICE_LEGGETT_HOLD_CONTROL,
    SERVICE_LEGGETT_SLEEP_TIMER,
    async_register_services,
)


@pytest.fixture
async def service_target(hass: HomeAssistant):
    """Keep real schemas and dispatch, replacing only the physical BLE target."""
    await async_register_services(hass)
    controller = SimpleNamespace(
        supports_sleep_timer=True,
        supports_alarm_timer=True,
        supports_held_control=True,
        sleep_timer_memory_options=(1, 2, 3, 4),
        sleep_timer_duration_options=(),
        held_control_options=LEGGETT_HELD_CONTROLS,
        set_sleep_timer=AsyncMock(),
        cancel_sleep_timer=AsyncMock(),
        set_alarm_timer=AsyncMock(),
        cancel_alarm_timer=AsyncMock(),
        hold_control=AsyncMock(),
    )
    coordinator = MagicMock(spec=AdjustableBedCoordinator)
    coordinator.name = "Leggett bed"
    coordinator.bed_type = BED_TYPE_LEGGETT_OKIN
    coordinator.entry = SimpleNamespace(data={})
    coordinator.capability_controller = controller

    async def execute(command, **kwargs):
        await command(controller)

    coordinator.async_execute_controller_command = AsyncMock(side_effect=execute)
    with patch(
        "custom_components.adjustable_bed.services._resolve_sided_targets",
        return_value=([(coordinator, SIDE_BOTH)], []),
    ) as resolve:
        yield coordinator, controller, resolve


@pytest.mark.parametrize("minutes", [1, 1439])
async def test_sleep_timer_dispatches_selectable_prodigy_bounds(
    hass: HomeAssistant, service_target, minutes
):
    coordinator, controller, _ = service_target
    await hass.services.async_call(
        DOMAIN,
        SERVICE_LEGGETT_SLEEP_TIMER,
        {"device_id": "bed", "action": "start", "minutes": minutes, "preset": 4},
        blocking=True,
    )
    controller.set_sleep_timer.assert_awaited_once_with(minutes, 4)
    kwargs = coordinator.async_execute_controller_command.await_args.kwargs
    assert kwargs["cancel_running"] is False
    assert kwargs["resource"] == "configuration"


@pytest.mark.parametrize("preset", [0, 3])
async def test_useries_sleep_accepts_flat_and_timer_only_third_memory(
    hass: HomeAssistant, service_target, preset
):
    _, controller, _ = service_target
    controller.sleep_timer_memory_options = (0, 1, 2, 3)
    controller.sleep_timer_duration_options = (15, 30, 45, 60, 75, 90)
    await hass.services.async_call(
        DOMAIN,
        SERVICE_LEGGETT_SLEEP_TIMER,
        {"device_id": "bed", "action": "start", "minutes": 90, "preset": preset},
        blocking=True,
    )
    controller.set_sleep_timer.assert_awaited_once_with(90, preset)


@pytest.mark.parametrize(
    ("minutes", "preset", "message"),
    [(16, 1, "requires a sleep duration"), (15, 4, "does not support sleep action")],
)
async def test_profile_constraints_are_preflighted_before_any_device_write(
    hass: HomeAssistant, service_target, minutes, preset, message
):
    coordinator, _, resolve = service_target
    useries = MagicMock(spec=AdjustableBedCoordinator)
    useries.name = "U Series"
    useries.bed_type = BED_TYPE_LEGGETT_OKIN
    useries.entry = SimpleNamespace(data={})
    useries.capability_controller = SimpleNamespace(
        supports_sleep_timer=True,
        sleep_timer_memory_options=(0, 1, 2, 3),
        sleep_timer_duration_options=(15, 30, 45, 60, 75, 90),
    )
    resolve.return_value = ([(coordinator, SIDE_BOTH), (useries, SIDE_BOTH)], [])
    with pytest.raises(ServiceValidationError, match=message):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_LEGGETT_SLEEP_TIMER,
            {
                "device_id": ["bed", "useries"],
                "action": "start",
                "minutes": minutes,
                "preset": preset,
            },
            blocking=True,
        )
    coordinator.async_execute_controller_command.assert_not_awaited()
    useries.async_execute_controller_command.assert_not_called()


async def test_alarm_accepts_full_day_delay(hass: HomeAssistant, service_target):
    _, controller, _ = service_target
    await hass.services.async_call(
        DOMAIN,
        SERVICE_LEGGETT_ALARM_TIMER,
        {"device_id": "bed", "action": "start", "minutes": 1440},
        blocking=True,
    )
    controller.set_alarm_timer.assert_awaited_once_with(1440)


@pytest.mark.parametrize(
    ("service", "method"),
    [
        (SERVICE_LEGGETT_SLEEP_TIMER, "cancel_sleep_timer"),
        (SERVICE_LEGGETT_ALARM_TIMER, "cancel_alarm_timer"),
    ],
)
async def test_timer_cancel_needs_no_duration(hass: HomeAssistant, service_target, service, method):
    _, controller, _ = service_target
    await hass.services.async_call(
        DOMAIN, service, {"device_id": "bed", "action": "cancel"}, blocking=True
    )
    getattr(controller, method).assert_awaited_once_with()
    controller.set_sleep_timer.assert_not_awaited()
    controller.set_alarm_timer.assert_not_awaited()


@pytest.mark.parametrize("service", [SERVICE_LEGGETT_SLEEP_TIMER, SERVICE_LEGGETT_ALARM_TIMER])
async def test_start_requires_duration_before_resolving_targets(
    hass: HomeAssistant, service_target, service
):
    _, _, resolve = service_target
    with pytest.raises(ServiceValidationError, match="requires minutes"):
        await hass.services.async_call(
            DOMAIN, service, {"device_id": "bed", "action": "start"}, blocking=True
        )
    resolve.assert_not_called()


@pytest.mark.parametrize(
    ("service", "data"),
    [
        (SERVICE_LEGGETT_SLEEP_TIMER, {"action": "start", "minutes": 1440}),
        (SERVICE_LEGGETT_SLEEP_TIMER, {"action": "start", "minutes": 15, "preset": 5}),
        (SERVICE_LEGGETT_ALARM_TIMER, {"action": "start", "minutes": 1441}),
        (SERVICE_LEGGETT_ALARM_TIMER, {"action": "start", "minutes": 1.5}),
        (SERVICE_LEGGETT_ALARM_TIMER, {"action": "start", "minutes": True}),
        (SERVICE_LEGGETT_ALARM_TIMER, {"action": "start", "minutes": 0}),
        (SERVICE_LEGGETT_HOLD_CONTROL, {"control": "snore", "duration": 0.099}),
        (SERVICE_LEGGETT_HOLD_CONTROL, {"control": "snore", "duration": 60.001}),
        (SERVICE_LEGGETT_HOLD_CONTROL, {"control": "snore", "duration": 1.0001}),
        (SERVICE_LEGGETT_HOLD_CONTROL, {"control": "snore", "duration": float("nan")}),
        (SERVICE_LEGGETT_HOLD_CONTROL, {"control": "snore", "duration": float("inf")}),
        (SERVICE_LEGGETT_HOLD_CONTROL, {"control": "memory_4", "duration": 1}),
    ],
)
async def test_invalid_schema_prevents_dispatch(hass: HomeAssistant, service_target, service, data):
    _, _, resolve = service_target
    with pytest.raises(vol.Invalid):
        await hass.services.async_call(DOMAIN, service, {"device_id": "bed", **data}, blocking=True)
    resolve.assert_not_called()


@pytest.mark.parametrize("control", LEGGETT_HELD_CONTROLS)
async def test_hold_control_uses_exact_milliseconds_and_cancellation(
    hass: HomeAssistant, service_target, control
):
    coordinator, controller, _ = service_target
    await hass.services.async_call(
        DOMAIN,
        SERVICE_LEGGETT_HOLD_CONTROL,
        {"device_id": "bed", "control": control, "duration": 1.001},
        blocking=True,
    )
    controller.hold_control.assert_awaited_once_with(control, 1001)
    kwargs = coordinator.async_execute_controller_command.await_args.kwargs
    assert kwargs["cancel_running"] is True
    assert kwargs["resource"] is None
    assert kwargs["resources"] is None


async def test_hold_store_rejects_profile_without_standalone_store(
    hass: HomeAssistant, service_target
):
    coordinator, controller, _ = service_target
    controller.held_control_options = ("flat", "snore")
    with pytest.raises(ServiceValidationError, match="does not support held control 'store'"):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_LEGGETT_HOLD_CONTROL,
            {"device_id": "bed", "control": "store", "duration": 1},
            blocking=True,
        )
    coordinator.async_execute_controller_command.assert_not_awaited()


@pytest.mark.parametrize(
    ("service", "data", "capability"),
    [
        (SERVICE_LEGGETT_SLEEP_TIMER, {"action": "cancel"}, "supports_sleep_timer"),
        (SERVICE_LEGGETT_ALARM_TIMER, {"action": "cancel"}, "supports_alarm_timer"),
        (
            SERVICE_LEGGETT_HOLD_CONTROL,
            {"control": "snore", "duration": 1},
            "supports_held_control",
        ),
    ],
)
async def test_capability_and_protocol_are_required(
    hass: HomeAssistant, service_target, service, data, capability
):
    coordinator, controller, _ = service_target
    setattr(controller, capability, False)
    with pytest.raises(ServiceValidationError, match="does not support"):
        await hass.services.async_call(DOMAIN, service, {"device_id": "bed", **data}, blocking=True)
    setattr(controller, capability, True)
    coordinator.bed_type = BED_TYPE_LINAK
    with pytest.raises(ServiceValidationError, match="not a Leggett Okin controller"):
        await hass.services.async_call(DOMAIN, service, {"device_id": "bed", **data}, blocking=True)
    coordinator.async_execute_controller_command.assert_not_awaited()


async def test_hold_preserves_paired_side_dispatch(hass: HomeAssistant, service_target):
    coordinator, controller, resolve = service_target
    pair = MagicMock(spec=PairedBedCoordinator)
    pair.child_for_side.return_value = coordinator

    async def execute(command, **kwargs):
        await command(controller)

    pair.async_execute_controller_command = AsyncMock(side_effect=execute)
    resolve.return_value = ([(pair, SIDE_RIGHT)], [])
    await hass.services.async_call(
        DOMAIN,
        SERVICE_LEGGETT_HOLD_CONTROL,
        {"device_id": "pair", "side": SIDE_RIGHT, "control": "flat", "duration": 0.1},
        blocking=True,
    )
    kwargs = pair.async_execute_controller_command.await_args.kwargs
    assert kwargs["side"] == SIDE_RIGHT
    assert kwargs["cancel_running"] is True
    controller.hold_control.assert_awaited_once_with("flat", 100)
    coordinator.async_execute_controller_command.assert_not_awaited()


@pytest.mark.parametrize(
    ("service", "data", "method"),
    [
        (SERVICE_LEGGETT_SLEEP_TIMER, {"action": "cancel"}, "cancel_sleep_timer"),
        (SERVICE_LEGGETT_ALARM_TIMER, {"action": "cancel"}, "cancel_alarm_timer"),
        (
            SERVICE_LEGGETT_HOLD_CONTROL,
            {"control": "snore", "duration": 1},
            "hold_control",
        ),
    ],
)
async def test_explicit_legacy_okin_alias_accepts_services(
    hass: HomeAssistant, service_target, service, data, method
):
    coordinator, controller, _ = service_target
    coordinator.bed_type = BED_TYPE_LEGGETT_PLATT
    coordinator.entry.data = {CONF_PROTOCOL_VARIANT: LEGGETT_VARIANT_OKIN}
    await hass.services.async_call(DOMAIN, service, {"device_id": "bed", **data}, blocking=True)
    getattr(controller, method).assert_awaited_once()
    coordinator.async_execute_controller_command.assert_awaited_once()


@pytest.mark.parametrize("variant", [LEGGETT_VARIANT_GEN2, LEGGETT_VARIANT_MLRM, "auto", None])
async def test_other_legacy_variants_reject_before_dispatch(
    hass: HomeAssistant, service_target, variant
):
    coordinator, _, _ = service_target
    coordinator.bed_type = BED_TYPE_LEGGETT_PLATT
    coordinator.entry.data = {CONF_PROTOCOL_VARIANT: variant}
    with pytest.raises(ServiceValidationError, match="not a Leggett Okin controller"):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_LEGGETT_HOLD_CONTROL,
            {"device_id": "bed", "control": "snore", "duration": 1},
            blocking=True,
        )
    coordinator.async_execute_controller_command.assert_not_awaited()
