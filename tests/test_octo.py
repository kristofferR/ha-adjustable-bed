"""Tests for Octo bed controllers."""

from __future__ import annotations

from typing import cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.components.light import ATTR_RGBW_COLOR, ColorMode
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed.beds.octo import (
    OCTO_FEATURE_END,
    OCTO_FEATURE_LIGHT,
    OCTO_FEATURE_LIGHT_RGBWI,
    OCTO_MOTOR_HEAD,
    OctoController,
    OctoStar2Controller,
)
from custom_components.adjustable_bed.light import AdjustableBedLight, LIGHT_DESCRIPTION
from custom_components.adjustable_bed.const import (
    BED_TYPE_OCTO,
    CONF_BED_TYPE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_HAS_MASSAGE,
    CONF_MOTOR_COUNT,
    CONF_MOTOR_PULSE_COUNT,
    CONF_MOTOR_PULSE_DELAY_MS,
    CONF_OCTO_PIN,
    CONF_PREFERRED_ADAPTER,
    CONF_PROTOCOL_VARIANT,
    DOMAIN,
    OCTO_CHAR_UUID,
    OCTO_VARIANT_STANDARD,
    OCTO_VARIANT_STAR2,
)
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator


@pytest.fixture
def mock_octo_config_entry_data() -> dict:
    """Return mock config entry data for an Octo bed."""
    return {
        CONF_ADDRESS: "AA:BB:CC:DD:EE:FF",
        CONF_NAME: "Octo Test Bed",
        CONF_BED_TYPE: BED_TYPE_OCTO,
        CONF_MOTOR_COUNT: 2,
        CONF_HAS_MASSAGE: False,
        CONF_DISABLE_ANGLE_SENSING: True,
        CONF_PREFERRED_ADAPTER: "auto",
        CONF_PROTOCOL_VARIANT: OCTO_VARIANT_STANDARD,
        CONF_OCTO_PIN: "1234",
        CONF_MOTOR_PULSE_COUNT: 1,
        CONF_MOTOR_PULSE_DELAY_MS: 1,
    }


@pytest.fixture
def mock_octo_config_entry(
    hass: HomeAssistant, mock_octo_config_entry_data: dict
) -> MockConfigEntry:
    """Return a mock config entry for an Octo bed."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Octo Test Bed",
        data=mock_octo_config_entry_data,
        unique_id="AA:BB:CC:DD:EE:FF",
        entry_id="octo_test_entry",
    )
    entry.add_to_hass(hass)
    return entry


@pytest.fixture
def mock_octo_star2_config_entry_data(mock_octo_config_entry_data: dict) -> dict:
    """Return mock config entry data for an Octo Star2 bed."""
    data = dict(mock_octo_config_entry_data)
    data[CONF_PROTOCOL_VARIANT] = OCTO_VARIANT_STAR2
    data[CONF_OCTO_PIN] = ""
    return data


@pytest.fixture
def mock_octo_star2_config_entry(
    hass: HomeAssistant, mock_octo_star2_config_entry_data: dict
) -> MockConfigEntry:
    """Return a mock config entry for an Octo Star2 bed."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Octo Star2 Test Bed",
        data=mock_octo_star2_config_entry_data,
        unique_id="AA:BB:CC:DD:EE:11",
        entry_id="octo_star2_test_entry",
    )
    entry.add_to_hass(hass)
    return entry


class TestOctoVariantSelection:
    """Test Octo variant selection in controller creation."""

    async def test_standard_variant_uses_octo_controller(
        self,
        hass: HomeAssistant,
        mock_octo_config_entry,
        mock_coordinator_connected,
    ):
        """Standard variant should create OctoController."""
        coordinator = AdjustableBedCoordinator(hass, mock_octo_config_entry)
        await coordinator.async_connect()

        assert isinstance(coordinator.controller, OctoController)

    async def test_star2_variant_uses_octo_star2_controller(
        self,
        hass: HomeAssistant,
        mock_octo_star2_config_entry,
        mock_coordinator_connected,
    ):
        """Star2 variant should create OctoStar2Controller."""
        coordinator = AdjustableBedCoordinator(hass, mock_octo_star2_config_entry)
        await coordinator.async_connect()

        assert isinstance(coordinator.controller, OctoStar2Controller)


class TestOctoPinAuth:
    """Test Octo PIN authentication flow."""

    async def test_send_pin_writes_auth_packet_when_pin_required(
        self,
        hass: HomeAssistant,
        mock_octo_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """send_pin should write PIN packet when bed is PIN-locked."""
        coordinator = AdjustableBedCoordinator(hass, mock_octo_config_entry)
        await coordinator.async_connect()

        controller = cast(OctoController, coordinator.controller)
        mock_bleak_client.write_gatt_char.reset_mock()

        controller._has_pin = True
        controller._pin_locked = True

        await controller.send_pin()

        expected_packet = controller._build_packet([0x20, 0x43], [1, 2, 3, 4])
        mock_bleak_client.write_gatt_char.assert_called_once_with(
            OCTO_CHAR_UUID,
            expected_packet,
            response=False,
        )

    async def test_send_pin_skips_when_bed_not_locked(
        self,
        hass: HomeAssistant,
        mock_octo_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """send_pin should skip writes when feature discovery shows unlocked bed."""
        coordinator = AdjustableBedCoordinator(hass, mock_octo_config_entry)
        await coordinator.async_connect()

        controller = cast(OctoController, coordinator.controller)
        mock_bleak_client.write_gatt_char.reset_mock()

        controller._has_pin = True
        controller._pin_locked = False

        await controller.send_pin()

        mock_bleak_client.write_gatt_char.assert_not_called()


class TestOctoCommands:
    """Test Octo motor, light, and stop commands."""

    async def test_move_head_up_sends_move_then_stop(
        self,
        hass: HomeAssistant,
        mock_octo_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """move_head_up should send movement packet followed by stop packet."""
        coordinator = AdjustableBedCoordinator(hass, mock_octo_config_entry)
        await coordinator.async_connect()

        controller = cast(OctoController, coordinator.controller)
        mock_bleak_client.write_gatt_char.reset_mock()

        await controller.move_head_up()

        calls = mock_bleak_client.write_gatt_char.call_args_list
        assert len(calls) == 2

        move_packet = controller._build_packet([0x02, 0x70], [OCTO_MOTOR_HEAD])
        stop_packet = controller._build_packet([0x02, 0x73])

        assert calls[0][0][1] == move_packet
        assert calls[-1][0][1] == stop_packet

    async def test_move_with_stop_sends_stop_on_error(
        self,
        hass: HomeAssistant,
        mock_octo_config_entry,
        mock_coordinator_connected,
    ):
        """_move_with_stop should always call _stop_motors in cleanup."""
        coordinator = AdjustableBedCoordinator(hass, mock_octo_config_entry)
        await coordinator.async_connect()
        controller = cast(OctoController, coordinator.controller)

        with (
            patch.object(controller, "_move_motor", new_callable=AsyncMock) as mock_move,
            patch.object(controller, "_stop_motors", new_callable=AsyncMock) as mock_stop,
        ):
            mock_move.side_effect = RuntimeError("move failed")
            with pytest.raises(RuntimeError, match="move failed"):
                await controller._octo_move_with_stop(OCTO_MOTOR_HEAD, "up")

            mock_stop.assert_awaited_once()

    async def test_lights_on_off_send_expected_packets(
        self,
        hass: HomeAssistant,
        mock_octo_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """lights_on/lights_off should send the expected feature-write packets."""
        coordinator = AdjustableBedCoordinator(hass, mock_octo_config_entry)
        await coordinator.async_connect()

        controller = cast(OctoController, coordinator.controller)

        mock_bleak_client.write_gatt_char.reset_mock()
        await controller.lights_on()
        expected_on = controller._build_packet(
            [0x20, 0x72],
            [0x00, 0x01, 0x02, 0x00, 0x01, 0x01, 0x01, 0x01],
        )
        mock_bleak_client.write_gatt_char.assert_called_once_with(
            OCTO_CHAR_UUID,
            expected_on,
            response=False,
        )

        mock_bleak_client.write_gatt_char.reset_mock()
        await controller.lights_off()
        expected_off = controller._build_packet(
            [0x20, 0x72],
            [0x00, 0x01, 0x02, 0x00, 0x01, 0x01, 0x01, 0x00],
        )
        mock_bleak_client.write_gatt_char.assert_called_once_with(
            OCTO_CHAR_UUID,
            expected_off,
            response=False,
        )

    async def test_stop_all_sends_stop_packet(
        self,
        hass: HomeAssistant,
        mock_octo_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """stop_all should send the stop command packet."""
        coordinator = AdjustableBedCoordinator(hass, mock_octo_config_entry)
        await coordinator.async_connect()

        controller = cast(OctoController, coordinator.controller)
        mock_bleak_client.write_gatt_char.reset_mock()

        await controller.stop_all()

        expected_stop = controller._build_packet([0x02, 0x73])
        mock_bleak_client.write_gatt_char.assert_called_once_with(
            OCTO_CHAR_UUID,
            expected_stop,
            response=False,
        )


class TestOctoRGBWIFeatureDetection:
    """Test OCTO RGBWI capability detection during feature discovery."""

    def _make_feature_data(
        self,
        feature_id: int,
        value: list[int],
        *,
        value_type: int = 0x05,
        skip_length: int = 1,
        skip_data: list[int] | None = None,
    ) -> list[int]:
        """Build feature response data matching _extract_feature_value_pair format.

        Format: [cap_id(3), flag(1), skip_length(1), skip_data(N), valueType(1), value(...)]
        """
        if skip_data is None:
            skip_data = [0x01] * skip_length
        return [
            (feature_id >> 16) & 0xFF,
            (feature_id >> 8) & 0xFF,
            feature_id & 0xFF,
            0x00,  # flag
            len(skip_data),
            *skip_data,
            value_type,
            *value,
        ]

    async def test_rgbwi_feature_sets_has_rgbwi(
        self,
        hass: HomeAssistant,
        mock_octo_config_entry,
        mock_coordinator_connected,
    ):
        """CAP_LIGHT_RGBWI (0x000104) should set _has_rgbwi to True."""
        coordinator = AdjustableBedCoordinator(hass, mock_octo_config_entry)
        await coordinator.async_connect()
        controller = cast(OctoController, coordinator.controller)

        assert controller._has_rgbwi is False

        data = self._make_feature_data(
            OCTO_FEATURE_LIGHT_RGBWI,
            [255, 0, 0, 128, 200],  # R, G, B, W, I
            value_type=0x05,
        )
        controller._handle_feature_response(data)

        assert controller._has_rgbwi is True

    async def test_rgbwi_feature_stores_value_type(
        self,
        hass: HomeAssistant,
        mock_octo_config_entry,
        mock_coordinator_connected,
    ):
        """RGBWI feature should store the valueType byte from the response."""
        coordinator = AdjustableBedCoordinator(hass, mock_octo_config_entry)
        await coordinator.async_connect()
        controller = cast(OctoController, coordinator.controller)

        assert controller._rgbwi_value_type is None

        data = self._make_feature_data(
            OCTO_FEATURE_LIGHT_RGBWI,
            [255, 255, 255, 255, 255],
            value_type=0x07,
        )
        controller._handle_feature_response(data)

        assert controller._rgbwi_value_type == 0x07

    async def test_no_rgbwi_feature_keeps_has_rgbwi_false(
        self,
        hass: HomeAssistant,
        mock_octo_config_entry,
        mock_coordinator_connected,
    ):
        """Only CAP_LIGHT (not RGBWI) should leave _has_rgbwi as False."""
        coordinator = AdjustableBedCoordinator(hass, mock_octo_config_entry)
        await coordinator.async_connect()
        controller = cast(OctoController, coordinator.controller)

        # Send only basic light feature
        data = self._make_feature_data(
            OCTO_FEATURE_LIGHT,
            [0x01],
            value_type=0x01,
        )
        controller._handle_feature_response(data)

        assert controller._has_rgbwi is False
        assert controller._has_lights is True

    async def test_rgbwi_properties_before_discovery(
        self,
        hass: HomeAssistant,
        mock_octo_config_entry,
        mock_coordinator_connected,
    ):
        """RGBWI properties should return correct defaults before feature discovery."""
        coordinator = AdjustableBedCoordinator(hass, mock_octo_config_entry)
        await coordinator.async_connect()
        controller = cast(OctoController, coordinator.controller)

        assert controller.supports_light_color_control is False
        assert controller.supported_color_mode is None
        assert controller.default_light_rgb_color is None

    async def test_rgbwi_properties_after_discovery(
        self,
        hass: HomeAssistant,
        mock_octo_config_entry,
        mock_coordinator_connected,
    ):
        """RGBWI properties should reflect RGBWI support after feature detection."""
        coordinator = AdjustableBedCoordinator(hass, mock_octo_config_entry)
        await coordinator.async_connect()
        controller = cast(OctoController, coordinator.controller)

        controller._has_rgbwi = True
        controller._rgbwi_value_type = 0x05

        assert controller.supports_light_color_control is True
        assert controller.supported_color_mode == "rgbw"
        assert controller.default_light_rgb_color == (255, 255, 255)
        assert controller.supports_explicit_light_on_control is True

    async def test_star2_has_no_rgbwi_support(
        self,
        hass: HomeAssistant,
        mock_octo_star2_config_entry,
        mock_coordinator_connected,
    ):
        """OctoStar2Controller should not have RGBWI support."""
        coordinator = AdjustableBedCoordinator(hass, mock_octo_star2_config_entry)
        await coordinator.async_connect()
        controller = cast(OctoStar2Controller, coordinator.controller)

        assert controller.supports_light_color_control is False
        assert controller.supported_color_mode is None

    async def test_discover_features_resets_rgbwi_state(
        self,
        hass: HomeAssistant,
        mock_octo_config_entry,
        mock_coordinator_connected,
    ):
        """discover_features should reset RGBWI state before requesting features."""
        coordinator = AdjustableBedCoordinator(hass, mock_octo_config_entry)
        await coordinator.async_connect()
        controller = cast(OctoController, coordinator.controller)

        # Pre-set RGBWI state
        controller._has_rgbwi = True
        controller._rgbwi_value_type = 0x07

        # discover_features will time out (no real BLE), but should reset state first
        await controller.discover_features()

        # After timeout, RGBWI state should be reset (not re-discovered without response)
        assert controller._has_rgbwi is False
        assert controller._rgbwi_value_type is None


class TestOctoRGBWICommands:
    """Test OCTO RGBWI set_light_color_rgbw command output."""

    async def test_set_light_color_rgbw_sends_expected_packet(
        self,
        hass: HomeAssistant,
        mock_octo_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """set_light_color_rgbw should send SYSTEM_SET_CAPS packet with RGBWI data."""
        coordinator = AdjustableBedCoordinator(hass, mock_octo_config_entry)
        await coordinator.async_connect()

        controller = cast(OctoController, coordinator.controller)
        controller._has_rgbwi = True
        controller._rgbwi_value_type = 0x05

        mock_bleak_client.write_gatt_char.reset_mock()
        await controller.set_light_color_rgbw((255, 0, 128, 64))

        expected_packet = controller._build_packet(
            [0x20, 0x72],
            [0x00, 0x01, 0x04, 0x00, 0x01, 0x01, 0x05, 255, 0, 128, 64, 255],
        )
        mock_bleak_client.write_gatt_char.assert_called_once_with(
            OCTO_CHAR_UUID,
            expected_packet,
            response=False,
        )

    async def test_set_light_color_rgbw_uses_fallback_value_type(
        self,
        hass: HomeAssistant,
        mock_octo_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """set_light_color_rgbw should fall back to 0x05 when discovery hasn't happened."""
        coordinator = AdjustableBedCoordinator(hass, mock_octo_config_entry)
        await coordinator.async_connect()

        controller = cast(OctoController, coordinator.controller)
        controller._has_rgbwi = True
        # Leave _rgbwi_value_type as None (no discovery)

        mock_bleak_client.write_gatt_char.reset_mock()
        await controller.set_light_color_rgbw((100, 200, 50, 150))

        expected_packet = controller._build_packet(
            [0x20, 0x72],
            [0x00, 0x01, 0x04, 0x00, 0x01, 0x01, 0x05, 100, 200, 50, 150, 255],
        )
        mock_bleak_client.write_gatt_char.assert_called_once_with(
            OCTO_CHAR_UUID,
            expected_packet,
            response=False,
        )

    async def test_set_light_color_rgbw_preserves_discovered_value_type(
        self,
        hass: HomeAssistant,
        mock_octo_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """set_light_color_rgbw should use the valueType from feature discovery."""
        coordinator = AdjustableBedCoordinator(hass, mock_octo_config_entry)
        await coordinator.async_connect()

        controller = cast(OctoController, coordinator.controller)
        controller._has_rgbwi = True
        controller._rgbwi_value_type = 0x0A  # Non-default valueType

        mock_bleak_client.write_gatt_char.reset_mock()
        await controller.set_light_color_rgbw((0, 0, 0, 0))

        expected_packet = controller._build_packet(
            [0x20, 0x72],
            [0x00, 0x01, 0x04, 0x00, 0x01, 0x01, 0x0A, 0, 0, 0, 0, 255],
        )
        mock_bleak_client.write_gatt_char.assert_called_once_with(
            OCTO_CHAR_UUID,
            expected_packet,
            response=False,
        )

    async def test_set_light_color_rgbw_intensity_always_255(
        self,
        hass: HomeAssistant,
        mock_octo_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Intensity byte should always be 255 in RGBWI packets."""
        coordinator = AdjustableBedCoordinator(hass, mock_octo_config_entry)
        await coordinator.async_connect()

        controller = cast(OctoController, coordinator.controller)
        controller._has_rgbwi = True
        controller._rgbwi_value_type = 0x05

        mock_bleak_client.write_gatt_char.reset_mock()
        await controller.set_light_color_rgbw((10, 20, 30, 40))

        # Extract the data portion from the built packet
        call_args = mock_bleak_client.write_gatt_char.call_args
        sent_packet = call_args[0][1]

        # The last data byte before the end marker should be the intensity (255)
        # Rebuild to verify the data field includes intensity=255
        expected_packet = controller._build_packet(
            [0x20, 0x72],
            [0x00, 0x01, 0x04, 0x00, 0x01, 0x01, 0x05, 10, 20, 30, 40, 255],
        )
        assert sent_packet == expected_packet


class TestOctoRGBWIFeatureValuePair:
    """Test _extract_feature_value_pair with valueType extraction."""

    async def test_extract_returns_value_type(
        self,
        hass: HomeAssistant,
        mock_octo_config_entry,
        mock_coordinator_connected,
    ):
        """_extract_feature_value_pair should return the valueType byte."""
        coordinator = AdjustableBedCoordinator(hass, mock_octo_config_entry)
        await coordinator.async_connect()
        controller = cast(OctoController, coordinator.controller)

        # Build data: feature_id=0x000104, flag=0x00, skip_len=1, skip=[0x01], valueType=0x05, value=[R,G,B,W,I]
        data = [0x00, 0x01, 0x04, 0x00, 0x01, 0x01, 0x05, 255, 128, 64, 200, 100]
        result = controller._extract_feature_value_pair(data)

        assert result is not None
        feature_id, value, value_type = result
        assert feature_id == 0x000104
        assert value == [255, 128, 64, 200, 100]
        assert value_type == 0x05

    async def test_extract_returns_none_for_short_data(
        self,
        hass: HomeAssistant,
        mock_octo_config_entry,
        mock_coordinator_connected,
    ):
        """_extract_feature_value_pair should return None for data too short."""
        coordinator = AdjustableBedCoordinator(hass, mock_octo_config_entry)
        await coordinator.async_connect()
        controller = cast(OctoController, coordinator.controller)

        result = controller._extract_feature_value_pair([0x00, 0x01])
        assert result is None

    async def test_extract_end_sentinel(
        self,
        hass: HomeAssistant,
        mock_octo_config_entry,
        mock_coordinator_connected,
    ):
        """_extract_feature_value_pair should parse the end sentinel correctly."""
        coordinator = AdjustableBedCoordinator(hass, mock_octo_config_entry)
        await coordinator.async_connect()
        controller = cast(OctoController, coordinator.controller)

        # End sentinel: 0xFFFFFF
        data = [0xFF, 0xFF, 0xFF, 0x00, 0x00, 0x00]
        result = controller._extract_feature_value_pair(data)

        assert result is not None
        feature_id, value, value_type = result
        assert feature_id == OCTO_FEATURE_END


class TestOctoRGBWILightEntity:
    """Test light entity behavior with OCTO RGBWI color mode."""

    async def test_light_entity_uses_rgbw_color_mode(
        self,
        hass: HomeAssistant,
        mock_octo_config_entry,
        mock_coordinator_connected,
    ):
        """Light entity should use ColorMode.RGBW for RGBWI controllers."""
        coordinator = AdjustableBedCoordinator(hass, mock_octo_config_entry)
        await coordinator.async_connect()
        controller = cast(OctoController, coordinator.controller)
        controller._has_rgbwi = True
        controller._rgbwi_value_type = 0x05

        light = AdjustableBedLight(coordinator, LIGHT_DESCRIPTION)

        assert light.color_mode == ColorMode.RGBW
        assert light.supported_color_modes == {ColorMode.RGBW}

    async def test_light_entity_default_rgbw_color(
        self,
        hass: HomeAssistant,
        mock_octo_config_entry,
        mock_coordinator_connected,
    ):
        """Light entity should have a default RGBW color for RGBWI controllers."""
        coordinator = AdjustableBedCoordinator(hass, mock_octo_config_entry)
        await coordinator.async_connect()
        controller = cast(OctoController, coordinator.controller)
        controller._has_rgbwi = True
        controller._rgbwi_value_type = 0x05

        light = AdjustableBedLight(coordinator, LIGHT_DESCRIPTION)

        assert light.rgbw_color == (255, 255, 255, 255)

    async def test_light_entity_without_rgbwi_uses_rgb(
        self,
        hass: HomeAssistant,
        mock_octo_config_entry,
        mock_coordinator_connected,
    ):
        """Light entity should fall back to ColorMode.RGB without RGBWI support."""
        coordinator = AdjustableBedCoordinator(hass, mock_octo_config_entry)
        await coordinator.async_connect()
        controller = cast(OctoController, coordinator.controller)
        # _has_rgbwi defaults to False

        assert controller.supported_color_mode is None

    async def test_light_entity_turn_on_with_rgbw_color(
        self,
        hass: HomeAssistant,
        mock_octo_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Turning on with ATTR_RGBW_COLOR should call set_light_color_rgbw."""
        coordinator = AdjustableBedCoordinator(hass, mock_octo_config_entry)
        await coordinator.async_connect()
        controller = cast(OctoController, coordinator.controller)
        controller._has_rgbwi = True
        controller._rgbwi_value_type = 0x05

        light = AdjustableBedLight(coordinator, LIGHT_DESCRIPTION)

        mock_bleak_client.write_gatt_char.reset_mock()
        with patch.object(light, "async_write_ha_state"):
            await light.async_turn_on(**{ATTR_RGBW_COLOR: (100, 150, 200, 50)})

        # Verify the correct RGBWI packet was sent
        expected_packet = controller._build_packet(
            [0x20, 0x72],
            [0x00, 0x01, 0x04, 0x00, 0x01, 0x01, 0x05, 100, 150, 200, 50, 255],
        )

        # Should have called lights_on() first, then set_light_color_rgbw()
        calls = mock_bleak_client.write_gatt_char.call_args_list
        assert len(calls) == 2  # lights_on + set_light_color_rgbw

        # The RGBWI packet is the second call
        assert calls[1][0][1] == expected_packet

        assert light.is_on is True
        assert light.rgbw_color == (100, 150, 200, 50)

    async def test_light_entity_turn_on_uses_previous_rgbw_color(
        self,
        hass: HomeAssistant,
        mock_octo_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Turning on without color should use previously set RGBW color."""
        coordinator = AdjustableBedCoordinator(hass, mock_octo_config_entry)
        await coordinator.async_connect()
        controller = cast(OctoController, coordinator.controller)
        controller._has_rgbwi = True
        controller._rgbwi_value_type = 0x05

        light = AdjustableBedLight(coordinator, LIGHT_DESCRIPTION)
        # Set a specific color first
        light._attr_rgbw_color = (10, 20, 30, 40)

        mock_bleak_client.write_gatt_char.reset_mock()
        with patch.object(light, "async_write_ha_state"):
            await light.async_turn_on()

        # Should use the stored RGBW color
        expected_packet = controller._build_packet(
            [0x20, 0x72],
            [0x00, 0x01, 0x04, 0x00, 0x01, 0x01, 0x05, 10, 20, 30, 40, 255],
        )
        calls = mock_bleak_client.write_gatt_char.call_args_list
        assert calls[-1][0][1] == expected_packet

    async def test_light_entity_turn_off(
        self,
        hass: HomeAssistant,
        mock_octo_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Turning off should send lights_off command."""
        coordinator = AdjustableBedCoordinator(hass, mock_octo_config_entry)
        await coordinator.async_connect()
        controller = cast(OctoController, coordinator.controller)
        controller._has_rgbwi = True
        controller._has_lights = True  # Needed for supports_discrete_light_control

        light = AdjustableBedLight(coordinator, LIGHT_DESCRIPTION)
        light._attr_is_on = True  # Pretend it's on

        mock_bleak_client.write_gatt_char.reset_mock()
        with patch.object(light, "async_write_ha_state"):
            await light.async_turn_off()

        # Should have called lights_off()
        expected_off = controller._build_packet(
            [0x20, 0x72],
            [0x00, 0x01, 0x02, 0x00, 0x01, 0x01, 0x01, 0x00],
        )
        mock_bleak_client.write_gatt_char.assert_called_once_with(
            OCTO_CHAR_UUID,
            expected_off,
            response=False,
        )
        assert light.is_on is False
