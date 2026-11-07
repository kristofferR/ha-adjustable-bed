"""Add late-discovered controller entities without reconnecting or reloading HA."""

from collections.abc import Callable, Iterable

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity import Entity

from .entity_runtime import EntityRuntime, controller_side_scope
from .entity_sweep import PlatformEntities


def async_setup_dynamic_entities(
    entry: ConfigEntry,
    coordinator: EntityRuntime,
    async_add_entities: PlatformEntities,
    build_entities: Callable[[], Iterable[Entity]],
    *,
    additional_coordinators: Iterable[EntityRuntime] = (),
) -> None:
    """Register initial entities, then add each newly proven capability once.

    A single runtime's builder runs with its side bound to a shared controller.
    A builder spanning ``additional_coordinators`` binds each runtime itself.
    """
    additional_coordinators = tuple(additional_coordinators)
    record = object()

    def build() -> list[Entity]:
        if additional_coordinators:
            return list(build_entities())
        with controller_side_scope(coordinator):
            return list(build_entities())

    entities = build()
    known = {entity.unique_id: entity for entity in entities}
    async_add_entities.publish(record, (entity.unique_id for entity in entities))
    async_add_entities.add_published(entities)

    def discover(_state: object) -> None:
        candidates = build()
        async_add_entities.publish(record, (entity.unique_id for entity in candidates))
        # Forget added entities whose rows a sweep retired, so they can return.
        for identity, entity in list(known.items()):
            if (
                identity is not None
                and entity.entity_id
                and not async_add_entities.has_row(identity)
            ):
                del known[identity]
        additions = [entity for entity in candidates if entity.unique_id not in known]
        known.update((entity.unique_id, entity) for entity in additions)
        async_add_entities.add_published(additions)

    for runtime in (coordinator, *additional_coordinators):
        controller = runtime.capability_controller
        if controller is not None and controller.has_dynamic_controller_entities:
            entry.async_on_unload(runtime.register_controller_state_callback(discover))
