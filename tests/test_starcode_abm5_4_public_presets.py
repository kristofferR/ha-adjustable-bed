"""Standard app preset surfaces and non-preempting automatic-white scheduling."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.exceptions import ServiceValidationError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.beds.starcode_abm5_4_profiles import SELECTORS, TRANSPORTS
from custom_components.adjustable_bed.button import _button_entities_for
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.services import async_register_services
from tests.starcode_abm5_4_vectors import BUILDER_VECTORS
from tests.test_malouf_app_entities import configure_entity_runtime
from tests.test_starcode_abm5_4 import make_controller

PRESETS = {
    "preset_flat": "flatPosition",
    "preset_zero_g": "zeroGravity",
    "preset_anti_snore": "anti",
    "preset_tv": "tv",
    "preset_lounge": "lounge",
    "preset_memory_1": "m1",
}


def literal_frame(selector: str, action: str) -> str:
    return next(
        frame for c, a, value, frame in BUILDER_VECTORS if (c, a, value) == (selector, action, 0)
    )


@pytest.mark.parametrize("selector", SELECTORS)
@pytest.mark.parametrize("ui", ["BOX15", "BOX25_STAR"])
@pytest.mark.parametrize("key", PRESETS)
async def test_standard_preset_buttons_execute_native_frames_and_U_release(hass, selector, ui, key):
    controller = make_controller(selector, ui=ui)
    runtime = configure_entity_runtime(hass, controller, const.BED_TYPE_STARCODE_ABM5_4)

    async def execute(action, **_kwargs):
        await action(controller)

    runtime.async_execute_controller_command = AsyncMock(side_effect=execute)
    buttons = {button.translation_key: button for button in _button_entities_for(hass, runtime)}
    assert set(PRESETS) <= buttons.keys()
    assert not any("preset_memory_" + str(slot) in buttons for slot in range(2, 7))
    with patch.object(controller, "_wait", AsyncMock(return_value=False)):
        await buttons[key].async_press()
    expected = [literal_frame(selector, PRESETS[key])]
    if key == "preset_memory_1" or ui == "BOX25_STAR":
        expected.append(literal_frame(selector, "stop"))
    assert [
        call.args[1].hex() for call in controller.client.write_gatt_char.await_args_list
    ] == expected
    assert runtime.async_execute_controller_command.await_args.kwargs["cancel_running"] is True


@pytest.mark.parametrize("selector", SELECTORS)
@pytest.mark.parametrize("slot", [1, 2])
async def test_registered_goto_preset_allows_only_Memory_A(hass, selector, slot):
    await async_register_services(hass)
    controller = make_controller(selector)
    runtime = configure_entity_runtime(hass, controller, const.BED_TYPE_STARCODE_ABM5_4)

    async def execute(action, **_kwargs):
        await action(controller)

    runtime.async_execute_controller_command = AsyncMock(side_effect=execute)
    with (
        patch(
            "custom_components.adjustable_bed.services._resolve_sided_targets",
            return_value=([(runtime, const.SIDE_BOTH)], []),
        ),
        patch.object(controller, "_wait", AsyncMock(return_value=False)),
    ):
        if slot == 1:
            await hass.services.async_call(
                const.DOMAIN, "goto_preset", {"device_id": "bed", "preset": slot}, blocking=True
            )
        else:
            with pytest.raises(ServiceValidationError):
                await hass.services.async_call(
                    const.DOMAIN, "goto_preset", {"device_id": "bed", "preset": slot}, blocking=True
                )
    expected = [literal_frame(selector, "m1"), literal_frame(selector, "stop")] if slot == 1 else []
    assert [
        call.args[1].hex() for call in controller.client.write_gatt_char.await_args_list
    ] == expected
    assert runtime.async_execute_controller_command.await_count == (1 if slot == 1 else 0)


@pytest.mark.parametrize("initial_D", ["BOX25", "BOX25_STAR"])
@pytest.mark.parametrize(
    "manufacturer,expected_C_D",
    [(b"star", "BOX25_STAR"), (b"Star", "BOX25"), (b"star\x00", "BOX25")],
)
@pytest.mark.parametrize("ui", ["BOX15", "BOX25_STAR"])
async def test_manufacturer_C_D_mutation_preserves_literal_UART_roles_and_independent_U(
    initial_D, manufacturer, expected_C_D, ui
):
    controller = make_controller("BOX15", ui=ui, device=initial_D)
    original_roles = controller._transport
    controller.client.read_gatt_char.return_value = manufacturer
    await controller._classify()
    assert (controller.command_selector, controller.transport_selector, controller.ui_selector) == (
        expected_C_D,
        expected_C_D,
        ui,
    )
    assert controller._transport is original_roles is TRANSPORTS[expected_C_D]
    await controller._stream("headUp", 0)
    assert [call.args[1].hex() for call in controller.client.write_gatt_char.await_args_list] == [
        literal_frame(expected_C_D, "headUp"),
        literal_frame(expected_C_D, "stop"),
    ]
    assert all(
        call.args[0].uuid == original_roles.write and call.kwargs["response"] is False
        for call in controller.client.write_gatt_char.await_args_list
    )
    controller._coordinator._async_persist_config.assert_called_once()


@pytest.mark.parametrize("control", ["head_up", "save_memory_1"])
@pytest.mark.parametrize("invalidate", [False, True])
async def test_real_scheduler_white_queues_without_interrupting_user_stream(
    hass, mock_coordinator_connected, control, invalidate
):
    entry = MockConfigEntry(
        domain=const.DOMAIN,
        data={
            CONF_ADDRESS: "AA:BB:CC:DD:EE:FF",
            CONF_NAME: "App scheduler",
            const.CONF_BED_TYPE: const.BED_TYPE_STARCODE_ABM5_4,
            const.CONF_STARCODE_COMMAND_SELECTOR: "BOX25",
            const.CONF_STARCODE_UI_SELECTOR: "BOX25",
            const.CONF_STARCODE_TRANSPORT_SELECTOR: "BOX1220",
            const.CONF_DISABLE_ANGLE_SENSING: True,
            const.CONF_DISCONNECT_AFTER_COMMAND: False,
        },
    )
    entry.add_to_hass(hass)
    coordinator = AdjustableBedCoordinator(hass, entry)
    controller = make_controller(device="BOX1220")
    client = controller.client
    client.disconnect = AsyncMock()
    controller._coordinator = coordinator
    coordinator._client, coordinator._controller = client, controller
    coordinator.async_ensure_connected = AsyncMock(return_value=True)
    controller._ready = True
    entered, release, queued = asyncio.Event(), asyncio.Event(), asyncio.Event()
    real_execute = coordinator.async_execute_controller_command

    async def execute(action, **kwargs):
        if kwargs.get("cancel_running") is False:
            queued.set()
        await real_execute(action, **kwargs)

    async def wait(_seconds, event):
        if not entered.is_set():
            entered.set()
            await release.wait()
            assert not event.is_set()
        return False

    async def user_action(current):
        await current.hold_control(control, 1000)

    user = None
    try:
        with (
            patch.object(coordinator, "async_execute_controller_command", execute),
            patch.object(controller, "_wait", wait),
        ):
            user = asyncio.create_task(execute(user_action))
            await asyncio.wait_for(entered.wait(), 2)
            controller._notification(
                controller.client,
                controller._session_generation,
                controller.client.services[0].characteristics[1],
                bytearray.fromhex("a50b0000006404030300000000002110"),
            )
            await asyncio.wait_for(queued.wait(), 2)
            assert not user.done()
            assert [
                call.args[1].hex() for call in controller.client.write_gatt_char.await_args_list
            ] == [literal_frame("BOX25", "headUp" if control == "head_up" else "saveM1")]
            if invalidate:
                controller._session_generation += 1
            release.set()
            await asyncio.wait_for(user, 2)
            await asyncio.wait_for(asyncio.gather(*tuple(controller._tasks)), 2)
        frames = [call.args[1].hex() for call in controller.client.write_gatt_char.await_args_list]
        if invalidate:
            assert len(frames) == 1
        else:
            assert frames == [
                literal_frame("BOX25", "headUp" if control == "head_up" else "saveM1"),
                literal_frame("BOX25", "stop"),
                literal_frame("BOX25", "change2White"),
            ]
    finally:
        release.set()
        if user is not None and not user.done():
            user.cancel()
            await asyncio.gather(user, return_exceptions=True)
        await coordinator.async_shutdown()


@pytest.mark.parametrize("side", ["left", "right", "both"])
@pytest.mark.parametrize("route", ["goto_preset", "starcode_abm5_4_hold_control"])
async def test_registered_preset_routes_use_actual_physical_children_and_native_release(
    hass, side, route
):
    from types import SimpleNamespace

    from custom_components.adjustable_bed.paired_coordinator import PairedBedCoordinator
    from tests.test_paired_coordinator import RecordingChild

    await async_register_services(hass)
    log = []

    class AppChild(RecordingChild):
        def __init__(self, child_side):
            super().__init__(child_side, log)
            self.bed_type = const.BED_TYPE_STARCODE_ABM5_4
            self.entry = SimpleNamespace(data={})
            self.controller = make_controller(
                "BOX15" if child_side == "left" else "BOX25_STAR",
                ui="BOX15" if child_side == "left" else "BOX25_STAR",
            )
            self.controller._coordinator.address = self.address
            self.controller._owner_address = self.address
            self.capability_controller = self.controller

        async def async_execute_controller_command(
            self,
            command_fn,
            cancel_running=True,
            skip_disconnect=False,
            resource=None,
            resources=None,
        ):
            await command_fn(self.controller)

    children = {key: AppChild(key) for key in ("left", "right")}
    pair = PairedBedCoordinator(
        hass, SimpleNamespace(data={const.CONF_PAIR_ID: "app-pair"}), children
    )
    parameters = {"device_id": "pair", "side": side}
    if route == "goto_preset":
        parameters["preset"] = 1
    else:
        parameters.update(control="zero_g", duration=0.1)
    with (
        patch(
            "custom_components.adjustable_bed.services._resolve_sided_targets",
            return_value=([(pair, side)], []),
        ),
        patch.object(children["left"].controller, "_wait", AsyncMock(return_value=False)),
        patch.object(children["right"].controller, "_wait", AsyncMock(return_value=False)),
    ):
        await hass.services.async_call(const.DOMAIN, route, parameters, blocking=True)
    for key, child in children.items():
        expected = []
        if side in (key, "both"):
            expected = [
                literal_frame(
                    child.controller.command_selector,
                    "m1" if route == "goto_preset" else "zeroGravity",
                )
            ]
            if route == "goto_preset" or key == "right":
                expected.append(literal_frame(child.controller.command_selector, "stop"))
        assert [
            call.args[1].hex() for call in child.controller.client.write_gatt_char.await_args_list
        ] == expected
        assert child.connection_holds == 0
