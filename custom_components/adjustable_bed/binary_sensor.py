"""Binary sensor entities for Adjustable Bed integration."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass
from functools import partial
from typing import TYPE_CHECKING, Any

from bleak.exc import BleakError
from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory, Platform
from homeassistant.core import HomeAssistant, callback

from .const import DOMAIN
from .controller_state import ControllerState, StateKey, sided
from .entity import AdjustableBedEntity
from .entity_discovery import async_setup_dynamic_entities
from .entity_runtime import EntityRuntime, named_for_side, own_sides
from .entity_sweep import PlatformEntities, records_entities
from .paired_coordinator import entity_runtimes
from .state_keys import BED_PRESENCE, BED_PRESENCE_SIDE

if TYPE_CHECKING:
    from .beds.base import BedController, ControllerStateBinarySensorSpec

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class AdjustableBedBinarySensorEntityDescription(BinarySensorEntityDescription):
    """Describes an Adjustable Bed binary sensor entity."""

    state_key: StateKey[str] | None = None
    side: str | None = None


BINARY_SENSOR_DESCRIPTIONS: tuple[AdjustableBedBinarySensorEntityDescription, ...] = (
    AdjustableBedBinarySensorEntityDescription(
        key="ble_connection",
        translation_key="ble_connection",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    AdjustableBedBinarySensorEntityDescription(
        key="bed_presence",
        translation_key="bed_presence",
        device_class=BinarySensorDeviceClass.OCCUPANCY,
        entity_registry_enabled_default=False,
        state_key=BED_PRESENCE,
    ),
)


def _build_side_presence_description(side: str) -> AdjustableBedBinarySensorEntityDescription:
    """Build one natively sided bed presence description."""
    return AdjustableBedBinarySensorEntityDescription(
        key=f"bed_presence_{side}",
        translation_key=f"bed_presence_{side}",
        device_class=BinarySensorDeviceClass.OCCUPANCY,
        entity_registry_enabled_default=False,
        state_key=sided(BED_PRESENCE, side),
        side=side,
    )


@records_entities(Platform.BINARY_SENSOR)
async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: PlatformEntities,
) -> None:
    """Set up Adjustable Bed binary sensor entities."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    for runtime in entity_runtimes(coordinator):
        async_setup_dynamic_entities(
            entry, runtime, async_add_entities, partial(_binary_sensor_entities_for, hass, runtime)
        )


def _binary_sensor_entities_for(
    hass: HomeAssistant, coordinator: EntityRuntime
) -> list[BinarySensorEntity]:
    """Build binary-sensor entities for a single (child or standalone) coordinator."""
    # capability_controller so an offline paired side still exposes bed_presence
    # (the unconditional ble_connection sensor below is unaffected).
    controller = coordinator.capability_controller
    entities: list[BinarySensorEntity] = []
    for description in BINARY_SENSOR_DESCRIPTIONS:
        if description.key == "bed_presence":
            if controller is None or not controller.supports_bed_presence:
                continue

            bed_presence_sides = own_sides(coordinator, controller.bed_presence_sides)
            if not bed_presence_sides:
                entities.append(AdjustableBedPresenceSensor(coordinator, description))
            entities.extend(
                AdjustableBedPresenceSensor(
                    coordinator,
                    named_for_side(coordinator, _build_side_presence_description(side), side),
                )
                for side in bed_presence_sides
            )
            continue
        entities.append(AdjustableBedConnectionSensor(coordinator, description))

    if controller is not None:
        entities.extend(
            AdjustableBedControllerStateBinarySensor(coordinator, spec)
            for spec in controller.controller_state_binary_sensor_specs
        )

    return entities


class AdjustableBedConnectionSensor(AdjustableBedEntity, BinarySensorEntity):
    """Binary sensor entity for Adjustable Bed BLE connection state."""

    entity_description: AdjustableBedBinarySensorEntityDescription

    def __init__(
        self,
        coordinator: EntityRuntime,
        description: AdjustableBedBinarySensorEntityDescription,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_translation_key = description.translation_key or description.key
        self._attr_unique_id = coordinator.entity_unique_id(description.key)
        self._unregister_callback: Callable[[], None] | None = None

    async def async_added_to_hass(self) -> None:
        """Run when entity is added to hass."""
        await super().async_added_to_hass()
        self._unregister_callback = self._coordinator.register_connection_state_callback(
            self._handle_connection_state_change
        )

    async def async_will_remove_from_hass(self) -> None:
        """Run when entity is removed from hass."""
        if self._unregister_callback:
            self._unregister_callback()
        await super().async_will_remove_from_hass()

    @callback
    def _handle_connection_state_change(self, _connected: bool) -> None:
        """Handle connection state change."""
        self.async_write_ha_state()

    @property
    def is_on(self) -> bool:
        """Return True if the bed is connected."""
        return self._coordinator.is_connected

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes."""
        attrs: dict[str, Any] = {}

        # Last connected timestamp
        if self._coordinator.last_connected:
            attrs["last_connected"] = self._coordinator.last_connected.isoformat()

        # Last disconnected timestamp
        if self._coordinator.last_disconnected:
            attrs["last_disconnected"] = self._coordinator.last_disconnected.isoformat()

        # Connection source (adapter name)
        if self._coordinator.connection_source:
            attrs["connection_source"] = self._coordinator.connection_source

        # RSSI at connection time
        if self._coordinator.connection_rssi is not None:
            attrs["rssi"] = self._coordinator.connection_rssi

        # Why the bed last disconnected, so an expected idle disconnect doesn't
        # read as a fault (issue #385). Intentional/idle reasons mean the bed is
        # fine and reconnects on demand on the next command.
        reason = self._coordinator.last_disconnect_reason
        if reason:
            attrs["disconnect_reason"] = reason

        # State detail for more granular status
        if self._coordinator.is_connecting:
            attrs["state_detail"] = "connecting"
        elif self._coordinator.is_connected:
            attrs["state_detail"] = "connected"
        elif reason in ("idle_timeout", "intentional"):
            # Disconnected on purpose (idle timeout or manual) — surface as "idle"
            # rather than a bare "disconnected" that looks like a fault.
            attrs["state_detail"] = "idle"
        else:
            attrs["state_detail"] = "disconnected"

        side = self._coordinator.entity_side
        if side is not None:
            attrs["bed_side"] = side

        return attrs


class AdjustableBedControllerStateBinarySensor(AdjustableBedEntity, BinarySensorEntity):
    """Binary diagnostic backed by typed controller-published state."""

    def __init__(
        self,
        coordinator: EntityRuntime,
        spec: ControllerStateBinarySensorSpec,
    ) -> None:
        """Initialize a controller-state binary sensor."""
        super().__init__(coordinator)
        self._spec = spec
        self._attr_unique_id = coordinator.entity_unique_id(spec.key)
        self._attr_translation_key = spec.translation_key
        self._attr_icon = spec.icon
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_entity_registry_enabled_default = spec.entity_registry_enabled_default
        self._unregister_callback: Callable[[], None] | None = None

    async def async_added_to_hass(self) -> None:
        """Subscribe to controller-state changes."""
        await super().async_added_to_hass()
        self._unregister_callback = self._coordinator.register_controller_state_callback(
            self._handle_controller_state_update
        )

    async def async_will_remove_from_hass(self) -> None:
        """Unsubscribe from controller-state changes."""
        if self._unregister_callback is not None:
            self._unregister_callback()
        await super().async_will_remove_from_hass()

    @callback
    def _handle_controller_state_update(self, state: ControllerState) -> None:
        """Refresh when this sensor or one of its attributes changed."""
        watched = {self._spec.state_key, *self._spec.attribute_keys}
        if watched.intersection(state):
            self.async_write_ha_state()

    @property
    def is_on(self) -> bool | None:
        """Return the latest controller-published boolean state."""
        value = self._coordinator.controller_state.get(self._spec.state_key)
        return value if isinstance(value, bool) else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return parser metadata selected by the controller spec."""
        state = self._coordinator.controller_state
        return {key: state[key] for key in self._spec.attribute_keys if key in state}


class AdjustableBedPresenceSensor(AdjustableBedEntity, BinarySensorEntity):
    """Binary sensor entity for adjustable bed occupancy state."""

    entity_description: AdjustableBedBinarySensorEntityDescription

    _attr_should_poll = True

    def __init__(
        self,
        coordinator: EntityRuntime,
        description: AdjustableBedBinarySensorEntityDescription,
    ) -> None:
        """Initialize the presence sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_translation_key = description.translation_key or description.key
        self._attr_unique_id = coordinator.entity_unique_id(description.key)
        self._presence_key = description.state_key or BED_PRESENCE
        self._unregister_callback: Callable[[], None] | None = None

    async def async_added_to_hass(self) -> None:
        """Run when entity is added to hass."""
        await super().async_added_to_hass()
        self._unregister_callback = self._coordinator.register_controller_state_callback(
            self._handle_controller_state_change
        )

    async def async_will_remove_from_hass(self) -> None:
        """Run when entity is removed from hass."""
        if self._unregister_callback:
            self._unregister_callback()
        await super().async_will_remove_from_hass()

    @callback
    def _handle_controller_state_change(self, state: ControllerState) -> None:
        """Write state when the controller publishes a presence update."""
        if self._presence_key in state:
            self.async_write_ha_state()

    @property
    def is_on(self) -> bool | None:
        """Return True when the configured side is occupied."""
        presence = self._coordinator.controller_state.get(self._presence_key)
        if presence == "in":
            return True
        if presence == "out":
            return False
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional presence metadata."""
        attrs: dict[str, Any] = {}
        side = self.entity_description.side or self._coordinator.controller_state.get(
            BED_PRESENCE_SIDE
        )
        if side is not None:
            attrs["side"] = side
        presence = self._coordinator.controller_state.get(self._presence_key)
        if presence is not None:
            attrs["presence_state"] = presence
        return attrs

    async def async_update(self) -> None:
        """Query the latest bed presence from the controller.

        Home Assistant calls ``async_update`` independently on every enabled
        poll-driven entity. For beds where a single BLE query refreshes
        occupancy for *both* sides at once (e.g. Sleep Number's grouped
        BAMG read), the controller's ``read_bed_presence_cached`` coalesces
        follow-up polls with a short TTL so we never run the same BLE
        query more than once per cycle.
        """

        async def _read_presence(ctrl: BedController) -> bool | None:
            return await ctrl.read_bed_presence_cached()

        try:
            await self._coordinator.async_execute_controller_query(
                _read_presence,
                cancel_running=False,
            )
        except asyncio.CancelledError:
            return
        except (BleakError, ConnectionError, RuntimeError, TimeoutError, ValueError) as err:
            _LOGGER.debug("Bed presence poll failed for %s: %s", self._coordinator.address, err)
