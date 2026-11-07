"""BLE bond and pairing state for the bed coordinator."""

# Each method annotates self as the coordinator so pyright checks its body
# against the full class. Pyright reports that annotation on a mixin as a
# general type issue, the only diagnostic this disables.
# pyright: reportGeneralTypeIssues=false

from __future__ import annotations

import asyncio
import contextlib
import logging
import sys
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from bleak import BleakClient
from bleak.backends.device import BLEDevice
from bleak.exc import BleakError
from homeassistant.components import bluetooth

from .address_lock import async_get_connect_lock
from .beds.vibradorm.app_state import ControlType
from .ble_auth import is_ble_authentication_error as _is_ble_authentication_error
from .ble_auth import is_ble_pairing_auth_failure
from .bluetooth_transport import TransportClass, async_clear_proxy_gatt_cache
from .bond_verification import (
    CONF_BLE_BOND_CONTEXT,
    BondEvidence,
    BondOwner,
    BondVerificationStatus,
    async_verify_native_bond,
    bond_context_matches,
    bond_owner_from_entry,
    build_bond_context,
)
from .command_scheduler import current_command_context
from .const import (
    BED_TYPE_FURNIMOVE,
    BED_TYPE_OKIN_CST,
    BED_TYPE_SLEEP_NUMBER,
    BED_TYPE_VIBRADORM_APP,
    CONF_BLE_BOND_ATTEMPTED_SOURCE,
    CONF_BLE_BOND_ESTABLISHED,
    CONF_BLE_BOND_MARKER_UNRELIABLE,
    CONF_VIBRADORM_APP_METADATA,
    CONF_VIBRADORM_APP_PROFILE,
    CONF_VIBRADORM_CONTROL_TYPE,
    CONF_VIBRADORM_VMAT_REMOTE,
    DEVICE_INFO_CHARS,
    DEVICE_INFO_READ_TIMEOUT,
    OKIN_CST_VARIANT_NECTAR_MOVE,
    RUNTIME_BOND_KEYS,
    VIBRADORM_APP_ONBOARDING_TIMEOUT_SECONDS,
    VIBRADORM_VMAT_ONBOARDING_TIMEOUT_SECONDS,
    connection_gated_by_bond,
    grants_one_connection_per_pairing_window,
    requires_pairing,
    requires_pairing_after_service_discovery,
    supports_runtime_authentication_recovery,
)
from .import_executor import async_import_modules
from .profiles.vibradorm import vibradorm_app_metadata_key
from .support_proxy_logs import capture_proxy_logs
from .unsupported import create_pairing_required_issue, delete_pairing_required_issue

if TYPE_CHECKING:
    from .coordinator import AdjustableBedCoordinator

# Log under the coordinator's own logger, as before the split.
_LOGGER = logging.getLogger(f"{__package__}.coordinator")

# How many successful paired connections to make while the always-pair latch is
# set before dropping it to re-test whether the bond persists again. Small
# enough that a bed moved to a bond-keeping adapter recovers quickly, large
# enough that a bed which genuinely loses bonds wastes an attempt only rarely.
BOND_LATCH_RETEST_AFTER = 10


class CoordinatorBondsMixin:
    """Bond verification, pairing attempts and bond bookkeeping."""

    @property
    def last_bond_evidence(self: AdjustableBedCoordinator) -> BondEvidence | None:
        """Return what the most recent authentication-gated check actually saw.

        Exposed so a repair can tell "this pairing was proven, and provenance is
        already recorded" from "nothing established an owner this time". The
        difference decides whether an existing provenance record is still
        trustworthy or has to be dropped.
        """
        return self._last_bond_evidence

    @property
    def pairing_supported(self: AdjustableBedCoordinator) -> bool | None:
        """Return whether the Bluetooth adapter supports pairing.

        None = not yet determined, True = supported, False = not supported.
        """
        return self._pairing_supported

    def _device_reports_existing_bond(self: AdjustableBedCoordinator, device: BLEDevice | None = None) -> bool:
        """Return True when HA/BlueZ reports this bed as already paired or bonded."""
        if self._bed_type == BED_TYPE_VIBRADORM_APP:
            # Cached discovery flags do not bind a stored bond to the live source.
            return False
        return any(
            state.get("paired") is True or state.get("bonded") is True
            for state in self._device_pairing_states(device)
        )

    def _device_pairing_states(self: AdjustableBedCoordinator, device: BLEDevice | None = None) -> list[dict[str, Any]]:
        """Return adapter-reported pairing flags for the available BLE device."""
        candidates: list[BLEDevice] = []
        if device is not None:
            candidates.append(device)

        try:
            current_device = bluetooth.async_ble_device_from_address(
                self.hass,
                self._address,
                connectable=True,
            )
        except Exception as err:
            _LOGGER.debug(
                "Could not inspect HA Bluetooth bond state for %s: %s",
                self._address,
                err,
            )
            current_device = None
        if current_device is not None and current_device not in candidates:
            candidates.append(current_device)

        states: list[dict[str, Any]] = []
        for candidate in candidates:
            raw_details = getattr(candidate, "details", None)
            if not isinstance(raw_details, dict):
                continue
            details: dict[str, Any] = raw_details
            raw_props = details.get("props")
            props: dict[str, Any] = raw_props if isinstance(raw_props, dict) else {}

            states.append(
                {
                    "source": details.get("source"),
                    "paired": props.get("Paired", details.get("paired")),
                    "bonded": props.get("Bonded", details.get("bonded")),
                    "trusted": props.get("Trusted", details.get("trusted")),
                    "address_type": props.get("AddressType", details.get("address_type")),
                }
            )
        return states

    def _record_bond_verification(
        self: AdjustableBedCoordinator,
        status: str,
        error: BaseException | None = None,
        attempt_details: dict[str, Any] | None = None,
    ) -> None:
        """Record the latest bond observation outcome for diagnostics."""
        result = {
            "status": status,
            "timestamp": datetime.now(UTC).isoformat(),
            "error": str(error) if error is not None else None,
            "error_type": type(error).__name__ if error is not None else None,
        }
        self._last_bond_verification = result
        if attempt_details is not None:
            pairing = attempt_details.get("pairing")
            if isinstance(pairing, dict):
                pairing["bond_verification"] = dict(result)

    def _persist_bond_flags(
        self: AdjustableBedCoordinator,
        *,
        established: bool | None = None,
        unreliable: bool | None = None,
        context: dict[str, Any] | None = None,
        profile_metadata: dict[str, str | None] | None = None,
    ) -> None:
        """Apply bond-state changes to runtime state and entry data in ONE write.

        Every config-entry update fires the options listener, so writing the two
        flags separately would queue two reloads for a single logical transition.
        The write is also marked internal, so the listener skips the reload
        entirely: on a bed that grants one connection per pairing window, simply
        recording "this link is not bonded" would otherwise tear down the link we
        just decided to keep (issue #385).
        """
        data = dict(self.entry.data)
        if profile_metadata is not None:
            data[CONF_VIBRADORM_APP_METADATA] = profile_metadata
        if established is not None:
            self._ble_bond_established = established
            # Only persist False where a True is actually stored: writing the
            # key into an entry that never had it is pure reload churn.
            if established:
                data[CONF_BLE_BOND_ESTABLISHED] = True
            elif data.get(CONF_BLE_BOND_ESTABLISHED):
                data[CONF_BLE_BOND_ESTABLISHED] = False
        if unreliable is not None:
            self._ble_bond_marker_unreliable = unreliable
            if unreliable:
                data[CONF_BLE_BOND_MARKER_UNRELIABLE] = True
            else:
                data.pop(CONF_BLE_BOND_MARKER_UNRELIABLE, None)
        if context is not None:
            data[CONF_BLE_BOND_CONTEXT] = context
            # Provenance is only ever written from positive proof, and it names
            # its own owner. The unproven route scope has nothing left to say.
            data.pop(CONF_BLE_BOND_ATTEMPTED_SOURCE, None)
        if data != dict(self.entry.data):
            self._begin_internal_entry_update(bool(data.get(CONF_BLE_BOND_ESTABLISHED, False)))
            # Routes a paired child's write to the parent's per-side descriptor
            # rather than the shared entry (issue #329).
            self._async_persist_config(data)

    def begin_internal_bond_update(
        self: AdjustableBedCoordinator,
        bond_established: bool,
        *,
        marker_unreliable: bool | None = None,
    ) -> None:
        """Claim the caller's next entry write as one of our own bond updates.

        A repair for a bed that grants one connection per pairing window runs on
        the link it has just paired, and an ordinary entry write fires the
        options listener whose reload disconnects that link. The bed grants no
        replacement until it is power-cycled, so a *successful* repair would
        strand it. Only the tagging is exposed, never the write: a caller whose
        tag does not land must still persist, and merely reload.
        """
        self._ble_bond_established = bond_established
        if marker_unreliable is not None:
            self._ble_bond_marker_unreliable = marker_unreliable
            if not marker_unreliable:
                self._latched_pairing_successes = 0
        self._begin_internal_entry_update(bond_established)

    def _record_bond_provenance(self: AdjustableBedCoordinator) -> None:
        """Persist which transport owns the bond this link just proved.

        Only ever called after an authentication-gated read succeeded. An
        inconclusive or skipped probe proves nothing and must leave whatever was
        recorded before untouched, because provenance is what later authorizes a
        host-side removal.
        """
        path = self._connection_path
        if path is None or path.transport is TransportClass.UNKNOWN:
            # Nothing worth recording: an unknown transport must not be written
            # as if it were established fact.
            return
        evidence = BondEvidence(
            status=BondVerificationStatus.VERIFIED,
            owner=BondOwner.from_path(path),
            operation="runtime_authenticated_read",
            observed_at=datetime.now(UTC).isoformat(),
        )
        # A repair asks for this afterwards to tell "the bond was proven and its
        # owner is recorded" from "nothing established an owner this time", and
        # answers the second by dropping the stored provenance. So the positive
        # evidence has to outlive the read that produced it - including on the
        # unchanged-owner path below, which deliberately writes nothing.
        self._last_bond_evidence = evidence
        context = build_bond_context(evidence)
        if bond_context_matches(self.entry.data.get(CONF_BLE_BOND_CONTEXT), context):
            # Same owner as last time. The observation timestamp always differs,
            # so comparing whole contexts would rewrite the entry on every
            # reconnect, and every write fires the options listener.
            return
        self._persist_bond_flags(established=True, context=context)

    def _mark_ble_bond_established(self: AdjustableBedCoordinator) -> None:
        """Record that future connections should skip `pair=True`."""
        if self._ble_bond_marker_unreliable:
            # Skipping pairing on this device has already been proven wrong once.
            # Re-arming the marker here is what made it flip-flop: every connect
            # spent a doomed unpaired attempt before succeeding on the retry.
            return

        if self._ble_bond_established:
            return

        self._persist_bond_flags(established=True)

    def _clear_ble_bond_established(self: AdjustableBedCoordinator) -> None:
        """Clear the persisted bond marker after an authentication failure."""
        if not self._ble_bond_established and not self.entry.data.get(CONF_BLE_BOND_ESTABLISHED):
            return

        self._persist_bond_flags(established=False)

    def apply_confirmed_bond_removal(self: AdjustableBedCoordinator) -> None:
        """Clear all runtime and persisted state for a confirmed bond removal."""
        self._discard_bond_tracking()

    def _discard_bond_tracking(self: AdjustableBedCoordinator) -> None:
        """Discard runtime and persisted bond bookkeeping without unpairing."""
        self._ble_bond_established = False
        self._ble_bond_marker_unreliable = False
        self._latched_pairing_successes = 0
        # Every transient pairing decision was tied to the bookkeeping being
        # discarded. Keeping the one-shot skip would leak that decision into a
        # later connection after either bond removal or a protocol reclassification.
        self._skip_pair_next_attempt = False
        data = dict(self.entry.data)
        data.pop(CONF_BLE_BOND_ESTABLISHED, None)
        data.pop(CONF_BLE_BOND_MARKER_UNRELIABLE, None)
        data.pop(CONF_BLE_BOND_CONTEXT, None)
        data.pop(CONF_BLE_BOND_ATTEMPTED_SOURCE, None)
        if data == dict(self.entry.data):
            return
        self._begin_internal_entry_update(False)
        self._async_persist_config(data, keys=RUNTIME_BOND_KEYS)

    def _has_unresolved_auth_failure(self: AdjustableBedCoordinator) -> bool:
        """Return whether an observed GATT auth failure still warrants the repair."""
        return (
            supports_runtime_authentication_recovery(self._bed_type, self._protocol_variant)
            and self._last_bond_evidence is not None
            and self._last_bond_evidence.status is BondVerificationStatus.AUTH_FAILED
        )

    async def async_clear_obsolete_pairing_state(self: AdjustableBedCoordinator) -> None:
        """Remove stale pairing state when this protocol no longer requires it."""
        if (
            self._force_pairing_requested
            and self._bed_type == BED_TYPE_OKIN_CST
            and self._protocol_variant == OKIN_CST_VARIANT_NECTAR_MOVE
        ) or requires_pairing(self._bed_type, self._protocol_variant):
            return
        self._discard_bond_tracking()
        await delete_pairing_required_issue(self.hass, self._address)

    def _log_bond_marker_unreliable(self: AdjustableBedCoordinator) -> None:
        """Log the latch transition. The write itself is batched by the caller."""
        _LOGGER.info(
            "Cached bond marker for %s did not survive to this connection; "
            "requesting pairing on every future connection attempt",
            self._address,
        )

    def _log_bond_marker_reliable_again(self: AdjustableBedCoordinator) -> None:
        """Log the latch release. The write itself is batched by the caller."""
        _LOGGER.info(
            "Bond for %s survived a connection that did not request pairing; "
            "trusting the cached bond marker again",
            self._address,
        )

    async def _async_handle_ble_authentication_error(
        self: AdjustableBedCoordinator,
        err: BleakError,
        *,
        holding_lock: bool = False,
        retain_link: bool = False,
        attempt_details: dict[str, Any] | None = None,
        defer_pairing_issue: bool = False,
    ) -> None:
        """Handle a failure caused by an unauthenticated BLE connection.

        ``holding_lock`` must be True when called from a context that already
        holds ``self._lock`` (e.g. bond verification inside the connect path),
        so the disconnect uses the lock-free variant and does not deadlock.

        ``retain_link`` must be True only where an unbonded link is still worth
        keeping, i.e. the post-connect bond probe, whose caller goes on to run
        controller startup on that same link. It must stay False once startup
        has already failed: a link with no controller cannot drive the bed, and
        keeping it would only block the physical remote while leaving the
        coordinator in a half-initialised state.

        Connection retries defer the repair until their final outcome; runtime
        command failures still report it immediately.
        """
        if not supports_runtime_authentication_recovery(self._bed_type, self._protocol_variant):
            return

        keep_link = retain_link and grants_one_connection_per_pairing_window(
            self._bed_type, self._protocol_variant
        )
        # Stale proxy handles fail exactly like a missing bond (issue #660).
        # A retained link keeps running on its discovered services, so only a
        # link being dropped may clear them.
        cache_cleared = not keep_link and await async_clear_proxy_gatt_cache(
            self._client, self._connection_path
        )
        # The first time, assume the bond is fine and retry on rediscovered
        # handles without pairing: re-pairing a bonded ESPHome device can fail
        # with error 82 or wedge the proxy. A repeat failure is a real one.
        # A clear implies a known proxy path; the retry is spent per proxy because
        # Home Assistant may reroute the next attempt through another one.
        cleared_source = self._connection_path.source if self._connection_path else ""
        self._auth_failure_source = cleared_source
        stale_cache_retry = (
            cache_cleared and cleared_source not in self._stale_gatt_retry_sources
        )
        if stale_cache_retry:
            self._stale_gatt_retry_sources.add(cleared_source)
            self._skip_pair_next_attempt = True
            self._stale_gatt_retry_source = cleared_source
            _LOGGER.warning(
                "BLE link on %s is not authenticated: %s. The proxy's cached GATT "
                "services may be stale; retrying with rediscovered services "
                "before requesting pairing.",
                self._address,
                err,
            )
        else:
            _LOGGER.warning(
                "BLE link on %s is not authenticated: %s. "
                "Clearing the cached bond marker so the next connection can request pairing.",
                self._address,
                err,
            )
        self._record_bond_verification("authentication_failed", err, attempt_details)
        # Attribute the failure to a transport. A host bond and a proxy bond are
        # separate state, so evidence carried by one says nothing about the
        # other, and recovery must never act on the wrong one. Nothing
        # destructive happens here: the marker is cleared and a repair is
        # raised, and removing a real bond stays an explicit, confirmed action.
        self._last_bond_evidence = BondEvidence(
            status=BondVerificationStatus.AUTH_FAILED,
            owner=BondOwner.from_path(self._connection_path),
            operation="runtime_gatt_access",
            observed_at=datetime.now(UTC).isoformat(),
            error=str(err),
            gatt_cache_cleared=cache_cleared,
        )
        # A definitive authentication failure invalidates any earlier decision
        # to skip a probe that timed out. The next paired connection should
        # verify the fresh bond again.
        self._bond_probe_timed_out = False
        if not stale_cache_retry:
            latch = self._attempt_trusted_bond_marker and not self._ble_bond_marker_unreliable
            if latch:
                self._log_bond_marker_unreliable()
            self._persist_bond_flags(
                established=False,
                unreliable=True if latch else None,
            )

            if not defer_pairing_issue:
                await self._async_raise_pairing_issue()

        if self._client is not None and self._client.is_connected:
            if keep_link:
                # Disconnecting would cost us the box's single connection and
                # the reconnect that "fixes" the bond can never happen. Leave
                # the link up; the repair tells the user to re-pair.
                _LOGGER.warning(
                    "Keeping the unbonded link to %s open: this bed grants one "
                    "connection per pairing window, so disconnecting to re-pair "
                    "would leave it unreachable until it is power-cycled.",
                    self._address,
                )
                return
            if holding_lock:
                await self._async_disconnect_locked(reason="authentication_failed")
            else:
                await self.async_disconnect(reason="authentication_failed")

    def _can_encrypt_link_in_place(self: AdjustableBedCoordinator) -> bool:
        """Return True when a runtime auth failure should first try in-place pairing.

        A retained link that never requested pairing proves nothing about the
        bond: unlike BlueZ, the ESP32 proxy in issue #709 did not raise link
        security after an "insufficient encryption" reply, so an unpaired
        reconnect to a bonded bed stayed unencrypted. Pairing that live link is
        exactly what the guided repair does, and with stored keys it needs no
        pairing mode. Once a link has paired, a further auth failure is real
        evidence.
        """
        return (
            grants_one_connection_per_pairing_window(self._bed_type, self._protocol_variant)
            and not self._attempt_used_pairing
            and self._pairing_supported is not False
            and self._client is not None
            and self._client.is_connected
        )

    async def _async_encrypt_link_in_place(self: AdjustableBedCoordinator) -> bool:
        """Pair the retained live link; raise the repair only if the bed refuses."""
        async with self._lock:
            if self._client is None or not self._client.is_connected:
                await self._async_raise_pairing_issue()
                return False
            try:
                # Raises the repair itself when the bond is refused.
                paired = await self._async_pair_on_live_link({})
            except Exception:
                _LOGGER.warning(
                    "Could not pair the live link to %s in place", self._address, exc_info=True
                )
                await self._async_raise_pairing_issue()
                return False
            if not paired:
                return False
            _LOGGER.info(
                "Paired the live link to %s in place with its existing bond; "
                "future connections will pair after service discovery",
                self._address,
            )
            # The authentication failure was the unencrypted link, not a lost bond.
            self._last_bond_evidence = None
            self._record_bond_verification("encrypted_in_place")
            await delete_pairing_required_issue(self.hass, self._address)
            return True

    async def _async_raise_pairing_issue(self: AdjustableBedCoordinator) -> None:
        """Surface the guided pairing repair, best-effort."""
        try:
            await create_pairing_required_issue(
                self.hass,
                self._address,
                self._name,
                self.entry.entry_id,
                evidence=(
                    self._last_bond_evidence.as_dict()
                    if self._last_bond_evidence is not None
                    else None
                ),
            )
        except Exception:
            _LOGGER.debug(
                "Failed to create pairing required repair issue for %s",
                self._address,
                exc_info=True,
            )

    async def _async_pair_on_live_link(
        self: AdjustableBedCoordinator, pairing_details: dict[str, Any], *,
        onboarding_deadline: float | None = None, force_pairing: bool = False,
    ) -> bool:
        """Create the BLE bond on an already-connected, service-discovered link.

        Returns True when the bond was created, False when it failed and the bed
        type tolerates staying unbonded.

        For a bed that only grants one connection per pairing window, letting a
        bond failure propagate is self-defeating: the caller tears the link down
        and the box then refuses every reconnect until it is power-cycled. LP
        Control never takes that risk — it fires ``createBond()`` and continues
        on the same link without ever checking whether it succeeded — so mirror
        that and keep the connection. Whether an unbonded link can actually
        drive the motors is firmware behaviour the APK cannot prove, but a live
        link can be tried while a dropped one is guaranteed useless.

        This applies to a backend that cannot pair at all
        (``NotImplementedError``/``TypeError``, e.g. ESPHome < 2024.3.0) just as
        much as to a rejected bond: the caller's compatibility fallback would
        reconnect with ``pair=False``, but the link we already hold was itself
        made with ``pair=False``, so it would spend the bed's one connection to
        obtain an identical one.
        """
        client = self._client
        if client is None:
            return False
        if self._bed_type == BED_TYPE_VIBRADORM_APP:
            metadata_progress: dict[str, str] = {}
            pairing_details.pop("vmat_setup_started", None)
            try:
                return await self._async_pair_vibradorm_app(
                    client, pairing_details, onboarding_deadline=onboarding_deadline,
                    force_pairing=force_pairing, metadata_progress=metadata_progress,
                )
            except (Exception, asyncio.CancelledError):
                if not self._ble_bond_established:
                    self._persist_bond_flags(
                        established=False,
                        profile_metadata=(
                            self._merged_vibradorm_app_metadata(metadata_progress)
                            if metadata_progress else None
                        ),
                    )
                raise
            finally:
                if self.entry.data.get(CONF_VIBRADORM_APP_PROFILE) == "vmat" and pairing_details.get("vmat_setup_started"):
                    from .beds.vibradorm.vmat_setup import async_close_vmat_setup

                    self._intentional_disconnect = True
                    disconnected = not client.is_connected
                    try:
                        if client.is_connected:
                            try:
                                with contextlib.suppress(Exception):
                                    await async_close_vmat_setup(client)
                            finally:
                                # Secondary teardown failure must not replace cancellation.
                                pending_failure = sys.exception()
                                try:
                                    await client.disconnect()
                                except Exception:
                                    if client.is_connected and pending_failure is None:
                                        raise
                                    _LOGGER.debug("VMAT disconnect failed during setup cleanup", exc_info=True)
                                else:
                                    disconnected = not client.is_connected
                                    if not disconnected and pending_failure is None:
                                        raise ConnectionError("VMAT setup connection did not disconnect")
                    finally:
                        if client.is_connected:
                            async_get_connect_lock(self.hass, self._address).retain_setup_client(client)
                        if self._client is client and (disconnected or not client.is_connected):
                            self._client = None
                            if self._vmat_unready_client is client:
                                self._vmat_unready_client = None
                        self._intentional_disconnect = False
        advisory = grants_one_connection_per_pairing_window(self._bed_type, self._protocol_variant)
        # Any pairing on this link, including the repair's, makes a later auth
        # failure on it evidence rather than an unencrypted link.
        self._attempt_used_pairing = True
        try:
            _LOGGER.info("BLE backend pairing starting for %s on the discovered link", self._address)
            await client.pair()
            _LOGGER.info("BLE backend pairing completed for %s; authenticated access is not yet verified", self._address)
        except (NotImplementedError, TypeError) as err:
            if not advisory:
                raise
            self._pairing_supported = False
            pairing_details["adapter_pairing_supported"] = False
            _LOGGER.warning(
                "Bluetooth backend for %s cannot create BLE bonds (%s). Keeping "
                "the live connection and continuing unbonded. If you use an "
                "ESPHome proxy, update it to 2024.3.0 or newer.",
                self._address,
                err,
            )
            pairing_details["error"] = str(err)
            pairing_details["error_type"] = type(err).__name__
            self._record_bond_verification("advisory_bond_unsupported", err)
            # Startup can still finish on the unbonded link, and the later bond
            # probe only raises the repair on a *definitive* auth error - a
            # timeout or non-auth BleakError is treated as inconclusive. Raise
            # it here so a failed bond always leaves the user a guided fix.
            await self._async_raise_pairing_issue()
            return False
        except (BleakError, TimeoutError, OSError) as err:
            if not advisory:
                raise
            self._pairing_supported = True
            pairing_details["adapter_pairing_supported"] = True
            if is_ble_pairing_auth_failure(err):
                # The bond failed at the authentication stage. Field evidence
                # (issue #385) shows the bed then drops the link about a second
                # later, so promising to keep the connection alive here would be
                # untrue. Suggest the remedy without asserting the cause:
                # BlueZ's AuthenticationFailed is generic, so mismatched stored
                # keys are a common explanation rather than a proven one.
                _LOGGER.warning(
                    "Could not authenticate the BLE bond with %s (%s). The bed "
                    "usually drops the connection straight after this, so "
                    "retrying unchanged rarely helps. One common cause is "
                    "stored pairing keys that no longer match: if this keeps "
                    "repeating, clear the stored pairing on the adapter you "
                    "connect from - on a Home Assistant host that is "
                    "'bluetoothctl remove %s', while on an ESPHome proxy the "
                    "bond lives on the proxy and must be cleared there - and "
                    "clear the bed's own stored pairings as its manufacturer "
                    "documents, then pair again.",
                    self._address,
                    err,
                    self._address,
                )
                self._record_bond_verification("advisory_bond_auth_failed", err)
            else:
                _LOGGER.warning(
                    "Could not create the BLE bond with %s (%s). Keeping the live "
                    "connection and continuing unbonded — this bed only accepts one "
                    "connection per pairing window, so dropping it now would strand "
                    "the bed until it is power-cycled.",
                    self._address,
                    err,
                )
                self._record_bond_verification("advisory_bond_failed", err)
            pairing_details["error"] = str(err)
            pairing_details["error_type"] = type(err).__name__
            await self._async_raise_pairing_issue()
            return False
        return True

    async def _async_observe_native_bond(
        self: AdjustableBedCoordinator, pairing_details: dict[str, Any], *,
        metadata: dict[str, str | None] | None = None,
    ) -> bool:
        """Persist exact native proof without claiming authenticated GATT access."""
        evidence = await async_verify_native_bond(
            self._address, path=self._connection_path, operation="runtime_native_bond_state"
        )
        self._last_bond_evidence = evidence
        self._record_bond_verification(str(evidence.status))
        pairing_details["bond_evidence"] = evidence.as_dict()
        if not evidence.proves_bond:
            return False
        context = build_bond_context(evidence)
        stored = self.entry.data.get(CONF_BLE_BOND_CONTEXT)
        if (
            not self._ble_bond_established or self._ble_bond_marker_unreliable
            or not bond_context_matches(stored, context)
            or not isinstance(stored, dict)
            or stored.get("evidence_kind") != context["evidence_kind"]
            or CONF_BLE_BOND_ATTEMPTED_SOURCE in self.entry.data
            or (metadata is not None and self.entry.data.get(CONF_VIBRADORM_APP_METADATA) != metadata)
        ):
            self._persist_bond_flags(
                established=True, unreliable=False, context=context, profile_metadata=metadata
            )
        await delete_pairing_required_issue(self.hass, self._address)
        return True

    async def _async_pair_vibradorm_app(
        self: AdjustableBedCoordinator, client: BleakClient, pairing_details: dict[str, Any], *,
        onboarding_deadline: float | None, force_pairing: bool,
        metadata_progress: dict[str, str],
    ) -> bool:
        """Run first-bond information and native pairing in one absolute budget."""
        # vmat_setup imports the app module.
        await async_import_modules(self.hass, "beds.vibradorm.vmat_setup")
        from .beds.vibradorm.app import (
            VibradormAppMetadataProgress,
            async_prepare_vibradorm_app_pairing,
        )

        def record_metadata(progress: VibradormAppMetadataProgress) -> None:
            # Completed fields remain useful diagnostics if a later stage fails.
            # Entry persistence waits for the terminal bond/attempt observation.
            completed = {field: value for field, value in progress.items() if isinstance(value, str)}
            metadata_progress.update(completed)
            self.handle_controller_state_updates(*(
                vibradorm_app_metadata_key(field)(value) for field, value in completed.items()
            ))

        onboarding_timeout = (
            VIBRADORM_VMAT_ONBOARDING_TIMEOUT_SECONDS
            if self.entry.data.get(CONF_VIBRADORM_APP_PROFILE) == "vmat"
            else VIBRADORM_APP_ONBOARDING_TIMEOUT_SECONDS
        )
        deadline = onboarding_deadline
        if deadline is None:
            deadline = asyncio.get_running_loop().time() + onboarding_timeout
        source = self._connection_path.source if self._connection_path is not None else None
        retained_context = (
            not force_pairing and self._ble_bond_established
            and self._unverified_marker_applies(source)
        )
        if not retained_context and deadline <= asyncio.get_running_loop().time():
            raise TimeoutError("App onboarding budget expired during connection")
        observation_deadline = (
            asyncio.get_running_loop().time() + onboarding_timeout
            if retained_context else deadline
        )
        async with asyncio.timeout_at(observation_deadline) as budget:
            if await self._async_observe_native_bond(pairing_details):
                pairing_details["native_pairing"] = "already_stored"
                pairing_details["requested"] = False
                self._attempt_used_pairing = False
                return True
            if (
                not force_pairing and self._ble_bond_established and source
                and self._unverified_marker_applies(source)
            ):
                pairing_details["native_pairing"] = "unverified_attempt_on_same_source"
                pairing_details["requested"] = False
                self._attempt_used_pairing = False
                self._record_bond_verification("unverified")
                return False
            # Defer the entry write until the terminal observation, so its
            # one-shot internal-update guard covers the whole transition.
            self._ble_bond_established = False
            if deadline <= asyncio.get_running_loop().time():
                raise TimeoutError("App onboarding budget expired during connection")
            budget.reschedule(deadline)
            if not force_pairing and self._pairing_supported is False:
                pairing_details["native_pairing"] = "unsupported_link_retained"
                self._persist_bond_flags(established=False)
                return False
            command_context = current_command_context()
            cancel_event = (
                self.cancel_command
                if command_context is not None
                and command_context.scheduler_token is self._command_scheduler.token
                else None
            )
            stored_control = self.entry.data[CONF_VIBRADORM_CONTROL_TYPE]
            control_type: ControlType
            if stored_control == "other":
                control_type = "other"
            elif isinstance(stored_control, int) and not isinstance(stored_control, bool):
                control_type = stored_control
            elif isinstance(stored_control, str):
                control_type = int(stored_control)
            else:
                raise ValueError("Invalid retained Vibradorm control type")
            if self.entry.data.get(CONF_VIBRADORM_APP_PROFILE) == "vmat":
                pairing_details["vmat_setup_started"] = True
                self._vmat_unready_client = client
            metadata = await async_prepare_vibradorm_app_pairing(
                client, self.entry.data[CONF_VIBRADORM_APP_PROFILE],
                control_type,
                deadline=deadline, cancel_event=cancel_event, metadata_progress=record_metadata,
                remote=self.entry.data.get(CONF_VIBRADORM_VMAT_REMOTE),
            )
            completed_metadata = {
                "model": metadata.model, "firmware": metadata.firmware,
                "software": metadata.software,
            }
            if self.entry.data.get(CONF_VIBRADORM_APP_PROFILE) == "vmat":
                completed_metadata.update(metadata_progress)
            if isinstance(metadata.main_firmware_article, str):
                completed_metadata["main_firmware_article"] = metadata.main_firmware_article
            stored_metadata = self._merged_vibradorm_app_metadata(completed_metadata)
            self.handle_controller_state_updates(*(
                vibradorm_app_metadata_key(field)(value)
                for field, value in stored_metadata.items()
            ))
            try:
                pairing_details["requested"] = True
                pairing_details["ordering"] = "connect_info_then_pair"
                self._attempt_used_pairing = True
                await client.pair()
            except (NotImplementedError, TypeError, BleakError, OSError) as err:
                self._pairing_supported = not isinstance(err, (NotImplementedError, TypeError))
                pairing_details.update(error=str(err), error_type=type(err).__name__)
                pairing_details["native_pairing"] = "failed_link_retained"
                self._persist_bond_flags(established=False, profile_metadata=stored_metadata)
                await self._async_raise_pairing_issue()
                return False
            self._pairing_supported = True
            if await self._async_observe_native_bond(pairing_details, metadata=stored_metadata):
                pairing_details["native_pairing"] = "stored"
                return True
            if (
                self._last_bond_evidence is not None
                and self._last_bond_evidence.proves_native_bond_absent
            ):
                pairing_details["native_pairing"] = "not_stored"
                self._persist_bond_flags(established=False, profile_metadata=stored_metadata)
                await self._async_raise_pairing_issue()
                return False
            if self.entry.data.get(CONF_VIBRADORM_APP_PROFILE) == "vmat":
                self._persist_bond_flags(established=False, profile_metadata=stored_metadata)
                self._record_bond_verification("unverified")
                pairing_details["native_pairing"] = "unverified"
                await self._async_raise_pairing_issue()
                return False
            # A successful RPC is only an attempted marker, scoped to this live
            # source. It avoids proxy re-pair storms without inventing proof.
            if source and source != "unknown":
                data = dict(self.entry.data)
                data[CONF_BLE_BOND_ESTABLISHED] = True
                data[CONF_BLE_BOND_ATTEMPTED_SOURCE] = source
                data[CONF_VIBRADORM_APP_METADATA] = stored_metadata
                data.pop(CONF_BLE_BOND_CONTEXT, None)
                self._ble_bond_established = True
                if data != dict(self.entry.data):
                    self._begin_internal_entry_update(True)
                    self._async_persist_config(data)
            else:
                self._persist_bond_flags(established=False, profile_metadata=stored_metadata)
            self._record_bond_verification("unverified")
            pairing_details["native_pairing"] = "unverified"
            await self._async_raise_pairing_issue()
            return False

    async def async_pair_now(self: AdjustableBedCoordinator) -> bool:
        """Re-run BLE pairing on demand and report whether the bond is live.

        Drives the pairing repair for a bed that only grants one connection per
        pairing window. Two things matter here:

        * The cached bond marker must be cleared on the *runtime* coordinator,
          not just in ``entry.data``. ``_ble_bond_established`` is read from the
          entry once at construction, so editing entry data alone would leave
          this connection still skipping ``pair=True``.
        * When a link is already up, pair on that link. Reconnecting to "pair
          properly" would spend the bed's single connection.

        Returns True only when the bond is confirmed, so a repair cannot report
        success while the link is still unbonded.
        """
        async with self._lock:
            if self._capability_reload_blocks_connection():
                _LOGGER.debug(
                    "Deferring pairing for %s until its capability reload completes",
                    self._address,
                )
                return False
            if self._bed_type == BED_TYPE_VIBRADORM_APP:
                # Native proof and its replacement context commit together;
                # an intermediate entry write would spend the one-shot guard.
                self._ble_bond_established = False
            else:
                self._clear_ble_bond_established()
            self._skip_pair_next_attempt = False
            self._bond_probe_timed_out = False
            # A repair persists the owner this attempt proves. Pairing a live
            # link can succeed without running a new authenticated read, so an
            # observation left by the previous bond - possibly one that has
            # since been removed - would otherwise be persisted as provenance
            # for its replacement.
            self._last_bond_evidence = None

            if self._client is not None and self._client.is_connected:
                if self._bed_type == BED_TYPE_SLEEP_NUMBER:
                    async with capture_proxy_logs(
                        self.hass, self._address, self._preferred_adapter, retain=True
                    ):
                        return await self._async_pair_live_and_verify()
                return await self._async_pair_live_and_verify()

            self._force_pairing_requested = (
                self._bed_type == BED_TYPE_OKIN_CST
                and self._protocol_variant == OKIN_CST_VARIANT_NECTAR_MOVE
            )
            try:
                if not await self._async_connect_locked():
                    if self._bed_type == BED_TYPE_VIBRADORM_APP:
                        self._persist_bond_flags(established=False)
                    return False
                if self._bed_type == BED_TYPE_VIBRADORM_APP:
                    return (
                        self._last_bond_evidence is not None
                        and self._last_bond_evidence.proves_bond
                    )
                return self._ble_bond_established
            finally:
                self._force_pairing_requested = False

    async def _async_pair_live_and_verify(self: AdjustableBedCoordinator) -> bool:
        """Pair and verify the live link while the coordinator lock is held."""
        pairing_details: dict[str, Any] = {}
        if self._bed_type == BED_TYPE_VIBRADORM_APP:
            return await self._async_pair_on_live_link(pairing_details, force_pairing=True)
        if await self._async_pair_on_live_link(pairing_details):
            if self._bed_type == BED_TYPE_SLEEP_NUMBER:
                return await self._async_verify_bonded() and self._ble_bond_established
            self._mark_ble_bond_established()
            await delete_pairing_required_issue(self.hass, self._address)
            return True
        # The bond request failed but the link survived; the probe is the
        # authority on whether we are nevertheless bonded.
        return await self._async_verify_bonded() and self._ble_bond_established

    async def _async_verify_bonded(
        self: AdjustableBedCoordinator,
        attempt_details: dict[str, Any] | None = None,
        *,
        defer_pairing_issue: bool = False,
    ) -> bool:
        """Probe an auth-gated characteristic to confirm the BLE bond is live.

        For beds that require pairing, a connection — even one made with
        ``pair=True`` — can succeed while the link is still unbonded; every
        encrypted characteristic then fails with GATT error=5 "Insufficient
        authentication". Reading one known auth-gated characteristic surfaces
        this so we can clear a stale bond marker and re-pair instead of
        silently staying unbonded.

        Returns True if the link is bonded (or the check is inconclusive), and
        False only when an authentication error is definitively observed — in
        which case the bond marker is cleared and the client is disconnected.
        Automatic retries may defer the repair until recovery has finished.
        """
        client = self._client
        if client is None or not client.is_connected:
            self._record_bond_verification("skipped_not_connected", attempt_details=attempt_details)
            return True

        if self._bed_type == BED_TYPE_VIBRADORM_APP:
            pairing_details = attempt_details.setdefault("pairing", {}) if attempt_details is not None else {}
            if await self._async_observe_native_bond(pairing_details):
                return True
            source = self._connection_path.source if self._connection_path is not None else None
            attempted_here = bool(source) and source == self.entry.data.get(CONF_BLE_BOND_ATTEMPTED_SOURCE)
            if not attempted_here:
                self._persist_bond_flags(established=False)
            if not defer_pairing_issue:
                await self._async_raise_pairing_issue()
            # Native state cannot prove authentication failure. Keep the usable
            # link; explicit repair still reports False unless native proof exists.
            return True

        if self._bond_probe_timed_out:
            _LOGGER.debug(
                "Bond verification read previously timed out on %s; "
                "skipping the probe for this session.",
                self._address,
            )
            self._record_bond_verification(
                "skipped_cached_timeout", attempt_details=attempt_details
            )
            return True

        probe_uuid = DEVICE_INFO_CHARS["model_number"]
        try:
            if self._bed_type == BED_TYPE_SLEEP_NUMBER:
                from .beds.sleep_number.auth import async_read_sleep_number_session

                await async_read_sleep_number_session(client)
            else:
                await asyncio.wait_for(client.read_gatt_char(probe_uuid), DEVICE_INFO_READ_TIMEOUT)
        except BleakError as err:
            if _is_ble_authentication_error(err):
                # We run inside _async_connect_locked, which holds self._lock —
                # disconnect via the lock-free path to avoid a deadlock.
                await self._async_handle_ble_authentication_error(
                    err,
                    holding_lock=True,
                    retain_link=True,
                    attempt_details=attempt_details,
                    defer_pairing_issue=defer_pairing_issue,
                )
                # For a one-connection-per-window bed the handler deliberately
                # kept the link, so report success and let controller startup
                # use it. Retrying "with pairing" would only spend the bed's
                # single connection on a reconnect that cannot happen.
                return grants_one_connection_per_pairing_window(
                    self._bed_type, self._protocol_variant
                )
            _LOGGER.debug(
                "Bond verification read for %s was inconclusive (%s); proceeding.",
                self._address,
                err,
            )
            self._record_bond_verification("inconclusive_error", err, attempt_details)
            return True
        except (TimeoutError, OSError) as err:
            # The field-proven OKIN CST receiver never answers this DIS read,
            # so repeated probes only add latency. Other pairing-required beds
            # can time out transiently while waking and must retry on a later
            # connection so stale bond state can still be detected.
            self._bond_probe_timed_out = self._bed_type == BED_TYPE_OKIN_CST
            if self._bond_probe_timed_out:
                _LOGGER.debug(
                    "Bond verification read for OKIN CST %s failed (%s); "
                    "skipping future probes for this session.",
                    self._address,
                    err,
                )
            else:
                _LOGGER.debug(
                    "Bond verification read for %s failed (%s); proceeding and "
                    "retrying on the next connection.",
                    self._address,
                    err,
                )
            self._record_bond_verification("timed_out", err, attempt_details)
            return True

        return await self._async_record_verified_bond(attempt_details)

    async def _async_record_verified_bond(
        self: AdjustableBedCoordinator, attempt_details: dict[str, Any] | None = None
    ) -> bool:
        """Record a successful protocol-specific authenticated read."""
        # Read succeeded → the encrypted link works → we are bonded. Record which
        # transport carried that proof, so a later unpair or recovery knows where
        # the bond actually lives instead of guessing (issue #459).
        # The link is authenticated now, so any earlier authentication failure
        # is history. Leaving it in place would let a later repair believe it
        # still had grounds to remove a bond that is demonstrably working.
        # _record_bond_provenance() then replaces it with this read's own
        # positive evidence whenever the route is known.
        self._last_bond_evidence = None
        self._record_bond_provenance()
        release_latch = False
        if self._ble_bond_marker_unreliable:
            if not self._attempt_used_pairing:
                # The bond survived to a connection that never asked to pair, so
                # whatever made the marker unreliable no longer applies (a
                # different adapter, a firmware change, a proxy that now
                # persists bonds). Trust the marker again.
                release_latch = True
                self._log_bond_marker_reliable_again()
            else:
                # While latched every attempt pairs, so the check above can only
                # fire on a backend where pairing itself failed and fell back to
                # an unpaired connect. Without this a pairing-capable backend
                # would re-pair on every reconnect forever, including on stacks
                # this code already knows can fail when re-pairing atop an
                # existing bond. Periodically drop the latch to re-test: the
                # cost of being wrong is one failed attempt per retest, not one
                # per connect.
                self._latched_pairing_successes += 1
                if self._latched_pairing_successes >= BOND_LATCH_RETEST_AFTER:
                    release_latch = True
                    _LOGGER.info(
                        "Re-testing the cached bond marker for %s after %d paired "
                        "connections; the next attempt will try without pairing",
                        self._address,
                        self._latched_pairing_successes,
                    )
        self._skip_pair_next_attempt = False
        self._stale_gatt_retry_sources.clear()
        if release_latch:
            self._latched_pairing_successes = 0
            self._persist_bond_flags(established=True, unreliable=False)
        else:
            self._mark_ble_bond_established()
        await delete_pairing_required_issue(self.hass, self._address)
        self._record_bond_verification("succeeded", attempt_details=attempt_details)
        _LOGGER.debug("Bond verification succeeded for %s", self._address)
        return True

    @property
    def pairing_diagnostics(self: AdjustableBedCoordinator) -> dict[str, Any]:
        """Return pairing and bond state for diagnostics and support bundles."""
        pairing_attempts = [
            {
                "attempt": attempt.get("attempt"),
                "started_at": attempt.get("started_at"),
                "result": attempt.get("result"),
                "pairing": dict(pairing),
            }
            for attempt in self._connection_attempt_details
            if isinstance((pairing := attempt.get("pairing")), dict)
            and pairing.get("required") is not None
        ]
        return {
            "furnimove_bond_request": dict(self._furnimove_bond_request),
            "required": requires_pairing(self._bed_type, self._protocol_variant),
            "connection_gated_by_bond": connection_gated_by_bond(
                self._bed_type, self._protocol_variant
            ),
            "persisted_bond_marker": bool(self.entry.data.get(CONF_BLE_BOND_ESTABLISHED, False)),
            "runtime_bond_established": self._ble_bond_established,
            "bond_marker_unreliable": self._ble_bond_marker_unreliable,
            "adapter_pairing_supported": self._pairing_supported,
            "transient_skip_next_attempt": self._skip_pair_next_attempt,
            "bond_probe_timed_out": self._bond_probe_timed_out,
            "last_bond_verification": dict(self._last_bond_verification),
            # Everything #459 asks diagnostics to record about a bond: which
            # path was predicted, which was used, who owns the bond, what the
            # evidence was, and what was done about it.
            "connection_path": (
                {
                    "source": self._connection_path.source,
                    "transport": str(self._connection_path.transport),
                    "scanner_name": self._connection_path.scanner_name,
                    "adapter": self._connection_path.adapter,
                }
                if self._connection_path is not None
                else None
            ),
            "bond_owner": bond_owner_from_entry(self.entry.data).as_dict(),
            "bond_context": self.entry.data.get(CONF_BLE_BOND_CONTEXT),
            "last_bond_evidence": (
                self._last_bond_evidence.as_dict() if self._last_bond_evidence is not None else None
            ),
            "stale_host_bond_suspected": bool(
                self._last_bond_evidence is not None
                and self._last_bond_evidence.proves_stale_host_bond
            ),
            "recovery_action": (
                "repair_issue_raised"
                if self._last_bond_evidence is not None
                and self._last_bond_evidence.status is BondVerificationStatus.AUTH_FAILED
                else None
            ),
            "backend_reports": self._device_pairing_states(),
            "connection_attempts": pairing_attempts,
        }

    def _unverified_marker_applies(self: AdjustableBedCoordinator, source: str | None) -> bool:
        """Return True when an unproven bond marker may be trusted on this route.

        A bond recorded without an authentication-gated read to prove it is only
        credible on the transport that made it. Automatic routing can re-rank a
        later connection onto an adapter or proxy that was never bonded, and
        trusting the marker there suppresses ``pair=True`` on an unbonded link,
        which fails authentication and raises a repair for a bed that only
        needed pairing.

        Erring toward pairing is the recoverable direction: a redundant
        ``pair=True`` is caught by the unreliable-marker latch, whereas skipping
        it on an unbonded route cannot be retried within the attempt.
        """
        attempted = self.entry.data.get(CONF_BLE_BOND_ATTEMPTED_SOURCE)
        if self._bed_type == BED_TYPE_VIBRADORM_APP:
            evidence = self._last_bond_evidence
            if (
                evidence is not None and evidence.proves_native_bond_absent
                and source == evidence.owner.source
            ):
                return False
            owner = bond_owner_from_entry(self.entry.data)
            return bool(source) and (
                source == attempted
                or (owner.transport is not TransportClass.UNKNOWN and source == owner.source)
            )
        if not attempted:
            # No scope recorded: either the bond was proven (and carries
            # provenance instead) or the entry predates scoping. Unchanged.
            return True
        return bool(source) and source == attempted

    def _prepare_pairing_attempt(
        self: AdjustableBedCoordinator,
        device: BLEDevice,
        pairing_details: dict[str, Any],
        source: str | None = None,
    ) -> tuple[bool, bool, bool]:
        """Resolve pairing policy and diagnostics for one connection attempt."""
        force_pairing = (
            self._force_pairing_requested
            and self._bed_type == BED_TYPE_OKIN_CST
            and self._protocol_variant == OKIN_CST_VARIANT_NECTAR_MOVE
        )
        bed_requires_pairing = force_pairing or requires_pairing(
            self._bed_type, self._protocol_variant
        )
        bond_marker_before_attempt = self._ble_bond_established
        transient_skip_was_set = self._skip_pair_next_attempt
        os_bond_reported = (
            bed_requires_pairing
            and not force_pairing
            and self._device_reports_existing_bond(device)
        )
        if bed_requires_pairing and not self._ble_bond_established and os_bond_reported:
            _LOGGER.info(
                "Existing BLE bond detected for %s; skipping pair=True",
                self._address,
            )
            self._mark_ble_bond_established()

        # An unproven marker only speaks for the route that recorded it.
        marker_out_of_scope = self._ble_bond_established and not (
            self._unverified_marker_applies(source)
        )
        if marker_out_of_scope:
            _LOGGER.info(
                "Bond marker for %s was recorded on %s but this attempt uses %s; "
                "requesting pairing rather than trusting it on another transport",
                self._address,
                self.entry.data.get(CONF_BLE_BOND_ATTEMPTED_SOURCE),
                source or "an unknown source",
            )
        # A latched marker has already been proven wrong once, so it never
        # suppresses pairing, even after a repair recorded a fresh bond
        # (issue #709: the repair kept the latch but re-armed the marker, and
        # the next unpaired proxy reconnect came up unencrypted).
        bond_marker_trusted = (
            self._ble_bond_established
            and not self._ble_bond_marker_unreliable
            and not marker_out_of_scope
        )

        use_pairing = (force_pairing and not self._skip_pair_next_attempt) or (
            self._pairing_supported is not False
            and (
                bed_requires_pairing
                and not bond_marker_trusted
                and not self._skip_pair_next_attempt
            )
        )
        pair_after_service_discovery = bool(
            use_pairing
            and requires_pairing_after_service_discovery(
                self._bed_type,
                self._protocol_variant,
            )
        )
        pairing_ordering = "not_requested"
        if use_pairing:
            pairing_ordering = (
                "connect_discover_then_pair" if pair_after_service_discovery else "backend_default"
            )
        if force_pairing and use_pairing:
            pairing_decision = "explicit_pair_repair"
        elif not bed_requires_pairing:
            pairing_decision = "not_required"
        elif self._ble_bond_marker_unreliable:
            pairing_decision = "bond_marker_unreliable"
        elif marker_out_of_scope:
            pairing_decision = "bond_marker_other_transport"
        elif os_bond_reported and not bond_marker_before_attempt:
            pairing_decision = "existing_os_bond_detected"
        elif self._ble_bond_established:
            pairing_decision = "bond_marker_present"
        elif transient_skip_was_set:
            pairing_decision = "retry_without_pairing"
        elif self._pairing_supported is False:
            pairing_decision = "adapter_pairing_unsupported"
        else:
            pairing_decision = "pairing_requested"
        pairing_details.update(
            {
                "required": bed_requires_pairing,
                "requested": use_pairing,
                "decision": pairing_decision,
                "adapter_pairing_supported": self._pairing_supported,
                "bond_marker_before_attempt": bond_marker_before_attempt,
                "bond_marker_after_detection": self._ble_bond_established,
                "bond_marker_unreliable": self._ble_bond_marker_unreliable,
                "os_bond_reported": os_bond_reported,
                "transient_skip_was_set": transient_skip_was_set,
                "ordering": pairing_ordering,
                "attempt_source": source,
                "bond_marker_scope": self.entry.data.get(CONF_BLE_BOND_ATTEMPTED_SOURCE),
                "bond_marker_out_of_scope": marker_out_of_scope,
            }
        )
        # Both of these skip pairing because something claimed we are already
        # bonded. If the probe then fails, that claim was wrong and must latch:
        # a stale OS-reported bond would otherwise be believed again on every
        # retry, so a pairing-required bed could exhaust all attempts without
        # ever actually pairing.
        self._attempt_trusted_bond_marker = (
            bed_requires_pairing
            and not use_pairing
            and pairing_decision in ("bond_marker_present", "existing_os_bond_detected")
        )
        self._attempt_used_pairing = use_pairing
        # Consume the transient skip flag: it only suppresses pairing for the
        # single attempt immediately following a failed pair.
        self._skip_pair_next_attempt = False
        return bed_requires_pairing, use_pairing, pair_after_service_discovery

    async def _async_cancel_furnimove_bond_request(self: AdjustableBedCoordinator) -> None:
        task = self._furnimove_bond_task
        try:
            if task is not None:
                if not task.done():
                    task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    current_task = asyncio.current_task()
                    if current_task is not None and current_task.cancelling():
                        raise
        finally:
            if self._furnimove_bond_task is task:
                self._furnimove_bond_task = None

    def _start_furnimove_bond_request(self: AdjustableBedCoordinator, device: BLEDevice) -> None:
        """Request a bond without making it a prerequisite for app control.

        Android requests createBond and immediately connects. Bleak needs a live
        link, so this backend adaptation requests it after GATT discovery while
        controller startup continues. A completed request is not bond proof.
        """
        if self._bed_type != BED_TYPE_FURNIMOVE:
            return
        client = self._client
        if client is None:
            return
        if device.name is None:
            reason = "unnamed_device"
        elif device.name.lower().startswith("okinmat"):
            reason = "okinmat_name"
        elif self._device_reports_existing_bond(device):
            reason = "existing_os_bond"
        else:
            reason = "request"
        self._furnimove_bond_request = {"status": "not_requested", "reason": reason}
        if reason != "request":
            return
        self._furnimove_bond_request = {
            "status": "requested", "ordering": "connect_discover_then_background_request"
        }

        async def request() -> None:
            status = "completed"
            error: Exception | None = None
            try:
                async with asyncio.timeout(5):
                    await client.pair()
            except asyncio.CancelledError:
                status = "cancelled"
                raise
            except (NotImplementedError, TypeError) as err:
                status, error = "unsupported", err
            except TimeoutError as err:
                status, error = "timed_out", err
            except Exception as err:  # Optional pairing must not interrupt ordinary control.
                status, error = "failed", err
            finally:
                if client is self._client:
                    self._furnimove_bond_request["status"] = status
                    if error is not None:
                        self._furnimove_bond_request["error_type"] = type(error).__name__
                        _LOGGER.debug("FurniMove optional bond request %s: %s", status, error)

        self._furnimove_bond_task = self.entry.async_create_background_task(
            self.hass, request(), f"adjustable_bed_furnimove_bond_{self._address}"
        )
