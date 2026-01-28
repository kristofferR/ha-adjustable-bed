"""Switch entities for Adjustable Bed integration."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

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
        required_capability="supports_discrete_light_control",
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
            # Default to False: only create entity if controller explicitly supports it
            if not getattr(controller, description.required_capability, False):
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
        # Cache discrete control capability at init (controller should exist at setup time)
        # Default to False for toggle-only beds when controller disconnects
        controller = coordinator.controller
        self._supports_discrete_light_control = (
            getattr(controller, "supports_discrete_light_control", False)
            if controller is not None
            else False
        )
        # Timer handle for auto-off state updates (e.g., Octo lights turn off after 5 min)
        self._auto_off_timer: asyncio.TimerHandle | None = None

    def _supports_discrete_control(self) -> bool:
        """Check if controller supports discrete on/off (vs toggle-only)."""
        return self._supports_discrete_light_control

    def _cancel_auto_off_timer(self) -> None:
        """Cancel any pending auto-off timer."""
        if self._auto_off_timer is not None:
            self._auto_off_timer.cancel()
            self._auto_off_timer = None
            _LOGGER.debug("Cancelled auto-off timer for %s", self.entity_description.key)

    def _schedule_auto_off_timer(self) -> None:
        """Schedule auto-off timer if controller reports a light auto-off timeout.

        Some beds (e.g., Octo) have hardware-enforced light timeouts where the
        lights automatically turn off after a fixed duration. This method
        schedules a timer to update the HA state to reflect the hardware behavior.
        """
        controller = self._coordinator.controller
        if controller is None:
            return

        auto_off_seconds = getattr(controller, "light_auto_off_seconds", None)
        if auto_off_seconds is None:
            return

        # Cancel any existing timer first
        self._cancel_auto_off_timer()

        def auto_off_callback() -> None:
            """Update state to off when hardware auto-off occurs."""
            _LOGGER.debug(
                "Auto-off timer fired for %s after %d seconds",
                self.entity_description.key,
                auto_off_seconds,
            )
            self._auto_off_timer = None
            self._attr_is_on = False
            self.async_write_ha_state()

        # Schedule the timer using the event loop
        self._auto_off_timer = self.hass.loop.call_later(
            auto_off_seconds, auto_off_callback
        )
        _LOGGER.debug(
            "Scheduled auto-off timer for %s in %d seconds",
            self.entity_description.key,
            auto_off_seconds,
        )

    async def async_will_remove_from_hass(self) -> None:
        """Clean up when entity is removed."""
        self._cancel_auto_off_timer()
        await super().async_will_remove_from_hass()

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
            # Only update assumed state if controller supports discrete on/off
            # Toggle-only controllers can't reliably track state
            if self._supports_discrete_control():
                self._attr_is_on = True
                self.async_write_ha_state()
                # Schedule auto-off timer if the bed has hardware auto-off
                self._schedule_auto_off_timer()
            else:
                _LOGGER.debug(
                    "Toggle-only controller - state tracking unreliable for %s",
                    self.entity_description.key,
                )
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

        # Cancel any pending auto-off timer since we're manually turning off
        self._cancel_auto_off_timer()

        try:
            _LOGGER.debug("Sending turn off command for %s", self.entity_description.key)
            await self._coordinator.async_execute_controller_command(
                self.entity_description.turn_off_fn,
                cancel_running=False,
            )
            # Only update assumed state if controller supports discrete on/off
            # Toggle-only controllers can't reliably track state
            if self._supports_discrete_control():
                self._attr_is_on = False
                self.async_write_ha_state()
            else:
                _LOGGER.debug(
                    "Toggle-only controller - state tracking unreliable for %s",
                    self.entity_description.key,
                )
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
