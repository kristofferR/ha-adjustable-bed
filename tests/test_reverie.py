"""Tests for Reverie bed controller."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed.beds.reverie import (
    ReverieCommands,
)
from custom_components.adjustable_bed.beds.reverie_comfort import ReverieComfortRequest
from custom_components.adjustable_bed.const import (
    BED_TYPE_REVERIE,
    CONF_BED_TYPE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_HAS_MASSAGE,
    CONF_MOTOR_COUNT,
    CONF_PREFERRED_ADAPTER,
    DOMAIN,
    REVERIE_CHAR_UUID,
)
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.number import MASSAGE_NUMBER_DESCRIPTIONS


@pytest.fixture
def mock_reverie_config_entry_data() -> dict:
    """Return mock config entry data for Reverie bed."""
    return {
        CONF_ADDRESS: "AA:BB:CC:DD:EE:FF",
        CONF_NAME: "Reverie Test Bed",
        CONF_BED_TYPE: BED_TYPE_REVERIE,
        CONF_MOTOR_COUNT: 2,
        CONF_HAS_MASSAGE: True,
        CONF_DISABLE_ANGLE_SENSING: True,
        CONF_PREFERRED_ADAPTER: "auto",
    }


@pytest.fixture
def mock_reverie_config_entry(
    hass: HomeAssistant, mock_reverie_config_entry_data: dict
) -> MockConfigEntry:
    """Return a mock config entry for Reverie bed."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Reverie Test Bed",
        data=mock_reverie_config_entry_data,
        unique_id="AA:BB:CC:DD:EE:FF",
        entry_id="reverie_test_entry",
    )
    entry.add_to_hass(hass)
    return entry


class TestReverieController:
    """Test Reverie controller."""

    async def test_wave_intensity_keeps_legacy_number_identity(
        self,
        hass: HomeAssistant,
        mock_reverie_config_entry,
        mock_coordinator_connected,
    ) -> None:
        coordinator = AdjustableBedCoordinator(hass, mock_reverie_config_entry)
        await coordinator.async_connect()

        wave = next(
            description
            for description in MASSAGE_NUMBER_DESCRIPTIONS
            if description.massage_zone == "wave"
        )
        assert wave.key == "massage_wave_intensity"
        assert "wave" in coordinator.controller.massage_intensity_zones
        assert coordinator.entity_unique_id(wave.key) == (
            "AA:BB:CC:DD:EE:FF_massage_wave_intensity"
        )

    async def test_control_characteristic_uuid(
        self,
        hass: HomeAssistant,
        mock_reverie_config_entry,
        mock_coordinator_connected,
    ):
        """Test controller reports correct characteristic UUID."""
        coordinator = AdjustableBedCoordinator(hass, mock_reverie_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.control_characteristic_uuid == REVERIE_CHAR_UUID

    async def test_build_command_checksum(
        self,
        hass: HomeAssistant,
        mock_reverie_config_entry,
        mock_coordinator_connected,
    ):
        """Test command building with XOR checksum."""
        coordinator = AdjustableBedCoordinator(hass, mock_reverie_config_entry)
        await coordinator.async_connect()

        command = coordinator.controller._build_command([0x05])

        # Format: [0x55, ...bytes, checksum]
        # checksum = 0x55 XOR all bytes
        assert command[0] == 0x55
        assert command[1] == 0x05
        expected_checksum = 0x55 ^ 0x05
        assert command[2] == expected_checksum

    async def test_write_command(
        self,
        hass: HomeAssistant,
        mock_reverie_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test writing a command to the bed."""
        coordinator = AdjustableBedCoordinator(hass, mock_reverie_config_entry)
        await coordinator.async_connect()

        command = coordinator.controller._build_command(ReverieCommands.MOTOR_STOP)
        await coordinator.controller.write_command(command)

        mock_bleak_client.write_gatt_char.assert_called_with(
            REVERIE_CHAR_UUID, command, response=True
        )

    async def test_write_command_not_connected(
        self,
        hass: HomeAssistant,
        mock_reverie_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test writing command when not connected raises error."""
        coordinator = AdjustableBedCoordinator(hass, mock_reverie_config_entry)
        await coordinator.async_connect()

        mock_bleak_client.is_connected = False

        with pytest.raises(ConnectionError):
            await coordinator.controller.write_command(
                coordinator.controller._build_command(ReverieCommands.MOTOR_STOP)
            )


class TestReverieMovement:
    """Test Reverie movement commands (linear motor commands with stop)."""

    async def test_move_head_up_is_one_press_frame(
        self,
        hass: HomeAssistant,
        mock_reverie_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test move head up sends linear HEAD_UP command then STOP."""
        coordinator = AdjustableBedCoordinator(hass, mock_reverie_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.move_head_up()

        calls = mock_bleak_client.write_gatt_char.call_args_list
        first_command = calls[0][0][1]
        expected = coordinator.controller._build_command(ReverieCommands.HEAD_UP)
        assert first_command == expected
        assert len(calls) == 1

    async def test_move_head_down_is_one_press_frame(
        self,
        hass: HomeAssistant,
        mock_reverie_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test move head down sends linear HEAD_DOWN command then STOP."""
        coordinator = AdjustableBedCoordinator(hass, mock_reverie_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.move_head_down()

        calls = mock_bleak_client.write_gatt_char.call_args_list
        first_command = calls[0][0][1]
        expected = coordinator.controller._build_command(ReverieCommands.HEAD_DOWN)
        assert first_command == expected
        assert len(calls) == 1

    async def test_move_legs_up_is_one_press_frame(
        self,
        hass: HomeAssistant,
        mock_reverie_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test move legs up sends linear FOOT_UP command then STOP."""
        coordinator = AdjustableBedCoordinator(hass, mock_reverie_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.move_legs_up()

        calls = mock_bleak_client.write_gatt_char.call_args_list
        first_command = calls[0][0][1]
        expected = coordinator.controller._build_command(ReverieCommands.FOOT_UP)
        assert first_command == expected
        assert len(calls) == 1

    async def test_stop_all(
        self,
        hass: HomeAssistant,
        mock_reverie_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test stop all sends MOTOR_STOP command."""
        coordinator = AdjustableBedCoordinator(hass, mock_reverie_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.stop_all()

        expected = coordinator.controller._build_command(ReverieCommands.MOTOR_STOP)
        mock_bleak_client.write_gatt_char.assert_called_with(
            REVERIE_CHAR_UUID, expected, response=True
        )

    async def test_bounded_hold_sends_one_press_then_fresh_stop(
        self,
        hass: HomeAssistant,
        mock_reverie_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        coordinator = AdjustableBedCoordinator(hass, mock_reverie_config_entry)
        await coordinator.async_connect()

        with patch("custom_components.adjustable_bed.beds.reverie.asyncio.sleep"):
            await coordinator.controller.hold_control("back_up", 250)

        assert [call.args[1] for call in mock_bleak_client.write_gatt_char.call_args_list] == [
            bytes.fromhex("550154"),
            bytes.fromhex("55ffaa"),
        ]


class TestReveriePresets:
    """Test Reverie preset commands."""

    async def test_preset_flat(
        self,
        hass: HomeAssistant,
        mock_reverie_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test preset flat command."""
        coordinator = AdjustableBedCoordinator(hass, mock_reverie_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.preset_flat()

        expected = coordinator.controller._build_command(ReverieCommands.PRESET_FLAT)
        first_call = mock_bleak_client.write_gatt_char.call_args_list[0]
        assert first_call[0][1] == expected

    async def test_preset_zero_g(
        self,
        hass: HomeAssistant,
        mock_reverie_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test preset zero gravity command."""
        coordinator = AdjustableBedCoordinator(hass, mock_reverie_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.preset_zero_g()

        expected = coordinator.controller._build_command(ReverieCommands.PRESET_ZERO_G)
        first_call = mock_bleak_client.write_gatt_char.call_args_list[0]
        assert first_call[0][1] == expected

    async def test_preset_anti_snore(
        self,
        hass: HomeAssistant,
        mock_reverie_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test preset anti-snore command."""
        coordinator = AdjustableBedCoordinator(hass, mock_reverie_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.preset_anti_snore()

        expected = coordinator.controller._build_command(ReverieCommands.PRESET_ANTI_SNORE)
        first_call = mock_bleak_client.write_gatt_char.call_args_list[0]
        assert first_call[0][1] == expected

    @pytest.mark.parametrize(
        "memory_num,expected_command",
        [
            (1, ReverieCommands.PRESET_MEMORY_1),
            (2, ReverieCommands.PRESET_MEMORY_2),
            (3, ReverieCommands.PRESET_MEMORY_3),
            (4, ReverieCommands.PRESET_MEMORY_4),
        ],
    )
    async def test_preset_memory(
        self,
        hass: HomeAssistant,
        mock_reverie_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
        memory_num: int,
        expected_command: list,
    ):
        """Test preset memory commands."""
        coordinator = AdjustableBedCoordinator(hass, mock_reverie_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.preset_memory(memory_num)

        expected = coordinator.controller._build_command(expected_command)
        first_call = mock_bleak_client.write_gatt_char.call_args_list[0]
        assert first_call[0][1] == expected

    @pytest.mark.parametrize(
        "memory_num,expected_command",
        [
            (1, ReverieCommands.PROGRAM_MEMORY_1),
            (2, ReverieCommands.PROGRAM_MEMORY_2),
            (3, ReverieCommands.PROGRAM_MEMORY_3),
            (4, ReverieCommands.PROGRAM_MEMORY_4),
        ],
    )
    async def test_program_memory(
        self,
        hass: HomeAssistant,
        mock_reverie_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
        memory_num: int,
        expected_command: list,
    ):
        """Test program memory commands."""
        coordinator = AdjustableBedCoordinator(hass, mock_reverie_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.program_memory(memory_num)

        expected = coordinator.controller._build_command(expected_command)
        mock_bleak_client.write_gatt_char.assert_called_with(
            REVERIE_CHAR_UUID, expected, response=True
        )


class TestReverieLights:
    """Test Reverie light commands."""

    async def test_lights_toggle(
        self,
        hass: HomeAssistant,
        mock_reverie_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test lights toggle command."""
        coordinator = AdjustableBedCoordinator(hass, mock_reverie_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.lights_toggle()

        expected = coordinator.controller._build_command(ReverieCommands.LIGHTS_TOGGLE)
        mock_bleak_client.write_gatt_char.assert_called_with(
            REVERIE_CHAR_UUID, expected, response=True
        )


class TestReverieMassage:
    """Test Reverie massage commands."""

    async def test_massage_off(
        self,
        hass: HomeAssistant,
        mock_reverie_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test massage off sends STOP_MASSAGE command (0x35)."""
        coordinator = AdjustableBedCoordinator(hass, mock_reverie_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.massage_off()

        expected = coordinator.controller._build_command(ReverieCommands.STOP_MASSAGE)
        mock_bleak_client.write_gatt_char.assert_called_once_with(
            REVERIE_CHAR_UUID, expected, response=True
        )

    async def test_massage_head_up(
        self,
        hass: HomeAssistant,
        mock_reverie_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test head massage intensity up."""
        coordinator = AdjustableBedCoordinator(hass, mock_reverie_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.massage_head_up()

        # Level should increment from 0 to 1
        expected = coordinator.controller._build_command(ReverieCommands.massage_head(1))
        mock_bleak_client.write_gatt_char.assert_called_with(
            REVERIE_CHAR_UUID, expected, response=True
        )

    async def test_massage_head_down(
        self,
        hass: HomeAssistant,
        mock_reverie_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test head massage intensity down (stays at 0)."""
        coordinator = AdjustableBedCoordinator(hass, mock_reverie_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.massage_head_down()

        # Level should stay at 0 (can't go negative)
        expected = coordinator.controller._build_command(ReverieCommands.massage_head(0))
        mock_bleak_client.write_gatt_char.assert_called_with(
            REVERIE_CHAR_UUID, expected, response=True
        )

    async def test_massage_mode_step(
        self,
        hass: HomeAssistant,
        mock_reverie_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test massage wave mode step."""
        coordinator = AdjustableBedCoordinator(hass, mock_reverie_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.massage_mode_step()

        # Wave level should increment from 0 to 1
        expected = coordinator.controller._build_command(ReverieCommands.massage_wave(1))
        mock_bleak_client.write_gatt_char.assert_called_with(
            REVERIE_CHAR_UUID, expected, response=True
        )

    def test_wave_builder_matches_only_the_accepted_zero_to_one_vector(self):
        assert ReverieCommands.massage_wave(1) == "41"
        assert bytes.fromhex(f"55{ReverieCommands.massage_wave(1)}14") == bytes.fromhex(
            "554114"
        )

    async def test_wave_direct_setter_uses_source_vector_and_rejects_negative_without_write(
        self,
        hass: HomeAssistant,
        mock_reverie_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        coordinator = AdjustableBedCoordinator(hass, mock_reverie_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.set_massage_intensity("wave", 1)
        assert mock_bleak_client.write_gatt_char.call_args.args[1] == bytes.fromhex(
            "554114"
        )
        write_count = mock_bleak_client.write_gatt_char.call_count

        with pytest.raises(ValueError, match="non-negative"):
            await coordinator.controller.set_massage_intensity("wave", -1)

        assert mock_bleak_client.write_gatt_char.call_count == write_count


class TestReverieComfortProgression:
    async def test_progression_waits_for_stable_current_notifications_and_gate(
        self,
        hass: HomeAssistant,
        mock_reverie_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        coordinator = AdjustableBedCoordinator(hass, mock_reverie_config_entry)
        await coordinator.async_connect()
        controller = coordinator.controller
        now = 0.0
        monkeypatch.setattr(controller, "_comfort_now", lambda: now)
        request = ReverieComfortRequest(head_position=25, foot_position=40)
        await controller.async_set_comfort(request)
        stop_frame = controller._build_command(ReverieCommands.STOP_MASSAGE)
        assert [call.args[1] for call in mock_bleak_client.write_gatt_char.call_args_list] == [
            stop_frame
        ]

        sample = bytearray((0, 0, 10, 20, 0, 0, 0, 0, 0))
        controller._parse_position_data(sample)
        controller._parse_position_data(sample)
        await hass.async_block_till_done()
        assert mock_bleak_client.write_gatt_char.call_count == 1

        now = 0.001
        controller._parse_position_data(sample)
        await hass.async_block_till_done()
        expected_head = controller._build_command(ReverieCommands.motor_head(25))
        assert mock_bleak_client.write_gatt_char.call_args.args[1] == expected_head

        # The source uses a strict greater-than gate and resets its origin
        # whenever feedback changes, even after a previous field was written.
        now = 2.001
        controller._parse_position_data(sample)
        await hass.async_block_till_done()
        assert mock_bleak_client.write_gatt_char.call_count == 2
        now = 2.125
        changed = bytearray((0, 0, 25, 35, 0, 0, 0, 0, 0))
        controller._parse_position_data(changed)
        now = 4.125
        controller._parse_position_data(changed)
        await hass.async_block_till_done()
        assert mock_bleak_client.write_gatt_char.call_count == 2
        now = 4.126
        controller._parse_position_data(changed)
        await hass.async_block_till_done()
        expected_foot = controller._build_command(ReverieCommands.motor_feet(40))
        assert [call.args[1] for call in mock_bleak_client.write_gatt_char.call_args_list] == [
            stop_frame, expected_head, expected_foot,
        ]
        assert controller._comfort_request is None

    async def test_reentry_invalidates_a_queued_stable_notification_write(
        self,
        hass: HomeAssistant,
        mock_reverie_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        coordinator = AdjustableBedCoordinator(hass, mock_reverie_config_entry)
        await coordinator.async_connect()
        controller = coordinator.controller
        now = 0.0
        monkeypatch.setattr(controller, "_comfort_now", lambda: now)
        queued: list[object] = []
        monkeypatch.setattr(
            hass,
            "async_create_task",
            lambda coroutine, *_args, **_kwargs: queued.append(coroutine),
        )

        await controller.async_set_comfort(ReverieComfortRequest(head_position=25))
        sample = bytearray((0, 0, 0, 0, 0, 0, 0, 0, 0))
        controller._parse_position_data(sample)
        now = 0.001
        controller._parse_position_data(sample)
        assert len(queued) == 1

        await controller.async_set_comfort(ReverieComfortRequest(head_position=30))
        await queued.pop()  # type: ignore[misc]

        assert [call.args[1] for call in mock_bleak_client.write_gatt_char.call_args_list] == [
            controller._build_command(ReverieCommands.STOP_MASSAGE),
            controller._build_command(ReverieCommands.STOP_MASSAGE),
        ]
        assert controller._comfort_request == ReverieComfortRequest(head_position=30)


class TestReveriePositionNotifications:
    """Test Reverie position notification handling."""

    async def test_start_notify(
        self,
        hass: HomeAssistant,
        mock_reverie_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test starting position notifications."""
        coordinator = AdjustableBedCoordinator(hass, mock_reverie_config_entry)
        await coordinator.async_connect()

        callback = MagicMock()
        await coordinator.controller.start_notify(callback)

        # Reverie uses same char for notify
        mock_bleak_client.start_notify.assert_called_once()

    async def test_parse_position_data(
        self,
        hass: HomeAssistant,
        mock_reverie_config_entry,
        mock_coordinator_connected,
    ):
        """Test parsing 9-byte position notification data."""
        coordinator = AdjustableBedCoordinator(hass, mock_reverie_config_entry)
        await coordinator.async_connect()

        callback = MagicMock()
        coordinator.controller._notify_callback = callback

        # 9-byte notification: [header0, header1, head_pos, foot_pos, head_wave, foot_wave, unk, unk, unk]
        head_pos = 50
        foot_pos = 30
        data = bytearray([0x00, 0x00, head_pos, foot_pos, 0, 0, 0, 0, 0])
        coordinator.controller._parse_position_data(data)

        # Callback should be called twice: once for back, once for legs
        assert callback.call_count == 2
        first_call = callback.call_args_list[0][0]
        second_call = callback.call_args_list[1][0]
        assert first_call[0] == "back"
        assert first_call[1] == pytest.approx(head_pos * 0.6)
        assert second_call[0] == "legs"
        assert second_call[1] == pytest.approx(foot_pos * 0.45)

    async def test_parse_position_data_invalid_length(
        self,
        hass: HomeAssistant,
        mock_reverie_config_entry,
        mock_coordinator_connected,
    ):
        """Test parsing position data with wrong length is ignored."""
        coordinator = AdjustableBedCoordinator(hass, mock_reverie_config_entry)
        await coordinator.async_connect()

        callback = MagicMock()
        coordinator.controller._notify_callback = callback

        # Not 9 bytes - should be silently ignored
        data = bytearray([0x00, 0x51, 50, 0x00])
        coordinator.controller._parse_position_data(data)

        # Callback should not be called (data length != 9)
        callback.assert_not_called()
