"""Base entity classes for Smart Bed integration."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity

from .const import DOMAIN

if TYPE_CHECKING:
    from .coordinator import SmartBedCoordinator


class SmartBedEntity(Entity):
    """Base class for Smart Bed entities."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: SmartBedCoordinator) -> None:
        """Initialize the entity."""
        self._coordinator = coordinator
        self._attr_device_info = coordinator.device_info

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return (
            self._coordinator.controller is not None
            and self._coordinator._client is not None
            and self._coordinator._client.is_connected
        )

