"""BLE diagnostic runner for capturing device protocol data."""

from __future__ import annotations

import asyncio
import contextlib
import functools
import logging
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from bleak import BleakClient
from bleak.backends.device import BLEDevice
from bleak.exc import BleakError
from bleak_retry_connector import establish_connection
from homeassistant.components import bluetooth
from homeassistant.core import HomeAssistant

from .adapter import (
    find_service_info_by_address,
    get_service_info_snapshots_by_address,
    select_adapter,
)
from .const import (
    ADAPTER_AUTO,
    CONF_PREFERRED_ADAPTER,
    DEVICE_INFO_CHARS,
    DEVICE_INFO_SERVICE_UUID,
    DOMAIN,
    SUPPORTED_BED_TYPES,
)
from .detection import detect_bed_type_detailed
from .diagnostic_payloads import (
    format_mapping_payloads,
    format_payload,
    new_connection_attempt_details,
    payload_ascii_preview,
    summarize_repeated_payloads,
)
from .kaidi_protocol import extract_kaidi_advertisement, kaidi_advertisement_to_dict

if TYPE_CHECKING:
    from .coordinator import AdjustableBedCoordinator

_LOGGER = logging.getLogger(__name__)

# Connection settings
CONNECTION_TIMEOUT = 30.0
DEFAULT_CAPTURE_DURATION = 120  # 2 minutes
MAX_CAPTURED_NOTIFICATIONS = 5000

# Timestamps above this value (approx. 2001-09-09) are treated as Unix epoch seconds
_EPOCH_SECONDS_THRESHOLD = 1_000_000_000


@dataclass
class CapturedNotification:
    """A captured BLE notification."""

    characteristic: str
    timestamp: str
    data_hex: str


@dataclass
class DescriptorInfo:
    """Information about a BLE descriptor."""

    uuid: str
    handle: int | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert descriptor info to a dictionary."""
        return {
            "uuid": self.uuid,
            "handle": self.handle,
        }


@dataclass
class CharacteristicInfo:
    """Information about a BLE characteristic."""

    uuid: str
    handle: int | None
    properties: list[str]
    read_result: dict[str, Any] | None = None
    read_error: str | None = None
    notify_subscription: dict[str, Any] = field(default_factory=dict)
    descriptors: list[DescriptorInfo] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert characteristic info to a dictionary."""
        return {
            "uuid": self.uuid,
            "handle": self.handle,
            "properties": self.properties,
            "read_result": self.read_result,
            "read_error": self.read_error,
            "notify_subscription": self.notify_subscription,
            "descriptors": [descriptor.to_dict() for descriptor in self.descriptors],
        }


@dataclass
class ServiceInfo:
    """Information about a BLE service."""

    uuid: str
    handle: int | None = None
    characteristics: list[CharacteristicInfo] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert service info to a dictionary."""
        return {
            "uuid": self.uuid,
            "handle": self.handle,
            "characteristics": [characteristic.to_dict() for characteristic in self.characteristics],
        }


@dataclass
class DiagnosticReport:
    """Complete diagnostic report for a BLE device."""

    metadata: dict[str, Any]
    device: dict[str, Any]
    advertisement: dict[str, Any]
    advertisements_by_source: list[dict[str, Any]]
    detection: dict[str, Any]
    gatt_services: list[dict[str, Any]]
    gatt_summary: dict[str, Any]
    device_information: dict[str, str | None]
    notifications: list[dict[str, str]]
    notification_summary: dict[str, Any]
    adapter_details: dict[str, Any]
    connection_history: dict[str, Any]
    connection_attempt_details: list[dict[str, Any]]
    command_trace: list[dict[str, Any]]
    errors: list[str]

    def to_dict(self) -> dict[str, Any]:
        """Convert report to dictionary for JSON serialization."""
        return {
            "metadata": self.metadata,
            "device": self.device,
            "advertisement": self.advertisement,
            "advertisements_by_source": self.advertisements_by_source,
            "detection": self.detection,
            "gatt_services": self.gatt_services,
            "gatt_summary": self.gatt_summary,
            "device_information": self.device_information,
            "notifications": self.notifications,
            "notification_summary": self.notification_summary,
            "adapter_details": self.adapter_details,
            "connection_history": self.connection_history,
            "connection_attempt_details": self.connection_attempt_details,
            "command_trace": self.command_trace,
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
        self._notifications: deque[CapturedNotification] = deque(maxlen=MAX_CAPTURED_NOTIFICATIONS)
        self._errors: list[str] = []
        self._notification_lock = asyncio.Lock()
        self._diagnostic_notifications_started: bool = False
        self._notification_payloads: dict[str, deque[bytes]] = {}
        self._connection_attempt_details: list[dict[str, Any]] = []
        self._advertisement_snapshots: list[tuple[Any, bool]] = []
        self._selected_source: str | None = None
        self._selected_rssi: int | None = None
        self._selected_connectable: bool | None = None
        self._actual_source: str | None = None
        self._selected_ble_device: BLEDevice | None = None
        self._using_non_connectable_fallback: bool = False
        self._background_tasks: set[asyncio.Task[None]] = set()

    async def run_diagnostics(self) -> DiagnosticReport:
        """Run full diagnostic capture on the device."""
        _LOGGER.info(
            "Starting BLE diagnostics for %s (capture duration: %ds)",
            self.address,
            self.capture_duration,
        )

        start_time = datetime.now(UTC)
        services_info: list[ServiceInfo] = []
        device_information: dict[str, str | None] = {}
        self._advertisement_snapshots = get_service_info_snapshots_by_address(
            self.hass,
            self.address,
            allow_non_connectable=True,
        )

        try:
            await self._connect()

            if self._client and self._client.is_connected:
                services_info = await self._enumerate_services()
                device_information = await self._read_device_information()

                try:
                    await self._subscribe_to_notifications(services_info)

                    _LOGGER.info(
                        "Capturing notifications for %d seconds. "
                        "Operate the physical remote to generate data.",
                        self.capture_duration,
                    )
                    await asyncio.sleep(self.capture_duration)
                finally:
                    await self._unsubscribe_from_notifications(services_info)

        except asyncio.CancelledError:
            raise
        except Exception as err:
            error_msg = f"Diagnostic error: {err}"
            _LOGGER.exception(error_msg)
            self._errors.append(error_msg)
        finally:
            await self._disconnect()

        end_time = datetime.now(UTC)
        best_snapshot = self._best_snapshot()
        detection = self._build_detection_section(best_snapshot[0] if best_snapshot else None)

        adapter_details: dict[str, Any] = self.coordinator.adapter_details if self.coordinator else {}
        connection_history: dict[str, Any] = (
            self.coordinator.connection_history if self.coordinator else {}
        )
        connection_attempt_details = self._connection_attempt_details
        if not connection_attempt_details and self.coordinator is not None:
            connection_attempt_details = self.coordinator.connection_attempt_details

        command_trace = self.coordinator.command_trace if self.coordinator else []

        return DiagnosticReport(
            metadata={
                "version": "2.0",
                "timestamp": start_time.isoformat(),
                "end_timestamp": end_time.isoformat(),
                "capture_duration_seconds": self.capture_duration,
                "integration_domain": DOMAIN,
            },
            device=self._build_device_section(best_snapshot[0] if best_snapshot else None),
            advertisement=self._build_best_advertisement(best_snapshot),
            advertisements_by_source=self._build_advertisements_by_source(),
            detection=detection,
            gatt_services=[service.to_dict() for service in services_info],
            gatt_summary=self._build_gatt_summary(services_info),
            device_information=device_information,
            notifications=[
                {
                    "characteristic": notification.characteristic,
                    "timestamp": notification.timestamp,
                    "data_hex": notification.data_hex,
                }
                for notification in self._notifications
            ],
            notification_summary=self._build_notification_summary(),
            adapter_details=adapter_details,
            connection_history=connection_history,
            connection_attempt_details=connection_attempt_details,
            command_trace=command_trace,
            errors=self._errors,
        )

    async def _connect(self) -> None:
        """Connect to the BLE device."""
        if self.coordinator and self.coordinator.client and self.coordinator.is_connected:
            _LOGGER.info("Using existing connection from coordinator")
            self._client = self.coordinator.client
            self._using_coordinator_connection = True
            self._selected_source = self.coordinator.connection_source
            self._actual_source = self.coordinator.connection_source
            self._selected_rssi = self.coordinator.connection_rssi
            self._selected_connectable = True
            self.coordinator.pause_disconnect_timer()
            return

        _LOGGER.info("Establishing new BLE connection to %s", self.address)
        self._using_coordinator_connection = False

        preferred_adapter = ADAPTER_AUTO
        if self.coordinator is not None:
            preferred_adapter = self.coordinator.entry.data.get(
                CONF_PREFERRED_ADAPTER,
                ADAPTER_AUTO,
            )

        for attempt in range(2):
            attempt_start = time.monotonic()
            attempt_details = new_connection_attempt_details(attempt + 1, preferred_adapter)

            adapter_result = await select_adapter(
                self.hass,
                self.address,
                preferred_adapter,
            )
            attempt_details["selected_source"] = adapter_result.source
            attempt_details["selected_rssi"] = adapter_result.rssi
            attempt_details["selected_connectable"] = adapter_result.connectable
            attempt_details["non_connectable_fallback_used"] = adapter_result.connectable is False
            attempt_details["visible_sources"] = list(adapter_result.available_sources)
            attempt_details["lookup_elapsed_seconds"] = round(
                time.monotonic() - attempt_start, 3
            )

            device = adapter_result.device
            if device is None:
                error = f"Device {self.address} not found in Bluetooth scanner"
                attempt_details["total_elapsed_seconds"] = attempt_details["lookup_elapsed_seconds"]
                attempt_details["error"] = error
                attempt_details["error_type"] = "BleakError"
                attempt_details["error_category"] = "DEVICE NOT FOUND"
                attempt_details["result"] = "device_not_found"
                self._connection_attempt_details.append(attempt_details)
                self._errors.append(error)
                raise BleakError(error)

            self._selected_ble_device = device
            self._selected_source = adapter_result.source
            self._selected_rssi = adapter_result.rssi
            self._selected_connectable = adapter_result.connectable
            self._using_non_connectable_fallback = adapter_result.connectable is False

            if adapter_result.connectable is False:
                warning = (
                    f"Using non-connectable scanner record for {self.address}; "
                    "the Bluetooth proxy may be misclassifying the advertisement"
                )
                _LOGGER.warning(warning)
                self._errors.append(warning)

            try:
                connect_start = time.monotonic()
                self._client = await establish_connection(
                    BleakClient,
                    device,
                    f"diagnostic_{self.address}",
                    max_attempts=1,
                    timeout=CONNECTION_TIMEOUT,
                )
                attempt_details["connect_elapsed_seconds"] = round(
                    time.monotonic() - connect_start, 3
                )
                attempt_details["service_discovery"]["attempted"] = True
                if hasattr(self._client, "get_services"):
                    await self._client.get_services()
                attempt_details["service_discovery"]["success"] = True
                attempt_details["service_discovery"]["service_count"] = (
                    len(list(self._client.services)) if self._client.services else 0
                )
                attempt_details["total_elapsed_seconds"] = round(
                    time.monotonic() - attempt_start, 3
                )
                attempt_details["result"] = "connected"
                self._actual_source = self._extract_client_source(self._client) or self._selected_source
                attempt_details["actual_source"] = self._actual_source
                self._connection_attempt_details.append(attempt_details)
                _LOGGER.info("Connected to %s", self.address)
                return
            except Exception as err:
                attempt_details["connect_elapsed_seconds"] = round(
                    time.monotonic() - attempt_start, 3
                )
                attempt_details["total_elapsed_seconds"] = round(
                    time.monotonic() - attempt_start, 3
                )
                attempt_details["error"] = str(err)
                attempt_details["error_type"] = type(err).__name__
                attempt_details["error_category"] = "BLE ERROR"
                attempt_details["result"] = "failed"
                if attempt_details["service_discovery"]["attempted"]:
                    attempt_details["service_discovery"]["success"] = False
                self._connection_attempt_details.append(attempt_details)

                if self._client is not None:
                    with contextlib.suppress(Exception):
                        await self._client.disconnect()
                    self._client = None

                if attempt == 1:
                    error = f"Failed to connect: {err}"
                    self._errors.append(error)
                    raise

                await asyncio.sleep(1)

    async def _disconnect(self) -> None:
        """Disconnect from the BLE device."""
        if self._using_coordinator_connection:
            _LOGGER.debug("Leaving coordinator connection intact")
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
            service_info = ServiceInfo(
                uuid=service.uuid,
                handle=getattr(service, "handle", None),
            )

            for char in service.characteristics:
                char_info = CharacteristicInfo(
                    uuid=char.uuid,
                    handle=getattr(char, "handle", None),
                    properties=list(char.properties),
                    notify_subscription={
                        "attempted": False,
                        "success": None,
                        "method": None,
                        "error": None,
                    },
                    descriptors=[
                        DescriptorInfo(
                            uuid=descriptor.uuid,
                            handle=getattr(descriptor, "handle", None),
                        )
                        for descriptor in getattr(char, "descriptors", [])
                    ],
                )

                if "read" in char.properties:
                    try:
                        value = await self._client.read_gatt_char(char)
                        char_info.read_result = format_payload(value)
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

        has_device_info = any(
            service.uuid.lower() == DEVICE_INFO_SERVICE_UUID for service in self._client.services
        )
        if not has_device_info:
            _LOGGER.debug("Device Information Service not found")
            return info

        for name, uuid in DEVICE_INFO_CHARS.items():
            try:
                value = await self._client.read_gatt_char(uuid)
                try:
                    info[name] = value.decode("utf-8").rstrip("\x00")
                except UnicodeDecodeError:
                    info[name] = value.hex()
            except Exception as err:
                _LOGGER.debug("Could not read %s: %s", name, err)
                info[name] = None

        return info

    def _raw_notify_callback(self, characteristic_uuid: str, data: bytes) -> None:
        """Handle raw notification from coordinator's controller."""
        task = asyncio.create_task(self._handle_notification(characteristic_uuid, data))
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

    async def _subscribe_to_notifications(self, services: list[ServiceInfo]) -> None:
        """Subscribe to all notifiable characteristics."""
        if not self._client:
            return

        if self._using_coordinator_connection:
            if self.coordinator is not None:
                _LOGGER.debug("Registering raw notification callback with coordinator")
                self.coordinator.set_raw_notify_callback(self._raw_notify_callback)
                if self.coordinator.disable_angle_sensing:
                    _LOGGER.info(
                        "Angle sensing disabled - starting notifications for diagnostic capture"
                    )
                    await self.coordinator.async_start_notify_for_diagnostics()
                    self._diagnostic_notifications_started = True

            for service in services:
                for char in service.characteristics:
                    if "notify" in char.properties or "indicate" in char.properties:
                        char.notify_subscription.update(
                            {
                                "attempted": False,
                                "success": None,
                                "method": "shared_connection",
                                "error": (
                                    "Direct per-characteristic subscription skipped while "
                                    "reusing the coordinator connection"
                                ),
                            }
                        )
            return

        for service in services:
            bleak_service = self._client.services.get_service(service.uuid)
            for char in service.characteristics:
                if "notify" not in char.properties and "indicate" not in char.properties:
                    continue

                char.notify_subscription["attempted"] = True
                char.notify_subscription["method"] = "direct_subscription"

                bleak_characteristic = None
                if bleak_service is not None:
                    for candidate in bleak_service.characteristics:
                        if getattr(candidate, "handle", None) == char.handle:
                            bleak_characteristic = candidate
                            break
                if bleak_characteristic is None:
                    bleak_characteristic = char.uuid

                try:
                    handler = functools.partial(self._notification_handler_sync, char.uuid)
                    await self._client.start_notify(bleak_characteristic, handler)
                    char.notify_subscription["success"] = True
                except Exception as err:
                    error = f"Failed to subscribe to {char.uuid}: {err}"
                    char.notify_subscription["success"] = False
                    char.notify_subscription["error"] = str(err)
                    _LOGGER.debug(error)
                    self._errors.append(error)

    def _notification_handler_sync(self, uuid: str, sender: object, data: bytearray) -> None:
        """Synchronous notification handler that schedules async processing."""
        self.hass.async_create_task(self._handle_notification(uuid, data))

    async def _unsubscribe_from_notifications(self, services: list[ServiceInfo]) -> None:
        """Unsubscribe from all notifiable characteristics."""
        if self._using_coordinator_connection:
            if self.coordinator is not None:
                _LOGGER.debug("Clearing raw notification callback from coordinator")
                self.coordinator.set_raw_notify_callback(None)
                if (
                    self._diagnostic_notifications_started
                    and self.coordinator.controller is not None
                    and self._client
                    and self._client.is_connected
                ):
                    _LOGGER.debug("Stopping diagnostic notifications that were started for capture")
                    await self.coordinator.controller.stop_notify()
                self._diagnostic_notifications_started = False
            return

        if not self._client or not self._client.is_connected:
            return

        for service in services:
            bleak_service = self._client.services.get_service(service.uuid)
            for char in service.characteristics:
                if "notify" not in char.properties and "indicate" not in char.properties:
                    continue
                try:
                    bleak_characteristic = None
                    if bleak_service is not None:
                        for candidate in bleak_service.characteristics:
                            if getattr(candidate, "handle", None) == char.handle:
                                bleak_characteristic = candidate
                                break
                    await self._client.stop_notify(bleak_characteristic or char.uuid)
                except Exception as err:
                    _LOGGER.debug(
                        "Error unsubscribing from %s: %s",
                        char.uuid,
                        err,
                    )

    async def _handle_notification(self, characteristic_uuid: str, data: bytes | bytearray) -> None:
        """Handle an incoming notification."""
        timestamp = datetime.now(UTC).isoformat()
        payload = bytes(data)

        async with self._notification_lock:
            notification = CapturedNotification(
                characteristic=characteristic_uuid,
                timestamp=timestamp,
                data_hex=payload.hex(),
            )
            self._notifications.append(notification)
            if characteristic_uuid not in self._notification_payloads:
                self._notification_payloads[characteristic_uuid] = deque(maxlen=MAX_CAPTURED_NOTIFICATIONS)
            self._notification_payloads[characteristic_uuid].append(payload)

        _LOGGER.debug(
            "Notification on %s: %s",
            characteristic_uuid,
            payload.hex(),
        )

    def _build_gatt_summary(self, services: list[ServiceInfo]) -> dict[str, Any]:
        """Build GATT summary from enumerated services."""
        if not services:
            return {
                "available": False,
                "service_count": 0,
                "characteristic_count": 0,
                "descriptor_count": 0,
                "notifiable_characteristics": [],
                "writable_characteristics": [],
                "readable_characteristics": [],
            }

        char_count = 0
        descriptor_count = 0
        notifiable_chars: list[str] = []
        writable_chars: list[str] = []
        readable_chars: list[str] = []

        for service in services:
            for char in service.characteristics:
                char_count += 1
                descriptor_count += len(char.descriptors)
                if "notify" in char.properties or "indicate" in char.properties:
                    notifiable_chars.append(char.uuid)
                if "write" in char.properties or "write-without-response" in char.properties:
                    writable_chars.append(char.uuid)
                if "read" in char.properties:
                    readable_chars.append(char.uuid)

        return {
            "available": True,
            "service_count": len(services),
            "characteristic_count": char_count,
            "descriptor_count": descriptor_count,
            "notifiable_characteristics": sorted(notifiable_chars),
            "writable_characteristics": sorted(writable_chars),
            "readable_characteristics": sorted(readable_chars),
        }

    def _build_detection_section(self, service_info: Any | None) -> dict[str, Any]:
        """Build a detection reasoning section."""
        if service_info is None:
            return {
                "bed_type": None,
                "confidence": 0.0,
                "signals": [],
                "ambiguous_types": [],
                "requires_characteristic_check": False,
                "detected_remote": None,
                "supported_match": False,
            }

        detection = detect_bed_type_detailed(service_info)
        return {
            "bed_type": detection.bed_type,
            "confidence": detection.confidence,
            "signals": list(detection.signals),
            "ambiguous_types": list(detection.ambiguous_types or []),
            "requires_characteristic_check": detection.requires_characteristic_check,
            "detected_remote": detection.detected_remote,
            "supported_match": detection.bed_type in SUPPORTED_BED_TYPES
            if detection.bed_type is not None
            else False,
            "manufacturer_id": detection.manufacturer_id,
        }

    def _build_best_advertisement(
        self,
        best_snapshot: tuple[Any, bool] | None,
    ) -> dict[str, Any]:
        """Build the best current advertisement snapshot."""
        if best_snapshot is None:
            return {
                "captured_at": datetime.now(UTC).isoformat(),
                "address": self.address,
                "name": None,
                "rssi": None,
                "source": self._selected_source,
                "connectable": self._selected_connectable,
                "service_uuids": [],
                "manufacturer_data": {},
                "service_data": {},
                "selected_for_connection": False,
                "non_connectable_fallback_used": self._using_non_connectable_fallback,
            }

        service_info, connectable = best_snapshot
        return self._service_info_snapshot_to_dict(
            service_info,
            connectable,
            selected_for_connection=True,
        )

    def _build_advertisements_by_source(self) -> list[dict[str, Any]]:
        """Build one advertisement row per current scanner source."""
        if not self._advertisement_snapshots:
            return []

        rows = [
            self._service_info_snapshot_to_dict(
                service_info,
                connectable,
                selected_for_connection=(
                    getattr(service_info, "source", None) == self._actual_source
                    or getattr(service_info, "source", None) == self._selected_source
                ),
            )
            for service_info, connectable in self._advertisement_snapshots
        ]

        rows.sort(
            key=lambda row: (
                row["selected_for_connection"],
                row["connectable"],
                row["rssi"] if isinstance(row["rssi"], int) else -999,
            ),
            reverse=True,
        )
        return rows

    def _service_info_snapshot_to_dict(
        self,
        service_info: Any,
        connectable: bool,
        *,
        selected_for_connection: bool,
    ) -> dict[str, Any]:
        """Convert a Bluetooth service snapshot to a dictionary."""
        snapshot = {
            "captured_at": datetime.now(UTC).isoformat(),
            "address": service_info.address.upper(),
            "name": service_info.name,
            "source": getattr(service_info, "source", None),
            "rssi": getattr(service_info, "rssi", None),
            "connectable": connectable,
            "service_uuids": [str(uuid) for uuid in (service_info.service_uuids or [])],
            "manufacturer_data": format_mapping_payloads(service_info.manufacturer_data),
            "service_data": format_mapping_payloads(service_info.service_data),
            "scanner_time": self._serialize_scanner_time(getattr(service_info, "time", None)),
            "selected_for_connection": selected_for_connection,
            "non_connectable_fallback_used": (
                selected_for_connection and self._using_non_connectable_fallback
            ),
        }
        kaidi_advertisement = extract_kaidi_advertisement(service_info.manufacturer_data)
        if kaidi_advertisement is not None:
            snapshot["kaidi"] = kaidi_advertisement_to_dict(kaidi_advertisement)
        return snapshot

    def _build_device_section(self, service_info: Any | None) -> dict[str, Any]:
        """Build enriched device and backend info."""
        backend_device = self._extract_backend_device()
        details = self._extract_backend_details(
            backend_device.details if backend_device is not None else None
        )
        if self._selected_ble_device is not None:
            details.setdefault(
                "ble_device_details",
                self._extract_backend_details(self._selected_ble_device.details),
            )

        pairing = self._extract_pairing_info(details)
        visible_sources = [
            getattr(snapshot, "source", None)
            for snapshot, _ in self._advertisement_snapshots
            if getattr(snapshot, "source", None) is not None
        ]

        return {
            "address": self.address,
            "name": service_info.name if service_info is not None else None,
            "rssi": getattr(service_info, "rssi", None) if service_info is not None else None,
            "selected_source": self._selected_source,
            "actual_source": self._actual_source,
            "connectable": self._selected_connectable,
            "non_connectable_fallback_used": self._using_non_connectable_fallback,
            "backend_details": details,
            "pairing": pairing,
            "scanner_count": self._get_scanner_count(),
            "visible_sources": visible_sources,
        }

    def _build_notification_summary(self) -> dict[str, Any]:
        """Build an aggregated notification summary."""
        summary: dict[str, Any] = {
            "total_notifications": len(self._notifications),
            "by_characteristic": {},
        }

        if not self._notifications:
            return summary

        notifications_by_characteristic: dict[str, list[CapturedNotification]] = {}
        for notification in self._notifications:
            notifications_by_characteristic.setdefault(notification.characteristic, []).append(
                notification
            )

        for characteristic, notifications in notifications_by_characteristic.items():
            payloads = self._notification_payloads.get(characteristic, [])
            summary["by_characteristic"][characteristic] = {
                "count": len(notifications),
                "first_timestamp": notifications[0].timestamp,
                "last_timestamp": notifications[-1].timestamp,
                "observed_payload_lengths": sorted({len(payload) for payload in payloads}),
                "ascii_previews": sorted(
                    {
                        preview
                        for preview in (
                            payload_ascii_preview(payload) for payload in payloads
                        )
                        if preview is not None
                    }
                )[:5],
                "top_repeated_payloads": summarize_repeated_payloads(payloads),
            }

        return summary

    def _best_snapshot(self) -> tuple[Any, bool] | None:
        """Return the best current advertisement snapshot."""
        if not self._advertisement_snapshots:
            service_info, connectable = find_service_info_by_address(
                self.hass,
                self.address,
                allow_non_connectable=True,
            )
            if service_info is None:
                self._errors.append("No advertisement data available")
                return None
            return service_info, connectable

        for snapshot in self._advertisement_snapshots:
            source = getattr(snapshot[0], "source", None)
            if source is not None and source in {self._actual_source, self._selected_source}:
                return snapshot

        return self._advertisement_snapshots[0]

    def _extract_backend_device(self) -> BLEDevice | None:
        """Return the backend BLEDevice when available."""
        if self._client is None:
            return self._selected_ble_device

        backend = getattr(self._client, "_backend", None)
        backend_device = getattr(backend, "_device", None)
        if isinstance(backend_device, BLEDevice):
            return backend_device
        return self._selected_ble_device

    def _extract_client_source(self, client: BleakClient | None) -> str | None:
        """Return the connected client source when available."""
        backend = getattr(client, "_backend", None)
        backend_device = getattr(backend, "_device", None)
        if hasattr(backend_device, "details") and isinstance(backend_device.details, dict):
            source = backend_device.details.get("source")
            if isinstance(source, str):
                return source
        return None

    def _extract_backend_details(self, details: Any) -> dict[str, Any]:
        """Serialize backend details into a JSON-friendly structure."""
        if not isinstance(details, dict):
            return {}
        return {str(key): self._serialize_value(value) for key, value in details.items()}

    def _extract_pairing_info(self, details: dict[str, Any]) -> dict[str, Any]:
        """Extract pairing-related flags from backend details."""
        props = details.get("props", {})
        if not isinstance(props, dict):
            props = {}

        def _get_field(name: str, fallback_name: str | None = None) -> Any:
            if name in props:
                return props[name]
            if name in details:
                return details[name]
            if fallback_name and fallback_name in details:
                return details[fallback_name]
            return None

        return {
            "paired": _get_field("Paired", "paired"),
            "bonded": _get_field("Bonded", "bonded"),
            "trusted": _get_field("Trusted", "trusted"),
            "address_type": _get_field("AddressType", "address_type"),
        }

    def _get_scanner_count(self) -> int | None:
        """Return current connectable scanner count."""
        try:
            return bluetooth.async_scanner_count(self.hass, connectable=True)
        except Exception as err:
            self._errors.append(f"Could not read scanner count: {err}")
            return None

    def _serialize_scanner_time(self, raw_time: Any) -> str | float | int | None:
        """Serialize scanner timestamps when available."""
        if raw_time is None:
            return None
        if isinstance(raw_time, datetime):
            return raw_time.isoformat()
        if isinstance(raw_time, (int, float)):
            if raw_time > _EPOCH_SECONDS_THRESHOLD:
                return datetime.fromtimestamp(raw_time, tz=UTC).isoformat()
            return raw_time
        return str(raw_time)

    def _serialize_value(self, value: Any) -> Any:
        """Serialize nested backend values into JSON-safe structures."""
        if value is None or isinstance(value, (bool, int, float, str)):
            return value
        if isinstance(value, bytes):
            return format_payload(value)
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, dict):
            return {str(key): self._serialize_value(val) for key, val in value.items()}
        if isinstance(value, (list, tuple, set)):
            return [self._serialize_value(item) for item in value]
        return str(value)

