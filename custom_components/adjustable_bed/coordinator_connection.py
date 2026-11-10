"""BLE connection lifecycle for the bed coordinator."""

# Each method annotates self as the coordinator so pyright checks its body
# against the full class. Pyright reports that annotation on a mixin as a
# general type issue, the only diagnostic this disables.
# pyright: reportGeneralTypeIssues=false

from __future__ import annotations

import asyncio
import contextlib
import logging
import random
import time
import traceback
from collections.abc import AsyncIterator, Callable, Coroutine, Iterator
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from bleak import BleakClient
from bleak.backends.device import BLEDevice
from bleak.exc import BleakError
from bleak_retry_connector import close_stale_connections_by_address, establish_connection
from homeassistant.components import bluetooth

from .adapter import (
    AdapterSelectionResult,
    detect_esphome_proxy,
    discover_services,
    get_ble_device_with_fallback,
    get_discovered_service_info,
    read_ble_device_info,
    select_adapter,
)
from .address_lock import async_get_connect_lock
from .bed_traits import bed_traits
from .beds.gmmotor.sessions import sleep_intent
from .ble_auth import is_ble_authentication_error as _is_ble_authentication_error
from .bluetooth_diagnostics import connection_reachability
from .bluetooth_transport import async_connection_paths, async_path_for_source, client_source
from .bond_verification import BondVerificationStatus
from .command_scheduler import ALL_COMMAND_RESOURCES, CommandOutcome
from .const import (
    ADAPTER_AUTO,
    BED_TYPE_ADJUSTABLE_LUMBAR,
    BED_TYPE_FURNIMOVE,
    BED_TYPE_GMMOTOR_SLEEP_MM,
    BED_TYPE_GMMOTOR_SLEEP_SXB,
    BED_TYPE_JENSEN,
    BED_TYPE_LEGGETT_GEN2,
    BED_TYPE_LEGGETT_OKIN,
    BED_TYPE_LEGGETT_PLATT,
    BED_TYPE_LIMOSS_REMOTE,
    BED_TYPE_OKIMAT,
    BED_TYPE_OKIN_RF_ECO_BT,
    BED_TYPE_OKIN_UUID,
    BED_TYPE_REVERIE_PAIRLINK,
    BED_TYPE_SLEEP_NUMBER,
    BED_TYPE_SLEEP_NUMBER_MCR,
    BED_TYPE_SLEEPYS_BOX25,
    BED_TYPE_SLEEPYS_ELITE_APP,
    BED_TYPE_VIBRADORM_APP,
    BED_TYPE_VMATBASIC,
    CONF_PAIRLINK_ROLE,
    CONF_VIBRADORM_APP_PROFILE,
    IDLE_DISCONNECT_KEEP_CONNECTED,
    LEGGETT_VARIANT_GEN2,
    OKIMAT_SERVICE_UUID,
    PAIRLINK_ROLE_PERIPHERAL,
    VARIANT_AUTO,
    VIBRADORM_APP_ONBOARDING_TIMEOUT_SECONDS,
    VIBRADORM_VMAT_ONBOARDING_TIMEOUT_SECONDS,
    grants_one_connection_per_pairing_window,
    requires_pairing,
)
from .controller_factory import create_controller
from .detection import (
    refine_dewertokin_star_protocol_from_name,
    refine_malouf_protocol_from_gatt,
    refine_nordic_uart_protocol_from_device_info,
    refine_okin_dot_protocol_from_gatt,
    refine_okin_shared_uuid_protocol_from_gatt,
    refine_qrrm_protocol_from_device_info,
)
from .diagnostic_payloads import new_connection_attempt_details
from .position_estimate import notify_connection_lost as notify_position_estimate_connection_lost
from .support_proxy_logs import capture_proxy_logs
from .unsupported import delete_pairing_required_issue

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from .beds.reverie.pairlink_runtime import PairlinkRuntime
    from .coordinator import AdjustableBedCoordinator

# Log under the coordinator's own logger, as before the split.
_LOGGER = logging.getLogger(f"{__package__}.coordinator")

# Share a connection across rapid taps, then give the physical remote back its link.
_COMMAND_BURST_GRACE_SECONDS = 1.0
_PAIRING_RELEASE_RESTORE_TIMEOUT = 5.0


class PairingOnlyConnectionActiveError(RuntimeError):
    """Raised when pair takeover would consume a receiver's one-use link."""


class _ConnectSession:
    """The ``ControllerSession`` one controller startup runs with."""

    def __init__(
        self,
        coordinator: AdjustableBedCoordinator,
        client: BleakClient | None,
        attempt_details: dict[str, Any],
        generation: int,
    ) -> None:
        self._coordinator = coordinator
        self._client = client
        self._attempt_details = attempt_details
        self._generation = generation

    @property
    def hass(self) -> HomeAssistant:
        return self._coordinator.hass

    @property
    def entry_id(self) -> str:
        return self._coordinator.entry.entry_id

    @property
    def address(self) -> str:
        return self._coordinator._address

    @property
    def name(self) -> str:
        return self._coordinator._name

    @property
    def model(self) -> str:
        return self._coordinator._ble_model or self._coordinator._get_model()

    @property
    def client(self) -> BleakClient | None:
        return self._client

    @property
    def angle_sensing_disabled(self) -> bool:
        return self._coordinator._disable_angle_sensing

    def disable_angle_sensing(self) -> None:
        self._coordinator._disable_angle_sensing = True

    def is_current(self) -> bool:
        client = self._client
        return (
            client is not None
            and self._coordinator._client is client
            and client.is_connected
            and self._coordinator._position_connection_generation == self._generation
        )

    async def async_start_notify(self) -> None:
        await self._coordinator.async_start_notify()

    async def async_record_verified_bond(self) -> None:
        await self._coordinator._async_record_verified_bond(self._attempt_details)

    def persist_capability_snapshot(self) -> None:
        self._coordinator._persist_capability_snapshot()

    def store_device_info(self, manufacturer: str | None, model: str | None) -> None:
        self._coordinator._store_ble_device_info(manufacturer, model)


class CoordinatorConnectionMixin:
    """Connecting, reconnecting, idle disconnect and connection ownership."""

    @contextlib.asynccontextmanager
    async def async_connection_operation_guard(
        self: AdjustableBedCoordinator,
    ) -> AsyncIterator[Callable[[str], Coroutine[object, object, bool]]]:
        """Keep the connection lane idle and expose its locked disconnect."""
        async with self._lock:
            yield self._async_disconnect_locked

    def _capability_reload_blocks_connection(self: AdjustableBedCoordinator) -> bool:
        """Return whether a deferred entity reload owns the next disconnected state."""
        link_is_up = self._client is not None and self._client.is_connected
        return (
            (self._pending_capability_reload or self._capability_reload_scheduled)
            and not self._capability_reload_deferrals
            and not link_is_up
        )

    @property
    def is_connected(self: AdjustableBedCoordinator) -> bool:
        """Return whether we are currently connected to the bed."""
        return self._client is not None and self._client.is_connected

    @property
    def is_connecting(self: AdjustableBedCoordinator) -> bool:
        """Return whether we are currently connecting to the bed."""
        return self._connecting

    @property
    def last_connected(self: AdjustableBedCoordinator) -> datetime | None:
        """Return the last connection timestamp."""
        return self._last_connected

    @property
    def last_disconnected(self: AdjustableBedCoordinator) -> datetime | None:
        """Return the last disconnection timestamp."""
        return self._last_disconnected

    @property
    def last_disconnect_reason(self: AdjustableBedCoordinator) -> str | None:
        """Return why the bed last disconnected (for diagnostics/UI).

        Common values: ``idle_timeout``, ``intentional``,
        ``authentication_failed``, ``unexpected``. Intentional/idle reasons mean
        the bed is fine and will reconnect on demand on the next command.
        """
        return self._last_disconnect_reason

    @property
    def connection_source(self: AdjustableBedCoordinator) -> str | None:
        """Return the adapter/source used for the current connection."""
        return self._connection_source

    @property
    def connection_rssi(self: AdjustableBedCoordinator) -> int | None:
        """Return the RSSI at connection time."""
        return self._connection_rssi

    @property
    def client(self: AdjustableBedCoordinator) -> BleakClient | None:
        """Return the BLE client (for diagnostics)."""
        return self._client

    @property
    def connection_history(self: AdjustableBedCoordinator) -> dict[str, Any]:
        """Return connection history for diagnostics."""
        return {
            "attempt_count": self._connection_attempt_count,
            "success_count": self._connection_success_count,
            "last_attempt": self._last_connection_attempt.isoformat()
            if self._last_connection_attempt
            else None,
            "last_error": self._last_connection_error,
            "last_error_type": self._last_connection_error_type,
            "last_disconnect_reason": self._last_disconnect_reason,
        }

    @property
    def adapter_details(self: AdjustableBedCoordinator) -> dict[str, Any]:
        """Return adapter selection details for diagnostics."""
        return {
            "preferred": self._preferred_adapter,
            "actual": self._actual_adapter,
            "available": self._available_adapters,
        }

    @property
    def connection_attempt_details(self: AdjustableBedCoordinator) -> list[dict[str, Any]]:
        """Return detailed recent connection attempts."""
        return list(self._connection_attempt_details)

    @property
    def connection_attempt_count(self: AdjustableBedCoordinator) -> int:
        """Return the monotonic number of connection attempts."""
        return self._connection_attempt_count

    async def async_connect(self: AdjustableBedCoordinator) -> bool:
        """Connect to the bed."""
        _LOGGER.debug("async_connect called for %s", self._address)
        async with self._lock:
            return await self._async_connect_locked()

    def _uses_persistent_connection(self: AdjustableBedCoordinator) -> bool:
        """Return True when this controller should stay connected indefinitely.

        Leggett & Platt Gen2 (LP Comfort Connect, 209-M001) is included
        conservatively until bonded reconnects are confirmed on hardware. We hold
        the link open for the lifetime of the entry in the meantime (issue #385).
        Trade-off: the physical remote cannot be used while Home Assistant is
        connected.

        Resolution order:
        1. The live controller's ``requires_persistent_connection`` (authoritative).
        2. The value cached from the last resolved controller — needed because
           ``_on_disconnect`` clears the controller *before* the reconnect
           decision runs, so an Okin/MlRM bed must still be recognised as
           non-persistent and get its reconnect timer.
        3. Before the first connect, the bed type's static ``persistent_connection``
           trait. ``auto``/``gen2`` ``leggett_platt`` entries assume Gen2;
           ``okin`` and ``mlrm`` do not (they reconnect normally).

        An idle timeout of 0 opts any bed into the same lifecycle unless
        Disconnect After Command is on (issue #700). Like persistent
        controllers, a dropped link then reconnects on the next command rather
        than on a timer, so receivers that drop idle links cannot storm.
        """
        if (
            self._idle_disconnect_seconds == IDLE_DISCONNECT_KEEP_CONNECTED
            and not self._disconnect_after_command
        ):
            return True
        controller = self._controller
        if controller is not None:
            return controller.requires_persistent_connection or (
                self._reconnect_stalled and controller.holds_link_after_stalled_reconnect
            )
        if self._persistent_connection_resolved is not None:
            return self._persistent_connection_resolved or (
                self._reconnect_stalled and self._holds_link_after_stall_resolved
            )
        return bed_traits(self._bed_type, self._protocol_variant).persistent_connection

    def _cache_persistent_connection_policy(self: AdjustableBedCoordinator) -> None:
        """Cache the live controller's persistence for decisions after a drop."""
        controller = self._controller
        if controller is None:
            return
        self._persistent_connection_resolved = controller.requires_persistent_connection
        self._holds_link_after_stall_resolved = controller.holds_link_after_stalled_reconnect

    def _disconnect_after_operation_enabled(self: AdjustableBedCoordinator) -> bool:
        """Return True when completed commands should promptly release the connection."""
        return self._disconnect_after_command and not self._uses_persistent_connection()

    async def _async_release_command_connection(self: AdjustableBedCoordinator) -> None:
        """Allow a short command burst before releasing the physical remote's link."""
        self._reset_disconnect_timer()

    def _idle_disconnect_delay(self: AdjustableBedCoordinator) -> float:
        """Keep the remote handoff short when disconnect-after-command is enabled."""
        if self._disconnect_after_operation_enabled():
            return _COMMAND_BURST_GRACE_SECONDS
        return self._idle_disconnect_seconds

    @contextlib.contextmanager
    def hold_command_connection(self: AdjustableBedCoordinator) -> Iterator[None]:
        """Start the idle timeout only after every side of a linked action settles."""
        if self._uses_persistent_connection():
            yield
            return
        self._command_connection_holds += 1
        self._cancel_disconnect_timer()
        try:
            yield
        finally:
            self._command_connection_holds -= 1
            if not self._command_connection_holds and self.is_connected:
                self._reset_disconnect_timer()

    def _auto_reconnect_enabled(self: AdjustableBedCoordinator) -> bool:
        """Return True when unexpected disconnects should schedule a reconnect timer."""
        controller = self.capability_controller
        if controller is not None and controller.requests_connection_recovery is True:
            return True

        # disconnect_after_command beds intentionally drop the link after each command
        # (and on idle), so an unexpected disconnect is expected behaviour, not a fault.
        # Scheduling a reconnect there causes a storm: some receivers (e.g. Keeson
        # BT40SA) require GATT activity within ~12s or they drop the link, and after a
        # few reconnect cycles enter a protection mode where they stop advertising
        # entirely until power-cycled (#369). The next user command reconnects on
        # demand, so no reconnect timer is needed for these beds.
        #
        if self._disconnect_after_operation_enabled():
            return False

        # Retaining an RF eco BT link (staircase, or FurniMove on that receiver)
        # must not disable recovery from an unexpected drop. Other FurniMove
        # receivers are not persistent, so this changes nothing for them.
        if self._bed_type in (BED_TYPE_OKIN_RF_ECO_BT, BED_TYPE_FURNIMOVE):
            return True

        if self._bed_type in (BED_TYPE_GMMOTOR_SLEEP_MM, BED_TYPE_GMMOTOR_SLEEP_SXB):
            return True

        # LP Comfort Connect is kept connected conservatively, and the new bond
        # makes an unexpected drop recoverable. Reconnect promptly while leaving
        # the established lifecycle behavior of other persistent protocols (such
        # as Sleep Number MCR) unchanged by this Gen2-specific fix.
        if self._bed_type == BED_TYPE_LEGGETT_GEN2:
            return True
        if self._bed_type == BED_TYPE_LEGGETT_PLATT and self._protocol_variant in (
            VARIANT_AUTO,
            LEGGETT_VARIANT_GEN2,
        ):
            return self._uses_persistent_connection()

        return not self._uses_persistent_connection()

    def _record_dropped_connection(
        self: AdjustableBedCoordinator, stage: str, attempt_details: dict[str, Any], attempt_start: float
    ) -> None:
        """Record a connect attempt whose link dropped before startup finished."""
        _LOGGER.warning("Connection to %s dropped during %s", self._address, stage)
        self._connecting = False
        self._last_connection_error = f"Connection dropped during {stage}"
        self._last_connection_error_type = ConnectionError.__name__
        # A failed (re)connect is not an intentional/idle disconnect; clear the
        # prior reason so the connectivity sensor doesn't keep reporting "idle"
        # after the attempt failed (issue #385 review).
        self._last_disconnect_reason = "connect_failed"
        attempt_details["total_elapsed_seconds"] = round(time.monotonic() - attempt_start, 3)
        attempt_details["result"] = "failed"
        attempt_details["error"] = self._last_connection_error
        attempt_details["error_type"] = self._last_connection_error_type
        attempt_details["error_category"] = "CONNECTION DROPPED"
        self._client = None
        self._controller = None
        self._notify_connection_state_change(False)
        self._connection_attempt_details.append(attempt_details)

    async def _async_cleanup_failed_connection(self: AdjustableBedCoordinator) -> None:
        """Release a failed-attempt client without scheduling auto-reconnect."""
        await self._async_cancel_furnimove_bond_request()
        client = self._client or self._vmat_unready_client
        if client is None:
            return

        _LOGGER.debug("Cleaning up failed connection attempt...")
        self._intentional_disconnect = True
        try:
            # Hold the address lock across the teardown. The connect attempt
            # released it before this runs, so an unprotected disconnect here
            # could land inside a competing caller's connect and abort it —
            # the same hazard the lock was added to prevent (issue #385).
            # Reentrant, so a caller that still holds it is unaffected.
            connect_lock = async_get_connect_lock(self.hass, self._address)
            if connect_lock.retained_setup_client is client:
                await connect_lock.async_release_setup_client()
            else:
                async with connect_lock:
                    try:
                        await client.disconnect()
                    finally:
                        if self.entry.data.get(CONF_VIBRADORM_APP_PROFILE) == "vmat" and client.is_connected:
                            connect_lock.retain_setup_client(client)
            _LOGGER.debug("Disconnect cleanup successful")
        except Exception as disconnect_err:
            _LOGGER.debug(
                "Error during disconnect cleanup: %s (%s)",
                disconnect_err,
                type(disconnect_err).__name__,
            )
        finally:
            if self.entry.data.get(CONF_VIBRADORM_APP_PROFILE) == "vmat" and client.is_connected:
                self._client = client
                self._vmat_unready_client = client
            else:
                self._client = None
                if self._vmat_unready_client is client:
                    self._vmat_unready_client = None
            self._controller = None
            self._intentional_disconnect = False

    async def _async_connect_locked(self: AdjustableBedCoordinator, reset_timer: bool = True) -> bool:
        """Allow automatic auth recovery before asking the user to re-pair."""
        if self._shutting_down and self.entry.data.get(CONF_VIBRADORM_APP_PROFILE) == "vmat":
            return False
        if self._pairing_transfer_active:
            _LOGGER.debug(
                "Skipping connection to %s while ownership transfers to a paired entry",
                self._address,
            )
            return False
        if (
            self._bed_type == BED_TYPE_REVERIE_PAIRLINK
            and self.entry.options.get(
                CONF_PAIRLINK_ROLE, self.entry.data.get(CONF_PAIRLINK_ROLE)
            ) == PAIRLINK_ROLE_PERIPHERAL
        ):
            controller = self._controller
            return bool(controller is not None and controller.disconnected_transport_ready)
        try:
            if self._bed_type == BED_TYPE_SLEEP_NUMBER and (
                self._client is None or not self._client.is_connected or self._controller is None
            ):
                # A configured bed can pair and verify Auth here without going
                # through config flow. Keep that attempt for a later bundle.
                async with capture_proxy_logs(
                    self.hass, self._address, self._preferred_adapter, retain=True
                ):
                    return await self._async_connect_attempts_locked(reset_timer)
            return await self._async_connect_attempts_locked(reset_timer)
        finally:
            # A verified retry clears this evidence. An inconclusive retry,
            # exhausted attempts or cancellation must still surface the repair.
            if self._has_unresolved_auth_failure():
                await self._async_raise_pairing_issue()

    async def _async_connect_attempts_locked(  # pyright: ignore[reportGeneralTypeIssues]
        self: AdjustableBedCoordinator, reset_timer: bool = True
    ) -> bool:
        """Connect to the bed (must hold lock)."""
        if self._capability_reload_blocks_connection():
            _LOGGER.debug(
                "Deferring connection to %s until its capability reload completes",
                self._address,
            )
            return False
        # Clear any prior manual/idle disconnect marker before a fresh connect attempt.
        self._intentional_disconnect = False

        if self._vmat_unready_client is not None and not self._vmat_unready_client.is_connected:
            self._vmat_unready_client = None
        if self._vmat_unready_link_pending():
            await self._async_cleanup_failed_connection()
            if self._vmat_unready_link_pending():
                return False

        if self._client is not None and self._client.is_connected:
            if self._controller is not None:
                _LOGGER.debug("Already connected to %s, reusing connection", self._address)
                if reset_timer:
                    self._reset_disconnect_timer()
                return True
            # Connected but half-initialised. Release the orphan before making a
            # fresh attempt: establish_connection() would otherwise overwrite
            # self._client and leak this still-live link, and the
            # stale-connection cleanup only operates on BlueZ backends.
            _LOGGER.debug(
                "Releasing half-initialised connection to %s before reconnecting",
                self._address,
            )
            await self._async_cleanup_failed_connection()
            if self._vmat_unready_link_pending():
                return False

        # Routine reconnects after an intentional/idle disconnect are expected for
        # non-persistent beds and shouldn't spam the log. Only the first successful
        # connection of the entry's lifetime logs the happy path at INFO; subsequent
        # on-demand reconnects log at DEBUG (still captured with debug logging enabled).
        # Retries, warnings, and failures keep their levels regardless (see below).
        connect_log = _LOGGER.info if self._last_connected is None else _LOGGER.debug

        attempt_limit = self._max_retries
        multipath = (
            sum(path.can_connect for path in async_connection_paths(self.hass, self._address)) > 1
        )
        if multipath:
            # HA may spend several attempts penalizing a strong but unusable
            # proxy before selecting a weaker working one. Keep that fallback
            # inside this request instead of requiring another user action.
            attempt_limit = max(attempt_limit, 5)

        connect_log(
            "Initiating BLE connection to %s (max %d attempts)",
            self._address,
            attempt_limit,
        )
        overall_start = time.monotonic()
        # Track adapters that ran out of connection slots so we can try
        # alternatives on subsequent retries (issue #152).
        exhausted_adapters: set[str] = set()
        adapter_result: AdapterSelectionResult | None = None

        attempt = 0
        protocol_correction_pairing_retry_reserved = False
        stale_gatt_retry_extensions = 0
        # A pending source may come from a runtime command failure. It stays
        # pending until authentication has actually been exercised on that proxy.
        unverified_stale_gatt_source: str | None = None
        stale_gatt_pairing_reserved = False
        pairlink_transport_failed = False
        while True:
            # The cleared proxy's fresh handles still failed authentication, so
            # its bond really is gone and pairing is now justified.
            stale_gatt_verification_failed = bool(
                unverified_stale_gatt_source
                and self._auth_failure_source == unverified_stale_gatt_source
            )
            if unverified_stale_gatt_source and not stale_gatt_verification_failed:
                # The last attempt failed without authenticating on the cleared
                # proxy: it never connected, HA routed it elsewhere, or it broke
                # before the probe. That proxy still deserves its no-pair check,
                # even if another path just cleared its own cache, because it
                # holds the bond being recovered.
                self._stale_gatt_retry_source = unverified_stale_gatt_source
                self._skip_pair_next_attempt = True
            unverified_stale_gatt_source = None
            if attempt >= attempt_limit:
                # A stale proxy cache cleared on the last attempt still gets the
                # rediscovered, no-pair verification it was promised (#660).
                # Two extensions cover one reroute away from the cleared proxy
                # while keeping the loop bounded.
                # One more covers pairing after the verification proved the bond
                # missing, which the plain budget would otherwise have spent.
                if self._stale_gatt_retry_source and stale_gatt_retry_extensions < 2:
                    stale_gatt_retry_extensions += 1
                elif stale_gatt_verification_failed and not stale_gatt_pairing_reserved:
                    stale_gatt_pairing_reserved = True
                else:
                    break
                attempt_limit += 1
            stale_gatt_retry_source = self._stale_gatt_retry_source
            self._stale_gatt_retry_source = None
            unverified_stale_gatt_source = stale_gatt_retry_source
            self._auth_failure_source = None
            if self._vmat_unready_link_pending():
                break
            attempt_index = attempt
            attempt += 1
            attempt_number = attempt_index + 1
            pairlink_transport_failed = False
            attempt_start = time.monotonic()
            attempt_details = new_connection_attempt_details(
                attempt_number, self._preferred_adapter
            )
            # Track connection attempt for diagnostics (issue #168)
            self._connection_attempt_count += 1
            self._last_connection_attempt = datetime.now(UTC)

            # On retries, add a delay before attempting to give the Bluetooth stack time to reset
            if attempt_index > 0:
                retry_exponent = attempt_index - 1
                if multipath:
                    retry_exponent = min(retry_exponent, 1)
                base_delay = self._retry_base_delay * (2**retry_exponent)
                jitter = random.uniform(1 - self._retry_jitter, 1 + self._retry_jitter)
                pre_retry_delay = base_delay * jitter
                _LOGGER.info(
                    "Waiting %.1fs before connection retry %d/%d to %s...",
                    pre_retry_delay,
                    attempt_number,
                    attempt_limit,
                    self._address,
                )
                await asyncio.sleep(pre_retry_delay)

            try:
                # A connection path belongs only to the link that established
                # it. If this attempt fails before establish_connection()
                # returns, retaining the previous path would attribute the
                # failure to an unrelated host adapter or proxy.
                self._connection_path = None
                _LOGGER.debug(
                    "Connection attempt %d/%d: Looking up device %s via HA Bluetooth (preferred adapter: %s)",
                    attempt_number,
                    attempt_limit,
                    self._address,
                    self._preferred_adapter,
                )

                # Log available Bluetooth adapters/scanners
                try:
                    scanner_count = bluetooth.async_scanner_count(self.hass, connectable=True)
                    _LOGGER.debug(
                        "Available Bluetooth scanners (connectable): %d",
                        scanner_count,
                    )
                    # Capture available adapters for diagnostics (issue #168)
                    try:
                        scanners = bluetooth.async_current_scanners(self.hass)
                        self._available_adapters = [
                            getattr(scanner, "source", "unknown") for scanner in scanners
                        ]
                    except Exception as exc:
                        _LOGGER.debug(
                            "Failed to capture adapters via bluetooth.async_current_scanners: %s",
                            exc,
                        )
                except Exception as err:
                    _LOGGER.debug("Could not get scanner count: %s", err)

                # Select best adapter and get device, excluding any adapters
                # that previously ran out of connection slots
                adapter_result = await select_adapter(
                    self.hass,
                    self._address,
                    # Steer a stale-cache verification to the proxy that was
                    # cleared. HA can still reroute; that is handled below.
                    stale_gatt_retry_source or self._preferred_adapter,
                    exclude_adapters=exhausted_adapters or None,
                )
                attempt_details["selected_source"] = adapter_result.source
                attempt_details["selected_rssi"] = adapter_result.rssi
                attempt_details["selected_connectable"] = adapter_result.connectable
                attempt_details["non_connectable_fallback_used"] = (
                    adapter_result.connectable is False
                )
                attempt_details["visible_sources"] = list(adapter_result.available_sources)
                device = adapter_result.device

                if device is None:
                    lookup_elapsed = time.monotonic() - attempt_start
                    attempt_details["lookup_elapsed_seconds"] = round(lookup_elapsed, 3)
                    attempt_details["total_elapsed_seconds"] = round(lookup_elapsed, 3)
                    attempt_details["result"] = "device_not_found"
                    _LOGGER.warning(
                        "Device %s NOT FOUND in Bluetooth scanner after %.1fs (attempt %d/%d). "
                        "Bed may be powered off, out of range, or connected to another device.",
                        self._address,
                        lookup_elapsed,
                        attempt_number,
                        attempt_limit,
                    )
                    # Log what devices ARE visible
                    try:
                        discovered = get_discovered_service_info(
                            self.hass,
                            include_non_connectable=True,
                        )
                        if discovered:
                            _LOGGER.debug(
                                "Currently visible BLE devices (%d total):",
                                len(discovered),
                            )
                            for svc_info in discovered[:10]:  # Limit to first 10
                                _LOGGER.debug(
                                    "  - %s (name: %s, rssi: %s, source: %s, connectable: %s)",
                                    svc_info.address,
                                    svc_info.name or "Unknown",
                                    getattr(svc_info, "rssi", "N/A"),
                                    getattr(svc_info, "source", "N/A"),
                                    getattr(svc_info, "connectable", None),
                                )
                            if len(discovered) > 10:
                                _LOGGER.debug("  ... and %d more devices", len(discovered) - 10)
                        else:
                            _LOGGER.debug("No BLE devices currently visible")
                    except Exception as err:
                        _LOGGER.debug("Could not enumerate visible devices: %s", err)
                    self._connection_attempt_details.append(attempt_details)
                    # Don't sleep here - the retry backoff at loop start handles delays
                    continue

                # Log detailed device info including which adapter discovered it
                device_source = None
                if hasattr(device, "details") and isinstance(device.details, dict):
                    device_source = device.details.get("source")
                # Local BlueZ devices carry no "source" in their details.
                device_source = device_source or adapter_result.source

                lookup_elapsed = time.monotonic() - attempt_start
                attempt_details["lookup_elapsed_seconds"] = round(lookup_elapsed, 3)
                connect_log(
                    "✓ Device %s FOUND in %.1fs (name: %s) via adapter: %s",
                    self._address,
                    lookup_elapsed,
                    device.name or "Unknown",
                    device_source or "unknown",
                )
                if adapter_result.connectable is False:
                    _LOGGER.warning(
                        "Device %s was recovered from a non-connectable scanner record. "
                        "This usually means the Bluetooth proxy or scanner classified the "
                        "advertisement incorrectly.",
                        self._address,
                    )
                _LOGGER.debug(
                    "Device details: address=%s, name=%s, details=%s",
                    device.address,
                    device.name,
                    getattr(device, "details", "N/A"),
                )
                if device.name:
                    self._record_observed_ble_device_name(device.name)

                if self._preferred_adapter and self._preferred_adapter != ADAPTER_AUTO:
                    if device_source == self._preferred_adapter:
                        _LOGGER.info(
                            "✓ Device discovered by preferred adapter: %s",
                            self._preferred_adapter,
                        )
                    else:
                        _LOGGER.warning(
                            "⚠ Device discovered by %s, but preferred adapter is %s - connection may use different adapter",
                            device_source,
                            self._preferred_adapter,
                        )

                # Detect ESPHome proxy (logs info if detected)
                detect_esphome_proxy(self.hass, self._address)

                # Use bleak-retry-connector for reliable connection establishment
                # This handles ESPHome Bluetooth proxy connections properly
                # Using standard BleakClient (not cached) for better compatibility
                # with devices that have connection stability issues
                connect_start = time.monotonic()
                connect_log(
                    "Attempting BLE GATT connection to %s (timeout: %.0fs)...",
                    self._address,
                    self._connection_timeout,
                )

                # Always provide a callback so bleak-retry-connector can refresh the
                # BLEDevice between retries. In auto mode this prevents using a stale
                # device object from an older scan snapshot.
                target_source: str | None = None
                if self._preferred_adapter and self._preferred_adapter != ADAPTER_AUTO:
                    target_source = self._preferred_adapter
                elif adapter_result.source and adapter_result.source != "unknown":
                    target_source = adapter_result.source

                def _get_fresh_device_for_connection(
                    selected_source: str | None = target_source,
                    current_attempt: dict[str, Any] = attempt_details,
                ) -> BLEDevice:
                    """Return a fresh BLEDevice from the current scanner data."""
                    discovered = get_discovered_service_info(
                        self.hass,
                        include_non_connectable=True,
                    )
                    for svc_info in discovered:
                        if svc_info.address.upper() != self._address:
                            continue
                        svc_source = getattr(svc_info, "source", None)
                        if selected_source is None or svc_source == selected_source:
                            if isinstance(svc_source, str) and svc_source:
                                current_attempt["actual_source"] = svc_source
                            if svc_info.device.name:
                                self._record_observed_ble_device_name(svc_info.device.name)
                            _LOGGER.debug(
                                "ble_device_callback returning device from %s (RSSI: %s, connectable=%s)",
                                svc_source or "unknown",
                                getattr(svc_info, "rssi", "N/A"),
                                getattr(svc_info, "connectable", None),
                            )
                            return svc_info.device

                    if selected_source is not None:
                        _LOGGER.debug(
                            "Target adapter %s not currently seeing %s, falling back to default lookup",
                            selected_source,
                            self._address,
                        )

                    fallback, connectable = get_ble_device_with_fallback(
                        self.hass,
                        self._address,
                        allow_non_connectable=True,
                    )
                    if fallback is None:
                        raise BleakError(f"Device {self._address} not found")
                    fallback_details = getattr(fallback, "details", None)
                    fallback_source = (
                        fallback_details.get("source")
                        if isinstance(fallback_details, dict)
                        else None
                    )
                    if isinstance(fallback_source, str) and fallback_source:
                        current_attempt["actual_source"] = fallback_source
                    if fallback.name:
                        self._record_observed_ble_device_name(fallback.name)
                    if connectable is False:
                        _LOGGER.debug(
                            "ble_device_callback falling back to non-connectable record for %s",
                            self._address,
                        )
                    return fallback

                ble_device_callback: Callable[[], BLEDevice] | None = (
                    _get_fresh_device_for_connection
                )

                # Determine if this bed type needs pairing and if pairing is supported.
                # Once the bed is bonded, future connections must skip pair=True:
                # some ESP-IDF/ESPHome stacks respond with auth error 82 and can
                # leave the proxy stuck in ESTABLISHED state when asked to re-pair
                # an already-bonded device.
                pairing_details = attempt_details["pairing"]
                (
                    bed_requires_pairing,
                    use_pairing,
                    pair_after_service_discovery,
                ) = self._prepare_pairing_attempt(
                    device,
                    pairing_details,
                    source=adapter_result.source,
                )
                keep_connecting_through_startup = self._uses_persistent_connection()
                if use_pairing:
                    _LOGGER.info(
                        "Pairing enabled for %s (bed type: %s, variant: %s, ordering: %s) - "
                        "GATT services cache disabled to force fresh discovery",
                        self._name,
                        self._bed_type,
                        self._protocol_variant,
                        pairing_details["ordering"],
                    )

                # Mark that we're connecting to suppress spurious disconnect warnings
                # during bleak's internal retry process
                self._connecting = True
                # Notify callbacks so binary sensor can show "connecting" state
                self._notify_connection_state_change(False)
                # Serialize with the config flow, repair flow and diagnostic so
                # an overlapping attempt cannot abort this one (issue #385). The
                # lock must cover the stale-connection cleanup below as well as
                # the connect itself: that cleanup disconnects the address, so
                # running it outside the lock would tear down a client another
                # caller is holding under lock protection.
                connect_lock = async_get_connect_lock(self.hass, self._address)
                await connect_lock.acquire()
                try:
                    # Best-effort BlueZ cleanup. Some failed attempts leave stale
                    # pending connections behind, which can cause repeated
                    # connect timeouts.
                    try:
                        await close_stale_connections_by_address(self._address)
                    except (OSError, BleakError) as err:
                        _LOGGER.debug(
                            "Could not close stale connections for %s: %s",
                            self._address,
                            err,
                        )
                    except Exception:
                        _LOGGER.warning(
                            "Unexpected error closing stale connections for %s",
                            self._address,
                            exc_info=True,
                        )

                    # Use max_attempts=1 here since outer loop handles retries
                    # Disable the services cache to force fresh GATT discovery for
                    # every pairing-required bed, not just the pair=True attempt.
                    # ESPHome proxies ignore this and serve their cached table;
                    # an authentication failure clears that cache instead.
                    # These devices expose different services/characteristics
                    # depending on bond state, so a stale cache from a previous
                    # non-paired connection would make characteristic lookups (and
                    # the post-connect bond probe) fail. This also covers the
                    # no-pair verify retry after a failed pair attempt, which must
                    # see live services to confirm the bond instead of looping.
                    # FurniMove startup subscribes immediately. On BlueZ a
                    # cached collection can precede the live GATT objects (#633).
                    disable_cache = bed_requires_pairing or self._bed_type == BED_TYPE_FURNIMOVE
                    onboarding_deadline = (
                        asyncio.get_running_loop().time() + (
                            VIBRADORM_VMAT_ONBOARDING_TIMEOUT_SECONDS
                            if self.entry.data.get(CONF_VIBRADORM_APP_PROFILE) == "vmat"
                            else VIBRADORM_APP_ONBOARDING_TIMEOUT_SECONDS
                        )
                        if self._bed_type == BED_TYPE_VIBRADORM_APP else None
                    )
                    connection_deadline = (
                        None if self._bed_type == BED_TYPE_VIBRADORM_APP
                        and self._ble_bond_established
                        and self._unverified_marker_applies(adapter_result.source)
                        else onboarding_deadline
                    )
                    live_link_bonded = False
                    try:
                        await self._async_cancel_furnimove_bond_request()
                        async with asyncio.timeout_at(connection_deadline):
                            self._client = await establish_connection(
                                BleakClient,
                                device,
                                self._name,
                                disconnected_callback=self._on_disconnect,
                                max_attempts=1,
                                timeout=(
                                    5.0 if self.entry.data.get(CONF_VIBRADORM_APP_PROFILE) == "vmat"
                                    and not self._ble_bond_established else self._connection_timeout
                                ),
                                ble_device_callback=ble_device_callback,
                                pair=use_pairing and not pair_after_service_discovery,
                                use_services_cache=not disable_cache,
                            )
                        self._start_furnimove_bond_request(device)
                        if self._bed_type == BED_TYPE_VIBRADORM_APP:
                            # Pairing must use the path actually selected by HA,
                            # including a reroute away from the planned scanner.
                            actual_source = client_source(self._client) or "unknown"
                            self._connection_path = async_path_for_source(self.hass, actual_source)
                            self._last_bond_evidence = None
                        # LP Control and Sleep Number request the bond after the
                        # unbonded GATT link has reported SERVICES_DISCOVERED.
                        # establish_connection() returns after Bleak has loaded
                        # the service collection, so pairing here preserves that
                        # proven application ordering on BlueZ as well.
                        bond_created = True
                        if pair_after_service_discovery or self._bed_type == BED_TYPE_VIBRADORM_APP:
                            _LOGGER.info(
                                "Connected to %s and discovered services; "
                                "creating the BLE bond now",
                                self._address,
                            )
                            if self._bed_type == BED_TYPE_VIBRADORM_APP:
                                bond_created = await self._async_pair_on_live_link(
                                    pairing_details, onboarding_deadline=onboarding_deadline
                                )
                            else:
                                bond_created = await self._async_pair_on_live_link(pairing_details)
                            if self.entry.data.get(CONF_VIBRADORM_APP_PROFILE) == "vmat":
                                if not bond_created:
                                    raise ConnectionError("VMAT requires verified native bond/address proof before control")
                                if pairing_details.get("vmat_setup_started"):
                                    # Setup closes its link. Start a distinct ordinary
                                    # control session and verify the route actually used.
                                    self._client = await establish_connection(
                                        BleakClient, device, self._name,
                                        disconnected_callback=self._on_disconnect,
                                        max_attempts=1, timeout=10.0,
                                        ble_device_callback=ble_device_callback,
                                        use_services_cache=False,
                                    )
                                    actual_source = client_source(self._client) or "unknown"
                                    self._connection_path = async_path_for_source(self.hass, actual_source)
                                    if not await self._async_observe_native_bond(pairing_details):
                                        raise ConnectionError("VMAT control link has no verified native bond/address proof")
                        # If we get here with pairing enabled, mark it as supported
                        if self._bed_type == BED_TYPE_VIBRADORM_APP:
                            pairing_details["adapter_pairing_supported"] = self._pairing_supported
                            pairing_details["connection_result"] = pairing_details["native_pairing"]
                        elif use_pairing and bond_created:
                            self._pairing_supported = True
                            if self._bed_type not in (
                                BED_TYPE_SLEEP_NUMBER,
                                BED_TYPE_VIBRADORM_APP,
                            ):
                                self._mark_ble_bond_established()
                            pairing_details["adapter_pairing_supported"] = True
                            pairing_details["connection_result"] = "pairing_connection_succeeded"
                            live_link_bonded = (
                                pair_after_service_discovery
                                and self._bed_type != BED_TYPE_SLEEP_NUMBER
                            )
                            if live_link_bonded:
                                # An earlier session's auth failure is retired;
                                # the probe below records any fresh one.
                                self._last_bond_evidence = None
                        elif use_pairing:
                            # Advisory bond failed; the link is up and stays up.
                            # _async_pair_on_live_link already recorded whether
                            # the backend supports pairing at all.
                            pairing_details["connection_result"] = (
                                "advisory_bond_failed_link_retained"
                            )
                        else:
                            pairing_details["connection_result"] = "connected_without_pairing"
                    except (NotImplementedError, TypeError) as pair_err:
                        # NotImplementedError: ESPHome < 2024.3.0 doesn't support pairing
                        # TypeError: older bleak-retry-connector doesn't have pair kwarg
                        if use_pairing:
                            # A post-discovery pair() failure leaves a live
                            # unbonded client, unlike a failed pair=True connect.
                            # Release it before the compatibility retry.
                            if self._client is not None:
                                client = self._client
                                self._intentional_disconnect = True
                                try:
                                    with contextlib.suppress(Exception):
                                        await client.disconnect()
                                finally:
                                    self._client = None
                                    self._intentional_disconnect = False
                            _LOGGER.warning(
                                "Pairing not supported by Bluetooth adapter: %s. "
                                "If using ESPHome proxy, update to ESPHome >= 2024.3.0. "
                                "Retrying connection without pairing...",
                                pair_err,
                            )
                            # Remember that pairing isn't supported to avoid repeated warnings
                            self._pairing_supported = False
                            pairing_details["adapter_pairing_supported"] = False
                            pairing_details["connection_result"] = (
                                "pairing_unsupported_retry_without_pairing"
                            )
                            pairing_details["error"] = str(pair_err)
                            pairing_details["error_type"] = type(pair_err).__name__
                            # Retry without pairing but still disable cache since
                            # this bed type requires pairing and may have stale data
                            self._client = await establish_connection(
                                BleakClient,
                                device,
                                self._name,
                                disconnected_callback=self._on_disconnect,
                                max_attempts=1,
                                timeout=self._connection_timeout,
                                ble_device_callback=ble_device_callback,
                                use_services_cache=False,
                            )
                            pairing_details["connection_result"] = (
                                "pairing_unsupported_connected_without_pairing"
                            )
                            # The link that actually came up did not pair, so the
                            # bond probe must judge it as unpaired. Leaving the
                            # planned value here would stop the unreliable-marker
                            # latch from ever releasing on adapters that lack
                            # pair= support (ESPHome < 2024.3.0).
                            self._attempt_used_pairing = False
                        else:
                            raise
                    except (BleakError, TimeoutError, OSError) as pair_err:
                        pairlink_transport_failed = self._client is None or not self._client.is_connected
                        # If pairing was requested and the connection failed,
                        # a BLE bond may already exist from a previous session;
                        # re-pairing on top of an existing bond causes auth
                        # failures on some ESP-IDF stacks and leaves the ESPHome
                        # proxy connection stuck.  Skip pair=True on the *next*
                        # attempt only (transient, in-memory) so the outer retry
                        # loop can reconnect — but do NOT persist a bond marker,
                        # since the failure may simply mean the base was not in
                        # its pairing window.  The post-connect bond probe
                        # (_async_verify_bonded) then confirms whether the link
                        # is really bonded and re-pairs if not.
                        if use_pairing:
                            _LOGGER.warning(
                                "Connection with pairing failed for %s: %s. "
                                "Next attempt will connect without re-pairing; "
                                "bond state will be verified after connecting.",
                                self._name,
                                pair_err,
                            )
                            self._pairing_supported = True
                            self._skip_pair_next_attempt = True
                            pairing_details["adapter_pairing_supported"] = True
                            pairing_details["connection_result"] = "pairing_connection_failed"
                            pairing_details["error"] = str(pair_err)
                            pairing_details["error_type"] = type(pair_err).__name__
                            raise
                        raise
                finally:
                    connect_lock.release()
                    if not keep_connecting_through_startup:
                        self._connecting = False
                    # Don't notify here - the connect success/failure paths will notify

                # Determine which adapter was actually used for connection.
                # Recorded here, immediately after the connect, because bond
                # verification runs before controller startup and must be able
                # to attribute a failure to the transport that carried it.
                actual_adapter = client_source(self._client) or "unknown"

                # Track successful connection for diagnostics (issue #168)
                self._connection_success_count += 1
                self._actual_adapter = actual_adapter
                self._connection_path = async_path_for_source(self.hass, actual_adapter)
                self._last_connection_error = None
                self._last_connection_error_type = None
                attempt_details["actual_source"] = actual_adapter

                connect_elapsed = time.monotonic() - connect_start
                total_elapsed = time.monotonic() - attempt_start
                attempt_details["connect_elapsed_seconds"] = round(connect_elapsed, 3)
                attempt_details["total_elapsed_seconds"] = round(total_elapsed, 3)
                attempt_details["result"] = "connected"
                connect_log(
                    "✓ CONNECTED to %s in %.1fs (GATT: %.1fs) via adapter: %s",
                    self._address,
                    total_elapsed,
                    connect_elapsed,
                    actual_adapter,
                )

                if self._preferred_adapter and self._preferred_adapter != ADAPTER_AUTO:
                    if actual_adapter == self._preferred_adapter:
                        _LOGGER.info(
                            "✓ Connection using preferred adapter: %s",
                            self._preferred_adapter,
                        )
                    elif actual_adapter != "unknown":
                        _LOGGER.warning(
                            "⚠ Connected via %s instead of preferred adapter %s",
                            actual_adapter,
                            self._preferred_adapter,
                        )

                # Small delay to let connection stabilize before operations.
                # Sleep Number MCR/Fuzion and Jensen beds disconnect quickly
                # if there is idle time after connect, so skip the delay for
                # bed types that need the notification channel established
                # immediately.
                if self._bed_type not in {
                    BED_TYPE_SLEEP_NUMBER_MCR,
                    BED_TYPE_SLEEP_NUMBER,
                    BED_TYPE_JENSEN,
                    BED_TYPE_SLEEPYS_ELITE_APP,
                    BED_TYPE_VIBRADORM_APP,
                }:
                    await asyncio.sleep(self._post_connect_delay)

                # The bed may disconnect during the stabilisation delay
                # (the _on_disconnect callback clears self._client).
                if self._client is None or not self._client.is_connected:
                    _LOGGER.warning(
                        "Connection to %s dropped during post-connect stabilisation",
                        self._address,
                    )
                    self._connecting = False
                    self._connection_attempt_details.append(attempt_details)
                    continue

                # Log connection details
                _LOGGER.debug(
                    "BleakClient connected: is_connected=%s, mtu_size=%s",
                    self._client.is_connected,
                    getattr(self._client, "mtu_size", "N/A"),
                )

                # Discover services and log hierarchy
                attempt_details["service_discovery"]["attempted"] = True
                service_discovery_success = await discover_services(self._client, self._address)
                attempt_details["service_discovery"]["success"] = service_discovery_success
                attempt_details["service_discovery"]["service_count"] = (
                    len(list(self._client.services)) if self._client.services else 0
                )

                # Validate expected services are present (for beds requiring pairing)
                if bed_requires_pairing and self._client.services:
                    discovered_uuids = {svc.uuid.lower() for svc in self._client.services}
                    _LOGGER.debug(
                        "Discovered service UUIDs for %s: %s",
                        self._name,
                        sorted(discovered_uuids),
                    )

                    # Get expected service UUID for this bed type
                    expected_service = OKIMAT_SERVICE_UUID.lower()
                    if (
                        self._bed_type
                        in (BED_TYPE_OKIMAT, BED_TYPE_OKIN_UUID, BED_TYPE_LEGGETT_OKIN)
                        and expected_service not in discovered_uuids
                    ):
                        _LOGGER.warning(
                            "⚠ Expected OKIN service UUID %s not found in discovered "
                            "services for %s. This usually means pairing/bonding failed. "
                            "Discovered services: %s. Try removing and re-adding the "
                            "device with 'Pair Now' option.",
                            expected_service,
                            self._name,
                            sorted(discovered_uuids),
                        )

                # Actively verify the encrypted link is bonded for beds that
                # require pairing. A connection — even establish_connection with
                # pair=True — can succeed while the link is still unbonded: every
                # encrypted characteristic then fails with GATT error=5. Skip the
                # delay-sensitive bed types whose protocol handshake must run
                # first (Sleep Number, Jensen).
                if (
                    bed_requires_pairing
                    and self._client is not None
                    and self._client.services
                    and self._bed_type
                    not in (
                        BED_TYPE_SLEEP_NUMBER,
                        BED_TYPE_SLEEP_NUMBER_MCR,
                        BED_TYPE_JENSEN,
                        BED_TYPE_VIBRADORM_APP,
                    )
                    and not await self._async_verify_bonded(
                        attempt_details, defer_pairing_issue=True
                    )
                ):
                    # _async_verify_bonded cleared the bond marker and
                    # disconnected. Retry before raising a repair; the next attempt
                    # requests pair=True again (the skip flag was consumed).
                    _LOGGER.warning(
                        "Bed %s connected but the BLE link is not bonded; retrying with pairing.",
                        self._address,
                    )
                    self._connecting = False
                    self._connection_attempt_details.append(attempt_details)
                    continue

                if live_link_bonded and (
                    self._last_bond_evidence is None
                    or self._last_bond_evidence.status is not BondVerificationStatus.AUTH_FAILED
                ):
                    # The bed accepted an explicit bond on this link and the
                    # probe saw no authentication failure: the same proof the
                    # pairing repair accepts. Without this, a bed whose probe is
                    # always inconclusive (LP Gen2 has no DIS) would keep an
                    # earlier session's repair open while working (issue #709).
                    await delete_pairing_required_issue(self.hass, self._address)

                # Some beds (Sleep Number MCR/Fuzion, Jensen) disconnect if
                # there is too much delay between the BLE connection and the
                # protocol handshake.  For those bed types we defer the
                # Device Information Service reads until after the
                # notification channel and handshake are established.
                _defer_device_info = self._bed_type in {
                    BED_TYPE_SLEEP_NUMBER_MCR,
                    BED_TYPE_SLEEP_NUMBER,
                    BED_TYPE_JENSEN,
                    BED_TYPE_SLEEPYS_ELITE_APP,
                }

                ble_manufacturer: str | None = None
                ble_model: str | None = None

                if (
                    not _defer_device_info
                    and not bed_traits(self._bed_type, self._protocol_variant).owns_device_info_reads
                    and self._bed_type not in {
                        BED_TYPE_VIBRADORM_APP,
                        BED_TYPE_VMATBASIC,
                        BED_TYPE_LIMOSS_REMOTE,
                        # Its controller performs the app's single raw 2A29 read.
                        BED_TYPE_ADJUSTABLE_LUMBAR,
                        # FurniMove owns its staggered reads after subscriptions.
                        BED_TYPE_FURNIMOVE,
                    }
                ):
                    if self._device_info_read_done:
                        ble_manufacturer = self._ble_manufacturer
                        ble_model = self._ble_model
                        _LOGGER.debug(
                            "Reusing cached device info for %s (manufacturer=%s, model=%s)",
                            self._address,
                            ble_manufacturer,
                            ble_model,
                        )
                    else:
                        ble_manufacturer, ble_model = await read_ble_device_info(
                            self._client, self._address
                        )
                        self._store_ble_device_info(ble_manufacturer, ble_model)

                # The awaited bond probe and device-info reads can lose the link,
                # and _on_disconnect then clears the client used below.
                if self._client is None or not self._client.is_connected:
                    self._record_dropped_connection(
                        "post-connect setup", attempt_details, attempt_start
                    )
                    continue

                previous_bed_type = self._bed_type
                observed_device_name = self._observed_ble_device_name or device.name
                corrected_bed_type = refine_malouf_protocol_from_gatt(
                    self._bed_type,
                    self._client.services,
                )
                corrected_bed_type = refine_okin_shared_uuid_protocol_from_gatt(
                    corrected_bed_type,
                    self._client.services,
                    self._protocol_variant,
                    ble_model,
                    observed_device_name,
                )
                corrected_bed_type = refine_dewertokin_star_protocol_from_name(
                    corrected_bed_type,
                    observed_device_name,
                )
                corrected_bed_type = refine_nordic_uart_protocol_from_device_info(
                    corrected_bed_type,
                    observed_device_name,
                    ble_manufacturer,
                    ble_model,
                )
                corrected_bed_type = refine_qrrm_protocol_from_device_info(
                    corrected_bed_type,
                    observed_device_name,
                    ble_model,
                )
                corrected_bed_type = refine_okin_dot_protocol_from_gatt(
                    corrected_bed_type,
                    self._client.services,
                )
                bed_type_corrected = self._apply_runtime_bed_type_correction(corrected_bed_type)
                if (
                    bed_type_corrected
                    and not bed_requires_pairing
                    and requires_pairing(self._bed_type, self._protocol_variant)
                ):
                    _LOGGER.info(
                        "Runtime protocol correction for %s changed %s to pairing-required "
                        "%s; reconnecting so BLE pairing and bond verification run before "
                        "controller startup",
                        self._address,
                        previous_bed_type,
                        self._bed_type,
                    )
                    attempt_details["total_elapsed_seconds"] = round(
                        time.monotonic() - attempt_start, 3
                    )
                    attempt_details["result"] = "retry_with_pairing_after_protocol_correction"
                    self._connection_attempt_details.append(attempt_details)
                    await self._async_disconnect_locked(
                        reason="protocol_correction_requires_pairing"
                    )
                    if not protocol_correction_pairing_retry_reserved:
                        protocol_correction_pairing_retry_reserved = True
                        attempt_limit += 1
                    continue

                manufacturer_data: dict[int, bytes] | None = None
                advertisement = bluetooth.async_last_service_info(
                    self.hass,
                    self._address,
                    connectable=True,
                )
                if advertisement is None or not advertisement.manufacturer_data:
                    # Fall back to the non-connectable advert: this integration
                    # supports misclassified ESPHome/proxy advertisements, and the
                    # manufacturer data (e.g. the Gen2 XP/CP product id) carries
                    # capability info we'd otherwise lose on that path.
                    advertisement = bluetooth.async_last_service_info(
                        self.hass,
                        self._address,
                        connectable=False,
                    )
                if advertisement and advertisement.manufacturer_data:
                    manufacturer_data = dict(advertisement.manufacturer_data)
                    _LOGGER.debug(
                        "Using manufacturer data keys for controller creation: %s",
                        sorted(manufacturer_data),
                    )

                # Create the controller
                _LOGGER.debug("Creating %s controller...", self._bed_type)
                self._controller = await create_controller(
                    coordinator=self,
                    bed_type=self._bed_type,
                    protocol_variant=self._protocol_variant,
                    client=self._client,
                    device_name=device.name,
                    ble_manufacturer=ble_manufacturer,
                    ble_model=ble_model,
                    manufacturer_data=manufacturer_data,
                    advertisement_name=advertisement.name if advertisement is not None else None,
                )
                if self._bed_type == BED_TYPE_SLEEPYS_BOX25:
                    dialect = type(self._controller)
                    if self._box25_dialect not in (None, dialect):
                        self._pending_capability_reload = True
                    self._box25_dialect = dialect
                await self._async_restore_app_state(self._controller)
                await self._controller.async_discover_capabilities()
                self._controller_state_refresh_retry_count = 0
                self._controller_state_refresh_completed = False
                # Position values retained across disconnects are last-known
                # state only. Give this controller session its own generation so
                # reconnect hydration and seeks can distinguish fresh feedback
                # from cached values.
                self._position_connection_generation += 1
                controller_session_generation = self._position_connection_generation
                # Remember the resolved persistence so reconnect/idle decisions are
                # correct even after _on_disconnect clears the controller.
                self._cache_persistent_connection_policy()
                _LOGGER.debug("Controller created successfully")

                controller = self._controller
                session = _ConnectSession(
                    self, self._client, attempt_details, controller_session_generation
                )
                await controller.async_on_connect(session)

                # Startup discovery can change which work is safe to schedule.
                # In particular, an Octo Smart Control session that did not
                # complete must not leave capability-driven polling behind.
                self._refresh_passive_position_reconciliation_schedule()
                self._refresh_diagnostic_polling_schedule()

                # Beds with connect-time feature discovery/state hydration.
                await controller.async_after_connect(session)

                # Read deferred BLE Device Information now that the
                # notification channel and protocol handshake are done.
                if (
                    _defer_device_info
                    and self._client is not None
                    and self._client.is_connected
                    and not await controller.async_read_device_info(session)
                ):
                    if self._device_info_read_done:
                        ble_manufacturer = self._ble_manufacturer
                        ble_model = self._ble_model
                        _LOGGER.debug(
                            "Reusing cached device info for %s (manufacturer=%s, model=%s)",
                            self._address,
                            ble_manufacturer,
                            ble_model,
                        )
                    else:
                        ble_manufacturer, ble_model = await read_ble_device_info(
                            self._client, self._address
                        )
                        self._store_ble_device_info(ble_manufacturer, ble_model)

                if (
                    not controller.reads_light_state_on_connect
                    and self._should_refresh_readable_light_state(force=True)
                ):
                    await self._async_refresh_readable_light_state()

                if self._client is None or not self._client.is_connected:
                    self._record_dropped_connection(
                        "controller startup", attempt_details, attempt_start
                    )
                    continue

                # Startup reads can settle persistence (FurniMove's receiver model).
                self._cache_persistent_connection_policy()

                if reset_timer:
                    self._reset_disconnect_timer()

                # Store connection metadata for binary sensor
                self._connecting = False
                self._last_connected = datetime.now(UTC)
                self._connection_source = actual_adapter
                self._connection_path = async_path_for_source(
                    self.hass, actual_adapter, rssi=adapter_result.rssi
                )
                self._connection_rssi = adapter_result.rssi
                self._notify_connection_state_change(True)
                self._connection_attempt_details.append(attempt_details)

                # Background, and only for axes still unknown: a bed that could
                # not answer at setup gets another chance on every connect
                # instead of staying "unknown" until the user moves it.
                self._schedule_position_hydration()

                if not bed_requires_pairing and self._has_unresolved_auth_failure():
                    # Controller startup ran on this unpaired link, so the GATT
                    # access that failed earlier works and its repair is resolved.
                    self._last_bond_evidence = None
                await self.async_clear_obsolete_pairing_state()

                return True

            except asyncio.CancelledError:
                # The transport releases its own slot wait, but a cancellation
                # after establish_connection returned leaves our client and any
                # startup subscriptions/tasks owned by this coordinator.
                self._connecting = False
                self._last_disconnect_reason = "connect_cancelled"
                try:
                    await self._async_cancel_position_hydration()
                    async with async_get_connect_lock(self.hass, self._address):
                        await self._async_disconnect_locked("connect_cancelled")
                except Exception:
                    _LOGGER.exception(
                        "Cleanup after cancelled connection to %s failed", self._address
                    )
                self._notify_connection_state_change(self.is_connected)
                raise
            except (BleakError, TimeoutError, OSError) as err:
                if isinstance(err, BleakError) and _is_ble_authentication_error(err):
                    # Authentication can first fail during controller startup,
                    # after a slow DIS probe was treated as inconclusive. Clear
                    # the stale marker here so the next retry requests pairing.
                    # Keep this best-effort: the handler usually disconnects the
                    # client, and disconnect cleanup can itself raise. Letting
                    # that escape would replace the original authentication error
                    # and abort the remaining retries. CancelledError is a
                    # BaseException, so cancellation still propagates.
                    try:
                        await self._async_handle_ble_authentication_error(
                            err,
                            holding_lock=True,
                            attempt_details=attempt_details,
                            defer_pairing_issue=True,
                        )
                    except Exception:
                        _LOGGER.debug(
                            "Authentication recovery cleanup failed for %s",
                            self._address,
                            exc_info=True,
                        )
                    if grants_one_connection_per_pairing_window(
                        self._bed_type, self._protocol_variant
                    ):
                        # Startup already failed, so the handler released the
                        # link (retain_link is False here): a link with no
                        # controller cannot drive the bed and would only block
                        # the physical remote. Retrying cannot recover either,
                        # because the box will not grant a second connection
                        # until it is power-cycled. Stop instead of burning the
                        # remaining attempts; the connect wrapper then raises
                        # the repair telling the user to re-pair.
                        _LOGGER.warning(
                            "Authentication failed for %s during startup. This "
                            "bed grants one connection per pairing window, so "
                            "further retries cannot succeed until it is "
                            "power-cycled; stopping reconnect attempts.",
                            self._address,
                        )
                        await self._async_cleanup_failed_connection()
                        self._connecting = False
                        attempt_details["total_elapsed_seconds"] = round(
                            time.monotonic() - attempt_start, 3
                        )
                        attempt_details["result"] = "failed"
                        attempt_details["error"] = str(err)
                        attempt_details["error_type"] = type(err).__name__
                        attempt_details["error_category"] = "AUTHENTICATION"
                        self._last_connection_error = str(err)
                        self._last_connection_error_type = type(err).__name__
                        self._connection_attempt_details.append(attempt_details)
                        break
                attempt_elapsed = time.monotonic() - attempt_start
                attempt_details["total_elapsed_seconds"] = round(attempt_elapsed, 3)
                attempt_details["result"] = "failed"
                attempt_details["error"] = str(err)
                attempt_details["error_type"] = type(err).__name__
                err_str = str(err).lower()
                # Categorize the error for clearer diagnostics
                if _is_ble_authentication_error(err):
                    error_category = "AUTHENTICATION"
                elif isinstance(err, TimeoutError) or "timeout" in err_str:
                    error_category = "CONNECTION TIMEOUT"
                elif "refused" in err_str or "rejected" in err_str:
                    error_category = "CONNECTION REFUSED (another device may be connected)"
                else:
                    error_category = "BLE ERROR"
                attempt_details["error_category"] = error_category
                # A receiver that is visible but times out or aborts the connect
                # is stalling. "Not found" and refusals (another device holds the
                # link) are not stalls.
                if error_category == "CONNECTION TIMEOUT" or "abort" in err_str:
                    self._reconnect_stalled = True

                # Detect connection slot exhaustion and exclude the adapter
                # on subsequent retries so we try an alternative (issue #152).
                if "connection slot" in err_str and adapter_result is not None:
                    failed_source = attempt_details.get("actual_source") or adapter_result.source
                    if isinstance(failed_source, str) and failed_source:
                        exhausted_adapters.add(failed_source)
                        _LOGGER.info(
                            "Adapter %s out of connection slots for %s, "
                            "will try alternative adapter on next retry",
                            failed_source,
                            self._address,
                        )

                # Track connection error for diagnostics (issue #168)
                self._connecting = False
                self._last_connection_error = str(err)
                self._last_connection_error_type = type(err).__name__

                _LOGGER.warning(
                    "✗ %s to %s after %.1fs (attempt %d/%d): %s",
                    error_category,
                    self._address,
                    attempt_elapsed,
                    attempt_number,
                    attempt_limit,
                    err,
                )
                _LOGGER.debug(
                    "Connection error details - type: %s, args: %s",
                    type(err).__name__,
                    err.args,
                )
                await self._async_cleanup_failed_connection()
                self._connection_attempt_details.append(attempt_details)
                # Delay is handled at the start of the next iteration with progressive backoff
            except Exception as err:  # noqa: BLE001 - preserve retry diagnostics for unexpected connect failures
                # Track connection error for diagnostics (issue #168)
                self._connecting = False
                self._last_connection_error = str(err)
                self._last_connection_error_type = type(err).__name__
                attempt_details["total_elapsed_seconds"] = round(
                    time.monotonic() - attempt_start, 3
                )
                attempt_details["result"] = "failed"
                attempt_details["error"] = str(err)
                attempt_details["error_type"] = type(err).__name__
                attempt_details["error_category"] = "UNEXPECTED ERROR"

                _LOGGER.warning(
                    "Unexpected error connecting to %s (attempt %d/%d): %s",
                    self._address,
                    attempt_number,
                    attempt_limit,
                    err,
                )
                _LOGGER.debug(
                    "Exception details - type: %s, args: %s",
                    type(err).__name__,
                    err.args,
                )
                # Log full traceback at debug level
                _LOGGER.debug("Full traceback:\n%s", traceback.format_exc())
                await self._async_cleanup_failed_connection()
                self._connection_attempt_details.append(attempt_details)
                # Delay is handled at the start of the next iteration with progressive backoff

        if (
            pairlink_transport_failed
            and self._bed_type == BED_TYPE_REVERIE_PAIRLINK
            and self._pairlink_runtime is not None
        ):
            # HA owns retries. Only an exhausted actual central connect failure
            # projects the source library's status6, never discovery absence.
            self._pairlink_runtime._on_central_library_status(
                6, source_mac=self._address
            )
        reason = connection_reachability(self.hass, self._address)
        if reason:
            _LOGGER.warning("Bluetooth reachability for %s: %s", self._address, reason)
            if self._connection_attempt_details:
                self._connection_attempt_details[-1]["reachability"] = reason
        total_elapsed = time.monotonic() - overall_start
        # All attempts failed: the bed is unreachable, not idle-disconnected, so
        # ensure the connectivity sensor reports "disconnected" rather than "idle"
        # (issue #385 review). Notify listeners so the sensor/card re-render now —
        # the device-not-found retries don't otherwise emit a state change, so a
        # previously published "idle" would linger until some later event.
        self._last_disconnect_reason = "connect_failed"
        self._notify_connection_state_change(False)
        _LOGGER.error(
            "✗ FAILED to connect to %s after %d attempts (%.1fs total). "
            "Troubleshooting:\n"
            "  1. Power cycle bed (unplug 30 seconds)\n"
            "  2. Close any phone apps connected to bed\n"
            "  3. Check Bluetooth adapter is working\n"
            "  4. Move adapter closer to bed\n"
            "  5. If using ESPHome proxy, verify it's online",
            self._address,
            attempt,
            total_elapsed,
        )
        self._schedule_pending_capability_reload()
        return False

    def _on_disconnect(self: AdjustableBedCoordinator, client: BleakClient) -> None:
        """Handle disconnection callback."""
        if client is self._vmat_unready_client:
            if client.is_connected:
                return
            self._vmat_unready_client = None
        # Ignore stale disconnect callbacks from old clients
        if client is not self._client:
            _LOGGER.debug(
                "Ignoring stale disconnect callback from old client for %s",
                self._address,
            )
            return

        if self._furnimove_bond_task is not None:
            self._furnimove_bond_task.cancel()

        # Invalidate connection-owned work even during Bleak initialization retries.
        controller = self._controller
        if controller is not None:
            controller.on_disconnect()
        # A tracked movement cut off by the link loss has no known stop time.
        notify_position_estimate_connection_lost(self)

        # If we're in the middle of connecting, this is likely bleak's internal retry
        # for le-connection-abort-by-local - don't log warnings or clear references
        if self._connecting:
            _LOGGER.debug(
                "Disconnect callback during connection establishment for %s (bleak internal retry)",
                self._address,
            )
            return

        # A held motion never resumes on a later link: end it and its
        # reservations now. Renewals for the ended generation are refused.
        self._command_scheduler.end_holds(CommandOutcome.DISCONNECTED)

        # Store disconnect timestamp for binary sensor
        self._cancel_diagnostic_polling()
        self._last_disconnected = datetime.now(UTC)

        # Track disconnect reason for diagnostics (issue #168)
        # If intentional, reason is set by async_disconnect() or _async_idle_disconnect()
        if not self._intentional_disconnect:
            self._last_disconnect_reason = "unexpected"

        # Stop keepalive task before clearing controller to prevent task leak
        if controller is not None:
            self._stop_keepalive_task = self.entry.async_create_background_task(
                self.hass,
                controller.stop_keepalive(),
                name=f"adjustable_bed_stop_keepalive_{self._address}",
            )

        # If this was an intentional disconnect (manual or idle timeout), don't auto-reconnect
        if self._intentional_disconnect:
            _LOGGER.debug(
                "Intentional disconnect from %s - skipping auto-reconnect",
                self._address,
            )
            self._client = None
            self._controller = None
            if self._vmat_unready_client is client:
                self._vmat_unready_client = None
            # Keep _position_data for last known state; entity availability handles offline
            # Flag is reset in _async_connect_locked when reconnecting
            self._notify_connection_state_change(False)
            self._schedule_pending_capability_reload()
            return

        _LOGGER.warning(
            "Unexpectedly disconnected from %s. Client details: is_connected=%s, address=%s",
            self._address,
            getattr(client, "is_connected", "N/A"),
            getattr(client, "address", "N/A"),
        )
        _LOGGER.debug(
            "Disconnect callback triggered - clearing client and controller references for %s",
            self._address,
        )
        self._client = None
        self._controller = None
        # Keep _position_data for last known state; entity availability handles offline
        self._cancel_disconnect_timer()
        self._notify_connection_state_change(False)
        _LOGGER.debug("Disconnect cleanup complete for %s", self._address)
        self._schedule_pending_capability_reload()

        if not self._auto_reconnect_enabled():
            _LOGGER.debug(
                "Skipping auto-reconnect timer for %s (persistent connection or "
                "disconnect_after_command); "
                "next command reconnects on demand",
                self._bed_type,
            )
            if self._reconnect_timer is not None:
                self._reconnect_timer.cancel()
                self._reconnect_timer = None
            return

        # Schedule automatic reconnection attempt
        # Cancel any existing reconnect timer first to prevent multiple concurrent reconnects
        if self._reconnect_timer is not None:
            self._reconnect_timer.cancel()
        self._reconnect_timer = self.hass.loop.call_later(
            5.0,  # Wait 5 seconds before attempting reconnect
            self._schedule_auto_reconnect,
        )

    def _schedule_auto_reconnect(self: AdjustableBedCoordinator) -> None:
        """Launch the auto-reconnect task once the reconnect timer fires.

        The task is tied to the config entry so it is tracked by HA and
        cancelled automatically if the entry unloads before it finishes.
        """
        self._reconnect_timer = None
        if self._reconnect_task is not None and not self._reconnect_task.done():
            return
        task = self.entry.async_create_background_task(
            self.hass,
            self._async_auto_reconnect(),
            name=f"adjustable_bed_auto_reconnect_{self._address}",
        )
        self._reconnect_task = task
        task.add_done_callback(self._auto_reconnect_done)

    def _auto_reconnect_done(self: AdjustableBedCoordinator, task: asyncio.Task[None]) -> None:
        if self._reconnect_task is task:
            self._reconnect_task = None

    def _cancel_auto_reconnect(self: AdjustableBedCoordinator) -> None:
        """Cancel delayed and launched recovery without interrupting its own cleanup."""
        if self._reconnect_timer is not None:
            self._reconnect_timer.cancel()
            self._reconnect_timer = None
        task = self._reconnect_task
        if (
            task is not None
            and task is not asyncio.current_task()
            and not task.done()
            and not task.cancelling()
        ):
            task.cancel()

    async def _async_auto_reconnect(self: AdjustableBedCoordinator) -> None:
        """Attempt automatic reconnection after unexpected disconnect."""
        # Don't reconnect if we're already connected or connecting
        if self._connecting or (self._client is not None and self._client.is_connected):
            _LOGGER.debug("Skipping auto-reconnect: already connected or connecting")
            return

        # A STOP sent while no command ran leaves the shared cancel event set.
        # With no command holding the lock there is nothing left to cancel, so it
        # must not abort this reconnect's connect-time initialization.
        if not self._command_lock.locked():
            self._cancel_command.clear()

        _LOGGER.info("Attempting automatic reconnection to %s", self._address)
        try:
            connected = await self.async_connect()
            if connected:
                _LOGGER.info("Auto-reconnection successful for %s", self._address)
                # Note: async_start_notify is called automatically in _async_connect_locked
            else:
                _LOGGER.warning(
                    "Auto-reconnection failed for %s. Will retry on next command.",
                    self._address,
                )
        except Exception as err:
            _LOGGER.warning(
                "Auto-reconnection error for %s: %s",
                self._address,
                err,
            )
        finally:
            controller = self.capability_controller
            if (
                not self._shutting_down
                and not self._intentional_disconnect
                and not self.is_connected
                and controller is not None
                and controller.requests_connection_recovery is True
                and self._reconnect_timer is None
            ):
                self._reconnect_timer = self.hass.loop.call_later(5.0, self._schedule_auto_reconnect)

    async def async_disconnect(
        self: AdjustableBedCoordinator,
        reason: str = "intentional",
        *,
        serialize_with_commands: bool = False,
    ) -> bool:
        """Disconnect from the bed.

        Args:
            reason: The reason for disconnecting (for diagnostics).
                    Common values: "intentional", "idle_timeout"
            serialize_with_commands: Take the command lock first so the teardown
                    cannot land in the middle of a command. Required for
                    externally triggered disconnects (the Disconnect button, the
                    idle timer); must stay False for callers that already hold
                    the command lock, such as disconnect-after-command.
        """
        _LOGGER.debug("async_disconnect called for %s", self._address)
        if reason == "intentional":
            # A user releasing the link (e.g. for the bed's phone app) wants the
            # configured handoff again until another connect stalls.
            self._reconnect_stalled = False
        # Stop recovery before waiting for the connection lane it may already own.
        self._cancel_auto_reconnect()
        if serialize_with_commands:
            # Without this, a disconnect requested while a connect is in flight
            # queues on self._lock and then tears the link down in the same tick
            # that the command which triggered the reconnect issues its first
            # GATT write, so the command fails (issue #368).
            disconnect_epoch = self._command_scheduler.request_stop(ALL_COMMAND_RESOURCES)
            try:
                async with self._command_lock, self._lock:
                    return await self._async_disconnect_locked(reason)
            finally:
                # Drop commands admitted while teardown held the wire lock too.
                # These two synchronous calls form one event-loop transition, so
                # a post-disconnect command cannot slip between invalidation and
                # release of the scheduler safety lane.
                self._command_scheduler.request_cancel(
                    ALL_COMMAND_RESOURCES, outcome=CommandOutcome.STOPPED
                )
                self._command_scheduler.finish_stop(disconnect_epoch)

        async with self._lock:
            return await self._async_disconnect_locked(reason)

    async def async_release_for_pairing_transfer(
        self: AdjustableBedCoordinator, *, expected_pairlink_runtime: PairlinkRuntime | None = None,
    ) -> bool:
        """Release this standalone link for takeover by a paired entry.

        Pairing-window-only receivers must be checked after any command or
        automatic reconnect already using the connection lane has completed.
        Holding both lanes through teardown keeps that check atomic.
        """
        async with self._command_lock, self._lock:
            if (
                expected_pairlink_runtime is not None
                and self._pairlink_runtime is not expected_pairlink_runtime
            ):
                raise ConnectionError("Pairlink source runtime changed before transfer")
            controller = self._controller
            if (
                self.is_connected
                and controller is not None
                and controller.manual_disconnect_strands_connection
            ):
                raise PairingOnlyConnectionActiveError
            self._pairing_transfer_active = True
            try:
                runtime = self._pairlink_runtime
                if (
                    self._bed_type == BED_TYPE_REVERIE_PAIRLINK
                    and controller is not None
                    and controller.requires_disconnected_transport is True
                ):
                    if runtime is None or not runtime.is_peripheral_role_active:
                        raise ConnectionError("Local source runtime is unavailable for transfer")
                    controller.on_disconnect()
                    try:
                        await runtime.async_shutdown()
                    finally:
                        self._pairlink_runtime = None
                        self._controller = None
                        self._offline_controller = None
                        self._last_disconnected = datetime.now(UTC)
                        self._notify_connection_state_change(False)
                    released = True
                else:
                    released = await self._async_disconnect_locked("absorbed_by_pair")
            except asyncio.CancelledError:
                try:
                    await self._async_restore_cancelled_pairing_release()
                finally:
                    self._pairing_transfer_active = False
                raise
            except Exception:
                self._pairing_transfer_active = False
                raise
            if not released:
                self._pairing_transfer_active = False
            return released

    async def _async_restore_cancelled_pairing_release(self: AdjustableBedCoordinator) -> None:
        """Restore controller tasks when a bounded pairing release is cancelled."""
        controller = self._controller
        if not self.is_connected or controller is None:
            return
        try:
            async with asyncio.timeout(_PAIRING_RELEASE_RESTORE_TIMEOUT):
                await self.async_start_notify()
                await controller.async_resume_session()
                self._reset_disconnect_timer()
        except TimeoutError:
            _LOGGER.warning(
                "Timed out restoring controller tasks for %s after pairing transfer cancellation",
                self._address,
            )
        except Exception:
            _LOGGER.exception(
                "Could not restore controller tasks for %s after pairing transfer cancellation",
                self._address,
            )

    def finish_pairing_transfer(self: AdjustableBedCoordinator) -> None:
        """Allow standalone reconnects after pair setup absorbs or releases us."""
        self._pairing_transfer_active = False
        self._schedule_pending_capability_reload()

    @contextlib.asynccontextmanager
    async def async_transport_operation(self: AdjustableBedCoordinator, operation: str) -> AsyncIterator[None]:
        """Hold the bed out of use for the whole of a transport operation.

        Removing or recreating a Bluetooth bond must not race a command or a
        reconnect, and it is not enough to disconnect and then let go: the
        removal itself has to happen while everything else is still excluded.
        So this is a context manager rather than a "prepare" call, and the locks
        stay held until the caller's transaction finishes.

        The locks are taken in the coordinator's established order - command
        lock, then connection lock - because an unpair that grabbed the address
        lock first could deadlock against a command that already holds the
        command lock and is waiting for the address.

        Inside the block the bed is disconnected with its idle and reconnect
        timers cancelled. Failing to reach that state raises, so a caller can
        refuse to touch the bond rather than remove it blindly.
        """
        _LOGGER.info("Releasing %s for a %s operation", self._address, operation)
        # Command lock, then connection lock, then the per-address connect lock:
        # the coordinator's established order. Excluding our own commands is not
        # enough - a config or repair flow connecting to the same address during
        # a bond removal is exactly what the address lock exists to prevent, and
        # taking it last is what keeps this from deadlocking against a command
        # that already holds the command lock and is waiting for the address.
        async with (
            self._command_lock,
            self._lock,
            async_get_connect_lock(self.hass, self._address),
        ):
            client = self._client
            try:
                released = await self._async_disconnect_locked(f"transport_operation_{operation}")
            except Exception:
                # Only BleakError is handled as a failed teardown; anything else
                # unwinds before the fallback below can run, and the caller is
                # about to abort. Try the same fallback close first: an occupied
                # link is the one thing this gate exists to prevent.
                await self._async_force_close(client)
                raise
            if client is not None and client.is_connected:
                # The link outlived the disconnect, either because bleak raised
                # or because it returned without actually closing the link.
                # Force it closed before raising, or nothing ever will:
                # stale-connection cleanup only operates on BlueZ backends.
                await self._async_force_close(client)
                if client.is_connected:
                    raise RuntimeError(
                        f"Could not release the Bluetooth connection to {self._address}"
                    )
                if not released:
                    # A failed disconnect keeps the live client so callers can
                    # see the link is still up. The fallback closed it, so
                    # finish the teardown that was left half-done.
                    self._client = None
                    self._controller = None
                    self._last_disconnected = datetime.now(UTC)
                    self._notify_connection_state_change(False)
            yield

    async def _async_force_close(self: AdjustableBedCoordinator, client: BleakClient | None) -> None:
        """Close a link the ordinary teardown left connected, and keep it closed.

        The teardown clears ``_intentional_disconnect`` on its way out, so a
        disconnect callback from this close would be read as an unexpected drop
        and schedule the auto-reconnect. That timer fires after the gate has
        released its locks, which for an unpair means reconnecting and creating
        the very bond the user just asked to remove.
        """
        if client is not None and client.is_connected:
            self._intentional_disconnect = True
            try:
                with contextlib.suppress(Exception):
                    await client.disconnect()
            finally:
                self._intentional_disconnect = False
        # A callback that landed before the flag was set may have queued a
        # reconnect already. This gate promises the bed stays released for the
        # whole operation, so nothing may be waiting to undo that.
        self._cancel_auto_reconnect()

    async def _async_disconnect_locked(self: AdjustableBedCoordinator, reason: str = "intentional") -> bool:
        """Disconnect from the bed. The caller MUST already hold ``self._lock``.

        Used by the bond-verification path, which runs inside
        ``_async_connect_locked`` (lock already held) and would otherwise
        deadlock on the public ``async_disconnect`` re-acquiring the lock.
        """
        if self._bed_type in (BED_TYPE_GMMOTOR_SLEEP_MM, BED_TYPE_GMMOTOR_SLEEP_SXB):
            # An explicit release also stops monitoring when a prior BLE drop
            # already discarded the live controller and client.
            sleep_intent(
                self.hass, self._address, sxb=self._bed_type == BED_TYPE_GMMOTOR_SLEEP_SXB
            ).live_enabled = False

        # An explicit release ends app intent even if the physical link already dropped.
        for controller in (self._controller, self._offline_controller):
            if controller is not None:
                controller.on_connection_release(reason)
        # Recovery may have launched while this caller waited for the lock.
        self._cancel_auto_reconnect()
        await self._async_cancel_furnimove_bond_request()
        self._cancel_diagnostic_polling()
        self._cancel_disconnect_timer()
        self._cancel_controller_state_refresh_retry()
        if self._controller_state_refresh_task is not None:
            self._controller_state_refresh_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._controller_state_refresh_task
            self._controller_state_refresh_task = None
        controller = self._controller
        if self._client is not None:
            # Intentional disconnects (manual, idle timeout, disconnect-after-command)
            # are routine for non-persistent beds; keep them at DEBUG so normal use
            # doesn't spam the log. The reason is preserved in _last_disconnect_reason.
            _LOGGER.debug("Disconnecting from bed at %s (reason: %s)", self._address, reason)
            # Mark as intentional so _on_disconnect doesn't trigger auto-reconnect
            self._intentional_disconnect = True
            # Track disconnect reason for diagnostics (issue #168)
            self._last_disconnect_reason = reason
            client = self._client
            try:
                # Stop keep-alive and notifications before disconnecting
                if controller is not None:
                    try:
                        await controller.stop_keepalive()
                    except Exception as err:
                        _LOGGER.debug("Error stopping keep-alive: %s", err)
                    try:
                        await controller.stop_notify()
                    except Exception as err:
                        _LOGGER.debug("Error stopping notifications: %s", err)
                connect_lock = async_get_connect_lock(self.hass, self._address)
                if connect_lock.retained_setup_client is client:
                    await connect_lock.async_release_setup_client()
                else:
                    await client.disconnect()
                _LOGGER.debug("Successfully disconnected from %s", self._address)
            except BleakError as err:
                _LOGGER.debug("Error during disconnect from %s: %s", self._address, err)
            finally:
                self._intentional_disconnect = False
            # Bleak can raise or return while the OS link remains active. Keep
            # the live client/controller instead of reporting a logical
            # disconnect: the paired sequential guard must know that opening
            # the other side could create two physical links.
            if client.is_connected:
                self._client = client
                _LOGGER.warning("Disconnect from %s did not release the BLE link", self._address)
                return False
            # Some Bleak backends do not emit the disconnect callback for an
            # intentional close. Preserve the same physical-session invalidation
            # by notifying the controller when the callback did not already own it.
            if controller is not None and self._controller is controller:
                controller.on_disconnect()
            self._client = None
            self._controller = None
            if self._vmat_unready_client is client:
                self._vmat_unready_client = None
            # Update disconnect timestamp and notify state change (don't rely on
            # _on_disconnect, which may not fire after a clean disconnect).
            self._last_disconnected = datetime.now(UTC)
            self._notify_connection_state_change(False)
        self._schedule_pending_capability_reload()
        return True

    def _reset_disconnect_timer(self: AdjustableBedCoordinator) -> None:
        """Reset the disconnect timer."""
        if self._command_connection_holds:
            self._cancel_disconnect_timer()
            return
        if self._uses_persistent_connection():
            self._cancel_disconnect_timer()
            _LOGGER.debug(
                "Skipping idle disconnect timer for persistent connection on %s",
                self._address,
            )
            return

        self._cancel_disconnect_timer()
        delay = self._idle_disconnect_delay()
        _LOGGER.debug(
            "Setting idle disconnect timer for %s (%.1f seconds)",
            self._address,
            delay,
        )
        self._disconnect_timer = self.hass.loop.call_later(
            delay,
            self._schedule_idle_disconnect,
        )

    def _schedule_idle_disconnect(self: AdjustableBedCoordinator) -> None:
        """Launch the idle-disconnect task once the idle timer fires.

        The task is tied to the config entry so it is tracked by HA and
        cancelled automatically if the entry unloads before it finishes.
        """
        # The handle has run, so drop it: _async_idle_disconnect uses a non-None
        # _disconnect_timer to mean "a command re-armed the timer while I waited
        # for the command lock", which only works if a fired handle is cleared.
        self._disconnect_timer = None
        self.entry.async_create_background_task(
            self.hass,
            self._async_idle_disconnect(),
            name=f"adjustable_bed_idle_disconnect_{self._address}",
        )

    def _cancel_disconnect_timer(self: AdjustableBedCoordinator) -> None:
        """Cancel the disconnect timer."""
        if self._disconnect_timer is not None:
            _LOGGER.debug("Cancelling idle disconnect timer for %s", self._address)
            self._disconnect_timer.cancel()
            self._disconnect_timer = None

    def pause_disconnect_timer(self: AdjustableBedCoordinator) -> None:
        """Pause the disconnect timer (for external use like diagnostics).

        Call resume_disconnect_timer() when done to restart the timer.
        """
        self._cancel_disconnect_timer()
        _LOGGER.debug("Disconnect timer paused for %s", self._address)

    def resume_disconnect_timer(self: AdjustableBedCoordinator) -> None:
        """Resume the disconnect timer after pausing.

        This resets the timer, giving a full idle timeout from now.
        """
        if self._client is not None and self._client.is_connected:
            self._reset_disconnect_timer()
            _LOGGER.debug("Disconnect timer resumed for %s", self._address)

    async def _async_idle_disconnect(self: AdjustableBedCoordinator) -> None:
        """Disconnect after idle timeout."""
        # Expected for non-persistent beds: we drop the link so the physical remote
        # can take over, and reconnect on demand on the next command. Logged at DEBUG
        # to avoid spamming the log during normal use.
        _LOGGER.debug(
            "Idle timeout reached (%.1f seconds), disconnecting from %s",
            self._idle_disconnect_delay(),
            self._address,
        )
        async with self._command_lock:
            if self._command_connection_holds:
                return
            if self._position_hydration_running:
                # Commands may re-arm the timer between hydration attempts.
                # The final hydration cleanup starts a fresh timer.
                _LOGGER.debug(
                    "Skipping idle disconnect during position hydration for %s",
                    self._address,
                )
                return
            if self._disconnect_timer is not None:
                # A command ran while this firing waited for the command lock and
                # re-armed the timer, so the bed is no longer idle.
                _LOGGER.debug(
                    "Skipping stale idle disconnect for %s: the timer was re-armed",
                    self._address,
                )
                return
            async with self._lock:
                await self._async_disconnect_locked("idle_timeout")

    async def async_ensure_connected(self: AdjustableBedCoordinator, reset_timer: bool = True) -> bool:
        """Ensure we are connected to the bed."""
        async with self._lock:
            if self.entry.data.get(CONF_VIBRADORM_APP_PROFILE) == "vmat" and (
                self._shutting_down or self._vmat_unready_link_pending() or self._controller is None
            ):
                return await self._async_connect_locked(reset_timer=reset_timer)
            if self._client is not None and self._client.is_connected:
                _LOGGER.debug("Connection check: already connected to %s", self._address)
                if reset_timer:
                    self._reset_disconnect_timer()
                return True
            _LOGGER.debug("Connection check: reconnecting to %s", self._address)
            return await self._async_connect_locked(reset_timer=reset_timer)

    def register_connection_state_callback(
        self: AdjustableBedCoordinator, callback_fn: Callable[[bool], None]
    ) -> Callable[[], None]:
        """Register a callback for connection state changes."""
        self._connection_state_callbacks.add(callback_fn)

        def unregister() -> None:
            self._connection_state_callbacks.discard(callback_fn)

        return unregister

    def _notify_connection_state_change(self: AdjustableBedCoordinator, connected: bool) -> None:
        """Notify all registered callbacks of a connection state change."""
        for callback_fn in list(self._connection_state_callbacks):
            try:
                callback_fn(connected)
            except Exception as err:
                _LOGGER.warning("Connection state callback error: %s", err)
