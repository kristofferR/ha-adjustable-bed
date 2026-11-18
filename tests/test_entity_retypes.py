"""A retyped entity keeps its object ID and the user's settings."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from homeassistant.core import HomeAssistant
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir
from homeassistant.setup import async_setup_component
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed.const import BED_TYPE_OCTO, DOMAIN
from custom_components.adjustable_bed.entity_retypes import (
    ISSUE_PREFIX,
    async_carry_over_retyped_entities,
    async_retyped_entities_built,
)

ADDRESS = "AA:BB:CC:DD:EE:01"
# What the platforms build: the light and the shared massage timer.
BUILT = frozenset(
    {("light", f"{ADDRESS}_under_bed_lights"), ("select", f"{ADDRESS}_massage_timer")}
)
NIGHT_LIGHT = {
    "automation": {
        "alias": "Night light",
        "trigger": {"platform": "event", "event_type": "test"},
        "action": {
            "action": "switch.turn_on",
            "target": {"entity_id": "switch.bed_under_bed_lights"},
        },
    }
}


def _runtime(bed_type: str = "keeson", suffix: str = "") -> SimpleNamespace:
    return SimpleNamespace(
        bed_type=bed_type, entity_unique_id=lambda key: f"{ADDRESS}_{key}{suffix}"
    )


def _entry(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(domain=DOMAIN, title="Bed", data={"address": ADDRESS})
    entry.add_to_hass(hass)
    return entry


def _row(
    registry: er.EntityRegistry, entry: MockConfigEntry, domain: str, key: str, object_id: str
) -> er.RegistryEntry:
    return registry.async_get_or_create(
        domain, DOMAIN, f"{ADDRESS}_{key}", config_entry=entry, suggested_object_id=object_id
    )


async def test_light_takes_over_the_switch_with_the_users_settings(hass: HomeAssistant) -> None:
    registry = er.async_get(hass)
    entry = _entry(hass)
    old = _row(registry, entry, "switch", "under_bed_lights", "bed_under_bed_lights")
    area = ar.async_get(hass).async_create("Bedroom")
    registry.async_update_entity(
        old.entity_id,
        name="Glow",
        icon="mdi:lamp",
        area_id=area.id,
        labels={"night"},
        aliases=["bed glow"],
        disabled_by=er.RegistryEntryDisabler.USER,
        hidden_by=er.RegistryEntryHider.USER,
    )
    registry.async_update_entity_options(old.entity_id, "conversation", {"should_expose": False})
    registry.async_update_entity(old.entity_id, categories={"automation": "lighting"})

    async_carry_over_retyped_entities(hass, entry, _runtime())

    assert registry.async_get("switch.bed_under_bed_lights") is None
    new = registry.async_get("light.bed_under_bed_lights")
    assert new is not None
    assert new.unique_id == f"{ADDRESS}_under_bed_lights"
    assert (new.name, new.icon, new.area_id) == ("Glow", "mdi:lamp", area.id)
    assert new.labels == {"night"}
    assert list(new.aliases) == ["bed glow"]
    assert new.disabled_by is er.RegistryEntryDisabler.USER
    assert new.hidden_by is er.RegistryEntryHider.USER
    assert new.options["conversation"] == {"should_expose": False}
    assert new.categories == {"automation": "lighting"}

    # A second run, or a fresh install, changes nothing.
    async_carry_over_retyped_entities(hass, entry, _runtime())
    assert [e.entity_id for e in er.async_entries_for_config_entry(registry, entry.entry_id)] == [
        "light.bed_under_bed_lights"
    ]


async def test_octo_keeps_its_switch(hass: HomeAssistant) -> None:
    registry = er.async_get(hass)
    entry = _entry(hass)
    _row(registry, entry, "switch", "under_bed_lights", "bed_under_bed_lights")
    async_carry_over_retyped_entities(hass, entry, _runtime(BED_TYPE_OCTO))
    assert registry.async_get("switch.bed_under_bed_lights") is not None
    assert registry.async_get("light.bed_under_bed_lights") is None


async def test_text_sleep_sensor_becomes_a_binary_sensor(hass: HomeAssistant) -> None:
    registry = er.async_get(hass)
    entry = _entry(hass)
    old = _row(registry, entry, "sensor", "goodvibe_L_occupancy", "bed_left_occupancy")
    registry.async_update_entity(
        old.entity_id, name="Kris in bed", disabled_by=er.RegistryEntryDisabler.INTEGRATION
    )
    async_carry_over_retyped_entities(hass, entry, _runtime())
    new = registry.async_get("binary_sensor.bed_left_occupancy")
    assert new is not None and new.name == "Kris in bed"
    # Only a user's disable carries over; v5 enables the reading by default.
    assert new.disabled_by is None
    assert registry.async_get(old.entity_id) is None


async def test_presence_disabled_by_the_integration_is_enabled_once(hass: HomeAssistant) -> None:
    registry = er.async_get(hass)
    entry = _entry(hass)
    row = _row(registry, entry, "binary_sensor", "bed_presence_left", "bed_left_presence")
    registry.async_update_entity(row.entity_id, disabled_by=er.RegistryEntryDisabler.INTEGRATION)
    async_carry_over_retyped_entities(hass, entry, _runtime())
    assert registry.async_get(row.entity_id).disabled_by is None

    registry.async_update_entity(row.entity_id, disabled_by=er.RegistryEntryDisabler.USER)
    async_carry_over_retyped_entities(hass, entry, _runtime())
    assert registry.async_get(row.entity_id).disabled_by is er.RegistryEntryDisabler.USER


async def test_each_side_of_a_paired_bed_is_carried_over(hass: HomeAssistant) -> None:
    registry = er.async_get(hass)
    entry = _entry(hass)
    for side in ("left", "right"):
        _row(registry, entry, "switch", f"under_bed_lights_{side}", f"bed_{side}_lights")
    sides = (_runtime(suffix="_left"), _runtime(suffix="_right"))
    with patch(
        "custom_components.adjustable_bed.entity_retypes.entity_runtimes", return_value=sides
    ):
        async_carry_over_retyped_entities(hass, entry, SimpleNamespace())
    for side in ("left", "right"):
        assert registry.async_get(f"switch.bed_{side}_lights") is None
        assert registry.async_get(f"light.bed_{side}_lights").unique_id == (
            f"{ADDRESS}_under_bed_lights_{side}"
        )


async def test_repair_names_only_automations_that_use_the_old_entity(hass: HomeAssistant) -> None:
    registry = er.async_get(hass)
    entry = _entry(hass)
    _row(registry, entry, "switch", "under_bed_lights", "bed_under_bed_lights")
    _row(registry, entry, "sensor", "goodvibe_L_snore", "bed_left_snoring")
    assert await async_setup_component(
        hass,
        "automation",
        {
            "automation": {
                "alias": "Night light",
                "trigger": {"platform": "event", "event_type": "test"},
                "action": {
                    "action": "switch.turn_on",
                    "target": {"entity_id": "switch.bed_under_bed_lights"},
                },
            }
        },
    )
    async_carry_over_retyped_entities(hass, entry, _runtime())
    async_retyped_entities_built(hass, entry, BUILT)
    await hass.async_block_till_done()
    issue = ir.async_get(hass).async_get_issue(DOMAIN, ISSUE_PREFIX + entry.entry_id)
    assert issue is not None
    entities = issue.translation_placeholders["entities"]
    assert "switch.bed_under_bed_lights → light.bed_under_bed_lights" in entities
    assert "automation.night_light" in entities
    assert "bed_left_snoring" not in entities

    await hass.config_entries.async_remove(entry.entry_id)
    assert ir.async_get(hass).async_get_issue(DOMAIN, ISSUE_PREFIX + entry.entry_id) is None


async def test_no_repair_without_references(hass: HomeAssistant) -> None:
    registry = er.async_get(hass)
    entry = _entry(hass)
    _row(registry, entry, "switch", "under_bed_lights", "bed_under_bed_lights")
    assert await async_setup_component(hass, "automation", {"automation": []})
    async_carry_over_retyped_entities(hass, entry, _runtime())
    async_retyped_entities_built(hass, entry, BUILT)
    await hass.async_block_till_done()
    assert ir.async_get(hass).async_get_issue(DOMAIN, ISSUE_PREFIX + entry.entry_id) is None


async def test_area_carries_over_for_an_entity_with_its_default_name(hass: HomeAssistant) -> None:
    registry = er.async_get(hass)
    entry = _entry(hass)
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id, identifiers={(DOMAIN, ADDRESS)}
    )
    old = registry.async_get_or_create(
        "switch",
        DOMAIN,
        f"{ADDRESS}_under_bed_lights",
        config_entry=entry,
        device_id=device.id,
        suggested_object_id="bed_under_bed_lights",
        has_entity_name=True,
        original_name="Under-bed lights",
        translation_key="under_bed_lights",
    )
    area = ar.async_get(hass).async_create("Bedroom")
    registry.async_update_entity(old.entity_id, area_id=area.id)
    async_carry_over_retyped_entities(hass, entry, _runtime())
    new = registry.async_get("light.bed_under_bed_lights")
    assert new is not None and new.name is None and new.area_id == area.id
    assert registry.async_get(old.entity_id) is None


async def test_a_new_unique_id_on_the_same_platform_keeps_the_row(hass: HomeAssistant) -> None:
    registry = er.async_get(hass)
    entry = _entry(hass)
    old = _row(
        registry, entry, "select", "controller_select_ore_comfort_massage_timer", "bed_timer"
    )
    registry.async_update_entity(old.entity_id, name="Timer")
    async_carry_over_retyped_entities(hass, entry, _runtime())
    row = registry.async_get("select.bed_timer")
    assert row is not None
    assert (row.id, row.name, row.unique_id) == (old.id, "Timer", f"{ADDRESS}_massage_timer")


async def test_repair_finds_automations_by_registry_id_and_changed_options(
    hass: HomeAssistant,
) -> None:
    registry = er.async_get(hass)
    entry = _entry(hass)
    light = _row(registry, entry, "switch", "under_bed_lights", "bed_under_bed_lights")
    timer = _row(
        registry, entry, "select", "controller_select_ore_comfort_massage_timer", "bed_timer"
    )
    assert await async_setup_component(
        hass,
        "automation",
        {
            "automation": [
                {
                    "alias": "By ID",
                    "trigger": {"platform": "event", "event_type": "test"},
                    "action": {"action": "switch.turn_on", "target": {"entity_id": light.id}},
                },
                {
                    "alias": "Timer",
                    "trigger": {"platform": "event", "event_type": "test"},
                    "action": {
                        "action": "select.select_option",
                        "target": {"entity_id": timer.entity_id},
                        "data": {"option": "20"},
                    },
                },
            ]
        },
    )
    async_carry_over_retyped_entities(hass, entry, _runtime())
    async_retyped_entities_built(hass, entry, BUILT)
    await hass.async_block_till_done()
    issue = ir.async_get(hass).async_get_issue(DOMAIN, ISSUE_PREFIX + entry.entry_id)
    assert issue is not None
    entities = issue.translation_placeholders["entities"]
    assert "switch.bed_under_bed_lights → light.bed_under_bed_lights: automation.by_id" in entities
    assert "select.bed_timer (its options changed): automation.timer" in entities


async def test_repair_waits_until_the_sweep_confirms_the_replacement(
    hass: HomeAssistant,
) -> None:
    """A reload or a bed still discovering capabilities reports nothing yet."""
    registry = er.async_get(hass)
    entry = _entry(hass)
    _row(registry, entry, "switch", "under_bed_lights", "bed_under_bed_lights")
    assert await async_setup_component(hass, "automation", NIGHT_LIGHT)
    async_carry_over_retyped_entities(hass, entry, _runtime())
    await hass.async_block_till_done()
    issues = ir.async_get(hass)
    assert issues.async_get_issue(DOMAIN, ISSUE_PREFIX + entry.entry_id) is None
    # Discovery finishes: the bed builds the light.
    async_retyped_entities_built(hass, entry, BUILT)
    await hass.async_block_till_done()
    assert issues.async_get_issue(DOMAIN, ISSUE_PREFIX + entry.entry_id) is not None


async def test_no_repair_for_a_replacement_the_bed_does_not_provide(hass: HomeAssistant) -> None:
    registry = er.async_get(hass)
    entry = _entry(hass)
    _row(registry, entry, "switch", "under_bed_lights", "bed_under_bed_lights")
    assert await async_setup_component(hass, "automation", NIGHT_LIGHT)
    async_carry_over_retyped_entities(hass, entry, _runtime())
    async_retyped_entities_built(hass, entry, frozenset())
    await hass.async_block_till_done()
    assert ir.async_get(hass).async_get_issue(DOMAIN, ISSUE_PREFIX + entry.entry_id) is None
