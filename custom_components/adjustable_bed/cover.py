"""Cover entities for Adjustable Bed integration."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable, Coroutine

from homeassistant.components.cover import (
    CoverDeviceClass,
    CoverEntity,
    CoverEntityDescription,
    CoverEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_MOTOR_COUNT, DEFAULT_MOTOR_COUNT, DOMAIN
from .coordinator import AdjustableBedCoordinator
from .entity import AdjustableBedEntity

if TYPE_CHECKING:
    from .beds.base import BedController

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class AdjustableBedCoverEntityDescription(CoverEntityDescription):
    """Describes a Adjustable Bed cover entity."""

    open_fn: Callable[[BedController], Coroutine[Any, Any, None]]
    close_fn: Callable[[BedController], Coroutine[Any, Any, None]]
    stop_fn: Callable[[BedController], Coroutine[Any, Any, None]]
    min_motors: int = 2


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

    entities = []
    for description in COVER_DESCRIPTIONS:
        # Special handling for lumbar - only add if bed type supports it
        if description.key == "lumbar":
            # Only Mattress Firm supports lumbar motor
            from .const import BED_TYPE_MATTRESSFIRM
            if coordinator.bed_type == BED_TYPE_MATTRESSFIRM:
                entities.append(AdjustableBedCover(coordinator, description))
        elif motor_count >= description.min_motors:
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

    @property
    def is_closed(self) -> bool | None:
        """Return if the cover is closed (flat position)."""
        # We don't have position feedback for all motor types
        # Return None to indicate unknown state
        angle = self._coordinator.position_data.get(self.entity_description.key)
        if angle is not None:
            return angle == 0
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
        # Get angle from position data if available
        angle = self._coordinator.position_data.get(self.entity_description.key)
        if angle is None:
            return None

        # Convert angle to percentage (0-100)
        # Max angles vary by motor type, but we'll normalize
        max_angles = {
            "back": 68,
            "legs": 45,
            "head": 68,
            "feet": 45,
        }
        max_angle = max_angles.get(self.entity_description.key, 68)
        return min(100, int((angle / max_angle) * 100))

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
        except Exception as err:
            _LOGGER.error(
                "Failed to move cover %s: %s",
                self.entity_description.key,
                err,
            )
        finally:
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

        try:
            _LOGGER.debug("Sending stop command for %s", self.entity_description.key)
            await self._coordinator.async_stop_command()
            _LOGGER.debug("Stop command sent for %s", self.entity_description.key)
        except Exception as err:
            _LOGGER.error(
                "Failed to stop cover %s: %s",
                self.entity_description.key,
                err,
            )
        finally:
            self._is_moving = False
            self._move_direction = None
            self.async_write_ha_state()

