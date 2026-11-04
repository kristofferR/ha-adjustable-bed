"""Okin 5A bed controller for the ``okin_7byte`` and ``okin_nordic`` profiles.

Protocol reverse-engineered and documented by MaximumWorf (https://github.com/MaximumWorf)
Source: https://github.com/MaximumWorf/homeassistant-nectar

Every command is a ``5A 01 03 10 30 [key] A5`` key frame from ``codec/okin_5a.py``.
The profile in ``profiles/okin_5a.py`` chooses the transport, write mode, wake
frames, keys and timing. ``OkinNordicController`` and ``OkinCB35Controller`` are
this controller over other profiles. See ``docs/beds/okin-5a.md``.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Final

from bleak.exc import BleakError

from ..profiles.okin_5a import OKIN_7BYTE, Action, Okin5AProfile
from .base import BedController

if TYPE_CHECKING:
    from ..coordinator import AdjustableBedCoordinator

_LOGGER = logging.getLogger(__name__)

_MEMORY: Final[dict[int, Action]] = {1: "memory_1", 2: "memory_2"}


class Okin7ByteController(BedController):
    """Controller for beds using the Okin 5A key frame."""

    def __init__(
        self,
        coordinator: AdjustableBedCoordinator,
        profile: Okin5AProfile = OKIN_7BYTE,
    ) -> None:
        super().__init__(coordinator)
        self.profile = profile
        self._initialized: bool = not profile.wake

    @property
    def control_characteristic_uuid(self) -> str:
        return self.profile.transport_uuid

    # Capability properties
    @property
    def supports_preset_zero_g(self) -> bool:
        return True

    @property
    def supports_preset_anti_snore(self) -> bool:
        return True

    @property
    def supports_preset_lounge(self) -> bool:
        return True

    @property
    def supports_preset_tv(self) -> bool:
        return "tv" in self.profile.frames

    @property
    def supports_preset_incline(self) -> bool:
        return "incline" in self.profile.frames

    @property
    def supports_massage_intensity_step_control(self) -> bool:
        # The methods are always overridden, so the base override check would
        # advertise buttons that raise on profiles without intensity keys.
        return "massage_up" in self.profile.frames

    @property
    def has_lumbar_support(self) -> bool:
        return True

    @property
    def supports_lights(self) -> bool:
        return True

    @property
    def supports_discrete_light_control(self) -> bool:
        return True

    @property
    def supports_light_cycle(self) -> bool:
        return self.profile.light_cycle

    @property
    def supports_memory_presets(self) -> bool:
        return "memory_1" in self.profile.frames

    @property
    def memory_slot_count(self) -> int:
        return 2

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 100,
        cancel_event: asyncio.Event | None = None,
        *,
        on_write: Callable[[], None] | None = None,
    ) -> None:
        """Write a command, sending the profile's wake frames on first use."""
        if self.client is None or not self.client.is_connected:
            _LOGGER.error("Cannot write command: BLE client not connected")
            raise ConnectionError("Not connected to bed")

        effective_cancel = cancel_event or self._coordinator.cancel_command
        profile = self.profile

        if not self._initialized:
            if effective_cancel is not None and effective_cancel.is_set():
                _LOGGER.info("Command cancelled before init sequence")
                return
            _LOGGER.debug("Sending wake frames before first command")
            try:
                for frame in profile.wake:
                    async with self._ble_lock:
                        await self.client.write_gatt_char(
                            self.control_characteristic_uuid,
                            frame,
                            response=profile.wake_with_response,
                        )
                    await asyncio.sleep(0.1)
                self._initialized = True
            except BleakError:
                _LOGGER.exception("Failed to send wake frames")
                raise

        await self._write_gatt_with_retry(
            self.control_characteristic_uuid,
            command,
            repeat_count=repeat_count,
            repeat_delay_ms=repeat_delay_ms,
            cancel_event=effective_cancel,
            response=profile.write_with_response,
            on_write=on_write,
        )

    async def _send(self, action: Action) -> None:
        await self.write_command(self.profile.frame(action))

    async def _send_stop(self) -> None:
        """Send STOP with a fresh cancel event so a pending cancel cannot suppress it."""
        stop = self.profile.stop
        await self.write_command(
            self.profile.frame("stop"),
            repeat_count=stop.repeats,
            repeat_delay_ms=stop.repeat_ms,
            cancel_event=asyncio.Event(),
        )

    async def _move(self, action: Action) -> None:
        await self._move_with_stop(self.profile.frame(action))

    async def _recall(self, action: Action) -> None:
        recall = self.profile.recall
        await self._preset_with_stop(self.profile.frame(action), recall.repeats, recall.repeat_ms)

    # Motor control methods
    async def move_head_up(self) -> None:
        await self._move("head_up")

    async def move_head_down(self) -> None:
        await self._move("head_down")

    async def move_head_stop(self) -> None:
        await self._send_stop()

    async def move_feet_up(self) -> None:
        await self._move("feet_up")

    async def move_feet_down(self) -> None:
        await self._move("feet_down")

    async def move_feet_stop(self) -> None:
        await self._send_stop()

    async def move_back_up(self) -> None:
        await self.move_head_up()

    async def move_back_down(self) -> None:
        await self.move_head_down()

    async def move_back_stop(self) -> None:
        await self.move_head_stop()

    async def move_legs_up(self) -> None:
        await self.move_feet_up()

    async def move_legs_down(self) -> None:
        await self.move_feet_down()

    async def move_legs_stop(self) -> None:
        await self.move_feet_stop()

    async def move_lumbar_up(self) -> None:
        await self._move("lumbar_up")

    async def move_lumbar_down(self) -> None:
        await self._move("lumbar_down")

    async def move_lumbar_stop(self) -> None:
        await self._send_stop()

    # Preset positions
    async def preset_flat(self) -> None:
        await self._recall("flat")

    async def preset_zero_g(self) -> None:
        await self._recall("zero_g")

    async def preset_anti_snore(self) -> None:
        await self._recall("anti_snore")

    async def preset_lounge(self) -> None:
        await self._recall("lounge")

    async def preset_tv(self) -> None:
        await self._recall("tv")

    async def preset_incline(self) -> None:
        await self._recall("incline")

    async def preset_memory(self, memory_num: int) -> None:
        """Go to memory position (slots 1-2)."""
        if memory_num not in _MEMORY:
            raise NotImplementedError(f"Memory slot {memory_num} not supported on this variant")
        await self._recall(_MEMORY[memory_num])

    async def program_memory(self, memory_num: int) -> None:
        """Program memory position (not supported)."""
        raise NotImplementedError(
            f"Memory programming (slot {memory_num}) not supported on Okin 7-byte beds"
        )

    async def stop_all(self) -> None:
        await self._send_stop()

    # Massage controls
    async def massage_toggle(self) -> None:
        await self._send("massage_toggle")

    async def massage_on(self) -> None:
        await self._send("massage_on")

    async def massage_off(self) -> None:
        await self._send("massage_off")

    async def massage_mode_step(self) -> None:
        await self._send("massage_mode")

    async def massage_intensity_up(self) -> None:
        await self._send("massage_up")

    async def massage_intensity_down(self) -> None:
        await self._send("massage_down")

    # Head and foot massage share the global toggle.
    async def massage_head_toggle(self) -> None:
        await self.massage_toggle()

    async def massage_foot_toggle(self) -> None:
        await self.massage_toggle()

    # Light controls
    async def lights_on(self) -> None:
        await self._send("light_on")

    async def lights_off(self) -> None:
        lights_off = self.profile.lights_off
        await self.write_command(
            self.profile.frame("light_off"),
            repeat_count=lights_off.repeats,
            repeat_delay_ms=lights_off.repeat_ms,
        )

    async def lights_toggle(self) -> None:
        await self._send("light_toggle")
