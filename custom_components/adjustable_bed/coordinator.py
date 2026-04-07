"""Coordinator for Adjustable Bed integration."""

from __future__ import annotations

import asyncio
import contextlib
import inspect
import logging
import random
import time
import traceback
from collections import deque
from collections.abc import Callable, Coroutine
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, TypeVar, cast

from bleak import BleakClient
from bleak.backends.device import BLEDevice
from bleak.exc import BleakError
from bleak_retry_connector import establish_connection

try:
    from bleak_retry_connector import close_stale_connections_by_address
except ImportError:
    # Older bleak-retry-connector versions may not expose this helper.
    close_stale_connections_by_address = None
from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo

from .adapter import (
    AdapterSelectionResult,
    detect_esphome_proxy,
    discover_services,
    get_ble_device_with_fallback,
    get_discovered_service_info,
    read_ble_device_info,
    select_adapter,
)
from .const import (
    ADAPTER_AUTO,
    BED_MOTOR_PULSE_DEFAULTS,
    BED_TYPE_COMFORT_MOTION,
    BED_TYPE_DEWERTOKIN,
    BED_TYPE_DIAGNOSTIC,
    BED_TYPE_ERGOMOTION,
    BED_TYPE_JENSEN,
    BED_TYPE_JIECANG,
    BED_TYPE_KEESON,
    BED_TYPE_LEGGETT_GEN2,
    BED_TYPE_LEGGETT_OKIN,
    BED_TYPE_LEGGETT_PLATT,
    BED_TYPE_LEGGETT_WILINKE,
    BED_TYPE_LIMOSS,
    BED_TYPE_LINAK,
    BED_TYPE_MALOUF_LEGACY_OKIN,
    BED_TYPE_MALOUF_NEW_OKIN,
    BED_TYPE_MATTRESSFIRM,
    BED_TYPE_MOTOSLEEP,
    BED_TYPE_NECTAR,
    BED_TYPE_OCTO,
    BED_TYPE_OKIMAT,
    BED_TYPE_OKIN_7BYTE,
    BED_TYPE_OKIN_CB35,
    BED_TYPE_OKIN_FFE,
    BED_TYPE_OKIN_HANDLE,
    BED_TYPE_OKIN_NORDIC,
    BED_TYPE_OKIN_UUID,
    BED_TYPE_REVERIE,
    BED_TYPE_REVERIE_NIGHTSTAND,
    BED_TYPE_RICHMAT,
    BED_TYPE_SERTA,
    BED_TYPE_SLEEPYS_BOX25,
    BED_TYPE_SOLACE,
    BED_TYPE_VIBRADORM,
    CONF_BACK_MAX_ANGLE,
    CONF_BED_TYPE,
    CONF_CB24_BED_SELECTION,
    CONF_CONNECTION_PROFILE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_DISCONNECT_AFTER_COMMAND,
    CONF_HAS_MASSAGE,
    CONF_IDLE_DISCONNECT_SECONDS,
    CONF_JENSEN_PIN,
    CONF_LEGS_MAX_ANGLE,
    CONF_MOTOR_COUNT,
    CONF_MOTOR_PULSE_COUNT,
    CONF_MOTOR_PULSE_DELAY_MS,
    CONF_OCTO_PIN,
    CONF_POSITION_MODE,
    CONF_PREFERRED_ADAPTER,
    CONF_PROTOCOL_VARIANT,
    CONF_RICHMAT_REMOTE,
    CONNECTION_PROFILES,
    DEFAULT_BACK_MAX_ANGLE,
    DEFAULT_CONNECTION_PROFILE,
    DEFAULT_DISABLE_ANGLE_SENSING,
    DEFAULT_DISCONNECT_AFTER_COMMAND,
    DEFAULT_HAS_MASSAGE,
    DEFAULT_IDLE_DISCONNECT_SECONDS,
    DEFAULT_LEGS_MAX_ANGLE,
    DEFAULT_MOTOR_COUNT,
    DEFAULT_MOTOR_PULSE_COUNT,
    DEFAULT_MOTOR_PULSE_DELAY_MS,
    DEFAULT_OCTO_PIN,
    DEFAULT_POSITION_MODE,
    DEFAULT_PROTOCOL_VARIANT,
    DOMAIN,
    OKIMAT_SERVICE_UUID,
    POSITION_CHECK_INTERVAL,
    POSITION_MODE_ACCURACY,
    POSITION_OVERSHOOT_TOLERANCE,
    POSITION_SEEK_TIMEOUT,
    POSITION_STALL_COUNT,
    POSITION_STALL_THRESHOLD,
    POSITION_TOLERANCE,
    RICHMAT_REMOTE_AUTO,
    get_richmat_features,
    get_richmat_motor_count,
    requires_pairing,
    resolve_richmat_remote_code,
)
from .controller_factory import create_controller
from .detection import detect_richmat_remote_from_name
from .diagnostic_payloads import new_connection_attempt_details

if TYPE_CHECKING:
    from .beds.base import BedController

T = TypeVar("T")
_LOGGER = logging.getLogger(__name__)
_READABLE_LIGHT_STATE_TIMEOUT = 2.0

MAX_COMMAND_TRACE_ENTRIES = 100
MAX_CONNECTION_ATTEMPT_DETAILS = 25


class NotConnectedError(Exception):
    """Raised when bed is not connected."""


class NoControllerError(Exception):
    """Raised when no controller is available."""


class AdjustableBedCoordinator:
    """Coordinator for managing bed connection and state."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the coordinator."""
        self.hass = hass
        self.entry = entry
        self._address: str = entry.data[CONF_ADDRESS].upper()
        self._bed_type: str = entry.data[CONF_BED_TYPE]
        self._protocol_variant: str = entry.data.get(
            CONF_PROTOCOL_VARIANT, DEFAULT_PROTOCOL_VARIANT
        )
        self._name: str = entry.data.get(CONF_NAME, "Adjustable Bed")
        self._richmat_remote: str = entry.data.get(CONF_RICHMAT_REMOTE, RICHMAT_REMOTE_AUTO)
        if self._bed_type == BED_TYPE_RICHMAT:
            self._richmat_remote = resolve_richmat_remote_code(
                self._richmat_remote,
                entry_title=entry.title,
                configured_name=self._name,
            )
            self._motor_count = get_richmat_motor_count(get_richmat_features(self._richmat_remote))
        else:
            self._motor_count = entry.data.get(CONF_MOTOR_COUNT, DEFAULT_MOTOR_COUNT)
        self._has_massage: bool = entry.data.get(CONF_HAS_MASSAGE, DEFAULT_HAS_MASSAGE)
        self._disable_angle_sensing: bool = entry.data.get(
            CONF_DISABLE_ANGLE_SENSING, DEFAULT_DISABLE_ANGLE_SENSING
        )
        self._position_mode: str = entry.data.get(CONF_POSITION_MODE, DEFAULT_POSITION_MODE)
        self._preferred_adapter: str = entry.data.get(CONF_PREFERRED_ADAPTER, ADAPTER_AUTO)

        # Connection profile settings
        self._connection_profile: str = entry.data.get(
            CONF_CONNECTION_PROFILE, DEFAULT_CONNECTION_PROFILE
        )
        profile_settings = CONNECTION_PROFILES.get(self._connection_profile)
        if profile_settings is None:
            _LOGGER.warning(
                "Unknown connection profile '%s'; defaulting to '%s'",
                self._connection_profile,
                DEFAULT_CONNECTION_PROFILE,
            )
            self._connection_profile = DEFAULT_CONNECTION_PROFILE
            profile_settings = CONNECTION_PROFILES[DEFAULT_CONNECTION_PROFILE]
        self._max_retries: int = profile_settings.max_retries
        self._retry_base_delay: float = profile_settings.retry_base_delay
        self._retry_jitter: float = profile_settings.retry_jitter
        self._connection_timeout: float = profile_settings.connection_timeout
        self._post_connect_delay: float = profile_settings.post_connect_delay

        # Get bed-type-specific motor pulse defaults, falling back to global defaults
        bed_pulse_defaults = BED_MOTOR_PULSE_DEFAULTS.get(
            self._bed_type, (DEFAULT_MOTOR_PULSE_COUNT, DEFAULT_MOTOR_PULSE_DELAY_MS)
        )
        self._motor_pulse_count: int = entry.data.get(CONF_MOTOR_PULSE_COUNT, bed_pulse_defaults[0])
        self._motor_pulse_delay_ms: int = entry.data.get(
            CONF_MOTOR_PULSE_DELAY_MS, bed_pulse_defaults[1]
        )

        # Disconnect behavior configuration
        self._disconnect_after_command: bool = entry.data.get(
            CONF_DISCONNECT_AFTER_COMMAND, DEFAULT_DISCONNECT_AFTER_COMMAND
        )
        self._idle_disconnect_seconds: int = entry.data.get(
            CONF_IDLE_DISCONNECT_SECONDS, DEFAULT_IDLE_DISCONNECT_SECONDS
        )

        # Octo-specific configuration
        self._octo_pin: str = entry.data.get(CONF_OCTO_PIN, DEFAULT_OCTO_PIN)

        # Jensen-specific configuration
        self._jensen_pin: str = entry.data.get(CONF_JENSEN_PIN, "")

        # CB24-specific configuration (SmartBed by Okin split beds)
        self._cb24_bed_selection: int = entry.data.get(CONF_CB24_BED_SELECTION, 0x00)
        self._cb24_continuous_presets_learned = False

        self._client: BleakClient | None = None
        self._controller: BedController | None = None
        self._disconnect_timer: asyncio.TimerHandle | None = None
        self._reconnect_timer: asyncio.TimerHandle | None = None
        self._lock = asyncio.Lock()
        self._command_lock = asyncio.Lock()  # Separate lock for command serialization
        self._connecting: bool = False  # Track if we're actively connecting
        self._intentional_disconnect: bool = (
            False  # Track intentional disconnects to skip auto-reconnect
        )
        self._cancel_command = asyncio.Event()  # Signal to cancel current command
        self._cancel_counter: int = 0  # Track cancellation requests to handle queued commands
        self._stop_keepalive_task: asyncio.Task[None] | None = None  # Track keepalive stop task

        # Position data from notifications
        self._position_data: dict[str, float] = {}
        self._position_callbacks: set[Callable[[dict[str, float]], None]] = set()
        self._controller_state: dict[str, Any] = {}
        self._controller_state_callbacks: set[Callable[[dict[str, Any]], None]] = set()
        self._controller_state_refresh_task: asyncio.Task[None] | None = None

        # Connection state callbacks
        self._connection_state_callbacks: set[Callable[[bool], None]] = set()

        # Connection metadata for binary sensor attributes
        self._last_connected: datetime | None = None
        self._last_disconnected: datetime | None = None
        self._connection_source: str | None = None
        self._connection_rssi: int | None = None

        # BLE Device Information Service data
        self._ble_manufacturer: str | None = None
        self._ble_model: str | None = None

        # Track if pairing is supported by the Bluetooth adapter (None = unknown)
        self._pairing_supported: bool | None = None

        # Connection history tracking for diagnostics (issue #168)
        self._connection_attempt_count: int = 0
        self._connection_success_count: int = 0
        self._last_connection_attempt: datetime | None = None
        self._last_connection_error: str | None = None
        self._last_connection_error_type: str | None = None
        self._last_disconnect_reason: str | None = (
            None  # "idle_timeout", "intentional", "unexpected"
        )

        # Command timing tracking for diagnostics (issue #168)
        self._last_command_start: datetime | None = None
        self._last_command_end: datetime | None = None
        self._last_notify_received: datetime | None = None

        # Adapter selection details for diagnostics (issue #168)
        self._actual_adapter: str | None = None
        self._available_adapters: list[str] = []
        self._command_trace: deque[dict[str, Any]] = deque(maxlen=MAX_COMMAND_TRACE_ENTRIES)
        self._connection_attempt_details: deque[dict[str, Any]] = deque(
            maxlen=MAX_CONNECTION_ATTEMPT_DETAILS
        )

        _LOGGER.debug(
            "Coordinator initialized for %s at %s (type: %s, motors: %d, massage: %s, disable_angle_sensing: %s, adapter: %s, connection_profile: %s)",
            self._name,
            self._address,
            self._bed_type,
            self._motor_count,
            self._has_massage,
            self._disable_angle_sensing,
            self._preferred_adapter,
            self._connection_profile,
        )

    @property
    def address(self) -> str:
        """Return the Bluetooth address."""
        return self._address

    @property
    def name(self) -> str:
        """Return the bed name."""
        return self._name

    @property
    def bed_type(self) -> str:
        """Return the bed type."""
        return self._bed_type

    @property
    def motor_count(self) -> int:
        """Return the motor count."""
        return self._motor_count

    @property
    def has_massage(self) -> bool:
        """Return whether the bed has massage."""
        return self._has_massage

    @property
    def disable_angle_sensing(self) -> bool:
        """Return whether angle sensing is disabled."""
        return self._disable_angle_sensing

    @property
    def back_max_angle(self) -> float:
        """Return the maximum angle for back motor (also used for head)."""
        # Check options first (runtime config), then entry data (initial config)
        if CONF_BACK_MAX_ANGLE in self.entry.options:
            return float(self.entry.options[CONF_BACK_MAX_ANGLE])
        if CONF_BACK_MAX_ANGLE in self.entry.data:
            return float(self.entry.data[CONF_BACK_MAX_ANGLE])
        return DEFAULT_BACK_MAX_ANGLE

    @property
    def legs_max_angle(self) -> float:
        """Return the maximum angle for legs motor (also used for feet)."""
        # Check options first (runtime config), then entry data (initial config)
        if CONF_LEGS_MAX_ANGLE in self.entry.options:
            return float(self.entry.options[CONF_LEGS_MAX_ANGLE])
        if CONF_LEGS_MAX_ANGLE in self.entry.data:
            return float(self.entry.data[CONF_LEGS_MAX_ANGLE])
        return DEFAULT_LEGS_MAX_ANGLE

    @property
    def head_max_angle(self) -> float:
        """Return the maximum angle for head motor (derived from back)."""
        return self.back_max_angle

    @property
    def feet_max_angle(self) -> float:
        """Return the maximum angle for feet motor (derived from legs)."""
        return self.legs_max_angle

    def get_max_angle(self, position_key: str) -> float:
        """Get the max angle for a motor position key.

        Args:
            position_key: Motor name ("back", "legs", "head", or "feet")

        Returns:
            Maximum angle in degrees for the specified motor.
        """
        if position_key in ("back", "head"):
            return self.back_max_angle
        if position_key in ("legs", "feet"):
            return self.legs_max_angle
        # Unknown motor, return back max as default
        return self.back_max_angle

    @property
    def motor_pulse_count(self) -> int:
        """Return the motor pulse count."""
        return self._motor_pulse_count

    @property
    def motor_pulse_delay_ms(self) -> int:
        """Return the motor pulse delay in milliseconds."""
        return self._motor_pulse_delay_ms

    @property
    def cb24_continuous_presets_learned(self) -> bool:
        """Return whether CB24 auto mode has learned continuous preset sends."""
        return self._cb24_continuous_presets_learned

    @property
    def controller(self) -> BedController | None:
        """Return the bed controller."""
        return self._controller

    @property
    def position_data(self) -> dict[str, float]:
        """Return current position data."""
        return self._position_data

    @property
    def controller_state(self) -> dict[str, Any]:
        """Return non-position controller state."""
        return self._controller_state

    @property
    def is_connected(self) -> bool:
        """Return whether we are currently connected to the bed."""
        return self._client is not None and self._client.is_connected

    @property
    def is_connecting(self) -> bool:
        """Return whether we are currently connecting to the bed."""
        return self._connecting

    @property
    def last_connected(self) -> datetime | None:
        """Return the last connection timestamp."""
        return self._last_connected

    @property
    def last_disconnected(self) -> datetime | None:
        """Return the last disconnection timestamp."""
        return self._last_disconnected

    @property
    def connection_source(self) -> str | None:
        """Return the adapter/source used for the current connection."""
        return self._connection_source

    @property
    def connection_rssi(self) -> int | None:
        """Return the RSSI at connection time."""
        return self._connection_rssi

    @property
    def client(self) -> BleakClient | None:
        """Return the BLE client (for diagnostics)."""
        return self._client

    @property
    def pairing_supported(self) -> bool | None:
        """Return whether the Bluetooth adapter supports pairing.

        None = not yet determined, True = supported, False = not supported.
        """
        return self._pairing_supported

    @property
    def cancel_command(self) -> asyncio.Event:
        """Return the cancel command event."""
        return self._cancel_command

    @property
    def connection_history(self) -> dict[str, Any]:
        """Return connection history for diagnostics."""
        return {
            "attempt_count": self._connection_attempt_count,
            "success_count": self._connection_success_count,
            "last_attempt": self._last_connection_attempt.isoformat()
            if self._last_connection_attempt
            else None,
            "last_error": self._last_connection_error,
            "last_error_type": self._last_connection_error_type,
            "last_disconnect_reason": self._last_disconnect_reason,
        }

    @property
    def adapter_details(self) -> dict[str, Any]:
        """Return adapter selection details for diagnostics."""
        return {
            "preferred": self._preferred_adapter,
            "actual": self._actual_adapter,
            "available": self._available_adapters,
        }

    @property
    def command_timing(self) -> dict[str, Any]:
        """Return command timing for diagnostics."""
        return {
            "last_command_start": self._last_command_start.isoformat()
            if self._last_command_start
            else None,
            "last_command_end": self._last_command_end.isoformat()
            if self._last_command_end
            else None,
            "last_notify_received": self._last_notify_received.isoformat()
            if self._last_notify_received
            else None,
        }

    @property
    def command_trace(self) -> list[dict[str, Any]]:
        """Return recent integration-issued BLE writes."""
        return list(self._command_trace)

    @property
    def connection_attempt_details(self) -> list[dict[str, Any]]:
        """Return detailed recent connection attempts."""
        return list(self._connection_attempt_details)

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info for this bed."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._address)},
            name=self._name,
            manufacturer=self._get_manufacturer(),
            model=self._get_model(),
        )

    def _get_manufacturer(self) -> str:
        """Get manufacturer name based on bed type."""
        # Use BLE value if available and useful
        if self._is_useful_ble_value(self._ble_manufacturer):
            return self._ble_manufacturer  # type: ignore[return-value]

        # Fall back to hardcoded values based on bed type
        manufacturers = {
            BED_TYPE_LINAK: "Linak",
            BED_TYPE_RICHMAT: "Richmat",
            BED_TYPE_KEESON: "Keeson",
            BED_TYPE_SOLACE: "Solace",
            BED_TYPE_MOTOSLEEP: "MotoSleep",
            BED_TYPE_LEGGETT_PLATT: "Leggett & Platt",
            BED_TYPE_LEGGETT_GEN2: "Leggett & Platt",
            BED_TYPE_LEGGETT_OKIN: "Leggett & Platt",
            BED_TYPE_LEGGETT_WILINKE: "Leggett & Platt",
            BED_TYPE_LIMOSS: "Limoss",
            BED_TYPE_REVERIE: "Reverie",
            BED_TYPE_REVERIE_NIGHTSTAND: "Reverie",
            BED_TYPE_OKIMAT: "Okimat",
            BED_TYPE_ERGOMOTION: "Ergomotion",
            BED_TYPE_JIECANG: "Jiecang",
            BED_TYPE_DEWERTOKIN: "DewertOkin",
            BED_TYPE_OKIN_HANDLE: "Okin",
            BED_TYPE_OKIN_UUID: "Okin",
            BED_TYPE_OKIN_7BYTE: "Okin",
            BED_TYPE_OKIN_NORDIC: "Okin",
            BED_TYPE_OKIN_FFE: "Okin",
            BED_TYPE_OCTO: "Octo",
            BED_TYPE_MATTRESSFIRM: "MattressFirm",
            BED_TYPE_NECTAR: "Nectar",
            BED_TYPE_MALOUF_NEW_OKIN: "Malouf",
            BED_TYPE_MALOUF_LEGACY_OKIN: "Malouf",
            BED_TYPE_COMFORT_MOTION: "Comfort Motion",
            BED_TYPE_SERTA: "Serta",
            BED_TYPE_DIAGNOSTIC: "Unknown",
        }
        return manufacturers.get(self._bed_type, "Unknown")

    def _get_model(self) -> str:
        """Get model name based on bed type."""
        if self._is_useful_ble_value(self._ble_model):
            return self._ble_model  # type: ignore[return-value]
        return f"Adjustable Bed ({self._motor_count} motors)"

    def _is_useful_ble_value(self, value: str | None) -> bool:
        """Check if a BLE value is useful (not generic/unhelpful).

        Some devices return generic strings like "BLE Device" or the chipset
        manufacturer instead of the actual bed manufacturer. This filters those out.
        """
        if not value or not value.strip():
            return False

        normalized = value.strip().lower()

        # Generic/placeholder strings
        generic_values = {
            "unknown",
            "n/a",
            "na",
            "none",
            "null",
            "undefined",
            "ble device",
            "bluetooth device",
            "generic",
        }
        if normalized in generic_values:
            return False

        # Chipset manufacturers (not the actual bed manufacturer)
        chipset_manufacturers = {
            "nordic semiconductor",
            "nordic",
            "texas instruments",
            "ti",
            "realtek",
            "qualcomm",
            "broadcom",
            "espressif",
            "silicon labs",
            "dialog semiconductor",
            "cypress",
            "microchip",
            "stmicroelectronics",
        }
        return normalized not in chipset_manufacturers

    def remember_cb24_continuous_presets(self) -> None:
        """Persist the learned CB24 continuous preset mode across reconnects."""
        if self._cb24_continuous_presets_learned:
            return

        self._cb24_continuous_presets_learned = True
        _LOGGER.info(
            "Learned CB24 continuous preset mode for %s; reusing it on reconnects",
            self._address,
        )

    def record_command_trace(
        self,
        *,
        payload: dict[str, Any],
        characteristic_uuid: str,
        characteristic_handle: int | None,
        response: bool,
        repeat_count: int,
        repeat_delay_ms: int,
        command_origin: str | None,
        controller_class: str,
    ) -> None:
        """Record an integration-issued write for support bundles."""
        self._command_trace.append(
            {
                "timestamp": datetime.now(UTC).isoformat(),
                "controller_class": controller_class,
                "characteristic_uuid": characteristic_uuid,
                "characteristic_handle": characteristic_handle,
                "payload": payload,
                "write_mode": "with_response" if response else "without_response",
                "repeat_count": repeat_count,
                "repeat_delay_ms": repeat_delay_ms,
                "command_origin": command_origin,
            }
        )

    async def async_connect(self) -> bool:
        """Connect to the bed."""
        _LOGGER.debug("async_connect called for %s", self._address)
        async with self._lock:
            return await self._async_connect_locked()

    async def _async_connect_locked(self, reset_timer: bool = True) -> bool:
        """Connect to the bed (must hold lock)."""
        # Clear intentional disconnect flag when explicitly connecting
        # This ensures the flag persists through late disconnect callbacks
        self._intentional_disconnect = False

        if self._client is not None and self._client.is_connected:
            _LOGGER.debug("Already connected to %s, reusing connection", self._address)
            if reset_timer:
                self._reset_disconnect_timer()
            return True

        _LOGGER.info(
            "Initiating BLE connection to %s (max %d attempts)",
            self._address,
            self._max_retries,
        )
        overall_start = time.monotonic()
        # Track adapters that ran out of connection slots so we can try
        # alternatives on subsequent retries (issue #152).
        exhausted_adapters: set[str] = set()
        adapter_result: AdapterSelectionResult | None = None

        for attempt in range(self._max_retries):
            attempt_start = time.monotonic()
            attempt_details = new_connection_attempt_details(attempt + 1, self._preferred_adapter)
            # Track connection attempt for diagnostics (issue #168)
            self._connection_attempt_count += 1
            self._last_connection_attempt = datetime.now(UTC)

            # On retries, add a delay before attempting to give the Bluetooth stack time to reset
            if attempt > 0:
                base_delay = self._retry_base_delay * (2 ** (attempt - 1))
                jitter = random.uniform(1 - self._retry_jitter, 1 + self._retry_jitter)
                pre_retry_delay = base_delay * jitter
                _LOGGER.info(
                    "Waiting %.1fs before connection retry %d/%d to %s...",
                    pre_retry_delay,
                    attempt + 1,
                    self._max_retries,
                    self._address,
                )
                await asyncio.sleep(pre_retry_delay)

            try:
                _LOGGER.debug(
                    "Connection attempt %d/%d: Looking up device %s via HA Bluetooth (preferred adapter: %s)",
                    attempt + 1,
                    self._max_retries,
                    self._address,
                    self._preferred_adapter,
                )

                # Log available Bluetooth adapters/scanners
                try:
                    scanner_count = bluetooth.async_scanner_count(self.hass, connectable=True)
                    _LOGGER.debug(
                        "Available Bluetooth scanners (connectable): %d",
                        scanner_count,
                    )
                    # Capture available adapters for diagnostics (issue #168)
                    try:
                        scanners = bluetooth.async_current_scanners(self.hass)
                        self._available_adapters = [
                            getattr(scanner, "source", "unknown") for scanner in scanners
                        ]
                    except Exception as exc:
                        _LOGGER.debug(
                            "Failed to capture adapters via bluetooth.async_current_scanners: %s",
                            exc,
                        )
                except Exception as err:
                    _LOGGER.debug("Could not get scanner count: %s", err)

                # Select best adapter and get device, excluding any adapters
                # that previously ran out of connection slots
                adapter_result = await select_adapter(
                    self.hass,
                    self._address,
                    self._preferred_adapter,
                    exclude_adapters=exhausted_adapters or None,
                )
                attempt_details["selected_source"] = adapter_result.source
                attempt_details["selected_rssi"] = adapter_result.rssi
                attempt_details["selected_connectable"] = adapter_result.connectable
                attempt_details["non_connectable_fallback_used"] = (
                    adapter_result.connectable is False
                )
                attempt_details["visible_sources"] = list(adapter_result.available_sources)
                device = adapter_result.device

                if device is None:
                    lookup_elapsed = time.monotonic() - attempt_start
                    attempt_details["lookup_elapsed_seconds"] = round(lookup_elapsed, 3)
                    attempt_details["total_elapsed_seconds"] = round(lookup_elapsed, 3)
                    attempt_details["result"] = "device_not_found"
                    _LOGGER.warning(
                        "Device %s NOT FOUND in Bluetooth scanner after %.1fs (attempt %d/%d). "
                        "Bed may be powered off, out of range, or connected to another device.",
                        self._address,
                        lookup_elapsed,
                        attempt + 1,
                        self._max_retries,
                    )
                    # Log what devices ARE visible
                    try:
                        discovered = get_discovered_service_info(
                            self.hass,
                            include_non_connectable=True,
                        )
                        if discovered:
                            _LOGGER.debug(
                                "Currently visible BLE devices (%d total):",
                                len(discovered),
                            )
                            for svc_info in discovered[:10]:  # Limit to first 10
                                _LOGGER.debug(
                                    "  - %s (name: %s, rssi: %s, source: %s, connectable: %s)",
                                    svc_info.address,
                                    svc_info.name or "Unknown",
                                    getattr(svc_info, "rssi", "N/A"),
                                    getattr(svc_info, "source", "N/A"),
                                    getattr(svc_info, "connectable", None),
                                )
                            if len(discovered) > 10:
                                _LOGGER.debug("  ... and %d more devices", len(discovered) - 10)
                        else:
                            _LOGGER.debug("No BLE devices currently visible")
                    except Exception as err:
                        _LOGGER.debug("Could not enumerate visible devices: %s", err)
                    self._connection_attempt_details.append(attempt_details)
                    # Don't sleep here - the retry backoff at loop start handles delays
                    continue

                # Log detailed device info including which adapter discovered it
                device_source = None
                if hasattr(device, "details") and isinstance(device.details, dict):
                    device_source = device.details.get("source")

                lookup_elapsed = time.monotonic() - attempt_start
                attempt_details["lookup_elapsed_seconds"] = round(lookup_elapsed, 3)
                _LOGGER.info(
                    "✓ Device %s FOUND in %.1fs (name: %s) via adapter: %s",
                    self._address,
                    lookup_elapsed,
                    device.name or "Unknown",
                    device_source or "unknown",
                )
                if adapter_result.connectable is False:
                    _LOGGER.warning(
                        "Device %s was recovered from a non-connectable scanner record. "
                        "This usually means the Bluetooth proxy or scanner classified the "
                        "advertisement incorrectly.",
                        self._address,
                    )
                _LOGGER.debug(
                    "Device details: address=%s, name=%s, details=%s",
                    device.address,
                    device.name,
                    getattr(device, "details", "N/A"),
                )

                if self._preferred_adapter and self._preferred_adapter != ADAPTER_AUTO:
                    if device_source == self._preferred_adapter:
                        _LOGGER.info(
                            "✓ Device discovered by preferred adapter: %s",
                            self._preferred_adapter,
                        )
                    else:
                        _LOGGER.warning(
                            "⚠ Device discovered by %s, but preferred adapter is %s - connection may use different adapter",
                            device_source,
                            self._preferred_adapter,
                        )

                # Detect ESPHome proxy (logs info if detected)
                detect_esphome_proxy(self.hass, self._address)

                # Use bleak-retry-connector for reliable connection establishment
                # This handles ESPHome Bluetooth proxy connections properly
                # Using standard BleakClient (not cached) for better compatibility
                # with devices that have connection stability issues
                connect_start = time.monotonic()
                _LOGGER.info(
                    "Attempting BLE GATT connection to %s (timeout: %.0fs)...",
                    self._address,
                    self._connection_timeout,
                )

                # Best-effort BlueZ cleanup. Some failed attempts leave stale pending
                # connections behind, which can cause repeated connect timeouts.
                if close_stale_connections_by_address is not None:
                    try:
                        close_result = close_stale_connections_by_address(self._address)
                        if inspect.isawaitable(close_result):
                            await close_result
                    except (OSError, BleakError) as err:
                        _LOGGER.debug(
                            "Could not close stale connections for %s: %s",
                            self._address,
                            err,
                        )
                    except Exception:
                        _LOGGER.warning(
                            "Unexpected error closing stale connections for %s",
                            self._address,
                            exc_info=True,
                        )

                # Always provide a callback so bleak-retry-connector can refresh the
                # BLEDevice between retries. In auto mode this prevents using a stale
                # device object from an older scan snapshot.
                target_source: str | None = None
                if self._preferred_adapter and self._preferred_adapter != ADAPTER_AUTO:
                    target_source = self._preferred_adapter
                elif adapter_result.source and adapter_result.source != "unknown":
                    target_source = adapter_result.source

                def _get_fresh_device_for_connection(
                    selected_source: str | None = target_source,
                ) -> BLEDevice:
                    """Return a fresh BLEDevice from the current scanner data."""
                    discovered = get_discovered_service_info(
                        self.hass,
                        include_non_connectable=True,
                    )
                    for svc_info in discovered:
                        if svc_info.address.upper() != self._address:
                            continue
                        svc_source = getattr(svc_info, "source", None)
                        if selected_source is None or svc_source == selected_source:
                            _LOGGER.debug(
                                "ble_device_callback returning device from %s (RSSI: %s, connectable=%s)",
                                svc_source or "unknown",
                                getattr(svc_info, "rssi", "N/A"),
                                getattr(svc_info, "connectable", None),
                            )
                            return svc_info.device

                    if selected_source is not None:
                        _LOGGER.debug(
                            "Target adapter %s not currently seeing %s, falling back to default lookup",
                            selected_source,
                            self._address,
                        )

                    fallback, connectable = get_ble_device_with_fallback(
                        self.hass,
                        self._address,
                        allow_non_connectable=True,
                    )
                    if fallback is None:
                        raise BleakError(f"Device {self._address} not found")
                    if connectable is False:
                        _LOGGER.debug(
                            "ble_device_callback falling back to non-connectable record for %s",
                            self._address,
                        )
                    return fallback

                ble_device_callback: Callable[[], BLEDevice] | None = (
                    _get_fresh_device_for_connection
                )

                # Determine if this bed type needs pairing and if pairing is supported
                bed_requires_pairing = requires_pairing(self._bed_type, self._protocol_variant)
                # Only attempt pairing if bed requires it AND we haven't already
                # determined that pairing is unsupported by this adapter
                use_pairing = bed_requires_pairing and self._pairing_supported is not False
                if use_pairing:
                    _LOGGER.info(
                        "Pairing enabled for %s (bed type: %s, variant: %s) - "
                        "GATT services cache disabled to force fresh discovery",
                        self._name,
                        self._bed_type,
                        self._protocol_variant,
                    )

                # Mark that we're connecting to suppress spurious disconnect warnings
                # during bleak's internal retry process
                self._connecting = True
                # Notify callbacks so binary sensor can show "connecting" state
                self._notify_connection_state_change(False)
                try:
                    # Use max_attempts=1 here since outer loop handles retries
                    # When pairing is required, disable services cache to force fresh
                    # GATT discovery. Some devices expose different services depending
                    # on pairing state, and stale cached services from a previous
                    # non-paired connection will cause characteristic lookups to fail.
                    disable_cache = use_pairing
                    try:
                        self._client = await establish_connection(
                            BleakClient,
                            device,
                            self._name,
                            disconnected_callback=self._on_disconnect,
                            max_attempts=1,
                            timeout=self._connection_timeout,
                            ble_device_callback=ble_device_callback,
                            pair=use_pairing,
                            use_services_cache=not disable_cache,
                        )
                        # If we get here with pairing enabled, mark it as supported
                        if use_pairing:
                            self._pairing_supported = True
                    except (NotImplementedError, TypeError) as pair_err:
                        # NotImplementedError: ESPHome < 2024.3.0 doesn't support pairing
                        # TypeError: older bleak-retry-connector doesn't have pair kwarg
                        if use_pairing:
                            _LOGGER.warning(
                                "Pairing not supported by Bluetooth adapter: %s. "
                                "If using ESPHome proxy, update to ESPHome >= 2024.3.0. "
                                "Retrying connection without pairing...",
                                pair_err,
                            )
                            # Remember that pairing isn't supported to avoid repeated warnings
                            self._pairing_supported = False
                            # Retry without pairing but still disable cache since
                            # this bed type requires pairing and may have stale data
                            self._client = await establish_connection(
                                BleakClient,
                                device,
                                self._name,
                                disconnected_callback=self._on_disconnect,
                                max_attempts=1,
                                timeout=self._connection_timeout,
                                ble_device_callback=ble_device_callback,
                                use_services_cache=False,
                            )
                        else:
                            raise
                finally:
                    self._connecting = False
                    # Don't notify here - the connect success/failure paths will notify

                # Determine which adapter was actually used for connection
                actual_adapter = "unknown"
                try:
                    # Try to get the actual connection source from the client
                    # (accessing private bleak internals for diagnostic purposes)
                    if hasattr(self._client, "_backend") and hasattr(
                        self._client._backend, "_device"
                    ):
                        backend_device = self._client._backend._device
                        if hasattr(backend_device, "details") and isinstance(
                            backend_device.details, dict
                        ):
                            actual_adapter = backend_device.details.get("source", "unknown")
                except Exception:
                    _LOGGER.debug("Could not determine actual connection adapter")

                # Track successful connection for diagnostics (issue #168)
                self._connection_success_count += 1
                self._actual_adapter = actual_adapter
                self._last_connection_error = None
                self._last_connection_error_type = None
                attempt_details["actual_source"] = actual_adapter

                connect_elapsed = time.monotonic() - connect_start
                total_elapsed = time.monotonic() - attempt_start
                attempt_details["connect_elapsed_seconds"] = round(connect_elapsed, 3)
                attempt_details["total_elapsed_seconds"] = round(total_elapsed, 3)
                attempt_details["result"] = "connected"
                _LOGGER.info(
                    "✓ CONNECTED to %s in %.1fs (GATT: %.1fs) via adapter: %s",
                    self._address,
                    total_elapsed,
                    connect_elapsed,
                    actual_adapter,
                )

                if self._preferred_adapter and self._preferred_adapter != ADAPTER_AUTO:
                    if actual_adapter == self._preferred_adapter:
                        _LOGGER.info(
                            "✓ Connection using preferred adapter: %s",
                            self._preferred_adapter,
                        )
                    elif actual_adapter != "unknown":
                        _LOGGER.warning(
                            "⚠ Connected via %s instead of preferred adapter %s",
                            actual_adapter,
                            self._preferred_adapter,
                        )

                # Small delay to let connection stabilize before operations
                await asyncio.sleep(self._post_connect_delay)

                # Log connection details
                _LOGGER.debug(
                    "BleakClient connected: is_connected=%s, mtu_size=%s",
                    self._client.is_connected,
                    getattr(self._client, "mtu_size", "N/A"),
                )

                # Discover services and log hierarchy
                attempt_details["service_discovery"]["attempted"] = True
                service_discovery_success = await discover_services(self._client, self._address)
                attempt_details["service_discovery"]["success"] = service_discovery_success
                attempt_details["service_discovery"]["service_count"] = (
                    len(list(self._client.services)) if self._client.services else 0
                )

                # Validate expected services are present (for beds requiring pairing)
                if bed_requires_pairing and self._client.services:
                    discovered_uuids = {svc.uuid.lower() for svc in self._client.services}
                    _LOGGER.debug(
                        "Discovered service UUIDs for %s: %s",
                        self._name,
                        sorted(discovered_uuids),
                    )

                    # Get expected service UUID for this bed type
                    expected_service = OKIMAT_SERVICE_UUID.lower()
                    if (
                        self._bed_type
                        in (BED_TYPE_OKIMAT, BED_TYPE_OKIN_UUID, BED_TYPE_LEGGETT_OKIN)
                        and expected_service not in discovered_uuids
                    ):
                        _LOGGER.warning(
                            "⚠ Expected OKIN service UUID %s not found in discovered "
                            "services for %s. This usually means pairing/bonding failed. "
                            "Discovered services: %s. Try removing and re-adding the "
                            "device with 'Pair Now' option.",
                            expected_service,
                            self._name,
                            sorted(discovered_uuids),
                        )

                # Read BLE Device Information Service for manufacturer/model
                ble_manufacturer, ble_model = await read_ble_device_info(
                    self._client, self._address
                )
                self._ble_manufacturer = ble_manufacturer
                self._ble_model = ble_model

                # Post-connection protocol verification for DewertOkin Star devices.
                # The adjustbed app (com.okin.bedding.adjustbed) reads BLE characteristic
                # 2A29 (Manufacturer Name) after connecting: exactly "STAR" = CB35 protocol
                # (35_22_01), anything else = BOX25 protocol (25_42_02).
                if self._bed_type in (BED_TYPE_OKIN_CB35, BED_TYPE_SLEEPYS_BOX25):
                    is_star_manufacturer = (
                        ble_manufacturer is not None and ble_manufacturer.strip().upper() == "STAR"
                    )
                    if is_star_manufacturer and self._bed_type == BED_TYPE_SLEEPYS_BOX25:
                        _LOGGER.warning(
                            "BLE Manufacturer Name is 'STAR' for %s - this indicates a "
                            "CB35 protocol device, but configured as BOX25. Auto-correcting "
                            "to CB35. Source: com.okin.bedding.adjustbed 2A29 detection",
                            self._address,
                        )
                        self._bed_type = BED_TYPE_OKIN_CB35
                    elif not is_star_manufacturer and self._bed_type == BED_TYPE_OKIN_CB35:
                        if ble_manufacturer is not None:
                            _LOGGER.warning(
                                "BLE Manufacturer Name is '%s' (not 'STAR') for %s - this "
                                "indicates a BOX25 protocol device, but configured as CB35. "
                                "Auto-correcting to BOX25. Source: com.okin.bedding.adjustbed "
                                "2A29 detection",
                                ble_manufacturer,
                                self._address,
                            )
                            self._bed_type = BED_TYPE_SLEEPYS_BOX25

                # If remote is set to auto, infer Richmat remote code from BLE name at runtime.
                # This preserves compatibility for existing entries created before auto-code storage.
                richmat_remote = self._richmat_remote
                if self._bed_type == BED_TYPE_RICHMAT and richmat_remote == RICHMAT_REMOTE_AUTO:
                    detected_remote = detect_richmat_remote_from_name(device.name)
                    if detected_remote:
                        richmat_remote = detected_remote
                        _LOGGER.info(
                            "Auto-detected Richmat remote code '%s' from BLE name '%s'",
                            detected_remote,
                            device.name,
                        )
                if self._bed_type == BED_TYPE_RICHMAT:
                    richmat_remote = resolve_richmat_remote_code(
                        richmat_remote,
                        entry_title=self.entry.title,
                        configured_name=self._name,
                        device_name=device.name,
                    )

                manufacturer_data: dict[int, bytes] | None = None
                advertisement = bluetooth.async_last_service_info(
                    self.hass,
                    self._address,
                    connectable=True,
                )
                if advertisement and advertisement.manufacturer_data:
                    manufacturer_data = dict(advertisement.manufacturer_data)
                    _LOGGER.debug(
                        "Using manufacturer data keys for controller creation: %s",
                        sorted(manufacturer_data),
                    )

                # Create the controller
                _LOGGER.debug("Creating %s controller...", self._bed_type)
                self._controller = await create_controller(
                    coordinator=self,
                    bed_type=self._bed_type,
                    protocol_variant=self._protocol_variant,
                    client=self._client,
                    device_name=device.name,
                    octo_pin=self._octo_pin,
                    richmat_remote=richmat_remote,
                    jensen_pin=self._jensen_pin,
                    cb24_bed_selection=self._cb24_bed_selection,
                    ble_manufacturer=ble_manufacturer,
                    manufacturer_data=manufacturer_data,
                )
                _LOGGER.debug("Controller created successfully")

                if (
                    self._bed_type == BED_TYPE_VIBRADORM
                    and not self._disable_angle_sensing
                    and not self._controller.supports_position_feedback
                ):
                    self._disable_angle_sensing = True
                    _LOGGER.info(
                        "Disabling angle sensing for %s: BLE model %s uses the OEM app's "
                        "write-only VMAT control path without position feedback",
                        self._address,
                        self._ble_model or self._get_model(),
                    )

                if self._bed_type == BED_TYPE_LIMOSS and hasattr(
                    self._controller, "reset_max_raw_estimate"
                ):
                    # Reset Limoss normalization state on each connection.
                    cast(Any, self._controller).reset_max_raw_estimate()

                if reset_timer:
                    self._reset_disconnect_timer()

                # Start position notifications (no-op if angle sensing disabled)
                await self.async_start_notify()

                # For Octo beds: discover features and handle PIN if needed
                if self._bed_type == BED_TYPE_OCTO:
                    # Discover features to detect PIN requirement
                    if hasattr(self._controller, "discover_features"):
                        await self._controller.discover_features()
                    # Send initial PIN and start keep-alive if bed requires it
                    if hasattr(self._controller, "send_pin"):
                        await self._controller.send_pin()
                        await self._controller.start_keepalive()  # type: ignore[attr-defined]

                # For Jensen beds: query dynamic features (lights, massage)
                if self._bed_type == BED_TYPE_JENSEN:
                    if hasattr(self._controller, "query_config"):
                        await self._controller.query_config()

                if self._should_refresh_readable_light_state(force=True):
                    await self._async_refresh_readable_light_state()

                # Store connection metadata for binary sensor
                self._last_connected = datetime.now(UTC)
                self._connection_source = actual_adapter
                self._connection_rssi = adapter_result.rssi
                self._notify_connection_state_change(True)
                self._connection_attempt_details.append(attempt_details)

                return True

            except (BleakError, TimeoutError, OSError) as err:
                attempt_elapsed = time.monotonic() - attempt_start
                attempt_details["total_elapsed_seconds"] = round(attempt_elapsed, 3)
                attempt_details["result"] = "failed"
                attempt_details["error"] = str(err)
                attempt_details["error_type"] = type(err).__name__
                err_str = str(err).lower()
                # Categorize the error for clearer diagnostics
                if isinstance(err, TimeoutError) or "timeout" in err_str:
                    error_category = "CONNECTION TIMEOUT"
                elif "refused" in err_str or "rejected" in err_str:
                    error_category = "CONNECTION REFUSED (another device may be connected)"
                else:
                    error_category = "BLE ERROR"
                attempt_details["error_category"] = error_category

                # Detect connection slot exhaustion and exclude the adapter
                # on subsequent retries so we try an alternative (issue #152).
                if "connection slot" in err_str and adapter_result is not None:
                    failed_source = adapter_result.source
                    if failed_source:
                        exhausted_adapters.add(failed_source)
                        _LOGGER.info(
                            "Adapter %s out of connection slots for %s, "
                            "will try alternative adapter on next retry",
                            failed_source,
                            self._address,
                        )

                # Track connection error for diagnostics (issue #168)
                self._last_connection_error = str(err)
                self._last_connection_error_type = type(err).__name__

                _LOGGER.warning(
                    "✗ %s to %s after %.1fs (attempt %d/%d): %s",
                    error_category,
                    self._address,
                    attempt_elapsed,
                    attempt + 1,
                    self._max_retries,
                    err,
                )
                _LOGGER.debug(
                    "Connection error details - type: %s, args: %s",
                    type(err).__name__,
                    err.args,
                )
                if self._client:
                    _LOGGER.debug("Cleaning up failed connection attempt...")
                    try:
                        await self._client.disconnect()
                        _LOGGER.debug("Disconnect cleanup successful")
                    except Exception as disconnect_err:
                        _LOGGER.debug(
                            "Error during disconnect cleanup: %s (%s)",
                            disconnect_err,
                            type(disconnect_err).__name__,
                        )
                    self._client = None
                self._connection_attempt_details.append(attempt_details)
                # Delay is handled at the start of the next iteration with progressive backoff
            except Exception as err:
                # Track connection error for diagnostics (issue #168)
                self._last_connection_error = str(err)
                self._last_connection_error_type = type(err).__name__
                attempt_details["total_elapsed_seconds"] = round(
                    time.monotonic() - attempt_start, 3
                )
                attempt_details["result"] = "failed"
                attempt_details["error"] = str(err)
                attempt_details["error_type"] = type(err).__name__
                attempt_details["error_category"] = "UNEXPECTED ERROR"

                _LOGGER.warning(
                    "Unexpected error connecting to %s (attempt %d/%d): %s",
                    self._address,
                    attempt + 1,
                    self._max_retries,
                    err,
                )
                _LOGGER.debug(
                    "Exception details - type: %s, args: %s",
                    type(err).__name__,
                    err.args,
                )
                # Log full traceback at debug level
                _LOGGER.debug("Full traceback:\n%s", traceback.format_exc())
                if self._client:
                    _LOGGER.debug("Cleaning up failed connection attempt...")
                    try:
                        await self._client.disconnect()
                        _LOGGER.debug("Disconnect cleanup successful")
                    except Exception as disconnect_err:
                        _LOGGER.debug(
                            "Error during disconnect cleanup: %s (%s)",
                            disconnect_err,
                            type(disconnect_err).__name__,
                        )
                    self._client = None
                self._connection_attempt_details.append(attempt_details)
                # Delay is handled at the start of the next iteration with progressive backoff

        total_elapsed = time.monotonic() - overall_start
        _LOGGER.error(
            "✗ FAILED to connect to %s after %d attempts (%.1fs total). "
            "Troubleshooting:\n"
            "  1. Power cycle bed (unplug 30 seconds)\n"
            "  2. Close any phone apps connected to bed\n"
            "  3. Check Bluetooth adapter is working\n"
            "  4. Move adapter closer to bed\n"
            "  5. If using ESPHome proxy, verify it's online",
            self._address,
            self._max_retries,
            total_elapsed,
        )
        return False

    def _on_disconnect(self, client: BleakClient) -> None:
        """Handle disconnection callback."""
        # Ignore stale disconnect callbacks from old clients
        if client is not self._client:
            _LOGGER.debug(
                "Ignoring stale disconnect callback from old client for %s",
                self._address,
            )
            return

        # If we're in the middle of connecting, this is likely bleak's internal retry
        # for le-connection-abort-by-local - don't log warnings or clear references
        if self._connecting:
            _LOGGER.debug(
                "Disconnect callback during connection establishment for %s (bleak internal retry)",
                self._address,
            )
            return

        # Store disconnect timestamp for binary sensor
        self._last_disconnected = datetime.now(UTC)

        # Track disconnect reason for diagnostics (issue #168)
        # If intentional, reason is set by async_disconnect() or _async_idle_disconnect()
        if not self._intentional_disconnect:
            self._last_disconnect_reason = "unexpected"

        # Stop keepalive task before clearing controller to prevent task leak
        # Capture controller reference before clearing to avoid race condition
        controller = self._controller
        if controller is not None and hasattr(controller, "stop_keepalive"):
            self._stop_keepalive_task = asyncio.create_task(controller.stop_keepalive())

        # If this was an intentional disconnect (manual or idle timeout), don't auto-reconnect
        if self._intentional_disconnect:
            _LOGGER.debug(
                "Intentional disconnect from %s - skipping auto-reconnect",
                self._address,
            )
            self._client = None
            self._controller = None
            # Keep _position_data for last known state; entity availability handles offline
            # Flag is reset in _async_connect_locked when reconnecting
            self._notify_connection_state_change(False)
            return

        _LOGGER.warning(
            "Unexpectedly disconnected from %s. Client details: is_connected=%s, address=%s",
            self._address,
            getattr(client, "is_connected", "N/A"),
            getattr(client, "address", "N/A"),
        )
        _LOGGER.debug(
            "Disconnect callback triggered - clearing client and controller references for %s",
            self._address,
        )
        self._client = None
        self._controller = None
        # Keep _position_data for last known state; entity availability handles offline
        self._cancel_disconnect_timer()
        self._notify_connection_state_change(False)
        _LOGGER.debug("Disconnect cleanup complete for %s", self._address)

        # Schedule automatic reconnection attempt
        # Cancel any existing reconnect timer first to prevent multiple concurrent reconnects
        if self._reconnect_timer is not None:
            self._reconnect_timer.cancel()
        self._reconnect_timer = self.hass.loop.call_later(
            5.0,  # Wait 5 seconds before attempting reconnect
            lambda: asyncio.create_task(self._async_auto_reconnect()),
        )

    async def _async_auto_reconnect(self) -> None:
        """Attempt automatic reconnection after unexpected disconnect."""
        # Timer has fired, clear the reference
        self._reconnect_timer = None

        # Don't reconnect if we're already connected or connecting
        if self._connecting or (self._client is not None and self._client.is_connected):
            _LOGGER.debug("Skipping auto-reconnect: already connected or connecting")
            return

        _LOGGER.info("Attempting automatic reconnection to %s", self._address)
        try:
            connected = await self.async_connect()
            if connected:
                _LOGGER.info("Auto-reconnection successful for %s", self._address)
                # Note: async_start_notify is called automatically in _async_connect_locked
            else:
                _LOGGER.warning(
                    "Auto-reconnection failed for %s. Will retry on next command.",
                    self._address,
                )
        except Exception as err:
            _LOGGER.warning(
                "Auto-reconnection error for %s: %s",
                self._address,
                err,
            )

    async def async_read_initial_positions(self) -> None:
        """Read positions at startup to initialize sensors.

        Called after initial connection to populate position sensors with
        actual values instead of starting as 'unknown'.
        Runs in background with short timeout to not block startup.

        Uses the command lock to prevent concurrent GATT operations with
        commands that may start immediately after connection.
        """
        if self._disable_angle_sensing:
            _LOGGER.debug("Skipping initial position read (angle sensing disabled)")
            return

        _LOGGER.debug("Reading initial positions for %s", self._address)
        try:
            async with asyncio.timeout(5.0):
                # Use command lock to prevent concurrent GATT operations
                async with self._command_lock:
                    if self._client is not None and self._client.is_connected:
                        await self._async_read_positions()
                        # Only log success if position_data has values
                        if self._position_data:
                            _LOGGER.info(
                                "Initial positions read for %s: %s",
                                self._address,
                                {k: f"{v}°" for k, v in self._position_data.items()},
                            )
                        else:
                            _LOGGER.debug("Initial position read completed but no data received")
        except TimeoutError:
            _LOGGER.debug("Initial position read timed out - sensors will update on first command")
        except Exception as err:
            _LOGGER.debug(
                "Initial position read failed: %s - sensors will update on first command", err
            )

    async def async_disconnect(self, reason: str = "intentional") -> None:
        """Disconnect from the bed.

        Args:
            reason: The reason for disconnecting (for diagnostics).
                    Common values: "intentional", "idle_timeout"
        """
        _LOGGER.debug("async_disconnect called for %s", self._address)
        async with self._lock:
            self._cancel_disconnect_timer()
            if self._controller_state_refresh_task is not None:
                self._controller_state_refresh_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await self._controller_state_refresh_task
                self._controller_state_refresh_task = None
            # Cancel any pending reconnect timer
            if self._reconnect_timer is not None:
                self._reconnect_timer.cancel()
                self._reconnect_timer = None
            if self._client is not None:
                _LOGGER.info("Disconnecting from bed at %s", self._address)
                # Mark as intentional so _on_disconnect doesn't trigger auto-reconnect
                self._intentional_disconnect = True
                # Track disconnect reason for diagnostics (issue #168)
                self._last_disconnect_reason = reason
                try:
                    # Stop keep-alive and notifications before disconnecting
                    if self._controller is not None:
                        # Stop Octo keep-alive if running
                        if hasattr(self._controller, "stop_keepalive"):
                            try:
                                # Cast to Any to avoid mypy error about BedController not having stop_keepalive
                                await cast(Any, self._controller).stop_keepalive()
                            except Exception as err:
                                _LOGGER.debug("Error stopping keep-alive: %s", err)
                        try:
                            await self._controller.stop_notify()
                        except Exception as err:
                            _LOGGER.debug("Error stopping notifications: %s", err)
                    await self._client.disconnect()
                    _LOGGER.debug("Successfully disconnected from %s", self._address)
                except BleakError as err:
                    _LOGGER.debug("Error during disconnect from %s: %s", self._address, err)
                finally:
                    self._client = None
                    self._controller = None
                    # Update disconnect timestamp and notify state change
                    # (don't rely on _on_disconnect callback which may not fire on clean disconnect)
                    self._last_disconnected = datetime.now(UTC)
                    self._notify_connection_state_change(False)
                    # Note: _intentional_disconnect is NOT cleared here
                    # It persists until an explicit reconnect to handle late disconnect callbacks

    def _reset_disconnect_timer(self) -> None:
        """Reset the disconnect timer."""
        self._cancel_disconnect_timer()
        _LOGGER.debug(
            "Setting idle disconnect timer for %s (%d seconds)",
            self._address,
            self._idle_disconnect_seconds,
        )
        self._disconnect_timer = self.hass.loop.call_later(
            self._idle_disconnect_seconds,
            lambda: asyncio.create_task(self._async_idle_disconnect()),
        )

    def _cancel_disconnect_timer(self) -> None:
        """Cancel the disconnect timer."""
        if self._disconnect_timer is not None:
            _LOGGER.debug("Cancelling idle disconnect timer for %s", self._address)
            self._disconnect_timer.cancel()
            self._disconnect_timer = None

    def pause_disconnect_timer(self) -> None:
        """Pause the disconnect timer (for external use like diagnostics).

        Call resume_disconnect_timer() when done to restart the timer.
        """
        self._cancel_disconnect_timer()
        _LOGGER.debug("Disconnect timer paused for %s", self._address)

    def resume_disconnect_timer(self) -> None:
        """Resume the disconnect timer after pausing.

        This resets the timer, giving a full idle timeout from now.
        """
        if self._client is not None and self._client.is_connected:
            self._reset_disconnect_timer()
            _LOGGER.debug("Disconnect timer resumed for %s", self._address)

    async def _async_idle_disconnect(self) -> None:
        """Disconnect after idle timeout."""
        _LOGGER.info(
            "Idle timeout reached (%d seconds), disconnecting from %s",
            self._idle_disconnect_seconds,
            self._address,
        )
        await self.async_disconnect(reason="idle_timeout")

    async def async_ensure_connected(self, reset_timer: bool = True) -> bool:
        """Ensure we are connected to the bed."""
        async with self._lock:
            if self._client is not None and self._client.is_connected:
                _LOGGER.debug("Connection check: already connected to %s", self._address)
                if reset_timer:
                    self._reset_disconnect_timer()
                return True
            _LOGGER.debug("Connection check: reconnecting to %s", self._address)
            return await self._async_connect_locked(reset_timer=reset_timer)

    async def _async_refresh_controller_auth(self) -> None:
        """Refresh protocol auth for controllers that require re-authentication."""
        if self._controller is None:
            return

        # Jensen can require a fresh PIN unlock command even on reused BLE connections.
        if self._bed_type == BED_TYPE_JENSEN and hasattr(self._controller, "send_pin"):
            _LOGGER.debug("Refreshing Jensen PIN unlock before command on %s", self._address)
            await cast(Any, self._controller).send_pin()

    async def async_write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 100,
        cancel_running: bool = True,
    ) -> None:
        """Write a command to the bed.

        Motor commands cancel any running command for immediate response.
        """
        if cancel_running:
            # Cancel any running command immediately
            self._cancel_counter += 1
            self._cancel_command.set()

        # Capture cancel count at entry to detect if we get cancelled while waiting
        entry_cancel_count = self._cancel_counter

        async with self._command_lock:
            # Cancel disconnect timer while command is in progress to prevent mid-command disconnect
            self._cancel_disconnect_timer()

            # Check if we were cancelled while waiting for the lock
            if self._cancel_counter > entry_cancel_count:
                _LOGGER.debug("Command %s cancelled while waiting for lock", command.hex())
                # Reset disconnect timer since we're bailing out
                if self._client is not None and self._client.is_connected:
                    self._reset_disconnect_timer()
                return

            try:
                # Clear cancel signal for this command
                self._cancel_command.clear()

                _LOGGER.debug(
                    "async_write_command: %s (repeat: %d, delay: %dms)",
                    command.hex(),
                    repeat_count,
                    repeat_delay_ms,
                )
                if not await self.async_ensure_connected(reset_timer=False):
                    _LOGGER.error("Cannot write command: not connected to bed")
                    raise ConnectionError("Not connected to bed")

                if self._controller is None:
                    _LOGGER.error("Cannot write command: no controller available")
                    raise RuntimeError("No controller available")

                await self._async_refresh_controller_auth()

                # Start position polling during movement if angle sensing enabled
                poll_stop: asyncio.Event | None = None
                poll_task: asyncio.Task[None] | None = None
                if (
                    not self._disable_angle_sensing
                    and self._controller.allow_position_polling_during_commands
                ):
                    poll_stop = asyncio.Event()
                    poll_task = asyncio.create_task(
                        self._async_poll_positions_during_movement(poll_stop)
                    )

                try:
                    await self._controller.write_command(
                        command, repeat_count, repeat_delay_ms, self._cancel_command
                    )
                finally:
                    # Stop polling
                    if poll_stop is not None:
                        poll_stop.set()
                    if poll_task is not None:
                        poll_task.cancel()
                        with contextlib.suppress(asyncio.CancelledError):
                            await poll_task

                # Final position read after command
                if not self._disable_angle_sensing and not self._cancel_command.is_set():
                    if self._position_mode == POSITION_MODE_ACCURACY:
                        # Accuracy mode: wait for read to complete
                        await self._async_read_positions()
                    else:
                        # Speed mode: fire-and-forget with lock to prevent concurrent GATT ops
                        self.hass.async_create_task(self._async_read_positions_background())
            finally:
                if self._client is not None and self._client.is_connected:
                    self._reset_disconnect_timer()

    async def async_stop_command(self) -> None:
        """Immediately stop any running command and send stop to bed."""
        _LOGGER.info("Stop requested - cancelling current command")

        # Signal cancellation to any running command
        self._cancel_counter += 1
        self._cancel_command.set()

        # Acquire the command lock to wait for any in-flight GATT write to complete
        # This prevents concurrent BLE writes which cause "operation in progress" errors
        # NOTE: Stop is safety-critical and must ALWAYS complete - no early return if
        # cancel_counter changes while waiting (that would leave motors running)
        async with self._command_lock:
            # Cancel disconnect timer while command is in progress
            self._cancel_disconnect_timer()
            try:
                if not await self.async_ensure_connected(reset_timer=False):
                    _LOGGER.error("Cannot send stop: not connected to bed")
                    return

                if self._controller is None:
                    _LOGGER.error("Cannot send stop: no controller available")
                    return

                try:
                    await self._async_refresh_controller_auth()
                except BleakError as err:
                    _LOGGER.warning(
                        "Auth refresh failed before stop command on %s: %s",
                        self._address,
                        err,
                    )
                except Exception as err:
                    _LOGGER.warning(
                        "Unexpected auth refresh failure before stop command on %s: %s",
                        self._address,
                        err,
                        exc_info=True,
                    )

                # Use controller's stop_all method which knows the correct protocol
                await self._controller.stop_all()
                _LOGGER.info("Stop command sent")
            finally:
                if self._client is not None and self._client.is_connected:
                    # Disconnect immediately if configured to do so
                    if self._disconnect_after_command:
                        _LOGGER.debug(
                            "Disconnecting after stop command (disconnect_after_command=True) for %s",
                            self._address,
                        )
                        await self.async_disconnect()
                    else:
                        # Otherwise, reset the idle disconnect timer
                        self._reset_disconnect_timer()

    async def _async_prepare_controller_operation(self, operation_name: str) -> BedController:
        """Ensure the controller is connected and authenticated before use."""
        self._cancel_command.clear()

        if not await self.async_ensure_connected(reset_timer=False):
            _LOGGER.error("Cannot execute %s: not connected to bed", operation_name)
            raise ConnectionError("Not connected to bed")

        controller = self._controller
        if controller is None:
            _LOGGER.error("Cannot execute %s: no controller available", operation_name)
            raise RuntimeError("No controller available")

        await self._async_refresh_controller_auth()
        return controller

    async def _async_finish_controller_operation(
        self,
        *,
        entry_cancel_count: int,
        skip_disconnect: bool,
        operation_name: str,
    ) -> None:
        """Handle disconnect timer reset or disconnect after an operation completes."""
        if self._client is None or not self._client.is_connected:
            return

        command_preempted = self._cancel_counter > entry_cancel_count
        if self._disconnect_after_command and not skip_disconnect and not command_preempted:
            _LOGGER.debug(
                "Disconnecting after %s (disconnect_after_command=True) for %s",
                operation_name,
                self._address,
            )
            await self.async_disconnect()
            return

        if command_preempted:
            _LOGGER.debug(
                "Skipping disconnect for %s: newer command is pending",
                self._address,
            )
        self._reset_disconnect_timer()

    async def _async_wait_for_controller_operation(
        self,
        operation_task: asyncio.Task[T],
        *,
        operation_name: str,
        raise_on_cancel: bool,
    ) -> T | None:
        """Wait for a controller operation or cancel it when preempted."""
        cancel_wait_task = asyncio.create_task(self._cancel_command.wait())
        try:
            done, pending = await asyncio.wait(
                {operation_task, cancel_wait_task},
                return_when=asyncio.FIRST_COMPLETED,
            )

            for task in pending:
                task.cancel()
            for task in pending:
                with contextlib.suppress(asyncio.CancelledError):
                    await task

            if cancel_wait_task in done:
                _LOGGER.debug("Controller %s cancelled during execution", operation_name)
                if not operation_task.done():
                    operation_task.cancel()
                try:
                    await operation_task
                except asyncio.CancelledError:
                    pass
                except Exception as err:
                    _LOGGER.debug(
                        "Controller %s raised while cancelling: %s",
                        operation_name,
                        err,
                    )
                if raise_on_cancel:
                    raise asyncio.CancelledError
                return None

            return operation_task.result()
        finally:
            for task in (operation_task, cancel_wait_task):
                if task.done():
                    continue
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task

    async def _async_execute_controller_operation(
        self,
        operation_fn: Callable[[BedController], Coroutine[Any, Any, T]],
        *,
        cancel_running: bool,
        skip_disconnect: bool,
        raise_on_lock_cancel: bool,
        enable_position_polling: bool,
        read_positions_after_operation: bool,
        operation_name: str,
    ) -> T | None:
        """Execute a controller operation with shared locking and connection handling."""
        if cancel_running:
            self._cancel_counter += 1
            self._cancel_command.set()

        entry_cancel_count = self._cancel_counter

        async with self._command_lock:
            self._cancel_disconnect_timer()

            if self._cancel_counter > entry_cancel_count:
                _LOGGER.debug("Controller %s cancelled while waiting for lock", operation_name)
                if self._client is not None and self._client.is_connected:
                    self._reset_disconnect_timer()
                if raise_on_lock_cancel:
                    raise asyncio.CancelledError
                return None

            try:
                controller = await self._async_prepare_controller_operation(operation_name)
                self._last_command_start = datetime.now(UTC)

                poll_stop: asyncio.Event | None = None
                poll_task: asyncio.Task[None] | None = None
                if (
                    enable_position_polling
                    and not self._disable_angle_sensing
                    and controller.allow_position_polling_during_commands
                ):
                    poll_stop = asyncio.Event()
                    poll_task = asyncio.create_task(
                        self._async_poll_positions_during_movement(poll_stop)
                    )

                try:
                    operation_task = asyncio.create_task(operation_fn(controller))
                    result = await self._async_wait_for_controller_operation(
                        operation_task,
                        operation_name=operation_name,
                        raise_on_cancel=raise_on_lock_cancel,
                    )
                finally:
                    self._last_command_end = datetime.now(UTC)
                    if poll_stop is not None:
                        poll_stop.set()
                    if poll_task is not None:
                        poll_task.cancel()
                        with contextlib.suppress(asyncio.CancelledError):
                            await poll_task

                if (
                    read_positions_after_operation
                    and not self._disable_angle_sensing
                    and not self._cancel_command.is_set()
                ):
                    if self._position_mode == POSITION_MODE_ACCURACY:
                        await self._async_read_positions()
                    else:
                        self.hass.async_create_task(self._async_read_positions_background())

                return result
            except (ConnectionError, RuntimeError):
                if (
                    self._client is not None
                    and self._client.is_connected
                    and not self._disconnect_after_command
                ):
                    self._reset_disconnect_timer()
                raise
            finally:
                await self._async_finish_controller_operation(
                    entry_cancel_count=entry_cancel_count,
                    skip_disconnect=skip_disconnect,
                    operation_name=operation_name,
                )

    async def async_execute_controller_command(
        self,
        command_fn: Callable[[BedController], Coroutine[Any, Any, None]],
        cancel_running: bool = True,
        skip_disconnect: bool = False,
    ) -> None:
        """Execute a controller command with proper serialization."""
        await self._async_execute_controller_operation(
            command_fn,
            cancel_running=cancel_running,
            skip_disconnect=skip_disconnect,
            raise_on_lock_cancel=False,
            enable_position_polling=True,
            read_positions_after_operation=True,
            operation_name="command",
        )

    async def async_execute_controller_query(
        self,
        query_fn: Callable[[BedController], Coroutine[Any, Any, T]],
        cancel_running: bool = False,
        skip_disconnect: bool = False,
    ) -> T:
        """Execute a controller query and return its result."""
        result = await self._async_execute_controller_operation(
            query_fn,
            cancel_running=cancel_running,
            skip_disconnect=skip_disconnect,
            raise_on_lock_cancel=True,
            enable_position_polling=False,
            read_positions_after_operation=False,
            operation_name="query",
        )
        return cast(T, result)

    async def async_start_notify(self) -> None:
        """Start listening for position notifications."""
        if self._controller is None:
            _LOGGER.warning("Cannot start notifications: no controller available")
            return

        requires_notify_channel = getattr(self._controller, "requires_notification_channel", False)
        if not isinstance(requires_notify_channel, bool):
            requires_notify_channel = False

        # Some controllers depend on notifications for command responses or
        # authentication even when angle sensing is disabled.
        if requires_notify_channel:
            if self._disable_angle_sensing:
                _LOGGER.info(
                    "Starting controller notifications for %s (%s requires notify channel with angle sensing disabled)",
                    self._address,
                    self._bed_type,
                )
                await self._controller.start_notify(None)
            else:
                _LOGGER.info(
                    "Starting controller notifications for %s (%s requires notify channel)",
                    self._address,
                    self._bed_type,
                )
                await self._controller.start_notify(self._handle_position_update)
            return

        if self._disable_angle_sensing:
            _LOGGER.info(
                "Angle sensing disabled for %s - skipping position notifications (physical remote will remain functional)",
                self._address,
            )
            return

        _LOGGER.info("Starting position notifications for %s", self._address)
        await self._controller.start_notify(self._handle_position_update)

    async def async_start_notify_for_diagnostics(self) -> None:
        """Start notifications for diagnostic capture, bypassing angle sensing setting.

        Unlike async_start_notify(), this always starts notifications regardless of
        the disable_angle_sensing setting. Used by diagnostics to capture raw protocol
        data from devices that have angle sensing disabled.
        """
        if self._controller is None:
            _LOGGER.warning("Cannot start diagnostic notifications: no controller available")
            return

        _LOGGER.info(
            "Starting notifications for diagnostic capture on %s (bypassing angle sensing setting)",
            self._address,
        )
        await self._controller.start_notify(self._handle_position_update)

    def set_raw_notify_callback(self, callback: Callable[[str, bytes], None] | None) -> None:
        """Set a callback to receive raw notification data.

        Used by diagnostics to capture raw BLE notifications from the controller
        without disrupting normal notification handling.

        Args:
            callback: Function to call with (characteristic_uuid, data), or None to clear.
        """
        if self._controller is not None:
            self._controller.set_raw_notify_callback(callback)

    async def _async_read_positions(self) -> None:
        """Actively read current positions from the bed.

        Called after movement commands to ensure position data is up to date.
        Uses a short timeout to avoid blocking commands.

        Note: This method does NOT acquire the command lock. When called from
        within a command (which already holds the lock), this is correct.
        For fire-and-forget background reads, use _async_read_positions_background().
        """
        if self._controller is None:
            return

        try:
            async with asyncio.timeout(3.0):
                await self._controller.read_positions(self._motor_count)
        except TimeoutError:
            _LOGGER.debug("Position read timed out")
        except Exception as err:
            _LOGGER.debug("Failed to read positions: %s", err)

    async def _async_read_positions_background(self) -> None:
        """Read positions in background with proper lock serialization.

        This method acquires the command lock to prevent concurrent GATT operations.
        Use this for fire-and-forget position reads (speed mode) to avoid
        "operation in progress" errors from overlapping BLE operations.
        """
        async with self._command_lock:
            await self._async_read_positions()

    async def _async_poll_positions_during_movement(self, stop_event: asyncio.Event) -> None:
        """Poll positions periodically during movement.

        Some motors (like Linak back) don't send notifications, only support reads.
        This provides real-time position updates during movement for those motors.
        Only polls motors that don't support notifications to avoid redundant reads.
        """
        if self._controller is None:
            return

        poll_interval = 0.5  # 500ms between polls
        while not stop_event.is_set():
            try:
                # Only read motors that don't send notifications
                async with asyncio.timeout(0.4):
                    await self._controller.read_non_notifying_positions()
            except TimeoutError:
                pass  # Timeout is expected during rapid polling
            except Exception as err:
                _LOGGER.debug("Position polling error (non-fatal): %s", err)

            # Wait for interval or stop signal
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=poll_interval)
                break  # Stop event was set
            except TimeoutError:
                pass  # Continue polling

    @callback
    def _handle_position_update(self, position: str, angle: float) -> None:
        """Handle a position update from the bed."""
        _LOGGER.debug("Position update: %s = %.1f°", position, angle)
        self._position_data[position] = angle
        # Track notification timing for diagnostics (issue #168)
        self._last_notify_received = datetime.now(UTC)
        # Copy to safely iterate while callbacks might unregister themselves
        for callback_fn in list(self._position_callbacks):
            try:
                callback_fn(self._position_data)
            except Exception as err:
                _LOGGER.warning("Position callback error: %s", err)

    def register_position_callback(
        self, callback_fn: Callable[[dict[str, float]], None]
    ) -> Callable[[], None]:
        """Register a callback for position updates."""
        self._position_callbacks.add(callback_fn)

        # Immediately emit current position data if available
        # This handles the race where initial read completed before registration
        if self._position_data:
            try:
                callback_fn(self._position_data)
            except Exception as err:
                _LOGGER.warning("Position callback error during registration: %s", err)

        def unregister() -> None:
            self._position_callbacks.discard(callback_fn)  # Safe removal, no error if missing

        return unregister

    def register_controller_state_callback(
        self, callback_fn: Callable[[dict[str, Any]], None]
    ) -> Callable[[], None]:
        """Register a callback for non-position controller state updates."""
        self._controller_state_callbacks.add(callback_fn)

        if self._controller_state:
            try:
                callback_fn(self._controller_state)
            except Exception as err:
                _LOGGER.warning("Controller state callback error during registration: %s", err)

        self._schedule_controller_state_refresh()

        def unregister() -> None:
            self._controller_state_callbacks.discard(callback_fn)

        return unregister

    def _should_refresh_readable_light_state(self, *, force: bool) -> bool:
        """Return True when controller light state should be refreshed from the bed."""
        if not self._controller_state_callbacks:
            return False

        if self._client is None or not self._client.is_connected or self._controller is None:
            return False

        if not self._controller.supports_under_bed_lights:
            return False

        if force:
            return True

        required_keys = {
            "under_bed_lights_on",
            "light_level",
            "light_timer_minutes",
            "light_timer_option",
        }
        return not required_keys.issubset(self._controller_state)

    @callback
    def _merge_controller_light_state(self, state: dict[str, Any]) -> None:
        """Merge readable light-state values into coordinator state."""
        updates = {
            key: value for key, value in state.items() if self._controller_state.get(key) != value
        }
        if updates:
            self.handle_controller_state_updates(updates)

    async def _async_refresh_readable_light_state(self) -> None:
        """Read light state from the controller and merge any fresh values."""
        controller = self._controller
        if controller is None:
            return

        try:
            async with asyncio.timeout(_READABLE_LIGHT_STATE_TIMEOUT):
                state = await controller.read_light_state()
        except asyncio.CancelledError:
            raise
        except NotImplementedError:
            _LOGGER.debug(
                "Controller %s does not expose readable light state",
                self._bed_type,
            )
            return
        except (BleakError, ConnectionError, RuntimeError, TimeoutError, ValueError) as err:
            _LOGGER.debug(
                "Failed to refresh readable light state for %s: %s",
                self._address,
                err,
            )
            return
        except Exception:
            _LOGGER.debug(
                "Unexpected readable light state refresh failure for %s",
                self._address,
                exc_info=True,
            )
            return

        self._merge_controller_light_state(state)

    async def _async_refresh_readable_light_state_task(self) -> None:
        """Run the controller-state refresh task and clear its tracking handle."""
        try:

            async def _read_light_state(controller: BedController) -> dict[str, Any]:
                return await controller.read_light_state()

            async with asyncio.timeout(_READABLE_LIGHT_STATE_TIMEOUT):
                state = await self.async_execute_controller_query(
                    _read_light_state,
                    cancel_running=False,
                    skip_disconnect=True,
                )
            self._merge_controller_light_state(state)
        except asyncio.CancelledError:
            raise
        except NotImplementedError:
            _LOGGER.debug(
                "Controller %s does not expose readable light state",
                self._bed_type,
            )
        except (BleakError, ConnectionError, RuntimeError, TimeoutError, ValueError) as err:
            _LOGGER.debug(
                "Failed to refresh readable light state for %s: %s",
                self._address,
                err,
            )
        except Exception:
            _LOGGER.debug(
                "Unexpected readable light state refresh failure for %s",
                self._address,
                exc_info=True,
            )
        finally:
            self._controller_state_refresh_task = None

    def _schedule_controller_state_refresh(self) -> None:
        """Schedule a one-shot controller-state refresh when entities need it."""
        if not self._should_refresh_readable_light_state(force=False):
            return

        if (
            self._controller_state_refresh_task is not None
            and not self._controller_state_refresh_task.done()
        ):
            return

        self._controller_state_refresh_task = self.hass.async_create_task(
            self._async_refresh_readable_light_state_task()
        )

    @callback
    def handle_controller_state_update(self, key: str, value: Any) -> None:
        """Store a single controller state value and notify listeners."""
        self.handle_controller_state_updates({key: value})

    @callback
    def handle_controller_state_updates(self, updates: dict[str, Any]) -> None:
        """Store controller state values and notify listeners."""
        if not updates:
            return

        self._controller_state.update(updates)
        for callback_fn in list(self._controller_state_callbacks):
            try:
                callback_fn(self._controller_state)
            except Exception as err:
                _LOGGER.warning("Controller state callback error: %s", err)

    def register_connection_state_callback(
        self, callback_fn: Callable[[bool], None]
    ) -> Callable[[], None]:
        """Register a callback for connection state changes."""
        self._connection_state_callbacks.add(callback_fn)

        def unregister() -> None:
            self._connection_state_callbacks.discard(callback_fn)

        return unregister

    def _notify_connection_state_change(self, connected: bool) -> None:
        """Notify all registered callbacks of a connection state change."""
        for callback_fn in list(self._connection_state_callbacks):
            try:
                callback_fn(connected)
            except Exception as err:
                _LOGGER.warning("Connection state callback error: %s", err)

    async def async_seek_position(
        self,
        position_key: str,
        target_angle: float,
        move_up_fn: Callable[[BedController], Coroutine[Any, Any, None]],
        move_down_fn: Callable[[BedController], Coroutine[Any, Any, None]],
        move_stop_fn: Callable[[BedController], Coroutine[Any, Any, None]],
    ) -> None:
        """Seek to a target position using feedback loop control.

        This method moves the motor toward the target position by polling the
        current position and adjusting direction as needed. It handles:
        - Immediate return if already at target position
        - Timeout protection (60s max)
        - Stall detection (motor not moving)
        - Cancellation via the cancel_command event

        Args:
            position_key: Key in position_data (e.g., "back", "legs")
            target_angle: Target position in degrees (or percentage for Keeson/Ergomotion)
            move_up_fn: Async function to move motor up
            move_down_fn: Async function to move motor down
            move_stop_fn: Async function to stop motor
        """
        # Cancel any running command FIRST (before tolerance check)
        # This ensures any in-flight seek is cancelled even if new target is already satisfied
        self._cancel_counter += 1
        self._cancel_command.set()
        entry_cancel_count = self._cancel_counter

        async with self._command_lock:
            # Cancel disconnect timer during seeking
            self._cancel_disconnect_timer()

            # Check if cancelled while waiting for lock
            if self._cancel_counter > entry_cancel_count:
                _LOGGER.debug("Position seek cancelled while waiting for lock")
                if self._client is not None and self._client.is_connected:
                    self._reset_disconnect_timer()
                return

            try:
                # Clear cancel signal
                self._cancel_command.clear()

                if not await self.async_ensure_connected(reset_timer=False):
                    _LOGGER.error("Cannot seek position: not connected to bed")
                    raise NotConnectedError("Not connected to bed")

                if self._controller is None:
                    _LOGGER.error("Cannot seek position: no controller available")
                    raise NoControllerError("No controller available")

                await self._async_refresh_controller_auth()

                supports_direct_position_control = self._controller.supports_direct_position_control

                # Get current position, attempting a read if not available.
                # Direct-position controllers can operate without a current reading.
                current_angle = self._position_data.get(position_key)
                if current_angle is None and not supports_direct_position_control:
                    _LOGGER.debug(
                        "No position data for %s, attempting one-shot read",
                        position_key,
                    )
                    await self._async_read_positions()
                    current_angle = self._position_data.get(position_key)
                    if current_angle is None:
                        raise NotConnectedError(
                            f"Cannot seek {position_key}: no position data available"
                        )

                # Check if already at target (within tolerance)
                if (
                    current_angle is not None
                    and abs(current_angle - target_angle) <= POSITION_TOLERANCE
                ):
                    _LOGGER.debug(
                        "Position %s already at target: %.1f (target: %.1f)",
                        position_key,
                        current_angle,
                        target_angle,
                    )
                    return  # finally block handles disconnect

                if current_angle is None:
                    _LOGGER.info(
                        "Seeking position %s to %.1f without current feedback",
                        position_key,
                        target_angle,
                    )
                else:
                    _LOGGER.info(
                        "Seeking position %s from %.1f to %.1f",
                        position_key,
                        current_angle,
                        target_angle,
                    )

                # Check if controller supports direct position control (e.g., Reverie)
                # This bypasses the incremental seek loop for beds that can set positions directly
                if supports_direct_position_control:
                    native_position = self._controller.angle_to_native_position(
                        position_key, target_angle
                    )
                    _LOGGER.debug(
                        "Using direct position control: %s -> %d",
                        position_key,
                        native_position,
                    )
                    await self._controller.set_motor_position(position_key, native_position)
                    self._handle_position_update(position_key, target_angle)
                    return  # finally block handles disconnect timer

                # Determine initial direction
                moving_up = target_angle > current_angle

                # Start movement in try-finally to guarantee stop is sent
                try:
                    if moving_up:
                        await move_up_fn(self._controller)
                    else:
                        await move_down_fn(self._controller)

                    # Tracking variables
                    start_time = time.monotonic()
                    stall_count = 0
                    last_angle = current_angle

                    # Position seeking loop
                    while True:
                        # Check for timeout
                        if time.monotonic() - start_time > POSITION_SEEK_TIMEOUT:
                            _LOGGER.warning(
                                "Position seek timeout for %s after %.0fs",
                                position_key,
                                POSITION_SEEK_TIMEOUT,
                            )
                            break

                        # Check for cancellation
                        if self._cancel_command.is_set():
                            _LOGGER.debug("Position seek cancelled for %s", position_key)
                            break

                        # Wait and poll position
                        await asyncio.sleep(POSITION_CHECK_INTERVAL)

                        # Read current position
                        await self._async_read_positions()

                        # Get updated position
                        current_angle = self._position_data.get(position_key)
                        if current_angle is None:
                            _LOGGER.warning(
                                "Lost position data for %s during seek",
                                position_key,
                            )
                            break

                        _LOGGER.debug(
                            "Position seek %s: current=%.1f, target=%.1f",
                            position_key,
                            current_angle,
                            target_angle,
                        )

                        # Check if at target
                        if abs(current_angle - target_angle) <= POSITION_TOLERANCE:
                            _LOGGER.info(
                                "Position %s reached target: %.1f (target: %.1f)",
                                position_key,
                                current_angle,
                                target_angle,
                            )
                            break

                        # Check for overshoot (passed the target)
                        # Overshoot reversal is a safety correction - clear cancel
                        # to allow reversal movement, but check _cancel_counter to
                        # detect if a NEW stop was requested (not just the prior
                        # cancel that the seek itself issued on entry). If counter
                        # changed, a real user-initiated stop arrived and we must
                        # honour it instead of reversing.
                        # Use larger overshoot tolerance to prevent oscillation
                        if (
                            moving_up
                            and current_angle > target_angle + POSITION_OVERSHOOT_TOLERANCE
                        ):
                            _LOGGER.debug(
                                "Position %s overshot target (up), reversing", position_key
                            )
                            # Only send explicit stop for controllers that don't auto-stop
                            # (Linak auto-stops and explicit STOP can cause reverse blips)
                            if not getattr(self._controller, "auto_stops_on_idle", False):
                                await move_stop_fn(self._controller)
                                await asyncio.sleep(0.3)  # Ensure stop completes before reversal
                            # Check if a new stop was requested while we were stopping
                            if self._cancel_counter > entry_cancel_count:
                                _LOGGER.debug(
                                    "New stop request during overshoot - aborting reversal"
                                )
                                break
                            self._cancel_command.clear()  # Ensure reversal isn't cancelled
                            await move_down_fn(self._controller)
                            moving_up = False
                        elif (
                            not moving_up
                            and current_angle < target_angle - POSITION_OVERSHOOT_TOLERANCE
                        ):
                            _LOGGER.debug(
                                "Position %s overshot target (down), reversing", position_key
                            )
                            # Only send explicit stop for controllers that don't auto-stop
                            # (Linak auto-stops and explicit STOP can cause reverse blips)
                            if not getattr(self._controller, "auto_stops_on_idle", False):
                                await move_stop_fn(self._controller)
                                await asyncio.sleep(0.3)  # Ensure stop completes before reversal
                            # Check if a new stop was requested while we were stopping
                            if self._cancel_counter > entry_cancel_count:
                                _LOGGER.debug(
                                    "New stop request during overshoot - aborting reversal"
                                )
                                break
                            self._cancel_command.clear()  # Ensure reversal isn't cancelled
                            await move_up_fn(self._controller)
                            moving_up = True

                        # Stall detection - re-issue movement if motor stopped prematurely
                        movement = abs(current_angle - last_angle)
                        if movement < POSITION_STALL_THRESHOLD:
                            stall_count += 1
                            if stall_count >= POSITION_STALL_COUNT:
                                # Motor appears stalled - re-issue movement command
                                # This handles pulse-based protocols where motors auto-stop
                                _LOGGER.debug(
                                    "Position %s stalled at %.1f, re-issuing movement command",
                                    position_key,
                                    current_angle,
                                )
                                if moving_up:
                                    await move_up_fn(self._controller)
                                else:
                                    await move_down_fn(self._controller)
                                stall_count = 0  # Reset stall count after re-issue
                        else:
                            stall_count = 0

                        last_angle = current_angle
                finally:
                    # Stop the motor unless it auto-stops on idle
                    # Some controllers (e.g., Linak) auto-stop and sending explicit
                    # STOP can cause brief reverse movement
                    if not getattr(self._controller, "auto_stops_on_idle", False):
                        try:
                            await move_stop_fn(self._controller)
                        except Exception:
                            _LOGGER.exception(
                                "CRITICAL: Failed to stop motor %s - manual intervention may be required",
                                position_key,
                            )
                            raise

            finally:
                if self._client is not None and self._client.is_connected:
                    if self._disconnect_after_command:
                        _LOGGER.debug(
                            "Disconnecting after seek (disconnect_after_command=True) for %s",
                            self._address,
                        )
                        await self.async_disconnect()
                    else:
                        self._reset_disconnect_timer()
