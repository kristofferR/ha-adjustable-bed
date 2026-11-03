"""Add late-discovered controller entities without reconnecting or reloading HA."""

from collections.abc import Callable, Iterable

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .entity_runtime import EntityRuntime


def async_setup_dynamic_entities(
    hass: HomeAssistant,
    entry: ConfigEntry,
    coordinator: EntityRuntime,
    async_add_entities: AddEntitiesCallback,
    build_entities: Callable[[], Iterable[Entity]],
) -> None:
    """Register initial entities, then add each newly proven capability once."""
    entities = list(build_entities())
    known = {entity.unique_id: entity for entity in entities}
    async_add_entities(entities)
    controller = coordinator.capability_controller
    if controller is None or not controller.has_dynamic_controller_entities:
        return

    def discover(_state: object) -> None:
        candidates = list(build_entities())
        # Builders may retire registry rows when a capability is withdrawn.
        # Forget those instances so a later positive reply can recreate them.
        for identity, entity in list(known.items()):
            if entity.entity_id and er.async_get(hass).async_get(entity.entity_id) is None:
                del known[identity]
        additions = [entity for entity in candidates if entity.unique_id not in known]
        if additions:
            known.update((entity.unique_id, entity) for entity in additions)
            async_add_entities(additions)

    entry.async_on_unload(coordinator.register_controller_state_callback(discover))


def async_remove_retired_rmcontrol_telemetry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    coordinator: EntityRuntime,
    domain: str,
) -> None:
    """Retire RMControl telemetry after switching to a static controller."""
    controller = coordinator.capability_controller
    if controller is None or controller.has_dynamic_controller_entities:
        return
    specs = (
        controller.controller_state_sensor_specs
        if domain == "sensor"
        else controller.controller_state_binary_sensor_specs
    )
    active_ids = {coordinator.entity_unique_id(spec.key) for spec in specs}
    prefix, suffix = coordinator.entity_unique_id("rmcontrol_").split("rmcontrol_", 1)
    prefix += "rmcontrol_"
    registry = er.async_get(hass)
    for row in er.async_entries_for_config_entry(registry, entry.entry_id):
        if (
            row.domain == domain
            and row.platform == DOMAIN
            and row.unique_id.startswith(prefix)
            and row.unique_id.endswith(suffix)
            and row.unique_id not in active_ids
        ):
            registry.async_remove(row.entity_id)
