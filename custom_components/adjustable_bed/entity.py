"""Base entity classes for Adjustable Bed integration."""

from __future__ import annotations

from collections.abc import Iterable
from contextlib import AbstractContextManager
from typing import TYPE_CHECKING, Any, Self

from homeassistant.core import callback
from homeassistant.helpers.entity import Entity

from .const import TIMED_MOVE_MOTOR_OPTIONS
from .entity_runtime import controller_side_scope
from .execution import ExecutionCapabilities

if TYPE_CHECKING:
    from .beds.base import BedController
    from .entity_runtime import EntityRuntime

# A renewable hold (#483) the card may lease: the declared hold mode, and the
# timed_move motor when the entity drives one.
ATTR_HOLD_LEASE_MODE = "hold_lease_mode"
ATTR_HOLD_LEASE_MOTOR = "hold_lease_motor"


def hold_lease_attributes(
    controllers: Iterable[BedController | None],
    motor: str | None = None,
    *,
    control: str | None = None,
) -> dict[str, str]:
    """Advertise a renewable hold when every physical target declares one mode.

    ``control`` is the entity's held control; without one the entity leases a
    motor route. The hold service refuses a lease otherwise, so a combined
    control offers a hold only when both sides agree.
    """
    # A controller without execution facts (an offline stub) declares no hold.
    modes = {
        execution.hold_for(control) if isinstance(execution, ExecutionCapabilities) else None
        for execution in (getattr(controller, "execution", None) for controller in controllers)
    }
    if len(modes) != 1 or (mode := modes.pop()) is None:
        return {}
    attributes = {ATTR_HOLD_LEASE_MODE: mode}
    if motor in TIMED_MOVE_MOTOR_OPTIONS:
        attributes[ATTR_HOLD_LEASE_MOTOR] = motor
    return attributes


class RenamesInPlace(Entity):
    """Keep the entity in place when the user changes its entity_id.

    Home Assistant removes and re-adds a custom entity on an entity_id change
    unless every class of it that has add or remove hooks declares
    async_entity_id_changed itself. A re-add tears down timers and
    subscriptions; an Octo light's auto-off timer, for one, is not restarted.
    Nothing in this integration is keyed on the entity_id, so each subclass
    declares a hook that only defers to the next one. A subclass that keys
    something on the entity_id defines its own hook to move it.
    """

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if "async_entity_id_changed" in cls.__dict__:
            return

        @callback
        def async_entity_id_changed(self: Self, old_entity_id: str) -> None:
            super(cls, self).async_entity_id_changed(old_entity_id)

        cls.async_entity_id_changed = async_entity_id_changed


class AdjustableBedEntity(RenamesInPlace):
    """Base class for Adjustable Bed entities."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: EntityRuntime) -> None:
        """Initialize the entity."""
        self._coordinator = coordinator
        self._attr_device_info = coordinator.device_info
        side = coordinator.entity_side
        if side is not None:
            self._attr_extra_state_attributes = {"bed_side": side}

    def _side_scope(self) -> AbstractContextManager[None]:
        """Bind this entity's side to a shared controller around a direct read."""
        return controller_side_scope(self._coordinator)

    def _async_write_ha_state(self) -> None:
        """Read state with a shared controller bound to this entity's side."""
        with self._side_scope():
            super()._async_write_ha_state()

    @property
    def available(self) -> bool:
        """Return True if entity is available.

        For on-demand-connect devices like this bed, entities are always
        available since we reconnect when a command is sent. The connection
        state doesn't affect availability - only actual connection failures
        during command execution indicate a problem.
        """
        return True
