"""Bedsense Bases and INNOVA (ORE SFM) app profiles, row059.

Every frame literal comes from the accepted clean-room reports for
com.ore.sfmc2bedsence 1.1 (3) and com.ore.sfm 2.0 (3); the notification
inputs are their synthetic parser fixtures, not captured traffic.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, call

import pytest
from bleak.exc import BleakError
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed.beds.keeson import KeesonController
from custom_components.adjustable_bed.beds.keeson_ore_sfm import (
    STATE_INNOVA_LIGHT,
    STATE_INNOVA_MASSAGE_TIMER,
    OreSfmKeesonController,
    innova_rename_frame,
    ore_sfm_frame,
    parse_innova_status,
)
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
)
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator

Action = Callable[[OreSfmKeesonController], Awaitable[None]]
ZERO = "e5fe160000000006"
HOLD = 10  # The app refreshes every 100 ms; the default burst is 10 x 100 ms.

# Bedsense Bases (big-endian keys): (action, motor count, report frame, held?)
BEDSENSE_VECTORS: list[tuple[Action, int, str, bool]] = [
    (lambda c: c.move_head_up(), 2, "e5fe160000000105", True),
    (lambda c: c.move_head_down(), 2, "e5fe160000000204", True),
    (lambda c: c.move_feet_up(), 2, "e5fe160000000402", True),
    (lambda c: c.move_feet_down(), 2, "e5fe1600000008fe", True),
    (lambda c: c.move_union_up(), 2, "e5fe1600000010f6", True),
    (lambda c: c.move_union_down(), 2, "e5fe1600000020e6", True),
    (lambda c: c.move_tilt_up(), 3, "e5fe1600000010f6", True),  # 3M head
    (lambda c: c.move_tilt_down(), 3, "e5fe1600000020e6", True),
    (lambda c: c.move_tilt_up(), 4, "e5fe1600000010f6", True),  # 4M waist
    (lambda c: c.move_tilt_down(), 4, "e5fe1600000020e6", True),
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
    (lambda c: c.set_massage_timer(10), 2, "e5fe1610000030c6", False),
    (lambda c: c.set_massage_timer(20), 2, "e5fe1610000031c5", False),
    (lambda c: c.set_massage_timer(30), 2, "e5fe1610000032c4", False),
    (lambda c: c.lights_on(), 2, "e5fe1631000001d4", False),
    (lambda c: c.lights_off(), 2, "e5fe1631000000d5", False),
]
BEDSENSE_MASSAGE = {
    "wave": ("e5fe1610000020d6", "e5fe1610000021d5", "e5fe1610000022d4", "e5fe1610000023d3"),
    "head": ("e5fe1610000010e6", "e5fe1610000011e5", "e5fe1610000012e4", "e5fe1610000013e3"),
    "foot": ("e5fe1611000010e5", "e5fe1611000011e4", "e5fe1611000012e3", "e5fe1611000013e2"),
}

# INNOVA (little-endian keys): (action, motor count, report row, frame, held?)
INNOVA_VECTORS: list[tuple[Action, int, str, str, bool]] = [
    (lambda c: c.move_head_up(), 2, "C17", "e5fe160100000005", True),
    (lambda c: c.move_feet_up(), 2, "C18", "e5fe160400000002", True),
    (lambda c: c.move_head_down(), 2, "C19", "e5fe160200000004", True),
    (lambda c: c.move_feet_down(), 2, "C20", "e5fe1608000000fe", True),
    (lambda c: c.move_union_up(), 2, "C21", "e5fe160500000001", True),
    (lambda c: c.move_union_down(), 2, "C22", "e5fe160a000000fc", True),
    (lambda c: c.move_lumbar_up(), 3, "C27", "e5fe1640000000c6", True),
    (lambda c: c.move_lumbar_down(), 3, "C28", "e5fe168000000086", True),
    (lambda c: c.move_lumbar_up(), 4, "C29", "e5fe1640000000c6", True),
    (lambda c: c.move_lumbar_down(), 4, "C30", "e5fe168000000086", True),
    (lambda c: c.move_tilt_up(), 4, "C31", "e5fe1610000000f6", True),
    (lambda c: c.move_tilt_down(), 4, "C32", "e5fe1620000000e6", True),
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
    (lambda c: c.stop_all(), 2, "C33", ZERO, False),
]


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
    hass: HomeAssistant, entry: MockConfigEntry, mock_coordinator_connected
) -> AdjustableBedCoordinator:
    coordinator = AdjustableBedCoordinator(hass, entry)
    await coordinator.async_connect()
    return coordinator


@pytest.fixture
def no_sleep(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    sleep = AsyncMock()
    monkeypatch.setattr("custom_components.adjustable_bed.beds.base.asyncio.sleep", sleep)
    return sleep


def _ctrl(
    coordinator: AdjustableBedCoordinator, variant: str, motors: int = 2
) -> OreSfmKeesonController:
    coordinator._motor_count = motors
    return OreSfmKeesonController(coordinator, variant=variant)


def _written(client: MagicMock) -> list[str]:
    return [c.args[1].hex() for c in client.write_gatt_char.await_args_list]


def _services(*chars: tuple[str, list[str]]) -> list[SimpleNamespace]:
    return [
        SimpleNamespace(
            uuid="0000ffe5-0000-1000-8000-00805f9b34fb",
            characteristics=[SimpleNamespace(uuid=uuid, properties=props) for uuid, props in chars],
        )
    ]


def test_builders_match_the_report_byte_order():
    """The asymmetric key proves each app's byte order; the checksum is shared."""
    assert ore_sfm_frame(0x12345678, big_endian=True).hex() == "e5fe1612345678f2"
    assert ore_sfm_frame(0x12345678, big_endian=False).hex() == "e5fe1678563412f2"
    assert ore_sfm_frame(1, big_endian=True).hex() == "e5fe160000000105"
    assert ore_sfm_frame(1, big_endian=False).hex() == "e5fe160100000005"
    for big_endian in (True, False):
        assert sum(ore_sfm_frame(0x80, big_endian=big_endian)) % 256 == 0xFF


@pytest.mark.parametrize(("action", "motors", "frame", "held"), BEDSENSE_VECTORS)
async def test_bedsense_controls_send_the_artifact_frames(
    coordinator, mock_bleak_client: MagicMock, no_sleep, action, motors, frame, held
):
    controller = _ctrl(coordinator, KEESON_VARIANT_BEDSENSE_BASES, motors)
    await action(controller)
    expected = [frame] * HOLD + [ZERO] if held else [frame]
    assert _written(mock_bleak_client) == expected


@pytest.mark.parametrize(("action", "motors", "row", "frame", "held"), INNOVA_VECTORS)
async def test_innova_controls_send_the_artifact_frames(
    coordinator, mock_bleak_client: MagicMock, no_sleep, action, motors, row, frame, held
):
    controller = _ctrl(coordinator, KEESON_VARIANT_INNOVA, motors)
    await action(controller)
    expected = [frame] * HOLD + [ZERO] if held else [frame]
    assert _written(mock_bleak_client) == expected, row


async def test_bedsense_massage_buckets_start_and_stop(
    coordinator, mock_bleak_client: MagicMock, no_sleep
):
    controller = _ctrl(coordinator, KEESON_VARIANT_BEDSENSE_BASES)
    # Start with the app's default slider progress 10 (bucket 1).
    await controller.massage_start()
    assert _written(mock_bleak_client) == [
        "e5fe1610000021d5",
        "e5fe1610000011e5",
        "e5fe1611000011e4",
    ]
    for zone, frames in BEDSENSE_MASSAGE.items():
        for level, frame in enumerate(frames):
            mock_bleak_client.write_gatt_char.reset_mock()
            await controller.set_massage_intensity(zone, level)
            assert _written(mock_bleak_client) == [frame]
    assert controller.get_massage_state()["head_intensity"] == 3
    await controller.set_massage_timer(20)
    assert controller.get_massage_state()["timer_mode"] == "20"
    mock_bleak_client.write_gatt_char.reset_mock()
    await controller.massage_off()
    assert _written(mock_bleak_client) == ["e5fe1610000010e6", "e5fe1611000010e5"]
    assert controller.get_massage_state()["timer_mode"] is None
    with pytest.raises(ValueError):
        await controller.set_massage_intensity("head", 4)
    with pytest.raises(ValueError):
        await controller.set_massage_timer(0)


async def test_bedsense_light_toggle_follows_local_state(
    coordinator, mock_bleak_client: MagicMock, no_sleep
):
    controller = _ctrl(coordinator, KEESON_VARIANT_BEDSENSE_BASES)
    await controller.lights_toggle()
    await controller.lights_toggle()
    assert _written(mock_bleak_client) == ["e5fe1631000001d4", "e5fe1631000000d5"]


async def test_hold_timing_and_single_send_delay(
    coordinator, mock_bleak_client: MagicMock, no_sleep
):
    """Holds refresh every 100 ms; singles and the release sleep 100 ms first."""
    controller = _ctrl(coordinator, KEESON_VARIANT_INNOVA)
    assert controller.motor_pulse_settings() == (10, 100)
    await controller.move_head_up()
    assert no_sleep.await_args_list == [call(0.1)] * (HOLD - 1) + [call(0.1)]
    no_sleep.reset_mock()
    await controller.preset_zero_g()
    assert no_sleep.await_args_list == [call(0.1)]


async def test_release_survives_a_stop_request(
    coordinator, mock_bleak_client: MagicMock, monkeypatch: pytest.MonkeyPatch
):
    """A stop ends the refresh, and the zero key still goes out on a fresh event."""
    controller = _ctrl(coordinator, KEESON_VARIANT_BEDSENSE_BASES)

    async def cancel(_delay: float) -> None:
        coordinator.cancel_command.set()

    monkeypatch.setattr("custom_components.adjustable_bed.beds.base.asyncio.sleep", cancel)
    await controller.move_feet_down()
    assert _written(mock_bleak_client) == ["e5fe1600000008fe", ZERO]


@pytest.mark.parametrize(
    ("variant", "motors", "keys"),
    [
        (KEESON_VARIANT_BEDSENSE_BASES, 2, ["head", "feet", "back_legs"]),
        (KEESON_VARIANT_BEDSENSE_BASES, 3, ["head", "feet", "tilt"]),
        (KEESON_VARIANT_BEDSENSE_BASES, 4, ["head", "feet", "waist", "lumbar"]),
        (KEESON_VARIANT_INNOVA, 2, ["head", "feet", "back_legs"]),
        (KEESON_VARIANT_INNOVA, 3, ["head", "feet", "lumbar"]),
        (KEESON_VARIANT_INNOVA, 4, ["head", "feet", "waist", "lumbar"]),
    ],
)
async def test_motor_count_selects_the_app_layout(coordinator, variant, motors, keys):
    controller = _ctrl(coordinator, variant, motors)
    assert [spec.key for spec in controller.motor_control_specs] == keys


async def test_waist_cover_drives_the_waist_key(
    coordinator, mock_bleak_client: MagicMock, no_sleep
):
    controller = _ctrl(coordinator, KEESON_VARIANT_BEDSENSE_BASES, 4)
    waist = next(spec for spec in controller.motor_control_specs if spec.key == "waist")
    await waist.open_fn(controller)
    assert _written(mock_bleak_client) == ["e5fe1600000010f6"] * HOLD + [ZERO]


async def test_capabilities_are_gated_per_app(coordinator):
    bedsense = _ctrl(coordinator, KEESON_VARIANT_BEDSENSE_BASES)
    innova = _ctrl(coordinator, KEESON_VARIANT_INNOVA)
    for controller in (bedsense, innova):
        assert controller.memory_slot_count == 2
        assert controller.supports_stop_all
        assert controller.auto_enable_massage
        assert not controller.supports_preset_anti_snore
        assert not controller.supports_preset_lounge
        assert not controller.supports_preset_tv
        assert not controller.supports_massage_toggle_control
        assert not controller.supports_massage_intensity_step_control
        assert controller.control_characteristic_uuid == KEESON_BASE_WRITE_CHAR_UUID
    assert bedsense.supports_memory_programming
    assert bedsense.supports_discrete_light_control
    assert bedsense.supports_massage_intensity_control
    assert bedsense.massage_intensity_zones == ["head", "foot", "wave"]
    assert bedsense.massage_intensity_max == 3
    assert bedsense.massage_timer_options == [10, 20, 30]
    assert bedsense.supports_massage_off_control
    assert not bedsense.supports_head_massage_intensity_step_control
    assert not bedsense.supports_device_rename
    assert not bedsense.requires_notification_channel
    assert [spec.key for spec in bedsense.controller_button_specs] == [
        "ore_sfm_program_zero_g",
        "ore_sfm_program_flat",
        "ore_sfm_massage_start",
    ]

    assert not innova.supports_memory_programming
    assert not innova.supports_discrete_light_control
    assert not innova.supports_massage_intensity_control
    assert not innova.supports_massage_timer
    assert not innova.supports_massage_off_control
    assert innova.supports_head_massage_intensity_step_control
    assert innova.supports_foot_massage_intensity_step_control
    assert innova.supports_massage_mode_step_control and innova.massage_mode_step_is_timer
    assert innova.supports_device_rename
    assert innova.requires_notification_channel
    assert [spec.key for spec in innova.controller_button_specs] == [
        "ore_sfm_massage_level",
        "ore_sfm_massage_timer_hold",
    ]
    with pytest.raises(NotImplementedError):
        await innova.program_memory(1)
    with pytest.raises(NotImplementedError):
        await innova.lights_on()
    with pytest.raises(ValueError):
        await bedsense.preset_memory(3)


def test_rename_frames_match_the_report():
    assert innova_rename_frame("A").hex() == "ef02410000000000000000000000000000cd"
    assert innova_rename_frame("BED").hex() == "ef0242454400000000000000000000000043"
    # String.trim() and the 14 UTF-16 unit editor limit.
    assert innova_rename_frame("  BED \t") == innova_rename_frame("BED")
    assert innova_rename_frame("N" * 14)[2:16] == b"N" * 14
    for bad in ("", "   ", "N" * 15):
        with pytest.raises(ValueError):
            innova_rename_frame(bad)
    # The app copies String.length() bytes of the UTF-8 encoding.
    frame = innova_rename_frame("Å")
    assert frame[2:4] == b"\xc3\x00"
    assert frame[17] == (~sum(frame[:17])) & 0xFF


async def test_rename_writes_once_on_ffe9(coordinator, mock_bleak_client: MagicMock, no_sleep):
    controller = _ctrl(coordinator, KEESON_VARIANT_INNOVA)
    await controller.rename_device("BED")
    assert _written(mock_bleak_client) == ["ef0242454400000000000000000000000043"]
    no_sleep.assert_not_awaited()
    with pytest.raises(ValueError):
        _ctrl(coordinator, KEESON_VARIANT_BEDSENSE_BASES).validate_device_rename("BED")


def _status(length: int, flags: int, timer: int) -> bytes:
    data = bytearray(length)
    offset = 13 if length == 16 else 14
    data[offset], data[offset + 1] = flags, timer
    return bytes(data)


@pytest.mark.parametrize("length", [16, 19])
def test_innova_parser_branches(length):
    # Report fixtures V-NOTIFY-16 / V-NOTIFY-19: lamp bit set, timer enum 1.
    assert parse_innova_status(_status(length, 0x40, 0x01)) == {
        STATE_INNOVA_LIGHT: True,
        STATE_INNOVA_MASSAGE_TIMER: 10,
    }
    assert parse_innova_status(_status(length, 0x00, 0xFF)) == {
        STATE_INNOVA_LIGHT: False,
        STATE_INNOVA_MASSAGE_TIMER: 0,
    }
    assert parse_innova_status(_status(length, 0x00, 0x03))[STATE_INNOVA_MASSAGE_TIMER] == 30
    # Other timer values leave the indicator unchanged.
    assert parse_innova_status(_status(length, 0x40, 0x07)) == {STATE_INNOVA_LIGHT: True}
    # Bit 5 suppresses the whole update; other flag bits are ignored.
    assert parse_innova_status(_status(length, 0x60, 0x01)) is None
    assert parse_innova_status(_status(length, 0x9F, 0x02)) == {
        STATE_INNOVA_LIGHT: False,
        STATE_INNOVA_MASSAGE_TIMER: 20,
    }


@pytest.mark.parametrize("length", [0, 9, 15, 17, 18, 20])
def test_innova_parser_ignores_other_lengths(length):
    assert parse_innova_status(bytes(length)) is None


async def test_innova_notifications_publish_and_clear(coordinator, mock_bleak_client: MagicMock):
    controller = _ctrl(coordinator, KEESON_VARIANT_INNOVA)
    await controller.start_notify(None)
    mock_bleak_client.start_notify.assert_awaited_once()
    assert mock_bleak_client.start_notify.await_args.args[0] == KEESON_BASE_NOTIFY_CHAR_UUID
    controller._on_notification(MagicMock(), bytearray(_status(16, 0x40, 0x02)))
    assert coordinator.controller_state[STATE_INNOVA_LIGHT] is True
    assert coordinator.controller_state[STATE_INNOVA_MASSAGE_TIMER] == 20
    controller._on_notification(MagicMock(), bytearray(_status(19, 0x20, 0x01)))
    assert coordinator.controller_state[STATE_INNOVA_MASSAGE_TIMER] == 20
    controller.invalidate_diagnostics()
    assert coordinator.controller_state[STATE_INNOVA_LIGHT] is None
    assert coordinator.controller_state[STATE_INNOVA_MASSAGE_TIMER] is None


async def test_bedsense_never_subscribes(coordinator, mock_bleak_client: MagicMock):
    """Bedsense discards every reply, so no notification state exists."""
    controller = _ctrl(coordinator, KEESON_VARIANT_BEDSENSE_BASES)
    await controller.start_notify(None)
    mock_bleak_client.start_notify.assert_not_awaited()
    assert controller.controller_state_binary_sensor_specs == ()
    assert controller.controller_state_sensor_specs == ()


async def test_failed_subscription_does_not_block_control(
    coordinator, mock_bleak_client: MagicMock, no_sleep
):
    mock_bleak_client.start_notify.side_effect = BleakError("no CCCD")
    controller = _ctrl(coordinator, KEESON_VARIANT_INNOVA)
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
    controller = _ctrl(coordinator, KEESON_VARIANT_BEDSENSE_BASES)
    await controller.preset_flat()
    assert mock_bleak_client.write_gatt_char.await_args.kwargs["response"] is response


async def test_both_roles_are_required_like_the_app(
    coordinator, mock_bleak_client: MagicMock, no_sleep
):
    mock_bleak_client.services = _services((KEESON_BASE_WRITE_CHAR_UUID, ["write"]))
    controller = _ctrl(coordinator, KEESON_VARIANT_INNOVA)
    with pytest.raises(BleakError):
        await controller.preset_flat()
    mock_bleak_client.write_gatt_char.assert_not_awaited()


async def test_profiles_are_selected_only_explicitly(coordinator):
    auto = await create_controller(
        coordinator=coordinator,
        bed_type=BED_TYPE_KEESON,
        protocol_variant="auto",
        client=coordinator.client,
        device_name="ORE-ac2170000d",
    )
    assert type(auto) is KeesonController
    assert auto._variant == KEESON_VARIANT_BASE
    for variant in (KEESON_VARIANT_BEDSENSE_BASES, KEESON_VARIANT_INNOVA):
        explicit = await create_controller(
            coordinator=coordinator,
            bed_type=BED_TYPE_KEESON,
            protocol_variant=variant,
            client=coordinator.client,
            device_name="ORE-ac2170000d",
        )
        assert isinstance(explicit, OreSfmKeesonController)
        assert explicit._variant == variant


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
    enable_custom_integrations,
):
    address = "AA:BB:CC:DD:EE:60"
    entry = _entry(hass, address, KEESON_VARIANT_BEDSENSE_BASES, 4)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    registry = er.async_get(hass)

    def exists(platform: str, key: str) -> bool:
        return registry.async_get_entity_id(platform, DOMAIN, f"{address}_{key}") is not None

    for key in ("head", "feet", "waist", "lumbar"):
        assert exists("cover", key), key
    for key in (
        "preset_flat",
        "preset_zero_g",
        "preset_memory_1",
        "preset_memory_2",
        "program_memory_1",
        "program_memory_2",
        "stop",
        "massage_all_off",
        "ore_sfm_program_zero_g",
        "ore_sfm_program_flat",
        "ore_sfm_massage_start",
    ):
        assert exists("button", key), key
    for key in ("preset_memory_3", "preset_anti_snore", "massage_all_toggle", "toggle_light"):
        assert not exists("button", key), key
    for key in ("massage_head_intensity", "massage_foot_intensity", "massage_wave_intensity"):
        assert exists("number", key), key
    assert exists("select", "massage_timer")

    await _reload(
        hass, entry, **{CONF_PROTOCOL_VARIANT: KEESON_VARIANT_INNOVA, CONF_MOTOR_COUNT: 2}
    )
    assert exists("cover", "back_legs")
    assert not exists("cover", "waist")
    assert not exists("button", "ore_sfm_program_zero_g")
    for key in (
        "ore_sfm_massage_level",
        "ore_sfm_massage_timer_hold",
        "toggle_light",
        "massage_head_up",
        "massage_foot_down",
        "massage_mode_step",
    ):
        assert exists("button", key), key
    assert not exists("button", "program_memory_1")
    assert not exists("select", "massage_timer")
    assert exists("binary_sensor", STATE_INNOVA_LIGHT)
    assert exists("sensor", STATE_INNOVA_MASSAGE_TIMER)

    await _reload(hass, entry, **{CONF_PROTOCOL_VARIANT: KEESON_VARIANT_ADJUSTABLE_LITE})
    assert not exists("cover", "back_legs")
    assert not exists("button", "ore_sfm_massage_level")
    assert not exists("binary_sensor", STATE_INNOVA_LIGHT)
    assert not exists("sensor", STATE_INNOVA_MASSAGE_TIMER)

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


async def test_innova_rename_service(
    hass: HomeAssistant,
    mock_coordinator_connected,
    mock_async_ble_device_from_address: MagicMock,
    mock_bleak_client: MagicMock,
    enable_custom_integrations,
):
    from homeassistant.helpers import device_registry as dr

    address = "AA:BB:CC:DD:EE:61"
    entry = _entry(hass, address, KEESON_VARIANT_INNOVA, 2)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    (device,) = dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)

    mock_bleak_client.write_gatt_char.reset_mock()
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN, "innova_rename", {"device_id": [device.id], "name": "N" * 15}, blocking=True
        )
    mock_bleak_client.write_gatt_char.assert_not_awaited()

    await hass.services.async_call(
        DOMAIN, "innova_rename", {"device_id": [device.id], "name": " BED "}, blocking=True
    )
    await asyncio.sleep(0)
    assert _written(mock_bleak_client)[-1] == "ef0242454400000000000000000000000043"

    await _reload(hass, entry, **{CONF_PROTOCOL_VARIANT: KEESON_VARIANT_BEDSENSE_BASES})
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN, "innova_rename", {"device_id": [device.id], "name": "BED"}, blocking=True
        )
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
