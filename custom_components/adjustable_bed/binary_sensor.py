"""Binary sensor entities for Adjustable Bed integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import AdjustableBedCoordinator
from .entity import AdjustableBedEntity


@dataclass(frozen=True, kw_only=True)
class AdjustableBedBinarySensorEntityDescription(BinarySensorEntityDescription):
    """Describes an Adjustable Bed binary sensor entity."""


BINARY_SENSOR_DESCRIPTIONS: tuple[AdjustableBedBinarySensorEntityDescription, ...] = (
    AdjustableBedBinarySensorEntityDescription(
        key="ble_connection",
        translation_key="ble_connection",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Adjustable Bed binary sensor entities."""
    coordinator: AdjustableBedCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities = [
        AdjustableBedConnectionSensor(coordinator, description)
        for description in BINARY_SENSOR_DESCRIPTIONS
    ]

    async_add_entities(entities)


class AdjustableBedConnectionSensor(AdjustableBedEntity, BinarySensorEntity):
    """Binary sensor entity for Adjustable Bed BLE connection state."""

    entity_description: AdjustableBedBinarySensorEntityDescription

    def __init__(
        self,
        coordinator: AdjustableBedCoordinator,
        description: AdjustableBedBinarySensorEntityDescription,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.address}_{description.key}"
        self._unregister_callback: Callable[[], None] | None = None

    async def async_added_to_hass(self) -> None:
        """Run when entity is added to hass."""
        await super().async_added_to_hass()
        self._unregister_callback = self._coordinator.register_connection_state_callback(
            self._handle_connection_state_change
        )

    async def async_will_remove_from_hass(self) -> None:
        """Run when entity is removed from hass."""
        if self._unregister_callback:
            self._unregister_callback()
        await super().async_will_remove_from_hass()

    @callback
    def _handle_connection_state_change(self, _connected: bool) -> None:
        """Handle connection state change."""
        self.async_write_ha_state()

    @property
    def is_on(self) -> bool:
        """Return True if the bed is connected."""
        return self._coordinator.is_connected

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes."""
        attrs: dict[str, Any] = {}

        # Last connected timestamp
        if self._coordinator.last_connected:
            attrs["last_connected"] = self._coordinator.last_connected.isoformat()

        # Last disconnected timestamp
        if self._coordinator.last_disconnected:
            attrs["last_disconnected"] = self._coordinator.last_disconnected.isoformat()

        # Connection source (adapter name)
        if self._coordinator.connection_source:
            attrs["connection_source"] = self._coordinator.connection_source

        # RSSI at connection time
        if self._coordinator.connection_rssi is not None:
            attrs["rssi"] = self._coordinator.connection_rssi

        # State detail for more granular status
        if self._coordinator.is_connecting:
            attrs["state_detail"] = "connecting"
        elif self._coordinator.is_connected:
            attrs["state_detail"] = "connected"
        else:
            attrs["state_detail"] = "disconnected"

        return attrs
