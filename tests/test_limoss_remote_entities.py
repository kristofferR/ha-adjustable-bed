"""Literal channel entities, editable slot-eight names and scoped removal."""

from unittest.mock import AsyncMock, MagicMock

from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed.button import (
    AdjustableBedButton,
    ControllerActionButton,
    _button_entities_for,
)
from custom_components.adjustable_bed.const import BED_TYPE_LIMOSS_REMOTE, DOMAIN
from custom_components.adjustable_bed.cover import _cover_entities_for
from custom_components.adjustable_bed.limoss_remote_state import LimossRemoteMemory
from tests.test_limoss_remote import make_controller


def runtime(controller, side=None):
    coordinator = MagicMock()
    coordinator.bed_type = BED_TYPE_LIMOSS_REMOTE
    coordinator.capability_controller = controller
    coordinator.controller = controller
    coordinator.has_massage = False
    coordinator.device_info = {}
    coordinator.entity_side = side
    coordinator.entity_unique_id.side_effect = lambda key: (
        f"target_{key}" + (f"_{side}" if side else "")
    )
    coordinator.entity_translation_key.side_effect = lambda key: key + (f"_{side}" if side else "")
    return coordinator


async def test_slot7_and8_real_button_callbacks_and_live_rename(hass):
    previous, current = make_controller(), make_controller()
    previous.memories.slots[8] = LimossRemoteMemory("Before", ((0, -1),))
    coordinator = runtime(previous)
    buttons = _button_entities_for(hass, coordinator)
    slots = {
        entity.entity_description.key: entity
        for entity in buttons
        if isinstance(entity, AdjustableBedButton)
    }
    assert {
        "preset_memory_7",
        "preset_memory_8",
        "program_memory_7",
        "program_memory_8",
    } <= slots.keys()
    recall, save = slots["preset_memory_8"], slots["program_memory_8"]
    assert recall.name == "Before" and save.name == "Save Before"
    await previous.rename_memory(8, "")
    assert recall.name == "" and save.name == "Save "
    current.preset_memory, current.program_memory = AsyncMock(), AsyncMock()

    async def execute(command, **kwargs):
        await command(current)

    coordinator.async_execute_controller_command = AsyncMock(side_effect=execute)
    await recall.async_press()
    await save.async_press()
    current.preset_memory.assert_awaited_once_with(8)
    current.program_memory.assert_awaited_once_with(8)
    previous.client.write_gatt_char.assert_not_called()


async def test_motor_cover_and_app_button_use_current_literal_action(hass):
    previous, current = make_controller(), make_controller()
    coordinator = runtime(previous)
    covers = _cover_entities_for(hass, coordinator)
    assert {cover.entity_description.key for cover in covers} == {"motor_1", "motor_2"}
    assert {cover.translation_key for cover in covers} == {
        "limoss_remote_motor_1",
        "limoss_remote_motor_2",
    }
    current.hold_control = AsyncMock()

    async def execute(command, **kwargs):
        await command(current)

    coordinator.async_execute_controller_command = AsyncMock(side_effect=execute)
    covers[0].hass = hass
    covers[0].entity_id = "cover.literal_channel"
    covers[0].async_write_ha_state = MagicMock()
    await covers[0].async_open_cover()
    current.hold_control.assert_awaited_once_with("motor_1_up", 1000)
    current.hold_control.reset_mock()
    buttons = _button_entities_for(hass, coordinator)
    action = next(
        entity
        for entity in buttons
        if isinstance(entity, ControllerActionButton)
        and entity.unique_id == "target_limoss_remote_motor_1_down"
    )
    await action.async_press()
    current.hold_control.assert_awaited_once_with("motor_1_down", 1000)
    assert action.translation_key == "remote_action"


async def test_removed_app_actions_are_pruned_only_for_same_physical_side(hass):
    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)
    registry = er.async_get(hass)
    stale = registry.async_get_or_create(
        "button", DOMAIN, "target_limoss_remote_light_left", config_entry=entry
    )
    opposite = registry.async_get_or_create(
        "button", DOMAIN, "target_limoss_remote_light_right", config_entry=entry
    )
    coordinator = runtime(make_controller(light=False), "left")
    coordinator.entry = entry
    _button_entities_for(hass, coordinator)
    assert registry.async_get(stale.entity_id) is None
    assert registry.async_get(opposite.entity_id) is not None


def test_other_controller_empty_memory_name_keeps_existing_translated_fallback():
    from custom_components.adjustable_bed.button import (
        BUTTON_DESCRIPTIONS,
        _discovered_memory_slot_name,
    )

    coordinator = runtime(make_controller())
    coordinator.bed_type = "octo"
    coordinator.controller = MagicMock(memory_slot_names=("",))
    description = next(row for row in BUTTON_DESCRIPTIONS if row.key == "preset_memory_1")
    assert _discovered_memory_slot_name(coordinator, description) is None
