"""Row059 cluster-015: INNOVA profile and Bedsense Bases on the ORE comfort-bed controller.

Every frame literal comes from the accepted clean-room reports for
com.ore.sfm 2.0 (3) and com.ore.sfmc2bedsence 1.1 (3); the notification inputs
are the INNOVA report's synthetic parser fixtures, not captured traffic.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, call

import pytest
import voluptuous as vol
from bleak.exc import BleakError
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed.beds.innova import (
    HELD_CONTROLS,
    STATE_LIGHT,
    STATE_MASSAGE_TIMER,
    InnovaController,
    innova_frame,
    innova_rename_frame,
    parse_innova_status,
)
from custom_components.adjustable_bed.beds.keeson import KeesonController
from custom_components.adjustable_bed.beds.ore_comfort_bed import OreComfortBedController
from custom_components.adjustable_bed.const import (
    BED_TYPE_KEESON,
    CONF_BED_TYPE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_HAS_MASSAGE,
    CONF_MOTOR_COUNT,
    CONF_PREFERRED_ADAPTER,
    CONF_PROTOCOL_VARIANT,
    DOMAIN,
    KEESON_BASE_NOTIFY_CHAR_UUID,
    KEESON_BASE_WRITE_CHAR_UUID,
    KEESON_VARIANT_ADJUSTABLE_LITE,
    KEESON_VARIANT_BASE,
    KEESON_VARIANT_BEDSENSE_BASES,
    KEESON_VARIANT_INNOVA,
    KEESON_VARIANT_RESTONIC_B,
    OFFLINE_CAPABILITY_SAFE_VARIANTS,
)
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator

Action = Callable[[Any], Awaitable[None]]
ZERO = "e5fe160000000006"
HOLD = 10  # The app refreshes every 100 ms; the default burst is 10 x 100 ms.

# INNOVA (little-endian keys): (action, motor count, report row, frame, held?)
INNOVA_VECTORS: list[tuple[Action, int, str, str, bool]] = [
    (lambda c: c.move_head_up(), 4, "C01", "e5fe160100000005", True),
    (lambda c: c.move_feet_up(), 4, "C02", "e5fe160400000002", True),
    (lambda c: c.move_head_down(), 4, "C03", "e5fe160200000004", True),
    (lambda c: c.move_feet_down(), 4, "C04", "e5fe1608000000fe", True),
    (lambda c: c.lights_toggle(), 2, "C05", "e5fe160000020004", False),
    (lambda c: c.massage_head_up(), 2, "C06", "e5fe1600080000fe", False),
    (lambda c: c.massage_mode_step(), 2, "C07", "e5fe160002000004", False),
    (lambda c: c.massage_foot_up(), 2, "C08", "e5fe160004000002", False),
    (lambda c: c.massage_head_down(), 2, "C09", "e5fe160000800086", False),
    (lambda c: c.massage_level_step(), 2, "C10", "e5fe160001000005", False),
    (lambda c: c.massage_foot_down(), 2, "C11", "e5fe160000000105", False),
    (lambda c: c.massage_timer_hold(), 2, "C12", "e5fe160002000004", True),
    (lambda c: c.preset_zero_g(), 2, "C13", "e5fe1600100000f6", False),
    (lambda c: c.preset_flat(), 2, "C14", "e5fe1600000008fe", False),
    (lambda c: c.preset_memory(1), 2, "C15", "e5fe1600200000e6", True),
    (lambda c: c.preset_memory(2), 2, "C16", "e5fe1600400000c6", True),
    (lambda c: c.move_head_up(), 2, "C17", "e5fe160100000005", True),
    (lambda c: c.move_feet_up(), 2, "C18", "e5fe160400000002", True),
    (lambda c: c.move_head_down(), 2, "C19", "e5fe160200000004", True),
    (lambda c: c.move_feet_down(), 2, "C20", "e5fe1608000000fe", True),
    (lambda c: c.move_union_up(), 2, "C21", "e5fe160500000001", True),
    (lambda c: c.move_union_down(), 2, "C22", "e5fe160a000000fc", True),
    (lambda c: c.move_head_up(), 3, "C23", "e5fe160100000005", True),
    (lambda c: c.move_feet_up(), 3, "C24", "e5fe160400000002", True),
    (lambda c: c.move_head_down(), 3, "C25", "e5fe160200000004", True),
    (lambda c: c.move_feet_down(), 3, "C26", "e5fe1608000000fe", True),
    (lambda c: c.move_lumbar_up(), 3, "C27", "e5fe1640000000c6", True),
    (lambda c: c.move_lumbar_down(), 3, "C28", "e5fe168000000086", True),
    (lambda c: c.move_lumbar_up(), 4, "C29", "e5fe1640000000c6", True),
    (lambda c: c.move_lumbar_down(), 4, "C30", "e5fe168000000086", True),
    (lambda c: c.move_tilt_up(), 4, "C31", "e5fe1610000000f6", True),
    (lambda c: c.move_tilt_down(), 4, "C32", "e5fe1620000000e6", True),
    (lambda c: c.stop_all(), 2, "C33", ZERO, False),
]

# Bedsense Bases report vectors (big-endian), run through OreComfortBedController.
BEDSENSE_VECTORS: list[tuple[Action, int, str, bool]] = [
    (lambda c: c.move_back_up(), 2, "e5fe160000000105", True),
    (lambda c: c.move_back_down(), 2, "e5fe160000000204", True),
    (lambda c: c.move_feet_up(), 2, "e5fe160000000402", True),
    (lambda c: c.move_feet_down(), 2, "e5fe1600000008fe", True),
    (lambda c: c._move_axis("both", True), 2, "e5fe1600000010f6", True),
    (lambda c: c._move_axis("both", False), 2, "e5fe1600000020e6", True),
    (lambda c: c.move_head_up(), 3, "e5fe1600000010f6", True),
    (lambda c: c.move_head_down(), 3, "e5fe1600000020e6", True),
    (lambda c: c._move_axis("waist", True), 4, "e5fe1600000010f6", True),
    (lambda c: c._move_axis("waist", False), 4, "e5fe1600000020e6", True),
    (lambda c: c.move_lumbar_up(), 4, "e5fe1600000040c6", True),
    (lambda c: c.move_lumbar_down(), 4, "e5fe160000008086", True),
    (lambda c: c.stop_all(), 2, ZERO, False),
    (lambda c: c.preset_zero_g(), 2, "e5fe160100000104", False),
    (lambda c: c.program_zero_g(), 2, "e5fe1620000001e5", False),
    (lambda c: c.preset_flat(), 2, "e5fe160100000203", False),
    (lambda c: c.program_flat(), 2, "e5fe1620000002e4", False),
    (lambda c: c.preset_memory(1), 2, "e5fe1601000008fd", False),
    (lambda c: c.program_memory(1), 2, "e5fe1620000008de", False),
    (lambda c: c.preset_memory(2), 2, "e5fe1601000009fc", False),
    (lambda c: c.program_memory(2), 2, "e5fe1620000009dd", False),
    (lambda c: c.set_massage_timer_option("10"), 2, "e5fe1610000030c6", False),
    (lambda c: c.set_massage_timer_option("20"), 2, "e5fe1610000031c5", False),
    (lambda c: c.set_massage_timer_option("30"), 2, "e5fe1610000032c4", False),
    (lambda c: c.lights_on(), 2, "e5fe1631000001d4", False),
    (lambda c: c.lights_off(), 2, "e5fe1631000000d5", False),
]
BEDSENSE_MASSAGE = {
    "wave": ("e5fe1610000020d6", "e5fe1610000021d5", "e5fe1610000022d4", "e5fe1610000023d3"),
    "head": ("e5fe1610000010e6", "e5fe1610000011e5", "e5fe1610000012e4", "e5fe1610000013e3"),
    "foot": ("e5fe1611000010e5", "e5fe1611000011e4", "e5fe1611000012e3", "e5fe1611000013e2"),
}


@pytest.fixture
def entry(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="ORE bed",
        data={
            CONF_ADDRESS: "AA:BB:CC:DD:EE:59",
            CONF_NAME: "ORE bed",
            CONF_BED_TYPE: BED_TYPE_KEESON,
            CONF_MOTOR_COUNT: 2,
            CONF_HAS_MASSAGE: False,
            CONF_DISABLE_ANGLE_SENSING: True,
            CONF_PREFERRED_ADAPTER: "auto",
        },
        unique_id="AA:BB:CC:DD:EE:59",
        entry_id="ore_sfm_entry",
    )
    entry.add_to_hass(hass)
    return entry


@pytest.fixture
async def coordinator(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    mock_coordinator_connected,
    mock_bleak_client: MagicMock,
) -> AdjustableBedCoordinator:
    coordinator = AdjustableBedCoordinator(hass, entry)
    await coordinator.async_connect()
    # The app's two roles; tests needing other layouts replace them.
    mock_bleak_client.services = _services(
        (KEESON_BASE_WRITE_CHAR_UUID, ["write"]), (KEESON_BASE_NOTIFY_CHAR_UUID, ["notify"])
    )
    return coordinator


@pytest.fixture
def no_sleep(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    """Record asyncio.sleep and the release wait instead of waiting."""
    sleep = AsyncMock()
    monkeypatch.setattr("custom_components.adjustable_bed.beds.base.asyncio.sleep", sleep)
    wait = AsyncMock()
    monkeypatch.setattr("custom_components.adjustable_bed.beds.innova._wait_unless_cancelled", wait)
    sleep.release_wait = wait
    return sleep


def _innova(coordinator: AdjustableBedCoordinator, motors: int = 2) -> InnovaController:
    coordinator._motor_count = motors
    return InnovaController(coordinator)


class _Char:
    """A hashable GATT characteristic stand-in (the write mock keys on it)."""

    def __init__(self, uuid: str, properties: list[str], handle: int) -> None:
        self.uuid = uuid
        self.properties = properties
        self.handle = handle
        self.descriptors: list[object] = []


def _services(*chars: tuple[str, list[str]]) -> list[SimpleNamespace]:
    return [
        SimpleNamespace(
            uuid="0000ffe5-0000-1000-8000-00805f9b34fb",
            characteristics=[
                _Char(uuid, props, index) for index, (uuid, props) in enumerate(chars)
            ],
        )
    ]


async def _yield() -> None:
    """Let other tasks run without asyncio.sleep, which the fixtures replace."""
    future = asyncio.get_running_loop().create_future()
    asyncio.get_running_loop().call_soon(future.set_result, None)
    await future


def _bedsense(
    coordinator: AdjustableBedCoordinator, client: MagicMock, motors: int = 2
) -> OreComfortBedController:
    client.services = _services(
        (KEESON_BASE_WRITE_CHAR_UUID, ["write"]), (KEESON_BASE_NOTIFY_CHAR_UUID, ["notify"])
    )
    coordinator._motor_count = motors
    return OreComfortBedController(coordinator, app=KEESON_VARIANT_BEDSENSE_BASES)


def _written(client: MagicMock) -> list[str]:
    return [bytes(c.args[1]).hex() for c in client.write_gatt_char.await_args_list]


def test_innova_builder_is_little_endian():
    """The asymmetric key proves INNOVA's byte order; Bedsense's is big-endian."""
    assert innova_frame(0x12345678).hex() == "e5fe1678563412f2"
    assert innova_frame(1).hex() == "e5fe160100000005"
    assert sum(innova_frame(0x80)) % 256 == 0xFF


@pytest.mark.parametrize(("action", "motors", "row", "frame", "held"), INNOVA_VECTORS)
async def test_innova_controls_send_the_artifact_frames(
    coordinator, mock_bleak_client: MagicMock, no_sleep, action, motors, row, frame, held
):
    await action(_innova(coordinator, motors))
    expected = [frame] * HOLD + [ZERO] if held else [frame]
    assert _written(mock_bleak_client) == expected, row


@pytest.mark.parametrize(("action", "motors", "frame", "held"), BEDSENSE_VECTORS)
async def test_bedsense_report_vectors_on_the_ore_comfort_controller(
    coordinator, mock_bleak_client: MagicMock, no_sleep, action, motors, frame, held
):
    await action(_bedsense(coordinator, mock_bleak_client, motors))
    expected = [frame] * HOLD + [ZERO] if held else [frame]
    assert _written(mock_bleak_client) == expected


async def test_bedsense_massage_report_vectors(coordinator, mock_bleak_client: MagicMock, no_sleep):
    controller = _bedsense(coordinator, mock_bleak_client)
    await controller.massage_start()  # Report defaults: wave, head, foot at bucket 1.
    assert _written(mock_bleak_client) == [
        "e5fe1610000021d5",
        "e5fe1610000011e5",
        "e5fe1611000011e4",
    ]
    for zone, frames in BEDSENSE_MASSAGE.items():
        for level, frame in enumerate(frames):
            mock_bleak_client.write_gatt_char.reset_mock()
            await controller.set_massage_level(zone, level)
            assert _written(mock_bleak_client) == [frame]
    mock_bleak_client.write_gatt_char.reset_mock()
    await controller.massage_off()
    assert _written(mock_bleak_client) == ["e5fe1610000010e6", "e5fe1611000010e5"]


async def test_hold_timing_and_single_send_delay(
    coordinator, mock_bleak_client: MagicMock, no_sleep
):
    """Holds refresh every 100 ms; singles sleep 100 ms; release waits 100 ms."""
    controller = _innova(coordinator)
    assert controller.motor_pulse_settings() == (10, 100)
    await controller.move_head_up()
    assert no_sleep.await_args_list == [call(0.1)] * (HOLD - 1)
    assert no_sleep.release_wait.await_args.args[1] == 0.1
    no_sleep.reset_mock()
    await controller.preset_zero_g()
    assert no_sleep.await_args_list == [call(0.1)]


async def test_stop_sends_the_zero_key_at_once(coordinator, mock_bleak_client: MagicMock, no_sleep):
    await _innova(coordinator).stop_all()
    assert _written(mock_bleak_client) == [ZERO]
    no_sleep.release_wait.assert_not_awaited()


async def test_cancelling_mid_release_still_writes_the_zero_key(
    coordinator, mock_bleak_client: MagicMock, monkeypatch: pytest.MonkeyPatch, no_sleep
):
    """A task cancelled during the 100 ms release wait sends the zero key at once."""
    controller = _innova(coordinator)
    waiting = asyncio.Event()

    async def wait(_event: asyncio.Event, _seconds: float) -> None:
        waiting.set()
        await asyncio.Event().wait()

    monkeypatch.setattr("custom_components.adjustable_bed.beds.innova._wait_unless_cancelled", wait)
    task = asyncio.create_task(controller.move_feet_up())
    await waiting.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert _written(mock_bleak_client) == ["e5fe160400000002"] * HOLD + [ZERO]


@pytest.mark.parametrize("cancellations", [1, 2, 3])
async def test_release_write_survives_repeated_cancellations(
    coordinator, mock_bleak_client: MagicMock, no_sleep, cancellations
):
    """Cancelling during the in-flight zero-key write, even repeatedly, cannot drop it."""
    controller = _innova(coordinator)
    started, finish = asyncio.Event(), asyncio.Event()
    written: list[str] = []

    async def slow_write(_char, data, response=True):
        if bytes(data).hex() == ZERO:
            started.set()
            await finish.wait()
        written.append(bytes(data).hex())

    mock_bleak_client.write_gatt_char.side_effect = slow_write
    task = asyncio.create_task(controller.stop_all())
    await started.wait()
    for _ in range(cancellations):
        task.cancel()
        await _yield()
        assert not task.done()
    finish.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert written == [ZERO]


async def test_duplicate_roles_use_the_last_ffe9_and_ffe4(
    coordinator, mock_bleak_client: MagicMock, no_sleep
):
    """Like the app, the last FFE9 and FFE4 found across services win."""
    first = SimpleNamespace(
        uuid="0000ffe5-0000-1000-8000-00805f9b34fb",
        characteristics=[
            _Char(KEESON_BASE_WRITE_CHAR_UUID, ["write"], 1),
            _Char(KEESON_BASE_NOTIFY_CHAR_UUID, ["notify"], 2),
        ],
    )
    second = SimpleNamespace(
        uuid="0000ffe0-0000-1000-8000-00805f9b34fb",
        characteristics=[
            _Char(KEESON_BASE_NOTIFY_CHAR_UUID, ["notify"], 3),
            _Char(KEESON_BASE_WRITE_CHAR_UUID, ["write", "write-without-response"], 4),
        ],
    )
    mock_bleak_client.services = [first, second]
    controller = _innova(coordinator)
    await controller.preset_flat()
    await controller.start_notify(None)
    target = mock_bleak_client.write_gatt_char.await_args
    assert target.args[0] is second.characteristics[1]
    assert target.kwargs["response"] is False
    assert mock_bleak_client.start_notify.await_args.args[0] is second.characteristics[0]


async def test_a_stop_during_the_hold_releases_immediately(
    coordinator, mock_bleak_client: MagicMock, monkeypatch: pytest.MonkeyPatch, no_sleep
):
    controller = _innova(coordinator)

    async def stop(_delay: float) -> None:
        coordinator.cancel_command.set()

    monkeypatch.setattr("custom_components.adjustable_bed.beds.base.asyncio.sleep", stop)
    await controller.move_feet_down()
    assert _written(mock_bleak_client) == ["e5fe1608000000fe", ZERO]
    no_sleep.release_wait.assert_not_awaited()


@pytest.mark.parametrize(
    ("motors", "keys"),
    [
        (2, ["head", "feet", "back_legs"]),
        (3, ["head", "feet", "lumbar"]),
        (4, ["head", "feet", "waist", "lumbar"]),
    ],
)
async def test_motor_count_selects_the_app_layout(coordinator, motors, keys):
    controller = _innova(coordinator, motors)
    assert [spec.key for spec in controller.motor_control_specs] == keys
    assert {spec.scheduler_resource for spec in controller.motor_control_specs} == {"*"}


@pytest.mark.parametrize(
    ("motors", "control", "frame"),
    [
        (2, "memory_a", "e5fe1600200000e6"),
        (2, "memory_b", "e5fe1600400000c6"),
        (2, "memory_timer", "e5fe160002000004"),
        (2, "combined_up", "e5fe160500000001"),
        (3, "lumbar_down", "e5fe168000000086"),
        (4, "waist_up", "e5fe1610000000f6"),
        (4, "legs_down", "e5fe1608000000fe"),
    ],
)
async def test_hold_control_streams_for_the_duration(
    coordinator, mock_bleak_client: MagicMock, no_sleep, motors, control, frame
):
    controller = _innova(coordinator, motors)
    await controller.hold_control(control, 2050)
    assert _written(mock_bleak_client) == [frame] * 21 + [ZERO]


async def test_hold_control_rejects_other_screens_and_durations(coordinator):
    controller = _innova(coordinator, 2)
    assert "waist_up" not in controller.held_control_options
    assert set(controller.held_control_options) <= set(HELD_CONTROLS)
    with pytest.raises(ValueError):
        await controller.hold_control("waist_up", 1000)
    with pytest.raises(ValueError):
        await controller.hold_control("memory_a", 60001)


async def test_innova_capabilities(coordinator):
    controller = _innova(coordinator)
    assert controller.memory_slot_count == 2
    assert not controller.supports_memory_programming
    assert controller.supports_stop_all
    assert controller.auto_enable_massage
    assert not controller.supports_discrete_light_control
    assert not controller.supports_massage_intensity_control
    assert not controller.supports_massage_timer
    assert not controller.supports_massage_off_control
    assert not controller.supports_massage_toggle_control
    assert controller.supports_head_massage_intensity_step_control
    assert controller.supports_massage_mode_step_control and controller.massage_mode_step_is_timer
    assert not controller.supports_preset_anti_snore
    assert controller.supports_device_rename
    assert controller.requires_notification_channel
    assert controller.control_characteristic_uuid == KEESON_BASE_WRITE_CHAR_UUID
    assert [(s.key, s.translation_key) for s in controller.controller_button_specs] == [
        ("innova_massage_level", "innova_massage_level"),
        ("innova_massage_timer_hold", "innova_massage_timer_hold"),
    ]
    with pytest.raises(NotImplementedError):
        await controller.program_memory(1)
    with pytest.raises(NotImplementedError):
        await controller.lights_on()


def test_rename_frames_match_the_report():
    assert innova_rename_frame("A").hex() == "ef02410000000000000000000000000000cd"
    assert innova_rename_frame("BED").hex() == "ef0242454400000000000000000000000043"
    assert innova_rename_frame("  BED \t") == innova_rename_frame("BED")
    assert innova_rename_frame("N" * 14)[2:16] == b"N" * 14
    # The editor's maxLength applies before trimming, like the app.
    for bad in ("", "   ", "N" * 15, " " + "N" * 14):
        with pytest.raises(ValueError):
            innova_rename_frame(bad)
    # The app copies String.length() bytes of the UTF-8 encoding.
    frame = innova_rename_frame("Å")
    assert frame[2:4] == b"\xc3\x00"
    assert frame[17] == (~sum(frame[:17])) & 0xFF


async def test_rename_writes_once_on_ffe9(coordinator, mock_bleak_client: MagicMock, no_sleep):
    await _innova(coordinator).rename_device("BED")
    assert _written(mock_bleak_client) == ["ef0242454400000000000000000000000043"]
    no_sleep.assert_not_awaited()


def _status(length: int, flags: int, timer: int) -> bytes:
    data = bytearray(length)
    offset = 13 if length == 16 else 14
    data[offset], data[offset + 1] = flags, timer
    return bytes(data)


@pytest.mark.parametrize("length", [16, 19])
def test_parser_branches(length):
    # Report fixtures V-NOTIFY-16 / V-NOTIFY-19: lamp bit set, timer enum 1.
    assert parse_innova_status(_status(length, 0x40, 0x01)) == {
        STATE_LIGHT: True,
        STATE_MASSAGE_TIMER: 10,
    }
    assert parse_innova_status(_status(length, 0x00, 0xFF)) == {
        STATE_LIGHT: False,
        STATE_MASSAGE_TIMER: 0,
    }
    assert parse_innova_status(_status(length, 0x00, 0x03))[STATE_MASSAGE_TIMER] == 30
    assert parse_innova_status(_status(length, 0x40, 0x07)) == {STATE_LIGHT: True}
    assert parse_innova_status(_status(length, 0x60, 0x01)) is None
    assert parse_innova_status(_status(length, 0x9F, 0x02)) == {
        STATE_LIGHT: False,
        STATE_MASSAGE_TIMER: 20,
    }


@pytest.mark.parametrize("length", [0, 9, 15, 17, 18, 20])
def test_parser_ignores_other_lengths(length):
    assert parse_innova_status(bytes(length)) is None


async def test_notifications_publish_and_clear(coordinator, mock_bleak_client: MagicMock):
    controller = _innova(coordinator)
    await controller.start_notify(None)
    assert mock_bleak_client.start_notify.await_args.args[0].uuid == KEESON_BASE_NOTIFY_CHAR_UUID
    controller._on_notification(MagicMock(), bytearray(_status(16, 0x40, 0x02)))
    assert coordinator.controller_state[STATE_LIGHT] is True
    assert coordinator.controller_state[STATE_MASSAGE_TIMER] == 20
    controller._on_notification(MagicMock(), bytearray(_status(19, 0x20, 0x01)))
    assert coordinator.controller_state[STATE_MASSAGE_TIMER] == 20
    controller.invalidate_diagnostics()
    assert coordinator.controller_state[STATE_LIGHT] is None
    assert coordinator.controller_state[STATE_MASSAGE_TIMER] is None


async def test_failed_subscription_does_not_block_control(
    coordinator, mock_bleak_client: MagicMock, no_sleep
):
    mock_bleak_client.start_notify.side_effect = BleakError("no CCCD")
    controller = _innova(coordinator)
    await controller.start_notify(None)
    await controller.preset_flat()
    assert _written(mock_bleak_client) == ["e5fe1600000008fe"]


@pytest.mark.parametrize(
    ("properties", "response"),
    [(["write", "write-without-response"], False), (["write"], True)],
)
async def test_write_type_mirrors_android_default(
    coordinator, mock_bleak_client: MagicMock, no_sleep, properties, response
):
    mock_bleak_client.services = _services(
        (KEESON_BASE_WRITE_CHAR_UUID, properties), (KEESON_BASE_NOTIFY_CHAR_UUID, ["notify"])
    )
    await _innova(coordinator).preset_flat()
    assert mock_bleak_client.write_gatt_char.await_args.kwargs["response"] is response


async def test_both_roles_are_required_like_the_app(
    coordinator, mock_bleak_client: MagicMock, no_sleep
):
    mock_bleak_client.services = _services((KEESON_BASE_WRITE_CHAR_UUID, ["write"]))
    with pytest.raises(BleakError):
        await _innova(coordinator).preset_flat()
    mock_bleak_client.write_gatt_char.assert_not_awaited()


async def test_profiles_are_selected_only_explicitly(coordinator, mock_bleak_client: MagicMock):
    # Auto Keeson routing queries services with get_characteristic.
    services = MagicMock()
    services.__iter__ = lambda _self: iter([])
    services.get_characteristic.return_value = None
    mock_bleak_client.services = services
    auto = await create_controller(
        coordinator=coordinator,
        bed_type=BED_TYPE_KEESON,
        protocol_variant="auto",
        client=coordinator.client,
        device_name="ORE-ac2170000d",
    )
    assert type(auto) is KeesonController
    assert auto._variant == KEESON_VARIANT_BASE
    innova = await create_controller(
        coordinator=coordinator,
        bed_type=BED_TYPE_KEESON,
        protocol_variant=KEESON_VARIANT_INNOVA,
        client=coordinator.client,
        device_name="ORE-ac2170000d",
    )
    assert isinstance(innova, InnovaController)
    bedsense = await create_controller(
        coordinator=coordinator,
        bed_type=BED_TYPE_KEESON,
        protocol_variant=KEESON_VARIANT_BEDSENSE_BASES,
        client=coordinator.client,
        device_name="ORE-ac2170000d",
    )
    assert isinstance(bedsense, OreComfortBedController)
    assert bedsense.protocol_diagnostics["app_package"] == "com.ore.sfmc2bedsence 1.1 (3)"


def _entry(hass: HomeAssistant, address: str, variant: str, motors: int) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="ORE bed",
        data={
            CONF_ADDRESS: address,
            CONF_NAME: "ORE bed",
            CONF_BED_TYPE: BED_TYPE_KEESON,
            CONF_PROTOCOL_VARIANT: variant,
            CONF_MOTOR_COUNT: motors,
            CONF_HAS_MASSAGE: False,
            CONF_DISABLE_ANGLE_SENSING: True,
            CONF_PREFERRED_ADAPTER: "auto",
        },
        unique_id=address,
        entry_id=f"ore_{address.replace(':', '')}",
    )
    entry.add_to_hass(hass)
    return entry


async def _reload(hass: HomeAssistant, entry: MockConfigEntry, **changes: Any) -> None:
    hass.config_entries.async_update_entry(entry, data={**entry.data, **changes})
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()


async def test_setup_exposes_each_app_surface_and_cleans_up(
    hass: HomeAssistant,
    mock_coordinator_connected,
    mock_async_ble_device_from_address: MagicMock,
    mock_bleak_client: MagicMock,
    enable_custom_integrations,
):
    mock_bleak_client.services = _services(
        (KEESON_BASE_WRITE_CHAR_UUID, ["write"]), (KEESON_BASE_NOTIFY_CHAR_UUID, ["notify"])
    )
    address = "AA:BB:CC:DD:EE:60"
    entry = _entry(hass, address, KEESON_VARIANT_INNOVA, 2)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    registry = er.async_get(hass)

    def exists(platform: str, key: str) -> bool:
        return registry.async_get_entity_id(platform, DOMAIN, f"{address}_{key}") is not None

    for key in ("head", "feet", "back_legs"):
        assert exists("cover", key), key
    for key in (
        "innova_massage_level",
        "innova_massage_timer_hold",
        "toggle_light",
        "massage_head_up",
        "massage_foot_down",
        "massage_mode_step",
        "preset_memory_1",
        "preset_memory_2",
        "stop",
    ):
        assert exists("button", key), key
    for key in ("program_memory_1", "massage_all_off", "massage_all_toggle", "preset_anti_snore"):
        assert not exists("button", key), key
    assert exists("binary_sensor", STATE_LIGHT)
    assert exists("sensor", STATE_MASSAGE_TIMER)

    await _reload(
        hass,
        entry,
        **{CONF_PROTOCOL_VARIANT: KEESON_VARIANT_BEDSENSE_BASES, CONF_MOTOR_COUNT: 4},
    )
    for key in ("back", "feet", "waist", "lumbar"):
        assert exists("cover", key), key
    assert not exists("cover", "back_legs")
    assert not exists("button", "innova_massage_level")
    assert exists("button", "ore_comfort_massage_start")
    assert exists("select", "controller_select_ore_comfort_massage_timer")
    assert exists("number", "controller_number_ore_comfort_massage_wave")
    assert exists("switch", "under_bed_lights")
    assert not exists("binary_sensor", STATE_LIGHT)
    assert not exists("sensor", STATE_MASSAGE_TIMER)

    await _reload(
        hass,
        entry,
        **{CONF_PROTOCOL_VARIANT: KEESON_VARIANT_INNOVA, CONF_MOTOR_COUNT: 2},
    )
    await _reload(hass, entry, **{CONF_PROTOCOL_VARIANT: KEESON_VARIANT_ADJUSTABLE_LITE})
    assert not exists("cover", "back_legs")
    assert not exists("button", "innova_massage_level")
    assert not exists("binary_sensor", STATE_LIGHT)
    assert not exists("sensor", STATE_MASSAGE_TIMER)

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


async def _setup_innova(hass: HomeAssistant, client: MagicMock, address: str) -> tuple[Any, Any]:
    client.services = _services(
        (KEESON_BASE_WRITE_CHAR_UUID, ["write"]), (KEESON_BASE_NOTIFY_CHAR_UUID, ["notify"])
    )
    entry = _entry(hass, address, KEESON_VARIANT_INNOVA, 2)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    (device,) = dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)
    return entry, device


async def test_innova_rename_service(
    hass: HomeAssistant,
    mock_coordinator_connected,
    mock_async_ble_device_from_address: MagicMock,
    mock_bleak_client: MagicMock,
    enable_custom_integrations,
):
    entry, device = await _setup_innova(hass, mock_bleak_client, "AA:BB:CC:DD:EE:61")
    mock_bleak_client.write_gatt_char.reset_mock()
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN, "rename", {"device_id": [device.id], "name": "N" * 15}, blocking=True
        )
    mock_bleak_client.write_gatt_char.assert_not_awaited()
    await hass.services.async_call(
        DOMAIN, "rename", {"device_id": [device.id], "name": " BED "}, blocking=True
    )
    assert _written(mock_bleak_client)[-1] == "ef0242454400000000000000000000000043"

    await _reload(hass, entry, **{CONF_PROTOCOL_VARIANT: KEESON_VARIANT_BEDSENSE_BASES})
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN, "rename", {"device_id": [device.id], "name": "BED"}, blocking=True
        )
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


async def test_innova_hold_control_service(
    hass: HomeAssistant,
    mock_coordinator_connected,
    mock_async_ble_device_from_address: MagicMock,
    mock_bleak_client: MagicMock,
    enable_custom_integrations,
    no_sleep,
):
    entry, device = await _setup_innova(hass, mock_bleak_client, "AA:BB:CC:DD:EE:62")
    mock_bleak_client.write_gatt_char.reset_mock()
    for data in (
        {"control": "waist_up", "duration": 1},  # 4M only
        {"control": "memory_a", "duration": 61},
        {"control": "head_up", "duration": 1},
    ):
        with pytest.raises((ServiceValidationError, vol.Invalid)):
            await hass.services.async_call(
                DOMAIN, "hold_control", {"device_id": [device.id], **data}, blocking=True
            )
    mock_bleak_client.write_gatt_char.assert_not_awaited()

    await hass.services.async_call(
        DOMAIN,
        "hold_control",
        {"device_id": [device.id], "control": "memory_a", "duration": 0.5},
        blocking=True,
    )
    assert _written(mock_bleak_client) == ["e5fe1600200000e6"] * 5 + [ZERO]

    # A Restonic entry is a Keeson bed too, but not the INNOVA profile.
    await _reload(hass, entry, **{CONF_PROTOCOL_VARIANT: KEESON_VARIANT_RESTONIC_B})
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            "hold_control",
            {"device_id": [device.id], "control": "legs_up", "duration": 1},
            blocking=True,
        )
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


async def test_a_failed_release_is_not_hidden_by_a_cancellation(
    coordinator, mock_bleak_client: MagicMock, no_sleep
):
    """Like an exception in a finally block, the release write error wins."""
    controller = _innova(coordinator)
    started, finish = asyncio.Event(), asyncio.Event()

    async def failing_write(_char, data, response=True):
        if bytes(data).hex() == ZERO:
            started.set()
            await finish.wait()
            raise BleakError("release write failed")

    mock_bleak_client.write_gatt_char.side_effect = failing_write
    task = asyncio.create_task(controller.stop_all())
    await started.wait()
    task.cancel()
    await _yield()
    finish.set()
    with pytest.raises(BleakError, match="release write failed") as raised:
        await task
    assert isinstance(raised.value.__cause__, asyncio.CancelledError)


def test_controller_is_exported_from_the_beds_package():
    from custom_components.adjustable_bed import beds

    assert "InnovaController" in beds.__all__
    assert beds.InnovaController is InnovaController


def _pair_side(address: str, variant: str) -> dict[str, object]:
    return {
        CONF_ADDRESS: address,
        CONF_NAME: address,
        CONF_BED_TYPE: BED_TYPE_KEESON,
        CONF_PROTOCOL_VARIANT: variant,
        CONF_MOTOR_COUNT: 2,
        CONF_DISABLE_ANGLE_SENSING: True,
    }


@pytest.mark.parametrize(
    ("left", "right", "requested"),
    [
        (KEESON_VARIANT_BASE, KEESON_VARIANT_BASE, KEESON_VARIANT_INNOVA),
        (KEESON_VARIANT_INNOVA, KEESON_VARIANT_BASE, KEESON_VARIANT_BASE),
    ],
    ids=["switch_to_innova", "switch_away_from_innova"],
)
async def test_two_address_pair_refuses_a_shared_innova_change(
    hass: HomeAssistant, left, right, requested
):
    """INNOVA is per receiver: the shared options form must not copy it to both sides."""
    from homeassistant.data_entry_flow import FlowResultType

    from custom_components.adjustable_bed.config_flow import AdjustableBedOptionsFlow
    from custom_components.adjustable_bed.pairing import (
        build_pair_entry_data,
        effective_child_data,
    )

    entry = MockConfigEntry(
        domain=DOMAIN,
        data=build_pair_entry_data(
            _pair_side("AA:BB:CC:DD:EE:71", left),
            _pair_side("AA:BB:CC:DD:EE:72", right),
            name="Pair",
        ),
    )
    entry.add_to_hass(hass)
    flow = AdjustableBedOptionsFlow(entry)
    flow.hass = hass
    flow.handler = entry.entry_id
    refused = await flow.async_step_settings({CONF_PROTOCOL_VARIANT: requested})
    assert refused["type"] is FlowResultType.FORM
    assert refused["errors"] == {CONF_PROTOCOL_VARIANT: "app_profile_unpair_first"}
    assert effective_child_data(entry.data, "left")[CONF_PROTOCOL_VARIANT] == left
    assert effective_child_data(entry.data, "right")[CONF_PROTOCOL_VARIANT] == right


@pytest.mark.parametrize("variant", sorted(OFFLINE_CAPABILITY_SAFE_VARIANTS[BED_TYPE_KEESON]))
async def test_offline_safe_variants_build_without_a_client(coordinator, variant):
    """Every allowed explicit variant mints its real controller client-free."""
    controller = await create_controller(
        coordinator=coordinator,
        bed_type=BED_TYPE_KEESON,
        protocol_variant=variant,
        client=None,
        device_name="ORE bed",
    )
    from custom_components.adjustable_bed.beds.keeson_okin_apps import OkinAppKeesonController

    assert isinstance(
        controller, (InnovaController, OreComfortBedController, OkinAppKeesonController)
    )
    assert controller.motor_control_specs


def test_keeson_auto_is_not_offline_safe():
    from custom_components.adjustable_bed.const import OFFLINE_CAPABILITY_SAFE_BED_TYPES

    assert BED_TYPE_KEESON not in OFFLINE_CAPABILITY_SAFE_BED_TYPES
    assert not {"auto", KEESON_VARIANT_BASE} & OFFLINE_CAPABILITY_SAFE_VARIANTS[BED_TYPE_KEESON]


LEFT_ADDRESS, RIGHT_ADDRESS = "AA:BB:CC:DD:EE:81", "AA:BB:CC:DD:EE:82"


@pytest.mark.parametrize(
    ("variant", "controller_key", "controller_type"),
    [
        (KEESON_VARIANT_INNOVA, "innova_massage_level", InnovaController),
        (KEESON_VARIANT_BEDSENSE_BASES, "ore_comfort_massage_start", OreComfortBedController),
        ("maxcoil_una", "ore_comfort_massage_start", OreComfortBedController),
    ],
)
async def test_pair_reload_with_one_side_offline_keeps_both_sides(
    hass: HomeAssistant,
    mock_coordinator_connected,
    mock_async_ble_device_from_address: MagicMock,
    mock_bleak_client: MagicMock,
    enable_custom_integrations,
    variant,
    controller_key,
    controller_type,
):
    """An unreachable receiver no longer blocks the reachable side of a pair."""
    from unittest.mock import patch

    from homeassistant.config_entries import ConfigEntryState

    from custom_components.adjustable_bed.const import SIDE_RIGHT
    from custom_components.adjustable_bed.pairing import build_pair_entry_data

    mock_bleak_client.services = _services(
        (KEESON_BASE_WRITE_CHAR_UUID, ["write"]), (KEESON_BASE_NOTIFY_CHAR_UUID, ["notify"])
    )
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Pair",
        data=build_pair_entry_data(
            _pair_side(LEFT_ADDRESS, variant), _pair_side(RIGHT_ADDRESS, variant), name="Pair"
        ),
        version=4,
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    registry = er.async_get(hass)
    right_action = registry.async_get_entity_id(
        "button", DOMAIN, f"{RIGHT_ADDRESS}_{controller_key}"
    )
    assert right_action is not None

    original = AdjustableBedCoordinator.async_connect

    async def right_unreachable(self: AdjustableBedCoordinator, *args: Any, **kwargs: Any) -> bool:
        if self.address == RIGHT_ADDRESS:
            return False
        return await original(self, *args, **kwargs)

    with patch.object(AdjustableBedCoordinator, "async_connect", right_unreachable):
        assert await hass.config_entries.async_reload(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    right = hass.data[DOMAIN][entry.entry_id].children[SIDE_RIGHT]
    assert not right.is_connected
    assert isinstance(right.capability_controller, controller_type)
    assert registry.async_get_entity_id("button", DOMAIN, f"{RIGHT_ADDRESS}_{controller_key}")
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


async def test_disconnect_keeps_app_state_and_clears_reported_state(
    hass: HomeAssistant,
    mock_coordinator_connected,
    mock_async_ble_device_from_address: MagicMock,
    mock_bleak_client: MagicMock,
    enable_custom_integrations,
    no_sleep,
):
    """Bedsense levels/timer survive a disconnect; INNOVA's bed reports become unknown."""
    mock_bleak_client.services = _services(
        (KEESON_BASE_WRITE_CHAR_UUID, ["write"]), (KEESON_BASE_NOTIFY_CHAR_UUID, ["notify"])
    )
    registry = er.async_get(hass)

    bedsense = _entry(hass, "AA:BB:CC:DD:EE:91", KEESON_VARIANT_BEDSENSE_BASES, 2)
    assert await hass.config_entries.async_setup(bedsense.entry_id)
    await hass.async_block_till_done()
    coordinator = hass.data[DOMAIN][bedsense.entry_id]
    number = registry.async_get_entity_id(
        "number", DOMAIN, "AA:BB:CC:DD:EE:91_controller_number_ore_comfort_massage_head"
    )
    select = registry.async_get_entity_id(
        "select", DOMAIN, "AA:BB:CC:DD:EE:91_controller_select_ore_comfort_massage_timer"
    )
    await hass.services.async_call(
        "number", "set_value", {"entity_id": number, "value": 3}, blocking=True
    )
    await hass.services.async_call(
        "select", "select_option", {"entity_id": select, "option": "20"}, blocking=True
    )
    await coordinator.async_disconnect()
    await hass.async_block_till_done()
    assert coordinator.controller is None
    assert float(hass.states.get(number).state) == 3
    assert hass.states.get(select).state == "20"

    innova = _entry(hass, "AA:BB:CC:DD:EE:92", KEESON_VARIANT_INNOVA, 2)
    assert await hass.config_entries.async_setup(innova.entry_id)
    await hass.async_block_till_done()
    innova_coordinator = hass.data[DOMAIN][innova.entry_id]
    innova_coordinator.controller._on_notification(MagicMock(), bytearray(_status(16, 0x40, 0x02)))
    await hass.async_block_till_done()
    light = registry.async_get_entity_id(
        "binary_sensor", DOMAIN, f"AA:BB:CC:DD:EE:92_{STATE_LIGHT}"
    )
    timer = registry.async_get_entity_id(
        "sensor", DOMAIN, f"AA:BB:CC:DD:EE:92_{STATE_MASSAGE_TIMER}"
    )
    assert hass.states.get(light).state == "on"
    assert hass.states.get(timer).state == "20"
    await innova_coordinator.async_disconnect()
    await hass.async_block_till_done()
    # The bed or its remote can change these while disconnected: unknown, not a default.
    assert hass.states.get(light).state == "unknown"
    assert hass.states.get(timer).state == "unknown"

    for entry in (bedsense, innova):
        assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
