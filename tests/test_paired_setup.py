"""Integration tests for setting up a paired (Dual Bed 4.0) entry."""

from __future__ import annotations

import pytest
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
    _build_paired_children,
    _make_child_persist_cb,
    _maybe_create_pairing_issue_for,
    _shared_child_fields,
)
from custom_components.adjustable_bed.const import (
    BED_TYPE_LINAK,
    BED_TYPE_OCTO,
    BED_TYPE_RICHMAT,
    CONF_BED_TYPE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_MOTOR_COUNT,
    CONF_PAIR_CHILDREN,
    CONF_PAIR_ID,
    CONF_PAIR_MEMBER_ADDRESSES,
    CONF_PAIR_MODE,
    CONF_PAIR_SCHEMA_VERSION,
    CONF_PREFERRED_ADAPTER,
    CONF_SIDE,
    DOMAIN,
    OFFLINE_CAPABILITY_SAFE_BED_TYPES,
    PAIR_MODE_SEPARATE_ADDRESS,
    SIDE_BOTH,
    SIDE_LEFT,
    SIDE_RIGHT,
)
from custom_components.adjustable_bed.paired_coordinator import PairedBedCoordinator
from custom_components.adjustable_bed.pairing import (
    get_child,
    is_paired,
    pair_member_addresses,
)

LEFT_ADDR = "AA:BB:CC:DD:EE:01"
RIGHT_ADDR = "AA:BB:CC:DD:EE:02"
PAIR_ID = "pair_test123456"


def _child(side: str, address: str) -> dict:
    return {
        CONF_SIDE: side,
        CONF_ADDRESS: address,
        CONF_NAME: side.capitalize(),
        CONF_BED_TYPE: BED_TYPE_LINAK,
        CONF_MOTOR_COUNT: 2,
        CONF_DISABLE_ANGLE_SENSING: True,
        CONF_PREFERRED_ADAPTER: "auto",
        "capabilities": {"motor_count": 2, "motor_keys": ["back", "legs"]},
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
        parent = registry.async_get_device(identifiers={(DOMAIN, PAIR_ID)})
        assert parent is not None

        left = registry.async_get_device(identifiers={(DOMAIN, LEFT_ADDR)})
        right = registry.async_get_device(identifiers={(DOMAIN, RIGHT_ADDR)})
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
        entries = [
            e for e in registry.entities.values() if e.config_entry_id == entry.entry_id
        ]
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
        assert both_uids - {
            f"{PAIR_ID}_stop_both"
        }, "expected combined movement/preset buttons on the parent"
        # A cover-based pair (Linak) has no combined cover, so the parent gets
        # per-motor "both sides" up/down motion buttons instead.
        for key in ("back_up", "back_down", "legs_up", "legs_down"):
            assert f"{PAIR_ID}_{key}_both" in both_uids

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
            if any(
                i[0] == DOMAIN and i[1].upper() == LEFT_ADDR.upper()
                for i in device.identifiers
            )
        )

        with patch.object(
            coordinator, "async_stop_command", new=AsyncMock()
        ) as mock_stop:
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
                for device in dr.async_entries_for_config_entry(
                    dev_reg, entry.entry_id
                )
                if any(
                    i[0] == DOMAIN and i[1].upper() == addr.upper()
                    for i in device.identifiers
                )
            )

        with patch.object(
            coordinator, "async_stop_command", new=AsyncMock()
        ) as mock_stop:
            await hass.services.async_call(
                DOMAIN,
                "stop_all",
                {"device_id": [device_for(LEFT_ADDR).id, device_for(RIGHT_ADDR).id]},
                blocking=True,
            )
        mock_stop.assert_awaited_once_with(side=SIDE_BOTH)

    async def test_set_position_on_parent_device_needs_a_side(
        self,
        hass: HomeAssistant,
        mock_coordinator_connected,
        enable_custom_integrations,
    ):
        """Per-motor services on the paired parent ask the user to pick a side."""
        entry = _paired_entry(hass)
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        dev_reg = dr.async_get(hass)
        parent = next(
            device
            for device in dr.async_entries_for_config_entry(dev_reg, entry.entry_id)
            if (DOMAIN, PAIR_ID) in device.identifiers
        )
        with pytest.raises(ServiceValidationError):
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
        shared = _shared_child_fields(_paired_entry_data())
        assert CONF_PAIR_ID not in shared
        assert CONF_PAIR_CHILDREN not in shared
        assert CONF_PAIR_MODE not in shared
        # shared, non-pair fields survive
        assert shared[CONF_BED_TYPE] == BED_TYPE_LINAK

    async def test_build_children_reads_per_side_descriptor(
        self, hass: HomeAssistant
    ):
        entry = _paired_entry(hass)
        children = _build_paired_children(hass, entry)
        assert set(children) == {SIDE_LEFT, SIDE_RIGHT}
        # each child reads its own address from its descriptor
        assert children[SIDE_LEFT].address == LEFT_ADDR
        assert children[SIDE_RIGHT].address == RIGHT_ADDR

    async def test_child_persist_writes_delta_to_correct_descriptor(
        self, hass: HomeAssistant
    ):
        entry = _paired_entry(hass)
        baseline = {**_shared_child_fields(entry.data), **_child(SIDE_LEFT, LEFT_ADDR)}
        persist = _make_child_persist_cb(hass, entry, SIDE_LEFT)

        # Persist a change (e.g. a BLE bond marker) for the left side.
        persist({**baseline, "ble_bond_established": True})

        left = get_child(entry.data, SIDE_LEFT)
        right = get_child(entry.data, SIDE_RIGHT)
        assert left["ble_bond_established"] is True
        assert "ble_bond_established" not in right  # right untouched

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


class TestPairBedsConversion:
    """The 'combine two beds' config-flow step."""

    def _single(
        self,
        hass: HomeAssistant,
        address: str,
        name: str,
        bed_type: str = BED_TYPE_LINAK,
    ) -> MockConfigEntry:
        entry = MockConfigEntry(
            domain=DOMAIN,
            title=name,
            data={
                CONF_ADDRESS: address,
                CONF_NAME: name,
                CONF_BED_TYPE: bed_type,
                CONF_MOTOR_COUNT: 2,
                CONF_DISABLE_ANGLE_SENSING: True,
                CONF_PREFERRED_ADAPTER: "auto",
            },
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
                "left_entry": left.entry_id,
                "right_entry": right.entry_id,
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
            {"left_entry": left.entry_id, "right_entry": right.entry_id},
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
            {"left_entry": left.entry_id, "right_entry": right.entry_id},
        )
        assert result["type"] == FlowResultType.FORM
        assert result["errors"].get("right_entry") == "same_address"

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
            {"left_entry": left.entry_id, "right_entry": right.entry_id},
        )
        await hass.async_block_till_done()
        assert result["type"] == FlowResultType.CREATE_ENTRY

        paired = next(
            entry
            for entry in hass.config_entries.async_entries(DOMAIN)
            if is_paired(entry.data)
        )
        left_child = get_child(paired.data, SIDE_LEFT)
        assert left_child is not None
        assert left_child[CONF_ADDRESS] == LEFT_ADDR
        assert left_child.get("back_max_angle") == 55.0

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
            {"left_entry": entries[0], "right_entry": entries[1]},
        )
        assert result["type"] == FlowResultType.FORM
        assert result["errors"]["base"] == "octo_pairing_needs_connection"

    async def test_octo_gate_allows_and_captures_when_snapshot_present(
        self, hass: HomeAssistant
    ):
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
        # Gate: a snapshot makes Octo offline-safe; without one it stays unsafe.
        assert flow._octo_capability_snapshot(entry) == snap
        assert flow._has_unsafe_offline_platforms(entry) is False
        hass.data[DOMAIN].pop(entry.entry_id)
        assert flow._has_unsafe_offline_platforms(entry) is True
        # Capture: the snapshot lands in the built descriptor's capabilities['octo'].
        pair = build_pair_entry_data(
            {CONF_ADDRESS: LEFT_ADDR, CONF_BED_TYPE: BED_TYPE_OCTO},
            {CONF_ADDRESS: RIGHT_ADDR, CONF_BED_TYPE: BED_TYPE_OCTO},
            name="Master Octo",
            left_octo_snapshot=snap,
            right_octo_snapshot=snap,
        )
        assert octo_snapshot_from_descriptor(get_child(pair, SIDE_LEFT)) == snap

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
        left = self._single(hass, LEFT_ADDR, "Seng")
        self._single(hass, RIGHT_ADDR, "Bed 4587")

        result = await self._reach_pair_step(hass)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"left_entry": left.entry_id, "right_entry": left.entry_id},
        )
        assert result["type"] == FlowResultType.FORM
        assert result["errors"]


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

        devices = dr.async_entries_for_config_entry(
            dr.async_get(hass), mock_config_entry.entry_id
        )
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

        parent = dr.async_get(hass).async_get_device(identifiers={(DOMAIN, PAIR_ID)})
        assert parent is not None
        for side in ("both", SIDE_LEFT, SIDE_RIGHT):
            await hass.services.async_call(
                DOMAIN,
                "stop_all",
                {"device_id": [parent.id], "side": side},
                blocking=True,
            )

    async def test_unconverted_services_reject_paired_cleanly(
        self,
        hass: HomeAssistant,
        mock_coordinator_connected,
        enable_custom_integrations,
    ):
        """set_position/timed_move raise a clean error (not AttributeError) on a pair."""
        entry = _paired_entry(hass)
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        parent = dr.async_get(hass).async_get_device(identifiers={(DOMAIN, PAIR_ID)})
        assert parent is not None

        with pytest.raises(ServiceValidationError):
            await hass.services.async_call(
                DOMAIN,
                "set_position",
                {"device_id": [parent.id], "motor": "back", "position": 50},
                blocking=True,
            )
        with pytest.raises(ServiceValidationError):
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


class TestOfflineSideEntities:
    """Phase 2.1: a side offline at setup still gets its per-side entities,
    built from a client-free 'capability' controller minted from config, so a
    reconnect needs no reload."""

    async def test_offline_side_builds_covers_from_capability_controller(
        self, hass: HomeAssistant
    ):
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

        # Linak under-bed lighting is a per-side switch; the exact entity must
        # exist offline too (not just "some" switch).
        uids = {s.unique_id for s in _switch_entities_for(hass, left)}
        assert f"{LEFT_ADDR}_under_bed_lights" in uids

    async def test_capability_controller_precedence_and_default(
        self, hass: HomeAssistant
    ):
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

    async def test_no_op_bed_type_correction_keeps_offline_controller(
        self, hass: HomeAssistant
    ):
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

    async def test_pairing_issue_noop_for_non_pairing_side(
        self, hass: HomeAssistant
    ):
        from homeassistant.helpers import issue_registry as ir

        entry = _paired_entry(hass)
        children = _build_paired_children(hass, entry)
        left = children[SIDE_LEFT]

        before = len(ir.async_get(hass).issues)
        # Linak doesn't require OS-level pairing -> no repair issue, no crash.
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
