"""Tests for the coordinator's BLE bond and pairing state."""

from __future__ import annotations

from typing import Any
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
from custom_components.adjustable_bed.bond_verification import BondVerificationStatus
from custom_components.adjustable_bed.const import (
    BED_TYPE_LEGGETT_GEN2,
    BED_TYPE_LEGGETT_OKIN,
    BED_TYPE_SLEEP_NUMBER,
    BED_TYPE_VIBRADORM_APP,
    CONF_BED_TYPE,
    CONF_BLE_BOND_ATTEMPTED_SOURCE,
    CONF_BLE_BOND_CONTEXT,
    CONF_BLE_BOND_ESTABLISHED,
    CONF_BLE_BOND_MARKER_UNRELIABLE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_HAS_MASSAGE,
    CONF_MOTOR_COUNT,
    CONF_PREFERRED_ADAPTER,
    DOMAIN,
)
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.coordinator_bonds import BOND_LATCH_RETEST_AFTER
from tests.coordinator_patches import patch_coordinator_global

from .conftest import TEST_ADDRESS, TEST_NAME, make_controller_mock


class TestBondMarkerReliability:
    """A bond marker that does not survive must stop suppressing pairing.

    Issue #368: the persisted marker made attempt 1 connect without pair=True,
    the auth-gated probe then failed with GATT error 5, the marker was cleared,
    the retry paired successfully and re-armed the marker. Every single connect
    therefore burned one guaranteed-failed attempt plus its backoff.
    """

    def _make_bonded_coordinator(
        self, hass: HomeAssistant, **extra_data: object
    ) -> AdjustableBedCoordinator:
        entry = MockConfigEntry(
            domain=DOMAIN,
            title=TEST_NAME,
            data={
                CONF_ADDRESS: TEST_ADDRESS,
                CONF_NAME: TEST_NAME,
                CONF_BED_TYPE: BED_TYPE_LEGGETT_OKIN,
                CONF_MOTOR_COUNT: 2,
                CONF_HAS_MASSAGE: False,
                CONF_DISABLE_ANGLE_SENSING: True,
                CONF_PREFERRED_ADAPTER: "auto",
                CONF_BLE_BOND_ESTABLISHED: True,
                **extra_data,
            },
            unique_id=TEST_ADDRESS,
            entry_id="bond_marker_reliability_test",
        )
        entry.add_to_hass(hass)
        return AdjustableBedCoordinator(hass, entry)

    async def test_auth_failure_on_trusted_marker_latches_pairing(
        self,
        hass: HomeAssistant,
    ):
        """After the marker is disproven, every later attempt must request pairing."""
        coordinator = self._make_bonded_coordinator(hass)
        device = MagicMock()
        device.details = {}

        _, use_pairing, _ = coordinator._prepare_pairing_attempt(device, {})
        assert use_pairing is False
        assert coordinator._attempt_trusted_bond_marker is True

        with patch(
            "custom_components.adjustable_bed.coordinator_bonds.create_pairing_required_issue",
            new_callable=AsyncMock,
        ):
            await coordinator._async_handle_ble_authentication_error(
                BleakError(
                    "Bluetooth GATT Error address=AA:BB:CC:DD:EE:FF "
                    "handle=26 error=5 description=Insufficient authentication"
                )
            )

        assert coordinator._ble_bond_marker_unreliable is True
        assert coordinator.entry.data[CONF_BLE_BOND_MARKER_UNRELIABLE] is True
        assert coordinator._ble_bond_established is False

        # A later successful probe must not re-arm the marker...
        coordinator._mark_ble_bond_established()
        assert coordinator._ble_bond_established is False

        # ...so the next attempt pairs instead of repeating the failed one.
        pairing_details: dict[str, Any] = {}
        _, use_pairing, _ = coordinator._prepare_pairing_attempt(device, pairing_details)
        assert use_pairing is True
        assert pairing_details["decision"] == "bond_marker_unreliable"

    async def test_latch_releases_once_a_bond_survives_without_pairing(
        self,
        hass: HomeAssistant,
    ):
        """The latch must be self-correcting, not permanent.

        A backend that rejects re-pairing an existing bond fails the paired
        attempt, falls back via _skip_pair_next_attempt, and connects unpaired.
        If that unpaired connection verifies as bonded, the bond clearly does
        survive here, so keeping the latch would alternate a failed paired
        attempt with a successful unpaired one on every single connect.
        """
        coordinator = self._make_bonded_coordinator(
            hass,
            **{CONF_BLE_BOND_MARKER_UNRELIABLE: True, CONF_BLE_BOND_ESTABLISHED: False},
        )
        assert coordinator._ble_bond_marker_unreliable is True
        client = MagicMock()
        client.is_connected = True
        client.read_gatt_char = AsyncMock(return_value=b"CU170")
        coordinator._client = client

        # The fallback attempt connects without requesting pairing...
        coordinator._attempt_used_pairing = False

        with (
            patch_coordinator_global(
                "delete_pairing_required_issue",
                new_callable=AsyncMock,
            ),
            patch.object(
                hass.config_entries,
                "async_update_entry",
                wraps=hass.config_entries.async_update_entry,
            ) as update_entry,
        ):
            assert await coordinator._async_verify_bonded() is True

        # ...and the probe succeeding releases the latch and re-arms the marker.
        assert coordinator._ble_bond_marker_unreliable is False
        assert CONF_BLE_BOND_MARKER_UNRELIABLE not in coordinator.entry.data
        assert coordinator._ble_bond_established is True
        # Both flags move in a single write: every entry update reloads the
        # integration, so two writes would queue two reloads mid-connect.
        assert update_entry.call_count == 1

    async def test_unpaired_compatibility_fallback_reports_itself_as_unpaired(
        self,
        hass: HomeAssistant,
        mock_bluetooth_api,
        mock_bleak_client: MagicMock,
    ):
        """An adapter without pair= support must not look like a paired connect.

        ESPHome < 2024.3.0 raises NotImplementedError, and the coordinator
        retries the same attempt as a plain unpaired connection. If the flag
        kept its planned value the bond probe would judge that link as paired,
        and the unreliable-marker latch could never release on such an adapter.
        """
        del mock_bluetooth_api
        coordinator = self._make_bonded_coordinator(
            hass,
            **{CONF_BLE_BOND_MARKER_UNRELIABLE: True, CONF_BLE_BOND_ESTABLISHED: False},
        )

        adapter_result = MagicMock()
        adapter_result.device = MagicMock()
        adapter_result.device.address = TEST_ADDRESS
        adapter_result.device.name = TEST_NAME
        adapter_result.device.details = {"source": "local"}
        adapter_result.source = "local"
        adapter_result.rssi = -60
        adapter_result.connectable = True
        adapter_result.available_sources = ["local"]

        calls: list[bool] = []

        async def _establish(*_args, **kwargs):
            paired = bool(kwargs.get("pair"))
            calls.append(paired)
            if paired:
                raise NotImplementedError("pairing not supported")
            return mock_bleak_client

        with (
            patch(
                "custom_components.adjustable_bed.coordinator_connection.select_adapter",
                new_callable=AsyncMock,
                return_value=adapter_result,
            ),
            patch(
                "custom_components.adjustable_bed.coordinator_connection.establish_connection",
                side_effect=_establish,
            ),
            patch_coordinator_global(
                "create_controller",
                new_callable=AsyncMock,
                return_value=make_controller_mock(),
            ),
            patch.object(
                AdjustableBedCoordinator,
                "_async_verify_bonded",
                new_callable=AsyncMock,
                return_value=True,
            ),
        ):
            assert await coordinator.async_connect() is True

        # The paired attempt was tried and fell back to an unpaired one...
        assert calls == [True, False]
        # ...so the probe must see this connection as unpaired.
        assert coordinator._attempt_used_pairing is False

        await coordinator.async_disconnect()

    async def test_latch_is_retested_after_repeated_paired_successes(
        self,
        hass: HomeAssistant,
    ):
        """A pairing-capable backend must not stay latched forever.

        While latched every attempt pairs, so the "bond survived an unpaired
        connect" release can only fire where pairing itself failed. Without a
        periodic retest, a bed moved to an adapter that now keeps bonds would be
        re-paired on every reconnect for good.
        """
        coordinator = self._make_bonded_coordinator(
            hass,
            **{CONF_BLE_BOND_MARKER_UNRELIABLE: True, CONF_BLE_BOND_ESTABLISHED: False},
        )
        client = MagicMock()
        client.is_connected = True
        client.read_gatt_char = AsyncMock(return_value=b"CU170")
        coordinator._client = client
        coordinator._attempt_used_pairing = True

        with patch_coordinator_global(
            "delete_pairing_required_issue",
            new_callable=AsyncMock,
        ):
            for _ in range(BOND_LATCH_RETEST_AFTER - 1):
                assert await coordinator._async_verify_bonded() is True
                assert coordinator._ble_bond_marker_unreliable is True

            # The last one drops the latch so the next connect tries unpaired.
            assert await coordinator._async_verify_bonded() is True

        assert coordinator._ble_bond_marker_unreliable is False
        assert coordinator._ble_bond_established is True
        assert coordinator._latched_pairing_successes == 0

    async def test_stale_os_reported_bond_latches_like_a_stale_marker(
        self,
        hass: HomeAssistant,
    ):
        """Skipping pairing on a stale OS bond must latch, or retries never pair.

        The backend can report a bond that the bed no longer honours. That skip
        is the same unfounded trust as a stale cached marker, so an auth failure
        after it has to latch; otherwise every retry believes the same stale
        report and the bed never actually pairs.
        """
        coordinator = self._make_bonded_coordinator(hass, **{CONF_BLE_BOND_ESTABLISHED: False})
        device = MagicMock()
        device.details = {}
        pairing_details: dict[str, Any] = {}

        with patch.object(coordinator, "_device_reports_existing_bond", return_value=True):
            _, use_pairing, _ = coordinator._prepare_pairing_attempt(device, pairing_details)

        assert use_pairing is False
        assert pairing_details["decision"] == "existing_os_bond_detected"
        assert coordinator._attempt_trusted_bond_marker is True

        with patch(
            "custom_components.adjustable_bed.coordinator_bonds.create_pairing_required_issue",
            new_callable=AsyncMock,
        ):
            await coordinator._async_handle_ble_authentication_error(
                BleakError("handle=26 error=5 description=Insufficient authentication")
            )

        assert coordinator._ble_bond_marker_unreliable is True

        # The stale OS report can no longer suppress pairing on the retry.
        with patch.object(coordinator, "_device_reports_existing_bond", return_value=True):
            _, use_pairing, _ = coordinator._prepare_pairing_attempt(device, {})
        assert use_pairing is True

    async def test_latch_holds_while_only_paired_connections_succeed(
        self,
        hass: HomeAssistant,
    ):
        """A bond verified on a paired attempt says nothing about skipping pairing."""
        coordinator = self._make_bonded_coordinator(
            hass,
            **{CONF_BLE_BOND_MARKER_UNRELIABLE: True, CONF_BLE_BOND_ESTABLISHED: False},
        )
        client = MagicMock()
        client.is_connected = True
        client.read_gatt_char = AsyncMock(return_value=b"CU170")
        coordinator._client = client
        coordinator._attempt_used_pairing = True

        with patch_coordinator_global(
            "delete_pairing_required_issue",
            new_callable=AsyncMock,
        ):
            assert await coordinator._async_verify_bonded() is True

        assert coordinator._ble_bond_marker_unreliable is True
        assert coordinator._ble_bond_established is False

    async def test_auth_failure_while_pairing_keeps_marker_trusted(
        self,
        hass: HomeAssistant,
    ):
        """An auth failure on an attempt that did pair says nothing about the marker."""
        coordinator = self._make_bonded_coordinator(hass)
        coordinator._ble_bond_established = False
        device = MagicMock()
        device.details = {}

        _, use_pairing, _ = coordinator._prepare_pairing_attempt(device, {})
        assert use_pairing is True
        assert coordinator._attempt_trusted_bond_marker is False

        with patch(
            "custom_components.adjustable_bed.coordinator_bonds.create_pairing_required_issue",
            new_callable=AsyncMock,
        ):
            await coordinator._async_handle_ble_authentication_error(
                BleakError("handle=26 error=5 description=Insufficient authentication")
            )

        assert coordinator._ble_bond_marker_unreliable is False
        coordinator._mark_ble_bond_established()
        assert coordinator._ble_bond_established is True

    def _esphome_link(self, coordinator: AdjustableBedCoordinator, calls: list[str]) -> MagicMock:
        client = MagicMock()
        client.is_connected = True
        client.clear_cache = AsyncMock(side_effect=lambda: calls.append("clear") or True)
        coordinator._client = client
        coordinator._connection_path = ConnectionPath(
            source="B0:CB:D8:03:7D:9E",
            transport=TransportClass.PROXY,
            source_domain="esphome",
        )
        return client

    async def test_stale_proxy_cache_gets_one_retry_before_repairing(
        self,
        hass: HomeAssistant,
    ):
        """Issue #660: rediscover handles first, re-pair only if that also fails."""
        coordinator = self._make_bonded_coordinator(hass)
        calls: list[str] = []
        self._esphome_link(coordinator, calls)
        error = BleakError("handle=23 error=15 description=Insufficient encryption")

        async def disconnect(*, reason: str) -> None:
            calls.append("disconnect")

        with (
            patch(
                "custom_components.adjustable_bed.coordinator_bonds.create_pairing_required_issue",
                new_callable=AsyncMock,
            ) as issue,
            patch.object(coordinator, "async_disconnect", side_effect=disconnect),
        ):
            await coordinator._async_handle_ble_authentication_error(error)

            assert calls == ["clear", "disconnect"]
            assert coordinator._last_bond_evidence is not None
            assert coordinator._last_bond_evidence.gatt_cache_cleared is True
            assert coordinator._ble_bond_established is True
            assert coordinator._skip_pair_next_attempt is True
            issue.assert_not_awaited()

            self._esphome_link(coordinator, calls)
            await coordinator._async_handle_ble_authentication_error(error)

            assert coordinator._ble_bond_established is False
            issue.assert_awaited_once()

    async def test_stale_cache_retry_is_spent_per_proxy(
        self,
        hass: HomeAssistant,
    ):
        """A reroute to another proxy is that proxy's first stale cache, not a repeat."""
        coordinator = self._make_bonded_coordinator(hass)
        calls: list[str] = []
        error = BleakError("error=15 description=Insufficient encryption")

        with (
            patch(
                "custom_components.adjustable_bed.coordinator_bonds.create_pairing_required_issue",
                new_callable=AsyncMock,
            ) as issue,
            patch.object(coordinator, "async_disconnect", new=AsyncMock()),
        ):
            self._esphome_link(coordinator, calls)
            await coordinator._async_handle_ble_authentication_error(error)
            self._esphome_link(coordinator, calls)
            coordinator._connection_path = ConnectionPath(
                source="B0:CB:D8:03:81:2A",
                transport=TransportClass.PROXY,
                source_domain="esphome",
            )
            await coordinator._async_handle_ble_authentication_error(error)

        assert coordinator._ble_bond_established is True
        issue.assert_not_awaited()

    async def test_retained_link_keeps_its_discovered_services(
        self,
        hass: HomeAssistant,
    ):
        """A one-connection bed runs startup on the retained link's services."""
        coordinator = self._make_bonded_coordinator(hass)
        calls: list[str] = []
        client = self._esphome_link(coordinator, calls)

        with (
            patch(
                "custom_components.adjustable_bed.coordinator_bonds.create_pairing_required_issue",
                new_callable=AsyncMock,
            ),
            patch_coordinator_global(
                "grants_one_connection_per_pairing_window",
                return_value=True,
            ),
        ):
            await coordinator._async_handle_ble_authentication_error(
                BleakError("error=15 description=Insufficient encryption"),
                retain_link=True,
            )

        client.clear_cache.assert_not_awaited()
        assert coordinator._last_bond_evidence is not None
        assert coordinator._last_bond_evidence.gatt_cache_cleared is False


class TestBondProvenanceAndTransportGate:
    """Who owns a bond, and holding the bed still while it is changed."""

    async def test_the_transport_gate_holds_the_address_lock(
        self, hass: HomeAssistant, mock_config_entry
    ) -> None:
        """A config or repair flow must not connect during a bond removal.

        Excluding the coordinator's own commands is not enough: the per-address
        connect lock is what stops another flow opening a link to the same bed
        while its bond is being removed.
        """
        from custom_components.adjustable_bed.address_lock import async_get_connect_lock
        from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator

        mock_config_entry.add_to_hass(hass)
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        lock = async_get_connect_lock(hass, coordinator._address)

        async with coordinator.async_transport_operation("unpair"):
            assert lock.locked()
        assert not lock.locked()

        await coordinator.async_shutdown()

    async def test_the_transport_gate_accepts_a_successful_fallback_disconnect(
        self, hass: HomeAssistant, mock_config_entry
    ) -> None:
        """A second disconnect that closes the client releases the operation."""
        from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator

        mock_config_entry.add_to_hass(hass)
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        client = MagicMock()
        client.is_connected = True

        async def disconnect() -> None:
            if client.disconnect.await_count == 2:
                client.is_connected = False

        client.disconnect = AsyncMock(side_effect=disconnect)
        coordinator._client = client

        async with coordinator.async_transport_operation("unpair"):
            pass

        assert client.disconnect.await_count == 2
        await coordinator.async_shutdown()

    async def test_the_gates_fallback_close_does_not_arm_a_reconnect(
        self, hass: HomeAssistant, mock_config_entry
    ) -> None:
        """A reconnect queued here would recreate the bond being removed.

        The teardown clears the intentional-disconnect flag on its way out, so
        without this the fallback close reads as an unexpected drop, and the
        five-second timer fires once the gate has released its locks.
        """
        from bleak.exc import BleakError

        from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator

        mock_config_entry.add_to_hass(hass)
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        client = MagicMock()
        client.is_connected = True

        async def disconnect() -> None:
            if client.disconnect.await_count == 1:
                # Bleak raised, but the OS link is still up.
                raise BleakError("still connected")
            client.is_connected = False
            # Backends report the drop through the callback.
            coordinator._on_disconnect(client)

        client.disconnect = AsyncMock(side_effect=disconnect)
        coordinator._client = client

        async with coordinator.async_transport_operation("unpair"):
            assert coordinator._reconnect_timer is None

        assert coordinator._reconnect_timer is None

        await coordinator.async_shutdown()

    async def test_the_transport_gate_closes_the_link_after_an_unexpected_error(
        self, hass: HomeAssistant, mock_config_entry
    ) -> None:
        """An aborted gate must not leave the bed's connection occupied.

        Only BleakError counts as a failed teardown, so anything else unwinds
        straight past the fallback close.
        """
        from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator

        mock_config_entry.add_to_hass(hass)
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        client = MagicMock()
        client.is_connected = True

        async def disconnect() -> None:
            if client.disconnect.await_count == 1:
                raise OSError("backend went away")
            client.is_connected = False

        client.disconnect = AsyncMock(side_effect=disconnect)
        coordinator._client = client

        with pytest.raises(OSError):
            async with coordinator.async_transport_operation("unpair"):
                pytest.fail("the gate must not hand over an occupied bed")

        assert client.disconnect.await_count == 2
        assert client.is_connected is False

        await coordinator.async_shutdown()

    async def test_an_authenticated_read_records_who_owns_the_bond(
        self, hass: HomeAssistant, mock_config_entry
    ) -> None:
        """A successful auth-gated read is the runtime proof of a bond."""
        from custom_components.adjustable_bed.bluetooth_transport import (
            ConnectionPath,
            TransportClass,
        )
        from custom_components.adjustable_bed.bond_verification import (
            CONF_BLE_BOND_CONTEXT,
        )
        from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator

        mock_config_entry.add_to_hass(hass)
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        coordinator._connection_path = ConnectionPath(
            source="AA:BB:CC:11:22:33",
            transport=TransportClass.LOCAL,
            adapter="hci0",
        )
        coordinator._record_bond_provenance()
        await hass.async_block_till_done()

        context = mock_config_entry.data.get(CONF_BLE_BOND_CONTEXT)
        assert context is not None
        assert context["transport"] == "local"
        assert context["source"] == "AA:BB:CC:11:22:33"

        await coordinator.async_shutdown()

    async def test_a_proven_bond_stays_available_as_evidence(
        self, hass: HomeAssistant, mock_config_entry
    ) -> None:
        """A repair asks what the last read proved before keeping provenance.

        Provenance is skipped when the owner has not changed, so the evidence
        has to survive that too - otherwise a correctly re-verified bond reads
        as "nothing was established" and its owner is deleted.
        """
        from custom_components.adjustable_bed.bluetooth_transport import (
            ConnectionPath,
            TransportClass,
        )
        from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator

        mock_config_entry.add_to_hass(hass)
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        coordinator._connection_path = ConnectionPath(
            source="AA:BB:CC:11:22:33",
            transport=TransportClass.LOCAL,
            adapter="hci0",
        )
        coordinator._record_bond_provenance()
        await hass.async_block_till_done()

        # Again, with the owner already stored: this writes nothing.
        coordinator._last_bond_evidence = None
        coordinator._record_bond_provenance()
        await hass.async_block_till_done()

        evidence = coordinator.last_bond_evidence
        assert evidence is not None
        assert evidence.proves_bond
        assert evidence.owner.source == "AA:BB:CC:11:22:33"
        assert coordinator.pairing_diagnostics["recovery_action"] is None

        await coordinator.async_shutdown()

    async def test_a_claimed_repair_write_is_not_seen_as_an_options_change(
        self, hass: HomeAssistant, mock_config_entry
    ) -> None:
        """The claim is what stops the update listener reloading the entry."""
        from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator

        mock_config_entry.add_to_hass(hass)
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        hass.data.setdefault(DOMAIN, {})[mock_config_entry.entry_id] = coordinator
        try:
            coordinator.begin_internal_bond_update(True)
            hass.config_entries.async_update_entry(
                mock_config_entry,
                data={**mock_config_entry.data, CONF_BLE_BOND_ESTABLISHED: True},
            )
            assert coordinator.consume_internal_entry_update(mock_config_entry) is True
        finally:
            hass.data[DOMAIN].pop(mock_config_entry.entry_id, None)

        await coordinator.async_shutdown()

    async def test_a_repair_pairing_discards_the_previous_bonds_evidence(
        self, hass: HomeAssistant, mock_config_entry
    ) -> None:
        """A repair persists the owner this attempt proved, so it must be fresh.

        Pairing a live link reports success straight after client.pair(), with
        no new authenticated read, so evidence left by the previous bond would
        be persisted as provenance for its replacement.
        """
        from custom_components.adjustable_bed.bluetooth_transport import TransportClass
        from custom_components.adjustable_bed.bond_verification import (
            BondEvidence,
            BondOwner,
            BondVerificationStatus,
        )
        from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator

        mock_config_entry.add_to_hass(hass)
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        coordinator._last_bond_evidence = BondEvidence(
            status=BondVerificationStatus.VERIFIED,
            owner=BondOwner(transport=TransportClass.LOCAL, source="old-adapter", adapter="hci9"),
            operation="runtime_authenticated_read",
            observed_at="2026-07-01T00:00:00+00:00",
        )
        client = MagicMock()
        client.is_connected = True
        client.pair = AsyncMock(return_value=True)
        client.disconnect = AsyncMock()
        coordinator._client = client

        assert await coordinator.async_pair_now() is True

        # Pairing succeeded but nothing proved who owns the new bond.
        assert coordinator.last_bond_evidence is None

        await coordinator.async_shutdown()

    async def test_a_confirmed_removal_stops_suppressing_the_next_pairing(
        self, hass: HomeAssistant, mock_config_entry
    ) -> None:
        """A skip decided against the old bond must not outlive it.

        The first connection after a removal is the one that has to pair, and on
        a bed that grants one connection per pairing window it is the only one.
        """
        from custom_components.adjustable_bed.bond_verification import (
            CONF_BLE_BOND_CONTEXT,
        )
        from custom_components.adjustable_bed.const import CONF_BLE_BOND_ESTABLISHED
        from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator

        mock_config_entry.add_to_hass(hass)
        hass.config_entries.async_update_entry(
            mock_config_entry,
            data={
                **mock_config_entry.data,
                CONF_BLE_BOND_ESTABLISHED: True,
                CONF_BLE_BOND_CONTEXT: {"version": 1, "transport": "local"},
            },
        )
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        coordinator._skip_pair_next_attempt = True

        coordinator.apply_confirmed_bond_removal()
        await hass.async_block_till_done()

        assert coordinator._skip_pair_next_attempt is False
        assert CONF_BLE_BOND_CONTEXT not in mock_config_entry.data

        await coordinator.async_shutdown()

    async def test_non_pairing_protocol_discards_obsolete_bond_state(
        self, hass: HomeAssistant, mock_config_entry
    ) -> None:
        """A Linak upgrade should remove stale bond flags and its false repair."""
        hass.config_entries.async_update_entry(
            mock_config_entry,
            data={
                **mock_config_entry.data,
                CONF_BLE_BOND_ESTABLISHED: False,
                CONF_BLE_BOND_MARKER_UNRELIABLE: True,
                CONF_BLE_BOND_CONTEXT: {"version": 1, "transport": "proxy"},
            },
        )
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)

        with patch_coordinator_global(
            "delete_pairing_required_issue",
            new_callable=AsyncMock,
        ) as delete_issue:
            await coordinator.async_clear_obsolete_pairing_state()
            await hass.async_block_till_done()

        assert coordinator._ble_bond_established is False
        assert coordinator._ble_bond_marker_unreliable is False
        assert CONF_BLE_BOND_ESTABLISHED not in mock_config_entry.data
        assert CONF_BLE_BOND_MARKER_UNRELIABLE not in mock_config_entry.data
        assert CONF_BLE_BOND_CONTEXT not in mock_config_entry.data
        delete_issue.assert_awaited_once_with(hass, mock_config_entry.data[CONF_ADDRESS])

        await coordinator.async_shutdown()

    async def test_an_unknown_transport_records_no_provenance(
        self, hass: HomeAssistant, mock_config_entry
    ) -> None:
        """Unknown ownership must not be written as if it were established."""
        from custom_components.adjustable_bed.bluetooth_transport import (
            ConnectionPath,
            TransportClass,
        )
        from custom_components.adjustable_bed.bond_verification import (
            CONF_BLE_BOND_CONTEXT,
        )
        from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator

        mock_config_entry.add_to_hass(hass)
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        coordinator._connection_path = ConnectionPath(
            source="mystery", transport=TransportClass.UNKNOWN
        )
        coordinator._record_bond_provenance()
        await hass.async_block_till_done()

        assert CONF_BLE_BOND_CONTEXT not in mock_config_entry.data

        await coordinator.async_shutdown()


class TestUnverifiedBondMarkerScope:
    """A bond nothing could prove is only credible on the route that made it.

    Setup can pair through one adapter or proxy while automatic routing puts the
    coordinator's first real connection on another that was never bonded. An
    unscoped marker suppresses pair=True there, so a setup that actually worked
    ends as an authentication failure and a repair (issue #459).
    """

    def _coordinator(self, hass: HomeAssistant, **extra_data: object) -> AdjustableBedCoordinator:
        entry = MockConfigEntry(
            domain=DOMAIN,
            title=TEST_NAME,
            data={
                CONF_ADDRESS: TEST_ADDRESS,
                CONF_NAME: TEST_NAME,
                CONF_BED_TYPE: BED_TYPE_LEGGETT_OKIN,
                CONF_MOTOR_COUNT: 2,
                CONF_HAS_MASSAGE: False,
                CONF_DISABLE_ANGLE_SENSING: True,
                CONF_PREFERRED_ADAPTER: "auto",
                CONF_BLE_BOND_ESTABLISHED: True,
                **extra_data,
            },
            unique_id=TEST_ADDRESS,
            entry_id="unverified_bond_scope_test",
        )
        entry.add_to_hass(hass)
        return AdjustableBedCoordinator(hass, entry)

    @staticmethod
    def _device() -> MagicMock:
        device = MagicMock()
        device.details = {}
        return device

    async def test_the_route_that_paired_still_skips_pairing(self, hass: HomeAssistant) -> None:
        """The auth-error-82 protection has to survive the scoping."""
        coordinator = self._coordinator(hass, ble_bond_attempted_source="11:22:33:44:55:66")
        details: dict[str, Any] = {}

        _, use_pairing, _ = coordinator._prepare_pairing_attempt(
            self._device(), details, source="11:22:33:44:55:66"
        )

        assert use_pairing is False
        assert details["decision"] == "bond_marker_present"
        assert details["bond_marker_out_of_scope"] is False

    async def test_another_route_pairs_instead_of_trusting_the_marker(
        self, hass: HomeAssistant
    ) -> None:
        """Re-ranked onto a transport that was never bonded, so pair there."""
        coordinator = self._coordinator(hass, ble_bond_attempted_source="11:22:33:44:55:66")
        details: dict[str, Any] = {}

        _, use_pairing, _ = coordinator._prepare_pairing_attempt(
            self._device(), details, source="esp32-proxy-livingroom"
        )

        assert use_pairing is True
        assert details["decision"] == "bond_marker_other_transport"
        assert details["bond_marker_out_of_scope"] is True

    async def test_an_unknown_route_does_not_trust_a_scoped_marker(
        self, hass: HomeAssistant
    ) -> None:
        """Cannot show it is the same route, so it is not treated as one."""
        coordinator = self._coordinator(hass, ble_bond_attempted_source="11:22:33:44:55:66")
        details: dict[str, Any] = {}

        _, use_pairing, _ = coordinator._prepare_pairing_attempt(
            self._device(), details, source=None
        )

        assert use_pairing is True
        assert details["bond_marker_out_of_scope"] is True

    async def test_an_entry_without_a_scope_is_unchanged(self, hass: HomeAssistant) -> None:
        """A proven bond, or one written before scoping existed, is global."""
        coordinator = self._coordinator(hass)
        details: dict[str, Any] = {}

        _, use_pairing, _ = coordinator._prepare_pairing_attempt(
            self._device(), details, source="some-other-source"
        )

        assert use_pairing is False
        assert details["decision"] == "bond_marker_present"
        assert details["bond_marker_out_of_scope"] is False

    async def test_proving_the_bond_drops_the_route_scope(self, hass: HomeAssistant) -> None:
        """Provenance names its own owner, so the unproven scope is spent."""
        coordinator = self._coordinator(hass, ble_bond_attempted_source="11:22:33:44:55:66")

        coordinator._persist_bond_flags(
            established=True,
            context={
                "version": 1,
                "transport": "local",
                "source": "11:22:33:44:55:66",
                "adapter": "hci0",
                "verification": "runtime_authenticated_read",
                "verified_at": "2026-07-27T00:00:00+00:00",
            },
        )

        assert CONF_BLE_BOND_ATTEMPTED_SOURCE not in coordinator.entry.data
        assert CONF_BLE_BOND_CONTEXT in coordinator.entry.data


_AUTH_ERROR = (
    "Bluetooth GATT Error address=AA:BB:CC:DD:EE:01 "
    "handle=26 error=5 description=Insufficient authentication"
)


class TestProxyLinkPairedInPlace:
    """An unpaired proxy reconnect to a bonded bed pairs the live link.

    Through an ESP32 proxy, a reconnect without pair=True comes up unencrypted
    although bed and proxy still hold the bond. Dropping that link and
    reconnecting with pair=True asks the bed for a new bond, which it refuses
    outside its pairing window, so the bed only worked until the next
    disconnect after each power cycle. Pairing the live link reuses the keys.
    """

    def _make_coordinator(
        self,
        hass: HomeAssistant,
        bed_type: str = BED_TYPE_LEGGETT_OKIN,
        **extra_data: object,
    ) -> AdjustableBedCoordinator:
        entry = MockConfigEntry(
            domain=DOMAIN,
            title=TEST_NAME,
            data={
                CONF_ADDRESS: TEST_ADDRESS,
                CONF_NAME: TEST_NAME,
                CONF_BED_TYPE: bed_type,
                CONF_MOTOR_COUNT: 2,
                CONF_HAS_MASSAGE: False,
                CONF_DISABLE_ANGLE_SENSING: True,
                CONF_PREFERRED_ADAPTER: "auto",
                CONF_BLE_BOND_ESTABLISHED: True,
                **extra_data,
            },
            unique_id=TEST_ADDRESS,
            entry_id="proxy_in_place_pairing_test",
        )
        entry.add_to_hass(hass)
        return AdjustableBedCoordinator(hass, entry)

    def _link(
        self,
        coordinator: AdjustableBedCoordinator,
        *,
        reads: list[object],
        transport: TransportClass = TransportClass.PROXY,
        source_domain: str | None = "esphome",
    ) -> MagicMock:
        client = MagicMock()
        client.is_connected = True
        client.pair = AsyncMock()
        client.clear_cache = AsyncMock(return_value=True)
        client.read_gatt_char = AsyncMock(side_effect=reads)
        coordinator._client = client
        coordinator._connection_path = ConnectionPath(
            source="AA:BB:CC:DD:EE:10",
            transport=transport,
            source_domain=source_domain,
        )
        coordinator._attempt_used_pairing = False
        return client

    async def test_unencrypted_proxy_reconnect_pairs_the_live_link(
        self, hass: HomeAssistant
    ) -> None:
        """The probe's auth failure is fixed on the same link, nothing is cleared."""
        coordinator = self._make_coordinator(hass)
        coordinator._attempt_trusted_bond_marker = True
        client = self._link(coordinator, reads=[BleakError(_AUTH_ERROR), b"CU170"])

        with (
            patch(
                "custom_components.adjustable_bed.coordinator_bonds.create_pairing_required_issue",
                new_callable=AsyncMock,
            ) as issue,
            patch_coordinator_global("delete_pairing_required_issue", new_callable=AsyncMock),
            patch.object(
                coordinator, "_async_disconnect_locked", new_callable=AsyncMock
            ) as disconnect,
        ):
            assert await coordinator._async_verify_bonded() is True

        client.pair.assert_awaited_once_with()
        assert client.read_gatt_char.await_count == 2
        disconnect.assert_not_awaited()
        client.clear_cache.assert_not_awaited()
        issue.assert_not_awaited()
        assert coordinator._ble_bond_established is True
        assert coordinator._ble_bond_marker_unreliable is False
        assert coordinator._last_bond_verification["status"] == "encrypted_in_place"

    async def test_in_place_pairing_releases_the_latch(self, hass: HomeAssistant) -> None:
        """One bonded proxy session is enough to stop forcing pair=True."""
        coordinator = self._make_coordinator(
            hass,
            **{CONF_BLE_BOND_MARKER_UNRELIABLE: True, CONF_BLE_BOND_ESTABLISHED: False},
        )
        self._link(coordinator, reads=[BleakError(_AUTH_ERROR), b"CU170"])

        with patch_coordinator_global("delete_pairing_required_issue", new_callable=AsyncMock):
            assert await coordinator._async_verify_bonded() is True

        assert coordinator._ble_bond_marker_unreliable is False
        assert coordinator._ble_bond_established is True
        assert CONF_BLE_BOND_MARKER_UNRELIABLE not in coordinator.entry.data
        assert coordinator.entry.data[CONF_BLE_BOND_ESTABLISHED] is True

        # The next reconnect no longer asks the bed for a new bond.
        device = MagicMock()
        device.details = {}
        _, use_pairing, _ = coordinator._prepare_pairing_attempt(device, {})
        assert use_pairing is False

    async def test_a_paired_proxy_session_releases_the_latch(self, hass: HomeAssistant) -> None:
        """A power-cycle pairing over a proxy must not stay latched afterwards."""
        coordinator = self._make_coordinator(
            hass,
            **{CONF_BLE_BOND_MARKER_UNRELIABLE: True, CONF_BLE_BOND_ESTABLISHED: False},
        )
        client = self._link(coordinator, reads=[b"CU170"])
        coordinator._attempt_used_pairing = True

        with patch_coordinator_global("delete_pairing_required_issue", new_callable=AsyncMock):
            assert await coordinator._async_verify_bonded() is True

        client.pair.assert_not_awaited()
        assert coordinator._ble_bond_marker_unreliable is False
        assert coordinator._ble_bond_established is True

    @pytest.mark.parametrize("bed_type", [BED_TYPE_SLEEP_NUMBER, BED_TYPE_VIBRADORM_APP])
    async def test_excluded_proxy_beds_keep_the_paired_session_latch(
        self, hass: HomeAssistant, bed_type: str
    ) -> None:
        """Beds without in-place proxy recovery still need the existing retest rule."""
        coordinator = self._make_coordinator(
            hass,
            bed_type=bed_type,
            **{CONF_BLE_BOND_MARKER_UNRELIABLE: True, CONF_BLE_BOND_ESTABLISHED: False},
        )
        self._link(coordinator, reads=[])
        coordinator._attempt_used_pairing = True

        with patch_coordinator_global("delete_pairing_required_issue", new_callable=AsyncMock):
            assert await coordinator._async_record_verified_bond() is True

        assert coordinator._ble_bond_marker_unreliable is True
        assert coordinator._latched_pairing_successes == 1
        device = MagicMock(details={})
        _, use_pairing, _ = coordinator._prepare_pairing_attempt(device, {})
        assert use_pairing is True

    @pytest.mark.parametrize("previous_source", [None, "old-proxy"])
    async def test_latch_release_and_provenance_do_not_reload_the_entry(
        self, hass: HomeAssistant, previous_source: str | None
    ) -> None:
        """A new bond owner and released latch are one internal entry update."""
        from custom_components.adjustable_bed import _async_update_listener

        coordinator = self._make_coordinator(
            hass,
            **{CONF_BLE_BOND_MARKER_UNRELIABLE: True, CONF_BLE_BOND_ESTABLISHED: False},
        )
        if previous_source is not None:
            hass.config_entries.async_update_entry(
                coordinator.entry,
                data={
                    **coordinator.entry.data,
                    CONF_BLE_BOND_CONTEXT: {
                        "version": 1,
                        "transport": "proxy",
                        "source": previous_source,
                        "verification": "runtime_authenticated_read",
                        "verified_at": "old",
                    },
                },
            )
        self._link(coordinator, reads=[b"CU170"])
        coordinator._attempt_used_pairing = True
        hass.data.setdefault(DOMAIN, {})[coordinator.entry.entry_id] = coordinator
        remove_listener = coordinator.entry.add_update_listener(_async_update_listener)
        try:
            with (
                patch_coordinator_global("delete_pairing_required_issue", new_callable=AsyncMock),
                patch.object(hass.config_entries, "async_reload", new_callable=AsyncMock) as reload,
                patch.object(
                    hass.config_entries,
                    "async_update_entry",
                    wraps=hass.config_entries.async_update_entry,
                ) as update,
            ):
                assert await coordinator._async_verify_bonded() is True
                await hass.async_block_till_done()

                assert update.call_count == 1
                reload.assert_not_awaited()
                assert (
                    coordinator.entry.data[CONF_BLE_BOND_CONTEXT]["source"] == "AA:BB:CC:DD:EE:10"
                )
                assert CONF_BLE_BOND_MARKER_UNRELIABLE not in coordinator.entry.data

                # A real options change must still reach the listener.
                hass.config_entries.async_update_entry(
                    coordinator.entry, options={"motor_count": 3}
                )
                await hass.async_block_till_done()
                reload.assert_awaited_once_with(coordinator.entry.entry_id)
        finally:
            remove_listener()
            hass.data[DOMAIN].pop(coordinator.entry.entry_id)

    async def test_a_refused_in_place_pairing_falls_back_to_the_usual_recovery(
        self, hass: HomeAssistant
    ) -> None:
        """If the bed refuses, the link is dropped and recovery runs as before."""
        coordinator = self._make_coordinator(hass)
        client = self._link(coordinator, reads=[BleakError(_AUTH_ERROR)])
        client.pair = AsyncMock(side_effect=BleakError("Pairing failed due to error: 102"))

        with (
            patch(
                "custom_components.adjustable_bed.coordinator_bonds.create_pairing_required_issue",
                new_callable=AsyncMock,
            ),
            patch.object(
                coordinator, "_async_disconnect_locked", new_callable=AsyncMock
            ) as disconnect,
        ):
            assert await coordinator._async_verify_bonded() is False

        client.pair.assert_awaited_once_with()
        disconnect.assert_awaited_once()
        assert coordinator._last_bond_evidence is not None
        assert coordinator._last_bond_evidence.status is BondVerificationStatus.AUTH_FAILED

    async def test_an_auth_failure_after_pairing_in_place_is_real_evidence(
        self, hass: HomeAssistant
    ) -> None:
        """A paired link that still fails the probe goes to the usual recovery."""
        coordinator = self._make_coordinator(hass)
        client = self._link(
            coordinator, reads=[BleakError(_AUTH_ERROR), BleakError(_AUTH_ERROR)]
        )

        with (
            patch(
                "custom_components.adjustable_bed.coordinator_bonds.create_pairing_required_issue",
                new_callable=AsyncMock,
            ),
            patch.object(
                coordinator, "_async_disconnect_locked", new_callable=AsyncMock
            ) as disconnect,
        ):
            assert await coordinator._async_verify_bonded() is False

        client.pair.assert_awaited_once_with()
        disconnect.assert_awaited_once()

    @pytest.mark.parametrize(
        ("transport", "source_domain"),
        [(TransportClass.LOCAL, None), (TransportClass.PROXY, "other_proxy")],
    )
    async def test_other_transports_keep_the_reconnect_recovery(
        self, hass: HomeAssistant, transport: TransportClass, source_domain: str | None
    ) -> None:
        """BlueZ raises link security itself; only ESPHome proxies pair in place."""
        coordinator = self._make_coordinator(hass)
        client = self._link(
            coordinator,
            reads=[BleakError(_AUTH_ERROR)],
            transport=transport,
            source_domain=source_domain,
        )

        with (
            patch(
                "custom_components.adjustable_bed.coordinator_bonds.create_pairing_required_issue",
                new_callable=AsyncMock,
            ),
            patch.object(coordinator, "_async_disconnect_locked", new_callable=AsyncMock),
        ):
            assert await coordinator._async_verify_bonded() is False

        client.pair.assert_not_awaited()

    async def test_a_link_that_already_paired_is_not_paired_again(
        self, hass: HomeAssistant
    ) -> None:
        """An auth failure on a link that requested pairing is evidence."""
        coordinator = self._make_coordinator(hass)
        client = self._link(coordinator, reads=[BleakError(_AUTH_ERROR)])
        coordinator._attempt_used_pairing = True

        assert coordinator._can_encrypt_proxy_link_in_place() is False
        with (
            patch(
                "custom_components.adjustable_bed.coordinator_bonds.create_pairing_required_issue",
                new_callable=AsyncMock,
            ),
            patch.object(coordinator, "_async_disconnect_locked", new_callable=AsyncMock),
        ):
            assert await coordinator._async_verify_bonded() is False
        client.pair.assert_not_awaited()

    async def test_one_connection_beds_keep_their_own_path(self, hass: HomeAssistant) -> None:
        """LP Gen2 retains its link and pairs at runtime as before (issue #709)."""
        coordinator = self._make_coordinator(hass, bed_type=BED_TYPE_LEGGETT_GEN2)
        client = self._link(coordinator, reads=[BleakError(_AUTH_ERROR)])

        assert coordinator._can_encrypt_proxy_link_in_place() is False
        assert coordinator._can_encrypt_link_in_place() is True
        with patch(
            "custom_components.adjustable_bed.coordinator_bonds.create_pairing_required_issue",
            new_callable=AsyncMock,
        ):
            # The probe keeps the link for startup without pairing it here.
            assert await coordinator._async_verify_bonded() is True
        client.pair.assert_not_awaited()
        assert coordinator._client is client
