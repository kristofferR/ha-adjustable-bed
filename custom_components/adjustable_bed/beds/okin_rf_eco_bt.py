"""OKIN Smart Remote RF ECO BT single-actuator controller."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable

from .base import MotorControlSpec
from .okin_uuid import OkinUuidController

_LOGGER = logging.getLogger(__name__)

STAIR_OUT_COMMAND = 0x00000001
STAIR_IN_COMMAND = 0x00000002
STOP_COMMAND = 0x00000000


class OkinRfEcoBtController(OkinUuidController):
    """Controller for OKIN Smart Remote single-actuator stair lifts.

    The OKIN Smart Remote APK maps RF-TOPLINE fallback commands M2Out/M2In to
    the moving stair actuator. This profile intentionally exposes only that
    single actuator surface.
    """

    @property
    def supports_preset_flat(self) -> bool:
        """Return False - this profile has no bed preset entities."""
        return False

    @property
    def supports_memory_presets(self) -> bool:
        """Return False - this profile has no memory preset entities."""
        return False

    @property
    def memory_slot_count(self) -> int:
        """Return zero memory slots for this single-actuator profile."""
        return 0

    @property
    def supports_memory_programming(self) -> bool:
        """Return False - this profile has no memory programming support."""
        return False

    @property
    def supports_lights(self) -> bool:
        """Return False - no light entities are exposed for this profile."""
        return False

    @property
    def supports_light_toggle_control(self) -> bool:
        """Return False - inherited OKIN light commands are not valid here."""
        return False

    @property
    def supports_massage(self) -> bool:
        """Return False - no massage entities are exposed for this profile."""
        return False

    @property
    def supports_massage_toggle_control(self) -> bool:
        """Return False - inherited OKIN massage commands are not valid here."""
        return False

    @property
    def supports_head_massage_intensity_step_control(self) -> bool:
        """Return False - inherited OKIN massage commands are not valid here."""
        return False

    @property
    def supports_foot_massage_intensity_step_control(self) -> bool:
        """Return False - inherited OKIN massage commands are not valid here."""
        return False

    @property
    def supports_massage_mode_step_control(self) -> bool:
        """Return False - inherited OKIN massage commands are not valid here."""
        return False

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        """Expose the single moving stair actuator."""
        return (
            MotorControlSpec(
                key="stair",
                translation_key="stair",
                open_fn=lambda ctrl: ctrl.move_back_up(),
                close_fn=lambda ctrl: ctrl.move_back_down(),
                stop_fn=lambda ctrl: ctrl.move_back_stop(),
            ),
        )

    @property
    def stale_motor_entity_keys(self) -> frozenset[str]:
        """Remove bed motor covers if an existing entry is switched to this profile."""
        return frozenset(
            {
                "back",
                "legs",
                "head",
                "feet",
                "lumbar",
                "pillow",
                "neck",
                "tilt",
                "hip",
                "bed_height",
            }
        )

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        """Store callback only; this profile has no supported position feedback."""
        self._notify_callback = callback

    async def stop_notify(self) -> None:
        """Clear stored callback; no BLE notification subscription is used."""
        self._notify_callback = None

    async def read_positions(self, motor_count: int = 1) -> None:
        """No-op because this profile has no supported position feedback."""
        del motor_count

    async def move_back_up(self) -> None:
        """Move the stair actuator out/open."""
        await self._move_motor("back", STAIR_OUT_COMMAND)

    async def move_back_down(self) -> None:
        """Move the stair actuator in/close."""
        await self._move_motor("back", STAIR_IN_COMMAND)

    async def stop_all(self) -> None:
        """Stop the stair actuator."""
        self._motor_state = {}
        await self.write_command(
            self._build_command(STOP_COMMAND),
            cancel_event=asyncio.Event(),
        )

    async def move_head_up(self) -> None:
        """Reject non-profile motor commands."""
        await self._unsupported_motor("head")

    async def move_head_down(self) -> None:
        """Reject non-profile motor commands."""
        await self._unsupported_motor("head")

    async def move_head_stop(self) -> None:
        """Reject non-profile motor commands."""
        await self._unsupported_motor("head")

    async def move_legs_up(self) -> None:
        """Reject non-profile motor commands."""
        await self._unsupported_motor("legs")

    async def move_legs_down(self) -> None:
        """Reject non-profile motor commands."""
        await self._unsupported_motor("legs")

    async def move_legs_stop(self) -> None:
        """Reject non-profile motor commands."""
        await self._unsupported_motor("legs")

    async def move_feet_up(self) -> None:
        """Reject non-profile motor commands."""
        await self._unsupported_motor("feet")

    async def move_feet_down(self) -> None:
        """Reject non-profile motor commands."""
        await self._unsupported_motor("feet")

    async def move_feet_stop(self) -> None:
        """Reject non-profile motor commands."""
        await self._unsupported_motor("feet")

    async def preset_flat(self) -> None:
        """Reject bed-only preset commands."""
        raise NotImplementedError("Presets are not supported by OKIN RF ECO BT")

    async def preset_memory(self, memory_num: int) -> None:
        """Reject bed-only memory commands."""
        del memory_num
        raise NotImplementedError("Memory presets are not supported by OKIN RF ECO BT")

    async def program_memory(self, memory_num: int) -> None:
        """Reject bed-only memory programming commands."""
        del memory_num
        raise NotImplementedError("Memory programming is not supported by OKIN RF ECO BT")

    async def _unsupported_motor(self, motor: str) -> None:
        """Reject hidden standard bed motor commands so no M3/extra channels leak."""
        _LOGGER.debug("Ignoring unsupported %s motor command for OKIN RF ECO BT", motor)
        raise NotImplementedError(f"{motor} motor is not supported by OKIN RF ECO BT")
