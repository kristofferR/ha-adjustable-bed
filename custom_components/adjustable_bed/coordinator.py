"""Coordinator for Adjustable Bed integration."""

from __future__ import annotations

import asyncio
import logging
import time
import traceback
from typing import TYPE_CHECKING, Any, Callable, Coroutine

from bleak import BleakClient
from bleak.exc import BleakError
from bleak_retry_connector import establish_connection
from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo

from .const import (
    ADAPTER_AUTO,
    BED_MOTOR_PULSE_DEFAULTS,
    BED_TYPE_DEWERTOKIN,
    BED_TYPE_ERGOMOTION,
    BED_TYPE_JIECANG,
    BED_TYPE_KEESON,
    BED_TYPE_LEGGETT_PLATT,
    BED_TYPE_LINAK,
    BED_TYPE_MATTRESSFIRM,
    BED_TYPE_MOTOSLEEP,
    BED_TYPE_OCTO,
    BED_TYPE_OKIMAT,
    BED_TYPE_REVERIE,
    BED_TYPE_RICHMAT,
    BED_TYPE_SERTA,
    BED_TYPE_SOLACE,
    CONF_BED_TYPE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_DISCONNECT_AFTER_COMMAND,
    CONF_HAS_MASSAGE,
    CONF_IDLE_DISCONNECT_SECONDS,
    CONF_MOTOR_COUNT,
    CONF_MOTOR_PULSE_COUNT,
    CONF_MOTOR_PULSE_DELAY_MS,
    CONF_OCTO_PIN,
    CONF_POSITION_MODE,
    CONF_PREFERRED_ADAPTER,
    CONF_PROTOCOL_VARIANT,
    DEFAULT_DISABLE_ANGLE_SENSING,
    DEFAULT_DISCONNECT_AFTER_COMMAND,
    DEFAULT_HAS_MASSAGE,
    DEFAULT_IDLE_DISCONNECT_SECONDS,
    DEFAULT_MOTOR_COUNT,
    DEFAULT_MOTOR_PULSE_COUNT,
    DEFAULT_MOTOR_PULSE_DELAY_MS,
    DEFAULT_OCTO_PIN,
    DEFAULT_POSITION_MODE,
    DEFAULT_PROTOCOL_VARIANT,
    POSITION_MODE_ACCURACY,
    DOMAIN,
    KEESON_VARIANT_BASE,
    KEESON_VARIANT_ERGOMOTION,
    KEESON_VARIANT_KSBT,
    LEGGETT_VARIANT_GEN2,
    LEGGETT_VARIANT_OKIN,
    RICHMAT_VARIANT_NORDIC,
    RICHMAT_VARIANT_WILINKE,
)

if TYPE_CHECKING:
    from .beds.base import BedController

_LOGGER = logging.getLogger(__name__)

# Retry settings
MAX_RETRIES = 3
RETRY_DELAY = 5.0  # Increased delay between retries for BLE stability
CONNECTION_TIMEOUT = 30.0  # Timeout for BLE connection attempts
POST_CONNECT_DELAY = 1.0  # Delay after connection to let it stabilize


class AdjustableBedCoordinator:
    """Coordinator for managing bed connection and state."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the coordinator."""
        self.hass = hass
        self.entry = entry
        self._address: str = entry.data[CONF_ADDRESS].upper()
        self._bed_type: str = entry.data[CONF_BED_TYPE]
        self._protocol_variant: str = entry.data.get(CONF_PROTOCOL_VARIANT, DEFAULT_PROTOCOL_VARIANT)
        self._name: str = entry.data.get(CONF_NAME, "Adjustable Bed")
        self._motor_count: int = entry.data.get(CONF_MOTOR_COUNT, DEFAULT_MOTOR_COUNT)
        self._has_massage: bool = entry.data.get(CONF_HAS_MASSAGE, DEFAULT_HAS_MASSAGE)
        self._disable_angle_sensing: bool = entry.data.get(CONF_DISABLE_ANGLE_SENSING, DEFAULT_DISABLE_ANGLE_SENSING)
        self._position_mode: str = entry.data.get(CONF_POSITION_MODE, DEFAULT_POSITION_MODE)
        self._preferred_adapter: str = entry.data.get(CONF_PREFERRED_ADAPTER, ADAPTER_AUTO)

        # Get bed-type-specific motor pulse defaults, falling back to global defaults
        bed_pulse_defaults = BED_MOTOR_PULSE_DEFAULTS.get(
            self._bed_type, (DEFAULT_MOTOR_PULSE_COUNT, DEFAULT_MOTOR_PULSE_DELAY_MS)
        )
        self._motor_pulse_count: int = entry.data.get(CONF_MOTOR_PULSE_COUNT, bed_pulse_defaults[0])
        self._motor_pulse_delay_ms: int = entry.data.get(CONF_MOTOR_PULSE_DELAY_MS, bed_pulse_defaults[1])

        # Disconnect behavior configuration
        self._disconnect_after_command: bool = entry.data.get(CONF_DISCONNECT_AFTER_COMMAND, DEFAULT_DISCONNECT_AFTER_COMMAND)
        self._idle_disconnect_seconds: int = entry.data.get(CONF_IDLE_DISCONNECT_SECONDS, DEFAULT_IDLE_DISCONNECT_SECONDS)

        # Octo-specific configuration
        self._octo_pin: str = entry.data.get(CONF_OCTO_PIN, DEFAULT_OCTO_PIN)

        self._client: BleakClient | None = None
        self._controller: BedController | None = None
        self._disconnect_timer: asyncio.TimerHandle | None = None
        self._reconnect_timer: asyncio.TimerHandle | None = None
        self._lock = asyncio.Lock()
        self._command_lock = asyncio.Lock()  # Separate lock for command serialization
        self._connecting: bool = False  # Track if we're actively connecting
        self._intentional_disconnect: bool = False  # Track intentional disconnects to skip auto-reconnect
        self._cancel_command = asyncio.Event()  # Signal to cancel current command

        # Position data from notifications
        self._position_data: dict[str, float] = {}
        self._position_callbacks: set[Callable[[dict[str, float]], None]] = set()

        _LOGGER.debug(
            "Coordinator initialized for %s at %s (type: %s, motors: %d, massage: %s, disable_angle_sensing: %s, adapter: %s)",
            self._name,
            self._address,
            self._bed_type,
            self._motor_count,
            self._has_massage,
            self._disable_angle_sensing,
            self._preferred_adapter,
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
        manufacturers = {
            BED_TYPE_LINAK: "Linak",
            BED_TYPE_RICHMAT: "Richmat",
            BED_TYPE_KEESON: "Keeson",
            BED_TYPE_SOLACE: "Solace",
            BED_TYPE_MOTOSLEEP: "MotoSleep",
            BED_TYPE_LEGGETT_PLATT: "Leggett & Platt",
            BED_TYPE_REVERIE: "Reverie",
            BED_TYPE_OKIMAT: "Okimat",
            BED_TYPE_ERGOMOTION: "Ergomotion",
            BED_TYPE_JIECANG: "Jiecang",
            BED_TYPE_DEWERTOKIN: "DewertOkin",
            BED_TYPE_SERTA: "Serta",
            BED_TYPE_OCTO: "Octo",
            BED_TYPE_MATTRESSFIRM: "MattressFirm",
        }
        return manufacturers.get(self._bed_type, "Unknown")

    def _get_model(self) -> str:
        """Get model name based on bed type."""
        return f"Adjustable Bed ({self._motor_count} motors)"

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

        _LOGGER.info("Initiating BLE connection to %s (max %d attempts)", self._address, MAX_RETRIES)
        overall_start = time.monotonic()

        for attempt in range(MAX_RETRIES):
            attempt_start = time.monotonic()
            # On retries, add a delay before attempting to give the Bluetooth stack time to reset
            if attempt > 0:
                pre_retry_delay = RETRY_DELAY * (1 + attempt * 0.5)  # Progressive backoff
                _LOGGER.info(
                    "Waiting %.1fs before connection retry %d/%d to %s...",
                    pre_retry_delay,
                    attempt + 1,
                    MAX_RETRIES,
                    self._address,
                )
                await asyncio.sleep(pre_retry_delay)
            
            try:
                _LOGGER.debug(
                    "Connection attempt %d/%d: Looking up device %s via HA Bluetooth (preferred adapter: %s)",
                    attempt + 1,
                    MAX_RETRIES,
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
                
                # Try to get device info, optionally filtered by preferred adapter
                device = None
                if self._preferred_adapter and self._preferred_adapter != ADAPTER_AUTO:
                    # Look for device from specific adapter/source
                    _LOGGER.info(
                        "Looking for device %s from preferred adapter: %s",
                        self._address,
                        self._preferred_adapter,
                    )
                    
                    # Log all sources that can see this device
                    available_sources = []
                    try:
                        for service_info in bluetooth.async_discovered_service_info(self.hass, connectable=True):
                            if service_info.address.upper() == self._address:
                                source = getattr(service_info, 'source', 'unknown')
                                rssi = getattr(service_info, 'rssi', 'N/A')
                                available_sources.append(f"{source} (RSSI: {rssi})")
                                
                                if source == self._preferred_adapter:
                                    device = service_info.device
                                    _LOGGER.info(
                                        "✓ Found device %s via preferred adapter %s (RSSI: %s)",
                                        self._address,
                                        self._preferred_adapter,
                                        rssi,
                                    )
                        
                        if available_sources:
                            _LOGGER.info(
                                "Adapters that can see device %s: %s",
                                self._address,
                                ", ".join(available_sources),
                            )
                        
                        if device is None and available_sources:
                            _LOGGER.warning(
                                "⚠ Device %s not found via preferred adapter %s, falling back to automatic selection",
                                self._address,
                                self._preferred_adapter,
                            )
                    except Exception as err:
                        _LOGGER.debug("Error looking up device from specific adapter: %s", err)
                
                # Fall back to auto selection if no preferred adapter or device not found
                # Auto mode: pick the adapter with the best RSSI (strongest signal)
                if device is None:
                    best_rssi = -999
                    best_source = None
                    try:
                        discovered = bluetooth.async_discovered_service_info(self.hass, connectable=True)
                        for svc_info in discovered:
                            if svc_info.address.upper() == self._address.upper():
                                rssi = getattr(svc_info, 'rssi', -999)
                                source = getattr(svc_info, 'source', 'unknown')
                                _LOGGER.debug(
                                    "Auto-select candidate: source=%s, rssi=%d",
                                    source, rssi
                                )
                                if rssi > best_rssi:
                                    best_rssi = rssi
                                    best_source = source
                    except Exception as err:
                        _LOGGER.debug("Error during auto adapter selection: %s", err)

                    if best_source:
                        _LOGGER.info(
                            "Auto-selected adapter %s with best RSSI %d",
                            best_source, best_rssi
                        )
                        # Get device from the best adapter
                        try:
                            for svc_info in bluetooth.async_discovered_service_info(self.hass, connectable=True):
                                if (svc_info.address.upper() == self._address.upper() and
                                    getattr(svc_info, 'source', None) == best_source):
                                    device = svc_info.device
                                    break
                        except Exception:
                            pass

                    # Final fallback to default lookup
                    if device is None:
                        device = bluetooth.async_ble_device_from_address(
                            self.hass, self._address, connectable=True
                        )
                        if device:
                            fallback_source = "unknown"
                            if hasattr(device, 'details') and isinstance(device.details, dict):
                                fallback_source = device.details.get('source', 'unknown')
                            _LOGGER.info(
                                "Using fallback adapter selection, device found via: %s",
                                fallback_source,
                            )
                if device is None:
                    lookup_elapsed = time.monotonic() - attempt_start
                    _LOGGER.warning(
                        "Device %s NOT FOUND in Bluetooth scanner after %.1fs (attempt %d/%d). "
                        "Bed may be powered off, out of range, or connected to another device.",
                        self._address,
                        lookup_elapsed,
                        attempt + 1,
                        MAX_RETRIES,
                    )
                    # Log what devices ARE visible
                    try:
                        discovered = bluetooth.async_discovered_service_info(self.hass, connectable=True)
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
                                    getattr(svc_info, 'rssi', 'N/A'),
                                    getattr(svc_info, 'source', 'N/A'),
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
                if hasattr(device, 'details') and isinstance(device.details, dict):
                    device_source = device.details.get('source')
                
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
                    getattr(device, 'details', 'N/A'),
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
                
                # Try to get service info for more details about the source (proxy info)
                try:
                    service_info = bluetooth.async_last_service_info(
                        self.hass, self._address, connectable=True
                    )
                    if service_info:
                        _LOGGER.debug(
                            "Service info: source=%s, rssi=%s, connectable=%s, service_uuids=%s",
                            getattr(service_info, 'source', 'N/A'),
                            getattr(service_info, 'rssi', 'N/A'),
                            getattr(service_info, 'connectable', 'N/A'),
                            getattr(service_info, 'service_uuids', []),
                        )
                        # Log if this is from an ESPHome proxy
                        source = getattr(service_info, 'source', '')
                        if source and 'esphome' in source.lower():
                            _LOGGER.info(
                                "Device discovered via ESPHome Bluetooth proxy: %s",
                                source,
                            )
                except Exception as err:
                    _LOGGER.debug("Could not get detailed service info: %s", err)

                # Use bleak-retry-connector for reliable connection establishment
                # This handles ESPHome Bluetooth proxy connections properly
                # Using standard BleakClient (not cached) for better compatibility
                # with devices that have connection stability issues
                connect_start = time.monotonic()
                _LOGGER.info(
                    "Attempting BLE GATT connection to %s (timeout: %.0fs)...",
                    self._address,
                    CONNECTION_TIMEOUT,
                )
                
                # Create a callback to get fresh device from preferred adapter on retries
                ble_device_callback = None
                if self._preferred_adapter and self._preferred_adapter != ADAPTER_AUTO:
                    def _get_device_from_preferred_adapter():
                        """Get a fresh BLEDevice from the preferred adapter."""
                        for svc_info in bluetooth.async_discovered_service_info(self.hass, connectable=True):
                            if (svc_info.address.upper() == self._address and
                                getattr(svc_info, 'source', None) == self._preferred_adapter):
                                _LOGGER.debug(
                                    "ble_device_callback returning device from %s (RSSI: %s)",
                                    self._preferred_adapter,
                                    getattr(svc_info, 'rssi', 'N/A'),
                                )
                                return svc_info.device
                        # Fall back to any source if preferred not available
                        _LOGGER.debug(
                            "Preferred adapter %s not available, falling back",
                            self._preferred_adapter,
                        )
                        return bluetooth.async_ble_device_from_address(
                            self.hass, self._address, connectable=True
                        )
                    ble_device_callback = _get_device_from_preferred_adapter
                
                # Mark that we're connecting to suppress spurious disconnect warnings
                # during bleak's internal retry process
                self._connecting = True
                try:
                    # Use max_attempts=1 here since outer loop handles retries
                    self._client = await establish_connection(
                        BleakClient,
                        device,
                        self._name,
                        disconnected_callback=self._on_disconnect,
                        max_attempts=1,
                        timeout=CONNECTION_TIMEOUT,
                        ble_device_callback=ble_device_callback,
                    )
                finally:
                    self._connecting = False

                # Determine which adapter was actually used for connection
                actual_adapter = "unknown"
                try:
                    # Try to get the actual connection source from the client
                    if hasattr(self._client, '_backend') and hasattr(self._client._backend, '_device'):
                        backend_device = self._client._backend._device
                        if hasattr(backend_device, 'details') and isinstance(backend_device.details, dict):
                            actual_adapter = backend_device.details.get('source', 'unknown')
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
                await asyncio.sleep(POST_CONNECT_DELAY)

                # Log connection details
                _LOGGER.debug(
                    "BleakClient connected: is_connected=%s, mtu_size=%s",
                    self._client.is_connected,
                    getattr(self._client, 'mtu_size', 'N/A'),
                )

                # Services are auto-discovered by HA's BleakClientWrapper during connection
                # Just log what we have - no need to explicitly call get_services()
                _LOGGER.debug("Checking discovered BLE services...")

                # Log discovered services in detail
                if self._client.services:
                    services_list = list(self._client.services)
                    _LOGGER.debug(
                        "Discovered %d BLE services on %s:",
                        len(services_list),
                        self._address,
                    )
                    for service in self._client.services:
                        _LOGGER.debug(
                            "  Service: %s (handle: %s)",
                            service.uuid,
                            getattr(service, 'handle', 'N/A'),
                        )
                        for char in service.characteristics:
                            props = ", ".join(char.properties)
                            _LOGGER.debug(
                                "    Characteristic: %s [%s] (handle: %s)",
                                char.uuid,
                                props,
                                getattr(char, 'handle', 'N/A'),
                            )
                            for desc in char.descriptors:
                                _LOGGER.debug(
                                    "      Descriptor: %s (handle: %s)",
                                    desc.uuid,
                                    getattr(desc, 'handle', 'N/A'),
                                )
                else:
                    _LOGGER.warning(
                        "No BLE services discovered on %s - this may indicate a connection issue",
                        self._address,
                    )

                # Create the controller
                _LOGGER.debug("Creating %s controller...", self._bed_type)
                self._controller = await self._async_create_controller()
                _LOGGER.debug("Controller created successfully")

                if reset_timer:
                    self._reset_disconnect_timer()

                # Start position notifications (no-op if angle sensing disabled)
                await self.async_start_notify()

                # For Octo beds: discover features and handle PIN if needed
                if self._bed_type == BED_TYPE_OCTO:
                    # Discover features to detect PIN requirement
                    if hasattr(self._controller, 'discover_features'):
                        await self._controller.discover_features()
                    # Send initial PIN and start keep-alive if bed requires it
                    if hasattr(self._controller, 'send_pin'):
                        await self._controller.send_pin()
                        await self._controller.start_keepalive()

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
                    MAX_RETRIES,
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
                    MAX_RETRIES,
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
            MAX_RETRIES,
            total_elapsed,
        )
        return False

    def _on_disconnect(self, client: BleakClient) -> None:
        """Handle disconnection callback."""
        # If we're in the middle of connecting, this is likely bleak's internal retry
        # for le-connection-abort-by-local - don't log warnings or clear references
        if self._connecting:
            _LOGGER.debug(
                "Disconnect callback during connection establishment for %s (bleak internal retry)",
                self._address,
            )
            return

        # Stop keepalive task before clearing controller to prevent task leak
        # Capture controller reference before clearing to avoid race condition
        controller = self._controller
        if controller is not None and hasattr(controller, 'stop_keepalive'):
            asyncio.create_task(controller.stop_keepalive())

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
            return

        _LOGGER.warning(
            "Unexpectedly disconnected from %s. Client details: is_connected=%s, address=%s",
            self._address,
            getattr(client, 'is_connected', 'N/A'),
            getattr(client, 'address', 'N/A'),
        )
        _LOGGER.debug(
            "Disconnect callback triggered - clearing client and controller references for %s",
            self._address,
        )
        self._client = None
        self._controller = None
        # Keep _position_data for last known state; entity availability handles offline
        self._cancel_disconnect_timer()
        _LOGGER.debug("Disconnect cleanup complete for %s", self._address)

        # Schedule automatic reconnection attempt
        # Cancel any existing reconnect timer first to prevent multiple concurrent reconnects
        if self._reconnect_timer is not None:
            self._reconnect_timer.cancel()
        self._reconnect_timer = self.hass.loop.call_later(
            5.0,  # Wait 5 seconds before attempting reconnect
            lambda: asyncio.create_task(self._async_auto_reconnect()),
        )

    async def _async_create_controller(self) -> BedController:
        """Create the appropriate bed controller."""
        if self._bed_type == BED_TYPE_LINAK:
            from .beds.linak import LinakController

            return LinakController(self)

        if self._bed_type == BED_TYPE_RICHMAT:
            from .beds.richmat import RichmatController, detect_richmat_variant

            # Use configured variant or auto-detect
            if self._protocol_variant == RICHMAT_VARIANT_NORDIC:
                _LOGGER.debug("Using Nordic Richmat variant (configured)")
                return RichmatController(self, is_wilinke=False)
            elif self._protocol_variant == RICHMAT_VARIANT_WILINKE:
                _LOGGER.debug("Using WiLinke Richmat variant (configured)")
                return RichmatController(self, is_wilinke=True)
            else:
                # Auto-detect variant based on available services
                _LOGGER.debug("Auto-detecting Richmat variant...")
                is_wilinke, char_uuid = await detect_richmat_variant(self._client)
                return RichmatController(
                    self,
                    is_wilinke=is_wilinke,
                    char_uuid=char_uuid,
                )

        if self._bed_type == BED_TYPE_KEESON:
            from .beds.keeson import KeesonController

            # Use configured variant or default to base
            if self._protocol_variant == KEESON_VARIANT_KSBT:
                _LOGGER.debug("Using KSBT Keeson variant (configured)")
                return KeesonController(self, variant="ksbt")
            elif self._protocol_variant == KEESON_VARIANT_ERGOMOTION:
                _LOGGER.debug("Using Ergomotion Keeson variant (with position feedback)")
                return KeesonController(self, variant="ergomotion")
            else:
                # Auto or base variant
                _LOGGER.debug("Using Base Keeson variant")
                return KeesonController(self, variant="base")

        if self._bed_type == BED_TYPE_SOLACE:
            from .beds.solace import SolaceController

            return SolaceController(self)

        if self._bed_type == BED_TYPE_MOTOSLEEP:
            from .beds.motosleep import MotoSleepController

            return MotoSleepController(self)

        if self._bed_type == BED_TYPE_LEGGETT_PLATT:
            from .beds.leggett_platt import LeggettPlattController

            # Use configured variant or default to gen2
            if self._protocol_variant == LEGGETT_VARIANT_OKIN:
                _LOGGER.debug("Using Okin Leggett & Platt variant (configured)")
                return LeggettPlattController(self, variant="okin")
            else:
                # Auto or gen2 variant
                _LOGGER.debug("Using Gen2 Leggett & Platt variant")
                return LeggettPlattController(self, variant="gen2")

        if self._bed_type == BED_TYPE_REVERIE:
            from .beds.reverie import ReverieController

            return ReverieController(self)

        if self._bed_type == BED_TYPE_OKIMAT:
            from .beds.okimat import OkimatController

            return OkimatController(self)

        if self._bed_type == BED_TYPE_ERGOMOTION:
            # Ergomotion uses the same protocol as Keeson with position feedback
            from .beds.keeson import KeesonController

            return KeesonController(self, variant="ergomotion")

        if self._bed_type == BED_TYPE_JIECANG:
            from .beds.jiecang import JiecangController

            return JiecangController(self)

        if self._bed_type == BED_TYPE_DEWERTOKIN:
            from .beds.dewertokin import DewertOkinController

            return DewertOkinController(self)

        if self._bed_type == BED_TYPE_SERTA:
            from .beds.serta import SertaController

            return SertaController(self)

        if self._bed_type == BED_TYPE_OCTO:
            from .beds.octo import OctoController

            return OctoController(self, pin=self._octo_pin)

        if self._bed_type == BED_TYPE_MATTRESSFIRM:
            from .beds.mattressfirm import MattressFirmController

            return MattressFirmController(self)

        raise ValueError(f"Unknown bed type: {self._bed_type}")

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
            _LOGGER.debug("Initial position read failed: %s - sensors will update on first command", err)

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
                        if hasattr(self._controller, 'stop_keepalive'):
                            try:
                                await self._controller.stop_keepalive()
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
            self._cancel_command.set()

        async with self._command_lock:
            # Cancel disconnect timer while command is in progress to prevent mid-command disconnect
            self._cancel_disconnect_timer()

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
                        try:
                            await poll_task
                        except asyncio.CancelledError:
                            pass

                # Final position read after command
                if not self._disable_angle_sensing and not self._cancel_command.is_set():
                    if self._position_mode == POSITION_MODE_ACCURACY:
                        # Accuracy mode: wait for read to complete
                        await self._async_read_positions()
                    else:
                        # Speed mode: fire-and-forget (no blocking)
                        self.hass.async_create_task(self._async_read_positions())
            finally:
                if self._client is not None and self._client.is_connected:
                    self._reset_disconnect_timer()

    async def async_stop_command(self) -> None:
        """Immediately stop any running command and send stop to bed."""
        _LOGGER.info("Stop requested - cancelling current command")

        # Signal cancellation to any running command
        self._cancel_command.set()

        # Acquire the command lock to wait for any in-flight GATT write to complete
        # This prevents concurrent BLE writes which cause "operation in progress" errors
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
        command_fn: Callable[["BedController"], Coroutine[Any, Any, None]],
        cancel_running: bool = True,
    ) -> None:
        """Execute a controller command with proper serialization.

        This ensures commands are serialized through the command lock,
        optionally cancels any running command, and properly resets the disconnect timer.

        Args:
            command_fn: An async callable that takes the controller as argument.
        """
        if cancel_running:
            # Cancel any running command immediately
            self._cancel_command.set()

        async with self._command_lock:
            # Cancel disconnect timer while command is in progress to prevent mid-command disconnect
            self._cancel_disconnect_timer()

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
                        try:
                            await poll_task
                        except asyncio.CancelledError:
                            pass

                # Final position read after command
                if not self._disable_angle_sensing and not self._cancel_command.is_set():
                    if self._position_mode == POSITION_MODE_ACCURACY:
                        # Accuracy mode: wait for read to complete
                        await self._async_read_positions()
                    else:
                        # Speed mode: fire-and-forget (no blocking)
                        self.hass.async_create_task(self._async_read_positions())
            except (ConnectionError, RuntimeError):
                # On connection/controller errors, reset timer if not disconnecting after commands
                if self._client is not None and self._client.is_connected and not self._disconnect_after_command:
                    self._reset_disconnect_timer()
                raise
            finally:
                if self._client is not None and self._client.is_connected:
                    # Disconnect immediately if configured to do so
                    if self._disconnect_after_command:
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
        if self._disable_angle_sensing:
            _LOGGER.info(
                "Angle sensing disabled for %s - skipping position notifications (physical remote will remain functional)",
                self._address,
            )
            return

        if self._controller is None:
            _LOGGER.warning("Cannot start notifications: no controller available")
            return

        _LOGGER.info("Starting position notifications for %s", self._address)
        await self._controller.start_notify(self._handle_position_update)

    async def _async_read_positions(self) -> None:
        """Actively read current positions from the bed.

        Called after movement commands to ensure position data is up to date.
        Uses a short timeout to avoid blocking commands.
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

    async def _async_poll_positions_during_movement(
        self, stop_event: asyncio.Event
    ) -> None:
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

        def unregister() -> None:
            self._position_callbacks.discard(callback_fn)  # Safe removal, no error if missing

        return unregister
