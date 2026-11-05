"""Tests for the coordinator's BLE connection lifecycle."""

from __future__ import annotations

import asyncio
import contextlib
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bleak.exc import BleakError
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed.bluetooth_transport import (
    ConnectionPath,
    TransportClass,
)
from custom_components.adjustable_bed.bond_verification import (
    BondEvidence,
    BondOwner,
    BondVerificationStatus,
)
from custom_components.adjustable_bed.command_scheduler import (
    current_command_context,
)
from custom_components.adjustable_bed.const import (
    BED_TYPE_KAIDI,
    BED_TYPE_KEESON,
    BED_TYPE_LEGGETT_GEN2,
    BED_TYPE_LEGGETT_OKIN,
    BED_TYPE_LINAK,
    BED_TYPE_OCTO,
    BED_TYPE_OKIMAT,
    BED_TYPE_OKIN_CST,
    BED_TYPE_SLEEP_NUMBER,
    BED_TYPE_SLEEP_NUMBER_MCR,
    CONF_BED_TYPE,
    CONF_BLE_BOND_ESTABLISHED,
    CONF_BLE_BOND_MARKER_UNRELIABLE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_HAS_MASSAGE,
    CONF_MOTOR_COUNT,
    CONF_PASSIVE_POSITION_RECONCILIATION,
    CONF_PREFERRED_ADAPTER,
    DEVICE_INFO_CHARS,
    DOMAIN,
)
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from tests.coordinator_patches import patch_coordinator_global

from .conftest import TEST_ADDRESS, TEST_NAME, make_controller_mock


class TestCoordinatorConnection:
    """Test coordinator connection handling."""

    @pytest.mark.parametrize("outcome", ["verified", "auth_failed", "inconclusive", "cancelled"])
    async def test_pairing_repair_waits_for_automatic_recovery(
        self, hass, mock_coordinator_connected, mock_bleak_client, outcome
    ):
        """Recovering a stale bond must not flash a repair between attempts."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            data={
                CONF_ADDRESS: TEST_ADDRESS,
                CONF_NAME: TEST_NAME,
                CONF_BED_TYPE: BED_TYPE_LEGGETT_OKIN,
                CONF_DISABLE_ANGLE_SENSING: True,
                CONF_BLE_BOND_ESTABLISHED: True,
            },
            unique_id=TEST_ADDRESS,
        )
        entry.add_to_hass(hass)
        coordinator = AdjustableBedCoordinator(hass, entry)
        coordinator._max_retries = 2
        reads = 0

        async def read_characteristic(_uuid):
            nonlocal reads
            reads += 1
            create_issue.assert_not_awaited()
            if reads == 1 or outcome == "auth_failed":
                raise BleakError("Insufficient authentication")
            if outcome == "cancelled":
                raise asyncio.CancelledError
            if outcome == "inconclusive":
                raise TimeoutError
            return b"Model"

        mock_bleak_client.read_gatt_char.side_effect = read_characteristic
        with (
            patch(
                "custom_components.adjustable_bed.coordinator_bonds.create_pairing_required_issue",
                new_callable=AsyncMock,
            ) as create_issue,
            patch(
                "custom_components.adjustable_bed.coordinator_connection.read_ble_device_info",
                new=AsyncMock(return_value=("Leggett", "Model")),
            ),
        ):
            if outcome == "cancelled":
                with pytest.raises(asyncio.CancelledError):
                    await coordinator.async_connect()
            else:
                result = await coordinator.async_connect()
                assert result is (outcome != "auth_failed")

            if outcome == "verified":
                create_issue.assert_not_awaited()
                assert coordinator.pairing_diagnostics["last_bond_verification"]["status"] == "succeeded"
            else:
                create_issue.assert_awaited_once()
                assert create_issue.await_args.kwargs["evidence"]["status"] == "auth_failed"

        assert coordinator._connection_attempt_count == 2

    @pytest.mark.parametrize("bond_intact", [True, False])
    async def test_stale_cache_clear_on_last_attempt_still_reconnects_once(
        self, hass, mock_coordinator_connected, mock_bleak_client, bond_intact
    ):
        """Issue #660: the rediscovered verification is not lost to the attempt budget."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            data={
                CONF_ADDRESS: TEST_ADDRESS,
                CONF_NAME: TEST_NAME,
                CONF_BED_TYPE: BED_TYPE_LEGGETT_OKIN,
                CONF_DISABLE_ANGLE_SENSING: True,
                CONF_BLE_BOND_ESTABLISHED: True,
            },
            unique_id=TEST_ADDRESS,
        )
        entry.add_to_hass(hass)
        coordinator = AdjustableBedCoordinator(hass, entry)
        coordinator._max_retries = 1
        reads = 0

        async def read_characteristic(_uuid):
            nonlocal reads
            reads += 1
            if reads == 1 or not bond_intact:
                raise BleakError("Insufficient encryption")
            return b"Model"

        mock_bleak_client.read_gatt_char.side_effect = read_characteristic
        with (
            patch(
                "custom_components.adjustable_bed.coordinator_bonds.create_pairing_required_issue",
                new_callable=AsyncMock,
            ) as create_issue,
            patch(
                "custom_components.adjustable_bed.coordinator_connection.read_ble_device_info",
                new=AsyncMock(return_value=("Leggett", "Model")),
            ),
            patch(
                "custom_components.adjustable_bed.coordinator_bonds.async_clear_proxy_gatt_cache",
                new=AsyncMock(return_value=True),
            ),
            patch(
                "custom_components.adjustable_bed.coordinator_connection.client_source",
                return_value="proxy-a",
            ),
            patch(
                "custom_components.adjustable_bed.coordinator_connection.async_path_for_source",
                return_value=ConnectionPath(
                    source="proxy-a", transport=TransportClass.PROXY, source_domain="esphome"
                ),
            ),
        ):
            assert await coordinator.async_connect() is bond_intact

        # A verification that still fails earns the pairing attempt it now justifies.
        assert coordinator._connection_attempt_count == (2 if bond_intact else 3)
        assert create_issue.await_count == int(not bond_intact)
        # Recovery closes the episode, so a later outage gets a fresh retry.
        assert coordinator._stale_gatt_retry_sources == (set() if bond_intact else {"proxy-a"})

    async def test_rerouted_stale_cache_verification_returns_to_the_cleared_proxy(
        self, hass, mock_coordinator_connected, mock_bleak_client
    ):
        """Issue #660: a reroute does not use up the cleared proxy's verification."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            data={
                CONF_ADDRESS: TEST_ADDRESS,
                CONF_NAME: TEST_NAME,
                CONF_BED_TYPE: BED_TYPE_LEGGETT_OKIN,
                CONF_DISABLE_ANGLE_SENSING: True,
                CONF_BLE_BOND_ESTABLISHED: True,
            },
            unique_id=TEST_ADDRESS,
        )
        entry.add_to_hass(hass)
        coordinator = AdjustableBedCoordinator(hass, entry)
        coordinator._max_retries = 1

        def route(_client):
            return "proxy-b" if coordinator._connection_attempt_count == 2 else "proxy-a"

        def path(_hass, source, **_kwargs):
            return ConnectionPath(
                source=source, transport=TransportClass.PROXY, source_domain="esphome"
            )

        async def read_characteristic(_uuid):
            if coordinator._connection_attempt_count < 3:
                raise BleakError("Insufficient encryption")
            return b"Model"

        mock_bleak_client.read_gatt_char.side_effect = read_characteristic
        from custom_components.adjustable_bed import coordinator_connection

        select = AsyncMock(side_effect=coordinator_connection.select_adapter)
        with (
            patch(
                "custom_components.adjustable_bed.coordinator_bonds.create_pairing_required_issue",
                new_callable=AsyncMock,
            ),
            patch(
                "custom_components.adjustable_bed.coordinator_connection.read_ble_device_info",
                new=AsyncMock(return_value=("Leggett", "Model")),
            ),
            patch(
                "custom_components.adjustable_bed.coordinator_bonds.async_clear_proxy_gatt_cache",
                new=AsyncMock(return_value=True),
            ),
            patch("custom_components.adjustable_bed.coordinator_connection.client_source", side_effect=route),
            patch(
                "custom_components.adjustable_bed.coordinator_connection.async_path_for_source",
                side_effect=path,
            ),
            patch("custom_components.adjustable_bed.coordinator_connection.select_adapter", new=select),
        ):
            assert await coordinator.async_connect() is True

        assert coordinator._connection_attempt_count == 3
        assert [call.args[2] for call in select.await_args_list][1:] == ["proxy-a", "proxy-a"]

    @pytest.mark.parametrize("failure", ["connect", "before_probe"])
    async def test_stale_cache_verification_survives_a_failed_reconnect(
        self, hass, mock_coordinator_connected, mock_bleak_client, mock_establish_connection,
        failure,
    ):
        """Issue #660: a reconnect that never reaches the proxy does not spend its check."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            data={
                CONF_ADDRESS: TEST_ADDRESS,
                CONF_NAME: TEST_NAME,
                CONF_BED_TYPE: BED_TYPE_LEGGETT_OKIN,
                CONF_DISABLE_ANGLE_SENSING: True,
                CONF_BLE_BOND_ESTABLISHED: True,
            },
            unique_id=TEST_ADDRESS,
        )
        entry.add_to_hass(hass)
        coordinator = AdjustableBedCoordinator(hass, entry)
        coordinator._max_retries = 1
        reads = 0
        connect = mock_establish_connection.side_effect

        async def establish(*args, **kwargs):
            if failure == "connect" and coordinator._connection_attempt_count == 2:
                raise TimeoutError("no answer")
            return await connect(*args, **kwargs)

        verify = coordinator._async_verify_bonded

        async def verify_bonded(*args, **kwargs):
            if failure == "before_probe" and coordinator._connection_attempt_count == 2:
                raise TimeoutError("link dropped before the probe")
            return await verify(*args, **kwargs)

        async def read_characteristic(_uuid):
            nonlocal reads
            reads += 1
            if reads == 1:
                raise BleakError("Insufficient encryption")
            return b"Model"

        mock_establish_connection.side_effect = establish
        mock_bleak_client.read_gatt_char.side_effect = read_characteristic
        from custom_components.adjustable_bed import coordinator_connection

        select = AsyncMock(side_effect=coordinator_connection.select_adapter)
        with (
            patch(
                "custom_components.adjustable_bed.coordinator_bonds.create_pairing_required_issue",
                new_callable=AsyncMock,
            ),
            patch(
                "custom_components.adjustable_bed.coordinator_connection.read_ble_device_info",
                new=AsyncMock(return_value=("Leggett", "Model")),
            ),
            patch(
                "custom_components.adjustable_bed.coordinator_bonds.async_clear_proxy_gatt_cache",
                new=AsyncMock(return_value=True),
            ),
            patch(
                "custom_components.adjustable_bed.coordinator_connection.client_source",
                return_value="proxy-a",
            ),
            patch(
                "custom_components.adjustable_bed.coordinator_connection.async_path_for_source",
                return_value=ConnectionPath(
                    source="proxy-a", transport=TransportClass.PROXY, source_domain="esphome"
                ),
            ),
            patch("custom_components.adjustable_bed.coordinator_connection.select_adapter", new=select),
            patch.object(coordinator, "_async_verify_bonded", side_effect=verify_bonded),
        ):
            assert await coordinator.async_connect() is True

        assert coordinator._connection_attempt_count == 3
        assert [call.args[2] for call in select.await_args_list][1:] == ["proxy-a", "proxy-a"]
        assert coordinator._ble_bond_established is True

    async def test_runtime_stale_cache_verification_survives_into_the_next_connect(
        self, hass, mock_config_entry, mock_coordinator_connected
    ):
        """A command's cache clear steers the following connect to that proxy."""
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        coordinator._stale_gatt_retry_source = "proxy-a"
        coordinator._skip_pair_next_attempt = True
        from custom_components.adjustable_bed import coordinator_connection

        select = AsyncMock(side_effect=coordinator_connection.select_adapter)
        with patch("custom_components.adjustable_bed.coordinator_connection.select_adapter", new=select):
            assert await coordinator.async_connect() is True

        assert select.await_args_list[0].args[2] == "proxy-a"
        assert coordinator._stale_gatt_retry_source is None

    async def test_connect_success(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test successful connection."""
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        result = await coordinator.async_connect()

        assert result is True
        assert coordinator.controller is not None

    async def test_connect_records_the_scanner_that_actually_routed_the_client(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ) -> None:
        """A rerouted wrapper must not inherit its original device's source."""
        mock_bleak_client._connected_scanner = SimpleNamespace(source="routed-scanner")
        mock_bleak_client._backend = SimpleNamespace(
            _device=SimpleNamespace(details={"source": "original-scanner"})
        )
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)

        assert await coordinator.async_connect() is True
        assert coordinator._actual_adapter == "routed-scanner"

    async def test_connect_arms_disconnect_timer_after_post_connect_hydration(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
    ):
        """Idle timer should start only after post-connect hydration completes."""
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        call_order: list[str] = []

        async def _start_notify() -> None:
            call_order.append("notify")

        async def _refresh_light_state() -> None:
            call_order.append("light")

        def _reset_timer() -> None:
            call_order.append("timer")

        with (
            patch.object(
                coordinator,
                "async_start_notify",
                new_callable=AsyncMock,
                side_effect=_start_notify,
            ) as mock_start_notify,
            patch.object(
                coordinator,
                "_should_refresh_readable_light_state",
                return_value=True,
            ),
            patch.object(
                coordinator,
                "_async_refresh_readable_light_state",
                new_callable=AsyncMock,
                side_effect=_refresh_light_state,
            ) as mock_refresh,
            patch.object(
                coordinator,
                "_reset_disconnect_timer",
                side_effect=_reset_timer,
            ) as mock_reset_timer,
        ):
            result = await coordinator.async_connect()

        assert result is True
        mock_start_notify.assert_awaited_once()
        mock_refresh.assert_awaited_once()
        mock_reset_timer.assert_called_once()
        assert call_order == ["notify", "light", "timer"]

    @pytest.mark.usefixtures("mock_coordinator_connected")
    async def test_connect_closes_stale_connections_before_connect(
        self,
        hass: HomeAssistant,
        mock_config_entry,
    ):
        """Test connection attempts close stale BlueZ state before GATT connect."""
        with patch(
            "custom_components.adjustable_bed.coordinator_connection.close_stale_connections_by_address",
            new_callable=AsyncMock,
        ) as mock_close_stale:
            coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
            result = await coordinator.async_connect()

        assert result is True
        mock_close_stale.assert_called_once_with(TEST_ADDRESS)

    async def test_connect_device_not_found(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_bluetooth_api,
    ):
        """Test connection fails when device not found."""
        with patch(
            "custom_components.adjustable_bed.coordinator.bluetooth.async_ble_device_from_address",
            return_value=None,
        ):
            coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
            result = await coordinator.async_connect()

        assert result is False
        assert coordinator.controller is None

    @pytest.mark.parametrize(
        "bed_type,path_count,success_at,expected_attempts",
        [
            (BED_TYPE_LINAK, 2, 4, 4),
            (BED_TYPE_LINAK, 2, None, 5),
            (BED_TYPE_LINAK, 1, 4, 3),
            (BED_TYPE_KEESON, 2, 4, 4),
            (BED_TYPE_KEESON, 2, None, 5),
            (BED_TYPE_KEESON, 1, 4, 3),
        ],
    )
    async def test_retries_reach_alternative_paths_with_bounded_backoff(
        self, hass, mock_config_entry, mock_coordinator_connected, mock_bleak_client,
        bed_type, path_count, success_at, expected_attempts,
    ):
        """HA's strong failed paths must not exhaust the budget before fallback."""
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        coordinator._bed_type = bed_type
        coordinator._retry_base_delay = 2
        attempts = 0

        async def connect(*_args, **_kwargs):
            nonlocal attempts
            attempts += 1
            if attempts != success_at:
                raise BleakError("ESP_GATT_ERROR while connecting")
            return mock_bleak_client

        with (
            patch("custom_components.adjustable_bed.coordinator_connection.async_connection_paths", return_value=tuple(
                ConnectionPath(source=f"proxy-{i}") for i in range(path_count)
            )),
            patch("custom_components.adjustable_bed.coordinator_connection.establish_connection", side_effect=connect),
            patch("custom_components.adjustable_bed.coordinator_connection.random.uniform", return_value=1),
            patch("custom_components.adjustable_bed.coordinator.asyncio.sleep", new=AsyncMock()) as sleep,
        ):
            result = await coordinator.async_connect()

        assert result is (success_at is not None and success_at <= expected_attempts)
        assert attempts == expected_attempts
        retry_delays = [call.args[0] for call in sleep.await_args_list if call.args[0] >= 2]
        assert retry_delays == [2, *([4] * (expected_attempts - 2))]

    async def test_connect_bleak_error(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_async_ble_device_from_address,
        mock_bluetooth_api,
    ):
        """Test connection handles BleakError."""
        with patch(
            "custom_components.adjustable_bed.coordinator_connection.establish_connection",
            new_callable=AsyncMock,
            side_effect=BleakError("Connection failed"),
        ):
            coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
            result = await coordinator.async_connect()

        assert result is False

    async def test_failed_attempt_does_not_reuse_previous_connection_path(
        self,
        hass: HomeAssistant,
        mock_async_ble_device_from_address,
        mock_bluetooth_api,
    ) -> None:
        """A pre-connect auth failure has no proven transport owner."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            title=TEST_NAME,
            data={
                CONF_ADDRESS: TEST_ADDRESS,
                CONF_NAME: TEST_NAME,
                CONF_BED_TYPE: BED_TYPE_OKIMAT,
                CONF_MOTOR_COUNT: 2,
                CONF_HAS_MASSAGE: False,
                CONF_DISABLE_ANGLE_SENSING: True,
                CONF_PREFERRED_ADAPTER: "auto",
            },
            unique_id=TEST_ADDRESS,
            entry_id="failed_attempt_connection_path_test",
        )
        entry.add_to_hass(hass)
        auth_error = BleakError("Insufficient authentication")

        with (
            patch(
                "custom_components.adjustable_bed.coordinator_connection.establish_connection",
                new_callable=AsyncMock,
                side_effect=auth_error,
            ),
            patch(
                "custom_components.adjustable_bed.coordinator_bonds.create_pairing_required_issue",
                new_callable=AsyncMock,
            ) as create_issue,
        ):
            coordinator = AdjustableBedCoordinator(hass, entry)
            coordinator._max_retries = 1
            coordinator._connection_path = ConnectionPath(
                source="old-host",
                transport=TransportClass.LOCAL,
                adapter="hci0",
            )
            result = await coordinator.async_connect()

        assert result is False
        evidence = create_issue.await_args.kwargs["evidence"]
        assert evidence["owner"]["transport"] == "unknown"
        assert evidence["owner"]["source"] is None

    async def test_connect_detects_existing_bond_and_skips_pairing(
        self,
        hass: HomeAssistant,
        mock_bluetooth_api,
        mock_bleak_client: MagicMock,
    ):
        """Pair-required beds should skip pair=True when BlueZ already reports a bond."""
        del mock_bluetooth_api

        entry = MockConfigEntry(
            domain=DOMAIN,
            title="Paired OKIN Bed",
            data={
                CONF_ADDRESS: TEST_ADDRESS,
                CONF_NAME: TEST_NAME,
                CONF_BED_TYPE: BED_TYPE_OKIMAT,
                CONF_MOTOR_COUNT: 2,
                CONF_HAS_MASSAGE: False,
                CONF_DISABLE_ANGLE_SENSING: True,
                CONF_PREFERRED_ADAPTER: "auto",
            },
            unique_id=TEST_ADDRESS,
            entry_id="paired_okin_test",
        )
        entry.add_to_hass(hass)

        adapter_result = MagicMock()
        adapter_result.device = MagicMock()
        adapter_result.device.address = TEST_ADDRESS
        adapter_result.device.name = TEST_NAME
        adapter_result.device.details = {
            "source": "local",
            "props": {"Paired": True, "Bonded": True},
        }
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
        assert entry.data[CONF_BLE_BOND_ESTABLISHED] is True
        pairing = coordinator.pairing_diagnostics
        assert pairing["required"] is True
        assert pairing["runtime_bond_established"] is True
        assert pairing["connection_attempts"][0]["pairing"]["decision"] == (
            "existing_os_bond_detected"
        )
        assert pairing["connection_attempts"][0]["pairing"]["os_bond_reported"] is True
        assert pairing["connection_attempts"][0]["pairing"]["requested"] is False

    @pytest.mark.parametrize(
        "bond_data",
        [
            pytest.param({}, id="unpaired"),
            # A repair records a bond but keeps the latch. That marker must not
            # skip pairing: an unpaired proxy reconnect stays unencrypted and
            # brings the repair straight back (issue #709).
            pytest.param(
                {CONF_BLE_BOND_ESTABLISHED: True, CONF_BLE_BOND_MARKER_UNRELIABLE: True},
                id="latched_after_repair",
            ),
        ],
    )
    async def test_leggett_gen2_connects_discovers_then_pairs(
        self,
        hass: HomeAssistant,
        mock_bluetooth_api,
        mock_bleak_client: MagicMock,
        bond_data: dict[str, bool],
    ) -> None:
        """Gen2 coordinator pairing must follow the LP Control app ordering."""
        del mock_bluetooth_api

        entry = MockConfigEntry(
            domain=DOMAIN,
            title="Unpaired LP Gen2 Bed",
            data={
                CONF_ADDRESS: TEST_ADDRESS,
                CONF_NAME: TEST_NAME,
                CONF_BED_TYPE: BED_TYPE_LEGGETT_GEN2,
                CONF_MOTOR_COUNT: 4,
                CONF_HAS_MASSAGE: True,
                CONF_DISABLE_ANGLE_SENSING: True,
                CONF_PREFERRED_ADAPTER: "auto",
                **bond_data,
            },
            unique_id=TEST_ADDRESS,
            entry_id="leggett_gen2_pair_order_test",
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

        events: list[str] = []

        async def establish(*_args: object, **_kwargs: object) -> MagicMock:
            events.append("connect_and_discover")
            return mock_bleak_client

        async def pair() -> None:
            events.append("pair")

        mock_bleak_client.pair = AsyncMock(side_effect=pair)

        controller = make_controller_mock()
        controller.requires_persistent_connection = True
        controller.requires_notification_channel = False
        controller.supports_under_bed_lights = False

        with (
            patch(
                "custom_components.adjustable_bed.coordinator_connection.select_adapter",
                new_callable=AsyncMock,
                return_value=adapter_result,
            ),
            patch(
                "custom_components.adjustable_bed.coordinator_connection.establish_connection",
                new=AsyncMock(side_effect=establish),
            ) as mock_establish_connection,
            patch(
                "custom_components.adjustable_bed.coordinator_connection.discover_services",
                new_callable=AsyncMock,
                return_value=True,
            ),
            patch(
                "custom_components.adjustable_bed.coordinator_connection.read_ble_device_info",
                new_callable=AsyncMock,
                return_value=(None, None),
            ),
            patch.object(
                AdjustableBedCoordinator,
                "_async_verify_bonded",
                new_callable=AsyncMock,
                return_value=True,
            ),
            patch_coordinator_global(
                "create_controller",
                new_callable=AsyncMock,
                return_value=controller,
            ),
            patch(
                "custom_components.adjustable_bed.coordinator.asyncio.sleep",
                new=AsyncMock(),
            ),
            patch_coordinator_global(
                "delete_pairing_required_issue",
                new_callable=AsyncMock,
            ) as delete_issue,
            patch(
                "custom_components.adjustable_bed.coordinator_bonds.create_pairing_required_issue",
                new_callable=AsyncMock,
            ) as create_issue,
        ):
            coordinator = AdjustableBedCoordinator(hass, entry)
            coordinator._max_retries = 1
            if bond_data:
                # The runtime failure that latched the marker is retired by
                # this link's bond, not re-raised when the connect finishes.
                coordinator._last_bond_evidence = BondEvidence(
                    status=BondVerificationStatus.AUTH_FAILED,
                    owner=BondOwner(transport=TransportClass.PROXY, source="proxy-a"),
                    operation="runtime_gatt_access",
                    observed_at="2026-10-27T21:19:09+00:00",
                )
            result = await coordinator.async_connect()

        assert result is True
        assert events == ["connect_and_discover", "pair"]
        # The bond on this link clears an earlier session's repair, since the
        # Gen2 probe is never conclusive on its own.
        delete_issue.assert_awaited_once_with(hass, TEST_ADDRESS)
        create_issue.assert_not_awaited()
        assert mock_establish_connection.await_args.kwargs["pair"] is False
        assert mock_establish_connection.await_args.kwargs["use_services_cache"] is False
        mock_bleak_client.pair.assert_awaited_once_with()
        assert entry.data[CONF_BLE_BOND_ESTABLISHED] is True

        pairing = coordinator.pairing_diagnostics["connection_attempts"][0]["pairing"]
        assert pairing["requested"] is True
        assert pairing["ordering"] == "connect_discover_then_pair"
        assert pairing["connection_result"] == "pairing_connection_succeeded"

    @pytest.mark.parametrize(
        ("bed_type", "retain_link", "keeps_link"),
        [
            # The bond probe runs before controller startup, so its caller can
            # still use the link: keep it (issue #385).
            (BED_TYPE_LEGGETT_GEN2, True, True),
            # Startup already failed. A link with no controller cannot drive the
            # bed and would only block the physical remote.
            (BED_TYPE_LEGGETT_GEN2, False, False),
            # A bed that reconnects freely must always take the normal path;
            # retain_link must not be read as "this is a one-connection bed".
            (BED_TYPE_OKIN_CST, True, False),
        ],
    )
    async def test_auth_error_retains_the_link_only_where_it_is_usable(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        bed_type: str,
        retain_link: bool,
        keeps_link: bool,
    ) -> None:
        """Only the probe path on a one-connection bed may keep an unbonded link."""
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        coordinator._bed_type = bed_type

        client = MagicMock()
        client.is_connected = True
        client.disconnect = AsyncMock()
        coordinator._client = client

        with patch.object(
            coordinator, "_async_disconnect_locked", new_callable=AsyncMock
        ) as disconnect_locked:
            await coordinator._async_handle_ble_authentication_error(
                BleakError("Insufficient authentication"),
                holding_lock=True,
                retain_link=retain_link,
            )

        if keeps_link:
            disconnect_locked.assert_not_awaited()
            assert coordinator._client is client
        else:
            disconnect_locked.assert_awaited_once()

    async def test_only_a_working_command_closes_the_stale_cache_episode(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
    ) -> None:
        """Issue #660: startup alone does not prove the link authenticates."""
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        await coordinator.async_connect()
        coordinator._stale_gatt_retry_sources.add("proxy-a")

        async def failing(_controller):
            raise BleakError("not connected")

        with pytest.raises(BleakError):
            await coordinator.async_execute_controller_command(failing, cancel_running=False)
        assert coordinator._stale_gatt_retry_sources == {"proxy-a"}

        async def cancel_operation(task, **_kwargs):
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

        with patch.object(
            coordinator, "_async_wait_for_controller_operation", side_effect=cancel_operation
        ):
            await coordinator.async_execute_controller_command(
                AsyncMock(), cancel_running=False
            )
        assert coordinator._stale_gatt_retry_sources == {"proxy-a"}

        await coordinator.async_execute_controller_command(AsyncMock(), cancel_running=False)
        assert coordinator._stale_gatt_retry_sources == set()

        await coordinator.async_disconnect()

    async def test_runtime_auth_failure_keeps_a_one_connection_link(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
    ) -> None:
        """A command-time auth failure must not spend the bed's one connection.

        The probe path passes retain_link=True and the startup path deliberately
        does not, but a runtime command is a third case: the controller is
        already initialised, so the link still drives the bed and async_pair_now()
        can bond through it. Dropping it left the repair unable to reconnect
        until the bed was power-cycled.
        """
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        await coordinator.async_connect()
        coordinator._bed_type = BED_TYPE_LEGGETT_GEN2

        async def _auth_failure_command(_controller):
            raise BleakError(
                "Bluetooth GATT Error address=AA:BB:CC:DD:EE:FF "
                "handle=19 error=5 description=Insufficient authentication"
            )

        client = coordinator._client
        with (
            patch(
                "custom_components.adjustable_bed.coordinator_bonds.create_pairing_required_issue",
                new_callable=AsyncMock,
            ),
            patch.object(coordinator, "async_disconnect", new_callable=AsyncMock) as disconnect,
            pytest.raises(BleakError),
        ):
            await coordinator.async_execute_controller_command(
                _auth_failure_command,
                cancel_running=False,
            )

        disconnect.assert_not_awaited()
        assert coordinator._client is client

        await coordinator.async_disconnect()

    async def test_runtime_auth_failure_pairs_the_unpaired_link_before_any_repair(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
    ) -> None:
        """An unpaired proxy link to a bonded bed is unencrypted, not unbonded.

        Issue #709: the ESP32 proxy does not raise link security on this reply,
        so pairing the live link with the stored keys fixes it without pairing
        mode. Only a failure on the now-paired link is evidence for the repair.
        """
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        await coordinator.async_connect()
        coordinator._bed_type = BED_TYPE_LEGGETT_GEN2
        client = coordinator._client
        client.pair = AsyncMock()

        async def _encryption_failure_command(_controller):
            raise BleakError(
                "Bluetooth GATT Error address=AA:BB:CC:DD:EE:FF "
                "handle=42 error=15 description=Insufficient encryption"
            )

        with (
            patch(
                "custom_components.adjustable_bed.coordinator_bonds.create_pairing_required_issue",
                new_callable=AsyncMock,
            ) as create_issue,
            patch_coordinator_global(
                "delete_pairing_required_issue",
                new_callable=AsyncMock,
            ) as delete_issue,
        ):
            with pytest.raises(BleakError):
                await coordinator.async_execute_controller_command(
                    _encryption_failure_command, cancel_running=False
                )

            client.pair.assert_awaited_once_with()
            create_issue.assert_not_awaited()
            delete_issue.assert_awaited_once_with(hass, coordinator.address)
            assert coordinator._client is client
            assert coordinator._last_bond_verification["status"] == "encrypted_in_place"

            with pytest.raises(BleakError):
                await coordinator.async_execute_controller_command(
                    _encryption_failure_command, cancel_running=False
                )

        # The link already paired, so the repeat is real evidence.
        client.pair.assert_awaited_once_with()
        create_issue.assert_awaited_once()

        await coordinator.async_disconnect()

    async def test_runtime_auth_failure_raises_the_repair_when_in_place_pairing_fails(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
    ) -> None:
        """A bed that refuses the bond outside its pairing window still gets the repair."""
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        await coordinator.async_connect()
        coordinator._bed_type = BED_TYPE_LEGGETT_GEN2
        client = coordinator._client
        client.pair = AsyncMock(side_effect=BleakError("pairing rejected"))

        async def _encryption_failure_command(_controller):
            raise BleakError(
                "Bluetooth GATT Error address=AA:BB:CC:DD:EE:FF "
                "handle=42 error=15 description=Insufficient encryption"
            )

        with (
            patch(
                "custom_components.adjustable_bed.coordinator_bonds.create_pairing_required_issue",
                new_callable=AsyncMock,
            ) as create_issue,
            patch_coordinator_global(
                "delete_pairing_required_issue",
                new_callable=AsyncMock,
            ) as delete_issue,
            pytest.raises(BleakError),
        ):
            await coordinator.async_execute_controller_command(
                _encryption_failure_command, cancel_running=False
            )

        client.pair.assert_awaited_once_with()
        create_issue.assert_awaited_once()
        delete_issue.assert_not_awaited()
        assert coordinator._client is client

        await coordinator.async_disconnect()

    async def test_connect_does_not_report_success_without_a_controller(
        self,
        hass: HomeAssistant,
        mock_config_entry,
    ) -> None:
        """A retained link with no controller is not a usable connection.

        Keeping the link after a failed startup makes "connected but no
        controller" reachable, so the reuse shortcut must not call it success.
        The orphaned client must also be released rather than leaked:
        establish_connection() would overwrite self._client while the old link
        stayed open, and close_stale_connections_by_address() is None on
        non-BlueZ backends, so nothing else would ever close it.
        """
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        client = MagicMock()
        client.is_connected = True
        client.disconnect = AsyncMock()
        coordinator._client = client
        coordinator._controller = None

        with (
            patch.object(coordinator, "_reset_disconnect_timer") as reset_timer,
            patch(
                "custom_components.adjustable_bed.coordinator_connection.select_adapter",
                new_callable=AsyncMock,
                side_effect=BleakError("stop here"),
            ),
        ):
            # Falls through to a real attempt instead of returning True.
            assert await coordinator._async_connect_locked() is False
        reset_timer.assert_not_called()
        # The half-initialised link was released, not leaked.
        client.disconnect.assert_awaited_once()
        assert coordinator._client is None

    @pytest.mark.parametrize(
        ("error", "expected_status", "says_refused"),
        [
            (
                BleakError("[org.bluez.Error.AuthenticationFailed] Authentication Failed"),
                "advisory_bond_auth_failed",
                True,
            ),
            (BleakError("pairing rejected"), "advisory_bond_failed", False),
        ],
    )
    async def test_an_auth_stage_bond_failure_gets_its_own_advice(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        error: BleakError,
        expected_status: str,
        says_refused: bool,
        caplog,
    ) -> None:
        """A bond that fails to authenticate needs different advice (issue #385).

        The field logs show the bed dropping the link about a second later, so
        the generic message's promise to keep the connection alive is untrue
        here. BlueZ's AuthenticationFailed is generic, so the message offers
        mismatched stored keys as a common cause rather than asserting it.
        """
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        coordinator._bed_type = BED_TYPE_LEGGETT_GEN2

        client = MagicMock()
        client.is_connected = True
        client.pair = AsyncMock(side_effect=error)
        coordinator._client = client

        with patch(
            "custom_components.adjustable_bed.coordinator_bonds.create_pairing_required_issue",
            new_callable=AsyncMock,
        ):
            assert await coordinator._async_pair_on_live_link({}) is False

        assert coordinator._last_bond_verification["status"] == expected_status
        # The link is still ours either way: the bed drops it, we do not.
        assert coordinator._client is client
        if says_refused:
            assert "Could not authenticate the BLE bond" in caplog.text
            assert "One common cause" in caplog.text
            # Does not assume the bond lives on the host: with a proxy it is
            # stored on the proxy instead.
            assert "ESPHome" in caplog.text
        else:
            assert "Keeping the live connection" in caplog.text

    async def test_advisory_bond_failure_raises_the_pairing_repair(
        self,
        hass: HomeAssistant,
        mock_config_entry,
    ) -> None:
        """A failed advisory bond must always leave the user a guided fix.

        The link is kept and controller startup can finish unbonded, and the
        later bond probe only raises the repair on a *definitive* auth error -
        a timeout or non-auth BleakError is treated as inconclusive. Without
        raising it here the bond silently never happens (issue #385).
        """
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        coordinator._bed_type = BED_TYPE_LEGGETT_GEN2

        client = MagicMock()
        client.is_connected = True
        client.pair = AsyncMock(side_effect=BleakError("pairing rejected"))
        coordinator._client = client

        with patch(
            "custom_components.adjustable_bed.coordinator_bonds.create_pairing_required_issue",
            new_callable=AsyncMock,
        ) as create_issue:
            assert await coordinator._async_pair_on_live_link({}) is False

        create_issue.assert_awaited_once()
        # The link is still ours: raising the repair must not cost the bed its
        # single connection.
        assert coordinator._client is client

    @pytest.mark.parametrize(
        ("pair_error", "max_retries", "pairing_supported"),
        [
            (NotImplementedError("pairing unavailable"), 1, False),
            (BleakError("pairing rejected"), 2, True),
        ],
    )
    async def test_leggett_gen2_pair_failure_keeps_the_live_link(
        self,
        hass: HomeAssistant,
        mock_bluetooth_api,
        mock_bleak_client: MagicMock,
        pair_error: Exception,
        max_retries: int,
        pairing_supported: bool,
    ) -> None:
        """A failed Gen2 bond must never cost us the connection (issue #385).

        LP Comfort Connect grants roughly one connection per pairing window, so
        reconnecting after a bond failure strands the bed until it is
        power-cycled. LP Control itself fires ``createBond()`` and continues on
        the same link without ever checking the result.
        """
        del mock_bluetooth_api

        entry = MockConfigEntry(
            domain=DOMAIN,
            title="Unpaired LP Gen2 Bed",
            data={
                CONF_ADDRESS: TEST_ADDRESS,
                CONF_NAME: TEST_NAME,
                CONF_BED_TYPE: BED_TYPE_LEGGETT_GEN2,
                CONF_MOTOR_COUNT: 4,
                CONF_HAS_MASSAGE: True,
                CONF_DISABLE_ANGLE_SENSING: True,
                CONF_PREFERRED_ADAPTER: "auto",
            },
            unique_id=TEST_ADDRESS,
            entry_id="leggett_gen2_pair_fallback_test",
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

        coordinator = AdjustableBedCoordinator(hass, entry)
        intentional_during_disconnect: list[bool] = []

        async def disconnect() -> None:
            intentional_during_disconnect.append(coordinator._intentional_disconnect)
            coordinator._on_disconnect(mock_bleak_client)

        mock_bleak_client.pair = AsyncMock(side_effect=pair_error)
        mock_bleak_client.disconnect = AsyncMock(side_effect=disconnect)
        # With no bond, the post-connect probe hits an unauthenticated link.
        # That must not cost us the connection either.
        mock_bleak_client.read_gatt_char = AsyncMock(
            side_effect=BleakError("Insufficient authentication")
        )

        controller = make_controller_mock()
        controller.requires_persistent_connection = True
        controller.requires_notification_channel = False
        controller.supports_under_bed_lights = False

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
            patch(
                "custom_components.adjustable_bed.coordinator_connection.discover_services",
                new_callable=AsyncMock,
                return_value=True,
            ),
            patch(
                "custom_components.adjustable_bed.coordinator_connection.read_ble_device_info",
                new_callable=AsyncMock,
                return_value=(None, None),
            ),
            patch_coordinator_global(
                "create_controller",
                new_callable=AsyncMock,
                return_value=controller,
            ),
            patch(
                "custom_components.adjustable_bed.coordinator.asyncio.sleep",
                new=AsyncMock(),
            ),
        ):
            coordinator._max_retries = max_retries
            result = await coordinator.async_connect()

        assert result is True
        # One connection, kept: no release, no reconnect.
        assert mock_establish_connection.await_count == 1
        assert mock_establish_connection.await_args_list[0].kwargs["pair"] is False
        mock_bleak_client.pair.assert_awaited_once_with()
        mock_bleak_client.disconnect.assert_not_awaited()
        assert intentional_during_disconnect == []
        assert coordinator._intentional_disconnect is False
        assert coordinator._client is mock_bleak_client

        # The bond did not happen, so nothing may claim it did — and the
        # unauthenticated probe must not have torn the link down either.
        # Assert the probe actually ran: a regression that skipped it would
        # otherwise still satisfy every assertion below.
        mock_bleak_client.read_gatt_char.assert_awaited_with(DEVICE_INFO_CHARS["model_number"])
        assert entry.data.get(CONF_BLE_BOND_ESTABLISHED) is not True
        assert coordinator._client is not None
        assert coordinator._last_disconnect_reason != "authentication_failed"
        assert coordinator._pairing_supported is pairing_supported
        pairing = coordinator.pairing_diagnostics["connection_attempts"][0]["pairing"]
        assert pairing["connection_result"] == "advisory_bond_failed_link_retained"
        assert pairing["adapter_pairing_supported"] is pairing_supported

    async def test_initial_position_read_prepares_controller_before_hydration(
        self,
        hass: HomeAssistant,
        mock_config_entry,
    ) -> None:
        """Startup hydration should run controller-specific preparation first."""
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        coordinator._disable_angle_sensing = False
        coordinator._client = MagicMock()
        coordinator._client.is_connected = True

        controller = MagicMock()
        controller.prepare_for_position_read = AsyncMock()
        controller.position_number_specs = (
            SimpleNamespace(position_key="back"),
            SimpleNamespace(position_key="legs"),
        )
        coordinator._controller = controller

        async def _read_positions() -> None:
            coordinator._position_data["back"] = 0.0
            coordinator._position_data["legs"] = 0.0

        with patch.object(
            coordinator,
            "_async_read_positions",
            new=AsyncMock(side_effect=_read_positions),
        ) as mock_read_positions:
            await coordinator.async_read_initial_positions()

        controller.prepare_for_position_read.assert_awaited_once_with()
        mock_read_positions.assert_awaited_once_with()

    async def test_quick_handoff_does_not_hold_link_for_missing_position_retries(
        self, hass, mock_config_entry,
    ):
        """Unavailable feedback must not turn quick handoff into a 40-second retry hold."""
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        coordinator._disconnect_after_command = True
        coordinator._disable_angle_sensing = False
        coordinator._client = MagicMock(is_connected=True)
        controller = make_controller_mock(
            position_number_specs=(SimpleNamespace(position_key="back"),),
        )
        controller.prepare_for_position_read = AsyncMock()
        controller.read_positions = AsyncMock()
        coordinator._controller = controller

        with patch("custom_components.adjustable_bed.coordinator_positions._INITIAL_POSITION_READ_RETRY_DELAY", 0):
            await coordinator.async_read_initial_positions()

        controller.read_positions.assert_awaited_once()
        assert coordinator._disconnect_timer is not None
        assert coordinator._disconnect_timer.when() - hass.loop.time() == pytest.approx(1, abs=.1)

    async def test_initial_position_read_retries_missing_axes(
        self,
        hass: HomeAssistant,
        mock_config_entry,
    ) -> None:
        """Startup hydration should retry until required axes are populated."""
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        coordinator._disable_angle_sensing = False
        coordinator._client = MagicMock()
        coordinator._client.is_connected = True

        controller = MagicMock()
        controller.prepare_for_position_read = AsyncMock()
        controller.position_number_specs = (
            SimpleNamespace(position_key="back"),
            SimpleNamespace(position_key="legs"),
        )
        coordinator._controller = controller

        read_count = 0

        async def _read_positions() -> None:
            nonlocal read_count
            assert coordinator._command_lock.locked()
            read_count += 1
            coordinator._position_data["legs"] = 9.6
            if read_count >= 2:
                coordinator._position_data["back"] = 0.0

        async def _retry_sleep(_delay: float) -> None:
            assert not coordinator._command_lock.locked()

        with (
            patch.object(
                coordinator,
                "_async_read_positions",
                new=AsyncMock(side_effect=_read_positions),
            ) as mock_read_positions,
            patch.object(coordinator, "_cancel_disconnect_timer") as cancel_timer,
            patch.object(coordinator, "_reset_disconnect_timer") as reset_timer,
            patch(
                "custom_components.adjustable_bed.coordinator.asyncio.sleep",
                new=AsyncMock(side_effect=_retry_sleep),
            ) as mock_sleep,
        ):
            await coordinator.async_read_initial_positions()

        assert mock_read_positions.await_count == 2
        assert controller.prepare_for_position_read.await_count == 2
        assert cancel_timer.call_count >= 1
        assert reset_timer.call_count >= 1
        mock_sleep.assert_awaited_once()

    async def test_initial_position_read_is_preempted_while_waiting_for_command_lock(
        self,
        hass: HomeAssistant,
        mock_config_entry,
    ) -> None:
        """A queued reconnect hydration must yield the lock to STOP."""
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        coordinator._disable_angle_sensing = False
        coordinator._client = MagicMock(is_connected=True)
        controller = MagicMock(position_number_specs=(SimpleNamespace(position_key="back"),))
        controller.prepare_for_position_read = AsyncMock()
        coordinator._controller = controller

        await coordinator._command_lock.acquire()
        hydration = asyncio.create_task(coordinator.async_read_initial_positions())
        await asyncio.sleep(0)
        coordinator.request_command_cancel()
        coordinator._command_lock.release()

        result = await asyncio.gather(hydration, return_exceptions=True)

        assert isinstance(result[0], asyncio.CancelledError)
        controller.prepare_for_position_read.assert_not_awaited()

    async def test_queued_position_read_does_not_reconnect_after_command_refresh(
        self,
        hass: HomeAssistant,
        mock_config_entry,
    ) -> None:
        """Fresh command feedback must cancel hydration queued behind that command."""
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        coordinator._disable_angle_sensing = False
        coordinator._client = MagicMock(is_connected=True)
        coordinator._position_connection_generation = 1
        coordinator._controller = make_controller_mock(
            position_number_specs=(
                SimpleNamespace(position_key="back"),
                SimpleNamespace(position_key="legs"),
            )
        )

        await coordinator._command_lock.acquire()
        with patch.object(
            coordinator,
            "async_ensure_connected",
            new_callable=AsyncMock,
        ) as ensure_connected:
            try:
                hydration = asyncio.create_task(coordinator.async_read_initial_positions())
                await asyncio.sleep(0)

                coordinator._handle_position_update("back", 12.0)
                coordinator._handle_position_update("legs", 4.0)
            finally:
                coordinator._command_lock.release()
            await hydration

        ensure_connected.assert_not_awaited()

    async def test_queued_position_read_does_not_reconnect_after_command_disconnect(
        self,
        hass: HomeAssistant,
        mock_config_entry,
    ) -> None:
        """A command-released link must stay released while hydration is queued."""
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        coordinator._disable_angle_sensing = False
        coordinator._client = MagicMock(is_connected=True)
        coordinator._position_connection_generation = 1
        coordinator._controller = make_controller_mock(
            position_number_specs=(
                SimpleNamespace(position_key="back"),
                SimpleNamespace(position_key="legs"),
            )
        )

        await coordinator._command_lock.acquire()
        with patch.object(
            coordinator,
            "async_ensure_connected",
            new_callable=AsyncMock,
        ) as ensure_connected:
            try:
                hydration = asyncio.create_task(coordinator.async_read_initial_positions())
                await asyncio.sleep(0)
                coordinator._client.is_connected = False
            finally:
                coordinator._command_lock.release()
            await hydration

        ensure_connected.assert_not_awaited()

    async def test_initial_position_read_has_overall_retry_deadline(
        self,
        hass: HomeAssistant,
        mock_config_entry,
    ) -> None:
        """Per-attempt retries must still release a silent single-client bed."""
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        coordinator._disable_angle_sensing = False
        coordinator._client = MagicMock(is_connected=True)
        controller = MagicMock(position_number_specs=(SimpleNamespace(position_key="back"),))
        controller.prepare_for_position_read = AsyncMock()
        coordinator._controller = controller

        with (
            patch(
                "custom_components.adjustable_bed.coordinator_positions._INITIAL_POSITION_READ_TOTAL_TIMEOUT",
                0.01,
            ),
            patch.object(
                coordinator,
                "_async_read_positions",
                new=AsyncMock(side_effect=asyncio.Event().wait),
            ),
        ):
            await coordinator.async_read_initial_positions()

        controller.prepare_for_position_read.assert_awaited_once_with()
        assert coordinator._position_hydration_running is False

    async def test_initial_position_read_survives_a_failed_attempt(
        self,
        hass: HomeAssistant,
        mock_config_entry,
    ) -> None:
        """One slow or failing attempt must not consume the whole retry budget."""
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        coordinator._disable_angle_sensing = False
        coordinator._client = MagicMock()
        coordinator._client.is_connected = True

        controller = MagicMock()
        controller.prepare_for_position_read = AsyncMock()
        controller.position_number_specs = (
            SimpleNamespace(position_key="back"),
            SimpleNamespace(position_key="legs"),
        )
        coordinator._controller = controller

        read_count = 0

        async def _read_positions() -> None:
            nonlocal read_count
            read_count += 1
            if read_count == 1:
                raise TimeoutError
            if read_count == 2:
                raise BleakError("read failed")
            coordinator._position_data["back"] = 12.0
            coordinator._position_data["legs"] = 4.0

        with (
            patch.object(
                coordinator,
                "_async_read_positions",
                new=AsyncMock(side_effect=_read_positions),
            ) as mock_read_positions,
            patch(
                "custom_components.adjustable_bed.coordinator.asyncio.sleep",
                new=AsyncMock(),
            ),
        ):
            await coordinator.async_read_initial_positions()

        assert mock_read_positions.await_count == 3
        assert coordinator.position_data == {"back": 12.0, "legs": 4.0}

    async def test_position_hydration_runs_once_per_connection(
        self,
        hass: HomeAssistant,
        mock_config_entry,
    ) -> None:
        """Each BLE session refreshes axes once without duplicate startup reads."""
        mock_config_entry.add_to_hass(hass)
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        coordinator._disable_angle_sensing = False
        coordinator._position_connection_generation = 1
        coordinator._controller = make_controller_mock(
            position_number_specs=(
                SimpleNamespace(position_key="back"),
                SimpleNamespace(position_key="legs"),
            )
        )

        async def _read_positions() -> None:
            coordinator._handle_position_update("back", 10.0)
            coordinator._handle_position_update("legs", 5.0)

        with patch.object(
            coordinator,
            "async_read_initial_positions",
            new=AsyncMock(side_effect=_read_positions),
        ) as mock_read:
            coordinator._schedule_position_hydration()
            assert coordinator._position_hydration_task is not None
            await coordinator._position_hydration_task
            mock_read.assert_awaited_once()

            # Platform setup asks again after forwarding, but the same session
            # has already hydrated and must not issue a second read.
            coordinator._position_hydration_task = None
            coordinator._schedule_position_hydration()
            assert coordinator._position_hydration_task is None
            assert mock_read.await_count == 1

            # Retained values are stale after reconnect, so the next BLE session
            # must refresh them even though both keys remain populated.
            coordinator._position_connection_generation = 2
            coordinator._schedule_position_hydration()
            reconnect_hydration = cast(
                asyncio.Task[None] | None,
                coordinator._position_hydration_task,
            )
            assert reconnect_hydration is not None
            await reconnect_hydration
            assert mock_read.await_count == 2

    async def test_position_hydration_skipped_when_angle_sensing_disabled(
        self,
        hass: HomeAssistant,
        mock_config_entry,
    ) -> None:
        """Angle sensing off means no background reads at all."""
        mock_config_entry.add_to_hass(hass)
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        coordinator._disable_angle_sensing = True

        coordinator._schedule_position_hydration()

        assert coordinator._position_hydration_task is None

    async def test_position_hydration_skipped_without_position_feedback(
        self,
        hass: HomeAssistant,
        mock_config_entry_data: dict,
    ) -> None:
        """Write-only position sliders must not trigger feedback hydration."""
        mock_config_entry_data[CONF_BED_TYPE] = BED_TYPE_KAIDI
        coordinator = AdjustableBedCoordinator(
            hass,
            MockConfigEntry(
                domain=DOMAIN,
                title=TEST_NAME,
                data=mock_config_entry_data,
                unique_id=TEST_ADDRESS,
                entry_id="write_only_position_hydration",
            ),
        )
        coordinator._disable_angle_sensing = False
        coordinator._controller = make_controller_mock(
            position_number_specs=(
                SimpleNamespace(position_key="back"),
                SimpleNamespace(position_key="legs"),
            )
        )

        coordinator._schedule_position_hydration()

        assert coordinator._position_hydration_task is None

    async def test_position_hydration_stays_paused_until_all_diagnostics_finish(
        self,
        hass: HomeAssistant,
        mock_config_entry,
    ) -> None:
        """Overlapping diagnostics must not resume hydration after the first exit."""
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        coordinator._client = MagicMock()
        coordinator._client.is_connected = True

        with (
            patch.object(
                coordinator,
                "_async_cancel_position_hydration",
                new_callable=AsyncMock,
            ) as cancel_hydration,
            patch.object(coordinator, "_schedule_position_hydration") as schedule_hydration,
        ):
            await coordinator.async_pause_position_hydration()
            await coordinator.async_pause_position_hydration()

            coordinator.resume_position_hydration()
            schedule_hydration.assert_not_called()

            coordinator.resume_position_hydration()

        assert cancel_hydration.await_count == 2
        schedule_hydration.assert_called_once_with()
        assert coordinator._position_hydration_pause_count == 0

    async def test_expected_position_axes_follow_live_controller_specs(
        self,
        hass: HomeAssistant,
        mock_config_entry_data: dict,
    ) -> None:
        """Configured motors do not add axes the live controller cannot report."""
        mock_config_entry_data[CONF_BED_TYPE] = BED_TYPE_SLEEP_NUMBER
        mock_config_entry_data[CONF_MOTOR_COUNT] = 4
        coordinator = AdjustableBedCoordinator(
            hass,
            MockConfigEntry(
                domain=DOMAIN,
                title=TEST_NAME,
                data=mock_config_entry_data,
                unique_id=TEST_ADDRESS,
                entry_id="reportable_position_axes",
            ),
        )
        coordinator._controller = make_controller_mock(
            position_number_specs=(
                SimpleNamespace(position_key="back"),
                SimpleNamespace(position_key="legs"),
            )
        )

        assert coordinator._expected_initial_position_axes() == {"back", "legs"}

    async def test_passive_position_reconciliation_reads_positions_when_idle(
        self,
        hass: HomeAssistant,
        mock_config_entry,
    ) -> None:
        """Passive reconciliation should run a serialized position read."""
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        coordinator._disable_angle_sensing = False
        coordinator._passive_position_reconciliation_interval_s = 120.0

        controller = MagicMock()
        controller.prepare_for_position_read = AsyncMock()
        controller.read_positions = AsyncMock()
        coordinator._controller = controller

        async def _execute_query(query_fn, cancel_running=False, skip_disconnect=False):
            del cancel_running, skip_disconnect
            return await query_fn(controller)

        with patch.object(
            coordinator,
            "async_execute_controller_query",
            new=AsyncMock(side_effect=_execute_query),
        ) as mock_query:
            await coordinator.async_reconcile_positions()

        mock_query.assert_awaited_once()
        controller.prepare_for_position_read.assert_awaited_once_with()
        controller.read_positions.assert_awaited_once_with(coordinator.motor_count)

    async def test_passive_position_reconciliation_skips_when_busy(
        self,
        hass: HomeAssistant,
        mock_config_entry,
    ) -> None:
        """Passive reconciliation should not compete with an active command."""
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        coordinator._disable_angle_sensing = False
        coordinator._passive_position_reconciliation_interval_s = 120.0
        await coordinator._command_lock.acquire()

        try:
            with patch.object(
                coordinator,
                "async_execute_controller_query",
                new=AsyncMock(),
            ) as mock_query:
                await coordinator.async_reconcile_positions()
        finally:
            coordinator._command_lock.release()

        mock_query.assert_not_awaited()

    async def test_passive_position_reconciliation_interval_respects_idle_timeout(
        self,
        hass: HomeAssistant,
        mock_config_entry,
    ) -> None:
        """Passive reconciliation should not fire often enough to pin the BLE session open."""
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        coordinator._disable_angle_sensing = False
        coordinator._idle_disconnect_seconds = 180

        assert coordinator._resolve_passive_position_reconciliation_interval(120.0) == 195.0

    @pytest.mark.parametrize("disconnect_after_command", [True, False])
    @pytest.mark.parametrize("bed_type", [BED_TYPE_LINAK, BED_TYPE_KEESON, BED_TYPE_OCTO])
    async def test_remote_handoff_controls_passive_polling(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        disconnect_after_command: bool,
        bed_type: str,
    ) -> None:
        """Quick handoff must not periodically reclaim the remote's BLE link."""
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        coordinator._bed_type = bed_type
        coordinator._disable_angle_sensing = False
        coordinator._passive_position_reconciliation_enabled = True
        coordinator._disconnect_after_command = disconnect_after_command
        coordinator._idle_disconnect_seconds = 40

        assert coordinator._resolve_passive_position_reconciliation_interval(120.0) == (
            None if disconnect_after_command else 120.0
        )

    async def test_passive_position_reconciliation_can_be_disabled_by_config(
        self,
        hass: HomeAssistant,
        mock_config_entry,
    ) -> None:
        """Explicit config should disable passive reconciliation even for Linak."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            title=mock_config_entry.title,
            data={
                **mock_config_entry.data,
                CONF_PASSIVE_POSITION_RECONCILIATION: False,
            },
            unique_id=mock_config_entry.unique_id,
            entry_id="linak_reconciliation_disabled",
        )
        coordinator = AdjustableBedCoordinator(hass, entry)
        coordinator._disable_angle_sensing = False

        assert coordinator._resolve_passive_position_reconciliation_interval(120.0) is None

    async def test_async_shutdown_cancels_passive_position_reconciliation(
        self,
        hass: HomeAssistant,
        mock_config_entry,
    ) -> None:
        """Coordinator shutdown should cancel passive reconciliation and disconnect cleanly."""
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        task = MagicMock()
        coordinator._passive_position_reconciliation_task = task

        with patch.object(coordinator, "async_disconnect", new=AsyncMock()) as mock_disconnect:
            await coordinator.async_shutdown()

        task.cancel.assert_called_once_with()
        assert coordinator._passive_position_reconciliation_task is None
        mock_disconnect.assert_awaited_once_with()

    async def test_async_shutdown_awaits_position_hydration_before_disconnect(
        self,
        hass: HomeAssistant,
        mock_config_entry,
    ) -> None:
        """Shutdown must stop an in-flight GATT hydration before disconnecting."""
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        hydration_started = asyncio.Event()

        async def _hydrate() -> None:
            hydration_started.set()
            await asyncio.Event().wait()

        task = hass.async_create_task(_hydrate())
        coordinator._position_hydration_task = task
        await hydration_started.wait()

        async def _disconnect() -> None:
            assert task.done()

        with patch.object(
            coordinator,
            "async_disconnect",
            new=AsyncMock(side_effect=_disconnect),
        ) as mock_disconnect:
            await coordinator.async_shutdown()

        assert task.cancelled()
        assert coordinator._position_hydration_task is None
        mock_disconnect.assert_awaited_once_with()

    async def test_async_shutdown_cancellation_finishes_cleanup(
        self,
        hass: HomeAssistant,
        mock_config_entry,
    ) -> None:
        """Caller cancellation must not strand hydration or skip shutdown cleanup."""
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        hydration_started = asyncio.Event()
        hydration_cancelled = asyncio.Event()

        async def _hydrate() -> None:
            hydration_started.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                hydration_cancelled.set()
                await asyncio.Event().wait()

        hydration_task = hass.async_create_task(_hydrate())
        coordinator._position_hydration_task = hydration_task
        passive_task = MagicMock()
        coordinator._passive_position_reconciliation_task = passive_task
        await hydration_started.wait()

        with patch.object(
            coordinator,
            "async_disconnect",
            new=AsyncMock(),
        ) as mock_disconnect:
            shutdown_task = hass.async_create_task(coordinator.async_shutdown())
            await hydration_cancelled.wait()
            shutdown_task.cancel()

            with pytest.raises(asyncio.CancelledError):
                await shutdown_task

        assert hydration_task.cancelled()
        assert coordinator._position_hydration_task is None
        passive_task.cancel.assert_called_once_with()
        assert coordinator._passive_position_reconciliation_task is None
        mock_disconnect.assert_awaited_once_with()


class TestCoordinatorDisconnectTimer:
    """Test coordinator idle disconnect timer."""

    async def test_disconnect_timer_set_on_connect(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
    ):
        """Test disconnect timer is set after connection."""
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        await coordinator.async_connect()

        assert coordinator._disconnect_timer is not None

    async def test_disconnect_timer_cancelled_on_disconnect(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test disconnect timer is cancelled on disconnect."""
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        await coordinator.async_connect()
        await coordinator.async_disconnect()

        assert coordinator._disconnect_timer is None

    async def test_disconnect_clears_intentional_disconnect_after_cleanup(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Manual disconnect should skip reconnect but not leave the flag latched."""
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        await coordinator.async_connect()

        async def _disconnect() -> None:
            coordinator._on_disconnect(mock_bleak_client)

        mock_bleak_client.disconnect.side_effect = _disconnect

        await coordinator.async_disconnect()

        assert coordinator._reconnect_timer is None
        assert coordinator._intentional_disconnect is False

    async def test_disconnect_error_with_live_link_is_reported_and_retained(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """A swallowed Bleak error cannot masquerade as a released link."""
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        await coordinator.async_connect()
        controller = coordinator.controller
        mock_bleak_client.is_connected = True
        mock_bleak_client.disconnect.side_effect = BleakError("link still active")

        disconnected = await coordinator.async_disconnect("sequential_switch")

        assert disconnected is False
        assert coordinator._client is mock_bleak_client
        assert coordinator.controller is controller
        assert coordinator.is_connected is True

        # Leave the shared fixture clean for teardown.
        mock_bleak_client.disconnect.side_effect = None
        mock_bleak_client.is_connected = False

    async def test_disconnect_return_with_live_link_is_reported_and_retained(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """A successful Bleak return cannot hide a physical link still in use."""
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        await coordinator.async_connect()
        controller = coordinator.controller
        mock_bleak_client.is_connected = True
        mock_bleak_client.disconnect = AsyncMock()

        disconnected = await coordinator.async_disconnect("sequential_switch")

        assert disconnected is False
        assert coordinator._client is mock_bleak_client
        assert coordinator.controller is controller
        assert coordinator.is_connected is True

        # Leave the shared fixture clean for teardown.
        mock_bleak_client.is_connected = False

    async def test_failed_connection_cleanup_is_intentional(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_bleak_client: MagicMock,
    ) -> None:
        """Failure cleanup must not let the callback schedule auto-reconnect."""
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        coordinator._client = mock_bleak_client
        coordinator._controller = MagicMock()
        intentional_during_disconnect: list[bool] = []

        async def disconnect() -> None:
            intentional_during_disconnect.append(coordinator._intentional_disconnect)
            coordinator._on_disconnect(mock_bleak_client)

        mock_bleak_client.disconnect = AsyncMock(side_effect=disconnect)

        await coordinator._async_cleanup_failed_connection()

        assert intentional_during_disconnect == [True]
        assert coordinator._client is None
        assert coordinator._controller is None
        assert coordinator._reconnect_timer is None
        assert coordinator._intentional_disconnect is False

    async def test_sleep_number_mcr_skips_disconnect_timer_on_connect(
        self,
        hass: HomeAssistant,
        mock_coordinator_connected,
    ):
        """Sleep Number MCR should keep a persistent connection without an idle timer."""
        del mock_coordinator_connected
        entry = MockConfigEntry(
            domain=DOMAIN,
            title="Sleep Number MCR Bed",
            data={
                CONF_ADDRESS: "AA:BB:CC:DD:EE:51",
                CONF_NAME: "64:DB:A0:07:DD:02",
                CONF_BED_TYPE: BED_TYPE_SLEEP_NUMBER_MCR,
                CONF_MOTOR_COUNT: 2,
                CONF_HAS_MASSAGE: False,
                CONF_DISABLE_ANGLE_SENSING: True,
                CONF_PREFERRED_ADAPTER: "auto",
            },
            unique_id="AA:BB:CC:DD:EE:51",
            entry_id="sleep_number_mcr_disconnect_timer_test",
        )
        entry.add_to_hass(hass)

        coordinator = AdjustableBedCoordinator(hass, entry)
        await coordinator.async_connect()

        assert coordinator._disconnect_timer is None


class TestDisconnectCommandSerialization:
    """Externally triggered disconnects must not interleave with a command.

    Issue #368: pressing Disconnect while a connect was in flight queued the
    teardown on the connection lock only. It then fired in the same tick that the
    command which triggered the reconnect issued its first GATT write, and the
    command failed with a user-visible error.
    """

    async def test_disconnect_button_waits_for_running_command(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
    ):
        """A serialized disconnect must not tear the link down mid-command."""
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        await coordinator.async_connect()

        command_running = asyncio.Event()
        release_command = asyncio.Event()
        disconnected_during_command = False

        async def _slow_command(_controller):
            nonlocal disconnected_during_command
            command_running.set()
            await release_command.wait()
            disconnected_during_command = coordinator._client is None

        command = asyncio.create_task(
            coordinator.async_execute_controller_command(_slow_command, cancel_running=False)
        )
        await command_running.wait()

        disconnect = asyncio.create_task(coordinator.async_disconnect(serialize_with_commands=True))
        # Give the disconnect a chance to run if it were going to ignore the lock.
        await asyncio.sleep(0)
        assert not disconnect.done()

        release_command.set()
        await command
        await disconnect

        assert disconnected_during_command is False
        assert coordinator._client is None

    async def test_disconnect_invalidates_queued_and_teardown_race_commands(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
    ):
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        await coordinator.async_connect()
        active_started = asyncio.Event()
        active_cancelled = asyncio.Event()
        release_cleanup = asyncio.Event()
        queued_ran = False
        teardown_race_ran = False

        async def active(_controller):
            context = current_command_context()
            assert context is not None
            active_started.set()
            await context.cancel_event.wait()
            active_cancelled.set()
            await release_cleanup.wait()

        async def queued(_controller):
            nonlocal queued_ran
            queued_ran = True

        async def teardown_race(_controller):
            nonlocal teardown_race_ran
            teardown_race_ran = True

        active_task = asyncio.create_task(coordinator.async_execute_controller_command(active))
        await active_started.wait()
        queued_task = asyncio.create_task(
            coordinator.async_execute_controller_command(
                queued,
                cancel_running=False,
                resource="motor:legs",
            )
        )
        while not coordinator._command_scheduler.has_pending:
            await asyncio.sleep(0)

        disconnect_task = asyncio.create_task(
            coordinator.async_disconnect(serialize_with_commands=True)
        )
        await active_cancelled.wait()
        teardown_race_task = asyncio.create_task(
            coordinator.async_execute_controller_command(
                teardown_race,
                cancel_running=False,
            )
        )
        release_cleanup.set()

        await asyncio.gather(
            active_task,
            queued_task,
            teardown_race_task,
            disconnect_task,
        )
        assert not queued_ran
        assert not teardown_race_ran
        assert coordinator._client is None

    async def test_idle_disconnect_skipped_when_timer_rearmed(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
    ):
        """A stale idle firing must not disconnect a bed a command just used."""
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        await coordinator.async_connect()

        # The fired handle is cleared when the timer callback runs; that is what
        # lets _async_idle_disconnect tell "re-armed" from "already fired". Drop
        # the pending handle first so the loop cannot also run it for real.
        assert coordinator._disconnect_timer is not None
        coordinator._disconnect_timer.cancel()
        with patch.object(
            coordinator.entry,
            "async_create_background_task",
            side_effect=lambda _hass, coro, **_kwargs: coro.close(),
        ):
            coordinator._schedule_idle_disconnect()
        assert coordinator._disconnect_timer is None

        async with coordinator._command_lock:
            idle = asyncio.create_task(coordinator._async_idle_disconnect())
            await asyncio.sleep(0)
            coordinator._reset_disconnect_timer()

        await idle

        assert coordinator._disconnect_timer is not None
        assert coordinator._client is not None

        await coordinator.async_disconnect()

    async def test_idle_disconnect_skipped_during_position_hydration(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
    ):
        """Hydration owns the connection across all attempts and retry backoffs."""
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        await coordinator.async_connect()
        coordinator._position_hydration_running = True

        with patch.object(
            coordinator,
            "_async_disconnect_locked",
            new_callable=AsyncMock,
        ) as disconnect:
            await coordinator._async_idle_disconnect()

        disconnect.assert_not_awaited()
        assert coordinator._client is not None

        coordinator._position_hydration_running = False
        await coordinator.async_disconnect()
