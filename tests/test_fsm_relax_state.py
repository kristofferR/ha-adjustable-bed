"""Device-local eight-slot app state and atomic memory saves, without physical units."""

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.const import CONF_ADDRESS
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed import async_remove_entry, const
from custom_components.adjustable_bed.app_state_store import app_state_store
from custom_components.adjustable_bed.beds.fsm_relax import FsmRelaxController
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.fsm_relax_state import (
    FsmRelaxSession,
    validate_capability_body,
    validate_names,
    validate_positions,
)
from tests.app_state_helpers import restart_app_state, stored_app_state

ADDRESS = "AA:BB:CC:DD:EE:FF"
SLOT = f"{const.BED_TYPE_FSM_RELAX}:auto"


def _entry(hass, address=ADDRESS, **extra):
    entry = MockConfigEntry(
        domain=const.DOMAIN,
        data={CONF_ADDRESS: address, const.CONF_BED_TYPE: const.BED_TYPE_FSM_RELAX, **extra},
    )
    entry.add_to_hass(hass)
    return entry


async def _controller(coordinator: AdjustableBedCoordinator) -> FsmRelaxController:
    """Mint and restore an offline controller, as setup does."""
    controller = await create_controller(coordinator, const.BED_TYPE_FSM_RELAX, None, None)
    assert isinstance(controller, FsmRelaxController)
    coordinator._offline_controller = controller
    await coordinator._async_restore_app_state(controller)
    return controller


async def test_memories_and_serial_survive_restart_and_names_come_from_config(hass):
    names = [" Sleep ", ""] + [f"Slot {i}" for i in range(3, 9)]
    entry = _entry(hass, **{const.CONF_FSM_RELAX_MEMORY_NAMES: names})
    coordinator = AdjustableBedCoordinator(hass, entry)
    controller = await _controller(coordinator)
    await controller._save_slot(8, {0: -(2**31), 3: 2**31 - 1})
    controller.session.serial = -1
    coordinator.save_app_state(controller)
    assert await stored_app_state(coordinator) == {
        "slots": {"8": {"0": -(2**31), "3": 2**31 - 1}},
        "serial": -1,
    }
    await restart_app_state(hass, ADDRESS)
    restored = await _controller(AdjustableBedCoordinator(hass, entry))
    assert restored.session is not controller.session
    assert restored.session.slots == {8: {0: -(2**31), 3: 2**31 - 1}}
    assert restored.session.serial == -1
    assert restored.memory_slot_names == (
        "Sleep", "M2", "Slot 3", "Slot 4", "Slot 5", "Slot 6", "Slot 7", "Slot 8",
    )
    other = await _controller(AdjustableBedCoordinator(hass, _entry(hass, "11:22:33:44:55:66")))
    assert other.session.slots == {} and other.session.serial is None


async def test_physical_memories_outlive_ownership_transfers_until_true_removal(hass):
    from custom_components.adjustable_bed.pairing import build_pair_entry_data

    left_data = {CONF_ADDRESS: ADDRESS, const.CONF_BED_TYPE: const.BED_TYPE_FSM_RELAX}
    right_data = {**left_data, CONF_ADDRESS: "11:22:33:44:55:66"}
    left = MockConfigEntry(domain=const.DOMAIN, data=left_data)
    right = MockConfigEntry(domain=const.DOMAIN, data=right_data)
    pair = MockConfigEntry(
        domain=const.DOMAIN, data=build_pair_entry_data(left_data, right_data, name="Pair")
    )
    for entry in (left, right, pair):
        entry.add_to_hass(hass)
    for entry, raw in ((left, -1), (right, -(2**31))):
        controller = await _controller(AdjustableBedCoordinator(hass, entry))
        await controller._save_slot(8, {0: raw})
    # Combining removes the standalone owners; the pair still owns both beds.
    for original, raw in ((left, -1), (right, -(2**31))):
        await async_remove_entry(hass, original)
        stored = await app_state_store(hass, original.data[CONF_ADDRESS]).async_slot(SLOT)
        assert stored["slots"] == {"8": {"0": raw}}
    # Unpair leaves surviving standalone owners, so parent removal preserves both.
    await async_remove_entry(hass, pair)
    # True pair removal deletes each physical record once no other owner exists.
    with patch.object(hass.config_entries, "async_entries", return_value=[pair]):
        await async_remove_entry(hass, pair)
    for address in (ADDRESS, right_data[CONF_ADDRESS]):
        assert await app_state_store(hass, address).async_slot(SLOT) == {}


async def test_failed_memory_write_keeps_the_previous_slot(hass):
    coordinator = AdjustableBedCoordinator(hass, _entry(hass))
    controller = await _controller(coordinator)
    await controller._save_slot(1, {0: 11})
    store = coordinator._app_state_store._store
    with (
        patch.object(store, "async_save", AsyncMock(side_effect=OSError("disk"))),
        pytest.raises(OSError),
    ):
        await controller._save_slot(1, {0: -1})
    assert controller.session.slots == {1: {0: 11}}
    assert (await stored_app_state(coordinator))["slots"] == {"1": {"0": 11}}


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


@pytest.mark.parametrize(
    "stored",
    [
        {"slots": {"1": {"0": 2**40}}},
        {"slots": {"9": {"0": 1}}},
        {"slots": {"1": {"x": 1}}},
        {"serial": True},
        {"serial": 2**31},
        {"names": [""] * 8},
    ],
)
async def test_corrupt_record_is_never_projected_to_bed(hass, stored):
    session = FsmRelaxSession(slots={1: {0: 11}}, serial=3)
    with pytest.raises(ValueError):
        session.restore(stored)
    assert session.slots == {1: {0: 11}} and session.serial == 3
    coordinator = AdjustableBedCoordinator(hass, _entry(hass))
    coordinator._app_state_store._store.async_load = AsyncMock(return_value={SLOT: stored})
    controller = await _controller(coordinator)
    assert controller.session.slots == {} and controller.session.serial is None


async def test_capability_reply_is_entry_data_written_once_per_change(hass):
    entry = _entry(hass)
    coordinator = AdjustableBedCoordinator(hass, entry)
    with patch.object(
        hass.config_entries, "async_update_entry", wraps=hass.config_entries.async_update_entry
    ) as update:
        for body in ("0202000008", "0202000008", "0206040004"):
            coordinator.remember_fsm_relax_capabilities(bytes.fromhex(body))
    assert update.call_count == 2
    assert entry.data["capabilities"] == {"fsm_relax": "0206040004"}
    controller = await _controller(coordinator)
    assert controller.key_count == 6 and controller.memory_slot_count == 4


@pytest.mark.parametrize("value", [None, 2, "zz", "0302000008", "02020000"])
def test_invalid_stored_capability_is_ignored(value):
    assert validate_capability_body(value) is None
