"""Enso Remote frozen literals, layout gates and connection-owned commands."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.adjustable_bed.beds.keeson.enso import EnsoController
from custom_components.adjustable_bed.codec import keeson
from custom_components.adjustable_bed.controller_state import ControllerState
from custom_components.adjustable_bed.profiles import enso as app
from custom_components.adjustable_bed.profiles.keeson import encode
from tests.error_helpers import raises_key
from tests.hold_lease_wire import virtual_clock

VECTORS = json.loads((Path(__file__).parent / "fixtures/enso/vectors.json").read_text())


@pytest.mark.parametrize("row", VECTORS, ids=lambda r: r["action"])
def test_frozen_literals(row):
    raw = bytes.fromhex(row["expected_bytes"])
    if row["kind"] == "control":
        for profile in app.PROFILES.values():
            assert encode(profile, int(row["inputs"]["key"], 16)) == raw
    elif row["kind"] == "rename":
        assert app.rename(row["inputs"]["name"]) == raw
    else:
        actual = app.parse_status(raw)
        expected = row["expected_parse"]
        if not expected.get("accepted") or expected.get("suppressed"):
            assert actual is None
        elif "lamp" in expected:
            assert actual.light == bool(expected["lamp"])
        elif "timer_minutes" in expected:
            assert actual.timer_minutes == expected["timer_minutes"]
        elif expected.get("timer") == "off":
            assert actual.timer_minutes == 0
        else:
            assert actual.timer_minutes is None


async def bed(layout="2", response=True):
    write = SimpleNamespace(
        uuid=app.WRITE_UUID,
        handle=22,
        properties=["write"] if response else ["write-without-response"],
    )
    notify = SimpleNamespace(uuid=app.NOTIFY_UUID, handle=32, properties=["notify"])
    client = MagicMock()
    client.is_connected = True
    client.services = [SimpleNamespace(uuid="arbitrary-service", characteristics=[write, notify])]
    client.write_gatt_char = AsyncMock()
    client.start_notify = AsyncMock()
    client.stop_notify = AsyncMock()
    state = ControllerState()
    coordinator = SimpleNamespace(
        client=client,
        address="AA:BB:CC:DD:EE:FF",
        motor_count=int(layout),
        motor_pulse_count=10,
        motor_pulse_delay_ms=100,
        cancel_command=asyncio.Event(),
        record_command_trace=MagicMock(),
        name="Bed",
        handle_controller_state_updates=lambda *updates: state.update(
            (u.key, u.value) for u in updates
        ),
    )
    controller = EnsoController(coordinator, layout)
    await controller.async_discover_capabilities()
    return controller, coordinator, client, state


def frames(client):
    return [bytes(c.args[1]).hex() for c in client.write_gatt_char.await_args_list]


@pytest.mark.parametrize(
    "layout,keys",
    [
        ("2", {"head", "feet", "both"}),
        ("3", {"head", "feet", "lumbar"}),
        ("4", {"head", "feet", "tilt", "lumbar"}),
    ],
)
async def test_layout_capabilities(layout, keys):
    controller, _, _, _ = await bed(layout)
    assert {s.key for s in controller.motor_control_specs} == keys
    assert controller.supports_memory_programming is False
    assert controller.supports_single_address_pairing is False
    assert controller.position_number_specs == ()
    assert ("massage_mode" in controller.held_control_options) == (layout == "3")
    assert all(
        s.scheduler_resource == "motor:*" and s.hold.stop_scope == "side"
        for s in controller.motor_control_specs
    )


async def test_press_kinds_and_release():
    c, _, client, _ = await bed("3")
    with virtual_clock():
        await c.preset_flat()
        assert frames(client) == ["e5fe1600000008fe", "e5fe160000000006"]
        client.write_gatt_char.reset_mock()
        await c.action("head_massage_increase")
        await c.lights_toggle()
        assert frames(client) == ["e5fe1600080000fe", "e5fe160000020004"]
        client.write_gatt_char.reset_mock()
        await c.hold_control("memory_A", 300)
        assert frames(client) == ["e5fe1600200000e6"] * 3 + ["e5fe160000000006"]


async def test_event_cancellation_releases_on_fresh_event():
    c, co, client, _ = await bed()

    async def sent(*args, **kwargs):
        if bytes(args[1]) != keeson.frame(0):
            co.cancel_command.set()

    client.write_gatt_char.side_effect = sent
    with virtual_clock():
        await c.move_head_up()
    assert frames(client) == [keeson.frame(1).hex(), keeson.frame(0).hex()]


async def test_task_cancellation_releases():
    c, _, client, _ = await bed()
    started = asyncio.Event()

    async def sent(*args, **kwargs):
        started.set()

    client.write_gatt_char.side_effect = sent
    task = asyncio.create_task(c.move_feet_up())
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert frames(client)[-1] == keeson.frame(0).hex()


async def test_reconnect_never_retargets_release():
    c, co, client, _ = await bed()
    replacement = MagicMock()
    replacement.write_gatt_char = AsyncMock()

    async def sent(*args, **kwargs):
        co.client = replacement

    client.write_gatt_char.side_effect = sent
    with virtual_clock(), raises_key("enso_session_changed"):
        await c.move_head_up()
    assert len(frames(client)) == 1
    replacement.write_gatt_char.assert_not_awaited()


async def test_last_runtime_handles_and_write_mode():
    c, _, client, _ = await bed(response=False)
    first = client.services[0].characteristics[0]
    last = SimpleNamespace(
        uuid=app.WRITE_UUID, handle=77, properties=["write", "write-without-response"]
    )
    client.services.append(SimpleNamespace(uuid="another-service", characteristics=[last]))
    await c.async_discover_capabilities()
    await c.lights_toggle()
    assert client.write_gatt_char.await_args.args[0] is last
    assert client.write_gatt_char.await_args.kwargs["response"] is True
    client.services[1].characteristics = [first]
    await c.async_discover_capabilities()
    await c.lights_toggle()
    assert client.write_gatt_char.await_args.kwargs["response"] is False


async def test_notification_suppression_retention_and_session_fence():
    c, co, client, state = await bed()
    await c.start_notify()
    sender, receive = client.start_notify.await_args.args
    data = bytearray(16)
    data[13:15] = bytes((0x40, 2))
    receive(sender, data)
    assert state.get("enso_light") is True
    assert state.get("massage_timer") == 20
    data[14] = 7
    receive(sender, data)
    assert state.get("massage_timer") == 20
    data[13] = 0x20
    receive(sender, data)
    assert state.get("enso_light") is True
    c.on_disconnect()
    receive(sender, bytearray(16))
    assert state.get("enso_light") is None
    assert state.get("massage_timer") is None
    co.client = MagicMock()
    receive(sender, data)
    assert state.get("enso_light") is None


async def test_rename_and_errors():
    c, _, client, _ = await bed()
    await c.rename_device("Enso")
    assert frames(client) == ["ef02456e736f000000000000000000000079"]
    for name in ("", "x" * 15):
        with raises_key("enso_name_invalid"):
            c.validate_device_rename(name)
    with raises_key("enso_control_invalid"):
        c.validate_hold_control("massage_mode", 100)
    client.services = []
    with raises_key("enso_gatt_missing"):
        await c.async_discover_capabilities()


@pytest.mark.parametrize("layout", ["2", "3", "4"])
async def test_setup_factory_and_manual_labels(layout):
    from custom_components.adjustable_bed import const
    from custom_components.adjustable_bed.controller_factory import create_controller
    from custom_components.adjustable_bed.detection import BED_TYPE_DISPLAY_NAMES
    from custom_components.adjustable_bed.setup_questions import setup_profile

    profile = setup_profile("enso")
    data = {const.CONF_PRODUCT_TYPE: layout, **profile.settled({const.CONF_PRODUCT_TYPE: layout})}
    assert data[const.CONF_MOTOR_COUNT] == int(layout)
    assert data[const.CONF_DISABLE_ANGLE_SENSING] is True
    assert BED_TYPE_DISPLAY_NAMES["enso"] == "Enso Remote"
    from tests.test_controller_contract import _FactoryCoordinator

    coordinator = _FactoryCoordinator()
    _, _, client, _ = await bed(layout)
    coordinator.entry = SimpleNamespace(data=data, options={})
    controller = await create_controller(coordinator, "enso", "auto", client)
    assert controller.profile is app.PROFILES[layout]
    assert len({s.name for s in controller.controller_button_specs}) == len(
        controller.controller_button_specs
    )


async def test_elapsed_hold_and_slow_ack_does_not_burst():
    c, _, client, _ = await bed()
    starts = []

    async def sent(*args, **kwargs):
        starts.append(asyncio.get_running_loop().time())
        await asyncio.sleep(0.15)

    client.write_gatt_char.side_effect = sent
    with virtual_clock():
        await c.hold_control("head_up", 300)
    assert frames(client) == [keeson.frame(1).hex()] * 2 + [keeson.frame(0).hex()]
    assert starts[-1] - starts[0] == pytest.approx(0.3)


async def test_cancel_before_start_sends_no_cleanup_or_command():
    c, co, client, _ = await bed()
    co.cancel_command.set()
    await c.move_head_up()
    client.write_gatt_char.assert_not_awaited()


async def test_queued_command_rechecks_cancel_and_link():
    c, co, client, _ = await bed()
    async with c._ble_lock:
        task = asyncio.create_task(c.lights_toggle())
        await asyncio.sleep(0)
        co.cancel_command.set()
    await task
    client.write_gatt_char.assert_not_awaited()


async def test_wrong_layout_and_duration_errors():
    c, _, _, _ = await bed()
    with raises_key("enso_control_invalid"):
        await c.action("massage_mode")
    with raises_key("enso_control_invalid"):
        await c.move_lumbar_up()
    for duration in (True, 0, 60001):
        with raises_key("enso_duration_invalid"):
            c.validate_hold_control("head_up", duration)


@pytest.mark.parametrize("layout", ["2", "3", "4"])
async def test_every_layout_motor_and_held_action_uses_its_words(layout):
    c, _, client, _ = await bed(layout)
    with virtual_clock():
        for spec in c.motor_control_specs:
            for move, index in ((spec.open_fn, 0), (spec.close_fn, 1)):
                client.write_gatt_char.reset_mock()
                await move(c)
                assert frames(client) == [
                    keeson.frame(app.MOTOR_WORDS[spec.key][index]).hex()
                ] * 10 + [keeson.frame(0).hex()]
        for key in c.held_control_options:
            client.write_gatt_char.reset_mock()
            await c.hold_control(key, 100)
            if key in app.HELD_WORDS:
                word = app.HELD_WORDS[key]
            else:
                motor, direction = key.rsplit("_", 1)
                word = app.MOTOR_WORDS[motor][0 if direction == "up" else 1]
            assert frames(client) == [keeson.frame(word).hex(), keeson.frame(0).hex()]
        for spec in c.controller_button_specs:
            if spec.key.removeprefix("enso_") in app.MASSAGE_WORDS:
                client.write_gatt_char.reset_mock()
                await spec.press_fn(c)
                assert frames(client) == [
                    keeson.frame(app.MASSAGE_WORDS[spec.key.removeprefix("enso_")]).hex()
                ]


async def test_repeated_cancellation_awaits_release_and_does_not_count_cleanup():
    from custom_components.adjustable_bed.command_scheduler import (
        _CURRENT_COMMAND_CONTEXT,
        CommandContext,
        CommandKind,
    )

    c, co, client, _ = await bed()
    held_sent, cleanup_started, allow_cleanup = asyncio.Event(), asyncio.Event(), asyncio.Event()

    async def sent(*args, **kwargs):
        if bytes(args[1]) == keeson.frame(0):
            cleanup_started.set()
            await allow_cleanup.wait()
        else:
            held_sent.set()

    client.write_gatt_char.side_effect = sent
    context = CommandContext(
        object(), co.cancel_command, 0, "enso-test", CommandKind.HOLD, None, frozenset({"motor:*"})
    )
    token = _CURRENT_COMMAND_CONTEXT.set(context)
    try:
        task = asyncio.create_task(c.move_head_up())
    finally:
        _CURRENT_COMMAND_CONTEXT.reset(token)
    await held_sent.wait()
    task.cancel()
    await cleanup_started.wait()
    task.cancel()
    await asyncio.sleep(0)
    assert not task.done()
    allow_cleanup.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert frames(client)[-1] == keeson.frame(0).hex()

    assert context.frames_written == 1
    assert context.cleanup_stop_sent is True
