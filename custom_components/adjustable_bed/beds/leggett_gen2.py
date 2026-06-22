"""Leggett & Platt Gen2 bed controller implementation.

Also known as the Leggett & Platt "LP Comfort Connect" controller (control box
209-M001, an ESP32-WROOM-32D board). Originally reverse-engineered by MarcusW
and Richard Hopton (smartbed-mqtt); the motor command format and detection here
were corrected from a decompile of the LP Control app
(com.leggett.android.universal) — see docs/beds/leggett-platt.md.

This controller handles Leggett & Platt beds using the Gen2 (Richmat-based) ASCII protocol.

Protocol details:
    Service UUID: 45e25100-3171-4cfc-ae89-1d83cf8d8071
    Write characteristic: 45e25101-3171-4cfc-ae89-1d83cf8d8071
    Read characteristic: 45e25103-3171-4cfc-ae89-1d83cf8d8071
    Command format: ASCII text (e.g., b"MEM 0" for flat preset; motor moves use
        "M {down}:{up}:{stop}").

Connection note:
    The ESP32 controller only accepts a BLE connection while the bed is in
    pairing mode and refuses reconnection afterwards, so this bed type uses a
    persistent connection (it is never idle-disconnected). See
    coordinator._uses_persistent_connection().

Features (gated per model by the bundled capability profile — see
leggett_gen2_profiles; the bed does not report its feature set over BLE):
    - Motor control (head/back, feet, and pillow/lumbar where present) via "M"
    - Position presets (Flat, Unwind, Sleep, Wake Up, Relax, Anti-Snore)
    - Memory position programming (slot count per model, typically 3)
    - Under-bed lighting: none / on-off toggle / single-colour / RGB per model,
      with live on/off + colour state from 45e25103 notifications
    - Massage control with adjustable strength
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import TYPE_CHECKING, Any

from ..const import LEGGETT_GEN2_READ_CHAR_UUID, LEGGETT_GEN2_WRITE_CHAR_UUID
from .base import BedController
from .leggett_gen2_profiles import (
    Gen2Capabilities,
    capabilities_for_product,
    compute_product_id,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from ..coordinator import AdjustableBedCoordinator

_LOGGER = logging.getLogger(__name__)


class LeggettGen2Commands:
    """Leggett & Platt Gen2 ASCII commands."""

    # Presets
    PRESET_FLAT = b"MEM 0"
    PRESET_UNWIND = b"MEM 1"
    PRESET_SLEEP = b"MEM 2"
    PRESET_WAKE_UP = b"MEM 3"
    PRESET_RELAX = b"MEM 4"
    PRESET_ANTI_SNORE = b"SNR"

    # Programming
    PROGRAM_UNWIND = b"SMEM 1"
    PROGRAM_SLEEP = b"SMEM 2"
    PROGRAM_WAKE_UP = b"SMEM 3"
    PROGRAM_RELAX = b"SMEM 4"
    # (Gen2 has no anti-snore *program* command; SNPOS is not a Gen2 command.)

    # Control
    STOP = b"STOP"
    GET_STATE = b"GET STATE"

    # Lighting (under-bed light, LightID 0). The LP Control app has NO "RGBENABLE"
    # command (the previous off/toggle command was invalid). The confirmed GEN2
    # light commands are:
    #   UBL TOGGLE            - toggle the under-bed light on/off (the only on/off
    #                           primitive; the app has no separate on/off command)
    #   RGBSET 0:RRGGBBAA     - set colour (8 hex: red, green, blue, alpha/brightness)
    #   RGBBRT 0:AA           - set brightness (2 hex)
    # Source: com.leggett.android.universal Gen2BedControlBoxInterface.
    # On/off is the toggle; the live light state (on/off + colour) is read back from
    # the 45e25103 STATE frame (see _handle_state_notification), so Home Assistant
    # knows the current state and the toggle resolves to the intended on/off.
    LIGHT_TOGGLE = b"UBL TOGGLE"

    @staticmethod
    def rgb_set(red: int, green: int, blue: int, alpha: int = 0xFF) -> bytes:
        """Create an RGBSET colour command (``RGBSET 0:RRGGBBAA``)."""
        hex_str = f"{red:02X}{green:02X}{blue:02X}{alpha:02X}"
        return f"RGBSET 0:{hex_str}".encode()

    @staticmethod
    def brightness_set(level: int) -> bytes:
        """Create an RGBBRT brightness command (``RGBBRT 0:AA``, level 0-255)."""
        return f"RGBBRT 0:{max(0, min(255, level)):02X}".encode()

    # Massage. Gen2 intensity is RELATIVE: "VII :<ch>" raises and "VII <ch>::"
    # lowers the given channel (0=primary head, 1=primary foot). Absolute set uses
    # "MVI <ch>:<level>" with level 0=off, 1=low, 2=med, 3=high (used for "off").
    # Mode is "MMODE <group>:<mode>" (group 0=primary; mode 0=wave, 1=pulse,
    # 2=always-on); wave speed is "WSP <group>:<speed>" (0=slow, 1=med, 2=fast);
    # "WVE TOGGLE" toggles wave. Source: Gen2BedControlBoxInterface/Gen2CommandFormatter.
    MASSAGE_HEAD_UP = b"VII :0"
    MASSAGE_HEAD_DOWN = b"VII 0::"
    MASSAGE_FOOT_UP = b"VII :1"
    MASSAGE_FOOT_DOWN = b"VII 1::"
    WAVE_TOGGLE = b"WVE TOGGLE"

    @staticmethod
    def massage_set(channel: int, level: int) -> bytes:
        """Set absolute massage intensity (``MVI <channel>:<level>``, level 0-3)."""
        return f"MVI {channel}:{max(0, min(3, level))}".encode()

    @staticmethod
    def wave_speed(speed: int) -> bytes:
        """Set primary wave speed (``WSP 0:<speed>``, 0=slow, 1=med, 2=fast)."""
        return f"WSP 0:{max(0, min(2, speed))}".encode()

    # Motor control: the LP Control app formats motor commands as
    #   M {down_codes}:{up_codes}:{stop_codes}
    # with the actuator code in exactly ONE of the three colon-separated fields
    # (the others empty), and no trailing stop list. Actuator codes:
    #   0=head, 1=feet, 2=pillow, 3=lumbar.
    # Examples (from com.leggett.android.universal Gen2CommandFormatter):
    #   head up = "M :0:", head down = "M 0::", stop head = "M ::0".
    # Source: APK reverse engineering (replaces the earlier smartbed-mqtt guess,
    # which had up/down swapped and appended a stop list).
    @staticmethod
    def motor_move(down: str = "", up: str = "", stop: str = "") -> bytes:
        """Build a motor move/stop command (``M {down}:{up}:{stop}``)."""
        return f"M {down}:{up}:{stop}".encode()

    MOTOR_HEAD_UP = b"M :0:"
    MOTOR_HEAD_DOWN = b"M 0::"
    MOTOR_HEAD_STOP = b"M ::0"
    MOTOR_FEET_UP = b"M :1:"
    MOTOR_FEET_DOWN = b"M 1::"
    MOTOR_FEET_STOP = b"M ::1"
    MOTOR_PILLOW_UP = b"M :2:"
    MOTOR_PILLOW_DOWN = b"M 2::"
    MOTOR_PILLOW_STOP = b"M ::2"
    MOTOR_LUMBAR_UP = b"M :3:"
    MOTOR_LUMBAR_DOWN = b"M 3::"
    MOTOR_LUMBAR_STOP = b"M ::3"
    # The app uses the plain "STOP" string to halt all actuators.
    MOTOR_STOP_ALL = b"STOP"


class LeggettGen2Controller(BedController):
    """Controller for Leggett & Platt Gen2 beds.

    These beds use ASCII commands over BLE for preset control, lighting, and massage.
    They do not support direct motor control (uses position-based control instead).
    """

    def __init__(
        self,
        coordinator: AdjustableBedCoordinator,
        manufacturer_data: Mapping[int, bytes] | None = None,
    ) -> None:
        """Initialize the Leggett & Platt Gen2 controller.

        The bed's feature set is not reported over BLE; it is looked up from the
        bundled per-model profile keyed by a productId derived from the
        advertisement manufacturer data (see leggett_gen2_profiles).
        """
        super().__init__(coordinator)
        product_id = compute_product_id(manufacturer_data)
        self._caps: Gen2Capabilities = capabilities_for_product(product_id)
        # Live under-bed light on/off, populated from 45e25103 STATE notifications.
        self._light_on: bool | None = None
        self._light_rgb: tuple[int, int, int] | None = None
        self._notify_started = False
        _LOGGER.debug(
            "LeggettGen2Controller initialized (product_id=%s, caps=%s)",
            product_id,
            self._caps,
        )

    @property
    def control_characteristic_uuid(self) -> str:
        """Return the UUID of the control characteristic."""
        return LEGGETT_GEN2_WRITE_CHAR_UUID

    @property
    def requires_persistent_connection(self) -> bool:
        """LP Comfort Connect's ESP32 only accepts a connection while in pairing
        mode and refuses reconnection afterwards, so the link must be held open."""
        return True

    @property
    def requires_notification_channel(self) -> bool:
        """Subscribe to STATE notifications even with angle sensing disabled, so we
        receive live under-bed light on/off + colour state from the bed."""
        return self._caps.light != "none"

    # Capability properties
    @property
    def supports_preset_zero_g(self) -> bool:
        return False  # Gen2 doesn't support Zero G

    @property
    def supports_preset_anti_snore(self) -> bool:
        return True

    @property
    def supports_lights(self) -> bool:
        """Return True when this model has an under-bed light (per profile)."""
        return self._caps.light != "none"

    @property
    def supports_discrete_light_control(self) -> bool:
        """Return True for any model with a light (on/off via RGBSET/UBL)."""
        return self._caps.light != "none"

    @property
    def supports_light_color_control(self) -> bool:
        """Return True only for RGB (multi-colour) under-bed lights."""
        return self._caps.light == "rgb"

    @property
    def supports_explicit_light_on_control(self) -> bool:
        """Return False - the only confirmed on/off primitive is UBL TOGGLE, so we
        don't issue a separate explicit "on"; setting a colour turns RGB lights on."""
        return False

    @property
    def default_light_rgb_color(self) -> tuple[int, int, int] | None:
        """Return default white color for RGB lights."""
        return (255, 255, 255) if self._caps.light == "rgb" else None

    @property
    def supports_memory_presets(self) -> bool:
        """Return True when the model exposes memory positions (per profile)."""
        return self._caps.memory_slots > 0

    @property
    def supports_motor_control(self) -> bool:
        """Return True when the model has at least one actuator."""
        return (
            self._caps.has_head
            or self._caps.has_foot
            or self._caps.has_pillow
            or self._caps.has_lumbar
        )

    @property
    def has_pillow_support(self) -> bool:
        """Return True when the model has a pillow actuator (per profile)."""
        return self._caps.has_pillow

    @property
    def has_lumbar_support(self) -> bool:
        """Return True when the model has a lumbar actuator (per profile)."""
        return self._caps.has_lumbar

    @property
    def memory_slot_count(self) -> int:
        """Return the model's memory slot count (per profile; typically 3)."""
        return self._caps.memory_slots

    @property
    def supports_memory_programming(self) -> bool:
        """Return True when the model exposes memory positions (per profile)."""
        return self._caps.memory_slots > 0

    # The base capability helpers detect overridden methods, so they would report
    # massage/light controls for every Gen2 bed. Gate them on the profile so models
    # without massage or an under-bed light don't get phantom entities.
    @property
    def supports_under_bed_lights(self) -> bool:
        return self._caps.light != "none"

    @property
    def supports_light_toggle_control(self) -> bool:
        return self._caps.light != "none"

    @property
    def supports_massage_off_control(self) -> bool:
        return self._caps.has_massage

    @property
    def supports_massage_toggle_control(self) -> bool:
        return self._caps.has_massage

    @property
    def supports_massage_intensity_step_control(self) -> bool:
        return self._caps.has_massage

    @property
    def supports_massage_mode_step_control(self) -> bool:
        return self._caps.has_massage

    @property
    def motor_control_specs(self) -> tuple:
        """Expose only the primary actuators the model actually has (per profile)."""
        present = {
            "back": self._caps.has_head,
            "legs": self._caps.has_foot,
            "pillow": self._caps.has_pillow,
            "lumbar": self._caps.has_lumbar,
        }
        return tuple(
            spec
            for spec in super().motor_control_specs
            if present.get(spec.key, True)
        )

    # Motor control methods - Gen2 re-sends the move command every 200 ms while
    # held and sends an explicit per-actuator stop on release (matching the app).
    async def _move_with_stop(
        self, command: bytes, stop_command: bytes = LeggettGen2Commands.MOTOR_STOP_ALL
    ) -> None:
        """Execute a movement command and always send a stop at the end."""
        try:
            await self.write_command(command, repeat_count=25, repeat_delay_ms=200)
        finally:
            try:
                await self.write_command(stop_command, cancel_event=asyncio.Event())
            except Exception:
                _LOGGER.debug("Failed to send stop during motor cleanup")

    async def _stop(self, stop_command: bytes) -> None:
        """Send a stop command (per-actuator or stop-all)."""
        await self.write_command(stop_command, cancel_event=asyncio.Event())

    async def move_head_up(self) -> None:
        """Move head up."""
        await self._move_with_stop(
            LeggettGen2Commands.MOTOR_HEAD_UP, LeggettGen2Commands.MOTOR_HEAD_STOP
        )

    async def move_head_down(self) -> None:
        """Move head down."""
        await self._move_with_stop(
            LeggettGen2Commands.MOTOR_HEAD_DOWN, LeggettGen2Commands.MOTOR_HEAD_STOP
        )

    async def move_head_stop(self) -> None:
        """Stop head motor."""
        await self._stop(LeggettGen2Commands.MOTOR_HEAD_STOP)

    async def move_back_up(self) -> None:
        """Move back up (same as head)."""
        await self.move_head_up()

    async def move_back_down(self) -> None:
        """Move back down (same as head)."""
        await self.move_head_down()

    async def move_back_stop(self) -> None:
        """Stop back motor."""
        await self.move_head_stop()

    async def move_legs_up(self) -> None:
        """Move legs up."""
        await self._move_with_stop(
            LeggettGen2Commands.MOTOR_FEET_UP, LeggettGen2Commands.MOTOR_FEET_STOP
        )

    async def move_legs_down(self) -> None:
        """Move legs down."""
        await self._move_with_stop(
            LeggettGen2Commands.MOTOR_FEET_DOWN, LeggettGen2Commands.MOTOR_FEET_STOP
        )

    async def move_legs_stop(self) -> None:
        """Stop legs motor."""
        await self._stop(LeggettGen2Commands.MOTOR_FEET_STOP)

    async def move_feet_up(self) -> None:
        """Move feet up."""
        await self.move_legs_up()

    async def move_feet_down(self) -> None:
        """Move feet down."""
        await self.move_legs_down()

    async def move_feet_stop(self) -> None:
        """Stop feet motor."""
        await self.move_legs_stop()

    async def move_pillow_up(self) -> None:
        """Move pillow up."""
        await self._move_with_stop(
            LeggettGen2Commands.MOTOR_PILLOW_UP, LeggettGen2Commands.MOTOR_PILLOW_STOP
        )

    async def move_pillow_down(self) -> None:
        """Move pillow down."""
        await self._move_with_stop(
            LeggettGen2Commands.MOTOR_PILLOW_DOWN, LeggettGen2Commands.MOTOR_PILLOW_STOP
        )

    async def move_pillow_stop(self) -> None:
        """Stop pillow motor."""
        await self._stop(LeggettGen2Commands.MOTOR_PILLOW_STOP)

    async def move_lumbar_up(self) -> None:
        """Move lumbar up."""
        await self._move_with_stop(
            LeggettGen2Commands.MOTOR_LUMBAR_UP, LeggettGen2Commands.MOTOR_LUMBAR_STOP
        )

    async def move_lumbar_down(self) -> None:
        """Move lumbar down."""
        await self._move_with_stop(
            LeggettGen2Commands.MOTOR_LUMBAR_DOWN, LeggettGen2Commands.MOTOR_LUMBAR_STOP
        )

    async def move_lumbar_stop(self) -> None:
        """Stop lumbar motor."""
        await self._stop(LeggettGen2Commands.MOTOR_LUMBAR_STOP)

    async def stop_all(self) -> None:
        """Stop all motors."""
        await self._stop(LeggettGen2Commands.MOTOR_STOP_ALL)

    # Preset methods
    async def preset_flat(self) -> None:
        """Go to flat position."""
        try:
            await self.write_command(
                LeggettGen2Commands.PRESET_FLAT,
                repeat_count=100,
                repeat_delay_ms=300,
            )
        finally:
            try:
                await self.write_command(
                    LeggettGen2Commands.STOP,
                    cancel_event=asyncio.Event(),
                )
            except Exception:
                _LOGGER.debug("Failed to send STOP command during preset_flat cleanup")

    async def preset_memory(self, memory_num: int) -> None:
        """Go to memory preset."""
        commands = {
            1: LeggettGen2Commands.PRESET_UNWIND,
            2: LeggettGen2Commands.PRESET_SLEEP,
            3: LeggettGen2Commands.PRESET_WAKE_UP,
            4: LeggettGen2Commands.PRESET_RELAX,
        }
        if command := commands.get(memory_num):
            try:
                await self.write_command(command, repeat_count=100, repeat_delay_ms=300)
            finally:
                try:
                    await self.write_command(
                        LeggettGen2Commands.STOP,
                        cancel_event=asyncio.Event(),
                    )
                except Exception:
                    _LOGGER.debug("Failed to send STOP command during preset_memory cleanup")

    async def program_memory(self, memory_num: int) -> None:
        """Program current position to memory."""
        commands = {
            1: LeggettGen2Commands.PROGRAM_UNWIND,
            2: LeggettGen2Commands.PROGRAM_SLEEP,
            3: LeggettGen2Commands.PROGRAM_WAKE_UP,
            4: LeggettGen2Commands.PROGRAM_RELAX,
        }
        if command := commands.get(memory_num):
            await self.write_command(command)

    async def preset_zero_g(self) -> None:
        """Go to zero gravity position (not supported on Gen2)."""
        _LOGGER.warning("Zero-G preset not available on Gen2 beds")

    async def preset_anti_snore(self) -> None:
        """Go to anti-snore position."""
        try:
            await self.write_command(
                LeggettGen2Commands.PRESET_ANTI_SNORE,
                repeat_count=100,
                repeat_delay_ms=300,
            )
        finally:
            try:
                await self.write_command(
                    LeggettGen2Commands.STOP,
                    cancel_event=asyncio.Event(),
                )
            except Exception:
                _LOGGER.debug("Failed to send STOP command during preset_anti_snore cleanup")

    # Light methods. The app toggles with "UBL TOGGLE" and turns the light off by
    # setting the colour to 0 (RGBSET 0:00000000); a non-zero colour turns it on.
    async def lights_toggle(self) -> None:
        """Toggle the under-bed light."""
        await self.write_command(LeggettGen2Commands.LIGHT_TOGGLE)

    async def lights_on(self) -> None:
        """Turn on the under-bed light (idempotent against the live state).

        The only on/off primitive is the toggle, so we toggle only when the
        bed-reported state (from STATE notifications) says the light is not already
        on, to avoid inverting it on stale assumed state.
        """
        if self._light_on is True:
            return
        await self.write_command(LeggettGen2Commands.LIGHT_TOGGLE)

    async def lights_off(self) -> None:
        """Turn off the under-bed light (idempotent against the live state)."""
        if self._light_on is False:
            return
        await self.write_command(LeggettGen2Commands.LIGHT_TOGGLE)

    async def set_light_color(self, rgb_color: tuple[int, int, int]) -> None:
        """Set the under-bed light colour using the RGBSET command."""
        r, g, b = rgb_color
        if not all(0 <= v <= 255 for v in (r, g, b)):
            raise ValueError(f"RGB values must be 0-255, got {rgb_color}")
        await self.write_command(LeggettGen2Commands.rgb_set(r, g, b))

    # ---- Live light state from 45e25103 STATE notifications -----------------
    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        """Subscribe to the STATE characteristic for live light on/off + colour.

        The position callback is unused (Gen2 reports no motor angle); we parse the
        under-bed light state ourselves and publish it as controller state.
        """
        client = self.client
        if client is None or not client.is_connected:
            raise ConnectionError("Not connected to bed")
        if not self._notify_started:
            async with self._ble_lock:
                await client.start_notify(
                    LEGGETT_GEN2_READ_CHAR_UUID, self._handle_state_notification
                )
            self._notify_started = True
            _LOGGER.debug("Started Gen2 STATE notifications for %s", self._coordinator.address)

    async def stop_notify(self) -> None:
        """Unsubscribe from the STATE characteristic."""
        client = self.client
        if client is not None and client.is_connected and self._notify_started:
            with contextlib.suppress(Exception):
                async with self._ble_lock:
                    await client.stop_notify(LEGGETT_GEN2_READ_CHAR_UUID)
        self._notify_started = False

    def _handle_state_notification(self, _sender: Any, data: bytearray) -> None:
        """Parse a Gen2 STATE frame for the under-bed light state.

        Per the app's StateChangeParser: byte 6 is the light OperatingMode
        (0x01 = constant-colour/on, 0x04 = off) and bytes 7-9 are R, G, B (byte 10
        is alpha). Other frame types leave byte 6 outside {0x01, 0x04} and are
        ignored here.
        """
        self.forward_raw_notification(LEGGETT_GEN2_READ_CHAR_UUID, bytes(data))
        if len(data) <= 10:
            return
        mode = data[6]
        updates: dict[str, Any] = {}
        if mode == 0x01:
            light_on = True
            rgb = (data[7], data[8], data[9])
            if rgb != self._light_rgb:
                self._light_rgb = rgb
                updates["under_bed_lights_rgb"] = rgb
        elif mode == 0x04:
            light_on = False
        else:
            return
        if light_on != self._light_on:
            self._light_on = light_on
            updates["under_bed_lights_on"] = light_on
        if updates:
            self.forward_controller_state_updates(updates)

    # Massage methods. Gen2 intensity is relative (VII raise/lower), so no level is
    # tracked locally. "Off" sets all four channels to 0 (matching the app's
    # stopMassage(ALL)).
    async def massage_off(self) -> None:
        """Turn off massage (set every channel's intensity to 0)."""
        for channel in (0, 1, 2, 3):
            await self.write_command(LeggettGen2Commands.massage_set(channel, 0))

    async def massage_head_up(self) -> None:
        """Increase head massage intensity (relative)."""
        await self.write_command(LeggettGen2Commands.MASSAGE_HEAD_UP)

    async def massage_head_down(self) -> None:
        """Decrease head massage intensity (relative)."""
        await self.write_command(LeggettGen2Commands.MASSAGE_HEAD_DOWN)

    async def massage_foot_up(self) -> None:
        """Increase foot massage intensity (relative)."""
        await self.write_command(LeggettGen2Commands.MASSAGE_FOOT_UP)

    async def massage_foot_down(self) -> None:
        """Decrease foot massage intensity (relative)."""
        await self.write_command(LeggettGen2Commands.MASSAGE_FOOT_DOWN)

    async def massage_toggle(self) -> None:
        """Toggle the wave massage mode (the only Gen2 massage toggle)."""
        await self.write_command(LeggettGen2Commands.WAVE_TOGGLE)
