"""Sensor entities for Adjustable Bed integration."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    BEDS_WITH_PERCENTAGE_POSITIONS,
    CONF_BED_TYPE,
    CONF_HAS_MASSAGE,
    CONF_MOTOR_COUNT,
    DEFAULT_MOTOR_COUNT,
    DOMAIN,
    KEESON_VARIANT_ERGOMOTION,
    CONF_PROTOCOL_VARIANT,
    BED_TYPE_KEESON,
)
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


@dataclass(frozen=True, kw_only=True)
class AdjustableBedMassageSensorEntityDescription(SensorEntityDescription):
    """Describes a massage state sensor entity."""

    state_key: str  # Key in get_massage_state() dict


MASSAGE_SENSOR_DESCRIPTIONS: tuple[AdjustableBedMassageSensorEntityDescription, ...] = (
    AdjustableBedMassageSensorEntityDescription(
        key="massage_head_level",
        translation_key="massage_head_level",
        icon="mdi:vibrate",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        state_key="head_intensity",
    ),
    AdjustableBedMassageSensorEntityDescription(
        key="massage_foot_level",
        translation_key="massage_foot_level",
        icon="mdi:vibrate",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        state_key="foot_intensity",
    ),
    AdjustableBedMassageSensorEntityDescription(
        key="massage_timer_mode",
        translation_key="massage_timer_mode",
        icon="mdi:timer",
        entity_category=EntityCategory.DIAGNOSTIC,
        state_key="timer_mode",
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
    bed_type = entry.data.get(CONF_BED_TYPE)
    has_massage = entry.data.get(CONF_HAS_MASSAGE, False)
    controller = coordinator.controller

    entities: list[SensorEntity] = []

    # Set up angle sensors (only for non-percentage beds with angle sensing enabled)
    if not coordinator.disable_angle_sensing:
        # Skip angle sensors for beds that report percentage instead of angles
        # (Keeson/Ergomotion/Serta report 0-100% position, not degrees)
        if bed_type not in BEDS_WITH_PERCENTAGE_POSITIONS:
            for description in SENSOR_DESCRIPTIONS:
                if motor_count >= description.min_motors:
                    entities.append(AdjustableBedAngleSensor(coordinator, description))
        else:
            _LOGGER.debug("Skipping angle sensors for %s - reports percentage, not angle", bed_type)
    else:
        _LOGGER.debug("Angle sensing disabled, skipping angle sensor creation")

    # Set up massage state sensors (only for beds with massage and state feedback)
    # Only Keeson/Ergomotion beds have state feedback via BLE notifications
    if has_massage and controller is not None:
        protocol_variant = entry.data.get(CONF_PROTOCOL_VARIANT)
        has_massage_feedback = (
            bed_type == BED_TYPE_KEESON and protocol_variant == KEESON_VARIANT_ERGOMOTION
        )

        if has_massage_feedback:
            _LOGGER.debug(
                "Setting up massage state sensors for %s (variant: %s)",
                coordinator.name,
                protocol_variant,
            )
            for description in MASSAGE_SENSOR_DESCRIPTIONS:
                entities.append(AdjustableBedMassageSensor(coordinator, description))

    if entities:
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
        """Handle position data update.

        The position_data parameter is provided by the callback interface but not
        used here since we read from the coordinator's position_data in native_value.
        """
        # position_data is intentionally unused - we read from coordinator in native_value
        del position_data  # Mark as intentionally unused
        self.async_write_ha_state()

    @property
    def native_value(self) -> float | None:
        """Return the sensor value."""
        return self._coordinator.position_data.get(self.entity_description.position_key)


class AdjustableBedMassageSensor(AdjustableBedEntity, SensorEntity):
    """Sensor entity for Adjustable Bed massage state feedback."""

    entity_description: AdjustableBedMassageSensorEntityDescription

    def __init__(
        self,
        coordinator: AdjustableBedCoordinator,
        description: AdjustableBedMassageSensorEntityDescription,
    ) -> None:
        """Initialize the massage sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.address}_{description.key}"
        self._unregister_callback: Callable[[], None] | None = None

    async def async_added_to_hass(self) -> None:
        """Run when entity is added to hass."""
        await super().async_added_to_hass()
        # Register for position callbacks because the BLE position notifications
        # (parsed by _parse_position_message in Keeson/Ergomotion controllers) also
        # contain massage state data. When the controller receives a notification,
        # it parses both position and massage state, then triggers all registered
        # position callbacks. Our _handle_state_update receives these updates and
        # refreshes the entity state, which reads massage data via get_massage_state().
        self._unregister_callback = self._coordinator.register_position_callback(
            self._handle_state_update
        )

    async def async_will_remove_from_hass(self) -> None:
        """Run when entity is removed from hass."""
        if self._unregister_callback:
            self._unregister_callback()
        await super().async_will_remove_from_hass()

    @callback
    def _handle_state_update(self, _position_data: dict[str, float]) -> None:
        """Handle state update from BLE notifications."""
        self.async_write_ha_state()

    @property
    def native_value(self) -> str | int | None:
        """Return the massage state value from controller."""
        controller = self._coordinator.controller
        if controller is None:
            return None

        state = controller.get_massage_state()
        value = state.get(self.entity_description.state_key)

        # Return appropriate type based on state key
        if value is None:
            return None

        # Timer mode is a string, intensity is int
        if self.entity_description.state_key == "timer_mode":
            # Normalize: treat "0", 0, or empty string as "Off"
            str_value = str(value)
            if str_value == "" or str_value == "0":
                return "Off"
            return str_value
        return int(value)
