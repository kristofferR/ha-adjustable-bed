"""Entities keep running when the user changes their entity_id."""

from __future__ import annotations

import importlib
import inspect
import pkgutil
from unittest.mock import patch

from homeassistant.components.cover.const import DATA_COMPONENT
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

# Home Assistant's own test for whether a rename removes and re-adds an entity.
# It goes away in 2027.11, when every entity is renamed in place.
from homeassistant.helpers.entity import Entity, _entity_class_requires_readd
from pytest_homeassistant.common import MockConfigEntry

import custom_components.adjustable_bed as integration
from custom_components.adjustable_bed.const import DOMAIN
from custom_components.adjustable_bed.cover import AdjustableBedCover


def _entity_classes() -> list[type[Entity]]:
    classes: dict[str, type[Entity]] = {}
    for module in pkgutil.walk_packages(integration.__path__, f"{integration.__name__}."):
        for value in vars(importlib.import_module(module.name)).values():
            if (
                inspect.isclass(value)
                and issubclass(value, Entity)
                and value.__module__.startswith(integration.__name__)
            ):
                classes[f"{value.__module__}.{value.__qualname__}"] = value
    return list(classes.values())


def test_no_entity_class_is_removed_and_re_added_on_rename() -> None:
    classes = _entity_classes()
    assert len(classes) > 30
    assert [cls.__qualname__ for cls in classes if _entity_class_requires_readd(cls)] == []


async def test_a_renamed_cover_keeps_its_entity_and_subscriptions(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_coordinator_connected,
) -> None:
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id("cover", DOMAIN, f"{mock_config_entry.unique_id}_back")
    assert entity_id is not None
    cover = hass.data[DATA_COMPONENT].get_entity(entity_id)
    assert isinstance(cover, AdjustableBedCover)

    with (
        patch.object(AdjustableBedCover, "async_will_remove_from_hass") as removed,
        patch.object(AdjustableBedCover, "async_added_to_hass") as added,
    ):
        registry.async_update_entity(entity_id, new_entity_id="cover.renamed_back")
        await hass.async_block_till_done()

    removed.assert_not_called()
    added.assert_not_called()
    assert hass.data[DATA_COMPONENT].get_entity("cover.renamed_back") is cover
    assert hass.states.get(entity_id) is None
    assert hass.states.get("cover.renamed_back") is not None
    await hass.config_entries.async_unload(mock_config_entry.entry_id)
