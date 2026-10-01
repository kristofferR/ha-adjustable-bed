"""Tests for Cool Base bed controller."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bleak.exc import BleakError
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed.beds.coolbase import (
    STATE_LEFT_FAN,
    STATE_LIGHT,
    STATE_MASSAGE_MODE,
    STATE_RIGHT_FAN,
    CoolBaseCommands,
    CoolBaseController,
)
from custom_components.adjustable_bed.const import (
    BED_TYPE_COOLBASE,
    CONF_BED_TYPE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_HAS_MASSAGE,
    CONF_MOTOR_COUNT,
    CONF_MOTOR_PULSE_DELAY_MS,
    CONF_PREFERRED_ADAPTER,
    DOMAIN,
    KEESON_BASE_NOTIFY_CHAR_UUID,
    KEESON_BASE_SERVICE_UUID,
    KEESON_BASE_WRITE_CHAR_UUID,
)
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator

# -----------------------------------------------------------------------------
# Test Fixtures
# -----------------------------------------------------------------------------


@pytest.fixture
def mock_coolbase_config_entry_data() -> dict:
    """Return mock config entry data for Cool Base bed."""
    return {
        CONF_ADDRESS: "AA:BB:CC:DD:EE:FF",
        CONF_NAME: "Cool Base Test Bed",
        CONF_BED_TYPE: BED_TYPE_COOLBASE,
        CONF_MOTOR_COUNT: 2,
        CONF_HAS_MASSAGE: True,
        CONF_DISABLE_ANGLE_SENSING: True,
        CONF_PREFERRED_ADAPTER: "auto",
    }


@pytest.fixture
def mock_coolbase_config_entry(
    hass: HomeAssistant, mock_coolbase_config_entry_data: dict
) -> MockConfigEntry:
    """Return a mock config entry for Cool Base bed."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Cool Base Test Bed",
        data=mock_coolbase_config_entry_data,
        unique_id="AA:BB:CC:DD:EE:FF",
        entry_id="coolbase_test_entry",
    )
    entry.add_to_hass(hass)
    return entry


# -----------------------------------------------------------------------------
# Command Constants Tests
# -----------------------------------------------------------------------------


class TestCoolBaseCommands:
    """Test Cool Base command constants."""

    def test_motor_commands(self):
        """Motor commands should be correct values."""
        assert CoolBaseCommands.MOTOR_HEAD_UP == 0x01
        assert CoolBaseCommands.MOTOR_HEAD_DOWN == 0x02
        assert CoolBaseCommands.MOTOR_FEET_UP == 0x04
        assert CoolBaseCommands.MOTOR_FEET_DOWN == 0x08

    def test_preset_commands(self):
        """Preset commands should be correct values."""
        assert CoolBaseCommands.PRESET_FLAT == 0x08000000
        assert CoolBaseCommands.PRESET_ZERO_G == 0x00001000
        assert CoolBaseCommands.PRESET_TV == 0x00004000
        assert CoolBaseCommands.PRESET_ANTI_SNORE == 0x00008000
        assert CoolBaseCommands.PRESET_MEMORY_1 == 0x00010000
        assert CoolBaseCommands.PRESET_MEMORY_2 == 0x00040000

    def test_light_command(self):
        """Light toggle command should be correct value."""
        assert CoolBaseCommands.TOGGLE_LIGHT == 0x00020000

    def test_massage_commands(self):
        """Massage commands should be correct values."""
        assert CoolBaseCommands.MASSAGE_HEAD == 0x00000800
        assert CoolBaseCommands.MASSAGE_FOOT == 0x00000400
        assert CoolBaseCommands.MASSAGE_LEVEL == 0x04000000

    def test_fan_commands(self):
        """Fan commands should be correct values (unique to Cool Base)."""
        assert CoolBaseCommands.FAN_LEFT == 0x00400000
        assert CoolBaseCommands.FAN_RIGHT == 0x40000000
        assert CoolBaseCommands.FAN_SYNC == 0x00040000


# -----------------------------------------------------------------------------
# Packet Building Tests
# -----------------------------------------------------------------------------


class TestCoolBasePacketBuilding:
    """Test Cool Base packet building."""

    def test_packet_is_8_bytes(self):
        """Packets should be exactly 8 bytes."""
        controller = CoolBaseController(MagicMock())
        packet = controller._build_command(cmd0=0x01)

        assert len(packet) == 8

    def test_packet_header(self):
        """Packet should start with correct header [0xE5, 0xFE, 0x16]."""
        controller = CoolBaseController(MagicMock())
        packet = controller._build_command()

        assert packet[0] == 0xE5
        assert packet[1] == 0xFE
        assert packet[2] == 0x16

    def test_command_bytes_position(self):
        """Command bytes should be in positions 3-6."""
        controller = CoolBaseController(MagicMock())
        packet = controller._build_command(cmd0=0x11, cmd1=0x22, cmd2=0x33, cmd3=0x44)

        assert packet[3] == 0x11  # cmd0
        assert packet[4] == 0x22  # cmd1
        assert packet[5] == 0x33  # cmd2
        assert packet[6] == 0x44  # cmd3

    def test_checksum_calculation(self):
        """Checksum should be XOR-based: (sum ^ 0xFF) & 0xFF."""
        controller = CoolBaseController(MagicMock())
        packet = controller._build_command()  # All zeros for command bytes

        # Header sum: 0xE5 + 0xFE + 0x16 = 0x1F9
        # With all zero commands: sum = 0x1F9
        # checksum = (0x1F9 ^ 0xFF) & 0xFF = 0x106 & 0xFF = 0x06
        expected_checksum = ((0xE5 + 0xFE + 0x16) ^ 0xFF) & 0xFF
        assert packet[7] == expected_checksum

    def test_build_from_value_splits_correctly(self):
        """_build_command_from_value should split 32-bit value into bytes."""
        controller = CoolBaseController(MagicMock())
        # PRESET_FLAT = 0x08000000
        packet = controller._build_command_from_value(CoolBaseCommands.PRESET_FLAT)

        assert packet[3] == 0x00  # cmd0 (bits 0-7)
        assert packet[4] == 0x00  # cmd1 (bits 8-15)
        assert packet[5] == 0x00  # cmd2 (bits 16-23)
        assert packet[6] == 0x08  # cmd3 (bits 24-31)


# -----------------------------------------------------------------------------
# Controller Tests
# -----------------------------------------------------------------------------


class TestCoolBaseController:
    """Test CoolBaseController."""

    async def test_control_characteristic_uuid(
        self,
        hass: HomeAssistant,
        mock_coolbase_config_entry,
        mock_coordinator_connected,
    ):
        """Control characteristic should use Keeson Base write UUID."""
        coordinator = AdjustableBedCoordinator(hass, mock_coolbase_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.control_characteristic_uuid == KEESON_BASE_WRITE_CHAR_UUID

    async def test_supports_preset_zero_g(
        self,
        hass: HomeAssistant,
        mock_coolbase_config_entry,
        mock_coordinator_connected,
    ):
        """Cool Base should support zero-g preset."""
        coordinator = AdjustableBedCoordinator(hass, mock_coolbase_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.supports_preset_zero_g is True

    async def test_supports_preset_tv(
        self,
        hass: HomeAssistant,
        mock_coolbase_config_entry,
        mock_coordinator_connected,
    ):
        """Cool Base should support TV preset."""
        coordinator = AdjustableBedCoordinator(hass, mock_coolbase_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.supports_preset_tv is True

    async def test_supports_preset_anti_snore(
        self,
        hass: HomeAssistant,
        mock_coolbase_config_entry,
        mock_coordinator_connected,
    ):
        """Cool Base should support anti-snore preset."""
        coordinator = AdjustableBedCoordinator(hass, mock_coolbase_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.supports_preset_anti_snore is True

    async def test_supports_lights(
        self,
        hass: HomeAssistant,
        mock_coolbase_config_entry,
        mock_coordinator_connected,
    ):
        """Cool Base should support light control."""
        coordinator = AdjustableBedCoordinator(hass, mock_coolbase_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.supports_lights is True

    async def test_supports_fan_control(
        self,
        hass: HomeAssistant,
        mock_coolbase_config_entry,
        mock_coordinator_connected,
    ):
        """Cool Base should support fan control (unique feature)."""
        coordinator = AdjustableBedCoordinator(hass, mock_coolbase_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.supports_fan_control is True

    async def test_fan_level_max(
        self,
        hass: HomeAssistant,
        mock_coolbase_config_entry,
        mock_coordinator_connected,
    ):
        """Cool Base should have max fan level of 3."""
        coordinator = AdjustableBedCoordinator(hass, mock_coolbase_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.fan_level_max == 3

    async def test_cool_base_profile_has_no_inferred_memory_or_lounge(
        self,
        hass: HomeAssistant,
        mock_coolbase_config_entry,
        mock_coordinator_connected,
    ):
        """The app's star frame has no proven memory meaning and there is no lounge."""
        coordinator = AdjustableBedCoordinator(hass, mock_coolbase_config_entry)
        await coordinator.async_connect()
        controller = coordinator.controller

        assert controller.memory_slot_count == 0
        assert controller.supports_memory_presets is False
        assert controller.supports_preset_lounge is False
        assert "coolbase_star" in {spec.key for spec in controller.controller_button_specs}

    def test_dewert_okin_profile_exposes_memory_two_without_fan_control(self):
        """DewertOKIN OKIN-BLE profile reuses sync-wind command as Memory 2."""
        controller = CoolBaseController(MagicMock(), dewert_okin_profile=True)

        assert controller.memory_slot_count == 2
        assert controller.supports_fan_control is False

    async def test_default_profile_rejects_memory_two(self):
        """Base-I5 profile should not send the sync-wind command as Memory 2."""
        controller = CoolBaseController(MagicMock())
        controller.write_command = AsyncMock()

        await controller.preset_memory(2)

        controller.write_command.assert_not_awaited()

    async def test_dewert_okin_profile_memory_two_sends_correct_packet(self):
        """DewertOKIN profile should send cmd2=0x04 for Memory 2."""
        controller = CoolBaseController(MagicMock(), dewert_okin_profile=True)
        controller.write_command = AsyncMock()

        await controller.preset_memory(2)

        controller.write_command.assert_awaited_once_with(
            controller._build_command_from_value(CoolBaseCommands.PRESET_MEMORY_2)
        )


# -----------------------------------------------------------------------------
# Movement Tests
# -----------------------------------------------------------------------------


class TestCoolBaseMovement:
    """Test Cool Base movement commands."""

    async def test_move_head_up_sends_8_byte_packet(
        self,
        hass: HomeAssistant,
        mock_coolbase_config_entry,
        mock_coordinator_connected,
    ):
        """move_head_up should send 8-byte packet."""
        hass.config_entries.async_update_entry(
            mock_coolbase_config_entry,
            data={**mock_coolbase_config_entry.data, CONF_MOTOR_PULSE_DELAY_MS: 0},
        )
        coordinator = AdjustableBedCoordinator(hass, mock_coolbase_config_entry)
        await coordinator.async_connect()
        mock_client = coordinator._client

        await coordinator.controller.move_head_up()

        assert mock_client.write_gatt_char.called
        calls = mock_client.write_gatt_char.call_args_list
        first_call_data = calls[0][0][1]
        assert len(first_call_data) == 8

    async def test_stop_all_sends_zero_command(
        self,
        hass: HomeAssistant,
        mock_coolbase_config_entry,
        mock_coordinator_connected,
    ):
        """stop_all should send all-zero command bytes."""
        coordinator = AdjustableBedCoordinator(hass, mock_coolbase_config_entry)
        await coordinator.async_connect()
        mock_client = coordinator._client

        await coordinator.controller.stop_all()

        calls = mock_client.write_gatt_char.call_args_list
        call_data = calls[0][0][1]
        # Command bytes should all be zero
        assert call_data[3] == 0x00
        assert call_data[4] == 0x00
        assert call_data[5] == 0x00
        assert call_data[6] == 0x00


# -----------------------------------------------------------------------------
# Fan Control Tests
# -----------------------------------------------------------------------------


class TestCoolBaseFanControl:
    """Test Cool Base fan control commands."""

    @pytest.fixture(autouse=True)
    def _no_click_query_delay(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Taps are followed by spaced status queries; tests need not wait them out."""
        monkeypatch.setattr("custom_components.adjustable_bed.beds.coolbase._CLICK_QUERY_DELAY", 0)

    async def test_fan_left_cycle_sends_correct_packet(
        self,
        hass: HomeAssistant,
        mock_coolbase_config_entry,
        mock_coordinator_connected,
    ):
        """fan_left_cycle should send FAN_LEFT command."""
        coordinator = AdjustableBedCoordinator(hass, mock_coolbase_config_entry)
        await coordinator.async_connect()
        mock_client = coordinator._client

        await coordinator.controller.fan_left_cycle()

        calls = mock_client.write_gatt_char.call_args_list
        call_data = calls[0][0][1]
        # FAN_LEFT = 0x00400000 -> cmd2=0x40
        assert call_data[5] == 0x40

    async def test_fan_right_cycle_sends_correct_packet(
        self,
        hass: HomeAssistant,
        mock_coolbase_config_entry,
        mock_coordinator_connected,
    ):
        """fan_right_cycle should send FAN_RIGHT command."""
        coordinator = AdjustableBedCoordinator(hass, mock_coolbase_config_entry)
        await coordinator.async_connect()
        mock_client = coordinator._client

        await coordinator.controller.fan_right_cycle()

        calls = mock_client.write_gatt_char.call_args_list
        call_data = calls[0][0][1]
        # FAN_RIGHT = 0x40000000 -> cmd3=0x40
        assert call_data[6] == 0x40

    async def test_fan_sync_cycle_sends_correct_packet(
        self,
        hass: HomeAssistant,
        mock_coolbase_config_entry,
        mock_coordinator_connected,
    ):
        """fan_sync_cycle should send FAN_SYNC command."""
        coordinator = AdjustableBedCoordinator(hass, mock_coolbase_config_entry)
        await coordinator.async_connect()
        mock_client = coordinator._client

        await coordinator.controller.fan_sync_cycle()

        calls = mock_client.write_gatt_char.call_args_list
        call_data = calls[0][0][1]
        # FAN_SYNC = 0x00040000 -> cmd2=0x04
        assert call_data[5] == 0x04


# -----------------------------------------------------------------------------
# Accepted com.keeson.coolbase 1.0.0 artifact vectors (row047)
# -----------------------------------------------------------------------------

# Every literal frame the app writes, in its command-table order.
APP_FRAMES = {
    "head_up": (CoolBaseCommands.MOTOR_HEAD_UP, "e5fe160100000005"),
    "head_down": (CoolBaseCommands.MOTOR_HEAD_DOWN, "e5fe160200000004"),
    "foot_up": (CoolBaseCommands.MOTOR_FEET_UP, "e5fe160400000002"),
    "foot_down": (CoolBaseCommands.MOTOR_FEET_DOWN, "e5fe1608000000fe"),
    "foot_massage": (CoolBaseCommands.MASSAGE_FOOT, "e5fe160004000002"),
    "head_massage": (CoolBaseCommands.MASSAGE_HEAD, "e5fe1600080000fe"),
    "left_fan": (CoolBaseCommands.FAN_LEFT, "e5fe1600004000c6"),
    "star": (CoolBaseCommands.STAR, "e5fe160000010005"),
    "massage_mode": (CoolBaseCommands.MASSAGE_LEVEL, "e5fe160000000402"),
    "right_fan": (CoolBaseCommands.FAN_RIGHT, "e5fe1600000040c6"),
    "fan_sync": (CoolBaseCommands.FAN_SYNC, "e5fe160000040002"),
    "tv": (CoolBaseCommands.PRESET_TV, "e5fe1600400000c6"),
    "zero_g": (CoolBaseCommands.PRESET_ZERO_G, "e5fe1600100000f6"),
    "flat": (CoolBaseCommands.PRESET_FLAT, "e5fe1600000008fe"),
    "light": (CoolBaseCommands.TOGGLE_LIGHT, "e5fe160000020004"),
    "anti_snore": (CoolBaseCommands.PRESET_ANTI_SNORE, "e5fe160080000086"),
}
STATUS_QUERY = bytes.fromhex("e5fe160000000006")


def _status(b13: int = 0, b19: int = 0, b20: int = 0, b21: int = 0, length: int = 28) -> bytes:
    data = bytearray(length)
    for index, value in ((13, b13), (19, b19), (20, b20), (21, b21)):
        if index < length:
            data[index] = value
    return bytes(data)


def _controller(*, dewert_okin_profile: bool = False) -> CoolBaseController:
    controller = CoolBaseController(MagicMock(), dewert_okin_profile=dewert_okin_profile)
    controller.write_command = AsyncMock()
    return controller


class TestCoolBaseAppVectors:
    """Byte-exact frames, parser, timing and exposure from the accepted audit."""

    @pytest.mark.parametrize("name", sorted(APP_FRAMES))
    def test_builder_reproduces_every_app_literal(self, name: str) -> None:
        value, expected = APP_FRAMES[name]
        assert _controller()._build_command_from_value(value).hex() == expected

    def test_status_query_is_the_all_zero_frame(self) -> None:
        assert _controller()._build_command() == STATUS_QUERY

    @pytest.mark.parametrize(
        ("frame", "expected"),
        [
            (_status(), {"light": False, "mode": 0, "left": 0, "right": 0}),
            (_status(64, 2, 1, 3), {"light": True, "mode": 2, "left": 1, "right": 3}),
        ],
    )
    def test_parser_vectors(self, frame: bytes, expected: dict[str, object]) -> None:
        controller = _controller()
        controller._parse_notification(frame)
        assert controller.led_on is expected["light"]
        assert controller.massage_level == expected["mode"]
        assert (controller.left_fan_level, controller.right_fan_level) == (
            expected["left"],
            expected["right"],
        )
        controller._coordinator.handle_controller_state_updates.assert_called_with(
            {
                STATE_LEFT_FAN: expected["left"],
                STATE_RIGHT_FAN: expected["right"],
                STATE_MASSAGE_MODE: expected["mode"],
                STATE_LIGHT: expected["light"],
            }
        )

    def test_out_of_range_values_keep_previous_state(self) -> None:
        controller = _controller()
        controller._parse_notification(_status(64, 2, 1, 3))
        controller._parse_notification(_status(128, 4, 255, 4))
        assert controller.led_on is True
        assert controller.massage_level == 2
        assert (controller.left_fan_level, controller.right_fan_level) == (1, 3)
        # Bits 4/5 of byte 13 do not alter the light flag.
        controller._parse_notification(_status(0x30))
        assert controller.led_on is False

    @pytest.mark.parametrize("length", [0, 22, 27, 29, 56])
    def test_only_exact_28_byte_replies_are_parsed(self, length: int) -> None:
        controller = _controller()
        controller._parse_notification(_status(64, 1, 1, 1, length=length))
        assert controller.led_on is None
        assert controller.left_fan_level is None
        controller._coordinator.handle_controller_state_updates.assert_not_called()

    async def test_tap_sends_command_then_three_spaced_status_queries(self) -> None:
        controller = _controller()
        with patch(
            "custom_components.adjustable_bed.beds.coolbase.asyncio.sleep", AsyncMock()
        ) as sleep:
            await controller.fan_left_cycle()
        frames = [call.args[0] for call in controller.write_command.await_args_list]
        assert frames == [bytes.fromhex(APP_FRAMES["left_fan"][1]), *[STATUS_QUERY] * 3]
        assert [call.args[0] for call in sleep.await_args_list] == [0.2, 0.2, 0.2]

    async def test_dewert_okin_profile_taps_send_no_status_queries(self) -> None:
        controller = _controller(dewert_okin_profile=True)
        await controller.preset_tv()
        controller.write_command.assert_awaited_once()

    async def test_button_specs_press_app_frames(self) -> None:
        controller = _controller()
        specs = {spec.key: spec for spec in controller.controller_button_specs}
        assert set(specs) == {
            "coolbase_left_fan",
            "coolbase_right_fan",
            "coolbase_fan_sync",
            "coolbase_head_massage",
            "coolbase_foot_massage",
            "coolbase_massage_mode",
            "coolbase_star",
        }
        assert specs["coolbase_star"].cancel_movement is True
        assert specs["coolbase_left_fan"].cancel_movement is False
        with patch("custom_components.adjustable_bed.beds.coolbase.asyncio.sleep", AsyncMock()):
            for key, frame in (("coolbase_star", "star"), ("coolbase_massage_mode", "massage_mode")):
                controller.write_command.reset_mock()
                await specs[key].press_fn(controller)
                first = controller.write_command.await_args_list[0].args[0]
                assert first.hex() == APP_FRAMES[frame][1]

    @pytest.mark.parametrize("dewert_okin_profile", [False, True])
    def test_generic_massage_controls_do_not_duplicate_app_buttons(
        self, dewert_okin_profile: bool
    ) -> None:
        controller = _controller(dewert_okin_profile=dewert_okin_profile)
        generic = (
            controller.supports_massage_toggle_control,
            controller.supports_head_massage_intensity_step_control,
            controller.supports_foot_massage_intensity_step_control,
        )
        assert generic == (dewert_okin_profile,) * 3

    def test_dewert_okin_profile_keeps_its_own_surface(self) -> None:
        controller = _controller(dewert_okin_profile=True)
        assert controller.controller_button_specs == ()
        assert controller.controller_state_sensor_specs == ()
        assert controller.diagnostic_poll_interval is None
        assert controller.supports_light_state_feedback is False
        assert controller.supports_preset_lounge is True

    async def test_status_poll_mirrors_app_interval(self) -> None:
        controller = _controller()
        assert controller.diagnostic_poll_interval == 3.0
        assert {spec.state_key for spec in controller.controller_state_sensor_specs} == {
            STATE_LEFT_FAN,
            STATE_RIGHT_FAN,
            STATE_MASSAGE_MODE,
        }
        await controller.async_refresh_diagnostics()
        controller.write_command.assert_awaited_once()
        assert controller.write_command.await_args.args[0] == STATUS_QUERY

    def test_session_end_clears_reported_state(self) -> None:
        controller = _controller()
        controller._parse_notification(_status(64, 1, 2, 3))
        controller.invalidate_diagnostics()
        assert controller.get_light_state() == {"is_on": None}
        controller._coordinator.handle_controller_state_updates.assert_called_with(
            {STATE_LEFT_FAN: None, STATE_RIGHT_FAN: None, STATE_MASSAGE_MODE: None, STATE_LIGHT: None}
        )

    @pytest.mark.parametrize(
        ("reported", "requested", "toggles"),
        [(False, True, 1), (True, True, 0), (True, False, 1), (False, False, 0)],
    )
    async def test_light_on_off_toggles_only_on_mismatch(
        self, reported: bool, requested: bool, toggles: int
    ) -> None:
        controller = _controller()
        controller._parse_notification(_status(64 if reported else 0))
        controller.lights_toggle = AsyncMock()
        await (controller.lights_on() if requested else controller.lights_off())
        assert controller.lights_toggle.await_count == toggles

    async def test_unknown_light_state_queries_then_uses_reply(self) -> None:
        controller = _controller()
        controller.lights_toggle = AsyncMock()

        async def reply(frame: bytes, **_: object) -> None:
            assert frame == STATUS_QUERY
            asyncio.get_running_loop().call_soon(controller._parse_notification, _status(0))

        controller.write_command.side_effect = reply
        await controller.lights_on()
        controller.lights_toggle.assert_awaited_once()

    async def test_unknown_light_state_without_reply_raises(self) -> None:
        controller = _controller()
        controller.lights_toggle = AsyncMock()
        with (
            patch("custom_components.adjustable_bed.beds.coolbase._LIGHT_STATE_WAIT", 0.01),
            pytest.raises(HomeAssistantError),
        ):
            await controller.lights_off()
        assert controller.write_command.await_args.args[0] == STATUS_QUERY
        controller.lights_toggle.assert_not_awaited()

    @pytest.mark.parametrize(
        ("properties", "response"),
        [(["write", "write-without-response"], False), (["write"], True)],
    )
    def test_write_type_mirrors_android_default(
        self, properties: list[str], response: bool
    ) -> None:
        dead = SimpleNamespace(uuid=KEESON_BASE_WRITE_CHAR_UUID, properties=["write"])
        char = SimpleNamespace(uuid=KEESON_BASE_WRITE_CHAR_UUID, properties=properties)
        client = MagicMock(is_connected=True)
        client.services = [
            SimpleNamespace(uuid="0000ffe0-0000-1000-8000-00805f9b34fb", characteristics=[dead]),
            SimpleNamespace(uuid=KEESON_BASE_SERVICE_UUID, characteristics=[char]),
        ]
        controller = CoolBaseController(MagicMock(client=client))
        controller._init_write_mode()
        assert controller._write_with_response is response
        # The dead alternate FFE9 under FFE0 is never the destination.
        assert controller._write_char is char

    async def test_write_command_uses_discovered_mode_and_instance(self) -> None:
        char = SimpleNamespace(uuid=KEESON_BASE_WRITE_CHAR_UUID, properties=["write-without-response"])
        client = MagicMock(is_connected=True)
        client.services = [SimpleNamespace(uuid=KEESON_BASE_SERVICE_UUID, characteristics=[char])]
        controller = CoolBaseController(MagicMock(client=client))
        controller._write_gatt_with_retry = AsyncMock()
        await controller.write_command(STATUS_QUERY)
        kwargs = controller._write_gatt_with_retry.await_args.kwargs
        assert kwargs["response"] is False
        assert kwargs["characteristic"] is char

    async def test_status_replies_subscribe_with_angle_sensing_disabled(
        self,
        hass: HomeAssistant,
        mock_coolbase_config_entry,
        mock_coordinator_connected,
    ) -> None:
        """The default entry disables angle sensing; status replies still need notify."""
        coordinator = AdjustableBedCoordinator(hass, mock_coolbase_config_entry)
        await coordinator.async_connect()
        controller = coordinator.controller
        assert controller.requires_notification_channel is True
        coordinator._client.start_notify.assert_awaited()
        assert coordinator._client.start_notify.await_args.args[0] == KEESON_BASE_NOTIFY_CHAR_UUID

    @pytest.mark.parametrize(("dewert_okin_profile", "raises"), [(False, True), (True, False)])
    async def test_required_notify_failure_propagates(
        self, dewert_okin_profile: bool, raises: bool
    ) -> None:
        client = MagicMock(is_connected=True)
        client.start_notify = AsyncMock(side_effect=BleakError("no CCCD"))
        controller = CoolBaseController(MagicMock(client=client), dewert_okin_profile=dewert_okin_profile)
        if raises:
            with pytest.raises(BleakError):
                await controller.start_notify()
        else:
            await controller.start_notify()

    def test_dewert_okin_profile_marks_cool_base_sensors_stale(self) -> None:
        assert _controller().stale_controller_state_sensor_entity_keys == frozenset()
        assert _controller(dewert_okin_profile=True).stale_controller_state_sensor_entity_keys == {
            STATE_LEFT_FAN,
            STATE_RIGHT_FAN,
            STATE_MASSAGE_MODE,
        }
        assert _controller(dewert_okin_profile=True).requires_notification_channel is False

    def test_capability_surface_has_no_position_or_settings(self) -> None:
        controller = _controller()
        assert controller.supports_position_feedback is False
        assert controller.supports_discrete_light_control is False
        assert controller.supports_memory_programming is False


async def test_protocol_change_removes_cool_base_entities(hass: HomeAssistant) -> None:
    """Changing bed type must not strand Cool Base sensors or app buttons."""
    from homeassistant.helpers import entity_registry as er

    from custom_components.adjustable_bed.beds.okin_rf_eco_bt import OkinRfEcoBtController
    from custom_components.adjustable_bed.button import _button_entities_for
    from custom_components.adjustable_bed.const import BED_TYPE_OKIN_RF_ECO_BT
    from custom_components.adjustable_bed.sensor import _sensor_entities_for
    from tests.test_furnimove import make_controller
    from tests.test_malouf_app_entities import configure_entity_runtime

    controller = OkinRfEcoBtController(make_controller()._coordinator)
    runtime = configure_entity_runtime(hass, controller, BED_TYPE_OKIN_RF_ECO_BT)
    registry = er.async_get(hass)
    stale = [
        registry.async_get_or_create(domain, DOMAIN, f"bed_{key}_left", config_entry=runtime.entry)
        for domain, key in (
            ("sensor", STATE_LEFT_FAN),
            ("sensor", STATE_RIGHT_FAN),
            ("sensor", STATE_MASSAGE_MODE),
            ("button", "coolbase_left_fan"),
        )
    ]
    _sensor_entities_for(hass, runtime)
    _button_entities_for(hass, runtime)
    assert all(registry.async_get(row.entity_id) is None for row in stale)
