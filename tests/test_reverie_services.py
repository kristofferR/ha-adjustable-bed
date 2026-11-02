"""Focused service contracts for Reverie comfort and routine actions."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError

from custom_components.adjustable_bed.beds.reverie_comfort import ReverieComfortRequest
from custom_components.adjustable_bed.const import (
    BED_TYPE_REVERIE_NIGHTSTAND,
    BED_TYPE_REVERIE_PAIRLINK,
    DOMAIN,
    SIDE_BOTH,
)
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.services import async_register_services


def _target(*, invalid: bool = False, bed_type: str = BED_TYPE_REVERIE_NIGHTSTAND):
    runtime_identity = object()
    plan = object()
    controller = SimpleNamespace(
        validate_comfort_request=MagicMock(
            side_effect=ValueError("unsupported selected model field") if invalid else None
        ),
        async_set_comfort=AsyncMock(),
        validate_routine=MagicMock(),
        async_start_routine=AsyncMock(),
        validate_diagnostic=MagicMock(),
        async_start_diagnostic=AsyncMock(),
    )
    coordinator = MagicMock(spec=AdjustableBedCoordinator)
    coordinator.name = "Reverie bed"
    coordinator.bed_type = bed_type
    coordinator.entry = SimpleNamespace(data={})
    coordinator.capability_controller = controller
    coordinator.controller = controller
    coordinator.is_connected = True
    if bed_type == BED_TYPE_REVERIE_PAIRLINK:
        controller.comfort_runtime_identity = MagicMock(return_value=runtime_identity)
        controller.prepare_comfort = MagicMock(
            side_effect=ValueError("unsupported selected model field") if invalid else None,
            return_value=plan,
        )

    async def execute(command, **_kwargs):
        await command(controller)

    coordinator.async_execute_controller_command = AsyncMock(side_effect=execute)
    return coordinator, controller


async def test_comfort_service_sends_one_typed_request_under_command_lock(
    hass: HomeAssistant,
) -> None:
    coordinator, controller = _target()
    await async_register_services(hass)
    with patch(
        "custom_components.adjustable_bed.services._resolve_sided_targets",
        return_value=([(coordinator, SIDE_BOTH)], []),
    ):
        await hass.services.async_call(
            DOMAIN,
            "reverie_set_comfort",
            {"device_id": "bed", "comfort": {"head_position": 45}},
            blocking=True,
        )

    request = ReverieComfortRequest(head_position=45)
    controller.validate_comfort_request.assert_called_once_with(request)
    controller.async_set_comfort.assert_awaited_once_with(request)
    assert coordinator.async_execute_controller_command.await_args.kwargs["resource"] == (
        "reverie:comfort"
    )


async def test_comfort_service_preflights_every_target_before_any_write(
    hass: HomeAssistant,
) -> None:
    first, first_controller = _target()
    second, second_controller = _target(invalid=True)
    await async_register_services(hass)
    with (
        patch(
            "custom_components.adjustable_bed.services._resolve_sided_targets",
            return_value=([(first, SIDE_BOTH), (second, SIDE_BOTH)], []),
        ),
        pytest.raises(ServiceValidationError, match="unsupported selected model field"),
    ):
        await hass.services.async_call(
            DOMAIN,
            "reverie_set_comfort",
            {"device_id": ["first", "second"], "comfort": {"head_position": 45}},
            blocking=True,
        )

    first_controller.async_set_comfort.assert_not_awaited()
    second_controller.async_set_comfort.assert_not_awaited()
    first.async_execute_controller_command.assert_not_awaited()
    second.async_execute_controller_command.assert_not_awaited()


async def test_pairlink_alarm_comfort_forces_complete_typed_request(
    hass: HomeAssistant,
) -> None:
    coordinator, controller = _target(bed_type=BED_TYPE_REVERIE_PAIRLINK)
    await async_register_services(hass)
    comfort = {
        "head_position": 20,
        "foot_position": 30,
        "lumbar_position": 40,
        "head_massage": 0,
        "foot_massage": 0,
        "timer_byte": 4,
        "mode": 2,
    }
    with patch(
        "custom_components.adjustable_bed.services._resolve_sided_targets",
        return_value=([(coordinator, SIDE_BOTH)], []),
    ):
        await hass.services.async_call(
            DOMAIN,
            "reverie_pairlink_alarm_comfort",
            {"device_id": "bed", "comfort": comfort},
            blocking=True,
        )

    request = ReverieComfortRequest(**comfort, force=True)
    controller.validate_comfort_request.assert_called_once_with(request)
    controller.prepare_comfort.assert_called_once_with(request)
    controller.async_set_comfort.assert_awaited_once_with(
        request, prepared_plan=controller.prepare_comfort.return_value
    )


async def test_pairlink_alarm_comfort_preflights_all_targets_before_any_write(
    hass: HomeAssistant,
) -> None:
    first, first_controller = _target(bed_type=BED_TYPE_REVERIE_PAIRLINK)
    second, second_controller = _target(
        invalid=True, bed_type=BED_TYPE_REVERIE_PAIRLINK
    )
    await async_register_services(hass)
    comfort = {
        "head_position": 20,
        "foot_position": 30,
        "lumbar_position": 40,
        "head_massage": 0,
        "foot_massage": 0,
        "timer_byte": 4,
        "mode": 2,
    }
    with (
        patch(
            "custom_components.adjustable_bed.services._resolve_sided_targets",
            return_value=([(first, SIDE_BOTH), (second, SIDE_BOTH)], []),
        ),
        pytest.raises(ServiceValidationError, match="unsupported selected model field"),
    ):
        await hass.services.async_call(
            DOMAIN,
            "reverie_pairlink_alarm_comfort",
            {"device_id": ["first", "second"], "comfort": comfort},
            blocking=True,
        )

    first_controller.async_set_comfort.assert_not_awaited()
    second_controller.async_set_comfort.assert_not_awaited()
    first.async_execute_controller_command.assert_not_awaited()
    second.async_execute_controller_command.assert_not_awaited()


async def test_routine_service_uses_selected_target_queue_without_scheduler(
    hass: HomeAssistant,
) -> None:
    coordinator, controller = _target()
    await async_register_services(hass)
    with patch(
        "custom_components.adjustable_bed.services._resolve_sided_targets",
        return_value=([(coordinator, SIDE_BOTH)], []),
    ):
        await hass.services.async_call(
            DOMAIN,
            "reverie_run_routine",
            {
                "device_id": "bed",
                "steps": [
                    {"duration_minutes": 4, "comfort": {"head_position": 45}},
                    {"duration_minutes": 0},
                ],
            },
            blocking=True,
        )

    request = ReverieComfortRequest(head_position=45)
    expected_steps = [(request, 4), (None, 0)]
    controller.validate_routine.assert_called_once_with(expected_steps)
    controller.async_start_routine.assert_awaited_once_with(expected_steps)
