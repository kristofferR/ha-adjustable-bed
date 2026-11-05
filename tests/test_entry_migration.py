"""Config entry migration of values released in v4.0.2, through schema 5.2."""

from __future__ import annotations

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed import async_migrate_entry, migrate_v5_2_entry
from custom_components.adjustable_bed.const import (
    BED_TYPE_JIECANG_APP,
    BED_TYPE_KEESON,
    BED_TYPE_LINAK,
    BED_TYPE_LOGICDATA_APP,
    CONF_BED_TYPE,
    CONF_DISABLE_DISCOVERY,
    CONF_HAS_LIGHT,
    CONF_PAIR_CHILDREN,
    CONF_PAIR_ID,
    CONF_PROFILE_ID,
    CONF_PROFILE_MIGRATION,
    CONF_PROTOCOL_VARIANT,
    CONF_SIDE,
    DOMAIN,
    KEESON_VARIANT_SINO,
)
from custom_components.adjustable_bed.pairing import KEY_ORIGIN_DATA, KEY_ORIGIN_OPTIONS


def _entry(
    hass: HomeAssistant,
    data: dict,
    *,
    version: int = 4,
    minor_version: int = 1,
    options: dict | None = None,
) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data=data,
        options=options or {},
        version=version,
        minor_version=minor_version,
    )
    entry.add_to_hass(hass)
    return entry


async def test_ore_alias_becomes_sino(hass: HomeAssistant) -> None:
    entry = _entry(
        hass,
        {CONF_ADDRESS: "AA:BB:CC:DD:EE:01", CONF_BED_TYPE: BED_TYPE_KEESON, CONF_PROTOCOL_VARIANT: "ore"},
    )

    await async_migrate_entry(hass, entry)

    assert (entry.version, entry.minor_version) == (5, 2)
    assert entry.data[CONF_PROTOCOL_VARIANT] == KEESON_VARIANT_SINO
    assert entry.data[CONF_PROFILE_ID] == "keeson:sino"


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

    await async_migrate_entry(hass, entry)

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

    await async_migrate_entry(hass, entry)

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

    await async_migrate_entry(hass, entry)

    assert (entry.version, entry.minor_version) == (5, 2)
    migrated = dict(entry.data)
    assert migrated.pop(CONF_PROFILE_ID) == BED_TYPE_LINAK
    assert migrated.pop(CONF_PROFILE_MIGRATION)["fields"] == {
        CONF_BED_TYPE: BED_TYPE_LINAK,
        CONF_PROTOCOL_VARIANT: "auto",
    }
    assert migrated == data


async def test_a_4x_pair_drops_obsolete_keys_on_its_way_to_5_2(hass: HomeAssistant) -> None:
    """Every place a pair stores configuration is cleaned and recorded; unknown keys stay."""
    left = {
        CONF_SIDE: "left",
        CONF_ADDRESS: "AA:BB:CC:DD:EE:0A",
        CONF_BED_TYPE: BED_TYPE_LINAK,
        CONF_DISABLE_DISCOVERY: True,
        "later_key": 1,
        KEY_ORIGIN_DATA: {CONF_BED_TYPE: BED_TYPE_LINAK, CONF_DISABLE_DISCOVERY: True},
        KEY_ORIGIN_OPTIONS: {CONF_DISABLE_DISCOVERY: False, "later_key": 2},
    }
    right = {
        CONF_SIDE: "right",
        CONF_ADDRESS: "AA:BB:CC:DD:EE:0B",
        CONF_BED_TYPE: BED_TYPE_LINAK,
        KEY_ORIGIN_OPTIONS: {CONF_DISABLE_DISCOVERY: True},
    }
    entry = _entry(
        hass,
        {
            CONF_PAIR_ID: "pair_1",
            CONF_BED_TYPE: BED_TYPE_LINAK,
            "pair_schema_version": 1,
            CONF_PAIR_CHILDREN: [left, right],
        },
        options={CONF_DISABLE_DISCOVERY: True, "later_key": 3},
    )

    await async_migrate_entry(hass, entry)

    assert (entry.version, entry.minor_version) == (5, 2)
    assert "pair_schema_version" not in entry.data
    assert dict(entry.options) == {"later_key": 3}
    migrated_left, migrated_right = entry.data[CONF_PAIR_CHILDREN]
    assert CONF_DISABLE_DISCOVERY not in migrated_left
    assert migrated_left["later_key"] == 1
    assert migrated_left[KEY_ORIGIN_DATA] == {CONF_BED_TYPE: BED_TYPE_LINAK}
    assert migrated_left[KEY_ORIGIN_OPTIONS] == {"later_key": 2}
    assert migrated_right[KEY_ORIGIN_OPTIONS] == {}
    record = entry.data[CONF_PROFILE_MIGRATION]
    assert (record["from_version"], record["from_minor_version"]) == (4, 1)
    assert record["profile_id"] == BED_TYPE_LINAK
    assert record["dropped_keys"] == {
        "data": ["pair_schema_version"],
        "data.left": [CONF_DISABLE_DISCOVERY],
        "data.left.origin_data": [CONF_DISABLE_DISCOVERY],
        "data.left.origin_options": [CONF_DISABLE_DISCOVERY],
        "data.right.origin_options": [CONF_DISABLE_DISCOVERY],
        "options": [CONF_DISABLE_DISCOVERY],
    }

    # Running the step again changes nothing.
    assert migrate_v5_2_entry(
        entry.data, entry.options, from_version=5, from_minor_version=2
    ) == (dict(entry.data), dict(entry.options))


async def test_a_5_1_entry_without_obsolete_keys_only_moves_to_5_2(hass: HomeAssistant) -> None:
    data = {CONF_ADDRESS: "AA:BB:CC:DD:EE:05", CONF_BED_TYPE: BED_TYPE_LINAK, "later_key": 1}
    entry = _entry(hass, dict(data), version=5, minor_version=1, options={"later_key": 2})

    await async_migrate_entry(hass, entry)

    assert (entry.version, entry.minor_version) == (5, 2)
    assert dict(entry.data) == data
    assert dict(entry.options) == {"later_key": 2}


async def test_a_5_1_entry_gets_a_record_of_what_was_dropped(hass: HomeAssistant) -> None:
    entry = _entry(
        hass,
        {CONF_PAIR_ID: "pair_2", CONF_BED_TYPE: BED_TYPE_LINAK, "pair_schema_version": 1},
        version=5,
        minor_version=1,
    )

    await async_migrate_entry(hass, entry)

    assert entry.data[CONF_PROFILE_MIGRATION] == {
        "from_version": 5,
        "from_minor_version": 1,
        "dropped_keys": {"data": ["pair_schema_version"]},
    }
