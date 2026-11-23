"""PR1028 R1/R2: alarm reconnect admission and shared diagnostic notifications."""

import asyncio
import json
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest
from homeassistant.exceptions import ServiceValidationError

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.beds.ore_ultramatic import state_keys as state
from custom_components.adjustable_bed.beds.ore_ultramatic.controller import OreUltramaticController
from custom_components.adjustable_bed.ble_diagnostics import (
    BLEDiagnosticRunner,
    CharacteristicInfo,
    ServiceInfo,
)
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.profiles import ore_ultramatic as app
from custom_components.adjustable_bed.services import async_register_services
from tests.hold_lease_wire import virtual_clock
from tests.test_ore_comfort_bed import _written
from tests.test_ore_ultramatic import target as target


@pytest.mark.parametrize("cached,live,restored", [
    ("P1", "P1", False), ("P2", "P2", False),
    ("P1", "P1", True), ("P2", "P2", True),
    ("P1", "P2", True), ("P2", "P1", True),
])
async def test_registered_alarm_after_idle_or_saved_route_restore(
    hass, target, mock_establish_connection, cached, live, restored,
):
    coordinator, client = await target(cached)
    await coordinator.async_disconnect(reason="idle")
    active = AdjustableBedCoordinator(hass, coordinator.entry) if restored else coordinator
    active._max_retries = 1
    await active.async_prime_offline_controller()
    assert active.controller is None
    assert active.capability_controller.capability_snapshot() == {"ultramatic_route": cached}
    client.services[0].uuid = app.SELECTOR if live == "P1" else "other"

    async def reconnect(*args, **kwargs):
        client.is_connected = True
        return client

    mock_establish_connection.reset_mock()
    mock_establish_connection.side_effect = reconnect
    client.write_gatt_char.reset_mock()
    await async_register_services(hass)
    now = datetime(2026, 11, 17, 7, 6, 5)
    try:
        with patch("custom_components.adjustable_bed.services._resolve_sided_targets", return_value=([(active, "both")], [])), patch("custom_components.adjustable_bed.beds.ore_ultramatic.controller.dt_util.now", return_value=now), virtual_clock():
            await hass.services.async_call(const.DOMAIN, "set_alarm", {
                "device_id": "bed", "enabled": True, "time": "07:30:00",
                # Massage is offered on both routes, so a changed live route still accepts it.
                "weekdays": ["monday"], "wake_action": "massage",
            }, blocking=True)
        assert mock_establish_connection.await_count == 1
        assert active.controller.capability_snapshot() == {"ultramatic_route": live}
        assert _written(client) == (
            ["ebfe160506071e0702821111ff24", "e2fe1605060702f5"]
            if live == "P1" else
            ["e780017e0a11070605ec", "ed8003071e82090000000000000000df", "e28003009a"]
        )
    finally:
        if restored:
            await active.async_shutdown()


async def test_unknown_cached_route_rejects_all_targets_before_reconnect_or_writes(
    hass, target, mock_establish_connection,
):
    first, first_client = await target("P1", address="AA:BB:CC:DD:15:86")
    invalid, invalid_client = await target("P2", address="AA:BB:CC:DD:15:87")
    await first.async_disconnect(reason="idle")
    await invalid.async_disconnect(reason="idle")
    # An unknown cached capability must never be treated as the default route.
    invalid._offline_controller = OreUltramaticController(invalid)
    assert invalid.capability_controller.capability_snapshot() is None
    mock_establish_connection.reset_mock()
    first_client.write_gatt_char.reset_mock()
    invalid_client.write_gatt_char.reset_mock()
    await async_register_services(hass)
    with (
        patch(
            "custom_components.adjustable_bed.services._resolve_sided_targets",
            return_value=([(first, "both"), (invalid, "both")], []),
        ),
        virtual_clock(),
        pytest.raises(ServiceValidationError, match="discover its bed route"),
    ):
        await hass.services.async_call(const.DOMAIN, "set_alarm", {
            "device_id": ["first", "invalid"], "enabled": True, "time": "07:30:00",
            "wake_action": "massage",
        }, blocking=True)
    mock_establish_connection.assert_not_awaited()
    assert not first_client.write_gatt_char.called
    assert not invalid_client.write_gatt_char.called


@pytest.mark.parametrize("route", ("P1", "P2"))
async def test_shared_diagnostics_captures_raw_frames_and_preserves_required_channel(
    hass, target, route,
):
    coordinator, client = await target(route)
    controller = coordinator.controller
    callback = client.start_notify.await_args.args[1]
    link = controller._link
    runner = BLEDiagnosticRunner(hass, coordinator.address, capture_duration=0, coordinator=coordinator)
    runner._client = client
    runner._using_coordinator_connection = True
    info = CharacteristicInfo(link.notify.uuid, link.notify.handle, ["notify"])
    services = [ServiceInfo(client.services[0].uuid, characteristics=[info])]
    await runner._subscribe_to_notifications(services)
    assert info.notify_subscription["method"] == "shared_connection"
    assert info.notify_subscription["attempted"] is False
    assert client.start_notify.await_count == 1

    seed = bytes.fromhex("0000000000000005000000000000f300")
    ignored = bytes(9)
    frozen = json.loads(
        (Path(__file__).parent / "fixtures/ore_ultramatic/vectors.json").read_text()
    )
    fragment = bytes.fromhex(frozen[87]["inputs"]["fragments"][0])
    tail = bytes(3)
    assert len(fragment) == 20
    frames = (seed, ignored, fragment, tail)
    for frame in frames:
        callback(link.notify, bytearray(frame))
    await asyncio.gather(*tuple(runner._background_tasks))
    assert [n.data_hex for n in runner._notifications] == [frame.hex() for frame in frames]
    assert {n.characteristic for n in runner._notifications} == {link.notify.uuid}
    assert coordinator.controller_state[state.TIMER] == 2
    assert coordinator.controller_state[state.INTENSITY] == 2

    # Capture cleanup removes only its callback, retaining ordinary bed reports.
    await runner._unsubscribe_from_notifications(services)
    client.stop_notify.assert_not_awaited()
    callback(link.notify, bytearray(seed))
    assert coordinator.controller_state[state.TIMER] == 3
    assert len(runner._notifications) == len(frames)
    await runner._subscribe_to_notifications(services)
    assert client.start_notify.await_count == 1

    client.is_connected = False
    callback(link.notify, bytearray(tail))
    assert len(runner._background_tasks) == 0
    assert coordinator.controller_state[state.TIMER] == 3
    client.is_connected = True
    controller.on_disconnect()
    callback(link.notify, bytearray(seed))
    assert len(runner._background_tasks) == 0
    assert len(runner._notifications) == len(frames)
    assert coordinator.controller_state[state.TIMER] is None
    await runner._unsubscribe_from_notifications(services)


@pytest.mark.parametrize("cached,live,wake", [("P1", "P2", "memory_1"), ("P2", "P1", "tv")])
async def test_changed_live_route_rejects_every_target_before_any_alarm_write(
    hass, target, mock_establish_connection, cached, live, wake,
):
    steady, steady_client = await target(cached, address="AA:BB:CC:DD:15:88")
    changed, client = await target(cached, address="AA:BB:CC:DD:15:89")
    await changed.async_disconnect(reason="idle")
    await changed.async_prime_offline_controller()
    client.services[0].uuid = app.SELECTOR if live == "P1" else "other"

    async def reconnect(*args, **kwargs):
        client.is_connected = True
        return client

    mock_establish_connection.side_effect = reconnect
    steady_client.write_gatt_char.reset_mock()
    client.write_gatt_char.reset_mock()
    await async_register_services(hass)
    with (
        patch(
            "custom_components.adjustable_bed.services._resolve_sided_targets",
            return_value=([(steady, "both"), (changed, "both")], []),
        ),
        virtual_clock(),
        pytest.raises(ServiceValidationError),
    ):
        await hass.services.async_call(const.DOMAIN, "set_alarm", {
            "device_id": ["steady", "changed"], "enabled": True, "time": "07:30:00",
            "wake_action": wake,
        }, blocking=True)
    # The first bed's route accepts the wake action, but nothing is written to it.
    assert not steady_client.write_gatt_char.called
    assert changed.controller.capability_snapshot() == {"ultramatic_route": live}
