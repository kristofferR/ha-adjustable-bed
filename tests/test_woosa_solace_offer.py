"""Existing generic Solace entries are asked once whether they use Woosa Sleep (#676)."""

from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from homeassistant.components.repairs import repairs_flow_manager
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import issue_registry as ir
from homeassistant.setup import async_setup_component
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed import async_migrate_entry
from custom_components.adjustable_bed.const import (
    BED_TYPE_SOLACE,
    CONF_BED_TYPE,
    CONF_PAIR_CHILDREN,
    CONF_PAIR_ID,
    CONF_PAIR_MODE,
    CONF_PROFILE_REVIEW_KEPT,
    CONF_PROFILE_REVIEW_PENDING,
    CONF_PROTOCOL_VARIANT,
    CONF_SIDE,
    DOMAIN,
    PAIR_MODE_SEPARATE_ADDRESS,
    SOLACE_SERVICE_UUID,
    SOLACE_VARIANT_WOOSA,
)
from custom_components.adjustable_bed.profile_recommendations import (
    ISSUE_PREFIX,
    _watches,
    async_watch_profile_recommendations,
)
from custom_components.adjustable_bed.profile_review import (
    async_refresh_profile_review_issue,
    carry_profile_review,
    profile_review_mark,
)
from tests.test_profile_recommendations import HISTORY as RECOMMENDATION_HISTORY
from tests.test_profile_recommendations import REGISTER, coordinator
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
        # Handing off alone leaves the repair open until a saved change or Keep.
        assert entry.data[CONF_PROFILE_REVIEW_PENDING] == "solace:auto"
        assert _issue(hass, entry) is not None
        result = await manager.async_configure(flow_id, {"action": "apply"})
        assert result["reason"] == "migration_applied"
        async_refresh_profile_review_issue(hass, entry)
    assert entry.data[CONF_PROTOCOL_VARIANT] == SOLACE_VARIANT_WOOSA
    assert CONF_PROFILE_REVIEW_PENDING not in entry.data
    assert _issue(hass, entry) is None


async def test_keep_on_the_guided_review_answers_the_woosa_repair(
    hass: HomeAssistant, enable_custom_integrations: None
) -> None:
    entry = await migrated(hass)
    manager = hass.config_entries.flow
    with patch(_HISTORY, return_value=None):
        async_refresh_profile_review_issue(hass, entry)
        flow, _form = await _open(hass, entry)
        handoff = await flow.async_step_init({"choice": "configure"})
        flow_id = handoff["next_flow"][1]
        await manager.async_configure(flow_id, {"choice": "woosa"})
        await manager.async_configure(flow_id, {})
        result = await manager.async_configure(flow_id, {"action": "keep"})
        assert result["reason"] == "migration_kept"
        async_refresh_profile_review_issue(hass, entry)
    assert entry.data[CONF_BED_TYPE] == BED_TYPE_SOLACE
    assert WOOSA in entry.data[CONF_PROFILE_REVIEW_KEPT]["apps"]
    assert _issue(hass, entry) is None


async def test_the_woosa_repair_opens_and_keeps_through_the_repairs_manager(
    hass: HomeAssistant, enable_custom_integrations: None
) -> None:
    assert await async_setup_component(hass, "repairs", {})
    assert await async_setup_component(hass, DOMAIN, {})
    entry = await migrated(hass)
    with patch(_HISTORY, return_value=None):
        async_refresh_profile_review_issue(hass, entry)
        issue = _issue(hass, entry)
        assert issue is not None
        manager = repairs_flow_manager(hass)
        assert manager is not None
        form = await manager.async_init(DOMAIN, data={"issue_id": issue.issue_id})
        assert form["step_id"] == "managed"
        result = await manager.async_configure(form["flow_id"], {"choice": "keep"})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert WOOSA in entry.data[CONF_PROFILE_REVIEW_KEPT]["apps"]


async def test_a_kept_woosa_review_is_not_asked_again_by_a_recommendation(
    hass: HomeAssistant,
) -> None:
    entry = await migrated(hass)
    with patch(_HISTORY, return_value=None):
        async_refresh_profile_review_issue(hass, entry)
        flow, _form = await _open(hass, entry)
        await flow.async_step_init({"choice": "keep"})
    # The bed then advertises a QMS name, which several apps share.
    seen = MagicMock(
        address=ADDRESS,
        service_uuids=[SOLACE_SERVICE_UUID],
        manufacturer_data={},
        service_data={},
    )
    seen.name = "QMS-i06"
    coord = coordinator()
    coord.bed_type = BED_TYPE_SOLACE
    coord.controller.protocol_diagnostics = {}
    with patch(RECOMMENDATION_HISTORY, return_value=seen), patch(REGISTER):
        await async_watch_profile_recommendations(hass, entry, ((None, coord),))
    target = _watches(hass)[f"{ISSUE_PREFIX}{entry.entry_id}_standalone"]
    assert target.recommendation is not None
    assert target.recommendation.choices == (WOOSA,)
    assert ir.async_get(hass).async_get_issue(DOMAIN, target.issue_id) is None


def test_a_split_pair_keeps_its_open_woosa_review_over_an_older_keep() -> None:
    single = {CONF_ADDRESS: ADDRESS, CONF_BED_TYPE: BED_TYPE_SOLACE}
    pair = {
        **single,
        CONF_PAIR_ID: "pair",
        CONF_PAIR_MODE: PAIR_MODE_SEPARATE_ADDRESS,
        CONF_PAIR_CHILDREN: [
            {CONF_SIDE: "left", **single},
            {CONF_SIDE: "right", CONF_ADDRESS: "AA:BB:CC:DD:EE:31", CONF_BED_TYPE: BED_TYPE_SOLACE},
        ],
    }
    mark = profile_review_mark(pair)
    # Kept before Woosa Sleep was offered, then marked again by the v5 migration.
    pair[CONF_PROFILE_REVIEW_KEPT] = {"route": mark, "apps": []}
    pair[CONF_PROFILE_REVIEW_PENDING] = mark
    target = dict(single)
    carry_profile_review(pair, target)
    assert target[CONF_PROFILE_REVIEW_PENDING] == "solace:auto"
