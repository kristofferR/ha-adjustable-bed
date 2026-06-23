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
    BED_TYPE_LEGGETT_GEN2,
    BED_TYPE_LEGGETT_OKIN,
    BED_TYPE_LEGGETT_PLATT,
    BED_TYPE_LEGGETT_WILINKE,
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
    CONF_PROTOCOL_VARIANT,
    CONF_SIDE,
    DOMAIN,
    LEGGETT_VARIANT_GEN2,
    LEGGETT_VARIANT_MLRM,
    LEGGETT_VARIANT_OKIN,
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
    octo_snapshot_from_descriptor,
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

    async def _setup_single(
        self, hass: HomeAssistant, address: str, name: str
    ) -> MockConfigEntry:
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

    async def test_leggett_platt_explicit_variant_is_offline_safe(
        self, hass: HomeAssistant
    ):
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
        assert (
            flow._offline_safe_bed_type(_entry(LEFT_ADDR, "auto"))
            == BED_TYPE_LEGGETT_PLATT
        )

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
        ent_reg.async_get_or_create(
            "light", DOMAIN, f"{LEFT_ADDR}_rgb_light", config_entry=gen2
        )
        assert flow._has_unsafe_offline_platforms(gen2) is False

        # okin resolves to a non-offline-safe type, so the same light entity keeps
        # it blocked.
        okin = _entry(RIGHT_ADDR, LEGGETT_VARIANT_OKIN)
        okin.add_to_hass(hass)
        ent_reg.async_get_or_create(
            "light", DOMAIN, f"{RIGHT_ADDR}_rgb_light", config_entry=okin
        )
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
        assert (
            resolve_explicit_bed_type(BED_TYPE_LEGGETT_PLATT, "auto")
            == BED_TYPE_LEGGETT_PLATT
        )
        assert (
            resolve_explicit_bed_type(BED_TYPE_LEGGETT_PLATT, None)
            == BED_TYPE_LEGGETT_PLATT
        )
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
        left = self._single(hass, LEFT_ADDR, "Seng")
        self._single(hass, RIGHT_ADDR, "Bed 4587")

        result = await self._reach_pair_step(hass)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"left_entry": left.entry_id, "right_entry": left.entry_id},
        )
        assert result["type"] == FlowResultType.FORM
        assert result["errors"]

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
        left_device = dev_reg.async_get_device(identifiers={(DOMAIN, LEFT_ADDR)})
        assert left_device is not None
        left_device_id = left_device.id
        dev_reg.async_update_device(left_device_id, name_by_user="Left headboard")

        # Convert.
        result = await self._reach_pair_step(hass)
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
        parent = dev_reg.async_get_device(
            identifiers={(DOMAIN, pair.data[CONF_PAIR_ID])}
        )
        assert parent is not None
        left_after = dev_reg.async_get_device(identifiers={(DOMAIN, LEFT_ADDR)})
        assert left_after is not None
        assert left_after.id == left_device_id  # same device, not recreated
        assert left_after.name_by_user == "Left headboard"
        assert left_after.via_device_id == parent.id

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
            "custom_components.adjustable_bed.coordinator.bluetooth."
            "async_ble_device_from_address",
            return_value=None,
        ):
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"],
                {"left_entry": left.entry_id, "right_entry": right.entry_id},
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
                {"left_entry": left.entry_id, "right_entry": right.entry_id},
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
                {"left_entry": left.entry_id, "right_entry": right.entry_id},
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
                {"left_entry": left.entry_id, "right_entry": right.entry_id},
            )
            await hass.async_block_till_done()

        assert result["type"] == FlowResultType.CREATE_ENTRY
        # The hanging retry was attempted, then deterministically cancelled by the
        # SETUP_TIMEOUT guard (not allowed to return after the long sleep), without
        # blocking setup.
        assert calls.get(LEFT_ADDR, 0) == 2
        assert retry_cancelled is True
        paired = [
            e for e in hass.config_entries.async_entries(DOMAIN) if is_paired(e.data)
        ]
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

    async def test_leggett_platt_explicit_variant_side_is_offline_minted(
        self, hass: HomeAssistant
    ):
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

        await left.async_prime_offline_controller()
        assert left.capability_controller is not None

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


class TestOctoSnapshotBackfill:
    """Phase 2.5 C3 (commit 4): a paired Octo side persists its freshly-discovered
    capability snapshot into its child descriptor on connect."""

    async def test_backfill_persists_snapshot_into_descriptor(
        self, hass: HomeAssistant
    ):
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

    async def test_backfill_preserves_snapshot_on_incomplete_discovery(
        self, hass: HomeAssistant
    ):
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
