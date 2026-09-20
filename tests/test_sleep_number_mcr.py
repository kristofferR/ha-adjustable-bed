"""Tests for the older Sleep Number BAM / MCR controller."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed.beds.sleep_number_mcr import SleepNumberMcrController
from custom_components.adjustable_bed.beds.sleep_number_mcr_protocol import decode_foundation
from custom_components.adjustable_bed.const import (
    BED_TYPE_SLEEP_NUMBER_MCR,
    CONF_BED_TYPE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_HAS_MASSAGE,
    CONF_MOTOR_COUNT,
    CONF_PREFERRED_ADAPTER,
    DOMAIN,
)
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator


def _mcr_address_from_mac(address: str) -> int:
    """Return the BAM/MCR address derived from the BLE MAC address."""
    parts = address.split(":")
    return (int(parts[-2], 16) << 8) | int(parts[-1], 16)


@pytest.fixture
def sleep_number_mcr_coordinator(hass: HomeAssistant, mock_coordinator_connected):
    """Create and connect a coordinator for a Sleep Number BAM/MCR test device."""

    async def _create(
        *,
        address: str,
        name: str,
        entry_id: str,
    ) -> AdjustableBedCoordinator:
        entry = MockConfigEntry(
            domain=DOMAIN,
            title="Sleep Number MCR Test Bed",
            data={
                CONF_ADDRESS: address,
                CONF_NAME: name,
                CONF_BED_TYPE: BED_TYPE_SLEEP_NUMBER_MCR,
                CONF_MOTOR_COUNT: 2,
                CONF_HAS_MASSAGE: False,
                CONF_DISABLE_ANGLE_SENSING: True,
                CONF_PREFERRED_ADAPTER: "auto",
            },
            unique_id=address,
            entry_id=entry_id,
        )
        entry.add_to_hass(hass)
        coordinator = AdjustableBedCoordinator(hass, entry)
        await coordinator.async_connect()
        return coordinator

    return _create


@pytest.fixture
def controller():
    """A protocol unit fixture with explicit feature discovery state."""
    from custom_components.adjustable_bed.beds.sleep_number_mcr_protocol import FoundationFeatures

    coordinator = MagicMock()
    coordinator.entry.data = {"sleep_number_mcr_client_id": 0x0102030405060708}
    coordinator.cancel_command = asyncio.Event()
    coordinator.motor_pulse_count = 1
    coordinator.motor_pulse_delay_ms = 1
    coordinator.client.mtu_size = 23
    coordinator.client.services.get_characteristic.return_value.properties = ["write"]
    result = SleepNumberMcrController(coordinator)
    result._initialized = True
    result._foundation_features = FoundationFeatures(2, True, True, True, True, "360", "FF3")
    result._nodes = {1, 0x31, 0x41, 0x51}
    result._chambers = {"right": 0, "left": 2}
    result._pump_model = "360"
    result._pressure_sides = ("right", "left")
    result._massage_sides = ("right", "left")
    return result


async def test_connect_negotiates_addresses(sleep_number_mcr_coordinator):
    coordinator = await sleep_number_mcr_coordinator(
        address="AA:BB:CC:DD:EE:51", name="MCR", entry_id="mcr_session"
    )
    controller = coordinator.controller
    assert isinstance(controller, SleepNumberMcrController)
    assert controller._bed_address == 0x5678
    assert controller._client_address == 0x1234
    assert controller.supports_motor_control
    assert controller.foundation_preset_sides == ("right", "left")
    assert coordinator.controller_state["sleep_number_right"] == 65
    assert coordinator.controller_state["sleep_number_left"] == 35
    assert controller.supports_lights and controller.supports_massage


def test_frozen_wire_vector():
    frame = SleepNumberMcrController._build_frame(
        command_type=2,
        status=2,
        function_code=18,
        side=0,
        payload=b"",
        sub_address=0x5678,
        client_address=0x1234,
    )
    assert frame.hex() == "1616021234567802123412000892"


@pytest.mark.parametrize(
    ("command", "parameters", "node", "opcode", "sub", "payload"),
    [
        ("preset_save", {"side": "left", "preset": "Read"}, 0x42, 0x16, 1, "02"),
        (
            "preset_timer",
            {"side": "right", "preset": "Flat", "timer": 300},
            0x42,
            0x11,
            0,
            "ffffffffffffff2c0104ffff",
        ),
        ("firmness_favorite", {"side": "right", "firmness": 65}, 2, 0x13, 0, "41"),
        (
            "massage",
            {"side": "left", "head": 2, "timer": 300},
            0x42,
            0x11,
            1,
            "ffffffff02ff00ffffff2c01",
        ),
        ("foot_warming", {"side": "right", "level": 3, "duration": 300}, 0x42, 0x29, 0, "482c01"),
        ("outlet", {"outlet": 3, "enabled": True, "duration": 300}, 0x42, 0x13, 3, "012c01"),
        ("light_intensity", {"side": "left", "intensity": 75}, 0x42, 0x24, 0, "ffff4b"),
        ("sense_and_do", {"enabled": True}, 0x32, 0x14, 0, "0100"),
        ("kid_outlet", {"device": 0, "light_on": True}, 0x92, 0x13, 0, "ff0100"),
    ],
)
async def test_frozen_command_payloads(controller, command, parameters, node, opcode, sub, payload):
    controller._mcr_request = AsyncMock(return_value=b"")
    assert await controller.async_execute_sleep_number_command(command, parameters) == {}
    call = controller._mcr_request.await_args
    assert call.args[:2] == (node, opcode)
    actual_sub = call.args[2] if len(call.args) > 2 else 0
    actual_payload = call.args[3] if len(call.args) > 3 else call.kwargs.get("payload", b"")
    assert actual_sub == sub
    assert actual_payload.hex() == payload


@pytest.mark.parametrize(
    ("command", "parameters", "key", "payload"),
    [
        ("position", {"side": "left", "axis": "foot", "position": 30}, "MFFL", b"30_0"),
        ("stop", {"side": "right"}, "MFHR", b"110"),
        ("preset_reset", {"side": "left", "preset": "Zero G"}, "MFRL", b"5"),
        ("responsive_air", {"side": "left", "enabled": True}, "LRLE", b"\x00\x00\x00\x01"),
        ("underbed_auto", {"enabled": False}, "MUAS", b"\x00"),
    ],
)
async def test_se_command_payloads(controller, command, parameters, key, payload):
    controller._se_write = AsyncMock()
    controller._prepare_foundation_motion = AsyncMock(return_value={})
    controller._wait_for_foundation = AsyncMock()
    controller._check_pinch = AsyncMock()
    controller._read_foundation = AsyncMock(return_value=decode_foundation(foundation_reply()))
    await controller.async_execute_sleep_number_command(command, parameters)
    assert controller._se_write.await_args_list[0].args == (key, payload)
    if command == "stop":
        assert not controller._se_write.await_args.kwargs["cancel_event"].is_set()


@pytest.mark.parametrize(
    ("command", "parameters"),
    [
        ("raw", {}),
        ("position", {"side": "left", "axis": "foot", "position": 101}),
        ("position", {"side": "left", "axis": "foot", "position": True}),
        ("massage", {"side": "left"}),
        ("massage", {"side": "left", "head": 4}),
        ("underbed_auto", {"enabled": 1}),
        ("foot_warming", {"side": "right", "level": -1}),
        ("kid_outlet", {"device": 16, "light_on": True}),
        ("stop", {"side": "right", "raw": "oops"}),
    ],
)
async def test_invalid_commands_write_nothing(controller, command, parameters):
    controller._mcr_request = AsyncMock()
    controller._se_write = AsyncMock()
    with pytest.raises(ValueError):
        await controller.async_execute_sleep_number_command(command, parameters)
    controller._mcr_request.assert_not_called()
    controller._se_write.assert_not_called()


async def test_bound_side_cannot_be_overridden(controller):
    with pytest.raises(ValueError, match="override"):
        await controller.bind_side("left").async_execute_sleep_number_command(
            "position", {"side": "right", "axis": "head", "position": 20}
        )


async def test_movement_cancel_always_releases(controller):
    controller._prepare_foundation_motion = AsyncMock(return_value={})
    controller._read_foundation = AsyncMock(return_value=decode_foundation(foundation_reply()))
    controller._mcr_request = AsyncMock(side_effect=asyncio.CancelledError)
    controller._stop_side = AsyncMock()
    with pytest.raises(asyncio.CancelledError):
        await controller.bind_side("left").move_back_up()
    controller._stop_side.assert_awaited_once_with("left")


async def test_stop_ignores_prior_cancel(controller):
    controller._coordinator.cancel_command.set()
    controller._mcr_request = AsyncMock(return_value=b"")
    await controller._stop_side("left")
    assert controller._mcr_request.await_args.args == (0x52, 0x1B)
    assert controller._mcr_request.await_args.kwargs["payload"] == b"MFHL110"
    assert not controller._mcr_request.await_args.kwargs["cancel_event"].is_set()


def foundation_reply(*, status=64, positions=(0, 0, 0, 0), flags=(0, 0, 0, 0), presets=0x44):
    """Literal layout from the frozen 15-byte foundation parser fixture."""
    return bytes((status, *positions, 0, 0, 0, 0, *flags, 0, presets))


@pytest.fixture
def motion(controller):
    responses = SimpleNamespace(foundation=[foundation_reply()], pinch=[bytes(5)])

    async def request(node, opcode, sub=0, payload=b"", **kwargs):
        if (node, opcode) == (0x42, 0x12):
            return (
                responses.foundation.pop(0)
                if len(responses.foundation) > 1
                else responses.foundation[0]
            )
        if (node, opcode) == (0x42, 0x28):
            return responses.pinch.pop(0) if len(responses.pinch) > 1 else responses.pinch[0]
        return b""

    controller._mcr_request = AsyncMock(side_effect=request)
    controller._foundation_delay = AsyncMock()
    controller._notify_callback = MagicMock()
    controller._coordinator.motor_pulse_count = 10
    controller._coordinator.motor_pulse_delay_ms = 100
    return responses


@pytest.mark.parametrize(
    ("side", "axis", "index", "selector"),
    [
        ("right", "head", 0, 2),
        ("left", "head", 1, 3),
        ("right", "foot", 2, 2),
        ("left", "foot", 3, 3),
    ],
)
async def test_held_motion_keeps_selected_side_moving(
    controller, motion, side, axis, index, selector
):
    flags, positions = [0] * 4, [0] * 4
    flags[index], positions[index] = 1, 20
    motion.foundation = [
        foundation_reply(),
        foundation_reply(flags=flags, positions=positions),
        foundation_reply(positions=positions),
    ]
    controller._coordinator.disable_angle_sensing = True
    await controller.bind_side(side)._move_axis(axis, 100)
    calls = controller._mcr_request.await_args_list
    status_calls = [call for call in calls if call.args[:2] == (0x42, 0x12)]
    assert [call.args[2] for call in status_calls] == [0, selector, selector, 0]
    assert all(len(call.args) == 3 for call in status_calls)
    target_call = next(call for call in calls if call.args[:2] == (0x42, 0x11))
    expected = bytearray(b"\xff" * 12)
    offset = 0 if axis == "head" else 2
    expected[offset : offset + 2] = b"\x64\x00"
    assert target_call.args == (0x42, 0x11, selector - 2, bytes(expected))
    stop = next(call for call in calls if call.args[:2] == (0x52, 0x1B))
    assert stop.kwargs["payload"] == (b"MFHR110" if side == "right" else b"MFHL110")
    assert not stop.kwargs["cancel_event"].is_set()
    controller._notify_callback.assert_any_call(
        f"{side}_{'back' if axis == 'head' else 'legs'}", 20.0
    )


async def test_held_motion_refreshes_selected_sides_until_all_actuators_stop(controller, motion):
    motion.foundation = [
        foundation_reply(),
        foundation_reply(flags=(1, 1, 0, 0)),
        foundation_reply(flags=(1, 0, 0, 0)),
        foundation_reply(),
    ]
    await controller.move_back_up()
    calls = controller._mcr_request.await_args_list
    assert [call.args[2] for call in calls if call.args[:2] == (0x42, 0x12)] == [0, 2, 3, 2, 0]
    assert [call.kwargs["payload"] for call in calls if call.args[:2] == (0x52, 0x1B)] == [
        b"MFHR110",
        b"MFHL110",
    ]


@pytest.mark.parametrize(
    ("side", "axis", "index", "key"),
    [
        ("right", "head", 0, b"MFUR"),
        ("left", "head", 1, b"MFUL"),
        ("right", "foot", 2, b"MFFR"),
        ("left", "foot", 3, b"MFFL"),
    ],
)
async def test_absolute_target_waits_for_stable_feedback(
    controller, motion, side, axis, index, key
):
    moving, near, final, flags = [0] * 4, [0] * 4, [0] * 4, [0] * 4
    moving[index], near[index], final[index], flags[index] = 10, 49, 50, 1
    motion.foundation = [
        foundation_reply(),
        foundation_reply(positions=moving, flags=flags),
        foundation_reply(positions=near),
        foundation_reply(positions=final),
    ]
    await controller._set_position(side, axis, 50)
    calls = controller._mcr_request.await_args_list
    writes = [call.kwargs["payload"] for call in calls if call.args[:2] == (0x52, 0x1B)]
    assert writes == [key + b"50_0", b"MFHL110" if side == "left" else b"MFHR110"]
    assert all(call.args[2] == 0 for call in calls if call.args[:2] == (0x42, 0x12))
    assert [call.args[0] for call in controller._foundation_delay.await_args_list] == [
        1.0,
        0.333,
        0.5,
        0.5,
    ]
    assert controller._state[f"foundation_{axis}_{side}"] == 50


async def test_absolute_target_reports_early_stop(controller, motion):
    with pytest.raises(ValueError, match="stopped before reaching"):
        await controller._set_position("left", "head", 50)
    assert controller._mcr_request.await_args_list[-2].kwargs["payload"] == b"MFHL110"
    assert controller._state["foundation_head_left"] == 0


@pytest.mark.parametrize("status", [0, 0x62, 0x63])
@pytest.mark.parametrize("operation", ["hold", "target", "preset"])
async def test_motion_rejects_unconfigured_or_homing(controller, motion, status, operation):
    motion.foundation = [foundation_reply(status=status)]
    with pytest.raises(ValueError, match="configured|homing"):
        if operation == "hold":
            await controller.move_back_up()
        elif operation == "target":
            await controller._set_position("left", "head", 50)
        else:
            await controller.set_foundation_preset_for_side("left", "Read")
    assert all(call.args[:2] == (0x42, 0x12) for call in controller._mcr_request.await_args_list)


@pytest.mark.parametrize("fault", [2, 4, 8, 16, 32, 64])
async def test_motion_rejects_selected_side_actuator_fault(controller, motion, fault):
    motion.foundation = [foundation_reply(flags=(0, 0, 0, fault))]
    with pytest.raises(ValueError, match="left foot"):
        await controller._set_position("left", "head", 50)
    assert controller._mcr_request.await_count == 1


async def test_running_fault_releases_and_publishes_positions(controller, motion):
    motion.foundation = [
        foundation_reply(),
        foundation_reply(flags=(0, 16, 0, 0), positions=(0, 10, 0, 0)),
    ]
    with pytest.raises(ValueError, match="current is over"):
        await controller.bind_side("left").move_back_up()
    assert controller._mcr_request.await_args_list[-2].kwargs["payload"] == b"MFHL110"
    assert controller._state["foundation_head_left"] == 10


@pytest.mark.parametrize("pinch", [bytes((8, 0, 0, 0, 0)), bytes((128, 0, 0, 0, 0))])
async def test_motion_rejects_obstruction_sensor_fault(controller, motion, pinch):
    motion.pinch = [pinch]
    with pytest.raises(ValueError, match="obstruction sensor"):
        await controller._set_position("left", "head", 50)
    assert all(
        call.args[0] == 0x42 and call.args[1] in (0x12, 0x28)
        for call in controller._mcr_request.await_args_list
    )


async def test_motion_detects_new_obstruction_event(controller, motion):
    motion.pinch = [bytes(5), bytes((0, 0, 0, 0, 1))]
    with pytest.raises(ValueError, match="obstruction counter changed"):
        await controller._set_position("left", "head", 0)
    assert controller._mcr_request.await_args_list[-2].kwargs["payload"] == b"MFHL110"


async def test_legacy_foundation_does_not_request_pinch_status(controller, motion):
    from dataclasses import replace

    controller._foundation_features = replace(controller._foundation_features, generation="legacy")
    await controller._set_position("left", "head", 0)
    assert not any(
        call.args[:2] == (0x42, 0x28) for call in controller._mcr_request.await_args_list
    )


@pytest.mark.parametrize("side,selector", [("right", 0), ("left", 1)])
@pytest.mark.parametrize("preset,preset_id", [("Read", 2), ("Flat", 4)])
async def test_preset_keeps_selected_side_and_monitors_recovery(
    controller, motion, side, selector, preset, preset_id
):
    if preset == "Flat":
        motion.foundation = [
            foundation_reply(status=0x62),
            foundation_reply(status=0x63, flags=(1, 1, 0, 0)),
            foundation_reply(),
        ]
    else:
        motion.foundation = [
            foundation_reply(),
            foundation_reply(presets=0x24 if side == "left" else 0x42),
        ]
    await controller.set_foundation_preset_for_side(side, preset)
    writes = [
        call for call in controller._mcr_request.await_args_list if call.args[:2] == (0x42, 0x15)
    ]
    assert len(writes) == 1
    assert writes[0].args == (0x42, 0x15, selector, bytes((preset_id, 0)))
    assert controller._state["foundation_needs_homing"] is False


async def test_flat_does_not_mistake_homing_flag_for_recovery(controller, motion):
    motion.foundation = [foundation_reply(status=0x62)]
    with pytest.raises(ValueError, match="needs homing"):
        await controller.set_foundation_preset_for_side("left", "Flat")


async def test_preset_ack_without_execution_does_not_claim_success(controller, motion):
    with pytest.raises(ValueError, match="without confirming left preset Read"):
        await controller.set_foundation_preset_for_side("left", "Read")
    assert controller._mcr_request.await_args_list[-2].kwargs["payload"] == b"MFHL110"


async def test_already_selected_preset_can_complete_without_movement(controller, motion):
    motion.foundation = [foundation_reply(presets=0x24)]
    await controller.set_foundation_preset_for_side("left", "Read")
    assert controller._state["foundation_preset_left"] == "Read"


@pytest.mark.parametrize("before,after", [(127, 128), (255, 0), (5, 0)])
async def test_changed_obstruction_counter_cannot_wrap_or_reset_silently(
    controller, motion, before, after
):
    motion.pinch = [bytes((0, 0, 0, 0, before)), bytes((0, 0, 0, 0, after))]
    with pytest.raises(ValueError, match="obstruction counter changed"):
        await controller._set_position("left", "head", 0)


async def test_unchanged_signed_obstruction_counter_is_not_a_new_fault(controller, motion):
    motion.pinch = [bytes((0, 0, 0, 0, 128))]
    await controller._set_position("left", "head", 0)


async def test_hold_checks_fault_in_final_read_after_duration_expires(controller, motion):
    controller._coordinator.motor_pulse_count = 1
    controller._coordinator.motor_pulse_delay_ms = 1
    motion.foundation = [foundation_reply(), foundation_reply(flags=(0, 16, 0, 0))]

    async def blocked(_seconds):
        await asyncio.Event().wait()

    controller._foundation_delay = blocked
    with pytest.raises(ValueError, match="current is over"):
        await controller.bind_side("left").move_back_up()
    assert controller._state["foundation_head_left_current"] == "over"
    assert controller._mcr_request.await_args_list[-2].kwargs["payload"] == b"MFHL110"


async def test_final_read_fault_does_not_replace_cancellation(controller, motion):
    motion.foundation = [foundation_reply(), foundation_reply(flags=(0, 16, 0, 0))]
    controller._foundation_delay = AsyncMock(side_effect=asyncio.CancelledError)
    with pytest.raises(asyncio.CancelledError):
        await controller._set_position("left", "head", 50)
    assert controller._state["foundation_head_left_current"] == "over"


@pytest.mark.parametrize("operation", ["hold", "target", "preset"])
async def test_motion_cancellation_releases_and_refreshes(controller, motion, operation):
    async def cancel(_seconds):
        controller._coordinator.cancel_command.set()
        raise asyncio.CancelledError

    controller._foundation_delay = cancel
    with pytest.raises(asyncio.CancelledError):
        if operation == "hold":
            await controller.bind_side("left").move_back_up()
        elif operation == "target":
            await controller._set_position("left", "head", 50)
        else:
            await controller.set_foundation_preset_for_side("left", "Read")
    calls = controller._mcr_request.await_args_list
    assert calls[-2].kwargs["payload"] == b"MFHL110"
    assert calls[-1].args == (0x42, 0x12, 0)
    assert all(not call.kwargs["cancel_event"].is_set() for call in calls[-2:])


async def test_position_timeout_stops_and_does_not_claim_success(controller, motion, monkeypatch):
    monkeypatch.setattr(
        "custom_components.adjustable_bed.beds.sleep_number_mcr._FOUNDATION_TIMEOUT_SECONDS", 0.01
    )

    async def blocked(_seconds):
        await asyncio.Event().wait()

    controller._foundation_delay = blocked
    with pytest.raises(TimeoutError):
        await controller._set_position("left", "head", 50)
    assert controller._mcr_request.await_args_list[-2].kwargs["payload"] == b"MFHL110"


async def test_held_duration_expires_without_hanging_on_status(controller, motion):
    controller._coordinator.motor_pulse_count = 1
    controller._coordinator.motor_pulse_delay_ms = 1

    async def blocked(_seconds):
        await asyncio.Event().wait()

    controller._foundation_delay = blocked
    await controller.bind_side("left").move_back_up()
    calls = controller._mcr_request.await_args_list
    assert calls[-3].kwargs["payload"] == b"MFHL110"
    assert calls[-1].args == (0x42, 0x28)


async def test_stalled_held_target_still_releases(controller, motion, monkeypatch):
    monkeypatch.setattr(
        "custom_components.adjustable_bed.beds.sleep_number_mcr._FOUNDATION_TIMEOUT_SECONDS",
        0.01,
    )
    normal = controller._mcr_request.side_effect

    async def request(node, opcode, *args, **kwargs):
        if (node, opcode) == (0x42, 0x11):
            await asyncio.Event().wait()
        return await normal(node, opcode, *args, **kwargs)

    controller._mcr_request.side_effect = request
    with pytest.raises(TimeoutError):
        await controller.bind_side("left").move_back_up()
    assert controller._mcr_request.await_args_list[-2].kwargs["payload"] == b"MFHL110"


async def test_target_waits_for_opposite_actuator_to_stop(controller, motion):
    motion.foundation = [
        foundation_reply(),
        foundation_reply(flags=(0, 0, 1, 0)),
        foundation_reply(),
    ]
    await controller._set_position("left", "head", 0)
    assert controller._foundation_delay.await_args_list[1].args == (0.333,)
    assert controller._foundation_delay.await_count == 4


async def test_hold_keeps_refreshing_while_opposite_actuator_moves(controller, motion):
    motion.foundation = [
        foundation_reply(),
        foundation_reply(flags=(0, 0, 1, 0)),
        foundation_reply(),
    ]
    await controller.bind_side("left").move_back_up()
    calls = controller._mcr_request.await_args_list
    assert [call.args[2] for call in calls if call.args[:2] == (0x42, 0x12)] == [0, 3, 3, 0]


async def test_foundation_delay_observes_cancel_signal(controller):
    controller._coordinator.cancel_command.set()
    with pytest.raises(asyncio.CancelledError):
        await controller._foundation_delay(10)


async def test_stop_timeout_still_releases_other_side(controller, motion, monkeypatch):
    monkeypatch.setattr(
        "custom_components.adjustable_bed.beds.sleep_number_mcr._FOUNDATION_CLEANUP_TIMEOUT_SECONDS",
        0.01,
    )

    async def stop(side):
        if side == "right":
            await asyncio.Event().wait()

    controller._stop_side = AsyncMock(side_effect=stop)
    with pytest.raises(TimeoutError):
        await controller._finish_foundation_motion(("right", "left"))
    assert [call.args for call in controller._stop_side.await_args_list] == [("right",), ("left",)]
    assert controller._mcr_request.await_args.args == (0x42, 0x12, 0)


async def test_final_read_timeout_does_not_claim_success(controller, motion, monkeypatch):
    monkeypatch.setattr(
        "custom_components.adjustable_bed.beds.sleep_number_mcr._FOUNDATION_CLEANUP_TIMEOUT_SECONDS",
        0.01,
    )

    async def read(**kwargs):
        await asyncio.Event().wait()

    controller._read_foundation = read
    with pytest.raises(TimeoutError):
        await controller._finish_foundation_motion(("left",))


async def test_cleanup_failure_preserves_original_motion_error(controller, motion):
    controller._finish_foundation_motion = AsyncMock(side_effect=TimeoutError)
    with pytest.raises(ValueError, match="stopped before reaching"):
        await controller._set_position("left", "head", 50)


@pytest.mark.parametrize("configuration", [0, 3])
async def test_shared_foundation_checks_opposite_obstruction_events(
    controller, motion, configuration
):
    from dataclasses import replace

    controller._foundation_features = replace(
        controller._foundation_features, configuration=configuration
    )
    motion.pinch = [bytes(5), bytes((0, 0, 0, 0, 1))]
    with pytest.raises(ValueError, match="left head: obstruction counter changed"):
        await controller._set_position("right", "head", 0)


async def test_split_foundation_ignores_opposite_obstruction_events(controller, motion):
    motion.pinch = [bytes(5), bytes((0, 0, 0, 0, 1))]
    await controller._set_position("right", "head", 0)


async def test_hold_stops_before_reading_post_motion_obstruction_status(controller, motion):
    await controller.bind_side("left").move_back_up()
    calls = controller._mcr_request.await_args_list
    assert calls[-3].kwargs["payload"] == b"MFHL110"
    assert calls[-2].args == (0x42, 0x12, 0)
    assert calls[-1].args == (0x42, 0x28)


async def test_binding_requires_valid_reply(controller, monkeypatch):
    controller._initialized = False
    controller._async_send_frame = AsyncMock(return_value=[SimpleNamespace(payload=b"", target=0)])
    with pytest.raises(ValueError, match="assigned"):
        await controller._async_initialize_session()
    assert not controller._initialized
    sent = controller._async_send_frame.await_args.kwargs
    assert sent["payload"].hex() == "0102030405060708"
    assert sent["sub_address"] == 0


async def test_write_fragmentation_and_properties(controller):
    controller._write_gatt_with_retry = AsyncMock()
    await controller._async_write_frame(bytes(range(29)))
    assert [c.args[1] for c in controller._write_gatt_with_retry.await_args_list] == [
        bytes(range(20)),
        bytes(range(20, 29)),
    ]
    assert all(c.kwargs["response"] for c in controller._write_gatt_with_retry.await_args_list)
    controller.client.services.get_characteristic.return_value.properties = [
        "write-without-response"
    ]
    await controller._async_write_frame(b"hello")
    assert controller._write_gatt_with_retry.await_args.kwargs["response"] is True


async def test_long_read_crc_and_chunk_cycle(controller):
    import zlib

    data = b"12345678901234567890"
    controller._async_send_frame = AsyncMock(return_value=[SimpleNamespace(side=14)])
    controller._mcr_request = AsyncMock(
        side_effect=[
            zlib.crc32(data).to_bytes(4, "big") + len(data).to_bytes(4, "big"),
            data[:15],
            data[15:],
        ]
    )
    assert await controller._se_read("SREL") == data
    assert [c.args[2] for c in controller._mcr_request.await_args_list] == [2, 12, 13]


@pytest.mark.parametrize("case", ["empty", "overrun", "crc"])
async def test_long_read_rejects_bad_data(controller, case):
    controller._async_send_frame = AsyncMock(return_value=[SimpleNamespace(side=14)])
    chunks = [b"", b"", b""] if case == "empty" else [b"ab"] if case == "overrun" else [b"a"]
    controller._mcr_request = AsyncMock(side_effect=[bytes(4) + b"\x00\x00\x00\x01", *chunks])
    with pytest.raises(ValueError):
        await controller._se_read("SREL")


def test_capability_and_state_vectors(controller):
    from custom_components.adjustable_bed.beds.sleep_number_mcr_protocol import (
        decode_foundation,
        decode_massage,
        decode_pinch,
        decode_system,
    )

    features, state = decode_system(bytes.fromhex("012d641e030004"))
    assert features.generation == "360" and features.model == "FF3"
    assert features.sides == ("right", "left")
    assert state["foundation_underperforming_left"]
    state = decode_foundation(bytes.fromhex("61320a461405000900010204082156"))
    assert state["foundation_head_right"] == 50
    assert state["foundation_head_right_moving"]
    assert state["foundation_preset_right"] == "Snore"
    assert state["foundation_preset_left"] == "Zero G"
    assert state["foundation_timer_right"] == 5
    assert decode_pinch(bytes.fromhex("ff0102ff04"))["pinch_head_right_events"] == -1
    with pytest.raises(ValueError):
        decode_massage(bytes.fromhex("0004000000000000000000"), "right")


def test_smartpump_classification_vectors():
    from custom_components.adjustable_bed.beds.sleep_number_mcr_protocol import classify_smartpump

    assert classify_smartpump(bytes.fromhex("000002"), "64:00:00:00:00:00")["model"] == "360"
    assert (
        classify_smartpump(bytes.fromhex("0000120000000000"), "00:00:00:00:00:00")["model"] == "k2"
    )
    assert classify_smartpump(b"", "00:00:00:00:00:00")["model"] == "unknown"


@pytest.mark.parametrize(
    ("name", "node", "opcode", "sub", "payload", "client", "peer", "expected"),
    [
        (
            "MCR-bind",
            2,
            0,
            0,
            "0102030405060708",
            0,
            0,
            "161602000000000200000008010203040506070800fe",
        ),
        ("MCR-pump-status", 2, 18, 0, "", 4660, 22136, "1616021234567802123412000892"),
        ("MCR-set-left-50", 2, 17, 1, "0032", 4660, 22136, "16160212345678021234111200320bd6"),
        (
            "MCR-head-right30",
            66,
            17,
            0,
            "1e00ffffffffffffffffffff",
            4660,
            22136,
            "16164212345678421234110c1e00ffffffffffffffffffff5c51",
        ),
        (
            "MCR-foot-left60",
            66,
            17,
            1,
            "ffff3c00ffffffffffffffff",
            4660,
            22136,
            "16164212345678421234111cffff3c00ffffffffffffffff620d",
        ),
        (
            "MCR-recall-favorite-left",
            66,
            21,
            1,
            "0100",
            4660,
            22136,
            "16164212345678421234151201001076",
        ),
        ("MCR-save-favorite-right", 66, 22, 0, "01", 4660, 22136, "161642123456784212341601010e51"),
        (
            "MCR-footwarm-left-high60",
            66,
            41,
            1,
            "483c00",
            4660,
            22136,
            "161642123456784212342913483c001431",
        ),
        (
            "MCR-massage-right-head-low30",
            66,
            17,
            0,
            "ffffffff01ff00ffffff1e00",
            4660,
            22136,
            "16164212345678421234110cffffffff01ff00ffffff1e006127",
        ),
        (
            "MCR-outlet-left-on",
            146,
            19,
            1,
            "01ff00",
            4660,
            22136,
            "16169212345678921234131301ff001b04",
        ),
        ("MCR-sense-enable", 50, 20, 0, "0100", 4660, 22136, "16163212345678321234140201000f12"),
        (
            "MCR-stop-right",
            82,
            27,
            0,
            "4d464852313130",
            4660,
            22136,
            "161652123456785212341b074d46485231313023cf",
        ),
        ("MCR-se-read", 82, 28, 0, "53575343", 4660, 22136, "161652123456785212341c0453575343190c"),
        (
            "MCR-se-long-select",
            82,
            29,
            2,
            "53575343",
            4660,
            22136,
            "161652123456785212341d245357534319b2",
        ),
        (
            "MCR-se-write-chunk",
            82,
            29,
            9,
            "303132333435363738396162636465",
            4660,
            22136,
            "161652123456785212341d9f30313233343536373839616263646551d6",
        ),
        ("MCR-se-terminal-write", 82, 29, 10, "", 4660, 22136, "161652123456785212341da00df8"),
    ],
)
def test_all_frozen_transport_vectors(name, node, opcode, sub, payload, client, peer, expected):
    assert (
        SleepNumberMcrController._build_frame(
            command_type=node,
            status=node,
            function_code=opcode,
            side=sub,
            payload=bytes.fromhex(payload),
            sub_address=peer,
            client_address=client,
        ).hex()
        == expected
    )


async def test_failed_stop_still_releases_other_side(controller):
    controller._stop_side = AsyncMock(side_effect=[OSError("lost ack"), None])
    with pytest.raises(OSError):
        await controller._stop_sides(("right", "left"))
    assert [c.args[0] for c in controller._stop_side.await_args_list] == ["right", "left"]


async def test_response_timeout_retries_exactly_three_times(controller):
    from custom_components.adjustable_bed.beds.sleep_number_mcr import _ResponseTimeout

    controller._async_send_frame_once = AsyncMock(
        side_effect=[_ResponseTimeout(), _ResponseTimeout(), _ResponseTimeout(), []]
    )
    assert (
        await controller._async_send_frame(command_type=2, status=2, function_code=18, side=0) == []
    )
    assert controller._async_send_frame_once.await_count == 4


async def test_long_read_select_rejects_error_selector(controller):
    controller._async_send_frame = AsyncMock(
        return_value=[SimpleNamespace(side=14, payload=bytes(8))]
    )
    with pytest.raises(ValueError, match="rejected"):
        await controller._mcr_request(0x52, 0x1D, 2, b"SREL")


async def test_massage_sentinel_preserves_timer(controller):
    controller._mcr_request = AsyncMock(return_value=b"")
    await controller.async_execute_sleep_number_command(
        "massage", {"side": "right", "head": 1, "timer": 255}
    )
    assert controller._mcr_request.await_args.args[3][10:] == b"\xff\xff"


async def test_pump_single_chamber_does_not_expose_second_side(controller):
    controller._chambers = {"right": 0, "left": 0}
    controller._chambers_present = (True, True)
    controller._async_send_frame = AsyncMock(
        return_value=[SimpleNamespace(function_code=18, payload=b"\x01\x32\x41", side=0)]
    )
    await controller._async_read_pump_status()
    assert controller.sleep_number_setting_sides == ("right",)
    assert controller._state["pump_adjusting"] is True
    controller._async_send_frame.return_value[0].side = 1
    await controller._async_read_pump_status()
    assert controller.sleep_number_setting_sides == ("right", "left")


async def test_single_360_warming_writes_both_physical_sides(controller):
    controller._pressure_sides = ("right",)
    controller._mcr_request = AsyncMock(return_value=b"")
    assert controller.footwarming_climate_sides == ("left",)
    await controller.async_execute_sleep_number_command(
        "foot_warming", {"side": "left", "level": 1}
    )
    assert [c.args[2] for c in controller._mcr_request.await_args_list] == [1, 0]
    assert all(c.args[3] == b"\x1f\x78\x00" for c in controller._mcr_request.await_args_list)


def test_massage_and_warming_sides_independent_of_single_foundation(controller):
    from dataclasses import replace

    controller._foundation_features = replace(controller._foundation_features, configuration=3)
    assert controller.foundation_preset_sides == ("right",)
    assert controller.footwarming_climate_sides == ("right", "left")
    controller.validate_sleep_number_command("massage", {"side": "left", "head": 1})
    controller.validate_sleep_number_command("foot_warming", {"side": "left", "level": 1})


def test_genie_obsolete_pressure_mutations_are_not_exposed(controller):
    controller._pump_model = "genie"
    assert controller.sleep_number_setting_sides == ()
    with pytest.raises(ValueError, match="Pressure side"):
        controller.validate_sleep_number_command(
            "firmness_favorite", {"side": "right", "firmness": 50}
        )


async def test_cancelled_firmness_request_idles_pump(controller):
    controller._async_send_frame = AsyncMock(side_effect=[[], asyncio.CancelledError])
    controller._idle_pump_after_cancel = AsyncMock()
    with pytest.raises(asyncio.CancelledError):
        await controller.set_sleep_number_setting_for_side("right", 50)
    controller._idle_pump_after_cancel.assert_awaited_once()


async def test_pump_cleanup_uses_fresh_token(controller):
    controller._coordinator.cancel_command.set()
    controller._mcr_request = AsyncMock(return_value=b"")
    controller._async_read_pump_status = AsyncMock()
    await controller._idle_pump_after_cancel()
    token = controller._mcr_request.await_args.kwargs["cancel_event"]
    assert not token.is_set()
    assert controller._async_read_pump_status.await_args.kwargs["cancel_event"] is token


async def test_busy_pump_cleanup_deadline_releases_request_state(controller, monkeypatch):
    from custom_components.adjustable_bed.beds import sleep_number_mcr

    original_sleep = asyncio.sleep

    async def advance_poll(_delay):
        await original_sleep(0)

    def reply_busy(raw, *, cancel_event=None):
        request = controller._parse_frame(raw)
        response = controller._build_frame(
            command_type=2,
            status=2,
            function_code=request.function_code | 0x80,
            side=1,
            payload=b"\x01\x32\x41",
            sub_address=0,
        )
        controller._handle_mcr_notification(None, bytearray(response))

    monkeypatch.setattr(sleep_number_mcr, "_PUMP_CLEANUP_TIMEOUT_SECONDS", 0.01)
    monkeypatch.setattr(sleep_number_mcr.asyncio, "sleep", advance_poll)
    controller._async_write_frame = AsyncMock(side_effect=reply_busy)
    with pytest.raises(TimeoutError, match="Could not confirm.*pump stopped"):
        await controller._idle_pump_after_cancel()
    assert controller._state["pump_adjusting"] is True
    assert controller._async_write_frame.await_count > 1
    assert controller._outstanding_request_key is None
    assert controller._outstanding_node is None


async def test_local_write_fallback_preserves_fragments(controller):
    from bleak.exc import BleakError

    controller.client.services.get_characteristic.return_value.properties = ["write-without-response"]
    controller._write_gatt_with_retry = AsyncMock(side_effect=[BleakError("not permitted"), None, None])
    await controller._async_write_frame(bytes(range(29)))
    calls = controller._write_gatt_with_retry.await_args_list
    assert [(call.args[1], call.kwargs["response"]) for call in calls] == [
        (bytes(range(20)), True), (bytes(range(20)), False), (bytes(range(20, 29)), True),
    ]


@pytest.mark.parametrize("service", ["set_position", "set_positions"])
async def test_position_services_use_explicit_side_percentages(hass, controller, service):
    from unittest.mock import patch

    from custom_components.adjustable_bed.services import async_register_services

    coordinator = controller._coordinator
    coordinator.entry.data = {CONF_BED_TYPE: BED_TYPE_SLEEP_NUMBER_MCR}
    coordinator.disable_angle_sensing = False
    coordinator.controller = controller
    coordinator.async_seek_position = AsyncMock()

    async def run_group(operations, **kwargs):
        for operation in operations:
            await operation()

    coordinator.async_execute_command_group = AsyncMock(side_effect=run_group)
    await async_register_services(hass)
    data = {"device_id": ["test"]}
    requests = [{"motor": "left_back", "position": 95}, {"motor": "right_legs", "position": 85}]
    if service == "set_position":
        data.update(requests[0])
        requests = requests[:1]
    else:
        data["positions"] = requests
    with patch("custom_components.adjustable_bed.services._resolve_sided_targets",
               return_value=([(coordinator, "both")], [])), patch(
        "custom_components.adjustable_bed.services._validation_controller", return_value=controller
    ):
        await hass.services.async_call(DOMAIN, service, data, blocking=True)
    calls = coordinator.async_seek_position.await_args_list
    assert [(call.kwargs["position_key"], call.kwargs["target_angle"]) for call in calls] == [
        (request["motor"], request["position"]) for request in requests
    ]
    bound = MagicMock()
    bound.move_back_up = AsyncMock()
    controller.bind_side = MagicMock(return_value=bound)
    await calls[0].kwargs["move_up_fn"](controller)
    controller.bind_side.assert_called_once_with("left")
    bound.move_back_up.assert_awaited_once()



@pytest.mark.parametrize("motor,position", [("back", 50), ("left_back", 101)])
async def test_position_plan_rejects_ambiguous_axis_and_invalid_percentage(controller, motor, position):
    from unittest.mock import patch

    from homeassistant.exceptions import ServiceValidationError

    from custom_components.adjustable_bed.services import _set_position_plan

    coordinator = controller._coordinator
    coordinator.entry.data = {CONF_BED_TYPE: BED_TYPE_SLEEP_NUMBER_MCR}
    coordinator.disable_angle_sensing = False
    coordinator.async_ensure_connected = AsyncMock()
    with (
        patch("custom_components.adjustable_bed.services._validation_controller", return_value=controller),
        pytest.raises(ServiceValidationError),
    ):
        await _set_position_plan(coordinator, coordinator, [], motor, position)


@pytest.mark.parametrize("failure", [ValueError("unsupported"), TimeoutError("transport")])
async def test_optional_mcr_hydration_isolates_only_payload_failures(controller, failure):
    from unittest.mock import patch

    controller._mcr_request = AsyncMock(side_effect=[b"\x41", b"\x01\x00\x01\x00", b"system"])
    controller._async_read_pump_status = AsyncMock()
    controller._read_favorites = AsyncMock()
    controller._read_foundation = AsyncMock()
    controller._async_read_underbed_light_state = AsyncMock()
    controller._read_massage = AsyncMock(side_effect=failure)
    controller._read_warming = AsyncMock(side_effect=ValueError("payload"))
    with patch("custom_components.adjustable_bed.beds.sleep_number_mcr.decode_system",
               return_value=(controller._foundation_features, {})):
        if isinstance(failure, TimeoutError):
            with pytest.raises(TimeoutError):
                await controller.query_config()
            controller._read_warming.assert_not_awaited()
        else:
            await controller.query_config()
            assert controller._read_massage.await_count == 2
            assert controller._read_warming.await_count == 2


@pytest.mark.parametrize("reverse", [True, False])
def test_unrelated_manufacturer_block_does_not_erase_model(controller, reverse):
    blocks = [(1, b"\x12\x06\x00\x00\x00"), (2, b"unrelated")]
    if reverse:
        blocks.reverse()
    actual = SleepNumberMcrController(controller._coordinator, manufacturer_data=dict(blocks))
    assert actual._pump_model == "360"


async def test_changed_foundation_removes_only_stale_position_numbers(hass, sleep_number_mcr_coordinator):
    from dataclasses import replace

    from homeassistant.helpers import entity_registry as er

    from custom_components.adjustable_bed.number import _number_entities_for

    coordinator = await sleep_number_mcr_coordinator(address="AA:BB:CC:DD:EE:51", name="MCR", entry_id="mcr_cleanup")
    controller = coordinator.controller
    registry = er.async_get(hass)
    keys = ("back_position_left", "back_position_right", "legs_position_left", "legs_position_right", "sleep_number_left")
    entries = {key: registry.async_get_or_create(
        "number", DOMAIN, coordinator.entity_unique_id(key), config_entry=coordinator.entry
    ) for key in keys}
    controller._foundation_features = replace(controller._foundation_features, configuration=0, foot=False)
    _number_entities_for(hass, coordinator)
    for key in ("back_position_left", "legs_position_left", "legs_position_right"):
        assert registry.async_get(entries[key].entity_id) is None
    for key in ("back_position_right", "sleep_number_left"):
        assert registry.async_get(entries[key].entity_id) is not None
