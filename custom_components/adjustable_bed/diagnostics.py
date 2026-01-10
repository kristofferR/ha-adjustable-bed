"""Diagnostics support for Adjustable Bed integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant

from .const import (
    CONF_BED_TYPE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_HAS_MASSAGE,
    CONF_MOTOR_COUNT,
    CONF_PREFERRED_ADAPTER,
    CONF_PROTOCOL_VARIANT,
    DOMAIN,
)
from .coordinator import AdjustableBedCoordinator

# Keys to redact from diagnostics (privacy-sensitive data)
TO_REDACT = {CONF_ADDRESS, CONF_NAME, "address"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator: AdjustableBedCoordinator = hass.data[DOMAIN][entry.entry_id]

    # Get connection state
    is_connected = coordinator.is_connected
    client = coordinator.client

    # Get BLE device info if connected
    ble_info: dict[str, Any] = {"connected": is_connected}
    if client and is_connected:
        ble_info.update({
            "mtu_size": getattr(client, "mtu_size", None),
            "services_discovered": len(list(client.services)) if client.services else 0,
        })

        # Get service UUIDs (useful for debugging detection issues)
        if client.services:
            ble_info["service_uuids"] = [
                str(service.uuid) for service in client.services
            ]

    # Get controller info
    controller_info: dict[str, Any] = {"initialized": coordinator.controller is not None}
    if coordinator.controller:
        controller = coordinator.controller
        controller_info.update({
            "class": type(controller).__name__,
            "characteristic_uuid": controller.control_characteristic_uuid,
        })

        # Add variant info for controllers that have it
        if hasattr(controller, "_is_wilinke"):
            controller_info["richmat_is_wilinke"] = controller._is_wilinke
        if hasattr(controller, "_variant"):
            controller_info["variant"] = controller._variant
        if hasattr(controller, "_char_uuid"):
            controller_info["char_uuid"] = controller._char_uuid

    # Get position data
    position_data = dict(coordinator.position_data)

    return {
        "entry": {
            "entry_id": entry.entry_id,
            "version": entry.version,
            "title": entry.title,
            "data": async_redact_data(dict(entry.data), TO_REDACT),
        },
        "config": {
            "bed_type": entry.data.get(CONF_BED_TYPE),
            "protocol_variant": entry.data.get(CONF_PROTOCOL_VARIANT, "auto"),
            "motor_count": entry.data.get(CONF_MOTOR_COUNT),
            "has_massage": entry.data.get(CONF_HAS_MASSAGE),
            "disable_angle_sensing": entry.data.get(CONF_DISABLE_ANGLE_SENSING),
            "preferred_adapter": entry.data.get(CONF_PREFERRED_ADAPTER),
        },
        "coordinator": {
            "is_connected": is_connected,
            "is_connecting": coordinator.is_connecting,
        },
        "ble": ble_info,
        "controller": controller_info,
        "position_data": position_data,
        "supported_bed_types": [
            "linak",
            "richmat (nordic/wilinke)",
            "keeson (base/ksbt)",
            "solace",
            "motosleep",
            "leggett_platt (gen2/okin)",
            "reverie",
            "okimat",
        ],
    }
