"""Offline paired names, rendered options errors and physical store ownership."""

from collections.abc import Iterable
from unittest.mock import patch

import pytest
from homeassistant.components.button import ButtonEntity
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.translation import async_get_translations
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed import async_remove_entry, button, const
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator, ChildEntryView
from custom_components.adjustable_bed.fsm_relax_state import FsmRelaxState, get_fsm_relax_state
from custom_components.adjustable_bed.paired_coordinator import PairedBedCoordinator
from custom_components.adjustable_bed.pairing import build_pair_entry_data


async def test_sequential_pair_offline_memory_buttons_keep_each_sides_eight_names(
    hass: HomeAssistant,
) -> None:
    children_data = [
        {CONF_ADDRESS: address, const.CONF_BED_TYPE: const.BED_TYPE_FSM_RELAX,
         const.CONF_FSM_RELAX_MEMORY_NAMES: [f"{side} {slot}" for slot in range(1, 9)]}
        for side, address in (("Left", "AA:BB:CC:DD:EE:FF"), ("Right", "11:22:33:44:55:66"))
    ]
    entry = MockConfigEntry(domain=const.DOMAIN, data=build_pair_entry_data(*children_data, name="Pair"))
    entry.add_to_hass(hass)
    children = {
        side: AdjustableBedCoordinator(hass, ChildEntryView(entry, child, lambda _: None))
        for side, child in zip(("left", "right"), entry.data[const.CONF_PAIR_CHILDREN], strict=True)
    }
    pair = PairedBedCoordinator(hass, entry, children)
    dr.async_get(hass).async_get_or_create(config_entry_id=entry.entry_id, **pair.device_info)
    hass.data[const.DOMAIN] = {entry.entry_id: pair}
    for child in children.values():
        state = get_fsm_relax_state(hass, entry.entry_id, child.address)
        await state.async_save_capabilities(bytes.fromhex("0204000008"))
        await child.async_prime_offline_controller()
        assert child.controller is None and child.capability_controller is not None
    entities: list[ButtonEntity] = []

    def collect(added: Iterable[ButtonEntity], _update_before_add: bool = False) -> None:
        entities.extend(added)

    await button.async_setup_entry(hass, entry, collect)
    memories = [entity for entity in entities if isinstance(entity, button.AdjustableBedButton)
                and entity.entity_description.memory_slot is not None]
    assert len(memories) == 32
    for entity in memories:
        side = entity._coordinator.entity_side
        description = entity.entity_description
        assert side in ("left", "right")
        expected = f"{side.title()} {description.memory_slot}"
        assert entity._attr_name == (f"Save {expected}" if description.is_program_button else expected)


async def test_public_options_invalid_names_has_renderable_explanatory_translation(
    hass: HomeAssistant, enable_custom_integrations: None,
) -> None:
    entry = MockConfigEntry(domain=const.DOMAIN, data={
        CONF_ADDRESS: "AA:BB:CC:DD:EE:FF", const.CONF_BED_TYPE: const.BED_TYPE_FSM_RELAX,
        const.CONF_FSM_RELAX_MEMORY_NAMES: ["Sleep"] + [""] * 7,
    })
    entry.add_to_hass(hass)
    menu = await hass.config_entries.options.async_init(entry.entry_id)
    shown = await hass.config_entries.options.async_configure(
        menu["flow_id"], {"next_step_id": "settings"},
    )
    result = await hass.config_entries.options.async_configure(
        shown["flow_id"], {const.CONF_FSM_RELAX_MEMORY_NAMES: [""] * 7},
    )
    assert result["errors"] == {"base": "fsm_relax_invalid"}
    translations = await async_get_translations(hass, "en", "options", {const.DOMAIN})
    message = translations[f"component.{const.DOMAIN}.options.error.fsm_relax_invalid"]
    assert "exactly eight memory names" in message
    assert entry.data[const.CONF_FSM_RELAX_MEMORY_NAMES] == ["Sleep"] + [""] * 7
    hass.config_entries.options.async_abort(result["flow_id"])


@pytest.mark.parametrize("paired", (False, True))
@pytest.mark.parametrize("retained_type", (None, const.BED_TYPE_FSM_RELAX, const.BED_TYPE_LIMOSS))
async def test_protocol_changed_entry_removal_cleans_only_unowned_physical_stores(
    hass: HomeAssistant, paired: bool, retained_type: str | None,
) -> None:
    addresses = ["AA:BB:CC:DD:EE:FF", "11:22:33:44:55:66"] if paired else ["AA:BB:CC:DD:EE:FF"]
    records = [{CONF_ADDRESS: address, const.CONF_BED_TYPE: const.BED_TYPE_FSM_RELAX} for address in addresses]
    entry = MockConfigEntry(domain=const.DOMAIN, data=build_pair_entry_data(*records, name="Pair") if paired else records[0])
    entry.add_to_hass(hass)
    states = []
    for address in addresses:
        state = get_fsm_relax_state(hass, entry.entry_id, address)
        await state.async_save_slot(8, {0: -1})
        await state.async_set_names(["Sleep"] + [""] * 7)
        await state.async_save_capabilities(bytes.fromhex("0204000008"))
        await state.async_save_serial(-1)
        states.append(state)
    if retained_type is not None:
        retained = MockConfigEntry(domain=const.DOMAIN, data={CONF_ADDRESS: addresses[0].lower(), const.CONF_BED_TYPE: retained_type})
        retained.add_to_hass(hass)
    unrelated = get_fsm_relax_state(hass, "unrelated-owner", "22:33:44:55:66:77")
    await unrelated.async_save_slot(1, {0: 77})
    changed = {**entry.data, const.CONF_BED_TYPE: const.BED_TYPE_LIMOSS}
    if paired:
        changed[const.CONF_PAIR_CHILDREN] = [
            {**child, const.CONF_BED_TYPE: const.BED_TYPE_LIMOSS}
            for child in entry.data[const.CONF_PAIR_CHILDREN]
        ]
    hass.config_entries.async_update_entry(entry, data=changed)
    with patch.object(hass.config_entries, "async_reload"):
        await async_remove_entry(hass, entry)
    for index, address in enumerate(addresses):
        after = FsmRelaxState(hass, "later-owner", address)
        await after.async_load()
        if index == 0 and retained_type is not None:
            assert after.slots == {8: {0: -1}} and states[index].slots == after.slots
            assert after.names[0] == "Sleep" and after.serial == -1
        else:
            assert after.slots == {} and states[index].slots == {}
            assert after.capability_body is None and after.serial is None
            assert after.names == tuple(f"M{i}" for i in range(1, 9))
    assert unrelated.slots == {1: {0: 77}}
