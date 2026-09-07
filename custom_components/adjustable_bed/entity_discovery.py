"""Add late-discovered controller entities without reconnecting or reloading HA."""

from collections.abc import Callable, Iterable

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import AdjustableBedCoordinator


def async_setup_dynamic_entities(
    entry: ConfigEntry,
    coordinator: AdjustableBedCoordinator,
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
        additions = [entity for entity in build_entities() if entity.unique_id not in known]
        if additions:
            known.update(entity.unique_id for entity in additions)
            async_add_entities(additions)

    entry.async_on_unload(coordinator.register_controller_state_callback(discover))
