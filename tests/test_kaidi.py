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
    KAIDI_VARIANT_BED_1,
    KAIDI_VARIANT_BED_12,
    KAIDI_VARIANT_BED_2,
    KAIDI_VARIANT_SEAT_1,
    KAIDI_VARIANT_SEAT_2,
    KAIDI_VARIANT_SEAT_3,
    VARIANT_AUTO,
)
from custom_components.adjustable_bed.kaidi_protocol import (
    KAIDI_ADV_TYPE_BROADCAST,
    KAIDI_ADV_TYPE_SINGLE,
    extract_best_kaidi_advertisement,
    extract_kaidi_advertisement,
    format_kaidi_node_address,
    kaidi_advertisement_to_dict,
    parse_kaidi_manufacturer_payload,
)
from custom_components.adjustable_bed.kaidi_variants import resolve_kaidi_variant

BROADCAST_MANUFACTURER_DATA = {
    0xFFFF: bytes.fromhex("c0ff0278563412ffeeddccbbaa0000810100a004030201")
}
SINGLE_MANUFACTURER_DATA = {
    0xFFFF: bytes.fromhex("c0ff017856341281010000000000000000")
}
ISSUE247_BROADCAST_PAYLOAD = bytes.fromhex(
    "c0ff025e270000e55d547fc5ec0200882004a101000000"
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
            record_command_trace=MagicMock(),
        )


async def _prepare_controller(
    mock_bleak_client: MagicMock,
    *,
    variant: str = KAIDI_VARIANT_SEAT_1,
    manufacturer_data: dict[int, bytes] | None = None,
    entry_data: dict[str, int] | None = None,
) -> KaidiController:
    """Create a Kaidi controller with a primed session."""
    coordinator = _KaidiCoordinator(mock_bleak_client)
    if entry_data:
        coordinator.entry.data.update(entry_data)

    controller = KaidiController(
        coordinator,
        device_name="Mouselet",
        manufacturer_data=manufacturer_data or BROADCAST_MANUFACTURER_DATA,
        variant=variant,
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

    mock_bleak_client.start_notify = AsyncMock(side_effect=start_notify)
    mock_bleak_client.write_gatt_char = AsyncMock(side_effect=write_side_effect)

    await controller._ensure_session_ready()
    mock_bleak_client.write_gatt_char = AsyncMock()
    return controller


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
    assert parsed.product_id == 0x81
    assert parsed.sofa_acu_no == 0x0100


def test_parse_issue247_broadcast_payload() -> None:
    """The issue-247 payload should decode Kaidi metadata from manufacturer data."""
    parsed = parse_kaidi_manufacturer_payload(ISSUE247_BROADCAST_PAYLOAD)

    assert parsed is not None
    assert parsed.adv_type == KAIDI_ADV_TYPE_BROADCAST
    assert parsed.room_id == 0x275E
    assert parsed.vaddr == 0x00000001
    assert parsed.product_id == 136
    assert parsed.sofa_acu_no == 0x2004

    serialized = kaidi_advertisement_to_dict(parsed)
    assert serialized["seat_1_bars"] == 4
    assert serialized["seat_2_bars"] == 0
    assert serialized["seat_3_bars"] == 0
    assert serialized["is_store"] is True


def test_extract_single_advertisement_payload() -> None:
    """Single-bed advertisements should still expose the room/home ID."""
    parsed = extract_kaidi_advertisement(SINGLE_MANUFACTURER_DATA)

    assert parsed is not None
    assert parsed.adv_type == KAIDI_ADV_TYPE_SINGLE
    assert parsed.room_id == 0x12345678
    assert parsed.vaddr is None
    assert parsed.product_id == 0x81
    assert parsed.sofa_acu_no == 0x0100


def test_merge_kaidi_advertisement_snapshots() -> None:
    """Mixed advertisement snapshots should combine room ID and VADDR state."""
    parsed = extract_best_kaidi_advertisement(
        [
            SINGLE_MANUFACTURER_DATA,
            BROADCAST_MANUFACTURER_DATA,
        ]
    )

    assert parsed is not None
    assert parsed.adv_type == KAIDI_ADV_TYPE_BROADCAST
    assert parsed.room_id == 0x12345678
    assert parsed.vaddr == 0x01020304
    assert parsed.product_id == 0x81
    assert parsed.sofa_acu_no == 0x0100


def test_format_kaidi_node_address() -> None:
    """Ping response node addresses should format to standard MAC notation."""
    assert format_kaidi_node_address(bytes.fromhex("ffeeddccbbaa")) == "AA:BB:CC:DD:EE:FF"


def test_resolve_kaidi_variant_manual_override() -> None:
    """Manual variant overrides must win over advertised metadata."""
    resolution = resolve_kaidi_variant(
        KAIDI_VARIANT_BED_2,
        product_id=129,
        sofa_acu_no=0x2004,
    )

    assert resolution.variant == KAIDI_VARIANT_BED_2
    assert resolution.source == "manual_override"


def test_resolve_kaidi_variant_prefers_exact_product_mapping() -> None:
    """Exact OEM BED_TYPE mappings should take precedence over seat-bar heuristics."""
    resolution = resolve_kaidi_variant(
        VARIANT_AUTO,
        product_id=130,
        sofa_acu_no=0x2004,
    )

    assert resolution.variant == KAIDI_VARIANT_BED_12
    assert resolution.source == "product_id"


def test_resolve_kaidi_variant_issue247_uses_sofa_acu_no() -> None:
    """The issue-247 sofa metadata should resolve to the seat-1 profile."""
    resolution = resolve_kaidi_variant(
        VARIANT_AUTO,
        product_id=136,
        sofa_acu_no=0x2004,
    )

    assert resolution.variant == KAIDI_VARIANT_SEAT_1
    assert resolution.source == "sofa_acu_no"
    assert resolution.seat_bars is not None
    assert resolution.seat_bars.populated_seats == (1,)


def test_resolve_kaidi_variant_without_metadata_falls_back_to_legacy() -> None:
    """Legacy Kaidi entries without metadata should keep the old seat-1 behavior."""
    resolution = resolve_kaidi_variant(VARIANT_AUTO)

    assert resolution.variant == KAIDI_VARIANT_SEAT_1
    assert resolution.source == "legacy_fallback"


def test_resolve_kaidi_variant_with_unknown_metadata_requires_override() -> None:
    """Unknown Kaidi metadata should refuse to guess a profile automatically."""
    resolution = resolve_kaidi_variant(
        VARIANT_AUTO,
        product_id=136,
        sofa_acu_no=0x0000,
    )

    assert resolution.variant is None
    assert resolution.source == "unresolved_metadata"


@pytest.mark.asyncio
async def test_session_uses_advertised_vaddr_without_ping(mock_bleak_client: MagicMock) -> None:
    """Broadcast advertisements should avoid the extra ping step."""
    coordinator = _KaidiCoordinator(mock_bleak_client)
    controller = KaidiController(
        coordinator,
        device_name="Mouselet",
        manufacturer_data=BROADCAST_MANUFACTURER_DATA,
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
        manufacturer_data=SINGLE_MANUFACTURER_DATA,
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
@pytest.mark.parametrize(
    ("variant", "move_command", "stop_command"),
    [
        (KAIDI_VARIANT_SEAT_1, 0x01, 0x03),
        (KAIDI_VARIANT_SEAT_2, 0x0A, 0x0C),
        (KAIDI_VARIANT_SEAT_3, 0x13, 0x15),
        (KAIDI_VARIANT_BED_1, 0x47, 0x49),
        (KAIDI_VARIANT_BED_2, 0x4A, 0x4C),
        (KAIDI_VARIANT_BED_12, 0x53, 0x55),
    ],
)
async def test_move_head_up_uses_variant_specific_command_profile(
    mock_bleak_client: MagicMock,
    variant: str,
    move_command: int,
    stop_command: int,
) -> None:
    """Head movement should follow the selected Kaidi profile."""
    controller = await _prepare_controller(mock_bleak_client, variant=variant)

    await controller.move_head_up()

    calls = mock_bleak_client.write_gatt_char.await_args_list
    assert len(calls) == 2
    assert calls[0].args[1] == controller._build_control_packet(move_command)
    assert calls[1].args[1] == controller._build_control_packet(stop_command)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("variant", "move_command", "stop_command"),
    [
        (KAIDI_VARIANT_SEAT_1, 0x05, 0x06),
        (KAIDI_VARIANT_SEAT_2, 0x0E, 0x0F),
        (KAIDI_VARIANT_SEAT_3, 0x17, 0x18),
        (KAIDI_VARIANT_BED_1, 0x4E, 0x4F),
        (KAIDI_VARIANT_BED_2, 0x51, 0x52),
        (KAIDI_VARIANT_BED_12, 0x57, 0x58),
    ],
)
async def test_move_legs_down_uses_variant_specific_command_profile(
    mock_bleak_client: MagicMock,
    variant: str,
    move_command: int,
    stop_command: int,
) -> None:
    """Leg movement should follow the selected Kaidi profile."""
    controller = await _prepare_controller(mock_bleak_client, variant=variant)

    await controller.move_legs_down()

    calls = mock_bleak_client.write_gatt_char.await_args_list
    assert len(calls) == 2
    assert calls[0].args[1] == controller._build_control_packet(move_command)
    assert calls[1].args[1] == controller._build_control_packet(stop_command)


@pytest.mark.asyncio
async def test_stop_all_uses_dedicated_command_when_available(mock_bleak_client: MagicMock) -> None:
    """Seat-1 should use its dedicated stop-all opcode."""
    controller = await _prepare_controller(mock_bleak_client, variant=KAIDI_VARIANT_SEAT_1)

    await controller.stop_all()

    calls = mock_bleak_client.write_gatt_char.await_args_list
    assert len(calls) == 1
    assert calls[0].args[1] == controller._build_control_packet(KaidiCommands.STOP_ALL)


@pytest.mark.asyncio
async def test_stop_all_falls_back_to_per_motor_stops(mock_bleak_client: MagicMock) -> None:
    """Profiles without stop-all should stop head and foot motors explicitly."""
    controller = await _prepare_controller(mock_bleak_client, variant=KAIDI_VARIANT_BED_12)

    await controller.stop_all()

    calls = mock_bleak_client.write_gatt_char.await_args_list
    assert len(calls) == 2
    assert calls[0].args[1] == controller._build_control_packet(0x55)
    assert calls[1].args[1] == controller._build_control_packet(0x58)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("variant", "method_name", "expected_command"),
    [
        (KAIDI_VARIANT_SEAT_1, "preset_flat", 0x68),
        (KAIDI_VARIANT_SEAT_2, "preset_zero_g", 0x63),
        (KAIDI_VARIANT_SEAT_2, "preset_anti_snore", 0x66),
    ],
)
async def test_preset_commands_use_variant_specific_profile(
    mock_bleak_client: MagicMock,
    variant: str,
    method_name: str,
    expected_command: int,
) -> None:
    """Seat-profile preset buttons should emit the APK-backed opcodes."""
    controller = await _prepare_controller(mock_bleak_client, variant=variant)

    await getattr(controller, method_name)()

    calls = mock_bleak_client.write_gatt_char.await_args_list
    assert len(calls) == 1
    assert calls[0].args[1] == controller._build_control_packet(expected_command)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("variant", "memory_slot", "expected_command"),
    [
        (KAIDI_VARIANT_SEAT_1, 4, 0x2C),
        (KAIDI_VARIANT_SEAT_2, 4, 0x34),
        (KAIDI_VARIANT_SEAT_3, 3, 0x3B),
    ],
)
async def test_memory_recall_commands_use_variant_specific_profile(
    mock_bleak_client: MagicMock,
    variant: str,
    memory_slot: int,
    expected_command: int,
) -> None:
    """Memory recall should follow the selected seat profile."""
    controller = await _prepare_controller(mock_bleak_client, variant=variant)

    await controller.preset_memory(memory_slot)

    calls = mock_bleak_client.write_gatt_char.await_args_list
    assert len(calls) == 1
    assert calls[0].args[1] == controller._build_control_packet(expected_command)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("variant", "memory_slot", "expected_command"),
    [
        (KAIDI_VARIANT_SEAT_1, 1, 0x25),
        (KAIDI_VARIANT_SEAT_2, 2, 0x2E),
        (KAIDI_VARIANT_SEAT_3, 4, 0x38),
    ],
)
async def test_memory_programming_commands_use_variant_specific_profile(
    mock_bleak_client: MagicMock,
    variant: str,
    memory_slot: int,
    expected_command: int,
) -> None:
    """Memory programming should follow the selected seat profile."""
    controller = await _prepare_controller(mock_bleak_client, variant=variant)

    await controller.program_memory(memory_slot)

    calls = mock_bleak_client.write_gatt_char.await_args_list
    assert len(calls) == 1
    assert calls[0].args[1] == controller._build_control_packet(expected_command)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("variant", "method_name", "args"),
    [
        (KAIDI_VARIANT_BED_1, "preset_flat", ()),
        (KAIDI_VARIANT_BED_2, "preset_memory", (1,)),
        (KAIDI_VARIANT_BED_12, "program_memory", (1,)),
    ],
)
async def test_bed_profiles_reject_unsupported_preset_and_memory_commands(
    mock_bleak_client: MagicMock,
    variant: str,
    method_name: str,
    args: tuple[int, ...],
) -> None:
    """Split-bed profiles should not expose unsupported seat preset helpers."""
    controller = await _prepare_controller(mock_bleak_client, variant=variant)

    with pytest.raises(NotImplementedError):
        await getattr(controller, method_name)(*args)
