"""Config entry migration of values released in v4.0.2, through schema 5.6."""

from __future__ import annotations

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed import (
    async_migrate_entry,
    migrate_v5_2_entry,
    migrate_v5_3_data,
    migrate_v5_6_entry,
)
from custom_components.adjustable_bed.bed_traits import reads_positions
from custom_components.adjustable_bed.const import (
    BED_TYPE_COMFORT_ENHANCEMENTS,
    BED_TYPE_DIAGNOSTIC,
    BED_TYPE_FURNIMOVE,
    BED_TYPE_JIECANG_APP,
    BED_TYPE_KEESON,
    BED_TYPE_LINAK,
    BED_TYPE_LOGICDATA_APP,
    BED_TYPE_OCTO,
    BED_TYPE_SLEEPYS_ELITE_APP,
    CONF_BED_TYPE,
    CONF_CONNECTION_MODE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_DISABLE_DISCOVERY,
    CONF_FURNIMOVE_REMOTE,
    CONF_HAS_LIGHT,
    CONF_HAS_MASSAGE,
    CONF_MOTOR_COUNT,
    CONF_OCTO_MOTOR_COUNT_OVERRIDE,
    CONF_PAIR_CHILDREN,
    CONF_PAIR_ID,
    CONF_PREFERRED_ADAPTER,
    CONF_PROFILE_ID,
    CONF_PROFILE_MIGRATION,
    CONF_PROTOCOL_VARIANT,
    CONF_SIDE,
    CONF_SLEEPYS_ELITE_SELECTOR,
    CONNECTION_MODE_ALWAYS,
    CONNECTION_MODE_IDLE,
    CONNECTION_MODE_RELEASE,
    DOMAIN,
    KEESON_VARIANT_SINO,
)
from custom_components.adjustable_bed.pairing import (
    KEY_ORIGIN_DATA,
    KEY_ORIGIN_OPTIONS,
    effective_child_data,
)
from tests.pair_mode import CONF_PAIR_CONNECTION_MODE


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

    assert (entry.version, entry.minor_version) == (5, 8)
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


async def test_other_entries_keep_their_settings(hass: HomeAssistant) -> None:
    """Only the settings 4.x ran with by default are saved; nothing else changes."""
    data = {
        CONF_ADDRESS: "AA:BB:CC:DD:EE:03",
        CONF_NAME: "Bed",
        CONF_BED_TYPE: BED_TYPE_LINAK,
        CONF_PROTOCOL_VARIANT: "auto",
    }
    entry = _entry(hass, dict(data), version=3)

    await async_migrate_entry(hass, entry)

    assert (entry.version, entry.minor_version) == (5, 8)
    migrated = dict(entry.data)
    assert migrated.pop(CONF_PROFILE_ID) == BED_TYPE_LINAK
    assert migrated.pop(CONF_PROFILE_MIGRATION)["fields"] == {
        CONF_BED_TYPE: BED_TYPE_LINAK,
        CONF_PROTOCOL_VARIANT: "auto",
    }
    assert migrated == {
        **data,
        CONF_DISABLE_ANGLE_SENSING: True,
        CONF_CONNECTION_MODE: CONNECTION_MODE_IDLE,
    }


@pytest.mark.parametrize(
    ("saved", "mode"),
    [
        # 1.4.6 to 2.5.3 set up a diagnostic device without a handoff; 4.x kept
        # its link, where v5's default for the bed type hands it back.
        ({}, CONNECTION_MODE_IDLE),
        ({"disconnect_after_command": True}, CONNECTION_MODE_RELEASE),
    ],
)
async def test_a_4x_entry_keeps_the_connection_it_ran_with(
    hass: HomeAssistant, saved: dict, mode: str
) -> None:
    # The data 2.5.3 stored for a diagnostic device, as 4.4.2 left it.
    data = {
        CONF_ADDRESS: "AA:BB:CC:DD:EE:0C",
        CONF_BED_TYPE: BED_TYPE_DIAGNOSTIC,
        CONF_NAME: "Unknown bed",
        CONF_MOTOR_COUNT: 0,
        CONF_HAS_MASSAGE: False,
        CONF_DISABLE_ANGLE_SENSING: True,
        CONF_PREFERRED_ADAPTER: "auto",
        **saved,
    }
    entry = _entry(hass, data, minor_version=3)

    await async_migrate_entry(hass, entry)

    assert entry.data[CONF_CONNECTION_MODE] == mode


async def test_a_4x_entry_keeps_not_reading_positions_its_options_never_reached(
    hass: HomeAssistant,
) -> None:
    """4.x read a bed's own setting from its data alone."""
    entry = _entry(
        hass,
        {CONF_ADDRESS: "AA:BB:CC:DD:EE:0F", CONF_BED_TYPE: BED_TYPE_LINAK},
        minor_version=3,
        options={CONF_DISABLE_ANGLE_SENSING: False},
    )

    await async_migrate_entry(hass, entry)

    assert not reads_positions(entry.data)


async def test_a_4x_pair_keeps_what_each_side_ran_with(hass: HomeAssistant) -> None:
    """Sides and originals that saved neither setting stay connected and do not read positions."""
    original = {
        CONF_NAME: "Bed",
        CONF_BED_TYPE: BED_TYPE_LINAK,
        CONF_MOTOR_COUNT: 2,
        CONF_HAS_MASSAGE: False,
        CONF_PREFERRED_ADAPTER: "auto",
        "idle_disconnect_seconds": 40,
    }
    # The pair 4.4.2's pairing flow built from two such entries.
    children = [
        {
            **original,
            CONF_ADDRESS: address,
            CONF_SIDE: side,
            "absorbed_entry_id": f"entry_{side}",
            "origin_unique_id": address,
            KEY_ORIGIN_DATA: {**original, CONF_ADDRESS: address},
            KEY_ORIGIN_OPTIONS: {},
        }
        for side, address in (("left", "AA:BB:CC:DD:EE:0D"), ("right", "AA:BB:CC:DD:EE:0E"))
    ]
    entry = _entry(
        hass,
        {
            CONF_PAIR_ID: "pair_2",
            "pair_mode": "separate_address",
            "pair_schema_version": 1,
            CONF_BED_TYPE: BED_TYPE_LINAK,
            CONF_NAME: "Pair",
            "pair_member_addresses": ["AA:BB:CC:DD:EE:0D", "AA:BB:CC:DD:EE:0E"],
            CONF_PAIR_CHILDREN: children,
        },
        minor_version=3,
    )

    await async_migrate_entry(hass, entry)

    # 4.4.2 kept these on the sides only, so the pair's own form shows no value
    # neither side ran with.
    assert CONF_CONNECTION_MODE not in entry.data
    assert CONF_DISABLE_ANGLE_SENSING not in entry.data
    for child in entry.data[CONF_PAIR_CHILDREN]:
        side = effective_child_data(entry.data, child[CONF_SIDE], entry.options)
        assert side[CONF_CONNECTION_MODE] == CONNECTION_MODE_IDLE
        assert not reads_positions(side)
        assert child[KEY_ORIGIN_DATA][CONF_CONNECTION_MODE] == CONNECTION_MODE_IDLE
        assert not reads_positions(child[KEY_ORIGIN_DATA])


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

    assert (entry.version, entry.minor_version) == (5, 8)
    assert "pair_schema_version" not in entry.data
    assert dict(entry.options) == {"later_key": 3}
    migrated_left, migrated_right = entry.data[CONF_PAIR_CHILDREN]
    assert CONF_DISABLE_DISCOVERY not in migrated_left
    assert migrated_left["later_key"] == 1
    assert migrated_left[KEY_ORIGIN_DATA] == {
        CONF_BED_TYPE: BED_TYPE_LINAK,
        # What the original ran with on 4.x, which saved neither.
        CONF_DISABLE_ANGLE_SENSING: True,
        CONF_CONNECTION_MODE: CONNECTION_MODE_IDLE,
    }
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


async def test_a_5_1_entry_without_obsolete_keys_only_moves_to_the_current_schema(hass: HomeAssistant) -> None:
    data = {CONF_ADDRESS: "AA:BB:CC:DD:EE:05", CONF_BED_TYPE: BED_TYPE_LINAK, "later_key": 1}
    entry = _entry(hass, dict(data), version=5, minor_version=1, options={"later_key": 2})

    await async_migrate_entry(hass, entry)

    assert (entry.version, entry.minor_version) == (5, 8)
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


# The layouts whose massage buttons raise or do nothing (#787), and a layout of
# each that has massage. A FurniMove handset's table and the Sleepy's control
# box decide massage, as do Comfort Enhancements layouts other than MC3.
NO_MASSAGE = {
    "furnimove handset without massage": {
        CONF_BED_TYPE: BED_TYPE_FURNIMOVE,
        CONF_FURNIMOVE_REMOTE: "80599",
    },
    "comfort enhancements mc3": {
        CONF_BED_TYPE: BED_TYPE_COMFORT_ENHANCEMENTS,
        CONF_PROTOCOL_VARIANT: "mc3",
    },
    "sleepys app BOX15 selector": {
        CONF_BED_TYPE: BED_TYPE_SLEEPYS_ELITE_APP,
        CONF_SLEEPYS_ELITE_SELECTOR: "BOX15",
    },
}
WITH_MASSAGE = {
    "furnimove handset with massage": {
        CONF_BED_TYPE: BED_TYPE_FURNIMOVE,
        CONF_FURNIMOVE_REMOTE: "12234",
    },
    "comfort enhancements mc2": {
        CONF_BED_TYPE: BED_TYPE_COMFORT_ENHANCEMENTS,
        CONF_PROTOCOL_VARIANT: "mc2",
    },
    "sleepys app BOX25 selector": {
        CONF_BED_TYPE: BED_TYPE_SLEEPYS_ELITE_APP,
        CONF_SLEEPYS_ELITE_SELECTOR: "BOX25",
    },
}


@pytest.mark.parametrize("layout", NO_MASSAGE.values(), ids=NO_MASSAGE)
async def test_schema_5_3_turns_massage_off_without_a_massage_page(
    hass: HomeAssistant, layout: dict
) -> None:
    data = {CONF_ADDRESS: "AA:BB:CC:DD:EE:10", **layout, CONF_HAS_MASSAGE: True}
    entry = _entry(hass, dict(data), version=5, minor_version=2)

    await async_migrate_entry(hass, entry)

    assert (entry.version, entry.minor_version) == (5, 8)
    assert entry.data[CONF_HAS_MASSAGE] is False
    assert entry.data[CONF_PROFILE_MIGRATION] == {
        "from_version": 5,
        "from_minor_version": 2,
        "massage_off": ["data"],
    }
    # Running the step again changes nothing.
    assert migrate_v5_3_data(entry.data, entry.options, from_version=5, from_minor_version=3) == (
        dict(entry.data),
        {},
        [],
    )


@pytest.mark.parametrize("layout", WITH_MASSAGE.values(), ids=WITH_MASSAGE)
async def test_schema_5_3_leaves_a_layout_with_massage_alone(
    hass: HomeAssistant, layout: dict
) -> None:
    data = {CONF_ADDRESS: "AA:BB:CC:DD:EE:11", **layout, CONF_HAS_MASSAGE: True}
    entry = _entry(hass, dict(data), version=5, minor_version=2)

    await async_migrate_entry(hass, entry)

    assert (entry.version, entry.minor_version) == (5, 8)
    assert dict(entry.data) == data


@pytest.mark.parametrize("layout", NO_MASSAGE.values(), ids=NO_MASSAGE)
async def test_schema_5_3_turns_massage_off_on_a_paired_side_and_its_original(
    hass: HomeAssistant, layout: dict
) -> None:
    # The left side inherits Massage from the pair; the right side has massage.
    left = {
        CONF_SIDE: "left",
        CONF_ADDRESS: "AA:BB:CC:DD:EE:12",
        **layout,
        KEY_ORIGIN_DATA: {**layout, CONF_HAS_MASSAGE: True},
    }
    right = {
        CONF_SIDE: "right",
        CONF_ADDRESS: "AA:BB:CC:DD:EE:13",
        **WITH_MASSAGE["sleepys app BOX25 selector"],
        CONF_HAS_MASSAGE: True,
    }
    entry = _entry(
        hass,
        {
            CONF_PAIR_ID: "pair_3",
            CONF_BED_TYPE: layout[CONF_BED_TYPE],
            CONF_HAS_MASSAGE: True,
            CONF_PAIR_CHILDREN: [left, right],
        },
        version=5,
        minor_version=2,
    )

    await async_migrate_entry(hass, entry)

    migrated_left, migrated_right = entry.data[CONF_PAIR_CHILDREN]
    assert migrated_left[CONF_HAS_MASSAGE] is False
    assert migrated_left[KEY_ORIGIN_DATA][CONF_HAS_MASSAGE] is False
    assert migrated_right[CONF_HAS_MASSAGE] is True
    assert entry.data[CONF_PROFILE_MIGRATION]["massage_off"] == [
        "data.left",
        "data.left.origin_data",
    ]


_FURNIMOVE_OFF = NO_MASSAGE["furnimove handset without massage"]
_FURNIMOVE_ON = WITH_MASSAGE["furnimove handset with massage"]
_BOX25 = WITH_MASSAGE["sleepys app BOX25 selector"]
_JIECANG = {CONF_BED_TYPE: BED_TYPE_JIECANG_APP, CONF_HAS_MASSAGE: True}


@pytest.mark.parametrize(
    ("left", "right", "option", "expected", "massage_off"),
    [
        # A mixed pair: only the side without massage turns off.
        (_FURNIMOVE_OFF, _BOX25, True, (False, True), ["data.left"]),
        # The same layout on both sides.
        (_FURNIMOVE_OFF, _FURNIMOVE_OFF, True, (False, False), ["data.left", "data.right"]),
        # Handsets with massage keep the value the option gave them.
        (_FURNIMOVE_ON, _FURNIMOVE_ON, False, (False, False), []),
        # A side whose profile already owned Massage never took the option.
        (_FURNIMOVE_OFF, _JIECANG, False, (False, True), []),
    ],
    ids=["mixed pair", "same layout", "with massage", "side owns massage"],
)
async def test_schema_5_3_moves_a_shared_massage_option_into_the_sides(
    hass: HomeAssistant, left, right, option, expected, massage_off
) -> None:
    """A parent option cannot override a corrected side, and no side changes otherwise."""
    entry = _entry(
        hass,
        {
            CONF_PAIR_ID: "pair_5",
            CONF_BED_TYPE: left[CONF_BED_TYPE],
            CONF_HAS_MASSAGE: False,
            CONF_PAIR_CHILDREN: [
                {CONF_SIDE: "left", CONF_ADDRESS: "AA:BB:CC:DD:EE:20", **left},
                {CONF_SIDE: "right", CONF_ADDRESS: "AA:BB:CC:DD:EE:21", **right},
            ],
        },
        version=5,
        minor_version=2,
        options={CONF_HAS_MASSAGE: option, "idle_disconnect_seconds": 55},
    )

    await async_migrate_entry(hass, entry)

    # Schema 5.6 moves the shared timeout into each side.
    assert dict(entry.options) == {}
    assert all(child["idle_disconnect_seconds"] == 55 for child in entry.data[CONF_PAIR_CHILDREN])
    effective = tuple(
        effective_child_data(entry.data, side, entry.options)[CONF_HAS_MASSAGE]
        for side in ("left", "right")
    )
    assert effective == expected
    record = entry.data.get(CONF_PROFILE_MIGRATION, {})
    assert record.get("massage_off", []) == massage_off


async def test_a_4x_entry_turns_massage_off_on_its_way_to_5_3(hass: HomeAssistant) -> None:
    data = {
        CONF_ADDRESS: "AA:BB:CC:DD:EE:14",
        **NO_MASSAGE["furnimove handset without massage"],
        CONF_HAS_MASSAGE: True,
    }
    entry = _entry(hass, dict(data))

    await async_migrate_entry(hass, entry)

    assert (entry.version, entry.minor_version) == (5, 8)
    assert entry.data[CONF_HAS_MASSAGE] is False
    record = entry.data[CONF_PROFILE_MIGRATION]
    assert (record["from_version"], record["from_minor_version"]) == (4, 1)
    assert record["profile_id"] == BED_TYPE_FURNIMOVE
    assert record["massage_off"] == ["data"]


@pytest.mark.parametrize("layout", NO_MASSAGE.values(), ids=NO_MASSAGE)
async def test_the_dead_massage_buttons_leave_the_registry(
    hass: HomeAssistant, layout: dict
) -> None:
    """The step removes them itself, so a bed out of reach keeps no orphans."""
    from homeassistant.helpers import entity_registry as er

    address = "AA:BB:CC:DD:EE:15"
    entry = _entry(
        hass,
        {CONF_ADDRESS: address, CONF_NAME: "Bed", **layout, CONF_HAS_MASSAGE: True},
        version=5,
        minor_version=2,
    )
    registry = er.async_get(hass)
    dead = registry.async_get_or_create(
        "button", DOMAIN, f"{address}_massage_all_toggle", config_entry=entry
    )
    kept = registry.async_get_or_create("button", DOMAIN, f"{address}_stop", config_entry=entry)

    await async_migrate_entry(hass, entry)

    assert registry.async_get(dead.entity_id) is None
    assert registry.async_get(kept.entity_id) is not None


async def test_a_paired_sides_dead_massage_buttons_leave_the_registry(hass: HomeAssistant) -> None:
    from homeassistant.helpers import entity_registry as er

    from custom_components.adjustable_bed.const import (
        CONF_PAIR_MODE,
        PAIR_MODE_SEPARATE_ADDRESS,
    )

    left_address, right_address = "AA:BB:CC:DD:EE:16", "AA:BB:CC:DD:EE:17"
    entry = _entry(
        hass,
        {
            CONF_PAIR_ID: "pair_4",
            CONF_PAIR_MODE: PAIR_MODE_SEPARATE_ADDRESS,
            CONF_BED_TYPE: BED_TYPE_COMFORT_ENHANCEMENTS,
            CONF_PAIR_CHILDREN: [
                {
                    CONF_SIDE: "left",
                    CONF_ADDRESS: left_address,
                    **NO_MASSAGE["comfort enhancements mc3"],
                    CONF_HAS_MASSAGE: True,
                },
                {
                    CONF_SIDE: "right",
                    CONF_ADDRESS: right_address,
                    **WITH_MASSAGE["comfort enhancements mc2"],
                    CONF_HAS_MASSAGE: True,
                },
            ],
        },
        version=5,
        minor_version=2,
    )
    registry = er.async_get(hass)
    rows = {
        unique_id: registry.async_get_or_create("button", DOMAIN, unique_id, config_entry=entry)
        for unique_id in (
            f"{left_address}_massage_all_toggle",
            f"{right_address}_massage_all_toggle",
            "pair_4_massage_all_toggle_both",
        )
    }

    await async_migrate_entry(hass, entry)

    assert registry.async_get(rows[f"{left_address}_massage_all_toggle"].entity_id) is None
    assert registry.async_get(rows["pair_4_massage_all_toggle_both"].entity_id) is None
    # The side with massage keeps its buttons.
    assert registry.async_get(rows[f"{right_address}_massage_all_toggle"].entity_id) is not None


@pytest.mark.parametrize(
    ("stored", "expected"),
    [
        # A count other than the default was the user's layout before the selector.
        ({CONF_MOTOR_COUNT: 1}, "1"),
        ({CONF_MOTOR_COUNT: 4}, "4"),
        # The default count, or none, followed the advertised layout.
        ({CONF_MOTOR_COUNT: 2}, "auto"),
        ({}, "auto"),
    ],
)
async def test_schema_5_5_stores_an_octo_layout_as_its_override(
    hass: HomeAssistant, stored: dict, expected: str
) -> None:
    entry = _entry(
        hass,
        {CONF_ADDRESS: "AA:BB:CC:DD:EE:20", CONF_BED_TYPE: BED_TYPE_OCTO, **stored},
        version=5,
        minor_version=3,
    )

    await async_migrate_entry(hass, entry)

    assert (entry.version, entry.minor_version) == (5, 8)
    assert entry.data[CONF_OCTO_MOTOR_COUNT_OVERRIDE] == expected
    assert entry.data[CONF_PROFILE_MIGRATION]["octo_motor_count_override"] == ["data"]


async def test_schema_5_5_keeps_a_chosen_override_and_other_beds(hass: HomeAssistant) -> None:
    octo = _entry(
        hass,
        {
            CONF_ADDRESS: "AA:BB:CC:DD:EE:21",
            CONF_BED_TYPE: BED_TYPE_OCTO,
            CONF_MOTOR_COUNT: 1,
            CONF_OCTO_MOTOR_COUNT_OVERRIDE: "auto",
        },
        version=5,
        minor_version=3,
    )
    other = _entry(
        hass,
        {CONF_ADDRESS: "AA:BB:CC:DD:EE:22", CONF_BED_TYPE: BED_TYPE_LINAK, CONF_MOTOR_COUNT: 3},
        version=5,
        minor_version=3,
    )

    await async_migrate_entry(hass, octo)
    await async_migrate_entry(hass, other)

    assert octo.data[CONF_OCTO_MOTOR_COUNT_OVERRIDE] == "auto"
    assert CONF_OCTO_MOTOR_COUNT_OVERRIDE not in other.data
    assert CONF_PROFILE_MIGRATION not in octo.data
    assert CONF_PROFILE_MIGRATION not in other.data


async def test_schema_5_5_writes_each_octo_side_and_its_original(hass: HomeAssistant) -> None:
    # The left side inherits the pair's one-motor count; the right side has its own.
    left = {
        CONF_SIDE: "left",
        CONF_ADDRESS: "AA:BB:CC:DD:EE:23",
        CONF_BED_TYPE: BED_TYPE_OCTO,
        KEY_ORIGIN_DATA: {CONF_BED_TYPE: BED_TYPE_OCTO, CONF_MOTOR_COUNT: 3},
    }
    right = {
        CONF_SIDE: "right",
        CONF_ADDRESS: "AA:BB:CC:DD:EE:24",
        CONF_BED_TYPE: BED_TYPE_OCTO,
        CONF_MOTOR_COUNT: 2,
    }
    entry = _entry(
        hass,
        {
            CONF_PAIR_ID: "pair_5",
            CONF_BED_TYPE: BED_TYPE_OCTO,
            CONF_MOTOR_COUNT: 1,
            CONF_PAIR_CHILDREN: [left, right],
        },
        version=5,
        minor_version=3,
    )

    await async_migrate_entry(hass, entry)

    migrated_left, migrated_right = entry.data[CONF_PAIR_CHILDREN]
    assert migrated_left[CONF_OCTO_MOTOR_COUNT_OVERRIDE] == "1"
    assert migrated_left[KEY_ORIGIN_DATA][CONF_OCTO_MOTOR_COUNT_OVERRIDE] == "3"
    assert migrated_right[CONF_OCTO_MOTOR_COUNT_OVERRIDE] == "auto"
    assert entry.data[CONF_PROFILE_MIGRATION]["octo_motor_count_override"] == [
        "data.left",
        "data.left.origin_data",
        "data.right",
    ]


@pytest.mark.parametrize(
    ("stored", "expected"),
    [
        ({"disconnect_after_command": True, "idle_disconnect_seconds": 60},
         {CONF_CONNECTION_MODE: CONNECTION_MODE_RELEASE, "idle_disconnect_seconds": 60}),
        ({"disconnect_after_command": False, "idle_disconnect_seconds": 0},
         {CONF_CONNECTION_MODE: CONNECTION_MODE_ALWAYS}),
        # A timeout of 0 kept a bed connected only with the handoff off.
        ({"disconnect_after_command": True, "idle_disconnect_seconds": 0},
         {CONF_CONNECTION_MODE: CONNECTION_MODE_RELEASE}),
        ({"disconnect_after_command": False, "idle_disconnect_seconds": 60},
         {CONF_CONNECTION_MODE: CONNECTION_MODE_IDLE, "idle_disconnect_seconds": 60}),
        # A v5 beta ran an entry without a saved handoff with its bed type's
        # default, and a Linak hands its link back, which a 0 timeout never
        # overrode. 4.x entries save 4.x's own default (no handoff) first.
        ({"idle_disconnect_seconds": 0}, {}),
        # Nothing chosen: the bed type's default still applies.
        ({"idle_disconnect_seconds": 40}, {"idle_disconnect_seconds": 40}),
        ({"position_mode": "accuracy", "connection_profile": "reliable"}, {}),
    ],
)
def test_schema_5_6_rewrites_the_connection_settings(stored: dict, expected: dict) -> None:
    base = {
        CONF_ADDRESS: "AA:BB:CC:DD:EE:30",
        CONF_BED_TYPE: BED_TYPE_LINAK,
        CONF_DISABLE_ANGLE_SENSING: True,
    }

    data, _options = migrate_v5_6_entry(
        {**base, **stored}, {}, from_version=5, from_minor_version=5
    )

    record = data.pop(CONF_PROFILE_MIGRATION, None)
    assert data == {**base, **expected}
    if stored != expected:
        assert set(record["settings_5_6"]) == {"data"}
    else:
        assert record is None


@pytest.mark.parametrize(
    ("bed_type", "disabled", "kept"),
    [
        # A bed without position feedback stores nothing.
        (BED_TYPE_JIECANG_APP, True, False),
        (BED_TYPE_LINAK, False, False),
        (BED_TYPE_LINAK, True, True),
        # A choice against the route's default stays.
        (BED_TYPE_KEESON, False, True),
    ],
)
def test_schema_5_6_keeps_only_a_position_choice_against_the_route(
    bed_type: str, disabled: bool, kept: bool
) -> None:
    data = {CONF_ADDRESS: "AA:BB:CC:DD:EE:31", CONF_BED_TYPE: bed_type, CONF_DISABLE_ANGLE_SENSING: disabled}

    migrated, _options = migrate_v5_6_entry(data, {}, from_version=5, from_minor_version=5)

    assert (CONF_DISABLE_ANGLE_SENSING in migrated) is kept
    if kept:
        assert migrated[CONF_DISABLE_ANGLE_SENSING] is disabled


def test_schema_5_6_keeps_a_zero_timeout_where_the_bed_kept_its_link() -> None:
    """A bed whose default kept the link between commands now stays connected."""
    data = {CONF_ADDRESS: "AA:BB:CC:DD:EE:36", CONF_BED_TYPE: BED_TYPE_KEESON, "idle_disconnect_seconds": 0}

    migrated, _options = migrate_v5_6_entry(data, {}, from_version=5, from_minor_version=5)

    assert migrated[CONF_CONNECTION_MODE] == CONNECTION_MODE_ALWAYS


def test_schema_5_6_options_follow_the_data_they_inherit_from() -> None:
    """A 0 timeout in options never overrode a handoff saved in data."""
    data = {CONF_ADDRESS: "AA:BB:CC:DD:EE:37", CONF_BED_TYPE: BED_TYPE_KEESON, "disconnect_after_command": True}

    migrated, options = migrate_v5_6_entry(
        data, {"idle_disconnect_seconds": 0}, from_version=5, from_minor_version=5
    )

    assert migrated[CONF_CONNECTION_MODE] == CONNECTION_MODE_RELEASE
    # Read over the data, the option still releases the link.
    assert options == {CONF_CONNECTION_MODE: CONNECTION_MODE_RELEASE}


def test_schema_5_6_options_and_data_read_as_one() -> None:
    """A 0 in data under a 65 s option meant a 65 s timeout, and still does."""
    data = {CONF_ADDRESS: "AA:BB:CC:DD:EE:42", CONF_BED_TYPE: BED_TYPE_KEESON, "idle_disconnect_seconds": 0}

    migrated, options = migrate_v5_6_entry(
        data, {"idle_disconnect_seconds": 65}, from_version=5, from_minor_version=5
    )

    assert migrated[CONF_CONNECTION_MODE] == CONNECTION_MODE_ALWAYS
    merged = {**migrated, **options}
    assert merged[CONF_CONNECTION_MODE] == CONNECTION_MODE_IDLE
    assert merged["idle_disconnect_seconds"] == 65


def test_schema_5_6_keeps_an_angle_option_that_hides_the_opposite_data_value() -> None:
    data = {CONF_ADDRESS: "AA:BB:CC:DD:EE:43", CONF_BED_TYPE: BED_TYPE_LINAK, CONF_DISABLE_ANGLE_SENSING: True}

    _migrated, options = migrate_v5_6_entry(
        data, {CONF_DISABLE_ANGLE_SENSING: False}, from_version=5, from_minor_version=5
    )

    assert options == {CONF_DISABLE_ANGLE_SENSING: False}


def test_schema_5_6_rewrites_each_paired_side_against_its_own_route() -> None:
    """A side takes the shared values it inherited, then follows its own route."""
    left = {
        CONF_SIDE: "left",
        CONF_ADDRESS: "AA:BB:CC:DD:EE:32",
        CONF_BED_TYPE: BED_TYPE_LINAK,
        KEY_ORIGIN_DATA: {
            CONF_BED_TYPE: BED_TYPE_LINAK,
            "disconnect_after_command": False,
            "idle_disconnect_seconds": 0,
        },
    }
    right = {
        CONF_SIDE: "right",
        CONF_ADDRESS: "AA:BB:CC:DD:EE:33",
        CONF_BED_TYPE: BED_TYPE_LINAK,
        "disconnect_after_command": False,
        CONF_DISABLE_ANGLE_SENSING: False,
    }
    data = {
        CONF_PAIR_ID: "pair_56",
        CONF_BED_TYPE: BED_TYPE_LINAK,
        "disconnect_after_command": True,
        CONF_DISABLE_ANGLE_SENSING: True,
        CONF_PAIR_CONNECTION_MODE: "sequential",
        CONF_PAIR_CHILDREN: [left, right],
    }

    migrated, _options = migrate_v5_6_entry(data, {}, from_version=5, from_minor_version=5)

    new_left, new_right = migrated[CONF_PAIR_CHILDREN]
    assert CONF_PAIR_CONNECTION_MODE not in migrated
    assert migrated[CONF_CONNECTION_MODE] == CONNECTION_MODE_RELEASE
    # The left side inherited the parent's handoff and angle choice.
    assert new_left[CONF_CONNECTION_MODE] == CONNECTION_MODE_RELEASE
    assert new_left[CONF_DISABLE_ANGLE_SENSING] is True
    assert new_left[KEY_ORIGIN_DATA] == {
        CONF_BED_TYPE: BED_TYPE_LINAK,
        CONF_CONNECTION_MODE: CONNECTION_MODE_ALWAYS,
    }
    # The right side kept its own choices; a side's angle choice stays as saved.
    assert new_right[CONF_CONNECTION_MODE] == CONNECTION_MODE_IDLE
    assert new_right[CONF_DISABLE_ANGLE_SENSING] is False
    assert "disconnect_after_command" not in str(migrated)
    assert set(migrated[CONF_PROFILE_MIGRATION]["settings_5_6"]) >= {
        "data",
        "data.left",
        "data.left.origin_data",
        "data.right",
    }


async def test_a_5_5_entry_moves_to_5_6(hass: HomeAssistant) -> None:
    data = {
        CONF_ADDRESS: "AA:BB:CC:DD:EE:34",
        CONF_NAME: "Bed",
        CONF_BED_TYPE: BED_TYPE_LINAK,
        CONF_PROFILE_ID: BED_TYPE_LINAK,
        "disconnect_after_command": True,
        "connection_profile": "balanced",
    }
    entry = _entry(hass, dict(data), version=5, minor_version=5)

    await async_migrate_entry(hass, entry)

    assert (entry.version, entry.minor_version) == (5, 8)
    assert entry.data[CONF_CONNECTION_MODE] == CONNECTION_MODE_RELEASE
    assert "connection_profile" not in entry.data
    assert entry.data[CONF_PROFILE_MIGRATION]["settings_5_6"]["data"] == [
        "connection_profile",
        f"{CONF_CONNECTION_MODE}={CONNECTION_MODE_RELEASE}",
    ]


def test_schema_5_6_a_shared_timeout_wins_over_a_sides_zero() -> None:
    """A side's 0 under a shared 65 s timeout disconnected after 65 s, and still does."""
    data = {
        CONF_PAIR_ID: "pair_65",
        CONF_BED_TYPE: BED_TYPE_KEESON,
        # The parent's own 0 becomes Always, which the side never ran with.
        "idle_disconnect_seconds": 0,
        CONF_PAIR_CHILDREN: [
            {
                CONF_SIDE: "left",
                CONF_ADDRESS: "AA:BB:CC:DD:EE:40",
                CONF_BED_TYPE: BED_TYPE_KEESON,
                "idle_disconnect_seconds": 0,
            },
        ],
    }

    migrated, options = migrate_v5_6_entry(
        data, {"idle_disconnect_seconds": 65}, from_version=5, from_minor_version=5
    )

    assert options == {}
    effective = effective_child_data(migrated, "left", options)
    assert effective[CONF_CONNECTION_MODE] == CONNECTION_MODE_IDLE
    assert effective["idle_disconnect_seconds"] == 65


def test_schema_5_6_a_side_that_released_its_link_keeps_releasing() -> None:
    """A side whose bed type handed the link back never followed a parent's 0."""
    data = {
        CONF_PAIR_ID: "pair_ffe",
        CONF_BED_TYPE: BED_TYPE_KEESON,
        "idle_disconnect_seconds": 0,
        CONF_PAIR_CHILDREN: [
            {CONF_SIDE: "left", CONF_ADDRESS: "AA:BB:CC:DD:EE:41", CONF_BED_TYPE: "okin_ffe"},
        ],
    }

    migrated, options = migrate_v5_6_entry(data, {}, from_version=5, from_minor_version=5)

    assert migrated[CONF_CONNECTION_MODE] == CONNECTION_MODE_ALWAYS
    effective = effective_child_data(migrated, "left", options)
    assert effective[CONF_CONNECTION_MODE] == CONNECTION_MODE_RELEASE


def test_schema_5_6_applies_pair_options_to_each_side_first() -> None:
    """A pair's options win over its sides, so each side's mode is derived with them."""
    data = {
        CONF_PAIR_ID: "pair_opts",
        CONF_BED_TYPE: BED_TYPE_KEESON,
        "disconnect_after_command": True,
        CONF_PAIR_CHILDREN: [
            {CONF_SIDE: "left", CONF_ADDRESS: "AA:BB:CC:DD:EE:38", CONF_BED_TYPE: BED_TYPE_KEESON},
            {
                CONF_SIDE: "right",
                CONF_ADDRESS: "AA:BB:CC:DD:EE:39",
                CONF_BED_TYPE: BED_TYPE_KEESON,
                "disconnect_after_command": False,
            },
        ],
    }

    migrated, options = migrate_v5_6_entry(
        data, {"idle_disconnect_seconds": 0}, from_version=5, from_minor_version=5
    )

    left, right = migrated[CONF_PAIR_CHILDREN]
    assert left[CONF_CONNECTION_MODE] == CONNECTION_MODE_RELEASE
    assert right[CONF_CONNECTION_MODE] == CONNECTION_MODE_ALWAYS
    assert options == {}


def test_schema_5_6_a_side_follows_the_pairs_route_option() -> None:
    """A side read the pair's route option, so its saved mode is that route's."""
    data = {
        CONF_PAIR_ID: "pair_ksbt",
        CONF_BED_TYPE: BED_TYPE_KEESON,
        CONF_PAIR_CHILDREN: [
            {
                CONF_SIDE: "left",
                CONF_ADDRESS: "AA:BB:CC:DD:EE:44",
                CONF_BED_TYPE: BED_TYPE_KEESON,
                CONF_PROTOCOL_VARIANT: "auto",
                "idle_disconnect_seconds": 40,
            },
        ],
    }

    migrated, options = migrate_v5_6_entry(
        data, {CONF_PROTOCOL_VARIANT: "ksbt"}, from_version=5, from_minor_version=5
    )

    effective = effective_child_data(migrated, "left", options)
    assert effective[CONF_CONNECTION_MODE] == CONNECTION_MODE_RELEASE


_CB24 = "okin_cb24"


@pytest.mark.parametrize(
    ("stored", "expected"),
    [
        pytest.param({}, {}, id="automatic stays automatic"),
        pytest.param(
            {CONF_PROTOCOL_VARIANT: "cb_old"}, {CONF_PROTOCOL_VARIANT: "cb24"}, id="older box"
        ),
        pytest.param(
            {CONF_PROTOCOL_VARIANT: "dacheng"},
            {CONF_PROTOCOL_VARIANT: "cb24"},
            id="dacheng sent the cb24 frames",
        ),
        pytest.param(
            {CONF_PROTOCOL_VARIANT: "cb_new"}, {CONF_PROTOCOL_VARIANT: "cb27new"}, id="newer box"
        ),
        pytest.param(
            {CONF_PROTOCOL_VARIANT: "cb27"}, {CONF_PROTOCOL_VARIANT: "cb27"}, id="cb27 keeps its name"
        ),
        pytest.param(
            {"cb24_bed_selection": 0xAA},
            {CONF_PROTOCOL_VARIANT: "cb24_ab", "cb24_bed_selection": 0xAA},
            id="a side makes it cb24ab",
        ),
        pytest.param(
            {CONF_PROTOCOL_VARIANT: "cb27new", "cb24_bed_selection": 0xBB},
            {CONF_PROTOCOL_VARIANT: "cb27new", "cb24_bed_selection": 0},
            id="cbnew never sent its side",
        ),
        pytest.param(
            {CONF_PROTOCOL_VARIANT: "cb1221", CONF_MOTOR_COUNT: 4, CONF_HAS_MASSAGE: True},
            {CONF_PROTOCOL_VARIANT: "cb1221", CONF_MOTOR_COUNT: 2, CONF_HAS_MASSAGE: False},
            id="settings the app profile decides",
        ),
    ],
)
def test_schema_5_7_saves_an_okin_cb24_bed_as_smartbed(stored: dict, expected: dict) -> None:
    from custom_components.adjustable_bed import migrate_v5_7_entry

    base = {CONF_ADDRESS: "AA:BB:CC:DD:EE:57", CONF_NAME: "Bed"}
    data, options = migrate_v5_7_entry(
        {**base, CONF_BED_TYPE: _CB24, **stored}, {}, from_version=5, from_minor_version=6
    )

    assert data.pop(CONF_PROFILE_MIGRATION)["smartbed"] == ["data"]
    assert data == {**base, CONF_BED_TYPE: "smartbed", **expected}
    assert options == {}


def test_schema_5_7_takes_the_receiver_from_the_data_a_bed_reads() -> None:
    from custom_components.adjustable_bed import migrate_v5_7_entry

    # A standalone bed never read its options, so they do not pick its receiver.
    data, options = migrate_v5_7_entry(
        {CONF_BED_TYPE: _CB24, "cb24_bed_selection": 0xAA},
        {CONF_PROTOCOL_VARIANT: "cb_new", "cb24_bed_selection": 0xBB, CONF_MOTOR_COUNT: 3},
        from_version=5,
        from_minor_version=6,
    )
    assert (data[CONF_PROTOCOL_VARIANT], data["cb24_bed_selection"]) == ("cb24_ab", 0xAA)
    # The legacy names leave the options too.
    assert options == {CONF_PROTOCOL_VARIANT: "cb27new", "cb24_bed_selection": 0, CONF_MOTOR_COUNT: 2}

    other = {CONF_BED_TYPE: BED_TYPE_LINAK, CONF_PROTOCOL_VARIANT: "auto"}
    assert migrate_v5_7_entry(other, {}, from_version=5, from_minor_version=6) == (other, {})


def test_schema_5_7_writes_a_one_address_pair_and_what_it_restores() -> None:
    from custom_components.adjustable_bed import migrate_v5_7_entry
    from custom_components.adjustable_bed.const import (
        CONF_PAIR_MODE,
        CONF_PROFILE_REVIEW_PENDING,
        PAIR_MODE_SINGLE_ADDRESS,
    )

    address = "AA:BB:CC:DD:EE:58"
    original = {
        CONF_ADDRESS: address,
        CONF_BED_TYPE: _CB24,
        CONF_PROTOCOL_VARIANT: "cb_old",
        CONF_PROFILE_REVIEW_PENDING: "okin_cb24:cb_old",
    }
    data, _options = migrate_v5_7_entry(
        {
            CONF_ADDRESS: address,
            CONF_BED_TYPE: _CB24,
            CONF_PAIR_ID: "pair_one",
            CONF_PAIR_MODE: PAIR_MODE_SINGLE_ADDRESS,
            CONF_PROFILE_REVIEW_PENDING: "okin_cb24:auto|okin_cb24:auto",
            CONF_PAIR_CHILDREN: [
                {
                    CONF_SIDE: side,
                    CONF_ADDRESS: address,
                    "cb24_bed_selection": selector,
                    KEY_ORIGIN_DATA: dict(original),
                    KEY_ORIGIN_OPTIONS: {CONF_MOTOR_COUNT: 2},
                }
                for side, selector in (("left", 0xAA), ("right", 0xBB))
            ],
        },
        {},
        from_version=5,
        from_minor_version=6,
    )

    # The bed sent a side on every frame, which only the CB24AB receiver does.
    assert (data[CONF_BED_TYPE], data[CONF_PROTOCOL_VARIANT]) == ("smartbed", "cb24_ab")
    left, right = data[CONF_PAIR_CHILDREN]
    assert (left["cb24_bed_selection"], right["cb24_bed_selection"]) == (0xAA, 0xBB)
    # Each side stores its own receiver, as a SmartBed side does.
    assert (left[CONF_BED_TYPE], left[CONF_PROTOCOL_VARIANT]) == ("smartbed", "cb24_ab")
    assert left[KEY_ORIGIN_DATA] == {
        **original,
        CONF_BED_TYPE: "smartbed",
        CONF_PROTOCOL_VARIANT: "cb24",
        CONF_PROFILE_REVIEW_PENDING: "smartbed:cb24",
    }
    assert left[KEY_ORIGIN_OPTIONS] == {CONF_MOTOR_COUNT: 2}
    # The open app review follows the renamed route, on the pair and its originals.
    assert data[CONF_PROFILE_REVIEW_PENDING] == "smartbed:cb24_ab|smartbed:cb24_ab"
    assert data[CONF_PROFILE_MIGRATION]["smartbed"] == [
        "data",
        "data.left",
        f"data.left.{KEY_ORIGIN_DATA}",
        "data.right",
        f"data.right.{KEY_ORIGIN_DATA}",
    ]


def test_schema_5_7_stores_on_each_side_what_it_ran_with() -> None:
    """A two-address side read the pair's options; SmartBed's settings are its own."""
    from custom_components.adjustable_bed import migrate_v5_7_entry
    from custom_components.adjustable_bed.pairing import effective_child_data

    data, options = migrate_v5_7_entry(
        {
            CONF_BED_TYPE: _CB24,
            CONF_PAIR_ID: "pair_two",
            CONF_MOTOR_COUNT: 4,
            CONF_PAIR_CHILDREN: [
                {CONF_SIDE: "left", CONF_ADDRESS: "AA:BB:CC:DD:EE:01"},
                {CONF_SIDE: "right", CONF_ADDRESS: "AA:BB:CC:DD:EE:02", CONF_BED_TYPE: _CB24},
            ],
        },
        {CONF_PROTOCOL_VARIANT: "cb1221"},
        from_version=5,
        from_minor_version=6,
    )

    for side in ("left", "right"):
        view = effective_child_data(data, side, options)
        assert (view[CONF_BED_TYPE], view[CONF_PROTOCOL_VARIANT]) == ("smartbed", "cb1221")
        assert view[CONF_MOTOR_COUNT] == 2


def test_an_older_okin_cb24_entry_keeps_its_link_through_the_5_6_step() -> None:
    """The 5.6 step still reads the retired route's default: 0 kept the bed connected."""
    from custom_components.adjustable_bed import migrate_v5_6_entry, migrate_v5_7_entry

    data, options = migrate_v5_6_entry(
        {CONF_BED_TYPE: _CB24, "idle_disconnect_seconds": 0},
        {},
        from_version=5,
        from_minor_version=5,
    )
    data, _options = migrate_v5_7_entry(data, options, from_version=5, from_minor_version=5)

    assert data[CONF_BED_TYPE] == "smartbed"
    assert data[CONF_CONNECTION_MODE] == CONNECTION_MODE_ALWAYS


async def test_schema_5_7_keeps_back_and_legs_over_their_duplicates(hass: HomeAssistant) -> None:
    """A count of three or four added Head and Feet covers that sent the same commands."""
    from homeassistant.helpers import entity_registry as er

    address = "AA:BB:CC:DD:EE:59"
    entry = _entry(
        hass,
        {CONF_ADDRESS: address, CONF_NAME: "Bed", CONF_BED_TYPE: _CB24, CONF_MOTOR_COUNT: 4},
        version=5,
        minor_version=6,
    )
    registry = er.async_get(hass)
    rows = {
        key: registry.async_get_or_create(domain, DOMAIN, f"{address}_{key}", config_entry=entry)
        for domain, key in (
            ("cover", "back"),
            ("cover", "head"),
            ("cover", "legs"),
            ("cover", "feet"),
            ("button", "back_up_both"),
            ("button", "legs_down_both"),
        )
    }

    await async_migrate_entry(hass, entry)

    assert entry.data[CONF_MOTOR_COUNT] == 2
    assert registry.async_get(rows["back"].entity_id).unique_id == f"{address}_head"
    assert registry.async_get(rows["legs"].entity_id).unique_id == f"{address}_feet"
    assert registry.async_get(rows["head"].entity_id) is None
    assert registry.async_get(rows["feet"].entity_id) is None
    # A pair's own movement buttons follow the covers.
    assert registry.async_get(rows["back_up_both"].entity_id).unique_id == f"{address}_head_up_both"
    assert registry.async_get(rows["legs_down_both"].entity_id).unique_id == f"{address}_feet_down_both"


async def test_a_5_6_okin_cb24_bed_loads_as_smartbed_with_its_entity_ids(
    hass: HomeAssistant,
    mock_bleak_client,
    mock_coordinator_connected,
    enable_custom_integrations,
) -> None:
    """The covers and wave button the app names differently keep their entity IDs."""
    from homeassistant.config_entries import ConfigEntryState
    from homeassistant.helpers import entity_registry as er

    from custom_components.adjustable_bed.beds.smartbed.controller import SmartBedController
    from custom_components.adjustable_bed.profiles.smartbed import NORDIC
    from custom_components.adjustable_bed.runtime_data import loaded_runtime

    class Gatt:
        def __init__(self, **fields) -> None:
            self.__dict__.update(fields)

    notify = Gatt(uuid=NORDIC[3], properties=("notify",), handle=2, descriptors=[])
    write = Gatt(
        uuid=NORDIC[1], properties=("write", "write-without-response"), handle=1, descriptors=[]
    )
    mock_bleak_client.services = [Gatt(uuid=NORDIC[0], characteristics=[write, notify])]

    address = "AA:BB:CC:DD:EE:FF"
    entry = _entry(
        hass,
        {CONF_ADDRESS: address, CONF_NAME: "Bed", CONF_BED_TYPE: _CB24, CONF_MOTOR_COUNT: 2},
        version=5,
        minor_version=6,
    )
    entry_unique = {"unique_id": address}
    hass.config_entries.async_update_entry(entry, **entry_unique)
    registry = er.async_get(hass)
    kept = {
        new: registry.async_get_or_create(domain, DOMAIN, f"{address}_{old}", config_entry=entry)
        for domain, old, new in (
            ("cover", "back", "head"),
            ("cover", "legs", "feet"),
            ("button", "massage_mode_step", "smartbed_wave_up"),
            ("button", "preset_lounge", "preset_lounge"),
            ("button", "massage_all_up", "massage_all_up"),
        )
    }

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    assert (entry.version, entry.minor_version) == (5, 8)
    assert entry.data[CONF_BED_TYPE] == "smartbed"
    runtime = loaded_runtime(hass, entry.entry_id)
    assert runtime is not None and type(runtime.controller) is SmartBedController
    for key, row in kept.items():
        assert registry.async_get(row.entity_id).unique_id == f"{address}_{key}"
        assert hass.states.get(row.entity_id) is not None


@pytest.mark.parametrize(
    ("retired", "route"),
    [
        ("okimat", "okin_uuid"),
        ("dewertokin", "okin_handle"),
        ("nectar", "okin_7byte"),
        ("mattressfirm", "okin_nordic"),
    ],
)
def test_schema_5_8_saves_a_brand_bed_type_as_its_route(retired: str, route: str) -> None:
    from custom_components.adjustable_bed import migrate_v5_8_entry
    from custom_components.adjustable_bed.const import (
        CONF_PROFILE_REVIEW_KEPT,
        CONF_PROFILE_REVIEW_PENDING,
    )

    settings = {CONF_ADDRESS: "AA:BB:CC:DD:EE:60", CONF_MOTOR_COUNT: 3, CONF_PROTOCOL_VARIANT: "auto"}
    kept = {"route": f"{retired}:auto", "apps": ["resident"]}
    data, options = migrate_v5_8_entry(
        {
            **settings,
            CONF_BED_TYPE: retired,
            CONF_PAIR_ID: "pair_brand",
            CONF_PROFILE_REVIEW_PENDING: f"{retired}:auto|{retired}:auto",
            CONF_PAIR_CHILDREN: [
                {
                    CONF_SIDE: side,
                    CONF_ADDRESS: address,
                    **own,
                    KEY_ORIGIN_DATA: {
                        CONF_ADDRESS: address,
                        CONF_BED_TYPE: retired,
                        CONF_PROFILE_REVIEW_KEPT: dict(kept),
                    },
                }
                for side, address, own in (
                    ("left", "AA:BB:CC:DD:EE:61", {}),
                    ("right", "AA:BB:CC:DD:EE:62", {CONF_BED_TYPE: retired}),
                )
            ],
        },
        {CONF_MOTOR_COUNT: 2, CONF_BED_TYPE: retired},
        from_version=5,
        from_minor_version=7,
    )

    # Only the name of the route changes; every setting stays.
    assert {key: data[key] for key in settings} == settings
    assert options == {CONF_MOTOR_COUNT: 2, CONF_BED_TYPE: route}
    assert data[CONF_BED_TYPE] == route
    left, right = data[CONF_PAIR_CHILDREN]
    assert CONF_BED_TYPE not in left and right[CONF_BED_TYPE] == route
    for child in (left, right):
        assert child[KEY_ORIGIN_DATA][CONF_BED_TYPE] == route
        # The Keep a bed answered before it was combined follows it too.
        assert child[KEY_ORIGIN_DATA][CONF_PROFILE_REVIEW_KEPT] == {**kept, "route": f"{route}:auto"}
    assert data[CONF_PROFILE_REVIEW_PENDING] == f"{route}:auto|{route}:auto"
    assert data[CONF_PROFILE_MIGRATION]["renamed_bed_types"] == {
        "data": retired,
        "options": retired,
        f"data.left.{KEY_ORIGIN_DATA}": retired,
        "data.right": retired,
        f"data.right.{KEY_ORIGIN_DATA}": retired,
    }


def test_schema_5_8_leaves_every_other_entry_as_it_is() -> None:
    from custom_components.adjustable_bed import migrate_v5_8_entry

    data = {CONF_BED_TYPE: BED_TYPE_LINAK, CONF_PROTOCOL_VARIANT: "auto"}
    assert migrate_v5_8_entry(data, {}, from_version=5, from_minor_version=7) == (data, {})


async def test_a_4x_okimat_entry_keeps_its_review_and_takes_its_routes_id(hass: HomeAssistant) -> None:
    """The steps before 5.8 still read a brand id: its app review is not lost."""
    from custom_components.adjustable_bed.const import CONF_PROFILE_REVIEW_PENDING

    entry = _entry(hass, {CONF_ADDRESS: "AA:BB:CC:DD:EE:63", CONF_NAME: "Bed", CONF_BED_TYPE: "okimat"})

    await async_migrate_entry(hass, entry)

    assert entry.data[CONF_BED_TYPE] == "okin_uuid"
    assert entry.data[CONF_PROFILE_ID] == "okin_uuid"
    assert entry.data[CONF_PROFILE_REVIEW_PENDING] == "okin_uuid:auto"
