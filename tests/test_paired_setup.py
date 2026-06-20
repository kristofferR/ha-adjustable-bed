"""Integration tests for setting up a paired (Dual Bed 4.0) entry."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
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
    SIDE_LEFT,
    SIDE_RIGHT,
)
from custom_components.adjustable_bed.paired_coordinator import PairedBedCoordinator
from custom_components.adjustable_bed.pairing import get_child

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

        # exactly one combined stop button on the parent.
        assert any(e.unique_id == f"{PAIR_ID}_stop_both" for e in buttons)

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
        persist = _make_child_persist_cb(hass, entry, SIDE_LEFT, baseline)

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
        persist = _make_child_persist_cb(hass, entry, SIDE_LEFT, baseline)
        persist(dict(baseline))  # no change
        assert entry.data is before  # entry not updated
