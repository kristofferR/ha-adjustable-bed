"""Tests for the coordinator's motor position state, callbacks and seeks."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest
from bleak.exc import BleakError
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed.command_scheduler import (
    CommandKind,
    CommandOutcome,
)
from custom_components.adjustable_bed.const import (
    BED_TYPE_OKIMAT,
    BED_TYPE_RICHMAT,
    CONF_BED_TYPE,
    CONF_BLE_BOND_ESTABLISHED,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_HAS_MASSAGE,
    CONF_MOTOR_COUNT,
    CONF_PREFERRED_ADAPTER,
    CONF_RICHMAT_REMOTE,
    DOMAIN,
    RICHMAT_REMOTE_AUTO,
)
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.position_seek import PositionFeedbackError, PositionSeekPolicy
from tests.coordinator_patches import patch_coordinator_global

from .conftest import TEST_ADDRESS, TEST_NAME, make_controller_mock


class _PulseStepPolicy(PositionSeekPolicy):
    """Pulse-driven policy that records its custom seek steps."""

    reverses_on_overshoot = False

    def __init__(self, controller: MagicMock, **tuning: float | bool) -> None:
        super().__init__(controller)
        for name, value in tuning.items():
            assert name in vars(PositionSeekPolicy), f"unknown seek tuning: {name}"
            setattr(self, name, value)
        self.steps = AsyncMock()

    async def async_issue_step(self, position_key, moving_up, default_step) -> None:
        del default_step
        await self.steps(position_key, moving_up)


class TestCoordinatorPositionSeek:
    """Test coordinator position seeking behavior."""

    async def test_seek_refreshes_stale_position_after_reconnect(
        self,
        hass: HomeAssistant,
        mock_config_entry,
    ) -> None:
        """A last-known target match must not suppress a command on a new BLE session."""
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        coordinator._client = MagicMock()
        coordinator._client.is_connected = True
        coordinator._position_connection_generation = 2
        coordinator._position_data["back"] = 50.0
        coordinator._position_data_generation["back"] = 1

        controller = make_controller_mock()
        controller.supports_direct_position_control = True
        controller.angle_to_native_position.return_value = 50
        controller.set_motor_position = AsyncMock()
        coordinator._controller = controller

        async def _refresh_position() -> None:
            coordinator._handle_position_update("back", 20.0)

        with patch.object(
            coordinator,
            "_async_read_positions",
            new=AsyncMock(side_effect=_refresh_position),
        ) as read_positions:
            await coordinator.async_seek_position(
                "back",
                50.0,
                AsyncMock(),
                AsyncMock(),
                AsyncMock(),
            )

        read_positions.assert_awaited_once_with()
        controller.set_motor_position.assert_awaited_once_with("back", 50)
        assert coordinator._position_data_generation["back"] == 2

    async def test_notification_only_seek_rejects_retained_position_after_reconnect(
        self,
        hass: HomeAssistant,
        mock_config_entry,
    ) -> None:
        """Prior-session feedback must not choose a notification-only seek direction."""
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        coordinator._client = MagicMock()
        coordinator._client.is_connected = True
        coordinator._position_connection_generation = 2
        coordinator._position_data["back"] = 50.0
        coordinator._position_data_generation["back"] = 1

        controller = make_controller_mock()
        coordinator._controller = controller
        move_up = AsyncMock()
        move_down = AsyncMock()
        move_stop = AsyncMock()

        with (
            patch.object(
                coordinator,
                "_async_read_positions",
                new=AsyncMock(),
            ) as read_positions,
            pytest.raises(PositionFeedbackError, match="no fresh position feedback available"),
        ):
            await coordinator.async_seek_position(
                "back",
                50.0,
                lambda c: move_up(c),
                lambda c: move_down(c),
                lambda c: move_stop(c),
            )

        read_positions.assert_awaited_once_with()
        move_up.assert_not_awaited()
        move_down.assert_not_awaited()
        move_stop.assert_not_awaited()

    async def test_seek_stops_on_first_target_crossing_for_single_direction_controllers(
        self,
        hass: HomeAssistant,
        mock_config_entry,
    ):
        """Pulse-driven controllers should use custom seek steps and stop on crossing."""
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        coordinator._client = MagicMock()
        coordinator._client.is_connected = True
        coordinator._position_data["legs"] = 0.0

        controller = make_controller_mock()
        controller.supports_direct_position_control = False
        controller.auto_stops_on_idle = True
        policy = _PulseStepPolicy(controller)
        controller.position_seek_policy = policy
        coordinator._controller = controller

        move_up = AsyncMock()
        move_down = AsyncMock()
        move_stop = AsyncMock()

        readings = iter([0.0, 27.0])

        async def _read_positions() -> None:
            coordinator._handle_position_update("legs", next(readings, 27.0))

        with (
            patch.object(
                coordinator,
                "_async_read_positions",
                new=AsyncMock(side_effect=_read_positions),
            ),
            patch(
                "custom_components.adjustable_bed.position_seek.asyncio.sleep",
                new=AsyncMock(),
            ),
        ):
            await coordinator.async_seek_position(
                "legs",
                20.0,
                lambda c: move_up(c),
                lambda c: move_down(c),
                lambda c: move_stop(c),
            )

        policy.steps.assert_awaited_once_with("legs", True)
        move_up.assert_not_awaited()
        move_down.assert_not_awaited()
        move_stop.assert_not_awaited()

    async def test_seek_reverses_on_overshoot_for_default_controllers(
        self,
        hass: HomeAssistant,
        mock_config_entry,
    ):
        """Controllers that allow overshoot correction should still reverse."""
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        coordinator._client = MagicMock()
        coordinator._client.is_connected = True
        coordinator._position_data["legs"] = 0.0

        controller = make_controller_mock()
        controller.supports_direct_position_control = False
        controller.auto_stops_on_idle = True
        coordinator._controller = controller

        move_up = AsyncMock()
        move_down = AsyncMock()
        move_stop = AsyncMock()
        readings = iter([0.0, 27.0, 20.0])

        async def _read_positions() -> None:
            coordinator._handle_position_update("legs", next(readings, 20.0))

        with (
            patch.object(
                coordinator,
                "_async_read_positions",
                new=AsyncMock(side_effect=_read_positions),
            ),
            patch(
                "custom_components.adjustable_bed.position_seek.asyncio.sleep",
                new=AsyncMock(),
            ),
        ):
            await coordinator.async_seek_position(
                "legs",
                20.0,
                lambda c: move_up(c),
                lambda c: move_down(c),
                lambda c: move_stop(c),
            )

        move_up.assert_awaited_once_with(controller)
        move_down.assert_awaited_once_with(controller)
        move_stop.assert_not_awaited()

    async def test_seek_uses_controller_specific_tolerance(
        self,
        hass: HomeAssistant,
        mock_config_entry,
    ) -> None:
        """Controllers can tighten the completion band without changing global seek behavior."""
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        coordinator._client = MagicMock()
        coordinator._client.is_connected = True
        coordinator._position_data["legs"] = 0.0

        controller = make_controller_mock()
        controller.supports_direct_position_control = False
        controller.auto_stops_on_idle = True
        policy = _PulseStepPolicy(controller, tolerance=0.5)
        controller.position_seek_policy = policy
        coordinator._controller = controller

        move_up = AsyncMock()
        move_down = AsyncMock()
        move_stop = AsyncMock()
        readings = iter([0.0, 7.0, 10.0])
        read_positions = AsyncMock(
            side_effect=lambda: coordinator._handle_position_update("legs", next(readings, 10.0))
        )

        with (
            patch.object(
                coordinator,
                "_async_read_positions",
                new=read_positions,
            ),
            patch(
                "custom_components.adjustable_bed.position_seek.asyncio.sleep",
                new=AsyncMock(),
            ),
        ):
            await coordinator.async_seek_position(
                "legs",
                10.0,
                lambda c: move_up(c),
                lambda c: move_down(c),
                lambda c: move_stop(c),
            )

        assert read_positions.await_count == 3
        policy.steps.assert_awaited_once_with("legs", True)
        move_up.assert_not_awaited()
        move_down.assert_not_awaited()
        move_stop.assert_not_awaited()

    async def test_seek_uses_controller_specific_stall_count(
        self,
        hass: HomeAssistant,
        mock_config_entry,
    ) -> None:
        """Controllers can reissue seek steps sooner than the generic stall loop."""
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        coordinator._client = MagicMock()
        coordinator._client.is_connected = True
        coordinator._position_data["legs"] = 0.0

        controller = make_controller_mock()
        controller.supports_direct_position_control = False
        controller.auto_stops_on_idle = True
        policy = _PulseStepPolicy(controller, tolerance=0.5, stall_count=1)
        controller.position_seek_policy = policy
        coordinator._controller = controller

        move_up = AsyncMock()
        move_down = AsyncMock()
        move_stop = AsyncMock()
        readings = iter([0.0, 7.0, 7.0, 10.0])

        async def _read_positions() -> None:
            coordinator._handle_position_update("legs", next(readings, 10.0))

        with (
            patch.object(
                coordinator,
                "_async_read_positions",
                new=AsyncMock(side_effect=_read_positions),
            ),
            patch(
                "custom_components.adjustable_bed.position_seek.asyncio.sleep",
                new=AsyncMock(),
            ),
        ):
            await coordinator.async_seek_position(
                "legs",
                10.0,
                lambda c: move_up(c),
                lambda c: move_down(c),
                lambda c: move_stop(c),
            )

        assert policy.steps.await_args_list == [call("legs", True), call("legs", True)]
        move_up.assert_not_awaited()
        move_down.assert_not_awaited()
        move_stop.assert_not_awaited()

    async def test_seek_chains_custom_steps_while_controller_is_still_moving(
        self,
        hass: HomeAssistant,
        mock_config_entry,
    ) -> None:
        """Controllers can chain seek bursts before a full stall to smooth long moves."""
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        coordinator._client = MagicMock()
        coordinator._client.is_connected = True
        coordinator._position_data["legs"] = 0.0

        controller = make_controller_mock()
        controller.supports_direct_position_control = False
        controller.auto_stops_on_idle = True
        policy = _PulseStepPolicy(
            controller,
            tolerance=0.5,
            stall_count=3,
            stall_threshold=0.2,
            chains_steps_while_moving=True,
            chain_min_remaining_distance=5.0,
        )
        controller.position_seek_policy = policy
        coordinator._controller = controller

        move_up = AsyncMock()
        move_down = AsyncMock()
        move_stop = AsyncMock()
        readings = iter([0.0, 10.0, 20.0])

        async def _read_positions() -> None:
            coordinator._handle_position_update("legs", next(readings, 20.0))

        with (
            patch.object(
                coordinator,
                "_async_read_positions",
                new=AsyncMock(side_effect=_read_positions),
            ),
            patch(
                "custom_components.adjustable_bed.position_seek.asyncio.sleep",
                new=AsyncMock(),
            ),
        ):
            await coordinator.async_seek_position(
                "legs",
                20.0,
                lambda c: move_up(c),
                lambda c: move_down(c),
                lambda c: move_stop(c),
            )

        assert policy.steps.await_args_list == [call("legs", True), call("legs", True)]
        move_up.assert_not_awaited()
        move_down.assert_not_awaited()
        move_stop.assert_not_awaited()

    async def test_seek_timeout_records_outcome_after_motor_cleanup(
        self,
        hass: HomeAssistant,
        mock_config_entry,
    ) -> None:
        """A feedback timeout should be terminal only after protocol cleanup."""
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        coordinator._client = MagicMock()
        coordinator._client.is_connected = True
        coordinator._position_data["legs"] = 0.0

        controller = make_controller_mock()
        controller.supports_direct_position_control = False
        controller.auto_stops_on_idle = False
        policy = PositionSeekPolicy(controller)
        policy.reverses_on_overshoot = False
        policy.timeout = 0
        controller.position_seek_policy = policy
        coordinator._controller = controller

        move_up = AsyncMock()
        move_down = AsyncMock()
        move_stop = AsyncMock()

        controller.read_positions = AsyncMock(
            side_effect=lambda _count: coordinator._handle_position_update("legs", 0.0)
        )
        with pytest.raises(TimeoutError, match="Position seek timed out"):
            await coordinator.async_seek_position(
                "legs",
                20.0,
                lambda c: move_up(c),
                lambda c: move_down(c),
                lambda c: move_stop(c),
            )

        move_up.assert_awaited_once_with(controller)
        move_down.assert_not_awaited()
        move_stop.assert_awaited_once_with(controller)
        record = coordinator._command_scheduler.recent_records[-1]
        assert record.kind is CommandKind.SEEK
        assert record.outcome is CommandOutcome.TIMEOUT

    async def test_connect_uses_persisted_bond_marker_to_skip_pairing(
        self,
        hass: HomeAssistant,
        mock_bluetooth_api,
        mock_bleak_client: MagicMock,
    ):
        """Persisted bond state should suppress re-pairing after restart."""
        del mock_bluetooth_api

        entry = MockConfigEntry(
            domain=DOMAIN,
            title="Persisted Bond OKIN Bed",
            data={
                CONF_ADDRESS: TEST_ADDRESS,
                CONF_NAME: TEST_NAME,
                CONF_BED_TYPE: BED_TYPE_OKIMAT,
                CONF_MOTOR_COUNT: 2,
                CONF_HAS_MASSAGE: False,
                CONF_DISABLE_ANGLE_SENSING: True,
                CONF_PREFERRED_ADAPTER: "auto",
                CONF_BLE_BOND_ESTABLISHED: True,
            },
            unique_id=TEST_ADDRESS,
            entry_id="persisted_bond_okin_test",
        )
        entry.add_to_hass(hass)

        adapter_result = MagicMock()
        adapter_result.device = MagicMock()
        adapter_result.device.address = TEST_ADDRESS
        adapter_result.device.name = TEST_NAME
        adapter_result.device.details = {"source": "local"}
        adapter_result.source = "local"
        adapter_result.rssi = -60
        adapter_result.connectable = True
        adapter_result.available_sources = ["local"]

        with (
            patch(
                "custom_components.adjustable_bed.coordinator_connection.select_adapter",
                new_callable=AsyncMock,
                return_value=adapter_result,
            ),
            patch(
                "custom_components.adjustable_bed.coordinator_connection.establish_connection",
                new_callable=AsyncMock,
                return_value=mock_bleak_client,
            ) as mock_establish_connection,
            patch_coordinator_global(
                "create_controller",
                new_callable=AsyncMock,
                return_value=make_controller_mock(),
            ),
        ):
            coordinator = AdjustableBedCoordinator(hass, entry)
            result = await coordinator.async_connect()

        assert result is True
        assert mock_establish_connection.await_args.kwargs["pair"] is False
        pairing_attempt = coordinator.pairing_diagnostics["connection_attempts"][0]["pairing"]
        assert pairing_attempt["decision"] == "bond_marker_present"
        assert pairing_attempt["bond_marker_before_attempt"] is True
        assert pairing_attempt["requested"] is False

    async def test_richmat_auto_remote_uses_live_ble_name_detection(
        self,
        hass: HomeAssistant,
    ):
        """An Auto Richmat remote is inferred from a live BLE name, never offline."""
        from custom_components.adjustable_bed.controller_factory import create_controller

        entry = MockConfigEntry(
            domain=DOMAIN,
            title="Richmat Test Bed",
            data={
                CONF_ADDRESS: TEST_ADDRESS,
                CONF_NAME: "Richmat Test Bed",
                CONF_BED_TYPE: BED_TYPE_RICHMAT,
                CONF_MOTOR_COUNT: 2,
                CONF_HAS_MASSAGE: True,
                CONF_DISABLE_ANGLE_SENSING: True,
                CONF_PREFERRED_ADAPTER: "auto",
                CONF_RICHMAT_REMOTE: RICHMAT_REMOTE_AUTO,
            },
            unique_id=TEST_ADDRESS,
            entry_id="richmat_auto_remote_test",
        )
        entry.add_to_hass(hass)
        coordinator = AdjustableBedCoordinator(hass, entry)
        client = MagicMock(is_connected=True)

        live = await create_controller(
            coordinator, BED_TYPE_RICHMAT, "nordic", client, device_name="QRRM141291"
        )
        offline = await create_controller(
            coordinator, BED_TYPE_RICHMAT, "nordic", None, device_name="QRRM141291"
        )

        assert live._remote_code == "qrrm"
        assert offline._remote_code == RICHMAT_REMOTE_AUTO

    async def test_connect_auto_mode_sets_fresh_device_callback_with_selected_source(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_bluetooth_api,
        mock_bleak_client: MagicMock,
    ):
        """Auto mode should pass a callback that refreshes device from selected source."""
        del mock_bluetooth_api

        adapter_result = MagicMock()
        adapter_result.device = MagicMock()
        adapter_result.device.address = TEST_ADDRESS
        adapter_result.device.name = TEST_NAME
        adapter_result.device.details = {"source": "proxy_1"}
        adapter_result.source = "proxy_1"
        adapter_result.rssi = -67

        fresh_device = MagicMock()
        fresh_device.address = TEST_ADDRESS
        fresh_device.name = TEST_NAME
        fresh_device.details = {"source": "proxy_1"}

        svc_info = MagicMock()
        svc_info.address = TEST_ADDRESS
        svc_info.source = "proxy_1"
        svc_info.rssi = -64
        svc_info.device = fresh_device

        with (
            patch(
                "custom_components.adjustable_bed.coordinator_connection.select_adapter",
                new_callable=AsyncMock,
                return_value=adapter_result,
            ),
            patch(
                "custom_components.adjustable_bed.coordinator_connection.establish_connection",
                new_callable=AsyncMock,
                return_value=mock_bleak_client,
            ) as mock_establish_connection,
            patch_coordinator_global(
                "create_controller",
                new_callable=AsyncMock,
                return_value=make_controller_mock(),
            ),
            patch(
                "custom_components.adjustable_bed.coordinator.bluetooth.async_discovered_service_info",
                return_value=[svc_info],
            ),
        ):
            coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
            result = await coordinator.async_connect()

            assert result is True
            ble_device_callback = mock_establish_connection.await_args.kwargs["ble_device_callback"]
            assert ble_device_callback is not None
            assert ble_device_callback() is fresh_device

    async def test_connect_auto_mode_callback_falls_back_when_source_missing(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_bluetooth_api,
        mock_bleak_client: MagicMock,
    ):
        """Auto mode callback should fall back to default lookup if selected source disappears."""
        del mock_bluetooth_api

        adapter_result = MagicMock()
        adapter_result.device = MagicMock()
        adapter_result.device.address = TEST_ADDRESS
        adapter_result.device.name = TEST_NAME
        adapter_result.device.details = {"source": "proxy_1"}
        adapter_result.source = "proxy_1"
        adapter_result.rssi = -67

        stale_source_info = MagicMock()
        stale_source_info.address = TEST_ADDRESS
        stale_source_info.source = "proxy_2"
        stale_source_info.rssi = -72
        stale_source_info.device = MagicMock()

        fallback_device = MagicMock()
        fallback_device.address = TEST_ADDRESS
        fallback_device.name = TEST_NAME
        fallback_device.details = {"source": "local"}

        with (
            patch(
                "custom_components.adjustable_bed.coordinator_connection.select_adapter",
                new_callable=AsyncMock,
                return_value=adapter_result,
            ),
            patch(
                "custom_components.adjustable_bed.coordinator_connection.establish_connection",
                new_callable=AsyncMock,
                return_value=mock_bleak_client,
            ) as mock_establish_connection,
            patch_coordinator_global(
                "create_controller",
                new_callable=AsyncMock,
                return_value=make_controller_mock(),
            ),
            patch(
                "custom_components.adjustable_bed.coordinator.bluetooth.async_discovered_service_info",
                return_value=[stale_source_info],
            ),
            patch(
                "custom_components.adjustable_bed.coordinator.bluetooth.async_ble_device_from_address",
                return_value=fallback_device,
            ),
        ):
            coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
            result = await coordinator.async_connect()

            assert result is True
            ble_device_callback = mock_establish_connection.await_args.kwargs["ble_device_callback"]
            assert ble_device_callback is not None
            assert ble_device_callback() is fallback_device
            assert coordinator.connection_attempt_details[0]["actual_source"] == "local"

    async def test_connect_slot_failure_records_fallback_source(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_bluetooth_api,
    ):
        """A failed connect should identify the source returned by its callback."""
        del mock_bluetooth_api

        selected_device = MagicMock(
            address=TEST_ADDRESS,
            name=TEST_NAME,
            details={"source": "proxy_1"},
        )
        adapter_result = MagicMock(
            device=selected_device,
            source="proxy_1",
            rssi=-67,
            connectable=True,
            available_sources=("proxy_1", "local"),
        )
        fallback_device = MagicMock(
            address=TEST_ADDRESS,
            name=TEST_NAME,
            details={"source": "local"},
        )

        async def fail_from_fallback(*_args: Any, **kwargs: Any):
            assert kwargs["ble_device_callback"]() is fallback_device
            raise BleakError("No connection slot available")

        with (
            patch(
                "custom_components.adjustable_bed.coordinator_connection.select_adapter",
                new_callable=AsyncMock,
                return_value=adapter_result,
            ),
            patch(
                "custom_components.adjustable_bed.coordinator_connection.establish_connection",
                new_callable=AsyncMock,
                side_effect=fail_from_fallback,
            ),
            patch(
                "custom_components.adjustable_bed.coordinator.bluetooth.async_discovered_service_info",
                return_value=[],
            ),
            patch(
                "custom_components.adjustable_bed.coordinator.bluetooth.async_ble_device_from_address",
                return_value=fallback_device,
            ),
        ):
            coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
            coordinator._max_retries = 1

            assert await coordinator.async_connect() is False

        attempt = coordinator.connection_attempt_details[0]
        assert attempt["selected_source"] == "proxy_1"
        assert attempt["actual_source"] == "local"

    async def test_disconnect(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test disconnection."""
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        await coordinator.async_connect()

        await coordinator.async_disconnect()

        mock_bleak_client.disconnect.assert_called_once()

    async def test_ensure_connected_when_connected(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test ensure_connected returns True when already connected."""
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        await coordinator.async_connect()

        result = await coordinator.async_ensure_connected()

        assert result is True

    async def test_ensure_connected_reconnects(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test ensure_connected reconnects when disconnected."""
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)

        # First call will connect
        result = await coordinator.async_ensure_connected()

        assert result is True


class TestCoordinatorPositionCallbacks:
    """Test coordinator position callback handling."""

    async def test_register_position_callback(
        self,
        hass: HomeAssistant,
        mock_config_entry,
    ):
        """Test registering position callbacks."""
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        callback = MagicMock()

        unregister = coordinator.register_position_callback(callback)

        assert callback in coordinator._position_callbacks
        assert callable(unregister)

    async def test_unregister_position_callback(
        self,
        hass: HomeAssistant,
        mock_config_entry,
    ):
        """Test unregistering position callbacks."""
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        callback = MagicMock()

        unregister = coordinator.register_position_callback(callback)
        unregister()

        assert callback not in coordinator._position_callbacks

    async def test_position_update_triggers_callbacks(
        self,
        hass: HomeAssistant,
        mock_config_entry,
    ):
        """Test position updates trigger all callbacks."""
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        callback1 = MagicMock()
        callback2 = MagicMock()

        coordinator.register_position_callback(callback1)
        coordinator.register_position_callback(callback2)

        # Simulate position update
        coordinator._handle_position_update("back", 45.0)

        assert coordinator.position_data["back"] == 45.0
        callback1.assert_called_once_with({"back": 45.0})
        callback2.assert_called_once_with({"back": 45.0})
