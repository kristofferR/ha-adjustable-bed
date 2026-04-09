"""Combined support bundle generation for Adjustable Bed."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.loader import async_get_integration

from .ble_diagnostics import BLEDiagnosticRunner
from .const import DOMAIN, SUPPORTED_BED_TYPES
from .redaction import redact_pins_only
from .support_report import (
    _get_bluetooth_info,
    _get_connection_info,
    _get_controller_info,
    _get_integration_info,
    _get_recent_logs,
    _get_system_info,
)

_LOGGER = logging.getLogger(__name__)


async def generate_support_bundle(
    hass: HomeAssistant,
    *,
    address: str,
    capture_duration: int,
    include_logs: bool,
    coordinator: Any | None = None,
    entry: ConfigEntry | None = None,
    device_id: str | None = None,
) -> dict[str, Any]:
    """Generate a single combined support bundle."""
    timestamp = datetime.now(UTC)
    integration = await async_get_integration(hass, DOMAIN)
    integration_version = str(integration.version) if integration.version is not None else "unknown"

    diagnostics_report = await BLEDiagnosticRunner(
        hass,
        address,
        capture_duration=capture_duration,
        coordinator=coordinator,
    ).run_diagnostics()

    bluetooth_info = await _build_bluetooth_section(
        hass,
        address,
        diagnostics_report.to_dict(),
        coordinator,
    )

    if coordinator is not None:
        connection = _get_connection_info(coordinator)
        connection_history = coordinator.connection_history
        adapter = coordinator.adapter_details
        controller = _get_controller_info(coordinator)
        position_data = dict(coordinator.position_data)
    else:
        connection = _build_connection_info_from_diagnostics(diagnostics_report.to_dict())
        connection_history = {}
        adapter = _build_raw_adapter_info(diagnostics_report.to_dict())
        controller = {"initialized": False, "class": None, "characteristic_uuid": None}
        position_data = {}

    report: dict[str, Any] = {
        "metadata": {
            "report_version": "2.0",
            "generated_at": timestamp.isoformat(),
            "capture_duration_seconds": capture_duration,
            "integration_domain": DOMAIN,
        },
        "target": {
            "mode": "configured_device" if entry is not None else "target_address",
            "address": address,
            "device_id": device_id,
            "entry_id": entry.entry_id if entry is not None else None,
            "title": entry.title if entry is not None else None,
        },
        "system": _get_system_info(hass, integration_version),
        "integration": _get_integration_info(entry) if entry is not None else _empty_integration_info(address),
        "device": diagnostics_report.device,
        "detection": diagnostics_report.detection,
        "connection": connection,
        "connection_history": connection_history,
        "connection_attempt_details": diagnostics_report.connection_attempt_details,
        "adapter": adapter,
        "bluetooth": bluetooth_info,
        "gatt_services": diagnostics_report.gatt_services,
        "gatt_summary": diagnostics_report.gatt_summary,
        "device_information": diagnostics_report.device_information,
        "controller": controller,
        "position_data": position_data,
        "notifications": diagnostics_report.notifications,
        "notification_summary": diagnostics_report.notification_summary,
        "command_trace": diagnostics_report.command_trace if coordinator is not None else [],
        "recent_logs": _get_recent_logs() if include_logs else [],
        "supported_bed_types": list(SUPPORTED_BED_TYPES),
        "errors": list(diagnostics_report.errors),
    }

    return redact_pins_only(report)  # type: ignore[no-any-return]


async def _build_bluetooth_section(
    hass: HomeAssistant,
    address: str,
    diagnostics_report: dict[str, Any],
    coordinator: Any | None,
) -> dict[str, Any]:
    """Build the support bundle Bluetooth section."""
    info: dict[str, Any]
    if coordinator is not None:
        info = await _get_bluetooth_info(hass, coordinator)
    else:
        info = {"last_advertisement": None, "scanners": []}

    info["last_advertisement"] = diagnostics_report.get("advertisement")
    info["advertisements_by_source"] = diagnostics_report.get("advertisements_by_source", [])
    info["scanner_count"] = diagnostics_report.get("device", {}).get("scanner_count")
    info["visible_sources"] = diagnostics_report.get("device", {}).get("visible_sources", [])
    info["selected_source"] = diagnostics_report.get("device", {}).get("selected_source")
    info["actual_source"] = diagnostics_report.get("device", {}).get("actual_source")
    info["non_connectable_fallback_used"] = diagnostics_report.get("device", {}).get(
        "non_connectable_fallback_used"
    )
    info["target_address"] = address

    if "scanners" not in info or not info["scanners"]:
        try:
            scanners = bluetooth.async_current_scanners(hass)
            info["scanners"] = [
                {
                    "source": getattr(scanner, "source", "unknown"),
                    "name": getattr(scanner, "name", "unknown"),
                    "scanning": getattr(scanner, "scanning", None),
                }
                for scanner in scanners
            ]
        except Exception as err:
            info["scanners_error"] = str(err)

    return info


def _build_connection_info_from_diagnostics(diagnostics_report: dict[str, Any]) -> dict[str, Any]:
    """Build connection info for a raw-address run."""
    gatt_services = diagnostics_report.get("gatt_services", [])
    return {
        "is_connected": False,
        "is_connecting": False,
        "mtu_size": None,
        "services_discovered": len(gatt_services),
        "service_uuids": [uuid for service in gatt_services if (uuid := service.get("uuid")) is not None],
    }


def _build_raw_adapter_info(diagnostics_report: dict[str, Any]) -> dict[str, Any]:
    """Build adapter details for raw-address runs."""
    device = diagnostics_report.get("device", {})
    return {
        "preferred": "auto",
        "actual": device.get("actual_source"),
        "available": device.get("visible_sources", []),
    }


def _empty_integration_info(address: str) -> dict[str, Any]:
    """Return a standardized integration section for raw-address runs."""
    return {
        "entry_id": None,
        "version": None,
        "title": None,
        "bed_type": None,
        "protocol_variant": None,
        "motor_count": None,
        "has_massage": None,
        "disable_angle_sensing": None,
        "preferred_adapter": None,
        "address": address,
        "kaidi_room_id": None,
        "kaidi_target_vaddr": None,
        "kaidi_product_id": None,
        "kaidi_sofa_acu_no": None,
        "kaidi_adv_type": None,
        "kaidi_resolved_variant": None,
        "kaidi_variant_source": None,
        "configured_device": False,
    }


def save_support_bundle(hass: HomeAssistant, report: dict[str, Any], address: str) -> Path:
    """Save the support bundle to a JSON file in the config directory."""
    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    address_safe = address.replace(":", "").lower()
    filename = f"adjustable_bed_support_bundle_{address_safe}_{timestamp}.json"

    config_dir = Path(hass.config.config_dir)
    filepath = config_dir / filename

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str)

    _LOGGER.info("Support bundle saved to %s", filepath)
    return filepath
