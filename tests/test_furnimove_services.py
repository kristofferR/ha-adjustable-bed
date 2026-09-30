"""App row services validate every target and retain exact consumer semantics."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.exceptions import ServiceValidationError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed.const import BED_TYPE_FURNIMOVE, DOMAIN, SIDE_BOTH
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.services import async_register_services
from tests.test_furnimove import GAP_NAME, WRITE, char, fast_controller, written


async def target(handset="82417", *, bed_type=BED_TYPE_FURNIMOVE, entry=None, rename=False):
    controller = await fast_controller(handset, characteristics=[char(WRITE), char(GAP_NAME)] if rename else None)
    coordinator = MagicMock(spec=AdjustableBedCoordinator)
    coordinator.name = "Bed"
    coordinator.bed_type = bed_type
    coordinator.entry = entry or SimpleNamespace(data={})
    coordinator.capability_controller = controller
    coordinator.async_ensure_connected = AsyncMock(return_value=True)

    async def execute(command, **kwargs):
        await command(controller)

    coordinator.async_execute_controller_command = AsyncMock(side_effect=execute)
    coordinator.async_set_furnimove_massage_duration = AsyncMock(side_effect=controller.set_massage_timer)
    return coordinator, controller


async def invoke(hass, targets, service, data):
    await async_register_services(hass)
    with patch("custom_components.adjustable_bed.services._resolve_sided_targets",
               return_value=([(value, SIDE_BOTH) for value in targets], [])):
        await hass.services.async_call(DOMAIN, service, {"device_id": "bed", **data}, blocking=True)


async def test_action_service_emits_selected_row_and_its_proven_release(hass):
    coordinator, controller = await target()
    row = next(spec for spec in controller.furnimove_action_specs if spec.name == "M2Out")
    await invoke(hass, [coordinator], "furnimove_action", {"row_index": row.row_index, "duration": .1})
    assert written(controller) == ["040200000001", "040200000000", "040200000000"]
    kwargs = coordinator.async_execute_controller_command.await_args.kwargs
    assert kwargs["cancel_running"] is True and kwargs["resource"] == "*"


@pytest.mark.parametrize("invalid", ["different_protocol", "different_row_layout"])
async def test_later_target_is_validated_before_first_target_moves(hass, invalid):
    first, controller = await target("12234")
    second, other = await target("00000", bed_type="okin_cst" if invalid == "different_protocol" else BED_TYPE_FURNIMOVE)
    if invalid == "different_protocol":
        row_index = 0
    else:
        row_index = max(spec.row_index for spec in controller.furnimove_action_specs)
    with pytest.raises(ServiceValidationError):
        await invoke(hass, [first, second], "furnimove_action", {"row_index": row_index})
    first.async_execute_controller_command.assert_not_awaited()
    second.async_execute_controller_command.assert_not_awaited()
    assert not written(controller) and not written(other)


@pytest.mark.parametrize("paired", [False, True])
async def test_same_row_with_different_actions_rejected_before_any_target_moves(hass, paired):
    from custom_components.adjustable_bed.const import CONF_PAIR_ID, SIDE_LEFT, SIDE_RIGHT
    from custom_components.adjustable_bed.paired_coordinator import PairedBedCoordinator

    first, controller = await target("00000")
    second, other = await target("82417")
    targets = [first, second]
    if paired:
        targets = [PairedBedCoordinator(
            hass, SimpleNamespace(data={CONF_PAIR_ID: "furnimove-pair"}),
            {SIDE_LEFT: first, SIDE_RIGHT: second},
        )]
    with pytest.raises(ServiceValidationError, match="different actions"):
        await invoke(hass, targets, "furnimove_action", {"row_index": 1, "duration": .1})
    first.async_execute_controller_command.assert_not_awaited()
    second.async_execute_controller_command.assert_not_awaited()
    assert not written(controller) and not written(other)


async def test_matching_actions_on_different_handsets_can_target_both_devices(hass):
    first, controller = await target("82417")
    second, other = await target("90167")
    await invoke(hass, [first, second], "furnimove_action", {"row_index": 1, "duration": .1})
    assert written(controller) and written(other)
    first.async_execute_controller_command.assert_awaited_once()
    second.async_execute_controller_command.assert_awaited_once()


async def test_missing_massage_program_on_later_target_rejected_before_any_write(hass):
    first, controller = await target("12234")
    second, other = await target("90167")
    with pytest.raises(ServiceValidationError, match="absent"):
        await invoke(hass, [first, second], "furnimove_massage_program", {"program": 1})
    first.async_execute_controller_command.assert_not_awaited()
    second.async_execute_controller_command.assert_not_awaited()
    assert not written(controller) and not written(other)


async def test_advisory_duration_accepts_ui_selection_without_wire_or_preemption(hass):
    coordinator, controller = await target("12234")
    await invoke(hass, [coordinator], "furnimove_massage_duration", {"minutes": "20"})
    assert controller.furnimove_local_state["duration_minutes"] == 20
    assert not written(controller)
    coordinator.async_execute_controller_command.assert_not_awaited()
    coordinator.async_ensure_connected.assert_not_awaited()
    coordinator.async_set_furnimove_massage_duration.assert_awaited_once_with(20)


async def test_advisory_duration_updates_disconnected_receiver_and_survives_reconnect(hass):
    from custom_components.adjustable_bed.beds.furnimove import FurniMoveController
    from custom_components.adjustable_bed.const import CONF_FURNIMOVE_REMOTE
    from tests.test_furnimove_connection import coordinator as make_coordinator

    coordinator = make_coordinator(hass)
    hass.config_entries.async_update_entry(
        coordinator.entry, data={**coordinator.entry.data, CONF_FURNIMOVE_REMOTE: "12234"}
    )
    coordinator = AdjustableBedCoordinator(hass, coordinator.entry)
    coordinator.async_ensure_connected = AsyncMock(return_value=False)
    await invoke(hass, [coordinator], "furnimove_massage_duration", {"minutes": "20"})
    assert coordinator.controller is None and coordinator.client is None
    assert coordinator.capability_controller.furnimove_local_state == {"duration_minutes": 20}
    coordinator.async_ensure_connected.assert_not_awaited()
    coordinator._controller = FurniMoveController(coordinator, handset_id="12234")
    await coordinator._async_restore_furnimove_local_state()
    assert coordinator.controller.furnimove_local_state == {"duration_minutes": 20}


async def test_advisory_duration_validates_all_profiles_before_updating_any(hass):
    first, controller = await target("12234")
    second, _ = await target("00000")
    with pytest.raises(ServiceValidationError, match="no supported local massage duration"):
        await invoke(hass, [first, second], "furnimove_massage_duration", {"minutes": 20})
    first.async_set_furnimove_massage_duration.assert_not_awaited()
    assert controller.furnimove_local_state == {"duration_minutes": 15}


async def test_rename_connects_for_live_role_then_preserves_wire_text_and_identity(hass):
    entry = MockConfigEntry(domain=DOMAIN, title="Bed", unique_id="original", data={"name": "Bed"})
    entry.add_to_hass(hass)
    coordinator, controller = await target(entry=entry, rename=True)
    await invoke(hass, [coordinator], "furnimove_rename", {"name": "  New name  "})
    coordinator.async_ensure_connected.assert_awaited_once()
    assert controller.client.write_gatt_char.await_args.args[1] == b"  New name  "
    assert entry.title == "New name" and entry.unique_id == "original"
    assert entry.data["name"] == "New name"


async def test_duplicate_or_current_rename_rejected_before_any_connection(hass):
    entry = MockConfigEntry(domain=DOMAIN, title="Taken", data={})
    entry.add_to_hass(hass)
    coordinator, controller = await target(rename=True)
    for name in (" bed ", " TAKEN "):
        with pytest.raises(ServiceValidationError, match="unique"):
            await invoke(hass, [coordinator], "furnimove_rename", {"name": name})
    coordinator.async_ensure_connected.assert_not_awaited()
    assert not written(controller)


async def test_unsupported_second_axis_rejected_before_any_wire_write(hass):
    coordinator, controller = await target("00000")
    with pytest.raises(ServiceValidationError, match="axes"):
        await invoke(hass, [coordinator], "furnimove_move_simultaneously", {
            "first_motor": "back", "second_motor": "head",
            "first_direction": "up", "second_direction": "down", "duration_ms": 100,
        })
    assert not written(controller)
