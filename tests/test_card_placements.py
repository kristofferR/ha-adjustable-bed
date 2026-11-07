"""Every entity tells the card where it sits, and the card's fixture matches."""

from __future__ import annotations

import importlib
import inspect
import json
import pkgutil
from unittest.mock import MagicMock

from homeassistant.helpers.entity import Entity

import custom_components.adjustable_bed as integration
from custom_components.adjustable_bed.card import CardSection
from custom_components.adjustable_bed.entity import PlacedInCard
from custom_components.adjustable_bed.number import NUMBER_DESCRIPTIONS, AdjustableBedPositionNumber
from tests.card_placements import FIXTURE, all_placements, built_entities


def _entity_classes() -> set[type[Entity]]:
    """Return every concrete entity class the integration defines."""
    for module in pkgutil.iter_modules(integration.__path__):
        importlib.import_module(f"{integration.__name__}.{module.name}")
    classes: set[type[Entity]] = set()
    pending = [Entity]
    while pending:
        for subclass in pending.pop().__subclasses__():
            pending.append(subclass)
            if subclass.__module__.startswith(integration.__name__) and not (
                inspect.isabstract(subclass) or subclass.__name__.startswith("_")
            ):
                classes.add(subclass)
    return classes


async def test_every_entity_has_a_card_placement_the_fixture_records() -> None:
    """A section, or the explicit hidden one, for every entity the integration creates.

    Regenerate the fixture with ``python -m tests.card_placements`` after
    adding or moving an entity.
    """
    built = await built_entities()
    built_classes = {type(entity) for entity in built}
    for cls in _entity_classes() - {PlacedInCard}:
        if cls.__name__ in {"AdjustableBedEntity", "RenamesInPlace"}:
            continue
        assert issubclass(cls, PlacedInCard), cls.__name__
        assert cls in built_classes, f"{cls.__name__} is not checked for a placement"
    for entity in built:
        assert isinstance(entity, PlacedInCard)
        assert entity._card.section in CardSection
    assert json.loads(FIXTURE.read_text()) == all_placements(built)


def test_placement_joins_the_platform_capabilities() -> None:
    """Capabilities stay published while an entity is unavailable."""
    runtime = MagicMock()
    runtime.entity_side = None
    entity = AdjustableBedPositionNumber(runtime, NUMBER_DESCRIPTIONS[0])
    entity._attr_available = False
    assert entity.capability_attributes == {
        "min": 0,
        "max": 68.0,
        "step": 1,
        "mode": "slider",
        "card_section": "motors",
        "card_motor": "back",
    }
