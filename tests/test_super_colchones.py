"""Frozen source literals exercised through the shipped app controller and parser."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.const import STATE_UNKNOWN

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.beds.super_colchones import controller as bed
from custom_components.adjustable_bed.beds.super_colchones.receive import Receiver, decode
from custom_components.adjustable_bed.codec import richmat as codec
from custom_components.adjustable_bed.discovery_hints.super_colchones import HINTS
from custom_components.adjustable_bed.profiles.super_colchones import ACTIONS
from custom_components.adjustable_bed.state_keys import MASSAGE_TIMER_MINUTES
from tests.error_helpers import raises_key
from tests.super_colchones_vectors import FIXTURES, WIRE
from tests.test_casper_base import char, frames
from tests.test_controller_contract import _FactoryCoordinator

GATT = json.loads((FIXTURES / "gatt.json").read_text())
INBOUND = json.loads((FIXTURES / "inbound.json").read_text())


def make(route=0, product="afeg350", properties=("write", "write-without-response")):
    c = _FactoryCoordinator()
    c.entry.data[const.CONF_PROTOCOL_VARIANT] = product
    c.handle_controller_state_updates = MagicMock()
    c.record_command_trace = MagicMock()
    c.client = MagicMock(is_connected=True)
    c.client.start_notify = AsyncMock()
    c.client.stop_notify = AsyncMock()
    c.client.write_gatt_char = AsyncMock()
    gatt = GATT[route]
    c.client.services = [SimpleNamespace(uuid=gatt["service"].upper(), characteristics=[char(gatt["write"].upper(), *properties), char("first-notify", "notify"), char(gatt["notify_candidate"], "notify")])]
    ctrl = bed.SuperColchonesController(c)
    c.controller = ctrl
    return ctrl, c


@pytest.fixture
def clock(monkeypatch):
    now = [0.0]
    real = asyncio.sleep

    async def pause(seconds, cancel):
        now[0] += seconds
        await real(0)
        if cancel.is_set():
            raise asyncio.CancelledError

    monkeypatch.setattr(bed, "monotonic", lambda: now[0])
    monkeypatch.setattr(bed, "_pause", pause)
    return now


def notify(c, packet):
    call = c.client.start_notify.call_args
    call.args[1](call.args[0], bytearray.fromhex(packet))


@pytest.mark.parametrize("route", range(6))
@pytest.mark.parametrize("properties,response", [(("write",), True), (("write", "write-without-response"), False)])
async def test_all_routes_startup_and_every_selected_literal(clock, route, properties, response):
    ctrl, c = make(route, properties=properties)
    await ctrl.start_notify()
    raw = route != 0
    assert frames(c) == (["00", "01", "01"] if raw else ["6e02010071", "6e08010178", "6e0a000179"])
    assert c.client.start_notify.call_args.args[0].uuid == "first-notify"
    c.client.write_gatt_char.reset_mock()
    for key, action in ACTIONS.items():
        for alternate, code in ((False, action.code), (True, action.alternate)):
            if code is None:
                continue
            expected = next(v["expected_bytes"] for v in WIRE if v["inputs"]["opcode"] == code and (v["protocol"] == "P2") is raw and v["inputs"]["prefix"] == [110, 1, 0])
            if key in ctrl.held_control_options:
                await ctrl.hold_control(key, 250)
                assert frames(c) == [bytes.fromhex(expected).hex()] * 2 + ["6e" if raw else "6e01006edd"]
            else:
                await ctrl.action(key, alternate=alternate)
                assert frames(c) == [bytes.fromhex(expected).hex()]
            assert all(call.kwargs["response"] is response for call in c.client.write_gatt_char.call_args_list)
            c.client.write_gatt_char.reset_mock()
    assert ctrl.supports_massage_timer and ctrl.massage_timer_options == [10, 20, 30]
    ctrl.on_disconnect()


async def test_first_roles_and_last_service_framing_are_independent(clock):
    ctrl, c = make()
    route = codec.TRANSPORTS["w1"]
    c.client.services.append(SimpleNamespace(uuid=route.service_uuid, characteristics=[char(route.write_uuid, "write"), char("later", "notify")]))
    await ctrl.start_notify()
    assert frames(c) == ["00", "01", "01"]
    assert all(call.args[0].uuid.lower() == GATT[0]["write"] for call in c.client.write_gatt_char.call_args_list)
    ctrl.on_disconnect()


async def test_property_gate_and_product_capabilities(clock):
    ctrl, c = make(product="afeg302", properties=("write-without-response",))
    with raises_key("super_colchones_route"):
        await ctrl.start_notify()
    assert frames(c) == []
    assert ctrl.memory_slot_count == 1 and not ctrl.supports_massage_timer
    assert len(ctrl.motor_control_specs) == 2
    with raises_key("super_colchones_control"):
        await ctrl.action("light")
    with raises_key("super_colchones_control"):
        await ctrl.program_memory(2)
    assert [s.key for s in ctrl.motor_control_specs] == ["back", "legs"]
    assert HINTS[0].matches_name("xQRRM123")
    assert not HINTS[0].matches_name("qrrm123")
    assert not HINTS[0].matches_name("NMRN123")


@pytest.mark.parametrize("row", INBOUND, ids=lambda r: r["id"])
def test_native_incoming_literals_and_bounded_malformed_data(row):
    result = [{"event": event.name, "value": event.value} for event in decode(bytes.fromhex(row["bytes"]))]
    expected = row["expected"]
    if isinstance(expected, dict) or row["id"] == "snore-stop-audio":
        expected = []  # Source errors are dropped safely; audio playback is excluded.
    assert result == expected


async def test_common_bitfields_are_diagnostics_without_inferred_controls(clock):
    ctrl, c = make()
    await ctrl.start_notify()
    notify(c, "6e90000100")
    notify(c, "6e9012ab00")
    notify(c, "6e90392d00")
    notify(c, "6e90a29c00")
    state = ctrl._observations
    assert state["deviceProtocolVersionEvent"] == 1
    assert state["deviceVersionOneBedModeEvent"] == 2
    assert state["deviceVersionOneMotorAngleEvent"] == {"no": 2, "status": 1, "angle": 45}
    assert state["deviceVersionOneMassageEvent"] == {"mode": 1, "massage1": 2, "massage2": 3, "massage3": 4}
    assert ctrl.position_number_specs == () and not ctrl.supports_clock_sync
    assert not ctrl.supports_light_color_control
    ctrl.on_disconnect()


async def test_residual_clear_only_expiry_and_replacement(monkeypatch):
    now = [0.0]
    timers = []
    loop = asyncio.get_running_loop()

    class Timer:
        def __init__(self, delay, callback):
            self.deadline, self.callback, self.cancelled = now[0] + delay, callback, False
            timers.append(self)
        def cancel(self):
            self.cancelled = True
        def when(self):
            return self.deadline

    monkeypatch.setattr(loop, "time", lambda: now[0])
    monkeypatch.setattr(loop, "call_later", Timer)
    def advance(t):
        now[0] = t
        for timer in timers:
            if not timer.cancelled and timer.deadline <= t:
                timer.cancelled = True
                timer.callback()

    rx = Receiver()
    assert rx.feed(bytes.fromhex("6e200d05")) == []
    advance(.499)
    assert rx.pending == bytes.fromhex("6e200d05")
    advance(.5)
    assert rx.pending == b""
    advance(1)
    assert rx.pending == b""
    assert rx.feed(bytes.fromhex("0102010203040506b8")) == []
    assert rx.pending == b""  # No late suffix joins the expired prefix.
    now[0] = 0
    assert rx.feed(bytes.fromhex("6e200d05")) == []
    advance(.3)
    assert rx.feed(bytes.fromhex("0102")) == []
    assert timers[-1].deadline == .8
    advance(.5)
    assert rx.pending == bytes.fromhex("6e200d050102")
    advance(.799)
    assert rx.pending == bytes.fromhex("6e200d050102")
    advance(.8)
    assert rx.pending == b""
    rx.close()


async def test_early_release_and_cancellation_use_owning_session(clock):
    ctrl, c = make()
    await ctrl.start_notify()
    c.client.write_gatt_char.reset_mock()
    await ctrl.hold_control("head_up", 80)
    assert frames(c) == []
    start = clock[0]
    await ctrl.hold_control("head_up", 250)
    assert clock[0] - start == pytest.approx(.25)
    assert frames(c) == ["6e01002493"] * 2 + ["6e01006edd"]
    c.client.write_gatt_char.reset_mock()
    async def cancel_after_write(*args, **kwargs):
        c.cancel_command.set()
    c.client.write_gatt_char.side_effect = cancel_after_write
    with pytest.raises(asyncio.CancelledError):
        await ctrl.hold_control("head_up", 1000)
    assert frames(c) == ["6e01002493", "6e01006edd"]
    # The fresh release event is independent of the still-cancelled command.
    assert c.cancel_command.is_set()
    ctrl.on_disconnect()


async def test_retired_callbacks_and_product_cannot_write_or_publish(clock):
    ctrl, c = make()
    await ctrl.start_notify()
    old = c.client.start_notify.call_args
    c.entry.data[const.CONF_PROTOCOL_VARIANT] = "afeg302"
    c.client.write_gatt_char.reset_mock()
    c.handle_controller_state_updates.reset_mock()
    old.args[1](old.args[0], bytearray.fromhex("6e09010078"))
    with raises_key("super_colchones_session"):
        await ctrl.action("light")
    assert frames(c) == []
    c.handle_controller_state_updates.assert_not_called()
    ctrl.on_disconnect()


async def test_failed_or_cancelled_timer_never_reports_sent_state(clock):
    ctrl, c = make()
    await ctrl.start_notify()
    c.handle_controller_state_updates.reset_mock()
    c.client.write_gatt_char.side_effect = OSError("radio")
    with pytest.raises(OSError):
        await ctrl.set_massage_timer(10)
    assert not any(u.key == MASSAGE_TIMER_MINUTES and u.value == 10 for call in c.handle_controller_state_updates.call_args_list for u in call.args)
    ctrl.on_disconnect()
    assert c.handle_controller_state_updates.call_args.args[-1].value == STATE_UNKNOWN


async def test_inflight_write_settles_before_release_and_retirement_blocks_cleanup(clock):
    ctrl, c = make()
    await ctrl.start_notify()
    c.client.write_gatt_char.reset_mock()
    entered, finish = asyncio.Event(), asyncio.Event()

    async def delayed(_char, packet, **kwargs):
        if packet == bytes.fromhex("6e01002493"):
            entered.set()
            await finish.wait()

    c.client.write_gatt_char.side_effect = delayed
    task = asyncio.create_task(ctrl.hold_control("head_up", 1000))
    await entered.wait()
    task.cancel()
    await asyncio.sleep(0)
    assert not task.done()
    assert frames(c) == ["6e01002493"]
    # A successor owns the link before the old radio operation finishes.
    c.controller = object()
    finish.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert frames(c) == ["6e01002493"]  # Never release on the successor's session.
    ctrl.on_disconnect()


async def test_local_stop_preserves_cancel_context_and_uses_proven_frame(clock):
    ctrl, c = make()
    await ctrl.start_notify()
    c.client.write_gatt_char.reset_mock()
    event = c.cancel_command
    await ctrl.stop_all()
    assert frames(c) == ["6e01006edd"]
    assert c.cancel_command is event and not event.is_set()
    await ctrl.hold_control("head_up", 80)
    assert frames(c) == ["6e01006edd"]
    ctrl.on_disconnect()


@pytest.mark.parametrize("duration", (100, 300, 1000))
async def test_exact_ticks_use_one_epoch_and_absorb_radio_latency(clock, monkeypatch, duration):
    ctrl, c = make()
    await ctrl.start_notify()
    c.client.write_gatt_char.reset_mock()
    times = []
    # Distinct clock reads expose the original one-pulse boundary bug.
    def sampled():
        clock[0] += .000001
        return clock[0]
    monkeypatch.setattr(bed, "monotonic", sampled)
    async def write(_char, packet, **kwargs):
        if packet == bytes.fromhex("6e01002493"):
            times.append(clock[0])
            clock[0] += .037
    c.client.write_gatt_char.side_effect = write
    start = clock[0]
    await ctrl.hold_control("head_up", duration)
    assert len(times) == duration // 100
    assert times == pytest.approx([start + n / 10 for n in range(1, duration // 100 + 1)], abs=.00002)
    assert frames(c)[-1] == "6e01006edd"
    c.client.write_gatt_char.reset_mock()
    c.motor_pulse_count = 1
    await ctrl.move_back_up()
    assert frames(c) == ["6e01002493", "6e01006edd"]
    ctrl.on_disconnect()


async def test_due_but_not_dispatched_expiry_cannot_join_late_suffix(monkeypatch):
    now = [0.0]
    loop = asyncio.get_running_loop()
    class Timer:
        def __init__(self, seconds, callback):
            self.deadline = now[0] + seconds
        def when(self):
            return self.deadline
        def cancel(self):
            pass
    monkeypatch.setattr(loop, "time", lambda: now[0])
    monkeypatch.setattr(loop, "call_later", Timer)
    rx = Receiver()
    assert rx.feed(bytes.fromhex("6e200d050102")) == []
    now[0] = .510  # Callback has not dispatched yet.
    assert rx.feed(bytes.fromhex("010203040506b8")) == []
    assert rx.pending == b""
    rx.close()


@pytest.mark.parametrize("name", ("QRRM123", "xQRRM123"))
def test_detailed_detection_offers_explicit_app_with_existing_receiver_priority(name):
    from custom_components.adjustable_bed.detection import detect_bed_type_detailed
    from tests.test_bluetooth_matchers import _info
    result = detect_bed_type_detailed(_info(name))
    assert "super_colchones" in {result.bed_type, *(result.ambiguous_types or ())}
    assert "name:super_colchones_app_candidate" in result.signals
    if name.startswith("QRRM"):
        assert result.bed_type == const.BED_TYPE_RICHMAT
    lower = detect_bed_type_detailed(_info(name.lower()))
    assert "super_colchones" not in {lower.bed_type, *(lower.ambiguous_types or ())}


@pytest.mark.parametrize("duration,late,expected", ((150, .4, []), (100, .104, ["6e01002493", "6e01006edd"]), (100, .106, [])))
async def test_expired_tick_never_starts_motion(clock, monkeypatch, duration, late, expected):
    ctrl, c = make()
    await ctrl.start_notify()
    c.client.write_gatt_char.reset_mock()
    async def late_wake(seconds, cancel):
        clock[0] = late
    monkeypatch.setattr(bed, "_pause", late_wake)
    await ctrl.hold_control("head_up", duration)
    assert frames(c) == expected
    ctrl.on_disconnect()


async def test_tick_expires_while_waiting_for_ble_lock(clock):
    ctrl, c = make()
    await ctrl.start_notify()
    c.client.write_gatt_char.reset_mock()
    attempted = asyncio.Event()
    class ObservedLock(asyncio.Lock):
        async def acquire(self):
            attempted.set()
            return await super().acquire()
    ctrl._ble_lock = ObservedLock()
    async with ctrl._ble_lock:
        attempted.clear()
        move = asyncio.create_task(ctrl.hold_control("head_up", 150))
        # Wait until _pause returned and the actual write task is blocked on
        # this held BLE lane, rather than advancing while still in _pause.
        await attempted.wait()
        assert clock[0] == pytest.approx(.1)
        clock[0] = .4
    await move
    assert frames(c) == []
    ctrl.on_disconnect()


@pytest.mark.parametrize("manufacturer,receiver,confidence", (({}, const.BED_TYPE_RICHMAT, .9), ({const.BEDTECH_MANUFACTURER_ID: b"\x00"}, const.BED_TYPE_BEDTECH, .95)))
def test_app_hint_preserves_confident_guided_receiver_suggestion(manufacturer, receiver, confidence):
    from custom_components.adjustable_bed.config_flow import _confident_auto_detect
    from custom_components.adjustable_bed.detection import detect_bed_type_detailed
    from tests.test_bluetooth_matchers import _info
    info = _info("QRRM123", (const.BEDTECH_SERVICE_UUID,), manufacturer)
    result = detect_bed_type_detailed(info)
    assert result.bed_type == receiver and result.confidence == confidence
    assert "super_colchones" in result.ambiguous_types
    assert _confident_auto_detect(result) == receiver
