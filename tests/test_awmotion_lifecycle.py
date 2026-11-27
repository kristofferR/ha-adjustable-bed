"""Native idle ingress and owned notification cleanup for AW MOTION."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from custom_components.adjustable_bed import const, services
from custom_components.adjustable_bed.beds.dreamsense.awmotion import STATUS
from custom_components.adjustable_bed.ble_diagnostics import BLEDiagnosticRunner
from custom_components.adjustable_bed.button import ControllerActionButton
from custom_components.adjustable_bed.controller_factory import create_controller
from tests.error_helpers import raises_key
from tests.test_awmotion import runtime
from tests.test_dreamsense import make_client, written


async def test_shared_diagnostics_never_stop_the_required_channel(hass):
    c, ctrl = await runtime(hass)
    c._link_ready = True
    session = ctrl._ready
    runner = BLEDiagnosticRunner(hass, c.address, capture_duration=0, coordinator=c)
    runner._client = c.client
    runner._using_coordinator_connection = True
    assert ctrl.requires_notification_channel
    await runner._subscribe_to_notifications([])
    assert not runner._diagnostic_notifications_started
    await runner._unsubscribe_from_notifications([])
    assert ctrl._ready is session and c._link_ready
    c.client.stop_notify.assert_not_awaited()
    c.client.write_gatt_char.reset_mock()
    await c.async_execute_controller_command(lambda live: live.press("MotorReset"))
    assert written(c) == ["6e010031a0", "6e01006edd"]


@pytest.mark.parametrize("cancel_disconnect", [False, True])
async def test_retained_physical_link_restores_after_notification_cleanup(hass, cancel_disconnect):
    c, ctrl = await runtime(hass)
    c._link_ready = True
    client, previous = c.client, ctrl._ready
    previous_callback = client.start_notify.call_args.args[1]
    entered = asyncio.Event()

    async def disconnect():
        entered.set()
        if cancel_disconnect:
            await asyncio.Event().wait()

    client.disconnect = AsyncMock(side_effect=disconnect)
    with patch.object(c, "_reset_disconnect_timer"):
        release = asyncio.create_task(c._async_disconnect_locked("idle_timeout"))
        await entered.wait()
        assert ctrl._session is previous and ctrl._ready is None
        if cancel_disconnect:
            release.cancel()
            with pytest.raises(asyncio.CancelledError):
                await release
        else:
            assert await release is False
    assert c.client is client and c._controller is ctrl and c._link_ready
    assert ctrl._ready is not None and ctrl._ready is not previous
    client.stop_notify.assert_awaited_once_with(previous.notify)
    assert client.start_notify.await_count == 2
    previous_callback(None, bytearray.fromhex("6e0e00037f"))
    assert "light" not in ctrl._receive.capabilities
    client.write_gatt_char.reset_mock()
    await c.async_execute_controller_command(lambda live: live.press("MotorReset"))
    assert written(c) == ["6e010031a0", "6e01006edd"]


async def test_task_cancellation_during_subscription_drains_exact_owned_cleanup(hass):
    c, ctrl = await runtime(hass)
    ctrl.on_disconnect()
    client = c.client
    client.write_gatt_char.reset_mock()
    client.stop_notify.reset_mock()
    entered, finish = asyncio.Event(), asyncio.Event()

    async def subscribe(_char, _callback):
        entered.set()
        await finish.wait()

    client.start_notify.side_effect = subscribe
    startup = asyncio.create_task(c.async_start_notify())
    await entered.wait()
    session = ctrl._session
    startup.cancel()
    await asyncio.sleep(0)
    assert not startup.done()  # The actual OS subscription must finish first.
    finish.set()
    with pytest.raises(asyncio.CancelledError):
        await startup
    client.stop_notify.assert_awaited_once_with(session.notify)
    assert ctrl._ready is None and ctrl._session is None and not written(c)
    with raises_key("dreamsense_session"):
        await ctrl.press("MotorReset")
    client.start_notify.side_effect = None
    await c.async_start_notify()
    await c.async_execute_controller_command(lambda live: live.press("MotorReset"))
    assert written(c)[-2:] == ["6e010031a0", "6e01006edd"]


@pytest.mark.parametrize("successor", ["generation", "controller", "client"])
async def test_obsolete_cancelled_startup_cannot_unsubscribe_or_clear_successor(hass, successor):
    c, ctrl = await runtime(hass)
    ctrl.on_disconnect()
    client = c.client
    client.stop_notify.reset_mock()
    entered, finish = asyncio.Event(), asyncio.Event()

    async def subscribe(_char, _callback):
        entered.set()
        await finish.wait()

    client.start_notify.side_effect = subscribe
    startup = asyncio.create_task(ctrl.start_notify())
    await entered.wait()
    obsolete = ctrl._session
    if successor == "generation":
        c._position_connection_generation += 1
    elif successor == "client":
        c._client = make_client(1)
    else:
        c._controller = await create_controller(c, "awmotion", "SN300", client)
    current = c._controller
    c.handle_controller_state_update(STATUS, "successor")
    startup.cancel()
    finish.set()
    with pytest.raises(asyncio.CancelledError):
        await startup
    client.stop_notify.assert_not_awaited()
    assert c._controller is current and c.controller_state[STATUS] == "successor"
    assert ctrl._ready is None
    with raises_key("dreamsense_session"):
        await ctrl.press("MotorReset")
    assert obsolete.generation <= c.connection_generation


async def idle_with_snapshot(hass, *, known=True):
    c, ctrl = await runtime(hass)
    if known:
        ctrl._notification(ctrl._session, None, bytearray.fromhex("6e0e00037f"))
    snapshot = ctrl.capability_snapshot()
    hass.config_entries.async_update_entry(
        c.entry, data={**c.entry.data, "capabilities": {"awmotion": snapshot}}
    )
    client = c.client
    client.disconnect = AsyncMock(side_effect=lambda: setattr(client, "is_connected", False))
    with patch.object(c, "_reset_disconnect_timer"):
        assert await c._async_disconnect_locked("idle_timeout")
    await c.async_prime_offline_controller()
    return c


def reconnect(c, *, capable=True):
    async def ensure(**_kwargs):
        # Only the BLE establishment is replaced. Ingress, profile factory,
        # subscription and controller command scheduler remain real.
        c._client = make_client(1)
        c._position_connection_generation += 1
        ctrl = await create_controller(c, "awmotion", "SN300", c.client)
        c._controller = ctrl
        ctrl._wait = AsyncMock()
        if capable:

            async def subscribe(_char, callback):
                callback(None, bytearray.fromhex("6e0e00037f"))

            c.client.start_notify.side_effect = subscribe
        await c.async_start_notify()
        c._link_ready = True
        return True

    return AsyncMock(side_effect=ensure)


@pytest.mark.parametrize("known", [False, True])
async def test_registered_light_action_idle_snapshot_admission_then_live_execution(hass, known):
    c = await idle_with_snapshot(hass, known=known)
    await services.async_register_services(hass)
    ensure = reconnect(c)
    with (
        patch.object(c, "async_ensure_connected", ensure),
        patch.object(services, "_resolve_sided_targets", return_value=([(c, const.SIDE_BOTH)], [])),
    ):
        call = hass.services.async_call(
            const.DOMAIN,
            "dreamsense_light",
            {
                "device_id": "bed",
                "rgb_color": [18, 52, 86],
                "seconds": 60,
            },
            blocking=True,
        )
        if known:
            await call
            ensure.assert_awaited_once()
            assert written(c) == [
                "6e02010071",
                "6e08010178",
                "6e0a000179",
                "6e0b003cb5",
                "6e0cff128b6e0d345605",
            ]
        else:
            with raises_key("dreamsense_capability"):
                await call
            ensure.assert_not_awaited()
            assert c.client is None


@pytest.mark.parametrize("ingress", ["service", "button"])
async def test_idle_light_paths_recheck_new_live_capability(hass, ingress):
    c = await idle_with_snapshot(hass)
    offline = c.capability_controller
    spec = next(s for s in offline.controller_button_specs if s.key == "dreamsense_light_close")
    button = ControllerActionButton(c, spec)
    assert button.available
    ensure = reconnect(c, capable=False)
    await services.async_register_services(hass)
    with (
        patch.object(c, "async_ensure_connected", ensure),
        patch.object(services, "_resolve_sided_targets", return_value=([(c, const.SIDE_BOTH)], [])),
        raises_key("dreamsense_capability"),
    ):
        if ingress == "button":
            await button.async_press()
        else:
            await hass.services.async_call(
                const.DOMAIN,
                "dreamsense_light",
                {
                    "device_id": "bed",
                    "rgb_color": [18, 52, 86],
                },
                blocking=True,
            )
    ensure.assert_awaited_once()
    assert written(c) == ["6e02010071", "6e08010178", "6e0a000179"]
    assert not button.available


async def test_known_idle_native_off_button_reconnects_and_sends_only_direct_close(hass):
    c = await idle_with_snapshot(hass)
    spec = next(
        s
        for s in c.capability_controller.controller_button_specs
        if s.key == "dreamsense_light_close"
    )
    button = ControllerActionButton(c, spec)
    assert button.available
    with patch.object(c, "async_ensure_connected", reconnect(c)) as ensure:
        await button.async_press()
    ensure.assert_awaited_once()
    assert written(c) == ["6e02010071", "6e08010178", "6e0a000179", "6e010075e4"]
    with c.controller.side_scope(const.SIDE_RIGHT):
        assert not c.controller.controller_button_available(spec.key)


async def test_sequential_pair_rejects_unknown_snapshot_before_connecting_either_side(hass):
    from pytest_homeassistant.common import MockConfigEntry

    from custom_components.adjustable_bed.paired_coordinator import PairedBedCoordinator

    left = await idle_with_snapshot(hass)
    right = await idle_with_snapshot(hass, known=False)
    right._address = "11:22:33:44:55:80"
    entry = MockConfigEntry(domain=const.DOMAIN, data={const.CONF_PAIR_ID: "awmotion-pair"})
    entry.add_to_hass(hass)
    pair = PairedBedCoordinator(
        hass, entry, {const.SIDE_LEFT: left, const.SIDE_RIGHT: right}, connection_mode="sequential"
    )
    await services.async_register_services(hass)
    with (
        patch.object(left, "async_ensure_connected", AsyncMock()) as connect_left,
        patch.object(right, "async_ensure_connected", AsyncMock()) as connect_right,
        patch.object(
            services, "_resolve_sided_targets", return_value=([(pair, const.SIDE_BOTH)], [])
        ),
        raises_key("dreamsense_capability"),
    ):
        await hass.services.async_call(
            const.DOMAIN,
            "dreamsense_light",
            {
                "device_id": "pair",
                "rgb_color": [18, 52, 86],
            },
            blocking=True,
        )
    connect_left.assert_not_awaited()
    connect_right.assert_not_awaited()
    assert left.client is None and right.client is None
