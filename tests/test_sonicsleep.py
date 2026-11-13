"""SonicSleep's public profile, transport, observation and ownership contracts."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.app_profiles import per_side_profile
from custom_components.adjustable_bed.beds.sonicsleep import controller as bed
from custom_components.adjustable_bed.beds.sonicsleep.protocol import Alarm, decode, form_alarm
from custom_components.adjustable_bed.codec import richmat as codec
from custom_components.adjustable_bed.detection import bed_type_label, get_bed_type_options
from custom_components.adjustable_bed.profiles.sonicsleep import DIRECTIONS, ROUTES
from custom_components.adjustable_bed.setup_questions import setup_profile
from tests.sonicsleep_vectors import VECTORS
from tests.test_casper_base import char, frames
from tests.test_controller_contract import _FactoryCoordinator

GATT = {row["id"]: row for row in json.loads((Path(__file__).parent / "fixtures/sonicsleep/gatt.json").read_text())}


def make(route="W1", properties=("write", "write-without-response")):
    c = _FactoryCoordinator()
    c.entry.data[const.CONF_PRODUCT_TYPE] = "one"
    c.handle_controller_state_updates = MagicMock()
    c.record_command_trace = MagicMock()
    c.client = MagicMock(is_connected=True)
    c.client.start_notify = AsyncMock()
    c.client.stop_notify = AsyncMock()
    c.client.write_gatt_char = AsyncMock()
    gatt = GATT[route]
    c.client.services = [SimpleNamespace(uuid=gatt["service"].upper(), characteristics=[char(gatt["write"].upper(), *properties), char("first-notify", "notify"), char(gatt["expected_notify_constant"], "notify")])]
    controller = bed.SonicSleepController(c)
    c.controller = controller
    return controller, c


@pytest.fixture
def clock(monkeypatch):
    now = [0.0]
    real = asyncio.sleep

    async def pause(seconds, cancel):
        now[0] += seconds
        await real(0)
        return cancel.is_set()

    monkeypatch.setattr(bed, "monotonic", lambda: now[0])
    monkeypatch.setattr(bed, "_pause", pause)
    monkeypatch.setattr(bed.dt_util, "now", lambda: datetime(2026, 11, 12, 5, 30, tzinfo=timezone(timedelta(minutes=330))))
    return now


def notify(c, packet):
    call = c.client.start_notify.call_args
    call.args[1](call.args[0], bytearray.fromhex(packet))


@pytest.mark.parametrize("route", ROUTES)
@pytest.mark.parametrize("properties,response", [(("write",), True), (("write", "write-without-response"), False)])
async def test_routes_exact_startup_roles_and_all_public_commands(clock, route, properties, response):
    ctrl, c = make(route, properties)
    await ctrl.start_notify()
    raw = route == "Nordic"
    assert c.client.start_notify.call_args.args[0].uuid == "first-notify"
    assert frames(c) == (["00", "01"] if raw else ["6e02010071", "6e08010178"]) + ["6e0820060300009f", "6e0c200802016af50180058a", "6e0d20080301380b0c051e0019"]
    c.client.write_gatt_char.reset_mock()
    for row in VECTORS["commands"]:
        p = row["inputs"]
        if row["kind"] != "function" or p["route"] != route or p["action"] in ("exit_limit", "query_clock"):
            continue
        action = p["action"]
        if action in DIRECTIONS:
            await ctrl.hold_control(action, 201)
            expected = [row["expected_bytes"]] * 3
        else:
            await ctrl.action(action.removeprefix("save_"), save=action.startswith("save_"))
            expected = [row["expected_bytes"]]
        assert frames(c) == expected
        assert all(call.kwargs["response"] is response for call in c.client.write_gatt_char.call_args_list)
        c.client.write_gatt_char.reset_mock()
    await ctrl.stop_all()
    assert frames(c) == []


async def test_write_without_response_only_is_not_a_route(clock):
    ctrl, _ = make(properties=("write-without-response",))
    with pytest.raises(ValueError, match="writable route"):
        await ctrl.start_notify()


async def test_property_routing_overwrite_and_notify_registration(clock):
    ctrl, c = make("Nordic")
    w = codec.TRANSPORTS["w1"]
    c.client.services.append(SimpleNamespace(uuid=w.service_uuid, characteristics=[char(w.write_uuid, "write"), char("later", "notify")]))
    registered = []

    async def start(characteristic, callback):
        registered.append(callback)
        callback(characteristic, bytearray.fromhex("6e09010078"))

    c.client.start_notify.side_effect = start
    await ctrl.start_notify()
    assert ctrl._link.single is False  # Later recognized service overwrites route.
    assert ctrl._link.write.uuid.lower() == codec.TRANSPORTS["n1"].write_uuid
    assert ctrl.observations["clock_capability"] is True
    assert len(registered) == 1


async def test_observations_do_not_enable_unproven_setters_or_positions(clock):
    ctrl, c = make()
    await ctrl.start_notify()
    assert ctrl.observations == {}
    for row in VECTORS["notifications"]:
        notify(c, row["bytes"])
    assert ctrl.observations["link_name"] == "RM-A\0"
    assert not ctrl.supports_massage and not ctrl.supports_lights
    assert not ctrl.supports_position_feedback and not ctrl.position_number_specs
    assert not ctrl.supports_single_address_pairing
    assert [s.key for s in ctrl.motor_control_specs] == ["back", "legs", "both"]
    assert ctrl.execution.hold == "stream" and not ctrl.execution.concurrent
    assert len(ctrl.controller_button_specs) == 8
    assert all(s.requires_confirmation for s in ctrl.controller_button_specs if s.key.endswith("_save"))


async def test_alarm_list_escalation_ack_and_opaque_caller_domains(clock):
    ctrl, c = make()
    await ctrl.start_notify()
    notify(c, "6e09010078")
    notify(c, "6e200d0501030307061e45839a")  # Unknown escalation cannot insert.
    assert not ctrl.alarms
    for row in VECTORS["alarm_repair"][:3]:
        notify(c, row["received"])
        c.client.write_gatt_char.reset_mock()
        await ctrl.execute_request(bed.Request("toggle", id=row["expected_cached"]["id"], enabled=row["enabled"]))
        assert frames(c) == [row["expected_bytes"]]
    assert ctrl.alarms[0].id == 9 and ctrl.alarms[0].opaque == 136
    notify(c, VECTORS["alarm_repair"][2]["received"])
    c.client.write_gatt_char.reset_mock()
    await ctrl.execute_request(bed.Request("edit", id=9, hour=6, minute=30, days=(0, 6), enabled=False))
    assert frames(c) == [VECTORS["alarm_repair"][4]["expected_bytes"]]
    notify(c, VECTORS["alarm_repair"][2]["received"])
    c.client.write_gatt_char.reset_mock()
    await ctrl.execute_request(bed.Request("delete", id=9))
    assert frames(c) == [VECTORS["alarm_repair"][5]["expected_bytes"]]
    assert ctrl.alarms[0].opaque == 136  # Sending is not an observation.
    notify(c, "6e07010177")
    assert ctrl.observations["alarm_add_success"] is True


@pytest.mark.parametrize("operation", ["edit", "toggle", "delete"])
async def test_alarm_mutation_ack_cannot_make_old_fields_writable(clock, monkeypatch, operation):
    ctrl, c = make()
    await ctrl.start_notify()
    notify(c, "6e09010078")
    notify(c, "6e200d0501020307061e458399")
    old = tuple(ctrl.alarms)
    await ctrl.execute_request(bed.Request(operation, id=3, hour=7, minute=45, days=(0, 6)))
    notify(c, "6e07010177")  # ACK has no current record fields.
    assert tuple(ctrl.alarms) == old  # Never invent a post-write observation.
    c.client.write_gatt_char.reset_mock()
    monkeypatch.setattr(bed, "STATE_WAIT_S", 0.01)
    with pytest.raises(ValueError, match="No current-connection"):
        await ctrl.execute_request(bed.Request("toggle", id=3, enabled=False))
    assert frames(c) == ["6e0820050100009c"]  # Query only, no stale mutation.
    notify(c, "6e200d0501020300072d4583a2")
    c.client.write_gatt_char.reset_mock()
    await ctrl.execute_request(bed.Request("toggle", id=3, enabled=False))
    assert frames(c) == ["6e0d200501010300072d4582a0"]


@pytest.mark.parametrize("wait", ["tick", "lock"])
async def test_alarm_plan_revalidated_at_actual_ble_write_boundary(clock, monkeypatch, wait):
    ctrl, c = make()
    await ctrl.start_notify()
    notify(c, "6e09010078")
    notify(c, "6e200d0501020307061e458399")
    plan = await ctrl.prepare_plan(bed.Request("toggle", id=3, enabled=False))
    c.client.write_gatt_char.reset_mock()
    ready, resume = asyncio.Event(), asyncio.Event()

    async def pause(seconds, cancel):
        ready.set()
        if wait == "tick":
            await resume.wait()
        return cancel.is_set()

    monkeypatch.setattr(bed, "_pause", pause)
    if wait == "lock":
        await ctrl._ble_lock.acquire()
    task = asyncio.create_task(ctrl.execute_prepared(plan))
    await ready.wait()
    await asyncio.sleep(0)
    notify(c, "6e200d0501030307081e45839c")
    if wait == "lock":
        ctrl._ble_lock.release()
    resume.set()
    with pytest.raises(ValueError, match="changed during admission"):
        await task
    assert frames(c) == []


async def test_alarm_latest_received_fields_win_over_older_duplicate_list_records(clock):
    ctrl, c = make()
    await ctrl.start_notify()
    notify(c, "6e09010078")
    notify(c, "6e200d0501020307061e458399")
    notify(c, "6e200d0501020307081e45839b")
    notify(c, "6e200d0501020307061e458399")  # Existing duplicate, now latest.
    assert len(ctrl.alarms) == 2  # Preserve the source's full-record list dedup.
    c.client.write_gatt_char.reset_mock()
    await ctrl.execute_request(bed.Request("toggle", id=3, enabled=False))
    assert frames(c) == ["6e0d200501010307061e458297"]


async def test_missing_cache_rejects_without_alarm_mutation(clock, monkeypatch):
    ctrl, c = make()
    await ctrl.start_notify()
    notify(c, "6e09010078")
    c.client.write_gatt_char.reset_mock()
    monkeypatch.setattr(bed, "STATE_WAIT_S", 0.01)
    with pytest.raises(ValueError, match="No current-connection"):
        await ctrl.execute_request(bed.Request("toggle", id=3))
    assert frames(c) == ["6e0820050100009c"]
    c.client.write_gatt_char.reset_mock()
    with pytest.raises(ValueError, match="No current-connection"):
        await ctrl.execute_request(bed.Request("new"))
    assert frames(c) == ["6e0820050100009c"]


async def test_new_allocator_reads_current_cache_and_form_zero(clock):
    ctrl, c = make()
    await ctrl.start_notify()
    notify(c, "6e09010078")
    c.client.write_gatt_char.reset_mock()

    async def reply(_char, packet, **kwargs):
        if packet.hex() == "6e0820050100009c":
            notify(c, "6e200d0501020307061e458399")

    c.client.write_gatt_char.side_effect = reply
    await ctrl.execute_request(bed.Request("new", hour=6, minute=30))
    assert frames(c) == ["6e0820050100009c", form_alarm(1, 6, 30, "zero_gravity", (), True).packet().hex()]


async def test_stale_notifications_and_prepared_settings_are_fenced(clock):
    ctrl, c = make()
    await ctrl.start_notify()
    old = c.client.start_notify.call_args
    notify(c, "6e09010078")
    notify(c, "6e200d0501020307061e458399")
    plan = await ctrl.prepare_plan(bed.Request("toggle", id=3, enabled=False))
    ctrl.on_disconnect()
    old.args[1](old.args[0], bytearray.fromhex("6e09010078"))
    assert ctrl.observations == {} and not ctrl.alarms
    c.client.write_gatt_char.reset_mock()
    await ctrl.start_notify()
    with pytest.raises(ConnectionError):
        await ctrl.execute_prepared(plan)
    c.controller = bed.SonicSleepController(c)
    old.args[1](old.args[0], bytearray.fromhex("6e09010078"))
    with pytest.raises(ConnectionError):
        await ctrl.action("flat")


async def test_cancel_during_tick_fences_unsent_and_drain_inflight(clock):
    ctrl, c = make()
    await ctrl.start_notify()
    c.client.write_gatt_char.reset_mock()
    entered, finish = asyncio.Event(), asyncio.Event()

    async def write(_char, packet, **kwargs):
        entered.set()
        await finish.wait()

    c.client.write_gatt_char.side_effect = write
    hold = asyncio.create_task(ctrl.hold_control("head_up", 1000))
    await entered.wait()
    hold.cancel()
    await asyncio.sleep(0)
    assert not hold.done()
    finish.set()
    with pytest.raises(asyncio.CancelledError):
        await hold
    assert frames(c) == ["6e01002493"]
    c.cancel_command.set()
    await ctrl.hold_control("head_up", 1000)
    await ctrl.stop_all()
    assert frames(c) == ["6e01002493"]


@pytest.mark.parametrize("wait", ["tick", "lock"])
async def test_minimum_hold_drops_writes_after_deadline(clock, monkeypatch, wait):
    ctrl, c = make()
    await ctrl.start_notify()
    c.client.write_gatt_char.reset_mock()
    start = clock[0]
    if wait == "tick":
        async def late_tick(seconds, cancel):
            clock[0] += 0.2
            return cancel.is_set()

        monkeypatch.setattr(bed, "_pause", late_tick)
        await ctrl.hold_control("head_up", 100)
    else:
        async with ctrl._ble_lock:
            task = asyncio.create_task(ctrl.hold_control("head_up", 100))
            await asyncio.sleep(0)
            await asyncio.sleep(0)
            clock[0] = start + 0.2
        await task
    assert frames(c) == []


async def test_cancel_during_first_tick_prevents_minimum_hold_write(clock, monkeypatch):
    ctrl, c = make()
    await ctrl.start_notify()
    c.client.write_gatt_char.reset_mock()

    async def cancel_tick(seconds, cancel):
        clock[0] += seconds
        cancel.set()
        return True

    monkeypatch.setattr(bed, "_pause", cancel_tick)
    await ctrl.hold_control("head_up", 100)
    assert frames(c) == []


async def test_slow_writes_do_not_backfill_or_exceed_deadline(clock):
    ctrl, c = make()
    await ctrl.start_notify()
    c.client.write_gatt_char.reset_mock()
    start = clock[0]

    async def slow(*args, **kwargs):
        clock[0] += 0.5

    c.client.write_gatt_char.side_effect = slow
    await ctrl.hold_control("head_up", 1100)
    assert frames(c) == ["6e01002493"] * 2
    assert clock[0] - start == pytest.approx(1.2)  # Only the already in-flight write drains.


@pytest.mark.parametrize("raw", (b"\x6e\x20\x00", b"\x6e\x20\x02", bytes([110, 32, 7, 5, 1, 2, 0]), b"x" * 5000))
def test_malformed_input_is_bounded(raw):
    receiver = bed.Receiver()
    for frame in receiver.feed(raw):
        decode(frame)
    assert len(receiver.pending) <= 255


def test_setup_is_fixed_app_owned_and_findable():
    profile = setup_profile("sonicsleep")
    settled = profile.settled({})
    assert settled[const.CONF_PRODUCT_TYPE] == "one"
    assert settled[const.CONF_MOTOR_COUNT] == 2
    assert settled[const.CONF_HAS_MASSAGE] is False
    assert settled[const.CONF_DISABLE_ANGLE_SENSING] is True
    assert profile.imports
    assert per_side_profile("sonicsleep", "auto") is not None
    assert "SonicSleep" in bed_type_label("sonicsleep")
    assert any("SonicSleep" in row["label"] for row in get_bed_type_options())
    for value in ("", "unknown", "none"):
        c = _FactoryCoordinator()
        c.entry.data[const.CONF_PRODUCT_TYPE] = value
        with pytest.raises(ValueError, match="fixed"):
            bed.SonicSleepController(c)


@pytest.mark.parametrize("route", ROUTES)
def test_codec_gatt_roles_match_accepted_literals(route):
    transport, literal = codec.TRANSPORTS[ROUTES[route]], GATT[route]
    assert (transport.service_uuid, transport.write_uuid, transport.notify_uuid) == (literal["service"], literal["write"], literal["expected_notify_constant"])


def test_raw_byte_character_link_and_diagnostic_bed_only():
    assert decode(codec.record_20_len(6, 3, 2, (0, 195, 169, 0)))["link_name"] == "Ã©\0"
    assert "diagnostic" in decode(codec.record_20_len(10, 5, 0, (0,)))
    assert not decode(codec.record_20_len(10, 6, 0, (0,)))
    assert Alarm(9, 136, 250, 251, 167, 85).toggle(False).packet().hex() == "6e0d200501010988fafba75423"


@pytest.mark.parametrize("route", ("sonicsleep", "sonicsleep:Nordic", "sonicsleep:W2", "sonicsleep:W3", "sonicsleep:W4", "sonicsleep:W5"))
@pytest.mark.parametrize("end", ("expire", "stop"))
async def test_real_renewable_lease_ends_without_a_release_packet(route, end):
    from tests.hold_lease_wire import intervals, leased_hold

    async def move(controller):
        await controller.hold_control("head_up", 30000)

    wire = await leased_hold(route, move, end_after_s=2, end=end)
    assert len(wire.held) > wire.pulse_count
    assert intervals(wire.held) <= {107}
    assert not wire.after
    expected = "24" if route.endswith("Nordic") else "6e01002493"
    assert {write.data.hex() for write in wire.held} == {expected}
