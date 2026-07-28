"""Tests for the Adjustable Bed repair flows."""

from __future__ import annotations

import asyncio
import json
from dataclasses import replace
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest
from bleak.exc import BleakError
from homeassistant.components.repairs import repairs_flow_manager
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_ADDRESS, CONF_NAME, EVENT_HOMEASSISTANT_STARTED
from homeassistant.core import CoreState, HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.issue_registry import IssueSeverity
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed.bluetooth_bond import (
    BluezReadStatus,
    LocalBondInventory,
    LocalBondRecord,
)
from custom_components.adjustable_bed.bluetooth_transport import (
    ConnectionPath,
    TransportClass,
)
from custom_components.adjustable_bed.bond_verification import (
    CONF_BLE_BOND_CONTEXT,
    BondEvidence,
    BondOwner,
    BondVerificationStatus,
)
from custom_components.adjustable_bed.const import (
    BED_TYPE_LEGGETT_GEN2,
    BED_TYPE_OKIMAT,
    CONF_BED_TYPE,
    CONF_BLE_BOND_ESTABLISHED,
    CONF_BLE_BOND_MARKER_UNRELIABLE,
    CONF_PAIR_ID,
    CONF_PAIR_MEMBER_ADDRESSES,
    DOMAIN,
)
from custom_components.adjustable_bed.pairing_candidates import (
    CONF_PAIR_SELECTION,
    decode_pair_selection,
    encode_pair_selection,
)
from custom_components.adjustable_bed.repairs import (
    COMBINE_BEDS_ISSUE_ID,
    CombineBedsRepairFlow,
    PairingRequiredRepairFlow,
    async_create_fix_flow,
    async_refresh_combine_beds_issue,
    async_setup_combine_beds_issue,
    async_track_combine_beds_issue,
)
from custom_components.adjustable_bed.setup_operation import (
    OperationOutcome,
    OperationResult,
)

from .conftest import TEST_ADDRESS, TEST_NAME

BLEAK_DEVICE = "custom_components.adjustable_bed.repairs.bluetooth.async_ble_device_from_address"
ESTABLISH = "bleak_retry_connector.establish_connection"


def _bed_entry(
    hass: HomeAssistant,
    *,
    address: str,
    name: str,
    state: ConfigEntryState = ConfigEntryState.LOADED,
) -> MockConfigEntry:
    """Add a standalone bed entry in the requested lifecycle state."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=name,
        data={
            CONF_ADDRESS: address,
            CONF_NAME: name,
            CONF_BED_TYPE: "linak",
        },
        unique_id=address,
        version=4,
        state=state,
    )
    entry.add_to_hass(hass)
    return entry


async def test_combine_suggestion_tracks_active_standalone_entries(
    hass: HomeAssistant,
) -> None:
    """The warning appears at two loaded beds and clears when one unloads."""
    hass.set_state(CoreState.running)
    left = _bed_entry(
        hass,
        address="AA:BB:CC:DD:EE:01",
        name="Left",
        state=ConfigEntryState.NOT_LOADED,
    )
    right = _bed_entry(
        hass,
        address="AA:BB:CC:DD:EE:02",
        name="Right",
        state=ConfigEntryState.NOT_LOADED,
    )
    async_track_combine_beds_issue(hass, left)
    async_track_combine_beds_issue(hass, right)
    registry = ir.async_get(hass)

    left._async_set_state(hass, ConfigEntryState.LOADED, None)
    assert registry.async_get_issue(DOMAIN, COMBINE_BEDS_ISSUE_ID) is None

    right._async_set_state(hass, ConfigEntryState.LOADED, None)
    issue = registry.async_get_issue(DOMAIN, COMBINE_BEDS_ISSUE_ID)
    assert issue is not None
    assert issue.translation_key == "combine_two_beds"
    assert issue.severity is IssueSeverity.WARNING
    assert issue.is_fixable is True
    assert issue.data == {"entry_count": 2}

    right._async_set_state(hass, ConfigEntryState.UNLOAD_IN_PROGRESS, None)
    assert registry.async_get_issue(DOMAIN, COMBINE_BEDS_ISSUE_ID) is None


async def test_combine_suggestion_preserves_dismissal_during_startup(
    hass: HomeAssistant,
) -> None:
    """Transient startup states do not recreate a dismissed persistent issue."""
    left = _bed_entry(hass, address="AA:BB:CC:DD:EE:01", name="Left")
    right = _bed_entry(hass, address="AA:BB:CC:DD:EE:02", name="Right")
    async_refresh_combine_beds_issue(hass)
    registry = ir.async_get(hass)
    registry.async_ignore(DOMAIN, COMBINE_BEDS_ISSUE_ID, True)
    issue = registry.async_get_issue(DOMAIN, COMBINE_BEDS_ISSUE_ID)
    assert issue is not None
    dismissed_version = issue.dismissed_version

    hass.set_state(CoreState.starting)
    async_setup_combine_beds_issue(hass)
    async_track_combine_beds_issue(hass, left)
    async_track_combine_beds_issue(hass, right)
    right._async_set_state(hass, ConfigEntryState.NOT_LOADED, None)

    issue = registry.async_get_issue(DOMAIN, COMBINE_BEDS_ISSUE_ID)
    assert issue is not None
    assert issue.dismissed_version == dismissed_version

    right._async_set_state(hass, ConfigEntryState.LOADED, None)
    hass.set_state(CoreState.running)
    hass.bus.async_fire_internal(EVENT_HOMEASSISTANT_STARTED)
    issue = registry.async_get_issue(DOMAIN, COMBINE_BEDS_ISSUE_ID)
    assert issue is not None
    assert issue.dismissed_version == dismissed_version


async def test_combine_suggestion_excludes_entries_claimed_by_pair(
    hass: HomeAssistant,
) -> None:
    """Original singles are not suggested once a paired entry claims them."""
    addresses = ["AA:BB:CC:DD:EE:01", "AA:BB:CC:DD:EE:02"]
    for index, address in enumerate(addresses):
        _bed_entry(hass, address=address, name=f"Side {index}")
    MockConfigEntry(
        domain=DOMAIN,
        title="Combined",
        data={
            CONF_PAIR_ID: "pair_test",
            CONF_PAIR_MEMBER_ADDRESSES: addresses,
        },
        unique_id="pair_test",
        version=4,
    ).add_to_hass(hass)

    async_refresh_combine_beds_issue(hass)

    assert ir.async_get(hass).async_get_issue(DOMAIN, COMBINE_BEDS_ISSUE_ID) is None


async def test_combine_repair_flow_shows_active_bed_picker(
    hass: HomeAssistant,
) -> None:
    """Choosing to combine opens the Left/Right selector."""
    left = _bed_entry(hass, address="AA:BB:CC:DD:EE:01", name="Left")
    right = _bed_entry(hass, address="AA:BB:CC:DD:EE:02", name="Right")
    flow = CombineBedsRepairFlow()
    flow.hass = hass

    # RepairsFlowManager passes its internal issue payload to the init step.
    menu = await flow.async_step_init({"issue_id": COMBINE_BEDS_ISSUE_ID})
    assert menu["type"] is FlowResultType.MENU
    assert menu["menu_options"] == ["pair_beds", "separate_beds"]
    assert menu["description_placeholders"] == {
        "count": "2",
        "names": "Left, Right",
    }

    result = await flow.async_step_pair_beds()

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "pair_beds"
    assert result["description_placeholders"] == {
        "count": "2",
        "names": "Left, Right",
    }
    schema = result.get("data_schema")
    assert schema is not None
    defaults = schema({})
    assert isinstance(defaults, dict)
    assert decode_pair_selection(defaults[CONF_PAIR_SELECTION]) == (
        left.entry_id,
        right.entry_id,
    )


async def test_combine_repair_flow_aborts_when_issue_is_stale(
    hass: HomeAssistant,
) -> None:
    """A stale issue cannot offer choices for fewer than two active beds."""
    _bed_entry(hass, address="AA:BB:CC:DD:EE:01", name="Only bed")
    async_refresh_combine_beds_issue(hass)
    flow = CombineBedsRepairFlow()
    flow.hass = hass

    result = await flow.async_step_init({"issue_id": COMBINE_BEDS_ISSUE_ID})

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "not_enough_beds"
    assert ir.async_get(hass).async_get_issue(DOMAIN, COMBINE_BEDS_ISSUE_ID) is None


async def test_combine_repair_opens_through_repairs_manager(
    hass: HomeAssistant,
    enable_custom_integrations,
) -> None:
    """The Repairs manager's issue metadata is not treated as form input."""
    assert await async_setup_component(hass, "repairs", {})
    assert await async_setup_component(hass, DOMAIN, {})
    left = _bed_entry(hass, address="AA:BB:CC:DD:EE:01", name="Left")
    right = _bed_entry(hass, address="AA:BB:CC:DD:EE:02", name="Right")
    async_refresh_combine_beds_issue(hass)
    manager = repairs_flow_manager(hass)
    assert manager is not None

    menu = await manager.async_init(
        DOMAIN,
        data={"issue_id": COMBINE_BEDS_ISSUE_ID},
    )
    assert menu["type"] is FlowResultType.MENU

    result = await manager.async_configure(
        menu["flow_id"], {"next_step_id": "pair_beds"}
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "pair_beds"
    schema = result.get("data_schema")
    assert schema is not None
    defaults = schema({})
    assert isinstance(defaults, dict)
    assert decode_pair_selection(defaults[CONF_PAIR_SELECTION]) == (
        left.entry_id,
        right.entry_id,
    )


async def test_combine_repair_flow_delegates_creation_to_config_flow(
    hass: HomeAssistant,
) -> None:
    """Submitting Repairs uses the canonical pairing config-flow transaction."""
    left = _bed_entry(hass, address="AA:BB:CC:DD:EE:01", name="Left")
    right = _bed_entry(hass, address="AA:BB:CC:DD:EE:02", name="Right")
    flow = CombineBedsRepairFlow()
    flow.hass = hass
    config_form = {
        "type": FlowResultType.FORM,
        "flow_id": "config-flow-id",
        "handler": DOMAIN,
        "step_id": "pair_beds",
    }
    config_created = {
        "type": FlowResultType.CREATE_ENTRY,
        "flow_id": "config-flow-id",
        "handler": DOMAIN,
        "title": "Combined",
        "data": {},
    }

    with (
        patch.object(
            hass.config_entries.flow,
            "async_init",
            new=AsyncMock(return_value=config_form),
        ) as init,
        patch.object(
            hass.config_entries.flow,
            "async_configure",
            new=AsyncMock(return_value=config_created),
        ) as configure,
    ):
        pair_selection = encode_pair_selection(left.entry_id, right.entry_id)
        result = await flow.async_step_pair_beds(
            {
                CONF_PAIR_SELECTION: pair_selection,
                CONF_NAME: "Combined",
            }
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    init.assert_awaited_once_with(
        DOMAIN,
        context={"source": "user"},
        data={CONF_ADDRESS: "pair_beds"},
    )
    configure.assert_awaited_once_with(
        "config-flow-id",
        {
            CONF_PAIR_SELECTION: pair_selection,
            CONF_NAME: "Combined",
        },
    )


async def test_combine_repair_reuses_nested_flow_after_validation_error(
    hass: HomeAssistant,
) -> None:
    """A corrected submission continues the same delegated config flow."""
    left = _bed_entry(hass, address="AA:BB:CC:DD:EE:01", name="Left")
    right = _bed_entry(hass, address="AA:BB:CC:DD:EE:02", name="Right")
    flow = CombineBedsRepairFlow()
    flow.hass = hass
    config_form = {
        "type": FlowResultType.FORM,
        "flow_id": "config-flow-id",
        "handler": DOMAIN,
        "step_id": "pair_beds",
    }
    validation_error = {
        **config_form,
        "errors": {"base": "incompatible"},
    }
    config_created = {
        "type": FlowResultType.CREATE_ENTRY,
        "flow_id": "config-flow-id",
        "handler": DOMAIN,
        "title": "Combined",
        "data": {},
    }
    pair_selection = encode_pair_selection(left.entry_id, right.entry_id)
    invalid_input = {CONF_PAIR_SELECTION: pair_selection}
    corrected_input = {
        CONF_PAIR_SELECTION: pair_selection,
        CONF_NAME: "Combined",
    }

    with (
        patch.object(
            hass.config_entries.flow,
            "async_init",
            new=AsyncMock(return_value=config_form),
        ) as init,
        patch.object(
            hass.config_entries.flow,
            "async_configure",
            new=AsyncMock(side_effect=[validation_error, config_created]),
        ) as configure,
    ):
        first = await flow.async_step_pair_beds(invalid_input)
        second = await flow.async_step_pair_beds(corrected_input)

    assert first["type"] is FlowResultType.FORM
    assert first["errors"] == {"base": "incompatible"}
    assert second["type"] is FlowResultType.CREATE_ENTRY
    init.assert_awaited_once()
    assert configure.await_args_list == [
        call("config-flow-id", invalid_input),
        call("config-flow-id", corrected_input),
    ]
    assert flow._pairing_flow_id is None


async def test_async_create_fix_flow_builds_pairing_flow(hass: HomeAssistant) -> None:
    """The factory wires issue data into the pairing repair flow."""
    flow = await async_create_fix_flow(
        hass,
        f"pairing_required_{TEST_ADDRESS.replace(':', '_').lower()}",
        {
            "address": TEST_ADDRESS,
            "name": TEST_NAME,
            "entry_id": "abc123",
            "evidence_status": "auth_failed",
            "evidence_transport": "proxy",
            "evidence_source": "bedroom-proxy",
            "evidence_adapter": None,
            "evidence_observed_at": "2026-07-27T00:00:00+00:00",
        },
    )
    assert isinstance(flow, PairingRequiredRepairFlow)
    assert flow._address == TEST_ADDRESS
    assert flow._name == TEST_NAME
    assert flow._entry_id == "abc123"
    assert flow._evidence is not None
    assert flow._evidence.status is BondVerificationStatus.AUTH_FAILED
    assert flow._evidence.owner.transport is TransportClass.PROXY
    assert flow._evidence.owner.source == "bedroom-proxy"


async def test_async_create_fix_flow_routes_combine_suggestion(
    hass: HomeAssistant,
) -> None:
    """The stable suggestion issue id opens the Dual Bed repair flow."""
    flow = await async_create_fix_flow(
        hass,
        COMBINE_BEDS_ISSUE_ID,
        {"entry_count": 2},
    )

    assert isinstance(flow, CombineBedsRepairFlow)


async def test_confirm_step_shows_form_first(hass: HomeAssistant) -> None:
    """The first step presents the pairing instructions form."""
    flow = PairingRequiredRepairFlow(TEST_ADDRESS, TEST_NAME, None)
    flow.hass = hass

    result = await flow.async_step_init()

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "confirm"
    assert result["description_placeholders"]["address"] == TEST_ADDRESS


async def test_one_link_proxy_failure_keeps_the_guided_pairing_flow(
    hass: HomeAssistant,
) -> None:
    """A live coordinator can safely pair the one link already held via a proxy."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=TEST_NAME,
        data={
            CONF_ADDRESS: TEST_ADDRESS,
            CONF_NAME: TEST_NAME,
            CONF_BED_TYPE: BED_TYPE_LEGGETT_GEN2,
        },
        unique_id=TEST_ADDRESS,
        entry_id="repair_gen2_proxy_entry",
    )
    entry.add_to_hass(hass)
    flow = PairingRequiredRepairFlow(
        TEST_ADDRESS,
        TEST_NAME,
        entry.entry_id,
        issue_data={"evidence_transport": "proxy", "evidence_source": "proxy-source"},
    )
    flow.hass = hass

    result = await flow.async_step_init()

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "confirm"


async def test_confirm_step_resolves_on_successful_pair(hass: HomeAssistant) -> None:
    """Submitting the form resolves the issue when pairing succeeds."""
    flow = PairingRequiredRepairFlow(TEST_ADDRESS, TEST_NAME, None)
    flow.hass = hass

    with patch.object(flow, "_async_try_pair", new=AsyncMock(return_value=True)):
        result = await flow.async_step_confirm({})

    assert result["type"] == FlowResultType.CREATE_ENTRY


async def test_confirm_step_aborts_on_failed_pair(hass: HomeAssistant) -> None:
    """Submitting the form aborts (issue stays) when pairing fails."""
    flow = PairingRequiredRepairFlow(TEST_ADDRESS, TEST_NAME, None)
    flow.hass = hass

    with patch.object(flow, "_async_try_pair", new=AsyncMock(return_value=False)):
        result = await flow.async_step_confirm({})

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "pairing_failed"


async def test_stale_recovery_stops_when_the_issue_was_cleared(
    hass: HomeAssistant,
) -> None:
    """An open confirmation cannot act after its evidence-bearing issue is gone."""
    flow = PairingRequiredRepairFlow(TEST_ADDRESS, TEST_NAME, None)
    flow.hass = hass
    flow._offer = MagicMock()

    with patch(
        "custom_components.adjustable_bed.repairs.async_recover_local_bond"
    ) as recover:
        result = await flow._async_recovery_worker()

    assert result.outcome is OperationOutcome.UNPAIR_FAILED
    assert result.detail == "pairing_issue_no_longer_exists"
    recover.assert_not_called()


def _verified_local_bond() -> BondEvidence:
    return BondEvidence(
        status=BondVerificationStatus.VERIFIED,
        owner=BondOwner(
            transport=TransportClass.LOCAL,
            source="11:22:33:44:55:66",
            adapter="hci0",
        ),
        operation="stale_bond_recovery",
        observed_at="2026-07-27T00:00:00+00:00",
    )


async def test_recovery_persistence_relies_on_the_loaded_entry_listener(
    hass: HomeAssistant,
) -> None:
    """A loaded entry's update listener must be the only reload source."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=TEST_NAME,
        data={
            CONF_ADDRESS: TEST_ADDRESS,
            CONF_NAME: TEST_NAME,
            CONF_BED_TYPE: "okimat",
        },
        unique_id=TEST_ADDRESS,
        entry_id="loaded_recovery_entry",
    )
    entry.add_to_hass(hass)
    coordinator = MagicMock()
    coordinator.consume_internal_entry_update.return_value = False
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    async def reload_listener(
        _hass: HomeAssistant, updated_entry: MockConfigEntry
    ) -> None:
        await hass.config_entries.async_reload(updated_entry.entry_id)

    entry.add_update_listener(reload_listener)
    flow = PairingRequiredRepairFlow(TEST_ADDRESS, TEST_NAME, entry.entry_id)
    flow.hass = hass
    result = OperationResult(
        outcome=OperationOutcome.SUCCESS,
        payload=_verified_local_bond(),
    )

    with patch.object(
        hass.config_entries, "async_reload", new=AsyncMock()
    ) as mock_reload:
        await flow._async_persist_recovered_bond(result)
        await hass.async_block_till_done()

    mock_reload.assert_awaited_once_with(entry.entry_id)


async def test_recovery_persistence_reloads_an_unloaded_entry(
    hass: HomeAssistant,
) -> None:
    """A setup-retry entry has no update listener, so persistence reloads it."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=TEST_NAME,
        data={
            CONF_ADDRESS: TEST_ADDRESS,
            CONF_NAME: TEST_NAME,
            CONF_BED_TYPE: "okimat",
        },
        unique_id=TEST_ADDRESS,
        entry_id="unloaded_recovery_entry",
    )
    entry.add_to_hass(hass)
    flow = PairingRequiredRepairFlow(TEST_ADDRESS, TEST_NAME, entry.entry_id)
    flow.hass = hass
    result = OperationResult(
        outcome=OperationOutcome.SUCCESS,
        payload=_verified_local_bond(),
    )

    with patch.object(
        hass.config_entries, "async_reload", new=AsyncMock()
    ) as mock_reload:
        await flow._async_persist_recovered_bond(result)

    mock_reload.assert_awaited_once_with(entry.entry_id)


async def test_a_removed_bond_stops_being_recorded_even_when_recovery_fails(
    hass: HomeAssistant,
) -> None:
    """The marker for a bond that is provably gone must go with it.

    The repair stays open, and the entry would otherwise still claim a bond, so
    the next connection would skip pair=True on an unbonded device and repeat
    the authentication failure this repair was raised for.
    """
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=TEST_NAME,
        data={
            CONF_ADDRESS: TEST_ADDRESS,
            CONF_NAME: TEST_NAME,
            CONF_BED_TYPE: "okimat",
            CONF_BLE_BOND_ESTABLISHED: True,
            CONF_BLE_BOND_MARKER_UNRELIABLE: True,
            CONF_BLE_BOND_CONTEXT: {
                "version": 1,
                "transport": "local",
                "source": "11:22:33:44:55:66",
                "adapter": "hci0",
            },
        },
        unique_id=TEST_ADDRESS,
        entry_id="failed_recovery_entry",
    )
    entry.add_to_hass(hass)
    flow = PairingRequiredRepairFlow(TEST_ADDRESS, TEST_NAME, entry.entry_id)
    flow.hass = hass

    await flow._async_clear_removed_bond()

    assert CONF_BLE_BOND_ESTABLISHED not in entry.data
    assert CONF_BLE_BOND_CONTEXT not in entry.data
    assert CONF_BLE_BOND_MARKER_UNRELIABLE not in entry.data


def test_pairing_repair_translations_cover_every_progress_and_result() -> None:
    """The Repairs namespace must localize phases and terminal guidance."""
    root = Path(__file__).parents[1] / "custom_components/adjustable_bed"
    required_progress = {
        "locating",
        "connecting",
        "pairing",
        "verifying_bond",
        "disconnecting",
        "unpairing",
    }
    # Every step id this flow can render. A step with no strings shows the user
    # an untitled, undescribed dialog for the whole time it is on screen.
    required_steps = {
        "confirm",
        "proxy_bond",
        "stale_bond_confirm",
        "stale_bond_progress",
        "stale_bond_result",
    }
    required_results = {
        "recovery_success",
        "recovery_not_run",
        "recovery_not_advertising",
        "recovery_unpair_failed",
        "recovery_unpair_unconfirmed",
        "recovery_failed_unchanged",
        "recovery_partial",
    }
    for relative in ("strings.json", "translations/en.json", "translations/nb.json"):
        data = json.loads((root / relative).read_text())
        pairing = data["issues"]["pairing_required"]
        flow = pairing["fix_flow"]
        assert required_progress <= flow["progress"].keys()
        assert required_results <= flow["abort"].keys()
        assert "title" in pairing
        assert required_steps <= flow["step"].keys()
        assert "pairing_failed" in flow["abort"]
        for step in required_steps:
            assert flow["step"][step].keys() >= {"title", "description"}


async def test_try_pair_returns_false_when_device_not_in_range(hass: HomeAssistant) -> None:
    """No reachable device means pairing cannot proceed."""
    flow = PairingRequiredRepairFlow(TEST_ADDRESS, TEST_NAME, None)
    flow.hass = hass

    with patch(BLEAK_DEVICE, return_value=None):
        assert await flow._async_try_pair() is False


async def test_try_pair_succeeds_and_clears_marker(hass: HomeAssistant) -> None:
    """A successful pair + verified read persists the bond and reloads the entry."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=TEST_NAME,
        data={
            CONF_ADDRESS: TEST_ADDRESS,
            CONF_NAME: TEST_NAME,
            CONF_BED_TYPE: "okimat",
            CONF_BLE_BOND_ESTABLISHED: False,
        },
        unique_id=TEST_ADDRESS,
        entry_id="repair_ok_entry",
    )
    entry.add_to_hass(hass)

    flow = PairingRequiredRepairFlow(TEST_ADDRESS, TEST_NAME, entry.entry_id)
    flow.hass = hass

    client = MagicMock()
    client._connected_scanner = MagicMock(source="bedroom-proxy")
    client.pair = AsyncMock()
    client.read_gatt_char = AsyncMock(return_value=b"Model X")
    client.disconnect = AsyncMock()

    with (
        patch(BLEAK_DEVICE, return_value=MagicMock()),
        patch(ESTABLISH, new=AsyncMock(return_value=client)) as mock_establish,
        patch(
            "custom_components.adjustable_bed.repairs.async_path_for_source",
            return_value=ConnectionPath(
                source="bedroom-proxy", transport=TransportClass.PROXY
            ),
        ),
        patch.object(
            hass.config_entries, "async_reload", new=AsyncMock()
        ) as mock_reload,
    ):
        result = await flow._async_try_pair()

    assert result is True
    assert entry.data[CONF_BLE_BOND_ESTABLISHED] is True
    assert entry.data[CONF_BLE_BOND_CONTEXT]["transport"] == "proxy"
    assert entry.data[CONF_BLE_BOND_CONTEXT]["source"] == "bedroom-proxy"
    assert mock_establish.await_args.kwargs["pair"] is True
    client.pair.assert_not_awaited()
    mock_reload.assert_awaited_once_with(entry.entry_id)
    client.disconnect.assert_awaited_once()


@pytest.mark.parametrize("bonded", [True, False])
async def test_leggett_gen2_repair_pairs_through_the_coordinator(
    hass: HomeAssistant, bonded: bool
) -> None:
    """The repair must reuse the coordinator's connection, not spend a new one.

    LP Comfort Connect grants roughly one connection per pairing window (#385),
    so opening a second client here and closing it in ``finally`` would leave
    the reload with a box that refuses every reconnect.
    """
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=TEST_NAME,
        data={
            CONF_ADDRESS: TEST_ADDRESS,
            CONF_NAME: TEST_NAME,
            CONF_BED_TYPE: BED_TYPE_LEGGETT_GEN2,
            CONF_BLE_BOND_ESTABLISHED: True,
        },
        unique_id=TEST_ADDRESS,
        entry_id="repair_gen2_coordinator_entry",
    )
    entry.add_to_hass(hass)

    coordinator = MagicMock()
    # async_pair_now() reports whether the bond is confirmed, not merely whether
    # a connection exists: the connect path deliberately keeps unbonded links.
    coordinator.async_pair_now = AsyncMock(return_value=bonded)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    flow = PairingRequiredRepairFlow(TEST_ADDRESS, TEST_NAME, entry.entry_id)
    flow.hass = hass

    with (
        patch(BLEAK_DEVICE, return_value=MagicMock()),
        patch(ESTABLISH, new=AsyncMock()) as mock_establish,
    ):
        assert await flow._async_try_pair() is bonded

    coordinator.async_pair_now.assert_awaited_once_with()
    mock_establish.assert_not_awaited()


async def test_leggett_gen2_repair_with_no_coordinator_reloads_the_entry(
    hass: HomeAssistant,
) -> None:
    """With no loaded coordinator the repair must reload, not open a client.

    The pairing repair is raised from SETUP_RETRY, where setup has not stored a
    coordinator yet. A standalone client would pair and then disconnect in its
    finally block, and the reload could not obtain a second connection (#385).
    """
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=TEST_NAME,
        data={
            CONF_ADDRESS: TEST_ADDRESS,
            CONF_NAME: TEST_NAME,
            CONF_BED_TYPE: BED_TYPE_LEGGETT_GEN2,
            CONF_BLE_BOND_ESTABLISHED: True,
        },
        unique_id=TEST_ADDRESS,
        entry_id="repair_leggett_gen2_entry",
    )
    entry.add_to_hass(hass)

    flow = PairingRequiredRepairFlow(TEST_ADDRESS, TEST_NAME, entry.entry_id)
    flow.hass = hass

    async def reload(entry_id: str) -> None:
        # Setup owns the single connection; simulate it confirming the bond.
        target = hass.config_entries.async_get_entry(entry_id)
        hass.config_entries.async_update_entry(
            target, data={**target.data, CONF_BLE_BOND_ESTABLISHED: True}
        )

    with (
        patch(BLEAK_DEVICE, return_value=MagicMock()),
        patch(ESTABLISH, new=AsyncMock()) as mock_establish,
        patch.object(
            hass.config_entries, "async_reload", new=AsyncMock(side_effect=reload)
        ) as mock_reload,
    ):
        assert await flow._async_try_pair() is True

    mock_establish.assert_not_awaited()
    mock_reload.assert_awaited_once_with(entry.entry_id)
    # The stale marker is cleared first so setup actually requests the bond.
    assert flow._bonded_now() is True


async def test_leggett_gen2_repair_reload_that_stays_unbonded_fails(
    hass: HomeAssistant,
) -> None:
    """Connecting is not pairing: an unbonded reload must not resolve the issue."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=TEST_NAME,
        data={
            CONF_ADDRESS: TEST_ADDRESS,
            CONF_NAME: TEST_NAME,
            CONF_BED_TYPE: BED_TYPE_LEGGETT_GEN2,
            CONF_BLE_BOND_ESTABLISHED: False,
        },
        unique_id=TEST_ADDRESS,
        entry_id="repair_leggett_gen2_unbonded_entry",
    )
    entry.add_to_hass(hass)

    flow = PairingRequiredRepairFlow(TEST_ADDRESS, TEST_NAME, entry.entry_id)
    flow.hass = hass

    with (
        patch(BLEAK_DEVICE, return_value=MagicMock()),
        patch(ESTABLISH, new=AsyncMock()) as mock_establish,
        patch.object(hass.config_entries, "async_reload", new=AsyncMock()),
    ):
        # The advisory connect path keeps an unbonded link, so the entry can load
        # without a bond. That must still report the repair as unsuccessful.
        assert await flow._async_try_pair() is False

    mock_establish.assert_not_awaited()
    assert entry.data[CONF_BLE_BOND_ESTABLISHED] is False


async def test_repair_releases_its_client_when_verification_is_cancelled(
    hass: HomeAssistant,
) -> None:
    """Cancelling bond verification must still release the standalone client."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=TEST_NAME,
        data={
            CONF_ADDRESS: TEST_ADDRESS,
            CONF_NAME: TEST_NAME,
            CONF_BED_TYPE: "okimat",
            CONF_BLE_BOND_ESTABLISHED: False,
        },
        unique_id=TEST_ADDRESS,
        entry_id="repair_cancelled_entry",
    )
    entry.add_to_hass(hass)

    flow = PairingRequiredRepairFlow(TEST_ADDRESS, TEST_NAME, entry.entry_id)
    flow.hass = hass

    client = MagicMock()
    client.read_gatt_char = AsyncMock(side_effect=asyncio.CancelledError())
    client.disconnect = AsyncMock()

    with (
        patch(BLEAK_DEVICE, return_value=MagicMock()),
        patch(ESTABLISH, new=AsyncMock(return_value=client)),
        pytest.raises(asyncio.CancelledError),
    ):
        await flow._async_try_pair()

    client.disconnect.assert_awaited_once_with()
    assert entry.data[CONF_BLE_BOND_ESTABLISHED] is False


async def test_repair_releases_its_client_when_verification_is_unauthenticated(
    hass: HomeAssistant,
) -> None:
    """A still-unbonded link must fail the repair and release the client."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=TEST_NAME,
        data={
            CONF_ADDRESS: TEST_ADDRESS,
            CONF_NAME: TEST_NAME,
            CONF_BED_TYPE: "okimat",
            CONF_BLE_BOND_ESTABLISHED: False,
        },
        unique_id=TEST_ADDRESS,
        entry_id="repair_unauth_entry",
    )
    entry.add_to_hass(hass)

    flow = PairingRequiredRepairFlow(TEST_ADDRESS, TEST_NAME, entry.entry_id)
    flow.hass = hass

    client = MagicMock()
    client.read_gatt_char = AsyncMock(
        side_effect=BleakError("Insufficient authentication")
    )
    client.disconnect = AsyncMock()

    with (
        patch(BLEAK_DEVICE, return_value=MagicMock()),
        patch(ESTABLISH, new=AsyncMock(return_value=client)),
    ):
        assert await flow._async_try_pair() is False

    client.disconnect.assert_awaited_once_with()
    assert entry.data[CONF_BLE_BOND_ESTABLISHED] is False



async def test_try_pair_treats_non_auth_read_error_as_success(hass: HomeAssistant) -> None:
    """A non-auth read failure (e.g. char absent) is inconclusive, not a failure.

    It must still persist the bond marker and reload the entry so the repair
    closes for good rather than re-triggering on the next connection.
    """
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=TEST_NAME,
        data={
            CONF_ADDRESS: TEST_ADDRESS,
            CONF_NAME: TEST_NAME,
            CONF_BED_TYPE: "okimat",
            CONF_BLE_BOND_ESTABLISHED: False,
            CONF_BLE_BOND_CONTEXT: {
                "version": 1,
                "transport": "local",
                "source": "11:22:33:44:55:66",
                "adapter": "hci0",
            },
        },
        unique_id=TEST_ADDRESS,
        entry_id="repair_inconclusive_entry",
    )
    entry.add_to_hass(hass)

    flow = PairingRequiredRepairFlow(TEST_ADDRESS, TEST_NAME, entry.entry_id)
    flow.hass = hass

    client = MagicMock()
    client.read_gatt_char = AsyncMock(side_effect=BleakError("Characteristic not found"))
    client.disconnect = AsyncMock()

    with (
        patch(BLEAK_DEVICE, return_value=MagicMock()),
        patch(ESTABLISH, new=AsyncMock(return_value=client)),
        patch.object(hass.config_entries, "async_reload", new=AsyncMock()) as mock_reload,
    ):
        assert await flow._async_try_pair() is True

    assert entry.data[CONF_BLE_BOND_ESTABLISHED] is True
    assert CONF_BLE_BOND_CONTEXT not in entry.data
    mock_reload.assert_awaited_once_with(entry.entry_id)
    client.disconnect.assert_awaited_once()


async def test_try_pair_returns_false_on_auth_error(hass: HomeAssistant) -> None:
    """Pairing that connects but fails the encrypted read is treated as not paired."""
    flow = PairingRequiredRepairFlow(TEST_ADDRESS, TEST_NAME, None)
    flow.hass = hass

    client = MagicMock()
    client.read_gatt_char = AsyncMock(
        side_effect=BleakError("handle=24 error=5 description=Insufficient authentication")
    )
    client.disconnect = AsyncMock()

    with (
        patch(BLEAK_DEVICE, return_value=MagicMock()),
        patch(ESTABLISH, new=AsyncMock(return_value=client)),
    ):
        assert await flow._async_try_pair() is False

    client.disconnect.assert_awaited_once()


async def test_a_reconnect_between_confirm_and_removal_does_not_block_recovery(
    hass: HomeAssistant,
) -> None:
    """Volatile fields change while the dialog is open; identity does not.

    Comparing whole records made a bed that merely connected look like a
    different bond, and refused a removal the user had already approved for
    exactly this one.
    """
    pinned = LocalBondRecord(
        address=TEST_ADDRESS,
        device_path="/org/bluez/hci0/dev_AA_BB_CC_DD_EE_FF",
        adapter_path="/org/bluez/hci0",
        adapter_address="11:22:33:44:55:66",
        paired=True,
        bonded=True,
        connected=False,
        trusted=False,
    )
    reconnected = replace(pinned, connected=True, trusted=True)

    assert pinned.is_same_bond_as(reconnected)
    # A bond that is actually gone is still a different answer.
    assert not pinned.is_same_bond_as(replace(pinned, paired=False, bonded=False))
    # So is one on another adapter.
    assert not pinned.is_same_bond_as(
        replace(
            pinned,
            adapter_path="/org/bluez/hci1",
            device_path="/org/bluez/hci1/dev_AA_BB_CC_DD_EE_FF",
        )
    )
    # Replacing the dongle reuses hci0, and with it every path in this record.
    # The bond the user approved was the one on the adapter that is now gone.
    assert not pinned.is_same_bond_as(replace(pinned, adapter_address="AA:00:00:00:00:01"))


async def test_an_unidentified_adapter_never_authorizes_a_removal() -> None:
    """Without both adapter MACs, only reusable identifiers are left.

    ``hciN`` and the deterministic device path are inherited by whatever dongle
    occupies the slot next, so a snapshot BlueZ took without an adapter address
    cannot show that the bond still on that path is the one the user approved.
    This method authorizes destroying a bond, so it fails closed.
    """
    identified = LocalBondRecord(
        address=TEST_ADDRESS,
        device_path="/org/bluez/hci0/dev_AA_BB_CC_DD_EE_FF",
        adapter_path="/org/bluez/hci0",
        adapter_address="11:22:33:44:55:66",
        paired=True,
        bonded=True,
    )
    anonymous = replace(identified, adapter_address=None)

    # Identical in every field BlueZ did publish, and still not a basis to act.
    assert not identified.is_same_bond_as(anonymous)
    assert not anonymous.is_same_bond_as(identified)
    assert not anonymous.is_same_bond_as(replace(anonymous))
    # The fully identified pair is unaffected.
    assert identified.is_same_bond_as(replace(identified, connected=True))


async def test_a_reverified_same_adapter_bond_keeps_its_provenance(
    hass: HomeAssistant,
) -> None:
    """An unchanged context means "same owner, re-proven", not "nothing proven".

    The coordinator deliberately skips rewriting provenance when the owner is
    identical, so treating "unchanged" as "unproven" deleted a perfectly valid
    record and left later unpairs guessing.
    """
    context = {
        "version": 1,
        "transport": "local",
        "source": "11:22:33:44:55:66",
        "adapter": "hci0",
    }
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_ADDRESS: TEST_ADDRESS,
            CONF_NAME: TEST_NAME,
            CONF_BED_TYPE: BED_TYPE_LEGGETT_GEN2,
            CONF_BLE_BOND_ESTABLISHED: True,
            CONF_BLE_BOND_CONTEXT: context,
        },
        unique_id=TEST_ADDRESS,
        entry_id="repair_same_owner_entry",
    )
    entry.add_to_hass(hass)

    coordinator = MagicMock()
    coordinator.async_pair_now = AsyncMock(return_value=True)
    coordinator.last_bond_evidence = BondEvidence(
        status=BondVerificationStatus.VERIFIED,
        owner=BondOwner(
            transport=TransportClass.LOCAL, source="11:22:33:44:55:66", adapter="hci0"
        ),
        operation="runtime_authenticated_read",
        observed_at="2026-07-27T00:00:00+00:00",
    )
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    flow = PairingRequiredRepairFlow(TEST_ADDRESS, TEST_NAME, entry.entry_id)
    flow.hass = hass
    try:
        assert await flow._async_pair_via_coordinator() is True
    finally:
        hass.data[DOMAIN].pop(entry.entry_id, None)

    stored = entry.data[CONF_BLE_BOND_CONTEXT]
    assert stored["transport"] == "local"
    assert stored["source"] == "11:22:33:44:55:66"
    assert stored["adapter"] == "hci0"


async def test_a_reverified_same_adapter_bond_is_not_rewritten(
    hass: HomeAssistant,
) -> None:
    """Restating a bond's owner is still a change to the entry.

    This path only runs for beds that grant one connection per pairing window,
    and the coordinator has already recorded the same owner through an internal
    write. An untagged rewrite here reads as an options change, and the reload
    it triggers takes away the link the bed will not grant again.
    """
    context = {
        "version": 1,
        "transport": "local",
        "source": "11:22:33:44:55:66",
        "adapter": "hci0",
        "operation": "runtime_authenticated_read",
        "verified_at": "2026-07-27T00:00:00+00:00",
    }
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_ADDRESS: TEST_ADDRESS,
            CONF_NAME: TEST_NAME,
            CONF_BED_TYPE: BED_TYPE_LEGGETT_GEN2,
            CONF_BLE_BOND_ESTABLISHED: True,
            CONF_BLE_BOND_CONTEXT: context,
        },
        unique_id=TEST_ADDRESS,
        entry_id="repair_no_rewrite_entry",
    )
    entry.add_to_hass(hass)

    coordinator = MagicMock()
    coordinator.async_pair_now = AsyncMock(return_value=True)
    coordinator.last_bond_evidence = BondEvidence(
        status=BondVerificationStatus.VERIFIED,
        owner=BondOwner(
            transport=TransportClass.LOCAL, source="11:22:33:44:55:66", adapter="hci0"
        ),
        operation="runtime_authenticated_read",
        observed_at="2026-07-27T12:00:00+00:00",
    )
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    flow = PairingRequiredRepairFlow(TEST_ADDRESS, TEST_NAME, entry.entry_id)
    flow.hass = hass
    with patch.object(
        hass.config_entries, "async_update_entry", wraps=hass.config_entries.async_update_entry
    ) as update:
        try:
            assert await flow._async_pair_via_coordinator() is True
        finally:
            hass.data[DOMAIN].pop(entry.entry_id, None)

    update.assert_not_called()
    assert entry.data[CONF_BLE_BOND_CONTEXT] == context


async def test_a_successful_repair_does_not_reload_a_one_connection_bed(
    hass: HomeAssistant,
) -> None:
    """The reload would take away the link the repair just paired on.

    Pairing a live link reports success without a new authenticated read, so the
    repair drops the old provenance, and an untagged entry write reads as an
    options change. On a bed that grants one connection per pairing window the
    resulting reload strands it until it is power-cycled.
    """
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_ADDRESS: TEST_ADDRESS,
            CONF_NAME: TEST_NAME,
            CONF_BED_TYPE: BED_TYPE_LEGGETT_GEN2,
            CONF_BLE_BOND_CONTEXT: {
                "version": 1,
                "transport": "local",
                "source": "11:22:33:44:55:66",
                "adapter": "hci0",
            },
        },
        unique_id=TEST_ADDRESS,
        entry_id="repair_no_reload_entry",
    )
    entry.add_to_hass(hass)

    claimed: list[bool] = []
    coordinator = MagicMock()
    coordinator.async_pair_now = AsyncMock(return_value=True)
    coordinator.last_bond_evidence = None
    coordinator.begin_internal_bond_update = claimed.append
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    flow = PairingRequiredRepairFlow(TEST_ADDRESS, TEST_NAME, entry.entry_id)
    flow.hass = hass
    try:
        assert await flow._async_pair_via_coordinator() is True
    finally:
        hass.data[DOMAIN].pop(entry.entry_id, None)

    # The cleanup still happened, and the coordinator was given the chance to
    # claim it so the update listener leaves the entry loaded.
    assert CONF_BLE_BOND_CONTEXT not in entry.data
    assert entry.data[CONF_BLE_BOND_ESTABLISHED] is True
    assert claimed == [True]


async def test_an_unproven_coordinator_repair_drops_the_old_provenance(
    hass: HomeAssistant,
) -> None:
    """Nothing established an owner, so the pre-repair record cannot stand."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_ADDRESS: TEST_ADDRESS,
            CONF_NAME: TEST_NAME,
            CONF_BED_TYPE: BED_TYPE_LEGGETT_GEN2,
            CONF_BLE_BOND_ESTABLISHED: True,
            CONF_BLE_BOND_CONTEXT: {
                "version": 1,
                "transport": "local",
                "source": "11:22:33:44:55:66",
                "adapter": "hci0",
            },
        },
        unique_id=TEST_ADDRESS,
        entry_id="repair_unproven_owner_entry",
    )
    entry.add_to_hass(hass)

    coordinator = MagicMock()
    coordinator.async_pair_now = AsyncMock(return_value=True)
    coordinator.last_bond_evidence = BondEvidence(
        status=BondVerificationStatus.INCONCLUSIVE,
        owner=BondOwner(),
        operation="runtime_authenticated_read",
        observed_at="2026-07-27T00:00:00+00:00",
    )
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    flow = PairingRequiredRepairFlow(TEST_ADDRESS, TEST_NAME, entry.entry_id)
    flow.hass = hass
    try:
        assert await flow._async_pair_via_coordinator() is True
    finally:
        hass.data[DOMAIN].pop(entry.entry_id, None)

    assert CONF_BLE_BOND_CONTEXT not in entry.data


def _stale_bond_issue_data() -> dict[str, str]:
    """Issue data whose evidence points squarely at this host's BlueZ."""
    return {
        "address": TEST_ADDRESS,
        "name": TEST_NAME,
        "evidence_status": BondVerificationStatus.AUTH_FAILED.value,
        "evidence_transport": TransportClass.LOCAL.value,
        "evidence_source": "11:22:33:44:55:66",
        "evidence_adapter": "hci0",
    }


def _host_bond_inventory() -> LocalBondInventory:
    """One unambiguous host bond for the bed under test."""
    return LocalBondInventory(
        status=BluezReadStatus.OK,
        records=(
            LocalBondRecord(
                address=TEST_ADDRESS,
                device_path="/org/bluez/hci0/dev_AA_BB_CC_DD_EE_FF",
                adapter_path="/org/bluez/hci0",
                adapter_address="11:22:33:44:55:66",
                paired=True,
                bonded=True,
            ),
        ),
    )


async def test_a_standalone_bed_with_host_evidence_is_offered_recovery(
    hass: HomeAssistant,
) -> None:
    """The control case for the combined-pair refusal below."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=TEST_NAME,
        data={
            CONF_ADDRESS: TEST_ADDRESS,
            CONF_NAME: TEST_NAME,
            CONF_BED_TYPE: BED_TYPE_OKIMAT,
        },
        unique_id=TEST_ADDRESS,
        entry_id="repair_single_stale_bond_entry",
    )
    entry.add_to_hass(hass)
    flow = PairingRequiredRepairFlow(
        TEST_ADDRESS, TEST_NAME, entry.entry_id, issue_data=_stale_bond_issue_data()
    )
    flow.hass = hass

    with patch(
        "custom_components.adjustable_bed.bond_recovery.async_read_local_bonds",
        AsyncMock(return_value=_host_bond_inventory()),
    ):
        result = await flow.async_step_init()

    assert result["step_id"] == "stale_bond_confirm"


async def test_a_combined_pair_is_never_offered_stale_bond_recovery(
    hass: HomeAssistant,
) -> None:
    """A pair keeps each side's address and bond state on a child descriptor.

    Recovery writes its markers at entry level and drives the sequence through
    the entry's coordinator, and a combined pair has neither: the parent
    coordinator exposes no per-side transport, and no child ever reads a
    top-level bond marker. Offering the destructive branch here would remove a
    real host bond and then report success for state nothing consumes, so the
    guided pairing branch is used instead.
    """
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=TEST_NAME,
        data={
            CONF_NAME: TEST_NAME,
            CONF_BED_TYPE: BED_TYPE_OKIMAT,
            CONF_PAIR_ID: "pair_abc123",
            CONF_PAIR_MEMBER_ADDRESSES: [TEST_ADDRESS, "AA:BB:CC:DD:EE:01"],
        },
        unique_id="pair_abc123",
        entry_id="repair_combined_pair_entry",
    )
    entry.add_to_hass(hass)
    flow = PairingRequiredRepairFlow(
        TEST_ADDRESS, TEST_NAME, entry.entry_id, issue_data=_stale_bond_issue_data()
    )
    flow.hass = hass

    read_bonds = AsyncMock(return_value=_host_bond_inventory())
    with patch(
        "custom_components.adjustable_bed.bond_recovery.async_read_local_bonds",
        read_bonds,
    ):
        result = await flow.async_step_init()

    assert result["step_id"] == "confirm"
    # The host's bond store is never even consulted for a pair.
    read_bonds.assert_not_awaited()


async def test_a_proxy_pairing_failure_keeps_the_guided_pairing_retry(
    hass: HomeAssistant,
) -> None:
    """Naming the route is not evidence that the route holds a stale bond.

    An ordinary pairing failure over a proxy records the proxy as the transport
    too. Routing every one of those to the read-only proxy guidance left users
    whose bed simply failed to pair with an abort and no way to try again.
    """
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=TEST_NAME,
        data={
            CONF_ADDRESS: TEST_ADDRESS,
            CONF_NAME: TEST_NAME,
            CONF_BED_TYPE: BED_TYPE_OKIMAT,
        },
        unique_id=TEST_ADDRESS,
        entry_id="repair_proxy_pairing_failure_entry",
    )
    entry.add_to_hass(hass)
    flow = PairingRequiredRepairFlow(
        TEST_ADDRESS,
        TEST_NAME,
        entry.entry_id,
        issue_data={
            "evidence_status": BondVerificationStatus.INCONCLUSIVE.value,
            "evidence_transport": TransportClass.PROXY.value,
            "evidence_source": "proxy-source",
        },
    )
    flow.hass = hass

    with patch(
        "custom_components.adjustable_bed.bond_recovery.async_read_local_bonds",
        AsyncMock(return_value=_host_bond_inventory()),
    ):
        result = await flow.async_step_init()

    assert result["step_id"] == "confirm"


async def test_an_unbonded_proxy_link_keeps_the_guided_pairing_retry(
    hass: HomeAssistant,
) -> None:
    """An auth failure over a proxy is what an unbonded bed looks like.

    ``pair=True`` fails, the fallback connects without pairing, and the
    auth-gated read then reports insufficient authentication. Nothing there says
    a proxy bond exists, and the guidance would tell the user to reflash the
    proxy: that erases every unrelated bond on it and still leaves this bed
    unpaired.
    """
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=TEST_NAME,
        data={
            CONF_ADDRESS: TEST_ADDRESS,
            CONF_NAME: TEST_NAME,
            CONF_BED_TYPE: BED_TYPE_OKIMAT,
        },
        unique_id=TEST_ADDRESS,
        entry_id="repair_unbonded_proxy_entry",
    )
    entry.add_to_hass(hass)
    flow = PairingRequiredRepairFlow(
        TEST_ADDRESS,
        TEST_NAME,
        entry.entry_id,
        issue_data={
            "evidence_status": BondVerificationStatus.AUTH_FAILED.value,
            "evidence_transport": TransportClass.PROXY.value,
            "evidence_source": "proxy-source",
        },
    )
    flow.hass = hass

    with patch(
        "custom_components.adjustable_bed.bond_recovery.async_read_local_bonds",
        AsyncMock(return_value=_host_bond_inventory()),
    ):
        result = await flow.async_step_init()

    assert result["step_id"] == "confirm"


async def test_a_proxy_authentication_failure_still_gets_proxy_guidance(
    hass: HomeAssistant,
) -> None:
    """A refused bond plus provenance proving a proxy made one is the suspect."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=TEST_NAME,
        data={
            CONF_ADDRESS: TEST_ADDRESS,
            CONF_NAME: TEST_NAME,
            CONF_BED_TYPE: BED_TYPE_OKIMAT,
            CONF_BLE_BOND_ESTABLISHED: True,
            # Only ever written from a verification that positively proved a
            # bond, which is what makes this independent of the failure above.
            CONF_BLE_BOND_CONTEXT: {
                "version": 1,
                "transport": TransportClass.PROXY.value,
                "source": "proxy-source",
                "adapter": None,
                "verification": "runtime_authenticated_read",
                "verified_at": "2026-07-27T00:00:00+00:00",
            },
        },
        unique_id=TEST_ADDRESS,
        entry_id="repair_proxy_auth_failure_entry",
    )
    entry.add_to_hass(hass)
    flow = PairingRequiredRepairFlow(
        TEST_ADDRESS,
        TEST_NAME,
        entry.entry_id,
        issue_data={
            "evidence_status": BondVerificationStatus.AUTH_FAILED.value,
            "evidence_transport": TransportClass.PROXY.value,
            "evidence_source": "proxy-source",
        },
    )
    flow.hass = hass

    with patch(
        "custom_components.adjustable_bed.bond_recovery.async_read_local_bonds",
        AsyncMock(return_value=_host_bond_inventory()),
    ):
        result = await flow.async_step_init()

    assert result["step_id"] == "proxy_bond"


async def test_a_one_connection_bed_with_a_proxy_bond_still_gets_proxy_guidance(
    hass: HomeAssistant,
) -> None:
    """Recovery eligibility answers KEEPS_FIRST_LINK before it looks at transport.

    A Gen2 bed whose stale bond lives on a proxy would otherwise be sent to the
    pairing form, which cannot reach the proxy's bond store and hits the same
    authentication failure again.
    """
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_ADDRESS: TEST_ADDRESS,
            CONF_NAME: TEST_NAME,
            CONF_BED_TYPE: BED_TYPE_LEGGETT_GEN2,
            CONF_BLE_BOND_ESTABLISHED: True,
            CONF_BLE_BOND_CONTEXT: {
                "version": 1,
                "transport": "proxy",
                "source": "bedroom-proxy",
                "adapter": None,
            },
        },
        unique_id=TEST_ADDRESS,
        entry_id="repair_gen2_proxy_entry",
    )
    entry.add_to_hass(hass)

    flow = PairingRequiredRepairFlow(
        TEST_ADDRESS,
        TEST_NAME,
        entry.entry_id,
        issue_data={
            "evidence_status": "auth_failed",
            "evidence_transport": "proxy",
            "evidence_source": "bedroom-proxy",
        },
    )
    flow.hass = hass

    result = await flow.async_step_init()

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "proxy_bond"


async def test_the_combine_suggestion_can_be_answered_with_separate_beds(
    hass: HomeAssistant,
) -> None:
    """A fixable Repairs issue gets no Ignore action from Home Assistant.

    Without an answer inside the flow, someone who owns two genuinely separate
    beds can only close the dialog, which leaves the suggestion in Repairs for
    good.
    """
    from homeassistant.helpers.issue_registry import async_get as async_get_issue_registry

    from custom_components.adjustable_bed.combine_suggestion import async_load_dismissal
    from custom_components.adjustable_bed.repairs import (
        CombineBedsRepairFlow,
        async_refresh_combine_beds_issue,
    )

    for idx, address in enumerate(("AA:AA:AA:AA:AA:01", "AA:AA:AA:AA:AA:02")):
        entry = MockConfigEntry(
            domain=DOMAIN,
            data={CONF_ADDRESS: address, CONF_NAME: f"Bed {idx}", CONF_BED_TYPE: "linak"},
            unique_id=address,
            entry_id=f"separate_beds_{idx}",
        )
        entry.add_to_hass(hass)
        entry.mock_state(hass, ConfigEntryState.LOADED)

    await async_load_dismissal(hass)
    async_refresh_combine_beds_issue(hass)
    registry = async_get_issue_registry(hass)
    assert registry.async_get_issue(DOMAIN, "combine_two_beds") is not None

    flow = CombineBedsRepairFlow()
    flow.hass = hass

    menu = await flow.async_step_init()
    assert menu["type"] == FlowResultType.MENU
    assert "separate_beds" in menu["menu_options"]

    done = await flow.async_step_separate_beds()
    assert done["type"] == FlowResultType.ABORT
    assert done["reason"] == "beds_are_separate"

    # Gone, and it stays gone when the state is reconciled again.
    assert registry.async_get_issue(DOMAIN, "combine_two_beds") is None
    async_refresh_combine_beds_issue(hass)
    assert registry.async_get_issue(DOMAIN, "combine_two_beds") is None


async def test_combine_repair_does_not_dismiss_candidates_that_changed(
    hass: HomeAssistant,
) -> None:
    """The separate-beds answer applies only to the set shown in the menu."""
    _bed_entry(hass, address="AA:AA:AA:AA:AA:01", name="Bed 1")
    _bed_entry(hass, address="AA:AA:AA:AA:AA:02", name="Bed 2")
    flow = CombineBedsRepairFlow()
    flow.hass = hass
    await flow.async_step_init()

    _bed_entry(hass, address="AA:AA:AA:AA:AA:03", name="Bed 3")

    done = await flow.async_step_separate_beds()

    assert done["type"] is FlowResultType.ABORT
    assert done["reason"] == "beds_changed"
    assert ir.async_get(hass).async_get_issue(DOMAIN, COMBINE_BEDS_ISSUE_ID) is not None


async def test_a_new_bed_makes_the_combine_question_worth_asking_again(
    hass: HomeAssistant,
) -> None:
    """Dismissal covers subsets, while a genuinely new bed asks again."""
    from homeassistant.helpers.issue_registry import async_get as async_get_issue_registry

    from custom_components.adjustable_bed.combine_suggestion import (
        async_dismiss,
        async_load_dismissal,
    )
    from custom_components.adjustable_bed.repairs import async_refresh_combine_beds_issue

    addresses = ("BB:BB:BB:BB:BB:01", "BB:BB:BB:BB:BB:02")
    for idx, address in enumerate(addresses):
        entry = MockConfigEntry(
            domain=DOMAIN,
            data={CONF_ADDRESS: address, CONF_NAME: f"Bed {idx}", CONF_BED_TYPE: "linak"},
            unique_id=address,
            entry_id=f"regrouped_{idx}",
        )
        entry.add_to_hass(hass)
        entry.mock_state(hass, ConfigEntryState.LOADED)

    await async_load_dismissal(hass)
    # Lower case on purpose: the comparison must not depend on formatting.
    await async_dismiss(hass, [a.lower() for a in addresses])
    async_refresh_combine_beds_issue(hass)
    registry = async_get_issue_registry(hass)
    assert registry.async_get_issue(DOMAIN, "combine_two_beds") is None

    third = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_ADDRESS: "BB:BB:BB:BB:BB:03", CONF_NAME: "Bed 3", CONF_BED_TYPE: "linak"},
        unique_id="BB:BB:BB:BB:BB:03",
        entry_id="regrouped_3",
    )
    third.add_to_hass(hass)
    third.mock_state(hass, ConfigEntryState.LOADED)

    async_refresh_combine_beds_issue(hass)
    assert registry.async_get_issue(DOMAIN, "combine_two_beds") is not None

    await async_dismiss(hass, [*addresses, third.data[CONF_ADDRESS]])
    async_refresh_combine_beds_issue(hass)
    assert registry.async_get_issue(DOMAIN, "combine_two_beds") is None

    third.mock_state(hass, ConfigEntryState.NOT_LOADED)
    async_refresh_combine_beds_issue(hass)
    assert registry.async_get_issue(DOMAIN, "combine_two_beds") is None


async def test_dismissed_group_covers_a_remaining_subset(
    hass: HomeAssistant,
) -> None:
    """Removing one dismissed separate bed does not recreate the suggestion."""
    from custom_components.adjustable_bed.combine_suggestion import (
        async_dismiss,
        async_load_dismissal,
    )
    from custom_components.adjustable_bed.repairs import async_refresh_combine_beds_issue

    entries = [
        _bed_entry(hass, address=f"BB:BB:BB:BB:BB:0{idx}", name=f"Bed {idx}")
        for idx in range(1, 4)
    ]
    await async_load_dismissal(hass)
    await async_dismiss(hass, [entry.data[CONF_ADDRESS] for entry in entries])

    entries[-1].mock_state(hass, ConfigEntryState.NOT_LOADED)
    async_refresh_combine_beds_issue(hass)

    assert (
        ir.async_get(hass).async_get_issue(DOMAIN, COMBINE_BEDS_ISSUE_ID) is None
    )


async def test_combine_dismissal_storage_migrates_single_address_set(
    hass: HomeAssistant,
    hass_storage: dict[str, Any],
) -> None:
    """The v1 dismissal remains effective after migrating to history storage."""
    from custom_components.adjustable_bed.combine_suggestion import (
        KEY_DISMISSED,
        LEGACY_KEY_DISMISSED,
        STORAGE_KEY,
        async_is_dismissed,
        async_load_dismissal,
    )

    addresses = ["CC:CC:CC:CC:CC:01", "CC:CC:CC:CC:CC:02"]
    hass_storage[STORAGE_KEY] = {
        "version": 1,
        "minor_version": 1,
        "data": {LEGACY_KEY_DISMISSED: addresses},
    }

    await async_load_dismissal(hass)

    assert async_is_dismissed(hass, addresses)
    assert hass_storage[STORAGE_KEY] == {
        "version": 2,
        "minor_version": 1,
        "key": STORAGE_KEY,
        "data": {KEY_DISMISSED: [addresses]},
    }
