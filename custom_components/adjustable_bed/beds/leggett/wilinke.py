"""Leggett & Platt MlRM beds: the ``LEGGETT_WILINKE`` profile over the Richmat 6E codec.

These beds use Richmat WiLinke hardware with Leggett & Platt codes. Unlike the
Richmat remotes they have discrete massage up/down codes per zone, direct
massage timers, and presets held for 100 writes 300 ms apart before STOP.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from bleak.exc import BleakError

from ...const import LEGGETT_RICHMAT_CHAR_UUID
from ...profiles.richmat import LEGGETT_WILINKE, Button
from ...state_keys import MASSAGE_TIMER_MINUTES
from ..richmat.controller import RichmatProfileController

if TYPE_CHECKING:
    from ...coordinator import AdjustableBedCoordinator

_LOGGER = logging.getLogger(__name__)
_TIMERS: dict[int, Button] = {
    10: "massage_timer_10",
    20: "massage_timer_20",
    30: "massage_timer_30",
}


class LeggettWilinkeController(RichmatProfileController):
    """Controller for Leggett & Platt beds using the WiLinke protocol."""

    def __init__(self, coordinator: AdjustableBedCoordinator, char_uuid: str | None = None) -> None:
        super().__init__(
            coordinator, LEGGETT_WILINKE, char_uuid=char_uuid or LEGGETT_RICHMAT_CHAR_UUID
        )
        # The timer is optimistic (no BLE feedback); the remote can desync it.
        self.forward_controller_state_update(MASSAGE_TIMER_MINUTES, 0)

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 100,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        """The pre-v5 L&P write loop: cancel checked before the lock, not inside it."""
        if self.client is None or not self.client.is_connected:
            _LOGGER.error("Cannot write command: BLE client not connected")
            raise ConnectionError("Not connected to bed")
        effective_cancel = cancel_event or self._coordinator.cancel_command
        self._record_command_trace(
            self._char_uuid,
            command,
            response=True,
            repeat_count=repeat_count,
            repeat_delay_ms=repeat_delay_ms,
        )
        for i in range(repeat_count):
            if effective_cancel is not None and effective_cancel.is_set():
                _LOGGER.info("Command cancelled after %d/%d writes", i, repeat_count)
                return
            try:
                async with self._ble_lock:
                    await self.client.write_gatt_char(self._char_uuid, command, response=True)
            except BleakError as err:
                _LOGGER.exception("Failed to write command")
                if "not found" in str(err).lower() or "invalid" in str(err).lower():
                    _LOGGER.warning(
                        "Characteristic %s may not exist on this device.", self._char_uuid
                    )
                    self.log_discovered_services(level=logging.INFO)
                raise
            if i < repeat_count - 1:
                await asyncio.sleep(repeat_delay_ms / 1000)

    @property
    def has_discrete_motor_control(self) -> bool:
        return True

    @property
    def supports_massage_timer(self) -> bool:
        return True

    @property
    def massage_timer_options(self) -> list[int]:
        return list(_TIMERS)

    async def lights_on(self) -> None:
        """Toggle-only lights."""
        await self.lights_toggle()

    async def lights_off(self) -> None:
        await self.lights_toggle()

    async def massage_off(self) -> None:
        await self._send("massage_off")
        self.forward_controller_state_update(MASSAGE_TIMER_MINUTES, 0)

    async def massage_head_up(self) -> None:
        await self._send("massage_head_up")

    async def massage_head_down(self) -> None:
        await self._send("massage_head_down")

    async def massage_foot_up(self) -> None:
        await self._send("massage_foot_up")

    async def massage_foot_down(self) -> None:
        await self._send("massage_foot_down")

    async def massage_intensity_up(self) -> None:
        await self._send("massage_intensity_up")

    async def massage_intensity_down(self) -> None:
        await self._send("massage_intensity_down")

    async def massage_wave_toggle(self) -> None:
        await self._send("massage_wave")

    async def set_massage_timer(self, minutes: int) -> None:
        """Set the massage timer: 0 stops massage, else 10, 20 or 30 minutes."""
        if minutes == 0:
            await self.massage_off()
        elif minutes in _TIMERS:
            await self._send(_TIMERS[minutes])
            self.forward_controller_state_update(MASSAGE_TIMER_MINUTES, minutes)
        else:
            _LOGGER.warning("Invalid timer duration: %d (valid: 0, 10, 20, 30)", minutes)

