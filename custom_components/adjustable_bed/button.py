"""Button entities for Adjustable Bed integration."""

from __future__ import annotations

import logging
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    DOMAIN,
    SIDE_BOTH,
)
from .coordinator import AdjustableBedCoordinator
from .cover import COVER_DESCRIPTIONS, AdjustableBedCoverEntityDescription
from .entity import AdjustableBedEntity
from .paired_coordinator import PairedBedCoordinator, PairedSideProxy

if TYPE_CHECKING:
    from .beds.base import BedController

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class AdjustableBedButtonEntityDescription(ButtonEntityDescription):
    """Describes a Adjustable Bed button entity."""

    press_fn: Callable[[BedController], Coroutine[Any, Any, None]] | None = None
    requires_massage: bool = False
    entity_category: EntityCategory | None = None
    is_coordinator_action: bool = (
        False  # If True, this is a coordinator-level action (connect/disconnect)
    )
    cancel_movement: bool = False  # If True, cancels any running motor command
    # Capability property name to check on controller (e.g., "supports_preset_zero_g")
    required_capability: str | None = None
    # Memory slot number for memory preset/program buttons (1-6). Used to check memory_slot_count.
    memory_slot: int | None = None
    # Whether this is a memory programming button (requires supports_memory_programming)
    is_program_button: bool = False


BUTTON_DESCRIPTIONS: tuple[AdjustableBedButtonEntityDescription, ...] = (
    # Preset buttons
    AdjustableBedButtonEntityDescription(
        key="preset_memory_1",
        translation_key="preset_memory_1",
        icon="mdi:numeric-1-box",
        press_fn=lambda ctrl: ctrl.preset_memory(1),
        cancel_movement=True,
        required_capability="supports_memory_presets",
        memory_slot=1,
    ),
    AdjustableBedButtonEntityDescription(
        key="preset_memory_2",
        translation_key="preset_memory_2",
        icon="mdi:numeric-2-box",
        press_fn=lambda ctrl: ctrl.preset_memory(2),
        cancel_movement=True,
        required_capability="supports_memory_presets",
        memory_slot=2,
    ),
    AdjustableBedButtonEntityDescription(
        key="preset_memory_3",
        translation_key="preset_memory_3",
        icon="mdi:numeric-3-box",
        press_fn=lambda ctrl: ctrl.preset_memory(3),
        cancel_movement=True,
        required_capability="supports_memory_presets",
        memory_slot=3,
    ),
    AdjustableBedButtonEntityDescription(
        key="preset_memory_4",
        translation_key="preset_memory_4",
        icon="mdi:numeric-4-box",
        press_fn=lambda ctrl: ctrl.preset_memory(4),
        cancel_movement=True,
        required_capability="supports_memory_presets",
        memory_slot=4,
    ),
    AdjustableBedButtonEntityDescription(
        key="preset_memory_5",
        translation_key="preset_memory_5",
        icon="mdi:numeric-5-box",
        press_fn=lambda ctrl: ctrl.preset_memory(5),
        cancel_movement=True,
        required_capability="supports_memory_presets",
        memory_slot=5,
    ),
    AdjustableBedButtonEntityDescription(
        key="preset_memory_6",
        translation_key="preset_memory_6",
        icon="mdi:numeric-6-box",
        press_fn=lambda ctrl: ctrl.preset_memory(6),
        cancel_movement=True,
        required_capability="supports_memory_presets",
        memory_slot=6,
    ),
    AdjustableBedButtonEntityDescription(
        key="preset_flat",
        translation_key="preset_flat",
        icon="mdi:bed",
        press_fn=lambda ctrl: ctrl.preset_flat(),
        cancel_movement=True,
        required_capability="supports_preset_flat",
    ),
    AdjustableBedButtonEntityDescription(
        key="preset_zero_g",
        translation_key="preset_zero_g",
        icon="mdi:rocket-launch",
        press_fn=lambda ctrl: ctrl.preset_zero_g(),
        cancel_movement=True,
        required_capability="supports_preset_zero_g",
    ),
    AdjustableBedButtonEntityDescription(
        key="preset_anti_snore",
        translation_key="preset_anti_snore",
        icon="mdi:sleep-off",
        press_fn=lambda ctrl: ctrl.preset_anti_snore(),
        cancel_movement=True,
        required_capability="supports_preset_anti_snore",
    ),
    AdjustableBedButtonEntityDescription(
        key="preset_tv",
        translation_key="preset_tv",
        icon="mdi:television",
        press_fn=lambda ctrl: ctrl.preset_tv(),
        cancel_movement=True,
        required_capability="supports_preset_tv",
    ),
    AdjustableBedButtonEntityDescription(
        key="preset_lounge",
        translation_key="preset_lounge",
        icon="mdi:seat-recline-normal",
        press_fn=lambda ctrl: cast(Any, ctrl).preset_lounge(),
        cancel_movement=True,
        required_capability="supports_preset_lounge",
    ),
    AdjustableBedButtonEntityDescription(
        key="preset_incline",
        translation_key="preset_incline",
        icon="mdi:angle-acute",
        press_fn=lambda ctrl: cast(Any, ctrl).preset_incline(),
        cancel_movement=True,
        required_capability="supports_preset_incline",
    ),
    AdjustableBedButtonEntityDescription(
        key="preset_both_up",
        translation_key="preset_both_up",
        icon="mdi:arrow-up-bold",
        press_fn=lambda ctrl: ctrl.preset_both_up(),
        cancel_movement=True,
        required_capability="supports_preset_both_up",
    ),
    AdjustableBedButtonEntityDescription(
        key="preset_yoga",
        translation_key="preset_yoga",
        icon="mdi:yoga",
        press_fn=lambda ctrl: ctrl.preset_yoga(),
        cancel_movement=True,
        required_capability="supports_preset_yoga",
    ),
    # Program buttons (config category)
    AdjustableBedButtonEntityDescription(
        key="program_memory_1",
        translation_key="program_memory_1",
        icon="mdi:content-save",
        entity_category=EntityCategory.CONFIG,
        press_fn=lambda ctrl: ctrl.program_memory(1),
        required_capability="supports_memory_presets",
        memory_slot=1,
        is_program_button=True,
    ),
    AdjustableBedButtonEntityDescription(
        key="program_memory_2",
        translation_key="program_memory_2",
        icon="mdi:content-save",
        entity_category=EntityCategory.CONFIG,
        press_fn=lambda ctrl: ctrl.program_memory(2),
        required_capability="supports_memory_presets",
        memory_slot=2,
        is_program_button=True,
    ),
    AdjustableBedButtonEntityDescription(
        key="program_memory_3",
        translation_key="program_memory_3",
        icon="mdi:content-save",
        entity_category=EntityCategory.CONFIG,
        press_fn=lambda ctrl: ctrl.program_memory(3),
        required_capability="supports_memory_presets",
        memory_slot=3,
        is_program_button=True,
    ),
    AdjustableBedButtonEntityDescription(
        key="program_memory_4",
        translation_key="program_memory_4",
        icon="mdi:content-save",
        entity_category=EntityCategory.CONFIG,
        press_fn=lambda ctrl: ctrl.program_memory(4),
        required_capability="supports_memory_presets",
        memory_slot=4,
        is_program_button=True,
    ),
    AdjustableBedButtonEntityDescription(
        key="program_memory_5",
        translation_key="program_memory_5",
        icon="mdi:content-save",
        entity_category=EntityCategory.CONFIG,
        press_fn=lambda ctrl: ctrl.program_memory(5),
        required_capability="supports_memory_presets",
        memory_slot=5,
        is_program_button=True,
    ),
    AdjustableBedButtonEntityDescription(
        key="program_memory_6",
        translation_key="program_memory_6",
        icon="mdi:content-save",
        entity_category=EntityCategory.CONFIG,
        press_fn=lambda ctrl: ctrl.program_memory(6),
        required_capability="supports_memory_presets",
        memory_slot=6,
        is_program_button=True,
    ),
    # Stop button
    AdjustableBedButtonEntityDescription(
        key="stop",
        translation_key="stop",
        icon="mdi:stop",
        press_fn=lambda ctrl: ctrl.stop_all(),
        required_capability="supports_stop_all",
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
        cancel_movement=True,
        press_fn=lambda ctrl: ctrl.massage_off(),
        required_capability="supports_massage_off_control",
    ),
    AdjustableBedButtonEntityDescription(
        key="massage_all_toggle",
        translation_key="massage_all_toggle",
        icon="mdi:vibrate",
        requires_massage=True,
        cancel_movement=True,
        press_fn=lambda ctrl: ctrl.massage_toggle(),
        required_capability="supports_massage_toggle_control",
    ),
    AdjustableBedButtonEntityDescription(
        key="massage_all_up",
        translation_key="massage_all_up",
        icon="mdi:arrow-up-bold",
        requires_massage=True,
        cancel_movement=True,
        press_fn=lambda ctrl: ctrl.massage_intensity_up(),
        required_capability="supports_massage_intensity_step_control",
    ),
    AdjustableBedButtonEntityDescription(
        key="massage_all_down",
        translation_key="massage_all_down",
        icon="mdi:arrow-down-bold",
        requires_massage=True,
        cancel_movement=True,
        press_fn=lambda ctrl: ctrl.massage_intensity_down(),
        required_capability="supports_massage_intensity_step_control",
    ),
    AdjustableBedButtonEntityDescription(
        key="massage_head_toggle",
        translation_key="massage_head_toggle",
        icon="mdi:head",
        requires_massage=True,
        cancel_movement=True,
        press_fn=lambda ctrl: ctrl.massage_head_toggle(),
        required_capability="supports_head_massage_toggle_control",
    ),
    AdjustableBedButtonEntityDescription(
        key="massage_head_up",
        translation_key="massage_head_up",
        icon="mdi:arrow-up",
        requires_massage=True,
        cancel_movement=True,
        press_fn=lambda ctrl: ctrl.massage_head_up(),
        required_capability="supports_head_massage_intensity_step_control",
    ),
    AdjustableBedButtonEntityDescription(
        key="massage_head_down",
        translation_key="massage_head_down",
        icon="mdi:arrow-down",
        requires_massage=True,
        cancel_movement=True,
        press_fn=lambda ctrl: ctrl.massage_head_down(),
        required_capability="supports_head_massage_intensity_step_control",
    ),
    AdjustableBedButtonEntityDescription(
        key="massage_foot_toggle",
        translation_key="massage_foot_toggle",
        icon="mdi:foot-print",
        requires_massage=True,
        cancel_movement=True,
        press_fn=lambda ctrl: ctrl.massage_foot_toggle(),
        required_capability="supports_foot_massage_toggle_control",
    ),
    AdjustableBedButtonEntityDescription(
        key="massage_foot_up",
        translation_key="massage_foot_up",
        icon="mdi:arrow-up",
        requires_massage=True,
        cancel_movement=True,
        press_fn=lambda ctrl: ctrl.massage_foot_up(),
        required_capability="supports_foot_massage_intensity_step_control",
    ),
    AdjustableBedButtonEntityDescription(
        key="massage_foot_down",
        translation_key="massage_foot_down",
        icon="mdi:arrow-down",
        requires_massage=True,
        cancel_movement=True,
        press_fn=lambda ctrl: ctrl.massage_foot_down(),
        required_capability="supports_foot_massage_intensity_step_control",
    ),
    AdjustableBedButtonEntityDescription(
        key="massage_mode_step",
        translation_key="massage_mode_step",
        icon="mdi:format-list-numbered",
        requires_massage=True,
        cancel_movement=True,
        press_fn=lambda ctrl: ctrl.massage_mode_step(),
        required_capability="supports_massage_mode_step_control",
    ),
    # Circulation massage buttons (only for beds with circulation massage support)
    AdjustableBedButtonEntityDescription(
        key="massage_circulation_full_body",
        translation_key="massage_circulation_full_body",
        icon="mdi:human",
        requires_massage=True,
        cancel_movement=True,
        press_fn=lambda ctrl: ctrl.massage_circulation_full_body(),
        required_capability="supports_circulation_massage",
    ),
    AdjustableBedButtonEntityDescription(
        key="massage_circulation_head",
        translation_key="massage_circulation_head",
        icon="mdi:head",
        requires_massage=True,
        cancel_movement=True,
        press_fn=lambda ctrl: ctrl.massage_circulation_head(),
        required_capability="supports_circulation_massage",
    ),
    AdjustableBedButtonEntityDescription(
        key="massage_circulation_leg",
        translation_key="massage_circulation_leg",
        icon="mdi:foot-print",
        requires_massage=True,
        cancel_movement=True,
        press_fn=lambda ctrl: ctrl.massage_circulation_leg(),
        required_capability="supports_circulation_massage",
    ),
    AdjustableBedButtonEntityDescription(
        key="massage_circulation_hip",
        translation_key="massage_circulation_hip",
        icon="mdi:human-handsdown",
        requires_massage=True,
        cancel_movement=True,
        press_fn=lambda ctrl: ctrl.massage_circulation_hip(),
        required_capability="supports_circulation_massage",
    ),
    # Light buttons
    AdjustableBedButtonEntityDescription(
        key="toggle_light",
        translation_key="toggle_light",
        icon="mdi:lightbulb",
        press_fn=lambda ctrl: ctrl.lights_toggle(),
        required_capability="supports_light_toggle_control",
    ),
    AdjustableBedButtonEntityDescription(
        key="light_cycle",
        translation_key="light_cycle",
        icon="mdi:lightbulb-multiple",
        press_fn=lambda ctrl: ctrl.lights_on(),
        required_capability="supports_light_cycle",
    ),
    # Light/Sound therapy buttons (KSBT04C / Beautyrest Baselogic)
    AdjustableBedButtonEntityDescription(
        key="toggle_sound",
        translation_key="toggle_sound",
        icon="mdi:volume-high",
        press_fn=lambda ctrl: ctrl.sound_toggle(),
        required_capability="supports_sound_toggle",
    ),
    AdjustableBedButtonEntityDescription(
        key="toggle_light_and_sound",
        translation_key="toggle_light_and_sound",
        icon="mdi:lightbulb-group",
        press_fn=lambda ctrl: ctrl.light_and_sound_toggle(),
        required_capability="supports_therapy_modes",
    ),
    AdjustableBedButtonEntityDescription(
        key="therapy_mode_1",
        translation_key="therapy_mode_1",
        icon="mdi:numeric-1-circle",
        press_fn=lambda ctrl: ctrl.therapy_mode_one(),
        required_capability="supports_therapy_modes",
    ),
    AdjustableBedButtonEntityDescription(
        key="therapy_mode_2",
        translation_key="therapy_mode_2",
        icon="mdi:numeric-2-circle",
        press_fn=lambda ctrl: ctrl.therapy_mode_two(),
        required_capability="supports_therapy_modes",
    ),
    AdjustableBedButtonEntityDescription(
        key="therapy_mode_3",
        translation_key="therapy_mode_3",
        icon="mdi:numeric-3-circle",
        press_fn=lambda ctrl: ctrl.therapy_mode_three(),
        required_capability="supports_therapy_modes",
    ),
    # Motor movement buttons (for discrete motor control beds)
    AdjustableBedButtonEntityDescription(
        key="head_up",
        translation_key="head_up",
        icon="mdi:arrow-up",
        press_fn=lambda ctrl: ctrl.move_head_up(),
        cancel_movement=True,
        required_capability="has_discrete_motor_control",
    ),
    AdjustableBedButtonEntityDescription(
        key="head_down",
        translation_key="head_down",
        icon="mdi:arrow-down",
        press_fn=lambda ctrl: ctrl.move_head_down(),
        cancel_movement=True,
        required_capability="has_discrete_motor_control",
    ),
    AdjustableBedButtonEntityDescription(
        key="legs_up",
        translation_key="legs_up",
        icon="mdi:arrow-up",
        press_fn=lambda ctrl: ctrl.move_legs_up(),
        cancel_movement=True,
        required_capability="has_discrete_motor_control",
    ),
    AdjustableBedButtonEntityDescription(
        key="legs_down",
        translation_key="legs_down",
        icon="mdi:arrow-down",
        press_fn=lambda ctrl: ctrl.move_legs_down(),
        cancel_movement=True,
        required_capability="has_discrete_motor_control",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Adjustable Bed button entities."""
    coordinator = hass.data[DOMAIN][entry.entry_id]

    # Paired beds expose per-side buttons (presets, stop, connect) built against
    # each child, plus combined controls on the parent device: a resilient "Stop"
    # that fans STOP to both sides, and "both" movement/preset buttons for actions
    # both sides support (since paired setup omits a combined cover, these buttons
    # are how the whole bed is driven from the parent device/card).
    if isinstance(coordinator, PairedBedCoordinator):
        entities: list[ButtonEntity] = []
        children = list(coordinator.children.values())
        for side, child in coordinator.children.items():
            entities.extend(
                _button_entities_for(
                    hass,
                    cast(
                        "AdjustableBedCoordinator",
                        PairedSideProxy(coordinator, child, side),
                    ),
                )
            )
        entities.append(PairedBedStopButton(coordinator))
        # Combined buttons read both children's live capabilities, so pass the
        # raw children (the button itself dispatches via the parent, side=both).
        entities.extend(_combined_button_entities_for(coordinator, children))
        async_add_entities(entities)
        return

    async_add_entities(_button_entities_for(hass, coordinator))


def _button_entities_for(
    hass: HomeAssistant, coordinator: AdjustableBedCoordinator
) -> list[ButtonEntity]:
    """Build button entities for a single (child or standalone) coordinator."""
    has_massage = coordinator.has_massage
    controller = coordinator.controller

    if controller is not None:
        _async_remove_stale_button_entities(hass, coordinator, controller, has_massage)

    entities: list[ButtonEntity] = []
    for description in BUTTON_DESCRIPTIONS:
        if not _should_add_button(description, controller, has_massage):
            continue
        entities.append(AdjustableBedButton(coordinator, description))

    return entities


def _combined_button_entities_for(
    coordinator: PairedBedCoordinator,
    children: list[AdjustableBedCoordinator],
) -> list[ButtonEntity]:
    """Build the parent device's combined 'both sides' movement/preset buttons.

    Only actions supported by BOTH children are exposed (connect/disconnect/stop
    are coordinator actions handled separately by the combined Stop button).
    """
    if not children:
        return []
    # Build the combined surface only from the sides we can actually read. A pair
    # is the same protocol, so an OFFLINE side at setup falls back to the
    # connected side(s) — controls still register (a half-available pair loads),
    # and press-time fan-out reconnects/fails the offline side. With BOTH online,
    # require both (intersection): the pair flow only rejects a different
    # bed_type, so two same-protocol sides can still differ in motor_count /
    # has_massage / variant, and a capability only one side has must NOT be
    # exposed as a combined control the other can't honour.
    eligible = [child for child in children if child.controller is not None] or children
    entities: list[ButtonEntity] = []
    for description in BUTTON_DESCRIPTIONS:
        if description.is_coordinator_action or description.press_fn is None:
            continue
        if description.key == "stop":
            # The combined stop is the dedicated PairedBedStopButton (same
            # {pair_id}_stop_both unique_id); don't also build a generic one.
            continue
        if not all(
            _should_add_button(description, child.controller, child.has_massage)
            for child in eligible
        ):
            continue
        entities.append(PairedBedCombinedButton(coordinator, description))

    # Cover-based pairs (e.g. Linak) move via covers, not discrete up/down
    # buttons, and paired setup creates no combined cover — so add per-motor
    # "both sides" up/down motion buttons from the cover descriptors.
    entities.extend(_combined_motor_buttons_for(coordinator, eligible))
    return entities


def _combined_motor_buttons_for(
    coordinator: PairedBedCoordinator,
    eligible: list[AdjustableBedCoordinator],
) -> list[ButtonEntity]:
    """Per-motor 'both sides' up/down buttons for a cover-based paired bed — only
    the motors EVERY eligible (connected) side exposes."""
    cover_by_key = {desc.key: desc for desc in COVER_DESCRIPTIONS}
    common: set[str] | None = None
    for child in eligible:
        controller = child.controller
        if (
            controller is None
            or not getattr(controller, "supports_motor_control", False)
            or getattr(controller, "has_discrete_motor_control", False)
        ):
            # Not a cover-based bed (discrete motors get combined buttons above),
            # or no side connected yet to read the motor layout from.
            return []
        keys = {spec.key for spec in controller.motor_control_specs}
        common = keys if common is None else (common & keys)

    entities: list[ButtonEntity] = []
    for key in sorted(common or set()):
        desc = cover_by_key.get(key)
        if desc is None:
            continue
        entities.append(PairedBedCombinedMotorButton(coordinator, desc, "up"))
        entities.append(PairedBedCombinedMotorButton(coordinator, desc, "down"))
    return entities


def _should_add_button(
    description: AdjustableBedButtonEntityDescription,
    controller: BedController | None,
    has_massage: bool,
) -> bool:
    """Return whether the button should be exposed for the current controller."""
    if description.requires_massage and not has_massage:
        return False

    if description.key == "toggle_light" and controller is not None:
        if getattr(controller, "supports_discrete_light_control", False) or getattr(
            controller, "supports_light_color_control", False
        ):
            return False

    if description.required_capability is not None:
        if controller is None:
            return False
        if not getattr(controller, description.required_capability, False):
            return False

    if description.memory_slot is not None and controller is not None:
        slot_count = getattr(controller, "memory_slot_count", 4)
        if description.memory_slot > slot_count:
            return False

    if description.is_program_button and controller is not None:
        if not getattr(controller, "supports_memory_programming", False):
            return False

    return True


def _async_remove_stale_button_entities(
    hass: HomeAssistant,
    coordinator: AdjustableBedCoordinator,
    controller: BedController,
    has_massage: bool,
) -> None:
    """Remove button entities that are no longer supported for this controller."""
    registry = er.async_get(hass)
    for description in BUTTON_DESCRIPTIONS:
        if _should_add_button(description, controller, has_massage):
            continue

        entity_id = registry.async_get_entity_id(
            "button",
            DOMAIN,
            f"{coordinator.address}_{description.key}",
        )
        if entity_id is not None:
            registry.async_remove(entity_id)


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
                    if not await self._coordinator.async_ensure_connected():
                        raise RuntimeError(f"Failed to connect to {self._coordinator.name}")
                    _LOGGER.info("Connected to bed")
            except Exception:
                _LOGGER.exception(
                    "Failed to execute coordinator action %s",
                    self.entity_description.key,
                )
                raise
            return

        # Stop button gets special handling - cancels current command immediately
        if self.entity_description.key == "stop":
            try:
                await self._coordinator.async_stop_command()
            except Exception:
                _LOGGER.exception("Failed to execute stop command")
                raise
            return

        try:
            _LOGGER.debug("Executing button action: %s", self.entity_description.key)
            if self.entity_description.press_fn is None:
                _LOGGER.warning(
                    "No press function defined for button: %s", self.entity_description.key
                )
                return
            await self._coordinator.async_execute_controller_command(
                self.entity_description.press_fn,
                cancel_running=self.entity_description.cancel_movement,
            )
            _LOGGER.debug("Button action completed: %s", self.entity_description.key)
        except Exception:
            _LOGGER.exception(
                "Failed to execute button action %s",
                self.entity_description.key,
            )
            raise


class PairedBedStopButton(ButtonEntity):
    """Combined STOP for a paired bed.

    Lives on the synthetic parent device and stops BOTH sides with the resilient
    stop contract — one side's STOP failure never prevents stopping the other.
    """

    _attr_has_entity_name = True
    _attr_translation_key = "stop_both"

    def __init__(self, coordinator: PairedBedCoordinator) -> None:
        """Initialize the combined stop button."""
        self._coordinator = coordinator
        self._attr_unique_id = f"{coordinator.pair_id}_stop_both"
        self._attr_device_info = coordinator.device_info

    @property
    def available(self) -> bool:
        """Always available (the bed reconnects on demand)."""
        return True

    async def async_press(self) -> None:
        """Stop both sides."""
        _LOGGER.info("Combined stop pressed for paired bed %s", self._coordinator.name)
        await self._coordinator.async_stop_command(side=SIDE_BOTH)


class PairedBedCombinedButton(ButtonEntity):
    """A 'both sides' movement/preset button on the paired parent device.

    Reuses the per-side button's translation_key (the parent device name keeps it
    distinct from the per-side entities) and fans the action out to both sides.
    """

    _attr_has_entity_name = True
    entity_description: AdjustableBedButtonEntityDescription

    def __init__(
        self,
        coordinator: PairedBedCoordinator,
        description: AdjustableBedButtonEntityDescription,
    ) -> None:
        """Initialize the combined button."""
        self._coordinator = coordinator
        self.entity_description = description
        self._attr_translation_key = description.translation_key
        self._attr_unique_id = f"{coordinator.pair_id}_{description.key}_both"
        self._attr_device_info = coordinator.device_info

    @property
    def available(self) -> bool:
        """Always available (the bed reconnects on demand)."""
        return True

    async def async_press(self) -> None:
        """Run the action on both sides."""
        description = self.entity_description
        if description.press_fn is None:
            return
        _LOGGER.info(
            "Combined button %s pressed for paired bed %s",
            description.key,
            self._coordinator.name,
        )
        await self._coordinator.async_execute_controller_command(
            description.press_fn,
            side=SIDE_BOTH,
            cancel_running=description.cancel_movement,
        )


class PairedBedCombinedMotorButton(ButtonEntity):
    """A 'move both sides' up/down motion button on the paired parent device.

    Cover-based pairs (Linak etc.) have no discrete motor buttons and no combined
    cover, so these drive a motor on BOTH sides from the parent device/card.
    """

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: PairedBedCoordinator,
        cover_description: AdjustableBedCoverEntityDescription,
        direction: str,
    ) -> None:
        """Initialize the combined motor button (``direction`` is up/down)."""
        self._coordinator = coordinator
        self._direction = direction
        self._move_fn = (
            cover_description.open_fn
            if direction == "up"
            else cover_description.close_fn
        )
        self._attr_translation_key = f"{cover_description.key}_{direction}"
        self._attr_unique_id = (
            f"{coordinator.pair_id}_{cover_description.key}_{direction}_both"
        )
        self._attr_device_info = coordinator.device_info

    @property
    def available(self) -> bool:
        """Always available (the bed reconnects on demand)."""
        return True

    async def async_press(self) -> None:
        """Move this motor on both sides."""
        await self._coordinator.async_execute_controller_command(
            self._move_fn, side=SIDE_BOTH, cancel_running=True
        )
