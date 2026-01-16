"""Switch entities for Adjustable Bed integration."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable, Coroutine

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import AdjustableBedCoordinator
from .entity import AdjustableBedEntity

if TYPE_CHECKING:
    from .beds.base import BedController

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class AdjustableBedSwitchEntityDescription(SwitchEntityDescription):
    """Describes a Adjustable Bed switch entity."""

    turn_on_fn: Callable[[BedController], Coroutine[Any, Any, None]]
    turn_off_fn: Callable[[BedController], Coroutine[Any, Any, None]]
    # Capability property name to check on controller (e.g., "supports_lights")
    required_capability: str | None = None


SWITCH_DESCRIPTIONS: tuple[AdjustableBedSwitchEntityDescription, ...] = (
    AdjustableBedSwitchEntityDescription(
        key="under_bed_lights",
        translation_key="under_bed_lights",
        icon="mdi:lightbulb",
        turn_on_fn=lambda ctrl: ctrl.lights_on(),
        turn_off_fn=lambda ctrl: ctrl.lights_off(),
        required_capability="supports_lights",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Adjustable Bed switch entities."""
    coordinator: AdjustableBedCoordinator = hass.data[DOMAIN][entry.entry_id]
    controller = coordinator.controller

    entities = []
    for description in SWITCH_DESCRIPTIONS:
        # Skip switches that require capabilities the controller doesn't have
        if description.required_capability is not None:
            if controller is None:
                continue
            if not getattr(controller, description.required_capability, True):
                continue
        entities.append(AdjustableBedSwitch(coordinator, description))

    async_add_entities(entities)


class AdjustableBedSwitch(AdjustableBedEntity, SwitchEntity):
    """Switch entity for Adjustable Bed."""

    entity_description: AdjustableBedSwitchEntityDescription

    def __init__(
        self,
        coordinator: AdjustableBedCoordinator,
        description: AdjustableBedSwitchEntityDescription,
    ) -> None:
        """Initialize the switch."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.address}_{description.key}"
        self._attr_is_on = False  # We don't have state feedback

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the switch."""
        _LOGGER.info(
            "Switch turn on: %s (device: %s)",
            self.entity_description.key,
            self._coordinator.name,
        )

        try:
            _LOGGER.debug("Sending turn on command for %s", self.entity_description.key)
            await self._coordinator.async_execute_controller_command(
                self.entity_description.turn_on_fn,
                cancel_running=False,
            )
            self._attr_is_on = True
            self.async_write_ha_state()
            _LOGGER.debug("Switch %s turned on successfully", self.entity_description.key)
        except NotImplementedError:
            _LOGGER.warning(
                "This bed does not support %s feature",
                self.entity_description.key,
            )
        except Exception:
            _LOGGER.exception(
                "Failed to turn on switch %s",
                self.entity_description.key,
            )
            raise

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the switch."""
        _LOGGER.info(
            "Switch turn off: %s (device: %s)",
            self.entity_description.key,
            self._coordinator.name,
        )

        try:
            _LOGGER.debug("Sending turn off command for %s", self.entity_description.key)
            await self._coordinator.async_execute_controller_command(
                self.entity_description.turn_off_fn,
                cancel_running=False,
            )
            self._attr_is_on = False
            self.async_write_ha_state()
            _LOGGER.debug("Switch %s turned off successfully", self.entity_description.key)
        except NotImplementedError:
            _LOGGER.warning(
                "This bed does not support %s feature",
                self.entity_description.key,
            )
        except Exception:
            _LOGGER.exception(
                "Failed to turn off switch %s",
                self.entity_description.key,
            )
            raise
