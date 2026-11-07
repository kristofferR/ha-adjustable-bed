"""Accepted row122 vectors and deliberate HA session/framing corrections."""

from __future__ import annotations

import asyncio
from datetime import datetime
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock

import pytest
from bleak.exc import BleakError

from custom_components.adjustable_bed.app_profiles import hidden_generic_fields, per_side_profile
from custom_components.adjustable_bed.bed_traits import bed_traits
from custom_components.adjustable_bed.beds.eshine_okin import EshineOkinController
from custom_components.adjustable_bed.beds.eshine_okin_protocol import (
    COMMANDS,
    HELD,
    NOTIFY_UUID,
    SERVICE_UUID,
    WRITE_UUID,
    alarm_frame,
    clock_frame,
    parse_notification,
)
from custom_components.adjustable_bed.const import (
    BED_TYPE_ESHINE_OKIN,
    CONF_HAS_MASSAGE,
    CONF_MOTOR_COUNT,
    CONF_MOTOR_PULSE_COUNT,
    CONF_MOTOR_PULSE_DELAY_MS,
    CONF_PROTOCOL_VARIANT,
    ESHINE_OKIN_PROFILES,
)
from custom_components.adjustable_bed.detection import get_bed_type_options
from custom_components.adjustable_bed.validators import get_variants_for_bed_type
from tests.state_helpers import state_writer

NOW = datetime.fromisoformat("2026-11-03T14:47:09+01:00")


def make(profile="eshine_e5000", *, properties=("notify",)):
    coordinator = MagicMock()
    coordinator.address = "AA:BB:CC:DD:EE:22"
    coordinator.cancel_command = asyncio.Event()
    coordinator.motor_pulse_count = 3
    coordinator.motor_pulse_delay_ms = 999
    coordinator.controller_state = {}
    coordinator.handle_controller_state_updates.side_effect = state_writer(coordinator.controller_state)
    write = SimpleNamespace(uuid=WRITE_UUID, properties=["write-without-response"], handle=1)
    notify = SimpleNamespace(uuid=NOTIFY_UUID, properties=list(properties), handle=2)
    coordinator.client = MagicMock(
        is_connected=True,
        services=[
            SimpleNamespace(
                uuid=SERVICE_UUID,
                characteristics=[write, notify],
            )
        ],
    )
    coordinator.client.write_gatt_char = AsyncMock()
    coordinator.client.start_notify = AsyncMock()
    coordinator.client.stop_notify = AsyncMock()
    return EshineOkinController(coordinator, profile=profile)


@pytest.fixture
def pauses(monkeypatch):
    delays = []

    async def pause(seconds, cancel):
        delays.append(seconds)
        return cancel.is_set()

    monkeypatch.setattr(EshineOkinController, "_pause", staticmethod(pause))
    return delays


def frames(ctrl):
    return [bytes(c.args[1]).hex() for c in ctrl.client.write_gatt_char.call_args_list]


# All 23 reachable fixed logical constructors. There is a second raw implementation
# of the chord; clock/alarm are the other two logical constructors.
VECTORS = [
    ("query_alarm", "00c0"),
    ("query_state", "00b0"),
    ("disable_alarm", "070500000000000000"),
    ("massage_wave", "05021000000000"),
    ("stop", "05020000000000"),
    ("tv", "05020000400000"),
    ("anti_snore", "05020000800000"),
    ("zero_g", "05020000100000"),
    ("feet_down", "05020000000800"),
    ("feet_up", "05020000000400"),
    ("head_down", "05020000000200"),
    ("head_up", "05020000000100"),
    ("pillow_down", "05020000002000"),
    ("pillow_up", "05020000001000"),
    ("light", "05020002000000"),
    ("flat", "05020800000000"),
    ("reading", "05020000200000"),
    ("massage_foot_strength", "05020000040000"),
    ("massage_head_strength", "05020000080000"),
    ("massage_timer", "05020000020000"),
    ("massage_off", "05020200000000"),
    ("massage_on", "05020000010000"),
    ("flat_zero_g", "05020800100000"),
]


@pytest.mark.parametrize(("action", "wire"), VECTORS)
async def test_every_fixed_constructor(action, wire, pauses):
    ctrl = make()
    await ctrl.async_discover_capabilities()
    ctrl._observed["massage"] = {"enabled": True}
    await ctrl.execute_action(action)
    expected = [wire] * (3 if action in HELD else 1)
    if action in HELD:
        expected.append("05020000000000")
    if action.startswith("massage_") or action == "light":
        expected.append("00b0")
    assert frames(ctrl) == expected
    assert all(c.kwargs["response"] is False for c in ctrl.client.write_gatt_char.call_args_list)
    if action in HELD:
        assert pauses[:3] == [0.3, 0.3, 0.2]
    if action.startswith("massage_"):
        assert pauses == [0.05]


@pytest.mark.parametrize("profile", ESHINE_OKIN_PROFILES)
def test_explicit_profiles_and_entity_contracts(profile):
    ctrl = make(profile)
    options = get_bed_type_options()
    assert any("eShine" in name and "E2000" in name for name in (o["label"] for o in options))
    assert get_variants_for_bed_type(BED_TYPE_ESHINE_OKIN) == ESHINE_OKIN_PROFILES
    assert bed_traits(BED_TYPE_ESHINE_OKIN).no_angle_feedback
    assert {s.key for s in ctrl.motor_control_specs} == (
        {"head", "feet", "pillow"} if profile == "eshine_e5000" else {"head", "feet"}
    )
    assert ctrl.supports_massage == (profile != "eshine_e2000")
    assert ctrl.supports_lights == ctrl.supports_massage
    assert ctrl.memory_slot_count == 0
    assert not ctrl.supports_position_feedback
    assert not ctrl.supports_single_address_pairing
    assert ctrl.motor_pulse_settings() == (3, 300)
    hidden = hidden_generic_fields(BED_TYPE_ESHINE_OKIN, profile)
    assert {CONF_MOTOR_COUNT, CONF_HAS_MASSAGE, CONF_MOTOR_PULSE_DELAY_MS} <= hidden
    assert CONF_PROTOCOL_VARIANT not in hidden and CONF_MOTOR_PULSE_COUNT not in hidden
    assert per_side_profile(BED_TYPE_ESHINE_OKIN, profile).variant_owned
    assert {s.key for s in ctrl.controller_state_sensor_specs} == (
        {"eshine_okin_alarm", "eshine_okin_massage"}
        if ctrl.supports_massage
        else {"eshine_okin_alarm"}
    )


@pytest.mark.parametrize("profile", ["auto", "", "unKnown", "e2000", "eshine_e6000"])
def test_no_profile_inference(profile):
    with pytest.raises(ValueError, match="Choose"):
        make(profile)


@pytest.mark.parametrize(
    "action", ["pillow_up", "pillow_down", "light", "massage_on", "massage_wave"]
)
async def test_profile_gates_before_writing(action, pauses):
    ctrl = make("eshine_e2000")
    await ctrl.async_discover_capabilities()
    with pytest.raises(ValueError):
        await ctrl.execute_action(action)
    assert frames(ctrl) == []


@pytest.mark.parametrize("properties", [("notify",), ("indicate",), ("notify", "indicate")])
async def test_session_initial_queries_and_subscription(properties, pauses):
    ctrl = make(properties=properties)
    await ctrl.async_discover_capabilities()
    await ctrl.start_notify()
    await ctrl.start_notify()
    assert frames(ctrl) == ["00b0", "00c0"]
    ctrl.client.start_notify.assert_awaited_once()
    assert pauses == [0.2]
    await ctrl.stop_notify()
    assert ctrl._session is None
    ctrl.client.stop_notify.assert_awaited_once()


@pytest.mark.parametrize("defect", ["service", "write", "notify", "write_mode", "subscribe"])
async def test_exact_gatt_roles_required(defect):
    ctrl = make()
    service = ctrl.client.services[0]
    if defect == "service":
        service.uuid = "0000fff0-0000-1000-8000-00805f9b34fb"
    if defect == "write":
        service.characteristics[0].uuid = NOTIFY_UUID
    if defect == "notify":
        service.characteristics[1].uuid = WRITE_UUID
    if defect == "write_mode":
        service.characteristics[0].properties = ["write"]
    if defect == "subscribe":
        service.characteristics[1].properties = ["read"]
    with pytest.raises(ValueError, match="exact UART"):
        await ctrl.async_discover_capabilities()


async def test_cancellation_release_ignores_cancel_and_never_reuses_mutable_packet(pauses):
    ctrl = make()
    await ctrl.async_discover_capabilities()

    async def cancel_on_write(*args, **kwargs):
        ctrl._coordinator.cancel_command.set()

    ctrl.client.write_gatt_char.side_effect = cancel_on_write
    await ctrl.move_head_up()
    assert frames(ctrl) == ["05020000000100", "05020000000000"]
    assert pauses == [0.2]


async def test_task_cancel_and_ble_error_still_release(pauses):
    for error in (asyncio.CancelledError(), BleakError("write failed")):
        ctrl = make()
        await ctrl.async_discover_capabilities()
        ctrl.client.write_gatt_char.side_effect = [error, None]
        with pytest.raises(type(error)):
            await ctrl.move_head_up()
        assert frames(ctrl) == ["05020000000100", "05020000000000"]


async def test_changed_session_cannot_receive_repeat_or_stop(pauses, monkeypatch):
    ctrl = make()
    await ctrl.async_discover_capabilities()
    original = ctrl.client

    async def swap(seconds, cancel):
        ctrl._coordinator.client = MagicMock(is_connected=True, write_gatt_char=AsyncMock())
        return False

    monkeypatch.setattr(ctrl, "_pause", swap)
    with pytest.raises(ConnectionError):
        await ctrl.move_head_up()
    assert len(original.write_gatt_char.call_args_list) == 1
    ctrl.client.write_gatt_char.assert_not_awaited()


async def test_cancelled_delayed_queries_do_not_survive_operation(pauses, monkeypatch):
    ctrl = make()
    await ctrl.async_discover_capabilities()

    async def cancel(seconds, event):
        event.set()
        return True

    monkeypatch.setattr(ctrl, "_pause", cancel)
    await ctrl.execute_action("massage_on")
    assert frames(ctrl) == ["05020000010000"]


def test_clock_and_alarm_vectors():
    assert clock_frame(NOW).hex() == "07041a0b03020e2f09"
    assert clock_frame(NOW.replace(year=1999)).hex() == "0704ff0b03030e2f09"
    assert alarm_frame(NOW, 16, 30, "zero_g").hex() == "07050401101e000101"
    assert alarm_frame(NOW, 12, 0, "flat").hex() == "070508090c00000101"
    assert alarm_frame(NOW.replace(day=7), 12, 0, "massage").hex() == "070501080c00000101"


async def test_alarm_double_set_query_order_and_clock(pauses, monkeypatch):
    monkeypatch.setattr(
        "custom_components.adjustable_bed.beds.eshine_okin.dt_util.now", lambda: NOW
    )
    ctrl = make()
    await ctrl.async_discover_capabilities()
    await ctrl.configure_clock_alarm(enabled=True, weekdays=(), hour=16, minute=30, preset="flat")
    assert frames(ctrl) == ["07050409101e000101", "00c0", "07050409101e000101", "00c0"]
    assert pauses == [0.2, 0.2]
    ctrl.client.write_gatt_char.reset_mock()
    await ctrl.configure_clock_alarm(enabled=False, weekdays=(), hour=0, minute=0, preset="zero_g")
    assert frames(ctrl) == ["070500000000000000", "00c0"]
    ctrl.client.write_gatt_char.reset_mock()
    await ctrl.sync_clock()
    assert frames(ctrl) == ["07041a0b03020e2f09", "00c0"]


@pytest.mark.parametrize(
    ("seconds", "index"),
    [(0, 0), (1, 1), (599, 1), (600, 1), (601, 2), (1200, 2), (1800, 3), (65535, 110)],
)
def test_timer_and_unclamped_consumer_arithmetic(seconds, index):
    data = bytearray.fromhex("a50b0e00000000ffff000000000100")
    data[4:6] = seconds.to_bytes(2, "big")
    parsed = parse_notification(bytes(data), NOW)
    assert parsed is not None
    group, state = parsed
    assert group == "massage" and state["timer_index"] == index
    assert state["head"] == (6 if index else 0)
    assert state["foot"] == (86 if index else 0)
    assert state["wave"] == (-1 if index else 0)
    assert state["light"] is True and state["combined"] == 86


@pytest.mark.parametrize(
    ("packet", "enabled", "selection"),
    [
        ("a50c0e00000110200001", True, 1),
        ("a50c0e00000910200001", True, 2),
        ("a50c0e00000810200002", True, 3),
        ("a50c0e00000000000001", False, 1),
        ("a50c0e00000000000002", True, 0),
        ("a50c0e000008ffff0001", True, 3),
        ("a50c0e00000810200000", False, 1),
    ],
)
def test_alarm_consumers(packet, enabled, selection):
    parsed = parse_notification(bytes.fromhex(packet), NOW)
    assert parsed is not None
    group, state = parsed
    assert group == "alarm"
    assert state["enabled"] is enabled and state["selection"] == selection
    if packet.endswith("ffff0001"):
        assert state["date"] == "2026-11-13T19:15:09+01:00"


@pytest.mark.parametrize("header,length", [("a50b0e", 14), ("a50c0e", 10)])
def test_truncated_packets_are_atomic_and_unknown_headers_ignored(header, length):
    for n in range(length):
        assert parse_notification((bytes.fromhex(header) + bytes(30))[:n], NOW) is None
    assert parse_notification(bytes.fromhex("fffe16") + bytes(17), NOW) is None
    assert parse_notification(bytes.fromhex("a50b0e000258010101000000000100"), NOW)[0] == "massage"


async def test_receive_state_entity_attributes_stale_callbacks_and_reconnect(pauses):
    ctrl = make()
    await ctrl.async_discover_capabilities()
    await ctrl.start_notify()
    notify, receive = ctrl.client.start_notify.call_args.args
    receive(notify, bytearray.fromhex("a50b0e000258010101000000000100"))
    state = cast(dict[str, Any], ctrl._coordinator.controller_state)
    assert state["under_bed_lights_on"] is True
    assert state["eshine_okin_massage_data"]["head"] == 1
    receive(notify, bytearray.fromhex("fffe16") + bytearray(17))
    receive(notify, bytearray.fromhex("a50c0e00000810200001"))
    assert state["eshine_okin_alarm_data"]["selection"] == 3
    await ctrl.stop_notify()
    receive(notify, bytearray.fromhex("a50b0e000000010101000000000000"))
    assert state["under_bed_lights_on"] is None
    await ctrl.async_discover_capabilities()
    assert state["under_bed_lights_on"] is None
    assert state["eshine_okin_alarm_data"] is None
    await ctrl.start_notify()
    receive(notify, bytearray.fromhex("a50b0e000258010101000000000000"))
    assert state["under_bed_lights_on"] is None


async def test_held_named_preset_and_chord_use_same_frames_without_invented_save(pauses):
    ctrl = make()
    await ctrl.async_discover_capabilities()
    await ctrl.hold_control("flat_zero_g", 5500)
    assert set(frames(ctrl)[:-1]) == {"05020800100000"}
    assert frames(ctrl)[-1] == "05020000000000"
    assert pauses[-1] == 0.2
    ctrl.client.write_gatt_char.reset_mock()
    ctrl.client.write_gatt_char.side_effect = TimeoutError("ATT timeout")
    with pytest.raises(TimeoutError):
        await ctrl.hold_control("head_up", 600)
    assert len(frames(ctrl)) == 2  # Failing move followed by attempted release.


@pytest.mark.parametrize("profile", ESHINE_OKIN_PROFILES)
async def test_factory_and_manual_selection(hass, profile):
    from homeassistant.const import CONF_ADDRESS
    from pytest_homeassistant.common import MockConfigEntry

    from custom_components.adjustable_bed.config_flow import AdjustableBedConfigFlow
    from custom_components.adjustable_bed.const import CONF_BED_TYPE, DOMAIN
    from custom_components.adjustable_bed.controller_factory import create_controller
    from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
    from custom_components.adjustable_bed.validators import is_valid_variant_for_bed_type

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_ADDRESS: "AA:BB:CC:DD:EE:22",
            CONF_BED_TYPE: BED_TYPE_ESHINE_OKIN,
            CONF_PROTOCOL_VARIANT: profile,
        },
    )
    coordinator = AdjustableBedCoordinator(hass, entry)
    controller = await create_controller(
        coordinator, BED_TYPE_ESHINE_OKIN, protocol_variant=profile, client=None
    )
    assert isinstance(controller, EshineOkinController) and controller.profile.key == profile
    assert is_valid_variant_for_bed_type(BED_TYPE_ESHINE_OKIN, profile)
    assert not is_valid_variant_for_bed_type(BED_TYPE_ESHINE_OKIN, "auto")
    from tests.form_helpers import finish_new_bed, start_new_bed

    flow = AdjustableBedConfigFlow()
    flow.hass, flow.context = hass, {}
    flow._finish_with_verify = AsyncMock(return_value={"type": "create_entry"})
    result = await start_new_bed(flow, "typed", f"eshine_okin:{profile}", "AA:BB:CC:DD:EE:22")
    await finish_new_bed(flow, result)
    saved = flow._finish_with_verify.await_args.args[0]
    assert saved[CONF_BED_TYPE] == BED_TYPE_ESHINE_OKIN
    assert saved[CONF_PROTOCOL_VARIANT] == profile


@pytest.fixture
async def ha_target(hass):
    from homeassistant.config_entries import ConfigEntryState
    from homeassistant.const import CONF_ADDRESS, CONF_NAME
    from homeassistant.helpers import device_registry as dr
    from pytest_homeassistant.common import MockConfigEntry

    from custom_components.adjustable_bed import services
    from custom_components.adjustable_bed.const import CONF_BED_TYPE, DOMAIN
    from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator

    entry = MockConfigEntry(
        domain=DOMAIN,
        title="eShine",
        data={
            CONF_ADDRESS: "AA:BB:CC:DD:EE:22",
            CONF_NAME: "eShine",
            CONF_BED_TYPE: BED_TYPE_ESHINE_OKIN,
            CONF_PROTOCOL_VARIANT: "eshine_e5000",
        },
    )
    entry.add_to_hass(hass)
    entry.mock_state(hass, ConfigEntryState.LOADED)
    coordinator = AdjustableBedCoordinator(hass, entry)
    coordinator._controller = EshineOkinController(coordinator, profile="eshine_e5000")
    coordinator.async_execute_controller_command = AsyncMock()
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, entry.data[CONF_ADDRESS])},
    )
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await services.async_register_services(hass)
    return coordinator, device.id


async def test_alarm_service_validation_and_serialized_execution(hass, ha_target):
    from homeassistant.exceptions import ServiceValidationError

    from custom_components.adjustable_bed.const import DOMAIN

    coordinator, device_id = ha_target
    data = {"device_id": [device_id], "enabled": True, "time": "06:30:00", "wake_mode": "massage"}
    await hass.services.async_call(DOMAIN, "eshine_set_alarm", data, blocking=True)
    coordinator.async_execute_controller_command.assert_awaited_once()
    command = coordinator.async_execute_controller_command.await_args.args[0]
    controller = MagicMock(sync_clock=AsyncMock(), configure_clock_alarm=AsyncMock())
    await command(controller)
    controller.sync_clock.assert_awaited_once()
    controller.configure_clock_alarm.assert_awaited_once_with(
        enabled=True,
        weekdays=(),
        hour=6,
        minute=30,
        preset="massage",
    )
    coordinator.async_execute_controller_command.reset_mock()
    for invalid in ({**data, "time": "06:30:01"}, {"device_id": [device_id], "enabled": True}):
        with pytest.raises(ServiceValidationError):
            await hass.services.async_call(DOMAIN, "eshine_set_alarm", invalid, blocking=True)
    coordinator._controller = EshineOkinController(coordinator, profile="eshine_e2000")
    with pytest.raises(ServiceValidationError, match="does not expose"):
        await hass.services.async_call(DOMAIN, "eshine_set_alarm", data, blocking=True)
    coordinator._bed_type = "eshine"  # E6000 is a different app, despite shared branding.
    with pytest.raises(ServiceValidationError, match="Choose an eShine"):
        await hass.services.async_call(DOMAIN, "eshine_set_alarm", data, blocking=True)
    coordinator.async_execute_controller_command.assert_not_awaited()


@pytest.mark.parametrize("profile", ESHINE_OKIN_PROFILES)
async def test_platform_exposure_and_entity_queue(hass, ha_target, profile):
    from custom_components.adjustable_bed import sensor
    from custom_components.adjustable_bed.button import (
        ControllerActionButton,
        _button_entities_for,
    )
    from custom_components.adjustable_bed.cover import _cover_entities_for

    coordinator, _ = ha_target
    coordinator._controller = EshineOkinController(coordinator, profile=profile)
    ctrl = coordinator._controller
    covers = _cover_entities_for(hass, coordinator)
    assert len(covers) == (3 if profile == "eshine_e5000" else 2)
    buttons = _button_entities_for(hass, coordinator)
    keys = {b.entity_description.key for b in buttons if hasattr(b, "entity_description")}
    assert {
        "preset_flat",
        "preset_zero_g",
        "preset_anti_snore",
        "preset_tv",
        "preset_reading",
    } <= keys
    assert "toggle_light" not in keys  # Feedback light replaces the estimated toggle button.
    assert ("massage_mode_step" in keys) == ctrl.supports_massage
    assert not any("memory_" in key for key in keys)
    extra = next(
        b
        for b in buttons
        if isinstance(b, ControllerActionButton) and b._spec.key == "eshine_okin_flat_zero_g"
    )
    await extra.async_press()
    coordinator.async_execute_controller_command.assert_awaited_once()
    received = []
    await sensor.async_setup_entry(hass, coordinator.entry, received.extend)
    assert any(s.unique_id == coordinator.entity_unique_id("eshine_okin_alarm") for s in received)
    assert (
        any(s.unique_id == coordinator.entity_unique_id("eshine_okin_massage") for s in received)
        == ctrl.supports_massage
    )


@pytest.mark.parametrize("name", ["Smartbed", "prefix Smartbed suffix", "smartbed", "SMARTBED"])
def test_discovery_candidate_never_selects_a_product(name):
    from custom_components.adjustable_bed.detection import detect_bed_type_detailed

    info = MagicMock(name=name)
    info.name, info.device.name = name, name
    info.address, info.rssi = "AA:BB:CC:DD:EE:22", -60
    info.service_uuids, info.manufacturer_data = [SERVICE_UUID], {}
    result = detect_bed_type_detailed(info)
    candidates = [result.bed_type, *(result.ambiguous_types or ())]
    assert (BED_TYPE_ESHINE_OKIN in candidates) == ("Smartbed" in name)
    assert not any("eshine_e" in signal for signal in result.signals)


async def test_public_hold_sync_and_all_target_alarm_preflight(hass, ha_target, monkeypatch):
    from homeassistant.exceptions import ServiceValidationError

    from custom_components.adjustable_bed import eshine_okin_services
    from custom_components.adjustable_bed.const import DOMAIN, SIDE_BOTH

    coordinator, device_id = ha_target
    await hass.services.async_call(
        DOMAIN,
        "hold_control",
        {
            "device_id": [device_id],
            "control": "flat_zero_g",
            "duration": 5.5,
        },
        blocking=True,
    )
    command = coordinator.async_execute_controller_command.await_args.args[0]
    fake = MagicMock(hold_control=AsyncMock())
    await command(fake)
    fake.hold_control.assert_awaited_once_with("flat_zero_g", 5500)
    coordinator.async_execute_controller_command.reset_mock()
    await hass.services.async_call(DOMAIN, "sync_clock", {"device_id": [device_id]}, blocking=True)
    coordinator.async_execute_controller_command.assert_awaited_once()
    coordinator.async_execute_controller_command.reset_mock()
    # Two physical targets must both validate before either command is queued.
    other = MagicMock(spec=type(coordinator))
    other.bed_type = BED_TYPE_ESHINE_OKIN
    other.name = "E2000"
    other.capability_controller = make("eshine_e2000")
    other.is_connected = True
    other.async_execute_controller_command = AsyncMock()
    monkeypatch.setattr(
        eshine_okin_services,
        "_call_targets",
        lambda call: [(coordinator, SIDE_BOTH), (other, SIDE_BOTH)],
    )
    with pytest.raises(ServiceValidationError, match="does not expose"):
        await hass.services.async_call(
            DOMAIN,
            "eshine_set_alarm",
            {
                "device_id": [device_id],
                "enabled": True,
                "time": "06:30:00",
                "wake_mode": "massage",
            },
            blocking=True,
        )
    coordinator.async_execute_controller_command.assert_not_awaited()
    other.async_execute_controller_command.assert_not_awaited()


async def test_disconnect_hook_immediately_invalidates_live_state_and_old_callbacks(pauses):
    ctrl = make()
    await ctrl.async_discover_capabilities()
    await ctrl.start_notify()
    notify, receive = ctrl.client.start_notify.call_args.args
    receive(notify, bytearray.fromhex("a50b0e000258010101000000000100"))
    assert ctrl._coordinator.controller_state["under_bed_lights_on"] is True
    ctrl.on_disconnect()
    assert ctrl._coordinator.controller_state["under_bed_lights_on"] is None
    # Some transports deliver a queued callback before updating is_connected.
    receive(notify, bytearray.fromhex("a50b0e000258010101000000000100"))
    assert ctrl._coordinator.controller_state["under_bed_lights_on"] is None
    with pytest.raises(ConnectionError):
        await ctrl.write_command(COMMANDS["query_state"])


@pytest.mark.parametrize("caller_cancel", [False, True])
async def test_coordinator_cancellation_drains_delayed_stop(monkeypatch, caller_cancel):
    from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator

    ctrl = make()
    await ctrl.async_discover_capabilities()
    first_write = asyncio.Event()
    release_started = asyncio.Event()
    allow_release = asyncio.Event()
    original_pause = ctrl._pause

    async def pause(seconds, cancel):
        if seconds == 0.2:
            release_started.set()
            await allow_release.wait()
            return False
        return await original_pause(seconds, cancel)

    async def record(*args, **kwargs):
        first_write.set()

    monkeypatch.setattr(ctrl, "_pause", pause)
    ctrl.client.write_gatt_char.side_effect = record
    operation = asyncio.create_task(ctrl.move_head_up())
    waiting = asyncio.create_task(
        AdjustableBedCoordinator._async_wait_for_controller_operation(
            ctrl._coordinator,
            operation,
            cancel_event=ctrl._coordinator.cancel_command,
            operation_name="command",
            raise_on_cancel=True,
        )
    )
    try:
        async with asyncio.timeout(1):
            await first_write.wait()
            ctrl._coordinator.cancel_command.set()
            await release_started.wait()
            if caller_cancel:
                waiting.cancel()  # A second cancellation while the release task drains.
            assert frames(ctrl) == ["05020000000100"]
            assert not waiting.done()
            allow_release.set()
            with pytest.raises(asyncio.CancelledError):
                await waiting
        assert operation.done()
        assert frames(ctrl) == ["05020000000100", "05020000000000"]
    finally:
        allow_release.set()
        if not waiting.done():
            waiting.cancel()
        await asyncio.gather(waiting, operation, return_exceptions=True)


async def test_reported_light_drives_enabled_entity_and_safe_desired_state(
    hass, ha_target, pauses, monkeypatch
):
    from custom_components.adjustable_bed.light import AdjustableBedOnOffLight, _light_entities_for

    coordinator, _ = ha_target
    ctrl = make()
    coordinator._controller = ctrl
    # Use the real HA callback registry, not a direct call to the entity handler.
    ctrl._coordinator.handle_controller_state_updates.side_effect = (
        coordinator.handle_controller_state_updates
    )
    await ctrl.async_discover_capabilities()
    await ctrl.start_notify()
    notify, receive = ctrl.client.start_notify.call_args.args
    (entity,) = _light_entities_for(hass, coordinator)
    assert isinstance(entity, AdjustableBedOnOffLight)
    assert entity.entity_registry_enabled_default
    entity.hass = hass
    monkeypatch.setattr(entity, "async_write_ha_state", MagicMock())
    await entity.async_added_to_hass()
    try:
        assert entity.is_on is None
        with pytest.raises(ValueError, match="Refresh light state"):
            await ctrl.lights_on()
        receive(notify, bytearray.fromhex("a50b0e000258010101000000000100"))
        assert entity.is_on is True
        ctrl.client.write_gatt_char.reset_mock()
        await ctrl.lights_on()
        assert frames(ctrl) == []  # Reported state already matches, do not toggle.
        await ctrl.lights_off()
        assert frames(ctrl) == ["05020002000000"] * 3 + ["05020000000000", "00b0"]
        assert entity.is_on is True  # No optimistic inversion without telemetry.
        receive(notify, bytearray.fromhex("a50b0e000258010101000000000000"))
        assert entity.is_on is False
        ctrl.on_disconnect()
        assert entity.is_on is None
    finally:
        await entity.async_will_remove_from_hass()


async def test_profile_change_removes_obsolete_actions_and_retains_sibling_registry(
    hass, ha_target
):
    from homeassistant.helpers import entity_registry as er

    from custom_components.adjustable_bed.button import _button_entities_for
    from custom_components.adjustable_bed.const import DOMAIN

    coordinator, _ = ha_target
    registry = er.async_get(hass)
    old_keys = [spec.key for spec in coordinator._controller.controller_button_specs]
    old = {
        key: registry.async_get_or_create(
            "button",
            DOMAIN,
            coordinator.entity_unique_id(key),
            config_entry=coordinator.entry,
        ).entity_id
        for key in old_keys
    }
    sibling = registry.async_get_or_create(
        "button",
        DOMAIN,
        "other_address_eshine_okin_massage_on",
        config_entry=coordinator.entry,
    )
    coordinator._controller = EshineOkinController(coordinator, profile="eshine_e2000")
    _button_entities_for(hass, coordinator)
    for key, entity_id in old.items():
        assert (registry.async_get(entity_id) is None) == key.startswith("eshine_okin_massage_")
    assert registry.async_get(sibling.entity_id) is not None


async def test_motor_covers_publish_controller_owned_hold_metadata(hass, ha_target):
    from custom_components.adjustable_bed.cover import _cover_entities_for

    coordinator, _ = ha_target
    covers = _cover_entities_for(hass, coordinator)
    for cover in covers:
        key = cover.entity_description.key
        assert cover.extra_state_attributes["held_control_up"] == f"{key}_up"
        assert cover.extra_state_attributes["held_control_down"] == f"{key}_down"
        assert cover.extra_state_attributes["hold_release_delay_ms"] == 0


async def test_manual_scan_retains_nonprefixed_name_only_app_candidate(hass, monkeypatch):
    from custom_components.adjustable_bed.config_flow import AdjustableBedConfigFlow
    from tests.test_detection import _make_service_info

    info = _make_service_info(name="prefix Smartbed suffix")
    monkeypatch.setattr(
        "custom_components.adjustable_bed.config_flow.get_discovered_service_info",
        lambda *args, **kwargs: [info],
    )
    flow = AdjustableBedConfigFlow()
    flow.hass, flow.context = hass, {}
    result = await flow.async_step_user()
    assert result["type"] == "form"
    assert info.address in flow._discovered_devices
