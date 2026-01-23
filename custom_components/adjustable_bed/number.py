"""Number entities for Adjustable Bed integration."""

from __future__ import annotations

import logging
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from homeassistant.components.number import (
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    BED_TYPE_ERGOMOTION,
    BED_TYPE_KEESON,
    BEDS_WITH_POSITION_FEEDBACK,
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

if TYPE_CHECKING:
    from .beds.base import BedController

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class AdjustableBedNumberEntityDescription(NumberEntityDescription):
    """Describes an Adjustable Bed number entity for position control."""

    position_key: str
    move_up_fn: Callable[[BedController], Coroutine[Any, Any, None]]
    move_down_fn: Callable[[BedController], Coroutine[Any, Any, None]]
    move_stop_fn: Callable[[BedController], Coroutine[Any, Any, None]]
    max_angle: float
    min_motors: int = 2


# Note: For most beds (Linak, Okimat, Reverie):
# - 2 motors: back and legs
# - 3 motors: back, legs, head
# - 4 motors: back, legs, head, feet
#
# For Keeson/Ergomotion:
# - The motors map to head/feet instead of back/legs
# - Position data comes as "back"/"legs" keys though
NUMBER_DESCRIPTIONS: tuple[AdjustableBedNumberEntityDescription, ...] = (
    AdjustableBedNumberEntityDescription(
        key="back_position",
        translation_key="back_position",
        icon="mdi:human-handsup",
        native_min_value=0,
        native_max_value=68,
        native_step=1,
        native_unit_of_measurement="°",
        mode=NumberMode.SLIDER,
        position_key="back",
        move_up_fn=lambda ctrl: ctrl.move_back_up(),
        move_down_fn=lambda ctrl: ctrl.move_back_down(),
        move_stop_fn=lambda ctrl: ctrl.move_back_stop(),
        max_angle=68.0,
        min_motors=2,
    ),
    AdjustableBedNumberEntityDescription(
        key="legs_position",
        translation_key="legs_position",
        icon="mdi:human-handsdown",
        native_min_value=0,
        native_max_value=45,
        native_step=1,
        native_unit_of_measurement="°",
        mode=NumberMode.SLIDER,
        position_key="legs",
        move_up_fn=lambda ctrl: ctrl.move_legs_up(),
        move_down_fn=lambda ctrl: ctrl.move_legs_down(),
        move_stop_fn=lambda ctrl: ctrl.move_legs_stop(),
        max_angle=45.0,
        min_motors=2,
    ),
    AdjustableBedNumberEntityDescription(
        key="head_position",
        translation_key="head_position",
        icon="mdi:head",
        native_min_value=0,
        native_max_value=68,
        native_step=1,
        native_unit_of_measurement="°",
        mode=NumberMode.SLIDER,
        position_key="head",
        move_up_fn=lambda ctrl: ctrl.move_head_up(),
        move_down_fn=lambda ctrl: ctrl.move_head_down(),
        move_stop_fn=lambda ctrl: ctrl.move_head_stop(),
        max_angle=68.0,
        min_motors=3,
    ),
    AdjustableBedNumberEntityDescription(
        key="feet_position",
        translation_key="feet_position",
        icon="mdi:foot-print",
        native_min_value=0,
        native_max_value=45,
        native_step=1,
        native_unit_of_measurement="°",
        mode=NumberMode.SLIDER,
        position_key="feet",
        move_up_fn=lambda ctrl: ctrl.move_feet_up(),
        move_down_fn=lambda ctrl: ctrl.move_feet_down(),
        move_stop_fn=lambda ctrl: ctrl.move_feet_stop(),
        max_angle=45.0,
        min_motors=4,
    ),
)


@dataclass(frozen=True, kw_only=True)
class AdjustableBedMassageNumberEntityDescription(NumberEntityDescription):
    """Describes an Adjustable Bed massage intensity number entity."""

    massage_zone: str  # "head", "foot", "wave"


MASSAGE_NUMBER_DESCRIPTIONS: tuple[AdjustableBedMassageNumberEntityDescription, ...] = (
    AdjustableBedMassageNumberEntityDescription(
        key="massage_head_intensity",
        translation_key="massage_head_intensity",
        icon="mdi:vibrate",
        native_min_value=0,
        native_max_value=10,
        native_step=1,
        mode=NumberMode.SLIDER,
        massage_zone="head",
    ),
    AdjustableBedMassageNumberEntityDescription(
        key="massage_foot_intensity",
        translation_key="massage_foot_intensity",
        icon="mdi:vibrate",
        native_min_value=0,
        native_max_value=10,
        native_step=1,
        mode=NumberMode.SLIDER,
        massage_zone="foot",
    ),
    AdjustableBedMassageNumberEntityDescription(
        key="massage_wave_intensity",
        translation_key="massage_wave_intensity",
        icon="mdi:vibrate",
        native_min_value=0,
        native_max_value=10,
        native_step=1,
        mode=NumberMode.SLIDER,
        massage_zone="wave",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Adjustable Bed number entities."""
    coordinator: AdjustableBedCoordinator = hass.data[DOMAIN][entry.entry_id]
    motor_count = entry.data.get(CONF_MOTOR_COUNT, DEFAULT_MOTOR_COUNT)
    bed_type = entry.data.get(CONF_BED_TYPE)
    has_massage = entry.data.get(CONF_HAS_MASSAGE, False)
    controller = coordinator.controller

    entities: list[NumberEntity] = []

    # Set up position number entities (only for beds with position feedback)
    if not coordinator.disable_angle_sensing:
        # Check if bed supports position feedback
        # Special case: BED_TYPE_KEESON only supports position feedback with ergomotion variant
        protocol_variant = entry.data.get(CONF_PROTOCOL_VARIANT)
        has_position_feedback = bed_type in BEDS_WITH_POSITION_FEEDBACK or (
            bed_type == BED_TYPE_KEESON and protocol_variant == KEESON_VARIANT_ERGOMOTION
        )

        if has_position_feedback:
            # Keeson and Ergomotion beds use different motor naming:
            # Head/Feet instead of Back/Legs, but position data still uses "back"/"legs" keys
            if bed_type in (BED_TYPE_KEESON, BED_TYPE_ERGOMOTION):
                _LOGGER.debug(
                    "Setting up Keeson/Ergomotion position numbers for %s (motor_count=%d)",
                    coordinator.name,
                    motor_count,
                )

                # Find the descriptions we need
                descriptions_by_key = {d.key: d for d in NUMBER_DESCRIPTIONS}

                # Create head position (maps to "back" position data)
                # Keeson/Ergomotion report percentage positions (0-100), not angles
                head_desc = descriptions_by_key["head_position"]
                keeson_head_desc = AdjustableBedNumberEntityDescription(
                    key=head_desc.key,
                    translation_key=head_desc.translation_key,
                    icon=head_desc.icon,
                    native_min_value=0,
                    native_max_value=100,
                    native_step=1,
                    native_unit_of_measurement="%",
                    mode=head_desc.mode,
                    position_key="back",  # Map to "back" in position_data
                    move_up_fn=head_desc.move_up_fn,
                    move_down_fn=head_desc.move_down_fn,
                    move_stop_fn=head_desc.move_stop_fn,
                    max_angle=100.0,  # Use 100 as max for percentage-based beds
                    min_motors=2,
                )
                entities.append(AdjustableBedPositionNumber(coordinator, keeson_head_desc))

                # Create feet position (maps to "legs" position data)
                # Keeson/Ergomotion report percentage positions (0-100), not angles
                feet_desc = descriptions_by_key["feet_position"]
                keeson_feet_desc = AdjustableBedNumberEntityDescription(
                    key=feet_desc.key,
                    translation_key=feet_desc.translation_key,
                    icon=feet_desc.icon,
                    native_min_value=0,
                    native_max_value=100,
                    native_step=1,
                    native_unit_of_measurement="%",
                    mode=feet_desc.mode,
                    position_key="legs",  # Map to "legs" in position_data
                    move_up_fn=feet_desc.move_up_fn,
                    move_down_fn=feet_desc.move_down_fn,
                    move_stop_fn=feet_desc.move_stop_fn,
                    max_angle=100.0,  # Use 100 as max for percentage-based beds
                    min_motors=2,
                )
                entities.append(AdjustableBedPositionNumber(coordinator, keeson_feet_desc))
            else:
                # Standard bed motor layout (Back/Legs/Head/Feet)
                for description in NUMBER_DESCRIPTIONS:
                    if motor_count >= description.min_motors:
                        entities.append(AdjustableBedPositionNumber(coordinator, description))
        else:
            _LOGGER.debug(
                "Bed type %s (variant=%s) does not support position feedback, skipping position number entities",
                bed_type,
                entry.data.get(CONF_PROTOCOL_VARIANT),
            )

    # Set up massage intensity number entities (only for beds with massage and direct intensity control)
    if has_massage and controller is not None:
        if getattr(controller, "supports_massage_intensity_control", False):
            supported_zones = getattr(controller, "massage_intensity_zones", [])
            max_intensity = getattr(controller, "massage_intensity_max", 10)
            _LOGGER.debug(
                "Setting up massage intensity numbers for %s (zones: %s, max: %d)",
                coordinator.name,
                supported_zones,
                max_intensity,
            )

            for description in MASSAGE_NUMBER_DESCRIPTIONS:
                if description.massage_zone in supported_zones:
                    # Create description with correct max value for this controller
                    adjusted_desc = AdjustableBedMassageNumberEntityDescription(
                        key=description.key,
                        translation_key=description.translation_key,
                        icon=description.icon,
                        native_min_value=0,
                        native_max_value=max_intensity,
                        native_step=1,
                        mode=description.mode,
                        massage_zone=description.massage_zone,
                    )
                    entities.append(AdjustableBedMassageNumber(coordinator, adjusted_desc))

    if entities:
        async_add_entities(entities)


class AdjustableBedPositionNumber(AdjustableBedEntity, NumberEntity):
    """Number entity for Adjustable Bed position control."""

    entity_description: AdjustableBedNumberEntityDescription

    def __init__(
        self,
        coordinator: AdjustableBedCoordinator,
        description: AdjustableBedNumberEntityDescription,
    ) -> None:
        """Initialize the number entity."""
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
    def _handle_position_update(self, _position_data: dict[str, float]) -> None:
        """Handle position data update."""
        self.async_write_ha_state()

    @property
    def native_value(self) -> float | None:
        """Return the current position (angle in degrees, or percentage for Keeson/Ergomotion)."""
        position = self._coordinator.position_data.get(self.entity_description.position_key)
        if position is None:
            return None

        # Return position clamped to valid range
        # For standard beds: angle (0 to max_angle degrees)
        # For Keeson/Ergomotion: percentage (0-100, max_angle is set to 100)
        max_angle = self.entity_description.max_angle
        return min(max_angle, max(0.0, float(position)))

    async def async_set_native_value(self, value: float) -> None:
        """Set the position by seeking to the target angle (or percentage for Keeson/Ergomotion)."""
        unit = self.entity_description.native_unit_of_measurement or "°"
        _LOGGER.info(
            "Position set requested: %s to %.1f%s (device: %s)",
            self.entity_description.key,
            value,
            unit,
            self._coordinator.name,
        )

        await self._coordinator.async_seek_position(
            position_key=self.entity_description.position_key,
            target_angle=value,
            move_up_fn=self.entity_description.move_up_fn,
            move_down_fn=self.entity_description.move_down_fn,
            move_stop_fn=self.entity_description.move_stop_fn,
        )


class AdjustableBedMassageNumber(AdjustableBedEntity, NumberEntity):
    """Number entity for Adjustable Bed massage intensity control."""

    entity_description: AdjustableBedMassageNumberEntityDescription

    def __init__(
        self,
        coordinator: AdjustableBedCoordinator,
        description: AdjustableBedMassageNumberEntityDescription,
    ) -> None:
        """Initialize the massage number entity."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.address}_{description.key}"

    @property
    def native_value(self) -> float | None:
        """Return the current massage intensity from controller state."""
        controller = self._coordinator.controller
        if controller is None:
            return None

        # Get massage state from controller
        state = controller.get_massage_state()
        zone = self.entity_description.massage_zone

        # Map zone to state key
        key_map = {
            "head": "head_intensity",
            "foot": "foot_intensity",
            "wave": "wave_intensity",
        }
        state_key = key_map.get(zone)
        if state_key and state_key in state:
            return float(state[state_key])
        return 0.0

    async def async_set_native_value(self, value: float) -> None:
        """Set the massage intensity level."""
        zone = self.entity_description.massage_zone
        level = round(value)

        _LOGGER.info(
            "Massage intensity set requested: %s zone to level %d (device: %s)",
            zone,
            level,
            self._coordinator.name,
        )

        async def _set_intensity(ctrl: BedController) -> None:
            await ctrl.set_massage_intensity(zone, level)

        await self._coordinator.async_execute_controller_command(_set_intensity)
