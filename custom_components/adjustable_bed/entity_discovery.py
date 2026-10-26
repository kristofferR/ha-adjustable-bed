"""Add late-discovered controller entities without reconnecting or reloading HA."""

from collections.abc import Callable, Iterable

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .entity_runtime import EntityRuntime
from .octo_runtime import octo_controller


def async_setup_dynamic_entities(
    entry: ConfigEntry,
    coordinator: EntityRuntime,
    async_add_entities: AddEntitiesCallback,
    build_entities: Callable[[], Iterable[Entity]],
) -> None:
    """Register initial entities, then add each newly proven capability once."""
    entities = list(build_entities())
    known = {entity.unique_id for entity in entities}
    async_add_entities(entities)
    controller = coordinator.capability_controller
    if controller is None or not controller.has_dynamic_controller_entities:
        return

    def discover(_state: object) -> None:
        entities = list(build_entities())
        controller = coordinator.capability_controller
        octo = octo_controller(controller)
        if octo is not None and octo.controller_entity_discovery_complete:
            # Platform builders retire Octo registry rows only after a complete
            # capability list. Forget those IDs too, so a later complete list
            # can add the same stable identities again. Other controllers remain
            # add-only.
            known.intersection_update(entity.unique_id for entity in entities)
        additions = [entity for entity in entities if entity.unique_id not in known]
        if additions:
            known.update(entity.unique_id for entity in additions)
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
