"""Real delivery, profile fences, diagnostics and cancellation for V-MAT Basic."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.adjustable_bed.beds import vmatbasic_protocol as protocol
from custom_components.adjustable_bed.beds.vmatbasic import VMatBasicController


def make_controller(profile="basic", **kwargs):
    coordinator = MagicMock()
    coordinator.address = "AA:BB:CC:DD:EE:FF"
    coordinator.cancel_command = asyncio.Event()
    coordinator.controller_state = {}
    coordinator.handle_controller_state_updates.side_effect = coordinator.controller_state.update
    coordinator.handle_controller_state_update.side_effect = lambda key, value: (
        coordinator.controller_state.update({key: value})
    )
    roles = {
        protocol.CONTROL_SERVICE: [
            (protocol.MOTOR_CHAR, ["write"]),
            (protocol.FLOOR_CHAR, ["read", "write"]),
            (protocol.XT_CHAR, ["write"]),
        ],
        protocol.STATUS_SERVICE: [
            (protocol.TEMPERATURE_CHAR, ["read"]),
            (protocol.ED_CHAR, ["read"]),
        ],
        protocol.GAP_SERVICE: [(protocol.NAME_CHAR, ["read", "write"])],
        protocol.INFO_SERVICE: [
            (protocol.MODEL_CHAR, ["read"]),
            (protocol.FIRMWARE_CHAR, ["read"]),
        ],
    }
    services = [
        MagicMock(
            uuid=service,
            characteristics=[
                MagicMock(uuid=uuid, handle=index + 1, properties=properties)
                for index, (uuid, properties) in enumerate(chars)
            ],
        )
        for service, chars in roles.items()
    ]
    coordinator.client = MagicMock(is_connected=True, services=services)
    coordinator.client.write_gatt_char = AsyncMock()
    values = {
        protocol.MODEL_CHAR: b" model \0",
        protocol.FIRMWARE_CHAR: b"FW",
        protocol.FLOOR_CHAR: bytes.fromhex("ff059f"),
        protocol.ED_CHAR: b"\x03",
        protocol.TEMPERATURE_CHAR: bytes.fromhex("80000000"),
    }
    coordinator.client.read_gatt_char = AsyncMock(side_effect=lambda char: values[char.uuid])
    coordinator.client.start_notify = AsyncMock()
    coordinator.client.stop_notify = AsyncMock()
    return VMatBasicController(coordinator, profile=profile, **kwargs)


def written(controller):
    return [
        (call.args[0].uuid, bytes(call.args[1]), call.kwargs["response"])
        for call in controller.client.write_gatt_char.call_args_list
    ]


@pytest.mark.parametrize("profile", protocol.PROFILES)
async def test_exact_service_gate_and_no_notify_position_or_auth(profile):
    controller = make_controller(profile)
    await controller.async_discover_capabilities()
    await controller.start_notify()
    await controller.read_positions()
    await controller.stop_notify()
    assert controller.client.start_notify.await_count == 0
    assert controller.client.stop_notify.await_count == 0
    assert controller.client.write_gatt_char.await_count == 0
    assert controller.client.read_gatt_char.await_count == 0
    assert [spec.key for spec in controller.motor_control_specs] == ["back", "legs"]
    assert not controller.supports_position_feedback
    assert not controller.supports_preset_flat
    assert not controller.supports_memory_presets
    assert not controller.supports_memory_programming
    assert not controller.supports_massage
    assert not controller.supports_light_color_control
    assert not controller.requires_notification_channel
    assert controller.supports_device_rename


@pytest.mark.parametrize("profile", protocol.PROFILES)
@pytest.mark.parametrize("missing", protocol.REQUIRED_SERVICES)
async def test_each_required_service_absence_fails_before_any_write(profile, missing):
    controller = make_controller(profile)
    controller.client.services = [
        service for service in controller.client.services if service.uuid != missing
    ]
    with pytest.raises(ValueError):
        await controller.async_discover_capabilities()
    assert written(controller) == []


@pytest.mark.parametrize("properties", [[], ["read"], ["write-without-response"]])
async def test_no_response_downgrade_or_reset_characteristic_fallback(properties):
    controller = make_controller()
    service = controller.client.services[0]
    service.characteristics[0].properties = properties
    service.characteristics.append(
        MagicMock(uuid="00001528" + protocol.VENDOR_SUFFIX, properties=["write"])
    )
    with pytest.raises(ValueError):
        await controller.async_discover_capabilities()
    assert written(controller) == []


async def test_first_exact_service_and_characteristic_handle_are_authoritative():
    controller = make_controller()
    original = controller.client.services[0].characteristics[0]
    duplicate = MagicMock(uuid=protocol.MOTOR_CHAR, properties=["write"])
    controller.client.services[0].characteristics.append(duplicate)
    controller.client.services.append(
        MagicMock(uuid=protocol.CONTROL_SERVICE, characteristics=[duplicate])
    )
    await controller.write_command(b"\x0b", 1)
    assert controller.client.write_gatt_char.call_args_list[0].args[0] is original
    assert controller.client.write_gatt_char.call_args_list[1].args[0] is original
    original.properties = []
    with pytest.raises(ValueError):
        await controller.async_discover_capabilities()


@pytest.mark.parametrize("profile", protocol.PROFILES)
@pytest.mark.parametrize(
    "action,packet",
    [
        ("all_up", 0x10),
        ("all_down", 0x00),
        ("back_up", 0x0B),
        ("back_down", 0x0A),
        ("legs_up", 0x09),
        ("legs_down", 0x08),
    ],
)
async def test_every_native_held_movement_has_response_and_fresh_ff_release(
    profile, action, packet
):
    controller = make_controller(profile)
    await controller.hold_control(action, 100)
    calls = written(controller)
    assert 3 <= len(calls) - 1 <= 4
    assert all(call == (protocol.MOTOR_CHAR, bytes((packet,)), True) for call in calls[:-1])
    assert calls[-1] == (protocol.MOTOR_CHAR, b"\xff", True)


async def test_cancel_during_write_stops_pump_and_release_ignores_set_event():
    controller = make_controller()
    entered = asyncio.Event()

    async def write(char, packet, **kwargs):
        if packet != b"\xff":
            entered.set()
            await asyncio.sleep(10)

    controller.client.write_gatt_char.side_effect = write
    task = asyncio.create_task(controller.hold_control("back_up", 1000))
    await entered.wait()
    controller._coordinator.cancel_command.set()
    await task
    assert [packet for _, packet, _ in written(controller)] == [b"\x0b", b"\xff"]
    assert not controller.ble_lock.locked()


async def test_release_survives_repeated_task_cancellation():
    controller = make_controller()
    entered = asyncio.Event()
    finish = asyncio.Event()

    async def write(char, packet, **kwargs):
        if packet == b"\xff":
            entered.set()
            await finish.wait()

    controller.client.write_gatt_char.side_effect = write
    task = asyncio.create_task(controller.hold_control("back_up", 100))
    await entered.wait()
    task.cancel()
    await asyncio.sleep(0)
    task.cancel()
    finish.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert written(controller)[-1][1] == b"\xff"
    assert not controller.ble_lock.locked()


@pytest.mark.parametrize("action", [*protocol.MOTOR_ACTIONS, "floor_hold"])
async def test_pre_cancelled_hold_has_no_stale_or_accessory_write(action):
    controller = make_controller("xtbox")
    controller._coordinator.cancel_command.set()
    await controller.hold_control(action, 100)
    assert written(controller) == []


async def test_xt_floor_hold_has_no_invented_release_packet():
    controller = make_controller("xtbox")
    await controller.hold_control("floor_hold", 100)
    assert written(controller)
    assert all(call == (protocol.XT_CHAR, b"\x00\x11", True) for call in written(controller))


async def test_lane_cancel_does_not_leak_lock_or_send_stale_write():
    controller = make_controller()
    await controller.ble_lock.acquire()
    task = asyncio.create_task(controller.hold_control("back_up", 1000))
    await asyncio.sleep(0)
    controller._coordinator.cancel_command.set()
    controller.ble_lock.release()
    await task
    assert written(controller) == [(protocol.MOTOR_CHAR, b"\xff", True)]
    assert not controller.ble_lock.locked()


async def test_read_order_and_all_observed_values_without_selector_inference():
    controller = make_controller()
    await controller.async_refresh_diagnostics()
    assert [call.args[0].uuid for call in controller.client.read_gatt_char.call_args_list] == [
        uuid for _, _, uuid in protocol.READ_ROLES
    ]
    assert controller._coordinator.controller_state == {
        "vmatbasic_model": " model \0",
        "vmatbasic_temperature": 25.0,
        "vmatbasic_floor_level_observed": 255,
        "vmatbasic_floor_minutes_observed": 1439,
        "vmatbasic_floor_percent_observed": 100.0,
        "vmatbasic_firmware": "FW",
        "vmatbasic_ed": True,
    }
    assert controller.profile == "basic"
    controller.invalidate_diagnostics()
    assert all(value is None for value in controller._coordinator.controller_state.values())


async def test_optional_dis_absence_clears_only_strings_and_retains_other_reads():
    controller = make_controller()
    controller.client.services = [
        service for service in controller.client.services if service.uuid != protocol.INFO_SERVICE
    ]
    await controller.async_discover_capabilities()
    await controller.async_refresh_diagnostics()
    assert controller._coordinator.controller_state["vmatbasic_model"] is None
    assert controller._coordinator.controller_state["vmatbasic_firmware"] is None
    assert controller._coordinator.controller_state["vmatbasic_temperature"] == 25.0
    assert controller._coordinator.controller_state["vmatbasic_ed"] is True


@pytest.mark.parametrize("bad", [b"", b"\xff", b"\xff\x01"])
async def test_cbi_toggle_short_read_never_writes(bad):
    controller = make_controller("cbi")
    controller.client.read_gatt_char.return_value = bad
    controller.client.read_gatt_char.side_effect = None
    with pytest.raises(ValueError):
        await controller.floor_toggle()
    assert written(controller) == []


@pytest.mark.parametrize(
    "level,saved,minutes,expected",
    [
        (255, None, 0, "000000"),
        (0, None, 0, "ff0000"),
        (0, 0, 0, "000000"),
        (0, 42, 1439, "2a059f"),
    ],
)
async def test_cbi_toggle_uses_fresh_q3_and_distinguishes_absent_and_zero(
    level, saved, minutes, expected
):
    controller = make_controller("cbi", floor_level=saved, floor_minutes=minutes)
    controller.client.read_gatt_char.side_effect = None
    controller.client.read_gatt_char.return_value = bytes((level, 0, 0))
    await controller.floor_toggle()
    assert controller.client.read_gatt_char.call_args.args[0].uuid == protocol.FLOOR_CHAR
    assert written(controller) == [(protocol.FLOOR_CHAR, bytes.fromhex(expected), True)]


@pytest.mark.parametrize(
    "profile,level,minutes,packet",
    [
        ("cbi", 255, 1439, "ff059f"),
        ("cbi", 0, 0, "000000"),
        ("xtbox", 1, 0, "00110100"),
        ("xtbox", 6, 255, "001106ff"),
    ],
)
async def test_floor_numbers_write_exact_parameters_and_persist_requested_intent(
    profile, level, minutes, packet
):
    remember = MagicMock()
    controller = make_controller(profile, floor_minutes=minutes, remember_settings=remember)
    await controller.set_floor_level(level)
    assert written(controller)[-1][1] == bytes.fromhex(packet)
    remember.assert_called_once_with({"floor_level": level, "floor_minutes": minutes})
    assert controller._coordinator.controller_state["vmatbasic_floor_level_requested"] == level
    assert "vmatbasic_floor_level_observed" not in controller._coordinator.controller_state


async def test_cbi_settings_absent_level_zero_differs_from_toggle_button_default():
    controller = make_controller("cbi")
    await controller.set_floor_minutes(12)
    assert written(controller)[-1][1] == bytes.fromhex("00000c")
    controller.client.read_gatt_char.side_effect = None
    controller.client.read_gatt_char.return_value = bytes(3)
    await controller.floor_toggle()
    assert written(controller)[-1][1] == bytes.fromhex("ff000c")


@pytest.mark.parametrize("option", protocol.PALETTE_OPTIONS)
async def test_all_twenty_palette_controls_use_exact_hsv_packet(option):
    controller = make_controller("xtbox")
    await controller.set_mood_palette(option)
    expected = protocol.color_action(protocol.PALETTE[protocol.PALETTE_OPTIONS.index(option)], 100)
    assert written(controller) == [(protocol.XT_CHAR, expected, True)]
    assert controller._coordinator.controller_state["vmatbasic_mood_palette"] == option


@pytest.mark.parametrize(
    "option,packet", [("E1", "00770801"), ("E2", "00770802"), ("E3", "00770803")]
)
async def test_three_effect_controls(option, packet):
    controller = make_controller("xtbox")
    await controller.set_mood_effect(option)
    assert written(controller)[-1][1] == bytes.fromhex(packet)


@pytest.mark.parametrize("value,packet", [(0, "00770901"), (255, "00770900")])
async def test_speed_encoded_zero_is_preserved(value, packet):
    controller = make_controller("xtbox")
    await controller.set_mood_speed(value)
    assert written(controller)[-1][1] == bytes.fromhex(packet)


async def test_mood_brightness_defaults_white_and_nightlight_has_only_known_rgb_zero():
    controller = make_controller("xtbox")
    await controller.set_mood_brightness(50)
    await controller.mood_toggle()
    await controller.mood_nightlight()
    assert [packet.hex() for _, packet, _ in written(controller)] == [
        "007701007f7f7f",
        "0077",
        "00770100000000",
    ]
    assert "vmatbasic_mood_power" not in controller._coordinator.controller_state


@pytest.mark.parametrize(
    "action,opcode",
    [
        ("back", 0x2C),
        ("legs", 0x2D),
        ("off", 0x34),
        ("program_1", 0x31),
        ("program_2", 0x28),
        ("program_3", 0x29),
    ],
)
async def test_six_massage_controls_without_motion_stop_or_guessed_state(action, opcode):
    controller = make_controller("xtbox")
    await controller.massage_action(action)
    assert written(controller) == [(protocol.XT_CHAR, bytes((0, opcode)), True)]
    assert controller._coordinator.controller_state == {}


@pytest.mark.parametrize("profile", ["basic", "cbi"])
async def test_non_xt_profiles_refuse_all_xt_public_routes_before_write(profile):
    controller = make_controller(profile)
    for operation in [
        controller.set_mood_palette("col1"),
        controller.set_mood_effect("E1"),
        controller.set_mood_speed(1),
        controller.set_mood_brightness(1),
        controller.mood_toggle(),
        controller.mood_nightlight(),
        controller.massage_action("back"),
    ]:
        with pytest.raises(ValueError):
            await operation
    assert written(controller) == []


async def test_rename_primary_gap_role_and_failed_write_does_not_publish_name():
    controller = make_controller()
    await controller.rename_device(" Béd ")
    assert written(controller) == [(protocol.NAME_CHAR, "Béd".encode(), True)]
    assert controller._coordinator.controller_state["vmatbasic_device_name"] == "Béd"
    controller.client.write_gatt_char.side_effect = RuntimeError("write failed")
    with pytest.raises(RuntimeError):
        await controller.rename_device("New")
    assert controller._coordinator.controller_state["vmatbasic_device_name"] == "Béd"


@pytest.mark.parametrize("name", ["a" * 11, "\u0800" * 10])
async def test_rename_ui_and_unfragmented_transport_limits_fail_before_write(name):
    controller = make_controller()
    with pytest.raises(ValueError):
        await controller.rename_device(name)
    assert written(controller) == []


@pytest.mark.parametrize(
    "profile,buttons,numbers,selects", [("basic", 3, 0, 0), ("cbi", 4, 2, 0), ("xtbox", 12, 4, 2)]
)
def test_immutable_profile_control_catalog(profile, buttons, numbers, selects):
    controller = make_controller(profile)
    assert len(controller.controller_button_specs) == buttons
    assert len(controller.controller_number_specs) == numbers
    assert len(controller.controller_select_specs) == selects
    assert len(controller.controller_state_sensor_specs) == 7
    assert len(controller.controller_state_binary_sensor_specs) == 1
    assert all(
        spec.translation_key.startswith("vmatbasic_") for spec in controller.controller_button_specs
    )


@pytest.mark.parametrize("method", ["hold", "write"])
async def test_attempted_motion_error_survives_failed_release(method):
    controller = make_controller()
    first = RuntimeError("first write")
    controller.client.write_gatt_char.side_effect = [first, ValueError("release failure")]
    with pytest.raises(RuntimeError, match="first write"):
        if method == "hold":
            await controller.hold_control("back_up", 100)
        else:
            await controller.write_command(b"\x0b", 2)
    assert [packet for _, packet, _ in written(controller)] == [b"\x0b", b"\xff"]


async def test_precancelled_raw_movement_does_not_admit_or_send_release():
    controller = make_controller()
    controller._coordinator.cancel_command.set()
    await controller.write_command(b"\x0b", 2)
    assert written(controller) == []


@pytest.mark.parametrize(
    "profile,action",
    [
        ("cbi", "level"),
        ("cbi", "timer"),
        ("xtbox", "level"),
        ("xtbox", "timer"),
        ("xtbox", "palette"),
        ("xtbox", "brightness"),
    ],
)
async def test_precancelled_setting_does_not_advance_preferences_or_mood_session(profile, action):
    from unittest.mock import Mock

    remember = Mock()
    controller = make_controller(profile, remember_settings=remember)
    controller._coordinator.cancel_command.set()
    if action == "level":
        await controller.set_floor_level(1)
    elif action == "timer":
        await controller.set_floor_minutes(5)
    elif action == "palette":
        await controller.set_mood_palette("col1")
    else:
        await controller.set_mood_brightness(50)
    assert written(controller) == []
    assert not remember.called
    assert controller._floor_level is None and controller._floor_minutes == 0
    assert (controller._intent.palette, controller._intent.brightness) == ("col20", 100)


async def test_real_read_timeout_clears_only_failed_field_and_continues_ordered_reads():
    controller = make_controller()
    original = controller.client.read_gatt_char.side_effect

    async def read(char):
        if char.uuid == protocol.MODEL_CHAR:
            await asyncio.sleep(10)
        return original(char)

    controller.client.read_gatt_char.side_effect = read
    started = asyncio.get_running_loop().time()
    await controller.async_refresh_diagnostics()
    elapsed = asyncio.get_running_loop().time() - started
    assert 0.75 <= elapsed < 1.5
    assert controller._coordinator.controller_state["vmatbasic_model"] is None
    assert controller._coordinator.controller_state["vmatbasic_ed"] is True
    assert [call.args[0].uuid for call in controller.client.read_gatt_char.call_args_list] == [
        uuid for _, _, uuid in protocol.READ_ROLES
    ]
    assert not controller.ble_lock.locked()


async def test_actual_write_timeout_is_failure_not_elapsed_hold_and_still_releases():
    controller = make_controller()

    async def write(char, packet, *, response):
        if packet != b"\xff":
            await asyncio.sleep(10)

    controller.client.write_gatt_char.side_effect = write
    with pytest.raises(TimeoutError):
        await controller.hold_control("back_up", 2000)
    assert [packet for _, packet, _ in written(controller)] == [b"\x0b", b"\xff"]
    assert not controller.ble_lock.locked()
