"""Release ownership through real Sleepy's coordinator and scheduler paths."""

from __future__ import annotations

import asyncio
from typing import Literal, cast
from unittest.mock import AsyncMock, patch

import pytest
from bleak.exc import BleakError

from custom_components.adjustable_bed.beds.sleepys_app import SleepysEliteAppController
from custom_components.adjustable_bed.beds.sleepys_app_routes import ROUTES
from custom_components.adjustable_bed.button import ControllerActionButton
from custom_components.adjustable_bed.command_scheduler import (
    CommandContext,
    current_command_context,
)
from custom_components.adjustable_bed.const import (
    BED_TYPE_SLEEPYS_ELITE_APP,
    CONF_SLEEPYS_ELITE_SELECTOR,
    DOMAIN,
)
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.cover import AdjustableBedCover, _build_cover_description
from custom_components.adjustable_bed.number import AdjustableBedControllerNumber
from tests.test_coordinator_sleepys_elite import (
    SleepysRuntime,
    _FakeGattClient,
    _FakeGattService,
    _ready_command_lane,
    _VirtualClock,
    sleepys_runtime,  # noqa: F401,F811 - imported pytest fixture
)


async def _factory_controller(
    coordinator: AdjustableBedCoordinator,
    client: _FakeGattClient,
    selector: str | None = None,
) -> SleepysEliteAppController:
    if selector is not None:
        coordinator.hass.config_entries.async_update_entry(
            coordinator.entry,
            options={CONF_SLEEPYS_ELITE_SELECTOR: selector},
        )
    controller = cast(
        SleepysEliteAppController,
        await create_controller(coordinator, BED_TYPE_SLEEPYS_ELITE_APP, None, client),
    )
    controller._initialized = True
    keep_route = ROUTES[("keepConnect", controller.selector)]
    notify_characteristic = keep_route.notify_target.split("/", maxsplit=1)[1]
    service = _FakeGattService(
        keep_route.write_service,
        (keep_route.write_characteristic, notify_characteristic),
    )
    client.services = [service]
    controller._write_characteristic = service.characteristics[0]
    controller._notify_characteristic = service.characteristics[1]
    coordinator._controller = controller
    return controller


@pytest.mark.parametrize("release_owner", ["bed", "cover"])
async def test_disconnected_cleanup_does_not_acknowledge_external_stop(
    sleepys_runtime: SleepysRuntime,  # noqa: F811 - pytest fixture argument
    release_owner: Literal["bed", "cover"],
) -> None:
    hass, coordinator, _old, client = sleepys_runtime
    controller = await _factory_controller(coordinator, client)
    up = controller._route("headUp").payload
    stop = controller._route("stop").payload
    started = asyncio.Event()
    clock = _VirtualClock()
    writes: list[tuple[str, str | None]] = []
    preempted: list[tuple[CommandContext, ...]] = []

    async def write(_characteristic, payload, *, response):
        context = current_command_context()
        writes.append(
            (
                bytes(payload).hex(),
                context.kind.value if context is not None else None,
            )
        )
        if bytes(payload) == up:
            started.set()

    async def ensure_connected(reset_timer=True):
        if coordinator._client is None:
            context = current_command_context()
            assert context is not None
            preempted.append(context.preempted_contexts)
            client.is_connected = True
            coordinator._client = client
            await _factory_controller(coordinator, client)
        return True

    client.write_gatt_char.side_effect = write
    cover = AdjustableBedCover(
        coordinator, _build_cover_description(controller.motor_control_specs[0])
    )
    with (
        patch.object(
            coordinator, "async_ensure_connected", new=AsyncMock(side_effect=ensure_connected)
        ),
        patch.object(coordinator, "_async_refresh_controller_auth", new=AsyncMock()),
        patch.object(coordinator, "_auto_reconnect_enabled", return_value=False),
        patch.object(cover, "async_write_ha_state"),
        patch.object(controller, "_monotonic", clock.monotonic),
        patch.object(controller, "_sleep", clock.sleep),
    ):
        held = asyncio.create_task(
            hass.services.async_call(
                DOMAIN,
                "hold_control",
                {"device_id": ["sleepys"], "control": "headUp", "duration": 60},
                blocking=True,
            )
        )
        await started.wait()
        for _ in range(30):
            await asyncio.sleep(0)
        active = coordinator._command_scheduler._active
        assert active is not None
        old_context = active.context
        client.is_connected = False
        coordinator._on_disconnect(client)
        assert coordinator._client is None and coordinator._controller is None
        release = asyncio.create_task(
            coordinator.async_stop_command() if release_owner == "bed" else cover.async_stop_cover()
        )
        await asyncio.gather(held, release)
        stops_after_release = sum(payload == stop.hex() for payload, _kind in writes)
        await coordinator.async_stop_command()

    assert preempted == [(old_context,)]
    assert stops_after_release == 1
    assert sum(payload == stop.hex() for payload, _kind in writes) == 2


@pytest.mark.parametrize("release_owner", ["bed", "cover"])
async def test_timed_move_leaves_cleanup_ack_for_admitted_release_owner(
    sleepys_runtime: SleepysRuntime,  # noqa: F811 - pytest fixture argument
    release_owner: Literal["bed", "cover"],
) -> None:
    hass, coordinator, _old, client = sleepys_runtime
    controller = await _factory_controller(coordinator, client)
    up = controller._route("headUp").payload
    stop = controller._route("stop").payload
    writes: list[tuple[str, str | None]] = []
    started = asyncio.Event()

    async def write(_characteristic, payload, *, response):
        frame = bytes(payload)
        context = current_command_context()
        writes.append((frame.hex(), context.kind.value if context is not None else None))
        if frame == up:
            started.set()
            await asyncio.Event().wait()

    client.write_gatt_char.side_effect = write
    cover = AdjustableBedCover(
        coordinator, _build_cover_description(controller.motor_control_specs[0])
    )
    with _ready_command_lane(coordinator), patch.object(cover, "async_write_ha_state"):
        operation = asyncio.create_task(
            hass.services.async_call(
                DOMAIN,
                "timed_move",
                {
                    "device_id": ["sleepys"],
                    "motor": "head",
                    "direction": "up",
                    "duration_ms": 1000,
                },
                blocking=True,
            )
        )
        await started.wait()
        release = asyncio.create_task(
            coordinator.async_stop_command() if release_owner == "bed" else cover.async_stop_cover()
        )
        await asyncio.gather(operation, release)

    assert sum(payload == stop.hex() for payload, _kind in writes) == 1


@pytest.mark.parametrize("caller", ["hold_service", "native_button", "native_cover"])
async def test_caller_cancellation_drains_pending_release(
    sleepys_runtime: SleepysRuntime,  # noqa: F811 - pytest fixture argument
    caller: Literal["hold_service", "native_button", "native_cover"],
) -> None:
    hass, coordinator, _old, client = sleepys_runtime
    controller = await _factory_controller(coordinator, client)
    clock = _VirtualClock()
    stop = controller._route("stop").payload
    cleanup_started = asyncio.Event()
    allow_cleanup = asyncio.Event()
    writes: list[tuple[str, str]] = []

    async def write(_characteristic, payload, *, response):
        frame = bytes(payload)
        writes.append(("start", frame.hex()))
        if frame == stop:
            cleanup_started.set()
            await allow_cleanup.wait()
        writes.append(("done", frame.hex()))

    client.write_gatt_char.side_effect = write
    cover = AdjustableBedCover(
        coordinator, _build_cover_description(controller.motor_control_specs[0])
    )
    with (
        _ready_command_lane(coordinator),
        patch.object(controller, "_monotonic", clock.monotonic),
        patch.object(controller, "_sleep", clock.sleep),
        patch.object(cover, "async_write_ha_state"),
    ):
        if caller == "hold_service":
            operation = hass.services.async_call(
                DOMAIN,
                "hold_control",
                {"device_id": ["sleepys"], "control": "headUp", "duration": 0.1},
                blocking=True,
            )
        elif caller == "native_button":
            spec = next(
                spec
                for spec in controller.controller_button_specs
                if spec.key == "sleepys_app_memory_1"
            )
            operation = ControllerActionButton(coordinator, spec).async_press()
        else:
            operation = cover.async_open_cover()

        task = asyncio.create_task(operation)
        await clock.run_until(asyncio.create_task(cleanup_started.wait()))
        task.cancel()
        for _ in range(50):
            await asyncio.sleep(0)
        assert not task.done()
        allow_cleanup.set()
        with pytest.raises(asyncio.CancelledError):
            await task

    assert writes.count(("done", stop.hex())) == 1


@pytest.mark.parametrize("release_owner", ["bed", "cover"])
async def test_admitted_stop_consumes_release_completed_during_cancellation(
    sleepys_runtime: SleepysRuntime,  # noqa: F811 - pytest fixture argument
    release_owner: Literal["bed", "cover"],
) -> None:
    hass, coordinator, _old, client = sleepys_runtime
    controller = await _factory_controller(coordinator, client)
    clock = _VirtualClock()
    stop = controller._route("stop").payload
    cleanup_started = asyncio.Event()
    allow_cleanup = asyncio.Event()
    writes: list[str] = []

    async def write(_characteristic, payload, *, response):
        frame = bytes(payload)
        writes.append(frame.hex())
        if frame == stop:
            cleanup_started.set()
            await allow_cleanup.wait()

    client.write_gatt_char.side_effect = write
    cover = AdjustableBedCover(
        coordinator, _build_cover_description(controller.motor_control_specs[0])
    )
    with (
        _ready_command_lane(coordinator),
        patch.object(controller, "_monotonic", clock.monotonic),
        patch.object(controller, "_sleep", clock.sleep),
        patch.object(cover, "async_write_ha_state"),
    ):
        operation = asyncio.create_task(
            hass.services.async_call(
                DOMAIN,
                "hold_control",
                {"device_id": ["sleepys"], "control": "headUp", "duration": 0.1},
                blocking=True,
            )
        )
        await clock.run_until(asyncio.create_task(cleanup_started.wait()))
        active = coordinator._command_scheduler._active
        assert active is not None
        operation_context = active.context
        release = asyncio.create_task(
            coordinator.async_stop_command() if release_owner == "bed" else cover.async_stop_cover()
        )
        for _ in range(50):
            await asyncio.sleep(0)
        assert not operation.done()
        allow_cleanup.set()
        await asyncio.gather(operation, release)

    assert writes.count(stop.hex()) == 1
    assert not operation_context.cleanup_stop_sent


async def test_position_recenter_invalidates_older_stop_before_admitted_release(
    sleepys_runtime: SleepysRuntime,  # noqa: F811 - pytest fixture argument
) -> None:
    _hass, coordinator, _old, client = sleepys_runtime
    controller = await _factory_controller(coordinator, client, "BOX2442")

    target = controller._value_route("position_axis_0", 100).payload
    midpoint = controller._value_route("position_axis_0", 50).payload
    stop = controller._route("stop").payload
    midpoint_started = asyncio.Event()
    writes: list[bytes] = []

    async def write(_characteristic, payload, *, response):
        frame = bytes(payload)
        writes.append(frame)
        if frame == midpoint:
            midpoint_started.set()
            await asyncio.Event().wait()

    client.write_gatt_char.side_effect = write
    spec = next(
        spec
        for spec in controller.controller_number_specs
        if spec.key == "sleepys_app_target_axis_0"
    )
    number = AdjustableBedControllerNumber(coordinator, spec)
    with _ready_command_lane(coordinator):
        position = asyncio.create_task(number.async_set_native_value(100))
        await midpoint_started.wait()
        active = coordinator._command_scheduler._active
        assert active is not None and not active.context.cleanup_stop_sent

        await coordinator.async_stop_command()
        await position
        await coordinator.async_stop_command()

    assert writes == [target, stop, midpoint, stop, stop]


async def test_position_midpoint_success_keeps_three_frame_sequence(
    sleepys_runtime: SleepysRuntime,  # noqa: F811 - pytest fixture argument
) -> None:
    _hass, coordinator, _old, client = sleepys_runtime
    controller = await _factory_controller(coordinator, client, "BOX2442")
    target = controller._value_route("position_axis_0", 100).payload
    midpoint = controller._value_route("position_axis_0", 50).payload
    stop = controller._route("stop").payload
    clock = _VirtualClock()
    writes: list[bytes] = []

    async def write(_characteristic, payload, *, response):
        writes.append(bytes(payload))

    client.write_gatt_char.side_effect = write
    spec = next(
        spec
        for spec in controller.controller_number_specs
        if spec.key == "sleepys_app_target_axis_0"
    )
    number = AdjustableBedControllerNumber(coordinator, spec)
    with (
        _ready_command_lane(coordinator),
        patch.object(controller, "_monotonic", clock.monotonic),
        patch.object(controller, "_sleep", clock.sleep),
    ):
        await number.async_set_native_value(100)

    assert writes == [target, stop, midpoint]


async def test_position_midpoint_caller_cancel_settles_release(
    sleepys_runtime: SleepysRuntime,  # noqa: F811 - pytest fixture argument
) -> None:
    _hass, coordinator, _old, client = sleepys_runtime
    controller = await _factory_controller(coordinator, client, "BOX2442")
    target = controller._value_route("position_axis_0", 100).payload
    midpoint = controller._value_route("position_axis_0", 50).payload
    stop = controller._route("stop").payload
    clock = _VirtualClock()
    midpoint_started = asyncio.Event()
    allow_midpoint = asyncio.Event()
    writes: list[bytes] = []
    context: CommandContext | None = None

    async def write(_characteristic, payload, *, response):
        nonlocal context
        frame = bytes(payload)
        writes.append(frame)
        if frame == target:
            context = current_command_context()
        if frame == midpoint:
            midpoint_started.set()
            await allow_midpoint.wait()

    client.write_gatt_char.side_effect = write
    spec = next(
        spec
        for spec in controller.controller_number_specs
        if spec.key == "sleepys_app_target_axis_0"
    )
    number = AdjustableBedControllerNumber(coordinator, spec)
    with (
        _ready_command_lane(coordinator),
        patch.object(controller, "_monotonic", clock.monotonic),
        patch.object(controller, "_sleep", clock.sleep),
    ):
        position = asyncio.create_task(number.async_set_native_value(100))
        await midpoint_started.wait()
        assert context is not None and not context.cleanup_stop_sent
        position.cancel()
        with pytest.raises(asyncio.CancelledError):
            await position
        assert context.cleanup_stop_sent

        # A new idle STOP is a separate operation and must still reach the bed.
        await coordinator.async_stop_command()

    assert writes == [target, stop, midpoint, stop, stop]


@pytest.mark.parametrize("cleanup_mode", ["success", "failure", "skipped"])
async def test_position_midpoint_failure_preserves_error_and_retries_release(
    sleepys_runtime: SleepysRuntime,  # noqa: F811 - pytest fixture argument
    cleanup_mode: Literal["success", "failure", "skipped"],
) -> None:
    _hass, coordinator, _old, client = sleepys_runtime
    controller = await _factory_controller(coordinator, client, "BOX2442")
    target = controller._value_route("position_axis_0", 100).payload
    midpoint = controller._value_route("position_axis_0", 50).payload
    stop = controller._route("stop").payload
    midpoint_started = asyncio.Event()
    fail_midpoint = asyncio.Event()
    stop_attempts = 0
    writes: list[bytes] = []
    context: CommandContext | None = None

    async def write(_characteristic, payload, *, response):
        nonlocal context, stop_attempts
        frame = bytes(payload)
        writes.append(frame)
        if frame == target:
            context = current_command_context()
        elif frame == midpoint:
            midpoint_started.set()
            await fail_midpoint.wait()
            if cleanup_mode == "skipped":
                client.is_connected = False
            raise BleakError("midpoint write failed")
        elif frame == stop:
            stop_attempts += 1
            if cleanup_mode == "failure" and stop_attempts == 2:
                raise BleakError("cleanup write failed")

    client.write_gatt_char.side_effect = write
    spec = next(
        spec
        for spec in controller.controller_number_specs
        if spec.key == "sleepys_app_target_axis_0"
    )
    number = AdjustableBedControllerNumber(coordinator, spec)
    with _ready_command_lane(coordinator):
        position = asyncio.create_task(number.async_set_native_value(100))
        await midpoint_started.wait()
        fail_midpoint.set()
        with pytest.raises(BleakError, match="midpoint write failed"):
            await position

        assert context is not None
        assert context.cleanup_stop_sent is (cleanup_mode == "success")
        if cleanup_mode == "skipped":
            assert writes == [target, stop, midpoint]
            client.is_connected = True
        # A later independent STOP retries failed cleanup and is never hidden by
        # the operation's earlier successful target-release acknowledgement.
        await coordinator.async_stop_command()

    expected = [target, stop, midpoint]
    if cleanup_mode != "skipped":
        expected.append(stop)
    expected.append(stop)
    assert writes == expected
