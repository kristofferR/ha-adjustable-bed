"""Coordinator for Adjustable Bed integration."""

from __future__ import annotations

import asyncio
import contextlib
import inspect
import logging
import random
import time
import traceback
from collections import deque
from collections.abc import AsyncIterator, Awaitable, Callable, Collection, Coroutine, Mapping
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, TypeVar, cast
from uuid import uuid4

from bleak import BleakClient
from bleak.backends.device import BLEDevice
from bleak.exc import BleakError
from bleak_retry_connector import establish_connection

try:
    from bleak_retry_connector import close_stale_connections_by_address
except ImportError:
    # Older bleak-retry-connector versions may not expose this helper.
    close_stale_connections_by_address = None

from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo

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
from .ble_auth import is_ble_authentication_error, is_ble_pairing_auth_failure
from .bluetooth_transport import (
    ConnectionPath,
    TransportClass,
    async_path_for_source,
    client_source,
)
from .bond_verification import (
    CONF_BLE_BOND_CONTEXT,
    BondEvidence,
    BondOwner,
    BondVerificationStatus,
    bond_context_matches,
    bond_owner_from_entry,
    build_bond_context,
)
from .command_scheduler import (
    ALL_COMMAND_RESOURCES,
    CommandContext,
    CommandHandle,
    CommandIntent,
    CommandKind,
    CommandOutcome,
    DeviceCommandScheduler,
    command_resources,
    current_command_context,
)
from .const import (
    ADAPTER_AUTO,
    BED_MOTOR_PULSE_DEFAULTS,
    BED_TYPE_BEDTECH,
    BED_TYPE_COMFORT_MOTION,
    BED_TYPE_DEWERTOKIN,
    BED_TYPE_DIAGNOSTIC,
    BED_TYPE_ERGOMOTION,
    BED_TYPE_JENSEN,
    BED_TYPE_JIECANG,
    BED_TYPE_KEESON,
    BED_TYPE_LEGGETT_GEN2,
    BED_TYPE_LEGGETT_OKIN,
    BED_TYPE_LEGGETT_PLATT,
    BED_TYPE_LEGGETT_WILINKE,
    BED_TYPE_LIMOSS,
    BED_TYPE_LINAK,
    BED_TYPE_MALOUF_LEGACY_OKIN,
    BED_TYPE_MALOUF_NEW_OKIN,
    BED_TYPE_MATTRESSFIRM,
    BED_TYPE_MOTOSLEEP,
    BED_TYPE_NECTAR,
    BED_TYPE_OCTO,
    BED_TYPE_OKIMAT,
    BED_TYPE_OKIN_7BYTE,
    BED_TYPE_OKIN_CST,
    BED_TYPE_OKIN_FFE,
    BED_TYPE_OKIN_HANDLE,
    BED_TYPE_OKIN_NORDIC,
    BED_TYPE_OKIN_RF_ECO_BT,
    BED_TYPE_OKIN_UUID,
    BED_TYPE_REVERIE,
    BED_TYPE_REVERIE_NIGHTSTAND,
    BED_TYPE_RICHMAT,
    BED_TYPE_SERTA,
    BED_TYPE_SLEEP_NUMBER,
    BED_TYPE_SLEEP_NUMBER_MCR,
    BED_TYPE_SOLACE,
    BED_TYPE_VIBRADORM,
    BEDS_WITH_POSITION_FEEDBACK,
    CONF_BACK_MAX_ANGLE,
    CONF_BED_TYPE,
    CONF_BLE_BOND_ATTEMPTED_SOURCE,
    CONF_BLE_BOND_ESTABLISHED,
    CONF_BLE_BOND_MARKER_UNRELIABLE,
    CONF_BLE_DEVICE_NAME,
    CONF_CB24_BED_SELECTION,
    CONF_CONNECTION_PROFILE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_DISCONNECT_AFTER_COMMAND,
    CONF_HAS_MASSAGE,
    CONF_IDLE_DISCONNECT_SECONDS,
    CONF_JENSEN_PIN,
    CONF_LEGS_MAX_ANGLE,
    CONF_MALOUF_LAYOUT,
    CONF_MALOUF_MEMORY_SLOTS,
    CONF_MOTOR_COUNT,
    CONF_MOTOR_PULSE_COUNT,
    CONF_MOTOR_PULSE_DELAY_MS,
    CONF_MOTOR_PULSE_USER_SET,
    CONF_OCTO_PIN,
    CONF_PASSIVE_POSITION_RECONCILIATION,
    CONF_POSITION_MODE,
    CONF_PREFERRED_ADAPTER,
    CONF_PROTOCOL_VARIANT,
    CONF_RICHMAT_REMOTE,
    CONF_SIDE,
    CONNECTION_PROFILES,
    DEFAULT_BACK_MAX_ANGLE,
    DEFAULT_CONNECTION_PROFILE,
    DEFAULT_DISABLE_ANGLE_SENSING,
    DEFAULT_DISCONNECT_AFTER_COMMAND,
    DEFAULT_HAS_MASSAGE,
    DEFAULT_IDLE_DISCONNECT_SECONDS,
    DEFAULT_LEGS_MAX_ANGLE,
    DEFAULT_MOTOR_COUNT,
    DEFAULT_OCTO_PIN,
    DEFAULT_POSITION_MODE,
    DEFAULT_PROTOCOL_VARIANT,
    DEVICE_INFO_CHARS,
    DEVICE_INFO_READ_TIMEOUT,
    DOMAIN,
    LEGGETT_OKIN_SUPERSEDED_PULSE_DEFAULTS,
    LEGGETT_VARIANT_GEN2,
    LEGGETT_VARIANT_OKIN,
    LINAK_VARIANT_PERFORMANCE,
    MALOUF_LAYOUT_AUTO,
    MALOUF_MEMORY_SLOTS_AUTO,
    OCTO_VARIANT_STAR2,
    OFFLINE_CAPABILITY_SAFE_BED_TYPES,
    OKIMAT_SERVICE_UUID,
    POSITION_MODE_ACCURACY,
    REVERIE_BACK_MAX_ANGLE,
    RICHMAT_REMOTE_AUTO,
    RUNTIME_BOND_KEYS,
    VARIANT_AUTO,
    bed_type_has_position_feedback,
    connection_gated_by_bond,
    get_motor_pulse_defaults,
    get_richmat_features,
    get_richmat_motor_count,
    grants_one_connection_per_pairing_window,
    passive_position_reconciliation_default_enabled,
    requires_pairing,
    requires_pairing_after_service_discovery,
    resolve_explicit_bed_type,
    resolve_richmat_remote_code,
)
from .controller_factory import create_controller
from .detection import (
    OKIN_SHARED_UUID_GATT_REFINABLE_TYPES,
    detect_richmat_remote_from_name,
    refine_dewertokin_star_protocol_from_name,
    refine_malouf_protocol_from_gatt,
    refine_nordic_uart_protocol_from_device_info,
    refine_okin_dot_protocol_from_gatt,
    refine_okin_shared_uuid_protocol_from_gatt,
    refine_qrrm_protocol_from_device_info,
)
from .diagnostic_payloads import new_connection_attempt_details
from .pairing import inheritable_child_fields, octo_snapshot_from_descriptor
from .position_seek import (
    PositionSeekRunner,
    SeekMotion,
    SeekOutcome,
    SeekResult,
    SeekSample,
    SeekTimeoutError,
)
from .unsupported import (
    create_pairing_required_issue,
    delete_pairing_required_issue,
    update_octo_pin_required_issue,
)

if TYPE_CHECKING:
    from .beds.base import BedController

T = TypeVar("T")
_LOGGER = logging.getLogger(__name__)
_CONTROLLER_OPERATION_RECOVERY_EXCEPTIONS = (ConnectionError, RuntimeError)
_READABLE_LIGHT_STATE_TIMEOUT = 2.0
_READABLE_LIGHT_STATE_RETRY_DELAY = 1.0
_READABLE_LIGHT_STATE_MAX_RETRIES = 3
_INITIAL_POSITION_READ_TIMEOUT = 10.0
_INITIAL_POSITION_READ_TOTAL_TIMEOUT = 40.0
_INITIAL_POSITION_READ_RETRY_DELAY = 3.0
_INITIAL_POSITION_READ_MAX_ATTEMPTS = 6
_PASSIVE_POSITION_RECONCILIATION_IDLE_MARGIN = 15.0
# One reconnect gives a stale preserved OKIN profile another chance to reveal
# the CST/RF ECO BT discriminator without making known receivers pay DIS
# timeouts forever.
_OKIN_PRESERVED_PROFILE_DEVICE_INFO_MAX_READ_ATTEMPTS = 2

MAX_COMMAND_TRACE_ENTRIES = 100

# How many successful paired connections to make while the always-pair latch is
# set before dropping it to re-test whether the bond persists again. Small
# enough that a bed moved to a bond-keeping adapter recovers quickly, large
# enough that a bed which genuinely loses bonds wastes an attempt only rarely.
BOND_LATCH_RETEST_AFTER = 10
MAX_CONNECTION_ATTEMPT_DETAILS = 25

# Backwards-compatible private alias; the implementation now lives in ble_auth
# so the repairs flow can share it without importing the coordinator.
_is_ble_authentication_error = is_ble_authentication_error


class NotConnectedError(Exception):
    """Raised when bed is not connected."""


class NoControllerError(Exception):
    """Raised when no controller is available."""


class ChildEntryView:
    """A per-side config view of a parent ConfigEntry (Dual Bed 4.0).

    A paired bed is one config entry but two child coordinators. Each child reads
    its per-side config from ``.data`` (this view) and persists runtime changes
    through ``persist_data`` — which updates this view in place and routes to the
    parent's child descriptor. Everything else proxies to the real parent entry,
    so background tasks, ``entry_id`` and the entry lifecycle stay attached to the
    single real entry. Single beds never use this — they get the real entry.
    """

    def __init__(
        self,
        parent: ConfigEntry,
        child_data: Mapping[str, Any],
        persist_cb: Callable[[dict[str, Any]], None],
    ) -> None:
        self._parent = parent
        self._child_data: dict[str, Any] = dict(child_data)
        self._persist_cb = persist_cb

    @property
    def data(self) -> dict[str, Any]:
        # Parent-level option edits (made on the paired bed after pairing) win
        # over the frozen per-side descriptor for any shared key, so they aren't
        # silently shadowed for settings the coordinator reads from `.data`.
        # Per-side identity (address/side/bond) isn't in options, so it's kept.
        if self._parent.options:
            return {
                **self._child_data,
                **inheritable_child_fields(self._parent.options),
            }
        return self._child_data

    @property
    def options(self) -> Mapping[str, Any]:
        return inheritable_child_fields(self._parent.options)

    def persist_data(
        self,
        new_data: Mapping[str, Any],
        *,
        keys: Collection[str] | None = None,
    ) -> None:
        """Update this side's config in place and route selected keys to the parent."""
        if keys is None:
            self._child_data = dict(new_data)
            persisted_data = self._child_data
        else:
            for key in keys:
                if key in new_data:
                    self._child_data[key] = new_data[key]
                else:
                    self._child_data.pop(key, None)
            persisted_data = {key: self._child_data[key] for key in keys if key in self._child_data}
        self._persist_cb(persisted_data)

    def __getattr__(self, name: str) -> Any:
        # Anything not overridden above (entry_id, title, unique_id, version,
        # async_create_background_task, async_on_unload, ...) comes from the parent.
        return getattr(self._parent, name)


class AdjustableBedCoordinator:
    """Coordinator for managing bed connection and state."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the coordinator."""
        self.hass = hass
        self.entry = entry
        self._address: str = entry.data[CONF_ADDRESS].upper()
        self._bed_type: str = entry.data[CONF_BED_TYPE]
        self._protocol_variant: str = entry.data.get(
            CONF_PROTOCOL_VARIANT, DEFAULT_PROTOCOL_VARIANT
        )
        self._name: str = entry.data.get(CONF_NAME, "Adjustable Bed")
        # Malouf's APK has one command exception keyed to Smartbed238. Keep the
        # configured name as a controller fallback, but track actual observations
        # separately so protocol detection never relies on a user-facing rename.
        self._ble_device_name: str = entry.data.get(CONF_BLE_DEVICE_NAME, self._name)
        self._observed_ble_device_name: str | None = None
        self._malouf_layout: str = entry.data.get(CONF_MALOUF_LAYOUT, MALOUF_LAYOUT_AUTO)
        self._malouf_memory_slots: int = int(
            entry.data.get(CONF_MALOUF_MEMORY_SLOTS, MALOUF_MEMORY_SLOTS_AUTO)
        )
        self._richmat_remote: str = entry.data.get(CONF_RICHMAT_REMOTE, RICHMAT_REMOTE_AUTO)
        if self._bed_type == BED_TYPE_RICHMAT:
            self._richmat_remote = resolve_richmat_remote_code(
                self._richmat_remote,
                entry_title=entry.title,
                configured_name=self._name,
            )
            self._motor_count = get_richmat_motor_count(get_richmat_features(self._richmat_remote))
        else:
            self._motor_count = entry.data.get(CONF_MOTOR_COUNT, DEFAULT_MOTOR_COUNT)
        self._has_massage: bool = entry.data.get(CONF_HAS_MASSAGE, DEFAULT_HAS_MASSAGE)
        self._disable_angle_sensing: bool = entry.data.get(
            CONF_DISABLE_ANGLE_SENSING, DEFAULT_DISABLE_ANGLE_SENSING
        )
        self._passive_position_reconciliation_enabled: bool = bool(
            entry.data.get(
                CONF_PASSIVE_POSITION_RECONCILIATION,
                passive_position_reconciliation_default_enabled(self._bed_type),
            )
        )
        self._position_mode: str = entry.data.get(CONF_POSITION_MODE, DEFAULT_POSITION_MODE)
        self._preferred_adapter: str = entry.data.get(CONF_PREFERRED_ADAPTER, ADAPTER_AUTO)

        # Connection profile settings
        self._connection_profile: str = entry.data.get(
            CONF_CONNECTION_PROFILE, DEFAULT_CONNECTION_PROFILE
        )
        profile_settings = CONNECTION_PROFILES.get(self._connection_profile)
        if profile_settings is None:
            _LOGGER.warning(
                "Unknown connection profile '%s'; defaulting to '%s'",
                self._connection_profile,
                DEFAULT_CONNECTION_PROFILE,
            )
            self._connection_profile = DEFAULT_CONNECTION_PROFILE
            profile_settings = CONNECTION_PROFILES[DEFAULT_CONNECTION_PROFILE]
        self._max_retries: int = profile_settings.max_retries
        self._retry_base_delay: float = profile_settings.retry_base_delay
        self._retry_jitter: float = profile_settings.retry_jitter
        self._connection_timeout: float = profile_settings.connection_timeout
        self._post_connect_delay: float = profile_settings.post_connect_delay

        # Get bed-type-specific motor pulse defaults, falling back to global defaults
        bed_pulse_defaults = get_motor_pulse_defaults(
            self._bed_type,
            self._protocol_variant,
        )
        self._motor_pulse_count: int = entry.data.get(CONF_MOTOR_PULSE_COUNT, bed_pulse_defaults[0])
        self._motor_pulse_delay_ms: int = entry.data.get(
            CONF_MOTOR_PULSE_DELAY_MS, bed_pulse_defaults[1]
        )

        # Disconnect behavior configuration
        self._disconnect_after_command: bool = entry.data.get(
            CONF_DISCONNECT_AFTER_COMMAND, DEFAULT_DISCONNECT_AFTER_COMMAND
        )
        self._idle_disconnect_seconds: int = entry.data.get(
            CONF_IDLE_DISCONNECT_SECONDS, DEFAULT_IDLE_DISCONNECT_SECONDS
        )

        # Octo-specific configuration
        self._octo_pin: str = entry.data.get(CONF_OCTO_PIN, DEFAULT_OCTO_PIN)

        # Jensen-specific configuration
        self._jensen_pin: str = entry.data.get(CONF_JENSEN_PIN, "")

        # CB24-specific configuration (SmartBed by Okin split beds)
        self._cb24_bed_selection: int = entry.data.get(CONF_CB24_BED_SELECTION, 0x00)

        self._client: BleakClient | None = None
        self._controller: BedController | None = None
        # A client-free controller minted from config purely to read this bed's
        # CAPABILITIES (which entities to expose) when no live controller exists.
        # Paired children prime this before platform setup so an offline side
        # still gets its per-side entities up-front. None until primed / for bed
        # types whose controller needs a live connection (auto-detected variants).
        self._offline_controller: BedController | None = None
        # Persistence is a property of the resolved controller, but _on_disconnect
        # clears the controller before the reconnect decision runs. Cache the last
        # resolved value so connection-lifecycle checks stay correct across the
        # disconnect (issue #385 review).
        self._persistent_connection_resolved: bool | None = None
        self._disconnect_timer: asyncio.TimerHandle | None = None
        self._reconnect_timer: asyncio.TimerHandle | None = None
        self._lock = asyncio.Lock()
        self._command_lock = asyncio.Lock()  # Separate lock for command serialization
        self._command_scheduler = DeviceCommandScheduler(self._address.replace(":", "_"))
        self._connecting: bool = False  # Track if we're actively connecting
        self._intentional_disconnect: bool = (
            False  # Track intentional disconnects to skip auto-reconnect
        )
        self._cancel_command = asyncio.Event()  # Signal to cancel current command
        self._cancel_counter: int = 0  # Track cancellation requests to handle queued commands
        self._stop_keepalive_task: asyncio.Task[None] | None = None  # Track keepalive stop task
        self._background_read_task: asyncio.Task[None] | None = None  # Deduped position read

        # Position data from notifications
        self._position_data: dict[str, float] = {}
        self._position_data_generation: dict[str, int] = {}
        self._position_data_updated_monotonic: dict[str, float] = {}
        self._position_connection_generation = 0
        self._position_callbacks: set[Callable[[dict[str, float]], None]] = set()
        self._controller_state: dict[str, Any] = {}
        self._controller_state_callbacks: set[Callable[[dict[str, Any]], None]] = set()
        self._controller_state_refresh_task: asyncio.Task[None] | None = None
        self._controller_state_refresh_retry_timer: asyncio.TimerHandle | None = None
        self._controller_state_refresh_retry_count = 0
        self._controller_state_refresh_completed = False
        self._passive_position_reconciliation_interval_s: float | None = None
        self._passive_position_reconciliation_task: asyncio.Task[None] | None = None
        self._position_hydration_task: asyncio.Task[None] | None = None
        self._position_hydration_running = False
        self._position_hydration_pause_count = 0

        # Connection state callbacks
        self._connection_state_callbacks: set[Callable[[bool], None]] = set()

        # Connection metadata for binary sensor attributes
        self._last_connected: datetime | None = None
        self._last_disconnected: datetime | None = None
        self._connection_source: str | None = None
        # The structured path of the live link, and the evidence behind the last
        # authentication failure. Both exist so stale-bond recovery can be
        # scoped to the transport that actually saw the failure (issue #459).
        self._connection_path: ConnectionPath | None = None
        self._last_bond_evidence: BondEvidence | None = None
        self._connection_rssi: int | None = None

        # BLE Device Information Service data
        self._ble_manufacturer: str | None = None
        self._ble_model: str | None = None
        self._device_info_read_done: bool = False
        self._device_info_read_attempts: int = 0
        self._bond_probe_timed_out: bool = False

        # Track if pairing is supported by the Bluetooth adapter (None = unknown)
        self._pairing_supported: bool | None = None
        self._ble_bond_established: bool = bool(entry.data.get(CONF_BLE_BOND_ESTABLISHED, False))
        # Sticky: this device has already demonstrated that a cached bond marker
        # does not survive to the next connection, so stop skipping pair=True.
        self._ble_bond_marker_unreliable: bool = bool(
            entry.data.get(CONF_BLE_BOND_MARKER_UNRELIABLE, False)
        )
        # Set just before an internal bond-marker write; see
        # _begin_internal_entry_update().
        self._pending_internal_bond_marker: bool | None = None
        # Learning a Solace profile changes which entities should exist. Persist
        # the name immediately, but defer the resulting reload until this link is
        # released so discovery cannot unload us halfway through a connection.
        self._pending_capability_reload = False
        self._capability_reload_scheduled = False
        self._shutting_down = False
        self._last_bond_verification: dict[str, Any] = {
            "status": "not_attempted",
            "timestamp": None,
            "error": None,
            "error_type": None,
        }
        # Transient (in-memory only) flag: a pairing attempt just failed, so the
        # single next connection attempt should skip pair=True (some stacks fail
        # to re-pair on top of an existing bond). Unlike the persisted bond
        # marker, this never poisons the config entry, so a transient pairing
        # failure cannot permanently prevent future pairing attempts.
        self._skip_pair_next_attempt: bool = False
        # True when the most recent attempt skipped pair=True purely because
        # CONF_BLE_BOND_ESTABLISHED said we were already bonded. An auth failure
        # under that condition is what proves the marker unreliable.
        self._attempt_trusted_bond_marker: bool = False
        # Whether the most recent attempt actually requested pair=True. A bond
        # that verifies on an attempt that did NOT pair proves the bond survives
        # on this stack, which is what releases the latch below.
        self._attempt_used_pairing: bool = False
        # Consecutive successful paired connections made while the latch is set.
        # Runtime only: a reload re-tests anyway.
        self._latched_pairing_successes: int = 0

        # Connection history tracking for diagnostics (issue #168)
        self._connection_attempt_count: int = 0
        self._connection_success_count: int = 0
        self._last_connection_attempt: datetime | None = None
        self._last_connection_error: str | None = None
        self._last_connection_error_type: str | None = None
        self._last_disconnect_reason: str | None = (
            None  # "idle_timeout", "intentional", "unexpected"
        )

        # Protocol-operation timing remains separate from scheduler intent timing.
        self._last_protocol_operation_start: datetime | None = None
        self._last_protocol_operation_end: datetime | None = None
        self._active_operation_name: str | None = None
        self._last_notify_received: datetime | None = None

        # Per-axis seek state: typed terminal outcomes for diagnostics and the
        # last commanded motion so a replacement seek's policy can distinguish
        # same-direction from opposite-direction transitions.
        self._seek_outcomes: dict[str, dict[str, Any]] = {}
        self._last_seek_motion: dict[str, SeekMotion] = {}

        # Adapter selection details for diagnostics (issue #168)
        self._actual_adapter: str | None = None
        self._available_adapters: list[str] = []
        self._command_trace: deque[dict[str, Any]] = deque(maxlen=MAX_COMMAND_TRACE_ENTRIES)
        self._connection_attempt_details: deque[dict[str, Any]] = deque(
            maxlen=MAX_CONNECTION_ATTEMPT_DETAILS
        )

        _LOGGER.debug(
            "Coordinator initialized for %s at %s (type: %s, motors: %d, massage: %s, disable_angle_sensing: %s, adapter: %s, connection_profile: %s)",
            self._name,
            self._address,
            self._bed_type,
            self._motor_count,
            self._has_massage,
            self._disable_angle_sensing,
            self._preferred_adapter,
            self._connection_profile,
        )

    def _async_persist_config(
        self,
        new_data: dict[str, Any],
        *,
        keys: Collection[str] | None = None,
    ) -> None:
        """Persist a runtime config change to the correct backing store.

        For a paired child the entry is a ChildEntryView, which routes the update
        to the parent's per-side descriptor. For a single bed it is the real
        entry, so this is exactly the previous async_update_entry call.
        """
        entry = self.entry
        if isinstance(entry, ChildEntryView):
            entry.persist_data(new_data, keys=keys)
        else:
            self.hass.config_entries.async_update_entry(entry, data=new_data)

    def _record_observed_ble_device_name(self, device_name: str) -> None:
        """Remember the advertising name used by protocol capability routing."""
        self._ble_device_name = device_name
        self._observed_ble_device_name = device_name
        if (
            self._bed_type == BED_TYPE_SOLACE
            and self.entry.data.get(CONF_BLE_DEVICE_NAME) != device_name
        ):
            self._begin_internal_entry_update(
                bool(self.entry.data.get(CONF_BLE_BOND_ESTABLISHED, False))
            )
            if self._pending_internal_bond_marker is not None:
                self._pending_capability_reload = True
            self._async_persist_config(
                {**self.entry.data, CONF_BLE_DEVICE_NAME: device_name},
                keys={CONF_BLE_DEVICE_NAME},
            )

    def _schedule_pending_capability_reload(self) -> None:
        """Reload capability-gated entities once this BLE link is released."""
        if (
            not self._pending_capability_reload
            or self._capability_reload_scheduled
            or self._shutting_down
        ):
            return
        self._capability_reload_scheduled = True
        self.hass.async_create_task(
            self._async_reload_after_capability_change(),
            f"adjustable_bed_capability_reload_{self._address}",
        )

    async def _async_reload_after_capability_change(self) -> None:
        """Wait for commands to release the link, then reconcile entity platforms."""
        try:
            loaded = self.hass.data.get(DOMAIN, {}).get(self.entry.entry_id)
            reload_guard = (
                getattr(loaded, "async_capability_reload_guard", None)
                if isinstance(self.entry, ChildEntryView)
                else None
            )
            if callable(reload_guard):
                typed_reload_guard = cast(
                    Callable[[], contextlib.AbstractAsyncContextManager[None]],
                    reload_guard,
                )
                async with typed_reload_guard():
                    await self._async_reload_if_capability_changed()
            else:
                async with self.async_command_operation_guard():
                    await self._async_reload_if_capability_changed()
        finally:
            self._capability_reload_scheduled = False

    async def _async_reload_if_capability_changed(self) -> None:
        """Reload if this disconnected coordinator still owns the loaded entry."""
        if not self._pending_capability_reload or self._shutting_down:
            return
        if self._client is not None and self._client.is_connected:
            return
        loaded = self.hass.data.get(DOMAIN, {}).get(self.entry.entry_id)
        owns_loaded_child = False
        if isinstance(self.entry, ChildEntryView) and loaded is not None:
            child_for_side = getattr(loaded, "child_for_side", None)
            side = self.entry.data.get(CONF_SIDE)
            owns_loaded_child = callable(child_for_side) and child_for_side(side) is self
        if loaded is not self and not owns_loaded_child:
            return
        self._pending_capability_reload = False
        await self.hass.config_entries.async_reload(self.entry.entry_id)

    @contextlib.asynccontextmanager
    async def async_command_operation_guard(self) -> AsyncIterator[None]:
        """Wait for this child's command lane and keep it idle."""
        async with self._command_lock:
            yield

    def _capability_reload_blocks_connection(self) -> bool:
        """Return whether a deferred entity reload owns the next disconnected state."""
        link_is_up = self._client is not None and self._client.is_connected
        return (
            self._pending_capability_reload or self._capability_reload_scheduled
        ) and not link_is_up

    def _apply_runtime_bed_type_correction(self, corrected_bed_type: str) -> bool:
        """Apply a protocol correction discovered after BLE service discovery."""
        previous_bed_type = self._bed_type

        bed_type_changed = corrected_bed_type != previous_bed_type
        if bed_type_changed:
            _LOGGER.warning(
                "Correcting bed protocol for %s from %s to %s based on connected GATT services",
                self._address,
                previous_bed_type,
                corrected_bed_type,
            )
        previous_defaults = BED_MOTOR_PULSE_DEFAULTS.get(previous_bed_type)
        corrected_uses_leggett_okin = corrected_bed_type == BED_TYPE_LEGGETT_OKIN or (
            corrected_bed_type == BED_TYPE_LEGGETT_PLATT
            and self._protocol_variant == LEGGETT_VARIANT_OKIN
        )
        corrected_defaults = BED_MOTOR_PULSE_DEFAULTS.get(
            BED_TYPE_LEGGETT_OKIN if corrected_uses_leggett_okin else corrected_bed_type
        )
        # Only swap in the corrected protocol's defaults if the user never set
        # their own pulse values. Comparing against ``previous_defaults`` alone is
        # not enough: an explicit override can coincidentally equal the previous
        # bed type's defaults (e.g. NEW_OKIN's (10, 100)), and we must not silently
        # overwrite it. Pulse values are read from ``entry.data`` in __init__, so
        # presence of these keys there is the authoritative override boundary.
        has_custom_pulse_override = (
            CONF_MOTOR_PULSE_COUNT in self.entry.data
            or CONF_MOTOR_PULSE_DELAY_MS in self.entry.data
        )
        # Config flows historically persisted generated defaults even when the
        # user did not customize them, so the presence of the pulse keys proves
        # nothing on its own. Restrict this migration to the Leggett Okin upgrade
        # paths so unrelated explicit settings remain intact.
        previous_uses_leggett_okin = previous_bed_type == BED_TYPE_LEGGETT_OKIN or (
            previous_bed_type == BED_TYPE_LEGGETT_PLATT
            and self._protocol_variant == LEGGETT_VARIANT_OKIN
        )
        # Entries carrying the superseded (5, 200) cadence got it from an earlier
        # release of this migration rather than from the user, so move them to the
        # cadence the Prodigy CE analysis proved. CONF_MOTOR_PULSE_USER_SET is the
        # provenance that keeps a deliberate choice out of this: without it the
        # migration reverted the user's own values on every connect, which is why
        # the option looked unsavable (issue #368).
        migrate_leggett_okin_defaults = (
            not self.entry.data.get(CONF_MOTOR_PULSE_USER_SET, False)
            and (previous_uses_leggett_okin or previous_bed_type == BED_TYPE_OKIN_CST)
            and corrected_uses_leggett_okin
            and (self._motor_pulse_count, self._motor_pulse_delay_ms)
            == LEGGETT_OKIN_SUPERSEDED_PULSE_DEFAULTS
        )
        if corrected_defaults is not None and (
            migrate_leggett_okin_defaults
            or (
                bed_type_changed
                and previous_defaults is not None
                and not has_custom_pulse_override
                and (self._motor_pulse_count, self._motor_pulse_delay_ms) == previous_defaults
            )
        ):
            self._motor_pulse_count, self._motor_pulse_delay_ms = corrected_defaults
            _LOGGER.info(
                "Updated motor pulse defaults for corrected %s protocol: count=%s, delay=%sms",
                corrected_bed_type,
                self._motor_pulse_count,
                self._motor_pulse_delay_ms,
            )

        self._bed_type = corrected_bed_type
        # The cached offline capability-controller was minted for the OLD type;
        # drop it ONLY on an actual change, so a no-op correction doesn't discard
        # the already-primed offline fallback (which capability_controller would
        # then miss after a later disconnect).
        if bed_type_changed:
            self._offline_controller = None

        entry_data = dict(self.entry.data)
        entry_data[CONF_BED_TYPE] = corrected_bed_type
        if migrate_leggett_okin_defaults and corrected_defaults is not None:
            entry_data[CONF_MOTOR_PULSE_COUNT] = corrected_defaults[0]
            entry_data[CONF_MOTOR_PULSE_DELAY_MS] = corrected_defaults[1]
        if corrected_bed_type == BED_TYPE_BEDTECH:
            entry_data.pop(CONF_RICHMAT_REMOTE, None)
        angle_sensing_defaulted = CONF_DISABLE_ANGLE_SENSING not in self.entry.data or (
            self.entry.data.get(CONF_DISABLE_ANGLE_SENSING) is True
            and previous_bed_type not in BEDS_WITH_POSITION_FEEDBACK
        )
        # Config flow defaults disable_angle_sensing from BEDS_WITH_POSITION_FEEDBACK,
        # so the correction must use the same set: a repaired entry (e.g. CB35 ->
        # BOX25, #419) should get position feedback re-enabled even when the
        # corrected type reports percentages rather than angles.
        if (
            corrected_bed_type in BEDS_WITH_POSITION_FEEDBACK
            and angle_sensing_defaulted
            and self._disable_angle_sensing
        ):
            self._disable_angle_sensing = False
            entry_data[CONF_DISABLE_ANGLE_SENSING] = False
            _LOGGER.info(
                "Enabled position feedback for corrected %s protocol on %s: "
                "the previous entry used the legacy default",
                corrected_bed_type,
                self._address,
            )
        elif (
            bed_type_changed
            and corrected_bed_type not in BEDS_WITH_POSITION_FEEDBACK
            and not self._disable_angle_sensing
        ):
            self._disable_angle_sensing = True
            entry_data[CONF_DISABLE_ANGLE_SENSING] = True
            _LOGGER.info(
                "Disabled angle sensing for corrected %s protocol on %s: "
                "the corrected profile does not support position feedback",
                corrected_bed_type,
                self._address,
            )

        entry_data_changed = entry_data != self.entry.data
        if entry_data_changed:
            self._async_persist_config(entry_data)

        return bed_type_changed or entry_data_changed

    @property
    def address(self) -> str:
        """Return the Bluetooth address."""
        return self._address

    @property
    def operation_identity(self) -> int:
        """Return the identity of this physical command scheduler."""
        return id(self._command_scheduler)

    def entity_unique_id(self, key: str) -> str:
        """Return the stable unique id for one standalone entity key."""
        return f"{self._address}_{key}"

    def entity_translation_key(self, key: str) -> str:
        """Return the translation key for one standalone entity."""
        return key

    @property
    def name(self) -> str:
        """Return the bed name."""
        return self._name

    @property
    def ble_device_name(self) -> str:
        """Return the observed BLE name or configured fallback for controller logic."""
        return self._ble_device_name

    @property
    def observed_ble_device_name(self) -> str | None:
        """Return the most recently observed BLE advertising name, if any."""
        return self._observed_ble_device_name

    @property
    def malouf_layout(self) -> str:
        """Return the configured Malouf actuator layout."""
        return self._malouf_layout

    @property
    def malouf_memory_slots(self) -> int:
        """Return the configured Malouf memory-slot override (0 means auto)."""
        return self._malouf_memory_slots

    @property
    def last_bond_evidence(self) -> BondEvidence | None:
        """Return what the most recent authentication-gated check actually saw.

        Exposed so a repair can tell "this pairing was proven, and provenance is
        already recorded" from "nothing established an owner this time". The
        difference decides whether an existing provenance record is still
        trustworthy or has to be dropped.
        """
        return self._last_bond_evidence

    @property
    def bed_type(self) -> str:
        """Return the bed type."""
        return self._bed_type

    @property
    def motor_count(self) -> int:
        """Return the motor count."""
        return self._motor_count

    @property
    def has_massage(self) -> bool:
        """Return whether the bed has massage."""
        return self._has_massage

    @property
    def disable_angle_sensing(self) -> bool:
        """Return whether angle sensing is disabled."""
        return self._disable_angle_sensing

    @property
    def back_max_angle(self) -> float:
        """Return the maximum angle for back motor (also used for head)."""
        # Check options first (runtime config), then entry data (initial config)
        if CONF_BACK_MAX_ANGLE in self.entry.options:
            return float(self.entry.options[CONF_BACK_MAX_ANGLE])
        if CONF_BACK_MAX_ANGLE in self.entry.data:
            return float(self.entry.data[CONF_BACK_MAX_ANGLE])
        return DEFAULT_BACK_MAX_ANGLE

    @property
    def legs_max_angle(self) -> float:
        """Return the maximum angle for legs motor (also used for feet)."""
        # Check options first (runtime config), then entry data (initial config)
        if CONF_LEGS_MAX_ANGLE in self.entry.options:
            return float(self.entry.options[CONF_LEGS_MAX_ANGLE])
        if CONF_LEGS_MAX_ANGLE in self.entry.data:
            return float(self.entry.data[CONF_LEGS_MAX_ANGLE])
        return DEFAULT_LEGS_MAX_ANGLE

    @property
    def head_max_angle(self) -> float:
        """Return the maximum angle for head motor (derived from back)."""
        return self.back_max_angle

    @property
    def feet_max_angle(self) -> float:
        """Return the maximum angle for feet motor (derived from legs)."""
        return self.legs_max_angle

    def get_max_angle(self, position_key: str) -> float:
        """Get the max angle for a motor position key.

        Args:
            position_key: Motor name ("back", "legs", "head", or "feet")

        Returns:
            Maximum angle in degrees for the specified motor.
        """
        # Deliberately keyed on bed type rather than the controller's
        # motor_max_angles: this limit must hold while disconnected, so that
        # set_position validation still rejects a target the frame cannot reach
        # when the controller is momentarily absent.
        if position_key in ("back", "head"):
            if self._bed_type in (BED_TYPE_REVERIE, BED_TYPE_REVERIE_NIGHTSTAND):
                return REVERIE_BACK_MAX_ANGLE
            return self.back_max_angle
        if position_key in ("legs", "feet"):
            return self.legs_max_angle
        # Unknown motor, return back max as default
        return self.back_max_angle

    @property
    def motor_pulse_count(self) -> int:
        """Return the motor pulse count."""
        context = current_command_context()
        if (
            context is not None
            and context.scheduler_token is self._command_scheduler.token
            and context.pulse_count is not None
        ):
            return context.pulse_count
        return self._motor_pulse_count

    @property
    def motor_pulse_delay_ms(self) -> int:
        """Return the motor pulse delay in milliseconds."""
        context = current_command_context()
        if (
            context is not None
            and context.scheduler_token is self._command_scheduler.token
            and context.pulse_delay_ms is not None
        ):
            return context.pulse_delay_ms
        return self._motor_pulse_delay_ms

    @property
    def controller(self) -> BedController | None:
        """Return the bed controller."""
        return self._controller

    @property
    def capability_controller(self) -> BedController | None:
        """Return the controller to read CAPABILITIES from (which entities to expose).

        The live controller when connected, else a client-free 'offline'
        controller minted from config. Paired children prime the offline
        controller before platform setup so an offline side still gets its
        per-side entities (with byte-identical unique_ids), and the live
        controller silently takes over on connect with no reload. None when
        neither exists (e.g. an auto-detected-variant bed that has never
        connected) — in which case behaviour is exactly as before.
        """
        if self._controller is not None:
            return self._controller
        return self._offline_controller

    async def async_prime_offline_controller(self) -> None:
        """Best-effort mint of a client-free controller for capability reads.

        Construction only — never connects or starts notifications. Failures are
        non-fatal (a bad mint just leaves this side as before). Bed types whose
        controller needs a live client (auto-detected Richmat/L&P/Keeson
        variants) raise ConnectionError and are left without an offline
        controller until they connect.
        """
        if self._offline_controller is not None or self._controller is not None:
            return
        # Resolve a legacy umbrella bed type (leggett_platt) with an explicit
        # variant to its concrete type, so a Gen2/WiLinke side that the pairing
        # gate accepted as offline-safe is actually minted here (the raw umbrella
        # type is not in OFFLINE_CAPABILITY_SAFE_BED_TYPES). Idempotent for a
        # descriptor already normalised at pairing, and for every other bed type.
        bed_type = resolve_explicit_bed_type(self._bed_type, self._protocol_variant)
        # Octo is not statically offline-safe (it discovers capabilities post
        # connect), but a paired side that captured a capability snapshot AT
        # PAIRING can be minted offline from that snapshot.
        octo_snapshot = (
            octo_snapshot_from_descriptor(self.entry.data) if bed_type == BED_TYPE_OCTO else None
        )
        capabilities = self.entry.data.get("capabilities")
        linak_snapshot = (
            capabilities.get("linak")
            if bed_type == BED_TYPE_LINAK and isinstance(capabilities, dict)
            else None
        )
        # Octo Remote Star2 is a different protocol with FIXED capabilities and no
        # PIN/snapshot, so it IS statically offline-mintable (like Linak) — its
        # controller builds without a client.
        is_octo_star2 = bed_type == BED_TYPE_OCTO and self._protocol_variant == OCTO_VARIANT_STAR2
        is_linak_performance = (
            bed_type == BED_TYPE_LINAK and self._protocol_variant == LINAK_VARIANT_PERFORMANCE
        )
        statically_mintable = bed_type in OFFLINE_CAPABILITY_SAFE_BED_TYPES and (
            bed_type != BED_TYPE_SOLACE
            or isinstance(self.entry.data.get(CONF_BLE_DEVICE_NAME), str)
        )
        mintable = (
            statically_mintable
            or (bed_type == BED_TYPE_OCTO and (octo_snapshot is not None or is_octo_star2))
            or (bed_type == BED_TYPE_LINAK and (linak_snapshot is not None or is_linak_performance))
        )
        if not mintable:
            # Only beds whose entity-gating capabilities are fully determined by
            # stored config offline are safe to mint without a live connection.
            # Others auto-detect their variant from live GATT/advertisement, can
            # be connect-time corrected to a different bed_type, or mutate
            # capabilities from a post-connect query — minting offline would
            # register entities from a WRONG profile. They keep today's behaviour
            # (no offline entities until the side connects).
            return
        try:
            self._offline_controller = await create_controller(
                coordinator=self,
                bed_type=bed_type,
                protocol_variant=self._protocol_variant,
                client=None,
                device_name=self._name,
                octo_pin=self._octo_pin,
                richmat_remote=self._richmat_remote,
                jensen_pin=self._jensen_pin,
                cb24_bed_selection=self._cb24_bed_selection,
                capability_snapshot=octo_snapshot or linak_snapshot,
            )
        except ConnectionError:
            # Auto-detected variant: needs a live client to resolve. Leave the
            # offline controller unset (this side behaves as today until connect).
            self._offline_controller = None
        except Exception:  # noqa: BLE001 - capability priming must never block setup
            _LOGGER.debug(
                "Offline capability-controller mint failed for %s",
                self._name,
                exc_info=True,
            )
            self._offline_controller = None

    def cache_capability_controller(self) -> None:
        """Retain the current live controller as the client-free offline
        capability controller, so its discovered capabilities survive a
        disconnect.

        A sequential pair connects each side at setup then releases it; that
        disconnect drops the live controller, and a bed that can't be minted
        offline from config/snapshot would otherwise build no per-side entities.
        Caching the just-discovered live controller keeps them. No-op if an
        offline controller is already set or there is no live controller.
        """
        if self._offline_controller is None and self._controller is not None:
            self._offline_controller = self._controller

    @property
    def position_data(self) -> dict[str, float]:
        """Return current position data."""
        return self._position_data

    @property
    def controller_state(self) -> dict[str, Any]:
        """Return non-position controller state."""
        return self._controller_state

    @property
    def is_connected(self) -> bool:
        """Return whether we are currently connected to the bed."""
        return self._client is not None and self._client.is_connected

    @property
    def is_connecting(self) -> bool:
        """Return whether we are currently connecting to the bed."""
        return self._connecting

    @property
    def last_connected(self) -> datetime | None:
        """Return the last connection timestamp."""
        return self._last_connected

    @property
    def last_disconnected(self) -> datetime | None:
        """Return the last disconnection timestamp."""
        return self._last_disconnected

    @property
    def last_disconnect_reason(self) -> str | None:
        """Return why the bed last disconnected (for diagnostics/UI).

        Common values: ``idle_timeout``, ``intentional``,
        ``authentication_failed``, ``unexpected``. Intentional/idle reasons mean
        the bed is fine and will reconnect on demand on the next command.
        """
        return self._last_disconnect_reason

    @property
    def connection_source(self) -> str | None:
        """Return the adapter/source used for the current connection."""
        return self._connection_source

    @property
    def connection_rssi(self) -> int | None:
        """Return the RSSI at connection time."""
        return self._connection_rssi

    @property
    def client(self) -> BleakClient | None:
        """Return the BLE client (for diagnostics)."""
        return self._client

    @property
    def pairing_supported(self) -> bool | None:
        """Return whether the Bluetooth adapter supports pairing.

        None = not yet determined, True = supported, False = not supported.
        """
        return self._pairing_supported

    def _device_reports_existing_bond(self, device: BLEDevice | None = None) -> bool:
        """Return True when HA/BlueZ reports this bed as already paired or bonded."""
        return any(
            state.get("paired") is True or state.get("bonded") is True
            for state in self._device_pairing_states(device)
        )

    def _device_pairing_states(self, device: BLEDevice | None = None) -> list[dict[str, Any]]:
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
        self,
        status: str,
        error: BaseException | None = None,
        attempt_details: dict[str, Any] | None = None,
    ) -> None:
        """Record the latest auth-gated bond probe outcome for diagnostics."""
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

    def _backfill_octo_snapshot(self) -> None:
        """Persist this paired Octo side's freshly-discovered capabilities into its
        child descriptor, so the OFFLINE side and reloads mint correct entities and
        a firmware capability change is reflected. No-op for a single bed (not a
        ``ChildEntryView``) or when nothing was discovered / it is unchanged.
        """
        if not isinstance(self.entry, ChildEntryView):
            return
        snapshot_fn = getattr(self._controller, "capability_snapshot", None)
        snapshot = snapshot_fn() if callable(snapshot_fn) else None
        if not snapshot:
            return
        capabilities = dict(self.entry.data.get("capabilities") or {})
        if capabilities.get("octo") == snapshot:
            return  # unchanged — avoid a redundant persist
        capabilities["octo"] = snapshot
        self._async_persist_config({**self.entry.data, "capabilities": capabilities})
        # The offline controller minted from the pairing-time snapshot is now stale
        # (cache_capability_controller only fills an EMPTY slot, so it never refreshes
        # it). Point it at the live controller — the same client-free capability
        # source — so a later sequential release gates per-side entities off the
        # freshly discovered capabilities, not the old snapshot, before the next
        # reload.
        self._offline_controller = self._controller

    def _backfill_linak_snapshot(self) -> None:
        """Persist a successful Linak model/capability resolution."""
        snapshot_fn = getattr(self._controller, "capability_snapshot", None)
        snapshot = snapshot_fn() if callable(snapshot_fn) else None
        if not isinstance(snapshot, Mapping) or snapshot.get("discovery_complete") is not True:
            return
        capabilities = dict(self.entry.data.get("capabilities") or {})
        if capabilities.get("linak") == snapshot:
            return
        capabilities["linak"] = snapshot
        self._async_persist_config({**self.entry.data, "capabilities": capabilities})
        self._offline_controller = self._controller

    def _persist_bond_flags(
        self,
        *,
        established: bool | None = None,
        unreliable: bool | None = None,
        context: dict[str, Any] | None = None,
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
        self,
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

    def _record_bond_provenance(self) -> None:
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

    def _begin_internal_entry_update(self, bond_established: bool) -> None:
        """Mark the next entry update as an internal bond-marker write.

        Every ``async_update_entry`` fires the options update listener, which
        reloads the entry — unloading the coordinator and disconnecting the bed.
        Recording our own bond-marker state here lets that listener recognise
        the write as internal and skip the reload. Without this, simply noting
        "this link is not bonded" would tear down the link we just decided to
        keep, and a bed that grants one connection per pairing window would be
        unreachable until it is power-cycled (issue #385).

        Only arm the marker when a listener can actually consume it. During
        initial setup the bond is written before ``async_setup_entry`` registers
        the update listener and stores this coordinator, so nothing would ever
        clear it — and the next genuine options change, which keeps the same
        bond value, would then be mistaken for this write and silently skip the
        reload it needs.
        """
        loaded = self.hass.data.get(DOMAIN, {}).get(self.entry.entry_id)
        owns_loaded_child = False
        if isinstance(self.entry, ChildEntryView) and loaded is not None:
            child_for_side = getattr(loaded, "child_for_side", None)
            side = self.entry.data.get(CONF_SIDE)
            owns_loaded_child = callable(child_for_side) and child_for_side(side) is self
        if loaded is not self and not owns_loaded_child:
            self._pending_internal_bond_marker = None
            return
        self._pending_internal_bond_marker = bond_established

    def consume_internal_entry_update(self, entry: ConfigEntry) -> bool:
        """Return True when ``entry`` reflects our own bond-marker write.

        Consumes the marker, so a genuine user-driven options change that
        happens to follow one still reloads normally.
        """
        pending = self._pending_internal_bond_marker
        if pending is None:
            return False
        self._pending_internal_bond_marker = None
        current_data = self.entry.data if isinstance(self.entry, ChildEntryView) else entry.data
        return bool(current_data.get(CONF_BLE_BOND_ESTABLISHED, False)) is pending

    def _mark_ble_bond_established(self) -> None:
        """Record that future connections should skip `pair=True`."""
        if self._ble_bond_marker_unreliable:
            # Skipping pairing on this device has already been proven wrong once.
            # Re-arming the marker here is what made it flip-flop: every connect
            # spent a doomed unpaired attempt before succeeding on the retry.
            return

        if self._ble_bond_established:
            return

        self._persist_bond_flags(established=True)

    def _clear_ble_bond_established(self) -> None:
        """Clear the persisted bond marker after an authentication failure."""
        if not self._ble_bond_established and not self.entry.data.get(CONF_BLE_BOND_ESTABLISHED):
            return

        self._persist_bond_flags(established=False)

    def apply_confirmed_bond_removal(self) -> None:
        """Clear all runtime and persisted state for a confirmed bond removal."""
        self._discard_bond_tracking()

    def _discard_bond_tracking(self) -> None:
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

    async def async_clear_obsolete_pairing_state(self) -> None:
        """Remove stale pairing state when this protocol no longer requires it."""
        if requires_pairing(self._bed_type, self._protocol_variant):
            return
        self._discard_bond_tracking()
        await delete_pairing_required_issue(self.hass, self._address)

    def _log_bond_marker_unreliable(self) -> None:
        """Log the latch transition. The write itself is batched by the caller."""
        _LOGGER.info(
            "Cached bond marker for %s did not survive to this connection; "
            "requesting pairing on every future connection attempt",
            self._address,
        )

    def _log_bond_marker_reliable_again(self) -> None:
        """Log the latch release. The write itself is batched by the caller."""
        _LOGGER.info(
            "Bond for %s survived a connection that did not request pairing; "
            "trusting the cached bond marker again",
            self._address,
        )

    async def _async_handle_ble_authentication_error(
        self,
        err: BleakError,
        *,
        holding_lock: bool = False,
        retain_link: bool = False,
        attempt_details: dict[str, Any] | None = None,
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
        """
        if not requires_pairing(self._bed_type, self._protocol_variant):
            return

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
        )
        # A definitive authentication failure invalidates any earlier decision
        # to skip a probe that timed out. The next paired connection should
        # verify the fresh bond again.
        self._bond_probe_timed_out = False
        latch = self._attempt_trusted_bond_marker and not self._ble_bond_marker_unreliable
        if latch:
            self._log_bond_marker_unreliable()
        self._persist_bond_flags(
            established=False,
            unreliable=True if latch else None,
        )

        await self._async_raise_pairing_issue()

        if self._client is not None and self._client.is_connected:
            if retain_link and grants_one_connection_per_pairing_window(
                self._bed_type, self._protocol_variant
            ):
                # Disconnecting would cost us the box's single connection and
                # the reconnect that "fixes" the bond can never happen. Leave
                # the link up; the repair issue above tells the user to re-pair.
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

    async def _async_raise_pairing_issue(self) -> None:
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

    async def _async_pair_on_live_link(self, pairing_details: dict[str, Any]) -> bool:
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
        advisory = grants_one_connection_per_pairing_window(self._bed_type, self._protocol_variant)
        try:
            await client.pair()
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

    async def async_pair_now(self) -> bool:
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
                pairing_details: dict[str, Any] = {}
                if await self._async_pair_on_live_link(pairing_details):
                    self._mark_ble_bond_established()
                    await delete_pairing_required_issue(self.hass, self._address)
                    return True
                # The bond request failed but the link survived; the probe is
                # the authority on whether we are nevertheless bonded.
                return await self._async_verify_bonded() and self._ble_bond_established

            if not await self._async_connect_locked():
                return False
            return self._ble_bond_established

    async def _async_verify_bonded(self, attempt_details: dict[str, Any] | None = None) -> bool:
        """Probe an auth-gated characteristic to confirm the BLE bond is live.

        For beds that require pairing, a connection — even one made with
        ``pair=True`` — can succeed while the link is still unbonded; every
        encrypted characteristic then fails with GATT error=5 "Insufficient
        authentication". Reading one known auth-gated characteristic surfaces
        this so we can clear a stale bond marker and re-pair instead of
        silently staying unbonded.

        Returns True if the link is bonded (or the check is inconclusive), and
        False only when an authentication error is definitively observed — in
        which case the bond marker is cleared, a repair issue is raised, and the
        client is disconnected.
        """
        client = self._client
        if client is None or not client.is_connected:
            self._record_bond_verification("skipped_not_connected", attempt_details=attempt_details)
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
    def cancel_command(self) -> asyncio.Event:
        """Return the cancel command event."""
        context = current_command_context()
        if context is not None and context.scheduler_token is self._command_scheduler.token:
            return context.cancel_event
        return self._cancel_command

    @property
    def connection_history(self) -> dict[str, Any]:
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
    def pairing_diagnostics(self) -> dict[str, Any]:
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

    @property
    def adapter_details(self) -> dict[str, Any]:
        """Return adapter selection details for diagnostics."""
        return {
            "preferred": self._preferred_adapter,
            "actual": self._actual_adapter,
            "available": self._available_adapters,
        }

    @property
    def command_timing(self) -> dict[str, Any]:
        """Return command timing for diagnostics."""
        return {
            "protocol_operation_timing": {
                "last_started_at": (
                    self._last_protocol_operation_start.isoformat()
                    if self._last_protocol_operation_start
                    else None
                ),
                "last_finished_at": (
                    self._last_protocol_operation_end.isoformat()
                    if self._last_protocol_operation_end
                    else None
                ),
            },
            "last_notify_received": self._last_notify_received.isoformat()
            if self._last_notify_received
            else None,
            "position_seeks": {
                position_key: dict(record) for position_key, record in self._seek_outcomes.items()
            },
            "scheduler": self._command_scheduler.diagnostics,
        }

    @property
    def command_trace(self) -> list[dict[str, Any]]:
        """Return recent integration-issued BLE writes."""
        return list(self._command_trace)

    @property
    def connection_attempt_details(self) -> list[dict[str, Any]]:
        """Return detailed recent connection attempts."""
        return list(self._connection_attempt_details)

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info for this bed."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._address)},
            name=self._name,
            manufacturer=self._get_manufacturer(),
            model=self._get_model(),
            model_id=self._get_model_id(),
        )

    def _get_manufacturer(self) -> str:
        """Get manufacturer name based on bed type."""
        # Use BLE value if available and useful
        if self._is_useful_ble_value(self._ble_manufacturer):
            return self._ble_manufacturer  # type: ignore[return-value]

        # Fall back to hardcoded values based on bed type
        manufacturers = {
            BED_TYPE_LINAK: "Linak",
            BED_TYPE_RICHMAT: "Richmat",
            BED_TYPE_KEESON: "Keeson",
            BED_TYPE_SOLACE: "Solace",
            BED_TYPE_MOTOSLEEP: "MotoSleep",
            BED_TYPE_LEGGETT_PLATT: "Leggett & Platt",
            BED_TYPE_LEGGETT_GEN2: "Leggett & Platt",
            BED_TYPE_LEGGETT_OKIN: "Leggett & Platt",
            BED_TYPE_LEGGETT_WILINKE: "Leggett & Platt",
            BED_TYPE_LIMOSS: "Limoss",
            BED_TYPE_REVERIE: "Reverie",
            BED_TYPE_REVERIE_NIGHTSTAND: "Reverie",
            BED_TYPE_OKIMAT: "Okimat",
            BED_TYPE_ERGOMOTION: "Ergomotion",
            BED_TYPE_JIECANG: "Jiecang",
            BED_TYPE_DEWERTOKIN: "DewertOkin",
            BED_TYPE_OKIN_HANDLE: "Okin",
            BED_TYPE_OKIN_UUID: "Okin",
            BED_TYPE_OKIN_7BYTE: "Okin",
            BED_TYPE_OKIN_NORDIC: "Okin",
            BED_TYPE_OKIN_FFE: "Okin",
            BED_TYPE_OCTO: "Octo",
            BED_TYPE_MATTRESSFIRM: "MattressFirm",
            BED_TYPE_NECTAR: "Nectar",
            BED_TYPE_MALOUF_NEW_OKIN: "Malouf",
            BED_TYPE_MALOUF_LEGACY_OKIN: "Malouf",
            BED_TYPE_COMFORT_MOTION: "Comfort Motion",
            BED_TYPE_SERTA: "Serta",
            BED_TYPE_DIAGNOSTIC: "Unknown",
        }
        return manufacturers.get(self._bed_type, "Unknown")

    def _get_model(self) -> str:
        """Get model name based on bed type."""
        if self._is_useful_ble_value(self._ble_model):
            return self._ble_model  # type: ignore[return-value]
        return f"Adjustable Bed ({self._motor_count} motors)"

    def _get_model_id(self) -> str | None:
        """Return the resolved protocol model as device metadata when available."""
        if self._bed_type != BED_TYPE_LINAK:
            return None

        raw_variant = self._controller_state.get("linak_model_variant")
        if not isinstance(raw_variant, str) or raw_variant == "unknown":
            return None

        labels = {
            "standard": "Standard",
            "td3": "TD3",
            "advanced": "Advanced",
            "advanced_with_alarm": "Advanced with alarm",
            "performance_legacy": "Performance legacy",
        }
        return labels.get(raw_variant, raw_variant.replace("_", " ").title())

    def _is_useful_ble_value(self, value: str | None) -> bool:
        """Check if a BLE value is useful (not generic/unhelpful).

        Some devices return generic strings like "BLE Device" or the chipset
        manufacturer instead of the actual bed manufacturer. This filters those out.
        """
        if not value or not value.strip():
            return False

        normalized = value.strip().lower()

        # Generic/placeholder strings
        generic_values = {
            "unknown",
            "n/a",
            "na",
            "none",
            "null",
            "undefined",
            "ble device",
            "bluetooth device",
            "generic",
        }
        if normalized in generic_values:
            return False

        # Chipset manufacturers (not the actual bed manufacturer)
        chipset_manufacturers = {
            "nordic semiconductor",
            "nordic",
            "texas instruments",
            "ti",
            "realtek",
            "qualcomm",
            "broadcom",
            "espressif",
            "silicon labs",
            "dialog semiconductor",
            "cypress",
            "microchip",
            "stmicroelectronics",
        }
        return normalized not in chipset_manufacturers

    def _bed_type_needs_ble_model(self) -> bool:
        """Whether the current protocol refinement depends on the DIS model value.

        Shared-UUID OKIN profiles use the Device Information model to tell a
        multi-motor OKIMAT bed apart from a single-actuator RF ECO BT stair that
        exposes the same GATT signature (issue #406). If that model read times
        out transiently we must not latch a partial read as complete, or the
        bed would be misrouted to the stair profile on every future reconnect.
        """
        if self._bed_type in OKIN_SHARED_UUID_GATT_REFINABLE_TYPES:
            return True
        return (
            self._bed_type == BED_TYPE_LEGGETT_PLATT
            and self._protocol_variant == LEGGETT_VARIANT_OKIN
        )

    def _store_ble_device_info(
        self,
        manufacturer: str | None,
        model: str | None,
    ) -> None:
        """Store Device Information and decide whether reconnects should retry it."""
        self._device_info_read_attempts += 1
        self._ble_manufacturer = manufacturer
        self._ble_model = model

        manufacturer_useful = self._is_useful_ble_value(manufacturer)
        model_useful = self._is_useful_ble_value(model)
        has_useful_value = manufacturer_useful or model_useful

        # A protocol whose per-reconnect refinement needs the DIS model must not
        # cache a read where the model timed out (manufacturer answered, model
        # did not). Latching that partial read would freeze model=None forever
        # and demote an OKIMAT bed to the single-actuator RF ECO BT profile on
        # every reconnect. Require the model before we stop retrying; a genuinely
        # model-less bed re-reads cheaply (an absent characteristic errors fast,
        # only a transient timeout costs the read budget, which is what we want
        # to retry).
        required_fields_present = not self._bed_type_needs_ble_model() or model_useful

        read_succeeded = has_useful_value and required_fields_present
        profile_retry_exhausted = (
            self._bed_type in {BED_TYPE_OKIN_CST, BED_TYPE_OKIN_RF_ECO_BT}
            and self._device_info_read_attempts
            >= _OKIN_PRESERVED_PROFILE_DEVICE_INFO_MAX_READ_ATTEMPTS
        )
        self._device_info_read_done = read_succeeded or profile_retry_exhausted

        if profile_retry_exhausted and not read_succeeded:
            _LOGGER.debug(
                "Device Information read for %s did not return the model after "
                "%d attempts; caching the %s profile for this coordinator session.",
                self._address,
                self._device_info_read_attempts,
                self._bed_type,
            )
        elif not self._device_info_read_done:
            if has_useful_value and not required_fields_present:
                _LOGGER.debug(
                    "Device Information read for %s is missing the model this "
                    "protocol needs (manufacturer=%r, model=%r); retrying on the "
                    "next connection.",
                    self._address,
                    manufacturer,
                    model,
                )
            else:
                _LOGGER.debug(
                    "Device Information read for %s returned no useful values; "
                    "retrying on the next connection.",
                    self._address,
                )

    def record_command_trace(
        self,
        *,
        payload: dict[str, Any],
        characteristic_uuid: str,
        characteristic_handle: int | None,
        response: bool,
        repeat_count: int,
        repeat_delay_ms: int,
        command_origin: str | None,
        controller_class: str,
    ) -> None:
        """Record an integration-issued write for support bundles."""
        context = current_command_context()
        if context is not None and context.scheduler_token is not self._command_scheduler.token:
            context = None
        self._command_trace.append(
            {
                "timestamp": datetime.now(UTC).isoformat(),
                "controller_class": controller_class,
                "characteristic_uuid": characteristic_uuid,
                "characteristic_handle": characteristic_handle,
                "payload": payload,
                "write_mode": "with_response" if response else "without_response",
                "repeat_count": repeat_count,
                "repeat_delay_ms": repeat_delay_ms,
                "command_origin": command_origin,
                "operation_name": self._active_operation_name,
                "intent_id": context.intent_id if context is not None else None,
                "kind": context.kind.value if context is not None else None,
                "group_id": context.group_id if context is not None else None,
                "resources": sorted(context.resources) if context is not None else [],
                "scheduler_strategy": self._command_scheduler.strategy_name,
                "stop_epoch": (
                    context.admitted_stop_epoch
                    if context is not None
                    else self._command_scheduler.stop_epoch
                ),
            }
        )

    async def async_connect(self) -> bool:
        """Connect to the bed."""
        _LOGGER.debug("async_connect called for %s", self._address)
        async with self._lock:
            return await self._async_connect_locked()

    def _uses_persistent_connection(self) -> bool:
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
        3. A pre-first-connect bed-type heuristic. Only ``auto``/``gen2``
           ``leggett_platt`` entries are assumed persistent here; ``okin`` and
           ``mlrm`` are not (they reconnect normally).
        """
        controller = self._controller
        if controller is not None:
            return controller.requires_persistent_connection
        if self._persistent_connection_resolved is not None:
            return self._persistent_connection_resolved
        if self._bed_type in (BED_TYPE_SLEEP_NUMBER_MCR, BED_TYPE_LEGGETT_GEN2):
            return True
        if self._bed_type == BED_TYPE_LEGGETT_PLATT:
            return self._protocol_variant in (VARIANT_AUTO, LEGGETT_VARIANT_GEN2)
        return False

    def _disconnect_after_operation_enabled(self) -> bool:
        """Return True when commands should disconnect immediately after completion."""
        return self._disconnect_after_command and not self._uses_persistent_connection()

    def _auto_reconnect_enabled(self) -> bool:
        """Return True when unexpected disconnects should schedule a reconnect timer."""
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

    def _unverified_marker_applies(self, source: str | None) -> bool:
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
        if not attempted:
            # No scope recorded: either the bond was proven (and carries
            # provenance instead) or the entry predates scoping. Unchanged.
            return True
        return bool(source) and source == attempted

    def _prepare_pairing_attempt(
        self,
        device: BLEDevice,
        pairing_details: dict[str, Any],
        source: str | None = None,
    ) -> tuple[bool, bool, bool]:
        """Resolve pairing policy and diagnostics for one connection attempt."""
        bed_requires_pairing = requires_pairing(self._bed_type, self._protocol_variant)
        bond_marker_before_attempt = self._ble_bond_established
        transient_skip_was_set = self._skip_pair_next_attempt
        os_bond_reported = bed_requires_pairing and self._device_reports_existing_bond(device)
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
        bond_marker_trusted = self._ble_bond_established and not marker_out_of_scope

        use_pairing = (
            bed_requires_pairing
            and not bond_marker_trusted
            and not self._skip_pair_next_attempt
            and self._pairing_supported is not False
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
        if not bed_requires_pairing:
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

    async def _async_cleanup_failed_connection(self) -> None:
        """Release a failed-attempt client without scheduling auto-reconnect."""
        client = self._client
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
            async with async_get_connect_lock(self.hass, self._address):
                await client.disconnect()
            _LOGGER.debug("Disconnect cleanup successful")
        except Exception as disconnect_err:
            _LOGGER.debug(
                "Error during disconnect cleanup: %s (%s)",
                disconnect_err,
                type(disconnect_err).__name__,
            )
        finally:
            self._client = None
            self._controller = None
            self._intentional_disconnect = False

    async def _async_connect_locked(  # pyright: ignore[reportGeneralTypeIssues]
        self, reset_timer: bool = True
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

        if self._client is not None and self._client.is_connected:
            if self._controller is not None:
                _LOGGER.debug("Already connected to %s, reusing connection", self._address)
                if reset_timer:
                    self._reset_disconnect_timer()
                return True
            # Connected but half-initialised. Release the orphan before making a
            # fresh attempt: establish_connection() would otherwise overwrite
            # self._client and leak this still-live link, and the
            # close_stale_connections_by_address() fallback is None on
            # non-BlueZ backends, so nothing else would ever close it.
            _LOGGER.debug(
                "Releasing half-initialised connection to %s before reconnecting",
                self._address,
            )
            await self._async_cleanup_failed_connection()

        # Routine reconnects after an intentional/idle disconnect are expected for
        # non-persistent beds and shouldn't spam the log. Only the first successful
        # connection of the entry's lifetime logs the happy path at INFO; subsequent
        # on-demand reconnects log at DEBUG (still captured with debug logging enabled).
        # Retries, warnings, and failures keep their levels regardless (see below).
        connect_log = _LOGGER.info if self._last_connected is None else _LOGGER.debug

        connect_log(
            "Initiating BLE connection to %s (max %d attempts)",
            self._address,
            self._max_retries,
        )
        overall_start = time.monotonic()
        # Track adapters that ran out of connection slots so we can try
        # alternatives on subsequent retries (issue #152).
        exhausted_adapters: set[str] = set()
        adapter_result: AdapterSelectionResult | None = None

        attempt = 0
        attempt_limit = self._max_retries
        protocol_correction_pairing_retry_reserved = False
        while attempt < attempt_limit:
            attempt_index = attempt
            attempt += 1
            attempt_number = attempt_index + 1
            attempt_start = time.monotonic()
            attempt_details = new_connection_attempt_details(
                attempt_number, self._preferred_adapter
            )
            # Track connection attempt for diagnostics (issue #168)
            self._connection_attempt_count += 1
            self._last_connection_attempt = datetime.now(UTC)

            # On retries, add a delay before attempting to give the Bluetooth stack time to reset
            if attempt_index > 0:
                base_delay = self._retry_base_delay * (2 ** (attempt_index - 1))
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
                    self._preferred_adapter,
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
                    if close_stale_connections_by_address is not None:
                        try:
                            close_result = close_stale_connections_by_address(self._address)
                            if inspect.isawaitable(close_result):
                                await close_result
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
                    # These devices expose different services/characteristics
                    # depending on bond state, so a stale cache from a previous
                    # non-paired connection would make characteristic lookups (and
                    # the post-connect bond probe) fail. This also covers the
                    # no-pair verify retry after a failed pair attempt, which must
                    # see live services to confirm the bond instead of looping.
                    #
                    # Sleep Number Climate 360 does not pair (see BEDS_REQUIRING_PAIRING)
                    # but the SleepIQ app refreshes the GATT cache on every connect, so
                    # force fresh discovery to keep parity and ensure the app-layer
                    # priming reads always see the live characteristic handles.
                    disable_cache = bed_requires_pairing or self._bed_type == BED_TYPE_SLEEP_NUMBER
                    try:
                        self._client = await establish_connection(
                            BleakClient,
                            device,
                            self._name,
                            disconnected_callback=self._on_disconnect,
                            max_attempts=1,
                            timeout=self._connection_timeout,
                            ble_device_callback=ble_device_callback,
                            pair=use_pairing and not pair_after_service_discovery,
                            use_services_cache=not disable_cache,
                        )
                        # LP Control requests the Android bond only after the
                        # unbonded GATT link has reported SERVICES_DISCOVERED.
                        # establish_connection() returns after Bleak has loaded
                        # the service collection, so pairing here preserves that
                        # proven application ordering on BlueZ as well.
                        bond_created = True
                        if pair_after_service_discovery:
                            _LOGGER.info(
                                "Connected to %s and discovered services; "
                                "creating the BLE bond now",
                                self._address,
                            )
                            bond_created = await self._async_pair_on_live_link(pairing_details)
                        # If we get here with pairing enabled, mark it as supported
                        if use_pairing and bond_created:
                            self._pairing_supported = True
                            self._mark_ble_bond_established()
                            pairing_details["adapter_pairing_supported"] = True
                            pairing_details["connection_result"] = "pairing_connection_succeeded"
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
                    )
                    and not await self._async_verify_bonded(attempt_details)
                ):
                    # _async_verify_bonded cleared the bond marker, raised the
                    # repair issue, and disconnected. Retry — the next attempt
                    # requests pair=True again (the skip flag was consumed).
                    _LOGGER.warning(
                        "Bed %s connected but the BLE link is not bonded; retrying with pairing.",
                        self._address,
                    )
                    self._connecting = False
                    self._connection_attempt_details.append(attempt_details)
                    continue

                # Some beds (Sleep Number MCR/Fuzion, Jensen) disconnect if
                # there is too much delay between the BLE connection and the
                # protocol handshake.  For those bed types we defer the
                # Device Information Service reads until after the
                # notification channel and handshake are established.
                _defer_device_info = self._bed_type in {
                    BED_TYPE_SLEEP_NUMBER_MCR,
                    BED_TYPE_SLEEP_NUMBER,
                    BED_TYPE_JENSEN,
                }

                ble_manufacturer: str | None = None
                ble_model: str | None = None

                if not _defer_device_info:
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

                # If remote is set to auto, infer Richmat remote code from BLE name at runtime.
                # This preserves compatibility for existing entries created before auto-code storage.
                richmat_remote = self._richmat_remote
                if self._bed_type == BED_TYPE_RICHMAT and richmat_remote == RICHMAT_REMOTE_AUTO:
                    detected_remote = detect_richmat_remote_from_name(device.name)
                    if detected_remote:
                        richmat_remote = detected_remote
                        _LOGGER.info(
                            "Auto-detected Richmat remote code '%s' from BLE name '%s'",
                            detected_remote,
                            device.name,
                        )
                if self._bed_type == BED_TYPE_RICHMAT:
                    richmat_remote = resolve_richmat_remote_code(
                        richmat_remote,
                        entry_title=self.entry.title,
                        configured_name=self._name,
                        device_name=device.name,
                    )

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

                stored_capabilities = self.entry.data.get("capabilities")
                stored_capability_snapshot: Mapping[str, Any] | None = None
                if isinstance(stored_capabilities, dict):
                    namespace = (
                        "octo"
                        if self._bed_type == BED_TYPE_OCTO
                        else "linak"
                        if self._bed_type == BED_TYPE_LINAK
                        else None
                    )
                    candidate = stored_capabilities.get(namespace) if namespace else None
                    if isinstance(candidate, Mapping):
                        stored_capability_snapshot = candidate

                # Create the controller
                _LOGGER.debug("Creating %s controller...", self._bed_type)
                self._controller = await create_controller(
                    coordinator=self,
                    bed_type=self._bed_type,
                    protocol_variant=self._protocol_variant,
                    client=self._client,
                    device_name=device.name,
                    octo_pin=self._octo_pin,
                    richmat_remote=richmat_remote,
                    jensen_pin=self._jensen_pin,
                    cb24_bed_selection=self._cb24_bed_selection,
                    ble_manufacturer=ble_manufacturer,
                    ble_model=ble_model,
                    manufacturer_data=manufacturer_data,
                    capability_snapshot=stored_capability_snapshot,
                )
                discovery_result = cast(Any, self._controller).async_discover_capabilities()
                if inspect.isawaitable(discovery_result):
                    await discovery_result
                self._controller_state_refresh_retry_count = 0
                self._controller_state_refresh_completed = False
                # Position values retained across disconnects are last-known
                # state only. Give this controller session its own generation so
                # reconnect hydration and seeks can distinguish fresh feedback
                # from cached values.
                self._position_connection_generation += 1
                # Remember the resolved persistence so reconnect/idle decisions are
                # correct even after _on_disconnect clears the controller.
                self._persistent_connection_resolved = (
                    self._controller.requires_persistent_connection
                )
                _LOGGER.debug("Controller created successfully")

                if self._bed_type == BED_TYPE_SLEEP_NUMBER_MCR:
                    # Older BAM/MCR firmware is sensitive to idle time between
                    # the BLE connect, notify subscribe, and init/query frames.
                    await self.async_start_notify()
                    if hasattr(self._controller, "query_config"):
                        await cast(Any, self._controller).query_config()

                if (
                    self._bed_type == BED_TYPE_VIBRADORM
                    and not self._disable_angle_sensing
                    and not self._controller.supports_position_feedback
                ):
                    self._disable_angle_sensing = True
                    _LOGGER.info(
                        "Disabling angle sensing for %s: BLE model %s uses the OEM app's "
                        "write-only VMAT control path without position feedback",
                        self._address,
                        self._ble_model or self._get_model(),
                    )

                if self._bed_type == BED_TYPE_LIMOSS and hasattr(
                    self._controller, "reset_max_raw_estimate"
                ):
                    # Reset Limoss normalization state on each connection.
                    cast(Any, self._controller).reset_max_raw_estimate()

                # Start position notifications (no-op if angle sensing disabled).
                # Sleep Number MCR performs its notify+init startup earlier.
                if self._bed_type != BED_TYPE_SLEEP_NUMBER_MCR:
                    await self.async_start_notify()

                # Notification startup may finish deferred capability discovery
                # after the BLE authentication window, so schedule from the final
                # resolved controller state.
                self._refresh_passive_position_reconciliation_schedule()

                if self._bed_type == BED_TYPE_LINAK:
                    self._backfill_linak_snapshot()

                # For Octo beds: discover features and handle PIN if needed
                if self._bed_type == BED_TYPE_OCTO:
                    # Discover features to detect PIN requirement
                    if hasattr(self._controller, "discover_features"):
                        await cast(Any, self._controller).discover_features()
                    # Persist this paired side's freshly-discovered capabilities so
                    # the OFFLINE side / a reload mints correct entities (no-op for
                    # a single bed or if nothing was discovered).
                    self._backfill_octo_snapshot()
                    # Send initial PIN and start keep-alive if bed requires it
                    if hasattr(self._controller, "send_pin"):
                        await cast(Any, self._controller).send_pin()
                        await cast(Any, self._controller).start_keepalive()
                    # A PIN-locked receiver accepts lights but ignores motors, so
                    # surface the missing PIN instead of looking simply broken.
                    if hasattr(self._controller, "pin_locked_without_pin"):
                        update_octo_pin_required_issue(
                            self.hass,
                            self._address,
                            self._name,
                            cast(Any, self._controller).pin_locked_without_pin,
                        )

                # Beds with connect-time feature discovery/state hydration.
                if self._bed_type in {BED_TYPE_JENSEN, BED_TYPE_SLEEP_NUMBER} and hasattr(
                    self._controller, "query_config"
                ):
                    await cast(Any, self._controller).query_config()

                # Read deferred BLE Device Information now that the
                # notification channel and protocol handshake are done.
                if _defer_device_info and self._client is not None and self._client.is_connected:
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
                    self._bed_type != BED_TYPE_SLEEP_NUMBER_MCR
                    and self._should_refresh_readable_light_state(force=True)
                ):
                    await self._async_refresh_readable_light_state()

                if self._client is None or not self._client.is_connected:
                    _LOGGER.warning(
                        "Connection to %s dropped during controller startup",
                        self._address,
                    )
                    self._connecting = False
                    self._last_connection_error = "Connection dropped during controller startup"
                    self._last_connection_error_type = ConnectionError.__name__
                    # A failed (re)connect is not an intentional/idle disconnect;
                    # clear the prior reason so the connectivity sensor doesn't keep
                    # reporting "idle" after the attempt failed (issue #385 review).
                    self._last_disconnect_reason = "connect_failed"
                    attempt_details["total_elapsed_seconds"] = round(
                        time.monotonic() - attempt_start, 3
                    )
                    attempt_details["result"] = "failed"
                    attempt_details["error"] = self._last_connection_error
                    attempt_details["error_type"] = self._last_connection_error_type
                    attempt_details["error_category"] = "CONNECTION DROPPED"
                    self._client = None
                    self._controller = None
                    self._notify_connection_state_change(False)
                    self._connection_attempt_details.append(attempt_details)
                    continue

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

                await self.async_clear_obsolete_pairing_state()

                return True

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
                        await self._async_handle_ble_authentication_error(err, holding_lock=True)
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
                        # remaining attempts; the repair issue the handler
                        # raised tells the user to re-pair.
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
                if isinstance(err, TimeoutError) or "timeout" in err_str:
                    error_category = "CONNECTION TIMEOUT"
                elif "refused" in err_str or "rejected" in err_str:
                    error_category = "CONNECTION REFUSED (another device may be connected)"
                else:
                    error_category = "BLE ERROR"
                attempt_details["error_category"] = error_category

                # Detect connection slot exhaustion and exclude the adapter
                # on subsequent retries so we try an alternative (issue #152).
                if "connection slot" in err_str and adapter_result is not None:
                    failed_source = adapter_result.source
                    if failed_source:
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
            self._max_retries,
            total_elapsed,
        )
        self._schedule_pending_capability_reload()
        return False

    def _on_disconnect(self, client: BleakClient) -> None:
        """Handle disconnection callback."""
        # Ignore stale disconnect callbacks from old clients
        if client is not self._client:
            _LOGGER.debug(
                "Ignoring stale disconnect callback from old client for %s",
                self._address,
            )
            return

        # If we're in the middle of connecting, this is likely bleak's internal retry
        # for le-connection-abort-by-local - don't log warnings or clear references
        if self._connecting:
            _LOGGER.debug(
                "Disconnect callback during connection establishment for %s (bleak internal retry)",
                self._address,
            )
            return

        # Store disconnect timestamp for binary sensor
        self._last_disconnected = datetime.now(UTC)

        # Track disconnect reason for diagnostics (issue #168)
        # If intentional, reason is set by async_disconnect() or _async_idle_disconnect()
        if not self._intentional_disconnect:
            self._last_disconnect_reason = "unexpected"

        # Stop keepalive task before clearing controller to prevent task leak
        # Capture controller reference before clearing to avoid race condition
        controller = self._controller
        if controller is not None and hasattr(controller, "stop_keepalive"):
            self._stop_keepalive_task = self.entry.async_create_background_task(
                self.hass,
                cast(Any, controller).stop_keepalive(),
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

    def _schedule_auto_reconnect(self) -> None:
        """Launch the auto-reconnect task once the reconnect timer fires.

        The task is tied to the config entry so it is tracked by HA and
        cancelled automatically if the entry unloads before it finishes.
        """
        self.entry.async_create_background_task(
            self.hass,
            self._async_auto_reconnect(),
            name=f"adjustable_bed_auto_reconnect_{self._address}",
        )

    async def _async_auto_reconnect(self) -> None:
        """Attempt automatic reconnection after unexpected disconnect."""
        # Timer has fired, clear the reference
        self._reconnect_timer = None

        # Don't reconnect if we're already connected or connecting
        if self._connecting or (self._client is not None and self._client.is_connected):
            _LOGGER.debug("Skipping auto-reconnect: already connected or connecting")
            return

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

    async def async_read_initial_positions(self) -> None:
        """Read positions to initialize sensors.

        Called after a connection is established to populate position sensors
        with actual values instead of leaving them 'unknown'. Runs in background
        with short timeouts so it never blocks startup.

        Uses the command lock to prevent concurrent GATT operations with
        commands that may start immediately after connection.

        Each attempt has its own timeout, while an overall deadline keeps the
        retry window from reserving a single-connection bed indefinitely.
        """
        if self._disable_angle_sensing:
            _LOGGER.debug("Skipping initial position read (angle sensing disabled)")
            return

        expected_axes = self._expected_initial_position_axes()
        if not expected_axes:
            _LOGGER.debug("Skipping initial position read (no expected axes)")
            return

        if self._position_hydration_running:
            _LOGGER.debug("Initial position read already running for %s - skipping", self._address)
            return

        self._position_hydration_running = True
        current_task = asyncio.current_task()
        if current_task is not None:
            # Setup and reconnect paths can both request the initial read. Keep
            # whichever task actually claimed the operation discoverable so
            # diagnostics and shutdown can cancel that exact task.
            self._position_hydration_task = current_task
        try:
            # Keep the link alive for the retry window, but only own the command
            # lock during a GATT attempt so user commands and STOP can run during
            # the backoff sleeps.
            self._cancel_disconnect_timer()
            try:
                _LOGGER.debug("Reading initial positions for %s", self._address)
                try:
                    async with asyncio.timeout(_INITIAL_POSITION_READ_TOTAL_TIMEOUT):
                        for attempt in range(1, _INITIAL_POSITION_READ_MAX_ATTEMPTS + 1):
                            # A command that established this connection may
                            # have refreshed every axis while hydration waited
                            # for the command lock, or deliberately released
                            # the link. Avoid entering the query path, which
                            # would reconnect after disconnect-after-command.
                            if (
                                self._client is None
                                or not self._client.is_connected
                                or all(self._position_is_current(axis) for axis in expected_axes)
                            ):
                                return

                            def _initial_position_read_needed() -> bool:
                                return (
                                    not self._position_hydration_pause_count
                                    and self._client is not None
                                    and self._client.is_connected
                                    and not all(
                                        self._position_is_current(axis) for axis in expected_axes
                                    )
                                )

                            async def _read_initial_positions(
                                controller: BedController,
                            ) -> None:
                                # Connection preparation can produce notifications,
                                # so recheck after it as well as before reconnecting.
                                if not _initial_position_read_needed():
                                    return
                                await controller.prepare_for_position_read()
                                await self._async_read_positions()

                            try:
                                async with asyncio.timeout(_INITIAL_POSITION_READ_TIMEOUT):
                                    await self.async_execute_controller_query(
                                        _read_initial_positions,
                                        skip_disconnect=True,
                                        preemptible=True,
                                        run_if=_initial_position_read_needed,
                                    )
                            except TimeoutError:
                                _LOGGER.debug(
                                    "Initial position read attempt %d/%d for %s timed out",
                                    attempt,
                                    _INITIAL_POSITION_READ_MAX_ATTEMPTS,
                                    self._address,
                                )
                            except asyncio.CancelledError:
                                raise
                            except Exception as err:
                                _LOGGER.debug(
                                    "Initial position read attempt %d/%d for %s failed: %s",
                                    attempt,
                                    _INITIAL_POSITION_READ_MAX_ATTEMPTS,
                                    self._address,
                                    err,
                                )
                            finally:
                                # Serialized queries restart the idle timer.
                                # Hydration owns the link through its bounded
                                # retry window, including the backoff sleeps.
                                self._cancel_disconnect_timer()

                            # Checked even after a failed attempt: a partial read
                            # (or a notification that landed meanwhile) may
                            # already be enough.
                            received_axes = {
                                axis for axis in expected_axes if self._position_is_current(axis)
                            }
                            if received_axes >= expected_axes:
                                _LOGGER.info(
                                    "Initial positions read for %s: %s",
                                    self._address,
                                    {k: f"{v}°" for k, v in self._position_data.items()},
                                )
                                return

                            if attempt >= _INITIAL_POSITION_READ_MAX_ATTEMPTS:
                                break

                            _LOGGER.debug(
                                "Initial position read for %s missing axes %s after "
                                "attempt %d/%d; retrying in %.1fs",
                                self._address,
                                sorted(expected_axes - received_axes),
                                attempt,
                                _INITIAL_POSITION_READ_MAX_ATTEMPTS,
                                _INITIAL_POSITION_READ_RETRY_DELAY,
                            )
                            await asyncio.sleep(_INITIAL_POSITION_READ_RETRY_DELAY)
                except TimeoutError:
                    _LOGGER.debug(
                        "Initial position read retry window for %s timed out after %.1fs",
                        self._address,
                        _INITIAL_POSITION_READ_TOTAL_TIMEOUT,
                    )

                if self._position_data:
                    _LOGGER.info(
                        "Initial position read for %s remained partial: %s",
                        self._address,
                        {k: f"{v}°" for k, v in self._position_data.items()},
                    )
                else:
                    _LOGGER.debug(
                        "Initial position read for %s produced no data - retrying on the "
                        "next connect",
                        self._address,
                    )
            finally:
                if self._client is not None and self._client.is_connected:
                    self._reset_disconnect_timer()
        finally:
            self._position_hydration_running = False
            if self._position_hydration_task is current_task:
                self._position_hydration_task = None

    def _schedule_position_hydration(self) -> None:
        """Refresh position axes in the background after a connect.

        Entry setup schedules the first read, but a bed that was busy, asleep or
        unreachable then would otherwise sit at "unknown" until the user moved
        it: outside a movement command nothing reads positions. Every new BLE
        session also refreshes last-known values in case another controller
        moved the bed while Home Assistant had released the link.
        """
        if self._disable_angle_sensing or self._position_hydration_pause_count:
            return

        expected_axes = self._expected_initial_position_axes()
        if not expected_axes or all(self._position_is_current(axis) for axis in expected_axes):
            return

        task = self._position_hydration_task
        if task is not None and not task.done():
            return

        self._position_hydration_task = self.entry.async_create_background_task(
            self.hass,
            self.async_read_initial_positions(),
            name=f"adjustable_bed_position_hydration_{self._address}",
        )

    def _expected_initial_position_axes(self) -> set[str]:
        """Return the logical position axes that startup hydration should populate."""
        if not bed_type_has_position_feedback(self._bed_type, self._protocol_variant):
            return set()
        controller = self._controller
        if controller is None:
            return set()
        return {spec.position_key for spec in controller.position_number_specs}

    def _position_is_current(self, position: str) -> bool:
        """Return whether a cached position was observed on the active BLE session."""
        if position not in self._position_data:
            return False
        # Unit tests and capability-only coordinators can operate without ever
        # establishing a BLE generation. Production connections start at one.
        if self._position_connection_generation == 0:
            return True
        return self._position_data_generation.get(position) == self._position_connection_generation

    async def _async_cancel_position_hydration(self) -> None:
        """Cancel and await the active position hydration task."""
        task = self._position_hydration_task
        try:
            if task is not None and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    current_task = asyncio.current_task()
                    if current_task is not None and current_task.cancelling():
                        raise
        finally:
            if self._position_hydration_task is task:
                self._position_hydration_task = None

    async def async_pause_position_hydration(self) -> None:
        """Suppress background position reads during external BLE diagnostics."""
        self._position_hydration_pause_count += 1
        await self._async_cancel_position_hydration()

    def resume_position_hydration(self) -> None:
        """Resume position hydration after an external BLE diagnostic operation."""
        if self._position_hydration_pause_count == 0:
            return
        self._position_hydration_pause_count -= 1
        if self._position_hydration_pause_count:
            return
        if self._client is not None and self._client.is_connected:
            self._schedule_position_hydration()

    def _resolve_passive_position_reconciliation_interval(
        self, requested_interval_s: float | None
    ) -> float | None:
        """Return the safe passive reconciliation interval for this entry."""
        if self._disable_angle_sensing:
            return None
        if not self._passive_position_reconciliation_enabled:
            return None
        if requested_interval_s is None or requested_interval_s <= 0:
            return None

        minimum_interval_s = float(self._idle_disconnect_seconds) + (
            _PASSIVE_POSITION_RECONCILIATION_IDLE_MARGIN
        )
        return max(float(requested_interval_s), minimum_interval_s)

    def _refresh_passive_position_reconciliation_schedule(self) -> None:
        """Start or stop passive position reconciliation based on controller support."""
        requested_interval_s: float | None = None
        if self._controller is not None:
            requested_interval_s = self._controller.passive_position_reconciliation_interval

        interval_s = self._resolve_passive_position_reconciliation_interval(requested_interval_s)
        current_task = self._passive_position_reconciliation_task
        if (
            interval_s == self._passive_position_reconciliation_interval_s
            and current_task is not None
            and not current_task.done()
        ):
            return

        self._cancel_passive_position_reconciliation_task()
        self._passive_position_reconciliation_interval_s = interval_s
        if interval_s is None:
            return

        _LOGGER.debug(
            "Starting passive position reconciliation for %s every %.0fs",
            self._address,
            interval_s,
        )
        self._passive_position_reconciliation_task = self.hass.async_create_background_task(
            self._async_passive_position_reconciliation_loop(),
            name=f"adjustable_bed.passive_position_reconciliation[{self._address}]",
        )

    def _cancel_passive_position_reconciliation_task(self) -> None:
        """Cancel the passive position reconciliation loop."""
        task = self._passive_position_reconciliation_task
        if task is not None:
            task.cancel()
            self._passive_position_reconciliation_task = None

    async def _async_passive_position_reconciliation_loop(self) -> None:
        """Periodically reconcile positions so external remote moves do not stay stale."""
        try:
            while True:
                interval_s = self._passive_position_reconciliation_interval_s
                if interval_s is None:
                    return

                await asyncio.sleep(interval_s)
                await self.async_reconcile_positions()
        except asyncio.CancelledError:
            return

    async def async_reconcile_positions(self) -> None:
        """Perform a low-frequency passive position refresh when the coordinator is idle."""
        if self._disable_angle_sensing or self._passive_position_reconciliation_interval_s is None:
            return

        if self._connecting or self._command_lock.locked():
            _LOGGER.debug(
                "Skipping passive position reconciliation for %s because the coordinator is busy",
                self._address,
            )
            return

        try:
            _LOGGER.debug("Running passive position reconciliation for %s", self._address)
            await self.async_execute_controller_query(
                self._async_execute_position_reconciliation_query,
                cancel_running=False,
            )
            _LOGGER.debug("Passive position reconciliation completed for %s", self._address)
        except asyncio.CancelledError:
            raise
        except Exception as err:
            _LOGGER.debug(
                "Passive position reconciliation failed for %s: %s",
                self._address,
                err,
            )

    async def _async_execute_position_reconciliation_query(self, controller: BedController) -> None:
        """Run a serialized passive position reconciliation read."""
        await controller.prepare_for_position_read()
        await controller.read_positions(self._motor_count)

    async def async_shutdown(self) -> None:
        """Stop background tasks and disconnect the coordinator."""
        self._shutting_down = True
        self._pending_capability_reload = False
        try:
            await self._async_cancel_position_hydration()
        finally:
            self._cancel_passive_position_reconciliation_task()
            try:
                await self._command_scheduler.async_shutdown()
            finally:
                await self.async_disconnect()

    async def async_disconnect(
        self,
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

    @contextlib.asynccontextmanager
    async def async_transport_operation(self, operation: str) -> AsyncIterator[None]:
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
                # close_stale_connections_by_address is None on non-BlueZ
                # backends.
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

    async def _async_force_close(self, client: BleakClient | None) -> None:
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
        if self._reconnect_timer is not None:
            self._reconnect_timer.cancel()
            self._reconnect_timer = None

    async def _async_disconnect_locked(self, reason: str = "intentional") -> bool:
        """Disconnect from the bed. The caller MUST already hold ``self._lock``.

        Used by the bond-verification path, which runs inside
        ``_async_connect_locked`` (lock already held) and would otherwise
        deadlock on the public ``async_disconnect`` re-acquiring the lock.
        """
        self._cancel_disconnect_timer()
        self._cancel_controller_state_refresh_retry()
        if self._controller_state_refresh_task is not None:
            self._controller_state_refresh_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._controller_state_refresh_task
            self._controller_state_refresh_task = None
        # Cancel any pending reconnect timer
        if self._reconnect_timer is not None:
            self._reconnect_timer.cancel()
            self._reconnect_timer = None
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
            disconnect_failed = False
            try:
                # Stop keep-alive and notifications before disconnecting
                if self._controller is not None:
                    # Stop Octo keep-alive if running
                    if hasattr(self._controller, "stop_keepalive"):
                        try:
                            # Cast to Any to avoid mypy error about BedController not having stop_keepalive
                            await cast(Any, self._controller).stop_keepalive()
                        except Exception as err:
                            _LOGGER.debug("Error stopping keep-alive: %s", err)
                    try:
                        await self._controller.stop_notify()
                    except Exception as err:
                        _LOGGER.debug("Error stopping notifications: %s", err)
                await client.disconnect()
                _LOGGER.debug("Successfully disconnected from %s", self._address)
            except BleakError as err:
                disconnect_failed = True
                _LOGGER.debug("Error during disconnect from %s: %s", self._address, err)
            finally:
                self._intentional_disconnect = False
            # Bleak can raise while the OS link remains active. Keep the live
            # client/controller instead of reporting a logical disconnect: the
            # paired sequential guard must know that opening the other side
            # could create two physical links.
            if disconnect_failed and client.is_connected:
                self._client = client
                _LOGGER.warning("Disconnect from %s did not release the BLE link", self._address)
                return False
            self._client = None
            self._controller = None
            # Update disconnect timestamp and notify state change (don't rely on
            # _on_disconnect, which may not fire after a clean disconnect).
            self._last_disconnected = datetime.now(UTC)
            self._notify_connection_state_change(False)
        self._schedule_pending_capability_reload()
        return True

    def _reset_disconnect_timer(self) -> None:
        """Reset the disconnect timer."""
        if self._uses_persistent_connection():
            self._cancel_disconnect_timer()
            _LOGGER.debug(
                "Skipping idle disconnect timer for persistent connection on %s",
                self._address,
            )
            return

        self._cancel_disconnect_timer()
        _LOGGER.debug(
            "Setting idle disconnect timer for %s (%d seconds)",
            self._address,
            self._idle_disconnect_seconds,
        )
        self._disconnect_timer = self.hass.loop.call_later(
            self._idle_disconnect_seconds,
            self._schedule_idle_disconnect,
        )

    def _schedule_idle_disconnect(self) -> None:
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

    def _cancel_disconnect_timer(self) -> None:
        """Cancel the disconnect timer."""
        if self._disconnect_timer is not None:
            _LOGGER.debug("Cancelling idle disconnect timer for %s", self._address)
            self._disconnect_timer.cancel()
            self._disconnect_timer = None

    def pause_disconnect_timer(self) -> None:
        """Pause the disconnect timer (for external use like diagnostics).

        Call resume_disconnect_timer() when done to restart the timer.
        """
        self._cancel_disconnect_timer()
        _LOGGER.debug("Disconnect timer paused for %s", self._address)

    def resume_disconnect_timer(self) -> None:
        """Resume the disconnect timer after pausing.

        This resets the timer, giving a full idle timeout from now.
        """
        if self._client is not None and self._client.is_connected:
            self._reset_disconnect_timer()
            _LOGGER.debug("Disconnect timer resumed for %s", self._address)

    async def _async_idle_disconnect(self) -> None:
        """Disconnect after idle timeout."""
        # Expected for non-persistent beds: we drop the link so the physical remote
        # can take over, and reconnect on demand on the next command. Logged at DEBUG
        # to avoid spamming the log during normal use.
        _LOGGER.debug(
            "Idle timeout reached (%d seconds), disconnecting from %s",
            self._idle_disconnect_seconds,
            self._address,
        )
        async with self._command_lock:
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

    async def async_ensure_connected(self, reset_timer: bool = True) -> bool:
        """Ensure we are connected to the bed."""
        async with self._lock:
            if self._client is not None and self._client.is_connected:
                _LOGGER.debug("Connection check: already connected to %s", self._address)
                if reset_timer:
                    self._reset_disconnect_timer()
                return True
            _LOGGER.debug("Connection check: reconnecting to %s", self._address)
            return await self._async_connect_locked(reset_timer=reset_timer)

    async def _async_refresh_controller_auth(self) -> None:
        """Refresh protocol auth for controllers that require re-authentication."""
        if self._controller is None:
            return

        # Jensen can require a fresh PIN unlock command even on reused BLE connections.
        if self._bed_type == BED_TYPE_JENSEN and hasattr(self._controller, "send_pin"):
            _LOGGER.debug("Refreshing Jensen PIN unlock before command on %s", self._address)
            await cast(Any, self._controller).send_pin()

    async def async_write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 100,
        cancel_running: bool = True,
    ) -> None:
        """Write a command to the bed.

        Motor commands cancel any running command for immediate response.
        """
        if cancel_running:
            # Cancel any running command immediately
            self.request_command_cancel()

        # Capture cancel count at entry to detect if we get cancelled while waiting
        entry_cancel_count = self._cancel_counter

        async with self._command_lock:
            # Cancel disconnect timer while command is in progress to prevent mid-command disconnect
            self._cancel_disconnect_timer()

            # Check if we were cancelled while waiting for the lock
            if self._cancel_counter > entry_cancel_count:
                _LOGGER.debug("Command %s cancelled while waiting for lock", command.hex())
                # Reset disconnect timer since we're bailing out
                if self._client is not None and self._client.is_connected:
                    self._reset_disconnect_timer()
                return

            try:
                # Clear cancel signal for this command
                self._cancel_command.clear()

                _LOGGER.debug(
                    "async_write_command: %s (repeat: %d, delay: %dms)",
                    command.hex(),
                    repeat_count,
                    repeat_delay_ms,
                )
                if not await self.async_ensure_connected(reset_timer=False):
                    _LOGGER.error("Cannot write command: not connected to bed")
                    raise ConnectionError("Not connected to bed")

                if self._controller is None:
                    _LOGGER.error("Cannot write command: no controller available")
                    raise RuntimeError("No controller available")

                await self._async_refresh_controller_auth()

                # Start position polling during movement if angle sensing enabled
                poll_stop: asyncio.Event | None = None
                poll_task: asyncio.Task[None] | None = None
                if (
                    not self._disable_angle_sensing
                    and self._controller.allow_position_polling_during_commands
                ):
                    poll_stop = asyncio.Event()
                    poll_task = asyncio.create_task(
                        self._async_poll_positions_during_movement(poll_stop)
                    )

                try:
                    await self._controller.write_command(
                        command, repeat_count, repeat_delay_ms, self._cancel_command
                    )
                finally:
                    # Stop polling
                    if poll_stop is not None:
                        poll_stop.set()
                    if poll_task is not None:
                        poll_task.cancel()
                        with contextlib.suppress(asyncio.CancelledError):
                            await poll_task

                # Final position read after command
                if not self._disable_angle_sensing and not self._cancel_command.is_set():
                    if self._position_mode == POSITION_MODE_ACCURACY:
                        # Accuracy mode: wait for read to complete
                        await self._async_read_positions()
                    else:
                        # Speed mode: fire-and-forget with lock to prevent concurrent GATT ops
                        self._start_background_position_read()
            finally:
                if self._client is not None and self._client.is_connected:
                    self._reset_disconnect_timer()

    def request_command_cancel(
        self,
        resource: str | None = None,
        *,
        resources: Collection[str] | None = None,
    ) -> None:
        """Signal the running command to stop ASAP, without sending a STOP write.

        Lets the paired parent preempt an in-flight child command before taking
        the pair lock, so a cancel_running movement (or STOP) isn't queued behind
        the BLE pulse window.
        """
        if resource is not None and resources is not None:
            raise ValueError("Pass resource or resources, not both")
        command_scope = (
            command_resources(*resources)
            if resources is not None
            else command_resources(resource or "*")
        )
        self._cancel_counter += 1
        self._cancel_command.set()
        self._command_scheduler.request_cancel(command_scope)

    async def async_stop_command(self) -> None:
        """Immediately stop any running command and send stop to bed."""
        _LOGGER.info("Stop requested - cancelling current command")

        # Invalidate active and queued movement before awaiting the wire lane.
        # The epoch check prevents a queued command from starting after STOP.
        self._cancel_counter += 1
        self._cancel_command.set()

        async def stop_operation(_context: CommandContext) -> None:
            await self._async_send_stop_command()

        stop_task = self._command_scheduler.admit_stop(stop_operation, ALL_COMMAND_RESOURCES)

        try:
            await asyncio.shield(stop_task)
        except asyncio.CancelledError:
            # Once accepted, a safety STOP outlives cancellation of the service
            # caller or config-entry task. Settle it before propagating cancellation.
            try:
                await stop_task
            except Exception:
                _LOGGER.exception("STOP failed after its caller was cancelled")
            raise

    async def _async_send_stop_command(self) -> None:
        """Send STOP while owning the legacy wire and connection lifecycle lane."""
        # STOP remains outside the ordinary scheduler lane so it can preempt it,
        # then waits for any cancelled controller cleanup to release the wire lock.
        async with self._command_lock:
            self._cancel_disconnect_timer()
            try:
                if not await self.async_ensure_connected(reset_timer=False):
                    _LOGGER.error("Cannot send stop: not connected to bed")
                    raise ConnectionError("Not connected to bed")

                if self._controller is None:
                    _LOGGER.error("Cannot send stop: no controller available")
                    raise RuntimeError("No controller available")

                try:
                    await self._async_refresh_controller_auth()
                except BleakError as err:
                    _LOGGER.warning(
                        "Auth refresh failed before stop command on %s: %s",
                        self._address,
                        err,
                    )
                except Exception as err:
                    _LOGGER.warning(
                        "Unexpected auth refresh failure before stop command on %s: %s",
                        self._address,
                        err,
                        exc_info=True,
                    )

                # Use controller's stop_all method which knows the correct protocol
                await self._controller.stop_all()
                _LOGGER.info("Stop command sent")
            finally:
                if self._client is not None and self._client.is_connected:
                    # Disconnect immediately if configured to do so
                    if self._disconnect_after_operation_enabled():
                        _LOGGER.debug(
                            "Disconnecting after stop command (disconnect_after_command=True) for %s",
                            self._address,
                        )
                        await self.async_disconnect()
                    else:
                        # Otherwise, reset the idle disconnect timer
                        self._reset_disconnect_timer()

    async def _async_prepare_controller_operation(self, operation_name: str) -> BedController:
        """Ensure the controller is connected and authenticated before use."""
        if not await self.async_ensure_connected(reset_timer=False):
            _LOGGER.error("Cannot execute %s: not connected to bed", operation_name)
            raise ConnectionError("Not connected to bed")

        controller = self._controller
        if controller is None:
            _LOGGER.error("Cannot execute %s: no controller available", operation_name)
            raise RuntimeError("No controller available")

        await self._async_refresh_controller_auth()
        return controller

    async def _async_finish_controller_operation(
        self,
        *,
        entry_cancel_count: int,
        cancel_event: asyncio.Event,
        scheduler_managed: bool,
        skip_disconnect: bool,
        operation_name: str,
    ) -> None:
        """Handle disconnect timer reset or disconnect after an operation completes."""
        if self._bed_type == BED_TYPE_LINAK and not self._command_scheduler.has_pending:
            # A cold Linak link can defer its actuator mask and timer channel
            # until the first command. Persist the now-resolved snapshot after
            # that command so the entry reload reconciles its capability-gated
            # entities without interrupting a queued operation.
            self._backfill_linak_snapshot()

        if self._client is None or not self._client.is_connected:
            return

        command_preempted = (
            cancel_event.is_set()
            or (scheduler_managed and self._command_scheduler.has_pending)
            or (
                scheduler_managed
                and (context := current_command_context()) is not None
                and context.defer_disconnect
            )
            or (not scheduler_managed and self._cancel_counter > entry_cancel_count)
        )
        if (
            self._disconnect_after_operation_enabled()
            and not skip_disconnect
            and not command_preempted
        ):
            _LOGGER.debug(
                "Disconnecting after %s (disconnect_after_command=True) for %s",
                operation_name,
                self._address,
            )
            await self.async_disconnect()
            return

        if command_preempted:
            _LOGGER.debug(
                "Skipping disconnect for %s: newer command is pending",
                self._address,
            )
        self._reset_disconnect_timer()

    async def _async_wait_for_controller_operation(
        self,
        operation_task: asyncio.Task[T],
        *,
        cancel_event: asyncio.Event,
        operation_name: str,
        raise_on_cancel: bool,
    ) -> T | None:
        """Wait for a controller operation or cancel it when preempted."""
        cancel_wait_task = asyncio.create_task(cancel_event.wait())
        try:
            done, pending = await asyncio.wait(
                {operation_task, cancel_wait_task},
                return_when=asyncio.FIRST_COMPLETED,
            )

            for task in pending:
                task.cancel()
            for task in pending:
                with contextlib.suppress(asyncio.CancelledError):
                    await task

            if cancel_wait_task in done:
                _LOGGER.debug("Controller %s cancelled during execution", operation_name)
                if not operation_task.done():
                    operation_task.cancel()
                try:
                    await operation_task
                except asyncio.CancelledError:
                    pass
                except Exception as err:
                    _LOGGER.debug(
                        "Controller %s raised while cancelling: %s",
                        operation_name,
                        err,
                    )
                if raise_on_cancel:
                    raise asyncio.CancelledError
                return None

            return operation_task.result()
        finally:
            for task in (operation_task, cancel_wait_task):
                if task.done():
                    continue
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task

    async def _async_execute_controller_operation(
        self,
        operation_fn: Callable[[BedController], Coroutine[Any, Any, T]],
        *,
        cancel_running: bool,
        skip_disconnect: bool,
        raise_on_lock_cancel: bool,
        preemptible: bool,
        enable_position_polling: bool,
        read_positions_after_operation: bool,
        operation_name: str,
        run_if: Callable[[], bool] | None = None,
    ) -> T | None:
        """Execute a controller operation with shared locking and connection handling."""
        if cancel_running:
            self._cancel_counter += 1
            self._cancel_command.set()

        entry_cancel_count = self._cancel_counter
        command_context = current_command_context()
        scheduler_managed = bool(
            command_context is not None
            and command_context.scheduler_token is self._command_scheduler.token
        )
        legacy_exclusive = bool(
            scheduler_managed and command_context is not None and "*" in command_context.resources
        )
        cancel_event = self.cancel_command

        async with self._command_lock:
            self._cancel_disconnect_timer()

            cancelled_while_waiting = (
                cancel_event.is_set()
                or (legacy_exclusive and self._cancel_counter > entry_cancel_count)
                if scheduler_managed
                else self._cancel_counter > entry_cancel_count
            )
            if preemptible and cancelled_while_waiting:
                _LOGGER.debug("Controller %s cancelled while waiting for lock", operation_name)
                if self._client is not None and self._client.is_connected:
                    self._reset_disconnect_timer()
                if raise_on_lock_cancel:
                    raise asyncio.CancelledError
                return None

            try:
                cancel_event.clear()
                if run_if is not None and not run_if():
                    _LOGGER.debug(
                        "Skipping controller %s: operation is no longer needed",
                        operation_name,
                    )
                    return None
                controller = await self._async_prepare_controller_operation(operation_name)
                cancelled_during_preparation = cancel_event.is_set() or (
                    (not scheduler_managed or legacy_exclusive)
                    and self._cancel_counter > entry_cancel_count
                )
                if preemptible and cancelled_during_preparation:
                    _LOGGER.debug("Controller %s cancelled during preparation", operation_name)
                    if raise_on_lock_cancel:
                        raise asyncio.CancelledError
                    return None
                self._active_operation_name = operation_name
                self._last_protocol_operation_start = datetime.now(UTC)

                poll_stop: asyncio.Event | None = None
                poll_task: asyncio.Task[None] | None = None
                if (
                    enable_position_polling
                    and not self._disable_angle_sensing
                    and controller.allow_position_polling_during_commands
                ):
                    poll_stop = asyncio.Event()
                    poll_task = asyncio.create_task(
                        self._async_poll_positions_during_movement(poll_stop)
                    )

                try:
                    operation_task = asyncio.create_task(operation_fn(controller))
                    if preemptible:
                        result = await self._async_wait_for_controller_operation(
                            operation_task,
                            cancel_event=cancel_event,
                            operation_name=operation_name,
                            raise_on_cancel=raise_on_lock_cancel,
                        )
                    else:
                        result = await operation_task
                finally:
                    self._last_protocol_operation_end = datetime.now(UTC)
                    self._active_operation_name = None
                    if poll_stop is not None:
                        poll_stop.set()
                    if poll_task is not None:
                        poll_task.cancel()
                        with contextlib.suppress(asyncio.CancelledError):
                            await poll_task

                if (
                    read_positions_after_operation
                    and not self._disable_angle_sensing
                    and not cancel_event.is_set()
                ):
                    if self._position_mode == POSITION_MODE_ACCURACY or (
                        self._disconnect_after_operation_enabled() and not skip_disconnect
                    ):
                        await self._async_read_positions()
                    else:
                        # Tracked + deduplicated: tie the read to the entry
                        # lifecycle. A raw async_create_task here would leak a
                        # task on every command and across reloads.
                        self._start_background_position_read()

                return result
            except BleakError as err:
                if _is_ble_authentication_error(err):
                    # A runtime auth failure is not the startup case: the
                    # controller is already initialised, so this link can still
                    # drive the bed and async_pair_now() can bond through it.
                    # Dropping it would spend the single connection a
                    # one-connection-per-window bed grants, and the repair could
                    # not reconnect until the user power-cycled the bed.
                    await self._async_handle_ble_authentication_error(err, retain_link=True)
                raise
            except _CONTROLLER_OPERATION_RECOVERY_EXCEPTIONS:
                if (
                    self._client is not None
                    and self._client.is_connected
                    and not self._disconnect_after_operation_enabled()
                ):
                    self._reset_disconnect_timer()
                raise
            finally:
                await self._async_finish_controller_operation(
                    entry_cancel_count=entry_cancel_count,
                    cancel_event=cancel_event,
                    scheduler_managed=scheduler_managed,
                    skip_disconnect=skip_disconnect,
                    operation_name=operation_name,
                )

    async def async_execute_controller_command(
        self,
        command_fn: Callable[[BedController], Coroutine[Any, Any, None]],
        cancel_running: bool = True,
        skip_disconnect: bool = False,
        *,
        resource: str | None = None,
        resources: Collection[str] | None = None,
        pulse_count: int | None = None,
        pulse_delay_ms: int | None = None,
        group_id: str | None = None,
        kind: CommandKind = CommandKind.COMMAND,
    ) -> None:
        """Execute an opaque controller command through the device scheduler."""

        async def operation() -> None:
            await self._async_execute_controller_operation(
                command_fn,
                cancel_running=False,
                skip_disconnect=skip_disconnect,
                raise_on_lock_cancel=False,
                preemptible=True,
                enable_position_polling=True,
                read_positions_after_operation=True,
                operation_name="command",
            )

        await self._async_schedule_command_operation(
            operation,
            resource=resource,
            resources=resources,
            kind=kind,
            cancel_running=cancel_running,
            pulse_count=pulse_count,
            pulse_delay_ms=pulse_delay_ms,
            group_id=group_id,
        )

    async def _async_schedule_command_operation(
        self,
        operation: Callable[[], Awaitable[None]],
        *,
        resource: str | None,
        resources: Collection[str] | None = None,
        kind: CommandKind,
        cancel_running: bool,
        pulse_count: int | None = None,
        pulse_delay_ms: int | None = None,
        group_id: str | None = None,
    ) -> None:
        """Schedule an operation, or run inline inside this scheduler's reservation."""
        context = current_command_context()
        if context is not None and context.scheduler_token is self._command_scheduler.token:
            previous_pulse_count = context.pulse_count
            previous_pulse_delay_ms = context.pulse_delay_ms
            if pulse_count is not None:
                context.pulse_count = pulse_count
            if pulse_delay_ms is not None:
                context.pulse_delay_ms = pulse_delay_ms
            try:
                await operation()
            finally:
                context.pulse_count = previous_pulse_count
                context.pulse_delay_ms = previous_pulse_delay_ms
            return

        intent = self._build_command_intent(
            operation,
            resource=resource,
            resources=resources,
            kind=kind,
            cancel_running=cancel_running,
            pulse_count=pulse_count,
            pulse_delay_ms=pulse_delay_ms,
            group_id=group_id,
        )
        await self._command_scheduler.execute(intent)

    def _build_command_intent(
        self,
        operation: Callable[[], Awaitable[None]],
        *,
        resource: str | None,
        resources: Collection[str] | None = None,
        kind: CommandKind,
        cancel_running: bool,
        pulse_count: int | None = None,
        pulse_delay_ms: int | None = None,
        group_id: str | None = None,
    ) -> CommandIntent:
        """Build one device intent while preserving legacy cancellation signals."""
        if resource is not None and resources is not None:
            raise ValueError("Pass resource or resources, not both")
        command_scope = (
            command_resources(*resources)
            if resources is not None
            else command_resources(resource or "*")
        )
        if cancel_running:
            # Keep preemptible non-scheduler work (queries and legacy direct
            # writes) responsive. Scheduler-owned operations use their private
            # ticket event and are replaced only when resources overlap.
            self._cancel_counter += 1
            self._cancel_command.set()

        async def scheduled(_context: CommandContext) -> None:
            await operation()

        return CommandIntent(
            scheduled,
            resources=command_scope,
            kind=kind,
            replacement_key=(resource or "*") if resources is None else None,
            cancel_running=cancel_running,
            group_id=group_id,
            pulse_count=pulse_count,
            pulse_delay_ms=pulse_delay_ms,
        )

    async def async_prepare_command_operation(
        self,
        operation: Callable[[], Awaitable[None]],
        *,
        resource: str | None = None,
        resources: Collection[str] | None = None,
        kind: CommandKind = CommandKind.GROUP,
        cancel_running: bool = True,
        group_id: str,
    ) -> CommandHandle:
        """Queue a linked operation without allowing controller execution yet."""
        intent = self._build_command_intent(
            operation,
            resource=resource,
            resources=resources,
            kind=kind,
            cancel_running=cancel_running,
            group_id=group_id,
        )
        return await self._command_scheduler.enqueue(intent, prepared=True)

    async def async_wait_prepared_command(self, handle: CommandHandle) -> None:
        """Wait until a prepared command owns this device scheduler."""
        await self._command_scheduler.wait_ready(handle)

    def commit_prepared_command(self, handle: CommandHandle) -> None:
        """Commit a prepared command after every linked device is ready."""
        self._command_scheduler.commit(handle)

    async def async_wait_prepared_command_result(self, handle: CommandHandle) -> None:
        """Wait for a committed linked command and require successful completion."""
        await self._command_scheduler.wait_prepared_result(handle)

    async def async_abort_prepared_command(self, handle: CommandHandle) -> None:
        """Abort a group member before or during execution."""
        await self._command_scheduler.cancel(handle, CommandOutcome.GROUP_ABORTED)

    async def async_execute_command_group(
        self,
        operations: Collection[Callable[[], Awaitable[None]]],
        *,
        resources: Collection[str],
        cancel_running: bool = True,
        group_id: str | None = None,
    ) -> None:
        """Run ordered operations as one resource-scoped scheduler intent."""
        operation_list = tuple(operations)
        if not operation_list:
            return

        async def group_operation() -> None:
            context = current_command_context()
            for index, operation in enumerate(operation_list):
                previous_defer_disconnect = (
                    context.defer_disconnect if context is not None else False
                )
                if context is not None:
                    context.defer_disconnect = index < len(operation_list) - 1
                try:
                    await operation()
                finally:
                    if context is not None:
                        context.defer_disconnect = previous_defer_disconnect

        context = current_command_context()
        if context is not None and context.scheduler_token is self._command_scheduler.token:
            await group_operation()
            return

        if cancel_running:
            self._cancel_counter += 1
            self._cancel_command.set()

        async def scheduled(_context: CommandContext) -> None:
            await group_operation()

        intent = CommandIntent(
            scheduled,
            resources=command_resources(*resources),
            kind=CommandKind.GROUP,
            cancel_running=cancel_running,
            group_id=group_id or uuid4().hex,
        )
        await self._command_scheduler.execute(intent)

    async def async_execute_controller_query(
        self,
        query_fn: Callable[[BedController], Coroutine[Any, Any, T]],
        cancel_running: bool = False,
        skip_disconnect: bool = False,
        preemptible: bool = True,
        run_if: Callable[[], bool] | None = None,
    ) -> T:
        """Execute a controller query and return its result."""
        result = await self._async_execute_controller_operation(
            query_fn,
            cancel_running=cancel_running,
            skip_disconnect=skip_disconnect,
            raise_on_lock_cancel=True,
            preemptible=preemptible,
            enable_position_polling=False,
            read_positions_after_operation=False,
            operation_name="query",
            run_if=run_if,
        )
        return cast(T, result)

    async def async_start_notify(self) -> None:
        """Start listening for position notifications."""
        if self._controller is None:
            _LOGGER.warning("Cannot start notifications: no controller available")
            return

        requires_notify_channel = self._controller.requires_notification_channel

        # Some controllers depend on notifications for command responses or
        # authentication even when angle sensing is disabled.
        if requires_notify_channel:
            if self._disable_angle_sensing:
                _LOGGER.info(
                    "Starting controller notifications for %s (%s requires notify channel with angle sensing disabled)",
                    self._address,
                    self._bed_type,
                )
                await self._controller.start_notify(None)
            else:
                _LOGGER.info(
                    "Starting controller notifications for %s (%s requires notify channel)",
                    self._address,
                    self._bed_type,
                )
                await self._controller.start_notify(self._handle_position_update)
            return

        if self._disable_angle_sensing:
            _LOGGER.info(
                "Angle sensing disabled for %s - skipping position notifications (physical remote will remain functional)",
                self._address,
            )
            return

        _LOGGER.info("Starting position notifications for %s", self._address)
        await self._controller.start_notify(self._handle_position_update)

    async def async_start_notify_for_diagnostics(self) -> None:
        """Start notifications for diagnostic capture, bypassing angle sensing setting.

        Unlike async_start_notify(), this always starts notifications regardless of
        the disable_angle_sensing setting. Used by diagnostics to capture raw protocol
        data from devices that have angle sensing disabled.
        """
        if self._controller is None:
            _LOGGER.warning("Cannot start diagnostic notifications: no controller available")
            return

        _LOGGER.info(
            "Starting notifications for diagnostic capture on %s (bypassing angle sensing setting)",
            self._address,
        )
        await self._controller.start_notify(self._handle_position_update)

    def set_raw_notify_callback(self, callback: Callable[[str, bytes], None] | None) -> None:
        """Set a callback to receive raw notification data.

        Used by diagnostics to capture raw BLE notifications from the controller
        without disrupting normal notification handling.

        Args:
            callback: Function to call with (characteristic_uuid, data), or None to clear.
        """
        if self._controller is not None:
            self._controller.set_raw_notify_callback(callback)

    async def _async_read_positions(self) -> None:
        """Actively read current positions from the bed.

        Called after movement commands to ensure position data is up to date.
        Uses a short timeout to avoid blocking commands.

        Note: This method does NOT acquire the command lock. When called from
        within a command (which already holds the lock), this is correct.
        For fire-and-forget background reads, use _async_read_positions_background().
        """
        if self._controller is None:
            return

        try:
            async with asyncio.timeout(3.0):
                await self._controller.read_positions(self._motor_count)
        except TimeoutError:
            _LOGGER.debug("Position read timed out")
        except Exception as err:
            _LOGGER.debug("Failed to read positions: %s", err)

    def _start_background_position_read(self) -> None:
        """Start a fire-and-forget position read tied to the config entry.

        Skips scheduling when a previous background read is still running so
        slow beds can't pile up queued reads behind the command lock.
        """
        task = self._background_read_task
        if task is not None and not task.done():
            _LOGGER.debug(
                "Background position read already running for %s - skipping", self._address
            )
            return
        self._background_read_task = self.entry.async_create_background_task(
            self.hass,
            self._async_read_positions_background(),
            name=f"adjustable_bed_position_read_{self._address}",
        )

    async def _async_read_positions_background(self) -> None:
        """Read positions in background with proper lock serialization.

        This method acquires the command lock to prevent concurrent GATT operations.
        Use this for fire-and-forget position reads (speed mode) to avoid
        "operation in progress" errors from overlapping BLE operations.
        """
        async with self._command_lock:
            await self._async_read_positions()

    async def _async_poll_positions_during_movement(self, stop_event: asyncio.Event) -> None:
        """Poll positions periodically during movement.

        Some motors (like Linak back) don't send notifications, only support reads.
        This provides real-time position updates during movement for those motors.
        Only polls motors that don't support notifications to avoid redundant reads.
        """
        if self._controller is None:
            return

        poll_interval = 0.5  # 500ms between polls
        while not stop_event.is_set():
            try:
                # Only read motors that don't send notifications
                async with asyncio.timeout(0.4):
                    await self._controller.read_non_notifying_positions()
            except TimeoutError:
                pass  # Timeout is expected during rapid polling
            except Exception as err:
                _LOGGER.debug("Position polling error (non-fatal): %s", err)

            # Wait for interval or stop signal
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=poll_interval)
                break  # Stop event was set
            except TimeoutError:
                pass  # Continue polling

    @callback
    def _handle_position_update(self, position: str, angle: float) -> None:
        """Handle a position update from the bed."""
        _LOGGER.debug("Position update: %s = %.1f°", position, angle)
        self._position_data[position] = angle
        self._position_data_generation[position] = self._position_connection_generation
        self._position_data_updated_monotonic[position] = time.monotonic()
        # Track notification timing for diagnostics (issue #168)
        self._last_notify_received = datetime.now(UTC)
        # Copy to safely iterate while callbacks might unregister themselves
        for callback_fn in list(self._position_callbacks):
            try:
                callback_fn(self._position_data)
            except Exception as err:
                _LOGGER.warning("Position callback error: %s", err)

    def register_position_callback(
        self, callback_fn: Callable[[dict[str, float]], None]
    ) -> Callable[[], None]:
        """Register a callback for position updates."""
        self._position_callbacks.add(callback_fn)

        # Immediately emit current position data if available
        # This handles the race where initial read completed before registration
        if self._position_data:
            try:
                callback_fn(self._position_data)
            except Exception as err:
                _LOGGER.warning("Position callback error during registration: %s", err)

        def unregister() -> None:
            self._position_callbacks.discard(callback_fn)  # Safe removal, no error if missing

        return unregister

    def register_controller_state_callback(
        self, callback_fn: Callable[[dict[str, Any]], None]
    ) -> Callable[[], None]:
        """Register a callback for non-position controller state updates."""
        self._controller_state_callbacks.add(callback_fn)

        if self._controller_state:
            try:
                callback_fn(self._controller_state)
            except Exception as err:
                _LOGGER.warning("Controller state callback error during registration: %s", err)

        self._schedule_controller_state_refresh()

        def unregister() -> None:
            self._controller_state_callbacks.discard(callback_fn)
            if not self._controller_state_callbacks:
                self._cancel_controller_state_refresh_retry()

        return unregister

    def _should_refresh_readable_light_state(self, *, force: bool) -> bool:
        """Return True when controller light state should be refreshed from the bed."""
        if not force and not self._controller_state_callbacks:
            return False

        if self._client is None or not self._client.is_connected or self._controller is None:
            return False

        if not self._controller.supports_under_bed_lights:
            return False

        if force:
            return True

        if self._controller_state_refresh_completed:
            return False

        required_keys = self._readable_light_state_required_keys()
        if not required_keys:
            return False

        return not required_keys.issubset(self._controller_state)

    def _readable_light_state_required_keys(self) -> set[str]:
        """Return the readable light-state keys expected for the current controller."""
        controller = self._controller
        if controller is None or not controller.supports_under_bed_lights:
            return set()

        required_keys: set[str] = set()
        if controller.supports_discrete_light_control:
            required_keys.add("under_bed_lights_on")
        if controller.supports_light_level_control:
            required_keys.add("light_level")
        if controller.supports_light_timer:
            required_keys.update({"light_timer_minutes", "light_timer_option"})
        return required_keys

    @callback
    def _mark_controller_state_refresh_complete(self) -> None:
        """Mark readable light-state hydration complete for the current connection."""
        self._controller_state_refresh_completed = True
        self._controller_state_refresh_retry_count = 0

    @callback
    def _schedule_controller_state_refresh_retry(self) -> None:
        """Schedule another readable light-state refresh after a transient failure."""
        if not self._should_refresh_readable_light_state(force=False):
            return

        if self._controller_state_refresh_retry_count >= _READABLE_LIGHT_STATE_MAX_RETRIES:
            _LOGGER.debug(
                "Giving up readable light-state refresh for %s after %d retries",
                self._address,
                self._controller_state_refresh_retry_count,
            )
            self._mark_controller_state_refresh_complete()
            return

        self._controller_state_refresh_retry_count += 1
        self._schedule_controller_state_refresh(retry_delay=_READABLE_LIGHT_STATE_RETRY_DELAY)

    @callback
    def _merge_controller_light_state(self, state: dict[str, Any]) -> None:
        """Merge readable light-state values into coordinator state."""
        if "is_on" in state and "under_bed_lights_on" not in state:
            state = {**state, "under_bed_lights_on": state["is_on"]}

        updates = {
            key: value for key, value in state.items() if self._controller_state.get(key) != value
        }
        if updates:
            self.handle_controller_state_updates(updates)
        if not self._should_refresh_readable_light_state(force=False):
            self._cancel_controller_state_refresh_retry()

    async def _async_refresh_readable_light_state(self) -> None:
        """Read light state from the controller and merge any fresh values."""
        controller = self._controller
        if controller is None:
            return

        state: dict[str, Any] | None = None
        cancelled_error: asyncio.CancelledError | None = None
        should_retry = False
        try:
            async with asyncio.timeout(_READABLE_LIGHT_STATE_TIMEOUT):
                state = await controller.read_light_state()
        except asyncio.CancelledError as err:
            should_retry = True
            cancelled_error = err
        except NotImplementedError:
            _LOGGER.debug(
                "Controller %s does not expose readable light state",
                self._bed_type,
            )
            self._mark_controller_state_refresh_complete()
        except (BleakError, ConnectionError, RuntimeError, TimeoutError) as err:
            _LOGGER.debug(
                "Failed to refresh readable light state for %s: %s",
                self._address,
                err,
            )
            should_retry = True
        except ValueError as err:
            _LOGGER.debug(
                "Invalid readable light state for %s: %s",
                self._address,
                err,
            )
            self._mark_controller_state_refresh_complete()
        except Exception:
            _LOGGER.debug(
                "Unexpected readable light state refresh failure for %s",
                self._address,
                exc_info=True,
            )
            self._mark_controller_state_refresh_complete()

        if state is not None:
            self._merge_controller_light_state(state)
            self._mark_controller_state_refresh_complete()
        elif should_retry:
            self._schedule_controller_state_refresh_retry()
        if cancelled_error is not None:
            raise cancelled_error

    async def _async_refresh_readable_light_state_task(self) -> None:
        """Run the controller-state refresh task and clear its tracking handle."""
        should_retry = False
        try:

            async def _read_light_state(controller: BedController) -> dict[str, Any]:
                return await controller.read_light_state()

            async with asyncio.timeout(_READABLE_LIGHT_STATE_TIMEOUT):
                state = await self.async_execute_controller_query(
                    _read_light_state,
                    cancel_running=False,
                    skip_disconnect=True,
                )
            self._merge_controller_light_state(state)
            self._mark_controller_state_refresh_complete()
        except asyncio.CancelledError:
            should_retry = True
            raise
        except NotImplementedError:
            _LOGGER.debug(
                "Controller %s does not expose readable light state",
                self._bed_type,
            )
            self._mark_controller_state_refresh_complete()
        except (BleakError, ConnectionError, RuntimeError, TimeoutError) as err:
            _LOGGER.debug(
                "Failed to refresh readable light state for %s: %s",
                self._address,
                err,
            )
            should_retry = True
        except ValueError as err:
            _LOGGER.debug(
                "Invalid readable light state for %s: %s",
                self._address,
                err,
            )
            self._mark_controller_state_refresh_complete()
        except Exception:
            _LOGGER.debug(
                "Unexpected readable light state refresh failure for %s",
                self._address,
                exc_info=True,
            )
            self._mark_controller_state_refresh_complete()
        finally:
            self._controller_state_refresh_task = None
            if should_retry:
                self._schedule_controller_state_refresh_retry()

    @callback
    def _cancel_controller_state_refresh_retry(self) -> None:
        """Cancel any pending retry for readable light-state hydration."""
        if self._controller_state_refresh_retry_timer is None:
            return

        self._controller_state_refresh_retry_timer.cancel()
        self._controller_state_refresh_retry_timer = None

    @callback
    def _handle_controller_state_refresh_retry(self) -> None:
        """Run a delayed readable light-state refresh retry."""
        self._controller_state_refresh_retry_timer = None
        self._schedule_controller_state_refresh()

    @callback
    def _schedule_controller_state_refresh(self, *, retry_delay: float = 0) -> None:
        """Schedule a one-shot controller-state refresh when entities need it."""
        if not self._should_refresh_readable_light_state(force=False):
            self._cancel_controller_state_refresh_retry()
            return

        if (
            self._controller_state_refresh_task is not None
            and not self._controller_state_refresh_task.done()
        ):
            return

        if retry_delay > 0:
            if self._controller_state_refresh_retry_timer is not None:
                return
            self._controller_state_refresh_retry_timer = self.hass.loop.call_later(
                retry_delay,
                self._handle_controller_state_refresh_retry,
            )
            return

        self._cancel_controller_state_refresh_retry()
        self._controller_state_refresh_task = self.hass.async_create_task(
            self._async_refresh_readable_light_state_task()
        )

    @callback
    def handle_controller_state_update(self, key: str, value: Any) -> None:
        """Store a single controller state value and notify listeners."""
        self.handle_controller_state_updates({key: value})

    @callback
    def handle_controller_state_updates(self, updates: dict[str, Any]) -> None:
        """Store controller state values and notify listeners."""
        if not updates:
            return

        self._controller_state.update(updates)
        for callback_fn in list(self._controller_state_callbacks):
            try:
                callback_fn(self._controller_state)
            except Exception as err:
                _LOGGER.warning("Controller state callback error: %s", err)

    def register_connection_state_callback(
        self, callback_fn: Callable[[bool], None]
    ) -> Callable[[], None]:
        """Register a callback for connection state changes."""
        self._connection_state_callbacks.add(callback_fn)

        def unregister() -> None:
            self._connection_state_callbacks.discard(callback_fn)

        return unregister

    def _notify_connection_state_change(self, connected: bool) -> None:
        """Notify all registered callbacks of a connection state change."""
        for callback_fn in list(self._connection_state_callbacks):
            try:
                callback_fn(connected)
            except Exception as err:
                _LOGGER.warning("Connection state callback error: %s", err)

    async def async_seek_position(
        self,
        position_key: str,
        target_angle: float,
        move_up_fn: Callable[[BedController], Coroutine[Any, Any, None]],
        move_down_fn: Callable[[BedController], Coroutine[Any, Any, None]],
        move_stop_fn: Callable[[BedController], Coroutine[Any, Any, None]],
        *,
        resources: Collection[str] | None = None,
    ) -> None:
        """Schedule one position target with axis-scoped replacement."""

        async def operation() -> None:
            await self._async_seek_position_serial(
                position_key,
                target_angle,
                move_up_fn,
                move_down_fn,
                move_stop_fn,
            )

        await self._async_schedule_command_operation(
            operation,
            resource=None if resources is not None else f"motor:{position_key}",
            resources=resources,
            kind=CommandKind.SEEK,
            cancel_running=True,
        )

    def _record_seek_result(self, result: SeekResult) -> None:
        """Retain the typed terminal outcome of one seek for diagnostics."""
        context = current_command_context()
        self._seek_outcomes[result.position_key] = {
            "outcome": result.outcome.value,
            "target": result.target,
            "final_angle": result.final_angle,
            "duration_seconds": round(result.duration, 3),
            "intent_id": context.intent_id if context is not None else None,
            "finished_at": datetime.now(UTC).isoformat(),
        }
        if result.final_direction is not None:
            self._last_seek_motion[result.position_key] = SeekMotion(
                moving_up=result.final_direction,
                outcome=result.outcome,
                finished_monotonic=time.monotonic(),
            )

    async def _async_seek_position_serial(
        self,
        position_key: str,
        target_angle: float,
        move_up_fn: Callable[[BedController], Coroutine[Any, Any, None]],
        move_down_fn: Callable[[BedController], Coroutine[Any, Any, None]],
        move_stop_fn: Callable[[BedController], Coroutine[Any, Any, None]],
    ) -> None:
        """Seek to a target position using feedback loop control.

        Owns the connection lifecycle around one seek: locking, connecting,
        initial position acquisition, and the direct-position shortcut. The
        feedback loop itself runs in `PositionSeekRunner` under the
        controller-supplied `PositionSeekPolicy`.

        Args:
            position_key: Key in position_data (e.g., "back", "legs")
            target_angle: Target position in degrees (or percentage for Keeson/Ergomotion)
            move_up_fn: Async function to move motor up
            move_down_fn: Async function to move motor down
            move_stop_fn: Async function to stop motor
        """
        cancel_event = self.cancel_command

        async with self._command_lock:
            # Cancel disconnect timer during seeking
            self._cancel_disconnect_timer()

            # Check if cancelled while waiting for lock
            if cancel_event.is_set():
                _LOGGER.debug("Position seek cancelled while waiting for lock")
                if self._client is not None and self._client.is_connected:
                    self._reset_disconnect_timer()
                return

            try:
                if not await self.async_ensure_connected(reset_timer=False):
                    _LOGGER.error("Cannot seek position: not connected to bed")
                    raise NotConnectedError("Not connected to bed")

                if self._controller is None:
                    _LOGGER.error("Cannot seek position: no controller available")
                    raise NoControllerError("No controller available")

                # Pin the controller for the whole seek. A disconnect callback can
                # clear self._controller while we await below, and every step of the
                # seek -- including the STOP in the finally block -- must keep acting
                # on the controller we validated rather than dereferencing None.
                controller = self._controller

                await self._async_refresh_controller_auth()

                supports_direct_position_control = controller.supports_direct_position_control

                # Cached values survive disconnects for display, but must not
                # drive direction or tolerance decisions on a new BLE session.
                # Attempt one read whenever this session has not reported the
                # requested axis. Direct-position controllers can still operate
                # if the read produces no fresh value.
                current_angle = (
                    self._position_data.get(position_key)
                    if self._position_is_current(position_key)
                    else None
                )
                if current_angle is None:
                    _LOGGER.debug(
                        "No current-session position data for %s, attempting one-shot read",
                        position_key,
                    )
                    await self._async_read_positions()
                    current_angle = (
                        self._position_data.get(position_key)
                        if self._position_is_current(position_key)
                        else None
                    )
                    if current_angle is None and not supports_direct_position_control:
                        raise NotConnectedError(
                            f"Cannot seek {position_key}: no position data available"
                        )

                policy = controller.position_seek_policy

                # Check if already at target (per the policy's completion band)
                if current_angle is not None and policy.accepts_position(
                    SeekSample(
                        position_key=position_key,
                        target=target_angle,
                        current=current_angle,
                        previous=None,
                        moving_up=target_angle > current_angle,
                        elapsed=0.0,
                    )
                ):
                    _LOGGER.debug(
                        "Position %s already at target: %.1f (target: %.1f)",
                        position_key,
                        current_angle,
                        target_angle,
                    )
                    self._record_seek_result(
                        SeekResult(
                            position_key=position_key,
                            target=target_angle,
                            outcome=SeekOutcome.ALREADY_AT_TARGET,
                            final_angle=current_angle,
                            final_direction=None,
                            duration=0.0,
                        )
                    )
                    return  # finally block handles disconnect

                if current_angle is None:
                    _LOGGER.info(
                        "Seeking position %s to %.1f without current feedback",
                        position_key,
                        target_angle,
                    )
                else:
                    _LOGGER.info(
                        "Seeking position %s from %.1f to %.1f",
                        position_key,
                        current_angle,
                        target_angle,
                    )

                # Check if controller supports direct position control (e.g., Reverie)
                # This bypasses the incremental seek loop for beds that can set positions directly
                if supports_direct_position_control:
                    native_position = controller.angle_to_native_position(
                        position_key, target_angle
                    )
                    _LOGGER.debug(
                        "Using direct position control: %s -> %d",
                        position_key,
                        native_position,
                    )
                    await controller.set_motor_position(position_key, native_position)
                    self._handle_position_update(position_key, target_angle)
                    self._record_seek_result(
                        SeekResult(
                            position_key=position_key,
                            target=target_angle,
                            outcome=SeekOutcome.DIRECT_SET,
                            final_angle=target_angle,
                            final_direction=None,
                            duration=0.0,
                        )
                    )
                    return  # finally block handles disconnect timer

                # Only direct-position controllers may reach this point without a
                # current reading, and they returned above.
                if current_angle is None:
                    raise NotConnectedError(
                        f"Cannot seek {position_key}: no position data available"
                    )

                use_custom_seek_steps = controller.uses_custom_position_seek_steps

                async def issue_seek_step(direction_up: bool, remaining_distance: float) -> None:
                    """Execute one seek movement step using controller-specific tuning."""
                    if use_custom_seek_steps:
                        await controller.seek_position_step(
                            position_key,
                            direction_up,
                            remaining_distance,
                        )
                        return
                    if direction_up:
                        await move_up_fn(controller)
                    else:
                        await move_down_fn(controller)

                async def read_position() -> float | None:
                    if policy.prefers_cached_position_feedback:
                        updated_at = self._position_data_updated_monotonic.get(position_key)
                        if (
                            updated_at is not None
                            and self._position_is_current(position_key)
                            and time.monotonic() - updated_at
                            <= policy.cached_position_feedback_max_age
                        ):
                            return self._position_data.get(position_key)
                    await self._async_read_positions()
                    return self._position_data.get(position_key)

                runner = PositionSeekRunner(
                    position_key=position_key,
                    target_angle=target_angle,
                    policy=policy,
                    cancel_event=cancel_event,
                    read_position=read_position,
                    issue_step=issue_seek_step,
                    stop=lambda: move_stop_fn(controller),
                    previous_motion=self._last_seek_motion.get(position_key),
                )
                try:
                    result = await runner.async_run(cast(float, current_angle))
                except SeekTimeoutError as err:
                    self._record_seek_result(err.result)
                    raise
                self._record_seek_result(result)

            finally:
                if self._bed_type == BED_TYPE_LINAK and not self._command_scheduler.has_pending:
                    # Seeks own their lock lifecycle instead of going through
                    # _async_finish_controller_operation(), so reconcile a
                    # deferred Linak snapshot here as well.
                    self._backfill_linak_snapshot()
                if self._client is not None and self._client.is_connected:
                    if (
                        self._disconnect_after_operation_enabled()
                        and not cancel_event.is_set()
                        and not self._command_scheduler.has_pending
                        and not (
                            (context := current_command_context()) is not None
                            and context.defer_disconnect
                        )
                    ):
                        _LOGGER.debug(
                            "Disconnecting after seek (disconnect_after_command=True) for %s",
                            self._address,
                        )
                        await self.async_disconnect()
                    else:
                        self._reset_disconnect_timer()
