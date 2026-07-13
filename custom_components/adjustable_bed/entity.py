"""Base entity classes for Adjustable Bed integration."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.helpers.entity import Entity

if TYPE_CHECKING:
    from .coordinator import AdjustableBedCoordinator


class AdjustableBedEntity(Entity):
    """Base class for Adjustable Bed entities."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: AdjustableBedCoordinator) -> None:
        """Initialize the entity."""
        self._coordinator = coordinator
        self._attr_device_info = coordinator.device_info
        side = getattr(coordinator, "entity_side", None)
        if side is not None:
            self._attr_extra_state_attributes = {"bed_side": side}

    def _set_sided_translation_key(self, key: str | None, fallback: str) -> None:
        """Apply a logical-side suffix only for single-address paired views."""
        self._attr_translation_key = self._coordinator.entity_translation_key(
            key or fallback
        )

    @property
    def available(self) -> bool:
        """Return True if entity is available.

        For on-demand-connect devices like this bed, entities are always
        available since we reconnect when a command is sent. The connection
        state doesn't affect availability - only actual connection failures
        during command execution indicate a problem.
        """
        return True
