"""Row158 factory, HA callers, sessions and bounded/renewable control paths."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bleak import BleakClient
from homeassistant.exceptions import ServiceValidationError

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.beds.ore_ultramatic import state_keys as state
from custom_components.adjustable_bed.beds.ore_ultramatic.controller import OreUltramaticController
from custom_components.adjustable_bed.button import _button_entities_for
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.cover import AdjustableBedCover, _build_cover_description
from custom_components.adjustable_bed.profiles import ore_ultramatic as app
from custom_components.adjustable_bed.services import async_register_services
from tests.hold_lease_wire import virtual_clock
from tests.test_ore_comfort_bed import _char, _entry, _written

APP = const.KEESON_VARIANT_ORE_ULTRAMATIC


@pytest.fixture
async def target(hass, mock_coordinator_connected, mock_establish_connection):
    made = []

    async def make(route="P1", count=2, address="AA:BB:CC:DD:01:58"):
        entry = _entry(hass, APP, count, address)
        coordinator = AdjustableBedCoordinator(hass, entry)
        coordinator._max_retries = 1
        client = MagicMock(spec=BleakClient)
        client.is_connected = True
        client.write_gatt_char = AsyncMock()
        client.read_gatt_char = AsyncMock(return_value=b"")
        client.start_notify = AsyncMock()
        client.stop_notify = AsyncMock()

        async def disconnect():
            client.is_connected = False

        client.disconnect = AsyncMock(side_effect=disconnect)
        mock_establish_connection.side_effect = None
        mock_establish_connection.return_value = client
        client.services = [
            SimpleNamespace(
                uuid=app.SELECTOR if route == "P1" else "other",
                characteristics=[
                    _char(app.WRITE, ["write", "write-without-response"]),
                    _char(app.NOTIFY, ["notify"]),
                ],
            )
        ]
        hass.data.setdefault(const.DOMAIN, {})[entry.entry_id] = coordinator
        assert await coordinator.async_connect()
        assert isinstance(coordinator.controller, OreUltramaticController)
        client.write_gatt_char.reset_mock()
        made.append(coordinator)
        return coordinator, client

    yield make
    for coordinator in made:
        await coordinator.async_shutdown()


@pytest.mark.parametrize("route", ("P1", "P2"))
@pytest.mark.parametrize(
    "count,axes",
    (
        (2, ("back", "feet", "both")),
        (3, ("back", "feet", "head")),
        (4, ("back", "feet", "waist", "lumbar")),
    ),
)
async def test_factory_layout_and_cover_caller(target, route, count, axes):
    coordinator, client = await target(route, count)
    ctrl = coordinator.controller
    assert tuple(s.key for s in ctrl.motor_control_specs) == axes
    assert ctrl.memory_slot_count == (2 if route == "P1" else 0)
    assert bool(ctrl.controller_number_specs) == (route == "P1")
    assert ctrl.execution.hold == "stream" and not ctrl.execution.concurrent
    assert ctrl.capability_snapshot() == {"ultramatic_route": route}
    # Last duplicate wins across unrelated service UUIDs, without a name gate.
    last = _char(app.WRITE, ["write"])
    client.services.append(SimpleNamespace(uuid="unrelated", characteristics=[last]))
    ctrl.on_disconnect()
    ctrl._capture_link()
    assert ctrl._link.write is last
    coordinator._motor_pulse_count = 2
    cover = AdjustableBedCover(coordinator, _build_cover_description(ctrl.motor_control_specs[-1]))
    cover.async_write_ha_state = MagicMock()
    with virtual_clock():
        await cover.async_open_cover()
    word = ctrl._axes[axes[-1]][0]
    from custom_components.adjustable_bed.profiles.keeson import encode

    expected = encode(app.profile(route), word).hex()
    assert _written(client) == [expected, expected, encode(app.profile(route), 0).hex()]
    assert all(
        c.args[0] is last and c.kwargs["response"] for c in client.write_gatt_char.call_args_list
    )


async def test_p1_presets_save_massage_and_native_entities(hass, target):
    coordinator, client = await target()
    with virtual_clock():
        await coordinator.async_execute_controller_command(lambda c: c.preset_memory(1))
        await coordinator.async_execute_controller_command(lambda c: c.preset_memory(1))
        await coordinator.async_execute_controller_command(lambda c: c.program_memory(2))
        await coordinator.async_execute_controller_command(lambda c: c.program_flat())
        await coordinator.async_execute_controller_command(lambda c: c.program_zero_g())
        await coordinator.async_execute_controller_command(lambda c: c.massage_start())
        await coordinator.async_execute_controller_command(lambda c: c.massage_off())
    assert _written(client) == [
        "e5fe1601000008fd",
        "e5fe160000000006",
        "e5fe1620000009dd",
        "e5fe1620000002e4",
        "e5fe1620000001e5",
        "e5fe1610000021d5",
        "e5fe1610000011e5",
        "e5fe1611000011e4",
        "e5fe1610000010e6",
        "e5fe1611000010e5",
    ]
    buttons = _button_entities_for(hass, coordinator)
    assert any(e.unique_id.endswith("ore_comfort_program_flat") for e in buttons)
    assert not any(e.unique_id.endswith("_ore_ultramatic_massage_toggle") for e in buttons)


async def test_p2_native_buttons_and_held_preset(hass, target):
    coordinator, client = await target("P2")
    ctrl = coordinator.controller
    buttons = _button_entities_for(hass, coordinator)
    assert any(e.unique_id.endswith("_ore_ultramatic_massage_head") for e in buttons)
    assert not any(e.unique_id.endswith("ore_comfort_program_flat") for e in buttons)
    with virtual_clock():
        await coordinator.async_execute_controller_command(lambda c: c.hold_preset("tv", 201))
    assert _written(client) == ["e6fe160040000000c5"] * 3 + ["e6fe16000000000005"]
    client.write_gatt_char.reset_mock()
    with pytest.raises(ValueError), virtual_clock():
        await ctrl.program_memory(1)
    assert not client.write_gatt_char.called


@pytest.mark.parametrize("route", ("P1", "P2"))
async def test_registered_alarm_all_fields_and_query_timing(hass, target, route):
    coordinator, client = await target(route)
    await async_register_services(hass)
    now = datetime(2026, 11, 17, 7, 6, 5)
    with (
        patch(
            "custom_components.adjustable_bed.beds.ore_ultramatic.controller.dt_util.now",
            return_value=now,
        ),
        patch(
            "custom_components.adjustable_bed.services._resolve_sided_targets",
            return_value=([(coordinator, "both")], []),
        ),
        virtual_clock() as clock,
    ):
        began = clock.time()
        await hass.services.async_call(
            const.DOMAIN,
            "ore_ultramatic_set_alarm",
            {
                "device_id": "bed",
                "enabled": True,
                "time": "07:30:00",
                "repeat": -128,
                "alarm_type": 2,
            },
            blocking=True,
        )
        assert clock.time() - began == pytest.approx(0.3 if route == "P1" else 0.4)
    assert _written(client) == (
        ["ebfe160506071e070280ffff0841", "e2fe1605060702f5"]
        if route == "P1"
        else ["e780017e0a11070605ec", "ed8003071e800f0000000000000000db", "e28003009a"]
    )


async def test_alarm_captures_stop_before_lazy_import(hass, target, monkeypatch):
    from custom_components.adjustable_bed.beds.ore_ultramatic import services

    coordinator, client = await target()
    await async_register_services(hass)
    original = services.async_import_modules

    async def stopped_import(*args):
        await coordinator.async_stop_command()
        client.write_gatt_char.reset_mock()
        await original(*args)

    monkeypatch.setattr(services, "async_import_modules", stopped_import)
    with (
        patch(
            "custom_components.adjustable_bed.services._resolve_sided_targets",
            return_value=([(coordinator, "both")], []),
        ),
        virtual_clock(),
    ):
        # A stopped scheduler admission ends normally without sending its plan.
        await hass.services.async_call(
            const.DOMAIN,
            "ore_ultramatic_set_alarm",
            {"device_id": "bed", "enabled": True, "time": "07:30:00"},
            blocking=True,
        )
    assert not client.write_gatt_char.called


async def test_notification_session_and_fragment_callbacks(target):
    coordinator, client = await target("P2")
    ctrl = coordinator.controller
    callback = client.start_notify.await_args.args[1]
    callback(None, bytearray.fromhex("0000000000000005000000000000f300"))
    assert coordinator.controller_state[state.TIMER] == 3
    frozen = json.loads(
        (Path(__file__).parent / "fixtures/ore_ultramatic/vectors.json").read_text()
    )
    callback(None, bytearray.fromhex(frozen[87]["inputs"]["fragments"][0]))
    assert coordinator.controller_state[state.TIMER] == 3
    callback(None, bytearray(3))
    assert coordinator.controller_state[state.TIMER] == 2
    ctrl.on_disconnect()
    callback(None, bytearray.fromhex("0000000000000005000000000000f300"))
    assert coordinator.controller_state[state.TIMER] is None
    assert ctrl._parser.pending is None


async def test_alarm_report_publishes_valid_time_with_raw_attributes(target):
    coordinator, client = await target("P2")
    callback = client.start_notify.await_args.args[1]
    callback(None, bytearray.fromhex("ed8003071e7f02000000"))
    assert coordinator.controller_state[state.TIME] == "07:30"
    assert coordinator.controller_state[state.REPEAT] == 127
    assert coordinator.controller_state[state.ACTION] == 2
    callback(None, bytearray.fromhex("ed8003631e7f02000000"))  # Hour 99 is no time of day.
    assert coordinator.controller_state[state.TIME] is None


async def test_cancellation_release_and_session_replacement(target):
    coordinator, client = await target("P2")
    ctrl = coordinator.controller

    async def cancel_first(*args, **kwargs):
        if len(client.write_gatt_char.call_args_list) == 1:
            raise asyncio.CancelledError

    client.write_gatt_char.side_effect = cancel_first
    with pytest.raises(asyncio.CancelledError), virtual_clock():
        await ctrl.move_back_up()
    assert _written(client) == ["e6fe16010000000004", "e6fe16000000000005"]
    client.write_gatt_char.reset_mock()

    async def replace_after_first(*args, **kwargs):
        ctrl.on_disconnect()
        replacement = MagicMock(spec=BleakClient)
        replacement.is_connected = True
        replacement.disconnect = AsyncMock()
        coordinator._client = replacement

    client.write_gatt_char.side_effect = replace_after_first
    with pytest.raises(ConnectionError), virtual_clock():
        await ctrl.hold_control("head", 201)
    assert _written(client) == ["e6fe160008000000fd"]


async def test_deadline_counts_elapsed_gatt_time(target):
    coordinator, client = await target("P2")

    async def slow_write(*args, **kwargs):
        await asyncio.sleep(0.15)

    client.write_gatt_char.side_effect = slow_write
    with virtual_clock() as clock:
        began = clock.time()
        await coordinator.controller.hold_control("head", 201)
        assert clock.time() - began < 0.6
    assert _written(client) == ["e6fe160008000000fd", "e6fe16000000000005"]


async def test_setup_configure_and_side_owned_layout(hass):
    from custom_components.adjustable_bed.app_profiles import hidden_generic_fields
    from custom_components.adjustable_bed.config_flow import (
        AdjustableBedConfigFlow,
        AdjustableBedOptionsFlow,
        _per_side_refusal,
    )
    from custom_components.adjustable_bed.detection import bed_type_choice, get_bed_type_options
    from custom_components.adjustable_bed.setup_questions import setup_profile_for
    from tests.form_helpers import finish_new_bed, start_new_bed

    choice = bed_type_choice("keeson", APP)
    assert (
        "ORE Ultramatic" in {row["value"]: row["label"] for row in get_bed_type_options()}[choice]
    )
    flow = AdjustableBedConfigFlow()
    flow.hass, flow.context = hass, {}
    flow._finish_with_verify = AsyncMock(return_value={"type": "create_entry"})
    form = await start_new_bed(flow, "typed", choice, "AA:BB:CC:DD:15:80")
    assert form["step_id"] == "profile_questions"
    await finish_new_bed(
        flow, await flow.async_step_profile_questions({const.CONF_MOTOR_COUNT: "4"})
    )
    saved = flow._finish_with_verify.await_args.args[0]
    assert (
        saved[const.CONF_BED_TYPE],
        saved[const.CONF_PROTOCOL_VARIANT],
        saved[const.CONF_MOTOR_COUNT],
    ) == ("keeson", APP, 4)
    assert setup_profile_for(saved) is not None
    assert const.CONF_HAS_MASSAGE in hidden_generic_fields("keeson", APP)
    assert _per_side_refusal(
        ("keeson", APP), [("keeson", APP)] * 2, {const.CONF_MOTOR_COUNT: 3}
    ) == (const.CONF_MOTOR_COUNT, "ORE Ultramatic")
    entry = _entry(hass, APP, 2, "AA:BB:CC:DD:15:81")
    options = AdjustableBedOptionsFlow(entry)
    options.hass, options.handler = hass, entry.entry_id
    form = await options.async_step_settings()
    assert form["type"] == "form"
    result = await options.async_step_settings({const.CONF_MOTOR_COUNT: 3})
    if result["type"] == "form":
        result = await options.async_step_profile_questions({const.CONF_MOTOR_COUNT: "3"})
    assert result["type"] == "create_entry"
    assert entry.data[const.CONF_MOTOR_COUNT] == 3


COMMANDS = json.loads((Path(__file__).parent / "fixtures/ore_ultramatic/commands.json").read_text())


@pytest.mark.parametrize(
    "route,row",
    [(route, row) for route, rows in COMMANDS.items() for row in rows],
    ids=lambda item: item["action"] if isinstance(item, dict) else item,
)
async def test_all61_accepted_command_callers(target, route, row):
    from custom_components.adjustable_bed.profiles.keeson import encode

    count = (
        int(row.get("variants", ["bedding2"])[0][-1])
        if row.get("variants", [""])[0].startswith("bedding")
        else 2
    )
    coordinator, client = await target(route, count)
    ctrl = coordinator.controller
    coordinator._motor_pulse_count = 1
    action = row["action"]
    with virtual_clock():
        if action.endswith(("_up", "_down")):
            axis, direction = action.rsplit("_", 1)
            axis = {"foot": "feet", "combined_back_foot": "both"}.get(axis, axis)
            await ctrl._move_axis(axis, direction == "up")
        elif action == "release_stop":
            await ctrl.stop_all()
        elif action.startswith(("recall_", "preset_", "save_")):
            verb, name = action.split("_", 1)
            name = {
                "M1": "memory_1",
                "M2": "memory_2",
                "ZG": "zero_g",
                "Flat": "flat",
                "TV": "tv",
                "Anti_Snore": "anti_snore",
            }[name]
            await (ctrl._save(name) if verb == "save" else ctrl._preset(name))
        elif action in ("massage_wave", "massage_head_intensity", "massage_foot_intensity"):
            for level in range(4):
                await ctrl.set_massage_level(action.split("_")[1], level)
        elif action.startswith("massage_timer_") and route == "P1":
            await ctrl.set_massage_timer_option(action.split("_")[2].removesuffix("min"))
        elif action == "massage_start":
            await ctrl.massage_start()
        elif action == "massage_stop":
            await ctrl.massage_off()
        elif action.startswith("massage_"):
            key = action.removeprefix("massage_").removesuffix("_button")
            await ctrl.hold_control(key, 1)
        elif action == "underbed_light_on":
            await ctrl.lights_on()
        elif action == "underbed_light_off":
            await ctrl.lights_off()
        elif action == "underbed_light_toggle":
            await ctrl.lights_toggle()
        elif action == "alarm_query":
            await ctrl.query_alarm()
        elif action == "set_current_time":
            await ctrl.sync_clock()
        else:
            assert action in ("alarm_enable", "alarm_disable")
            await ctrl.set_alarm(
                enabled=action == "alarm_enable", hour=7, minute=30, repeat=128, kind=1
            )
    written = _written(client)
    assert written, action
    if row.get("key") is not None:
        expected = bytes.fromhex(row["bytes"]).hex()
        assert written[0] == expected
        held = "repeat_interval_ms" in row["timing"]
        assert written == ([expected, encode(app.profile(route), 0).hex()] if held else [expected])


async def test_real_paired_device_target_and_whole_target_rejection(hass, target):
    from homeassistant.config_entries import ConfigEntryState
    from homeassistant.helpers import device_registry as dr
    from pytest_homeassistant.common import MockConfigEntry

    from custom_components.adjustable_bed.paired_coordinator import PairedBedCoordinator

    left, lc = await target("P1", address="AA:BB:CC:DD:15:82")
    right, rc = await target("P2", address="AA:BB:CC:DD:15:83")
    entry = MockConfigEntry(
        domain=const.DOMAIN, data={"pair_id": "ultramatic158"}, state=ConfigEntryState.LOADED
    )
    entry.add_to_hass(hass)
    pair = PairedBedCoordinator(
        hass, entry, {"left": left, "right": right}, connection_mode="concurrent"
    )
    hass.data[const.DOMAIN][entry.entry_id] = pair
    registry = dr.async_get(hass)
    device = registry.async_get_or_create(
        config_entry_id=entry.entry_id, identifiers={(const.DOMAIN, right.address)}
    )
    await async_register_services(hass)
    with virtual_clock():
        await hass.services.async_call(
            const.DOMAIN,
            "ore_ultramatic_set_alarm",
            {"device_id": device.id, "enabled": False, "time": "00:00:00"},
            blocking=True,
        )
    assert not lc.write_gatt_char.called
    assert _written(rc)[-1] == "e28003009a"
    before = len(_written(rc))
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            const.DOMAIN,
            "ore_ultramatic_set_alarm",
            {"device_id": device.id, "side": "left", "enabled": False, "time": "00:00:00"},
            blocking=True,
        )
    assert len(_written(rc)) == before
    # Admission validates both targets before any requested write.
    with (
        patch(
            "custom_components.adjustable_bed.services._resolve_sided_targets",
            return_value=([(pair, "both")], []),
        ),
        virtual_clock(),
        pytest.raises(ServiceValidationError),
    ):
        await hass.services.async_call(
            const.DOMAIN, "goto_preset", {"device_id": "parent", "preset": 1}, blocking=True
        )
    assert not lc.write_gatt_char.called
    await pair.async_shutdown()


async def test_registered_renewable_hold_extends_deadline(hass, target):
    coordinator, client = await target("P2")
    coordinator._motor_pulse_count = 1
    await async_register_services(hass)
    data = {
        "device_id": "bed",
        "control": "head",
        "duration": 0.1,
        "hold_owner": "card",
        "hold_generation": 1,
    }
    first = asyncio.Event()

    async def wrote(*args, **kwargs):
        first.set()

    client.write_gatt_char.side_effect = wrote

    async def call():
        await hass.services.async_call(const.DOMAIN, "hold_control", data, blocking=True)

    with (
        patch(
            "custom_components.adjustable_bed.services._resolve_sided_targets",
            return_value=([(coordinator, "both")], []),
        ),
        virtual_clock(),
    ):
        task = asyncio.create_task(call())
        await first.wait()
        for _ in range(5):
            await asyncio.sleep(0.05)
            await call()
        await task
    frames = _written(client)
    assert frames.count("e6fe160008000000fd") >= 3
    assert frames[-1] == "e6fe16000000000005"
