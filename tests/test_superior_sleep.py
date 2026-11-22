"""Frozen literals, real send paths and captured-session Superior Sleep cleanup."""

from __future__ import annotations

import asyncio
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from bleak.exc import BleakError
from homeassistant.exceptions import ServiceValidationError

from custom_components.adjustable_bed.alarm import WEEKDAYS, AlarmRequest
from custom_components.adjustable_bed.bed_traits import bed_traits
from custom_components.adjustable_bed.beds.superior_sleep import controller as bed
from custom_components.adjustable_bed.beds.superior_sleep import state_keys as s
from custom_components.adjustable_bed.command_scheduler import Delivery, delivered
from custom_components.adjustable_bed.controller_state import ControllerState
from custom_components.adjustable_bed.profiles import superior_sleep as p
from tests.hold_lease_wire import virtual_clock
from tests.superior_sleep_vectors import CONTROL_FRAMES, VECTORS

ALIASES = {
    "queryAlarm": "query_alarm",
    "queryMassage": "query_massage",
    "motionSensorOff": "motion_off",
    "motionSensorOn": "motion_on",
    "underbedLighting": "light",
    "waveReduce": "wave_down",
    "waveAdd": "wave_up",
    "footStrengthReduce": "massage_foot_down",
    "footStrengthAdd": "massage_foot_up",
    "headStrengthReduce": "massage_head_down",
    "headStrengthAdd": "massage_head_up",
    "meanwhileStrengthReduce": "massage_down",
    "meanwhileStrengthAdd": "massage_up",
    "massageMode": "massage_mode",
    "massageTimer": "massage_timer",
    "massageOff": "massage_off",
    "massageOn": "massage_on",
    "resetMemory": "reset_memories",
    "m2": "memory_2",
    "m1": "memory_1",
    "flatPosition": "flat",
    "anti": "anti_snore",
    "zeroGravity": "zero_g",
    "voiceStop": "speech_stop",
    "stop": "stop",
    "lounge": "lounge",
    "lumbarDown": "lumbar_down",
    "lumbarUp": "lumbar_up",
    "neckTiltDown": "back_down",
    "neckTiltUp": "back_up",
    "footDown": "foot_down",
    "footUp": "foot_up",
    "headDown": "head_down",
    "headUp": "head_up",
}


class Char:
    def __init__(self, uuid, properties, handle):
        self.uuid, self.properties, self.handle = uuid, properties, handle
        self.descriptors = []


def gatt(name="Smartbed123"):
    route = p.transport_for_name(name)
    chars = [
        Char(uuid, props, i)
        for i, (uuid, props) in enumerate(
            ((route.write, ["write-without-response"]), (route.notify, ["notify"])), 1
        )
    ]
    return [
        SimpleNamespace(
            uuid=route.service,
            characteristics=chars,
            get_characteristic=lambda uuid: next((c for c in chars if c.uuid == uuid), None),
        )
    ]


def controller(product="ss350", name="Smartbed123"):
    coord = MagicMock()
    coord.cancel_command = asyncio.Event()
    coord.connection_generation = 1
    coord.motor_pulse_count = 3
    coord.client.is_connected = True
    coord.client.services = gatt(name)
    coord.client.write_gatt_char = AsyncMock()
    coord.client.start_notify = AsyncMock()
    coord.client.stop_notify = AsyncMock()
    c = bed.SuperiorSleepController(coord, product, name)
    coord.controller = c
    coord.controller_state = ControllerState()
    coord.handle_controller_state_updates.side_effect = lambda *updates: (
        coord.controller_state.update({u.key: u.value for u in updates})
    )
    c.static_traits = bed_traits("superior_sleep")
    return c, coord, coord.client


@pytest.mark.parametrize("row", VECTORS, ids=lambda r: r["id"])
def test_frozen_literals_through_real_profile(row):
    action, args = row["action"], row["inputs"]
    if action in ALIASES:
        assert p.FRAMES[ALIASES[action]] == bytes.fromhex(row["expected_bytes"])
    elif action == "setCurrentTime":
        assert p.clock(
            datetime(**{k: v for k, v in args.items() if k != "weekday"})
        ) == bytes.fromhex(row["expected_bytes"])
    elif action == "setAlarm":
        assert p.alarm_fields(
            args["mask"], args["mode"], args["hour"], args["minute"]
        ) == bytes.fromhex(row["expected_bytes"])
    elif action == "setAlarmFromPicker":
        request = AlarmRequest(
            enabled=args["enabled"],
            hour=args["hour"],
            minute=args["minute"],
            weekdays=tuple(WEEKDAYS.index(day.lower()) for day in args["checked"]),
            wake_action="wake_mode_1",
            reference_time=datetime(2026, 11, 20),
        )
        assert p.alarm(request) == bytes.fromhex(row["expected_bytes"])
    else:
        data = bytes.fromhex(args["frame"])
        expected = row["expected_state"]
        if data[1] == 11:
            state = p.parse_massage(data)
            assert state is not None
            assert {key: getattr(state, key) for key in expected} == expected
        else:
            state = p.parse_alarm(data)
            assert state is not None
            assert {key: getattr(state, key) for key in expected} == expected


def test_exact_census_and_no_extra_speech_routes():
    assert {
        v.hex() for k, v in p.FRAMES.items() if k not in ("query_alarm", "query_massage")
    } == CONTROL_FRAMES
    assert len(p.SPEECH_ACTIONS) == 20
    assert all(
        not set(profile.adjustments) & set(p.SPEECH_ACTIONS) for profile in p.PROFILES.values()
    )
    assert [p.level(n) for n in range(7)] == [0, 1, 3, 2, 3, 4, 3]
    assert [p.alarm_display_days(mask) for mask in (2, 64, 1, 11)] == [
        "Sat",
        "Mon",
        "Sun",
        "Thu, Sat, Sun",
    ]


@pytest.mark.parametrize(
    "name,route",
    [("BLEabc", "ble"), ("bleabc", "nordic"), ("Smartbed1", "nordic"), ("Any name", "nordic")],
)
async def test_name_selects_gatt_only(name, route):
    c, _, client = controller("ss650", name)
    with virtual_clock():
        await c.async_discover_capabilities()
        await c.move_back_up()
    assert c.transport == p.TRANSPORTS[route]
    assert (
        client.write_gatt_char.await_args_list[0].args[0] is client.services[0].characteristics[0]
    )
    assert all(
        call.kwargs == {"response": False} for call in client.write_gatt_char.await_args_list
    )


@pytest.mark.parametrize("product", p.PROFILES)
async def test_every_button_and_selected_speech_caller(product):
    c, _, client = controller(product)
    with virtual_clock():
        await c.async_discover_capabilities()
        for action in c.button_actions:
            await c.action(action)
        for action in p.SPEECH_ACTIONS:
            await c.action(action, speech=True, duration_ms=200)
    assert {call.args[1] for call in client.write_gatt_char.await_args_list} <= set(
        p.FRAMES.values()
    )
    for action in c.profile.adjustments:
        with pytest.raises(ServiceValidationError):
            c.validate_action(action, True)


@pytest.mark.parametrize(
    "action,speech,times,tail",
    [
        ("head_up", False, [0, 100, 200], [(300, "stop"), (400, "stop")]),
        ("flat", True, [0, 100], []),
        ("massage_on", True, [0, 100], []),
        ("massage_up", False, [0, 100, 200, 300], [(400, "query_massage"), (500, "query_massage")]),
        ("motion_on", False, list(range(0, 5000, 100)), []),
    ],
)
async def test_real_refresh_attempts_and_release(action, speech, times, tail):
    c, _, client = controller()
    writes = []
    with virtual_clock() as clock:
        await c.async_discover_capabilities()
        client.write_gatt_char.side_effect = lambda _ch, data, **_kw: writes.append(
            (round(clock.elapsed * 1000), data)
        )
        await c.action(action, speech=speech)
    assert [at for at, frame in writes if frame == p.FRAMES[action]] == times
    assert [(at, frame) for at, frame in writes if frame != p.FRAMES[action]] == [
        (at, p.FRAMES[key]) for at, key in tail
    ]


async def test_cancel_releases_on_captured_owner_with_fresh_event():
    c, coord, client = controller()
    writes = []
    with virtual_clock() as clock:
        await c.async_discover_capabilities()
        client.write_gatt_char.side_effect = lambda _ch, data, **_kw: writes.append(
            (round(clock.elapsed * 1000), data)
        )
        task = asyncio.create_task(c.hold_control("head_up", 1000))
        await asyncio.wait({task}, timeout=0.15)
        coord.cancel_command.set()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert writes[-2:] == [(150, p.FRAMES["stop"]), (250, p.FRAMES["stop"])]
        # Local STOP has no authority over this running scheduler context.
        coord.cancel_command.clear()
        await c.stop_all()
        assert not coord.cancel_command.is_set()


async def test_retired_session_never_writes_or_publishes_to_replacement():
    c, coord, client = controller()
    with virtual_clock():
        await c.async_discover_capabilities()
        await c.start_notify(lambda *_: None)
        notify = client.start_notify.await_args.args[1]
        task = asyncio.create_task(c.action("head_up", duration_ms=1000))
        await asyncio.wait({task}, timeout=0.15)
        c.on_disconnect()
        coord.connection_generation += 1
        client.services = gatt()
        await c.async_discover_capabilities()
        replacement = client.services[0].characteristics[0]
        before = coord.handle_controller_state_updates.call_count
        notify(client.services[0].characteristics[1], bytearray.fromhex("a50b0e000258020203"))
        assert coord.handle_controller_state_updates.call_count == before
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert all(
            call.args[0] is not replacement for call in client.write_gatt_char.await_args_list
        )


async def test_delivery_state_and_exact_two_attempt_failures():
    c, coord, client = controller()
    outcomes = []
    with virtual_clock():
        await c.async_discover_capabilities()
        with delivered(outcomes.append):
            await c.action("motion_on")
        assert outcomes == [Delivery.SENT]
        assert coord.controller_state[s.MOTION] is True
        c.on_disconnect()
        assert coord.controller_state[s.MOTION] is None
        await c.async_discover_capabilities()
        client.write_gatt_char.reset_mock()
        client.write_gatt_char.side_effect = BleakError("temporary write failure")
        with pytest.raises(BleakError):
            await c.action("flat", speech=True)
        assert client.write_gatt_char.await_count == 2


@pytest.mark.parametrize("cancel_at,expected", [(0, False), (0.15, None), (4.95, True)])
async def test_motion_state_only_follows_its_delivered_refreshes(cancel_at, expected):
    from custom_components.adjustable_bed.command_scheduler import _CURRENT_COMMAND_CONTEXT
    from tests.test_shown_state import _running_command

    c, coord, _ = controller()
    coord.controller_state[s.MOTION] = False
    with virtual_clock():
        await c.async_discover_capabilities()
        token = _CURRENT_COMMAND_CONTEXT.set(_running_command(coord.cancel_command))
        try:
            if cancel_at == 0:
                coord.cancel_command.set()
                await c.action("motion_on")
            else:
                task = asyncio.create_task(c.action("motion_on"))
                await asyncio.wait({task}, timeout=cancel_at)
                coord.cancel_command.set()
                with pytest.raises(asyncio.CancelledError):
                    await task
        finally:
            _CURRENT_COMMAND_CONTEXT.reset(token)
    assert coord.controller_state[s.MOTION] is expected


@pytest.mark.parametrize(
    "seconds,minutes",
    [(0, 0), (1, 10), (600, 10), (601, 20), (1200, 20), (1201, 30), (1800, 30), (1801, 0)],
)
def test_timer_boundaries_and_truncation(seconds, minutes):
    data = bytes((0xA5, 11, 14, 0, seconds >> 8, seconds & 255, 1, 0, 0))
    assert p.parse_massage(data).timer_minutes == minutes
    for size in range(9):
        assert p.parse_massage(data[:size]) is None


async def test_startup_and_alarm_use_shared_lifecycle_and_actions():
    c, coord, client = controller()
    writes = []
    with virtual_clock() as clock:
        await c.async_discover_capabilities()
        client.write_gatt_char.side_effect = lambda _ch, data, **_kw: writes.append(
            (round(clock.elapsed * 1000), data)
        )
        await c.async_on_connect(
            SimpleNamespace(async_start_notify=AsyncMock(), is_current=lambda: True)
        )
        assert [at for at, _ in writes] == [0, 100, 500, 600]
        writes.clear()
        await c.configure_alarm(
            AlarmRequest(
                enabled=True,
                hour=6,
                minute=42,
                weekdays=(0, 2, 6),
                wake_action="wake_mode_2",
                reference_time=datetime(2026, 11, 20),
            )
        )
        assert [at for at, _ in writes] == [600, 700, 1100, 1200]
        assert writes[0][1].hex() == "07058b06062a000101"
        assert writes[-1][1] == p.FRAMES["query_alarm"]
        assert s.ALARM_MASK not in coord.controller_state  # No invented TX/RX round trip.


@pytest.mark.parametrize("action,duration", [("motion_on", 5000), ("head_up", 300)])
async def test_slow_gatt_never_dispatches_held_frames_after_deadline(action, duration):
    c, _, client = controller()
    writes = []
    with virtual_clock() as clock:
        await c.async_discover_capabilities()

        async def write(_char, frame, **_kw):
            writes.append((round(clock.elapsed * 1000), frame))
            await asyncio.sleep(0.15)

        client.write_gatt_char.side_effect = write
        await c.action(action, duration_ms=duration)
    held = [at for at, frame in writes if frame == p.FRAMES[action]]
    assert held and all(at < duration for at in held)
    if action == "motion_on":
        assert len(held) == 34
        assert len(writes) == len(held)  # No invented release.
    else:
        assert [frame for _, frame in writes[-2:]] == [p.FRAMES["stop"]] * 2


@pytest.mark.parametrize("retire", ["disconnect", "cancel"])
async def test_scheduled_writer_rechecks_ownership_and_cancel_before_dispatch(retire):
    c, coord, client = controller()
    await c.async_discover_capabilities()
    link = c._live()
    asyncio.get_running_loop().call_soon(
        c.on_disconnect if retire == "disconnect" else coord.cancel_command.set
    )
    await c._send(link, p.FRAMES["head_up"], coord.cancel_command)
    client.write_gatt_char.assert_not_awaited()


async def test_task_cancel_before_scheduled_dispatch_sends_nothing():
    c, coord, client = controller()
    await c.async_discover_capabilities()
    task = asyncio.create_task(c._send(c._live(), p.FRAMES["head_up"], coord.cancel_command))
    asyncio.get_running_loop().call_soon(task.cancel)
    with pytest.raises(asyncio.CancelledError):
        await task
    client.write_gatt_char.assert_not_awaited()


async def test_cancelling_after_slow_final_refresh_does_not_invent_a_skipped_frame():
    from custom_components.adjustable_bed.command_scheduler import _CURRENT_COMMAND_CONTEXT
    from tests.test_shown_state import _running_command

    c, coord, client = controller()
    outcomes = []
    with virtual_clock():
        await c.async_discover_capabilities()

        async def write(*_args, **_kwargs):
            await asyncio.sleep(0.15)

        client.write_gatt_char.side_effect = write
        token = _CURRENT_COMMAND_CONTEXT.set(_running_command(coord.cancel_command))
        try:
            with delivered(outcomes.append):
                task = asyncio.create_task(c.action("motion_on"))
                await asyncio.wait({task}, timeout=5.02)
                coord.cancel_command.set()
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task
        finally:
            _CURRENT_COMMAND_CONTEXT.reset(token)
    assert client.write_gatt_char.await_count == 34
    assert outcomes == [Delivery.SENT]
    assert coord.controller_state[s.MOTION] is True


async def test_cancelling_final_motion_frame_waiting_for_lock_is_partial():
    from custom_components.adjustable_bed.command_scheduler import _CURRENT_COMMAND_CONTEXT
    from tests.test_shown_state import _running_command

    c, coord, client = controller()
    held = asyncio.Event()
    with virtual_clock():
        await c.async_discover_capabilities()

        async def occupy_lock():
            await asyncio.sleep(4.85)
            async with c.ble_lock:
                await held.wait()

        locker = asyncio.create_task(occupy_lock())
        token = _CURRENT_COMMAND_CONTEXT.set(_running_command(coord.cancel_command))
        outcomes = []
        try:
            with delivered(outcomes.append):
                task = asyncio.create_task(c.action("motion_on"))
                await asyncio.wait({task}, timeout=4.95)
                coord.cancel_command.set()
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task
        finally:
            _CURRENT_COMMAND_CONTEXT.reset(token)
            held.set()
            await locker
    assert client.write_gatt_char.await_count == 49
    assert outcomes == [Delivery.PARTIAL]
    assert coord.controller_state[s.MOTION] is None


async def test_retired_cleanup_does_not_change_fully_sent_command_delivery():
    from custom_components.adjustable_bed.command_scheduler import _CURRENT_COMMAND_CONTEXT
    from tests.test_shown_state import _running_command

    c, coord, client = controller()
    outcomes = []
    with virtual_clock():
        await c.async_discover_capabilities()
        token = _CURRENT_COMMAND_CONTEXT.set(_running_command(coord.cancel_command))
        try:
            with delivered(outcomes.append):
                task = asyncio.create_task(c.action("head_up"))
                await asyncio.wait({task}, timeout=0.25)
                coord.connection_generation += 1
                coord.cancel_command.set()
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task
        finally:
            _CURRENT_COMMAND_CONTEXT.reset(token)
    assert client.write_gatt_char.await_count == 3
    assert outcomes == [Delivery.SENT]


async def test_final_massage_refresh_failure_still_sends_release_queries():
    c, _, client = controller()
    writes = []
    with virtual_clock() as clock:
        await c.async_discover_capabilities()

        async def write(_char, frame, **_kw):
            at = round(clock.elapsed * 1000)
            writes.append((at, frame))
            if at == 300 and frame == p.FRAMES["massage_up"]:
                raise BleakError("final massage refresh")

        client.write_gatt_char.side_effect = write
        with pytest.raises(BleakError, match="final massage refresh"):
            await c.action("massage_up")
    assert [at for at, frame in writes if frame == p.FRAMES["query_massage"]] == [400, 500]


@pytest.mark.parametrize(
    "row",
    [r for r in VECTORS if r["action"] == "parse" and r["id"].startswith("alarm-")],
    ids=lambda r: r["id"],
)
async def test_frozen_alarm_reports_reach_native_state_publisher(row):
    c, coord, client = controller()
    await c.async_discover_capabilities()
    await c.start_notify()
    callback = client.start_notify.await_args.args[1]
    callback(client.services[0].characteristics[1], bytearray.fromhex(row["inputs"]["frame"]))
    keys = {
        "alarm_hour": s.ALARM_HOUR,
        "alarm_minute": s.ALARM_MINUTE,
        "alarm_mask": s.ALARM_MASK,
        "alarm_selector": s.ALARM_SELECTOR,
        "alarm_enabled": s.ALARM_ENABLED,
    }
    assert {key: coord.controller_state[state_key] for key, state_key in keys.items()} == row[
        "expected_state"
    ]


@pytest.mark.parametrize("task_cancel", [False, True])
async def test_cancel_before_first_massage_dispatch_never_starts_massage_in_cleanup(task_cancel):
    c, coord, client = controller()
    with virtual_clock():
        await c.async_discover_capabilities()
        await c.ble_lock.acquire()
        task = asyncio.create_task(c.action("massage_on"))
        await asyncio.wait({task}, timeout=0.03)
        if task_cancel:
            task.cancel()
        else:
            coord.cancel_command.set()
        c.ble_lock.release()
        result = await asyncio.gather(task, return_exceptions=True)
        if task_cancel:
            assert isinstance(result[0], asyncio.CancelledError)
    assert [call.args[1] for call in client.write_gatt_char.await_args_list] == [
        p.FRAMES["query_massage"]
    ] * 2


async def test_overdue_started_massage_tick_runs_inside_the_release_query_window(monkeypatch):
    c, _, client = controller()
    writes = []
    release = c._release

    async def delayed_release(*args, **kwargs):
        await asyncio.sleep(0.003)  # Real event-loop scheduling jitter, in virtual time.
        await release(*args, **kwargs)

    monkeypatch.setattr(c, "_release", delayed_release)
    with virtual_clock() as clock:
        await c.async_discover_capabilities()
        client.write_gatt_char.side_effect = lambda _char, data, **_kw: writes.append(
            (round(clock.elapsed * 1000), data)
        )
        await c.action("massage_on")
    assert [at for at, frame in writes if frame == p.FRAMES["massage_on"]] == [0, 100, 200, 303]
    assert [at for at, frame in writes if frame == p.FRAMES["query_massage"]] == [400, 500]


async def test_delayed_gatt_does_not_extend_the_massage_tail_refresh_window():
    c, _, client = controller()
    writes = []
    with virtual_clock() as clock:
        await c.async_discover_capabilities()

        async def write(_char, data, **_kwargs):
            writes.append((round(clock.elapsed * 1000), data))
            if data == p.FRAMES["massage_on"]:
                await asyncio.sleep(0.5)

        client.write_gatt_char.side_effect = write
        await c.hold_control("massage_on", 100)
    assert writes == [
        (0, p.FRAMES["massage_on"]),
        (500, p.FRAMES["query_massage"]),
        (600, p.FRAMES["query_massage"]),
    ]


async def test_expired_first_held_write_reports_no_delivery():
    from custom_components.adjustable_bed.command_scheduler import _CURRENT_COMMAND_CONTEXT
    from tests.test_shown_state import _running_command

    c, coord, client = controller()
    outcomes = []
    with virtual_clock():
        await c.async_discover_capabilities()
        await c.ble_lock.acquire()
        token = _CURRENT_COMMAND_CONTEXT.set(_running_command(coord.cancel_command))
        try:
            with delivered(outcomes.append):
                task = asyncio.create_task(c.action("head_up", speech=True, duration_ms=1))
                await asyncio.wait({task}, timeout=0.01)
                c.ble_lock.release()
                await task
        finally:
            _CURRENT_COMMAND_CONTEXT.reset(token)
    assert outcomes == [Delivery.NONE]
    assert [call.args[1] for call in client.write_gatt_char.await_args_list] == [
        p.FRAMES["stop"]
    ] * 2


async def test_alarm_attempt_failure_still_runs_scheduled_readback_on_same_session():
    c, _, client = controller()
    request = AlarmRequest(
        enabled=True, hour=6, minute=42, weekdays=(0,), reference_time=datetime(2026, 11, 20)
    )
    writes = []
    with virtual_clock() as clock:
        await c.async_discover_capabilities()

        async def write(_char, data, **_kwargs):
            writes.append((round(clock.elapsed * 1000), data))
            if len(writes) == 1:
                raise BleakError("first alarm write")

        client.write_gatt_char.side_effect = write
        with pytest.raises(BleakError, match="first alarm write"):
            await c.configure_alarm(request)
    assert writes == [
        (0, p.alarm(request)),
        (100, p.alarm(request)),
        (500, p.FRAMES["query_alarm"]),
        (600, p.FRAMES["query_alarm"]),
    ]


async def test_explicit_bluetooth_name_wins_over_platform_alias():
    from custom_components.adjustable_bed.beds.builder import BuildContext

    c, coord, client = controller("ss650", "BLE123")
    coord.entry.data = {"ble_device_name": "BLE123"}
    context = BuildContext(
        coordinator=coord,
        bed_type="superior_sleep",
        variant="ss650",
        client=client,
        device_name="Bedroom bed",
    )
    c = await bed.build_controller(context)
    coord.controller = c
    assert c.transport == p.TRANSPORTS["ble"]
    await c.async_discover_capabilities()


@pytest.mark.parametrize("task_cancel", [False, True])
async def test_alarm_preemption_is_not_replaced_by_saved_write_error(task_cancel):
    c, coord, client = controller()
    alarm = AlarmRequest(enabled=True, hour=6, minute=42, reference_time=datetime(2026, 11, 20))
    writes = []
    with virtual_clock():
        await c.async_discover_capabilities()

        async def write(_char, data, **_kwargs):
            writes.append(data)
            if len(writes) == 1:
                raise BleakError("first alarm write")

        client.write_gatt_char.side_effect = write
        task = asyncio.create_task(c.configure_alarm(alarm))
        await asyncio.wait({task}, timeout=0.2)
        if task_cancel:
            task.cancel()
        else:
            coord.cancel_command.set()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert writes == [p.alarm(alarm)] * 2
    assert task.cancelled()


async def test_massage_on_and_off_are_one_switch_sending_the_old_buttons_frames():
    keys = {spec.key for spec in controller()[0].controller_button_specs}
    assert not {"superior_sleep_massage_on", "superior_sleep_massage_off"} & keys
    for on, action in ((True, "massage_on"), (False, "massage_off")):
        sent = []
        for press in (
            lambda ctrl, a=action: ctrl.action(a),  # what the button pressed
            lambda ctrl, o=on: next(
                spec for spec in ctrl.controller_switch_specs if spec.key == "superior_sleep_massage"
            ).set_fn(ctrl, o),
        ):
            c, coord, client = controller()
            with virtual_clock():
                await c.async_discover_capabilities()
                client.write_gatt_char.reset_mock()
                await press(c)
            sent.append([bytes(call.args[1]) for call in client.write_gatt_char.await_args_list])
            assert coord.controller_state[s.MASSAGE] is on
        assert sent[0] == sent[1] and p.FRAMES[action] in sent[0]
        c.on_disconnect()
        assert coord.controller_state[s.MASSAGE] is None


async def test_spoken_massage_on_and_off_move_the_massage_switch():
    c, coord, client = controller()
    with virtual_clock():
        await c.async_discover_capabilities()
        for on, action in ((True, "massage_on"), (False, "massage_off")):
            client.write_gatt_char.reset_mock()
            await c.action(action, speech=True)
            # The speech route's own burst, unchanged.
            assert {bytes(call.args[1]) for call in client.write_gatt_char.await_args_list} == {
                p.FRAMES[action]
            }
            assert coord.controller_state[s.MASSAGE] is on
