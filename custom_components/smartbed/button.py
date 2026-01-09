"""Button entities for Smart Bed integration."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable, Coroutine, Any

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_HAS_MASSAGE, DOMAIN
from .coordinator import SmartBedCoordinator
from .entity import SmartBedEntity

if TYPE_CHECKING:
    from .beds.base import BedController

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class SmartBedButtonEntityDescription(ButtonEntityDescription):
    """Describes a Smart Bed button entity."""

    press_fn: Callable[[BedController], Coroutine[Any, Any, None]] | None = None
    requires_massage: bool = False
    entity_category: EntityCategory | None = None
    is_coordinator_action: bool = False  # If True, this is a coordinator-level action (connect/disconnect)


BUTTON_DESCRIPTIONS: tuple[SmartBedButtonEntityDescription, ...] = (
    # Preset buttons
    SmartBedButtonEntityDescription(
        key="preset_memory_1",
        translation_key="preset_memory_1",
        icon="mdi:numeric-1-box",
        press_fn=lambda ctrl: ctrl.preset_memory(1),
    ),
    SmartBedButtonEntityDescription(
        key="preset_memory_2",
        translation_key="preset_memory_2",
        icon="mdi:numeric-2-box",
        press_fn=lambda ctrl: ctrl.preset_memory(2),
    ),
    SmartBedButtonEntityDescription(
        key="preset_memory_3",
        translation_key="preset_memory_3",
        icon="mdi:numeric-3-box",
        press_fn=lambda ctrl: ctrl.preset_memory(3),
    ),
    SmartBedButtonEntityDescription(
        key="preset_memory_4",
        translation_key="preset_memory_4",
        icon="mdi:numeric-4-box",
        press_fn=lambda ctrl: ctrl.preset_memory(4),
    ),
    # Program buttons (config category)
    SmartBedButtonEntityDescription(
        key="program_memory_1",
        translation_key="program_memory_1",
        icon="mdi:content-save",
        entity_category=EntityCategory.CONFIG,
        press_fn=lambda ctrl: ctrl.program_memory(1),
    ),
    SmartBedButtonEntityDescription(
        key="program_memory_2",
        translation_key="program_memory_2",
        icon="mdi:content-save",
        entity_category=EntityCategory.CONFIG,
        press_fn=lambda ctrl: ctrl.program_memory(2),
    ),
    SmartBedButtonEntityDescription(
        key="program_memory_3",
        translation_key="program_memory_3",
        icon="mdi:content-save",
        entity_category=EntityCategory.CONFIG,
        press_fn=lambda ctrl: ctrl.program_memory(3),
    ),
    SmartBedButtonEntityDescription(
        key="program_memory_4",
        translation_key="program_memory_4",
        icon="mdi:content-save",
        entity_category=EntityCategory.CONFIG,
        press_fn=lambda ctrl: ctrl.program_memory(4),
    ),
    # Stop button
    SmartBedButtonEntityDescription(
        key="stop",
        translation_key="stop",
        icon="mdi:stop",
        press_fn=lambda ctrl: ctrl.stop_all(),
    ),
    # Connection control buttons (diagnostic)
    SmartBedButtonEntityDescription(
        key="disconnect",
        name=None,
        translation_key="disconnect",
        icon="mdi:bluetooth-off",
        entity_category=EntityCategory.DIAGNOSTIC,
        is_coordinator_action=True,
    ),
    SmartBedButtonEntityDescription(
        key="connect",
        name=None,
        translation_key="connect",
        icon="mdi:bluetooth-connect",
        entity_category=EntityCategory.DIAGNOSTIC,
        is_coordinator_action=True,
    ),
    # Massage buttons (only if has_massage)
    SmartBedButtonEntityDescription(
        key="massage_all_off",
        translation_key="massage_all_off",
        icon="mdi:vibrate-off",
        requires_massage=True,
        press_fn=lambda ctrl: ctrl.massage_off(),
    ),
    SmartBedButtonEntityDescription(
        key="massage_all_toggle",
        translation_key="massage_all_toggle",
        icon="mdi:vibrate",
        requires_massage=True,
        press_fn=lambda ctrl: ctrl.massage_toggle(),
    ),
    SmartBedButtonEntityDescription(
        key="massage_all_up",
        translation_key="massage_all_up",
        icon="mdi:arrow-up-bold",
        requires_massage=True,
        press_fn=lambda ctrl: ctrl.massage_intensity_up(),
    ),
    SmartBedButtonEntityDescription(
        key="massage_all_down",
        translation_key="massage_all_down",
        icon="mdi:arrow-down-bold",
        requires_massage=True,
        press_fn=lambda ctrl: ctrl.massage_intensity_down(),
    ),
    SmartBedButtonEntityDescription(
        key="massage_head_toggle",
        translation_key="massage_head_toggle",
        icon="mdi:head",
        requires_massage=True,
        press_fn=lambda ctrl: ctrl.massage_head_toggle(),
    ),
    SmartBedButtonEntityDescription(
        key="massage_head_up",
        translation_key="massage_head_up",
        icon="mdi:arrow-up",
        requires_massage=True,
        press_fn=lambda ctrl: ctrl.massage_head_up(),
    ),
    SmartBedButtonEntityDescription(
        key="massage_head_down",
        translation_key="massage_head_down",
        icon="mdi:arrow-down",
        requires_massage=True,
        press_fn=lambda ctrl: ctrl.massage_head_down(),
    ),
    SmartBedButtonEntityDescription(
        key="massage_foot_toggle",
        translation_key="massage_foot_toggle",
        icon="mdi:foot-print",
        requires_massage=True,
        press_fn=lambda ctrl: ctrl.massage_foot_toggle(),
    ),
    SmartBedButtonEntityDescription(
        key="massage_foot_up",
        translation_key="massage_foot_up",
        icon="mdi:arrow-up",
        requires_massage=True,
        press_fn=lambda ctrl: ctrl.massage_foot_up(),
    ),
    SmartBedButtonEntityDescription(
        key="massage_foot_down",
        translation_key="massage_foot_down",
        icon="mdi:arrow-down",
        requires_massage=True,
        press_fn=lambda ctrl: ctrl.massage_foot_down(),
    ),
    SmartBedButtonEntityDescription(
        key="massage_mode_step",
        translation_key="massage_mode_step",
        icon="mdi:format-list-numbered",
        requires_massage=True,
        press_fn=lambda ctrl: ctrl.massage_mode_step(),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Smart Bed button entities."""
    coordinator: SmartBedCoordinator = hass.data[DOMAIN][entry.entry_id]
    has_massage = entry.data.get(CONF_HAS_MASSAGE, False)

    entities = []
    for description in BUTTON_DESCRIPTIONS:
        if description.requires_massage and not has_massage:
            continue
        entities.append(SmartBedButton(coordinator, description))

    async_add_entities(entities)


class SmartBedButton(SmartBedEntity, ButtonEntity):
    """Button entity for Smart Bed."""

    entity_description: SmartBedButtonEntityDescription

    def __init__(
        self,
        coordinator: SmartBedCoordinator,
        description: SmartBedButtonEntityDescription,
    ) -> None:
        """Initialize the button."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.address}_{description.key}"
        self._attr_translation_key = description.translation_key

    async def async_press(self) -> None:
        """Handle button press."""
        _LOGGER.info(
            "Button pressed: %s (device: %s)",
            self.entity_description.key,
            self._coordinator.name,
        )

        # Handle coordinator-level actions (connect/disconnect/stop)
        if self.entity_description.is_coordinator_action:
            try:
                if self.entity_description.key == "disconnect":
                    await self._coordinator.async_disconnect()
                    _LOGGER.info("Disconnected from bed - physical remote should now work")
                elif self.entity_description.key == "connect":
                    await self._coordinator.async_ensure_connected()
                    _LOGGER.info("Connected to bed")
            except Exception as err:
                _LOGGER.error(
                    "Failed to execute coordinator action %s: %s",
                    self.entity_description.key,
                    err,
                )
            return

        # Stop button gets special handling - cancels current command immediately
        if self.entity_description.key == "stop":
            try:
                await self._coordinator.async_stop_command()
            except Exception as err:
                _LOGGER.error("Failed to execute stop command: %s", err)
            return

        try:
            _LOGGER.debug("Executing button action: %s", self.entity_description.key)
            await self._coordinator.async_execute_controller_command(
                self.entity_description.press_fn
            )
            _LOGGER.debug("Button action completed: %s", self.entity_description.key)
        except Exception as err:
            _LOGGER.error(
                "Failed to execute button action %s: %s",
                self.entity_description.key,
                err,
            )

