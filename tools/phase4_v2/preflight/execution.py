"""Deterministic execution and caching for routed package-local preparation tools."""

from __future__ import annotations

import builtins
import errno
import hashlib
import json
import math
import os
import re
import resource
import selectors
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path, PurePosixPath
from typing import Literal

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from .core import (
    PREFLIGHT_SCHEMA,
    ArtifactMember,
    PreflightResult,
    _make_private_directory_at,
    _rename_noreplace,
    _rename_noreplace_at,
)

EXECUTION_SCHEMA = "phase4-v2-preparation-execution-v2"
EXECUTION_CACHE_SCHEMA = "phase4-v2-preparation-cache-v2"
EXECUTION_PROFILE_REVISION = "phase4-v2-execution-profile-v3"
SANDBOX_REVISION = "phase4-v2-bwrap-sandbox-v3"
EXECUTION_ATTESTATION_REVISION = "phase4-v2-execution-attestation-v1"
CANDIDATE_INDEX_SCHEMA = "phase4-v2-ble-candidate-index-v1"
CANDIDATE_CONTRACT_REVISION = "phase4-v2-ble-candidate-contract-v2"

_REVISION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,199}$")
_PLACEHOLDERS = frozenset({"{input}", "{output}"})
_DIAGNOSTIC_LINE = re.compile(
    rb"^\s*(?:\[[^]\r\n]{1,64}\]\s*)?(?:warning|warn|error|exception|failed|failure|skipped)\b",
    re.IGNORECASE,
)
_SOURCE_SUFFIXES = frozenset({".java", ".kt"})
_SMALI_SUFFIX = ".smali"
_MAX_CACHE_MANIFEST_BYTES = 128 * 1024**2
_CHUNK = 1024 * 1024
_BWRAP_NAMES = ("bwrap", "bubblewrap")
_TRUSTED_CACHE_OBJECTS: dict[str, tuple[int, int, str]] = {}
_ED25519_PUBLIC_KEY = re.compile(r"^[0-9a-f]{64}$")
_ED25519_SIGNATURE = re.compile(r"^[0-9a-f]{128}$")
_QUOTA_KEEPER_SCRIPT = r"""
import ctypes
import os
import sys

mountpoint, size, nodes, ready, control = sys.argv[1:]
ready_descriptor = int(ready)
control_descriptor = int(control)

def write_file(path, payload):
    descriptor = os.open(path, os.O_WRONLY | getattr(os, "O_CLOEXEC", 0))
    try:
        os.write(descriptor, payload)
    finally:
        os.close(descriptor)

def mount(source, target, filesystem, flags, data):
    libc = ctypes.CDLL(None, use_errno=True)
    function = libc.mount
    function.argtypes = (ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p,
                         ctypes.c_ulong, ctypes.c_char_p)
    function.restype = ctypes.c_int
    if function(source, target, filesystem, flags, data) != 0:
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error))

try:
    outer_uid, outer_gid = os.getuid(), os.getgid()
    os.unshare(os.CLONE_NEWUSER)
    try:
        write_file("/proc/self/setgroups", b"deny\n")
    except FileNotFoundError:
        pass
    write_file("/proc/self/uid_map", f"0 {outer_uid} 1\n".encode("ascii"))
    write_file("/proc/self/gid_map", f"0 {outer_gid} 1\n".encode("ascii"))
    os.unshare(os.CLONE_NEWNS)
    mount(None, b"/", None, (1 << 18) | 16384, None)
    options = f"size={size},nr_inodes={int(nodes) + 1},mode=0777".encode("ascii")
    mount(b"tmpfs", os.fsencode(mountpoint), b"tmpfs", 2 | 4 | 8, options)
    os.write(ready_descriptor, b"READY\n")
    os.close(ready_descriptor)
    while os.read(control_descriptor, 1):
        pass
except BaseException as error:
    try:
        os.write(ready_descriptor, f"ERROR:{type(error).__name__}\n".encode("ascii"))
    except OSError:
        pass
"""
_CANDIDATE_SIGNALS: tuple[tuple[str, bytes], ...] = (
    ("android.bluetooth.descriptor", b"Landroid/bluetooth/"),
    ("android.bluetooth.namespace", b"android.bluetooth"),
    ("android.bluetooth.path", b"android/bluetooth/"),
    ("bluetooth.gatt", b"BluetoothGatt"),
    ("bluetooth.gatt.characteristic", b"BluetoothGattCharacteristic"),
    ("bluetooth.le.scanner", b"BluetoothLeScanner"),
    ("bluetooth.notification", b"setCharacteristicNotification"),
    ("bluetooth.write", b"writeCharacteristic"),
    ("corebluetooth.uuid", b"CBUUID"),
    ("uuid.construction", b"UUID.fromString"),
    ("air.bluetooth-le", b"BluetoothLE"),
    ("air.byte-array", b"ByteArray"),
    ("ble.characteristic-uuid", b"characteristicUUID"),
    ("ble.connect", b"connectToDevice"),
    ("ble.gatt-native", b"bt_gatt"),
    ("ble.monitor", b"monitorCharacteristic"),
    ("ble.notification-start", b"startNotification"),
    ("ble.scan", b"startDeviceScan"),
    ("ble.service-uuids", b"serviceUUIDs"),
    ("ble.write-without-response", b"writeWithoutResponse"),
    ("flutter.characteristic", b"BluetoothCharacteristic"),
    ("flutter.guid", b"Guid("),
    ("flutter.reactive-ble", b"flutter_reactive_ble"),
    ("flutter.blue", b"flutter_blue"),
    ("native.bluetooth-gatt", b"bluetooth_gatt"),
    ("native.nordic-write", b"sd_ble_gattc_write"),
    ("native.uuid-parse", b"uuid_parse"),
    ("react-native.ble-manager", b"BleManager"),
    ("react-native.ble-plx", b"react-native-ble-plx"),
    ("react-native.write", b"writeCharacteristicWithResponseForDevice"),
)
CANDIDATE_SIGNAL_IDS = frozenset(name for name, _needle in _CANDIDATE_SIGNALS)
CANDIDATE_CONTRACT_SHA256 = hashlib.sha256(
    json.dumps(
        {
            "revision": CANDIDATE_CONTRACT_REVISION,
            "signals": [
                {"id": name, "needle_hex": needle.hex()} for name, needle in _CANDIDATE_SIGNALS
            ],
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
).hexdigest()


class PreparationError(RuntimeError):
    """Raised when package preparation cannot be performed safely."""


class PreparationCacheError(PreparationError):
    """Raised when a preparation cache object fails verification."""


class PreparationExecutionSigner:
    """Executor credential whose public key is pinned by protected authority."""

    __slots__ = ("_key", "public_key")

    def __init__(self) -> None:
        raise PreparationError("execution signers must be loaded from protected credentials")

    @classmethod
    def _from_private_bytes(cls, payload: bytes) -> PreparationExecutionSigner:
        if type(payload) is not bytes or len(payload) != 32:
            raise PreparationError("execution signing key must contain exactly 32 bytes")
        signer = object.__new__(cls)
        key = Ed25519PrivateKey.from_private_bytes(payload)
        public_key = (
            key.public_key()
            .public_bytes(
                serialization.Encoding.Raw,
                serialization.PublicFormat.Raw,
            )
            .hex()
        )
        object.__setattr__(signer, "_key", key)
        object.__setattr__(signer, "public_key", public_key)
        return signer

    def sign(self, payload: bytes) -> str:
        return self._key.sign(payload).hex()


def load_protected_preparation_signer() -> PreparationExecutionSigner:
    """Load a root-owned, non-writable raw Ed25519 executor credential."""

    try:
        directory_descriptor = os.open(
            "/etc/ha-adjustable-bed",
            os.O_RDONLY
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_DIRECTORY", 0),
        )
    except OSError as error:
        raise PreparationError("protected executor directory is unavailable") from error
    try:
        directory = os.fstat(directory_descriptor)
        if (
            not stat.S_ISDIR(directory.st_mode)
            or directory.st_uid != 0
            or stat.S_IMODE(directory.st_mode) & 0o022
        ):
            raise PreparationError("protected executor directory is not root-owned and immutable")
        try:
            descriptor = os.open(
                "phase4-v2-preparation-executor.ed25519",
                os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=directory_descriptor,
            )
        except OSError as error:
            raise PreparationError("protected executor credential is unavailable") from error
        try:
            before = os.fstat(descriptor)
            if (
                not stat.S_ISREG(before.st_mode)
                or before.st_uid != 0
                or stat.S_IMODE(before.st_mode) & 0o077
                or before.st_size != 32
            ):
                raise PreparationError(
                    "execution signing key must be a root-owned mode-0600-or-stricter regular file"
                )
            payload = os.read(descriptor, 33)
            after = os.fstat(descriptor)
        finally:
            os.close(descriptor)
        current_directory = os.fstat(directory_descriptor)
        if (directory.st_dev, directory.st_ino) != (
            current_directory.st_dev,
            current_directory.st_ino,
        ):
            raise PreparationError("protected executor directory changed while reading credential")
    finally:
        os.close(directory_descriptor)
    if len(payload) != 32 or (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
    ) != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
        raise PreparationError("execution signing key changed while reading")
    return PreparationExecutionSigner._from_private_bytes(payload)


def _execution_attestation_bytes(
    *,
    authority_sha256: str,
    artifact_digest: str,
    preflight_manifest_sha256: str,
    registry_sha256: str,
    execution_profile_sha256: str,
    pipeline_revision: str,
    manifest_sha256: str,
    candidate_index_sha256: str,
) -> bytes:
    return b"phase4-v2:execution-attestation\0" + _canonical_json(
        {
            "artifact_digest": artifact_digest,
            "authority_sha256": authority_sha256,
            "candidate_index_sha256": candidate_index_sha256,
            "execution_profile_sha256": execution_profile_sha256,
            "manifest_sha256": manifest_sha256,
            "pipeline_revision": pipeline_revision,
            "preflight_manifest_sha256": preflight_manifest_sha256,
            "registry_sha256": registry_sha256,
            "revision": EXECUTION_ATTESTATION_REVISION,
        }
    )


def _verify_ed25519(public_key: str, signature: str, payload: bytes) -> bool:
    if (
        type(public_key) is not str
        or _ED25519_PUBLIC_KEY.fullmatch(public_key) is None
        or type(signature) is not str
        or _ED25519_SIGNATURE.fullmatch(signature) is None
    ):
        return False
    try:
        Ed25519PublicKey.from_public_bytes(bytes.fromhex(public_key)).verify(
            bytes.fromhex(signature), payload
        )
    except InvalidSignature, ValueError:
        return False
    return True


class _OutputValidationError(PreparationError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class _CandidateIndexError(PreparationError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class ExecutionLimits:
    """Resource limits applied to tool execution and derived outputs."""

    tool_timeout_seconds: float = 30 * 60
    version_timeout_seconds: float = 30
    max_tool_stream_bytes: int = 16 * 1024**2
    max_version_stream_bytes: int = 1024**2
    max_tool_binary_bytes: int = 2 * 1024**3
    max_runtime_files: int = 1_000_000
    max_runtime_file_bytes: int = 2 * 1024**3
    max_runtime_bytes: int = 16 * 1024**3
    max_invocations: int = 4_096
    max_output_files: int = 250_000
    max_total_output_files: int = 1_000_000
    max_output_nodes: int = 500_000
    max_output_path_bytes: int = 4_096
    max_output_file_bytes: int = 2 * 1024**3
    max_output_bytes: int = 16 * 1024**3
    max_warning_records: int = 4_096
    max_warning_line_bytes: int = 16 * 1024
    max_candidate_file_bytes: int = 128 * 1024**2
    max_candidate_bytes: int = 2 * 1024**3
    max_candidates: int = 250_000
    max_result_manifest_bytes: int = 256 * 1024**2
    max_candidate_index_bytes: int = 256 * 1024**2
    max_address_space_bytes: int = 8 * 1024**3
    max_processes: int = 4_096
    max_open_files: int = 1_024

    def validate(self) -> None:
        defaults = type(self)()
        for name in self.__dataclass_fields__:
            value = getattr(self, name)
            maximum = getattr(defaults, name)
            if name.endswith("_seconds"):
                if (
                    isinstance(value, bool)
                    or not isinstance(value, int | float)
                    or not math.isfinite(value)
                    or value <= 0
                    or value > maximum
                    or not float(value * 1_000).is_integer()
                ):
                    raise PreparationError(
                        "execution timeouts must be finite positive whole milliseconds "
                        "within the immutable profile ceiling"
                    )
            elif type(value) is not int or not 0 < value <= maximum:
                raise PreparationError(
                    "execution limits must be positive integers within immutable ceilings"
                )

    def to_data(self) -> dict[str, int]:
        self.validate()
        return {
            name: (
                int(getattr(self, name) * 1_000)
                if name.endswith("_seconds")
                else getattr(self, name)
            )
            for name in self.__dataclass_fields__
        }


@dataclass(frozen=True, slots=True)
class ExecutionProfile:
    """Exact executor, sandbox, and resource contract authorized for one run."""

    limits: ExecutionLimits
    executor_sha256: str
    executor_version: str
    revision: str = EXECUTION_PROFILE_REVISION
    sandbox_revision: str = SANDBOX_REVISION
    sha256: str = field(default="")

    def __post_init__(self) -> None:
        if type(self.limits) is not ExecutionLimits:
            raise PreparationError("execution profile limits must be exact ExecutionLimits")
        self.limits.validate()
        if self.revision != EXECUTION_PROFILE_REVISION:
            raise PreparationError("execution profile revision is unsupported")
        if self.sandbox_revision != SANDBOX_REVISION:
            raise PreparationError("execution sandbox revision is unsupported")
        if re.fullmatch(r"[0-9a-f]{64}", self.executor_sha256) is None:
            raise PreparationError("execution profile executor digest is invalid")
        if (
            type(self.executor_version) is not str
            or not self.executor_version
            or len(self.executor_version) > 16_384
            or any(value in self.executor_version for value in ("\x00", "\r", "\n"))
        ):
            raise PreparationError("execution profile executor version is invalid")
        expected = hashlib.sha256(_canonical_json(self.to_data(include_sha256=False))).hexdigest()
        if type(self.sha256) is not str:
            raise PreparationError("execution profile digest is invalid")
        if self.sha256:
            if self.sha256 != expected:
                raise PreparationError("execution profile digest is not canonical")
        else:
            object.__setattr__(self, "sha256", expected)

    def to_data(self, *, include_sha256: bool = True) -> dict[str, object]:
        result: dict[str, object] = {
            "executor": {
                "binary_sha256": self.executor_sha256,
                "name": "bubblewrap",
                "version": self.executor_version,
            },
            "limits": self.limits.to_data(),
            "revision": self.revision,
            "sandbox": {
                "host_filesystem": "NOT_MOUNTED",
                "network": "DISABLED",
                "output_allocation": "KERNEL_CAPPED_TMPFS",
                "process_namespace": "PRIVATE",
                "revision": self.sandbox_revision,
                "runtime_root": "SEALED_CONTENT_ADDRESSED",
                "writable_scope": "PRIVATE_WORKSPACE",
            },
        }
        if include_sha256:
            result["sha256"] = self.sha256
        return result


@dataclass(frozen=True, slots=True)
class ToolSpec:
    """A route's exact executable and deterministic argument contract."""

    executable: str
    version_arguments: tuple[str, ...]
    arguments: tuple[str, ...]
    flags: tuple[str, ...] = ()
    runtime_root: str | None = None

    def validate(self) -> None:
        if (
            type(self.executable) is not str
            or not self.executable
            or any(value in self.executable for value in ("\x00", "\r", "\n"))
            or type(self.version_arguments) is not tuple
            or type(self.arguments) is not tuple
            or type(self.flags) is not tuple
            or type(self.runtime_root) is not str
            or any(
                type(value) is not str
                for value in (*self.version_arguments, *self.arguments, *self.flags)
            )
        ):
            raise PreparationError("tool executable must be a non-empty path or command")
        runtime_root = Path(self.runtime_root)
        if (
            not runtime_root.is_absolute()
            or runtime_root == Path("/")
            or os.path.normpath(self.runtime_root) != self.runtime_root
        ):
            raise PreparationError(
                "tool runtime root must be an absolute canonical non-host-root path"
            )
        if not self.version_arguments:
            raise PreparationError("tool version arguments must not be empty")
        if len(self.version_arguments) > 128 or len(self.arguments) > 4_096:
            raise PreparationError("tool argument count exceeds the configured contract limit")
        try:
            invalid_argument = any(
                not value or "\x00" in value or len(value.encode("utf-8")) > 16 * 1024
                for value in (*self.version_arguments, *self.arguments)
            )
        except UnicodeEncodeError as error:
            raise PreparationError("tool argument is not valid Unicode") from error
        if invalid_argument:
            raise PreparationError("tool argument is empty, unsafe, or too large")
        if any(value in _PLACEHOLDERS for value in self.version_arguments):
            raise PreparationError("tool version arguments cannot contain path placeholders")
        placeholders = [value for value in self.arguments if value in _PLACEHOLDERS]
        if sorted(placeholders) != sorted(_PLACEHOLDERS):
            raise PreparationError("tool arguments must contain {input} and {output} exactly once")
        expected_flags = tuple(value for value in self.arguments if value.startswith("-"))
        if self.flags != expected_flags:
            raise PreparationError(
                "tool flags must exactly list argument tokens beginning with '-'"
            )


@dataclass(frozen=True, slots=True)
class StreamDigest:
    bytes: int
    sha256: str

    @classmethod
    def from_bytes(cls, payload: builtins.bytes) -> StreamDigest:
        return cls(len(payload), hashlib.sha256(payload).hexdigest())

    def to_data(self) -> dict[str, object]:
        return {"bytes": self.bytes, "sha256": self.sha256}


@dataclass(frozen=True, slots=True)
class ToolRecord:
    executable: str
    binary_bytes: int | None
    binary_sha256: str | None
    runtime_files: int | None
    runtime_sha256: str | None
    version_arguments: tuple[str, ...]
    version: str | None
    version_stdout: StreamDigest
    version_stderr: StreamDigest
    failure: str | None

    def to_data(self) -> dict[str, object]:
        return {
            "binary_bytes": self.binary_bytes,
            "binary_sha256": self.binary_sha256,
            "executable": self.executable,
            "failure": self.failure,
            "runtime_files": self.runtime_files,
            "runtime_sha256": self.runtime_sha256,
            "version": self.version,
            "version_arguments": list(self.version_arguments),
            "version_stderr": self.version_stderr.to_data(),
            "version_stdout": self.version_stdout.to_data(),
        }


@dataclass(frozen=True, slots=True)
class OutputMember:
    path: str
    bytes: int
    sha256: str

    def to_data(self) -> dict[str, object]:
        return {"bytes": self.bytes, "path": self.path, "sha256": self.sha256}


@dataclass(frozen=True, slots=True)
class WarningRecord:
    stream: Literal["stdout", "stderr"]
    line: int
    text: str
    sha256: str

    def to_data(self) -> dict[str, object]:
        return {
            "line": self.line,
            "sha256": self.sha256,
            "stream": self.stream,
            "text": self.text,
        }


@dataclass(frozen=True, slots=True)
class InvocationRecord:
    member: str
    input_sha256: str
    route: str
    cache_key: str | None
    tool: ToolRecord
    arguments: tuple[str, ...]
    flags: tuple[str, ...]
    status: Literal["COMPLETE", "FALLBACK", "BLOCKED"]
    exit_code: int | None
    stdout: StreamDigest
    stderr: StreamDigest
    warnings: tuple[WarningRecord, ...]
    failures: tuple[str, ...]
    outputs: tuple[OutputMember, ...]
    fallback_route: str | None = None
    fallback_reason: str | None = None

    def to_data(self) -> dict[str, object]:
        return {
            "arguments": list(self.arguments),
            "cache_key": self.cache_key,
            "exit_code": self.exit_code,
            "failures": list(self.failures),
            "fallback_route": self.fallback_route,
            "fallback_reason": self.fallback_reason,
            "flags": list(self.flags),
            "input_sha256": self.input_sha256,
            "member": self.member,
            "outputs": [output.to_data() for output in self.outputs],
            "route": self.route,
            "status": self.status,
            "stderr": self.stderr.to_data(),
            "stdout": self.stdout.to_data(),
            "tool": self.tool.to_data(),
            "warnings": [warning.to_data() for warning in self.warnings],
        }


@dataclass(frozen=True, slots=True)
class CandidateRecord:
    invocation_cache_key: str
    member: str
    route: str
    output_path: str
    output_sha256: str
    start_byte: int
    end_byte: int
    signal: str

    def to_data(self) -> dict[str, object]:
        return {
            "end_byte": self.end_byte,
            "invocation_cache_key": self.invocation_cache_key,
            "member": self.member,
            "output_path": self.output_path,
            "output_sha256": self.output_sha256,
            "route": self.route,
            "signal": self.signal,
            "start_byte": self.start_byte,
        }


@dataclass(frozen=True, slots=True)
class PreparationResult:
    output_directory: Path
    artifact_digest: str
    pipeline_revision: str
    execution_profile_sha256: str
    status: Literal["COMPLETE", "BLOCKED"]
    invocations: tuple[InvocationRecord, ...]
    candidates: tuple[CandidateRecord, ...]
    failures: tuple[str, ...]
    manifest_sha256: str
    candidate_index_sha256: str
    authority_sha256: str | None = None
    executor_public_key: str | None = None
    execution_signature: str | None = None


@dataclass(frozen=True, slots=True)
class _RunResult:
    exit_code: int | None
    stdout: bytes
    stderr: bytes
    failure: str | None


@dataclass(frozen=True, slots=True)
class _PreparedInvocation:
    record: InvocationRecord
    cache_directory: Path | None


@dataclass(slots=True)
class _SealedExecutable:
    path: Path
    descriptor: int
    binary_sha256: str
    binary_bytes: int
    runtime_root: Path
    runtime_sha256: str
    runtime_files: int
    sandbox_path: str
    snapshot_directory: Path | None = None
    runtime_descriptor: int | None = None

    def close(self) -> None:
        os.close(self.descriptor)
        if self.runtime_descriptor is not None:
            os.close(self.runtime_descriptor)
        if self.snapshot_directory is not None:
            shutil.rmtree(self.snapshot_directory, ignore_errors=True)


@dataclass(slots=True)
class _QuotaFilesystem:
    descriptor: int
    setup_userns_descriptor: int
    mountns_descriptor: int
    keeper: subprocess.Popen[bytes]
    control_descriptor: int
    mountpoint: Path

    @property
    def path(self) -> Path:
        return Path(f"/proc/{self.keeper.pid}/root/{self.mountpoint.relative_to('/')}")

    def close(self) -> None:
        os.close(self.control_descriptor)
        try:
            self.keeper.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.keeper.kill()
            self.keeper.wait()
        os.close(self.descriptor)
        os.close(self.setup_userns_descriptor)
        os.close(self.mountns_descriptor)
        shutil.rmtree(self.mountpoint, ignore_errors=True)


def _canonical_json(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _read_bounded(path: Path, limit: int) -> bytes:
    node = path.lstat()
    if not stat.S_ISREG(node.st_mode) or node.st_size > limit:
        raise PreparationCacheError(f"cache member is not a bounded regular file: {path.name}")
    descriptor = os.open(
        path,
        os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0),
    )
    try:
        payload = bytearray()
        while chunk := os.read(descriptor, min(_CHUNK, limit + 1 - len(payload))):
            payload.extend(chunk)
            if len(payload) > limit:
                raise PreparationCacheError(f"cache member exceeds byte limit: {path.name}")
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    if (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns) != (
        node.st_dev,
        node.st_ino,
        node.st_size,
        node.st_mtime_ns,
    ):
        raise PreparationCacheError(f"cache member changed while reading: {path.name}")
    return bytes(payload)


def _write_new_file(path: Path, payload: bytes) -> None:
    descriptor = os.open(
        path,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0),
        0o600,
    )
    try:
        view = memoryview(payload)
        while view:
            written = os.write(descriptor, view)
            view = view[written:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(
        path,
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_DIRECTORY", 0),
    )
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _create_quota_filesystem(limits: ExecutionLimits) -> _QuotaFilesystem:
    """Create a private tmpfs whose kernel limit covers visible and unlinked output."""

    mountpoint = Path(tempfile.mkdtemp(prefix="phase4-output-quota.", dir="/var/tmp"))
    ready_read, ready_write = os.pipe()
    control_read, control_write = os.pipe()
    try:
        keeper = subprocess.Popen(  # noqa: S603 - fixed interpreter and embedded helper
            (
                sys.executable,
                "-I",
                "-c",
                _QUOTA_KEEPER_SCRIPT,
                os.fspath(mountpoint),
                str(limits.max_output_bytes),
                str(limits.max_output_nodes),
                str(ready_write),
                str(control_read),
            ),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
            pass_fds=(ready_write, control_read),
            env={"LANG": "C.UTF-8", "LC_ALL": "C.UTF-8", "PATH": "/usr/bin:/bin"},
        )
    except OSError as error:
        for descriptor in (ready_read, ready_write, control_read, control_write):
            os.close(descriptor)
        shutil.rmtree(mountpoint, ignore_errors=True)
        raise PreparationError("kernel-enforced output quota helper is unavailable") from error
    os.close(ready_write)
    os.close(control_read)
    descriptor = setup_userns_descriptor = mountns_descriptor = -1
    with selectors.DefaultSelector() as selector:
        selector.register(ready_read, selectors.EVENT_READ)
        ready = bool(selector.select(timeout=min(5.0, limits.version_timeout_seconds)))
    try:
        response = os.read(ready_read, 128) if ready else b""
    finally:
        os.close(ready_read)
    if response != b"READY\n":
        os.close(control_write)
        try:
            keeper.wait(timeout=1)
        except subprocess.TimeoutExpired:
            keeper.kill()
            keeper.wait()
        shutil.rmtree(mountpoint, ignore_errors=True)
        raise PreparationError("kernel-enforced output quota is unavailable")
    try:
        descriptor = os.open(
            f"/proc/{keeper.pid}/root/{mountpoint.relative_to('/')}",
            os.O_RDONLY
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_DIRECTORY", 0),
        )
        setup_userns_descriptor = os.open(
            f"/proc/{keeper.pid}/ns/user",
            os.O_RDONLY | getattr(os, "O_CLOEXEC", 0),
        )
        mountns_descriptor = os.open(
            f"/proc/{keeper.pid}/ns/mnt",
            os.O_RDONLY | getattr(os, "O_CLOEXEC", 0),
        )
    except OSError as error:
        for opened_descriptor in (
            descriptor,
            setup_userns_descriptor,
            mountns_descriptor,
        ):
            if opened_descriptor >= 0:
                os.close(opened_descriptor)
        os.close(control_write)
        keeper.wait()
        shutil.rmtree(mountpoint, ignore_errors=True)
        raise PreparationError("kernel-enforced output quota is inaccessible") from error
    return _QuotaFilesystem(
        descriptor,
        setup_userns_descriptor,
        mountns_descriptor,
        keeper,
        control_write,
        mountpoint,
    )


def _sync_output_tree(root: Path, outputs: Sequence[OutputMember]) -> None:
    directories = {root}
    for output in outputs:
        path = root / output.path
        descriptor = os.open(
            path,
            os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0),
        )
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        parent = path.parent
        while True:
            directories.add(parent)
            if parent == root:
                break
            parent = parent.parent
    for directory in sorted(directories, key=lambda path: len(path.parts), reverse=True):
        _fsync_directory(directory)


def _validate_token(value: str, label: str) -> None:
    if _REVISION.fullmatch(value) is None:
        raise PreparationError(f"{label} must be a stable path-safe identifier")


def _safe_relative_path(value: str) -> str:
    candidate = PurePosixPath(value)
    if (
        candidate.is_absolute()
        or not candidate.parts
        or value != candidate.as_posix()
        or any(part in {"", ".", ".."} for part in candidate.parts)
        or any(character in value for character in ("\x00", "\r", "\n", "\\"))
    ):
        raise PreparationError(f"unsafe output path: {value!r}")
    return value


def _reject_symlink_ancestry(path: Path, label: str) -> None:
    current = path
    while True:
        try:
            node = current.lstat()
        except FileNotFoundError:
            pass
        else:
            if stat.S_ISLNK(node.st_mode):
                raise PreparationError(f"{label} contains a symlink ancestor")
        if current.parent == current:
            return
        current = current.parent


def _hash_file(path: Path, *, max_bytes: int) -> tuple[str, int]:
    before = path.lstat()
    if not stat.S_ISREG(before.st_mode) or before.st_size > max_bytes:
        raise PreparationError(f"file is not a bounded regular file: {path.name}")
    digest = hashlib.sha256()
    total = 0
    descriptor = os.open(
        path,
        os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0),
    )
    try:
        while chunk := os.read(descriptor, _CHUNK):
            total += len(chunk)
            if total > max_bytes:
                raise PreparationError(f"file exceeds byte limit: {path.name}")
            digest.update(chunk)
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    identity_before = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
    identity_after = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
    if identity_before != identity_after or total != before.st_size:
        raise PreparationError(f"file changed while hashing: {path.name}")
    return digest.hexdigest(), total


def _hash_descriptor(descriptor: int, *, max_bytes: int) -> tuple[str, int]:
    before = os.fstat(descriptor)
    if not stat.S_ISREG(before.st_mode) or before.st_size > max_bytes:
        raise PreparationError("descriptor is not a bounded regular file")
    digest = hashlib.sha256()
    total = 0
    offset = 0
    while chunk := os.pread(descriptor, _CHUNK, offset):
        total += len(chunk)
        if total > max_bytes:
            raise PreparationError("descriptor exceeds byte limit")
        digest.update(chunk)
        offset += len(chunk)
    after = os.fstat(descriptor)
    if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
    ) or total != before.st_size:
        raise PreparationError("descriptor changed while hashing")
    return digest.hexdigest(), total


def _stop_process(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, 15)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=1)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, 9)
        except ProcessLookupError:
            pass
        process.wait()


def _live_output_limit_failure(root_descriptor: int, limits: ExecutionLimits) -> str | None:
    """Cheap live quota check; the final inventory remains authoritative."""

    nodes = files = total = 0
    stack = [Path(f"/proc/self/fd/{root_descriptor}")]
    try:
        while stack:
            directory = stack.pop()
            with os.scandir(directory) as entries:
                for child in entries:
                    nodes += 1
                    if nodes > limits.max_output_nodes:
                        return "OUTPUT_NODE_LIMIT"
                    node = child.stat(follow_symlinks=False)
                    if stat.S_ISDIR(node.st_mode):
                        stack.append(Path(child.path))
                    elif stat.S_ISREG(node.st_mode):
                        files += 1
                        total += node.st_size
                        if files > limits.max_output_files:
                            return "OUTPUT_FILE_LIMIT"
                        if node.st_size > limits.max_output_file_bytes:
                            return "OUTPUT_MEMBER_BYTE_LIMIT"
                        if total > limits.max_output_bytes:
                            return "OUTPUT_AGGREGATE_BYTE_LIMIT"
                    else:
                        return "OUTPUT_UNSAFE_NODE"
    except FileNotFoundError:
        return "OUTPUT_DIRECTORY_INVALID"
    return None


def _run_bounded(
    arguments: Sequence[str],
    *,
    cwd: Path,
    environment: Mapping[str, str],
    timeout: float,
    stream_limit: int,
    pass_fds: tuple[int, ...] = (),
    limits: ExecutionLimits | None = None,
    monitored_output_descriptor: int | None = None,
    user_namespace_descriptor: int | None = None,
    mount_namespace_descriptor: int | None = None,
) -> _RunResult:
    process: subprocess.Popen[bytes] | None = None
    stdout = bytearray()
    stderr = bytearray()
    streams: dict[int, tuple[Literal["stdout", "stderr"], bytearray]] = {}
    try:

        def apply_limits() -> None:
            if user_namespace_descriptor is not None:
                if mount_namespace_descriptor is None:
                    raise OSError("mount namespace descriptor is missing")
                os.setns(user_namespace_descriptor, os.CLONE_NEWUSER)
                os.setns(mount_namespace_descriptor, os.CLONE_NEWNS)
            if limits is None:
                return
            resource.setrlimit(
                resource.RLIMIT_AS,
                (limits.max_address_space_bytes, limits.max_address_space_bytes),
            )
            resource.setrlimit(resource.RLIMIT_NPROC, (limits.max_processes, limits.max_processes))
            resource.setrlimit(
                resource.RLIMIT_NOFILE, (limits.max_open_files, limits.max_open_files)
            )
            resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
            resource.setrlimit(
                resource.RLIMIT_FSIZE,
                (limits.max_output_file_bytes, limits.max_output_file_bytes),
            )

        process = subprocess.Popen(  # noqa: S603 - executable is held open and content-addressed
            list(arguments),
            cwd=cwd,
            env=dict(environment),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
            pass_fds=pass_fds,
            preexec_fn=apply_limits,
        )
        assert process.stdout is not None and process.stderr is not None
        streams = {
            process.stdout.fileno(): ("stdout", stdout),
            process.stderr.fileno(): ("stderr", stderr),
        }
        deadline = time.monotonic() + timeout
        with selectors.DefaultSelector() as selector:
            for descriptor in streams:
                selector.register(descriptor, selectors.EVENT_READ)
            while selector.get_map():
                remaining = deadline - time.monotonic()
                events = selector.select(min(0.05, max(0.0, remaining))) if remaining > 0 else []
                if monitored_output_descriptor is not None and limits is not None:
                    output_failure = _live_output_limit_failure(monitored_output_descriptor, limits)
                    if output_failure is not None:
                        _stop_process(process)
                        return _RunResult(None, bytes(stdout), bytes(stderr), output_failure)
                if not events and remaining <= 0:
                    _stop_process(process)
                    return _RunResult(None, bytes(stdout), bytes(stderr), "TOOL_TIMEOUT")
                for key, _mask in events:
                    descriptor = key.fd
                    _stream, target = streams[descriptor]
                    chunk = os.read(descriptor, min(64 * 1024, stream_limit + 1 - len(target)))
                    if not chunk:
                        selector.unregister(descriptor)
                        continue
                    target.extend(chunk)
                    if len(target) > stream_limit:
                        _stop_process(process)
                        return _RunResult(None, bytes(stdout), bytes(stderr), "TOOL_OUTPUT_LIMIT")
        process.wait(timeout=max(0.0, deadline - time.monotonic()))
        return _RunResult(process.returncode, bytes(stdout), bytes(stderr), None)
    except OSError, subprocess.SubprocessError:
        if process is not None:
            _stop_process(process)
        return _RunResult(None, bytes(stdout), bytes(stderr), "TOOL_EXECUTION_FAILED")
    finally:
        if process is not None:
            if process.stdout is not None:
                process.stdout.close()
            if process.stderr is not None:
                process.stderr.close()


def _controlled_environment(workspace: Path) -> dict[str, str]:
    return {
        "HOME": str(workspace / "home"),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PATH": "/usr/bin:/bin",
        "PYTHONHASHSEED": "0",
        "SOURCE_DATE_EPOCH": "0",
        "TMPDIR": str(workspace / "tmp"),
        "TZ": "UTC",
    }


def _open_executable(path: Path, max_bytes: int) -> tuple[int, str, int]:
    descriptor = os.open(
        path,
        os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0),
    )
    try:
        node = os.fstat(descriptor)
        if not stat.S_ISREG(node.st_mode) or not node.st_mode & 0o111:
            raise PreparationError("executable is not a regular executable file")
        digest, size = _hash_descriptor(descriptor, max_bytes=max_bytes)
    except BaseException:
        os.close(descriptor)
        raise
    return descriptor, digest, size


def _resolve_bwrap(limits: ExecutionLimits) -> tuple[Path, int, str, int]:
    executable = next((shutil.which(name) for name in _BWRAP_NAMES if shutil.which(name)), None)
    if executable is None:
        raise PreparationError("bubblewrap is required for secure preparation execution")
    path = Path(executable).resolve(strict=True)
    descriptor, digest, size = _open_executable(path, limits.max_tool_binary_bytes)
    return path, descriptor, digest, size


def build_execution_profile(limits: ExecutionLimits | None = None) -> ExecutionProfile:
    """Qualify the mandatory local sandbox executor into a canonical profile."""

    selected = limits or ExecutionLimits()
    selected.validate()
    _path, descriptor, digest, _size = _resolve_bwrap(selected)
    try:
        run = _run_bounded(
            (f"/proc/self/fd/{descriptor}", "--version"),
            cwd=Path("/"),
            environment={"LANG": "C.UTF-8", "LC_ALL": "C.UTF-8", "PATH": "/usr/bin:/bin"},
            timeout=selected.version_timeout_seconds,
            stream_limit=selected.max_version_stream_bytes,
            pass_fds=(descriptor,),
            limits=selected,
        )
    finally:
        os.close(descriptor)
    if run.failure is not None or run.exit_code != 0:
        raise PreparationError("bubblewrap qualification failed")
    raw_version = run.stdout.strip() or run.stderr.strip()
    try:
        version = raw_version.decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise PreparationError("bubblewrap version is not UTF-8") from error
    if not version:
        raise PreparationError("bubblewrap version is empty")
    return ExecutionProfile(selected, digest, version)


def _open_profile_executor(profile: ExecutionProfile) -> int:
    _path, descriptor, digest, _size = _resolve_bwrap(profile.limits)
    if digest != profile.executor_sha256:
        os.close(descriptor)
        raise PreparationError("sandbox executor no longer matches the execution profile")
    return descriptor


def _run_sandboxed(
    executable: _SealedExecutable,
    arguments: Sequence[str],
    *,
    workspace: Path,
    profile: ExecutionProfile,
    timeout: float,
    stream_limit: int,
    workspace_identity: tuple[int, int] | None = None,
    monitor_output: bool = False,
    quota_output_descriptor: int | None = None,
    quota_setup_userns_descriptor: int | None = None,
    quota_mountns_descriptor: int | None = None,
) -> _RunResult:
    workspace_descriptor = -1
    output_descriptor = -1
    executor_descriptor = -1
    try:
        workspace_descriptor = os.open(
            workspace,
            os.O_RDONLY
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_DIRECTORY", 0),
        )
        if monitor_output and quota_output_descriptor is None:
            output_descriptor = os.open(
                workspace / "output",
                os.O_RDONLY
                | getattr(os, "O_CLOEXEC", 0)
                | getattr(os, "O_NOFOLLOW", 0)
                | getattr(os, "O_DIRECTORY", 0),
            )
        executor_descriptor = _open_profile_executor(profile)
        workspace_node = os.fstat(workspace_descriptor)
        if (
            workspace_identity is not None
            and (
                workspace_node.st_dev,
                workspace_node.st_ino,
            )
            != workspace_identity
        ):
            raise PreparationError("execution workspace identity changed before sandbox entry")
        environment = _controlled_environment(Path("/run"))
        sandbox_executable = executable.sandbox_path
        command = [
            f"/proc/self/fd/{executor_descriptor}",
            "--unshare-user",
            "--unshare-all",
            "--disable-userns",
        ]
        command.extend(
            (
                "--die-with-parent",
                "--new-session",
                "--cap-drop",
                "ALL",
                "--ro-bind-fd",
                str(executable.runtime_descriptor),
                "/",
                "--proc",
                "/proc",
                "--dev",
                "/dev",
                "--bind-fd",
                str(workspace_descriptor),
                "/run",
            )
        )
        if quota_output_descriptor is not None:
            command.extend(("--bind-fd", str(quota_output_descriptor), "/run/output"))
        if executable.runtime_descriptor is None:
            raise PreparationError("sealed runtime root is missing")
        command.extend(("--clearenv",))
        for name, value in sorted(environment.items()):
            command.extend(("--setenv", name, value))
        command.extend(("--chdir", "/run", "--", sandbox_executable, *arguments))
        return _run_bounded(
            command,
            cwd=Path("/"),
            environment={"LANG": "C.UTF-8", "LC_ALL": "C.UTF-8", "PATH": "/usr/bin:/bin"},
            timeout=timeout,
            stream_limit=stream_limit,
            pass_fds=tuple(
                descriptor
                for descriptor in (
                    executor_descriptor,
                    workspace_descriptor,
                    executable.descriptor,
                    executable.runtime_descriptor,
                    quota_output_descriptor,
                    quota_setup_userns_descriptor,
                    quota_mountns_descriptor,
                )
                if descriptor is not None
            ),
            limits=profile.limits,
            monitored_output_descriptor=(
                quota_output_descriptor
                if monitor_output and quota_output_descriptor is not None
                else output_descriptor
                if monitor_output
                else None
            ),
            user_namespace_descriptor=quota_setup_userns_descriptor,
            mount_namespace_descriptor=quota_mountns_descriptor,
        )
    finally:
        for descriptor in (executor_descriptor, workspace_descriptor, output_descriptor):
            if descriptor >= 0:
                os.close(descriptor)


def _copy_runtime_file_at(
    source_directory_descriptor: int,
    name: str,
    destination: Path,
    limit: int,
    expected: os.stat_result | None = None,
) -> tuple[str, int]:
    source_descriptor = os.open(
        name,
        os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0),
        dir_fd=source_directory_descriptor,
    )
    destination_descriptor = -1
    try:
        before = os.fstat(source_descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_size > limit:
            raise PreparationError("runtime closure contains an invalid file")
        if expected is not None and _runtime_metadata(before) != _runtime_metadata(expected):
            raise PreparationError("runtime closure changed while sealing")
        destination_descriptor = os.open(
            destination,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0),
            stat.S_IMODE(before.st_mode) & 0o777,
        )
        digest = hashlib.sha256()
        total = 0
        offset = 0
        while chunk := os.pread(source_descriptor, _CHUNK, offset):
            total += len(chunk)
            if total > limit:
                raise PreparationError("runtime closure exceeds its byte limit")
            digest.update(chunk)
            view = memoryview(chunk)
            while view:
                written = os.write(destination_descriptor, view)
                view = view[written:]
            offset += len(chunk)
        os.fsync(destination_descriptor)
        after = os.fstat(source_descriptor)
        if _runtime_metadata(before) != _runtime_metadata(after):
            raise PreparationError("runtime closure changed while sealing")
        return digest.hexdigest(), total
    finally:
        if destination_descriptor >= 0:
            os.close(destination_descriptor)
        os.close(source_descriptor)


def _runtime_metadata(node: os.stat_result) -> tuple[int, ...]:
    return (
        node.st_dev,
        node.st_ino,
        node.st_mode,
        node.st_nlink,
        node.st_size,
        node.st_mtime_ns,
        node.st_ctime_ns,
    )


def _seal_executable(path: Path, runtime_root: str, limits: ExecutionLimits) -> _SealedExecutable:
    original_descriptor, binary_sha256, binary_bytes = _open_executable(
        path, limits.max_tool_binary_bytes
    )
    requested_root = Path(runtime_root)
    _reject_symlink_ancestry(requested_root, "tool runtime root")
    source_root = requested_root.resolve(strict=True)
    if not source_root.is_dir() or source_root.is_symlink():
        os.close(original_descriptor)
        raise PreparationError("tool runtime root must be a regular directory")
    try:
        executable_relative = path.relative_to(source_root).as_posix()
    except ValueError as error:
        os.close(original_descriptor)
        raise PreparationError("tool executable must be contained by its runtime root") from error
    os.close(original_descriptor)
    snapshot_directory = Path(tempfile.mkdtemp(prefix="phase4-runtime.", dir="/var/tmp"))
    snapshot_root = snapshot_directory / "root"
    snapshot_root.mkdir(mode=0o700)
    inventory: list[dict[str, object]] = []
    total = 0
    nodes = 0
    try:
        source_descriptor = os.open(
            source_root,
            os.O_RDONLY
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_DIRECTORY", 0),
        )

        def seal_directory(
            source_directory_descriptor: int,
            target_directory: Path,
            relative_parent: PurePosixPath,
            depth: int,
        ) -> None:
            nonlocal nodes, total
            if depth > 256:
                raise PreparationError("runtime closure directory depth limit exceeded")
            before = os.fstat(source_directory_descriptor)
            with os.scandir(source_directory_descriptor) as entries:
                children = sorted(entries, key=lambda item: item.name)
            initial_names = tuple(child.name for child in children)
            for child in children:
                nodes += 1
                if nodes > limits.max_runtime_files:
                    raise PreparationError("runtime closure node limit exceeded")
                node = child.stat(follow_symlinks=False)
                relative = (relative_parent / child.name).as_posix()
                target = target_directory / child.name
                if stat.S_ISDIR(node.st_mode):
                    child_descriptor = os.open(
                        child.name,
                        os.O_RDONLY
                        | getattr(os, "O_CLOEXEC", 0)
                        | getattr(os, "O_NOFOLLOW", 0)
                        | getattr(os, "O_DIRECTORY", 0),
                        dir_fd=source_directory_descriptor,
                    )
                    try:
                        opened = os.fstat(child_descriptor)
                        if _runtime_metadata(node) != _runtime_metadata(opened):
                            raise PreparationError("runtime closure changed while sealing")
                        target.mkdir(mode=stat.S_IMODE(opened.st_mode) & 0o777)
                        inventory.append(
                            {
                                "bytes": 0,
                                "mode": stat.S_IMODE(opened.st_mode),
                                "path": relative,
                                "sha256": None,
                            }
                        )
                        seal_directory(
                            child_descriptor,
                            target,
                            relative_parent / child.name,
                            depth + 1,
                        )
                    finally:
                        os.close(child_descriptor)
                    continue
                if not stat.S_ISREG(node.st_mode):
                    raise PreparationError("runtime closure contains a symlink or special node")
                digest, size = _copy_runtime_file_at(
                    source_directory_descriptor,
                    child.name,
                    target,
                    limits.max_runtime_file_bytes,
                    node,
                )
                total += size
                if total > limits.max_runtime_bytes:
                    raise PreparationError("runtime closure aggregate byte limit exceeded")
                inventory.append(
                    {
                        "bytes": size,
                        "mode": stat.S_IMODE(node.st_mode),
                        "path": relative,
                        "sha256": digest,
                    }
                )
            after = os.fstat(source_directory_descriptor)
            with os.scandir(source_directory_descriptor) as entries:
                final_names = tuple(sorted(entry.name for entry in entries))
            if (
                _runtime_metadata(before) != _runtime_metadata(after)
                or initial_names != final_names
            ):
                raise PreparationError("runtime closure directory changed while sealing")

        try:
            seal_directory(source_descriptor, snapshot_root, PurePosixPath(), 0)
        finally:
            os.close(source_descriptor)
        inventory.sort(key=lambda item: str(item["path"]))
        runtime_sha256 = hashlib.sha256(_canonical_json(inventory)).hexdigest()
        for relative in ("run", "tmp", "home", "var", "var/tmp", "proc", "dev"):
            (snapshot_root / relative).mkdir(mode=0o700, parents=True, exist_ok=True)
        sealed_path = snapshot_root / executable_relative
        sealed_descriptor, sealed_sha256, sealed_bytes = _open_executable(
            sealed_path, limits.max_tool_binary_bytes
        )
        if (sealed_sha256, sealed_bytes) != (binary_sha256, binary_bytes):
            os.close(sealed_descriptor)
            raise PreparationError("sealed executable identity mismatch")
        runtime_descriptor = os.open(
            snapshot_root,
            os.O_RDONLY
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_DIRECTORY", 0),
        )
        return _SealedExecutable(
            path,
            sealed_descriptor,
            binary_sha256,
            binary_bytes,
            snapshot_root,
            runtime_sha256,
            sum(item["sha256"] is not None for item in inventory),
            "/" + executable_relative,
            snapshot_directory,
            runtime_descriptor,
        )
    except BaseException:
        shutil.rmtree(snapshot_directory, ignore_errors=True)
        raise


def _tool_record(
    spec: ToolSpec,
    workspace: Path,
    limits: ExecutionLimits,
    profile: ExecutionProfile,
) -> tuple[ToolRecord, _SealedExecutable | None]:
    requested_name = Path(spec.executable).name
    empty = StreamDigest.from_bytes(b"")
    executable = shutil.which(spec.executable)
    if executable is None:
        return (
            ToolRecord(
                executable=requested_name,
                binary_bytes=None,
                binary_sha256=None,
                runtime_files=None,
                runtime_sha256=None,
                version_arguments=spec.version_arguments,
                version=None,
                version_stdout=empty,
                version_stderr=empty,
                failure="TOOL_NOT_FOUND",
            ),
            None,
        )
    try:
        binary = Path(executable).resolve(strict=True)
        assert spec.runtime_root is not None
        sealed = _seal_executable(binary, spec.runtime_root, limits)
    except OSError, PreparationError:
        return (
            ToolRecord(
                executable=requested_name,
                binary_bytes=None,
                binary_sha256=None,
                runtime_files=None,
                runtime_sha256=None,
                version_arguments=spec.version_arguments,
                version=None,
                version_stdout=empty,
                version_stderr=empty,
                failure="TOOL_BINARY_INVALID",
            ),
            None,
        )
    run = _run_sandboxed(
        sealed,
        spec.version_arguments,
        workspace=workspace,
        profile=profile,
        timeout=limits.version_timeout_seconds,
        stream_limit=limits.max_version_stream_bytes,
        workspace_identity=(workspace.stat().st_dev, workspace.stat().st_ino),
    )
    failure = run.failure
    if failure is None and run.exit_code != 0:
        failure = "TOOL_VERSION_EXIT_NONZERO"
    version: str | None = None
    if failure is None:
        raw_version = run.stdout.strip() or run.stderr.strip()
        try:
            version = raw_version.decode("utf-8", errors="strict")
        except UnicodeDecodeError:
            failure = "TOOL_VERSION_NON_UTF8"
        else:
            if not version:
                failure = "TOOL_VERSION_EMPTY"
        if failure is not None:
            version = None
    return (
        ToolRecord(
            executable=requested_name,
            binary_bytes=sealed.binary_bytes,
            binary_sha256=sealed.binary_sha256,
            runtime_files=sealed.runtime_files,
            runtime_sha256=sealed.runtime_sha256,
            version_arguments=spec.version_arguments,
            version=version,
            version_stdout=StreamDigest.from_bytes(run.stdout),
            version_stderr=StreamDigest.from_bytes(run.stderr),
            failure=failure,
        ),
        sealed,
    )


def qualify_tool(spec: ToolSpec, execution_profile: ExecutionProfile) -> ToolRecord:
    """Return the exact sandboxed build/runtime identity used by execution."""

    if type(spec) is not ToolSpec or type(execution_profile) is not ExecutionProfile:
        raise PreparationError("tool qualification requires exact trusted contract types")
    spec.validate()
    execution_profile.__post_init__()
    workspace = Path(tempfile.mkdtemp(prefix="phase4-qualification.", dir="/var/tmp"))
    sealed: _SealedExecutable | None = None
    try:
        for name in ("home", "tmp"):
            (workspace / name).mkdir(mode=0o700)
        record, sealed = _tool_record(spec, workspace, execution_profile.limits, execution_profile)
        return record
    finally:
        if sealed is not None:
            sealed.close()
        shutil.rmtree(workspace, ignore_errors=True)


def _warning_records(
    stdout: bytes, stderr: bytes, limits: ExecutionLimits
) -> tuple[WarningRecord, ...]:
    records: list[WarningRecord] = []
    streams: tuple[tuple[Literal["stdout", "stderr"], bytes], ...] = (
        ("stdout", stdout),
        ("stderr", stderr),
    )
    for stream_name, payload in streams:
        for line_number, line in enumerate(payload.splitlines(), start=1):
            if _DIAGNOSTIC_LINE.search(line) is None:
                continue
            if len(records) >= limits.max_warning_records:
                raise PreparationError("tool warning record limit exceeded")
            if len(line) > limits.max_warning_line_bytes:
                raise PreparationError("tool warning line limit exceeded")
            records.append(
                WarningRecord(
                    stream_name,
                    line_number,
                    line.decode("utf-8", errors="backslashreplace"),
                    hashlib.sha256(line).hexdigest(),
                )
            )
    return tuple(records)


def _output_members(output: Path, limits: ExecutionLimits) -> tuple[OutputMember, ...]:
    if not output.is_dir() or output.is_symlink():
        raise _OutputValidationError("OUTPUT_DIRECTORY_INVALID")
    paths: list[Path] = []
    stack = [output]
    nodes = 0
    while stack:
        directory = stack.pop()
        with os.scandir(directory) as entries:
            children = sorted(entries, key=lambda entry: entry.name)
        for child in children:
            nodes += 1
            if nodes > limits.max_output_nodes:
                raise _OutputValidationError("OUTPUT_NODE_LIMIT")
            node = child.stat(follow_symlinks=False)
            if stat.S_ISLNK(node.st_mode) or not (
                stat.S_ISDIR(node.st_mode) or stat.S_ISREG(node.st_mode)
            ):
                raise _OutputValidationError("OUTPUT_UNSAFE_NODE")
            path = Path(child.path)
            relative = _safe_relative_path(path.relative_to(output).as_posix())
            if len(relative.encode("utf-8")) > limits.max_output_path_bytes:
                raise _OutputValidationError("OUTPUT_PATH_LIMIT")
            if stat.S_ISDIR(node.st_mode):
                stack.append(path)
                continue
            paths.append(path)
            if len(paths) > limits.max_output_files:
                raise _OutputValidationError("OUTPUT_FILE_LIMIT")
            if node.st_size > limits.max_output_file_bytes:
                raise _OutputValidationError("OUTPUT_MEMBER_BYTE_LIMIT")
    paths.sort(key=lambda path: path.relative_to(output).as_posix())
    relative_paths = [path.relative_to(output).as_posix() for path in paths]
    if len({path.casefold() for path in relative_paths}) != len(relative_paths):
        raise _OutputValidationError("OUTPUT_CASE_AMBIGUOUS")
    total = 0
    records: list[OutputMember] = []
    for path, relative in zip(paths, relative_paths, strict=True):
        digest, size = _hash_file(path, max_bytes=limits.max_output_file_bytes)
        total += size
        if total > limits.max_output_bytes:
            raise _OutputValidationError("OUTPUT_AGGREGATE_BYTE_LIMIT")
        records.append(OutputMember(relative, size, digest))
    if not records:
        raise _OutputValidationError("OUTPUT_EMPTY")
    return tuple(records)


def _materialize_quota_output(
    quota: _QuotaFilesystem,
    destination: Path,
    limits: ExecutionLimits,
) -> None:
    """Copy the quiescent, quota-backed output into the durable workspace."""

    for output in _output_members(quota.path, limits):
        relative = PurePosixPath(output.path)
        target_parent = destination.joinpath(*relative.parts[:-1])
        target_parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        source_parent = quota.path.joinpath(*relative.parts[:-1])
        source_descriptor = os.open(
            source_parent,
            os.O_RDONLY
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_DIRECTORY", 0),
        )
        try:
            digest, size = _copy_runtime_file_at(
                source_descriptor,
                relative.name,
                target_parent / relative.name,
                limits.max_output_file_bytes,
            )
        finally:
            os.close(source_descriptor)
        if (digest, size) != (output.sha256, output.bytes):
            raise PreparationError("quota-backed output changed during materialization")


def _copy_input(member: ArtifactMember, destination: Path) -> None:
    descriptor = os.open(
        destination,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0),
        0o400,
    )
    digest = hashlib.sha256()
    total = 0
    offset = 0
    try:
        while chunk := os.pread(member._sealed_fd, _CHUNK, offset):
            view = memoryview(chunk)
            while view:
                written = os.write(descriptor, view)
                view = view[written:]
            digest.update(chunk)
            total += len(chunk)
            offset += len(chunk)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    if total != member.size or digest.hexdigest() != member.sha256:
        raise PreparationError("sealed preflight member identity changed")


def _invocation_key(
    *,
    artifact_digest: str,
    member: ArtifactMember,
    route: str,
    tool: ToolRecord,
    spec: ToolSpec,
    pipeline_revision: str,
    tool_registry_sha256: str | None,
    execution_profile_sha256: str,
) -> str:
    return hashlib.sha256(
        _canonical_json(
            {
                "cache_schema": EXECUTION_CACHE_SCHEMA,
                "candidate_index_schema": CANDIDATE_INDEX_SCHEMA,
                "candidate_contract_sha256": CANDIDATE_CONTRACT_SHA256,
                "artifact_digest": artifact_digest,
                "input_sha256": member.sha256,
                "member": member.name,
                "pipeline_revision": pipeline_revision,
                "execution_profile_sha256": execution_profile_sha256,
                "tool_registry_sha256": tool_registry_sha256,
                "preflight_schema": PREFLIGHT_SCHEMA,
                "route": route,
                "tool": tool.to_data(),
                "arguments": list(_normalized_arguments(spec)),
                "flags": list(spec.flags),
            }
        )
    ).hexdigest()


def _normalized_arguments(spec: ToolSpec) -> tuple[str, ...]:
    return tuple(
        "input.apk" if value == "{input}" else "output" if value == "{output}" else value
        for value in spec.arguments
    )


class PreparationCache:
    """Content-addressed cache of complete package-local tool invocations."""

    def __init__(
        self,
        root: Path | str,
        *,
        signer: PreparationExecutionSigner | None = None,
        verification_public_key: str | None = None,
    ) -> None:
        if signer is not None and type(signer) is not PreparationExecutionSigner:
            raise PreparationError("cache signer must be an exact executor credential")
        if signer is not None:
            verification_public_key = signer.public_key
        if verification_public_key is not None and (
            type(verification_public_key) is not str
            or _ED25519_PUBLIC_KEY.fullmatch(verification_public_key) is None
        ):
            raise PreparationError("cache verification key is invalid")
        self.signer = signer
        self.verification_public_key = verification_public_key
        self.root = Path(os.path.abspath(os.fspath(root)))
        _reject_symlink_ancestry(self.root, "preparation cache root")
        self.objects = self.root / "objects" / EXECUTION_CACHE_SCHEMA
        self.work = self.root / "work"
        self.objects.mkdir(parents=True, exist_ok=True)
        self.work.mkdir(parents=True, exist_ok=True)
        for directory in (self.root, self.objects, self.work):
            node = directory.lstat()
            if not stat.S_ISDIR(node.st_mode) or stat.S_ISLNK(node.st_mode):
                raise PreparationError("preparation cache path is not a regular directory")

    def _object(self, key: str) -> Path:
        if re.fullmatch(r"[0-9a-f]{64}", key) is None:
            raise PreparationCacheError("invalid preparation cache key")
        return self.objects / key

    def load(
        self, key: str, expected: InvocationRecord, limits: ExecutionLimits
    ) -> _PreparedInvocation | None:
        target = self._object(key)
        trusted = _TRUSTED_CACHE_OBJECTS.get(os.fspath(target))
        if trusted is None and self.verification_public_key is None:
            return None
        try:
            target_stat = target.lstat()
        except FileNotFoundError:
            return None
        if not stat.S_ISDIR(target_stat.st_mode) or stat.S_ISLNK(target_stat.st_mode):
            raise PreparationCacheError("cache object is not a regular directory")
        if trusted is not None and (target_stat.st_dev, target_stat.st_ino) != trusted[:2]:
            raise PreparationCacheError("trusted cache object identity changed")
        try:
            names = {entry.name for entry in os.scandir(target)}
            expected_names = {
                "OBJECT.COMPLETE",
                "manifest.json",
                "outputs",
                "stderr.bin",
                "stdout.bin",
            }
            if self.verification_public_key is not None:
                expected_names.add("OBJECT.SIGNATURE")
            if names != expected_names:
                raise PreparationCacheError("cache object contains unexpected payloads")
            manifest_payload = _read_bounded(target / "manifest.json", _MAX_CACHE_MANIFEST_BYTES)
            marker = _read_bounded(target / "OBJECT.COMPLETE", 256).decode("ascii").strip().split()
            if marker != [hashlib.sha256(manifest_payload).hexdigest(), "manifest.json"]:
                raise PreparationCacheError("cache manifest seal mismatch")
            manifest_digest = hashlib.sha256(manifest_payload).hexdigest()
            if self.verification_public_key is not None:
                signature = _read_bounded(target / "OBJECT.SIGNATURE", 256).decode("ascii").strip()
                signed = b"phase4-v2:cache-object\0" + manifest_digest.encode("ascii")
                if not _verify_ed25519(self.verification_public_key, signature, signed):
                    raise PreparationCacheError("cache object signature is invalid")
            else:
                assert trusted is not None
                if manifest_digest != trusted[2]:
                    raise PreparationCacheError("trusted cache manifest changed")
            raw = json.loads(manifest_payload, object_pairs_hook=_reject_duplicate_keys)
            if (
                not isinstance(raw, dict)
                or set(raw) != {"schema", "invocation"}
                or raw.get("schema") != EXECUTION_CACHE_SCHEMA
            ):
                raise PreparationCacheError("cache manifest schema mismatch")
            record_data = raw.get("invocation")
            if not isinstance(record_data, dict):
                raise PreparationCacheError("cache invocation manifest is invalid")
            stdout = _read_bounded(target / "stdout.bin", limits.max_tool_stream_bytes)
            stderr = _read_bounded(target / "stderr.bin", limits.max_tool_stream_bytes)
            outputs = _output_members(target / "outputs", limits)
            loaded = replace(
                expected,
                stdout=StreamDigest.from_bytes(stdout),
                stderr=StreamDigest.from_bytes(stderr),
                warnings=_warning_records(stdout, stderr, limits),
                outputs=outputs,
            )
            if record_data != loaded.to_data():
                raise PreparationCacheError("cache invocation identity mismatch")
            return _PreparedInvocation(loaded, target)
        except PreparationCacheError:
            raise
        except (OSError, UnicodeError, ValueError, json.JSONDecodeError, PreparationError) as err:
            raise PreparationCacheError("cache object is invalid") from err


def _execute_one(
    *,
    cache: PreparationCache,
    artifact_digest: str,
    member: ArtifactMember,
    route: str,
    spec: ToolSpec,
    tool: ToolRecord,
    binary: _SealedExecutable | None,
    pipeline_revision: str,
    tool_registry_sha256: str | None,
    limits: ExecutionLimits,
    execution_profile: ExecutionProfile,
) -> _PreparedInvocation:
    key = None
    empty = StreamDigest.from_bytes(b"")
    if tool.failure is not None or binary is None:
        return _PreparedInvocation(
            InvocationRecord(
                member.name,
                member.sha256,
                route,
                None,
                tool,
                _normalized_arguments(spec),
                spec.flags,
                "BLOCKED",
                None,
                empty,
                empty,
                (),
                (tool.failure or "TOOL_BINARY_INVALID",),
                (),
            ),
            None,
        )
    key = _invocation_key(
        artifact_digest=artifact_digest,
        member=member,
        route=route,
        tool=tool,
        spec=spec,
        pipeline_revision=pipeline_revision,
        tool_registry_sha256=tool_registry_sha256,
        execution_profile_sha256=execution_profile.sha256,
    )
    expected = InvocationRecord(
        member.name,
        member.sha256,
        route,
        key,
        tool,
        _normalized_arguments(spec),
        spec.flags,
        "COMPLETE",
        0,
        empty,
        empty,
        (),
        (),
        (),
    )
    cached = cache.load(key, expected, limits)
    if cached is not None:
        return cached

    workspace = Path(tempfile.mkdtemp(prefix=f"{key}.", dir=cache.work))
    try:
        for name in ("home", "tmp"):
            (workspace / name).mkdir(mode=0o700)
        input_path = workspace / "input.apk"
        _copy_input(member, input_path)
        arguments = _normalized_arguments(spec)
        quota = _create_quota_filesystem(limits)
        quota_failure: str | None = None
        try:
            run = _run_sandboxed(
                binary,
                arguments,
                workspace=workspace,
                profile=execution_profile,
                timeout=limits.tool_timeout_seconds,
                stream_limit=limits.max_tool_stream_bytes,
                workspace_identity=(workspace.stat().st_dev, workspace.stat().st_ino),
                monitor_output=True,
                quota_output_descriptor=quota.descriptor,
                quota_setup_userns_descriptor=quota.setup_userns_descriptor,
                quota_mountns_descriptor=quota.mountns_descriptor,
            )
            try:
                _materialize_quota_output(quota, workspace / "output", limits)
            except _OutputValidationError as error:
                quota_failure = error.code
            except PreparationError:
                quota_failure = "OUTPUT_INVALID"
        finally:
            quota.close()
        failures: list[str] = []
        if quota_failure is not None:
            failures.append(quota_failure)
        if run.failure is not None:
            failures.append(run.failure)
        elif run.exit_code != 0:
            failures.append("TOOL_EXIT_NONZERO")
        try:
            warnings = _warning_records(run.stdout, run.stderr, limits)
        except PreparationError:
            warnings = ()
            failures.append("TOOL_WARNING_LIMIT")
        if warnings:
            failures.append("TOOL_DIAGNOSTIC")
        outputs: tuple[OutputMember, ...] = ()
        if quota_failure is None:
            try:
                outputs = _output_members(workspace / "output", limits)
            except _OutputValidationError as err:
                failures.append(err.code)
            except PreparationError:
                failures.append("OUTPUT_INVALID")
        try:
            input_digest, input_size = _hash_file(input_path, max_bytes=member.size)
        except OSError, PreparationError:
            failures.append("INPUT_MUTATED")
        else:
            if (input_digest, input_size) != (member.sha256, member.size):
                failures.append("INPUT_MUTATED")
        record = InvocationRecord(
            member.name,
            member.sha256,
            route,
            key,
            tool,
            arguments,
            spec.flags,
            "BLOCKED" if failures else "COMPLETE",
            run.exit_code,
            StreamDigest.from_bytes(run.stdout),
            StreamDigest.from_bytes(run.stderr),
            warnings,
            tuple(dict.fromkeys(failures)),
            outputs,
        )
        if failures:
            return _PreparedInvocation(record, None)
        _publish_cache_object(cache, key, workspace, record, run.stdout, run.stderr)
        loaded = cache.load(key, record, limits)
        if loaded is None:
            raise PreparationCacheError("published cache object disappeared")
        return loaded
    finally:
        shutil.rmtree(workspace, ignore_errors=True)


def _publish_cache_object(
    cache: PreparationCache,
    key: str,
    workspace: Path,
    record: InvocationRecord,
    stdout: bytes,
    stderr: bytes,
) -> Path:
    target = cache._object(key)
    temporary = Path(tempfile.mkdtemp(prefix=f".{key}.", dir=cache.objects))
    keep = False
    try:
        os.rename(workspace / "output", temporary / "outputs")
        _sync_output_tree(temporary / "outputs", record.outputs)
        _write_new_file(temporary / "stdout.bin", stdout)
        _write_new_file(temporary / "stderr.bin", stderr)
        manifest = _canonical_json(
            {"schema": EXECUTION_CACHE_SCHEMA, "invocation": record.to_data()}
        )
        _write_new_file(temporary / "manifest.json", manifest)
        if cache.signer is not None:
            manifest_digest = hashlib.sha256(manifest).hexdigest()
            _write_new_file(
                temporary / "OBJECT.SIGNATURE",
                (
                    cache.signer.sign(b"phase4-v2:cache-object\0" + manifest_digest.encode("ascii"))
                    + "\n"
                ).encode("ascii"),
            )
        _write_new_file(
            temporary / "OBJECT.COMPLETE",
            f"{hashlib.sha256(manifest).hexdigest()} manifest.json\n".encode("ascii"),
        )
        _fsync_directory(temporary)
        try:
            _rename_noreplace(temporary, target)
            keep = True
            node = target.lstat()
            _TRUSTED_CACHE_OBJECTS[os.fspath(target)] = (
                node.st_dev,
                node.st_ino,
                hashlib.sha256(manifest).hexdigest(),
            )
            _fsync_directory(cache.objects)
            return target
        except OSError as err:
            if err.errno not in {errno.EEXIST, errno.ENOTEMPTY}:
                raise
            trusted = _TRUSTED_CACHE_OBJECTS.get(os.fspath(target))
            if trusted is not None:
                node = target.lstat()
                if (node.st_dev, node.st_ino) == trusted[:2]:
                    return target
            if cache.verification_public_key is not None:
                # A concurrently or previously published object is accepted only
                # after load() verifies its executor signature and full contents.
                return target
            raise PreparationCacheError(
                "untrusted cache object already occupies cache key"
            ) from err
    finally:
        if not keep:
            shutil.rmtree(temporary, ignore_errors=True)


def _candidate_records(
    invocations: Sequence[_PreparedInvocation], limits: ExecutionLimits
) -> tuple[CandidateRecord, ...]:
    records: list[CandidateRecord] = []
    scanned = 0
    max_signal = max(len(value) for _name, value in _CANDIDATE_SIGNALS)
    for prepared in invocations:
        record = prepared.record
        if record.status not in {"COMPLETE", "FALLBACK"} or prepared.cache_directory is None:
            continue
        assert record.cache_key is not None
        output_root = prepared.cache_directory / "outputs"
        for output in record.outputs:
            if output.bytes > limits.max_candidate_file_bytes:
                raise _CandidateIndexError("CANDIDATE_MEMBER_BYTE_LIMIT")
            scanned += output.bytes
            if scanned > limits.max_candidate_bytes:
                raise _CandidateIndexError("CANDIDATE_SCAN_BYTE_LIMIT")
            path = output_root / output.path
            tail = b""
            processed = 0
            digest = hashlib.sha256()
            descriptor = os.open(
                path,
                os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0),
            )
            before = os.fstat(descriptor)
            if not stat.S_ISREG(before.st_mode) or before.st_size != output.bytes:
                os.close(descriptor)
                raise PreparationCacheError("cached output changed before candidate indexing")
            with os.fdopen(descriptor, "rb") as stream:
                while chunk := stream.read(_CHUNK):
                    digest.update(chunk)
                    data = tail + chunk
                    data_start = processed - len(tail)
                    for signal, needle in _CANDIDATE_SIGNALS:
                        start = 0
                        while (match := data.find(needle, start)) >= 0:
                            absolute = data_start + match
                            if absolute + len(needle) > processed:
                                if len(records) >= limits.max_candidates:
                                    raise _CandidateIndexError("CANDIDATE_RECORD_LIMIT")
                                records.append(
                                    CandidateRecord(
                                        record.cache_key,
                                        record.member,
                                        record.route,
                                        output.path,
                                        output.sha256,
                                        absolute,
                                        absolute + len(needle),
                                        signal,
                                    )
                                )
                            start = match + 1
                    processed += len(chunk)
                    tail = data[-(max_signal - 1) :] if max_signal > 1 else b""
                after = os.fstat(stream.fileno())
            if (
                processed != output.bytes
                or digest.hexdigest() != output.sha256
                or (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
                != (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
            ):
                raise PreparationCacheError("cached output changed during candidate indexing")
    records.sort(
        key=lambda item: (
            item.member,
            item.route,
            item.output_path,
            item.start_byte,
            item.end_byte,
            item.signal,
        )
    )
    return tuple(records)


def _apply_jadx_fallbacks(
    invocations: Sequence[_PreparedInvocation],
) -> tuple[_PreparedInvocation, ...]:
    by_member_route = {(item.record.member, item.record.route): item for item in invocations}
    adjusted: list[_PreparedInvocation] = []
    for prepared in invocations:
        record = prepared.record
        if record.route != "jadx" or record.status != "COMPLETE":
            adjusted.append(prepared)
            continue
        if any(
            output.bytes > 0 and PurePosixPath(output.path).suffix.lower() in _SOURCE_SUFFIXES
            for output in record.outputs
        ):
            adjusted.append(prepared)
            continue
        fallback = by_member_route.get((record.member, "apktool"))
        fallback_valid = (
            fallback is not None
            and fallback.record.status == "COMPLETE"
            and any(
                output.bytes > 0 and output.path.lower().endswith(_SMALI_SUFFIX)
                for output in fallback.record.outputs
            )
        )
        if fallback_valid:
            adjusted.append(
                replace(
                    prepared,
                    record=replace(
                        record,
                        status="FALLBACK",
                        fallback_reason="JADX_OUTPUT_SUSPICIOUS",
                        fallback_route="apktool",
                    ),
                )
            )
        else:
            adjusted.append(
                replace(
                    prepared,
                    record=replace(
                        record,
                        status="BLOCKED",
                        failures=("JADX_OUTPUT_SUSPICIOUS", "AUTHORITATIVE_SMALI_FALLBACK_MISSING"),
                    ),
                )
            )
    return tuple(adjusted)


def _publish_result(
    destination: Path,
    manifest: bytes,
    candidate_index: bytes,
    status: Literal["COMPLETE", "BLOCKED"],
    execution_signature: str | None = None,
) -> None:
    parent = destination.parent
    if not parent.is_dir() or parent.is_symlink():
        raise PreparationError("preparation output parent must be an existing regular directory")
    if destination.exists() or destination.is_symlink():
        raise PreparationError("preparation output destination already exists")
    parent_descriptor = os.open(
        parent,
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_DIRECTORY", 0),
    )
    parent_identity = os.fstat(parent_descriptor)
    temporary_name = _make_private_directory_at(parent_descriptor, f".{destination.name}.")
    temporary = parent / temporary_name
    temporary_identity = temporary.lstat()
    published = False
    try:
        _write_new_file(temporary / "manifest.json", manifest)
        _write_new_file(temporary / "candidate-index.json", candidate_index)
        if execution_signature is not None:
            _write_new_file(
                temporary / "PREPARATION.SIGNATURE",
                (execution_signature + "\n").encode("ascii"),
            )
        marker = "PREPARATION.COMPLETE" if status == "COMPLETE" else "PREPARATION.BLOCKED"
        _write_new_file(
            temporary / marker,
            (
                f"{hashlib.sha256(manifest).hexdigest()} manifest.json\n"
                f"{hashlib.sha256(candidate_index).hexdigest()} candidate-index.json\n"
            ).encode("ascii"),
        )
        _fsync_directory(temporary)
        current_parent = os.fstat(parent_descriptor)
        current_temporary = temporary.lstat()
        if (current_parent.st_dev, current_parent.st_ino) != (
            parent_identity.st_dev,
            parent_identity.st_ino,
        ) or (current_temporary.st_dev, current_temporary.st_ino) != (
            temporary_identity.st_dev,
            temporary_identity.st_ino,
        ):
            raise PreparationError("preparation output ancestry changed during publication")
        _rename_noreplace_at(
            parent_descriptor,
            os.fsencode(temporary_name),
            parent_descriptor,
            os.fsencode(destination.name),
        )
        published = True
        os.fsync(parent_descriptor)
    finally:
        if not published:
            current_parent = os.fstat(parent_descriptor)
            if (current_parent.st_dev, current_parent.st_ino) == (
                parent_identity.st_dev,
                parent_identity.st_ino,
            ):
                shutil.rmtree(temporary, ignore_errors=True)
        os.close(parent_descriptor)


def execute_preparation(
    preflight: PreflightResult,
    *,
    tool_specs: Mapping[str, ToolSpec],
    cache_directory: Path | str,
    output_directory: Path | str,
    pipeline_revision: str,
    tool_registry_sha256: str | None = None,
    approved_tool_builds: Mapping[str, frozenset[tuple[str, str, str, int]]] | None = None,
    limits: ExecutionLimits | None = None,
    execution_profile: ExecutionProfile | None = None,
    execution_signer: PreparationExecutionSigner | None = None,
    authority_sha256: str | None = None,
) -> PreparationResult:
    """Execute every routed tool and publish a deterministic package-local manifest."""

    if limits is not None and execution_profile is not None:
        raise PreparationError("provide execution_profile or limits, not both")
    selected_profile = execution_profile or build_execution_profile(limits)
    if type(selected_profile) is not ExecutionProfile:
        raise PreparationError("execution profile must be an exact ExecutionProfile")
    selected_profile.__post_init__()
    selected_limits = selected_profile.limits
    _validate_token(pipeline_revision, "pipeline revision")
    if tool_registry_sha256 is not None and (
        type(tool_registry_sha256) is not str
        or len(tool_registry_sha256) != 64
        or any(character not in "0123456789abcdef" for character in tool_registry_sha256)
    ):
        raise PreparationError("tool registry digest must be a lowercase SHA-256")
    if approved_tool_builds is not None and tool_registry_sha256 is None:
        raise PreparationError("approved tool builds require a bound tool registry digest")
    if (execution_signer is None) != (authority_sha256 is None):
        raise PreparationError("executor authentication requires signer and authority together")
    if execution_signer is not None and type(execution_signer) is not PreparationExecutionSigner:
        raise PreparationError("execution signer must be an exact protected credential")
    if authority_sha256 is not None and (
        type(authority_sha256) is not str or re.fullmatch(r"[0-9a-f]{64}", authority_sha256) is None
    ):
        raise PreparationError("execution authority digest is invalid")
    if approved_tool_builds is not None:
        if len(approved_tool_builds) > 256:
            raise PreparationError("approved tool build registry exceeds the route limit")
        for route, builds in approved_tool_builds.items():
            _validate_token(route, "approved tool route")
            if type(builds) is not frozenset or not builds or len(builds) > 256:
                raise PreparationError("approved tool builds must be bounded non-empty frozensets")
            for build in builds:
                if (
                    type(build) is not tuple
                    or len(build) != 4
                    or type(build[0]) is not str
                    or re.fullmatch(r"[0-9a-f]{64}", build[0]) is None
                    or type(build[1]) is not str
                    or not build[1]
                    or len(build[1]) > 16_384
                    or any(character in build[1] for character in ("\x00", "\r", "\n"))
                    or type(build[2]) is not str
                    or re.fullmatch(r"[0-9a-f]{64}", build[2]) is None
                    or type(build[3]) is not int
                    or not 1 <= build[3] <= selected_limits.max_output_nodes
                ):
                    raise PreparationError("approved tool build identity is invalid")
    if preflight.decision.status != "READY" or preflight.package_identity is None:
        raise PreparationError("preflight result must be READY with authoritative package identity")
    artifact_member_names = [member.name for member in preflight.artifact_members]
    decision_member_names = [member.name for member in preflight.decision.members]
    if len(artifact_member_names) != len(set(artifact_member_names)) or sorted(
        artifact_member_names
    ) != sorted(decision_member_names):
        raise PreparationError("preflight artifact and classification member sets differ")
    if len(tool_specs) > 256:
        raise PreparationError("tool route configuration exceeds the route limit")
    required_routes = sorted(
        {route for member in preflight.decision.members for route in member.routes}
    )
    for route in required_routes:
        _validate_token(route, "required tool route")
    invocation_count = sum(len(member.routes) for member in preflight.decision.members)
    if invocation_count > selected_limits.max_invocations:
        raise PreparationError("preparation invocation limit exceeded")
    for route, spec in tool_specs.items():
        _validate_token(route, "tool route")
        spec.validate()

    probe_workspace = Path(tempfile.mkdtemp(prefix="phase4-probe.", dir="/var/tmp"))
    tools: dict[str, tuple[ToolRecord, _SealedExecutable | None]] = {}
    try:
        for name in ("home", "tmp"):
            (probe_workspace / name).mkdir(mode=0o700)
        for route in required_routes:
            configured_spec = tool_specs.get(route)
            if configured_spec is None:
                empty = StreamDigest.from_bytes(b"")
                tools[route] = (
                    ToolRecord(
                        executable=route,
                        binary_bytes=None,
                        binary_sha256=None,
                        runtime_files=None,
                        runtime_sha256=None,
                        version_arguments=(),
                        version=None,
                        version_stdout=empty,
                        version_stderr=empty,
                        failure="TOOL_ROUTE_UNCONFIGURED",
                    ),
                    None,
                )
            else:
                route_workspace = probe_workspace / route
                route_workspace.mkdir(mode=0o700)
                for name in ("home", "tmp"):
                    (route_workspace / name).mkdir(mode=0o700)
                tool, binary = _tool_record(
                    configured_spec, route_workspace, selected_limits, selected_profile
                )
                if (
                    approved_tool_builds is not None
                    and tool.failure is None
                    and (
                        tool.binary_sha256,
                        tool.version,
                        tool.runtime_sha256,
                        tool.runtime_files,
                    )
                    not in approved_tool_builds.get(route, frozenset())
                ):
                    tool = replace(tool, failure="TOOL_BUILD_UNAPPROVED")
                    assert binary is not None
                    binary.close()
                    binary = None
                tools[route] = (tool, binary)
    except BaseException:
        for _tool, binary in tools.values():
            if binary is not None:
                binary.close()
        raise
    finally:
        shutil.rmtree(probe_workspace, ignore_errors=True)

    cache = PreparationCache(cache_directory, signer=execution_signer)
    member_by_name = {member.name: member for member in preflight.artifact_members}
    prepared: list[_PreparedInvocation] = []
    total_output_files = 0
    try:
        for classification in preflight.decision.members:
            member = member_by_name[classification.name]
            for route in classification.routes:
                configured_spec = tool_specs.get(route)
                tool, binary = tools[route]
                if configured_spec is None:
                    configured_spec = ToolSpec(route, ("--version",), ("{input}", "{output}"))
                invocation = _execute_one(
                    cache=cache,
                    artifact_digest=preflight.artifact_digest,
                    member=member,
                    route=route,
                    spec=configured_spec,
                    tool=tool,
                    binary=binary,
                    pipeline_revision=pipeline_revision,
                    tool_registry_sha256=tool_registry_sha256,
                    limits=selected_limits,
                    execution_profile=selected_profile,
                )
                prepared.append(invocation)
                total_output_files += len(invocation.record.outputs)
                if total_output_files > selected_limits.max_total_output_files:
                    raise PreparationError("preparation total output file limit exceeded")
    finally:
        for _tool, binary in tools.values():
            if binary is not None:
                binary.close()
    adjusted = _apply_jadx_fallbacks(prepared)
    aggregate_failures: list[str] = []
    try:
        candidates = _candidate_records(adjusted, selected_limits)
    except _CandidateIndexError as err:
        candidates = ()
        aggregate_failures.append(err.code)
    records = tuple(item.record for item in adjusted)
    status: Literal["COMPLETE", "BLOCKED"] = (
        "BLOCKED"
        if aggregate_failures or any(record.status == "BLOCKED" for record in records)
        else "COMPLETE"
    )
    candidate_data = {
        "artifact_digest": preflight.artifact_digest,
        "candidate_contract_sha256": CANDIDATE_CONTRACT_SHA256,
        "candidates": [candidate.to_data() for candidate in candidates],
        "schema": CANDIDATE_INDEX_SCHEMA,
    }
    candidate_bytes = _canonical_json(candidate_data) + b"\n"
    if len(candidate_bytes) > selected_limits.max_candidate_index_bytes:
        raise PreparationError("candidate index manifest byte limit exceeded")
    candidate_sha256 = hashlib.sha256(candidate_bytes).hexdigest()
    preflight_manifest_sha256 = hashlib.sha256(_canonical_json(preflight.manifest())).hexdigest()
    manifest_data = {
        "artifact_digest": preflight.artifact_digest,
        "candidate_index": {
            "candidates": len(candidates),
            "member": "candidate-index.json",
            "sha256": candidate_sha256,
        },
        "candidate_contract": {
            "revision": CANDIDATE_CONTRACT_REVISION,
            "sha256": CANDIDATE_CONTRACT_SHA256,
        },
        "failures": aggregate_failures,
        "execution_profile": {
            "revision": selected_profile.revision,
            "sha256": selected_profile.sha256,
        },
        "invocations": [record.to_data() for record in records],
        "package_identity": preflight.package_identity.public_dict(),
        "pipeline_revision": pipeline_revision,
        "tool_registry_sha256": tool_registry_sha256,
        "preflight": {
            "manifest_sha256": preflight_manifest_sha256,
            "schema": PREFLIGHT_SCHEMA,
        },
        "schema": EXECUTION_SCHEMA,
        "status": status,
    }
    manifest_bytes = _canonical_json(manifest_data) + b"\n"
    if len(manifest_bytes) > selected_limits.max_result_manifest_bytes:
        raise PreparationError("preparation result manifest byte limit exceeded")
    manifest_sha256 = hashlib.sha256(manifest_bytes).hexdigest()
    execution_signature = None
    if execution_signer is not None:
        assert authority_sha256 is not None and tool_registry_sha256 is not None
        execution_signature = execution_signer.sign(
            _execution_attestation_bytes(
                authority_sha256=authority_sha256,
                artifact_digest=preflight.artifact_digest,
                preflight_manifest_sha256=preflight_manifest_sha256,
                registry_sha256=tool_registry_sha256,
                execution_profile_sha256=selected_profile.sha256,
                pipeline_revision=pipeline_revision,
                manifest_sha256=manifest_sha256,
                candidate_index_sha256=candidate_sha256,
            )
        )
    destination = Path(os.path.abspath(os.fspath(output_directory)))
    _publish_result(destination, manifest_bytes, candidate_bytes, status, execution_signature)
    return PreparationResult(
        destination,
        preflight.artifact_digest,
        pipeline_revision,
        selected_profile.sha256,
        status,
        records,
        candidates,
        tuple(aggregate_failures),
        manifest_sha256,
        candidate_sha256,
        authority_sha256,
        None if execution_signer is None else execution_signer.public_key,
        execution_signature,
    )
