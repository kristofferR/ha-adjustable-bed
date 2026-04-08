"""Climate entities for Adjustable Bed integration."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityDescription,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import AdjustableBedCoordinator
from .entity import AdjustableBedEntity

if TYPE_CHECKING:
    from .beds.base import BedController

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class AdjustableBedClimateEntityDescription(ClimateEntityDescription):
    """Describes an Adjustable Bed climate entity."""

    required_capability: str
    active_hvac_mode: HVACMode
    hvac_state_key: str
    preset_state_key: str
    timer_state_key: str
    remaining_time_key: str
    total_remaining_time_key: str | None = None
    raw_mode_state_key: str | None = None
    turn_on_method_name: str
    turn_off_method_name: str
    set_preset_method_name: str
    preset_modes: tuple[str, ...]


CLIMATE_DESCRIPTIONS: tuple[AdjustableBedClimateEntityDescription, ...] = (
    AdjustableBedClimateEntityDescription(
        key="cooling_climate",
        translation_key="cooling_climate",
        icon="mdi:snowflake-thermometer",
        required_capability="supports_frosty_climate",
        active_hvac_mode=HVACMode.COOL,
        hvac_state_key="frosty_hvac_mode",
        preset_state_key="frosty_preset",
        timer_state_key="frosty_timer_option",
        remaining_time_key="frosty_remaining_time_minutes",
        raw_mode_state_key="frosty_mode",
        turn_on_method_name="turn_frosty_on",
        turn_off_method_name="turn_frosty_off",
        set_preset_method_name="set_frosty_preset",
        preset_modes=("low", "medium", "high", "boost"),
    ),
    AdjustableBedClimateEntityDescription(
        key="heating_climate",
        translation_key="heating_climate",
        icon="mdi:heat-wave",
        required_capability="supports_heidi_climate",
        active_hvac_mode=HVACMode.HEAT,
        hvac_state_key="heidi_hvac_mode",
        preset_state_key="heidi_preset",
        timer_state_key="heidi_timer_option",
        remaining_time_key="heidi_remaining_time_minutes",
        raw_mode_state_key="heidi_mode",
        turn_on_method_name="turn_heidi_on",
        turn_off_method_name="turn_heidi_off",
        set_preset_method_name="set_heidi_preset",
        preset_modes=("low", "medium", "high"),
    ),
    AdjustableBedClimateEntityDescription(
        key="footwarming_climate",
        translation_key="footwarming_climate",
        icon="mdi:foot-print",
        required_capability="supports_footwarming_climate",
        active_hvac_mode=HVACMode.HEAT,
        hvac_state_key="footwarming_hvac_mode",
        preset_state_key="footwarming_preset",
        timer_state_key="footwarming_timer_option",
        remaining_time_key="footwarming_remaining_time_minutes",
        total_remaining_time_key="footwarming_total_remaining_time_minutes",
        raw_mode_state_key="footwarming_level",
        turn_on_method_name="turn_footwarming_on",
        turn_off_method_name="turn_footwarming_off",
        set_preset_method_name="set_footwarming_preset",
        preset_modes=("low", "medium", "high"),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Adjustable Bed climate entities."""
    coordinator: AdjustableBedCoordinator = hass.data[DOMAIN][entry.entry_id]
    controller = coordinator.controller
    if controller is None:
        return

    entities = [
        AdjustableBedClimate(coordinator, description)
        for description in CLIMATE_DESCRIPTIONS
        if getattr(controller, description.required_capability, False)
    ]
    if entities:
        async_add_entities(entities)


class AdjustableBedClimate(AdjustableBedEntity, ClimateEntity):
    """Climate entity backed by controller-state updates."""

    entity_description: AdjustableBedClimateEntityDescription

    def __init__(
        self,
        coordinator: AdjustableBedCoordinator,
        description: AdjustableBedClimateEntityDescription,
    ) -> None:
        """Initialize the climate entity."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.address}_{description.key}"
        self._attr_hvac_modes = [HVACMode.OFF, description.active_hvac_mode]
        self._attr_preset_modes = list(description.preset_modes)
        self._attr_supported_features = (
            ClimateEntityFeature.PRESET_MODE
            | ClimateEntityFeature.TURN_ON
            | ClimateEntityFeature.TURN_OFF
        )
        self._unregister_callback: Callable[[], None] | None = None

    async def async_added_to_hass(self) -> None:
        """Register for controller-state updates."""
        await super().async_added_to_hass()
        self._unregister_callback = self._coordinator.register_controller_state_callback(
            self._handle_controller_state_update
        )

    async def async_will_remove_from_hass(self) -> None:
        """Clean up when the entity is removed."""
        if self._unregister_callback:
            self._unregister_callback()
        await super().async_will_remove_from_hass()

    @callback
    def _handle_controller_state_update(self, state: dict[str, Any]) -> None:
        """Write state when the controller publishes climate changes."""
        if any(
            key in state
            for key in (
                self.entity_description.hvac_state_key,
                self.entity_description.preset_state_key,
                self.entity_description.timer_state_key,
                self.entity_description.remaining_time_key,
            )
        ):
            self.async_write_ha_state()

    @property
    def temperature_unit(self) -> str:
        """Return a temperature unit for ClimateEntity compatibility."""
        return UnitOfTemperature.CELSIUS

    @property
    def hvac_mode(self) -> HVACMode:
        """Return the current HVAC mode."""
        mode = self._coordinator.controller_state.get(self.entity_description.hvac_state_key)
        if mode == self.entity_description.active_hvac_mode.value:
            return self.entity_description.active_hvac_mode
        return HVACMode.OFF

    @property
    def preset_mode(self) -> str | None:
        """Return the current preset mode when active."""
        preset = self._coordinator.controller_state.get(self.entity_description.preset_state_key)
        if self.hvac_mode == HVACMode.OFF:
            return None
        if preset in (self._attr_preset_modes or []):
            return str(preset)
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return climate-specific metadata."""
        attrs: dict[str, Any] = {}
        side = self._coordinator.controller_state.get("sleep_number_side")
        if side is not None:
            attrs["side"] = side
        timer_option = self._coordinator.controller_state.get(self.entity_description.timer_state_key)
        if timer_option is not None:
            attrs["timer"] = timer_option
        remaining = self._coordinator.controller_state.get(self.entity_description.remaining_time_key)
        if remaining is not None:
            attrs["remaining_time_minutes"] = remaining
        if self.entity_description.total_remaining_time_key is not None:
            total = self._coordinator.controller_state.get(
                self.entity_description.total_remaining_time_key
            )
            if total is not None:
                attrs["total_remaining_time_minutes"] = total
        if self.entity_description.raw_mode_state_key is not None:
            raw_mode = self._coordinator.controller_state.get(
                self.entity_description.raw_mode_state_key
            )
            if raw_mode is not None:
                attrs["raw_mode"] = raw_mode
        return attrs

    async def async_turn_on(self) -> None:
        """Turn the climate entity on."""
        await self._async_call_controller_method(self.entity_description.turn_on_method_name)

    async def async_turn_off(self) -> None:
        """Turn the climate entity off."""
        await self._async_call_controller_method(self.entity_description.turn_off_method_name)

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set the HVAC mode."""
        if hvac_mode == HVACMode.OFF:
            await self.async_turn_off()
            return
        if hvac_mode != self.entity_description.active_hvac_mode:
            raise ValueError(f"Unsupported HVAC mode for {self.entity_id}: {hvac_mode}")
        await self.async_turn_on()

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Set the preset mode."""
        if preset_mode not in (self._attr_preset_modes or []):
            raise ValueError(f"Unsupported preset mode for {self.entity_id}: {preset_mode}")
        await self._async_call_controller_method(
            self.entity_description.set_preset_method_name,
            preset_mode,
        )

    async def _async_call_controller_method(self, method_name: str, *args: str) -> None:
        """Execute a controller command method by name."""
        _LOGGER.info(
            "Climate command requested: %s(%s) on %s",
            method_name,
            ", ".join(args),
            self._coordinator.name,
        )

        async def _invoke(ctrl: BedController) -> None:
            await getattr(ctrl, method_name)(*args)

        await self._coordinator.async_execute_controller_command(_invoke)
