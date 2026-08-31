"""Fail-closed, protocol-neutral preflight for Android application deliveries."""

from __future__ import annotations

import ctypes
import errno
import fcntl
import hashlib
import json
import os
import re
import selectors
import shutil
import stat
import struct
import subprocess
import tempfile
import time
import zipfile
from collections.abc import Iterable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import IO, Literal, TypedDict, cast

PREFLIGHT_SCHEMA = "phase4-v2-preflight-v3"
CACHE_SCHEMA = "phase4-v2-artifact-cache-v1"
_DELIVERY_ARCHIVES = frozenset({".apks", ".xapk", ".zip"})
_APK_SUFFIX = ".apk"
_COPY_CHUNK = 1024 * 1024
_MAX_CACHE_MANIFEST_BYTES = 16 * 1024**2
_MAX_ZIP_COMMENT_BYTES = 65_535
_ZIP_EOCD_BYTES = 22
_ZIP_EOCD_SIGNATURE = b"PK\x05\x06"
_STATUS_REVISION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,199}$")
_BADGING_PACKAGE = re.compile(r"^package:(?: [A-Za-z][A-Za-z0-9]*='[^']*')+$")
_BADGING_ATTRIBUTE = re.compile(r" ([A-Za-z][A-Za-z0-9]*)='([^']*)'")
_BADGING_SPLIT = re.compile(r"^split='([^']+)'$")
_BADGING_USES_SPLIT = re.compile(r"^uses-split(?:-not-required)?:'([^']+)'$")
_SIGNER_DIGEST = re.compile(r"^Signer #\d+ certificate SHA-256 digest: ([0-9a-fA-F]{64})$")
_PACKAGE_NAME = re.compile(r"^[A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)+$")
_DEX_MEMBER = re.compile(r"^classes(?:[1-9][0-9]*)?\.dex$")
_SHIPPED_CODE_SUFFIXES = (
    ".bc",
    ".cjs",
    ".dex",
    ".dll",
    ".js",
    ".jsc",
    ".lua",
    ".luac",
    ".mjs",
    ".pck",
    ".py",
    ".pyc",
    ".wasm",
)
_EMBEDDED_ARCHIVE_SUFFIXES = (".aar", ".apk", ".apks", ".jar", ".xapk", ".zip")
_STACK_ROUTES: Mapping[str, tuple[str, ...]] = MappingProxyType({
    "air": ("ffdec",),
    "android": ("apktool",),
    "android_dex": ("jadx",),
    "embedded_archive": ("embedded-archive-inventory",),
    "flutter": ("blutter",),
    "hermes": ("hermes-bundle",),
    "native": ("native-library-inventory",),
    "react_native": ("react-native-bundle",),
    "shipped_bundle": ("shipped-bundle",),
})
_AT_FDCWD = -100
_RENAME_NOREPLACE = 1
_O_NOATIME = getattr(os, "O_NOATIME", 0)
_READ_FLAGS = (
    os.O_RDONLY
    | getattr(os, "O_CLOEXEC", 0)
    | getattr(os, "O_NOFOLLOW", 0)
    | getattr(os, "O_NONBLOCK", 0)
    | _O_NOATIME
)
_DIRECTORY_FLAGS = (
    os.O_RDONLY
    | getattr(os, "O_CLOEXEC", 0)
    | getattr(os, "O_NOFOLLOW", 0)
    | getattr(os, "O_DIRECTORY", 0)
)


class PreflightError(RuntimeError):
    """Base error for deterministic preflight failures."""


class SafetyError(PreflightError):
    """Raised when an input cannot be inventoried safely."""


class CacheIntegrityError(PreflightError):
    """Raised when a content-addressed cache object fails verification."""


class CachedMember(TypedDict):
    name: str
    stored_name: str
    size: int
    sha256: str


class CacheManifest(TypedDict):
    schema: str
    artifact_digest: str
    members: list[CachedMember]


@dataclass(frozen=True, slots=True)
class PreflightLimits:
    """Limits enforced before archive content is expanded."""

    max_delivery_file_bytes: int = 4 * 1024**3
    max_archive_members: int = 100_000
    max_member_bytes: int = 2 * 1024**3
    max_archive_bytes: int = 8 * 1024**3
    max_archive_compressed_bytes: int = 4 * 1024**3
    max_central_directory_bytes: int = 256 * 1024**2
    max_compression_ratio: int = 2_000


@dataclass(frozen=True, slots=True)
class DeliveryFile:
    name: str
    size: int
    sha256: str


class _SealedOwner:
    def __init__(self, directory: Path | str | None = None) -> None:
        parent: str | None = None
        if directory is not None:
            try:
                resolved = Path(directory).resolve(strict=True)
            except OSError as err:
                raise PreflightError(f"sealing directory is inaccessible: {directory}") from err
            if not resolved.is_dir():
                raise PreflightError(f"sealing directory is not a directory: {resolved}")
            parent = os.fspath(resolved)
        self._temporary = tempfile.TemporaryDirectory(prefix="phase4-v2-preflight-", dir=parent)
        self.path = Path(self._temporary.name)

    def close(self) -> None:
        self._temporary.cleanup()


@dataclass(frozen=True, slots=True)
class ArtifactMember:
    """One logical APK backed by a private sealed copy."""

    name: str
    size: int
    sha256: str
    _sealed_path: Path = field(repr=False, compare=False)

    def public_dict(self) -> dict[str, object]:
        return {"name": self.name, "size": self.size, "sha256": self.sha256}


@dataclass(frozen=True, slots=True)
class PackageIdentity:
    """Identity shared by one cryptographically coherent install set."""

    package_name: str
    version_code: str
    version_name: str
    signer_sha256: tuple[str, ...]
    base_member: str
    split_members: tuple[tuple[str, str], ...]

    def public_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class MemberClassification:
    """Canonical application-stack routing for one logical APK member."""

    name: str
    stacks: tuple[str, ...]
    routes: tuple[str, ...]
    status: Literal["READY", "BLOCKED"]
    blockers: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class StackDecision:
    stacks: tuple[str, ...]
    routes: tuple[str, ...]
    status: Literal["READY", "BLOCKED"]
    blockers: tuple[str, ...]
    members: tuple[MemberClassification, ...]


@dataclass(frozen=True, slots=True)
class PreflightResult:
    delivery_digest: str
    artifact_digest: str
    delivery_files: tuple[DeliveryFile, ...]
    artifact_members: tuple[ArtifactMember, ...]
    package_identity: PackageIdentity | None
    decision: StackDecision
    _owner: _SealedOwner = field(repr=False, compare=False)

    def manifest(self) -> dict[str, object]:
        return {
            "schema": PREFLIGHT_SCHEMA,
            "delivery_digest": self.delivery_digest,
            "artifact_digest": self.artifact_digest,
            "delivery_files": [asdict(item) for item in self.delivery_files],
            "artifact_members": [item.public_dict() for item in self.artifact_members],
            "package_identity": (
                self.package_identity.public_dict() if self.package_identity is not None else None
            ),
            "classification": asdict(self.decision),
        }

    def close(self) -> None:
        self._owner.close()

    def __enter__(self) -> PreflightResult:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


@dataclass(frozen=True, slots=True)
class _ArchiveEntry:
    name: str
    info: zipfile.ZipInfo


@dataclass(frozen=True, slots=True)
class _ApkIdentity:
    member: str
    package_name: str
    version_code: str
    version_name: str
    split_name: str | None
    required_splits: tuple[str, ...]
    signer_sha256: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _ApkObservation:
    member: str
    stacks: tuple[str, ...]
    blockers: tuple[str, ...]


def _canonical_json(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _cache_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate cache manifest key: {key}")
        result[key] = value
    return result


def _reject_cache_constant(value: str) -> object:
    raise ValueError(f"non-finite cache manifest number: {value}")


def _is_sha256(value: str) -> bool:
    return len(value) == 64 and all(character in "0123456789abcdef" for character in value)


def _digest_manifest(domain: str, items: Sequence[Mapping[str, object]]) -> str:
    digest = hashlib.sha256()
    digest.update(domain.encode())
    digest.update(b"\0")
    digest.update(_canonical_json(items))
    return digest.hexdigest()


def _identity(node: os.stat_result) -> tuple[int, int, int, int, int]:
    return (node.st_dev, node.st_ino, node.st_size, node.st_mtime_ns, node.st_ctime_ns)


def _open_readonly(path: os.PathLike[str] | str, *, dir_fd: int | None = None) -> int:
    """Open safely, falling back when Linux denies the optional no-atime hint."""
    try:
        return os.open(path, _READ_FLAGS, dir_fd=dir_fd)
    except OSError as error:
        if not _O_NOATIME or error.errno != errno.EPERM:
            raise
        return os.open(path, _READ_FLAGS & ~_O_NOATIME, dir_fd=dir_fd)


def _hash_stream(stream: IO[bytes], *, expected_size: int) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    while size < expected_size:
        chunk = stream.read(min(_COPY_CHUNK, expected_size - size))
        if not chunk:
            break
        digest.update(chunk)
        size += len(chunk)
    if size != expected_size or stream.read(1):
        raise SafetyError("stream length differs from its sealed size")
    return digest.hexdigest(), size


def _regular_file(path: Path, *, max_bytes: int | None = None) -> os.stat_result:
    try:
        node = path.lstat()
    except OSError as err:
        raise PreflightError(f"delivery file is inaccessible: {path}") from err
    if not stat.S_ISREG(node.st_mode):
        raise SafetyError(f"delivery input must be a regular file: {path}")
    if max_bytes is not None and node.st_size > max_bytes:
        raise SafetyError(f"compressed delivery size limit exceeded: {path.name}")
    return node


def _copy_fd_exact(source_fd: int, destination_fd: int, *, expected_size: int) -> tuple[str, int]:
    digest = hashlib.sha256()
    copied = 0
    while copied < expected_size:
        chunk = os.read(source_fd, min(_COPY_CHUNK, expected_size - copied))
        if not chunk:
            break
        view = memoryview(chunk)
        while view:
            written = os.write(destination_fd, view)
            if written <= 0:
                raise SafetyError("short write while copying sealed bytes")
            view = view[written:]
        digest.update(chunk)
        copied += len(chunk)
    if copied != expected_size or os.read(source_fd, 1):
        raise SafetyError("source length differs from its sealed size")
    return digest.hexdigest(), copied


def _seal_delivery_file(source: Path, destination: Path, limits: PreflightLimits) -> DeliveryFile:
    before = _regular_file(source, max_bytes=limits.max_delivery_file_bytes)
    source_fd = _open_readonly(source)
    destination_fd = -1
    try:
        opened = os.fstat(source_fd)
        if not stat.S_ISREG(opened.st_mode) or _identity(opened) != _identity(before):
            raise SafetyError(f"delivery file changed before sealing: {source}")
        destination_fd = os.open(
            destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0), 0o600
        )
        digest, size = _copy_fd_exact(source_fd, destination_fd, expected_size=before.st_size)
        os.fsync(destination_fd)
        opened_after = os.fstat(source_fd)
    finally:
        if destination_fd >= 0:
            os.close(destination_fd)
        os.close(source_fd)
    try:
        path_after = source.lstat()
    except OSError as err:
        raise SafetyError(f"delivery file disappeared after sealing: {source}") from err
    if _identity(opened_after) != _identity(before) or _identity(path_after) != _identity(before):
        raise SafetyError(f"delivery file changed during sealing: {source}")
    return DeliveryFile(source.name, size, digest)


def _safe_member_name(name: str) -> str:
    if not name or "\x00" in name or "\r" in name or "\n" in name or "\\" in name:
        raise SafetyError(f"unsafe archive member name: {name!r}")
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or any(part in {"", "."} for part in path.parts):
        raise SafetyError(f"unsafe archive member name: {name!r}")
    return path.as_posix()


def _archive_entries(
    archive: zipfile.ZipFile, limits: PreflightLimits
) -> tuple[_ArchiveEntry, ...]:
    infos = archive.infolist()
    if len(infos) > limits.max_archive_members:
        raise SafetyError("archive member-count limit exceeded")
    entries: list[_ArchiveEntry] = []
    seen: set[str] = set()
    seen_casefold: set[str] = set()
    expanded_total = 0
    compressed_total = 0
    for info in infos:
        name = _safe_member_name(info.filename.rstrip("/"))
        if name in seen:
            raise SafetyError(f"duplicate archive member: {name}")
        folded_name = name.casefold()
        if folded_name in seen_casefold:
            raise SafetyError(f"case-ambiguous archive member: {name}")
        seen.add(name)
        seen_casefold.add(folded_name)
        if info.flag_bits & 0x1:
            raise SafetyError(f"encrypted archive member is unsupported: {name}")
        unix_mode = info.external_attr >> 16
        if unix_mode and stat.S_IFMT(unix_mode) not in {0, stat.S_IFREG, stat.S_IFDIR}:
            raise SafetyError(f"non-regular archive member is unsupported: {name}")
        if info.is_dir():
            continue
        if info.file_size > limits.max_member_bytes:
            raise SafetyError(f"archive member size limit exceeded: {name}")
        expanded_total += info.file_size
        compressed_total += info.compress_size
        if expanded_total > limits.max_archive_bytes:
            raise SafetyError("archive expanded-size limit exceeded")
        if compressed_total > limits.max_archive_compressed_bytes:
            raise SafetyError("archive compressed-size limit exceeded")
        if info.file_size and info.compress_size == 0:
            raise SafetyError(f"invalid compressed size for archive member: {name}")
        if (
            info.compress_size
            and info.file_size / info.compress_size > limits.max_compression_ratio
        ):
            raise SafetyError(f"archive compression-ratio limit exceeded: {name}")
        entries.append(_ArchiveEntry(name, info))
    return tuple(entries)


def _preflight_zip_directory(stream: IO[bytes], limits: PreflightLimits) -> None:
    try:
        stream.seek(0, os.SEEK_END)
        file_size = stream.tell()
        tail_size = min(file_size, _ZIP_EOCD_BYTES + _MAX_ZIP_COMMENT_BYTES)
        stream.seek(file_size - tail_size)
        tail = stream.read(tail_size)
        search_end = len(tail)
        while True:
            marker = tail.rfind(_ZIP_EOCD_SIGNATURE, 0, search_end)
            if marker < 0:
                raise SafetyError("ZIP end-of-central-directory record is missing")
            search_end = marker
            if len(tail) - marker < _ZIP_EOCD_BYTES:
                continue
            fields = struct.unpack_from("<4s4H2LH", tail, marker)
            comment_size = fields[-1]
            if marker + _ZIP_EOCD_BYTES + comment_size == len(tail):
                break
        (
            _signature,
            disk_number,
            central_disk,
            entries_on_disk,
            entry_count,
            central_size,
            central_offset,
            _comment_size,
        ) = fields
        if disk_number or central_disk or entries_on_disk != entry_count:
            raise SafetyError("multi-disk ZIP deliveries are unsupported")
        if entry_count == 0xFFFF or central_size == 0xFFFFFFFF or central_offset == 0xFFFFFFFF:
            raise SafetyError("ZIP64 deliveries require a dedicated bounded parser")
        if entry_count > limits.max_archive_members:
            raise SafetyError("archive member-count limit exceeded before ZIP parsing")
        if central_size > limits.max_central_directory_bytes:
            raise SafetyError("archive central-directory size limit exceeded")
        eocd_offset = file_size - tail_size + marker
        if central_offset + central_size > eocd_offset:
            raise SafetyError("archive central-directory bounds are invalid")
    except OSError as error:
        raise SafetyError("ZIP directory preflight failed") from error
    finally:
        stream.seek(0)


@contextmanager
def _open_zip_path(path: Path, limits: PreflightLimits | None = None) -> Iterator[zipfile.ZipFile]:
    expected = _regular_file(path)
    descriptor = _open_readonly(path)
    stream: IO[bytes] | None = None
    try:
        if _identity(os.fstat(descriptor)) != _identity(expected):
            raise SafetyError(f"sealed ZIP identity changed: {path.name}")
        stream = os.fdopen(descriptor, "rb")
        descriptor = -1
        try:
            _preflight_zip_directory(stream, limits or PreflightLimits())
            archive = zipfile.ZipFile(stream, "r")
        except (OSError, zipfile.BadZipFile) as err:
            raise SafetyError(f"invalid ZIP delivery or APK: {path.name}") from err
        try:
            yield archive
        finally:
            archive.close()
    finally:
        if stream is not None:
            stream.close()
        if descriptor >= 0:
            os.close(descriptor)


def _logical_apk_name(name: str) -> str:
    logical = PurePosixPath(_safe_member_name(name)).name
    if not logical.lower().endswith(_APK_SUFFIX):
        raise SafetyError(f"artifact member is not an APK: {name}")
    return logical


def _classify_apk(path: Path, label: str, limits: PreflightLimits) -> _ApkObservation:
    try:
        with _open_zip_path(path, limits) as apk:
            entries = _archive_entries(apk, limits)
    except SafetyError as err:
        raise SafetyError(f"invalid APK member {label}: {err}") from err
    names = {entry.name.casefold() for entry in entries}
    stacks: set[str] = set()
    blockers: set[str] = set()
    if "androidmanifest.xml" in names:
        stacks.add("android")
    else:
        blockers.add(f"android_manifest_missing:{label}")
    if any(_DEX_MEMBER.fullmatch(name) for name in names):
        stacks.add("android_dex")
    if "assets/flutter_assets/kernel_blob.bin" in names or any(
        name.startswith("lib/") and name.endswith("/libapp.so") for name in names
    ):
        stacks.add("flutter")
    if "assets/index.android.bundle" in names or "assets/index.android.bundle.hbc" in names:
        stacks.add("react_native")
    if any(name.endswith(".hermes") or name.endswith(".hbc") for name in names):
        stacks.add("hermes")
    if "assets/meta-inf/air/application.xml" in names or any(
        name.endswith(".swf") for name in names
    ):
        stacks.add("air")
    if any(name.endswith(".so") for name in names):
        stacks.add("native")
    if any(name.endswith(_EMBEDDED_ARCHIVE_SUFFIXES) for name in names):
        stacks.add("embedded_archive")
    known_react_native_bundles = {
        "assets/index.android.bundle",
        "assets/index.android.bundle.hbc",
    }
    if any(
        name not in known_react_native_bundles
        and (name.endswith(_SHIPPED_CODE_SUFFIXES) or name.endswith(".bundle"))
        and _DEX_MEMBER.fullmatch(name) is None
        for name in names
    ):
        stacks.add("shipped_bundle")
    if not stacks:
        blockers.add(f"unknown_application_stack:{label}")
    return _ApkObservation(label, tuple(sorted(stacks)), tuple(sorted(blockers)))


def _run_identity_tool(arguments: Sequence[str], *, label: str) -> tuple[str | None, str | None]:
    executable = shutil.which(arguments[0])
    if executable is None:
        return None, f"identity_tool_unavailable:{arguments[0]}"
    process: subprocess.Popen[bytes] | None = None
    output = bytearray()
    output_limit = 4 * 1024**2
    try:
        process = subprocess.Popen(  # noqa: S603 - fixed executable and sealed private path
            [executable, *arguments[1:]],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        assert process.stdout is not None
        deadline = time.monotonic() + 60
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ)
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise subprocess.TimeoutExpired(arguments, 60)
                if not selector.select(remaining):
                    raise subprocess.TimeoutExpired(arguments, 60)
                chunk = os.read(
                    process.stdout.fileno(),
                    min(64 * 1024, output_limit + 1 - len(output)),
                )
                if not chunk:
                    process.wait(timeout=max(0.0, deadline - time.monotonic()))
                    break
                output.extend(chunk)
                if len(output) > output_limit:
                    _terminate_identity_tool(process)
                    return None, f"identity_tool_output_limit:{arguments[0]}:{label}"
    except (OSError, subprocess.TimeoutExpired):
        if process is not None:
            _terminate_identity_tool(process)
        return None, f"identity_tool_failed:{arguments[0]}:{label}"
    finally:
        if process is not None and process.stdout is not None:
            process.stdout.close()
    if process.returncode != 0:
        return None, f"identity_verification_failed:{arguments[0]}:{label}"
    try:
        return output.decode("utf-8", errors="strict"), None
    except UnicodeDecodeError:
        return None, f"identity_tool_non_utf8:{arguments[0]}:{label}"


def _terminate_identity_tool(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=1)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


def _inspect_apk_identity(member: ArtifactMember) -> tuple[_ApkIdentity | None, tuple[str, ...]]:
    badging, badging_error = _run_identity_tool(
        ("aapt2", "dump", "badging", os.fspath(member._sealed_path)), label=member.name
    )
    signer, signer_error = _run_identity_tool(
        ("apksigner", "verify", "--print-certs", os.fspath(member._sealed_path)),
        label=member.name,
    )
    blockers = tuple(error for error in (badging_error, signer_error) if error is not None)
    if badging is None or signer is None:
        return None, blockers
    package_lines = [line for line in badging.splitlines() if _BADGING_PACKAGE.fullmatch(line)]
    package_attribute_pairs = [_BADGING_ATTRIBUTE.findall(line) for line in package_lines]
    package_attributes = [dict(pairs) for pairs in package_attribute_pairs]
    split_matches = [
        match.group(1) for line in badging.splitlines() if (match := _BADGING_SPLIT.fullmatch(line))
    ]
    split_matches.extend(
        attributes["split"] for attributes in package_attributes if "split" in attributes
    )
    signer_digests = tuple(
        sorted(
            {
                match.group(1).lower()
                for line in signer.splitlines()
                if (match := _SIGNER_DIGEST.fullmatch(line))
            }
        )
    )
    parse_blockers: list[str] = []
    if any(len(pairs) != len({key for key, _value in pairs}) for pairs in package_attribute_pairs):
        parse_blockers.append(f"package_identity_ambiguous:{member.name}")
    if len(package_attributes) != 1 or not {
        "name",
        "versionCode",
        "versionName",
    }.issubset(package_attributes[0]):
        parse_blockers.append(f"package_identity_ambiguous:{member.name}")
    if len(split_matches) > 1:
        parse_blockers.append(f"split_identity_ambiguous:{member.name}")
    if not signer_digests:
        parse_blockers.append(f"signer_identity_missing:{member.name}")
    if package_attributes:
        package = package_attributes[0]
        if (
            _PACKAGE_NAME.fullmatch(package.get("name", "")) is None
            or not package.get("versionCode")
            or len(package.get("versionCode", "")) > 256
            or not package.get("versionName")
            or len(package.get("versionName", "")) > 256
        ):
            parse_blockers.append(f"package_identity_invalid:{member.name}")
    if parse_blockers:
        return None, tuple(parse_blockers)
    package = package_attributes[0]
    required_splits = tuple(
        sorted(
            {
                match.group(1)
                for line in badging.splitlines()
                if (match := _BADGING_USES_SPLIT.fullmatch(line))
                and not line.startswith("uses-split-not-required")
            }
        )
    )
    return (
        _ApkIdentity(
            member.name,
            package["name"],
            package["versionCode"],
            package["versionName"],
            split_matches[0] if split_matches else None,
            required_splits,
            signer_digests,
        ),
        (),
    )


def _derive_package_identity(
    members: Sequence[ArtifactMember],
) -> tuple[PackageIdentity | None, tuple[str, ...]]:
    inspected: list[_ApkIdentity] = []
    blockers: list[str] = []
    for member in members:
        identity, member_blockers = _inspect_apk_identity(member)
        blockers.extend(member_blockers)
        if identity is not None:
            inspected.append(identity)
    if blockers or len(inspected) != len(members):
        return None, tuple(sorted(set(blockers)))
    packages = {item.package_name for item in inspected}
    versions = {(item.version_code, item.version_name) for item in inspected}
    signers = {item.signer_sha256 for item in inspected}
    bases = [item for item in inspected if item.split_name is None]
    split_names = [item.split_name for item in inspected if item.split_name is not None]
    if len(packages) != 1:
        blockers.append("package_identity_mismatch")
    if len(versions) != 1:
        blockers.append("version_identity_mismatch")
    if len(signers) != 1:
        blockers.append("signer_identity_mismatch")
    if len(bases) != 1:
        blockers.append("split_base_ambiguous")
    if len(split_names) != len(set(split_names)):
        blockers.append("split_identity_duplicate")
    present_splits = {name for name in split_names if name is not None}
    required_splits = {name for item in inspected for name in item.required_splits}
    missing = sorted(required_splits - present_splits)
    blockers.extend(f"required_split_missing:{name}" for name in missing)
    if blockers:
        return None, tuple(sorted(set(blockers)))
    package_name = next(iter(packages))
    version_code, version_name = next(iter(versions))
    signer_sha256 = next(iter(signers))
    return (
        PackageIdentity(
            package_name,
            version_code,
            version_name,
            signer_sha256,
            bases[0].member,
            tuple(
                sorted(
                    (item.split_name or "", item.member) for item in inspected if item.split_name
                )
            ),
        ),
        (),
    )


def _suggested_routes(stacks: Iterable[str]) -> tuple[str, ...]:
    observed = set(stacks)
    unknown = observed - _STACK_ROUTES.keys()
    if unknown:
        raise PreflightError(f"stack route mapping is incomplete: {sorted(unknown)}")
    return tuple(sorted({route for stack in observed for route in _STACK_ROUTES[stack]}))


def _decision(
    observations: Iterable[_ApkObservation],
    *,
    identity_verified: bool = False,
    extra_blockers: Iterable[str] = (),
) -> StackDecision:
    ordered_observations = tuple(sorted(observations, key=lambda item: item.member.casefold()))
    members = tuple(
        MemberClassification(
            observation.member,
            observation.stacks,
            _suggested_routes(observation.stacks),
            "READY" if not observation.blockers else "BLOCKED",
            observation.blockers,
        )
        for observation in ordered_observations
    )
    observed = tuple(sorted({stack for member in members for stack in member.stacks}))
    blockers = {blocker for member in members for blocker in member.blockers}
    if not identity_verified:
        blockers.update(
            {
                "package_identity_not_verified",
                "version_identity_not_verified",
                "signer_coherence_not_verified",
                "split_coherence_not_verified",
            }
        )
    blockers.update(extra_blockers)
    ordered_blockers = tuple(sorted(blockers))
    status: Literal["READY", "BLOCKED"] = "READY" if not ordered_blockers else "BLOCKED"
    return StackDecision(
        observed,
        _suggested_routes(observed),
        status,
        ordered_blockers,
        members,
    )


def _seal_archive_member(
    archive: zipfile.ZipFile, entry: _ArchiveEntry, destination: Path
) -> tuple[str, int]:
    destination_fd = os.open(
        destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0), 0o600
    )
    try:
        digest = hashlib.sha256()
        copied = 0
        with archive.open(entry.info, "r") as source:
            while copied < entry.info.file_size:
                chunk = source.read(min(_COPY_CHUNK, entry.info.file_size - copied))
                if not chunk:
                    break
                view = memoryview(chunk)
                while view:
                    written = os.write(destination_fd, view)
                    if written <= 0:
                        raise SafetyError("short write while sealing archive member")
                    view = view[written:]
                digest.update(chunk)
                copied += len(chunk)
            if copied != entry.info.file_size or source.read(1):
                raise SafetyError(f"archive member size changed while reading: {entry.name}")
        os.fsync(destination_fd)
    finally:
        os.close(destination_fd)
    return digest.hexdigest(), copied


def preflight_delivery(
    paths: Sequence[Path | str],
    *,
    limits: PreflightLimits | None = None,
    sealing_directory: Path | str | None = None,
) -> PreflightResult:
    """Seal each delivery once, then derive all results from sealed bytes."""
    if not paths:
        raise PreflightError("delivery must contain at least one file")
    active_limits = limits or PreflightLimits()
    supplied = [Path(os.path.abspath(os.fspath(path))) for path in paths]
    if len({path.name.casefold() for path in supplied}) != len(supplied):
        raise SafetyError("delivery contains duplicate file names")
    owner = _SealedOwner(sealing_directory)
    deliveries: list[DeliveryFile] = []
    artifacts: list[ArtifactMember] = []
    observations: list[_ApkObservation] = []
    try:
        for delivery_index, source in enumerate(
            sorted(supplied, key=lambda item: item.name.casefold())
        ):
            sealed_delivery = owner.path / f"delivery-{delivery_index:04d}"
            delivery = _seal_delivery_file(source, sealed_delivery, active_limits)
            deliveries.append(delivery)
            if source.suffix.lower() == _APK_SUFFIX:
                if delivery.size > active_limits.max_member_bytes:
                    raise SafetyError(f"artifact member size limit exceeded: {source.name}")
                logical = _logical_apk_name(source.name)
                observations.append(_classify_apk(sealed_delivery, logical, active_limits))
                artifacts.append(
                    ArtifactMember(logical, delivery.size, delivery.sha256, sealed_delivery)
                )
            elif source.suffix.lower() in _DELIVERY_ARCHIVES:
                with _open_zip_path(sealed_delivery, active_limits) as archive:
                    entries = _archive_entries(archive, active_limits)
                    apk_entries = [
                        entry for entry in entries if entry.name.lower().endswith(_APK_SUFFIX)
                    ]
                    for member_index, entry in enumerate(apk_entries):
                        logical = _logical_apk_name(entry.name)
                        sealed_member = (
                            owner.path / f"artifact-{delivery_index:04d}-{member_index:04d}"
                        )
                        digest, size = _seal_archive_member(archive, entry, sealed_member)
                        observations.append(
                            _classify_apk(sealed_member, logical, active_limits)
                        )
                        artifacts.append(ArtifactMember(logical, size, digest, sealed_member))
            else:
                raise SafetyError(f"unsupported delivery file type: {source.name}")
        extra_blockers = () if artifacts else ("delivery_contains_no_apk_members",)
        if len({member.name.casefold() for member in artifacts}) != len(artifacts):
            raise SafetyError("artifact set contains duplicate logical APK names")
        artifacts.sort(key=lambda item: item.name.casefold())
        deliveries.sort(key=lambda item: item.name.casefold())
        package_identity, identity_blockers = _derive_package_identity(artifacts)
        delivery_public = [asdict(item) for item in deliveries]
        artifact_public = [item.public_dict() for item in artifacts]
        return PreflightResult(
            _digest_manifest("delivery", delivery_public),
            _digest_manifest("artifact", artifact_public),
            tuple(deliveries),
            tuple(artifacts),
            package_identity,
            _decision(
                observations,
                identity_verified=package_identity is not None,
                extra_blockers=(*extra_blockers, *identity_blockers),
            ),
            owner,
        )
    except BaseException:
        owner.close()
        raise


def _rename_noreplace(source: Path, destination: Path) -> None:
    libc = ctypes.CDLL(None, use_errno=True)
    operation = getattr(libc, "renameat2", None)
    if operation is None:
        raise PreflightError("atomic no-replace directory publication is unavailable")
    operation.argtypes = [
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_uint,
    ]
    operation.restype = ctypes.c_int
    if (
        operation(
            _AT_FDCWD, os.fsencode(source), _AT_FDCWD, os.fsencode(destination), _RENAME_NOREPLACE
        )
        == 0
    ):
        return
    error = ctypes.get_errno()
    if error == errno.EEXIST:
        raise FileExistsError(error, os.strerror(error), destination)
    raise OSError(error, os.strerror(error), destination)


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, _DIRECTORY_FLAGS)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _write_file_at(directory_fd: int, name: str, payload: bytes) -> None:
    descriptor = os.open(
        name,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0),
        0o600,
        dir_fd=directory_fd,
    )
    try:
        view = memoryview(payload)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise SafetyError("short write while publishing metadata")
            view = view[written:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _read_file_at(directory_fd: int, name: str, *, max_bytes: int) -> bytes:
    descriptor = _open_readonly(name, dir_fd=directory_fd)
    try:
        node = os.fstat(descriptor)
        if not stat.S_ISREG(node.st_mode) or node.st_size > max_bytes:
            raise CacheIntegrityError(f"cache file is not a bounded regular file: {name}")
        chunks: list[bytes] = []
        remaining = node.st_size
        while remaining:
            chunk = os.read(descriptor, min(_COPY_CHUNK, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        if (
            remaining
            or os.read(descriptor, 1)
            or _identity(os.fstat(descriptor)) != _identity(node)
        ):
            raise CacheIntegrityError(f"cache file changed while reading: {name}")
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def _hash_fd_exact(descriptor: int, expected_size: int) -> tuple[str, int]:
    try:
        with os.fdopen(os.dup(descriptor), "rb") as stream:
            return _hash_stream(stream, expected_size=expected_size)
    except SafetyError as err:
        raise CacheIntegrityError("cache member length changed while reading") from err


def _validate_cached_member(member: object) -> CachedMember:
    if not isinstance(member, dict):
        raise CacheIntegrityError("cache member record is invalid")
    name, stored_name, size, digest = (
        member.get("name"),
        member.get("stored_name"),
        member.get("size"),
        member.get("sha256"),
    )
    if (
        not isinstance(name, str)
        or PurePosixPath(name).name != name
        or not name.lower().endswith(_APK_SUFFIX)
    ):
        raise CacheIntegrityError("cache logical member name is invalid")
    if (
        not isinstance(stored_name, str)
        or PurePosixPath(stored_name).name != stored_name
        or "\\" in stored_name
    ):
        raise CacheIntegrityError("cache stored member path is unsafe")
    if type(size) is not int or size < 0:
        raise CacheIntegrityError("cache member size is invalid")
    if not isinstance(digest, str) or not _is_sha256(digest):
        raise CacheIntegrityError("cache member digest is invalid")
    if set(member) != {"name", "stored_name", "size", "sha256"}:
        raise CacheIntegrityError("cache member record has unexpected fields")
    return cast(CachedMember, member)


class ArtifactCache:
    """Byte-only objects with mutable processing status stored separately."""

    def __init__(self, root: Path | str, *, limits: PreflightLimits | None = None) -> None:
        self.root = Path(root)
        self.limits = limits or PreflightLimits()

    def _object(self, digest: str) -> Path:
        if not _is_sha256(digest):
            raise PreflightError("invalid artifact digest")
        return self.root / "objects" / CACHE_SCHEMA / digest

    def store(self, result: PreflightResult) -> Path:
        """Atomically store sealed bytes regardless of provisional routing state."""
        if not result.artifact_members:
            raise PreflightError("artifact cache requires at least one sealed APK member")
        self.root.mkdir(parents=True, exist_ok=True)
        _fsync_directory(self.root.parent)
        objects = self.root / "objects"
        objects.mkdir(exist_ok=True)
        schema_objects = objects / CACHE_SCHEMA
        schema_objects.mkdir(exist_ok=True)
        _fsync_directory(self.root)
        _fsync_directory(objects)
        _fsync_directory(schema_objects)
        destination = self._object(result.artifact_digest)
        if destination.exists() or destination.is_symlink():
            self.verify(result.artifact_digest)
            return destination
        temporary = Path(
            tempfile.mkdtemp(prefix=f".{result.artifact_digest}.tmp-", dir=schema_objects)
        )
        published = False
        try:
            members_path = temporary / "members"
            members_path.mkdir(mode=0o700)
            members_fd = os.open(members_path, _DIRECTORY_FLAGS)
            try:
                records: list[CachedMember] = []
                for index, member in enumerate(result.artifact_members):
                    stored_name = f"{index:04d}-{member.sha256}.apk"
                    source_fd = _open_readonly(member._sealed_path)
                    try:
                        target_fd = os.open(
                            stored_name,
                            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0),
                            0o600,
                            dir_fd=members_fd,
                        )
                        try:
                            source_stat = os.fstat(source_fd)
                            if (
                                not stat.S_ISREG(source_stat.st_mode)
                                or source_stat.st_size != member.size
                            ):
                                raise SafetyError(
                                    f"sealed artifact member is unavailable: {member.name}"
                                )
                            digest, size = _copy_fd_exact(
                                source_fd, target_fd, expected_size=member.size
                            )
                            os.fsync(target_fd)
                        finally:
                            os.close(target_fd)
                    finally:
                        os.close(source_fd)
                    if (digest, size) != (member.sha256, member.size):
                        raise SafetyError(f"sealed artifact member changed: {member.name}")
                    records.append(
                        {
                            "name": member.name,
                            "stored_name": stored_name,
                            "size": member.size,
                            "sha256": member.sha256,
                        }
                    )
                os.fsync(members_fd)
            finally:
                os.close(members_fd)
            manifest: CacheManifest = {
                "schema": CACHE_SCHEMA,
                "artifact_digest": result.artifact_digest,
                "members": records,
            }
            temporary_fd = os.open(temporary, _DIRECTORY_FLAGS)
            try:
                manifest_bytes = _canonical_json(manifest)
                _write_file_at(temporary_fd, "manifest.json", manifest_bytes)
                manifest_sha = hashlib.sha256(manifest_bytes).hexdigest()
                _write_file_at(
                    temporary_fd, "OBJECT.COMPLETE", f"{manifest_sha}  manifest.json\n".encode()
                )
                os.fsync(temporary_fd)
            finally:
                os.close(temporary_fd)
            try:
                _rename_noreplace(temporary, destination)
                published = True
                _fsync_directory(schema_objects)
            except FileExistsError:
                self.verify(result.artifact_digest)
                return destination
        finally:
            if not published:
                shutil.rmtree(temporary, ignore_errors=True)
        self.verify(result.artifact_digest)
        return destination

    def verify(self, artifact_digest: str) -> CacheManifest:
        object_path = self._object(artifact_digest)
        try:
            object_fd = os.open(object_path, _DIRECTORY_FLAGS)
        except OSError as err:
            raise CacheIntegrityError(f"cache object is missing: {artifact_digest}") from err
        try:
            object_identity = _identity(os.fstat(object_fd))
            expected_object_names = {"OBJECT.COMPLETE", "manifest.json", "members"}
            if set(os.listdir(object_fd)) != expected_object_names:
                raise CacheIntegrityError("cache object contains unexpected payloads")
            marker = _read_file_at(object_fd, "OBJECT.COMPLETE", max_bytes=256)
            try:
                expected_manifest, target = marker.decode().strip().split(maxsplit=1)
            except (UnicodeError, ValueError) as err:
                raise CacheIntegrityError("cache completion marker is invalid") from err
            if target != "manifest.json" or not _is_sha256(expected_manifest):
                raise CacheIntegrityError("cache completion marker is invalid")
            manifest_bytes = _read_file_at(
                object_fd, "manifest.json", max_bytes=_MAX_CACHE_MANIFEST_BYTES
            )
            if hashlib.sha256(manifest_bytes).hexdigest() != expected_manifest:
                raise CacheIntegrityError("cache manifest seal mismatch")
            try:
                raw = json.loads(
                    manifest_bytes,
                    object_pairs_hook=_cache_object,
                    parse_constant=_reject_cache_constant,
                )
            except (UnicodeError, ValueError, json.JSONDecodeError, RecursionError) as err:
                raise CacheIntegrityError("cache manifest is invalid") from err
            if not isinstance(raw, dict) or set(raw) != {
                "schema",
                "artifact_digest",
                "members",
            }:
                raise CacheIntegrityError("cache manifest is invalid")
            if raw.get("schema") != CACHE_SCHEMA or raw.get("artifact_digest") != artifact_digest:
                raise CacheIntegrityError("cache artifact identity mismatch")
            raw_members = raw.get("members")
            if not isinstance(raw_members, list):
                raise CacheIntegrityError("cache member manifest is invalid")
            members = [_validate_cached_member(member) for member in raw_members]
            if any(member["size"] > self.limits.max_member_bytes for member in members):
                raise CacheIntegrityError("cache member exceeds the configured size limit")
            try:
                members_fd = os.open("members", _DIRECTORY_FLAGS, dir_fd=object_fd)
            except OSError as err:
                raise CacheIntegrityError("cache member directory is missing or unsafe") from err
            try:
                members_identity = _identity(os.fstat(members_fd))
                expected_names = [member["stored_name"] for member in members]
                if len(set(expected_names)) != len(expected_names) or set(
                    os.listdir(members_fd)
                ) != set(expected_names):
                    raise CacheIntegrityError("cache member directory payload set is invalid")
                logical: list[dict[str, object]] = []
                for member in members:
                    try:
                        descriptor = _open_readonly(member["stored_name"], dir_fd=members_fd)
                    except OSError as err:
                        raise CacheIntegrityError("cache member is missing or unsafe") from err
                    try:
                        node = os.fstat(descriptor)
                        if not stat.S_ISREG(node.st_mode) or node.st_size != member["size"]:
                            raise CacheIntegrityError("cache member size or type mismatch")
                        digest, size = _hash_fd_exact(descriptor, member["size"])
                        if _identity(os.fstat(descriptor)) != _identity(node):
                            raise CacheIntegrityError("cache member changed while verifying")
                    finally:
                        os.close(descriptor)
                    if (digest, size) != (member["sha256"], member["size"]):
                        raise CacheIntegrityError("cache member integrity mismatch")
                    logical.append(
                        {"name": member["name"], "size": member["size"], "sha256": member["sha256"]}
                    )
                if _digest_manifest("artifact", logical) != artifact_digest:
                    raise CacheIntegrityError("cache logical artifact digest mismatch")
                if _identity(os.fstat(members_fd)) != members_identity or set(
                    os.listdir(members_fd)
                ) != set(expected_names):
                    raise CacheIntegrityError("cache member directory changed while verifying")
            finally:
                os.close(members_fd)
            if (
                _identity(os.fstat(object_fd)) != object_identity
                or set(os.listdir(object_fd)) != expected_object_names
            ):
                raise CacheIntegrityError("cache object changed while verifying")
            return cast(CacheManifest, raw)
        finally:
            os.close(object_fd)

    def write_status(
        self,
        artifact_digest: str,
        status: Literal["READY", "BLOCKED", "FAILED", "COMPLETE"],
        *,
        pipeline_revision: str,
        detail: str | None = None,
    ) -> Path:
        self.verify(artifact_digest)
        if _STATUS_REVISION.fullmatch(pipeline_revision) is None:
            raise PreflightError("pipeline revision must be a stable path-safe identifier")
        status_root = self.root / "status"
        status_root.mkdir(exist_ok=True)
        status_dir = status_root / pipeline_revision
        status_dir.mkdir(exist_ok=True)
        _fsync_directory(self.root)
        _fsync_directory(status_root)
        status_fd = os.open(status_dir, _DIRECTORY_FLAGS)
        fcntl.flock(status_fd, fcntl.LOCK_EX)
        target_name = f"{artifact_digest}.json"
        try:
            try:
                previous = _read_file_at(status_fd, target_name, max_bytes=1024 * 1024)
            except FileNotFoundError:
                previous = None
            current: str | None = None
            if previous is not None:
                try:
                    decoded = json.loads(
                        previous,
                        object_pairs_hook=_cache_object,
                        parse_constant=_reject_cache_constant,
                    )
                except (UnicodeError, ValueError, json.JSONDecodeError, RecursionError) as err:
                    raise CacheIntegrityError("existing cache status is invalid") from err
                if (
                    not isinstance(decoded, dict)
                    or set(decoded) != {"artifact_digest", "pipeline_revision", "status", "detail"}
                    or decoded.get("artifact_digest") != artifact_digest
                    or decoded.get("pipeline_revision") != pipeline_revision
                ):
                    raise CacheIntegrityError("existing cache status is invalid")
                current_value = decoded.get("status")
                if not isinstance(current_value, str):
                    raise CacheIntegrityError("existing cache status is invalid")
                current = current_value
            transitions: dict[str | None, set[str]] = {
                None: {"READY", "BLOCKED"},
                "BLOCKED": {"BLOCKED", "READY"},
                "READY": {"READY", "BLOCKED", "FAILED", "COMPLETE"},
                "FAILED": set(),
                "COMPLETE": set(),
            }
            if status not in transitions.get(current, set()):
                raise PreflightError(f"invalid cache status transition: {current!r} -> {status}")
            payload = _canonical_json(
                {
                    "artifact_digest": artifact_digest,
                    "pipeline_revision": pipeline_revision,
                    "status": status,
                    "detail": detail,
                }
            )
            if len(payload) > 1024 * 1024:
                raise PreflightError("cache status payload exceeds the size limit")
            temporary_name = f".{artifact_digest}.{os.getpid()}.{id(payload)}.tmp"
            try:
                _write_file_at(status_fd, temporary_name, payload)
                os.replace(
                    temporary_name,
                    target_name,
                    src_dir_fd=status_fd,
                    dst_dir_fd=status_fd,
                )
                os.fsync(status_fd)
            finally:
                try:
                    os.unlink(temporary_name, dir_fd=status_fd)
                except FileNotFoundError:
                    pass
        finally:
            os.close(status_fd)
        return status_dir / target_name

    def materialize(self, artifact_digest: str, destination: Path | str) -> Path:
        manifest = self.verify(artifact_digest)
        target = Path(os.path.abspath(os.fspath(destination)))
        try:
            parent = target.parent.resolve(strict=True)
        except OSError as err:
            raise PreflightError(
                f"materialization parent is inaccessible: {target.parent}"
            ) from err
        target = parent / target.name
        if target.exists() or target.is_symlink():
            raise PreflightError(f"materialization destination already exists: {target}")
        temporary = Path(tempfile.mkdtemp(prefix=f".{target.name}.tmp-", dir=parent))
        published = False
        object_fd = -1
        members_fd = -1
        destination_fd = -1
        try:
            object_fd = os.open(self._object(artifact_digest), _DIRECTORY_FLAGS)
            members_fd = os.open("members", _DIRECTORY_FLAGS, dir_fd=object_fd)
            destination_fd = os.open(temporary, _DIRECTORY_FLAGS)
            for member in manifest["members"]:
                source_fd = _open_readonly(member["stored_name"], dir_fd=members_fd)
                try:
                    copied_fd = os.open(
                        member["stored_name"],
                        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0),
                        0o600,
                        dir_fd=destination_fd,
                    )
                    try:
                        source_stat = os.fstat(source_fd)
                        if (
                            not stat.S_ISREG(source_stat.st_mode)
                            or source_stat.st_size != member["size"]
                        ):
                            raise CacheIntegrityError("cache member size or type changed")
                        try:
                            digest, size = _copy_fd_exact(
                                source_fd, copied_fd, expected_size=member["size"]
                            )
                        except SafetyError as err:
                            raise CacheIntegrityError(
                                "cache member changed while materializing"
                            ) from err
                        os.fsync(copied_fd)
                        copied_stat = os.fstat(copied_fd)
                        if (source_stat.st_dev, source_stat.st_ino) == (
                            copied_stat.st_dev,
                            copied_stat.st_ino,
                        ):
                            raise CacheIntegrityError(
                                "materialization unexpectedly created a hardlink"
                            )
                    finally:
                        os.close(copied_fd)
                finally:
                    os.close(source_fd)
                if (digest, size) != (member["sha256"], member["size"]):
                    raise CacheIntegrityError("materialized member integrity mismatch")
            _write_file_at(
                destination_fd, "MATERIALIZED.COMPLETE", f"{artifact_digest}  artifact\n".encode()
            )
            os.fsync(destination_fd)
            os.close(destination_fd)
            destination_fd = -1
            os.close(members_fd)
            members_fd = -1
            os.close(object_fd)
            object_fd = -1
            _rename_noreplace(temporary, target)
            published = True
            _fsync_directory(parent)
        finally:
            if destination_fd >= 0:
                os.close(destination_fd)
            if members_fd >= 0:
                os.close(members_fd)
            if object_fd >= 0:
                os.close(object_fd)
            if not published:
                shutil.rmtree(temporary, ignore_errors=True)
        return target
