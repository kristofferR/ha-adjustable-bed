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
    side: str | None = None
    supports_heating_state_key: str | None = None
    backend_state_key: str | None = None


SLEEP_NUMBER_THERMAL_CLIMATE_DESCRIPTION = AdjustableBedClimateEntityDescription(
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
    supports_heating_state_key="thermal_supports_heating",
    backend_state_key="thermal_backend",
)

FOOTWARMING_CLIMATE_DESCRIPTION = AdjustableBedClimateEntityDescription(
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
)


def _build_side_thermal_climate_description(side: str) -> AdjustableBedClimateEntityDescription:
    """Build the side-specific Sleep Number thermal climate description."""
    return AdjustableBedClimateEntityDescription(
        key=f"sleep_number_thermal_climate_{side}",
        translation_key=f"sleep_number_thermal_climate_{side}",
        icon=SLEEP_NUMBER_THERMAL_CLIMATE_DESCRIPTION.icon,
        required_capability=SLEEP_NUMBER_THERMAL_CLIMATE_DESCRIPTION.required_capability,
        hvac_state_key=f"thermal_hvac_mode_{side}",
        preset_state_key=f"thermal_preset_{side}",
        timer_state_key=f"thermal_timer_option_{side}",
        remaining_time_key=f"thermal_remaining_time_minutes_{side}",
        raw_mode_state_key=f"thermal_mode_{side}",
        supports_heat=True,
        supports_cool=True,
        turn_on_method_name="turn_thermal_on_for_side",
        turn_off_method_name="turn_thermal_off_for_side",
        set_preset_method_name="set_thermal_preset_for_side",
        base_preset_modes=_THERMAL_CLIMATE_PRESETS_BASE,
        side=side,
        supports_heating_state_key=f"thermal_supports_heating_{side}",
        backend_state_key=f"thermal_backend_{side}",
    )


def _build_side_footwarming_climate_description(
    side: str,
) -> AdjustableBedClimateEntityDescription:
    """Build the side-specific footwarming climate description."""
    return AdjustableBedClimateEntityDescription(
        key=f"footwarming_climate_{side}",
        translation_key=f"footwarming_climate_{side}",
        icon=FOOTWARMING_CLIMATE_DESCRIPTION.icon,
        required_capability=FOOTWARMING_CLIMATE_DESCRIPTION.required_capability,
        hvac_state_key=f"footwarming_hvac_mode_{side}",
        preset_state_key=f"footwarming_preset_{side}",
        timer_state_key=f"footwarming_timer_option_{side}",
        remaining_time_key=f"footwarming_remaining_time_minutes_{side}",
        total_remaining_time_key=f"footwarming_total_remaining_time_minutes_{side}",
        raw_mode_state_key=f"footwarming_level_{side}",
        supports_heat=True,
        supports_cool=False,
        turn_on_method_name="turn_footwarming_on_for_side",
        turn_off_method_name="turn_footwarming_off_for_side",
        set_preset_method_name="set_footwarming_preset_for_side",
        base_preset_modes=_THERMAL_CLIMATE_PRESETS_BASE,
        side=side,
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

    entities: list[AdjustableBedClimate] = []

    thermal_sides = tuple(getattr(controller, "thermal_climate_sides", ()))
    if thermal_sides:
        entities.append(
            AdjustableBedClimate(
                coordinator,
                AdjustableBedClimateEntityDescription(
                    key=SLEEP_NUMBER_THERMAL_CLIMATE_DESCRIPTION.key,
                    translation_key=SLEEP_NUMBER_THERMAL_CLIMATE_DESCRIPTION.translation_key,
                    icon=SLEEP_NUMBER_THERMAL_CLIMATE_DESCRIPTION.icon,
                    required_capability=SLEEP_NUMBER_THERMAL_CLIMATE_DESCRIPTION.required_capability,
                    hvac_state_key=SLEEP_NUMBER_THERMAL_CLIMATE_DESCRIPTION.hvac_state_key,
                    preset_state_key=SLEEP_NUMBER_THERMAL_CLIMATE_DESCRIPTION.preset_state_key,
                    timer_state_key=SLEEP_NUMBER_THERMAL_CLIMATE_DESCRIPTION.timer_state_key,
                    remaining_time_key=SLEEP_NUMBER_THERMAL_CLIMATE_DESCRIPTION.remaining_time_key,
                    raw_mode_state_key=SLEEP_NUMBER_THERMAL_CLIMATE_DESCRIPTION.raw_mode_state_key,
                    supports_heat=SLEEP_NUMBER_THERMAL_CLIMATE_DESCRIPTION.supports_heat,
                    supports_cool=SLEEP_NUMBER_THERMAL_CLIMATE_DESCRIPTION.supports_cool,
                    turn_on_method_name=SLEEP_NUMBER_THERMAL_CLIMATE_DESCRIPTION.turn_on_method_name,
                    turn_off_method_name=SLEEP_NUMBER_THERMAL_CLIMATE_DESCRIPTION.turn_off_method_name,
                    set_preset_method_name=SLEEP_NUMBER_THERMAL_CLIMATE_DESCRIPTION.set_preset_method_name,
                    base_preset_modes=SLEEP_NUMBER_THERMAL_CLIMATE_DESCRIPTION.base_preset_modes,
                    supports_heating_state_key=SLEEP_NUMBER_THERMAL_CLIMATE_DESCRIPTION.supports_heating_state_key,
                    backend_state_key=SLEEP_NUMBER_THERMAL_CLIMATE_DESCRIPTION.backend_state_key,
                    entity_registry_enabled_default=False,
                ),
            )
        )
        for side in thermal_sides:
            entities.append(
                AdjustableBedClimate(
                    coordinator,
                    _build_side_thermal_climate_description(side),
                )
            )
    elif getattr(controller, SLEEP_NUMBER_THERMAL_CLIMATE_DESCRIPTION.required_capability, False):
        entities.append(AdjustableBedClimate(coordinator, SLEEP_NUMBER_THERMAL_CLIMATE_DESCRIPTION))

    footwarming_sides = tuple(getattr(controller, "footwarming_climate_sides", ()))
    if footwarming_sides:
        entities.append(
            AdjustableBedClimate(
                coordinator,
                AdjustableBedClimateEntityDescription(
                    key=FOOTWARMING_CLIMATE_DESCRIPTION.key,
                    translation_key=FOOTWARMING_CLIMATE_DESCRIPTION.translation_key,
                    icon=FOOTWARMING_CLIMATE_DESCRIPTION.icon,
                    required_capability=FOOTWARMING_CLIMATE_DESCRIPTION.required_capability,
                    hvac_state_key=FOOTWARMING_CLIMATE_DESCRIPTION.hvac_state_key,
                    preset_state_key=FOOTWARMING_CLIMATE_DESCRIPTION.preset_state_key,
                    timer_state_key=FOOTWARMING_CLIMATE_DESCRIPTION.timer_state_key,
                    remaining_time_key=FOOTWARMING_CLIMATE_DESCRIPTION.remaining_time_key,
                    total_remaining_time_key=FOOTWARMING_CLIMATE_DESCRIPTION.total_remaining_time_key,
                    raw_mode_state_key=FOOTWARMING_CLIMATE_DESCRIPTION.raw_mode_state_key,
                    supports_heat=FOOTWARMING_CLIMATE_DESCRIPTION.supports_heat,
                    supports_cool=FOOTWARMING_CLIMATE_DESCRIPTION.supports_cool,
                    turn_on_method_name=FOOTWARMING_CLIMATE_DESCRIPTION.turn_on_method_name,
                    turn_off_method_name=FOOTWARMING_CLIMATE_DESCRIPTION.turn_off_method_name,
                    set_preset_method_name=FOOTWARMING_CLIMATE_DESCRIPTION.set_preset_method_name,
                    base_preset_modes=FOOTWARMING_CLIMATE_DESCRIPTION.base_preset_modes,
                    entity_registry_enabled_default=False,
                ),
            )
        )
        for side in footwarming_sides:
            entities.append(
                AdjustableBedClimate(
                    coordinator,
                    _build_side_footwarming_climate_description(side),
                )
            )
    elif getattr(controller, FOOTWARMING_CLIMATE_DESCRIPTION.required_capability, False):
        entities.append(AdjustableBedClimate(coordinator, FOOTWARMING_CLIMATE_DESCRIPTION))

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
        if self.entity_description.supports_heating_state_key is not None:
            relevant_keys.add(self.entity_description.supports_heating_state_key)
        if self.entity_description.backend_state_key is not None:
            relevant_keys.add(self.entity_description.backend_state_key)
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
            self.entity_description.key.startswith("sleep_number_thermal_climate")
            and self._backend_supports_heating()
            and self.hvac_mode != HVACMode.HEAT
        ):
            presets.append(_THERMAL_CLIMATE_BOOST_PRESET)
        return presets

    def _backend_supports_heating(self) -> bool:
        """Return True when the backend supports HVAC HEAT."""
        if not self.entity_description.supports_heat:
            return False
        if self.entity_description.supports_heating_state_key is not None:
            return bool(
                self._coordinator.controller_state.get(
                    self.entity_description.supports_heating_state_key
                )
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
        side = self.entity_description.side or self._coordinator.controller_state.get(
            "sleep_number_side"
        )
        if side is not None:
            attrs["side"] = side
        if self.entity_description.backend_state_key is not None:
            backend = self._coordinator.controller_state.get(
                self.entity_description.backend_state_key
            )
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

        if self.entity_description.key.startswith("sleep_number_thermal_climate"):
            # Resume using the last active preset, but routed to the
            # requested hvac_mode so users can flip between heat and cool
            # without having to re-pick a preset. When the entity is
            # currently OFF, ``preset_mode`` intentionally returns None, so
            # we read the controller's per-direction resume cache to
            # preserve whatever preset the user last ran for *that* hvac
            # mode instead of discarding it and defaulting to ``low``.
            # ``boost`` is cooling-only and must never be forwarded into
            # heat, so downgrade to the high preset in that case.
            preset = self.preset_mode
            if preset is None:
                controller = self._coordinator.controller
                target_hvac_value = hvac_mode.value
                if self.entity_description.side is not None:
                    resume = getattr(controller, "get_thermal_resume_preset_for_side", None)
                else:
                    resume = getattr(controller, "get_thermal_resume_preset", None)
                if callable(resume):
                    if self.entity_description.side is not None:
                        preset = resume(self.entity_description.side, target_hvac_value)
                    else:
                        preset = resume(target_hvac_value)
                else:
                    preset = "low"
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

        if self.entity_description.key.startswith("sleep_number_thermal_climate"):
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
            if self.entity_description.side is not None:
                await ctrl.set_thermal_preset_for_side(  # type: ignore[attr-defined]
                    self.entity_description.side,
                    preset_mode,
                    hvac_mode=hvac_value,
                )
            else:
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
            ", ".join(
                (
                    [self.entity_description.side]
                    if self.entity_description.side is not None
                    else []
                )
                + list(args)
            ),
            self._coordinator.name,
        )

        async def _invoke(ctrl: BedController) -> None:
            if self.entity_description.side is not None:
                await getattr(ctrl, method_name)(self.entity_description.side, *args)
            else:
                await getattr(ctrl, method_name)(*args)

        await self._coordinator.async_execute_controller_command(_invoke)
