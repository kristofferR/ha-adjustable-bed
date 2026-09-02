"""Deterministic execution and caching for routed package-local preparation tools."""

from __future__ import annotations

import builtins
import errno
import hashlib
import json
import os
import re
import selectors
import shutil
import stat
import subprocess
import tempfile
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path, PurePosixPath
from typing import Literal

from .core import PREFLIGHT_SCHEMA, ArtifactMember, PreflightResult, _rename_noreplace

EXECUTION_SCHEMA = "phase4-v2-preparation-execution-v1"
EXECUTION_CACHE_SCHEMA = "phase4-v2-preparation-cache-v1"
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

    def validate(self) -> None:
        values = (
            self.tool_timeout_seconds,
            self.version_timeout_seconds,
            self.max_tool_stream_bytes,
            self.max_version_stream_bytes,
            self.max_tool_binary_bytes,
            self.max_invocations,
            self.max_output_files,
            self.max_total_output_files,
            self.max_output_nodes,
            self.max_output_path_bytes,
            self.max_output_file_bytes,
            self.max_output_bytes,
            self.max_warning_records,
            self.max_warning_line_bytes,
            self.max_candidate_file_bytes,
            self.max_candidate_bytes,
            self.max_candidates,
            self.max_result_manifest_bytes,
            self.max_candidate_index_bytes,
        )
        if any(value <= 0 for value in values):
            raise PreparationError("execution limits must be positive")


@dataclass(frozen=True, slots=True)
class ToolSpec:
    """A route's exact executable and deterministic argument contract."""

    executable: str
    version_arguments: tuple[str, ...]
    arguments: tuple[str, ...]
    flags: tuple[str, ...] = ()

    def validate(self) -> None:
        if not self.executable or any(value in self.executable for value in ("\x00", "\r", "\n")):
            raise PreparationError("tool executable must be a non-empty path or command")
        if not self.version_arguments:
            raise PreparationError("tool version arguments must not be empty")
        if len(self.version_arguments) > 128 or len(self.arguments) > 4_096:
            raise PreparationError("tool argument count exceeds the configured contract limit")
        if any(
            not value or "\x00" in value or len(value.encode("utf-8")) > 16 * 1024
            for value in (*self.version_arguments, *self.arguments)
        ):
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
    status: Literal["COMPLETE", "BLOCKED"]
    invocations: tuple[InvocationRecord, ...]
    candidates: tuple[CandidateRecord, ...]
    failures: tuple[str, ...]
    manifest_sha256: str
    candidate_index_sha256: str


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


def _run_bounded(
    arguments: Sequence[str],
    *,
    cwd: Path,
    environment: Mapping[str, str],
    timeout: float,
    stream_limit: int,
) -> _RunResult:
    process: subprocess.Popen[bytes] | None = None
    stdout = bytearray()
    stderr = bytearray()
    streams: dict[int, tuple[Literal["stdout", "stderr"], bytearray]] = {}
    try:
        process = subprocess.Popen(  # noqa: S603 - executable was resolved and content-addressed
            list(arguments),
            cwd=cwd,
            env=dict(environment),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
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
                events = selector.select(max(0.0, remaining)) if remaining > 0 else []
                if not events:
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
    except OSError, subprocess.TimeoutExpired:
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


def _tool_record(
    spec: ToolSpec, workspace: Path, limits: ExecutionLimits
) -> tuple[ToolRecord, Path | None]:
    requested_name = Path(spec.executable).name
    empty = StreamDigest.from_bytes(b"")
    executable = shutil.which(spec.executable)
    if executable is None:
        return (
            ToolRecord(
                requested_name,
                None,
                None,
                spec.version_arguments,
                None,
                empty,
                empty,
                "TOOL_NOT_FOUND",
            ),
            None,
        )
    try:
        binary = Path(executable).resolve(strict=True)
        binary_sha256, binary_bytes = _hash_file(binary, max_bytes=limits.max_tool_binary_bytes)
    except OSError, PreparationError:
        return (
            ToolRecord(
                requested_name,
                None,
                None,
                spec.version_arguments,
                None,
                empty,
                empty,
                "TOOL_BINARY_INVALID",
            ),
            None,
        )
    run = _run_bounded(
        (str(binary), *spec.version_arguments),
        cwd=workspace,
        environment=_controlled_environment(workspace),
        timeout=limits.version_timeout_seconds,
        stream_limit=limits.max_version_stream_bytes,
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
    try:
        after_sha256, after_bytes = _hash_file(binary, max_bytes=limits.max_tool_binary_bytes)
    except OSError, PreparationError:
        failure = "TOOL_BINARY_CHANGED"
    else:
        if (after_sha256, after_bytes) != (binary_sha256, binary_bytes):
            failure = "TOOL_BINARY_CHANGED"
    return (
        ToolRecord(
            requested_name,
            binary_bytes,
            binary_sha256,
            spec.version_arguments,
            version,
            StreamDigest.from_bytes(run.stdout),
            StreamDigest.from_bytes(run.stderr),
            failure,
        ),
        binary,
    )


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

    def __init__(self, root: Path | str) -> None:
        self.root = Path(os.path.abspath(os.fspath(root)))
        self.objects = self.root / "objects" / EXECUTION_CACHE_SCHEMA
        self.work = self.root / "work"
        self.objects.mkdir(parents=True, exist_ok=True)
        self.work.mkdir(parents=True, exist_ok=True)

    def _object(self, key: str) -> Path:
        if re.fullmatch(r"[0-9a-f]{64}", key) is None:
            raise PreparationCacheError("invalid preparation cache key")
        return self.objects / key

    def load(
        self, key: str, expected: InvocationRecord, limits: ExecutionLimits
    ) -> _PreparedInvocation | None:
        target = self._object(key)
        try:
            target_stat = target.lstat()
        except FileNotFoundError:
            return None
        if not stat.S_ISDIR(target_stat.st_mode) or stat.S_ISLNK(target_stat.st_mode):
            raise PreparationCacheError("cache object is not a regular directory")
        try:
            names = {entry.name for entry in os.scandir(target)}
            if names != {"OBJECT.COMPLETE", "manifest.json", "outputs", "stderr.bin", "stdout.bin"}:
                raise PreparationCacheError("cache object contains unexpected payloads")
            manifest_payload = _read_bounded(target / "manifest.json", _MAX_CACHE_MANIFEST_BYTES)
            marker = _read_bounded(target / "OBJECT.COMPLETE", 256).decode("ascii").strip().split()
            if marker != [hashlib.sha256(manifest_payload).hexdigest(), "manifest.json"]:
                raise PreparationCacheError("cache manifest seal mismatch")
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
    binary: Path | None,
    pipeline_revision: str,
    tool_registry_sha256: str | None,
    limits: ExecutionLimits,
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
        for name in ("home", "tmp", "output"):
            (workspace / name).mkdir(mode=0o700)
        input_path = workspace / "input.apk"
        _copy_input(member, input_path)
        arguments = _normalized_arguments(spec)
        run = _run_bounded(
            (str(binary), *arguments),
            cwd=workspace,
            environment=_controlled_environment(workspace),
            timeout=limits.tool_timeout_seconds,
            stream_limit=limits.max_tool_stream_bytes,
        )
        failures: list[str] = []
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
        try:
            binary_digest, binary_size = _hash_file(binary, max_bytes=limits.max_tool_binary_bytes)
        except OSError, PreparationError:
            failures.append("TOOL_BINARY_CHANGED")
        else:
            if (binary_digest, binary_size) != (tool.binary_sha256, tool.binary_bytes):
                failures.append("TOOL_BINARY_CHANGED")
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
        _write_new_file(
            temporary / "OBJECT.COMPLETE",
            f"{hashlib.sha256(manifest).hexdigest()} manifest.json\n".encode("ascii"),
        )
        _fsync_directory(temporary)
        try:
            _rename_noreplace(temporary, target)
            keep = True
            _fsync_directory(cache.objects)
            return target
        except OSError as err:
            if err.errno not in {errno.EEXIST, errno.ENOTEMPTY}:
                raise
            return target
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
) -> None:
    parent = destination.parent
    if not parent.is_dir() or parent.is_symlink():
        raise PreparationError("preparation output parent must be an existing regular directory")
    if destination.exists() or destination.is_symlink():
        raise PreparationError("preparation output destination already exists")
    temporary = Path(tempfile.mkdtemp(prefix=f".{destination.name}.", dir=parent))
    published = False
    try:
        _write_new_file(temporary / "manifest.json", manifest)
        _write_new_file(temporary / "candidate-index.json", candidate_index)
        marker = "PREPARATION.COMPLETE" if status == "COMPLETE" else "PREPARATION.BLOCKED"
        _write_new_file(
            temporary / marker,
            (
                f"{hashlib.sha256(manifest).hexdigest()} manifest.json\n"
                f"{hashlib.sha256(candidate_index).hexdigest()} candidate-index.json\n"
            ).encode("ascii"),
        )
        _fsync_directory(temporary)
        _rename_noreplace(temporary, destination)
        published = True
        _fsync_directory(parent)
    finally:
        if not published:
            shutil.rmtree(temporary, ignore_errors=True)


def execute_preparation(
    preflight: PreflightResult,
    *,
    tool_specs: Mapping[str, ToolSpec],
    cache_directory: Path | str,
    output_directory: Path | str,
    pipeline_revision: str,
    tool_registry_sha256: str | None = None,
    approved_tool_builds: Mapping[str, frozenset[tuple[str, str]]] | None = None,
    limits: ExecutionLimits | None = None,
) -> PreparationResult:
    """Execute every routed tool and publish a deterministic package-local manifest."""

    selected_limits = limits or ExecutionLimits()
    selected_limits.validate()
    _validate_token(pipeline_revision, "pipeline revision")
    if tool_registry_sha256 is not None and (
        type(tool_registry_sha256) is not str
        or len(tool_registry_sha256) != 64
        or any(character not in "0123456789abcdef" for character in tool_registry_sha256)
    ):
        raise PreparationError("tool registry digest must be a lowercase SHA-256")
    if approved_tool_builds is not None and tool_registry_sha256 is None:
        raise PreparationError("approved tool builds require a bound tool registry digest")
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
                    or len(build) != 2
                    or type(build[0]) is not str
                    or re.fullmatch(r"[0-9a-f]{64}", build[0]) is None
                    or type(build[1]) is not str
                    or not build[1]
                    or len(build[1]) > 16_384
                    or any(character in build[1] for character in ("\x00", "\r", "\n"))
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
    cache = PreparationCache(cache_directory)
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

    probe_workspace = Path(tempfile.mkdtemp(prefix="probe.", dir=cache.work))
    tools: dict[str, tuple[ToolRecord, Path | None]] = {}
    try:
        for name in ("home", "tmp"):
            (probe_workspace / name).mkdir(mode=0o700)
        for route in required_routes:
            configured_spec = tool_specs.get(route)
            if configured_spec is None:
                empty = StreamDigest.from_bytes(b"")
                tools[route] = (
                    ToolRecord(
                        route, None, None, (), None, empty, empty, "TOOL_ROUTE_UNCONFIGURED"
                    ),
                    None,
                )
            else:
                route_workspace = probe_workspace / route
                route_workspace.mkdir(mode=0o700)
                for name in ("home", "tmp"):
                    (route_workspace / name).mkdir(mode=0o700)
                tool, binary = _tool_record(configured_spec, route_workspace, selected_limits)
                if (
                    approved_tool_builds is not None
                    and tool.failure is None
                    and (tool.binary_sha256, tool.version)
                    not in approved_tool_builds.get(route, frozenset())
                ):
                    tool = replace(tool, failure="TOOL_BUILD_UNAPPROVED")
                    binary = None
                tools[route] = (tool, binary)
    finally:
        shutil.rmtree(probe_workspace, ignore_errors=True)

    member_by_name = {member.name: member for member in preflight.artifact_members}
    prepared: list[_PreparedInvocation] = []
    total_output_files = 0
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
            )
            prepared.append(invocation)
            total_output_files += len(invocation.record.outputs)
            if total_output_files > selected_limits.max_total_output_files:
                raise PreparationError("preparation total output file limit exceeded")
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
    destination = Path(os.path.abspath(os.fspath(output_directory)))
    _publish_result(destination, manifest_bytes, candidate_bytes, status)
    return PreparationResult(
        destination,
        preflight.artifact_digest,
        pipeline_revision,
        status,
        records,
        candidates,
        tuple(aggregate_failures),
        manifest_sha256,
        candidate_sha256,
    )
