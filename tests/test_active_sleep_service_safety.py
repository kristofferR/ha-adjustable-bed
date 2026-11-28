"""Native services preserve STOP cleanup, combination locks and reconnect admission."""

import asyncio
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed import const, services
from custom_components.adjustable_bed.beds.active_sleep.controller import ActiveSleepController
from custom_components.adjustable_bed.codec import active_sleep as codec
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.errors import BedCommandTimedOutError, BedNotConnectedError
from custom_components.adjustable_bed.execution import HOLD_CEILING_MS
from custom_components.adjustable_bed.paired_coordinator import PairedBedCoordinator
from custom_components.adjustable_bed.runtime_data import entry_runtime
from scripts.wire_snapshot import FakeServices
from tests.test_active_sleep import Bed


async def test_paired_hold_recovers_after_preempting_query(hass):
    async def receiver(suffix):
        bed = Bed()
        entry = MockConfigEntry(domain=const.DOMAIN, data={
            CONF_ADDRESS: f"AA:BB:CC:DD:15:{suffix}", CONF_NAME: "Active Sleep",
            const.CONF_BED_TYPE: "active_sleep", "active_sleep_auth_id": "0123456789ABCDEF",
            const.CONF_CONNECTION_MODE: const.CONNECTION_MODE_IDLE,
        })
        entry.add_to_hass(hass)
        coordinator = AdjustableBedCoordinator(hass, entry)
        bed.coordinator = coordinator
        coordinator._client = bed.client
        coordinator._link_ready = True

        async def install():
            bed.controller = ActiveSleepController(coordinator, "0123456789ABCDEF")
            bed.controller.profile = replace(bed.controller.profile,
                interval_ms=0, manual_delay_ms=0, preset_delay_ms=0,
                response_timeout_ms=15, query_timeout_s=0.05)
            coordinator._controller = bed.controller
            await bed.controller.async_on_connect(SimpleNamespace(
                async_start_notify=bed.controller.start_notify,
                persist_capability_snapshot=MagicMock()))

        async def disconnect(**_kwargs):
            bed.controller.on_disconnect()
            await install()
            return True

        await install()
        coordinator.async_ensure_connected = AsyncMock(return_value=True)
        coordinator.async_disconnect = AsyncMock(side_effect=disconnect)
        coordinator._start_background_position_read = MagicMock()
        bed.writes.clear()
        return coordinator, bed

    left, bed = await receiver("96")
    right, other = await receiver("97")
    entry = MockConfigEntry(domain=const.DOMAIN, data={const.CONF_PAIR_ID: "active-sleep-pair"})
    pair = PairedBedCoordinator(hass, entry, {const.SIDE_LEFT: left, const.SIDE_RIGHT: right},
        connection_mode=const.PAIR_CONNECTION_MODE_CONCURRENT)
    query_written = asyncio.Event()
    left_motion = asyncio.Event()
    right_motion = asyncio.Event()
    bed.drop = 0xB2
    original_write = bed.write

    async def write(char, raw, **kwargs):
        await original_write(char, raw, **kwargs)
        if raw[0] == 0xB2:
            query_written.set()
        elif raw == codec.arrow(2):
            left_motion.set()

    async def right_write(char, raw, **kwargs):
        await other.write(char, raw, **kwargs)
        if raw == codec.arrow(2):
            right_motion.set()

    bed.client.write_gatt_char.side_effect = write
    other.client.write_gatt_char.side_effect = right_write
    query = asyncio.create_task(left.async_execute_controller_query(
        lambda current: current.read_positions(), skip_disconnect=True, preemptible=True))
    try:
        await query_written.wait()
        bed.drop = None
        original_controller = left.controller
        hold = asyncio.create_task(
            services._hold_targets([(pair, const.SIDE_BOTH)], "head_up", HOLD_CEILING_MS)
        )
        try:
            await asyncio.wait_for(asyncio.gather(left_motion.wait(), right_motion.wait()), 5)
        finally:
            hold.cancel()
            with pytest.raises(asyncio.CancelledError):
                await hold
        assert left.controller is not original_controller
        left.async_disconnect.assert_awaited_once_with(reason="protocol_error")
        assert any(raw[0] == 0xB4 and raw[2] == 2 for raw in bed.writes)
        assert any(raw[0] == 0xB4 and raw[2] == 2 for raw in other.writes)
        assert [raw for raw in bed.writes if raw[0] == 0xB4][-1] == codec.arrow(0)
        assert [raw for raw in other.writes if raw[0] == 0xB4][-1] == codec.arrow(0)
    finally:
        query.cancel()
        await asyncio.gather(query, return_exceptions=True)
        for child in (left, right):
            await child.command_scheduler.async_shutdown()
            child._cancel_disconnect_timer()
        for unsubscribe in pair._child_unsubs:
            unsubscribe()


@pytest.mark.parametrize(
    "case",
    [
        "ambiguous_write", "combination_lock", "disconnected_position",
        "preempted_query", "failed_recovery", "unrelated_motor_lock",
    ],
)
async def test_native_route(
    case,
    hass,
    mock_coordinator_connected,
    mock_bleak_client,
    mock_async_ble_device_from_address,
    enable_custom_integrations,
):
    simulator = Bed()
    if case == "combination_lock":
        simulator.position = replace(simulator.position, locks=8)
    elif case == "unrelated_motor_lock":
        simulator.position = replace(simulator.position, locks=4)
    mock_bleak_client.services = FakeServices(
        {
            "services": {codec.SERVICE_UUID: [codec.CHAR_UUID]},
            "properties": {codec.CHAR_UUID: ["write", "notify"]},
        }
    )
    simulator.char = mock_bleak_client.services.get_characteristic(codec.CHAR_UUID)
    mock_bleak_client.start_notify.side_effect = simulator.subscribe
    mock_bleak_client.write_gatt_char.side_effect = simulator.write
    address = "AA:BB:CC:DD:15:96"
    entry = MockConfigEntry(
        domain=const.DOMAIN,
        title="Active Sleep",
        unique_id=address,
        data={
            CONF_ADDRESS: address,
            CONF_NAME: "Active Sleep",
            const.CONF_BED_TYPE: "active_sleep",
            const.CONF_DISABLE_ANGLE_SENSING: False,
            "active_sleep_auth_id": "0123456789ABCDEF",
            const.CONF_CONNECTION_MODE: const.CONNECTION_MODE_IDLE,
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    coordinator = entry_runtime(hass, entry.entry_id)
    device = dr.async_get(hass).async_get_device_by_identifier(
        (const.DOMAIN, address), entry.entry_id
    )
    assert device is not None
    simulator.writes.clear()
    try:
        if case == "ambiguous_write":
            original = simulator.write

            async def fail(char, raw, **kwargs):
                if raw == codec.arrow(2):
                    simulator.writes.append(raw)
                    raise TimeoutError("synthetic backend failure after delivery")
                await original(char, raw, **kwargs)

            mock_bleak_client.write_gatt_char.side_effect = fail
            with pytest.raises(BedCommandTimedOutError):
                await hass.services.async_call(
                    const.DOMAIN,
                    "hold_control",
                    {"device_id": [device.id], "control": "head_up", "duration": 0.1},
                    blocking=True,
                )
            assert codec.arrow(2) in simulator.writes
            assert simulator.writes[-1] == codec.arrow(0)
        elif case == "combination_lock":
            with pytest.raises(ServiceValidationError, match="locked"):
                await hass.services.async_call(
                    const.DOMAIN,
                    "hold_control",
                    {"device_id": [device.id], "control": "combination_up", "duration": 0.1},
                    blocking=True,
                )
            assert not any(raw[0] == 0xB4 for raw in simulator.writes)
        elif case in {"preempted_query", "failed_recovery"}:
            coordinator._cancel_diagnostic_polling()
            old_controller = coordinator.controller
            query_written = asyncio.Event()
            simulator.drop = 0xB2

            async def query_write(char, raw, **kwargs):
                await simulator.write(char, raw, **kwargs)
                if raw[0] == 0xB2:
                    query_written.set()

            mock_bleak_client.write_gatt_char.side_effect = query_write
            query = asyncio.create_task(
                coordinator.async_execute_controller_query(
                    lambda current: current.read_positions(),
                    cancel_running=False,
                    skip_disconnect=True,
                    preemptible=True,
                )
            )
            await query_written.wait()
            simulator.drop = None
            original_disconnect = mock_bleak_client.disconnect.side_effect
            if case == "failed_recovery":
                mock_bleak_client.disconnect.side_effect = None
                mock_bleak_client.disconnect.return_value = None
                with pytest.raises(BedNotConnectedError):
                    await hass.services.async_call(
                        const.DOMAIN,
                        "hold_control",
                        {"device_id": [device.id], "control": "head_up", "duration": 0.1},
                        blocking=True,
                    )
                assert not any(raw[0] == 0xB4 for raw in simulator.writes)
                mock_bleak_client.disconnect.side_effect = original_disconnect
            await hass.services.async_call(
                const.DOMAIN,
                "hold_control",
                {"device_id": [device.id], "control": "head_up", "duration": 0.1},
                blocking=True,
            )
            await asyncio.gather(query, return_exceptions=True)
            assert coordinator.controller is not old_controller
            assert coordinator.controller._authenticated
            assert not coordinator.controller._poisoned
            mock_bleak_client.disconnect.assert_awaited()
            assert codec.arrow(2) in simulator.writes
            assert [raw for raw in simulator.writes if raw[0] == 0xB4][-1] == codec.arrow(0)
        elif case == "unrelated_motor_lock":
            with patch.object(
                ActiveSleepController, "_hold_movement", new_callable=AsyncMock
            ) as move:
                await hass.services.async_call(
                    const.DOMAIN,
                    "set_position",
                    {"device_id": [device.id], "motor": "head", "position": 20},
                    blocking=True,
                )
                move.assert_awaited_once_with("target", 30000, (20, 255, 255, 255))
        else:
            await coordinator.async_disconnect(reason="intentional")
            assert coordinator.controller is None
            assert coordinator.capability_controller is not None
            coordinator.async_ensure_connected = AsyncMock(wraps=coordinator.async_ensure_connected)
            with patch.object(
                ActiveSleepController, "_hold_movement", new_callable=AsyncMock
            ) as move:
                await hass.services.async_call(
                    const.DOMAIN,
                    "set_position",
                    {"device_id": [device.id], "motor": "head", "position": 20},
                    blocking=True,
                )
                move.assert_awaited_once()
            coordinator.async_ensure_connected.assert_awaited()
            assert coordinator.controller is not None
            assert coordinator.controller._authenticated
    finally:
        mock_bleak_client.start_notify.side_effect = None
        mock_bleak_client.write_gatt_char.side_effect = None
        assert await hass.config_entries.async_unload(entry.entry_id)
