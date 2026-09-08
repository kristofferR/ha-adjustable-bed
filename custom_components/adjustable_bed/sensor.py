"""Sensor entities for Adjustable Bed integration."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from homeassistant.components.sensor import (
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    BED_TYPE_ERGOMOTION,
    BED_TYPE_KEESON,
    BED_TYPE_LINAK,
    BEDS_WITH_ANGLE_SENSING,
    CONF_BED_TYPE,
    CONF_HAS_MASSAGE,
    CONF_MOTOR_COUNT,
    CONF_PROTOCOL_VARIANT,
    DEFAULT_MOTOR_COUNT,
    DOMAIN,
    KEESON_VARIANT_ERGOMOTION,
)
from .coordinator import AdjustableBedCoordinator
from .entity import AdjustableBedEntity
from .paired_coordinator import PairedBedCoordinator

if TYPE_CHECKING:
    from .beds.base import ControllerStateSensorSpec

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
    coordinator = hass.data[DOMAIN][entry.entry_id]
    if isinstance(coordinator, PairedBedCoordinator):
        paired_entities: list[SensorEntity] = []
        for child in coordinator.children.values():
            paired_entities.extend(_sensor_entities_for(hass, child))
        if paired_entities:
            async_add_entities(paired_entities)
        return
    async_add_entities(_sensor_entities_for(hass, coordinator))


def _sensor_entities_for(
    hass: HomeAssistant, coordinator: AdjustableBedCoordinator
) -> list[SensorEntity]:
    """Build sensor entities for a single (child or standalone) coordinator."""
    entry = coordinator.entry  # ChildEntryView for a paired child; real entry otherwise
    motor_count = entry.data.get(CONF_MOTOR_COUNT, DEFAULT_MOTOR_COUNT)
    bed_type = entry.data.get(CONF_BED_TYPE)
    has_massage = entry.data.get(CONF_HAS_MASSAGE, False)
    # capability_controller: an offline paired side still gets its sensors built
    # from a client-free controller minted from config (see coordinator).
    controller = coordinator.capability_controller
    position_number_keys = (
        {spec.position_key for spec in controller.position_number_specs}
        if controller is not None
        else set()
    )

    entities: list[SensorEntity] = []

    # Only protocols in the explicit angle-sensing capability set may expose degree
    # sensors. Clean up entities created by older permissive logic so unsupported
    # beds cannot leave dead "unknown" angles in Home Assistant or the card.
    if bed_type == BED_TYPE_LINAK:
        # Linak position numbers already expose the app's exact reference values.
        # Remove every legacy angle entity, including axes omitted by a new mask.
        _async_remove_stale_angle_entities(hass, coordinator)
    elif bed_type not in BEDS_WITH_ANGLE_SENSING:
        _async_remove_stale_angle_entities(hass, coordinator)
    elif position_number_keys:
        # A position number already exposes the same live value while also
        # allowing a target to be set. Keep one entity per axis and remove the
        # duplicate read-only angle sensor left by earlier releases.
        _async_remove_stale_angle_entities(
            hass,
            coordinator,
            position_keys=position_number_keys,
        )

    if bed_type == BED_TYPE_LINAK:
        _async_remove_stale_sensor_entities(
            hass,
            coordinator,
            keys=("linak_model_variant",),
        )

    # Set up angle sensors only when both the protocol and configuration support it.
    if not coordinator.disable_angle_sensing:
        if bed_type == BED_TYPE_LINAK:
            _LOGGER.debug("Skipping duplicate Linak angle sensors")
        elif bed_type not in BEDS_WITH_ANGLE_SENSING:
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
        protocol_variant = entry.data.get(CONF_PROTOCOL_VARIANT)
        has_massage_feedback = bed_type == BED_TYPE_ERGOMOTION or (
            bed_type == BED_TYPE_KEESON and protocol_variant == KEESON_VARIANT_ERGOMOTION
        )

        if has_massage_feedback:
            _LOGGER.debug(
                "Setting up massage state sensors for %s (variant: %s)",
                coordinator.name,
                protocol_variant,
            )
            for massage_desc in MASSAGE_SENSOR_DESCRIPTIONS:
                entities.append(AdjustableBedMassageSensor(coordinator, massage_desc))

    if controller is not None:
        specs = controller.controller_state_sensor_specs
        active_keys = {spec.key for spec in specs}
        stale_keys = controller.stale_controller_state_sensor_entity_keys | (
            {"leggett_led_mask", "leggett_status", "logicdata_app_alarm", "logicdata_app_family_match"} - active_keys
        )
        _async_remove_stale_sensor_entities(
            hass,
            coordinator,
            keys=tuple(stale_keys),
        )
        entities.extend(
            AdjustableBedControllerStateSensor(coordinator, spec) for spec in specs
        )

    return entities


def _async_remove_stale_angle_entities(
    hass: HomeAssistant,
    coordinator: AdjustableBedCoordinator,
    *,
    position_keys: set[str] | None = None,
) -> None:
    """Remove stale angle entities for protocols without degree feedback."""
    registry = er.async_get(hass)
    for description in SENSOR_DESCRIPTIONS:
        if position_keys is not None and description.position_key not in position_keys:
            continue
        entity_id = registry.async_get_entity_id(
            "sensor", DOMAIN, coordinator.entity_unique_id(description.key)
        )
        if entity_id is not None:
            registry.async_remove(entity_id)


def _async_remove_stale_sensor_entities(
    hass: HomeAssistant,
    coordinator: AdjustableBedCoordinator,
    *,
    keys: tuple[str, ...],
) -> None:
    """Remove sensor entities retired in favor of device metadata."""
    registry = er.async_get(hass)
    for key in keys:
        entity_id = registry.async_get_entity_id(
            "sensor", DOMAIN, coordinator.entity_unique_id(key)
        )
        if entity_id is not None:
            registry.async_remove(entity_id)


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
        self._set_sided_translation_key(description.translation_key, description.key)
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
        coordinator: AdjustableBedCoordinator,
        description: AdjustableBedMassageSensorEntityDescription,
    ) -> None:
        """Initialize the massage sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._set_sided_translation_key(description.translation_key, description.key)
        self._attr_unique_id = coordinator.entity_unique_id(description.key)
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
        try:
            return int(value)
        except ValueError, TypeError:
            _LOGGER.debug("Non-numeric massage state value: %s", value)
            return None


class AdjustableBedControllerStateSensor(AdjustableBedEntity, SensorEntity):
    """Diagnostic sensor backed by typed controller-published state."""

    def __init__(
        self,
        coordinator: AdjustableBedCoordinator,
        spec: ControllerStateSensorSpec,
    ) -> None:
        """Initialize a controller-state sensor."""
        super().__init__(coordinator)
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
    def _handle_controller_state_update(self, state: dict[str, Any]) -> None:
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
