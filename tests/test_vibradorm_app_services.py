"""Registered app actions preserve exact factory profile, packet and side gates."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
import voluptuous as vol
from homeassistant.exceptions import ServiceValidationError

from custom_components.adjustable_bed.const import (
    BED_TYPE_VIBRADORM_APP,
    CONF_PAIR_ID,
    CONF_VIBRADORM_APP_PROFILE,
    CONF_VIBRADORM_CONTROL_TYPE,
    CONF_VIBRADORM_RESTORED,
    DOMAIN,
    SIDE_BOTH,
    SIDE_LEFT,
    SIDE_RIGHT,
)
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.paired_coordinator import PairedBedCoordinator
from custom_components.adjustable_bed.services import async_register_services
from tests.test_paired_coordinator import RecordingChild
from tests.test_vibradorm_app import make_controller, written


async def factory_target(hass, app="caresse", control=2):
    # Reuse the native-role BLE fixture, but construct the tested controller via
    # the production factory and explicit persisted profile fields.
    seed = make_controller(control, app=app)
    coordinator = seed._coordinator
    coordinator.hass = hass
    coordinator.name = f"{app} {control}"
    coordinator.bed_type = BED_TYPE_VIBRADORM_APP
    coordinator.entry = SimpleNamespace(
        data={
            CONF_VIBRADORM_APP_PROFILE: app,
            CONF_VIBRADORM_CONTROL_TYPE: str(control),
            CONF_VIBRADORM_RESTORED: app == "caresse" and control != 2,
        }
    )
    controller = await create_controller(
        coordinator, BED_TYPE_VIBRADORM_APP, "auto", coordinator.client
    )
    coordinator.controller = coordinator.capability_controller = controller
    coordinator.is_connected = True

    async def execute(command, **kwargs):
        await command(coordinator.controller)

    coordinator.async_execute_controller_command = AsyncMock(side_effect=execute)
    return coordinator, controller


async def invoke(hass, targets, control, duration=0.1, side=None):
    await async_register_services(hass)
    with patch(
        "custom_components.adjustable_bed.services._resolve_sided_targets",
        return_value=(targets, []),
    ):
        await hass.services.async_call(
            DOMAIN,
            "hold_control",
            {
                "device_id": "selected",
                "control": control,
                "duration": duration,
                **({"side": side} if side else {}),
            },
            blocking=True,
        )


@pytest.mark.parametrize(
    "app,control,axes,slots,sync",
    [
        ("caresse", 2, ("back", "legs"), 0, False),
        ("caresse", 3, ("head", "back", "legs"), 3, False),
        ("caresse", 6, ("head", "back", "legs"), 6, False),
        ("caresse", "other", (), 6, False),
        ("werkmeister", 5, ("back", "legs"), 6, False),
        ("werkmeister", 7, ("head", "back", "legs", "feet"), 6, True),
    ],
)
async def test_factory_profiles_expose_only_their_exact_hold_catalog(
    hass, app, control, axes, slots, sync
):
    _, controller = await factory_target(hass, app, control)
    expected = {f"{axis}_{direction}" for axis in axes for direction in ("up", "down")}
    if axes:
        expected |= {"all_up", "all_down"}
    expected |= {f"memory_{slot}" for slot in range(1, slots + 1)}
    if sync:
        expected.add("sync")
    assert set(controller.held_control_options) == expected
    assert written(controller) == []


@pytest.mark.parametrize(
    "app,control,action,packets,uuid",
    [
        ("caresse", 2, "back_up", ["0b", "ff"], "00001526-9f03-0de5-96c5-b8f4f3081186"),
        ("caresse", 3, "head_up", ["03", "ff"], "00001526-9f03-0de5-96c5-b8f4f3081186"),
        ("werkmeister", 5, "back_up", ["000b", "00ff"], "00001550-9f03-0de5-96c5-b8f4f3081186"),
        ("werkmeister", 7, "feet_down", ["0004", "00ff"], "00001550-9f03-0de5-96c5-b8f4f3081186"),
    ],
)
async def test_registered_hold_uses_literal_profile_packet_and_bounded_release(
    hass, app, control, action, packets, uuid
):
    target, controller = await factory_target(hass, app, control)
    await asyncio.wait_for(invoke(hass, [(target, SIDE_BOTH)], action), timeout=2)
    assert written(controller) == packets
    characteristic = next(
        char for service in controller.client.services for char in service.characteristics
        if char.uuid == uuid
    )
    assert all(
        call.args[0] is characteristic for call in controller.client.write_gatt_char.call_args_list
    )
    assert target.async_execute_controller_command.await_args.kwargs["cancel_running"] is True


@pytest.mark.parametrize(
    "later_app,later_control,action",
    [
        ("caresse", 2, "feet_up"),
        ("caresse", 3, "memory_4"),
        ("caresse", "other", "back_up"),
        ("werkmeister", 5, "sync"),
    ],
)
async def test_all_target_preflight_rejects_later_profile_before_any_write(
    hass, later_app, later_control, action
):
    first, first_controller = await factory_target(hass, "werkmeister", 7)
    second, second_controller = await factory_target(hass, later_app, later_control)
    with pytest.raises(ServiceValidationError):
        await invoke(hass, [(first, SIDE_BOTH), (second, SIDE_BOTH)], action)
    assert written(first_controller) == written(second_controller) == []
    first.async_execute_controller_command.assert_not_awaited()
    second.async_execute_controller_command.assert_not_awaited()


@pytest.mark.parametrize(
    "duration",
    [
        True,
        False,
        -1,
        0,
        0.099,
        60.001,
        0.1001,
        1.0001,
        float("nan"),
        float("inf"),
        float("-inf"),
        "not a number",
    ],
)
async def test_invalid_duration_schema_rejects_before_target_or_write(hass, duration):
    await async_register_services(hass)
    target, controller = await factory_target(hass)
    with (
        patch(
            "custom_components.adjustable_bed.services._resolve_sided_targets",
            return_value=([(target, SIDE_BOTH)], []),
        ) as resolve,
        pytest.raises(vol.Invalid),
    ):
        await hass.services.async_call(
            DOMAIN,
            "hold_control",
            {"device_id": "bed", "control": "back_up", "duration": duration},
            blocking=True,
        )
    resolve.assert_not_called()
    assert written(controller) == []


@pytest.mark.parametrize("duration,milliseconds", [(0.1, 100), (0.101, 101), (60, 60000)])
async def test_duration_endpoints_preserve_whole_milliseconds(hass, duration, milliseconds):
    target, controller = await factory_target(hass)
    # Exercise registered schema/dispatch without waiting 60 physical seconds;
    # the real controller's bounded delivery is separately proven above.
    with patch.object(controller, "hold_control", new_callable=AsyncMock) as hold:
        await invoke(hass, [(target, SIDE_BOTH)], "back_up", duration)
    hold.assert_awaited_once_with("back_up", milliseconds)
    assert written(controller) == []


@pytest.mark.parametrize("side", [SIDE_LEFT, SIDE_RIGHT, SIDE_BOTH])
async def test_real_pair_routes_differing_profiles_and_exact_release(hass, side):
    log = []

    class AppChild(RecordingChild):
        def __init__(self, child_side, target, controller):
            super().__init__(child_side, log)
            self.bed_type = BED_TYPE_VIBRADORM_APP
            self.entry = target.entry
            self.controller = self.capability_controller = controller

        async def async_execute_controller_command(
            self, command_fn, cancel_running=True, skip_disconnect=False, resource=None, resources=None
        ):
            await command_fn(self.controller)

    left_target, left_controller = await factory_target(hass, "caresse", 2)
    right_target, right_controller = await factory_target(hass, "werkmeister", 7)
    children = {
        SIDE_LEFT: AppChild(SIDE_LEFT, left_target, left_controller),
        SIDE_RIGHT: AppChild(SIDE_RIGHT, right_target, right_controller),
    }
    pair = PairedBedCoordinator(hass, SimpleNamespace(data={CONF_PAIR_ID: "app-pair"}), children)
    await invoke(hass, [(pair, side)], "back_up", side=side)
    assert written(left_controller) == (["0b", "ff"] if side != SIDE_RIGHT else [])
    assert written(right_controller) == (["000b", "00ff"] if side != SIDE_LEFT else [])
    assert all(child.connection_holds == 0 for child in children.values())
