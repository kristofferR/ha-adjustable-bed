"""Elapsed movement and ordinary AI-zero cleanup at the real GATT/caller boundary."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch

import pytest
from bleak.exc import BleakError
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import ServiceCall
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed.beds.smart_sleep.controller import SmartSleepController
from custom_components.adjustable_bed.button import ControllerActionButton, _button_entities_for
from custom_components.adjustable_bed.codec import smart_sleep as codec
from custom_components.adjustable_bed.command_scheduler import CommandKind, HoldLease
from custom_components.adjustable_bed.const import DOMAIN, SIDE_BOTH
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.profiles.smart_sleep import PROFILES
from custom_components.adjustable_bed.services import handle_timed_move
from tests.hold_lease_wire import virtual_clock
from tests.test_smart_sleep import controller


@asynccontextmanager
async def live_bed(hass, fmt="p1", model=0):
    """A connected mock peripheral with real controller, coordinator and scheduler."""
    client = controller(fmt, model).client
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_ADDRESS: "AA:BB:CC:DD:EE:94",
            "name": "Smart Sleep",
            "bed_type": "smart_sleep",
            "protocol_variant": fmt,
            "product_type": str(model),
            "motor_pulse_count": 3,
            "disconnect_after_command": False,
            "idle_disconnect_seconds": 0,
            "disable_angle_sensing": True,
            "has_massage": True,
        },
    )
    entry.add_to_hass(hass)
    coord = AdjustableBedCoordinator(hass, entry)
    coord._client = client
    ctrl = SmartSleepController(coord, PROFILES[fmt], model)
    coord._controller = coord._offline_controller = ctrl

    async def disconnect():
        client.is_connected = False

    client.disconnect = AsyncMock(side_effect=disconnect)
    try:
        yield coord, ctrl
    finally:
        await coord.async_shutdown()


def acknowledged_writer(ctrl, clock, seconds=0.15, on_start=None):
    """Only emulate the peripheral ACK. The real writer owns pacing and locking."""
    events = []
    active = False

    async def write(char, data, *, response):
        nonlocal active
        assert not active, "Release overlapped an in-flight movement write"
        assert ctrl._ble_lock.locked()
        assert response is True and char.uuid == codec.WRITE
        frame = bytes(data)
        active = True
        events.append(("start", frame, round(clock.now * 1000)))
        try:
            if on_start:
                on_start(frame)
            await asyncio.sleep(seconds)
        except asyncio.CancelledError:
            events.append(("cancel", frame, round(clock.now * 1000)))
            raise
        else:
            events.append(("ack", frame, round(clock.now * 1000)))
        finally:
            active = False

    ctrl.client.write_gatt_char = AsyncMock(side_effect=write)
    return events


@pytest.mark.parametrize("fmt", ["p1", "p2"])
@pytest.mark.parametrize("duration_ms", [1, 100, 200, 30000])
async def test_timed_move_deadline_cancels_slow_ack_before_release(hass, fmt, duration_ms):
    async with live_bed(hass, fmt) as (coord, ctrl):
        with virtual_clock() as clock:

            def serialized(_frame):
                assert coord._command_lock.locked()

            events = acknowledged_writer(ctrl, clock, on_start=serialized)
            call = ServiceCall(
                hass,
                DOMAIN,
                "timed_move",
                {
                    "device_id": ["bed"],
                    "motor": "back",
                    "direction": "up",
                    "duration_ms": duration_ms,
                },
            )
            with patch(
                "custom_components.adjustable_bed.services._resolve_sided_targets",
                return_value=([(coord, SIDE_BOTH)], []),
            ):
                await handle_timed_move(call)
            starts = [(frame, at) for kind, frame, at in events if kind == "start"]
            release = codec.stop(fmt, motor=True)
            assert starts[-1] == (release, duration_ms + (100 if fmt == "p1" else 0))
            assert all(at <= duration_ms for frame, at in starts if frame != release)
            assert any(
                kind == "cancel" and frame == codec.motion(fmt, 1, True) and at == duration_ms
                for kind, frame, at in events
            )
            assert events[-1] == ("ack", release, starts[-1][1] + 150)
            assert not ctrl._ble_lock.locked() and not coord._command_lock.locked()


@pytest.mark.parametrize("fmt", ["p1", "p2"])
async def test_ordinary_pulse_count_has_no_bounded_hold_deadline(hass, fmt):
    async with live_bed(hass, fmt) as (coord, ctrl):
        with virtual_clock() as clock:
            events = acknowledged_writer(ctrl, clock)
            await coord.async_execute_controller_command(lambda bed: bed.move_back_up())
            starts = [(frame, at) for kind, frame, at in events if kind == "start"]
            assert starts == [(codec.motion(fmt, 1, True), at) for at in (0, 150, 300)] + [
                (codec.stop(fmt, motor=True), 550 if fmt == "p1" else 450)
            ]
            assert not any(kind == "cancel" for kind, _, _ in events)


@pytest.mark.parametrize("fmt", ["p1", "p2"])
async def test_renewed_lease_outlives_initial_bounded_duration(hass, fmt):
    async with live_bed(hass, fmt) as (coord, ctrl):
        with virtual_clock() as clock:
            events = acknowledged_writer(ctrl, clock)

            async def move(bed):
                await bed.move_axis("back", True, duration_ms=200)

            task = asyncio.create_task(
                coord.async_execute_controller_command(
                    move,
                    resource="motor:back",
                    kind=CommandKind.HOLD,
                    lease=HoldLease(owner="card", generation=1, action="back_up", duration_s=0.25),
                )
            )
            await asyncio.sleep(0.2)
            await coord.async_execute_controller_command(
                move,
                resource="motor:back",
                kind=CommandKind.HOLD,
                lease=HoldLease(owner="card", generation=1, action="back_up", duration_s=0.4),
            )
            await task
            starts = [(frame, at) for kind, frame, at in events if kind == "start"]
            assert any(frame == codec.motion(fmt, 1, True) and at >= 300 for frame, at in starts)
            assert starts[-1][0] == codec.stop(fmt, motor=True)
            assert starts[-1][1] >= 600


def ai_zero_button(hass, coord):
    entity = next(
        entity
        for entity in _button_entities_for(hass, coord)
        if isinstance(entity, ControllerActionButton) and entity._spec.key == "smart_sleep_ai_zero"
    )
    entity.hass = hass
    entity.entity_id = "button.smart_sleep_ai_zero"
    return entity


@pytest.mark.parametrize("entry_point", ["entity", "direct"])
@pytest.mark.parametrize("outcome", ["normal", "child", "write_error", "write_timeout"])
async def test_ordinary_ai_zero_entity_always_releases(hass, outcome, entry_point):
    async with live_bed(hass, "p1", 8) as (coord, ctrl):
        entity = ai_zero_button(hass, coord)

        async def recall():
            if entry_point == "entity":
                await entity.async_press()
            else:
                await ctrl.recall("ai_zero")

        with virtual_clock() as clock:

            def on_start(frame):
                if frame == codec.preset("p1", "ai_zero"):
                    if outcome == "child":
                        ctrl.select_child("on")
                    elif outcome == "write_error":
                        raise BleakError("failed acknowledged write")
                    elif outcome == "write_timeout":
                        raise TimeoutError("peripheral ACK timed out")

            events = acknowledged_writer(ctrl, clock, on_start=on_start)
            if outcome == "normal":
                await recall()
            else:
                error = (
                    ValueError
                    if outcome == "child"
                    else BleakError
                    if outcome == "write_error"
                    else TimeoutError
                )
                with pytest.raises(error):
                    await recall()
            starts = [(frame, at) for kind, frame, at in events if kind == "start"]
            assert [frame for frame, _ in starts] == [codec.preset("p1", "ai_zero")] * (
                2 if outcome == "normal" else 1
            ) + [codec.stop("p1")]
            assert events[-1][0:2] == ("ack", codec.stop("p1"))
            assert not ctrl._ble_lock.locked() and not coord._command_lock.locked()


@pytest.mark.parametrize("cancel_at", [0.05, 0.2, 0.35])
async def test_ai_zero_preemption_drains_release_before_replacement(hass, cancel_at):
    async with live_bed(hass, "p1", 8) as (coord, ctrl):
        entity = ai_zero_button(hass, coord)
        with virtual_clock() as clock:
            events = acknowledged_writer(ctrl, clock)
            pending = asyncio.create_task(entity.async_press())
            await asyncio.sleep(cancel_at)
            ctrl.select_child("on")
            await coord.async_execute_controller_command(
                lambda bed: bed.write_command(codec.privacy(True))
            )
            await pending
            frames = [frame for kind, frame, _ in events if kind == "start"]
            assert frames[-2:] == [codec.stop("p1"), codec.privacy(True)]
            assert frames.count(codec.stop("p1")) == 1
            assert not ctrl._ble_lock.locked() and not coord._command_lock.locked()


async def test_ai_zero_captured_cleanup_does_not_write_to_replacement_session(hass):
    async with live_bed(hass, "p1", 8) as (coord, ctrl):
        old_client, old_session = ctrl.client, ctrl._session
        replacement = controller("p2").client
        replacement.disconnect = AsyncMock(
            side_effect=lambda: setattr(replacement, "is_connected", False)
        )
        original_cleanup = ctrl._cleanup
        captured = []

        async def cleanup(frame, session, client, delay_ms=0):
            captured.append((frame, session, client, delay_ms))
            await original_cleanup(frame, session, client, delay_ms)

        ctrl._cleanup = cleanup
        with virtual_clock() as clock:

            def switch(frame):
                if frame == codec.preset("p1", "ai_zero"):
                    old_client.is_connected = False
                    ctrl.on_disconnect()
                    coord._client = replacement

            events = acknowledged_writer(ctrl, clock, on_start=switch)
            with pytest.raises(ConnectionError):
                await ctrl.recall("ai_zero")
        assert captured == [(codec.stop("p1"), old_session, old_client, 100)]
        assert len([event for event in events if event[0] == "start"]) == 1
        replacement.write_gatt_char.assert_not_called()


async def test_bounded_move_preserves_a_real_ack_timeout_and_releases(hass):
    async with live_bed(hass, "p2") as (_coord, ctrl):
        with virtual_clock() as clock:

            def fail(frame):
                if frame == codec.motion("p2", 1, True):
                    raise TimeoutError("transport timed out before movement deadline")

            events = acknowledged_writer(ctrl, clock, on_start=fail)
            with pytest.raises(TimeoutError, match="transport timed out"):
                await ctrl.move_axis("back", True, duration_ms=200)
            assert [frame for kind, frame, _at in events if kind == "start"] == [
                codec.motion("p2", 1, True),
                codec.stop("p2", motor=True),
            ]
