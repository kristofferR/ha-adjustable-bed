"""Strict bond verification and durable bond provenance.

Two questions get conflated constantly and must not be:

*Is this link authenticated?* and *who owns the bond that authenticated it?*

The first is answered by actually exercising an authentication-gated operation.
Connecting is not evidence — the connect path deliberately keeps an unbonded
link — and neither is `client.pair()` returning, since a backend can report a
pairing request as sent without a bond ever forming. Only a read that would fail
on an unbonded link and did not fail counts.

The second is answered by the transport that carried that read. A bond made over
an ESPHome proxy lives on the proxy; a bond made over a host adapter lives in the
host's BlueZ. Recording which is why a later unpair can be safe (issue #459).

The authenticated verifier is deliberately four-valued. "Not an authentication error" is not
the same as "verified": a missing characteristic, a timeout or a generic GATT
error prove nothing either way, and treating them as success is how an entry ends
up marked bonded while the bed is still refusing every write.

Runtime behaviour for beds already configured is untouched. The coordinator
keeps its existing lenient handling, which exists because real hardware answers
this probe inconsistently. What changes is that a *new* bond marker, and any
destructive recovery, now requires positive evidence. Exact host-native stored
bond state is separate from authenticated access and never proves encryption or
authorizes stale-bond recovery by itself.
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from .ble_auth import is_ble_authentication_error
from .bluetooth_bond import BondSelectionStatus, async_read_local_bonds, select_local_bond
from .bluetooth_transport import ConnectionPath, TransportClass, async_clear_proxy_gatt_cache
from .const import (
    BED_TYPE_OKIMAT,
    BED_TYPE_OKIN_UUID,
    BED_TYPE_SLEEP_NUMBER,
    CONF_BLE_BOND_CONTEXT,
    DEVICE_INFO_CHARS,
    DEVICE_INFO_READ_TIMEOUT,
)
from .sleep_number_auth import async_read_sleep_number_session

if TYPE_CHECKING:
    from bleak import BleakClient

_LOGGER = logging.getLogger(__name__)


BOND_CONTEXT_VERSION = 1


class BondVerificationStatus(StrEnum):
    """How much a verification attempt actually established."""

    VERIFIED = "verified"
    NATIVE_OS_STATE = "native_os_state"
    NATIVE_ABSENT = "native_absent"
    AUTH_FAILED = "auth_failed"
    INCONCLUSIVE = "inconclusive"
    UNSUPPORTED = "unsupported"


class BondEvidenceKind(StrEnum):
    """Distinguish authenticated access from the host's stored native state."""

    AUTHENTICATED_ACCESS = "authenticated_access"
    NATIVE_OS_STATE = "native_os_state"


@dataclass(frozen=True, slots=True)
class BondOwner:
    """Which transport stores the bond in question."""

    transport: TransportClass = TransportClass.UNKNOWN
    source: str | None = None
    adapter: str | None = None

    @property
    def is_host(self) -> bool:
        """Return True only when the bond is provably on this host."""
        return self.transport is TransportClass.LOCAL

    @classmethod
    def from_path(cls, path: ConnectionPath | None) -> BondOwner:
        """Derive ownership from the path a verified operation travelled."""
        if path is None:
            return cls()
        return cls(transport=path.transport, source=path.source, adapter=path.adapter)

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-friendly view for diagnostics and entry data."""
        return {
            "transport": str(self.transport),
            "source": self.source,
            "adapter": self.adapter,
        }


@dataclass(frozen=True, slots=True)
class BondEvidence:
    """One observation about a bond, and what carried it."""

    status: BondVerificationStatus
    owner: BondOwner
    operation: str
    observed_at: str
    error: str | None = None
    kind: BondEvidenceKind = BondEvidenceKind.AUTHENTICATED_ACCESS
    # True when the failure also dropped a proxy's cached GATT table, so a
    # retry runs on rediscovered handles rather than the same stale ones.
    gatt_cache_cleared: bool = False

    @property
    def proves_bond(self) -> bool:
        """Return True only for a positively verified bond."""
        if self.kind is BondEvidenceKind.NATIVE_OS_STATE:
            return (
                self.status is BondVerificationStatus.NATIVE_OS_STATE
                and self.owner.is_host
            )
        return self.status is BondVerificationStatus.VERIFIED

    @property
    def proves_stale_host_bond(self) -> bool:
        """Return True when this is grounds to suspect a stale *host* bond.

        Requires both an explicit authentication failure and a transport we have
        proven is local. An authentication failure carried by a proxy says
        nothing about the host's BlueZ, and acting on it would delete a bond
        that was never involved (issue #459).
        """
        return (
            self.kind is BondEvidenceKind.AUTHENTICATED_ACCESS
            and self.status is BondVerificationStatus.AUTH_FAILED
            and self.owner.is_host
        )

    @property
    def proves_native_bond_absent(self) -> bool:
        """Distinguish readable absence from an unavailable native inventory."""
        return (
            self.kind is BondEvidenceKind.NATIVE_OS_STATE
            and self.status is BondVerificationStatus.NATIVE_ABSENT
            and self.owner.is_host
        )

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-friendly view for diagnostics."""
        return {
            "status": str(self.status),
            "owner": self.owner.as_dict(),
            "operation": self.operation,
            "observed_at": self.observed_at,
            "error": self.error,
            "kind": str(self.kind),
            "gatt_cache_cleared": self.gatt_cache_cleared,
        }


def _now() -> str:
    return datetime.now(UTC).isoformat()


async def async_verify_native_bond(
    address: str,
    *,
    path: ConnectionPath | None,
    operation: str,
) -> BondEvidence:
    """Confirm an exact stored bond on the actual local transport.

    Native state does not authenticate a GATT operation. ``paired=True`` with
    ``bonded=False`` may describe transient pairing and is not positive stored
    bond proof. Proxy/unknown paths cannot be checked through host BlueZ.
    """
    owner = BondOwner.from_path(path)

    def result(status: BondVerificationStatus, error: str | None = None) -> BondEvidence:
        return BondEvidence(
            status=status,
            owner=owner,
            operation=operation,
            observed_at=_now(),
            error=error,
            kind=BondEvidenceKind.NATIVE_OS_STATE,
        )

    if path is None or path.transport is not TransportClass.LOCAL:
        return result(BondVerificationStatus.UNSUPPORTED, "native_state_not_local")

    target = address.upper()
    source = path.source.upper()
    mac_pattern = r"(?:[0-9A-F]{2}:){5}[0-9A-F]{2}"
    if not re.fullmatch(mac_pattern, target) or not re.fullmatch(mac_pattern, source):
        return result(BondVerificationStatus.INCONCLUSIVE, "native_identity_unknown")
    if path.adapter is not None and not re.fullmatch(r"hci[0-9]+", path.adapter):
        return result(BondVerificationStatus.INCONCLUSIVE, "native_adapter_unknown")

    try:
        inventory = await async_read_local_bonds(target)
    except Exception as err:  # noqa: BLE001 - unavailable inventory is not proof
        return result(BondVerificationStatus.INCONCLUSIVE, str(err))

    selection = select_local_bond(
        inventory, owner_source=path.source, owner_adapter=path.adapter
    )
    record = selection.record
    if not selection.is_exact or record is None:
        return result(
            BondVerificationStatus.NATIVE_ABSENT
            if selection.status is BondSelectionStatus.NO_BOND
            else BondVerificationStatus.INCONCLUSIVE,
            f"native_bond_{selection.status}",
        )

    # The shared selector also serves legacy removal flows with looser fallback
    # rules. Native proof must independently bind every identity to this path.
    if (
        record.address.upper() != target
        or (record.adapter_address or "").upper() != source
        or not re.fullmatch(r"/org/bluez/hci[0-9]+", record.adapter_path)
        or (
            path.adapter is not None
            and record.adapter_path != f"/org/bluez/{path.adapter}"
        )
        or record.device_path
        != f"{record.adapter_path}/dev_{target.replace(':', '_')}"
    ):
        return result(BondVerificationStatus.INCONCLUSIVE, "native_identity_mismatch")
    if not record.bonded:
        return result(BondVerificationStatus.NATIVE_ABSENT, "native_bond_not_stored")

    return result(BondVerificationStatus.NATIVE_OS_STATE)


def has_evidence_backed_verifier(bed_type: str | None, protocol_variant: str | None) -> bool:
    """Return True when this protocol has a known authentication-gated read.

    The standard Device Information model-number read is known to be bond-gated
    for the Okin UUID protocol and its legacy alias. Requiring pairing is not
    sufficient evidence: other protocols gate a different characteristic, so a
    successful model-number read would prove nothing about their bond.
    """
    # Sleep Number's Auth read is encryption-gated in #574. Its response must
    # also be a usable session UUID; a successful read of two zero bytes (#565)
    # does not authenticate a session.
    return bed_type in (BED_TYPE_OKIMAT, BED_TYPE_OKIN_UUID, BED_TYPE_SLEEP_NUMBER)


async def async_verify_authenticated_access(
    client: BleakClient,
    *,
    bed_type: str | None,
    protocol_variant: str | None,
    path: ConnectionPath | None,
    operation: str,
) -> BondEvidence:
    """Exercise an authentication-gated read and report exactly what it showed."""
    owner = BondOwner.from_path(path)

    if not has_evidence_backed_verifier(bed_type, protocol_variant):
        return BondEvidence(
            status=BondVerificationStatus.UNSUPPORTED,
            owner=owner,
            operation=operation,
            observed_at=_now(),
        )

    if client is None or not getattr(client, "is_connected", False):
        return BondEvidence(
            status=BondVerificationStatus.INCONCLUSIVE,
            owner=owner,
            operation=operation,
            observed_at=_now(),
            error="not_connected",
        )

    try:
        if bed_type == BED_TYPE_SLEEP_NUMBER:
            await async_read_sleep_number_session(client)
        else:
            await asyncio.wait_for(
                client.read_gatt_char(DEVICE_INFO_CHARS["model_number"]),
                DEVICE_INFO_READ_TIMEOUT,
            )
    except Exception as err:  # noqa: BLE001 - the failure mode is the result
        if is_ble_authentication_error(err):
            return BondEvidence(
                status=BondVerificationStatus.AUTH_FAILED,
                owner=owner,
                operation=operation,
                observed_at=_now(),
                error=str(err),
                # Stale proxy handles fail exactly like a missing bond.
                gatt_cache_cleared=await async_clear_proxy_gatt_cache(client, path),
            )
        # A timeout, an absent characteristic or a generic GATT error tells us
        # nothing. The OKIN CST receiver, for one, simply never answers this
        # read even when perfectly bonded.
        _LOGGER.debug("Bond verification for %s was inconclusive: %s", operation, err)
        return BondEvidence(
            status=BondVerificationStatus.INCONCLUSIVE,
            owner=owner,
            operation=operation,
            observed_at=_now(),
            error=str(err),
        )

    return BondEvidence(
        status=BondVerificationStatus.VERIFIED,
        owner=owner,
        operation=operation,
        observed_at=_now(),
    )


def bond_context_matches(stored: Any, candidate: dict[str, Any]) -> bool:
    """Return True when two contexts describe the same bond owner.

    Compares only the identity of the owner. ``verified_at`` moves every time a
    bond is re-proven, so comparing whole contexts would report a change on
    every reconnect and rewrite the config entry for nothing.
    """
    if not isinstance(stored, dict):
        return False
    keys = ("version", "transport", "source", "adapter")
    return all(stored.get(key) == candidate.get(key) for key in keys)


def build_bond_context(evidence: BondEvidence) -> dict[str, Any]:
    """Return the entry-data provenance record for a verified bond.

    Raises:
        ValueError: the evidence does not prove a bond. Provenance is what later
            authorizes a host-side removal, so recording it from an inconclusive
            or unsupported observation would manufacture permission out of
            something that established nothing.
    """
    if not evidence.proves_bond:
        raise ValueError(
            f"refusing to record bond provenance from {evidence.status} evidence"
        )
    context = {
        "version": BOND_CONTEXT_VERSION,
        "transport": str(evidence.owner.transport),
        "source": evidence.owner.source,
        "adapter": evidence.owner.adapter,
        "verification": evidence.operation,
        "verified_at": evidence.observed_at,
    }
    if evidence.kind is BondEvidenceKind.NATIVE_OS_STATE:
        context["evidence_kind"] = str(evidence.kind)
    return context


def bond_owner_from_entry(entry_data: dict[str, Any] | Any) -> BondOwner:
    """Return the recorded bond owner, or an unknown owner.

    An entry written before provenance existed carries only a boolean, so its
    owner is genuinely unknown. That must stay unknown rather than defaulting to
    "local": defaulting would let a legacy entry authorize a host-side unpair for
    a bond that may well live on a proxy.
    """
    context = None
    try:
        context = entry_data.get(CONF_BLE_BOND_CONTEXT)
    except AttributeError:
        return BondOwner()
    if not isinstance(context, dict):
        return BondOwner()
    transport = context.get("transport")
    try:
        transport_class = TransportClass(transport)
    except (ValueError, TypeError):
        # TypeError covers an unhashable stored value; both mean the same thing
        # here, and provenance that cannot be read must never read as local.
        transport_class = TransportClass.UNKNOWN
    return BondOwner(
        transport=transport_class,
        source=context.get("source"),
        adapter=context.get("adapter"),
    )
