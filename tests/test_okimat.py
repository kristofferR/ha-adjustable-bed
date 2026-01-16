"""Tests for Okimat bed controller."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bleak.exc import BleakError
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed.beds.okimat import (
    OKIMAT_REMOTES,
    OkimatComplexCommand,
    OkimatController,
    OkimatRemoteConfig,
    int_to_bytes,
)
from custom_components.adjustable_bed.const import (
    BED_TYPE_OKIMAT,
    CONF_BED_TYPE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_HAS_MASSAGE,
    CONF_MOTOR_COUNT,
    CONF_PREFERRED_ADAPTER,
    CONF_PROTOCOL_VARIANT,
    DOMAIN,
    OKIMAT_VARIANT_82417,
    OKIMAT_VARIANT_82418,
    OKIMAT_VARIANT_93329,
    OKIMAT_VARIANT_93332,
    OKIMAT_VARIANT_94238,
    OKIMAT_WRITE_CHAR_UUID,
    VARIANT_AUTO,
)
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator


class TestOkimatHelpers:
    """Test Okimat helper functions."""

    def test_int_to_bytes(self):
        """Test integer to big-endian bytes conversion."""
        assert int_to_bytes(0x1) == [0x00, 0x00, 0x00, 0x01]
        assert int_to_bytes(0x100) == [0x00, 0x00, 0x01, 0x00]
        assert int_to_bytes(0xAA) == [0x00, 0x00, 0x00, 0xAA]


class TestOkimatRemoteConfigs:
    """Test Okimat remote configurations."""

    def test_remote_82417_basic(self):
        """Test 82417 RF TOPLINE basic remote config."""
        remote = OKIMAT_REMOTES[OKIMAT_VARIANT_82417]
        assert remote.name == "RF TOPLINE"
        assert remote.flat == 0x000000AA
        assert remote.back_up == 0x1
        assert remote.back_down == 0x2
        assert remote.legs_up == 0x4
        assert remote.legs_down == 0x8
        # No memory on basic remote
        assert remote.memory_1 is None
        assert remote.memory_2 is None
        # No head/feet motors
        assert remote.head_up is None
        assert remote.feet_up is None

    def test_remote_82418_with_memory(self):
        """Test 82418 RF TOPLINE remote with memory."""
        remote = OKIMAT_REMOTES[OKIMAT_VARIANT_82418]
        assert remote.flat == 0x000000AA
        assert remote.memory_1 == 0x1000
        assert remote.memory_2 == 0x2000
        assert remote.memory_save == 0x10000
        # No memory 3/4
        assert remote.memory_3 is None
        assert remote.memory_4 is None

    def test_remote_93329_advanced(self):
        """Test 93329 RF TOPLINE advanced remote with head motor and 4 memory."""
        remote = OKIMAT_REMOTES[OKIMAT_VARIANT_93329]
        assert remote.flat == 0x0000002A  # Different flat value
        assert remote.head_up == 0x10
        assert remote.head_down == 0x20
        assert remote.memory_1 == 0x1000
        assert remote.memory_2 == 0x2000
        assert remote.memory_3 == 0x4000
        assert remote.memory_4 == 0x8000

    def test_remote_93332_full(self):
        """Test 93332 RF TOPLINE full remote with head and feet motors."""
        remote = OKIMAT_REMOTES[OKIMAT_VARIANT_93332]
        assert remote.flat == 0x000000AA
        assert remote.head_up == 0x10
        assert remote.head_down == 0x20
        assert remote.feet_up == 0x40
        assert remote.feet_down == 0x20  # Shares value with head_down
        assert remote.memory_1 == 0x1000
        assert remote.memory_2 == 0x2000

    def test_all_remotes_have_lights(self):
        """Test all remotes support under-bed lights."""
        for variant, remote in OKIMAT_REMOTES.items():
            cmd = remote.toggle_lights
            if isinstance(cmd, OkimatComplexCommand):
                assert cmd.data == 0x20000, f"Remote {variant} has wrong lights command"
            else:
                assert cmd == 0x20000, f"Remote {variant} missing lights"

    def test_remote_94238_complex_commands(self):
        """Test 94238 RF FLASHLINE uses complex commands for lights and memory save."""
        remote = OKIMAT_REMOTES[OKIMAT_VARIANT_94238]
        assert remote.name == "RF FLASHLINE"

        # UBL (Under-Bed Lights) has complex command with specific timing
        assert isinstance(remote.toggle_lights, OkimatComplexCommand)
        assert remote.toggle_lights.data == 0x20000
        assert remote.toggle_lights.count == 50
        assert remote.toggle_lights.wait_time == 100

        # Memory save also has complex command with specific timing
        assert isinstance(remote.memory_save, OkimatComplexCommand)
        assert remote.memory_save.data == 0x10000
        assert remote.memory_save.count == 25
        assert remote.memory_save.wait_time == 200


@pytest.fixture
def mock_okimat_config_entry_data() -> dict:
    """Return mock config entry data for Okimat bed."""
    return {
        CONF_ADDRESS: "AA:BB:CC:DD:EE:FF",
        CONF_NAME: "Okimat Test Bed",
        CONF_BED_TYPE: BED_TYPE_OKIMAT,
        CONF_PROTOCOL_VARIANT: OKIMAT_VARIANT_82417,
        CONF_MOTOR_COUNT: 2,
        CONF_HAS_MASSAGE: True,
        CONF_DISABLE_ANGLE_SENSING: True,
        CONF_PREFERRED_ADAPTER: "auto",
    }


@pytest.fixture
def mock_okimat_config_entry(
    hass: HomeAssistant, mock_okimat_config_entry_data: dict
) -> MockConfigEntry:
    """Return a mock config entry for Okimat bed."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Okimat Test Bed",
        data=mock_okimat_config_entry_data,
        unique_id="AA:BB:CC:DD:EE:FF",
        entry_id="okimat_test_entry",
    )
    entry.add_to_hass(hass)
    return entry


@pytest.fixture
def mock_okimat_93329_config_entry_data() -> dict:
    """Return mock config entry data for Okimat 93329 bed."""
    return {
        CONF_ADDRESS: "AA:BB:CC:DD:EE:FF",
        CONF_NAME: "Okimat 93329 Test Bed",
        CONF_BED_TYPE: BED_TYPE_OKIMAT,
        CONF_PROTOCOL_VARIANT: OKIMAT_VARIANT_93329,
        CONF_MOTOR_COUNT: 3,
        CONF_HAS_MASSAGE: True,
        CONF_DISABLE_ANGLE_SENSING: True,
        CONF_PREFERRED_ADAPTER: "auto",
    }


@pytest.fixture
def mock_okimat_93329_config_entry(
    hass: HomeAssistant, mock_okimat_93329_config_entry_data: dict
) -> MockConfigEntry:
    """Return a mock config entry for Okimat 93329 bed."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Okimat 93329 Test Bed",
        data=mock_okimat_93329_config_entry_data,
        unique_id="AA:BB:CC:DD:EE:FF",
        entry_id="okimat_93329_test_entry",
    )
    entry.add_to_hass(hass)
    return entry


@pytest.fixture
def mock_okimat_94238_config_entry_data() -> dict:
    """Return mock config entry data for Okimat 94238 bed (complex commands)."""
    return {
        CONF_ADDRESS: "AA:BB:CC:DD:EE:FF",
        CONF_NAME: "Okimat 94238 Test Bed",
        CONF_BED_TYPE: BED_TYPE_OKIMAT,
        CONF_PROTOCOL_VARIANT: OKIMAT_VARIANT_94238,
        CONF_MOTOR_COUNT: 2,
        CONF_HAS_MASSAGE: True,
        CONF_DISABLE_ANGLE_SENSING: True,
        CONF_PREFERRED_ADAPTER: "auto",
    }


@pytest.fixture
def mock_okimat_94238_config_entry(
    hass: HomeAssistant, mock_okimat_94238_config_entry_data: dict
) -> MockConfigEntry:
    """Return a mock config entry for Okimat 94238 bed."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Okimat 94238 Test Bed",
        data=mock_okimat_94238_config_entry_data,
        unique_id="AA:BB:CC:DD:EE:FF",
        entry_id="okimat_94238_test_entry",
    )
    entry.add_to_hass(hass)
    return entry


class TestOkimatController:
    """Test Okimat controller."""

    async def test_control_characteristic_uuid(
        self,
        hass: HomeAssistant,
        mock_okimat_config_entry,
        mock_coordinator_connected,
    ):
        """Test controller reports correct characteristic UUID."""
        coordinator = AdjustableBedCoordinator(hass, mock_okimat_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.control_characteristic_uuid == OKIMAT_WRITE_CHAR_UUID

    async def test_build_command(
        self,
        hass: HomeAssistant,
        mock_okimat_config_entry,
        mock_coordinator_connected,
    ):
        """Test command building format."""
        coordinator = AdjustableBedCoordinator(hass, mock_okimat_config_entry)
        await coordinator.async_connect()

        # Okimat format: [0x04, 0x02, ...int_bytes]
        remote = OKIMAT_REMOTES[OKIMAT_VARIANT_82417]
        command = coordinator.controller._build_command(remote.back_up)

        assert len(command) == 6
        assert command[:2] == bytes([0x04, 0x02])
        # Command 0x1 in big-endian
        assert command[2:] == bytes([0x00, 0x00, 0x00, 0x01])

    async def test_variant_auto_defaults_to_82417(
        self,
        hass: HomeAssistant,
        mock_coordinator_connected,
    ):
        """Test auto variant defaults to 82417."""
        entry_data = {
            CONF_ADDRESS: "AA:BB:CC:DD:EE:FF",
            CONF_NAME: "Okimat Test",
            CONF_BED_TYPE: BED_TYPE_OKIMAT,
            CONF_PROTOCOL_VARIANT: VARIANT_AUTO,
            CONF_MOTOR_COUNT: 2,
            CONF_HAS_MASSAGE: False,
            CONF_DISABLE_ANGLE_SENSING: True,
            CONF_PREFERRED_ADAPTER: "auto",
        }
        entry = MockConfigEntry(
            domain=DOMAIN,
            title="Okimat Test",
            data=entry_data,
            unique_id="AA:BB:CC:DD:EE:FF",
            entry_id="okimat_auto_test",
        )
        entry.add_to_hass(hass)

        coordinator = AdjustableBedCoordinator(hass, entry)
        await coordinator.async_connect()

        # Controller should use 82417 as default
        assert coordinator.controller._variant == OKIMAT_VARIANT_82417

    async def test_write_command(
        self,
        hass: HomeAssistant,
        mock_okimat_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test writing a command to the bed."""
        coordinator = AdjustableBedCoordinator(hass, mock_okimat_config_entry)
        await coordinator.async_connect()

        command = coordinator.controller._build_command(0)
        await coordinator.controller.write_command(command)

        mock_bleak_client.write_gatt_char.assert_called_with(
            OKIMAT_WRITE_CHAR_UUID, command, response=True
        )

    async def test_write_command_not_connected(
        self,
        hass: HomeAssistant,
        mock_okimat_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test writing command when not connected raises error."""
        coordinator = AdjustableBedCoordinator(hass, mock_okimat_config_entry)
        await coordinator.async_connect()

        mock_bleak_client.is_connected = False

        with pytest.raises(ConnectionError):
            await coordinator.controller.write_command(
                coordinator.controller._build_command(0)
            )


class TestOkimatMovement:
    """Test Okimat movement commands."""

    async def test_move_head_up(
        self,
        hass: HomeAssistant,
        mock_okimat_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test move head up sends commands followed by stop."""
        coordinator = AdjustableBedCoordinator(hass, mock_okimat_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.move_head_up()

        calls = mock_bleak_client.write_gatt_char.call_args_list
        assert len(calls) > 1

        # Last call should be stop (zero command)
        last_command = calls[-1][0][1]
        expected_stop = coordinator.controller._build_command(0)
        assert last_command == expected_stop

    async def test_move_head_down(
        self,
        hass: HomeAssistant,
        mock_okimat_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test move head down."""
        coordinator = AdjustableBedCoordinator(hass, mock_okimat_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.move_head_down()

        calls = mock_bleak_client.write_gatt_char.call_args_list
        assert len(calls) > 1

    async def test_move_feet_up(
        self,
        hass: HomeAssistant,
        mock_okimat_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test move feet up (maps to legs on basic remote)."""
        coordinator = AdjustableBedCoordinator(hass, mock_okimat_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.move_feet_up()

        calls = mock_bleak_client.write_gatt_char.call_args_list
        assert len(calls) > 1

    async def test_stop_all(
        self,
        hass: HomeAssistant,
        mock_okimat_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test stop all sends zero command."""
        coordinator = AdjustableBedCoordinator(hass, mock_okimat_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.stop_all()

        expected_stop = coordinator.controller._build_command(0)
        mock_bleak_client.write_gatt_char.assert_called_with(
            OKIMAT_WRITE_CHAR_UUID, expected_stop, response=True
        )


class TestOkimatPresets:
    """Test Okimat preset commands."""

    async def test_preset_flat_82417(
        self,
        hass: HomeAssistant,
        mock_okimat_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test preset flat command for 82417 remote."""
        coordinator = AdjustableBedCoordinator(hass, mock_okimat_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.preset_flat()

        remote = OKIMAT_REMOTES[OKIMAT_VARIANT_82417]
        expected_cmd = coordinator.controller._build_command(remote.flat)
        first_call = mock_bleak_client.write_gatt_char.call_args_list[0]
        assert first_call[0][1] == expected_cmd

    async def test_preset_flat_93329_different_value(
        self,
        hass: HomeAssistant,
        mock_okimat_93329_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test preset flat for 93329 uses different value (0x2A vs 0xAA)."""
        coordinator = AdjustableBedCoordinator(hass, mock_okimat_93329_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.preset_flat()

        remote = OKIMAT_REMOTES[OKIMAT_VARIANT_93329]
        expected_cmd = coordinator.controller._build_command(remote.flat)
        first_call = mock_bleak_client.write_gatt_char.call_args_list[0]
        assert first_call[0][1] == expected_cmd
        # Verify it's the 0x2A value
        assert first_call[0][1][5] == 0x2A

    async def test_preset_memory_available(
        self,
        hass: HomeAssistant,
        mock_okimat_93329_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test preset memory commands on 93329 remote."""
        coordinator = AdjustableBedCoordinator(hass, mock_okimat_93329_config_entry)
        await coordinator.async_connect()

        remote = OKIMAT_REMOTES[OKIMAT_VARIANT_93329]

        for memory_num, expected_value in [
            (1, remote.memory_1),
            (2, remote.memory_2),
            (3, remote.memory_3),
            (4, remote.memory_4),
        ]:
            mock_bleak_client.write_gatt_char.reset_mock()
            await coordinator.controller.preset_memory(memory_num)

            expected_cmd = coordinator.controller._build_command(expected_value)
            first_call = mock_bleak_client.write_gatt_char.call_args_list[0]
            assert first_call[0][1] == expected_cmd

    async def test_preset_memory_not_available_on_basic(
        self,
        hass: HomeAssistant,
        mock_okimat_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
        caplog,
    ):
        """Test memory preset logs warning on basic remote without memory."""
        coordinator = AdjustableBedCoordinator(hass, mock_okimat_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.preset_memory(1)

        assert "not available on remote" in caplog.text

    async def test_program_memory_available(
        self,
        hass: HomeAssistant,
        mock_okimat_93329_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test program memory on remote that supports it."""
        coordinator = AdjustableBedCoordinator(hass, mock_okimat_93329_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.program_memory(1)

        # Should have written the memory save command
        calls = mock_bleak_client.write_gatt_char.call_args_list
        assert len(calls) > 0

    async def test_program_memory_not_available(
        self,
        hass: HomeAssistant,
        mock_okimat_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
        caplog,
    ):
        """Test program memory logs warning on basic remote."""
        coordinator = AdjustableBedCoordinator(hass, mock_okimat_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.program_memory(1)

        assert "Memory save not available" in caplog.text

    async def test_program_memory_complex_command(
        self,
        hass: HomeAssistant,
        mock_okimat_94238_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test program memory with complex command (94238 remote)."""
        coordinator = AdjustableBedCoordinator(hass, mock_okimat_94238_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.program_memory(1)

        # 94238 has complex command: data=0x10000, count=25, wait_time=200
        remote = OKIMAT_REMOTES[OKIMAT_VARIANT_94238]
        assert isinstance(remote.memory_save, OkimatComplexCommand)

        # Command should use the data field from complex command
        expected_cmd = coordinator.controller._build_command(remote.memory_save.data)
        first_call = mock_bleak_client.write_gatt_char.call_args_list[0]
        assert first_call[0][1] == expected_cmd

        # Should send count (25) commands
        calls = mock_bleak_client.write_gatt_char.call_args_list
        assert len(calls) == 25


class TestOkimatLights:
    """Test Okimat light commands."""

    async def test_lights_toggle(
        self,
        hass: HomeAssistant,
        mock_okimat_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test lights toggle command."""
        coordinator = AdjustableBedCoordinator(hass, mock_okimat_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.lights_toggle()

        remote = OKIMAT_REMOTES[OKIMAT_VARIANT_82417]
        expected_cmd = coordinator.controller._build_command(remote.toggle_lights)
        # Lights toggle sends multiple commands
        first_call = mock_bleak_client.write_gatt_char.call_args_list[0]
        assert first_call[0][1] == expected_cmd

    async def test_lights_toggle_complex_command(
        self,
        hass: HomeAssistant,
        mock_okimat_94238_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test lights toggle with complex command (94238 remote)."""
        coordinator = AdjustableBedCoordinator(hass, mock_okimat_94238_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.lights_toggle()

        # 94238 has complex command: data=0x20000, count=50, wait_time=100
        remote = OKIMAT_REMOTES[OKIMAT_VARIANT_94238]
        assert isinstance(remote.toggle_lights, OkimatComplexCommand)

        # Command should use the data field from complex command
        expected_cmd = coordinator.controller._build_command(remote.toggle_lights.data)
        first_call = mock_bleak_client.write_gatt_char.call_args_list[0]
        assert first_call[0][1] == expected_cmd

        # Should send count (50) commands
        calls = mock_bleak_client.write_gatt_char.call_args_list
        assert len(calls) == 50

    async def test_lights_toggle_complex_command_timing(
        self,
        hass: HomeAssistant,
        mock_okimat_94238_config_entry,
        mock_coordinator_connected,
    ):
        """Test lights toggle uses correct timing from complex command."""
        coordinator = AdjustableBedCoordinator(hass, mock_okimat_94238_config_entry)
        await coordinator.async_connect()

        with patch.object(
            coordinator.controller, "write_command", new_callable=AsyncMock
        ) as mock_write:
            await coordinator.controller.lights_toggle()

            mock_write.assert_called_once()
            _, kwargs = mock_write.call_args
            # Verify wait_time (100) from complex command is passed as repeat_delay_ms
            assert kwargs.get("repeat_delay_ms") == 100
            # Verify count (50) from complex command is passed as repeat_count
            assert kwargs.get("repeat_count") == 50


class TestOkimatMassage:
    """Test Okimat massage commands."""

    async def test_massage_toggle(
        self,
        hass: HomeAssistant,
        mock_okimat_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test massage toggle command."""
        coordinator = AdjustableBedCoordinator(hass, mock_okimat_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.massage_toggle()

        expected_cmd = coordinator.controller._build_command(0x100)
        mock_bleak_client.write_gatt_char.assert_called_with(
            OKIMAT_WRITE_CHAR_UUID, expected_cmd, response=True
        )

    async def test_massage_head_up(
        self,
        hass: HomeAssistant,
        mock_okimat_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test head massage intensity up."""
        coordinator = AdjustableBedCoordinator(hass, mock_okimat_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.massage_head_up()

        expected_cmd = coordinator.controller._build_command(0x800)
        mock_bleak_client.write_gatt_char.assert_called_with(
            OKIMAT_WRITE_CHAR_UUID, expected_cmd, response=True
        )

    async def test_massage_foot_down(
        self,
        hass: HomeAssistant,
        mock_okimat_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test foot massage intensity down."""
        coordinator = AdjustableBedCoordinator(hass, mock_okimat_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.massage_foot_down()

        expected_cmd = coordinator.controller._build_command(0x1000000)
        mock_bleak_client.write_gatt_char.assert_called_with(
            OKIMAT_WRITE_CHAR_UUID, expected_cmd, response=True
        )

    async def test_massage_mode_step(
        self,
        hass: HomeAssistant,
        mock_okimat_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test massage timer step."""
        coordinator = AdjustableBedCoordinator(hass, mock_okimat_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.massage_mode_step()

        expected_cmd = coordinator.controller._build_command(0x200)
        mock_bleak_client.write_gatt_char.assert_called_with(
            OKIMAT_WRITE_CHAR_UUID, expected_cmd, response=True
        )


class TestOkimatPositionNotifications:
    """Test Okimat position notification handling."""

    async def test_start_notify_no_support(
        self,
        hass: HomeAssistant,
        mock_okimat_config_entry,
        mock_coordinator_connected,
        caplog,
    ):
        """Test that Okimat doesn't support position notifications."""
        coordinator = AdjustableBedCoordinator(hass, mock_okimat_config_entry)
        await coordinator.async_connect()

        callback = MagicMock()
        await coordinator.controller.start_notify(callback)

        assert "don't support position notifications" in caplog.text

    async def test_read_positions_noop(
        self,
        hass: HomeAssistant,
        mock_okimat_config_entry,
        mock_coordinator_connected,
    ):
        """Test read_positions does nothing (not supported)."""
        coordinator = AdjustableBedCoordinator(hass, mock_okimat_config_entry)
        await coordinator.async_connect()

        # Should complete without error
        await coordinator.controller.read_positions()
