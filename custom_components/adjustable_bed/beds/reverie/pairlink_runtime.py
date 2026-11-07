"""Entry-owned Pairlink protocol/session state for the Reverie BLE routes.

This module contains no radio or D-Bus lifecycle. It reduces accepted raw
Pairlink frames into typed effects; the owning controller performs those
effects through its already-selected central or local transport.
"""

from __future__ import annotations

import secrets
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Literal

from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from homeassistant.const import CONF_ADDRESS

from ...const import (
    CONF_PAIRLINK_HOME_ID,
    CONF_PAIRLINK_PASSWORD_HEX,
    CONF_PAIRLINK_PASSWORD_TEXT,
    CONF_PAIRLINK_ROLE,
    PAIRLINK_ROLE_CENTRAL,
    PAIRLINK_ROLE_PERIPHERAL,
)
from .pairlink_protocol import (
    PAIRLINK_BROADCAST_ADDRESS,
    PairlinkSignGate,
    _encrypt_padded_aes_ecb,
    cmac_aes,
    decrypt_login_block,
    decrypt_user_frame,
    derive_event_key_from_seed,
    derive_event_key_index,
    encrypt_login_block,
    normalize_mac,
)
from .pairlink_transport import (
    PairlinkHostAdapterInventoryEntry,
    PairlinkPeerIdentity,
    PairlinkPeerLifecycleCallback,
    PairlinkPeerLifecycleEvent,
    PairlinkPeerLifecycleKind,
    PairlinkPeerWriteCallback,
    PairlinkPeripheralBackend,
    PairlinkPeripheralProfile,
)

if TYPE_CHECKING:
    from .pairlink_sdk_storage import PairlinkSdkState

DEFAULT_PAIRLINK_PASSWORD_TEXT = "1122"
DEFAULT_PAIRLINK_HOME_ID = 5566
_ZERO4 = bytes(4)
_ZERO16 = bytes(16)
_MAX_SAFE_PACKET_LENGTH = 255


class PairlinkRole(StrEnum):
    """The selected transport role for one config-entry runtime."""

    CENTRAL = "central"
    PERIPHERAL = "peripheral"


class PairlinkHomeIdOrigin(StrEnum):
    """Provenance retained for the exact four HomeID bytes."""

    ADVERTISEMENT = "advertisement"
    EXPLICIT_CONFIG = "explicit_config"
    DECLARED_HA_POLICY = "declared_ha_policy"


@dataclass(frozen=True, slots=True)
class PairlinkCredentials:
    """Validated runtime credential bytes, with secrets excluded from repr."""

    home_id_le: bytes
    password: bytes = field(repr=False)
    home_id_origin: PairlinkHomeIdOrigin
    password_origin: Literal["utf8_text", "exact_hex"] = "utf8_text"

    def __post_init__(self) -> None:
        if type(self.home_id_le) is not bytes or len(self.home_id_le) != 4:
            raise ValueError("Pairlink HomeID must be exactly four little-endian bytes")
        if type(self.password) is not bytes or len(self.password) != 4:
            raise ValueError("Pairlink password must contain exactly four bytes")
        if not isinstance(self.home_id_origin, PairlinkHomeIdOrigin):
            raise TypeError("Pairlink HomeID provenance must use its typed enum")
        if self.password_origin not in ("utf8_text", "exact_hex"):
            raise ValueError("Unsupported Pairlink password provenance")

    @classmethod
    def from_inputs(
        cls,
        home_id: int,
        *,
        home_id_origin: PairlinkHomeIdOrigin,
        password_text: str | None = None,
        password_hex: str | None = None,
    ) -> PairlinkCredentials:
        """Apply the explicit HA UTF-8 or exact-byte policy without fallback."""
        home_id_le = normalize_home_id(home_id)
        password, password_origin = encode_pairlink_password(
            password_text=password_text,
            password_hex=password_hex,
        )
        return cls(home_id_le, password, home_id_origin, password_origin)


def encode_pairlink_password(
    *,
    password_text: str | None = None,
    password_hex: str | None = None,
) -> tuple[bytes, Literal["utf8_text", "exact_hex"]]:
    """Validate the declared HA UTF-8/default or exact four-byte override policy."""
    text = DEFAULT_PAIRLINK_PASSWORD_TEXT if password_text is None else password_text
    if not isinstance(text, str):
        raise TypeError("Pairlink password text must be a string")
    try:
        encoded_text = text.encode("utf-8")
    except UnicodeEncodeError:
        raise ValueError("Pairlink password text cannot be encoded as UTF-8") from None
    if len(encoded_text) != 4:
        raise ValueError("Pairlink UTF-8 password text must encode to exactly four bytes")
    if password_hex is None:
        return encoded_text, "utf8_text"
    if not isinstance(password_hex, str) or len(password_hex) != 8:
        raise ValueError("Pairlink password hex must contain exactly eight digits")
    if any(character not in "0123456789abcdefABCDEF" for character in password_hex):
        raise ValueError("Pairlink password hex must contain exactly eight digits")
    if text != DEFAULT_PAIRLINK_PASSWORD_TEXT:
        raise ValueError("Pairlink password hex overrides only the default text value")
    return bytes.fromhex(password_hex), "exact_hex"


def normalize_home_id(home_id: int) -> bytes:
    """Normalize Java signed or unsigned HomeID bits to the exact LE4 value."""
    if isinstance(home_id, bool) or not isinstance(home_id, int):
        raise TypeError("Pairlink HomeID must be an integer")
    if not -(1 << 31) <= home_id <= 0xFFFFFFFF:
        raise ValueError("Pairlink HomeID must fit a signed or unsigned four-byte value")
    return (home_id & 0xFFFFFFFF).to_bytes(4, "little")


def create_pairlink_runtime_for_entry(
    entry_data: Mapping[str, object],
    entry_options: Mapping[str, object],
    *,
    manufacturer_data: dict[int, bytes] | None,
) -> PairlinkRuntime:
    """Create one runtime from explicit entry policy and accepted advertisement fields."""
    from .pairlink_profile import (
        generate_pairlink_local_join_bt_mac,
    )

    role, target_mac, credentials = _resolve_pairlink_entry_configuration(
        entry_data,
        entry_options,
        manufacturer_data=manufacturer_data,
    )
    return PairlinkRuntime(
        credentials,
        role=role,
        target_mac=target_mac if role is PairlinkRole.CENTRAL else None,
        local_join_bt_mac=generate_pairlink_local_join_bt_mac(),
    )


def _resolve_pairlink_entry_configuration(
    entry_data: Mapping[str, object],
    entry_options: Mapping[str, object],
    *,
    manufacturer_data: dict[int, bytes] | None,
    previous_credentials: PairlinkCredentials | None = None,
) -> tuple[PairlinkRole, str | None, PairlinkCredentials]:
    """Resolve current inputs without replacing an accepted ad value with missing data."""
    from .pairlink_profile import parse_pairlink_manufacturer_data

    data = {**entry_data, **entry_options}
    role_value = data.get(CONF_PAIRLINK_ROLE, PAIRLINK_ROLE_CENTRAL)
    if role_value == PAIRLINK_ROLE_CENTRAL:
        role = PairlinkRole.CENTRAL
    elif role_value == PAIRLINK_ROLE_PERIPHERAL:
        role = PairlinkRole.PERIPHERAL
    else:
        raise ValueError("Pairlink role must be central or local peripheral")

    explicit_home_id = data.get(CONF_PAIRLINK_HOME_ID)
    if explicit_home_id == "":
        explicit_home_id = None
    elif isinstance(explicit_home_id, str):
        try:
            explicit_home_id = int(explicit_home_id.strip(), 10)
        except ValueError:
            raise ValueError("Pairlink HomeID must be a decimal integer") from None
    if explicit_home_id is not None:
        if isinstance(explicit_home_id, bool) or not isinstance(explicit_home_id, int):
            raise ValueError("Pairlink HomeID must be an integer")
        home_id = explicit_home_id
        home_origin = PairlinkHomeIdOrigin.EXPLICIT_CONFIG
    else:
        advertisement = parse_pairlink_manufacturer_data(manufacturer_data)
        if advertisement is None or advertisement.mesh_id is None:
            if (
                previous_credentials is not None
                and previous_credentials.home_id_origin is PairlinkHomeIdOrigin.ADVERTISEMENT
            ):
                home_id = int.from_bytes(previous_credentials.home_id_le, "little")
                home_origin = PairlinkHomeIdOrigin.ADVERTISEMENT
            else:
                home_id = DEFAULT_PAIRLINK_HOME_ID
                home_origin = PairlinkHomeIdOrigin.DECLARED_HA_POLICY
        else:
            home_id = advertisement.mesh_id
            home_origin = PairlinkHomeIdOrigin.ADVERTISEMENT

    password_text = data.get(CONF_PAIRLINK_PASSWORD_TEXT)
    if password_text is not None and not isinstance(password_text, str):
        raise ValueError("Pairlink password text must be a string")
    password_hex = data.get(CONF_PAIRLINK_PASSWORD_HEX)
    if password_hex is not None and not isinstance(password_hex, str):
        raise ValueError("Pairlink password hex must be a string")
    credentials = PairlinkCredentials.from_inputs(
        home_id,
        home_id_origin=home_origin,
        password_text=password_text,
        password_hex=password_hex or None,
    )
    target_mac = data.get(CONF_ADDRESS)
    if target_mac is not None and not isinstance(target_mac, str):
        raise ValueError("Pairlink target address must be text")
    return role, target_mac, credentials


@dataclass(frozen=True, slots=True)
class PairlinkSendSnapshot:
    """Immutable send inputs prepared from one current source session."""

    epoch: int
    state_generation: int
    role: PairlinkRole
    target_mac: str
    peer: PairlinkPeerIdentity | None
    own_virtual_address: bytes
    event_key: bytes = field(repr=False)
    device_key: bytes | None = field(repr=False)
    device_type: int
    mtu: int
    peer_generation: int | None = None
    peer_state_generation: int | None = None


@dataclass(frozen=True, slots=True)
class PairlinkSendReply:
    """One native login reply that must use its current transport target."""

    epoch: int
    target_mac: str
    peer: PairlinkPeerIdentity | None
    payload: bytes = field(repr=False)


@dataclass(frozen=True, slots=True)
class PairlinkWelcome:
    """An accepted local welcome that starts the source backup check."""

    epoch: int
    target_mac: str
    peer: PairlinkPeerIdentity


@dataclass(frozen=True, slots=True)
class PairlinkComfortPlan:
    """One request reduced against a single current Pairlink session snapshot."""

    owner: PairlinkRuntime = field(repr=False, compare=False)
    snapshot: PairlinkSendSnapshot
    request_signature: tuple[object, ...]
    payloads: tuple[bytes, ...]
    omitted_fields: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PairlinkMeshEvent:
    """Decoded event delivered to the controller's concrete state consumer."""

    epoch: int
    source_mac: str
    peer: PairlinkPeerIdentity | None
    event_type: int
    event_data: bytes
    broadcast: bool


@dataclass(frozen=True, slots=True)
class PairlinkSdkFrame:
    """A non-preempted decoded frame for the private SDK response consumer."""

    epoch: int
    peer: PairlinkPeerIdentity | None
    frame: bytes
    source_mac: str


@dataclass(frozen=True, slots=True)
class PairlinkSdkNative:
    """A current native receive/lifecycle continuation, never a mesh packet."""

    epoch: int
    source_mac: str
    peer: PairlinkPeerIdentity | None
    kind: Literal["network_info", "fingerprint"]
    packet: bytes


@dataclass(frozen=True, slots=True)
class PairlinkMeshStatusEvent:
    """A source library callback, never a fabricated inbound packet."""

    epoch: int
    source_mac: str
    peer: PairlinkPeerIdentity | None
    status: int


@dataclass(frozen=True, slots=True)
class PairlinkClockResponse:
    """One source time response, retained only to drive the source retry loop."""

    epoch: int
    source_mac: str
    peer: PairlinkPeerIdentity | None
    timestamp_seconds: int


PairlinkEffect = (
    PairlinkSendReply
    | PairlinkWelcome
    | PairlinkMeshEvent
    | PairlinkSdkFrame
    | PairlinkClockResponse
    | PairlinkSdkNative
)


@dataclass(slots=True)
class _EventKeyRecord:
    reserved: bytes = _ZERO4
    index: bytes = _ZERO4
    key: bytes = _ZERO16


@dataclass(slots=True)
class _ProvisioningState:
    """Private safe-domain state for one physical peer's native provision flow."""

    stage: int = 0
    initialized: bool = False
    capability: bytes = b""
    start: bytes = bytes(3)
    local_private_key: ec.EllipticCurvePrivateKey | None = field(default=None, repr=False)
    local_public_key: bytes = field(default=b"", repr=False)
    peer_public_key: bytes = field(default=b"", repr=False)
    shared_secret: bytes = field(default=b"", repr=False)
    confirmation_salt: bytes = field(default=b"", repr=False)
    local_random: bytes = field(default=b"", repr=False)
    auth: bytes = field(default=bytes(16), repr=False)
    extension: bytes = field(default=b"", repr=False)
    source_mac: str | None = field(default=None, repr=False)
    device_key: bytes = field(default=b"", repr=False)
    session_key: bytes = field(default=b"", repr=False)
    nonce_material: bytes = field(default=b"", repr=False)

    def clear(self) -> None:
        self.stage = 0
        self.initialized = False
        self.capability = b""
        self.start = bytes(3)
        self.local_private_key = None
        self.local_public_key = b""
        self.peer_public_key = b""
        self.shared_secret = b""
        self.confirmation_salt = b""
        self.local_random = b""
        self.auth = bytes(16)
        self.extension = b""
        self.source_mac = None
        self.device_key = b""
        self.session_key = b""
        self.nonce_material = b""


def _derive_provision_confirmation(
    *,
    capability: bytes,
    start: bytes,
    local_public_key: bytes,
    peer_public_key: bytes,
    shared_secret: bytes,
    local_random: bytes,
    auth: bytes,
) -> tuple[bytes, bytes]:
    """Apply the accepted fixed-mode transcript CMAC and confirmation labels."""
    if (
        len(capability) != 7
        or len(start) != 3
        or len(local_public_key) != 64
        or len(peer_public_key) != 64
        or len(shared_secret) != 32
        or len(local_random) != 16
        or len(auth) != 16
    ):
        raise ValueError("Pairlink provision transcript fields have invalid widths")
    salt = cmac_aes(
        bytes(16),
        capability + start + local_public_key + peer_public_key,
    )
    confirmation_key = cmac_aes(cmac_aes(salt, shared_secret), b"prck")
    confirmation = cmac_aes(confirmation_key, local_random + auth)
    return salt, confirmation


def _derive_provision_data(
    *,
    confirmation_salt: bytes,
    shared_secret: bytes,
    local_random: bytes,
    peer_random: bytes,
    plaintext: bytes,
) -> tuple[bytes, bytes, bytes, bytes]:
    """Build native prdk/prsk/prsn and exact fixed-credential ciphertext."""
    if (
        len(confirmation_salt) != 16
        or len(shared_secret) != 32
        or len(local_random) != 16
        or len(peer_random) != 16
        or not plaintext
        or len(plaintext) > 95
    ):
        raise ValueError("Pairlink provision data fields have invalid widths")
    provision_salt = cmac_aes(
        bytes(16),
        confirmation_salt + local_random + peer_random,
    )
    intermediate = cmac_aes(provision_salt, shared_secret)
    device_key = cmac_aes(intermediate, b"prdk")
    session_key = cmac_aes(intermediate, b"prsk")
    nonce_material = cmac_aes(intermediate, b"prsn")
    ciphertext = _encrypt_padded_aes_ecb(plaintext, key=session_key)
    return device_key, session_key, nonce_material, ciphertext


@dataclass(slots=True)
class _PeerSession:
    address: str
    identity: PairlinkPeerIdentity | None = None
    connected: bool = False
    subscribed: bool = False
    notify_mtu: int | None = None
    device_type: int | None = None
    primary: bool = False
    backup: bool = False
    source_backup_member: bool = False
    join_pending: bool = False
    state_generation: int = 0
    provisioning: _ProvisioningState = field(default_factory=_ProvisioningState, repr=False)


@dataclass(slots=True)
class _FragmentState:
    sequence: int = 0
    buffer: bytearray = field(default_factory=bytearray)


class PairlinkRuntimeNotReadyError(ConnectionError):
    """A selected Pairlink role lacks a source-proven current session."""


class PairlinkRuntime:
    """Own one entry's Pairlink keys, decoded state, and peer generations."""

    def __init__(
        self,
        credentials: PairlinkCredentials,
        *,
        role: PairlinkRole,
        target_mac: str | None,
        local_join_bt_mac: bytes,
    ) -> None:
        if not isinstance(credentials, PairlinkCredentials):
            raise TypeError("Pairlink runtime requires validated credentials")
        if not isinstance(role, PairlinkRole):
            raise TypeError("Pairlink runtime role must use PairlinkRole")
        if type(local_join_bt_mac) is not bytes or len(local_join_bt_mac) != 6:
            raise ValueError("Pairlink local join address must contain six bytes")
        self.credentials = credentials
        self.role = role
        self.target_mac = normalize_mac(target_mac) if target_mac else None
        self.local_join_bt_mac = local_join_bt_mac
        self.epoch = 1
        self.own_virtual_address = _ZERO4
        self.own_virtual_address_assigned = False
        self._central_link_connected = False
        self.central_add_pending = False
        self.joined = False
        self.peripheral_stop_adv_after_welcome = True
        self.primary_mac: str | None = None
        self.sign_gate = PairlinkSignGate()
        # The controller installs the app MeshCallback. A null callback alone
        # must not preempt the built-in SDK parser, even for registered types.
        self._sdk_state: PairlinkSdkState | None = None
        self._sdk_exit_callback: Callable[[], Awaitable[None]] | None = None
        self._mesh_callback_present = True
        # Ordinary app joins bypass the detector; its transient getter stays0.
        self._join_check_type = 0
        self._central_status_callback: Callable[[PairlinkMeshStatusEvent], None] | None = None
        self.registered_channels: set[int] = {0x20}
        self.peer_sessions: dict[str, _PeerSession] = {}
        self._peer_keys: dict[str, bytes] = {}
        self._current_event_key = self._fixed_context(b"EVENTKEY")
        self._login_key = self._fixed_context(b"LOGINKEY")
        self._variable_password = b""
        self._event_key_index = _ZERO4
        self._event_key_history = [_EventKeyRecord() for _ in range(5)]
        self._fragment_states: dict[tuple[str, int], _FragmentState] = {}
        self._central_provisioning = _ProvisioningState()
        self.state_generation = 0
        self._shutdown_callback: Callable[[], None] | None = None
        self.peripheral_backend: PairlinkPeripheralBackend | None = None
        self.host_adapter_source: str | None = None
        self.host_adapter_path: str | None = None
        self._closed = False
        self._exiting = False

    @property
    def current_event_key(self) -> bytes:
        """Return a copy of the current source event context."""
        return memoryview(self._current_event_key).tobytes()

    @property
    def admitted_peer_count(self) -> int:
        return len(self._peer_keys)

    @property
    def backup_peer_identities(self) -> tuple[PairlinkPeerIdentity, ...]:
        """Return current subscribed physical peers retained as backups."""
        if self.role is not PairlinkRole.PERIPHERAL or self._closed:
            return ()
        return tuple(
            session.identity
            for session in self.peer_sessions.values()
            if session.backup
            and not session.primary
            and session.connected
            and session.subscribed
            and session.identity is not None
        )

    @property
    def is_peripheral_role_active(self) -> bool:
        return self.role is PairlinkRole.PERIPHERAL and not self._closed

    @property
    def is_closed(self) -> bool:
        """Whether entry teardown has invalidated this runtime's state."""
        return self._closed

    @property
    def is_exiting(self) -> bool:
        """Whether exit has fenced new work before awaited persistence."""
        return self._exiting

    @property
    def disconnected_transport_ready(self) -> bool:
        if not self.is_peripheral_role_active or self.peripheral_backend is None:
            return False
        if not self.peripheral_backend.is_ready:
            return False
        try:
            self.prepare_send()
        except (PairlinkRuntimeNotReadyError, PermissionError, ValueError):
            return False
        return True

    async def async_start_peripheral(
        self,
        *,
        host_adapter_source: str,
        adapter_inventory: tuple[PairlinkHostAdapterInventoryEntry, ...],
        profile: PairlinkPeripheralProfile,
        on_peer_write: PairlinkPeerWriteCallback,
        on_peer_lifecycle: PairlinkPeerLifecycleCallback,
    ) -> None:
        """Start and retain the local BlueZ backend for this config-entry runtime."""
        if self.role is not PairlinkRole.PERIPHERAL or self._closed:
            raise PairlinkRuntimeNotReadyError("Pairlink local role is not active")
        if self.peripheral_backend is not None:
            raise PairlinkRuntimeNotReadyError("Pairlink local backend is already owned")
        if not callable(on_peer_lifecycle):
            raise TypeError("Pairlink peer lifecycle callback must be callable")
        backend = PairlinkPeripheralBackend()
        self.peripheral_backend = backend
        self.host_adapter_source = host_adapter_source
        try:
            await backend.async_start(
                host_adapter_source=host_adapter_source,
                adapter_inventory=adapter_inventory,
                profile=profile,
                on_peer_write=on_peer_write,
                on_peer_lifecycle=on_peer_lifecycle,
                is_peripheral_role_active=lambda: self.is_peripheral_role_active,
            )
            self.host_adapter_path = backend.adapter_path
            if self.host_adapter_path is None:
                raise PairlinkRuntimeNotReadyError(
                    "Pairlink BlueZ backend did not retain its selected adapter"
                )
        except BaseException:
            self.peripheral_backend = None
            self.host_adapter_source = None
            self.host_adapter_path = None
            raise

    def set_shutdown_callback(self, callback: Callable[[], None]) -> None:
        """Register the current controller's entry-owned timer cleanup."""
        if not callable(callback):
            raise TypeError("Pairlink shutdown callback must be callable")
        if self._closed:
            raise PairlinkRuntimeNotReadyError("Pairlink runtime is already closed")
        self._shutdown_callback = callback

    async def async_notify_to_peer(
        self,
        snapshot: PairlinkSendSnapshot,
        value: bytes,
        *,
        validate_send: Callable[[], None] | None = None,
    ) -> None:
        backend = self.peripheral_backend
        peer = snapshot.peer
        if (
            backend is None
            or peer is None
            or snapshot.role is not PairlinkRole.PERIPHERAL
            or not self.snapshot_is_current(snapshot)
        ):
            raise PairlinkRuntimeNotReadyError("Pairlink local peer session changed")
        await backend.async_notify_to_peer(peer, value, validate_send=validate_send)

    async def async_reply_to_peer(
        self,
        peer: PairlinkPeerIdentity,
        value: bytes,
        *,
        epoch: int,
    ) -> None:
        """Send a native response only through its current verified peer FD."""
        if (
            self._closed
            or self.role is not PairlinkRole.PERIPHERAL
            or epoch != self.epoch
        ):
            raise PairlinkRuntimeNotReadyError("Pairlink local role is no longer active")
        session = self._current_peer_session(peer)
        backend = self.peripheral_backend
        if (
            session is None
            or not session.connected
            or not session.subscribed
            or backend is None
            or not backend.is_ready
        ):
            raise PairlinkRuntimeNotReadyError(
                "Pairlink native reply has no current subscribed peer"
            )
        await backend.async_notify_to_peer(peer, value)

    def begin_exit(self) -> None:
        """Fence receive admission before awaited source-state persistence."""
        self._exiting = True

    async def async_shutdown(self) -> None:
        """Stop entry-owned sockets and erase its in-memory session material."""
        self.begin_exit()
        try:
            if self._sdk_exit_callback is not None:
                await self._sdk_exit_callback()
        finally:
            await self._async_shutdown_transport()

    async def _async_shutdown_transport(self) -> None:
        """Erase transport material even if source exit persistence failed."""
        self._sdk_exit_callback = None
        self._closed = True
        self._mesh_callback_present = False
        self._central_status_callback = None
        self.epoch += 1
        self.state_generation += 1
        shutdown_callback = self._shutdown_callback
        self._shutdown_callback = None
        backend = self.peripheral_backend
        self.peripheral_backend = None
        self.host_adapter_source = None
        self.host_adapter_path = None
        try:
            try:
                if shutdown_callback is not None:
                    shutdown_callback()
            finally:
                if backend is not None:
                    await backend.async_stop()
        finally:
            self._peer_keys.clear()
            self._central_provisioning.clear()
            for session in self.peer_sessions.values():
                session.provisioning.clear()
            self.peer_sessions.clear()
            self.joined = False
            self.primary_mac = None
            self._central_link_connected = False
            self.own_virtual_address = _ZERO4
            self.own_virtual_address_assigned = False
            self._login_key = _ZERO16
            self._current_event_key = _ZERO16
            self._event_key_index = _ZERO4
            self._event_key_history = [_EventKeyRecord() for _ in range(5)]
            self.sign_gate.device_signs.clear()
            self.sign_gate.sign_all = True
            self._variable_password = b""
            self._fragment_states.clear()
            self.local_join_bt_mac = bytes(6)
            self.credentials = PairlinkCredentials(
                _ZERO4,
                _ZERO4,
                self.credentials.home_id_origin,
                self.credentials.password_origin,
            )

    @property
    def event_key_index(self) -> bytes:
        return memoryview(self._event_key_index).tobytes()

    @property
    def event_key_history(self) -> tuple[tuple[bytes, bytes, bytes], ...]:
        return tuple((record.reserved, record.index, record.key) for record in self._event_key_history)

    def set_fixed_credentials(self, credentials: PairlinkCredentials) -> None:
        """Port the fixed native setter's table reset and retained history."""
        if self._closed:
            raise PairlinkRuntimeNotReadyError("Pairlink entry runtime is closed")
        if not isinstance(credentials, PairlinkCredentials):
            raise TypeError("Pairlink runtime requires validated credentials")
        self.credentials = credentials
        self._peer_keys.clear()
        self._central_provisioning.clear()
        self._variable_password = b""
        self._login_key = self._fixed_context(b"LOGINKEY")
        self._current_event_key = self._fixed_context(b"EVENTKEY")
        self.state_generation += 1

    def refresh_configured_inputs(
        self,
        entry_data: Mapping[str, object],
        entry_options: Mapping[str, object],
        *,
        manufacturer_data: dict[int, bytes] | None,
    ) -> None:
        """Refresh offline inputs before transport startup without replacing the owner."""
        role, target_mac, credentials = _resolve_pairlink_entry_configuration(
            entry_data,
            entry_options,
            manufacturer_data=manufacturer_data,
            previous_credentials=self.credentials,
        )
        configured_target = (
            normalize_mac(target_mac)
            if role is PairlinkRole.CENTRAL and target_mac
            else None
        )
        if role is not self.role or configured_target != self.target_mac:
            raise PairlinkRuntimeNotReadyError(
                "Pairlink role or target changed; reload the config entry before reuse"
            )
        if credentials == self.credentials:
            return
        if (
            self._central_link_connected
            or self.peripheral_backend is not None
            or self.peer_sessions
        ):
            raise PairlinkRuntimeNotReadyError(
                "Pairlink credentials changed during a live session; reload the config entry"
            )
        self.set_fixed_credentials(credentials)

    def mesh_exited(self) -> None:
        """Clear only the native session table, retaining key/index history."""
        if self._closed:
            return
        self._peer_keys.clear()
        self.state_generation += 1

    def central_connected(self, target_mac: str) -> None:
        """Record the exact selected central link without asserting source join."""
        if self._closed:
            raise PairlinkRuntimeNotReadyError("Pairlink entry runtime is closed")
        normalized = normalize_mac(target_mac)
        if self.role is not PairlinkRole.CENTRAL:
            raise PairlinkRuntimeNotReadyError("Pairlink runtime is not in central role")
        if self.target_mac is not None and self.target_mac != normalized:
            raise PairlinkRuntimeNotReadyError("Pairlink central target changed")
        if not self._central_link_connected:
            self.epoch += 1
            self.central_add_pending = True
            self._clear_fragments_for_mac(normalized)
            self._central_provisioning.clear()
            self._initialize_provisioning_state(
                self._central_provisioning,
                source_mac=normalized,
                extension=self.credentials.home_id_le,
            )
        self.target_mac = normalized
        self._central_link_connected = True
        self.state_generation += 1

    def _on_central_library_status(self, status: int, *, source_mac: str) -> None:
        """Project only source status3/4/6 and then end that central session."""
        if self._closed or self.role is not PairlinkRole.CENTRAL or status not in (3, 4, 6):
            return
        mac = normalize_mac(source_mac)
        if mac != self.target_mac:
            return
        callback = self._central_status_callback
        try:
            if self._mesh_callback_present and callback is not None:
                callback(PairlinkMeshStatusEvent(self.epoch, mac, None, 8))
        finally:
            # Source orders callback before meshExited. HA must still release
            # the failed session if its consumer raises during shutdown.
            self.central_disconnected(mac)

    def central_disconnected(self, target_mac: str) -> None:
        """Invalidate the selected physical session and its exact MAC key."""
        if self._closed:
            return
        normalized = normalize_mac(target_mac)
        if (
            self.role is not PairlinkRole.CENTRAL
            or normalized != self.target_mac
            or not self._central_link_connected
        ):
            return
        self.epoch += 1
        self._clear_fragments_for_mac(normalized)
        self._central_link_connected = False
        self.central_add_pending = False
        self._central_provisioning.clear()
        self.joined = False
        self.primary_mac = None
        self.own_virtual_address = _ZERO4
        self.own_virtual_address_assigned = False
        self.mesh_exited()
        self.state_generation += 1

    def source_joined(self, target_mac: str) -> None:
        """Apply only the accepted add-success source callback transition."""
        if self._closed:
            raise PairlinkRuntimeNotReadyError("Pairlink entry runtime is closed")
        normalized = normalize_mac(target_mac)
        if self.role is PairlinkRole.CENTRAL:
            if not self._central_link_connected or normalized != self.target_mac:
                return
        else:
            session = self.peer_sessions.get(normalized)
            if session is None or not session.connected:
                return
        previous_primary = self.primary_mac
        if self.role is PairlinkRole.PERIPHERAL and previous_primary not in (None, normalized):
            previous_session = self.peer_sessions.get(previous_primary)
            if previous_session is not None:
                previous_session.primary = False
                previous_session.backup = True
        self.joined = True
        self.primary_mac = normalized
        self._clear_fragments_for_mac(normalized)
        if self.role is PairlinkRole.CENTRAL:
            self.central_add_pending = False
        session = self.peer_sessions.get(normalized)
        if session is not None:
            session.primary = True
            session.backup = False
            session.source_backup_member = False
            session.join_pending = False
        self.state_generation += 1

    def peer_connected(self, peer: PairlinkPeerIdentity) -> None:
        self._validate_local_peer(peer)
        if self._exiting:
            return
        session = self.peer_sessions.get(peer.address)
        if session is not None and session.identity != peer:
            previous_identity = session.identity
            if previous_identity is not None:
                self.peer_disconnected(previous_identity)
            session = None
        if session is None:
            self._clear_fragments_for_mac(peer.address)
            session = _PeerSession(
                peer.address,
                identity=peer,
                connected=True,
                backup=self.primary_mac is not None and self.primary_mac != peer.address,
                source_backup_member=True,
                join_pending=True,
            )
            self.peer_sessions[peer.address] = session
        elif not session.connected:
            session.connected = True
            session.source_backup_member = True
            session.join_pending = True
            session.state_generation += 1

    def initialize_peer_provisioning(
        self,
        peer: PairlinkPeerIdentity,
        *,
        extension: bytes,
    ) -> None:
        """Initialize one current peer's source-shaped provisioner state.

        The local-host join route owns a separate provisioning context for each
        connected peer. The accepted app caller passes its four HomeID bytes as
        the optional extension; this private method does not expose a general
        packet or credential API.
        """
        if self.role is not PairlinkRole.PERIPHERAL or self._closed:
            raise PairlinkRuntimeNotReadyError("Pairlink local provisioner is not active")
        if type(extension) is not bytes or len(extension) != 4:
            raise ValueError("Pairlink provision extension must contain four bytes")
        self._validate_local_peer(peer)
        session = self._current_peer_session(peer)
        if session is None or not session.connected:
            raise PairlinkRuntimeNotReadyError("Pairlink provisioning peer is stale")

        self._initialize_provisioning_state(
            session.provisioning,
            source_mac=peer.address,
            extension=extension,
        )

    @staticmethod
    def _initialize_provisioning_state(
        state: _ProvisioningState,
        *,
        source_mac: str,
        extension: bytes,
    ) -> None:
        """Build the accepted fixed-mode provision-init state for one route."""
        state.clear()
        private_key = ec.generate_private_key(ec.SECP256R1())
        encoded_public = private_key.public_key().public_bytes(
            Encoding.X962,
            PublicFormat.UncompressedPoint,
        )
        if len(encoded_public) != 65 or encoded_public[0] != 0x04:
            raise RuntimeError("Pairlink P-256 provider returned an invalid public point")
        state.initialized = True
        # pl_provisioner_init clears the source info block before writing its
        # generated key material. Keep the native zero-filled transcript
        # fields explicit so the reachable subtype-04 path never reads an
        # uninitialized or stale host value.
        state.capability = bytes(7)
        state.start = bytes(3)
        state.peer_public_key = bytes(64)
        state.shared_secret = bytes(32)
        state.confirmation_salt = bytes(16)
        state.auth = bytes(16)
        state.local_private_key = private_key
        state.local_public_key = encoded_public[1:]
        # Native generate_random consumes four rand() words in little-endian
        # order. HA owns this host RNG; use fresh process entropy, never a
        # copied vector or zero/stale fallback.
        state.local_random = secrets.token_bytes(16)
        state.extension = memoryview(extension).tobytes()
        state.source_mac = source_mac

    def apply_peer_lifecycle(self, event: PairlinkPeerLifecycleEvent) -> None:
        """Apply backend identity facts without conflating subscription and link state."""
        if self._closed:
            return
        if self._exiting and event.kind in (
            PairlinkPeerLifecycleKind.CONNECTED,
            PairlinkPeerLifecycleKind.NOTIFY_SUBSCRIBED,
        ):
            return
        match event.kind:
            case PairlinkPeerLifecycleKind.CONNECTED:
                self.peer_connected(event.peer)
            case PairlinkPeerLifecycleKind.NOTIFY_SUBSCRIBED:
                assert event.mtu is not None
                self.peer_subscribed(event.peer, event.mtu)
            case PairlinkPeerLifecycleKind.NOTIFY_UNSUBSCRIBED:
                self.peer_unsubscribed(event.peer)
            case PairlinkPeerLifecycleKind.DISCONNECTED:
                self.peer_disconnected(event.peer)

    def peer_subscribed(self, peer: PairlinkPeerIdentity, mtu: int) -> None:
        self._validate_local_peer(peer)
        if isinstance(mtu, bool) or not isinstance(mtu, int) or mtu < 3:
            raise PairlinkRuntimeNotReadyError("Pairlink peer notify MTU is invalid")
        session = self.peer_sessions.get(peer.address)
        if session is None or session.identity != peer or not session.connected:
            raise PairlinkRuntimeNotReadyError("Pairlink peer is not physically connected")
        changed = not session.subscribed or session.notify_mtu != mtu
        session.subscribed = True
        session.notify_mtu = mtu
        if changed:
            session.state_generation += 1

    def peer_unsubscribed(self, peer: PairlinkPeerIdentity) -> None:
        if self._closed:
            return
        session = self._current_peer_session(peer)
        if session is None:
            return
        if not session.subscribed and session.notify_mtu is None:
            return
        session.subscribed = False
        session.notify_mtu = None
        session.state_generation += 1

    def peer_disconnected(self, peer: PairlinkPeerIdentity) -> None:
        if self._closed:
            return
        session = self._current_peer_session(peer)
        if session is None:
            return
        was_primary = session.primary
        if was_primary:
            self.joined = False
            self.primary_mac = None
            self.own_virtual_address = _ZERO4
            self.own_virtual_address_assigned = False
            self.mesh_exited()
            for remaining in self.peer_sessions.values():
                remaining.device_type = None
                remaining.primary = False
                remaining.backup = False
                remaining.source_backup_member = False
                remaining.join_pending = False
                remaining.provisioning.clear()
        if was_primary:
            self.epoch += 1
        session.connected = False
        session.subscribed = False
        session.notify_mtu = None
        self._peer_keys.pop(peer.address, None)
        self._clear_fragments_for_mac(peer.address)
        session.provisioning.clear()
        self.peer_sessions.pop(peer.address, None)
        if was_primary:
            self.state_generation += 1

    def set_peer_device_type(self, peer: PairlinkPeerIdentity, device_type: int) -> None:
        self._validate_local_peer(peer)
        if isinstance(device_type, bool) or not isinstance(device_type, int) or not 0 <= device_type <= 0xFF:
            raise ValueError("Pairlink peer type must fit one byte")
        session = self._current_peer_session(peer)
        if session is None:
            raise PairlinkRuntimeNotReadyError("Pairlink peer generation is stale")
        session.device_type = device_type
        session.state_generation += 1

    def prepare_send(self, *, mtu: int = 23) -> PairlinkSendSnapshot:
        """Capture all currently proven send state before constructing bytes."""
        if self._closed or self._exiting:
            raise PairlinkRuntimeNotReadyError("Pairlink entry runtime is closed")
        if self.role is PairlinkRole.CENTRAL:
            target = self.target_mac
            if not self._central_link_connected or not self.joined or target is None:
                raise PairlinkRuntimeNotReadyError("Pairlink central session is not joined")
            key = self._peer_keys.get(target)
            if key is None:
                raise PairlinkRuntimeNotReadyError("Pairlink central peer key is unavailable")
            return PairlinkSendSnapshot(
                epoch=self.epoch,
                state_generation=self.state_generation,
                role=self.role,
                target_mac=target,
                peer=None,
                own_virtual_address=self.own_virtual_address,
                event_key=self._current_event_key,
                device_key=key,
                device_type=1,
                mtu=mtu,
            )

        target = self.primary_mac
        if not self.joined or target is None:
            raise PairlinkRuntimeNotReadyError("Pairlink local source session is not joined")
        session = self.peer_sessions.get(target)
        if (
            session is None
            or not session.connected
            or not session.subscribed
            or session.identity is None
            or session.notify_mtu is None
        ):
            raise PairlinkRuntimeNotReadyError("Pairlink local peer has no active notify session")
        if session.device_type not in (0, 1):
            raise PairlinkRuntimeNotReadyError("Pairlink local peer type is not established")
        key = self._peer_keys.get(target) if session.device_type == 1 else None
        if session.device_type == 1 and key is None:
            raise PairlinkRuntimeNotReadyError("Pairlink encrypted peer key is unavailable")
        return PairlinkSendSnapshot(
            epoch=self.epoch,
            state_generation=self.state_generation,
            role=self.role,
            target_mac=target,
            peer=session.identity,
            own_virtual_address=self.own_virtual_address,
            event_key=self._current_event_key,
            device_key=key,
            device_type=session.device_type,
            mtu=session.notify_mtu,
            peer_generation=session.identity.connection_generation,
            peer_state_generation=session.state_generation,
        )

    def snapshot_is_current(self, snapshot: PairlinkSendSnapshot) -> bool:
        if (
            self._closed
            or self._exiting
            or snapshot.epoch != self.epoch
            or snapshot.role is not self.role
        ):
            return False
        if snapshot.role is PairlinkRole.CENTRAL:
            return (
                snapshot.state_generation == self.state_generation
                and self._central_link_connected
                and self.joined
                and self.target_mac == snapshot.target_mac
                and self._peer_keys.get(snapshot.target_mac) == snapshot.device_key
            )
        session = self.peer_sessions.get(snapshot.target_mac)
        peer_identity = session.identity if session is not None else None
        return bool(
            session is not None
            and snapshot.state_generation == self.state_generation
            and snapshot.peer_state_generation == session.state_generation
            and peer_identity is not None
            and peer_identity == snapshot.peer
            and peer_identity.connection_generation == snapshot.peer_generation
            and session.connected
            and session.subscribed
            and session.device_type == snapshot.device_type
            and (snapshot.device_key is None or self._peer_keys.get(snapshot.target_mac) == snapshot.device_key)
        )

    def prepare_release_snapshot(
        self, captured: PairlinkSendSnapshot, *, mtu: int = 23
    ) -> PairlinkSendSnapshot:
        """Refresh auth for the captured physical target without rerouting it."""
        if not isinstance(captured, PairlinkSendSnapshot) or captured.role is not self.role:
            raise PairlinkRuntimeNotReadyError("Pairlink cleanup target is invalid")
        if captured.epoch != self.epoch:
            raise PairlinkRuntimeNotReadyError("Pairlink cleanup physical generation changed")
        if captured.role is PairlinkRole.CENTRAL:
            current = self.prepare_send(mtu=mtu)
            if current.target_mac != captured.target_mac:
                raise PairlinkRuntimeNotReadyError(
                    "Pairlink central cleanup target changed"
                )
            return current

        if captured.peer is None:
            raise PairlinkRuntimeNotReadyError("Pairlink local cleanup has no peer identity")
        session = self._current_peer_session(captured.peer)
        if (
            session is None
            or not session.connected
            or not session.subscribed
            or session.identity is None
            or session.notify_mtu is None
            or session.device_type not in (0, 1)
        ):
            raise PairlinkRuntimeNotReadyError(
                "Pairlink captured peer is no longer a ready physical session"
            )
        key = self._peer_keys.get(captured.target_mac) if session.device_type == 1 else None
        if session.device_type == 1 and key is None:
            raise PairlinkRuntimeNotReadyError(
                "Pairlink captured peer no longer has current authentication"
            )
        return PairlinkSendSnapshot(
            epoch=self.epoch,
            state_generation=self.state_generation,
            role=self.role,
            target_mac=captured.target_mac,
            peer=session.identity,
            own_virtual_address=self.own_virtual_address,
            event_key=self._current_event_key,
            device_key=key,
            device_type=session.device_type,
            mtu=session.notify_mtu,
            peer_generation=session.identity.connection_generation,
            peer_state_generation=session.state_generation,
        )

    def mark_peer_state_changed(self, peer: PairlinkPeerIdentity | None) -> None:
        """Advance only the affected local peer's state generation."""
        if self._closed:
            return
        if self.role is PairlinkRole.CENTRAL or peer is None:
            self.state_generation += 1
            return
        session = self._current_peer_session(peer)
        if session is not None:
            session.state_generation += 1

    def allows_send(
        self,
        snapshot: PairlinkSendSnapshot,
        *,
        destination: bytes,
        channel: int,
    ) -> bool:
        """Apply the source sign gate to the actual destination/channel pair."""
        return self.snapshot_is_current(snapshot) and self.sign_gate.allows(
            destination,
            channel,
            target_mac=snapshot.target_mac,
        )

    def process_transport_packet(
        self,
        payload: bytes,
        *,
        source_mac: str,
        peer: PairlinkPeerIdentity | None = None,
        expected_epoch: int | None = None,
    ) -> tuple[PairlinkEffect, ...]:
        """Process one accepted raw BLE callback/WriteValue payload."""
        if (
            self._closed
            or self._exiting
            or (expected_epoch is not None and expected_epoch != self.epoch)
            or type(payload) is not bytes
            or not payload
            or len(payload) > _MAX_SAFE_PACKET_LENGTH
        ):
            return ()
        mac = normalize_mac(source_mac)
        if self.role is PairlinkRole.CENTRAL:
            if peer is not None or mac != self.target_mac or not self._central_link_connected:
                return ()
        else:
            session = self._current_peer_session(peer) if peer is not None else None
            if (
                peer is None
                or peer.address != mac
                or session is None
                or not session.connected
            ):
                return ()

        if payload.startswith(b"\x04\x04"):
            assembled = self._accept_fragment(payload, mac, peer)
            if assembled is None:
                return ()
            payload = assembled

        if payload[:1] in (b"\x01", b"\x02"):
            if len(payload) < 2:
                return ()
            native_result = self._process_native_command(payload, mac, peer)
            if native_result is not None:
                return native_result
            return ()

        if payload[:1] == b"\x06":
            key = self._peer_keys.get(mac)
            if key is None:
                return ()
            try:
                decoded = decrypt_user_frame(
                    payload,
                    event_key=self._current_event_key,
                    device_key=key,
                )
            except (ValueError, RuntimeError):
                return ()
            return self._process_mesh_frame(decoded, mac, decrypted_by_native=True, peer=peer)

        if payload[:1] == b"\x03":
            return self._process_mesh_frame(payload, mac, decrypted_by_native=False, peer=peer)
        return ()

    def _process_native_command(
        self,
        packet: bytes,
        mac: str,
        peer: PairlinkPeerIdentity | None,
    ) -> tuple[PairlinkEffect, ...] | None:
        if len(packet) >= 6 and packet[0] == 0x01 and packet[1] == 0x0A:
            self.own_virtual_address = packet[2:6]
            self.own_virtual_address_assigned = True
            self.state_generation += 1
            return ()

        if packet[0] == 0x01 and packet[1] == 0x02:
            # The accepted Java CMD02 parser reads the count before it calls
            # the native seed updater. Keep both state changes in the safe
            # complete-packet domain rather than reproducing its short-read.
            if len(packet) < 14:
                return ()
            self.sign_gate.process_network_info()
            self.state_generation += 1
            self._replace_event_seed(packet[10:14])
            return (PairlinkSdkNative(self.epoch, mac, peer, "network_info", packet),)

        if packet[:2] == b"\x02\x42":
            if len(packet) < 10:
                return ()
            return (PairlinkSdkNative(self.epoch, mac, peer, "fingerprint", packet),)

        if packet[0] == 0x02 and packet[1] == 0x1A:
            if len(packet) < 6 or self.role is not PairlinkRole.CENTRAL or not self.joined:
                return ()
            return (
                PairlinkClockResponse(
                    self.epoch,
                    mac,
                    peer,
                    int.from_bytes(packet[2:6], "little", signed=False),
                ),
            )

        if packet[0] == 0x01 and packet[1] == 0x00 and len(packet) == 6:
            session = self.peer_sessions.get(mac)
            if (
                self.role is PairlinkRole.PERIPHERAL
                and session is not None
                and session.backup
                and not session.primary
                and session.device_type in (None, 0)
            ):
                session.device_type = 0
                session.state_generation += 1
                return (
                    PairlinkSendReply(
                        self.epoch,
                        mac,
                        peer,
                        b"\x02" + packet[1:] + self.credentials.password,
                    ),
                )
            return ()

        if packet[0] == 0x01 and packet[1] == 0x01 and len(packet) == 2:
            session = self.peer_sessions.get(mac)
            if (
                self.role is PairlinkRole.PERIPHERAL
                and session is not None
                and session.backup
                and not session.primary
                and session.device_type == 0
            ):
                return (PairlinkSendReply(self.epoch, mac, peer, b"\x01\x10"),)
            return ()

        if packet[0] == 0x02 and packet[1] == 0x31:
            if len(packet) < 3:
                return ()
            subtype = packet[2]
            if subtype == 0x08 and len(packet) >= 3:
                if (
                    self.role is PairlinkRole.CENTRAL
                    and self.central_add_pending
                    and mac == self.target_mac
                ):
                    self.source_joined(mac)
                    return (PairlinkSendReply(self.epoch, mac, peer, b"\x01\x20"),)
                session = self.peer_sessions.get(mac)
                if (
                    self.role is PairlinkRole.PERIPHERAL
                    and peer is not None
                    and session is not None
                    and session.join_pending
                ):
                    self.source_joined(mac)
                    return (
                        PairlinkWelcome(self.epoch, mac, peer),
                        PairlinkSendReply(self.epoch, mac, peer, b"\x01\x20"),
                    )
            elif subtype == 0x09 and len(packet) >= 4:
                if (
                    self.role is PairlinkRole.CENTRAL
                    and self.central_add_pending
                    and mac == self.target_mac
                ):
                    self.central_add_pending = False
                    self.joined = False
                    self.primary_mac = None
                    self._peer_keys.pop(mac, None)
                    self.state_generation += 1
                    return ()
                if self.role is PairlinkRole.PERIPHERAL and peer is not None:
                    session = self.peer_sessions.get(mac)
                    if session is not None:
                        session.primary = False
                        session.backup = False
                        session.join_pending = False
                        self._peer_keys.pop(mac, None)
                        session.state_generation += 1
                    if self.primary_mac == mac:
                        self.joined = False
                        self.primary_mac = None
                        self.state_generation += 1
                    return ()
            if subtype in (0x01, 0x03, 0x04, 0x05, 0x06):
                return self._process_provision_command(subtype, packet[3:], mac, peer)
            return ()

        command = packet[1]
        body = packet[2:]
        if not ((packet[0] == 0x01 and command == 0x19) or (packet[0] == 0x02 and command == 0x20)):
            return None
        if len(body) != 16:
            return ()
        try:
            decrypted = decrypt_login_block(body, login_key=self._login_key)
        except (ValueError, RuntimeError):
            return ()
        if decrypted[:4] != self.credentials.home_id_le:
            return ()
        session_key = decrypted[4:8]
        if mac not in self._peer_keys and len(self._peer_keys) < 7:
            self._peer_keys[mac] = session_key
        if self.role is PairlinkRole.PERIPHERAL:
            session = self.peer_sessions.get(mac)
            if session is not None:
                session.device_type = 1
                session.state_generation += 1
                if self.primary_mac is not None and self.primary_mac != mac:
                    session.backup = True
        else:
            self.state_generation += 1
        response_plaintext = (
            self.credentials.home_id_le + self.credentials.password + session_key + bytes((4,)) * 4
        )
        response_ciphertext = encrypt_login_block(response_plaintext, login_key=self._login_key)
        response = (
            b"\x02\x19" + response_ciphertext
            if packet[0] == 0x01
            else b"\x01\x16\x03" + response_ciphertext
        )
        return (PairlinkSendReply(self.epoch, mac, peer, response),)

    def _process_provision_command(
        self,
        subtype: int,
        body: bytes,
        mac: str,
        peer: PairlinkPeerIdentity | None,
    ) -> tuple[PairlinkEffect, ...]:
        """Reduce only the initialized, bounds-checked fixed-mode provision path."""
        if self.role is PairlinkRole.CENTRAL:
            state = self._central_provisioning
        else:
            if peer is None:
                return ()
            session = self._current_peer_session(peer)
            if session is None or not session.connected:
                return ()
            state = session.provisioning

        # The outer native dispatcher reads subtype before its length guard. This
        # host reducer receives only the already-selected subtype and keeps all
        # body accesses behind the source's safe fixed-width conditions.
        if subtype == 0x01:
            if len(body) < 7 or state.stage != 0:
                return ()
            capability = bytes(body[:7])
            state.capability = capability
            state.source_mac = mac
            if capability[0] | capability[1] | capability[4]:
                # The Java callback is a no-op on the ordinary route. Native
                # stores the source MAC after the callback and leaves state 0.
                return ()

            # The source has provisionInit establish these values before the
            # capability callback. Its zero-filled BSS fallback is not a valid
            # host session, so fail closed if the selected peer was not init'd.
            if (
                not state.initialized
                or state.local_private_key is None
                or len(state.local_public_key) != 64
                or len(state.local_random) != 16
            ):
                return ()
            state.stage = 2
            return (
                PairlinkSendReply(self.epoch, mac, peer, b"\x01\x31\x02\x00\x00\x00"),
                PairlinkSendReply(
                    self.epoch,
                    mac,
                    peer,
                    b"\x01\x31\x03" + state.local_public_key,
                ),
            )

        if subtype == 0x03:
            if len(body) != 64 or state.stage != 2 or state.local_private_key is None:
                return ()
            try:
                remote_public_key = ec.EllipticCurvePublicKey.from_encoded_point(
                    ec.SECP256R1(),
                    b"\x04" + body,
                )
                shared_secret = state.local_private_key.exchange(
                    ec.ECDH(),
                    remote_public_key,
                )
            except ValueError:
                return ()
            confirmation_salt, confirmation = _derive_provision_confirmation(
                capability=state.capability,
                start=state.start,
                local_public_key=state.local_public_key,
                peer_public_key=body,
                shared_secret=shared_secret,
                local_random=state.local_random,
                auth=state.auth,
            )
            state.shared_secret = shared_secret
            state.peer_public_key = bytes(body)
            state.confirmation_salt = confirmation_salt
            state.stage = 3
            return (
                PairlinkSendReply(
                    self.epoch,
                    mac,
                    peer,
                    b"\x01\x31\x05" + confirmation,
                ),
            )

        if subtype == 0x05:
            if len(body) != 16 or state.stage != 3 or len(state.local_random) != 16:
                return ()
            # Source subtype 05 consumes but does not compare peer confirmation.
            state.stage = 4
            return (
                PairlinkSendReply(
                    self.epoch,
                    mac,
                    peer,
                    b"\x01\x31\x06" + state.local_random,
                ),
            )

        if subtype == 0x06:
            if (
                len(body) != 16
                or state.stage != 4
                or len(state.shared_secret) != 32
                or len(state.confirmation_salt) != 16
                or len(state.local_random) != 16
            ):
                return ()
            plaintext = (
                b"\x55\x66\xAA\xBB"
                + b"\x05\x01"
                + self.credentials.home_id_le
                + b"\x05\x04"
                + self.credentials.password
                + b"\x02\x03\xA6"
                + bytes((len(state.extension) + 1, 0xFF))
                + state.extension
            )
            device_key, session_key, nonce_material, ciphertext = _derive_provision_data(
                confirmation_salt=state.confirmation_salt,
                shared_secret=state.shared_secret,
                local_random=state.local_random,
                peer_random=body,
                plaintext=plaintext,
            )
            state.device_key = device_key
            state.session_key = session_key
            state.nonce_material = nonce_material
            state.stage = 5
            return (
                PairlinkSendReply(
                    self.epoch,
                    mac,
                    peer,
                    b"\x01\x31\x07" + ciphertext,
                ),
            )

        if subtype == 0x04:
            # Native subtype 04 has no body/state guard. Restrict this host
            # branch to a current provisionInit owner and complete fixed-width
            # fields; the freshly initialized fields above match the source's
            # zeroed info block, while uninitialized/stale native memory is
            # never emulated.
            if (
                not state.initialized
                or state.local_private_key is None
                or len(state.capability) != 7
                or len(state.start) != 3
                or len(state.local_public_key) != 64
                or len(state.peer_public_key) != 64
                or len(state.shared_secret) != 32
                or len(state.local_random) != 16
                or len(state.auth) != 16
            ):
                return ()
            confirmation_salt, confirmation = _derive_provision_confirmation(
                capability=state.capability,
                start=state.start,
                local_public_key=state.local_public_key,
                peer_public_key=state.peer_public_key,
                shared_secret=state.shared_secret,
                local_random=state.local_random,
                auth=state.auth,
            )
            state.confirmation_salt = confirmation_salt
            state.stage = 3
            return (
                PairlinkSendReply(
                    self.epoch,
                    mac,
                    peer,
                    b"\x01\x31\x05" + confirmation,
                ),
            )

        return ()

    def _process_mesh_frame(
        self,
        frame: bytes,
        mac: str,
        *,
        decrypted_by_native: bool,
        peer: PairlinkPeerIdentity | None,
    ) -> tuple[PairlinkEffect, ...]:
        # Byte 5 is the source event selector; each registered callback owns
        # its own body-length checks. In particular channel 0x20 preempts SDK
        # fallthrough for the valid six-byte selector-only frame.
        if len(frame) < 6 or frame[0] != 0x03 or len(frame) > _MAX_SAFE_PACKET_LENGTH:
            return ()
        channel_unsigned = frame[5]
        channel = channel_unsigned if channel_unsigned < 128 else channel_unsigned - 256
        if (
            decrypted_by_native
            and channel_unsigned == 0x11
            and len(frame) >= 11
            and frame[6] == 0x32
        ):
            self._replace_event_seed(frame[7:11])
            return ()

        destination = frame[1:5]
        broadcast = destination == PAIRLINK_BROADCAST_ADDRESS
        if broadcast and 32 <= channel <= 63 and not self.sign_gate.sign_all:
            return ()
        event_data = memoryview(frame[6:]).tobytes()
        if self._mesh_callback_present and channel in self.registered_channels:
            return (PairlinkMeshEvent(self.epoch, mac, peer, channel, event_data, broadcast),)
        return (PairlinkSdkFrame(self.epoch, peer, memoryview(frame).tobytes(), mac),)

    def effect_is_current(
        self,
        *,
        epoch: int,
        source_mac: str,
        peer: PairlinkPeerIdentity | None,
    ) -> bool:
        """Reject queued reducer effects after their selected transport went stale."""
        if epoch != self.epoch or self._closed or self._exiting:
            return False
        try:
            mac = normalize_mac(source_mac)
        except ValueError:
            return False
        if self.role is PairlinkRole.CENTRAL:
            return peer is None and self._central_link_connected and mac == self.target_mac
        if peer is None or peer.address != mac:
            return False
        session = self._current_peer_session(peer)
        return session is not None and session.connected

    def status_callback_target_is_current(
        self, *, source_mac: str, peer: PairlinkPeerIdentity | None
    ) -> bool:
        """Require a joined current target before consuming app status callbacks."""
        if self._closed:
            return False
        try:
            mac = normalize_mac(source_mac)
        except ValueError:
            return False
        if self.role is PairlinkRole.CENTRAL:
            return (
                peer is None
                and self._central_link_connected
                and self.joined
                and mac == self.target_mac
            )
        if peer is None or peer.address != mac or not self.joined or self.primary_mac != mac:
            return False
        session = self._current_peer_session(peer)
        return bool(session is not None and session.connected and session.subscribed)

    def _replace_event_seed(self, seed: bytes) -> None:
        if type(seed) is not bytes or len(seed) != 4:
            return
        if seed == _ZERO4:
            self._event_key_index = _ZERO4
            self.state_generation += 1
            return
        event_key = derive_event_key_from_seed(seed, variable_password=self._variable_password)
        event_index = derive_event_key_index(event_key)
        shifted = self._event_key_history[1:]
        shifted.append(_EventKeyRecord(self._event_key_history[-1].reserved, event_index, event_key))
        self._event_key_history = shifted
        self._current_event_key = event_key
        self._event_key_index = event_index
        self.state_generation += 1

    def _accept_fragment(
        self, packet: bytes, mac: str, peer: PairlinkPeerIdentity | None
    ) -> bytes | None:
        if len(packet) < 3:
            return None
        count = packet[2] >> 4
        sequence = packet[2] & 0x0F
        if count == 0 or sequence == 0 or sequence > count:
            return None
        key = (
            (mac, peer.connection_generation)
            if peer is not None
            else (mac, self.epoch)
        )
        state = self._fragment_states.get(key)
        expected_sequence = state.sequence + 1 if state is not None else 1
        if sequence != expected_sequence:
            return None
        if (
            state is not None
            and len(state.buffer) + len(packet[3:]) > _MAX_SAFE_PACKET_LENGTH
        ):
            return None
        if state is None:
            state = _FragmentState()
            self._fragment_states[key] = state
        state.buffer.extend(packet[3:])
        state.sequence = sequence
        if count != sequence:
            return None
        assembled = bytes(state.buffer)
        self._fragment_states.pop(key, None)
        return assembled

    def _clear_fragments_for_mac(self, mac: str) -> None:
        for key in tuple(self._fragment_states):
            if key[0] == mac:
                self._fragment_states.pop(key, None)

    def _fixed_context(self, suffix: bytes) -> bytes:
        home = self.credentials.home_id_le
        password = self.credentials.password
        interleaved = b"".join(
            bytes((home_byte, password_byte))
            for home_byte, password_byte in zip(home, password, strict=True)
        )
        return interleaved + suffix

    def _validate_local_peer(self, peer: PairlinkPeerIdentity) -> None:
        if self._closed:
            raise PairlinkRuntimeNotReadyError("Pairlink entry runtime is closed")
        if self.role is not PairlinkRole.PERIPHERAL:
            raise PairlinkRuntimeNotReadyError("Pairlink runtime is not in local role")
        if not isinstance(peer, PairlinkPeerIdentity):
            raise PairlinkRuntimeNotReadyError("Pairlink peer identity is unavailable")
        if self.host_adapter_path is None or peer.adapter_path != self.host_adapter_path:
            raise PairlinkRuntimeNotReadyError(
                "Pairlink peer identity belongs to another local adapter"
            )

    def _current_peer_session(self, peer: PairlinkPeerIdentity) -> _PeerSession | None:
        if (
            self._closed
            or self.role is not PairlinkRole.PERIPHERAL
            or not isinstance(peer, PairlinkPeerIdentity)
        ):
            return None
        session = self.peer_sessions.get(peer.address)
        if session is None or session.identity != peer:
            return None
        return session
