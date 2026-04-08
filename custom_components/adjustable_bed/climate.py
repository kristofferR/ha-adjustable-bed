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

_THERMAL_CLIMATE_PRESETS_BASE: tuple[str, ...] = ("low", "medium", "high")
# `boost` corresponds to Heidi's SPECIAL_HIGH_COOLING ThermalMode and is
# strictly cooling-only (no heating equivalent in the SleepIQ enum). It must
# never be forwarded to the controller while the entity is in HEAT mode.
_THERMAL_CLIMATE_BOOST_PRESET: str = "boost"
_THERMAL_CLIMATE_HEAT_FALLBACK_PRESET: str = "high"


@dataclass(frozen=True, kw_only=True)
class AdjustableBedClimateEntityDescription(ClimateEntityDescription):
    """Describes an Adjustable Bed climate entity."""

    required_capability: str
    hvac_state_key: str
    preset_state_key: str
    timer_state_key: str
    remaining_time_key: str
    total_remaining_time_key: str | None = None
    raw_mode_state_key: str | None = None
    supports_heat: bool
    supports_cool: bool
    turn_on_method_name: str
    turn_off_method_name: str
    set_preset_method_name: str
    base_preset_modes: tuple[str, ...]


CLIMATE_DESCRIPTIONS: tuple[AdjustableBedClimateEntityDescription, ...] = (
    # Unified Sleep Number thermal climate entity: present if either Frosty
    # (Cooling Module) or Heidi (Core Temperature Module) is present.
    # Heat is only exposed when the active backend supports it (Heidi only).
    AdjustableBedClimateEntityDescription(
        key="sleep_number_thermal_climate",
        translation_key="sleep_number_thermal_climate",
        icon="mdi:thermometer",
        required_capability="supports_thermal_climate",
        hvac_state_key="thermal_hvac_mode",
        preset_state_key="thermal_preset",
        timer_state_key="thermal_timer_option",
        remaining_time_key="thermal_remaining_time_minutes",
        raw_mode_state_key="thermal_mode",
        supports_heat=True,
        supports_cool=True,
        turn_on_method_name="turn_thermal_on",
        turn_off_method_name="turn_thermal_off",
        set_preset_method_name="set_thermal_preset",
        base_preset_modes=_THERMAL_CLIMATE_PRESETS_BASE,
    ),
    AdjustableBedClimateEntityDescription(
        key="footwarming_climate",
        translation_key="footwarming_climate",
        icon="mdi:foot-print",
        required_capability="supports_footwarming_climate",
        hvac_state_key="footwarming_hvac_mode",
        preset_state_key="footwarming_preset",
        timer_state_key="footwarming_timer_option",
        remaining_time_key="footwarming_remaining_time_minutes",
        total_remaining_time_key="footwarming_total_remaining_time_minutes",
        raw_mode_state_key="footwarming_level",
        supports_heat=True,
        supports_cool=False,
        turn_on_method_name="turn_footwarming_on",
        turn_off_method_name="turn_footwarming_off",
        set_preset_method_name="set_footwarming_preset",
        base_preset_modes=_THERMAL_CLIMATE_PRESETS_BASE,
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
        relevant_keys = {
            self.entity_description.hvac_state_key,
            self.entity_description.preset_state_key,
            self.entity_description.timer_state_key,
            self.entity_description.remaining_time_key,
        }
        if self.entity_description.total_remaining_time_key is not None:
            relevant_keys.add(self.entity_description.total_remaining_time_key)
        if self.entity_description.raw_mode_state_key is not None:
            relevant_keys.add(self.entity_description.raw_mode_state_key)
        # The unified thermal entity's hvac_modes depend on
        # `thermal_supports_heating`; refresh when that flips too.
        relevant_keys.add("thermal_supports_heating")
        if relevant_keys & state.keys():
            self.async_write_ha_state()

    @property
    def temperature_unit(self) -> str:
        """Return a temperature unit for ClimateEntity compatibility."""
        return UnitOfTemperature.CELSIUS

    @property
    def hvac_modes(self) -> list[HVACMode]:
        """Return the HVAC modes available for this entity's current backend."""
        modes: list[HVACMode] = [HVACMode.OFF]
        if self.entity_description.supports_cool and self._backend_supports_cooling():
            modes.append(HVACMode.COOL)
        if self.entity_description.supports_heat and self._backend_supports_heating():
            modes.append(HVACMode.HEAT)
        return modes

    @property
    def preset_modes(self) -> list[str]:
        """Return available preset modes, expanding boost when valid.

        ``boost`` is only meaningful for the cooling path (Heidi's
        SPECIAL_HIGH_COOLING). It is hidden when the entity is currently in
        HEAT mode so the UI cannot offer impossible combinations.
        """
        presets = list(self.entity_description.base_preset_modes)
        if (
            self.entity_description.key == "sleep_number_thermal_climate"
            and getattr(self._coordinator.controller, "thermal_supports_boost", False)
            and self.hvac_mode != HVACMode.HEAT
        ):
            presets.append(_THERMAL_CLIMATE_BOOST_PRESET)
        return presets

    def _backend_supports_heating(self) -> bool:
        """Return True when the backend supports HVAC HEAT."""
        if not self.entity_description.supports_heat:
            return False
        if self.entity_description.key == "sleep_number_thermal_climate":
            # Only Heidi (Core Temperature) heats; Frosty is cooling-only.
            return bool(
                getattr(self._coordinator.controller, "thermal_supports_heating", False)
            )
        return True

    def _backend_supports_cooling(self) -> bool:
        """Return True when the backend supports HVAC COOL."""
        return self.entity_description.supports_cool

    @property
    def hvac_mode(self) -> HVACMode:
        """Return the current HVAC mode."""
        mode = self._coordinator.controller_state.get(self.entity_description.hvac_state_key)
        if mode == HVACMode.COOL.value and self._backend_supports_cooling():
            return HVACMode.COOL
        if mode == HVACMode.HEAT.value and self._backend_supports_heating():
            return HVACMode.HEAT
        return HVACMode.OFF

    @property
    def preset_mode(self) -> str | None:
        """Return the current preset mode when active."""
        preset = self._coordinator.controller_state.get(self.entity_description.preset_state_key)
        if self.hvac_mode == HVACMode.OFF:
            return None
        if preset in self.preset_modes:
            return str(preset)
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return climate-specific metadata."""
        attrs: dict[str, Any] = {}
        side = self._coordinator.controller_state.get("sleep_number_side")
        if side is not None:
            attrs["side"] = side
        if self.entity_description.key == "sleep_number_thermal_climate":
            backend = self._coordinator.controller_state.get("thermal_backend")
            if backend is not None:
                attrs["backend"] = backend
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
        if hvac_mode not in self.hvac_modes:
            raise ValueError(f"Unsupported HVAC mode for {self.entity_id}: {hvac_mode}")

        if self.entity_description.key == "sleep_number_thermal_climate":
            # Resume using the last active preset, but routed to the requested
            # hvac_mode so users can flip between heat and cool without having
            # to re-pick a preset. ``boost`` is cooling-only and would be an
            # invalid mode for heating, so downgrade to the high preset when
            # switching from cool/boost to heat.
            preset = self.preset_mode or "low"
            if (
                hvac_mode == HVACMode.HEAT
                and preset == _THERMAL_CLIMATE_BOOST_PRESET
            ):
                preset = _THERMAL_CLIMATE_HEAT_FALLBACK_PRESET
            await self._async_call_thermal_preset(preset, hvac_mode)
            return
        await self.async_turn_on()

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Set the preset mode."""
        if preset_mode not in self.preset_modes:
            raise ValueError(f"Unsupported preset mode for {self.entity_id}: {preset_mode}")

        if self.entity_description.key == "sleep_number_thermal_climate":
            current_hvac = self.hvac_mode
            if current_hvac == HVACMode.OFF:
                # Default to the backend's last active HVAC mode (Heidi) or
                # COOL (Frosty). The controller's set_thermal_preset resolves
                # this when hvac_mode is None — but ``boost`` is cooling-only,
                # so force COOL when the user picks it from an off state to
                # avoid an impossible combination if Heidi's last active was
                # heating.
                target: HVACMode | None
                if preset_mode == _THERMAL_CLIMATE_BOOST_PRESET:
                    target = HVACMode.COOL
                else:
                    target = None
            else:
                target = current_hvac
            # Belt-and-braces: never forward boost into a heat-mode call.
            if (
                target == HVACMode.HEAT
                and preset_mode == _THERMAL_CLIMATE_BOOST_PRESET
            ):
                raise ValueError(
                    f"`boost` is a cooling-only preset for {self.entity_id}; "
                    "switch to cool first"
                )
            await self._async_call_thermal_preset(preset_mode, target)
            return

        await self._async_call_controller_method(
            self.entity_description.set_preset_method_name,
            preset_mode,
        )

    async def _async_call_thermal_preset(
        self, preset_mode: str, hvac_mode: HVACMode | None
    ) -> None:
        """Call set_thermal_preset with an optional hvac_mode argument."""
        hvac_value: str | None = hvac_mode.value if hvac_mode is not None else None

        async def _invoke(ctrl: BedController) -> None:
            await ctrl.set_thermal_preset(preset_mode, hvac_mode=hvac_value)  # type: ignore[attr-defined]

        _LOGGER.info(
            "Climate command requested: set_thermal_preset(%s, hvac_mode=%s) on %s",
            preset_mode,
            hvac_value,
            self._coordinator.name,
        )
        await self._coordinator.async_execute_controller_command(_invoke)

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
