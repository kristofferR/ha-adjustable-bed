"""What every offline controller variant builds, checked where Home Assistant or the card would break."""

from __future__ import annotations

import asyncio
from collections import Counter

import pytest

from tests.entity_surface import devices as build
from tests.entity_translation_reachability import (
    entity_strings,
    factory_controllers,
    missing_translations,
)


@pytest.fixture(scope="module")
def devices():
    return asyncio.run(build())


def test_unique_ids_are_unique_on_every_device(devices) -> None:
    """Home Assistant drops the second entity with a unique ID it already has."""
    offenders = set()
    for device in devices:
        ids = Counter((entity.domain, entity.unique_id) for entity in device.entities)
        offenders |= {(device.bed, key) for key, count in ids.items() if count > 1}
    assert offenders == set()


def test_a_button_that_asks_first_offers_no_held_gesture(devices) -> None:
    """The card's hold path sends without its dialog, so a confirmed button never holds."""
    assert {
        (device.bed, entity.name)
        for device in devices
        for entity in device.entities
        if entity.requires_confirmation and entity.held
    } == set()


async def test_every_key_an_entity_can_be_given_is_translated() -> None:
    """A missing key names the entity after its device alone, such as "Bed Left" (#711)."""
    assert missing_translations(entity_strings(), await factory_controllers()) == {}
