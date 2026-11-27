"""Sealy FlexiRest's frozen packets and native, session-owned bed controls."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.adjustable_bed.alarm import AlarmRequest
from custom_components.adjustable_bed.beds.solace.controller import preset_selected
from custom_components.adjustable_bed.beds.solace.flexirest import FAULT, FlexirestController
from custom_components.adjustable_bed.beds.solace.sophie_state import (
    ALARM_ENABLED,
    ALARM_MODE,
    ALARM_TIME,
    FOOT_LEVEL,
    HEAD_LEVEL,
    WAVE,
)
from custom_components.adjustable_bed.codec import ff_frame as codec
from custom_components.adjustable_bed.controller_state import ControllerState
from custom_components.adjustable_bed.profiles import flexirest as app
from custom_components.adjustable_bed.state_keys import LIGHT_LEVEL, SYNCHRO_MODE
from tests.state_helpers import state_writer

VECTORS = json.loads((Path(__file__).parent / "fixtures/flexirest/vectors.json").read_text())


@pytest.mark.parametrize("row", VECTORS, ids=lambda row: row["id"])
def test_all_accepted_literals_match_existing_codec(row):
    x = row["inputs"]
    if x["kind"] == "literal":
        literal = bytes.fromhex(x["hex"])
        if literal[4] == 5:
            actual = codec.control(literal[8], arg=literal[7], group=literal[6])
        elif literal[4] == 3:
            actual = codec.query(literal[6], literal[8])
        else:
            actual = codec.summed(literal[4], literal[6], literal[8:-2])
    elif x["kind"] == "clock":
        y, month, day, hour, minute, second, weekday = x["date"]
        actual = codec.clock(datetime(y, month, day, hour, minute, second), weekday)
    elif x["kind"] == "alarm":
        actual = codec.alarm(
            switch=1 if x["enabled"] else 0xA1,
            hour=int(x["hour"]),
            minute=int(x["minute"]),
            weekday_mask=sum(1 << int(day) for day, selected in x["days"].items() if selected),
            repeat=bool(x["days"]),
            mode=int(x["mode"], 16),
            massage=x["massage"],
            sound=int(x["sound"], 16),
        )
    else:
        prefix = bytes.fromhex(x["prefix"])
        actual = codec.summed(prefix[4], prefix[6], prefix[8:])
    assert actual.hex().upper() == row["expected_bytes"]


@pytest.fixture
async def controller():
    co = MagicMock()
    co.controller_state = ControllerState()
    co.handle_controller_state_updates.side_effect = state_writer(co.controller_state)
    co.address = "AA:BB:CC:DD:EE:FF"
    co.entry.data = {"bed_type": "solace", "protocol_variant": "flexirest"}
    co.ble_device_name = "Sealy K1"
    co.connection_generation = 1
    co.cancel_counter = 0
    co.cancel_command = asyncio.Event()
    char = SimpleNamespace(uuid=codec.CHARACTERISTIC_UUID, handle=9, properties=["write", "notify"])
    co.client = MagicMock(is_connected=True)
    co.client.services = [SimpleNamespace(uuid="unproven-service", characteristics=[char])]
    co.client.write_gatt_char = AsyncMock()
    co.client.start_notify = AsyncMock()
    co.client.stop_notify = AsyncMock()
    ctrl = FlexirestController(co)
    co.controller = ctrl
    await ctrl.start_notify()
    yield ctrl
    ctrl.on_disconnect()


def frames(ctrl):
    return [call.args[1].hex().upper() for call in ctrl.client.write_gatt_char.await_args_list]


@pytest.mark.parametrize("audio", [False, True])
async def test_alarm_audio_capability_survives_controller_replacement(controller, audio):
    from custom_components.adjustable_bed.alarm import AlarmRequest

    controller._parse_notification(bytes.fromhex(
        f"FFFFFFFF01000413{'1F' if audio else '0F'}0730002201020111"
    ))
    sounds = controller.alarm_capability.sounds
    coordinator = controller._coordinator
    controller.on_disconnect()
    replacement = FlexirestController(coordinator)
    coordinator.controller = replacement
    await replacement.start_notify()
    assert replacement.alarm_capability.sounds == sounds
    await replacement.configure_alarm(AlarmRequest(
        enabled=True, hour=7, minute=30, wake_action="zero_g",
        sound="music_1" if audio else "alarm",
        reference_time=datetime(2026, 11, 27, 6),
    ))
    assert frames(replacement)
    replacement.on_disconnect()


@pytest.mark.parametrize(
    "method,command_id",
    [
        ("move_back_up", "V-C001"),
        ("move_back_down", "V-C002"),
        ("move_legs_up", "V-C003"),
        ("move_legs_down", "V-C004"),
    ],
)
async def test_native_axes_one_press_then_release(controller, method, command_id):
    async def cancel(*_, **__):
        controller._coordinator.cancel_command.set()

    controller.client.write_gatt_char.side_effect = cancel
    await getattr(controller, method)()
    expected = next(row["expected_bytes"] for row in VECTORS if row["id"] == command_id)
    assert frames(controller) == [expected, "FFFFFFFF0500000000D700"]
    assert [spec.key for spec in controller.motor_control_specs] == ["back", "legs"]
    assert controller.execution.hold == "latched" and not controller.execution.concurrent


async def test_cancelled_dispatched_write_settles_before_original_link_release(controller):
    entered, finish = asyncio.Event(), asyncio.Event()
    original = controller.client
    written = []

    async def write(char, frame, **_):
        written.append(frame)
        if frame != codec.STOP:
            entered.set()
            await finish.wait()

    original.write_gatt_char.side_effect = write
    task = asyncio.create_task(controller.hold_control("back_up", 100))
    await entered.wait()
    task.cancel()
    replacement = MagicMock(is_connected=True)
    replacement.write_gatt_char = AsyncMock()
    controller._coordinator.client = replacement
    controller._coordinator.connection_generation += 1
    await asyncio.sleep(0)
    assert not task.done() and written == [codec.control(3)]
    finish.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert written == [codec.control(3), codec.STOP]
    replacement.write_gatt_char.assert_not_called()


async def test_cancel_before_admission_writes_nothing(controller):
    controller._coordinator.cancel_command.set()
    with pytest.raises(asyncio.CancelledError):
        await controller.hold_control("legs_down", 100)
    assert frames(controller) == []


@pytest.mark.parametrize("held", [False, True])
async def test_cancellation_at_settled_dispatch_does_not_send_a_late_frame(
    controller, monkeypatch, held
):
    original = controller._emit

    async def queued(*args, **kwargs):
        asyncio.get_running_loop().call_soon(controller._coordinator.cancel_command.set)
        await original(*args, **kwargs)

    monkeypatch.setattr(controller, "_emit", queued)
    with pytest.raises(asyncio.CancelledError):
        if held:
            await controller.hold_control("back_up", 100)
        else:
            await controller.preset_flat()
    assert frames(controller) == []


async def test_settings_and_notifications_cannot_cross_profile_change(controller):
    old_callback = controller.client.start_notify.call_args.args[1]
    controller._coordinator.entry.data["protocol_variant"] = "sophie"
    with pytest.raises(ConnectionError, match="session changed"):
        await controller.preset_flat()
    old_callback(None, bytearray.fromhex("FFFFFFFF05000105"))
    assert LIGHT_LEVEL not in controller._coordinator.controller_state
    assert frames(controller) == []


async def test_completed_old_link_setting_does_not_publish_to_replacement(controller):
    controller._parse_notification(bytes.fromhex("FFFFFFFF01000A0B00"))
    original = controller.client

    async def replace_link(*_, **__):
        controller._coordinator.client = MagicMock(is_connected=True)
        controller._coordinator.connection_generation += 1

    original.write_gatt_char.side_effect = replace_link
    with pytest.raises(ConnectionError, match="during write"):
        await controller.set_synchro(True)
    assert controller._coordinator.controller_state[SYNCHRO_MODE] is False


async def test_last_ffe1_any_service_and_property_selected_write_mode(controller):
    first = controller.client.services[0].characteristics[0]
    last = SimpleNamespace(
        uuid=first.uuid, handle=12, properties=["write-without-response", "notify"]
    )
    controller.client.services.append(
        SimpleNamespace(uuid="another-service", characteristics=[last])
    )
    await controller.preset_flat()
    call = controller.client.write_gatt_char.call_args
    assert call.args[0] is last and call.kwargs["response"] is False


@pytest.mark.parametrize(
    "index,code,key",
    [
        (0, 0x0A, "memory_1"),
        (1, 0x0B, "memory_2"),
        (2, 5, "tv"),
        (3, 9, "zero_g"),
        (4, 15, "anti_snore"),
    ],
)
async def test_saved_echo_drives_clear_and_recall(controller, index, code, key):
    await controller.save_preset(key)
    assert bytes.fromhex(frames(controller)[-1]) == codec.control(code, arg=code << 4)
    assert preset_selected(key) not in controller._coordinator.controller_state
    controller._parse_notification(codec.HEADER + bytes((3, 6, 0, code)))
    assert controller._coordinator.controller_state[preset_selected(key)] is True
    await controller.save_preset(key)
    assert bytes.fromhex(frames(controller)[-1]) == codec.control(code, arg=(code << 4) | 15)
    if index < 2:
        await controller.preset_memory(index + 1)
    else:
        await getattr(controller, f"preset_{key}")()
    assert bytes.fromhex(frames(controller)[-1]) == codec.control(code, arg=(code << 4) | 1)
    controller._parse_notification(codec.control(code, arg=(code << 4) | 15))
    assert controller._coordinator.controller_state[preset_selected(key)] is False


@pytest.mark.parametrize(
    "wire,key,value",
    [
        ("FFFFFFFF0500000100D690", HEAD_LEVEL, 0),
        ("FFFFFFFF050000011E5698", HEAD_LEVEL, 1),
        ("FFFFFFFF050000011F9758", HEAD_LEVEL, 2),
        ("FFFFFFFF0500000120D748", HEAD_LEVEL, 3),
        ("FFFFFFFF0500000200D660", FOOT_LEVEL, 0),
        ("FFFFFFFF05000002211678", FOOT_LEVEL, 1),
        ("FFFFFFFF05000002225679", FOOT_LEVEL, 2),
        ("FFFFFFFF050000022397B9", FOOT_LEVEL, 3),
        ("FFFFFFFF0500000324D7EB", WAVE, 1),
        ("FFFFFFFF0500000325162B", WAVE, 2),
        ("FFFFFFFF0500000326562A", WAVE, 3),
        ("FFFFFFFF050000032797EA", WAVE, 4),
    ],
)
async def test_exact_massage_reports(controller, wire, key, value):
    controller._parse_notification(bytes.fromhex(wire))
    assert controller._coordinator.controller_state[key] == value


async def test_light_reply_gate_and_distinct_off(controller):
    with pytest.raises(ValueError, match="brightness support"):
        await controller.set_light_level(1)
    await controller.lights_off()
    assert frames(controller) == ["FFFFFFFF050000004B9737"]
    controller._parse_notification(bytes.fromhex("FFFFFFFF05000105"))
    await controller.set_light_level(10)
    assert frames(controller)[-1] == "FFFFFFFF0500000A239079"
    assert controller._coordinator.controller_state[LIGHT_LEVEL] == 5
    controller._parse_notification(bytes.fromhex("FFFFFFFF050001FF"))
    assert controller._coordinator.controller_state[LIGHT_LEVEL] is None
    assert controller.protocol_diagnostics["light_level"] == "255"


async def test_alarm_audio_and_sync_records_have_separate_semantics(controller):
    controller._parse_notification(bytes.fromhex("FFFFFFFF01000A0B01"))
    assert controller._coordinator.controller_state[SYNCHRO_MODE] is True
    controller._parse_notification(bytes.fromhex("FFFFFFFF010004131F0730002201020111"))
    assert controller._coordinator.controller_state[ALARM_ENABLED] is True
    assert controller._coordinator.controller_state[ALARM_TIME] == "07:30"
    assert controller._coordinator.controller_state[SYNCHRO_MODE] is True
    assert controller.alarm_capability.sounds == (
        "none",
        "music_1",
        "music_2",
        "music_3",
        "music_4",
        "music_5",
    )
    await controller.configure_alarm(
        AlarmRequest(
            enabled=True,
            hour=7,
            minute=30,
            weekdays=(0, 4),
            wake_action="memory_1",
            massage=True,
            sound="music_1",
            reference_time=datetime(2026, 11, 27),
        )
    )
    assert frames(controller)[-1] == "FFFFFFFF010002130107300022010201118104"
    controller._parse_notification(bytes.fromhex("FFFFFFFF010004130F0730002201040101"))
    assert controller._coordinator.controller_state[ALARM_MODE] == "unknown_04"
    assert controller.alarm_capability.wake_actions == ("none", "zero_g", "memory_1")
    assert controller.alarm_capability.sounds == ("none", "alarm")
    controller._coordinator.ble_device_name = "QMS2"
    assert not controller.alarm_capability.massage
    with pytest.raises(ValueError, match="QMS2"):
        await controller.configure_alarm(
            AlarmRequest(
                enabled=True, hour=7, minute=30, massage=True, reference_time=datetime(2026, 11, 27)
            )
        )
    # An audio-panel UI gate is not a leg-relaxation write requirement.
    controller._parse_notification(bytes.fromhex("FFFFFFFF0100030B00"))
    await controller.preset_relaxing_bedtime()
    assert frames(controller)[-1] == "FFFFFFFF050000006A572F"


@pytest.mark.parametrize("mode,trailer", [(4, "7304"), (5, "7404"), (6, "7504")])
async def test_retained_alarm_mode_can_only_be_reapplied_from_fresh_report(
    controller, mode, trailer
):
    with pytest.raises(ValueError, match="not reported"):
        await controller.reapply_alarm()
    controller._parse_notification(bytes.fromhex(f"FFFFFFFF010004130F0730002201{mode:02X}0101"))
    await controller.reapply_alarm()
    assert frames(controller)[-1] == f"FFFFFFFF01000213010730002201{mode:02X}0101{trailer}"
    assert controller.alarm_capability.wake_actions == ("none", "zero_g", "memory_1")
    controller.on_disconnect()
    with pytest.raises(ValueError, match="not reported"):
        await controller.reapply_alarm()


@pytest.mark.parametrize("wire", ["FFFFFFFF050001", "FFFFFFFF01000413", "FFFFFFFF0304"])
async def test_incomplete_or_misaligned_offset_records_are_ignored(controller, wire):
    data = bytes.fromhex(wire)
    for size in range(len(data) + 1):
        controller._parse_notification(data[:size])
    controller._parse_notification(b"\x00" + data + b"\x00" * 17)
    assert not controller._coordinator.controller_state


@pytest.mark.parametrize("part", list(app.PARTS))
@pytest.mark.parametrize("fault", list(app.FAULTS))
async def test_fault_table_readback(controller, part, fault):
    controller._parse_notification(bytes.fromhex(f"FFFFFFFF0304{part}{fault}"))
    assert (
        controller._coordinator.controller_state[FAULT] == f"{app.PARTS[part]}: {app.FAULTS[fault]}"
    )
    assert controller.protocol_diagnostics["fault_part"] == part
    assert controller.protocol_diagnostics["fault_code"] == fault


@pytest.mark.parametrize(
    "name,accepted,diagnostics",
    [
        ("Sealy", True, True),
        ("xQMS4x", True, True),
        ("xS4-6x", True, True),
        ("qms", False, True),
        ("QMS-I06", True, False),
        ("QMS-L94", True, False),
        ("QMS-IQ", True, False),
        ("Sealy<:;=>?", True, True),
    ],
)
def test_profile_name_gates(name, accepted, diagnostics):
    assert app.accepts_name(name) is accepted
    assert app.diagnostics_allowed(name) is diagnostics
    assert app.normalize_name("<:;=>?") == "CABDEF"


def test_own_startup_offsets():
    assert [offset for offset, _ in app.startup_schedule()] == [
        1000,
        1000,
        1500,
        2300,
        2800,
        3300,
        3800,
        4300,
    ]
    assert app.startup_schedule()[-1][1].hex().upper() == "FFFFFFFF03003800039ECC"


@pytest.fixture
async def connected_flexirest(
    hass,
    mock_coordinator_connected,
    mock_async_ble_device_from_address,
    mock_bleak_client,
    enable_custom_integrations,
):
    from homeassistant.helpers import entity_registry as er
    from pytest_homeassistant.common import MockConfigEntry

    from custom_components.adjustable_bed.const import DOMAIN

    char = MagicMock()
    char.uuid, char.handle, char.properties = codec.CHARACTERISTIC_UUID, 15, ["write", "notify"]
    service = SimpleNamespace(uuid="12340000-0000-1000-8000-00805f9b34fb", characteristics=[char])
    mock_bleak_client.services.__iter__ = lambda _: iter([service])
    mock_bleak_client.services.__len__ = lambda _: 1
    mock_bleak_client.services.get_characteristic.return_value = char
    mock_bleak_client.write_gatt_char.side_effect = None
    mock_async_ble_device_from_address.return_value.name = "Sealy K1"
    entry = MockConfigEntry(
        domain=DOMAIN,
        version=5,
        minor_version=3,
        data={
            "address": "AA:BB:CC:DD:EE:FF",
            "name": "FlexiRest",
            "bed_type": "solace",
            "protocol_variant": "flexirest",
            "ble_device_name": "Sealy K1",
            "motor_count": 2,
            "has_massage": True,
            "disable_angle_sensing": True,
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    coordinator = hass.data[DOMAIN][entry.entry_id]
    await coordinator.async_ensure_connected()
    ctrl = coordinator.controller
    assert isinstance(ctrl, FlexirestController)
    ctrl._cancel_startup()
    await hass.async_block_till_done()
    mock_bleak_client.write_gatt_char.reset_mock()

    def entity(domain, key):
        found = er.async_get(hass).async_get_entity_id(domain, DOMAIN, f"AA:BB:CC:DD:EE:FF_{key}")
        assert found is not None, (domain, key)
        return found

    yield entry, coordinator, entity
    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


async def test_native_setup_entities_and_actions(hass, connected_flexirest):
    from homeassistant.helpers import entity_registry as er

    from custom_components.adjustable_bed.const import DOMAIN

    _, coordinator, entity = connected_flexirest
    ctrl = coordinator.controller
    registry = er.async_get(hass)
    assert registry.async_get_entity_id("number", DOMAIN, "AA:BB:CC:DD:EE:FF_back_position") is None
    assert not ctrl.supports_solace_audio
    assert ctrl.position_number_specs == ()
    ctrl._parse_notification(bytes.fromhex("FFFFFFFF05000103"))
    await hass.services.async_call(
        "number",
        "set_value",
        {"entity_id": entity("number", "light_level"), "value": 4},
        blocking=True,
    )
    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": entity("select", "light_timer"), "option": "8 hours"},
        blocking=True,
    )
    assert frames(ctrl)[-2:] == ["FFFFFFFF05000004239419", "FFFFFFFF050000001A56CB"]
    assert (
        hass.states.get(entity("button", "flexirest_program_tv")).attributes["card_role"] == "save"
    )
    ctrl._parse_notification(bytes.fromhex("FFFFFFFF010004130F0730002201020101"))
    device_id = registry.async_get(entity("binary_sensor", "flexirest_alarm_enabled")).device_id
    await hass.services.async_call(
        DOMAIN,
        "set_alarm",
        {
            "device_id": device_id,
            "enabled": True,
            "time": "07:30:00",
            "weekdays": ["monday", "friday"],
            "wake_action": "memory_1",
            "massage": True,
            "sound": "alarm",
        },
        blocking=True,
    )
    assert frames(ctrl)[-1] == "FFFFFFFF010002130107300022010201017104"
    await hass.services.async_call(
        DOMAIN,
        "timed_move",
        {
            "device_id": device_id,
            "motor": "back",
            "direction": "up",
            "duration_ms": 100,
        },
        blocking=True,
    )
    assert frames(ctrl)[-2:] == ["FFFFFFFF05000000039701", "FFFFFFFF0500000000D700"]
    await coordinator.async_execute_controller_command(lambda c: c.query_fault())
    assert frames(ctrl)[-1] == "FFFFFFFF03005A0002FED2"


async def test_explicit_app_setup_and_per_side_ownership():
    from custom_components.adjustable_bed.app_profiles import per_side_profile
    from custom_components.adjustable_bed.detection import APP_VARIANT_CHOICES
    from custom_components.adjustable_bed.setup_questions import setup_profile

    assert APP_VARIANT_CHOICES["solace", "flexirest"] == "Sealy FlexiRest app"
    profile = setup_profile("solace", "flexirest")
    assert profile is not None
    assert profile.owns["motor_count"] == 2 and profile.owns["has_massage"] is True
    assert "ble_device_name" in per_side_profile("solace", "flexirest").keys
