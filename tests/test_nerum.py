"""Frozen Nerum 1.0.8 literals and session-safe HA execution."""

from __future__ import annotations

import asyncio
import gzip
import json
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.adjustable_bed.beds.nerum import controller as runtime
from custom_components.adjustable_bed.beds.nerum import state
from custom_components.adjustable_bed.controller_state import ControllerState
from custom_components.adjustable_bed.profiles import nerum as app
from tests.hold_lease_wire import virtual_clock

FIXTURE = Path(__file__).parent / "fixtures/nerum"
BUILDERS = json.loads(gzip.decompress((FIXTURE / "builders.json.gz").read_bytes()))
PARSERS = json.loads((FIXTURE / "parsers.json").read_text())


def test_every_accepted_builder_case_uses_production_encoders():
    assert len(BUILDERS) == 5088
    for row in BUILDERS:
        payload = bytes(row["payload"]) if row["payload"] is not None else None
        args = (row["protocol"].lower(), row["function"], row["subfunction"], payload)
        if row["expected"].startswith("EXCEPTION:"):
            with pytest.raises(ValueError):
                app.build(*args, now=datetime(2026, 11, 16, 0, 30, 25))
        else:
            assert (
                app.build(*args, now=datetime(2026, 11, 16, 0, 30, 25)).hex() == row["expected"]
            ), row


def test_frozen_live_alarm_banks_and_slots():
    for row in json.loads((FIXTURE / "alarms.json").read_text()):
        if row["protocol"] == "P2":
            bank = tuple(
                app.Alarm(a["hour"], a["minute"], a["repeat"], a["type"], a["on"])
                for a in row["inputs"]
            )
            assert app.alarms("p2", bank)[0].hex() == row["expected"]
        else:
            a = row["inputs"]
            bank = (app.Alarm(a["hour"], a["minute"], a["repeat"], a["kind"], a["on"]),) * 3
            assert app.alarms("p3", bank)[a["index"]].hex() == row["expected"]


def test_r1_and_safe_session_owned_fragment_admission():
    prefix = bytes.fromhex(PARSERS[11]["hex"])
    replies = state.Replies()
    assert replies.feed("p2", prefix) is None
    assert replies.pending == prefix
    assert replies.feed("p2", bytes.fromhex(PARSERS[12]["hex"])) == state.Status(
        3, 3, 20, 3, None, True
    )
    assert replies.pending is None
    assert replies.feed("p2", b"\0\x04\0") is None
    assert replies.feed("p2", bytes.fromhex("ed800300")) is None
    # A real admitted short alarm fails closed instead of indexing beyond it.
    assert replies.feed("p2", bytes.fromhex("ed800300000000000000")) is None
    assert state.Replies().feed("p2", b"\0\x04\0") is None
    assert replies.feed("p1", bytes.fromhex(PARSERS[3]["hex"])) is None
    assert replies.feed("p1", bytes.fromhex(PARSERS[4]["hex"])) == state.Operation(4)
    assert replies.feed("p1", b"\xa5") is None
    for row in PARSERS:
        if row["parser"] == "P3" and row["expected"] and "index" in row["expected"]:
            result = replies.feed("p3", bytes.fromhex(row["hex"]))
            assert isinstance(result, tuple)
            index, alarm = result[0]
            assert index == row["expected"]["index"]
            assert alarm.hour == row["expected"]["hour"]
            assert alarm.repeat == row["expected"]["repeat"] & 255



def test_alarm_detail_names_days_and_wake_action():
    alarm = app.Alarm(7, 30, 0b1000_0011, app.WAKE["memory_2"], True)
    assert state.alarm_detail(alarm) == {
        "enabled": True,
        "days": ["sunday", "monday"],
        "recurring": True,
        "action": "memory_2",
    }
    assert state.alarm_detail(app.Alarm(kind=9))["action"] is None

def test_exact_discovery_literals_and_truncation_safety():
    for row in PARSERS:
        if row["parser"] != "discovery":
            continue
        actual = app.advertisement(row["name"], bytes.fromhex(row["hex"]))
        expected = row["expected"]
        if expected is None or "exception" in expected:
            assert actual is None
        else:
            assert (actual.protocol, actual.identifier, actual.motors, actual.massage) == (
                expected["protocol"].lower(),
                expected["id"],
                expected["motors"],
                expected["massage"],
            )


class Char:
    def __init__(self, uuid, handle, properties):
        self.uuid, self.handle, self.properties = uuid, handle, properties
        self.descriptors = []


def gatt(profile):
    write = Char(profile.write, 10, ["write", "write-without-response"])
    notify = Char(profile.notify, 11, ["notify"])
    return [
        SimpleNamespace(uuid=profile.service, characteristics=[write]),
        SimpleNamespace(uuid=profile.notify_service, characteristics=[notify]),
    ]


def bed(protocol="p2", layout="nerum"):
    client = MagicMock(is_connected=True, services=gatt(app.PROFILES[protocol]))
    client.write_gatt_char = AsyncMock()
    client.start_notify = AsyncMock()
    client.stop_notify = AsyncMock()
    co = MagicMock(client=client, cancel_command=asyncio.Event(), motor_pulse_count=1)
    co.entry.data = {"product_type": layout}
    co.controller_state = ControllerState()
    co.handle_controller_state_updates.side_effect = lambda *updates: co.controller_state.update(
        (u.key, u.value) for u in updates
    )
    return runtime.NerumController(co, protocol), co, client


def frames(client):
    return [bytes(call.args[1]) for call in client.write_gatt_char.call_args_list]


@pytest.mark.parametrize("protocol", app.PROTOCOLS)
async def test_short_hold_and_proven_release(protocol, monkeypatch):
    ctrl, co, client = bed(protocol)
    await ctrl.async_discover_capabilities()
    with virtual_clock():
        await ctrl.hold_control("back_up", 1)
    assert frames(client) == [
        app.build(protocol, 1, 1),
        app.build(protocol, 6),
        app.build(protocol, 6),
    ]
    assert not ctrl.supports_memory_programming
    assert ctrl.memory_slot_count == (1 if protocol == "p1" else 2)


async def test_radio_latency_does_not_expand_finite_hold(monkeypatch):
    ctrl, co, client = bed()
    await ctrl.async_discover_capabilities()
    with virtual_clock():

        async def slow(*args, **kwargs):
            await asyncio.sleep(0.4)

        client.write_gatt_char.side_effect = slow
        await ctrl.hold_control("back_up", 350)
    assert frames(client) == [app.build("p2", 1, 1), app.build("p2", 6), app.build("p2", 6)]


async def test_old_notifications_and_deferred_release_cannot_retarget(monkeypatch):
    ctrl, co, first = bed()
    await ctrl.async_discover_capabilities()
    await ctrl.start_notify()
    old = ctrl._live()
    callback = first.start_notify.call_args.args[1]
    ctrl.on_disconnect()
    replacement = MagicMock(
        is_connected=True, services=gatt(ctrl.profile), write_gatt_char=AsyncMock()
    )
    co.client = replacement
    await ctrl.async_discover_capabilities()
    callback(old.notify, bytearray.fromhex("00000000000000000100"))
    with virtual_clock():
        await ctrl._release(old)
    assert frames(first) == frames(replacement) == []
    assert not co.controller_state


async def test_clock_and_full_bank_schedule(monkeypatch):
    ctrl, co, client = bed("p3")
    await ctrl.async_discover_capabilities()
    bank = (app.Alarm(6, 30, 130, 17, True), app.Alarm(), app.Alarm())
    with virtual_clock():
        await ctrl.set_alarms(bank)
    assert frames(client)[1:] == [
        *app.alarms("p3", bank),
        *(app.query("p3", slot) for slot in range(1, 4)),
    ]


def test_all_status_shapes_and_signed_single_field_dispatch():
    for index, expected in (
        (0, state.Status(1, 2, 30, 2, True, True)),
        (1, state.Status(1, 2, 30, 2, True, True)),
        (13, state.Status(2, 3, 20, 2, None, True)),
        (14, state.Status(0, 0, 10, 0, None, True)),
    ):
        row = PARSERS[index]
        assert state.Replies().feed(row["parser"].lower(), bytes.fromhex(row["hex"])) == expected
    # Signed low byte 80 needs high byte 21 to enter the source's 2080 case.
    assert state.Replies().feed("p1", bytes.fromhex("a55a00000021800001")) == state.Status(
        light=True
    )
    assert state.Replies().feed("p1", bytes.fromhex("a55a00000020800001")) is None


async def test_release_and_alarm_offsets_include_radio_latency():
    ctrl, co, client = bed("p3")
    await ctrl.async_discover_capabilities()
    with virtual_clock() as clock:
        starts = []

        async def slow(_char, frame, **_kwargs):
            starts.append((round(clock.now * 1000), bytes(frame)))
            await asyncio.sleep(0.007)

        client.write_gatt_char.side_effect = slow
        await ctrl.set_alarms((app.Alarm(), app.Alarm(), app.Alarm()))
        assert [t for t, _ in starts] == [0, 100, 200, 300, 400, 600, 800]
        starts.clear()
        began = clock.now
        await ctrl._release(ctrl._live())
        assert [t - round(began * 1000) for t, _ in starts] == [300, 600]


async def test_preset_release_is_not_a_duplicate_motor_release():
    ctrl, co, client = bed("p2", "4")
    await ctrl.async_discover_capabilities()
    with virtual_clock():
        await ctrl.hold_control("memory_1", 1)
    assert frames(client) == [app.build("p2", 10)] + [app.build("p2", 6)] * 2
