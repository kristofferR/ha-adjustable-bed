"""BedTech bed controller: the ``BEDTECH`` profile over the Richmat 6E codec.

BedTech beds send ``6E 01 00 code sum8``, where each code is one ASCII
character of the BedTech app (React Native/Hermes). Codes and the ``^`` STOP
live in ``profiles/richmat.py``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..const import BEDTECH_WRITE_CHAR_UUID
from ..profiles.richmat import BEDTECH
from .richmat.controller import RichmatProfileController

if TYPE_CHECKING:
    from ..coordinator import AdjustableBedCoordinator


class BedTechController(RichmatProfileController):
    """Controller for BedTech beds."""

    def __init__(self, coordinator: AdjustableBedCoordinator) -> None:
        super().__init__(coordinator, BEDTECH, char_uuid=BEDTECH_WRITE_CHAR_UUID)

    async def lights_on(self) -> None:
        """Toggle, matching the OEM app's light button: it has no discrete ON."""
        await self.lights_toggle()

    async def lights_off(self) -> None:
        await self._send("light_off")
