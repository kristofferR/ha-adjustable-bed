"""Tests for strict bond verification and bond provenance (issues #459, #461)."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from bleak.exc import BleakError

from custom_components.adjustable_bed.bluetooth_bond import (
    BluezReadStatus,
    LocalBondInventory,
    LocalBondRecord,
)
from custom_components.adjustable_bed.bluetooth_transport import (
    ConnectionPath,
    TransportClass,
)
from custom_components.adjustable_bed.bond_verification import (
    CONF_BLE_BOND_CONTEXT,
    BondEvidence,
    BondEvidenceKind,
    BondOwner,
    BondVerificationStatus,
    async_verify_authenticated_access,
    async_verify_native_bond,
    bond_context_matches,
    bond_owner_from_entry,
    build_bond_context,
    has_evidence_backed_verifier,
)
from custom_components.adjustable_bed.const import (
    BED_TYPE_LINAK,
    BED_TYPE_LOGICDATA,
    BED_TYPE_OKIMAT,
    BED_TYPE_OKIN_CST,
    BED_TYPE_OKIN_UUID,
    BED_TYPE_SLEEP_NUMBER,
    BED_TYPE_SLEEP_NUMBER_MCR,
    BED_TYPE_VIBRADORM,
    BED_TYPE_VIBRADORM_APP,
    SLEEP_NUMBER_AUTH_CHAR_UUID,
)

_LOCAL = ConnectionPath(source="hci0", transport=TransportClass.LOCAL, adapter="hci0")
_PROXY = ConnectionPath(source="proxy", transport=TransportClass.PROXY)
_TARGET = "AA:BB:CC:DD:EE:FF"
_NATIVE_PATH = ConnectionPath(
    source="11:22:33:44:55:66", transport=TransportClass.LOCAL, adapter="hci0"
)
_NATIVE_RECORD = LocalBondRecord(
    address=_TARGET,
    device_path="/org/bluez/hci0/dev_AA_BB_CC_DD_EE_FF",
    adapter_path="/org/bluez/hci0",
    adapter_address=_NATIVE_PATH.source,
    bonded=True,
)


def _client(read: Any = None) -> MagicMock:
    client = MagicMock()
    client.is_connected = True
    client.read_gatt_char = AsyncMock(
        side_effect=read if isinstance(read, Exception) else None,
        return_value=b"model",
    )
    return client


class TestVerifierApplicability:
    """A read only proves a bond where the read is known to be bond-gated."""

    @pytest.mark.parametrize("bed_type", [BED_TYPE_OKIMAT, BED_TYPE_OKIN_UUID])
    def test_okin_uuid_protocol_has_a_verifier(self, bed_type: str) -> None:
        assert has_evidence_backed_verifier(bed_type, None)

    def test_a_bed_that_never_bonds_has_no_verifier(self) -> None:
        """A successful read on an unbonded protocol proves nothing at all."""
        assert not has_evidence_backed_verifier(BED_TYPE_LINAK, None)

    def test_okin_cst_has_no_positive_verifier(self) -> None:
        assert not has_evidence_backed_verifier(BED_TYPE_OKIN_CST, None)

    def test_pairing_requirement_alone_does_not_supply_a_verifier(self) -> None:
        """Logicdata gates its command characteristic, not this DIS read."""
        assert not has_evidence_backed_verifier(BED_TYPE_LOGICDATA, None)

    async def test_no_verifier_reports_unsupported_without_reading(self) -> None:
        client = _client()
        evidence = await async_verify_authenticated_access(
            client,
            bed_type=BED_TYPE_LINAK,
            protocol_variant=None,
            path=_LOCAL,
            operation="setup_pairing",
        )
        assert evidence.status is BondVerificationStatus.UNSUPPORTED
        assert not evidence.proves_bond
        client.read_gatt_char.assert_not_called()

    @pytest.mark.parametrize("bed_type", [BED_TYPE_VIBRADORM, BED_TYPE_VIBRADORM_APP])
    async def test_native_profiles_do_not_expand_authenticated_whitelist(
        self, bed_type: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        inventory_read = AsyncMock()
        monkeypatch.setattr(
            "custom_components.adjustable_bed.bond_verification.async_read_local_bonds",
            inventory_read,
        )
        client = _client()
        evidence = await async_verify_authenticated_access(
            client, bed_type=bed_type, protocol_variant=None,
            path=_NATIVE_PATH, operation="setup_pairing",
        )
        assert evidence.kind is BondEvidenceKind.AUTHENTICATED_ACCESS
        assert evidence.status is BondVerificationStatus.UNSUPPORTED
        assert not has_evidence_backed_verifier(bed_type, None)
        client.read_gatt_char.assert_not_called()
        inventory_read.assert_not_called()


class TestNativeBondVerification:
    """Native proof binds stored state to the exact live host path, never GATT auth."""

    @pytest.fixture
    def inventory_read(self, monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
        read = AsyncMock(return_value=LocalBondInventory(BluezReadStatus.OK, (_NATIVE_RECORD,)))
        monkeypatch.setattr(
            "custom_components.adjustable_bed.bond_verification.async_read_local_bonds", read
        )
        return read

    @pytest.mark.parametrize("adapter", ["hci0", None])
    async def test_exact_native_state_preserves_owner_without_claiming_authentication(
        self, inventory_read: AsyncMock, adapter: str | None
    ) -> None:
        path = replace(_NATIVE_PATH, source=_NATIVE_PATH.source.lower(), adapter=adapter)
        inventory_read.return_value = LocalBondInventory(
            BluezReadStatus.OK,
            (replace(_NATIVE_RECORD, address=_TARGET.lower(),
                     adapter_address=_NATIVE_PATH.source.lower()),),
        )
        evidence = await async_verify_native_bond(
            _TARGET.lower(), path=path, operation="native_pairing_completion"
        )
        assert evidence.status is BondVerificationStatus.NATIVE_OS_STATE
        assert evidence.status is not BondVerificationStatus.VERIFIED
        assert evidence.kind is BondEvidenceKind.NATIVE_OS_STATE
        assert evidence.owner == BondOwner.from_path(path)
        assert evidence.proves_bond
        assert not evidence.proves_stale_host_bond
        inventory_read.assert_awaited_once_with(_TARGET)
        context = build_bond_context(evidence)
        assert context["evidence_kind"] == "native_os_state"
        assert context["source"] == path.source
        assert context["adapter"] == adapter
        assert context["verification"] == "native_pairing_completion"
        assert bond_owner_from_entry({CONF_BLE_BOND_CONTEXT: context}) == evidence.owner
        assert evidence.as_dict()["kind"] == "native_os_state"

    @pytest.mark.parametrize("path", [None, _PROXY, ConnectionPath(source="unknown")])
    async def test_nonlocal_paths_never_query_host_inventory(
        self, inventory_read: AsyncMock, path: ConnectionPath | None
    ) -> None:
        evidence = await async_verify_native_bond(_TARGET, path=path, operation="pairing")
        assert evidence.status is BondVerificationStatus.UNSUPPORTED
        assert evidence.kind is BondEvidenceKind.NATIVE_OS_STATE
        assert not evidence.proves_bond
        assert not evidence.proves_stale_host_bond
        inventory_read.assert_not_called()

    @pytest.mark.parametrize(
        ("address", "path"),
        [
            (_TARGET, _LOCAL),
            (_TARGET, replace(_NATIVE_PATH, source="")),
            (_TARGET, replace(_NATIVE_PATH, adapter="/org/bluez/hci0")),
            ("not-a-mac", _NATIVE_PATH),
        ],
    )
    async def test_unknown_identity_never_uses_sole_bond_fallback(
        self, inventory_read: AsyncMock, address: str, path: ConnectionPath
    ) -> None:
        evidence = await async_verify_native_bond(address, path=path, operation="pairing")
        assert evidence.status is BondVerificationStatus.INCONCLUSIVE
        assert not evidence.proves_bond
        inventory_read.assert_not_called()

    @pytest.mark.parametrize(
        "record",
        [
            replace(_NATIVE_RECORD, address="AA:BB:CC:DD:EE:00"),
            replace(_NATIVE_RECORD, adapter_address="11:22:33:44:55:00"),
            replace(_NATIVE_RECORD, adapter_address=None),
            replace(_NATIVE_RECORD, adapter_path="/org/bluez/hci1",
                    device_path="/org/bluez/hci1/dev_AA_BB_CC_DD_EE_FF"),
            replace(_NATIVE_RECORD, adapter_path="/not/bluez/hci0"),
            replace(_NATIVE_RECORD, device_path="/org/bluez/hci0/dev_AA_BB_CC_DD_EE_00"),
        ],
    )
    async def test_address_adapter_and_actual_object_must_all_match(
        self, inventory_read: AsyncMock, record: LocalBondRecord
    ) -> None:
        inventory_read.return_value = LocalBondInventory(BluezReadStatus.OK, (record,))
        evidence = await async_verify_native_bond(_TARGET, path=_NATIVE_PATH, operation="pairing")
        assert evidence.status is BondVerificationStatus.INCONCLUSIVE
        assert not evidence.proves_bond
        assert not evidence.proves_stale_host_bond
        with pytest.raises(ValueError):
            build_bond_context(evidence)

    async def test_two_adapters_select_only_the_live_source(self, inventory_read: AsyncMock) -> None:
        unrelated = replace(
            _NATIVE_RECORD, adapter_address="11:22:33:44:55:00",
            adapter_path="/org/bluez/hci1", device_path="/org/bluez/hci1/dev_AA_BB_CC_DD_EE_FF",
        )
        inventory_read.return_value = LocalBondInventory(
            BluezReadStatus.OK, (unrelated, _NATIVE_RECORD)
        )
        evidence = await async_verify_native_bond(_TARGET, path=_NATIVE_PATH, operation="pairing")
        assert evidence.proves_bond
        assert evidence.owner.source == _NATIVE_PATH.source

    @pytest.mark.parametrize(
        "inventory",
        [
            LocalBondInventory(BluezReadStatus.UNAVAILABLE, (_NATIVE_RECORD,)),
            LocalBondInventory(BluezReadStatus.OK),
            LocalBondInventory(BluezReadStatus.OK, (_NATIVE_RECORD, _NATIVE_RECORD)),
            LocalBondInventory(BluezReadStatus.OK, (replace(_NATIVE_RECORD, bonded=False),)),
        ],
    )
    async def test_unreadable_absent_duplicate_and_negative_state_are_not_proof(
        self, inventory_read: AsyncMock, inventory: LocalBondInventory
    ) -> None:
        inventory_read.return_value = inventory
        evidence = await async_verify_native_bond(_TARGET, path=_NATIVE_PATH, operation="pairing")
        assert evidence.status is BondVerificationStatus.INCONCLUSIVE
        assert not evidence.proves_bond
        assert not evidence.proves_stale_host_bond

    async def test_paired_without_bonded_is_not_positive_stored_bond_proof(
        self, inventory_read: AsyncMock
    ) -> None:
        transient = replace(_NATIVE_RECORD, paired=True, bonded=False)
        assert transient.has_bond  # The shared legacy inventory semantics remain unchanged.
        inventory_read.return_value = LocalBondInventory(BluezReadStatus.OK, (transient,))
        evidence = await async_verify_native_bond(_TARGET, path=_NATIVE_PATH, operation="pairing")
        assert evidence.status is BondVerificationStatus.INCONCLUSIVE
        assert evidence.error == "native_bond_not_stored"
        assert not evidence.proves_bond
        assert not evidence.proves_stale_host_bond

    async def test_read_failure_is_inconclusive_and_cancellation_propagates(
        self, inventory_read: AsyncMock
    ) -> None:
        inventory_read.side_effect = OSError("BlueZ unavailable")
        evidence = await async_verify_native_bond(_TARGET, path=_NATIVE_PATH, operation="pairing")
        assert evidence.status is BondVerificationStatus.INCONCLUSIVE
        assert not evidence.proves_stale_host_bond
        inventory_read.side_effect = asyncio.CancelledError
        with pytest.raises(asyncio.CancelledError):
            await async_verify_native_bond(_TARGET, path=_NATIVE_PATH, operation="pairing")

    @pytest.mark.parametrize(
        ("status", "kind", "path"),
        [
            (BondVerificationStatus.AUTH_FAILED, BondEvidenceKind.NATIVE_OS_STATE, _NATIVE_PATH),
            (BondVerificationStatus.VERIFIED, BondEvidenceKind.NATIVE_OS_STATE, _NATIVE_PATH),
            (BondVerificationStatus.NATIVE_OS_STATE, BondEvidenceKind.AUTHENTICATED_ACCESS,
             _NATIVE_PATH),
            (BondVerificationStatus.NATIVE_OS_STATE, BondEvidenceKind.NATIVE_OS_STATE, _PROXY),
        ],
    )
    def test_mixed_kinds_cannot_manufacture_proof_or_authorize_stale_recovery(
        self, status: BondVerificationStatus, kind: BondEvidenceKind, path: ConnectionPath
    ) -> None:
        evidence = BondEvidence(status, BondOwner.from_path(path), "pairing", "now", kind=kind)
        assert not evidence.proves_bond
        assert not evidence.proves_stale_host_bond
        with pytest.raises(ValueError):
            build_bond_context(evidence)

    def test_authenticated_context_shape_and_owner_matching_remain_unchanged(self) -> None:
        evidence = BondEvidence(
            BondVerificationStatus.VERIFIED, BondOwner.from_path(_NATIVE_PATH), "auth_read", "now"
        )
        assert evidence.kind is BondEvidenceKind.AUTHENTICATED_ACCESS
        context = build_bond_context(evidence)
        assert context == {
            "version": 1, "transport": "local", "source": _NATIVE_PATH.source,
            "adapter": "hci0", "verification": "auth_read", "verified_at": "now",
        }
        native = build_bond_context(replace(
            evidence, status=BondVerificationStatus.NATIVE_OS_STATE,
            kind=BondEvidenceKind.NATIVE_OS_STATE,
        ))
        assert bond_context_matches(context, native)
        assert not bond_context_matches(context, {**native, "source": "11:22:33:44:55:00"})


class TestVerificationOutcomes:
    """Four outcomes, because "not an auth error" is not "verified"."""

    @pytest.mark.parametrize("path", [_LOCAL, _PROXY])
    async def test_sleep_number_session_verifies_the_actual_transport(self, path) -> None:
        client = _client()
        client.read_gatt_char.return_value = bytes.fromhex("00112233445566778899aabbccddeeff")
        evidence = await async_verify_authenticated_access(
            client, bed_type=BED_TYPE_SLEEP_NUMBER, protocol_variant=None,
            path=path, operation="setup_pairing",
        )
        assert evidence.status is BondVerificationStatus.VERIFIED
        assert evidence.owner.source == path.source
        client.read_gatt_char.assert_awaited_once_with(SLEEP_NUMBER_AUTH_CHAR_UUID)
        assert not has_evidence_backed_verifier(BED_TYPE_SLEEP_NUMBER_MCR, None)

    @pytest.mark.parametrize("value", [b"", b"\x00\x00", bytes(15) + b"\x01"])
    async def test_sleep_number_invalid_auth_is_not_bond_proof(self, value: bytes) -> None:
        client = _client()
        client.read_gatt_char.return_value = value
        evidence = await async_verify_authenticated_access(
            client, bed_type=BED_TYPE_SLEEP_NUMBER, protocol_variant=None,
            path=_PROXY, operation="setup_pairing",
        )
        assert not evidence.proves_bond
        assert evidence.status is BondVerificationStatus.AUTH_FAILED

    async def test_sleep_number_connection_limit_does_not_invalidate_bond(self) -> None:
        client = _client()
        client.read_gatt_char.return_value = bytes(16)
        evidence = await async_verify_authenticated_access(
            client, bed_type=BED_TYPE_SLEEP_NUMBER, protocol_variant=None,
            path=_LOCAL, operation="setup_pairing",
        )
        assert evidence.status is BondVerificationStatus.INCONCLUSIVE
        assert not evidence.proves_bond
        assert not evidence.proves_stale_host_bond

    async def test_sleep_number_encryption_error_is_a_failed_bond(self) -> None:
        evidence = await async_verify_authenticated_access(
            _client(BleakError("error=15 description=Insufficient encryption")),
            bed_type=BED_TYPE_SLEEP_NUMBER, protocol_variant=None,
            path=_PROXY, operation="setup_pairing",
        )
        assert evidence.status is BondVerificationStatus.AUTH_FAILED
        assert evidence.owner.transport is TransportClass.PROXY

    async def test_a_successful_read_verifies_the_bond(self) -> None:
        evidence = await async_verify_authenticated_access(
            _client(),
            bed_type=BED_TYPE_OKIMAT,
            protocol_variant=None,
            path=_LOCAL,
            operation="setup_pairing",
        )
        assert evidence.status is BondVerificationStatus.VERIFIED
        assert evidence.proves_bond

    async def test_an_authentication_error_is_a_definite_failure(self) -> None:
        evidence = await async_verify_authenticated_access(
            _client(BleakError("Insufficient authentication")),
            bed_type=BED_TYPE_OKIMAT,
            protocol_variant=None,
            path=_LOCAL,
            operation="setup_pairing",
        )
        assert evidence.status is BondVerificationStatus.AUTH_FAILED
        assert not evidence.proves_bond

    @pytest.mark.parametrize(
        "error",
        [
            TimeoutError("no answer"),
            BleakError("Characteristic not found"),
            OSError("link lost"),
        ],
    )
    async def test_other_failures_are_inconclusive(self, error: Exception) -> None:
        """The OKIN CST receiver never answers this read even when bonded."""
        evidence = await async_verify_authenticated_access(
            _client(error),
            bed_type=BED_TYPE_OKIMAT,
            protocol_variant=None,
            path=_LOCAL,
            operation="setup_pairing",
        )
        assert evidence.status is BondVerificationStatus.INCONCLUSIVE
        assert not evidence.proves_bond

    async def test_a_disconnected_client_is_inconclusive(self) -> None:
        client = _client()
        client.is_connected = False
        evidence = await async_verify_authenticated_access(
            client,
            bed_type=BED_TYPE_OKIMAT,
            protocol_variant=None,
            path=_LOCAL,
            operation="setup_pairing",
        )
        assert evidence.status is BondVerificationStatus.INCONCLUSIVE


class TestStaleHostBondEvidence:
    """Only a local authentication failure may implicate the host's bond."""

    def _evidence(
        self, status: BondVerificationStatus, path: ConnectionPath | None
    ) -> BondEvidence:
        return BondEvidence(
            status=status,
            owner=BondOwner.from_path(path),
            operation="runtime_gatt_access",
            observed_at="2026-07-27T00:00:00+00:00",
        )

    def test_a_local_authentication_failure_implicates_the_host_bond(self) -> None:
        evidence = self._evidence(BondVerificationStatus.AUTH_FAILED, _LOCAL)
        assert evidence.proves_stale_host_bond

    def test_a_proxy_authentication_failure_does_not(self) -> None:
        """Host BlueZ was not involved, so its bond is not the suspect."""
        evidence = self._evidence(BondVerificationStatus.AUTH_FAILED, _PROXY)
        assert not evidence.proves_stale_host_bond

    def test_an_unknown_transport_does_not(self) -> None:
        evidence = self._evidence(BondVerificationStatus.AUTH_FAILED, None)
        assert not evidence.proves_stale_host_bond

    @pytest.mark.parametrize(
        "status",
        [
            BondVerificationStatus.INCONCLUSIVE,
            BondVerificationStatus.UNSUPPORTED,
            BondVerificationStatus.VERIFIED,
        ],
    )
    def test_nothing_but_an_authentication_failure_implicates_a_bond(
        self, status: BondVerificationStatus
    ) -> None:
        """Timeouts, missing characteristics and successes are not evidence."""
        assert not self._evidence(status, _LOCAL).proves_stale_host_bond


class TestProvenance:
    """A legacy marker must never authorize a destructive action."""

    def test_unproven_evidence_cannot_become_provenance(self) -> None:
        """Provenance authorizes removal, so it needs a positive verification."""
        for status in (
            BondVerificationStatus.INCONCLUSIVE,
            BondVerificationStatus.UNSUPPORTED,
            BondVerificationStatus.AUTH_FAILED,
        ):
            evidence = BondEvidence(
                status=status,
                owner=BondOwner.from_path(_LOCAL),
                operation="setup_pairing",
                observed_at="2026-07-27T00:00:00+00:00",
            )
            with pytest.raises(ValueError):
                build_bond_context(evidence)

    def test_the_same_owner_is_recognised_across_observations(self) -> None:
        """verified_at moves every time; the owner is what decides a rewrite."""
        def _context(when: str) -> dict:
            return build_bond_context(
                BondEvidence(
                    status=BondVerificationStatus.VERIFIED,
                    owner=BondOwner.from_path(_LOCAL),
                    operation="runtime_authenticated_read",
                    observed_at=when,
                )
            )

        first = _context("2026-07-27T00:00:00+00:00")
        later = _context("2026-07-27T09:30:00+00:00")
        assert first != later
        assert bond_context_matches(first, later)

    def test_a_different_owner_is_not_a_match(self) -> None:
        verified = build_bond_context(
            BondEvidence(
                status=BondVerificationStatus.VERIFIED,
                owner=BondOwner.from_path(_LOCAL),
                operation="setup_pairing",
                observed_at="2026-07-27T00:00:00+00:00",
            )
        )
        moved = build_bond_context(
            BondEvidence(
                status=BondVerificationStatus.VERIFIED,
                owner=BondOwner.from_path(_PROXY),
                operation="setup_pairing",
                observed_at="2026-07-27T00:00:00+00:00",
            )
        )
        assert not bond_context_matches(verified, moved)
        assert not bond_context_matches(None, verified)

    def test_a_verified_bond_records_its_owner(self) -> None:
        evidence = BondEvidence(
            status=BondVerificationStatus.VERIFIED,
            owner=BondOwner.from_path(_LOCAL),
            operation="setup_pairing",
            observed_at="2026-07-27T00:00:00+00:00",
        )
        context = build_bond_context(evidence)
        assert context["transport"] == "local"
        assert context["source"] == "hci0"
        assert bond_owner_from_entry({CONF_BLE_BOND_CONTEXT: context}).is_host

    def test_a_legacy_entry_has_an_unknown_owner(self) -> None:
        """Entries written before provenance existed carry only a boolean."""
        owner = bond_owner_from_entry({"ble_bond_established": True})
        assert owner.transport is TransportClass.UNKNOWN
        assert not owner.is_host

    def test_a_proxy_bond_is_not_a_host_bond(self) -> None:
        context = build_bond_context(
            BondEvidence(
                status=BondVerificationStatus.VERIFIED,
                owner=BondOwner.from_path(_PROXY),
                operation="setup_pairing",
                observed_at="2026-07-27T00:00:00+00:00",
            )
        )
        assert not bond_owner_from_entry({CONF_BLE_BOND_CONTEXT: context}).is_host

    @pytest.mark.parametrize(
        "stored",
        [
            None,
            {},
            {"transport": "nonsense"},
            "not-a-dict",
            42,
            # An unhashable value raises TypeError rather than ValueError from
            # the enum lookup, which used to propagate instead of falling back.
            {"transport": ["local"]},
            {"transport": {"local": True}},
        ],
    )
    def test_malformed_provenance_is_unknown_not_local(self, stored: Any) -> None:
        owner = bond_owner_from_entry({CONF_BLE_BOND_CONTEXT: stored})
        assert not owner.is_host
