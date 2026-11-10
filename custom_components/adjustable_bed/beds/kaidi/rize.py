"""Rize Beds 1.4.2 (57), unit149, over the shared Kaidi app session.

The profile's literal vectors select capabilities. Android global-target races,
short-tap STOP suppression and unauthenticated admission are not reproduced.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Mapping
from typing import TYPE_CHECKING, Final, cast

from bleak.backends.characteristic import BleakGATTCharacteristic

from ...card import CARD_UTILITY
from ...codec import kaidi as codec
from ...controller_state import StateKey
from ...execution import ExecutionCapabilities
from ...profiles.kaidi import (
    RIZE_DEFAULT_PARAMETERS,
    RizeProfile,
    rize_advertisement,
    validate_rize_profile,
)
from ..entity_specs import ControllerButtonSpec, ControllerStateBinarySensorSpec
from .app import KaidiAppController

if TYPE_CHECKING:
    from ...coordinator import AdjustableBedCoordinator
    from ..lifecycle import ControllerSession

BATTERY_MODE: Final = StateKey[bool | None]("rize_battery_mode")


class RizeController(KaidiAppController):
    """One physical node with app-proven native sides where available."""

    profile: RizeProfile

    def __init__(self, coordinator: AdjustableBedCoordinator) -> None:
        super().__init__(coordinator, validate_rize_profile(coordinator.entry.data))
        self._battery_mode: bool | None = None
        self._next_write_at = 0.0
        self._pacing_lock = asyncio.Lock()

    def restore_persisted_app_state(self, state: Mapping[str, object]) -> None:
        super().restore_persisted_app_state(state)
        self._parameter = 0

    @property
    def execution(self) -> ExecutionCapabilities:
        return self.profile.execution

    @property
    def pattern_count(self) -> int:
        return 4 if self.profile.product == 140 else 3

    @property
    def has_neck_support(self) -> bool:
        return "neck" in self.profile.axes

    @property
    def supports_preset_tv(self) -> bool:
        return self.profile.extended

    @property
    def supports_preset_lounge(self) -> bool:
        return self.profile.extended

    @property
    def massage_intensity_zones(self) -> list[str]:
        # Voice on layouts5-8 also reaches leg strength, independent of its slider.
        return ["head", "foot"] if self.profile.extended else ["head"]

    @property
    def massage_timer_options(self) -> list[int]:
        return [15, 30, 45]

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        specs = super().controller_button_specs
        if self.profile.layout == 9:
            specs = tuple(s for s in specs if s.key not in ("rize_all_up", "rize_all_down"))
        if not self.profile.extended:
            return specs
        return (*specs, *(
            ControllerButtonSpec(
                f"rize_motion_{state}", f"Motion sensor {state}",
                lambda c, state=state: cast(RizeController, c)._action(f"motion_{state}"),
                translation_key=f"rize_motion_{state}", card=CARD_UTILITY,
            )
            for state in ("on", "off")
        ))

    @property
    def controller_state_binary_sensor_specs(self) -> tuple[ControllerStateBinarySensorSpec, ...]:
        if not self.profile.extended:
            return ()
        return (ControllerStateBinarySensorSpec(
            "rize_battery_mode", "rize_battery_mode", BATTERY_MODE, "mdi:battery",
        ),)

    @property
    def diagnostic_poll_interval(self) -> float | None:
        return self.profile.power_poll_s if self.profile.extended else None

    async def async_after_connect(self, session: ControllerSession) -> None:
        from homeassistant.components import bluetooth

        info = bluetooth.async_last_service_info(session.hass, session.address, connectable=True)
        ad = rize_advertisement(info.manufacturer_data) if info is not None else None
        if ad is not None and ad.adv_type == 9 and ad.product_id == self.profile.product:
            # An unprovisioned bed cannot join yet. Ordinary actions still
            # authenticate on demand; only explicit enrollment assigns a room.
            return
        await self._ensure_session()
        await self.async_refresh_diagnostics()

    async def async_refresh_diagnostics(self) -> None:
        # Coordinator polls only a live link under its query lock, without
        # extending idle ownership or reconnecting after quick handoff.
        if self.profile.extended and self._ready and self._own is not None:
            if self._target is None:
                await self.write_command(codec.ping(self._own))
            else:
                await self._send_opcode(self._opcode("power_query"))

    def on_disconnect(self) -> None:
        super().on_disconnect()
        self._battery_mode = None
        self._next_write_at = 0.0
        self.forward_controller_state_updates(BATTERY_MODE(None))

    def _notification(self, sender: BleakGATTCharacteristic, data: bytearray) -> None:
        super()._notification(sender, data)
        frame = bytes(data)
        if isinstance(codec.parse_notification(frame), codec.RosterChange):
            self._battery_mode = None
            self.forward_controller_state_updates(BATTERY_MODE(None))
        if not self.profile.extended or len(frame) < 14:
            return
        # E-PARSE forwards own-addressed and broadcast events, not other phones'.
        destination = int.from_bytes(frame[1:5], "little")
        if destination not in (codec.BROADCAST, self._own):
            return
        match codec.parse_notification(frame):
            case codec.ControlReply(command=166, value=value):
                self._battery_mode = value == 1
                self.forward_controller_state_updates(BATTERY_MODE(self._battery_mode))

    async def write_command(
        self, command: bytes, repeat_count: int = 1, repeat_delay_ms: int = 100,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        """One callback-gated write; retain the app's 50ms sender cadence."""
        cancel = cancel_event or self._coordinator.cancel_command
        client = self.client
        async with self._pacing_lock:
            delay = self._next_write_at - time.monotonic()
            if delay > 0:
                try:
                    await asyncio.wait_for(cancel.wait(), delay)
                except TimeoutError:
                    pass
            if cancel.is_set():
                raise asyncio.CancelledError
            await self._write_gatt_with_retry(
                codec.WRITE_CHAR_UUID, command, response=True, cancel_event=cancel,
                expected_client=client,
            )
            self._next_write_at = time.monotonic() + self.profile.write_spacing_s

    async def _send_opcode(self, opcode: int, *, cancel: asyncio.Event | None = None) -> None:
        try:
            await super()._send_opcode(opcode, cancel=cancel)
        finally:
            # E-FRAME: the app resets its payload on every manager accessor.
            self._parameter = 0

    def _axis(self, axis: str) -> str:
        if axis == "all":
            if self.profile.layout == 9:
                raise ValueError("Clarity has no all-motor control")
            return "new_all" if self.profile.extended else "all"
        if axis not in self.profile.axes:
            raise ValueError(f"Rize product {self.profile.product} has no {axis} control")
        if axis == "back" and (
            self.profile.layout in (2, 5, 6, 7, 8) or self.profile.split
        ):
            return "head"
        return axis

    async def _move(self, axis: str, up: bool) -> None:
        if up and self._battery_mode is True:
            raise ValueError("Rize reports battery mode; raising is disabled")
        await super()._move(axis, up)

    async def stop_all(self) -> None:
        for axis in self.profile.axes:
            await self._stop(axis)
        if self.profile.layout != 9:
            await self._stop("all")

    async def move_neck_up(self) -> None:
        await self._move("neck", True)

    async def move_neck_down(self) -> None:
        await self._move("neck", False)

    async def move_neck_stop(self) -> None:
        await self._stop("neck")

    async def preset_tv(self) -> None:
        if not self.profile.extended:
            raise ValueError("Reading requires a Rize voice layout")
        await self._action("book")

    async def preset_lounge(self) -> None:
        if not self.profile.extended:
            raise ValueError("Leisure requires a Rize voice layout")
        await self._action("leisure")

    async def _special(self, parameter: int, parameter2: int = 0) -> None:
        if self._coordinator.cancel_command.is_set():
            raise asyncio.CancelledError
        await self._ensure_session()
        assert self._own is not None and self._target is not None
        await self.write_command(codec.control(
            self._target, self._own, self._opcode("special"), parameter, parameter2,
        ))

    async def set_pattern(self, pattern: int) -> None:
        if type(pattern) is not int or not 0 <= pattern <= self.pattern_count:
            raise ValueError("Pattern is unavailable for this Rize product")
        lane = self._lane
        selected = 0 if self._patterns[lane] == pattern else pattern
        if selected == 4 or (selected == 0 and self._patterns[lane] == 4):
            await self._special(1, 1 if selected else 4)
        else:
            await self._action(f"pattern_{selected}" if selected else "pattern_cancel")
        for affected in self._affected_lanes:
            self._patterns[affected] = selected
        self._save_intent()

    async def massage_mode_step(self) -> None:
        await self.set_pattern((self._patterns[self._lane] + 1) % (self.pattern_count + 1))

    def validate_program_preset(self, preset: str, confirm: bool) -> None:
        if not confirm or preset not in self.profile.programmable_presets:
            raise ValueError("Confirm programming a supported Rize default preset")

    async def program_preset(self, preset: str, confirm: bool) -> None:
        """Capture one physical target under HA command admission, with no pre-save."""
        self.validate_program_preset(preset, confirm)
        await self._special(RIZE_DEFAULT_PARAMETERS[preset])

    def _enrollment_advertisement(self, manufacturer_data: Mapping[int, bytes]):
        return rize_advertisement(manufacturer_data)
