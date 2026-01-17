"""BLE diagnostic runner for capturing device protocol data."""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

from bleak import BleakClient
from bleak.exc import BleakError
from bleak_retry_connector import establish_connection
from homeassistant.components import bluetooth
from homeassistant.core import HomeAssistant

from .const import DOMAIN

if TYPE_CHECKING:
    from .coordinator import AdjustableBedCoordinator

_LOGGER = logging.getLogger(__name__)

# Standard BLE Device Information Service UUIDs
DEVICE_INFO_SERVICE_UUID = "0000180a-0000-1000-8000-00805f9b34fb"
DEVICE_INFO_CHARS = {
    "manufacturer_name": "00002a29-0000-1000-8000-00805f9b34fb",
    "model_number": "00002a24-0000-1000-8000-00805f9b34fb",
    "serial_number": "00002a25-0000-1000-8000-00805f9b34fb",
    "hardware_revision": "00002a27-0000-1000-8000-00805f9b34fb",
    "firmware_revision": "00002a26-0000-1000-8000-00805f9b34fb",
    "software_revision": "00002a28-0000-1000-8000-00805f9b34fb",
    "system_id": "00002a23-0000-1000-8000-00805f9b34fb",
}

# Connection settings
CONNECTION_TIMEOUT = 30.0
DEFAULT_CAPTURE_DURATION = 120  # 2 minutes


@dataclass
class CapturedNotification:
    """A captured BLE notification."""

    characteristic: str
    timestamp: str
    data_hex: str


@dataclass
class CharacteristicInfo:
    """Information about a BLE characteristic."""

    uuid: str
    properties: list[str]
    value_hex: str | None = None
    read_error: str | None = None


@dataclass
class ServiceInfo:
    """Information about a BLE service."""

    uuid: str
    characteristics: list[CharacteristicInfo] = field(default_factory=list)


@dataclass
class DiagnosticReport:
    """Complete diagnostic report for a BLE device."""

    metadata: dict[str, Any]
    device: dict[str, Any]
    advertisement: dict[str, Any]
    gatt_services: list[dict[str, Any]]
    device_information: dict[str, str | None]
    notifications: list[dict[str, str]]
    errors: list[str]

    def to_dict(self) -> dict[str, Any]:
        """Convert report to dictionary for JSON serialization."""
        return {
            "metadata": self.metadata,
            "device": self.device,
            "advertisement": self.advertisement,
            "gatt_services": self.gatt_services,
            "device_information": self.device_information,
            "notifications": self.notifications,
            "errors": self.errors,
        }


class BLEDiagnosticRunner:
    """Runner for BLE device diagnostics."""

    def __init__(
        self,
        hass: HomeAssistant,
        address: str,
        capture_duration: int = DEFAULT_CAPTURE_DURATION,
        coordinator: AdjustableBedCoordinator | None = None,
    ) -> None:
        """Initialize the diagnostic runner."""
        if capture_duration < 0:
            raise ValueError("capture_duration must be non-negative")

        self.hass = hass
        self.address = address.upper()
        self.capture_duration = capture_duration
        self.coordinator = coordinator

        self._client: BleakClient | None = None
        self._using_coordinator_connection: bool = False
        self._notifications: list[CapturedNotification] = []
        self._errors: list[str] = []
        self._notification_lock = asyncio.Lock()

    async def run_diagnostics(self) -> DiagnosticReport:
        """Run full diagnostic capture on the device."""
        _LOGGER.info(
            "Starting BLE diagnostics for %s (capture duration: %ds)",
            self.address,
            self.capture_duration,
        )

        start_time = datetime.now(timezone.utc)
        device_info: dict[str, Any] = {"address": self.address}
        advertisement_info: dict[str, Any] = {}
        services_info: list[ServiceInfo] = []
        device_information: dict[str, str | None] = {}

        try:
            # Get advertisement data from HA Bluetooth
            service_info = bluetooth.async_last_service_info(
                self.hass, self.address, connectable=True
            )
            if service_info:
                device_info["name"] = service_info.name
                device_info["rssi"] = getattr(service_info, "rssi", None)
                advertisement_info["service_uuids"] = [
                    str(uuid) for uuid in service_info.service_uuids
                ]
                advertisement_info["manufacturer_data"] = {
                    str(k): bytes(v).hex()
                    for k, v in service_info.manufacturer_data.items()
                }
                advertisement_info["service_data"] = {
                    str(k): bytes(v).hex()
                    for k, v in service_info.service_data.items()
                }
            else:
                self._errors.append("No advertisement data available")

            # Connect to device
            await self._connect()

            if self._client and self._client.is_connected:
                # Enumerate GATT services and characteristics
                services_info = await self._enumerate_services()

                # Read Device Information Service
                device_information = await self._read_device_information()

                # Subscribe to all notifiable characteristics
                await self._subscribe_to_notifications(services_info)

                # Capture notifications for the specified duration
                _LOGGER.info(
                    "Capturing notifications for %d seconds. "
                    "Operate the physical remote to generate data.",
                    self.capture_duration,
                )
                await asyncio.sleep(self.capture_duration)

                # Unsubscribe from notifications
                await self._unsubscribe_from_notifications(services_info)

        except Exception as err:
            error_msg = f"Diagnostic error: {err}"
            _LOGGER.error(error_msg)
            self._errors.append(error_msg)
        finally:
            await self._disconnect()

        end_time = datetime.now(timezone.utc)

        return DiagnosticReport(
            metadata={
                "version": "1.0",
                "timestamp": start_time.isoformat(),
                "end_timestamp": end_time.isoformat(),
                "capture_duration_seconds": self.capture_duration,
                "integration_domain": DOMAIN,
            },
            device=device_info,
            advertisement=advertisement_info,
            gatt_services=[self._service_to_dict(s) for s in services_info],
            device_information=device_information,
            notifications=[
                {
                    "characteristic": n.characteristic,
                    "timestamp": n.timestamp,
                    "data_hex": n.data_hex,
                }
                for n in self._notifications
            ],
            errors=self._errors,
        )

    async def _connect(self) -> None:
        """Connect to the BLE device."""
        # If we have a coordinator with an active connection, use it
        if self.coordinator and self.coordinator.client and self.coordinator.is_connected:
            _LOGGER.info("Using existing connection from coordinator")
            self._client = self.coordinator.client
            self._using_coordinator_connection = True
            # Pause the disconnect timer while capturing - capture may exceed idle timeout
            self.coordinator.pause_disconnect_timer()
            return

        # Otherwise, establish a new connection
        _LOGGER.info("Establishing new BLE connection to %s", self.address)
        self._using_coordinator_connection = False

        device = bluetooth.async_ble_device_from_address(
            self.hass, self.address, connectable=True
        )
        if device is None:
            error = f"Device {self.address} not found in Bluetooth scanner"
            self._errors.append(error)
            raise BleakError(error)

        try:
            self._client = await establish_connection(
                BleakClient,
                device,
                f"diagnostic_{self.address}",
                max_attempts=2,
                timeout=CONNECTION_TIMEOUT,
            )
            _LOGGER.info("Connected to %s", self.address)
        except Exception as err:
            error = f"Failed to connect: {err}"
            self._errors.append(error)
            raise

    async def _disconnect(self) -> None:
        """Disconnect from the BLE device."""
        # Don't disconnect if we're using the coordinator's connection
        if self._using_coordinator_connection:
            _LOGGER.debug("Leaving coordinator connection intact")
            # Resume the disconnect timer now that capture is complete
            if self.coordinator:
                self.coordinator.resume_disconnect_timer()
            self._client = None
            return

        if self._client and self._client.is_connected:
            _LOGGER.info("Disconnecting from %s", self.address)
            try:
                await self._client.disconnect()
            except Exception as err:
                _LOGGER.debug("Error during disconnect: %s", err)
            self._client = None
            self._using_coordinator_connection = False

    async def _enumerate_services(self) -> list[ServiceInfo]:
        """Enumerate all GATT services and characteristics."""
        if not self._client or not self._client.services:
            return []

        services: list[ServiceInfo] = []

        for service in self._client.services:
            service_info = ServiceInfo(uuid=service.uuid)

            for char in service.characteristics:
                char_info = CharacteristicInfo(
                    uuid=char.uuid,
                    properties=list(char.properties),
                )

                # Try to read the characteristic value if readable
                if "read" in char.properties:
                    try:
                        value = await self._client.read_gatt_char(char.uuid)
                        char_info.value_hex = value.hex()
                    except Exception as err:
                        char_info.read_error = str(err)
                        _LOGGER.debug(
                            "Could not read characteristic %s: %s",
                            char.uuid,
                            err,
                        )

                service_info.characteristics.append(char_info)

            services.append(service_info)

        _LOGGER.info("Enumerated %d GATT services", len(services))
        return services

    async def _read_device_information(self) -> dict[str, str | None]:
        """Read standard Device Information Service if available."""
        if not self._client or not self._client.services:
            return {}

        info: dict[str, str | None] = {}

        # Check if Device Information Service exists
        has_device_info = False
        for service in self._client.services:
            if service.uuid.lower() == DEVICE_INFO_SERVICE_UUID:
                has_device_info = True
                break

        if not has_device_info:
            _LOGGER.debug("Device Information Service not found")
            return info

        for name, uuid in DEVICE_INFO_CHARS.items():
            try:
                value = await self._client.read_gatt_char(uuid)
                # Device info chars are typically strings
                try:
                    info[name] = value.decode("utf-8").rstrip("\x00")
                except UnicodeDecodeError:
                    info[name] = value.hex()
                _LOGGER.debug("Device info %s: %s", name, info[name])
            except Exception as err:
                _LOGGER.debug("Could not read %s: %s", name, err)
                info[name] = None

        return info

    async def _subscribe_to_notifications(
        self, services: list[ServiceInfo]
    ) -> None:
        """Subscribe to all notifiable characteristics."""
        if not self._client:
            return

        # Skip notification subscription when using coordinator's connection
        # to avoid replacing or tearing down coordinator callbacks
        if self._using_coordinator_connection:
            _LOGGER.debug(
                "Skipping notification subscription (using coordinator connection)"
            )
            return

        for service in services:
            for char in service.characteristics:
                if "notify" in char.properties or "indicate" in char.properties:
                    try:
                        await self._client.start_notify(
                            char.uuid,
                            lambda sender, data, uuid=char.uuid: asyncio.create_task(
                                self._handle_notification(uuid, data)
                            ),
                        )
                        _LOGGER.debug("Subscribed to notifications on %s", char.uuid)
                    except Exception as err:
                        error = f"Failed to subscribe to {char.uuid}: {err}"
                        _LOGGER.debug(error)
                        self._errors.append(error)

    async def _unsubscribe_from_notifications(
        self, services: list[ServiceInfo]
    ) -> None:
        """Unsubscribe from all notifiable characteristics."""
        if not self._client or not self._client.is_connected:
            return

        # Skip notification unsubscription when using coordinator's connection
        # to avoid tearing down coordinator callbacks
        if self._using_coordinator_connection:
            _LOGGER.debug(
                "Skipping notification unsubscription (using coordinator connection)"
            )
            return

        for service in services:
            for char in service.characteristics:
                if "notify" in char.properties or "indicate" in char.properties:
                    try:
                        await self._client.stop_notify(char.uuid)
                    except Exception as err:
                        _LOGGER.debug(
                            "Error unsubscribing from %s: %s",
                            char.uuid,
                            err,
                        )

    async def _handle_notification(
        self, characteristic_uuid: str, data: bytes
    ) -> None:
        """Handle an incoming notification."""
        timestamp = datetime.now(timezone.utc).isoformat()

        async with self._notification_lock:
            notification = CapturedNotification(
                characteristic=characteristic_uuid,
                timestamp=timestamp,
                data_hex=data.hex(),
            )
            self._notifications.append(notification)

        _LOGGER.debug(
            "Notification on %s: %s",
            characteristic_uuid,
            data.hex(),
        )

    @staticmethod
    def _service_to_dict(service: ServiceInfo) -> dict[str, Any]:
        """Convert ServiceInfo to dictionary."""
        return {
            "uuid": service.uuid,
            "characteristics": [
                {
                    "uuid": char.uuid,
                    "properties": char.properties,
                    "value_hex": char.value_hex,
                    "read_error": char.read_error,
                }
                for char in service.characteristics
            ],
        }


def save_diagnostic_report(
    hass: HomeAssistant,
    report: DiagnosticReport,
    address: str,
) -> Path:
    """Save diagnostic report to a JSON file in the config directory."""
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    address_safe = address.replace(":", "").lower()
    filename = f"adjustable_bed_diagnostic_{address_safe}_{timestamp}.json"

    config_dir = Path(hass.config.config_dir)
    filepath = config_dir / filename

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(report.to_dict(), f, indent=2)

    _LOGGER.info("Diagnostic report saved to %s", filepath)
    return filepath
