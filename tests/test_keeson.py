"""Tests for Keeson bed controller."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed.beds.keeson import (
    KeesonCommands,
    KeesonController,
    SinoCommands,
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
    KEESON_BASE_WRITE_CHAR_UUID,
)
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator


@pytest.fixture
def mock_keeson_config_entry_data() -> dict:
    """Return mock config entry data for Keeson bed."""
    return {
        CONF_ADDRESS: "AA:BB:CC:DD:EE:FF",
        CONF_NAME: "Keeson Test Bed",
        CONF_BED_TYPE: BED_TYPE_KEESON,
        CONF_MOTOR_COUNT: 2,
        CONF_HAS_MASSAGE: True,
        CONF_DISABLE_ANGLE_SENSING: True,
        CONF_PREFERRED_ADAPTER: "auto",
    }


@pytest.fixture
def mock_keeson_config_entry(
    hass: HomeAssistant, mock_keeson_config_entry_data: dict
) -> MockConfigEntry:
    """Return a mock config entry for Keeson bed."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Keeson Test Bed",
        data=mock_keeson_config_entry_data,
        unique_id="AA:BB:CC:DD:EE:FF",
        entry_id="keeson_test_entry",
    )
    entry.add_to_hass(hass)
    return entry


class TestKeesonController:
    """Test Keeson controller."""

    async def test_control_characteristic_uuid_base(
        self,
        hass: HomeAssistant,
        mock_keeson_config_entry,
        mock_coordinator_connected,
    ):
        """Test controller reports Base characteristic UUID."""
        coordinator = AdjustableBedCoordinator(hass, mock_keeson_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.control_characteristic_uuid == KEESON_BASE_WRITE_CHAR_UUID

    async def test_build_command_base(
        self,
        hass: HomeAssistant,
        mock_keeson_config_entry,
        mock_coordinator_connected,
    ):
        """Test Base variant command format."""
        coordinator = AdjustableBedCoordinator(hass, mock_keeson_config_entry)
        await coordinator.async_connect()

        # Build a command for HEAD_UP (0x1)
        command = coordinator.controller._build_command(KeesonCommands.MOTOR_HEAD_UP)

        # Base format: [0xe5, 0xfe, 0x16, ...reversed_int_bytes, checksum]
        assert len(command) == 8
        assert command[:3] == bytes([0xE5, 0xFE, 0x16])
        # Command 0x1 in little-endian
        assert command[3:7] == bytes([0x01, 0x00, 0x00, 0x00])

    async def test_build_command_ksbt(
        self,
        hass: HomeAssistant,
        mock_keeson_config_entry,
        mock_coordinator_connected,
    ):
        """Test KSBT variant command format."""
        coordinator = AdjustableBedCoordinator(hass, mock_keeson_config_entry)
        await coordinator.async_connect()

        # Create a KSBT controller directly
        controller = KeesonController(coordinator, variant="ksbt")

        # KSBT format: [0x04, 0x02, ...int_bytes]
        command = controller._build_command(KeesonCommands.MOTOR_HEAD_UP)

        assert len(command) == 6
        assert command[:2] == bytes([0x04, 0x02])
        # Command 0x1 in big-endian
        assert command[2:] == bytes([0x00, 0x00, 0x00, 0x01])

    async def test_write_command(
        self,
        hass: HomeAssistant,
        mock_keeson_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test writing a command to the bed."""
        coordinator = AdjustableBedCoordinator(hass, mock_keeson_config_entry)
        await coordinator.async_connect()

        command = coordinator.controller._build_command(0)
        await coordinator.controller.write_command(command)

        mock_bleak_client.write_gatt_char.assert_called_with(
            KEESON_BASE_WRITE_CHAR_UUID, command, response=True
        )

    async def test_write_command_not_connected(
        self,
        hass: HomeAssistant,
        mock_keeson_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test writing command when not connected raises error."""
        coordinator = AdjustableBedCoordinator(hass, mock_keeson_config_entry)
        await coordinator.async_connect()

        mock_bleak_client.is_connected = False

        with pytest.raises(ConnectionError):
            await coordinator.controller.write_command(coordinator.controller._build_command(0))


class TestKeesonMovement:
    """Test Keeson movement commands."""

    async def test_move_head_up(
        self,
        hass: HomeAssistant,
        mock_keeson_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test move head up sends commands followed by stop."""
        coordinator = AdjustableBedCoordinator(hass, mock_keeson_config_entry)
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
        mock_keeson_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test move head down."""
        coordinator = AdjustableBedCoordinator(hass, mock_keeson_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.move_head_down()

        calls = mock_bleak_client.write_gatt_char.call_args_list
        assert len(calls) > 1

    async def test_move_feet_up(
        self,
        hass: HomeAssistant,
        mock_keeson_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test move feet up."""
        coordinator = AdjustableBedCoordinator(hass, mock_keeson_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.move_feet_up()

        calls = mock_bleak_client.write_gatt_char.call_args_list
        assert len(calls) > 1

    async def test_stop_all(
        self,
        hass: HomeAssistant,
        mock_keeson_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test stop all sends zero command."""
        coordinator = AdjustableBedCoordinator(hass, mock_keeson_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.stop_all()

        expected_stop = coordinator.controller._build_command(0)
        mock_bleak_client.write_gatt_char.assert_called_with(
            KEESON_BASE_WRITE_CHAR_UUID, expected_stop, response=True
        )


class TestKeesonPresets:
    """Test Keeson preset commands."""

    async def test_preset_flat(
        self,
        hass: HomeAssistant,
        mock_keeson_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test preset flat command."""
        coordinator = AdjustableBedCoordinator(hass, mock_keeson_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.preset_flat()

        expected_cmd = coordinator.controller._build_command(KeesonCommands.PRESET_FLAT)
        first_call = mock_bleak_client.write_gatt_char.call_args_list[0]
        assert first_call[0][1] == expected_cmd

    async def test_preset_zero_g(
        self,
        hass: HomeAssistant,
        mock_keeson_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test preset zero gravity command."""
        coordinator = AdjustableBedCoordinator(hass, mock_keeson_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.preset_zero_g()

        expected_cmd = coordinator.controller._build_command(KeesonCommands.PRESET_ZERO_G)
        first_call = mock_bleak_client.write_gatt_char.call_args_list[0]
        assert first_call[0][1] == expected_cmd

    @pytest.mark.parametrize(
        "memory_num,expected_value",
        [
            (1, KeesonCommands.PRESET_MEMORY_1),
            (2, KeesonCommands.PRESET_MEMORY_2),
            (3, KeesonCommands.PRESET_MEMORY_3),
            (4, KeesonCommands.PRESET_MEMORY_4),
        ],
    )
    async def test_preset_memory(
        self,
        hass: HomeAssistant,
        mock_keeson_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
        memory_num: int,
        expected_value: int,
    ):
        """Test preset memory commands."""
        coordinator = AdjustableBedCoordinator(hass, mock_keeson_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.preset_memory(memory_num)

        expected_cmd = coordinator.controller._build_command(expected_value)
        first_call = mock_bleak_client.write_gatt_char.call_args_list[0]
        assert first_call[0][1] == expected_cmd

    async def test_program_memory_not_supported(
        self,
        hass: HomeAssistant,
        mock_keeson_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
        caplog,
    ):
        """Test program memory logs warning."""
        coordinator = AdjustableBedCoordinator(hass, mock_keeson_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.program_memory(1)

        assert "don't support programming memory presets" in caplog.text


class TestKeesonLights:
    """Test Keeson light commands."""

    async def test_lights_toggle(
        self,
        hass: HomeAssistant,
        mock_keeson_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test lights toggle command."""
        coordinator = AdjustableBedCoordinator(hass, mock_keeson_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.lights_toggle()

        expected_cmd = coordinator.controller._build_command(KeesonCommands.TOGGLE_SAFETY_LIGHTS)
        mock_bleak_client.write_gatt_char.assert_called_with(
            KEESON_BASE_WRITE_CHAR_UUID, expected_cmd, response=True
        )

    async def test_sino_lights_toggle_tracks_state(
        self,
        hass: HomeAssistant,
        mock_keeson_config_entry_data: dict,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test Sino lights_toggle alternates on/off using tracked state."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            title="Keeson Sino Test Bed",
            data={
                **mock_keeson_config_entry_data,
                CONF_PROTOCOL_VARIANT: "sino",
            },
            unique_id="AA:BB:CC:DD:EE:FF",
            entry_id="keeson_sino_lights_toggle",
        )
        entry.add_to_hass(hass)
        coordinator = AdjustableBedCoordinator(hass, entry)
        await coordinator.async_connect()

        await coordinator.controller.lights_toggle()
        assert coordinator.controller.led_on is True
        first_call = mock_bleak_client.write_gatt_char.call_args_list[-1]
        assert first_call[0][1] == coordinator.controller._build_command(SinoCommands.LIGHT_ON)

        await coordinator.controller.lights_toggle()
        assert coordinator.controller.led_on is False
        second_call = mock_bleak_client.write_gatt_char.call_args_list[-1]
        assert second_call[0][1] == coordinator.controller._build_command(SinoCommands.LIGHT_OFF)

    async def test_sino_lights_on_off_updates_led_state(
        self,
        hass: HomeAssistant,
        mock_keeson_config_entry_data: dict,
        mock_coordinator_connected,
    ):
        """Test Sino lights_on/lights_off keep tracked LED state in sync."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            title="Keeson Sino Test Bed",
            data={
                **mock_keeson_config_entry_data,
                CONF_PROTOCOL_VARIANT: "sino",
            },
            unique_id="AA:BB:CC:DD:EE:FF",
            entry_id="keeson_sino_lights_discrete",
        )
        entry.add_to_hass(hass)
        coordinator = AdjustableBedCoordinator(hass, entry)
        await coordinator.async_connect()

        await coordinator.controller.lights_on()
        assert coordinator.controller.led_on is True
        await coordinator.controller.lights_off()
        assert coordinator.controller.led_on is False

    async def test_legacy_ore_variant_maps_to_sino(
        self,
        hass: HomeAssistant,
        mock_keeson_config_entry_data: dict,
        mock_coordinator_connected,
    ):
        """Test legacy 'ore' protocol variant is normalized to Sino controller behavior."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            title="Keeson ORE Alias Test Bed",
            data={
                **mock_keeson_config_entry_data,
                CONF_PROTOCOL_VARIANT: "ore",
            },
            unique_id="AA:BB:CC:DD:EE:FF",
            entry_id="keeson_ore_alias",
        )
        entry.add_to_hass(hass)
        coordinator = AdjustableBedCoordinator(hass, entry)
        await coordinator.async_connect()

        assert isinstance(coordinator.controller, KeesonController)
        assert coordinator.controller._variant == "sino"


class TestKeesonMassage:
    """Test Keeson massage commands."""

    async def test_massage_toggle(
        self,
        hass: HomeAssistant,
        mock_keeson_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test massage toggle command."""
        coordinator = AdjustableBedCoordinator(hass, mock_keeson_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.massage_toggle()

        expected_cmd = coordinator.controller._build_command(KeesonCommands.MASSAGE_STEP)
        mock_bleak_client.write_gatt_char.assert_called_with(
            KEESON_BASE_WRITE_CHAR_UUID, expected_cmd, response=True
        )

    async def test_massage_head_up(
        self,
        hass: HomeAssistant,
        mock_keeson_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test head massage intensity up."""
        coordinator = AdjustableBedCoordinator(hass, mock_keeson_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.massage_head_up()

        expected_cmd = coordinator.controller._build_command(KeesonCommands.MASSAGE_HEAD_UP)
        mock_bleak_client.write_gatt_char.assert_called_with(
            KEESON_BASE_WRITE_CHAR_UUID, expected_cmd, response=True
        )

    async def test_massage_foot_down(
        self,
        hass: HomeAssistant,
        mock_keeson_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test foot massage intensity down."""
        coordinator = AdjustableBedCoordinator(hass, mock_keeson_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.massage_foot_down()

        expected_cmd = coordinator.controller._build_command(KeesonCommands.MASSAGE_FOOT_DOWN)
        mock_bleak_client.write_gatt_char.assert_called_with(
            KEESON_BASE_WRITE_CHAR_UUID, expected_cmd, response=True
        )


class TestSinoMassage:
    """Test Sino (Dynasty/INNOVA) massage commands with absolute intensity levels."""

    @pytest.fixture
    def sino_config_entry_data(self, mock_keeson_config_entry_data: dict) -> dict:
        """Return config entry data for Sino variant."""
        return {**mock_keeson_config_entry_data, CONF_PROTOCOL_VARIANT: "sino"}

    async def _make_coordinator(
        self,
        hass: HomeAssistant,
        sino_config_entry_data: dict,
        entry_id: str,
    ) -> AdjustableBedCoordinator:
        entry = MockConfigEntry(
            domain=DOMAIN,
            title="Sino Test Bed",
            data=sino_config_entry_data,
            unique_id="AA:BB:CC:DD:EE:FF",
            entry_id=entry_id,
        )
        entry.add_to_hass(hass)
        coordinator = AdjustableBedCoordinator(hass, entry)
        await coordinator.async_connect()
        return coordinator

    async def test_massage_head_up_sends_absolute_intensity(
        self,
        hass: HomeAssistant,
        sino_config_entry_data: dict,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test head up sends absolute intensity command (base + level)."""
        coordinator = await self._make_coordinator(hass, sino_config_entry_data, "sino_head_up")

        await coordinator.controller.massage_head_up()
        assert coordinator.controller._head_massage == 1
        expected = coordinator.controller._build_command(
            SinoCommands.MASSAGE_HEAD_INTENSITY_BASE + 1
        )
        mock_bleak_client.write_gatt_char.assert_called_with(
            coordinator.controller._char_uuid, expected, response=True
        )

        await coordinator.controller.massage_head_up()
        assert coordinator.controller._head_massage == 2
        expected = coordinator.controller._build_command(
            SinoCommands.MASSAGE_HEAD_INTENSITY_BASE + 2
        )
        mock_bleak_client.write_gatt_char.assert_called_with(
            coordinator.controller._char_uuid, expected, response=True
        )

    async def test_massage_head_down_sends_absolute_intensity(
        self,
        hass: HomeAssistant,
        sino_config_entry_data: dict,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test head down sends absolute intensity command."""
        coordinator = await self._make_coordinator(hass, sino_config_entry_data, "sino_head_down")
        coordinator.controller._head_massage = 3

        await coordinator.controller.massage_head_down()
        assert coordinator.controller._head_massage == 2
        expected = coordinator.controller._build_command(
            SinoCommands.MASSAGE_HEAD_INTENSITY_BASE + 2
        )
        mock_bleak_client.write_gatt_char.assert_called_with(
            coordinator.controller._char_uuid, expected, response=True
        )

    async def test_massage_foot_up_sends_absolute_intensity(
        self,
        hass: HomeAssistant,
        sino_config_entry_data: dict,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test foot up sends absolute intensity command."""
        coordinator = await self._make_coordinator(hass, sino_config_entry_data, "sino_foot_up")

        await coordinator.controller.massage_foot_up()
        assert coordinator.controller._foot_massage == 1
        expected = coordinator.controller._build_command(
            SinoCommands.MASSAGE_FOOT_INTENSITY_BASE + 1
        )
        mock_bleak_client.write_gatt_char.assert_called_with(
            coordinator.controller._char_uuid, expected, response=True
        )

    async def test_massage_foot_down_sends_absolute_intensity(
        self,
        hass: HomeAssistant,
        sino_config_entry_data: dict,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test foot down sends absolute intensity command."""
        coordinator = await self._make_coordinator(hass, sino_config_entry_data, "sino_foot_down")
        coordinator.controller._foot_massage = 5

        await coordinator.controller.massage_foot_down()
        assert coordinator.controller._foot_massage == 4
        expected = coordinator.controller._build_command(
            SinoCommands.MASSAGE_FOOT_INTENSITY_BASE + 4
        )
        mock_bleak_client.write_gatt_char.assert_called_with(
            coordinator.controller._char_uuid, expected, response=True
        )

    async def test_massage_off_sends_off_and_resets(
        self,
        hass: HomeAssistant,
        sino_config_entry_data: dict,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test massage_off sends zero intensity to both zones and resets tracked levels."""
        coordinator = await self._make_coordinator(hass, sino_config_entry_data, "sino_off")
        coordinator.controller._head_massage = 5
        coordinator.controller._foot_massage = 3

        await coordinator.controller.massage_off()

        assert coordinator.controller._head_massage == 0
        assert coordinator.controller._foot_massage == 0
        calls = mock_bleak_client.write_gatt_char.call_args_list
        head_off = coordinator.controller._build_command(SinoCommands.MASSAGE_HEAD_INTENSITY_BASE)
        foot_off = coordinator.controller._build_command(SinoCommands.MASSAGE_FOOT_INTENSITY_BASE)
        assert calls[-2][0][1] == head_off
        assert calls[-1][0][1] == foot_off

    async def test_massage_toggle_off_to_on(
        self,
        hass: HomeAssistant,
        sino_config_entry_data: dict,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test massage_toggle turns on both zones at level 1 when off."""
        coordinator = await self._make_coordinator(hass, sino_config_entry_data, "sino_toggle_on")

        await coordinator.controller.massage_toggle()

        assert coordinator.controller._head_massage == 1
        assert coordinator.controller._foot_massage == 1
        calls = mock_bleak_client.write_gatt_char.call_args_list
        head_cmd = coordinator.controller._build_command(
            SinoCommands.MASSAGE_HEAD_INTENSITY_BASE + 1
        )
        foot_cmd = coordinator.controller._build_command(
            SinoCommands.MASSAGE_FOOT_INTENSITY_BASE + 1
        )
        assert calls[-2][0][1] == head_cmd
        assert calls[-1][0][1] == foot_cmd

    async def test_massage_toggle_on_to_off(
        self,
        hass: HomeAssistant,
        sino_config_entry_data: dict,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test massage_toggle sends zero intensity to both zones when active."""
        coordinator = await self._make_coordinator(
            hass, sino_config_entry_data, "sino_toggle_off"
        )
        coordinator.controller._head_massage = 3

        await coordinator.controller.massage_toggle()

        assert coordinator.controller._head_massage == 0
        assert coordinator.controller._foot_massage == 0
        calls = mock_bleak_client.write_gatt_char.call_args_list
        head_off = coordinator.controller._build_command(SinoCommands.MASSAGE_HEAD_INTENSITY_BASE)
        foot_off = coordinator.controller._build_command(SinoCommands.MASSAGE_FOOT_INTENSITY_BASE)
        assert calls[-2][0][1] == head_off
        assert calls[-1][0][1] == foot_off

    async def test_massage_head_toggle_off_to_on(
        self,
        hass: HomeAssistant,
        sino_config_entry_data: dict,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test head toggle turns on at level 1 when off."""
        coordinator = await self._make_coordinator(
            hass, sino_config_entry_data, "sino_head_toggle_on"
        )

        await coordinator.controller.massage_head_toggle()

        assert coordinator.controller._head_massage == 1
        expected = coordinator.controller._build_command(
            SinoCommands.MASSAGE_HEAD_INTENSITY_BASE + 1
        )
        mock_bleak_client.write_gatt_char.assert_called_with(
            coordinator.controller._char_uuid, expected, response=True
        )

    async def test_massage_head_toggle_on_to_off(
        self,
        hass: HomeAssistant,
        sino_config_entry_data: dict,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test head toggle sends intensity 0 when on."""
        coordinator = await self._make_coordinator(
            hass, sino_config_entry_data, "sino_head_toggle_off"
        )
        coordinator.controller._head_massage = 5

        await coordinator.controller.massage_head_toggle()

        assert coordinator.controller._head_massage == 0
        expected = coordinator.controller._build_command(
            SinoCommands.MASSAGE_HEAD_INTENSITY_BASE
        )
        mock_bleak_client.write_gatt_char.assert_called_with(
            coordinator.controller._char_uuid, expected, response=True
        )

    async def test_massage_foot_toggle_off_to_on(
        self,
        hass: HomeAssistant,
        sino_config_entry_data: dict,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test foot toggle turns on at level 1 when off."""
        coordinator = await self._make_coordinator(
            hass, sino_config_entry_data, "sino_foot_toggle_on"
        )

        await coordinator.controller.massage_foot_toggle()

        assert coordinator.controller._foot_massage == 1
        expected = coordinator.controller._build_command(
            SinoCommands.MASSAGE_FOOT_INTENSITY_BASE + 1
        )
        mock_bleak_client.write_gatt_char.assert_called_with(
            coordinator.controller._char_uuid, expected, response=True
        )

    async def test_massage_foot_toggle_on_to_off(
        self,
        hass: HomeAssistant,
        sino_config_entry_data: dict,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test foot toggle sends intensity 0 when on."""
        coordinator = await self._make_coordinator(
            hass, sino_config_entry_data, "sino_foot_toggle_off"
        )
        coordinator.controller._foot_massage = 3

        await coordinator.controller.massage_foot_toggle()

        assert coordinator.controller._foot_massage == 0
        expected = coordinator.controller._build_command(
            SinoCommands.MASSAGE_FOOT_INTENSITY_BASE
        )
        mock_bleak_client.write_gatt_char.assert_called_with(
            coordinator.controller._char_uuid, expected, response=True
        )

    async def test_head_intensity_clamped_at_max(
        self,
        hass: HomeAssistant,
        sino_config_entry_data: dict,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test head intensity clamps at 10."""
        coordinator = await self._make_coordinator(hass, sino_config_entry_data, "sino_head_max")
        coordinator.controller._head_massage = 10

        await coordinator.controller.massage_head_up()

        assert coordinator.controller._head_massage == 10
        expected = coordinator.controller._build_command(
            SinoCommands.MASSAGE_HEAD_INTENSITY_BASE + 10
        )
        mock_bleak_client.write_gatt_char.assert_called_with(
            coordinator.controller._char_uuid, expected, response=True
        )

    async def test_head_intensity_clamped_at_min(
        self,
        hass: HomeAssistant,
        sino_config_entry_data: dict,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test head intensity clamps at 0."""
        coordinator = await self._make_coordinator(hass, sino_config_entry_data, "sino_head_min")

        await coordinator.controller.massage_head_down()

        assert coordinator.controller._head_massage == 0
        expected = coordinator.controller._build_command(
            SinoCommands.MASSAGE_HEAD_INTENSITY_BASE
        )
        mock_bleak_client.write_gatt_char.assert_called_with(
            coordinator.controller._char_uuid, expected, response=True
        )

    async def test_massage_mode_step_cycles_wave_patterns(
        self,
        hass: HomeAssistant,
        sino_config_entry_data: dict,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test mode step cycles through wave patterns 1-10."""
        coordinator = await self._make_coordinator(hass, sino_config_entry_data, "sino_wave")

        await coordinator.controller.massage_mode_step()
        assert coordinator.controller._wave_massage == 1
        expected = coordinator.controller._build_command(
            SinoCommands.MASSAGE_HEAD_WAVE_BASE + 1
        )
        mock_bleak_client.write_gatt_char.assert_called_with(
            coordinator.controller._char_uuid, expected, response=True
        )

        # At level 10, wraps to 1
        coordinator.controller._wave_massage = 10
        coordinator.controller._head_massage = 4
        await coordinator.controller.massage_mode_step()
        assert coordinator.controller._wave_massage == 1
        assert coordinator.controller._head_massage == 4
        expected = coordinator.controller._build_command(
            SinoCommands.MASSAGE_HEAD_WAVE_BASE + 1
        )
        mock_bleak_client.write_gatt_char.assert_called_with(
            coordinator.controller._char_uuid, expected, response=True
        )


class TestKeesonPositionNotifications:
    """Test Keeson position notification handling."""

    async def test_start_notify_no_support(
        self,
        hass: HomeAssistant,
        mock_keeson_config_entry,
        mock_coordinator_connected,
    ):
        """Test start_notify stores callback for non-ergomotion variant."""
        coordinator = AdjustableBedCoordinator(hass, mock_keeson_config_entry)
        await coordinator.async_connect()

        callback = MagicMock()
        await coordinator.controller.start_notify(callback)

        assert coordinator.controller._notify_callback is callback
