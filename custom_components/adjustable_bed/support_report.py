"""Support report generation for the Adjustable Bed integration."""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS, __version__ as HA_VERSION
from homeassistant.core import HomeAssistant

from .const import (
    CONF_BED_TYPE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_HAS_MASSAGE,
    CONF_MOTOR_COUNT,
    CONF_PREFERRED_ADAPTER,
    CONF_PROTOCOL_VARIANT,
    DOMAIN,
    SUPPORTED_BED_TYPES,
)
from .redaction import redact_data

if TYPE_CHECKING:
    from .coordinator import AdjustableBedCoordinator

_LOGGER = logging.getLogger(__name__)

# Maximum number of log entries to include
MAX_LOG_ENTRIES = 100


async def generate_support_report(
    hass: HomeAssistant,
    entry: ConfigEntry,
    coordinator: AdjustableBedCoordinator,
    include_logs: bool = True,
) -> dict[str, Any]:
    """Generate a comprehensive support report."""
    timestamp = datetime.now(timezone.utc)

    report: dict[str, Any] = {
        "report_version": "1.0",
        "generated_at": timestamp.isoformat(),
        "system": _get_system_info(hass),
        "integration": _get_integration_info(entry),
        "connection": _get_connection_info(coordinator),
        "bluetooth": await _get_bluetooth_info(hass, coordinator),
        "controller": _get_controller_info(coordinator),
        "position_data": dict(coordinator.position_data),
        "supported_bed_types": list(SUPPORTED_BED_TYPES),
    }

    if include_logs:
        report["recent_logs"] = _get_recent_logs()

    # Redact sensitive data (partial MAC redaction - keeps OUI for debugging)
    return redact_data(report)


def _get_system_info(hass: HomeAssistant) -> dict[str, Any]:
    """Get system information."""
    return {
        "home_assistant_version": HA_VERSION,
        "python_version": sys.version,
        "os": sys.platform,
        "timezone": str(hass.config.time_zone),
    }


def _get_integration_info(entry: ConfigEntry) -> dict[str, Any]:
    """Get integration configuration info."""
    return {
        "entry_id": entry.entry_id,
        "version": entry.version,
        "title": entry.title,
        "bed_type": entry.data.get(CONF_BED_TYPE),
        "protocol_variant": entry.data.get(CONF_PROTOCOL_VARIANT, "auto"),
        "motor_count": entry.data.get(CONF_MOTOR_COUNT),
        "has_massage": entry.data.get(CONF_HAS_MASSAGE),
        "disable_angle_sensing": entry.data.get(CONF_DISABLE_ANGLE_SENSING),
        "preferred_adapter": entry.data.get(CONF_PREFERRED_ADAPTER),
        "address": entry.data.get(CONF_ADDRESS),
    }


def _get_connection_info(coordinator: AdjustableBedCoordinator) -> dict[str, Any]:
    """Get connection state information."""
    is_connected = coordinator.is_connected
    client = coordinator.client

    info: dict[str, Any] = {
        "is_connected": is_connected,
        "is_connecting": coordinator.is_connecting,
    }

    if client and is_connected:
        info.update({
            "mtu_size": getattr(client, "mtu_size", None),
            "services_discovered": len(list(client.services)) if client.services else 0,
        })

        # Get service UUIDs
        if client.services:
            info["service_uuids"] = [str(service.uuid) for service in client.services]

    return info


def _get_controller_info(coordinator: AdjustableBedCoordinator) -> dict[str, Any]:
    """Get controller information."""
    info: dict[str, Any] = {"initialized": coordinator.controller is not None}

    if coordinator.controller:
        controller = coordinator.controller
        info.update({
            "class": type(controller).__name__,
            "characteristic_uuid": controller.control_characteristic_uuid,
        })

        # Add variant info for controllers that have it
        if hasattr(controller, "_is_wilinke"):
            info["richmat_is_wilinke"] = controller._is_wilinke
        if hasattr(controller, "_variant"):
            info["variant"] = controller._variant
        if hasattr(controller, "_char_uuid"):
            info["char_uuid"] = controller._char_uuid

    return info


async def _get_bluetooth_info(
    hass: HomeAssistant, coordinator: AdjustableBedCoordinator
) -> dict[str, Any]:
    """Get Bluetooth adapter and advertisement information."""
    info: dict[str, Any] = {}

    # Get last known advertisement data
    service_info = bluetooth.async_last_service_info(
        hass, coordinator.address, connectable=True
    )
    if service_info:
        info["last_advertisement"] = {
            "device_name": service_info.name,
            "rssi": getattr(service_info, "rssi", None),
            "service_uuids": [str(uuid) for uuid in service_info.service_uuids],
            "manufacturer_data": {
                str(k): bytes(v).hex()
                for k, v in service_info.manufacturer_data.items()
            },
            "service_data": {
                str(k): bytes(v).hex() for k, v in service_info.service_data.items()
            },
            "connectable": service_info.connectable,
        }
        # Include source info (adapter/proxy)
        if hasattr(service_info, "source"):
            info["last_advertisement"]["source"] = service_info.source
    else:
        info["last_advertisement"] = None

    # Get adapter info if available
    try:
        adapters = bluetooth.async_get_adapters(hass)
        info["adapters"] = [
            {
                "address": adapter.get("address"),
                "adapter_name": adapter.get("name"),
                "passive_scan": adapter.get("passive_scan"),
            }
            for adapter in adapters
        ]
    except Exception as err:
        info["adapters_error"] = str(err)

    return info


def _get_recent_logs() -> list[dict[str, str]]:
    """Get recent log entries related to the integration."""
    logs: list[dict[str, str]] = []

    try:
        # Access the logging memory handler if available
        # This is a best-effort approach since HA doesn't expose logs directly
        root_logger = logging.getLogger()
        for handler in root_logger.handlers:
            if hasattr(handler, "buffer"):
                # MemoryHandler or similar
                for record in list(handler.buffer)[-500:]:
                    if (
                        DOMAIN in record.name
                        or "bluetooth" in record.name.lower()
                        or "bleak" in record.name.lower()
                    ):
                        logs.append({
                            "timestamp": datetime.fromtimestamp(
                                record.created, tz=timezone.utc
                            ).isoformat(),
                            "level": record.levelname,
                            "name": record.name,
                            "message": record.getMessage(),
                        })
    except Exception as err:
        _LOGGER.debug("Could not retrieve log entries: %s", err)
        logs.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": "INFO",
            "name": DOMAIN,
            "message": f"Could not retrieve historical logs: {err}. "
            "Enable debug logging and reproduce the issue to capture logs.",
        })

    # Limit and return most recent
    return logs[-MAX_LOG_ENTRIES:]


def save_support_report(
    hass: HomeAssistant, report: dict[str, Any], address: str
) -> Path:
    """Save support report to a JSON file in the config directory."""
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    address_safe = address.replace(":", "").lower()
    filename = f"adjustable_bed_support_report_{address_safe}_{timestamp}.json"

    config_dir = Path(hass.config.config_dir)
    filepath = config_dir / filename

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str)

    _LOGGER.info("Support report saved to %s", filepath)
    return filepath
