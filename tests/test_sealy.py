"""Literal fitting and public Sealy behavior on a recorded physical session."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.adjustable_bed import button, switch
from custom_components.adjustable_bed.beds.sealy.controller import SealyController
from custom_components.adjustable_bed.codec import okin_5a as codec
from custom_components.adjustable_bed.controller_state import ControllerState
from custom_components.adjustable_bed.profiles import sealy as app
from custom_components.adjustable_bed.state_keys import (
    MASSAGE_TIMER_MINUTES,
    UNDER_BED_LIGHTS_ON,
    massage_intensity,
)
from tests.entity_surface import _Runtime
from tests.error_helpers import raises_key
from tests.hold_lease_wire import virtual_clock
from tests.sealy_vectors import COMMANDS


@pytest.mark.parametrize("key,literal", COMMANDS.items())
def test_literal_fit(key, literal):
    data = bytes.fromhex(literal)
    assert app.FRAMES[key] == data
    assert (codec.request(data[1]) if len(data) == 4 else codec.command(data[5], data[4])) == data
    for profile in app.PROFILES.values():
        if key in profile.frames:
            assert profile.frames[key] == data


@pytest.mark.parametrize(
    "parts,literal",
    [
        ((0, 0, 56, 34, 12, 19, 4, 11, 2026), "07041a0b13040c2238"),
        ((0, 0, 0, 0, 0, 1, 1, 1, 2001), "070401010101000000"),
    ],
)
def test_exact_raw_parts_clock(parts, literal):
    assert codec.raw_parts_clock(parts).hex() == literal


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("a50b", None),
        ("a50b00", (0, 0, 0, 0)),
        ("a50b000002580321", (1, 3, 1, 2)),
        ("a50b000002590fff", (2, 15, 15, 15)),
        ("a50b000001", (1, 0, 0, 0)),
        ("a50b000000010100", (1, 1, 0, 0)),
        ("a50b0000ffff12a3ff", (110, 2, 3, 10)),
        ("ed80000000000000", None),
    ],
)
def test_massage_parser(raw, expected):
    parsed = app.parse_massage(bytes.fromhex(raw))
    assert ((parsed.minutes, parsed.wave, parsed.head, parsed.foot) if parsed else None) == expected


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("a50e", None),
        ("a50e00", 0),
        ("a50e000000000000000015", 21),
        ("a50b000000000000000010", None),
    ],
)
def test_anti_pinch_parser(raw, expected):
    assert app.parse_anti_pinch(bytes.fromhex(raw)) == expected


async def bed(layout="0", *, start=True):
    roles = codec.TRANSPORTS["nus"]
    write = SimpleNamespace(
        uuid=roles.write_uuid,
        handle=12,
        properties=["write", "write-without-response"],
        descriptors=[],
    )
    notify = SimpleNamespace(
        uuid=roles.notify_uuid, handle=13, properties=["notify"], descriptors=[]
    )
    client = MagicMock()
    client.is_connected = True
    client.services = [SimpleNamespace(uuid=roles.service_uuid, characteristics=[write, notify])]
    client.write_gatt_char = AsyncMock()
    client.start_notify = AsyncMock()
    client.stop_notify = AsyncMock()
    state = ControllerState()
    co = SimpleNamespace(
        client=client,
        address="AA:BB:CC:DD:EE:FF",
        motor_count=2,
        motor_pulse_count=2,
        motor_pulse_delay_ms=300,
        cancel_command=asyncio.Event(),
        cancel_counter=0,
        connection_generation=0,
        command_scheduler=SimpleNamespace(token=object(), stop_epoch=0),
        record_command_trace=MagicMock(),
        name="Bed",
        entry=SimpleNamespace(data={"bed_type": "sealy_posturematic", "product_type": layout}),
        handle_controller_state_updates=lambda *updates: state.update(
            (u.key, u.value) for u in updates
        ),
    )
    c = co.controller = SealyController(co, layout)
    await c.async_discover_capabilities()
    co.connection_generation += 1
    if start:
        with virtual_clock():
            session = SimpleNamespace(async_start_notify=c.start_notify, is_current=lambda: True)
            await c.async_on_connect(session)
            await c.async_after_connect(session)
    return c, co, client, state


def frames(client):
    return [bytes(call.args[1]).hex() for call in client.write_gatt_char.await_args_list]


@pytest.mark.parametrize("layout", app.LAYOUTS)
async def test_layout_and_startup(layout):
    c, _, client, _ = await bed(layout)
    assert frames(client) == [
        COMMANDS[k] for k in ("initialize", "query_anti_pinch", "query_massage")
    ]
    assert [call.kwargs["response"] for call in client.write_gatt_char.await_args_list] == [
        True,
        False,
        False,
    ]
    assert c.supports_clock_sync is False
    assert c.alarm_capability is None
    assert c.memory_slot_count == 2
    assert c.supports_single_address_pairing is False
    assert c.has_lumbar_support is False
    assert c.supports_preset_lounge is False
    assert {s.key for s in c.motor_control_specs} == {"head", "feet", "both"}
    assert c.supports_massage and c.supports_lights
    assert all(s.hold is None for s in c.controller_button_specs if s.requires_confirmation)


async def test_massage_is_one_switch_without_a_toggle_button():
    """The Massage switch sends the app's on and off; no toggle button can unsettle it."""
    c, _, _, _ = await bed()
    runtime = _Runtime(c)
    with patch("homeassistant.helpers.entity_registry.async_get", return_value=MagicMock()):
        buttons = {e.translation_key for e in button._button_entities_for(MagicMock(), runtime)}
        switches = {e.translation_key for e in switch._switch_entities_for(MagicMock(), runtime)}
    assert "massage_all_toggle" not in buttons
    assert "sealy_massage" in switches


async def test_finite_public_commands_and_programming():
    c, _, client, _ = await bed()
    client.write_gatt_char.reset_mock()
    with virtual_clock():
        await c.move_head_up()
        assert frames(client) == [COMMANDS["head_up"]] * 2 + [COMMANDS["stop"]] * 2
        client.write_gatt_char.reset_mock()
        await c.preset_zero_g()
        assert frames(client) == [COMMANDS["zero_g"]] * 2 + [COMMANDS["stop"]] * 2
        client.write_gatt_char.reset_mock()
        await c.program_memory(1)
        assert frames(client) == [COMMANDS["save_memory_1"]] * 20 + [COMMANDS["stop"]] * 2
        with raises_key("sealy_control_invalid"):
            await c.program_memory(3)


async def test_event_cancel_and_fresh_release():
    c, co, client, _ = await bed()
    client.write_gatt_char.reset_mock()

    async def sent(*args, **kwargs):
        if args[1] == app.FRAMES["head_up"]:
            co.cancel_command.set()

    client.write_gatt_char.side_effect = sent
    with virtual_clock():
        await c.move_head_up()
    assert frames(client) == [COMMANDS["head_up"]] + [COMMANDS["stop"]] * 2


async def test_task_cancel_drains_inflight_before_release():
    c, _, client, _ = await bed()
    client.write_gatt_char.reset_mock()
    started, finish = asyncio.Event(), asyncio.Event()

    async def sent(*args, **kwargs):
        if args[1] == app.FRAMES["head_up"]:
            started.set()
            await finish.wait()

    client.write_gatt_char.side_effect = sent
    task = asyncio.create_task(c.move_head_up())
    await started.wait()
    task.cancel()
    await asyncio.sleep(0)
    assert frames(client) == [COMMANDS["head_up"]]
    finish.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert frames(client) == [COMMANDS["head_up"]] + [COMMANDS["stop"]] * 2


@pytest.mark.parametrize("change", ["client", "generation", "product", "address", "owner"])
async def test_no_refresh_or_release_on_replacement(change):
    c, co, client, _ = await bed()
    client.write_gatt_char.reset_mock()

    async def sent(*args, **kwargs):
        if args[1] != app.FRAMES["head_up"]:
            return
        if change == "client":
            co.client = MagicMock()
        elif change == "generation":
            co.connection_generation += 1
        elif change == "product":
            co.entry.data["product_type"] = "2"
        elif change == "address":
            co.address = "11:22:33:44:55:66"
        else:
            co.controller = MagicMock()

    client.write_gatt_char.side_effect = sent
    with virtual_clock(), raises_key("sealy_session_changed"):
        await c.move_head_up()
    assert frames(client) == [COMMANDS["head_up"]]


async def test_notify_state_and_stale_callback():
    c, co, client, state = await bed()
    receive = client.start_notify.call_args.args[1]
    notify = c._link.notify
    receive(notify, bytearray.fromhex("a50b000002580321"))
    assert state.get(MASSAGE_TIMER_MINUTES) == 1
    assert state.get(massage_intensity("head")) == 1
    client.write_gatt_char.reset_mock()
    with virtual_clock():
        await c.massage_mode_step()
    assert frames(client) == [COMMANDS["massage_off"]]
    for value in (0x15, 0x10, 0x13, 0x14, 0):
        receive(notify, bytearray.fromhex("a50e0000000000000000") + bytes([value]))
    # Raw status is diagnostic, never an emulation of an app dialog/admission flag.
    with virtual_clock():
        await c.action("voice_head_up")
    assert frames(client)[-1] == COMMANDS["voice_head_up"]
    c.on_disconnect()
    receive(notify, bytearray.fromhex("a50b000002580321"))
    assert state.get(MASSAGE_TIMER_MINUTES) is None


@pytest.mark.parametrize("layout", app.LAYOUTS)
async def test_reset_variants(layout):
    c, _, client, _ = await bed(layout)
    client.write_gatt_char.reset_mock()
    with virtual_clock():
        await c.action("reset")
    assert frames(client) == (
        [COMMANDS["stop"]] * 2 + [COMMANDS["reset_element"]]
        if layout == "0"
        else [COMMANDS["reset"]] * 20 + [COMMANDS["stop"]] * 2
    )


async def test_held_controls_validate_before_writes():
    c, _, client, _ = await bed()
    client.write_gatt_char.reset_mock()
    with raises_key("sealy_control_invalid"):
        await c.hold_control("save_zero_g", 6000)
    assert frames(client) == []
    with virtual_clock():
        await c.hold_control("both_down", 900)
    assert frames(client) == [COMMANDS["both_down"]] * 3 + [COMMANDS["stop"]] * 2


async def test_sent_light_state_and_write_failure():
    c, _, client, state = await bed()
    with virtual_clock():
        await c.lights_on()
    assert state.get(UNDER_BED_LIGHTS_ON) is True
    client.write_gatt_char.side_effect = ConnectionError("offline")
    with pytest.raises(ConnectionError):
        await c.lights_off()
    assert state.get(UNDER_BED_LIGHTS_ON) is True


@pytest.mark.parametrize(
    "name,match",
    [
        ("sTaR123", True),
        ("star", True),
        ("Star35", True),
        (" Star35", False),
        ("okin35", False),
        ("", False),
    ],
)
def test_exact_discovery_normalization(name, match):
    assert app.matches_name(name) is match


@pytest.mark.parametrize("layout", app.LAYOUTS)
async def test_live_catalog_routes(layout):
    c, _, client, _ = await bed(layout)
    with virtual_clock():
        for spec in c.controller_button_specs:
            key = spec.key.removeprefix("sealy_")
            client.write_gatt_char.reset_mock()
            await spec.press_fn(c)
            if key == "reset":
                expected = (
                    [COMMANDS["stop"]] * 2 + [COMMANDS["reset_element"]]
                    if layout == "0"
                    else [COMMANDS["reset"]] * 20 + [COMMANDS["stop"]] * 2
                )
            elif key.startswith("save_"):
                expected = [COMMANDS[key]] * 20 + [COMMANDS["stop"]] * 2
            elif key == "force_flat":
                expected = [COMMANDS[key]] * 2 + [COMMANDS["stop"]] * 2
            else:
                expected = [COMMANDS[key.removeprefix("once_")]] * (2 if key == "voice_stop" else 1)
            assert frames(client) == expected, key
        for action in (
            "massage_on",
            "massage_off",
            "massage_toggle",
            "massage_head_up",
            "massage_head_down",
            "massage_foot_up",
            "massage_foot_down",
            "light_on",
            "light_off",
            "light_toggle",
        ):
            client.write_gatt_char.reset_mock()
            method = {
                "light_on": "lights_on",
                "light_off": "lights_off",
                "light_toggle": "lights_toggle",
            }.get(action, action)
            await getattr(c, method)()
            assert frames(client) == [COMMANDS[action]] * (
                2 if action in ("massage_on", "massage_off", "massage_toggle") else 1
            )
        receive = client.start_notify.call_args.args[1]
        for wave, key in ((0, "mode_0"), (1, "mode_1"), (2, "mode_2"), (3, "massage_off")):
            receive(c._link.notify, bytearray.fromhex(f"a50b00000000{wave:02x}00"))
            client.write_gatt_char.reset_mock()
            await c.massage_mode_step()
            assert frames(client) == [COMMANDS[key]]


@pytest.mark.parametrize("case", ["wrong_service", "upper_service", "upper_write", "upper_notify"])
async def test_exact_gatt_roles(case):
    c, co, client, _ = await bed(start=False)
    service = client.services[0]
    if case == "wrong_service":
        service.uuid = "0000ffff-0000-1000-8000-00805f9b34fb"
    elif case == "upper_service":
        service.uuid = service.uuid.upper()
    elif case == "upper_write":
        service.characteristics[0].uuid = service.characteristics[0].uuid.upper()
    else:
        service.characteristics[1].uuid = service.characteristics[1].uuid.upper()
    with raises_key("sealy_gatt_missing"):
        await c.async_discover_capabilities()
    assert frames(client) == []


async def test_delivery_accounting():
    from custom_components.adjustable_bed.command_scheduler import (
        _CURRENT_COMMAND_CONTEXT,
        CommandContext,
        CommandKind,
    )

    c, co, client, state = await bed()
    client.write_gatt_char.reset_mock()
    context = CommandContext(
        object(), co.cancel_command, 0, "sealy-test", CommandKind.COMMAND, None, frozenset({"*"})
    )
    token = _CURRENT_COMMAND_CONTEXT.set(context)
    try:
        with virtual_clock():
            await c.move_head_up()
        assert context.frames_written == 2
        assert context.cleanup_stop_sent
        # Explicit STOP's own frames count, unlike the movement's cleanup.
        with virtual_clock():
            await c.stop_all()
        assert context.frames_written == 4
        co.cancel_command.set()
        await c.lights_on()
        assert state.get(UNDER_BED_LIGHTS_ON) is None
        assert context.frames_skipped > 0
        co.cancel_command.clear()
        original = client.write_gatt_char

        async def partial(*args, **kwargs):
            if len(client.write_gatt_char.await_args_list) == 2:
                raise ConnectionError("second frame failed")

        client.write_gatt_char = AsyncMock(side_effect=partial)
        with pytest.raises(ConnectionError), virtual_clock():
            await c.massage_on()
        assert context.frames_written == 5
        client.write_gatt_char = original
    finally:
        _CURRENT_COMMAND_CONTEXT.reset(token)


async def test_native_public_admission(hass, mock_coordinator_connected, mock_bleak_client):
    from unittest.mock import patch

    from pytest_homeassistant.common import MockConfigEntry

    from custom_components.adjustable_bed.const import DOMAIN
    from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
    from custom_components.adjustable_bed.cover import AdjustableBedCover, _build_cover_description
    from custom_components.adjustable_bed.services import async_register_services

    _, _, sample, _ = await bed()
    mock_bleak_client.services = sample.services
    mock_bleak_client.write_gatt_char = AsyncMock()
    mock_bleak_client.start_notify = AsyncMock()
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "address": "AA:BB:CC:DD:EE:FF",
            "name": "Sealy",
            "bed_type": "sealy_posturematic",
            "product_type": "1",
            "disable_angle_sensing": True,
            "has_massage": True,
            "connection_mode": "idle",
        },
    )
    entry.add_to_hass(hass)
    target = AdjustableBedCoordinator(hass, entry)
    try:
        with virtual_clock():
            assert await target.async_connect()
        assert isinstance(target.controller, SealyController)
        await async_register_services(hass)
        mock_bleak_client.write_gatt_char.reset_mock()
        with (
            patch(
                "custom_components.adjustable_bed.services._resolve_sided_targets",
                return_value=([(target, "both")], []),
            ),
            virtual_clock(),
        ):
            await hass.services.async_call(
                DOMAIN,
                "hold_control",
                {"device_id": "bed", "control": "head_up", "duration": 0.6},
                blocking=True,
            )
        assert frames(mock_bleak_client) == [COMMANDS["head_up"]] * 2 + [COMMANDS["stop"]] * 2
        mock_bleak_client.write_gatt_char.reset_mock()
        with (
            patch(
                "custom_components.adjustable_bed.services._resolve_sided_targets",
                return_value=([(target, "both")], []),
            ),
            virtual_clock(),
        ):
            await hass.services.async_call(
                DOMAIN,
                "goto_preset",
                {"device_id": "bed", "preset": 2, "duration": 0.6},
                blocking=True,
            )
            assert frames(mock_bleak_client) == [COMMANDS["memory_2"]] * 2 + [COMMANDS["stop"]] * 2
            mock_bleak_client.write_gatt_char.reset_mock()
            await hass.services.async_call(
                DOMAIN, "save_preset", {"device_id": "bed", "preset": 1}, blocking=True
            )
            assert (
                frames(mock_bleak_client)
                == [COMMANDS["save_memory_1"]] * 20 + [COMMANDS["stop"]] * 2
            )
        mock_bleak_client.write_gatt_char.reset_mock()
        cover = AdjustableBedCover(
            target, _build_cover_description(target.controller.motor_control_specs[1])
        )
        cover.async_write_ha_state = MagicMock()
        with virtual_clock():
            await cover.async_open_cover()
        assert frames(mock_bleak_client) and set(frames(mock_bleak_client)) == {
            COMMANDS["feet_up"],
            COMMANDS["stop"],
        }
    finally:
        await target.async_shutdown()


async def test_inflight_single_light_is_delivered_when_caller_cancelled():
    from custom_components.adjustable_bed.command_scheduler import (
        _CURRENT_COMMAND_CONTEXT,
        CommandContext,
        CommandKind,
    )

    c, co, client, state = await bed()
    began, finish = asyncio.Event(), asyncio.Event()

    async def sent(*args, **kwargs):
        began.set()
        await finish.wait()

    client.write_gatt_char.side_effect = sent
    context = CommandContext(
        object(), co.cancel_command, 0, "light-test", CommandKind.COMMAND, None, frozenset({"*"})
    )
    token = _CURRENT_COMMAND_CONTEXT.set(context)
    try:
        task = asyncio.create_task(c.lights_on())
        await began.wait()
        task.cancel()
        finish.set()
        with pytest.raises(asyncio.CancelledError):
            await task
    finally:
        _CURRENT_COMMAND_CONTEXT.reset(token)
    assert context.frames_written == 1 and context.frames_skipped == 0
    assert state.get(UNDER_BED_LIGHTS_ON) is True


async def test_queued_write_rechecks_owner_and_cancel():
    c, co, client, state = await bed()
    client.write_gatt_char.reset_mock()
    async with c.ble_lock:
        task = asyncio.create_task(c.lights_on())
        await asyncio.sleep(0)
        co.entry.data["product_type"] = "2"
    with raises_key("sealy_session_changed"):
        await task
    assert frames(client) == [] and state.get(UNDER_BED_LIGHTS_ON) is None
    co.entry.data["product_type"] = "0"
    async with c.ble_lock:
        task = asyncio.create_task(c.lights_on())
        await asyncio.sleep(0)
        co.cancel_command.set()
    await task
    assert frames(client) == []


async def test_native_massage_switch_uses_the_two_write_pair():
    from custom_components.adjustable_bed.beds.sealy.controller import MASSAGE_ON

    c, _, client, state = await bed()
    client.write_gatt_char.reset_mock()
    spec = c.controller_switch_specs[0]
    with virtual_clock():
        await spec.set_fn(c, True)
        assert state.get(MASSAGE_ON) is True
        await spec.set_fn(c, False)
    assert state.get(MASSAGE_ON) is False
    assert frames(client) == [COMMANDS["massage_on"]] * 2 + [COMMANDS["massage_off"]] * 2


async def test_gatt_selects_first_exact_service_and_characteristic():
    c, _, client, _ = await bed(start=False)
    first = client.services[0]
    original = first.characteristics[0]
    first.characteristics.append(SimpleNamespace(uuid=original.uuid, handle=88))
    client.services.append(SimpleNamespace(uuid=first.uuid, characteristics=[]))
    await c.async_discover_capabilities()
    assert c._link.write is original
