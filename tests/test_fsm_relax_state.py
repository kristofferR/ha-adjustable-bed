"""Device-local eight-slot storage and atomic rollback, without physical units."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.adjustable_bed.fsm_relax_state import (
    FsmRelaxState,
    validate_names,
    validate_positions,
)


async def test_store_roundtrip_restart_names_serial_and_removal(hass):
    state = FsmRelaxState(hass, "entry", "AA:BB:CC:DD:EE:FF")
    await state.async_load()
    await state.async_save_slot(8, {0: -(2**31), 3: 2**31 - 1})
    await state.async_set_names([" Sleep ", ""] + [f"Slot {i}" for i in range(3, 9)])
    await state.async_save_capabilities(bytes.fromhex("0206040008"))
    await state.async_save_serial(-1)
    reloaded = FsmRelaxState(hass, "entry", "aa:bb:cc:dd:ee:ff")
    await reloaded.async_load()
    assert reloaded.slots == {8: {0: -(2**31), 3: 2**31 - 1}}
    assert reloaded.names == (
        "Sleep",
        "M2",
        "Slot 3",
        "Slot 4",
        "Slot 5",
        "Slot 6",
        "Slot 7",
        "Slot 8",
    )
    assert reloaded.capability_body == bytes.fromhex("0206040008")
    assert reloaded.serial == -1
    await reloaded.async_set_names([""] * 8)
    assert reloaded.names == tuple(f"M{i}" for i in range(1, 9))
    for identity, address in [("other", "11:22:33:44:55:66")]:
        other = FsmRelaxState(hass, identity, address)
        await other.async_load()
        assert other.slots == {} and other.serial is None
    await reloaded.async_remove()
    after = FsmRelaxState(hass, "entry", "AA:BB:CC:DD:EE:FF")
    await after.async_load()
    assert after.slots == {} and after.capability_body is None and after.serial is None


async def test_child_entry_ownership_transfers_preserve_physical_store_and_true_removal(hass):
    from homeassistant.const import CONF_ADDRESS
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.adjustable_bed import async_remove_entry, const
    from custom_components.adjustable_bed.coordinator import ChildEntryView
    from custom_components.adjustable_bed.pairing import build_pair_entry_data

    left_data = {CONF_ADDRESS: "AA:BB:CC:DD:EE:FF", const.CONF_BED_TYPE: const.BED_TYPE_FSM_RELAX}
    right_data = {**left_data, CONF_ADDRESS: "11:22:33:44:55:66"}
    left = MockConfigEntry(domain=const.DOMAIN, data=left_data)
    right = MockConfigEntry(domain=const.DOMAIN, data=right_data)
    pair = MockConfigEntry(domain=const.DOMAIN, data=build_pair_entry_data(left_data, right_data, name="Pair"))
    for entry in (left, right, pair):
        entry.add_to_hass(hass)
    for entry, raw in ((left, -1), (right, -(2**31))):
        state = FsmRelaxState(hass, entry.entry_id, entry.data[CONF_ADDRESS])
        await state.async_save_slot(8, {0: raw})
        await state.async_set_names([entry.entry_id] + [""] * 7)
        await state.async_save_capabilities(bytes.fromhex("0206000008"))
    for index, original in enumerate((left, right)):
        child = ChildEntryView(pair, pair.data[const.CONF_PAIR_CHILDREN][index], lambda _: None)
        state = FsmRelaxState(hass, child.entry_id, child.data[CONF_ADDRESS])
        await state.async_load()
        assert state.slots[8][0] == (-1 if index == 0 else -(2**31))
        assert state.names[0] == original.entry_id
        await async_remove_entry(hass, original)
        after = FsmRelaxState(hass, "unpaired-owner", child.data[CONF_ADDRESS])
        await after.async_load()
        assert after.slots == state.slots and after.names == state.names
    # Unpair leaves surviving standalone owners, so parent removal preserves both.
    await async_remove_entry(hass, pair)
    # True pair removal cleans each physical child once no other owner exists.
    with patch.object(hass.config_entries, "async_entries", return_value=[pair]):
        await async_remove_entry(hass, pair)
    for address in (left_data[CONF_ADDRESS], right_data[CONF_ADDRESS]):
        removed = FsmRelaxState(hass, "new-owner", address)
        await removed.async_load()
        assert removed.slots == {} and removed.capability_body is None


async def test_atomic_failure_preserves_existing_slot_names_and_serial(hass):
    state = FsmRelaxState(hass, "entry", "AA:BB:CC:DD:EE:FF")
    state._store = MagicMock(async_save=AsyncMock(side_effect=OSError("disk")))
    state.slots = {1: {0: 11}}
    for operation in (
        state.async_save_slot(1, {0: -1}),
        state.async_set_names(["new"] * 8),
        state.async_save_serial(3),
        state.async_save_capabilities(bytes.fromhex("0202040008")),
    ):
        with pytest.raises(OSError):
            await operation
    assert state.slots == {1: {0: 11}}
    assert state.names == tuple(f"M{i}" for i in range(1, 9))
    assert state.serial is None and state.capability_body is None


@pytest.mark.parametrize("value", [None, [], [""] * 7, [""] * 9, ["x" * 81] * 8, [True] * 8])
def test_validate_all_names_before_mutation(value):
    with pytest.raises(ValueError):
        validate_names(value)


@pytest.mark.parametrize(
    "positions", [{}, {1: 1}, {0: True}, {0: 2**31}, {0: -(2**31) - 1}, {0: 0, 4: 1}, {"0": 1}]
)
def test_opaque_position_validation(positions):
    with pytest.raises(ValueError):
        validate_positions(positions)


async def test_corrupt_record_is_never_projected_to_bed(hass):
    state = FsmRelaxState(hass, "entry", "AA:BB:CC:DD:EE:FF")
    state._store = MagicMock(
        async_load=AsyncMock(return_value={"slots": {"1": {"0": 2**40}}, "names": [""] * 8})
    )
    await state.async_load()
    assert state.slots == {}
