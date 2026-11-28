"""Purely Sleep selected normal controls through HA setup, entities and sessions."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import voluptuous as vol
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.exceptions import HomeAssistantError
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.beds.richmat.purely_sleep import (
    CLOCK,
    LIGHT,
    VERSION,
    PurelySleepController,
)
from custom_components.adjustable_bed.button import _button_entities_for
from custom_components.adjustable_bed.command_scheduler import Delivery, delivered
from custom_components.adjustable_bed.config_flow import AdjustableBedConfigFlow
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.cover import AdjustableBedCover, _build_cover_description
from custom_components.adjustable_bed.detection import bed_type_label
from custom_components.adjustable_bed.light import _light_entities_for
from custom_components.adjustable_bed.profile_id import resolve_profile_id
from custom_components.adjustable_bed.profiles.purely_sleep import PRODUCT_CHOICES
from custom_components.adjustable_bed.services import async_register_services
from tests.error_helpers import raises_key
from tests.form_helpers import form_answers, suggested
from tests.hold_lease_wire import intervals, leased_hold, virtual_clock
from tests.test_atlas_lift import client_on, frames, service, session_for
from tests.test_richmat_family_flow import answer, setup_flow

ADDRESS = "AA:BB:CC:DD:EE:71"


def packet(code, route="w1"):
    return bytes((code,)) if route == "n1" else bytes((0x6E, 1, 0, code, (0x6F + code) & 255))


@pytest.mark.parametrize("route", ("n1", "w1", "w2", "w3", "w4", "w5"))
@pytest.mark.parametrize("no_response", (False, True))
@pytest.mark.parametrize("product", ("JLRN", "VJRM"))
async def test_exact_service_roles_first_notify_write_mode_and_paced_startup(route, no_response, product):
    gatt = service(route, *("write", "write-without-response") if no_response else ("write",))
    client = client_on(gatt)
    ctrl = PurelySleepController(MagicMock(client=client), product=product)
    timed = []
    with virtual_clock() as clock:
        client.write_gatt_char.side_effect = lambda *args, **kwargs: timed.append(clock.now)
        await ctrl.async_on_connect(session_for(ctrl, client))
    assert frames(client) == (
        [bytes((n,)) for n in (0, 1, 1, 0, 0)]
        if route == "n1"
        else list(
            map(
                bytes.fromhex,
                ("6e02010071", "6e08010178", "6e0a000179", "6e2100008f", "6e9a000008"),
            )
        )
    )
    assert [round(t, 2) for t in timed] == [0, 0.1, 0.2, 0.3, 0.4]
    assert all(
        c.args[0] is gatt.characteristics[0] and c.kwargs["response"] is not no_response
        for c in client.write_gatt_char.await_args_list
    )
    assert client.start_notify.await_args.args[0] is gatt.characteristics[1]


@pytest.mark.parametrize("roles", (("n1", "w1"), ("w1", "n1"), ()))
async def test_ambiguous_or_missing_service_fails_before_writes(roles):
    client = client_on(*(service(route, "write") for route in roles))
    ctrl = PurelySleepController(MagicMock(client=client), product="VJRM")
    with raises_key("purely_sleep_gatt"):
        await ctrl.async_on_connect(session_for(ctrl, client))
    assert not frames(client)


@pytest.mark.parametrize("missing", ("write", "notify"))
async def test_a_usable_gatt_link_is_required(missing):
    gatt = service("w1", "write-without-response" if missing == "write" else "write")
    if missing == "notify":
        gatt.characteristics = gatt.characteristics[:1]
    client = client_on(gatt)
    ctrl = PurelySleepController(MagicMock(client=client), product="VJRM")
    with raises_key("purely_sleep_gatt"):
        await ctrl.async_on_connect(session_for(ctrl, client))
    assert not frames(client)


@pytest.mark.parametrize(
    "product",
    ("auto", "UFRM", "VERM", "F0RM", "U5RM", "VCRM", "LFRM", "JRRN", "JSRN", "JMRN", "JNRN"),
)
def test_unaccepted_products_are_never_silently_replaced(product):
    with raises_key("purely_sleep_product_required"):
        PurelySleepController(MagicMock(), product=product)


@pytest.mark.parametrize("product", ("JLRN", "VJRM"))
async def test_native_setup_requires_an_explicit_product(hass, product):
    flow = setup_flow(hass)
    result, _finish = await answer(flow, "purely_sleep")
    assert result["step_id"] == "profile_questions"
    assert result["data_schema"].schema[const.CONF_PROTOCOL_VARIANT].rows() == {
        label: code for code, label in PRODUCT_CHOICES.items()
    }
    assert suggested(result, const.CONF_PROTOCOL_VARIANT) is None
    with pytest.raises(vol.Invalid):
        result["data_schema"]({})
    with patch.object(flow, "_finish_with_verify", new=AsyncMock()) as finish:
        await flow.async_step_profile_questions({const.CONF_PROTOCOL_VARIANT: product})
    saved = finish.await_args.args[0]
    assert saved[const.CONF_BED_TYPE] == const.BED_TYPE_PURELY_SLEEP
    assert saved[const.CONF_MOTOR_COUNT] == 2
    assert saved[const.CONF_HAS_MASSAGE] is False
    assert resolve_profile_id(saved) == f"purely_sleep:{product}"
    assert "Purely Sleep" in bed_type_label(const.BED_TYPE_PURELY_SLEEP)


@pytest.mark.parametrize("origin", ("typed", "picked", "discovered"))
@pytest.mark.parametrize("product", ("JLRN", "VJRM"))
async def test_public_app_row_saves_each_explicit_product(
    hass, mock_bluetooth_service_info, origin, product
):
    flow = AdjustableBedConfigFlow()
    flow.hass, flow.context = hass, {"source": "user"}
    flow._async_transport_note = AsyncMock(return_value="")
    flow._app_after_device = "manual_entry" if origin == "typed" else "device"
    if origin != "typed":
        flow._discovery_info = mock_bluetooth_service_info
        flow._new_bed_origin = origin
    form = await flow.async_step_select_app({const.CONF_BED_TYPE: "purely_sleep"})
    if origin == "typed":
        form = await flow.async_step_manual_entry({CONF_ADDRESS: ADDRESS})
    assert form["step_id"] == "profile_questions"
    assert suggested(form, const.CONF_PROTOCOL_VARIANT) is None
    form = await flow.async_step_profile_questions({const.CONF_PROTOCOL_VARIANT: product})
    assert form["step_id"] == "finish_settings"
    with patch.object(flow, "_finish_with_verify", new=AsyncMock()) as finish:
        await flow.async_step_finish_settings(form_answers(form))
    finish.assert_awaited_once()
    saved = finish.await_args.args[0]
    assert saved[const.CONF_PROTOCOL_VARIANT] == product
    assert resolve_profile_id(saved) == f"purely_sleep:{product}"


@pytest.fixture
async def runtime(hass, request, mock_coordinator_connected, mock_bleak_client):
    product, route = getattr(request, "param", ("JLRN", "w1"))
    entry = MockConfigEntry(
        domain=const.DOMAIN,
        title="Purely Sleep",
        data={
            CONF_ADDRESS: ADDRESS,
            CONF_NAME: "Purely Sleep",
            const.CONF_BED_TYPE: const.BED_TYPE_PURELY_SLEEP,
            const.CONF_PROTOCOL_VARIANT: product,
            const.CONF_MOTOR_COUNT: 4,
            const.CONF_HAS_MASSAGE: True,
            const.CONF_MOTOR_PULSE_COUNT: 2,
            const.CONF_CONNECTION_MODE: const.CONNECTION_MODE_IDLE,
        },
    )
    entry.add_to_hass(hass)
    coordinator = AdjustableBedCoordinator(hass, entry)
    hass.data.setdefault(const.DOMAIN, {})[entry.entry_id] = coordinator
    mock_bleak_client.services = [service(route, "write")]
    mock_bleak_client.write_gatt_char = AsyncMock()
    mock_bleak_client.start_notify = AsyncMock()
    mock_bleak_client.stop_notify = AsyncMock()
    await coordinator.async_prime_offline_controller()
    await async_register_services(hass)
    try:
        with (
            patch(
                "custom_components.adjustable_bed.services._resolve_sided_targets",
                return_value=([(coordinator, "both")], []),
            ),
            virtual_clock(),
        ):
            yield coordinator, mock_bleak_client, product, route
    finally:
        await coordinator.async_shutdown()


@pytest.mark.parametrize(
    "runtime", (("JLRN", "w1"), ("JLRN", "n1"), ("VJRM", "w1"), ("VJRM", "n1")), indirect=True
)
async def test_real_buttons_axes_and_public_actions_respect_product_gates(hass, runtime):
    coordinator, client, product, route = runtime
    assert await coordinator.async_connect()
    ctrl = coordinator.controller
    assert isinstance(ctrl, PurelySleepController)
    assert [m.key for m in ctrl.motor_control_specs] == (
        ["back", "legs", "both"] if product == "JLRN" else ["back", "legs"]
    )
    assert not ctrl.position_number_specs
    assert not ctrl.supports_single_address_pairing
    assert not ctrl.supports_massage
    assert _light_entities_for(hass, coordinator) == []
    buttons = _button_entities_for(hass, coordinator)
    actions = {"preset_flat": 0x31, "preset_memory_1": 0x2E, "program_memory_1": 0x2B}
    if product == "JLRN":
        actions.update(
            {
                "preset_tv": 0x58,
                "preset_anti_snore": 0x46,
                "preset_lounge": 0x59,
                "preset_zero_g": 0x45,
                "purely_sleep_save_tv": 0x64,
                "purely_sleep_save_anti_snore": 0x69,
                "purely_sleep_save_lounge": 0x65,
                "purely_sleep_save_zero_g": 0x66,
            }
        )
        assert all(spec.requires_confirmation for spec in ctrl.controller_button_specs)
    else:
        assert not ctrl.controller_button_specs
        assert not ctrl.supports_preset_tv
        assert not ctrl.supports_preset_zero_g
    assert not any(
        b.unique_id.endswith(
            ("preset_memory_2", "program_memory_2", "lights_toggle", "massage_toggle")
        )
        for b in buttons
    )
    client.write_gatt_char.reset_mock()
    for key in actions:
        button = next(b for b in buttons if b.unique_id.endswith(key))
        await button.async_press()
    assert frames(client) == [packet(code, route) for code in actions.values()]
    client.write_gatt_char.reset_mock()
    for m in ctrl.motor_control_specs:
        cover = AdjustableBedCover(coordinator, _build_cover_description(m))
        cover.async_write_ha_state = MagicMock()
        await cover.async_open_cover()
        await cover.async_close_cover()
    expected = [
        code
        for codes in (
            ((0x24, 0x25), (0x26, 0x27), (0x29, 0x2A))
            if product == "JLRN"
            else ((0x24, 0x25), (0x26, 0x27))
        )
        for direction in codes
        for code in (direction, direction, 0x6E)
    ]
    assert frames(client) == [packet(code, route) for code in expected]
    client.write_gatt_char.reset_mock()
    for action in ("goto_preset", "save_preset"):
        await hass.services.async_call(
            const.DOMAIN, action, {"device_id": "bed", "preset": 1}, blocking=True
        )
    assert frames(client) == [packet(n, route) for n in (0x2E, 0x2B)]
    client.write_gatt_char.reset_mock()
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            const.DOMAIN, "goto_preset", {"device_id": "bed", "preset": 2}, blocking=True
        )
    assert not frames(client)


@pytest.mark.parametrize("runtime", (("JLRN", "w1"), ("VJRM", "n1")), indirect=True)
async def test_received_common_state_and_v1_gate_clear_only_on_new_version(runtime):
    coordinator, client, _, route = runtime
    assert await coordinator.async_connect()
    ctrl = coordinator.controller
    sender, receive = client.start_notify.await_args.args
    receive(sender, bytearray.fromhex("6e09010078"))
    receive(sender, bytearray.fromhex("6e0e00037f"))
    assert coordinator.controller_state[CLOCK] is True
    assert coordinator.controller_state[LIGHT] is True
    receive(sender, bytearray.fromhex("6e900001ff"))  # Branch does not prove checksum enforcement.
    assert coordinator.controller_state[VERSION] == 1
    assert ctrl.protocol_diagnostics["protocol_version"] == 1
    assert ctrl.protocol_diagnostics["clock_reply_seen"] is True
    assert ctrl.protocol_diagnostics["light_reply_seen"] is True
    assert not ctrl.controller_state_sensor_specs
    client.write_gatt_char.reset_mock()
    with raises_key("purely_sleep_version_one"):
        await ctrl.preset_flat()
    with raises_key("purely_sleep_version_one"):
        ctrl.validate_memory_recall(1)
    assert not ctrl.supports_memory_programming
    assert not frames(client)
    await ctrl.stop_all()
    assert frames(client) == [packet(0x6E, route)]
    ctrl.on_disconnect()
    assert coordinator.controller_state[VERSION] is None
    receive(sender, bytearray.fromhex("6e90000000"))
    assert ctrl._version == 1  # Stale callback cannot change a retired session.


@pytest.mark.parametrize(
    "scenario",
    ("purely_sleep", "purely_sleep:JLRN:n1", "purely_sleep:VJRM:n1", "purely_sleep:VJRM:w1"),
)
async def test_hold_lease_repeats_at_100ms_and_releases(scenario):
    wire = await leased_hold(scenario, lambda c: c.move_back_up(), end_after_s=2, end="expire")
    route = "n1" if scenario.endswith(":n1") else "w1"
    assert wire.held[0].at_ms == 100
    assert intervals(wire.held) == {100}
    assert {e.data for e in wire.held} == {packet(0x24, route)}
    assert [e.data for e in wire.after] == [packet(0x6E, route)]


async def test_inflight_write_settles_before_cancel_stop_and_no_retry(runtime):
    coordinator, client, _, route = runtime
    assert await coordinator.async_connect()
    client.write_gatt_char.reset_mock()
    began, finish = asyncio.Event(), asyncio.Event()

    async def write(_char, frame, **kwargs):
        if frame == packet(0x24, route):
            began.set()
            await finish.wait()

    client.write_gatt_char.side_effect = write
    running = asyncio.create_task(
        coordinator.async_execute_controller_command(lambda c: c.move_back_up())
    )
    await began.wait()
    stop = asyncio.create_task(coordinator.async_stop_command())
    await asyncio.sleep(0)
    assert not stop.done()
    finish.set()
    await asyncio.gather(running, stop)
    assert frames(client) == [packet(0x24, route), packet(0x6E, route)]


async def test_stop_waits_for_an_inflight_write_then_sends_one_fifo_release(runtime):
    coordinator, client, _, route = runtime
    assert await coordinator.async_connect()
    client.write_gatt_char.reset_mock()
    entered, finish = asyncio.Event(), asyncio.Event()

    async def write(_characteristic, frame, **kwargs):
        if frame == packet(0x24, route):
            entered.set()
            await finish.wait()

    client.write_gatt_char.side_effect = write
    movement = asyncio.create_task(
        coordinator.async_execute_controller_command(lambda ctrl: ctrl.move_back_up())
    )
    await entered.wait()
    stop = asyncio.create_task(coordinator.async_stop_command())
    await asyncio.sleep(0)
    assert not stop.done()
    assert frames(client) == [packet(0x24, route)]
    finish.set()
    await asyncio.gather(movement, stop)
    assert frames(client) == [packet(n, route) for n in (0x24, 0x6E)]


async def test_replaced_link_cannot_receive_a_queued_preset():
    old = client_on(service("w1", "write"))
    coordinator = MagicMock(client=old, cancel_command=asyncio.Event())
    ctrl = PurelySleepController(coordinator, product="JLRN")
    with virtual_clock():
        await ctrl.async_on_connect(session_for(ctrl, old))
        old.write_gatt_char.reset_mock()
        async with ctrl.ble_lock:
            running = asyncio.create_task(ctrl.preset_tv())
            await asyncio.sleep(0)
            ctrl.on_disconnect()
            coordinator.client = new = client_on(service("n1", "write"))
        with pytest.raises(ConnectionError):
            await running
        await ctrl.async_on_connect(session_for(ctrl, new))
        new.write_gatt_char.reset_mock()
        await ctrl.preset_tv()
    assert not frames(old)
    assert frames(new) == [b"\x58"]


@pytest.mark.parametrize("action", ("goto_preset", "save_preset"))
async def test_pair_checks_every_live_target_before_recalling_or_saving(hass, action):
    from tests.test_shared_action_hardening import beds

    with virtual_clock():
        async with beds(hass, topology="concurrent") as made:
            for product, bed in zip(("JLRN", "VJRM"), made.items, strict=True):
                ctrl = PurelySleepController(bed, product=product)
                bed._controller = bed._offline_controller = ctrl
                bed.client.services = [service("w1", "write")]
                bed.client.write_gatt_char = AsyncMock()
                bed.client.start_notify = AsyncMock()
                await ctrl.async_on_connect(session_for(ctrl, bed.client))
                bed.client.write_gatt_char.reset_mock()
            made.items[1].controller._receive_notification("notify", bytes.fromhex("6e90000100"))
            with (
                patch(
                    "custom_components.adjustable_bed.services._resolve_sided_targets",
                    return_value=([(made.pair, "both")], []),
                ),
                pytest.raises(HomeAssistantError),
            ):
                await hass.services.async_call(
                    const.DOMAIN, action, {"device_id": "pair", "preset": 1}, blocking=True
                )
            assert all(not frames(bed.client) for bed in made.items)


async def test_sequential_pair_routes_only_the_target_side_and_reconnects_for_stop(hass):
    from tests.test_shared_action_hardening import beds

    with virtual_clock():
        async with beds(hass, topology="sequential", connected=False) as made:
            sessions = []

            def connector(bed, product, route):
                async def connect(**kwargs):
                    if bed.is_connected:
                        return True
                    assert not any(peer.is_connected for peer in made.items if peer is not bed)
                    assert await bed.fake_connect(**kwargs)
                    client = bed.client
                    client.services = [service(route, "write")]
                    client.write_gatt_char = AsyncMock()
                    client.start_notify = AsyncMock()
                    client.stop_notify = AsyncMock()
                    bed._controller = ctrl = PurelySleepController(bed, product=product)
                    await ctrl.async_on_connect(session_for(ctrl, client))
                    client.write_gatt_char.reset_mock()
                    sessions.append((product, route, client))
                    return True

                return connect

            for bed, product, route in zip(made.items, ("JLRN", "VJRM"), ("n1", "w1"), strict=True):
                bed._offline_controller = PurelySleepController(bed, product=product)
                bed.async_connect.side_effect = bed.async_ensure_connected.side_effect = connector(
                    bed, product, route
                )
            with patch(
                "custom_components.adjustable_bed.services._resolve_sided_targets",
                side_effect=lambda *args, **kwargs: [(made.pair, "right")],
            ):
                # Use the pair's routing API directly for a right-only native action.
                await made.pair.async_execute_controller_command(
                    lambda ctrl: ctrl.preset_memory(1), side="right"
                )
                await made.pair.async_stop_motor(
                    lambda ctrl: ctrl.move_back_stop(), "motor:back", side="right"
                )
            assert [product for product, _, _ in sessions] == ["VJRM", "VJRM"]
            assert [frames(client) for _, route, client in sessions] == [
                [packet(0x2E)],
                [packet(0x6E)],
            ]
            assert not any(bed.is_connected for bed in made.items)


@pytest.mark.parametrize("reason", ("cancel", "write_failure", "version_one"))
async def test_motion_cleanup_survives_cancellation_failure_and_version_change(runtime, reason):
    from bleak.exc import BleakError

    coordinator, client, _, route = runtime
    assert await coordinator.async_connect()
    ctrl = coordinator.controller
    client.write_gatt_char.reset_mock()
    entered, finish = asyncio.Event(), asyncio.Event()

    async def write(_char, frame, **_kwargs):
        if frame == packet(0x24, route):
            entered.set()
            await finish.wait()
            if reason == "write_failure":
                raise BleakError("Rejected")
            if reason == "version_one":
                ctrl._receive_notification("notify", bytes.fromhex("6e90000100"))

    client.write_gatt_char.side_effect = write
    holding = asyncio.create_task(ctrl.move_back_up())
    await entered.wait()
    if reason == "cancel":
        holding.cancel()
    finish.set()
    expected = (
        asyncio.CancelledError
        if reason == "cancel"
        else BleakError
        if reason == "write_failure"
        else HomeAssistantError
    )
    with pytest.raises(expected):
        await holding
    assert frames(client) == [packet(n, route) for n in (0x24, 0x6E)]


@pytest.mark.parametrize("runtime", (("JLRN", "w1"), ("VJRM", "n1")), indirect=True)
async def test_real_reconnect_retains_version_exclusion_until_a_fresh_reply(runtime):
    coordinator, client, _, route = runtime
    assert await coordinator.async_connect()
    first = coordinator.controller
    sender, receive = client.start_notify.await_args.args
    receive(sender, bytearray.fromhex("6e90000100"))
    assert await coordinator.async_disconnect()
    assert await coordinator.async_connect()
    assert coordinator.controller is not first
    # A callback captured from the previous subscription cannot clear the guard.
    receive(sender, bytearray.fromhex("6e90000000"))
    receive(sender, bytearray.fromhex("6e09010078"))
    receive(sender, bytearray.fromhex("6e0e00037f"))
    assert coordinator.controller_state[CLOCK] is None
    assert coordinator.controller_state[LIGHT] is None
    # Startup queries are still allowed; there has been no fresh version reply.
    assert len(frames(client)) == 10
    client.write_gatt_char.reset_mock()
    with raises_key("purely_sleep_version_one"):
        await coordinator.controller.preset_flat()
    assert not frames(client)
    await coordinator.controller.stop_all()
    assert frames(client) == [packet(0x6E, route)]
    sender, receive = client.start_notify.await_args.args
    receive(sender, bytearray.fromhex("6e90000000"))
    client.write_gatt_char.reset_mock()
    await coordinator.controller.preset_flat()
    assert frames(client) == [packet(0x31, route)]
    assert await coordinator.async_disconnect()
    assert await coordinator.async_connect()
    client.write_gatt_char.reset_mock()
    await coordinator.controller.preset_flat()
    assert frames(client) == [packet(0x31, route)]


TIMED_AXES = (
    (("JLRN", "w1"), "back", 0x24),
    (("JLRN", "w1"), "legs", 0x26),
    (("JLRN", "w1"), "both", 0x29),
    (("VJRM", "n1"), "back", 0x24),
    (("VJRM", "n1"), "legs", 0x26),
)


@pytest.mark.parametrize(("runtime", "motor", "code"), TIMED_AXES, indirect=["runtime"])
async def test_public_timed_axes_keep_the_immediate_pulse_and_release(hass, runtime, motor, code):
    from custom_components.adjustable_bed.beds.richmat import atlas_lift, fixed, purely_sleep

    coordinator, client, _, route = runtime
    assert await coordinator.async_connect()
    assert atlas_lift._Link is purely_sleep._Link is fixed._Link
    assert type(coordinator.controller._current_link()) is fixed._Link
    await asyncio.sleep(0.1)  # Let the last startup query's FIFO interval elapse.
    client.write_gatt_char.reset_mock()
    recorded = []
    loop = asyncio.get_running_loop()
    started = loop.time()

    async def write(_characteristic, frame, **kwargs):
        recorded.append((round((loop.time() - started) * 1000), frame))

    client.write_gatt_char.side_effect = write
    await hass.services.async_call(
        const.DOMAIN,
        "timed_move",
        {"device_id": "bed", "motor": motor, "direction": "up", "duration_ms": 100},
        blocking=True,
    )
    assert recorded == [(0, packet(code, route)), (100, packet(0x6E, route))]


@pytest.mark.parametrize(("runtime", "motor", "code"), TIMED_AXES, indirect=["runtime"])
async def test_native_timed_axis_cancel_settles_before_one_release(runtime, motor, code):
    coordinator, client, _, route = runtime
    assert await coordinator.async_connect()
    await asyncio.sleep(0.1)
    controller = coordinator.controller
    timed_move = next(s for s in controller.motor_control_specs if s.key == motor).timed_move_fn
    assert timed_move is not None
    client.write_gatt_char.reset_mock()
    entered, finish = asyncio.Event(), asyncio.Event()

    async def write(_characteristic, frame, **kwargs):
        if frame == packet(code, route):
            entered.set()
            await finish.wait()

    client.write_gatt_char.side_effect = write
    task = asyncio.create_task(
        coordinator.async_execute_controller_command(lambda ctrl: timed_move(ctrl, True, 350))
    )
    await entered.wait()
    task.cancel()
    await asyncio.sleep(0)
    assert not task.done() and frames(client) == [packet(code, route)]
    finish.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert frames(client) == [packet(code, route), packet(0x6E, route)]


@pytest.mark.parametrize(("selection", "motor", "code"), TIMED_AXES)
async def test_queued_native_timed_axis_cannot_cross_a_replacement(selection, motor, code):
    product, route = selection
    old = client_on(service(route, "write"))
    coordinator = MagicMock(
        client=old,
        cancel_command=asyncio.Event(),
        motor_count=2,
        motor_pulse_count=2,
        motor_pulse_delay_ms=100,
    )
    controller = PurelySleepController(coordinator, product=product)
    with virtual_clock():
        await controller.async_on_connect(session_for(controller, old))
        timed_move = next(s for s in controller.motor_control_specs if s.key == motor).timed_move_fn
        assert timed_move is not None
        old.write_gatt_char.reset_mock()
        async with controller.ble_lock:
            task = asyncio.create_task(timed_move(controller, True, 350))
            await asyncio.sleep(0.15)
            controller.on_disconnect()
            new = client_on(service("n1" if route == "w1" else "w1", "write"))
            coordinator.client = new
        with pytest.raises(ConnectionError):
            await task
        await controller.async_on_connect(session_for(controller, new))
        new.write_gatt_char.reset_mock()
        old.write_gatt_char.assert_not_awaited()
        new.write_gatt_char.assert_not_awaited()


@pytest.mark.parametrize(
    ("address", "product", "excluded"),
    ((ADDRESS, "JLRN", True), (ADDRESS, "VJRM", False), ("AA:BB:CC:DD:EE:72", "JLRN", False)),
)
async def test_replacement_coordinators_restore_only_the_same_physical_product(
    hass, runtime, address, product, excluded
):
    from tests.app_state_helpers import restart_app_state

    coordinator, client, _, _ = runtime
    assert await coordinator.async_connect()
    sender, receive = client.start_notify.await_args.args
    receive(sender, bytearray.fromhex("6e90000100"))
    assert await coordinator.async_disconnect()
    await restart_app_state(hass, ADDRESS)
    entry = MockConfigEntry(
        domain=const.DOMAIN,
        data={
            CONF_ADDRESS: address,
            CONF_NAME: "Purely Sleep",
            const.CONF_BED_TYPE: const.BED_TYPE_PURELY_SLEEP,
            const.CONF_PROTOCOL_VARIANT: product,
        },
    )
    entry.add_to_hass(hass)
    replacement = AdjustableBedCoordinator(hass, entry)
    try:
        assert await replacement.async_connect()
        restored = replacement.controller
        assert isinstance(restored, PurelySleepController)
        if excluded:
            with raises_key("purely_sleep_version_one"):
                restored.validate_button_press("preset_flat")
        else:
            restored.validate_button_press("preset_flat")
    finally:
        await replacement.async_shutdown()


@pytest.mark.parametrize(
    "key", ("preset_tv", "preset_flat", "preset_anti_snore", "preset_zero_g", "preset_lounge")
)
@pytest.mark.parametrize("already_created", (False, True))
async def test_native_both_presets_preflight_each_version_before_any_peer_write(
    hass, key, already_created
):
    from custom_components.adjustable_bed.button import _combined_button_entities_for
    from tests.test_shared_action_hardening import beds

    with virtual_clock():
        async with beds(hass, topology="concurrent") as made:
            for bed in made.items:
                ctrl = PurelySleepController(bed, product="JLRN")
                bed._controller = bed._offline_controller = ctrl
                bed.client.services = [service("w1", "write")]
                bed.client.write_gatt_char = AsyncMock()
                bed.client.start_notify = AsyncMock()
                await ctrl.async_on_connect(session_for(ctrl, bed.client))
                bed.client.write_gatt_char.reset_mock()
            buttons = (
                _combined_button_entities_for(made.pair, made.items) if already_created else None
            )
            made.items[1].controller._receive_notification("notify", bytes.fromhex("6e90000100"))
            if buttons is None:
                buttons = _combined_button_entities_for(made.pair, made.items)
            button = next(b for b in buttons if b.entity_description.key == key)
            with raises_key("purely_sleep_version_one"):
                await button.async_press()
            assert all(not frames(bed.client) for bed in made.items)
            # Resolving a fresh normal version makes the same entity usable again.
            made.items[1].controller._receive_notification("notify", bytes.fromhex("6e90000000"))
            await button.async_press()
            opcode = {
                "preset_tv": 0x58,
                "preset_flat": 0x31,
                "preset_anti_snore": 0x46,
                "preset_zero_g": 0x45,
                "preset_lounge": 0x59,
            }[key]
            assert all(frames(bed.client) == [packet(opcode)] for bed in made.items)


@pytest.mark.parametrize("waiting_for", ("lock", "pacing"))
async def test_cancelled_second_write_records_partial_delivery(runtime, waiting_for):
    coordinator, client, _, route = runtime
    assert await coordinator.async_connect()
    ctrl = coordinator.controller
    client.write_gatt_char.reset_mock()
    first, proceed = asyncio.Event(), asyncio.Event()
    operations, outcomes = [], []

    async def operation(live):
        operations.append(asyncio.current_task())
        with delivered(outcomes.append):
            await live.preset_tv()
            first.set()
            await proceed.wait()
            await live.preset_zero_g()

    task = asyncio.create_task(coordinator.async_execute_controller_command(operation))
    await first.wait()
    if waiting_for == "lock":
        async with ctrl.ble_lock:
            proceed.set()
            await asyncio.sleep(0)
            operations[0].cancel()
            await asyncio.sleep(0)
    else:
        ctrl._next_write = asyncio.get_running_loop().time() + 3600
        proceed.set()
        await asyncio.sleep(0)
        operations[0].cancel()
    await task
    assert frames(client) == [packet(0x58, route)]
    assert outcomes == [Delivery.PARTIAL]
