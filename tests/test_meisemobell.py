"""Real GATT writes, timing, notification/session boundaries and alarm preservation."""

from __future__ import annotations

import asyncio
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from bleak.exc import BleakError
from homeassistant.exceptions import ServiceValidationError

from custom_components.adjustable_bed.alarm import AlarmRequest
from custom_components.adjustable_bed.bed_traits import bed_traits
from custom_components.adjustable_bed.beds.meisemobell import state_keys as s
from custom_components.adjustable_bed.beds.meisemobell.controller import MeisemobellController
from custom_components.adjustable_bed.controller_state import ControllerState
from custom_components.adjustable_bed.profiles import meisemobell as p
from tests.hold_lease_wire import virtual_clock
from tests.test_superior_sleep import Char


def gatt(route):
    t = p.TRANSPORTS[route]
    write, notify = Char(t.write, ["write-without-response"], 1), Char(t.notify, ["notify"], 2)
    services = [SimpleNamespace(uuid=t.service, characteristics=[write])]
    if t.notify_service == t.service:
        services[0].characteristics.append(notify)
    else:
        services.append(SimpleNamespace(uuid=t.notify_service, characteristics=[notify]))
    return services


def controller(route="15_22_15a"):
    coord = MagicMock()
    coord.cancel_command = asyncio.Event()
    coord.motor_pulse_count = 2
    coord.client.is_connected = True
    coord.client.services = gatt(route)
    coord.client.write_gatt_char = AsyncMock()
    coord.client.start_notify = AsyncMock()
    coord.client.stop_notify = AsyncMock()
    coord.controller_state = ControllerState()
    coord.handle_controller_state_updates.side_effect = lambda *updates: (
        coord.controller_state.update({u.key: u.value for u in updates})
    )
    c = MeisemobellController(coord, route)
    coord.controller = c
    c.static_traits = bed_traits("meisemobell")
    return c, coord, coord.client


async def ready(c):
    await c.async_discover_capabilities()
    await c.start_notify()


def frames(client):
    return [bytes(call.args[1]) for call in client.write_gatt_char.await_args_list]


@pytest.mark.parametrize("route", p.PROFILES)
async def test_hold_stop_save_and_reset_schedules(route):
    c, coord, client = controller(route)
    await ready(c)
    with virtual_clock() as clock:
        stamps = []
        client.write_gatt_char.side_effect = lambda *_args, **_kwargs: stamps.append(clock.now)
        await c.hold_control("head_up", 601)
        assert frames(client) == [p.control(route, "head_up")] * 3 + [p.control(route, "stop")] * 2
        assert stamps == pytest.approx([0, 0.3, 0.6, 0.601, 0.701])
        client.write_gatt_char.reset_mock()
        stamps.clear()
        await c.program_memory(2)
        assert (
            frames(client) == [p.control(route, "memory_2")] * 17 + [p.control(route, "stop")] * 2
        )
        client.write_gatt_char.reset_mock()
        stamps.clear()
        await c.reset_memories()
        assert frames(client) == [p.control(route, "reset_memories")] * 31
        assert stamps[-1] - stamps[0] == pytest.approx(6)
        assert c.execution.hold_for("head_up") == "stream"
        assert not c.execution.concurrent


@pytest.mark.parametrize("route", p.PROFILES)
async def test_cancel_and_failed_write_release_with_fresh_event(route):
    c, coord, client = controller(route)
    await ready(c)

    async def cancel(_char, data, **_kwargs):
        if bytes(data) != p.control(route, "stop"):
            coord.cancel_command.set()

    client.write_gatt_char.side_effect = cancel
    with virtual_clock():
        await c.hold_control("foot_down", 1000)
    assert frames(client) == [p.control(route, "foot_down")] + [p.control(route, "stop")] * 2
    coord.cancel_command.clear()
    client.write_gatt_char.reset_mock()

    async def fail(_char, data, **_kwargs):
        if bytes(data) != p.control(route, "stop"):
            raise BleakError("lost")

    client.write_gatt_char.side_effect = fail
    with virtual_clock(), pytest.raises(BleakError):
        await c.hold_control("flat", 100)
    assert frames(client)[-2:] == [p.control(route, "stop")] * 2


@pytest.mark.parametrize("route", p.PROFILES)
async def test_session_admission_retry_late_callbacks_and_fragments(route):
    c, coord, client = controller(route)
    with pytest.raises(ConnectionError):
        await c.move_head_up()
    await c.async_discover_capabilities()
    client.start_notify.side_effect = [BleakError("retry"), None]
    await c.async_on_connect(
        SimpleNamespace(async_start_notify=c.start_notify, is_current=lambda: True)
    )
    assert client.start_notify.await_count == 2
    assert frames(client)[0][:2] == (b"\xe7\x80" if route == "15_22_15a" else b"\x07\x04")
    callback = client.start_notify.await_args.args[1]
    raw = bytes.fromhex(
        "ed8003061e8211072d841300" if route == "15_22_15a" else "a50c00008205061e0001"
    )
    callback(None, bytearray(raw))
    assert coord.controller_state[s.ALARM_1] == "06:30"
    assert coord.controller_state[s.SOURCE_1] == "reported"
    callback(None, bytearray(20))
    callback(None, bytearray(raw))
    assert coord.controller_state[s.ALARM_1] == "06:30"
    old = c._current()
    c.on_disconnect()
    callback(None, bytearray(raw))
    assert coord.controller_state[s.ALARM_1] is None
    client.start_notify.side_effect = None
    await c.async_discover_capabilities()
    await c.start_notify()
    client.write_gatt_char.reset_mock()
    await c._release_link(old)
    assert not frames(client)
    assert not c._alarms
    c.on_disconnect()
    client.services[0].characteristics[0].properties = ["write"]
    with pytest.raises(ServiceValidationError):
        await c.async_discover_capabilities()


@pytest.mark.parametrize("route", p.PROFILES)
async def test_alarm_peer_admission_readback_sent_state_and_query_timing(route):
    c, coord, client = controller(route)
    await ready(c)
    req = AlarmRequest(
        enabled=True,
        hour=6,
        minute=30,
        weekdays=(0,),
        slot=1,
        wake_action="memory_1",
        reference_time=datetime(2026, 11, 27),
    )
    with virtual_clock():
        if route == "15_22_15a":
            with pytest.raises(ServiceValidationError):
                await c.configure_alarm(req)
            assert all(f[:1] != b"\xed" for f in frames(client))
            c._receive(c._current(), bytes.fromhex("ed800300000000072d841300"))
        client.write_gatt_char.reset_mock()
        await c.configure_alarm(req)
    expected = (
        bytes.fromhex("ed8003061e8211072d8413000000000d")
        if route == "15_22_15a"
        else bytes.fromhex("07058205061e000100")
    )
    assert frames(client)[0] == expected
    assert coord.controller_state[s.SOURCE_1] == "sent"
    assert all(call.kwargs["response"] is False for call in client.write_gatt_char.await_args_list)
    assert p.alarm_request(route, req).week == 130
    assert (
        p.parse_massage(route, bytes.fromhex("a50b00000259000303")) == (2, 0, 2, 2)
        if route == "24_xx_xx"
        else p.parse_massage(route, bytes(9)) is None
    )


@pytest.mark.parametrize("route", p.PROFILES)
async def test_full_reset_closes_alarms_then_memory_at_two_seconds(route):
    c, coord, client = controller(route)
    await ready(c)
    with virtual_clock() as clock:
        stamps = []
        client.write_gatt_char.side_effect = lambda *_args, **_kwargs: stamps.append(clock.now)
        await c.reset_settings()
    reset = p.control(route, "reset_memories")
    index = frames(client).index(reset)
    assert stamps[index] == pytest.approx(2)
    assert frames(client)[index:] == [reset] * 31
    if route == "15_22_15a":
        assert (
            frames(client)[:index]
            == [bytes.fromhex("ed80030000000000000000000000008f")] + [bytes.fromhex("e180039b")] * 2
        )
        assert stamps[:index] == pytest.approx([0, 0.35, 0.7])
    else:
        assert frames(client)[:index] == [
            bytes.fromhex("070500000000000000"),
            bytes.fromhex("070600000000000000"),
        ]
        assert stamps[:index] == pytest.approx([0, 0.1])


@pytest.mark.parametrize("route", p.PROFILES)
async def test_task_cancellation_during_refresh_does_not_release_replacement_session(route):
    c, coord, client = controller(route)
    await ready(c)
    started = asyncio.Event()

    async def mark(_char, _data, **_kwargs):
        started.set()

    client.write_gatt_char.side_effect = mark
    task = asyncio.create_task(c.hold_control("head_up", 1000))
    await started.wait()
    c.on_disconnect()
    await ready(c)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert p.control(route, "stop") not in frames(client)


@pytest.mark.parametrize("route", p.PROFILES)
async def test_alarm_query_cannot_continue_on_a_new_session(route):
    c, coord, client = controller(route)
    await ready(c)

    async def replace(_char, _data, **_kwargs):
        c.on_disconnect()
        # A live coordinator could already have a different controller/client.

    client.write_gatt_char.side_effect = replace
    with virtual_clock(), pytest.raises(ConnectionError):
        await c.refresh_alarms()
    assert len(frames(client)) == 1


@pytest.mark.parametrize("route", p.PROFILES)
def test_alarm_headers_are_dispatched_independently_of_selected_route(route):
    assert p.parse_alarms(route, bytes.fromhex("ed8003061e8211072d001300")) == (
        (1, p.Alarm(6, 30, 130, 17, True)),
        (2, p.Alarm(7, 45, 0, 19, False)),
    )
    assert p.parse_alarms(route, bytes.fromhex("a50d00008413072d0001")) == (
        (2, p.Alarm(7, 45, 132, 19, True)),
    )
    assert p.parse_alarms(route, bytes.fromhex("ed800300")) == ()
    assert p.parse_alarms(route, bytes.fromhex("a50c0000")) == ()


@pytest.mark.parametrize("operation", ["set", "close"])
async def test_identical_alarm_readback_restores_invalidated_records(operation):
    c, coord, client = controller("15_22_15a")
    await ready(c)
    raw = bytes.fromhex(
        "ed8003061e8211072d841300" if operation == "set" else "ed8003000000000000000000"
    )
    c._receive(c._current(), raw)
    request = AlarmRequest(
        enabled=True,
        hour=6,
        minute=30,
        weekdays=(0,),
        slot=1,
        wake_action="memory_1",
        reference_time=datetime(2026, 11, 27),
    )

    async def reply_to_query(_char, data, **_kwargs):
        if bytes(data) in p.queries("15_22_15a"):
            c._receive(c._current(), raw)

    client.write_gatt_char.side_effect = reply_to_query
    with virtual_clock():
        if operation == "set":
            await c.configure_alarm(request)
        else:
            await c.close_alarms()
        assert set(c._alarms) == {1, 2}
        assert coord.controller_state[s.SOURCE_1] == "reported"
        await c.check_alarm(request)
