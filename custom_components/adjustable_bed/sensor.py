"""Sensor entities for Adjustable Bed integration."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from functools import partial
from typing import TYPE_CHECKING, Any

from homeassistant.components.sensor import (
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory, Platform
from homeassistant.core import HomeAssistant, callback

from .bed_traits import bed_traits
from .card import CARD_HIDDEN, motor_card
from .const import (
    BED_TYPE_LINAK,
    CONF_BED_TYPE,
    CONF_HAS_MASSAGE,
    CONF_MOTOR_COUNT,
    CONF_PROTOCOL_VARIANT,
    DEFAULT_MOTOR_COUNT,
    DOMAIN,
)
from .controller_state import ControllerState, StateKey
from .entity import AdjustableBedEntity
from .entity_discovery import async_setup_dynamic_entities
from .entity_runtime import EntityRuntime
from .entity_sweep import PlatformEntities, records_entities
from .paired_coordinator import entity_runtimes
from .position_estimate_entities import async_setup_estimate_sensors
from .state_keys import MASSAGE_TIMER_MINUTES, massage_intensity

if TYPE_CHECKING:
    from .beds.entity_specs import ControllerStateSensorSpec

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

    state_key: StateKey[int | None]


MASSAGE_SENSOR_DESCRIPTIONS: tuple[AdjustableBedMassageSensorEntityDescription, ...] = (
    AdjustableBedMassageSensorEntityDescription(
        key="massage_head_level",
        translation_key="massage_head_level",
        icon="mdi:vibrate",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        state_key=massage_intensity("head"),
    ),
    AdjustableBedMassageSensorEntityDescription(
        key="massage_foot_level",
        translation_key="massage_foot_level",
        icon="mdi:vibrate",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        state_key=massage_intensity("foot"),
    ),
    AdjustableBedMassageSensorEntityDescription(
        key="massage_timer_mode",
        translation_key="massage_timer_mode",
        icon="mdi:timer",
        entity_category=EntityCategory.DIAGNOSTIC,
        state_key=MASSAGE_TIMER_MINUTES,
    ),
)


@records_entities(Platform.SENSOR)
async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: PlatformEntities,
) -> None:
    """Set up Adjustable Bed sensor entities."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    # Opt-in travel-time estimates and saved positions (#601).
    async_setup_estimate_sensors(hass, entry, async_add_entities)
    for runtime in entity_runtimes(coordinator):
        async_setup_dynamic_entities(
            entry, runtime, async_add_entities, partial(_sensor_entities_for, hass, runtime)
        )


def _sensor_entities_for(
    hass: HomeAssistant, coordinator: EntityRuntime
) -> list[SensorEntity]:
    """Build sensor entities for a single (child or standalone) coordinator."""
    entry = coordinator.entry  # ChildEntryView for a paired child; real entry otherwise
    motor_count = entry.data.get(CONF_MOTOR_COUNT, DEFAULT_MOTOR_COUNT)
    bed_type = entry.data.get(CONF_BED_TYPE)
    protocol_variant = entry.data.get(CONF_PROTOCOL_VARIANT)
    has_massage = entry.data.get(CONF_HAS_MASSAGE, False)
    has_angle_feedback = bed_traits(bed_type, protocol_variant).angle_sensors
    # capability_controller: an offline paired side still gets its sensors built
    # from a client-free controller minted from config (see coordinator).
    controller = coordinator.capability_controller
    if controller is not None and controller.auto_enable_massage:
        has_massage = True
    position_number_keys = (
        {spec.position_key for spec in controller.position_number_specs}
        if controller is not None
        else set()
    )

    entities: list[SensorEntity] = []

    # Set up angle sensors only when both the protocol and configuration support it.
    if not coordinator.disable_angle_sensing:
        if bed_type == BED_TYPE_LINAK:
            _LOGGER.debug("Skipping duplicate Linak angle sensors")
        elif not has_angle_feedback:
            _LOGGER.debug("Skipping angle sensors for %s - no angle feedback", bed_type)
        else:
            for description in SENSOR_DESCRIPTIONS:
                if description.position_key in position_number_keys:
                    continue
                if motor_count >= description.min_motors:
                    entities.append(AdjustableBedAngleSensor(coordinator, description))
    else:
        _LOGGER.debug("Angle sensing disabled, skipping angle sensor creation")

    # Set up massage state sensors (only for beds with massage and state feedback)
    # Keeson/Ergomotion beds have state feedback via BLE notifications
    if has_massage and controller is not None:
        if controller.reports_massage_state:
            _LOGGER.debug(
                "Setting up massage state sensors for %s (variant: %s)",
                coordinator.name,
                protocol_variant,
            )
            for massage_desc in MASSAGE_SENSOR_DESCRIPTIONS:
                entities.append(AdjustableBedMassageSensor(coordinator, massage_desc))

    if controller is not None:
        specs = controller.controller_state_sensor_specs
        entities.extend(
            AdjustableBedControllerStateSensor(coordinator, spec) for spec in specs
        )

    return entities


class AdjustableBedAngleSensor(AdjustableBedEntity, SensorEntity):
    """Sensor entity for Adjustable Bed angle measurements."""

    entity_description: AdjustableBedSensorEntityDescription

    def __init__(
        self,
        coordinator: EntityRuntime,
        description: AdjustableBedSensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, motor_card(description.position_key))
        self.entity_description = description
        self._attr_translation_key = description.translation_key or description.key
        self._attr_unique_id = coordinator.entity_unique_id(description.key)
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
        coordinator: EntityRuntime,
        description: AdjustableBedMassageSensorEntityDescription,
    ) -> None:
        """Initialize the massage sensor."""
        super().__init__(coordinator, CARD_HIDDEN)
        self.entity_description = description
        self._attr_translation_key = description.translation_key or description.key
        self._attr_unique_id = coordinator.entity_unique_id(description.key)
        self._unregister_callback: Callable[[], None] | None = None

    async def async_added_to_hass(self) -> None:
        """Run when entity is added to hass."""
        await super().async_added_to_hass()
        self._unregister_callback = self._coordinator.register_controller_state_callback(
            self._handle_state_update
        )

    async def async_will_remove_from_hass(self) -> None:
        """Run when entity is removed from hass."""
        if self._unregister_callback:
            self._unregister_callback()
        await super().async_will_remove_from_hass()

    @callback
    def _handle_state_update(self, _state: ControllerState) -> None:
        self.async_write_ha_state()

    @property
    def native_value(self) -> str | int | None:
        """Return the value the controller last published."""
        key = self.entity_description.state_key
        state = self._coordinator.controller_state
        if key != MASSAGE_TIMER_MINUTES:
            # Like the massage number, a connected bed with no report yet shows zero.
            if key not in state:
                return None if self._coordinator.controller is None else 0
            return state[key]
        value = state.get(key)
        return None if value is None else str(value) if value else "Off"


class AdjustableBedControllerStateSensor(AdjustableBedEntity, SensorEntity):
    """Diagnostic sensor backed by typed controller-published state."""

    def __init__(
        self,
        coordinator: EntityRuntime,
        spec: ControllerStateSensorSpec,
    ) -> None:
        """Initialize a controller-state sensor."""
        super().__init__(coordinator, spec.card)
        self._spec = spec
        self._attr_unique_id = coordinator.entity_unique_id(spec.key)
        self._attr_translation_key = spec.translation_key
        self._attr_icon = spec.icon
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_entity_registry_enabled_default = spec.entity_registry_enabled_default
        self._attr_native_unit_of_measurement = spec.native_unit_of_measurement
        self._attr_suggested_display_precision = spec.suggested_display_precision
        if spec.native_unit_of_measurement is not None:
            self._attr_state_class = SensorStateClass.MEASUREMENT
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
    def native_value(self) -> str | int | float | None:
        """Return the latest controller-published value."""
        value = self._coordinator.controller_state.get(self._spec.state_key)
        return value if isinstance(value, (str, int, float)) else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the parser metadata selected by the controller spec."""
        state = self._coordinator.controller_state
        return {key: state[key] for key in self._spec.attribute_keys if key in state}
