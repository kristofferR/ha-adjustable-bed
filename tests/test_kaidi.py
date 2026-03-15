"""Tests for the Kaidi controller and protocol helpers."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.adjustable_bed.beds.kaidi import KaidiCommands, KaidiController
from custom_components.adjustable_bed.const import (
    CONF_KAIDI_ROOM_ID,
    KAIDI_BROADCAST_VADDR,
)
from custom_components.adjustable_bed.kaidi_protocol import (
    KAIDI_ADV_TYPE_BROADCAST,
    KAIDI_ADV_TYPE_SINGLE,
    extract_best_kaidi_advertisement,
    extract_kaidi_advertisement,
    format_kaidi_node_address,
    parse_kaidi_manufacturer_payload,
)


class _KaidiCoordinator(SimpleNamespace):
    """Minimal coordinator stub for Kaidi controller tests."""

    def __init__(self, client: MagicMock, address: str = "AA:BB:CC:DD:EE:FF") -> None:
        super().__init__(
            client=client,
            cancel_command=asyncio.Event(),
            motor_pulse_count=1,
            motor_pulse_delay_ms=1,
            address=address,
            name="Kaidi Test Bed",
            entry=SimpleNamespace(data={}),
        )


def test_parse_broadcast_advertisement_payload() -> None:
    """Broadcast advertisements should expose room ID and virtual address."""
    parsed = parse_kaidi_manufacturer_payload(
        bytes.fromhex("c0ff0278563412ffeeddccbbaa0000810100a004030201")
    )

    assert parsed is not None
    assert parsed.adv_type == KAIDI_ADV_TYPE_BROADCAST
    assert parsed.room_id == 0x12345678
    assert parsed.vaddr == 0x01020304
    assert parsed.sofa_type == 0x81


def test_extract_single_advertisement_payload() -> None:
    """Single-bed advertisements should still expose the room/home ID."""
    parsed = extract_kaidi_advertisement(
        {
            0xFFFF: bytes.fromhex("c0ff017856341281010000000000000000"),
        }
    )

    assert parsed is not None
    assert parsed.adv_type == KAIDI_ADV_TYPE_SINGLE
    assert parsed.room_id == 0x12345678
    assert parsed.vaddr is None


def test_merge_kaidi_advertisement_snapshots() -> None:
    """Mixed advertisement snapshots should combine room ID and VADDR state."""
    parsed = extract_best_kaidi_advertisement(
        [
            {0xFFFF: bytes.fromhex("c0ff017856341281010000000000000000")},
            {0xFFFF: bytes.fromhex("c0ff0278563412ffeeddccbbaa0000810100a004030201")},
        ]
    )

    assert parsed is not None
    assert parsed.adv_type == KAIDI_ADV_TYPE_BROADCAST
    assert parsed.room_id == 0x12345678
    assert parsed.vaddr == 0x01020304


def test_format_kaidi_node_address() -> None:
    """Ping response node addresses should format to standard MAC notation."""
    assert format_kaidi_node_address(bytes.fromhex("ffeeddccbbaa")) == "AA:BB:CC:DD:EE:FF"


@pytest.mark.asyncio
async def test_session_uses_advertised_vaddr_without_ping(mock_bleak_client: MagicMock) -> None:
    """Broadcast advertisements should avoid the extra ping step."""
    coordinator = _KaidiCoordinator(mock_bleak_client)
    controller = KaidiController(
        coordinator,
        device_name="Mouselet",
        manufacturer_data={
            0xFFFF: bytes.fromhex("c0ff0278563412ffeeddccbbaa0000810100a004030201")
        },
    )

    notify_callback: object | None = None

    async def start_notify(_uuid: str, callback: object) -> None:
        nonlocal notify_callback
        notify_callback = callback

    async def write_side_effect(_uuid: str, data: bytes, response: bool = True) -> None:
        del response
        if data == controller._build_join_packet(0x12345678):
            assert notify_callback is not None
            notify_callback(MagicMock(), bytearray([0x02, 0x16, 0x00]))

    mock_bleak_client.start_notify = AsyncMock(side_effect=start_notify)
    mock_bleak_client.write_gatt_char = AsyncMock(side_effect=write_side_effect)

    await controller._ensure_session_ready()

    assert controller._room_id == 0x12345678
    assert controller._target_vaddr == 0x01020304
    assert controller._own_vaddr == KAIDI_BROADCAST_VADDR
    assert mock_bleak_client.write_gatt_char.await_count == 1


@pytest.mark.asyncio
async def test_session_pings_when_advertisement_lacks_vaddr(mock_bleak_client: MagicMock) -> None:
    """Single-bed advertisements should fall back to ping discovery."""
    coordinator = _KaidiCoordinator(mock_bleak_client)
    controller = KaidiController(
        coordinator,
        device_name="Mouselet",
        manufacturer_data={
            0xFFFF: bytes.fromhex("c0ff017856341281010000000000000000")
        },
    )

    notify_callback: object | None = None

    async def start_notify(_uuid: str, callback: object) -> None:
        nonlocal notify_callback
        notify_callback = callback

    async def write_side_effect(_uuid: str, data: bytes, response: bool = True) -> None:
        del response
        assert notify_callback is not None
        if data == controller._build_join_packet(0x12345678):
            notify_callback(MagicMock(), bytearray([0x02, 0x16, 0x00]))
        elif data == controller._build_ping_packet():
            notify_callback(
                MagicMock(),
                bytearray.fromhex("0300000000ffffeeddccbbaa04030201"),
            )

    mock_bleak_client.start_notify = AsyncMock(side_effect=start_notify)
    mock_bleak_client.write_gatt_char = AsyncMock(side_effect=write_side_effect)

    await controller._ensure_session_ready()

    assert controller._target_vaddr == 0x01020304
    assert mock_bleak_client.write_gatt_char.await_count == 2


@pytest.mark.asyncio
async def test_session_uses_cached_room_id_when_manufacturer_data_is_missing(
    mock_bleak_client: MagicMock,
) -> None:
    """Cached Kaidi room IDs should recover sessions without fresh manufacturer data."""
    coordinator = _KaidiCoordinator(mock_bleak_client)
    coordinator.entry.data[CONF_KAIDI_ROOM_ID] = 0x12345678
    controller = KaidiController(
        coordinator,
        device_name="Mouselet",
        manufacturer_data=None,
    )

    notify_callback: object | None = None

    async def start_notify(_uuid: str, callback: object) -> None:
        nonlocal notify_callback
        notify_callback = callback

    async def write_side_effect(_uuid: str, data: bytes, response: bool = True) -> None:
        del response
        assert notify_callback is not None
        if data == controller._build_join_packet(0x12345678):
            notify_callback(MagicMock(), bytearray([0x02, 0x16, 0x00]))
        elif data == controller._build_ping_packet():
            notify_callback(
                MagicMock(),
                bytearray.fromhex("0300000000ffffeeddccbbaa04030201"),
            )

    mock_bleak_client.start_notify = AsyncMock(side_effect=start_notify)
    mock_bleak_client.write_gatt_char = AsyncMock(side_effect=write_side_effect)

    await controller._ensure_session_ready()

    assert controller._room_id == 0x12345678
    assert controller._target_vaddr == 0x01020304


@pytest.mark.asyncio
async def test_move_head_up_sends_move_then_stop(mock_bleak_client: MagicMock) -> None:
    """Head movement should emit the motor command followed by a stop command."""
    coordinator = _KaidiCoordinator(mock_bleak_client)
    controller = KaidiController(
        coordinator,
        device_name="Mouselet",
        manufacturer_data={
            0xFFFF: bytes.fromhex("c0ff0278563412ffeeddccbbaa0000810100a004030201")
        },
    )

    notify_callback: object | None = None

    async def start_notify(_uuid: str, callback: object) -> None:
        nonlocal notify_callback
        notify_callback = callback

    async def write_side_effect(_uuid: str, data: bytes, response: bool = True) -> None:
        del response
        if data == controller._build_join_packet(0x12345678):
            assert notify_callback is not None
            notify_callback(MagicMock(), bytearray([0x02, 0x16, 0x00]))

    mock_bleak_client.start_notify = AsyncMock(side_effect=start_notify)
    mock_bleak_client.write_gatt_char = AsyncMock(side_effect=write_side_effect)

    await controller._ensure_session_ready()
    mock_bleak_client.write_gatt_char.reset_mock(side_effect=False)

    await controller.move_head_up()

    calls = mock_bleak_client.write_gatt_char.await_args_list
    assert len(calls) == 2
    assert calls[0].args[1] == controller._build_control_packet(KaidiCommands.HEAD_UP)
    assert calls[1].args[1] == controller._build_control_packet(KaidiCommands.HEAD_STOP)
