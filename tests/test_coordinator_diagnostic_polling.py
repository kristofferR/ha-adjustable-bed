"""Default-disabled live diagnostic queries preserve command and idle ownership."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.beds.base import BedController
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from tests.test_vmatbasic import make_controller


@pytest.fixture
def coordinator(hass):
    entry = MockConfigEntry(
        domain=const.DOMAIN,
        data={
            CONF_ADDRESS: "AA:BB:CC:DD:EE:FF",
            CONF_NAME: "App",
            const.CONF_BED_TYPE: const.BED_TYPE_VMATBASIC,
            const.CONF_VMATBASIC_PROFILE: "basic",
            const.CONF_DISCONNECT_AFTER_COMMAND: False,
        },
    )
    entry.add_to_hass(hass)
    coordinator = AdjustableBedCoordinator(hass, entry)
    controller = make_controller()
    coordinator._client = controller.client
    controller._coordinator = coordinator
    coordinator._controller = controller
    return coordinator


def test_base_diagnostics_disabled_without_controller_evidence():
    poll = BedController.diagnostic_poll_interval.fget
    sample = BedController.diagnostic_advertisement_interval.fget
    assert poll is not None and sample is not None
    assert poll(object()) is None
    assert sample(object()) is None


async def test_actual_query_keeps_identical_idle_timer_and_never_connects(coordinator):
    coordinator._reset_disconnect_timer()
    timer = coordinator._disconnect_timer
    when = timer.when()
    with patch.object(coordinator, "_async_connect_locked", new=AsyncMock()) as connect:
        await coordinator.async_execute_controller_query(
            lambda ctrl: ctrl.async_refresh_diagnostics(),
            preserve_idle_deadline=True,
            run_if=lambda: coordinator.is_connected,
        )
    assert coordinator._disconnect_timer is timer
    assert not timer.cancelled()
    assert timer.when() == when
    assert connect.await_count == 0
    coordinator._cancel_disconnect_timer()


async def test_initial_live_refresh_and_disconnect_invalidation(coordinator):
    coordinator._refresh_diagnostic_polling_schedule()
    for _ in range(50):
        if coordinator._controller_state.get("vmatbasic_ed") is True:
            break
        await asyncio.sleep(0.001)
    assert coordinator._controller_state["vmatbasic_model"] == " model \0"
    assert coordinator._controller_state["vmatbasic_ed"] is True
    assert coordinator._diagnostic_poll_task is not None
    task = coordinator._diagnostic_poll_task
    advertisement_task = coordinator._diagnostic_advertisement_task
    coordinator._cancel_diagnostic_polling()
    await asyncio.gather(task, advertisement_task, return_exceptions=True)
    assert coordinator._diagnostic_poll_task is None
    assert all(value is None for value in coordinator._controller_state.values())


async def test_poll_is_preempted_by_stop_without_later_reads(coordinator):
    entered = asyncio.Event()

    async def read(characteristic):
        entered.set()
        await asyncio.sleep(30)
        return b"late"

    coordinator._client.read_gatt_char.side_effect = read
    task = asyncio.create_task(
        coordinator.async_execute_controller_query(
            lambda ctrl: ctrl.async_refresh_diagnostics(), preserve_idle_deadline=True
        )
    )
    await entered.wait()
    coordinator._cancel_counter += 1
    coordinator._cancel_command.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert coordinator._client.read_gatt_char.await_count == 1
    assert not coordinator._command_lock.locked()
    assert not coordinator._controller.ble_lock.locked()


async def test_live_guard_disconnected_skips_without_reconnect(coordinator):
    coordinator._client.is_connected = False
    with patch.object(coordinator, "_async_connect_locked", new=AsyncMock()) as connect:
        await coordinator.async_execute_controller_query(
            lambda ctrl: ctrl.async_refresh_diagnostics(),
            preserve_idle_deadline=True,
            run_if=lambda: coordinator.is_connected,
        )
    assert connect.await_count == 0
    assert coordinator._client.read_gatt_char.await_count == 0


async def test_advertisement_sampling_has_exact_provenance_without_io_or_idle_renewal(coordinator):
    coordinator._reset_disconnect_timer()
    timer = coordinator._disconnect_timer
    info = SimpleNamespace(rssi=-65, source="proxy-left", time=123.5)
    with patch(
        "custom_components.adjustable_bed.coordinator.bluetooth.async_last_service_info",
        return_value=info,
    ):
        task = asyncio.create_task(
            coordinator._async_diagnostic_advertisement_loop(coordinator.controller, 0.01)
        )
        await asyncio.sleep(0.025)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
    state = coordinator.controller_state
    assert state["vmatbasic_rssi"] == -65
    assert state["vmatbasic_rssi_source"] == "proxy-left"
    assert state["vmatbasic_rssi_seen_at"] == 123.5
    assert "remote RSSI read unavailable" in state["vmatbasic_rssi_representation"]
    assert coordinator._disconnect_timer is timer and not timer.cancelled()
    assert coordinator.client.read_gatt_char.await_count == 0
    assert coordinator.client.write_gatt_char.await_count == 0
    coordinator._cancel_disconnect_timer()


@pytest.mark.parametrize("rssi", [-127, -128])
async def test_unavailable_advertisement_signal_never_publishes_a_valid_remote_read(
    coordinator, rssi
):
    info = SimpleNamespace(rssi=rssi, source="hci0", time=5.0)
    with patch(
        "custom_components.adjustable_bed.coordinator.bluetooth.async_last_service_info",
        return_value=info,
    ):
        task = asyncio.create_task(
            coordinator._async_diagnostic_advertisement_loop(coordinator.controller, 1)
        )
        await asyncio.sleep(0)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
    assert coordinator.controller_state["vmatbasic_rssi"] is None


async def test_three_second_attempt_cadence_does_not_add_read_latency(coordinator):
    original_sleep = asyncio.sleep

    async def refresh():
        await original_sleep(0.03)

    delays = []

    async def sleep(delay):
        delays.append(delay)
        coordinator._client.is_connected = False

    coordinator.controller.async_refresh_diagnostics = refresh
    with patch("custom_components.adjustable_bed.coordinator.asyncio.sleep", side_effect=sleep):
        await coordinator._async_diagnostic_poll_loop(coordinator.controller, 3)
    assert len(delays) == 1
    assert 2.9 < delays[0] < 2.99


@pytest.mark.parametrize("interval", [0, -1, float("nan"), float("inf")])
async def test_invalid_optional_polling_interval_leaves_live_connection_usable(
    coordinator, interval
):
    with patch.object(
        type(coordinator.controller),
        "diagnostic_poll_interval",
        new=property(lambda self: interval),
    ):
        coordinator._refresh_diagnostic_polling_schedule()
    assert coordinator.is_connected
    assert coordinator._diagnostic_poll_task is None
    assert coordinator._diagnostic_advertisement_task is None


async def test_live_only_query_never_enters_reconnect_or_auth_preparation(coordinator):
    coordinator._reset_disconnect_timer()
    timer = coordinator._disconnect_timer
    try:
        with (
            patch.object(
                coordinator,
                "async_ensure_connected",
                new=AsyncMock(side_effect=AssertionError("must not enter connect lock")),
            ) as connect,
            patch.object(
                coordinator,
                "_async_refresh_controller_auth",
                new=AsyncMock(side_effect=AssertionError("must not perform auth")),
            ) as auth,
        ):
            await coordinator.async_execute_controller_query(
                lambda ctrl: ctrl.async_refresh_diagnostics(), preserve_idle_deadline=True
            )
        assert connect.await_count == auth.await_count == 0
        assert coordinator._disconnect_timer is timer
        assert coordinator._controller_state["vmatbasic_ed"] is True
    finally:
        coordinator._cancel_disconnect_timer()
