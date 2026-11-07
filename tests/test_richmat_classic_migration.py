"""Schema 5.4 renames what the classic Richmat apps stored under their 4.4 audit name."""

from __future__ import annotations

from homeassistant.const import CONF_ADDRESS
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.storage import Store
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed import async_migrate_entry, migrate_v5_4_data
from custom_components.adjustable_bed.app_state_store import app_state_storage_key
from custom_components.adjustable_bed.beds.richmat_classic.profiles import (
    LEGACY_KEY_PREFIX,
    current_control_name,
)
from custom_components.adjustable_bed.const import (
    BED_TYPE_RICHMAT_CLASSIC_APPS,
    CONF_BED_TYPE,
    CONF_PAIR_CHILDREN,
    CONF_PAIR_ID,
    CONF_PAIR_MODE,
    CONF_RICHMAT_CLASSIC_THIRD_SERVICE,
    CONF_SIDE,
    DOMAIN,
    PAIR_MODE_SEPARATE_ADDRESS,
)
from custom_components.adjustable_bed.pairing import KEY_ORIGIN_DATA, KEY_ORIGIN_OPTIONS

LEGACY_THIRD_SERVICE = f"{LEGACY_KEY_PREFIX}third_service"
LEFT, RIGHT = "AA:BB:CC:DD:EE:41", "AA:BB:CC:DD:EE:42"


def _entry(hass: HomeAssistant, data: dict, options: dict | None = None) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN, data=data, options=options or {}, version=5, minor_version=3
    )
    entry.add_to_hass(hass)
    return entry


def test_the_third_service_key_is_renamed_everywhere_an_entry_stores_it() -> None:
    side = {CONF_SIDE: "left", CONF_ADDRESS: LEFT, LEGACY_THIRD_SERVICE: True}
    data = {
        CONF_PAIR_ID: "pair_1",
        CONF_PAIR_CHILDREN: [
            {
                **side,
                KEY_ORIGIN_DATA: {LEGACY_THIRD_SERVICE: True},
                KEY_ORIGIN_OPTIONS: {LEGACY_THIRD_SERVICE: False},
            },
            {CONF_SIDE: "right", CONF_ADDRESS: RIGHT},
        ],
    }

    migrated = migrate_v5_4_data(data)

    left, right = migrated[CONF_PAIR_CHILDREN]
    assert left == {
        CONF_SIDE: "left",
        CONF_ADDRESS: LEFT,
        CONF_RICHMAT_CLASSIC_THIRD_SERVICE: True,
        KEY_ORIGIN_DATA: {CONF_RICHMAT_CLASSIC_THIRD_SERVICE: True},
        KEY_ORIGIN_OPTIONS: {CONF_RICHMAT_CLASSIC_THIRD_SERVICE: False},
    }
    assert right == {CONF_SIDE: "right", CONF_ADDRESS: RIGHT}


async def test_a_standalone_entry_moves_its_key_entities_and_app_state(
    hass: HomeAssistant, hass_storage: dict
) -> None:
    hass_storage[app_state_storage_key(LEFT)] = {
        "version": 1,
        "key": app_state_storage_key(LEFT),
        "data": {
            f"{BED_TYPE_RICHMAT_CLASSIC_APPS}:cluster018:superior:ABRM": {"lamp_minutes": 5},
            "profile_recommendations": {"kept": True},
        },
    }
    entry = _entry(
        hass,
        {CONF_ADDRESS: LEFT, CONF_BED_TYPE: BED_TYPE_RICHMAT_CLASSIC_APPS, LEGACY_THIRD_SERVICE: True},
        {LEGACY_THIRD_SERVICE: False},
    )
    registry = er.async_get(hass)
    button = registry.async_get_or_create(
        "button", DOMAIN, f"{LEFT}_{LEGACY_KEY_PREFIX}9_hold", config_entry=entry
    )
    status = registry.async_get_or_create(
        "sensor", DOMAIN, f"{LEFT}_{LEGACY_KEY_PREFIX}status", config_entry=entry
    )
    other = registry.async_get_or_create("button", DOMAIN, f"{LEFT}_stop", config_entry=entry)

    await async_migrate_entry(hass, entry)

    assert (entry.version, entry.minor_version) == (5, 5)
    assert dict(entry.data) == {
        CONF_ADDRESS: LEFT,
        CONF_BED_TYPE: BED_TYPE_RICHMAT_CLASSIC_APPS,
        CONF_RICHMAT_CLASSIC_THIRD_SERVICE: True,
    }
    assert dict(entry.options) == {CONF_RICHMAT_CLASSIC_THIRD_SERVICE: False}
    assert registry.async_get(button.entity_id).unique_id == f"{LEFT}_richmat_classic_9_hold"
    assert registry.async_get(status.entity_id).unique_id == f"{LEFT}_richmat_classic_status"
    assert registry.async_get(other.entity_id).unique_id == f"{LEFT}_stop"
    stored = await Store(hass, 1, app_state_storage_key(LEFT)).async_load()
    assert stored == {
        f"{BED_TYPE_RICHMAT_CLASSIC_APPS}:superior:ABRM": {"lamp_minutes": 5},
        "profile_recommendations": {"kept": True},
    }


async def test_a_pairs_side_and_combined_entities_are_renamed(hass: HomeAssistant) -> None:
    entry = _entry(
        hass,
        {
            CONF_PAIR_ID: "pair_2",
            CONF_PAIR_MODE: PAIR_MODE_SEPARATE_ADDRESS,
            CONF_BED_TYPE: BED_TYPE_RICHMAT_CLASSIC_APPS,
            CONF_PAIR_CHILDREN: [
                {CONF_SIDE: "left", CONF_ADDRESS: LEFT},
                {CONF_SIDE: "right", CONF_ADDRESS: RIGHT},
            ],
        },
    )
    registry = er.async_get(hass)
    rows = {
        unique_id: registry.async_get_or_create("select", DOMAIN, unique_id, config_entry=entry)
        for unique_id in (f"{RIGHT}_{LEGACY_KEY_PREFIX}mode", f"pair_2_{LEGACY_KEY_PREFIX}release_both")
    }

    await async_migrate_entry(hass, entry)

    assert {registry.async_get(row.entity_id).unique_id for row in rows.values()} == {
        f"{RIGHT}_richmat_classic_mode",
        "pair_2_richmat_classic_release_both",
    }


def test_hold_control_accepts_the_held_control_names_44_shipped() -> None:
    assert current_control_name(f"{LEGACY_KEY_PREFIX}6") == "richmat_classic_6"
    assert current_control_name(f"{LEGACY_KEY_PREFIX}12_hold") == "richmat_classic_12_hold"
    assert current_control_name("richmat_classic_6") == "richmat_classic_6"
    assert current_control_name("head_up") == "head_up"
