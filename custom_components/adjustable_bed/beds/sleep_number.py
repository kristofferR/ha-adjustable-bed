"""Sleep Number Climate 360 / FlexFit controller.

This implements Select Comfort's Fuzion "bamkey" BLE protocol used by the
SleepIQ app. Commands are UTF-8 text sent to a single GATT characteristic and
responses arrive as notifications on that same characteristic.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from bleak.exc import BleakError

from ..const import (
    SLEEP_NUMBER_BAMKEY_CHAR_UUID,
    SLEEP_NUMBER_VARIANT_LEFT,
    SLEEP_NUMBER_VARIANT_RIGHT,
    VARIANT_AUTO,
)
from .base import BedController, MotorControlSpec

if TYPE_CHECKING:
    from ..coordinator import AdjustableBedCoordinator

_LOGGER = logging.getLogger(__name__)

_BAMKEY_RESPONSE_TIMEOUT = 7.5
_SLEEP_NUMBER_MIN_POSITION = 0
_SLEEP_NUMBER_MAX_POSITION = 100
_SLEEP_NUMBER_LIGHT_TIMER_OPTIONS = (0, 15, 30, 45, 60, 120, 180)
_SLEEP_NUMBER_DEFAULT_LIGHT_TIMER_MINUTES = 15
_SLEEP_NUMBER_LIGHT_LEVEL_TO_VALUE = {
    "off": 0,
    "low": 1,
    "medium": 2,
    "high": 3,
}
_SLEEP_NUMBER_LIGHT_VALUE_TO_LEVEL = {
    value: key for key, value in _SLEEP_NUMBER_LIGHT_LEVEL_TO_VALUE.items()
}


class SleepNumberCommands:
    """Fuzion bamkey command names used by Adjustable Bed support."""

    GET_ACTUATOR_POSITION = "ACTG"
    SET_ACTUATOR_TARGET_POSITION = "ACTS"
    HALT_ACTUATOR = "ACTH"
    HALT_ALL_ACTUATORS = "ACHA"
    SET_TARGET_PRESET = "ACSP"
    GET_BED_PRESENCE = "LBPG"
    GET_UNDERBED_LIGHT_SETTINGS = "UBLG"
    SET_UNDERBED_LIGHT_SETTINGS = "UBLS"


class SleepNumberPresets:
    """Fuzion articulation preset values used by the SleepIQ app."""

    FLAT = "flat"
    ZERO_G = "zero_g"
    ANTI_SNORE = "snore"
    TV = "watch_tv"


class SleepNumberController(BedController):
    """Controller for Sleep Number Climate 360 / FlexFit bases."""

    def __init__(
        self,
        coordinator: AdjustableBedCoordinator,
        *,
        side: str = VARIANT_AUTO,
    ) -> None:
        super().__init__(coordinator)
        self._notify_callback: Callable[[str, float], None] | None = None
        self._side = self._normalize_side(side)
        self._notify_started = False
        self._response_queue: asyncio.Queue[str] = asyncio.Queue()
        self._underbed_light_level: str | None = None
        self._underbed_light_timer_minutes: int | None = None
        self._underbed_light_last_active_level = "high"
        self._bed_presence_state: str | None = None

    @staticmethod
    def _normalize_side(side: str | None) -> str:
        """Normalize the configured side selection."""
        if side == SLEEP_NUMBER_VARIANT_RIGHT:
            return SLEEP_NUMBER_VARIANT_RIGHT
        return SLEEP_NUMBER_VARIANT_LEFT

    @property
    def control_characteristic_uuid(self) -> str:
        """Return the Fuzion BamKey characteristic UUID."""
        return SLEEP_NUMBER_BAMKEY_CHAR_UUID

    @property
    def supports_position_feedback(self) -> bool:
        """Sleep Number positions can be queried on demand."""
        return True

    @property
    def supports_direct_position_control(self) -> bool:
        """Sleep Number supports 0-100 target positions per actuator."""
        return True

    @property
    def supports_lights(self) -> bool:
        """Sleep Number exposes underbed light control."""
        return True

    @property
    def supports_under_bed_lights(self) -> bool:
        """Sleep Number exposes dedicated underbed light settings."""
        return True

    @property
    def supports_discrete_light_control(self) -> bool:
        """Sleep Number has explicit underbed light on/off states."""
        return True

    @property
    def supports_light_level_control(self) -> bool:
        """Sleep Number supports off/low/medium/high light levels."""
        return True

    @property
    def light_level_max(self) -> int:
        """Sleep Number exposes four discrete light levels."""
        return 3

    @property
    def supports_light_timer(self) -> bool:
        """Sleep Number exposes underbed light timers."""
        return True

    @property
    def light_timer_options(self) -> list[str]:
        """Return the SleepIQ underbed light timer options."""
        return [
            self._format_light_timer_option(minutes)
            for minutes in _SLEEP_NUMBER_LIGHT_TIMER_OPTIONS
        ]

    @property
    def light_auto_off_seconds(self) -> int | None:
        """Return the configured auto-off timeout when one is active."""
        if self._underbed_light_timer_minutes is None or self._underbed_light_timer_minutes <= 0:
            return None
        return self._underbed_light_timer_minutes * 60

    @property
    def supports_bed_presence(self) -> bool:
        """Sleep Number exposes side occupancy via LBPG."""
        return True

    @property
    def requires_notification_channel(self) -> bool:
        """Command acks and query responses arrive as notifications."""
        return True

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
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        """Expose the selected side as a two-axis bed."""
        return (
            MotorControlSpec(
                key="back",
                translation_key="back",
                open_fn=lambda ctrl: ctrl.move_back_up(),
                close_fn=lambda ctrl: ctrl.move_back_down(),
                stop_fn=lambda ctrl: ctrl.move_back_stop(),
                max_angle=100,
            ),
            MotorControlSpec(
                key="legs",
                translation_key="legs",
                open_fn=lambda ctrl: ctrl.move_legs_up(),
                close_fn=lambda ctrl: ctrl.move_legs_down(),
                stop_fn=lambda ctrl: ctrl.move_legs_stop(),
                max_angle=100,
            ),
        )

    def angle_to_native_position(self, motor: str, angle: float) -> int:  # noqa: ARG002
        """Convert direct-position values to Sleep Number's 0-100 native range."""
        return max(_SLEEP_NUMBER_MIN_POSITION, min(_SLEEP_NUMBER_MAX_POSITION, int(round(angle))))

    def get_light_state(self) -> dict[str, Any]:
        """Return the last known underbed light state."""
        state: dict[str, Any] = {}
        if self._underbed_light_level is not None:
            level_value = _SLEEP_NUMBER_LIGHT_LEVEL_TO_VALUE.get(self._underbed_light_level)
            state["is_on"] = self._underbed_light_level != "off"
            if level_value is not None:
                state["light_level"] = level_value
        if self._underbed_light_timer_minutes is not None:
            state["light_timer_minutes"] = self._underbed_light_timer_minutes
            state["light_timer_option"] = self._format_light_timer_option(
                self._underbed_light_timer_minutes
            )
        return state

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        """Subscribe to bamkey notifications used for responses."""
        self._notify_callback = callback

        if self._notify_started:
            return

        client = self.client
        if client is None or not client.is_connected:
            raise ConnectionError("Not connected to bed")

        await client.start_notify(
            SLEEP_NUMBER_BAMKEY_CHAR_UUID,
            self._handle_bamkey_notification,
        )
        self._notify_started = True

    async def stop_notify(self) -> None:
        """Unsubscribe from bamkey notifications."""
        self._notify_callback = None
        client = self.client
        if client is None or not client.is_connected or not self._notify_started:
            return

        try:
            await client.stop_notify(SLEEP_NUMBER_BAMKEY_CHAR_UUID)
        except BleakError:
            _LOGGER.debug("Failed to stop Sleep Number notifications", exc_info=True)
        finally:
            self._notify_started = False

    async def read_positions(self, motor_count: int = 2) -> None:  # noqa: ARG002
        """Read the current head and foot target positions for the selected side."""
        head_position = await self._read_actuator_position("head")
        foot_position = await self._read_actuator_position("foot")

        if self._notify_callback is not None:
            self._notify_callback("back", float(head_position))
            self._notify_callback("legs", float(foot_position))

    async def read_non_notifying_positions(self) -> None:
        """Sleep Number uses request/response reads rather than streaming positions."""
        await self.read_positions()

    async def set_motor_position(self, motor: str, position: int) -> None:
        """Set a motor target position on the selected side."""
        actuator = self._motor_to_actuator(motor)
        normalized = max(_SLEEP_NUMBER_MIN_POSITION, min(_SLEEP_NUMBER_MAX_POSITION, int(position)))
        await self._send_bamkey_command(
            SleepNumberCommands.SET_ACTUATOR_TARGET_POSITION,
            self._side,
            actuator,
            str(normalized),
        )

    async def _send_stop_for_motor(self, motor: str) -> None:
        """Stop a specific actuator on the selected side."""
        await self._send_bamkey_command(
            SleepNumberCommands.HALT_ACTUATOR,
            self._side,
            self._motor_to_actuator(motor),
        )

    async def move_head_up(self) -> None:
        await self.move_back_up()

    async def move_head_down(self) -> None:
        await self.move_back_down()

    async def move_head_stop(self) -> None:
        await self.move_back_stop()

    async def move_back_up(self) -> None:
        await self.set_motor_position("back", _SLEEP_NUMBER_MAX_POSITION)

    async def move_back_down(self) -> None:
        await self.set_motor_position("back", _SLEEP_NUMBER_MIN_POSITION)

    async def move_back_stop(self) -> None:
        await self._send_stop_for_motor("back")

    async def move_legs_up(self) -> None:
        await self.set_motor_position("legs", _SLEEP_NUMBER_MAX_POSITION)

    async def move_legs_down(self) -> None:
        await self.set_motor_position("legs", _SLEEP_NUMBER_MIN_POSITION)

    async def move_legs_stop(self) -> None:
        await self._send_stop_for_motor("legs")

    async def move_feet_up(self) -> None:
        await self.move_legs_up()

    async def move_feet_down(self) -> None:
        await self.move_legs_down()

    async def move_feet_stop(self) -> None:
        await self.move_legs_stop()

    async def stop_all(self) -> None:
        await self._send_bamkey_command(SleepNumberCommands.HALT_ALL_ACTUATORS)

    async def lights_on(self) -> None:
        """Turn on the underbed light using the last active or default level."""
        target_level = self._underbed_light_last_active_level
        if target_level == "off":
            target_level = "high"
        await self._apply_underbed_light_settings(level=target_level)

    async def lights_off(self) -> None:
        """Turn off the underbed light while preserving the timer selection."""
        await self._apply_underbed_light_settings(level="off")

    async def set_light_level(self, level: int) -> None:
        """Set the Sleep Number underbed light level."""
        normalized = max(0, min(self.light_level_max, int(level)))
        await self._apply_underbed_light_settings(
            level=_SLEEP_NUMBER_LIGHT_VALUE_TO_LEVEL[normalized]
        )

    async def set_light_timer(self, timer_option: str) -> None:
        """Set the Sleep Number underbed light auto-off timer."""
        await self._apply_underbed_light_settings(
            timer_minutes=self._parse_light_timer_option(timer_option)
        )

    async def read_bed_presence(self) -> bool | None:
        """Read occupancy state for the configured bed side."""
        response = await self._send_bamkey_command(
            SleepNumberCommands.GET_BED_PRESENCE,
            self._side,
            expected_args=1,
        )
        presence = self._normalize_bed_presence(response[0])
        self._bed_presence_state = presence
        self.forward_controller_state_updates(
            {
                "bed_presence": presence,
                "bed_presence_side": self._side,
            }
        )
        if presence == "in":
            return True
        if presence == "out":
            return False
        return None

    async def preset_flat(self) -> None:
        await self._send_preset(SleepNumberPresets.FLAT)

    async def preset_zero_g(self) -> None:
        await self._send_preset(SleepNumberPresets.ZERO_G)

    async def preset_anti_snore(self) -> None:
        await self._send_preset(SleepNumberPresets.ANTI_SNORE)

    async def preset_tv(self) -> None:
        await self._send_preset(SleepNumberPresets.TV)

    async def preset_memory(self, memory_num: int) -> None:
        """Sleep Number does not expose numbered memory slots via this integration."""
        raise NotImplementedError(
            f"Sleep Number controller does not support memory slot {memory_num}"
        )

    async def program_memory(self, memory_num: int) -> None:
        """Sleep Number preset programming is not exposed as generic memory slots."""
        raise NotImplementedError(
            f"Sleep Number controller does not support programming memory slot {memory_num}"
        )

    async def _send_preset(self, preset: str) -> None:
        """Send a Fuzion articulation preset with timer=0."""
        await self._send_bamkey_command(
            SleepNumberCommands.SET_TARGET_PRESET,
            self._side,
            preset,
            "0",
        )

    async def _read_actuator_position(self, actuator: str) -> int:
        """Read an actuator position from the selected side."""
        response = await self._send_bamkey_command(
            SleepNumberCommands.GET_ACTUATOR_POSITION,
            self._side,
            actuator,
            expected_args=1,
        )
        return max(
            _SLEEP_NUMBER_MIN_POSITION,
            min(_SLEEP_NUMBER_MAX_POSITION, int(response[0])),
        )

    async def _read_underbed_light_settings(self) -> tuple[str, int]:
        """Read the current underbed light level and timer."""
        response = await self._send_bamkey_command(
            SleepNumberCommands.GET_UNDERBED_LIGHT_SETTINGS,
            expected_args=2,
        )
        level = self._normalize_underbed_light_level(response[0])
        timer_minutes = max(0, int(response[1]))
        self._store_underbed_light_state(level, timer_minutes)
        return level, timer_minutes

    async def _ensure_underbed_light_settings_loaded(self) -> None:
        """Load underbed light settings once before mutating them."""
        if self._underbed_light_level is None or self._underbed_light_timer_minutes is None:
            await self._read_underbed_light_settings()

    async def _apply_underbed_light_settings(
        self,
        *,
        level: str | None = None,
        timer_minutes: int | None = None,
    ) -> None:
        """Apply underbed light settings while preserving the untouched field."""
        await self._ensure_underbed_light_settings_loaded()

        resolved_level = level or self._underbed_light_level or "off"
        resolved_timer = (
            timer_minutes if timer_minutes is not None else self._underbed_light_timer_minutes
        )
        if resolved_timer is None:
            resolved_timer = _SLEEP_NUMBER_DEFAULT_LIGHT_TIMER_MINUTES

        await self._send_bamkey_command(
            SleepNumberCommands.SET_UNDERBED_LIGHT_SETTINGS,
            resolved_level,
            str(resolved_timer),
        )
        self._store_underbed_light_state(resolved_level, resolved_timer)

    def _store_underbed_light_state(self, level: str, timer_minutes: int) -> None:
        """Persist and publish the latest underbed light state."""
        self._underbed_light_level = level
        self._underbed_light_timer_minutes = timer_minutes
        if level != "off":
            self._underbed_light_last_active_level = level

        self.forward_controller_state_updates(
            {
                "under_bed_lights_on": level != "off",
                "light_level": _SLEEP_NUMBER_LIGHT_LEVEL_TO_VALUE.get(level),
                "light_timer_minutes": timer_minutes,
                "light_timer_option": self._format_light_timer_option(timer_minutes),
            }
        )

    async def _ensure_notifications_started(self) -> None:
        """Ensure the bamkey response channel is subscribed."""
        if not self._notify_started:
            await self.start_notify(self._notify_callback)

    async def _send_bamkey_command(
        self,
        bamkey: str,
        *args: str,
        expected_args: int = 0,
    ) -> list[str]:
        """Send a bamkey command and parse the matching response."""
        await self._ensure_notifications_started()
        self._drain_response_queue()

        payload = bamkey if not args else f"{bamkey} {' '.join(args)}"
        await self._write_gatt_with_retry(
            SLEEP_NUMBER_BAMKEY_CHAR_UUID,
            payload.encode("utf-8"),
            response=True,
        )

        raw_response = await asyncio.wait_for(
            self._response_queue.get(),
            timeout=_BAMKEY_RESPONSE_TIMEOUT,
        )
        return self._parse_bamkey_response(bamkey, raw_response, expected_args)

    def _drain_response_queue(self) -> None:
        """Discard stale bamkey responses before sending a new command."""
        while not self._response_queue.empty():
            self._response_queue.get_nowait()

    def _parse_bamkey_response(
        self,
        bamkey: str,
        raw_response: str,
        expected_args: int,
    ) -> list[str]:
        """Parse PASS:/FAIL: bamkey responses into argument lists."""
        response = raw_response.strip()

        if response.startswith("PASS:ACK"):
            payload = ""
        elif response.startswith("PASS:"):
            payload = response.removeprefix("PASS:").strip()
        elif response.startswith("FAIL:0"):
            raise ValueError(f"{bamkey} failed: unknown bamkey")
        elif response.startswith("FAIL:1"):
            raise TimeoutError(f"{bamkey} failed: device timeout")
        elif response.startswith("FAIL:2"):
            raise ValueError(f"{bamkey} failed: generic protocol error")
        else:
            raise ValueError(f"{bamkey} returned unknown response: {response}")

        if expected_args == 0:
            return []
        if expected_args == 1:
            if not payload:
                raise ValueError(f"{bamkey} returned no payload")
            return [payload]

        parts = [part for part in payload.split(" ") if part]
        if len(parts) != expected_args:
            raise ValueError(
                f"{bamkey} returned {len(parts)} values, expected {expected_args}: {response}"
            )
        return parts

    def _handle_bamkey_notification(self, _sender: object, data: bytearray) -> None:
        """Decode bamkey notifications into the response queue."""
        raw = bytes(data)
        self.forward_raw_notification(SLEEP_NUMBER_BAMKEY_CHAR_UUID, raw)

        decoded = raw.decode("utf-8", errors="ignore").strip()
        if not decoded:
            return

        self._response_queue.put_nowait(decoded)

    @staticmethod
    def _motor_to_actuator(motor: str) -> str:
        """Map integration motor keys to Fuzion actuator names."""
        normalized = motor.lower()
        if normalized in {"back", "head"}:
            return "head"
        if normalized in {"legs", "feet"}:
            return "foot"
        raise ValueError(f"Unsupported Sleep Number motor: {motor}")

    @staticmethod
    def _normalize_bed_presence(value: str) -> str:
        """Normalize LBPG responses to in/out/unknown."""
        normalized = value.strip().lower()
        if normalized in {"in", "out", "unknown"}:
            return normalized
        raise ValueError(f"Unsupported Sleep Number bed presence value: {value}")

    @staticmethod
    def _normalize_underbed_light_level(value: str) -> str:
        """Normalize UBLG/UBLS level values."""
        normalized = value.strip().lower()
        if normalized in _SLEEP_NUMBER_LIGHT_LEVEL_TO_VALUE:
            return normalized
        raise ValueError(f"Unsupported Sleep Number light level: {value}")

    @staticmethod
    def _format_light_timer_option(minutes: int) -> str:
        """Format a timer value in minutes for Home Assistant select entities."""
        if minutes <= 0:
            return "Off"
        if minutes == 60:
            return "1 hr"
        if minutes == 120:
            return "2 hr"
        if minutes == 180:
            return "3 hr"
        return f"{minutes} min"

    @staticmethod
    def _parse_light_timer_option(timer_option: str) -> int:
        """Parse a Home Assistant light timer option into minutes."""
        normalized = timer_option.strip().lower()
        if normalized == "off":
            return 0
        option_map = {
            "15 min": 15,
            "30 min": 30,
            "45 min": 45,
            "1 hr": 60,
            "2 hr": 120,
            "3 hr": 180,
        }
        if normalized in option_map:
            return option_map[normalized]
        raise ValueError(f"Unsupported Sleep Number light timer option: {timer_option}")
