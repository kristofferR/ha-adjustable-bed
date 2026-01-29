"""Coordinator for Adjustable Bed integration."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import random
import time
import traceback
from collections.abc import Callable, Coroutine
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, cast

from bleak import BleakClient
from bleak.backends.device import BLEDevice
from bleak.exc import BleakError
from bleak_retry_connector import establish_connection
from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo

from .adapter import (
    detect_esphome_proxy,
    discover_services,
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
    BED_TYPE_LINAK,
    BED_TYPE_MALOUF_LEGACY_OKIN,
    BED_TYPE_MALOUF_NEW_OKIN,
    BED_TYPE_MATTRESSFIRM,
    BED_TYPE_MOTOSLEEP,
    BED_TYPE_NECTAR,
    BED_TYPE_OCTO,
    BED_TYPE_OKIMAT,
    BED_TYPE_OKIN_7BYTE,
    BED_TYPE_OKIN_FFE,
    BED_TYPE_OKIN_HANDLE,
    BED_TYPE_OKIN_NORDIC,
    BED_TYPE_OKIN_UUID,
    BED_TYPE_REVERIE,
    BED_TYPE_REVERIE_NIGHTSTAND,
    BED_TYPE_RICHMAT,
    BED_TYPE_SERTA,
    BED_TYPE_SOLACE,
    CONF_BED_TYPE,
    CONF_CONNECTION_PROFILE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_DISCONNECT_AFTER_COMMAND,
    CONF_HAS_MASSAGE,
    CONF_IDLE_DISCONNECT_SECONDS,
    CONF_JENSEN_PIN,
    CONF_MOTOR_COUNT,
    CONF_MOTOR_PULSE_COUNT,
    CONF_MOTOR_PULSE_DELAY_MS,
    CONF_OCTO_PIN,
    CONF_POSITION_MODE,
    CONF_PREFERRED_ADAPTER,
    CONF_PROTOCOL_VARIANT,
    CONF_RICHMAT_REMOTE,
    DEFAULT_DISABLE_ANGLE_SENSING,
    DEFAULT_DISCONNECT_AFTER_COMMAND,
    DEFAULT_HAS_MASSAGE,
    DEFAULT_IDLE_DISCONNECT_SECONDS,
    DEFAULT_CONNECTION_PROFILE,
    DEFAULT_MOTOR_COUNT,
    DEFAULT_MOTOR_PULSE_COUNT,
    DEFAULT_MOTOR_PULSE_DELAY_MS,
    DEFAULT_OCTO_PIN,
    DEFAULT_POSITION_MODE,
    DEFAULT_PROTOCOL_VARIANT,
    DOMAIN,
    CONNECTION_PROFILES,
    POSITION_CHECK_INTERVAL,
    POSITION_MODE_ACCURACY,
    POSITION_OVERSHOOT_TOLERANCE,
    POSITION_SEEK_TIMEOUT,
    POSITION_STALL_COUNT,
    POSITION_STALL_THRESHOLD,
    POSITION_TOLERANCE,
    OKIMAT_SERVICE_UUID,
    RICHMAT_REMOTE_AUTO,
    requires_pairing,
)
from .controller_factory import create_controller

if TYPE_CHECKING:
    from .beds.base import BedController

_LOGGER = logging.getLogger(__name__)


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
        self._motor_count: int = entry.data.get(CONF_MOTOR_COUNT, DEFAULT_MOTOR_COUNT)
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

        # Richmat-specific configuration
        self._richmat_remote: str = entry.data.get(CONF_RICHMAT_REMOTE, RICHMAT_REMOTE_AUTO)

        # Jensen-specific configuration
        self._jensen_pin: str = entry.data.get(CONF_JENSEN_PIN, "")

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
    def motor_pulse_count(self) -> int:
        """Return the motor pulse count."""
        return self._motor_pulse_count

    @property
    def motor_pulse_delay_ms(self) -> int:
        """Return the motor pulse delay in milliseconds."""
        return self._motor_pulse_delay_ms

    @property
    def controller(self) -> BedController | None:
        """Return the bed controller."""
        return self._controller

    @property
    def position_data(self) -> dict[str, float]:
        """Return current position data."""
        return self._position_data

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
    def cancel_command(self) -> asyncio.Event:
        """Return the cancel command event."""
        return self._cancel_command

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

        for attempt in range(self._max_retries):
            attempt_start = time.monotonic()
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
                except Exception as err:
                    _LOGGER.debug("Could not get scanner count: %s", err)

                # Select best adapter and get device
                adapter_result = await select_adapter(
                    self.hass, self._address, self._preferred_adapter
                )
                device = adapter_result.device

                if device is None:
                    lookup_elapsed = time.monotonic() - attempt_start
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
                        discovered = list(
                            bluetooth.async_discovered_service_info(self.hass, connectable=True)
                        )
                        if discovered:
                            _LOGGER.debug(
                                "Currently visible BLE devices (%d total):",
                                len(discovered),
                            )
                            for svc_info in discovered[:10]:  # Limit to first 10
                                _LOGGER.debug(
                                    "  - %s (name: %s, rssi: %s, source: %s)",
                                    svc_info.address,
                                    svc_info.name or "Unknown",
                                    getattr(svc_info, "rssi", "N/A"),
                                    getattr(svc_info, "source", "N/A"),
                                )
                            if len(discovered) > 10:
                                _LOGGER.debug("  ... and %d more devices", len(discovered) - 10)
                        else:
                            _LOGGER.debug("No BLE devices currently visible")
                    except Exception as err:
                        _LOGGER.debug("Could not enumerate visible devices: %s", err)
                    # Don't sleep here - the retry backoff at loop start handles delays
                    continue

                # Log detailed device info including which adapter discovered it
                device_source = None
                if hasattr(device, "details") and isinstance(device.details, dict):
                    device_source = device.details.get("source")

                lookup_elapsed = time.monotonic() - attempt_start
                _LOGGER.info(
                    "✓ Device %s FOUND in %.1fs (name: %s) via adapter: %s",
                    self._address,
                    lookup_elapsed,
                    device.name or "Unknown",
                    device_source or "unknown",
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

                # Create a callback to get fresh device from preferred adapter on retries
                ble_device_callback: Callable[[], BLEDevice] | None = None
                if self._preferred_adapter and self._preferred_adapter != ADAPTER_AUTO:

                    def _get_device_from_preferred_adapter() -> BLEDevice:
                        """Get a fresh BLEDevice from the preferred adapter."""
                        for svc_info in bluetooth.async_discovered_service_info(
                            self.hass, connectable=True
                        ):
                            if (
                                svc_info.address.upper() == self._address
                                and getattr(svc_info, "source", None) == self._preferred_adapter
                            ):
                                _LOGGER.debug(
                                    "ble_device_callback returning device from %s (RSSI: %s)",
                                    self._preferred_adapter,
                                    getattr(svc_info, "rssi", "N/A"),
                                )
                                return svc_info.device
                        # Fall back to any source if preferred not available
                        _LOGGER.debug(
                            "Preferred adapter %s not available, falling back",
                            self._preferred_adapter,
                        )
                        fallback = bluetooth.async_ble_device_from_address(
                            self.hass, self._address, connectable=True
                        )
                        if fallback is None:
                            raise BleakError(f"Device {self._address} not found")
                        return fallback

                    ble_device_callback = _get_device_from_preferred_adapter

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

                connect_elapsed = time.monotonic() - connect_start
                total_elapsed = time.monotonic() - attempt_start
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
                await discover_services(self._client, self._address)

                # Validate expected services are present (for beds requiring pairing)
                if bed_requires_pairing and self._client.services:
                    discovered_uuids = {
                        svc.uuid.lower() for svc in self._client.services
                    }
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

                # Create the controller
                _LOGGER.debug("Creating %s controller...", self._bed_type)
                self._controller = await create_controller(
                    coordinator=self,
                    bed_type=self._bed_type,
                    protocol_variant=self._protocol_variant,
                    client=self._client,
                    octo_pin=self._octo_pin,
                    richmat_remote=self._richmat_remote,
                    jensen_pin=self._jensen_pin,
                )
                _LOGGER.debug("Controller created successfully")

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

                # Store connection metadata for binary sensor
                self._last_connected = datetime.now(UTC)
                self._connection_source = actual_adapter
                self._connection_rssi = adapter_result.rssi
                self._notify_connection_state_change(True)

                return True

            except (BleakError, TimeoutError, OSError) as err:
                attempt_elapsed = time.monotonic() - attempt_start
                # Categorize the error for clearer diagnostics
                if isinstance(err, TimeoutError) or "timeout" in str(err).lower():
                    error_category = "CONNECTION TIMEOUT"
                elif "refused" in str(err).lower() or "rejected" in str(err).lower():
                    error_category = "CONNECTION REFUSED (another device may be connected)"
                else:
                    error_category = "BLE ERROR"
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
                # Delay is handled at the start of the next iteration with progressive backoff
            except Exception as err:
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
        """
        if self._disable_angle_sensing:
            _LOGGER.debug("Skipping initial position read (angle sensing disabled)")
            return

        _LOGGER.debug("Reading initial positions for %s", self._address)
        try:
            async with asyncio.timeout(5.0):
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

    async def async_disconnect(self) -> None:
        """Disconnect from the bed."""
        _LOGGER.debug("async_disconnect called for %s", self._address)
        async with self._lock:
            self._cancel_disconnect_timer()
            # Cancel any pending reconnect timer
            if self._reconnect_timer is not None:
                self._reconnect_timer.cancel()
                self._reconnect_timer = None
            if self._client is not None:
                _LOGGER.info("Disconnecting from bed at %s", self._address)
                # Mark as intentional so _on_disconnect doesn't trigger auto-reconnect
                self._intentional_disconnect = True
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
        await self.async_disconnect()

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

                # Start position polling during movement if angle sensing enabled
                poll_stop: asyncio.Event | None = None
                poll_task: asyncio.Task[None] | None = None
                if not self._disable_angle_sensing:
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
        entry_cancel_count = self._cancel_counter

        # Acquire the command lock to wait for any in-flight GATT write to complete
        # This prevents concurrent BLE writes which cause "operation in progress" errors
        async with self._command_lock:
            # Check if we were cancelled while waiting (unlikely for stop, but possible)
            if self._cancel_counter > entry_cancel_count:
                _LOGGER.debug("Stop command cancelled while waiting for lock")
                return

            # Cancel disconnect timer while command is in progress
            self._cancel_disconnect_timer()
            try:
                if not await self.async_ensure_connected(reset_timer=False):
                    _LOGGER.error("Cannot send stop: not connected to bed")
                    return

                if self._controller is None:
                    _LOGGER.error("Cannot send stop: no controller available")
                    return

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

    async def async_execute_controller_command(
        self,
        command_fn: Callable[[BedController], Coroutine[Any, Any, None]],
        cancel_running: bool = True,
        skip_disconnect: bool = False,
    ) -> None:
        """Execute a controller command with proper serialization.

        This ensures commands are serialized through the command lock,
        optionally cancels any running command, and properly resets the disconnect timer.

        Args:
            command_fn: An async callable that takes the controller as argument.
            cancel_running: If True, cancel any running command before executing.
            skip_disconnect: If True, skip the disconnect_after_command behavior.
                Use this for keep-alive commands that need the connection to persist.
        """
        if cancel_running:
            # Cancel any running command immediately
            self._cancel_counter += 1
            self._cancel_command.set()

        # Capture cancel count at entry
        entry_cancel_count = self._cancel_counter

        async with self._command_lock:
            # Cancel disconnect timer while command is in progress to prevent mid-command disconnect
            self._cancel_disconnect_timer()

            # Check if we were cancelled while waiting for the lock
            if self._cancel_counter > entry_cancel_count:
                _LOGGER.debug("Controller command cancelled while waiting for lock")
                # Handle disconnect timer since we're bailing out without executing
                if self._client is not None and self._client.is_connected:
                    if self._disconnect_after_command and not skip_disconnect:
                        # Configured to disconnect after commands and not a keep-alive command -
                        # disconnect now since no command was executed (avoids leaving connection open)
                        _LOGGER.debug("Disconnecting after cancelled command (disconnect_after_command=True)")
                        await self.async_disconnect()
                    else:
                        # Not configured for immediate disconnect or skip_disconnect is True
                        # (e.g., keep-alive commands) - reset idle timer instead
                        self._reset_disconnect_timer()
                return

            try:
                # Clear cancel signal for this command
                self._cancel_command.clear()

                if not await self.async_ensure_connected(reset_timer=False):
                    _LOGGER.error("Cannot execute command: not connected to bed")
                    raise ConnectionError("Not connected to bed")

                if self._controller is None:
                    _LOGGER.error("Cannot execute command: no controller available")
                    raise RuntimeError("No controller available")

                # Start position polling during movement if angle sensing enabled
                poll_stop: asyncio.Event | None = None
                poll_task: asyncio.Task[None] | None = None
                if not self._disable_angle_sensing:
                    poll_stop = asyncio.Event()
                    poll_task = asyncio.create_task(
                        self._async_poll_positions_during_movement(poll_stop)
                    )

                try:
                    await command_fn(self._controller)
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
            except (ConnectionError, RuntimeError):
                # On connection/controller errors, reset timer if not disconnecting after commands
                if (
                    self._client is not None
                    and self._client.is_connected
                    and not self._disconnect_after_command
                ):
                    self._reset_disconnect_timer()
                raise
            finally:
                if self._client is not None and self._client.is_connected:
                    # Disconnect immediately if configured to do so (unless skip_disconnect)
                    if self._disconnect_after_command and not skip_disconnect:
                        _LOGGER.debug(
                            "Disconnecting after command (disconnect_after_command=True) for %s",
                            self._address,
                        )
                        await self.async_disconnect()
                    else:
                        # Otherwise, reset the idle disconnect timer
                        self._reset_disconnect_timer()

    async def async_start_notify(self) -> None:
        """Start listening for position notifications."""
        if self._controller is None:
            _LOGGER.warning("Cannot start notifications: no controller available")
            return

        # Jensen beds ALWAYS need start_notify() called, even with angle sensing disabled,
        # because it sends the PIN unlock command required before any other commands work.
        # The Jensen app sequence: enable notifications → PIN unlock → config query → commands
        if self._bed_type == BED_TYPE_JENSEN:
            if self._disable_angle_sensing:
                _LOGGER.info(
                    "Starting notifications for Jensen bed %s (PIN unlock only; angle sensing disabled)",
                    self._address,
                )
                await self._controller.start_notify(None)
            else:
                _LOGGER.info(
                    "Starting notifications for Jensen bed %s (required for PIN unlock)",
                    self._address,
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

                # Get current position, attempting a read if not available
                # This must be done INSIDE the lock after ensuring connection
                current_angle = self._position_data.get(position_key)
                if current_angle is None:
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
                if abs(current_angle - target_angle) <= POSITION_TOLERANCE:
                    _LOGGER.debug(
                        "Position %s already at target: %.1f (target: %.1f)",
                        position_key,
                        current_angle,
                        target_angle,
                    )
                    return  # finally block handles disconnect

                _LOGGER.info(
                    "Seeking position %s from %.1f to %.1f",
                    position_key,
                    current_angle,
                    target_angle,
                )

                # Check if controller supports direct position control (e.g., Reverie)
                # This bypasses the incremental seek loop for beds that can set positions directly
                if self._controller.supports_direct_position_control:
                    native_position = self._controller.angle_to_native_position(
                        position_key, target_angle
                    )
                    _LOGGER.debug(
                        "Using direct position control: %s -> %d",
                        position_key,
                        native_position,
                    )
                    await self._controller.set_motor_position(position_key, native_position)
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
                        # Overshoot reversal is a safety correction - clear cancel event
                        # to ensure reversal completes even if user cancelled
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
