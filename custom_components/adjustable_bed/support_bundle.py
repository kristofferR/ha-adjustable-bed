"""Combined support bundle generation for Adjustable Bed."""

from __future__ import annotations

import inspect
import json
import logging
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any

from homeassistant.components import bluetooth
from homeassistant.components.bluetooth.const import (
    CONF_SOURCE_CONFIG_ENTRY_ID,
    CONF_SOURCE_DEVICE_ID,
    CONF_SOURCE_DOMAIN,
    CONF_SOURCE_MODEL,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_SOURCE
from homeassistant.core import HomeAssistant
from homeassistant.loader import async_get_integration

from .adapter import RSSI_UNAVAILABLE, get_discovered_service_info
from .ble_auth import is_ble_authentication_error
from .ble_diagnostics import BLEDiagnosticRunner
from .const import (
    ADAPTER_AUTO,
    CONF_BED_TYPE,
    CONF_BLE_BOND_ESTABLISHED,
    CONF_PREFERRED_ADAPTER,
    CONF_PROTOCOL_VARIANT,
    DEVICE_INFO_CHARS,
    DOMAIN,
    SUPPORTED_BED_TYPES,
    requires_pairing,
)
from .detection import detect_bed_type_detailed
from .diagnostic_payloads import format_mapping_payloads
from .redaction import redact_pins_only
from .support_report import (
    _get_bluetooth_info,
    _get_connection_info,
    _get_controller_info,
    _get_integration_info,
    _get_pairing_info,
    _get_recent_logs,
    _get_system_info,
)

_LOGGER = logging.getLogger(__name__)

_REPORT_VERSION = "2.2"
_MAX_NEARBY_BLUETOOTH_DEVICES = 30
_BLUETOOTH_DOMAIN = "bluetooth"
_ESPHOME_DOMAIN = "esphome"
_ESPHOME_PAIRING_FEATURE_FLAG = 1 << 3
_OMITTED_SCANNER_DIAGNOSTIC_FRAGMENTS = (
    "advertisement",
    "discovered_device",
    "history",
)


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
    pre_capture_command_trace = (
        list(coordinator.command_trace) if coordinator is not None else []
    )
    reproduction_command_trace = [
        trace
        for trace in pre_capture_command_trace
        if trace.get("operation_name") == "command"
    ]

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

    recent_logs = await _get_recent_logs(hass) if include_logs else []
    diagnostic_dict = diagnostics_report.to_dict()
    pairing = _build_pairing_assessment(
        diagnostic_dict,
        entry=entry,
        coordinator=coordinator,
    )
    evidence = _build_evidence_summary(
        capture_duration=capture_duration,
        include_logs=include_logs,
        recent_logs=recent_logs,
        diagnostic_report=diagnostic_dict,
        reproduction_command_trace=reproduction_command_trace,
        pairing=pairing,
        bluetooth_info=bluetooth_info,
        configured=entry is not None,
        controller=controller,
    )

    report: dict[str, Any] = {
        "metadata": {
            "report_version": _REPORT_VERSION,
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
        "pairing": pairing,
        "gatt_services": diagnostics_report.gatt_services,
        "gatt_summary": diagnostics_report.gatt_summary,
        "device_information": diagnostics_report.device_information,
        "controller": controller,
        "position_data": position_data,
        "notifications": diagnostics_report.notifications,
        "notification_summary": diagnostics_report.notification_summary,
        "command_trace": diagnostics_report.command_trace if coordinator is not None else [],
        "recent_logs": recent_logs,
        "evidence": evidence,
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

    try:
        info["nearby_devices"] = _build_nearby_device_inventory(hass, address)
    except Exception as err:  # noqa: BLE001 - diagnostics must degrade gracefully
        info["nearby_devices_error"] = str(err)

    try:
        info["scanners"] = await _build_scanner_status(
            hass,
            diagnostics_report.get("advertisements_by_source", []),
        )
    except Exception as err:  # noqa: BLE001 - diagnostics must degrade gracefully
        info["scanners_error"] = str(err)

    return info


def _build_nearby_device_inventory(
    hass: HomeAssistant,
    target_address: str,
    *,
    limit: int = _MAX_NEARBY_BLUETOOTH_DEVICES,
) -> dict[str, Any]:
    """Return a ranked, bounded inventory of nearby Bluetooth devices."""
    grouped: dict[str, list[Any]] = {}
    for service_info in get_discovered_service_info(
        hass,
        include_non_connectable=True,
    ):
        address = str(getattr(service_info, "address", "")).upper()
        if not address:
            continue
        grouped.setdefault(address, []).append(service_info)

    devices: list[dict[str, Any]] = []
    normalized_target = target_address.upper()
    for snapshots in grouped.values():
        candidates = [
            _nearby_device_snapshot(service_info, normalized_target) for service_info in snapshots
        ]
        best = max(candidates, key=_nearby_device_priority)
        sources = sorted(
            (
                {
                    "source": candidate["source"],
                    "rssi": candidate["rssi"],
                    "connectable": candidate["connectable"],
                }
                for candidate in candidates
            ),
            key=lambda source: (
                not source["connectable"],
                -(source["rssi"] if isinstance(source["rssi"], int) else RSSI_UNAVAILABLE),
                source["source"] or "",
            ),
        )
        best["sources"] = sources
        best["source_count"] = len(sources)
        devices.append(best)

    devices.sort(key=_nearby_device_sort_key)
    included = devices[: max(0, limit)]
    for rank, device in enumerate(included, start=1):
        device["rank"] = rank

    return {
        "limit": limit,
        "total_visible": len(devices),
        "included": len(included),
        "truncated": len(devices) > len(included),
        "ranking": [
            "supported_bed_match",
            "detection_confidence",
            "connectable",
            "rssi",
        ],
        "privacy_note": (
            "Contains Bluetooth names and addresses visible to Home Assistant "
            "when the bundle was generated."
        ),
        "devices": included,
    }


def _nearby_device_snapshot(
    service_info: Any,
    target_address: str,
) -> dict[str, Any]:
    """Serialize one nearby advertisement with detection evidence."""
    try:
        detection = detect_bed_type_detailed(service_info)
        bed_type = detection.bed_type
        detection_info: dict[str, Any] = {
            "bed_type": bed_type,
            "confidence": detection.confidence,
            "signals": list(detection.signals),
            "ambiguous_types": list(detection.ambiguous_types or []),
            "supported_match": bed_type in SUPPORTED_BED_TYPES if bed_type else False,
        }
    except Exception as err:  # noqa: BLE001 - one malformed advertisement must not abort a bundle
        detection_info = {
            "bed_type": None,
            "confidence": 0.0,
            "signals": [],
            "ambiguous_types": [],
            "supported_match": False,
            "error": str(err),
        }

    raw_rssi = getattr(service_info, "rssi", None)
    rssi = raw_rssi if isinstance(raw_rssi, int) else None
    raw_name = getattr(service_info, "name", None)
    name = raw_name if isinstance(raw_name, str) else None
    raw_source = getattr(service_info, "source", None)
    source = raw_source if isinstance(raw_source, str) else None
    service_uuids = getattr(service_info, "service_uuids", None) or []
    manufacturer_data = getattr(service_info, "manufacturer_data", None)
    service_data = getattr(service_info, "service_data", None)
    address = str(getattr(service_info, "address", "")).upper()

    return {
        "address": address,
        "name": name,
        "rssi": rssi,
        "source": source,
        "connectable": bool(getattr(service_info, "connectable", True)),
        "is_target": address == target_address,
        "service_uuids": sorted(str(uuid).lower() for uuid in service_uuids),
        "manufacturer_data": format_mapping_payloads(
            manufacturer_data if isinstance(manufacturer_data, dict) else None
        ),
        "service_data": format_mapping_payloads(
            service_data if isinstance(service_data, dict) else None
        ),
        "detection": detection_info,
    }


def _nearby_device_priority(device: dict[str, Any]) -> tuple[bool, float, bool, int]:
    """Return the descending priority tuple for one nearby device snapshot."""
    detection = device["detection"]
    rssi = device["rssi"] if isinstance(device["rssi"], int) else RSSI_UNAVAILABLE
    return (
        bool(detection["supported_match"]),
        float(detection["confidence"]),
        bool(device["connectable"]),
        rssi,
    )


def _nearby_device_sort_key(device: dict[str, Any]) -> tuple[Any, ...]:
    """Return a stable ascending key with likely and strong devices first."""
    supported, confidence, connectable, rssi = _nearby_device_priority(device)
    return (
        not supported,
        -confidence,
        not connectable,
        -rssi,
        (device["name"] or "").lower(),
        device["address"],
    )


async def _build_scanner_status(
    hass: HomeAssistant,
    advertisements_by_source: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return enriched status for local adapters and remote Bluetooth proxies."""
    advertisements = {
        row.get("source"): row
        for row in advertisements_by_source
        if isinstance(row, dict) and row.get("source")
    }
    registrations = {
        entry.data.get(CONF_SOURCE): entry
        for entry in hass.config_entries.async_entries(_BLUETOOTH_DOMAIN)
        if entry.data.get(CONF_SOURCE)
    }

    rows: list[dict[str, Any]] = []
    for scanner in bluetooth.async_current_scanners(hass):
        source = str(getattr(scanner, "source", "unknown"))
        connector = getattr(scanner, "connector", None)
        registration = registrations.get(source)
        registration_data = registration.data if registration is not None else {}
        source_domain = registration_data.get(CONF_SOURCE_DOMAIN)
        target = advertisements.get(source)

        row: dict[str, Any] = {
            "source": source,
            "name": getattr(scanner, "name", "unknown"),
            "scanner_class": type(scanner).__name__,
            "scanner_type": _scanner_type(source_domain, connector),
            "source_domain": source_domain,
            "source_model": registration_data.get(CONF_SOURCE_MODEL),
            "scanning": getattr(scanner, "scanning", None),
            "connectable": getattr(scanner, "connectable", None),
            "connector": type(connector).__name__ if connector is not None else None,
            "current_mode": _simple_value(getattr(scanner, "current_mode", None)),
            "requested_mode": _simple_value(getattr(scanner, "requested_mode", None)),
            "connecting_count": getattr(scanner, "connecting_count", None),
            "connections_in_progress": getattr(scanner, "connections_in_progress", None),
            "connection_failures": _json_friendly(
                getattr(scanner, "connection_failures", None)
            ),
            "target_visible": target is not None,
            "target_rssi": target.get("rssi") if target else None,
            "target_connectable": target.get("connectable") if target else None,
            "selected_for_connection": bool(
                target and target.get("selected_for_connection")
            ),
        }

        details = getattr(scanner, "details", None)
        if isinstance(details, dict):
            row["details"] = _json_friendly(details)

        diagnostics_method = getattr(scanner, "async_diagnostics", None)
        if callable(diagnostics_method):
            try:
                scanner_diagnostics = diagnostics_method()
                if inspect.isawaitable(scanner_diagnostics):
                    scanner_diagnostics = await scanner_diagnostics
                if isinstance(scanner_diagnostics, dict):
                    row["diagnostics"] = _compact_scanner_diagnostics(
                        scanner_diagnostics
                    )
            except Exception as err:  # noqa: BLE001
                row["diagnostics_error"] = str(err)

        if registration is not None:
            row["bluetooth_registration"] = {
                "entry_id": registration.entry_id,
                "entry_state": _simple_value(registration.state),
                "source_config_entry_id": registration_data.get(
                    CONF_SOURCE_CONFIG_ENTRY_ID
                ),
                "source_device_id": registration_data.get(CONF_SOURCE_DEVICE_ID),
            }

        if source_domain == _ESPHOME_DOMAIN:
            row["esphome_proxy"] = _build_esphome_proxy_status(
                hass,
                registration_data.get(CONF_SOURCE_CONFIG_ENTRY_ID),
            )

        rows.append(row)

    rows.sort(key=lambda row: (not row["selected_for_connection"], row["source"]))
    return rows


def _scanner_type(source_domain: Any, connector: Any) -> str:
    """Classify a scanner without depending on optional integration modules."""
    if source_domain == _ESPHOME_DOMAIN:
        return "esphome_proxy"
    if source_domain:
        return "remote_proxy"
    if connector is not None and "remote" in type(connector).__name__.lower():
        return "remote_proxy"
    return "local_adapter"


def _build_esphome_proxy_status(
    hass: HomeAssistant,
    source_config_entry_id: Any,
) -> dict[str, Any]:
    """Return ESPHome runtime and Bluetooth slot status when HA exposes it."""
    status: dict[str, Any] = {
        "config_entry_id": source_config_entry_id,
        "entry_found": False,
    }
    if not isinstance(source_config_entry_id, str):
        return status

    entry = hass.config_entries.async_get_entry(source_config_entry_id)
    if entry is None:
        return status

    status.update(
        {
            "entry_found": True,
            "title": entry.title,
            "entry_state": _simple_value(entry.state),
            "disabled_by": _simple_value(entry.disabled_by),
        }
    )

    try:
        runtime = entry.runtime_data
    except (AttributeError, RuntimeError):
        runtime = None
    if runtime is None:
        status["runtime_data_available"] = False
        return status

    status["runtime_data_available"] = True
    status["available"] = getattr(runtime, "available", None)
    status["api_version"] = _api_version(getattr(runtime, "api_version", None))

    device_info = getattr(runtime, "device_info", None)
    if device_info is not None:
        raw_feature_flags = getattr(
            device_info, "bluetooth_proxy_feature_flags", None
        )
        feature_flags = raw_feature_flags
        feature_flags_compat = getattr(
            device_info, "bluetooth_proxy_feature_flags_compat", None
        )
        if callable(feature_flags_compat):
            try:
                feature_flags = feature_flags_compat(
                    getattr(runtime, "api_version", None)
                )
            except Exception:  # noqa: BLE001 - raw flags still provide useful evidence
                pass
        status["device"] = {
            "name": getattr(device_info, "name", None),
            "friendly_name": getattr(device_info, "friendly_name", None),
            "model": getattr(device_info, "model", None),
            "manufacturer": getattr(device_info, "manufacturer", None),
            "esphome_version": getattr(device_info, "esphome_version", None),
            "compilation_time": getattr(device_info, "compilation_time", None),
            "project_name": getattr(device_info, "project_name", None),
            "project_version": getattr(device_info, "project_version", None),
            "bluetooth_mac_address": getattr(
                device_info, "bluetooth_mac_address", None
            ),
            "bluetooth_proxy_feature_flags": raw_feature_flags,
            "bluetooth_proxy_feature_flags_effective": _simple_value(feature_flags),
            "pairing_supported": (
                bool(feature_flags & _ESPHOME_PAIRING_FEATURE_FLAG)
                if isinstance(feature_flags, int)
                else None
            ),
        }

    bluetooth_device = getattr(runtime, "bluetooth_device", None)
    if bluetooth_device is not None:
        status["bluetooth"] = {
            "available": getattr(bluetooth_device, "available", None),
            "connections_free": getattr(
                bluetooth_device, "ble_connections_free", None
            ),
            "connections_limit": getattr(
                bluetooth_device, "ble_connections_limit", None
            ),
        }

    return status


def _build_pairing_assessment(
    diagnostics_report: dict[str, Any],
    *,
    entry: ConfigEntry | None,
    coordinator: Any | None,
) -> dict[str, Any]:
    """Turn raw GATT authentication evidence into a clear pairing verdict."""
    detection = diagnostics_report.get("detection", {})
    bed_type = (
        entry.data.get(CONF_BED_TYPE)
        if entry is not None
        else detection.get("bed_type")
    )
    protocol_variant = (
        entry.data.get(CONF_PROTOCOL_VARIANT)
        if entry is not None
        else None
    )
    pairing_required = bool(bed_type and requires_pairing(bed_type, protocol_variant))
    probe_uuids = {uuid.lower() for uuid in DEVICE_INFO_CHARS.values()}
    successful_probes: list[str] = []
    authentication_errors: list[dict[str, Any]] = []

    for service in diagnostics_report.get("gatt_services", []):
        for characteristic in service.get("characteristics", []):
            uuid = str(characteristic.get("uuid", "")).lower()
            read_error = characteristic.get("read_error")
            if isinstance(read_error, str) and is_ble_authentication_error(
                Exception(read_error)
            ):
                authentication_errors.append(
                    {
                        "uuid": characteristic.get("uuid"),
                        "handle": characteristic.get("handle"),
                        "error": read_error,
                    }
                )
            if uuid in probe_uuids and characteristic.get("read_result") is not None:
                successful_probes.append(characteristic.get("uuid"))

    if authentication_errors:
        status = "authentication_failed"
    elif not pairing_required:
        status = "not_required"
    elif successful_probes:
        status = "verified"
    else:
        status = "unverified"

    saved_bond = (
        entry.data.get(CONF_BLE_BOND_ESTABLISHED) if entry is not None else None
    )
    pairing_supported = getattr(coordinator, "pairing_supported", None)
    if not isinstance(pairing_supported, bool):
        pairing_supported = None

    device = diagnostics_report.get("device", {})
    preferred = (
        entry.data.get(CONF_PREFERRED_ADAPTER, ADAPTER_AUTO)
        if entry is not None
        else ADAPTER_AUTO
    )
    selected = device.get("selected_source")
    actual = device.get("actual_source")
    coordinator_pairing = getattr(coordinator, "pairing_diagnostics", None)
    base_pairing = _get_pairing_info(
        entry,
        coordinator if isinstance(coordinator_pairing, dict) else None,
        diagnostic_backend=device.get("pairing", {}),
    )

    return {
        **base_pairing,
        "required": pairing_required,
        "status": status,
        "bed_type": bed_type,
        "protocol_variant": protocol_variant,
        "configured_bond_marker": saved_bond,
        "configured_bond_conflicts_with_capture": bool(
            saved_bond is True and authentication_errors
        ),
        "coordinator_pairing_supported": pairing_supported,
        "backend_flags": device.get("pairing", {}),
        "auth_gated_probe": {
            "successful_characteristics": successful_probes,
            "authentication_errors": authentication_errors,
        },
        "source": {
            "preferred": preferred,
            "selected": selected,
            "actual": actual,
            "matches_preference": (
                None
                if not preferred or preferred == ADAPTER_AUTO or actual is None
                else actual == preferred
            ),
        },
    }

def _build_evidence_summary(
    *,
    capture_duration: int,
    include_logs: bool,
    recent_logs: list[dict[str, str]],
    diagnostic_report: dict[str, Any],
    reproduction_command_trace: list[dict[str, Any]],
    pairing: dict[str, Any],
    bluetooth_info: dict[str, Any],
    configured: bool,
    controller: dict[str, Any],
) -> dict[str, Any]:
    """Summarize whether the bundle contains enough evidence to act on."""
    command_count = len(diagnostic_report.get("command_trace", []))
    reproduction_command_count = len(reproduction_command_trace)
    notification_count = diagnostic_report.get("notification_summary", {}).get(
        "total_notifications", 0
    )
    log_capture_failed = bool(
        recent_logs
        and any(
            log.get("name") == DOMAIN
            and log.get("message", "").startswith("Could not read ")
            for log in recent_logs
        )
    )
    if not include_logs:
        log_status = "not_requested"
    elif log_capture_failed:
        log_status = "unavailable"
    elif recent_logs:
        log_status = "available"
    else:
        log_status = "empty"

    warnings: list[str] = []
    if configured and reproduction_command_count == 0:
        warnings.append(
            "No user command reproduction was captured. Retry at least one failed "
            "Home Assistant command before generating the bundle."
        )
    if capture_duration > 0 and not notification_count:
        warnings.append(
            "No BLE notifications were captured. Operate the physical remote during "
            "the capture window when protocol traffic is needed."
        )
    if log_status == "not_requested":
        warnings.append("Recent logs were not requested for this bundle.")
    elif log_status == "unavailable":
        warnings.append(
            "Home Assistant file logging was unavailable, so the reproduction log "
            "is missing."
        )
    elif log_status == "empty":
        warnings.append("No relevant Adjustable Bed or Bluetooth log entries were found.")
    if pairing.get("configured_bond_conflicts_with_capture"):
        warnings.append(
            "The saved bond marker says paired, but this capture observed an "
            "unauthenticated GATT link on the selected source."
        )
    if configured and not controller.get("initialized"):
        warnings.append("The controller was not initialized when the bundle was assembled.")

    selected_source = pairing.get("source", {}).get("actual") or pairing.get(
        "source", {}
    ).get("selected")
    for scanner in bluetooth_info.get("scanners", []):
        if scanner.get("source") != selected_source:
            continue
        proxy = scanner.get("esphome_proxy")
        if isinstance(proxy, dict) and proxy.get("available") is False:
            warnings.append("The selected ESPHome Bluetooth proxy reports unavailable.")
        bluetooth_status = proxy.get("bluetooth", {}) if isinstance(proxy, dict) else {}
        if bluetooth_status.get("connections_free") == 0:
            warnings.append("The selected ESPHome proxy has no free BLE connection slots.")

    return {
        "command_trace_count": command_count,
        "reproduction_command_trace_count": reproduction_command_count,
        "non_reproduction_command_trace_count": max(
            0, command_count - reproduction_command_count
        ),
        "notification_count": notification_count,
        "log_capture_status": log_status,
        "recent_log_entry_count": len(recent_logs),
        "usable_recent_log_entry_count": 0 if log_capture_failed else len(recent_logs),
        "pairing_status": pairing.get("status"),
        "complete": not warnings,
        "warnings": warnings,
    }


def _compact_scanner_diagnostics(value: dict[str, Any]) -> dict[str, Any]:
    """Drop large advertisement inventories while preserving scanner health."""
    return {
        str(key): _json_friendly(item)
        for key, item in value.items()
        if not any(
            fragment in str(key).lower()
            for fragment in _OMITTED_SCANNER_DIAGNOSTIC_FRAGMENTS
        )
    }


def _json_friendly(value: Any) -> Any:
    """Convert diagnostic values to stable JSON-friendly primitives."""
    if value is None or isinstance(value, bool | int | float | str):
        return value
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, bytes):
        return value.hex()
    if isinstance(value, dict):
        return {str(key): _json_friendly(item) for key, item in value.items()}
    if isinstance(value, list | tuple | set):
        return [_json_friendly(item) for item in value]
    return str(value)


def _simple_value(value: Any) -> Any:
    """Return the scalar value of enums used by Home Assistant APIs."""
    if isinstance(value, Enum):
        return value.value
    if value is None or isinstance(value, bool | int | float | str):
        return value
    return str(value)


def _api_version(value: Any) -> dict[str, int] | str | None:
    """Serialize an ESPHome API version without importing optional modules."""
    if value is None:
        return None
    major = getattr(value, "major", None)
    minor = getattr(value, "minor", None)
    if isinstance(major, int) and isinstance(minor, int):
        return {"major": major, "minor": minor}
    return str(value)


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
        "ble_bond_established": None,
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
