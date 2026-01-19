"""Number entities for Adjustable Bed integration."""

from __future__ import annotations

import logging
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from homeassistant.components.number import (
    NumberDeviceClass,
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
    CONF_MOTOR_COUNT,
    DEFAULT_MOTOR_COUNT,
    DOMAIN,
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
        native_max_value=100,
        native_step=1,
        native_unit_of_measurement="%",
        device_class=NumberDeviceClass.POWER_FACTOR,
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
        native_max_value=100,
        native_step=1,
        native_unit_of_measurement="%",
        device_class=NumberDeviceClass.POWER_FACTOR,
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
        native_max_value=100,
        native_step=1,
        native_unit_of_measurement="%",
        device_class=NumberDeviceClass.POWER_FACTOR,
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
        native_max_value=100,
        native_step=1,
        native_unit_of_measurement="%",
        device_class=NumberDeviceClass.POWER_FACTOR,
        mode=NumberMode.SLIDER,
        position_key="feet",
        move_up_fn=lambda ctrl: ctrl.move_feet_up(),
        move_down_fn=lambda ctrl: ctrl.move_feet_down(),
        move_stop_fn=lambda ctrl: ctrl.move_feet_stop(),
        max_angle=45.0,
        min_motors=4,
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

    # Skip number entities if angle sensing is disabled
    if coordinator.disable_angle_sensing:
        _LOGGER.debug(
            "Angle sensing disabled for %s, skipping position number entities",
            coordinator.name,
        )
        return

    # Skip number entities for beds without position feedback
    if bed_type not in BEDS_WITH_POSITION_FEEDBACK:
        _LOGGER.debug(
            "Bed type %s does not support position feedback, skipping position number entities",
            bed_type,
        )
        return

    entities: list[AdjustableBedPositionNumber] = []

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
        head_desc = descriptions_by_key["head_position"]
        keeson_head_desc = AdjustableBedNumberEntityDescription(
            key=head_desc.key,
            translation_key=head_desc.translation_key,
            icon=head_desc.icon,
            native_min_value=head_desc.native_min_value,
            native_max_value=head_desc.native_max_value,
            native_step=head_desc.native_step,
            native_unit_of_measurement=head_desc.native_unit_of_measurement,
            device_class=head_desc.device_class,
            mode=head_desc.mode,
            position_key="back",  # Map to "back" in position_data
            move_up_fn=head_desc.move_up_fn,
            move_down_fn=head_desc.move_down_fn,
            move_stop_fn=head_desc.move_stop_fn,
            max_angle=head_desc.max_angle,
            min_motors=2,
        )
        entities.append(AdjustableBedPositionNumber(coordinator, keeson_head_desc))

        # Create feet position (maps to "legs" position data)
        feet_desc = descriptions_by_key["feet_position"]
        keeson_feet_desc = AdjustableBedNumberEntityDescription(
            key=feet_desc.key,
            translation_key=feet_desc.translation_key,
            icon=feet_desc.icon,
            native_min_value=feet_desc.native_min_value,
            native_max_value=feet_desc.native_max_value,
            native_step=feet_desc.native_step,
            native_unit_of_measurement=feet_desc.native_unit_of_measurement,
            device_class=feet_desc.device_class,
            mode=feet_desc.mode,
            position_key="legs",  # Map to "legs" in position_data
            move_up_fn=feet_desc.move_up_fn,
            move_down_fn=feet_desc.move_down_fn,
            move_stop_fn=feet_desc.move_stop_fn,
            max_angle=feet_desc.max_angle,
            min_motors=2,
        )
        entities.append(AdjustableBedPositionNumber(coordinator, keeson_feet_desc))
    else:
        # Standard bed motor layout (Back/Legs/Head/Feet)
        for description in NUMBER_DESCRIPTIONS:
            if motor_count >= description.min_motors:
                entities.append(AdjustableBedPositionNumber(coordinator, description))

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
        """Return the current position as a percentage."""
        position = self._coordinator.position_data.get(
            self.entity_description.position_key
        )
        if position is None:
            return None

        # Check if controller reports percentage directly (e.g., Keeson/Ergomotion)
        controller = self._coordinator.controller
        if controller is not None and getattr(
            controller, "reports_percentage_position", False
        ):
            # Position is already 0-100 percentage
            return min(100.0, max(0.0, float(position)))

        # Convert angle to percentage (0-100) using the description's max_angle
        max_angle = self.entity_description.max_angle
        return min(100.0, (position / max_angle) * 100)

    async def async_set_native_value(self, value: float) -> None:
        """Set the position by seeking to the target percentage."""
        _LOGGER.info(
            "Position set requested: %s to %.1f%% (device: %s)",
            self.entity_description.key,
            value,
            self._coordinator.name,
        )

        await self._coordinator.async_seek_position(
            position_key=self.entity_description.position_key,
            target_percentage=value,
            move_up_fn=self.entity_description.move_up_fn,
            move_down_fn=self.entity_description.move_down_fn,
            move_stop_fn=self.entity_description.move_stop_fn,
            max_angle=self.entity_description.max_angle,
        )
