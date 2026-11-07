"""Select entities for Adjustable Bed integration."""

from __future__ import annotations

import logging
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from functools import partial
from typing import TYPE_CHECKING, Any

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ServiceValidationError

from .beds.base import ControllerSelectSpec
from .card import CARD_CLIMATE, CARD_LIGHTING, CARD_MASSAGE_TIMER, CardPlacement
from .const import (
    DOMAIN,
)
from .controller_state import ControllerState, StateKey, sided
from .entity import AdjustableBedEntity
from .entity_discovery import async_setup_dynamic_entities
from .entity_runtime import EntityRuntime, own_sides
from .entity_sweep import PlatformEntities, records_entities
from .octo_runtime import octo_controller
from .paired_coordinator import entity_runtimes
from .state_keys import (
    FOOTWARMING_TIMER_OPTION,
    FOUNDATION_PRESET,
    LIGHT_TIMER_OPTION,
    MASSAGE_TIMER_MINUTES,
    THERMAL_TIMER_OPTION,
    massage_state_side,
)

if TYPE_CHECKING:
    from .beds.base import BedController

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class AdjustableBedControllerStateSelectDescription(SelectEntityDescription):
    """Describes a controller-state-backed select entity."""

    is_supported: Callable[[BedController], bool]
    options_fn: Callable[[BedController], list[str]]
    state_key: StateKey[str | None]
    select_fn: Callable[[BedController, str], Coroutine[Any, Any, None]]
    card: CardPlacement


@dataclass(frozen=True, kw_only=True)
class AdjustableBedSideStateSelectDescription(SelectEntityDescription):
    """Describes a side-specific select entity backed by controller state."""

    state_key: StateKey[str | None]
    select_fn: Callable[[BedController, str, str], Coroutine[Any, Any, None]]
    side: str


MASSAGE_TIMER_DESCRIPTION = SelectEntityDescription(
    key="massage_timer",
    translation_key="massage_timer",
    icon="mdi:timer",
)

LIGHT_TIMER_DESCRIPTION = AdjustableBedControllerStateSelectDescription(
    key="light_timer",
    translation_key="light_timer",
    icon="mdi:timer-outline",
    is_supported=lambda c: c.supports_light_timer,
    options_fn=lambda c: c.light_timer_options,
    state_key=LIGHT_TIMER_OPTION,
    select_fn=lambda c, option: c.set_light_timer(option),
    card=CARD_LIGHTING,
)

THERMAL_TIMER_DESCRIPTION = AdjustableBedControllerStateSelectDescription(
    key="thermal_timer",
    translation_key="thermal_timer",
    icon="mdi:thermometer-lines",
    is_supported=lambda c: c.supports_thermal_climate,
    options_fn=lambda c: c.thermal_timer_options,
    state_key=THERMAL_TIMER_OPTION,
    select_fn=lambda c, option: c.set_thermal_timer(option),
    card=CARD_CLIMATE,
)

FOOTWARMING_TIMER_DESCRIPTION = AdjustableBedControllerStateSelectDescription(
    key="footwarming_timer",
    translation_key="footwarming_timer",
    icon="mdi:shoe-print",
    is_supported=lambda c: c.supports_footwarming_climate,
    options_fn=lambda c: c.footwarming_timer_options,
    state_key=FOOTWARMING_TIMER_OPTION,
    select_fn=lambda c, option: c.set_footwarming_timer(option),
    card=CARD_CLIMATE,
)

THERMAL_TIMER_LEFT_DESCRIPTION = AdjustableBedSideStateSelectDescription(
    key="thermal_timer_left",
    translation_key="thermal_timer_left",
    icon="mdi:thermometer-lines",
    state_key=sided(THERMAL_TIMER_OPTION, "left"),
    select_fn=lambda c, side, option: c.set_thermal_timer_for_side(side, option),
    side="left",
)

THERMAL_TIMER_RIGHT_DESCRIPTION = AdjustableBedSideStateSelectDescription(
    key="thermal_timer_right",
    translation_key="thermal_timer_right",
    icon="mdi:thermometer-lines",
    state_key=sided(THERMAL_TIMER_OPTION, "right"),
    select_fn=lambda c, side, option: c.set_thermal_timer_for_side(side, option),
    side="right",
)

FOOTWARMING_TIMER_LEFT_DESCRIPTION = AdjustableBedSideStateSelectDescription(
    key="footwarming_timer_left",
    translation_key="footwarming_timer_left",
    icon="mdi:shoe-print",
    state_key=sided(FOOTWARMING_TIMER_OPTION, "left"),
    select_fn=lambda c, side, option: c.set_footwarming_timer_for_side(side, option),
    side="left",
)

FOOTWARMING_TIMER_RIGHT_DESCRIPTION = AdjustableBedSideStateSelectDescription(
    key="footwarming_timer_right",
    translation_key="footwarming_timer_right",
    icon="mdi:shoe-print",
    state_key=sided(FOOTWARMING_TIMER_OPTION, "right"),
    select_fn=lambda c, side, option: c.set_footwarming_timer_for_side(side, option),
    side="right",
)

FOUNDATION_PRESET_LEFT_DESCRIPTION = AdjustableBedSideStateSelectDescription(
    key="foundation_preset_left",
    translation_key="foundation_preset_left",
    icon="mdi:bed-double-outline",
    state_key=sided(FOUNDATION_PRESET, "left"),
    select_fn=lambda c, side, option: c.set_foundation_preset_for_side(side, option),
    side="left",
)

FOUNDATION_PRESET_RIGHT_DESCRIPTION = AdjustableBedSideStateSelectDescription(
    key="foundation_preset_right",
    translation_key="foundation_preset_right",
    icon="mdi:bed-double-outline",
    state_key=sided(FOUNDATION_PRESET, "right"),
    select_fn=lambda c, side, option: c.set_foundation_preset_for_side(side, option),
    side="right",
)


@records_entities(Platform.SELECT)
async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: PlatformEntities,
) -> None:
    """Set up Adjustable Bed select entities."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    for runtime in entity_runtimes(coordinator):
        async_setup_dynamic_entities(
            entry,
            runtime,
            async_add_entities,
            partial(_select_entities_for, hass, runtime),
        )


def _select_entities_for(hass: HomeAssistant, coordinator: EntityRuntime) -> list[SelectEntity]:
    """Build select entities for a single (child or standalone) coordinator."""
    has_massage = coordinator.has_massage
    controller = coordinator.capability_controller
    if controller is not None and controller.auto_enable_massage:
        has_massage = True

    entities: list[SelectEntity] = []

    # Set up massage timer select (only for beds with massage and timer support)
    if has_massage and controller is not None and controller.supports_massage_timer:
        timer_options = controller.massage_timer_options
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
        if LIGHT_TIMER_DESCRIPTION.is_supported(controller):
            timer_options = LIGHT_TIMER_DESCRIPTION.options_fn(controller)
            if timer_options:
                _LOGGER.debug(
                    "Setting up %s select for %s (options: %s)",
                    LIGHT_TIMER_DESCRIPTION.key,
                    coordinator.name,
                    timer_options,
                )
                entities.append(
                    AdjustableBedControllerStateSelect(
                        coordinator,
                        LIGHT_TIMER_DESCRIPTION,
                        timer_options,
                    )
                )

        thermal_timer_options = list(
            THERMAL_TIMER_DESCRIPTION.options_fn(controller)
        )
        thermal_sides = own_sides(coordinator, controller.thermal_climate_sides)
        if thermal_sides and thermal_timer_options:
            _LOGGER.debug(
                "Setting up side-specific thermal timer selects for %s (sides: %s, options: %s)",
                coordinator.name,
                thermal_sides,
                thermal_timer_options,
            )
            for side_description in (
                THERMAL_TIMER_LEFT_DESCRIPTION,
                THERMAL_TIMER_RIGHT_DESCRIPTION,
            ):
                if side_description.side not in thermal_sides:
                    continue
                entities.append(
                    AdjustableBedSideStateSelect(
                        coordinator,
                        side_description,
                        thermal_timer_options,
                    )
                )
        elif THERMAL_TIMER_DESCRIPTION.is_supported(controller):
            if thermal_timer_options:
                _LOGGER.debug(
                    "Setting up %s select for %s (options: %s)",
                    THERMAL_TIMER_DESCRIPTION.key,
                    coordinator.name,
                    thermal_timer_options,
                )
                entities.append(
                    AdjustableBedControllerStateSelect(
                        coordinator,
                        THERMAL_TIMER_DESCRIPTION,
                        thermal_timer_options,
                    )
                )

        footwarming_timer_options = list(
            FOOTWARMING_TIMER_DESCRIPTION.options_fn(controller)
        )
        footwarming_sides = own_sides(coordinator, controller.footwarming_climate_sides)
        if footwarming_sides and footwarming_timer_options:
            _LOGGER.debug(
                "Setting up side-specific footwarming timer selects for %s (sides: %s, options: %s)",
                coordinator.name,
                footwarming_sides,
                footwarming_timer_options,
            )
            for side_description in (
                FOOTWARMING_TIMER_LEFT_DESCRIPTION,
                FOOTWARMING_TIMER_RIGHT_DESCRIPTION,
            ):
                if side_description.side not in footwarming_sides:
                    continue
                entities.append(
                    AdjustableBedSideStateSelect(
                        coordinator,
                        side_description,
                        footwarming_timer_options,
                    )
                )
        elif FOOTWARMING_TIMER_DESCRIPTION.is_supported(controller):
            if footwarming_timer_options:
                _LOGGER.debug(
                    "Setting up %s select for %s (options: %s)",
                    FOOTWARMING_TIMER_DESCRIPTION.key,
                    coordinator.name,
                    footwarming_timer_options,
                )
                entities.append(
                    AdjustableBedControllerStateSelect(
                        coordinator,
                        FOOTWARMING_TIMER_DESCRIPTION,
                        footwarming_timer_options,
                    )
                )

    foundation_preset_sides = (
        own_sides(coordinator, controller.foundation_preset_sides) if controller else ()
    )
    foundation_preset_options = controller.foundation_preset_options if controller else []
    if foundation_preset_sides and foundation_preset_options:
        _LOGGER.debug(
            "Setting up side-specific foundation preset selects for %s (sides: %s, options: %s)",
            coordinator.name,
            foundation_preset_sides,
            foundation_preset_options,
        )
        for side_description in (
            FOUNDATION_PRESET_LEFT_DESCRIPTION,
            FOUNDATION_PRESET_RIGHT_DESCRIPTION,
        ):
            if side_description.side not in foundation_preset_sides:
                continue
            entities.append(
                AdjustableBedSideStateSelect(
                    coordinator,
                    side_description,
                    foundation_preset_options,
                )
            )

    if controller is not None:
        specs = controller.controller_select_specs
        entities.extend(AdjustableBedControllerSelect(coordinator, spec) for spec in specs)

    return entities


class AdjustableBedControllerSelect(AdjustableBedEntity, SelectEntity):
    """A declared product option, unknown until the controller publishes state."""

    def __init__(self, coordinator: EntityRuntime, spec: ControllerSelectSpec) -> None:
        super().__init__(coordinator, spec.card)
        self._spec = spec
        self.entity_description = SelectEntityDescription(
            key=f"controller_select_{spec.key}", translation_key=spec.translation_key
        )
        self._attr_unique_id = coordinator.entity_unique_id(self.entity_description.key)
        self._attr_translation_key = spec.translation_key
        self._attr_options = list(spec.options)
        self._unregister_callback: Callable[[], None] | None = None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self._unregister_callback = self._coordinator.register_controller_state_callback(
            self._handle_controller_state_update
        )

    async def async_will_remove_from_hass(self) -> None:
        if self._unregister_callback is not None:
            self._unregister_callback()
        await super().async_will_remove_from_hass()

    @callback
    def _handle_controller_state_update(self, state: ControllerState) -> None:
        if self._spec.state_key in state:
            self.async_write_ha_state()

    @property
    def current_option(self) -> str | None:
        value = self._coordinator.controller_state.get(self._spec.state_key)
        return value if value in self._spec.options else None

    async def async_select_option(self, option: str) -> None:
        if option not in self._spec.options:
            raise ServiceValidationError("Option is not supported by this controller")
        if self._spec.local_select_fn is not None:
            # No frame is sent, so do not take the bed's single BLE link.
            controller = self._coordinator.capability_controller
            specs = controller.controller_select_specs if controller is not None else ()
            live = next(
                (spec for spec in specs if spec.key == self._spec.key),
                None,
            )
            if live is None or live.local_select_fn is None or option not in live.options:
                raise ServiceValidationError("Controller no longer supports this local option")
            live.local_select_fn(option)
            return

        async def select(ctrl: BedController) -> None:
            live = next(
                (spec for spec in ctrl.controller_select_specs if spec.key == self._spec.key), None
            )
            if live is None or option not in live.options:
                raise ServiceValidationError("Controller no longer supports this option")
            await live.select_fn(ctrl, option)

        await self._coordinator.async_execute_controller_command(select)


class AdjustableBedMassageTimerSelect(AdjustableBedEntity, SelectEntity):
    """Select entity for Adjustable Bed massage timer."""

    entity_description: SelectEntityDescription

    def __init__(
        self,
        coordinator: EntityRuntime,
        description: SelectEntityDescription,
        timer_options: list[int],
    ) -> None:
        """Initialize the massage timer select entity."""
        super().__init__(coordinator, CARD_MASSAGE_TIMER)
        self.entity_description = description
        self._attr_translation_key = description.translation_key or description.key
        self._attr_unique_id = coordinator.entity_unique_id(description.key)
        self._timer_options = timer_options

        # Build options list: "Off" plus timer durations
        self._attr_options = ["Off"] + [f"{m} min" for m in timer_options]
        self._unregister_callback: Callable[[], None] | None = None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self._unregister_callback = self._coordinator.register_controller_state_callback(
            self._handle_controller_state_update
        )

    async def async_will_remove_from_hass(self) -> None:
        if self._unregister_callback:
            self._unregister_callback()
        await super().async_will_remove_from_hass()

    @callback
    def _handle_controller_state_update(self, state: ControllerState) -> None:
        self.async_write_ha_state()

    @property
    def current_option(self) -> str | None:
        """Return the last published timer, or "Off"."""
        minutes = self._coordinator.controller_state.get(
            sided(
                MASSAGE_TIMER_MINUTES,
                massage_state_side(self._coordinator.bed_type, self._coordinator.entity_side),
            )
        )
        formatted = f"{minutes} min"
        return formatted if minutes and formatted in self._attr_options else "Off"

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

    _attr_should_poll = False

    entity_description: AdjustableBedControllerStateSelectDescription

    @property
    def available(self) -> bool:
        """Respect Octo's PIN gate for live settings."""
        controller = self._coordinator.capability_controller
        octo = octo_controller(controller)
        return super().available and (octo is None or octo.normal_controls_available)

    def __init__(
        self,
        coordinator: EntityRuntime,
        description: AdjustableBedControllerStateSelectDescription,
        timer_options: list[str],
    ) -> None:
        """Initialize the controller-state-backed select entity."""
        super().__init__(coordinator, description.card)
        self.entity_description = description
        self._attr_translation_key = description.translation_key or description.key
        self._attr_unique_id = coordinator.entity_unique_id(description.key)
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
    def _handle_controller_state_update(self, state: ControllerState) -> None:
        """Write state when the controller publishes updated select state."""
        if self.entity_description.state_key in state:
            self.async_write_ha_state()

    @property
    def current_option(self) -> str | None:
        """Return the current timer setting when the controller tracks it."""
        option = self._coordinator.controller_state.get(self.entity_description.state_key)
        return option if option in self._attr_options else None

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
            await self.entity_description.select_fn(ctrl, option)

        await self._coordinator.async_execute_controller_command(_set_timer)


class AdjustableBedSideStateSelect(AdjustableBedEntity, SelectEntity):
    """Select entity backed by a side-specific controller-state value."""

    entity_description: AdjustableBedSideStateSelectDescription

    def __init__(
        self,
        coordinator: EntityRuntime,
        description: AdjustableBedSideStateSelectDescription,
        options: list[str],
    ) -> None:
        """Initialize the side-specific select entity."""
        super().__init__(coordinator, CARD_CLIMATE)
        self.entity_description = description
        self._attr_translation_key = description.translation_key or description.key
        self._attr_unique_id = coordinator.entity_unique_id(description.key)
        self._attr_options = options
        self._unregister_callback: Callable[[], None] | None = None

    async def async_added_to_hass(self) -> None:
        """Register for controller-state updates."""
        await super().async_added_to_hass()
        self._unregister_callback = self._coordinator.register_controller_state_callback(
            self._handle_controller_state_update
        )

    async def async_will_remove_from_hass(self) -> None:
        """Clean up the callback."""
        if self._unregister_callback:
            self._unregister_callback()
        await super().async_will_remove_from_hass()

    @callback
    def _handle_controller_state_update(self, state: ControllerState) -> None:
        """Refresh when the tracked controller-state key changes."""
        if self.entity_description.state_key in state:
            self.async_write_ha_state()

    @property
    def current_option(self) -> str | None:
        """Return the current side-specific option."""
        option = self._coordinator.controller_state.get(self.entity_description.state_key)
        return option if option in self._attr_options else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose the side this preset selector targets."""
        return {"side": self.entity_description.side}

    async def async_select_option(self, option: str) -> None:
        """Set the side-specific option through the controller."""
        if option not in self._attr_options:
            _LOGGER.warning(
                "Invalid %s option '%s' - allowed options: %s",
                self.entity_description.key,
                option,
                self._attr_options,
            )
            return

        async def _set_option(ctrl: BedController) -> None:
            await self.entity_description.select_fn(ctrl, self.entity_description.side, option)

        await self._coordinator.async_execute_controller_command(_set_option)
