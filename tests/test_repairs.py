"""Tests for the Adjustable Bed repair flows."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, call, patch

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

from custom_components.adjustable_bed.const import (
    CONF_BED_TYPE,
    CONF_BLE_BOND_ESTABLISHED,
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
    """The suggestion opens directly on the Left/Right selector."""
    left = _bed_entry(hass, address="AA:BB:CC:DD:EE:01", name="Left")
    right = _bed_entry(hass, address="AA:BB:CC:DD:EE:02", name="Right")
    flow = CombineBedsRepairFlow()
    flow.hass = hass

    # RepairsFlowManager passes its internal issue payload to the init step.
    result = await flow.async_step_init({"issue_id": COMBINE_BEDS_ISSUE_ID})

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

    result = await manager.async_init(
        DOMAIN,
        data={"issue_id": COMBINE_BEDS_ISSUE_ID},
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
        {"address": TEST_ADDRESS, "name": TEST_NAME, "entry_id": "abc123"},
    )
    assert isinstance(flow, PairingRequiredRepairFlow)
    assert flow._address == TEST_ADDRESS
    assert flow._name == TEST_NAME
    assert flow._entry_id == "abc123"


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
    client.read_gatt_char = AsyncMock(return_value=b"Model X")
    client.disconnect = AsyncMock()

    with (
        patch(BLEAK_DEVICE, return_value=MagicMock()),
        patch(ESTABLISH, new=AsyncMock(return_value=client)),
        patch.object(
            hass.config_entries, "async_reload", new=AsyncMock()
        ) as mock_reload,
    ):
        result = await flow._async_try_pair()

    assert result is True
    assert entry.data[CONF_BLE_BOND_ESTABLISHED] is True
    mock_reload.assert_awaited_once_with(entry.entry_id)
    client.disconnect.assert_awaited_once()


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
