"""DewertOkin bed controller over the Okin N-frame codec.

Reverse engineering by Richard Hopton (smartbed-mqtt). Brands: DewertOkin (A H
Beard, HankookGallery), detected by device name rather than service UUID.

Older notes described these beds as handle-based, but handles vary by device and
firmware, so the controller writes to the stable Okin write characteristic and
Bleak resolves the live handle. Command words and timing are the ``DEWERTOKIN``
profile (``profiles/okin_nframe.py``). These beds report no positions.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from ..profiles.okin_nframe import DEWERTOKIN
from .okin_nframe import OkinNFrameController

if TYPE_CHECKING:
    from ..coordinator import AdjustableBedCoordinator

_LOGGER = logging.getLogger(__name__)


class OkinHandleController(OkinNFrameController):
    """Head and feet motors, presets, two memories, massage and a light toggle."""

    profile = DEWERTOKIN

    def __init__(self, coordinator: AdjustableBedCoordinator) -> None:
        """Initialize the DewertOkin controller."""
        super().__init__(coordinator)
        _LOGGER.debug("OkinHandleController initialized")

    def _key(self, name: str) -> bytes:
        return self._build_command(self.profile.keys[name])

    @property
    def supports_preset_zero_g(self) -> bool:
        return True

    @property
    def supports_preset_anti_snore(self) -> bool:
        return True

    @property
    def supports_preset_tv(self) -> bool:
        return True

    @property
    def supports_lights(self) -> bool:
        return True

    @property
    def supports_discrete_light_control(self) -> bool:
        """The light is a toggle key only."""
        return False

    @property
    def supports_memory_presets(self) -> bool:
        return True

    @property
    def memory_slot_count(self) -> int:
        return self.profile.memory_slots

    @property
    def supports_memory_programming(self) -> bool:
        """There is no memory programming key."""
        return False

    async def move_head_up(self) -> None:
        await self._move_with_stop(self._key("head_up"))

    async def move_head_down(self) -> None:
        await self._move_with_stop(self._key("head_down"))

    async def move_head_stop(self) -> None:
        await self._send_stop()

    async def move_back_up(self) -> None:
        await self.move_head_up()

    async def move_back_down(self) -> None:
        await self.move_head_down()

    async def move_back_stop(self) -> None:
        await self.move_head_stop()

    async def move_legs_up(self) -> None:
        await self._move_with_stop(self._key("feet_up"))

    async def move_legs_down(self) -> None:
        await self._move_with_stop(self._key("feet_down"))

    async def move_legs_stop(self) -> None:
        await self._send_stop()

    async def move_feet_up(self) -> None:
        await self.move_legs_up()

    async def move_feet_down(self) -> None:
        await self.move_legs_down()

    async def move_feet_stop(self) -> None:
        await self._send_stop()

    async def stop_all(self) -> None:
        await self._send_stop()

    async def _preset(self, name: str) -> None:
        recall = self.profile.recall
        assert recall is not None
        await self._preset_with_stop(self._key(name), recall.repeats, recall.repeat_ms)

    async def preset_flat(self) -> None:
        await self._preset("flat")

    async def preset_memory(self, memory_num: int) -> None:
        if 1 <= memory_num <= self.profile.memory_slots:
            await self._preset(f"memory_{memory_num}")
        else:
            _LOGGER.warning("Okin handle beds only support memory presets 1 and 2")

    async def program_memory(self, memory_num: int) -> None:
        _LOGGER.warning(
            "Okin handle beds don't support programming memory presets via BLE (requested slot: %d)",
            memory_num,
        )

    async def preset_zero_g(self) -> None:
        await self._preset("zero_g")

    async def preset_tv(self) -> None:
        await self._preset("tv")

    async def preset_anti_snore(self) -> None:
        await self._preset("anti_snore")

    async def lights_toggle(self) -> None:
        await self.write_command(self._key("light"))

    async def lights_on(self) -> None:
        """Toggle: calling this while the light is on turns it off."""
        await self.lights_toggle()

    async def lights_off(self) -> None:
        """Toggle: calling this while the light is off turns it on."""
        await self.lights_toggle()

    async def massage_toggle(self) -> None:
        await self.write_command(self._key("massage_wave"))

    async def massage_off(self) -> None:
        await self.write_command(self._key("massage_off"))

    async def massage_head_toggle(self) -> None:
        await self.write_command(self._key("massage_head"))

    async def massage_foot_toggle(self) -> None:
        await self.write_command(self._key("massage_foot"))
