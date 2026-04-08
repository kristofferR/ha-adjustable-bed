"""Select entities for Adjustable Bed integration."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
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


@dataclass(frozen=True, kw_only=True)
class AdjustableBedControllerStateSelectDescription(SelectEntityDescription):
    """Describes a controller-state-backed select entity."""

    required_capability: str
    options_attr: str
    state_key: str
    setter_name: str


MASSAGE_TIMER_DESCRIPTION = SelectEntityDescription(
    key="massage_timer",
    translation_key="massage_timer",
    icon="mdi:timer",
)

LIGHT_TIMER_DESCRIPTION = AdjustableBedControllerStateSelectDescription(
    key="light_timer",
    translation_key="light_timer",
    icon="mdi:timer-outline",
    required_capability="supports_light_timer",
    options_attr="light_timer_options",
    state_key="light_timer_option",
    setter_name="set_light_timer",
)

COOLING_TIMER_DESCRIPTION = AdjustableBedControllerStateSelectDescription(
    key="cooling_timer",
    translation_key="cooling_timer",
    icon="mdi:snowflake-clock",
    required_capability="supports_frosty_climate",
    options_attr="cooling_timer_options",
    state_key="frosty_timer_option",
    setter_name="set_frosty_timer",
)

HEATING_TIMER_DESCRIPTION = AdjustableBedControllerStateSelectDescription(
    key="heating_timer",
    translation_key="heating_timer",
    icon="mdi:fire-circle",
    required_capability="supports_heidi_climate",
    options_attr="heating_timer_options",
    state_key="heidi_timer_option",
    setter_name="set_heidi_timer",
)

FOOTWARMING_TIMER_DESCRIPTION = AdjustableBedControllerStateSelectDescription(
    key="footwarming_timer",
    translation_key="footwarming_timer",
    icon="mdi:shoe-print",
    required_capability="supports_footwarming_climate",
    options_attr="footwarming_timer_options",
    state_key="footwarming_timer_option",
    setter_name="set_footwarming_timer",
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

    if controller is not None:
        for description in (
            LIGHT_TIMER_DESCRIPTION,
            COOLING_TIMER_DESCRIPTION,
            HEATING_TIMER_DESCRIPTION,
            FOOTWARMING_TIMER_DESCRIPTION,
        ):
            if not getattr(controller, description.required_capability, False):
                continue
            timer_options = getattr(controller, description.options_attr, [])
            if not timer_options:
                continue
            _LOGGER.debug(
                "Setting up %s select for %s (options: %s)",
                description.key,
                coordinator.name,
                timer_options,
            )
            entities.append(
                AdjustableBedControllerStateSelect(
                    coordinator,
                    description,
                    timer_options,
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


class AdjustableBedControllerStateSelect(AdjustableBedEntity, SelectEntity):
    """Select entity backed by controller state updates."""

    entity_description: AdjustableBedControllerStateSelectDescription

    def __init__(
        self,
        coordinator: AdjustableBedCoordinator,
        description: AdjustableBedControllerStateSelectDescription,
        timer_options: list[str],
    ) -> None:
        """Initialize the controller-state-backed select entity."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.address}_{description.key}"
        self._timer_options = timer_options

        # Use options directly from controller (already formatted)
        self._attr_options = timer_options
        self._unregister_callback: Callable[[], None] | None = None

    async def async_added_to_hass(self) -> None:
        """Run when entity is added to hass."""
        await super().async_added_to_hass()
        self._unregister_callback = self._coordinator.register_controller_state_callback(
            self._handle_controller_state_update
        )

    async def async_will_remove_from_hass(self) -> None:
        """Run when entity is removed from hass."""
        if self._unregister_callback:
            self._unregister_callback()
        await super().async_will_remove_from_hass()

    @callback
    def _handle_controller_state_update(self, state: dict[str, object]) -> None:
        """Write state when the controller publishes updated select state."""
        if self.entity_description.state_key in state:
            self.async_write_ha_state()

    @property
    def current_option(self) -> str | None:
        """Return the current timer setting when the controller tracks it."""
        option = self._coordinator.controller_state.get(self.entity_description.state_key)
        if isinstance(option, str) and option in self._attr_options:
            return option
        return None

    async def async_select_option(self, option: str) -> None:
        """Set the controller-backed option."""
        # Validate option against allowed options
        if option not in self._attr_options:
            _LOGGER.warning(
                "Invalid %s option '%s' - allowed options: %s",
                self.entity_description.key,
                option,
                self._attr_options,
            )
            return

        _LOGGER.info(
            "%s set requested: %s (device: %s)",
            self.entity_description.key,
            option,
            self._coordinator.name,
        )

        async def _set_timer(ctrl: BedController) -> None:
            await getattr(ctrl, self.entity_description.setter_name)(option)

        await self._coordinator.async_execute_controller_command(_set_timer)
