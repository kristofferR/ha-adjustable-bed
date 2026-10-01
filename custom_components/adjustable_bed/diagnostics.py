"""Diagnostics support for Adjustable Bed integration."""

from __future__ import annotations

import sys
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS
from homeassistant.const import __version__ as HA_VERSION
from homeassistant.core import HomeAssistant
from homeassistant.loader import async_get_integration

from .adapter import find_service_info_by_address
from .bluetooth_diagnostics import connection_reachability
from .const import (
    BED_TYPE_VIBRADORM_APP,
    BED_TYPE_VMATBASIC,
    CONF_BED_TYPE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_HAS_MASSAGE,
    CONF_KAIDI_ADV_TYPE,
    CONF_KAIDI_PRODUCT_ID,
    CONF_KAIDI_RESOLVED_VARIANT,
    CONF_KAIDI_ROOM_ID,
    CONF_KAIDI_SOFA_ACU_NO,
    CONF_KAIDI_TARGET_VADDR,
    CONF_KAIDI_VARIANT_SOURCE,
    CONF_MOTOR_COUNT,
    CONF_PAIR_ID,
    CONF_PREFERRED_ADAPTER,
    CONF_PROTOCOL_VARIANT,
    DOMAIN,
    SUPPORTED_BED_TYPES,
)
from .coordinator import AdjustableBedCoordinator
from .diagnostics_utils import get_gatt_summary
from .discovery_log import async_get_discovery_log
from .discovery_settings import async_is_discovery_disabled
from .kaidi_protocol import extract_kaidi_advertisement, kaidi_advertisement_to_dict
from .paired_coordinator import PairedBedCoordinator
from .redaction import redact_data
from .vibradorm_app_discovery import manufacturer_discovery_diagnostics
from .vibradorm_vmat_discovery import vmat_manufacturer_diagnostics
from .vmatbasic_discovery import manufacturer_diagnostics as vmatbasic_manufacturer_diagnostics


def _normalize_ble_address(value: Any) -> str | None:
    """Return a comparable BLE address string, if the value looks usable."""
    if not isinstance(value, str):
        return None
    normalized = value.strip().upper().replace("-", ":")
    return normalized or None


def _config_entry_addresses(entry: ConfigEntry) -> set[str]:
    """Return BLE addresses that are owned by this config entry."""
    return {
        address
        for address in (
            _normalize_ble_address(entry.data.get(CONF_ADDRESS)),
            _normalize_ble_address(entry.unique_id),
        )
        if address is not None
    }


async def _async_paired_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry, coordinator: PairedBedCoordinator
) -> dict[str, Any]:
    """Aggregate diagnostics for a paired (Dual Bed 4.0) entry, per side."""
    integration = await async_get_integration(hass, DOMAIN)

    sides: dict[str, Any] = {}
    for side, child in coordinator.children.items():
        child_controller = child.controller
        sides[side] = {
            "address": getattr(child, "address", None),
            "connected": child.is_connected,
            "reachability": connection_reachability(hass, child.address),
            "controller_type": (
                type(child_controller).__name__
                if child_controller is not None
                else None
            ),
            "position_data": getattr(child, "position_data", None),
            "command_timing": child.command_timing,
            "config": dict(child.entry.data),
        }
        if child.bed_type in {BED_TYPE_VIBRADORM_APP, BED_TYPE_VMATBASIC}:
            service_info, connectable = find_service_info_by_address(
                hass, child.address, allow_non_connectable=True
            )
            discovery_key = "vmatbasic_discovery" if child.bed_type == BED_TYPE_VMATBASIC else "vibradorm_app_discovery"
            discovery_parser = vmatbasic_manufacturer_diagnostics if child.bed_type == BED_TYPE_VMATBASIC else manufacturer_discovery_diagnostics
            sides[side]["advertisement"] = {
                "available": service_info is not None,
                "connectable": connectable,
                "service_uuids": list(service_info.service_uuids) if service_info else [],
                discovery_key: discovery_parser(
                    service_info.manufacturer_data if service_info else {}
                ),
            }
            if child.entry.data.get("vibradorm_app_profile") == "vmat":
                sides[side]["advertisement"]["vmat_discovery"] = vmat_manufacturer_diagnostics(
                    service_info.manufacturer_data if service_info else {}
                )

    data: dict[str, Any] = {
        "integration_version": integration.version,
        "ha_version": HA_VERSION,
        "python_version": sys.version,
        "paired": True,
        "pair_id": entry.data.get(CONF_PAIR_ID),
        "name": coordinator.name,
        "connection_mode": getattr(coordinator, "connection_mode", None),
        "is_connected": coordinator.is_connected,
        "config_entry": {
            "title": entry.title,
            "version": entry.version,
            "data": dict(entry.data),
            "options": dict(entry.options),
        },
        "sides": sides,
    }
    return redact_data(data)


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    stored = hass.data[DOMAIN][entry.entry_id]
    if isinstance(stored, PairedBedCoordinator):
        # A paired entry stores a PairedBedCoordinator, which has no client /
        # controller / position_data — aggregate per side instead of crashing.
        return await _async_paired_diagnostics(hass, entry, stored)
    coordinator: AdjustableBedCoordinator = stored

    # Get integration version from manifest
    integration = await async_get_integration(hass, DOMAIN)
    integration_version = integration.version

    # Get connection state
    is_connected = coordinator.is_connected
    client = coordinator.client

    # Get BLE device info if connected
    ble_info: dict[str, Any] = {"connected": is_connected}
    if client and is_connected:
        ble_info.update(
            {
                "mtu_size": getattr(client, "mtu_size", None),
                "services_discovered": len(list(client.services)) if client.services else 0,
            }
        )

        # Get service UUIDs (useful for debugging detection issues)
        if client.services:
            ble_info["service_uuids"] = [str(service.uuid) for service in client.services]

    # Get controller info
    controller_info: dict[str, Any] = {"initialized": coordinator.controller is not None}
    if coordinator.controller:
        controller = coordinator.controller
        controller_info.update(
            {
                "class": type(controller).__name__,
                "characteristic_uuid": controller.control_characteristic_uuid,
            }
        )

        # Add variant info for controllers that have it
        is_wilinke = getattr(controller, "_is_wilinke", None)
        if is_wilinke is not None:
            controller_info["richmat_is_wilinke"] = is_wilinke
        variant = getattr(controller, "_variant", None)
        if variant is not None:
            controller_info["variant"] = variant
        variant_source = getattr(controller, "_variant_source", None)
        if variant_source is not None:
            controller_info["variant_source"] = variant_source
        char_uuid = getattr(controller, "_char_uuid", None)
        if char_uuid is not None:
            controller_info["char_uuid"] = char_uuid

        # Add Octo-specific discovered features
        discovered_motor_count = getattr(controller, "discovered_motor_count", None)
        if discovered_motor_count is not None:
            controller_info["discovered_motor_count"] = discovered_motor_count
        supports_synchro = getattr(controller, "supports_synchro", None)
        if supports_synchro is not None:
            controller_info["supports_synchro"] = supports_synchro
        is_synchro_active = getattr(controller, "is_synchro_active", None)
        if is_synchro_active is not None:
            controller_info["synchro_active"] = is_synchro_active

        # Whatever the connect-time protocol handshake resolved to (capabilities,
        # authentication state, ...). Empty for controllers with no handshake.
        protocol_state = controller.protocol_diagnostics
        if protocol_state:
            controller_info["protocol_state"] = protocol_state

    # Get position data
    position_data = dict(coordinator.position_data)

    # Get advertisement data
    advertisement_info: dict[str, Any] = {}
    service_info, service_info_connectable = find_service_info_by_address(
        hass,
        coordinator.address,
        allow_non_connectable=True,
    )
    if service_info:
        advertisement_info = {
            # Use "device_name" to avoid redaction (name is useful for debugging)
            "device_name": service_info.name,
            "rssi": getattr(service_info, "rssi", None),
            "service_uuids": (
                [str(uuid) for uuid in service_info.service_uuids]
                if service_info.service_uuids
                else []
            ),
            "manufacturer_data_keys": (
                list(service_info.manufacturer_data.keys())
                if service_info.manufacturer_data
                else []
            ),
            "connectable": service_info_connectable,
        }
        kaidi_advertisement = extract_kaidi_advertisement(service_info.manufacturer_data)
        if kaidi_advertisement is not None:
            advertisement_info["kaidi"] = kaidi_advertisement_to_dict(kaidi_advertisement)
        if hasattr(service_info, "source"):
            advertisement_info["source"] = service_info.source

    if coordinator.bed_type == BED_TYPE_VIBRADORM_APP:
        advertisement_info["vibradorm_app_discovery"] = manufacturer_discovery_diagnostics(
            service_info.manufacturer_data if service_info else {}
        )
        advertisement_info["available"] = service_info is not None
        if entry.data.get("vibradorm_app_profile") == "vmat":
            advertisement_info["vmat_discovery"] = vmat_manufacturer_diagnostics(
                service_info.manufacturer_data if service_info else {}
            )
    if coordinator.bed_type == BED_TYPE_VMATBASIC:
        advertisement_info["vmatbasic_discovery"] = vmatbasic_manufacturer_diagnostics(
            service_info.manufacturer_data if service_info else {}
        )
        advertisement_info["available"] = service_info is not None

    # Include only auto-detections tied to this config entry. The backing log is
    # global, so exposing it wholesale would leak unrelated nearby BLE devices.
    entry_addresses = _config_entry_addresses(entry)
    discovery_log = [
        record
        for record in await async_get_discovery_log(hass).async_all()
        if _normalize_ble_address(record.get("address")) in entry_addresses
    ]
    auto_discovery_log = [
        {
            "detected_at": record["detected_at"],
            "address": record["address"],
            "service_uuids": record["service_uuids"],
            "manufacturer_data": record["manufacturer_data"],
            "bed_type": record["bed_type"],
            "confidence": record["confidence"],
            "signals": record["signals"],
        }
        for record in discovery_log
    ]

    # Build the diagnostic data
    data = {
        "system": {
            "integration_version": integration_version,
            "home_assistant_version": HA_VERSION,
            "python_version": sys.version.split()[0],
        },
        "entry": {
            "entry_id": entry.entry_id,
            "version": entry.version,
            "title": entry.title,
            "data": dict(entry.data),
        },
        "config": {
            "bed_type": entry.data.get(CONF_BED_TYPE),
            "protocol_variant": entry.data.get(CONF_PROTOCOL_VARIANT, "auto"),
            "motor_count": entry.data.get(CONF_MOTOR_COUNT),
            "has_massage": entry.data.get(CONF_HAS_MASSAGE),
            "disable_angle_sensing": entry.data.get(CONF_DISABLE_ANGLE_SENSING),
            "preferred_adapter": entry.data.get(CONF_PREFERRED_ADAPTER),
            "kaidi_room_id": entry.data.get(CONF_KAIDI_ROOM_ID),
            "kaidi_target_vaddr": entry.data.get(CONF_KAIDI_TARGET_VADDR),
            "kaidi_product_id": entry.data.get(CONF_KAIDI_PRODUCT_ID),
            "kaidi_sofa_acu_no": entry.data.get(CONF_KAIDI_SOFA_ACU_NO),
            "kaidi_adv_type": entry.data.get(CONF_KAIDI_ADV_TYPE),
            "kaidi_resolved_variant": entry.data.get(CONF_KAIDI_RESOLVED_VARIANT),
            "kaidi_variant_source": entry.data.get(CONF_KAIDI_VARIANT_SOURCE),
        },
        "coordinator": {
            "is_connected": is_connected,
            "is_connecting": coordinator.is_connecting,
            "connection_history": coordinator.connection_history,
            "adapter_details": coordinator.adapter_details,
            "command_timing": coordinator.command_timing,
        },
        "pairing": coordinator.pairing_diagnostics,
        "ble": ble_info,
        "gatt_summary": get_gatt_summary(coordinator),
        "advertisement": advertisement_info,
        "controller": controller_info,
        "position_data": position_data,
        "supported_bed_types": list(SUPPORTED_BED_TYPES),
        "auto_discovery_disabled": await async_is_discovery_disabled(hass),
        "auto_discovery_log": auto_discovery_log,
    }

    data["reachability"] = connection_reachability(hass, coordinator.address) if coordinator else None

    # Redact sensitive data (partial MAC redaction - keeps OUI for debugging)
    return redact_data(data)  # type: ignore[no-any-return]
