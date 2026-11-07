"""Focused service contracts for Reverie comfort and routine actions."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError

from custom_components.adjustable_bed.beds.reverie_comfort import (
    PairlinkComfortActions,
    ReverieComfortActions,
    ReverieComfortRequest,
)
from custom_components.adjustable_bed.const import (
    BED_TYPE_REVERIE,
    BED_TYPE_REVERIE_NIGHTSTAND,
    BED_TYPE_REVERIE_PAIRLINK,
    DOMAIN,
    SIDE_BOTH,
    SIDE_LEFT,
    SIDE_RIGHT,
)
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.paired_coordinator import PairedBedCoordinator
from custom_components.adjustable_bed.services import async_register_services


def _target(*, invalid: bool = False, bed_type: str = BED_TYPE_REVERIE_NIGHTSTAND):
    runtime_identity = object()
    plan = object()
    interface = (
        PairlinkComfortActions if bed_type == BED_TYPE_REVERIE_PAIRLINK else ReverieComfortActions
    )
    controller = MagicMock(
        spec=interface,
        requires_disconnected_transport=False,
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
    # A lightweight double: no scheduler reservation API, so no prepared dispatch.
    del coordinator.async_prepare_command_operation
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
        "custom_components.adjustable_bed.reverie_services._resolve_sided_targets",
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
            "custom_components.adjustable_bed.reverie_services._resolve_sided_targets",
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
        "custom_components.adjustable_bed.reverie_services._resolve_sided_targets",
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
            "custom_components.adjustable_bed.reverie_services._resolve_sided_targets",
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
        "custom_components.adjustable_bed.reverie_services._resolve_sided_targets",
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


@pytest.mark.parametrize("service", ["reverie_run_routine", "reverie_test"])
@pytest.mark.parametrize("mode", ["sequential", "concurrent"])
@pytest.mark.parametrize("local_role", [False, True])
@pytest.mark.parametrize("side", [SIDE_BOTH, SIDE_LEFT])
async def test_deferred_actions_preflight_pair_connection_policy(
    hass, service, mode, local_role, side,
):
    first, first_controller = _target()
    left, left_controller = _target(bed_type=BED_TYPE_REVERIE_PAIRLINK)
    right, right_controller = _target(bed_type=BED_TYPE_REVERIE_PAIRLINK)
    pair = MagicMock(spec=PairedBedCoordinator)
    pair.connection_mode = mode
    pair.children = {SIDE_LEFT: left, SIDE_RIGHT: right}
    pair.child_for_side.side_effect = pair.children.get
    for controller in (left_controller, right_controller):
        controller.requires_disconnected_transport = local_role
        controller.disconnected_transport_ready = True

    async def execute(command, *, side, **_kwargs):
        selected = pair.children.values() if side == SIDE_BOTH else [pair.children[side]]
        for target in selected:
            await command(target.controller)

    pair.async_execute_controller_command = AsyncMock(side_effect=execute)
    await async_register_services(hass)
    data = {"device_id": ["first", "pair"], "side": side}
    if service == "reverie_run_routine":
        data["steps"] = [{"comfort": {"head_position": 25}, "duration_minutes": 1}]
    with patch(
        "custom_components.adjustable_bed.reverie_services._resolve_sided_targets",
        return_value=([(first, SIDE_BOTH), (pair, side)], []),
    ):
        if mode == "sequential" and not local_role:
            with pytest.raises(ServiceValidationError, match="require concurrent"):
                await hass.services.async_call(DOMAIN, service, data, blocking=True)
            first.async_execute_controller_command.assert_not_awaited()
            pair.async_execute_controller_command.assert_not_awaited()
        else:
            await hass.services.async_call(DOMAIN, service, data, blocking=True)
            first.async_execute_controller_command.assert_awaited_once()
            pair.async_execute_controller_command.assert_awaited_once()
    method = "async_start_routine" if service == "reverie_run_routine" else "async_start_diagnostic"
    rejected = mode == "sequential" and not local_role
    assert getattr(first_controller, method).await_count == (0 if rejected else 1)
    assert getattr(left_controller, method).await_count == (0 if rejected else 1)
    assert getattr(right_controller, method).await_count == (1 if not rejected and side == SIDE_BOTH else 0)


@pytest.mark.parametrize("bed_type", [BED_TYPE_REVERIE, BED_TYPE_REVERIE_NIGHTSTAND])
@pytest.mark.parametrize("mode", ["sequential", "concurrent", "fallback"])
@pytest.mark.parametrize("side", [SIDE_LEFT, SIDE_BOTH])
async def test_comfort_rejects_only_deferred_sequential_targets(hass, bed_type, mode, side):
    first, first_controller = _target()
    left, left_controller = _target(bed_type=bed_type)
    right, right_controller = _target(bed_type=bed_type)
    pair = MagicMock(spec=PairedBedCoordinator)
    pair.connection_mode = "concurrent" if mode == "fallback" else mode
    pair.children = {SIDE_LEFT: left, SIDE_RIGHT: right}
    pair.child_for_side.side_effect = pair.children.get
    for controller in (left_controller, right_controller):
        controller.requires_disconnected_transport = False

    async def execute(command, *, side, **_kwargs):
        if mode == "fallback":
            pair.connection_mode = "sequential"
        selected = pair.children.values() if side == SIDE_BOTH else [pair.children[side]]
        for target in selected:
            await command(target.controller)

    pair.async_execute_controller_command = AsyncMock(side_effect=execute)
    await async_register_services(hass)
    rejected = bed_type == BED_TYPE_REVERIE and mode != "concurrent"
    with patch(
        "custom_components.adjustable_bed.reverie_services._resolve_sided_targets",
        return_value=([(first, SIDE_BOTH), (pair, side)], []),
    ):
        call = hass.services.async_call(
            DOMAIN, "reverie_set_comfort",
            {"device_id": ["first", "pair"], "comfort": {"head_position": 45}},
            blocking=True,
        )
        if rejected:
            with pytest.raises(ServiceValidationError, match="require concurrent"):
                await call
        else:
            await call
    # Preflight rejects every initial write. Runtime fallback rejects before the
    # pair starts, even if an earlier independent target already completed.
    assert first_controller.async_set_comfort.await_count == (0 if rejected and mode == "sequential" else 1)
    assert left_controller.async_set_comfort.await_count == (0 if rejected else 1)
    assert right_controller.async_set_comfort.await_count == (1 if not rejected and side == SIDE_BOTH else 0)
