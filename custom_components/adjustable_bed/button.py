"""Button entities for Adjustable Bed integration."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable, Coroutine, Any

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    BED_TYPE_KEESON,
    BED_TYPE_LEGGETT_PLATT,
    BED_TYPE_MOTOSLEEP,
    BED_TYPE_REVERIE,
    BED_TYPE_RICHMAT,
    BED_TYPE_SOLACE,
    CONF_BED_TYPE,
    CONF_HAS_MASSAGE,
    DOMAIN,
)
from .coordinator import AdjustableBedCoordinator
from .entity import AdjustableBedEntity

if TYPE_CHECKING:
    from .beds.base import BedController

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class AdjustableBedButtonEntityDescription(ButtonEntityDescription):
    """Describes a Adjustable Bed button entity."""

    press_fn: Callable[[BedController], Coroutine[Any, Any, None]] | None = None
    requires_massage: bool = False
    entity_category: EntityCategory | None = None
    is_coordinator_action: bool = False  # If True, this is a coordinator-level action (connect/disconnect)
    cancel_movement: bool = False  # If True, cancels any running motor command
    supported_bed_types: tuple[str, ...] | None = None  # If set, only create for these bed types


BUTTON_DESCRIPTIONS: tuple[AdjustableBedButtonEntityDescription, ...] = (
    # Preset buttons
    AdjustableBedButtonEntityDescription(
        key="preset_memory_1",
        translation_key="preset_memory_1",
        icon="mdi:numeric-1-box",
        press_fn=lambda ctrl: ctrl.preset_memory(1),
        cancel_movement=True,
    ),
    AdjustableBedButtonEntityDescription(
        key="preset_memory_2",
        translation_key="preset_memory_2",
        icon="mdi:numeric-2-box",
        press_fn=lambda ctrl: ctrl.preset_memory(2),
        cancel_movement=True,
    ),
    AdjustableBedButtonEntityDescription(
        key="preset_memory_3",
        translation_key="preset_memory_3",
        icon="mdi:numeric-3-box",
        press_fn=lambda ctrl: ctrl.preset_memory(3),
        cancel_movement=True,
    ),
    AdjustableBedButtonEntityDescription(
        key="preset_memory_4",
        translation_key="preset_memory_4",
        icon="mdi:numeric-4-box",
        press_fn=lambda ctrl: ctrl.preset_memory(4),
        cancel_movement=True,
    ),
    AdjustableBedButtonEntityDescription(
        key="preset_flat",
        translation_key="preset_flat",
        icon="mdi:bed",
        press_fn=lambda ctrl: ctrl.preset_flat(),
        cancel_movement=True,
    ),
    AdjustableBedButtonEntityDescription(
        key="preset_zero_g",
        translation_key="preset_zero_g",
        icon="mdi:rocket-launch",
        press_fn=lambda ctrl: ctrl.preset_zero_g(),
        cancel_movement=True,
        supported_bed_types=(
            BED_TYPE_KEESON,
            BED_TYPE_LEGGETT_PLATT,
            BED_TYPE_MOTOSLEEP,
            BED_TYPE_REVERIE,
            BED_TYPE_RICHMAT,
            BED_TYPE_SOLACE,
        ),
    ),
    AdjustableBedButtonEntityDescription(
        key="preset_anti_snore",
        translation_key="preset_anti_snore",
        icon="mdi:sleep-off",
        press_fn=lambda ctrl: ctrl.preset_anti_snore(),
        cancel_movement=True,
        supported_bed_types=(
            BED_TYPE_LEGGETT_PLATT,
            BED_TYPE_MOTOSLEEP,
            BED_TYPE_REVERIE,
            BED_TYPE_RICHMAT,
            BED_TYPE_SOLACE,
        ),
    ),
    AdjustableBedButtonEntityDescription(
        key="preset_tv",
        translation_key="preset_tv",
        icon="mdi:television",
        press_fn=lambda ctrl: ctrl.preset_tv(),
        cancel_movement=True,
        supported_bed_types=(
            BED_TYPE_MOTOSLEEP,
            BED_TYPE_RICHMAT,
            BED_TYPE_SOLACE,
        ),
    ),
    AdjustableBedButtonEntityDescription(
        key="preset_lounge",
        translation_key="preset_lounge",
        icon="mdi:seat-recline-normal",
        press_fn=lambda ctrl: ctrl.preset_lounge(),
        cancel_movement=True,
        supported_bed_types=(
            "mattressfirm",  # Mattress Firm 900 has separate Lounge preset
        ),
    ),
    AdjustableBedButtonEntityDescription(
        key="preset_incline",
        translation_key="preset_incline",
        icon="mdi:angle-acute",
        press_fn=lambda ctrl: ctrl.preset_incline(),
        cancel_movement=True,
        supported_bed_types=(
            "mattressfirm",  # Mattress Firm 900 specific
        ),
    ),
    # Program buttons (config category)
    AdjustableBedButtonEntityDescription(
        key="program_memory_1",
        translation_key="program_memory_1",
        icon="mdi:content-save",
        entity_category=EntityCategory.CONFIG,
        press_fn=lambda ctrl: ctrl.program_memory(1),
    ),
    AdjustableBedButtonEntityDescription(
        key="program_memory_2",
        translation_key="program_memory_2",
        icon="mdi:content-save",
        entity_category=EntityCategory.CONFIG,
        press_fn=lambda ctrl: ctrl.program_memory(2),
    ),
    AdjustableBedButtonEntityDescription(
        key="program_memory_3",
        translation_key="program_memory_3",
        icon="mdi:content-save",
        entity_category=EntityCategory.CONFIG,
        press_fn=lambda ctrl: ctrl.program_memory(3),
    ),
    AdjustableBedButtonEntityDescription(
        key="program_memory_4",
        translation_key="program_memory_4",
        icon="mdi:content-save",
        entity_category=EntityCategory.CONFIG,
        press_fn=lambda ctrl: ctrl.program_memory(4),
    ),
    # Stop button
    AdjustableBedButtonEntityDescription(
        key="stop",
        translation_key="stop",
        icon="mdi:stop",
        press_fn=lambda ctrl: ctrl.stop_all(),
    ),
    # Connection control buttons (diagnostic)
    AdjustableBedButtonEntityDescription(
        key="disconnect",
        name=None,
        translation_key="disconnect",
        icon="mdi:bluetooth-off",
        entity_category=EntityCategory.DIAGNOSTIC,
        is_coordinator_action=True,
    ),
    AdjustableBedButtonEntityDescription(
        key="connect",
        name=None,
        translation_key="connect",
        icon="mdi:bluetooth-connect",
        entity_category=EntityCategory.DIAGNOSTIC,
        is_coordinator_action=True,
    ),
    # Massage buttons (only if has_massage)
    AdjustableBedButtonEntityDescription(
        key="massage_all_off",
        translation_key="massage_all_off",
        icon="mdi:vibrate-off",
        requires_massage=True,
        press_fn=lambda ctrl: ctrl.massage_off(),
    ),
    AdjustableBedButtonEntityDescription(
        key="massage_all_toggle",
        translation_key="massage_all_toggle",
        icon="mdi:vibrate",
        requires_massage=True,
        press_fn=lambda ctrl: ctrl.massage_toggle(),
    ),
    AdjustableBedButtonEntityDescription(
        key="massage_all_up",
        translation_key="massage_all_up",
        icon="mdi:arrow-up-bold",
        requires_massage=True,
        press_fn=lambda ctrl: ctrl.massage_intensity_up(),
    ),
    AdjustableBedButtonEntityDescription(
        key="massage_all_down",
        translation_key="massage_all_down",
        icon="mdi:arrow-down-bold",
        requires_massage=True,
        press_fn=lambda ctrl: ctrl.massage_intensity_down(),
    ),
    AdjustableBedButtonEntityDescription(
        key="massage_head_toggle",
        translation_key="massage_head_toggle",
        icon="mdi:head",
        requires_massage=True,
        press_fn=lambda ctrl: ctrl.massage_head_toggle(),
    ),
    AdjustableBedButtonEntityDescription(
        key="massage_head_up",
        translation_key="massage_head_up",
        icon="mdi:arrow-up",
        requires_massage=True,
        press_fn=lambda ctrl: ctrl.massage_head_up(),
    ),
    AdjustableBedButtonEntityDescription(
        key="massage_head_down",
        translation_key="massage_head_down",
        icon="mdi:arrow-down",
        requires_massage=True,
        press_fn=lambda ctrl: ctrl.massage_head_down(),
    ),
    AdjustableBedButtonEntityDescription(
        key="massage_foot_toggle",
        translation_key="massage_foot_toggle",
        icon="mdi:foot-print",
        requires_massage=True,
        press_fn=lambda ctrl: ctrl.massage_foot_toggle(),
    ),
    AdjustableBedButtonEntityDescription(
        key="massage_foot_up",
        translation_key="massage_foot_up",
        icon="mdi:arrow-up",
        requires_massage=True,
        press_fn=lambda ctrl: ctrl.massage_foot_up(),
    ),
    AdjustableBedButtonEntityDescription(
        key="massage_foot_down",
        translation_key="massage_foot_down",
        icon="mdi:arrow-down",
        requires_massage=True,
        press_fn=lambda ctrl: ctrl.massage_foot_down(),
    ),
    AdjustableBedButtonEntityDescription(
        key="massage_mode_step",
        translation_key="massage_mode_step",
        icon="mdi:format-list-numbered",
        requires_massage=True,
        press_fn=lambda ctrl: ctrl.massage_mode_step(),
    ),
    # Light cycle button (Mattress Firm 900 specific)
    AdjustableBedButtonEntityDescription(
        key="light_cycle",
        translation_key="light_cycle",
        icon="mdi:lightbulb-multiple",
        press_fn=lambda ctrl: ctrl.lights_on(),
        supported_bed_types=(
            "mattressfirm",
        ),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Adjustable Bed button entities."""
    coordinator: AdjustableBedCoordinator = hass.data[DOMAIN][entry.entry_id]
    has_massage = entry.data.get(CONF_HAS_MASSAGE, False)
    bed_type = entry.data.get(CONF_BED_TYPE)

    entities = []
    for description in BUTTON_DESCRIPTIONS:
        if description.requires_massage and not has_massage:
            continue
        # Skip buttons that aren't supported by this bed type
        if description.supported_bed_types is not None and bed_type not in description.supported_bed_types:
            continue
        entities.append(AdjustableBedButton(coordinator, description))

    async_add_entities(entities)


class AdjustableBedButton(AdjustableBedEntity, ButtonEntity):
    """Button entity for Adjustable Bed."""

    entity_description: AdjustableBedButtonEntityDescription

    def __init__(
        self,
        coordinator: AdjustableBedCoordinator,
        description: AdjustableBedButtonEntityDescription,
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
                self.entity_description.press_fn,
                cancel_running=self.entity_description.cancel_movement,
            )
            _LOGGER.debug("Button action completed: %s", self.entity_description.key)
        except Exception as err:
            _LOGGER.error(
                "Failed to execute button action %s: %s",
                self.entity_description.key,
                err,
            )
