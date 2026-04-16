"""Light entities for Adjustable Bed integration."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from homeassistant.components.light import (
    ATTR_RGB_COLOR,
    ATTR_RGBW_COLOR,
    ColorMode,
    LightEntity,
    LightEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_ON
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import DOMAIN
from .coordinator import AdjustableBedCoordinator
from .entity import AdjustableBedEntity

if TYPE_CHECKING:
    from .beds.base import BedController

_LOGGER = logging.getLogger(__name__)


LIGHT_DESCRIPTION = LightEntityDescription(
    key="under_bed_lights",
    translation_key="under_bed_lights",
    icon="mdi:led-strip-variant",
)


def _normalize_rgb_color(value: Any) -> tuple[int, int, int] | None:
    """Normalize an RGB-like value to a strict 3-tuple."""
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        return None

    try:
        rgb = tuple(int(channel) for channel in value)
    except (TypeError, ValueError):
        return None

    if any(channel < 0 or channel > 255 for channel in rgb):
        return None
    return rgb


def _normalize_rgbw_color(value: Any) -> tuple[int, int, int, int] | None:
    """Normalize an RGBW-like value to a strict 4-tuple."""
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        return None

    try:
        rgbw = tuple(int(channel) for channel in value)
    except (TypeError, ValueError):
        return None

    if any(channel < 0 or channel > 255 for channel in rgbw):
        return None
    return rgbw


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Adjustable Bed light entities."""
    coordinator: AdjustableBedCoordinator = hass.data[DOMAIN][entry.entry_id]
    controller = coordinator.controller

    if controller is None or not getattr(controller, "supports_light_color_control", False):
        _async_remove_stale_light_entity(hass, coordinator)
        return

    async_add_entities([AdjustableBedLight(coordinator, LIGHT_DESCRIPTION)])


def _async_remove_stale_light_entity(
    hass: HomeAssistant, coordinator: AdjustableBedCoordinator
) -> None:
    """Remove stale light entities when the controller no longer supports them."""
    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id(
        "light",
        DOMAIN,
        f"{coordinator.address}_{LIGHT_DESCRIPTION.key}",
    )
    if entity_id is not None:
        registry.async_remove(entity_id)


class AdjustableBedLight(AdjustableBedEntity, RestoreEntity, LightEntity):
    """RGB/RGBW light entity for adjustable beds."""

    entity_description: LightEntityDescription

    _attr_assumed_state = True

    def __init__(
        self,
        coordinator: AdjustableBedCoordinator,
        description: LightEntityDescription,
    ) -> None:
        """Initialize the light."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.address}_{description.key}"

        controller = coordinator.controller
        color_mode_str = (
            getattr(controller, "supported_color_mode", None) if controller is not None else None
        )
        if color_mode_str == "rgbw":
            self._attr_color_mode = ColorMode.RGBW
            self._attr_supported_color_modes = {ColorMode.RGBW}
        else:
            self._attr_color_mode = ColorMode.RGB
            self._attr_supported_color_modes = {ColorMode.RGB}

        default_rgb = (
            getattr(controller, "default_light_rgb_color", None) if controller is not None else None
        )
        self._supports_discrete_light_control = bool(
            getattr(controller, "supports_discrete_light_control", False)
            if controller is not None
            else False
        )
        self._default_rgb_color = _normalize_rgb_color(default_rgb)
        self._attr_is_on = False
        if self._attr_color_mode == ColorMode.RGBW:
            # Default RGBW: use default RGB + white=255
            if self._default_rgb_color is not None:
                r, g, b = self._default_rgb_color
                self._attr_rgbw_color = (r, g, b, 255)
            else:
                self._attr_rgbw_color = (255, 255, 255, 255)
        else:
            self._attr_rgb_color = self._default_rgb_color

    async def async_added_to_hass(self) -> None:
        """Restore the last light state when available."""
        await super().async_added_to_hass()

        if (last_state := await self.async_get_last_state()) is None:
            return

        self._attr_is_on = last_state.state == STATE_ON
        if self._attr_color_mode == ColorMode.RGBW:
            restored_rgbw = _normalize_rgbw_color(last_state.attributes.get(ATTR_RGBW_COLOR))
            if restored_rgbw is not None:
                self._attr_rgbw_color = restored_rgbw
        else:
            restored_rgb = _normalize_rgb_color(last_state.attributes.get(ATTR_RGB_COLOR))
            if restored_rgb is not None:
                self._attr_rgb_color = restored_rgb

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the light on and optionally set a specific color."""
        if self._attr_color_mode == ColorMode.RGBW:
            await self._turn_on_rgbw(**kwargs)
        else:
            await self._turn_on_rgb(**kwargs)

    async def _turn_on_rgb(self, **kwargs: Any) -> None:
        """Turn on with RGB color mode."""
        requested_rgb = _normalize_rgb_color(kwargs.get(ATTR_RGB_COLOR))
        target_rgb = requested_rgb or self._attr_rgb_color or self._default_rgb_color
        if target_rgb is None:
            raise ValueError("No RGB color available for this light")

        async def _turn_on(ctrl: BedController) -> None:
            if getattr(ctrl, "supports_explicit_light_on_control", False):
                await ctrl.lights_on()
            await ctrl.set_light_color(target_rgb)

        await self._coordinator.async_execute_controller_command(_turn_on, cancel_running=False)
        self._attr_is_on = True
        self._attr_rgb_color = target_rgb
        self.async_write_ha_state()

    async def _turn_on_rgbw(self, **kwargs: Any) -> None:
        """Turn on with RGBW color mode."""
        requested_rgbw = _normalize_rgbw_color(kwargs.get(ATTR_RGBW_COLOR))
        target_rgbw = requested_rgbw or self._attr_rgbw_color or (255, 255, 255, 255)

        async def _turn_on(ctrl: BedController) -> None:
            if getattr(ctrl, "supports_explicit_light_on_control", False):
                await ctrl.lights_on()
            await ctrl.set_light_color_rgbw(target_rgbw)

        await self._coordinator.async_execute_controller_command(_turn_on, cancel_running=False)
        self._attr_is_on = True
        self._attr_rgbw_color = target_rgbw
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the light off using the controller's light-off semantics."""
        del kwargs

        if not self._attr_is_on and not self._supports_discrete_light_control:
            _LOGGER.debug(
                "Skipping toggle-based light off for %s because HA already believes it is off",
                self._coordinator.name,
            )
            return

        async def _turn_off(ctrl: BedController) -> None:
            if getattr(ctrl, "supports_discrete_light_control", False):
                await ctrl.lights_off()
                return
            if getattr(ctrl, "supports_light_toggle_control", False):
                await ctrl.lights_toggle()
                return
            raise NotImplementedError("Light off control not supported on this bed")

        await self._coordinator.async_execute_controller_command(_turn_off, cancel_running=False)
        self._attr_is_on = False
        self.async_write_ha_state()
