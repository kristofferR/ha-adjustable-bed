"""Confirmed recovery from a stale bond stored on this Home Assistant host.

A bond can survive on the host while the bed no longer honours it: the bed was
factory reset, re-paired with a phone, or simply forgot. The link then connects
and every encrypted read fails, which looks identical to "pairing is broken".
The fix is to remove the host's copy and make a new one — but only ever with the
user's explicit say-so, and only when the evidence points at the host.

Three rules make that safe, and every one of them exists because getting it
wrong destroys something the user cannot easily get back.

**Only local authentication evidence counts.** A proxy keeps its own bond store
that the host cannot read, so an authentication failure carried by a proxy says
nothing about the host's BlueZ. Removing a host bond on that evidence would
delete state that was never involved. Unknown ownership is treated the same way:
not proven local means not eligible.

**Reachability is proven before anything is destroyed.** Removing first would
leave a sleeping bed with no bond and no way to make a new one until someone
walks over to it.

**Success means verified.** A new bond is only recorded when an
authentication-gated operation actually succeeded over the link. Anything else
leaves the repair open, because a repair that closes itself on an unproven fix
is worse than one that stays open.

Beds that grant one connection per pairing window are excluded entirely.
Removing their bond drops the link and the box will not grant another until it
is power-cycled, so a single background sequence cannot both remove the bond and
keep the link it was going to recover through. Those beds get guidance instead.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator, Awaitable, Callable, Coroutine
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from homeassistant.core import HomeAssistant

from .bluetooth_bond import (
    BondSelectionStatus,
    LocalBondRecord,
    async_read_local_bonds,
    async_remove_local_bond,
    select_local_bond,
)
from .bluetooth_freshness import (
    ADVERTISEMENT_WAIT_SECONDS,
    async_wait_for_advertisement,
)
from .bluetooth_transport import (
    ConnectionPath,
    TransportClass,
    async_path_for_source,
    client_source,
)
from .bond_verification import (
    BondEvidence,
    BondOwner,
    BondVerificationStatus,
    async_verify_authenticated_access,
    build_bond_context,
    has_evidence_backed_verifier,
)
from .const import (
    CONNECTION_PROFILES,
    DEFAULT_CONNECTION_PROFILE,
    grants_one_connection_per_pairing_window,
)
from .setup_operation import OperationOutcome, OperationResult, SetupAction

if TYPE_CHECKING:
    from bleak import BleakClient
    from bleak.backends.device import BLEDevice

_LOGGER = logging.getLogger(__name__)


class RecoveryEligibility(StrEnum):
    """Why a stale-bond recovery is or is not on offer."""

    ELIGIBLE = "eligible"
    NO_EVIDENCE = "no_evidence"
    NOT_LOCAL = "not_local"
    NO_BOND = "no_bond"
    AMBIGUOUS = "ambiguous"
    UNREADABLE = "unreadable"
    KEEPS_FIRST_LINK = "keeps_first_link"
    NO_VERIFIER = "no_verifier"
    UNKNOWN_SOURCE = "unknown_source"
    # A combined Dual Bed entry whose issue address could not be resolved to one
    # child descriptor. The caller owns that mapping and refuses rather than
    # guessing which side a destructive recovery should change.
    COMBINED_PAIR = "combined_pair"


@dataclass(frozen=True, slots=True)
class RecoveryOffer:
    """Whether recovery may be offered, and against which exact bond."""

    eligibility: RecoveryEligibility
    record: LocalBondRecord | None = None
    owner: BondOwner | None = None

    @property
    def is_eligible(self) -> bool:
        """Return True only when an exact host bond may be replaced."""
        return self.eligibility == RecoveryEligibility.ELIGIBLE and self.record is not None


def evidence_is_local_auth_failure(issue_data: dict[str, Any]) -> bool:
    """Return True when the repair was raised by a local authentication failure.

    Reads the flattened evidence the coordinator attaches to the issue. An issue
    raised before that existed carries none, which correctly reads as "not
    eligible" rather than as permission.
    """
    return (
        issue_data.get("evidence_status") == BondVerificationStatus.AUTH_FAILED.value
        and issue_data.get("evidence_transport") == TransportClass.LOCAL.value
    )


def evidence_is_proxy_auth_failure(issue_data: dict[str, Any]) -> bool:
    """Return True when a proxy carried an authentication failure.

    Only this combination makes a proxy-held stale bond the likely explanation:
    the route was a proxy *and* the bond it presented was refused. Knowing the
    route alone proves nothing. A proxy that merely failed to pair, timed out or
    could not find a characteristic has the ordinary causes and must keep the
    guided pairing retry rather than being sent to read-only guidance.
    """
    return (
        issue_data.get("evidence_status") == BondVerificationStatus.AUTH_FAILED.value
        and issue_data.get("evidence_transport") == TransportClass.PROXY.value
    )


async def async_recovery_offer(
    hass: HomeAssistant,
    *,
    address: str,
    issue_data: dict[str, Any],
    bed_type: str | None,
    protocol_variant: str | None,
) -> RecoveryOffer:
    """Decide whether a stale host bond may be replaced, and which one."""
    if grants_one_connection_per_pairing_window(bed_type or "", protocol_variant):
        # Removing the bond drops the only link this box will grant until it is
        # power-cycled, so recovery cannot both remove and reconnect.
        return RecoveryOffer(eligibility=RecoveryEligibility.KEEPS_FIRST_LINK)

    if not has_evidence_backed_verifier(bed_type, protocol_variant):
        return RecoveryOffer(eligibility=RecoveryEligibility.NO_VERIFIER)

    if not evidence_is_local_auth_failure(issue_data):
        transport = issue_data.get("evidence_transport")
        return RecoveryOffer(
            eligibility=(
                RecoveryEligibility.NOT_LOCAL
                if transport and transport != TransportClass.LOCAL.value
                else RecoveryEligibility.NO_EVIDENCE
            )
        )

    owner = BondOwner(
        transport=TransportClass.LOCAL,
        source=issue_data.get("evidence_source"),
        adapter=issue_data.get("evidence_adapter"),
    )
    if owner.source is None:
        return RecoveryOffer(
            eligibility=RecoveryEligibility.UNKNOWN_SOURCE,
            owner=owner,
        )

    inventory = await async_read_local_bonds(address)
    # The source is the adapter's stable MAC address. Once evidence records it,
    # never fall back to the reusable interface name (for example hci0), which
    # may belong to a replacement adapter now.
    selection = select_local_bond(inventory, owner_source=owner.source)
    if selection.status is BondSelectionStatus.UNREADABLE:
        return RecoveryOffer(eligibility=RecoveryEligibility.UNREADABLE, owner=owner)
    if selection.status is BondSelectionStatus.NO_BOND:
        return RecoveryOffer(eligibility=RecoveryEligibility.NO_BOND, owner=owner)
    if not selection.is_exact:
        return RecoveryOffer(eligibility=RecoveryEligibility.AMBIGUOUS, owner=owner)
    return RecoveryOffer(
        eligibility=RecoveryEligibility.ELIGIBLE, record=selection.record, owner=owner
    )


@dataclass(slots=True)
class _RecoveryState:
    """Cancellation boundary and progress of a destructive recovery transaction."""

    removal_started: bool = False
    removal_confirmed: bool = False


async def _async_await_task_completion[T](task: asyncio.Task[T]) -> T:
    """Wait for a task without forwarding cancellation from the current task."""
    while True:
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            if task.done():
                return task.result()


async def async_recover_local_bond(
    hass: HomeAssistant,
    *,
    address: str,
    name: str,
    offer: RecoveryOffer,
    bed_type: str | None,
    protocol_variant: str | None,
    transport_operation: Callable[[str], AbstractAsyncContextManager[None]] | None = None,
    on_verified: Callable[[OperationResult], Awaitable[None]] | None = None,
    on_bond_removed: Callable[[], Awaitable[None]] | None = None,
    report_action: Callable[[SetupAction], None] | None = None,
    report_progress: Callable[[float], None] | None = None,
    report_path: Callable[[ConnectionPath | None], None] | None = None,
) -> OperationResult:
    """Remove one exact host bond, pair again, and prove the new bond.

    Cancellation is honoured until removal begins. Once BlueZ may have removed
    the old bond, the transaction is allowed to finish so closing the Repairs
    dialog cannot strand the bed halfway through recovery.

    ``on_bond_removed`` invalidates whatever the caller persisted about the bond
    that was just removed, and runs whenever removal was confirmed but the
    replacement was not - ``on_verified`` overwrites the same state on the path
    where a new bond was proven.
    """
    if not offer.is_eligible:
        return OperationResult(
            outcome=OperationOutcome.UNPAIR_FAILED, detail=offer.eligibility
        )

    state = _RecoveryState()
    transaction = hass.async_create_task(
        _async_recovery_transaction(
            hass,
            address=address,
            name=name,
            offer=offer,
            bed_type=bed_type,
            protocol_variant=protocol_variant,
            transport_operation=transport_operation,
            report_action=report_action,
            report_progress=report_progress,
            report_path=report_path,
            state=state,
        ),
        eager_start=False,
    )
    try:
        result = await asyncio.shield(transaction)
    except asyncio.CancelledError:
        if not state.removal_started:
            transaction.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await transaction
            raise
        _LOGGER.info(
            "Finishing bond recovery for %s after the Repairs flow was cancelled",
            address,
        )
        result = await _async_await_task_completion(transaction)

    async def _persist_verified() -> None:
        assert on_verified is not None
        await on_verified(result)

    async def _persist_removal() -> None:
        assert on_bond_removed is not None
        await on_bond_removed()

    persist: Callable[[], Coroutine[Any, Any, None]] | None = None
    if result.succeeded:
        if on_verified is not None:
            persist = _persist_verified
    elif state.removal_confirmed and on_bond_removed is not None:
        # The old bond is gone and no new one was proven. Whatever the caller
        # recorded about the removed bond has to go with it, or the next
        # connection trusts a marker for a bond that no longer exists.
        persist = _persist_removal
    if persist is not None:
        persistence = hass.async_create_task(persist(), eager_start=False)
        try:
            await asyncio.shield(persistence)
        except asyncio.CancelledError:
            await _async_await_task_completion(persistence)
    return result


async def _async_recovery_transaction(
    hass: HomeAssistant,
    *,
    address: str,
    name: str,
    offer: RecoveryOffer,
    bed_type: str | None,
    protocol_variant: str | None,
    transport_operation: Callable[[str], AbstractAsyncContextManager[None]] | None,
    report_action: Callable[[SetupAction], None] | None,
    report_progress: Callable[[float], None] | None,
    report_path: Callable[[ConnectionPath | None], None] | None,
    state: _RecoveryState,
) -> OperationResult:
    """Run one serialized, source-pinned recovery transaction."""
    from .address_lock import async_get_connect_lock

    @contextlib.asynccontextmanager
    async def _transport_gate() -> AsyncIterator[None]:
        if transport_operation is not None:
            async with transport_operation("stale_bond_recovery"):
                yield
            return
        async with async_get_connect_lock(hass, address):
            yield

    def _report(action: SetupAction) -> None:
        if report_action is not None:
            report_action(action)

    assert offer.owner is not None
    target_source = offer.owner.source
    assert target_source is not None
    # Guaranteed by the ``is_eligible`` gate in ``async_recover_local_bond``.
    target = offer.record
    assert target is not None

    async with _transport_gate():
        _report(SetupAction.LOCATING)
        evidence, device = await async_wait_for_advertisement(
            hass,
            address,
            source=target_source,
            wait_timeout=ADVERTISEMENT_WAIT_SECONDS,
            on_progress=report_progress,
        )
        if not evidence.is_fresh or device is None:
            _LOGGER.info(
                "Not recovering the bond for %s: the bed is not advertising (%s)",
                address,
                evidence.status,
            )
            return OperationResult(
                outcome=OperationOutcome.NOT_ADVERTISING, detail=str(evidence.status)
            )

        # Re-prove the stale-bond diagnosis immediately before the destructive
        # action. If the existing bond works now, preserve it and close the
        # obsolete issue without asking BlueZ to remove anything.
        current_bond = await _async_connect_and_verify(
            hass,
            address=address,
            name=name,
            device=device,
            target_source=target_source,
            bed_type=bed_type,
            protocol_variant=protocol_variant,
            pair=False,
            operation="stale_bond_recovery_preflight",
            report_action=_report,
            report_path=report_path,
        )
        if isinstance(current_bond, OperationResult):
            return current_bond
        if current_bond.proves_bond:
            result = OperationResult(
                outcome=OperationOutcome.SUCCESS,
                payload=current_bond,
                path=bond_path(current_bond),
            )
            return result
        if current_bond.status is not BondVerificationStatus.AUTH_FAILED:
            return OperationResult(
                outcome=OperationOutcome.BOND_VERIFICATION_FAILED,
                detail="authentication_state_unconfirmed",
                payload=current_bond,
            )

        # The record was selected before the preflight, which has since waited
        # for an advertisement, connected, probed and disconnected. BlueZ object
        # paths are deterministic and this integration's locks do not exclude
        # other D-Bus clients, so an external one can remove and recreate a bond
        # on that same path in the interval. Confirm the approved bond is still
        # the bond about to be destroyed, while refusing is still free.
        confirmed = await async_read_local_bonds(address)
        if not confirmed.readable:
            _LOGGER.warning(
                "Not recovering the bond for %s: the host's bonds could not be "
                "re-read before removal (%s)",
                address,
                confirmed.status,
            )
            return OperationResult(
                outcome=OperationOutcome.UNPAIR_UNCONFIRMED,
                detail="bond_unreadable_before_removal",
            )
        latest = select_local_bond(confirmed, owner_source=target_source)
        if not latest.is_exact or latest.record is None or not latest.record.is_same_bond_as(target):
            _LOGGER.warning(
                "Not recovering the bond for %s: the approved BlueZ record "
                "changed before it could be removed (%s)",
                address,
                latest.status,
            )
            return OperationResult(
                outcome=OperationOutcome.UNPAIR_FAILED,
                detail="bond_changed_before_removal",
            )

        _report(SetupAction.UNPAIRING)
        state.removal_started = True
        removal = await async_remove_local_bond(latest.record)
        if not removal.succeeded:
            _LOGGER.warning(
                "Not recovering the bond for %s: removal failed (%s)",
                address,
                removal.error,
            )
            return OperationResult(
                outcome=(
                    OperationOutcome.UNPAIR_UNCONFIRMED
                    if removal.is_unconfirmed
                    else OperationOutcome.UNPAIR_FAILED
                ),
                detail=removal.error or str(removal.status),
                payload=removal,
            )
        # The bond the entry still points at is provably gone. Everything below
        # can fail, and the marker must not survive any of it: a marker that
        # says "bonded" makes the next connection skip pair=True on a device
        # that now has no bond, which just repeats the authentication failure.
        state.removal_confirmed = True
        # RemoveDevice invalidates the BlueZ Device1 object used by the
        # preflight connection. Require an advertisement after the RPC
        # completed so the reconnect receives a newly resolved BLEDevice. The
        # removal helper records that point before its follow-up object-tree
        # verification, which may itself overlap the advertisement we need.
        if removal.removed_at is None:
            return OperationResult(
                outcome=OperationOutcome.BOND_VERIFICATION_FAILED,
                detail="removal_completion_time_unavailable",
                payload=removal,
            )
        _report(SetupAction.LOCATING)
        evidence, device = await async_wait_for_advertisement(
            hass,
            address,
            source=target_source,
            seen_after=removal.removed_at,
            wait_timeout=ADVERTISEMENT_WAIT_SECONDS,
            on_progress=report_progress,
        )
        if not evidence.is_fresh or device is None:
            return OperationResult(
                outcome=OperationOutcome.BOND_VERIFICATION_FAILED,
                detail=f"post_removal_advertisement_{evidence.status}",
                payload=removal,
            )

        bond = await _async_connect_and_verify(
            hass,
            address=address,
            name=name,
            device=device,
            target_source=target_source,
            bed_type=bed_type,
            protocol_variant=protocol_variant,
            pair=True,
            operation="stale_bond_recovery",
            report_action=_report,
            report_path=report_path,
        )
        if isinstance(bond, OperationResult):
            return OperationResult(
                outcome=OperationOutcome.BOND_VERIFICATION_FAILED,
                detail=bond.detail,
                payload=bond.payload,
            )
        if not bond.proves_bond:
            return OperationResult(
                outcome=OperationOutcome.BOND_VERIFICATION_FAILED,
                detail=str(bond.status),
                payload=bond,
            )
        result = OperationResult(
            outcome=OperationOutcome.SUCCESS, payload=bond, path=bond_path(bond)
        )

    return result


async def _async_connect_and_verify(
    hass: HomeAssistant,
    *,
    address: str,
    name: str,
    device: BLEDevice,
    target_source: str,
    bed_type: str | None,
    protocol_variant: str | None,
    pair: bool,
    operation: str,
    report_action: Callable[[SetupAction], None],
    report_path: Callable[[ConnectionPath | None], None] | None,
) -> BondEvidence | OperationResult:
    """Connect through the intended host scanner and verify authentication."""
    from bleak import BleakClient
    from bleak_retry_connector import establish_connection

    client: BleakClient | None = None
    try:
        report_action(SetupAction.CONNECTING)
        client = await establish_connection(
            BleakClient,
            device,
            address,
            max_attempts=1,
            timeout=CONNECTION_PROFILES[DEFAULT_CONNECTION_PROFILE].connection_timeout,
            # HaBleakClientWrapper may reroute a scanner-specific BLEDevice
            # during connect. Pair only after the resulting source is proven.
            pair=False,
            use_services_cache=False,
        )

        actual_source = client_source(client)
        path = async_path_for_source(hass, actual_source) if actual_source else None
        if report_path is not None:
            report_path(path)
        if (
            actual_source != target_source
            or path is None
            or path.transport is not TransportClass.LOCAL
        ):
            return OperationResult(
                outcome=OperationOutcome.CONNECTION_FAILED,
                detail="unexpected_connection_source",
            )

        pair_error: Exception | None = None
        if pair:
            report_action(SetupAction.PAIRING)
            try:
                await client.pair()
            except Exception as err:  # noqa: BLE001 - the verifier decides
                # The RPC can create the bond and still raise, typically by
                # timing out waiting for its own reply. The link is usually
                # still up, so let the auth-gated read decide whether a bond
                # exists instead of discarding one that was just made. Giving up
                # here is not neutral: the old bond is already gone, so the
                # caller would clear the marker and the next connection would
                # pair on top of a good new bond - the wedge this path exists
                # to avoid.
                pair_error = err
                _LOGGER.warning(
                    "Pairing %s raised (%s); verifying whether a bond was made anyway",
                    name,
                    err,
                )

        report_action(SetupAction.VERIFYING_BOND)
        evidence = await async_verify_authenticated_access(
            client,
            bed_type=bed_type,
            protocol_variant=protocol_variant,
            path=path,
            operation=operation,
        )
        if pair_error is not None and not evidence.proves_bond:
            # Nothing proved a bond, so the pairing failure is the real outcome
            # and is more informative than an unproven verification.
            return OperationResult(
                outcome=OperationOutcome.CONNECTION_FAILED,
                detail=str(pair_error) or pair_error.__class__.__name__,
            )
        return evidence
    except Exception as err:  # noqa: BLE001 - a failure here is an outcome
        _LOGGER.warning("Bond recovery for %s failed: %s", name, err)
        return OperationResult(
            outcome=OperationOutcome.CONNECTION_FAILED,
            detail=str(err) or err.__class__.__name__,
        )
    finally:
        report_action(SetupAction.DISCONNECTING)
        if client is not None:
            disconnect = hass.async_create_task(
                client.disconnect(), eager_start=False
            )
            try:
                await asyncio.shield(disconnect)
            except asyncio.CancelledError:
                try:
                    await _async_await_task_completion(disconnect)
                except Exception:  # noqa: BLE001 - preserve cancellation
                    _LOGGER.debug("Disconnect after recovery failed", exc_info=True)
                raise
            except Exception:  # noqa: BLE001 - cleanup must not mask the result
                _LOGGER.debug("Disconnect after recovery failed", exc_info=True)


def bond_path(bond: Any) -> ConnectionPath | None:
    """Return a path describing where a verified bond ended up."""
    owner = getattr(bond, "owner", None)
    if owner is None or owner.source is None:
        return None
    return ConnectionPath(
        source=owner.source, transport=owner.transport, adapter=owner.adapter
    )


def recovery_context(bond: Any) -> dict[str, Any]:
    """Return the entry-data provenance for a bond created by recovery."""
    return build_bond_context(bond)
