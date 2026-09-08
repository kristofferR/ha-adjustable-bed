"""Tests for Leggett & Platt bed controller."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest
from bleak.exc import BleakError
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
    parse_leggett_okin_feedback,
)
from custom_components.adjustable_bed.button import BUTTON_DESCRIPTIONS, _should_add_button
from custom_components.adjustable_bed.const import (
    BED_TYPE_LEGGETT_GEN2,
    BED_TYPE_LEGGETT_PLATT,
    BED_TYPE_OKIMAT,
    CONF_BED_TYPE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_HAS_MASSAGE,
    CONF_MOTOR_COUNT,
    CONF_PREFERRED_ADAPTER,
    CONF_PROTOCOL_VARIANT,
    DOMAIN,
    LEGGETT_GEN2_WRITE_CHAR_UUID,
    LEGGETT_OKIN_CHAR_UUID,
    LEGGETT_OKIN_NOTIFY_CHAR_UUID,
    LEGGETT_OKIN_PULSE_DEFAULTS,
    LEGGETT_OKIN_REVISION_SELECTOR_CHAR_UUID,
    LEGGETT_OKIN_SERVICE_UUID,
    LEGGETT_VARIANT_GEN2,
    LEGGETT_VARIANT_MLRM,
    LEGGETT_VARIANT_OKIN,
    OKIN_SMART_REMOTE_CSS_NOTIFY_CHAR_UUID,
    OKIN_SMART_REMOTE_CSS_WRITE_CHAR_UUID,
    VARIANT_AUTO,
    connection_gated_by_bond,
    requires_pairing,
    requires_pairing_after_service_discovery,
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
        controller = self._controller_with_characteristics()

        # Okin format: [0x04, 0x02, ...int_bytes]
        command = controller._build_command(LeggettOkinCommands.MOTOR_HEAD_UP)

        assert len(command) == 6
        assert command[:2] == bytes([0x04, 0x02])
        # Command 0x1 in big-endian
        assert command[2:] == bytes([0x00, 0x00, 0x00, 0x01])

    @staticmethod
    def _controller_with_characteristics(*uuids: str) -> LeggettOkinController:
        coordinator = MagicMock()
        if not uuids:
            uuids = (LEGGETT_OKIN_CHAR_UUID, LEGGETT_OKIN_REVISION_SELECTOR_CHAR_UUID)
        coordinator.client = SimpleNamespace(
            is_connected=True,
            services=[
                SimpleNamespace(
                    uuid=LEGGETT_OKIN_SERVICE_UUID,
                    characteristics=[SimpleNamespace(uuid=uuid) for uuid in uuids],
                )
            ],
        )
        coordinator.cancel_command = asyncio.Event()
        coordinator.address = "AA:BB:CC:DD:EE:FF"
        controller = LeggettOkinController(coordinator)
        controller._wait_hold_deadline = AsyncMock()
        return controller

    def test_revision_zero_framing_selected_when_selector_is_absent(self):
        """The write characteristic without 1721 selects the checksummed R0 frame."""
        controller = self._controller_with_characteristics(LEGGETT_OKIN_CHAR_UUID)

        assert controller._build_command(LeggettOkinCommands.MOTOR_HEAD_UP) == bytes.fromhex(
            "e5fe160000000105"
        )
        assert controller._build_command(0) == bytes.fromhex("e5fe160000000006")
        assert controller._build_command(
            LeggettOkinCommands.CONTROL_MODE_PRESS_AND_HOLD
        ) == bytes.fromhex("e5fe1608010000fd")
        assert controller.protocol_diagnostics["protocol_revision"] == 0

    def test_revision_one_framing_selected_when_selector_is_present(self):
        """Characteristic 1721 selects the established six-byte R1 frame."""
        controller = self._controller_with_characteristics(
            LEGGETT_OKIN_CHAR_UUID,
            LEGGETT_OKIN_REVISION_SELECTOR_CHAR_UUID,
        )

        assert controller._build_command(LeggettOkinCommands.MOTOR_HEAD_UP) == bytes.fromhex(
            "040200000001"
        )
        assert controller.protocol_diagnostics["protocol_revision"] == 1

    async def test_massage_off_is_not_advertised(self):
        """Massage power is a toggle, so no massage-off button should be offered.

        The capability is detected by checking whether the subclass overrides
        massage_off, so overriding it just to raise NotImplementedError created a
        button that could only ever fail (issue #368).
        """
        controller = self._controller_with_characteristics()

        assert controller.supports_massage_off_control is False

    async def test_favorites_match_the_prodigy_ce_model(self):
        """Only Favorite 1/2/3 are editable; the third wire slot is fixed Snore."""
        controller = self._controller_with_characteristics()
        controller.write_command = AsyncMock()

        assert controller.supports_preset_zero_g is False
        assert controller.memory_slot_names == (
            "Favorite 1",
            "Favorite 2",
            "Snore",
            "Favorite 3",
        )
        assert [controller.is_memory_slot_programmable(slot) for slot in range(1, 5)] == [
            True,
            True,
            False,
            True,
        ]

        await controller.program_memory(3)

        controller.write_command.assert_not_awaited()

        descriptions = {description.key: description for description in BUTTON_DESCRIPTIONS}
        assert not _should_add_button(descriptions["preset_zero_g"], controller, True)
        assert not _should_add_button(descriptions["program_memory_3"], controller, True)
        assert _should_add_button(descriptions["control_mode_press_and_hold"], controller, True)
        assert _should_add_button(descriptions["control_mode_press_and_release"], controller, True)

    async def test_massage_wave_mode_is_advertised_and_sends_release(self):
        """Expose the proven wave keycode through the shared mode-step entity."""
        controller = self._controller_with_characteristics()
        controller.write_command = AsyncMock()

        assert controller.supports_massage_mode_step_control is True

        await controller.massage_mode_step()

        wave, release = controller.write_command.await_args_list
        assert wave.args == (bytes.fromhex("040210000000"),)
        assert release.args == (bytes.fromhex("040200000000"),)
        assert release.kwargs["repeat_count"] == 4
        assert release.kwargs["cancel_event"].is_set() is False

    async def test_write_stream_is_unconfirmed_and_wall_clock_paced(self):
        """CU170 streams must not add a confirmed-write RTT to every gap."""
        controller = self._controller_with_characteristics()
        controller._write_gatt_with_retry = AsyncMock()
        cancel_event = MagicMock()

        await controller.write_command(
            b"command",
            repeat_count=10,
            repeat_delay_ms=100,
            cancel_event=cancel_event,
        )

        controller._write_gatt_with_retry.assert_awaited_once_with(
            controller.control_characteristic_uuid,
            b"command",
            repeat_count=10,
            repeat_delay_ms=100,
            cancel_event=cancel_event,
            response=False,
            wall_clock_pacing=True,
        )

    async def test_motor_surface_matches_cu170_actuators(self):
        """Expose head, lumbar, pillow and feet once each, without aliases."""
        controller = self._controller_with_characteristics()

        assert [spec.key for spec in controller.motor_control_specs] == [
            "head",
            "lumbar",
            "pillow",
            "feet",
        ]
        assert controller.stale_motor_entity_keys == frozenset(
            {"back", "legs", "tilt", "pillow", "lumbar"}
        )

    async def test_motor_streams_then_sends_four_release_frames(self):
        """Held keycodes stream at the configured cadence, then release with four zeros.

        The app's output thread writes the held keycode every 100ms and emits
        exactly four keycode-0 frames on release (MaxZeroCount = 3). There is no
        distinct stop opcode; the release frame is an ordinary frame carrying 0.
        """
        coordinator = MagicMock()
        coordinator.motor_pulse_count = 10
        coordinator.motor_pulse_delay_ms = 100
        coordinator.client = self._controller_with_characteristics().client
        controller = LeggettOkinController(coordinator)
        controller.write_command = AsyncMock()

        await controller.move_head_up()

        move_call, release_call = controller.write_command.await_args_list
        assert move_call.args == (bytes.fromhex("040200000001"),)
        assert move_call.kwargs == {
            "repeat_count": 10,
            "repeat_delay_ms": 100,
        }
        assert release_call.args == (bytes.fromhex("040200000000"),)
        assert release_call.kwargs["repeat_count"] == 4
        assert release_call.kwargs["cancel_event"].is_set() is False

    @pytest.mark.parametrize("stored_delay", [0, 1, 100, 300])
    async def test_motor_stream_uses_the_proven_pulse_delay(self, stored_delay: int):
        """Stored timing cannot flood writes or exceed the CU170 watchdog."""
        coordinator = MagicMock()
        coordinator.motor_pulse_count = 10
        coordinator.motor_pulse_delay_ms = stored_delay
        coordinator.client = self._controller_with_characteristics().client
        controller = LeggettOkinController(coordinator)
        controller.write_command = AsyncMock()

        await controller.move_head_up()

        move_call = controller.write_command.await_args_list[0]
        assert move_call.kwargs["repeat_delay_ms"] == LEGGETT_OKIN_PULSE_DEFAULTS[1]

    @pytest.mark.parametrize(
        ("slot", "keycode"),
        [(1, "00001000"), (2, "00002000"), (3, "00004000"), (4, "00008000")],
    )
    async def test_memory_recall_ladder_and_burst(self, slot: int, keycode: str):
        """Recall is a 10-frame burst of the slot bit with no terminator.

        The ladder previously started at 0x2000 and ran to 0x10000, so every slot
        recalled its neighbour and "memory 4" actually sent the store-arm keycode
        (issue #368). Recall is also autonomous: appending a release frame could
        cancel the move the box just started.
        """
        controller = self._controller_with_characteristics()
        controller.write_command = AsyncMock()

        await controller.preset_memory(slot)

        controller.write_command.assert_awaited_once()
        call = controller.write_command.await_args
        assert call.args == (bytes.fromhex(f"0402{keycode}"),)
        assert call.kwargs == {"repeat_count": 10, "repeat_delay_ms": 100}

    async def test_store_keycode_is_never_a_recall(self):
        """0x10000 arms an overwrite and must not appear in the recall ladder."""
        assert LeggettOkinCommands.MEMORY_STORE == 0x10000
        assert LeggettOkinCommands.MEMORY_STORE not in {
            LeggettOkinCommands.PRESET_MEMORY_1,
            LeggettOkinCommands.PRESET_MEMORY_2,
            LeggettOkinCommands.PRESET_MEMORY_3,
            LeggettOkinCommands.PRESET_MEMORY_4,
            LeggettOkinCommands.PRESET_ANTI_SNORE,
        }

    @pytest.mark.parametrize(
        ("method_name", "command_hex"),
        [
            ("set_control_mode_press_and_hold", "040208010000"),
            ("set_control_mode_press_and_release", "040201800000"),
        ],
    )
    async def test_control_modes_use_the_exact_special_command_lifecycle(
        self, method_name: str, command_hex: str
    ):
        """Each persistent mode is 55 attempts followed by one explicit zero."""
        controller = self._controller_with_characteristics()
        controller.write_command = AsyncMock()

        assert controller.supports_control_mode_configuration is True
        await getattr(controller, method_name)()

        command_write, release_write = controller.write_command.await_args_list
        assert command_write.args == (bytes.fromhex(command_hex),)
        assert command_write.kwargs == {
            "repeat_count": 55,
            "repeat_delay_ms": 100,
        }
        assert release_write.args == (bytes.fromhex("040200000000"),)
        assert release_write.kwargs["repeat_count"] == 1
        assert release_write.kwargs["cancel_event"].is_set() is False

    @pytest.mark.parametrize(
        ("payload", "expected"),
        [
            ("010203", None),
            ("06000600000000", None),
            ("0200061234", (4660, -1)),
            ("04000712340000", (1810, -1)),
            ("04000812340000", (305399826, -1)),
            ("060008123456fe0000", (135410774, -2)),
            ("04000912340000", (2322, -1)),
            ("04000bffff0f0f", (3855, -1)),
            ("040055aa000000", (21930, -1)),
            ("060055aa0000fe0000", (1437204480, -2)),
        ],
    )
    def test_feedback_parser_matches_frozen_apk_vectors(
        self, payload: str, expected: tuple[int, int] | None
    ):
        """Keep all ten accepted clean-room parser vectors exact."""
        assert parse_leggett_okin_feedback(bytes.fromhex(payload)) == expected

    async def test_status_channels_are_subscribed_and_settings_initialized(self):
        """Start both APK channels and perform the optional raw 01 02 setup write."""
        controller = self._controller_with_characteristics(
            LEGGETT_OKIN_CHAR_UUID,
            LEGGETT_OKIN_REVISION_SELECTOR_CHAR_UUID,
            LEGGETT_OKIN_NOTIFY_CHAR_UUID,
            OKIN_SMART_REMOTE_CSS_NOTIFY_CHAR_UUID,
            OKIN_SMART_REMOTE_CSS_WRITE_CHAR_UUID,
        )
        client = controller.client
        assert client is not None
        client.start_notify = AsyncMock()
        client.stop_notify = AsyncMock()
        client.write_gatt_char = AsyncMock()

        await controller.start_notify()

        assert client.start_notify.await_args_list == [
            call(LEGGETT_OKIN_NOTIFY_CHAR_UUID, controller._handle_notification),
            call(OKIN_SMART_REMOTE_CSS_NOTIFY_CHAR_UUID, controller._handle_notification),
        ]
        client.write_gatt_char.assert_awaited_once_with(
            OKIN_SMART_REMOTE_CSS_WRITE_CHAR_UUID,
            b"\x01\x02",
            response=True,
        )
        assert controller.protocol_diagnostics["settings_initialized"] is True

        controller._handle_notification(
            SimpleNamespace(uuid=LEGGETT_OKIN_NOTIFY_CHAR_UUID),
            bytearray.fromhex("040055aa000000"),
        )
        assert controller.protocol_diagnostics["notification_led_mask"] == "0x000055aa"
        assert controller.protocol_diagnostics["notification_status"] == -1

        await controller.stop_notify()
        assert client.stop_notify.await_count == 2

    async def test_program_memory_is_a_two_stage_hold(self):
        """Programming switches directly from store to slot, then releases."""
        controller = self._controller_with_characteristics()
        controller.write_command = AsyncMock()

        await controller.program_memory(2)

        arm, slot, slot_release = controller.write_command.await_args_list
        # ~5s of the store keycode...
        assert arm.args == (bytes.fromhex("040200010000"),)
        assert {key: value for key, value in arm.kwargs.items() if key != "deadline"} == {"repeat_count": 50, "repeat_delay_ms": 100}
        # ...directly followed by ~2s of the slot keycode, then a release.
        assert slot.args == (bytes.fromhex("040200002000"),)
        assert {key: value for key, value in slot.kwargs.items() if key != "deadline"} == {"repeat_count": 20, "repeat_delay_ms": 100}
        assert slot_release.args == (bytes.fromhex("040200000000"),)

    async def test_stop_all_propagates_write_failures(self):
        """An explicit stop must not report success when it never reached the bed.

        The release burst is this protocol's only stop, and the shared helper
        logs and swallows BleakError for cleanup callers. stop_all opts out, or
        async_stop_command would log "Stop command sent" while the bed kept
        moving.
        """
        controller = self._controller_with_characteristics()
        controller.write_command = AsyncMock(side_effect=BleakError("write failed"))

        with pytest.raises(BleakError):
            await controller.stop_all()

    async def test_cleanup_release_failures_do_not_mask_the_real_error(self):
        """A failed release burst during cleanup stays logged, not raised.

        The two writes raise distinct errors so the assertion actually proves
        which one propagated: with a shared message it would pass even if the
        cleanup failure replaced the movement failure.
        """
        controller = self._controller_with_characteristics()
        controller.write_command = AsyncMock(
            side_effect=[BleakError("movement failed"), BleakError("release failed")]
        )

        with pytest.raises(BleakError, match="movement failed"):
            await controller.move_head_up()

        assert controller.write_command.await_count == 2

    async def test_preset_flat_floors_an_unsafe_pulse_delay(self):
        """Flat is a fixed-duration hold, so the cadence has a floor.

        The setup and options flows accept any integer. 0 would divide by zero,
        a negative would collapse the hold to one frame, and a small positive
        like 1ms would expand the 30s hold into 30,000 sequential writes and
        saturate the link. All three floor to the proven cadence.
        """
        for stored_delay in (0, -50, 1):
            coordinator = MagicMock()
            coordinator.motor_pulse_count = 10
            coordinator.motor_pulse_delay_ms = stored_delay
            coordinator.client = self._controller_with_characteristics().client
            controller = LeggettOkinController(coordinator)
            controller.write_command = AsyncMock()

            await controller.preset_flat()

            flat_call = controller.write_command.await_args_list[0]
            assert flat_call.args == (bytes.fromhex("040208000000"),)
            assert flat_call.kwargs["repeat_delay_ms"] == LEGGETT_OKIN_PULSE_DEFAULTS[1]
            assert flat_call.kwargs["repeat_count"] == 300

    async def test_program_memory_cancellation_after_arm_skips_slot(self):
        """A cancelled arm never starts programming a slot, but still releases."""
        controller = self._controller_with_characteristics()

        async def cancel_after_arm(*args, **kwargs):
            if args[0] == bytes.fromhex("040200010000"):
                controller._coordinator.cancel_command.set()

        controller.write_command = AsyncMock(side_effect=cancel_after_arm)
        await controller.program_memory(2)

        sent = [item.args[0] for item in controller.write_command.await_args_list]
        assert sent == [bytes.fromhex("040200010000"), bytes.fromhex("040200000000")]
        release = controller.write_command.await_args_list[-1]
        assert not release.kwargs["cancel_event"].is_set()

    async def test_light_and_massage_taps_end_with_a_release_burst(self):
        """Lights and massage are held keycodes, so a tap must release the key.

        Sending the frame alone can leave the key asserted, and the receiver may
        then not recognise the next press of the same control.
        """
        controller = self._controller_with_characteristics()
        controller.write_command = AsyncMock()

        await controller.lights_toggle()

        press, release = controller.write_command.await_args_list
        assert press.args == (bytes.fromhex("040200020000"),)
        assert release.args == (bytes.fromhex("040200000000"),)
        assert release.kwargs["repeat_count"] == 4

        controller.write_command.reset_mock()
        await controller.massage_toggle()

        press, release = controller.write_command.await_args_list
        assert press.args == (bytes.fromhex("040200000100"),)
        assert release.args == (bytes.fromhex("040200000000"),)

    async def test_program_memory_surfaces_a_failed_final_release(self):
        """On the success path the closing release is the operation, not cleanup.

        If it fails the slot keycode may still be asserted, so the save must not
        report success.
        """
        controller = self._controller_with_characteristics()
        # arm and slot holds succeed; the final release fails.
        controller.write_command = AsyncMock(
            side_effect=[None, None, BleakError("final release failed")]
        )

        with pytest.raises(BleakError, match="final release failed"):
            await controller.program_memory(2)

    @pytest.mark.parametrize(
        ("action", "primary_frame"),
        [
            ("move_head_up", "040200000001"),
            ("preset_flat", "040208000000"),
            ("lights_toggle", "040200020000"),
            ("massage_toggle", "040200000100"),
        ],
    )
    async def test_release_failure_surfaces_after_a_successful_command(
        self, action: str, primary_frame: str
    ):
        """A lost release after a successful command must not report success.

        The release burst is this protocol's stop, so losing it can leave the
        bed moving or a keycode asserted. Every command family that ends in one
        has to surface that, not just log it.
        """
        coordinator = MagicMock()
        coordinator.motor_pulse_count = 10
        coordinator.motor_pulse_delay_ms = 100
        coordinator.client = self._controller_with_characteristics().client
        controller = LeggettOkinController(coordinator)
        controller.write_command = AsyncMock(side_effect=[None, BleakError("release failed")])

        with pytest.raises(BleakError, match="release failed"):
            await getattr(controller, action)()

        first = controller.write_command.await_args_list[0]
        assert first.args == (bytes.fromhex(primary_frame),)

    async def test_massage_timer_step_is_not_exposed(self):
        """0x200 is a constant the app never builds or writes, so it is not a command."""
        controller = self._controller_with_characteristics()

        assert not hasattr(LeggettOkinCommands, "MASSAGE_TIMER_STEP")
        assert not hasattr(controller, "massage_timer_step")


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

    @pytest.mark.parametrize(
        ("bed_type", "variant", "expected"),
        [
            (BED_TYPE_LEGGETT_GEN2, None, True),
            (BED_TYPE_LEGGETT_GEN2, VARIANT_AUTO, True),
            (BED_TYPE_LEGGETT_PLATT, LEGGETT_VARIANT_GEN2, True),
            (BED_TYPE_LEGGETT_PLATT, LEGGETT_VARIANT_OKIN, True),
            (BED_TYPE_LEGGETT_PLATT, VARIANT_AUTO, False),
            (BED_TYPE_LEGGETT_PLATT, LEGGETT_VARIANT_MLRM, False),
        ],
    )
    async def test_gen2_requires_pairing(
        self, bed_type: str, variant: str | None, expected: bool
    ):
        """LP Control calls createBond() for Gen2 after service discovery."""
        assert requires_pairing(bed_type, variant) is expected

    @pytest.mark.parametrize(
        ("bed_type", "variant", "expected"),
        [
            (BED_TYPE_LEGGETT_GEN2, None, True),
            (BED_TYPE_LEGGETT_GEN2, VARIANT_AUTO, True),
            (BED_TYPE_LEGGETT_PLATT, LEGGETT_VARIANT_GEN2, True),
            # Okin-style pairing beds accept the connection and only gate GATT
            # access, so a connect timeout there is not a pairing symptom.
            (BED_TYPE_LEGGETT_PLATT, LEGGETT_VARIANT_OKIN, False),
            (BED_TYPE_LEGGETT_PLATT, VARIANT_AUTO, False),
            (BED_TYPE_OKIMAT, None, False),
        ],
    )
    async def test_connection_gated_by_bond(
        self, bed_type: str, variant: str | None, expected: bool
    ):
        """Only Gen2 showed the bond-gated timeout signature in issue #385."""
        assert connection_gated_by_bond(bed_type, variant) is expected

    @pytest.mark.parametrize(
        ("bed_type", "variant", "expected"),
        [
            (BED_TYPE_LEGGETT_GEN2, None, True),
            (BED_TYPE_LEGGETT_PLATT, LEGGETT_VARIANT_GEN2, True),
            (BED_TYPE_LEGGETT_PLATT, LEGGETT_VARIANT_OKIN, False),
            (BED_TYPE_LEGGETT_PLATT, VARIANT_AUTO, False),
            (BED_TYPE_OKIMAT, None, False),
        ],
    )
    async def test_pairing_order(
        self, bed_type: str, variant: str | None, expected: bool
    ) -> None:
        """Only LP Gen2 connects and discovers GATT before requesting a bond."""
        assert requires_pairing_after_service_discovery(bed_type, variant) is expected

    async def test_gen2_unexpected_disconnect_schedules_auto_reconnect(
        self,
        hass: HomeAssistant,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """A persistent Gen2 bed should promptly repair an unexpected drop."""
        del mock_coordinator_connected
        entry = MockConfigEntry(
            domain=DOMAIN,
            title="LP Comfort Connect Bed",
            data={
                CONF_ADDRESS: "AA:BB:CC:DD:EE:85",
                CONF_NAME: "Smart Bed 22D8",
                CONF_BED_TYPE: BED_TYPE_LEGGETT_GEN2,
                CONF_MOTOR_COUNT: 2,
                CONF_HAS_MASSAGE: False,
                CONF_DISABLE_ANGLE_SENSING: True,
                CONF_PREFERRED_ADAPTER: "auto",
            },
            unique_id="AA:BB:CC:DD:EE:85",
            entry_id="leggett_gen2_auto_reconnect_test",
        )
        entry.add_to_hass(hass)

        coordinator = AdjustableBedCoordinator(hass, entry)
        assert coordinator._auto_reconnect_enabled() is True
        await coordinator.async_connect()
        mock_bleak_client.is_connected = False

        coordinator._on_disconnect(mock_bleak_client)

        assert coordinator._reconnect_timer is not None
        coordinator._reconnect_timer.cancel()
        coordinator._reconnect_timer = None


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
        # Gen2 never exposes the base's duplicate head/feet specs.
        assert not ({"head", "feet"} & keys)

    async def test_no_massage_profile_hides_zone_buttons(
        self, hass: HomeAssistant, mock_leggett_gen2_config_entry
    ):
        # Product 10011: no massage -> all massage helpers (incl. zone) report False.
        c = self._controller(hass, mock_leggett_gen2_config_entry, 10011)
        assert not c.supports_head_massage_intensity_step_control
        assert not c.supports_foot_massage_intensity_step_control
        assert not c.supports_massage_off_control

    async def test_manual_disconnect_strands_connection(
        self, hass: HomeAssistant, mock_leggett_gen2_config_entry
    ):
        # Keep this hidden until bonded reconnects are confirmed on hardware.
        assert self._controller(
            hass, mock_leggett_gen2_config_entry, 5
        ).manual_disconnect_strands_connection is True

    async def test_stale_motor_keys_for_absent_actuators(
        self, hass: HomeAssistant, mock_leggett_gen2_config_entry
    ):
        # Product 10011: head only -> legs/pillow/lumbar removable, plus the
        # duplicate head/feet keys Gen2 never exposes.
        c = self._controller(hass, mock_leggett_gen2_config_entry, 10011)
        assert c.stale_motor_entity_keys == frozenset(
            {"legs", "pillow", "lumbar", "head", "feet"}
        )
        # Full profile (5): only the duplicate head/feet keys are stale.
        assert self._controller(
            hass, mock_leggett_gen2_config_entry, 5
        ).stale_motor_entity_keys == frozenset({"head", "feet"})
        # No-actuator profile (10014): everything is stale.
        assert self._controller(
            hass, mock_leggett_gen2_config_entry, 10014
        ).stale_motor_entity_keys == frozenset(
            {"back", "legs", "pillow", "lumbar", "head", "feet"}
        )

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

        with patch("custom_components.adjustable_bed.beds.leggett_gen2.asyncio.sleep"):
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

        with patch("custom_components.adjustable_bed.beds.leggett_gen2.asyncio.sleep"):
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

        with patch("custom_components.adjustable_bed.beds.leggett_gen2.asyncio.sleep"):
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

        with patch("custom_components.adjustable_bed.beds.leggett_gen2.asyncio.sleep"):
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
        # RGB must be published to controller state, not just cached privately.
        assert coordinator.controller_state.get("under_bed_lights_rgb") == (0xFF, 0x00, 0x00)

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
