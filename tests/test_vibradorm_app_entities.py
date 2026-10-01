"""App metadata and sync sensors reconcile only the configured physical side."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed.const import (
    BED_TYPE_DIAGNOSTIC,
    BED_TYPE_VIBRADORM_APP,
    CONF_BED_TYPE,
    CONF_PAIR_ID,
    CONF_VIBRADORM_APP_PROFILE,
    CONF_VIBRADORM_CONTROL_TYPE,
    CONF_VIBRADORM_FLOOR_LIGHT,
    CONF_VIBRADORM_LIGHT_EXTENSION,
    CONF_VIBRADORM_RESTORED,
    CONF_VIBRADORM_RGB,
    DOMAIN,
)
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.light import _light_entities_for
from custom_components.adjustable_bed.number import _number_entities_for
from custom_components.adjustable_bed.paired_coordinator import (
    PairedBedCoordinator,
    PairedSideProxy,
)
from custom_components.adjustable_bed.select import _select_entities_for
from custom_components.adjustable_bed.sensor import _sensor_entities_for
from custom_components.adjustable_bed.switch import _switch_entities_for
from tests.conftest import make_controller_mock
from tests.test_malouf_app_entities import configure_entity_runtime
from tests.test_paired_coordinator import RecordingChild
from tests.test_vibradorm_app import make_controller, written


@pytest.mark.parametrize(
    ("control", "app"),
    [(None, "werkmeister"), (2, "caresse"), (3, "caresse"), (5, "werkmeister"), (7, "werkmeister")],
)
async def test_profile_switch_reconciles_metadata_and_sync_for_only_its_side(hass, control, app):
    controller = (
        make_controller(control, app=app)
        if control is not None
        else make_controller_mock(
            controller_state_sensor_specs=(),
            stale_controller_state_sensor_entity_keys=frozenset(),
            position_number_specs=(),
        )
    )
    runtime = configure_entity_runtime(
        hass, controller, BED_TYPE_VIBRADORM_APP if control else BED_TYPE_DIAGNOSTIC
    )
    registry = er.async_get(hass)
    keys = {
        "vibradorm_app_model",
        "vibradorm_app_firmware",
        "vibradorm_app_software",
        "vibradorm_app_main_firmware_article",
        "vibradorm_app_sync_observed",
    }
    old = {
        key: registry.async_get_or_create(
            "sensor", DOMAIN, f"bed_{key}_left", config_entry=runtime.entry
        )
        for key in keys
    }
    other_side = registry.async_get_or_create(
        "sensor", DOMAIN, "bed_vibradorm_app_sync_observed_right", config_entry=runtime.entry
    )
    unrelated = registry.async_get_or_create(
        "sensor", DOMAIN, "bed_unrelated_left", config_entry=runtime.entry
    )
    other_platform = registry.async_get_or_create(
        "sensor",
        "another_integration",
        "bed_vibradorm_app_sync_observed_left",
        config_entry=runtime.entry,
    )
    entities = _sensor_entities_for(hass, runtime)
    active = {spec.key for spec in controller.controller_state_sensor_specs}
    assert ("vibradorm_app_main_firmware_article" in active) is (control in (5, 7))
    assert {entity._spec.key for entity in entities if hasattr(entity, "_spec")} == active
    for key, row in old.items():
        assert (registry.async_get(row.entity_id) is not None) == (key in active)
    for row in (other_side, unrelated, other_platform):
        assert registry.async_get(row.entity_id) is not None


async def floor_runtime(hass, app="caresse", control=2, *, floor=True, extension=False, rgb=False):
    seed = make_controller(control, app=app)
    runtime = seed._coordinator
    runtime.hass = hass
    runtime.bed_type = BED_TYPE_VIBRADORM_APP
    runtime.entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_BED_TYPE: BED_TYPE_VIBRADORM_APP,
            CONF_VIBRADORM_APP_PROFILE: app,
            CONF_VIBRADORM_CONTROL_TYPE: str(control),
            CONF_VIBRADORM_RESTORED: app == "caresse"
            and (floor or rgb or control != 2 or extension),
            CONF_VIBRADORM_FLOOR_LIGHT: floor,
            CONF_VIBRADORM_LIGHT_EXTENSION: extension,
            CONF_VIBRADORM_RGB: rgb,
        },
    )
    runtime.entry.add_to_hass(hass)
    controller = await create_controller(runtime, BED_TYPE_VIBRADORM_APP, "auto", runtime.client)
    runtime.controller = runtime.capability_controller = controller
    runtime.entity_side = None
    runtime.device_info = {}
    runtime.has_massage = False
    runtime.disable_angle_sensing = True
    runtime.controller_state = {}
    runtime.entity_unique_id.side_effect = lambda key: f"{runtime.entry.entry_id}_{key}"
    runtime.entity_translation_key.side_effect = lambda key: key
    callbacks = []

    def register(callback):
        callbacks.append(callback)
        return lambda: callbacks.remove(callback)

    def publish(updates):
        runtime.controller_state.update(updates)
        for callback in tuple(callbacks):
            callback(updates)

    runtime.register_controller_state_callback.side_effect = register
    runtime.handle_controller_state_updates.side_effect = publish
    runtime.handle_controller_state_update.side_effect = lambda key, value: publish({key: value})
    lock = asyncio.Lock()

    async def execute(command, **kwargs):
        async with lock:
            await command(runtime.controller)

    runtime.async_execute_controller_command = AsyncMock(side_effect=execute)
    return runtime, controller


async def add_public_floor_entities(hass, runtime):
    switches = _switch_entities_for(hass, runtime)
    switch = next(
        entity for entity in switches if entity.entity_description.key == "under_bed_lights"
    )
    number = next(
        entity
        for entity in _number_entities_for(hass, runtime)
        if entity.entity_description.key == "light_level"
    )
    assert _light_entities_for(hass, runtime) == []
    for entity in (switch, number):
        entity.hass = hass
        entity.async_write_ha_state = MagicMock()
        await entity.async_added_to_hass()
    return switch, number


@pytest.mark.parametrize(("packet", "observed", "state"), [
    ("203f40", True, "on"),
    ("203f00", False, "off"),
])
async def test_sync_sensor_publishes_translatable_state_without_changing_parser(hass, packet, observed, state):
    runtime, controller = await floor_runtime(hass, app="werkmeister", control=7)
    sensor = next(entity for entity in _sensor_entities_for(hass, runtime)
                  if entity._spec.key == "vibradorm_app_sync_observed")
    sensor.hass = hass
    sensor.async_write_ha_state = MagicMock()
    await sensor.async_added_to_hass()
    assert sensor.native_value is None
    controller._notification(MagicMock(uuid="response"), bytearray.fromhex(packet))
    assert controller._sync_observed is observed
    assert controller.protocol_diagnostics["sync_observed"] is observed
    assert sensor.native_value == state
    sensor.async_write_ha_state.assert_called_once()
    await sensor.async_will_remove_from_hass()


@pytest.mark.parametrize(
    "app,control,extension,frames",
    [
        ("caresse", 2, False, ["200000", "000000", "200000", "200000", "000000", "000000"]),
        (
            "caresse",
            2,
            True,
            ["00110100", "80110000", "00110100", "80110100", "00110000", "80110000"],
        ),
        (
            "caresse",
            7,
            False,
            ["00112000", "80110000", "00112000", "80112000", "00110000", "80110000"],
        ),
        (
            "caresse",
            7,
            True,
            ["10110100", "90110000", "10110100", "90110100", "10110000", "90110000"],
        ),
        (
            "werkmeister",
            5,
            False,
            ["00112000", "80110000", "00112000", "80112000", "00110000", "80110000"],
        ),
        (
            "werkmeister",
            7,
            False,
            ["00112000", "80110000", "00112000", "80112000", "00110000", "80110000"],
        ),
    ],
)
async def test_actual_floor_switch_and_slider_remember_one_repeat_exact_headers(
    hass, app, control, extension, frames
):
    runtime, controller = await floor_runtime(hass, app, control, extension=extension)
    switch, number = await add_public_floor_entities(hass, runtime)
    assert switch.is_on is None
    assert switch.assumed_state
    assert number.native_value is None
    assert (number.native_min_value, number.native_max_value) == (1, 6 if extension else 8)
    await number.async_set_native_value(1)
    assert switch.is_on is True and number.native_value == 1
    await switch.async_turn_off()
    assert switch.is_on is False and number.native_value == 0
    await switch.async_turn_on()
    assert switch.is_on is True and number.native_value == 1
    await switch.async_turn_on()
    assert switch.is_on is True and number.native_value == 1
    await switch.async_turn_off()
    await switch.async_turn_off()
    assert switch.is_on is False and number.native_value == 0
    assert written(controller) == frames
    assert controller._floor_default == 1
    assert controller._toggle == 0x8000
    for entity in (switch, number):
        await entity.async_will_remove_from_hass()


@pytest.mark.parametrize("floor,rgb", [(False, False), (True, False), (False, True), (True, True)])
async def test_actual_floor_gate_is_independent_of_restored_mood_rgb(hass, floor, rgb):
    runtime, controller = await floor_runtime(hass, floor=floor, rgb=rgb)
    switches = _switch_entities_for(hass, runtime)
    numbers = _number_entities_for(hass, runtime)
    assert any(entity.entity_description.key == "under_bed_lights" for entity in switches) is floor
    assert any(entity.entity_description.key == "light_level" for entity in numbers) is floor
    assert _light_entities_for(hass, runtime) == []
    assert bool(controller.controller_select_specs) is rgb
    assert not controller.supports_light_color_control
    assert not controller.supports_light_state_feedback


@pytest.mark.parametrize("control", [2, 7])
async def test_floor_capability_loss_removes_only_its_number_registry_entry(hass, control):
    runtime, _ = await floor_runtime(hass, control=control, floor=False)
    registry = er.async_get(hass)
    unique_id = runtime.entity_unique_id("light_level")
    stale = registry.async_get_or_create("number", DOMAIN, unique_id, config_entry=runtime.entry)
    other_side = registry.async_get_or_create(
        "number", DOMAIN, unique_id + "_right", config_entry=runtime.entry
    )
    other_platform = registry.async_get_or_create(
        "number", "another_integration", unique_id, config_entry=runtime.entry
    )
    unrelated = registry.async_get_or_create(
        "number", DOMAIN, runtime.entity_unique_id("unrelated"), config_entry=runtime.entry
    )
    numbers = _number_entities_for(hass, runtime)
    assert not any(entity.entity_description.key == "light_level" for entity in numbers)
    assert registry.async_get(stale.entity_id) is None
    for kept in (other_side, other_platform, unrelated):
        assert registry.async_get(kept.entity_id) is not None


async def test_failed_public_floor_off_retains_last_publication_and_source_intent(hass):
    runtime, controller = await floor_runtime(hass, control=7)
    switch, number = await add_public_floor_entities(hass, runtime)
    await number.async_set_native_value(1)
    controller.client.write_gatt_char.side_effect = OSError("failed floor write")
    with pytest.raises(OSError, match="failed floor write"):
        await switch.async_turn_off()
    assert controller._floor_level == 0  # Source intent advances before delivery.
    assert controller._floor_default == 1
    assert switch.is_on is True and number.native_value == 1
    assert runtime.controller_state["light_level"] == 1
    controller.client.write_gatt_char.side_effect = None
    await switch.async_turn_on()
    assert written(controller) == ["00112000", "80110000", "00112000"]
    assert switch.is_on is True and number.native_value == 1
    for entity in (switch, number):
        await entity.async_will_remove_from_hass()


async def test_actual_paired_floor_entities_use_each_physical_profile_and_callbacks(hass):
    left_runtime, left_controller = await floor_runtime(hass)
    right_runtime, right_controller = await floor_runtime(hass, "werkmeister", 7)
    log = []

    class FloorChild(RecordingChild):
        def __init__(self, side, runtime, controller):
            super().__init__(side, log)
            self.entry = runtime.entry
            self.bed_type = BED_TYPE_VIBRADORM_APP
            self.controller = self.capability_controller = controller
            self.controller_state = runtime.controller_state
            self.has_massage = False
            self.disable_angle_sensing = True
            self.entity_unique_id = runtime.entity_unique_id
            self.entity_translation_key = runtime.entity_translation_key
            self.register_controller_state_callback = runtime.register_controller_state_callback

        async def async_execute_controller_command(
            self,
            command_fn,
            cancel_running=True,
            skip_disconnect=False,
            resource=None,
            resources=None,
        ):
            await command_fn(self.controller)

    children = {
        "left": FloorChild("left", left_runtime, left_controller),
        "right": FloorChild("right", right_runtime, right_controller),
    }
    pair_entry = MockConfigEntry(domain=DOMAIN, data={CONF_PAIR_ID: "floor-pair"})
    pair_entry.add_to_hass(hass)
    pair = PairedBedCoordinator(hass, pair_entry, children)
    with patch(
        "custom_components.adjustable_bed.paired_coordinator.child_device_info", return_value={}
    ):
        left_switch, left_number = await add_public_floor_entities(
            hass, PairedSideProxy(pair, children["left"], "left")
        )
        right_switch, right_number = await add_public_floor_entities(
            hass, PairedSideProxy(pair, children["right"], "right")
        )
    for switch, number in ((left_switch, left_number), (right_switch, right_number)):
        assert switch.is_on is None and number.native_value is None
    await left_number.async_set_native_value(1)
    await left_switch.async_turn_off()
    await left_switch.async_turn_on()
    assert written(left_controller) == ["200000", "000000", "200000"]
    assert written(right_controller) == []
    assert left_switch.is_on is True and left_number.native_value == 1
    assert right_switch.is_on is None and right_number.native_value is None
    await right_number.async_set_native_value(1)
    await right_switch.async_turn_off()
    await right_switch.async_turn_on()
    assert written(right_controller) == ["00112000", "80110000", "00112000"]
    assert left_runtime.controller_state is not right_runtime.controller_state
    assert all(child.connection_holds == 0 for child in children.values())
    for entity in (left_switch, left_number, right_switch, right_number):
        await entity.async_will_remove_from_hass()


@pytest.mark.parametrize("control", [2, 7])
async def test_zero_minute_pending_toggle_preserves_source_state_and_effective_timer(hass, control):
    runtime, controller = await floor_runtime(hass, control=control)
    timer = next(entity for entity in _select_entities_for(hass, runtime)
                 if entity.entity_description.key == "light_timer")
    minutes = next(entity for entity in _number_entities_for(hass, runtime)
                   if hasattr(entity, "_spec")
                   and entity._spec.key == "vibradorm_app_floor_timer_minutes")
    assert controller._timer_minutes == 0 and not controller._timer_enabled
    await runtime.async_execute_controller_command(
        lambda ctrl: ctrl.execute_app_action("floor_timer_toggle")
    )
    assert controller._timer_enabled and controller._timer_minutes == 0
    assert controller.protocol_diagnostics["pending_timer"] == {"enabled": True, "minutes": 0}
    assert timer.current_option == "Off"
    assert controller.get_light_state()["light_timer_option"] == "Off"
    assert runtime.controller_state["vibradorm_app_floor_timer_enabled"] is False
    assert written(controller) == []
    await controller.set_light_level(6)
    zero = "c00000" if control == 2 else "0011c000"
    assert written(controller) == [zero]
    await minutes.async_set_native_value(17)
    assert controller._timer_enabled and controller._timer_minutes == 17
    assert timer.current_option == "17 min"
    assert runtime.controller_state["vibradorm_app_floor_timer_enabled"] is True
    assert written(controller) == [zero]
    await controller.set_light_level(6)
    positive = "c00011" if control == 2 else "0011c011"
    assert written(controller) == [zero, positive]
    await runtime.async_execute_controller_command(
        lambda ctrl: ctrl.execute_app_action("floor_timer_toggle")
    )
    assert not controller._timer_enabled and controller._timer_minutes == 17
    assert timer.current_option == "Off"
    await controller.set_light_level(6)
    assert written(controller) == [zero, positive, zero]
