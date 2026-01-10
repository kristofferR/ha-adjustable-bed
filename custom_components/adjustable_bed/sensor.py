"""Sensor entities for Adjustable Bed integration."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_MOTOR_COUNT, DEFAULT_MOTOR_COUNT, DOMAIN
from .coordinator import AdjustableBedCoordinator
from .entity import AdjustableBedEntity

_LOGGER = logging.getLogger(__name__)

# Unit constant for angle measurements
UNIT_DEGREES = "°"


@dataclass(frozen=True, kw_only=True)
class AdjustableBedSensorEntityDescription(SensorEntityDescription):
    """Describes a Adjustable Bed sensor entity."""

    position_key: str
    min_motors: int = 2


SENSOR_DESCRIPTIONS: tuple[AdjustableBedSensorEntityDescription, ...] = (
    AdjustableBedSensorEntityDescription(
        key="back_angle",
        translation_key="back_angle",
        icon="mdi:angle-acute",
        native_unit_of_measurement=UNIT_DEGREES,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        position_key="back",
        min_motors=2,
    ),
    AdjustableBedSensorEntityDescription(
        key="legs_angle",
        translation_key="legs_angle",
        icon="mdi:angle-acute",
        native_unit_of_measurement=UNIT_DEGREES,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        position_key="legs",
        min_motors=2,
    ),
    AdjustableBedSensorEntityDescription(
        key="head_angle",
        translation_key="head_angle",
        icon="mdi:angle-acute",
        native_unit_of_measurement=UNIT_DEGREES,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        position_key="head",
        min_motors=3,
    ),
    AdjustableBedSensorEntityDescription(
        key="feet_angle",
        translation_key="feet_angle",
        icon="mdi:angle-acute",
        native_unit_of_measurement=UNIT_DEGREES,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        position_key="feet",
        min_motors=4,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Adjustable Bed sensor entities."""
    coordinator: AdjustableBedCoordinator = hass.data[DOMAIN][entry.entry_id]
    motor_count = entry.data.get(CONF_MOTOR_COUNT, DEFAULT_MOTOR_COUNT)

    # Skip angle sensors if angle sensing is disabled
    if coordinator.disable_angle_sensing:
        _LOGGER.debug("Angle sensing disabled, skipping angle sensor creation")
        return

    entities = []
    for description in SENSOR_DESCRIPTIONS:
        if motor_count >= description.min_motors:
            entities.append(AdjustableBedAngleSensor(coordinator, description))

    async_add_entities(entities)


class AdjustableBedAngleSensor(AdjustableBedEntity, SensorEntity):
    """Sensor entity for Adjustable Bed angle measurements."""

    entity_description: AdjustableBedSensorEntityDescription

    def __init__(
        self,
        coordinator: AdjustableBedCoordinator,
        description: AdjustableBedSensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.address}_{description.key}"
        self._unregister_callback: Callable[[], None] | None = None

    async def async_added_to_hass(self) -> None:
        """Run when entity is added to hass."""
        await super().async_added_to_hass()
        self._unregister_callback = self._coordinator.register_position_callback(
            self._handle_position_update
        )

    async def async_will_remove_from_hass(self) -> None:
        """Run when entity is removed from hass."""
        if self._unregister_callback:
            self._unregister_callback()
        await super().async_will_remove_from_hass()

    @callback
    def _handle_position_update(self, position_data: dict[str, float]) -> None:
        """Handle position data update."""
        self.async_write_ha_state()

    @property
    def native_value(self) -> float | None:
        """Return the sensor value."""
        return self._coordinator.position_data.get(
            self.entity_description.position_key
        )

