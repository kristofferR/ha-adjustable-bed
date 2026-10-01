"""Legacy RF receivers get an offline, identity-preserving layout repair."""

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.const import CONF_ADDRESS
from homeassistant.helpers import issue_registry as ir
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed.const import (
    BED_TYPE_FURNIMOVE,
    BED_TYPE_OKIN_RF_ECO_BT,
    CONF_BED_TYPE,
    CONF_BLE_BOND_ESTABLISHED,
    CONF_FURNIMOVE_REMOTE,
    CONF_MOTOR_COUNT,
    CONF_PAIR_CHILDREN,
    CONF_PAIR_ID,
    CONF_PAIR_MODE,
    CONF_SIDE,
    DOMAIN,
    PAIR_MODE_SEPARATE_ADDRESS,
    SIDE_LEFT,
    SIDE_RIGHT,
)
from custom_components.adjustable_bed.furnimove_repair import (
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
