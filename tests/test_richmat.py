"""Tests for Richmat bed controller."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed.beds.richmat import (
    RICHMAT_LEGACY_RGB_LIGHT_TIMER_OPTIONS,
    RichmatController,
)
from custom_components.adjustable_bed.button import BUTTON_DESCRIPTIONS, _should_add_button
from custom_components.adjustable_bed.const import (
    BED_TYPE_RICHMAT,
    CONF_BED_TYPE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_HAS_MASSAGE,
    CONF_MOTOR_COUNT,
    CONF_PREFERRED_ADAPTER,
    CONF_PROTOCOL_VARIANT,
    CONF_RICHMAT_REMOTE,
    DOMAIN,
    RICHMAT_NORDIC_CHAR_UUID,
    RICHMAT_REMOTE_GGRM,
    RICHMAT_REMOTE_LP_QRRM,
    RICHMAT_VARIANT_NORDIC,
    get_richmat_features,
    get_richmat_motor_count,
    resolve_richmat_remote_code,
)
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator


@pytest.fixture
def mock_richmat_config_entry_data() -> dict:
    """Return mock config entry data for Richmat bed."""
    return {
        CONF_ADDRESS: "AA:BB:CC:DD:EE:FF",
        CONF_NAME: "Richmat Test Bed",
        CONF_BED_TYPE: BED_TYPE_RICHMAT,
        CONF_MOTOR_COUNT: 2,
        CONF_HAS_MASSAGE: True,
        CONF_DISABLE_ANGLE_SENSING: True,
        CONF_PREFERRED_ADAPTER: "auto",
        CONF_PROTOCOL_VARIANT: RICHMAT_VARIANT_NORDIC,
    }


@pytest.fixture
def mock_richmat_config_entry(
    hass: HomeAssistant, mock_richmat_config_entry_data: dict
) -> MockConfigEntry:
    """Return a mock config entry for Richmat bed."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Richmat Test Bed",
        data=mock_richmat_config_entry_data,
        unique_id="AA:BB:CC:DD:EE:FF",
        entry_id="richmat_test_entry",
    )
    entry.add_to_hass(hass)
    return entry


class TestRichmatController:
    """Test Richmat controller."""

    async def test_control_characteristic_uuid_nordic(
        self,
        hass: HomeAssistant,
        mock_richmat_config_entry,
        mock_coordinator_connected,
    ):
        """Test controller reports Nordic characteristic UUID by default."""
        coordinator = AdjustableBedCoordinator(hass, mock_richmat_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.control_characteristic_uuid == RICHMAT_NORDIC_CHAR_UUID

    async def test_wilinke_qrrm_uses_compat_stop_byte(
        self,
        hass: HomeAssistant,
        mock_richmat_config_entry,
        mock_coordinator_connected,
    ):
        """WiLinke QRRM remotes should use compatibility stop byte 0x5E."""
        coordinator = AdjustableBedCoordinator(hass, mock_richmat_config_entry)
        await coordinator.async_connect()

        controller = RichmatController(coordinator, is_wilinke=True, remote_code="qrrm")
        stop_command = controller._build_stop_command()

        assert len(stop_command) == 5
        assert stop_command[3] == 0x5E

    async def test_wilinke_non_compat_remote_uses_standard_stop_byte(
        self,
        hass: HomeAssistant,
        mock_richmat_config_entry,
        mock_coordinator_connected,
    ):
        """WiLinke non-compat remotes should keep standard stop byte 0x6E."""
        coordinator = AdjustableBedCoordinator(hass, mock_richmat_config_entry)
        await coordinator.async_connect()

        controller = RichmatController(coordinator, is_wilinke=True, remote_code="v1rm")
        stop_command = controller._build_stop_command()

        assert len(stop_command) == 5
        assert stop_command[3] == 0x6E

    async def test_write_command_not_connected(
        self,
        hass: HomeAssistant,
        mock_richmat_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test writing command when not connected raises error."""
        coordinator = AdjustableBedCoordinator(hass, mock_richmat_config_entry)
        await coordinator.async_connect()

        mock_bleak_client.is_connected = False

        with pytest.raises(ConnectionError):
            await coordinator.controller.write_command(
                coordinator.controller._build_command(0x6E)
            )


class TestRichmatMovement:
    """Test Richmat movement commands."""

    async def test_move_head_feet_up_sends_combined_command(
        self,
        hass: HomeAssistant,
        mock_richmat_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Head+feet must send the single combined command, not two motor commands."""
        coordinator = AdjustableBedCoordinator(hass, mock_richmat_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.move_head_feet_up()

        calls = mock_bleak_client.write_gatt_char.call_args_list
        expected = coordinator.controller._build_command(0x29)
        assert calls[0][0][1] == expected
        assert calls[-1][0][1] == coordinator.controller._build_command(0x6E)

    async def test_move_head_feet_down_sends_combined_command(
        self,
        hass: HomeAssistant,
        mock_richmat_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Head+feet down uses the paired combined command byte."""
        coordinator = AdjustableBedCoordinator(hass, mock_richmat_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.move_head_feet_down()

        calls = mock_bleak_client.write_gatt_char.call_args_list
        expected = coordinator.controller._build_command(0x2A)
        assert calls[0][0][1] == expected

    async def test_wilinke_qrrm_move_stop_uses_compat_byte(
        self,
        hass: HomeAssistant,
        mock_richmat_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """move_head_stop should use 0x5E for WiLinke QRRM compatibility."""
        coordinator = AdjustableBedCoordinator(hass, mock_richmat_config_entry)
        await coordinator.async_connect()

        controller = RichmatController(coordinator, is_wilinke=True, remote_code="qrrm")
        mock_bleak_client.write_gatt_char.reset_mock()

        await controller.move_head_stop()

        calls = mock_bleak_client.write_gatt_char.call_args_list
        assert len(calls) == 1
        sent_command = calls[0][0][1]
        assert sent_command[3] == 0x5E

    async def test_has_lumbar_support(
        self,
        hass: HomeAssistant,
        mock_richmat_config_entry,
        mock_coordinator_connected,
    ):
        """Test Richmat controller reports lumbar support with default 'auto' remote."""
        coordinator = AdjustableBedCoordinator(hass, mock_richmat_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.has_lumbar_support is True

    async def test_has_pillow_support(
        self,
        hass: HomeAssistant,
        mock_richmat_config_entry,
        mock_coordinator_connected,
    ):
        """Test Richmat controller reports pillow support with default 'auto' remote."""
        coordinator = AdjustableBedCoordinator(hass, mock_richmat_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.has_pillow_support is True


class TestRichmatFeatureDetection:
    """Test Richmat remote-based feature detection."""

    def test_v1rm_no_pillow_no_lumbar(self):
        """Test V1RM remote has no pillow or lumbar support."""
        from custom_components.adjustable_bed.beds.richmat import RichmatController

        # Create controller with V1RM remote code
        coordinator = MagicMock()
        controller = RichmatController(coordinator, is_wilinke=False, remote_code="V1RM")

        assert controller.has_pillow_support is False
        assert controller.has_lumbar_support is False
        assert controller.supports_preset_zero_g is True
        assert controller.supports_preset_tv is False

    def test_190_0055_pillow_no_lumbar(self):
        """Test 190-0055 remote has pillow but no lumbar support."""
        from custom_components.adjustable_bed.beds.richmat import RichmatController

        coordinator = MagicMock()
        controller = RichmatController(coordinator, is_wilinke=False, remote_code="190-0055")

        assert controller.has_pillow_support is True
        assert controller.has_lumbar_support is False

    def test_virm_full_features(self):
        """Test VIRM remote has full feature support."""
        from custom_components.adjustable_bed.beds.richmat import RichmatController

        coordinator = MagicMock()
        controller = RichmatController(coordinator, is_wilinke=False, remote_code="VIRM")

        assert controller.has_pillow_support is True
        assert controller.has_lumbar_support is True
        assert controller.supports_preset_zero_g is True
        assert controller.supports_preset_anti_snore is True

    def test_bt6500_profile_restores_missing_presets(self):
        """BT6500 should expose the preset set reported in issue #194."""
        coordinator = MagicMock()
        controller = RichmatController(coordinator, is_wilinke=True, remote_code="BT6500")

        assert controller.supports_preset_zero_g is True
        assert controller.supports_preset_anti_snore is True
        assert controller.supports_preset_tv is True
        assert controller.supports_memory_presets is True
        assert controller.memory_slot_count == 2
        assert controller.supports_lights is True
        assert controller.has_pillow_support is True
        assert controller.has_lumbar_support is True

    def test_lp_qrrm_profile_exposes_reported_presets_only(self):
        """L&P QRRM should expose the four-position surface from issue #504."""
        coordinator = MagicMock()
        controller = RichmatController(
            coordinator,
            is_wilinke=True,
            remote_code=RICHMAT_REMOTE_LP_QRRM,
        )

        assert controller.supports_preset_flat is True
        assert controller.supports_preset_zero_g is True
        assert controller.supports_memory_presets is True
        assert controller.memory_slot_count == 2
        assert controller.memory_slot_names == ("Custom 1", "Custom 2")
        assert controller.supports_memory_programming is False
        assert controller.supports_preset_anti_snore is False
        assert controller.supports_preset_tv is False
        assert controller.supports_preset_lounge is False
        assert controller.supports_lights is False
        assert controller.has_pillow_support is False
        assert controller.has_lumbar_support is False

    def test_lp_qrrm_profile_uses_recovered_wilinke_frames(self):
        """L&P commands should match the clean-room recovered app packets."""
        coordinator = MagicMock()
        controller = RichmatController(
            coordinator,
            is_wilinke=True,
            remote_code=RICHMAT_REMOTE_LP_QRRM,
        )

        assert controller._build_command(0x31) == bytes.fromhex(
            "6e010031a0"
        )
        assert controller._build_command(0x45) == bytes.fromhex(
            "6e010045b4"
        )
        assert controller._build_command(0x2E) == bytes.fromhex(
            "6e01002e9d"
        )
        assert controller._build_command(0x2F) == bytes.fromhex(
            "6e01002f9e"
        )
        assert controller._build_stop_command() == bytes.fromhex("6e01006edd")

    def test_resolve_bt6500_title_alias_from_qrrm_family(self):
        """BT6500 titles should resolve away from the generic QRRM profile."""
        assert (
            resolve_richmat_remote_code(
                "qrrm",
                entry_title="BedTech BT6500",
                device_name="QRRM141291",
            )
            == "bt6500"
        )

    def test_richmat_motor_count_ignores_pillow_and_lumbar_axes(self):
        """Richmat motor_count should only track the primary head/feet axes."""
        features = get_richmat_features("BT6500")

        assert get_richmat_motor_count(features) == 2

    async def test_bt6500_motor_layout_avoids_back_and_legs_duplicates(
        self,
        hass: HomeAssistant,
        mock_richmat_config_entry_data: dict,
        mock_coordinator_connected,
    ):
        """Richmat BT6500 should expose head/feet/pillow/lumbar only."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            title="BedTech BT6500",
            data={
                **mock_richmat_config_entry_data,
                CONF_PROTOCOL_VARIANT: "wilinke",
                CONF_MOTOR_COUNT: 4,
                CONF_RICHMAT_REMOTE: "qrrm",
            },
            unique_id="57:4C:62:B0:EF:3D",
            entry_id="richmat_bt6500_entry",
        )
        entry.add_to_hass(hass)

        coordinator = AdjustableBedCoordinator(hass, entry)
        await coordinator.async_connect()
        controller = coordinator.controller

        assert coordinator.motor_count == 2
        # The BT6500 remote surface has no combined head+feet button, so the
        # combined step must not appear even though both motors are present.
        assert [spec.key for spec in controller.motor_control_specs] == [
            "head",
            "feet",
            "pillow",
            "lumbar",
        ]
        assert controller.stale_motor_entity_keys == {
            "back",
            "legs",
            "pillow",
            "lumbar",
            "head_feet",
        }

    def test_head_only_remote_omits_combined_head_feet_control(self):
        """The combined step needs both axes, so a head-only remote must not get it."""
        coordinator = MagicMock()
        controller = RichmatController(coordinator, is_wilinke=True, remote_code="aarn")

        assert "head_feet" not in [spec.key for spec in controller.motor_control_specs]

    def test_remote_with_combined_button_exposes_head_feet_control(self):
        """twrm binds a button to 0x29/0x2A, so it gets the combined cover."""
        coordinator = MagicMock()
        controller = RichmatController(coordinator, is_wilinke=True, remote_code="twrm")

        assert "head_feet" in [spec.key for spec in controller.motor_control_specs]

    def test_remote_without_combined_button_omits_head_feet_control(self):
        """virm has both motors but no combined button on its remote surface."""
        coordinator = MagicMock()
        controller = RichmatController(coordinator, is_wilinke=True, remote_code="virm")

        assert "head_feet" not in [spec.key for spec in controller.motor_control_specs]

    def test_auto_remote_omits_head_feet_control(self):
        """Auto is the fallback for unidentified beds, so it does not get the combined step."""
        coordinator = MagicMock()
        controller = RichmatController(coordinator, is_wilinke=True, remote_code="auto")

        assert "head_feet" not in [spec.key for spec in controller.motor_control_specs]

    def test_qrrm_wilinke_supports_rgb_light_and_timer(self):
        """QRRM WiLinke remotes should expose RGB light and timer controls."""
        coordinator = MagicMock()
        controller = RichmatController(coordinator, is_wilinke=True, remote_code="qrrm")

        assert controller.light_protocol_family == "rgb_strip"
        assert controller.supports_light_color_control is True
        assert controller.supports_light_timer is True
        assert controller.supports_discrete_light_control is True
        assert controller.supports_explicit_light_on_control is True
        assert controller.default_light_rgb_color == (1, 221, 255)
        expected_options = ["Always On", *[f"{minute} min" for minute in range(1, 31)]]
        assert controller.light_timer_options == expected_options

    def test_bt6500_wilinke_uses_plain_light_toggle(self):
        """BT6500 has a white toggle light, not RGB light packets."""
        coordinator = MagicMock()
        controller = RichmatController(coordinator, is_wilinke=True, remote_code="bt6500")

        assert controller.light_protocol_family is None
        assert controller.supports_lights is True
        assert controller.supports_light_color_control is False
        assert controller.supports_light_timer is False
        assert controller.supports_discrete_light_control is False
        assert controller.supports_explicit_light_on_control is False
        assert controller.default_light_rgb_color is None
        assert controller.light_timer_options == []

    def test_ggrm_profile_matches_hjh89_handset(self):
        """GGRM on a QRRM receiver (#695) exposes the HJH89 handset surface."""
        coordinator = MagicMock()
        controller = RichmatController(
            coordinator, is_wilinke=True, remote_code=RICHMAT_REMOTE_GGRM
        )

        assert controller.supports_preset_flat is True
        assert controller.supports_preset_zero_g is True
        assert controller.supports_preset_anti_snore is True
        assert controller.supports_preset_tv is False
        assert controller.supports_preset_lounge is False
        assert controller.memory_slot_count == 1
        assert controller.supports_memory_programming is True
        assert controller.has_pillow_support is True
        assert controller.has_lumbar_support is True
        # The app layouts only send the 0x3C toggle, never RGB light packets.
        assert controller.supports_lights is True
        assert controller.light_protocol_family is None
        assert controller.supports_explicit_light_on_control is False
        assert controller.supports_light_color_control is False

    def test_ggrm_profile_uses_app_catalog_frames(self):
        """GGRM frames match the Revive Control/Blvd Home/HARMONY GGRM catalog."""
        coordinator = MagicMock()
        controller = RichmatController(
            coordinator, is_wilinke=True, remote_code=RICHMAT_REMOTE_GGRM
        )

        expected = {
            0x3F: "6e01003fae",
            0x41: "6e010041b0",
            0x46: "6e010046b5",
            0x2B: "6e01002b9a",
            0x3C: "6e01003cab",
        }
        for command, frame in expected.items():
            assert controller._build_command(command) == bytes.fromhex(frame)
        # The apps release with 0x6E; 0x5E is their massage "All Off".
        assert controller._build_stop_command() == bytes.fromhex("6e01006edd")

    def test_i7rm_sleep_function_prefers_rgb_strip_protocol(self):
        """Sleep Function 2.0 aliases should stay on the newer RGB-strip family."""
        coordinator = MagicMock()
        controller = RichmatController(
            coordinator,
            is_wilinke=True,
            remote_code="i7rm",
            device_name="Sleep Function 2.0",
        )

        assert controller.light_protocol_family == "rgb_strip"
        assert controller.supports_discrete_light_control is True
        assert controller.supports_explicit_light_on_control is True

    def test_i7rm_without_sleep_function_hint_uses_legacy_rgb_protocol(self):
        """Generic I7RM remotes should default to the older Java RGB family."""
        coordinator = MagicMock()
        controller = RichmatController(coordinator, is_wilinke=True, remote_code="i7rm")

        assert controller.light_protocol_family == "legacy_rgb"
        assert controller.supports_discrete_light_control is False

    def test_non_i7rm_casper_name_hint_stays_on_legacy_rgb_protocol(self):
        """Casper-style names should not promote unrelated WiLinke remotes to RGB-strip."""
        coordinator = MagicMock()
        controller = RichmatController(
            coordinator,
            is_wilinke=True,
            remote_code="virm",
            entry_title="Casper Adjustable Bed",
        )

        assert controller.light_protocol_family == "legacy_rgb"
        assert controller.supports_discrete_light_control is False

    def test_qrrm_nordic_does_not_assume_rgb_light_packets(self):
        """The recovered RGB packets are WiLinke-specific and should not be used on Nordic."""
        coordinator = MagicMock()
        controller = RichmatController(coordinator, is_wilinke=False, remote_code="qrrm")

        assert controller.supports_light_color_control is False
        assert controller.supports_light_timer is False

    def test_build_qrrm_light_color_command(self):
        """QRRM RGB light packets should match the recovered Casper/Richmat app format."""
        coordinator = MagicMock()
        controller = RichmatController(coordinator, is_wilinke=True, remote_code="qrrm")

        command = controller._build_light_color_command((1, 221, 255))

        assert command == bytes.fromhex("040b01010001ddff0000ee")

    def test_build_qrrm_light_power_command(self):
        """QRRM RGB-strip power packets should use explicit on/off frames."""
        coordinator = MagicMock()
        controller = RichmatController(coordinator, is_wilinke=True, remote_code="qrrm")

        assert controller._build_light_power_command(is_on=True) == bytes.fromhex(
            "040904010002000014"
        )
        assert controller._build_light_power_command(is_on=False) == bytes.fromhex(
            "040904010000000012"
        )

    def test_build_qrrm_light_timer_command(self):
        """QRRM timer packets should use minute values in the RGB-strip frame."""
        coordinator = MagicMock()
        controller = RichmatController(coordinator, is_wilinke=True, remote_code="qrrm")

        assert controller._build_light_timer_command(3) == bytes.fromhex("040a0201000003000014")
        assert controller._build_light_timer_command(10) == bytes.fromhex(
            "040a020100000a00001b"
        )
        assert controller._build_light_timer_command(0) == bytes.fromhex("040a0201000000000011")

    def test_virm_wilinke_supports_legacy_rgb_light_and_timer(self):
        """Legacy WiLinke remotes with lights should expose the older RGB family."""
        coordinator = MagicMock()
        controller = RichmatController(coordinator, is_wilinke=True, remote_code="virm")

        assert controller.light_protocol_family == "legacy_rgb"
        assert controller.supports_light_color_control is True
        assert controller.supports_light_timer is True
        assert controller.supports_discrete_light_control is False
        assert controller.supports_explicit_light_on_control is True
        assert controller.default_light_rgb_color == (0, 255, 0)
        assert controller.light_timer_options == RICHMAT_LEGACY_RGB_LIGHT_TIMER_OPTIONS

    def test_build_legacy_richmat_light_color_command(self):
        """Legacy Richmat RGB packets should match the older Java OEM apps."""
        coordinator = MagicMock()
        controller = RichmatController(coordinator, is_wilinke=True, remote_code="virm")

        command = controller._build_light_color_command((1, 221, 255))

        assert command == bytes.fromhex("6e0cff017a6e0dddff57")

    def test_build_legacy_richmat_light_power_on_command(self):
        """Legacy Richmat light power-on should use the confirmed TX_LED packet."""
        coordinator = MagicMock()
        controller = RichmatController(coordinator, is_wilinke=True, remote_code="virm")

        assert controller._build_legacy_light_power_on_command() == bytes.fromhex("6e0a000179")

    def test_build_legacy_richmat_light_timer_command(self):
        """Legacy Richmat timers should use seconds up to the 300-second app limit."""
        coordinator = MagicMock()
        controller = RichmatController(coordinator, is_wilinke=True, remote_code="virm")

        assert controller._build_light_timer_command(180) == bytes.fromhex("6e0b00b42d")
        assert controller._build_light_timer_command(0) == bytes.fromhex("6e0b000079")


class TestRichmatRgbLights:
    """Test Richmat RGB light controls."""

    async def test_set_legacy_richmat_light_color(
        self,
        hass: HomeAssistant,
        mock_richmat_config_entry_data: dict,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Legacy WiLinke Richmat beds should send the older RGB packet."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            title="Richmat VIRM Bed",
            data={
                **mock_richmat_config_entry_data,
                CONF_PROTOCOL_VARIANT: "wilinke",
                CONF_RICHMAT_REMOTE: "virm",
            },
            unique_id="57:4C:62:AA:BB:CC",
            entry_id="richmat_virm_light_entry",
        )
        entry.add_to_hass(hass)

        coordinator = AdjustableBedCoordinator(hass, entry)
        await coordinator.async_connect()
        mock_bleak_client.write_gatt_char.reset_mock()

        await coordinator.controller.set_light_color((1, 221, 255))

        mock_bleak_client.write_gatt_char.assert_called_with(
            coordinator.controller.control_characteristic_uuid,
            bytes.fromhex("6e0cff017a6e0dddff57"),
            response=True,
        )

    async def test_set_legacy_richmat_light_timer(
        self,
        hass: HomeAssistant,
        mock_richmat_config_entry_data: dict,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Legacy WiLinke Richmat beds should use the older second-based timer packet."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            title="Richmat VIRM Bed",
            data={
                **mock_richmat_config_entry_data,
                CONF_PROTOCOL_VARIANT: "wilinke",
                CONF_RICHMAT_REMOTE: "virm",
            },
            unique_id="57:4C:62:AA:BB:CC",
            entry_id="richmat_virm_timer_entry",
        )
        entry.add_to_hass(hass)

        coordinator = AdjustableBedCoordinator(hass, entry)
        await coordinator.async_connect()
        mock_bleak_client.write_gatt_char.reset_mock()

        await coordinator.controller.set_light_timer("3 min")

        mock_bleak_client.write_gatt_char.assert_called_with(
            coordinator.controller.control_characteristic_uuid,
            bytes.fromhex("6e0b00b42d"),
            response=True,
        )

    async def test_set_qrrm_light_color(
        self,
        hass: HomeAssistant,
        mock_richmat_config_entry_data: dict,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """QRRM WiLinke beds should send the recovered RGB packet."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            title="Casper QRRM Bed",
            data={
                **mock_richmat_config_entry_data,
                CONF_PROTOCOL_VARIANT: "wilinke",
                CONF_RICHMAT_REMOTE: "qrrm",
            },
            unique_id="57:4C:62:C3:39:05",
            entry_id="richmat_qrrm_light_entry",
        )
        entry.add_to_hass(hass)

        coordinator = AdjustableBedCoordinator(hass, entry)
        await coordinator.async_connect()
        mock_bleak_client.write_gatt_char.reset_mock()

        await coordinator.controller.set_light_color((1, 221, 255))

        mock_bleak_client.write_gatt_char.assert_called_with(
            coordinator.controller.control_characteristic_uuid,
            bytes.fromhex("040b01010001ddff0000ee"),
            response=True,
        )

    async def test_set_qrrm_light_timer(
        self,
        hass: HomeAssistant,
        mock_richmat_config_entry_data: dict,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """QRRM WiLinke beds should support minute-granular RGB-strip timers."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            title="Casper QRRM Bed",
            data={
                **mock_richmat_config_entry_data,
                CONF_PROTOCOL_VARIANT: "wilinke",
                CONF_RICHMAT_REMOTE: "qrrm",
            },
            unique_id="57:4C:62:C3:39:05",
            entry_id="richmat_qrrm_timer_entry",
        )
        entry.add_to_hass(hass)

        coordinator = AdjustableBedCoordinator(hass, entry)
        await coordinator.async_connect()
        mock_bleak_client.write_gatt_char.reset_mock()

        await coordinator.controller.set_light_timer("3 min")

        mock_bleak_client.write_gatt_char.assert_called_with(
            coordinator.controller.control_characteristic_uuid,
            bytes.fromhex("040a0201000003000014"),
            response=True,
        )


class TestRichmatLights:
    """Test Richmat light commands."""

    @pytest.mark.parametrize("method_name", ["lights_on", "lights_off"])
    async def test_bt6500_lights_on_off_send_toggle_command(
        self,
        hass: HomeAssistant,
        mock_richmat_config_entry_data: dict,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
        method_name: str,
    ):
        """BT6500 light on/off should delegate to the WiLinke 0x3C toggle command."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            title="BedTech BT6500",
            data={
                **mock_richmat_config_entry_data,
                CONF_PROTOCOL_VARIANT: "wilinke",
                CONF_RICHMAT_REMOTE: "auto",
            },
            unique_id="57:4C:62:B0:EF:3D",
            entry_id=f"richmat_bt6500_{method_name}_light_entry",
        )
        entry.add_to_hass(hass)

        coordinator = AdjustableBedCoordinator(hass, entry)
        await coordinator.async_connect()
        mock_bleak_client.write_gatt_char.reset_mock()

        assert coordinator.controller._remote_code == "bt6500"
        assert coordinator.controller.light_protocol_family is None

        await getattr(coordinator.controller, method_name)()

        mock_bleak_client.write_gatt_char.assert_called_once_with(
            coordinator.controller.control_characteristic_uuid,
            bytes.fromhex("6e01003cab"),
            response=True,
        )


class TestRichmatMassage:
    """Test Richmat massage commands."""

    @pytest.mark.parametrize(
        ("command", "frame"),
        [
            (0x66, "6e010066d5"),
            (0x69, "6e010069d8"),
            (0x5F, "6e01005fce"),
            (0x63, "6e010063d2"),
            (0x61, "6e010061d0"),
        ],
    )

    async def test_ggrm_extra_actions_match_frozen_catalog(self, monkeypatch, command, frame):
        """Row055 Blvd Home GGRM vectors and Revive ONCE release semantics."""
        controller = RichmatController(MagicMock(has_massage=True), is_wilinke=True, remote_code="GGRM")
        controller.write_command = AsyncMock()
        sleep = AsyncMock()
        monkeypatch.setattr("custom_components.adjustable_bed.beds.richmat.asyncio.sleep", sleep)
        spec = next(s for s in controller.controller_button_specs if s.key == f"richmat_mh_{command:02x}")

        await spec.press_fn(controller)

        assert [call.args[0].hex() for call in controller.write_command.await_args_list] == [
            frame, "6e01006edd"
        ]
        sleep.assert_awaited_once_with(0.12)
        assert not controller.write_command.await_args_list[-1].kwargs["cancel_event"].is_set()

    @pytest.mark.parametrize("remote, wilinke, massage, keys", [
        ("ggrm", True, False, {"richmat_mh_66", "richmat_mh_69"}),
        ("BT6500", True, True, set()),
        ("auto", True, True, set()),
        ("GGRM", False, True, set()),
    ])

    async def test_ggrm_extra_actions_require_profile_transport_and_massage(
        self, remote, wilinke, massage, keys
    ):
        controller = RichmatController(MagicMock(has_massage=massage), is_wilinke=wilinke, remote_code=remote)
        controller.write_command = AsyncMock()
        assert {spec.key for spec in controller.controller_button_specs} == keys
        with pytest.raises(ValueError):
            await controller.tap_ggrm_action(0x5F)
        controller.write_command.assert_not_awaited()

    @pytest.mark.parametrize("cancel_during", ["write", "release_delay"])
    async def test_ggrm_extra_action_cancellation_releases(self, monkeypatch, cancel_during):
        controller = RichmatController(MagicMock(has_massage=True), is_wilinke=True, remote_code="GGRM")
        controller.write_command = AsyncMock(
            side_effect=[asyncio.CancelledError(), None] if cancel_during == "write" else None
        )
        sleep = AsyncMock(side_effect=asyncio.CancelledError() if cancel_during == "release_delay" else None)
        monkeypatch.setattr("custom_components.adjustable_bed.beds.richmat.asyncio.sleep", sleep)

        with pytest.raises(asyncio.CancelledError):
            await controller.tap_ggrm_action(0x66)

        assert controller.write_command.await_args_list[-1].args == (bytes.fromhex("6e01006edd"),)
        assert not controller.write_command.await_args_list[-1].kwargs["cancel_event"].is_set()

    @pytest.mark.parametrize(
        ("remote_code", "button_key", "frame", "unsupported_method"),
        [
            (RICHMAT_REMOTE_GGRM, "massage_all_off", "6e01005ecd", "massage_toggle"),
            ("ggrm", "massage_all_off", "6e01005ecd", "massage_toggle"),
            ("auto", "massage_all_toggle", "6e01005dcc", "massage_off"),
            ("bt6500", "massage_all_toggle", "6e01005dcc", "massage_off"),
        ],
    )

    async def test_all_massage_button_matches_remote(
        self, remote_code, button_key, frame, unsupported_method
    ):
        """GGRM offers the catalog's All Off instead of the legacy toggle."""
        controller = RichmatController(MagicMock(), is_wilinke=True, remote_code=remote_code)
        controller.write_command = AsyncMock()
        buttons = {
            description.key: description
            for description in BUTTON_DESCRIPTIONS
            if description.key in {"massage_all_off", "massage_all_toggle"}
            and _should_add_button(description, controller, has_massage=True)
        }
        assert set(buttons) == {button_key}
        assert not _should_add_button(buttons[button_key], controller, has_massage=False)

        press_fn = buttons[button_key].press_fn
        assert press_fn is not None
        await press_fn(controller)
        controller.write_command.assert_awaited_once_with(bytes.fromhex(frame))

        controller.write_command.reset_mock()
        with pytest.raises(NotImplementedError):
            await getattr(controller, unsupported_method)()
        controller.write_command.assert_not_awaited()


class TestRichmatSync:
    """Test Richmat split-king sync commands."""

    async def test_supports_synchro(
        self,
        hass: HomeAssistant,
        mock_richmat_config_entry,
        mock_coordinator_connected,
    ):
        """Test that Richmat controller reports sync support."""
        coordinator = AdjustableBedCoordinator(hass, mock_richmat_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.supports_synchro is True


class TestRichmatPositionNotifications:
    """Test Richmat position notification handling."""

    async def test_start_notify_no_support(
        self,
        hass: HomeAssistant,
        mock_richmat_config_entry,
        mock_coordinator_connected,
    ):
        """Test start_notify stores callback without BLE subscription."""
        coordinator = AdjustableBedCoordinator(hass, mock_richmat_config_entry)
        await coordinator.async_connect()

        callback = MagicMock()
        await coordinator.controller.start_notify(callback)

        assert coordinator.controller._notify_callback is callback

    async def test_read_positions_noop(
        self,
        hass: HomeAssistant,
        mock_richmat_config_entry,
        mock_coordinator_connected,
    ):
        """Test read_positions does nothing (not supported)."""
        coordinator = AdjustableBedCoordinator(hass, mock_richmat_config_entry)
        await coordinator.async_connect()

        # Should complete without error
        await coordinator.controller.read_positions()
