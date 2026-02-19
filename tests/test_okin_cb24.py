"""Tests for Okin CB24/CBNew controller behavior."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, call

import pytest

from custom_components.adjustable_bed.beds.okin_cb24 import (
    _PRESET_CONTINUOUS_COUNT,
    _PRESET_CONTINUOUS_DELAY_MS,
    OkinCB24Commands,
    OkinCB24Controller,
)
from custom_components.adjustable_bed.const import (
    BED_TYPE_OKIN_CB24,
    MANUFACTURER_ID_OKIN,
    OKIN_CB24_VARIANT_CB24,
    OKIN_CB24_VARIANT_CB24_AB,
    OKIN_CB24_VARIANT_CB27,
    OKIN_CB24_VARIANT_CB27NEW,
    OKIN_CB24_VARIANT_CB1221,
    OKIN_CB24_VARIANT_DACHENG,
    OKIN_CB24_VARIANT_NEW,
    OKIN_CB24_VARIANT_OLD,
)
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.validators import (
    get_variants_for_bed_type,
    is_valid_variant_for_bed_type,
)


def _make_factory_coordinator() -> SimpleNamespace:
    """Create a minimal coordinator stub for factory tests."""
    return SimpleNamespace(
        client=None,
        cancel_command=None,
        motor_pulse_count=10,
        motor_pulse_delay_ms=100,
        address="AA:BB:CC:DD:EE:FF",
        name="CB24 Test Bed",
        motor_count=2,
        has_massage=True,
        disable_angle_sensing=True,
    )


class TestOkinCB24Controller:
    """Test OkinCB24Controller."""

    def test_protocol_command_bytes_match_cb24_format(self) -> None:
        """Legacy CB24 packet bytes should match OEM app command format."""
        coordinator_default = MagicMock()
        coordinator_default.address = "AA:BB:CC:DD:EE:FF"
        controller_default = OkinCB24Controller(coordinator_default)
        assert controller_default._build_command(OkinCB24Commands.PRESET_FLAT) == bytes(
            [0x05, 0x02, 0x08, 0x00, 0x00, 0x00, 0x00]
        )

        coordinator_bed_a = MagicMock()
        coordinator_bed_a.address = "AA:BB:CC:DD:EE:FF"
        controller_bed_a = OkinCB24Controller(coordinator_bed_a, bed_selection=0xAA)
        assert controller_bed_a._build_command(OkinCB24Commands.MASSAGE_ALL_TOGGLE) == bytes(
            [0x05, 0x02, 0x00, 0x00, 0x01, 0x00, 0xAA]
        )

    def test_new_protocol_motor_and_stop_packets_match_cbnew(self) -> None:
        """CBNew profiles should use 0x2A/0xAA packet families for motor/stop."""
        coordinator = MagicMock()
        coordinator.address = "AA:BB:CC:DD:EE:FF"
        controller = OkinCB24Controller(coordinator, protocol_variant=OKIN_CB24_VARIANT_CB27NEW)

        assert controller._build_motor_command(OkinCB24Commands.MOTOR_HEAD_UP) == bytes(
            [0x2A, 0x00, 0x00, 0x01, 0x01, 0x04, 0x01, 0x00, 0x00, 0x00]
        )
        assert controller._build_stop_command() == bytes([0xAA, 0x00, 0x00, 0x01, 0x02, 0x00])

    def test_new_protocol_preset_mapping_matches_cbnew_memory_indices(self) -> None:
        """CBNew profiles should map preset integers to CBNew memory indices."""
        coordinator = MagicMock()
        coordinator.address = "AA:BB:CC:DD:EE:FF"
        controller = OkinCB24Controller(coordinator, protocol_variant=OKIN_CB24_VARIANT_CB27NEW)

        assert controller._build_preset_command(OkinCB24Commands.PRESET_FLAT) == bytes(
            [0x2A, 0x00, 0x00, 0x01, 0x03, 0x01, 0x09]
        )
        assert controller._build_preset_command(OkinCB24Commands.PRESET_ZERO_G) == bytes(
            [0x2A, 0x00, 0x00, 0x01, 0x03, 0x01, 0x01]
        )
        assert controller._build_preset_command(OkinCB24Commands.PRESET_MEMORY_1) == bytes(
            [0x2A, 0x00, 0x00, 0x01, 0x03, 0x01, 0x02]
        )

    @pytest.mark.asyncio
    async def test_new_protocol_preset_is_one_shot(self) -> None:
        """CBNew presets should be one-shot with no trailing STOP."""
        coordinator = MagicMock()
        coordinator.address = "AA:BB:CC:DD:EE:FF"
        controller = OkinCB24Controller(coordinator, protocol_variant=OKIN_CB24_VARIANT_CB27NEW)
        controller.write_command = AsyncMock()

        await controller._send_preset(OkinCB24Commands.PRESET_ZERO_G)

        controller.write_command.assert_awaited_once_with(
            bytes([0x2A, 0x00, 0x00, 0x01, 0x03, 0x01, 0x01]),
        )

    @pytest.mark.asyncio
    async def test_old_protocol_preset_sends_continuously_then_stop(self) -> None:
        """`cb_old` compatibility presets should send repeatedly at 300ms then STOP."""
        coordinator = MagicMock()
        coordinator.address = "AA:BB:CC:DD:EE:FF"
        controller = OkinCB24Controller(coordinator, protocol_variant=OKIN_CB24_VARIANT_OLD)
        controller.write_command = AsyncMock()

        await controller._send_preset(OkinCB24Commands.PRESET_FLAT)

        assert controller.write_command.await_count == 2
        first_call = controller.write_command.await_args_list[0]
        assert first_call == call(
            controller._build_command(OkinCB24Commands.PRESET_FLAT),
            repeat_count=_PRESET_CONTINUOUS_COUNT,
            repeat_delay_ms=_PRESET_CONTINUOUS_DELAY_MS,
        )
        second_call = controller.write_command.await_args_list[1]
        assert second_call.args[0] == controller._build_command(0)

    @pytest.mark.asyncio
    async def test_cb24_profile_preset_is_one_shot(self) -> None:
        """CB24 profile presets should be one-shot to match known working hardware."""
        coordinator = MagicMock()
        coordinator.address = "AA:BB:CC:DD:EE:FF"
        controller = OkinCB24Controller(coordinator, protocol_variant=OKIN_CB24_VARIANT_CB24)
        controller.write_command = AsyncMock()

        await controller._send_preset(OkinCB24Commands.PRESET_MEMORY_1)

        controller.write_command.assert_awaited_once_with(
            controller._build_command(OkinCB24Commands.PRESET_MEMORY_1),
        )

    @pytest.mark.asyncio
    async def test_adaptive_cb24_promotes_to_continuous_after_retry(self) -> None:
        """Auto legacy mode should switch to continuous presets after quick retry."""
        coordinator = MagicMock()
        coordinator.address = "AA:BB:CC:DD:EE:FF"
        controller = OkinCB24Controller(
            coordinator,
            protocol_variant=OKIN_CB24_VARIANT_CB24,
            adaptive_preset_fallback=True,
        )
        controller.write_command = AsyncMock()

        await controller._send_preset(OkinCB24Commands.PRESET_MEMORY_1)
        await controller._send_preset(OkinCB24Commands.PRESET_MEMORY_1)

        assert controller.write_command.await_count == 3
        assert controller.write_command.await_args_list[0] == call(
            controller._build_command(OkinCB24Commands.PRESET_MEMORY_1),
        )
        assert controller.write_command.await_args_list[1] == call(
            controller._build_command(OkinCB24Commands.PRESET_MEMORY_1),
            repeat_count=_PRESET_CONTINUOUS_COUNT,
            repeat_delay_ms=_PRESET_CONTINUOUS_DELAY_MS,
        )
        assert controller.write_command.await_args_list[2].args[0] == controller._build_command(0)
        assert controller._continuous_presets is True
        assert controller._adaptive_preset_fallback is False

    @pytest.mark.asyncio
    async def test_adaptive_cb24_stays_one_shot_for_different_preset(self) -> None:
        """Adaptive fallback should not promote when different presets are tapped."""
        coordinator = MagicMock()
        coordinator.address = "AA:BB:CC:DD:EE:FF"
        controller = OkinCB24Controller(
            coordinator,
            protocol_variant=OKIN_CB24_VARIANT_CB24,
            adaptive_preset_fallback=True,
        )
        controller.write_command = AsyncMock()

        await controller._send_preset(OkinCB24Commands.PRESET_MEMORY_1)
        await controller._send_preset(OkinCB24Commands.PRESET_MEMORY_2)

        assert controller.write_command.await_count == 2
        assert controller.write_command.await_args_list[0] == call(
            controller._build_command(OkinCB24Commands.PRESET_MEMORY_1),
        )
        assert controller.write_command.await_args_list[1] == call(
            controller._build_command(OkinCB24Commands.PRESET_MEMORY_2),
        )
        assert controller._continuous_presets is False
        assert controller._adaptive_preset_fallback is True

    def test_adaptive_cb24_stays_one_shot_after_window_expires(self) -> None:
        """Adaptive fallback should not promote when retry is outside the 12-second window."""
        coordinator = MagicMock()
        coordinator.address = "AA:BB:CC:DD:EE:FF"
        controller = OkinCB24Controller(
            coordinator,
            protocol_variant=OKIN_CB24_VARIANT_CB24,
            adaptive_preset_fallback=True,
        )

        # First tap at t=1000 records the preset and timestamp
        result1 = controller._should_promote_presets_to_continuous(
            OkinCB24Commands.PRESET_MEMORY_1, _now=1000.0
        )
        assert result1 is False

        # Retry same preset after window has expired (13s > 12s) — treated as fresh tap
        result2 = controller._should_promote_presets_to_continuous(
            OkinCB24Commands.PRESET_MEMORY_1, _now=1013.0
        )
        assert result2 is False
        assert controller._continuous_presets is False
        assert controller._adaptive_preset_fallback is True

    @pytest.mark.asyncio
    async def test_old_protocol_preset_sends_stop_on_cancellation(self) -> None:
        """`cb_old` compatibility profile should still attempt STOP on cancellation."""
        coordinator = MagicMock()
        coordinator.address = "AA:BB:CC:DD:EE:FF"
        controller = OkinCB24Controller(coordinator, protocol_variant=OKIN_CB24_VARIANT_OLD)
        controller.write_command = AsyncMock(side_effect=[asyncio.CancelledError(), None])

        with pytest.raises(asyncio.CancelledError):
            await controller._send_preset(OkinCB24Commands.PRESET_FLAT)

        assert controller.write_command.await_count == 2
        second_call = controller.write_command.await_args_list[1]
        assert second_call.args[0] == controller._build_command(0)

    @pytest.mark.asyncio
    async def test_default_is_old_protocol(self) -> None:
        """Default variant should use OLD protocol behavior."""
        coordinator = MagicMock()
        coordinator.address = "AA:BB:CC:DD:EE:FF"
        controller = OkinCB24Controller(coordinator)
        controller.write_command = AsyncMock()

        await controller._send_preset(OkinCB24Commands.PRESET_MEMORY_1)

        assert controller.write_command.await_count == 2
        first_call = controller.write_command.await_args_list[0]
        assert first_call == call(
            controller._build_command(OkinCB24Commands.PRESET_MEMORY_1),
            repeat_count=_PRESET_CONTINUOUS_COUNT,
            repeat_delay_ms=_PRESET_CONTINUOUS_DELAY_MS,
        )

    @pytest.mark.asyncio
    async def test_new_protocol_lights_use_discrete_packets(self) -> None:
        """CBNew profiles should use discrete light on/off commands."""
        coordinator = MagicMock()
        coordinator.address = "AA:BB:CC:DD:EE:FF"
        controller = OkinCB24Controller(coordinator, protocol_variant=OKIN_CB24_VARIANT_CB27NEW)
        controller.write_command = AsyncMock()

        await controller.lights_on()
        await controller.lights_off()

        assert controller.supports_discrete_light_control is True
        assert controller.write_command.await_args_list == [
            call(bytes([0xAA, 0x00, 0x00, 0x04, 0x01, 0x05, 0x00, 0x01, 0x00, 0x00, 0x00, 0x00])),
            call(bytes([0xAA, 0x00, 0x00, 0x04, 0x01, 0x05, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])),
        ]


class TestOkinCB24FactoryProfiles:
    """Factory tests for CB24 profile selection and override behavior."""

    @pytest.mark.asyncio
    async def test_auto_detect_cb27new_from_smartbed_name_length(self) -> None:
        """Factory should detect CB27New for smartbed names with length 18."""
        coordinator = _make_factory_coordinator()
        controller = await create_controller(
            coordinator=coordinator,
            bed_type=BED_TYPE_OKIN_CB24,
            protocol_variant=None,
            client=None,
            device_name="smartbed1234567890",
        )

        assert isinstance(controller, OkinCB24Controller)
        assert controller._protocol_variant == OKIN_CB24_VARIANT_CB27NEW
        assert controller._is_new_protocol is True

    @pytest.mark.asyncio
    async def test_auto_detect_defaults_to_old_for_non_cb27new_names(self) -> None:
        """Factory should default to CB24 legacy profile when CB27New signature is absent."""
        coordinator = _make_factory_coordinator()
        controller = await create_controller(
            coordinator=coordinator,
            bed_type=BED_TYPE_OKIN_CB24,
            protocol_variant=None,
            client=None,
            device_name="SmartBed-Not18",
        )

        assert isinstance(controller, OkinCB24Controller)
        assert controller._protocol_variant == OKIN_CB24_VARIANT_CB24
        assert controller._is_new_protocol is False
        assert controller._adaptive_preset_fallback is True

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("manufacturer_payload", "expected_variant"),
        [
            (b"AB\x08\x01\x02", OKIN_CB24_VARIANT_CB24_AB),
            (b"OK\x02\x04", OKIN_CB24_VARIANT_CB27),
            (b"DOT\x01\x02", OKIN_CB24_VARIANT_DACHENG),
            (b"DOT\x02\x01", OKIN_CB24_VARIANT_CB1221),
            (b"DOT\x03\x02", OKIN_CB24_VARIANT_CB24),
        ],
    )
    async def test_auto_detects_cb24_variant_from_manufacturer_payload(
        self,
        manufacturer_payload: bytes,
        expected_variant: str,
    ) -> None:
        """Factory should infer APK CB24 sub-profiles from manufacturer payload markers."""
        coordinator = _make_factory_coordinator()
        controller = await create_controller(
            coordinator=coordinator,
            bed_type=BED_TYPE_OKIN_CB24,
            protocol_variant=None,
            client=None,
            device_name="smartbed1234567890",
            manufacturer_data={MANUFACTURER_ID_OKIN: manufacturer_payload},
        )

        assert isinstance(controller, OkinCB24Controller)
        assert controller._protocol_variant == expected_variant
        assert controller._adaptive_preset_fallback is True

    @pytest.mark.asyncio
    async def test_unknown_manufacturer_payload_falls_back_to_name_heuristic(self) -> None:
        """Unknown OKIN payload should fall through to name-based CB27New detection."""
        coordinator = _make_factory_coordinator()
        controller = await create_controller(
            coordinator=coordinator,
            bed_type=BED_TYPE_OKIN_CB24,
            protocol_variant=None,
            client=None,
            device_name="smartbed1234567890",
            manufacturer_data={MANUFACTURER_ID_OKIN: b"\x00\x00\x00\x00"},
        )

        assert isinstance(controller, OkinCB24Controller)
        assert controller._protocol_variant == OKIN_CB24_VARIANT_CB27NEW

    @pytest.mark.asyncio
    async def test_manufacturer_payload_takes_precedence_over_cb27new_name(self) -> None:
        """Manufacturer marker-based profiles should win over CB27New name heuristic."""
        coordinator = _make_factory_coordinator()
        controller = await create_controller(
            coordinator=coordinator,
            bed_type=BED_TYPE_OKIN_CB24,
            protocol_variant=None,
            client=None,
            device_name="smartbed1234567890",
            manufacturer_data={MANUFACTURER_ID_OKIN: b"AB\x08\x01\x02"},
        )

        assert isinstance(controller, OkinCB24Controller)
        assert controller._protocol_variant == OKIN_CB24_VARIANT_CB24_AB
        assert controller._is_new_protocol is False

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("profile_variant", "is_new_protocol"),
        [
            (OKIN_CB24_VARIANT_OLD, False),
            (OKIN_CB24_VARIANT_NEW, True),
            (OKIN_CB24_VARIANT_CB24, False),
            (OKIN_CB24_VARIANT_CB27, False),
            (OKIN_CB24_VARIANT_CB24_AB, False),
            (OKIN_CB24_VARIANT_CB1221, False),
            (OKIN_CB24_VARIANT_DACHENG, False),
            (OKIN_CB24_VARIANT_CB27NEW, True),
        ],
    )
    async def test_manual_profile_override_is_respected(
        self,
        profile_variant: str,
        is_new_protocol: bool,
    ) -> None:
        """Factory should honor all explicit CB24 profile variants from APK device profiles."""
        coordinator = _make_factory_coordinator()
        controller = await create_controller(
            coordinator=coordinator,
            bed_type=BED_TYPE_OKIN_CB24,
            protocol_variant=profile_variant,
            client=None,
            device_name="smartbed1234567890",
        )

        assert isinstance(controller, OkinCB24Controller)
        assert controller._protocol_variant == profile_variant
        assert controller._is_new_protocol is is_new_protocol
        assert controller._adaptive_preset_fallback is False


class TestOkinCB24VariantValidation:
    """Validation tests for CB24 profile variants."""

    def test_all_cb24_profile_variants_are_valid(self) -> None:
        """Every CB24 variant exposed in config should validate for BED_TYPE_OKIN_CB24."""
        variants = get_variants_for_bed_type(BED_TYPE_OKIN_CB24)
        assert variants is not None

        expected_variants = [
            OKIN_CB24_VARIANT_OLD,
            OKIN_CB24_VARIANT_NEW,
            OKIN_CB24_VARIANT_CB24,
            OKIN_CB24_VARIANT_CB27,
            OKIN_CB24_VARIANT_CB24_AB,
            OKIN_CB24_VARIANT_CB1221,
            OKIN_CB24_VARIANT_DACHENG,
            OKIN_CB24_VARIANT_CB27NEW,
        ]

        for variant in expected_variants:
            assert variant in variants
            assert is_valid_variant_for_bed_type(BED_TYPE_OKIN_CB24, variant) is True
