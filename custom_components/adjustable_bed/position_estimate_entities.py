"""Entities for calibrated position estimates and saved positions (#601).

Each estimated motor gets a number labelled as estimated and a "Set reference"
button; each estimated bed or side gets an "I used the remote" button. Saved
positions belong to the whole bed: a sensor lists them for the card, and each
position the user chose to expose gets a button that recalls it.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.button import ButtonEntity
from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .card import CARD_HIDDEN, CARD_SAVED_POSITIONS, CardRole, motor_card
from .const import CONF_BACK_MAX_ANGLE, CONF_LEGS_MAX_ANGLE, DOMAIN
from .coordinator import AdjustableBedCoordinator
from .entity import AdjustableBedEntity, PlacedInCard, RenamesInPlace
from .entity_runtime import EntityRuntime
from .paired_coordinator import PairedBedCoordinator, entity_runtimes
from .position_estimate import (
    BedEstimate,
    EstimateReason,
    EstimateState,
    PositionEstimates,
    SavedPosition,
    async_move_bed,
    async_recall_position,
    position_estimates,
)

# The card draws a dashed estimate only for an axis whose maximum angle the
# user configured; percent of travel is not an angle otherwise.
MAX_ANGLE_OPTIONS = {
    "back": CONF_BACK_MAX_ANGLE,
    "head": CONF_BACK_MAX_ANGLE,
    "legs": CONF_LEGS_MAX_ANGLE,
    "feet": CONF_LEGS_MAX_ANGLE,
}

ESTIMATED_MOTOR_ICONS = {
    "tv_lift": "mdi:television-classic",
    "back": "mdi:human-handsup",
    "legs": "mdi:human-handsdown",
    "head": "mdi:head",
    "feet": "mdi:foot-print",
}


def _estimated_beds(
    hass: HomeAssistant, entry: ConfigEntry
) -> tuple[PositionEstimates, list[tuple[EntityRuntime, BedEstimate]]] | None:
    manager = position_estimates(hass, entry.entry_id)
    coordinator = hass.data[DOMAIN][entry.entry_id]
    if manager is None:
        return None
    beds = [
        (runtime, bed)
        for runtime in entity_runtimes(coordinator)
        if (bed := manager.bed_for_address(runtime.address)) is not None
    ]
    return manager, beds


class _ListensToEstimates(RenamesInPlace, PlacedInCard):
    """Write state whenever the entry's estimates or saved positions change."""

    _attr_should_poll = False
    _manager: PositionEstimates

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(self._manager.async_add_listener(self._handle_change))

    @callback
    def _handle_change(self) -> None:
        self.async_write_ha_state()


class EstimatedPositionNumber(_ListensToEstimates, AdjustableBedEntity, NumberEntity):
    """Estimated travel of one motor; setting it moves for the calculated time."""

    _attr_native_min_value = 0
    _attr_native_max_value = 100
    _attr_native_step = 1
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_mode = NumberMode.SLIDER

    def __init__(
        self,
        runtime: EntityRuntime,
        manager: PositionEstimates,
        bed: BedEstimate,
        motor: str,
    ) -> None:
        super().__init__(runtime, motor_card(motor, CardRole.ESTIMATE))
        self._manager = manager
        self._bed = bed
        self._motor = motor
        key = f"{motor}_position_estimated"
        self._attr_unique_id = runtime.entity_unique_id(key)
        self._attr_translation_key = key
        self._attr_icon = ESTIMATED_MOTOR_ICONS.get(motor, "mdi:arrow-up-down")

    @property
    def available(self) -> bool:
        estimate = self._bed.motors.get(self._motor)
        return estimate is not None and estimate.calibrated

    @property
    def native_value(self) -> float | None:
        estimate = self._bed.motors.get(self._motor)
        # Only a tracking estimate is a number, so automations never act on a guess.
        if estimate is None or estimate.state is not EstimateState.TRACKING:
            return None
        return round(estimate.percent or 0.0)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        attributes = dict(getattr(self, "_attr_extra_state_attributes", None) or {})
        estimate = self._bed.motors.get(self._motor)
        if estimate is None:
            return attributes
        attributes.update(
            estimated=True,
            motor=self._motor,
            estimate_state=estimate.state.value,
            estimate_reason=estimate.reason.value if estimate.reason is not None else None,
            last_estimate=(round(estimate.percent, 1) if estimate.percent is not None else None),
            reference_at=estimate.reference_at.isoformat() if estimate.reference_at else None,
            full_travel_up_s=estimate.up_s,
            full_travel_down_s=estimate.down_s,
            moves_since_reference=estimate.moves_since_reference,
        )
        option = MAX_ANGLE_OPTIONS.get(self._motor)
        entry = self._coordinator.entry
        configured = None if option is None else entry.options.get(option, entry.data.get(option))
        if isinstance(configured, int | float) and not isinstance(configured, bool):
            attributes["max_angle"] = float(configured)
        return attributes

    async def async_set_native_value(self, value: float) -> None:
        if not await async_move_bed(self.hass, self._manager, self._bed, {self._motor: value}):
            raise HomeAssistantError(
                "The estimated position was not reached",
                translation_domain=DOMAIN,
                translation_key="estimated_position_not_reached",
            )


class SetReferenceButton(_ListensToEstimates, AdjustableBedEntity, ButtonEntity):
    """Confirm that one motor is flat now."""

    _attr_icon = "mdi:arrow-collapse-down"

    def __init__(
        self,
        runtime: EntityRuntime,
        manager: PositionEstimates,
        bed: BedEstimate,
        motor: str,
    ) -> None:
        super().__init__(runtime, motor_card(motor, CardRole.REFERENCE))
        self._manager = manager
        self._bed = bed
        self._motor = motor
        key = f"set_{motor}_reference"
        self._attr_unique_id = runtime.entity_unique_id(key)
        self._attr_translation_key = key

    @property
    def available(self) -> bool:
        estimate = self._bed.motors.get(self._motor)
        return estimate is not None and estimate.calibrated

    async def async_press(self) -> None:
        self._bed.set_reference([self._motor])


class RemoteUsedButton(AdjustableBedEntity, ButtonEntity):
    """Report a movement the integration could not see."""

    _attr_should_poll = False
    _attr_icon = "mdi:remote"

    def __init__(self, runtime: EntityRuntime, bed: BedEstimate) -> None:
        super().__init__(runtime, CARD_SAVED_POSITIONS)
        self._bed = bed
        key = "estimate_remote_used"
        self._attr_unique_id = runtime.entity_unique_id(key)
        self._attr_translation_key = key

    async def async_press(self) -> None:
        self._bed.invalidate(EstimateReason.REMOTE)


def _bed_identity(
    coordinator: AdjustableBedCoordinator | PairedBedCoordinator,
) -> tuple[DeviceInfo, str]:
    """Device and unique-id prefix of the whole bed (the parent of a pair)."""
    return coordinator.device_info, coordinator.entity_unique_id("")


class SavedPositionsSensor(_ListensToEstimates, SensorEntity):
    """Saved positions of the whole bed, listed for the card."""

    _attr_has_entity_name = True
    _attr_translation_key = "saved_positions"
    _attr_icon = "mdi:bookmark-multiple-outline"
    _card = CARD_SAVED_POSITIONS

    def __init__(
        self,
        coordinator: AdjustableBedCoordinator | PairedBedCoordinator,
        manager: PositionEstimates,
    ) -> None:
        self._manager = manager
        device_info, prefix = _bed_identity(coordinator)
        self._attr_device_info = device_info
        self._attr_unique_id = f"{prefix}saved_positions"

    @property
    def native_value(self) -> int:
        return len(self._manager.positions)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "positions": [
                {
                    "id": position.id,
                    "name": position.name,
                    "button": position.button,
                    "beds": position.targets,
                }
                for position in self._manager.positions
            ],
            "beds": sorted(bed.key for bed in self._manager.beds.values() if bed.motors),
        }


class SavedPositionButton(_ListensToEstimates, ButtonEntity):
    """Recall one saved position, for automations and voice."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:bookmark-outline"
    # The card lists saved positions from the saved positions sensor.
    _card = CARD_HIDDEN

    def __init__(
        self,
        coordinator: AdjustableBedCoordinator | PairedBedCoordinator,
        manager: PositionEstimates,
        position: SavedPosition,
    ) -> None:
        self._manager = manager
        self._position = position
        device_info, prefix = _bed_identity(coordinator)
        self._attr_device_info = device_info
        self._attr_unique_id = f"{prefix}saved_position_{position.id}"

    @property
    def name(self) -> str:
        return self._position.name

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"saved_position_id": self._position.id, "estimated": True}

    async def async_press(self) -> None:
        await async_recall_position(self.hass, self._manager, self._position)


def async_setup_estimate_numbers(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    found = _estimated_beds(hass, entry)
    if found is None:
        return
    manager, beds = found
    async_add_entities(
        EstimatedPositionNumber(runtime, manager, bed, motor)
        for runtime, bed in beds
        for motor in bed.motors
    )


def async_setup_estimate_sensors(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    manager = position_estimates(hass, entry.entry_id)
    if manager is None or not manager.active:
        return
    async_add_entities([SavedPositionsSensor(hass.data[DOMAIN][entry.entry_id], manager)])


def async_setup_estimate_buttons(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    found = _estimated_beds(hass, entry)
    if found is None:
        return
    manager, beds = found
    entities: list[ButtonEntity] = []
    for runtime, bed in beds:
        if not bed.motors:
            continue
        entities.extend(SetReferenceButton(runtime, manager, bed, motor) for motor in bed.motors)
        entities.append(RemoteUsedButton(runtime, bed))
    async_add_entities(entities)

    coordinator = hass.data[DOMAIN][entry.entry_id]
    buttons: dict[str, SavedPositionButton] = {}

    @callback
    def sync_position_buttons() -> None:
        wanted = {position.id: position for position in manager.positions if position.button}
        for position_id in [key for key in buttons if key not in wanted]:
            entity = buttons.pop(position_id)
            registry = er.async_get(hass)
            if entity.entity_id and registry.async_get(entity.entity_id) is not None:
                registry.async_remove(entity.entity_id)
        additions = [
            SavedPositionButton(coordinator, manager, position)
            for position_id, position in wanted.items()
            if position_id not in buttons
        ]
        for entity in additions:
            buttons[entity._position.id] = entity
        if additions:
            async_add_entities(additions)

    _async_remove_orphan_position_buttons(hass, entry, coordinator, manager)
    sync_position_buttons()
    entry.async_on_unload(manager.async_add_listener(sync_position_buttons))


def _async_remove_orphan_position_buttons(
    hass: HomeAssistant,
    entry: ConfigEntry,
    coordinator: AdjustableBedCoordinator | PairedBedCoordinator,
    manager: PositionEstimates,
) -> None:
    """Drop buttons of saved positions deleted or hidden while unloaded."""
    _device_info, prefix = _bed_identity(coordinator)
    wanted = {f"{prefix}saved_position_{item.id}" for item in manager.positions if item.button}
    registry = er.async_get(hass)
    for row in er.async_entries_for_config_entry(registry, entry.entry_id):
        if (
            row.domain == "button"
            and row.platform == DOMAIN
            and row.unique_id.startswith(f"{prefix}saved_position_")
            and row.unique_id not in wanted
        ):
            registry.async_remove(row.entity_id)
