"""Select entities for Adjustable Bed integration."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONF_HAS_MASSAGE,
    DOMAIN,
)
from .coordinator import AdjustableBedCoordinator
from .entity import AdjustableBedEntity

if TYPE_CHECKING:
    from .beds.base import BedController

_LOGGER = logging.getLogger(__name__)


MASSAGE_TIMER_DESCRIPTION = SelectEntityDescription(
    key="massage_timer",
    translation_key="massage_timer",
    icon="mdi:timer",
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Adjustable Bed select entities."""
    coordinator: AdjustableBedCoordinator = hass.data[DOMAIN][entry.entry_id]
    has_massage = entry.data.get(CONF_HAS_MASSAGE, False)
    controller = coordinator.controller

    entities: list[SelectEntity] = []

    # Set up massage timer select (only for beds with massage and timer support)
    if has_massage and controller is not None:
        if getattr(controller, "supports_massage_timer", False):
            timer_options = getattr(controller, "massage_timer_options", [])
            if timer_options:
                _LOGGER.debug(
                    "Setting up massage timer select for %s (options: %s)",
                    coordinator.name,
                    timer_options,
                )
                entities.append(
                    AdjustableBedMassageTimerSelect(
                        coordinator, MASSAGE_TIMER_DESCRIPTION, timer_options
                    )
                )

    if entities:
        async_add_entities(entities)


class AdjustableBedMassageTimerSelect(AdjustableBedEntity, SelectEntity):
    """Select entity for Adjustable Bed massage timer."""

    entity_description: SelectEntityDescription

    def __init__(
        self,
        coordinator: AdjustableBedCoordinator,
        description: SelectEntityDescription,
        timer_options: list[int],
    ) -> None:
        """Initialize the massage timer select entity."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.address}_{description.key}"
        self._timer_options = timer_options

        # Build options list: "Off" plus timer durations
        self._attr_options = ["Off"] + [f"{m} min" for m in timer_options]

    @property
    def current_option(self) -> str | None:
        """Return the current timer setting from controller state."""
        controller = self._coordinator.controller
        if controller is None:
            return "Off"

        # Get massage state from controller
        state = controller.get_massage_state()
        timer_mode = state.get("timer_mode")

        # Normalize: treat "0", 0, empty, or None as "Off"
        if not timer_mode or str(timer_mode) == "0":
            return "Off"

        # Format as option string and validate against allowed options
        formatted = f"{timer_mode} min"
        if formatted in self._attr_options:
            return formatted
        return "Off"

    async def async_select_option(self, option: str) -> None:
        """Set the massage timer duration."""
        # Validate option against allowed options
        if option not in self._attr_options:
            _LOGGER.warning(
                "Invalid timer option '%s' - allowed options: %s",
                option,
                self._attr_options,
            )
            return

        _LOGGER.info(
            "Massage timer set requested: %s (device: %s)",
            option,
            self._coordinator.name,
        )

        # Parse the option to get minutes
        if option == "Off":
            minutes = 0
        else:
            # Extract number from "10 min", "20 min", etc.
            minutes = int(option.split()[0])

        async def _set_timer(ctrl: BedController) -> None:
            await ctrl.set_massage_timer(minutes)

        await self._coordinator.async_execute_controller_command(_set_timer)
