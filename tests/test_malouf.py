"""Tests for Malouf bed controllers (NEW_OKIN and LEGACY_OKIN protocols)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed.beds.malouf import (
    MaloufCommands,
    _save_memory_command,
)
from custom_components.adjustable_bed.codec import malouf as malouf_codec
from custom_components.adjustable_bed.const import (
    BED_TYPE_MALOUF_LEGACY_OKIN,
    BED_TYPE_MALOUF_NEW_OKIN,
    CONF_BED_TYPE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_HAS_MASSAGE,
    CONF_MALOUF_LAYOUT,
    CONF_MALOUF_MEMORY_SLOTS,
    CONF_MOTOR_COUNT,
    CONF_PREFERRED_ADAPTER,
    DOMAIN,
    MALOUF_LAYOUT_FOUR_MOTOR,
    MALOUF_LAYOUT_HILO,
    MALOUF_LEGACY_OKIN_WRITE_CHAR_UUID,
    MALOUF_NEW_OKIN_WRITE_CHAR_UUID,
)
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator


def _new_okin_frame(word: int) -> bytes:
    return malouf_codec.command("okin_new", word)


@pytest.fixture
def mock_malouf_new_config_entry_data() -> dict:
    """Return mock config entry data for Malouf NEW_OKIN bed."""
    return {
        CONF_ADDRESS: "AA:BB:CC:DD:EE:FF",
        CONF_NAME: "Malouf Test Bed",
        CONF_BED_TYPE: BED_TYPE_MALOUF_NEW_OKIN,
        CONF_MOTOR_COUNT: 2,
        CONF_HAS_MASSAGE: True,
        CONF_DISABLE_ANGLE_SENSING: True,
        CONF_PREFERRED_ADAPTER: "auto",
    }


@pytest.fixture
def mock_malouf_new_config_entry(
    hass: HomeAssistant, mock_malouf_new_config_entry_data: dict
) -> MockConfigEntry:
    """Return a mock config entry for Malouf NEW_OKIN bed."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Malouf Test Bed",
        data=mock_malouf_new_config_entry_data,
        unique_id="AA:BB:CC:DD:EE:FF",
        entry_id="malouf_new_test_entry",
    )
    entry.add_to_hass(hass)
    return entry


@pytest.fixture
def mock_malouf_legacy_config_entry_data() -> dict:
    """Return mock config entry data for Malouf LEGACY_OKIN bed."""
    return {
        CONF_ADDRESS: "AA:BB:CC:DD:EE:FF",
        CONF_NAME: "Malouf Legacy Test Bed",
        CONF_BED_TYPE: BED_TYPE_MALOUF_LEGACY_OKIN,
        CONF_MOTOR_COUNT: 2,
        CONF_HAS_MASSAGE: True,
        CONF_DISABLE_ANGLE_SENSING: True,
        CONF_PREFERRED_ADAPTER: "auto",
    }


@pytest.fixture
def mock_malouf_legacy_config_entry(
    hass: HomeAssistant, mock_malouf_legacy_config_entry_data: dict
) -> MockConfigEntry:
    """Return a mock config entry for Malouf LEGACY_OKIN bed."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Malouf Legacy Test Bed",
        data=mock_malouf_legacy_config_entry_data,
        unique_id="AA:BB:CC:DD:EE:FF",
        entry_id="malouf_legacy_test_entry",
    )
    entry.add_to_hass(hass)
    return entry


class TestMaloufCommands:
    """Test Malouf command constants."""

    def test_dual_commands_combine_flags(self):
        """Test dual motor commands are combinations of single flags."""
        assert MaloufCommands.DUAL_UP == MaloufCommands.HEAD_UP | MaloufCommands.FOOT_UP
        assert MaloufCommands.DUAL_DOWN == MaloufCommands.HEAD_DOWN | MaloufCommands.FOOT_DOWN

    def test_preset_command_values(self):
        """Test preset command values."""
        assert MaloufCommands.ALL_FLAT == 0x8000000
        assert MaloufCommands.ZERO_G == 0x1000
        assert MaloufCommands.LOUNGE == 0x2000
        assert MaloufCommands.ANTI_SNORE == 0x8000
        assert MaloufCommands.TV_READ == 0x4000
        assert MaloufCommands.MEMORY_1 == 0x10000
        assert MaloufCommands.MEMORY_2 == 0x40000


class TestMaloufNewOkinController:
    """Test Malouf NEW_OKIN controller."""

    async def test_control_characteristic_uuid(
        self,
        hass: HomeAssistant,
        mock_malouf_new_config_entry,
        mock_coordinator_connected,
    ):
        """Test controller reports correct characteristic UUID."""
        coordinator = AdjustableBedCoordinator(hass, mock_malouf_new_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.control_characteristic_uuid == MALOUF_NEW_OKIN_WRITE_CHAR_UUID

    async def test_coordinator_preserves_observed_ble_name(
        self,
        hass: HomeAssistant,
        mock_malouf_new_config_entry,
        mock_coordinator_connected,
    ):
        """APK name-specific commands use advertising name, not the entry title."""
        coordinator = AdjustableBedCoordinator(hass, mock_malouf_new_config_entry)
        await coordinator.async_connect()

        assert coordinator.name == "Malouf Test Bed"
        assert coordinator.ble_device_name == "Test Bed"


class TestMaloufLegacyOkinController:
    """Test Malouf LEGACY_OKIN controller."""

    async def test_control_characteristic_uuid(
        self,
        hass: HomeAssistant,
        mock_malouf_legacy_config_entry,
        mock_coordinator_connected,
    ):
        """Test controller reports correct characteristic UUID."""
        coordinator = AdjustableBedCoordinator(hass, mock_malouf_legacy_config_entry)
        await coordinator.async_connect()

        assert (
            coordinator.controller.control_characteristic_uuid == MALOUF_LEGACY_OKIN_WRITE_CHAR_UUID
        )


class TestMaloufNewOkinPresets:
    """Test Malouf NEW_OKIN preset commands."""

    async def test_preset_flat(
        self,
        hass: HomeAssistant,
        mock_malouf_new_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test preset flat sends command then STOP."""
        coordinator = AdjustableBedCoordinator(hass, mock_malouf_new_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.preset_flat()

        calls = mock_bleak_client.write_gatt_char.call_args_list
        sent_commands = [call.args[1] for call in calls]
        expected_preset = _new_okin_frame(MaloufCommands.ALL_FLAT)
        expected_stop = _new_okin_frame(MaloufCommands.STOP)
        assert expected_preset in sent_commands
        assert sent_commands[-1] == expected_stop

    async def test_preset_zero_g(
        self,
        hass: HomeAssistant,
        mock_malouf_new_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test preset zero-G sends command then STOP."""
        coordinator = AdjustableBedCoordinator(hass, mock_malouf_new_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.preset_zero_g()

        calls = mock_bleak_client.write_gatt_char.call_args_list
        sent_commands = [call.args[1] for call in calls]
        expected_preset = _new_okin_frame(MaloufCommands.ZERO_G)
        expected_stop = _new_okin_frame(MaloufCommands.STOP)
        assert expected_preset in sent_commands
        assert sent_commands[-1] == expected_stop

    async def test_preset_memory_1(
        self,
        hass: HomeAssistant,
        mock_malouf_new_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test preset memory 1 sends command then STOP."""
        coordinator = AdjustableBedCoordinator(hass, mock_malouf_new_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.preset_memory(1)

        calls = mock_bleak_client.write_gatt_char.call_args_list
        sent_commands = [call.args[1] for call in calls]
        expected_preset = _new_okin_frame(MaloufCommands.MEMORY_1)
        expected_stop = _new_okin_frame(MaloufCommands.STOP)
        assert expected_preset in sent_commands
        assert sent_commands[-1] == expected_stop

    async def test_preset_memory_2(
        self,
        hass: HomeAssistant,
        mock_malouf_new_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test an explicitly configured second memory sends command then STOP."""
        hass.config_entries.async_update_entry(
            mock_malouf_new_config_entry,
            data={
                **mock_malouf_new_config_entry.data,
                CONF_MALOUF_MEMORY_SLOTS: 2,
            },
        )
        coordinator = AdjustableBedCoordinator(hass, mock_malouf_new_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.preset_memory(2)

        calls = mock_bleak_client.write_gatt_char.call_args_list
        sent_commands = [call.args[1] for call in calls]
        expected_preset = _new_okin_frame(MaloufCommands.MEMORY_2)
        expected_stop = _new_okin_frame(MaloufCommands.STOP)
        assert expected_preset in sent_commands
        assert sent_commands[-1] == expected_stop


class TestMaloufMemoryProgramming:
    """Test the long-press sequences recovered from Lucid Base 1.3.3."""

    async def test_new_okin_programs_55_times_without_stop(
        self,
        hass: HomeAssistant,
        mock_malouf_new_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """NEW_OKIN uses 55 writes at 100 ms and emits no trailing STOP."""
        coordinator = AdjustableBedCoordinator(hass, mock_malouf_new_config_entry)
        await coordinator.async_connect()
        mock_bleak_client.write_gatt_char.reset_mock()

        with patch(
            "custom_components.adjustable_bed.beds.malouf.asyncio.sleep",
            new_callable=AsyncMock,
        ):
            await coordinator.controller.program_memory(1)

        expected = _new_okin_frame(MaloufCommands.MEMORY_1)
        assert [call.args[1] for call in mock_bleak_client.write_gatt_char.call_args_list] == [
            expected
        ] * 55

    async def test_legacy_smartbed238_uses_modified_save_and_no_stop(
        self,
        hass: HomeAssistant,
        mock_malouf_legacy_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
        mock_async_ble_device_from_address: MagicMock,
    ):
        """The configured Smartbed238 name remains a fallback for the save command."""
        hass.config_entries.async_update_entry(
            mock_malouf_legacy_config_entry,
            data={
                **mock_malouf_legacy_config_entry.data,
                CONF_NAME: "Smartbed238001234",
            },
        )
        mock_async_ble_device_from_address.return_value.name = None
        coordinator = AdjustableBedCoordinator(hass, mock_malouf_legacy_config_entry)
        await coordinator.async_connect()
        assert coordinator.ble_device_name == "Smartbed238001234"
        assert coordinator.observed_ble_device_name is None
        mock_bleak_client.write_gatt_char.reset_mock()

        with patch(
            "custom_components.adjustable_bed.beds.malouf.asyncio.sleep",
            new_callable=AsyncMock,
        ):
            await coordinator.controller.program_memory(1)

        expected = coordinator.controller._build_command(MaloufCommands.SAVE_MEMORY_1_SMARTBED238)
        assert [call.args[1] for call in mock_bleak_client.write_gatt_char.call_args_list] == [
            expected
        ] * 85

    async def test_new_okin_program_memory_streams_save(
        self,
        hass: HomeAssistant,
        mock_malouf_new_config_entry,
        mock_coordinator_connected,
    ):
        """Test NEW_OKIN programming streams the save command at 55x100ms."""
        coordinator = AdjustableBedCoordinator(hass, mock_malouf_new_config_entry)
        await coordinator.async_connect()
        controller = coordinator.controller

        with patch.object(controller, "write_command", new=AsyncMock()) as mock_write:
            await controller.program_memory(1)

        mock_write.assert_called_once()
        save_call = mock_write.call_args
        assert save_call.args[0] == _new_okin_frame(MaloufCommands.SAVE_MEMORY_1)
        assert save_call.kwargs["repeat_count"] == 55
        assert save_call.kwargs["repeat_delay_ms"] == 100

    async def test_legacy_okin_program_memory_streams_save(
        self,
        hass: HomeAssistant,
        mock_malouf_legacy_config_entry,
        mock_coordinator_connected,
    ):
        """Test LEGACY_OKIN programming streams the save command at 85x150ms."""
        hass.config_entries.async_update_entry(
            mock_malouf_legacy_config_entry,
            data={
                **mock_malouf_legacy_config_entry.data,
                CONF_MALOUF_MEMORY_SLOTS: 2,
            },
        )
        coordinator = AdjustableBedCoordinator(hass, mock_malouf_legacy_config_entry)
        await coordinator.async_connect()
        controller = coordinator.controller

        with patch.object(controller, "write_command", new=AsyncMock()) as mock_write:
            await controller.program_memory(2)

        mock_write.assert_called_once()
        save_call = mock_write.call_args
        assert save_call.args[0] == controller._build_command(MaloufCommands.SAVE_MEMORY_2)
        assert save_call.kwargs["repeat_count"] == 85
        assert save_call.kwargs["repeat_delay_ms"] == 150

    async def test_program_memory_invalid_slot_writes_nothing(
        self,
        hass: HomeAssistant,
        mock_malouf_legacy_config_entry,
        mock_coordinator_connected,
    ):
        """Test invalid memory slots are rejected without any BLE writes."""
        coordinator = AdjustableBedCoordinator(hass, mock_malouf_legacy_config_entry)
        await coordinator.async_connect()
        controller = coordinator.controller

        with patch.object(controller, "write_command", new=AsyncMock()) as mock_write:
            await controller.program_memory(3)

        mock_write.assert_not_called()

    def test_save_memory_command_values(self):
        """Test save values match the app (slot 1 recall value, slot 2 save bit)."""
        assert _save_memory_command(1, "OKIN-BLE00017786") == 0x10000
        assert _save_memory_command(1, "Smartbed238-0042") == 0x80010000
        assert _save_memory_command(2, "OKIN-BLE00017786") == 0x80040000
        assert _save_memory_command(2, "Smartbed238-0042") == 0x80040000
        assert _save_memory_command(3, "OKIN-BLE00017786") is None
        assert _save_memory_command(1, None) == 0x10000


class TestMaloufCapabilities:
    """Test Malouf capability properties."""

    async def test_two_motor_layout_does_not_expose_lumbar(
        self,
        hass: HomeAssistant,
        mock_malouf_new_config_entry,
        mock_coordinator_connected,
    ):
        """A two-motor L600-style layout must not invent lumbar support."""
        coordinator = AdjustableBedCoordinator(hass, mock_malouf_new_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.has_lumbar_support is False

    async def test_two_motor_layout_does_not_expose_tilt(
        self,
        hass: HomeAssistant,
        mock_malouf_new_config_entry,
        mock_coordinator_connected,
    ):
        """A two-motor L600-style layout must not invent tilt support."""
        coordinator = AdjustableBedCoordinator(hass, mock_malouf_new_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.has_tilt_support is False

    async def test_supports_lights_toggle_only(
        self,
        hass: HomeAssistant,
        mock_malouf_new_config_entry,
        mock_coordinator_connected,
    ):
        """Test Malouf supports lights but only toggle control."""
        coordinator = AdjustableBedCoordinator(hass, mock_malouf_new_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.supports_lights is True
        assert coordinator.controller.supports_discrete_light_control is False

    async def test_two_motor_layout_defaults_to_one_memory_slot(
        self,
        hass: HomeAssistant,
        mock_malouf_new_config_entry,
        mock_coordinator_connected,
    ):
        """The confirmed Lucid L600 app profile exposes one memory position."""
        coordinator = AdjustableBedCoordinator(hass, mock_malouf_new_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.memory_slot_count == 1

    async def test_new_okin_two_motor_layout_is_not_hilo(
        self,
        hass: HomeAssistant,
        mock_malouf_new_config_entry,
        mock_coordinator_connected,
    ):
        """NEW_OKIN protocol alone must not imply a Hi-Lo actuator layout."""
        coordinator = AdjustableBedCoordinator(hass, mock_malouf_new_config_entry)
        await coordinator.async_connect()

        specs = coordinator.controller.motor_control_specs

        assert [spec.key for spec in specs] == ["back", "legs"]
        assert coordinator.controller.stale_motor_entity_keys == {
            "head",
            "feet",
            "tilt",
            "lumbar",
            "bed_height",
        }

    async def test_legacy_okin_two_motor_layout_is_not_hilo(
        self,
        hass: HomeAssistant,
        mock_malouf_legacy_config_entry,
        mock_coordinator_connected,
    ):
        """LEGACY_OKIN protocol alone must not imply extra L600 actuators."""
        coordinator = AdjustableBedCoordinator(hass, mock_malouf_legacy_config_entry)
        await coordinator.async_connect()

        specs = coordinator.controller.motor_control_specs

        assert [spec.key for spec in specs] == ["back", "legs"]

    async def test_supports_memory_programming(
        self,
        hass: HomeAssistant,
        mock_malouf_new_config_entry,
        mock_coordinator_connected,
    ):
        """The official app implements timed memory programming."""
        coordinator = AdjustableBedCoordinator(hass, mock_malouf_new_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.supports_memory_programming is True

    @pytest.mark.parametrize(
        ("bed_type", "layout", "expected"),
        [
            (
                BED_TYPE_MALOUF_NEW_OKIN,
                MALOUF_LAYOUT_FOUR_MOTOR,
                ["back", "legs", "tilt", "lumbar"],
            ),
            (
                BED_TYPE_MALOUF_LEGACY_OKIN,
                MALOUF_LAYOUT_HILO,
                ["back", "legs", "tilt", "lumbar", "bed_height"],
            ),
        ],
    )

    async def test_explicit_layout_is_independent_of_protocol(
        self,
        hass: HomeAssistant,
        mock_malouf_new_config_entry,
        mock_coordinator_connected,
        bed_type: str,
        layout: str,
        expected: list[str],
    ):
        """The same command family can expose different physical layouts."""
        hass.config_entries.async_update_entry(
            mock_malouf_new_config_entry,
            data={
                **mock_malouf_new_config_entry.data,
                CONF_BED_TYPE: bed_type,
                CONF_MOTOR_COUNT: 4,
                CONF_MALOUF_LAYOUT: layout,
            },
        )
        coordinator = AdjustableBedCoordinator(hass, mock_malouf_new_config_entry)
        await coordinator.async_connect()

        assert [spec.key for spec in coordinator.controller.motor_control_specs] == expected

    @pytest.mark.parametrize("bed_type", [BED_TYPE_MALOUF_NEW_OKIN, BED_TYPE_MALOUF_LEGACY_OKIN])
    async def test_auto_four_motor_layout_does_not_infer_hilo_from_protocol(
        self,
        hass: HomeAssistant,
        mock_malouf_new_config_entry,
        mock_coordinator_connected,
        bed_type: str,
    ):
        """Hi-Lo requires explicit hardware evidence from the user's remote."""
        hass.config_entries.async_update_entry(
            mock_malouf_new_config_entry,
            data={
                **mock_malouf_new_config_entry.data,
                CONF_BED_TYPE: bed_type,
                CONF_MOTOR_COUNT: 4,
            },
        )
        coordinator = AdjustableBedCoordinator(hass, mock_malouf_new_config_entry)
        await coordinator.async_connect()

        assert [spec.key for spec in coordinator.controller.motor_control_specs] == [
            "back",
            "legs",
            "tilt",
            "lumbar",
        ]
        assert coordinator.controller.has_bed_height_support is False


