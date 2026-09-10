"""Malouf/Lucid alarm service validation and serialized dispatch."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import voluptuous as vol
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError

from custom_components.adjustable_bed.const import (
    BED_TYPE_MALOUF_APP,
    BED_TYPE_MALOUF_NEW_OKIN,
    CONF_MALOUF_APP_PROFILE,
    DOMAIN,
    SIDE_BOTH,
    SIDE_RIGHT,
)
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.malouf_app_protocol import ROUTABLE_ACTIONS
from custom_components.adjustable_bed.paired_coordinator import PairedBedCoordinator
from custom_components.adjustable_bed.services import (
    MALOUF_ALARM_PRESETS,
    SERVICE_MALOUF_APP_ACTION,
    SERVICE_MALOUF_SET_ALARM,
    async_register_services,
)


@pytest.fixture
async def service_target(hass: HomeAssistant):
    """Use the registered schema and dispatch with a client-free controller."""
    await async_register_services(hass)
    controller = SimpleNamespace(
        supports_clock_alarm=True,
        clock_alarm_presets=MALOUF_ALARM_PRESETS,
        memory_slot_count=0,
        supports_preset_zero_g=False,
        configure_clock_alarm=AsyncMock(),
    )
    coordinator = MagicMock(spec=AdjustableBedCoordinator)
    coordinator.name = "Malouf app bed"
    coordinator.bed_type = BED_TYPE_MALOUF_APP
    coordinator.capability_controller = controller

    async def execute(command, **kwargs):
        await command(controller)

    coordinator.async_execute_controller_command = AsyncMock(side_effect=execute)
    with patch(
        "custom_components.adjustable_bed.services._resolve_sided_targets",
        return_value=([(coordinator, SIDE_BOTH)], []),
    ) as resolve:
        yield coordinator, controller, resolve


async def test_alarm_maps_weekdays_and_uses_configuration_queue(
    hass: HomeAssistant, service_target
):
    coordinator, controller, _ = service_target
    await hass.services.async_call(
        DOMAIN,
        SERVICE_MALOUF_SET_ALARM,
        {
            "device_id": "bed",
            "enabled": True,
            "time": "07:35:00",
            "weekdays": ["monday", "friday", "sunday"],
            "preset": "anti_snore",
        },
        blocking=True,
    )
    controller.configure_clock_alarm.assert_awaited_once_with(
        enabled=True, weekdays=(0, 4, 6), hour=7, minute=35, preset="anti_snore"
    )
    kwargs = coordinator.async_execute_controller_command.await_args.kwargs
    assert kwargs["cancel_running"] is False
    assert kwargs["resource"] == "configuration"


@pytest.mark.parametrize("preset", MALOUF_ALARM_PRESETS)
async def test_alarm_presets_do_not_depend_on_ordinary_motor_or_memory_capabilities(
    hass: HomeAssistant, service_target, preset
):
    _, controller, _ = service_target
    await hass.services.async_call(
        DOMAIN,
        SERVICE_MALOUF_SET_ALARM,
        {"device_id": "bed", "enabled": True, "time": "06:30:00", "preset": preset},
        blocking=True,
    )
    controller.configure_clock_alarm.assert_awaited_once_with(
        enabled=True, weekdays=(), hour=6, minute=30, preset=preset
    )


async def test_disable_needs_no_schedule_fields(hass: HomeAssistant, service_target):
    _, controller, _ = service_target
    controller.clock_alarm_presets = ()
    await hass.services.async_call(
        DOMAIN,
        SERVICE_MALOUF_SET_ALARM,
        {"device_id": "bed", "enabled": False},
        blocking=True,
    )
    controller.configure_clock_alarm.assert_awaited_once_with(
        enabled=False, weekdays=(), hour=0, minute=0, preset=""
    )


@pytest.mark.parametrize("fields", [{}, {"preset": "zero_g"}, {"time": "07:00:00"}])
async def test_enable_requires_time_and_preset_before_resolving_targets(
    hass: HomeAssistant, service_target, fields
):
    _, _, resolve = service_target
    with pytest.raises(ServiceValidationError, match="requires time and preset"):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_MALOUF_SET_ALARM,
            {"device_id": "bed", "enabled": True, **fields},
            blocking=True,
        )
    resolve.assert_not_called()


@pytest.mark.parametrize(
    "fields",
    [
        {"time": "25:00:00", "preset": "zero_g"},
        {"time": "07:00:00", "preset": "unknown"},
        {"time": "07:00:00", "preset": "zero_g", "weekdays": ["holiday"]},
        {"device_id": []},
    ],
)
async def test_invalid_schema_prevents_dispatch(hass: HomeAssistant, service_target, fields):
    _, _, resolve = service_target
    with pytest.raises(vol.Invalid):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_MALOUF_SET_ALARM,
            {"device_id": "bed", "enabled": True, **fields},
            blocking=True,
        )
    resolve.assert_not_called()


async def test_alarm_does_not_silently_discard_seconds(hass: HomeAssistant, service_target):
    _, _, resolve = service_target
    with pytest.raises(ServiceValidationError, match="whole minutes"):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_MALOUF_SET_ALARM,
            {"device_id": "bed", "enabled": True, "time": "07:00:59", "preset": "zero_g"},
            blocking=True,
        )
    resolve.assert_not_called()


@pytest.mark.parametrize("clock_capable", [False, True])
async def test_every_target_is_preflighted_before_any_alarm_is_replaced(
    hass: HomeAssistant, service_target, clock_capable
):
    coordinator, controller, resolve = service_target
    unsupported = MagicMock(spec=AdjustableBedCoordinator)
    unsupported.name = "Unsupported alarm target"
    unsupported.bed_type = BED_TYPE_MALOUF_APP
    unsupported.capability_controller = SimpleNamespace(
        supports_clock_alarm=clock_capable, clock_alarm_presets=("zero_g",)
    )
    resolve.return_value = ([(coordinator, SIDE_BOTH), (unsupported, SIDE_BOTH)], [])
    with pytest.raises(ServiceValidationError, match="does not support"):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_MALOUF_SET_ALARM,
            {
                "device_id": ["bed", "other"],
                "enabled": True,
                "time": "06:00:00",
                "preset": "memory_2",
            },
            blocking=True,
        )
    controller.configure_clock_alarm.assert_not_awaited()
    coordinator.async_execute_controller_command.assert_not_awaited()
    unsupported.async_execute_controller_command.assert_not_called()


async def test_legacy_controller_type_is_not_reinterpreted(hass: HomeAssistant, service_target):
    coordinator, _, _ = service_target
    coordinator.bed_type = BED_TYPE_MALOUF_NEW_OKIN
    with pytest.raises(ServiceValidationError, match="not a Malouf/Lucid app controller"):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_MALOUF_SET_ALARM,
            {"device_id": "bed", "enabled": False},
            blocking=True,
        )
    coordinator.async_execute_controller_command.assert_not_awaited()


async def test_alarm_preserves_paired_side_dispatch(hass: HomeAssistant, service_target):
    coordinator, controller, resolve = service_target
    pair = MagicMock(spec=PairedBedCoordinator)
    pair.child_for_side.return_value = coordinator

    async def execute(command, **kwargs):
        await command(controller)

    pair.async_execute_controller_command = AsyncMock(side_effect=execute)
    resolve.return_value = ([(pair, SIDE_RIGHT)], [])
    await hass.services.async_call(
        DOMAIN,
        SERVICE_MALOUF_SET_ALARM,
        {"device_id": "pair", "side": SIDE_RIGHT, "enabled": False},
        blocking=True,
    )
    kwargs = pair.async_execute_controller_command.await_args.kwargs
    assert kwargs["side"] == SIDE_RIGHT
    assert kwargs["cancel_running"] is False
    assert kwargs["resource"] == "configuration"
    controller.configure_clock_alarm.assert_awaited_once()
    coordinator.async_execute_controller_command.assert_not_awaited()


@pytest.fixture
async def routed_pair(hass: HomeAssistant):
    """Capture side-specific operations admitted through the paired scheduler."""
    await async_register_services(hass)
    children = {}
    for side in ("left", "right"):
        child = MagicMock(spec=AdjustableBedCoordinator)
        child.name = side
        child.bed_type = BED_TYPE_MALOUF_APP
        child.entry = SimpleNamespace(data={CONF_MALOUF_APP_PROFILE: "lucid"})
        child.capability_controller = SimpleNamespace(
            app_action_options=tuple(ROUTABLE_ACTIONS),
            app_action_noops=(),
            execute_app_action=AsyncMock(),
        )

        async def execute(command, *, controller=child.capability_controller, **kwargs):
            await command(controller)

        child.async_execute_controller_command = AsyncMock(side_effect=execute)
        children[side] = child
    pair = MagicMock(spec=PairedBedCoordinator)
    pair.children = children

    async def run(action, operation, *, side, cancel_running):
        selected = children.values() if side == SIDE_BOTH else [children[side]]
        for child in selected:
            await operation(child)

    pair.async_run_child_operation = AsyncMock(side_effect=run)
    with patch(
        "custom_components.adjustable_bed.services._resolve_sided_target",
        return_value=(pair, None),
    ) as resolve:
        yield pair, children, resolve


@pytest.mark.parametrize(
    ("route", "action", "expected"),
    [
        ("standard", "dualUp", {"left": "dualUp"}),
        ("split_head_dual", "dualUp", {"left": "dualUp", "right": "footUp"}),
        ("split_head_dual", "allDown", {"left": "allDown", "right": "footDown"}),
        ("split_head_dual", "footUp", {"left": "footUp", "right": "footUp"}),
        ("split_head_dual", "stopDriver", {"left": "stopDriver", "right": "stopDriver"}),
        ("split_head_dual", "massageFoot", {"left": "massageFoot"}),
        ("split_head_dual", "allFlat", {"left": "allFlat", "right": "allFlat"}),
        ("split_head_dual", "setMemory2", {"left": "setMemory2"}),
    ],
)
async def test_app_routing_preserves_exact_per_child_actions(
    hass: HomeAssistant, routed_pair, route, action, expected
):
    pair, children, _ = routed_pair
    await hass.services.async_call(
        DOMAIN,
        SERVICE_MALOUF_APP_ACTION,
        {"device_id": "parent", "route": route, "active_side": "left", "action": action},
        blocking=True,
    )
    for side, child in children.items():
        execute = child.capability_controller.execute_app_action
        if side in expected:
            execute.assert_awaited_once_with(expected[side], primary=True)
            assert child.async_execute_controller_command.await_args.kwargs["cancel_running"]
        else:
            execute.assert_not_awaited()
    kwargs = pair.async_run_child_operation.await_args.kwargs
    assert kwargs["side"] == (SIDE_BOTH if len(expected) == 2 else "left")
    assert kwargs["cancel_running"] is True


async def test_malouf_does_not_inherit_lucid_all_rewrite(hass: HomeAssistant, routed_pair):
    _, children, _ = routed_pair
    for child in children.values():
        child.entry.data[CONF_MALOUF_APP_PROFILE] = "malouf"
    await hass.services.async_call(
        DOMAIN,
        SERVICE_MALOUF_APP_ACTION,
        {
            "device_id": "parent",
            "route": "split_head_dual",
            "active_side": "left",
            "action": "allUp",
        },
        blocking=True,
    )
    children["left"].capability_controller.execute_app_action.assert_awaited_once_with(
        "allUp", primary=True
    )
    children["right"].async_execute_controller_command.assert_not_awaited()


@pytest.mark.parametrize(
    ("active_side", "swapped", "primary"),
    [
        ("left", False, True),
        ("left", True, False),
        ("right", False, False),
        ("right", True, True),
        ("both", False, False),
        ("none", False, False),
    ],
)
async def test_native_side_selector_is_transient_and_single_dispatch(
    hass: HomeAssistant, routed_pair, active_side, swapped, primary
):
    _, children, resolve = routed_pair
    child = children["left"]
    resolve.return_value = (child, None)
    await hass.services.async_call(
        DOMAIN,
        SERVICE_MALOUF_APP_ACTION,
        {
            "device_id": "single",
            "route": "split_head_native",
            "active_side": active_side,
            "motor_swapped": swapped,
            "action": "headUp",
        },
        blocking=True,
    )
    child.capability_controller.execute_app_action.assert_awaited_once_with(
        "headUp", primary=primary
    )


async def test_native_programming_keeps_default_primary(hass: HomeAssistant, routed_pair):
    pair, children, _ = routed_pair
    await hass.services.async_call(
        DOMAIN,
        SERVICE_MALOUF_APP_ACTION,
        {
            "device_id": "parent",
            "route": "split_head_native",
            "active_side": "right",
            "action": "setMemory2",
        },
        blocking=True,
    )
    children["right"].capability_controller.execute_app_action.assert_awaited_once_with(
        "setMemory2", primary=True
    )
    children["left"].async_execute_controller_command.assert_not_awaited()
    assert pair.async_run_child_operation.await_args.kwargs["side"] == "right"


async def test_proven_no_write_child_does_not_suppress_inactive_foot_copy(
    hass: HomeAssistant, routed_pair
):
    pair, children, _ = routed_pair
    children["left"].capability_controller.app_action_options = ("headUp",)
    children["left"].capability_controller.app_action_noops = ("allUp",)
    await hass.services.async_call(
        DOMAIN,
        SERVICE_MALOUF_APP_ACTION,
        {
            "device_id": "parent",
            "route": "split_head_dual",
            "active_side": "left",
            "action": "allUp",
        },
        blocking=True,
    )
    children["left"].async_execute_controller_command.assert_not_awaited()
    children["right"].capability_controller.execute_app_action.assert_awaited_once_with(
        "footUp", primary=True
    )
    assert pair.async_run_child_operation.await_args.kwargs["side"] == "right"


@pytest.mark.parametrize("reason", ["missing_action", "mixed_app", "wrong_type", "child_target"])
async def test_routing_preflight_rejects_invalid_group_before_dispatch(
    hass: HomeAssistant, routed_pair, reason
):
    pair, children, resolve = routed_pair
    if reason == "missing_action":
        children["right"].capability_controller.app_action_options = ("headUp",)
    elif reason == "mixed_app":
        children["right"].entry.data[CONF_MALOUF_APP_PROFILE] = "malouf"
    elif reason == "wrong_type":
        children["right"].bed_type = BED_TYPE_MALOUF_NEW_OKIN
    else:
        resolve.return_value = (pair, "left")
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_MALOUF_APP_ACTION,
            {
                "device_id": "parent",
                "route": "split_head_dual",
                "active_side": "left",
                "action": "dualUp",
            },
            blocking=True,
        )
    pair.async_run_child_operation.assert_not_awaited()
    for child in children.values():
        child.async_execute_controller_command.assert_not_awaited()
