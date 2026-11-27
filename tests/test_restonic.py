"""Actual HA callers, captured-session STOP, and cancellation at GATT admission."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.beds.restonic import controller as bed
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.profiles import restonic as app
from custom_components.adjustable_bed.setup_questions import _restonic_settings
from tests.hold_lease_wire import virtual_clock

ADDRESS = "AA:BB:CC:DD:AA:48"


class Char:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


def gatt(branch):
    route = app.TRANSPORTS[branch]
    write = Char(
        uuid=route.write,
        handle=1,
        properties=["write" if route.response else "write-without-response"],
        descriptors=[],
    )
    notify = Char(uuid=route.notify, handle=2, properties=["notify"], descriptors=[])

    def service(uuid, chars):
        return SimpleNamespace(
            uuid=uuid,
            characteristics=chars,
            get_characteristic=lambda key: next((c for c in chars if c.uuid == key), None),
        )

    return (
        [service(route.service, [write]), service(route.notify_service, [notify])]
        if branch == "box15"
        else [service(route.service, [write, notify])]
    )


def entry(hass, branch="box15", layout="prime"):
    data = {
        CONF_ADDRESS: ADDRESS,
        CONF_NAME: "Restonic",
        const.CONF_BED_TYPE: "restonic",
        const.CONF_PROTOCOL_VARIANT: branch,
        const.CONF_PRODUCT_TYPE: layout,
        const.CONF_CONNECTION_MODE: const.CONNECTION_MODE_IDLE,
    }
    data.update(_restonic_settings(data))
    e = MockConfigEntry(domain=const.DOMAIN, title="Restonic", unique_id=ADDRESS, data=data)
    e.add_to_hass(hass)
    return e


def writes(client):
    return [bytes(call.args[1]) for call in client.write_gatt_char.call_args_list]


@pytest.mark.parametrize("branch", app.TRANSPORTS)
@pytest.mark.parametrize("layout", app.LAYOUT_CHOICES)
async def test_real_setup_every_action_and_entity(
    hass, mock_coordinator_connected, mock_bleak_client, enable_custom_integrations, branch, layout
):
    mock_bleak_client.services = gatt(branch)
    e = entry(hass, branch, layout)
    assert await hass.config_entries.async_setup(e.entry_id)
    await hass.async_block_till_done()
    target = hass.data[const.DOMAIN][e.entry_id]
    c = target.controller
    assert isinstance(c, bed.RestonicController)
    registry = er.async_get(hass)
    entities = [v for v in registry.entities.values() if v.config_entry_id == e.entry_id]
    device = next(v.device_id for v in entities if v.device_id)
    assert not c.supports_memory_programming
    assert not c.supports_single_address_pairing
    assert not c.position_number_specs
    assert len(c.motor_control_specs) == len(app.AXES[layout])
    assert len(c.controller_button_specs) == (1 if layout == "prime" else 6)
    assert all(not s.entity_registry_enabled_default for s in c.controller_state_sensor_specs)
    assert not mock_bleak_client.write_gatt_char.called
    with virtual_clock():
        for action in app.ACTIONS[layout]:
            mock_bleak_client.write_gatt_char.reset_mock()
            await hass.services.async_call(
                const.DOMAIN,
                "hold_control",
                {"device_id": device, "control": action, "duration": 0.1},
                blocking=True,
            )
            assert writes(mock_bleak_client) == [
                app.encode(branch, action),
                app.encode(branch, "stop"),
                app.encode(branch, "stop"),
            ]
            assert all(
                call.kwargs["response"] is app.TRANSPORTS[branch].response
                for call in mock_bleak_client.write_gatt_char.call_args_list
            )
        mock_bleak_client.write_gatt_char.reset_mock()
        await hass.services.async_call(
            const.DOMAIN,
            "timed_move",
            {"device_id": device, "motor": "head", "direction": "up", "duration_ms": 450},
            blocking=True,
        )
        assert (
            writes(mock_bleak_client)
            == [app.encode(branch, "headUp")] * 3 + [app.encode(branch, "stop")] * 2
        )
        mock_bleak_client.write_gatt_char.reset_mock()
        await target.async_stop_command()
        assert writes(mock_bleak_client) == [app.encode(branch, "stop")] * 2
        preset = registry.async_get_entity_id("button", const.DOMAIN, f"{ADDRESS}_preset_zero_g")
        assert hass.states.get(preset).attributes["held_control"] == "zeroGravity"
        mock_bleak_client.write_gatt_char.reset_mock()
        light = registry.async_get_entity_id(
            "button", const.DOMAIN, f"{ADDRESS}_restonic_underbedLighting"
        )
        assert light
        await hass.services.async_call("button", "press", {"entity_id": light}, blocking=True)
        assert writes(mock_bleak_client) == [
            app.encode(branch, "underbedLighting"),
            app.encode(branch, "stop"),
            app.encode(branch, "stop"),
        ]
    await hass.config_entries.async_unload(e.entry_id)


async def connected(hass, client, layout="infinity"):
    client.services = gatt("box24")
    e = entry(hass, "box24", layout)
    coordinator = AdjustableBedCoordinator(hass, e)
    coordinator._client = client
    c = bed.RestonicController(coordinator, branch="box24", layout=layout)
    coordinator._controller = c
    await c.async_discover_capabilities()
    return coordinator, c


async def test_cancelled_waiter_sends_no_motion_or_stop(hass, mock_bleak_client):
    co, c = await connected(hass, mock_bleak_client)
    async with c.ble_lock:
        task = asyncio.create_task(c.hold_control("head_up", 1000))
        await asyncio.sleep(0)
        co.cancel_command.set()
    await task
    assert not mock_bleak_client.write_gatt_char.called


async def test_expired_waiter_sends_no_motion_or_stop(hass, mock_bleak_client):
    _, c = await connected(hass, mock_bleak_client)
    with virtual_clock():
        async with c.ble_lock:
            task = asyncio.create_task(c.hold_control("head_up", 100))
            await asyncio.sleep(0)
            await asyncio.sleep(0.2)
        await task
    assert not mock_bleak_client.write_gatt_char.called


async def test_cancel_inflight_settles_before_both_stops(hass, mock_bleak_client):
    _, c = await connected(hass, mock_bleak_client)
    started, finish = asyncio.Event(), asyncio.Event()
    seen = []

    async def write(char, frame, **kw):
        seen.append(bytes(frame))
        if len(seen) == 1:
            started.set()
            await finish.wait()

    mock_bleak_client.write_gatt_char.side_effect = write
    task = asyncio.create_task(c.hold_control("head_up", 1000))
    await started.wait()
    task.cancel()
    await asyncio.sleep(0)
    assert len(seen) == 1 and not task.done()
    with virtual_clock():
        finish.set()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert seen == [app.encode("box24", "headUp"), *[app.encode("box24", "stop")] * 2]


async def test_replacement_link_gets_no_old_refresh_or_cleanup(hass, mock_bleak_client):
    co, c = await connected(hass, mock_bleak_client)
    replacement = AsyncMock()
    replacement.is_connected = True

    async def switch(*args, **kw):
        co._client = replacement

    mock_bleak_client.write_gatt_char.side_effect = switch
    with virtual_clock(), pytest.raises(ConnectionError):
        await c.hold_control("head_up", 500)
    assert len(writes(mock_bleak_client)) == 1
    assert not replacement.write_gatt_char.called


async def test_notifications_are_raw_current_link_only_and_reset(hass, mock_bleak_client):
    co, c = await connected(hass, mock_bleak_client)
    await c.start_notify()
    callback = mock_bleak_client.start_notify.call_args.args[1]
    notify = c._link.notify
    callback(notify, bytearray.fromhex("a50b0e002f00020306"))
    assert c.protocol_diagnostics["received"]["b"] == 7
    c.on_disconnect()
    callback(notify, bytearray.fromhex("a50b0e000200020306"))
    assert c.protocol_diagnostics["received"] == {}


async def test_task_cancelled_waiter_never_starts_gatt(hass, mock_bleak_client):
    _, c = await connected(hass, mock_bleak_client)
    async with c.ble_lock:
        task = asyncio.create_task(c.hold_control("head_up", 1000))
        await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert not mock_bleak_client.write_gatt_char.called


@pytest.mark.parametrize("branch", app.TRANSPORTS)
@pytest.mark.parametrize("layout", app.LAYOUT_CHOICES)
async def test_explicit_setup_and_offline_capabilities(hass, branch, layout):
    from custom_components.adjustable_bed.app_profiles import per_side_profile
    from custom_components.adjustable_bed.config_flow import AdjustableBedConfigFlow
    from custom_components.adjustable_bed.controller_factory import create_controller
    from custom_components.adjustable_bed.detection import BED_TYPE_DISPLAY_NAMES
    from custom_components.adjustable_bed.setup_questions import REQUIRED, setup_profile_for
    from tests.form_helpers import finish_new_bed
    from tests.test_controller_contract import _FactoryCoordinator

    flow = AdjustableBedConfigFlow()
    flow.hass, flow.context = hass, {}
    flow._app_after_device = "manual_entry"
    flow._finish_with_verify = AsyncMock(return_value={"type": "create_entry"})
    await flow.async_step_select_app()
    await flow.async_step_select_app({const.CONF_BED_TYPE: BED_TYPE_DISPLAY_NAMES["restonic"]})
    result = await flow.async_step_manual_entry({"address": ADDRESS})
    assert result["step_id"] == "profile_questions"
    profile = setup_profile_for({const.CONF_BED_TYPE: "restonic"})
    assert profile.questions[0].default_for({}) is REQUIRED
    assert profile.questions[1].default_for({}) is REQUIRED
    result = await flow.async_step_profile_questions(
        {const.CONF_PROTOCOL_VARIANT: branch, const.CONF_PRODUCT_TYPE: layout}
    )
    await finish_new_bed(flow, result)
    saved = flow._finish_with_verify.await_args.args[0]
    assert saved[const.CONF_MOTOR_COUNT] == len(app.AXES[layout])
    assert saved.get(const.CONF_DISABLE_ANGLE_SENSING, True)
    assert not saved.get(const.CONF_HAS_MASSAGE, False)
    assert const.CONF_PRODUCT_TYPE in per_side_profile("restonic", branch).keys
    co = _FactoryCoordinator()
    co.entry.data = saved
    c = await create_controller(co, "restonic", branch, None)
    assert c.layout == layout and c.branch == branch
    assert len(c.motor_control_specs) == len(app.AXES[layout])
    assert not c.supports_memory_programming


async def test_exact_hold_deadline_and_two_stop_cadence(hass, mock_bleak_client):
    _, c = await connected(hass, mock_bleak_client)
    seen = []

    async def write(char, frame, **kw):
        seen.append((asyncio.get_running_loop().time(), bytes(frame)))

    mock_bleak_client.write_gatt_char.side_effect = write
    with virtual_clock():
        await c.hold_control("head_up", 450)
    base = seen[0][0]
    assert [(round((t - base) * 1000), frame) for t, frame in seen] == [
        (0, app.encode("box24", "headUp")),
        (200, app.encode("box24", "headUp")),
        (400, app.encode("box24", "headUp")),
        (450, app.encode("box24", "stop")),
        (650, app.encode("box24", "stop")),
    ]


async def test_stalled_write_is_bounded_and_then_cleanup(hass, mock_bleak_client):
    _, c = await connected(hass, mock_bleak_client)
    calls = []

    async def write(char, frame, **kw):
        calls.append(bytes(frame))
        if len(calls) == 1:
            await asyncio.Event().wait()

    mock_bleak_client.write_gatt_char.side_effect = write
    with virtual_clock(), pytest.raises(TimeoutError):
        await c.hold_control("head_up", 1000)
    assert calls == [app.encode("box24", "headUp"), *[app.encode("box24", "stop")] * 2]


@pytest.mark.parametrize("branch", ("box15", "box1220", "box24"))
async def test_renewable_hold_outlasts_finite_press_and_expires_with_release(branch):
    from tests.hold_lease_wire import intervals, leased_hold

    scenario = "restonic" if branch == "box15" else f"restonic:{branch}:prime"
    result = await leased_hold(scenario, lambda c: c.move_head_up(), end_after_s=3.15, end="expire")
    assert len(result.held) > result.pulse_count
    assert intervals(result.held) == {200}
    assert all(write.data == app.encode(branch, "headUp") for write in result.held)
    assert [w.data for w in result.after] == [app.encode(branch, "stop")] * 2
    assert [w.at_ms - result.ended_ms for w in result.after] == [0, 200]


@pytest.mark.parametrize("branch", app.TRANSPORTS)
async def test_active_public_stop_consumes_only_its_completed_same_link_cleanup(
    hass, mock_coordinator_connected, mock_bleak_client, enable_custom_integrations, branch
):
    mock_bleak_client.services = gatt(branch)
    e = entry(hass, branch)
    assert await hass.config_entries.async_setup(e.entry_id)
    await hass.async_block_till_done()
    co = hass.data[const.DOMAIN][e.entry_id]
    c = co.controller
    first = asyncio.Event()

    async def record(*args, **kwargs):
        first.set()

    mock_bleak_client.write_gatt_char.side_effect = record
    with virtual_clock():
        movement = asyncio.create_task(
            co.async_execute_controller_command(
                lambda controller: controller.hold_control("head_up", 1000)
            )
        )
        await first.wait()
        await co.async_stop_command()
        await asyncio.gather(movement, return_exceptions=True)
        assert writes(mock_bleak_client) == [
            app.encode(branch, "headUp"),
            *[app.encode(branch, "stop")] * 2,
        ]
        assert c._cleanup is None
        # The acknowledgement was consumed, not a global suppression of STOP.
        mock_bleak_client.write_gatt_char.reset_mock()
        await co.async_stop_command()
        assert writes(mock_bleak_client) == [app.encode(branch, "stop")] * 2
    await hass.config_entries.async_unload(e.entry_id)


@pytest.mark.parametrize("branch", app.TRANSPORTS)
@pytest.mark.parametrize("revocation", ("event", "caller", "replacement"))
async def test_ready_callback_cannot_revoke_admission_before_gatt_entry(
    hass, mock_bleak_client, branch, revocation
):
    co, c = await connected(hass, mock_bleak_client)
    # Rebuild the same physical session on each app transport.
    mock_bleak_client.services = gatt(branch)
    c = bed.RestonicController(co, branch=branch, layout="infinity")
    co._controller = c
    await c.async_discover_capabilities()
    replacement = AsyncMock()
    replacement.is_connected = True
    entered = asyncio.Event()
    observations = []

    async def write(char, frame, **kwargs):
        if bytes(frame) != app.encode(branch, "headUp"):
            return
        observations.append(
            (co.cancel_command.is_set(), movement.cancelling(), co.client is mock_bleak_client)
        )
        entered.set()
        # Let the already-ready revocation callback run during the in-flight
        # write. The new writer must have entered GATT before that callback.
        await asyncio.sleep(0)

    mock_bleak_client.write_gatt_char.side_effect = write
    loop = asyncio.get_running_loop()
    with virtual_clock():
        movement = asyncio.create_task(c.hold_control("head_up", 100))
        if revocation == "event":
            loop.call_soon(co.cancel_command.set)
        elif revocation == "caller":
            loop.call_soon(movement.cancel)
        else:
            loop.call_soon(setattr, co, "_client", replacement)
        await asyncio.gather(movement, return_exceptions=True)
    assert entered.is_set()
    assert observations == [(False, 0, True)]
    assert not replacement.write_gatt_char.called
    expected = [app.encode(branch, "headUp")]
    if revocation != "replacement":
        expected += [app.encode(branch, "stop")] * 2
    assert writes(mock_bleak_client) == expected


@pytest.mark.parametrize("revocation", ("event", "caller", "replacement"))
async def test_revocation_before_lane_admission_sends_nothing(hass, mock_bleak_client, revocation):
    co, c = await connected(hass, mock_bleak_client)
    replacement = AsyncMock()
    replacement.is_connected = True
    async with c.ble_lock:
        movement = asyncio.create_task(c.hold_control("head_up", 100))
        await asyncio.sleep(0)
        if revocation == "event":
            co.cancel_command.set()
        elif revocation == "caller":
            movement.cancel()
        else:
            co._client = replacement
    await asyncio.gather(movement, return_exceptions=True)
    assert not mock_bleak_client.write_gatt_char.called
    assert not replacement.write_gatt_char.called


@pytest.mark.parametrize("branch", app.TRANSPORTS)
@pytest.mark.parametrize("schedule", ("queued_controller", "resumed_ble_waiter"))
async def test_public_caller_cancellation_before_gatt_sends_nothing(
    hass,
    mock_coordinator_connected,
    mock_bleak_client,
    enable_custom_integrations,
    branch,
    schedule,
):
    from custom_components.adjustable_bed.command_scheduler import current_command_context

    mock_bleak_client.services = gatt(branch)
    e = entry(hass, branch)
    assert await hass.config_entries.async_setup(e.entry_id)
    await hass.async_block_till_done()
    co = hass.data[const.DOMAIN][e.entry_id]
    c = co.controller
    observations = []
    entered = asyncio.Event()

    async def record(char, frame, **kwargs):
        if bytes(frame) == app.encode(branch, "headUp"):
            context = current_command_context()
            assert context is not None and context.caller_is_cancelling is not None
            observations.append(
                (
                    movement.cancelling(),
                    context.cancel_event.is_set(),
                    context.caller_is_cancelling(),
                )
            )

    def queued_command(controller):
        # Cancel the public caller before the separately queued controller task
        # runs, without waiting for its scheduler event to catch up.
        asyncio.get_running_loop().call_soon(movement.cancel)
        return controller.hold_control("head_up", 1000)

    async def waiting_command(controller):
        entered.set()
        await controller.hold_control("head_up", 1000)

    mock_bleak_client.write_gatt_char.side_effect = record
    with virtual_clock():
        if schedule == "queued_controller":
            movement = asyncio.create_task(co.async_execute_controller_command(queued_command))
        else:
            async with c.ble_lock:
                movement = asyncio.create_task(co.async_execute_controller_command(waiting_command))
                await entered.wait()
            # Releasing the lane makes its waiter ready first. Cancellation of
            # the public caller must still be visible at final GATT admission.
            movement.cancel()
        await asyncio.gather(movement, return_exceptions=True)
        await hass.async_block_till_done()
    assert not observations
    assert not mock_bleak_client.write_gatt_char.called
    assert c._cleanup is None
    await hass.config_entries.async_unload(e.entry_id)


@pytest.mark.parametrize("branch", app.TRANSPORTS)
async def test_public_caller_cancel_after_gatt_settles_and_releases_twice(
    hass, mock_coordinator_connected, mock_bleak_client, enable_custom_integrations, branch
):
    mock_bleak_client.services = gatt(branch)
    e = entry(hass, branch)
    assert await hass.config_entries.async_setup(e.entry_id)
    await hass.async_block_till_done()
    co = hass.data[const.DOMAIN][e.entry_id]
    started, finish, settled = asyncio.Event(), asyncio.Event(), asyncio.Event()

    async def record(char, frame, **kwargs):
        if bytes(frame) == app.encode(branch, "headUp"):
            started.set()
            await finish.wait()
            settled.set()
        else:
            assert settled.is_set()

    mock_bleak_client.write_gatt_char.side_effect = record
    with virtual_clock():
        movement = asyncio.create_task(
            co.async_execute_controller_command(
                lambda controller: controller.hold_control("head_up", 1000)
            )
        )
        await started.wait()
        movement.cancel()
        await asyncio.sleep(0)
        assert not movement.done()
        assert writes(mock_bleak_client) == [app.encode(branch, "headUp")]
        finish.set()
        await asyncio.gather(movement, return_exceptions=True)
        assert writes(mock_bleak_client) == [
            app.encode(branch, "headUp"),
            *[app.encode(branch, "stop")] * 2,
        ]
        mock_bleak_client.write_gatt_char.reset_mock()
        await co.async_stop_command()
        assert writes(mock_bleak_client) == [app.encode(branch, "stop")] * 2
    await hass.config_entries.async_unload(e.entry_id)
