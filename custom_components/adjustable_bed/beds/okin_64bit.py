"""OKIN 64-bit bed controller implementation.

OKIN 64-bit beds use 64-bit Okin N-frames (``codec/okin_nframe.py``):
``08 02 <64-bit word>``, ten bytes, no checksum. The words are the
``OKIN_64BIT_KEYS`` profile data.

Two protocol variants use the same command format:
- Protocol 25_42_02: Nordic UART service, fire-and-forget (withoutResponse=True)
- Protocol 36_33_04a: Custom OKIN service, wait-for-response (withoutResponse=False)

Protocol reverse-engineered from com.okin.bedding.adjustbed app (Flutter/Dart).

The Custom OKIN variant also opens a session on every connection, as captured
from the Resident Adjustable Base iPhone app on a Nectar Premier / Resident
base: subscribe to 62741625, then write the UTC clock record twice and the
clock query twice. Without it the base answers motor writes with ATT
"Insufficient Authorization" even on an encrypted, bonded link.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Final

from bleak.exc import BleakError

from ..ble_auth import is_ble_authentication_error
from ..codec import okin_nframe as codec
from ..const import (
    NORDIC_UART_WRITE_CHAR_UUID,
    OKIMAT_NOTIFY_CHAR_UUID,
    OKIMAT_WRITE_CHAR_UUID,
)
from ..profiles.okin_nframe import OKIN_64BIT_PROFILES, OkinNFrameProfile
from .base import BedController, ProfileExecution
from .builder import BuildContext

if TYPE_CHECKING:
    from ..coordinator import AdjustableBedCoordinator
    from .lifecycle import ControllerSession

_LOGGER = logging.getLogger(__name__)


# Protocol variants
OKIN_64BIT_VARIANT_NORDIC = "nordic"  # Protocol 25_42_02 - Nordic UART, fire-and-forget
OKIN_64BIT_VARIANT_CUSTOM = "custom"  # Protocol 36_33_04a - Custom OKIN, wait-for-response

CLOCK_QUERY: Final = codec.prefixed_query((0xE1, 0x80, 0x01))
"""``08 02 E1 80 01``, the Resident apps' clock query."""
SESSION_WRITE_GAP_S: Final = 0.12
"""The hardware-verified replay sent each session write 120 ms after the previous response."""


def clock_record(now: datetime) -> bytes:
    """Encode ``now`` as the ``E7 80 01`` clock record, in the time zone given.

    The six fields are C ``struct tm`` values: years since 1900, zero-based
    month, day, hour, minute, second. There is no checksum.
    """
    return codec.calendar_record(
        0xE7, (now.year - 1900, now.month - 1, now.day, now.hour, now.minute, now.second)
    )


class Okin64BitController(ProfileExecution[OkinNFrameProfile], BedController):
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
        *,
        profile: OkinNFrameProfile | None = None,
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
        self._profile = profile or OKIN_64BIT_PROFILES.get(variant, OKIN_64BIT_PROFILES["nordic"])
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

    @property
    def requires_notification_channel(self) -> bool:
        """The Custom OKIN session subscribes even with angle sensing disabled."""
        return self._variant == OKIN_64BIT_VARIANT_CUSTOM

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        """Subscribe to the Custom OKIN status characteristic, 62741625."""
        self._notify_callback = callback
        if self._variant != OKIN_64BIT_VARIANT_CUSTOM:
            return
        client = self.client
        if client is None or not client.is_connected:
            raise ConnectionError("Cannot subscribe to OKIN 64-bit status: not connected")
        async with self._ble_lock:
            await client.start_notify(OKIMAT_NOTIFY_CHAR_UUID, self._handle_notification)

    def _handle_notification(self, _: object, data: bytearray) -> None:
        """Forward raw status notifications to diagnostics."""
        self.forward_raw_notification(OKIMAT_NOTIFY_CHAR_UUID, bytes(data))

    async def stop_notify(self) -> None:
        """Stop the Custom OKIN status subscription."""
        self._notify_callback = None
        client = self.client
        if self._variant != OKIN_64BIT_VARIANT_CUSTOM or client is None or not client.is_connected:
            return
        try:
            async with self._ble_lock:
                await client.stop_notify(OKIMAT_NOTIFY_CHAR_UUID)
        except BleakError as err:
            _LOGGER.debug("Could not stop OKIN 64-bit notifications: %s", err)

    async def async_on_connect(self, session: ControllerSession) -> None:
        """Open the Custom OKIN session on every connection, before any command.

        Subscribe, then write the UTC clock record twice and the clock query
        twice, with response. A GATT security error is raised so the
        coordinator's pairing recovery runs; other failures are logged and
        leave the link usable for beds that need no session.
        """
        if self._variant != OKIN_64BIT_VARIANT_CUSTOM:
            await super().async_on_connect(session)
            return
        try:
            await session.async_start_notify()
            # The iPhone capture carries UTC, unlike Resident's Android app.
            clock = clock_record(datetime.now(UTC))
            for frame in (clock, clock, CLOCK_QUERY, CLOCK_QUERY):
                await self._write_gatt_with_retry(
                    self._char_uuid, frame, cancel_event=asyncio.Event(), response=True
                )
                await asyncio.sleep(SESSION_WRITE_GAP_S)
        except BleakError as err:
            if is_ble_authentication_error(err):
                raise
            _LOGGER.warning("OKIN 64-bit session setup incomplete: %s", err)

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

    # The toggles and steps below exist only where the profile defines their key;
    # an inherited method alone would offer a button that has nothing to send.
    @property
    def supports_light_toggle_control(self) -> bool:
        return "light_toggle" in self.profile.keys

    @property
    def supports_massage_toggle_control(self) -> bool:
        return "massage_switch" in self.profile.keys

    @property
    def supports_head_massage_intensity_step_control(self) -> bool:
        return {"strength_up", "strength_down"} <= self.profile.keys.keys()

    @property
    def supports_massage_mode_step_control(self) -> bool:
        return "wave_mode" in self.profile.keys

    @property
    def profile(self) -> OkinNFrameProfile:
        """The variant's profile: its words and write mode."""
        return self._profile

    def _build_command(self, word: int) -> bytes:
        """Frame one 64-bit word."""
        return codec.frame(word, self.profile.width)

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
                await self._send_stop()
            except Exception:
                _LOGGER.debug("Failed to send STOP command during cleanup")

    async def _send_stop(self) -> None:
        """Release the active key; app subclasses may own a release schedule."""
        await self.write_command(self._build_command(0), cancel_event=asyncio.Event())

    async def _press(self, word: int) -> None:
        """One app press; subclasses may add their profile's release sequence."""
        await self.write_command(self._build_command(word))

    # Motor control methods
    async def move_head_up(self) -> None:
        await self._move_with_stop(self._build_command(self.profile.keys["head_up"]))

    async def move_head_down(self) -> None:
        await self._move_with_stop(self._build_command(self.profile.keys["head_down"]))

    async def move_head_stop(self) -> None:
        await self._send_stop()

    async def move_back_up(self) -> None:
        await self.move_head_up()

    async def move_back_down(self) -> None:
        await self.move_head_down()

    async def move_back_stop(self) -> None:
        await self.move_head_stop()

    async def move_legs_up(self) -> None:
        await self._move_with_stop(self._build_command(self.profile.keys["foot_up"]))

    async def move_legs_down(self) -> None:
        await self._move_with_stop(self._build_command(self.profile.keys["foot_down"]))

    async def move_legs_stop(self) -> None:
        await self.move_head_stop()

    async def move_feet_up(self) -> None:
        await self._move_with_stop(self._build_command(self.profile.keys["foot_up"]))

    async def move_feet_down(self) -> None:
        await self._move_with_stop(self._build_command(self.profile.keys["foot_down"]))

    async def move_feet_stop(self) -> None:
        await self.move_head_stop()

    async def move_lumbar_up(self) -> None:
        await self._move_with_stop(self._build_command(self.profile.keys["lumbar_up"]))

    async def move_lumbar_down(self) -> None:
        await self._move_with_stop(self._build_command(self.profile.keys["lumbar_down"]))

    async def move_lumbar_stop(self) -> None:
        await self.move_head_stop()

    async def stop_all(self) -> None:
        await self._send_stop()

    # Preset methods
    async def preset_flat(self) -> None:
        await self._press(self.profile.keys["flat"])

    async def preset_memory(self, memory_num: int) -> None:
        """Go to memory preset."""
        commands = {
            1: self.profile.keys["memory_1"],
            2: self.profile.keys["memory_2"],
        }
        if (word := commands.get(memory_num)) is not None:
            await self._press(word)
        else:
            _LOGGER.warning("Invalid memory number %d (valid: 1-2)", memory_num)

    async def program_memory(self, memory_num: int) -> None:
        """Program current position to memory (not supported - use set commands)."""
        _LOGGER.warning(
            "OKIN 64-bit beds don't support programming memory presets directly. "
            "Memory positions are programmed by sending set commands at the desired position."
        )

    async def preset_zero_g(self) -> None:
        await self._press(self.profile.keys["zero_g"])

    async def preset_anti_snore(self) -> None:
        await self._press(self.profile.keys["anti_snore"])

    async def preset_tv(self) -> None:
        await self._press(self.profile.keys["tv_pc"])

    async def preset_lounge(self) -> None:
        await self._press(self.profile.keys["lounge"])

    # Light methods
    async def lights_on(self) -> None:
        await self._press(self.profile.keys["light_on"])

    async def lights_off(self) -> None:
        await self._press(self.profile.keys["light_off"])

    async def lights_toggle(self) -> None:
        await self._press(self.profile.keys["light_toggle"])

    # Massage methods
    async def massage_toggle(self) -> None:
        await self._press(self.profile.keys["massage_switch"])

    async def massage_head_up(self) -> None:
        await self._press(self.profile.keys["strength_up"])

    async def massage_head_down(self) -> None:
        await self._press(self.profile.keys["strength_down"])

    async def massage_mode_step(self) -> None:
        await self._press(self.profile.keys["wave_mode"])


async def build_controller(ctx: BuildContext) -> Okin64BitController:
    """Build the controller; Auto defaults to Nordic UART (fire-and-forget)."""
    variant = ctx.variant if ctx.variant and ctx.variant != "auto" else "nordic"
    _LOGGER.debug("Using OKIN 64-bit variant: %s", variant)
    return Okin64BitController(ctx.coordinator, variant=variant)
