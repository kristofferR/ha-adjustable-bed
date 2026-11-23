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
    BED_TYPE_STARCODE_M1X12,
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

    assert (entry.version, entry.minor_version) == (5, 11)
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

    assert (entry.version, entry.minor_version) == (5, 11)
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

    assert (entry.version, entry.minor_version) == (5, 11)
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

    assert (entry.version, entry.minor_version) == (5, 11)
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

    assert (entry.version, entry.minor_version) == (5, 11)
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

    assert (entry.version, entry.minor_version) == (5, 11)
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

    assert (entry.version, entry.minor_version) == (5, 11)
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

    assert (entry.version, entry.minor_version) == (5, 11)
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
        # M1X12's setup saved "off" itself before its positions were read.
        (BED_TYPE_STARCODE_M1X12, True, False),
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

    assert (entry.version, entry.minor_version) == (5, 11)
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
    assert (entry.version, entry.minor_version) == (5, 11)
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


_SBI = "sbi"


@pytest.mark.parametrize(
    ("stored", "expected"),
    [
        # Unset and automatic build Both on the app route too, so they stay as stored.
        pytest.param({}, {}, id="no selection"),
        pytest.param(
            {CONF_PROTOCOL_VARIANT: "auto"}, {CONF_PROTOCOL_VARIANT: "auto"}, id="automatic"
        ),
        pytest.param(
            {CONF_PROTOCOL_VARIANT: "side_a"}, {CONF_PROTOCOL_VARIANT: "side_a"}, id="side a"
        ),
        pytest.param(
            {CONF_PROTOCOL_VARIANT: "side_b"}, {CONF_PROTOCOL_VARIANT: "side_b"}, id="side b"
        ),
        pytest.param(
            {CONF_MOTOR_COUNT: 4, CONF_HAS_MASSAGE: True},
            {CONF_MOTOR_COUNT: 2, CONF_HAS_MASSAGE: False},
            id="settings the app layout decides",
        ),
        pytest.param(
            {CONF_DISABLE_ANGLE_SENSING: True},
            {CONF_DISABLE_ANGLE_SENSING: True},
            id="positions stay unread",
        ),
    ],
)
def test_schema_5_9_saves_an_sbi_bed_as_the_qplus_app(stored: dict, expected: dict) -> None:
    from custom_components.adjustable_bed import migrate_v5_9_entry

    base = {CONF_ADDRESS: "AA:BB:CC:DD:EE:70", CONF_NAME: "Bed"}
    data, options = migrate_v5_9_entry(
        {**base, CONF_BED_TYPE: _SBI, **stored}, {}, from_version=5, from_minor_version=8
    )

    assert data.pop(CONF_PROFILE_MIGRATION)["qplus_app"] == ["data"]
    # The H layout has the keys the sbi route sent.
    assert data == {**base, CONF_BED_TYPE: "qplus_app", "product_type": "H", **expected}
    assert options == {}


def test_schema_5_9_takes_the_selection_from_the_data_a_bed_reads() -> None:
    from custom_components.adjustable_bed import migrate_v5_9_entry

    # A standalone bed never read its options, so they do not pick its selection.
    data, options = migrate_v5_9_entry(
        {CONF_BED_TYPE: _SBI, CONF_PROTOCOL_VARIANT: "side_a"},
        {CONF_BED_TYPE: _SBI, CONF_PROTOCOL_VARIANT: "side_b", CONF_MOTOR_COUNT: 4},
        from_version=5,
        from_minor_version=8,
    )
    assert (data[CONF_PROTOCOL_VARIANT], data["product_type"]) == ("side_a", "H")
    # Only the old name leaves the options.
    assert options == {
        CONF_BED_TYPE: "qplus_app",
        CONF_PROTOCOL_VARIANT: "side_b",
        CONF_MOTOR_COUNT: 4,
    }

    other = {CONF_BED_TYPE: "rondure", CONF_PROTOCOL_VARIANT: "side_a"}
    assert migrate_v5_9_entry(other, {}, from_version=5, from_minor_version=8) == (other, {})


def test_schema_5_9_writes_a_one_address_pair_and_what_it_restores() -> None:
    from custom_components.adjustable_bed import migrate_v5_9_entry
    from custom_components.adjustable_bed.const import (
        CONF_PAIR_MODE,
        CONF_PROFILE_REVIEW_PENDING,
        PAIR_MODE_SINGLE_ADDRESS,
    )

    address = "AA:BB:CC:DD:EE:71"
    original = {
        CONF_ADDRESS: address,
        CONF_BED_TYPE: _SBI,
        CONF_PROTOCOL_VARIANT: "side_b",
        CONF_PROFILE_REVIEW_PENDING: "sbi:side_b",
    }
    data, _options = migrate_v5_9_entry(
        {
            CONF_ADDRESS: address,
            CONF_BED_TYPE: _SBI,
            CONF_PROTOCOL_VARIANT: "both",
            CONF_PAIR_ID: "pair_one",
            CONF_PAIR_MODE: PAIR_MODE_SINGLE_ADDRESS,
            CONF_PROFILE_REVIEW_PENDING: "sbi:side_a|sbi:side_b",
            CONF_PAIR_CHILDREN: [
                {
                    CONF_SIDE: side,
                    CONF_ADDRESS: address,
                    CONF_BED_TYPE: _SBI,
                    CONF_PROTOCOL_VARIANT: selection,
                    KEY_ORIGIN_DATA: dict(original),
                    KEY_ORIGIN_OPTIONS: {CONF_MOTOR_COUNT: 4},
                }
                for side, selection in (("left", "side_a"), ("right", "side_b"))
            ],
        },
        # A one-address side keeps its A or B whatever the pair's options say.
        {CONF_PROTOCOL_VARIANT: "both"},
        from_version=5,
        from_minor_version=8,
    )

    assert (data[CONF_BED_TYPE], data[CONF_PROTOCOL_VARIANT], data["product_type"]) == (
        "qplus_app",
        "both",
        "H",
    )
    left, right = data[CONF_PAIR_CHILDREN]
    assert [(side[CONF_BED_TYPE], side[CONF_PROTOCOL_VARIANT]) for side in (left, right)] == [
        ("qplus_app", "side_a"),
        ("qplus_app", "side_b"),
    ]
    assert left[KEY_ORIGIN_DATA] == {
        **original,
        CONF_BED_TYPE: "qplus_app",
        "product_type": "H",
        CONF_PROFILE_REVIEW_PENDING: "qplus_app:side_b",
    }
    assert left[KEY_ORIGIN_OPTIONS] == {CONF_MOTOR_COUNT: 4}
    # The open app review follows the renamed route, on the pair and its originals.
    assert data[CONF_PROFILE_REVIEW_PENDING] == "qplus_app:side_a|qplus_app:side_b"
    assert data[CONF_PROFILE_MIGRATION]["qplus_app"] == [
        "data",
        "data.left",
        f"data.left.{KEY_ORIGIN_DATA}",
        "data.right",
        f"data.right.{KEY_ORIGIN_DATA}",
    ]


def test_schema_5_9_stores_on_each_side_what_it_ran_with() -> None:
    """A two-address side read the pair's options; the app's settings are its own."""
    from custom_components.adjustable_bed import migrate_v5_9_entry

    shared = {CONF_PROTOCOL_VARIANT: "side_b", CONF_MOTOR_COUNT: 4}
    data, options = migrate_v5_9_entry(
        {
            CONF_BED_TYPE: _SBI,
            CONF_HAS_MASSAGE: True,
            CONF_PAIR_ID: "pair_two",
            CONF_PAIR_CHILDREN: [
                {CONF_SIDE: "left", CONF_ADDRESS: "AA:BB:CC:DD:EE:01"},
                {CONF_SIDE: "right", CONF_ADDRESS: "AA:BB:CC:DD:EE:02", CONF_BED_TYPE: "rondure"},
            ],
        },
        shared,
        from_version=5,
        from_minor_version=8,
    )

    left = effective_child_data(data, "left", options)
    assert (left[CONF_BED_TYPE], left[CONF_PROTOCOL_VARIANT], left["product_type"]) == (
        "qplus_app",
        "side_b",
        "H",
    )
    # The other side is another bed type: it and what it reads from the pair stay.
    right = effective_child_data(data, "right", options)
    assert (right[CONF_BED_TYPE], right[CONF_PROTOCOL_VARIANT]) == ("rondure", "side_b")
    assert (right[CONF_MOTOR_COUNT], right[CONF_HAS_MASSAGE]) == (4, True)
    assert options == shared


def test_schema_5_9_keeps_positions_unread_on_a_bed_the_app_route_never_read() -> None:
    """The app route reads positions from 5.9 on; a bed set up before keeps them unread."""
    from custom_components.adjustable_bed import migrate_v5_9_entry

    bed = {CONF_ADDRESS: "AA:BB:CC:DD:EE:74", CONF_BED_TYPE: "qplus_app", "product_type": "M2"}
    data, _options = migrate_v5_9_entry(bed, {}, from_version=5, from_minor_version=8)
    assert data.pop(CONF_PROFILE_MIGRATION)["qplus_app_positions_unread"] == ["data"]
    assert data == {**bed, CONF_DISABLE_ANGLE_SENSING: True}

    # A saved choice is the user's.
    chosen = {**bed, CONF_DISABLE_ANGLE_SENSING: False}
    assert migrate_v5_9_entry(chosen, {}, from_version=5, from_minor_version=8) == (chosen, {})
    # An entry from before 5.6 without a saved choice ran unread too.
    older, _options = migrate_v5_9_entry(bed, {}, from_version=5, from_minor_version=5)
    assert older[CONF_DISABLE_ANGLE_SENSING] is True

    # A paired side is judged by what it reads, and its original by its own data.
    data, _options = migrate_v5_9_entry(
        {
            CONF_BED_TYPE: "qplus_app",
            CONF_PAIR_ID: "pair_app",
            CONF_PAIR_CHILDREN: [
                {CONF_SIDE: "left", CONF_ADDRESS: "AA:BB:CC:DD:EE:75", KEY_ORIGIN_DATA: dict(bed)},
                {
                    CONF_SIDE: "right",
                    CONF_ADDRESS: "AA:BB:CC:DD:EE:76",
                    CONF_DISABLE_ANGLE_SENSING: False,
                },
            ],
        },
        {},
        from_version=5,
        from_minor_version=8,
    )
    left, right = data[CONF_PAIR_CHILDREN]
    assert left[CONF_DISABLE_ANGLE_SENSING] is True
    assert left[KEY_ORIGIN_DATA][CONF_DISABLE_ANGLE_SENSING] is True
    assert right[CONF_DISABLE_ANGLE_SENSING] is False


async def test_schema_5_9_keeps_the_buttons_the_app_has_under_another_key(
    hass: HomeAssistant,
) -> None:
    """Zero gravity, TV, the light and the massage keys keep their entity IDs."""
    from homeassistant.helpers import entity_registry as er

    sbi, other = "AA:BB:CC:DD:EE:72", "AA:BB:CC:DD:EE:73"
    entry = _entry(
        hass,
        {
            CONF_BED_TYPE: "rondure",
            CONF_PAIR_ID: "pair_mixed",
            CONF_PAIR_CHILDREN: [
                {CONF_SIDE: "left", CONF_ADDRESS: sbi, CONF_BED_TYPE: _SBI},
                {CONF_SIDE: "right", CONF_ADDRESS: other},
            ],
        },
        version=5,
        minor_version=8,
    )
    registry = er.async_get(hass)

    def row(domain: str, address: str, key: str):
        return registry.async_get_or_create(domain, DOMAIN, f"{address}_{key}", config_entry=entry)

    renamed = {
        new: row("button", sbi, old)
        for old, new in (
            ("preset_zero_g", "zero_g"),
            ("preset_tv", "tv"),
            ("toggle_light", "light"),
            ("massage_head_up", "massage_head"),
            ("massage_foot_up", "massage_foot"),
        )
    }
    # The same command under a wrong name, or no app command at all.
    kept = [row("button", sbi, key) for key in ("preset_memory_1", "preset_memory_2")]
    kept += [row("cover", sbi, "tilt"), row("button", other, "preset_zero_g")]
    stale = row("button", sbi, "zero_g")

    await async_migrate_entry(hass, entry)

    for key, old in renamed.items():
        assert registry.async_get(old.entity_id).unique_id == f"{sbi}_{key}"
    for old in kept:
        assert registry.async_get(old.entity_id).unique_id == old.unique_id
    # The entity that was in use keeps its ID over a leftover row.
    assert registry.async_get(stale.entity_id) is None


async def test_a_5_8_sbi_one_address_pair_loads_as_the_qplus_app_and_keeps_its_sides(
    hass: HomeAssistant,
    mock_bleak_client,
    mock_coordinator_connected,
    enable_custom_integrations,
) -> None:
    """Left still sends A, right B and the pair Both; renamed buttons and sliders keep their IDs."""
    from homeassistant.config_entries import ConfigEntryState
    from homeassistant.helpers import entity_registry as er

    from custom_components.adjustable_bed.beds.keeson.layout_app import FFE4, FFE9
    from custom_components.adjustable_bed.beds.qplus_app import QPlusAppController
    from custom_components.adjustable_bed.const import (
        CONF_PAIR_MEMBER_ADDRESSES,
        CONF_PAIR_MODE,
        PAIR_MODE_SINGLE_ADDRESS,
    )
    from custom_components.adjustable_bed.paired_coordinator import SingleAddressPairedCoordinator
    from custom_components.adjustable_bed.runtime_data import loaded_runtime

    class Gatt:
        def __init__(self, **fields) -> None:
            self.__dict__.update(fields)

    write = Gatt(uuid=FFE9, properties=("write",), handle=1, descriptors=[])
    notify = Gatt(uuid=FFE4, properties=("notify",), handle=2, descriptors=[])
    mock_bleak_client.services = [Gatt(uuid="ffe5", characteristics=[write, notify])]

    address = "AA:BB:CC:DD:EE:FF"
    single = {CONF_ADDRESS: address, CONF_NAME: "Bed", CONF_BED_TYPE: _SBI, CONF_MOTOR_COUNT: 4}
    entry = _entry(
        hass,
        {
            **single,
            CONF_PAIR_ID: "pair_one",
            CONF_PAIR_MODE: PAIR_MODE_SINGLE_ADDRESS,
            CONF_PAIR_MEMBER_ADDRESSES: [address],
            CONF_PAIR_CHILDREN: [
                {**single, CONF_SIDE: side, CONF_PROTOCOL_VARIANT: selection}
                for side, selection in (("left", "side_a"), ("right", "side_b"))
            ],
        },
        version=5,
        minor_version=8,
    )
    hass.config_entries.async_update_entry(entry, unique_id=address)
    registry = er.async_get(hass)
    kept = {
        new: registry.async_get_or_create(domain, DOMAIN, f"{address}_{old}", config_entry=entry)
        for domain, old, new in (
            ("button", "preset_zero_g_left", "zero_g_left"),
            ("button", "preset_tv_right", "tv_right"),
            ("button", "toggle_light_left", "light_left"),
            ("button", "preset_flat_both", "preset_flat_both"),
            # The bed read its positions, and still does.
            ("number", "back_position_left", "back_position_left"),
            ("number", "legs_position_right", "legs_position_right"),
        )
    }
    gone = [
        registry.async_get_or_create(domain, DOMAIN, f"{address}_{key}", config_entry=entry)
        for domain, key in (
            ("cover", "tilt_left"),
            ("cover", "head_right"),
            ("button", "preset_memory_1_left"),
            ("button", "preset_zero_g_both"),
        )
    ]

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    assert (entry.version, entry.minor_version) == (5, 11)
    # The bed stored no selection, which is Both on either route; its sides keep theirs.
    assert [entry.data[CONF_PROFILE_ID], *(c[CONF_PROFILE_ID] for c in entry.data[CONF_PAIR_CHILDREN])] == [
        "qplus_app",
        "qplus_app:side_a",
        "qplus_app:side_b",
    ]
    runtime = loaded_runtime(hass, entry.entry_id)
    assert isinstance(runtime, SingleAddressPairedCoordinator)
    assert type(runtime.children["left"].controller) is QPlusAppController
    for key, row in kept.items():
        assert registry.async_get(row.entity_id).unique_id == f"{address}_{key}"
        assert hass.states.get(row.entity_id) is not None
    # Controls without an app key of the same meaning go once the bed has loaded.
    assert [registry.async_get(row.entity_id) for row in gone] == [None] * len(gone)

    sent = []
    for side in ("left", "right", "both"):
        mock_bleak_client.write_gatt_char.reset_mock()
        await runtime.async_stop_command(side=side)
        sent.append(mock_bleak_client.write_gatt_char.await_args.args[1].hex())
    assert sent == ["e6fe16000000000104", "e6fe16000000000203", "e5fe160000000006"]


@pytest.mark.parametrize("bed_type", [_SBI, "qplus_app"])
async def test_a_4x_bed_keeps_its_positions_unread_as_a_qplus_app_bed(
    hass: HomeAssistant, bed_type: str
) -> None:
    """4.x read no position unless asked; the app route's default must not turn it on."""
    entry = _entry(hass, {CONF_ADDRESS: "AA:BB:CC:DD:EE:77", CONF_NAME: "Bed", CONF_BED_TYPE: bed_type})

    await async_migrate_entry(hass, entry)

    assert entry.data[CONF_BED_TYPE] == "qplus_app"
    assert not reads_positions(entry.data)


_SERTA = "serta"
_SERTA_MP = {CONF_BED_TYPE: "serta_mp_remote", "product_type": "standard"}


@pytest.mark.parametrize(
    ("stored", "expected"),
    [
        pytest.param({CONF_BED_TYPE: _SERTA}, {}, id="bed type"),
        pytest.param(
            {CONF_BED_TYPE: BED_TYPE_KEESON, CONF_PROTOCOL_VARIANT: _SERTA},
            {CONF_PROTOCOL_VARIANT: "auto"},
            id="keeson remote",
        ),
        pytest.param(
            {CONF_BED_TYPE: _SERTA, CONF_MOTOR_COUNT: 4, CONF_HAS_MASSAGE: True},
            {CONF_MOTOR_COUNT: 2, CONF_HAS_MASSAGE: False},
            id="settings the app layout decides",
        ),
        # 4.x saved positions unread; the app always reads them.
        pytest.param({CONF_BED_TYPE: _SERTA, CONF_DISABLE_ANGLE_SENSING: True}, {}, id="unread"),
    ],
)
def test_schema_5_10_saves_a_serta_bed_as_the_serta_mp_remote_app(
    stored: dict, expected: dict
) -> None:
    from custom_components.adjustable_bed import migrate_v5_10_entry

    base = {CONF_ADDRESS: "AA:BB:CC:DD:EE:80", CONF_NAME: "Bed"}
    data, options = migrate_v5_10_entry(
        {**base, **stored}, {}, from_version=5, from_minor_version=9
    )

    assert data.pop(CONF_PROFILE_MIGRATION)["serta_mp_remote"] == ["data"]
    assert data == {**base, **_SERTA_MP, CONF_DISABLE_ANGLE_SENSING: False, **expected}
    assert reads_positions(data)
    assert options == {}


@pytest.mark.parametrize(
    "other",
    [
        {CONF_BED_TYPE: BED_TYPE_KEESON, CONF_PROTOCOL_VARIANT: "base"},
        {CONF_BED_TYPE: "ergomotion"},
        # A standalone bed never read its options, so they do not pick its route.
        {CONF_BED_TYPE: BED_TYPE_KEESON},
    ],
)
def test_schema_5_10_leaves_every_other_route(other: dict) -> None:
    from custom_components.adjustable_bed import migrate_v5_10_entry

    options = {CONF_PROTOCOL_VARIANT: _SERTA}
    assert migrate_v5_10_entry(other, options, from_version=5, from_minor_version=9) == (
        other,
        options,
    )


def test_schema_5_10_moves_only_the_serta_side_of_a_pair() -> None:
    from custom_components.adjustable_bed import migrate_v5_10_entry

    left, right = "AA:BB:CC:DD:EE:81", "AA:BB:CC:DD:EE:82"
    data, options = migrate_v5_10_entry(
        {
            # The pair's shared layer named the route; the right side chose its own remote.
            CONF_BED_TYPE: BED_TYPE_KEESON,
            CONF_PROTOCOL_VARIANT: _SERTA,
            CONF_PAIR_ID: "pair_serta",
            CONF_PAIR_CHILDREN: [
                {
                    CONF_SIDE: "left",
                    CONF_ADDRESS: left,
                    KEY_ORIGIN_DATA: {CONF_ADDRESS: left, CONF_BED_TYPE: _SERTA},
                    KEY_ORIGIN_OPTIONS: {CONF_BED_TYPE: _SERTA},
                },
                {CONF_SIDE: "right", CONF_ADDRESS: right, CONF_PROTOCOL_VARIANT: "base"},
            ],
        },
        # A pair's options override both sides.
        {CONF_BED_TYPE: BED_TYPE_KEESON, CONF_DISABLE_ANGLE_SENSING: True, CONF_MOTOR_COUNT: 3},
        from_version=5,
        from_minor_version=9,
    )

    assert data[CONF_PROFILE_MIGRATION]["serta_mp_remote"] == [
        "data",
        "data.left",
        f"data.left.{KEY_ORIGIN_DATA}",
    ]
    # The options no longer decide a route, so the moved side cannot fall back.
    assert options == {CONF_MOTOR_COUNT: 3}
    views = [effective_child_data(data, side, options) for side in ("left", "right")]
    assert [(view[CONF_BED_TYPE], view[CONF_PROTOCOL_VARIANT]) for view in views] == [
        ("serta_mp_remote", "auto"),
        (BED_TYPE_KEESON, "base"),
    ]
    # The moved side reads positions; the other side is as it was.
    assert [reads_positions(view) for view in views] == [True, False]
    origin = data[CONF_PAIR_CHILDREN][0]
    assert origin[KEY_ORIGIN_DATA] == {
        CONF_ADDRESS: left,
        **_SERTA_MP,
        CONF_DISABLE_ANGLE_SENSING: False,
    }
    assert origin[KEY_ORIGIN_OPTIONS] == {CONF_BED_TYPE: "serta_mp_remote"}


@pytest.mark.parametrize(
    ("masking", "ran"),
    [
        # Both sides ran the Base remote, whatever they had stored.
        ({CONF_PROTOCOL_VARIANT: "base"}, (BED_TYPE_KEESON, "base")),
        ({CONF_BED_TYPE: BED_TYPE_LINAK}, (BED_TYPE_LINAK, "auto")),
    ],
)
def test_schema_5_10_leaves_no_serta_remote_behind_the_pairs_options(
    masking: dict, ran: tuple[str, str]
) -> None:
    from custom_components.adjustable_bed import migrate_v5_10_entry

    stored = {CONF_BED_TYPE: BED_TYPE_KEESON, CONF_PROTOCOL_VARIANT: _SERTA}
    data, options = migrate_v5_10_entry(
        {
            CONF_PAIR_ID: "pair_masked",
            CONF_PAIR_CHILDREN: [
                {CONF_SIDE: "left", CONF_ADDRESS: "AA:BB:CC:DD:EE:85", **stored},
                {CONF_SIDE: "right", CONF_ADDRESS: "AA:BB:CC:DD:EE:86", **stored},
            ],
        },
        masking,
        from_version=5,
        from_minor_version=9,
    )

    assert options == masking
    # Unpairing, or clearing the options, must not bring the removed remote back.
    assert [
        (child[CONF_BED_TYPE], child[CONF_PROTOCOL_VARIANT]) for child in data[CONF_PAIR_CHILDREN]
    ] == [ran, ran]


@pytest.mark.parametrize(
    ("pair", "options"),
    [
        pytest.param({CONF_BED_TYPE: BED_TYPE_KEESON}, {}, id="sides inherit the bed type"),
        # One bed on one address reads its own data, so a stale option moves nothing.
        pytest.param(
            {CONF_BED_TYPE: BED_TYPE_KEESON, "pair_mode": "single_address"},
            {CONF_PROTOCOL_VARIANT: _SERTA},
            id="one address",
        ),
    ],
)
def test_schema_5_10_leaves_other_pairs_as_saved(pair: dict, options: dict) -> None:
    from custom_components.adjustable_bed import migrate_v5_10_entry

    data = {
        **pair,
        CONF_ADDRESS: "AA:BB:CC:DD:EE:87",
        CONF_PAIR_ID: "pair_other",
        CONF_PAIR_CHILDREN: [
            {CONF_SIDE: "left", CONF_ADDRESS: "AA:BB:CC:DD:EE:87"},
            {CONF_SIDE: "right", CONF_ADDRESS: "AA:BB:CC:DD:EE:88"},
        ],
    }
    assert migrate_v5_10_entry(data, options, from_version=5, from_minor_version=9) == (
        data,
        options,
    )


async def test_schema_5_10_keeps_the_controls_the_app_has_under_another_key(
    hass: HomeAssistant,
) -> None:
    """Covers, zero gravity and the massage keys keep their entity IDs; so do a pair's own buttons."""
    from homeassistant.helpers import entity_registry as er

    left, right = "AA:BB:CC:DD:EE:83", "AA:BB:CC:DD:EE:84"
    entry = _entry(
        hass,
        {
            CONF_BED_TYPE: _SERTA,
            CONF_PAIR_ID: "pair_serta",
            CONF_PAIR_CHILDREN: [
                {CONF_SIDE: "left", CONF_ADDRESS: left},
                {CONF_SIDE: "right", CONF_ADDRESS: right},
            ],
        },
        version=5,
        minor_version=9,
    )
    registry = er.async_get(hass)

    def row(domain: str, unique_id: str):
        return registry.async_get_or_create(domain, DOMAIN, unique_id, config_entry=entry)

    renamed = {
        new: row(domain, old)
        for domain, old, new in (
            ("cover", f"{left}_head", f"{left}_back"),
            ("cover", f"{right}_feet", f"{right}_legs"),
            ("button", f"{left}_preset_zero_g", f"{left}_zg"),
            ("button", f"{left}_massage_all_toggle", f"{left}_level"),
            ("button", f"{left}_massage_mode_step", f"{left}_timer"),
            ("button", f"{right}_massage_head_up", f"{right}_masheadadd"),
            ("button", f"{right}_massage_foot_down", f"{right}_masfootmin"),
            ("button", "pair_serta_head_up_both", "pair_serta_back_up_both"),
            ("button", "pair_serta_feet_down_both", "pair_serta_legs_down_both"),
        )
    }
    # Memory 1 recalls the app's own memory from now on; the rest has no app key.
    kept = [
        row("button", f"{left}_preset_memory_1"),
        row("cover", f"{left}_tilt"),
        row("button", f"{left}_toggle_light"),
    ]

    await async_migrate_entry(hass, entry)

    for unique_id, old in renamed.items():
        assert registry.async_get(old.entity_id).unique_id == unique_id
    for old in kept:
        assert registry.async_get(old.entity_id).unique_id == old.unique_id


async def test_a_5_9_serta_bed_loads_as_the_serta_mp_remote_app(
    hass: HomeAssistant,
    mock_bleak_client,
    mock_coordinator_connected,
    enable_custom_integrations,
) -> None:
    """The bed runs the app's controller; renamed controls keep their IDs and the rest goes."""
    from homeassistant.config_entries import ConfigEntryState
    from homeassistant.helpers import entity_registry as er

    from custom_components.adjustable_bed.beds.keeson.layout_app import FFE4, FFE9
    from custom_components.adjustable_bed.beds.serta_mp_remote import SertaMPRemoteController
    from custom_components.adjustable_bed.runtime_data import loaded_runtime

    class Gatt:
        def __init__(self, **fields) -> None:
            self.__dict__.update(fields)

    write = Gatt(uuid=FFE9, properties=("write",), handle=1, descriptors=[])
    notify = Gatt(uuid=FFE4, properties=("notify",), handle=2, descriptors=[])
    mock_bleak_client.services = [Gatt(uuid="ffe5", characteristics=[write, notify])]

    address = "AA:BB:CC:DD:EE:FF"
    entry = _entry(
        hass,
        {
            CONF_ADDRESS: address,
            CONF_NAME: "Bed",
            CONF_BED_TYPE: _SERTA,
            CONF_MOTOR_COUNT: 3,
            CONF_HAS_MASSAGE: True,
        },
        version=5,
        minor_version=9,
    )
    hass.config_entries.async_update_entry(entry, unique_id=address)
    registry = er.async_get(hass)
    kept = {
        new: registry.async_get_or_create(domain, DOMAIN, f"{address}_{old}", config_entry=entry)
        for domain, old, new in (
            ("cover", "head", "back"),
            ("cover", "feet", "legs"),
            ("button", "preset_zero_g", "zg"),
            ("button", "massage_mode_step", "timer"),
            ("button", "preset_flat", "preset_flat"),
            ("button", "preset_memory_1", "preset_memory_1"),
        )
    }
    gone = [
        registry.async_get_or_create(domain, DOMAIN, f"{address}_{key}", config_entry=entry)
        for domain, key in (
            ("cover", "tilt"),
            ("button", "toggle_light"),
            ("button", "massage_head_toggle"),
        )
    ]

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    assert (entry.version, entry.minor_version) == (5, 11)
    assert entry.data[CONF_PROFILE_ID] == "serta_mp_remote"
    assert type(loaded_runtime(hass, entry.entry_id).controller) is SertaMPRemoteController
    for key, row in kept.items():
        assert registry.async_get(row.entity_id).unique_id == f"{address}_{key}"
        assert hass.states.get(row.entity_id) is not None
    assert [registry.async_get(row.entity_id) for row in gone] == [None] * len(gone)


_LEGGETT = "leggett_platt"


@pytest.mark.parametrize(
    ("stored", "bed_type"),
    [
        pytest.param({CONF_BED_TYPE: _LEGGETT, CONF_PROTOCOL_VARIANT: "gen2"}, "leggett_gen2", id="gen2"),
        pytest.param(
            {CONF_BED_TYPE: _LEGGETT, CONF_PROTOCOL_VARIANT: "okin", "leggett_app_profile": "prodigy2"},
            "leggett_okin",
            id="okin",
        ),
        pytest.param({CONF_BED_TYPE: _LEGGETT, CONF_PROTOCOL_VARIANT: "mlrm"}, "leggett_wilinke", id="mlrm"),
        # Pairing, and a correction on connecting, saved the bed type beside the model.
        pytest.param(
            {CONF_BED_TYPE: "leggett_gen2", CONF_PROTOCOL_VARIANT: "gen2"},
            "leggett_gen2",
            id="model name left beside its bed type",
        ),
    ],
)
def test_schema_5_11_saves_a_leggett_model_as_its_bed_type(stored: dict, bed_type: str) -> None:
    from custom_components.adjustable_bed import migrate_v5_11_entry

    base = {CONF_ADDRESS: "AA:BB:CC:DD:EE:90", CONF_NAME: "Bed", CONF_MOTOR_COUNT: 3}
    options = {CONF_PREFERRED_ADAPTER: "hci1"}
    data, new_options = migrate_v5_11_entry(
        {**base, **stored}, options, from_version=5, from_minor_version=10
    )

    assert data.pop(CONF_PROFILE_MIGRATION)["leggett_models"] == ["data"]
    assert data == {**base, **stored, CONF_BED_TYPE: bed_type, CONF_PROTOCOL_VARIANT: "auto"}
    assert new_options == options


@pytest.mark.parametrize(
    "other",
    [
        # The automatic setup finds its model when it connects.
        {CONF_BED_TYPE: _LEGGETT},
        {CONF_BED_TYPE: _LEGGETT, CONF_PROTOCOL_VARIANT: "auto"},
        {CONF_BED_TYPE: "leggett_okin", "leggett_app_profile": "useries"},
        {CONF_BED_TYPE: BED_TYPE_KEESON, CONF_PROTOCOL_VARIANT: "okin"},
    ],
)
def test_schema_5_11_leaves_the_automatic_setup_and_other_routes(other: dict) -> None:
    from custom_components.adjustable_bed import migrate_v5_11_entry

    options = {CONF_PREFERRED_ADAPTER: "hci1"}
    assert migrate_v5_11_entry(other, options, from_version=5, from_minor_version=10) == (
        other,
        options,
    )


@pytest.mark.parametrize(
    ("stored", "ran"),
    [
        ({CONF_BED_TYPE: _LEGGETT, CONF_PROTOCOL_VARIANT: "auto"}, (_LEGGETT, "auto")),
        ({CONF_BED_TYPE: _LEGGETT, CONF_PROTOCOL_VARIANT: "gen2"}, ("leggett_gen2", "auto")),
    ],
)
def test_schema_5_11_keeps_a_beds_options_from_naming_a_model(
    stored: dict, ran: tuple[str, str]
) -> None:
    """A bed runs its own data; pairing and Reconfigure read its options over it."""
    from custom_components.adjustable_bed import migrate_v5_11_entry

    data, options = migrate_v5_11_entry(
        stored,
        {CONF_PROTOCOL_VARIANT: "okin", CONF_PREFERRED_ADAPTER: "hci1"},
        from_version=5,
        from_minor_version=10,
    )

    assert "options" in data[CONF_PROFILE_MIGRATION]["leggett_models"]
    assert options == {CONF_PREFERRED_ADAPTER: "hci1"}
    merged = {**data, **options}
    assert (merged[CONF_BED_TYPE], merged[CONF_PROTOCOL_VARIANT]) == ran


def test_schema_5_11_stores_on_each_side_of_a_pair_the_route_it_ran() -> None:
    from custom_components.adjustable_bed import migrate_v5_11_entry

    left, right = "AA:BB:CC:DD:EE:91", "AA:BB:CC:DD:EE:92"
    stored = {
        CONF_PAIR_ID: "pair_leggett",
        CONF_PAIR_CHILDREN: [
            {
                CONF_SIDE: "left",
                CONF_ADDRESS: left,
                CONF_BED_TYPE: _LEGGETT,
                # Unpair restores this bed: its data ran MlRM, whatever its options say.
                KEY_ORIGIN_DATA: {
                    CONF_ADDRESS: left,
                    CONF_BED_TYPE: _LEGGETT,
                    CONF_PROTOCOL_VARIANT: "mlrm",
                },
                KEY_ORIGIN_OPTIONS: {CONF_PROTOCOL_VARIANT: "gen2", CONF_PREFERRED_ADAPTER: "hci1"},
            },
            # This side chose its own bed type; the pair's model name reached it too.
            {CONF_SIDE: "right", CONF_ADDRESS: right, CONF_BED_TYPE: BED_TYPE_LINAK},
        ],
    }
    # A pair's options override both sides: they named the model and its app.
    stored_options = {
        CONF_PROTOCOL_VARIANT: "okin",
        "leggett_app_profile": "prodigy2",
        CONF_MOTOR_COUNT: 3,
    }

    def read(data: dict, options: dict) -> list[dict]:
        views = [effective_child_data(data, side, options) for side in ("left", "right")]
        originals = (KEY_ORIGIN_DATA, KEY_ORIGIN_OPTIONS)
        return [{k: v for k, v in view.items() if k not in originals} for view in views]

    before = read(stored, stored_options)

    data, options = migrate_v5_11_entry(
        stored, stored_options, from_version=5, from_minor_version=10
    )

    assert data.pop(CONF_PROFILE_MIGRATION)["leggett_models"] == [
        "data.left",
        f"data.left.{KEY_ORIGIN_DATA}",
        f"data.left.{KEY_ORIGIN_OPTIONS}",
    ]
    # The options no longer decide a route, so the renamed side cannot fall back.
    assert options == {"leggett_app_profile": "prodigy2", CONF_MOTOR_COUNT: 3}
    # Each side reads what it read before, the left under its model's bed type.
    assert read(data, options) == [
        {**before[0], CONF_BED_TYPE: "leggett_okin", CONF_PROTOCOL_VARIANT: "auto"},
        before[1],
    ]
    # The Okin bed type keeps its app to itself, so the side stores the one it ran.
    assert data[CONF_PAIR_CHILDREN][0]["leggett_app_profile"] == "prodigy2"
    origin = data[CONF_PAIR_CHILDREN][0]
    assert origin[KEY_ORIGIN_DATA] == {
        CONF_ADDRESS: left,
        CONF_BED_TYPE: "leggett_wilinke",
        CONF_PROTOCOL_VARIANT: "auto",
    }
    assert origin[KEY_ORIGIN_OPTIONS] == {CONF_PREFERRED_ADAPTER: "hci1"}


async def test_a_5_10_leggett_mlrm_bed_loads_as_the_mlrm_bed_type(
    hass: HomeAssistant,
    mock_bleak_client,
    mock_coordinator_connected,
    enable_custom_integrations,
) -> None:
    """The bed runs the controller it ran before, and its entities keep their IDs."""
    from homeassistant.config_entries import ConfigEntryState
    from homeassistant.helpers import entity_registry as er

    from custom_components.adjustable_bed.beds.leggett.wilinke import LeggettWilinkeController
    from custom_components.adjustable_bed.runtime_data import loaded_runtime

    address = "AA:BB:CC:DD:EE:FF"
    entry = _entry(
        hass,
        {
            CONF_ADDRESS: address,
            CONF_NAME: "Bed",
            CONF_BED_TYPE: _LEGGETT,
            CONF_PROTOCOL_VARIANT: "mlrm",
            CONF_MOTOR_COUNT: 2,
            CONF_HAS_MASSAGE: True,
            "motor_pulse_delay_ms": 100,
        },
        version=5,
        minor_version=10,
    )
    hass.config_entries.async_update_entry(entry, unique_id=address)
    registry = er.async_get(hass)
    kept = {
        key: registry.async_get_or_create(domain, DOMAIN, f"{address}_{key}", config_entry=entry)
        for domain, key in (
            ("button", "head_up"),
            ("button", "preset_lounge"),
            ("button", "massage_foot_toggle"),
            ("light", "under_bed_lights_assumed"),
        )
    }

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    assert (entry.version, entry.minor_version) == (5, 11)
    assert entry.data[CONF_PROFILE_ID] == "leggett_wilinke"
    runtime = loaded_runtime(hass, entry.entry_id)
    assert type(runtime.controller) is LeggettWilinkeController
    # A saved repeat interval stays; only a bed without one takes the MlRM cadence.
    assert runtime.motor_pulse_delay_ms == 100
    for key, row in kept.items():
        assert registry.async_get(row.entity_id).unique_id == f"{address}_{key}"
        assert hass.states.get(row.entity_id) is not None
