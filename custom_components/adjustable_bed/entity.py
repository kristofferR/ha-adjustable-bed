"""Base entity classes for Adjustable Bed integration."""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING

from homeassistant.helpers.entity import Entity

from .const import TIMED_MOVE_MOTOR_OPTIONS
from .execution import ExecutionCapabilities

if TYPE_CHECKING:
    from .beds.base import BedController, SideBoundController
    from .entity_runtime import EntityRuntime

# A renewable hold (#483) the card may lease: the declared hold mode, and the
# timed_move motor when the entity drives one.
ATTR_HOLD_LEASE_MODE = "hold_lease_mode"
ATTR_HOLD_LEASE_MOTOR = "hold_lease_motor"


def hold_lease_attributes(
    controllers: Iterable[BedController | SideBoundController | None],
    motor: str | None = None,
) -> dict[str, str]:
    """Advertise a renewable hold when every physical target declares one mode.

    The hold service refuses a lease otherwise, so a combined control offers a
    hold only when both sides agree.
    """
    # A controller without execution facts (an offline stub) declares no hold.
    modes = {
        execution.hold if isinstance(execution, ExecutionCapabilities) else None
        for execution in (getattr(controller, "execution", None) for controller in controllers)
    }
    if len(modes) != 1 or (mode := modes.pop()) is None:
        return {}
    attributes = {ATTR_HOLD_LEASE_MODE: mode}
    if motor in TIMED_MOVE_MOTOR_OPTIONS:
        attributes[ATTR_HOLD_LEASE_MOTOR] = motor
    return attributes


class AdjustableBedEntity(Entity):
    """Base class for Adjustable Bed entities."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: EntityRuntime) -> None:
        """Initialize the entity."""
        self._coordinator = coordinator
        self._attr_device_info = coordinator.device_info
        side = coordinator.entity_side
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
