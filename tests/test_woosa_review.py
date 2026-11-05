"""Existing generic Solace entries are asked once whether they use Woosa Sleep (#676)."""

from typing import Any
from unittest.mock import patch

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed import async_migrate_entry
from custom_components.adjustable_bed.const import (
    BED_TYPE_SOLACE,
    CONF_BED_TYPE,
    CONF_PROFILE_REVIEW_KEPT,
    CONF_PROFILE_REVIEW_PENDING,
    CONF_PROTOCOL_VARIANT,
    DOMAIN,
    SOLACE_VARIANT_WOOSA,
)
from custom_components.adjustable_bed.profile_review import async_refresh_profile_review_issue
from tests.test_profile_review import _HISTORY, ADDRESS, _issue, _open

WOOSA = f"{BED_TYPE_SOLACE}:{SOLACE_VARIANT_WOOSA}"


def reviewed_entry(hass: HomeAssistant, **data: Any) -> MockConfigEntry:
    """A Solace entry that v4.3 already reviewed, with nothing left to offer then."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Guest bed",
        unique_id=ADDRESS,
        data={
            CONF_ADDRESS: ADDRESS,
            CONF_NAME: "Guest bed",
            CONF_BED_TYPE: BED_TYPE_SOLACE,
            **data,
        },
        version=4,
        minor_version=3,
    )
    entry.add_to_hass(hass)
    return entry


async def migrated(hass: HomeAssistant, **data: Any) -> MockConfigEntry:
    entry = reviewed_entry(hass, **data)
    await async_migrate_entry(hass, entry)
    assert entry.version == 5
    return entry


@pytest.mark.parametrize(
    ("data", "mark"),
    [
        ({}, "solace:auto"),
        ({CONF_PROTOCOL_VARIANT: "auto"}, "solace:auto"),
        # Keep was answered before Woosa Sleep was offered for the route.
        (
            {CONF_PROFILE_REVIEW_KEPT: {"route": "solace:auto", "apps": ["motion_bed"]}},
            "solace:auto",
        ),
        # The entry already chose Woosa Sleep.
        ({CONF_PROTOCOL_VARIANT: SOLACE_VARIANT_WOOSA}, None),
    ],
)
async def test_the_v5_migration_asks_reviewed_solace_entries_about_woosa(
    hass: HomeAssistant, data: dict[str, Any], mark: str | None
) -> None:
    entry = await migrated(hass, **data)
    assert entry.data.get(CONF_PROFILE_REVIEW_PENDING) == mark


async def test_keep_answers_the_woosa_review_for_good(hass: HomeAssistant) -> None:
    entry = await migrated(hass)
    with patch(_HISTORY, return_value=None):
        async_refresh_profile_review_issue(hass, entry)
        issue = _issue(hass, entry)
        assert issue is not None and issue.translation_key == "app_profile_woosa"
        flow, form = await _open(hass, entry)
        # Solace has a guided change: the repair offers it, or Keep.
        assert form["step_id"] == "managed"
        assert form["description_placeholders"]["name"] == "Guest bed"
        result = await flow.async_step_init({"choice": "keep"})
        assert result["type"] == "create_entry"
        assert WOOSA in entry.data[CONF_PROFILE_REVIEW_KEPT]["apps"]
        async_refresh_profile_review_issue(hass, entry)
    assert _issue(hass, entry) is None
    assert CONF_PROFILE_REVIEW_PENDING not in entry.data


async def test_choosing_woosa_continues_in_the_guided_change(
    hass: HomeAssistant, enable_custom_integrations: None
) -> None:
    entry = await migrated(hass)
    manager = hass.config_entries.flow
    with patch(_HISTORY, return_value=None):
        async_refresh_profile_review_issue(hass, entry)
        flow, _form = await _open(hass, entry)
        handoff = await flow.async_step_init({"choice": "configure"})
        assert handoff["reason"] == "migration_setup_started"
        flow_id = handoff["next_flow"][1]
        result = await manager.async_configure(flow_id, {"choice": "woosa"})
        assert result["step_id"] == "solace_woosa"
        result = await manager.async_configure(flow_id, {})
        assert result["step_id"] == "migration_confirm"
        manager.async_abort(flow_id)
    # The repair stays open until a saved change or Keep.
    assert entry.data[CONF_PROFILE_REVIEW_PENDING] == "solace:auto"
    assert entry.data[CONF_BED_TYPE] == BED_TYPE_SOLACE
    assert _issue(hass, entry) is not None
