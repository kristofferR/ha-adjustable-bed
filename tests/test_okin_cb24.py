"""Tests for Okin CB24 controller behavior."""

from __future__ import annotations

from unittest.mock import ANY, AsyncMock, MagicMock, call

from custom_components.adjustable_bed.beds.okin_cb24 import (
    OkinCB24Commands,
    OkinCB24Controller,
)


class TestOkinCB24Controller:
    """Test OkinCB24Controller."""

    def test_protocol_command_bytes_match_cb24_format(self) -> None:
        """CB24 packet bytes should match OEM app command format."""
        coordinator_default = MagicMock()
        coordinator_default.address = "AA:BB:CC:DD:EE:FF"
        controller_default = OkinCB24Controller(coordinator_default)
        assert controller_default._build_command(OkinCB24Commands.PRESET_FLAT) == bytes(
            [0x05, 0x02, 0x08, 0x00, 0x00, 0x00, 0x00]
        )

        coordinator_bed_a = MagicMock()
        coordinator_bed_a.address = "AA:BB:CC:DD:EE:FF"
        controller_bed_a = OkinCB24Controller(coordinator_bed_a, bed_selection=0xAA)
        assert controller_bed_a._build_command(OkinCB24Commands.MASSAGE_ALL_TOGGLE) == bytes(
            [0x05, 0x02, 0x00, 0x00, 0x01, 0x00, 0xAA]
        )

    def test_preset_burst_timing_constants(self) -> None:
        """Preset burst timing should match CB24 hold-style cadence."""
        assert OkinCB24Controller.PRESET_REPEAT_COUNT == 83
        assert OkinCB24Controller.PRESET_REPEAT_DELAY_MS == 300

    async def test_send_preset_uses_burst_timing_and_stop_cleanup(self) -> None:
        """Preset commands should use hold burst timing and send STOP cleanup."""
        coordinator = MagicMock()
        coordinator.address = "AA:BB:CC:DD:EE:FF"
        controller = OkinCB24Controller(coordinator)
        controller.write_command = AsyncMock()

        await controller._send_preset(OkinCB24Commands.PRESET_ZERO_G)

        assert controller.write_command.await_count == 2
        controller.write_command.assert_has_awaits(
            [
                call(
                    controller._build_command(OkinCB24Commands.PRESET_ZERO_G),
                    repeat_count=controller.PRESET_REPEAT_COUNT,
                    repeat_delay_ms=controller.PRESET_REPEAT_DELAY_MS,
                ),
                call(
                    controller._build_command(0),
                    cancel_event=ANY,
                ),
            ]
        )
