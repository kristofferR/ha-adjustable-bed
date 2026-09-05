"""Integration tests for setting up a paired (Dual Bed 4.0) entry."""

from __future__ import annotations

import asyncio
from copy import copy
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed import (
    _async_release_absorbed_singles,
    _async_update_listener,
    _build_paired_children,
    _device_for_entry_and_identifier,
    _make_child_persist_cb,
    _maybe_create_pairing_issue_for,
    _shared_child_fields,
    async_unpair_entry,
)
from custom_components.adjustable_bed.const import (
    BED_TYPE_BEDTECH,
    BED_TYPE_KAIDI,
    BED_TYPE_KEESON,
    BED_TYPE_LEGGETT_GEN2,
    BED_TYPE_LEGGETT_OKIN,
    BED_TYPE_LEGGETT_PLATT,
    BED_TYPE_LEGGETT_WILINKE,
    BED_TYPE_LINAK,
    BED_TYPE_OCTO,
    BED_TYPE_RICHMAT,
    BED_TYPE_SBI,
    BED_TYPE_SOLACE,
    CONF_BED_TYPE,
    CONF_BLE_DEVICE_NAME,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_HAS_MASSAGE,
    CONF_KAIDI_RESOLVED_VARIANT,
    CONF_MOTOR_COUNT,
    CONF_PAIR_CHILDREN,
    CONF_PAIR_ID,
    CONF_PAIR_MEMBER_ADDRESSES,
    CONF_PAIR_MODE,
    CONF_PAIR_SCHEMA_VERSION,
    CONF_PREFERRED_ADAPTER,
    CONF_PROTOCOL_VARIANT,
    CONF_SIDE,
    DOMAIN,
    KAIDI_VARIANT_SEAT_1,
    KAIDI_VARIANT_SEAT_1_2,
    LEGGETT_VARIANT_GEN2,
    LEGGETT_VARIANT_MLRM,
    LEGGETT_VARIANT_OKIN,
    LINAK_VARIANT_PERFORMANCE,
    OCTO_VARIANT_STAR2,
    OFFLINE_CAPABILITY_SAFE_BED_TYPES,
    PAIR_MODE_SEPARATE_ADDRESS,
    PAIR_MODE_SINGLE_ADDRESS,
    SBI_VARIANT_BOTH,
    SIDE_BOTH,
    SIDE_LEFT,
    SIDE_RIGHT,
)
from custom_components.adjustable_bed.paired_coordinator import (
    PairedBedCoordinator,
    SingleAddressPairedCoordinator,
)
from custom_components.adjustable_bed.pairing import (
    effective_child_data,
    get_child,
    is_paired,
    octo_snapshot_from_descriptor,
    pair_member_addresses,
    with_updated_child,
)
from custom_components.adjustable_bed.pairing_candidates import (
    CONF_PAIR_SELECTION,
    decode_pair_selection,
    encode_pair_selection,
)

LEFT_ADDR = "AA:BB:CC:DD:EE:01"
RIGHT_ADDR = "AA:BB:CC:DD:EE:02"
PAIR_ID = "pair_test123456"

LINAK_ADVANCED_SNAPSHOT = {
    "profile": "bed_control",
    "model_variant": "advanced",
    "actuator_mask": 0xC0,
    "timer_supported": False,
    "discovery_complete": True,
}


def _linak_capabilities(*, motor_count: int = 2) -> dict:
    """Return the persisted layout and live-discovered Linak snapshot."""
    motor_keys = ["back", "legs"] if motor_count == 2 else ["back", "legs", "head"]
    return {
        "motor_count": motor_count,
        "motor_keys": motor_keys,
        "linak": dict(LINAK_ADVANCED_SNAPSHOT),
    }


def _child(side: str, address: str) -> dict:
    return {
        CONF_SIDE: side,
        CONF_ADDRESS: address,
        CONF_NAME: side.capitalize(),
        CONF_BED_TYPE: BED_TYPE_LINAK,
        CONF_MOTOR_COUNT: 2,
        CONF_DISABLE_ANGLE_SENSING: True,
        CONF_PREFERRED_ADAPTER: "auto",
        "capabilities": _linak_capabilities(),
    }


def _paired_entry_data() -> dict:
    return {
        CONF_PAIR_ID: PAIR_ID,
        CONF_PAIR_MODE: PAIR_MODE_SEPARATE_ADDRESS,
        CONF_PAIR_SCHEMA_VERSION: 1,
        CONF_BED_TYPE: BED_TYPE_LINAK,
        CONF_NAME: "Master Bed",
        CONF_PREFERRED_ADAPTER: "auto",
        CONF_PAIR_MEMBER_ADDRESSES: [LEFT_ADDR, RIGHT_ADDR],
        CONF_PAIR_CHILDREN: [
            _child(SIDE_LEFT, LEFT_ADDR),
            _child(SIDE_RIGHT, RIGHT_ADDR),
        ],
    }


def _paired_entry(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Master Bed",
        data=_paired_entry_data(),
        unique_id=PAIR_ID,
        entry_id="paired_test_entry",
        version=4,
    )
    entry.add_to_hass(hass)
    return entry


class TestPairedSetup:
    async def test_pair_setup_clears_pending_member_discoveries(
        self,
        hass: HomeAssistant,
        mock_bluetooth_service_info,
        mock_coordinator_connected,
        enable_custom_integrations,
    ) -> None:
        """Existing discovery cards disappear when their addresses join a pair."""
        flows = {}
        for address in (LEFT_ADDR, RIGHT_ADDR, "AA:BB:CC:DD:EE:03"):
            info = copy(mock_bluetooth_service_info)
            info.address = address.lower()
            result = await hass.config_entries.flow.async_init(
                DOMAIN, context={"source": config_entries.SOURCE_BLUETOOTH}, data=info
            )
            assert result["type"] == FlowResultType.FORM
            flows[address] = result["flow_id"]

        entry = _paired_entry(hass)
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        assert entry.state == ConfigEntryState.LOADED
        remaining = {
            flow["flow_id"]
            for flow in hass.config_entries.flow.async_progress_by_handler(DOMAIN)
        }
        assert remaining == {flows["AA:BB:CC:DD:EE:03"]}

    @pytest.mark.parametrize("address", [LEFT_ADDR, RIGHT_ADDR])
    async def test_pending_discovery_rechecks_pair_membership(
        self,
        hass: HomeAssistant,
        mock_bluetooth_service_info,
        enable_custom_integrations,
        address: str,
    ) -> None:
        """A discovery opened before pairing must not offer a duplicate afterward."""
        info = copy(mock_bluetooth_service_info)
        info.address = address.lower()
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_BLUETOOTH}, data=info
        )
        assert result["type"] == FlowResultType.FORM
        _paired_entry(hass)

        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})

        assert result["type"] == FlowResultType.ABORT
        assert result["reason"] == "already_configured"

    @pytest.mark.parametrize("address", [LEFT_ADDR, RIGHT_ADDR])
    async def test_new_discovery_rejects_pair_members(
        self,
        hass: HomeAssistant,
        mock_bluetooth_service_info,
        enable_custom_integrations,
        address: str,
    ) -> None:
        """Both sides stay suppressed on fresh Bluetooth discovery."""
        _paired_entry(hass)
        info = copy(mock_bluetooth_service_info)
        info.address = address.lower()

        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_BLUETOOTH}, data=info
        )

        assert result["type"] == FlowResultType.ABORT
        assert result["reason"] == "already_configured"

    @pytest.mark.parametrize(
        ("resolved_variant", "offers_pairing"),
        [
            (KAIDI_VARIANT_SEAT_1_2, True),
            (KAIDI_VARIANT_SEAT_1, False),
        ],
    )
    async def test_kaidi_pair_menu_requires_dual_lane_variant(
        self,
        hass: HomeAssistant,
        enable_custom_integrations,
        resolved_variant: str,
        offers_pairing: bool,
    ) -> None:
        """Only an auto-resolved Kaidi Seat 1+2 entry can enter Phase 3."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            title="Kaidi",
            data={
                CONF_ADDRESS: LEFT_ADDR,
                CONF_NAME: "Kaidi",
                CONF_BED_TYPE: BED_TYPE_KAIDI,
                CONF_PROTOCOL_VARIANT: "auto",
                CONF_KAIDI_RESOLVED_VARIANT: resolved_variant,
            },
            unique_id=LEFT_ADDR,
        )
        entry.add_to_hass(hass)

        result = await hass.config_entries.options.async_init(entry.entry_id)

        # The options flow always opens on a menu, so a bed that cannot pair its
        # sides is proven by the absence of the entry, not by skipping the menu.
        assert result["type"] == FlowResultType.MENU
        expected = {"settings", "remove_bond"}
        if offers_pairing:
            expected.add("pair_sides")
        assert set(result["menu_options"]) == expected

    async def test_single_address_pair_enable_and_revert_in_place(
        self,
        hass: HomeAssistant,
        mock_bleak_client,
        mock_coordinator_connected,
        enable_custom_integrations,
    ):
        """Phase 3 keeps the entry/MAC and reversibly adds logical side entities."""
        original_data = {
            CONF_ADDRESS: LEFT_ADDR,
            CONF_NAME: "SBI One Address",
            CONF_BED_TYPE: BED_TYPE_SBI,
            CONF_PROTOCOL_VARIANT: SBI_VARIANT_BOTH,
            CONF_MOTOR_COUNT: 4,
            CONF_DISABLE_ANGLE_SENSING: True,
            CONF_PREFERRED_ADAPTER: "auto",
        }
        entry = MockConfigEntry(
            domain=DOMAIN,
            title="SBI One Address",
            data=original_data,
            unique_id=LEFT_ADDR,
            entry_id="single_address_sbi",
            version=4,
        )
        entry.add_to_hass(hass)
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        result = await hass.config_entries.options.async_init(entry.entry_id)
        assert result["type"] == FlowResultType.MENU
        assert set(result["menu_options"]) == {"settings", "pair_sides", "remove_bond"}
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {"next_step_id": "pair_sides"}
        )
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {"confirm": True}
        )
        assert result["type"] == FlowResultType.CREATE_ENTRY
        await hass.async_block_till_done()

        assert entry.entry_id == "single_address_sbi"
        assert entry.unique_id == LEFT_ADDR
        assert entry.data[CONF_PAIR_MODE] == PAIR_MODE_SINGLE_ADDRESS
        assert isinstance(hass.data[DOMAIN][entry.entry_id], SingleAddressPairedCoordinator)
        rows = er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
        assert any(row.unique_id.endswith("_left") for row in rows)
        assert any(row.unique_id.endswith("_right") for row in rows)
        assert any(row.unique_id.endswith("_both") for row in rows)

        device = _device_for_entry_and_identifier(
            dr.async_get(hass), entry.entry_id, (DOMAIN, LEFT_ADDR)
        )
        assert device is not None
        mock_bleak_client.write_gatt_char.reset_mock()
        await hass.services.async_call(
            DOMAIN,
            "stop_all",
            {"device_id": [device.id]},
            blocking=True,
        )
        # Targeting the one physical device with no side must mean native both,
        # not the first logical side that happens to share its MAC.
        packet = mock_bleak_client.write_gatt_char.await_args.args[1]
        assert packet[0] == 0xE5

        await async_unpair_entry(hass, entry)
        await hass.async_block_till_done()

        assert entry.data == original_data
        assert entry.unique_id == LEFT_ADDR
        assert not is_paired(entry.data)
        rows = er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
        assert not any(
            row.unique_id.endswith(("_left", "_right", "_both"))
            for row in rows
            if row.unique_id not in entry.data.get("single_address_origin_entity_unique_ids", [])
        )

    async def test_paired_entry_loads_with_both_sides(
        self,
        hass: HomeAssistant,
        mock_coordinator_connected,
        enable_custom_integrations,
    ):
        """A paired entry sets up as one device with a PairedBedCoordinator."""
        entry = _paired_entry(hass)

        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        assert entry.state == ConfigEntryState.LOADED
        coordinator = hass.data[DOMAIN][entry.entry_id]
        assert isinstance(coordinator, PairedBedCoordinator)
        assert set(coordinator.sides) == {SIDE_LEFT, SIDE_RIGHT}

    async def test_splitting_a_bed_is_not_removing_its_bluetooth_bond(
        self,
        hass: HomeAssistant,
        mock_coordinator_connected,
        enable_custom_integrations,
    ):
        """Two separate features both wanted an options step called "unpair".

        Splitting a combined bed and removing a Bluetooth bond are unrelated and
        both destructive, so they must stay distinct handlers: defining them
        under one name would silently shadow whichever came first.
        """
        from custom_components.adjustable_bed.config_flow import AdjustableBedOptionsFlow

        assert (
            AdjustableBedOptionsFlow.async_step_unpair
            is not AdjustableBedOptionsFlow.async_step_remove_bond
        )

        entry = _paired_entry(hass)
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        menu = await hass.config_entries.options.async_init(entry.entry_id)
        result = await hass.config_entries.options.async_configure(
            menu["flow_id"], {"next_step_id": "unpair"}
        )

        # The split confirmation asks for a checkbox; the bond confirmation
        # takes no input and names the adapter the bond sits on instead.
        assert result["step_id"] == "unpair"
        assert [str(key) for key in result["data_schema"].schema] == ["confirm"]
        assert not result.get("description_placeholders")

    async def test_options_flow_exposes_confirmed_unpair(
        self,
        hass: HomeAssistant,
        mock_coordinator_connected,
        enable_custom_integrations,
    ):
        """A paired entry exposes unpair and runs it after the flow closes."""
        entry = _paired_entry(hass)
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        result = await hass.config_entries.options.async_init(entry.entry_id)
        assert result["type"] == FlowResultType.MENU
        assert set(result["menu_options"]) == {
            "settings",
            "unpair",
            "remove_bond",
        }

        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {"next_step_id": "unpair"}
        )
        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "unpair"

        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {"confirm": True}
        )
        assert result["type"] == FlowResultType.CREATE_ENTRY
        await hass.async_block_till_done()

        assert hass.config_entries.async_get_entry(entry.entry_id) is None
        restored = hass.config_entries.async_entries(DOMAIN)
        assert len(restored) == 2
        assert {candidate.data[CONF_ADDRESS] for candidate in restored} == {
            LEFT_ADDR,
            RIGHT_ADDR,
        }

    async def test_combined_bed_selects_a_side_before_bond_removal(
        self,
        hass: HomeAssistant,
        enable_custom_integrations,
    ) -> None:
        """A combined parent never guesses which child address the action means."""
        entry = _paired_entry(hass)

        menu = await hass.config_entries.options.async_init(entry.entry_id)
        result = await hass.config_entries.options.async_configure(
            menu["flow_id"],
            {"next_step_id": "remove_bond"},
        )

        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "remove_bond_side"
        side_field = next(iter(result["data_schema"].schema))
        choices = result["data_schema"].schema[side_field].container
        assert set(choices) == {SIDE_LEFT, SIDE_RIGHT}
        assert LEFT_ADDR in choices[SIDE_LEFT]
        assert RIGHT_ADDR in choices[SIDE_RIGHT]

    async def test_bond_removal_refuses_a_pair_without_resolvable_sides(
        self,
        hass: HomeAssistant,
        enable_custom_integrations,
    ) -> None:
        """Malformed child data must abort instead of rendering an empty selector."""
        data = _paired_entry_data()
        data[CONF_PAIR_CHILDREN] = [
            {
                CONF_SIDE: "middle",
                CONF_ADDRESS: LEFT_ADDR,
                CONF_NAME: "Unknown side",
                CONF_BED_TYPE: BED_TYPE_LINAK,
            }
        ]
        entry = MockConfigEntry(
            domain=DOMAIN,
            title="Malformed pair",
            data=data,
            unique_id=PAIR_ID,
            entry_id="malformed_pair_bond_removal",
            version=4,
        )
        entry.add_to_hass(hass)

        menu = await hass.config_entries.options.async_init(entry.entry_id)
        result = await hass.config_entries.options.async_configure(
            menu["flow_id"],
            {"next_step_id": "remove_bond"},
        )

        assert result["type"] == FlowResultType.ABORT
        assert result["reason"] == "remove_bond_ambiguous"

    async def test_bond_removal_refuses_children_with_one_shared_address(
        self,
        hass: HomeAssistant,
        enable_custom_integrations,
    ) -> None:
        """One host bond cannot safely be removed for only one child."""
        data = _paired_entry_data()
        data[CONF_PAIR_CHILDREN][1][CONF_ADDRESS] = LEFT_ADDR.lower()
        entry = MockConfigEntry(
            domain=DOMAIN,
            title="Ambiguous pair",
            data=data,
            unique_id=PAIR_ID,
            entry_id="ambiguous_pair_bond_removal",
            version=4,
        )
        entry.add_to_hass(hass)

        menu = await hass.config_entries.options.async_init(entry.entry_id)
        result = await hass.config_entries.options.async_configure(
            menu["flow_id"],
            {"next_step_id": "remove_bond"},
        )

        assert result["type"] == FlowResultType.ABORT
        assert result["reason"] == "remove_bond_ambiguous"

    @pytest.mark.parametrize("invalid_address", [None, 123, "", "   "])
    async def test_bond_removal_refuses_child_without_usable_address(
        self,
        hass: HomeAssistant,
        enable_custom_integrations,
        invalid_address: object,
    ) -> None:
        """Bond removal must not select a child whose address cannot be queried."""
        data = _paired_entry_data()
        data[CONF_PAIR_CHILDREN] = [data[CONF_PAIR_CHILDREN][0]]
        data[CONF_PAIR_CHILDREN][0][CONF_ADDRESS] = invalid_address
        entry = MockConfigEntry(
            domain=DOMAIN,
            title="Malformed pair",
            data=data,
            unique_id=PAIR_ID,
            entry_id="malformed_pair_address_bond_removal",
            version=4,
        )
        entry.add_to_hass(hass)

        menu = await hass.config_entries.options.async_init(entry.entry_id)
        result = await hass.config_entries.options.async_configure(
            menu["flow_id"],
            {"next_step_id": "remove_bond"},
        )

        assert result["type"] == FlowResultType.ABORT
        assert result["reason"] == "remove_bond_ambiguous"

    async def test_bond_removal_auto_selects_the_only_child(
        self,
        hass: HomeAssistant,
        enable_custom_integrations,
    ) -> None:
        """A one-child descriptor does not render a one-option selector."""
        from custom_components.adjustable_bed.config_flow import (
            AdjustableBedOptionsFlow,
        )

        data = _paired_entry_data()
        data[CONF_PAIR_CHILDREN] = [data[CONF_PAIR_CHILDREN][0]]
        entry = MockConfigEntry(
            domain=DOMAIN,
            title="Partial pair",
            data=data,
            unique_id=PAIR_ID,
            entry_id="partial_pair_bond_removal",
            version=4,
        )
        entry.add_to_hass(hass)
        original_remove_bond = AdjustableBedOptionsFlow.async_step_remove_bond
        selected: list[str | None] = []

        async def stop_after_selection(
            flow: AdjustableBedOptionsFlow,
            user_input: dict[str, Any] | None = None,
        ):
            if flow._bond_removal_side is None:
                return await original_remove_bond(flow, user_input)
            selected.append(flow._bond_removal_side)
            return {"type": FlowResultType.FORM}

        with patch.object(
            AdjustableBedOptionsFlow,
            "async_step_remove_bond",
            new=stop_after_selection,
        ):
            menu = await hass.config_entries.options.async_init(entry.entry_id)
            result = await hass.config_entries.options.async_configure(
                menu["flow_id"],
                {"next_step_id": "remove_bond"},
            )

        assert result["type"] == FlowResultType.FORM
        assert selected == [SIDE_LEFT]

    async def test_unpair_keeps_offline_restored_beds(
        self,
        hass: HomeAssistant,
        mock_coordinator_connected,
        enable_custom_integrations,
    ):
        """Offline sides remain restored and retry setup after the pair is removed."""
        from unittest.mock import patch

        from homeassistant.exceptions import ConfigEntryNotReady

        from custom_components.adjustable_bed.coordinator import (
            AdjustableBedCoordinator,
        )

        entry = _paired_entry(hass)
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        async def offline_connect(_coordinator):
            raise ConfigEntryNotReady("bed is offline")

        with patch.object(
            AdjustableBedCoordinator,
            "async_connect",
            new=offline_connect,
        ):
            restored = await async_unpair_entry(hass, entry)

        assert hass.config_entries.async_get_entry(entry.entry_id) is None
        assert {candidate.data[CONF_ADDRESS] for candidate in restored} == {
            LEFT_ADDR,
            RIGHT_ADDR,
        }
        assert all(candidate.disabled_by is None for candidate in restored)
        assert all(candidate.state == ConfigEntryState.SETUP_RETRY for candidate in restored)
        for candidate in restored:
            candidate.async_cancel_retry_setup()

    async def test_unpair_rolls_back_if_second_single_cannot_be_added(
        self,
        hass: HomeAssistant,
        mock_coordinator_connected,
        enable_custom_integrations,
    ):
        """A partial unpair restores the paired entry and registry ownership."""
        from unittest.mock import patch

        entry = _paired_entry(hass)
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        ent_reg = er.async_get(hass)
        row_id = ent_reg.async_get_entity_id("cover", DOMAIN, f"{LEFT_ADDR}_back")
        assert row_id is not None

        real_add = hass.config_entries.async_add
        calls = 0

        async def fail_second(single):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise RuntimeError("injected second-side failure")
            await real_add(single)

        with (
            patch.object(hass.config_entries, "async_add", side_effect=fail_second),
            patch(
                "custom_components.adjustable_bed._async_transfer_device_registry_entry"
            ) as transfer_device,
            pytest.raises(RuntimeError, match="injected second-side failure"),
        ):
            await async_unpair_entry(hass, entry)
        await hass.async_block_till_done()

        transfer_device.assert_not_called()
        pair = hass.config_entries.async_get_entry(entry.entry_id)
        assert pair is not None
        assert pair.state == ConfigEntryState.LOADED
        assert len(hass.config_entries.async_entries(DOMAIN)) == 1
        row = ent_reg.async_get(row_id)
        assert row is not None
        assert row.config_entry_id == entry.entry_id
        device = _device_for_entry_and_identifier(
            dr.async_get(hass), entry.entry_id, (DOMAIN, LEFT_ADDR)
        )
        assert device is not None
        assert device.config_entry_id == entry.entry_id

    async def test_paired_entry_creates_parent_and_child_devices(
        self,
        hass: HomeAssistant,
        mock_coordinator_connected,
        enable_custom_integrations,
    ):
        """The synthetic parent device exists with both sides nested via_device."""
        entry = _paired_entry(hass)
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        registry = dr.async_get(hass)
        parent = _device_for_entry_and_identifier(registry, entry.entry_id, (DOMAIN, PAIR_ID))
        assert parent is not None

        left = _device_for_entry_and_identifier(registry, entry.entry_id, (DOMAIN, LEFT_ADDR))
        right = _device_for_entry_and_identifier(registry, entry.entry_id, (DOMAIN, RIGHT_ADDR))
        assert left is not None and right is not None
        assert left.via_device_id == parent.id
        assert right.via_device_id == parent.id

    async def test_paired_entry_exposes_per_side_covers_and_combined_stop(
        self,
        hass: HomeAssistant,
        mock_coordinator_connected,
        enable_custom_integrations,
    ):
        """Per-side motor covers + a combined stop button are created."""
        entry = _paired_entry(hass)
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        registry = er.async_get(hass)
        entries = [e for e in registry.entities.values() if e.config_entry_id == entry.entry_id]
        covers = [e for e in entries if e.domain == "cover"]
        buttons = [e for e in entries if e.domain == "button"]

        # back + legs per side = 4 covers, one per child address.
        cover_uids = {e.unique_id for e in covers}
        assert f"{LEFT_ADDR}_back" in cover_uids
        assert f"{LEFT_ADDR}_legs" in cover_uids
        assert f"{RIGHT_ADDR}_back" in cover_uids
        assert f"{RIGHT_ADDR}_legs" in cover_uids

        # combined controls on the parent: stop + 'both' movement/preset buttons.
        both_uids = {e.unique_id for e in buttons if e.unique_id.endswith("_both")}
        assert f"{PAIR_ID}_stop_both" in both_uids
        assert both_uids - {f"{PAIR_ID}_stop_both"}, (
            "expected combined movement/preset buttons on the parent"
        )
        # A cover-based pair (Linak) has no combined cover, so the parent gets
        # per-motor "both sides" up/down motion buttons instead.
        for key in ("back_up", "back_down", "legs_up", "legs_down"):
            assert f"{PAIR_ID}_{key}_both" in both_uids

    async def test_performance_profile_auto_enables_combined_massage_buttons(
        self,
        hass: HomeAssistant,
        mock_coordinator_connected,
        enable_custom_integrations,
    ) -> None:
        """Protocol-declared massage should apply to paired parent controls."""
        entry = _paired_entry(hass)
        children = [
            {
                **child,
                CONF_PROTOCOL_VARIANT: LINAK_VARIANT_PERFORMANCE,
                CONF_HAS_MASSAGE: False,
            }
            for child in entry.data[CONF_PAIR_CHILDREN]
        ]
        hass.config_entries.async_update_entry(
            entry,
            data={**entry.data, CONF_PAIR_CHILDREN: children},
        )

        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        registry = er.async_get(hass)
        assert (
            registry.async_get_entity_id(
                "button",
                DOMAIN,
                f"{PAIR_ID}_massage_all_toggle_both",
            )
            is not None
        )

    async def test_paired_entry_migrates_combined_massage_intensity_ids(
        self,
        hass: HomeAssistant,
        mock_coordinator_connected,
        enable_custom_integrations,
    ) -> None:
        """Briefly shipped combined intensity IDs keep their entity IDs."""
        data = _paired_entry_data()
        data[CONF_BED_TYPE] = BED_TYPE_KEESON
        for child in data[CONF_PAIR_CHILDREN]:
            child.update(
                {
                    CONF_BED_TYPE: BED_TYPE_KEESON,
                    CONF_PROTOCOL_VARIANT: "base",
                    CONF_HAS_MASSAGE: True,
                }
            )
        entry = MockConfigEntry(
            domain=DOMAIN,
            title="Paired Keeson Bed",
            data=data,
            unique_id=PAIR_ID,
            entry_id="paired_keeson_migration_entry",
            version=4,
        )
        entry.add_to_hass(hass)

        registry = er.async_get(hass)
        legacy_entries = {
            level: registry.async_get_or_create(
                "button",
                DOMAIN,
                f"{PAIR_ID}_massage_intensity_{level}_both",
                config_entry=entry,
                suggested_object_id=f"paired_keeson_massage_intensity_{level}",
            )
            for level in range(1, 4)
        }

        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        for level, legacy_entry in legacy_entries.items():
            new_unique_id = f"{PAIR_ID}_massage_intensity_level_{level}_both"
            assert registry.async_get_entity_id("button", DOMAIN, new_unique_id) == str(
                legacy_entry.entity_id
            )
            assert (
                registry.async_get_entity_id(
                    "button",
                    DOMAIN,
                    f"{PAIR_ID}_massage_intensity_{level}_both",
                )
                is None
            )

    async def test_diagnostics_for_paired_entry_does_not_crash(
        self,
        hass: HomeAssistant,
        mock_coordinator_connected,
        enable_custom_integrations,
    ):
        """Diagnostics for a paired entry aggregate per side instead of crashing."""
        from custom_components.adjustable_bed.diagnostics import (
            async_get_config_entry_diagnostics,
        )

        entry = _paired_entry(hass)
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        diag = await async_get_config_entry_diagnostics(hass, entry)
        assert diag["paired"] is True
        assert set(diag["sides"]) == {SIDE_LEFT, SIDE_RIGHT}

    async def test_stop_all_on_child_device_infers_that_side(
        self,
        hass: HomeAssistant,
        mock_coordinator_connected,
        enable_custom_integrations,
    ):
        """stop_all targeting a side's child device acts on only that side."""
        from unittest.mock import AsyncMock, patch

        entry = _paired_entry(hass)
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        coordinator = hass.data[DOMAIN][entry.entry_id]

        dev_reg = dr.async_get(hass)
        left_device = next(
            device
            for device in dr.async_entries_for_config_entry(dev_reg, entry.entry_id)
            if any(i[0] == DOMAIN and i[1].upper() == LEFT_ADDR.upper() for i in device.identifiers)
        )

        with patch.object(coordinator, "async_stop_command", new=AsyncMock()) as mock_stop:
            await hass.services.async_call(
                DOMAIN, "stop_all", {"device_id": left_device.id}, blocking=True
            )
        mock_stop.assert_awaited_once_with(side=SIDE_LEFT)

    async def test_stop_all_on_both_child_devices_coalesces_to_both(
        self,
        hass: HomeAssistant,
        mock_coordinator_connected,
        enable_custom_integrations,
    ):
        """Targeting both children in one call collapses to a single side=both."""
        from unittest.mock import AsyncMock, patch

        entry = _paired_entry(hass)
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        coordinator = hass.data[DOMAIN][entry.entry_id]

        dev_reg = dr.async_get(hass)

        def device_for(addr: str):
            return next(
                device
                for device in dr.async_entries_for_config_entry(dev_reg, entry.entry_id)
                if any(i[0] == DOMAIN and i[1].upper() == addr.upper() for i in device.identifiers)
            )

        with patch.object(coordinator, "async_stop_command", new=AsyncMock()) as mock_stop:
            await hass.services.async_call(
                DOMAIN,
                "stop_all",
                {"device_id": [device_for(LEFT_ADDR).id, device_for(RIGHT_ADDR).id]},
                blocking=True,
            )
        mock_stop.assert_awaited_once_with(side=SIDE_BOTH)

    async def test_set_position_on_parent_reports_capability_error(
        self,
        hass: HomeAssistant,
        mock_coordinator_connected,
        enable_custom_integrations,
    ):
        """The paired parent is accepted, then normal capability checks apply."""
        entry = _paired_entry(hass)
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        dev_reg = dr.async_get(hass)
        parent = next(
            device
            for device in dr.async_entries_for_config_entry(dev_reg, entry.entry_id)
            if (DOMAIN, PAIR_ID) in device.identifiers
        )
        with pytest.raises(ServiceValidationError, match="Angle sensing is disabled"):
            await hass.services.async_call(
                DOMAIN,
                "set_position",
                {"device_id": parent.id, "motor": "back", "position": 50},
                blocking=True,
            )

    async def test_paired_entry_unloads(
        self,
        hass: HomeAssistant,
        mock_coordinator_connected,
        enable_custom_integrations,
    ):
        entry = _paired_entry(hass)
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        assert entry.state == ConfigEntryState.LOADED

        assert await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()
        assert entry.state == ConfigEntryState.NOT_LOADED
        assert entry.entry_id not in hass.data[DOMAIN]


class TestPairedBuilders:
    """Unit tests for the child-construction helpers (no BLE)."""

    def test_shared_child_fields_excludes_pair_keys(self):
        data = {
            **_paired_entry_data(),
            "ble_bond_established": True,
            "ble_bond_marker_unreliable": True,
            "ble_bond_context": {"transport": "local"},
            "ble_bond_attempted_source": "hci0",
        }
        shared = _shared_child_fields(data)
        assert CONF_PAIR_ID not in shared
        assert CONF_PAIR_CHILDREN not in shared
        assert CONF_PAIR_MODE not in shared
        assert "ble_bond_established" not in shared
        assert "ble_bond_marker_unreliable" not in shared
        assert "ble_bond_context" not in shared
        assert "ble_bond_attempted_source" not in shared
        # shared, non-pair fields survive
        assert shared[CONF_BED_TYPE] == BED_TYPE_LINAK

    def test_effective_child_data_filters_excluded_options(self):
        data = _paired_entry_data()
        child_data = effective_child_data(
            data,
            SIDE_LEFT,
            {
                CONF_PAIR_MODE: "invalid",
                "ble_bond_established": True,
                CONF_MOTOR_COUNT: 3,
            },
        )

        assert CONF_PAIR_MODE not in child_data
        assert "ble_bond_established" not in child_data
        assert child_data[CONF_MOTOR_COUNT] == 3

    async def test_build_children_reads_per_side_descriptor(self, hass: HomeAssistant):
        entry = _paired_entry(hass)
        children = _build_paired_children(hass, entry)
        assert set(children) == {SIDE_LEFT, SIDE_RIGHT}
        # each child reads its own address from its descriptor
        assert children[SIDE_LEFT].address == LEFT_ADDR
        assert children[SIDE_RIGHT].address == RIGHT_ADDR

    async def test_child_persist_writes_delta_to_correct_descriptor(self, hass: HomeAssistant):
        entry = _paired_entry(hass)
        baseline = {**_shared_child_fields(entry.data), **_child(SIDE_LEFT, LEFT_ADDR)}
        persist = _make_child_persist_cb(hass, entry, SIDE_LEFT)

        # Persist a change (e.g. a BLE bond marker) for the left side.
        persist({**baseline, "ble_bond_established": True})

        left = get_child(entry.data, SIDE_LEFT)
        right = get_child(entry.data, SIDE_RIGHT)
        assert left["ble_bond_established"] is True
        assert "ble_bond_established" not in right  # right untouched

    async def test_excluded_option_does_not_block_child_bond_persistence(
        self,
        hass: HomeAssistant,
    ) -> None:
        entry = _paired_entry(hass)
        hass.config_entries.async_update_entry(
            entry,
            options={"ble_bond_established": False},
        )
        baseline = {**_shared_child_fields(entry.data), **_child(SIDE_LEFT, LEFT_ADDR)}
        persist = _make_child_persist_cb(hass, entry, SIDE_LEFT)

        persist({**baseline, "ble_bond_established": True})

        left = get_child(entry.data, SIDE_LEFT)
        assert left is not None
        assert left["ble_bond_established"] is True

    async def test_child_persist_noop_when_unchanged(self, hass: HomeAssistant):
        entry = _paired_entry(hass)
        before = entry.data
        baseline = {**_shared_child_fields(entry.data), **_child(SIDE_LEFT, LEFT_ADDR)}
        persist = _make_child_persist_cb(hass, entry, SIDE_LEFT)
        persist(dict(baseline))  # no change
        assert entry.data is before  # entry not updated

    async def test_child_persist_can_revert_a_value(self, hass: HomeAssistant):
        # A value set then reverted must still be written (compares against the
        # live descriptor, not a stale build-time baseline).
        entry = _paired_entry(hass)
        baseline = {**_shared_child_fields(entry.data), **_child(SIDE_LEFT, LEFT_ADDR)}
        persist = _make_child_persist_cb(hass, entry, SIDE_LEFT)

        persist({**baseline, "ble_bond_established": True})
        assert get_child(entry.data, SIDE_LEFT)["ble_bond_established"] is True
        persist({**baseline, "ble_bond_established": False})
        assert get_child(entry.data, SIDE_LEFT)["ble_bond_established"] is False

    async def test_child_persist_removes_runtime_bond_keys(self, hass: HomeAssistant):
        """Confirmed removal must delete markers instead of leaving stale overrides."""
        entry = _paired_entry(hass)
        baseline = {**_shared_child_fields(entry.data), **_child(SIDE_LEFT, LEFT_ADDR)}
        persist = _make_child_persist_cb(hass, entry, SIDE_LEFT)
        persist(
            {
                **baseline,
                "ble_bond_established": True,
                "ble_bond_context": {
                    "version": 1,
                    "transport": "local",
                    "source": "hci0",
                },
                "ble_bond_attempted_source": "hci0",
            }
        )

        persist(dict(baseline))

        left = get_child(entry.data, SIDE_LEFT)
        right = get_child(entry.data, SIDE_RIGHT)
        assert "ble_bond_established" not in left
        assert "ble_bond_context" not in left
        assert "ble_bond_attempted_source" not in left
        assert "ble_bond_established" not in right

    async def test_child_bond_removal_is_consumed_without_reloading_the_pair(
        self,
        hass: HomeAssistant,
    ) -> None:
        """The parent listener must recognize the child's internal state write."""
        from custom_components.adjustable_bed import _async_update_listener

        entry = _paired_entry(hass)
        hass.config_entries.async_update_entry(
            entry,
            data=with_updated_child(
                {**entry.data, "connection_profile": "performance"},
                SIDE_LEFT,
                {
                    "ble_bond_established": True,
                    "ble_bond_context": {
                        "version": 1,
                        "transport": "local",
                        "source": "hci0",
                    },
                },
            ),
        )
        children = _build_paired_children(hass, entry)
        coordinator = PairedBedCoordinator(hass, entry, children)
        hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
        remove_listener = entry.add_update_listener(_async_update_listener)

        try:
            with patch.object(
                hass.config_entries,
                "async_reload",
                new_callable=AsyncMock,
            ) as reload_entry:
                children[SIDE_LEFT].apply_confirmed_bond_removal()
                await hass.async_block_till_done()

            reload_entry.assert_not_awaited()
        finally:
            remove_listener()
            hass.data[DOMAIN].pop(entry.entry_id, None)

        left = get_child(entry.data, SIDE_LEFT)
        assert left is not None
        assert "ble_bond_established" not in left
        assert "ble_bond_context" not in left
        assert "connection_profile" not in left

    async def test_each_parent_listener_consumes_one_child_bond_update(
        self,
        hass: HomeAssistant,
    ) -> None:
        """Each queued parent write retains one matching child marker."""
        entry = _paired_entry(hass)
        children = _build_paired_children(hass, entry)
        coordinator = PairedBedCoordinator(hass, entry, children)
        hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

        try:
            children[SIDE_LEFT].begin_internal_bond_update(False)
            children[SIDE_RIGHT].begin_internal_bond_update(False)
            assert coordinator.consume_internal_entry_update(entry) is True
            assert coordinator.consume_internal_entry_update(entry) is True
            assert coordinator.consume_internal_entry_update(entry) is False
        finally:
            hass.data[DOMAIN].pop(entry.entry_id, None)


class TestPairBedsConversion:
    """The 'combine two beds' config-flow step."""

    def _single(
        self,
        hass: HomeAssistant,
        address: str,
        name: str,
        bed_type: str = BED_TYPE_LINAK,
    ) -> MockConfigEntry:
        data = {
            CONF_ADDRESS: address,
            CONF_NAME: name,
            CONF_BED_TYPE: bed_type,
            CONF_MOTOR_COUNT: 2,
            CONF_DISABLE_ANGLE_SENSING: True,
            CONF_PREFERRED_ADAPTER: "auto",
        }
        if bed_type == BED_TYPE_LINAK:
            data["capabilities"] = _linak_capabilities()
        entry = MockConfigEntry(
            domain=DOMAIN,
            title=name,
            data=data,
            unique_id=address,
            version=4,
            state=ConfigEntryState.LOADED,
        )
        entry.add_to_hass(hass)
        return entry

    async def _reach_pair_step(self, hass: HomeAssistant):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        assert result["type"] == FlowResultType.FORM
        return await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_ADDRESS: "pair_beds"}
        )

    async def _setup_single(self, hass: HomeAssistant, address: str, name: str) -> MockConfigEntry:
        """Set up a REAL single Linak bed so it owns real entity/device rows."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            title=name,
            data={
                CONF_ADDRESS: address,
                CONF_NAME: name,
                CONF_BED_TYPE: BED_TYPE_LINAK,
                CONF_MOTOR_COUNT: 2,
                CONF_DISABLE_ANGLE_SENSING: True,
                CONF_PREFERRED_ADAPTER: "auto",
                "capabilities": _linak_capabilities(),
            },
            unique_id=address,
            version=4,
        )
        entry.add_to_hass(hass)
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        assert entry.state == ConfigEntryState.LOADED
        return entry

    async def test_combine_two_singles_into_one_pair(
        self,
        hass: HomeAssistant,
        mock_coordinator_connected,
        enable_custom_integrations,
    ):
        left = self._single(hass, LEFT_ADDR, "Seng")
        right = self._single(hass, RIGHT_ADDR, "Bed 4587")

        result = await self._reach_pair_step(hass)
        assert result["step_id"] == "pair_beds"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_PAIR_SELECTION: encode_pair_selection(left.entry_id, right.entry_id),
                CONF_NAME: "Master Bed",
            },
        )
        await hass.async_block_till_done()

        assert result["type"] == FlowResultType.CREATE_ENTRY
        remaining = hass.config_entries.async_entries(DOMAIN)
        ids = {entry.entry_id for entry in remaining}
        assert left.entry_id not in ids  # originals removed
        assert right.entry_id not in ids
        paired = [entry for entry in remaining if is_paired(entry.data)]
        assert len(paired) == 1
        assert set(pair_member_addresses(paired[0].data)) == {LEFT_ADDR, RIGHT_ADDR}

    async def test_pair_form_defaults_to_distinct_beds_and_cannot_select_same_bed(
        self,
        hass: HomeAssistant,
        mock_coordinator_connected,
        enable_custom_integrations,
    ):
        """The side picker starts valid and only offers distinct assignments."""
        left = self._single(hass, LEFT_ADDR, "Seng")
        right = self._single(hass, RIGHT_ADDR, "Bed 4587")

        result = await self._reach_pair_step(hass)
        schema = result.get("data_schema")
        assert schema is not None
        defaults = schema({})
        assert isinstance(defaults, dict)

        assert decode_pair_selection(defaults[CONF_PAIR_SELECTION]) == (
            left.entry_id,
            right.entry_id,
        )
        reversed_assignment = schema(
            {CONF_PAIR_SELECTION: encode_pair_selection(right.entry_id, left.entry_id)}
        )
        assert isinstance(reversed_assignment, dict)
        assert reversed_assignment[CONF_PAIR_SELECTION] == encode_pair_selection(
            right.entry_id, left.entry_id
        )
        with pytest.raises(vol.Invalid):
            schema({CONF_PAIR_SELECTION: encode_pair_selection(left.entry_id, left.entry_id)})

    async def test_pairing_blocked_for_unsafe_offline_platform_entities(
        self,
        hass: HomeAssistant,
        mock_coordinator_connected,
        enable_custom_integrations,
    ):
        """A NON-offline-capability-safe bed exposing climate/light/select stays
        blocked: those platforms are forwarded per-side now (Phase 2.3), but such
        a bed can't rebuild them when a side is offline, so a half-available pair
        would lose them. (Richmat is not in OFFLINE_CAPABILITY_SAFE_BED_TYPES.)"""
        from homeassistant.helpers import entity_registry as er

        left = self._single(hass, LEFT_ADDR, "Left", bed_type=BED_TYPE_RICHMAT)
        right = self._single(hass, RIGHT_ADDR, "Right", bed_type=BED_TYPE_RICHMAT)
        er.async_get(hass).async_get_or_create(
            "select", DOMAIN, f"{LEFT_ADDR}_firmness", config_entry=left
        )

        result = await self._reach_pair_step(hass)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_PAIR_SELECTION: encode_pair_selection(left.entry_id, right.entry_id)},
        )
        assert result["type"] == FlowResultType.FORM
        assert result["errors"]["base"] == "pairing_unsupported_entities"

    async def test_pairing_blocked_for_same_address(
        self,
        hass: HomeAssistant,
        mock_coordinator_connected,
        enable_custom_integrations,
    ):
        """Two distinct entries for the same MAC can't be paired (would collide)."""
        left = self._single(hass, LEFT_ADDR, "Left")
        right = MockConfigEntry(
            domain=DOMAIN,
            title="Left duplicate",
            data={
                CONF_ADDRESS: LEFT_ADDR,
                CONF_NAME: "Left duplicate",
                CONF_BED_TYPE: BED_TYPE_LINAK,
                CONF_MOTOR_COUNT: 2,
                CONF_DISABLE_ANGLE_SENSING: True,
                CONF_PREFERRED_ADAPTER: "auto",
            },
            unique_id=f"{LEFT_ADDR}-dup",
            version=4,
            state=ConfigEntryState.LOADED,
        )
        right.add_to_hass(hass)

        result = await self._reach_pair_step(hass)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_PAIR_SELECTION: encode_pair_selection(left.entry_id, right.entry_id)},
        )
        assert result["type"] == FlowResultType.FORM
        assert result["errors"].get(CONF_PAIR_SELECTION) == "same_address"

    async def test_pairing_preserves_angle_options(
        self,
        hass: HomeAssistant,
        mock_coordinator_connected,
        enable_custom_integrations,
    ):
        """Customized angle limits in entry.options survive into the child."""
        from custom_components.adjustable_bed.const import SIDE_LEFT
        from custom_components.adjustable_bed.pairing import get_child

        left = self._single(hass, LEFT_ADDR, "Left")
        right = self._single(hass, RIGHT_ADDR, "Right")
        hass.config_entries.async_update_entry(left, options={"back_max_angle": 55.0})

        result = await self._reach_pair_step(hass)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_PAIR_SELECTION: encode_pair_selection(left.entry_id, right.entry_id)},
        )
        await hass.async_block_till_done()
        assert result["type"] == FlowResultType.CREATE_ENTRY

        paired = next(
            entry for entry in hass.config_entries.async_entries(DOMAIN) if is_paired(entry.data)
        )
        left_child = get_child(paired.data, SIDE_LEFT)
        assert left_child is not None
        assert left_child[CONF_ADDRESS] == LEFT_ADDR
        assert left_child.get("back_max_angle") == 55.0

    async def test_pairing_blocks_mismatched_motor_layouts(
        self,
        hass: HomeAssistant,
        mock_coordinator_connected,
        enable_custom_integrations,
    ):
        """Matching protocols with different motor layouts cannot be paired."""
        left = self._single(hass, LEFT_ADDR, "Left")
        right = self._single(hass, RIGHT_ADDR, "Right")
        hass.config_entries.async_update_entry(
            right,
            data={
                **right.data,
                CONF_MOTOR_COUNT: 3,
                "capabilities": _linak_capabilities(motor_count=3),
            },
        )

        result = await self._reach_pair_step(hass)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_PAIR_SELECTION: encode_pair_selection(left.entry_id, right.entry_id)},
        )
        assert result["type"] == FlowResultType.FORM
        assert result["errors"]["base"] == "mismatched_motor_layouts"

    async def test_octo_pairing_blocked_without_connection(
        self,
        hass: HomeAssistant,
        mock_coordinator_connected,
        enable_custom_integrations,
    ):
        """Octo pairing is blocked when the beds aren't connected: their offline
        side is minted from a capability snapshot captured here from the live bed,
        which doesn't exist until connected (Phase 2.5)."""
        for addr, name in ((LEFT_ADDR, "Octo L"), (RIGHT_ADDR, "Octo R")):
            MockConfigEntry(
                domain=DOMAIN,
                title=name,
                data={CONF_ADDRESS: addr, CONF_NAME: name, CONF_BED_TYPE: BED_TYPE_OCTO},
                unique_id=addr,
                version=4,
                state=ConfigEntryState.LOADED,
            ).add_to_hass(hass)

        result = await self._reach_pair_step(hass)
        entries = self._pairable_octo_ids(hass)
        assert len(entries) >= 2  # keep the real assertion below diagnostic
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_PAIR_SELECTION: encode_pair_selection(entries[0], entries[1])},
        )
        assert result["type"] == FlowResultType.FORM
        assert result["errors"]["base"] == "octo_pairing_needs_connection"

    async def test_octo_one_motor_lifts_cannot_be_paired_as_bed_sides(
        self,
        hass: HomeAssistant,
        mock_coordinator_connected,
        enable_custom_integrations,
    ):
        """Matching one-motor OCTO lifts remain separate standalone devices."""
        left = self._single(hass, LEFT_ADDR, "RTV Left", bed_type=BED_TYPE_OCTO)
        right = self._single(hass, RIGHT_ADDR, "RTV Right", bed_type=BED_TYPE_OCTO)
        for entry in (left, right):
            hass.config_entries.async_update_entry(
                entry,
                data={
                    **entry.data,
                    CONF_MOTOR_COUNT: 1,
                },
            )

        result = await self._reach_pair_step(hass)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_PAIR_SELECTION: encode_pair_selection(left.entry_id, right.entry_id)},
        )

        assert result["type"] == FlowResultType.FORM
        assert result["errors"]["base"] == "octo_tv_lift_pairing_unsupported"

    async def test_standard_octo_and_star2_pair_when_layouts_match(
        self,
        hass: HomeAssistant,
        mock_coordinator_connected,
        enable_custom_integrations,
    ):
        """The accepted standard-Octo plus Star2 combination is not rejected."""
        from types import SimpleNamespace

        from custom_components.adjustable_bed.coordinator import (
            AdjustableBedCoordinator,
        )

        snapshot = {
            "has_pin": False,
            "pin_locked": False,
            "has_lights": False,
            "has_rgbwi": False,
            "rgbwi_value_type": None,
            "memory_count": 0,
            "discovered_motor_count": 2,
            "has_synchro": False,
        }
        standard = MockConfigEntry(
            domain=DOMAIN,
            title="Standard Octo",
            data={
                CONF_ADDRESS: LEFT_ADDR,
                CONF_NAME: "Standard Octo",
                CONF_BED_TYPE: BED_TYPE_OCTO,
                CONF_MOTOR_COUNT: 2,
                "capabilities": {"octo": snapshot},
            },
            unique_id=LEFT_ADDR,
            version=4,
            state=ConfigEntryState.LOADED,
        )
        star2 = MockConfigEntry(
            domain=DOMAIN,
            title="Star2",
            data={
                CONF_ADDRESS: RIGHT_ADDR,
                CONF_NAME: "Star2",
                CONF_BED_TYPE: BED_TYPE_OCTO,
                CONF_PROTOCOL_VARIANT: OCTO_VARIANT_STAR2,
                CONF_MOTOR_COUNT: 2,
            },
            unique_id=RIGHT_ADDR,
            version=4,
            state=ConfigEntryState.LOADED,
        )
        standard.add_to_hass(hass)
        star2.add_to_hass(hass)

        hass.data.setdefault(DOMAIN, {})
        for entry in (standard, star2):
            coordinator = AdjustableBedCoordinator(hass, entry)
            await coordinator.async_prime_offline_controller()
            controller = coordinator.capability_controller
            assert controller is not None
            hass.data[DOMAIN][entry.entry_id] = SimpleNamespace(
                controller=controller,
                capability_controller=controller,
            )

        result = await self._reach_pair_step(hass)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_PAIR_SELECTION: encode_pair_selection(standard.entry_id, star2.entry_id)},
        )
        assert result["type"] == FlowResultType.CREATE_ENTRY

    async def test_octo_gate_allows_and_captures_when_snapshot_present(self, hass: HomeAssistant):
        """With a live capability snapshot, Octo is offline-safe (gate passes) and
        the snapshot is captured into the built pair descriptor."""
        from types import SimpleNamespace

        from custom_components.adjustable_bed.config_flow import (
            AdjustableBedConfigFlow,
        )
        from custom_components.adjustable_bed.pairing import (
            build_pair_entry_data,
            octo_snapshot_from_descriptor,
        )

        snap = {"has_lights": True, "memory_count": 4, "has_rgbwi": False}
        entry = MockConfigEntry(
            domain=DOMAIN,
            data={CONF_ADDRESS: LEFT_ADDR, CONF_BED_TYPE: BED_TYPE_OCTO},
            unique_id=LEFT_ADDR,
            version=4,
        )
        entry.add_to_hass(hass)
        hass.data.setdefault(DOMAIN, {})[entry.entry_id] = SimpleNamespace(
            controller=SimpleNamespace(capability_snapshot=lambda: dict(snap))
        )

        flow = AdjustableBedConfigFlow()
        flow.hass = hass
        # Gate: a live snapshot makes Octo offline-safe AND is cached on the flow,
        # so the side stays safe even after it disconnects (sequential capture).
        assert flow._octo_capability_snapshot(entry) == snap
        assert flow._has_unsafe_offline_platforms(entry) is False
        hass.data[DOMAIN].pop(entry.entry_id)
        assert flow._octo_capability_snapshot(entry) == snap  # cached, survives drop
        assert flow._has_unsafe_offline_platforms(entry) is False
        # A FRESH flow that never saw a live snapshot keeps Octo unsafe.
        fresh = AdjustableBedConfigFlow()
        fresh.hass = hass
        assert fresh._octo_capability_snapshot(entry) is None
        assert fresh._has_unsafe_offline_platforms(entry) is True
        # Capture: the snapshot lands in the built descriptor's capabilities['octo'].
        pair = build_pair_entry_data(
            {CONF_ADDRESS: LEFT_ADDR, CONF_BED_TYPE: BED_TYPE_OCTO},
            {CONF_ADDRESS: RIGHT_ADDR, CONF_BED_TYPE: BED_TYPE_OCTO},
            name="Master Octo",
            left_octo_snapshot=snap,
            right_octo_snapshot=snap,
        )
        assert octo_snapshot_from_descriptor(get_child(pair, SIDE_LEFT)) == snap

    async def test_octo_sequential_two_side_capture(self, hass: HomeAssistant):
        """One-link Octo capture: connect LEFT (captured), disconnect it, connect
        RIGHT (captured) — both snapshots are available afterwards though only one
        side was ever live at a time, so the pair gate no longer needs both live."""
        from types import SimpleNamespace

        from custom_components.adjustable_bed.config_flow import (
            AdjustableBedConfigFlow,
        )

        left = MockConfigEntry(
            domain=DOMAIN,
            data={CONF_ADDRESS: LEFT_ADDR, CONF_BED_TYPE: BED_TYPE_OCTO},
            unique_id=LEFT_ADDR,
            version=4,
        )
        right = MockConfigEntry(
            domain=DOMAIN,
            data={CONF_ADDRESS: RIGHT_ADDR, CONF_BED_TYPE: BED_TYPE_OCTO},
            unique_id=RIGHT_ADDR,
            version=4,
        )
        left.add_to_hass(hass)
        right.add_to_hass(hass)
        lsnap = {"has_lights": True, "memory_count": 4}
        rsnap = {"has_lights": False, "memory_count": 2}

        flow = AdjustableBedConfigFlow()
        flow.hass = hass
        store = hass.data.setdefault(DOMAIN, {})

        # Connect LEFT only -> captured.
        store[left.entry_id] = SimpleNamespace(
            controller=SimpleNamespace(capability_snapshot=lambda: dict(lsnap))
        )
        assert flow._octo_capability_snapshot(left) == lsnap

        # Disconnect LEFT, connect RIGHT -> captured; LEFT served from cache.
        store.pop(left.entry_id)
        store[right.entry_id] = SimpleNamespace(
            controller=SimpleNamespace(capability_snapshot=lambda: dict(rsnap))
        )
        assert flow._octo_capability_snapshot(right) == rsnap
        assert flow._octo_capability_snapshot(left) == lsnap

    async def test_leggett_platt_explicit_variant_is_offline_safe(self, hass: HomeAssistant):
        """A legacy leggett_platt entry with an EXPLICIT gen2/mlrm variant resolves
        to leggett_gen2 / leggett_wilinke (both offline-capability-safe), so the
        pairing gate must NOT block it even though a Gen2 entry exposes a light
        entity. okin resolves to leggett_okin (OS-bonds, not offline-safe); auto
        can't be resolved without a live client. Regression for the gate keying
        off the umbrella bed_type instead of the resolved variant."""
        from custom_components.adjustable_bed.config_flow import (
            AdjustableBedConfigFlow,
        )

        flow = AdjustableBedConfigFlow()
        flow.hass = hass

        def _entry(address: str, variant: str) -> MockConfigEntry:
            return MockConfigEntry(
                domain=DOMAIN,
                data={
                    CONF_ADDRESS: address,
                    CONF_BED_TYPE: BED_TYPE_LEGGETT_PLATT,
                    CONF_PROTOCOL_VARIANT: variant,
                },
                unique_id=address,
                version=4,
            )

        # Resolver mirrors controller_factory's explicit-variant mapping.
        assert (
            flow._offline_safe_bed_type(_entry(LEFT_ADDR, LEGGETT_VARIANT_GEN2))
            == BED_TYPE_LEGGETT_GEN2
        )
        assert (
            flow._offline_safe_bed_type(_entry(LEFT_ADDR, LEGGETT_VARIANT_MLRM))
            == BED_TYPE_LEGGETT_WILINKE
        )
        assert (
            flow._offline_safe_bed_type(_entry(LEFT_ADDR, LEGGETT_VARIANT_OKIN))
            == BED_TYPE_LEGGETT_OKIN
        )
        assert flow._offline_safe_bed_type(_entry(LEFT_ADDR, "auto")) == BED_TYPE_LEGGETT_PLATT

        # Gate <-> minting consistency: the resolved type the gate calls safe is a
        # concrete type async_prime_offline_controller can actually mint (it is in
        # the offline-safe set). The umbrella type is NOT, which is why the pair
        # descriptor must store the resolved type (asserted in the conversion test).
        assert BED_TYPE_LEGGETT_GEN2 in OFFLINE_CAPABILITY_SAFE_BED_TYPES
        assert BED_TYPE_LEGGETT_WILINKE in OFFLINE_CAPABILITY_SAFE_BED_TYPES
        assert BED_TYPE_LEGGETT_PLATT not in OFFLINE_CAPABILITY_SAFE_BED_TYPES

        # Two leggett_platt entries with DIFFERENT explicit variants resolve to
        # different concrete protocols, so the pairing mismatch check (now over
        # resolved types) rejects them even though their raw umbrella type matches.
        assert flow._offline_safe_bed_type(
            _entry(LEFT_ADDR, LEGGETT_VARIANT_GEN2)
        ) != flow._offline_safe_bed_type(_entry(RIGHT_ADDR, LEGGETT_VARIANT_MLRM))

        ent_reg = er.async_get(hass)

        # Gen2 entry with a light entity is STILL offline-safe — the resolved type
        # short-circuits the registry scan that previously blocked it.
        gen2 = _entry(LEFT_ADDR, LEGGETT_VARIANT_GEN2)
        gen2.add_to_hass(hass)
        ent_reg.async_get_or_create("light", DOMAIN, f"{LEFT_ADDR}_rgb_light", config_entry=gen2)
        assert flow._has_unsafe_offline_platforms(gen2) is False

        # okin resolves to a non-offline-safe type, so the same light entity keeps
        # it blocked.
        okin = _entry(RIGHT_ADDR, LEGGETT_VARIANT_OKIN)
        okin.add_to_hass(hass)
        ent_reg.async_get_or_create("light", DOMAIN, f"{RIGHT_ADDR}_rgb_light", config_entry=okin)
        assert flow._has_unsafe_offline_platforms(okin) is True

        # The pair descriptor is built through the SAME resolver, so a stored
        # child carries the concrete (mintable) type — not the umbrella — and
        # options are merged in. Without this the gate would pass but
        # async_prime_offline_controller would refuse to mint the side.
        gen2_with_opts = MockConfigEntry(
            domain=DOMAIN,
            data={
                CONF_ADDRESS: LEFT_ADDR,
                CONF_BED_TYPE: BED_TYPE_LEGGETT_PLATT,
                CONF_PROTOCOL_VARIANT: LEGGETT_VARIANT_GEN2,
            },
            options={CONF_PREFERRED_ADAPTER: "hci1"},
            unique_id="leggett-resolve-test",
            version=4,
        )
        resolved = flow._resolved_pair_side_data(gen2_with_opts)
        assert resolved[CONF_BED_TYPE] == BED_TYPE_LEGGETT_GEN2
        assert resolved[CONF_PREFERRED_ADAPTER] == "hci1"  # option merged in

    def test_resolve_explicit_bed_type_pure(self):
        """The shared resolver: explicit Leggett variants -> concrete types,
        everything else (other beds, auto/unset) passes through unchanged."""
        from custom_components.adjustable_bed.const import resolve_explicit_bed_type

        assert (
            resolve_explicit_bed_type(BED_TYPE_LEGGETT_PLATT, LEGGETT_VARIANT_GEN2)
            == BED_TYPE_LEGGETT_GEN2
        )
        assert (
            resolve_explicit_bed_type(BED_TYPE_LEGGETT_PLATT, LEGGETT_VARIANT_MLRM)
            == BED_TYPE_LEGGETT_WILINKE
        )
        assert (
            resolve_explicit_bed_type(BED_TYPE_LEGGETT_PLATT, LEGGETT_VARIANT_OKIN)
            == BED_TYPE_LEGGETT_OKIN
        )
        # auto / unset can't be resolved offline -> umbrella unchanged.
        assert resolve_explicit_bed_type(BED_TYPE_LEGGETT_PLATT, "auto") == BED_TYPE_LEGGETT_PLATT
        assert resolve_explicit_bed_type(BED_TYPE_LEGGETT_PLATT, None) == BED_TYPE_LEGGETT_PLATT
        # Non-Leggett beds are never rewritten.
        assert resolve_explicit_bed_type(BED_TYPE_OCTO, "gen2") == BED_TYPE_OCTO
        assert resolve_explicit_bed_type(BED_TYPE_LINAK, None) == BED_TYPE_LINAK

    @staticmethod
    def _pairable_octo_ids(hass: HomeAssistant) -> list[str]:
        return [
            entry.entry_id
            for entry in hass.config_entries.async_entries(DOMAIN)
            if entry.data.get(CONF_BED_TYPE) == BED_TYPE_OCTO
        ]

    async def test_same_entry_twice_is_rejected(
        self,
        hass: HomeAssistant,
        mock_coordinator_connected,
        enable_custom_integrations,
    ):
        from custom_components.adjustable_bed.config_flow import (
            AdjustableBedConfigFlow,
        )

        left = self._single(hass, LEFT_ADDR, "Seng")
        self._single(hass, RIGHT_ADDR, "Bed 4587")

        flow = AdjustableBedConfigFlow()
        flow.hass = hass
        result = await flow.async_step_pair_beds(
            {"left_entry": left.entry_id, "right_entry": left.entry_id},
        )
        assert result["type"] == FlowResultType.FORM
        assert result["errors"][CONF_PAIR_SELECTION] == "same_device"

    async def test_conversion_rehomes_rows_preserving_history(
        self,
        hass: HomeAssistant,
        mock_coordinator_connected,
        enable_custom_integrations,
    ):
        """Converting two singles re-homes each side's existing entity AND device
        registry rows onto the pair IN PLACE (Phase 2.6): entity_id, the registry
        row identity, user customizations, and the device all survive — proving
        the conversion is additive and per-side history follows."""
        ent_reg = er.async_get(hass)
        dev_reg = dr.async_get(hass)

        left = await self._setup_single(hass, LEFT_ADDR, "Seng")
        right = await self._setup_single(hass, RIGHT_ADDR, "Bed 4587")
        left_original_data = dict(left.data)
        hass.config_entries.async_update_entry(left, options={"back_max_angle": 55.0})
        await hass.async_block_till_done()

        # Snapshot one real per-side entity's identity and customize it, so we can
        # prove the SAME row survives (not a freshly recreated one).
        cover_uid = f"{LEFT_ADDR}_back"
        cover_id = ent_reg.async_get_entity_id("cover", DOMAIN, cover_uid)
        assert cover_id is not None
        ent_reg.async_update_entity(cover_id, name="Kris head angle")
        before_row = ent_reg.async_get(cover_id)
        assert before_row is not None
        before_row_id = before_row.id
        assert before_row.config_entry_id == left.entry_id

        # Customize the left side's device too.
        left_device = _device_for_entry_and_identifier(dev_reg, left.entry_id, (DOMAIN, LEFT_ADDR))
        assert left_device is not None
        left_device_id = left_device.id
        dev_reg.async_update_device(left_device_id, name_by_user="Left headboard")

        # Convert.
        result = await self._reach_pair_step(hass)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_PAIR_SELECTION: encode_pair_selection(left.entry_id, right.entry_id),
                CONF_NAME: "Master Bed",
            },
        )
        await hass.async_block_till_done()
        assert result["type"] == FlowResultType.CREATE_ENTRY

        # Originals absorbed; exactly one paired entry, now LOADED.
        remaining = hass.config_entries.async_entries(DOMAIN)
        ids = {e.entry_id for e in remaining}
        assert left.entry_id not in ids
        assert right.entry_id not in ids
        paired = [e for e in remaining if is_paired(e.data)]
        assert len(paired) == 1
        pair = paired[0]
        assert pair.state == ConfigEntryState.LOADED

        # The cover row survived IN PLACE: same entity_id, same registry-row id
        # (not recreated), now owned by the pair, customization intact.
        after_id = ent_reg.async_get_entity_id("cover", DOMAIN, cover_uid)
        assert after_id == cover_id  # entity_id unchanged -> recorder history follows
        after_row = ent_reg.async_get(after_id)
        assert after_row is not None
        assert after_row.id == before_row_id  # same row object, not recreated
        assert after_row.config_entry_id == pair.entry_id  # re-homed onto the pair
        assert after_row.name == "Kris head angle"  # user customization preserved

        # No orphaned/duplicate row for that unique_id.
        rows = [e for e in ent_reg.entities.values() if e.unique_id == cover_uid]
        assert len(rows) == 1

        # The device survived in place (same id), keeps its user name, and now
        # nests under the synthetic parent.
        parent = _device_for_entry_and_identifier(
            dev_reg,
            pair.entry_id,
            (DOMAIN, pair.data[CONF_PAIR_ID]),
        )
        assert parent is not None
        left_after = _device_for_entry_and_identifier(dev_reg, pair.entry_id, (DOMAIN, LEFT_ADDR))
        assert left_after is not None
        assert left_after.id == left_device_id  # same device, not recreated
        assert left_after.config_entry_id == pair.entry_id
        assert left_after.name_by_user == "Left headboard"
        assert left_after.via_device_id == parent.id

        # Reverse the conversion. The original entry ids and side registry
        # ownership return, while the exact same entity/device rows and user
        # customizations survive in place.
        restored = await async_unpair_entry(hass, pair)
        await hass.async_block_till_done()
        assert {entry.entry_id for entry in restored} == {
            left.entry_id,
            right.entry_id,
        }
        assert hass.config_entries.async_get_entry(pair.entry_id) is None
        left_restored = hass.config_entries.async_get_entry(left.entry_id)
        right_restored = hass.config_entries.async_get_entry(right.entry_id)
        assert left_restored is not None
        assert right_restored is not None
        assert left_restored.title == "Seng"
        assert right_restored.title == "Bed 4587"
        assert left_restored.data == left_original_data
        assert left_restored.options == {"back_max_angle": 55.0}

        final_row = ent_reg.async_get(cover_id)
        assert final_row is not None
        assert final_row.id == before_row_id
        assert final_row.config_entry_id == left.entry_id
        assert final_row.name == "Kris head angle"
        assert len([e for e in ent_reg.entities.values() if e.unique_id == cover_uid]) == 1

        final_device = _device_for_entry_and_identifier(dev_reg, left.entry_id, (DOMAIN, LEFT_ADDR))
        assert final_device is not None
        assert final_device.id == left_device_id
        assert final_device.config_entry_id == left.entry_id
        assert final_device.name_by_user == "Left headboard"
        assert final_device.via_device_id is None

    async def test_conversion_connect_failure_preserves_originals(
        self,
        hass: HomeAssistant,
        mock_coordinator_connected,
        enable_custom_integrations,
    ):
        """If no paired child can connect, the originals are NOT absorbed: re-homing
        only happens after a successful connect, so the two single beds stay loaded
        and controllable (owning their rows) while the pair retries. The user is
        never left with no controllable bed."""
        from unittest.mock import patch

        left = await self._setup_single(hass, LEFT_ADDR, "Seng")
        right = await self._setup_single(hass, RIGHT_ADDR, "Bed 4587")

        ent_reg = er.async_get(hass)
        cover_uid = f"{LEFT_ADDR}_back"
        cover_id = ent_reg.async_get_entity_id("cover", DOMAIN, cover_uid)
        assert cover_id is not None
        assert ent_reg.async_get(cover_id).config_entry_id == left.entry_id

        result = await self._reach_pair_step(hass)
        # Make the pair's setup unable to find the beds, so no child connects.
        with patch(
            "custom_components.adjustable_bed.coordinator.bluetooth.async_ble_device_from_address",
            return_value=None,
        ):
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"],
                {CONF_PAIR_SELECTION: encode_pair_selection(left.entry_id, right.entry_id)},
            )
            await hass.async_block_till_done()

        assert result["type"] == FlowResultType.CREATE_ENTRY
        remaining = {e.entry_id: e for e in hass.config_entries.async_entries(DOMAIN)}
        paired = [e for e in remaining.values() if is_paired(e.data)]
        assert len(paired) == 1
        # The pair exists but is retrying (no side connected).
        assert paired[0].state == ConfigEntryState.SETUP_RETRY

        # The originals were NOT absorbed: they're still configured and LOADED, and
        # still own their entity rows — the user keeps two working beds.
        assert left.entry_id in remaining
        assert right.entry_id in remaining
        assert remaining[left.entry_id].state == ConfigEntryState.LOADED
        assert remaining[right.entry_id].state == ConfigEntryState.LOADED
        after = ent_reg.async_get(cover_id)
        assert after is not None
        assert after.config_entry_id == left.entry_id  # still on the original
        rows = [e for e in ent_reg.entities.values() if e.unique_id == cover_uid]
        assert len(rows) == 1

    async def test_conversion_rehome_failure_does_not_abort_setup(
        self,
        hass: HomeAssistant,
        mock_coordinator_connected,
        enable_custom_integrations,
    ):
        """A registry error while absorbing ONE side must not propagate (re-homing
        runs after the live coordinator is in hass.data, so a raised exception would
        fail paired setup and leak its open BLE links) nor abort the OTHER side. The
        pair still loads, the failing side's rows are rolled back so it survives as a
        consistent single for the next reload, and the healthy side is absorbed."""
        from unittest.mock import patch

        left = await self._setup_single(hass, LEFT_ADDR, "Seng")
        right = await self._setup_single(hass, RIGHT_ADDR, "Bed 4587")
        failing_id = left.entry_id  # only the left side's removal blows up

        ent_reg = er.async_get(hass)
        left_cover_id = ent_reg.async_get_entity_id("cover", DOMAIN, f"{LEFT_ADDR}_back")
        assert left_cover_id is not None

        orig_remove = hass.config_entries.async_remove

        async def _failing_remove(entry_id):
            if entry_id == failing_id:
                raise RuntimeError("boom")
            return await orig_remove(entry_id)

        result = await self._reach_pair_step(hass)
        with patch.object(hass.config_entries, "async_remove", _failing_remove):
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"],
                {CONF_PAIR_SELECTION: encode_pair_selection(left.entry_id, right.entry_id)},
            )
            await hass.async_block_till_done()

        assert result["type"] == FlowResultType.CREATE_ENTRY
        remaining = {e.entry_id: e for e in hass.config_entries.async_entries(DOMAIN)}
        paired = [e for e in remaining.values() if is_paired(e.data)]
        assert len(paired) == 1
        pair = paired[0]
        # Setup completed despite the re-home failure (not SETUP_ERROR), and the
        # coordinator is live in hass.data — not leaked by a propagating exception.
        assert pair.state == ConfigEntryState.LOADED
        assert pair.entry_id in hass.data[DOMAIN]
        # Per-side isolation: the failing side survives for a retry on the next
        # reload, while the healthy side is absorbed normally.
        assert left.entry_id in remaining
        assert right.entry_id not in remaining
        # Rollback: the failing side's rows are restored to the still-loaded single
        # (not left pointing at the pair), so it stays a consistent single.
        rolled_back = ent_reg.async_get(left_cover_id)
        assert rolled_back is not None
        assert rolled_back.config_entry_id == left.entry_id

    async def test_conversion_surfaces_unclean_unload(
        self,
        hass: HomeAssistant,
        mock_coordinator_connected,
        enable_custom_integrations,
        caplog,
    ):
        """If an absorbed single's platforms don't unload cleanly, async_remove
        still removes the entry and returns require_restart (it does not raise) —
        the rows are already re-homed so the side IS absorbed, but the unclean
        unload is surfaced (a warning), not silently swallowed."""
        import logging
        from unittest.mock import patch

        left = await self._setup_single(hass, LEFT_ADDR, "Seng")
        right = await self._setup_single(hass, RIGHT_ADDR, "Bed 4587")

        orig_remove = hass.config_entries.async_remove

        async def _unclean_remove(entry_id):
            await orig_remove(entry_id)  # actually removes the entry
            return {"require_restart": True}  # ...but reports an unclean unload

        result = await self._reach_pair_step(hass)
        with (
            patch.object(hass.config_entries, "async_remove", _unclean_remove),
            caplog.at_level(logging.WARNING),
        ):
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"],
                {CONF_PAIR_SELECTION: encode_pair_selection(left.entry_id, right.entry_id)},
            )
            await hass.async_block_till_done()

        assert result["type"] == FlowResultType.CREATE_ENTRY
        ids = {e.entry_id for e in hass.config_entries.async_entries(DOMAIN)}
        # Both originals absorbed (removed) despite the unclean-unload signal...
        assert left.entry_id not in ids
        assert right.entry_id not in ids
        # ...and the unclean unload was surfaced, not silently ignored.
        assert "did not unload cleanly" in caplog.text

    async def test_release_absorbed_singles_disconnects_originals(self, hass: HomeAssistant):
        """A single-connection (Octo) pair must release its absorbed originals' BLE
        links BEFORE it connects — Octo keeps its one link alive via PIN keepalive,
        so a still-loaded original would block the paired child (same MAC) and the
        pair would hang in setup retry. The original entry stays loaded (only its
        link is dropped)."""
        from unittest.mock import AsyncMock

        from custom_components.adjustable_bed.coordinator import (
            AdjustableBedCoordinator,
        )
        from custom_components.adjustable_bed.pairing import build_pair_entry_data

        single = MockConfigEntry(
            domain=DOMAIN,
            data={CONF_ADDRESS: LEFT_ADDR, CONF_BED_TYPE: BED_TYPE_OCTO},
            unique_id=LEFT_ADDR,
            version=4,
        )
        single.add_to_hass(hass)
        coord = AdjustableBedCoordinator(hass, single)
        coord.async_disconnect = AsyncMock()  # type: ignore[method-assign]
        hass.data.setdefault(DOMAIN, {})[single.entry_id] = coord

        pair_data = build_pair_entry_data(
            {CONF_ADDRESS: LEFT_ADDR, CONF_BED_TYPE: BED_TYPE_OCTO},
            {CONF_ADDRESS: RIGHT_ADDR, CONF_BED_TYPE: BED_TYPE_OCTO},
            name="Octo pair",
            left_origin=(single.entry_id, single.unique_id),
        )
        pair = MockConfigEntry(
            domain=DOMAIN,
            data=pair_data,
            unique_id=pair_data[CONF_PAIR_ID],
            version=4,
        )
        pair.add_to_hass(hass)

        await _async_release_absorbed_singles(hass, pair)

        # The absorbed original's link was dropped...
        coord.async_disconnect.assert_awaited_once()
        # ...but the original entry is still present (released, not removed).
        assert single.entry_id in {e.entry_id for e in hass.config_entries.async_entries(DOMAIN)}

    async def test_conversion_retries_contended_side_after_absorb(
        self,
        hass: HomeAssistant,
        mock_coordinator_connected,
        enable_custom_integrations,
    ):
        """A concurrent child that fails its initial connect only because its
        original single still held the single-link BLE is retried after the absorb
        frees the link — so a non-offline-mintable side isn't left empty until a
        reload."""
        from unittest.mock import MagicMock, patch

        from custom_components.adjustable_bed.coordinator import (
            AdjustableBedCoordinator,
        )

        left = await self._setup_single(hass, LEFT_ADDR, "Seng")
        right = await self._setup_single(hass, RIGHT_ADDR, "Bed 4587")

        calls: dict[str, int] = {}

        async def fake_connect(self):
            calls[self.address] = calls.get(self.address, 0) + 1
            # The left child's FIRST connect fails (its original single still
            # holds the link); every other connect — including the post-absorb
            # retry — succeeds and marks the link live.
            if self.address == LEFT_ADDR and calls[self.address] == 1:
                return False
            client = MagicMock()
            client.is_connected = True
            self._client = client
            return True

        result = await self._reach_pair_step(hass)
        with patch.object(AdjustableBedCoordinator, "async_connect", fake_connect):
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"],
                {CONF_PAIR_SELECTION: encode_pair_selection(left.entry_id, right.entry_id)},
            )
            await hass.async_block_till_done()

        assert result["type"] == FlowResultType.CREATE_ENTRY
        # The left child was retried after the absorb (initial fail + one retry);
        # the already-connected right child was not retried.
        assert calls.get(LEFT_ADDR, 0) == 2
        assert calls.get(RIGHT_ADDR, 0) == 1

    async def test_conversion_retry_is_bounded_by_timeout(
        self,
        hass: HomeAssistant,
        mock_coordinator_connected,
        enable_custom_integrations,
    ):
        """The post-absorb retry is bounded by SETUP_TIMEOUT like the initial
        connect, so a hanging reconnect can't block setup — it falls back to
        offline-prime and the pair still loads."""
        import asyncio
        from unittest.mock import MagicMock, patch

        from custom_components.adjustable_bed.coordinator import (
            AdjustableBedCoordinator,
        )

        left = await self._setup_single(hass, LEFT_ADDR, "Seng")
        right = await self._setup_single(hass, RIGHT_ADDR, "Bed 4587")

        calls: dict[str, int] = {}
        retry_cancelled = False

        async def fake_connect(self):
            nonlocal retry_cancelled
            calls[self.address] = calls.get(self.address, 0) + 1
            if self.address == LEFT_ADDR:
                if calls[self.address] == 1:
                    return False  # initial connect fails (contention)
                try:
                    await asyncio.sleep(1)  # retry hangs — must be cut off by timeout
                except asyncio.CancelledError:
                    retry_cancelled = True  # the SETUP_TIMEOUT guard fired
                    raise
                return True
            client = MagicMock()
            client.is_connected = True
            self._client = client
            return True

        result = await self._reach_pair_step(hass)
        with (
            patch.object(AdjustableBedCoordinator, "async_connect", fake_connect),
            patch("custom_components.adjustable_bed.SETUP_TIMEOUT", 0.2),
        ):
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"],
                {CONF_PAIR_SELECTION: encode_pair_selection(left.entry_id, right.entry_id)},
            )
            await hass.async_block_till_done()

        assert result["type"] == FlowResultType.CREATE_ENTRY
        # The hanging retry was attempted, then deterministically cancelled by the
        # SETUP_TIMEOUT guard (not allowed to return after the long sleep), without
        # blocking setup.
        assert calls.get(LEFT_ADDR, 0) == 2
        assert retry_cancelled is True
        paired = [e for e in hass.config_entries.async_entries(DOMAIN) if is_paired(e.data)]
        assert len(paired) == 1
        assert paired[0].state == ConfigEntryState.LOADED


class TestSideServiceRouting:
    """The left/right/both service field routes correctly."""

    async def test_side_left_rejected_on_single_bed(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
        enable_custom_integrations,
    ):
        """A single bed rejects a left/right side with a clean error."""
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

        devices = dr.async_entries_for_config_entry(dr.async_get(hass), mock_config_entry.entry_id)
        assert devices
        with pytest.raises(ServiceValidationError):
            await hass.services.async_call(
                DOMAIN,
                "stop_all",
                {"device_id": [devices[0].id], "side": SIDE_LEFT},
                blocking=True,
            )

    async def test_stop_all_sides_on_paired_bed(
        self,
        hass: HomeAssistant,
        mock_coordinator_connected,
        enable_custom_integrations,
    ):
        """stop_all with both/left/right is accepted on a paired bed."""
        entry = _paired_entry(hass)
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        parent = _device_for_entry_and_identifier(
            dr.async_get(hass), entry.entry_id, (DOMAIN, PAIR_ID)
        )
        assert parent is not None
        for side in ("both", SIDE_LEFT, SIDE_RIGHT):
            await hass.services.async_call(
                DOMAIN,
                "stop_all",
                {"device_id": [parent.id], "side": side},
                blocking=True,
            )

    async def test_preset_preflight_uses_offline_controller_no_connect(self, hass: HomeAssistant):
        """goto_preset on a paired Octo validates EVERY side from its offline
        capability snapshot WITHOUT connecting — connecting each side to preflight
        would momentarily hold two BLE links, which the single-connection profile
        must never do (#390)."""
        from unittest.mock import AsyncMock

        from custom_components.adjustable_bed import (
            _async_ensure_paired_device_registry,
            async_register_services,
        )
        from custom_components.adjustable_bed.paired_coordinator import (
            PairedBedCoordinator,
        )

        snap = {
            "has_pin": False,
            "pin_locked": False,
            "has_lights": True,
            "has_rgbwi": False,
            "rgbwi_value_type": None,
            "memory_count": 4,
            "discovered_motor_count": 2,
            "has_synchro": False,
        }
        data = _paired_entry_data()
        data[CONF_BED_TYPE] = BED_TYPE_OCTO
        for child in data[CONF_PAIR_CHILDREN]:
            child[CONF_BED_TYPE] = BED_TYPE_OCTO
            child["capabilities"] = {"octo": snap}
        entry = MockConfigEntry(
            domain=DOMAIN,
            data=data,
            unique_id="pair_octo_svc",
            entry_id="pair_octo_svc",
            version=4,
        )
        entry.add_to_hass(hass)
        children = _build_paired_children(hass, entry)
        for child in children.values():
            await child.async_prime_offline_controller()
            assert child.capability_controller is not None
            # Spy on the preflight's connect path (idle reconnect).
            child.async_ensure_connected = AsyncMock(return_value=True)  # type: ignore[method-assign]
        coordinator = PairedBedCoordinator(hass, entry, children)
        # Skip the real fan-out (Phase 2 execution) — we're asserting on preflight.
        coordinator.async_execute_controller_command = AsyncMock()  # type: ignore[method-assign]
        hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
        _async_ensure_paired_device_registry(hass, entry, coordinator)
        await async_register_services(hass)

        parent = _device_for_entry_and_identifier(
            dr.async_get(hass), entry.entry_id, (DOMAIN, PAIR_ID)
        )
        assert parent is not None
        await hass.services.async_call(
            DOMAIN,
            "goto_preset",
            {"device_id": [parent.id], "side": "both", "preset": 1},
            blocking=True,
        )

        # Preflight validated from the offline snapshot — neither side was connected.
        for child in children.values():
            child.async_ensure_connected.assert_not_awaited()
        # ...and the command still fanned out for execution.
        coordinator.async_execute_controller_command.assert_awaited()

        # save_preset shares the same no-connect preflight (it validates
        # supports_memory_programming). This snapshot reports four slots, so the
        # validation passes and the command fans out - still read entirely from
        # the offline controller, without connecting either side.
        for child in children.values():
            child.async_ensure_connected.reset_mock()
        coordinator.async_execute_controller_command.reset_mock()
        await hass.services.async_call(
            DOMAIN,
            "save_preset",
            {"device_id": [parent.id], "side": "both", "preset": 1},
            blocking=True,
        )
        for child in children.values():
            child.async_ensure_connected.assert_not_awaited()
        coordinator.async_execute_controller_command.assert_awaited()

    async def test_preset_preflight_rejects_from_snapshot_without_connecting(
        self, hass: HomeAssistant
    ):
        """A side whose snapshot reports no memory is rejected from that snapshot
        alone: the preflight must never connect a side just to find out (#390)."""
        from unittest.mock import AsyncMock

        from custom_components.adjustable_bed import (
            _async_ensure_paired_device_registry,
            async_register_services,
        )
        from custom_components.adjustable_bed.paired_coordinator import (
            PairedBedCoordinator,
        )

        snap = {
            "has_pin": False,
            "pin_locked": False,
            "has_lights": True,
            "has_rgbwi": False,
            "rgbwi_value_type": None,
            "memory_count": 0,  # this receiver has no memory slots at all
            "discovered_motor_count": 2,
            "has_synchro": False,
        }
        data = _paired_entry_data()
        data[CONF_BED_TYPE] = BED_TYPE_OCTO
        for child in data[CONF_PAIR_CHILDREN]:
            child[CONF_BED_TYPE] = BED_TYPE_OCTO
            child["capabilities"] = {"octo": snap}
        entry = MockConfigEntry(
            domain=DOMAIN,
            data=data,
            unique_id="pair_octo_nomem",
            entry_id="pair_octo_nomem",
            version=4,
        )
        entry.add_to_hass(hass)
        children = _build_paired_children(hass, entry)
        for child in children.values():
            await child.async_prime_offline_controller()
            child.async_ensure_connected = AsyncMock(return_value=True)  # type: ignore[method-assign]
        coordinator = PairedBedCoordinator(hass, entry, children)
        coordinator.async_execute_controller_command = AsyncMock()  # type: ignore[method-assign]
        hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
        _async_ensure_paired_device_registry(hass, entry, coordinator)
        await async_register_services(hass)

        parent = _device_for_entry_and_identifier(
            dr.async_get(hass), entry.entry_id, (DOMAIN, PAIR_ID)
        )
        assert parent is not None
        with pytest.raises(ServiceValidationError):
            await hass.services.async_call(
                DOMAIN,
                "save_preset",
                {"device_id": [parent.id], "side": "both", "preset": 1},
                blocking=True,
            )
        for child in children.values():
            child.async_ensure_connected.assert_not_awaited()
        coordinator.async_execute_controller_command.assert_not_awaited()

    async def test_per_motor_services_accept_paired_parent(
        self,
        hass: HomeAssistant,
        mock_coordinator_connected,
        enable_custom_integrations,
    ):
        """Per-motor services accept the parent and default to both sides."""
        entry = _paired_entry(hass)
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        parent = _device_for_entry_and_identifier(
            dr.async_get(hass), entry.entry_id, (DOMAIN, PAIR_ID)
        )
        assert parent is not None

        # This fixture disables angle sensing, so set_position still rejects the
        # request for its normal capability reason, not because the target is a
        # paired parent.
        with pytest.raises(ServiceValidationError, match="Angle sensing is disabled"):
            await hass.services.async_call(
                DOMAIN,
                "set_position",
                {"device_id": [parent.id], "motor": "back", "position": 50},
                blocking=True,
            )
        await hass.services.async_call(
            DOMAIN,
            "timed_move",
            {
                "device_id": [parent.id],
                "motor": "back",
                "direction": "up",
                "duration_ms": 1000,
            },
            blocking=True,
        )

    async def test_set_position_parent_preflights_and_targets_both(
        self,
        hass: HomeAssistant,
        mock_coordinator_connected,
        enable_custom_integrations,
    ):
        """set_position validates both sides before paired fan-out."""
        from unittest.mock import AsyncMock

        data = _paired_entry_data()
        for child in data[CONF_PAIR_CHILDREN]:
            child[CONF_DISABLE_ANGLE_SENSING] = False
        entry = MockConfigEntry(
            domain=DOMAIN,
            title="Master Bed",
            data=data,
            unique_id=PAIR_ID,
            version=4,
        )
        entry.add_to_hass(hass)
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        coordinator = hass.data[DOMAIN][entry.entry_id]
        from custom_components.adjustable_bed.beds.linak_protocol import (
            LinakCapabilitySnapshot,
            LinakProfile,
        )

        for child in coordinator.children.values():
            child.controller._capabilities = LinakCapabilitySnapshot.from_mapping(
                LINAK_ADVANCED_SNAPSHOT,
                profile=LinakProfile.BED_CONTROL,
            )
        coordinator.async_run_child_operation = AsyncMock()
        parent = _device_for_entry_and_identifier(
            dr.async_get(hass), entry.entry_id, (DOMAIN, PAIR_ID)
        )
        assert parent is not None

        await hass.services.async_call(
            DOMAIN,
            "set_position",
            {"device_id": [parent.id], "motor": "back", "position": 20},
            blocking=True,
        )
        coordinator.async_run_child_operation.assert_awaited_once()
        assert coordinator.async_run_child_operation.await_args.kwargs["side"] == SIDE_BOTH

    async def test_timed_move_both_aborts_if_right_preflight_fails(
        self,
        hass: HomeAssistant,
        mock_coordinator_connected,
        enable_custom_integrations,
    ):
        """An invalid right side prevents a valid left side from moving."""
        from types import SimpleNamespace
        from unittest.mock import AsyncMock

        entry = _paired_entry(hass)
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        coordinator = hass.data[DOMAIN][entry.entry_id]
        coordinator.children[SIDE_RIGHT]._controller = SimpleNamespace(motor_control_specs=())
        coordinator.async_run_child_operation = AsyncMock()
        parent = _device_for_entry_and_identifier(
            dr.async_get(hass), entry.entry_id, (DOMAIN, PAIR_ID)
        )
        assert parent is not None

        with pytest.raises(ServiceValidationError, match="Motor 'back' is not valid"):
            await hass.services.async_call(
                DOMAIN,
                "timed_move",
                {
                    "device_id": [parent.id],
                    "side": SIDE_BOTH,
                    "motor": "back",
                    "direction": "up",
                    "duration_ms": 1000,
                },
                blocking=True,
            )
        coordinator.async_run_child_operation.assert_not_awaited()

    async def test_combined_motor_buttons_use_side_spec_functions(self):
        """The combined both-sides motor buttons carry each side's OWN
        MotorControlSpec functions, so a 3/4-motor Octo's head/feet buttons drive
        the mapped extra motors (_move_motor3/4), not the generic move_head/feet
        (motors 1/2)."""
        from types import SimpleNamespace
        from unittest.mock import MagicMock

        from custom_components.adjustable_bed.beds.base import MotorControlSpec
        from custom_components.adjustable_bed.button import (
            PairedBedCombinedMotorButton,
            _combined_motor_buttons_for,
        )

        motor3_up = MagicMock(name="motor3_up")
        head_spec = MotorControlSpec(
            key="head",
            translation_key="head",
            open_fn=motor3_up,
            close_fn=MagicMock(),
            stop_fn=MagicMock(),
            position_key="back",
        )
        back_spec = MotorControlSpec(
            key="back",
            translation_key="back",
            open_fn=MagicMock(),
            close_fn=MagicMock(),
            stop_fn=MagicMock(),
        )
        back_legs_spec = MotorControlSpec(
            key="back_legs",
            translation_key="back_legs",
            open_fn=MagicMock(),
            close_fn=MagicMock(),
            stop_fn=MagicMock(),
        )

        # The button carries the spec's open_fn (the mapped per-side motor) and
        # keeps the same unique_id as before (no entity churn).
        coord = MagicMock(pair_id="pair_x", device_info={})
        btn = PairedBedCombinedMotorButton(coord, head_spec, "up")
        assert btn._move_fn is motor3_up
        assert btn._resource == "motor:back"
        assert btn._attr_unique_id == "pair_x_head_up_both"

        # The builder intersects each side's specs and builds from THEM, not from
        # generic COVER_DESCRIPTIONS.
        left_controller = SimpleNamespace(
            supports_motor_control=True,
            has_discrete_motor_control=False,
            motor_control_specs=[head_spec, back_spec, back_legs_spec],
        )
        right_controller = SimpleNamespace(
            supports_motor_control=True,
            has_discrete_motor_control=False,
            motor_control_specs=[head_spec, back_legs_spec],
        )
        left = SimpleNamespace(capability_controller=left_controller)
        right = SimpleNamespace(capability_controller=right_controller)
        buttons = _combined_motor_buttons_for(coord, [left, right])
        head_up = next(b for b in buttons if b._attr_unique_id == "pair_x_head_up_both")
        assert head_up._move_fn is motor3_up
        back_legs_up = next(b for b in buttons if b._attr_unique_id == "pair_x_back_legs_up_both")
        assert back_legs_up._attr_translation_key == "back_legs_up"
        assert not any(button._attr_unique_id == "pair_x_back_up_both" for button in buttons)

        # A known left side is not enough to advertise a both-sides action. The
        # other side could have a different capability surface, so suppress all
        # combined motor controls until both sources are known.
        unknown = SimpleNamespace(capability_controller=None)
        assert _combined_motor_buttons_for(coord, [left, unknown]) == []


class TestCombinedPositionSliders:
    """The paired parent device gets 'both sides' position sliders."""

    @staticmethod
    def _side(specs, *, capability=True, disable_angle_sensing=False, position=None):
        from types import SimpleNamespace
        from unittest.mock import MagicMock

        controller = (
            SimpleNamespace(
                position_number_specs=specs,
                supports_direct_position_control=False,
            )
            if capability
            else None
        )
        return SimpleNamespace(
            capability_controller=controller,
            disable_angle_sensing=disable_angle_sensing,
            entry=SimpleNamespace(data={CONF_BED_TYPE: BED_TYPE_LINAK}),
            position_data={} if position is None else {"back": position},
            register_position_callback=MagicMock(return_value=MagicMock()),
        )

    def test_builder_intersects_side_specs_and_needs_both_capability_sources(self):
        from unittest.mock import MagicMock

        from custom_components.adjustable_bed.beds.base import build_position_number_spec
        from custom_components.adjustable_bed.number import (
            _combined_position_entities_for,
        )

        back = build_position_number_spec("back", max_value=68, unit="°")
        right_back = build_position_number_spec("back", max_value=55, unit="°")
        legs = build_position_number_spec("legs", max_value=45, unit="°")
        head = build_position_number_spec("head", max_value=68, unit="°")
        coord = MagicMock(spec=PairedBedCoordinator)
        coord.entity_unique_id.side_effect = lambda key: f"pair_x_{key}"
        coord.device_info = {}

        left = self._side((back, legs, head))
        right = self._side((right_back, legs))
        entities = _combined_position_entities_for(coord, [left, right])
        assert [entity.unique_id for entity in entities] == [
            "pair_x_back_position_both",
            "pair_x_legs_position_both",
        ]
        # Separate-address pairs reuse the plain translation key; the parent
        # device name keeps the entity distinct from the per-side sliders.
        assert entities[0].translation_key == "back_position"
        assert entities[0].native_max_value == 55

        incompatible_back = build_position_number_spec(
            "back", max_value=100, unit="%"
        )
        assert _combined_position_entities_for(
            coord, [left, self._side((incompatible_back,))]
        ) == []

        # An unknown side could have a different layout: build nothing yet.
        assert (
            _combined_position_entities_for(coord, [left, self._side((), capability=False)]) == []
        )
        # A side with angle sensing disabled cannot seek, so nothing is common.
        assert (
            _combined_position_entities_for(
                coord, [left, self._side((back,), disable_angle_sensing=True)]
            )
            == []
        )

    async def test_slider_reports_mean_and_seeks_both_sides(self):
        from types import SimpleNamespace
        from unittest.mock import AsyncMock, MagicMock

        from custom_components.adjustable_bed.beds.base import build_position_number_spec
        from custom_components.adjustable_bed.number import (
            PairedBedCombinedPositionNumber,
            _build_position_description,
        )

        back = build_position_number_spec("back", max_value=68, unit="°")
        left = self._side((back,), position=20.0)
        right = self._side((back,), position=30.0)
        coord = MagicMock(spec=PairedBedCoordinator)
        coord.entity_unique_id.side_effect = lambda key: f"pair_x_{key}"
        coord.device_info = {}
        coord.name = "Master Bed"
        coord.children = {SIDE_LEFT: left, SIDE_RIGHT: right}
        coord.async_seek_position = AsyncMock()

        entity = PairedBedCombinedPositionNumber(coord, _build_position_description(back))
        assert entity.native_value == 25.0
        right.position_data.clear()
        assert entity.native_value == 20.0
        left.position_data.clear()
        assert entity.native_value is None

        await entity.async_set_native_value(40)
        coord.async_seek_position.assert_awaited_once()
        kwargs = coord.async_seek_position.await_args.kwargs
        assert kwargs["side"] == SIDE_BOTH
        assert kwargs["position_key"] == "back"
        assert kwargs["target_angle"] == 40
        assert kwargs["move_up_fn"] is back.open_fn
        assert kwargs["move_stop_fn"] is back.stop_fn

        single = SingleAddressPairedCoordinator.__new__(SingleAddressPairedCoordinator)
        single._single_inner = SimpleNamespace(
            address="AA:BB:CC:DD:EE:50", device_info={}
        )
        single_entity = PairedBedCombinedPositionNumber(
            single, _build_position_description(back)
        )
        assert single_entity.translation_key == "back_position_both"
        assert single_entity.extra_state_attributes == {"bed_side": SIDE_BOTH}

    async def test_stale_cleanup_only_removes_combined_position_numbers(
        self, hass: HomeAssistant
    ):
        from unittest.mock import MagicMock

        from custom_components.adjustable_bed.beds.base import build_position_number_spec
        from custom_components.adjustable_bed.number import (
            _async_remove_stale_combined_number_entities,
            _combined_position_entities_for,
        )

        entry = MockConfigEntry(
            domain=DOMAIN,
            title="Master Bed",
            data=_paired_entry_data(),
            unique_id=PAIR_ID,
            entry_id="combined_position_cleanup",
            version=4,
        )
        entry.add_to_hass(hass)
        coordinator = MagicMock(spec=PairedBedCoordinator)
        coordinator.entry = entry
        coordinator.entity_unique_id.side_effect = lambda key: f"{PAIR_ID}_{key}"
        coordinator.device_info = {}

        back = build_position_number_spec("back", max_value=68, unit="°")
        children = [self._side((back,)), self._side((back,))]
        entities = _combined_position_entities_for(coordinator, children)

        registry = er.async_get(hass)
        stale_position = registry.async_get_or_create(
            "number",
            DOMAIN,
            f"{PAIR_ID}_lumbar_position_both",
            config_entry=entry,
            translation_key="lumbar_position",
        )
        unrelated = registry.async_get_or_create(
            "number",
            DOMAIN,
            f"{PAIR_ID}_sleep_number_setting_both",
            config_entry=entry,
            translation_key="sleep_number_setting_both",
        )
        child_position = registry.async_get_or_create(
            "number",
            DOMAIN,
            f"{LEFT_ADDR}_lumbar_position",
            config_entry=entry,
            translation_key="lumbar_position",
        )

        _async_remove_stale_combined_number_entities(
            hass, coordinator, children, entities
        )

        assert registry.async_get(stale_position.entity_id) is None
        assert registry.async_get(unrelated.entity_id) is not None
        assert registry.async_get(child_position.entity_id) is not None

    async def test_parent_device_gets_position_sliders_when_sides_report_angles(
        self,
        hass: HomeAssistant,
        mock_coordinator_connected,
        enable_custom_integrations,
    ):
        from unittest.mock import PropertyMock

        from custom_components.adjustable_bed.beds.base import build_position_number_spec
        from custom_components.adjustable_bed.beds.linak import LinakController

        data = _paired_entry_data()
        for child in data[CONF_PAIR_CHILDREN]:
            child[CONF_DISABLE_ANGLE_SENSING] = False
        entry = MockConfigEntry(
            domain=DOMAIN, title="Master Bed", data=data, unique_id=PAIR_ID, version=4
        )
        entry.add_to_hass(hass)
        # The mocked link discovers no Linak actuator mask, so declare the axes a
        # real advanced frame would report.
        specs = (
            build_position_number_spec("back", max_value=68, unit="°"),
            build_position_number_spec("legs", max_value=45, unit="°"),
        )
        with patch.object(
            LinakController, "position_number_specs", new_callable=PropertyMock, return_value=specs
        ):
            await hass.config_entries.async_setup(entry.entry_id)
            await hass.async_block_till_done()

        registry = er.async_get(hass)
        parent = _device_for_entry_and_identifier(
            dr.async_get(hass), entry.entry_id, (DOMAIN, PAIR_ID)
        )
        assert parent is not None
        both_numbers = {
            row.unique_id: row
            for row in er.async_entries_for_config_entry(registry, entry.entry_id)
            if row.domain == "number" and row.unique_id.endswith("_both")
        }
        assert set(both_numbers) == {
            f"{PAIR_ID}_back_position_both",
            f"{PAIR_ID}_legs_position_both",
        }
        assert all(row.device_id == parent.id for row in both_numbers.values())
        state = hass.states.get(both_numbers[f"{PAIR_ID}_back_position_both"].entity_id)
        assert state is not None
        assert state.name == "Master Bed Back Position"
        # The per-side sliders still live on the children.
        assert registry.async_get_entity_id("number", DOMAIN, f"{LEFT_ADDR}_back_position")

    async def test_no_combined_sliders_without_angle_sensing(
        self,
        hass: HomeAssistant,
        mock_coordinator_connected,
        enable_custom_integrations,
    ):
        entry = _paired_entry(hass)
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        rows = er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
        assert not any(row.domain == "number" and row.unique_id.endswith("_both") for row in rows)


class TestOfflineSideEntities:
    """Phase 2.1: a side offline at setup still gets its per-side entities,
    built from a client-free 'capability' controller minted from config, so a
    reconnect needs no reload."""

    async def test_offline_side_builds_covers_from_capability_controller(self, hass: HomeAssistant):
        from custom_components.adjustable_bed.beds.linak import LinakController
        from custom_components.adjustable_bed.cover import _cover_entities_for

        entry = _paired_entry(hass)
        children = _build_paired_children(hass, entry)
        right = children[SIDE_RIGHT]

        # The side never connected: no live controller, and not primed yet.
        assert right.controller is None
        assert right.capability_controller is None

        # Priming mints a client-free Linak controller purely for capabilities.
        await right.async_prime_offline_controller()
        cap = right.capability_controller
        assert isinstance(cap, LinakController)

        # Its covers are created up-front with byte-identical unique_ids, so the
        # live controller can silently take over on reconnect (no re-add).
        covers = _cover_entities_for(hass, right)
        assert {c.unique_id for c in covers} == {
            f"{RIGHT_ADDR}_back",
            f"{RIGHT_ADDR}_legs",
        }

    async def test_offline_side_builds_switches_from_capability_controller(
        self, hass: HomeAssistant
    ):
        from custom_components.adjustable_bed.switch import _switch_entities_for

        entry = _paired_entry(hass)
        children = _build_paired_children(hass, entry)
        left = children[SIDE_LEFT]
        await left.async_prime_offline_controller()

        # Modern Linak exposes automatic-drive configuration, while its app's
        # AUX light action is toggle-only and therefore never becomes a switch.
        uids = {s.unique_id for s in _switch_entities_for(hass, left)}
        assert f"{LEFT_ADDR}_linak_automatic_drive" in uids
        assert f"{LEFT_ADDR}_under_bed_lights" not in uids

    async def test_pair_cleanup_removes_memory_buttons_after_capacity_shrinks(
        self,
        hass: HomeAssistant,
    ) -> None:
        """Pair-level buttons must follow both sides' current memory capacity."""
        from custom_components.adjustable_bed.button import async_setup_entry

        data = _paired_entry_data()
        standard_snapshot = {
            "profile": "bed_control",
            "model_variant": "standard",
            "actuator_mask": None,
            "timer_supported": False,
            "discovery_complete": True,
        }
        for child in data[CONF_PAIR_CHILDREN]:
            child["capabilities"]["linak"] = standard_snapshot
        entry = MockConfigEntry(
            domain=DOMAIN,
            title="Standard Pair",
            data=data,
            unique_id=PAIR_ID,
            entry_id="paired_standard_cleanup_entry",
            version=4,
        )
        entry.add_to_hass(hass)
        children = _build_paired_children(hass, entry)
        for child in children.values():
            await child.async_prime_offline_controller()
        coordinator = PairedBedCoordinator(hass, entry, children)
        hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

        registry = er.async_get(hass)
        stale_unique_ids = {
            f"{PAIR_ID}_preset_memory_1_both",
            f"{PAIR_ID}_program_memory_1_both",
        }
        for unique_id in stale_unique_ids:
            registry.async_get_or_create(
                "button",
                DOMAIN,
                unique_id,
                config_entry=entry,
            )

        entities: list[Any] = []
        await async_setup_entry(hass, entry, entities.extend)

        assert all(
            registry.async_get_entity_id("button", DOMAIN, unique_id) is None
            for unique_id in stale_unique_ids
        )
        assert f"{PAIR_ID}_stop_both" in {entity.unique_id for entity in entities}

    async def test_capability_controller_precedence_and_default(self, hass: HomeAssistant):
        from unittest.mock import MagicMock

        entry = _paired_entry(hass)
        children = _build_paired_children(hass, entry)
        child = children[SIDE_LEFT]

        # No live and no offline controller -> None (exactly today's behaviour).
        assert child.capability_controller is None
        await child.async_prime_offline_controller()
        assert child.capability_controller is not None

        # A live controller always takes precedence over the offline one.
        live = MagicMock()
        child._controller = live
        assert child.capability_controller is live

    async def test_unsafe_bed_type_side_is_not_offline_minted(self, hass: HomeAssistant):
        # A bed type that is NOT capability-deterministic offline (auto-variant /
        # connect-corrected / post-connect query) must NOT be offline-minted, so
        # it can't register entities from a wrong profile. It keeps today's
        # behaviour (no offline entities until it connects).
        data = _paired_entry_data()
        data[CONF_BED_TYPE] = BED_TYPE_OCTO
        for child in data[CONF_PAIR_CHILDREN]:
            child[CONF_BED_TYPE] = BED_TYPE_OCTO
        entry = MockConfigEntry(
            domain=DOMAIN, title="Octo", data=data, unique_id="pair_octo", version=4
        )
        entry.add_to_hass(hass)
        children = _build_paired_children(hass, entry)
        left = children[SIDE_LEFT]

        await left.async_prime_offline_controller()
        assert left.capability_controller is None

    async def test_leggett_platt_explicit_variant_side_is_offline_minted(self, hass: HomeAssistant):
        # Even if a child descriptor still carries the UMBRELLA leggett_platt with
        # an explicit gen2 variant, the coordinator resolves it before the
        # mintability check and mints the concrete Gen2 controller offline — so the
        # side the pairing gate accepted as offline-safe actually gets its
        # light/select/climate entities without waiting for a reload-while-online.
        data = _paired_entry_data()
        data[CONF_BED_TYPE] = BED_TYPE_LEGGETT_PLATT
        for child in data[CONF_PAIR_CHILDREN]:
            child[CONF_BED_TYPE] = BED_TYPE_LEGGETT_PLATT
            child[CONF_PROTOCOL_VARIANT] = LEGGETT_VARIANT_GEN2
        entry = MockConfigEntry(
            domain=DOMAIN,
            title="L&P",
            data=data,
            unique_id="pair_lp",
            version=4,
        )
        entry.add_to_hass(hass)
        left = _build_paired_children(hass, entry)[SIDE_LEFT]

        from unittest.mock import patch

        from custom_components.adjustable_bed import coordinator as coordinator_mod

        with patch(
            "custom_components.adjustable_bed.coordinator.create_controller",
            wraps=coordinator_mod.create_controller,
        ) as create_controller:
            await left.async_prime_offline_controller()
        assert left.capability_controller is not None
        # Minted with the RESOLVED concrete type, not the umbrella leggett_platt —
        # that is the gate/minting consistency this regression guards.
        assert create_controller.await_args is not None
        assert create_controller.await_args.kwargs["bed_type"] == BED_TYPE_LEGGETT_GEN2

    async def test_no_op_bed_type_correction_keeps_offline_controller(self, hass: HomeAssistant):
        # A connect-time correction that does NOT change the bed type must keep
        # the already-primed offline controller (so capability_controller still
        # resolves it after a later disconnect).
        entry = _paired_entry(hass)
        children = _build_paired_children(hass, entry)
        left = children[SIDE_LEFT]
        await left.async_prime_offline_controller()
        primed = left.capability_controller
        assert primed is not None

        left._apply_runtime_bed_type_correction(left.bed_type)
        assert left.capability_controller is primed


class TestPairedPairingIssue:
    """Phase 2.4: a paired side that needs OS-level BLE pairing surfaces a repair."""

    async def test_pairing_issue_noop_for_non_pairing_side(self, hass: HomeAssistant):
        from homeassistant.helpers import issue_registry as ir

        data = _paired_entry_data()
        data[CONF_BED_TYPE] = BED_TYPE_BEDTECH
        for child in data[CONF_PAIR_CHILDREN]:
            child[CONF_BED_TYPE] = BED_TYPE_BEDTECH
            child.pop("capabilities", None)
        entry = MockConfigEntry(
            domain=DOMAIN,
            title="Master Bed",
            data=data,
            unique_id=PAIR_ID,
            entry_id="paired_non_bonding_entry",
            version=4,
        )
        entry.add_to_hass(hass)
        children = _build_paired_children(hass, entry)
        left = children[SIDE_LEFT]

        before = len(ir.async_get(hass).issues)
        # A non-bonding protocol produces no repair issue and does not crash.
        await _maybe_create_pairing_issue_for(hass, left)
        assert len(ir.async_get(hass).issues) == before


class TestOfflineSafeBedTypes:
    """Every member of OFFLINE_CAPABILITY_SAFE_BED_TYPES must mint a client-free
    capability controller — guards against a future bed introducing a live-client
    dependency / post-connect capability mutation while still in the safe set."""

    @pytest.mark.parametrize("bed_type", sorted(OFFLINE_CAPABILITY_SAFE_BED_TYPES))
    async def test_offline_safe_bed_mints_capability_controller(
        self, hass: HomeAssistant, bed_type: str
    ):
        data = _paired_entry_data()
        data[CONF_BED_TYPE] = bed_type
        for child in data[CONF_PAIR_CHILDREN]:
            child[CONF_BED_TYPE] = bed_type
            if bed_type == BED_TYPE_SOLACE:
                child[CONF_BLE_DEVICE_NAME] = "SealyMF Base"
        entry = MockConfigEntry(
            domain=DOMAIN,
            title=bed_type,
            data=data,
            unique_id=f"pair_{bed_type}",
            version=4,
        )
        entry.add_to_hass(hass)
        children = _build_paired_children(hass, entry)
        left = children[SIDE_LEFT]

        await left.async_prime_offline_controller()
        assert left.capability_controller is not None, bed_type

    async def test_solace_offline_profile_uses_observed_ble_name(self, hass: HomeAssistant) -> None:
        data = _paired_entry_data()
        data[CONF_BED_TYPE] = BED_TYPE_SOLACE
        for child in data[CONF_PAIR_CHILDREN]:
            child.update(
                {
                    CONF_BED_TYPE: BED_TYPE_SOLACE,
                    CONF_NAME: "Renamed bedroom bed",
                    CONF_BLE_DEVICE_NAME: "SealyMF Base",
                }
            )
        entry = MockConfigEntry(
            domain=DOMAIN,
            title="Renamed bedroom bed",
            data=data,
            unique_id="pair_solace_observed_name",
            version=4,
        )
        entry.add_to_hass(hass)
        left = _build_paired_children(hass, entry)[SIDE_LEFT]

        await left.async_prime_offline_controller()

        assert left.capability_controller is not None
        assert left.capability_controller.supports_solace_audio is True

    async def test_legacy_solace_without_observed_name_is_not_minted(
        self, hass: HomeAssistant
    ) -> None:
        data = _paired_entry_data()
        data[CONF_BED_TYPE] = BED_TYPE_SOLACE
        for child in data[CONF_PAIR_CHILDREN]:
            child.update(
                {
                    CONF_BED_TYPE: BED_TYPE_SOLACE,
                    CONF_NAME: "Renamed bedroom bed",
                }
            )
            child.pop(CONF_BLE_DEVICE_NAME, None)
        entry = MockConfigEntry(
            domain=DOMAIN,
            title="Renamed bedroom bed",
            data=data,
            unique_id="pair_solace_legacy_name",
            version=4,
        )
        entry.add_to_hass(hass)
        left = _build_paired_children(hass, entry)[SIDE_LEFT]

        await left.async_prime_offline_controller()

        assert left.capability_controller is None

    async def test_solace_learned_profile_reloads_after_connection_release(
        self, hass: HomeAssistant
    ) -> None:
        """A legacy offline side gains its profile entities without a manual reload."""
        data = _paired_entry_data()
        data[CONF_BED_TYPE] = BED_TYPE_SOLACE
        for child in data[CONF_PAIR_CHILDREN]:
            child[CONF_BED_TYPE] = BED_TYPE_SOLACE
            child.pop(CONF_BLE_DEVICE_NAME, None)
        entry = MockConfigEntry(
            domain=DOMAIN,
            title="Legacy Solace pair",
            data=data,
            unique_id="pair_solace_deferred_reload",
            entry_id="pair_solace_deferred_reload",
            version=4,
        )
        entry.add_to_hass(hass)
        children = _build_paired_children(hass, entry)
        coordinator = PairedBedCoordinator(hass, entry, children)
        hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
        remove_listener = entry.add_update_listener(_async_update_listener)
        left = children[SIDE_LEFT]
        right = children[SIDE_RIGHT]
        client = AsyncMock()
        client.is_connected = True
        left._client = client

        try:
            with patch.object(
                hass.config_entries,
                "async_reload",
                new_callable=AsyncMock,
            ) as reload_entry:
                left._record_observed_ble_device_name("SealyMF Base")
                await hass.async_block_till_done()

                # Persist the profile without unloading the coordinator during
                # connection setup.
                reload_entry.assert_not_awaited()
                persisted = get_child(entry.data, SIDE_LEFT)
                assert persisted is not None
                assert dict(persisted)[CONF_BLE_DEVICE_NAME] == "SealyMF Base"

                # Once the learned-profile link drops, neither an ordinary
                # reconnect nor an explicit pairing attempt may race the reload.
                client.is_connected = False
                assert await left.async_connect() is False
                assert await left.async_pair_now() is False
                client.is_connected = True
                client.disconnect.side_effect = lambda: setattr(client, "is_connected", False)
                async with right.async_command_operation_guard():
                    await left.async_disconnect()
                    await asyncio.sleep(0)

                    reload_entry.assert_not_awaited()
                await hass.async_block_till_done()

                reload_entry.assert_awaited_once_with(entry.entry_id)
        finally:
            remove_listener()
            hass.data[DOMAIN].pop(entry.entry_id, None)


class TestOctoOfflineSnapshot:
    """Phase 2.5 C3 (commit 2): a paired Octo side mints offline from a captured
    capability snapshot; without one it stays non-minted (today's behaviour)."""

    def _octo_children(self, hass: HomeAssistant, *, left_snapshot):
        data = _paired_entry_data()
        data[CONF_BED_TYPE] = BED_TYPE_OCTO
        for child in data[CONF_PAIR_CHILDREN]:
            child[CONF_BED_TYPE] = BED_TYPE_OCTO
        if left_snapshot is not None:
            data[CONF_PAIR_CHILDREN][0]["capabilities"] = {"octo": left_snapshot}
        entry = MockConfigEntry(
            domain=DOMAIN, title="Octo", data=data, unique_id="pair_octo", version=4
        )
        entry.add_to_hass(hass)
        return _build_paired_children(hass, entry)

    async def test_octo_side_with_snapshot_mints_offline(self, hass: HomeAssistant):
        snap = {
            "has_pin": True,
            "pin_locked": False,
            "has_lights": True,
            "has_rgbwi": True,
            "rgbwi_value_type": 5,
            "memory_count": 4,
            "discovered_motor_count": 2,
            "has_synchro": True,
        }
        left = self._octo_children(hass, left_snapshot=snap)[SIDE_LEFT]
        await left.async_prime_offline_controller()
        ctrl = left.capability_controller
        assert ctrl is not None
        assert ctrl.supports_lights is True
        assert ctrl.supports_memory_presets is True

    async def test_octo_side_without_snapshot_not_minted(self, hass: HomeAssistant):
        left = self._octo_children(hass, left_snapshot=None)[SIDE_LEFT]
        await left.async_prime_offline_controller()
        # No snapshot -> Octo is not offline-mintable (keeps today's behaviour).
        assert left.capability_controller is None

    async def test_octo_star2_side_mints_offline_without_snapshot(self, hass: HomeAssistant):
        """Star2 has FIXED caps and no snapshot, but is statically offline-mintable
        (its controller builds without a client), so a paired Star2 side still gets
        its entities offline — unlike standard Octo, which needs a snapshot."""
        data = _paired_entry_data()
        data[CONF_BED_TYPE] = BED_TYPE_OCTO
        for child in data[CONF_PAIR_CHILDREN]:
            child[CONF_BED_TYPE] = BED_TYPE_OCTO
            child[CONF_PROTOCOL_VARIANT] = OCTO_VARIANT_STAR2
        entry = MockConfigEntry(domain=DOMAIN, data=data, unique_id="pair_star2", version=4)
        entry.add_to_hass(hass)
        left = _build_paired_children(hass, entry)[SIDE_LEFT]
        await left.async_prime_offline_controller()
        assert left.capability_controller is not None

    async def test_octo_star2_pair_offline_safe_without_snapshot(self, hass: HomeAssistant):
        """A Star2 entry is offline-safe with NO live snapshot, so the pairing gate
        must not demand a connection for it."""
        from custom_components.adjustable_bed.config_flow import (
            AdjustableBedConfigFlow,
        )

        star2 = MockConfigEntry(
            domain=DOMAIN,
            data={
                CONF_ADDRESS: LEFT_ADDR,
                CONF_BED_TYPE: BED_TYPE_OCTO,
                CONF_PROTOCOL_VARIANT: OCTO_VARIANT_STAR2,
            },
            unique_id=LEFT_ADDR,
            version=4,
        )
        star2.add_to_hass(hass)

        flow = AdjustableBedConfigFlow()
        flow.hass = hass
        assert flow._is_octo_star2(star2) is True
        assert flow._octo_capability_snapshot(star2) is None  # no dynamic snapshot
        # ...yet still offline-safe (standard Octo without a snapshot would be unsafe).
        assert flow._has_unsafe_offline_platforms(star2) is False


class TestOctoSnapshotBackfill:
    """Phase 2.5 C3 (commit 4): a paired Octo side persists its freshly-discovered
    capability snapshot into its child descriptor on connect."""

    async def test_backfill_persists_snapshot_into_descriptor(self, hass: HomeAssistant):
        from types import SimpleNamespace

        data = _paired_entry_data()
        data[CONF_BED_TYPE] = BED_TYPE_OCTO
        for child in data[CONF_PAIR_CHILDREN]:
            child[CONF_BED_TYPE] = BED_TYPE_OCTO
        entry = MockConfigEntry(
            domain=DOMAIN,
            title="Octo",
            data=data,
            unique_id="pair_octo_bf",
            entry_id="pair_octo_bf",
            version=4,
        )
        entry.add_to_hass(hass)
        left = _build_paired_children(hass, entry)[SIDE_LEFT]

        snap = {"has_lights": True, "memory_count": 4, "has_rgbwi": False}
        left._controller = SimpleNamespace(capability_snapshot=lambda: dict(snap))
        left._backfill_octo_snapshot()

        # The snapshot was persisted into the parent entry's left descriptor.
        assert octo_snapshot_from_descriptor(get_child(entry.data, SIDE_LEFT)) == snap
        # Right side untouched.
        assert octo_snapshot_from_descriptor(get_child(entry.data, SIDE_RIGHT)) is None

    async def test_backfill_preserves_snapshot_on_incomplete_discovery(self, hass: HomeAssistant):
        """A later reconnect whose discover_features() times out yields NO snapshot
        (capability_snapshot() returns None once it gates on the CAP_END sentinel),
        so backfill must NOT erase the pairing-time capabilities. Regression for a
        transient timeout's fallback profile overwriting a real descriptor and
        dropping offline memory/light entities on the next reload."""
        from types import SimpleNamespace

        data = _paired_entry_data()
        data[CONF_BED_TYPE] = BED_TYPE_OCTO
        for child in data[CONF_PAIR_CHILDREN]:
            child[CONF_BED_TYPE] = BED_TYPE_OCTO
        entry = MockConfigEntry(
            domain=DOMAIN,
            title="Octo",
            data=data,
            unique_id="pair_octo_bf2",
            entry_id="pair_octo_bf2",
            version=4,
        )
        entry.add_to_hass(hass)
        left = _build_paired_children(hass, entry)[SIDE_LEFT]

        real = {"has_lights": True, "memory_count": 4, "has_rgbwi": True}
        left._controller = SimpleNamespace(capability_snapshot=lambda: dict(real))
        left._backfill_octo_snapshot()
        assert octo_snapshot_from_descriptor(get_child(entry.data, SIDE_LEFT)) == real

        # Transient discovery timeout -> capability_snapshot() is None -> no-op,
        # the real pairing-time snapshot survives.
        left._controller = SimpleNamespace(capability_snapshot=lambda: None)
        left._backfill_octo_snapshot()
        assert octo_snapshot_from_descriptor(get_child(entry.data, SIDE_LEFT)) == real

    async def test_backfill_refreshes_stale_offline_controller(self, hass: HomeAssistant):
        """A backfill that discovers NEW caps must also refresh the in-memory
        offline controller — cache_capability_controller only fills an empty slot,
        so without this a later sequential release falls back to the stale
        pairing-time controller and per-side entity gating stays wrong until
        reload."""
        from types import SimpleNamespace

        data = _paired_entry_data()
        data[CONF_BED_TYPE] = BED_TYPE_OCTO
        for child in data[CONF_PAIR_CHILDREN]:
            child[CONF_BED_TYPE] = BED_TYPE_OCTO
        entry = MockConfigEntry(
            domain=DOMAIN,
            title="Octo",
            data=data,
            unique_id="pair_octo_refresh",
            entry_id="pair_octo_refresh",
            version=4,
        )
        entry.add_to_hass(hass)
        left = _build_paired_children(hass, entry)[SIDE_LEFT]

        # Offline controller minted from the OLD pairing-time snapshot.
        stale = SimpleNamespace(tag="stale-pairing-time")
        left._offline_controller = stale
        # Live controller has freshly discovered (different) caps.
        new_snap = {"has_lights": True, "memory_count": 4, "has_rgbwi": True}
        live = SimpleNamespace(capability_snapshot=lambda: dict(new_snap))
        left._controller = live

        left._backfill_octo_snapshot()

        # Descriptor backfilled AND the offline controller refreshed to the live
        # one (no longer the stale pairing-time controller).
        assert octo_snapshot_from_descriptor(get_child(entry.data, SIDE_LEFT)) == new_snap
        assert left._offline_controller is live
        assert left._offline_controller is not stale
