"""Schema 5 profile ids (#778): resolver, migration, setup sync and controller routing."""

from __future__ import annotations

import importlib.util
import json
import sys
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed import _async_sync_profile_ids, async_migrate_entry
from custom_components.adjustable_bed.const import (
    BED_TYPE_CLUSTER018,
    BED_TYPE_DIAGNOSTIC,
    BED_TYPE_JIECANG_APP,
    BED_TYPE_LEGGETT_PLATT,
    BED_TYPE_LINAK,
    BED_TYPE_LOGICDATA_APP,
    BED_TYPE_MALOUF_LEGACY_OKIN,
    BED_TYPE_MALOUF_NEW_OKIN,
    BED_TYPE_SBI,
    CONF_BED_TYPE,
    CONF_BLE_DEVICE_NAME,
    CONF_CLUSTER018_THIRD_SERVICE,
    CONF_JIECANG_APP_PROFILE,
    CONF_LEGGETT_APP_PROFILE,
    CONF_LOGICDATA_APP_PROFILE,
    CONF_MALOUF_APP_PROFILE,
    CONF_MOTOR_COUNT,
    CONF_PAIR_CHILDREN,
    CONF_PAIR_ID,
    CONF_PAIR_MODE,
    CONF_PRODUCT_TYPE,
    CONF_PROFILE_ID,
    CONF_PROFILE_MIGRATION,
    CONF_PROFILE_REVIEW_PENDING,
    CONF_PROTOCOL_VARIANT,
    CONF_SIDE,
    CONF_VIBRADORM_APP_PROFILE,
    DOMAIN,
    JIECANG_APP_PROFILES,
    LEGGETT_APP_PROFILES,
    LEGGETT_VARIANT_GEN2,
    LEGGETT_VARIANT_OKIN,
    LOGICDATA_APP_PROFILES,
    MALOUF_APP_PROFILES,
    PAIR_MODE_SEPARATE_ADDRESS,
    PAIR_MODE_SINGLE_ADDRESS,
    SUPPORTED_BED_TYPES,
    VARIANT_AUTO,
    VIBRADORM_APP_PROFILES,
)
from custom_components.adjustable_bed.controller_factory import _SIMPLE_CONTROLLERS
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.pairing import effective_child_data
from custom_components.adjustable_bed.profile_id import (
    APP_PROFILE_KEYS,
    PROFILE_RESOLVER_VERSION,
    ProfileRoute,
    app_profile_key,
    profile_route,
    profile_route_from_data,
    resolve_profile_id,
    with_profile_ids,
)
from custom_components.adjustable_bed.profile_review import v5_profile_review_mark
from custom_components.adjustable_bed.validators import VARIANTS_BY_BED_TYPE
from tests.codec_families import families
from tests.codec_families._standalone import STANDALONE

ADDRESS = "AA:BB:CC:DD:EE:01"
WIRE_SNAPSHOT = Path(__file__).resolve().parent.parent / "scripts" / "wire_snapshot.py"
_APP_CHOICES = {
    CONF_JIECANG_APP_PROFILE: JIECANG_APP_PROFILES,
    CONF_LEGGETT_APP_PROFILE: LEGGETT_APP_PROFILES,
    CONF_LOGICDATA_APP_PROFILE: LOGICDATA_APP_PROFILES,
    CONF_MALOUF_APP_PROFILE: MALOUF_APP_PROFILES,
    CONF_VIBRADORM_APP_PROFILE: VIBRADORM_APP_PROFILES,
}


def former_routes() -> Iterator[dict[str, Any]]:
    """Every former bed type, each listed variant and each app key choice."""
    for bed_type in sorted({*SUPPORTED_BED_TYPES, BED_TYPE_DIAGNOSTIC}):
        yield {CONF_BED_TYPE: bed_type}
        for variant in VARIANTS_BY_BED_TYPE.get(bed_type, {}):
            yield {CONF_BED_TYPE: bed_type, CONF_PROTOCOL_VARIANT: variant}
    for bed_type, key in APP_PROFILE_KEYS.items():
        for choice in _APP_CHOICES[key]:
            yield {CONF_BED_TYPE: bed_type, key: choice}
    for choice in LEGGETT_APP_PROFILES:
        yield {
            CONF_BED_TYPE: BED_TYPE_LEGGETT_PLATT,
            CONF_PROTOCOL_VARIANT: LEGGETT_VARIANT_OKIN,
            CONF_LEGGETT_APP_PROFILE: choice,
        }


def _expected_route(data: dict[str, Any]) -> ProfileRoute:
    variant = data.get(CONF_PROTOCOL_VARIANT)
    variant = None if variant in (None, VARIANT_AUTO) else variant
    key = APP_PROFILE_KEYS.get(data[CONF_BED_TYPE])
    if data[CONF_BED_TYPE] == BED_TYPE_LEGGETT_PLATT and variant == LEGGETT_VARIANT_OKIN:
        key = CONF_LEGGETT_APP_PROFILE
    return ProfileRoute(data[CONF_BED_TYPE], variant, data.get(key) if key else None)


def test_every_former_route_resolves_to_its_own_round_tripping_id() -> None:
    routes = list(former_routes())
    seen: dict[str, ProfileRoute] = {}
    for data in routes:
        profile_id = resolve_profile_id(data)
        route = profile_route(profile_id)
        assert route == _expected_route(data) == profile_route_from_data(data), data
        assert route.profile_id == profile_id
        # Distinct routes never share an id: no alias is merged yet.
        assert seen.setdefault(profile_id, route) == route, profile_id
    assert len(seen) > 1000
    # The id space covers every codec family bed type and every standalone controller.
    registered = {*STANDALONE}
    for family in families().values():
        registered |= family.bed_types | set(family.pending)
    assert registered <= {route.bed_type for route in seen.values()}


@pytest.mark.parametrize(
    ("data", "profile_id"),
    [
        ({CONF_BED_TYPE: "linak"}, "linak"),
        ({CONF_BED_TYPE: "linak", CONF_PROTOCOL_VARIANT: VARIANT_AUTO}, "linak"),
        ({CONF_BED_TYPE: "keeson", CONF_PROTOCOL_VARIANT: "sino"}, "keeson:sino"),
        ({CONF_BED_TYPE: "reverie", CONF_PROTOCOL_VARIANT: "Skye 500"}, "reverie:Skye 500"),
        ({CONF_BED_TYPE: BED_TYPE_JIECANG_APP, CONF_JIECANG_APP_PROFILE: "dreamask"}, "jiecang_app@dreamask"),
        (
            {
                CONF_BED_TYPE: BED_TYPE_LEGGETT_PLATT,
                CONF_PROTOCOL_VARIANT: LEGGETT_VARIANT_OKIN,
                CONF_LEGGETT_APP_PROFILE: "prodigy",
            },
            "leggett_platt:okin@prodigy",
        ),
        # An app key only counts on the route that reads it.
        (
            {
                CONF_BED_TYPE: BED_TYPE_LEGGETT_PLATT,
                CONF_PROTOCOL_VARIANT: LEGGETT_VARIANT_GEN2,
                CONF_LEGGETT_APP_PROFILE: "prodigy",
            },
            "leggett_platt:gen2",
        ),
        ({CONF_BED_TYPE: BED_TYPE_LINAK, CONF_JIECANG_APP_PROFILE: "dreamask"}, "linak"),
        # A classic Richmat app is its variant; its layout is a setting, not the route.
        (
            {
                CONF_BED_TYPE: BED_TYPE_CLUSTER018,
                CONF_PROTOCOL_VARIANT: "superior",
                CONF_PRODUCT_TYPE: "YGRM",
            },
            "richmat_classic_apps:superior",
        ),
        # Separators inside saved values round-trip.
        ({CONF_BED_TYPE: "okin_uuid", CONF_PROTOCOL_VARIANT: "a:b@c%d"}, "okin_uuid:a%3Ab%40c%25d"),
    ],
)
def test_profile_id_format(data: dict[str, Any], profile_id: str) -> None:
    assert resolve_profile_id(data) == profile_id
    assert profile_route(profile_id).profile_id == profile_id


def test_resolver_needs_a_bed_type() -> None:
    with pytest.raises(ValueError):
        resolve_profile_id({CONF_PROTOCOL_VARIANT: "sino"})
    assert with_profile_ids({CONF_ADDRESS: ADDRESS}) == {CONF_ADDRESS: ADDRESS}


async def test_migration_stores_an_id_for_every_former_route(hass: HomeAssistant) -> None:
    """Each former bed type, variant and app key migrates with its fields untouched."""
    for index, data in enumerate(former_routes()):
        stored = {CONF_ADDRESS: f"AA:BB:CC:{index >> 8:02X}:{index & 0xFF:02X}:01", **data}
        entry = MockConfigEntry(
            domain=DOMAIN, data=dict(stored), options={"motor_pulse_count": 7}, version=4, minor_version=3
        )
        entry.add_to_hass(hass)

        await async_migrate_entry(hass, entry)

        migrated = dict(entry.data)
        profile_id = migrated.pop(CONF_PROFILE_ID)
        record = migrated.pop(CONF_PROFILE_MIGRATION)
        # Only a route that gained an app in v5 is asked about it once more.
        assert migrated.pop(CONF_PROFILE_REVIEW_PENDING, None) == v5_profile_review_mark(stored)
        assert (entry.version, entry.minor_version) == (5, 3)
        assert migrated == stored
        assert dict(entry.options) == {"motor_pulse_count": 7}
        assert profile_id == resolve_profile_id(data)
        assert record == {
            "from_version": 4,
            "from_minor_version": 3,
            "resolver_version": PROFILE_RESOLVER_VERSION,
            "profile_id": profile_id,
            "fields": data,
        }


async def test_classic_richmat_entries_from_4x_keep_their_app_settings(
    hass: HomeAssistant,
) -> None:
    """A 4.x classic app entry gains its app's id; layout and fallback stay as saved."""
    stored = {
        CONF_ADDRESS: ADDRESS,
        CONF_BED_TYPE: BED_TYPE_CLUSTER018,
        CONF_PROTOCOL_VARIANT: "fortywinks",
        CONF_PRODUCT_TYPE: "CORN",
        CONF_CLUSTER018_THIRD_SERVICE: True,
    }
    entry = MockConfigEntry(domain=DOMAIN, data=dict(stored), version=4, minor_version=3)
    entry.add_to_hass(hass)

    await async_migrate_entry(hass, entry)

    migrated = dict(entry.data)
    assert migrated.pop(CONF_PROFILE_ID) == "richmat_classic_apps:fortywinks"
    assert migrated.pop(CONF_PROFILE_MIGRATION)["profile_id"] == "richmat_classic_apps:fortywinks"
    assert migrated == stored


@pytest.mark.parametrize(
    ("stored", "profile_id"),
    [
        # MotoMotion's exact name selects its panel; it is a setting, not the route.
        (
            {CONF_BED_TYPE: "motomotion", CONF_BLE_DEVICE_NAME: "SOFA000005S00FM"},
            "motomotion",
        ),
        ({CONF_BED_TYPE: "bedjet_powerlayer", CONF_MOTOR_COUNT: 2}, "bedjet_powerlayer"),
        # A Hush Base product is its variant, a sided product included.
        (
            {CONF_BED_TYPE: "hush_base", CONF_PROTOCOL_VARIANT: "hushs575sh"},
            "hush_base:hushs575sh",
        ),
        ({CONF_BED_TYPE: "hush_remote"}, "hush_remote"),
        ({CONF_BED_TYPE: "hush_sleep_mm"}, "hush_sleep_mm"),
        ({CONF_BED_TYPE: "hush_sleep_sxb"}, "hush_sleep_sxb"),
    ],
)
async def test_beds_from_main_migrate_from_4x_with_their_settings(
    hass: HomeAssistant, stored: dict[str, Any], profile_id: str
) -> None:
    """A 4.x entry for a bed that arrived on main gains its id and keeps its data."""
    stored = {CONF_ADDRESS: ADDRESS, **stored}
    entry = MockConfigEntry(domain=DOMAIN, data=dict(stored), version=4, minor_version=3)
    entry.add_to_hass(hass)

    await async_migrate_entry(hass, entry)

    migrated = dict(entry.data)
    assert migrated.pop(CONF_PROFILE_ID) == profile_id
    assert migrated.pop(CONF_PROFILE_MIGRATION)["profile_id"] == profile_id
    assert migrated == stored


async def test_migration_keeps_entry_device_and_entity_identities(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Bedroom",
        unique_id=ADDRESS,
        data={CONF_ADDRESS: ADDRESS, CONF_NAME: "Bedroom", CONF_BED_TYPE: "okimat"},
        version=1,
    )
    entry.add_to_hass(hass)
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id, identifiers={(DOMAIN, ADDRESS)}
    )
    entity = er.async_get(hass).async_get_or_create(
        "cover", DOMAIN, f"{ADDRESS}_back", config_entry=entry, device_id=device.id
    )
    entry_id = entry.entry_id

    await async_migrate_entry(hass, entry)

    assert (entry.entry_id, entry.unique_id, entry.title) == (entry_id, ADDRESS, "Bedroom")
    assert entry.data[CONF_BED_TYPE] == "okimat"
    assert entry.data[CONF_PROFILE_ID] == "okimat"
    assert entry.data[CONF_PROFILE_MIGRATION]["from_version"] == 1
    assert dr.async_get(hass).async_get(device.id) == device
    assert er.async_get(hass).async_get(entity.entity_id) == entity


def _side(side: str, address: str, **fields: Any) -> dict[str, Any]:
    return {CONF_SIDE: side, CONF_ADDRESS: address, **fields}


async def test_paired_migration_gives_each_side_its_own_id(hass: HomeAssistant) -> None:
    left = _side("left", "AA:BB:CC:DD:EE:0A", **{
        CONF_BED_TYPE: BED_TYPE_JIECANG_APP, CONF_JIECANG_APP_PROFILE: "dreamask"
    })
    right = _side("right", "AA:BB:CC:DD:EE:0B", **{
        CONF_BED_TYPE: BED_TYPE_LOGICDATA_APP, CONF_LOGICDATA_APP_PROFILE: "phone"
    })
    data = {
        CONF_PAIR_ID: "pair_1",
        CONF_PAIR_MODE: PAIR_MODE_SEPARATE_ADDRESS,
        CONF_BED_TYPE: BED_TYPE_JIECANG_APP,
        CONF_JIECANG_APP_PROFILE: "dreamask",
        CONF_PAIR_CHILDREN: [dict(left), dict(right)],
    }
    entry = MockConfigEntry(domain=DOMAIN, data=data, version=4, minor_version=3)
    entry.add_to_hass(hass)

    await async_migrate_entry(hass, entry)

    assert entry.data[CONF_PROFILE_ID] == "jiecang_app@dreamask"
    children = {child[CONF_SIDE]: child for child in entry.data[CONF_PAIR_CHILDREN]}
    assert children["left"] == {**left, CONF_PROFILE_ID: "jiecang_app@dreamask"}
    assert children["right"] == {**right, CONF_PROFILE_ID: "logicdata_app@phone"}
    record = entry.data[CONF_PROFILE_MIGRATION]
    assert record["sides"] == {
        "left": {
            "profile_id": "jiecang_app@dreamask",
            "fields": {CONF_BED_TYPE: BED_TYPE_JIECANG_APP, CONF_JIECANG_APP_PROFILE: "dreamask"},
        },
        "right": {
            # The parent's app key is inherited but is not this route's key.
            "profile_id": "logicdata_app@phone",
            "fields": {
                CONF_BED_TYPE: BED_TYPE_LOGICDATA_APP,
                CONF_JIECANG_APP_PROFILE: "dreamask",
                CONF_LOGICDATA_APP_PROFILE: "phone",
            },
        },
    }
    # A side never inherits the parent's id.
    view = effective_child_data(entry.data, "right", entry.options)
    assert view[CONF_PROFILE_ID] == "logicdata_app@phone"


async def test_single_address_pair_sides_follow_their_wire_side(hass: HomeAssistant) -> None:
    single = {CONF_ADDRESS: ADDRESS, CONF_BED_TYPE: BED_TYPE_SBI, CONF_PROTOCOL_VARIANT: "both"}
    data = {
        **single,
        CONF_PAIR_ID: "pair_2",
        CONF_PAIR_MODE: PAIR_MODE_SINGLE_ADDRESS,
        CONF_PAIR_CHILDREN: [
            _side("left", ADDRESS, **{CONF_BED_TYPE: BED_TYPE_SBI, CONF_PROTOCOL_VARIANT: "side_a"}),
            _side("right", ADDRESS, **{CONF_BED_TYPE: BED_TYPE_SBI, CONF_PROTOCOL_VARIANT: "side_b"}),
        ],
    }
    entry = MockConfigEntry(domain=DOMAIN, data=data, version=4, minor_version=3)
    entry.add_to_hass(hass)

    await async_migrate_entry(hass, entry)

    assert entry.data[CONF_PROFILE_ID] == "sbi:both"
    assert [child[CONF_PROFILE_ID] for child in entry.data[CONF_PAIR_CHILDREN]] == [
        "sbi:side_a",
        "sbi:side_b",
    ]


async def test_setup_sync_follows_edits_to_saved_fields(hass: HomeAssistant) -> None:
    """Configure, repairs and corrections edit fields; setup re-derives the ids."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_ADDRESS: ADDRESS,
            CONF_BED_TYPE: BED_TYPE_LINAK,
            CONF_PROFILE_ID: "okimat",
            CONF_PAIR_ID: "pair_3",
            CONF_PAIR_CHILDREN: [
                _side("left", ADDRESS, **{CONF_BED_TYPE: "keeson", CONF_PROFILE_ID: "stale"}),
            ],
        },
        # A parent option overrides the side's variant, so its id follows.
        options={CONF_PROTOCOL_VARIANT: "sino"},
        version=5,
    )
    entry.add_to_hass(hass)

    _async_sync_profile_ids(hass, entry)

    assert entry.data[CONF_PROFILE_ID] == BED_TYPE_LINAK
    assert entry.data[CONF_PAIR_CHILDREN][0][CONF_PROFILE_ID] == "keeson:sino"
    synced = dict(entry.data)
    _async_sync_profile_ids(hass, entry)
    assert dict(entry.data) == synced


def _coordinator(hass: HomeAssistant, **data: Any) -> AdjustableBedCoordinator:
    entry = MockConfigEntry(
        domain=DOMAIN, data={CONF_ADDRESS: ADDRESS, CONF_NAME: "Bed", **data}, version=5
    )
    entry.add_to_hass(hass)
    return AdjustableBedCoordinator(hass, entry)


async def test_coordinator_builds_from_the_stored_profile_id(hass: HomeAssistant) -> None:
    coordinator = _coordinator(
        hass, **{CONF_BED_TYPE: "keeson", CONF_PROTOCOL_VARIANT: "sino", CONF_PROFILE_ID: "keeson:sino"}
    )
    assert (coordinator.profile_id, coordinator.bed_type) == ("keeson:sino", "keeson")
    assert coordinator._protocol_variant == "sino"

    # Data from before setup derived an id resolves it from the fields.
    coordinator = _coordinator(hass, **{CONF_BED_TYPE: BED_TYPE_LINAK})
    assert (coordinator.profile_id, coordinator._protocol_variant) == (BED_TYPE_LINAK, VARIANT_AUTO)


async def test_runtime_correction_stores_the_corrected_profile_id(hass: HomeAssistant) -> None:
    coordinator = _coordinator(
        hass, **{CONF_BED_TYPE: BED_TYPE_MALOUF_NEW_OKIN, CONF_PROFILE_ID: BED_TYPE_MALOUF_NEW_OKIN}
    )

    coordinator._apply_runtime_bed_type_correction(BED_TYPE_MALOUF_LEGACY_OKIN)

    assert coordinator.profile_id == BED_TYPE_MALOUF_LEGACY_OKIN
    assert coordinator.entry.data[CONF_PROFILE_ID] == BED_TYPE_MALOUF_LEGACY_OKIN


def _wire_tool() -> Any:
    spec = importlib.util.spec_from_file_location("wire_snapshot", WIRE_SNAPSHOT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


async def _build_or_error(tool: Any, scenario: Any, layout: dict[str, Any]) -> type:
    clock = tool.FakeClock()
    with tool.deterministic_process_state(), tool.virtual_time(clock):
        client = tool.FakeClient(tool.Recorder(clock), layout, scenario.replies)
        try:
            return type(await tool._build(scenario, client))
        except Exception as err:  # noqa: BLE001 - a build error must match too
            return type(err)


async def test_wire_snapshot_routes_build_identically_from_their_profile_ids() -> None:
    """The snapshot builds from bed types; their profile ids build the same controllers."""
    tool = _wire_tool()
    layouts = json.loads(tool.LAYOUTS_PATH.read_text())
    for scenario in tool.build_scenarios():
        data = {**tool._base_entry_data(), **scenario.entry_data, CONF_BED_TYPE: scenario.bed_type}
        if scenario.protocol_variant is not None:
            data[CONF_PROTOCOL_VARIANT] = scenario.protocol_variant
        route = profile_route(resolve_profile_id(data))
        assert (route.bed_type, route.variant) == (scenario.bed_type, scenario.protocol_variant)
        if (key := app_profile_key(route.bed_type, route.variant)) is not None:
            assert route.app_profile == data.get(key), scenario.id
        layout = layouts[scenario.layout_id or scenario.id]
        rebuilt = replace(scenario, bed_type=route.bed_type, protocol_variant=route.variant)
        assert await _build_or_error(tool, rebuilt, layout) is await _build_or_error(
            tool, scenario, layout
        ), scenario.id


def test_simple_controllers_are_reachable_through_their_profile_ids() -> None:
    for bed_type in _SIMPLE_CONTROLLERS:
        assert profile_route(resolve_profile_id({CONF_BED_TYPE: bed_type})).bed_type == bed_type
