"""Tests for the Kaidi controller and protocol helpers."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.adjustable_bed.beds.kaidi import (
    KAIDI_COMMAND_PROFILES,
    KaidiCommands,
    KaidiController,
)
from custom_components.adjustable_bed.const import (
    CONF_KAIDI_ROOM_ID,
    KAIDI_BROADCAST_VADDR,
    KAIDI_VARIANT_SEAT_1,
    KAIDI_VARIANT_SEAT_1_2,
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

    def __init__(
        self,
        client: MagicMock,
        address: str = "AA:BB:CC:DD:EE:FF",
        has_massage: bool = True,
    ) -> None:
        super().__init__(
            client=client,
            cancel_command=asyncio.Event(),
            motor_pulse_count=1,
            motor_pulse_delay_ms=1,
            address=address,
            name="Kaidi Test Bed",
            entry=SimpleNamespace(data={}),
            has_massage=has_massage,
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


# ---------------------------------------------------------------------------
# Protocol parsing tests
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Variant resolution tests
# ---------------------------------------------------------------------------


def test_resolve_kaidi_variant_manual_override() -> None:
    """Manual variant overrides must win over advertised metadata."""
    resolution = resolve_kaidi_variant(
        KAIDI_VARIANT_SEAT_2,
        product_id=129,
        sofa_acu_no=0x2004,
    )

    assert resolution.variant == KAIDI_VARIANT_SEAT_2
    assert resolution.source == "manual_override"


def test_resolve_kaidi_variant_manual_override_seat_1_2() -> None:
    """Manual seat_1_2 override should be accepted."""
    resolution = resolve_kaidi_variant(
        KAIDI_VARIANT_SEAT_1_2,
        product_id=129,
    )

    assert resolution.variant == KAIDI_VARIANT_SEAT_1_2
    assert resolution.source == "manual_override"


def test_resolve_kaidi_variant_single_product_id() -> None:
    """Single-base product IDs should resolve to seat_1."""
    for pid in (129, 131, 132, 135, 136, 137, 138, 139, 142):
        resolution = resolve_kaidi_variant(VARIANT_AUTO, product_id=pid)
        assert resolution.variant == KAIDI_VARIANT_SEAT_1, f"product_id={pid}"
        assert resolution.source == "product_id"


def test_resolve_kaidi_variant_double_product_id() -> None:
    """Double-base product IDs should resolve to seat_1_2."""
    for pid in (130, 133, 134, 143):
        resolution = resolve_kaidi_variant(VARIANT_AUTO, product_id=pid)
        assert resolution.variant == KAIDI_VARIANT_SEAT_1_2, f"product_id={pid}"
        assert resolution.source == "product_id"


def test_resolve_kaidi_variant_issue247_uses_product_id() -> None:
    """Product 136 (Rize Remedy 4) should resolve to seat_1 via product_id."""
    resolution = resolve_kaidi_variant(
        VARIANT_AUTO,
        product_id=136,
        sofa_acu_no=0x2004,
    )

    assert resolution.variant == KAIDI_VARIANT_SEAT_1
    assert resolution.source == "product_id"


def test_resolve_kaidi_variant_sofa_acu_no_fallback() -> None:
    """When product_id is unknown, seat-bar heuristic should be used."""
    resolution = resolve_kaidi_variant(
        VARIANT_AUTO,
        product_id=999,
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
        product_id=999,
        sofa_acu_no=0x0000,
    )

    assert resolution.variant is None
    assert resolution.source == "unresolved_metadata"


# ---------------------------------------------------------------------------
# Session management tests
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Motor command tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("variant", "move_command", "stop_command"),
    [
        (KAIDI_VARIANT_SEAT_1, 0x01, 0x03),
        (KAIDI_VARIANT_SEAT_2, 0x0A, 0x0C),
        (KAIDI_VARIANT_SEAT_3, 0x13, 0x15),
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
    """Seat-3 (no stop_all) should stop every supported actuator explicitly."""
    controller = await _prepare_controller(mock_bleak_client, variant=KAIDI_VARIANT_SEAT_3)

    await controller.stop_all()

    calls = mock_bleak_client.write_gatt_char.await_args_list
    assert len(calls) == 3
    assert calls[0].args[1] == controller._build_control_packet(0x15)  # seat_3 head_stop
    assert calls[1].args[1] == controller._build_control_packet(0x18)  # seat_3 foot_stop
    assert calls[2].args[1] == controller._build_control_packet(0x1B)  # seat_3 waist_stop


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
async def test_book_and_leisure_presets_map_to_tv_and_lounge_capabilities(
    mock_bleak_client: MagicMock,
) -> None:
    """Kaidi book/leisure opcodes should surface through the existing TV/lounge presets."""
    controller = await _prepare_controller(
        mock_bleak_client,
        variant=KAIDI_VARIANT_SEAT_1,
    )
    controller._product_id = 135

    assert controller.supports_preset_tv is True
    assert controller.supports_preset_lounge is True

    await controller.preset_tv()
    await controller.preset_lounge()

    calls = mock_bleak_client.write_gatt_char.await_args_list
    assert len(calls) == 2
    assert calls[0].args[1] == controller._build_control_packet(0x9E)
    assert calls[1].args[1] == controller._build_control_packet(0xA1)


@pytest.mark.asyncio
async def test_direct_position_progress_commands_use_progress_parameter(
    mock_bleak_client: MagicMock,
) -> None:
    """Kaidi direct position writes should send the APK-backed progress opcodes."""
    controller = await _prepare_controller(mock_bleak_client, variant=KAIDI_VARIANT_SEAT_1)

    await controller.set_motor_position("back", 37)
    await controller.set_motor_position("legs", 64)

    calls = mock_bleak_client.write_gatt_char.await_args_list
    assert len(calls) == 2
    assert calls[0].args[1] == controller._build_control_packet(0x4D, param=37)
    assert calls[1].args[1] == controller._build_control_packet(0x4F, param=64)


@pytest.mark.asyncio
async def test_massage_timer_commands_update_local_state(
    mock_bleak_client: MagicMock,
) -> None:
    """Kaidi massage timers should send the correct opcode and update select state."""
    controller = await _prepare_controller(
        mock_bleak_client,
        variant=KAIDI_VARIANT_SEAT_1,
    )
    controller._product_id = 135

    assert controller.supports_massage_timer is True
    assert controller.massage_timer_options == [15, 30, 45]

    await controller.set_massage_timer(30)

    calls = mock_bleak_client.write_gatt_char.await_args_list
    assert len(calls) == 1
    assert calls[0].args[1] == controller._build_control_packet(0x54)
    assert controller.get_massage_state()["timer_mode"] == "30"
    assert controller.get_massage_state()["mode"] is None


@pytest.mark.asyncio
async def test_verified_kaidi_profiles_do_not_expose_massage_mode_step(
    mock_bleak_client: MagicMock,
) -> None:
    """JS-only Kaidi massage mode buttons should stay disabled until verified."""
    controller = await _prepare_controller(
        mock_bleak_client,
        variant=KAIDI_VARIANT_SEAT_1,
    )
    controller._product_id = 135

    assert controller.supports_massage_mode_step_control is False

    with pytest.raises(NotImplementedError, match="does not support massage modes"):
        await controller.massage_mode_step()


@pytest.mark.asyncio
async def test_discrete_light_control_follows_product_family_capability(
    mock_bleak_client: MagicMock,
) -> None:
    """Kaidi should only expose discrete light control on light-capable product families."""
    unsupported = await _prepare_controller(
        mock_bleak_client,
        variant=KAIDI_VARIANT_SEAT_1,
    )
    unsupported._product_id = 129
    supported = await _prepare_controller(
        mock_bleak_client,
        variant=KAIDI_VARIANT_SEAT_1,
    )
    supported._product_id = 135

    assert unsupported.supports_discrete_light_control is False
    assert supported.supports_discrete_light_control is True


@pytest.mark.asyncio
async def test_seat_3_lumbar_commands_use_verified_waist_opcodes(
    mock_bleak_client: MagicMock,
) -> None:
    """Seat_3 should expose waist control through the lumbar surface."""
    controller = await _prepare_controller(mock_bleak_client, variant=KAIDI_VARIANT_SEAT_3)

    assert controller.has_lumbar_support is True

    await controller.move_lumbar_up()

    calls = mock_bleak_client.write_gatt_char.await_args_list
    assert len(calls) == 2
    assert calls[0].args[1] == controller._build_control_packet(0x19)
    assert calls[1].args[1] == controller._build_control_packet(0x1B)


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


# ---------------------------------------------------------------------------
# Dual-bed (seat_1_2) tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_seat_1_2_sends_both_sides_for_head_up(mock_bleak_client: MagicMock) -> None:
    """seat_1_2 should send seat_1 HEAD_UP then seat_2 HEAD_UP."""
    controller = await _prepare_controller(mock_bleak_client, variant=KAIDI_VARIANT_SEAT_1_2)

    await controller.move_head_up()

    calls = mock_bleak_client.write_gatt_char.await_args_list
    # move: seat_1 head_up + seat_2 head_up, then stop: seat_1 head_stop + seat_2 head_stop
    assert len(calls) == 4
    assert calls[0].args[1] == controller._build_control_packet(0x01)  # SEAT_1_HEAD_UP
    assert calls[1].args[1] == controller._build_control_packet(0x0A)  # SEAT_2_HEAD_UP
    assert calls[2].args[1] == controller._build_control_packet(0x03)  # SEAT_1_HEAD_STOP
    assert calls[3].args[1] == controller._build_control_packet(0x0C)  # SEAT_2_HEAD_STOP


@pytest.mark.asyncio
async def test_seat_1_2_stop_all_sends_both_sides(mock_bleak_client: MagicMock) -> None:
    """seat_1_2 stop_all should send seat_1 STOP_ALL then seat_2 STOP_ALL."""
    controller = await _prepare_controller(mock_bleak_client, variant=KAIDI_VARIANT_SEAT_1_2)

    await controller.stop_all()

    calls = mock_bleak_client.write_gatt_char.await_args_list
    assert len(calls) == 2
    assert calls[0].args[1] == controller._build_control_packet(0x1C)  # SEAT_1_STOP_ALL
    assert calls[1].args[1] == controller._build_control_packet(0x1D)  # SEAT_2_STOP_ALL


@pytest.mark.asyncio
async def test_seat_1_2_preset_sends_both_sides(mock_bleak_client: MagicMock) -> None:
    """seat_1_2 presets should send for both seats."""
    controller = await _prepare_controller(mock_bleak_client, variant=KAIDI_VARIANT_SEAT_1_2)

    await controller.preset_flat()

    calls = mock_bleak_client.write_gatt_char.await_args_list
    assert len(calls) == 2
    assert calls[0].args[1] == controller._build_control_packet(0x68)  # SEAT_1_FLAT
    assert calls[1].args[1] == controller._build_control_packet(0x69)  # SEAT_2_FLAT


# ---------------------------------------------------------------------------
# Extended command tests
# ---------------------------------------------------------------------------


def test_primary_seat_profiles_have_verified_extended_commands() -> None:
    """Seat_1 and seat_2 profiles should include verified Kaidi OEM commands."""
    for variant_key in (KAIDI_VARIANT_SEAT_1, KAIDI_VARIANT_SEAT_2):
        profile = KAIDI_COMMAND_PROFILES[variant_key]
        assert profile.back_up is not None, f"{variant_key} missing back_up"
        assert profile.waist_up is not None, f"{variant_key} missing waist_up"
        assert profile.neck_up is not None, f"{variant_key} missing neck_up"
        assert profile.light_on is not None, f"{variant_key} missing light_on"
        assert profile.massage_start is not None, f"{variant_key} missing massage_start"
        assert profile.massage_timer_15 is not None, f"{variant_key} missing massage_timer_15"
        assert profile.preset_book is not None, f"{variant_key} missing preset_book"
        assert profile.preset_leisure is not None, f"{variant_key} missing preset_leisure"


def test_seat_3_profile_includes_verified_waist_commands() -> None:
    """Seat_3 should carry the waist opcodes confirmed in PLDataTrans.java."""
    profile = KAIDI_COMMAND_PROFILES[KAIDI_VARIANT_SEAT_3]
    assert profile.waist_up == 0x19
    assert profile.waist_down == 0x1A
    assert profile.waist_stop == 0x1B


def test_seat_1_2_profile_uses_seat_1_values() -> None:
    """seat_1_2 profile should have the same command values as seat_1."""
    seat_1 = KAIDI_COMMAND_PROFILES[KAIDI_VARIANT_SEAT_1]
    seat_1_2 = KAIDI_COMMAND_PROFILES[KAIDI_VARIANT_SEAT_1_2]

    assert seat_1_2.head_up == seat_1.head_up
    assert seat_1_2.foot_down == seat_1.foot_down
    assert seat_1_2.back_up == seat_1.back_up
    assert seat_1_2.light_on == seat_1.light_on


def test_no_bed_variant_profiles_exist() -> None:
    """BED_* variant profiles must not exist — they used wrong command values."""
    for key in KAIDI_COMMAND_PROFILES:
        assert not key.startswith("bed_"), f"Found legacy BED profile: {key}"
