"""Frozen A99 vectors and current-session Cosyworld controls, no hardware claims."""

from __future__ import annotations

import asyncio
import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.exceptions import HomeAssistantError
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.beds.octo.cosyworld import CosyworldController
from custom_components.adjustable_bed.codec.octo import (
    OctoCapabilityRecord,
    OctoPacketCodec,
    _encode_capability_value,
)
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.profiles import cosyworld as app
from tests.error_helpers import raises_key
from tests.hold_lease_wire import virtual_clock

VECTORS = json.loads((Path(__file__).parent / "fixtures/cosyworld/vectors.json").read_text())


@pytest.mark.parametrize("row", VECTORS, ids=lambda r: r["id"])
def test_all_frozen_literals_reproduce_existing_codec(row):
    i = row["inputs"]
    assert OctoPacketCodec()._build_packet(
        [i["type"] | i.get("direction", 0), i["command"]], i["data"]
    ) == bytes.fromhex(row["expected_bytes"])


def record(feature, value=b"", characteristic=b"\x01", readonly=0, value_type=1):
    return OctoCapabilityRecord(feature, readonly, characteristic, value_type, value)


def complete(c, *records):
    for r in records:
        c._handle_feature_response(_encode_capability_value(r, r.value))
    c._handle_feature_response([255, 255, 255, 0, 0, 0])


@pytest.fixture
def runtime(hass, mock_bleak_client):
    entry = MockConfigEntry(
        domain=const.DOMAIN,
        title="Cosyworld",
        unique_id="AA:BB:CC:DD:99:01",
        data={
            CONF_ADDRESS: "AA:BB:CC:DD:99:01",
            CONF_NAME: "Cosyworld",
            const.CONF_BED_TYPE: "cosyworld",
            const.CONF_MOTOR_COUNT: 2,
            const.CONF_MOTOR_PULSE_COUNT: 1,
            const.CONF_MOTOR_PULSE_DELAY_MS: 350,
            const.CONF_DISABLE_ANGLE_SENSING: True,
        },
    )
    entry.add_to_hass(hass)
    co = AdjustableBedCoordinator(hass, entry)
    co._client = mock_bleak_client
    mock_bleak_client.is_connected = True
    char = SimpleNamespace(
        uuid=app.CHARACTERISTIC,
        properties=["write-without-response", "notify"],
        handle=99,
        descriptors=[],
    )
    mock_bleak_client.services = [SimpleNamespace(uuid=app.SERVICE, characteristics=[char])]
    c = CosyworldController(co)
    co._controller = c
    c._device_info = {"cid": 1, "pid": 2, "firmware": 3, "hardware": 4}
    complete(c, record(1, characteristic=b"\x02"), record(3, b"\x00\x01", characteristic=b"\x00"))
    c._session_ready = True
    return co, c, mock_bleak_client


def writes(client):
    return [bytes(call.args[1]) for call in client.write_gatt_char.call_args_list]


@pytest.mark.parametrize(
    "feature,action", ((0x102, "lights"), (0x101, "synchro"), (0x11, "remote_control_lock"))
)
@pytest.mark.parametrize("tail", (b"\x40", b"\x40\x3c\x4f\x41\x00"))
@pytest.mark.parametrize("on", (False, True))
@pytest.mark.parametrize("readonly", (0, 1))
async def test_actual_toggle_preserves_all_current_metadata_and_tail(
    runtime, feature, action, tail, on, readonly
):
    _, c, client = runtime
    r = record(feature, b"\x00" + tail, b"\x01\x3c\x40", readonly, 2)
    complete(c, r)
    if action == "lights":
        await (c.lights_on() if on else c.lights_off())
    else:
        await getattr(c, f"set_{action}")(on)
    expected = r.with_value(bytes((on,)) + tail)
    assert writes(client) == [
        c._build_packet([0x20, 0x72], _encode_capability_value(expected, expected.value))
    ]
    assert c._capability_records[feature] == expected
    assert client.write_gatt_char.call_args.kwargs["response"] is False


@pytest.mark.parametrize("row", [r for r in VECTORS if "-tail-" in r["id"]], ids=lambda r: r["id"])
async def test_corrected_actual_setters_match_frozen_tail_literals(runtime, row):
    _, c, client = runtime
    data = row["inputs"]["data"]
    feature = int.from_bytes(bytes(data[:3]), "big")
    complete(c, record(feature, b"\x00\x40", value_type=2))
    if feature == 0x102:
        await (c.lights_on() if data[7] else c.lights_off())
    elif feature == 0x101:
        await c.set_synchro(bool(data[7]))
    else:
        await c.set_remote_control_lock(bool(data[7]))
    assert writes(client) == [bytes.fromhex(row["expected_bytes"])]


async def test_duration_replaces_value_and_shared_select(runtime):
    _, c, client = runtime
    r = record(0x103, b"\x05\x40\x3c", value_type=2)
    complete(c, r)
    assert c.supports_light_timer and not c.controller_number_specs
    await c.set_light_timer("60 min")
    assert writes(client) == [c._build_packet([0x20, 0x72], _encode_capability_value(r, b"\x3c"))]
    assert c._capability_records[0x103].value == b"\x3c"


async def test_duplicate_capability_keeps_original_readonly_and_type(runtime):
    _, c, _ = runtime
    complete(c, record(0x102, b"\x00", readonly=1, value_type=2))
    c._handle_feature_response(
        _encode_capability_value(record(0x102, b"\x01\x40", b"\x01\x03", 0, 7), b"\x01\x40")
    )
    assert c._capability_records[0x102] == record(0x102, b"\x01\x40", b"\x01\x03", 1, 2)


@pytest.mark.parametrize("count", (1, 2, 3, 4, 0))
async def test_layout_and_unsupported_sibling_features(runtime, count):
    _, c, _ = runtime
    complete(
        c,
        record(1, characteristic=bytes((count,))),
        record(0x104, bytes(5)),
        record(0x105, b"\x01"),
        record(0x106, b"\x00\x06"),
    )
    assert len(c.motor_control_specs) == {1: 1, 2: 3}.get(count, 0)
    assert not c.supports_single_address_pairing
    assert not c.supports_light_color_control
    assert not c.supports_automatic_light and not c.supports_light_sensitivity
    assert not c.controller_select_specs
    if count == 4:
        assert c.held_control_options == ("all_down",)
        assert [s.key for s in c.controller_button_specs] == ["octo_all_down"]
    elif count != 1 and count != 2:
        assert c.held_control_options == ()


async def test_memory_classes_count_and_labels_are_profile_specific(runtime):
    _, c, _ = runtime
    complete(c, record(2, characteristic=b"\x03"), record(4, b"\x01\x02\x03", b"\x03\x01\x01"))
    assert c.memory_slot_count == 3
    assert c.memory_slot_names == ("Anti-snore", "Zero gravity", "Lumbar support")
    assert c.is_memory_slot_programmable(1) and c.is_memory_slot_programmable(2)
    assert not c.is_memory_slot_programmable(3)
    assert all(s.hold.release_delay_ms == 0 for s in c.controller_button_specs if s.hold)
    # An unknown description does not inherit OCTO's Flat label.
    complete(c, record(4, b"\x04\xff\x00", b"\x03\x00\x00"))
    assert c.memory_slot_names == (None, None, None)


@pytest.mark.parametrize(
    "control,expected",
    (("back_up", "V-M1-up"), ("back_legs_down", "V-M12-down"), ("memory_1", "V-recall-0")),
)
async def test_held_actual_path_refresh_and_fresh_stop(runtime, control, expected):
    _, c, client = runtime
    complete(c, record(2, characteristic=b"\x03"))
    with virtual_clock():
        await c.hold_control(control, 701)
    literal = bytes.fromhex(next(r["expected_bytes"] for r in VECTORS if r["id"] == expected))
    assert writes(client) == [literal] * 3 + [bytes.fromhex("40 02 73 00 00 0b 40")]


async def test_cancelled_move_still_stops_and_reconnect_never_gets_old_cleanup(runtime):
    co, c, client = runtime

    async def cancel(_char, payload, **_kwargs):
        if payload == bytes.fromhex("40 02 70 00 01 0b 02 40"):
            co.cancel_command.set()

    client.write_gatt_char.side_effect = cancel
    await c.hold_control("back_up", 700)
    assert writes(client)[-1] == bytes.fromhex("40 02 73 00 00 0b 40")
    co.cancel_command.clear()
    client.write_gatt_char.reset_mock()
    replacement = MagicMock(is_connected=True, write_gatt_char=AsyncMock())

    async def reconnect(*_args, **_kwargs):
        co._client = replacement
        c.on_disconnect()

    client.write_gatt_char.side_effect = reconnect
    with virtual_clock(), pytest.raises(ConnectionError):
        await c.hold_control("back_up", 701)
    replacement.write_gatt_char.assert_not_called()


async def test_setting_dispatch_uses_newest_record_and_rejects_reconnected_client(runtime):
    co, c, client = runtime
    complete(c, record(0x102, b"\x00\x40"))
    await c._ble_lock.acquire()
    task = asyncio.create_task(c.lights_on())
    await asyncio.sleep(0)
    complete(c, record(0x102, b"\x00\x3c\x41"))
    c._ble_lock.release()
    await task
    assert c._capability_records[0x102].value == b"\x01\x3c\x41"
    await c._ble_lock.acquire()
    task = asyncio.create_task(c.lights_off())
    await asyncio.sleep(0)
    co._client = MagicMock(is_connected=True, write_gatt_char=AsyncMock())
    c._ble_lock.release()
    with pytest.raises(ConnectionError):
        await task
    co.client.write_gatt_char.assert_not_called()


@pytest.mark.parametrize("block", ("pin", "customer", "session", "empty"))
async def test_unsafe_setting_sends_nothing(runtime, block):
    _, c, client = runtime
    complete(c, record(0x102, b"" if block == "empty" else b"\x00\x40"))
    if block == "pin":
        c._pin_feature_active, c._has_pin, c._pin_locked = True, True, True
    if block == "customer":
        c._device_info["cid"] = 0xFFFFFFFF
    if block == "session":
        c._session_ready = False
    with raises_key(
        "cosyworld_session"
        if block == "session"
        else "cosyworld_capability"
        if block == "empty"
        else "cosyworld_locked"
    ):
        await c.lights_on()
    client.write_gatt_char.assert_not_called()


async def test_cancelled_setting_does_not_change_cache_or_publish(runtime):
    co, c, client = runtime
    complete(c, record(0x102, b"\x00\x40"))
    co.handle_controller_state_updates = MagicMock()
    co.cancel_command.set()
    await c.lights_on()
    client.write_gatt_char.assert_not_called()
    assert c._capability_records[0x102].value == b"\x00\x40"
    co.handle_controller_state_updates.assert_not_called()


async def test_exact_handshake_order_session_stale_callback_and_complete_capabilities(runtime):
    co, c, client = runtime
    callbacks = []
    client.start_notify.side_effect = lambda _char, cb: callbacks.append(cb)

    def receive(payload):
        callbacks[-1](MagicMock(), bytearray(payload))

    async def answer(_char, payload, **_kwargs):
        if payload == app.STARTUP[0]:
            receive(app.HANDSHAKE_RESPONSE)
        elif payload == app.STARTUP[1]:
            receive(
                bytes.fromhex(
                    next(r["expected_bytes"] for r in VECTORS if r["id"] == "V-info-response")
                )
            )
        elif payload == app.STARTUP[2]:
            for r in (
                record(1, characteristic=b"\x02"),
                record(3, b"\x00\x01", characteristic=b"\x00"),
                record(0xFFFFFF),
            ):
                receive(c._build_packet([0x21, 0x71], _encode_capability_value(r, r.value)))

    client.write_gatt_char.side_effect = answer
    assert await c.discover_features()
    assert writes(client) == list(app.STARTUP)
    assert c.normal_controls_available
    old = callbacks[-1]
    c.on_disconnect()
    old(MagicMock(), bytearray(c._build_packet([0x21, 0x43], [1])))
    assert c._pin_state_accepted is None
    assert not c.normal_controls_available


@pytest.mark.parametrize(
    "response", (b"", b"noise", app.HANDSHAKE_RESPONSE + app.HANDSHAKE_RESPONSE)
)
async def test_no_legacy_fallback_when_exact_handshake_is_missing(runtime, response):
    _, c, client = runtime
    c.profile = replace(app.PROFILE, handshake_timeout_s=0.001)
    callbacks = []
    client.start_notify.side_effect = lambda _char, cb: callbacks.append(cb)

    async def answer(*_args, **_kwargs):
        callbacks[-1](MagicMock(), bytearray(response))

    client.write_gatt_char.side_effect = answer
    assert not await c.discover_features()
    assert not c.normal_controls_available
    assert not c._legacy_assumed_lights
    assert writes(client) == [app.STARTUP[0]]


async def test_confirmed_reset_uses_one_frame_and_scoped_five_second_disconnect(runtime):
    co, c, client = runtime
    tasks = []
    co.entry.async_create_background_task = lambda _h, coro, **_kw: tasks.append(coro)
    await c.reset_defaults()
    assert writes(client) == [bytes.fromhex("40 20 ae 00 00 b2 40")]
    assert len(tasks) == 1
    co.async_disconnect = AsyncMock()
    with virtual_clock() as clock:
        await tasks.pop()
    assert clock.now == 5
    co.async_disconnect.assert_awaited_once()
    assert co.async_disconnect.call_args.kwargs["serialize_with_commands"] is True
    assert co.async_disconnect.call_args.kwargs["expected_session"]() is True
    await c.reset_defaults()
    c.on_disconnect()
    co.async_disconnect.reset_mock()
    with virtual_clock():
        await tasks.pop()
    co.async_disconnect.assert_not_called()


async def test_reset_cancelled_or_locked_never_schedules_disconnect(runtime):
    co, c, client = runtime
    co.entry.async_create_background_task = MagicMock()
    co.cancel_command.set()
    await c.reset_defaults()
    client.write_gatt_char.assert_not_called()
    co.entry.async_create_background_task.assert_not_called()
    c._pin_locked = True
    with raises_key("cosyworld_locked"):
        await c.reset_defaults()


async def test_actual_pin_enrollment_is_numeric_and_cancel_does_not_save(runtime):
    co, c, client = runtime
    c._pin_feature_active = True
    assert not c.normal_controls_available
    await c.enroll_pin("0123")
    assert writes(client) == [bytes.fromhex("40 20 3c 04 00 04 15 00 01 02 03 40")]
    assert c._pin == "0123"
    co.cancel_command.set()
    with raises_key("action_stopped"):
        await c.enroll_pin("4567")
    assert c._pin == "0123"


async def test_native_shared_services_require_confirmation_and_single_physical_target(
    runtime, hass, monkeypatch
):
    from custom_components.adjustable_bed.services import async_register_services
    from tests.test_octo_services import _register_service_device

    co, c, client = runtime
    co._ready = True
    co.async_ensure_connected = AsyncMock(return_value=True)
    device = _register_service_device(hass, co.entry, co)
    await async_register_services(hass)
    tasks = []
    monkeypatch.setattr(
        co.entry, "async_create_background_task", lambda _h, coro, **_kw: tasks.append(coro)
    )
    with pytest.raises(Exception) as error:
        await hass.services.async_call(
            const.DOMAIN, "octo_reset_defaults", {"device_id": device.id}, blocking=True
        )
    assert "confirmed" in str(error.value)
    client.write_gatt_char.assert_not_called()
    await hass.services.async_call(
        const.DOMAIN,
        "octo_reset_defaults",
        {"device_id": device.id, "confirmed": True},
        blocking=True,
    )
    assert writes(client) == [bytes.fromhex("40 20 ae 00 00 b2 40")]
    assert len(tasks) == 1
    tasks.pop().close()
    # The shared action validates matching PINs before connection or writes.
    client.write_gatt_char.reset_mock()
    with raises_key("pin_mismatch"):
        await hass.services.async_call(
            const.DOMAIN,
            "octo_enroll_pin",
            {
                "device_id": device.id,
                "octo_pin": "0123",
                "octo_pin_confirmation": "0124",
            },
            blocking=True,
        )
    client.write_gatt_char.assert_not_called()
    c._pin_feature_active = True
    assert not c.normal_controls_available
    await hass.services.async_call(
        const.DOMAIN,
        "octo_enroll_pin",
        {
            "device_id": device.id,
            "octo_pin": "0123",
            "octo_pin_confirmation": "0123",
        },
        blocking=True,
    )
    assert writes(client) == [bytes.fromhex("40 20 3c 04 00 04 15 00 01 02 03 40")]
    assert co.entry.data[const.CONF_OCTO_PIN] == "0123"


def test_discovery_offers_shared_app_without_selecting_it():
    from custom_components.adjustable_bed.detection import detect_bed_type_detailed

    for name in ("RC2", "CLI", "OtherReceiver"):
        service = MagicMock(name=name, service_uuids=[app.SERVICE], manufacturer_data={})
        service.name = name
        service.advertisement = None
        service.local_name = name
        result = detect_bed_type_detailed(service)
        assert "cosyworld" in result.ambiguous_types
        assert result.bed_type != "cosyworld"
    assert not app.scan_name("OCTOHDev")
    assert app.scan_name("C\x00LI")


def test_profile_setup_and_per_side_ownership():
    from custom_components.adjustable_bed.app_profiles import (
        hidden_generic_fields,
        per_side_profile,
    )

    p = per_side_profile("cosyworld", None)
    assert p is not None and const.CONF_OCTO_PIN in p.keys
    assert const.CONF_MOTOR_COUNT in hidden_generic_fields("cosyworld", None)
    assert const.CONF_PROTOCOL_VARIANT in hidden_generic_fields("cosyworld", None)
    assert const.CONF_OCTO_MOTOR_COUNT_OVERRIDE not in p.keys


async def test_current_pin_unlock_is_not_overwritten_by_accessory_notifications(runtime):
    _, c, _ = runtime
    complete(c, record(3, b"\x01\x00"))
    c._handle_pin_notification(0x43, [1])
    assert c.normal_controls_available
    complete(c, record(0x102, b"\x00\x40"))
    # The helper's END reapplies the snapshot; test the ordinary live notification.
    c._handle_pin_notification(0x43, [1])
    c._handle_feature_response(_encode_capability_value(record(0x102, b"\x01\x40"), b"\x01\x40"))
    assert c.normal_controls_available


async def test_native_ha_setup_and_light_timer_entities(
    hass,
    mock_coordinator_connected,
    mock_bleak_client,
    enable_custom_integrations,
    mock_async_ble_device_from_address,
):
    from homeassistant.helpers import entity_registry as er

    from custom_components.adjustable_bed.codec.octo import OctoPacketCodec

    client = mock_bleak_client
    char = SimpleNamespace(
        uuid=app.CHARACTERISTIC,
        properties=["write-without-response", "notify"],
        handle=99,
        descriptors=[],
    )
    client.services = [SimpleNamespace(uuid=app.SERVICE, characteristics=[char])]
    callbacks = []
    client.start_notify.side_effect = lambda _char, cb: callbacks.append(cb)
    codec = OctoPacketCodec()
    info = bytes.fromhex(next(r["expected_bytes"] for r in VECTORS if r["id"] == "V-info-response"))

    def receive(payload):
        callbacks[-1](char, bytearray(payload))

    async def answer(_char, payload, **_kwargs):
        if payload == app.STARTUP[0]:
            receive(app.HANDSHAKE_RESPONSE)
        elif payload == app.STARTUP[1]:
            receive(info)
        elif payload == app.STARTUP[2]:
            for r in (
                record(1, characteristic=b"\x02"),
                record(3, b"\x00\x01", characteristic=b"\x00"),
                record(0x102, b"\x00\x40"),
                record(0x103, b"\x05"),
                record(0xFFFFFF),
            ):
                receive(codec._build_packet([0x21, 0x71], _encode_capability_value(r, r.value)))

    client.write_gatt_char.side_effect = answer
    entry = MockConfigEntry(
        domain=const.DOMAIN,
        title="Cosyworld",
        unique_id="AA:BB:CC:DD:99:02",
        data={
            CONF_ADDRESS: "AA:BB:CC:DD:99:02",
            CONF_NAME: "Cosyworld",
            const.CONF_BED_TYPE: "cosyworld",
            const.CONF_DISABLE_ANGLE_SENSING: True,
            const.CONF_CONNECTION_MODE: const.CONNECTION_MODE_IDLE,
            const.CONF_HAS_MASSAGE: False,
            const.CONF_MOTOR_COUNT: 2,
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    registry = er.async_get(hass)
    light = registry.async_get_entity_id(
        "light", const.DOMAIN, "AA:BB:CC:DD:99:02_under_bed_lights"
    )
    timer = registry.async_get_entity_id("select", const.DOMAIN, "AA:BB:CC:DD:99:02_light_timer")
    assert light and timer
    from bleak.exc import BleakError

    from custom_components.adjustable_bed.runtime_data import loaded_runtime

    coordinator = loaded_runtime(hass, entry.entry_id)
    client.disconnect.side_effect = BleakError("receiver kept the link")
    assert await coordinator.async_disconnect() is False
    await hass.async_block_till_done()
    assert hass.states.get(light).state != "unavailable"
    client.disconnect.side_effect = None
    client.write_gatt_char.reset_mock()
    await hass.services.async_call("light", "turn_on", {"entity_id": light}, blocking=True)
    assert writes(client) == [bytes.fromhex("40 20 72 00 09 9e 00 01 02 00 01 01 01 01 3c 01 40")]
    durations = [r for r in VECTORS if r["id"].startswith("V-duration-")]
    assert {r["inputs"]["data"][-1] for r in durations} == set(range(61))
    for row in durations:
        # The real select action must replace the whole V, including a peer tail.
        receive(
            codec._build_packet(
                [0x21, 0x71],
                _encode_capability_value(record(0x103, b"\x05\x40\x3c"), b"\x05\x40\x3c"),
            )
        )
        client.write_gatt_char.reset_mock()
        option = app.LIGHT_TIMER_OPTIONS[row["inputs"]["data"][-1]]
        await hass.services.async_call(
            "select", "select_option", {"entity_id": timer, "option": option}, blocking=True
        )
        assert writes(client) == [bytes.fromhex(row["expected_bytes"])]
        assert hass.states.get(timer).state == option
    client.write_gatt_char.reset_mock()
    receive(codec._build_packet([0x21, 0x44]))
    await hass.async_block_till_done()
    assert hass.states.get(light).state == "unavailable"
    await hass.services.async_call("light", "turn_on", {"entity_id": light}, blocking=True)
    client.write_gatt_char.assert_not_called()
    receive(codec._build_packet([0x21, 0x43], [1]))
    await hass.async_block_till_done()
    assert hass.states.get(light).state != "unavailable"
    await hass.services.async_call("light", "turn_off", {"entity_id": light}, blocking=True)
    assert len(writes(client)) == 1
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_all_down_save_and_teach_use_their_own_frozen_literals(runtime):
    _, c, client = runtime
    complete(
        c,
        record(1, characteristic=b"\x04"),
        record(2, characteristic=b"\x03"),
        record(4, b"\x00\x01\x02", b"\x03\x01\x01"),
        record(0x10),
    )
    with virtual_clock():
        await c.hold_control("all_down", 100)
    assert writes(client) == [
        bytes.fromhex("40 02 71 00 01 ee 1e 40"),
        bytes.fromhex("40 02 73 00 00 0b 40"),
    ]
    client.write_gatt_char.reset_mock()
    await c.program_memory(2)
    await c.program_memory(3)
    assert writes(client) == [bytes.fromhex("40 10 70 00 01 fe 01 40")]
    client.write_gatt_char.reset_mock()
    await c.teach_remote()
    assert writes(client) == [bytes.fromhex("40 20 72 00 08 d1 00 00 10 01 01 01 01 01 40")]
    assert not any(s.key.startswith(("reset_", "octo_reset_")) for s in c.controller_button_specs)
    assert not c.supports_preset_flat and not c.supports_preset_both_up


async def test_inflight_peer_update_wins_over_command_cache_and_expiry_keeps_tail(runtime):
    _, c, client = runtime
    complete(c, record(0x102, b"\x00\x40"))

    async def answer(*_args, **_kwargs):
        r = record(0x102, b"\x00\x3c\x41")
        c._handle_feature_response(_encode_capability_value(r, r.value))

    client.write_gatt_char.side_effect = answer
    await c.lights_on()
    assert c._capability_records[0x102].value == b"\x00\x3c\x41"
    c.on_light_auto_off()
    assert c._capability_records[0x102].value == b"\x00\x3c\x41"


async def test_transport_admission_and_no_periodic_pin_sender(runtime):
    _, c, client = runtime
    char = client.services[0].characteristics[0]
    client.services[0].characteristics.append(char)
    with raises_key("cosyworld_transport"):
        await c.start_notify()
    client.start_notify.assert_not_called()
    await c.start_keepalive()
    assert c._keepalive_task is None


async def test_required_unset_pin_blocks_motion_but_allows_explicit_enrollment(runtime):
    _, c, client = runtime
    complete(c, record(3, b"\x00\x01"))
    assert not c.normal_controls_available
    with raises_key("cosyworld_pin_unset"):
        await c._octo_move_with_stop(2, "up")
    assert writes(client) == [bytes.fromhex("40 02 73 00 00 0b 40")]
    client.write_gatt_char.reset_mock()
    await c.enroll_pin("0123")
    assert writes(client) == [bytes.fromhex("40 20 3c 04 00 04 15 00 01 02 03 40")]


async def test_reused_session_authentication_uses_controller_lifecycle(runtime):
    _, c, client = runtime
    complete(c, record(3, b"\x01\x00"))
    c._pin = "9876"

    async def unlock(_char, payload, **_kwargs):
        assert payload == bytes.fromhex("40 20 43 00 04 fb 09 08 07 06 40")
        c._handle_pin_notification(0x43, [1])

    client.write_gatt_char.side_effect = unlock
    await c.async_refresh_auth()
    assert c.normal_controls_available
    assert len(writes(client)) == 1


@pytest.mark.parametrize("name", ("RC2", "CLI", "OtherReceiver"))
@pytest.mark.parametrize("bed_type", ("octo", "cosyworld"))
def test_shared_app_candidate_does_not_question_configured_receiver(name, bed_type):
    from custom_components.adjustable_bed.profile_recommendations import recommend_profile

    info = MagicMock(
        address="AA:BB:CC:DD:99:01",
        service_uuids=[app.SERVICE],
        manufacturer_data={},
        service_data={},
    )
    info.name = info.local_name = name
    assert recommend_profile({"bed_type": bed_type}, info, {}) is None


@pytest.mark.parametrize("subscription", ("notify", "indicate"))
async def test_native_subscription_modes_use_the_same_session_codec(runtime, subscription):
    _, c, client = runtime
    char = client.services[0].characteristics[0]
    char.properties = ["write-without-response", subscription]
    callbacks = []
    client.start_notify.side_effect = lambda target, cb: callbacks.append((target, cb))
    await c.start_notify()
    assert callbacks[0][0] is char
    callbacks[0][1](char, bytearray(c._build_packet([0x21, 0x43], [1])))
    assert c._pin_locked is False


@pytest.mark.parametrize("control", ("", "quad_other", "motor_0"))
async def test_invalid_saved_quad_selector_has_codec_proof_but_no_public_route(runtime, control):
    co, c, client = runtime
    complete(c, record(1, characteristic=b"\x04"))
    assert c.held_control_options == ("all_down",)
    with pytest.raises(ValueError, match="Unsupported OCTO held control"):
        await co.async_execute_controller_command(
            lambda controller: controller.hold_control(control, 350)
        )
    client.write_gatt_char.assert_not_called()


@pytest.mark.parametrize(
    "minutes,readonly,characteristic,value_type",
    (
        (0, 1, b"\x01", 1),
        (1, 1, b"\x01\x40", 2),
        (35, 0, b"\x01\x3c\x4f", 7),
        (60, 1, b"\x01\x41", 2),
    ),
)
async def test_duration_retains_alternate_peer_metadata_while_replacing_whole_value(
    runtime, minutes, readonly, characteristic, value_type
):
    co, c, client = runtime
    r = record(0x103, b"\x05\x40\x3c", characteristic, readonly, value_type)
    complete(c, r)
    await co.async_execute_controller_command(
        lambda controller: controller.set_light_timer(app.LIGHT_TIMER_OPTIONS[minutes]),
        resource="lighting",
    )
    assert writes(client) == [
        c._build_packet([0x20, 0x72], _encode_capability_value(r, bytes((minutes,))))
    ]
    assert c._capability_records[0x103] == r.with_value(bytes((minutes,)))


@pytest.fixture
async def public_hold_runtime(runtime, hass):
    from custom_components.adjustable_bed.services import async_register_services
    from tests.test_octo_services import _register_service_device

    co, c, client = runtime
    complete(c, record(2, characteristic=b"\x01"))
    co._ready = True
    co.async_ensure_connected = AsyncMock(return_value=True)
    device = _register_service_device(hass, co.entry, co)
    await async_register_services(hass)
    yield co, c, client, device
    co._cancel_disconnect_timer()


@pytest.mark.parametrize(
    "service,control,vector",
    (
        ("hold_control", "back_up", "V-M1-up"),
        ("hold_control", "memory_1", "V-recall-0"),
        ("goto_preset", None, "V-recall-0"),
    ),
)
@pytest.mark.parametrize(
    "latency,starts,release",
    (
        (0, [0.0, 0.35, 0.7], 1.0),
        (0.1, [0.0, 0.35, 0.7], 1.0),
        (0.4, [0.0, 0.4, 0.8], 1.2),
        (1.0, [0.0], 1.0),
        (1.2, [0.0], 1.2),
    ),
)
async def test_public_timed_hold_obeys_elapsed_deadline(
    public_hold_runtime, hass, service, control, vector, latency, starts, release
):
    _, _, client, device = public_hold_runtime
    events = []
    with virtual_clock() as clock:

        async def write(_char, payload, **_kwargs):
            events.append((round(clock.now, 6), bytes(payload)))
            await asyncio.sleep(latency)

        client.write_gatt_char.side_effect = write
        fields = {"control": control} if control is not None else {"preset": 1}
        await hass.services.async_call(
            const.DOMAIN,
            service,
            {"device_id": device.id, "duration": 1, **fields},
            blocking=True,
        )
        expected = bytes.fromhex(next(r["expected_bytes"] for r in VECTORS if r["id"] == vector))
        assert [at for at, data in events if data == expected] == starts
        assert events[-1] == (release, bytes.fromhex("40 02 73 00 00 0b 40"))
        # An already submitted frame and the cleanup write settle normally.
        assert clock.now == pytest.approx(release + latency)


@pytest.mark.parametrize("lane_released", (0.2, 1.1))
async def test_public_timed_hold_accounts_for_queued_ble_lane(
    public_hold_runtime, hass, lane_released
):
    _, c, client, device = public_hold_runtime
    await c._ble_lock.acquire()
    events = []
    with virtual_clock() as clock:

        async def unlock():
            await asyncio.sleep(lane_released)
            c._ble_lock.release()

        async def write(_char, payload, **_kwargs):
            events.append((round(clock.now, 6), bytes(payload)))

        client.write_gatt_char.side_effect = write
        unlocker = asyncio.create_task(unlock())
        await hass.services.async_call(
            const.DOMAIN,
            "hold_control",
            {"device_id": device.id, "control": "back_up", "duration": 1},
            blocking=True,
        )
        await unlocker
        if lane_released > 1:
            assert events == [(1.1, bytes.fromhex("40 02 73 00 00 0b 40"))]
        else:
            assert [at for at, _ in events] == [0.2, 0.55, 0.9, 1.0]
        assert clock.now == pytest.approx(max(1, lane_released))


@pytest.mark.parametrize("control", ("back_up", "memory_1"))
async def test_public_slow_timed_hold_cancellation_still_sends_fresh_stop(
    public_hold_runtime, hass, control
):
    co, _, client, device = public_hold_runtime
    events = []
    with virtual_clock() as clock:

        async def write(_char, payload, **_kwargs):
            if not events:
                asyncio.get_running_loop().call_later(0.2, co.cancel_command.set)
            events.append((round(clock.now, 6), bytes(payload)))
            await asyncio.sleep(0.6)

        client.write_gatt_char.side_effect = write
        await hass.services.async_call(
            const.DOMAIN,
            "hold_control",
            {"device_id": device.id, "control": control, "duration": 1},
            blocking=True,
        )
        assert len(events) == 2
        assert events[-1] == (0.6, bytes.fromhex("40 02 73 00 00 0b 40"))
        assert clock.now == pytest.approx(1.2)


@pytest.mark.parametrize(
    "service,operand,motion",
    (
        ("hold_control", {"control": "back_up"}, "40 02 70 00 01 0b 02 40"),
        ("goto_preset", {"preset": 1}, "40 02 72 00 01 0b 00 40"),
    ),
)
async def test_timed_hold_cannot_refresh_after_retained_link_subscription_recovery(
    public_hold_runtime, hass, service, operand, motion
):
    from bleak.exc import BleakError

    co, controller, client, device = public_hold_runtime
    generation = controller._session_generation
    co._link_ready = True
    client.start_notify.side_effect = None
    client.disconnect.side_effect = BleakError("receiver retained the live link")
    motion = bytes.fromhex(motion)
    moves = []
    with virtual_clock() as clock:

        async def write(_char, payload, **_kwargs):
            payload = bytes(payload)
            if payload in (motion, bytes.fromhex("40 02 73 00 00 0b 40")):
                moves.append((round(clock.now, 6), payload))
            if payload == app.STARTUP[0]:
                controller._ping_event.set()
            elif payload == app.STARTUP[1]:
                controller._device_info = {"cid": 1, "pid": 2, "firmware": 3, "hardware": 4}
                controller._device_info_event.set()
            elif payload == app.STARTUP[2]:
                complete(
                    controller, record(1, characteristic=b"\x02"),
                    record(2, characteristic=b"\x01"),
                    record(3, b"\x00\x01", characteristic=b"\x00"),
                )

        async def recover():
            await asyncio.sleep(0.1)
            assert not await co.async_disconnect(reason="sequential_switch")
            assert co.is_connected and controller._session_ready
            assert controller._session_generation != generation

        client.write_gatt_char.side_effect = write
        recovery = asyncio.create_task(recover())
        try:
            await hass.services.async_call(
                const.DOMAIN, service,
                {"device_id": device.id, "duration": 1, **operand}, blocking=True,
            )
        except HomeAssistantError:
            # The public service may translate the stale-session rejection.
            pass
        await recovery
        assert moves == [(0.0, motion)]


@pytest.mark.parametrize("name", ("BED-Linak", "RC2", "CLI"))
def test_cosyworld_hint_preserves_dedicated_confidence_and_shared_app_choice(name):
    from custom_components.adjustable_bed.config_flow import _confident_auto_detect
    from custom_components.adjustable_bed.detection import detect_bed_type_detailed
    from tests.test_detection import _make_service_info

    services = (
        [const.LINAK_CONTROL_SERVICE_UUID, app.SERVICE] if name == "BED-Linak" else [app.SERVICE]
    )
    result = detect_bed_type_detailed(_make_service_info(name, service_uuids=services))
    assert "cosyworld" in result.ambiguous_types
    assert _confident_auto_detect(result) == (const.BED_TYPE_LINAK if name == "BED-Linak" else None)


def test_cosyworld_hint_does_not_mask_dedicated_star2_recommendation():
    from custom_components.adjustable_bed.profile_recommendations import recommend_profile
    from tests.test_profile_recommendations import advertisement

    result = recommend_profile(
        {const.CONF_BED_TYPE: "octo", const.CONF_PROTOCOL_VARIANT: "standard"},
        advertisement("DA1458x", [const.OCTO_STAR2_SERVICE_UUID, app.SERVICE]),
        {},
    )
    assert result is not None and "octo:star2" in result.choices
