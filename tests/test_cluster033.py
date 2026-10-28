"""Accepted cluster033 packet, caller-domain, session and state conformance."""

from __future__ import annotations

import asyncio
import json
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

import pytest

from custom_components.adjustable_bed.alarm_table import (
    AlarmTableSchedule,
    OneTimeAlarmRecord,
    WeeklyAlarmRecord,
)
from custom_components.adjustable_bed.beds.cluster033 import (
    FFE4,
    FFE9,
    NUS_RX,
    NUS_TX,
    AppController,
    control_frame,
    mx_frame,
    name_frame,
)
from custom_components.adjustable_bed.beds.serta_mp_remote import (
    FOOT_TABLE,
    HEAD_TABLE,
    SertaMPRemoteController,
    pulse_angle,
    pulse_frame,
)
from custom_components.adjustable_bed.cluster033_profiles import (
    APP_LAYOUTS,
    app_profile,
)

FIXTURES = json.loads((Path(__file__).parent / "fixtures/cluster033/vectors.json").read_text())
APPS = tuple(APP_LAYOUTS)
NOW = datetime(2026, 10, 27, 10, 0, tzinfo=ZoneInfo("Europe/Oslo"))


def coordinator():
    result = MagicMock()
    result.client.is_connected = True
    result.client.start_notify = AsyncMock()
    result.client.stop_notify = AsyncMock()
    result.client.write_gatt_char = AsyncMock()
    result.motor_pulse_count = 3
    result.motor_count = 2
    result._cancel_command = asyncio.Event()
    result.cancel_command = result._cancel_command
    result.controller_state = {}
    result.handle_controller_state_updates.side_effect = result.controller_state.update
    rx = MagicMock(uuid=FFE4, properties=["notify"])
    tx = MagicMock(uuid=FFE9, properties=["write"])
    service = MagicMock()
    service.characteristics = [rx, tx]
    result.client.services = [service]
    return result


async def ready(app="tempur_curve", layout=None):
    coord = coordinator()
    ctrl = AppController(coord, app_profile(app, layout))
    ctrl._wait = AsyncMock(return_value=False)
    await ctrl.start_notify()
    coord.client.write_gatt_char.reset_mock()
    ctrl._wait.reset_mock()
    return ctrl, coord


def packets(coord):
    return [bytes(call.args[1]) for call in coord.client.write_gatt_char.await_args_list]


def schedule(**kwargs):
    return AlarmTableSchedule(weekly=(), one_time=(), dispatch="both", reference_time=NOW, **kwargs)


KEY_VECTORS = []
for package, fixture in FIXTURES.items():
    for vector in fixture["vectors"]:
        inputs = vector.get("inputs", {})
        expected = vector.get("expected_bytes")
        try:
            wire = bytes.fromhex(expected)
        except ValueError, TypeError:
            continue
        if len(wire) == 8 and wire[:3] == b"\xe5\xfe\x16" and vector.get("protocol") != "P2":
            key = next(
                (inputs[k] for k in ("key", "key_code", "mask", "code") if k in inputs), None
            )
            if key is not None:
                KEY_VECTORS.append(
                    pytest.param(
                        int(key, 0) if isinstance(key, str) else key,
                        wire,
                        id=f"{package}:{vector['id']}",
                    )
                )


@pytest.mark.parametrize(("key", "expected"), KEY_VECTORS)
def test_accepted_control_vectors(key, expected):
    """Independent frozen bytes cover each package's shared low32 arithmetic."""
    assert control_frame(key) == expected


@pytest.mark.parametrize(
    "side,expected",
    [
        ("both", "e5fe160100000005"),
        ("side_a", "e6fe16010000000103"),
        ("side_b", "e6fe16000000000203"),
    ],
)
def test_qplus_p1_side_vectors(side, expected):
    assert control_frame(0 if side == "side_b" else 1, side).hex() == expected


@pytest.mark.parametrize(
    "mask,expected",
    [
        (0x8000, "040200008000"),
        (0x10000, "040200010000"),
        (0x8000000, "040208000000"),
        (3, "040200000000"),
    ],
)
def test_mx_sparse_builder_vectors(mask, expected):
    assert mx_frame(mask).hex() == expected


@pytest.mark.parametrize(
    "name,expected",
    [
        ("Bed", "ef0242656400000000000000000000000003"),
        ("é", "ef02c300000000000000000000000000004b"),
    ],
)
def test_name_copy_uses_source_unit_count(name, expected):
    assert name_frame(name).hex() == expected


@pytest.mark.parametrize("name", ["", "A" * 16])
def test_name_rejects_empty_or_unsafe_payload_overflow(name):
    with pytest.raises(ValueError):
        name_frame(name)


@pytest.mark.parametrize("app", [a for a in APPS if a != "serta_mp_remote"])
def test_alarm_exact_weekday_wake_fields_and_disabled_rows(app):
    spec = app_profile(app).alarm
    value = AlarmTableSchedule(
        weekly=(
            WeeklyAlarmRecord(enabled=False, hour=23, minute=59),
            WeeklyAlarmRecord(enabled=True, hour=6, minute=45, weekdays=(0, 2, 6), wake=True),
        ),
        one_time=(
            OneTimeAlarmRecord(enabled=False),
            OneTimeAlarmRecord(enabled=True, hour=12, minute=3, wake=True),
        ),
        dispatch="both",
        reference_time=NOW.replace(second=56),
    )
    weekly, one_time = spec.encode(value)
    marker = 0 if app in ("omazz_adjusto_iii", "ergomotion_app") else 128
    wake = 16 if app == "qplus_app" else 3
    assert weekly[:7] == bytes((0xED, 0x80, 3, 6, 45, marker | 11, wake))
    assert one_time[:7] == bytes((0xED, 0x80, 2, 2, 2, 4, wake))
    assert weekly[7:15] == one_time[7:15] == bytes(8)
    assert (sum(weekly) & 255) == (sum(one_time) & 255) == 255


@pytest.mark.parametrize("app", [a for a in APPS if a != "serta_mp_remote"])
@pytest.mark.parametrize("dispatch", ["both", "weekly", "one_time"])
@pytest.mark.parametrize("table", ["weekly", "one_time"])
async def test_either_table_overflow_aborts_before_checksum_and_send(app, dispatch, table):
    ctrl, coord = await ready(app)
    value = AlarmTableSchedule(
        weekly=(WeeklyAlarmRecord(enabled=True, weekdays=(0,)),) * (4 if table == "weekly" else 1),
        one_time=(OneTimeAlarmRecord(enabled=True, hour=12),) * (4 if table == "one_time" else 1),
        dispatch=dispatch,
        reference_time=NOW,
    )
    with patch.object(
        type(ctrl.profile.alarm), "encode", wraps=ctrl.profile.alarm.encode
    ) as encode:
        with pytest.raises(ValueError, match="three|3"):
            ctrl.alarm_table_schedule_spec.validate(value)
        encode.assert_not_called()
    with pytest.raises(ValueError):
        await ctrl.configure_alarm_table_schedule(value)
    assert packets(coord) == []


@pytest.mark.parametrize("app", [a for a in APPS if a != "serta_mp_remote"])
@pytest.mark.parametrize(
    "dispatch,headers,waits",
    [("both", [3, 2], [500, 500]), ("weekly", [3], [500]), ("one_time", [2], [500])],
)
async def test_alarm_dispatch_empty_table_is_attempted_wire(app, dispatch, headers, waits):
    ctrl, coord = await ready(app)
    await ctrl.configure_alarm_table_schedule(replace(schedule(), dispatch=dispatch))
    assert [p[2] for p in packets(coord)] == headers
    assert [x.args[0] for x in ctrl._wait.await_args_list] == waits
    assert all(p[3:15] == bytes(12) for p in packets(coord))


@pytest.mark.parametrize(
    "row",
    [
        WeeklyAlarmRecord(enabled=True),
        WeeklyAlarmRecord(weekdays=(0, 0)),
        WeeklyAlarmRecord(weekdays=(7,)),
        WeeklyAlarmRecord(hour=24),
        WeeklyAlarmRecord(minute=-1),
    ],
)
def test_weekly_invalid_domain(row):
    with pytest.raises(ValueError):
        app_profile("tempur_curve").alarm.validate(replace(schedule(), weekly=(row,)))


@pytest.mark.parametrize(
    "now,hour,minute",
    [
        (NOW, 10, 0),
        (NOW, 9, 59),
        (datetime(2026, 3, 29, 0, 0, tzinfo=ZoneInfo("Europe/Oslo")), 2, 30),
        (datetime(2026, 10, 25, 0, 0, tzinfo=ZoneInfo("Europe/Oslo")), 2, 30),
    ],
)
def test_one_time_past_equal_dst_invalid_and_ambiguous(now, hour, minute):
    value = replace(
        schedule(),
        reference_time=now,
        one_time=(OneTimeAlarmRecord(enabled=True, hour=hour, minute=minute),),
    )
    with pytest.raises(ValueError):
        app_profile("tempur_au").alarm.encode(value)


def test_positive_subsecond_truncation_is_not_rejected_as_equal_time():
    value = replace(
        schedule(),
        reference_time=NOW.replace(second=59, microsecond=900000),
        one_time=(OneTimeAlarmRecord(enabled=True, hour=10, minute=1),),
    )
    assert app_profile("tempur_curve").alarm.encode(value)[1][3:7] == bytes(4)


@pytest.mark.parametrize("app", APPS)
async def test_current_session_requires_both_roles_and_ignores_stale_notifications(app):
    ctrl, coord = await ready(app)
    old_callback = coord.client.start_notify.await_args.args[1]
    ctrl.on_disconnect()
    old_callback(None, bytearray(20))
    coord.handle_controller_state_updates.assert_not_called()
    with pytest.raises(ConnectionError):
        await ctrl.write_command(b"x")
    assert packets(coord) == []
    coord.client.services[0].characteristics = []
    with pytest.raises(ConnectionError):
        await ctrl.start_notify()


async def test_qplus_independent_last_gatt_matches_not_style_or_service_pair():
    ctrl, coord = await ready("qplus_app", "H")
    service = MagicMock()
    rx = MagicMock(uuid=NUS_RX, properties=["notify"])
    tx = MagicMock(uuid=NUS_TX, properties=["write-without-response"])
    service.characteristics = [rx]
    later = MagicMock()
    later.characteristics = [tx]
    coord.client.services += [service, later]
    ctrl.on_disconnect()
    await ctrl.start_notify()
    assert ctrl._rx is rx and ctrl._tx is tx
    assert coord.client.write_gatt_char.await_args.args[0] is tx
    assert coord.client.write_gatt_char.await_args.kwargs["response"] is False


@pytest.mark.parametrize(
    "app,layout", [(app, layout) for app, layouts in APP_LAYOUTS.items() for layout in layouts]
)
async def test_declared_actions_dispatch_exact_event_lifecycle(app, layout):
    ctrl, coord = await ready(app, layout)
    for action in ctrl.profile.actions:
        coord.client.write_gatt_char.reset_mock()
        ctrl._wait.reset_mock()
        await ctrl._run_action(action.key)
        wire = packets(coord)
        assert wire[0] == ctrl._frame(action.mask)
        if action.mode in ("held", "held_zeros"):
            assert wire[:3] == [ctrl._frame(action.mask)] * 3
            if app == "qplus_app" and layout == "MX":
                assert wire[3:] == [b"\0\xb0"] * 3
                assert [w.args[0] for w in ctrl._wait.await_args_list] == [100] * 3 + [300] * 3
            else:
                assert wire[3] == control_frame(0)
                assert not any(p[:3] == b"\xe5\xfe\x16" and len(p) != 8 for p in wire)
        elif action.mode == "pulse":
            if app == "qplus_app" and layout == "MX":
                assert wire[1:] == [b"\0\xb0"] * 3
                assert [w.args[0] for w in ctrl._wait.await_args_list] == [300, 300, 300, 300]
            else:
                assert wire == [ctrl._frame(action.mask), control_frame(0)]
        elif action.mode == "tap_zeros":
            assert wire[1:] == [control_frame(0)] * 3
            assert [w.args[0] for w in ctrl._wait.await_args_list] == [300, 100, 100]
        elif app == "qplus_app" and layout == "MX":
            assert wire[1:] == [b"\0\xb0"] * 2
        else:
            assert wire == [ctrl._frame(action.mask)]


@pytest.mark.parametrize(
    "app", ["tempur_curve", "qplus_app", "ergomotion_app", "tempur_au", "ergo_slim"]
)
async def test_cancelled_hold_has_fresh_release_and_no_late_control_packets(app):
    ctrl, coord = await ready(app, "MX" if app == "qplus_app" else None)

    async def wait(ms, **kwargs):
        if not kwargs.get("cleanup"):
            coord._cancel_command.set()
            return True
        return False

    ctrl._wait.side_effect = wait
    await ctrl.hold_control("head_up", 60000)
    assert packets(coord)[0] == ctrl._frame(1)
    assert packets(coord)[1:] == ([b"\0\xb0"] * 3 if app == "qplus_app" else [control_frame(0)])


async def test_mx_memory1_is_opaque_held_action_and_release_has_no_zero():
    ctrl, coord = await ready("qplus_app", "MX")
    memory = next(s for s in ctrl.controller_button_specs if s.key == "mx_memory1")
    assert memory.name == "MX Memory 1"
    assert not ctrl.supports_memory_presets and not ctrl.supports_memory_programming
    await memory.press_fn(ctrl)
    assert packets(coord) == [bytes.fromhex("040200010000")] * 3 + [b"\0\xb0"] * 3
    assert (
        "mx_memory1"
        not in AppController(coordinator(), app_profile("qplus_app", "M2")).held_control_options
    )


@pytest.mark.parametrize(
    "app,length,flag_offset,status_offset,accept",
    [
        ("tempur_curve", 19, 14, 15, True),
        ("omazz_adjusto_iii", 19, None, 15, False),
        ("omazz_adjusto_iii", 23, None, 15, True),
        ("ergomotion_app", 19, None, 15, True),
        ("row_control", 19, 14, 15, True),
        ("tempur_au", 19, 14, 15, True),
        ("ergo_slim", 19, None, 15, False),
        ("serta_mp_remote", 20, None, 14, False),
    ],
)
def test_exact_parser_lengths_and_gates(app, length, flag_offset, status_offset, accept):
    coord = coordinator()
    ctrl = AppController(coord, app_profile(app))
    data = bytearray(length)
    data[status_offset] = 3
    ctrl._parse_notification(data)
    assert coord.controller_state.get("app_timer_status") == (3 if accept else None)
    if flag_offset is not None:
        coord.controller_state.clear()
        data[flag_offset] = 32
        ctrl._parse_notification(data)
        assert coord.controller_state == {}


@pytest.mark.parametrize("app", APPS)
def test_unknown_status_and_malformed_frames_retain_previous_state(app):
    coord = coordinator()
    ctrl = AppController(coord, app_profile(app))
    for n in range(24):
        data = bytearray(n)
        if n >= 15:
            data[14] = 3
        ctrl._parse_notification(data)
    old = coord.controller_state.copy()
    for n in range(24):
        ctrl._parse_notification(bytes([0x55]) * n)
    assert coord.controller_state == old


def test_qplus_prefix_precedence_and_all_current_side_selector_fates():
    for side in ("both", "side_a", "side_b"):
        coord = coordinator()
        ctrl = AppController(coord, app_profile("qplus_app"), side=side)
        data = bytearray(16)
        data[:5] = bytes.fromhex("a50b0d0259")  # 601 seconds -> state 2
        data[13] = 32
        ctrl._parse_notification(data)
        assert coord.controller_state["app_timer_status"] == 2
        data = bytearray(19)
        data[15], data[16] = 3, 2
        ctrl._parse_notification(data)
        assert coord.controller_state["app_timer_status"] == 2
        data[16] = 1
        ctrl._parse_notification(data)
        assert coord.controller_state["app_timer_status"] == 3


SERTA_PULSES = [
    pytest.param(v, id=v["id"])
    for v in FIXTURES["com-ore-serta330"]["vectors"]
    if v["protocol"] == "P1" and "head_pulse" in v["inputs"]
]


@pytest.mark.parametrize("vector", SERTA_PULSES)
def test_serta_accepted_angle_pulse_vectors(vector):
    inputs = vector["inputs"]
    assert pulse_frame(inputs["head_pulse"], inputs["foot_pulse"]) == bytes.fromhex(
        vector["expected_bytes"]
    )


def test_serta_calibration_midpoint_lower_and_inverted_boundaries():
    assert pulse_angle(168, HEAD_TABLE, 15430) == 0
    assert pulse_angle(169, HEAD_TABLE, 15430) == 1
    assert pulse_angle(65535, HEAD_TABLE, 15430) == 0
    assert pulse_angle(32768, HEAD_TABLE, 15430) == 60
    assert pulse_angle(11668, FOOT_TABLE, 11667) == 45


async def test_serta_local_memory_separate_from_m4_and_progress_equality_wins():
    coord = coordinator()
    ctrl = SertaMPRemoteController(coord)
    ctrl._wait = AsyncMock(return_value=False)
    callback = MagicMock()
    await ctrl.start_notify(callback)
    await ctrl.preset_memory(1)
    assert packets(coord) == [bytes.fromhex("e5fe177d0ca324b5")]
    assert ctrl.alarm_table_schedule_spec is None
    assert ctrl._memory_target == (15, 35)
    ctrl._memory_active = True
    data = bytearray(16)
    data[3:7] = bytes.fromhex("7d0ca324")
    data[13] = 3
    ctrl._parse_notification(data)
    assert coord.controller_state["app_memory_request"] == "inactive"
    assert coord.controller_state["app_memory_progress_visible"] is False
    callback.assert_any_call("back", 15.0)
    callback.assert_any_call("legs", 35.0)
    await ctrl.set_motor_position("back", 15)
    assert packets(coord)[-1] == pulse_frame(3197, 0x8000)
    ctrl.on_disconnect()
    assert all(handle.cancelled() for handle in ctrl._setters)


ACTION_RECEIPTS = json.loads(
    (Path(__file__).parent / "fixtures/cluster033/action_receipts.json").read_text()
)["receipts"]


@pytest.mark.parametrize("receipt", ACTION_RECEIPTS, ids=lambda r: r["id"])
async def test_source_action_receipts(receipt):
    """Profile gates and bytes are checked against an independent source fixture."""
    ctrl, coord = await ready(receipt["app"], receipt["layout"])
    await ctrl._run_action(receipt["key"])
    assert [p.hex() for p in packets(coord)] == receipt["attempted_frames_300ms_adapter"]


async def test_old_session_writer_waiting_for_ble_lane_cannot_write_to_new_client():
    ctrl, coord = await ready("omazz_adjusto_iii")
    await ctrl.ble_lock.acquire()
    pending = asyncio.create_task(ctrl.write_command(control_frame(1)))
    await asyncio.sleep(0)
    ctrl.on_disconnect()
    coord.client = coordinator().client
    await ctrl.start_notify()
    ctrl.ble_lock.release()
    with pytest.raises(ConnectionError, match="expired session"):
        await pending
    assert packets(coord) == []


async def test_mx_periodic_queries_use_existing_diagnostic_hook_with_first5_then30_cadence():
    ctrl, coord = await ready("qplus_app", "MX")
    loop = asyncio.get_running_loop()
    base = loop.time()
    ctrl._next_query = base + 5
    with patch.object(loop, "time", return_value=base + 4.99):
        await ctrl.async_refresh_diagnostics()
    assert packets(coord) == []
    with patch.object(loop, "time", return_value=base + 5):
        await ctrl.async_refresh_diagnostics()
    assert packets(coord) == [b"\0\xb0"]
    with patch.object(loop, "time", return_value=base + 34.99):
        await ctrl.async_refresh_diagnostics()
    assert packets(coord) == [b"\0\xb0"]
    with patch.object(loop, "time", return_value=base + 35):
        await ctrl.async_refresh_diagnostics()
    assert packets(coord) == [b"\0\xb0"] * 2
    ctrl.on_disconnect()
    await ctrl.async_refresh_diagnostics()
    assert packets(coord) == [b"\0\xb0"] * 2


async def test_serta_angle_edit_holds_locally_then_sends_one_bounded_target_on_release():
    coord = coordinator()
    ctrl = SertaMPRemoteController(coord)
    ctrl._wait = AsyncMock(return_value=False)
    await ctrl.start_notify()
    ctrl._angles = 59, 0
    await ctrl.hold_control("head_target_up", 401)
    assert packets(coord) == [pulse_frame(HEAD_TABLE[60], 0x8000)]
    assert [x.args[0] for x in ctrl._wait.await_args_list] == [200, 200, 1]
    ctrl.on_disconnect()


@pytest.mark.parametrize(
    "app,expected,waits",
    [
        ("tempur_curve", ["e780017e091b0a0000eb"], [2000, 500]),
        ("qplus_app", ["e5fe160000000006"], []),
        ("omazz_adjusto_iii", [], []),
        ("ergomotion_app", [], []),
        ("serta_mp_remote", [], []),
    ],
)
async def test_initialization_source_frames_and_gates(app, expected, waits):
    coord = coordinator()
    ctrl = AppController(coord, app_profile(app))
    ctrl._wait = AsyncMock(return_value=False)
    with patch("custom_components.adjustable_bed.beds.cluster033.dt_util.now", return_value=NOW):
        await ctrl.start_notify()
    assert [p.hex() for p in packets(coord)] == expected
    assert [c.args[0] for c in ctrl._wait.await_args_list] == waits


@pytest.mark.parametrize(
    "app",
    [
        "tempur_curve",
        "omazz_adjusto_iii",
        "ergomotion_app",
        "row_control",
        "ergo_slim",
        "tempur_au",
    ],
)
async def test_clock_uses_exact_local_calendar_fields(app):
    ctrl, coord = await ready(app)
    ctrl._wait.reset_mock()
    with patch("custom_components.adjustable_bed.beds.cluster033.dt_util.now", return_value=NOW):
        await ctrl.sync_clock()
    assert packets(coord) == [bytes.fromhex("e780017e091b0a0000eb")]
    ctrl._wait.assert_awaited_once_with(500)


@pytest.mark.parametrize(
    "app,count,gap",
    [
        ("tempur_curve", 2, 400),
        ("qplus_app", 4, 200),
        ("row_control", 2, 400),
        ("ergo_slim", 4, 200),
        ("tempur_au", 2, 400),
    ],
)
async def test_alarm_dismissal_source_count_and_gap(app, count, gap):
    ctrl, coord = await ready(app)
    await ctrl.stop_wake_routine()
    assert packets(coord) == [bytes.fromhex("e180049a")] * count
    assert [c.args[0] for c in ctrl._wait.await_args_list] == [gap] * count


@pytest.mark.parametrize(
    "app,prefix,status_offset,flag_offset",
    [
        ("ergomotion_app", 0xF1, 14, None),
        ("ergomotion_app", 0xF4, 15, None),
        ("ergo_slim", 0xF1, 14, None),
        ("ergo_slim", 0xF4, 15, None),
        ("tempur_curve", 0, 15, 14),
        ("row_control", 0, 15, 14),
        ("tempur_au", 0, 15, 14),
    ],
)
def test_parser_branch_vector_cases(app, prefix, status_offset, flag_offset):
    coord = coordinator()
    ctrl = AppController(coord, app_profile(app))
    data = bytearray(19)
    data[0], data[status_offset] = prefix, 255
    ctrl._parse_notification(data)
    assert coord.controller_state["app_timer_status"] == -1
    data[status_offset] = 2
    ctrl._parse_notification(data)
    assert coord.controller_state["app_timer_status"] == 2
    if flag_offset is not None:
        data[flag_offset] = 32
        data[status_offset] = 3
        ctrl._parse_notification(data)
        assert coord.controller_state["app_timer_status"] == 2
    ctrl._parse_notification(None)
    assert coord.controller_state["app_timer_status"] == 2


def test_absolute_java_date_milliseconds_are_chosen_before_delta_division():
    value = replace(
        schedule(),
        reference_time=NOW.replace(microsecond=999),
        one_time=(OneTimeAlarmRecord(enabled=True, hour=10, minute=1),),
    )
    # Java Date stores now at 10:00:00.000, so the derived interval is 60s.
    assert app_profile("tempur_curve").alarm.encode(value)[1][3:7] == bytes((0, 1, 0, 0))


@pytest.mark.parametrize("slot,head,foot", [(1, 15, 35), (2, 15, 35), (3, 15, 35), (4, 15, 0)])
async def test_serta_four_local_memory_defaults_and_configuration_are_not_physical_saves(
    slot, head, foot
):
    coord = coordinator()
    ctrl = SertaMPRemoteController(coord)
    ctrl._wait = AsyncMock(return_value=False)
    await ctrl.start_notify()
    try:
        await ctrl.preset_memory(slot)
        assert packets(coord) == [pulse_frame(HEAD_TABLE[head], FOOT_TABLE[foot])]
        assert not ctrl.supports_memory_programming
        assert ctrl.motor_max_angles == {"back": 60.0, "legs": 45.0}
    finally:
        ctrl.on_disconnect()
    with pytest.raises(ValueError):
        SertaMPRemoteController(coord, memories=((61, 0),) * 4)


@pytest.mark.parametrize("app", APPS)
def test_unavailable_layout_control_is_refused_before_any_wire(app):
    coord = coordinator()
    ctrl = AppController(coord, app_profile(app))
    assert not ctrl.controller_button_available("not_in_this_layout")
    with pytest.raises(ValueError):
        ctrl.validate_hold_control("not_in_this_layout", 1000)
    assert packets(coord) == []


@pytest.mark.parametrize("flags,accepted", [(0, True), (1, True), (2, False), (3, False)])
def test_qplus_19byte_flags_have_no_invented_both_side_override(flags, accepted):
    coord = coordinator()
    ctrl = AppController(coord, app_profile("qplus_app"))
    data = bytearray(19)
    data[15], data[16] = 3, flags
    ctrl._parse_notification(data)
    assert coord.controller_state == ({"app_timer_status": 3} if accepted else {})


@pytest.mark.parametrize(
    "duration,expected_masks",
    [
        (100, [0x8001000, 0, 0, 0, 0]),
        (700, [0x8001000] * 3 + [0x8001000, 0, 0x8001000, 0, 0x8001000, 0, 0x8001000, 0]),
    ],
)
async def test_ergomotion_held_down_zeros_keep_original_offsets_and_early_release(
    duration, expected_masks
):
    ctrl, coord = await ready("ergomotion_app", "B2")
    await ctrl.hold_control("reset", duration)
    assert packets(coord) == [control_frame(mask) for mask in expected_masks]


async def test_pulse_write_failure_still_attempts_protocol_release():
    from bleak.exc import BleakError

    ctrl, coord = await ready("tempur_curve")
    coord.client.write_gatt_char.side_effect = [BleakError("failed write callback"), None]
    with pytest.raises(BleakError):
        await ctrl._run_action("massage_timer")
    assert packets(coord) == [control_frame(0x200), control_frame(0)]


async def test_diagnostic_callback_change_does_not_repeat_session_initialization_or_subscription():
    ctrl, coord = await ready("qplus_app", "MX")
    callback = MagicMock()
    await ctrl.start_notify(callback)
    assert coord.client.start_notify.await_count == 1
    assert ctrl._notify_callback is callback
    assert packets(coord) == []
