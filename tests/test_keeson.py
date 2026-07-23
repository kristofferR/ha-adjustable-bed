"""Tests for Keeson bed controller."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, call

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
    KEESON_JSON_WRITE_CHAR_UUID,
    KEESON_KSBT_CHAR_UUID,
    KEESON_VARIANT_JSON,
    KEESON_VARIANT_KSBT04C,
    KEESON_VARIANT_PURPLE,
    KEESON_VARIANT_SLEEP_HARMONY,
    VARIANT_AUTO,
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

    async def test_build_command_ksbt04c(
        self,
        hass: HomeAssistant,
        mock_keeson_config_entry,
        mock_coordinator_connected,
    ):
        """Test KSBT04C variant command format (7-byte with checksum)."""
        coordinator = AdjustableBedCoordinator(hass, mock_keeson_config_entry)
        await coordinator.async_connect()

        controller = KeesonController(coordinator, variant="ksbt04c")

        # KSBT04C format: [0x04, 0x02, ...int_bytes, checksum]
        # checksum = ~(sum of bytes 0-5) & 0xFF
        command = controller._build_command(KeesonCommands.MOTOR_HEAD_UP)

        assert len(command) == 7
        assert command[:2] == bytes([0x04, 0x02])
        assert command[2:6] == bytes([0x00, 0x00, 0x00, 0x01])
        # Checksum: ~(0x04 + 0x02 + 0x00 + 0x00 + 0x00 + 0x01) = ~0x07 = 0xF8
        assert command[6] == 0xF8

        # Test FLAT preset (0x8000000)
        flat_cmd = controller._build_command(KeesonCommands.PRESET_FLAT)
        assert len(flat_cmd) == 7
        assert flat_cmd[:2] == bytes([0x04, 0x02])
        assert flat_cmd[2:6] == bytes([0x08, 0x00, 0x00, 0x00])
        # Checksum: ~(0x04 + 0x02 + 0x08) = ~0x0E = 0xF1
        assert flat_cmd[6] == 0xF1

        # Test STOP (0x00)
        stop_cmd = controller._build_command(0)
        assert len(stop_cmd) == 7
        assert stop_cmd[:6] == bytes([0x04, 0x02, 0x00, 0x00, 0x00, 0x00])
        # Checksum: ~(0x04 + 0x02) = ~0x06 = 0xF9
        assert stop_cmd[6] == 0xF9

    @pytest.mark.usefixtures("mock_coordinator_connected")
    async def test_build_command_json_variant(
        self,
        hass: HomeAssistant,
        mock_keeson_config_entry,
    ):
        """Test JSON/A00A variant command envelope."""
        coordinator = AdjustableBedCoordinator(hass, mock_keeson_config_entry)
        await coordinator.async_connect()

        controller = KeesonController(coordinator, variant=KEESON_VARIANT_JSON)

        command = controller._build_command(KeesonCommands.PRESET_ZERO_G)
        payload = json.loads(command.decode())

        assert controller.control_characteristic_uuid == KEESON_JSON_WRITE_CHAR_UUID
        assert payload["code"] == 2
        assert payload["cmd"] == {
            "key": "00001000",
            "ctrm": 1,
            "km": 1,
            "keykt": 0,
        }

        stop_command = controller._build_command(0)
        stop_payload = json.loads(stop_command.decode())
        assert stop_payload["cmd"] == {
            "key": "00000000",
            "ctrm": 0,
            "km": 1,
            "keykt": 0,
        }

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

    async def test_write_command_prefers_write_with_response_when_both_modes_exist(
        self,
        hass: HomeAssistant,
        mock_keeson_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Dual-mode characteristics should keep write-with-response enabled."""
        coordinator = AdjustableBedCoordinator(hass, mock_keeson_config_entry)
        await coordinator.async_connect()

        controller = KeesonController(coordinator, variant=KEESON_VARIANT_JSON)
        mock_bleak_client.services = [
            SimpleNamespace(
                characteristics=[
                    SimpleNamespace(
                        uuid=KEESON_JSON_WRITE_CHAR_UUID,
                        properties=["write", "write-without-response"],
                    )
                ]
            )
        ]

        command = controller._build_command(KeesonCommands.PRESET_ZERO_G)
        await controller.write_command(command)

        mock_bleak_client.write_gatt_char.assert_called_with(
            KEESON_JSON_WRITE_CHAR_UUID, command, response=True
        )

    async def test_ksbt03c_write_command_uses_no_response_when_supported(
        self,
        hass: HomeAssistant,
        mock_keeson_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """KSBT03C should match Ergomotion Sync's Android-default write mode."""
        coordinator = AdjustableBedCoordinator(hass, mock_keeson_config_entry)
        await coordinator.async_connect()

        controller = KeesonController(
            coordinator,
            variant="ksbt",
            device_name="KSBT03C300039050",
        )
        mock_bleak_client.services = [
            SimpleNamespace(
                characteristics=[
                    SimpleNamespace(
                        uuid=KEESON_KSBT_CHAR_UUID,
                        properties=["write", "write-without-response"],
                    )
                ]
            )
        ]

        command = controller._build_command(KeesonCommands.MOTOR_HEAD_UP)
        await controller.write_command(command)

        mock_bleak_client.write_gatt_char.assert_called_with(
            KEESON_KSBT_CHAR_UUID,
            command,
            response=False,
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

    async def test_write_command_honors_default_cancellation(
        self,
        hass: HomeAssistant,
        mock_keeson_config_entry,
        mock_coordinator_connected,
    ):
        """Test an omitted event uses the coordinator cancellation state."""
        coordinator = AdjustableBedCoordinator(hass, mock_keeson_config_entry)
        await coordinator.async_connect()
        coordinator.cancel_command.set()
        controller = coordinator.controller
        controller._write_gatt_with_retry = AsyncMock()

        await controller.write_command(controller._build_command(0))

        controller._write_gatt_with_retry.assert_not_awaited()

    async def test_write_command_preserves_explicit_release_event(
        self,
        hass: HomeAssistant,
        mock_keeson_config_entry,
        mock_coordinator_connected,
    ):
        """Test a fresh explicit event bypasses stale command cancellation."""
        coordinator = AdjustableBedCoordinator(hass, mock_keeson_config_entry)
        await coordinator.async_connect()
        coordinator.cancel_command.set()
        controller = coordinator.controller
        controller._write_gatt_with_retry = AsyncMock()
        release_event = asyncio.Event()
        command = controller._build_command(0)

        await controller.write_command(command, cancel_event=release_event)

        controller._write_gatt_with_retry.assert_awaited_once()
        assert (
            controller._write_gatt_with_retry.await_args.kwargs["cancel_event"]
            is release_event
        )


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

    @pytest.mark.usefixtures("mock_coordinator_connected")
    async def test_move_head_up_json_variant_uses_dual_motion_modes(
        self,
        hass: HomeAssistant,
        mock_keeson_config_entry,
        mock_bleak_client: MagicMock,
    ):
        """JSON/A00A movement should send both known held-motion ctrm variants."""
        coordinator = AdjustableBedCoordinator(hass, mock_keeson_config_entry)
        await coordinator.async_connect()
        controller = KeesonController(coordinator, variant=KEESON_VARIANT_JSON)

        await controller.move_head_up()

        calls = mock_bleak_client.write_gatt_char.call_args_list
        payloads = [json.loads(call.args[1].decode()) for call in calls]
        motion_payloads = [payload for payload in payloads if payload["cmd"]["key"] == "00000001"]

        assert motion_payloads
        assert {payload["cmd"]["ctrm"] for payload in motion_payloads} == {0, 1}
        assert payloads[-1]["cmd"] == {
            "key": "00000000",
            "ctrm": 0,
            "km": 1,
            "keykt": 0,
        }


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
        ("preset_method", "expected_key"),
        [
            ("preset_lounge", "00002000"),
            ("preset_anti_snore", "00008000"),
        ],
    )
    @pytest.mark.usefixtures("mock_coordinator_connected")
    async def test_json_presets_use_expected_command_keys(
        self,
        hass: HomeAssistant,
        mock_keeson_config_entry,
        mock_bleak_client: MagicMock,
        preset_method: str,
        expected_key: str,
    ):
        """JSON/A00A presets should send the shared one-shot command envelope."""
        coordinator = AdjustableBedCoordinator(hass, mock_keeson_config_entry)
        await coordinator.async_connect()
        controller = KeesonController(coordinator, variant=KEESON_VARIANT_JSON)

        await getattr(controller, preset_method)()

        payload = json.loads(mock_bleak_client.write_gatt_char.call_args.args[1].decode())
        assert payload["cmd"] == {
            "key": expected_key,
            "ctrm": 1,
            "km": 1,
            "keykt": 0,
        }

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
        coordinator = await self._make_coordinator(hass, sino_config_entry_data, "sino_toggle_off")
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
        expected = coordinator.controller._build_command(SinoCommands.MASSAGE_HEAD_INTENSITY_BASE)
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
        expected = coordinator.controller._build_command(SinoCommands.MASSAGE_FOOT_INTENSITY_BASE)
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
        expected = coordinator.controller._build_command(SinoCommands.MASSAGE_HEAD_INTENSITY_BASE)
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
        expected = coordinator.controller._build_command(SinoCommands.MASSAGE_HEAD_WAVE_BASE + 1)
        mock_bleak_client.write_gatt_char.assert_called_with(
            coordinator.controller._char_uuid, expected, response=True
        )

        # At level 10, wraps to 1
        coordinator.controller._wave_massage = 10
        coordinator.controller._head_massage = 4
        await coordinator.controller.massage_mode_step()
        assert coordinator.controller._wave_massage == 1
        assert coordinator.controller._head_massage == 4
        expected = coordinator.controller._build_command(SinoCommands.MASSAGE_HEAD_WAVE_BASE + 1)
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


class TestPurpleSmartBaseProtocol:
    """Test current Purple Premium and Premium Plus protocol variants."""

    async def test_premium_and_plus_build_distinct_packets(
        self,
        hass: HomeAssistant,
        mock_keeson_config_entry,
        mock_coordinator_connected,
    ):
        """Test Premium uses checksummed P1 and Plus uses zero-suffixed P2."""
        coordinator = AdjustableBedCoordinator(hass, mock_keeson_config_entry)
        await coordinator.async_connect()

        premium = KeesonController(coordinator, variant="purple", device_name="base-i5.123456")
        plus = KeesonController(coordinator, variant="purple", device_name="KSBT04C123456789")

        assert premium._build_command(KeesonCommands.MOTOR_HEAD_UP) == bytes.fromhex(
            "e5fe160100000005"
        )
        assert plus._build_command(KeesonCommands.MOTOR_HEAD_UP) == bytes.fromhex("04020000000100")
        assert plus.control_characteristic_uuid == KEESON_KSBT_CHAR_UUID

    async def test_plus_capabilities_and_memory_map(
        self,
        hass: HomeAssistant,
        mock_keeson_config_entry,
        mock_coordinator_connected,
    ):
        """Test Purple Plus exposes three proven slots and no lounge action."""
        coordinator = AdjustableBedCoordinator(hass, mock_keeson_config_entry)
        await coordinator.async_connect()
        premium = KeesonController(coordinator, variant="purple", device_name="base-i5.123456")
        plus = KeesonController(coordinator, variant="purple", device_name="KSBT04C123456789")
        plus.write_command = AsyncMock()

        assert premium.memory_slot_count == 2
        assert premium.supports_preset_lounge
        assert not premium.supports_lights
        assert plus.memory_slot_count == 3
        assert not plus.supports_preset_lounge
        assert plus.supports_lights

        for memory_num in (1, 2, 3):
            await plus.preset_memory(memory_num)

        assert [call.args[0] for call in plus.write_command.await_args_list] == [
            bytes.fromhex("04020001000000"),
            bytes.fromhex("04020000000000"),
            bytes.fromhex("04020000200000"),
            bytes.fromhex("04020000000000"),
            bytes.fromhex("04020000400000"),
            bytes.fromhex("04020000000000"),
        ]

    @pytest.mark.parametrize("device_name", ["base-i5.123456", "KSBT04C123456789"])
    async def test_purple_release_uses_p2_zero_frame(
        self,
        hass: HomeAssistant,
        mock_keeson_config_entry,
        mock_coordinator_connected,
        device_name: str,
    ):
        """Test both Purple surfaces release with the artifact's P2 STOP."""
        coordinator = AdjustableBedCoordinator(hass, mock_keeson_config_entry)
        await coordinator.async_connect()
        controller = KeesonController(coordinator, variant="purple", device_name=device_name)
        controller.write_command = AsyncMock()

        await controller.stop_all()

        assert controller.write_command.await_args.args == (bytes.fromhex("04020000000000"),)
        cancel_event = controller.write_command.await_args.kwargs["cancel_event"]
        assert isinstance(cancel_event, asyncio.Event)
        assert not cancel_event.is_set()

    async def test_plus_light_toggle_appends_release(
        self,
        hass: HomeAssistant,
        mock_keeson_config_entry,
        mock_coordinator_connected,
    ):
        """Test Purple Plus light toggles append the required zero-mask frame."""
        coordinator = AdjustableBedCoordinator(hass, mock_keeson_config_entry)
        await coordinator.async_connect()
        controller = KeesonController(
            coordinator,
            variant=KEESON_VARIANT_PURPLE,
            device_name="KSBT04C123456789",
        )
        controller.write_command = AsyncMock()

        await controller.lights_toggle()

        assert [call.args[0] for call in controller.write_command.await_args_list] == [
            bytes.fromhex("04020002000000"),
            bytes.fromhex("04020000000000"),
        ]

    @pytest.mark.parametrize(
        ("variant", "device_name", "expected_release", "expected_delays"),
        [
            (
                KEESON_VARIANT_PURPLE,
                "KSBT04C123456789",
                bytes.fromhex("04020000000000"),
                [],
            ),
            (
                KEESON_VARIANT_SLEEP_HARMONY,
                "KSBT04C123456789",
                bytes.fromhex("040200000000f9"),
                [(0.2,)],
            ),
        ],
    )
    async def test_one_shot_cleanup_runs_after_write_failure(
        self,
        hass: HomeAssistant,
        mock_keeson_config_entry,
        mock_coordinator_connected,
        monkeypatch: pytest.MonkeyPatch,
        variant: str,
        device_name: str,
        expected_release: bytes,
        expected_delays: list[tuple[float]],
    ):
        """Test app-required one-shot releases run from a finally block."""
        coordinator = AdjustableBedCoordinator(hass, mock_keeson_config_entry)
        await coordinator.async_connect()
        controller = KeesonController(
            coordinator,
            variant=variant,
            device_name=device_name,
        )
        controller.write_command = AsyncMock(side_effect=[RuntimeError("write failed"), None])
        sleep = AsyncMock()
        monkeypatch.setattr(
            "custom_components.adjustable_bed.beds.keeson.asyncio.sleep",
            sleep,
        )

        with pytest.raises(RuntimeError, match="write failed"):
            await controller.preset_zero_g()

        calls = controller.write_command.await_args_list
        assert len(calls) == 2
        assert calls[1].args == (expected_release,)
        release_event = calls[1].kwargs["cancel_event"]
        assert isinstance(release_event, asyncio.Event)
        assert release_event is not coordinator.cancel_command
        assert not release_event.is_set()
        assert [call.args for call in sleep.await_args_list] == expected_delays

    async def test_plus_program_memory_matches_send_memory_sequence(
        self,
        hass: HomeAssistant,
        mock_keeson_config_entry,
        mock_coordinator_connected,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """Test Plus memory 2 save performs 26 delayed P2 writes."""
        coordinator = AdjustableBedCoordinator(hass, mock_keeson_config_entry)
        await coordinator.async_connect()
        coordinator.cancel_command.clear()
        controller = KeesonController(coordinator, variant="purple", device_name="KSBT04C123456789")
        controller.write_command = AsyncMock()
        sleep = AsyncMock()
        monkeypatch.setattr(
            "custom_components.adjustable_bed.beds.keeson.asyncio.sleep",
            sleep,
        )

        await controller.program_memory(2)

        assert controller.write_command.await_count == 26
        assert all(
            call.args == (bytes.fromhex("04020000200000"),)
            for call in controller.write_command.await_args_list
        )
        assert [call.args for call in sleep.await_args_list] == [(0.2,)] * 26


class TestSleepHarmonyProtocol:
    """Test current Sleep Harmony protocol routing and release behavior."""

    async def test_base_i5_uses_side_zero_p2_packet(
        self,
        hass: HomeAssistant,
        mock_keeson_config_entry,
        mock_coordinator_connected,
    ):
        """Test explicit Sleep Harmony base-i5 uses E6 plus side zero."""
        coordinator = AdjustableBedCoordinator(hass, mock_keeson_config_entry)
        await coordinator.async_connect()
        controller = KeesonController(
            coordinator,
            variant=KEESON_VARIANT_SLEEP_HARMONY,
            device_name="base-i5.123456",
        )

        assert controller._build_command(KeesonCommands.MOTOR_HEAD_UP) == bytes.fromhex(
            "e6fe16010000000004"
        )
        assert controller._build_command(0) == bytes.fromhex("e6fe16000000000005")
        assert controller.control_characteristic_uuid == KEESON_BASE_WRITE_CHAR_UUID

    async def test_motor_hold_and_delayed_release_match_remote(
        self,
        hass: HomeAssistant,
        mock_keeson_config_entry,
        mock_coordinator_connected,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """Test Sleep Harmony repeats at 300 ms and stops after 200 ms."""
        coordinator = AdjustableBedCoordinator(hass, mock_keeson_config_entry)
        await coordinator.async_connect()
        controller = KeesonController(
            coordinator,
            variant=KEESON_VARIANT_SLEEP_HARMONY,
            device_name="KSBT04C123456789",
        )
        controller.write_command = AsyncMock()
        sleep = AsyncMock()
        monkeypatch.setattr(
            "custom_components.adjustable_bed.beds.keeson.asyncio.sleep",
            sleep,
        )

        await controller.move_head_up()

        calls = controller.write_command.await_args_list
        assert calls[0].args == (bytes.fromhex("040200000001f8"),)
        assert calls[0].kwargs == {
            "repeat_count": 4,
            "repeat_delay_ms": 300,
        }
        assert calls[1].args == (bytes.fromhex("040200000000f9"),)
        assert isinstance(calls[1].kwargs["cancel_event"], asyncio.Event)
        sleep.assert_awaited_once_with(0.2)

    async def test_memory_three_and_massage_off_append_delayed_stop(
        self,
        hass: HomeAssistant,
        mock_keeson_config_entry,
        mock_coordinator_connected,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """Test recovered M3 and massage-off actions each release with STOP."""
        coordinator = AdjustableBedCoordinator(hass, mock_keeson_config_entry)
        await coordinator.async_connect()
        controller = KeesonController(
            coordinator,
            variant=KEESON_VARIANT_SLEEP_HARMONY,
            device_name="KSBT04C123456789",
        )
        controller.write_command = AsyncMock()
        sleep = AsyncMock()
        monkeypatch.setattr(
            "custom_components.adjustable_bed.beds.keeson.asyncio.sleep",
            sleep,
        )

        assert controller.supports_massage_off_control
        await controller.preset_memory(3)
        await controller.massage_off()

        assert [call.args[0] for call in controller.write_command.await_args_list] == [
            bytes.fromhex("04020000800079"),
            bytes.fromhex("040200000000f9"),
            bytes.fromhex("040202000000f7"),
            bytes.fromhex("040200000000f9"),
        ]
        assert [call.args for call in sleep.await_args_list] == [(0.2,), (0.2,)]

    async def test_all_zone_massage_steps_each_append_delayed_stop(
        self,
        hass: HomeAssistant,
        mock_keeson_config_entry,
        mock_coordinator_connected,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """Test aggregate massage controls release each Sleep Harmony key."""
        coordinator = AdjustableBedCoordinator(hass, mock_keeson_config_entry)
        await coordinator.async_connect()
        controller = KeesonController(
            coordinator,
            variant=KEESON_VARIANT_SLEEP_HARMONY,
            device_name="KSBT04C123456789",
        )
        controller.write_command = AsyncMock()
        sleep = AsyncMock()
        monkeypatch.setattr(
            "custom_components.adjustable_bed.beds.keeson.asyncio.sleep",
            sleep,
        )

        await controller.massage_intensity_up()

        assert [call.args[0] for call in controller.write_command.await_args_list] == [
            bytes.fromhex("040200000800f1"),
            bytes.fromhex("040200000000f9"),
            bytes.fromhex("040200000400f5"),
            bytes.fromhex("040200000000f9"),
        ]
        assert [call.args for call in sleep.await_args_list] == [(0.2,), (0.2,)]

    async def test_stop_all_sends_immediate_sleep_harmony_stop(
        self,
        hass: HomeAssistant,
        mock_keeson_config_entry,
        mock_coordinator_connected,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """Test the safety stop bypasses the UI release delay."""
        coordinator = AdjustableBedCoordinator(hass, mock_keeson_config_entry)
        await coordinator.async_connect()
        controller = KeesonController(
            coordinator,
            variant=KEESON_VARIANT_SLEEP_HARMONY,
            device_name="KSBT04C123456789",
        )
        controller.write_command = AsyncMock()
        sleep = AsyncMock()
        monkeypatch.setattr(
            "custom_components.adjustable_bed.beds.keeson.asyncio.sleep",
            sleep,
        )

        await controller.stop_all()

        controller.write_command.assert_awaited_once()
        assert controller.write_command.await_args.args == (bytes.fromhex("040200000000f9"),)
        sleep.assert_not_awaited()


class TestKsbt03cMotorLayout:
    """Test KSBT03C (Ergomotion RIO 5.0) motor layout handling (issue #408)."""

    def test_is_ksbt03c_name(self):
        """Test KSBT03C name detection."""
        from custom_components.adjustable_bed.beds.keeson import is_ksbt03c_name

        assert is_ksbt03c_name("KSBT03C300039050")
        assert is_ksbt03c_name("ksbt03c123")
        assert not is_ksbt03c_name("KSBT03CR12345")
        assert not is_ksbt03c_name("KSBT04C300039050")
        assert not is_ksbt03c_name("KSBT123456")
        assert not is_ksbt03c_name(None)
        assert not is_ksbt03c_name("")

    async def test_ksbt03c_three_motors_third_is_lumbar(
        self,
        hass: HomeAssistant,
        mock_keeson_config_entry,
        mock_coordinator_connected,
    ):
        """Test KSBT03C with 3 motors exposes lumbar (not tilt) as third motor."""
        coordinator = AdjustableBedCoordinator(hass, mock_keeson_config_entry)
        await coordinator.async_connect()
        coordinator._motor_count = 3

        controller = KeesonController(coordinator, variant="ksbt", device_name="KSBT03C300039050")

        assert not controller.has_tilt_support
        keys = [spec.key for spec in controller.motor_control_specs]
        assert keys == ["head", "feet", "lumbar"]

    async def test_ksbt03c_four_motors_has_no_phantom_tilt(
        self,
        hass: HomeAssistant,
        mock_keeson_config_entry,
        mock_coordinator_connected,
    ):
        """Test KSBT03C with 4 configured motors still has no tilt motor."""
        coordinator = AdjustableBedCoordinator(hass, mock_keeson_config_entry)
        await coordinator.async_connect()
        coordinator._motor_count = 4

        controller = KeesonController(coordinator, variant="ksbt", device_name="KSBT03C300039050")

        keys = [spec.key for spec in controller.motor_control_specs]
        assert keys == ["head", "feet", "lumbar"]

    async def test_ksbt03c_detected_from_configured_name(
        self,
        hass: HomeAssistant,
        mock_keeson_config_entry_data: dict,
        mock_coordinator_connected,
    ):
        """Test KSBT03C layout falls back to the configured name via the factory."""
        from custom_components.adjustable_bed.const import KEESON_VARIANT_KSBT
        from custom_components.adjustable_bed.controller_factory import create_controller

        mock_keeson_config_entry_data[CONF_NAME] = "KSBT03C300039050"
        entry = MockConfigEntry(
            domain=DOMAIN,
            title="KSBT03C300039050",
            data=mock_keeson_config_entry_data,
            unique_id="AA:BB:CC:DD:EE:F0",
            entry_id="keeson_ksbt03c_entry",
        )
        entry.add_to_hass(hass)
        coordinator = AdjustableBedCoordinator(hass, entry)
        await coordinator.async_connect()
        coordinator._motor_count = 3

        controller = await create_controller(
            coordinator=coordinator,
            bed_type=BED_TYPE_KEESON,
            protocol_variant=KEESON_VARIANT_KSBT,
            client=coordinator.client,
            device_name=None,
        )

        assert isinstance(controller, KeesonController)
        assert controller._variant == "ksbt"
        assert not controller.has_tilt_support
        assert [spec.key for spec in controller.motor_control_specs] == [
            "head",
            "feet",
            "lumbar",
        ]

    async def test_ksbt03c_detected_from_ble_name_via_factory(
        self,
        hass: HomeAssistant,
        mock_keeson_config_entry,
        mock_coordinator_connected,
    ):
        """Test the factory auto-detects the ksbt variant and KSBT03C layout from the BLE name."""
        from custom_components.adjustable_bed.controller_factory import create_controller

        coordinator = AdjustableBedCoordinator(hass, mock_keeson_config_entry)
        await coordinator.async_connect()
        coordinator._motor_count = 3

        controller = await create_controller(
            coordinator=coordinator,
            bed_type=BED_TYPE_KEESON,
            protocol_variant="auto",
            client=coordinator.client,
            device_name="KSBT03C300039050",
        )

        assert isinstance(controller, KeesonController)
        assert controller._variant == "ksbt"
        assert not controller.has_tilt_support
        assert [spec.key for spec in controller.motor_control_specs] == [
            "head",
            "feet",
            "lumbar",
        ]

    async def test_ambiguous_ksbt04c_name_keeps_legacy_generic_profile(
        self,
        hass: HomeAssistant,
        mock_keeson_config_entry,
        mock_coordinator_connected,
        caplog,
    ):
        """Test an ambiguous name does not silently select Sleep Harmony."""
        from custom_components.adjustable_bed.controller_factory import create_controller

        coordinator = AdjustableBedCoordinator(hass, mock_keeson_config_entry)
        await coordinator.async_connect()

        controller = await create_controller(
            coordinator=coordinator,
            bed_type=BED_TYPE_KEESON,
            protocol_variant=VARIANT_AUTO,
            client=coordinator.client,
            device_name="KSBT04C123456789",
        )

        assert isinstance(controller, KeesonController)
        assert controller._variant == KEESON_VARIANT_KSBT04C
        assert not controller._is_sleep_harmony
        assert "ambiguous name" in caplog.text

    async def test_factory_selects_sleep_harmony_only_when_explicit(
        self,
        hass: HomeAssistant,
        mock_keeson_config_entry,
        mock_coordinator_connected,
    ):
        """Test the Sleep Harmony profile requires explicit selection."""
        from custom_components.adjustable_bed.controller_factory import create_controller

        coordinator = AdjustableBedCoordinator(hass, mock_keeson_config_entry)
        await coordinator.async_connect()

        controller = await create_controller(
            coordinator=coordinator,
            bed_type=BED_TYPE_KEESON,
            protocol_variant=KEESON_VARIANT_SLEEP_HARMONY,
            client=coordinator.client,
            device_name="KSBT04C123456789",
        )

        assert isinstance(controller, KeesonController)
        assert controller._variant == KEESON_VARIANT_SLEEP_HARMONY
        assert controller._is_sleep_harmony

    async def test_present_device_name_overrides_configured_name(
        self,
        hass: HomeAssistant,
        mock_keeson_config_entry_data: dict,
        mock_coordinator_connected,
    ):
        """Test a non-KSBT03C raw BLE name wins over a stale KSBT03C configured name."""
        mock_keeson_config_entry_data[CONF_NAME] = "KSBT03C300039050"
        entry = MockConfigEntry(
            domain=DOMAIN,
            title="KSBT03C300039050",
            data=mock_keeson_config_entry_data,
            unique_id="AA:BB:CC:DD:EE:F1",
            entry_id="keeson_stale_name_entry",
        )
        entry.add_to_hass(hass)
        coordinator = AdjustableBedCoordinator(hass, entry)
        await coordinator.async_connect()

        controller = KeesonController(coordinator, variant="ksbt_cr", device_name="KSBT03CR12345")

        assert controller.has_tilt_support

    async def test_standard_keeson_motor_layout_unchanged(
        self,
        hass: HomeAssistant,
        mock_keeson_config_entry,
        mock_coordinator_connected,
    ):
        """Test non-KSBT03C beds keep tilt as third and lumbar as fourth motor."""
        coordinator = AdjustableBedCoordinator(hass, mock_keeson_config_entry)
        await coordinator.async_connect()
        controller = coordinator.controller
        assert controller.has_tilt_support

        coordinator._motor_count = 3
        assert [spec.key for spec in controller.motor_control_specs] == [
            "head",
            "feet",
            "tilt",
        ]

        coordinator._motor_count = 4
        assert [spec.key for spec in controller.motor_control_specs] == [
            "head",
            "feet",
            "tilt",
            "lumbar",
        ]

    @pytest.mark.parametrize(
        ("variant", "motor_count", "expected"),
        [
            ("base", 2, (3, 400)),
            ("json", 2, (10, 100)),
            ("ksbt", 2, (10, 100)),
            ("ksbt_cr", 2, (4, 300)),
            ("ksbt04c", 2, (4, 300)),
            ("sleep_harmony", 2, (4, 300)),
            ("ergomotion", 2, (10, 100)),
            ("okin", 2, (10, 100)),
            ("okin", 3, (5, 200)),
            ("serta", 2, (10, 100)),
            ("sino", 2, (10, 100)),
            ("sino", 3, (5, 200)),
            ("purple", 2, (10, 100)),
        ],
    )
    def test_variant_uses_oem_motor_cadence_for_generic_defaults(
        self,
        hass: HomeAssistant,
        mock_keeson_config_entry,
        variant: str,
        motor_count: int,
        expected: tuple[int, int],
    ):
        """Test generic Keeson defaults are translated to each OEM app cadence."""
        coordinator = AdjustableBedCoordinator(hass, mock_keeson_config_entry)
        coordinator._motor_count = motor_count
        controller = KeesonController(coordinator, variant=variant)

        assert controller._motor_pulse_settings() == expected

    def test_ksbt03c_uses_ergomotion_sync_motor_cadence(
        self,
        hass: HomeAssistant,
        mock_keeson_config_entry,
    ):
        """KSBT03C uses Ergomotion Sync's immediate plus 300 ms timer."""
        coordinator = AdjustableBedCoordinator(hass, mock_keeson_config_entry)
        controller = KeesonController(
            coordinator,
            variant="ksbt",
            device_name="KSBT03C300039050",
        )

        assert controller._motor_pulse_settings() == (4, 300)

    @pytest.mark.parametrize(
        ("motor_count", "expected"),
        [
            (2, (10, 100)),
            (3, (5, 200)),
        ],
    )
    def test_betterliving_flag_uses_betterliving_motor_cadence(
        self,
        hass: HomeAssistant,
        mock_keeson_config_entry,
        motor_count: int,
        expected: tuple[int, int],
    ):
        """Test BetterLiving cadence follows the explicit preset flag."""
        coordinator = AdjustableBedCoordinator(hass, mock_keeson_config_entry)
        coordinator._motor_count = motor_count
        controller = KeesonController(coordinator, variant="base", betterliving_presets=True)

        assert controller._motor_pulse_settings() == expected

    async def test_custom_motor_cadence_is_preserved(
        self,
        hass: HomeAssistant,
        mock_keeson_config_entry,
        mock_coordinator_connected,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """Test per-device pulse tuning overrides the OEM app default."""
        coordinator = AdjustableBedCoordinator(hass, mock_keeson_config_entry)
        await coordinator.async_connect()
        coordinator._motor_pulse_count = 6
        coordinator._motor_pulse_delay_ms = 250
        controller = KeesonController(coordinator, variant="ksbt", device_name="KSBT03C300039050")
        controller.write_command = AsyncMock()
        monkeypatch.setattr(
            "custom_components.adjustable_bed.beds.keeson.asyncio.sleep",
            AsyncMock(),
        )

        await controller.move_head_up()

        first_call = controller.write_command.await_args_list[0]
        assert first_call.kwargs["repeat_count"] == 6
        assert first_call.kwargs["repeat_delay_ms"] == 250

    async def test_motor_release_failure_is_propagated(
        self,
        hass: HomeAssistant,
        mock_keeson_config_entry,
        mock_coordinator_connected,
    ):
        """Test a failed safety release is visible to command callers."""
        coordinator = AdjustableBedCoordinator(hass, mock_keeson_config_entry)
        await coordinator.async_connect()
        controller = KeesonController(coordinator, variant="base")
        controller.write_command = AsyncMock(side_effect=[None, RuntimeError("release failed")])

        with pytest.raises(RuntimeError, match="release failed"):
            await controller.move_head_up()

        calls = controller.write_command.await_args_list
        assert len(calls) == 2
        release_event = calls[1].kwargs["cancel_event"]
        assert isinstance(release_event, asyncio.Event)
        assert release_event is not coordinator.cancel_command
        assert not release_event.is_set()

    async def test_generic_ksbt_motion_uses_sfd_hold_and_release_sequence(
        self,
        hass: HomeAssistant,
        mock_keeson_config_entry,
        mock_coordinator_connected,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """Test non-KSBT03C P2 motion keeps the current SFD sequence."""
        coordinator = AdjustableBedCoordinator(hass, mock_keeson_config_entry)
        await coordinator.async_connect()
        controller = KeesonController(coordinator, variant="ksbt", device_name="KSBT300039050")
        controller.write_command = AsyncMock()
        sleep = AsyncMock()
        monkeypatch.setattr(
            "custom_components.adjustable_bed.beds.keeson.asyncio.sleep",
            sleep,
        )

        await controller.move_head_up()

        calls = controller.write_command.await_args_list
        assert len(calls) == 4
        assert calls[0].args == (bytes.fromhex("040200000001"),)
        assert calls[0].kwargs == {
            "repeat_count": 10,
            "repeat_delay_ms": 100,
        }
        assert [call.args for call in calls[1:]] == [
            (bytes.fromhex("00b0"),),
            (bytes.fromhex("00b0"),),
            (bytes.fromhex("00b0"),),
        ]
        release_events = [call.kwargs["cancel_event"] for call in calls[1:]]
        assert all(isinstance(event, asyncio.Event) for event in release_events)
        assert release_events[0] is release_events[1] is release_events[2]
        assert not release_events[0].is_set()
        assert [call.args for call in sleep.await_args_list] == [
            (0.3,),
            (0.3,),
            (0.3,),
        ]

    async def test_ksbt03c_motion_matches_ergomotion_sync_hold_and_release(
        self,
        hass: HomeAssistant,
        mock_keeson_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """Test Rio 5 repeats at 300 ms and emits no release packet."""
        coordinator = AdjustableBedCoordinator(hass, mock_keeson_config_entry)
        await coordinator.async_connect()
        controller = KeesonController(
            coordinator,
            variant="ksbt",
            device_name="KSBT03C300039050",
        )
        sleep = AsyncMock()
        monkeypatch.setattr(
            "custom_components.adjustable_bed.beds.base.asyncio.sleep",
            sleep,
        )

        await controller.move_head_up()

        assert mock_bleak_client.write_gatt_char.await_args_list == [
            call(
                KEESON_KSBT_CHAR_UUID,
                bytes.fromhex("040200000001"),
                response=True,
            )
        ] * 4
        assert sleep.await_args_list == [call(0.3)] * 3

    async def test_ksbt03c_motion_honors_coordinator_cancellation(
        self,
        hass: HomeAssistant,
        mock_keeson_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """Test cancelling the repeat timer stops Rio 5 without a release write."""
        coordinator = AdjustableBedCoordinator(hass, mock_keeson_config_entry)
        await coordinator.async_connect()
        controller = KeesonController(
            coordinator,
            variant="ksbt",
            device_name="KSBT03C300039050",
        )
        original_sleep = asyncio.sleep

        async def cancel_during_refresh(delay: float) -> None:
            if delay == 0.3:
                coordinator.cancel_command.set()
            else:
                await original_sleep(delay)

        monkeypatch.setattr(
            "custom_components.adjustable_bed.beds.base.asyncio.sleep",
            cancel_during_refresh,
        )

        await controller.move_head_up()

        mock_bleak_client.write_gatt_char.assert_awaited_once_with(
            KEESON_KSBT_CHAR_UUID,
            bytes.fromhex("040200000001"),
            response=True,
        )
        assert coordinator.cancel_command.is_set()

    async def test_ksbt_stop_all_does_not_wait_for_status_queries(
        self,
        hass: HomeAssistant,
        mock_keeson_config_entry,
        mock_coordinator_connected,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """Test direct P2 safety stop ends refresh without a 900 ms delay."""
        coordinator = AdjustableBedCoordinator(hass, mock_keeson_config_entry)
        await coordinator.async_connect()
        controller = KeesonController(coordinator, variant="ksbt", device_name="KSBT03C300039050")
        controller.write_command = AsyncMock()
        sleep = AsyncMock()
        monkeypatch.setattr(
            "custom_components.adjustable_bed.beds.keeson.asyncio.sleep",
            sleep,
        )

        await controller.stop_all()

        controller.write_command.assert_not_awaited()
        sleep.assert_not_awaited()

    @pytest.mark.parametrize(
        ("variant", "expected"),
        [
            ("ksbt", 1),
            ("ksbt_cr", 1),
            ("ksbt04c", 1),
            ("sleep_harmony", 1),
        ],
    )
    def test_ksbt_single_shot_count_matches_oem_app(
        self,
        hass: HomeAssistant,
        mock_keeson_config_entry,
        variant: str,
        expected: int,
    ):
        """Test OEM app one-shots are sent once before any release sequence."""
        coordinator = AdjustableBedCoordinator(hass, mock_keeson_config_entry)
        controller = KeesonController(coordinator, variant=variant)

        assert controller._single_shot_count == expected

    async def test_stale_motor_entity_keys(
        self,
        hass: HomeAssistant,
        mock_keeson_config_entry,
        mock_coordinator_connected,
    ):
        """Test stale keys cover the optional tilt/lumbar motors."""
        coordinator = AdjustableBedCoordinator(hass, mock_keeson_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.stale_motor_entity_keys == frozenset({"tilt", "lumbar"})


class TestKeesonMassageOffGating:
    """Test massage-off capability gating (issue #408)."""

    @pytest.mark.parametrize(
        "variant",
        ["base", "ksbt", "ksbt04c", "ergomotion"],
    )
    async def test_non_sino_variants_hide_massage_off(
        self,
        hass: HomeAssistant,
        mock_keeson_config_entry,
        mock_coordinator_connected,
        variant: str,
    ):
        """Test variants without a real off command don't expose the button."""
        coordinator = AdjustableBedCoordinator(hass, mock_keeson_config_entry)
        await coordinator.async_connect()

        controller = KeesonController(coordinator, variant=variant)

        assert not controller.supports_massage_off_control

    async def test_sino_variant_supports_massage_off(
        self,
        hass: HomeAssistant,
        mock_keeson_config_entry,
        mock_coordinator_connected,
    ):
        """Test the Sino variant keeps its working massage-off control."""
        coordinator = AdjustableBedCoordinator(hass, mock_keeson_config_entry)
        await coordinator.async_connect()

        controller = KeesonController(coordinator, variant="sino")

        assert controller.supports_massage_off_control


class TestKsbtMemoryPresets:
    """Test KSBT memory presets from Ergomotion Sync APK (issue #408)."""

    @pytest.mark.parametrize(
        ("variant", "slots"),
        [
            ("ksbt", 3),
            ("ksbt04c", 3),
            ("sleep_harmony", 3),
            ("ksbt_cr", 2),
        ],
    )
    async def test_memory_slot_count(
        self,
        hass: HomeAssistant,
        mock_keeson_config_entry,
        mock_coordinator_connected,
        variant: str,
        slots: int,
    ):
        """Test KSBT variants expose the remotes' three preset buttons."""
        coordinator = AdjustableBedCoordinator(hass, mock_keeson_config_entry)
        await coordinator.async_connect()

        controller = KeesonController(coordinator, variant=variant)

        assert controller.memory_slot_count == slots

    @pytest.mark.parametrize(
        "variant,memory_num,expected_value",
        [
            # Literal protocol values from the Ergomotion Sync APK, pinned so a
            # bad edit to the KeesonCommands constants cannot self-verify.
            ("ksbt", 1, 0x2000),  # Read button
            ("ksbt", 2, 0x4000),  # TV button
            ("ksbt", 3, 0x10000),  # M button
            ("ksbt04c", 1, 0x2000),  # Generic checksum profile: Read
            ("ksbt04c", 2, 0x4000),  # Generic checksum profile: TV
            ("ksbt04c", 3, 0x10000),  # Generic checksum profile: M
            # Sleep Harmony labels Reading/TV/Snore as M1/M2/M3.
            ("sleep_harmony", 1, 0x2000),
            ("sleep_harmony", 2, 0x4000),
            ("sleep_harmony", 3, 0x8000),
        ],
    )
    async def test_ksbt_preset_memory_mapping(
        self,
        hass: HomeAssistant,
        mock_keeson_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
        variant: str,
        memory_num: int,
        expected_value: int,
    ):
        """Test direct KSBT and Sleep Harmony use their proven memory labels."""
        coordinator = AdjustableBedCoordinator(hass, mock_keeson_config_entry)
        await coordinator.async_connect()
        controller = KeesonController(coordinator, variant=variant)
        coordinator._controller = controller
        mock_bleak_client.write_gatt_char.reset_mock()

        await controller.preset_memory(memory_num)

        expected_cmd = controller._build_command(expected_value)
        first_call = mock_bleak_client.write_gatt_char.call_args_list[0]
        assert first_call[0][1] == expected_cmd

    async def test_ksbt_preset_memory_invalid_slot_warns(
        self,
        hass: HomeAssistant,
        mock_keeson_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
        caplog,
    ):
        """Test out-of-range KSBT memory slot warns and sends nothing."""
        coordinator = AdjustableBedCoordinator(hass, mock_keeson_config_entry)
        await coordinator.async_connect()
        controller = KeesonController(coordinator, variant="ksbt")
        coordinator._controller = controller
        mock_bleak_client.write_gatt_char.reset_mock()

        await controller.preset_memory(4)

        assert "KSBT memory 4 not supported" in caplog.text
        mock_bleak_client.write_gatt_char.assert_not_called()
