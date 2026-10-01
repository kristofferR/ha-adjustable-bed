"""Exact app entity ranges, observed feedback and child-only custom surfaces."""

from unittest.mock import AsyncMock, patch

from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.button import _button_entities_for
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.cover import _cover_entities_for
from custom_components.adjustable_bed.light import _light_entities_for
from custom_components.adjustable_bed.number import _number_entities_for
from custom_components.adjustable_bed.paired_coordinator import (
    PairedBedCoordinator,
    entity_runtimes,
)
from custom_components.adjustable_bed.select import _select_entities_for
from custom_components.adjustable_bed.sensor import _sensor_entities_for
from tests.test_malouf_app_entities import configure_entity_runtime
from tests.test_starcode_abm5_4 import make_controller


async def test_real_two_address_entity_views_keep_feedback_and_setters_on_their_child(hass):
    children = {}
    for side, selector, address in (
        ("left", "BOX25", "AA:BB:CC:DD:EE:01"),
        ("right", "BOX25_STAR", "AA:BB:CC:DD:EE:02"),
    ):
        entry = MockConfigEntry(
            domain=const.DOMAIN,
            data={
                CONF_ADDRESS: address,
                CONF_NAME: side,
                const.CONF_BED_TYPE: const.BED_TYPE_STARCODE_ABM5_4,
                const.CONF_HAS_MASSAGE: True,
                const.CONF_STARCODE_COMMAND_SELECTOR: selector,
                const.CONF_STARCODE_UI_SELECTOR: selector,
            },
        )
        entry.add_to_hass(hass)
        child = AdjustableBedCoordinator(hass, entry)
        controller = make_controller(selector)
        child._client = controller.client
        child._controller = controller
        controller._coordinator = child
        controller._owner_address = address
        controller._spawn = lambda operation: None

        async def execute(command, *, target=controller, **kwargs):
            await command(target)

        child.async_execute_controller_command = AsyncMock(side_effect=execute)
        children[side] = child
    parent_entry = MockConfigEntry(
        domain=const.DOMAIN,
        data={const.CONF_PAIR_ID: "app-pair", CONF_NAME: "Pair"},
    )
    parent_entry.add_to_hass(hass)
    parent = PairedBedCoordinator(hass, parent_entry, children)
    dr.async_get(hass).async_get_or_create(
        config_entry_id=parent_entry.entry_id, **parent.device_info
    )
    views = {view.entity_side: view for view in entity_runtimes(parent)}
    timers = {
        side: next(
            entity
            for entity in _select_entities_for(hass, view)
            if entity.translation_key == "starcode_abm5_4_massage_timer"
        )
        for side, view in views.items()
    }
    levels = {
        side: next(
            entity
            for entity in _number_entities_for(hass, view)
            if entity.translation_key == "starcode_abm5_4_light_level"
        )
        for side, view in views.items()
    }
    assert timers["left"].unique_id != timers["right"].unique_id
    assert levels["left"].unique_id != levels["right"].unique_id
    packet = bytearray.fromhex("a50b0000006400040300000000000000")
    packet[14] = 0x41
    left_controller = children["left"].controller
    right_controller = children["right"].controller
    left_controller._notification(
        left_controller.client, 0, left_controller.client.services[0].characteristics[1], packet
    )
    assert timers["left"].current_option == "10"
    assert timers["right"].current_option is None
    assert levels["left"].native_value == 4
    right_packet = bytearray(packet)
    right_packet[4:6] = (900).to_bytes(2, "big")
    right_packet[14] = 0x21
    right_controller._notification(
        right_controller.client,
        0,
        right_controller.client.services[0].characteristics[1],
        right_packet,
    )
    assert timers["right"].current_option == "20"
    assert levels["right"].native_value == 2
    assert timers["left"].current_option == "10"
    assert levels["left"].native_value == 4
    with patch(
        "custom_components.adjustable_bed.beds.starcode_abm5_4.asyncio.sleep",
        new_callable=AsyncMock,
    ):
        await timers["right"].async_select_option("10")
        await levels["left"].async_set_native_value(6)
    assert [
        call.args[1].hex() for call in right_controller.client.write_gatt_char.await_args_list
    ] == [
        "5ae00407010000a5",
        "5a010310300fa5",
        "5ab000a5",
    ]
    assert [
        call.args[1].hex() for call in left_controller.client.write_gatt_char.await_args_list
    ] == [
        "04e000060000",
    ]
    assert left_controller.command_selector == "BOX25"
    assert right_controller.command_selector == "BOX25_STAR"
    assert levels["right"].native_value == 2
    assert all(
        children[side].async_execute_controller_command.await_count == 1 for side in children
    )


async def test_actual_entity_catalog_ranges_names_and_locked_dispatch(hass):
    c = make_controller()
    runtime = configure_entity_runtime(hass, c, const.BED_TYPE_STARCODE_ABM5_4)
    hass.config_entries.async_update_entry(
        runtime.entry, data={**runtime.entry.data, const.CONF_HAS_MASSAGE: True}
    )
    numbers = _number_entities_for(hass, runtime)
    app_numbers = [n for n in numbers if n.translation_key == "starcode_abm5_4_light_level"]
    assert len(app_numbers) == 1
    assert (
        app_numbers[0].native_min_value,
        app_numbers[0].native_max_value,
        app_numbers[0].native_step,
    ) == (1, 6, 1)
    assert not any(n.translation_key.endswith("_position") for n in numbers)
    selects = _select_entities_for(hass, runtime)
    timer = next(s for s in selects if s.translation_key == "starcode_abm5_4_massage_timer")
    assert timer.options == ["10", "20", "30"]
    c.set_app_timer = AsyncMock()
    c.set_app_brightness = AsyncMock()

    async def execute(action, **kwargs):
        await action(c)

    runtime.async_execute_controller_command = AsyncMock(side_effect=execute)
    await timer.async_select_option("20")
    await app_numbers[0].async_set_native_value(4)
    c.set_app_timer.assert_awaited_once_with("20")
    c.set_app_brightness.assert_awaited_once_with(4)
    assert runtime.async_execute_controller_command.call_count == 2
    buttons = _button_entities_for(hass, runtime)
    assert any(b.translation_key == "starcode_abm5_4_use_detected_profile" for b in buttons)
    assert not any(b.translation_key in ("preset_memory_2", "program_memory_2") for b in buttons)
    covers = _cover_entities_for(hass, runtime)
    assert {e.translation_key for e in covers} == {"back", "legs"}
    lights = _light_entities_for(hass, runtime)
    assert len(lights) == 1 and lights[0]._feedback_only
    assert c.get_light_state()["is_on"] is None
    sensors = _sensor_entities_for(hass, runtime)
    assert {s.translation_key for s in sensors} >= {
        "starcode_abm5_4_raw_b",
        "starcode_abm5_4_wave",
        "starcode_abm5_4_head_intensity",
    }
