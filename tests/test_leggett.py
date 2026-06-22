"""Tests for Leggett & Platt bed controller."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed.beds.leggett_gen2 import (
    LeggettGen2Commands,
    LeggettGen2Controller,
)
from custom_components.adjustable_bed.beds.leggett_okin import (
    LeggettOkinCommands,
    LeggettOkinController,
)
from custom_components.adjustable_bed.const import (
    BED_TYPE_LEGGETT_GEN2,
    BED_TYPE_LEGGETT_PLATT,
    CONF_BED_TYPE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_HAS_MASSAGE,
    CONF_MOTOR_COUNT,
    CONF_PREFERRED_ADAPTER,
    CONF_PROTOCOL_VARIANT,
    DOMAIN,
    LEGGETT_GEN2_WRITE_CHAR_UUID,
    LEGGETT_VARIANT_GEN2,
    LEGGETT_VARIANT_MLRM,
    LEGGETT_VARIANT_OKIN,
    VARIANT_AUTO,
)
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator


@pytest.fixture
def mock_leggett_gen2_config_entry_data() -> dict:
    """Return mock config entry data for Leggett & Platt Gen2 bed."""
    return {
        CONF_ADDRESS: "AA:BB:CC:DD:EE:FF",
        CONF_NAME: "Leggett Gen2 Test Bed",
        CONF_BED_TYPE: BED_TYPE_LEGGETT_PLATT,
        CONF_MOTOR_COUNT: 2,
        CONF_HAS_MASSAGE: True,
        CONF_DISABLE_ANGLE_SENSING: True,
        CONF_PREFERRED_ADAPTER: "auto",
    }


@pytest.fixture
def mock_leggett_gen2_config_entry(
    hass: HomeAssistant, mock_leggett_gen2_config_entry_data: dict
) -> MockConfigEntry:
    """Return a mock config entry for Leggett & Platt Gen2 bed."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Leggett Gen2 Test Bed",
        data=mock_leggett_gen2_config_entry_data,
        unique_id="AA:BB:CC:DD:EE:FF",
        entry_id="leggett_gen2_test_entry",
    )
    entry.add_to_hass(hass)
    return entry


class TestLeggettGen2Controller:
    """Test Leggett & Platt Gen2 controller."""

    async def test_control_characteristic_uuid(
        self,
        hass: HomeAssistant,
        mock_leggett_gen2_config_entry,
        mock_coordinator_connected,
    ):
        """Test controller reports correct characteristic UUID."""
        coordinator = AdjustableBedCoordinator(hass, mock_leggett_gen2_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.control_characteristic_uuid == LEGGETT_GEN2_WRITE_CHAR_UUID

    async def test_write_command(
        self,
        hass: HomeAssistant,
        mock_leggett_gen2_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test writing a command to the bed."""
        coordinator = AdjustableBedCoordinator(hass, mock_leggett_gen2_config_entry)
        await coordinator.async_connect()

        command = LeggettGen2Commands.STOP
        await coordinator.controller.write_command(command)

        mock_bleak_client.write_gatt_char.assert_called_with(
            LEGGETT_GEN2_WRITE_CHAR_UUID, command, response=True
        )


class TestLeggettOkinController:
    """Test Leggett & Platt Okin controller variant."""

    async def test_build_okin_command(
        self,
        hass: HomeAssistant,
        mock_leggett_gen2_config_entry,
        mock_coordinator_connected,
    ):
        """Test Okin variant command format."""
        coordinator = AdjustableBedCoordinator(hass, mock_leggett_gen2_config_entry)
        await coordinator.async_connect()

        # Create an Okin controller directly (using the new protocol-based class)
        controller = LeggettOkinController(coordinator)

        # Okin format: [0x04, 0x02, ...int_bytes]
        command = controller._build_command(LeggettOkinCommands.MOTOR_HEAD_UP)

        assert len(command) == 6
        assert command[:2] == bytes([0x04, 0x02])
        # Command 0x1 in big-endian
        assert command[2:] == bytes([0x00, 0x00, 0x00, 0x01])


class TestLeggettGen2CommandFormat:
    """Verify Gen2 motor command bytes match the LP Control app (issue #385)."""

    def test_motor_command_bytes(self):
        """Format is ``M {down}:{up}:{stop}`` with the code in exactly one field."""
        c = LeggettGen2Commands
        assert c.MOTOR_HEAD_UP == b"M :0:"
        assert c.MOTOR_HEAD_DOWN == b"M 0::"
        assert c.MOTOR_HEAD_STOP == b"M ::0"
        assert c.MOTOR_FEET_UP == b"M :1:"
        assert c.MOTOR_FEET_DOWN == b"M 1::"
        assert c.MOTOR_FEET_STOP == b"M ::1"
        assert c.MOTOR_PILLOW_UP == b"M :2:"
        assert c.MOTOR_LUMBAR_UP == b"M :3:"
        assert c.MOTOR_STOP_ALL == b"STOP"

    def test_motor_move_builder(self):
        """The builder lays fields out as down:up:stop."""
        assert LeggettGen2Commands.motor_move(up="0") == b"M :0:"
        assert LeggettGen2Commands.motor_move(down="1") == b"M 1::"
        assert LeggettGen2Commands.motor_move(stop="2") == b"M ::2"

    def test_massage_command_bytes(self):
        """Massage uses VII (relative) / MVI (absolute) / MMODE / WVE TOGGLE."""
        c = LeggettGen2Commands
        assert c.MASSAGE_HEAD_UP == b"VII :0"
        assert c.MASSAGE_HEAD_DOWN == b"VII 0::"
        assert c.MASSAGE_FOOT_UP == b"VII :1"
        assert c.MASSAGE_FOOT_DOWN == b"VII 1::"
        assert c.MASSAGE_ALL_UP == b"VII :0123"
        assert c.MASSAGE_ALL_DOWN == b"VII 0123::"
        assert c.WAVE_TOGGLE == b"WVE TOGGLE"
        assert c.massage_set(0, 0) == b"MVI 0:0"  # off, head channel
        assert c.massage_set(1, 3) == b"MVI 1:3"  # foot channel, high
        # Mode codes verified from Gen2CommandFormatter: wave=0, pulse=1, always-on=2.
        assert c.massage_mode(c.MODE_WAVE) == b"MMODE 0:0"
        assert c.massage_mode(c.MODE_PULSE) == b"MMODE 0:1"
        assert c.massage_mode(c.MODE_ALWAYS_ON) == b"MMODE 0:2"


class TestLeggettGen2Connection:
    """Gen2 / LP Comfort Connect connection behaviour."""

    @staticmethod
    def _coordinator(hass: HomeAssistant, bed_type: str, variant: str):
        entry = MockConfigEntry(
            domain=DOMAIN,
            data={
                CONF_ADDRESS: "AA:BB:CC:DD:EE:FF",
                CONF_NAME: "LP Bed",
                CONF_BED_TYPE: bed_type,
                CONF_PROTOCOL_VARIANT: variant,
            },
            unique_id="AA:BB:CC:DD:EE:FF",
        )
        entry.add_to_hass(hass)
        return AdjustableBedCoordinator(hass, entry)

    @pytest.mark.parametrize(
        ("bed_type", "variant", "expected"),
        [
            (BED_TYPE_LEGGETT_GEN2, VARIANT_AUTO, True),
            (BED_TYPE_LEGGETT_PLATT, LEGGETT_VARIANT_GEN2, True),
            # Before a controller is resolved, only auto/gen2 leggett_platt is
            # assumed persistent; okin and mlrm reconnect normally.
            (BED_TYPE_LEGGETT_PLATT, VARIANT_AUTO, True),
            (BED_TYPE_LEGGETT_PLATT, LEGGETT_VARIANT_MLRM, False),
            (BED_TYPE_LEGGETT_PLATT, LEGGETT_VARIANT_OKIN, False),
        ],
    )
    async def test_persistent_connection_fallback(
        self, hass: HomeAssistant, bed_type: str, variant: str, expected: bool
    ):
        """Pre-connect (no controller, no cache): fall back to the bed-type heuristic."""
        coordinator = self._coordinator(hass, bed_type, variant)
        assert coordinator._controller is None
        assert coordinator._persistent_connection_resolved is None
        assert coordinator._uses_persistent_connection() is expected

    async def test_resolved_controller_is_authoritative(self, hass: HomeAssistant):
        """Once resolved, the controller decides — a leggett_platt+auto that
        resolved to WiLinke/MlRM is NOT persistent; one that resolved to Gen2 is
        (issue #385 review, both directions)."""
        from custom_components.adjustable_bed.beds.leggett_gen2 import LeggettGen2Controller
        from custom_components.adjustable_bed.beds.leggett_wilinke import (
            LeggettWilinkeController,
        )

        coordinator = self._coordinator(hass, BED_TYPE_LEGGETT_PLATT, VARIANT_AUTO)

        coordinator._controller = LeggettWilinkeController(coordinator)
        assert coordinator._uses_persistent_connection() is False

        coordinator._controller = LeggettGen2Controller(coordinator)
        assert coordinator._uses_persistent_connection() is True

    async def test_persistence_cached_across_disconnect(self, hass: HomeAssistant):
        """_on_disconnect clears the controller before the reconnect decision, so
        the cached resolved value must drive it — an MlRM bed resolved via auto
        must stay non-persistent (and thus reconnect) after the drop (issue #385
        review)."""
        coordinator = self._coordinator(hass, BED_TYPE_LEGGETT_PLATT, VARIANT_AUTO)

        # Resolved to a non-persistent controller, then cleared on disconnect.
        coordinator._persistent_connection_resolved = False
        coordinator._controller = None
        assert coordinator._uses_persistent_connection() is False

        # Resolved to a persistent (Gen2) controller, then cleared.
        coordinator._persistent_connection_resolved = True
        assert coordinator._uses_persistent_connection() is True


class TestLeggettGen2Capabilities:
    """Gen2 capabilities are gated per model by the bundled product profile."""

    @staticmethod
    def _controller(hass, entry, product_id: int) -> LeggettGen2Controller:
        # Payload encodes the productId: "XP" + little-endian bytes -> reversed
        # first 4 hex -> base16. For ids < 256 that is just byte[2].
        payload = bytes([0x58, 0x50]) + product_id.to_bytes(4, "little")
        coordinator = AdjustableBedCoordinator(hass, entry)
        return LeggettGen2Controller(coordinator, manufacturer_data={0x092D: payload})

    async def test_rgb_bed_with_pillow_lumbar(
        self, hass: HomeAssistant, mock_leggett_gen2_config_entry
    ):
        c = self._controller(hass, mock_leggett_gen2_config_entry, 5)
        assert c.supports_lights and c.supports_light_color_control
        assert c.has_pillow_support and c.has_lumbar_support
        assert c.memory_slot_count == 3  # not the old hardcoded 4

    async def test_toggle_light_bed_without_pillow_lumbar(
        self, hass: HomeAssistant, mock_leggett_gen2_config_entry
    ):
        c = self._controller(hass, mock_leggett_gen2_config_entry, 8)
        assert c.supports_lights and not c.supports_light_color_control
        assert not c.has_pillow_support and not c.has_lumbar_support

    async def test_bed_without_light(
        self, hass: HomeAssistant, mock_leggett_gen2_config_entry
    ):
        c = self._controller(hass, mock_leggett_gen2_config_entry, 10011)
        assert not c.supports_lights and not c.supports_light_color_control
        assert c.default_light_rgb_color is None

    async def test_unknown_product_falls_back_to_full_featured(
        self, hass: HomeAssistant, mock_leggett_gen2_config_entry
    ):
        c = self._controller(hass, mock_leggett_gen2_config_entry, 999999)
        assert c.supports_light_color_control and c.has_pillow_support

    async def test_no_light_no_massage_profile_suppresses_helpers(
        self, hass: HomeAssistant, mock_leggett_gen2_config_entry
    ):
        # Product 10011: head-only, no foot, no light, no massage.
        c = self._controller(hass, mock_leggett_gen2_config_entry, 10011)
        # Light + massage capability helpers are gated off (no phantom entities).
        assert not c.supports_light_toggle_control
        assert not c.supports_under_bed_lights
        assert not c.supports_massage_off_control
        assert not c.supports_massage_toggle_control
        # Motor specs expose only present primary actuators (head, not foot).
        keys = {spec.key for spec in c.motor_control_specs}
        assert "back" in keys  # head present
        assert "legs" not in keys  # no foot

    async def test_full_profile_keeps_helpers(
        self, hass: HomeAssistant, mock_leggett_gen2_config_entry
    ):
        c = self._controller(hass, mock_leggett_gen2_config_entry, 5)
        assert c.supports_light_toggle_control and c.supports_massage_off_control
        keys = {spec.key for spec in c.motor_control_specs}
        assert {"back", "legs"} <= keys

    async def test_stale_motor_keys_for_absent_actuators(
        self, hass: HomeAssistant, mock_leggett_gen2_config_entry
    ):
        # Product 10011: head only -> legs/pillow/lumbar covers should be removable.
        c = self._controller(hass, mock_leggett_gen2_config_entry, 10011)
        assert c.stale_motor_entity_keys == frozenset({"legs", "pillow", "lumbar"})
        # Full profile (5): nothing stale.
        assert self._controller(
            hass, mock_leggett_gen2_config_entry, 5
        ).stale_motor_entity_keys == frozenset()

    async def test_set_light_color_updates_cache(
        self,
        hass: HomeAssistant,
        mock_leggett_gen2_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        coordinator = AdjustableBedCoordinator(hass, mock_leggett_gen2_config_entry)
        await coordinator.async_connect()
        controller = coordinator.controller

        # RGBSET is the RGB turn-on path -> cache must flip on, so a later off works.
        await controller.set_light_color((255, 0, 0))
        assert controller._light_on is True
        await controller.set_light_color((0, 0, 0))
        assert controller._light_on is False

    async def test_massage_toggle_gated_on_wave(
        self, hass: HomeAssistant, mock_leggett_gen2_config_entry
    ):
        # Product 10012: massage but NO wave -> no massage toggle (WVE TOGGLE),
        # but intensity step + mode step are still available.
        c = self._controller(hass, mock_leggett_gen2_config_entry, 10012)
        assert c.supports_massage_off_control
        assert c.supports_massage_intensity_step_control
        assert c.supports_massage_mode_step_control
        assert not c.supports_massage_toggle_control
        # Product 5 has wave -> toggle available.
        assert self._controller(
            hass, mock_leggett_gen2_config_entry, 5
        ).supports_massage_toggle_control

    async def test_massage_intensity_all_and_mode_step(
        self,
        hass: HomeAssistant,
        mock_leggett_gen2_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        coordinator = AdjustableBedCoordinator(hass, mock_leggett_gen2_config_entry)
        await coordinator.async_connect()
        controller = coordinator.controller

        await controller.massage_intensity_up()
        assert mock_bleak_client.write_gatt_char.call_args[0][1] == b"VII :0123"
        await controller.massage_intensity_down()
        assert mock_bleak_client.write_gatt_char.call_args[0][1] == b"VII 0123::"

        # Mode step cycles wave -> pulse -> always-on -> wave (fallback profile has wave).
        sent = []
        for _ in range(4):
            await controller.massage_mode_step()
            sent.append(mock_bleak_client.write_gatt_char.call_args[0][1])
        assert sent == [b"MMODE 0:1", b"MMODE 0:2", b"MMODE 0:0", b"MMODE 0:1"]

    async def test_lights_on_off_idempotent_and_optimistic(
        self,
        hass: HomeAssistant,
        mock_leggett_gen2_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        coordinator = AdjustableBedCoordinator(hass, mock_leggett_gen2_config_entry)
        await coordinator.async_connect()
        controller = coordinator.controller

        # Unknown state -> on toggles and caches True; repeat is a no-op.
        await controller.lights_on()
        assert controller._light_on is True
        mock_bleak_client.write_gatt_char.reset_mock()
        await controller.lights_on()
        mock_bleak_client.write_gatt_char.assert_not_called()

        # Off toggles once and caches False; repeat is a no-op (no inversion).
        await controller.lights_off()
        assert controller._light_on is False
        mock_bleak_client.write_gatt_char.reset_mock()
        await controller.lights_off()
        mock_bleak_client.write_gatt_char.assert_not_called()


class TestLeggettMovement:
    """Test Leggett & Platt movement commands."""

    async def test_move_head_up_gen2_sends_command(
        self,
        hass: HomeAssistant,
        mock_leggett_gen2_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test move head up on Gen2 sends motor command."""
        coordinator = AdjustableBedCoordinator(hass, mock_leggett_gen2_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.move_head_up()

        # _move_with_stop sends the head-up command then the per-actuator stop
        assert mock_bleak_client.write_gatt_char.called
        last_call = mock_bleak_client.write_gatt_char.call_args
        assert last_call[0][1] == LeggettGen2Commands.MOTOR_HEAD_STOP
        # The move command itself (head up = "M :0:") was sent before the stop
        sent = [c[0][1] for c in mock_bleak_client.write_gatt_char.call_args_list]
        assert LeggettGen2Commands.MOTOR_HEAD_UP in sent

    async def test_move_head_stop_gen2(
        self,
        hass: HomeAssistant,
        mock_leggett_gen2_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test move head stop sends the per-actuator head stop command."""
        coordinator = AdjustableBedCoordinator(hass, mock_leggett_gen2_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.move_head_stop()

        mock_bleak_client.write_gatt_char.assert_called_with(
            LEGGETT_GEN2_WRITE_CHAR_UUID, LeggettGen2Commands.MOTOR_HEAD_STOP, response=True
        )

    async def test_stop_all_gen2(
        self,
        hass: HomeAssistant,
        mock_leggett_gen2_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test stop all sends MOTOR_STOP_ALL command."""
        coordinator = AdjustableBedCoordinator(hass, mock_leggett_gen2_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.stop_all()

        mock_bleak_client.write_gatt_char.assert_called_with(
            LEGGETT_GEN2_WRITE_CHAR_UUID, LeggettGen2Commands.MOTOR_STOP_ALL, response=True
        )


class TestLeggettPresets:
    """Test Leggett & Platt preset commands."""

    async def test_preset_flat_gen2(
        self,
        hass: HomeAssistant,
        mock_leggett_gen2_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test preset flat command on Gen2."""
        coordinator = AdjustableBedCoordinator(hass, mock_leggett_gen2_config_entry)
        await coordinator.async_connect()
        mock_bleak_client.write_gatt_char.reset_mock()  # ignore the GET STATE on connect

        await coordinator.controller.preset_flat()

        first_call = mock_bleak_client.write_gatt_char.call_args_list[0]
        assert first_call[0][1] == LeggettGen2Commands.PRESET_FLAT

    async def test_preset_anti_snore_gen2(
        self,
        hass: HomeAssistant,
        mock_leggett_gen2_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test preset anti-snore command on Gen2."""
        coordinator = AdjustableBedCoordinator(hass, mock_leggett_gen2_config_entry)
        await coordinator.async_connect()
        mock_bleak_client.write_gatt_char.reset_mock()  # ignore the GET STATE on connect

        await coordinator.controller.preset_anti_snore()

        first_call = mock_bleak_client.write_gatt_char.call_args_list[0]
        assert first_call[0][1] == LeggettGen2Commands.PRESET_ANTI_SNORE

    @pytest.mark.parametrize(
        "memory_num,expected_command",
        [
            (1, LeggettGen2Commands.PRESET_UNWIND),
            (2, LeggettGen2Commands.PRESET_SLEEP),
            (3, LeggettGen2Commands.PRESET_WAKE_UP),
            (4, LeggettGen2Commands.PRESET_RELAX),
        ],
    )
    async def test_preset_memory_gen2(
        self,
        hass: HomeAssistant,
        mock_leggett_gen2_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
        memory_num: int,
        expected_command: bytes,
    ):
        """Test preset memory commands on Gen2."""
        coordinator = AdjustableBedCoordinator(hass, mock_leggett_gen2_config_entry)
        await coordinator.async_connect()
        mock_bleak_client.write_gatt_char.reset_mock()  # ignore the GET STATE on connect

        await coordinator.controller.preset_memory(memory_num)

        first_call = mock_bleak_client.write_gatt_char.call_args_list[0]
        assert first_call[0][1] == expected_command

    @pytest.mark.parametrize(
        "memory_num,expected_command",
        [
            (1, LeggettGen2Commands.PROGRAM_UNWIND),
            (2, LeggettGen2Commands.PROGRAM_SLEEP),
            (3, LeggettGen2Commands.PROGRAM_WAKE_UP),
            (4, LeggettGen2Commands.PROGRAM_RELAX),
        ],
    )
    async def test_program_memory_gen2(
        self,
        hass: HomeAssistant,
        mock_leggett_gen2_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
        memory_num: int,
        expected_command: bytes,
    ):
        """Test program memory commands on Gen2."""
        coordinator = AdjustableBedCoordinator(hass, mock_leggett_gen2_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.program_memory(memory_num)

        mock_bleak_client.write_gatt_char.assert_called_with(
            LEGGETT_GEN2_WRITE_CHAR_UUID, expected_command, response=True
        )


class TestLeggettLights:
    """Test Leggett & Platt light commands."""

    async def test_lights_toggle_gen2(
        self,
        hass: HomeAssistant,
        mock_leggett_gen2_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test lights toggle on Gen2 sends the UBL TOGGLE command."""
        coordinator = AdjustableBedCoordinator(hass, mock_leggett_gen2_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.lights_toggle()

        mock_bleak_client.write_gatt_char.assert_called_with(
            LEGGETT_GEN2_WRITE_CHAR_UUID, LeggettGen2Commands.LIGHT_TOGGLE, response=True
        )
        assert LeggettGen2Commands.LIGHT_TOGGLE == b"UBL TOGGLE"

    async def test_lights_on_gen2(
        self,
        hass: HomeAssistant,
        mock_leggett_gen2_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Lights on (state unknown) sends the toggle; idempotent once state known."""
        coordinator = AdjustableBedCoordinator(hass, mock_leggett_gen2_config_entry)
        await coordinator.async_connect()
        controller = coordinator.controller

        # State unknown -> toggle to turn on.
        await controller.lights_on()
        mock_bleak_client.write_gatt_char.assert_called_with(
            LEGGETT_GEN2_WRITE_CHAR_UUID, LeggettGen2Commands.LIGHT_TOGGLE, response=True
        )

        # Once the bed reports the light is on, lights_on is a no-op (no inversion).
        controller._light_on = True
        mock_bleak_client.write_gatt_char.reset_mock()
        await controller.lights_on()
        mock_bleak_client.write_gatt_char.assert_not_called()

    async def test_lights_off_gen2(
        self,
        hass: HomeAssistant,
        mock_leggett_gen2_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test lights off Gen2 uses the confirmed toggle (UBL TOGGLE)."""
        coordinator = AdjustableBedCoordinator(hass, mock_leggett_gen2_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.lights_off()

        mock_bleak_client.write_gatt_char.assert_called_with(
            LEGGETT_GEN2_WRITE_CHAR_UUID, LeggettGen2Commands.LIGHT_TOGGLE, response=True
        )


class TestLeggettGen2RgbLights:
    """Test Leggett & Platt Gen2 RGB light controls."""

    async def test_supports_light_color_control(
        self,
        hass: HomeAssistant,
        mock_leggett_gen2_config_entry,
        mock_coordinator_connected,
    ):
        """Test Gen2 controller reports RGB light color support."""
        coordinator = AdjustableBedCoordinator(hass, mock_leggett_gen2_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.supports_light_color_control is True

    async def test_supports_explicit_light_on_control(
        self,
        hass: HomeAssistant,
        mock_leggett_gen2_config_entry,
        mock_coordinator_connected,
    ):
        """Gen2 has no separate explicit on command (only UBL TOGGLE); setting a
        colour turns RGB lights on, so explicit-on is reported False."""
        coordinator = AdjustableBedCoordinator(hass, mock_leggett_gen2_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.supports_explicit_light_on_control is False

    async def test_default_light_rgb_color(
        self,
        hass: HomeAssistant,
        mock_leggett_gen2_config_entry,
        mock_coordinator_connected,
    ):
        """Test Gen2 controller returns white as default RGB color."""
        coordinator = AdjustableBedCoordinator(hass, mock_leggett_gen2_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.default_light_rgb_color == (255, 255, 255)

    async def test_set_light_color(
        self,
        hass: HomeAssistant,
        mock_leggett_gen2_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test set_light_color sends correct RGBSET ASCII command."""
        coordinator = AdjustableBedCoordinator(hass, mock_leggett_gen2_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.set_light_color((255, 0, 128))

        expected = LeggettGen2Commands.rgb_set(255, 0, 128, 255)
        assert expected == b"RGBSET 0:FF0080FF"
        mock_bleak_client.write_gatt_char.assert_called_with(
            LEGGETT_GEN2_WRITE_CHAR_UUID, expected, response=True
        )

    async def test_set_light_color_red(
        self,
        hass: HomeAssistant,
        mock_leggett_gen2_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test set_light_color with pure red produces correct hex."""
        coordinator = AdjustableBedCoordinator(hass, mock_leggett_gen2_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.set_light_color((255, 0, 0))

        expected = b"RGBSET 0:FF0000FF"
        mock_bleak_client.write_gatt_char.assert_called_with(
            LEGGETT_GEN2_WRITE_CHAR_UUID, expected, response=True
        )

    async def test_set_light_color_green(
        self,
        hass: HomeAssistant,
        mock_leggett_gen2_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test set_light_color with pure green produces correct hex."""
        coordinator = AdjustableBedCoordinator(hass, mock_leggett_gen2_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.set_light_color((0, 255, 0))

        expected = b"RGBSET 0:00FF00FF"
        mock_bleak_client.write_gatt_char.assert_called_with(
            LEGGETT_GEN2_WRITE_CHAR_UUID, expected, response=True
        )


class TestLeggettMassage:
    """Test Leggett & Platt massage commands."""

    async def test_massage_off_gen2(
        self,
        hass: HomeAssistant,
        mock_leggett_gen2_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test massage off on Gen2."""
        coordinator = AdjustableBedCoordinator(hass, mock_leggett_gen2_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.massage_off()

        calls = mock_bleak_client.write_gatt_char.call_args_list
        # Should send head(0) and foot(0)
        assert len(calls) >= 2

    async def test_massage_head_up_gen2(
        self,
        hass: HomeAssistant,
        mock_leggett_gen2_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Head massage up on Gen2 sends the relative increase command (VII :0)."""
        coordinator = AdjustableBedCoordinator(hass, mock_leggett_gen2_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.massage_head_up()

        mock_bleak_client.write_gatt_char.assert_called_with(
            LEGGETT_GEN2_WRITE_CHAR_UUID, LeggettGen2Commands.MASSAGE_HEAD_UP, response=True
        )
        assert LeggettGen2Commands.MASSAGE_HEAD_UP == b"VII :0"

    async def test_massage_toggle_gen2(
        self,
        hass: HomeAssistant,
        mock_leggett_gen2_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Massage toggle on Gen2 sends the wave toggle (WVE TOGGLE)."""
        coordinator = AdjustableBedCoordinator(hass, mock_leggett_gen2_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.massage_toggle()

        mock_bleak_client.write_gatt_char.assert_called_with(
            LEGGETT_GEN2_WRITE_CHAR_UUID, LeggettGen2Commands.WAVE_TOGGLE, response=True
        )
        assert LeggettGen2Commands.WAVE_TOGGLE == b"WVE TOGGLE"


class TestLeggettPositionNotifications:
    """Test Leggett & Platt position notification handling."""

    async def test_start_notify_subscribes_to_state_char(
        self,
        hass: HomeAssistant,
        mock_leggett_gen2_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Gen2 subscribes to the 45e25103 STATE characteristic for light state."""
        from custom_components.adjustable_bed.const import LEGGETT_GEN2_READ_CHAR_UUID

        coordinator = AdjustableBedCoordinator(hass, mock_leggett_gen2_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.start_notify(None)

        chars = [c.args[0] for c in mock_bleak_client.start_notify.call_args_list]
        assert LEGGETT_GEN2_READ_CHAR_UUID in chars
        assert coordinator.controller._notify_started is True

    async def test_light_state_notification_parses_on_off(
        self,
        hass: HomeAssistant,
        mock_leggett_gen2_config_entry,
        mock_coordinator_connected,
    ):
        """STATE byte 6 = OperatingMode (0x01 on / 0x04 off); 7-9 = RGB."""
        coordinator = AdjustableBedCoordinator(hass, mock_leggett_gen2_config_entry)
        await coordinator.async_connect()
        controller = coordinator.controller

        # Constant-colour (on), red: bytes [..6 header.., 0x01, FF, 00, 00, FF, ...]
        on_frame = bytearray([0x6E, 0x20, 0x00, 0x04, 0x01, 0x03, 0x01, 0xFF, 0x00, 0x00, 0xFF])
        controller._handle_state_notification(None, on_frame)
        assert controller._light_on is True
        assert controller._light_rgb == (0xFF, 0x00, 0x00)
        assert coordinator.controller_state.get("under_bed_lights_on") is True

        # Off frame (byte 6 = 0x04).
        off_frame = bytearray([0x6E, 0x20, 0x00, 0x04, 0x01, 0x03, 0x04, 0x00, 0x00, 0x00, 0x00])
        controller._handle_state_notification(None, off_frame)
        assert controller._light_on is False
        assert coordinator.controller_state.get("under_bed_lights_on") is False

        # A non-light frame (byte 6 outside {0x01,0x04}) is ignored.
        controller._handle_state_notification(
            None, bytearray([0] * 6 + [0x09] + [0] * 5)
        )
        assert controller._light_on is False  # unchanged
