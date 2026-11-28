"""Current product byte paths, bounded notifications, gates and session cleanup."""

import asyncio
import json
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.adjustable_bed.alarm import AlarmRequest
from custom_components.adjustable_bed.beds.thrivesleep import controller as bed
from custom_components.adjustable_bed.beds.thrivesleep.receive import Receiver, decode
from custom_components.adjustable_bed.beds.thrivesleep.services import Request, execute, validate
from custom_components.adjustable_bed.codec import richmat as codec
from custom_components.adjustable_bed.profiles.thrivesleep import ACTIONS, PROFILES, ROUTES, THERAPY
from tests.test_casper_base import char, frames
from tests.test_controller_contract import _FactoryCoordinator
from tests.test_thrivesleep_vectors import FIXTURES, VECTORS


@pytest.fixture
def clock(monkeypatch):
    now = [0.0]
    real = asyncio.sleep

    async def pause(seconds, *args, **kwargs):
        now[0] += seconds
        await real(0)

    monkeypatch.setattr(bed, "monotonic", lambda: now[0])
    monkeypatch.setattr(bed.asyncio, "sleep", pause)
    return now


def make(product="level5", route="w1", properties=("write", "write-without-response")):
    c = _FactoryCoordinator()
    c.entry.data[bed.CONF_PROTOCOL_VARIANT] = product
    c.handle_controller_state_updates = MagicMock()
    c.record_command_trace = MagicMock()
    c.client = MagicMock(is_connected=True)
    c.client.start_notify = AsyncMock()
    c.client.stop_notify = AsyncMock()
    c.client.write_gatt_char = AsyncMock()
    gatt = json.loads((FIXTURES / "gatt.json").read_text())[ROUTES.index(route)]
    c.client.services = [
        SimpleNamespace(
            uuid=gatt["service"].upper(),
            characteristics=[
                char(gatt["write"].upper(), *properties),
                char("first-notify", "notify"),
                char(gatt["declared_notify"], "notify"),
            ],
        )
    ]
    ctrl = bed.ThriveSleepController(c, product=product)
    c.controller = ctrl
    return ctrl, c


def notify(c, packet):
    call = c.client.start_notify.call_args
    call.args[1](call.args[0], bytearray.fromhex(packet))


def capabilities(c):
    notify(c, "6e09010078")
    notify(c, "6e0e00037f")


@pytest.mark.parametrize("route", ROUTES)
@pytest.mark.parametrize("product", PROFILES)
async def test_current_profiles_every_generic_literal_and_release(clock, route, product):
    ctrl, c = make(product, route)
    await ctrl.start_notify()
    assert c.client.start_notify.call_args.args[0].uuid == "first-notify"
    raw = route == "n1"
    assert frames(c)[:3] == (
        ["00", "01", "01"] if raw else ["6e02010071", "6e08010178", "6e0a000179"]
    )
    assert len(frames(c)) == (5 if product == "level5" else 4)
    capabilities(c)
    for key in ctrl.profile.actions:
        for alternate, code in ((False, ACTIONS[key].code), (True, ACTIONS[key].alternate)):
            if code is None:
                continue
            c.client.write_gatt_char.reset_mock()
            expected = (
                bytes((code,)).hex()
                if raw
                else next(
                    v["expected_bytes"]
                    for v in VECTORS
                    if v["inputs"].get("builder") == "generic"
                    and v["inputs"]["opcode"] == code
                    and v["inputs"].get("nordic", False) == raw
                    and v["inputs"].get("side", 0) == 0
                )
            )
            if key in ctrl.held_control_options:
                await ctrl.hold_control(key, 250)
                assert frames(c) == [expected] * 2 + ["6e" if raw else "6e01006edd"]
            else:
                await ctrl.action(key, alternate=alternate)
                assert frames(c) == [expected]
    assert all(call.kwargs["response"] is False for call in c.client.write_gatt_char.call_args_list)
    ctrl.on_disconnect()


@pytest.mark.parametrize("first,last", [("w1", "n1"), ("n1", "w1"), ("w1", "w4")])
async def test_mixed_services_fail_before_any_subscription_or_write(clock, first, last):
    ctrl, c = make(route=first)
    other, other_c = make(route=last)
    c.client.services += other_c.client.services
    with pytest.raises(ValueError, match="exactly one"):
        await ctrl.start_notify()
    c.client.start_notify.assert_not_awaited()
    assert frames(c) == []


async def test_gatt_property_response_and_actual_notification_handle(clock):
    ctrl, c = make(properties=("write-without-response",))
    with pytest.raises(ValueError, match="write property"):
        await ctrl.start_notify()
    assert frames(c) == []
    ctrl, c = make(properties=("write",))
    await ctrl.start_notify()
    assert all(call.kwargs["response"] for call in c.client.write_gatt_char.call_args_list)
    ctrl.on_disconnect()


@pytest.mark.parametrize(
    "row", json.loads((FIXTURES / "notification-vectors.json").read_text()), ids=lambda r: r["id"]
)
def test_frozen_current_notifications_and_checksum_rejection(row):
    value = bytes.fromhex(row["frame"])
    assert decode(value) == row["expected"]
    assert decode(value[:-1] + bytes((value[-1] ^ 1,))) == {}


async def test_fragments_coalescing_residual_and_stale_callback(clock):
    ctrl, c = make()
    await ctrl.start_notify()
    cb = c.client.start_notify.call_args.args[1]
    notify(c, "6e200d0603")
    assert not ctrl.sleep_name
    notify(c, "02004245442d31cf6e09010078")
    assert ctrl.sleep_name == "BED-1" and "clock" in ctrl.features
    await ctrl.read_positions()
    assert frames(c)[-1] == "6e2008060100009d"
    count = len(frames(c))
    await ctrl.read_positions()
    assert len(frames(c)) == count
    ctrl.on_disconnect()
    cb(char("first-notify", "notify"), bytearray.fromhex("6e0e00037f"))
    assert ctrl.features == set() and not ctrl.sleep_name
    receiver = Receiver()
    receiver.feed(bytes.fromhex("6e200d"))
    receiver.expiry._run()
    assert receiver.pending == b""
    receiver.close()


async def test_reply_gates_rgb_timers_therapy_and_snore(clock):
    ctrl, c = make("eco_comfort", "n1")
    await ctrl.start_notify()
    c.client.write_gatt_char.reset_mock()
    for request in (
        Request("light_rgb", (1, 2, 3)),
        Request("query_alarms"),
        Request("query_snore"),
    ):
        with pytest.raises(ValueError):
            validate(ctrl, request)
    assert frames(c) == []
    capabilities(c)
    await ctrl.light_rgb((1, 2, 3))
    await ctrl.light_timer(0)
    await ctrl.light_timer(300)
    await ctrl.light_timer(900)
    await ctrl.therapy("close")
    for option in THERAPY:
        await ctrl.therapy(option)
    assert frames(c)[:3] == ["6e0cff017a6e0d020380", "6e0bffff77", "6e0b012ca6"]
    for number in (-1, 901, True):
        with pytest.raises(ValueError):
            await ctrl.light_timer(number)
    for rgb in ((1, 2, 256), (1.5, 2, 3), (True, 2, 3)):
        with pytest.raises(ValueError):
            await ctrl.light_rgb(rgb)
    with pytest.raises(ValueError):
        await ctrl.snore(True)
    ctrl.on_disconnect()
    ctrl, c = make()
    await ctrl.start_notify()
    with pytest.raises(ValueError):
        await ctrl.snore(True)
    notify(c, "6e200d060302004245442d31cf")
    await ctrl.snore(True)
    assert frames(c)[-1] == "6e20090601010001a0"
    notify(c, "6e20090601020001a1")
    ctrl.on_disconnect()


def alarm(**kwargs):
    return AlarmRequest(
        enabled=True,
        hour=7,
        minute=30,
        slot=1,
        wake_action="zero_g",
        weekdays=(0, 1, 2, 3, 4),
        reference_time=datetime.now(),
    ).__replace__(**kwargs)


async def test_native_repeat_alarm_modes_fields_list_and_update(clock):
    ctrl, c = make()
    await ctrl.start_notify()
    with pytest.raises(ValueError):
        await ctrl.configure_alarm(alarm())
    capabilities(c)
    c.client.write_gatt_char.reset_mock()
    await ctrl.configure_alarm(alarm())
    assert frames(c) == ["6e200d0501010100071e45f906"]
    await ctrl.configure_alarm(
        alarm(slot=7, hour=0, minute=0, wake_action="anti_snore", weekdays=())
    )
    assert frames(c)[-1] == "6e200d050101070000004601f0"
    await ctrl.query_alarms()
    notify(c, "6e200d0501020100071e45f907")
    notify(c, "6e200d0501020100071e45f907")
    assert len(ctrl.alarms) == 1
    updated = codec.record_20_len(5, 1, 3, (1, 0, 8, 15, 69, 1)).hex()
    notify(c, updated)
    assert ctrl.alarms[0]["hour"] == 8
    notify(c, codec.record_20_len(5, 1, 3, (7, 0, 8, 15, 69, 1)).hex())
    assert len(ctrl.alarms) == 1
    await execute(ctrl, Request("delete_alarm", alarm_id=1))
    assert ctrl.alarms == [] and frames(c)[-1] == "6e2008050201019f"
    for request in (
        alarm(slot=0),
        alarm(slot=True),
        alarm(wake_action="none"),
        alarm(weekdays=(7,)),
    ):
        with pytest.raises(ValueError):
            ctrl.validate_alarm(request)
    ctrl.on_disconnect()


async def test_cancellation_stops_only_the_captured_session(clock):
    ctrl, c = make()
    await ctrl.start_notify()
    original = c.client.write_gatt_char

    async def cancel_on_motion(*args, **kwargs):
        await original(*args, **kwargs)
        if args[1] == bytes.fromhex("6e01002493"):
            c.cancel_command.set()

    c.client.write_gatt_char = AsyncMock(side_effect=cancel_on_motion)
    with pytest.raises(asyncio.CancelledError):
        await ctrl.hold_control("head_up", 1000)
    assert frames(c)[-1] == "6e01006edd"
    old = ctrl._link
    c.client = MagicMock(is_connected=True)
    with pytest.raises(ConnectionError):
        await ctrl._send(old, b"test", asyncio.Event())
    c.client.write_gatt_char.assert_not_called()
    ctrl.on_disconnect()


async def test_logical_side_rejection_and_product_mutation(clock):
    ctrl, c = make()
    await ctrl.start_notify()
    c.client.write_gatt_char.reset_mock()
    with ctrl.side_scope("right"), pytest.raises(ConnectionError):
        await ctrl.preset_memory(1)
    c.entry.data[bed.CONF_PROTOCOL_VARIANT] = "cool_flow"
    with pytest.raises(ConnectionError):
        await ctrl.program_memory(1)
    assert frames(c) == []
    ctrl.on_disconnect()


@pytest.mark.parametrize("name", ("QRRM123", "xCOOL123", "MPE_123", "x209A123", "BED-1"))
def test_current_scan_keywords_are_shared_case_sensitive_advertisement_hints(name):
    from custom_components.adjustable_bed.discovery_hints import first_pass
    from tests.test_bluetooth_matchers import _info

    info = _info(name, ())
    encoded = name.encode()
    info.raw = bytes((len(encoded) + 1, 9)) + encoded
    assert first_pass(info).name("thrivesleep")
    if name.lower() != name:
        assert not first_pass(_info(name.lower(), ())).name("thrivesleep")
    assert not first_pass(_info("HZRN", ())).name("thrivesleep")
    assert not first_pass(_info("Q3RN", ())).name("thrivesleep")


def test_current_fan_observation_is_not_claimed_as_ui_state():
    assert decode(bytes.fromhex("6e20090e01020003ab")) == {"fanGear": 3}


def test_first_travel_field_stays_diagnostic_without_an_axis_or_unit():
    frame = codec.record_20_len(1, 2, 2, (0, 1, 2))
    assert decode(frame) == {"firstTravel": 25.8}
    assert decode(codec.record_20_len(1, 2, 2, (0,))) == {}


async def test_subscription_replacement_drops_prior_stream_and_buffer(clock):
    ctrl, c = make()
    await ctrl.start_notify()
    old = c.client.start_notify.call_args.args[1]
    notify(c, "6e200d")
    await ctrl.start_notify()
    c.client.stop_notify.assert_awaited_once()
    assert ctrl._receiver.pending == b""
    old(char("first-notify", "notify"), bytearray.fromhex("6e09010078"))
    assert ctrl.features == set()
    ctrl.on_disconnect()
