"""Typed product controls keep state, capabilities and physical side ownership."""

import asyncio
from dataclasses import FrozenInstanceError, replace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed.beds.base import (
    ControllerNumberSpec,
    ControllerSelectSpec,
    build_position_number_spec,
)
from custom_components.adjustable_bed.beds.diagnostic import DiagnosticBedController
from custom_components.adjustable_bed.const import BED_TYPE_DIAGNOSTIC, CONF_BED_TYPE, DOMAIN
from custom_components.adjustable_bed.number import (
    AdjustableBedControllerNumber,
    AdjustableBedLevelNumber,
    _number_entities_for,
)
from custom_components.adjustable_bed.number import (
    async_setup_entry as setup_numbers,
)
from custom_components.adjustable_bed.paired_coordinator import (
    PairedBedCoordinator,
    PairedSideProxy,
)
from custom_components.adjustable_bed.select import (
    AdjustableBedControllerSelect,
    _select_entities_for,
)
from custom_components.adjustable_bed.select import (
    async_setup_entry as setup_selects,
)


class ProductController(DiagnosticBedController):
    """Record commands and side context without simulating hardware feedback."""

    def __init__(self):
        super().__init__(MagicMock(address="test"))
        self.selects = True
        self.numbers = True
        self.complete = True
        self.calls = []
        self.fail = False

    @property
    def controller_select_specs(self) -> tuple[ControllerSelectSpec, ...]:
        return (
            (
                ControllerSelectSpec(
                    "mood",
                    "mood_palette",
                    "mood_intent",
                    ("red", "blue"),
                    lambda ctrl, option: ctrl.set_mood_palette(option),
                ),
            )
            if self.selects
            else ()
        )

    @property
    def controller_number_specs(self) -> tuple[ControllerNumberSpec, ...]:
        return (
            (
                ControllerNumberSpec(
                    "speed",
                    "mood_speed",
                    "speed_intent",
                    0,
                    8,
                    1,
                    lambda ctrl, value: ctrl.set_mood_speed(value),
                ),
            )
            if self.numbers
            else ()
        )

    @property
    def has_dynamic_controller_entities(self):
        return True

    @property
    def controller_entity_discovery_complete(self):
        return self.complete

    async def set_mood_palette(self, option):
        await asyncio.sleep(0)
        if self.fail:
            raise OSError("write failed")
        self.calls.append(("palette", option, self.command_side))

    async def set_mood_speed(self, value):
        await asyncio.sleep(0)
        if self.fail:
            raise OSError("write failed")
        self.calls.append(("speed", value, self.command_side))


def runtime_for(hass, controller, side=None, entry=None):
    entry = entry or MockConfigEntry(domain=DOMAIN, data={CONF_BED_TYPE: BED_TYPE_DIAGNOSTIC})
    if hass.config_entries.async_get_entry(entry.entry_id) is None:
        entry.add_to_hass(hass)
    runtime = MagicMock()
    runtime.entry = entry
    runtime.entity_side = side
    runtime.device_info = {}
    runtime.has_massage = False
    runtime.disable_angle_sensing = True
    runtime.controller = controller
    runtime.capability_controller = controller
    runtime.controller_state = {}
    runtime.entity_unique_id.side_effect = lambda key: f"bed_{key}" + (f"_{side}" if side else "")
    runtime.entity_translation_key.side_effect = lambda key: key
    lock = asyncio.Lock()

    async def execute(command, **kwargs):
        async with lock:
            live = runtime.controller
            await command(live.bind_side(side) if side else live)

    runtime.async_execute_controller_command = AsyncMock(side_effect=execute)
    return runtime


def custom_entities(hass, runtime):
    return (
        next(
            entity
            for entity in _select_entities_for(hass, runtime)
            if isinstance(entity, AdjustableBedControllerSelect)
        ),
        next(
            entity
            for entity in _number_entities_for(hass, runtime)
            if isinstance(entity, AdjustableBedControllerNumber)
        ),
    )


async def test_metadata_and_unknown_state_do_not_infer_hardware(hass):
    controller = ProductController()
    runtime = runtime_for(hass, controller)
    select, number = custom_entities(hass, runtime)
    assert select.unique_id == "bed_controller_select_mood"
    assert select.options == ["red", "blue"]
    assert number.unique_id == "bed_controller_number_speed"
    assert (number.native_min_value, number.native_max_value, number.native_step) == (0, 8, 1)
    assert select.current_option is None
    assert number.native_value is None
    await select.async_select_option("blue")
    await number.async_set_native_value(3)
    assert select.current_option is None
    assert number.native_value is None
    assert controller.calls == [("palette", "blue", None), ("speed", 3, None)]
    runtime.controller_state.update(mood_intent="blue", speed_intent=3)
    assert (select.current_option, number.native_value) == ("blue", 3)
    with pytest.raises(FrozenInstanceError):
        controller.controller_select_specs[0].key = "changed"


@pytest.mark.parametrize("value", [True, -1, 9, 1.5, float("nan"), float("inf")])
async def test_invalid_numbers_reject_before_command(hass, value):
    runtime = runtime_for(hass, ProductController())
    _, number = custom_entities(hass, runtime)
    with pytest.raises(ServiceValidationError):
        await number.async_set_native_value(value)
    runtime.async_execute_controller_command.assert_not_awaited()
    runtime.controller_state["speed_intent"] = value
    assert number.native_value is None


async def test_invalid_select_rejects_before_command(hass):
    runtime = runtime_for(hass, ProductController())
    select, _ = custom_entities(hass, runtime)
    with pytest.raises(ServiceValidationError):
        await select.async_select_option("green")
    runtime.async_execute_controller_command.assert_not_awaited()
    runtime.controller_state["mood_intent"] = "green"
    assert select.current_option is None


@pytest.mark.parametrize("side", [None, "left", "right"])
async def test_reconnect_uses_live_spec_and_real_side_bound_methods(hass, side):
    offline = ProductController()
    runtime = runtime_for(hass, offline, side)
    select, number = custom_entities(hass, runtime)
    live = ProductController()
    runtime.controller = live
    await asyncio.gather(select.async_select_option("red"), number.async_set_native_value(2))
    assert offline.calls == []
    assert live.calls == [("palette", "red", side), ("speed", 2, side)]
    assert live.command_side is None
    assert runtime.controller_state == {}


@pytest.mark.parametrize("domain", ["select", "number"])
async def test_missing_live_capability_rejects_obsolete_entity(hass, domain):
    runtime = runtime_for(hass, ProductController())
    select, number = custom_entities(hass, runtime)
    live = ProductController()
    live.selects = live.numbers = False
    runtime.controller = live
    with pytest.raises(ServiceValidationError):
        if domain == "select":
            await select.async_select_option("red")
        else:
            await number.async_set_native_value(2)
    assert live.calls == []


@pytest.mark.parametrize("domain", ["select", "number"])
async def test_write_failure_does_not_create_optimistic_state(hass, domain):
    controller = ProductController()
    controller.fail = True
    runtime = runtime_for(hass, controller)
    select, number = custom_entities(hass, runtime)
    with pytest.raises(OSError, match="write failed"):
        if domain == "select":
            await select.async_select_option("red")
        else:
            await number.async_set_native_value(2)
    assert select.current_option is None
    assert number.native_value is None


@pytest.mark.parametrize("domain,key", [("select", "mood_intent"), ("number", "speed_intent")])
async def test_state_callbacks_watch_declared_key_and_unsubscribe(hass, domain, key):
    runtime = runtime_for(hass, ProductController())
    entities = custom_entities(hass, runtime)
    entity = entities[0 if domain == "select" else 1]
    entity.hass = hass
    unsubscribe = MagicMock()
    runtime.register_controller_state_callback.return_value = unsubscribe
    await entity.async_added_to_hass()
    state_callback = runtime.register_controller_state_callback.call_args.args[0]
    with patch.object(entity, "async_write_ha_state") as write:
        state_callback({"other": 2})
        write.assert_not_called()
        state_callback({key: 2})
        write.assert_called_once()
    await entity.async_will_remove_from_hass()
    unsubscribe.assert_called_once()


@pytest.mark.parametrize("domain", ["select", "number"])
@pytest.mark.parametrize("complete", [False, True])
async def test_stale_cleanup_is_bounded_to_profile_side_platform_and_entry(hass, domain, complete):
    controller = ProductController()
    controller.complete = complete
    controller.selects = controller.numbers = False
    runtime = runtime_for(hass, controller, "left")
    registry = er.async_get(hass)
    stale = registry.async_get_or_create(
        domain, DOMAIN, f"bed_controller_{domain}_old_left", config_entry=runtime.entry
    )
    other_side = registry.async_get_or_create(
        domain, DOMAIN, f"bed_controller_{domain}_old_right", config_entry=runtime.entry
    )
    unrelated = registry.async_get_or_create(
        domain, DOMAIN, "bed_unrelated_left", config_entry=runtime.entry
    )
    other_platform = registry.async_get_or_create(
        domain, "other", f"bed_controller_{domain}_old_left", config_entry=runtime.entry
    )
    other_entry = MockConfigEntry(domain=DOMAIN)
    other_entry.add_to_hass(hass)
    other_bed = registry.async_get_or_create(
        domain, DOMAIN, f"another_controller_{domain}_old_left", config_entry=other_entry
    )
    (_select_entities_for if domain == "select" else _number_entities_for)(hass, runtime)
    assert (registry.async_get(stale.entity_id) is not None) is (not complete)
    for kept in (other_side, unrelated, other_platform, other_bed):
        assert registry.async_get(kept.entity_id) is not None


@pytest.mark.parametrize("domain", ["select", "number"])
async def test_late_capabilities_add_once_and_do_not_delete_pending_registry(hass, domain):
    controller = ProductController()
    controller.complete = False
    controller.selects = controller.numbers = False
    runtime = runtime_for(hass, controller)
    registry = er.async_get(hass)
    old = registry.async_get_or_create(
        domain, DOMAIN, f"bed_controller_{domain}_old", config_entry=runtime.entry
    )
    hass.data[DOMAIN] = {runtime.entry.entry_id: runtime}
    add = MagicMock()
    module = f"custom_components.adjustable_bed.{domain}"
    with patch(f"{module}.entity_runtimes", return_value=[runtime]):
        await (setup_selects if domain == "select" else setup_numbers)(hass, runtime.entry, add)
    discover = runtime.register_controller_state_callback.call_args.args[0]
    assert registry.async_get(old.entity_id) is not None
    controller.selects = controller.numbers = True
    controller.complete = True
    discover({})
    discover({})
    assert add.call_count == 2
    assert len(add.call_args.args[0]) == 1
    assert registry.async_get(old.entity_id) is None


async def test_default_controller_removes_custom_controls_and_adds_none(hass):
    controller = DiagnosticBedController(MagicMock(address="test"))
    assert controller.controller_select_specs == ()
    assert controller.controller_number_specs == ()
    assert controller.light_level_min == 0
    runtime = runtime_for(hass, controller)
    assert _select_entities_for(hass, runtime) == []
    assert _number_entities_for(hass, runtime) == []


async def test_fractional_grid_preserves_original_valid_value(hass):
    controller = ProductController()
    spec = replace(controller.controller_number_specs[0], native_max_value=1, native_step=0.1)
    runtime = runtime_for(hass, controller)
    number = AdjustableBedControllerNumber(runtime, spec)
    with patch.object(
        ProductController, "controller_number_specs", new=property(lambda _: (spec,))
    ):
        await number.async_set_native_value(0.1 + 0.2)
    assert controller.calls == [("speed", 0.1 + 0.2, None)]


async def test_dynamic_child_numbers_preserve_paired_parent_position_sliders(hass):
    left = runtime_for(hass, ProductController(), "left")
    right = runtime_for(hass, ProductController(), "right", left.entry)
    coordinator = MagicMock(spec=PairedBedCoordinator)
    coordinator.children = {"left": left, "right": right}
    coordinator.device_info = {}
    coordinator.entity_unique_id.side_effect = lambda key: f"pair_{key}"
    coordinator.entry = left.entry
    hass.data[DOMAIN] = {left.entry.entry_id: coordinator}
    position = build_position_number_spec("back", max_value=68, unit="°")
    for runtime in (left, right):
        runtime.disable_angle_sensing = False
    add = MagicMock()
    with (
        patch(
            "custom_components.adjustable_bed.number.entity_runtimes", return_value=[left, right]
        ),
        patch(
            "custom_components.adjustable_bed.number._position_number_specs",
            return_value=(position,),
        ),
    ):
        await setup_numbers(hass, left.entry, add)
        left.register_controller_state_callback.call_args.args[0]({})
        right.register_controller_state_callback.call_args.args[0]({})
    all_ids = [entity.unique_id for call in add.call_args_list for entity in call.args[0]]
    assert all_ids.count("pair_back_position_both") == 1
    assert all_ids.count("bed_controller_number_speed_left") == 1
    assert all_ids.count("bed_controller_number_speed_right") == 1


@pytest.mark.parametrize("domain", ["select", "number"])
async def test_changed_live_domain_rejects_old_valid_value(hass, domain):
    runtime = runtime_for(hass, ProductController())
    select, number = custom_entities(hass, runtime)
    if domain == "select":
        live_spec = replace(runtime.controller.controller_select_specs[0], options=("blue",))
        attribute, replacement = "controller_select_specs", (live_spec,)
    else:
        live_spec = replace(runtime.controller.controller_number_specs[0], native_min_value=4)
        attribute, replacement = "controller_number_specs", (live_spec,)
    with (
        patch.object(ProductController, attribute, new=property(lambda _: replacement)),
        pytest.raises(ServiceValidationError),
    ):
        if domain == "select":
            await select.async_select_option("red")
        else:
            await number.async_set_native_value(2)
    assert runtime.controller.calls == []


@pytest.mark.parametrize("maximum", [6, 8])
async def test_floor_slider_has_positive_domain_and_separate_off(hass, maximum):
    class FloorController(ProductController):
        @property
        def supports_light_level_control(self):
            return True

        @property
        def light_level_min(self):
            return 1

        @property
        def light_level_max(self):
            return maximum

        async def set_light_level(self, level):
            if not 1 <= level <= maximum:
                raise ValueError("Invalid floor slider value")
            self.calls.append(("floor", level, self.command_side))

        async def lights_off(self):
            self.calls.append(("floor_off", 0, self.command_side))

    controller = FloorController()
    runtime = runtime_for(hass, controller)
    number = next(
        entity
        for entity in _number_entities_for(hass, runtime)
        if isinstance(entity, AdjustableBedLevelNumber)
    )
    assert (number.native_min_value, number.native_max_value) == (1, maximum)
    await number.async_set_native_value(1)
    await number.async_set_native_value(maximum)
    for invalid in (0, maximum + 1, 1.4, True, float("nan"), float("inf")):
        with pytest.raises(ServiceValidationError):
            await number.async_set_native_value(invalid)
    await runtime.async_execute_controller_command(lambda ctrl: ctrl.lights_off())
    assert controller.calls == [
        ("floor", 1, None),
        ("floor", maximum, None),
        ("floor_off", 0, None),
    ]


async def test_two_address_proxy_routes_only_selected_physical_child(hass):
    controllers = {side: ProductController() for side in ("left", "right")}
    children = {side: runtime_for(hass, controller) for side, controller in controllers.items()}
    parent = MagicMock(spec=PairedBedCoordinator)

    async def execute(command, *, side, **kwargs):
        await children[side].async_execute_controller_command(command, **kwargs)

    parent.async_execute_controller_command = AsyncMock(side_effect=execute)
    left = PairedSideProxy(parent, children["left"], "left")
    right = PairedSideProxy(parent, children["right"], "right")
    with patch(
        "custom_components.adjustable_bed.paired_coordinator.child_device_info", return_value={}
    ):
        select = AdjustableBedControllerSelect(left, controllers["left"].controller_select_specs[0])
        number = AdjustableBedControllerNumber(
            right, controllers["right"].controller_number_specs[0]
        )
    await select.async_select_option("blue")
    await number.async_set_native_value(4)
    assert [
        call.kwargs["side"] for call in parent.async_execute_controller_command.await_args_list
    ] == [
        "left",
        "right",
    ]
    assert controllers["left"].calls == [("palette", "blue", None)]
    assert controllers["right"].calls == [("speed", 4, None)]
    children["left"].controller_state["mood_intent"] = "blue"
    assert select.current_option == "blue"
    assert number.native_value is None
