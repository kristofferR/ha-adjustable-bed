"""The repair naming automations and scripts that use an entity the sweep removed."""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir
from homeassistant.setup import async_setup_component
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed import async_migrate_entry, async_remove_entry
from custom_components.adjustable_bed.beds.bedsense import BedSenseController
from custom_components.adjustable_bed.const import (
    CONF_BED_TYPE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_HAS_MASSAGE,
    CONF_MOTOR_COUNT,
    CONF_PREFERRED_ADAPTER,
    CONF_PROTOCOL_VARIANT,
    DOMAIN,
)
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.entity_retypes import (
    ISSUE_PREFIX as RETYPED_PREFIX,
)
from custom_components.adjustable_bed.entity_retypes import (
    async_carry_over_retyped_entities,
)
from custom_components.adjustable_bed.removed_entities import (
    _STORE,
    ISSUE_PREFIX,
    async_report_removed_entities,
    async_setup_removed_entities,
)
from tests.conftest import make_controller_mock
from tests.test_entity_sweep import async_setup_platforms_and_sweep

ADDRESS = "AA:BB:CC:DD:EE:61"


def _automation(alias: str, entity_id: str, action: str = "button.press") -> dict[str, Any]:
    return {
        "alias": alias,
        "trigger": {"platform": "event", "event_type": "test"},
        "action": {"action": action, "target": {"entity_id": entity_id}},
    }


def _entry(hass: HomeAssistant, **data: Any) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Bed",
        version=4,
        minor_version=3,
        unique_id=ADDRESS,
        data={
            CONF_ADDRESS: ADDRESS,
            CONF_NAME: "Bed",
            CONF_MOTOR_COUNT: 2,
            CONF_DISABLE_ANGLE_SENSING: True,
            CONF_PREFERRED_ADAPTER: "auto",
            **data,
        },
    )
    entry.add_to_hass(hass)
    return entry


def _issue(hass: HomeAssistant, entry: MockConfigEntry) -> ir.IssueEntry | None:
    return ir.async_get(hass).async_get_issue(DOMAIN, ISSUE_PREFIX + entry.entry_id)


async def test_a_folded_timer_button_an_automation_presses_is_named(hass: HomeAssistant) -> None:
    """A 4.4.2 BedSense bed's timer buttons became the Massage: Timer select."""
    await async_setup_removed_entities(hass)
    # The data 4.4.2 stored for a BedSense bed, and the buttons it created.
    entry = _entry(
        hass, **{CONF_BED_TYPE: "bedsense", CONF_PROTOCOL_VARIANT: "bedsense_3", CONF_HAS_MASSAGE: True}
    )
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id, identifiers={(DOMAIN, ADDRESS)}, name="Bed"
    )
    registry = er.async_get(hass)
    for minutes in (10, 20, 30):
        registry.async_get_or_create(
            "button",
            DOMAIN,
            f"{ADDRESS}_bedsense_massage_timer_{minutes}",
            config_entry=entry,
            device_id=device.id,
            suggested_object_id=f"bed_massage_{minutes}_minute_selection",
            has_entity_name=True,
            original_name=f"Massage {minutes}-minute selection",
        )
    assert await async_setup_component(
        hass,
        "automation",
        {"automation": _automation("Massage", "button.bed_massage_10_minute_selection")},
    )
    await async_migrate_entry(hass, entry)
    coordinator = AdjustableBedCoordinator(hass, entry)
    coordinator._controller = BedSenseController(coordinator, variant="bedsense_3")  # type: ignore[assignment]

    await async_setup_platforms_and_sweep(hass, entry, coordinator)
    await hass.async_block_till_done()

    assert not registry.async_is_registered("button.bed_massage_10_minute_selection")
    issue = _issue(hass, entry)
    assert issue is not None
    assert issue.translation_placeholders["entities"] == (
        "- Bed Massage 10-minute selection (button.bed_massage_10_minute_selection): "
        "automation.massage"
    )
    # The two buttons nothing presses are forgotten.
    assert [r["entity_id"] for r in hass.data[_STORE][1][entry.entry_id]] == [
        "button.bed_massage_10_minute_selection"
    ]

    # The user edits the automation; the next start withdraws the repair for good.
    with patch(
        "custom_components.adjustable_bed.removed_entities.entity_users", return_value=set()
    ):
        async_report_removed_entities(hass, entry)
        await hass.async_block_till_done()
    assert _issue(hass, entry) is None
    async_report_removed_entities(hass, entry)
    await hass.async_block_till_done()
    assert _issue(hass, entry) is None
    assert entry.entry_id not in hass.data[_STORE][1]


async def test_a_device_action_by_registry_id_is_found_and_a_deleted_bed_forgotten(
    hass: HomeAssistant,
) -> None:
    await async_setup_removed_entities(hass)
    entry = _entry(hass, **{CONF_BED_TYPE: "okimat", CONF_HAS_MASSAGE: False})
    row = er.async_get(hass).async_get_or_create(
        "number", DOMAIN, f"{ADDRESS}_massage_head_intensity", config_entry=entry
    )
    assert await async_setup_component(
        hass,
        "automation",
        {
            "automation": {
                "alias": "By device",
                "trigger": {"platform": "event", "event_type": "test"},
                "action": {
                    "device_id": "abc",
                    "domain": "number",
                    "entity_id": row.id,
                    "type": "set_value",
                    "value": 1,
                },
            }
        },
    )
    await async_setup_platforms_and_sweep(
        hass, entry, _coordinator(hass, entry, make_controller_mock())
    )
    await hass.async_block_till_done()
    assert "automation.by_device" in _issue(hass, entry).translation_placeholders["entities"]  # type: ignore[union-attr]

    await async_remove_entry(hass, entry)
    assert entry.entry_id not in hass.data[_STORE][1]


async def test_entities_the_user_disabled_or_deleted_are_not_named(hass: HomeAssistant) -> None:
    await async_setup_removed_entities(hass)
    entry = _entry(hass, **{CONF_BED_TYPE: "okimat", CONF_HAS_MASSAGE: False})
    registry = er.async_get(hass)
    disabled = registry.async_get_or_create(
        "number",
        DOMAIN,
        f"{ADDRESS}_massage_head_intensity",
        config_entry=entry,
        disabled_by=er.RegistryEntryDisabler.USER,
    )
    deleted = registry.async_get_or_create(
        "number", DOMAIN, f"{ADDRESS}_massage_foot_intensity", config_entry=entry
    )
    registry.async_remove(deleted.entity_id)
    assert await async_setup_component(
        hass,
        "automation",
        {
            "automation": [
                _automation("Head", disabled.entity_id, "number.set_value"),
                _automation("Foot", deleted.entity_id, "number.set_value"),
            ]
        },
    )

    await async_setup_platforms_and_sweep(
        hass, entry, _coordinator(hass, entry, make_controller_mock())
    )
    await hass.async_block_till_done()

    assert not registry.async_is_registered(disabled.entity_id)
    assert _issue(hass, entry) is None


async def test_a_retyped_entity_is_named_only_by_its_own_repair(hass: HomeAssistant) -> None:
    await async_setup_removed_entities(hass)
    entry = _entry(hass, **{CONF_BED_TYPE: "okimat", CONF_HAS_MASSAGE: False})
    er.async_get(hass).async_get_or_create(
        "switch",
        DOMAIN,
        f"{ADDRESS}_under_bed_lights",
        config_entry=entry,
        suggested_object_id="bed_under_bed_lights",
    )
    assert await async_setup_component(
        hass,
        "automation",
        {"automation": _automation("Night", "switch.bed_under_bed_lights", "switch.turn_on")},
    )
    coordinator = _coordinator(
        hass, entry, make_controller_mock(supports_discrete_light_control=True)
    )

    async_carry_over_retyped_entities(hass, entry, coordinator)
    await async_setup_platforms_and_sweep(hass, entry, coordinator)
    await hass.async_block_till_done()

    issues = ir.async_get(hass)
    assert issues.async_get_issue(DOMAIN, RETYPED_PREFIX + entry.entry_id) is not None
    assert _issue(hass, entry) is None


def _coordinator(
    hass: HomeAssistant, entry: MockConfigEntry, controller: object
) -> AdjustableBedCoordinator:
    coordinator = AdjustableBedCoordinator(hass, entry)
    coordinator._controller = controller  # type: ignore[assignment]
    return coordinator
