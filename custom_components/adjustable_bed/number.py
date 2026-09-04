"""Number entities for Adjustable Bed integration."""

from __future__ import annotations

import logging
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any, cast

from homeassistant.components.number import (
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .beds.base import PositionNumberSpec
from .const import (
    BED_TYPE_LINAK,
    BED_TYPE_SLEEPSTAR,
    BED_TYPE_SOLACE,
    BEDS_WITHOUT_ANGLE_FEEDBACK,
    CONF_BED_TYPE,
    CONF_HAS_MASSAGE,
    CONF_PROTOCOL_VARIANT,
    DOMAIN,
    SIDE_BOTH,
    bed_type_has_position_feedback,
)
from .coordinator import AdjustableBedCoordinator
from .entity import AdjustableBedEntity
from .paired_coordinator import (
    PairedBedCoordinator,
    PairedSideProxy,
    SingleAddressPairedCoordinator,
)

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


@dataclass(frozen=True, kw_only=True)
class AdjustableBedSideStateNumberEntityDescription(NumberEntityDescription):
    """Describes a side-specific number entity backed by controller state."""

    state_key: str
    setter_name: str
    side: str


MASSAGE_NUMBER_DESCRIPTIONS: tuple[AdjustableBedMassageNumberEntityDescription, ...] = (
    AdjustableBedMassageNumberEntityDescription(
        key="massage_intensity",
        translation_key="massage_intensity",
        icon="mdi:vibrate",
        native_min_value=0,
        native_max_value=10,
        native_step=1,
        mode=NumberMode.SLIDER,
        massage_zone="all",
    ),
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


LIGHT_LEVEL_DESCRIPTION = NumberEntityDescription(
    key="light_level",
    translation_key="light_level",
    icon="mdi:brightness-6",
    native_min_value=0,
    native_max_value=10,
    native_step=1,
    mode=NumberMode.SLIDER,
)

SLEEP_NUMBER_SETTING_DESCRIPTION = NumberEntityDescription(
    key="sleep_number_setting",
    translation_key="sleep_number_setting",
    icon="mdi:bed-queen",
    native_min_value=5,
    native_max_value=100,
    native_step=5,
    mode=NumberMode.SLIDER,
)

SLEEP_NUMBER_SETTING_LEFT_DESCRIPTION = AdjustableBedSideStateNumberEntityDescription(
    key="sleep_number_setting_left",
    translation_key="sleep_number_setting_left",
    icon="mdi:bed-queen-outline",
    native_min_value=5,
    native_max_value=100,
    native_step=5,
    mode=NumberMode.SLIDER,
    state_key="sleep_number_left",
    setter_name="set_sleep_number_setting_for_side",
    side="left",
)

SLEEP_NUMBER_SETTING_RIGHT_DESCRIPTION = AdjustableBedSideStateNumberEntityDescription(
    key="sleep_number_setting_right",
    translation_key="sleep_number_setting_right",
    icon="mdi:bed-queen-outline",
    native_min_value=5,
    native_max_value=100,
    native_step=5,
    mode=NumberMode.SLIDER,
    state_key="sleep_number_right",
    setter_name="set_sleep_number_setting_for_side",
    side="right",
)


def _build_position_description(
    spec: PositionNumberSpec,
) -> AdjustableBedNumberEntityDescription:
    """Render a controller-declared position slider as an entity description.

    Everything bed-specific (axis set, scale, unit, calibration) is already
    resolved in the spec, so this only adapts it to Home Assistant's shape.
    """
    return AdjustableBedNumberEntityDescription(
        key=spec.key,
        translation_key=spec.translation_key,
        icon=spec.icon,
        native_min_value=0,
        native_max_value=spec.native_max_value,
        native_step=1,
        native_unit_of_measurement=spec.native_unit_of_measurement,
        mode=NumberMode.SLIDER,
        position_key=spec.position_key,
        move_up_fn=spec.open_fn,
        move_down_fn=spec.close_fn,
        move_stop_fn=spec.stop_fn,
        max_angle=spec.native_max_value,
        min_motors=1,
    )


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Adjustable Bed number entities."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    if isinstance(coordinator, PairedBedCoordinator):
        paired_entities: list[NumberEntity] = []
        children = list(coordinator.children.values())
        for side, child in coordinator.children.items():
            paired_entities.extend(
                _number_entities_for(
                    hass,
                    cast(
                        "AdjustableBedCoordinator",
                        PairedSideProxy(coordinator, child, side),
                    ),
                )
            )
        # Combined sliders on the parent device drive both sides to one target.
        # They read the raw children's positions and seek via the parent (side=both).
        paired_entities.extend(_combined_position_entities_for(coordinator, children))
        _async_remove_stale_combined_number_entities(hass, coordinator, children, paired_entities)
        if paired_entities:
            async_add_entities(paired_entities)
        return
    async_add_entities(_number_entities_for(hass, coordinator))


def _number_entities_for(
    hass: HomeAssistant, coordinator: AdjustableBedCoordinator
) -> list[NumberEntity]:
    """Build number entities for a single (child or standalone) coordinator."""
    entry = coordinator.entry  # ChildEntryView for a paired child; real entry otherwise
    bed_type = entry.data.get(CONF_BED_TYPE)
    has_massage = entry.data.get(CONF_HAS_MASSAGE, False)
    # capability_controller: an offline paired side still gets its number entities
    # built from a client-free controller minted from config (see coordinator).
    controller = coordinator.capability_controller
    if controller is not None and controller.auto_enable_massage:
        has_massage = True

    entities: list[NumberEntity] = []

    # Beds with no angle/position feedback may have registered position sliders
    # under an earlier version or a previously selected profile. Remove any so
    # existing installs do not keep dead orphaned numbers (#322, #344).
    if bed_type in BEDS_WITHOUT_ANGLE_FEEDBACK:
        _async_remove_stale_position_entities(hass, coordinator)
    elif bed_type == BED_TYPE_LINAK and controller is not None:
        supported_keys = {spec.key for spec in controller.position_number_specs}
        _async_remove_stale_position_entities(
            hass,
            coordinator,
            stale_keys=frozenset(
                description.key
                for description in NUMBER_DESCRIPTIONS
                if description.key not in supported_keys
            ),
        )
    elif bed_type == BED_TYPE_SLEEPSTAR:
        _async_remove_stale_position_entities(
            hass,
            coordinator,
            stale_keys=frozenset({"back_position", "legs_position"}),
        )

    # Set up position number entities (only for beds with position feedback)
    if not coordinator.disable_angle_sensing:
        specs = _position_number_specs(coordinator)
        if specs:
            entities.extend(
                AdjustableBedPositionNumber(coordinator, _build_position_description(spec))
                for spec in specs
            )
        elif controller is None:
            # The layout comes from the controller, so a bed that is disconnected
            # at setup gets no sliders until the entry reloads. Say so plainly
            # rather than blaming the bed type.
            _LOGGER.warning(
                "No controller available for %s, skipping position number entities; "
                "reload the entry once the bed reconnects",
                coordinator.name,
            )
        else:
            _LOGGER.debug(
                "Bed type %s (variant=%s) does not support position feedback, skipping position number entities",
                bed_type,
                entry.data.get(CONF_PROTOCOL_VARIANT),
            )

    # Set up massage intensity number entities (only for beds with massage and direct intensity control)
    if has_massage and controller is not None:
        if controller.supports_massage_intensity_control:
            supported_zones = controller.massage_intensity_zones
            max_intensity = controller.massage_intensity_max
            _LOGGER.debug(
                "Setting up massage intensity numbers for %s (zones: %s, max: %d)",
                coordinator.name,
                supported_zones,
                max_intensity,
            )

            for massage_desc in MASSAGE_NUMBER_DESCRIPTIONS:
                if massage_desc.massage_zone in supported_zones:
                    # Create description with correct max value for this controller
                    massage_adjusted = AdjustableBedMassageNumberEntityDescription(
                        key=massage_desc.key,
                        translation_key=massage_desc.translation_key,
                        icon=massage_desc.icon,
                        native_min_value=0,
                        native_max_value=max_intensity,
                        native_step=1,
                        mode=massage_desc.mode,
                        massage_zone=massage_desc.massage_zone,
                    )
                    entities.append(AdjustableBedMassageNumber(coordinator, massage_adjusted))

    # Set up light level number entity (only for beds that support it)
    if controller is not None and controller.supports_light_level_control:
        max_level = controller.light_level_max
        _LOGGER.debug(
            "Setting up light level number for %s (max: %d)",
            coordinator.name,
            max_level,
        )
        # Create description with correct max value for this controller
        light_adjusted = NumberEntityDescription(
            key=LIGHT_LEVEL_DESCRIPTION.key,
            translation_key=LIGHT_LEVEL_DESCRIPTION.translation_key,
            icon=LIGHT_LEVEL_DESCRIPTION.icon,
            native_min_value=0,
            native_max_value=max_level,
            native_step=1,
            mode=NumberMode.SLIDER,
        )
        entities.append(AdjustableBedLightLevelNumber(coordinator, light_adjusted))
    elif bed_type == BED_TYPE_SOLACE and controller is not None:
        _async_remove_stale_light_level_entity(hass, coordinator)

    sleep_number_sides = controller.sleep_number_setting_sides if controller else ()
    if controller is not None and sleep_number_sides:
        _LOGGER.debug(
            "Setting up side-specific Sleep Number controls for %s (sides: %s)",
            coordinator.name,
            sleep_number_sides,
        )
        _async_remove_stale_sleep_number_entity(hass, coordinator)
        for side_description in (
            SLEEP_NUMBER_SETTING_LEFT_DESCRIPTION,
            SLEEP_NUMBER_SETTING_RIGHT_DESCRIPTION,
        ):
            if side_description.side not in sleep_number_sides:
                continue
            entities.append(
                AdjustableBedSideStateNumber(
                    coordinator,
                    AdjustableBedSideStateNumberEntityDescription(
                        key=side_description.key,
                        translation_key=side_description.translation_key,
                        icon=side_description.icon,
                        native_min_value=controller.sleep_number_setting_min,
                        native_max_value=controller.sleep_number_setting_max,
                        native_step=controller.sleep_number_setting_step,
                        mode=side_description.mode,
                        state_key=side_description.state_key,
                        setter_name=side_description.setter_name,
                        side=side_description.side,
                    ),
                )
            )
    elif controller is not None and controller.supports_sleep_number_setting:
        _LOGGER.debug("Setting up Sleep Number setting control for %s", coordinator.name)
        entities.append(
            AdjustableBedSleepNumberSettingNumber(
                coordinator,
                NumberEntityDescription(
                    key=SLEEP_NUMBER_SETTING_DESCRIPTION.key,
                    translation_key=SLEEP_NUMBER_SETTING_DESCRIPTION.translation_key,
                    icon=SLEEP_NUMBER_SETTING_DESCRIPTION.icon,
                    native_min_value=controller.sleep_number_setting_min,
                    native_max_value=controller.sleep_number_setting_max,
                    native_step=controller.sleep_number_setting_step,
                    mode=SLEEP_NUMBER_SETTING_DESCRIPTION.mode,
                ),
            )
        )

    return entities


def _position_number_specs(
    coordinator: AdjustableBedCoordinator,
) -> tuple[PositionNumberSpec, ...]:
    """Return the position sliders one bed (or paired side) can seek, else ().

    The controller owns the layout: which axes exist, whether they are scaled in
    degrees or percent, and which position_data key each one reads. See
    BedController.position_number_specs.
    """
    controller = coordinator.capability_controller
    if coordinator.disable_angle_sensing or controller is None:
        return ()
    entry = coordinator.entry
    has_position_feedback = bed_type_has_position_feedback(
        entry.data.get(CONF_BED_TYPE), entry.data.get(CONF_PROTOCOL_VARIANT)
    )
    if not (has_position_feedback or controller.supports_direct_position_control):
        return ()
    return tuple(controller.position_number_specs)


def _combined_position_entities_for(
    coordinator: PairedBedCoordinator,
    children: list[AdjustableBedCoordinator],
) -> list[NumberEntity]:
    """Build the parent device's 'both sides' position sliders.

    Only axes EVERY side can seek are exposed. A side without a capability
    source is unknown, not absent, so no combined slider is built until both
    sides are known (same rule as the combined buttons).
    """
    if not children or any(child.capability_controller is None for child in children):
        return []
    specs_per_side = [_position_number_specs(child) for child in children]
    specs_by_side = [{spec.key: spec for spec in specs} for specs in specs_per_side]
    common = set.intersection(*(set(specs) for specs in specs_by_side))
    entities: list[NumberEntity] = []
    for spec in specs_per_side[0]:
        if spec.key not in common:
            continue
        matching_specs = [side_specs[spec.key] for side_specs in specs_by_side]
        if any(
            candidate.position_key != spec.position_key
            or candidate.native_unit_of_measurement != spec.native_unit_of_measurement
            for candidate in matching_specs[1:]
        ):
            continue
        reconciled = replace(
            spec,
            native_max_value=min(candidate.native_max_value for candidate in matching_specs),
        )
        entities.append(
            PairedBedCombinedPositionNumber(
                coordinator, _build_position_description(reconciled)
            )
        )
    return entities


def _async_remove_stale_combined_number_entities(
    hass: HomeAssistant,
    coordinator: PairedBedCoordinator,
    children: list[AdjustableBedCoordinator],
    entities: list[NumberEntity],
) -> None:
    """Remove pair-level sliders no longer supported by both known sides."""
    if any(child.capability_controller is None for child in children):
        return
    desired_unique_ids = {
        unique_id
        for entity in entities
        if (unique_id := entity.unique_id) is not None and unique_id.endswith("_both")
    }
    candidate_keys = {description.key for description in NUMBER_DESCRIPTIONS}
    candidate_keys.update(
        spec.key for child in children for spec in _position_number_specs(child)
    )
    candidate_unique_ids = {
        coordinator.entity_unique_id(f"{key}_both") for key in candidate_keys
    }
    registry = er.async_get(hass)
    for row in list(er.async_entries_for_config_entry(registry, coordinator.entry.entry_id)):
        translation_key = (row.translation_key or "").removesuffix("_both")
        if (
            row.domain == "number"
            and (
                row.unique_id in candidate_unique_ids
                or (
                    row.unique_id.endswith("_both")
                    and translation_key.endswith("_position")
                )
            )
            and row.unique_id not in desired_unique_ids
        ):
            registry.async_remove(row.entity_id)


def _async_remove_stale_sleep_number_entity(
    hass: HomeAssistant,
    coordinator: AdjustableBedCoordinator,
) -> None:
    """Remove the legacy single-side Sleep Number entity when side controls exist."""
    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id(
        "number",
        DOMAIN,
        coordinator.entity_unique_id(SLEEP_NUMBER_SETTING_DESCRIPTION.key),
    )
    if entity_id is not None:
        registry.async_remove(entity_id)


def _async_remove_stale_light_level_entity(
    hass: HomeAssistant,
    coordinator: AdjustableBedCoordinator,
) -> None:
    """Remove the broad legacy Solace brightness number from narrowed profiles."""
    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id(
        "number",
        DOMAIN,
        coordinator.entity_unique_id(LIGHT_LEVEL_DESCRIPTION.key),
    )
    if entity_id is not None:
        registry.async_remove(entity_id)


def _async_remove_stale_position_entities(
    hass: HomeAssistant,
    coordinator: AdjustableBedCoordinator,
    *,
    stale_keys: frozenset[str] | None = None,
) -> None:
    """Remove position number entities the integration no longer creates.

    Beds in BEDS_WITHOUT_ANGLE_FEEDBACK have no position feedback, but an earlier
    version or profile may have registered *_back_position/*_legs_position sliders
    that now linger as dead orphaned numbers (#322, #344).
    """
    registry = er.async_get(hass)
    for description in NUMBER_DESCRIPTIONS:
        if stale_keys is not None and description.key not in stale_keys:
            continue
        entity_id = registry.async_get_entity_id(
            "number", DOMAIN, coordinator.entity_unique_id(description.key)
        )
        if entity_id is not None:
            registry.async_remove(entity_id)


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


class PairedBedCombinedPositionNumber(NumberEntity):
    """A 'both sides' position slider on the paired parent device.

    Reports the mean of the sides' positions, so the slider sits between them
    while they differ. Setting it seeks both sides to the same target through
    the parent (side=both), which takes the pair command lock.
    """

    _attr_has_entity_name = True
    entity_description: AdjustableBedNumberEntityDescription

    def __init__(
        self,
        coordinator: PairedBedCoordinator,
        description: AdjustableBedNumberEntityDescription,
    ) -> None:
        """Initialize the combined position slider."""
        self._coordinator = coordinator
        self.entity_description = description
        self._attr_unique_id = coordinator.entity_unique_id(f"{description.key}_both")
        self._attr_device_info = coordinator.device_info
        translation_key = description.translation_key or description.key
        if isinstance(coordinator, SingleAddressPairedCoordinator):
            self._attr_translation_key = f"{translation_key}_both"
            self._attr_extra_state_attributes = {"bed_side": SIDE_BOTH}
        else:
            self._attr_translation_key = translation_key
        self._unregister_callbacks: list[Callable[[], None]] = []

    @property
    def available(self) -> bool:
        """Always available (the bed reconnects on demand)."""
        return True

    async def async_added_to_hass(self) -> None:
        """Follow position updates from every side."""
        await super().async_added_to_hass()
        self._unregister_callbacks = [
            child.register_position_callback(self._handle_position_update)
            for child in self._coordinator.children.values()
        ]

    async def async_will_remove_from_hass(self) -> None:
        """Stop following position updates."""
        for unregister in self._unregister_callbacks:
            unregister()
        self._unregister_callbacks = []
        await super().async_will_remove_from_hass()

    @callback
    def _handle_position_update(self, _position_data: dict[str, float]) -> None:
        """Handle a position update from either side."""
        self.async_write_ha_state()

    @property
    def native_value(self) -> float | None:
        """Return the mean position of the sides that report one."""
        max_angle = self.entity_description.max_angle
        position_key = self.entity_description.position_key
        positions = [
            min(max_angle, max(0.0, float(position)))
            for child in self._coordinator.children.values()
            if (position := child.position_data.get(position_key)) is not None
        ]
        if not positions:
            return None
        return sum(positions) / len(positions)

    async def async_set_native_value(self, value: float) -> None:
        """Seek both sides to the target position."""
        description = self.entity_description
        _LOGGER.info(
            "Combined position set requested: %s to %.1f%s (paired bed: %s)",
            description.key,
            value,
            description.native_unit_of_measurement or "°",
            self._coordinator.name,
        )
        await self._coordinator.async_seek_position(
            position_key=description.position_key,
            target_angle=value,
            move_up_fn=description.move_up_fn,
            move_down_fn=description.move_down_fn,
            move_stop_fn=description.move_stop_fn,
            side=SIDE_BOTH,
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
        self._set_sided_translation_key(description.translation_key, description.key)
        self._attr_unique_id = coordinator.entity_unique_id(description.key)

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
            "all": "intensity",
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


class AdjustableBedLightLevelNumber(AdjustableBedEntity, NumberEntity):
    """Number entity for Adjustable Bed light level control."""

    entity_description: NumberEntityDescription

    def __init__(
        self,
        coordinator: AdjustableBedCoordinator,
        description: NumberEntityDescription,
    ) -> None:
        """Initialize the light level number entity."""
        super().__init__(coordinator)
        self.entity_description = description
        self._set_sided_translation_key(description.translation_key, description.key)
        self._attr_unique_id = coordinator.entity_unique_id(description.key)
        self._unregister_callback: Callable[[], None] | None = None

    async def async_added_to_hass(self) -> None:
        """Run when entity is added to hass."""
        await super().async_added_to_hass()
        self._unregister_callback = self._coordinator.register_controller_state_callback(
            self._handle_controller_state_update
        )

    async def async_will_remove_from_hass(self) -> None:
        """Run when entity is removed from hass."""
        if self._unregister_callback:
            self._unregister_callback()
        await super().async_will_remove_from_hass()

    @callback
    def _handle_controller_state_update(self, state: dict[str, Any]) -> None:
        """Write state when the controller publishes light updates."""
        if "light_level" in state:
            self.async_write_ha_state()

    @property
    def native_value(self) -> float | None:
        """Return the current light level when the controller tracks it."""
        level = self._coordinator.controller_state.get("light_level")
        if level is None:
            return None
        return float(level)

    async def async_set_native_value(self, value: float) -> None:
        """Set the light level."""
        level = round(value)

        _LOGGER.info(
            "Light level set requested: level %d (device: %s)",
            level,
            self._coordinator.name,
        )

        async def _set_level(ctrl: BedController) -> None:
            await ctrl.set_light_level(level)

        await self._coordinator.async_execute_controller_command(_set_level)


class AdjustableBedSleepNumberSettingNumber(AdjustableBedEntity, NumberEntity):
    """Number entity for Sleep Number firmness setting control."""

    entity_description: NumberEntityDescription

    def __init__(
        self,
        coordinator: AdjustableBedCoordinator,
        description: NumberEntityDescription,
    ) -> None:
        """Initialize the Sleep Number setting entity."""
        super().__init__(coordinator)
        self.entity_description = description
        self._set_sided_translation_key(description.translation_key, description.key)
        self._attr_unique_id = coordinator.entity_unique_id(description.key)
        self._unregister_callback: Callable[[], None] | None = None

    async def async_added_to_hass(self) -> None:
        """Run when entity is added to hass."""
        await super().async_added_to_hass()
        self._unregister_callback = self._coordinator.register_controller_state_callback(
            self._handle_controller_state_update
        )

    async def async_will_remove_from_hass(self) -> None:
        """Run when entity is removed from hass."""
        if self._unregister_callback:
            self._unregister_callback()
        await super().async_will_remove_from_hass()

    @callback
    def _handle_controller_state_update(self, state: dict[str, Any]) -> None:
        """Write state when the controller publishes Sleep Number changes."""
        if "sleep_number" in state:
            self.async_write_ha_state()

    @property
    def native_value(self) -> float | None:
        """Return the current Sleep Number setting."""
        value = self._coordinator.controller_state.get("sleep_number")
        if value is None:
            return None
        return float(value)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return side metadata for the configured Sleep Number setting."""
        attrs: dict[str, Any] = {}
        side = self._coordinator.controller_state.get("sleep_number_side")
        if side is not None:
            attrs["side"] = side
        return attrs

    async def async_set_native_value(self, value: float) -> None:
        """Set the Sleep Number setting."""
        setting = round(value)

        _LOGGER.info(
            "Sleep Number setting requested: %d (device: %s)",
            setting,
            self._coordinator.name,
        )

        async def _set_sleep_number(ctrl: BedController) -> None:
            await cast(Any, ctrl).set_sleep_number_setting(setting)

        await self._coordinator.async_execute_controller_command(_set_sleep_number)


class AdjustableBedSideStateNumber(AdjustableBedEntity, NumberEntity):
    """Number entity backed by a side-specific controller-state value."""

    entity_description: AdjustableBedSideStateNumberEntityDescription

    def __init__(
        self,
        coordinator: AdjustableBedCoordinator,
        description: AdjustableBedSideStateNumberEntityDescription,
    ) -> None:
        """Initialize the side-specific number entity."""
        super().__init__(coordinator)
        self.entity_description = description
        self._set_sided_translation_key(description.translation_key, description.key)
        self._attr_unique_id = coordinator.entity_unique_id(description.key)
        self._unregister_callback: Callable[[], None] | None = None

    async def async_added_to_hass(self) -> None:
        """Register for controller-state updates."""
        await super().async_added_to_hass()
        self._unregister_callback = self._coordinator.register_controller_state_callback(
            self._handle_controller_state_update
        )

    async def async_will_remove_from_hass(self) -> None:
        """Clean up the callback."""
        if self._unregister_callback:
            self._unregister_callback()
        await super().async_will_remove_from_hass()

    @callback
    def _handle_controller_state_update(self, state: dict[str, Any]) -> None:
        """Refresh when the tracked controller-state key changes."""
        if self.entity_description.state_key in state:
            self.async_write_ha_state()

    @property
    def native_value(self) -> float | None:
        """Return the current side-specific value."""
        value = self._coordinator.controller_state.get(self.entity_description.state_key)
        if value is None:
            return None
        return float(value)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose the side served by this number entity."""
        return {"side": self.entity_description.side}

    async def async_set_native_value(self, value: float) -> None:
        """Set the side-specific value through the controller."""
        setting = round(value)

        async def _set_value(ctrl: BedController) -> None:
            await getattr(cast(Any, ctrl), self.entity_description.setter_name)(
                self.entity_description.side,
                setting,
            )

        await self._coordinator.async_execute_controller_command(_set_value)
