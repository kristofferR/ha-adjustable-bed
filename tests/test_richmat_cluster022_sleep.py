"""Separate sleep-receiver framing, guards and session ownership."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from bleak.exc import BleakError
from homeassistant.const import CONF_ADDRESS

from custom_components.adjustable_bed.beds.richmat_mh.cluster022_sleep import (
    Cluster022SleepController,
)
from custom_components.adjustable_bed.beds.ruf_richmat.protocol import sleep_frame
from custom_components.adjustable_bed.beds.ruf_richmat.sleep import CHARACTERISTIC
from tests.test_richmat_cluster022 import make
from tests.test_richmat_mh import sleeps as sleeps


def receiver(app="nisco"):
    coordinator = make(app)._coordinator
    coordinator.entry.data[CONF_ADDRESS] = "11:22:33:44:55:66"
    controller = Cluster022SleepController(coordinator, app=app)
    controller._char = MagicMock(uuid=CHARACTERISTIC)
    controller._owner = coordinator.client
    return controller


@pytest.mark.parametrize(("app", "attempts"), [("nisco", 4), ("mlily_supreme", 3)])
async def test_notify_failure_limit_belongs_to_each_app(app, attempts, sleeps) -> None:
    controller = receiver(app)
    controller.client.start_notify = AsyncMock(side_effect=BleakError("subscribe failed"))
    with pytest.raises(BleakError, match="subscribe failed"):
        await controller.start_notify()
    assert controller.client.start_notify.await_count == attempts
    assert sleeps == [1] * attempts
    assert controller._heartbeat is None


async def test_sleep_stop_invalidates_notification_and_drains_background(sleeps) -> None:
    controller = receiver()
    controller.client.start_notify = AsyncMock()
    controller.client.stop_notify = AsyncMock()
    await controller.start_notify()
    callback = controller.client.start_notify.call_args.args[1]
    await controller.stop_notify()
    state = dict(controller._coordinator.controller_state)
    callback(controller._char, bytearray(sleep_frame(0x11, b'{"Left":{"HD":99}}')))
    assert controller._coordinator.controller_state == state
    assert controller._heartbeat is None
    controller.client.stop_notify.assert_awaited_once()


@pytest.mark.parametrize(("app", "attempts"), [("nisco", 4), ("mlily_supreme", 3)])
async def test_notify_failure_uses_each_apps_own_bounded_limit(app, attempts, sleeps) -> None:
    controller = receiver(app)
    controller.client.start_notify = AsyncMock(side_effect=BleakError("notify failed"))
    with pytest.raises(BleakError):
        await controller.start_notify()
    assert controller.client.start_notify.await_count == attempts
    assert sleeps == [1] * attempts
    assert controller._heartbeat is None


async def test_notify_success_and_stop_invalidate_old_callback_and_drain_tasks(sleeps) -> None:
    controller = receiver()
    owner = controller.client
    owner.start_notify, owner.stop_notify = AsyncMock(), AsyncMock()
    # An actual blocked coroutine lets stop_notify exercise cancellation/drain.
    async def heartbeat():
        await asyncio.Event().wait()
    controller._heartbeat_loop = heartbeat
    await controller.start_notify()
    receive = owner.start_notify.call_args.args[1]
    task = controller._heartbeat
    await controller.stop_notify()
    assert task.done()
    owner.stop_notify.assert_awaited_once_with(controller._char)
    controller._apply_frame = MagicMock()
    receive(controller._char, bytearray(sleep_frame(1)))
    controller._apply_frame.assert_not_called()


@pytest.mark.parametrize("app", ["nisco", "mlily_supreme"])
async def test_settings_keep_bed_schema_and_local_ack_beside_excluded_metadata(app) -> None:
    controller = receiver(app)
    controller._queue_reply = MagicMock()
    attributes = {"MAC": "excluded", "CV": "excluded", "NV": "excluded",
                  "SDMode": 1, "SDModeSet": 1, "LI": 1, "RI": 0}
    controller._notify(None, bytearray(sleep_frame(0x12, json.dumps(attributes).encode())))
    assert controller._attributes == {key: attributes[key] for key in ("SDMode", "SDModeSet", "LI", "RI")}
    controller._queue_reply.assert_called_once_with(sleep_frame(0xA5, b"\x12"))
    state = controller._coordinator.controller_state
    assert state["ruf_richmat_sleep_left_intervention"] == "on"
    assert state["ruf_richmat_sleep_right_intervention"] == "off"
    with pytest.raises(ValueError, match="fixed single-user"):
        await controller.set_sleep_option("mode", "double")
    controller.write_command = AsyncMock()
    if app == "nisco":
        await controller.direct_user_mode("double")
        controller.write_command.assert_awaited_once_with(sleep_frame(0x14, b"\x01\x03\x02"))
    else:
        with pytest.raises(ValueError, match="only for Nisco"):
            await controller.direct_user_mode("double")
        controller.write_command.assert_not_awaited()


@pytest.mark.parametrize(("app", "std"), [("nisco", None), ("mlily_supreme", 1)])
def test_live_defaults_and_saved_receiver_gate_are_not_borrowed(app, std) -> None:
    controller = receiver(app)
    payload = json.dumps({"Left": {"HD": 70, "BD": 15, "IsOnBed": 1, "IsMove": 0}}).encode()
    controller._notify(None, bytearray(sleep_frame(0x11, payload)))
    state = controller._coordinator.controller_state
    assert state["ruf_richmat_sleep_left_heart_rate"] == 70
    assert state.get("richmat_cluster022_sleep_left_state") == std
    state.clear()
    controller._coordinator.entry.data.pop(CONF_ADDRESS)
    controller._notify(None, bytearray(sleep_frame(0x11, payload)))
    assert ("ruf_richmat_sleep_left_heart_rate" in state) == (app == "nisco")


def test_fragment_crc_and_signed_length_fences_are_explicit() -> None:
    controller = receiver()
    controller._apply_frame = MagicMock()
    frame = sleep_frame(0x11, json.dumps({"Left": {"HD": 70}}).encode())
    controller._notify(None, bytearray(frame[:20]))
    controller._apply_frame.assert_not_called()
    controller._notify(None, bytearray(frame[20:]))
    controller._apply_frame.assert_called_once_with(frame)
    controller._apply_frame.reset_mock()
    damaged = frame[:-1] + bytes((frame[-1] ^ 1,))
    controller._notify(None, bytearray(damaged))
    controller._notify(None, bytearray((0xFA, 0x80, 0, 1)))
    controller._apply_frame.assert_not_called()
    assert not controller._buffer


async def test_queued_reply_cannot_migrate_after_reconnect() -> None:
    controller = receiver()
    queued = []

    async def enqueue(command, **_kwargs):
        queued.append(command)

    controller._coordinator.async_execute_controller_command = enqueue
    await controller._serialized_write(sleep_frame(1))
    controller.on_disconnect()
    controller._owner = controller._coordinator.client = MagicMock(is_connected=True)
    with pytest.raises(ConnectionError, match="previous session"):
        await queued[0](controller)


async def test_fifo_write_cancellation_drains_actual_inflight_write() -> None:
    controller = receiver()
    began, drain = asyncio.Event(), asyncio.Event()

    async def write(*_args, **_kwargs):
        began.set()
        await drain.wait()

    controller.client.write_gatt_char.side_effect = write
    task = asyncio.create_task(controller.write_command(sleep_frame(1)))
    await began.wait()
    task.cancel()
    await asyncio.sleep(0)
    assert not task.done()
    drain.set()
    with pytest.raises(asyncio.CancelledError):
        await task
