"""Public STOP, reconnect, subscription recovery and session-scoped state."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed.beds.sealy.controller import MASSAGE_ON
from custom_components.adjustable_bed.const import DOMAIN
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.light import LIGHT_DESCRIPTION, AdjustableBedOnOffLight
from custom_components.adjustable_bed.paired_coordinator import (
    PairedBedCoordinator,
    PairedSideError,
)
from custom_components.adjustable_bed.state_keys import UNDER_BED_LIGHTS_ON
from tests.error_helpers import raises_key
from tests.hold_lease_wire import virtual_clock
from tests.test_paired_coordinator import RecordingChild
from tests.test_sealy import COMMANDS, bed, frames


@pytest.fixture
async def native(hass, mock_coordinator_connected, mock_bleak_client):
    _, _, sample, _ = await bed()
    mock_bleak_client.services = sample.services
    mock_bleak_client.write_gatt_char = AsyncMock()
    mock_bleak_client.start_notify = AsyncMock()
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "address": "AA:BB:CC:DD:EE:FF",
            "name": "Sealy",
            "bed_type": "sealy_posturematic",
            "product_type": "0",
            "disable_angle_sensing": True,
            "connection_mode": "idle",
        },
    )
    entry.add_to_hass(hass)
    target = AdjustableBedCoordinator(hass, entry)
    try:
        with virtual_clock():
            assert await target.async_connect()
        yield target, mock_bleak_client
    finally:
        await target.async_shutdown()


async def test_public_stop_disconnect_then_manual_connect(native):
    target, client = native
    with virtual_clock():
        await target.async_stop_command()
        await target.async_disconnect()
        assert target.cancel_command.is_set()
        client.is_connected = True
        client.write_gatt_char.reset_mock()
        assert await target.async_connect()
    assert frames(client) == [
        COMMANDS[k] for k in ("initialize", "query_anti_pinch", "query_massage")
    ]


async def test_startup_still_fences_a_new_stop():
    c, co, client, _ = await bed(start=False)
    co.cancel_command.set()  # Already-set idle event is not this startup's owner.

    async def sent(*args, **kwargs):
        co.cancel_counter += 1
        co.command_scheduler.stop_epoch += 1

    client.write_gatt_char.side_effect = sent
    session = SimpleNamespace(async_start_notify=c.start_notify)
    with virtual_clock():
        await c.async_on_connect(session)
        with pytest.raises(asyncio.CancelledError):
            await c.async_after_connect(session)
    assert frames(client) == [COMMANDS["initialize"]]


async def test_explicit_stop_drains_both_frames_across_epoch_changes():
    c, co, client, _ = await bed()
    client.write_gatt_char.reset_mock()

    async def sent(*args, **kwargs):
        co.cancel_counter += 1
        co.cancel_command.set()

    client.write_gatt_char.side_effect = sent
    with virtual_clock():
        await c.stop_all()
    assert frames(client) == [COMMANDS["stop"]] * 2 + [COMMANDS["voice_stop"]] * 2


@pytest.mark.parametrize("resubscribe", [True, False])
async def test_connected_notification_teardown_recovers(resubscribe):
    c, _, client, state = await bed()
    await c.stop_notify()
    if resubscribe:
        await c.start_notify()
    client.write_gatt_char.reset_mock()
    await c.lights_on()
    assert frames(client) == [COMMANDS["light_on"]]
    assert state.get(UNDER_BED_LIGHTS_ON) is True
    assert client.start_notify.await_count == 2


async def test_late_light_completion_cannot_republish_disconnected_state(native):
    target, client = native
    light = AdjustableBedOnOffLight(target, LIGHT_DESCRIPTION)
    light.async_write_ha_state = MagicMock()
    assert light.assumed_state is True and light.is_on is None

    async def sent(*args, **kwargs):
        client.is_connected = False
        target._on_disconnect(client)

    client.write_gatt_char.side_effect = sent
    with raises_key("sealy_session_changed"):
        await light.async_turn_on()
    assert target.controller_state.get(UNDER_BED_LIGHTS_ON) is None
    assert light.is_on is None


async def test_reported_wave_off_updates_switch_with_one_write():
    c, _, client, state = await bed()
    with virtual_clock():
        await c.massage_on()
    assert state.get(MASSAGE_ON) is True
    receive = client.start_notify.call_args.args[1]
    receive(c._link.notify, bytearray.fromhex("a50b000000000300"))
    client.write_gatt_char.reset_mock()
    await c.massage_mode_step()
    assert frames(client) == [COMMANDS["massage_off"]]
    assert state.get(MASSAGE_ON) is False


async def test_sequential_explicit_stop_reopens_without_two_links():
    log = []
    cap, _, _, _ = await bed()
    children = {}

    class Child(RecordingChild):
        async def async_connect(self):
            assert not any(c.is_connected for c in children.values() if c is not self)
            return await super().async_connect()

        async def async_stop_command(self):
            if not self.is_connected:
                assert await self.async_connect()
            await super().async_stop_command()

        async def async_stop_motor(self, stop_fn, resource, *, stream_member=False):
            await self.async_stop_command()

    for side in ("left", "right"):
        child = Child(side, log, connected=False)
        child.capability_controller = cap
        children[side] = child
    pair = PairedBedCoordinator(
        None,
        SimpleNamespace(data={"pair_id": "sealy", "name": "Bed"}),
        children,
        connection_mode="sequential",
    )
    try:
        # The native cycle releases each one-shot side. Link loss is not a STOP.
        await pair.async_execute_controller_command(
            lambda c: c.action("voice_head_up"), side="both"
        )
        assert not any(c.is_connected for c in children.values())
        log.clear()
        await pair.async_stop_command(side="both")
        assert log == [
            ("left", "connect"),
            ("left", "stop"),
            ("left", "disconnect"),
            ("right", "connect"),
            ("right", "stop"),
            ("right", "disconnect"),
        ]
        assert not any(c.is_connected for c in children.values())
        log.clear()
        await pair.async_stop_motor(lambda c: c.stop_all(), "motor:head", side="both")
        assert [(side, event) for side, event in log if event == "stop"] == [
            ("left", "stop"),
            ("right", "stop"),
        ]
        assert not any(c.is_connected for c in children.values())
        children["right"]._connected = True
        children["right"].fail_disconnect = True
        log.clear()
        with pytest.raises(PairedSideError):
            await pair.async_stop_command(side="left")
        assert ("left", "connect") not in log
        log.clear()
        with pytest.raises(PairedSideError):
            await pair.async_stop_command(side="both")
        assert ("left", "connect") not in log
        assert ("right", "stop") in log
    finally:
        await pair.async_shutdown()


@pytest.mark.parametrize("motor", [False, True])
@pytest.mark.parametrize(
    "stop_side,queued_side", [("right", None), ("right", "left"), ("left", "right")]
)
async def test_reconnecting_stop_preempts_the_other_sides_link_owner(motor, stop_side, queued_side):
    log = []
    cap, _, _, _ = await bed()
    entered = asyncio.Event()
    children = {}

    class Child(RecordingChild):
        async def async_execute_controller_command(self, *args, **kwargs):
            self._gate.clear()
            if self.side == "left":
                entered.set()
            try:
                await super().async_execute_controller_command(*args, **kwargs)
            finally:
                log.append((self.side, "release"))

        async def async_connect(self):
            assert not any(c.is_connected for c in children.values() if c is not self)
            return await super().async_connect()

        async def async_stop_command(self):
            if not self.is_connected:
                assert await self.async_connect()
            await super().async_stop_command()

        async def async_stop_motor(self, stop_fn, resource, *, stream_member=False):
            await self.async_stop_command()

    for side in ("left", "right"):
        child = Child(side, log, connected=False, block=side == "left")
        child.capability_controller = cap
        children[side] = child
    pair = PairedBedCoordinator(
        None,
        SimpleNamespace(data={"pair_id": "sealy", "name": "Bed"}),
        children,
        connection_mode="sequential",
    )
    tasks = []
    try:
        if stop_side == "right":
            await pair.async_execute_controller_command(
                lambda c: c.action("voice_head_up"), side="right"
            )
        assert not children["right"].is_connected
        children["right"]._block = queued_side == "right"
        log.clear()
        tasks.append(
            asyncio.create_task(
                pair.async_execute_controller_command(
                    lambda c: c.action("voice_head_up"), side="left", resource="motor:head"
                )
            )
        )
        await entered.wait()
        if queued_side is not None:
            tasks.append(
                asyncio.create_task(
                    pair.async_execute_controller_command(
                        lambda c: c.move_legs_up(),
                        side=queued_side,
                        resource="motor:feet",
                        cancel_running=False,
                    )
                )
            )
            await asyncio.sleep(0)
        stop = asyncio.create_task(
            pair.async_stop_motor(lambda c: c.stop_all(), "motor:head", side=stop_side)
            if motor
            else pair.async_stop_command(side=stop_side)
        )
        tasks.append(stop)
        done, _ = await asyncio.wait({stop}, timeout=3)
        assert done, "STOP waited for the other side's held command"
        await stop
        await asyncio.gather(*tasks)
        assert log.count(("left", "command")) == 1
        assert ("right", "command") not in log
        assert log.index(("left", "release")) < log.index(("left", "disconnect"))
        assert log.index(("left", "disconnect")) < len(log) - 3
        assert log[-3:] == [(stop_side, "connect"), (stop_side, "stop"), (stop_side, "disconnect")]
        for side, child in children.items():
            assert pair.stop_count(side) == child.stop_epoch == int(side == stop_side)
        assert not any(c.is_connected for c in children.values())
    finally:
        for child in children.values():
            child._block = False
            child._gate.set()
        await asyncio.gather(*tasks, return_exceptions=True)
        await pair.async_shutdown()


async def test_old_light_completion_preserves_a_replacement_sessions_state():
    c, co, client, state = await bed()
    began, finish = asyncio.Event(), asyncio.Event()

    async def sent(*args, **kwargs):
        began.set()
        await finish.wait()

    client.write_gatt_char.side_effect = sent
    task = asyncio.create_task(c.lights_off())
    await began.wait()
    c.on_disconnect()
    co.controller = MagicMock()
    state.update({UNDER_BED_LIGHTS_ON: True})
    finish.set()
    with raises_key("sealy_session_changed"):
        await task
    assert state.get(UNDER_BED_LIGHTS_ON) is True


@pytest.mark.parametrize("motor", [False, True])
async def test_stop_reconnect_is_not_cancelled_by_movement_admission(native, motor):
    target, client = native
    target.cache_capability_controller()
    with virtual_clock():
        await target.async_disconnect()
    client.is_connected = True
    began, finish = asyncio.Event(), asyncio.Event()

    async def subscribe(*args, **kwargs):
        began.set()
        await finish.wait()

    client.start_notify.side_effect = subscribe
    client.write_gatt_char.reset_mock()
    with virtual_clock():
        stop = asyncio.create_task(
            target.async_stop_motor(lambda c: c.stop_all(), "motor:head", stream_member=False)
            if motor else target.async_stop_command()
        )
        await began.wait()
        epoch = target.command_scheduler.stop_epoch
        movement = asyncio.create_task(target.async_execute_controller_command(
            lambda c: c.action("voice_head_up"), resource="motor:head"
        ))
        await asyncio.sleep(0)
        assert target.command_scheduler.stop_epoch == epoch
        finish.set()
        await asyncio.gather(stop, movement)
    assert frames(client)[-5:] == (
        [COMMANDS["stop"]] * 2 + [COMMANDS["voice_stop"]] * 2 + [COMMANDS["voice_head_up"]]
    )


async def test_motor_stop_waiting_for_writer_survives_movement_admission(native):
    target, client = native
    target.cache_capability_controller()
    client.write_gatt_char.reset_mock()
    await target._command_lock.acquire()
    stop = asyncio.create_task(
        target.async_stop_motor(lambda c: c.stop_all(), "motor:head", stream_member=False)
    )
    try:
        # The public call admits its STOP task, which then queues for the writer.
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        target.request_command_cancel("motor:head")
    finally:
        target._command_lock.release()
    with virtual_clock():
        await stop
    assert frames(client) == [COMMANDS["stop"]] * 2 + [COMMANDS["voice_stop"]] * 2


@pytest.mark.parametrize("motor", [False, True])
async def test_pair_stop_reserves_lane_before_later_movement(native, motor):
    target, client = native
    target.cache_capability_controller()
    with virtual_clock():
        await target.async_disconnect()
    pair = PairedBedCoordinator(
        None, SimpleNamespace(data={"pair_id": "sealy", "name": "Bed"}),
        {"left": target}, connection_mode="sequential",
    )
    client.write_gatt_char.reset_mock()
    try:
        with virtual_clock():
            stop = asyncio.create_task(
                pair.async_stop_motor(lambda c: c.stop_all(), "motor:head", side="left")
                if motor else pair.async_stop_command(side="left")
            )
            movement = asyncio.create_task(
                pair.async_execute_controller_command(
                    lambda c: c.action("voice_head_up"), side="left", resource="motor:head"
                )
            )
            await asyncio.gather(stop, movement)
        relevant = {COMMANDS["stop"], COMMANDS["voice_head_up"]}
        assert [f for f in frames(client) if f in relevant] == [
            COMMANDS["stop"], COMMANDS["stop"], COMMANDS["voice_head_up"]
        ]
    finally:
        await pair.async_shutdown()


@pytest.mark.parametrize("motor", [False, True])
@pytest.mark.parametrize("cancel_waiting", [False, True])
async def test_pair_queued_stop_keeps_its_lane_before_movement(native, motor, cancel_waiting):
    target, client = native
    target.cache_capability_controller()
    pair = PairedBedCoordinator(
        None, SimpleNamespace(data={"pair_id": "sealy", "name": "Bed"}),
        {"left": target}, connection_mode="sequential",
    )
    began, finish = asyncio.Event(), asyncio.Event()

    async def write(_char, data, **kwargs):
        if data.hex() == COMMANDS["stop"] and not began.is_set():
            began.set()
            await finish.wait()

    async def stop():
        if motor:
            await pair.async_stop_motor(lambda c: c.stop_all(), "motor:head", side="left")
        else:
            await pair.async_stop_command(side="left")

    client.write_gatt_char.side_effect = write
    client.write_gatt_char.reset_mock()
    try:
        with virtual_clock():
            first = asyncio.create_task(stop())
            await began.wait()
            second = asyncio.create_task(stop())
            await asyncio.sleep(0)
            movement = asyncio.create_task(pair.async_execute_controller_command(
                lambda c: c.action("voice_head_up"), side="left", resource="motor:head"
            ))
            await asyncio.sleep(0)
            if cancel_waiting:
                second.cancel()
                await asyncio.sleep(0)
                second.cancel()
            finish.set()
            await asyncio.gather(first, movement)
            if cancel_waiting:
                with pytest.raises(asyncio.CancelledError):
                    await second
            else:
                await second
        relevant = {COMMANDS["stop"], COMMANDS["voice_head_up"]}
        assert [f for f in frames(client) if f in relevant] == (
            [COMMANDS["stop"]] * 4 + [COMMANDS["voice_head_up"]]
        )
    finally:
        finish.set()
        await pair.async_shutdown()


async def test_cover_stop_after_dispatched_one_shot_drains_cycle_then_stops():
    log = []
    cap, _, _, _ = await bed()
    entered = asyncio.Event()
    children = {}

    class Child(RecordingChild):
        async def async_execute_controller_command(self, *args, **kwargs):
            entered.set()
            await super().async_execute_controller_command(*args, **kwargs)

        async def async_connect(self):
            assert not any(c.is_connected for c in children.values() if c is not self)
            return await super().async_connect()

        async def async_stop_motor(self, stop_fn, resource, *, stream_member=False):
            if not self.is_connected:
                await self.async_connect()
            await super().async_stop_command()

    child = Child("left", log, connected=False, block=True)
    child.capability_controller = cap
    children["left"] = child
    pair = PairedBedCoordinator(
        None,
        SimpleNamespace(data={"pair_id": "sealy", "name": "Bed"}),
        children,
        connection_mode="sequential",
    )
    try:
        movement = asyncio.create_task(
            pair.async_execute_controller_command(lambda c: c.action("voice_head_up"), side="left")
        )
        await entered.wait()
        await pair.async_stop_motor(lambda c: c.stop_all(), "motor:head", side="left")
        await movement
        assert ("left", "stop") in log
        assert log[-3:] == [("left", "connect"), ("left", "stop"), ("left", "disconnect")]
        assert not child.is_connected
    finally:
        await pair.async_shutdown()


@pytest.mark.parametrize("motor", [False, True])
async def test_cancelled_pair_stop_finishes_both_sides_and_disconnects(motor):
    log = []
    cap, _, _, _ = await bed()
    began, finish = asyncio.Event(), asyncio.Event()
    children = {}

    class Child(RecordingChild):
        async def async_connect(self):
            assert not any(c.is_connected for c in children.values() if c is not self)
            return await super().async_connect()

        async def async_stop_command(self):
            if not self.is_connected:
                await self.async_connect()
            await super().async_stop_command()
            if self.side == "left":
                began.set()
                await finish.wait()

        async def async_stop_motor(self, stop_fn, resource, *, stream_member=False):
            await self.async_stop_command()

    for side in ("left", "right"):
        child = Child(side, log, connected=False)
        child.capability_controller = cap
        children[side] = child
    pair = PairedBedCoordinator(
        None,
        SimpleNamespace(data={"pair_id": "sealy", "name": "Bed"}),
        children,
        connection_mode="sequential",
    )
    try:
        stop = asyncio.create_task(
            pair.async_stop_motor(lambda c: c.stop_all(), "motor:head", side="both")
            if motor
            else pair.async_stop_command(side="both")
        )
        await began.wait()
        stop.cancel()
        await asyncio.sleep(0)
        stop.cancel()
        await asyncio.sleep(0)
        assert not stop.done()
        finish.set()
        with pytest.raises(asyncio.CancelledError):
            await stop
        assert [(s, e) for s, e in log if e == "stop"] == [("left", "stop"), ("right", "stop")]
        assert not any(c.is_connected for c in children.values())
    finally:
        await pair.async_shutdown()
