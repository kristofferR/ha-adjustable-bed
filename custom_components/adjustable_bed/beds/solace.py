"""Controller for the FFE1/11-byte adjustable-bed protocol family.

Accepted APK analyses prove several overlapping device-name routes with
different motor and accessory surfaces.  Profiles keep those capabilities
separate instead of exposing the historical union to every bed.
"""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Callable, Collection
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from bleak.exc import BleakError
from homeassistant.util import dt as dt_util

from ..const import SOLACE_CHAR_UUID, SOLACE_NAME_PATTERNS
from .base import (
    BedController,
    ControllerStateBinarySensorSpec,
    ControllerStateSensorSpec,
    MotorControlSpec,
)

if TYPE_CHECKING:
    from ..coordinator import AdjustableBedCoordinator

_LOGGER = logging.getLogger(__name__)


class SolaceProfile(StrEnum):
    """Evidence-backed capability routes for the shared packet family."""

    COMMON = "common"
    HOME_K1 = "home_k1"
    HOME_K2 = "home_k2"
    MOTION_FLEX = "motion_flex"
    LEGACY_S4_Y = "legacy_s4_y"
    UNVERIFIED = "unverified"


_HOME_K1_PRIMARY_NAMES = ("qms-iq", "qms-i06", "qms-lq", "qms-l04")
_HOME_K1_FALLBACK_NAMES = ("qms-nq", "qms3")
_HOME_K2_NAMES = ("qms-jq-d", "qms4")
_LEGACY_S4_Y_PATTERN = re.compile(r"^s4-y-\d+-[a-z0-9]+$", re.IGNORECASE)

_SOLACE_ALARM_MODES = {"zero_g": 0x01, "memory_1": 0x02, "no_action": 0x03}
_SOLACE_ALARM_SOUNDS = {
    "none": 0x00,
    "alarm": 0x01,
    "music_1": 0x11,
    "music_2": 0x12,
    "music_3": 0x13,
    "music_4": 0x14,
    "music_5": 0x15,
}


def _bcd(value: int) -> int:
    """Encode a two-digit decimal value as one BCD byte."""
    return ((value // 10) << 4) | (value % 10)


def _with_additive_checksum(body: bytes) -> bytes:
    """Append the app's unpadded little-endian additive checksum."""
    checksum = sum(body)
    encoded = bytearray()
    while checksum:
        encoded.append(checksum & 0xFF)
        checksum >>= 8
    return body + bytes(encoded)


def build_solace_clock_command(now: datetime) -> bytes:
    """Build the MotionFlex startup clock-sync frame."""
    body = bytes.fromhex("FF FF FF FF 01 00 01 11") + bytes(
        (
            _bcd(now.hour),
            _bcd(now.minute),
            _bcd(now.second),
            _bcd(now.isoweekday()),
            _bcd(now.year % 100),
            _bcd(now.month),
            _bcd(now.day),
        )
    )
    return _with_additive_checksum(body)


def build_solace_alarm_command(
    *,
    enabled: bool,
    hour: int,
    minute: int,
    weekdays: Collection[int],
    mode: str,
    massage: bool,
    sound: str,
) -> bytes:
    """Build the MotionFlex alarm frame from user-facing values."""
    weekday_mask = 0
    for weekday in weekdays:
        weekday_mask |= 1 << weekday
    body = bytes.fromhex("FF FF FF FF 01 00 02 13") + bytes(
        (
            0x01 if enabled else 0xA1,
            _bcd(hour),
            _bcd(minute),
            0x00,
            weekday_mask,
            bool(weekdays),
            _SOLACE_ALARM_MODES[mode],
            massage,
            _SOLACE_ALARM_SOUNDS[sound],
        )
    )
    return _with_additive_checksum(body)


def resolve_solace_profile(device_name: str) -> SolaceProfile:
    """Resolve the narrowest profile proven for an observed BLE name."""
    name = device_name.strip().lower()
    if _LEGACY_S4_Y_PATTERN.fullmatch(name):
        return SolaceProfile.LEGACY_S4_Y
    if not (
        any(name.startswith(prefix) for prefix in SOLACE_NAME_PATTERNS)
        or name.startswith("my qms2")
    ):
        return SolaceProfile.UNVERIFIED
    if name.startswith("sealymf"):
        return SolaceProfile.MOTION_FLEX
    if any(name.startswith(prefix) for prefix in _HOME_K1_PRIMARY_NAMES):
        return SolaceProfile.HOME_K1
    if any(name.startswith(prefix) for prefix in _HOME_K2_NAMES):
        return SolaceProfile.HOME_K2
    if name.startswith(("qms-mq", "qms2", "my qms2")):
        return SolaceProfile.COMMON
    if any(name.startswith(prefix) for prefix in _HOME_K1_FALLBACK_NAMES):
        return SolaceProfile.HOME_K1
    return SolaceProfile.UNVERIFIED


class SolaceCommands:
    """Solace command constants (11-byte arrays)."""

    # Presets (autonomous — bed moves to target position on its own)
    PRESET_TV = bytes([0xFF, 0xFF, 0xFF, 0xFF, 0x05, 0x00, 0x00, 0x00, 0x05, 0x17, 0x03])
    PRESET_ZERO_G = bytes([0xFF, 0xFF, 0xFF, 0xFF, 0x05, 0x00, 0x00, 0x00, 0x09, 0x17, 0x06])
    PRESET_ANTI_SNORE = bytes([0xFF, 0xFF, 0xFF, 0xFF, 0x05, 0x00, 0x00, 0x00, 0x0F, 0x97, 0x04])
    PRESET_FLAT_BED = bytes([0xFF, 0xFF, 0xFF, 0xFF, 0x05, 0x00, 0x00, 0x00, 0x08, 0xD6, 0xC6])
    PRESET_RELAXING_BEDTIME = bytes.fromhex("FF FF FF FF 05 00 00 00 6A 57 2F")
    PRESET_LEGACY_ALL_FLAT = bytes(
        [0xFF, 0xFF, 0xFF, 0xFF, 0x05, 0x00, 0x00, 0x00, 0x2A, 0x56, 0xDF]
    )

    # Memory presets (byte 7 contains memory slot)
    PRESET_MEMORY_1 = bytes([0xFF, 0xFF, 0xFF, 0xFF, 0x05, 0x00, 0x00, 0xA1, 0x0A, 0x2E, 0x97])
    PRESET_MEMORY_2 = bytes([0xFF, 0xFF, 0xFF, 0xFF, 0x05, 0x00, 0x00, 0xB1, 0x0B, 0xE2, 0x97])
    PRESET_TV_SELECTED = bytes([0xFF, 0xFF, 0xFF, 0xFF, 0x05, 0x00, 0x00, 0x51, 0x05, 0x2A, 0x93])
    PRESET_ZERO_G_SELECTED = bytes(
        [0xFF, 0xFF, 0xFF, 0xFF, 0x05, 0x00, 0x00, 0x91, 0x09, 0x7A, 0x96]
    )
    PRESET_ANTI_SNORE_SELECTED = bytes(
        [0xFF, 0xFF, 0xFF, 0xFF, 0x05, 0x00, 0x00, 0xF1, 0x0F, 0xD2, 0x94]
    )

    # Program memory
    PROGRAM_MEMORY_1 = bytes([0xFF, 0xFF, 0xFF, 0xFF, 0x05, 0x00, 0x00, 0xA0, 0x0A, 0x2F, 0x07])
    PROGRAM_MEMORY_1_SELECTED = bytes(
        [0xFF, 0xFF, 0xFF, 0xFF, 0x05, 0x00, 0x00, 0xAF, 0x0A, 0x2A, 0xF7]
    )
    PROGRAM_MEMORY_2 = bytes([0xFF, 0xFF, 0xFF, 0xFF, 0x05, 0x00, 0x00, 0xB0, 0x0B, 0xE3, 0x07])
    PROGRAM_MEMORY_2_SELECTED = bytes(
        [0xFF, 0xFF, 0xFF, 0xFF, 0x05, 0x00, 0x00, 0xBF, 0x0B, 0xE6, 0xF7]
    )
    PROGRAM_TV = bytes([0xFF, 0xFF, 0xFF, 0xFF, 0x05, 0x00, 0x00, 0x50, 0x05, 0x2B, 0x03])
    PROGRAM_ZERO_G = bytes([0xFF, 0xFF, 0xFF, 0xFF, 0x05, 0x00, 0x00, 0x90, 0x09, 0x7B, 0x06])
    PROGRAM_ANTI_SNORE = bytes([0xFF, 0xFF, 0xFF, 0xFF, 0x05, 0x00, 0x00, 0xF0, 0x0F, 0xD3, 0x04])

    # Motor controls
    MOTOR_HEAD_UP = bytes([0xFF, 0xFF, 0xFF, 0xFF, 0x05, 0x00, 0x00, 0x00, 0x01, 0x16, 0xC0])
    MOTOR_HEAD_DOWN = bytes([0xFF, 0xFF, 0xFF, 0xFF, 0x05, 0x00, 0x00, 0x00, 0x02, 0x56, 0xC1])
    MOTOR_BACK_UP = bytes([0xFF, 0xFF, 0xFF, 0xFF, 0x05, 0x00, 0x00, 0x00, 0x03, 0x97, 0x01])
    MOTOR_BACK_DOWN = bytes([0xFF, 0xFF, 0xFF, 0xFF, 0x05, 0x00, 0x00, 0x00, 0x04, 0xD6, 0xC3])
    MOTOR_LEGS_UP = bytes([0xFF, 0xFF, 0xFF, 0xFF, 0x05, 0x00, 0x00, 0x00, 0x06, 0x57, 0x02])
    MOTOR_LEGS_DOWN = bytes([0xFF, 0xFF, 0xFF, 0xFF, 0x05, 0x00, 0x00, 0x00, 0x07, 0x96, 0xC2])
    MOTOR_LIFT_UP = bytes([0xFF, 0xFF, 0xFF, 0xFF, 0x05, 0x00, 0x00, 0x00, 0x21, 0x17, 0x18])
    MOTOR_LIFT_DOWN = bytes([0xFF, 0xFF, 0xFF, 0xFF, 0x05, 0x00, 0x00, 0x00, 0x22, 0x57, 0x19])
    MOTOR_TILT_UP = bytes([0xFF, 0xFF, 0xFF, 0xFF, 0x05, 0x00, 0x00, 0x00, 0x28, 0xD7, 0x1E])
    MOTOR_TILT_DOWN = bytes([0xFF, 0xFF, 0xFF, 0xFF, 0x05, 0x00, 0x00, 0x00, 0x29, 0x16, 0xDE])

    MOTOR_STOP = bytes([0xFF, 0xFF, 0xFF, 0xFF, 0x05, 0x00, 0x00, 0x00, 0x00, 0xD7, 0x00])

    # Preset-state queries. Q1 and Q2 are distinct firmware response families.
    QUERY_Q1 = (
        bytes.fromhex("FF FF FF FF 03 00 28 00 09 1F 0E"),
        bytes.fromhex("FF FF FF FF 03 00 31 00 09 CE C9"),
        bytes.fromhex("FF FF FF FF 03 00 16 00 09 7E C2"),
        bytes.fromhex("FF FF FF FF 03 00 1F 00 09 AE C0"),
        bytes.fromhex("FF FF FF FF 03 00 3A 00 09 BF 0B"),
    )
    QUERY_Q2 = (
        bytes.fromhex("FF FF FF FF 03 00 28 00 03 9F 09"),
        bytes.fromhex("FF FF FF FF 03 00 30 00 03 1F 0E"),
        bytes.fromhex("FF FF FF FF 03 00 18 00 03 9F 06"),
        bytes.fromhex("FF FF FF FF 03 00 20 00 03 1E CB"),
        bytes.fromhex("FF FF FF FF 03 00 38 00 03 9E CC"),
    )

    # Hip motor
    MOTOR_HIP_UP = bytes([0xFF, 0xFF, 0xFF, 0xFF, 0x05, 0x00, 0x00, 0x00, 0x0D, 0x16, 0xC5])
    MOTOR_HIP_DOWN = bytes([0xFF, 0xFF, 0xFF, 0xFF, 0x05, 0x00, 0x00, 0x00, 0x0E, 0x56, 0xC4])

    # Massage controls
    MASSAGE_HEAD_UP = bytes([0xFF, 0xFF, 0xFF, 0xFF, 0x05, 0x00, 0x00, 0x00, 0x10, 0xD6, 0xCC])
    MASSAGE_HEAD_DOWN = bytes([0xFF, 0xFF, 0xFF, 0xFF, 0x05, 0x00, 0x00, 0x00, 0x11, 0x17, 0x0C])
    MASSAGE_FOOT_UP = bytes([0xFF, 0xFF, 0xFF, 0xFF, 0x05, 0x00, 0x00, 0x00, 0x12, 0x57, 0x0D])
    MASSAGE_FOOT_DOWN = bytes([0xFF, 0xFF, 0xFF, 0xFF, 0x05, 0x00, 0x00, 0x00, 0x13, 0x96, 0xCD])
    MASSAGE_FREQUENCY_UP = bytes([0xFF, 0xFF, 0xFF, 0xFF, 0x05, 0x00, 0x00, 0x00, 0x14, 0xD7, 0x0F])
    MASSAGE_FREQUENCY_DOWN = bytes(
        [0xFF, 0xFF, 0xFF, 0xFF, 0x05, 0x00, 0x00, 0x00, 0x15, 0x16, 0xCF]
    )
    MASSAGE_STOP = bytes([0xFF, 0xFF, 0xFF, 0xFF, 0x05, 0x00, 0x00, 0x00, 0x1C, 0xD6, 0xC9])

    # Massage timers
    MASSAGE_TIMER_10_MIN = bytes([0xFF, 0xFF, 0xFF, 0xFF, 0x05, 0x00, 0x00, 0x00, 0x16, 0x56, 0xCE])
    MASSAGE_TIMER_20_MIN = bytes([0xFF, 0xFF, 0xFF, 0xFF, 0x05, 0x00, 0x00, 0x00, 0x17, 0x97, 0x0E])
    MASSAGE_TIMER_30_MIN = bytes([0xFF, 0xFF, 0xFF, 0xFF, 0x05, 0x00, 0x00, 0x00, 0x18, 0xD7, 0x0A])

    # Circulation/Loop massage modes
    MASSAGE_CIRCULATION_FULL_BODY = bytes(
        [0xFF, 0xFF, 0xFF, 0xFF, 0x05, 0x00, 0x05, 0x00, 0xE4, 0xC7, 0x4A]
    )
    MASSAGE_CIRCULATION_HEAD = bytes(
        [0xFF, 0xFF, 0xFF, 0xFF, 0x05, 0x00, 0x05, 0x00, 0xE3, 0x86, 0x88]
    )
    MASSAGE_CIRCULATION_LEG = bytes(
        [0xFF, 0xFF, 0xFF, 0xFF, 0x05, 0x00, 0x05, 0x00, 0xE5, 0x06, 0x8A]
    )
    MASSAGE_CIRCULATION_HIP = bytes(
        [0xFF, 0xFF, 0xFF, 0xFF, 0x05, 0x00, 0x05, 0x00, 0xE6, 0x46, 0x8B]
    )

    # Light levels (0-10)
    LIGHT_LEVEL_0 = bytes([0xFF, 0xFF, 0xFF, 0xFF, 0x05, 0x00, 0x00, 0x00, 0x23, 0x96, 0xD9])
    LIGHT_LEVEL_1 = bytes([0xFF, 0xFF, 0xFF, 0xFF, 0x05, 0x00, 0x00, 0x01, 0x23, 0x97, 0x49])
    LIGHT_LEVEL_2 = bytes([0xFF, 0xFF, 0xFF, 0xFF, 0x05, 0x00, 0x00, 0x02, 0x23, 0x97, 0xB9])
    LIGHT_LEVEL_3 = bytes([0xFF, 0xFF, 0xFF, 0xFF, 0x05, 0x00, 0x00, 0x03, 0x23, 0x96, 0x29])
    LIGHT_LEVEL_4 = bytes([0xFF, 0xFF, 0xFF, 0xFF, 0x05, 0x00, 0x00, 0x04, 0x23, 0x94, 0x19])
    LIGHT_LEVEL_5 = bytes([0xFF, 0xFF, 0xFF, 0xFF, 0x05, 0x00, 0x00, 0x05, 0x23, 0x95, 0x89])
    LIGHT_LEVEL_6 = bytes([0xFF, 0xFF, 0xFF, 0xFF, 0x05, 0x00, 0x00, 0x06, 0x23, 0x95, 0x79])
    LIGHT_LEVEL_7 = bytes([0xFF, 0xFF, 0xFF, 0xFF, 0x05, 0x00, 0x00, 0x07, 0x23, 0x94, 0xE9])
    LIGHT_LEVEL_8 = bytes([0xFF, 0xFF, 0xFF, 0xFF, 0x05, 0x00, 0x00, 0x08, 0x23, 0x91, 0x19])
    LIGHT_LEVEL_9 = bytes([0xFF, 0xFF, 0xFF, 0xFF, 0x05, 0x00, 0x00, 0x09, 0x23, 0x90, 0x89])
    LIGHT_LEVEL_10 = bytes([0xFF, 0xFF, 0xFF, 0xFF, 0x05, 0x00, 0x00, 0x0A, 0x23, 0x90, 0x79])
    LIGHT_STATUS_QUERY = bytes.fromhex("FF FF FF FF 05 00 05 FF 23 C7 28")

    # Light timers
    LIGHT_TIMER_10_MIN = bytes([0xFF, 0xFF, 0xFF, 0xFF, 0x05, 0x00, 0x00, 0x00, 0x19, 0x16, 0xCA])
    LIGHT_TIMER_8_HOURS = bytes([0xFF, 0xFF, 0xFF, 0xFF, 0x05, 0x00, 0x00, 0x00, 0x1A, 0x56, 0xCB])
    LIGHT_TIMER_10_HOURS = bytes([0xFF, 0xFF, 0xFF, 0xFF, 0x05, 0x00, 0x00, 0x00, 0x1B, 0x97, 0x0B])

    # MotionFlex music/audio controls use the additive-checksum frame family.
    MUSIC_TOGGLE = bytes.fromhex("FF FF FF FF 01 00 13 0B FF 1A 05")
    MUSIC_OFF = bytes.fromhex("FF FF FF FF 01 00 13 0B 00 1B 04")
    AUDIO_VOLUME_QUERY = bytes.fromhex("FF FF FF FF 01 00 15 0B 00 1D 04")


class SolaceController(BedController):
    """Controller for Solace beds."""

    def __init__(self, coordinator: AdjustableBedCoordinator) -> None:
        """Initialize the Solace controller."""
        super().__init__(coordinator)
        self._query_task: asyncio.Task[None] | None = None
        _LOGGER.debug("SolaceController initialized")

    @property
    def profile(self) -> SolaceProfile:
        """Return the profile for the latest observed BLE name."""
        return resolve_solace_profile(self._coordinator.ble_device_name)

    @property
    def protocol_diagnostics(self) -> dict[str, str]:
        """Expose the selected evidence profile in support bundles."""
        return {
            "solace_profile": self.profile.value,
            "solace_query_family": self._query_family or "none",
        }

    @property
    def controller_state_sensor_specs(self) -> tuple[ControllerStateSensorSpec, ...]:
        """Expose the result returned by MotionFlex audio-volume queries."""
        if not self.supports_solace_audio:
            return ()
        return (
            ControllerStateSensorSpec(
                key="solace_audio_volume",
                translation_key="solace_audio_volume",
                state_key="solace_audio_volume",
                icon="mdi:volume-high",
            ),
        )

    @property
    def controller_state_binary_sensor_specs(
        self,
    ) -> tuple[ControllerStateBinarySensorSpec, ...]:
        """Expose the decoded MotionFlex alarm reply and its configuration."""
        if not self.supports_solace_alarm:
            return ()
        return (
            ControllerStateBinarySensorSpec(
                key="solace_alarm_enabled",
                translation_key="solace_alarm_enabled",
                state_key="solace_alarm_enabled",
                icon="mdi:alarm",
                attribute_keys=(
                    "solace_alarm_time",
                    "solace_alarm_weekdays",
                    "solace_alarm_mode",
                    "solace_alarm_massage",
                    "solace_alarm_sound",
                    "solace_audio_available",
                ),
            ),
        )

    @property
    def stale_controller_state_sensor_entity_keys(self) -> frozenset[str]:
        """Remove MotionFlex-only sensor entities from narrower profiles."""
        if self.supports_solace_audio:
            return frozenset()
        return frozenset({"solace_audio_volume"})

    @property
    def stale_controller_state_binary_sensor_entity_keys(self) -> frozenset[str]:
        """Remove MotionFlex-only binary sensors from narrower profiles."""
        if self.supports_solace_alarm:
            return frozenset()
        return frozenset({"solace_alarm_enabled"})

    @property
    def control_characteristic_uuid(self) -> str:
        """Return the UUID of the control characteristic."""
        return SOLACE_CHAR_UUID

    @property
    def requires_notification_channel(self) -> bool:
        """Keep FFE1 subscribed for preset and accessory state replies."""
        return self.profile not in {
            SolaceProfile.LEGACY_S4_Y,
            SolaceProfile.UNVERIFIED,
        }

    @property
    def _query_family(self) -> str | None:
        """Return the accepted preset-status query family for this name route."""
        if self.profile in {SolaceProfile.LEGACY_S4_Y, SolaceProfile.UNVERIFIED}:
            return None
        if self.profile is SolaceProfile.HOME_K1:
            return "q1"
        if self.profile is SolaceProfile.HOME_K2:
            name = self._coordinator.ble_device_name.lower()
            return (
                "q2" if any(token in name for token in ("qms-mq", "qms2", "qms3", "s3-2")) else "q1"
            )
        return "q2"

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        """Subscribe to FFE1 and request the five preset-selection states."""
        self._notify_callback = callback
        client = self.client
        if client is None or not client.is_connected:
            _LOGGER.warning("Cannot start Solace notifications: not connected")
            return

        try:
            await client.start_notify(SOLACE_CHAR_UUID, self._handle_notification)
        except BleakError as err:
            _LOGGER.debug("Could not start Solace notifications: %s", err)
            return
        query_family = self._query_family
        if query_family is None:
            return

        if self._query_task is not None:
            self._query_task.cancel()
        self._query_task = asyncio.create_task(
            self._async_query_preset_states(query_family),
            name=f"solace-preset-state-{self._coordinator.address}",
        )

    async def _async_query_preset_states(self, query_family: str) -> None:
        """Issue the app-proven startup query sequence without delaying setup."""
        if self._coordinator.controller is not self:
            return
        self.forward_controller_state_updates(
            {
                f"solace_{key}_selected": False
                for key in ("tv", "zero_g", "memory_1", "memory_2", "anti_snore")
            }
        )
        queries = SolaceCommands.QUERY_Q1 if query_family == "q1" else SolaceCommands.QUERY_Q2

        async def run_queries(controller: BedController) -> None:
            if controller is not self:
                return
            if self.profile is SolaceProfile.MOTION_FLEX:
                await controller.write_command(
                    build_solace_clock_command(dt_util.now()),
                    cancel_event=asyncio.Event(),
                )
                queries_with_accessories = (*queries, SolaceCommands.LIGHT_STATUS_QUERY)
            else:
                queries_with_accessories = queries
            for index, command in enumerate(queries_with_accessories):
                await controller.write_command(command, cancel_event=asyncio.Event())
                if index < len(queries_with_accessories) - 1:
                    await asyncio.sleep(0.5)

        try:
            await asyncio.sleep(0.3)
            await self._coordinator.async_execute_controller_query(
                run_queries,
                skip_disconnect=True,
                preemptible=True,
                run_if=lambda: self._query_task is asyncio.current_task()
                and self._coordinator.controller is self,
            )
        except asyncio.CancelledError:
            raise
        except (BleakError, ConnectionError, RuntimeError) as err:
            # State is advisory. A failed query must not prevent bed controls.
            _LOGGER.debug("Solace preset-state query failed: %s", err)
        finally:
            if self._query_task is asyncio.current_task():
                self._query_task = None

    async def stop_notify(self) -> None:
        """Stop the FFE1 state subscription."""
        client = self.client
        if self._query_task is not None:
            self._query_task.cancel()
            self._query_task = None
        if client is None or not client.is_connected:
            return
        try:
            await client.stop_notify(SOLACE_CHAR_UUID)
        except BleakError as err:
            _LOGGER.debug("Could not stop Solace notifications: %s", err)

    def _handle_notification(self, _: object, data: bytearray) -> None:
        """Forward and parse the app-proven substring-based state replies."""
        payload = bytes(data)
        self.forward_raw_notification(SOLACE_CHAR_UUID, payload)
        self._parse_notification(payload)

    def _parse_notification(self, data: bytes) -> None:
        """Update selected preset flags from Q1/Q2 replies and command echoes."""
        updates: dict[str, bool | int | str] = {}
        selectors = {
            0x05: "tv",
            0x09: "zero_g",
            0x0A: "memory_1",
            0x0B: "memory_2",
            0x0F: "anti_snore",
        }
        prefix = bytes.fromhex("FF FF FF FF 03 06 00")
        for selector, key in selectors.items():
            if prefix + bytes([selector]) in data:
                updates[f"solace_{key}_selected"] = True

        state_frames = {
            SolaceCommands.PROGRAM_MEMORY_1: ("memory_1", True),
            SolaceCommands.PROGRAM_MEMORY_1_SELECTED: ("memory_1", False),
            SolaceCommands.PROGRAM_MEMORY_2: ("memory_2", True),
            SolaceCommands.PROGRAM_MEMORY_2_SELECTED: ("memory_2", False),
            SolaceCommands.PROGRAM_TV: ("tv", True),
            bytes.fromhex("FF FF FF FF 05 00 00 5F 05 2E F3"): ("tv", False),
            SolaceCommands.PROGRAM_ZERO_G: ("zero_g", True),
            bytes.fromhex("FF FF FF FF 05 00 00 9F 09 7E F6"): ("zero_g", False),
            SolaceCommands.PROGRAM_ANTI_SNORE: ("anti_snore", True),
            bytes.fromhex("FF FF FF FF 05 00 00 FF 0F D6 F4"): ("anti_snore", False),
        }
        for frame, (key, selected) in state_frames.items():
            if frame in data:
                updates[f"solace_{key}_selected"] = selected

        volume_prefix = bytes.fromhex("FF FF FF FF 01 00 15 0B")
        if (volume_index := data.find(volume_prefix)) >= 0 and len(data) > volume_index + 8:
            updates["solace_audio_volume"] = data[volume_index + 8] & 0x0F

        light_prefix = bytes.fromhex("FF FF FF FF 05 00 01")
        if (light_index := data.find(light_prefix)) >= 0 and len(data) > light_index + 7:
            light_level = data[light_index + 7]
            if 0 <= light_level <= self.light_level_max:
                updates["light_level"] = light_level

        alarm_none_prefix = bytes.fromhex("FF FF FF FF 01 00 03 0B")
        if (alarm_none_index := data.find(alarm_none_prefix)) >= 0 and len(
            data
        ) > alarm_none_index + 8:
            updates.update(
                {
                    "solace_alarm_enabled": False,
                    "solace_audio_available": data[alarm_none_index + 8] != 0,
                }
            )

        alarm_prefix = bytes.fromhex("FF FF FF FF 01 00 04 13")
        if (alarm_index := data.find(alarm_prefix)) >= 0 and len(data) >= alarm_index + 17:
            payload = data[alarm_index + 8 : alarm_index + 17]
            enabled = payload[0] in {0x0F, 0x1F}
            weekdays = [str(day) for day in range(1, 8) if payload[4] & (1 << day)]
            mode = {value: key for key, value in _SOLACE_ALARM_MODES.items()}.get(
                payload[6], f"unknown_{payload[6]:02x}"
            )
            sound = {value: key for key, value in _SOLACE_ALARM_SOUNDS.items()}.get(
                payload[8], f"unknown_{payload[8]:02x}"
            )
            updates.update(
                {
                    "solace_alarm_enabled": enabled,
                    "solace_alarm_time": f"{payload[1]:02x}:{payload[2]:02x}",
                    "solace_alarm_weekdays": ",".join(weekdays),
                    "solace_alarm_mode": mode,
                    "solace_alarm_massage": payload[7] == 1,
                    "solace_alarm_sound": sound,
                }
            )
        if updates:
            self.forward_controller_state_updates(updates)

    # Capability properties
    @property
    def supports_preset_flat(self) -> bool:
        """Avoid sending either flat variant to an unidentified manual route."""
        return self.profile is not SolaceProfile.UNVERIFIED

    @property
    def supports_preset_zero_g(self) -> bool:
        return self.profile is not SolaceProfile.UNVERIFIED

    @property
    def supports_preset_anti_snore(self) -> bool:
        return self.profile is not SolaceProfile.UNVERIFIED

    @property
    def supports_preset_tv(self) -> bool:
        return self.profile is not SolaceProfile.UNVERIFIED

    @property
    def supports_preset_yoga(self) -> bool:
        # Yoga belongs to a different app whose Phase 4 analysis is pending.
        return False

    @property
    def supports_relaxing_bedtime(self) -> bool:
        """Return whether MotionFlex exposes its relaxing-bedtime preset."""
        return self.profile is SolaceProfile.MOTION_FLEX

    @property
    def supports_solace_audio(self) -> bool:
        """Return whether MotionFlex exposes music and volume controls."""
        return self.profile is SolaceProfile.MOTION_FLEX

    @property
    def supports_solace_alarm(self) -> bool:
        """Return whether MotionFlex exposes its alarm packet family."""
        return self.profile is SolaceProfile.MOTION_FLEX

    @property
    def supports_memory_presets(self) -> bool:
        """Return whether the identified route has numbered memories."""
        return self.profile is not SolaceProfile.UNVERIFIED

    @property
    def memory_slot_count(self) -> int:
        """Return only the two slots that are not overloaded named presets."""
        return 0 if self.profile is SolaceProfile.UNVERIFIED else 2

    @property
    def supports_memory_programming(self) -> bool:
        """Return whether the two numbered memories can be programmed."""
        return self.profile is not SolaceProfile.UNVERIFIED

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        """Return only the motors proven for the selected profile."""

        def spec(
            key: str,
            up: str,
            down: str,
            stop: str,
            *,
            max_angle: float = 68,
        ) -> MotorControlSpec:
            return MotorControlSpec(
                key=key,
                translation_key=key,
                open_fn=lambda ctrl: getattr(ctrl, up)(),
                close_fn=lambda ctrl: getattr(ctrl, down)(),
                stop_fn=lambda ctrl: getattr(ctrl, stop)(),
                max_angle=max_angle,
            )

        controls = [
            spec("back", "move_back_up", "move_back_down", "move_back_stop"),
            spec(
                "legs",
                "move_legs_up",
                "move_legs_down",
                "move_legs_stop",
                max_angle=45,
            ),
        ]
        if self.profile is SolaceProfile.HOME_K1:
            controls.extend(
                (
                    spec("head", "move_head_up", "move_head_down", "move_head_stop"),
                    spec("hip", "move_hip_up", "move_hip_down", "move_hip_stop"),
                )
            )
        elif self.profile is SolaceProfile.HOME_K2:
            controls.extend(
                (
                    spec("head", "move_head_up", "move_head_down", "move_head_stop"),
                    spec(
                        "lumbar",
                        "move_lumbar_up",
                        "move_lumbar_down",
                        "move_lumbar_stop",
                        max_angle=30,
                    ),
                )
            )
        elif self.profile is SolaceProfile.LEGACY_S4_Y:
            controls.extend(
                (
                    spec(
                        "bed_height",
                        "move_lift_up",
                        "move_lift_down",
                        "move_lift_stop",
                    ),
                    spec(
                        "tilt",
                        "move_tilt_up",
                        "move_tilt_down",
                        "move_tilt_stop",
                        max_angle=45,
                    ),
                )
            )
        return tuple(controls)

    @property
    def stale_motor_entity_keys(self) -> frozenset[str]:
        """Remove covers left behind by the former union/motor-count layout."""
        return frozenset({"back", "legs", "head", "feet", "hip", "lumbar", "bed_height", "tilt"})

    # HA cover actions have no button-release event. Keep the existing timeout as
    # an integration safety cap, while still allowing an explicit stop to cancel it.
    _MOVEMENT_SAFETY_TIMEOUT: float = 5.0

    async def _send_stop(self) -> None:
        """Send STOP command with fresh cancel event."""
        await self.write_command(SolaceCommands.MOTOR_STOP, cancel_event=asyncio.Event())

    async def _move_with_stop(self, command: bytes) -> None:
        """Send a press command and guarantee its protocol STOP cleanup."""
        try:
            # Send move command once (latched — controller holds motor state)
            await self.write_command(command, cancel_event=asyncio.Event())
            # Wait for movement duration, interruptible by coordinator's cancel event
            try:
                await asyncio.wait_for(
                    self._coordinator.cancel_command.wait(),
                    timeout=self._MOVEMENT_SAFETY_TIMEOUT,
                )
            except TimeoutError:
                pass  # Normal: completed full movement duration
        finally:
            try:
                await self._send_stop()
            except BleakError, ConnectionError:
                _LOGGER.debug("Failed to send STOP command during cleanup")

    # Motor control methods
    async def move_head_up(self) -> None:
        """Move head up (separate pillow-top motor)."""
        await self._move_with_stop(SolaceCommands.MOTOR_HEAD_UP)

    async def move_head_down(self) -> None:
        """Move head down (separate pillow-top motor)."""
        await self._move_with_stop(SolaceCommands.MOTOR_HEAD_DOWN)

    async def move_head_stop(self) -> None:
        """Stop head motor."""
        await self.write_command(
            SolaceCommands.MOTOR_STOP,
            cancel_event=asyncio.Event(),
        )

    async def move_back_up(self) -> None:
        """Move back up."""
        await self._move_with_stop(SolaceCommands.MOTOR_BACK_UP)

    async def move_back_down(self) -> None:
        """Move back down."""
        await self._move_with_stop(SolaceCommands.MOTOR_BACK_DOWN)

    async def move_back_stop(self) -> None:
        """Stop back motor."""
        await self.move_head_stop()

    async def move_legs_up(self) -> None:
        """Move legs up."""
        await self._move_with_stop(SolaceCommands.MOTOR_LEGS_UP)

    async def move_legs_down(self) -> None:
        """Move legs down."""
        await self._move_with_stop(SolaceCommands.MOTOR_LEGS_DOWN)

    async def move_legs_stop(self) -> None:
        """Stop legs motor."""
        await self.move_head_stop()

    async def move_feet_up(self) -> None:
        """Move feet up (same as legs for Solace)."""
        await self.move_legs_up()

    async def move_feet_down(self) -> None:
        """Move feet down (same as legs for Solace)."""
        await self.move_legs_down()

    async def move_feet_stop(self) -> None:
        """Stop feet motor."""
        await self.move_head_stop()

    async def stop_all(self) -> None:
        """Stop all motors."""
        await self.write_command(
            SolaceCommands.MOTOR_STOP,
            cancel_event=asyncio.Event(),
        )

    async def _send_preset(self, command: bytes) -> None:
        """Send the accepted apps' single-write autonomous preset command."""
        await self.write_command(command, cancel_event=asyncio.Event())

    # Preset methods
    async def preset_flat(self) -> None:
        """Go to flat position (single-shot, bed moves autonomously)."""
        command = (
            SolaceCommands.PRESET_LEGACY_ALL_FLAT
            if self.profile is SolaceProfile.LEGACY_S4_Y
            else SolaceCommands.PRESET_FLAT_BED
        )
        await self._send_preset(command)

    async def preset_memory(self, memory_num: int) -> None:
        """Go to memory preset (single-shot, bed moves autonomously)."""
        commands = {
            1: SolaceCommands.PRESET_MEMORY_1,
            2: SolaceCommands.PRESET_MEMORY_2,
        }
        if command := commands.get(memory_num):
            await self._send_preset(command)
        else:
            _LOGGER.warning("Invalid memory preset number: %d (valid: 1-2)", memory_num)

    async def program_memory(self, memory_num: int) -> None:
        """Program current position to memory."""
        commands = {
            1: (
                SolaceCommands.PROGRAM_MEMORY_1_SELECTED
                if self._preset_is_selected("memory_1")
                else SolaceCommands.PROGRAM_MEMORY_1
            ),
            2: (
                SolaceCommands.PROGRAM_MEMORY_2_SELECTED
                if self._preset_is_selected("memory_2")
                else SolaceCommands.PROGRAM_MEMORY_2
            ),
        }
        if command := commands.get(memory_num):
            await self.write_command(command)
        else:
            _LOGGER.warning("Invalid memory program number: %d (valid: 1-2)", memory_num)

    async def preset_zero_g(self) -> None:
        """Go to zero gravity position (single-shot, bed moves autonomously)."""
        command = (
            SolaceCommands.PRESET_ZERO_G_SELECTED
            if self._preset_is_selected("zero_g")
            else SolaceCommands.PRESET_ZERO_G
        )
        await self._send_preset(command)

    async def preset_anti_snore(self) -> None:
        """Go to anti-snore position (single-shot, bed moves autonomously)."""
        command = (
            SolaceCommands.PRESET_ANTI_SNORE_SELECTED
            if self._preset_is_selected("anti_snore")
            else SolaceCommands.PRESET_ANTI_SNORE
        )
        await self._send_preset(command)

    async def preset_tv(self) -> None:
        """Go to TV position (single-shot, bed moves autonomously)."""
        command = (
            SolaceCommands.PRESET_TV_SELECTED
            if self._preset_is_selected("tv")
            else SolaceCommands.PRESET_TV
        )
        await self._send_preset(command)

    async def preset_relaxing_bedtime(self) -> None:
        """Run the MotionFlex relaxing-bedtime preset."""
        await self._send_preset(SolaceCommands.PRESET_RELAXING_BEDTIME)

    async def solace_music_toggle(self) -> None:
        """Send the MotionFlex short-press music action."""
        await self.write_command(SolaceCommands.MUSIC_TOGGLE, cancel_event=asyncio.Event())

    async def solace_music_off(self) -> None:
        """Send the MotionFlex long-press/dialog-save music action."""
        await self.write_command(SolaceCommands.MUSIC_OFF, cancel_event=asyncio.Event())

    async def solace_select_music(self, track: int, *, preview: bool = False) -> None:
        """Select one of the five MotionFlex tracks, optionally as an alarm preview."""
        value = track | (0x80 if preview else 0)
        body = bytes.fromhex("FF FF FF FF 01 00 13 0B") + bytes((value,))
        await self.write_command(_with_additive_checksum(body), cancel_event=asyncio.Event())

    async def solace_set_audio_volume(self, level: int) -> None:
        """Set the MotionFlex audio volume to an app-supported level (1-5)."""
        body = bytes.fromhex("FF FF FF FF 01 00 14 0B") + bytes((level,))
        await self.write_command(_with_additive_checksum(body), cancel_event=asyncio.Event())
        self.forward_controller_state_updates({"solace_audio_volume": level})

    async def solace_query_audio_volume(self) -> None:
        """Request the MotionFlex audio volume notification."""
        await self.write_command(
            SolaceCommands.AUDIO_VOLUME_QUERY,
            cancel_event=asyncio.Event(),
        )

    async def program_solace_alarm(
        self,
        *,
        enabled: bool,
        hour: int,
        minute: int,
        weekdays: Collection[int],
        mode: str,
        massage: bool,
        sound: str,
    ) -> None:
        """Program the MotionFlex alarm surface."""
        await self.write_command(
            build_solace_alarm_command(
                enabled=enabled,
                hour=hour,
                minute=minute,
                weekdays=weekdays,
                mode=mode,
                massage=massage,
                sound=sound,
            ),
            cancel_event=asyncio.Event(),
        )
        self.forward_controller_state_updates(
            {
                "solace_alarm_enabled": enabled,
                "solace_alarm_time": f"{hour:02d}:{minute:02d}",
                "solace_alarm_weekdays": ",".join(
                    str(day) for day in sorted(set(weekdays))
                ),
                "solace_alarm_mode": mode,
                "solace_alarm_massage": massage,
                "solace_alarm_sound": sound,
            }
        )

    def _preset_is_selected(self, key: str) -> bool:
        """Return the last state proven by a query response or command echo."""
        return bool(self._coordinator.controller_state.get(f"solace_{key}_selected", False))

    # Massage methods
    @property
    def supports_massage(self) -> bool:
        """Return whether the selected Home profile exposes massage."""
        return self.profile in {SolaceProfile.HOME_K1, SolaceProfile.HOME_K2}

    @property
    def auto_enable_massage(self) -> bool:
        """Auto-enable massage only where the app proves it is always present."""
        return self.supports_massage

    @property
    def supports_massage_off_control(self) -> bool:
        return self.supports_massage

    @property
    def supports_massage_intensity_step_control(self) -> bool:
        # The overall +/- label was historical; 0x14/0x15 are wave controls.
        return False

    @property
    def supports_head_massage_intensity_step_control(self) -> bool:
        return self.supports_massage

    @property
    def supports_foot_massage_intensity_step_control(self) -> bool:
        return self.supports_massage

    @property
    def supports_massage_wave_frequency_control(self) -> bool:
        return self.supports_massage

    async def massage_wave_frequency_up(self) -> None:
        """Increase the Home profile's massage wave frequency."""
        await self.write_command(SolaceCommands.MASSAGE_FREQUENCY_UP)

    async def massage_wave_frequency_down(self) -> None:
        """Decrease the Home profile's massage wave frequency."""
        await self.write_command(SolaceCommands.MASSAGE_FREQUENCY_DOWN)

    async def massage_head_up(self) -> None:
        """Increase head massage intensity."""
        await self.write_command(SolaceCommands.MASSAGE_HEAD_UP)

    async def massage_head_down(self) -> None:
        """Decrease head massage intensity."""
        await self.write_command(SolaceCommands.MASSAGE_HEAD_DOWN)

    async def massage_foot_up(self) -> None:
        """Increase foot massage intensity."""
        await self.write_command(SolaceCommands.MASSAGE_FOOT_UP)

    async def massage_foot_down(self) -> None:
        """Decrease foot massage intensity."""
        await self.write_command(SolaceCommands.MASSAGE_FOOT_DOWN)

    async def massage_intensity_up(self) -> None:
        """Increase massage frequency."""
        await self.write_command(SolaceCommands.MASSAGE_FREQUENCY_UP)

    async def massage_intensity_down(self) -> None:
        """Decrease massage frequency."""
        await self.write_command(SolaceCommands.MASSAGE_FREQUENCY_DOWN)

    async def massage_off(self) -> None:
        """Stop all massage."""
        await self.write_command(SolaceCommands.MASSAGE_STOP)

    # Hip motor support — not all Solace/QMS beds have a hip motor.
    # The smartbed-mqtt reference only exposes Back, Legs, Lift, Tilt.
    # Hip commands (0x0D/0x0E) exist in the protocol but are model-specific.

    async def move_hip_up(self) -> None:
        """Move hip motor up."""
        await self._move_with_stop(SolaceCommands.MOTOR_HIP_UP)

    async def move_hip_down(self) -> None:
        """Move hip motor down."""
        await self._move_with_stop(SolaceCommands.MOTOR_HIP_DOWN)

    async def move_hip_stop(self) -> None:
        """Stop hip motor."""
        await self.move_head_stop()

    async def move_lumbar_up(self) -> None:
        """Raise the lumbar axis used by Home K2 layouts."""
        await self._move_with_stop(SolaceCommands.MOTOR_HIP_UP)

    async def move_lumbar_down(self) -> None:
        """Lower the lumbar axis used by Home K2 layouts."""
        await self._move_with_stop(SolaceCommands.MOTOR_HIP_DOWN)

    async def move_lumbar_stop(self) -> None:
        """Stop the lumbar motor."""
        await self.move_head_stop()

    async def move_lift_up(self) -> None:
        """Raise the height axis on the hardware-confirmed S4-Y layout."""
        await self._move_with_stop(SolaceCommands.MOTOR_LIFT_UP)

    async def move_lift_down(self) -> None:
        """Lower the height axis on the hardware-confirmed S4-Y layout."""
        await self._move_with_stop(SolaceCommands.MOTOR_LIFT_DOWN)

    async def move_lift_stop(self) -> None:
        """Stop the height axis."""
        await self.move_head_stop()

    async def move_tilt_up(self) -> None:
        """Raise the tilt axis on the hardware-confirmed S4-Y layout."""
        await self._move_with_stop(SolaceCommands.MOTOR_TILT_UP)

    async def move_tilt_down(self) -> None:
        """Lower the tilt axis on the hardware-confirmed S4-Y layout."""
        await self._move_with_stop(SolaceCommands.MOTOR_TILT_DOWN)

    async def move_tilt_stop(self) -> None:
        """Stop the tilt axis."""
        await self.move_head_stop()

    # Light control
    @property
    def supports_lights(self) -> bool:
        """Return whether MotionFlex proves direct brightness control."""
        return self.profile is SolaceProfile.MOTION_FLEX

    async def lights_on(self) -> None:
        """Turn lights on (set to max brightness)."""
        await self.write_command(SolaceCommands.LIGHT_LEVEL_10)
        self.forward_controller_state_update("light_level", 10)

    async def lights_off(self) -> None:
        """Turn lights off."""
        await self.write_command(SolaceCommands.LIGHT_LEVEL_0)
        self.forward_controller_state_update("light_level", 0)

    @property
    def supports_light_level_control(self) -> bool:
        """Return whether MotionFlex proves levels 0 through 10."""
        return self.profile is SolaceProfile.MOTION_FLEX

    @property
    def light_level_max(self) -> int:
        """Return maximum light level (10)."""
        return 10

    async def set_light_level(self, level: int) -> None:
        """Set light level (0-10)."""
        commands = [
            SolaceCommands.LIGHT_LEVEL_0,
            SolaceCommands.LIGHT_LEVEL_1,
            SolaceCommands.LIGHT_LEVEL_2,
            SolaceCommands.LIGHT_LEVEL_3,
            SolaceCommands.LIGHT_LEVEL_4,
            SolaceCommands.LIGHT_LEVEL_5,
            SolaceCommands.LIGHT_LEVEL_6,
            SolaceCommands.LIGHT_LEVEL_7,
            SolaceCommands.LIGHT_LEVEL_8,
            SolaceCommands.LIGHT_LEVEL_9,
            SolaceCommands.LIGHT_LEVEL_10,
        ]
        if 0 <= level <= 10:
            await self.write_command(commands[level])
            self.forward_controller_state_update("light_level", level)
        else:
            _LOGGER.warning("Invalid light level: %d (valid: 0-10)", level)

    # Light timer control
    @property
    def supports_light_timer(self) -> bool:
        """Return whether the accepted profile exposes the timer frames."""
        return self.profile not in {
            SolaceProfile.LEGACY_S4_Y,
            SolaceProfile.UNVERIFIED,
        }

    @property
    def light_timer_options(self) -> list[str]:
        """Return available light timer options."""
        options = ["10 min", "8 hours", "10 hours"]
        if self.profile is SolaceProfile.MOTION_FLEX:
            return ["Off", *options]
        return options

    async def set_light_timer(self, timer_option: str) -> None:
        """Set light timer.

        Args:
            timer_option: One of "Off", "10 min", "8 hours", "10 hours"
        """
        commands = {
            "Off": SolaceCommands.LIGHT_LEVEL_0,  # Turn off light
            "10 min": SolaceCommands.LIGHT_TIMER_10_MIN,
            "8 hours": SolaceCommands.LIGHT_TIMER_8_HOURS,
            "10 hours": SolaceCommands.LIGHT_TIMER_10_HOURS,
        }
        if cmd := commands.get(timer_option):
            await self.write_command(cmd)
        else:
            _LOGGER.warning("Invalid light timer option: %s", timer_option)

    # Circulation massage support
    @property
    def supports_circulation_massage(self) -> bool:
        """Expose cycle labels only where the fourth zone is proven as hip."""
        return self.profile is SolaceProfile.HOME_K1

    async def massage_circulation_full_body(self) -> None:
        """Start full body circulation massage."""
        await self.write_command(SolaceCommands.MASSAGE_CIRCULATION_FULL_BODY)

    async def massage_circulation_head(self) -> None:
        """Start head circulation massage."""
        await self.write_command(SolaceCommands.MASSAGE_CIRCULATION_HEAD)

    async def massage_circulation_leg(self) -> None:
        """Start leg circulation massage."""
        await self.write_command(SolaceCommands.MASSAGE_CIRCULATION_LEG)

    async def massage_circulation_hip(self) -> None:
        """Start hip circulation massage."""
        await self.write_command(SolaceCommands.MASSAGE_CIRCULATION_HIP)

    # Massage timer support
    @property
    def supports_massage_timer(self) -> bool:
        """Return whether the selected Home profile exposes massage timers."""
        return self.supports_massage

    @property
    def massage_timer_options(self) -> list[int]:
        """Return available timer durations in minutes."""
        return [10, 20, 30]

    async def set_massage_timer(self, minutes: int) -> None:
        """Set massage auto-off timer (0=off, 10/20/30 minutes)."""
        commands = {
            0: SolaceCommands.MASSAGE_STOP,
            10: SolaceCommands.MASSAGE_TIMER_10_MIN,
            20: SolaceCommands.MASSAGE_TIMER_20_MIN,
            30: SolaceCommands.MASSAGE_TIMER_30_MIN,
        }
        if cmd := commands.get(minutes):
            await self.write_command(cmd)
        else:
            _LOGGER.warning("Invalid massage timer: %d min (valid: 0, 10, 20, 30)", minutes)
