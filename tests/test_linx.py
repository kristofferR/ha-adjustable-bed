"""Linx through HA setup, entities, coordinator, services and paired targets."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bleak.exc import BleakError
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import ServiceCall
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed.app_profiles import per_side_profile
from custom_components.adjustable_bed.bed_traits import reads_positions
from custom_components.adjustable_bed.beds.linx import controller as ctrl
from custom_components.adjustable_bed.button import ControllerActionButton
from custom_components.adjustable_bed.codec import linx as codec
from custom_components.adjustable_bed.const import (
    CONF_BED_TYPE,
    CONF_BLE_DEVICE_NAME,
    CONF_PAIR_ID,
    CONF_PRODUCT_TYPE,
    CONF_PROTOCOL_VARIANT,
    DOMAIN,
)
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.paired_coordinator import PairedBedCoordinator
from custom_components.adjustable_bed.paired_devices import child_device_info
from custom_components.adjustable_bed.profile_id import resolve_profile_id
from custom_components.adjustable_bed.profiles import linx as app
from custom_components.adjustable_bed.services import async_register_services, handle_timed_move
from custom_components.adjustable_bed.setup_questions import setup_profile_for
from tests.form_helpers import complete, form_fields
from tests.hold_lease_wire import virtual_clock
from tests.test_controller_contract import _FactoryCoordinator
from tests.test_setup_routes import _typed

NAME = "KSWF07D00000000"


class _Characteristic:
    def __init__(self, uuid, properties, handle):
        self.uuid, self.properties, self.handle = uuid, properties, handle
        self.descriptors = ()

    def __str__(self):
        return self.uuid


class _Service:
    def __init__(self, transport):
        self.uuid = transport.service
        self.characteristics = [
            _Characteristic(transport.write, ["write"], 1),
            _Characteristic(transport.notify, [transport.subscription], 2),
        ]

    def get_characteristic(self, uuid):
        return next((c for c in self.characteristics if c.uuid == uuid), None)


class _Services(list):
    def get_service(self, uuid):
        return next((s for s in self if s.uuid == uuid), None)

    def get_characteristic(self, uuid):
        return next((c for s in self for c in s.characteristics if c.uuid == uuid), None)


def gatt():
    return _Services(_Service(transport) for transport in codec.TRANSPORTS.values())


@pytest.fixture(autouse=True)
async def cleanup(hass, monkeypatch):
    monkeypatch.setattr(app, "CONNECT_SETTLE_MS", 0)
    yield
    for coord in hass.data.get("linx_test_targets", []):
        await coord.async_shutdown()


async def target(hass, model="quest", route="a00a"):
    targets = hass.data.setdefault("linx_test_targets", [])
    address = f"AA:BB:CC:79:00:{len(targets) + 1:02X}"
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Linx",
        unique_id=address,
        data={
            CONF_ADDRESS: address,
            CONF_NAME: "Editable display title",
            CONF_BED_TYPE: "linx",
            CONF_PRODUCT_TYPE: model,
            CONF_PROTOCOL_VARIANT: route,
            CONF_BLE_DEVICE_NAME: NAME,
            "motor_count": 2,
            "has_massage": model == "quest",
            "disable_angle_sensing": True,
            "disconnect_after_command": False,
            "idle_disconnect_seconds": 0,
        },
    )
    entry.add_to_hass(hass)
    coord = AdjustableBedCoordinator(hass, entry)
    client = SimpleNamespace(
        is_connected=True,
        services=gatt(),
        write_gatt_char=AsyncMock(),
        start_notify=AsyncMock(),
        stop_notify=AsyncMock(),
        disconnect=AsyncMock(),
    )

    async def disconnect():
        client.is_connected = False

    client.disconnect.side_effect = disconnect
    coord._client = client
    bed = await create_controller(coord, "linx", route, client)
    assert isinstance(bed, ctrl.LinxController)
    coord._controller = coord._offline_controller = bed
    await bed.async_discover_capabilities()
    await bed.start_notify()
    coord._ready = True
    entry.mock_state(hass, ConfigEntryState.LOADED)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coord
    targets.append(coord)
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id, **coord.device_info
    )
    return coord, bed, client, device


def frames(client):
    return [bytes(call.args[1]) for call in client.write_gatt_char.call_args_list]


@pytest.mark.parametrize("model", app.PROFILES)
@pytest.mark.parametrize("route", app.ROUTES)
async def test_real_setup_questions_defaults_factory_and_side_ownership(
    hass, enable_custom_integrations, model, route
):
    result = await _typed(hass, "linx")
    assert result["step_id"] == "profile_questions"
    keys = {str(marker.schema) for marker in form_fields(result["data_schema"])}
    assert {CONF_PRODUCT_TYPE, CONF_PROTOCOL_VARIANT, CONF_BLE_DEVICE_NAME} <= keys
    with (
        patch(
            "custom_components.adjustable_bed.config_flow.AdjustableBedConfigFlow._verification_possible",
            return_value=False,
        ),
        patch("custom_components.adjustable_bed.async_setup_entry", return_value=True),
    ):
        result = await complete(
            hass,
            result,
            {
                "profile_questions": {
                    CONF_PRODUCT_TYPE: model,
                    CONF_PROTOCOL_VARIANT: route,
                    CONF_BLE_DEVICE_NAME: NAME,
                },
                "finish_settings": {CONF_NAME: "Linx"},
            },
        )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    data = result["data"]
    assert data["motor_count"] == 2 and data["has_massage"] == (model == "quest")
    assert not reads_positions(data) and data["motor_pulse_delay_ms"] == 3
    assert data["motor_pulse_count"] == 334 and resolve_profile_id(data) == f"linx:{route}"
    coordinator = _FactoryCoordinator()
    coordinator.entry.data.update(data)
    bed = await create_controller(coordinator, "linx", route, None)
    assert isinstance(bed, ctrl.LinxController) and bed.profile is app.PROFILES[model]
    assert tuple(spec.key for spec in bed.motor_control_specs) == ("head", "feet", "both")
    assert bed.execution.hold == "stream" and not bed.execution.concurrent
    assert not bed.supports_single_address_pairing and not bed.supports_memory_programming
    assert bed.memory_slot_count == (4 if model == "quest" else 0)
    assert bed.supports_preset_anti_snore == (model == "orbes")
    side = per_side_profile("linx", route)
    assert side is not None and side.variant_owned
    assert {CONF_PRODUCT_TYPE, CONF_PROTOCOL_VARIANT, CONF_BLE_DEVICE_NAME} <= side.keys
    profile = setup_profile_for(data)
    assert profile.validate is not None and profile.validate(data) == {}
    assert profile.validate({**data, CONF_PRODUCT_TYPE: "inferred"})
    assert profile.validate({**data, CONF_PROTOCOL_VARIANT: "auto"})
    assert profile.validate({**data, CONF_BLE_DEVICE_NAME: ""})


@pytest.mark.parametrize("model", app.PROFILES)
@pytest.mark.parametrize("route", app.ROUTES)
async def test_actual_import_and_coordinator_startup(
    hass,
    mock_coordinator_connected,
    mock_bleak_client,
    mock_async_ble_device_from_address,
    model,
    route,
):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_ADDRESS: "AA:BB:CC:DD:EE:FF",
            CONF_NAME: "Linx",
            CONF_BED_TYPE: "linx",
            CONF_PRODUCT_TYPE: model,
            CONF_PROTOCOL_VARIANT: route,
            CONF_BLE_DEVICE_NAME: NAME,
            "disable_angle_sensing": True,
        },
    )
    entry.add_to_hass(hass)
    mock_bleak_client.services = gatt()
    mock_async_ble_device_from_address.return_value.name = NAME
    coordinator = AdjustableBedCoordinator(hass, entry)
    hass.data.setdefault("linx_test_targets", []).append(coordinator)
    assert await coordinator.async_connect()
    bed = coordinator.controller
    assert isinstance(bed, ctrl.LinxController)
    assert bed._notifying
    sent = frames(mock_bleak_client)
    assert sent[-2:] == [
        codec.startup_query(NAME)
        if app.ROUTES[route].event_transport == "uart"
        else codec.request(NAME, 4, {"sw": 1}),
        codec.request(NAME, 7, {"bedmd": 100}),
    ]
    for call in mock_bleak_client.write_gatt_char.call_args_list[-2:]:
        assert call.args[0].uuid == codec.TRANSPORTS[app.ROUTES[route].event_transport].write


@pytest.mark.parametrize("model", app.PROFILES)
@pytest.mark.parametrize("route", codec.TRANSPORTS)
async def test_entity_controls_keep_ui_gates_and_literal_route(hass, model, route):
    coord, bed, client, _ = await target(hass, model, route)
    for preset, word in app.PRESETS.items():
        await coord.async_execute_controller_command(
            lambda c, preset=preset: getattr(c, f"preset_{preset}")()
        )
        assert frames(client)[-1] == codec.control(NAME, word)
    await coord.async_execute_controller_command(lambda c: c.lights_toggle())
    assert frames(client)[-1] == codec.control(NAME, app.LIGHT)
    if model == "quest":
        for slot, word in app.MEMORY.items():
            await coord.async_execute_controller_command(lambda c, slot=slot: c.preset_memory(slot))
            assert frames(client)[-1] == codec.control(NAME, word)
        await coord.async_execute_controller_command(lambda c: c.massage_mode_step())
        assert frames(client)[-1] == codec.control(NAME, app.MASSAGE["mode"])
        for spec in bed.controller_button_specs:
            if spec.key.startswith("linx_massage_"):
                button = ControllerActionButton(coord, spec)
                button.hass = hass
                await button.async_press()
                assert frames(client)[-1] == codec.control(
                    NAME, app.MASSAGE[spec.key.removeprefix("linx_massage_")]
                )
    else:
        await coord.async_execute_controller_command(lambda c: c.preset_anti_snore())
        assert frames(client)[-1] == codec.control(NAME, app.MEMORY[1])
        assert not any(s.key.startswith("linx_massage_") for s in bed.controller_button_specs)
        with pytest.raises(ValueError):
            await bed.massage_action("head")
    assert all(
        call.args[0].uuid == codec.TRANSPORTS[app.ROUTES[route].event_transport].write
        for call in client.write_gatt_char.call_args_list
    )
    assert all(json.loads(frame).get("dvid") == NAME for frame in frames(client))


@pytest.mark.parametrize("model", app.PROFILES)
@pytest.mark.parametrize("axis", app.AXES)
@pytest.mark.parametrize("duration", (1, 20))
async def test_short_holds_start_after_lane_latency_and_never_backfill(hass, model, axis, duration):
    coord, bed, client, _ = await target(hass, model)
    events = []
    with virtual_clock() as clock:

        async def write(char, frame, **kwargs):
            events.append((clock.now, bytes(frame)))
            await asyncio.sleep(0.007)

        client.write_gatt_char.side_effect = write
        await bed._ble_lock.acquire()
        task = asyncio.create_task(
            coord.async_execute_controller_command(lambda c: c.hold_control(f"{axis}_up", duration))
        )
        await asyncio.sleep(0.05)
        bed._ble_lock.release()
        await task
    motion = [(at, frame) for at, frame in events if frame != app.release(bed.profile, NAME, axis)]
    assert motion and motion[0][0] >= 0.05
    assert all(at < motion[0][0] + duration / 1000 for at, _ in motion)
    assert len(motion) <= 1 + duration // 10
    assert events[-1][1] == app.release(bed.profile, NAME, axis)


@pytest.mark.parametrize("model", app.PROFILES)
async def test_timed_service_uses_elapsed_deadline_and_captured_release(hass, model):
    coord, bed, client, _ = await target(hass, model)
    events = []
    with virtual_clock() as clock:

        async def write(char, frame, **kwargs):
            events.append((round(clock.now * 1000), bytes(frame)))
            await asyncio.sleep(0.15)

        client.write_gatt_char.side_effect = write
        call = ServiceCall(
            hass,
            DOMAIN,
            "timed_move",
            {"device_id": ["bed"], "motor": "head", "direction": "up", "duration_ms": 100},
        )
        with patch(
            "custom_components.adjustable_bed.services._resolve_sided_targets",
            return_value=([(coord, "both")], []),
        ):
            await handle_timed_move(call)
    assert events == [
        (0, codec.control(NAME, 1, km=6 if model == "quest" else 10, held=True)),
        (150, app.release(bed.profile, NAME, "head")),
    ]  # Finish the already admitted ACK, then release.


async def test_session_cache_parser_setup_and_late_callback_ownership(hass):
    coord, bed, client, _ = await target(hass)
    link = bed._link
    bed._notification(
        link, link.notify, bytearray(b'{"bedmd":20,"data":{"apld":2,"mgmd":3,"blsw":1}}')
    )
    assert coord.controller_state[ctrl.TIMER] == 20 and coord.controller_state[ctrl.MODE] == 3
    assert bed._touch() == 6 and bed._touch() == 6
    bed._notification(link, link.notify, bytearray(b'{"bedmd": 2}'))
    assert bed._touch() == 10 and bed._touch() == 6
    # The Android 15-field freeze is not copied: session-owned state stays fresh.
    for _ in range(16):
        bed._notification(link, link.notify, bytearray(b'{"data":{"apld":1}}'))
    bed._notification(link, link.notify, bytearray(b'{"data":{"apld":3}}'))
    assert coord.controller_state[ctrl.TIMER] == 30
    replacement = ctrl.LinxController(coord, model="quest", route="a00a", device=NAME)
    await replacement.async_discover_capabilities()
    replacement._notification(
        replacement._link, replacement._link.notify, bytearray(b'{"data":{"apld":2}}')
    )
    bed.on_disconnect()
    bed._notification(link, link.notify, bytearray(b'{"data":{"apld":0}}'))
    assert coord.controller_state[ctrl.TIMER] == 20
    replacement.on_disconnect()
    coord2, uart, _, _ = await target(hass, "orbes", "uart")
    for payload, expected in (
        ("8e00000002123400", "version_received"),
        ("8e000000020a3400", "invalid_version"),
        ("8e00000001000000", "connection_failed"),
    ):
        uart._notification(uart._link, uart._link.notify, bytearray.fromhex(payload))
        assert coord2.controller_state[ctrl.SETUP_RESULT] == expected
    assert coord2.controller_state[ctrl.VERSION] == "12.3.4"
    for length in range(19):
        uart._notification(uart._link, uart._link.notify, bytearray([1] * length))
    uart.on_disconnect()
    assert coord2.controller_state[ctrl.VERSION] is None


async def test_set_alarm_clears_one_resident_slot_and_refuses_to_set(hass):
    coord, bed, client, device = await target(hass, route="uart")
    await async_register_services(hass)
    for slot in range(1, 7):
        await hass.services.async_call(
            DOMAIN,
            "set_alarm",
            {"device_id": [device.id], "enabled": False, "slot": slot},
            blocking=True,
        )
    assert frames(client) == [codec.alarm_slot(NAME, slot) for slot in range(1, 7)]
    client.write_gatt_char.reset_mock()
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            "set_alarm",
            {"device_id": [device.id], "enabled": True, "time": "07:00:00", "slot": 1},
            blocking=True,
        )
    client.write_gatt_char.side_effect = BleakError("failed slot")
    with pytest.raises(BleakError):
        await hass.services.async_call(
            DOMAIN, "set_alarm", {"device_id": [device.id], "enabled": False}, blocking=True
        )
    client.write_gatt_char.side_effect = None
    await coord.async_execute_controller_command(lambda c: c.lights_toggle())
    assert frames(client) == [codec.alarm_slot(NAME, 1), codec.control(NAME, app.LIGHT)]


@pytest.mark.parametrize("route", codec.TRANSPORTS)
async def test_manual_snore_defaults_status_destination_and_no_reconnect(hass, route):
    coord, bed, client, device = await target(hass, route=route)
    await async_register_services(hass)
    with virtual_clock():
        await hass.services.async_call(
            DOMAIN,
            "linx_snore_intervention",
            {"device_id": [device.id], "hold_minutes": 1},
            blocking=True,
        )
        assert frames(client)[0] == codec.snore(
            NAME, uart=route == "uart", keep=1, speed=10, lift=10
        )
        await asyncio.sleep(60.01)
        assert frames(client)[-1] == codec.SNORE_STATUS
        assert client.write_gatt_char.call_args.args[0].uuid == codec.TRANSPORTS["a00a"].write
        await hass.services.async_call(
            DOMAIN,
            "linx_snore_intervention",
            {"device_id": [device.id], "hold_minutes": 1},
            blocking=True,
        )
        bed.on_disconnect()
        before = len(frames(client))
        coord.async_ensure_connected = AsyncMock(return_value=True)
        await asyncio.sleep(61)
        assert len(frames(client)) == before
        coord.async_ensure_connected.assert_not_awaited()


async def test_self_check_reports_only_proven_fields_and_bounds_timeout(hass):
    coord, bed, client, _ = await target(hass)
    with virtual_clock():
        await coord.async_execute_controller_command(
            lambda c: cast(ctrl.LinxController, c).self_check()
        )
        bed._notification(
            bed._link, bed._link.notify, bytearray(b'{"chkStatu":192,"headPlus":12,"footPlus":34}')
        )
        assert coord.controller_state[ctrl.CHECK] == "complete"
        assert coord.controller_state[ctrl.CHECK_DETAIL] == {
            "head_fault": 0,
            "foot_fault": 0,
            "head_massage_connected": True,
            "foot_massage_connected": True,
            "head_ripple": 12,
            "foot_ripple": 34,
            "head_ripple_max": 12,
            "foot_ripple_max": 34,
        }
        await asyncio.sleep(61)
        assert coord.controller_state[ctrl.CHECK] == "complete"
        await coord.async_execute_controller_command(
            lambda c: cast(ctrl.LinxController, c).self_check()
        )
        await asyncio.sleep(61)
        assert coord.controller_state[ctrl.CHECK] == "timeout"


async def test_registered_multi_target_stop_admission_precedes_lazy_import(hass, monkeypatch):
    first = await target(hass)
    second = await target(hass, model="orbes")
    await async_register_services(hass)
    imported = asyncio.Event()
    proceed = asyncio.Event()
    from custom_components.adjustable_bed.beds.linx import services

    original = services.async_import_modules

    async def delayed(*args):
        imported.set()
        await proceed.wait()
        await original(*args)

    monkeypatch.setattr(services, "async_import_modules", delayed)
    task = asyncio.create_task(
        hass.services.async_call(
            DOMAIN,
            "linx_snore_intervention",
            {"device_id": [first[3].id, second[3].id]},
            blocking=True,
        )
    )
    await imported.wait()
    await second[0].async_stop_command()
    second[2].write_gatt_char.reset_mock()
    proceed.set()
    await task
    assert not frames(second[2])  # A later target's STOP cancels its pending admission.


async def test_paired_child_routes_only_to_its_physical_receiver(hass):
    triples = {"left": await target(hass), "right": await target(hass, "orbes", "uart")}
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_PAIR_ID: "linx-test"})
    entry.add_to_hass(hass)
    entry.mock_state(hass, ConfigEntryState.LOADED)
    pair = PairedBedCoordinator(hass, entry, {side: values[0] for side, values in triples.items()})
    hass.data[DOMAIN][entry.entry_id] = pair
    registry = dr.async_get(hass)
    registry.async_get_or_create(config_entry_id=entry.entry_id, **pair.device_info)
    right = registry.async_get_or_create_child(
        config_entry_id=entry.entry_id, **child_device_info(pair, "right")
    )
    await async_register_services(hass)
    await hass.services.async_call(
        DOMAIN,
        "set_alarm",
        {"device_id": [right.id], "enabled": False, "slot": 2},
        blocking=True,
    )
    assert frames(triples["left"][2]) == []
    assert frames(triples["right"][2]) == [codec.alarm_slot(NAME, 2)]


@pytest.mark.parametrize("model", app.PROFILES)
async def test_stop_preempts_movement_and_waits_for_model_specific_cleanup(hass, model):
    coord, bed, client, _ = await target(hass, model)
    events = []
    with virtual_clock() as clock:

        async def write(char, frame, **kwargs):
            events.append((round(clock.now * 1000), bytes(frame)))
            await asyncio.sleep(0.007)

        client.write_gatt_char.side_effect = write
        task = asyncio.create_task(
            coord.async_execute_controller_command(lambda c: c.hold_control("head_up", 5000))
        )
        await asyncio.sleep(0.05)
        await coord.async_stop_command()
        await task
        assert events[-1][1] == app.release(bed.profile, NAME, "head")
        assert sum(frame == app.release(bed.profile, NAME, "head") for _, frame in events) == 1
        boundary = len(events)
        await coord.async_execute_controller_command(lambda c: c.hold_control("both_down", 20))
        assert all(
            frame
            in (
                codec.control(NAME, 10, km=6 if model == "quest" else 10, held=True),
                app.release(bed.profile, NAME, "both"),
            )
            for _, frame in events[boundary:]
        )


async def test_old_gesture_cannot_release_or_publish_on_a_replaced_link(hass):
    coord, bed, client, _ = await target(hass, "orbes")
    original = bed._link
    entered = asyncio.Event()
    resume = asyncio.Event()

    async def write(char, frame, **kwargs):
        entered.set()
        await resume.wait()

    client.write_gatt_char.side_effect = write
    task = asyncio.create_task(
        coord.async_execute_controller_command(lambda c: c.hold_control("head_up", 50))
    )
    await entered.wait()
    bed.on_disconnect()
    client.services = gatt()
    await bed.async_discover_capabilities()
    resume.set()
    with pytest.raises(ConnectionError):
        await task
    assert len(frames(client)) == 1
    bed._notification(original, original.notify, bytearray(b'{"data":{"apld":3}}'))
    assert coord.controller_state.get(ctrl.TIMER) is None


async def test_chunking_and_property_admission_keep_original_buffers(hass):
    coord, bed, client, _ = await target(hass)
    data = b"a" * 500
    await coord.async_execute_controller_command(lambda c: c.write_command(data))
    assert frames(client) == [data[:243], data[243:486], data[486:]]
    client.write_gatt_char.reset_mock()
    bed._link.write.properties = []
    with pytest.raises(BleakError):
        await coord.async_execute_controller_command(lambda c: c.write_command(b"unsafe"))
    assert frames(client) == []


async def test_native_combined_cover_uses_coordinator_and_its_own_release(hass):
    from custom_components.adjustable_bed.cover import _cover_entities_for

    coord, bed, client, _ = await target(hass, "orbes")
    cover = next(e for e in _cover_entities_for(hass, coord) if e.entity_description.key == "both")
    cover.hass = hass
    cover.async_write_ha_state = MagicMock()
    with virtual_clock():
        await cover.async_open_cover()
    assert frames(client)[0] == codec.control(NAME, 5, km=10, held=True)
    assert frames(client)[-1] == app.release(bed.profile, NAME, "both")


async def test_split_json_finishes_one_admitted_buffer_before_short_hold_release(hass):
    coord, _, client, _ = await target(hass)
    name = "KSWF07D" + "0" * 200
    bed = ctrl.LinxController(coord, model="quest", route="a00a", device=name)
    coord._controller = coord._offline_controller = bed
    await bed.async_discover_capabilities()

    async def write(char, frame, **kwargs):
        await asyncio.sleep(0.01)

    client.write_gatt_char.side_effect = write
    with virtual_clock():
        await coord.async_execute_controller_command(lambda c: c.hold_control("head_up", 1))
    held = codec.control(name, 1, km=6, held=True)
    release = codec.control(name, 0)
    assert frames(client) == [held[:243], held[243:], release[:243], release[243:]]


async def test_uart_does_not_infer_json_reply_support_from_unchanged_outbound_json(hass):
    coord, bed, _, _ = await target(hass, route="uart")
    bed._notification(
        bed._link, bed._link.notify, bytearray(b'{"bedmd":20,"data":{"apld":3,"blsw":1}}')
    )
    assert bed._bed_mode is None
    assert coord.controller_state.get(ctrl.TIMER) is None


async def test_factory_prefers_live_raw_bluetooth_name_over_saved_title(hass):
    coord, _, client, _ = await target(hass)
    raw = "KSWF07D12345678"
    bed = await create_controller(coord, "linx", "a00a", client, device_name=raw)
    assert isinstance(bed, ctrl.LinxController) and bed.device == raw


@pytest.mark.parametrize("route", ("uart_json", "a00a_uart"))
async def test_mixed_service_route_and_saved_intervention_family_are_independent(hass, route):
    coord, bed, client, device = await target(hass, route=route)
    await async_register_services(hass)
    await hass.services.async_call(
        DOMAIN, "linx_snore_intervention", {"device_id": [device.id]}, blocking=True
    )
    binary = app.ROUTES[route].snore_uart
    assert frames(client) == [codec.snore(NAME, uart=binary, keep=10, speed=10, lift=10)]
    assert client.write_gatt_char.call_args.args[0].uuid == codec.TRANSPORTS["uart"].write
    client.write_gatt_char.reset_mock()
    await coord.async_execute_controller_command(lambda c: c.lights_toggle())
    assert frames(client) == [codec.control(NAME, app.LIGHT)]
    assert (
        client.write_gatt_char.call_args.args[0].uuid
        == codec.TRANSPORTS[app.ROUTES[route].event_transport].write
    )


async def test_self_check_timeout_cannot_be_completed_by_a_late_reply(hass):
    coord, bed, _, _ = await target(hass)
    with virtual_clock():
        await coord.async_execute_controller_command(
            lambda c: cast(ctrl.LinxController, c).self_check()
        )
        await asyncio.sleep(61)
        bed._notification(
            bed._link, bed._link.notify, bytearray(b'{"chkStatu":192,"headPlus":7,"footPlus":8}')
        )
    assert coord.controller_state[ctrl.CHECK] == "timeout"
    assert coord.controller_state[ctrl.CHECK_DETAIL] is None


def test_intervention_delay_retains_java_integer_arithmetic():
    assert codec.snore_delay_ms(10) == 600000
    assert codec.snore_delay_ms(35792) == -2147447296


async def test_every_intervention_destination_is_preflighted_before_any_target_writes(hass):
    first = await target(hass)
    second = await target(hass, route="a00a_uart")
    second[2].services.pop()  # Generic A00A still works, but direct UART is absent.
    await async_register_services(hass)
    with pytest.raises(BleakError):
        await hass.services.async_call(
            DOMAIN,
            "linx_snore_intervention",
            {"device_id": [first[3].id, second[3].id]},
            blocking=True,
        )
    assert frames(first[2]) == frames(second[2]) == []


@pytest.mark.parametrize("model", app.PROFILES)
@pytest.mark.parametrize("route", app.ROUTES)
async def test_state_entities_follow_the_actual_incoming_route(hass, model, route):
    _, bed, _, _ = await target(hass, model, route)
    keys = {spec.state_key for spec in bed.controller_state_sensor_specs}
    uart = app.ROUTES[route].event_transport == "uart"
    assert (ctrl.VERSION in keys) == uart
    assert ctrl.SETUP_RESULT not in keys
    assert (ctrl.CHECK in keys) == (not uart)
    assert (ctrl.TIMER in keys) == (ctrl.MODE in keys) == (model == "quest" and not uart)


async def test_self_check_retains_session_ripple_maxima_without_synthetic_currents(hass):
    coord, bed, _, _ = await target(hass)
    for head, foot, maximum in ((12, 34, (12, 34)), (8, 40, (12, 40))):
        await coord.async_execute_controller_command(
            lambda c: cast(ctrl.LinxController, c).self_check()
        )
        payload = json.dumps({"chkStatu": 192, "headPlus": head, "footPlus": foot}).encode()
        bed._notification(bed._link, bed._link.notify, bytearray(payload))
        detail = coord.controller_state[ctrl.CHECK_DETAIL]
        assert detail is not None
        assert detail["head_ripple_max"] == maximum[0] and detail["foot_ripple_max"] == maximum[1]
        assert not any("current" in key for key in detail)
    bed.on_disconnect()
    assert bed._head_ripple_max == bed._foot_ripple_max == 0
