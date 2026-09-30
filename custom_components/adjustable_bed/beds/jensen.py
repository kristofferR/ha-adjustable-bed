"""Jensen JMC400 bed controller.

Protocol from the clean-room APK Protocol Audits of ``air.no.jensen.adjustablesleep``
2.0.29 (98) and 2.0.37 (106). See docs/beds/jensen.md for the frame table and the
evidence behind each behavior.

The app treats the four position bytes of a ``0x10`` report as opaque and only
echoes them back in go-to frames. Their byte order and physical scale come from
a JMC400 capture (issue #631): unsigned 16-bit little-endian values, with the
foot value falling as the foot rises.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Callable, Mapping
from enum import IntFlag
from typing import TYPE_CHECKING, Any

from bleak.backends.characteristic import BleakGATTCharacteristic
from bleak.exc import BleakError
from homeassistant.helpers.storage import Store

from ..const import DOMAIN, JENSEN_CHAR_UUID, JENSEN_SERVICE_UUID
from .base import (
    POSITION_UNIT_PERCENT,
    BedController,
    PositionNumberSpec,
    build_position_number_spec,
)

if TYPE_CHECKING:
    from ..coordinator import AdjustableBedCoordinator

_LOGGER = logging.getLogger(__name__)

# Raw position anchors measured on a JMC400 (issue #631). The app never scales
# positions, so these are hardware calibration rather than app evidence.
HEAD_POS_FLAT = 30000
HEAD_POS_MAX = 30804
FOOT_POS_FLAT = 30000
FOOT_POS_MAX = 29369  # The foot value falls as the foot rises.

_CONFIG_RESPONSE_TIMEOUT = 5.0
_POSITION_RESPONSE_TIMEOUT = 5.0
# Integration safeguards for autonomous moves, not hardware deadlines. The bed
# pushes a report about every 0.5 s while it moves (issue #631).
_MOVEMENT_START_SECONDS = 3.0
_MOVEMENT_STALL_SECONDS = 2.0
_MOVEMENT_FEEDBACK_TIMEOUT_SECONDS = 90.0
# A moving bed can pause its reports for about 2 s (issue #631), so the closing
# read repeats until two replies agree, within a bound.
_SETTLE_READ_INTERVAL_SECONDS = 1.0
_SETTLE_TIMEOUT_SECONDS = 10.0
# Report state bytes that do not indicate motion: idle, and the reply to a query.
_IDLE_MOTION_STATES = frozenset({0x00, 0xFF})

# Boxes of this type keep one memory slot on the device; every other box type
# keeps the app's favourites as stored positions.
_DEVICE_MEMORY_BOX_TYPE = 4
_APP_MEMORY_SLOT_COUNT = 4
_MEMORY_STORE_KEY = f"{DOMAIN}.jensen_memory"
_MEMORY_STORE_VERSION = 1

_LEVEL_MAX = 10

_BACK_FLAGS = {True: 0x01, False: 0x02}
_LEGS_FLAGS = {True: 0x10, False: 0x20}


def _decode_config_field(value: int) -> int:
    """Decode a config byte the way the app does.

    The app prefixes the byte's decimal digits with ``0x`` and parses the
    result, so a report byte of 16 becomes 0x16.
    """
    return int(str(value), 16)


class JensenCommands:
    """Jensen command frames.

    Frames have no checksum. Every frame's first byte is its opcode:
    0x0A config, 0x10 motion/preset/position, 0x12 massage, 0x13 light,
    0x14 fan, 0x1E PIN.
    """

    CONFIG_READ_ALL = bytes([0x0A, 0x00, 0x00, 0x00, 0x00])

    MOTOR_STOP = bytes([0x10, 0x00, 0x00, 0x00, 0x00, 0x00])
    MOTOR_HEAD_UP = bytes([0x10, 0x01, 0x00, 0x00, 0x00, 0x00])
    MOTOR_HEAD_DOWN = bytes([0x10, 0x02, 0x00, 0x00, 0x00, 0x00])
    MOTOR_FOOT_UP = bytes([0x10, 0x10, 0x00, 0x00, 0x00, 0x00])
    MOTOR_FOOT_DOWN = bytes([0x10, 0x20, 0x00, 0x00, 0x00, 0x00])

    PRESET_FLAT = bytes([0x10, 0x81, 0x00, 0x00, 0x00, 0x00])
    PRESET_MEMORY_SAVE = bytes([0x10, 0x40, 0x00, 0x00, 0x00, 0x00])
    PRESET_MEMORY_RECALL = bytes([0x10, 0x80, 0x00, 0x00, 0x00, 0x00])

    # Not sent by the app. The bed answers it with a 0x10 position report
    # (issue #631), and it doubles as the 0x10 warm-up some beds need after
    # reconnect before they accept flat (issue #217).
    READ_POSITION = bytes([0x10, 0xFF, 0x00, 0x00, 0x00, 0x00])

    MASSAGE_OFF = bytes([0x12, 0x00, 0x00, 0x00, 0x00, 0x00])
    # A fixed frame in 2.0.37, unlike the level frame's layout.
    LIGHT_OFF = bytes([0x13, 0x02, 0x00, 0x00, 0x00, 0x32])
    FAN_OFF = bytes([0x14, 0x00, 0x00, 0x00, 0x00, 0x50])

    @staticmethod
    def pin_unlock(digits: str) -> bytes:
        """Build the 5-byte PIN frame from four decimal digits."""
        return bytes([0x1E, *(int(digit) for digit in digits)])

    @staticmethod
    def motion(back_up: bool | None, legs_up: bool | None) -> bytes:
        """Build a held-motion frame; either section may be idle (None)."""
        flags = 0
        if back_up is not None:
            flags |= _BACK_FLAGS[back_up]
        if legs_up is not None:
            flags |= _LEGS_FLAGS[legs_up]
        return bytes([0x10, flags, 0x00, 0x00, 0x00, 0x00])

    @staticmethod
    def goto_position(head_raw: int, foot_raw: int) -> bytes:
        """Build a go-to frame in the byte order of the bed's position reports."""
        return bytes([0x10, 0x04, *head_raw.to_bytes(2, "little"), *foot_raw.to_bytes(2, "little")])

    @staticmethod
    def massage(head: int, foot: int, wave: int) -> bytes:
        """Build a massage frame; each level is 0-10 and 0 turns that part off."""
        return bytes([0x12, head, foot, wave, 0x00, 0x00])

    @staticmethod
    def light(level: int) -> bytes:
        """Build a light frame; the app drives every light kind through output 2."""
        return bytes([0x13, 0x02, level, 0x00, 0x00, 0x00])

    @staticmethod
    def fan(level: int) -> bytes:
        """Build a fan frame for level 0-10."""
        return bytes([0x14, level, 0x00, 0x00, 0x00, 0x50])


class JensenFeatureFlags(IntFlag):
    """Feature flags decoded from byte 2 of the config report."""

    NONE = 0
    MASSAGE_HEAD = 0x01
    MASSAGE_FOOT = 0x02
    LIGHT = 0x04
    FAN = 0x10
    LIGHT_UNDERBED = 0x40


_LIGHT_FLAGS = JensenFeatureFlags.LIGHT | JensenFeatureFlags.LIGHT_UNDERBED
_MASSAGE_FLAGS = JensenFeatureFlags.MASSAGE_HEAD | JensenFeatureFlags.MASSAGE_FOOT


def _raw_to_percentage(raw: int, flat: int, full: int) -> float:
    """Map a raw position onto 0-100 %, for axes that rise or fall with travel."""
    return max(0.0, min(100.0, (raw - flat) / (full - flat) * 100))


def _percentage_to_raw(percentage: float, flat: int, full: int) -> int:
    """Map 0-100 % onto a raw position."""
    percentage = max(0.0, min(100.0, percentage))
    return round(flat + percentage / 100 * (full - flat))


class JensenController(BedController):
    """Controller for Jensen JMC400 beds."""

    DEFAULT_PIN: str = "3060"

    def __init__(
        self,
        coordinator: AdjustableBedCoordinator,
        pin: str = "",
        capability_snapshot: Mapping[str, Any] | None = None,
    ) -> None:
        """Initialize the Jensen controller.

        ``capability_snapshot`` is the last config report stored for this bed. It
        sets the capabilities until this connection's report arrives, stands in
        when that request goes unanswered, and lets an offline paired side build
        its entities.
        """
        super().__init__(coordinator)
        self._notify_callback: Callable[[str, float], None] | None = None
        self._features: JensenFeatureFlags = JensenFeatureFlags.NONE
        self._box_type: int | None = None
        self._config_loaded: bool = False
        self._config_received: asyncio.Event | None = None
        self._config_data: bytes | None = None
        self._position_received: asyncio.Event | None = None
        self._position_query_lock = asyncio.Lock()
        # Set by every 0x10 report; movement monitoring waits on it.
        self._position_update = asyncio.Event()
        self._raw_positions: tuple[int, int] | None = None
        self._motion_state: int | None = None
        self._memory_slots: dict[int, tuple[int, int]] = {}
        # The bed does not report massage, light or fan state, so these track
        # what this integration last sent.
        self._massage_levels: dict[str, int] = {"head": 0, "foot": 0, "wave": 0}
        self._light_level: int = 0
        self._last_light_level: int = _LEVEL_MAX
        self._fan_level: int = 0
        self._write_with_response: bool = False
        self._pin: str = pin if pin else self.DEFAULT_PIN
        # The config report as the bed sent it; None until one has been received.
        self._reported_config: tuple[JensenFeatureFlags, int] | None = None
        if capability_snapshot is not None:
            with contextlib.suppress(KeyError, TypeError, ValueError):
                self._reported_config = (
                    JensenFeatureFlags(int(capability_snapshot["features"])),
                    int(capability_snapshot["box_type"]),
                )
        if self._reported_config is not None:
            self._features, self._box_type = self._reported_config
        _LOGGER.debug("JensenController initialized with PIN: %s", "*" * len(self._pin))

    def capability_snapshot(self) -> dict[str, Any] | None:
        """Return the bed-reported features and box type, once known."""
        if self._reported_config is None:
            return None
        features, box_type = self._reported_config
        return {"features": int(features), "box_type": box_type}

    @property
    def control_characteristic_uuid(self) -> str:
        """Return the UUID of the control characteristic."""
        return JENSEN_CHAR_UUID

    @property
    def requires_notification_channel(self) -> bool:
        """Jensen uses notifications for config reads and PIN-gated handshakes."""
        return True

    def _build_pin_unlock_command(self) -> bytes:
        """Build the PIN frame, falling back to the default for an invalid PIN."""
        sanitized = "".join(c for c in self._pin.strip() if c.isdigit())
        if not sanitized:
            _LOGGER.warning("Invalid Jensen PIN configured, using default '%s'", self.DEFAULT_PIN)
            sanitized = self.DEFAULT_PIN
        return JensenCommands.pin_unlock(sanitized.ljust(4, "0")[:4])

    async def send_pin(self) -> None:
        """Send the PIN frame that authorizes Jensen commands."""
        if self.client is None or not self.client.is_connected:
            _LOGGER.warning("Cannot send Jensen PIN unlock command: not connected")
            return

        try:
            await self._write_gatt_with_retry(
                JENSEN_CHAR_UUID,
                self._build_pin_unlock_command(),
                response=self._write_with_response,
            )
        except (ValueError, BleakError) as err:
            _LOGGER.warning("Failed to send Jensen PIN unlock command: %s", err)

    # Capabilities
    @property
    def supports_preset_flat(self) -> bool:
        """Return True - Jensen beds have a dedicated flat command."""
        return True

    @property
    def uses_device_memory(self) -> bool:
        """Return True when the box stores its memory slot on the device."""
        return self._box_type == _DEVICE_MEMORY_BOX_TYPE

    @property
    def supports_memory_presets(self) -> bool:
        """Return True - device and app-stored memories can both be recalled."""
        return True

    @property
    def memory_slot_count(self) -> int:
        """Return the box's memory slots: one on the device, else four app-stored."""
        return 1 if self.uses_device_memory else _APP_MEMORY_SLOT_COUNT

    @property
    def supports_memory_programming(self) -> bool:
        """Return True - both memory kinds can be programmed."""
        return True

    @property
    def supports_simultaneous_movement(self) -> bool:
        """Return True - one motion frame can drive back and legs together."""
        return True

    @property
    def simultaneous_movement_axes(self) -> tuple[str, ...]:
        """Return the two sections a combined motion frame can drive."""
        return ("back", "legs")

    @property
    def supports_lights(self) -> bool:
        """Return True if the config report lists any light."""
        return bool(self._features & _LIGHT_FLAGS)

    @property
    def supports_discrete_light_control(self) -> bool:
        """Return True if bed has discrete on/off light commands."""
        return self.supports_lights

    @property
    def supports_light_level_control(self) -> bool:
        """Return True if the light level can be set directly."""
        return self.supports_lights

    @property
    def light_level_max(self) -> int:
        """Return the maximum light level."""
        return _LEVEL_MAX

    @property
    def has_massage(self) -> bool:
        """Return True if bed has any massage motor (determined dynamically)."""
        return bool(self._features & _MASSAGE_FLAGS)

    @property
    def has_massage_head(self) -> bool:
        """Return True if bed has head massage motor."""
        return bool(self._features & JensenFeatureFlags.MASSAGE_HEAD)

    @property
    def has_massage_foot(self) -> bool:
        """Return True if bed has foot massage motor."""
        return bool(self._features & JensenFeatureFlags.MASSAGE_FOOT)

    @property
    def has_fan(self) -> bool:
        """Return True if bed has fan (determined dynamically)."""
        return bool(self._features & JensenFeatureFlags.FAN)

    @property
    def supports_fan_level_control(self) -> bool:
        """Return True if the fan level can be set directly."""
        return self.has_fan

    @property
    def fan_level_max(self) -> int:
        """Return the maximum fan level."""
        return _LEVEL_MAX if self.has_fan else 0

    @property
    def supports_direct_position_control(self) -> bool:
        """Return True - Jensen beds accept absolute go-to frames."""
        return True

    @property
    def supports_position_feedback(self) -> bool:
        """Return True - Jensen beds report position via notifications."""
        return True

    @property
    def reports_percentage_position(self) -> bool:
        """Return True because Jensen normalizes reported positions to percentages."""
        return True

    @property
    def position_number_specs(self) -> tuple[PositionNumberSpec, ...]:
        """Expose back and legs as percentage sliders."""
        return (
            build_position_number_spec("back", max_value=100.0, unit=POSITION_UNIT_PERCENT),
            build_position_number_spec("legs", max_value=100.0, unit=POSITION_UNIT_PERCENT),
        )

    @property
    def supports_massage_intensity_control(self) -> bool:
        """Return True when any massage zone is present."""
        return self.has_massage

    @property
    def massage_intensity_zones(self) -> list[str]:
        """Return the massage zones with direct level control."""
        zones: list[str] = []
        if self.has_massage_head:
            zones.append("head")
        if self.has_massage_foot:
            zones.append("foot")
        if zones:
            zones.append("wave")
        return zones

    @property
    def massage_intensity_max(self) -> int:
        """Return maximum massage intensity level (0-10 scale)."""
        return _LEVEL_MAX

    async def async_discover_capabilities(self) -> None:
        """Load the app-stored memory positions saved for this bed."""
        stored = await self._memory_store().async_load()
        self._memory_slots = {}
        for slot, values in (stored if isinstance(stored, dict) else {}).items():
            try:
                self._memory_slots[int(slot)] = (int(values[0]), int(values[1]))
            except (IndexError, TypeError, ValueError):
                _LOGGER.warning("Ignoring unreadable Jensen memory slot %r: %r", slot, values)

    def _memory_store(self) -> Store[dict[str, list[int]]]:
        # One file per bed, so the two sides of a pair never overwrite each other.
        address = self._coordinator.address.replace(":", "_").lower()
        return Store(
            self._coordinator.hass, _MEMORY_STORE_VERSION, f"{_MEMORY_STORE_KEY}.{address}"
        )

    async def _save_memory_slots(self) -> None:
        await self._memory_store().async_save(
            {str(slot): list(values) for slot, values in self._memory_slots.items()}
        )

    def _use_stored_config(self, fallback: JensenFeatureFlags) -> None:
        """Keep the last reported config when this connection's report is missing."""
        if self._reported_config is not None:
            _LOGGER.info("Using the stored Jensen config")
            self._features, self._box_type = self._reported_config
        else:
            _LOGGER.warning("No stored Jensen config, assuming features %s", fallback)
            self._features = fallback

    async def query_config(self) -> None:
        """Read the bed's feature flags and box type after connection."""
        if self._config_loaded:
            _LOGGER.debug("Jensen config already loaded, skipping query")
            return

        if self.client is None or not self.client.is_connected:
            _LOGGER.warning("Cannot query config: not connected")
            return

        _LOGGER.debug("Querying Jensen bed configuration...")
        self._config_received = asyncio.Event()
        self._config_data = None

        try:
            await self._write_gatt_with_retry(
                JENSEN_CHAR_UUID,
                JensenCommands.CONFIG_READ_ALL,
                response=self._write_with_response,
            )

            try:
                await asyncio.wait_for(
                    self._config_received.wait(),
                    timeout=_CONFIG_RESPONSE_TIMEOUT,
                )
            except TimeoutError:
                _LOGGER.warning("Timeout waiting for Jensen config response")
                self._use_stored_config(_MASSAGE_FLAGS | _LIGHT_FLAGS | JensenFeatureFlags.FAN)
                return

            data = self._config_data
            if data is not None and len(data) >= 5:
                self._features = JensenFeatureFlags(_decode_config_field(data[2]))
                self._box_type = _decode_config_field(data[4])
                self._reported_config = (self._features, self._box_type)
                _LOGGER.info(
                    "Jensen bed features: %s, box type %d (raw: %s)",
                    self._features,
                    self._box_type,
                    data.hex(),
                )
            else:
                _LOGGER.warning("Unusable Jensen config response: %s", data.hex() if data else None)
                self._use_stored_config(JensenFeatureFlags.NONE)

        except BleakError as err:
            _LOGGER.warning("Failed to query config: %s", err)
            self._use_stored_config(JensenFeatureFlags.NONE)
        finally:
            self._config_loaded = True
            self._config_received = None
            self._config_data = None

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 100,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        """Write a command to the bed."""
        _LOGGER.debug(
            "Writing command to Jensen bed: %s (repeat: %d, delay: %dms, response=%s)",
            command.hex(),
            repeat_count,
            repeat_delay_ms,
            self._write_with_response,
        )

        await self._write_gatt_with_retry(
            JENSEN_CHAR_UUID,
            command,
            repeat_count=repeat_count,
            repeat_delay_ms=repeat_delay_ms,
            cancel_event=cancel_event,
            response=self._write_with_response,
        )

    def _handle_notification(self, _sender: BleakGATTCharacteristic, data: bytearray) -> None:
        """Handle a report from the bed.

        Position report: [0x10, motion state, head u16 LE, foot u16 LE].
        """
        self.forward_raw_notification(JENSEN_CHAR_UUID, bytes(data))

        if not data:
            return
        opcode = data[0]

        if opcode == 0x10 and len(data) >= 6:
            head_raw = int.from_bytes(data[2:4], "little")
            foot_raw = int.from_bytes(data[4:6], "little")
            self._raw_positions = (head_raw, foot_raw)
            self._motion_state = data[1]
            _LOGGER.debug(
                "Jensen position report: state=0x%02X head_raw=%d foot_raw=%d",
                data[1],
                head_raw,
                foot_raw,
            )

            self._position_update.set()
            if self._position_received is not None:
                self._position_received.set()

            if self._notify_callback:
                self._notify_callback(
                    "back", _raw_to_percentage(head_raw, HEAD_POS_FLAT, HEAD_POS_MAX)
                )
                self._notify_callback(
                    "legs", _raw_to_percentage(foot_raw, FOOT_POS_FLAT, FOOT_POS_MAX)
                )

        elif opcode == 0x0A:
            _LOGGER.debug("Jensen config notification: %s", data.hex())
            if self._config_received is not None:
                self._config_data = bytes(data)
                self._config_received.set()

        elif opcode == 0x1E and len(data) >= 2:
            # The app reads byte 1 as hex text; only 1 means unlocked.
            if _decode_config_field(data[1]) != 1:
                _LOGGER.warning(
                    "Jensen bed at %s rejected the configured PIN; check the Jensen PIN option",
                    self._coordinator.address,
                )

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        """Subscribe to reports, unlock with the PIN and warm up command acceptance.

        This must run even when angle sensing is disabled, because the PIN and
        config handshake depend on the notification channel.
        """
        self._notify_callback = callback

        if self.client is None or not self.client.is_connected:
            _LOGGER.warning("Cannot start Jensen notifications: not connected")
            return

        if self.client.services:
            for service in self.client.services:
                if str(service.uuid).lower() != JENSEN_SERVICE_UUID.lower():
                    continue
                for char in service.characteristics:
                    if str(char.uuid).lower() != JENSEN_CHAR_UUID.lower():
                        continue
                    props = {prop.lower() for prop in char.properties}
                    # The app writes without response; use a response only
                    # when the characteristic cannot do otherwise.
                    self._write_with_response = (
                        "write-without-response" not in props and "write" in props
                    )
                    _LOGGER.info(
                        "Jensen characteristic %s properties %s, write %s",
                        char.uuid,
                        char.properties,
                        "with response" if self._write_with_response else "without response",
                    )

        try:
            async with self._ble_lock:
                await self.client.start_notify(JENSEN_CHAR_UUID, self._handle_notification)
            _LOGGER.info("Started position notifications for Jensen bed")

            await self.send_pin()

            # Some beds ignore the first flat preset after reconnect unless they
            # have already seen a 0x10 frame (issue #217). Wait for the reply so
            # it cannot satisfy a later position read.
            try:
                await self.read_positions()
            except TimeoutError:
                _LOGGER.warning("Timeout waiting for Jensen warm-up position response, continuing")

        except (BleakError, ConnectionError) as err:
            _LOGGER.warning("Failed to start Jensen notifications: %s", err)
            self.log_discovered_services(level=logging.INFO)

    async def stop_notify(self) -> None:
        """Stop listening for position notifications."""
        if self.client is None or not self.client.is_connected:
            return

        try:
            async with self._ble_lock:
                await self.client.stop_notify(JENSEN_CHAR_UUID)
            _LOGGER.debug("Stopped Jensen position notifications")
        except BleakError:
            pass

    async def _send_position_query(self) -> bool:
        """Send READ_POSITION and report whether the write succeeded."""
        if self.client is None or not self.client.is_connected:
            _LOGGER.debug("Cannot read positions: not connected")
            return False

        try:
            await self._write_gatt_with_retry(
                JENSEN_CHAR_UUID,
                JensenCommands.READ_POSITION,
                cancel_event=asyncio.Event(),
                response=self._write_with_response,
            )
            _LOGGER.debug("Sent READ_POSITION command to Jensen bed")
            return True
        except (BleakError, ConnectionError) as err:
            _LOGGER.warning("Failed to send READ_POSITION command: %s", err)
            return False

    async def read_positions(self, motor_count: int = 2) -> None:  # noqa: ARG002
        """Read current positions via the asynchronous report that answers a query."""
        del motor_count  # Jensen always reports both motors
        async with self._position_query_lock:
            position_received = asyncio.Event()
            self._position_received = position_received
            try:
                if not await self._send_position_query():
                    raise ConnectionError("Failed to send Jensen position query")
                async with asyncio.timeout(_POSITION_RESPONSE_TIMEOUT):
                    await position_received.wait()
            finally:
                if self._position_received is position_received:
                    self._position_received = None

    async def _wait_for_position_update(self, timeout: float, cancel_event: asyncio.Event) -> bool:
        """Return whether a new position report arrives before ``timeout``."""
        self._position_update.clear()
        update = asyncio.ensure_future(self._position_update.wait())
        cancelled = asyncio.ensure_future(cancel_event.wait())
        try:
            await asyncio.wait(
                (update, cancelled), timeout=timeout, return_when=asyncio.FIRST_COMPLETED
            )
        finally:
            update.cancel()
            cancelled.cancel()
        if cancel_event.is_set():
            raise asyncio.CancelledError
        return self._position_update.is_set()

    async def _monitor_movement(self) -> None:
        """Hold the command until reports show the bed has stopped moving.

        The bed moves autonomously after a single preset or go-to frame, so an
        acknowledged write says nothing about completion. Motion is a report
        with a moving state or a changed position; it has ended once reports
        stop, or once an idle report repeats the last position.
        """
        if self._coordinator.disable_angle_sensing:
            return
        cancel_event = self._coordinator.cancel_command
        loop = asyncio.get_running_loop()
        start_deadline = loop.time() + _MOVEMENT_START_SECONDS
        moving = False
        last_positions = self._raw_positions
        try:
            async with asyncio.timeout(_MOVEMENT_FEEDBACK_TIMEOUT_SECONDS):
                while True:
                    wait = (
                        _MOVEMENT_STALL_SECONDS
                        if moving
                        else max(0.0, start_deadline - loop.time())
                    )
                    if not await self._wait_for_position_update(wait, cancel_event):
                        break
                    changed = self._raw_positions != last_positions
                    last_positions = self._raw_positions
                    idle = self._motion_state in _IDLE_MOTION_STATES
                    if changed or not idle:
                        moving = True
                    elif moving:
                        break
        except TimeoutError:
            _LOGGER.warning(
                "Jensen bed at %s still reported movement after %.0f s; stopping it",
                self._coordinator.address,
                _MOVEMENT_FEEDBACK_TIMEOUT_SECONDS,
            )
            try:
                await asyncio.shield(self._send_stop())
            except (BleakError, ConnectionError):
                _LOGGER.debug("Failed to send Jensen STOP after the movement timeout")
            return
        try:
            await self._read_settled_positions(cancel_event)
        except (TimeoutError, ConnectionError, BleakError) as err:
            _LOGGER.debug("Jensen final position read failed: %s", err)

    async def _read_settled_positions(self, cancel_event: asyncio.Event) -> None:
        """Query positions until two consecutive replies agree.

        Silence does not prove the move ended: the bed can go quiet while it
        still travels. Queries do not interrupt an autonomous move (#631).
        """
        loop = asyncio.get_running_loop()
        deadline = loop.time() + _SETTLE_TIMEOUT_SECONDS
        previous: tuple[int, int] | None = None
        while True:
            await self.read_positions()
            if self._raw_positions == previous:
                return
            previous = self._raw_positions
            remaining = deadline - loop.time()
            if remaining <= 0:
                _LOGGER.debug(
                    "Jensen bed at %s still moving after %.0f s of settle reads",
                    self._coordinator.address,
                    _SETTLE_TIMEOUT_SECONDS,
                )
                return
            try:
                await asyncio.wait_for(
                    cancel_event.wait(), min(_SETTLE_READ_INTERVAL_SECONDS, remaining)
                )
            except TimeoutError:
                continue
            raise asyncio.CancelledError

    async def _run_monitored(self, command: bytes, repeat_count: int = 1) -> None:
        """Send an autonomous-move frame and follow the move to completion.

        If the move is cancelled, replaced or fails, STOP is sent while this
        command still owns the connection.
        """
        try:
            await self.write_command(
                command,
                repeat_count=repeat_count,
                repeat_delay_ms=self._coordinator.motor_pulse_delay_ms,
            )
            await self._monitor_movement()
        except BaseException:
            try:
                await asyncio.shield(self._send_stop())
            except (BleakError, ConnectionError):
                _LOGGER.debug("Failed to send Jensen STOP after an interrupted move")
            raise

    async def _send_stop(self) -> None:
        await self.write_command(JensenCommands.MOTOR_STOP, cancel_event=asyncio.Event())

    async def _move_with_stop(self, command: bytes, duration_ms: int | None = None) -> None:
        """Repeat a held-motion frame, then always send STOP."""
        pulse_count, pulse_delay = self.motor_pulse_settings()
        if duration_ms is not None:
            pulse_count = self.timed_move_repeat_count(duration_ms, pulse_delay)
        try:
            await self.write_command(
                command,
                repeat_count=pulse_count,
                repeat_delay_ms=pulse_delay,
            )
        finally:
            try:
                await self._send_stop()
            except (BleakError, ConnectionError):
                _LOGGER.debug("Failed to send STOP command during cleanup")

    # Motor control methods
    async def move_head_up(self) -> None:
        """Move head up."""
        await self._move_with_stop(JensenCommands.MOTOR_HEAD_UP)

    async def move_head_down(self) -> None:
        """Move head down."""
        await self._move_with_stop(JensenCommands.MOTOR_HEAD_DOWN)

    async def move_head_stop(self) -> None:
        """Stop head motor."""
        await self._send_stop()

    async def move_back_up(self) -> None:
        """Move back up (same as head for Jensen)."""
        await self.move_head_up()

    async def move_back_down(self) -> None:
        """Move back down (same as head for Jensen)."""
        await self.move_head_down()

    async def move_back_stop(self) -> None:
        """Stop back motor (same as head for Jensen)."""
        await self._send_stop()

    async def move_legs_up(self) -> None:
        """Move legs/feet up."""
        await self._move_with_stop(JensenCommands.MOTOR_FOOT_UP)

    async def move_legs_down(self) -> None:
        """Move legs/feet down."""
        await self._move_with_stop(JensenCommands.MOTOR_FOOT_DOWN)

    async def move_legs_stop(self) -> None:
        """Stop legs motor."""
        await self._send_stop()

    async def move_feet_up(self) -> None:
        """Move feet up (same as legs for Jensen)."""
        await self.move_legs_up()

    async def move_feet_down(self) -> None:
        """Move feet down (same as legs for Jensen)."""
        await self.move_legs_down()

    async def move_feet_stop(self) -> None:
        """Stop feet motor."""
        await self._send_stop()

    async def stop_all(self) -> None:
        """Stop all motors."""
        await self._send_stop()

    async def move_simultaneously(
        self,
        first_axis: str,
        first_up: bool,
        second_axis: str,
        second_up: bool,
        duration_ms: int | None = None,
    ) -> None:
        """Drive back and legs with one combined motion frame."""
        directions = {first_axis: first_up, second_axis: second_up}
        if set(directions) != set(self.simultaneous_movement_axes):
            raise ValueError("Jensen beds combine only the back and legs sections")
        await self._move_with_stop(
            JensenCommands.motion(directions["back"], directions["legs"]),
            duration_ms,
        )

    # Presets
    async def preset_flat(self) -> None:
        """Go to flat and follow the move to completion."""
        # A short burst keeps flat reliable on beds that drop the first frame.
        await self._run_monitored(
            JensenCommands.PRESET_FLAT,
            repeat_count=max(2, self._coordinator.motor_pulse_count),
        )

    async def preset_memory(self, memory_num: int) -> None:
        """Recall a device memory slot or an app-stored position."""
        if self.uses_device_memory:
            if memory_num != 1:
                raise ValueError("This Jensen bed has one memory slot")
            await self._run_monitored(JensenCommands.PRESET_MEMORY_RECALL)
            return
        positions = self._memory_slots.get(memory_num)
        if positions is None:
            raise ValueError(f"Jensen memory slot {memory_num} has not been saved yet")
        await self._run_monitored(JensenCommands.goto_position(*positions))

    async def program_memory(self, memory_num: int) -> None:
        """Save the current position to a device slot or an app-stored slot."""
        if self.uses_device_memory:
            if memory_num != 1:
                raise ValueError("This Jensen bed has one memory slot")
            await self.write_command(JensenCommands.PRESET_MEMORY_SAVE)
            return
        if not 1 <= memory_num <= _APP_MEMORY_SLOT_COUNT:
            raise ValueError(f"Jensen memory slots are 1-{_APP_MEMORY_SLOT_COUNT}")
        await self.read_positions()
        assert self._raw_positions is not None  # set by the report read_positions waited for
        self._memory_slots[memory_num] = self._raw_positions
        await self._save_memory_slots()
        _LOGGER.info(
            "Saved Jensen memory slot %d: head_raw=%d foot_raw=%d",
            memory_num,
            *self._raw_positions,
        )

    # Lights
    async def set_light_level(self, level: int) -> None:
        """Set the light level (0 turns it off)."""
        if not self.supports_lights:
            raise NotImplementedError("This Jensen bed does not have lights")
        level = max(0, min(_LEVEL_MAX, level))
        await self.write_command(JensenCommands.light(level) if level else JensenCommands.LIGHT_OFF)
        self._light_level = level
        if level:
            self._last_light_level = level
        self.forward_controller_state_updates(
            {"light_level": level, "under_bed_lights_on": level > 0}
        )

    async def lights_on(self) -> None:
        """Turn the light on at its last level."""
        await self.set_light_level(self._last_light_level)

    async def lights_off(self) -> None:
        """Turn the light off."""
        await self.set_light_level(0)

    async def lights_toggle(self) -> None:
        """Toggle the light."""
        await (self.lights_off() if self._light_level else self.lights_on())

    def get_light_state(self) -> dict[str, Any]:
        """Return the light state this integration last sent."""
        return {"is_on": self._light_level > 0, "light_level": self._light_level}

    # Fan
    async def set_fan_level(self, level: int) -> None:
        """Set the fan level (0 turns it off)."""
        if not self.has_fan:
            raise NotImplementedError("This Jensen bed does not have a fan")
        level = max(0, min(_LEVEL_MAX, level))
        await self.write_command(JensenCommands.fan(level) if level else JensenCommands.FAN_OFF)
        self._fan_level = level
        self.forward_controller_state_updates({"fan_level": level})

    # Massage
    async def _send_massage(self, **levels: int) -> None:
        updated = {**self._massage_levels, **levels}
        await self.write_command(
            JensenCommands.massage(updated["head"], updated["foot"], updated["wave"])
        )
        self._massage_levels = updated
        self.forward_controller_state_updates(self.get_massage_state())

    async def massage_off(self) -> None:
        """Turn off all massage."""
        await self.write_command(JensenCommands.MASSAGE_OFF)
        self._massage_levels = {"head": 0, "foot": 0, "wave": 0}
        self.forward_controller_state_updates(self.get_massage_state())

    async def _toggle_zone(self, zone: str) -> None:
        await self._send_massage(**{zone: 0 if self._massage_levels[zone] else 5})

    async def massage_head_toggle(self) -> None:
        """Toggle head massage."""
        if not self.has_massage_head:
            raise NotImplementedError("This Jensen bed does not have head massage")
        await self._toggle_zone("head")

    async def massage_foot_toggle(self) -> None:
        """Toggle foot massage."""
        if not self.has_massage_foot:
            raise NotImplementedError("This Jensen bed does not have foot massage")
        await self._toggle_zone("foot")

    async def massage_toggle(self) -> None:
        """Toggle all massage."""
        if not self.has_massage:
            raise NotImplementedError("This Jensen bed does not have massage")
        if self._massage_levels["head"] or self._massage_levels["foot"]:
            await self.massage_off()
            return
        await self._send_massage(
            head=5 if self.has_massage_head else 0,
            foot=5 if self.has_massage_foot else 0,
        )

    async def set_massage_intensity(self, zone: str, level: int) -> None:
        """Set one massage zone's level (0-10, 0 = off)."""
        if zone not in self._massage_levels:
            raise ValueError(f"Unknown Jensen massage zone: {zone}")
        await self._send_massage(**{zone: max(0, min(_LEVEL_MAX, level))})

    def get_massage_state(self) -> dict[str, Any]:
        """Return the massage levels this integration last sent."""
        return {
            "head_intensity": self._massage_levels["head"],
            "foot_intensity": self._massage_levels["foot"],
            "wave_intensity": self._massage_levels["wave"],
            "head_active": self._massage_levels["head"] > 0,
            "foot_active": self._massage_levels["foot"] > 0,
        }

    # Direct position control
    def angle_to_native_position(self, motor: str, angle: float) -> int:
        """Jensen targets are percentages, so the value passes through."""
        del motor
        return int(angle)

    async def set_motor_position(self, motor: str, position: int) -> None:
        """Move one section to a percentage, keeping the other where it is."""
        if motor not in ("head", "back", "legs", "feet"):
            raise ValueError(f"Unknown Jensen motor: {motor}")
        if self._raw_positions is None:
            await self.read_positions()
        assert self._raw_positions is not None  # set by the report read_positions waited for
        head_raw, foot_raw = self._raw_positions
        if motor in ("head", "back"):
            head_raw = _percentage_to_raw(position, HEAD_POS_FLAT, HEAD_POS_MAX)
        else:
            foot_raw = _percentage_to_raw(position, FOOT_POS_FLAT, FOOT_POS_MAX)
        await self._run_monitored(JensenCommands.goto_position(head_raw, foot_raw))
