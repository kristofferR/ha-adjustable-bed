"""Tests for Jensen bed controller."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed.beds.jensen import (
    FOOT_POS_FLAT,
    FOOT_POS_MAX,
    HEAD_POS_FLAT,
    HEAD_POS_MAX,
    JensenCommands,
    JensenController,
    JensenFeatureFlags,
)
from custom_components.adjustable_bed.const import (
    BED_TYPE_JENSEN,
    CONF_BED_TYPE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_HAS_MASSAGE,
    CONF_JENSEN_PIN,
    CONF_MOTOR_COUNT,
    CONF_PREFERRED_ADAPTER,
    DOMAIN,
    JENSEN_CHAR_UUID,
)
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator


@pytest.fixture
def mock_jensen_config_entry_data() -> dict:
    """Return mock config entry data for Jensen bed."""
    return {
        CONF_ADDRESS: "AA:BB:CC:DD:EE:FF",
        CONF_NAME: "Jensen Test Bed",
        CONF_BED_TYPE: BED_TYPE_JENSEN,
        CONF_MOTOR_COUNT: 2,
        CONF_HAS_MASSAGE: False,
        CONF_DISABLE_ANGLE_SENSING: True,
        CONF_PREFERRED_ADAPTER: "auto",
    }


@pytest.fixture
def mock_jensen_config_entry(
    hass: HomeAssistant, mock_jensen_config_entry_data: dict
) -> MockConfigEntry:
    """Return a mock config entry for Jensen bed."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Jensen Test Bed",
        data=mock_jensen_config_entry_data,
        unique_id="AA:BB:CC:DD:EE:FF",
        entry_id="jensen_test_entry",
    )
    entry.add_to_hass(hass)
    return entry


class TestJensenCommands:
    """Test Jensen command bytes."""

    def test_command_format_is_6_bytes(self):
        """Test all commands are 6 bytes."""
        commands = [
            JensenCommands.CONFIG_READ_ALL,
            JensenCommands.MOTOR_STOP,
            JensenCommands.MOTOR_HEAD_UP,
            JensenCommands.MOTOR_HEAD_DOWN,
            JensenCommands.MOTOR_FOOT_UP,
            JensenCommands.MOTOR_FOOT_DOWN,
            JensenCommands.PRESET_FLAT,
            JensenCommands.PRESET_MEMORY_SAVE,
            JensenCommands.PRESET_MEMORY_RECALL,
            JensenCommands.READ_POSITION,
            JensenCommands.GET_STATUS,
            JensenCommands.MASSAGE_OFF,
            JensenCommands.MASSAGE_HEAD_ON,
            JensenCommands.MASSAGE_FOOT_ON,
            JensenCommands.MASSAGE_BOTH_ON,
            JensenCommands.LIGHT_MAIN_ON,
            JensenCommands.LIGHT_MAIN_OFF,
            JensenCommands.LIGHT_UNDERBED_ON,
            JensenCommands.LIGHT_UNDERBED_OFF,
        ]
        for cmd in commands:
            assert len(cmd) == 6, f"Command {cmd.hex()} is not 6 bytes"

    def test_motor_commands_have_0x10_prefix(self):
        """Test motor commands have 0x10 prefix."""
        motor_commands = [
            JensenCommands.MOTOR_STOP,
            JensenCommands.MOTOR_HEAD_UP,
            JensenCommands.MOTOR_HEAD_DOWN,
            JensenCommands.MOTOR_FOOT_UP,
            JensenCommands.MOTOR_FOOT_DOWN,
            JensenCommands.PRESET_FLAT,
            JensenCommands.PRESET_MEMORY_SAVE,
            JensenCommands.PRESET_MEMORY_RECALL,
        ]
        for cmd in motor_commands:
            assert cmd[0] == 0x10, f"Motor command {cmd.hex()} doesn't have 0x10 prefix"

    def test_massage_commands_have_0x12_prefix(self):
        """Test massage commands have 0x12 prefix."""
        massage_commands = [
            JensenCommands.MASSAGE_OFF,
            JensenCommands.MASSAGE_HEAD_ON,
            JensenCommands.MASSAGE_FOOT_ON,
            JensenCommands.MASSAGE_BOTH_ON,
        ]
        for cmd in massage_commands:
            assert cmd[0] == 0x12, f"Massage command {cmd.hex()} doesn't have 0x12 prefix"

    def test_light_commands_have_0x13_prefix(self):
        """Test light commands have 0x13 prefix."""
        light_commands = [
            JensenCommands.LIGHT_MAIN_ON,
            JensenCommands.LIGHT_MAIN_OFF,
            JensenCommands.LIGHT_UNDERBED_ON,
            JensenCommands.LIGHT_UNDERBED_OFF,
        ]
        for cmd in light_commands:
            assert cmd[0] == 0x13, f"Light command {cmd.hex()} doesn't have 0x13 prefix"

    def test_config_command_has_0x0a_prefix(self):
        """Test config command has 0x0A prefix."""
        assert JensenCommands.CONFIG_READ_ALL[0] == 0x0A

    def test_motor_stop_command_bytes(self):
        """Test MOTOR_STOP command is [0x10, 0x00, 0x00, 0x00, 0x00, 0x00]."""
        assert JensenCommands.MOTOR_STOP == bytes([0x10, 0x00, 0x00, 0x00, 0x00, 0x00])

    def test_motor_head_up_command_bytes(self):
        """Test MOTOR_HEAD_UP command is [0x10, 0x01, ...]."""
        assert JensenCommands.MOTOR_HEAD_UP[1] == 0x01

    def test_motor_head_down_command_bytes(self):
        """Test MOTOR_HEAD_DOWN command is [0x10, 0x02, ...]."""
        assert JensenCommands.MOTOR_HEAD_DOWN[1] == 0x02

    def test_motor_foot_up_command_bytes(self):
        """Test MOTOR_FOOT_UP command is [0x10, 0x10, ...]."""
        assert JensenCommands.MOTOR_FOOT_UP[1] == 0x10

    def test_motor_foot_down_command_bytes(self):
        """Test MOTOR_FOOT_DOWN command is [0x10, 0x20, ...]."""
        assert JensenCommands.MOTOR_FOOT_DOWN[1] == 0x20

    def test_preset_flat_command_bytes(self):
        """Test PRESET_FLAT command is [0x10, 0x81, ...]."""
        assert JensenCommands.PRESET_FLAT[1] == 0x81


class TestJensenFeatureFlags:
    """Test Jensen feature flags."""

    def test_feature_flags_are_bit_flags(self):
        """Test feature flags are individual bits."""
        flags = [
            JensenFeatureFlags.MASSAGE_HEAD,
            JensenFeatureFlags.MASSAGE_FOOT,
            JensenFeatureFlags.LIGHT,
            JensenFeatureFlags.FAN,
            JensenFeatureFlags.LIGHT_UNDERBED,
        ]
        for flag in flags:
            # Each flag should be a power of 2 (single bit set)
            assert flag.bit_count() == 1

    def test_feature_flags_values(self):
        """Test specific feature flag values."""
        assert JensenFeatureFlags.MASSAGE_HEAD == 0x01
        assert JensenFeatureFlags.MASSAGE_FOOT == 0x02
        assert JensenFeatureFlags.LIGHT == 0x04
        assert JensenFeatureFlags.FAN == 0x10
        assert JensenFeatureFlags.LIGHT_UNDERBED == 0x40

    def test_feature_flags_can_be_combined(self):
        """Test feature flags can be combined with OR."""
        combined = JensenFeatureFlags.MASSAGE_HEAD | JensenFeatureFlags.LIGHT
        assert combined == 0x05
        assert combined & JensenFeatureFlags.MASSAGE_HEAD
        assert combined & JensenFeatureFlags.LIGHT
        assert not (combined & JensenFeatureFlags.FAN)


class TestJensenController:
    """Test Jensen controller initialization."""

    async def test_control_characteristic_uuid(
        self,
        hass: HomeAssistant,
        mock_jensen_config_entry,
        mock_coordinator_connected,
    ):
        """Test controller reports correct characteristic UUID."""
        coordinator = AdjustableBedCoordinator(hass, mock_jensen_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.control_characteristic_uuid == JENSEN_CHAR_UUID

    async def test_default_pin_is_3060(
        self,
        hass: HomeAssistant,
        mock_jensen_config_entry,
        mock_coordinator_connected,
    ):
        """Test default PIN is 3060 when not configured."""
        coordinator = AdjustableBedCoordinator(hass, mock_jensen_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller._pin == "3060"

    async def test_custom_pin_from_config(
        self,
        hass: HomeAssistant,
        mock_jensen_config_entry_data: dict,
        mock_coordinator_connected,
    ):
        """Test custom PIN from config entry."""
        mock_jensen_config_entry_data[CONF_JENSEN_PIN] = "1234"
        entry = MockConfigEntry(
            domain=DOMAIN,
            title="Jensen Test Bed",
            data=mock_jensen_config_entry_data,
            unique_id="AA:BB:CC:DD:EE:FF",
            entry_id="jensen_test_entry_pin",
        )

        coordinator = AdjustableBedCoordinator(hass, entry)
        await coordinator.async_connect()

        assert coordinator.controller._pin == "1234"


class TestJensenPinUnlockCommand:
    """Test Jensen PIN unlock command building."""

    async def test_build_pin_unlock_command_default(
        self,
        hass: HomeAssistant,
        mock_jensen_config_entry,
        mock_coordinator_connected,
    ):
        """Test PIN unlock command with default PIN 3060."""
        coordinator = AdjustableBedCoordinator(hass, mock_jensen_config_entry)
        await coordinator.async_connect()

        pin_cmd = coordinator.controller._build_pin_unlock_command()

        # Format: [0x1E, digit1, digit2, digit3, digit4, 0x00]
        assert pin_cmd[0] == 0x1E
        assert pin_cmd[1] == 3  # '3'
        assert pin_cmd[2] == 0  # '0'
        assert pin_cmd[3] == 6  # '6'
        assert pin_cmd[4] == 0  # '0'
        assert pin_cmd[5] == 0x00

    async def test_build_pin_unlock_command_custom(
        self,
        hass: HomeAssistant,
        mock_jensen_config_entry_data: dict,
        mock_coordinator_connected,
    ):
        """Test PIN unlock command with custom PIN."""
        mock_jensen_config_entry_data[CONF_JENSEN_PIN] = "1234"
        entry = MockConfigEntry(
            domain=DOMAIN,
            title="Jensen Test Bed",
            data=mock_jensen_config_entry_data,
            unique_id="AA:BB:CC:DD:EE:FF",
            entry_id="jensen_test_entry_pin2",
        )

        coordinator = AdjustableBedCoordinator(hass, entry)
        await coordinator.async_connect()

        pin_cmd = coordinator.controller._build_pin_unlock_command()

        assert pin_cmd[1] == 1  # '1'
        assert pin_cmd[2] == 2  # '2'
        assert pin_cmd[3] == 3  # '3'
        assert pin_cmd[4] == 4  # '4'

    async def test_send_pin_writes_unlock_command(
        self,
        hass: HomeAssistant,
        mock_jensen_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test send_pin writes the expected PIN unlock command."""
        coordinator = AdjustableBedCoordinator(hass, mock_jensen_config_entry)
        await coordinator.async_connect()
        mock_bleak_client.write_gatt_char.reset_mock()

        await coordinator.controller.send_pin()

        mock_bleak_client.write_gatt_char.assert_called_with(
            JENSEN_CHAR_UUID,
            bytes([0x1E, 0x03, 0x00, 0x06, 0x00, 0x00]),
            response=True,
        )


class TestJensenCoordinatorAuthRefresh:
    """Test Jensen command auth refresh in coordinator command paths."""

    async def test_async_execute_controller_command_refreshes_pin(
        self,
        hass: HomeAssistant,
        mock_jensen_config_entry,
    ):
        """Test coordinator refreshes Jensen PIN before controller command execution."""
        coordinator = AdjustableBedCoordinator(hass, mock_jensen_config_entry)
        coordinator._client = MagicMock()
        coordinator._client.is_connected = True
        coordinator._controller = MagicMock()
        coordinator._controller.send_pin = AsyncMock()

        command_called = AsyncMock()

        async def _command_fn(_controller):
            await command_called()

        await coordinator.async_execute_controller_command(_command_fn, cancel_running=False)

        coordinator._controller.send_pin.assert_awaited_once()
        command_called.assert_awaited_once()

    async def test_async_write_command_refreshes_pin(
        self,
        hass: HomeAssistant,
        mock_jensen_config_entry,
    ):
        """Test coordinator refreshes Jensen PIN before raw write commands."""
        coordinator = AdjustableBedCoordinator(hass, mock_jensen_config_entry)
        coordinator._client = MagicMock()
        coordinator._client.is_connected = True
        coordinator._controller = MagicMock()
        coordinator._controller.send_pin = AsyncMock()
        coordinator._controller.write_command = AsyncMock()

        await coordinator.async_write_command(
            JensenCommands.PRESET_FLAT,
            cancel_running=False,
        )

        coordinator._controller.send_pin.assert_awaited_once()
        coordinator._controller.write_command.assert_awaited_once()


class TestJensenMovement:
    """Test Jensen movement commands."""

    def _get_motor_commands(self, calls):
        """Extract only motor commands (starting with 0x10) from call list.

        Jensen beds send PIN unlock (0x1E) and config query (0x0A) during start_notify,
        so we need to filter to just motor commands for movement tests.
        """
        return [call[0][1] for call in calls if call[0][1][0] == 0x10]

    async def test_move_head_up(
        self,
        hass: HomeAssistant,
        mock_jensen_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test move head up sends HEAD_UP command followed by STOP."""
        coordinator = AdjustableBedCoordinator(hass, mock_jensen_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.move_head_up()

        calls = mock_bleak_client.write_gatt_char.call_args_list
        motor_commands = self._get_motor_commands(calls)
        # First motor command should be HEAD_UP (may be repeated), last should be STOP
        assert motor_commands[0] == JensenCommands.MOTOR_HEAD_UP
        assert motor_commands[-1] == JensenCommands.MOTOR_STOP

    async def test_move_head_down(
        self,
        hass: HomeAssistant,
        mock_jensen_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test move head down sends HEAD_DOWN command followed by STOP."""
        coordinator = AdjustableBedCoordinator(hass, mock_jensen_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.move_head_down()

        calls = mock_bleak_client.write_gatt_char.call_args_list
        motor_commands = self._get_motor_commands(calls)
        assert motor_commands[0] == JensenCommands.MOTOR_HEAD_DOWN
        assert motor_commands[-1] == JensenCommands.MOTOR_STOP

    async def test_move_feet_up(
        self,
        hass: HomeAssistant,
        mock_jensen_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test move feet up sends FOOT_UP command followed by STOP."""
        coordinator = AdjustableBedCoordinator(hass, mock_jensen_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.move_feet_up()

        calls = mock_bleak_client.write_gatt_char.call_args_list
        motor_commands = self._get_motor_commands(calls)
        assert motor_commands[0] == JensenCommands.MOTOR_FOOT_UP
        assert motor_commands[-1] == JensenCommands.MOTOR_STOP

    async def test_move_feet_down(
        self,
        hass: HomeAssistant,
        mock_jensen_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test move feet down sends FOOT_DOWN command followed by STOP."""
        coordinator = AdjustableBedCoordinator(hass, mock_jensen_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.move_feet_down()

        calls = mock_bleak_client.write_gatt_char.call_args_list
        motor_commands = self._get_motor_commands(calls)
        assert motor_commands[0] == JensenCommands.MOTOR_FOOT_DOWN
        assert motor_commands[-1] == JensenCommands.MOTOR_STOP

    async def test_stop_all(
        self,
        hass: HomeAssistant,
        mock_jensen_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test stop_all sends MOTOR_STOP command."""
        coordinator = AdjustableBedCoordinator(hass, mock_jensen_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.stop_all()

        mock_bleak_client.write_gatt_char.assert_called_with(
            JENSEN_CHAR_UUID, JensenCommands.MOTOR_STOP, response=True
        )


class TestJensenPresets:
    """Test Jensen preset commands."""

    async def test_preset_flat(
        self,
        hass: HomeAssistant,
        mock_jensen_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test preset flat command."""
        coordinator = AdjustableBedCoordinator(hass, mock_jensen_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.preset_flat()

        mock_bleak_client.write_gatt_char.assert_called_with(
            JENSEN_CHAR_UUID, JensenCommands.PRESET_FLAT, response=True
        )

    async def test_preset_memory_recall(
        self,
        hass: HomeAssistant,
        mock_jensen_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test preset memory recall (slot 1)."""
        coordinator = AdjustableBedCoordinator(hass, mock_jensen_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.preset_memory(1)

        mock_bleak_client.write_gatt_char.assert_called_with(
            JENSEN_CHAR_UUID, JensenCommands.PRESET_MEMORY_RECALL, response=True
        )

    async def test_preset_memory_invalid_slot(
        self,
        hass: HomeAssistant,
        mock_jensen_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
        caplog,
    ):
        """Test preset memory with invalid slot logs warning."""
        coordinator = AdjustableBedCoordinator(hass, mock_jensen_config_entry)
        await coordinator.async_connect()
        mock_bleak_client.reset_mock()

        await coordinator.controller.preset_memory(2)  # Jensen only supports slot 1

        # Should not send command
        mock_bleak_client.write_gatt_char.assert_not_called()
        assert "Invalid memory preset number" in caplog.text

    async def test_program_memory(
        self,
        hass: HomeAssistant,
        mock_jensen_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test program memory (save current position)."""
        coordinator = AdjustableBedCoordinator(hass, mock_jensen_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.program_memory(1)

        mock_bleak_client.write_gatt_char.assert_called_with(
            JENSEN_CHAR_UUID, JensenCommands.PRESET_MEMORY_SAVE, response=True
        )


class TestJensenCapabilities:
    """Test Jensen capability properties."""

    async def test_supports_preset_flat(
        self,
        hass: HomeAssistant,
        mock_jensen_config_entry,
        mock_coordinator_connected,
    ):
        """Test Jensen reports flat preset support."""
        coordinator = AdjustableBedCoordinator(hass, mock_jensen_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.supports_preset_flat is True

    async def test_supports_memory_presets(
        self,
        hass: HomeAssistant,
        mock_jensen_config_entry,
        mock_coordinator_connected,
    ):
        """Test Jensen reports memory preset support."""
        coordinator = AdjustableBedCoordinator(hass, mock_jensen_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.supports_memory_presets is True

    async def test_memory_slot_count_is_one(
        self,
        hass: HomeAssistant,
        mock_jensen_config_entry,
        mock_coordinator_connected,
    ):
        """Test Jensen reports 1 memory slot."""
        coordinator = AdjustableBedCoordinator(hass, mock_jensen_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.memory_slot_count == 1

    async def test_supports_memory_programming(
        self,
        hass: HomeAssistant,
        mock_jensen_config_entry,
        mock_coordinator_connected,
    ):
        """Test Jensen reports memory programming support."""
        coordinator = AdjustableBedCoordinator(hass, mock_jensen_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.supports_memory_programming is True


class TestJensenFeatureDetection:
    """Test Jensen feature detection from config response."""

    async def test_full_features_on_timeout(
        self,
        hass: HomeAssistant,
        mock_jensen_config_entry,
        mock_coordinator_connected,
    ):
        """Test full features are assumed when config query times out."""
        coordinator = AdjustableBedCoordinator(hass, mock_jensen_config_entry)
        await coordinator.async_connect()

        # Features are detected via query_config during start_notify
        # When query_config times out (no mock response), common features are assumed
        # as a failsafe to avoid limiting functionality unnecessarily
        # Note: FAN is NOT included in timeout defaults (rare feature)
        assert coordinator.controller.supports_lights is True
        assert coordinator.controller.supports_under_bed_lights is True
        assert coordinator.controller.has_massage is True
        assert coordinator.controller.has_fan is False  # FAN not included in timeout defaults

    async def test_features_from_flags(
        self,
        hass: HomeAssistant,
        mock_jensen_config_entry,
        mock_coordinator_connected,
    ):
        """Test features are set from feature flags."""
        coordinator = AdjustableBedCoordinator(hass, mock_jensen_config_entry)
        await coordinator.async_connect()

        # Manually set feature flags (simulating query_config response)
        coordinator.controller._features = (
            JensenFeatureFlags.LIGHT
            | JensenFeatureFlags.MASSAGE_HEAD
            | JensenFeatureFlags.MASSAGE_FOOT
        )

        assert coordinator.controller.supports_lights is True
        assert coordinator.controller.has_massage is True
        assert coordinator.controller.has_massage_head is True
        assert coordinator.controller.has_massage_foot is True


class TestJensenPositionParsing:
    """Test Jensen position notification parsing."""

    def test_raw_to_percentage_head_flat(self):
        """Test head position at flat returns 0%."""
        # Create controller instance with mock coordinator
        mock_coordinator = MagicMock()
        controller = JensenController(mock_coordinator)

        result = controller._raw_to_percentage(HEAD_POS_FLAT, "head")
        assert result == 0.0

    def test_raw_to_percentage_head_max(self):
        """Test head position at max returns 100%."""
        mock_coordinator = MagicMock()
        controller = JensenController(mock_coordinator)

        result = controller._raw_to_percentage(HEAD_POS_MAX, "head")
        assert result == 100.0

    def test_raw_to_percentage_head_midpoint(self):
        """Test head position at midpoint returns ~50%."""
        mock_coordinator = MagicMock()
        controller = JensenController(mock_coordinator)

        midpoint = (HEAD_POS_MAX - HEAD_POS_FLAT) // 2 + HEAD_POS_FLAT
        result = controller._raw_to_percentage(midpoint, "head")
        assert 45.0 <= result <= 55.0  # Allow some tolerance

    def test_raw_to_percentage_foot_flat(self):
        """Test foot position at flat returns 0%."""
        mock_coordinator = MagicMock()
        controller = JensenController(mock_coordinator)

        result = controller._raw_to_percentage(FOOT_POS_FLAT, "foot")
        assert result == 0.0

    def test_raw_to_percentage_foot_max(self):
        """Test foot position at max returns 100%."""
        mock_coordinator = MagicMock()
        controller = JensenController(mock_coordinator)

        result = controller._raw_to_percentage(FOOT_POS_MAX, "foot")
        assert result == 100.0

    def test_raw_to_percentage_clamps_below_flat(self):
        """Test values below flat are clamped to 0%."""
        mock_coordinator = MagicMock()
        controller = JensenController(mock_coordinator)

        result = controller._raw_to_percentage(0, "head")
        assert result == 0.0

    def test_raw_to_percentage_clamps_above_max(self):
        """Test values above max are clamped to 100%."""
        mock_coordinator = MagicMock()
        controller = JensenController(mock_coordinator)

        result = controller._raw_to_percentage(50000, "head")
        assert result == 100.0


class TestJensenLights:
    """Test Jensen light commands (when feature is enabled)."""

    async def test_lights_on_with_feature(
        self,
        hass: HomeAssistant,
        mock_jensen_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test lights_on sends correct command when feature is enabled."""
        coordinator = AdjustableBedCoordinator(hass, mock_jensen_config_entry)
        await coordinator.async_connect()

        # Enable light feature
        coordinator.controller._features = JensenFeatureFlags.LIGHT

        await coordinator.controller.lights_on()

        mock_bleak_client.write_gatt_char.assert_called_with(
            JENSEN_CHAR_UUID, JensenCommands.LIGHT_MAIN_ON, response=True
        )

    async def test_lights_on_without_feature_raises(
        self,
        hass: HomeAssistant,
        mock_jensen_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test lights_on raises NotImplementedError when feature is disabled."""
        coordinator = AdjustableBedCoordinator(hass, mock_jensen_config_entry)
        await coordinator.async_connect()

        # No features enabled
        coordinator.controller._features = JensenFeatureFlags.NONE

        with pytest.raises(NotImplementedError):
            await coordinator.controller.lights_on()

    async def test_lights_off_with_feature(
        self,
        hass: HomeAssistant,
        mock_jensen_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test lights_off sends correct command when feature is enabled."""
        coordinator = AdjustableBedCoordinator(hass, mock_jensen_config_entry)
        await coordinator.async_connect()

        # Enable light feature and set state
        coordinator.controller._features = JensenFeatureFlags.LIGHT
        coordinator.controller._lights_on = True

        await coordinator.controller.lights_off()

        mock_bleak_client.write_gatt_char.assert_called_with(
            JENSEN_CHAR_UUID, JensenCommands.LIGHT_MAIN_OFF, response=True
        )

    async def test_underbed_lights_on_with_feature(
        self,
        hass: HomeAssistant,
        mock_jensen_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test underbed_lights_on sends correct command when feature is enabled."""
        coordinator = AdjustableBedCoordinator(hass, mock_jensen_config_entry)
        await coordinator.async_connect()

        # Enable underbed light feature
        coordinator.controller._features = JensenFeatureFlags.LIGHT_UNDERBED

        await coordinator.controller.underbed_lights_on()

        mock_bleak_client.write_gatt_char.assert_called_with(
            JENSEN_CHAR_UUID, JensenCommands.LIGHT_UNDERBED_ON, response=True
        )


class TestJensenMassage:
    """Test Jensen massage commands (when feature is enabled)."""

    async def test_massage_off(
        self,
        hass: HomeAssistant,
        mock_jensen_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test massage_off sends correct command."""
        coordinator = AdjustableBedCoordinator(hass, mock_jensen_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.massage_off()

        mock_bleak_client.write_gatt_char.assert_called_with(
            JENSEN_CHAR_UUID, JensenCommands.MASSAGE_OFF, response=True
        )

    async def test_massage_head_toggle_on(
        self,
        hass: HomeAssistant,
        mock_jensen_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test massage_head_toggle turns head massage on."""
        coordinator = AdjustableBedCoordinator(hass, mock_jensen_config_entry)
        await coordinator.async_connect()

        # Enable massage feature
        coordinator.controller._features = JensenFeatureFlags.MASSAGE_HEAD
        coordinator.controller._massage_head_on = False

        await coordinator.controller.massage_head_toggle()

        mock_bleak_client.write_gatt_char.assert_called_with(
            JENSEN_CHAR_UUID, JensenCommands.MASSAGE_HEAD_ON, response=True
        )
        assert coordinator.controller._massage_head_on is True

    async def test_massage_head_toggle_off(
        self,
        hass: HomeAssistant,
        mock_jensen_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test massage_head_toggle turns head massage off."""
        coordinator = AdjustableBedCoordinator(hass, mock_jensen_config_entry)
        await coordinator.async_connect()

        # Enable massage feature and set to on
        coordinator.controller._features = JensenFeatureFlags.MASSAGE_HEAD
        coordinator.controller._massage_head_on = True
        coordinator.controller._massage_foot_on = False

        await coordinator.controller.massage_head_toggle()

        mock_bleak_client.write_gatt_char.assert_called_with(
            JENSEN_CHAR_UUID, JensenCommands.MASSAGE_OFF, response=True
        )
        assert coordinator.controller._massage_head_on is False

    async def test_massage_toggle_without_feature_raises(
        self,
        hass: HomeAssistant,
        mock_jensen_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test massage_toggle raises NotImplementedError when no massage feature."""
        coordinator = AdjustableBedCoordinator(hass, mock_jensen_config_entry)
        await coordinator.async_connect()

        coordinator.controller._features = JensenFeatureFlags.NONE

        with pytest.raises(NotImplementedError):
            await coordinator.controller.massage_toggle()
