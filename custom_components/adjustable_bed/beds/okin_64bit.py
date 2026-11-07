"""OKIN 64-bit bed controller implementation.

OKIN 64-bit beds use 64-bit Okin N-frames (``codec/okin_nframe.py``):
``08 02 <64-bit word>``, ten bytes, no checksum. The words are the
``OKIN_64BIT_KEYS`` profile data.

Two protocol variants use the same command format:
- Protocol 25_42_02: Nordic UART service, fire-and-forget (withoutResponse=True)
- Protocol 36_33_04a: Custom OKIN service, wait-for-response (withoutResponse=False)

Protocol reverse-engineered from com.okin.bedding.adjustbed app (Flutter/Dart).
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from ..codec import okin_nframe as codec
from ..const import (
    NORDIC_UART_WRITE_CHAR_UUID,
    OKIMAT_WRITE_CHAR_UUID,
)
from ..profiles.okin_nframe import OKIN_64BIT_KEYS as _KEYS
from ..profiles.okin_nframe import OKIN_64BIT_PROFILES, OkinNFrameProfile
from .base import BedController
from .builder import BuildContext

if TYPE_CHECKING:
    from ..coordinator import AdjustableBedCoordinator

_LOGGER = logging.getLogger(__name__)


# Protocol variants
OKIN_64BIT_VARIANT_NORDIC = "nordic"  # Protocol 25_42_02 - Nordic UART, fire-and-forget
OKIN_64BIT_VARIANT_CUSTOM = "custom"  # Protocol 36_33_04a - Custom OKIN, wait-for-response


class Okin64BitController(BedController):
    """Controller for OKIN 64-bit beds.

    Supports two protocol variants:
    - Nordic (Protocol 25_42_02): Nordic UART service, fire-and-forget
    - Custom (Protocol 36_33_04a): Custom OKIN service, wait-for-response
    """

    def __init__(
        self,
        coordinator: AdjustableBedCoordinator,
        variant: str = OKIN_64BIT_VARIANT_NORDIC,
        char_uuid: str | None = None,
    ) -> None:
        """Initialize the OKIN 64-bit controller.

        Args:
            coordinator: The AdjustableBedCoordinator instance
            variant: Protocol variant ('nordic' or 'custom')
            char_uuid: Optional override for characteristic UUID
        """
        super().__init__(coordinator)
        self._variant = variant

        # Determine characteristic UUID based on variant
        if char_uuid:
            self._char_uuid = char_uuid
        elif variant == OKIN_64BIT_VARIANT_CUSTOM:
            self._char_uuid = OKIMAT_WRITE_CHAR_UUID
        else:
            self._char_uuid = NORDIC_UART_WRITE_CHAR_UUID

        # Any other variant uses the Nordic UART route.
        self._profile = OKIN_64BIT_PROFILES.get(variant, OKIN_64BIT_PROFILES["nordic"])
        self._write_with_response = self._profile.write == "response"

        _LOGGER.debug(
            "Okin64BitController initialized (variant: %s, char: %s, response: %s)",
            variant,
            self._char_uuid,
            self._write_with_response,
        )

    @property
    def protocol_diagnostics(self) -> dict[str, object]:
        return {"variant": self._variant}

    @property
    def control_characteristic_uuid(self) -> str:
        """Return the UUID of the control characteristic."""
        return self._char_uuid

    # Capability properties
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
    def supports_preset_lounge(self) -> bool:
        return True

    @property
    def supports_memory_presets(self) -> bool:
        return True

    @property
    def memory_slot_count(self) -> int:
        return 2

    @property
    def supports_memory_programming(self) -> bool:
        return False

    @property
    def supports_lights(self) -> bool:
        return True

    @property
    def supports_discrete_light_control(self) -> bool:
        return True

    @property
    def has_lumbar_support(self) -> bool:
        return True

    @property
    def supports_stop_all(self) -> bool:
        return True

    @property
    def profile(self) -> OkinNFrameProfile:
        """The variant's profile: its words and write mode."""
        return self._profile

    def _build_command(self, word: int) -> bytes:
        """Frame one 64-bit word."""
        return codec.frame(word, 8)

    async def _send_command(self, command: bytes, repeat: int | None = None) -> None:
        """Send a framed command at the entry's pulse settings."""
        pulse_count = repeat if repeat is not None else self._coordinator.motor_pulse_count
        pulse_delay = self._coordinator.motor_pulse_delay_ms
        await self.write_command(command, repeat_count=pulse_count, repeat_delay_ms=pulse_delay)

    async def _move_with_stop(self, command: bytes) -> None:
        """Execute a movement command and send STOP at the end."""
        try:
            await self._send_command(command)
        finally:
            try:
                await self.write_command(
                    self._build_command(_KEYS["stop"]),
                    cancel_event=asyncio.Event(),
                )
            except Exception:
                _LOGGER.debug("Failed to send STOP command during cleanup")

    # Motor control methods
    async def move_head_up(self) -> None:
        await self._move_with_stop(self._build_command(_KEYS["head_up"]))

    async def move_head_down(self) -> None:
        await self._move_with_stop(self._build_command(_KEYS["head_down"]))

    async def move_head_stop(self) -> None:
        await self.write_command(
            self._build_command(_KEYS["stop"]),
            cancel_event=asyncio.Event(),
        )

    async def move_back_up(self) -> None:
        await self.move_head_up()

    async def move_back_down(self) -> None:
        await self.move_head_down()

    async def move_back_stop(self) -> None:
        await self.move_head_stop()

    async def move_legs_up(self) -> None:
        await self._move_with_stop(self._build_command(_KEYS["foot_up"]))

    async def move_legs_down(self) -> None:
        await self._move_with_stop(self._build_command(_KEYS["foot_down"]))

    async def move_legs_stop(self) -> None:
        await self.move_head_stop()

    async def move_feet_up(self) -> None:
        await self._move_with_stop(self._build_command(_KEYS["foot_up"]))

    async def move_feet_down(self) -> None:
        await self._move_with_stop(self._build_command(_KEYS["foot_down"]))

    async def move_feet_stop(self) -> None:
        await self.move_head_stop()

    async def move_lumbar_up(self) -> None:
        await self._move_with_stop(self._build_command(_KEYS["lumbar_up"]))

    async def move_lumbar_down(self) -> None:
        await self._move_with_stop(self._build_command(_KEYS["lumbar_down"]))

    async def move_lumbar_stop(self) -> None:
        await self.move_head_stop()

    async def stop_all(self) -> None:
        await self.write_command(
            self._build_command(_KEYS["stop"]),
            cancel_event=asyncio.Event(),
        )

    # Preset methods
    async def preset_flat(self) -> None:
        await self.write_command(self._build_command(_KEYS["flat"]))

    async def preset_memory(self, memory_num: int) -> None:
        """Go to memory preset."""
        commands = {
            1: _KEYS["memory_1"],
            2: _KEYS["memory_2"],
        }
        if (word := commands.get(memory_num)) is not None:
            await self.write_command(self._build_command(word))
        else:
            _LOGGER.warning("Invalid memory number %d (valid: 1-2)", memory_num)

    async def program_memory(self, memory_num: int) -> None:  # noqa: ARG002
        """Program current position to memory (not supported - use set commands)."""
        _LOGGER.warning(
            "OKIN 64-bit beds don't support programming memory presets directly. "
            "Memory positions are programmed by sending set commands at the desired position."
        )

    async def preset_zero_g(self) -> None:
        await self.write_command(self._build_command(_KEYS["zero_g"]))

    async def preset_anti_snore(self) -> None:
        await self.write_command(self._build_command(_KEYS["anti_snore"]))

    async def preset_tv(self) -> None:
        await self.write_command(self._build_command(_KEYS["tv_pc"]))

    async def preset_lounge(self) -> None:
        await self.write_command(self._build_command(_KEYS["lounge"]))

    # Light methods
    async def lights_on(self) -> None:
        await self.write_command(self._build_command(_KEYS["light_on"]))

    async def lights_off(self) -> None:
        await self.write_command(self._build_command(_KEYS["light_off"]))

    async def lights_toggle(self) -> None:
        await self.write_command(self._build_command(_KEYS["light_toggle"]))

    # Massage methods
    async def massage_toggle(self) -> None:
        await self.write_command(self._build_command(_KEYS["massage_switch"]))

    async def massage_head_up(self) -> None:
        await self.write_command(self._build_command(_KEYS["strength_up"]))

    async def massage_head_down(self) -> None:
        await self.write_command(self._build_command(_KEYS["strength_down"]))

    async def massage_mode_step(self) -> None:
        await self.write_command(self._build_command(_KEYS["wave_mode"]))


async def build_controller(ctx: BuildContext) -> Okin64BitController:
    """Build the controller; Auto defaults to Nordic UART (fire-and-forget)."""
    variant = ctx.variant if ctx.variant and ctx.variant != "auto" else "nordic"
    _LOGGER.debug("Using OKIN 64-bit variant: %s", variant)
    return Okin64BitController(ctx.coordinator, variant=variant)
