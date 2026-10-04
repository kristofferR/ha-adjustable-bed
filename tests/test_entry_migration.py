"""Config entry minor-version 2 migration of values released in v4.0.2."""

from __future__ import annotations

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed import async_migrate_entry
from custom_components.adjustable_bed.const import (
    BED_TYPE_JIECANG_APP,
    BED_TYPE_KEESON,
    BED_TYPE_LINAK,
    BED_TYPE_LOGICDATA_APP,
    CONF_BED_TYPE,
    CONF_HAS_LIGHT,
    CONF_PAIR_CHILDREN,
    CONF_PAIR_ID,
    CONF_PROTOCOL_VARIANT,
    DOMAIN,
    KEESON_VARIANT_SINO,
)
from custom_components.adjustable_bed.pairing import KEY_ORIGIN_DATA


def _entry(hass: HomeAssistant, data: dict, *, version: int = 4) -> MockConfigEntry:
    entry = MockConfigEntry(domain=DOMAIN, data=data, version=version, minor_version=1)
    entry.add_to_hass(hass)
    return entry


async def test_ore_alias_becomes_sino(hass: HomeAssistant) -> None:
    entry = _entry(
        hass,
        {CONF_ADDRESS: "AA:BB:CC:DD:EE:01", CONF_BED_TYPE: BED_TYPE_KEESON, CONF_PROTOCOL_VARIANT: "ore"},
    )

    assert await async_migrate_entry(hass, entry) is True

    assert entry.minor_version == 3
    assert entry.data[CONF_PROTOCOL_VARIANT] == KEESON_VARIANT_SINO


@pytest.mark.parametrize(
    ("bed_type", "old_key"),
    [
        (BED_TYPE_LOGICDATA_APP, "logicdata_app_has_light"),
        (BED_TYPE_JIECANG_APP, "jiecang_app_has_light"),
    ],
)
async def test_app_light_choice_becomes_has_light(
    hass: HomeAssistant, bed_type: str, old_key: str
) -> None:
    entry = _entry(
        hass,
        {CONF_ADDRESS: "AA:BB:CC:DD:EE:04", CONF_BED_TYPE: bed_type, old_key: False},
    )

    assert await async_migrate_entry(hass, entry) is True

    assert old_key not in entry.data
    assert entry.data[CONF_HAS_LIGHT] is False


async def test_paired_sides_and_their_originals_are_migrated(hass: HomeAssistant) -> None:
    side = {
        CONF_ADDRESS: "AA:BB:CC:DD:EE:02",
        CONF_BED_TYPE: BED_TYPE_KEESON,
        CONF_PROTOCOL_VARIANT: "ore",
        KEY_ORIGIN_DATA: {CONF_BED_TYPE: BED_TYPE_KEESON, CONF_PROTOCOL_VARIANT: "ore"},
    }
    entry = _entry(
        hass,
        {CONF_PAIR_ID: "pair_1", CONF_BED_TYPE: BED_TYPE_KEESON, CONF_PAIR_CHILDREN: [side]},
    )

    assert await async_migrate_entry(hass, entry) is True

    (child,) = entry.data[CONF_PAIR_CHILDREN]
    assert child[CONF_PROTOCOL_VARIANT] == KEESON_VARIANT_SINO
    assert child[KEY_ORIGIN_DATA][CONF_PROTOCOL_VARIANT] == KEESON_VARIANT_SINO


async def test_other_entries_are_unchanged(hass: HomeAssistant) -> None:
    data = {
        CONF_ADDRESS: "AA:BB:CC:DD:EE:03",
        CONF_NAME: "Bed",
        CONF_BED_TYPE: BED_TYPE_LINAK,
        CONF_PROTOCOL_VARIANT: "auto",
    }
    entry = _entry(hass, dict(data), version=3)

    assert await async_migrate_entry(hass, entry) is True

    assert (entry.version, entry.minor_version) == (4, 3)
    assert dict(entry.data) == data
