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
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    BED_TYPE_REVERIE,
    BED_TYPE_REVERIE_NIGHTSTAND,
    BEDS_WITH_PERCENTAGE_POSITIONS,
    DOMAIN,
    REVERIE_BACK_MAX_ANGLE,
)
from .coordinator import AdjustableBedCoordinator
from .entity import AdjustableBedEntity

if TYPE_CHECKING:
    from .beds.base import BedController, MotorControlSpec

_LOGGER = logging.getLogger(__name__)


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
        key="neck",
        translation_key="neck",
        icon="mdi:head-outline",
        device_class=CoverDeviceClass.DAMPER,
        open_fn=lambda ctrl: ctrl.move_neck_up(),
        close_fn=lambda ctrl: ctrl.move_neck_down(),
        stop_fn=lambda ctrl: ctrl.move_neck_stop(),
        min_motors=2,  # Neck is independent of motor count
        max_angle=30,
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
    AdjustableBedCoverEntityDescription(
        key="bed_height",
        translation_key="bed_height",
        icon="mdi:arrow-up-down",
        device_class=CoverDeviceClass.DAMPER,
        open_fn=lambda ctrl: ctrl.move_bed_height_up(),
        close_fn=lambda ctrl: ctrl.move_bed_height_down(),
        stop_fn=lambda ctrl: ctrl.move_bed_height_stop(),
        min_motors=2,  # Bed height is independent of motor count
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Adjustable Bed cover entities."""
    coordinator: AdjustableBedCoordinator = hass.data[DOMAIN][entry.entry_id]
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

    if controller is None:
        _LOGGER.warning("Skipping motor covers for %s - controller not available", coordinator.name)
        return

    _async_remove_stale_cover_entities(hass, coordinator, controller)

    entities = [
        AdjustableBedCover(coordinator, _build_cover_description(coordinator, spec))
        for spec in controller.motor_control_specs
    ]

    async_add_entities(entities)


def _build_cover_description(
    coordinator: AdjustableBedCoordinator,
    spec: MotorControlSpec,
) -> AdjustableBedCoverEntityDescription:
    """Build a cover description from the controller-provided motor spec."""
    templates_by_key = {description.key: description for description in COVER_DESCRIPTIONS}
    template = templates_by_key[spec.key]
    max_angle = spec.max_angle

    if coordinator.bed_type in (BED_TYPE_REVERIE, BED_TYPE_REVERIE_NIGHTSTAND) and spec.key in (
        "back",
        "head",
    ):
        max_angle = REVERIE_BACK_MAX_ANGLE

    return AdjustableBedCoverEntityDescription(
        key=template.key,
        translation_key=spec.translation_key,
        icon=template.icon,
        device_class=template.device_class,
        open_fn=spec.open_fn,
        close_fn=spec.close_fn,
        stop_fn=spec.stop_fn,
        position_key=spec.position_key,
        max_angle=max_angle,
    )


def _async_remove_stale_cover_entities(
    hass: HomeAssistant,
    coordinator: AdjustableBedCoordinator,
    controller: BedController,
) -> None:
    """Remove stale cover entities that should no longer be exposed."""
    if not controller.stale_motor_entity_keys:
        return

    registry = er.async_get(hass)
    active_keys = {spec.key for spec in controller.motor_control_specs}

    for key in controller.stale_motor_entity_keys:
        if key in active_keys:
            continue

        unique_id = f"{coordinator.address}_{key}"
        entity_id = registry.async_get_entity_id("cover", DOMAIN, unique_id)
        if entity_id is not None:
            registry.async_remove(entity_id)
            _LOGGER.info("Removed stale cover entity %s for %s", entity_id, coordinator.name)


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
            raise
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
            raise
        finally:
            # Only clear state if no newer movement has started since stop was called
            if self._movement_generation == stop_generation:
                self._is_moving = False
                self._move_direction = None
                self.async_write_ha_state()
