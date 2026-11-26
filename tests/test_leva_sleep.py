"""Leva Sleep 1.0.2 frozen literals and Home Assistant command paths."""

from __future__ import annotations

import asyncio
import json
from contextlib import nullcontext
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bleak.backends.device import BLEDevice
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import async_get_platforms

from custom_components.adjustable_bed import const, services
from custom_components.adjustable_bed.beds.ore_ultramatic import state_keys as state
from custom_components.adjustable_bed.beds.ore_ultramatic.controller import OreDualRouteController
from custom_components.adjustable_bed.button import _button_entities_for
from custom_components.adjustable_bed.codec import keeson as codec
from custom_components.adjustable_bed.detection import bed_type_choice, get_bed_type_options
from custom_components.adjustable_bed.pairing import get_child, supports_single_address_pairing
from custom_components.adjustable_bed.profiles import leva_sleep
from custom_components.adjustable_bed.profiles import ore_ultramatic as ore
from custom_components.adjustable_bed.profiles.keeson import encode
from custom_components.adjustable_bed.runtime_data import loaded_runtime
from custom_components.adjustable_bed.services import async_register_services
from tests.hold_lease_wire import virtual_clock
from tests.pair_mode import CONF_PAIR_CONNECTION_MODE
from tests.test_ore_comfort_bed import _char, _entry, _written
from tests.test_ore_ultramatic import target as target
from tests.test_ore_ultramatic_restore import gatt, paired_entry

_APP = const.KEESON_VARIANT_LEVA_SLEEP
_NOW = datetime(2026, 11, 26, 10, 23, 44)
_VECTORS = json.loads((Path(__file__).parent / "fixtures/leva_sleep/vectors.json").read_text())
_BY_ID = {row["id"]: bytes.fromhex(row["expected_bytes"]).hex() for row in _VECTORS}


@pytest.fixture
def mounted_alarm_timing(monkeypatch):
    """Skip the wire delays without virtualizing HA's entity platform timers."""
    write = OreDualRouteController._single_on

    async def immediate(controller, link, frame, delay_ms=0):
        await write(controller, link, frame, 0)

    monkeypatch.setattr(OreDualRouteController, "_single_on", immediate)


@pytest.mark.parametrize("row", _VECTORS, ids=lambda row: row["id"])
def test_frozen_vectors(row):
    route, inputs = row["protocol"], row["inputs"]
    kind = inputs["kind"]
    if kind == "parser":
        parser = codec.LevaSleepParser()
        parser.state.type = inputs["initial_alarm_type"]
        callbacks: tuple[str, ...] = ()
        for part in inputs["fragments"]:
            callbacks = parser.feed(bytes.fromhex(part))
        expected = row["expected_decoded"]
        if expected is None:
            assert callbacks == ()
            return
        s = parser.state
        if expected["kind"] == "massage":
            assert callbacks == ("massage",)
            assert (s.timer, s.intensity) == (expected["timer"], expected["intensity"])
        else:
            assert callbacks == ("alarm",)
            assert (s.hour, s.minute, s.repeat, s.type) == tuple(
                expected[key] for key in ("hour", "minute", "repeat", "mode")
            )
        return

    match kind:
        case "frame":
            actual = encode(leva_sleep.profile(route), int(inputs["key"], 16))
        case "slider":
            actual = encode(
                leva_sleep.profile(route), int(inputs["base"], 16) + inputs["progress"] // 10
            )
        case "clock":
            actual = codec.clock(_NOW)
        case "query":
            actual = ore.query(route, _NOW)
        case "on" | "off":
            actual = leva_sleep.alarm(
                route,
                _NOW,
                enabled=kind == "on",
                hour=inputs.get("alarm_hour", 0),
                minute=inputs.get("alarm_minute", 0),
                repeat=inputs.get("repeat", 0),
                kind=inputs.get("mode", 0),
            )
        case _:
            pytest.fail(f"Unknown vector kind {kind}")
    assert actual.hex() == _BY_ID[row["id"]]


def test_alarm_branches_keep_separate_caches_and_signed_fields():
    parser = codec.LevaSleepParser()
    status = bytes.fromhex("ed8003062380ff")
    query = bytes.fromhex("e2fe16290a0083ffff09")
    assert parser.feed(status) == ("alarm",)
    assert (parser.state.repeat, parser.state.type) == (-128, -1)
    assert parser.feed(query) == ("alarm",)
    assert parser.feed(query) == ("alarm",)
    assert parser.feed(status) == ()
    assert (parser.state.hour, parser.state.minute, parser.state.type) == (10, 41, 3)
    assert parser.feed(status[:-1]) == ()
    assert parser.feed(query[:-1]) == ()
    assert parser.feed(bytes.fromhex("ed800300000000")) == ("alarm",)
    assert (parser.state.hour, parser.state.minute, parser.state.repeat, parser.state.type) == (
        0,
        0,
        0,
        0,
    )
    assert parser.feed(bytes.fromhex("f4fe16") + bytes(17)) == ("massage",)


@pytest.mark.parametrize("raw_type", (-1, 17))
def test_received_p2_mode_is_not_an_outgoing_wake_choice(raw_type):
    assert (
        leva_sleep.alarm(
            "P2", _NOW, enabled=True, hour=6, minute=35, repeat=131, kind=raw_type
        ).hex()
        == _BY_ID["V77"]
    )


@pytest.mark.parametrize(
    "route, count, axes, first, stop",
    [
        ("P1", 2, ("back", "feet", "both"), "V05", "V13"),
        ("P1", 3, ("back", "feet", "head"), "V07", "V13"),
        ("P1", 4, ("back", "feet", "waist", "lumbar"), "V11", "V13"),
        ("P2", 2, ("back", "feet", "both"), "V18", "V26"),
        ("P2", 3, ("back", "feet", "head"), "V20", "V26"),
        ("P2", 4, ("back", "feet", "waist", "lumbar"), "V24", "V26"),
    ],
)
async def test_live_route_and_layout(target, route, count, axes, first, stop):
    coordinator, client = await target(route, count, variant=_APP)
    controller = coordinator.controller
    assert controller.capability_snapshot() == {"leva_sleep_route": route}
    assert controller.execution.hold == "stream" and not controller.execution.concurrent
    assert tuple(s.key for s in controller.motor_control_specs) == axes
    assert controller.memory_slot_count == 2
    assert controller.supports_memory_programming == (route == "P1")
    assert controller.supports_discrete_light_control == (route == "P1")
    assert controller.supports_light_toggle_control == (route == "P2")
    assert bool(controller.controller_number_specs) == (route == "P1")
    assert not controller.supports_preset_tv and not controller.supports_preset_anti_snore
    assert controller.supports_memory_recall_duration(2) == (route == "P2")
    coordinator._motor_pulse_count = 2
    with virtual_clock():
        await coordinator.async_execute_controller_command(
            controller.motor_control_specs[-1].open_fn
        )
    assert _written(client) == [_BY_ID[first]] * 2 + [_BY_ID[stop]]


async def test_memory_buttons_and_massage_actions(hass, target):
    coordinator, client = await target("P2", variant=_APP)
    controller = coordinator.controller
    buttons = _button_entities_for(hass, coordinator)
    assert any(e.unique_id.endswith("preset_memory_2") for e in buttons)
    assert not any(e.unique_id.endswith("program_memory_1") for e in buttons)
    assert controller.standard_button_hold_spec("preset_memory_2") is not None
    with virtual_clock():
        await coordinator.async_execute_controller_command(
            lambda c: c.recall_memory(2, hold_ms=201)
        )
        await coordinator.async_execute_controller_command(lambda c: c.hold_control("head", 1))
        await coordinator.async_execute_controller_command(lambda c: c.lights_toggle())
    assert _written(client) == [_BY_ID["V35"]] * 3 + [
        _BY_ID[key] for key in ("V26", "V44", "V26", "V41")
    ]
    with pytest.raises(ValueError):
        await controller.program_memory(2)


async def test_p1_discrete_controls(target):
    coordinator, client = await target("P1", variant=_APP)
    with virtual_clock():
        for control in (
            lambda c: c.preset_memory(1),
            lambda c: c.preset_memory(1),
            lambda c: c.program_memory(2),
            lambda c: c.massage_start(),
            lambda c: c.set_massage_level("wave", 3),
            lambda c: c.set_massage_timer(30),
            lambda c: c.massage_off(),
            lambda c: c.lights_on(),
            lambda c: c.lights_off(),
        ):
            await coordinator.async_execute_controller_command(control)
    assert _written(client) == [
        _BY_ID[key]
        for key in (
            "V30",
            "V13",
            "V34",
            "V59",
            "V60",
            "V61",
            "V50",
            "V66",
            "V62",
            "V63",
            "V39",
            "V40",
        )
    ]


@pytest.mark.parametrize("route", ("P1", "P2"))
async def test_registered_alarm_sequence(hass, target, route):
    coordinator, client = await target(route, variant=_APP)
    await async_register_services(hass)
    with (
        patch(
            "custom_components.adjustable_bed.beds.ore_ultramatic.controller.dt_util.now",
            return_value=_NOW,
        ),
        patch(
            "custom_components.adjustable_bed.services._resolve_sided_targets",
            return_value=([(coordinator, "both")], []),
        ),
        virtual_clock() as clock,
    ):
        started = clock.time()
        await hass.services.async_call(
            const.DOMAIN,
            "set_alarm",
            {
                "device_id": "bed",
                "enabled": True,
                "time": "06:35:00",
                "weekdays": ["sunday", "monday"],
                "wake_action": "memory_1",
            },
            blocking=True,
        )
        assert clock.time() - started == pytest.approx(0.3 if route == "P1" else 0.4)
    expected = ("V71", "V67") if route == "P1" else ("V76", "V79", "V74")
    assert _written(client) == [_BY_ID[k] for k in expected]


async def test_route_rediscovery_waits_for_alarm_and_link_release(
    hass,
    enable_custom_integrations,
    mock_coordinator_connected,
    mock_bleak_client,
):
    gatt(mock_bleak_client, "P1")
    entry = _entry(hass, _APP, 2)
    hass.config_entries.async_update_entry(
        entry,
        data={**entry.data, "capabilities": {"keeson": {"leva_sleep_route": "P1"}}},
    )
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    coordinator = loaded_runtime(hass, entry.entry_id)
    assert coordinator is not None
    await coordinator.async_disconnect()
    mock_bleak_client.write_gatt_char.reset_mock()
    gatt(mock_bleak_client, "P2")
    registry = dr.async_get(hass)
    (device,) = dr.async_entries_for_config_entry(registry, entry.entry_id)

    with (
        patch(
            "custom_components.adjustable_bed.beds.ore_ultramatic.controller.dt_util.now",
            return_value=_NOW,
        ),
        virtual_clock(),
    ):
        await hass.services.async_call(
            const.DOMAIN,
            "set_alarm",
            {
                "device_id": device.id,
                "enabled": True,
                "time": "06:35:00",
                "weekdays": ["sunday", "monday"],
                "wake_action": "memory_1",
            },
            blocking=True,
        )
    await hass.async_block_till_done()
    assert _written(mock_bleak_client) == [_BY_ID[k] for k in ("V76", "V79", "V74")]
    assert entry.data["capabilities"]["keeson"] == {"leva_sleep_route": "P2"}
    assert loaded_runtime(hass, entry.entry_id) is coordinator

    await coordinator.async_disconnect()
    await hass.async_block_till_done()
    reloaded = loaded_runtime(hass, entry.entry_id)
    assert reloaded is not None and reloaded is not coordinator
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


@pytest.mark.parametrize(
    ("validation_route", "write_route", "collides", "frames"),
    [
        ("P2", "P2", False, ("V76", "V79", "V74")),
        ("P2", "P1", False, ("V71", "V67")),
        ("P1", "P2", True, ()),
    ],
)
async def test_sequential_alarm_rediscovery_defers_reload_until_the_write_cycle(
    hass,
    enable_custom_integrations,
    mock_coordinator_connected,
    mock_bleak_client,
    mock_establish_connection,
    mock_async_ble_device_from_address,
    mounted_alarm_timing,
    validation_route,
    write_route,
    collides,
    frames,
):
    mock_async_ble_device_from_address.side_effect = lambda _hass, address, **_kwargs: BLEDevice(
        address, "Test Bed", {"source": "local"}
    )
    entry = paired_entry(
        hass, variant=_APP, right_capabilities={"keeson": {"leva_sleep_route": "P1"}}
    )
    hass.config_entries.async_update_entry(
        entry, data={**entry.data, CONF_PAIR_CONNECTION_MODE: const.PAIR_CONNECTION_MODE_SEQUENTIAL}
    )
    gatt(mock_bleak_client, "P1")
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    pair = loaded_runtime(hass, entry.entry_id)
    assert pair.connection_mode == const.PAIR_CONNECTION_MODE_SEQUENTIAL
    right = pair.child_for_side(const.SIDE_RIGHT)
    assert not pair.is_connected
    assert right.capability_controller.capability_snapshot() == {"leva_sleep_route": "P1"}
    device = dr.async_get(hass).async_get_child_device_by_identifier(
        (const.DOMAIN, right.address), entry.entry_id
    )
    assert device is not None
    gatt(mock_bleak_client, "P2")
    mock_bleak_client.write_gatt_char.reset_mock()

    releases = []
    connects = []

    async def disconnect():
        if loaded_runtime(hass, entry.entry_id) is pair:
            releases.append(mock_bleak_client.write_gatt_char.await_count)
        mock_bleak_client.is_connected = False

    async def connect(_cls, ble_device, _name, **_kwargs):
        assert not mock_bleak_client.is_connected
        route = write_route
        if loaded_runtime(hass, entry.entry_id) is pair:
            if not connects:
                route = validation_route
            connects.append(ble_device.address)
        gatt(mock_bleak_client, route if ble_device.address == right.address else "P1")
        mock_bleak_client.is_connected = True
        return mock_bleak_client

    mock_bleak_client.disconnect.side_effect = disconnect
    mock_establish_connection.side_effect = connect
    alarm_data = (
        {"time": "00:00:00", "wake_action": "none"}
        if collides
        else {"time": "06:35:00", "weekdays": ["sunday", "monday"], "wake_action": "memory_1"}
    )
    with (
        patch(
            "custom_components.adjustable_bed.beds.ore_ultramatic.controller.dt_util.now",
            return_value=_NOW,
        ),
        pytest.raises(ServiceValidationError) if collides else nullcontext() as error,
    ):
        await hass.services.async_call(
            const.DOMAIN,
            "set_alarm",
            {
                "device_id": device.id,
                "enabled": True,
                **alarm_data,
            },
            blocking=True,
        )
    await hass.async_block_till_done()
    assert connects == [right.address, right.address]
    if error is not None:
        assert error.value.translation_key == "alarm_midnight_requires_action_or_repeat"
    assert releases == [0, len(frames)]
    assert _written(mock_bleak_client) == [_BY_ID[k] for k in frames]
    assert get_child(entry.data, const.SIDE_RIGHT)["capabilities"]["keeson"] == {
        "leva_sleep_route": write_route
    }
    assert get_child(entry.data, const.SIDE_LEFT)["capabilities"]["keeson"] == {
        "ultramatic_route": "P1"
    }
    assert loaded_runtime(hass, entry.entry_id) is not pair
    registry = er.async_get(hass)
    massage = registry.async_get_entity_id(
        "button", const.DOMAIN, f"{right.address}_ore_ultramatic_massage_head"
    )
    assert bool(massage) == (write_route == "P2")
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


async def test_always_connected_reconciles_route_entities_after_alarm(
    hass,
    enable_custom_integrations,
    mock_coordinator_connected,
    mock_bleak_client,
    mounted_alarm_timing,
):
    gatt(mock_bleak_client, "P1")
    entry = _entry(hass, _APP, 2)
    hass.config_entries.async_update_entry(
        entry,
        data={
            **entry.data,
            const.CONF_CONNECTION_MODE: const.CONNECTION_MODE_ALWAYS,
            const.CONF_IDLE_DISCONNECT_SECONDS: const.IDLE_DISCONNECT_KEEP_CONNECTED,
            "capabilities": {"keeson": {"leva_sleep_route": "P1"}},
        },
    )
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    coordinator = loaded_runtime(hass, entry.entry_id)
    assert coordinator.connection_settings["mode"] == const.CONNECTION_MODE_ALWAYS
    await coordinator.async_disconnect()
    gatt(mock_bleak_client, "P2")
    mock_bleak_client.disconnect.reset_mock()
    mock_bleak_client.write_gatt_char.reset_mock()
    (device,) = dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)
    registry = er.async_get(hass)
    (buttons,) = [
        platform
        for platform in async_get_platforms(hass, const.DOMAIN)
        if platform.domain == "button"
    ]
    presets = {}
    for control in ("preset_flat", "preset_zero_g"):
        entity_id = registry.async_get_entity_id(
            "button", const.DOMAIN, coordinator.entity_unique_id(control)
        )
        assert entity_id is not None
        presets[control] = registry.async_get(entity_id), buttons.entities[entity_id]

    def assert_presets(*, held):
        for control, (row, entity) in presets.items():
            assert registry.async_get(row.entity_id).id == row.id
            assert buttons.entities[row.entity_id] is entity
            attrs = hass.states.get(row.entity_id).attributes
            if held:
                assert attrs["held_control"] == control
                assert attrs["hold_release_delay_ms"] == ore.SINGLE_MS
                assert attrs["hold_lease_mode"] == "stream"
            else:
                assert {"held_control", "hold_release_delay_ms", "hold_lease_mode"}.isdisjoint(
                    attrs
                )

    assert_presets(held=False)
    program = coordinator.entity_unique_id("ore_comfort_program_flat")
    massage = coordinator.entity_unique_id("ore_ultramatic_massage_head")
    light = coordinator.entity_unique_id("under_bed_lights")
    entered, finish = asyncio.Event(), asyncio.Event()

    async def write(_char, data, **_kwargs):
        if data.hex() == _BY_ID["V74"]:
            entered.set()
            await finish.wait()

    mock_bleak_client.write_gatt_char.side_effect = write
    with patch(
        "custom_components.adjustable_bed.beds.ore_ultramatic.controller.dt_util.now",
        return_value=_NOW,
    ):
        alarm = asyncio.create_task(
            hass.services.async_call(
                const.DOMAIN,
                "set_alarm",
                {
                    "device_id": device.id,
                    "enabled": True,
                    "time": "06:35:00",
                    "weekdays": ["sunday", "monday"],
                    "wake_action": "memory_1",
                },
                blocking=True,
            )
        )
        in_flight = asyncio.create_task(entered.wait())
        try:
            await asyncio.wait((alarm, in_flight), return_when=asyncio.FIRST_COMPLETED)
            assert entered.is_set()
            current = coordinator.controller
            channel, receive = mock_bleak_client.start_notify.await_args.args
            receive(channel, bytearray.fromhex("ed800306238311"))
            await asyncio.sleep(0)
            assert registry.async_get_entity_id("button", const.DOMAIN, program)
            assert registry.async_get_entity_id("light", const.DOMAIN, light)
            assert not registry.async_get_entity_id("button", const.DOMAIN, massage)
            assert_presets(held=False)
        finally:
            in_flight.cancel()
            finish.set()
            await alarm

    await hass.async_block_till_done()
    assert _written(mock_bleak_client) == [_BY_ID[k] for k in ("V76", "V79", "V74")]
    mock_bleak_client.disconnect.assert_not_awaited()
    assert loaded_runtime(hass, entry.entry_id) is coordinator
    assert coordinator.is_connected and coordinator.controller is current
    assert coordinator.capability_controller.capability_snapshot() == {"leva_sleep_route": "P2"}
    assert registry.async_get_entity_id("button", const.DOMAIN, massage)
    assert not registry.async_get_entity_id("button", const.DOMAIN, program)
    assert not registry.async_get_entity_id("light", const.DOMAIN, light)
    assert_presets(held=True)

    await coordinator.async_disconnect()
    gatt(mock_bleak_client, "P1")
    assert await coordinator.async_connect()
    await hass.async_block_till_done()
    assert loaded_runtime(hass, entry.entry_id) is coordinator
    assert_presets(held=False)
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


@pytest.mark.parametrize("live_route", ("P1", "P2"))
async def test_midnight_alarm_during_reconnect_waits_for_live_route(
    hass,
    enable_custom_integrations,
    mock_coordinator_connected,
    mock_bleak_client,
    mounted_alarm_timing,
    live_route,
):
    gatt(mock_bleak_client, "P2")
    entry = _entry(hass, _APP, 2)
    hass.config_entries.async_update_entry(
        entry, data={**entry.data, "capabilities": {"keeson": {"leva_sleep_route": "P2"}}}
    )
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    coordinator = loaded_runtime(hass, entry.entry_id)
    await coordinator.async_disconnect()
    assert coordinator.capability_controller.capability_snapshot() == {"leva_sleep_route": "P2"}
    gatt(mock_bleak_client, live_route)
    mock_bleak_client.write_gatt_char.reset_mock()
    (device,) = dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)
    discovery_started, finish_discovery, admitted = (asyncio.Event() for _ in range(3))

    async def discover_services(_client, _address):
        discovery_started.set()
        await finish_discovery.wait()
        return True

    write_checked_alarms = services._write_checked_alarms

    async def after_preflight(*args):
        admitted.set()
        return await write_checked_alarms(*args)

    with (
        patch(
            "custom_components.adjustable_bed.beds.ore_ultramatic.controller.dt_util.now",
            return_value=_NOW,
        ),
        patch(
            "custom_components.adjustable_bed.coordinator_connection.discover_services",
            discover_services,
        ),
        patch.object(services, "_write_checked_alarms", after_preflight),
    ):
        reconnect = asyncio.create_task(coordinator.async_connect())
        try:
            await discovery_started.wait()
            assert mock_bleak_client.is_connected and coordinator.controller is None
            alarm = asyncio.create_task(
                hass.services.async_call(
                    const.DOMAIN,
                    "set_alarm",
                    {
                        "device_id": device.id,
                        "enabled": True,
                        "time": "00:00:00",
                        "wake_action": "none",
                    },
                    blocking=True,
                )
            )
            admission = asyncio.create_task(admitted.wait())
            try:
                await asyncio.wait((alarm, admission), return_when=asyncio.FIRST_COMPLETED)
                if alarm.done():
                    await alarm
                    pytest.fail("Alarm finished before live GATT discovery")
                mock_bleak_client.write_gatt_char.assert_not_awaited()
            finally:
                admission.cancel()
                finish_discovery.set()
            assert await reconnect
            if live_route == "P1":
                await alarm
                assert _written(mock_bleak_client) == [
                    "ebfe162c170a00000400ffffffb2",
                    _BY_ID["V67"],
                ]
            else:
                with pytest.raises(ServiceValidationError) as error:
                    await alarm
                assert error.value.translation_key == "alarm_midnight_requires_action_or_repeat"
                mock_bleak_client.write_gatt_char.assert_not_awaited()
        finally:
            finish_discovery.set()
            await reconnect
    assert entry.data["capabilities"]["keeson"] == {"leva_sleep_route": live_route}
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


@pytest.mark.parametrize("weekdays", ({}, {"weekdays": []}))
async def test_p2_midnight_alarm_rejects_disable_record(hass, target, weekdays):
    coordinator, client = await target("P2", variant=_APP)
    await async_register_services(hass)

    with (
        patch(
            "custom_components.adjustable_bed.services._resolve_sided_targets",
            return_value=([(coordinator, "both")], []),
        ),
        virtual_clock(),
        pytest.raises(ServiceValidationError) as error,
    ):
        await hass.services.async_call(
            const.DOMAIN,
            "set_alarm",
            {
                "device_id": "bed",
                "enabled": True,
                "time": "00:00:00",
                "wake_action": "none",
                **weekdays,
            },
            blocking=True,
        )
    assert error.value.translation_key == "alarm_midnight_requires_action_or_repeat"
    client.write_gatt_char.assert_not_awaited()


async def test_first_p2_disabled_status_updates_alarm_once(target):
    coordinator, client = await target("P2", variant=_APP)
    controller = coordinator.controller
    notify, callback = client.start_notify.await_args.args
    disabled = bytearray.fromhex("ed800300000000")
    assert coordinator.controller_state.get(state.ALARM_ENABLED) is None

    callback(notify, disabled[:-1])
    assert coordinator.controller_state.get(state.ALARM_ENABLED) is None
    with patch.object(
        controller,
        "forward_controller_state_updates",
        wraps=controller.forward_controller_state_updates,
    ) as updates:
        callback(notify, disabled)
        assert coordinator.controller_state[state.ALARM_ENABLED] is False
        callback(notify, disabled)
        updates.assert_called_once()


async def test_subscription_roles_and_link_scoped_cancellation(target):
    coordinator, client = await target("P2", variant=_APP)
    controller = coordinator.controller
    old_callback = client.start_notify.await_args.args[1]
    await controller.stop_notify()
    notify = _char(ore.NOTIFY, ["notify"])
    write = _char(ore.WRITE, ["write"])
    client.services += [
        SimpleNamespace(uuid=ore.SELECTOR.upper(), characteristics=[]),
        SimpleNamespace(uuid="other", characteristics=[write]),
        SimpleNamespace(uuid="another", characteristics=[notify]),
    ]
    await controller.start_notify()
    assert [c.args[0] for c in client.start_notify.await_args_list][-2:] == [
        client.services[0].characteristics[1],
        notify,
    ]
    assert controller.capability_snapshot() == {"leva_sleep_route": "P1"}
    old_callback(notify, bytearray.fromhex("ed8003062380ff"))
    assert coordinator.controller_state[state.ACTION] is None
    callback = client.start_notify.await_args.args[1]
    callback(notify, bytearray.fromhex("e2fe1623060083ffff09"))
    assert coordinator.controller_state[state.ALARM_ENABLED] is True
    assert coordinator.controller_state[state.ACTION] == 3

    async def cancel_first(*_args, **_kwargs):
        if client.write_gatt_char.await_count == 1:
            raise asyncio.CancelledError

    client.write_gatt_char.side_effect = cancel_first
    with pytest.raises(asyncio.CancelledError), virtual_clock():
        await controller.move_back_up()
    assert _written(client) == [_BY_ID["V01"], _BY_ID["V13"]]
    assert all(call.args[0] is write for call in client.write_gatt_char.await_args_list)
    assert all(call.kwargs["response"] for call in client.write_gatt_char.await_args_list)


async def test_old_hold_cannot_write_to_replacement_link(target):
    coordinator, client = await target("P2", variant=_APP)
    controller = coordinator.controller
    replacement = MagicMock(spec=client._spec_class)
    replacement.is_connected = True
    replacement.services = client.services
    replacement.start_notify = AsyncMock()
    replacement.write_gatt_char = AsyncMock()
    replacement.disconnect = AsyncMock()

    async def replace_link(*_args, **_kwargs):
        controller.on_disconnect()
        coordinator._client = replacement

    client.write_gatt_char.side_effect = replace_link
    with pytest.raises(ConnectionError), virtual_clock():
        await controller.hold_preset("memory_1", 201)
    assert _written(client) == [_BY_ID["V32"]]
    replacement.write_gatt_char.assert_not_awaited()


def test_explicit_setup_and_pair_ownership():
    from custom_components.adjustable_bed.app_profiles import per_side_profile
    from custom_components.adjustable_bed.setup_questions import setup_profile_for

    choice = bed_type_choice(const.BED_TYPE_KEESON, _APP)
    options = {row["value"]: row["label"] for row in get_bed_type_options()}
    assert "Leva Sleep app" in options[choice]
    assert "Leva Bed Remote" in options[const.BED_TYPE_LEVA]
    assert not supports_single_address_pairing(const.BED_TYPE_KEESON, _APP)
    side = per_side_profile(const.BED_TYPE_KEESON, _APP)
    assert const.CONF_MOTOR_COUNT in side.keys
    setup = setup_profile_for(
        {const.CONF_BED_TYPE: const.BED_TYPE_KEESON, const.CONF_PROTOCOL_VARIANT: _APP}
    )
    assert const.CONF_MOTOR_COUNT in {q.key for q in setup.questions}
