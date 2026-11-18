"""A retyped entity keeps its object ID and the user's settings."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from homeassistant.core import HomeAssistant
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir
from homeassistant.setup import async_setup_component
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed.const import BED_TYPE_OCTO, DOMAIN
from custom_components.adjustable_bed.entity_retypes import (
    ISSUE_PREFIX,
    async_carry_over_retyped_entities,
)

ADDRESS = "AA:BB:CC:DD:EE:01"


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
    await hass.async_block_till_done()
    assert ir.async_get(hass).async_get_issue(DOMAIN, ISSUE_PREFIX + entry.entry_id) is None
