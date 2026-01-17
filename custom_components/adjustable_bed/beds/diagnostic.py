"""Diagnostic controller for unsupported BLE devices.

This controller provides a minimal implementation that allows users to add
unsupported BLE devices to Home Assistant for diagnostic purposes. It enables
running the run_diagnostics service to capture BLE protocol data that can
help add support for new bed models.

No motor control or position entities are created - this is purely for
diagnostic data capture.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING

from .base import BedController

if TYPE_CHECKING:
    from ..coordinator import AdjustableBedCoordinator

_LOGGER = logging.getLogger(__name__)


class DiagnosticBedController(BedController):
    """Minimal controller for diagnostic/unsupported BLE devices.

    This controller doesn't send any commands to the device - it exists solely
    to enable BLE diagnostics capture. All motor control methods raise
    NotImplementedError since there's no known protocol for the device.
    """

    def __init__(self, coordinator: AdjustableBedCoordinator) -> None:
        """Initialize the diagnostic controller."""
        super().__init__(coordinator)
        _LOGGER.info(
            "Diagnostic controller initialized for %s - no motor control available",
            coordinator.address,
        )

    @property
    def control_characteristic_uuid(self) -> str:
        """Return empty string - no control characteristic for diagnostic devices."""
        return ""

    @property
    def supports_motor_control(self) -> bool:
        """Return False - diagnostic devices have no motor control."""
        return False

    @property
    def memory_slot_count(self) -> int:
        """Return 0 - no memory presets for diagnostic devices."""
        return 0

    @property
    def supports_preset_flat(self) -> bool:
        """Return False - no presets for diagnostic devices."""
        return False

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 100,
        cancel_event=None,
    ) -> None:
        """No-op - diagnostic devices don't accept commands."""
        _LOGGER.debug("Diagnostic mode: write_command ignored (no known protocol)")

    async def start_notify(self, callback: Callable[[str, float], None]) -> None:
        """No-op - diagnostic devices don't have position notifications.

        The diagnostic service handles raw notification capture separately.
        """
        _LOGGER.debug("Diagnostic mode: start_notify skipped (no known characteristics)")

    async def stop_notify(self) -> None:
        """No-op - nothing to stop."""
        pass

    async def read_positions(self, motor_count: int = 2) -> None:
        """No-op - diagnostic devices don't have position characteristics."""
        pass

    # Motor control methods - all raise NotImplementedError

    async def move_head_up(self) -> None:
        """Not available in diagnostic mode."""
        raise NotImplementedError("Diagnostic mode: no motor control available")

    async def move_head_down(self) -> None:
        """Not available in diagnostic mode."""
        raise NotImplementedError("Diagnostic mode: no motor control available")

    async def move_head_stop(self) -> None:
        """Not available in diagnostic mode."""
        raise NotImplementedError("Diagnostic mode: no motor control available")

    async def move_back_up(self) -> None:
        """Not available in diagnostic mode."""
        raise NotImplementedError("Diagnostic mode: no motor control available")

    async def move_back_down(self) -> None:
        """Not available in diagnostic mode."""
        raise NotImplementedError("Diagnostic mode: no motor control available")

    async def move_back_stop(self) -> None:
        """Not available in diagnostic mode."""
        raise NotImplementedError("Diagnostic mode: no motor control available")

    async def move_legs_up(self) -> None:
        """Not available in diagnostic mode."""
        raise NotImplementedError("Diagnostic mode: no motor control available")

    async def move_legs_down(self) -> None:
        """Not available in diagnostic mode."""
        raise NotImplementedError("Diagnostic mode: no motor control available")

    async def move_legs_stop(self) -> None:
        """Not available in diagnostic mode."""
        raise NotImplementedError("Diagnostic mode: no motor control available")

    async def move_feet_up(self) -> None:
        """Not available in diagnostic mode."""
        raise NotImplementedError("Diagnostic mode: no motor control available")

    async def move_feet_down(self) -> None:
        """Not available in diagnostic mode."""
        raise NotImplementedError("Diagnostic mode: no motor control available")

    async def move_feet_stop(self) -> None:
        """Not available in diagnostic mode."""
        raise NotImplementedError("Diagnostic mode: no motor control available")

    async def stop_all(self) -> None:
        """No-op - nothing to stop in diagnostic mode."""
        _LOGGER.debug("Diagnostic mode: stop_all ignored (no motor control)")

    async def preset_flat(self) -> None:
        """Not available in diagnostic mode."""
        raise NotImplementedError("Diagnostic mode: no preset control available")

    async def preset_memory(self, memory_num: int) -> None:
        """Not available in diagnostic mode."""
        raise NotImplementedError("Diagnostic mode: no preset control available")

    async def program_memory(self, memory_num: int) -> None:
        """Not available in diagnostic mode."""
        raise NotImplementedError("Diagnostic mode: no preset control available")
