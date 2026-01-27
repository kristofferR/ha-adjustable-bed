"""Cover entities for Adjustable Bed integration."""

from __future__ import annotations

import logging
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from homeassistant.components.cover import (
    CoverDeviceClass,
    CoverEntity,
    CoverEntityDescription,
    CoverEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    BED_TYPE_ERGOMOTION,
    BED_TYPE_KEESON,
    BED_TYPE_REVERIE,
    BED_TYPE_REVERIE_NIGHTSTAND,
    BEDS_WITH_PERCENTAGE_POSITIONS,
    CONF_MOTOR_COUNT,
    DEFAULT_MOTOR_COUNT,
    DOMAIN,
)
from .coordinator import AdjustableBedCoordinator
from .entity import AdjustableBedEntity

if TYPE_CHECKING:
    from .beds.base import BedController

_LOGGER = logging.getLogger(__name__)

# Bed-type-specific max angles for back/head motors
# Reverie beds report position 0-100 which maps to 0-60 degrees (not 68)
REVERIE_BACK_MAX_ANGLE = 60


@dataclass(frozen=True, kw_only=True)
class AdjustableBedCoverEntityDescription(CoverEntityDescription):
    """Describes a Adjustable Bed cover entity."""

    open_fn: Callable[[BedController], Coroutine[Any, Any, None]]
    close_fn: Callable[[BedController], Coroutine[Any, Any, None]]
    stop_fn: Callable[[BedController], Coroutine[Any, Any, None]]
    min_motors: int = 2
    # Key to look up in coordinator.position_data (defaults to key if not set)
    position_key: str | None = None
    # Maximum angle for percentage calculation (default 68 degrees)
    max_angle: int = 68


# Note: For Linak beds:
# - 2 motors: back and legs
# - 3 motors: back, legs, head
# - 4 motors: back, legs, head, feet
COVER_DESCRIPTIONS: tuple[AdjustableBedCoverEntityDescription, ...] = (
    AdjustableBedCoverEntityDescription(
        key="back",
        translation_key="back",
        icon="mdi:human-handsup",
        device_class=CoverDeviceClass.DAMPER,
        open_fn=lambda ctrl: ctrl.move_back_up(),
        close_fn=lambda ctrl: ctrl.move_back_down(),
        stop_fn=lambda ctrl: ctrl.move_back_stop(),
        min_motors=2,
    ),
    AdjustableBedCoverEntityDescription(
        key="legs",
        translation_key="legs",
        icon="mdi:human-handsdown",
        device_class=CoverDeviceClass.DAMPER,
        open_fn=lambda ctrl: ctrl.move_legs_up(),
        close_fn=lambda ctrl: ctrl.move_legs_down(),
        stop_fn=lambda ctrl: ctrl.move_legs_stop(),
        min_motors=2,
        max_angle=45,
    ),
    AdjustableBedCoverEntityDescription(
        key="head",
        translation_key="head",
        icon="mdi:head",
        device_class=CoverDeviceClass.DAMPER,
        open_fn=lambda ctrl: ctrl.move_head_up(),
        close_fn=lambda ctrl: ctrl.move_head_down(),
        stop_fn=lambda ctrl: ctrl.move_head_stop(),
        min_motors=3,
    ),
    AdjustableBedCoverEntityDescription(
        key="feet",
        translation_key="feet",
        icon="mdi:foot-print",
        device_class=CoverDeviceClass.DAMPER,
        open_fn=lambda ctrl: ctrl.move_feet_up(),
        close_fn=lambda ctrl: ctrl.move_feet_down(),
        stop_fn=lambda ctrl: ctrl.move_feet_stop(),
        min_motors=4,
        max_angle=45,
    ),
    AdjustableBedCoverEntityDescription(
        key="lumbar",
        translation_key="lumbar",
        icon="mdi:lumbar-vertebrae",
        device_class=CoverDeviceClass.DAMPER,
        open_fn=lambda ctrl: ctrl.move_lumbar_up(),
        close_fn=lambda ctrl: ctrl.move_lumbar_down(),
        stop_fn=lambda ctrl: ctrl.move_lumbar_stop(),
        min_motors=2,  # Lumbar is independent of motor count
        max_angle=30,
    ),
    AdjustableBedCoverEntityDescription(
        key="pillow",
        translation_key="pillow",
        icon="mdi:pillow",
        device_class=CoverDeviceClass.DAMPER,
        open_fn=lambda ctrl: ctrl.move_pillow_up(),
        close_fn=lambda ctrl: ctrl.move_pillow_down(),
        stop_fn=lambda ctrl: ctrl.move_pillow_stop(),
        min_motors=2,  # Pillow is independent of motor count
    ),
    AdjustableBedCoverEntityDescription(
        key="tilt",
        translation_key="tilt",
        icon="mdi:angle-acute",
        device_class=CoverDeviceClass.DAMPER,
        open_fn=lambda ctrl: ctrl.move_tilt_up(),
        close_fn=lambda ctrl: ctrl.move_tilt_down(),
        stop_fn=lambda ctrl: ctrl.move_tilt_stop(),
        min_motors=2,  # Tilt is independent of motor count
        max_angle=45,
    ),
    AdjustableBedCoverEntityDescription(
        key="hip",
        translation_key="hip",
        icon="mdi:human",
        device_class=CoverDeviceClass.DAMPER,
        open_fn=lambda ctrl: ctrl.move_hip_up(),
        close_fn=lambda ctrl: ctrl.move_hip_down(),
        stop_fn=lambda ctrl: ctrl.move_hip_stop(),
        min_motors=2,  # Hip is independent of motor count
        max_angle=45,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Adjustable Bed cover entities."""
    coordinator: AdjustableBedCoordinator = hass.data[DOMAIN][entry.entry_id]
    motor_count = entry.data.get(CONF_MOTOR_COUNT, DEFAULT_MOTOR_COUNT)
    controller = coordinator.controller

    # Skip motor cover entities if bed doesn't support motor control
    if controller is not None and not controller.supports_motor_control:
        _LOGGER.debug(
            "Skipping motor covers for %s - bed only supports presets",
            coordinator.name,
        )
        return

    # Skip motor cover entities if bed uses discrete motor control (buttons instead)
    if controller is not None and controller.has_discrete_motor_control:
        _LOGGER.debug(
            "Skipping motor covers for %s - bed uses discrete motor control (buttons instead)",
            coordinator.name,
        )
        return

    entities = []

    # Keeson and Ergomotion beds use different motor naming:
    # Head/Feet/Tilt/Lumbar instead of Back/Legs/Head/Feet
    # Position data comes in as "back"/"legs", so we need position_key mapping
    if coordinator.bed_type in (BED_TYPE_KEESON, BED_TYPE_ERGOMOTION):
        _LOGGER.debug(
            "Setting up Keeson/Ergomotion covers for %s (motor_count=%d)",
            coordinator.name,
            motor_count,
        )
        # Find the specific descriptions we need
        descriptions_by_key = {d.key: d for d in COVER_DESCRIPTIONS}

        # Get translation key overrides from controller
        translation_overrides = (
            controller.motor_translation_keys if controller is not None else None
        ) or {}

        # Create Keeson-specific head description that maps to "back" position data
        # Keeson "head" motor = upper body, position reported as "back"
        head_desc = descriptions_by_key["head"]
        keeson_head_desc = AdjustableBedCoverEntityDescription(
            key=head_desc.key,
            translation_key=translation_overrides.get("head", head_desc.translation_key),
            icon=head_desc.icon,
            device_class=head_desc.device_class,
            open_fn=head_desc.open_fn,
            close_fn=head_desc.close_fn,
            stop_fn=head_desc.stop_fn,
            min_motors=2,
            position_key="back",  # Map to "back" in position_data
            max_angle=head_desc.max_angle,
        )
        entities.append(AdjustableBedCover(coordinator, keeson_head_desc))

        # Create Keeson-specific feet description that maps to "legs" position data
        # Keeson "feet" motor = lower body, position reported as "legs"
        feet_desc = descriptions_by_key["feet"]
        keeson_feet_desc = AdjustableBedCoverEntityDescription(
            key=feet_desc.key,
            translation_key=translation_overrides.get("feet", feet_desc.translation_key),
            icon=feet_desc.icon,
            device_class=feet_desc.device_class,
            open_fn=feet_desc.open_fn,
            close_fn=feet_desc.close_fn,
            stop_fn=feet_desc.stop_fn,
            min_motors=2,
            position_key="legs",  # Map to "legs" in position_data
            max_angle=feet_desc.max_angle,
        )
        entities.append(AdjustableBedCover(coordinator, keeson_feet_desc))

        # Add tilt for 3+ motors if controller supports it
        if (
            motor_count >= 3
            and "tilt" in descriptions_by_key
            and controller is not None
            and controller.has_tilt_support
        ):
            tilt_desc = descriptions_by_key["tilt"]
            keeson_tilt_desc = AdjustableBedCoverEntityDescription(
                key=tilt_desc.key,
                translation_key=translation_overrides.get("tilt", tilt_desc.translation_key),
                icon=tilt_desc.icon,
                device_class=tilt_desc.device_class,
                open_fn=tilt_desc.open_fn,
                close_fn=tilt_desc.close_fn,
                stop_fn=tilt_desc.stop_fn,
                min_motors=tilt_desc.min_motors,
                position_key=tilt_desc.position_key,
                max_angle=tilt_desc.max_angle,
            )
            entities.append(AdjustableBedCover(coordinator, keeson_tilt_desc))

        # Add lumbar for 4 motors if controller supports it
        if (
            motor_count >= 4
            and "lumbar" in descriptions_by_key
            and controller is not None
            and controller.has_lumbar_support
        ):
            entities.append(AdjustableBedCover(coordinator, descriptions_by_key["lumbar"]))
    else:
        # Standard bed motor layout (Back/Legs/Head/Feet)
        # Check if bed type needs adjusted max angles
        is_reverie = coordinator.bed_type in (BED_TYPE_REVERIE, BED_TYPE_REVERIE_NIGHTSTAND)

        for description in COVER_DESCRIPTIONS:
            # Skip tilt - only for Keeson/Ergomotion
            if description.key == "tilt":
                continue
            # Special handling for lumbar - only add if controller supports it
            if description.key == "lumbar":
                if controller is not None and controller.has_lumbar_support:
                    entities.append(AdjustableBedCover(coordinator, description))
            # Special handling for pillow - only add if controller supports it
            elif description.key == "pillow":
                if controller is not None and controller.has_pillow_support:
                    entities.append(AdjustableBedCover(coordinator, description))
            # Special handling for hip - only add if controller supports it
            elif description.key == "hip":
                if controller is not None and controller.has_hip_support:
                    entities.append(AdjustableBedCover(coordinator, description))
            elif motor_count >= description.min_motors:
                # For Reverie beds, adjust max_angle for back/head motors
                if is_reverie and description.key in ("back", "head"):
                    adjusted_desc = AdjustableBedCoverEntityDescription(
                        key=description.key,
                        translation_key=description.translation_key,
                        icon=description.icon,
                        device_class=description.device_class,
                        open_fn=description.open_fn,
                        close_fn=description.close_fn,
                        stop_fn=description.stop_fn,
                        min_motors=description.min_motors,
                        position_key=description.position_key,
                        max_angle=REVERIE_BACK_MAX_ANGLE,
                    )
                    entities.append(AdjustableBedCover(coordinator, adjusted_desc))
                else:
                    entities.append(AdjustableBedCover(coordinator, description))

    async_add_entities(entities)


class AdjustableBedCover(AdjustableBedEntity, CoverEntity):
    """Cover entity for Adjustable Bed motor control."""

    entity_description: AdjustableBedCoverEntityDescription
    _attr_supported_features = (
        CoverEntityFeature.OPEN | CoverEntityFeature.CLOSE | CoverEntityFeature.STOP
    )

    def __init__(
        self,
        coordinator: AdjustableBedCoordinator,
        description: AdjustableBedCoverEntityDescription,
    ) -> None:
        """Initialize the cover."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.address}_{description.key}"
        self._is_moving = False
        self._move_direction: str | None = None
        self._movement_generation: int = 0  # Track active movement to handle cancellation

    @property
    def _position_key(self) -> str:
        """Return the key to look up in position_data."""
        return self.entity_description.position_key or self.entity_description.key

    @property
    def is_closed(self) -> bool | None:
        """Return if the cover is closed (flat position)."""
        if self._coordinator.disable_angle_sensing:
            return None
        # We don't have position feedback for all motor types
        # Return None to indicate unknown state
        angle = self._coordinator.position_data.get(self._position_key)
        if angle is not None:
            # Use 1-degree tolerance for sensor noise/precision issues
            return angle < 1.0
        return None

    @property
    def is_opening(self) -> bool:
        """Return if the cover is opening."""
        return self._is_moving and self._move_direction == "open"

    @property
    def is_closing(self) -> bool:
        """Return if the cover is closing."""
        return self._is_moving and self._move_direction == "close"

    @property
    def current_cover_position(self) -> int | None:
        """Return current position of cover."""
        if self._coordinator.disable_angle_sensing:
            return None
        # Get position from position data if available
        position = self._coordinator.position_data.get(self._position_key)
        if position is None:
            return None

        # Check if bed type reports percentage directly (e.g., Keeson/Ergomotion/Serta)
        # Use bed_type constant check instead of controller to handle disconnected state
        if self._coordinator.bed_type in BEDS_WITH_PERCENTAGE_POSITIONS:
            # Position is already 0-100 percentage
            return min(100, max(0, int(position)))

        # Convert angle to percentage (0-100) using the description's max_angle
        max_angle = self.entity_description.max_angle
        return max(0, min(100, int((position / max_angle) * 100)))

    async def async_open_cover(self, **kwargs: Any) -> None:
        """Open the cover (raise the motor)."""
        await self._async_start_movement("open")

    async def async_close_cover(self, **kwargs: Any) -> None:
        """Close the cover (lower the motor)."""
        await self._async_start_movement("close")

    async def async_stop_cover(self, **kwargs: Any) -> None:
        """Stop the cover."""
        await self._async_stop_movement()

    async def _async_start_movement(self, direction: str) -> None:
        """Start moving the cover."""
        _LOGGER.info(
            "Cover movement: %s %s (device: %s)",
            self.entity_description.key,
            direction,
            self._coordinator.name,
        )

        # Increment generation to track this specific movement
        self._movement_generation += 1
        current_generation = self._movement_generation

        self._is_moving = True
        self._move_direction = direction
        self.async_write_ha_state()

        try:
            _LOGGER.debug(
                "Starting %s movement for %s",
                direction,
                self.entity_description.key,
            )
            if direction == "open":
                await self._coordinator.async_execute_controller_command(
                    self.entity_description.open_fn
                )
            else:
                await self._coordinator.async_execute_controller_command(
                    self.entity_description.close_fn
                )
            _LOGGER.debug(
                "Movement command sent for %s %s",
                self.entity_description.key,
                direction,
            )
        except Exception:
            _LOGGER.exception(
                "Failed to move cover %s",
                self.entity_description.key,
            )
        finally:
            # Only clear state if no newer movement has started
            if self._movement_generation == current_generation:
                self._is_moving = False
                self._move_direction = None
                self.async_write_ha_state()

    async def _async_stop_movement(self) -> None:
        """Stop the cover movement."""
        _LOGGER.info(
            "Cover stop: %s (device: %s)",
            self.entity_description.key,
            self._coordinator.name,
        )

        # Capture generation at stop start to avoid clearing state from a newer movement
        # that started after this stop was called (rapid stop→move sequence)
        stop_generation = self._movement_generation

        try:
            _LOGGER.debug("Sending stop command for %s", self.entity_description.key)
            await self._coordinator.async_execute_controller_command(
                self.entity_description.stop_fn
            )
            _LOGGER.debug("Stop command sent for %s", self.entity_description.key)
        except Exception:
            _LOGGER.exception(
                "Failed to stop cover %s",
                self.entity_description.key,
            )
        finally:
            # Only clear state if no newer movement has started since stop was called
            if self._movement_generation == stop_generation:
                self._is_moving = False
                self._move_direction = None
                self.async_write_ha_state()
