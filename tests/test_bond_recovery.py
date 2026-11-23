"""Tests for confirmed stale-bond recovery (issue #459)."""

from __future__ import annotations

import asyncio
import contextlib
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.core import HomeAssistant

from custom_components.adjustable_bed.bluetooth_bond import (
    BluezReadStatus,
    BondRemovalResult,
    BondRemovalStatus,
    LocalBondInventory,
    LocalBondRecord,
)
from custom_components.adjustable_bed.bluetooth_freshness import (
    AdvertisementEvidence,
    FreshnessStatus,
)
from custom_components.adjustable_bed.bluetooth_transport import ConnectionPath, TransportClass
from custom_components.adjustable_bed.bond_recovery import (
    RecoveryEligibility,
    RecoveryOffer,
    async_recover_local_bond,
    async_recovery_offer,
    evidence_is_local_auth_failure,
)
from custom_components.adjustable_bed.bond_verification import (
    BondEvidence,
    BondOwner,
    BondVerificationStatus,
)
from custom_components.adjustable_bed.const import (
    BED_TYPE_LEGGETT_GEN2,
    BED_TYPE_OKIN_CST,
    BED_TYPE_OKIN_UUID,
)
from custom_components.adjustable_bed.setup_operation import OperationOutcome

TEST_ADDRESS = "AA:BB:CC:DD:EE:FF"
_RECOVERY = "custom_components.adjustable_bed.bond_recovery"
_REMOVED_AT = 123.0


def _record(
    adapter_address: str = "11:22:33:44:55:66", adapter: str = "hci0"
) -> LocalBondRecord:
    return LocalBondRecord(
        address=TEST_ADDRESS,
        device_path=f"/org/bluez/{adapter}/dev_AA_BB_CC_DD_EE_FF",
        adapter_path=f"/org/bluez/{adapter}",
        adapter_address=adapter_address,
        paired=True,
        bonded=True,
    )


def _local_auth_evidence(**overrides: Any) -> dict[str, Any]:
    data = {
        "evidence_status": "auth_failed",
        "evidence_transport": "local",
        "evidence_source": "11:22:33:44:55:66",
        "evidence_adapter": "hci0",
    }
    data.update(overrides)
    return data


def _patch_inventory(*records: LocalBondRecord, readable: bool = True):
    inventory = LocalBondInventory(
        status=BluezReadStatus.OK if readable else BluezReadStatus.UNAVAILABLE,
        records=records,
    )
    return patch(f"{_RECOVERY}.async_read_local_bonds", AsyncMock(return_value=inventory))


def _client(source: str = "11:22:33:44:55:66") -> MagicMock:
    client = MagicMock()
    client._connected_scanner.source = source
    client.disconnect = AsyncMock()
    client.pair = AsyncMock()
    return client


def _bond(status: BondVerificationStatus, operation: str) -> BondEvidence:
    return BondEvidence(
        status=status,
        owner=BondOwner(
            transport=TransportClass.LOCAL,
            source="11:22:33:44:55:66",
            adapter="hci0",
        ),
        operation=operation,
        observed_at="2026-07-27T00:00:00+00:00",
    )


def _local_path() -> ConnectionPath:
    return ConnectionPath(
        source="11:22:33:44:55:66",
        transport=TransportClass.LOCAL,
        adapter="hci0",
    )


class TestWhenRecoveryIsOffered:
    """Removing a bond is only ever justified by evidence about that bond."""

    async def test_local_authentication_failure_is_eligible(
        self, hass: HomeAssistant
    ) -> None:
        with _patch_inventory(_record()):
            offer = await async_recovery_offer(
                hass,
                address=TEST_ADDRESS,
                issue_data=_local_auth_evidence(),
                bed_type=BED_TYPE_OKIN_UUID,
                protocol_variant=None,
            )
        assert offer.is_eligible
        assert offer.record is not None

    async def test_a_proxy_failure_is_never_eligible(self, hass: HomeAssistant) -> None:
        """Host BlueZ was not involved, so its bond is not the suspect."""
        with _patch_inventory(_record()):
            offer = await async_recovery_offer(
                hass,
                address=TEST_ADDRESS,
                issue_data=_local_auth_evidence(evidence_transport="proxy"),
                bed_type=BED_TYPE_OKIN_UUID,
                protocol_variant=None,
            )
        assert not offer.is_eligible
        assert offer.eligibility == RecoveryEligibility.NOT_LOCAL

    @pytest.mark.parametrize(
        "status", ["inconclusive", "unsupported", "verified", None]
    )
    async def test_only_an_authentication_failure_qualifies(
        self, hass: HomeAssistant, status: str | None
    ) -> None:
        """Timeouts and missing characteristics prove nothing about a bond."""
        data = _local_auth_evidence(evidence_status=status)
        with _patch_inventory(_record()):
            offer = await async_recovery_offer(
                hass,
                address=TEST_ADDRESS,
                issue_data=data,
                bed_type=BED_TYPE_OKIN_UUID,
                protocol_variant=None,
            )
        assert not offer.is_eligible
        assert offer.eligibility == RecoveryEligibility.NO_EVIDENCE

    async def test_missing_bed_type_has_no_destructive_offer(
        self, hass: HomeAssistant
    ) -> None:
        with _patch_inventory(_record()):
            offer = await async_recovery_offer(
                hass,
                address=TEST_ADDRESS,
                issue_data=_local_auth_evidence(),
                bed_type=None,
                protocol_variant=None,
            )
        assert offer.eligibility == RecoveryEligibility.NO_VERIFIER

    async def test_okin_cst_has_no_destructive_offer(
        self, hass: HomeAssistant
    ) -> None:
        """Its auth-gated read never positively verifies a replacement bond."""
        with _patch_inventory(_record()):
            offer = await async_recovery_offer(
                hass,
                address=TEST_ADDRESS,
                issue_data=_local_auth_evidence(),
                bed_type=BED_TYPE_OKIN_CST,
                protocol_variant=None,
            )
        assert offer.eligibility == RecoveryEligibility.NO_VERIFIER

    async def test_a_legacy_issue_without_evidence_is_not_eligible(
        self, hass: HomeAssistant
    ) -> None:
        """Repairs raised before evidence existed grant no permission."""
        with _patch_inventory(_record()):
            offer = await async_recovery_offer(
                hass,
                address=TEST_ADDRESS,
                issue_data={"address": TEST_ADDRESS, "name": "Bed"},
                bed_type=BED_TYPE_OKIN_UUID,
                protocol_variant=None,
            )
        assert offer.eligibility == RecoveryEligibility.NO_EVIDENCE

    async def test_a_one_connection_bed_is_never_offered_removal(
        self, hass: HomeAssistant
    ) -> None:
        """Removing the bond drops the only link the box will grant (#385)."""
        with _patch_inventory(_record()):
            offer = await async_recovery_offer(
                hass,
                address=TEST_ADDRESS,
                issue_data=_local_auth_evidence(),
                bed_type=BED_TYPE_LEGGETT_GEN2,
                protocol_variant=None,
            )
        assert offer.eligibility == RecoveryEligibility.KEEPS_FIRST_LINK

    async def test_an_unreadable_host_is_not_eligible(self, hass: HomeAssistant) -> None:
        with _patch_inventory(readable=False):
            offer = await async_recovery_offer(
                hass,
                address=TEST_ADDRESS,
                issue_data=_local_auth_evidence(),
                bed_type=BED_TYPE_OKIN_UUID,
                protocol_variant=None,
            )
        assert offer.eligibility == RecoveryEligibility.UNREADABLE

    async def test_provenance_naming_an_absent_adapter_is_not_eligible(
        self, hass: HomeAssistant
    ) -> None:
        # Neither the adapter MAC nor the interface name matches what the
        # evidence recorded, so nothing here is the bond it is talking about.
        with _patch_inventory(_record("AA:AA:AA:AA:AA:AA", adapter="hci1")):
            offer = await async_recovery_offer(
                hass,
                address=TEST_ADDRESS,
                issue_data=_local_auth_evidence(),
                bed_type=BED_TYPE_OKIN_UUID,
                protocol_variant=None,
            )
        assert not offer.is_eligible

    async def test_replaced_adapter_does_not_inherit_the_interface_match(
        self, hass: HomeAssistant
    ) -> None:
        """A new adapter on hci0 must not inherit evidence about the old MAC."""
        with _patch_inventory(_record("AA:AA:AA:AA:AA:AA", adapter="hci0")):
            offer = await async_recovery_offer(
                hass,
                address=TEST_ADDRESS,
                issue_data=_local_auth_evidence(),
                bed_type=BED_TYPE_OKIN_UUID,
                protocol_variant=None,
            )
        assert offer.eligibility == RecoveryEligibility.AMBIGUOUS

    def test_evidence_predicate_needs_both_halves(self) -> None:
        assert evidence_is_local_auth_failure(_local_auth_evidence())
        assert not evidence_is_local_auth_failure(
            _local_auth_evidence(evidence_transport="unknown")
        )
        assert not evidence_is_local_auth_failure(
            _local_auth_evidence(evidence_status="inconclusive")
        )


class TestRunningRecovery:
    """Nothing is destroyed until the bed has proven it is reachable."""

    @pytest.fixture(autouse=True)
    def _approved_bond_still_present(self):
        """Default: the approved bond is still exactly the one BlueZ holds.

        The transaction re-reads BlueZ immediately before ``RemoveDevice``, so
        every test that expects a removal needs that re-read to agree. Tests
        about the re-read itself override this with their own patch.
        """
        with _patch_inventory(_record()):
            yield

    def _offer(self) -> RecoveryOffer:
        return RecoveryOffer(
            eligibility=RecoveryEligibility.ELIGIBLE,
            record=_record(),
            owner=BondOwner(transport=TransportClass.LOCAL, source="11:22:33:44:55:66"),
        )

    async def test_a_sleeping_bed_keeps_its_bond(self, hass: HomeAssistant) -> None:
        stale = AdvertisementEvidence(status=FreshnessStatus.STALE, age_seconds=600.0)
        wait = AsyncMock(return_value=(stale, None))
        with (
            patch(f"{_RECOVERY}.async_wait_for_advertisement", wait),
            patch(f"{_RECOVERY}.async_remove_local_bond") as removal,
        ):
            result = await async_recover_local_bond(
                hass,
                address=TEST_ADDRESS,
                name="Bed",
                offer=self._offer(),
                bed_type=BED_TYPE_OKIN_UUID,
                protocol_variant=None,
            )
        removal.assert_not_called()
        assert wait.await_args.kwargs["source"] == "11:22:33:44:55:66"
        assert result.outcome is OperationOutcome.NOT_ADVERTISING

    async def test_a_different_actual_source_is_rejected_before_removal(
        self, hass: HomeAssistant
    ) -> None:
        fresh = AdvertisementEvidence(status=FreshnessStatus.FRESH, age_seconds=1.0)
        client = _client("proxy-source")
        with (
            patch(
                f"{_RECOVERY}.async_wait_for_advertisement",
                AsyncMock(return_value=(fresh, MagicMock())),
            ),
            patch(
                "bleak_retry_connector.establish_connection",
                AsyncMock(return_value=client),
            ),
            patch(
                f"{_RECOVERY}.async_path_for_source",
                return_value=ConnectionPath(
                    source="proxy-source", transport=TransportClass.PROXY
                ),
            ),
            patch(f"{_RECOVERY}.async_remove_local_bond") as removal,
        ):
            result = await async_recover_local_bond(
                hass,
                address=TEST_ADDRESS,
                name="Bed",
                offer=self._offer(),
                bed_type=BED_TYPE_OKIN_UUID,
                protocol_variant=None,
            )
        assert result.outcome is OperationOutcome.CONNECTION_FAILED
        assert result.detail == "unexpected_connection_source"
        removal.assert_not_called()

    async def test_a_different_recovery_source_is_rejected_before_pairing(
        self, hass: HomeAssistant
    ) -> None:
        """Rerouting after removal must not create a bond on a proxy."""
        fresh = AdvertisementEvidence(status=FreshnessStatus.FRESH, age_seconds=1.0)
        removed = BondRemovalResult(
            status=BondRemovalStatus.REMOVED,
            record=_record(),
            removed_at=_REMOVED_AT,
        )
        preflight_client = _client()
        recovery_client = _client("proxy-source")
        with (
            patch(
                f"{_RECOVERY}.async_wait_for_advertisement",
                AsyncMock(return_value=(fresh, MagicMock())),
            ),
            patch(
                f"{_RECOVERY}.async_remove_local_bond",
                AsyncMock(return_value=removed),
            ),
            patch(
                "bleak_retry_connector.establish_connection",
                AsyncMock(side_effect=[preflight_client, recovery_client]),
            ),
            patch(
                f"{_RECOVERY}.async_path_for_source",
                side_effect=[
                    _local_path(),
                    ConnectionPath(
                        source="proxy-source", transport=TransportClass.PROXY
                    ),
                ],
            ),
            patch(
                f"{_RECOVERY}.async_verify_authenticated_access",
                AsyncMock(
                    return_value=_bond(
                        BondVerificationStatus.AUTH_FAILED, "preflight"
                    )
                ),
            ),
        ):
            result = await async_recover_local_bond(
                hass,
                address=TEST_ADDRESS,
                name="Bed",
                offer=self._offer(),
                bed_type=BED_TYPE_OKIN_UUID,
                protocol_variant=None,
            )
        assert result.outcome is OperationOutcome.BOND_VERIFICATION_FAILED
        assert result.detail == "unexpected_connection_source"
        preflight_client.pair.assert_not_awaited()
        recovery_client.pair.assert_not_awaited()

    async def test_a_failed_removal_stops_before_pairing(
        self, hass: HomeAssistant
    ) -> None:
        fresh = AdvertisementEvidence(status=FreshnessStatus.FRESH, age_seconds=1.0)
        failed = BondRemovalResult(
            status=BondRemovalStatus.VERIFICATION_FAILED, error="bond_still_present"
        )
        client = _client()
        with (
            patch(
                f"{_RECOVERY}.async_wait_for_advertisement",
                AsyncMock(return_value=(fresh, MagicMock())),
            ),
            patch(
                f"{_RECOVERY}.async_remove_local_bond", AsyncMock(return_value=failed)
            ),
            patch(
                "bleak_retry_connector.establish_connection",
                AsyncMock(return_value=client),
            ) as connect,
            patch(f"{_RECOVERY}.async_path_for_source", return_value=_local_path()),
            patch(
                f"{_RECOVERY}.async_verify_authenticated_access",
                AsyncMock(return_value=_bond(BondVerificationStatus.AUTH_FAILED, "preflight")),
            ),
        ):
            result = await async_recover_local_bond(
                hass,
                address=TEST_ADDRESS,
                name="Bed",
                offer=self._offer(),
                bed_type=BED_TYPE_OKIN_UUID,
                protocol_variant=None,
            )
        connect.assert_awaited_once()
        assert result.outcome is OperationOutcome.UNPAIR_FAILED

    async def test_an_unverifiable_removal_is_not_reported_as_unchanged(
        self, hass: HomeAssistant
    ) -> None:
        """RemoveDevice was accepted and the check could not be read.

        "The bond could not be removed" would send the user back to remove a
        bond that may already be gone, when what they may need is to pair a
        replacement.
        """
        fresh = AdvertisementEvidence(status=FreshnessStatus.FRESH, age_seconds=1.0)
        unconfirmed = BondRemovalResult(
            status=BondRemovalStatus.VERIFICATION_FAILED,
            error="bluez_unreadable_after_removal",
        )
        removed_marker = AsyncMock()
        with (
            patch(
                f"{_RECOVERY}.async_wait_for_advertisement",
                AsyncMock(return_value=(fresh, MagicMock())),
            ),
            patch(
                f"{_RECOVERY}.async_remove_local_bond",
                AsyncMock(return_value=unconfirmed),
            ),
            patch(
                "bleak_retry_connector.establish_connection",
                AsyncMock(return_value=_client()),
            ),
            patch(f"{_RECOVERY}.async_path_for_source", return_value=_local_path()),
            patch(
                f"{_RECOVERY}.async_verify_authenticated_access",
                AsyncMock(return_value=_bond(BondVerificationStatus.AUTH_FAILED, "preflight")),
            ),
        ):
            result = await async_recover_local_bond(
                hass,
                address=TEST_ADDRESS,
                name="Bed",
                offer=self._offer(),
                bed_type=BED_TYPE_OKIN_UUID,
                protocol_variant=None,
                on_bond_removed=removed_marker,
            )
        assert result.outcome is OperationOutcome.UNPAIR_UNCONFIRMED
        # Nothing is known to have been removed, so nothing is invalidated.
        removed_marker.assert_not_awaited()

    async def test_removal_without_a_completion_time_stops_before_reconnect(
        self, hass: HomeAssistant
    ) -> None:
        """Never reuse the vanished Device1 without a trustworthy cutoff."""
        fresh = AdvertisementEvidence(status=FreshnessStatus.FRESH, age_seconds=1.0)
        removed = BondRemovalResult(
            status=BondRemovalStatus.REMOVED,
            record=_record(),
        )
        client = _client()
        wait = AsyncMock(return_value=(fresh, MagicMock()))
        with (
            patch(f"{_RECOVERY}.async_wait_for_advertisement", wait),
            patch(
                f"{_RECOVERY}.async_remove_local_bond",
                AsyncMock(return_value=removed),
            ),
            patch(
                "bleak_retry_connector.establish_connection",
                AsyncMock(return_value=client),
            ) as connect,
            patch(f"{_RECOVERY}.async_path_for_source", return_value=_local_path()),
            patch(
                f"{_RECOVERY}.async_verify_authenticated_access",
                AsyncMock(
                    return_value=_bond(
                        BondVerificationStatus.AUTH_FAILED, "preflight"
                    )
                ),
            ),
        ):
            result = await async_recover_local_bond(
                hass,
                address=TEST_ADDRESS,
                name="Bed",
                offer=self._offer(),
                bed_type=BED_TYPE_OKIN_UUID,
                protocol_variant=None,
            )
        connect.assert_awaited_once()
        wait.assert_awaited_once()
        assert result.outcome is OperationOutcome.BOND_VERIFICATION_FAILED
        assert result.detail == "removal_completion_time_unavailable"

    async def test_an_unverified_new_bond_is_not_a_success(
        self, hass: HomeAssistant
    ) -> None:
        """The old bond is gone; claiming success would close a live problem."""
        fresh = AdvertisementEvidence(status=FreshnessStatus.FRESH, age_seconds=1.0)
        removed = BondRemovalResult(
            status=BondRemovalStatus.REMOVED,
            record=_record(),
            removed_at=_REMOVED_AT,
        )
        preflight_client = _client()
        recovery_client = _client()
        with (
            patch(
                f"{_RECOVERY}.async_wait_for_advertisement",
                AsyncMock(return_value=(fresh, MagicMock())),
            ),
            patch(
                f"{_RECOVERY}.async_remove_local_bond", AsyncMock(return_value=removed)
            ),
            patch(
                "bleak_retry_connector.establish_connection",
                AsyncMock(side_effect=[preflight_client, recovery_client]),
            ),
            patch(
                f"{_RECOVERY}.async_verify_authenticated_access",
                AsyncMock(
                    side_effect=[
                        _bond(BondVerificationStatus.AUTH_FAILED, "preflight"),
                        _bond(BondVerificationStatus.INCONCLUSIVE, "stale_bond_recovery"),
                    ]
                ),
            ),
            patch(f"{_RECOVERY}.async_path_for_source", return_value=_local_path()),
        ):
            result = await async_recover_local_bond(
                hass,
                address=TEST_ADDRESS,
                name="Bed",
                offer=self._offer(),
                bed_type=BED_TYPE_OKIN_UUID,
                protocol_variant=None,
            )
        assert result.outcome is OperationOutcome.BOND_VERIFICATION_FAILED
        preflight_client.disconnect.assert_awaited_once_with()
        recovery_client.disconnect.assert_awaited_once_with()

    async def test_a_confirmed_removal_invalidates_the_marker_even_when_pairing_fails(
        self, hass: HomeAssistant
    ) -> None:
        """The removed bond's marker must not outlive the bond itself.

        The repair stays open, and a marker still saying "bonded" would make the
        next connection skip pair=True on a device that now has no bond, which
        just repeats the authentication failure it was raised for.
        """
        fresh = AdvertisementEvidence(status=FreshnessStatus.FRESH, age_seconds=1.0)
        removed = BondRemovalResult(
            status=BondRemovalStatus.REMOVED,
            record=_record(),
            removed_at=_REMOVED_AT,
        )
        removed_marker = AsyncMock()
        persisted = AsyncMock()
        with (
            patch(
                f"{_RECOVERY}.async_wait_for_advertisement",
                AsyncMock(side_effect=[(fresh, MagicMock()), (fresh, None)]),
            ),
            patch(
                f"{_RECOVERY}.async_remove_local_bond", AsyncMock(return_value=removed)
            ),
            patch(
                "bleak_retry_connector.establish_connection",
                AsyncMock(return_value=_client()),
            ),
            patch(f"{_RECOVERY}.async_path_for_source", return_value=_local_path()),
            patch(
                f"{_RECOVERY}.async_verify_authenticated_access",
                AsyncMock(return_value=_bond(BondVerificationStatus.AUTH_FAILED, "preflight")),
            ),
        ):
            result = await async_recover_local_bond(
                hass,
                address=TEST_ADDRESS,
                name="Bed",
                offer=self._offer(),
                bed_type=BED_TYPE_OKIN_UUID,
                protocol_variant=None,
                on_verified=persisted,
                on_bond_removed=removed_marker,
            )
        assert result.outcome is OperationOutcome.BOND_VERIFICATION_FAILED
        removed_marker.assert_awaited_once_with()
        persisted.assert_not_awaited()

    async def test_a_verified_new_bond_succeeds_and_carries_its_owner(
        self, hass: HomeAssistant
    ) -> None:
        removed_marker = AsyncMock()
        fresh = AdvertisementEvidence(status=FreshnessStatus.FRESH, age_seconds=1.0)
        removed = BondRemovalResult(
            status=BondRemovalStatus.REMOVED,
            record=_record(),
            removed_at=_REMOVED_AT,
        )
        preflight_client = _client()
        recovery_client = _client()
        with (
            patch(
                f"{_RECOVERY}.async_wait_for_advertisement",
                AsyncMock(return_value=(fresh, MagicMock())),
            ),
            patch(
                f"{_RECOVERY}.async_remove_local_bond", AsyncMock(return_value=removed)
            ),
            patch(
                "bleak_retry_connector.establish_connection",
                AsyncMock(side_effect=[preflight_client, recovery_client]),
            ),
            patch(
                f"{_RECOVERY}.async_verify_authenticated_access",
                AsyncMock(
                    side_effect=[
                        _bond(BondVerificationStatus.AUTH_FAILED, "preflight"),
                        _bond(BondVerificationStatus.VERIFIED, "stale_bond_recovery"),
                    ]
                ),
            ),
            patch(f"{_RECOVERY}.async_path_for_source", return_value=_local_path()),
        ):
            result = await async_recover_local_bond(
                hass,
                address=TEST_ADDRESS,
                name="Bed",
                offer=self._offer(),
                bed_type=BED_TYPE_OKIN_UUID,
                protocol_variant=None,
                on_bond_removed=removed_marker,
            )
        assert result.succeeded
        assert result.path is not None
        assert result.path.transport is TransportClass.LOCAL
        preflight_client.pair.assert_not_awaited()
        recovery_client.pair.assert_awaited_once_with()
        # The replacement was proven, so its marker is written, not cleared.
        removed_marker.assert_not_awaited()

    async def test_reconnect_uses_a_device_resolved_after_removal(
        self, hass: HomeAssistant
    ) -> None:
        fresh = AdvertisementEvidence(status=FreshnessStatus.FRESH, age_seconds=1.0)
        old_device = MagicMock(name="old_device")
        new_device = MagicMock(name="new_device")
        removed = BondRemovalResult(
            status=BondRemovalStatus.REMOVED,
            record=_record(),
            removed_at=_REMOVED_AT,
        )
        preflight_client = _client()
        recovery_client = _client()
        connect = AsyncMock(side_effect=[preflight_client, recovery_client])
        wait = AsyncMock(
            side_effect=[(fresh, old_device), (fresh, new_device)]
        )
        with (
            patch(f"{_RECOVERY}.async_wait_for_advertisement", wait),
            patch(
                f"{_RECOVERY}.async_remove_local_bond",
                AsyncMock(return_value=removed),
            ),
            patch("bleak_retry_connector.establish_connection", connect),
            patch(f"{_RECOVERY}.async_path_for_source", return_value=_local_path()),
            patch(
                f"{_RECOVERY}.async_verify_authenticated_access",
                AsyncMock(
                    side_effect=[
                        _bond(BondVerificationStatus.AUTH_FAILED, "preflight"),
                        _bond(BondVerificationStatus.VERIFIED, "stale_bond_recovery"),
                    ]
                ),
            ),
        ):
            result = await async_recover_local_bond(
                hass,
                address=TEST_ADDRESS,
                name="Bed",
                offer=self._offer(),
                bed_type=BED_TYPE_OKIN_UUID,
                protocol_variant=None,
            )
        assert result.succeeded
        assert connect.await_args_list[0].args[1] is old_device
        assert connect.await_args_list[1].args[1] is new_device
        assert wait.await_args_list[1].kwargs["seen_after"] == _REMOVED_AT

    async def test_cancellation_after_removal_still_verifies_and_persists(
        self, hass: HomeAssistant
    ) -> None:
        fresh = AdvertisementEvidence(status=FreshnessStatus.FRESH, age_seconds=1.0)
        removed = BondRemovalResult(
            status=BondRemovalStatus.REMOVED,
            record=_record(),
            removed_at=_REMOVED_AT,
        )
        removal_started = asyncio.Event()
        release_removal = asyncio.Event()
        gate_events: list[str] = []
        persisted = AsyncMock()

        async def remove(_record: LocalBondRecord) -> BondRemovalResult:
            removal_started.set()
            await release_removal.wait()
            return removed

        @contextlib.asynccontextmanager
        async def transport_gate(operation: str):
            gate_events.append(f"enter:{operation}")
            try:
                yield
            finally:
                gate_events.append(f"exit:{operation}")

        with (
            patch(
                f"{_RECOVERY}.async_wait_for_advertisement",
                AsyncMock(return_value=(fresh, MagicMock())),
            ),
            patch(f"{_RECOVERY}.async_remove_local_bond", side_effect=remove),
            patch(
                "bleak_retry_connector.establish_connection",
                AsyncMock(side_effect=[_client(), _client()]),
            ),
            patch(f"{_RECOVERY}.async_path_for_source", return_value=_local_path()),
            patch(
                f"{_RECOVERY}.async_verify_authenticated_access",
                AsyncMock(
                    side_effect=[
                        _bond(BondVerificationStatus.AUTH_FAILED, "preflight"),
                        _bond(BondVerificationStatus.VERIFIED, "stale_bond_recovery"),
                    ]
                ),
            ),
        ):
            task = asyncio.create_task(
                async_recover_local_bond(
                    hass,
                    address=TEST_ADDRESS,
                    name="Bed",
                    offer=self._offer(),
                    bed_type=BED_TYPE_OKIN_UUID,
                    protocol_variant=None,
                    transport_operation=transport_gate,
                    on_verified=persisted,
                )
            )
            await removal_started.wait()
            task.cancel()
            await asyncio.sleep(0)
            task.cancel()
            release_removal.set()
            result = await task

        assert result.succeeded
        persisted.assert_awaited_once_with(result)
        assert gate_events == [
            "enter:stale_bond_recovery",
            "exit:stale_bond_recovery",
        ]

    async def test_cancellation_waits_for_preflight_disconnect_before_gate_exit(
        self, hass: HomeAssistant
    ) -> None:
        fresh = AdvertisementEvidence(status=FreshnessStatus.FRESH, age_seconds=1.0)
        disconnect_started = asyncio.Event()
        release_disconnect = asyncio.Event()
        gate_events: list[str] = []
        client = _client()

        async def disconnect() -> None:
            disconnect_started.set()
            await release_disconnect.wait()

        client.disconnect.side_effect = disconnect

        @contextlib.asynccontextmanager
        async def transport_gate(operation: str):
            gate_events.append(f"enter:{operation}")
            try:
                yield
            finally:
                gate_events.append(f"exit:{operation}")

        with (
            patch(
                f"{_RECOVERY}.async_wait_for_advertisement",
                AsyncMock(return_value=(fresh, MagicMock())),
            ),
            patch(
                "bleak_retry_connector.establish_connection",
                AsyncMock(return_value=client),
            ),
            patch(f"{_RECOVERY}.async_path_for_source", return_value=_local_path()),
            patch(
                f"{_RECOVERY}.async_verify_authenticated_access",
                AsyncMock(
                    return_value=_bond(
                        BondVerificationStatus.AUTH_FAILED, "preflight"
                    )
                ),
            ),
        ):
            task = asyncio.create_task(
                async_recover_local_bond(
                    hass,
                    address=TEST_ADDRESS,
                    name="Bed",
                    offer=self._offer(),
                    bed_type=BED_TYPE_OKIN_UUID,
                    protocol_variant=None,
                    transport_operation=transport_gate,
                )
            )
            await disconnect_started.wait()
            task.cancel()
            await asyncio.sleep(0)

            assert gate_events == ["enter:stale_bond_recovery"]

            release_disconnect.set()
            with pytest.raises(asyncio.CancelledError):
                await task

        assert gate_events == [
            "enter:stale_bond_recovery",
            "exit:stale_bond_recovery",
        ]

    async def test_an_ineligible_offer_never_touches_anything(
        self, hass: HomeAssistant
    ) -> None:
        with (
            patch(f"{_RECOVERY}.async_wait_for_advertisement") as wait,
            patch(f"{_RECOVERY}.async_remove_local_bond") as removal,
        ):
            result = await async_recover_local_bond(
                hass,
                address=TEST_ADDRESS,
                name="Bed",
                offer=RecoveryOffer(eligibility=RecoveryEligibility.NOT_LOCAL),
                bed_type=BED_TYPE_OKIN_UUID,
                protocol_variant=None,
            )
        wait.assert_not_called()
        removal.assert_not_called()
        assert result.outcome is OperationOutcome.UNPAIR_FAILED

    async def test_a_bond_that_vanished_during_the_preflight_is_not_removed(
        self, hass: HomeAssistant
    ) -> None:
        """The record was chosen before the preflight connected and disconnected.

        BlueZ object paths are deterministic and nothing here locks out other
        D-Bus clients, so the approved record has to be re-confirmed rather than
        trusted across that window.
        """
        fresh = AdvertisementEvidence(status=FreshnessStatus.FRESH, age_seconds=1.0)
        with (
            patch(
                f"{_RECOVERY}.async_wait_for_advertisement",
                AsyncMock(return_value=(fresh, MagicMock())),
            ),
            _patch_inventory(),
            patch(f"{_RECOVERY}.async_remove_local_bond") as removal,
            patch(
                "bleak_retry_connector.establish_connection",
                AsyncMock(return_value=_client()),
            ),
            patch(
                f"{_RECOVERY}.async_verify_authenticated_access",
                AsyncMock(return_value=_bond(BondVerificationStatus.AUTH_FAILED, "preflight")),
            ),
            patch(f"{_RECOVERY}.async_path_for_source", return_value=_local_path()),
        ):
            result = await async_recover_local_bond(
                hass,
                address=TEST_ADDRESS,
                name="Bed",
                offer=self._offer(),
                bed_type=BED_TYPE_OKIN_UUID,
                protocol_variant=None,
            )
        removal.assert_not_called()
        assert result.outcome is OperationOutcome.UNPAIR_FAILED
        assert result.detail == "bond_changed_before_removal"

    async def test_an_unreadable_host_before_removal_removes_nothing(
        self, hass: HomeAssistant
    ) -> None:
        """A read that never answered cannot authorize destroying anything."""
        fresh = AdvertisementEvidence(status=FreshnessStatus.FRESH, age_seconds=1.0)
        with (
            patch(
                f"{_RECOVERY}.async_wait_for_advertisement",
                AsyncMock(return_value=(fresh, MagicMock())),
            ),
            _patch_inventory(_record(), readable=False),
            patch(f"{_RECOVERY}.async_remove_local_bond") as removal,
            patch(
                "bleak_retry_connector.establish_connection",
                AsyncMock(return_value=_client()),
            ),
            patch(
                f"{_RECOVERY}.async_verify_authenticated_access",
                AsyncMock(return_value=_bond(BondVerificationStatus.AUTH_FAILED, "preflight")),
            ),
            patch(f"{_RECOVERY}.async_path_for_source", return_value=_local_path()),
        ):
            result = await async_recover_local_bond(
                hass,
                address=TEST_ADDRESS,
                name="Bed",
                offer=self._offer(),
                bed_type=BED_TYPE_OKIN_UUID,
                protocol_variant=None,
            )
        removal.assert_not_called()
        assert result.outcome is OperationOutcome.UNPAIR_UNCONFIRMED
        assert result.detail == "bond_unreadable_before_removal"

    async def test_a_pairing_error_still_verifies_the_link(
        self, hass: HomeAssistant
    ) -> None:
        """``pair()`` can create the bond and still raise waiting for its reply.

        The old bond is already gone by then, so reporting failure would clear
        the marker and make the next connection pair on top of a good new bond,
        which is the wedge this whole path exists to avoid. The auth-gated read
        decides, not the RPC.
        """
        fresh = AdvertisementEvidence(status=FreshnessStatus.FRESH, age_seconds=1.0)
        removed = BondRemovalResult(
            status=BondRemovalStatus.REMOVED, record=_record(), removed_at=_REMOVED_AT
        )
        recovery_client = _client()
        recovery_client.pair = AsyncMock(side_effect=TimeoutError("no reply"))
        with (
            patch(
                f"{_RECOVERY}.async_wait_for_advertisement",
                AsyncMock(return_value=(fresh, MagicMock())),
            ),
            patch(f"{_RECOVERY}.async_remove_local_bond", AsyncMock(return_value=removed)),
            patch(
                "bleak_retry_connector.establish_connection",
                AsyncMock(side_effect=[_client(), recovery_client]),
            ),
            patch(
                f"{_RECOVERY}.async_verify_authenticated_access",
                AsyncMock(
                    side_effect=[
                        _bond(BondVerificationStatus.AUTH_FAILED, "preflight"),
                        _bond(BondVerificationStatus.VERIFIED, "stale_bond_recovery"),
                    ]
                ),
            ),
            patch(f"{_RECOVERY}.async_path_for_source", return_value=_local_path()),
        ):
            result = await async_recover_local_bond(
                hass,
                address=TEST_ADDRESS,
                name="Bed",
                offer=self._offer(),
                bed_type=BED_TYPE_OKIN_UUID,
                protocol_variant=None,
            )
        recovery_client.pair.assert_awaited_once_with()
        assert result.succeeded

    async def test_a_pairing_error_with_no_proof_reports_that_error(
        self, hass: HomeAssistant
    ) -> None:
        """Nothing proved a bond, so the pairing failure is the real outcome."""
        fresh = AdvertisementEvidence(status=FreshnessStatus.FRESH, age_seconds=1.0)
        removed = BondRemovalResult(
            status=BondRemovalStatus.REMOVED, record=_record(), removed_at=_REMOVED_AT
        )
        recovery_client = _client()
        recovery_client.pair = AsyncMock(side_effect=TimeoutError("no reply"))
        with (
            patch(
                f"{_RECOVERY}.async_wait_for_advertisement",
                AsyncMock(return_value=(fresh, MagicMock())),
            ),
            patch(f"{_RECOVERY}.async_remove_local_bond", AsyncMock(return_value=removed)),
            patch(
                "bleak_retry_connector.establish_connection",
                AsyncMock(side_effect=[_client(), recovery_client]),
            ),
            patch(
                f"{_RECOVERY}.async_verify_authenticated_access",
                AsyncMock(
                    side_effect=[
                        _bond(BondVerificationStatus.AUTH_FAILED, "preflight"),
                        _bond(BondVerificationStatus.AUTH_FAILED, "stale_bond_recovery"),
                    ]
                ),
            ),
            patch(f"{_RECOVERY}.async_path_for_source", return_value=_local_path()),
        ):
            result = await async_recover_local_bond(
                hass,
                address=TEST_ADDRESS,
                name="Bed",
                offer=self._offer(),
                bed_type=BED_TYPE_OKIN_UUID,
                protocol_variant=None,
            )
        assert not result.succeeded
        assert result.detail is not None and "no reply" in result.detail
