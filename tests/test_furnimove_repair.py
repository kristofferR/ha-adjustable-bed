"""Legacy RF receivers get an offline, identity-preserving layout repair."""

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.const import CONF_ADDRESS
from homeassistant.helpers import issue_registry as ir
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed.const import (
    BED_TYPE_FURNIMOVE,
    BED_TYPE_OKIN_DOT,
    BED_TYPE_OKIN_RF_ECO_BT,
    BED_TYPE_OKIN_UUID,
    CONF_BED_TYPE,
    CONF_BLE_BOND_ESTABLISHED,
    CONF_FURNIMOVE_REMOTE,
    CONF_MOTOR_COUNT,
    CONF_PAIR_CHILDREN,
    CONF_PAIR_ID,
    CONF_PAIR_MODE,
    CONF_PROTOCOL_VARIANT,
    CONF_SIDE,
    DOMAIN,
    PAIR_MODE_SEPARATE_ADDRESS,
    SIDE_LEFT,
    SIDE_RIGHT,
)
from custom_components.adjustable_bed.furnimove_repair import (
    CONF_FURNIMOVE_ROUTE_KEPT,
    CONF_STAIRCASE_LAYOUT_CONFIRMED,
    FurniMoveLayoutRepairFlow,
    async_clear_furnimove_layout_issues,
    async_refresh_furnimove_layout_issues,
)
from custom_components.adjustable_bed.pairing import effective_child_data
from custom_components.adjustable_bed.repairs import async_create_fix_flow
from custom_components.adjustable_bed.unsupported import create_pairing_required_issue


def _legacy(hass, **kwargs):
    entry = MockConfigEntry(domain=DOMAIN, title="My bed", unique_id="AA:BB:CC:DD:EE:FF", version=4,
        data={CONF_ADDRESS: "AA:BB:CC:DD:EE:FF", CONF_BED_TYPE: BED_TYPE_OKIN_RF_ECO_BT,
              CONF_MOTOR_COUNT: 2, CONF_BLE_BOND_ESTABLISHED: True}, **kwargs)
    entry.add_to_hass(hass)
    return entry


async def test_offline_entry_gets_repair_before_any_connection(hass):
    entry = _legacy(hass)
    from custom_components.adjustable_bed import async_setup_entry

    with patch("custom_components.adjustable_bed.async_register_services", AsyncMock()), patch(
        "custom_components.adjustable_bed.AdjustableBedCoordinator", side_effect=RuntimeError("offline")
    ), pytest.raises(RuntimeError, match="offline"):
        await async_setup_entry(hass, entry)
    issue_id = f"furnimove_layout_{entry.entry_id}_standalone"
    issue = ir.async_get(hass).async_get_issue(DOMAIN, issue_id)
    assert issue is not None and issue.is_fixable
    flow = await async_create_fix_flow(hass, issue_id, issue.data)
    assert isinstance(flow, FurniMoveLayoutRepairFlow)
    flow.hass = hass
    # HA supplies metadata to init, not a submitted form.
    result = await flow.async_step_init({"issue_id": issue_id})
    assert result["step_id"] == "init"
    async_clear_furnimove_layout_issues(hass, entry.entry_id)
    assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id) is None


async def test_bed_repair_preserves_identity_and_clears_obsolete_pairing_issue(hass):
    entry = _legacy(hass, options={CONF_MOTOR_COUNT: 4})
    entry_id, unique_id = entry.entry_id, entry.unique_id
    async_refresh_furnimove_layout_issues(hass, entry)
    await create_pairing_required_issue(hass, entry.data[CONF_ADDRESS], entry.title, entry.entry_id)
    flow = FurniMoveLayoutRepairFlow(entry_id, None)
    flow.hass = hass
    result = await flow.async_step_init({"layout": "furnimove"})
    assert result["step_id"] == "handset"
    assert CONF_FURNIMOVE_REMOTE not in entry.data
    invalid = await flow.async_step_handset({CONF_FURNIMOVE_REMOTE: "not-in-catalog"})
    assert invalid["errors"] == {CONF_FURNIMOVE_REMOTE: "handset_required"}
    assert entry.data[CONF_BED_TYPE] == BED_TYPE_OKIN_RF_ECO_BT
    result = await flow.async_step_handset({CONF_FURNIMOVE_REMOTE: "00000"})
    assert result["type"] == "create_entry"
    assert (entry.entry_id, entry.unique_id, entry.title) == (entry_id, unique_id, "My bed")
    assert entry.data[CONF_ADDRESS] == "AA:BB:CC:DD:EE:FF"
    assert entry.data[CONF_BED_TYPE] == BED_TYPE_FURNIMOVE
    assert entry.data[CONF_MOTOR_COUNT] == 2
    assert CONF_MOTOR_COUNT not in entry.options
    assert CONF_BLE_BOND_ESTABLISHED not in entry.data
    assert not [issue for (domain, _), issue in ir.async_get(hass).issues.items() if domain == DOMAIN]


async def test_confirmed_staircase_is_not_converted_to_a_bed(hass):
    entry = _legacy(hass)
    flow = FurniMoveLayoutRepairFlow(entry.entry_id, None)
    flow.hass = hass
    await flow.async_step_init({"layout": "staircase"})
    assert entry.data[CONF_BED_TYPE] == BED_TYPE_OKIN_RF_ECO_BT
    assert entry.data[CONF_MOTOR_COUNT] == 1
    async_refresh_furnimove_layout_issues(hass, entry)
    assert not ir.async_get(hass).issues


async def test_keep_current_dismisses_repair_without_rewriting_settings(hass):
    """A working OKIMAT bed saved as RF ECO BT keeps its motors and remote (#406)."""
    entry = _legacy(hass, options={CONF_PROTOCOL_VARIANT: "82418"})
    before = (dict(entry.data), dict(entry.options))
    async_refresh_furnimove_layout_issues(hass, entry)
    flow = FurniMoveLayoutRepairFlow(entry.entry_id, None)
    flow.hass = hass
    form = await flow.async_step_init()
    config = form["data_schema"].schema["layout"].config
    assert config["options"] == ["furnimove", "staircase", "keep"]
    assert config["translation_key"] == "furnimove_layout"
    result = await flow.async_step_init({"layout": "keep"})
    assert result["type"] == "create_entry"
    assert dict(entry.data) == {**before[0], CONF_STAIRCASE_LAYOUT_CONFIRMED: True}
    assert dict(entry.options) == before[1]
    assert not ir.async_get(hass).issues


async def test_paired_repair_only_changes_selected_physical_side(hass):
    entry = MockConfigEntry(domain=DOMAIN, data={
        CONF_PAIR_ID: "pair_test", CONF_PAIR_MODE: PAIR_MODE_SEPARATE_ADDRESS,
        CONF_PAIR_CHILDREN: [
            {CONF_SIDE: side, CONF_ADDRESS: address, CONF_BED_TYPE: BED_TYPE_OKIN_RF_ECO_BT,
             CONF_MOTOR_COUNT: 2} for side, address in (
                (SIDE_LEFT, "AA:BB:CC:DD:EE:01"), (SIDE_RIGHT, "AA:BB:CC:DD:EE:02"))],
    }, options={CONF_MOTOR_COUNT: 3})
    entry.add_to_hass(hass)
    right_before = effective_child_data(entry.data, SIDE_RIGHT, entry.options)
    async_refresh_furnimove_layout_issues(hass, entry)
    flow = FurniMoveLayoutRepairFlow(entry.entry_id, SIDE_LEFT)
    flow.hass = hass
    await flow.async_step_handset({CONF_FURNIMOVE_REMOTE: "00000"})
    assert effective_child_data(entry.data, SIDE_RIGHT, entry.options) == right_before
    left = effective_child_data(entry.data, SIDE_LEFT, entry.options)
    assert left[CONF_BED_TYPE] == BED_TYPE_FURNIMOVE and left[CONF_MOTOR_COUNT] == 2
    issues = ir.async_get(hass).issues
    assert (DOMAIN, f"furnimove_layout_{entry.entry_id}_left") not in issues
    assert (DOMAIN, f"furnimove_layout_{entry.entry_id}_right") in issues


async def test_removed_entry_or_side_cannot_be_recreated_by_a_stale_flow(hass):
    flow = FurniMoveLayoutRepairFlow("removed", SIDE_LEFT)
    flow.hass = hass
    result = await flow.async_step_handset({CONF_FURNIMOVE_REMOTE: "00000"})
    assert result == {"type": "abort", "flow_id": flow.flow_id, "handler": flow.handler,
                      "reason": "entry_missing", "description_placeholders": None}


async def test_one_motor_does_not_prove_that_a_legacy_entry_is_a_staircase(hass):
    entry = _legacy(hass)
    hass.config_entries.async_update_entry(entry, data={**entry.data, CONF_MOTOR_COUNT: 1})
    async_refresh_furnimove_layout_issues(hass, entry)
    assert ir.async_get(hass).async_get_issue(DOMAIN, f"furnimove_layout_{entry.entry_id}_standalone")


async def test_handset_repair_accepts_the_exact_furnimove_app_82417(hass):
    """Repair must offer the captured layout shown in the user's FurniMove app."""
    from custom_components.adjustable_bed.furnimove_profiles import FURNIMOVE_PROFILES
    entry = _legacy(hass)
    flow = FurniMoveLayoutRepairFlow(entry.entry_id, None)
    flow.hass = hass
    form = await flow.async_step_handset()
    offered = {
        option["value"]
        for option in form["data_schema"].schema[CONF_FURNIMOVE_REMOTE].config["options"]
    }
    assert offered == set(FURNIMOVE_PROFILES)
    saved = await flow.async_step_handset({CONF_FURNIMOVE_REMOTE: "82417"})
    assert saved["type"] == "create_entry"
    assert entry.data[CONF_BED_TYPE] == BED_TYPE_FURNIMOVE
    assert entry.data[CONF_FURNIMOVE_REMOTE] == "82417"


def _dot(hass, variant: str):
    entry = MockConfigEntry(domain=DOMAIN, title="DOT bed", unique_id="AA:BB:CC:DD:EE:10", version=4,
        data={CONF_ADDRESS: "AA:BB:CC:DD:EE:10", CONF_BED_TYPE: BED_TYPE_OKIN_DOT,
              CONF_PROTOCOL_VARIANT: variant, CONF_MOTOR_COUNT: 2})
    entry.add_to_hass(hass)
    return entry


async def test_dot_handset_in_furnimove_catalog_is_offered_the_furnimove_profile(hass):
    entry = _dot(hass, "93558")
    entry_id = entry.entry_id
    async_refresh_furnimove_layout_issues(hass, entry)
    issue_id = f"furnimove_layout_{entry_id}_standalone"
    issue = ir.async_get(hass).async_get_issue(DOMAIN, issue_id)
    assert issue is not None and issue.translation_key == "furnimove_handset_route"
    assert issue.translation_placeholders == {"name": "DOT bed", "handset": "93558"}
    flow = await async_create_fix_flow(hass, issue_id, issue.data)
    flow.hass = hass
    form = await flow.async_step_init({"issue_id": issue_id})
    config = form["data_schema"].schema["route"].config
    assert (config["options"], config["translation_key"]) == (
        ["furnimove", "keep"], "furnimove_handset_route",
    )
    result = await flow.async_step_init({"route": "furnimove"})
    assert result["type"] == "create_entry"
    assert entry.entry_id == entry_id
    assert entry.data[CONF_BED_TYPE] == BED_TYPE_FURNIMOVE
    assert entry.data[CONF_FURNIMOVE_REMOTE] == "93558"
    assert CONF_PROTOCOL_VARIANT not in entry.data
    assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id) is None


async def test_dot_entry_can_keep_its_working_configuration(hass):
    entry = _dot(hass, "90167")
    before = dict(entry.data)
    async_refresh_furnimove_layout_issues(hass, entry)
    flow = FurniMoveLayoutRepairFlow(entry.entry_id, None)
    flow.hass = hass
    await flow.async_step_init({"route": "keep"})
    assert dict(entry.data) == {**before, CONF_FURNIMOVE_ROUTE_KEPT: True}
    assert not ir.async_get(hass).issues


async def test_dot_handsets_outside_the_catalog_and_okin_uuid_entries_get_no_prompt(hass):
    """Okin UUID stays the route for its handsets: it adds the bond and FFE4 feedback."""
    dot = _dot(hass, "97450")
    async_refresh_furnimove_layout_issues(hass, dot)
    okin = MockConfigEntry(domain=DOMAIN, title="Okimat", unique_id="AA:BB:CC:DD:EE:11", version=4,
        data={CONF_ADDRESS: "AA:BB:CC:DD:EE:11", CONF_BED_TYPE: BED_TYPE_OKIN_UUID,
              CONF_PROTOCOL_VARIANT: "82417", CONF_MOTOR_COUNT: 2})
    okin.add_to_hass(hass)
    async_refresh_furnimove_layout_issues(hass, okin)
    assert not ir.async_get(hass).issues


def test_every_repair_choice_has_a_translated_label():
    import json
    from pathlib import Path

    strings = json.loads(Path("custom_components/adjustable_bed/strings.json").read_text())
    assert set(strings["selector"]["furnimove_layout"]["options"]) == {
        "furnimove", "staircase", "keep",
    }
    assert set(strings["selector"]["furnimove_handset_route"]["options"]) == {"furnimove", "keep"}
