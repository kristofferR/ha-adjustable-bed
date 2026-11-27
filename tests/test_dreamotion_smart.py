"""Accepted Dreamotion Smart vectors and native, session-bound controls."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.adjustable_bed.beds.jiecang.dreamotion_smart import (
    BACK,
    DURATION,
    SENSOR_ENABLED,
    DreamotionSmartController,
)
from custom_components.adjustable_bed.codec import jiecang as codec
from custom_components.adjustable_bed.profiles import dreamotion_smart as app
from custom_components.adjustable_bed.state_keys import UNDER_BED_LIGHTS_RGB
from scripts.wire_snapshot import FakeClock, FakeServices, virtual_time
from tests.error_helpers import raises_key
from tests.test_controller_contract import _FactoryCoordinator

FIXTURES = Path(__file__).parent / "fixtures" / "dreamotion_smart"
VECTORS = json.loads((FIXTURES / "vectors.json").read_text())
PRIMARY = json.loads((FIXTURES / "primary.json").read_text())
LAYOUT = {
    "services": {app.SERVICE: [app.WRITE, app.NOTIFY]},
    "properties": {app.WRITE: ["write"], app.NOTIFY: ["notify"]},
}


@pytest.fixture
def bed():
    coordinator = _FactoryCoordinator()
    coordinator.motor_pulse_count = 2
    coordinator.motor_count = 4
    coordinator.record_command_trace = MagicMock()
    callbacks = []
    client = SimpleNamespace(
        is_connected=True,
        services=FakeServices(LAYOUT),
        write_gatt_char=AsyncMock(),
        stop_notify=AsyncMock(),
        disconnect=AsyncMock(),
    )

    async def subscribe(char, callback):
        callbacks.append(callback)

    client.start_notify = AsyncMock(side_effect=subscribe)
    coordinator.client = client

    def publish(*updates):
        coordinator.controller_state.update((u.key, u.value) for u in updates)

    coordinator.handle_controller_state_updates = publish
    controller = DreamotionSmartController(coordinator)
    return SimpleNamespace(
        c=controller,
        coordinator=coordinator,
        client=client,
        callbacks=callbacks,
        frames=lambda: [c.args[1].hex().upper() for c in client.write_gatt_char.await_args_list],
    )


@pytest.mark.parametrize("row", VECTORS, ids=lambda r: r["id"])
def test_every_frozen_builder_and_parser(row):
    i = row["inputs"]
    kind = i["kind"]
    expected = bytes.fromhex(row["expected_bytes"])
    if kind == "parser":
        record = codec.parse_sendinfo_record(expected)
        assert record is not None
        op, p = record
        if op == 0x81:
            actual = dict(
                zip(("back", "foot", "pattern", "duration"), (f"{v:02x}" for v in p), strict=True)
            )
        elif op == 0x45:
            actual = {
                **dict(
                    zip(
                        ("brightness", "red", "green", "blue"),
                        (f"{v:02x}" for v in p[:4]),
                        strict=True,
                    )
                ),
                "duration": p[4:].hex(),
            }
        elif op == 0x44:
            actual = {"slots": [p[n : n + 4].hex() for n in (0, 4, 8)]}
        else:
            actual = {
                {0x43: "light", 0x40: "sensor", 0x80: "massage_hz", 0x82: "audio_level"}[
                    op
                ]: p.hex()
            }
        assert actual == i["expected_state"]
        return
    a = i["args"]
    if kind == "common":
        op = int(a[0], 16)
        payload = codec.BILATERAL
        length = None
    elif kind == "flag":
        op = int(a[0], 16)
        payload = bytes.fromhex(a[1] + "00")
        length = None
    elif kind == "date":
        op = int(a[0], 16)
        payload = bytes.fromhex(a[1])
        length = None
    elif kind == "variable":
        op = int(a[0][:2], 16)
        payload = bytes.fromhex(a[1])
        length = int(a[0][2:], 16)
    else:
        op = 0x85
        payload = bytes.fromhex(a[0] + a[1])
        length = 4
    assert codec.frame(op, payload, declared_length=length) == expected


@pytest.mark.parametrize("row", PRIMARY, ids=lambda r: r["id"])
async def test_primary_caller_cases(bed, row, monkeypatch):
    c = bed.c
    i = row["inputs"]
    kind = row["kind"]
    await c.start_notify()
    if kind == "massage":
        state = app.Massage(**{k: int(v, 16) for k, v in i["state"].items()})
        local, wire = state.cycle(i["action"])
        assert wire is not None
        assert [[0, wire.frame().hex().upper()]] == row["expected"]
        assert {k: f"{v:02x}" for k, v in asdict(local).items()} == row["expected_state"]
        # Acoustic overlay blocks zone UI in HA too; the callable remains byte-tested above.
        if i["action"].startswith("timer") or state.hz:
            c._massage = state
            c._massage_known = c._mode_known = True
            await c.cycle_massage(i["action"])
            assert bed.frames() == [row["expected"][0][1]]
        return
    if kind in ("mode", "slots", "timed"):
        clock = FakeClock()
        events = []

        async def write(char, data, **kwargs):
            events.append([round(clock.now * 1000), data.hex().upper()])

        bed.client.write_gatt_char.side_effect = write
        original_pause = c._pause

        async def pause(ms, cancel):
            if kind == "mode" and "state_at_resume" in i:
                late = i["state_at_resume"]
                c._receive(
                    bytes.fromhex(
                        "f2f281ffff"
                        + "".join(late[k] for k in ("back", "foot", "pattern", "duration"))
                    )
                )
            if kind == "slots" and "selection_at_resume" in i:
                c._slot = i["selection_at_resume"]
            return await original_pause(ms, cancel)

        monkeypatch.setattr(c, "_pause", pause)
        with virtual_time(clock):
            if kind == "mode":
                c._massage = app.Massage(**{k: int(v, 16) for k, v in i["state"].items()})
                c._massage_known = True
                await c.set_mode("inherent" if i["inherent"] else "acoustic")
            elif kind == "slots":
                c._page = "presets"
                c._slot = i["selection"]
                groups = [app.Color(*bytes.fromhex(g)) for g in i["groups"]]
                c._colors = tuple(groups)
                await c._save_light(preview=i["preview"], delay_ms=i.get("delay", 300))
            elif not i["brightness"]:
                # The raw artifact's malformed default frame is reproducible,
                # but native read/modify/write admission must never dispatch it.
                assert (
                    codec.frame(0x45, b"\xa1", declared_length=7).hex().upper()
                    == row["expected"][0][1]
                )
                with raises_key("dreamotion_smart_refresh"):
                    await c._save_light(preview=False)
                assert not events
                return
            else:
                c._timed = (
                    app.Color(int(i["brightness"], 16), *bytes.fromhex(i["rgb"])),
                    int(i["duration"], 16),
                )
                await c._save_light(preview=i["preview"], delay_ms=i.get("delay", 300))
        assert events == row["expected"]
    elif kind == "schedule":
        actual = app.MAIN_QUERIES if i["screen"] == "main" else app.MASSAGE_QUERIES
        assert [[t, f.hex().upper()] for t, f in actual] == row["expected"][
            :-1
        ]  # Audio 82 is excluded.
    elif kind == "route":
        assert (
            list(app.destinations(i["address"], "main" if i["origin"] == "main" else "control"))
            == row["expected"]
        )
    elif kind == "duration":
        c._timed = app.Color(50, 1, 2, 3), 0
        await c._duration_option(str(app.DURATIONS[i["slider"]]))
        assert c._timed[1].to_bytes(2, "big").hex() == row["expected"]
        assert bed.coordinator.controller_state[DURATION] == str(c._timed[1])
        assert not bed.frames()  # Duration choice is local until Save/Preview.
    elif kind == "color":
        rgb = tuple(bytes.fromhex(i["argb"])[1:])
        c._timed = app.Color(50, 1, 2, 3), 0
        with virtual_time(FakeClock()):
            await c.set_light_color(rgb)
        assert bed.frames()[0][12:18] == row["expected"]
    else:
        # Android's countdown only resets UI; startup has no countdown retries.
        assert row["id"] == "PC-COUNTDOWN"
        with virtual_time(FakeClock()):
            await c.async_on_connect(SimpleNamespace(async_start_notify=AsyncMock()))
        assert len(bed.frames()) == 7
        assert bed.client.start_notify.await_count == 1


async def test_hold_release_cancellation_and_session_fence(bed, monkeypatch):
    c = bed.c
    await c.start_notify()

    async def cancel_after_first(*args, **kwargs):
        bed.coordinator.cancel_command.set()

    bed.client.write_gatt_char.side_effect = cancel_after_first
    with virtual_time(FakeClock()):
        await c.move_back_up()
    assert bed.frames() == ["F1F101020000037E", "F1F14E020000507E"]
    assert c.execution.declared == {"hold"}
    bed.coordinator.cancel_command.clear()
    bed.client.write_gatt_char.reset_mock(side_effect=True)
    replacement = SimpleNamespace(is_connected=True, write_gatt_char=AsyncMock())

    async def replace_link(*args, **kwargs):
        bed.coordinator.client = replacement
        c.on_disconnect()

    bed.client.write_gatt_char.side_effect = replace_link
    with virtual_time(FakeClock()), pytest.raises(ConnectionError):
        await c.move_back_up()
    replacement.write_gatt_char.assert_not_called()
    assert len(bed.frames()) == 1


async def test_notify_owned_state_and_failure_invalidates_admission(bed):
    c = bed.c
    await c.start_notify()
    notify = bed.callbacks[0]
    sender = c._link.notify
    notify(sender, bytearray.fromhex("f2f281ffff01020304"))
    assert bed.coordinator.controller_state[BACK] == 1  # No invented checksum requirement.
    notify(sender, bytearray.fromhex("f2f24002a101"))
    assert bed.coordinator.controller_state[SENSOR_ENABLED] is True
    notify(sender, bytearray.fromhex("f2f24507a164ff0080012c"))
    assert bed.coordinator.controller_state[UNDER_BED_LIGHTS_RGB] == (255, 0, 128)
    notify(sender, bytearray.fromhex("f2f281"))  # Safe short-callback rejection.
    bed.client.write_gatt_char.side_effect = ConnectionError("admission failed")
    with pytest.raises(ConnectionError, match="admission failed"):
        await c.lights_on()
    assert c._link is None
    bed.client.disconnect.assert_awaited_once()
    assert len(bed.frames()) == 1  # No retry/ACK packet.
    notify(sender, bytearray.fromhex("f2f281ffff03020100"))
    assert bed.coordinator.controller_state[BACK] is None
    with pytest.raises(ConnectionError):
        await c.lights_on()


async def test_native_specs_and_gatt_admission(bed):
    c = bed.c
    await c.start_notify()
    assert [s.key for s in c.motor_control_specs] == list(app.AXES)
    assert c.memory_slot_count == 2
    assert not c.supports_single_address_pairing
    assert c.alarm_capability is None
    with virtual_time(FakeClock()):
        for spec in c.motor_control_specs:
            await spec.open_fn(c)
        await c.preset_zero_g()
        await c.program_memory(2)
    assert bed.frames()[-2:] == ["F1F107020000097E", "F1F10C0200000E7E"]
    with pytest.raises(ValueError):
        await c.preset_memory(3)
    for spec in c.controller_button_specs:
        assert spec.card.section.value in ("lighting", "massage", "presets", "utility")
    bed.client.services = FakeServices(
        {
            "services": {app.SERVICE: [app.WRITE, app.NOTIFY]},
            "properties": {app.WRITE: ["read"], app.NOTIFY: ["notify"]},
        }
    )
    with raises_key("dreamotion_smart_gatt"):
        await c.async_discover_capabilities()
