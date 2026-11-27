"""BERUN public controls, frozen state, physical-session cleanup and setup."""

from __future__ import annotations

import asyncio
from dataclasses import asdict
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.adjustable_bed.beds.berun import controller as runtime
from custom_components.adjustable_bed.beds.berun import state
from custom_components.adjustable_bed.controller_state import ControllerState
from custom_components.adjustable_bed.profiles import berun as app
from tests.hold_lease_wire import virtual_clock
from tests.test_berun_vectors import VECTORS
from tests.test_nerum import Char


def gatt(role=0, response=True):
    s, w, ns, n = app.ROLES[role]
    write = Char(w, 10, ["write"] if response else ["write-without-response"])
    notify = Char(n, 11, ["notify"])
    return [
        SimpleNamespace(uuid=s, characteristics=[write]),
        SimpleNamespace(uuid=ns, characteristics=[notify]),
    ]


def bed(version="v6", role=0, response=True):
    client = MagicMock(is_connected=True, services=gatt(role, response))
    client.write_gatt_char, client.start_notify, client.stop_notify = (
        AsyncMock(),
        AsyncMock(),
        AsyncMock(),
    )
    co = MagicMock(client=client, cancel_command=asyncio.Event(), motor_pulse_count=1)
    co.entry.data = {}
    co.controller_state = ControllerState()
    co.handle_controller_state_updates.side_effect = lambda *updates: co.controller_state.update(
        (u.key, u.value) for u in updates
    )
    return runtime.BerunController(co, app.PROFILES[version]), co, client


def frames(client):
    return [bytes(call.args[1]).hex() for call in client.write_gatt_char.call_args_list]


HELPERS = {
    "HeadUp": "head_up",
    "HeadDown": "head_down",
    "FootUp": "foot_up",
    "FootDown": "foot_down",
    "Flat": "flat",
    "MemoryZero": "zero_g",
    "MemoryPosition": "memory",
    "MemoryTv": "tv",
    "MemoryLounge": "read",
    "MemoryAntiSnore": "anti_snore",
    "Light": "light",
    "MassageAll": "massage_toggle",
    "MassageTime": "massage_timer",
    "MassageHeadPlus": "massage_head",
    "MassageFootPlus": "massage_foot",
    "MassageWavePlus": "massage_mode",
}


def test_profiles_match_all_accepted_live_literals():
    for row in VECTORS:
        if not row["id"].startswith(("H", "calendar-")) or not row["inputs"].get(
            "ui_reachable", True
        ):
            continue
        profile = app.PROFILES[f"v{row['inputs']['version']}"]
        action = row["action"]
        args = row["inputs"].get("arguments", [])
        if action in HELPERS:
            frame = profile.frame(next(a.mask for a in profile.actions if a.key == HELPERS[action]))
        elif action == "Stop":
            frame = profile.frame(0)
        elif action == "AlarmClick":
            frame = profile.alarm_frame(*args)
        elif action in ("AlarmCalibration", "Dynamic calendar date boundary"):
            frame = profile.clock_frame(
                datetime.fromisoformat(row["inputs"].get("clock", "2026-11-27T12:34:56+00:00"))
            )
        else:
            frame = profile.query(alarm=action == "AlarmCheck")
        assert frame.hex() == row["expected_bytes"], row["id"]


@pytest.mark.parametrize(
    "row", [r for r in VECTORS if "expected_state" in r], ids=lambda r: r["id"]
)
def test_frozen_parser_vectors(row):
    expected = row["expected_state"]
    reply = state.Replies().feed(row["inputs"]["version"], bytes.fromhex(row["expected_bytes"]))
    if isinstance(reply, state.Massage):
        assert asdict(reply) == expected
    elif isinstance(reply, state.Alarm):
        assert (reply.hour, reply.minute, reply.on) == (
            expected["hour"],
            expected["minute"],
            expected["isOn"],
        )
        assert reply.action == "massage"
        assert reply.detail()["weekdays"] == ["sunday"]
    else:
        assert expected == asdict(state.Massage())


def test_notification_events_are_not_reassembled_and_off_retains_alarm():
    parser = state.Replies()
    frame = bytes.fromhex("a50b0e0002580204060000000000")
    assert parser.feed(8, frame[:2]) is None and parser.feed(8, frame[2:]) is None
    on = parser.feed(8, bytes.fromhex("a50c0e008108071e0001"))
    off = parser.feed(8, bytes.fromhex("a50c0e00000000000000"))
    assert isinstance(on, state.Alarm) and isinstance(off, state.Alarm)
    assert (off.hour, off.minute, off.days, off.action) == (on.hour, on.minute, on.days, on.action)
    assert off.on is False
    for prefix in ("edfe16", "f4fe16", "a50b0e", "ed8003", "a50c0e"):
        assert parser.feed(8, bytes.fromhex(prefix)) is None
    # The source's isOn compares all three raw fields to zero, before P3 scaling.
    assert parser.feed(8, bytes.fromhex("a50b0e000001000000")).isOn


@pytest.mark.parametrize("version", app.PROFILES)
async def test_motion_refreshes_200ms_then_one_stop(version):
    c, co, client = bed(version)
    await c.async_discover_capabilities()
    with virtual_clock() as clock:
        await c.hold_control("head_up", 450)
        assert clock.now == pytest.approx(0.45)
    assert frames(client) == [c.berun.frame(1).hex()] * 3 + [c.berun.frame(0).hex()]
    assert {call.kwargs["response"] for call in client.write_gatt_char.call_args_list} == {True}


@pytest.mark.parametrize("version,key", [("v8", "light"), ("v7", "massage_timer")])
async def test_broken_live_actions_never_write(version, key):
    c, _, client = bed(version)
    assert key not in {s.key for s in c.controller_button_specs}
    with pytest.raises(ValueError):
        await c._run_action(key)
    assert not client.write_gatt_char.called


async def test_massage_click_has_delayed_query_without_stop():
    c, co, client = bed("v9", 2, False)
    await c.async_discover_capabilities()
    with virtual_clock() as clock:
        await c._run_action("massage_head")
        assert clock.now == pytest.approx(0.1)
    assert frames(client) == ["05020000080000", "00b0"]
    assert all(call.kwargs["response"] is False for call in client.write_gatt_char.call_args_list)


async def test_notification_and_gatt_ownership_survive_role_version_mismatch():
    c, co, old = bed("v7", 2)
    await c.async_discover_capabilities()
    await c.start_notify()
    callback = old.start_notify.call_args.args[1]
    callback(c._live().notify, bytearray.fromhex("ed8003071eff09"))
    assert co.controller_state.get(state.ALARM) == "07:30"
    c.on_disconnect()
    callback(Char("stale", 99, []), bytearray.fromhex("ed8003081eff11"))
    assert co.controller_state.get(state.ALARM) is None
    await c.async_discover_capabilities()
    await c.write_command(c.berun.frame(1))
    assert old.write_gatt_char.call_args.args[0].uuid == app.ROLES[2][1]


async def test_cancel_in_flight_write_settles_before_release():
    c, co, client = bed()
    await c.async_discover_capabilities()
    entered, finish = asyncio.Event(), asyncio.Event()
    order = []

    async def write(char, data, **kwargs):
        if bytes(data) == c.berun.frame(1):
            entered.set()
            await finish.wait()
            order.append("movement")
        else:
            order.append("release")

    client.write_gatt_char.side_effect = write
    task = asyncio.create_task(c.hold_control("head_up", 1000))
    await entered.wait()
    task.cancel()
    await asyncio.sleep(0)
    assert not task.done() and order == []
    finish.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert order == ["movement", "release"]


async def test_reconnect_does_not_transplant_pending_query_or_release():
    c, co, old = bed("v9", 2)
    await c.async_discover_capabilities()

    async def change(*args, **kwargs):
        c.on_disconnect()
        replacement = MagicMock(is_connected=True, services=gatt(2), write_gatt_char=AsyncMock())
        co.client = replacement
        await c.async_discover_capabilities()

    old.write_gatt_char.side_effect = change
    with pytest.raises(ConnectionError):
        await c._run_action("massage_head")
    assert frames(old) == ["05020000080000"]
    assert not co.client.write_gatt_char.called


async def test_reconnect_during_hold_never_releases_on_new_link():
    c, co, old = bed()
    await c.async_discover_capabilities()

    async def change(*args, **kwargs):
        c.on_disconnect()
        co.client = MagicMock(is_connected=True, services=gatt(), write_gatt_char=AsyncMock())
        await c.async_discover_capabilities()

    old.write_gatt_char.side_effect = change
    with pytest.raises(ConnectionError):
        await c.hold_control("head_up", 200)
    assert len(frames(old)) == 1 and not co.client.write_gatt_char.called


@pytest.mark.parametrize("version", app.PROFILES)
@pytest.mark.parametrize("preset", ["zero_g", "memory", "tv", "read", "anti_snore"])
async def test_long_preset_holds_only_repeat_recall_and_release(version, preset):
    c, _, client = bed(version)
    await c.async_discover_capabilities()
    with virtual_clock():
        await c.hold_control(preset, 5600)
    recall = c.berun.frame(c._action(preset).mask).hex()
    assert frames(client) == [recall] * 28 + [c.berun.frame(0).hex()]
    with pytest.raises(NotImplementedError):
        await c.program_memory(1)


async def test_old_startup_hook_cannot_sync_clock_on_replacement_session():
    c, _, client = bed()
    await c.async_discover_capabilities()
    await c.async_after_connect(SimpleNamespace(is_current=lambda: False))
    assert not client.write_gatt_char.called


def test_every_frozen_discovery_selector_uses_company_id_inclusive_data():
    import json
    from pathlib import Path

    rows = json.loads((Path(__file__).parent / "fixtures/berun/discovery.json").read_text())
    for row in rows:
        raw = bytes(row["bytes"])
        manufacturer = {int.from_bytes(raw[:2], "little"): raw[2:]} if raw else {}
        assert app.advertisement(row["name"], manufacturer) == f"v{row['expected']}"


async def test_query_deadline_does_not_drift_by_write_latency():
    c, _, client = bed("v9", 2)
    await c.async_discover_capabilities()
    with virtual_clock() as clock:
        starts = []

        async def write(char, data, **kwargs):
            starts.append(round(clock.now * 1000))
            await asyncio.sleep(0.075)

        client.write_gatt_char.side_effect = write
        await c._run_action("massage_head")
    assert starts == [0, 100]
