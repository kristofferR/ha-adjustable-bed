"""Coordinator for Adjustable Bed integration."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import math
from collections import deque
from collections.abc import (
    AsyncIterator,
    Awaitable,
    Callable,
    Collection,
    Coroutine,
    Mapping,
)
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, TypeVar, cast
from uuid import uuid4
from weakref import WeakKeyDictionary

from bleak import BleakClient
from bleak.exc import BleakError
from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo

from .app_state_store import app_state_slot, app_state_store
from .bed_traits import (
    bed_traits,
    disconnect_after_command_default_enabled,
    passive_position_reconciliation_default_enabled,
)
from .beds.vibradorm.app_state import (
    ControlType,
    VibradormAppSessionIntent,
    get_vibradorm_app_session_intent,
)
from .ble_auth import is_ble_authentication_error
from .bluetooth_transport import (
    ConnectionPath,
)
from .bond_verification import (
    BondEvidence,
)
from .command_scheduler import (
    ALL_COMMAND_RESOURCES,
    CommandContext,
    CommandHandle,
    CommandIntent,
    CommandKind,
    CommandOutcome,
    DeviceCommandScheduler,
    HoldClaim,
    HoldLease,
    StreamDriver,
    StreamMember,
    command_resources,
    current_command_context,
)
from .const import (
    ADAPTER_AUTO,
    BED_MOTOR_PULSE_DEFAULTS,
    BED_TYPE_BEDJET_POWERLAYER,
    BED_TYPE_BEDTECH,
    BED_TYPE_COMFORT_MOTION,
    BED_TYPE_DEWERTOKIN,
    BED_TYPE_DIAGNOSTIC,
    BED_TYPE_ERGOMOTION,
    BED_TYPE_FSM_RELAX,
    BED_TYPE_FURNIMOVE,
    BED_TYPE_JENSEN,
    BED_TYPE_JIECANG,
    BED_TYPE_KAIDI,
    BED_TYPE_KEESON,
    BED_TYPE_LEGGETT_GEN2,
    BED_TYPE_LEGGETT_OKIN,
    BED_TYPE_LEGGETT_PLATT,
    BED_TYPE_LEGGETT_WILINKE,
    BED_TYPE_LIMOSS,
    BED_TYPE_LIMOSS_REMOTE,
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
    BED_TYPE_REMACRO,
    BED_TYPE_REVERIE,
    BED_TYPE_REVERIE_NIGHTSTAND,
    BED_TYPE_RICHMAT,
    BED_TYPE_SERTA,
    BED_TYPE_SLEEP_NUMBER,
    BED_TYPE_SOLACE,
    BED_TYPE_STARCODE_ABM5_4,
    BED_TYPE_VIBRADORM_APP,
    BED_TYPE_VMATBASIC,
    BEDJET_POWERLAYER_FOOT_MAX_ANGLE,
    BEDJET_POWERLAYER_HEAD_MAX_ANGLE,
    CONF_BACK_MAX_ANGLE,
    CONF_BED_TYPE,
    CONF_BLE_BOND_ESTABLISHED,
    CONF_BLE_BOND_MARKER_UNRELIABLE,
    CONF_BLE_DEVICE_NAME,
    CONF_CONNECTION_PROFILE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_DISCONNECT_AFTER_COMMAND,
    CONF_HAS_LIGHT,
    CONF_HAS_MASSAGE,
    CONF_IDLE_DISCONNECT_SECONDS,
    CONF_KAIDI_ROOM_ID,
    CONF_KAIDI_TARGET_VADDR,
    CONF_LEGS_MAX_ANGLE,
    CONF_LIMOSS_REMOTE_STATE,
    CONF_MOTOR_COUNT,
    CONF_MOTOR_PULSE_COUNT,
    CONF_MOTOR_PULSE_DELAY_MS,
    CONF_MOTOR_PULSE_USER_SET,
    CONF_PAIR_MODE,
    CONF_PASSIVE_POSITION_RECONCILIATION,
    CONF_POSITION_MODE,
    CONF_PREFERRED_ADAPTER,
    CONF_PROFILE_ID,
    CONF_REMACRO_LED_LEVEL,
    CONF_RICHMAT_REMOTE,
    CONF_SIDE,
    CONF_VIBRADORM_APP_METADATA,
    CONF_VIBRADORM_APP_PROFILE,
    CONF_VIBRADORM_CONTROL_TYPE,
    CONF_VIBRADORM_FLOOR_DEFAULT,
    CONF_VIBRADORM_LIGHT_EXTENSION,
    CONF_VIBRADORM_RESTORED,
    CONF_VIBRADORM_VMAT_REMOTE,
    CONF_VMATBASIC_FLOOR_LEVEL,
    CONF_VMATBASIC_FLOOR_MINUTES,
    CONF_VMATBASIC_PROFILE,
    CONNECTION_PROFILES,
    DEFAULT_BACK_MAX_ANGLE,
    DEFAULT_CONNECTION_PROFILE,
    DEFAULT_DISABLE_ANGLE_SENSING,
    DEFAULT_HAS_MASSAGE,
    DEFAULT_IDLE_DISCONNECT_SECONDS,
    DEFAULT_LEGS_MAX_ANGLE,
    DEFAULT_MOTOR_COUNT,
    DEFAULT_POSITION_MODE,
    DEFAULT_PROTOCOL_VARIANT,
    DOMAIN,
    LEGGETT_OKIN_SUPERSEDED_PULSE_DEFAULTS,
    LEGGETT_VARIANT_OKIN,
    LINAK_VARIANT_PERFORMANCE,
    NAME_RULE_VARIANTS_BY_BED_TYPE,
    OCTO_VARIANT_STAR2,
    OFFLINE_CAPABILITY_SAFE_BED_TYPES,
    PAIR_MODE_SINGLE_ADDRESS,
    POSITION_MODE_ACCURACY,
    REVERIE_BACK_MAX_ANGLE,
    RICHMAT_MH_BED_TYPES,
    RICHMAT_REMOTE_AUTO,
    SOLACE_VARIANT_WOOSA,
    STARCODE_GROUP_BED_TYPES,
    get_motor_pulse_defaults,
    get_richmat_motor_count,
    resolve_explicit_bed_type,
    resolve_richmat_remote_code,
)
from .controller_factory import create_controller
from .controller_state import AnyStateKey, ControllerState, StateKey, StateUpdate
from .coordinator_bonds import CoordinatorBondsMixin
from .coordinator_connection import CoordinatorConnectionMixin
from .coordinator_positions import CoordinatorPositionsMixin
from .detection import (
    OKIN_SHARED_UUID_GATT_REFINABLE_TYPES,
    is_mac_like_name,
)
from .execution import HOLD_CEILING_MS
from .pairing import (
    OFFLINE_CAPABILITY_SAFE_VARIANTS,
    filter_child_options,
    is_paired,
    octo_snapshot_from_descriptor,
)
from .position_seek import (
    SeekMotion,
)
from .profile_id import entry_profile_id, profile_route, resolve_profile_id
from .state_keys import (
    LIGHT_LEVEL,
    LIGHT_TIMER_MINUTES,
    LIGHT_TIMER_OPTION,
    LINAK_MODEL_VARIANT,
    UNDER_BED_LIGHTS_ON,
)

if TYPE_CHECKING:
    from .beds.base import BedController
    from .beds.reverie.pairlink_runtime import PairlinkRuntime
    from .beds.starcode.abm5_4_profiles import RetainedAppState

T = TypeVar("T")
_LOGGER = logging.getLogger(__name__)
_CONTROLLER_OPERATION_RECOVERY_EXCEPTIONS = (ConnectionError, RuntimeError)
_READABLE_LIGHT_STATE_TIMEOUT = 2.0
_READABLE_LIGHT_STATE_RETRY_DELAY = 1.0
_READABLE_LIGHT_STATE_MAX_RETRIES = 3


# One reconnect gives a stale preserved OKIN profile another chance to reveal
# the CST/RF ECO BT discriminator without making known receivers pay DIS
# timeouts forever.
_OKIN_PRESERVED_PROFILE_DEVICE_INFO_MAX_READ_ATTEMPTS = 2

MAX_COMMAND_TRACE_ENTRIES = 100

MAX_CONNECTION_ATTEMPT_DETAILS = 25

# Backwards-compatible private alias; the implementation now lives in ble_auth
# so the repairs flow can share it without importing the coordinator.
_is_ble_authentication_error = is_ble_authentication_error


class ChildEntryView:
    """A per-side config view of a parent ConfigEntry (Dual Bed 4.0).

    A paired bed is one config entry but two child coordinators. Each child reads
    its per-side config from ``.data`` (this view) and persists runtime changes
    through ``persist_data`` — which updates this view in place and routes to the
    parent's child descriptor. Explicit lifecycle methods forward to the parent,
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
                **filter_child_options(self._child_data, self._parent.options),
            }
        return self._child_data

    @property
    def options(self) -> Mapping[str, Any]:
        return filter_child_options(self._child_data, self._parent.options)

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

    @property
    def entry_id(self) -> str:
        return self._parent.entry_id

    @property
    def title(self) -> str:
        return self._parent.title

    @property
    def unique_id(self) -> str | None:
        return self._parent.unique_id

    @property
    def version(self) -> int:
        return self._parent.version

    def async_create_background_task[R](
        self, hass: HomeAssistant, target: Coroutine[object, object, R],
        name: str, eager_start: bool = True,
    ) -> asyncio.Task[R]:
        return self._parent.async_create_background_task(hass, target, name, eager_start)

    def async_on_unload(
        self, func: Callable[[], Coroutine[object, object, None] | None],
    ) -> None:
        self._parent.async_on_unload(func)


class AdjustableBedCoordinator(
    CoordinatorBondsMixin, CoordinatorConnectionMixin, CoordinatorPositionsMixin
):
    """Coordinator for managing bed connection and state."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry | ChildEntryView) -> None:
        """Initialize the coordinator."""
        self.hass = hass
        self.entry = entry
        self._address: str = entry.data[CONF_ADDRESS].upper()
        # The stored profile id is the lookup key; its route is what the
        # controller factory and every bed-type branch below read.
        self._profile_id: str = entry_profile_id(entry.data)
        route = profile_route(self._profile_id)
        self._bed_type: str = route.bed_type
        self._protocol_variant: str = (
            route.variant if route.variant is not None else DEFAULT_PROTOCOL_VARIANT
        )
        self._name: str = entry.data.get(CONF_NAME, "Adjustable Bed")
        # Malouf's APK has one command exception keyed to Smartbed238. Keep the
        # configured name as a controller fallback, but track actual observations
        # separately so protocol detection never relies on a user-facing rename.
        self._ble_device_name: str = entry.data.get(CONF_BLE_DEVICE_NAME, self._name)
        self._observed_ble_device_name: str | None = None
        self._furnimove_bond_task: asyncio.Task[None] | None = None
        self._furnimove_bond_request: dict[str, object] = {"status": "not_requested"}
        if self._bed_type == BED_TYPE_RICHMAT:
            from .beds.richmat.features import get_richmat_features

            # Entities need the motor count before the first connection, so it
            # comes from the stored remote code, as the Richmat builder resolves it.
            richmat_remote = resolve_richmat_remote_code(
                entry.data.get(CONF_RICHMAT_REMOTE, RICHMAT_REMOTE_AUTO),
                entry_title=entry.title,
                configured_name=self._name,
            )
            self._motor_count = get_richmat_motor_count(get_richmat_features(richmat_remote))
        else:
            self._motor_count = entry.data.get(CONF_MOTOR_COUNT, DEFAULT_MOTOR_COUNT)
        self._has_massage: bool = entry.data.get(CONF_HAS_MASSAGE, DEFAULT_HAS_MASSAGE)
        self._disable_angle_sensing: bool = entry.data.get(
            CONF_DISABLE_ANGLE_SENSING, DEFAULT_DISABLE_ANGLE_SENSING
        )
        # Legacy P1 positions have no side ownership. Keep the stored preference
        # for restoring standalone controls, but never seek using shared feedback.
        if (
            is_paired(entry.data)
            and entry.data.get(CONF_PAIR_MODE) == PAIR_MODE_SINGLE_ADDRESS
            and self._bed_type in {BED_TYPE_KEESON, BED_TYPE_ERGOMOTION}
        ):
            self._disable_angle_sensing = True
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
        self._connection_timeout: float = (
            bed_traits(self._bed_type, self._protocol_variant).connection_timeout
            or profile_settings.connection_timeout
        )
        if entry.data.get(CONF_VIBRADORM_APP_PROFILE) == "vmat":
            self._connection_timeout = 10.0
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
            CONF_DISCONNECT_AFTER_COMMAND,
            disconnect_after_command_default_enabled(self._bed_type, self._protocol_variant),
        )
        self._idle_disconnect_seconds: int = entry.data.get(
            CONF_IDLE_DISCONNECT_SECONDS, DEFAULT_IDLE_DISCONNECT_SECONDS
        )

        self._client: BleakClient | None = None
        self._vmat_unready_client: BleakClient | None = None
        self._controller: BedController | None = None
        self._pairlink_runtime: PairlinkRuntime | None = None
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
        # A connect in this session timed out or aborted, and whether the last
        # resolved controller holds its link after that (cached like the above).
        self._reconnect_stalled = False
        self._holds_link_after_stall_resolved = False
        self._disconnect_timer: asyncio.TimerHandle | None = None
        self._reconnect_timer: asyncio.TimerHandle | None = None
        self._reconnect_task: asyncio.Task[None] | None = None
        self._lock = asyncio.Lock()
        self._command_lock = asyncio.Lock()  # Separate lock for command serialization
        self._command_connection_holds = 0
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
        # CB35 autonomous presets can outlive the connection-scoped controller.
        self.okin_cb35_preset_started_at: float | None = None
        self._controller_state = ControllerState()
        self.starcode_app_retained_state: RetainedAppState | None = None
        self.furnimove_widget_state: tuple[bool, bytes | None, bytes | None] = (False, None, None)
        # App-local state (BedController.persisted_app_state), slotted per restored controller.
        self._app_state_store = app_state_store(hass, self._address)
        self._app_state_slots: WeakKeyDictionary[BedController, str] = WeakKeyDictionary()
        self._app_state_restoring = False
        self._controller_state_callbacks: set[Callable[[ControllerState], None]] = set()
        self._controller_state_refresh_task: asyncio.Task[None] | None = None
        self._controller_state_refresh_retry_timer: asyncio.TimerHandle | None = None
        self._controller_state_refresh_retry_count = 0
        self._controller_state_refresh_completed = False
        self._diagnostic_poll_task: asyncio.Task[None] | None = None
        self._diagnostic_advertisement_task: asyncio.Task[None] | None = None
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
        # Proxies whose stale GATT cache an auth failure already cleared, so only
        # the first such failure per proxy skips re-pairing (issue #660).
        self._stale_gatt_retry_sources: set[str] = set()
        # The proxy whose stale cache the attempt that just failed cleared; the
        # next attempt verifies there without pairing.
        self._stale_gatt_retry_source: str | None = None
        # The path whose authentication failed most recently in this attempt.
        self._auth_failure_source: str | None = None

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
        # BOX25 auto selects its dialect from Device Information, which may first
        # become readable on a later connection; the dialects expose different lights.
        self._box25_dialect: type[BedController] | None = None
        self._capability_reload_scheduled = False
        self._capability_reload_deferrals = 0
        self._shutting_down = False
        self._pairing_transfer_active = False
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
        # Pair Now is an explicit user repair for Nectar Move, whose ordinary
        # profile deliberately does not request a bond. Scope this override to
        # that locked repair operation only.
        self._force_pairing_requested: bool = False
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
        elif (
            self._protocol_variant
            in NAME_RULE_VARIANTS_BY_BED_TYPE.get(self._bed_type, frozenset())
            and not is_mac_like_name(device_name)
            and self.entry.data.get(CONF_BLE_DEVICE_NAME) != device_name
        ):
            # App name rules (SIMMONS, Adjustable Lumbar) need the raw name later, when BlueZ may
            # report only the address; entities do not depend on it.
            self._begin_internal_entry_update(
                bool(self.entry.data.get(CONF_BLE_BOND_ESTABLISHED, False))
            )
            self._async_persist_config(
                {**self.entry.data, CONF_BLE_DEVICE_NAME: device_name},
                keys={CONF_BLE_DEVICE_NAME},
            )

    def _schedule_pending_capability_reload(self) -> None:
        """Reload capability-gated entities once this BLE link is released."""
        if (
            not self._pending_capability_reload
            or self._capability_reload_scheduled
            or self._capability_reload_deferrals
            or self._shutting_down
            or self._pairing_transfer_active
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

    def _starcode_reload_coordinators(self, loaded: object) -> tuple[AdjustableBedCoordinator, ...]:
        """Find the exact standalone or physical children of this loaded entry."""
        from .paired_coordinator import PairedBedCoordinator

        if isinstance(loaded, AdjustableBedCoordinator):
            return (loaded,) if loaded.entry.entry_id == self.entry.entry_id else ()
        if isinstance(loaded, PairedBedCoordinator):
            return tuple(
                child
                for child in loaded.children.values()
                if isinstance(child, AdjustableBedCoordinator)
                and child.entry.entry_id == self.entry.entry_id
            )
        return ()

    async def _async_reload_if_capability_changed(self) -> None:
        """Reload if this disconnected coordinator still owns the loaded entry."""
        if (
            not self._pending_capability_reload
            or self._capability_reload_deferrals
            or self._shutting_down
            or self._pairing_transfer_active
        ):
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
        from .beds.starcode.abm5_4 import StarcodeAbm5_4Controller
        from .beds.starcode.abm5_4_profiles import RetainedAppState

        retained_states = {
            (child.entry.entry_id, child.address): child.starcode_app_retained_state
            for child in self._starcode_reload_coordinators(loaded)
            if child.bed_type == BED_TYPE_STARCODE_ABM5_4
            and isinstance(child.starcode_app_retained_state, RetainedAppState)
            and child.starcode_app_retained_state.address == child.address
        }
        self._pending_capability_reload = False
        if not await self.hass.config_entries.async_reload(self.entry.entry_id):
            return
        reloaded = self.hass.data.get(DOMAIN, {}).get(self.entry.entry_id)
        for child in self._starcode_reload_coordinators(reloaded):
            retained = retained_states.get((child.entry.entry_id, child.address))
            fresh = child.starcode_app_retained_state
            if (
                retained is None
                or child.bed_type != BED_TYPE_STARCODE_ABM5_4
                or isinstance(fresh, RetainedAppState)
                and (fresh.observed or fresh.last_light_time_ms is not None)
            ):
                continue
            child.starcode_app_retained_state = retained
            controllers = (child._controller, child._offline_controller)
            for controller in controllers:
                if isinstance(controller, StarcodeAbm5_4Controller):
                    controller.restore_retained_app_state(retained)

    @contextlib.asynccontextmanager
    async def async_defer_capability_reload(self) -> AsyncIterator[None]:
        """Keep a multi-phase service's coordinators alive while releasing BLE links."""
        self._capability_reload_deferrals += 1
        try:
            yield
        finally:
            self._capability_reload_deferrals -= 1
            if not self._capability_reload_deferrals:
                self._schedule_pending_capability_reload()

    @contextlib.asynccontextmanager
    async def async_command_operation_guard(self) -> AsyncIterator[None]:
        """Wait for this child's command lane and keep it idle."""
        async with self._command_lock:
            yield

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
        if bed_type_changed:
            self._profile_id = entry_data[CONF_PROFILE_ID] = resolve_profile_id(entry_data)
        if migrate_leggett_okin_defaults and corrected_defaults is not None:
            entry_data[CONF_MOTOR_PULSE_COUNT] = corrected_defaults[0]
            entry_data[CONF_MOTOR_PULSE_DELAY_MS] = corrected_defaults[1]
        if corrected_bed_type == BED_TYPE_BEDTECH:
            entry_data.pop(CONF_RICHMAT_REMOTE, None)
        angle_sensing_defaulted = CONF_DISABLE_ANGLE_SENSING not in self.entry.data or (
            self.entry.data.get(CONF_DISABLE_ANGLE_SENSING) is True
            and not bed_traits(previous_bed_type).position_feedback
        )
        # Config flow defaults disable_angle_sensing from the position_feedback trait,
        # so the correction must use the same trait: a repaired entry (e.g. CB35 ->
        # BOX25, #419) should get position feedback re-enabled even when the
        # corrected type reports percentages rather than angles.
        if (
            bed_traits(corrected_bed_type).position_feedback
            and angle_sensing_defaulted
            and self._disable_angle_sensing
            and not (
                is_paired(entry_data)
                and entry_data.get(CONF_PAIR_MODE) == PAIR_MODE_SINGLE_ADDRESS
                and corrected_bed_type in {BED_TYPE_KEESON, BED_TYPE_ERGOMOTION}
            )
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
            and not bed_traits(corrected_bed_type).position_feedback
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
    def entity_side(self) -> str | None:
        """Standalone and separate-address children keep unsuffixed identities."""
        return None

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
    def bed_type(self) -> str:
        """Return the bed type."""
        return self._bed_type

    @property
    def profile_id(self) -> str:
        """Return the profile id this coordinator builds its controller from."""
        return self._profile_id

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
            if self._bed_type == BED_TYPE_BEDJET_POWERLAYER:
                return BEDJET_POWERLAYER_HEAD_MAX_ANGLE
            return self.back_max_angle
        if position_key in ("legs", "feet"):
            if self._bed_type == BED_TYPE_BEDJET_POWERLAYER:
                return BEDJET_POWERLAYER_FOOT_MAX_ANGLE
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
    def controller_side(self) -> None:
        """A physical bed's controller is never shared between logical sides."""
        return None

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

    async def async_prime_offline_controller(self, *, preview: bool = False) -> None:
        """Best-effort mint of a client-free controller for capability reads.

        Construction only — never connects or starts notifications. Failures are
        non-fatal (a bad mint just leaves this side as before). Bed types whose
        controller needs a live client (auto-detected Richmat/L&P/Keeson
        variants) raise ConnectionError and are left without an offline
        controller until they connect.

        ``preview`` mints for a staged configuration that is never set up: it
        lists the controls the configuration declares before connecting, so it
        skips the runtime safety gate and never reads or writes app state.
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
        # A Jensen side's capabilities come from its config report, stored once
        # it has connected; with that snapshot it can be minted offline.
        jensen_snapshot = (
            capabilities.get("jensen")
            if bed_type == BED_TYPE_JENSEN and isinstance(capabilities, dict)
            else None
        )
        # A Richmat MH side's pages come from its model catalog plus the stored
        # session replies; with that snapshot it can be minted offline.
        richmat_mh_snapshot = (
            capabilities.get("richmat_mh")
            if bed_type in RICHMAT_MH_BED_TYPES and isinstance(capabilities, dict)
            else None
        )
        # Octo Remote Star2 is a different protocol with FIXED capabilities and no
        # PIN/snapshot, so it IS statically offline-mintable (like Linak) — its
        # controller builds without a client.
        is_octo_star2 = bed_type == BED_TYPE_OCTO and self._protocol_variant == OCTO_VARIANT_STAR2
        is_linak_performance = (
            bed_type == BED_TYPE_LINAK and self._protocol_variant == LINAK_VARIANT_PERFORMANCE
        )
        # A Remacro side mints its stored model's screen, else the fallback
        # screen; a live advertisement still wins when it connects, and a
        # fallback side reloads once it advertises a listed model.
        remacro = bed_type == BED_TYPE_REMACRO
        statically_mintable = bed_type in OFFLINE_CAPABILITY_SAFE_BED_TYPES and (
            bed_type != BED_TYPE_SOLACE
            or isinstance(self.entry.data.get(CONF_BLE_DEVICE_NAME), str)
            or self._protocol_variant == SOLACE_VARIANT_WOOSA
        )
        # An explicit variant whose capabilities come only from stored config.
        variant_mintable = self._protocol_variant in OFFLINE_CAPABILITY_SAFE_VARIANTS.get(
            bed_type, frozenset()
        )
        mintable = (
            statically_mintable
            or variant_mintable
            or remacro
            # FSM Relax mints from its exact stored capability body (entry data).
            # With no snapshot its action/memory descriptors remain empty.
            or bed_type == BED_TYPE_FSM_RELAX
            or (bed_type == BED_TYPE_OCTO and (octo_snapshot is not None or is_octo_star2))
            or (bed_type == BED_TYPE_LINAK and (linak_snapshot is not None or is_linak_performance))
            or (bed_type == BED_TYPE_JENSEN and jensen_snapshot is not None)
            or (bed_type in RICHMAT_MH_BED_TYPES and isinstance(richmat_mh_snapshot, dict))
        )
        if not mintable and not preview:
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
            )
            if not preview:
                await self._async_restore_app_state(self._offline_controller)
            if bed_type in RICHMAT_MH_BED_TYPES and not getattr(
                self._offline_controller, "has_stored_capabilities", False
            ):
                # The snapshot belongs to another model (the variant changed):
                # its pages are unknown until the side connects again.
                self._offline_controller = None
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
        Caching the just-discovered live controller keeps them. A complete live
        discovery replaces an older cache, while an incomplete discovery only
        fills an empty cache. This preserves known capabilities across transient
        probe failures while allowing a later successful fallback connection to
        refresh them.
        """
        if self._controller is not None and (
            self._offline_controller is None
            or self._controller.controller_entity_discovery_complete
        ):
            self._offline_controller = self._controller

    @property
    def controller_state(self) -> ControllerState:
        """Return non-position controller state."""
        return self._controller_state

    @property
    def vibradorm_app_session_intent(self) -> VibradormAppSessionIntent:
        """Return this exact physical target's process-local app intentions."""
        if self._bed_type != BED_TYPE_VIBRADORM_APP:
            raise ValueError("App intent requires an explicit Vibradorm app profile")
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
        app_profile = self.entry.data[CONF_VIBRADORM_APP_PROFILE]
        fallback = 6
        if (
            app_profile == "caresse" and self.entry.data.get(CONF_VIBRADORM_RESTORED) is True
        ) or app_profile == "vmat":
            fallback = 6 if self.entry.data.get(CONF_VIBRADORM_LIGHT_EXTENSION) else 8
        return get_vibradorm_app_session_intent(
            self.hass, self._address, app_profile=app_profile, control_type=control_type,
            remembered_floor_default=self.entry.data.get(CONF_VIBRADORM_FLOOR_DEFAULT, fallback),
            remote=self.entry.data.get(CONF_VIBRADORM_VMAT_REMOTE),
        )

    def remember_vibradorm_app_floor_default(self, level: int) -> None:
        """Remember local brightness intent without claiming a hardware response."""
        if isinstance(level, bool) or not isinstance(level, int) or not 1 <= level <= 8:
            raise ValueError("Remembered brightness must be an integer from one to eight")
        intent = self.vibradorm_app_session_intent
        intent.floor.default_level = level
        if self.entry.data.get(CONF_VIBRADORM_FLOOR_DEFAULT) == level:
            return
        self._begin_internal_entry_update(self._ble_bond_established)
        self._async_persist_config({**self.entry.data, CONF_VIBRADORM_FLOOR_DEFAULT: level})

    def remember_remacro_led_level(self, model_id: int, level: int) -> None:
        """Persist the committed Remacro LED level.

        The app keys its "LV" preference by model (company ID) and address, so
        each model keeps its own value and a new model starts at the default.
        """
        if self._bed_type != BED_TYPE_REMACRO:
            raise ValueError("The LED level belongs to the Remacro app profiles")
        if isinstance(level, bool) or not isinstance(level, int) or not 0 <= level <= 255:
            raise ValueError("The LED level must be an integer from 0 to 255")
        stored = self.entry.data.get(CONF_REMACRO_LED_LEVEL)
        levels = dict(stored) if isinstance(stored, dict) else {}
        if levels.get(str(model_id)) == level:
            return
        levels[str(model_id)] = level
        self._begin_internal_entry_update(self._ble_bond_established)
        self._async_persist_config(
            {**self.entry.data, CONF_REMACRO_LED_LEVEL: levels}, keys={CONF_REMACRO_LED_LEVEL}
        )

    def remember_richmat_mh_snapshot(self, snapshot: Mapping[str, Any]) -> None:
        """Persist a Richmat MH session's version and page replies.

        The app rebuilds its pages from these replies on every connection; a
        changed snapshot reloads the entities once this link is released.
        """
        if self._bed_type not in RICHMAT_MH_BED_TYPES:
            raise ValueError("The capability snapshot belongs to the Richmat MH app profiles")
        capabilities = dict(self.entry.data.get("capabilities") or {})
        if capabilities.get("richmat_mh") == snapshot:
            return
        capabilities["richmat_mh"] = dict(snapshot)
        self._begin_internal_entry_update(self._ble_bond_established)
        if self._pending_internal_bond_marker is not None:
            self._pending_capability_reload = True
        self._async_persist_config({**self.entry.data, "capabilities": capabilities})
        self._offline_controller = self._controller
        self._schedule_pending_capability_reload()

    def remember_fsm_relax_capabilities(self, body: bytes) -> None:
        """Persist FSM Relax's capability reply, which decides its entities.

        The controller decides whether the change needs a reload.
        """
        if self._bed_type != BED_TYPE_FSM_RELAX:
            raise ValueError("The capability reply belongs to the FSM Relax app profile")
        capabilities = dict(self.entry.data.get("capabilities") or {})
        if capabilities.get("fsm_relax") == body.hex():
            return
        capabilities["fsm_relax"] = body.hex()
        self._begin_internal_entry_update(self._ble_bond_established)
        self._async_persist_config({**self.entry.data, "capabilities": capabilities})

    def remember_vmatbasic_settings(self, settings: dict[str, int]) -> None:
        """Persist this physical receiver's requested settings, never measured state."""
        from .profiles.vmatbasic import integer

        profile = self.entry.data.get(CONF_VMATBASIC_PROFILE)
        if self._bed_type != BED_TYPE_VMATBASIC or profile not in {"cbi", "xtbox"}:
            raise ValueError("Floor settings require an explicit V-MAT Basic floor profile")
        updates: dict[str, int] = {}
        if "floor_level" in settings:
            updates[CONF_VMATBASIC_FLOOR_LEVEL] = integer(
                settings["floor_level"],
                1 if profile == "xtbox" else 0,
                6 if profile == "xtbox" else 255,
            )
        if "floor_minutes" in settings:
            updates[CONF_VMATBASIC_FLOOR_MINUTES] = integer(
                settings["floor_minutes"], 0, 255 if profile == "xtbox" else 1439
            )
        if any(self.entry.data.get(key) != value for key, value in updates.items()):
            self._begin_internal_entry_update(self._ble_bond_established)
            self._async_persist_config({**self.entry.data, **updates})

    def remember_vmatbasic_name(self, name: str) -> None:
        """Retain a confirmed GAP write for this exact physical config entry."""
        if self._bed_type != BED_TYPE_VMATBASIC:
            raise ValueError("Name persistence requires a V-MAT Basic app profile")
        if self.entry.data.get(CONF_NAME) != name:
            self._begin_internal_entry_update(self._ble_bond_established)
            self._async_persist_config({**self.entry.data, CONF_NAME: name})
        self._name = name

    def _vmat_unready_link_pending(self) -> bool:
        """Keep an unclosed setup/failed-startup link owned but unusable."""
        client = self._vmat_unready_client
        return client is not None and client.is_connected

    def _persist_capability_snapshot(self) -> None:
        """Persist the live controller's capability snapshot under this bed type.

        No-op when the controller declares no snapshot policy, nothing was
        discovered, or the stored snapshot is unchanged.
        """
        controller = self._controller
        policy = controller.capability_snapshot_policy if controller is not None else None
        if controller is None or policy is None:
            return
        if policy.paired_side_only and not isinstance(self.entry, ChildEntryView):
            return
        snapshot = controller.capability_snapshot()
        if not snapshot:
            return
        capabilities = dict(self.entry.data.get("capabilities") or {})
        if capabilities.get(self._bed_type) == snapshot:
            return
        capabilities[self._bed_type] = snapshot
        if policy.deferred_reload:
            self._begin_internal_entry_update(self._ble_bond_established)
            if self._pending_internal_bond_marker is not None:
                self._pending_capability_reload = True
        self._async_persist_config({**self.entry.data, "capabilities": capabilities})
        if not policy.deferred_reload:
            # The offline controller minted from the stored snapshot is now
            # stale; gate entities off the fresh capabilities until reload.
            self._offline_controller = controller

    def _persist_capability_snapshot_after_operation(self) -> None:
        """Reconcile a snapshot the operation may have resolved, once nothing is queued."""
        controller = self._controller
        policy = controller.capability_snapshot_policy if controller is not None else None
        if policy is not None and policy.after_operations and not self._command_scheduler.has_pending:
            self._persist_capability_snapshot()

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

    def remember_floyd_room(self, room_id: int) -> None:
        """Persist acknowledged BLE membership without reloading mid-service."""
        if self._bed_type != BED_TYPE_KAIDI or not 1 <= room_id <= 0xFFFFFFFF:
            raise ValueError("Invalid Floyd BLE room")
        data = {**self.entry.data, CONF_KAIDI_ROOM_ID: room_id}
        data.pop(CONF_KAIDI_TARGET_VADDR, None)
        self._begin_internal_entry_update(self._ble_bond_established)
        self._offline_controller = None
        self._async_persist_config(data)

    def remember_limoss_remote_capabilities(self, capabilities: Mapping[str, int]) -> None:
        """Persist the reported capability record, which decides the entity layout."""
        from .beds.limoss.remote_state import validate_limoss_remote_state

        if self._bed_type != BED_TYPE_LIMOSS_REMOTE:
            raise ValueError("Invalid Limoss Remote local data")
        previous = validate_limoss_remote_state(self.entry.data.get(CONF_LIMOSS_REMOTE_STATE, {}))
        state = validate_limoss_remote_state({"capabilities": capabilities})
        if state == previous:
            return
        self._begin_internal_entry_update(self._ble_bond_established)
        self._offline_controller = self._controller
        if self._pending_internal_bond_marker is not None:
            self._pending_capability_reload = True
        self._async_persist_config({**self.entry.data, CONF_LIMOSS_REMOTE_STATE: state}, keys={CONF_LIMOSS_REMOTE_STATE})
        self._schedule_pending_capability_reload()

    def remember_limoss_remote_features(self, light: bool, massage: bool) -> None:
        """Reload the exact target's entity layout after completed OFF writes."""
        if self._bed_type != BED_TYPE_LIMOSS_REMOTE or type(light) is not bool or type(massage) is not bool:
            raise ValueError("Invalid Limoss Remote local features")
        changed = {CONF_HAS_LIGHT: light, CONF_HAS_MASSAGE: massage}
        if all(self.entry.data.get(key, False) == value for key, value in changed.items()):
            return
        self._begin_internal_entry_update(self._ble_bond_established)
        self._offline_controller = self._controller or self._offline_controller
        from .beds.limoss.remote import LimossRemoteController

        if isinstance(self._offline_controller, LimossRemoteController):
            self._offline_controller.underbed_light = light
            self._offline_controller.massage = massage
        if self._pending_internal_bond_marker is not None:
            self._pending_capability_reload = True
        self._async_persist_config({**self.entry.data, **changed}, keys=set(changed))
        self._schedule_pending_capability_reload()

    def _merged_vibradorm_app_metadata(self, progress: Mapping[str, str]) -> dict[str, str | None]:
        """Preserve completed fields; omitted values mean not read, never clear."""
        stored = self.entry.data.get(CONF_VIBRADORM_APP_METADATA)
        merged: dict[str, str | None] = {}
        fields = ("model", "firmware", "software", "main_firmware_article")
        if self.entry.data.get(CONF_VIBRADORM_APP_PROFILE) == "vmat":
            fields += ("xmc_status", "opmode", "device_name", "revision_id", "revision_string", "variant")
        for field in fields:
            old = stored.get(field) if isinstance(stored, dict) else None
            if isinstance(old, str):
                merged[field] = old
            if field in progress:
                merged[field] = progress[field]
        return merged

    def remember_vibradorm_app_metadata(self, progress: Mapping[str, str]) -> None:
        """Batch completed diagnostic fields without changing native bond proof."""
        if self._bed_type != BED_TYPE_VIBRADORM_APP:
            raise ValueError("App metadata requires an explicit Vibradorm app profile")
        fields = {"model", "firmware", "software", "main_firmware_article"}
        if self.entry.data.get(CONF_VIBRADORM_APP_PROFILE) == "vmat":
            from .profiles.vibradorm import VMAT_METADATA_FIELDS

            fields.update(VMAT_METADATA_FIELDS)
        if any(field not in fields or not isinstance(value, str) for field, value in progress.items()):
            raise ValueError("App metadata must contain completed string fields")
        if not progress:
            return
        metadata = self._merged_vibradorm_app_metadata(progress)
        if self.entry.data.get(CONF_VIBRADORM_APP_METADATA) == metadata:
            return
        self._begin_internal_entry_update(self._ble_bond_established)
        self._async_persist_config({**self.entry.data, CONF_VIBRADORM_APP_METADATA: metadata})

    @property
    def cancel_command(self) -> asyncio.Event:
        """Return the cancel command event."""
        context = current_command_context()
        if context is not None and context.scheduler_token is self._command_scheduler.token:
            return context.cancel_event
        return self._cancel_command

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

        raw_variant = self._controller_state.get(LINAK_MODEL_VARIANT)
        if raw_variant is None or raw_variant == "unknown":
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

    async def async_shutdown(self) -> None:
        """Stop background tasks and disconnect the coordinator."""
        self._shutting_down = True
        self._cancel_diagnostic_polling()
        self._pending_capability_reload = False
        try:
            await self._async_cancel_position_hydration()
        finally:
            self._cancel_passive_position_reconciliation_task()
            try:
                await self._command_scheduler.async_shutdown()
            finally:
                try:
                    try:
                        runtime = self._pairlink_runtime
                        if runtime is not None:
                            runtime.begin_exit()
                            if runtime._sdk_exit_callback is not None:
                                await runtime._sdk_exit_callback()
                    finally:
                        await self.async_disconnect()
                finally:
                    runtime = self._pairlink_runtime
                    self._pairlink_runtime = None
                    try:
                        if runtime is not None:
                            await runtime.async_shutdown()
                    finally:
                        await self._app_state_store.async_save()

    async def _async_refresh_controller_auth(self) -> None:
        """Refresh protocol auth for controllers that require re-authentication."""
        if self._controller is None:
            return

        await self._controller.async_refresh_auth()

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

                logged_command = command.hex()
                if self._bed_type == BED_TYPE_OCTO and self._controller is not None:
                    trace_payload = self._controller._format_command_trace_payload(command)
                    if trace_payload is not None:
                        logged_command = str(trace_payload.get("hex", "**REDACTED**"))
                _LOGGER.debug(
                    "async_write_command: %s (repeat: %d, delay: %dms)",
                    logged_command,
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

    def _protocol_command_resources(self, resources: frozenset[str]) -> frozenset[str]:
        """Keep Fuzion movements in the same scope as their global halt."""
        if self._bed_type == BED_TYPE_SLEEP_NUMBER and any(
            item == "*"
            or item.startswith("motor:")
            or ":motor:" in item
            or (item.startswith("side:") and item.endswith(":*"))
            for item in resources
        ):
            return command_resources("*")
        return resources

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
        self._command_scheduler.request_cancel(self._protocol_command_resources(command_scope))

    async def async_stop_command(self) -> None:
        """Immediately stop any running command and send stop to bed."""
        _LOGGER.info("Stop requested - cancelling current command")

        if self._bed_type in STARCODE_GROUP_BED_TYPES:
            from .beds.starcode.accessory_group import cancel_group_operations

            # Fence public STOP before the wire wait; retained cleanup has its
            # own scope and must not invalidate the replacing individual move.
            cancel_group_operations(self.hass, self.entry.entry_id)

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
            if getattr(self, "_pairing_transfer_active", False) is True:
                raise ConnectionError("Bed ownership is being transferred")
            controller = self._controller
            disconnected_transport = controller is not None and (
                controller.requires_disconnected_transport is True
            )
            try:
                if disconnected_transport:
                    assert controller is not None
                    if controller.disconnected_transport_ready is not True:
                        raise ConnectionError(
                            "Selected disconnected transport is not ready for STOP"
                        )
                else:
                    if not await self.async_ensure_connected(reset_timer=False):
                        _LOGGER.error("Cannot send stop: not connected to bed")
                        raise ConnectionError("Not connected to bed")

                    # Connecting can rebuild the controller from the selected
                    # path. STOP must use that live instance, not the offline
                    # discovery-time controller captured before the connect.
                    controller = self._controller
                    if controller is None or controller.requires_disconnected_transport is True:
                        raise ConnectionError(
                            "Selected controller changed transport during STOP preparation"
                        )

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
                await controller.stop_all()
                _LOGGER.info("Stop command sent")
            finally:
                if (
                    not disconnected_transport
                    and self._client is not None
                    and self._client.is_connected
                ):
                    # Release promptly after the short burst handoff.
                    if self._disconnect_after_operation_enabled():
                        _LOGGER.debug(
                            "Scheduling disconnect after stop command (disconnect_after_command=True) for %s",
                            self._address,
                        )
                        await self._async_release_command_connection()
                    else:
                        # Otherwise, reset the idle disconnect timer
                        self._reset_disconnect_timer()

    async def _async_prepare_controller_operation(self, operation_name: str) -> BedController:
        """Prepare the selected transport before any controller operation."""
        if getattr(self, "_pairing_transfer_active", False) is True:
            raise ConnectionError("Bed ownership is being transferred")
        controller = self._controller
        if controller is not None and controller.requires_disconnected_transport is True:
            if controller.disconnected_transport_ready is not True:
                _LOGGER.error(
                    "Cannot execute %s: selected disconnected transport is not ready",
                    operation_name,
                )
                raise ConnectionError("Selected disconnected transport is not ready")
            return controller

        if not await self.async_ensure_connected(reset_timer=False):
            _LOGGER.error("Cannot execute %s: not connected to bed", operation_name)
            raise ConnectionError("Not connected to bed")

        # async_ensure_connected may resolve a different usable path and
        # replace the offline controller. Return only the controller bound to
        # the connection that was actually established.
        controller = self._controller
        if controller is None or controller.requires_disconnected_transport is True:
            _LOGGER.error(
                "Cannot execute %s: current central controller is unavailable after connect",
                operation_name,
            )
            raise ConnectionError(
                f"Selected controller changed transport during {operation_name} preparation"
            )
        await self._async_refresh_controller_auth()
        if self._bed_type == BED_TYPE_OCTO:
            from .beds.octo.runtime import octo_controller

            octo = octo_controller(controller)
            if octo is not None:
                await octo.async_wait_for_pin_acceptance(self.cancel_command)
        return controller

    async def _async_finish_controller_operation(
        self,
        *,
        entry_cancel_count: int,
        cancel_event: asyncio.Event,
        scheduler_managed: bool,
        skip_disconnect: bool,
        operation_name: str,
        disconnected_transport: bool = False,
    ) -> None:
        """Handle disconnect timer reset or disconnect after an operation completes."""
        if disconnected_transport:
            return

        # Persist a snapshot the command resolved (a cold Linak link defers its
        # actuator mask) without interrupting a queued operation.
        self._persist_capability_snapshot_after_operation()

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
                "Scheduling disconnect after %s (disconnect_after_command=True) for %s",
                operation_name,
                self._address,
            )
            await self._async_release_command_connection()
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
        caller_task = asyncio.current_task()
        cancel_wait_task = asyncio.create_task(cancel_event.wait())
        try:
            done, pending = await asyncio.wait(
                {operation_task, cancel_wait_task},
                return_when=asyncio.FIRST_COMPLETED,
            )

            context = current_command_context()
            # A lease running out is a hold's normal end (#483). Only
            # controllers whose loop leaves on the event may hold, so let the
            # operation finish its release schedule instead of cutting it short.
            lease_ended = (
                cancel_wait_task in done
                and context is not None
                and context.cancel_event is cancel_event
                and context.cancel_reason is CommandOutcome.EXPIRED
            )
            for task in pending:
                if not (lease_ended and task is operation_task):
                    task.cancel()
            for task in pending:
                if task is operation_task and lease_ended:
                    continue
                try:
                    await task
                except asyncio.CancelledError:
                    if caller_task is not None and caller_task.cancelling():
                        raise

            if cancel_wait_task in done:
                _LOGGER.debug("Controller %s cancelled during execution", operation_name)
                if not operation_task.done() and not lease_ended:
                    operation_task.cancel()
                try:
                    await operation_task
                except asyncio.CancelledError:
                    if caller_task is not None and caller_task.cancelling():
                        raise
                if raise_on_cancel:
                    raise asyncio.CancelledError
                return None

            return operation_task.result()
        finally:
            # Cancel both children before draining either, even if the caller exits.
            for task in (operation_task, cancel_wait_task):
                if not task.done():
                    task.cancel()
            for task in (operation_task, cancel_wait_task):
                if task.done():
                    continue
                try:
                    await task
                except asyncio.CancelledError:
                    if caller_task is not None and caller_task.cancelling():
                        raise

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
        preserve_idle_deadline: bool = False,
    ) -> T | None:
        """Execute a controller operation with shared locking and connection handling."""
        if cancel_running:
            self._cancel_counter += 1
            self._cancel_command.set()

        entry_cancel_count = self._cancel_counter
        async with self._command_lock:
            # Background reads can inherit a command context while it is active,
            # then acquire this lock after that command has finished. Resolve
            # ownership here so their controller sees the same cancellation event.
            command_context = current_command_context()
            scheduler_managed = bool(
                command_context is not None
                and command_context.scheduler_token is self._command_scheduler.token
            )
            legacy_exclusive = bool(
                scheduler_managed
                and command_context is not None
                and "*" in command_context.resources
            )
            cancel_event = self.cancel_command
            controller_before_prepare = self._controller
            disconnected_transport = (
                controller_before_prepare is not None
                and controller_before_prepare.requires_disconnected_transport is True
            )
            if not preserve_idle_deadline:
                self._cancel_disconnect_timer()

            cancelled_while_waiting = (
                cancel_event.is_set()
                or (legacy_exclusive and self._cancel_counter > entry_cancel_count)
                if scheduler_managed
                else self._cancel_counter > entry_cancel_count
            )
            if preemptible and cancelled_while_waiting:
                _LOGGER.debug("Controller %s cancelled while waiting for lock", operation_name)
                if (
                    not preserve_idle_deadline
                    and self._client is not None
                    and self._client.is_connected
                ):
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
                if preserve_idle_deadline:
                    # A live diagnostic read must not wait on connect/auth work
                    # that could reopen a link after the idle deadline expires.
                    controller = self._controller
                    if controller is None:
                        raise ConnectionError("Diagnostic query requires a live receiver")
                    disconnected_transport = (
                        controller.requires_disconnected_transport is True
                    )
                    if disconnected_transport:
                        if controller.disconnected_transport_ready is not True:
                            raise ConnectionError(
                                "Selected disconnected transport is not ready"
                            )
                    elif not self.is_connected:
                        raise ConnectionError("Diagnostic query requires a live receiver")
                else:
                    controller = await self._async_prepare_controller_operation(operation_name)
                    # Capture the role chosen during preparation. It remains the
                    # owner of operation cleanup even if readiness changes later.
                    disconnected_transport = (
                        controller.requires_disconnected_transport is True
                    )
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
                    context = current_command_context()
                    if (
                        context is not None
                        and context.lease is not None
                        and context.scheduler_token is self._command_scheduler.token
                    ):
                        # A leased hold's ceiling is clock time from here, after
                        # connecting, whatever each of its writes takes (#483).
                        ceiling_ms = controller.execution.hold_ceiling_ms or HOLD_CEILING_MS
                        self._command_scheduler.bound_hold(context, ceiling_ms / 1000)
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
                    # A command that worked closes the stale-cache episode. Startup
                    # alone does not: some beds start without any authenticated
                    # access, and a missing bond must still reach the repair.
                    # Neither does a command cancelled before it could finish.
                    if not operation_task.cancelled():
                        self._stale_gatt_retry_sources.clear()
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
                    and not self._command_scheduler.has_pending
                ):
                    if self._position_mode == POSITION_MODE_ACCURACY or (
                        self._disconnect_after_operation_enabled() and not skip_disconnect
                    ):
                        await self._async_wait_for_controller_operation(
                            asyncio.create_task(self._async_read_positions()),
                            cancel_event=cancel_event,
                            operation_name="final position read",
                            raise_on_cancel=False,
                        )
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
                    encrypt_in_place = self._can_encrypt_link_in_place()
                    await self._async_handle_ble_authentication_error(
                        err, retain_link=True, defer_pairing_issue=encrypt_in_place
                    )
                    if encrypt_in_place:
                        await self._async_encrypt_link_in_place()
                raise
            except _CONTROLLER_OPERATION_RECOVERY_EXCEPTIONS:
                if (
                    not preserve_idle_deadline
                    and self._client is not None
                    and self._client.is_connected
                    and not self._disconnect_after_operation_enabled()
                ):
                    self._reset_disconnect_timer()
                raise
            finally:
                if not preserve_idle_deadline:
                    await self._async_finish_controller_operation(
                        entry_cancel_count=entry_cancel_count,
                        cancel_event=cancel_event,
                        scheduler_managed=scheduler_managed,
                        skip_disconnect=skip_disconnect,
                        operation_name=operation_name,
                        disconnected_transport=disconnected_transport,
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
        read_positions_after_operation: bool = True,
        expected_stop_epoch: int | None = None,
        lease: HoldLease | None = None,
    ) -> None:
        """Execute an opaque controller command through the device scheduler.

        With a ``lease`` the command is a ``CommandKind.HOLD``: a renewal of
        the live hold of that generation returns at once, and the hold ends at
        the lease deadline through its cancel event (#483).
        """

        async def operation() -> None:
            await self._async_execute_controller_operation(
                command_fn,
                cancel_running=False,
                skip_disconnect=skip_disconnect,
                raise_on_lock_cancel=False,
                preemptible=True,
                enable_position_polling=True,
                read_positions_after_operation=read_positions_after_operation,
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
            controller_command=command_fn,
            expected_stop_epoch=expected_stop_epoch,
            lease=lease,
        )

    def stream_resources(self) -> frozenset[str] | None:
        """Scheduler resources the live controller may merge into one stream (#516)."""
        controller = self.capability_controller
        if controller is None or not controller.execution.concurrent:
            return None
        return self._protocol_command_resources(
            command_resources(*controller.execution.concurrent)
        )

    def stop_stream_member(self, resource: str) -> bool:
        """End a motor's merged-stream member for a motor-scoped STOP (#516).

        Returns False when no live stream owns the motor, so the caller sends
        its ordinary STOP. The member's own cleanup runs in the streamer, and the
        other members keep moving.
        """
        resources = self._protocol_command_resources(command_resources(resource))
        if not self._command_scheduler.stream_owns(resources):
            return False
        self._command_scheduler.finish_stop(self._command_scheduler.request_stop(resources))
        return True

    async def async_stop_motor(
        self,
        stop_fn: Callable[[BedController], Coroutine[Any, Any, None]],
        resource: str,
        *,
        stream_member: bool = True,
    ) -> None:
        """Stop a motor at once, never behind another motor's command (#516).

        ``resource`` is the STOP's scope. With ``stream_member``, a live merged
        stream that owns the motor ends only that member, and its cleanup runs
        in the streamer. Otherwise this is a STOP admission: it pre-empts the
        motion holding the writer, whichever motor of the bed that is, then
        runs ``stop_fn`` as an ordinary command runs it.
        """
        if stream_member and self.stop_stream_member(resource):
            return
        if self._bed_type in STARCODE_GROUP_BED_TYPES:
            from .beds.starcode.accessory_group import cancel_group_operations

            cancel_group_operations(self.hass, self.entry.entry_id)
        # Keep preemptible non-scheduler work responsive, as every STOP does.
        self._cancel_counter += 1
        self._cancel_command.set()

        async def stop_operation(_context: CommandContext) -> None:
            await self._async_execute_controller_operation(
                stop_fn,
                cancel_running=False,
                skip_disconnect=False,
                raise_on_lock_cancel=False,
                preemptible=True,
                enable_position_polling=True,
                read_positions_after_operation=True,
                operation_name="motor stop",
            )

        stop_task = self._command_scheduler.admit_stop(
            stop_operation, self._protocol_command_resources(command_resources(resource))
        )
        try:
            await asyncio.shield(stop_task)
        except asyncio.CancelledError:
            # An admitted STOP outlives its caller, as a bed-wide STOP does.
            try:
                await stop_task
            except Exception:
                _LOGGER.exception("Motor STOP failed after its caller was cancelled")
            raise

    async def async_execute_stream_member(
        self,
        *,
        motor: str,
        resource: str,
        action: str,
        duration_s: float,
        ceiling_s: float | None = None,
        lease: HoldLease | None = None,
        expected_stop_epoch: int | None = None,
        on_wire: Callable[[], None] | None = None,
        on_left: Callable[[float | None], None] | None = None,
    ) -> CommandOutcome | None:
        """Run a held or timed motion as a member of the merged stream (#516).

        The caller has checked that ``resource`` is one of the controller's
        concurrent motors. The streamer owns the wire through the ordinary
        controller-operation lane, so connection, locking and STOP preemption
        work as for any command.
        """
        resources = self.stream_resources()
        if resources is None:
            raise ValueError("This controller does not declare concurrent motors")
        context = current_command_context()
        if context is not None and context.scheduler_token is self._command_scheduler.token:
            # A streamer queues behind the reservation this call runs in.
            raise ValueError("A stream member cannot start inside another command")
        loop = asyncio.get_running_loop()
        member = StreamMember(
            motor=motor,
            resource=resource,
            action=action,
            # A lease is a dead-man deadline from this call; a timed move's
            # budget starts with its first written tick.
            deadline=loop.time() + duration_s if lease is not None else math.inf,
            duration_s=None if lease is not None else duration_s,
            lease=lease,
            ceiling=None if ceiling_s is None else loop.time() + ceiling_s,
            on_wire=on_wire,
            on_left=on_left,
        )

        async def runner(body: Callable[[StreamDriver], Awaitable[None]]) -> None:
            async def stream(controller: BedController) -> None:
                await body(controller)

            await self._async_execute_controller_operation(
                stream,
                cancel_running=False,
                skip_disconnect=False,
                raise_on_lock_cancel=False,
                preemptible=True,
                enable_position_polling=False,
                read_positions_after_operation=False,
                operation_name="merged stream",
            )

        return await self._command_scheduler.execute_stream_member(
            member, resources, runner, expected_stop_epoch=expected_stop_epoch
        )

    def claim_hold_lease(
        self,
        lease: HoldLease,
        *,
        resource: str | None = None,
        resources: Collection[str] | None = None,
        reserve: bool = True,
    ) -> HoldClaim:
        """Renew, reserve or refuse a hold lease on the command's resources."""
        return self._command_scheduler.claim_hold(
            lease, self._hold_resources(resource, resources), reserve=reserve
        )

    def release_hold_claim(
        self,
        lease: HoldLease,
        *,
        resource: str | None = None,
        resources: Collection[str] | None = None,
    ) -> None:
        """End a hold reservation that never reached admission."""
        self._command_scheduler.release_hold_claim(
            lease, self._hold_resources(resource, resources)
        )

    def _hold_resources(
        self, resource: str | None, resources: Collection[str] | None
    ) -> frozenset[str]:
        if resource is not None and resources is not None:
            raise ValueError("Pass resource or resources, not both")
        return self._protocol_command_resources(
            command_resources(*resources)
            if resources is not None
            else command_resources(resource or "*")
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
        controller_command: Callable[[BedController], Awaitable[None]] | None = None,
        expected_stop_epoch: int | None = None,
        lease: HoldLease | None = None,
    ) -> None:
        """Schedule an operation, or run inline inside this scheduler's reservation."""
        if (
            expected_stop_epoch is not None
            and self._command_scheduler.stop_epoch != expected_stop_epoch
        ):
            return
        context = current_command_context()
        if context is not None and context.scheduler_token is self._command_scheduler.token:
            if lease is not None and not self._command_scheduler.bind_hold_inline(
                context, lease, self._hold_resources(resource, resources)
            ):
                return
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

        if self._bed_type in STARCODE_GROUP_BED_TYPES:
            from .beds.starcode.accessory_group import prepare_individual_command

            settled_group = await prepare_individual_command(self, controller_command)
            if settled_group and expected_stop_epoch is not None:
                # The group helper rejects public STOP during its await. Its
                # own settled cleanup STOPs precede this individual admission.
                expected_stop_epoch = self._command_scheduler.stop_epoch

        if (
            expected_stop_epoch is not None
            and self._command_scheduler.stop_epoch != expected_stop_epoch
        ):
            return

        if (
            expected_stop_epoch is not None
            and self._command_scheduler.stop_epoch != expected_stop_epoch
        ):
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
            expected_stop_epoch=expected_stop_epoch,
            lease=lease,
        )
        await self._command_scheduler.execute(
            intent, expected_stop_epoch=expected_stop_epoch
        )

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
        expected_stop_epoch: int | None = None,
        lease: HoldLease | None = None,
    ) -> CommandIntent:
        """Build one device intent while preserving legacy cancellation signals."""
        if resource is not None and resources is not None:
            raise ValueError("Pass resource or resources, not both")
        command_scope = (
            command_resources(*resources)
            if resources is not None
            else command_resources(resource or "*")
        )
        if cancel_running and (
            expected_stop_epoch is None
            or self._command_scheduler.stop_epoch == expected_stop_epoch
        ):
            # Keep preemptible non-scheduler work (queries and legacy direct
            # writes) responsive. Scheduler-owned operations use their private
            # ticket event and are replaced only when resources overlap.
            self._cancel_counter += 1
            self._cancel_command.set()

        async def scheduled(_context: CommandContext) -> None:
            await operation()

        return CommandIntent(
            scheduled,
            resources=self._protocol_command_resources(command_scope),
            kind=CommandKind.HOLD if lease is not None else kind,
            replacement_key=(resource or "*") if resources is None else None,
            cancel_running=cancel_running,
            group_id=group_id,
            pulse_count=pulse_count,
            pulse_delay_ms=pulse_delay_ms,
            lease=lease,
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
        expected_stop_epoch: int | None = None,
    ) -> CommandHandle:
        """Queue a linked operation without allowing controller execution yet."""
        intent = self._build_command_intent(
            operation,
            resource=resource,
            resources=resources,
            kind=kind,
            cancel_running=cancel_running,
            group_id=group_id,
            expected_stop_epoch=expected_stop_epoch,
        )
        return await self._command_scheduler.enqueue(
            intent,
            prepared=True,
            expected_stop_epoch=expected_stop_epoch,
        )

    async def async_validate_linked_command_readiness(self) -> None:
        """Prepare actual GATT without starting a reserved linked command."""
        if not await self.async_ensure_connected(reset_timer=False):
            raise ConnectionError("Linked receiver is unavailable")
        controller = self._controller
        if controller is None or controller.requires_linked_live_readiness is not True:
            raise ValueError("Linked readiness requires an explicitly compatible profile")
        await controller.async_validate_linked_readiness()
        if self._controller is not controller or not self.is_connected:
            raise ConnectionError("Linked session changed during readiness validation")

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
            resources=self._protocol_command_resources(command_resources(*resources)),
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
        preserve_idle_deadline: bool = False,
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
            preserve_idle_deadline=preserve_idle_deadline,
        )
        return cast(T, result)

    def _cancel_diagnostic_polling(self) -> None:
        """End live-link queries and invalidate this connection's observed values."""
        task = self._diagnostic_poll_task
        self._diagnostic_poll_task = None
        if task is not None and task is not asyncio.current_task():
            task.cancel()
        advertisement_task = self._diagnostic_advertisement_task
        self._diagnostic_advertisement_task = None
        if advertisement_task is not None and advertisement_task is not asyncio.current_task():
            advertisement_task.cancel()
        if self._controller is not None:
            self._controller.invalidate_diagnostics()

    def _refresh_diagnostic_polling_schedule(self) -> None:
        self._cancel_diagnostic_polling()
        controller = self._controller
        if controller is None or controller.diagnostic_poll_interval is None:
            return
        interval = controller.diagnostic_poll_interval
        if not math.isfinite(interval) or interval <= 0:
            _LOGGER.warning("Ignoring invalid diagnostic polling interval %s", interval)
            return
        self._diagnostic_poll_task = self.entry.async_create_background_task(
            self.hass,
            self._async_diagnostic_poll_loop(controller, interval),
            name=f"adjustable_bed_diagnostics_{self._address}",
        )
        sample_interval = controller.diagnostic_advertisement_interval
        if sample_interval is not None:
            if not math.isfinite(sample_interval) or sample_interval <= 0:
                _LOGGER.warning(
                    "Ignoring invalid advertisement diagnostic interval %s", sample_interval
                )
                return
            self._diagnostic_advertisement_task = self.entry.async_create_background_task(
                self.hass,
                self._async_diagnostic_advertisement_loop(controller, sample_interval),
                name=f"adjustable_bed_advertisement_diagnostics_{self._address}",
            )

    async def _async_diagnostic_advertisement_loop(
        self, controller: BedController, interval: float
    ) -> None:
        """Sample retained HA observations without BLE queries or idle-timer renewal."""
        try:
            while self._controller is controller and self.is_connected and not self._shutting_down:
                if self._connecting:
                    await asyncio.sleep(0.1)
                    continue
                info = bluetooth.async_last_service_info(self.hass, self._address, connectable=True)
                controller.update_advertisement_diagnostics(
                    info.rssi if info is not None and info.rssi > -127 else None,
                    info.source if info is not None else None,
                    info.time if info is not None else None,
                )
                await asyncio.sleep(interval)
        finally:
            if self._diagnostic_advertisement_task is asyncio.current_task():
                self._diagnostic_advertisement_task = None

    async def _async_diagnostic_poll_loop(self, controller: BedController, interval: float) -> None:
        """Refresh only a current live session, with command priority and no idle renewal."""

        def available() -> bool:
            return (
                self._controller is controller
                and self._client is not None
                and self._client.is_connected
                and not self._connecting
                and not self._shutting_down
            )

        try:
            while (
                self._controller is controller
                and self._client is not None
                and self._client.is_connected
            ):
                if self._connecting:
                    await asyncio.sleep(0.1)
                    continue
                if (
                    available()
                    and not self._command_lock.locked()
                    and not self._command_scheduler.has_pending
                ):
                    next_attempt = asyncio.get_running_loop().time() + interval
                    try:
                        await self.async_execute_controller_query(
                            lambda current: current.async_refresh_diagnostics(),
                            cancel_running=False,
                            skip_disconnect=True,
                            preemptible=True,
                            run_if=available,
                            preserve_idle_deadline=True,
                        )
                    except asyncio.CancelledError:
                        current_task = asyncio.current_task()
                        if current_task is not None and current_task.cancelling():
                            raise
                    except Exception as error:
                        _LOGGER.debug("Background diagnostic refresh failed: %s", error)
                    await asyncio.sleep(max(0, next_attempt - asyncio.get_running_loop().time()))
                else:
                    await asyncio.sleep(interval)
        finally:
            if self._diagnostic_poll_task is asyncio.current_task():
                self._diagnostic_poll_task = None

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

    def register_controller_state_callback(
        self, callback_fn: Callable[[ControllerState], None]
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

    def _readable_light_state_required_keys(self) -> set[AnyStateKey]:
        """Return the readable light-state keys expected for the current controller."""
        controller = self._controller
        if controller is None or not controller.supports_under_bed_lights:
            return set()

        required_keys: set[AnyStateKey] = set()
        if controller.supports_discrete_light_control:
            required_keys.add(UNDER_BED_LIGHTS_ON)
        if controller.supports_light_level_control:
            required_keys.add(LIGHT_LEVEL)
        if controller.supports_light_timer:
            required_keys.update({LIGHT_TIMER_MINUTES, LIGHT_TIMER_OPTION})
        return required_keys

    @callback
    def _mark_controller_state_refresh_complete(self) -> None:
        """Mark readable light-state hydration complete for the current connection."""
        self._controller_state_refresh_completed = True
        self._controller_state_refresh_retry_count = 0

    @callback
    def _schedule_controller_state_refresh_retry(self) -> None:
        """Schedule another readable light-state refresh after a transient failure."""
        if self._disconnect_after_operation_enabled():
            # Background retries must not keep renewing the remote handoff.
            return
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
    def _merge_controller_light_state(self, state: tuple[StateUpdate, ...]) -> None:
        """Merge readable light-state values into coordinator state."""
        # The last update of a key wins, as it does when published.
        latest = {update.key: update for update in state}
        self.handle_controller_state_updates(
            *(
                update
                for update in latest.values()
                if self._controller_state.get(update.key) != update.value
            )
        )
        if not self._should_refresh_readable_light_state(force=False):
            self._cancel_controller_state_refresh_retry()

    async def _async_refresh_readable_light_state(self) -> None:
        """Read light state from the controller and merge any fresh values."""
        controller = self._controller
        if controller is None:
            return

        state: tuple[StateUpdate, ...] | None = None
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

            async def _read_light_state(controller: BedController) -> tuple[StateUpdate, ...]:
                return await controller.read_light_state()

            async with asyncio.timeout(_READABLE_LIGHT_STATE_TIMEOUT):
                state = await self.async_execute_controller_query(
                    _read_light_state,
                    cancel_running=False,
                    skip_disconnect=True,
                    run_if=lambda: self._should_refresh_readable_light_state(force=False),
                )
            if state is not None:
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
    def handle_controller_state_update[T](self, key: StateKey[T], value: T) -> None:
        """Store a single controller state value and notify listeners."""
        self.handle_controller_state_updates(key(value))

    async def async_set_furnimove_massage_duration(self, minutes: int) -> None:
        """Serialize an app preference without reserving a Bluetooth connection."""
        async with self._command_lock:
            await self.async_prime_offline_controller()
            controller = self.capability_controller
            if self._bed_type != BED_TYPE_FURNIMOVE or controller is None:
                raise ValueError("No selected FurniMove handset is available")
            # The capability controller may be an older instance than the one that
            # last saved; hand it the current preferences before changing one.
            await self._async_restore_app_state(controller)
            await controller.set_massage_timer(minutes)

    async def _async_restore_app_state(self, controller: BedController | None) -> None:
        """Hand a new controller the app-local state stored for this bed and profile."""
        if controller is None or controller.persisted_app_state is None:
            return
        slot = app_state_slot(
            self._bed_type, self._protocol_variant, controller.persisted_app_state_key
        )
        stored = await self._app_state_store.async_slot(slot)
        self._app_state_restoring = True
        try:
            try:
                controller.restore_persisted_app_state(stored)
            except ValueError, TypeError:
                _LOGGER.warning("Ignoring invalid stored app state for %s", self._address)
                controller.restore_persisted_app_state({})
            self._app_state_slots[controller] = slot
            self._app_state_store.update(slot, controller.persisted_app_state or {})
        finally:
            self._app_state_restoring = False

    def save_app_state(self, controller: BedController | None = None) -> None:
        """Schedule a save of a restored controller's app-local state.

        Publishing controller state saves the capability controller's state.
        A controller whose state lives in a shared session saves itself, since
        it may be an older instance than the capability controller, or the
        coordinator may have none after a disconnect.
        """
        controller = controller or self.capability_controller
        if controller is None or self._app_state_restoring:
            return
        slot = self._app_state_slots.get(controller)
        state = controller.persisted_app_state if slot is not None else None
        if slot is not None and state is not None:
            self._app_state_store.update(slot, state)

    async def async_write_app_state(
        self, controller: BedController, state: Mapping[str, Any]
    ) -> None:
        """Write ``controller``'s app-local state now; raise if it is not durable."""
        slot = self._app_state_slots.get(controller) or app_state_slot(
            self._bed_type, self._protocol_variant, controller.persisted_app_state_key
        )
        await self._app_state_store.async_write(slot, state)

    @callback
    def handle_controller_state_updates(self, *updates: StateUpdate) -> None:
        """Store ``KEY(value)`` updates and notify listeners."""
        if not updates:
            return

        self._controller_state.update((update.key, update.value) for update in updates)
        self.save_app_state()
        for callback_fn in list(self._controller_state_callbacks):
            try:
                callback_fn(self._controller_state)
            except Exception as err:
                _LOGGER.warning("Controller state callback error: %s", err)


