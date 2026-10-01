"""Actual platform buttons preflight every physical memory slot before dispatch."""

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed.button import (
    BUTTON_DESCRIPTIONS,
    AdjustableBedButton,
    PairedBedCombinedButton,
    _combined_button_entities_for,
)
from custom_components.adjustable_bed.const import (
    BED_TYPE_SVANE,
    CONF_BED_TYPE,
    CONF_DISCONNECT_AFTER_COMMAND,
    CONF_PAIR_ID,
    CONF_PROTOCOL_VARIANT,
    DOMAIN,
    SIDE_LEFT,
    SIDE_RIGHT,
    SVANE_VARIANT_JMC,
    SVANE_VARIANT_MULTI,
)
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.paired_coordinator import (
    PairedBedCoordinator,
)
from tests.test_svane import make_controller, written


@pytest.fixture
async def mixed_pair(hass, request):
    multi_side = request.param
    children, controllers = {}, {}
    for side, address in [(SIDE_LEFT, "AA:BB:CC:DD:EE:01"), (SIDE_RIGHT, "AA:BB:CC:DD:EE:02")]:
        profile = "multi" if side == multi_side else "jmc"
        entry = MockConfigEntry(domain=DOMAIN, data={
            CONF_ADDRESS: address, CONF_NAME: side, CONF_BED_TYPE: BED_TYPE_SVANE,
            CONF_PROTOCOL_VARIANT: SVANE_VARIANT_MULTI if profile == "multi" else SVANE_VARIANT_JMC,
            CONF_DISCONNECT_AFTER_COMMAND: False,
        })
        entry.add_to_hass(hass)
        child = AdjustableBedCoordinator(hass, entry)
        controller = make_controller(profile)
        child._client = controller.client
        controller._coordinator = child
        controller._wait = AsyncMock(return_value=True)
        client = controller.client

        async def disconnect(current=client):
            current.is_connected = False
            return True

        client.disconnect = AsyncMock(side_effect=disconnect)
        child._controller = controller
        children[side], controllers[side] = child, controller
    parent_entry = MockConfigEntry(domain=DOMAIN, data={CONF_PAIR_ID: "mixed", CONF_NAME: "Pair"})
    parent_entry.add_to_hass(hass)
    pair = PairedBedCoordinator(hass, parent_entry, children)
    try:
        yield pair, children, controllers, multi_side
    finally:
        await pair.async_shutdown()


def memory_button(pair, children, slot):
    entities = _combined_button_entities_for(pair, list(children.values()))
    return next(entity for entity in entities if isinstance(entity, PairedBedCombinedButton)
                and entity.entity_description.key == f"preset_memory_{slot}")


@pytest.mark.parametrize("mixed_pair", [SIDE_LEFT, SIDE_RIGHT], indirect=True)
@pytest.mark.parametrize("slot", [1, 2])
async def test_actual_combined_memory_button_rejects_unsaved_side_before_any_dispatch(mixed_pair, slot):
    pair, children, controllers, multi_side = mixed_pair
    assert slot not in controllers[multi_side].session.multi_slots
    button = memory_button(pair, children, slot)
    with (
        patch.object(pair, "async_execute_controller_command", wraps=pair.async_execute_controller_command) as dispatch,
        pytest.raises(ValueError, match="save this local slot"),
    ):
        await button.async_press()
    dispatch.assert_not_awaited()
    for controller in controllers.values():
        assert written(controller) == []
        controller.client.write_gatt_char.assert_not_awaited()


@pytest.mark.parametrize("mixed_pair", [SIDE_LEFT, SIDE_RIGHT], indirect=True)
@pytest.mark.parametrize("slot", [1, 2])
async def test_actual_combined_memory_button_recalls_both_ready_physical_slots(mixed_pair, slot):
    pair, children, controllers, multi_side = mixed_pair
    controllers[multi_side].session.multi_slots[slot] = (b"opaque head", b"opaque feet")
    await memory_button(pair, children, slot).async_press()
    for side, controller in controllers.items():
        packets = [packet for _, _, packet in written(controller)]
        assert packets == ([b"opaque head".hex(), b"opaque feet".hex()] if side == multi_side else [
            "100481388113" if slot == 1 else "100482738204"
        ])
        assert not controller._started
        assert not children[side]._command_lock.locked()


@pytest.mark.parametrize("mixed_pair", [SIDE_LEFT, SIDE_RIGHT], indirect=True)
async def test_invalid_combined_slot_rejects_before_ready_sibling_dispatch(mixed_pair):
    pair, children, controllers, multi_side = mixed_pair
    controllers[multi_side].session.multi_slots[1] = (b"head", b"")
    with (
        patch.object(pair, "async_execute_controller_command", wraps=pair.async_execute_controller_command) as dispatch,
        pytest.raises(ValueError, match="nonempty raw axes"),
    ):
        await memory_button(pair, children, 1).async_press()
    dispatch.assert_not_awaited()
    assert all(not written(controller) for controller in controllers.values())


@pytest.mark.parametrize("mixed_pair", [SIDE_LEFT], indirect=True)
async def test_existing_button_fails_closed_when_one_side_has_no_capability_source(mixed_pair):
    pair, children, controllers, multi_side = mixed_pair
    controllers[multi_side].session.multi_slots[1] = (b"head", b"feet")
    button = memory_button(pair, children, 1)
    children[SIDE_RIGHT]._controller = None
    children[SIDE_RIGHT]._offline_controller = None
    with (
        patch.object(pair, "async_execute_controller_command", wraps=pair.async_execute_controller_command) as dispatch,
        pytest.raises(ValueError, match="unavailable device"),
    ):
        await button.async_press()
    dispatch.assert_not_awaited()
    assert all(not written(controller) for controller in controllers.values())


@pytest.mark.parametrize("mixed_pair", [SIDE_LEFT], indirect=True)
async def test_offline_slot_preflight_does_not_open_either_connection(mixed_pair):
    pair, children, controllers, _ = mixed_pair
    button = memory_button(pair, children, 1)
    for child in children.values():
        child._offline_controller = child._controller
        child._controller = None
    with (
        patch.object(pair, "async_execute_controller_command", wraps=pair.async_execute_controller_command) as dispatch,
        pytest.raises(ValueError, match="save this local slot"),
    ):
        await button.async_press()
    dispatch.assert_not_awaited()
    assert all(not written(controller) for controller in controllers.values())


@pytest.mark.parametrize("mixed_pair", [SIDE_LEFT], indirect=True)
async def test_combined_save_works_before_either_local_slot_is_saved(mixed_pair):
    pair, children, controllers, multi_side = mixed_pair
    description = next(d for d in BUTTON_DESCRIPTIONS if d.key == "program_memory_1")
    button = PairedBedCombinedButton(pair, description)
    await button.async_press()
    assert controllers[multi_side].session.multi_slots[1] == (bytes.fromhex("8138"),) * 2
    other = SIDE_RIGHT if multi_side == SIDE_LEFT else SIDE_LEFT
    assert controllers[other].session.jmc_slots[0] == bytes.fromhex("81388113")
    assert all(not written(controller) for controller in controllers.values())


@pytest.mark.parametrize("mixed_pair", [SIDE_LEFT], indirect=True)
async def test_standalone_memory_button_still_uses_its_own_controller(mixed_pair):
    _, children, controllers, _ = mixed_pair
    description = next(d for d in BUTTON_DESCRIPTIONS if d.key == "preset_memory_2")
    await AdjustableBedButton(children[SIDE_RIGHT], description).async_press()
    assert [packet for _, _, packet in written(controllers[SIDE_RIGHT])] == ["100482738204"]
    assert not written(controllers[SIDE_LEFT])
