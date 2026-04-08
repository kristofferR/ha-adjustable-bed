"""Sleep Number Climate 360 / FlexFit controller.

This implements Select Comfort's Fuzion "bamkey" BLE protocol used by the
SleepIQ app. Commands are UTF-8 text wrapped in the app's `fUzIoN` blob framing
and sent to the BamKey characteristic. Some beds deliver full framed responses
as notifications, while others use notifications as a readback trigger, so the
controller supports both patterns.
"""

from __future__ import annotations

import asyncio
import binascii
import contextlib
import json
import logging
import struct
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from bleak.exc import BleakError

from ..const import (
    SLEEP_NUMBER_AUTH_CHAR_UUID,
    SLEEP_NUMBER_BAMKEY_CHAR_UUID,
    SLEEP_NUMBER_BULK_TRANSFER_CHAR_UUID,
    SLEEP_NUMBER_TRANSFER_INFO_CHAR_UUID,
    SLEEP_NUMBER_VARIANT_LEFT,
    SLEEP_NUMBER_VARIANT_RIGHT,
    VARIANT_AUTO,
)
from .base import BedController, MotorControlSpec

if TYPE_CHECKING:
    from ..coordinator import AdjustableBedCoordinator

_LOGGER = logging.getLogger(__name__)

_BAMKEY_RESPONSE_TIMEOUT = 7.5
_BAMKEY_BLOB_PREAMBLE = b"fUzIoN"
_BAMKEY_BLOB_HEADER_LENGTH = len(_BAMKEY_BLOB_PREAMBLE) + 4
_BAMKEY_BLOB_MIN_LENGTH = _BAMKEY_BLOB_HEADER_LENGTH + 4
_BAMKEY_READBACK_TRIGGER_DELAY = 0.05
_SLEEP_NUMBER_MIN_POSITION = 0
_SLEEP_NUMBER_MAX_POSITION = 100
_SLEEP_NUMBER_SLEEP_SETTING_MIN = 5
_SLEEP_NUMBER_SLEEP_SETTING_MAX = 100
_SLEEP_NUMBER_SLEEP_SETTING_STEP = 5
_SLEEP_NUMBER_LIGHT_TIMER_OPTIONS = (0, 15, 30, 45, 60, 120, 180)
_SLEEP_NUMBER_DEFAULT_LIGHT_TIMER_MINUTES = 15
# Thermal timer options match the SleepIQ app's FuzionCoolingCapability and
# FuzionCoreTemperatureCapability: 30 min through 10 hours.
_SLEEP_NUMBER_THERMAL_TIMER_OPTIONS = (30, 60, 120, 180, 240, 300, 360, 420, 480, 540, 600)
# Footwarming caps at 6 hours per the SleepIQ app's FuzionFootwarmingCapability.
_SLEEP_NUMBER_FOOTWARMING_TIMER_OPTIONS = (30, 60, 120, 180, 240, 300, 360)
_SLEEP_NUMBER_DEFAULT_THERMAL_TIMER_MINUTES = 120
_SLEEP_NUMBER_BED_PRESENCE_QUERY_SIDES = (
    SLEEP_NUMBER_VARIANT_LEFT,
    SLEEP_NUMBER_VARIANT_RIGHT,
)
_SLEEP_NUMBER_LIGHT_LEVEL_TO_VALUE = {
    "off": 0,
    "low": 1,
    "medium": 2,
    "high": 3,
}
_SLEEP_NUMBER_LIGHT_VALUE_TO_LEVEL = {
    value: key for key, value in _SLEEP_NUMBER_LIGHT_LEVEL_TO_VALUE.items()
}
_SLEEP_NUMBER_FOOTWARMING_LEVELS = ("low", "medium", "high")
_SLEEP_NUMBER_DEFAULT_FOOTWARMING_LEVEL = "low"

# Backends for the unified thermal climate entity.
_THERMAL_BACKEND_HEIDI = "heidi"  # Core Temperature Module (THMS) — heat + cool
_THERMAL_BACKEND_FROSTY = "frosty"  # Cooling Module (CLMS) — cool only

# Frosty (Cooling Module) supports cooling only, 3 presets + off.
# Authoritative source: com.selectcomfort.bedcontrolframework.cache.thermal.cooling.a$b
_FROSTY_COOLING_PRESET_TO_MODE = {
    "low": "cooling_pull_low",
    "medium": "cooling_pull_med",
    "high": "cooling_pull_high",
}
_FROSTY_MODE_TO_COOLING_PRESET = {
    mode: preset for preset, mode in _FROSTY_COOLING_PRESET_TO_MODE.items()
}

# Heidi (Core Temperature Module) supports cooling AND heating, including a
# SPECIAL_HIGH_COOLING "boost" mode.
# Authoritative source: com.selectcomfort.bedcontrolframework.cache.thermal.core.a$b
_HEIDI_COOLING_PRESET_TO_MODE = {
    "low": "cooling_pull_low",
    "medium": "cooling_pull_med",
    "high": "cooling_pull_high",
    "boost": "cooling_push_high",
}
_HEIDI_MODE_TO_COOLING_PRESET = {
    mode: preset for preset, mode in _HEIDI_COOLING_PRESET_TO_MODE.items()
}
_HEIDI_HEATING_PRESET_TO_MODE = {
    "low": "heating_push_low",
    "medium": "heating_push_med",
    "high": "heating_push_high",
}
_HEIDI_MODE_TO_HEATING_PRESET = {
    mode: preset for preset, mode in _HEIDI_HEATING_PRESET_TO_MODE.items()
}
_HEIDI_COOLING_MODES = frozenset(_HEIDI_COOLING_PRESET_TO_MODE.values())
_HEIDI_HEATING_MODES = frozenset(_HEIDI_HEATING_PRESET_TO_MODE.values())

# HVAC modes used by the unified thermal climate entity.
_THERMAL_HVAC_OFF = "off"
_THERMAL_HVAC_COOL = "cool"
_THERMAL_HVAC_HEAT = "heat"


class SleepNumberCommands:
    """Fuzion bamkey command names used by Adjustable Bed support."""

    MULTIPLE_BAMKEYS_VIA_JSON = "BAMG"
    GET_ACTUATOR_POSITION = "ACTG"
    SET_ACTUATOR_TARGET_POSITION = "ACTS"
    HALT_ACTUATOR = "ACTH"
    HALT_ALL_ACTUATORS = "ACHA"
    SET_TARGET_PRESET = "ACSP"
    GET_BED_PRESENCE = "LBPG"
    GET_UNDERBED_LIGHT_SETTINGS = "UBLG"
    SET_UNDERBED_LIGHT_SETTINGS = "UBLS"
    GET_SLEEP_NUMBER_SETTING = "PSNG"
    # PSNS is "Start Sleep Number Adjustment" in the SleepIQ app: it takes a
    # target firmness and the bed pumps air asynchronously. We use it as a
    # fire-and-forget setter; PSNI would interrupt, PSNU polls progress.
    START_SLEEP_NUMBER_ADJUSTMENT = "PSNS"
    GET_FOOTWARMING_PRESENCE = "FWPG"
    GET_FOOTWARMING_SETTINGS = "FWTG"
    SET_FOOTWARMING_SETTINGS = "FWTS"
    # Frosty = Cooling Module (cooling only).
    GET_FROSTY_PRESENCE = "CLPG"
    GET_FROSTY_MODE = "CLMG"
    SET_FROSTY_MODE = "CLMS"
    # Heidi = Core Temperature Module (heat + cool).
    GET_HEIDI_PRESENCE = "THPG"
    GET_HEIDI_MODE = "THMG"
    SET_HEIDI_MODE = "THMS"


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
        self._bulk_notify_started = False
        self._response_queue: asyncio.Queue[str] = asyncio.Queue()
        self._readback_hint_queue: asyncio.Queue[None] = asyncio.Queue()
        self._response_buffer = bytearray()
        self._underbed_light_level: str | None = None
        self._underbed_light_timer_minutes: int | None = None
        self._underbed_light_last_active_level = "high"
        self._bed_presence_states: dict[str, str] = {}
        self._bed_presence_state: str | None = None
        self._bed_presence_channel_primed = False
        self._sleep_number_setting: int | None = None
        self._footwarming_present = False
        self._footwarming_level = "off"
        self._footwarming_timer_minutes = _SLEEP_NUMBER_DEFAULT_THERMAL_TIMER_MINUTES
        self._footwarming_remaining_time_minutes = 0
        self._footwarming_total_remaining_time_minutes = 0
        self._footwarming_last_active_level = _SLEEP_NUMBER_DEFAULT_FOOTWARMING_LEVEL
        self._frosty_present = False
        self._frosty_mode = "off"
        self._frosty_timer_minutes = _SLEEP_NUMBER_DEFAULT_THERMAL_TIMER_MINUTES
        self._frosty_remaining_time_minutes = 0
        # Last active cooling preset name for Frosty resume-on.
        self._frosty_last_active_preset = "low"
        self._heidi_present = False
        self._heidi_mode = "off"
        self._heidi_timer_minutes = _SLEEP_NUMBER_DEFAULT_THERMAL_TIMER_MINUTES
        self._heidi_remaining_time_minutes = 0
        # Last active (hvac_mode, preset) for Heidi resume-on.
        self._heidi_last_active_hvac = _THERMAL_HVAC_HEAT
        self._heidi_last_active_preset = "low"

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
    def bed_presence_sides(self) -> tuple[str, ...]:
        """Return the sides exposed by Sleep Number occupancy queries."""
        return _SLEEP_NUMBER_BED_PRESENCE_QUERY_SIDES

    @property
    def supports_sleep_number_setting(self) -> bool:
        """Sleep Number exposes firmness adjustment for the configured side."""
        return True

    @property
    def sleep_number_setting_min(self) -> int:
        """Return the minimum supported Sleep Number firmness value."""
        return _SLEEP_NUMBER_SLEEP_SETTING_MIN

    @property
    def sleep_number_setting_max(self) -> int:
        """Return the maximum supported Sleep Number firmness value."""
        return _SLEEP_NUMBER_SLEEP_SETTING_MAX

    @property
    def sleep_number_setting_step(self) -> int:
        """Return the native increment used for Sleep Number firmness."""
        return _SLEEP_NUMBER_SLEEP_SETTING_STEP

    @property
    def supports_footwarming_climate(self) -> bool:
        """Return True when footwarming is present on the connected bed."""
        return self._footwarming_present

    @property
    def supports_thermal_climate(self) -> bool:
        """Return True when either Frosty or Heidi is present on the bed."""
        return self._frosty_present or self._heidi_present

    @property
    def thermal_supports_heating(self) -> bool:
        """Return True when the active thermal backend can heat.

        Only Heidi (Core Temperature Module) supports heating; Frosty is
        cooling-only.
        """
        return self._heidi_present

    @property
    def thermal_supports_boost(self) -> bool:
        """Return True when the active backend exposes the SPECIAL_HIGH_COOLING boost mode."""
        # Only Heidi has SPECIAL_HIGH_COOLING in its mode enum.
        return self._heidi_present

    @property
    def footwarming_timer_options(self) -> list[str]:
        """Return available footwarming timer options (30m – 6h)."""
        if not self.supports_footwarming_climate:
            return []
        return [
            self._format_thermal_timer_option(minutes)
            for minutes in _SLEEP_NUMBER_FOOTWARMING_TIMER_OPTIONS
        ]

    @property
    def thermal_timer_options(self) -> list[str]:
        """Return available cooling/heating timer options (30m – 10h)."""
        if not self.supports_thermal_climate:
            return []
        return [
            self._format_thermal_timer_option(minutes)
            for minutes in _SLEEP_NUMBER_THERMAL_TIMER_OPTIONS
        ]

    @property
    def requires_notification_channel(self) -> bool:
        """Command acks and query responses arrive as notifications."""
        return True

    @property
    def allow_position_polling_during_commands(self) -> bool:
        """Sleep Number bamkey commands must own the response queue exclusively."""
        return False

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
        return max(_SLEEP_NUMBER_MIN_POSITION, min(_SLEEP_NUMBER_MAX_POSITION, round(angle)))

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

    def get_footwarming_state(self) -> dict[str, Any]:
        """Return the last known footwarming state."""
        return {
            "side": self._side,
            "present": self._footwarming_present,
            "hvac_mode": "heat" if self._footwarming_level != "off" else "off",
            "preset_mode": None if self._footwarming_level == "off" else self._footwarming_level,
            "timer_option": self._format_thermal_timer_option(self._footwarming_timer_minutes),
            "remaining_time_minutes": self._footwarming_remaining_time_minutes,
            "total_remaining_time_minutes": self._footwarming_total_remaining_time_minutes,
            "level": self._footwarming_level,
        }

    def get_frosty_state(self) -> dict[str, Any]:
        """Return the last known Frosty (cooling module) state."""
        return {
            "side": self._side,
            "present": self._frosty_present,
            "hvac_mode": _THERMAL_HVAC_COOL if self._frosty_mode != "off" else _THERMAL_HVAC_OFF,
            "preset_mode": _FROSTY_MODE_TO_COOLING_PRESET.get(self._frosty_mode),
            "timer_option": self._format_thermal_timer_option(self._frosty_timer_minutes),
            "remaining_time_minutes": self._frosty_remaining_time_minutes,
            "mode": self._frosty_mode,
        }

    def get_heidi_state(self) -> dict[str, Any]:
        """Return the last known Heidi (core temperature module) state."""
        hvac_mode, preset = self._heidi_hvac_and_preset(self._heidi_mode)
        return {
            "side": self._side,
            "present": self._heidi_present,
            "hvac_mode": hvac_mode,
            "preset_mode": preset,
            "timer_option": self._format_thermal_timer_option(self._heidi_timer_minutes),
            "remaining_time_minutes": self._heidi_remaining_time_minutes,
            "mode": self._heidi_mode,
        }

    def get_thermal_state(self) -> dict[str, Any]:
        """Return the last known unified thermal climate state (heidi-preferred)."""
        backend = self._thermal_backend
        if backend == _THERMAL_BACKEND_HEIDI:
            state = self.get_heidi_state()
        elif backend == _THERMAL_BACKEND_FROSTY:
            state = self.get_frosty_state()
        else:
            return {
                "side": self._side,
                "backend": None,
                "present": False,
                "hvac_mode": _THERMAL_HVAC_OFF,
                "preset_mode": None,
                "supports_heating": False,
                "timer_option": self._format_thermal_timer_option(
                    _SLEEP_NUMBER_DEFAULT_THERMAL_TIMER_MINUTES
                ),
                "remaining_time_minutes": 0,
                "mode": "off",
            }
        state["backend"] = backend
        state["supports_heating"] = backend == _THERMAL_BACKEND_HEIDI
        return state

    @property
    def _thermal_backend(self) -> str | None:
        """Return which thermal module backs the unified climate entity."""
        if self._heidi_present:
            return _THERMAL_BACKEND_HEIDI
        if self._frosty_present:
            return _THERMAL_BACKEND_FROSTY
        return None

    @staticmethod
    def _heidi_hvac_and_preset(raw_mode: str) -> tuple[str, str | None]:
        """Map a raw Heidi ThermalMode value to (hvac_mode, preset_name)."""
        if raw_mode in _HEIDI_HEATING_MODES:
            return _THERMAL_HVAC_HEAT, _HEIDI_MODE_TO_HEATING_PRESET.get(raw_mode)
        if raw_mode in _HEIDI_COOLING_MODES:
            return _THERMAL_HVAC_COOL, _HEIDI_MODE_TO_COOLING_PRESET.get(raw_mode)
        return _THERMAL_HVAC_OFF, None

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        """Subscribe to bamkey notifications used for responses."""
        self._notify_callback = callback

        if self._notify_started:
            return

        client = self.client
        if client is None or not client.is_connected:
            raise ConnectionError("Not connected to bed")

        self._response_buffer.clear()
        self._drain_response_queue()
        self._drain_readback_hint_queue()
        await client.start_notify(
            SLEEP_NUMBER_BAMKEY_CHAR_UUID,
            self._handle_bamkey_notification,
        )
        self._notify_started = True

        if self._has_characteristic(SLEEP_NUMBER_BULK_TRANSFER_CHAR_UUID):
            try:
                await client.start_notify(
                    SLEEP_NUMBER_BULK_TRANSFER_CHAR_UUID,
                    self._handle_bamkey_readback_hint_notification,
                )
            except BleakError:
                _LOGGER.debug(
                    "Failed to start Sleep Number bulk-transfer notifications",
                    exc_info=True,
                )
            else:
                self._bulk_notify_started = True

    async def stop_notify(self) -> None:
        """Unsubscribe from bamkey notifications."""
        self._notify_callback = None
        client = self.client
        try:
            if client is None or not client.is_connected or not self._notify_started:
                return
            await client.stop_notify(SLEEP_NUMBER_BAMKEY_CHAR_UUID)
        except BleakError:
            _LOGGER.debug("Failed to stop Sleep Number notifications", exc_info=True)
        finally:
            if client is not None and client.is_connected and self._bulk_notify_started:
                try:
                    await client.stop_notify(SLEEP_NUMBER_BULK_TRANSFER_CHAR_UUID)
                except BleakError:
                    _LOGGER.debug(
                        "Failed to stop Sleep Number bulk-transfer notifications",
                        exc_info=True,
                    )
            self._notify_started = False
            self._bulk_notify_started = False
            self._bed_presence_channel_primed = False
            self._response_buffer.clear()
            self._drain_response_queue()
            self._drain_readback_hint_queue()

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
            cancel_event=asyncio.Event(),
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
        errors: list[Exception] = []
        for motor in ("back", "legs"):
            try:
                await self._send_stop_for_motor(motor)
            except Exception as err:
                errors.append(err)

        if errors:
            raise ExceptionGroup("Failed to stop one or more Sleep Number actuators", errors)

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
        states = await self._read_bed_presence_states()
        return self._presence_state_to_bool(states[self._side])

    async def query_config(self) -> None:
        """Load Sleep Number feature state needed for entity creation."""
        with contextlib.suppress(BleakError, ConnectionError, TimeoutError, ValueError):
            await self.read_sleep_number_setting()

        await self._query_optional_presence_feature(
            presence_bamkey=SleepNumberCommands.GET_FOOTWARMING_PRESENCE,
            store_present=self._store_footwarming_present,
            read_state=self.read_footwarming_state,
        )
        await self._query_optional_presence_feature(
            presence_bamkey=SleepNumberCommands.GET_FROSTY_PRESENCE,
            store_present=self._store_frosty_present,
            read_state=self.read_frosty_state,
        )
        await self._query_optional_presence_feature(
            presence_bamkey=SleepNumberCommands.GET_HEIDI_PRESENCE,
            store_present=self._store_heidi_present,
            read_state=self.read_heidi_state,
        )
        with contextlib.suppress(BleakError, ConnectionError, TimeoutError, ValueError):
            await self.read_bed_presence()

    async def read_sleep_number_setting(self) -> int:
        """Read the configured side's Sleep Number setting."""
        response = await self._send_bamkey_command(
            SleepNumberCommands.GET_SLEEP_NUMBER_SETTING,
            self._side,
            expected_args=1,
        )
        value = self._normalize_sleep_number_setting(int(response[0]))
        self._store_sleep_number_setting(value)
        return value

    async def set_sleep_number_setting(self, value: int) -> None:
        """Start a Sleep Number firmness adjustment on the configured side.

        Wire-level this is ``PSNS <side> <target>`` which the SleepIQ app calls
        "Start Sleep Number Adjustment" — the bed then pumps air asynchronously
        toward the target. We optimistically publish the target immediately; a
        future iteration could poll ``PSNU`` for progress and expose ``PSNI``
        for cancel.
        """
        normalized = self._normalize_sleep_number_setting(value)
        await self._send_bamkey_command(
            SleepNumberCommands.START_SLEEP_NUMBER_ADJUSTMENT,
            self._side,
            str(normalized),
        )
        self._store_sleep_number_setting(normalized)

    async def read_footwarming_state(self) -> dict[str, Any]:
        """Read and publish current footwarming settings."""
        response = await self._send_bamkey_command(
            SleepNumberCommands.GET_FOOTWARMING_SETTINGS,
            self._side,
            expected_args=3,
        )
        level = self._normalize_footwarming_level(response[0])
        remaining = max(0, int(response[1]))
        total = max(0, int(response[2]))
        self._store_footwarming_state(level, remaining, total)
        return self.get_footwarming_state()

    async def set_footwarming_preset(self, preset: str) -> None:
        """Set the footwarming level for the configured side.

        For "off", the SleepIQ app's FuzionFootwarmingCapability preserves the
        current remaining timer rather than sending 0, so we match that here.
        """
        level = self._normalize_footwarming_preset(preset)
        timer_minutes = self._footwarming_timer_minutes
        await self._send_bamkey_command(
            SleepNumberCommands.SET_FOOTWARMING_SETTINGS,
            self._side,
            level,
            str(timer_minutes),
        )
        remaining = timer_minutes if level != "off" else 0
        total = timer_minutes if level != "off" else 0
        self._store_footwarming_state(level, remaining, total, selected_timer_minutes=timer_minutes)

    async def turn_footwarming_on(self) -> None:
        """Turn footwarming on using the last active or default preset."""
        await self.set_footwarming_preset(self._footwarming_last_active_level)

    async def turn_footwarming_off(self) -> None:
        """Turn footwarming off while preserving the selected timer."""
        await self.set_footwarming_preset("off")

    async def set_footwarming_timer(self, timer_option: str) -> None:
        """Update the footwarming timer."""
        timer_minutes = self._parse_footwarming_timer_option(timer_option)
        self._footwarming_timer_minutes = timer_minutes
        if self._footwarming_level == "off":
            self._publish_footwarming_state()
            return
        await self.set_footwarming_preset(self._footwarming_level)

    async def read_frosty_state(self) -> dict[str, Any]:
        """Read and publish current Frosty (cooling module) settings."""
        response = await self._send_bamkey_command(
            SleepNumberCommands.GET_FROSTY_MODE,
            self._side,
            expected_args=2,
        )
        mode = self._normalize_frosty_mode(response[0])
        remaining = max(0, int(response[1]))
        self._store_frosty_state(mode, remaining)
        return self.get_frosty_state()

    async def _send_frosty_mode(self, raw_mode: str, *, timer_minutes: int) -> None:
        """Send the CLMS command with a validated ThermalMode value."""
        normalized = self._normalize_frosty_mode(raw_mode)
        await self._send_bamkey_command(
            SleepNumberCommands.SET_FROSTY_MODE,
            self._side,
            normalized,
            str(timer_minutes),
        )
        # The SleepIQ app sends timer=0 with OFF, so remaining is 0 when we
        # observe OFF below.
        remaining = timer_minutes if normalized != "off" else 0
        self._store_frosty_state(
            normalized,
            remaining,
            selected_timer_minutes=timer_minutes if normalized != "off" else None,
        )

    async def read_heidi_state(self) -> dict[str, Any]:
        """Read and publish current Heidi (core temperature module) settings."""
        response = await self._send_bamkey_command(
            SleepNumberCommands.GET_HEIDI_MODE,
            self._side,
            expected_args=2,
        )
        mode = self._normalize_heidi_mode(response[0])
        remaining = max(0, int(response[1]))
        self._store_heidi_state(mode, remaining)
        return self.get_heidi_state()

    async def _send_heidi_mode(self, raw_mode: str, *, timer_minutes: int) -> None:
        """Send the THMS command with a validated ThermalMode value."""
        normalized = self._normalize_heidi_mode(raw_mode)
        await self._send_bamkey_command(
            SleepNumberCommands.SET_HEIDI_MODE,
            self._side,
            normalized,
            str(timer_minutes),
        )
        remaining = timer_minutes if normalized != "off" else 0
        self._store_heidi_state(
            normalized,
            remaining,
            selected_timer_minutes=timer_minutes if normalized != "off" else None,
        )

    async def read_thermal_state(self) -> dict[str, Any]:
        """Read state from the active thermal backend (heidi preferred)."""
        backend = self._thermal_backend
        if backend == _THERMAL_BACKEND_HEIDI:
            await self.read_heidi_state()
        elif backend == _THERMAL_BACKEND_FROSTY:
            await self.read_frosty_state()
        return self.get_thermal_state()

    async def set_thermal_preset(self, preset: str, hvac_mode: str | None = None) -> None:
        """Set the unified thermal climate preset for the active backend.

        The preset must be one of low/medium/high (or boost for Heidi cooling).
        ``hvac_mode`` selects heat vs cool on Heidi beds; it is ignored on
        Frosty beds (which can only cool). Pass preset "off" to turn off.
        """
        backend = self._thermal_backend
        if backend is None:
            raise ValueError("No thermal module present on this Sleep Number bed")

        normalized_preset = preset.strip().lower()
        if normalized_preset == "off":
            # Per the SleepIQ app's FuzionCoolingCapability/
            # FuzionCoreTemperatureCapability, the cooling and core-temperature
            # modules are turned off with timer=0.
            if backend == _THERMAL_BACKEND_HEIDI:
                await self._send_heidi_mode("off", timer_minutes=0)
            else:
                await self._send_frosty_mode("off", timer_minutes=0)
            return

        if backend == _THERMAL_BACKEND_HEIDI:
            target_hvac = (hvac_mode or self._heidi_last_active_hvac).strip().lower()
            if target_hvac == _THERMAL_HVAC_HEAT:
                if normalized_preset not in _HEIDI_HEATING_PRESET_TO_MODE:
                    raise ValueError(
                        f"Unsupported Sleep Number heating preset: {preset}"
                    )
                raw_mode = _HEIDI_HEATING_PRESET_TO_MODE[normalized_preset]
            elif target_hvac == _THERMAL_HVAC_COOL:
                if normalized_preset not in _HEIDI_COOLING_PRESET_TO_MODE:
                    raise ValueError(
                        f"Unsupported Sleep Number cooling preset: {preset}"
                    )
                raw_mode = _HEIDI_COOLING_PRESET_TO_MODE[normalized_preset]
            else:
                raise ValueError(
                    f"Unsupported Sleep Number thermal hvac mode: {hvac_mode}"
                )
            self._heidi_last_active_hvac = target_hvac
            self._heidi_last_active_preset = normalized_preset
            await self._send_heidi_mode(raw_mode, timer_minutes=self._heidi_timer_minutes)
            return

        # Frosty (cooling-only)
        if hvac_mode is not None and hvac_mode.strip().lower() == _THERMAL_HVAC_HEAT:
            raise ValueError(
                "Frosty (cooling module) cannot heat; only Heidi supports heating"
            )
        if normalized_preset not in _FROSTY_COOLING_PRESET_TO_MODE:
            raise ValueError(
                f"Unsupported Sleep Number frosty preset: {preset}"
            )
        self._frosty_last_active_preset = normalized_preset
        await self._send_frosty_mode(
            _FROSTY_COOLING_PRESET_TO_MODE[normalized_preset],
            timer_minutes=self._frosty_timer_minutes,
        )

    async def turn_thermal_on(self) -> None:
        """Turn the unified thermal climate on using the last active preset."""
        backend = self._thermal_backend
        if backend is None:
            raise ValueError("No thermal module present on this Sleep Number bed")
        if backend == _THERMAL_BACKEND_HEIDI:
            await self.set_thermal_preset(
                self._heidi_last_active_preset,
                hvac_mode=self._heidi_last_active_hvac,
            )
            return
        await self.set_thermal_preset(self._frosty_last_active_preset)

    async def turn_thermal_off(self) -> None:
        """Turn the unified thermal climate off (sends timer=0)."""
        backend = self._thermal_backend
        if backend is None:
            return
        await self.set_thermal_preset("off")

    async def set_thermal_timer(self, timer_option: str) -> None:
        """Update the cooling/heating timer on the active backend.

        If the backend is currently running, the new timer is re-applied via
        SET to restart the countdown, matching the SleepIQ app's behaviour.
        """
        backend = self._thermal_backend
        if backend is None:
            return
        timer_minutes = self._parse_thermal_timer_option(timer_option)
        if backend == _THERMAL_BACKEND_HEIDI:
            self._heidi_timer_minutes = timer_minutes
            if self._heidi_mode == "off":
                self._publish_heidi_state()
                self._publish_thermal_state()
                return
            await self._send_heidi_mode(self._heidi_mode, timer_minutes=timer_minutes)
            return
        # frosty
        self._frosty_timer_minutes = timer_minutes
        if self._frosty_mode == "off":
            self._publish_frosty_state()
            self._publish_thermal_state()
            return
        await self._send_frosty_mode(self._frosty_mode, timer_minutes=timer_minutes)

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

    async def read_light_state(self) -> dict[str, Any]:
        """Read and return the current underbed light state."""
        await self._read_underbed_light_settings()
        return self.get_light_state()

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

    async def _query_optional_presence_feature(
        self,
        *,
        presence_bamkey: str,
        store_present: Callable[[bool], None],
        read_state: Callable[[], Any],
    ) -> None:
        """Query a presence-gated optional Sleep Number feature."""
        try:
            present = await self._read_feature_presence(presence_bamkey)
        except (BleakError, ConnectionError, TimeoutError, ValueError):
            _LOGGER.debug("Sleep Number optional feature query failed: %s", presence_bamkey)
            return

        store_present(present)
        if not present:
            return

        with contextlib.suppress(BleakError, ConnectionError, TimeoutError, ValueError):
            await read_state()

    async def _read_feature_presence(self, bamkey: str) -> bool:
        """Read a boolean-like Sleep Number Presence bamkey."""
        response = await self._send_bamkey_command(
            bamkey,
            self._side,
            expected_args=1,
        )
        return self._normalize_presence_flag(response[0])

    async def _read_bed_presence_states(self) -> dict[str, str]:
        """Read and publish occupancy state for both sides in one BAMG request."""
        await self._ensure_bed_presence_channel_primed()

        grouped_response = await self._send_bamkey_raw_response(
            SleepNumberCommands.MULTIPLE_BAMKEYS_VIA_JSON,
            json.dumps(
                [
                    {"bamkey": SleepNumberCommands.GET_BED_PRESENCE, "args": side}
                    for side in _SLEEP_NUMBER_BED_PRESENCE_QUERY_SIDES
                ],
                separators=(",", ":"),
            ),
        )
        return self._publish_bed_presence_states(
            self._parse_grouped_bed_presence_response(grouped_response)
        )

    def _publish_bed_presence_states(self, states: dict[str, str]) -> dict[str, str]:
        """Normalize and publish Sleep Number bed-presence state for both sides."""
        normalized_states = {
            side: self._normalize_bed_presence(value)
            for side, value in states.items()
        }
        self._bed_presence_states = normalized_states
        self._bed_presence_state = normalized_states[self._side]
        self.forward_controller_state_updates(
            {
                "bed_presence": self._bed_presence_state,
                "bed_presence_side": self._side,
                "bed_presence_left": normalized_states[SLEEP_NUMBER_VARIANT_LEFT],
                "bed_presence_right": normalized_states[SLEEP_NUMBER_VARIANT_RIGHT],
            }
        )
        return normalized_states

    def _store_sleep_number_setting(self, value: int) -> None:
        """Persist and publish the configured side's Sleep Number setting."""
        self._sleep_number_setting = value
        self.forward_controller_state_updates(
            {
                "sleep_number": value,
                "sleep_number_side": self._side,
            }
        )

    def _store_footwarming_present(self, present: bool) -> None:
        """Persist and publish footwarming presence."""
        self._footwarming_present = present
        self.forward_controller_state_update("footwarming_present", present)

    def _store_footwarming_state(
        self,
        level: str,
        remaining_minutes: int,
        total_remaining_minutes: int,
        *,
        selected_timer_minutes: int | None = None,
    ) -> None:
        """Persist and publish footwarming state."""
        self._footwarming_level = level
        self._footwarming_remaining_time_minutes = remaining_minutes
        self._footwarming_total_remaining_time_minutes = total_remaining_minutes
        if selected_timer_minutes is not None:
            self._footwarming_timer_minutes = selected_timer_minutes
        elif total_remaining_minutes > 0:
            self._footwarming_timer_minutes = total_remaining_minutes
        if level != "off":
            self._footwarming_last_active_level = level
        self._publish_footwarming_state()

    def _publish_footwarming_state(self) -> None:
        """Publish the cached footwarming state."""
        self.forward_controller_state_updates(
            {
                "footwarming_present": self._footwarming_present,
                "footwarming_hvac_mode": "heat" if self._footwarming_level != "off" else "off",
                "footwarming_preset": (
                    None if self._footwarming_level == "off" else self._footwarming_level
                ),
                "footwarming_level": self._footwarming_level,
                "footwarming_remaining_time_minutes": self._footwarming_remaining_time_minutes,
                "footwarming_total_remaining_time_minutes": (
                    self._footwarming_total_remaining_time_minutes
                ),
                "footwarming_timer_option": self._format_thermal_timer_option(
                    self._footwarming_timer_minutes
                ),
            }
        )

    def _store_frosty_present(self, present: bool) -> None:
        """Persist and publish Frosty (cooling module) presence."""
        self._frosty_present = present
        self.forward_controller_state_update("frosty_present", present)
        self._publish_thermal_state()

    def _store_frosty_state(
        self,
        mode: str,
        remaining_minutes: int,
        *,
        selected_timer_minutes: int | None = None,
    ) -> None:
        """Persist and publish Frosty (cooling module) state."""
        self._frosty_mode = mode
        self._frosty_remaining_time_minutes = remaining_minutes
        if selected_timer_minutes is not None:
            self._frosty_timer_minutes = selected_timer_minutes
        elif remaining_minutes > 0:
            self._frosty_timer_minutes = remaining_minutes
        if mode != "off":
            preset = _FROSTY_MODE_TO_COOLING_PRESET.get(mode)
            if preset is not None:
                self._frosty_last_active_preset = preset
        self._publish_frosty_state()
        self._publish_thermal_state()

    def _publish_frosty_state(self) -> None:
        """Publish the cached Frosty state under the legacy keys."""
        preset = _FROSTY_MODE_TO_COOLING_PRESET.get(self._frosty_mode)
        self.forward_controller_state_updates(
            {
                "frosty_present": self._frosty_present,
                "frosty_hvac_mode": (
                    _THERMAL_HVAC_COOL if self._frosty_mode != "off" else _THERMAL_HVAC_OFF
                ),
                "frosty_preset": preset,
                "frosty_mode": self._frosty_mode,
                "frosty_remaining_time_minutes": self._frosty_remaining_time_minutes,
                "frosty_timer_option": self._format_thermal_timer_option(
                    self._frosty_timer_minutes
                ),
            }
        )

    def _store_heidi_present(self, present: bool) -> None:
        """Persist and publish Heidi (core temperature module) presence."""
        self._heidi_present = present
        self.forward_controller_state_update("heidi_present", present)
        self._publish_thermal_state()

    def _store_heidi_state(
        self,
        mode: str,
        remaining_minutes: int,
        *,
        selected_timer_minutes: int | None = None,
    ) -> None:
        """Persist and publish Heidi (core temperature module) state."""
        self._heidi_mode = mode
        self._heidi_remaining_time_minutes = remaining_minutes
        if selected_timer_minutes is not None:
            self._heidi_timer_minutes = selected_timer_minutes
        elif remaining_minutes > 0:
            self._heidi_timer_minutes = remaining_minutes
        if mode != "off":
            hvac_mode, preset = self._heidi_hvac_and_preset(mode)
            if preset is not None:
                self._heidi_last_active_hvac = hvac_mode
                self._heidi_last_active_preset = preset
        self._publish_heidi_state()
        self._publish_thermal_state()

    def _publish_heidi_state(self) -> None:
        """Publish the cached Heidi state under the legacy keys."""
        hvac_mode, preset = self._heidi_hvac_and_preset(self._heidi_mode)
        self.forward_controller_state_updates(
            {
                "heidi_present": self._heidi_present,
                "heidi_hvac_mode": hvac_mode,
                "heidi_preset": preset,
                "heidi_mode": self._heidi_mode,
                "heidi_remaining_time_minutes": self._heidi_remaining_time_minutes,
                "heidi_timer_option": self._format_thermal_timer_option(
                    self._heidi_timer_minutes
                ),
            }
        )

    def _publish_thermal_state(self) -> None:
        """Publish unified thermal climate state from the active backend."""
        backend = self._thermal_backend
        if backend is None:
            self.forward_controller_state_updates(
                {
                    "thermal_backend": None,
                    "thermal_present": False,
                    "thermal_hvac_mode": _THERMAL_HVAC_OFF,
                    "thermal_preset": None,
                    "thermal_mode": "off",
                    "thermal_remaining_time_minutes": 0,
                    "thermal_timer_option": self._format_thermal_timer_option(
                        _SLEEP_NUMBER_DEFAULT_THERMAL_TIMER_MINUTES
                    ),
                    "thermal_supports_heating": False,
                }
            )
            return

        if backend == _THERMAL_BACKEND_HEIDI:
            raw_mode = self._heidi_mode
            timer_minutes = self._heidi_timer_minutes
            remaining = self._heidi_remaining_time_minutes
            hvac_mode, preset = self._heidi_hvac_and_preset(raw_mode)
            supports_heating = True
        else:  # frosty
            raw_mode = self._frosty_mode
            timer_minutes = self._frosty_timer_minutes
            remaining = self._frosty_remaining_time_minutes
            hvac_mode = (
                _THERMAL_HVAC_COOL if raw_mode != "off" else _THERMAL_HVAC_OFF
            )
            preset = _FROSTY_MODE_TO_COOLING_PRESET.get(raw_mode)
            supports_heating = False

        self.forward_controller_state_updates(
            {
                "thermal_backend": backend,
                "thermal_present": True,
                "thermal_hvac_mode": hvac_mode,
                "thermal_preset": preset,
                "thermal_mode": raw_mode,
                "thermal_remaining_time_minutes": remaining,
                "thermal_timer_option": self._format_thermal_timer_option(timer_minutes),
                "thermal_supports_heating": supports_heating,
            }
        )

    async def _ensure_notifications_started(self) -> None:
        """Ensure the bamkey response channel is subscribed."""
        if not self._notify_started:
            await self.start_notify(self._notify_callback)

    async def _ensure_bed_presence_channel_primed(self) -> None:
        """Prime the BLE side channels Sleep Number needs before LBPG polls."""
        if self._bed_presence_channel_primed:
            return

        client = self.client
        if client is None or not client.is_connected:
            raise ConnectionError("Not connected to bed")

        for char_uuid in (SLEEP_NUMBER_AUTH_CHAR_UUID, SLEEP_NUMBER_TRANSFER_INFO_CHAR_UUID):
            async with self.ble_lock:
                await client.read_gatt_char(char_uuid)

        self._bed_presence_channel_primed = True

    async def _send_bamkey_command(
        self,
        bamkey: str,
        *args: str,
        expected_args: int = 0,
        cancel_event: asyncio.Event | None = None,
    ) -> list[str]:
        """Send a bamkey command and parse the matching response."""
        raw_response = await self._send_bamkey_raw_response(
            bamkey,
            *args,
            cancel_event=cancel_event,
        )
        return self._parse_bamkey_response(bamkey, raw_response, expected_args)

    async def _send_bamkey_raw_response(
        self,
        bamkey: str,
        *args: str,
        cancel_event: asyncio.Event | None = None,
    ) -> str:
        """Send a bamkey command and return the raw response text."""
        effective_cancel = cancel_event or self._coordinator.cancel_command
        if effective_cancel.is_set():
            raise asyncio.CancelledError

        await self._ensure_notifications_started()
        if effective_cancel.is_set():
            raise asyncio.CancelledError
        self._response_buffer.clear()
        self._drain_response_queue()
        self._drain_readback_hint_queue()

        payload = self._format_bamkey_command(bamkey, *args)
        # Sleep Number returns BamKey results over the notify/readback path on the
        # same characteristic, so waiting for a GATT write response only adds latency.
        await self._write_gatt_with_retry(
            SLEEP_NUMBER_BAMKEY_CHAR_UUID,
            self._build_bamkey_blob(payload),
            cancel_event=effective_cancel,
            response=False,
        )
        deadline = asyncio.get_running_loop().time() + _BAMKEY_RESPONSE_TIMEOUT
        response_task = asyncio.create_task(self._response_queue.get())
        hint_task = asyncio.create_task(self._readback_hint_queue.get())
        cancel_task = asyncio.create_task(effective_cancel.wait())
        try:
            while True:
                timeout = deadline - asyncio.get_running_loop().time()
                if timeout <= 0:
                    raise TimeoutError(f"{bamkey} timed out waiting for response")

                done, _ = await asyncio.wait(
                    {response_task, hint_task, cancel_task},
                    timeout=timeout,
                    return_when=asyncio.FIRST_COMPLETED,
                )
                if not done:
                    raise TimeoutError(f"{bamkey} timed out waiting for response")

                if cancel_task in done:
                    raise asyncio.CancelledError

                if response_task in done:
                    return response_task.result()

                if hint_task in done:
                    hint_task = asyncio.create_task(self._readback_hint_queue.get())
                    try:
                        return await self._read_bamkey_response_after_hint(
                            remaining_timeout=deadline - asyncio.get_running_loop().time(),
                            cancel_event=effective_cancel,
                        )
                    except (TimeoutError, ValueError):
                        _LOGGER.debug(
                            "Sleep Number readback after notification hint did not yield a full response",
                            exc_info=True,
                        )
        finally:
            for task in (response_task, hint_task, cancel_task):
                if task.done():
                    continue
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task

    def _drain_response_queue(self) -> None:
        """Discard stale bamkey responses before sending a new command."""
        while not self._response_queue.empty():
            self._response_queue.get_nowait()

    def _drain_readback_hint_queue(self) -> None:
        """Discard stale readback hints before sending a new command."""
        while not self._readback_hint_queue.empty():
            self._readback_hint_queue.get_nowait()

    async def _read_bamkey_response_after_hint(
        self,
        *,
        remaining_timeout: float,
        cancel_event: asyncio.Event,
    ) -> str:
        """Read the BamKey characteristic after a notification indicates fresh data."""
        client = self.client
        if client is None or not client.is_connected:
            raise ConnectionError("Not connected to bed")

        deadline = asyncio.get_running_loop().time() + remaining_timeout
        while True:
            if cancel_event.is_set():
                raise asyncio.CancelledError

            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                raise TimeoutError("Timed out waiting for Sleep Number readback response")

            await asyncio.sleep(min(_BAMKEY_READBACK_TRIGGER_DELAY, remaining))
            async with asyncio.timeout(remaining):
                async with self.ble_lock:
                    raw_response = bytes(await client.read_gatt_char(SLEEP_NUMBER_BAMKEY_CHAR_UUID))

            if not raw_response:
                continue

            try:
                decoded = self._decode_bamkey_text(raw_response)
            except ValueError:
                continue
            if not self._looks_like_bamkey_response(decoded):
                continue
            return decoded

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

        try:
            responses = self._extract_bamkey_text_responses(raw)
            for decoded in responses:
                self._response_queue.put_nowait(decoded)
        except ValueError:
            _LOGGER.debug("Failed to decode Sleep Number bamkey notification", exc_info=True)
            self._queue_readback_hint()
            return

        if not responses and not self._response_buffer:
            self._queue_readback_hint()

    def _handle_bamkey_readback_hint_notification(self, _sender: object, data: bytearray) -> None:
        """Treat secondary Sleep Number notifications as readback triggers."""
        raw = bytes(data)
        self.forward_raw_notification(SLEEP_NUMBER_BULK_TRANSFER_CHAR_UUID, raw)
        self._queue_readback_hint()

    def _queue_readback_hint(self) -> None:
        """Queue a notification hint that the BamKey characteristic should be read."""
        self._readback_hint_queue.put_nowait(None)

    def _extract_bamkey_text_responses(self, raw: bytes) -> list[str]:
        """Extract zero or more decoded bamkey payloads from the notification stream."""
        if not raw:
            return []

        if not self._response_buffer and not raw.startswith(_BAMKEY_BLOB_PREAMBLE):
            decoded = raw.decode("utf-8", errors="ignore").strip()
            if self._looks_like_bamkey_response(decoded):
                return [decoded]
            return []

        self._response_buffer.extend(raw)
        responses: list[str] = []

        while self._response_buffer:
            preamble_index = self._response_buffer.find(_BAMKEY_BLOB_PREAMBLE)
            if preamble_index == -1:
                self._response_buffer.clear()
                return responses
            if preamble_index > 0:
                del self._response_buffer[:preamble_index]

            if len(self._response_buffer) < _BAMKEY_BLOB_HEADER_LENGTH:
                return responses

            total_length = struct.unpack("<I", self._response_buffer[6:10])[0]
            if total_length < _BAMKEY_BLOB_MIN_LENGTH:
                raise ValueError(f"Invalid Sleep Number blob length: {total_length}")
            if len(self._response_buffer) < total_length:
                return responses

            frame = bytes(self._response_buffer[:total_length])
            del self._response_buffer[:total_length]
            decoded = self._parse_bamkey_blob(frame)
            if self._looks_like_bamkey_response(decoded):
                responses.append(decoded)

        return responses

    @staticmethod
    def _format_bamkey_command(bamkey: str, *args: str) -> str:
        """Format a bamkey request payload."""
        return bamkey if not args else f"{bamkey} {' '.join(args)}"

    @staticmethod
    def _build_bamkey_blob(payload: str) -> bytes:
        """Wrap a bamkey payload in the Fuzion blob framing used by SleepIQ."""
        encoded_payload = payload.encode("utf-8")
        total_length = _BAMKEY_BLOB_HEADER_LENGTH + len(encoded_payload) + 4
        header = _BAMKEY_BLOB_PREAMBLE + struct.pack("<I", total_length)
        checksum = binascii.crc32(header + encoded_payload) & 0xFFFFFFFF
        return header + encoded_payload + struct.pack("<I", checksum)

    @staticmethod
    def _decode_bamkey_text(raw: bytes) -> str:
        """Decode either a framed blob or a plain-text bamkey response."""
        if raw.startswith(_BAMKEY_BLOB_PREAMBLE):
            return SleepNumberController._parse_bamkey_blob(raw)

        decoded = raw.decode("utf-8", errors="ignore").strip()
        if not decoded:
            raise ValueError("Sleep Number returned an empty response")
        return decoded

    def _has_characteristic(self, char_uuid: str) -> bool:
        """Return True if the current connection exposed the characteristic UUID."""
        client = self.client
        if client is None or not client.services:
            return False

        for service in client.services:
            for characteristic in service.characteristics:
                if characteristic.uuid == char_uuid:
                    return True
        return False

    @staticmethod
    def _looks_like_bamkey_response(decoded: str) -> bool:
        """Return True when a decoded plain-text notification looks like a real response."""
        return decoded.startswith(("PASS:", "FAIL:", "["))

    @staticmethod
    def _parse_bamkey_blob(frame: bytes) -> str:
        """Decode and validate a single Sleep Number Fuzion blob."""
        if len(frame) < _BAMKEY_BLOB_MIN_LENGTH:
            raise ValueError("Sleep Number response blob is too short")
        if not frame.startswith(_BAMKEY_BLOB_PREAMBLE):
            raise ValueError("Sleep Number response blob is missing the Fuzion preamble")

        total_length = struct.unpack("<I", frame[6:10])[0]
        if total_length != len(frame):
            raise ValueError(
                f"Sleep Number response blob length mismatch: {len(frame)} != {total_length}"
            )

        payload = frame[_BAMKEY_BLOB_HEADER_LENGTH:-4]
        expected_crc = struct.unpack("<I", frame[-4:])[0]
        actual_crc = binascii.crc32(frame[:-4]) & 0xFFFFFFFF
        if actual_crc != expected_crc:
            raise ValueError("Sleep Number response blob failed CRC validation")

        decoded = payload.decode("utf-8", errors="ignore").strip()
        if not decoded:
            raise ValueError("Sleep Number response blob contained an empty payload")
        return decoded

    def _parse_grouped_bed_presence_response(self, response: str) -> dict[str, str]:
        """Extract both LBPG results from a grouped BAMG response."""
        payload = response.strip()
        if payload.startswith("PASS:"):
            payload = payload.removeprefix("PASS:").strip()

        try:
            values = json.loads(payload)
        except json.JSONDecodeError as err:
            raise ValueError(f"Invalid Sleep Number BAMG response: {response}") from err

        if not isinstance(values, list) or len(values) != len(_SLEEP_NUMBER_BED_PRESENCE_QUERY_SIDES):
            raise ValueError(f"Unexpected Sleep Number BAMG bed-presence response: {response}")

        states: dict[str, str] = {}
        for side, value in zip(_SLEEP_NUMBER_BED_PRESENCE_QUERY_SIDES, values, strict=True):
            if not isinstance(value, str):
                raise ValueError(f"Unexpected Sleep Number BAMG bed-presence item: {value!r}")
            if value.startswith("PASS:"):
                states[side] = value.removeprefix("PASS:").strip()
                continue
            if value.startswith("FAIL"):
                raise ValueError(f"Sleep Number BAMG bed-presence query failed: {value}")
            states[side] = value.strip()
        return states

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
    def _presence_state_to_bool(value: str) -> bool | None:
        """Convert a normalized Sleep Number presence state into a boolean."""
        if value == "in":
            return True
        if value == "out":
            return False
        return None

    @staticmethod
    def _normalize_presence_flag(value: str) -> bool:
        """Normalize a Sleep Number Presence enum value."""
        normalized = value.strip().lower()
        if normalized in {"true", "present", "1"}:
            return True
        if normalized in {"false", "not_present", "0"}:
            return False
        raise ValueError(f"Unsupported Sleep Number presence flag: {value}")

    @staticmethod
    def _normalize_sleep_number_setting(value: int) -> int:
        """Clamp and snap a Sleep Number setting to the supported range."""
        bounded = max(_SLEEP_NUMBER_SLEEP_SETTING_MIN, min(_SLEEP_NUMBER_SLEEP_SETTING_MAX, value))
        rounded_steps = round((bounded - _SLEEP_NUMBER_SLEEP_SETTING_MIN) / _SLEEP_NUMBER_SLEEP_SETTING_STEP)
        return _SLEEP_NUMBER_SLEEP_SETTING_MIN + (
            rounded_steps * _SLEEP_NUMBER_SLEEP_SETTING_STEP
        )

    @staticmethod
    def _normalize_underbed_light_level(value: str) -> str:
        """Normalize UBLG/UBLS level values."""
        normalized = value.strip().lower()
        if normalized in _SLEEP_NUMBER_LIGHT_LEVEL_TO_VALUE:
            return normalized
        raise ValueError(f"Unsupported Sleep Number light level: {value}")

    @staticmethod
    def _normalize_footwarming_level(value: str) -> str:
        """Normalize a footwarming level string."""
        normalized = value.strip().lower()
        if normalized == "off" or normalized in _SLEEP_NUMBER_FOOTWARMING_LEVELS:
            return normalized
        raise ValueError(f"Unsupported Sleep Number footwarming level: {value}")

    @staticmethod
    def _normalize_footwarming_preset(value: str) -> str:
        """Normalize a requested footwarming preset or raw level."""
        return SleepNumberController._normalize_footwarming_level(value)

    @staticmethod
    def _normalize_frosty_mode(value: str) -> str:
        """Normalize a raw Frosty (cooling module) mode string.

        The Cooling Module only supports 4 modes: off, cooling_pull_low,
        cooling_pull_med, cooling_pull_high.
        """
        normalized = value.strip().lower()
        if normalized == "off" or normalized in _FROSTY_COOLING_PRESET_TO_MODE.values():
            return normalized
        raise ValueError(f"Unsupported Sleep Number frosty mode: {value}")

    @staticmethod
    def _normalize_heidi_mode(value: str) -> str:
        """Normalize a raw Heidi (core temperature module) mode string.

        Heidi supports off, cooling_pull_* (low/med/high), cooling_push_high,
        and heating_push_* (low/med/high).
        """
        normalized = value.strip().lower()
        if (
            normalized == "off"
            or normalized in _HEIDI_COOLING_MODES
            or normalized in _HEIDI_HEATING_MODES
        ):
            return normalized
        raise ValueError(f"Unsupported Sleep Number heidi mode: {value}")

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

    @staticmethod
    def _format_thermal_timer_option(minutes: int) -> str:
        """Format a Sleep Number thermal timer value for Home Assistant selects."""
        if minutes <= 0:
            return "Off"
        if minutes < 60:
            return f"{minutes} min"
        hours, remainder = divmod(minutes, 60)
        if remainder:
            return f"{hours} hr {remainder} min"
        return f"{hours} hr"

    @staticmethod
    def _parse_thermal_timer_option(timer_option: str) -> int:
        """Parse a Home Assistant cooling/heating timer option into minutes."""
        return SleepNumberController._parse_timer_option_from(
            timer_option, _SLEEP_NUMBER_THERMAL_TIMER_OPTIONS
        )

    @staticmethod
    def _parse_footwarming_timer_option(timer_option: str) -> int:
        """Parse a Home Assistant footwarming timer option into minutes."""
        return SleepNumberController._parse_timer_option_from(
            timer_option, _SLEEP_NUMBER_FOOTWARMING_TIMER_OPTIONS
        )

    @staticmethod
    def _parse_timer_option_from(timer_option: str, options: tuple[int, ...]) -> int:
        """Parse a timer display string against a specific set of allowed values."""
        normalized = timer_option.strip().lower()
        if normalized == "off":
            return 0
        option_map = {
            SleepNumberController._format_thermal_timer_option(minutes).lower(): minutes
            for minutes in options
        }
        if normalized in option_map:
            return option_map[normalized]
        raise ValueError(f"Unsupported Sleep Number timer option: {timer_option}")
