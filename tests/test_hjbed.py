"""Accepted row121 artifact vectors and HA behavior; hardware is unverified."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from zoneinfo import ZoneInfo

import pytest

from custom_components.adjustable_bed.beds import hjbed as bed
from custom_components.adjustable_bed.hjbed_catalog import ACTIONS, MUSIC_ACTIONS, PRODUCTS
from custom_components.adjustable_bed.hjbed_protocol import (
    Alarm,
    add_alarm,
    clock,
    color,
    control_mode,
    delete_alarm,
    function,
    light_time,
    query_alarms,
    sync_time,
)
from custom_components.adjustable_bed.hjbed_receive import parse_frame
from custom_components.adjustable_bed.hjbed_requests import Request
from custom_components.adjustable_bed.hjbed_state import NonProgressFrame, State, Stream

FIXTURES = Path(__file__).parent / "fixtures"
RX = json.loads((FIXTURES / "hjbed_receive_vectors.json").read_text())
TX = json.loads((FIXTURES / "hjbed_command_vectors.json").read_text())


@pytest.fixture
def coordinator():
    c = MagicMock()
    c.address = "AA:BB:CC:DD:EE:21"
    c.capability_controller = None
    c.cancel_command = asyncio.Event()
    c.motor_pulse_count = 3
    c.motor_pulse_delay_ms = 999  # Not protocol evidence and must not affect cadence.
    c.client.is_connected = True
    c.client.write_gatt_char = AsyncMock()
    c.client.start_notify = AsyncMock()
    c.client.stop_notify = AsyncMock()
    c.controller_state = {}
    c.handle_controller_state_updates.side_effect = c.controller_state.update
    return c


def controller(coordinator, profile="hj_bedbjrn", single=False):
    # Profile spelling follows the compiled product ID rather than name heuristics.
    profile = next((k for k, p in PRODUCTS.items() if p.object == profile), profile)
    c = bed.HJBedController(coordinator, profile=profile)
    write = SimpleNamespace(uuid="write", properties=["write", "write-without-response"], handle=21)
    notify = SimpleNamespace(uuid="notify", properties=["notify"], handle=22)
    c._session = bed.Session(coordinator.client, write, notify, single, coordinator.address)
    return c


@pytest.fixture
def clocked(monkeypatch):
    clock_value = [0.0]

    async def delay(self, seconds, cancel):
        clock_value[0] += seconds
        return not cancel.is_set()

    async def sleep(seconds):
        clock_value[0] += seconds

    monkeypatch.setattr(bed, "monotonic", lambda: clock_value[0])
    monkeypatch.setattr(bed.HJBedController, "_delay", delay)
    monkeypatch.setattr(bed.asyncio, "sleep", sleep)
    return clock_value


@pytest.fixture
def instant(monkeypatch, clocked):
    delays = []

    async def delay(self, seconds, cancel):
        delays.append(seconds)
        clocked[0] += seconds
        return not cancel.is_set()

    monkeypatch.setattr(bed.HJBedController, "_delay", delay)
    return delays


def written(c):
    return [call.args[1].hex() for call in c.client.write_gatt_char.await_args_list]


@pytest.mark.parametrize("vector", RX, ids=[v["id"] for v in RX])
def test_receive_vectors(vector):
    events = parse_frame(bytes.fromhex(vector["inputs"]["frame"]))
    expected = (vector["expected_event"], vector.get("expected_payload"))
    assert expected in events


@pytest.mark.parametrize("vector", TX, ids=[v["id"] for v in TX])
def test_static_command_vectors(vector):
    action = ACTIONS[vector["detail_object"]]
    code = action.save_code if vector["id"].endswith("/save") else action.code
    for side, expected in vector["framed_by_side"].items():
        assert function(action.enum, code, int(side), False).hex() == expected
    assert function(action.enum, code, 0, True).hex() == vector["single_code"]


def test_variable_packet_vectors():
    assert query_alarms().hex() == "6e0820050100009c"
    assert control_mode(0).hex() == "6e09200b02010000a5"
    assert control_mode(2).hex() == "6e09200b02010002a7"
    assert control_mode().hex() == "6e08200b020000a3"
    assert clock(1440, 0x45) == (bytes.fromhex("6e05a00013"), bytes.fromhex("6e060545be"))
    assert clock(0, 0) == (bytes.fromhex("6e05000073"), bytes.fromhex("6e06000074"))
    assert light_time(900).hex() == "6e0b038400"
    assert light_time(0).hex() == "6e0bffff77"
    assert color((255, 128, 0)).hex() == "6e0cffff786e0d8000fb"
    a = Alarm(1, 0, 7, 30, 0x45, 0x81)
    assert add_alarm(a).hex() == "6e0d200501010100071e45818e"
    assert delete_alarm(1).hex() == "6e0820050201019f"
    imported = Alarm(2, 1, 8, 9, 0x45, 1, (11, 22))
    assert add_alarm(imported)[10:14] == bytes((0, 1, 11, 22))
    now = datetime.fromisoformat("2026-11-03T07:30:00+05:30")
    stamp, calendar = sync_time(now, now)
    assert stamp[6:10] == int(now.timestamp()).to_bytes(4, "big")
    assert stamp[-2] == 5
    assert calendar[6:-1] == bytes((56, 11, 3, 7, 30, 0))


@pytest.mark.parametrize("profile", PRODUCTS)
def test_profile_surfaces(coordinator, profile):
    c = controller(coordinator, profile)
    assert (
        len(c.product.motor) + len(c.product.massage) + len(c.product.preset) + len(c.product.alarm)
        >= 2
    )
    # Every declared hold must execute an actual selected detail, including sofa travel.
    for spec in c.motor_control_specs:
        assert spec.hold.stop_scope == "side"
        assert spec.hold.up_control in c.held_control_options
        assert spec.hold.down_control in c.held_control_options
    for spec in c.controller_button_specs:
        if spec.hold:
            assert spec.hold.control in c.held_control_options
    assert not any(ACTIONS[d].kind == "music" for d in c.product.massage)


def test_exact_product_inventory():
    assert len(PRODUCTS) == 43
    assert sum(p.current for p in PRODUCTS.values()) == 19
    assert (
        sum(len(p.motor) + len(p.massage) + len(p.preset) + len(p.alarm) for p in PRODUCTS.values())
        == 724
    )
    assert len(ACTIONS) == 70
    assert len(MUSIC_ACTIONS) == 8
    assert {p.object for p in PRODUCTS.values()}.isdisjoint({"98fdf1", "98fe51", "990db1"})


async def test_motor_refresh_release_and_fast_tap(coordinator, instant):
    c = controller(coordinator, "990871")
    await c.execute_action("974261")
    assert written(coordinator) == ["6e01002493"] * 3 + ["6e01006edd"]
    assert instant == pytest.approx([0.1] * 3)
    coordinator.client.write_gatt_char.reset_mock()
    instant.clear()
    # A duration shorter than the first 100 ms tick sends neither movement nor STOP.
    await c.hold_control("hjbed_head_up", 50)
    assert written(coordinator) == []


async def test_preset_save_and_no_release(coordinator, instant):
    c = controller(coordinator, "990871")
    await c.execute_action("974e61")
    assert written(coordinator) == ["6e01002e9d"] * 3
    coordinator.client.write_gatt_char.reset_mock()
    instant.clear()
    await c.execute_action("974e61", save=True)
    assert written(coordinator) == ["6e01002b9a"]
    assert instant == [3]


@pytest.mark.parametrize("detail,code,release", [("974261", 36, True), ("974e61", 46, False)])
async def test_one_pulse_accepts_late_timer_within_its_tick(
    coordinator, clocked, monkeypatch, detail, code, release
):
    coordinator.motor_pulse_count = 1
    c = controller(coordinator, "990871")

    async def late_timer(self, seconds, cancel):
        clocked[0] += seconds + 0.002
        return not cancel.is_set()

    monkeypatch.setattr(bed.HJBedController, "_delay", late_timer)
    await c.execute_action(detail)
    frames = [bytes.fromhex(frame) for frame in written(coordinator)]
    assert [frame[3] for frame in frames] == [code] + ([110] if release else [])
    assert clocked[0] == pytest.approx(0.202 if release else 0.102)


@pytest.mark.parametrize("pulse_count", [1, 3])
@pytest.mark.parametrize("action,code,release", [("motor", 36, True), ("preset", 46, False)])
async def test_both_finite_pulses_share_a_bounded_window(
    coordinator, clocked, monkeypatch, pulse_count, action, code, release
):
    coordinator.motor_pulse_count = pulse_count
    c = controller(coordinator, "dream_orange")
    writes = []

    async def late_timer(self, seconds, cancel):
        clocked[0] += seconds + 0.002
        return not cancel.is_set()

    async def record_write(_char, frame, **_kwargs):
        writes.append((frame[2], frame[3], clocked[0]))

    monkeypatch.setattr(bed.HJBedController, "_delay", late_timer)
    coordinator.client.write_gatt_char.side_effect = record_write
    both = c.bind_side("both")
    if action == "motor":
        await both.move_head_up()
    else:
        await both.preset_memory(1)
    movement = [(side, at) for side, command, at in writes if command == code]
    expected = (
        [0.0, 0.1]
        if action == "preset"  # This coupled product selects the short preset detail.
        else [0.102, 0.202]
        if pulse_count == 1
        else [0.102, 0.202, 0.302, 0.402]
    )
    assert [side for side, _ in movement] == [0, 1] * (len(expected) // 2)
    assert [at for _, at in movement] == pytest.approx(expected)
    assert [(side, command) for side, command, _ in writes if command != code] == (
        [(0, 110), (1, 110)] if release else []
    )


@pytest.mark.parametrize("late_at", ["timer", "pacing", "lock", "cancel", "duration"])
async def test_one_pulse_rejects_stale_or_cancelled_tick(
    coordinator, clocked, monkeypatch, late_at
):
    coordinator.motor_pulse_count = 1
    c = controller(coordinator, "990871")

    async def late_timer(self, seconds, cancel):
        clocked[0] += seconds + (0.101 if late_at == "timer" else 0.002)
        if late_at == "cancel":
            cancel.set()
        return not cancel.is_set()

    monkeypatch.setattr(bed.HJBedController, "_delay", late_timer)
    if late_at == "pacing":
        c._last_write = 0.15
    if late_at == "lock":

        class LateLock:
            async def __aenter__(self):
                clocked[0] += 0.1

            async def __aexit__(self, *_exc):
                pass

        monkeypatch.setattr(c, "_ble_lock", LateLock())
    if late_at == "duration":
        await c.hold_control("hjbed_head_up", 100)
    else:
        await c.execute_action("974261")
    assert written(coordinator) == []


async def test_sofa_reset_has_no_invented_stop(coordinator, instant):
    c = controller(coordinator, "990751")
    await c.execute_action("9753e1")
    assert written(coordinator) == ["6e0100e554"] * 3
    coordinator.client.write_gatt_char.reset_mock()
    await c.execute_action("975361")
    assert written(coordinator) == ["6e01003cab"]


async def test_motion_reset_is_short(coordinator, instant):
    c = controller(coordinator, "990871")
    await c.execute_action("974f61", motion=True)
    assert written(coordinator) == ["6e010031a0", "6e01006edd"]
    assert instant == []


async def test_cancel_releases_original_side(coordinator, instant):
    c = controller(coordinator, "990871")
    token = c._command_side.set("right")

    async def cancel(*args, **kwargs):
        coordinator.cancel_command.set()

    coordinator.client.write_gatt_char.side_effect = cancel
    try:
        await c.execute_action("974261")
    finally:
        c._command_side.reset(token)
    assert written(coordinator) == ["6e01012494", "6e01016ede"]


async def test_music_named_route_fixed_left(coordinator, instant):
    c = controller(coordinator, "990871")
    token = c._command_side.set("right")
    try:
        for action in MUSIC_ACTIONS:
            await c.execute_action(action.object)
    finally:
        c._command_side.reset(token)
    assert len(written(coordinator)) == 8
    assert all(bytes.fromhex(frame)[2] == 0 for frame in written(coordinator))


def test_gatt_iteration_precedence(coordinator):
    first_service, (first_uuid, _) = next(iter(bed.GATT.items()))
    nordic = "6e400001-b5a3-f393-e0a9-e50e24dcca9e"
    write = SimpleNamespace(uuid=first_uuid, properties=["write"], handle=1)
    # First notify is retained even though it is not the declared UUID.
    notify = SimpleNamespace(uuid="different-notify", properties=["notify"], handle=2)
    second = SimpleNamespace(uuid=bed.GATT[nordic][0], properties=["write", "notify"], handle=3)
    coordinator.client.services = [
        SimpleNamespace(uuid=first_service, characteristics=[write, notify]),
        SimpleNamespace(uuid=nordic, characteristics=[second]),
    ]
    assert bed.select_transport(coordinator.client) == (write, notify, True)
    coordinator.client.services.reverse()
    assert bed.select_transport(coordinator.client) == (second, second, False)
    second.properties = ["write-without-response", "indicate"]
    coordinator.client.services = [SimpleNamespace(uuid=nordic, characteristics=[second])]
    with pytest.raises(ValueError):
        bed.select_transport(coordinator.client)


def test_stream_error_order_remainder_recovery():
    events = []
    arm, cancel = MagicMock(), MagicMock()
    stream = Stream(lambda e, v: events.append((e, v)), arm, cancel)
    good = bytes.fromhex("6e200903010200019e")
    bad = bytes.fromhex("6e20070b0202a4")
    with pytest.raises(IndexError):
        stream.feed(good + bad + good + good[:4])
    assert events == [("deviceWhiteLedStatusEvent", True)]
    assert stream.buffer == list(good[:4])
    arm.assert_not_called()
    stream.feed(good[4:])
    assert events == [("deviceWhiteLedStatusEvent", True)] * 2
    assert stream.buffer == []
    with pytest.raises(IndexError):
        stream.feed(good + bytes.fromhex("6e4000"))
    assert len(events) == 2  # All complete frames were split before dispatch.
    assert stream.buffer == [0x6E, 0x40, 0]


def test_zero_length_safety_and_callback_effects():
    events = []
    stream = Stream(lambda e, v: events.append((e, v)), MagicMock(), MagicMock())
    with pytest.raises(NonProgressFrame):
        stream.feed(bytes.fromhex("6e200903010200019e6e2000"))
    assert not events and not stream.buffer

    def error(event, value):
        events.append((event, value))
        raise RuntimeError("listener failed after mutation")

    stream = Stream(error, MagicMock(), MagicMock())
    with pytest.raises(RuntimeError):
        stream.feed(bytes.fromhex("6e90b1e0006e200903010200019e6e20"))
    assert events == [("deviceMusicUsbStatusEvent", True)]
    assert stream.buffer == [0x6E, 0x20]


def test_alarm_consumer_equality_and_escalation():
    state = State()
    a = {"number": 1, "kind": 0, "hour": 7, "minute": 0, "code": 69, "repeat": 129, "data": []}
    b = dict(a, minute=1)
    state.accept("deviceRepeatAlarmListStatusEvent", a)
    state.accept("deviceRepeatAlarmListStatusEvent", a)
    state.accept("deviceRepeatAlarmListStatusEvent", b)
    assert state.alarms == [a, b]
    state.accept("deviceRepeatAlarmListEscalationStatusEvent", dict(b, hour=8))
    assert state.alarms == [dict(b, hour=8), b]
    state.accept("deviceRepeatAlarmListEscalationStatusEvent", dict(a, number=7))
    assert len(state.alarms) == 2


async def test_alarm_gates_slots_toggle_and_ack_persistence(coordinator, instant):
    c = controller(coordinator, "98ff11")
    request = Request("repeat", action="zero_gravity", when=time(7), alarm_id=1, weekdays=(0, 6))
    with pytest.raises(ValueError):
        c.validate_hjbed_request(request)
    c._event("deviceCharacteristicsSubscriptionClockEvent", None)
    await c.async_execute_hjbed_request(request)
    assert bytes.fromhex(written(coordinator)[0])[6] == 1
    c._state.alarms = [
        {"number": 2, "kind": 1, "hour": 8, "minute": 9, "code": 0, "repeat": 1, "data": [11, 22]}
    ]
    await c.async_execute_hjbed_request(Request("toggle", alarm_id=2, enabled=False))
    assert bytes.fromhex(written(coordinator)[-1])[10:14] == bytes((0, 0, 11, 22))
    single = controller(coordinator, "98fcd1")
    single._event("deviceCharacteristicsSubscriptionClockEvent", None)
    await single.async_execute_hjbed_request(Request("single", action="zero_gravity", when=time(7)))
    assert single.persisted_app_state["saved_alarm"] is None
    single._event("deviceAddAlarmSuccessEvent", None)
    assert single.persisted_app_state["saved_alarm"]["action"] == "zero_gravity"
    single._event("deviceCancelAlarmSuccessEvent", None)
    assert single.persisted_app_state["saved_alarm"] is None


async def test_late_notification_and_session_replacement(coordinator, instant):
    c = controller(coordinator, "990871")
    old = c._session
    coordinator.client = MagicMock()
    c._notification(old, old.notify, bytearray.fromhex("6e200903010200019e"))
    assert not c._state.values
    with pytest.raises(ConnectionError):
        await c.execute_action("974261")


def test_all_profile_bindings_match_frozen_source(coordinator):
    rows = json.loads((FIXTURES / "hjbed_profile_vectors.json").read_text())
    active = {p.object: p for p in PRODUCTS.values()}
    ignored = {"9736e1", "974561", "974ee1"}
    music = {a.object for a in MUSIC_ACTIONS}
    for row in rows:
        if row["disposition"] == "DEAD/UNUSED":
            assert row["object"] not in active
            continue
        p = active[row["object"]]
        assert (p.label, p.remote, p.current) == (
            row["selector"]["display_key"],
            row["selector"]["remote_code"],
            row["selector"]["current_dialog"],
        )
        for field, name in [
            ("off_24", "motor"),
            ("off_28", "massage"),
            ("off_2c", "preset"),
            ("off_30", "alarm"),
        ]:
            expected = tuple(
                d
                for d in row["groups"][field]
                if d not in ignored and not (field == "off_28" and d in music)
            )
            assert getattr(p, name) == expected
        assert (p.music, p.alarms, p.repeat, p.light, p.coupled, p.sofa) == tuple(
            row["flags"][key]
            for key in ("off_34", "off_38", "off_3c", "off_40", "off_44", "off_48")
        )


@pytest.mark.parametrize("profile", PRODUCTS)
async def test_every_selected_action_uses_its_source_gesture(coordinator, instant, profile):
    c = controller(coordinator, profile)
    expected = {
        r["detail"]: r for r in json.loads((FIXTURES / "hjbed_gesture_vectors.json").read_text())
    }
    for detail in dict.fromkeys((*c.product.motor, *c.product.massage, *c.product.preset)):
        row = expected[detail]
        coordinator.client.write_gatt_char.reset_mock()
        await c.execute_action(detail)
        count = 3 if row["sustain"] else 1
        frames = [function(ACTIONS[detail].enum, row["code"], 0, False).hex()] * count
        if row["release"]:
            frames.append("6e01006edd")
        assert written(coordinator) == frames
        if row["save"] is not None and detail in c.product.preset:
            coordinator.client.write_gatt_char.reset_mock()
            await c.execute_action(detail, save=True)
            assert written(coordinator) == [
                function(ACTIONS[detail].enum, row["save"], 0, False).hex()
            ]


async def test_cancelled_write_still_releases_if_attempted(coordinator, instant):
    c = controller(coordinator, "990871")

    async def interrupt(_char, frame, **_kwargs):
        if frame[3] == 36:
            raise asyncio.CancelledError

    coordinator.client.write_gatt_char.side_effect = interrupt
    with pytest.raises(asyncio.CancelledError):
        await c.execute_action("974261")
    assert written(coordinator) == ["6e01002493", "6e01006edd"]


async def test_no_stop_on_preset_cancel_and_release_button(coordinator, instant):
    c = controller(coordinator, "990871")

    async def cancel(*_args, **_kwargs):
        coordinator.cancel_command.set()

    coordinator.client.write_gatt_char.side_effect = cancel
    await c.execute_action("974e61")
    assert written(coordinator) == ["6e01002e9d"]
    release = next(spec for spec in c.controller_button_specs if spec.key == "hjbed_release")
    assert release.cancel_movement
    await release.press_fn(c)
    assert written(coordinator) == ["6e01002e9d"]


async def test_side_bound_action_and_both_control(coordinator, instant):
    c = controller(coordinator, "990871")
    spec = next(spec for spec in c.controller_button_specs if spec.key == "hjbed_motor_reset")
    await spec.press_fn(c.bind_side("right"))
    assert all(bytes.fromhex(f)[2] == 1 for f in written(coordinator))
    coordinator.client.write_gatt_char.reset_mock()
    await c.bind_side("both").stop_all()
    assert written(coordinator) == ["6e01006edd", "6e01016ede"]


def test_safety_and_valid_product_service_limits(coordinator):
    c = controller(coordinator, "98fcd1")
    c._state.features.update({"alarm", "light"})
    for seconds in (1800, 28800):
        c.validate_hjbed_request(Request("light_timeout", seconds=seconds))
    for seconds in (0, 900, 28801):
        with pytest.raises(ValueError):
            c.validate_hjbed_request(Request("light_timeout", seconds=seconds))
    with pytest.raises(ValueError):
        c.validate_hjbed_request(Request("repeat", action="zero_gravity", when=time(7)))
    c.validate_hjbed_request(Request("mode", mode="standard"))
    c._layout("Motion")
    with pytest.raises(ValueError):
        c.validate_hjbed_request(Request("mode", mode="standard"))
    no_flags = controller(coordinator, "990871")
    no_flags._state.features.update({"alarm", "light"})
    with pytest.raises(ValueError):
        no_flags.validate_hjbed_request(Request("light_color", rgb=(1, 2, 3)))


async def test_setup_choices_and_factory(hass, coordinator):
    from custom_components.adjustable_bed.app_profiles import (
        hidden_generic_fields,
        per_side_profile,
    )
    from custom_components.adjustable_bed.const import BED_TYPE_HJBED, CONF_MOTOR_COUNT
    from custom_components.adjustable_bed.controller_factory import create_controller
    from custom_components.adjustable_bed.detection import (
        APP_VARIANT_CHOICES,
        bed_type_choice,
        get_bed_type_options,
    )
    from custom_components.adjustable_bed.setup_questions import setup_profile
    from custom_components.adjustable_bed.validators import is_valid_variant_for_bed_type

    coordinator.hass = hass
    # One row asks the product; each product keeps its app entry.
    rows = {row["value"] for row in get_bed_type_options()}
    assert BED_TYPE_HJBED in rows
    assert not any(bed_type_choice(BED_TYPE_HJBED, profile) in rows for profile in PRODUCTS)
    profile_spec = setup_profile(BED_TYPE_HJBED)
    assert profile_spec is not None
    assert set(profile_spec.questions[0].options({})) == set(PRODUCTS)
    for profile in PRODUCTS:
        assert "HJBed" in APP_VARIANT_CHOICES[BED_TYPE_HJBED, profile]
        assert is_valid_variant_for_bed_type(BED_TYPE_HJBED, profile)
        assert CONF_MOTOR_COUNT in hidden_generic_fields(BED_TYPE_HJBED, profile)
        assert per_side_profile(BED_TYPE_HJBED, profile).variant_owned
        c = await create_controller(coordinator, BED_TYPE_HJBED, profile, None)
        assert isinstance(c, bed.HJBedController) and c.product_key == profile
    assert not is_valid_variant_for_bed_type(BED_TYPE_HJBED, "auto")


@pytest.mark.parametrize(
    "product,motion,queries",
    [
        ("98fcd1", False, True),
        ("98fcd1", True, False),
        ("98fd31", True, True),
        ("990871", False, False),
    ],
)
async def test_startup_source_order_and_response_policy(
    coordinator, monkeypatch, product, motion, queries
):
    c = controller(coordinator, product)
    c._motion = motion
    service, (uuid, _) = next(iter(bed.GATT.items()))
    write = SimpleNamespace(uuid=uuid, properties=["write", "write-without-response"], handle=1)
    notify = SimpleNamespace(uuid="first-notify", properties=["notify"], handle=2)
    coordinator.client.services = [SimpleNamespace(uuid=service, characteristics=[write, notify])]
    clock_value = [0.0]
    fake_loop = SimpleNamespace(time=lambda: clock_value[0])

    async def sleep(seconds):
        clock_value[0] += seconds

    monkeypatch.setattr(bed.asyncio, "get_running_loop", lambda: fake_loop)
    monkeypatch.setattr(bed, "monotonic", lambda: clock_value[0])
    monkeypatch.setattr(bed.asyncio, "sleep", sleep)
    await c.start_notify()
    frames = written(coordinator)
    assert frames[0] == "6e02010071"
    assert [bytes.fromhex(f)[4] for f in frames[1:3]] == [2, 3]
    menu = 4 if queries else 3
    if queries:
        assert frames[3] == "6e08200b020000a3"
    assert frames[menu:] == ["6e08010178", "6e0a000179", "6e15010185"]
    assert all(
        call.kwargs["response"] is False
        for call in coordinator.client.write_gatt_char.await_args_list
    )
    assert clock_value[0] == pytest.approx(0.9)


async def test_timer_lifecycle_and_feature_scope(coordinator):
    c = controller(coordinator, "990871")
    c._notification(c._session, c._session.notify, bytearray.fromhex("6e200903"))
    timer = c._timer
    assert timer is not None
    timer._run()
    assert c._stream.buffer == [] and c._timer is timer
    c._notification(c._session, c._session.notify, bytearray.fromhex("6e200903010200019e"))
    assert c._timer is None
    assert c._state.values["deviceWhiteLedStatusEvent"] is True
    await c.stop_notify()
    assert not c._stream.buffer


async def test_ha_service_preflights_all_targets(hass, coordinator, instant):
    from unittest.mock import patch

    from homeassistant.exceptions import ServiceValidationError

    from custom_components.adjustable_bed.const import DOMAIN
    from custom_components.adjustable_bed.hjbed_services import async_register_hjbed_services

    good = controller(coordinator, "98fcd1")
    good._state.features.add("light")
    coordinator.capability_controller = good
    other = MagicMock()
    other.capability_controller = controller(other, "990871")
    other.name = "Unsupported receiver"
    targets = [(coordinator, "both"), (other, "both")]
    async_register_hjbed_services(hass)
    with (
        patch(
            "custom_components.adjustable_bed.hjbed_services._resolve_sided_targets",
            return_value=(targets, []),
        ),
        pytest.raises(ServiceValidationError),
    ):
        await hass.services.async_call(
            DOMAIN,
            "hjbed",
            {"device_id": ["a", "b"], "operation": "light_color", "rgb_color": [1, 2, 3]},
            blocking=True,
        )
    coordinator.client.write_gatt_char.assert_not_awaited()


@pytest.mark.parametrize("keyword", ["QRRM", "COOL", "MPE_", "209A", "ZRA1"])
def test_discovery_uses_artifact_substrings_without_selecting_a_profile(keyword):
    from custom_components.adjustable_bed.const import BED_TYPE_HJBED
    from custom_components.adjustable_bed.detection import detect_bed_type_detailed

    advert = SimpleNamespace(
        name="prefix-" + keyword + "-suffix",
        address="AA:BB:CC:DD:EE:21",
        service_uuids=[],
        manufacturer_data={},
        service_data={},
    )
    result = detect_bed_type_detailed(advert)
    assert result.bed_type == BED_TYPE_HJBED or BED_TYPE_HJBED in result.ambiguous_types
    assert result.signals[-1] == "name:hjbed_app_candidate"
    assert not hasattr(result, "protocol_variant")
    if keyword == "ZRA1":
        advert.name = "prefix-zra1-suffix"
        result = detect_bed_type_detailed(advert)
        assert result.bed_type != BED_TYPE_HJBED and BED_TYPE_HJBED not in (
            result.ambiguous_types or []
        )
    manifest = json.loads(
        (FIXTURES.parents[1] / "custom_components/adjustable_bed/manifest.json").read_text()
    )
    # HA's indexed manifest requires a literal prefix. Service/manual discovery
    # still uses the full app substring rule exercised above.
    assert {"local_name": keyword + "*"} in manifest["bluetooth"]


@pytest.mark.parametrize(
    "selected, suggested", [("richmat", "bedtech"), ("bedtech", None), ("hjbed", None)]
)
def test_app_scan_hint_preserves_receiver_recommendations_and_explicit_selection(
    selected, suggested
):
    from custom_components.adjustable_bed.const import CONF_BED_TYPE, CONF_PROTOCOL_VARIANT
    from custom_components.adjustable_bed.profile_recommendations import recommend_profile

    advert = SimpleNamespace(
        address="AA:BB:CC:DD:EE:21",
        name="QRRM157738",
        service_uuids=["0000fee9-0000-1000-8000-00805f9b34fb"],
        manufacturer_data={19543: bytes.fromhex("54307651")},
        service_data={},
    )
    result = recommend_profile(
        {
            CONF_BED_TYPE: selected,
            CONF_PROTOCOL_VARIANT: "hj_bedbjrn" if selected == "hjbed" else "auto",
        },
        advert,
        {},
    )
    if suggested is None:
        assert result is None
    else:
        assert result is not None and result.suggested == suggested
        assert all(not choice.startswith("hjbed") for choice in result.choices)


def test_app_scan_hint_does_not_corroborate_a_shared_receiver_signature():
    from custom_components.adjustable_bed.const import CONF_BED_TYPE
    from custom_components.adjustable_bed.profile_recommendations import recommend_profile

    advert = SimpleNamespace(
        address="AA:BB:CC:DD:EE:21",
        name="prefix-QRRM-suffix",
        service_uuids=["0000fee9-0000-1000-8000-00805f9b34fb"],
        manufacturer_data={},
        service_data={},
    )
    assert recommend_profile({CONF_BED_TYPE: "octo"}, advert, {}) is None


async def test_short_gesture_holds_release_without_repeating(coordinator, instant):
    c = controller(coordinator, "990b71")
    await c.hold_control("hjbed_massage_mode_change", 2500)
    assert instant == [2.5]
    assert written(coordinator) == ["6e010048b7", "6e01006edd"]
    spec = next(s for s in c.controller_button_specs if s.key == "hjbed_massage_mode_change")
    assert spec.hold is not None and spec.hold.start_delay_ms == 0
    assert spec.hold.release_button_key == "hjbed_release"


async def test_release_invalidates_pending_hold_without_extra_wire_stop(coordinator, instant):
    from custom_components.adjustable_bed.button import ControllerActionButton
    from custom_components.adjustable_bed.command_scheduler import (
        CommandIntent,
        DeviceCommandScheduler,
    )

    c = controller(coordinator, "990871")
    scheduler = DeviceCommandScheduler("hjbed-release")
    admitted_before_release = scheduler.stop_epoch
    runtime = MagicMock()
    runtime.device_info = {}
    runtime.entity_unique_id.side_effect = lambda key: "bed_" + key

    async def stop():
        async def on_wire(_context):
            await c.stop_all()

        await scheduler.admit_stop(on_wire)

    runtime.async_stop_command = AsyncMock(side_effect=stop)
    spec = next(s for s in c.controller_button_specs if s.key == "hjbed_release")
    await ControllerActionButton(runtime, spec).async_press()
    assert scheduler.stop_epoch > admitted_before_release
    assert written(coordinator) == []
    runtime.async_execute_controller_command.assert_not_called()

    async def delayed_preflight_completed(_context):
        await c.execute_action("974261")

    await scheduler.execute(
        CommandIntent(delayed_preflight_completed), expected_stop_epoch=admitted_before_release
    )
    assert written(coordinator) == []
    # The release context cannot suppress a later explicit safety STOP.
    await c.stop_all()
    assert written(coordinator) == ["6e01006edd"]
    await scheduler.async_shutdown()


def test_disposition_ledger_covers_the_accepted_inventory():
    from hashlib import sha256

    ledger = json.loads((FIXTURES / "hjbed_ledger.json").read_text())
    items = ledger["items"]
    assert len(items) == len({row["id"] for row in items}) == 1510
    appended = {
        "command",
        "product binding",
        "receive rule",
        "feature domain",
        "state/timing/configuration",
    }
    candidate_ids = sorted(row["id"] for row in items if row["category"] not in appended)
    assert len(candidate_ids) == 582
    assert (
        sha256(json.dumps(candidate_ids, separators=(",", ":")).encode()).hexdigest()
        == "e587eefb8c5d679fe88d93e049e58f9264f30ad0fe156a3e7eda7cfe2726632f"
    )
    assert sum(row["category"] == "command" for row in items) == 99
    assert (
        sum(
            row["category"] == "product binding" and row["disposition"] == "IMPLEMENTED"
            for row in items
        )
        == 724
    )
    for row in items:
        assert row["disposition"] in {"IMPLEMENTED", "ALREADY_IMPLEMENTED", "EXCLUDED"}
        assert ledger["reasons"][row["reason_ref"]]
        assert row["evidence"]
        if row["disposition"] != "EXCLUDED":
            assert ledger["proofs"][row["proof_ref"]]
            for ref in ledger["proofs"][row["proof_ref"]]:
                assert (FIXTURES.parents[1] / ref.split(":", 1)[0]).is_file()


async def test_acknowledged_alarm_metadata_roundtrips_without_stale_ack_loss(
    coordinator, instant, monkeypatch
):
    now = datetime.fromisoformat("2026-11-03T12:00:00+01:00")
    monkeypatch.setattr(bed.dt_util, "now", lambda: now)
    c = controller(coordinator, "98fcd1")
    c._state.features.add("alarm")
    await c.async_execute_hjbed_request(Request("single", action="zero_gravity", when=time(7)))
    c._event("deviceAddAlarmSuccessEvent", None)
    saved = c.persisted_app_state
    row = saved["saved_alarm"]
    assert isinstance(row, dict)
    assert row["clock_datetime_ms"] == int(now.replace(hour=7).timestamp() * 1000)
    assert row["function_enum"] == "deviceFunctionItemZeroGravity"
    assert row["repeat_type"] is None
    restored = controller(coordinator, "98fcd1")
    restored.restore_persisted_app_state(saved)
    restored._event("deviceAddAlarmSuccessEvent", None)
    assert restored.persisted_app_state == saved
    restored._event("deviceCancelAlarmSuccessEvent", None)
    restored._event("deviceAddAlarmSuccessEvent", None)
    assert restored.persisted_app_state["saved_alarm"] is None


async def test_both_hold_refreshes_and_releases_each_attempted_side(coordinator, clocked):
    c = controller(coordinator, "dream_orange")
    movement = []

    async def release_after_four_writes(_char, frame, **_kwargs):
        if frame[3] == 36:
            movement.append((frame[2], clocked[0]))
            if len(movement) == 4:
                coordinator.cancel_command.set()

    coordinator.client.write_gatt_char.side_effect = release_after_four_writes
    await c.bind_side("both").hold_control("hjbed_head_up", 60000)
    assert [side for side, _ in movement] == [0, 1, 0, 1]
    assert [at for _, at in movement] == pytest.approx([0.1, 0.2, 0.3, 0.4])
    assert written(coordinator)[-2:] == ["6e01006edd", "6e01016ede"]


async def test_both_cleanup_attempts_right_even_if_left_release_fails(coordinator, clocked):
    c = controller(coordinator, "dream_orange")

    async def fail_left_stop(_char, frame, **_kwargs):
        if frame[2:4] == bytes((0, 110)):
            raise ConnectionError("left release failed")

    coordinator.client.write_gatt_char.side_effect = fail_left_stop
    with pytest.raises(ConnectionError, match="left release failed"):
        await c.bind_side("both").hold_control("hjbed_head_up", 400)
    assert written(coordinator)[-2:] == ["6e01006edd", "6e01016ede"]


@pytest.mark.parametrize("latency, cadence", [(0.04, 0.1), (0.16, 0.2)])
async def test_refresh_deadlines_do_not_accumulate_write_latency(
    coordinator, clocked, latency, cadence
):
    c = controller(coordinator, "990871")
    writes = []

    async def slow_write(_char, frame, **_kwargs):
        writes.append((frame[3], clocked[0]))
        clocked[0] += latency

    coordinator.client.write_gatt_char.side_effect = slow_write
    await c.hold_control("hjbed_head_up", 1000)
    movement = [at for code, at in writes if code == 36]
    assert movement[:4] == pytest.approx([0.1 + i * cadence for i in range(4)])
    assert all(at <= 1 + 1e-9 for at in movement)
    assert writes[-1][0] == 110
    assert writes[-1][1] <= 1 + max(0.1, latency) + 1e-9


async def test_query_and_delete_retire_only_the_source_alarm_records(coordinator, clocked):
    c = controller(coordinator, "98ff11")
    c._state.features.add("alarm")
    rows = [
        {"number": number, "kind": 0, "hour": 7, "minute": 0, "code": 69, "repeat": 1, "data": []}
        for number in range(1, 8)
    ]
    c._state.alarms = rows.copy()
    create = Request("repeat", action="zero_gravity", when=time(8))
    with pytest.raises(ValueError, match="occupied"):
        c.validate_hjbed_request(create)
    await c.async_execute_hjbed_request(Request("delete", alarm_id=7))
    assert c._state.alarms == rows[:6]
    assert coordinator.controller_state["hjbed_alarms"] == rows[:6]
    await c.async_execute_hjbed_request(create)
    assert bytes.fromhex(written(coordinator)[-1])[6] == 7

    # Same-number beans are distinct: delete removes the selected first full bean.
    changed = dict(rows[0], hour=8)
    c._state.alarms = [rows[0], changed]
    await c.async_execute_hjbed_request(Request("delete", alarm_id=1))
    assert c._state.alarms == [changed]

    async def query_reply(_char, frame, **_kwargs):
        if frame == query_alarms():
            assert c._state.alarms == []
            assert coordinator.controller_state["hjbed_alarms"] == []
            c._event("deviceRepeatAlarmListStatusEvent", rows[1])

    coordinator.client.write_gatt_char.side_effect = query_reply
    await c.async_execute_hjbed_request(Request("query"))
    assert c._state.alarms == [rows[1]]


@pytest.mark.parametrize(
    "date, hour, minutes",
    [
        ("2026-10-25T01:30:00", 3, 180),
        ("2026-03-29T01:30:00", 3, 60),
        ("2026-10-25T01:30:00", 1, 1440),
    ],
)
async def test_single_alarm_epoch_minutes_across_dst(
    coordinator, clocked, monkeypatch, date, hour, minutes
):
    now = datetime.fromisoformat(date).replace(tzinfo=ZoneInfo("Europe/Oslo"))
    monkeypatch.setattr(bed.dt_util, "now", lambda: now)
    c = controller(coordinator, "98fcd1")
    c._state.features.add("alarm")
    await c.async_execute_hjbed_request(
        Request("single", action="zero_gravity", when=time(hour, 30))
    )
    assert written(coordinator) == [frame.hex() for frame in clock(minutes, 69)]


async def test_repeat_allocation_requires_known_free_slot_and_reserves_attempt(
    coordinator, clocked
):
    c = controller(coordinator, "98ff11")
    c._state.features.add("alarm")
    auto = Request("repeat", action="zero_gravity", when=time(7))
    with pytest.raises(ValueError, match="explicit alarm_id"):
        await c.async_execute_hjbed_request(auto)
    assert written(coordinator) == []
    await c.async_execute_hjbed_request(
        Request("repeat", action="zero_gravity", when=time(7), alarm_id=1)
    )
    with pytest.raises(ValueError, match="explicit alarm_id"):
        await c.async_execute_hjbed_request(auto)
    await c.async_execute_hjbed_request(Request("delete", alarm_id=2))
    assert c._available_alarm_slots() == [2]
    await c.async_execute_hjbed_request(auto)
    assert bytes.fromhex(written(coordinator)[-1])[6] == 2
    assert coordinator.controller_state["hjbed_available_alarm_slots"] == []
    count = len(written(coordinator))
    with pytest.raises(ValueError, match="explicit alarm_id"):
        await c.async_execute_hjbed_request(auto)
    assert len(written(coordinator)) == count  # No notification is needed to reserve it.


async def test_alarm_free_slots_expire_on_query_notification_and_replacement(coordinator, clocked):
    c = controller(coordinator, "98ff11")
    c._state.features.add("alarm")
    await c.async_execute_hjbed_request(Request("delete", alarm_id=3))
    c._event("deviceRepeatAlarmListStatusEvent", {"number": 3})
    assert c._available_alarm_slots() == []
    await c.async_execute_hjbed_request(Request("delete", alarm_id=4))
    coordinator.capability_controller = c
    replacement = controller(coordinator, "98ff11")
    assert replacement._available_alarm_slots() == []
    await c.async_execute_hjbed_request(Request("query"))
    assert c._available_alarm_slots() == []
    await c.async_execute_hjbed_request(Request("delete", alarm_id=5))
    await c.stop_notify()
    assert c._available_alarm_slots() == []


async def test_failed_alarm_write_does_not_reallocate_an_uncertain_slot(coordinator, clocked):
    c = controller(coordinator, "98ff11")
    c._state.features.add("alarm")
    await c.async_execute_hjbed_request(Request("delete", alarm_id=6))
    coordinator.client.write_gatt_char.side_effect = ConnectionError("write uncertain")
    auto = Request("repeat", action="zero_gravity", when=time(7))
    with pytest.raises(ConnectionError, match="uncertain"):
        await c.async_execute_hjbed_request(auto)
    with pytest.raises(ValueError, match="explicit alarm_id"):
        await c.async_execute_hjbed_request(auto)


async def test_alarm_reply_during_pacing_revokes_implicit_allocation(
    coordinator, clocked, monkeypatch
):
    c = controller(coordinator, "98ff11")
    c._state.features.add("alarm")
    await c.async_execute_hjbed_request(Request("query"))
    await c.async_execute_hjbed_request(Request("delete", alarm_id=1))
    assert c._available_alarm_slots() == [1]
    frame = next(
        v["inputs"]["frame"] for v in RX if v["inputs"]["frame"] == "6e200d0501020100071e2efff6"
    )

    async def occupied_reply(seconds):
        clocked[0] += seconds
        c._notification(c._session, c._session.notify, bytearray.fromhex(frame))

    monkeypatch.setattr(bed.asyncio, "sleep", occupied_reply)
    coordinator.client.write_gatt_char.reset_mock()
    with pytest.raises(ValueError, match="no longer free"):
        await c.async_execute_hjbed_request(Request("repeat", action="zero_gravity", when=time(9)))
    assert c._available_alarm_slots() == []
    assert written(coordinator) == []
    # An explicit slot remains an intentional edit, including when occupied.
    await c.async_execute_hjbed_request(
        Request("repeat", action="zero_gravity", when=time(9), alarm_id=1)
    )
    assert written(coordinator) == ["6e0d20050101010009004501f2"]


@pytest.mark.parametrize("profile", ["990871", "98fcd1"])
async def test_local_layout_select_uses_replacement_controller(coordinator, instant, profile):
    from homeassistant.exceptions import ServiceValidationError

    from custom_components.adjustable_bed.select import AdjustableBedControllerSelect

    coordinator.device_info = {}
    coordinator.entity_side = None
    coordinator.entity_unique_id.side_effect = lambda key: "bed_" + key
    old = controller(coordinator, profile)
    coordinator.capability_controller = old
    entity = AdjustableBedControllerSelect(coordinator, old.controller_select_specs[0])
    live = controller(coordinator, profile)
    coordinator.capability_controller = live
    await entity.async_select_option("Motion")
    assert not old._motion and live._motion
    assert entity.current_option == "Motion"
    coordinator.async_execute_controller_command.assert_not_called()
    if profile == "990871":
        await live.execute_action("974f61")
        assert written(coordinator) == ["6e010031a0", "6e01006edd"]
    else:
        with pytest.raises(ValueError, match="Normal layout"):
            live.validate_hjbed_request(Request("mode", mode="standard"))
    coordinator.capability_controller = None
    with pytest.raises(ServiceValidationError, match="local option"):
        await entity.async_select_option("Normal")
    assert live._motion
