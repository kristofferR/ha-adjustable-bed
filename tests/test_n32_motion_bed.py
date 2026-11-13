"""Accepted row080 literals, alarm semantics and real session/hold boundaries."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from bleak.exc import BleakError

from custom_components.adjustable_bed.bed_traits import bed_traits
from custom_components.adjustable_bed.beds.n32_motion_bed import controller as n32
from custom_components.adjustable_bed.beds.n32_motion_bed.state import (
    ALARM_KEYS,
    AlarmRow,
    callback_row,
)
from custom_components.adjustable_bed.codec import okin_nframe as codec
from custom_components.adjustable_bed.const import (
    BED_TYPE_N32_MOTION_BED,
    CONF_BED_TYPE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_HAS_MASSAGE,
    CONF_MOTOR_COUNT,
    CONF_MOTOR_PULSE_COUNT,
    CONF_MOTOR_PULSE_DELAY_MS,
    NORDIC_UART_READ_CHAR_UUID,
    NORDIC_UART_SERVICE_UUID,
    NORDIC_UART_WRITE_CHAR_UUID,
)
from custom_components.adjustable_bed.controller_state import ControllerState
from custom_components.adjustable_bed.profiles.n32_motion_bed import (
    N32,
    alarm_frame,
    alarm_week,
    clock_frame,
    effective_week,
    manufacturer_identity,
    query_frame,
)
from custom_components.adjustable_bed.setup_questions import setup_profile_for
from tests.hold_lease_wire import virtual_clock
from tests.test_controller_contract import _FactoryCoordinator

VECTORS = json.loads((Path(__file__).parent / "fixtures/n32_motion_bed_vectors.json").read_text())
ACTION_KEYS = {
    "stop": "stop",
    "m1m2up": "head_up",
    "m1m2down": "head_down",
    "m3up": "foot_up",
    "m3down": "foot_down",
    "m4up": "cervical_up",
    "m4down": "cervical_down",
    "m1m5": "memory_1",
    "m2m6": "memory_2",
    "antisnore": "memory_3",
    "lounge": "lounge",
    "tv": "tv_pc",
    "zero": "zero_g",
    "flat": "flat",
}


def frame(key):
    return codec.frame40(N32.keys[key])


@pytest.mark.parametrize("row", VECTORS["masks"], ids=lambda row: row["method"])
def test_all_twenty_independent_source_masks_use_existing_codec(row):
    literal = bytes((5, 2, *row["body"], 0))
    assert codec.frame40(int.from_bytes(bytes(row["body"]), "big")) == literal
    if row["method"] in ACTION_KEYS:
        assert frame(ACTION_KEYS[row["method"]]) == literal
    else:
        assert row["method"] not in N32.keys  # Individual upper motors are not capabilities.


@pytest.mark.parametrize(
    "row",
    [
        v
        for v in VECTORS["raw"]
        if v["function"] in ("held", "setup_alarm", "query_alarm", "calibrate", "effective_week")
    ],
    ids=lambda row: row["id"],
)
def test_frozen_raw_frames_and_once_dates(row):
    args, function = row["inputs"], row["function"]
    if function == "held":
        actual = frame(ACTION_KEYS[args["action"]])
    elif function == "setup_alarm":
        actual = alarm_frame(
            args["slot"], args["hour"], args["minute"], args["week"], args["mode"], args["enabled"]
        )
    elif function == "query_alarm":
        actual = query_frame(args["slot"])
    elif function == "calibrate":
        actual = clock_frame(datetime.fromisoformat(args["now"]))
    else:
        assert (
            effective_week(
                args["week"], args["hour"], args["minute"], datetime.fromisoformat(args["now"])
            )
            == row["expected"]
        )
        return
    assert actual == bytes.fromhex(row["expected"])


@pytest.mark.parametrize(
    "row",
    [v for v in VECTORS["repair"] if v["function"] == "manufacturer_real_mac"],
    ids=lambda row: row["id"],
)
def test_optional_identity_reverses_whole_payload_before_slice(row):
    data = {
        int(k): bytes(v) if v is not None else None
        for k, v in row["inputs"]["manufacturer_data"].items()
    }
    assert manufacturer_identity(data) == row["expected"]


@pytest.mark.parametrize(
    "row",
    [v for v in VECTORS["repair"] if v["function"] == "callback_alarm"],
    ids=lambda row: row["id"],
)
def test_callback_delete_before_old_row_and_disabled_preservation(row):
    args, expected = row["inputs"], row["expected"]
    old = args.get("old")
    previous = (
        AlarmRow(*(old[k] for k in ("hour", "minute", "week", "mode", "enabled"))) if old else None
    )
    report = codec.parse_alarm(bytes.fromhex(args["input_bytes"]))
    assert report is not None
    actual = callback_row(report, previous)
    if expected["operation"] == "delete":
        assert actual is None
    else:
        model = expected["model"]
        assert actual == AlarmRow(
            *(model[k] for k in ("hour", "minute", "week", "mode", "enabled"))
        )
        # Source music is phone-local. It never becomes a packet field or entity.


@pytest.mark.parametrize(
    "row",
    [
        v
        for v in VECTORS["repair"]
        if v["function"]
        in ("ui_close_alarm", "ui_delete_alarm", "ui_alarm_after_toggle", "setup_alarm")
    ],
    ids=lambda row: row["id"],
)
def test_corrected_set_disable_delete_literals_are_distinct(row):
    args, kind = row["inputs"], row["function"]
    if kind == "setup_alarm":
        assert (
            alarm_frame(
                args["slot"],
                args["hour"],
                args["minute"],
                args["week"],
                args["mode"],
                args["enabled"],
            ).hex(" ")
            == row["expected"]
        )
        return
    model = args["model"]
    if kind == "ui_delete_alarm":
        actual = alarm_frame(model["slot"], 0, 0, 0, 0, 0)
    else:
        if kind == "ui_alarm_after_toggle":
            # HA chooses weekdays directly; the source's Monday/Sunday widget
            # roundtrips retain their distinct UI and encoded once masks.
            week = alarm_week((0,)) if args["toggle"] == "day" else alarm_week(())
            assert week == row["expected"]["week"]
        else:
            week = model["week"]
        week = effective_week(
            week, model["hour"], model["minute"], datetime.fromisoformat(args["now"])
        )
        actual = alarm_frame(
            model["slot"],
            model["hour"],
            model["minute"],
            week,
            model["mode"],
            int(kind != "ui_close_alarm"),
        )
    expected = row["expected"]
    if isinstance(expected, dict):
        assert actual.hex(" ") == expected["bytes"]
    else:
        assert [actual.hex(" "), query_frame(model["slot"]).hex(" ")] == expected


def make_bed():
    write = SimpleNamespace(
        uuid=NORDIC_UART_WRITE_CHAR_UUID, properties=["write"], descriptors=[], handle=1
    )
    notify = SimpleNamespace(
        uuid=NORDIC_UART_READ_CHAR_UUID, properties=["notify"], descriptors=[], handle=2
    )
    client = MagicMock()
    client.is_connected = True
    client.disconnect = AsyncMock()
    client.services = [
        SimpleNamespace(uuid=NORDIC_UART_SERVICE_UUID, characteristics=[write, notify])
    ]
    client.write_gatt_char, client.start_notify, client.stop_notify = (
        AsyncMock(),
        AsyncMock(),
        AsyncMock(),
    )
    coordinator = _FactoryCoordinator()
    coordinator.client = client
    coordinator.record_command_trace = lambda **_kwargs: None
    coordinator.motor_count, coordinator.motor_pulse_count = 4, 3
    coordinator.controller_state = ControllerState()

    def updates(*values):
        coordinator.controller_state.update((u.key, u.value) for u in values)

    coordinator.handle_controller_state_updates = updates
    controller = n32.N32MotionBedController(coordinator)
    controller.static_traits = bed_traits(BED_TYPE_N32_MOTION_BED)
    coordinator.controller = controller
    return controller, coordinator, client


@pytest.fixture
async def bed():
    controller, coordinator, client = make_bed()
    await controller.async_discover_capabilities()
    await controller.start_notify()
    return controller, coordinator, client


def writes(client):
    return [c.args[1] for c in client.write_gatt_char.await_args_list]


def notify(client, value):
    client.start_notify.call_args.args[1](
        client.start_notify.call_args.args[0], bytearray.fromhex(value)
    )


async def test_capabilities_match_live_ui_and_setup_does_not_hide_pulse_count(bed):
    c, _, _ = bed
    assert c.profile is N32
    assert c.execution.hold == "stream" and not c.execution.concurrent
    assert not c.supports_single_address_pairing
    assert not c.supports_massage and not c.supports_lights and not c.has_lumbar_support
    assert not c.supports_position_feedback and not c.position_number_specs
    assert c.memory_slot_count == 3 and c.memory_slot_names == ("M1", "M2", "M3")
    assert not c.supports_memory_programming and not c.supports_preset_anti_snore
    specs = c.motor_control_specs
    assert [(s.key, s.translation_key) for s in specs] == [
        ("back", "n32_upper"),
        ("legs", "n32_lower"),
        ("head", "n32_cervical"),
    ]
    assert all(
        s.scheduler_resource == "*" and s.hold.press_hold_ms is None and s.hold.stop_scope == "side"
        for s in specs
    )
    owned = setup_profile_for({CONF_BED_TYPE: BED_TYPE_N32_MOTION_BED}).owns
    assert owned[CONF_MOTOR_COUNT] == 3
    assert owned[CONF_HAS_MASSAGE] is False
    assert owned[CONF_DISABLE_ANGLE_SENSING] is True and owned[CONF_MOTOR_PULSE_DELAY_MS] == 200
    assert CONF_MOTOR_PULSE_COUNT not in owned


@pytest.mark.parametrize("key", tuple(N32.keys)[1:])
async def test_each_live_hold_refreshes_then_releases_captured_characteristic(bed, key):
    c, _, client = bed
    with virtual_clock():
        await c.hold_control(key, 450)
    assert writes(client) == [frame(key)] * 3 + [frame("stop")]
    assert all(call.kwargs == {"response": True} for call in client.write_gatt_char.await_args_list)
    assert all(call.args[0] is c._link.write for call in client.write_gatt_char.await_args_list)


@pytest.mark.parametrize("latency", [0.1, 0.35])
async def test_slow_acknowledgement_cannot_extend_refresh_deadline(bed, latency):
    c, _, client = bed
    times = []
    with virtual_clock() as clock:

        async def write(_char, data, **_kwargs):
            times.append((round(clock.elapsed * 1000), data))
            await asyncio.sleep(latency)

        client.write_gatt_char.side_effect = write
        await c.hold_control("head_up", 600)
    held = [at for at, data in times if data != frame("stop")]
    assert held == ([0, 200, 400] if latency == 0.1 else [0, 400])
    assert all(at < 600 for at in held)
    assert times[-1][0] == (600 if latency == 0.1 else 750)


async def test_native_movement_keeps_user_pulses_and_cervical_mapping(bed):
    c, coord, client = bed
    with virtual_clock():
        await c.move_head_up()
    assert writes(client) == [frame("cervical_up")] * coord.motor_pulse_count + [frame("stop")]


async def test_frame_button_threshold_is_not_an_unbounded_save(bed):
    c, _, client = bed
    with virtual_clock() as clock:
        await c.hold_control("memory_3", 15000)
        assert clock.elapsed == pytest.approx(5.3)
    assert writes(client) == [frame("memory_3")] * 27 + [frame("stop")]


async def test_cancelled_queue_sends_only_fresh_event_release(bed):
    c, coord, client = bed
    async with c._ble_lock:
        task = asyncio.create_task(c.move_back_up())
        await asyncio.sleep(0)
        coord.cancel_command.set()
    await task
    assert writes(client) == [frame("stop")]


async def test_task_cancellation_finishes_stop_before_next_gesture(bed):
    c, coord, client = bed
    moving, stopped, release = asyncio.Event(), asyncio.Event(), asyncio.Event()

    async def write(_char, data, **_kwargs):
        if data == frame("stop"):
            stopped.set()
            await release.wait()
        else:
            moving.set()

    client.write_gatt_char.side_effect = write
    task = asyncio.create_task(c.hold_control("foot_up", 1000))
    await moving.wait()
    task.cancel()
    await stopped.wait()
    task.cancel()  # A repeated cancellation must not abandon the captured release.
    await asyncio.sleep(0)
    assert not task.done()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert writes(client) == [frame("foot_up"), frame("stop")]


async def test_old_session_cleanup_and_callback_cannot_touch_replacement(bed):
    c, _, client = bed
    old_link, callback = c._link, client.start_notify.call_args.args[1]
    await c.async_discover_capabilities()
    await c.start_notify()
    with pytest.raises(ConnectionError, match="session changed"):
        await c._release(old_link)
    callback(old_link.notify, bytearray.fromhex("a50c00008205061e00010000"))
    assert not c._seen and writes(client) == []


@pytest.mark.parametrize(
    "missing", ["write", "notify", "service", "write_property", "notify_property"]
)
async def test_missing_required_gatt_never_ready(bed, missing):
    c, _, client = bed
    service = client.services[0]
    if missing == "service":
        service.uuid = "0000"
    elif missing.endswith("property"):
        service.characteristics[0 if missing.startswith("write") else 1].properties = []
    else:
        service.characteristics = [
            ch
            for ch in service.characteristics
            if ch.uuid
            != (NORDIC_UART_WRITE_CHAR_UUID if missing == "write" else NORDIC_UART_READ_CHAR_UUID)
        ]
    with pytest.raises(ValueError, match="requires"):
        await c.async_discover_capabilities()
    assert c._link is None


async def test_two_subscription_attempts_and_disable_existing_subscription(bed):
    c, _, client = bed
    client.start_notify.reset_mock()
    client.start_notify.side_effect = [BleakError("retry"), None]
    await c.start_notify()
    assert client.start_notify.await_count == 2
    client.stop_notify.assert_awaited_once_with(c._link.notify)


async def test_startup_queries_all_slots_and_uses_fresh_clock_after_half_second(bed, monkeypatch):
    c, coord, client = bed
    now = datetime(2026, 11, 12, 23, 59, 1)
    monkeypatch.setattr(n32.dt_util, "now", lambda: now)
    with virtual_clock() as clock:
        await c.async_on_connect(SimpleNamespace(async_start_notify=AsyncMock()))
        assert clock.elapsed == pytest.approx(0.5)
    assert writes(client) == [query_frame(s) for s in (1, 2, 3)] + [clock_frame(now)]
    # The app's signed persisted-week filter is safely replaced by querying
    # every proven slot; startup never creates guessed empty alarm records.
    assert not any(keys.time in coord.controller_state for keys in ALARM_KEYS.values())


async def test_clock_materializes_after_wire_lock_not_before(bed, monkeypatch):
    c, _, client = bed
    now = datetime(2025, 8, 27, 12, 34, 56)
    monkeypatch.setattr(n32.dt_util, "now", lambda: now)
    async with c._ble_lock:
        task = asyncio.create_task(c.sync_clock())
        await asyncio.sleep(0)
        now = datetime(2026, 11, 12, 23, 59, 1)
    await task
    assert writes(client) == [clock_frame(now)]


@pytest.mark.parametrize(
    "row",
    [r for r in VECTORS["raw"] if r["function"] == "parse_notification"],
    ids=lambda r: r["id"],
)
async def test_live_notification_callback_is_only_alarm_telemetry(bed, row):
    c, coord, client = bed
    notify(client, row["input_bytes"])
    expected = row["expected"]
    if isinstance(expected, dict) and "alarm" in expected:
        hour, minute, week, mode, enabled, ab, soft, slot = expected["alarm"]
        keys = ALARM_KEYS[slot]
        assert coord.controller_state[keys.enabled] == bool(enabled)
        assert coord.controller_state[keys.ab] == ab and coord.controller_state[keys.soft] == soft
        if any((hour, minute, week, mode, enabled)):
            assert coord.controller_state[keys.time] == f"{hour:02d}:{minute:02d}"
        else:
            assert coord.controller_state[keys.time] is None
    else:
        assert not c._seen
        assert set(coord.controller_state) <= {keys.fresh for keys in ALARM_KEYS.values()}


@pytest.mark.parametrize("slot", (1, 2, 3))
async def test_actual_ui_delete_clears_and_queries_without_once_conversion(bed, slot):
    c, coord, client = bed
    await c.apply_alarm(slot, "delete", None)
    assert writes(client) == [alarm_frame(slot, 0, 0, 0, 0, 0), query_frame(slot)]
    assert ALARM_KEYS[slot].time not in coord.controller_state


async def test_disable_requires_new_report_and_preserves_fields(bed, monkeypatch):
    c, _, client = bed
    monkeypatch.setattr(n32.dt_util, "now", lambda: datetime(2026, 11, 14, 9))
    notify(client, "a50e00008205061e00010000")  # Earlier cache is not admission.

    async def write(_char, data, **_kwargs):
        if data == query_frame(3):
            notify(client, "a50e00001006082d00010000")  # Once, new 08:45 M2.

    client.write_gatt_char.side_effect = write
    await c.apply_alarm(3, "disable", None)
    assert writes(client) == [query_frame(3), bytes.fromhex("07078006082d00000100"), query_frame(3)]


async def test_missing_report_never_overwrites_unknown_fields(bed, monkeypatch):
    c, _, client = bed
    monkeypatch.setattr(n32, "ALARM_REPLY_TIMEOUT_S", 0.01)
    with virtual_clock(), pytest.raises(TimeoutError):
        await c.apply_alarm(2, "disable", None)
    assert writes(client) == [query_frame(2)]


async def test_disabled_partial_report_does_not_replay_cached_fields(bed):
    c, _, client = bed
    c._rows[1] = AlarmRow(6, 30, 130, 5, 1)

    async def write(_char, data, **_kwargs):
        if data == query_frame(1):
            notify(client, "a50c00000700090f00000000")

    client.write_gatt_char.side_effect = write
    await c.apply_alarm(1, "disable", None)
    assert writes(client) == [query_frame(1)]
    assert c._rows[1] == AlarmRow(9, 15, 130, 5, 0)


async def test_empty_enabled_byte_is_normalized_before_disable_admission(bed):
    c, _, client = bed

    async def write(_char, data, **_kwargs):
        if data == query_frame(1):
            notify(client, "a50c00000000000000010000")

    client.write_gatt_char.side_effect = write
    await c.apply_alarm(1, "disable", None)
    assert writes(client) == [query_frame(1)]


async def test_a_report_before_query_dispatch_does_not_satisfy_the_query(bed, monkeypatch):
    c, _, client = bed
    monkeypatch.setattr(n32, "ALARM_REPLY_TIMEOUT_S", 0.01)
    async with c._ble_lock:
        task = asyncio.create_task(c._query_slot(1))
        await asyncio.sleep(0)
        notify(client, "a50c00008205061e00010000")
    with virtual_clock(), pytest.raises(TimeoutError):
        await task
    assert writes(client) == [query_frame(1)]


async def test_disable_rechecks_report_revision_after_waiting_for_writer(bed, monkeypatch):
    c, _, client = bed
    original = c._write

    async def write(link, payload, cancel, **kwargs):
        if "revision" in kwargs:
            notify(client, "a50c00008206072d00010000")
        return await original(link, payload, cancel, **kwargs)

    async def reply(_char, data, **_kwargs):
        if data == query_frame(1):
            notify(client, "a50c00008205061e00010000")

    monkeypatch.setattr(c, "_write", write)
    client.write_gatt_char.side_effect = reply
    with pytest.raises(ValueError, match="changed while waiting"):
        await c.apply_alarm(1, "disable", None)
    assert writes(client) == [query_frame(1)]


async def test_once_date_is_selected_at_actual_alarm_dispatch(bed, monkeypatch):
    c, _, client = bed
    now = datetime(2026, 11, 14, 7)
    monkeypatch.setattr(n32.dt_util, "now", lambda: now)
    async with c._ble_lock:
        task = asyncio.create_task(c.apply_alarm(2, "set", AlarmRow(8, 45, 0, 6, 1)))
        await asyncio.sleep(0)
        now = datetime(2026, 11, 14, 9)
    await task
    assert writes(client) == [bytes.fromhex("07068006082d00010100"), query_frame(2)]


async def test_recreated_controller_keeps_display_but_invalidates_write_freshness(bed):
    c, coord, client = bed
    notify(client, "a50c00008205061e00010000")
    c.on_disconnect()
    replacement = n32.N32MotionBedController(coord)
    assert replacement._rows[1] == AlarmRow(6, 30, 130, 5, 1)
    assert not replacement._seen and not coord.controller_state[ALARM_KEYS[1].fresh]


@pytest.mark.parametrize(
    "days, expected", [([], 0), ([0], 130), ([6], 129), (list(range(7)), 255), ([0, 0, 2], 138)]
)
def test_ha_weekday_selection_retains_source_ui_mask(days, expected):
    assert alarm_week(days) == expected


@pytest.mark.parametrize("days", [[-1], [7], [True], [1.5]])
def test_invalid_weekdays_rejected_before_writes(days):
    with pytest.raises(ValueError):
        alarm_week(days)
