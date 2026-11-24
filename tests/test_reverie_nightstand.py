"""Tests for Reverie Nightstand bed controller (Protocol 110)."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bleak.exc import BleakError
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed.beds.reverie.comfort import (
    ReverieComfortRequest,
)
from custom_components.adjustable_bed.beds.reverie.nightstand import (
    ReverieNightstandCommands,
    ReverieNightstandController,
)
from custom_components.adjustable_bed.const import (
    BED_TYPE_REVERIE_NIGHTSTAND,
    CONF_BED_TYPE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_HAS_MASSAGE,
    CONF_MOTOR_COUNT,
    CONF_PREFERRED_ADAPTER,
    CONF_PROTOCOL_VARIANT,
    DOMAIN,
    REVERIE_NIGHTSTAND_FOOT_POSITION_UUID,
    REVERIE_NIGHTSTAND_FOOT_WAVE_UUID,
    REVERIE_NIGHTSTAND_HEAD_POSITION_UUID,
    REVERIE_NIGHTSTAND_HEAD_WAVE_UUID,
    REVERIE_NIGHTSTAND_LED_UUID,
    REVERIE_NIGHTSTAND_LINEAR_FOOT_UUID,
    REVERIE_NIGHTSTAND_LINEAR_HEAD_UUID,
    REVERIE_NIGHTSTAND_LINEAR_LUMBAR_UUID,
    REVERIE_NIGHTSTAND_LUMBAR_UUID,
    REVERIE_NIGHTSTAND_MASSAGE_WAVE_UUID,
    REVERIE_NIGHTSTAND_PRESETS_UUID,
    REVERIE_NIGHTSTAND_RGB_UUID,
    REVERIE_STK_SIDE_DATA_UUID,
    REVERIE_STK_SIDE_NO_DATA_UUID,
)
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator

# -----------------------------------------------------------------------------
# Test Fixtures
# -----------------------------------------------------------------------------


@pytest.fixture
def mock_reverie_nightstand_config_entry_data() -> dict:
    """Return mock config entry data for Reverie Nightstand bed."""
    return {
        CONF_ADDRESS: "AA:BB:CC:DD:EE:FF",
        CONF_NAME: "Reverie Nightstand Test Bed",
        CONF_BED_TYPE: BED_TYPE_REVERIE_NIGHTSTAND,
        CONF_MOTOR_COUNT: 2,
        CONF_HAS_MASSAGE: True,
        CONF_DISABLE_ANGLE_SENSING: False,
        CONF_PREFERRED_ADAPTER: "auto",
        CONF_PROTOCOL_VARIANT: "R510L",
    }


@pytest.fixture
def mock_reverie_nightstand_config_entry(
    hass: HomeAssistant, mock_reverie_nightstand_config_entry_data: dict
) -> MockConfigEntry:
    """Return a mock config entry for Reverie Nightstand bed."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Reverie Nightstand Test Bed",
        data=mock_reverie_nightstand_config_entry_data,
        unique_id="AA:BB:CC:DD:EE:FF",
        entry_id="reverie_nightstand_test_entry",
    )
    entry.add_to_hass(hass)
    return entry


# -----------------------------------------------------------------------------
# Command Constants Tests
# -----------------------------------------------------------------------------


class TestReverieNightstandCommands:
    """Test Reverie Nightstand command constants."""

    def test_motor_control_values(self):
        """Motor control values should be correct."""
        assert ReverieNightstandCommands.MOTOR_UP == 0x01
        assert ReverieNightstandCommands.MOTOR_DOWN == 0x02
        assert ReverieNightstandCommands.MOTOR_STOP == 0x00

    def test_led_control_values(self):
        """LED control values should be correct."""
        assert ReverieNightstandCommands.LED_ON == 64
        assert ReverieNightstandCommands.LED_OFF == 0x00

    def test_preset_mode_values(self):
        """Preset mode values should be correct."""
        assert ReverieNightstandCommands.MODE_ZERO_G == 0x01
        assert ReverieNightstandCommands.MODE_ANTI_SNORE == 0x02
        assert ReverieNightstandCommands.MODE_FLAT == 0x03

    def test_memory_preset_calculation(self):
        """memory_preset() should return memory_num + 3."""
        assert ReverieNightstandCommands.memory_preset(1) == 0x04
        assert ReverieNightstandCommands.memory_preset(2) == 0x05
        assert ReverieNightstandCommands.memory_preset(3) == 0x06
        assert ReverieNightstandCommands.memory_preset(4) == 0x07

    def test_store_memory_calculation(self):
        """Store values use the source's decimal slot-plus-83 conversion."""
        assert ReverieNightstandCommands.store_memory(1) == 0x54
        assert ReverieNightstandCommands.store_memory(2) == 0x55
        assert ReverieNightstandCommands.store_memory(3) == 0x56
        assert ReverieNightstandCommands.store_memory(4) == 0x57


# -----------------------------------------------------------------------------
# Controller Tests
# -----------------------------------------------------------------------------


class TestReverieNightstandController:
    """Test ReverieNightstandController."""

    async def test_control_characteristic_uuid(
        self,
        hass: HomeAssistant,
        mock_reverie_nightstand_config_entry,
        mock_coordinator_connected,
    ):
        """Control characteristic should be linear head UUID."""
        coordinator = AdjustableBedCoordinator(
            hass, mock_reverie_nightstand_config_entry
        )
        await coordinator.async_connect()

        assert (
            coordinator.controller.control_characteristic_uuid
            == REVERIE_NIGHTSTAND_LINEAR_HEAD_UUID
        )

    async def test_supports_preset_zero_g(
        self,
        hass: HomeAssistant,
        mock_reverie_nightstand_config_entry,
        mock_coordinator_connected,
    ):
        """Reverie Nightstand should support zero-g preset."""
        coordinator = AdjustableBedCoordinator(
            hass, mock_reverie_nightstand_config_entry
        )
        await coordinator.async_connect()

        assert coordinator.controller.supports_preset_zero_g is True

    async def test_supports_memory_presets(
        self,
        hass: HomeAssistant,
        mock_reverie_nightstand_config_entry,
        mock_coordinator_connected,
    ):
        """Reverie Nightstand should support memory presets."""
        coordinator = AdjustableBedCoordinator(
            hass, mock_reverie_nightstand_config_entry
        )
        await coordinator.async_connect()

        assert coordinator.controller.supports_memory_presets is True

    async def test_memory_slot_count_is_4(
        self,
        hass: HomeAssistant,
        mock_reverie_nightstand_config_entry,
        mock_coordinator_connected,
    ):
        """Reverie Nightstand should have 4 memory slots."""
        coordinator = AdjustableBedCoordinator(
            hass, mock_reverie_nightstand_config_entry
        )
        await coordinator.async_connect()

        assert coordinator.controller.memory_slot_count == 4

    async def test_supports_memory_programming(
        self,
        hass: HomeAssistant,
        mock_reverie_nightstand_config_entry,
        mock_coordinator_connected,
    ):
        """Reverie Nightstand should support memory programming."""
        coordinator = AdjustableBedCoordinator(
            hass, mock_reverie_nightstand_config_entry
        )
        await coordinator.async_connect()

        assert coordinator.controller.supports_memory_programming is True

    async def test_supports_discrete_light_control(
        self,
        hass: HomeAssistant,
        mock_reverie_nightstand_config_entry,
        mock_coordinator_connected,
    ):
        """Reverie Nightstand should support discrete light control."""
        coordinator = AdjustableBedCoordinator(
            hass, mock_reverie_nightstand_config_entry
        )
        await coordinator.async_connect()

        assert coordinator.controller.supports_discrete_light_control is True

    async def test_has_lumbar_support(
        self,
        hass: HomeAssistant,
        mock_reverie_nightstand_config_entry,
        mock_coordinator_connected,
    ):
        """Reverie Nightstand should support lumbar motor."""
        coordinator = AdjustableBedCoordinator(
            hass, mock_reverie_nightstand_config_entry
        )
        await coordinator.async_connect()

        assert coordinator.controller.has_lumbar_support is True


class TestReverieNightstandMovement:
    """Test Reverie Nightstand movement commands."""

    async def test_move_head_up_writes_to_head_char(
        self,
        hass: HomeAssistant,
        mock_reverie_nightstand_config_entry,
        mock_coordinator_connected,
    ):
        """move_head_up should write to linear head characteristic."""
        coordinator = AdjustableBedCoordinator(
            hass, mock_reverie_nightstand_config_entry
        )
        await coordinator.async_connect()
        mock_client = coordinator._client

        await coordinator.controller.move_head_up()

        assert mock_client.write_gatt_char.call_count == 1
        calls = mock_client.write_gatt_char.call_args_list
        assert calls[0][0][0] == REVERIE_NIGHTSTAND_LINEAR_HEAD_UUID
        assert calls[0][0][1] == bytes([ReverieNightstandCommands.MOTOR_UP])

    async def test_move_legs_up_writes_to_foot_char(
        self,
        hass: HomeAssistant,
        mock_reverie_nightstand_config_entry,
        mock_coordinator_connected,
    ):
        """move_legs_up should write to linear foot characteristic."""
        coordinator = AdjustableBedCoordinator(
            hass, mock_reverie_nightstand_config_entry
        )
        await coordinator.async_connect()
        mock_client = coordinator._client

        await coordinator.controller.move_legs_up()

        calls = mock_client.write_gatt_char.call_args_list
        assert len(calls) == 1
        assert calls[0][0][0] == REVERIE_NIGHTSTAND_LINEAR_FOOT_UUID
        assert calls[0][0][1] == bytes([ReverieNightstandCommands.MOTOR_UP])

    async def test_move_lumbar_up_writes_to_lumbar_char(
        self,
        hass: HomeAssistant,
        mock_reverie_nightstand_config_entry,
        mock_coordinator_connected,
    ):
        """move_lumbar_up should write to linear lumbar characteristic."""
        coordinator = AdjustableBedCoordinator(
            hass, mock_reverie_nightstand_config_entry
        )
        await coordinator.async_connect()
        mock_client = coordinator._client

        await coordinator.controller.move_lumbar_up()

        calls = mock_client.write_gatt_char.call_args_list
        assert len(calls) == 1
        assert calls[0][0][0] == REVERIE_NIGHTSTAND_LINEAR_LUMBAR_UUID
        assert calls[0][0][1] == bytes([ReverieNightstandCommands.MOTOR_UP])

    async def test_movement_release_is_a_single_explicit_axis_stop(
        self,
        hass: HomeAssistant,
        mock_reverie_nightstand_config_entry,
        mock_coordinator_connected,
    ):
        """An independent release writes one STOP to the same head axis."""
        coordinator = AdjustableBedCoordinator(
            hass, mock_reverie_nightstand_config_entry
        )
        await coordinator.async_connect()
        mock_client = coordinator._client

        await coordinator.controller.move_head_stop()

        calls = mock_client.write_gatt_char.call_args_list
        assert len(calls) == 1
        assert calls[0][0][0] == REVERIE_NIGHTSTAND_LINEAR_HEAD_UUID
        assert calls[0][0][1] == bytes([ReverieNightstandCommands.MOTOR_STOP])

    async def test_stop_all_writes_to_all_motor_chars(
        self,
        hass: HomeAssistant,
        mock_reverie_nightstand_config_entry,
        mock_coordinator_connected,
    ):
        """stop_all should write STOP to head, foot, and lumbar characteristics."""
        coordinator = AdjustableBedCoordinator(
            hass, mock_reverie_nightstand_config_entry
        )
        await coordinator.async_connect()
        mock_client = coordinator._client

        await coordinator.controller.stop_all()

        calls = mock_client.write_gatt_char.call_args_list
        # Should have 3 calls (head, foot, lumbar)
        assert len(calls) == 3

        # Extract UUIDs written to
        uuids = [call[0][0] for call in calls]
        assert REVERIE_NIGHTSTAND_LINEAR_HEAD_UUID in uuids
        assert REVERIE_NIGHTSTAND_LINEAR_FOOT_UUID in uuids
        assert REVERIE_NIGHTSTAND_LINEAR_LUMBAR_UUID in uuids

        # All should be STOP command
        for call in calls:
            assert call[0][1] == bytes([ReverieNightstandCommands.MOTOR_STOP])

    async def test_bounded_hold_sends_one_press_then_same_axis_stop(
        self,
        hass: HomeAssistant,
        mock_reverie_nightstand_config_entry,
        mock_coordinator_connected,
    ):
        coordinator = AdjustableBedCoordinator(hass, mock_reverie_nightstand_config_entry)
        await coordinator.async_connect()
        mock_client = coordinator._client

        with patch("custom_components.adjustable_bed.beds.reverie.nightstand.asyncio.sleep"):
            await coordinator.controller.hold_control("back_up", 250)

        calls = mock_client.write_gatt_char.call_args_list
        assert [call.args[1] for call in calls] == [b"\x01", b"\x00"]
        assert [call.args[0] for call in calls] == [
            REVERIE_NIGHTSTAND_LINEAR_HEAD_UUID,
            REVERIE_NIGHTSTAND_LINEAR_HEAD_UUID,
        ]

    async def test_stk_side_drift_releases_the_captured_p1_route(
        self,
        hass: HomeAssistant,
        mock_reverie_nightstand_config_entry,
        mock_coordinator_connected,
    ):
        coordinator = AdjustableBedCoordinator(
            hass, mock_reverie_nightstand_config_entry
        )
        await coordinator.async_connect()
        client = coordinator._client
        controller = ReverieNightstandController(coordinator, model="STK")
        controller._set_stk_side("1")

        await controller.move_head_up()
        controller._set_stk_side("2")
        await controller.move_head_stop()

        assert [call.args[0] for call in client.write_gatt_char.call_args_list] == [
            REVERIE_NIGHTSTAND_LINEAR_HEAD_UUID,
            REVERIE_NIGHTSTAND_LINEAR_HEAD_UUID,
        ]
        assert [call.args[1] for call in client.write_gatt_char.call_args_list] == [
            b"\x01",
            b"\x00",
        ]

    async def test_stk_side_drift_releases_the_captured_p3_route(
        self,
        hass: HomeAssistant,
        mock_reverie_nightstand_config_entry,
        mock_coordinator_connected,
    ):
        coordinator = AdjustableBedCoordinator(
            hass, mock_reverie_nightstand_config_entry
        )
        await coordinator.async_connect()
        client = coordinator._client
        controller = ReverieNightstandController(coordinator, model="STK")
        controller._set_stk_side("2")

        await controller.move_head_up()
        controller._set_stk_side("1")
        await controller.move_head_stop()

        calls = client.write_gatt_char.call_args_list
        assert [(call.args[0], call.args[1]) for call in calls] == [
            (REVERIE_STK_SIDE_DATA_UUID, bytes((2, 0x01))),
            (REVERIE_STK_SIDE_NO_DATA_UUID, bytes((2, 0xFF))),
        ]

    @pytest.mark.parametrize("side", ["1", "2", "3"])
    @pytest.mark.parametrize("direction", ["up", "down"])
    @pytest.mark.parametrize("failure", ["cancel", "write_error"])
    async def test_stk_failed_hold_start_releases_its_captured_side(
        self,
        hass,
        mock_reverie_nightstand_config_entry,
        mock_coordinator_connected,
        side,
        direction,
        failure,
    ):
        coordinator = AdjustableBedCoordinator(hass, mock_reverie_nightstand_config_entry)
        await coordinator.async_connect()
        client = coordinator._client
        controller = ReverieNightstandController(coordinator, model="STK")
        controller._set_stk_side(side)
        entered, fail_write = asyncio.Event(), asyncio.Event()
        writes = []

        async def write(characteristic, payload, **_kwargs):
            writes.append((characteristic, payload))
            if len(writes) == 1:
                entered.set()
                await fail_write.wait()
                raise BleakError("Initial write completion failed")

        client.write_gatt_char.side_effect = write
        hold = asyncio.create_task(controller.hold_control(f"back_{direction}", 250))
        changed_side = "2" if side == "1" else "1"
        try:
            async with asyncio.timeout(2):
                await entered.wait()
                controller._set_stk_side(changed_side)
                if failure == "cancel":
                    coordinator.cancel_command.set()
                    hold.cancel()
                else:
                    fail_write.set()
                with pytest.raises(asyncio.CancelledError if failure == "cancel" else BleakError):
                    await hold
            if side == "1":
                expected = [
                    (
                        REVERIE_NIGHTSTAND_LINEAR_HEAD_UUID,
                        b"\x01" if direction == "up" else b"\x02",
                    ),
                    (REVERIE_NIGHTSTAND_LINEAR_HEAD_UUID, b"\x00"),
                ]
            else:
                expected = [
                    (REVERIE_STK_SIDE_DATA_UUID, bytes((int(side), 1 if direction == "up" else 3))),
                    (REVERIE_STK_SIDE_NO_DATA_UUID, bytes((int(side), 0xFF))),
                ]
            assert writes == expected
            assert controller._active_stk_motion_side is None
            assert controller._stk_selected_side == changed_side
        finally:
            if not hold.done():
                hold.cancel()
            await asyncio.gather(hold, return_exceptions=True)
            await coordinator.async_shutdown()

    async def test_absolute_position_uses_the_evidence_low_byte(
        self,
        hass: HomeAssistant,
        mock_reverie_nightstand_config_entry,
        mock_coordinator_connected,
    ):
        coordinator = AdjustableBedCoordinator(hass, mock_reverie_nightstand_config_entry)
        await coordinator.async_connect()
        mock_client = coordinator._client

        await coordinator.controller.set_motor_position("head", 300)

        mock_client.write_gatt_char.assert_called_once_with(
            REVERIE_NIGHTSTAND_HEAD_POSITION_UUID,
            b"\x2c",
            response=True,
        )


class TestReverieNightstandPresets:
    """Test Reverie Nightstand preset commands."""

    async def test_preset_flat_writes_mode_1(
        self,
        hass: HomeAssistant,
        mock_reverie_nightstand_config_entry,
        mock_coordinator_connected,
    ):
        """preset_flat should write MODE_1 to presets characteristic."""
        coordinator = AdjustableBedCoordinator(
            hass, mock_reverie_nightstand_config_entry
        )
        await coordinator.async_connect()
        mock_client = coordinator._client

        await coordinator.controller.preset_flat()

        calls = mock_client.write_gatt_char.call_args_list
        first_call = calls[0]
        assert first_call[0][0] == REVERIE_NIGHTSTAND_PRESETS_UUID
        assert first_call[0][1] == bytes([ReverieNightstandCommands.MODE_FLAT])

    async def test_preset_zero_g_writes_mode_zero_g(
        self,
        hass: HomeAssistant,
        mock_reverie_nightstand_config_entry,
        mock_coordinator_connected,
    ):
        """preset_zero_g should write MODE_ZERO_G to presets characteristic."""
        coordinator = AdjustableBedCoordinator(
            hass, mock_reverie_nightstand_config_entry
        )
        await coordinator.async_connect()
        mock_client = coordinator._client

        await coordinator.controller.preset_zero_g()

        calls = mock_client.write_gatt_char.call_args_list
        first_call = calls[0]
        assert first_call[0][0] == REVERIE_NIGHTSTAND_PRESETS_UUID
        assert first_call[0][1] == bytes([ReverieNightstandCommands.MODE_ZERO_G])

    async def test_preset_memory_1_writes_correct_value(
        self,
        hass: HomeAssistant,
        mock_reverie_nightstand_config_entry,
        mock_coordinator_connected,
    ):
        """preset_memory(1) should write 0x04 to presets characteristic."""
        coordinator = AdjustableBedCoordinator(
            hass, mock_reverie_nightstand_config_entry
        )
        await coordinator.async_connect()
        mock_client = coordinator._client

        await coordinator.controller.preset_memory(1)

        calls = mock_client.write_gatt_char.call_args_list
        first_call = calls[0]
        assert first_call[0][0] == REVERIE_NIGHTSTAND_PRESETS_UUID
        assert first_call[0][1] == bytes([0x04])  # memory_preset(1) = 4

    async def test_preset_memory_4_writes_correct_value(
        self,
        hass: HomeAssistant,
        mock_reverie_nightstand_config_entry,
        mock_coordinator_connected,
    ):
        """preset_memory(4) should write 0x07 to presets characteristic."""
        coordinator = AdjustableBedCoordinator(
            hass, mock_reverie_nightstand_config_entry
        )
        await coordinator.async_connect()
        mock_client = coordinator._client

        await coordinator.controller.preset_memory(4)

        calls = mock_client.write_gatt_char.call_args_list
        first_call = calls[0]
        assert first_call[0][0] == REVERIE_NIGHTSTAND_PRESETS_UUID
        assert first_call[0][1] == bytes([0x07])  # memory_preset(4) = 7

    async def test_program_memory_1_writes_store_value(
        self,
        hass: HomeAssistant,
        mock_reverie_nightstand_config_entry,
        mock_coordinator_connected,
    ):
        """program_memory(1) writes the accepted 0x54 slot byte."""
        coordinator = AdjustableBedCoordinator(
            hass, mock_reverie_nightstand_config_entry
        )
        await coordinator.async_connect()
        mock_client = coordinator._client

        await coordinator.controller.program_memory(1)

        calls = mock_client.write_gatt_char.call_args_list
        first_call = calls[0]
        assert first_call[0][0] == REVERIE_NIGHTSTAND_PRESETS_UUID
        assert first_call[0][1] == bytes([0x54])

    async def test_program_memory_4_writes_store_value(
        self,
        hass: HomeAssistant,
        mock_reverie_nightstand_config_entry,
        mock_coordinator_connected,
    ):
        """program_memory(4) writes the accepted 0x57 slot byte."""
        coordinator = AdjustableBedCoordinator(
            hass, mock_reverie_nightstand_config_entry
        )
        await coordinator.async_connect()
        mock_client = coordinator._client

        await coordinator.controller.program_memory(4)

        calls = mock_client.write_gatt_char.call_args_list
        first_call = calls[0]
        assert first_call[0][0] == REVERIE_NIGHTSTAND_PRESETS_UUID
        assert first_call[0][1] == bytes([0x57])


class TestReverieNightstandLights:
    """Test Reverie Nightstand light commands."""

    async def test_lights_on_writes_led_on(
        self,
        hass: HomeAssistant,
        mock_reverie_nightstand_config_entry,
        mock_coordinator_connected,
    ):
        """lights_on restores known brightness, or falls back to 64."""
        coordinator = AdjustableBedCoordinator(
            hass, mock_reverie_nightstand_config_entry
        )
        await coordinator.async_connect()
        mock_client = coordinator._client

        await coordinator.controller.lights_on()

        calls = mock_client.write_gatt_char.call_args_list
        first_call = calls[0]
        assert first_call[0][0] == REVERIE_NIGHTSTAND_LED_UUID
        assert first_call[0][1] == bytes([ReverieNightstandCommands.LED_ON])

    async def test_lights_off_writes_led_off(
        self,
        hass: HomeAssistant,
        mock_reverie_nightstand_config_entry,
        mock_coordinator_connected,
    ):
        """lights_off should write LED_OFF (0x00) to LED characteristic."""
        coordinator = AdjustableBedCoordinator(
            hass, mock_reverie_nightstand_config_entry
        )
        await coordinator.async_connect()
        mock_client = coordinator._client

        await coordinator.controller.lights_off()

        calls = mock_client.write_gatt_char.call_args_list
        first_call = calls[0]
        assert first_call[0][0] == REVERIE_NIGHTSTAND_LED_UUID
        assert first_call[0][1] == bytes([ReverieNightstandCommands.LED_OFF])

    async def test_lights_on_restores_last_nonzero_brightness(
        self,
        hass: HomeAssistant,
        mock_reverie_nightstand_config_entry,
        mock_coordinator_connected,
    ):
        coordinator = AdjustableBedCoordinator(
            hass, mock_reverie_nightstand_config_entry
        )
        await coordinator.async_connect()
        mock_client = coordinator._client
        mock_client.read_gatt_char = AsyncMock(
            side_effect=[
                bytes((41,)),
                bytes((1, 41, 10, 20, 30)),
                bytes((0,)),
                bytes((0,)),
                bytes((0,)),
            ]
        )

        await coordinator.controller.read_light_state()
        await coordinator.controller.lights_off()
        await coordinator.controller.lights_on()

        writes = [
            call.args[1]
            for call in mock_client.write_gatt_char.call_args_list
            if call.args[0] == REVERIE_NIGHTSTAND_LED_UUID
        ]
        assert writes == [bytes((0,)), bytes((41,))]

    async def test_box_without_the_rgb_characteristic_has_an_on_off_light(
        self,
        hass: HomeAssistant,
        mock_reverie_nightstand_config_entry,
        mock_coordinator_connected,
    ):
        """A RevCB_A1 box has no RGB characteristic; the app then only toggles (#1172)."""
        coordinator = AdjustableBedCoordinator(
            hass, mock_reverie_nightstand_config_entry
        )
        await coordinator.async_connect()
        client = coordinator._client
        controller = ReverieNightstandController(coordinator)
        assert controller.supports_light_level_control
        assert controller.capability_snapshot() is None

        client.services.get_characteristic.side_effect = lambda uuid: (
            None if uuid == REVERIE_NIGHTSTAND_RGB_UUID else MagicMock()
        )
        await controller.async_discover_capabilities()

        assert controller.supports_lights
        assert not controller.supports_light_level_control
        assert not controller.supports_light_color_control
        assert controller.supported_color_mode is None
        assert controller.capability_snapshot() == {"rgb_light": False}
        client.read_gatt_char = AsyncMock(return_value=bytes((0,)))
        await controller.lights_toggle()
        assert REVERIE_NIGHTSTAND_RGB_UUID not in [
            call.args[0] for call in client.read_gatt_char.call_args_list
        ]
        assert client.write_gatt_char.call_args.args[:2] == (
            REVERIE_NIGHTSTAND_LED_UUID,
            bytes((ReverieNightstandCommands.LED_ON,)),
        )
        with pytest.raises(ValueError):
            await controller.set_light_level(50)

        # The stored answer shapes the entities before the next connection.
        stored = ReverieNightstandController(
            coordinator, capability_snapshot={"rgb_light": False}
        )
        assert not stored.supports_light_level_control

    async def test_wave_select_writes_the_app_pattern_numbers(
        self,
        hass: HomeAssistant,
        mock_reverie_nightstand_config_entry,
        mock_coordinator_connected,
    ):
        """The app's wave buttons write 1-4 and Stop writes 0 (#1172)."""
        coordinator = AdjustableBedCoordinator(
            hass, mock_reverie_nightstand_config_entry
        )
        await coordinator.async_connect()
        client = coordinator._client
        controller = ReverieNightstandController(coordinator)
        assert "wave" not in controller.massage_intensity_zones
        wave = next(
            spec
            for spec in controller.controller_select_specs
            if spec.key == "reverie_massage_wave"
        )
        assert wave.options == ("off", "1", "2", "3", "4")

        for option in ("3", "off"):
            await wave.select_fn(controller, option)
            assert coordinator.controller_state[wave.state_key] == option
        writes = [
            call.args[1]
            for call in client.write_gatt_char.call_args_list
            if call.args[0] == REVERIE_NIGHTSTAND_MASSAGE_WAVE_UUID
        ]
        assert writes == [bytes((3,)), bytes((0,))]
        with pytest.raises(ValueError):
            await controller.set_massage_intensity("wave", 5)


class TestReverieNightstandMultiCharacteristic:
    """Test Reverie Nightstand multi-characteristic protocol."""

    def test_all_characteristic_uuids_defined(self):
        """All characteristic UUIDs should be defined."""
        assert REVERIE_NIGHTSTAND_LINEAR_HEAD_UUID is not None
        assert REVERIE_NIGHTSTAND_LINEAR_FOOT_UUID is not None
        assert REVERIE_NIGHTSTAND_LINEAR_LUMBAR_UUID is not None
        assert REVERIE_NIGHTSTAND_PRESETS_UUID is not None
        assert REVERIE_NIGHTSTAND_LED_UUID is not None

    def test_characteristic_uuids_are_different(self):
        """All motor characteristics should be different UUIDs."""
        uuids = [
            REVERIE_NIGHTSTAND_LINEAR_HEAD_UUID,
            REVERIE_NIGHTSTAND_LINEAR_FOOT_UUID,
            REVERIE_NIGHTSTAND_LINEAR_LUMBAR_UUID,
        ]
        assert len(uuids) == len(set(uuids))

    def test_single_byte_commands(self):
        """All motor commands should be single bytes."""
        assert ReverieNightstandCommands.MOTOR_UP <= 0xFF
        assert ReverieNightstandCommands.MOTOR_DOWN <= 0xFF
        assert ReverieNightstandCommands.MOTOR_STOP <= 0xFF
        assert ReverieNightstandCommands.LED_ON <= 0xFF
        assert ReverieNightstandCommands.LED_OFF <= 0xFF

    async def test_stk_routine_uses_live_preserved_axes_from_notifications(
        self,
        hass: HomeAssistant,
        mock_reverie_nightstand_config_entry,
        mock_coordinator_connected,
    ):
        """Normal STK notifications produce the exact routine preservation keys."""
        coordinator = AdjustableBedCoordinator(
            hass, mock_reverie_nightstand_config_entry
        )
        await coordinator.async_connect()
        client = coordinator._client
        assert client is not None

        controller = ReverieNightstandController(coordinator, model="STK")
        coordinator._controller = controller
        await controller.start_notify()
        handlers = {
            call.args[0]: call.args[1]
            for call in client.start_notify.call_args_list
        }
        handlers[REVERIE_NIGHTSTAND_HEAD_POSITION_UUID](None, bytearray((25,)))
        handlers[REVERIE_NIGHTSTAND_LUMBAR_UUID](None, bytearray((54,)))

        assert coordinator.controller_state["reverie_stk_head_position"] == 25
        assert coordinator.controller_state["reverie_stk_head2_position"] == 54

        controller._set_stk_side("1")
        request = ReverieComfortRequest(
            head_position=25,
            foot_position=40,
            lumbar_position=30,
            head_massage=1,
            foot_massage=2,
        )
        await controller.async_set_comfort(request)
        client.write_gatt_char.assert_not_awaited()
        await controller.async_start_routine([(request, 1)])

        client.write_gatt_char.assert_awaited_with(
            REVERIE_NIGHTSTAND_PRESETS_UUID,
            bytes.fromhex("0019283608040400000000"),
            response=True,
        )
        controller._cancel_routine()

    async def test_massage_levels_without_notify_do_not_block_startup(
        self,
        hass: HomeAssistant,
        mock_reverie_nightstand_config_entry,
        mock_coordinator_connected,
    ) -> None:
        """A control box with read/write-only massage levels still starts (#1016)."""
        coordinator = AdjustableBedCoordinator(
            hass, mock_reverie_nightstand_config_entry
        )
        await coordinator.async_connect()
        client = coordinator._client
        assert client is not None
        wave_uuids = {
            REVERIE_NIGHTSTAND_HEAD_WAVE_UUID,
            REVERIE_NIGHTSTAND_FOOT_WAVE_UUID,
        }
        read_write_only = MagicMock(properties=["read", "write"])
        notifying = MagicMock(properties=["read", "write", "notify"])
        client.services.get_characteristic.side_effect = lambda uuid: (
            read_write_only if uuid in wave_uuids else notifying
        )

        async def start_notify(uuid: str, _handler: object) -> None:
            if uuid in wave_uuids:
                raise BleakError(
                    f"Characteristic {uuid} does not have notify or indicate property set."
                )

        client.start_notify.reset_mock()
        client.start_notify.side_effect = start_notify

        controller = ReverieNightstandController(coordinator)
        assert controller.model.massage
        await controller.start_notify()

        subscribed = [call.args[0] for call in client.start_notify.call_args_list]
        assert REVERIE_NIGHTSTAND_HEAD_POSITION_UUID in subscribed
        assert REVERIE_NIGHTSTAND_FOOT_POSITION_UUID in subscribed
        assert wave_uuids.isdisjoint(subscribed)

    async def test_v1_negative_lumbar_routine_is_a_source_defined_no_write(
        self,
        hass: HomeAssistant,
        mock_reverie_nightstand_config_entry,
        mock_coordinator_connected,
    ) -> None:
        coordinator = AdjustableBedCoordinator(
            hass, mock_reverie_nightstand_config_entry
        )
        await coordinator.async_connect()
        client = coordinator._client
        assert client is not None
        controller = ReverieNightstandController(coordinator, model="5D")
        coordinator._controller = controller
        request = ReverieComfortRequest(
            head_position=25,
            foot_position=40,
            lumbar_position=-1,
            head_massage=0,
            foot_massage=0,
        )

        await controller.async_start_routine([(request, 1)])

        client.write_gatt_char.assert_not_awaited()
        controller._cancel_routine()
