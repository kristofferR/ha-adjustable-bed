"""Leggett & Platt MlRM beds: the ``LEGGETT_WILINKE`` profile over the Richmat 6E codec.

These beds use Richmat WiLinke hardware with Leggett & Platt codes. Unlike the
Richmat remotes they have discrete massage up/down codes per zone, direct
massage timers, and presets held for 100 writes 300 ms apart before STOP.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from ..const import LEGGETT_RICHMAT_CHAR_UUID
from ..profiles.richmat import LEGGETT_WILINKE, Button
from .richmat import RichmatProfileController

if TYPE_CHECKING:
    from ..coordinator import AdjustableBedCoordinator

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
        # Optimistic timer state (no BLE feedback): 0 = off, 10/20/30 = active.
        self._timer_mode: int = 0

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
        self._timer_mode = 0

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
            self._timer_mode = minutes
        else:
            _LOGGER.warning("Invalid timer duration: %d (valid: 0, 10, 20, 30)", minutes)

    def get_massage_state(self) -> dict[str, Any]:
        """Optimistic state from this controller's own commands; the remote can desync it."""
        return {"timer_mode": str(self._timer_mode) if self._timer_mode > 0 else None}
