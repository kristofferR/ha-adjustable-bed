"""Jensen LinOn bed controller.

Protocol from the clean-room APK Protocol Audit of ``air.no.jensen.adjustablesleep``
2.0.37 (106). The Jensen Adjustable Sleep app drives LinOn beds ("Adjustable Bed"
and "Jensen Bed" names) through the LinonPI services the Svane controller uses,
but with its own one-byte frames. See docs/beds/jensen.md.

The app never subscribes to LinOn notifications, so this profile has no
position feedback, and its memory and light-intensity paths never reach the bed.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING, Any

from ..const import (
    SVANE_CHAR_DOWN_UUID,
    SVANE_CHAR_POSITION_UUID,
    SVANE_CHAR_UP_UUID,
    SVANE_FEET_SERVICE_UUID,
    SVANE_HEAD_SERVICE_UUID,
    SVANE_LIGHT_ON_OFF_UUID,
    SVANE_LIGHT_SERVICE_UUID,
)
from .svane import SvaneController

if TYPE_CHECKING:
    from ..coordinator import AdjustableBedCoordinator

# The app resends a held frame, or steps a combined-motion sequence, every 800 ms.
HOLD_INTERVAL_MS = 800

_MOTOR_SERVICES = {
    "back": SVANE_HEAD_SERVICE_UUID,
    "legs": SVANE_FEET_SERVICE_UUID,
}


class JensenLinonCommands:
    """One-byte LinOn frames, each written to a per-function characteristic."""

    MOVE = bytes([0x01])
    STOP = bytes([0xFF])
    # Written to both position characteristics: go to position zero.
    FLAT = bytes([0x00])

    @staticmethod
    def light(on: bool) -> bytes:
        """Build the under-bed light frame: state, timer seconds (none), 0."""
        return bytes([0x01 if on else 0x00, 0x00, 0x00])


def _direction_char(up: bool) -> str:
    return SVANE_CHAR_UP_UUID if up else SVANE_CHAR_DOWN_UUID


class JensenLinonController(SvaneController):
    """Controller for Jensen LinOn beds (Jensen Adjustable Sleep app profile)."""

    def __init__(self, coordinator: AdjustableBedCoordinator) -> None:
        """Initialize the Jensen LinOn controller."""
        super().__init__(coordinator)
        # The bed does not report light state, so track what was last sent.
        self._light_on = False

    # Capabilities
    @property
    def supports_preset_flat(self) -> bool:
        """Return True - the app's flat writes zero to both position characteristics."""
        return True

    @property
    def supports_preset_zero_g(self) -> bool:
        """Return False - the Svane position preset is not part of this app."""
        return False

    @property
    def supports_memory_presets(self) -> bool:
        """Return False - the app's LinOn favourite recall writes nothing."""
        return False

    @property
    def memory_slot_count(self) -> int:
        """Return 0 - no memory slots reach the bed."""
        return 0

    @property
    def supports_memory_programming(self) -> bool:
        """Return False - no memory slots reach the bed."""
        return False

    @property
    def supports_light_level_control(self) -> bool:
        """Return False - the app's intensity slider never writes a frame."""
        return False

    @property
    def supports_simultaneous_movement(self) -> bool:
        """Return True - the app alternates head and foot frames."""
        return True

    @property
    def simultaneous_movement_axes(self) -> tuple[str, ...]:
        """Return the two sections combined motion can drive."""
        return ("back", "legs")

    def motor_pulse_settings(self) -> tuple[int, int]:
        """Keep the configured hold duration at the app's 800 ms cadence."""
        pulse_count, pulse_delay = super().motor_pulse_settings()
        duration_ms = max(0, pulse_count - 1) * pulse_delay
        return self.timed_move_repeat_count(duration_ms, HOLD_INTERVAL_MS), HOLD_INTERVAL_MS

    # Notifications: the app never subscribes, so there is nothing to follow.
    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        """Keep the callback; LinOn reports are not used."""
        self._notify_callback = callback

    async def stop_notify(self) -> None:
        """Nothing to stop."""

    async def read_positions(self, motor_count: int = 2) -> None:
        """LinOn beds have no position feedback in this profile."""
        del motor_count

    # Movement
    async def _hold_sequence(self, steps: Sequence[tuple[str, str]], repeat_count: int) -> None:
        """Write MOVE through ``steps`` in turn every 800 ms, then always STOP."""
        cancel_event = self._coordinator.cancel_command
        try:
            for index in range(repeat_count):
                if cancel_event.is_set():
                    break
                service_uuid, char_uuid = steps[index % len(steps)]
                await self._write_to_service_char(
                    service_uuid, char_uuid, JensenLinonCommands.MOVE, cancel_event=cancel_event
                )
                if index < repeat_count - 1:
                    await asyncio.sleep(HOLD_INTERVAL_MS / 1000)
        finally:
            await self._send_stop()

    async def _move_motor(self, service_uuid: str, char_uuid: str) -> None:
        """Hold one direction characteristic, then STOP."""
        pulse_count, _ = self.motor_pulse_settings()
        await self._hold_sequence(((service_uuid, char_uuid),), pulse_count)

    async def _send_stop(self) -> None:
        """Write STOP to the head, then the foot, up characteristic."""
        cancel_event = asyncio.Event()  # STOP must not be suppressed by a cancel
        for service_uuid in (SVANE_HEAD_SERVICE_UUID, SVANE_FEET_SERVICE_UUID):
            await self._write_to_service_char(
                service_uuid, SVANE_CHAR_UP_UUID, JensenLinonCommands.STOP, cancel_event=cancel_event
            )

    async def move_head_stop(self) -> None:
        """Stop both motors; the app has one STOP for the bed."""
        await self._send_stop()

    async def move_legs_stop(self) -> None:
        """Stop both motors; the app has one STOP for the bed."""
        await self._send_stop()

    async def stop_all(self) -> None:
        """Stop both motors."""
        await self._send_stop()

    async def move_simultaneously(
        self,
        first_axis: str,
        first_up: bool,
        second_axis: str,
        second_up: bool,
        duration_ms: int | None = None,
    ) -> None:
        """Alternate head and foot frames, as the app's combined controls do."""
        directions = {first_axis: first_up, second_axis: second_up}
        if set(directions) != set(self.simultaneous_movement_axes):
            raise ValueError("Jensen LinOn beds combine only the back and legs sections")
        repeat_count, _ = self.motor_pulse_settings()
        if duration_ms is not None:
            repeat_count = self.timed_move_repeat_count(duration_ms, HOLD_INTERVAL_MS)
        steps = tuple(
            (_MOTOR_SERVICES[axis], _direction_char(directions[axis])) for axis in ("back", "legs")
        )
        await self._hold_sequence(steps, max(2, repeat_count))

    # Presets
    async def preset_flat(self) -> None:
        """Send position zero to the head, then the foot, motor."""
        cancel_event = self._coordinator.cancel_command
        for service_uuid in (SVANE_HEAD_SERVICE_UUID, SVANE_FEET_SERVICE_UUID):
            if cancel_event.is_set():
                return
            await self._write_to_service_char(
                service_uuid, SVANE_CHAR_POSITION_UUID, JensenLinonCommands.FLAT
            )

    async def preset_zero_g(self) -> None:
        """Not part of the Jensen LinOn profile."""
        raise NotImplementedError("Jensen LinOn beds have no position preset")

    async def preset_memory(self, memory_num: int) -> None:
        """Not reachable in the Jensen LinOn profile."""
        raise NotImplementedError("Jensen LinOn beds have no memory recall")

    async def program_memory(self, memory_num: int) -> None:
        """Not reachable in the Jensen LinOn profile."""
        raise NotImplementedError("Jensen LinOn beds have no memory programming")

    # Lights
    async def _set_light(self, on: bool) -> None:
        await self._write_to_service_char(
            SVANE_LIGHT_SERVICE_UUID, SVANE_LIGHT_ON_OFF_UUID, JensenLinonCommands.light(on)
        )
        self._light_on = on
        self.forward_controller_state_updates({"under_bed_lights_on": on})

    async def lights_on(self) -> None:
        """Turn the under-bed light on."""
        await self._set_light(True)

    async def lights_off(self) -> None:
        """Turn the under-bed light off."""
        await self._set_light(False)

    async def lights_toggle(self) -> None:
        """Toggle the under-bed light."""
        await self._set_light(not self._light_on)

    async def set_light_level(self, level: int) -> None:
        """Not reachable in the Jensen LinOn profile."""
        raise NotImplementedError("Jensen LinOn beds have no light level control")

    def get_light_state(self) -> dict[str, Any]:
        """Return the light state this integration last sent."""
        return {"is_on": self._light_on}
