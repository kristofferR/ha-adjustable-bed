"""Bluetooth adapter selection and BLE helper functions."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from bleak import BleakClient
from bleak.backends.device import BLEDevice
from bleak.exc import BleakError
from homeassistant.components import bluetooth
from homeassistant.core import HomeAssistant

from .const import ADAPTER_AUTO, DEVICE_INFO_CHARS, DEVICE_INFO_SERVICE_UUID

# Sentinel value indicating RSSI is unavailable
RSSI_UNAVAILABLE = -999

_LOGGER = logging.getLogger(__name__)


@dataclass
class AdapterSelectionResult:
    """Result from adapter selection process."""

    device: BLEDevice | None
    source: str | None
    rssi: int | None
    available_sources: list[str]


async def select_adapter(
    hass: HomeAssistant,
    address: str,
    preferred_adapter: str | None,
) -> AdapterSelectionResult:
    """Select the best Bluetooth adapter for connection.

    This function handles adapter discovery and selection logic:
    - If a preferred adapter is configured, looks for device from that adapter
    - Otherwise, selects the adapter with the best RSSI (strongest signal)
    - Falls back to default Home Assistant lookup if needed

    Args:
        hass: Home Assistant instance
        address: The BLE device address to find
        preferred_adapter: Preferred adapter source, or None/ADAPTER_AUTO for automatic

    Returns:
        AdapterSelectionResult with device, source, rssi, and available sources
    """
    device: BLEDevice | None = None
    source: str | None = None
    rssi: int | None = None
    available_sources: list[str] = []

    if preferred_adapter and preferred_adapter != ADAPTER_AUTO:
        # Look for device from specific adapter/source
        _LOGGER.info(
            "Looking for device %s from preferred adapter: %s",
            address,
            preferred_adapter,
        )

        # Log all sources that can see this device
        try:
            for service_info in bluetooth.async_discovered_service_info(hass, connectable=True):
                if service_info.address.upper() == address.upper():
                    svc_source = getattr(service_info, 'source', 'unknown')
                    svc_rssi = getattr(service_info, 'rssi', 'N/A')
                    available_sources.append(f"{svc_source} (RSSI: {svc_rssi})")

                    if svc_source == preferred_adapter:
                        device = service_info.device
                        source = svc_source
                        rssi = svc_rssi if isinstance(svc_rssi, int) else None
                        _LOGGER.info(
                            "✓ Found device %s via preferred adapter %s (RSSI: %s)",
                            address,
                            preferred_adapter,
                            svc_rssi,
                        )
                        break

            if available_sources:
                _LOGGER.info(
                    "Adapters that can see device %s: %s",
                    address,
                    ", ".join(available_sources),
                )

            if device is None and available_sources:
                _LOGGER.warning(
                    "⚠ Device %s not found via preferred adapter %s, falling back to automatic selection",
                    address,
                    preferred_adapter,
                )
        except Exception as err:
            _LOGGER.debug("Error looking up device from specific adapter: %s", err)

    # Fall back to auto selection if no preferred adapter or device not found
    # Auto mode: pick the adapter with the best RSSI (strongest signal)
    if device is None:
        best_rssi = RSSI_UNAVAILABLE
        best_source: str | None = None
        # Capture discovery snapshot once and reuse for both RSSI selection and device lookup
        try:
            discovered_services = list(bluetooth.async_discovered_service_info(hass, connectable=True))
        except (OSError, TimeoutError) as err:
            _LOGGER.debug("Error during auto adapter selection: %s", err)
            discovered_services = []

        # Find the adapter with best RSSI
        for svc_info in discovered_services:
            if svc_info.address.upper() == address.upper():
                svc_rssi = getattr(svc_info, 'rssi', None)
                # Safely coerce RSSI to int, handling None/malformed values
                try:
                    rssi_value = int(svc_rssi) if svc_rssi is not None else RSSI_UNAVAILABLE
                except (ValueError, TypeError):
                    rssi_value = RSSI_UNAVAILABLE
                svc_source = getattr(svc_info, 'source', 'unknown')
                _LOGGER.debug(
                    "Auto-select candidate: source=%s, rssi=%s",
                    svc_source, rssi_value
                )
                if rssi_value > best_rssi:
                    best_rssi = rssi_value
                    best_source = svc_source

        if best_source:
            _LOGGER.info(
                "Auto-selected adapter %s with best RSSI %d",
                best_source, best_rssi
            )
            # Get device from the best adapter using the same snapshot
            for svc_info in discovered_services:
                if (svc_info.address.upper() == address.upper() and
                    getattr(svc_info, 'source', None) == best_source):
                    device = svc_info.device
                    source = best_source
                    rssi = best_rssi if best_rssi != RSSI_UNAVAILABLE else None
                    break

        # Final fallback to default lookup
        if device is None:
            device = bluetooth.async_ble_device_from_address(
                hass, address, connectable=True
            )
            if device:
                fallback_source = "unknown"
                if hasattr(device, 'details') and isinstance(device.details, dict):
                    fallback_source = device.details.get('source', 'unknown')
                source = fallback_source
                _LOGGER.info(
                    "Using fallback adapter selection, device found via: %s",
                    fallback_source,
                )

    return AdapterSelectionResult(
        device=device,
        source=source,
        rssi=rssi,
        available_sources=available_sources,
    )


def detect_esphome_proxy(hass: HomeAssistant, address: str) -> bool:
    """Detect if connection is through an ESPHome Bluetooth proxy.

    Args:
        hass: Home Assistant instance
        address: The BLE device address

    Returns:
        True if ESPHome proxy detected, False otherwise
    """
    try:
        service_info = bluetooth.async_last_service_info(
            hass, address, connectable=True
        )
        if service_info:
            _LOGGER.debug(
                "Service info: source=%s, rssi=%s, connectable=%s, service_uuids=%s",
                getattr(service_info, 'source', 'N/A'),
                getattr(service_info, 'rssi', 'N/A'),
                getattr(service_info, 'connectable', 'N/A'),
                getattr(service_info, 'service_uuids', []),
            )
            # Check if this is from an ESPHome proxy
            info_source = getattr(service_info, 'source', '')
            if info_source and 'esphome' in info_source.lower():
                _LOGGER.info(
                    "Device discovered via ESPHome Bluetooth proxy: %s",
                    info_source,
                )
                return True
    except Exception as err:
        _LOGGER.debug("Could not get detailed service info: %s", err)

    return False


async def discover_services(client: BleakClient, address: str) -> bool:
    """Explicitly discover BLE services and log the hierarchy.

    Some backends don't auto-discover services, so this ensures
    services are available before we try to use them.

    Args:
        client: The connected BleakClient
        address: The BLE device address (for logging)

    Returns:
        True if services were discovered successfully, False otherwise
    """
    # Explicitly discover services
    _LOGGER.debug("Discovering BLE services...")
    # Note: In Bleak >=0.21 (which we require), service discovery is automatic on connection.

    # Log discovered services in detail
    if client.services:
        services_list = list(client.services)
        _LOGGER.debug(
            "Discovered %d BLE services on %s:",
            len(services_list),
            address,
        )
        for service in client.services:
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
        return True
    else:
        _LOGGER.warning(
            "No BLE services discovered on %s - this may indicate a connection issue",
            address,
        )
        return False


async def read_ble_device_info(
    client: BleakClient, address: str
) -> tuple[str | None, str | None]:
    """Read manufacturer and model from BLE Device Information Service.

    This reads the standard BLE Device Information Service (UUID 0x180A)
    if available.

    Args:
        client: The connected BleakClient
        address: The BLE device address (for logging)

    Returns:
        Tuple of (manufacturer, model), either can be None if not available
    """
    manufacturer: str | None = None
    model: str | None = None

    if not client.is_connected:
        return manufacturer, model

    if not client.services:
        return manufacturer, model

    # Check if Device Information Service exists
    has_device_info = False
    for service in client.services:
        if service.uuid.lower() == DEVICE_INFO_SERVICE_UUID:
            has_device_info = True
            break

    if not has_device_info:
        _LOGGER.debug("Device Information Service not found on %s", address)
        return manufacturer, model

    _LOGGER.debug("Reading Device Information Service from %s", address)

    # Read manufacturer name
    try:
        manufacturer_uuid = DEVICE_INFO_CHARS["manufacturer_name"]
        value = await client.read_gatt_char(manufacturer_uuid)
        try:
            manufacturer = value.decode("utf-8").rstrip("\x00")
            _LOGGER.debug("BLE manufacturer: %s", manufacturer)
        except UnicodeDecodeError:
            _LOGGER.debug("Could not decode manufacturer name as UTF-8")
    except (BleakError, TimeoutError) as err:
        _LOGGER.debug("Could not read manufacturer name: %s", err)

    # Read model number
    try:
        model_uuid = DEVICE_INFO_CHARS["model_number"]
        value = await client.read_gatt_char(model_uuid)
        try:
            model = value.decode("utf-8").rstrip("\x00")
            _LOGGER.debug("BLE model: %s", model)
        except UnicodeDecodeError:
            _LOGGER.debug("Could not decode model number as UTF-8")
    except (BleakError, TimeoutError) as err:
        _LOGGER.debug("Could not read model number: %s", err)

    return manufacturer, model
