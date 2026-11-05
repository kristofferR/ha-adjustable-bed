"""Focused timing and cleanup tests for Reverie per-target routine queues."""

from __future__ import annotations

import asyncio
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from homeassistant.const import CONF_ADDRESS
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed.beds.reverie import ReverieController
from custom_components.adjustable_bed.beds.reverie_comfort import ReverieComfortRequest
from custom_components.adjustable_bed.beds.reverie_nightstand import (
    ReverieNightstandController,
)
from custom_components.adjustable_bed.beds.reverie_pairlink import ReveriePairlinkController
from custom_components.adjustable_bed.beds.reverie_pairlink_runtime import (
    PairlinkCredentials,
    PairlinkHomeIdOrigin,
    PairlinkRole,
    PairlinkRuntime,
)
from custom_components.adjustable_bed.const import (
    BED_TYPE_REVERIE,
    BED_TYPE_REVERIE_NIGHTSTAND,
    CONF_BED_TYPE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_DISCONNECT_AFTER_COMMAND,
    CONF_HAS_MASSAGE,
    CONF_MOTOR_COUNT,
    CONF_PREFERRED_ADAPTER,
    CONF_PROTOCOL_VARIANT,
    DOMAIN,
)


class _Timer:
    def __init__(self) -> None:
        self.cancel = Mock()


def _pairlink_runtime() -> PairlinkRuntime:
    return PairlinkRuntime(
        PairlinkCredentials(
            b"\x01\x00\x00\x00",
            b"1122",
            PairlinkHomeIdOrigin.EXPLICIT_CONFIG,
        ),
        role=PairlinkRole.CENTRAL,
        target_mac="11:22:33:44:55:66",
        local_join_bt_mac=bytes.fromhex("102030405060"),
    )


def _request(controller_type) -> ReverieComfortRequest:
    return ReverieComfortRequest(
        head_position=25,
        foot_position=40,
        lumbar_position=(None if controller_type is ReverieController else 0),
        head_massage=0,
        foot_massage=0,
    )


def _coordinator(*, events: list[tuple[str, object]] | None = None):
    calls: list[tuple[float, object]] = []
    timer = _Timer()

    def call_later(delay: float, callback: object, *args: object) -> _Timer:
        if events is not None:
            events.append(("timer", delay))
        calls.append((delay, callback))
        return timer

    coordinator = SimpleNamespace(
        client=SimpleNamespace(is_connected=True),
        hold_command_connection=nullcontext,
        controller_state={},
        hass=SimpleNamespace(
            loop=SimpleNamespace(call_later=call_later),
            async_create_task=Mock(),
        ),
        handle_controller_state_update=Mock(),
        handle_controller_state_updates=Mock(),
        clear_position_feedback=Mock(),
    )
    return coordinator, calls, timer


@pytest.mark.parametrize(
    ("controller_type", "model", "send_method"),
    [
        (ReverieController, "9T", "_apply_composer_values"),
        (ReverieNightstandController, "R510L", "_write_routine_comfort"),
    ],
)
async def test_composer_schedules_zero_minute_last_poll_before_first_send(
    controller_type, model: str, send_method: str
) -> None:
    events: list[tuple[str, object]] = []
    coordinator, calls, _timer = _coordinator(events=events)
    controller = controller_type(coordinator, model=model)
    request = _request(controller_type)

    async def send(_request: ReverieComfortRequest) -> None:
        events.append(("send", _request))

    setattr(controller, send_method, AsyncMock(side_effect=send))
    await controller.async_start_routine([(request, 0)])

    assert events == [("timer", 0), ("send", request)]
    assert calls[0][0] == 0
    getattr(controller, send_method).assert_awaited_once_with(request)


@pytest.mark.parametrize(
    ("controller_type", "model", "send_method"),
    [
        (ReverieController, "9T", "_apply_composer_values"),
        (ReverieNightstandController, "R510L", "_write_routine_comfort"),
    ],
)
async def test_composer_missing_step_replaces_queue_but_leaves_prefix_unscheduled(
    controller_type, model: str, send_method: str
) -> None:
    coordinator, calls, old_timer = _coordinator()
    controller = controller_type(coordinator, model=model)
    request = _request(controller_type)
    send = AsyncMock()
    setattr(controller, send_method, send)
    controller._routine_timer = old_timer
    controller._routine_steps.append((request, 9))

    await controller.async_start_routine([(request, 4), (None, 0), (request, 6)])

    old_timer.cancel.assert_called_once_with()
    assert controller._routine_steps == [(request, 4)]
    assert calls == []
    send.assert_not_awaited()


@pytest.mark.parametrize(
    ("controller_type", "model", "send_method"),
    [
        (ReverieController, "9T", "_apply_composer_values"),
        (ReverieNightstandController, "R510L", "_write_routine_comfort"),
    ],
)
async def test_composer_write_failure_cancels_timer_and_unsent_queue(
    controller_type, model: str, send_method: str
) -> None:
    coordinator, calls, timer = _coordinator()
    controller = controller_type(coordinator, model=model)
    request = _request(controller_type)
    send = AsyncMock(side_effect=ConnectionError("write failed"))
    setattr(controller, send_method, send)

    with pytest.raises(ConnectionError, match="write failed"):
        await controller.async_start_routine([(request, 4), (request, 5)])

    assert calls[0][0] == 4 * 60
    timer.cancel.assert_called_once_with()
    assert controller._routine_timer is None
    assert controller._routine_steps == []


async def test_composer_routine_holds_real_coordinator_connection_until_cancel(
    hass,
    mock_coordinator_connected,
) -> None:
    from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator

    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Reverie routine ownership",
        data={
            CONF_ADDRESS: "AA:BB:CC:DD:EE:FF",
            CONF_BED_TYPE: BED_TYPE_REVERIE,
            CONF_MOTOR_COUNT: 2,
            CONF_HAS_MASSAGE: True,
            CONF_DISABLE_ANGLE_SENSING: True,
            CONF_PREFERRED_ADAPTER: "auto",
        },
        unique_id="AA:BB:CC:DD:EE:FF",
    )
    entry.add_to_hass(hass)
    coordinator = AdjustableBedCoordinator(hass, entry)
    await coordinator.async_connect()
    controller = coordinator.controller
    assert isinstance(controller, ReverieController)
    request = ReverieComfortRequest(
        head_position=25,
        foot_position=40,
        head_massage=0,
        foot_massage=0,
    )

    await controller.async_start_routine([(request, 1), (request, 1)])

    pending_timer = controller._routine_timer
    assert pending_timer is not None
    assert coordinator._command_connection_holds == 2  # Routine and active comfort progression.
    assert coordinator._disconnect_timer is None

    controller._cancel_routine()

    assert pending_timer.cancelled()
    assert coordinator._command_connection_holds == 0
    assert coordinator._disconnect_timer is not None


async def test_pairlink_routine_keeps_times_independent_and_defaults_missing_duration() -> None:
    timer_calls: list[tuple[float, object, tuple[object, ...], _Timer]] = []

    def call_later(delay: float, callback: object, *args: object) -> _Timer:
        timer = _Timer()
        timer_calls.append((delay, callback, args, timer))
        return timer

    coordinator = SimpleNamespace(
        client=SimpleNamespace(is_connected=True),
        hold_command_connection=nullcontext,
        address="11:22:33:44:55:66",
        cancel_command=asyncio.Event(),
        handle_controller_state_update=Mock(),
        handle_controller_state_updates=Mock(),
        hass=SimpleNamespace(
            loop=SimpleNamespace(call_later=call_later),
            async_create_task=Mock(),
        ),
    )
    controller = ReveriePairlinkController(
        coordinator, model="R510L", runtime=_pairlink_runtime()
    )
    first = ReverieComfortRequest(head_position=25)
    second = ReverieComfortRequest(head_position=35)
    third = ReverieComfortRequest(head_position=45)
    sent: list[ReverieComfortRequest] = []

    async def send(request: ReverieComfortRequest) -> None:
        sent.append(request)

    controller.async_set_comfort = AsyncMock(side_effect=send)
    steps = [(None, 9), (first, None), (second, 5), (third, 7)]

    controller.validate_routine(steps)
    await controller.async_start_routine(steps)

    assert sent == [first]
    assert [call[0] for call in timer_calls] == [9 * 60]
    generation = controller._routine_generation

    await controller._run_routine_step(generation)

    assert sent == [first, second]
    assert [call[0] for call in timer_calls] == [9 * 60, 60]

    await controller._run_routine_step(generation)

    assert sent == [first, second, third]
    assert [call[0] for call in timer_calls] == [9 * 60, 60]
    assert controller._routine_timer is None
    assert controller._routine_settings == []
    assert controller._routine_times == []


async def test_pairlink_routine_replacement_cancels_old_timer_before_first_write() -> None:
    timers: list[_Timer] = []

    def call_later(_delay: float, _callback: object, *_args: object) -> _Timer:
        timer = _Timer()
        timers.append(timer)
        return timer

    coordinator = SimpleNamespace(
        client=SimpleNamespace(is_connected=True),
        hold_command_connection=nullcontext,
        address="11:22:33:44:55:66",
        cancel_command=asyncio.Event(),
        handle_controller_state_update=Mock(),
        handle_controller_state_updates=Mock(),
        hass=SimpleNamespace(
            loop=SimpleNamespace(call_later=call_later),
            async_create_task=Mock(),
        ),
    )
    controller = ReveriePairlinkController(
        coordinator, model="R510L", runtime=_pairlink_runtime()
    )
    request = ReverieComfortRequest(head_position=25)
    controller.async_set_comfort = AsyncMock()

    await controller.async_start_routine([(request, 3), (request, 4)])
    old_timer = controller._routine_timer
    assert old_timer is timers[0]

    await controller.async_start_routine([(request, 5)])

    old_timer.cancel.assert_called_once_with()
    assert controller._routine_timer is None
    controller.async_set_comfort.assert_awaited_with(request)


@pytest.mark.parametrize(
    ("controller_type", "model"),
    [(ReverieController, "8Q"), (ReverieNightstandController, "R510L")],
)
async def test_diagnostic_stop_pair_runs_in_one_serialized_operation(
    controller_type, model: str
) -> None:
    calls: list[tuple[bytes, asyncio.Event | None]] = []
    coordinator, _calls, _timer = _coordinator()
    controller = controller_type(coordinator, model=model)

    async def write_command(_command, *args, **kwargs):
        del args
        calls.append((_command, kwargs.get("cancel_event")))

    async def execute(command, **_kwargs):
        await command(controller)

    if controller_type is ReverieController:
        controller.write_command = AsyncMock(side_effect=write_command)
    else:

        async def write_characteristic(_uuid, value: int, **kwargs) -> None:
            calls.append((bytes((value,)), kwargs.get("cancel_event")))

        controller._write_to_char = AsyncMock(side_effect=write_characteristic)
    coordinator.async_execute_controller_command = AsyncMock(side_effect=execute)

    await controller._stop_diagnostic()

    coordinator.async_execute_controller_command.assert_awaited_once()
    assert len(calls) == 2
    assert calls[0][1] is not None and calls[1][1] is not None
    assert calls[0][1] is not calls[1][1]
    assert not calls[0][1].is_set() and not calls[1][1].is_set()


@pytest.mark.parametrize(
    ("bed_type", "model", "controller_type", "write_method"),
    [
        (BED_TYPE_REVERIE, "8Q", ReverieController, "write_command"),
        (BED_TYPE_REVERIE_NIGHTSTAND, "R510L", ReverieNightstandController, "_write_to_char"),
    ],
)
@pytest.mark.parametrize("finish", ["stop", "stop_failure", "disconnect", "replace"])
async def test_diagnostic_keeps_connection_until_cleanup(
    hass, mock_coordinator_connected, monkeypatch,
    bed_type, model, controller_type, write_method, finish,
) -> None:
    from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator

    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Reverie diagnostic ownership",
        data={
            CONF_ADDRESS: "AA:BB:CC:DD:EE:FF",
            CONF_BED_TYPE: bed_type,
            CONF_PROTOCOL_VARIANT: model,
            CONF_MOTOR_COUNT: 2,
            CONF_HAS_MASSAGE: True,
            CONF_DISABLE_ANGLE_SENSING: True,
            CONF_PREFERRED_ADAPTER: "auto",
        },
        options={CONF_DISCONNECT_AFTER_COMMAND: True},
        unique_id="AA:BB:CC:DD:EE:FF",
    )
    entry.add_to_hass(hass)
    coordinator = AdjustableBedCoordinator(hass, entry)
    await coordinator.async_connect()
    controller = coordinator.controller
    assert isinstance(controller, controller_type)
    writes = AsyncMock()
    monkeypatch.setattr(controller, write_method, writes)

    await coordinator.async_execute_controller_command(
        lambda selected: selected.async_start_diagnostic(),
        resource="reverie:diagnostic",
        read_positions_after_operation=False,
    )
    timer = controller._diagnostic_timer
    release = controller._diagnostic_connection_release
    assert timer is not None
    assert coordinator._command_connection_holds == 1
    assert coordinator._disconnect_timer is None
    writes.reset_mock()

    if finish == "disconnect":
        controller.on_disconnect()
        writes.assert_not_awaited()
    else:
        if finish == "replace":
            await controller.async_start_diagnostic()
            writes.reset_mock()
            await controller._stop_diagnostic(release)
            writes.assert_not_awaited()
            assert coordinator._command_connection_holds == 1
        if finish == "stop_failure":
            writes.side_effect = ConnectionError("stop write failed")
            with pytest.raises(ExceptionGroup, match="diagnostic stop writes failed"):
                await controller._stop_diagnostic()
        else:
            await controller._stop_diagnostic()
        assert writes.await_count == 2
    assert timer.cancelled()
    assert coordinator._command_connection_holds == 0
    assert controller._diagnostic_timer is None
    assert coordinator._disconnect_timer is not None
    coordinator._cancel_disconnect_timer()


@pytest.mark.parametrize("side", ["1", "2", "3"])
def test_stk_side_changes_only_legacy_wave_number_availability(side):
    from custom_components.adjustable_bed.number import (
        MASSAGE_NUMBER_DESCRIPTIONS,
        AdjustableBedMassageNumber,
    )

    coordinator, _, _ = _coordinator()
    controller = ReverieNightstandController(coordinator, model="STK")
    coordinator.capability_controller = controller
    coordinator.entity_side = None
    coordinator.device_info = {}
    coordinator.entity_translation_key = lambda key: key
    coordinator.entity_unique_id = lambda key: key
    controller._set_stk_side(side)
    numbers = {
        description.massage_zone: AdjustableBedMassageNumber(coordinator, description)
        for description in MASSAGE_NUMBER_DESCRIPTIONS
        if description.massage_zone in ("head", "foot", "wave")
    }

    assert numbers["head"].available
    assert numbers["foot"].available
    assert numbers["wave"].available is (side == "1")
