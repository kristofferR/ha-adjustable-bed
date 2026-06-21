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
    _shared_child_fields,
)
from custom_components.adjustable_bed.const import (
    BED_TYPE_LINAK,
    BED_TYPE_OCTO,
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

    def _single(self, hass: HomeAssistant, address: str, name: str) -> MockConfigEntry:
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
            },
            unique_id=address,
            version=4,
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

    async def test_pairing_blocked_for_unforwarded_entities(
        self,
        hass: HomeAssistant,
        mock_coordinator_connected,
        enable_custom_integrations,
    ):
        """A bed exposing climate/light/select can't be paired (those would drop)."""
        from homeassistant.helpers import entity_registry as er

        left = self._single(hass, LEFT_ADDR, "Left")
        right = self._single(hass, RIGHT_ADDR, "Right")
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

    async def test_octo_pairing_is_rejected(
        self,
        hass: HomeAssistant,
        mock_coordinator_connected,
        enable_custom_integrations,
    ):
        """Octo pairing is blocked (sequential profile is Phase 2)."""
        for addr, name in ((LEFT_ADDR, "Octo L"), (RIGHT_ADDR, "Octo R")):
            MockConfigEntry(
                domain=DOMAIN,
                title=name,
                data={CONF_ADDRESS: addr, CONF_NAME: name, CONF_BED_TYPE: BED_TYPE_OCTO},
                unique_id=addr,
                version=4,
            ).add_to_hass(hass)

        result = await self._reach_pair_step(hass)
        entries = self._pairable_octo_ids(hass)
        assert len(entries) >= 2  # keep the real assertion below diagnostic
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"left_entry": entries[0], "right_entry": entries[1]},
        )
        assert result["type"] == FlowResultType.FORM
        assert result["errors"]["base"] == "octo_pairing_unsupported"

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
