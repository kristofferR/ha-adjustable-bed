"""Light entities for Adjustable Bed integration."""

from __future__ import annotations

import asyncio
import logging
import math
from collections.abc import Callable, Mapping
from functools import partial
from typing import TYPE_CHECKING, Any

from bleak.exc import BleakError
from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_RGB_COLOR,
    ATTR_RGBW_COLOR,
    LightEntity,
    LightEntityDescription,
)
from homeassistant.components.light.const import ColorMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_OFF, STATE_ON, Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.restore_state import RestoreEntity

from .beds.octo.runtime import octo_controller
from .card import CARD_LIGHTING
from .command_scheduler import Delivery, delivered
from .const import DOMAIN
from .controller_state import ControllerState, sided
from .entity import AdjustableBedEntity
from .entity_discovery import async_setup_dynamic_entities
from .entity_runtime import EntityRuntime
from .entity_sweep import PlatformEntities, records_entities
from .errors import invalid
from .paired_coordinator import entity_runtimes
from .state_keys import (
    LIGHT_INTENSITY,
    LIGHT_LEVEL,
    OCTO_LIGHT_DURATION,
    UNDER_BED_LIGHTS_ON,
    UNDER_BED_LIGHTS_RGB,
    UNDER_BED_LIGHTS_RGBW,
)

if TYPE_CHECKING:
    from .beds.base import BedController
    from .beds.octo.controller import OctoController

_LOGGER = logging.getLogger(__name__)


LIGHT_DESCRIPTION = LightEntityDescription(
    key="under_bed_lights",
    translation_key="under_bed_lights",
    icon="mdi:led-strip-variant",
)

ASSUMED_LIGHT_DESCRIPTION = LightEntityDescription(
    key="under_bed_lights_assumed",
    translation_key="under_bed_lights",
    icon="mdi:led-strip-variant",
    entity_registry_enabled_default=False,
)


def _normalize_rgb_color(value: Any) -> tuple[int, int, int] | None:
    """Normalize an RGB-like value to a strict 3-tuple."""
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        return None

    try:
        rgb = (int(value[0]), int(value[1]), int(value[2]))
    except TypeError, ValueError:
        return None

    if any(channel < 0 or channel > 255 for channel in rgb):
        return None
    return rgb


def _brightness_to_level(brightness: int, max_level: int) -> int:
    """Map HA brightness 1-255 onto equal buckets of native levels 1..max."""
    return max(1, math.ceil(brightness * max_level / 255))


def _level_to_brightness(level: int, max_level: int) -> int:
    """Report a native level as the top of its bucket, so it maps back exactly."""
    return level * 255 // max_level


def _normalize_rgbw_color(value: Any) -> tuple[int, int, int, int] | None:
    """Normalize an RGBW-like value to a strict 4-tuple."""
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        return None

    try:
        rgbw = (int(value[0]), int(value[1]), int(value[2]), int(value[3]))
    except TypeError, ValueError:
        return None

    if any(channel < 0 or channel > 255 for channel in rgbw):
        return None
    return rgbw


@records_entities(Platform.LIGHT)
async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: PlatformEntities,
) -> None:
    """Set up Adjustable Bed light entities."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    for runtime in entity_runtimes(coordinator):
        async_setup_dynamic_entities(
            entry,
            runtime,
            async_add_entities,
            partial(_light_entities_for, hass, runtime),
        )


def _light_entities_for(hass: HomeAssistant, coordinator: EntityRuntime) -> list[LightEntity]:
    """Build light entities for a single (child or standalone) coordinator."""
    controller = coordinator.capability_controller

    if controller is None:
        # No controller to read capabilities from (e.g. a paired side offline at
        # setup whose type can't be offline-minted).
        return []

    octo = octo_controller(controller)
    if octo is not None and not octo.controller_entity_discovery_complete:
        # Defer construction: legacy snapshots cannot provide a legal HA color
        # mode until CAP_END. The incomplete discovery also keeps the row.
        return []

    if octo is not None and not octo.supports_lights:
        return []

    toggle_only = (
        controller.supports_light_toggle_control
        and not controller.supports_discrete_light_control
        and not controller.supports_light_color_control
        and not controller.supports_light_state_feedback
        and not controller.light_color_control_pending
    )

    if controller.supports_light_color_control:
        return [AdjustableBedLight(coordinator, LIGHT_DESCRIPTION)]

    if octo is not None and octo.supports_discrete_light_control:
        # Main exposed OCTO's on/off-only capability as a switch. Keep its
        # registry identity and automations stable across this upgrade.
        return []

    if controller.supports_light_state_feedback or controller.supports_discrete_light_control:
        return [AdjustableBedOnOffLight(coordinator, LIGHT_DESCRIPTION)]

    if toggle_only and controller.exposes_assumed_toggle_light:
        return [AdjustableBedAssumedLight(coordinator)]
    return []


class AdjustableBedAssumedLight(AdjustableBedEntity, RestoreEntity, LightEntity):
    """Opt-in light state estimated from HA commands to a toggle-only controller."""

    entity_description = ASSUMED_LIGHT_DESCRIPTION
    _attr_should_poll = False
    _attr_assumed_state = True
    _attr_color_mode = ColorMode.ONOFF
    _attr_supported_color_modes = {ColorMode.ONOFF}

    def __init__(self, coordinator: EntityRuntime) -> None:
        """Start with an off estimate without sending a command to the bed."""
        super().__init__(coordinator, CARD_LIGHTING)
        description = self.entity_description
        self._attr_translation_key = description.translation_key or description.key
        self._attr_unique_id = coordinator.entity_unique_id(description.key)
        self._attr_is_on = False

    async def async_added_to_hass(self) -> None:
        """Restore only valid on/off estimates, without changing the bed."""
        await super().async_added_to_hass()
        if (last_state := await self.async_get_last_state()) is not None and last_state.state in (
            STATE_ON,
            STATE_OFF,
        ):
            self._attr_is_on = last_state.state == STATE_ON

    async def async_turn_on(self, **kwargs: object) -> None:
        """Toggle only when the current estimate is off."""
        await self._async_set_state(True)

    async def async_turn_off(self, **kwargs: object) -> None:
        """Toggle only when the current estimate is on."""
        await self._async_set_state(False)

    async def _async_set_state(self, is_on: bool) -> None:
        """Check and update the estimate inside the coordinator's command lock."""

        async def set_state(ctrl: BedController) -> None:
            if self._attr_is_on != is_on:
                await self._async_toggle_to(ctrl, is_on)

        await self._coordinator.async_execute_controller_command(set_state, cancel_running=False)

    async def async_toggle(self, **kwargs: object) -> None:
        """Always send one native toggle, then invert the estimate."""

        async def toggle(ctrl: BedController) -> None:
            await self._async_toggle_to(ctrl, not self._attr_is_on)

        await self._coordinator.async_execute_controller_command(toggle, cancel_running=False)

    async def _async_toggle_to(self, ctrl: BedController, is_on: bool) -> None:
        """Toggle, then move the estimate only if the toggle reached the light.

        An unsent toggle must not invert the estimate for good. Its first frame
        is the toggle, so a partly sent one counts, also when cancellation
        interrupts its release frames.
        """

        def show(delivery: Delivery) -> None:
            if delivery is not Delivery.NONE:
                self._attr_is_on = is_on
                self.async_write_ha_state()

        with delivered(show):
            await ctrl.lights_toggle()


class AdjustableBedLight(AdjustableBedEntity, RestoreEntity, LightEntity):
    """RGB/RGBW light entity for adjustable beds."""

    _attr_should_poll = False

    entity_description: LightEntityDescription

    _attr_assumed_state = True

    def __init__(
        self,
        coordinator: EntityRuntime,
        description: LightEntityDescription,
    ) -> None:
        """Initialize the light."""
        super().__init__(coordinator, CARD_LIGHTING)
        self.entity_description = description
        self._attr_translation_key = description.translation_key or description.key
        self._attr_unique_id = coordinator.entity_unique_id(description.key)

        # Use the capability controller (live when connected, else the client-free
        # one minted from config) so an OFFLINE offline-safe side still gets the
        # right colour mode / default colour instead of falling back to plain RGB.
        controller = coordinator.capability_controller
        octo = octo_controller(controller)
        if octo is not None:
            color_mode_str = octo.supported_color_mode
            color_modes = octo.supported_color_modes
        elif controller is not None:
            color_mode_str = controller.supported_color_mode
            color_modes = controller.supported_color_modes
        else:
            color_mode_str = None
            color_modes = ()
        mode_by_name = {
            "rgb": ColorMode.RGB,
            "rgbw": ColorMode.RGBW,
            "onoff": ColorMode.ONOFF,
        }
        supported_modes = {mode_by_name[mode] for mode in color_modes if mode in mode_by_name}
        is_octo = octo is not None
        if not supported_modes and not is_octo:
            # Preserve the established fallback used by controllers that do not
            # declare color modes. OCTO's plural capability set is authoritative.
            supported_modes = {ColorMode.RGBW if color_mode_str == "rgbw" else ColorMode.RGB}
        self._attr_supported_color_modes = supported_modes
        self._attr_color_mode = (
            mode_by_name.get(color_mode_str) if isinstance(color_mode_str, str) else None
        )
        if self._attr_color_mode not in supported_modes:
            self._attr_color_mode = next(iter(supported_modes), None)

        default_rgb = controller.default_light_rgb_color if controller is not None else None
        self._supports_desired_light_off = controller is not None and (
            controller.supports_discrete_light_control or controller.supports_light_state_feedback
        )
        self._default_rgb_color = _normalize_rgb_color(default_rgb)
        # HA brightness maps onto the bed's native 1..max levels when it has them.
        self._light_level_max: int | None = (
            controller.light_level_max
            if controller is not None and controller.supports_light_level_control
            else None
        )
        self._attr_is_on = False
        current_rgb = controller.current_light_rgb_color if controller is not None else None
        if current_rgb is None:
            current_rgb = coordinator.controller_state.get(UNDER_BED_LIGHTS_RGB)
        self._attr_rgb_color = _normalize_rgb_color(current_rgb) or self._default_rgb_color
        if ColorMode.RGBW in supported_modes:
            # Keep RGB, RGBW and intensity independent when both records exist.
            current_rgbw = (
                controller.current_light_rgbw_color if controller is not None else None
            )
            if current_rgbw is None:
                current_rgbw = coordinator.controller_state.get(UNDER_BED_LIGHTS_RGBW)
            normalized_rgbw = _normalize_rgbw_color(current_rgbw)
            if normalized_rgbw is not None:
                self._attr_rgbw_color = normalized_rgbw
            elif not is_octo and self._default_rgb_color is not None:
                r, g, b = self._default_rgb_color
                self._attr_rgbw_color = (r, g, b, 255)
            elif not is_octo:
                self._attr_rgbw_color = (255, 255, 255, 255)
            current_intensity = controller.light_intensity if controller is not None else None
            if current_intensity is None:
                current_intensity = coordinator.controller_state.get(LIGHT_INTENSITY)
            if type(current_intensity) is int and (
                0 <= current_intensity <= 255 if is_octo else 1 <= current_intensity <= 255
            ):
                self._attr_brightness = current_intensity
        self._last_octo_controls_available: bool | None = (
            octo.normal_controls_available if octo is not None else None
        )
        self._light_auto_off_timer: asyncio.TimerHandle | None = None
        self._light_auto_off_generation = 0
        self._light_auto_off_seconds = (
            octo.light_auto_off_seconds
            if octo is not None and octo.controller_entity_discovery_complete
            else None
        )
        self._light_turn_on_in_progress = False
        self._light_turn_off_in_progress = False
        self._last_controller_entity_available = self.available

    @property
    def available(self) -> bool:
        """Keep dynamically discovered OCTO lights unavailable when all caps disappear."""
        controller = self._coordinator.capability_controller
        octo = octo_controller(controller)
        if octo is not None:
            return (
                super().available
                and bool(octo.supports_lights)
                and bool(octo.supported_color_modes)
                and octo.normal_controls_available
            )
        return super().available and (
            controller is None
            or self.entity_description.key not in controller.unavailable_controller_entity_keys
        )

    async def async_added_to_hass(self) -> None:
        """Restore the last light state and subscribe to live light state."""
        await super().async_added_to_hass()

        # Restore the persisted HA state FIRST, then subscribe — registering the
        # callback can fire immediately with live bed state, which must win over
        # the older restored value rather than be overwritten by it.
        if (last_state := await self.async_get_last_state()) is not None:
            self._attr_is_on = last_state.state == STATE_ON
            if self._attr_color_mode == ColorMode.RGBW:
                restored_rgbw = _normalize_rgbw_color(last_state.attributes.get(ATTR_RGBW_COLOR))
                if restored_rgbw is not None:
                    self._attr_rgbw_color = restored_rgbw
            else:
                restored_rgb = _normalize_rgb_color(last_state.attributes.get(ATTR_RGB_COLOR))
                if restored_rgb is not None:
                    self._attr_rgb_color = restored_rgb
            restored_brightness = last_state.attributes.get(ATTR_BRIGHTNESS)
            if self._light_level_max is not None and type(restored_brightness) is int:
                self._attr_brightness = restored_brightness

        # Reflect bed-reported on/off + colour where the controller publishes it
        # (e.g. Leggett Gen2). No-op for controllers that don't report light state.
        self._unregister_light_state = self._coordinator.register_controller_state_callback(
            self._handle_light_state
        )

    async def async_will_remove_from_hass(self) -> None:
        """Cancel auto-off expiry and unsubscribe from live light-state updates."""
        self._cancel_light_auto_off_timer()
        unregister = getattr(self, "_unregister_light_state", None)
        if unregister is not None:
            unregister()
            self._unregister_light_state = None
        await super().async_will_remove_from_hass()

    @callback
    def _handle_light_state(self, state: ControllerState) -> None:
        """Update on/off + colour from controller-reported light state.

        Only writes HA state when a value actually changes, to avoid event churn
        on repeated/identical telemetry packets.
        """
        available = self.available
        changed = available != self._last_controller_entity_available
        self._last_controller_entity_available = available
        was_on = self._attr_is_on
        controller = self._coordinator.capability_controller
        octo = octo_controller(controller)
        active_modes: set[ColorMode] = self._attr_supported_color_modes or set()
        if octo is not None:
            available = octo.normal_controls_available
            if available != self._last_octo_controls_available:
                self._last_octo_controls_available = available
                changed = True
            mode_by_name = {
                "rgb": ColorMode.RGB,
                "rgbw": ColorMode.RGBW,
                "onoff": ColorMode.ONOFF,
            }
            active_modes = {
                mode_by_name[mode] for mode in octo.supported_color_modes if mode in mode_by_name
            }
            if active_modes != (self._attr_supported_color_modes or set()):
                self._attr_supported_color_modes = active_modes
                changed = True
            if ColorMode.RGB not in active_modes and self._attr_rgb_color is not None:
                self._attr_rgb_color = None
                changed = True
            if ColorMode.RGBW not in active_modes:
                if self._attr_rgbw_color is not None:
                    self._attr_rgbw_color = None
                    changed = True
                if self._attr_brightness is not None:
                    self._attr_brightness = None
                    changed = True
            if self._attr_color_mode not in active_modes:
                preferred = (
                    mode_by_name.get(octo.supported_color_mode)
                    if octo.supported_color_mode is not None
                    else None
                )
                if preferred not in active_modes:
                    preferred = next(iter(active_modes), None)
                if preferred != self._attr_color_mode:
                    self._attr_color_mode = preferred
                    changed = True
            if not active_modes and self._attr_is_on:
                self._attr_is_on = False
                changed = True
        if UNDER_BED_LIGHTS_ON in state:
            reported_state = state[UNDER_BED_LIGHTS_ON]
            if not (octo is not None and reported_state is None):
                is_on = bool(reported_state)
                if is_on != self._attr_is_on:
                    self._attr_is_on = is_on
                    changed = True
        octo_modes = active_modes if octo is not None else {ColorMode.RGB, ColorMode.RGBW}
        rgb = _normalize_rgb_color(state.get(UNDER_BED_LIGHTS_RGB))
        if (
            UNDER_BED_LIGHTS_RGB in state
            and ColorMode.RGB in octo_modes
            and rgb != self._attr_rgb_color
        ):
            self._attr_rgb_color = rgb
            changed = True
        rgbw = _normalize_rgbw_color(state.get(UNDER_BED_LIGHTS_RGBW))
        if (
            UNDER_BED_LIGHTS_RGBW in state
            and ColorMode.RGBW in octo_modes
            and rgbw != self._attr_rgbw_color
        ):
            self._attr_rgbw_color = rgbw
            changed = True
        intensity = state.get(LIGHT_INTENSITY)
        normalized_intensity = (
            intensity
            if type(intensity) is int
            and (0 <= intensity <= 255 if octo is not None else 1 <= intensity <= 255)
            else None
        )
        if (
            LIGHT_INTENSITY in state
            and (octo is None or ColorMode.RGBW in octo_modes)
            and normalized_intensity != self._attr_brightness
        ):
            self._attr_brightness = normalized_intensity
            changed = True

        if octo is not None and not (
            self._light_turn_on_in_progress or self._light_turn_off_in_progress
        ):
            if octo.controller_entity_discovery_complete and not octo.supports_lights:
                self._cancel_light_auto_off_timer()
            else:
                if OCTO_LIGHT_DURATION in state:
                    duration = (
                        octo.light_auto_off_seconds
                        if octo.controller_entity_discovery_complete
                        else None
                    )
                    if duration != self._light_auto_off_seconds:
                        self._light_auto_off_seconds = duration
                        if self._attr_is_on:
                            self._schedule_light_auto_off_timer()
                        else:
                            self._cancel_light_auto_off_timer()

                if UNDER_BED_LIGHTS_ON in state:
                    reported_state = state[UNDER_BED_LIGHTS_ON]
                    if reported_state is True:
                        if not was_on or self._light_auto_off_timer is None:
                            self._schedule_light_auto_off_timer()
                    elif reported_state is False:
                        self._cancel_light_auto_off_timer()
        level = state.get(LIGHT_LEVEL)
        if LIGHT_LEVEL in state and self._light_level_max is not None:
            brightness = (
                _level_to_brightness(level, self._light_level_max)
                if type(level) is int and 0 <= level <= self._light_level_max
                else None
            )
            if brightness != self._attr_brightness:
                self._attr_brightness = brightness
                changed = True
        if changed:
            self.async_write_ha_state()

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the light on and optionally set a specific color."""
        requested_rgbw = _normalize_rgbw_color(kwargs.get(ATTR_RGBW_COLOR))
        requested_rgb = _normalize_rgb_color(kwargs.get(ATTR_RGB_COLOR))
        supported_modes = self._attr_supported_color_modes or set()
        if requested_rgbw is not None and ColorMode.RGBW not in supported_modes:
            raise ValueError("RGBW color is not supported by this light")
        if requested_rgb is not None and ColorMode.RGB not in supported_modes:
            raise ValueError("RGB color is not supported by this light")
        explicit = (
            ColorMode.RGBW
            if requested_rgbw is not None
            else ColorMode.RGB
            if requested_rgb is not None
            else None
        )
        shown: Callable[[], None] | None = None

        async def turn_on(ctrl: BedController) -> None:
            nonlocal shown
            # Resolved inside the serialized command, so a request without a
            # color follows the last mode actually sent, never a dropped one.
            mode = explicit or self._attr_color_mode
            if mode == ColorMode.RGBW:
                shown = await self._send_rgbw(ctrl, kwargs)
            elif mode == ColorMode.RGB:
                shown = await self._send_rgb(ctrl, kwargs)
            elif mode == ColorMode.ONOFF:
                await ctrl.lights_on()
                shown = self._shown_on
            else:
                raise ValueError("This light has no active color mode")

        def show(delivery: Delivery) -> None:
            if delivery is Delivery.NONE:
                return
            if delivery is Delivery.SENT and shown is not None:
                shown()
            else:
                # Part of the request reached the light.
                self._attr_is_on = None
            self.async_write_ha_state()

        self._light_turn_on_in_progress = True
        try:
            delivery = await self._async_send(turn_on, on_delivery=show, cancel_running=False)
        finally:
            self._light_turn_on_in_progress = False
        if delivery is Delivery.SENT:
            self._schedule_light_auto_off_timer()

    def _shown_on(self) -> None:
        self._attr_is_on = True

    async def _send_rgb(self, ctrl: BedController, kwargs: Mapping[str, Any]) -> Callable[[], None]:
        """Send an RGB turn-on; return how to show it once it was sent."""
        requested_rgb = _normalize_rgb_color(kwargs.get(ATTR_RGB_COLOR))
        target_rgb = requested_rgb or self._attr_rgb_color or self._default_rgb_color
        # Turning on from off resends the known brightness: the bed may not keep
        # its level across a power-on, or may have lost it across an HA restart.
        requested_brightness = kwargs.get(ATTR_BRIGHTNESS)
        brightness = requested_brightness or (None if self._attr_is_on else self._attr_brightness)
        level = (
            _brightness_to_level(brightness, self._light_level_max)
            if self._light_level_max is not None and isinstance(brightness, int) and brightness > 0
            else None
        )
        # A brightness-only change on a lit light needs no colour write.
        brightness_only = (
            level is not None
            and requested_brightness is not None
            and requested_rgb is None
            and self._attr_is_on
        )
        if not brightness_only:
            if ctrl.supports_explicit_light_on_control:
                await ctrl.lights_on()
            elif target_rgb is None:
                if ctrl.supports_light_toggle_control:
                    if not self._attr_is_on:
                        await ctrl.lights_toggle()
                else:
                    raise ValueError("No RGB color available for this light")
            if target_rgb is not None:
                await ctrl.set_light_color(target_rgb)
        if level is not None:
            await ctrl.set_light_level(level)

        def shown() -> None:
            self._attr_color_mode = ColorMode.RGB
            self._attr_is_on = True
            self._attr_rgb_color = target_rgb
            if level is not None and self._light_level_max is not None:
                self._attr_brightness = _level_to_brightness(level, self._light_level_max)

        return shown

    async def _send_rgbw(
        self, ctrl: BedController, kwargs: Mapping[str, Any]
    ) -> Callable[[], None]:
        """Send an RGBW turn-on; return how to show it once it was sent."""
        requested_rgbw = _normalize_rgbw_color(kwargs.get(ATTR_RGBW_COLOR))
        target_rgbw = requested_rgbw or self._attr_rgbw_color or (255, 255, 255, 255)
        requested_brightness = kwargs.get(ATTR_BRIGHTNESS)
        intensity = (
            max(0, min(255, requested_brightness)) if type(requested_brightness) is int else None
        )
        if ctrl.supports_explicit_light_on_control:
            await ctrl.lights_on()
        await ctrl.set_light_color_rgbw(target_rgbw, intensity)

        def shown() -> None:
            self._attr_color_mode = ColorMode.RGBW
            self._attr_is_on = True
            self._attr_rgbw_color = target_rgbw
            if intensity is not None:
                self._attr_brightness = intensity

        return shown

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the light off using the controller's light-off semantics."""
        del kwargs

        if not self._attr_is_on and not self._supports_desired_light_off:
            _LOGGER.debug(
                "Skipping toggle-based light off for %s because HA already believes it is off",
                self._coordinator.name,
            )
            return

        async def _turn_off(ctrl: BedController) -> None:
            if ctrl.supports_discrete_light_control or ctrl.supports_light_state_feedback:
                await ctrl.lights_off()
                return
            if ctrl.supports_light_toggle_control:
                await ctrl.lights_toggle()
                return
            raise NotImplementedError("Light off control not supported on this bed")

        def show(delivery: Delivery) -> None:
            # Shown inside the command, before a queued turn-on reads it.
            if delivery is not Delivery.NONE:
                # Partly sent leaves the light unknown.
                self._attr_is_on = False if delivery is Delivery.SENT else None
                self.async_write_ha_state()

        delivery = Delivery.NONE
        self._light_turn_off_in_progress = True
        try:
            delivery = await self._async_send(_turn_off, on_delivery=show, cancel_running=False)
        finally:
            self._light_turn_off_in_progress = False
        if delivery is not Delivery.NONE:
            self._cancel_light_auto_off_timer()

    def _current_octo_timer_controller(self) -> OctoController | None:
        """Return this light's authoritative live OCTO controller, if any."""
        controller = self._coordinator.controller or self._coordinator.capability_controller
        octo = octo_controller(controller)
        if octo is None or not octo.controller_entity_discovery_complete:
            return None
        return octo

    def _cancel_light_auto_off_timer(self) -> None:
        """Invalidate any pending OCTO light expiry callback."""
        self._light_auto_off_generation += 1
        if self._light_auto_off_timer is not None:
            self._light_auto_off_timer.cancel()
            self._light_auto_off_timer = None

    def _schedule_light_auto_off_timer(self) -> None:
        """Track OCTO's positive hardware light timeout in the HA light entity."""
        self._cancel_light_auto_off_timer()
        if self.entity_description.key != "under_bed_lights" or not self._attr_is_on:
            return
        controller = self._current_octo_timer_controller()
        if controller is None:
            return
        auto_off_seconds = controller.light_auto_off_seconds
        self._light_auto_off_seconds = auto_off_seconds
        if auto_off_seconds is None:
            return

        generation = self._light_auto_off_generation

        def auto_off_callback() -> None:
            """Publish the bed's expected hardware expiry without another write."""
            if generation != self._light_auto_off_generation:
                return
            self._light_auto_off_generation += 1
            self._light_auto_off_timer = None
            current = self._current_octo_timer_controller()
            if (
                current is None
                or current.light_auto_off_seconds != auto_off_seconds
                or not self._attr_is_on
            ):
                return
            self._attr_is_on = False
            current.on_light_auto_off()
            self.async_write_ha_state()

        self._light_auto_off_timer = self.hass.loop.call_later(auto_off_seconds, auto_off_callback)


class AdjustableBedOnOffLight(AdjustableBedEntity, RestoreEntity, LightEntity):
    """On/off under-bed light, optionally driven solely by device feedback."""

    _attr_should_poll = False
    entity_description: LightEntityDescription

    _attr_color_mode = ColorMode.ONOFF
    _attr_supported_color_modes = {ColorMode.ONOFF}

    def __init__(
        self,
        coordinator: EntityRuntime,
        description: LightEntityDescription,
    ) -> None:
        """Initialize the on/off light."""
        super().__init__(coordinator, CARD_LIGHTING)
        self.entity_description = description
        self._attr_translation_key = description.translation_key or description.key
        self._attr_unique_id = coordinator.entity_unique_id(description.key)
        self._attr_is_on: bool | None = None
        controller = coordinator.capability_controller
        self._feedback_only = controller is not None and controller.supports_light_state_feedback
        self._initialize_off = controller is not None and controller.light_state_starts_off
        # The app's intended level stands in for a readback the bed never sends.
        self._level_intent = (
            controller is not None and controller.light_switch_follows_level_intent
        )
        self._attr_assumed_state = self._level_intent or (
            controller is not None and controller.light_state_is_assumed
        )
        if self._level_intent:
            self._attr_is_on = self._level_is_on(coordinator.controller_state.get(LIGHT_LEVEL))
        self._auto_off_timer: asyncio.TimerHandle | None = None
        # Counts published light state, so a command's assumed result never
        # overwrites state the bed published while the command ran.
        self._state_generation = 0
        self._unregister_callback: Callable[[], None] | None = None
        self._unregister_connection: Callable[[], None] | None = None

    @staticmethod
    def _level_is_on(level: object) -> bool | None:
        return level > 0 if type(level) is int and level >= 0 else None

    async def async_added_to_hass(self) -> None:
        """Subscribe to controller-state updates for the light."""
        await super().async_added_to_hass()
        if (
            not self._feedback_only
            and not self._initialize_off
            and not self._attr_assumed_state
            and (last_state := await self.async_get_last_state()) is not None
            and last_state.state in (STATE_ON, STATE_OFF)
        ):
            self._attr_is_on = last_state.state == STATE_ON
        self._unregister_callback = self._coordinator.register_controller_state_callback(
            self._handle_controller_state_update
        )
        if self._feedback_only:
            self._unregister_connection = self._coordinator.register_connection_state_callback(
                self._handle_connection_state_update
            )
        if self._initialize_off:
            # Establish a known physical state once per entity load, not on BLE
            # reconnects. A failed write must leave the light unknown.
            try:
                await self.async_turn_off()
            except (
                HomeAssistantError,
                BleakError,
                ConnectionError,
                TimeoutError,
                RuntimeError,
            ) as err:
                _LOGGER.warning("Could not initialize under-bed light for %s: %s", self.name, err)

    async def async_will_remove_from_hass(self) -> None:
        """Clean up controller-state callback registration."""
        self._cancel_auto_off()
        if self._unregister_callback is not None:
            self._unregister_callback()
            self._unregister_callback = None
        if self._unregister_connection is not None:
            self._unregister_connection()
            self._unregister_connection = None
        await super().async_will_remove_from_hass()

    @callback
    def _handle_connection_state_update(self, connected: bool) -> None:
        """Invalidate feedback across both clean and unexpected disconnects."""
        if not connected:
            self._attr_is_on = None
            self.async_write_ha_state()
        else:
            self._handle_controller_state_update(self._coordinator.controller_state)

    @callback
    def _handle_controller_state_update(self, state: ControllerState) -> None:
        """Update state from published light state.

        Feedback controllers publish what the bed reported on the current link,
        so the light is unknown while no controller is connected.
        """
        if self._level_intent:
            if LIGHT_LEVEL not in state or (is_on := self._level_is_on(state[LIGHT_LEVEL])) is None:
                return
            self._attr_is_on = is_on
        else:
            key = sided(UNDER_BED_LIGHTS_ON, self._coordinator.controller_side)
            if key not in state:
                key = UNDER_BED_LIGHTS_ON
            if key not in state:
                return
            value = state[key]
            if self._feedback_only and self._coordinator.controller is None:
                value = None
            self._attr_is_on = None if value is None else bool(value)
        self._state_generation += 1
        self._schedule_auto_off()
        self.async_write_ha_state()

    def _cancel_auto_off(self) -> None:
        if self._auto_off_timer is not None:
            self._auto_off_timer.cancel()
            self._auto_off_timer = None

    def _schedule_auto_off(self) -> None:
        """Follow a bed whose light switches itself off after a set time."""
        controller = self._coordinator.controller
        if controller is None and self._attr_is_on:
            return  # Offline: the bed's own timer keeps running, so keep ours.
        self._cancel_auto_off()
        if controller is None or not self._attr_is_on:
            return
        seconds = controller.light_auto_off_seconds
        if seconds is None:
            return

        def expire() -> None:
            # The bed's own timer runs on after an idle disconnect.
            self._auto_off_timer = None
            if not self._attr_is_on:
                return
            controller.on_light_auto_off()
            self._attr_is_on = False
            self.async_write_ha_state()

        self._auto_off_timer = self.hass.loop.call_later(seconds, expire)

    async def async_turn_on(self, **kwargs: object) -> None:
        """Turn the under-bed light on."""
        del kwargs

        generation = self._state_generation

        async def _turn_on(ctrl: BedController) -> None:
            nonlocal generation
            generation = self._state_generation
            await ctrl.lights_on()

        def show(delivery: Delivery) -> None:
            # Published state wins; a value sent only in part is unknown.
            if (
                not self._feedback_only
                and delivery is not Delivery.NONE
                and generation == self._state_generation
            ):
                self._attr_is_on = True if delivery is Delivery.SENT else None
                if delivery is Delivery.SENT:
                    self._schedule_auto_off()
                self.async_write_ha_state()

        await self._async_send(_turn_on, on_delivery=show, cancel_running=False)

    async def async_turn_off(self, **kwargs: object) -> None:
        """Turn the under-bed light off."""
        del kwargs

        generation = self._state_generation

        async def _turn_off(ctrl: BedController) -> None:
            nonlocal generation
            generation = self._state_generation
            await ctrl.lights_off()

        def show(delivery: Delivery) -> None:
            if (
                not self._feedback_only
                and delivery is not Delivery.NONE
                and generation == self._state_generation
            ):
                self._attr_is_on = False if delivery is Delivery.SENT else None
                if delivery is Delivery.SENT:
                    self._cancel_auto_off()
                self.async_write_ha_state()

        await self._async_send(_turn_off, on_delivery=show, cancel_running=False)

    async def async_toggle(self, **kwargs: object) -> None:
        """Use discrete commands with known feedback, or a native toggle."""
        if not self._feedback_only:
            await super().async_toggle(**kwargs)
            return

        async def toggle(ctrl: BedController) -> None:
            if ctrl.supports_light_toggle_control:
                await ctrl.lights_toggle()
            elif ctrl.supports_discrete_light_control:
                if not isinstance(self.is_on, bool):
                    raise invalid("light_toggle_state_unknown")
                if self.is_on:
                    await ctrl.lights_off()
                else:
                    await ctrl.lights_on()
            else:
                raise invalid("not_supported_by_bed", feature="toggling the light")

        await self._coordinator.async_execute_controller_command(toggle, cancel_running=False)
