"""Binary sensor entities for Adjustable Bed integration."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from bleak.exc import BleakError
from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import AdjustableBedCoordinator
from .entity import AdjustableBedEntity

if TYPE_CHECKING:
    from .beds.base import BedController

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class AdjustableBedBinarySensorEntityDescription(BinarySensorEntityDescription):
    """Describes an Adjustable Bed binary sensor entity."""

    state_key: str | None = None
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
        state_key="bed_presence",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Adjustable Bed binary sensor entities."""
    coordinator: AdjustableBedCoordinator = hass.data[DOMAIN][entry.entry_id]
    controller = coordinator.controller
    entities: list[BinarySensorEntity] = []
    for description in BINARY_SENSOR_DESCRIPTIONS:
        if description.key == "bed_presence":
            if controller is None or not getattr(controller, "supports_bed_presence", False):
                continue

            bed_presence_sides = tuple(getattr(controller, "bed_presence_sides", ()))
            if bed_presence_sides:
                _async_remove_stale_presence_entity(hass, coordinator)
            else:
                entities.append(AdjustableBedPresenceSensor(coordinator, description))
            for side in bed_presence_sides:
                entities.append(
                    AdjustableBedPresenceSensor(
                        coordinator,
                        AdjustableBedBinarySensorEntityDescription(
                            key=f"bed_presence_{side}",
                            translation_key=f"bed_presence_{side}",
                            device_class=BinarySensorDeviceClass.OCCUPANCY,
                            entity_registry_enabled_default=False,
                            state_key=f"bed_presence_{side}",
                            side=side,
                        ),
                    )
                )
            continue
        entities.append(AdjustableBedConnectionSensor(coordinator, description))

    async_add_entities(entities)


def _async_remove_stale_presence_entity(
    hass: HomeAssistant,
    coordinator: AdjustableBedCoordinator,
) -> None:
    """Remove the legacy single-side presence entity when split sensors exist."""
    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id(
        "binary_sensor",
        DOMAIN,
        f"{coordinator.address}_bed_presence",
    )
    if entity_id is not None:
        registry.async_remove(entity_id)


class AdjustableBedConnectionSensor(AdjustableBedEntity, BinarySensorEntity):
    """Binary sensor entity for Adjustable Bed BLE connection state."""

    entity_description: AdjustableBedBinarySensorEntityDescription

    def __init__(
        self,
        coordinator: AdjustableBedCoordinator,
        description: AdjustableBedBinarySensorEntityDescription,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.address}_{description.key}"
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

        # State detail for more granular status
        if self._coordinator.is_connecting:
            attrs["state_detail"] = "connecting"
        elif self._coordinator.is_connected:
            attrs["state_detail"] = "connected"
        else:
            attrs["state_detail"] = "disconnected"

        return attrs


class AdjustableBedPresenceSensor(AdjustableBedEntity, BinarySensorEntity):
    """Binary sensor entity for adjustable bed occupancy state."""

    entity_description: AdjustableBedBinarySensorEntityDescription

    _attr_should_poll = True

    def __init__(
        self,
        coordinator: AdjustableBedCoordinator,
        description: AdjustableBedBinarySensorEntityDescription,
    ) -> None:
        """Initialize the presence sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.address}_{description.key}"
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
    def _handle_controller_state_change(self, state: dict[str, Any]) -> None:
        """Write state when the controller publishes a presence update."""
        state_key = self.entity_description.state_key or self.entity_description.key
        if state_key in state:
            self.async_write_ha_state()

    @property
    def is_on(self) -> bool | None:
        """Return True when the configured side is occupied."""
        state_key = self.entity_description.state_key or self.entity_description.key
        presence = self._coordinator.controller_state.get(state_key)
        if presence == "in":
            return True
        if presence == "out":
            return False
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional presence metadata."""
        attrs: dict[str, Any] = {}
        side = self.entity_description.side or self._coordinator.controller_state.get("bed_presence_side")
        if side is not None:
            attrs["side"] = side
        state_key = self.entity_description.state_key or self.entity_description.key
        presence = self._coordinator.controller_state.get(state_key)
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
