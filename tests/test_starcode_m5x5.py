"""Frozen AdjustableM5X5 command vectors and transport/session safety."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bleak.exc import BleakError
from homeassistant.core import HomeAssistant

from custom_components.adjustable_bed.beds.starcode_m5x5 import (
    DEVICE_INFORMATION,
    FIRMWARE,
    MANUFACTURER,
    NOTIFY,
    SERVICE,
    WRITE,
    StarcodeM5X5Controller,
    profile_from_name,
)
from custom_components.adjustable_bed.beds.starcode_m5x5_protocol import clock_packet

# ELEVATE (P3) rows are verified against the star_elevate controller instead.
VECTORS = [
    case
    for case in json.loads(
        Path(__file__).with_name("fixtures").joinpath("starcode_m5x5_commands.json").read_text()
    )
    if case["profile"] != "elevate"
]
NOW = datetime(2026, 10, 1, 12, 34, 56)


def make_controller(
    hass: HomeAssistant, profile: str = "cb25", dialect: str = "legacy"
) -> StarcodeM5X5Controller:
    client = MagicMock()
    client.is_connected = True
    client.start_notify = AsyncMock()
    client.stop_notify = AsyncMock()
    client.read_gatt_char = AsyncMock(
        side_effect=lambda uuid: (
            b"STAR"
            if uuid == MANUFACTURER and dialect == "star"
            else b"1.2.3"
            if uuid == FIRMWARE
            else b""
        )
    )
    client.services.get_characteristic.side_effect = lambda uuid: SimpleNamespace(
        service_uuid=SERVICE if uuid in (WRITE, NOTIFY) else DEVICE_INFORMATION,
        properties=["write-without-response"]
        if uuid == WRITE
        else ["notify"]
        if uuid == NOTIFY
        else ["read"],
    )
    coordinator = MagicMock()
    coordinator.hass = hass
    coordinator.entry = SimpleNamespace(entry_id="row005", data={})
    coordinator.name = "STAR252201123456"
    coordinator.address = "AA:00:00:00:00:05"
    coordinator.client = client
    coordinator.cancel_command = asyncio.Event()
    coordinator.motor_pulse_count = 2
    coordinator.motor_pulse_delay_ms = 100
    controller = StarcodeM5X5Controller(coordinator, profile=profile)
    controller.dialect = dialect
    controller._ready = True
    return controller


@pytest.mark.parametrize("case", VECTORS, ids=lambda c: c["id"])
async def test_all_command_vectors(hass: HomeAssistant, case: dict[str, object]) -> None:
    controller = make_controller(hass, str(case["profile"]), str(case["dialect"]))
    action = str(case["action"])
    controller.device_name = "STAR252201123456" if action == "mode_special" else "STAR259999123456"
    with patch.object(controller, "write_command", AsyncMock()) as writes:
        if action == "stop":
            await controller.stop_all()
        elif action == "interrupt":
            await controller.interrupt()
        elif action == "light_on":
            await controller.lights_on()
        elif action == "light_off":
            await controller.lights_off()
        elif action == "light_cycle":
            await controller.lights_cycle()
        elif action == "brightness":
            await controller.set_brightness(4)
        elif action == "color":
            await controller.set_color_index(4)
        elif action.startswith("timer"):
            await controller.set_massage_timer(int(action[5:]))
        elif action.startswith("mode_"):
            await controller.light_mode()
        elif action.startswith("initialize"):
            with patch(
                "custom_components.adjustable_bed.beds.starcode_m5x5.dt_util.now", return_value=NOW
            ):
                await controller.start_notify()
        else:
            await controller.app_action(action)
    expanded = []
    for call in writes.await_args_list:
        expanded.extend([call.args[0]] * call.kwargs.get("repeat_count", 1))
    raw = str(case["vector"]).replace("(v&ff)", "04")
    if action == "initialize_clock":
        expected = [clock_packet(NOW)]
    else:
        expected = [bytes.fromhex(v.strip()) for v in raw.split(";")]
    source_count = int(case["source_count"])
    if source_count in (-1, 35, 55):
        count = 2 if source_count == -1 else source_count
        # Save preflight and safe release are intentional repairs to the app's cleanup.
        offset = 1 if action.startswith("save_") or action == "reset" else 0
        assert expanded[offset : offset + count] == [expected[0]] * count
        if source_count == 35:
            assert len(expanded) == offset + count
        if source_count == -1 or source_count == 55:
            assert expanded[offset + count] == controller_stop(controller)
        if source_count == -1 and action.startswith("massage_"):
            assert expanded[-1] == bytes.fromhex(
                "5ab000a5" if controller.dialect == "star" else "00b0"
            )
    elif action.startswith("initialize"):
        assert expected[0] in expanded
    else:
        assert expanded == expected


def controller_stop(controller: StarcodeM5X5Controller) -> bytes:
    return bytes.fromhex(
        "5a010310300fa5" if controller.dialect == "star" else "05020000000000"
    )


@pytest.mark.parametrize(
    ("name", "profile"),
    [
        ("STAR254205foo", "f23"),
        ("STAR255401foo", "f23"),
        ("STAR255402foo", "kneading"),
        ("STAR255403foo", "kneading"),
        ("STAR25999", "cb25"),
        ("ELEVATEfoo", None),
        ("star25999", None),
        ("TV", None),
    ],
)
def test_exact_factory_precedence(name: str, profile: str | None) -> None:
    assert profile_from_name(name) == profile


@pytest.mark.parametrize("profile", ["cb25", "f23", "kneading"])
async def test_required_roles_and_without_response(hass: HomeAssistant, profile: str) -> None:
    c = make_controller(hass, profile, "star")
    events = []

    async def subscribe(uuid, callback):
        events.append(("subscribe", uuid))

    async def write(uuid, packet, **kwargs):
        assert kwargs["response"] is False
        events.append(("write", packet))

    c.client.start_notify.side_effect = subscribe
    with (
        patch.object(c, "_write_gatt_with_retry", side_effect=write),
        patch("custom_components.adjustable_bed.beds.starcode_m5x5.asyncio.sleep", AsyncMock()),
    ):
        await c.start_notify()
    assert events[0] == ("subscribe", NOTIFY)
    assert events[1] == ("write", bytes.fromhex("5a0b00a5"))
    c.client.services.get_characteristic.side_effect = lambda uuid: (
        None
        if uuid == FIRMWARE
        else SimpleNamespace(properties=["notify", "write-without-response"])
    )
    with pytest.raises(ConnectionError, match="requires characteristic"):
        await c.start_notify()


async def test_exact_manufacturer_failure_legacy_no_wake(hass: HomeAssistant) -> None:
    c = make_controller(hass, "cb25")
    c.client.read_gatt_char.side_effect = BleakError("missing optional read")
    with patch.object(c, "write_command", AsyncMock()) as writes:
        await c.start_notify()
    assert c.dialect == "legacy"
    assert c._firmware_read_ok is False
    assert [call.args[0] for call in writes.await_args_list] == [bytes.fromhex("00b0")]


async def test_cancelled_movement_still_releases(hass: HomeAssistant) -> None:
    c = make_controller(hass, "f23", "legacy")

    async def write(command, **kwargs):
        if kwargs.get("repeat_count", 1) > 1:
            c._coordinator.cancel_command.set()
            raise asyncio.CancelledError

    with (
        patch.object(c, "write_command", AsyncMock(side_effect=write)) as writes,
        pytest.raises(asyncio.CancelledError),
    ):
        await c.move_head_up()
    assert writes.await_args_list[-1].args[0] == bytes.fromhex("05020000000000")
    assert not writes.await_args_list[-1].kwargs["cancel_event"].is_set()


async def test_stale_callbacks_are_discarded(hass: HomeAssistant) -> None:
    c = make_controller(hass)
    with patch.object(c, "write_command", AsyncMock()):
        await c.start_notify()
        old = c.client.start_notify.await_args.args[1]
        await c.stop_notify()
        await c.start_notify()
    c._coordinator.handle_controller_state_updates.reset_mock()
    old(MagicMock(), bytearray.fromhex("a50d00000a140b1e0c00280000000000000000"))
    c._coordinator.handle_controller_state_updates.assert_not_called()
    assert c.client.stop_notify.await_count == 1


async def test_cancelled_firmware_read_unsubscribes_owned_session(hass: HomeAssistant) -> None:
    c = make_controller(hass)
    owned = c.client
    owned.read_gatt_char.side_effect = asyncio.CancelledError
    with pytest.raises(asyncio.CancelledError):
        await c.start_notify()
    owned.stop_notify.assert_awaited_once_with(NOTIFY)
    assert not c.ready
    assert not c._subscribed


@pytest.mark.parametrize("boundary", [FIRMWARE, MANUFACTURER])
@pytest.mark.parametrize("change", ["dispose", "replace"])
async def test_startup_read_cannot_revive_superseded_session(
    hass: HomeAssistant,
    boundary: str,
    change: str,
) -> None:
    c = make_controller(hass)
    owned = c.client
    entered = asyncio.Event()
    resume = asyncio.Event()

    async def read(uuid):
        if uuid == boundary:
            entered.set()
            await resume.wait()
        return b"1.2.3" if uuid == FIRMWARE else b"STAR"

    owned.read_gatt_char.side_effect = read
    with patch.object(c, "write_command", AsyncMock()) as writes:
        starting = asyncio.create_task(c.start_notify())
        await entered.wait()
        if change == "dispose":
            await c.stop_notify()
        else:
            c._coordinator.client = MagicMock(is_connected=True)
        resume.set()
        with pytest.raises(asyncio.CancelledError):
            await starting
    assert not c.ready
    writes.assert_not_awaited()
    owned.stop_notify.assert_awaited_once_with(NOTIFY)


async def test_stale_read_result_cannot_overwrite_restarted_session_firmware(
    hass: HomeAssistant,
) -> None:
    c = make_controller(hass)
    entered = asyncio.Event()
    resume = asyncio.Event()
    firmware_reads = 0

    async def read(uuid):
        nonlocal firmware_reads
        if uuid == FIRMWARE:
            firmware_reads += 1
            if firmware_reads == 1:
                entered.set()
                await resume.wait()
                return b"old firmware"
            return b"current firmware"
        return b"STAR"

    c.client.read_gatt_char.side_effect = read
    with patch.object(c, "write_command", AsyncMock()):
        old_start = asyncio.create_task(c.start_notify())
        await entered.wait()
        await c.stop_notify()
        await c.start_notify()
        resume.set()
        with pytest.raises(asyncio.CancelledError):
            await old_start
    assert c.ready
    assert c.protocol_diagnostics["firmware"] == "current firmware"
    assert c.protocol_diagnostics["firmware_read_ok"] is True


async def test_init_tick_cannot_write_through_replacement_client(hass: HomeAssistant) -> None:
    c = make_controller(hass, dialect="star")
    owned = c.client
    owned.write_gatt_char = AsyncMock()
    replacement = make_controller(hass, dialect="star").client
    replacement.write_gatt_char = AsyncMock()
    entered = asyncio.Event()
    resume = asyncio.Event()

    async def pause_tick(seconds):
        entered.set()
        await resume.wait()

    with patch(
        "custom_components.adjustable_bed.beds.starcode_m5x5.asyncio.sleep",
        side_effect=pause_tick,
    ):
        starting = asyncio.create_task(c.start_notify())
        await entered.wait()
        c._coordinator.client = replacement
        resume.set()
        with pytest.raises(asyncio.CancelledError):
            await starting
    owned.write_gatt_char.assert_not_awaited()
    replacement.write_gatt_char.assert_not_awaited()


@pytest.mark.parametrize("change", ["client", "generation"])
async def test_queued_ble_lane_rechecks_owned_writer_session(
    hass: HomeAssistant,
    change: str,
) -> None:
    c = make_controller(hass, dialect="star")
    owned = c.client
    owned.write_gatt_char = AsyncMock()
    replacement = make_controller(hass, dialect="star").client
    replacement.write_gatt_char = AsyncMock()
    queued = asyncio.Event()
    c._coordinator.record_command_trace.side_effect = lambda **kwargs: queued.set()
    await c.ble_lock.acquire()
    with patch("custom_components.adjustable_bed.beds.starcode_m5x5.asyncio.sleep", AsyncMock()):
        writing = asyncio.create_task(c.write_command(bytes.fromhex("5a0b00a5")))
        await queued.wait()
        if change == "client":
            c._coordinator.client = replacement
        else:
            c._generation += 1
        c.ble_lock.release()
        with pytest.raises(asyncio.CancelledError):
            await writing
    owned.write_gatt_char.assert_not_awaited()
    replacement.write_gatt_char.assert_not_awaited()


async def test_replaced_client_unsubscribes_old_client_without_stop_on_new(
    hass: HomeAssistant,
) -> None:
    c = make_controller(hass)
    owned = c.client
    with patch.object(c, "write_command", AsyncMock()) as writes:
        await c.start_notify()
        writes.reset_mock()
        replacement = MagicMock(is_connected=True)
        c._coordinator.client = replacement
        await c.stop_notify()
    owned.stop_notify.assert_awaited_once_with(NOTIFY)
    replacement.stop_notify.assert_not_called()
    writes.assert_not_awaited()
    assert not c.ready


async def test_early_notification_waits_for_manufacturer_dialect(hass: HomeAssistant) -> None:
    c = make_controller(hass, "cb25", "star")
    payload = bytearray.fromhex("a50d00000a140b1e0c00280000000000000000")

    async def subscribe(uuid, callback):
        callback(MagicMock(), payload)
        c._coordinator.handle_controller_state_updates.assert_not_called()

    c.client.start_notify.side_effect = subscribe
    with patch.object(c, "write_command", AsyncMock()):
        await c.start_notify()
    assert c.dialect == "star"
    assert c._coordinator.handle_controller_state_updates.call_count >= 1


async def test_sender_tick_cancel_and_failed_delivery(hass: HomeAssistant) -> None:
    c = make_controller(hass)
    tick = asyncio.get_running_loop().time() + 0.1
    c._next_tick = tick
    with (
        patch(
            "custom_components.adjustable_bed.beds.starcode_m5x5.asyncio.sleep", AsyncMock()
        ) as sleep,
        patch.object(c, "_write_gatt_with_retry", AsyncMock()) as write,
    ):
        await c.write_command(b"one", repeat_count=3)
    assert sleep.await_args_list[0].args[0] > 0
    assert sleep.await_count == 3
    assert write.await_count == 3
    c._coordinator.cancel_command.set()
    with patch.object(c, "_write_gatt_with_retry", AsyncMock()) as write:
        await c.write_command(b"cancelled")
    write.assert_not_awaited()
    c._coordinator.cancel_command.clear()
    with (
        patch("custom_components.adjustable_bed.beds.starcode_m5x5.asyncio.sleep", AsyncMock()),
        patch.object(
            c, "_write_gatt_with_retry", AsyncMock(side_effect=BleakError("delivery failed"))
        ),
        pytest.raises(BleakError, match="delivery failed"),
    ):
        await c.write_command(b"failed")


async def test_profile_capability_boundaries(hass: HomeAssistant) -> None:
    bed_only_capabilities = (
        "supports_memory_presets",
        "supports_preset_anti_snore",
        "supports_preset_tv",
        "supports_preset_lounge",
        "supports_massage",
        "auto_enable_massage",
        "supports_lights",
        "supports_light",
        "supports_discrete_light_control",
        "supports_light_state_feedback",
        "supports_massage_timer",
        "supports_massage_wave_direction_control",
        "supports_head_massage_intensity_step_control",
        "supports_foot_massage_intensity_step_control",
        "supports_massage_off_control",
        "supports_massage_toggle_control",
    )
    # ELEVATE lifts use the star_elevate bed type, not an app bedding class.
    with pytest.raises(ValueError, match="bedding class"):
        make_controller(hass, "elevate")
    for profile in ("cb25", "f23", "kneading"):
        c = make_controller(hass, profile)
        assert all(getattr(c, capability) is True for capability in bed_only_capabilities)
        assert c.memory_slot_count == 2
        assert len(c.motor_control_specs) == 4
        assert [s.key for s in c.controller_number_specs] == ["starcode_brightness"]
        assert c.controller_select_specs[0].options == tuple(str(i) for i in range(8))
        assert not c.supports_massage_intensity_control


EXISTING_LEAVES = json.loads(
    Path(__file__).with_name("fixtures").joinpath("starcode_m5x5_existing_leaves.json").read_text()
)


@pytest.mark.parametrize("case", EXISTING_LEAVES, ids=lambda case: case["id"])
def test_all_frozen_existing_leaf_proofs(case: dict[str, object]) -> None:
    from custom_components.adjustable_bed.beds import sleepys_box25
    from custom_components.adjustable_bed.beds.star_elevate import _elevate_command
    from custom_components.adjustable_bed.beds.starcode_m5x5_protocol import (
        extended_packet,
        normal_packet,
    )

    raw_arguments = case["arguments"]
    assert isinstance(raw_arguments, list)
    arguments: list[int] = []
    for argument in raw_arguments:
        assert isinstance(argument, int)
        arguments.append(argument)
    vector = case["vector"]
    assert isinstance(vector, str)
    expected = bytes.fromhex(vector)
    name = case["function"]
    if name == "_legacy_normal":
        assert len(arguments) == 1
        actual = sleepys_box25._legacy_normal(arguments[0])
        replacement = normal_packet(arguments[0], "legacy")
    elif name == "_legacy_extended":
        assert len(arguments) == 2
        actual = sleepys_box25._legacy_extended(arguments[0], arguments[1])
        replacement = extended_packet(arguments[0], arguments[1], "legacy")
    elif name == "_star_command":
        assert len(arguments) == 2
        actual = sleepys_box25._star_command(arguments[0], arguments[1])
        replacement = normal_packet(0x03100000 | (arguments[1] << 8) | arguments[0], "star")
    elif name == "_star_extended":
        assert len(arguments) == 2
        actual = sleepys_box25._star_extended(arguments[0], arguments[1])
        replacement = extended_packet(arguments[0], arguments[1], "star")
    else:
        assert name == "_elevate_command"
        assert len(arguments) == 1
        actual = _elevate_command(arguments[0])
        replacement = normal_packet(0x03103000 | arguments[0], "star")
    assert actual == replacement == expected
