"""Base entity classes for Adjustable Bed integration."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity

from .const import DOMAIN

if TYPE_CHECKING:
    from .coordinator import AdjustableBedCoordinator


class AdjustableBedEntity(Entity):
    """Base class for Adjustable Bed entities."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: AdjustableBedCoordinator) -> None:
        """Initialize the entity."""
        self._coordinator = coordinator
        self._attr_device_info = coordinator.device_info

    @property
    def available(self) -> bool:
        """Return True if entity is available.

        Entities are available when the bed is currently connected.
        This provides accurate availability feedback in the Home Assistant UI.
        """
        return self._coordinator.is_connected

