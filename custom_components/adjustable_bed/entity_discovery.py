"""Add late-discovered controller entities without reconnecting or reloading HA."""

from collections.abc import Callable, Iterable

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .entity_runtime import EntityRuntime, controller_side_scope
from .octo_runtime import octo_controller


def async_setup_dynamic_entities(
    hass: HomeAssistant,
    entry: ConfigEntry,
    coordinator: EntityRuntime,
    async_add_entities: AddEntitiesCallback,
    build_entities: Callable[[], Iterable[Entity]],
    *,
    additional_coordinators: Iterable[EntityRuntime] = (),
) -> None:
    """Register initial entities, then add each newly proven capability once.

    A single runtime's builder runs with its side bound to a shared controller.
    A builder spanning ``additional_coordinators`` binds each runtime itself.
    """
    additional_coordinators = tuple(additional_coordinators)

    def build() -> list[Entity]:
        if additional_coordinators:
            return list(build_entities())
        with controller_side_scope(coordinator):
            return list(build_entities())

    entities = build()
    known = {entity.unique_id: entity for entity in entities}
    async_add_entities(entities)

    def discover(_state: object) -> None:
        candidates = build()
        # Builders may retire registry rows when a capability is withdrawn.
        # Forget those instances so a later positive reply can recreate them.
        for identity, entity in list(known.items()):
            if entity.entity_id and er.async_get(hass).async_get(entity.entity_id) is None:
                del known[identity]
        octo = octo_controller(coordinator.capability_controller)
        if octo is not None and octo.controller_entity_discovery_complete:
            # Platform builders retire Octo registry rows only after a complete
            # capability list. Forget those IDs too, so a later complete list
            # can add the same stable identities again.
            current = {entity.unique_id for entity in candidates}
            for identity in [identity for identity in known if identity not in current]:
                del known[identity]
        additions = [entity for entity in candidates if entity.unique_id not in known]
        if additions:
            known.update((entity.unique_id, entity) for entity in additions)
            async_add_entities(additions)

    for runtime in (coordinator, *additional_coordinators):
        controller = runtime.capability_controller
        if controller is not None and controller.has_dynamic_controller_entities:
            entry.async_on_unload(runtime.register_controller_state_callback(discover))


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
    with controller_side_scope(coordinator):
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
