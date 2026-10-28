"""Switch entities for Adjustable Bed integration."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    BED_TYPE_LINAK,
    BED_TYPE_REMACRO,
    BED_TYPE_SLEEP_NUMBER_MCR,
    BED_TYPE_SVANE,
    BED_TYPE_VIBRADORM_APP,
    DOMAIN,
    OKIN_BEDDING_APP_BED_TYPES,
)
from .entity import AdjustableBedEntity
from .entity_discovery import async_setup_dynamic_entities
from .entity_runtime import EntityRuntime
from .octo_runtime import octo_controller
from .paired_coordinator import entity_runtimes

if TYPE_CHECKING:
    from .beds.base import BedController
    from .beds.octo import OctoController

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class AdjustableBedSwitchEntityDescription(SwitchEntityDescription):
    """Describes a Adjustable Bed switch entity."""

    turn_on_fn: Callable[[BedController], Coroutine[Any, Any, None]]
    turn_off_fn: Callable[[BedController], Coroutine[Any, Any, None]]
    # Capability property name to check on controller (e.g., "supports_lights")
    required_capability: str | None = None
    # Only create entity for these bed types (None = all bed types)
    required_bed_types: tuple[str, ...] | None = None
    # True if the switch has separate on/off commands (enables state tracking)
    # When False, the switch is treated as toggle-only (no state tracking)
    has_discrete_control: bool = False
    # Optional controller-state key for readback/assumed-state publication.
    state_key: str | None = None


SWITCH_DESCRIPTIONS: tuple[AdjustableBedSwitchEntityDescription, ...] = (
    AdjustableBedSwitchEntityDescription(
        key="automatic_light",
        translation_key="automatic_light",
        icon="mdi:lightbulb-auto",
        turn_on_fn=lambda ctrl: ctrl.set_automatic_light(True),
        turn_off_fn=lambda ctrl: ctrl.set_automatic_light(False),
        required_capability="supports_automatic_light",
        has_discrete_control=True,
        state_key="automatic_light",
    ),
    AdjustableBedSwitchEntityDescription(
        key="under_bed_lights",
        translation_key="under_bed_lights",
        icon="mdi:lightbulb",
        turn_on_fn=lambda ctrl: ctrl.lights_on(),
        turn_off_fn=lambda ctrl: ctrl.lights_off(),
        required_capability="supports_discrete_light_control",
    ),
    AdjustableBedSwitchEntityDescription(
        key="linak_automatic_drive",
        translation_key="linak_automatic_drive",
        icon="mdi:car-shift-pattern",
        turn_on_fn=lambda ctrl: ctrl.set_automatic_drive(True),
        turn_off_fn=lambda ctrl: ctrl.set_automatic_drive(False),
        required_capability="supports_automatic_drive",
        entity_registry_enabled_default=False,
        has_discrete_control=True,
        state_key="linak_automatic_drive",
    ),
    AdjustableBedSwitchEntityDescription(
        key="synchro_mode",
        translation_key="synchro_mode",
        icon="mdi:link-variant",
        turn_on_fn=lambda ctrl: ctrl.set_synchro(True),
        turn_off_fn=lambda ctrl: ctrl.set_synchro(False),
        required_capability="supports_synchro",
        entity_registry_enabled_default=False,
        has_discrete_control=True,
        state_key="synchro_mode",
    ),
    AdjustableBedSwitchEntityDescription(
        key="remote_control_lock",
        translation_key="remote_control_lock",
        icon="mdi:remote-lock",
        turn_on_fn=lambda ctrl: ctrl.set_remote_control_lock(True),
        turn_off_fn=lambda ctrl: ctrl.set_remote_control_lock(False),
        required_capability="supports_remote_control_lock",
        has_discrete_control=True,
        state_key="remote_control_lock",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Adjustable Bed switch entities."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    for runtime in entity_runtimes(coordinator):
        async_setup_dynamic_entities(
            entry,
            runtime,
            async_add_entities,
            lambda runtime=runtime: _switch_entities_for(hass, runtime),
        )


def _switch_entities_for(
    hass: HomeAssistant, coordinator: EntityRuntime
) -> list[AdjustableBedSwitch]:
    """Build switch entities for a single (child or standalone) coordinator."""
    # capability_controller: an offline paired side (e.g. Linak under-bed lights)
    # still gets its switches built from a client-free controller minted from
    # config (see coordinator).
    controller = coordinator.capability_controller
    octo = octo_controller(controller)
    registry = er.async_get(hass)

    if octo is not None and not octo.controller_entity_discovery_complete:
        # Legacy paired Octo snapshots contain capability booleans but no
        # complete record set. Keep previously registered switches available to
        # HA as offline entity rows, while the entity availability gate below
        # prevents writes until live discovery provides authoritative records.
        entities = [
            AdjustableBedSwitch(coordinator, description)
            for description in SWITCH_DESCRIPTIONS
            if registry.async_get_entity_id(
                "switch",
                DOMAIN,
                coordinator.entity_unique_id(description.key),
            )
            is not None
        ]
        if octo.legacy_light_fallback and not any(
            entity.entity_description.key == "under_bed_lights" for entity in entities
        ):
            entities.append(
                AdjustableBedSwitch(
                    coordinator,
                    next(
                        description
                        for description in SWITCH_DESCRIPTIONS
                        if description.key == "under_bed_lights"
                    ),
                )
            )
        return entities

    entities = []
    for description in SWITCH_DESCRIPTIONS:
        if octo is not None and description.key == "under_bed_lights":
            existing = registry.async_get_entity_id(
                "switch",
                DOMAIN,
                coordinator.entity_unique_id(description.key),
            )
            if existing is not None and not octo.supports_lights:
                registry.async_remove(existing)
                existing = None
            if (
                existing is not None
                or octo.legacy_light_fallback
                or (octo.supports_discrete_light_control and not octo.supports_light_color_control)
            ):
                entities.append(AdjustableBedSwitch(coordinator, description))
            # OCTO keeps this legacy switch identity. Color surfaces use the
            # light platform without deleting a user's existing switch row.
            continue
        if (
            description.key == "under_bed_lights"
            and controller is not None
            and (
                controller.supports_light_color_control
                or controller.supports_light_state_feedback
                or controller.supported_color_modes == frozenset(("onoff",))
                or (
                    coordinator.bed_type in (BED_TYPE_LINAK, BED_TYPE_SLEEP_NUMBER_MCR)
                    and controller.supports_discrete_light_control
                )
            )
        ):
            entity_id = registry.async_get_entity_id(
                "switch",
                DOMAIN,
                coordinator.entity_unique_id(description.key),
            )
            if entity_id is not None:
                registry.async_remove(entity_id)
            continue
        # Skip switches restricted to specific bed types
        if description.required_bed_types is not None:
            if coordinator.bed_type not in description.required_bed_types:
                continue
        # Skip switches that require capabilities the controller doesn't have
        if description.required_capability is not None:
            if controller is None:
                continue
            # Default to False: only create entity if controller explicitly supports it
            if not getattr(controller, description.required_capability, False):
                # Older releases may have created this switch before the
                # capability was dropped (e.g. BedTech discrete lights, #410);
                # remove the stale registry entry so a dead control doesn't
                # linger in the UI and card.
                entity_id = registry.async_get_entity_id(
                    "switch",
                    DOMAIN,
                    coordinator.entity_unique_id(description.key),
                )
                if entity_id is not None:
                    registry.async_remove(entity_id)
                continue
        entities.append(AdjustableBedSwitch(coordinator, description))

    return entities


class AdjustableBedSwitch(AdjustableBedEntity, SwitchEntity):
    """Switch entity for Adjustable Bed."""

    entity_description: AdjustableBedSwitchEntityDescription

    @property
    def available(self) -> bool:
        """Keep Octo setting switches unavailable while its PIN gate is locked."""
        controller = self._coordinator.capability_controller
        octo = octo_controller(controller)
        if octo is None:
            return super().available
        if self.entity_description.key == "under_bed_lights":
            return (
                super().available
                and octo.normal_controls_available
                and (
                    octo.legacy_light_fallback
                    or octo.controller_entity_discovery_complete
                    and octo.supports_discrete_light_control
                )
            )
        return (
            super().available
            and octo.controller_entity_discovery_complete
            and octo.normal_controls_available
        )

    def __init__(
        self,
        coordinator: EntityRuntime,
        description: AdjustableBedSwitchEntityDescription,
    ) -> None:
        """Initialize the switch."""
        super().__init__(coordinator)
        self.entity_description = description
        self._set_sided_translation_key(description.translation_key, description.key)
        self._attr_unique_id = coordinator.entity_unique_id(description.key)
        self._app_floor_intent = (
            description.key == "under_bed_lights" and coordinator.bed_type == BED_TYPE_VIBRADORM_APP
        )
        controller = coordinator.capability_controller
        if description.state_key is None:
            self._attr_is_on = False
            if description.key == "under_bed_lights" and (
                coordinator.bed_type
                in {*OKIN_BEDDING_APP_BED_TYPES, BED_TYPE_REMACRO, BED_TYPE_SVANE}
                or (controller is not None and controller.light_state_is_assumed)
            ):
                # These apps have on/off commands but no physical state response.
                self._attr_is_on = None
                self._attr_assumed_state = True
            elif self._app_floor_intent:
                # The selected app publishes intended level, never physical readback.
                level = coordinator.controller_state.get("light_level")
                self._attr_is_on = level > 0 if type(level) is int and level >= 0 else None
                self._attr_assumed_state = True
        else:
            initial_state = coordinator.controller_state.get(description.state_key)
            self._attr_is_on = initial_state if isinstance(initial_state, bool) else None
            # Linak publishes the state after our own write, but the app does
            # not decode configuration notifications into authoritative
            # automatic-drive state. Start unknown after a reload and mark the
            # commanded value as assumed instead of reporting a false readback.
            self._attr_assumed_state = True
        # Cache discrete control capability at init. Use capability_controller so
        # a switch created for an offline paired side still caches the correct
        # capability (from the client-free controller) instead of defaulting to
        # False; the live controller takes over for actual commands.
        self._supports_discrete_light_control = (
            controller is not None and controller.supports_discrete_light_control
        )
        # Timer handle for auto-off state updates (e.g., Octo lights turn off after 5 min)
        self._auto_off_timer: asyncio.TimerHandle | None = None
        self._octo_light_auto_off_generation = 0
        octo = octo_controller(controller)
        self._octo_light_auto_off_seconds = (
            octo.light_auto_off_seconds
            if octo is not None
            and (octo.controller_entity_discovery_complete or octo.legacy_light_fallback)
            else None
        )
        self._state_unregister_callback: Callable[[], None] | None = None

    async def async_added_to_hass(self) -> None:
        """Register for controller-state updates when available."""
        await super().async_added_to_hass()
        if (
            self.entity_description.key != "under_bed_lights"
            and self.entity_description.state_key is None
        ):
            return
        self._state_unregister_callback = self._coordinator.register_controller_state_callback(
            self._handle_controller_state_update
        )

    @callback
    def _handle_controller_state_update(self, state: dict[str, Any]) -> None:
        """Update the switch when the controller publishes light state."""
        if self.entity_description.key == "under_bed_lights" and "octo_light_duration" in state:
            octo = self._current_octo_timer_controller()
            if octo is not None:
                self._schedule_octo_auto_off_timer(octo)
        state_key = (
            "light_level"
            if self._app_floor_intent
            else self.entity_description.state_key or "under_bed_lights_on"
        )
        if state_key not in state:
            return
        if self._app_floor_intent and (type(state[state_key]) is not int or state[state_key] < 0):
            return
        self._attr_is_on = bool(state[state_key])
        if self.entity_description.key != "under_bed_lights":
            self.async_write_ha_state()
            return
        if self._attr_is_on:
            self._schedule_auto_off_timer()
        else:
            self._cancel_auto_off_timer()
        self.async_write_ha_state()

    def _supports_discrete_control(self) -> bool:
        """Check if controller supports discrete on/off (vs toggle-only)."""
        return self._supports_discrete_light_control or self.entity_description.has_discrete_control

    def _cancel_auto_off_timer(self) -> None:
        """Cancel any pending auto-off timer."""
        self._octo_light_auto_off_generation += 1
        if self._auto_off_timer is not None:
            self._auto_off_timer.cancel()
            self._auto_off_timer = None
            _LOGGER.debug("Cancelled auto-off timer for %s", self.entity_description.key)

    def _current_octo_timer_controller(self) -> OctoController | None:
        """Return this switch's current authoritative or legacy OCTO controller."""
        controller = self._coordinator.controller or self._coordinator.capability_controller
        octo = octo_controller(controller)
        if octo is None or not (
            octo.controller_entity_discovery_complete or octo.legacy_light_fallback
        ):
            return None
        return octo

    def _schedule_octo_auto_off_timer(
        self, octo: OctoController, *, reset_deadline: bool = False
    ) -> None:
        """Preserve the hardware expiry across equivalent OCTO controller handoff."""
        auto_off_seconds = octo.light_auto_off_seconds
        if auto_off_seconds != self._octo_light_auto_off_seconds:
            self._cancel_auto_off_timer()
            self._octo_light_auto_off_seconds = auto_off_seconds
        if auto_off_seconds is None or not self._attr_is_on:
            self._cancel_auto_off_timer()
            return
        if self._auto_off_timer is not None and not reset_deadline:
            return
        if reset_deadline:
            self._cancel_auto_off_timer()

        generation = self._octo_light_auto_off_generation

        def auto_off_callback() -> None:
            """Publish the expected expiry through the current controller."""
            if generation != self._octo_light_auto_off_generation:
                return
            current = self._current_octo_timer_controller()
            if (
                current is None
                or current.light_auto_off_seconds != auto_off_seconds
                or not self._attr_is_on
            ):
                return
            self._auto_off_timer = None
            self._octo_light_auto_off_generation += 1
            self._attr_is_on = False
            current.on_light_auto_off()
            self.async_write_ha_state()

        self._auto_off_timer = self.hass.loop.call_later(auto_off_seconds, auto_off_callback)

    def _schedule_auto_off_timer(self, *, reset_octo_deadline: bool = False) -> None:
        """Schedule auto-off timer if controller reports a light auto-off timeout.

        Some beds (e.g., Octo) have hardware-enforced light timeouts where the
        lights automatically turn off after a fixed duration. This method
        schedules a timer to update the HA state to reflect the hardware behavior.
        """
        if self.entity_description.key != "under_bed_lights":
            return

        octo = self._current_octo_timer_controller()
        if octo is not None:
            self._schedule_octo_auto_off_timer(octo, reset_deadline=reset_octo_deadline)
            return

        controller = self._coordinator.controller
        if controller is None:
            return

        auto_off_seconds = controller.light_auto_off_seconds
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
            controller.on_light_auto_off()
            self._attr_is_on = False
            self.async_write_ha_state()

        # Schedule the timer using the event loop
        self._auto_off_timer = self.hass.loop.call_later(auto_off_seconds, auto_off_callback)
        _LOGGER.debug(
            "Scheduled auto-off timer for %s in %d seconds",
            self.entity_description.key,
            auto_off_seconds,
        )

    async def async_will_remove_from_hass(self) -> None:
        """Clean up when entity is removed."""
        if self._state_unregister_callback:
            self._state_unregister_callback()
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
                self._schedule_auto_off_timer(reset_octo_deadline=True)
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

        try:
            _LOGGER.debug("Sending turn off command for %s", self.entity_description.key)
            await self._coordinator.async_execute_controller_command(
                self.entity_description.turn_off_fn,
                cancel_running=False,
            )
            # Only update assumed state if controller supports discrete on/off
            # Toggle-only controllers can't reliably track state
            if self._supports_discrete_control():
                # Cancel any pending auto-off timer only after the command succeeds.
                # If transport fails, keep the timer so HA can still reflect the
                # hardware-enforced auto-off when it happens.
                self._cancel_auto_off_timer()
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
