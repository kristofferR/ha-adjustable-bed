"""Read-only integrity checks for one frozen Phase 4 report directory.

The validator treats the directory as hostile input. Relative members are opened
through directory file descriptors with ``O_NOFOLLOW`` and no report-local code
is imported or executed.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import stat
from dataclasses import asdict, dataclass, replace
from errno import EFBIG, EIO
from pathlib import Path, PurePosixPath
from typing import cast

from .binding import (
    VALIDATION_INPUT,
    ArtifactIdentityAttestation,
    BindingDiagnostic,
    DependencyPins,
    EvidenceAnchorAttestation,
    EvidenceMemberAttestation,
    PackageDependencyPins,
    validate_binding_contract,
)
from .lineage import EvidenceLineageTrust

VALIDATOR_REVISION = "phase4-v2-bundle-validator-v4"
BOUND_VALIDATION_PROFILE = "BOUND_V4"
PACKAGE_BOUND_VALIDATION_PROFILE = "BOUND_V5"
REPORT_MANIFEST = "REPORT.SHA256"
_MANIFEST_LINE = re.compile(r"^([0-9a-f]{64})  ([^\x00\r\n]+)$")
_READ_SIZE = 1024 * 1024
_MAX_MANIFEST_BYTES = 64 * 1024**2
_MAX_JSON_BYTES = 64 * 1024**2
_MAX_RECEIPT_BYTES = 64 * 1024**2
_MAX_JSON_DEPTH = 128
_MAX_JSON_NODES = 2_000_000
_MIN_JSON_INTEGER = -(2**63)
_MAX_JSON_INTEGER = 2**63 - 1
_MAX_TREE_ENTRIES = 250_000
_MAX_TREE_DEPTH = 128
_MAX_REGULAR_FILE_BYTES = 2 * 1024**3
_MAX_TREE_FILE_BYTES = 16 * 1024**3

type JsonValue = None | bool | int | float | str | list[JsonValue] | dict[str, JsonValue]


class StrictJsonError(ValueError):
    """A JSON document is not strict, unambiguous JSON."""

    def __init__(self, reason: str, *, key: str | None = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.key = key


class _SnapshotError(RuntimeError):
    """A source tree could not be captured consistently."""

    def __init__(self, operation: str, path: str, error: OSError | None = None) -> None:
        super().__init__(operation)
        self.operation = operation
        self.path = path
        self.error = error


@dataclass(frozen=True, slots=True)
class Diagnostic:
    """One deterministic validation failure."""

    code: str
    path: str
    context: tuple[tuple[str, str], ...] = ()

    def to_dict(self) -> dict[str, object]:
        """Return a canonical JSON-compatible representation."""
        result: dict[str, object] = {"code": self.code, "path": self.path}
        if self.context:
            result["context"] = dict(self.context)
        return result


@dataclass(frozen=True, slots=True)
class ValidationReceipt:
    """Content-stable result of validating one report bundle."""

    validator_revision: str
    accepted: bool
    source_unchanged: bool
    bundle_sha256: str | None
    report_manifest_sha256: str | None
    discovered_members: int
    declared_members: int
    diagnostics: tuple[Diagnostic, ...]
    dependency_digests: tuple[tuple[str, str], ...] = ()
    evidence_anchors_checked: int = 0
    validation_profile: str = "FILESYSTEM_ONLY"
    contract_revision: str | None = None
    validated_artifact_identity: ArtifactIdentityAttestation | None = None
    validated_evidence_members: tuple[EvidenceMemberAttestation, ...] = ()
    validated_evidence_anchors: tuple[EvidenceAnchorAttestation, ...] = ()
    validation_receipt_sha256: str | None = None

    def to_dict(self) -> dict[str, object]:
        """Return a canonical JSON-compatible representation."""
        return {
            "accepted": self.accepted,
            "bundle_sha256": self.bundle_sha256,
            "contract_revision": self.contract_revision,
            "declared_members": self.declared_members,
            "dependency_digests": dict(self.dependency_digests),
            "diagnostics": [item.to_dict() for item in self.diagnostics],
            "discovered_members": self.discovered_members,
            "evidence_anchors_checked": self.evidence_anchors_checked,
            "report_manifest_sha256": self.report_manifest_sha256,
            "source_unchanged": self.source_unchanged,
            "validated_artifact_identity": (
                self.validated_artifact_identity.to_dict()
                if self.validated_artifact_identity is not None
                else None
            ),
            "validation_profile": self.validation_profile,
            "validation_receipt_sha256": self.validation_receipt_sha256,
            "validated_evidence_anchors": [
                item.to_dict() for item in self.validated_evidence_anchors
            ],
            "validated_evidence_members": [
                item.to_dict() for item in self.validated_evidence_members
            ],
            "validator_revision": self.validator_revision,
        }

    def to_json(self) -> str:
        """Return the deterministic single-line receipt."""
        return _canonical_receipt_bytes(self.to_dict()).decode("utf-8")

    def identity_payload(self) -> dict[str, object]:
        """Return the exact canonical data covered by the receipt identity."""
        payload = self.to_dict()
        del payload["validation_receipt_sha256"]
        return payload


@dataclass(frozen=True, slots=True)
class _Node:
    path: str
    kind: str
    mode: int
    uid: int
    gid: int
    size: int
    link_count: int
    atime_ns: int
    mtime_ns: int
    ctime_ns: int
    device: int
    inode: int
    sha256: str | None = None
    link_target: str | None = None

    def snapshot_bytes(self) -> bytes:
        return (json.dumps(asdict(self), sort_keys=True, separators=(",", ":")) + "\n").encode()


@dataclass(frozen=True, slots=True)
class _TreeSnapshot:
    nodes: tuple[_Node, ...]
    digest: str


@dataclass(frozen=True, slots=True)
class _ManifestEntry:
    path: str
    sha256: str


@dataclass(slots=True)
class _ScanBudget:
    entries: int = 0
    regular_file_bytes: int = 0

    def observe(self, path: str, kind: str, size: int) -> None:
        self.entries += 1
        if self.entries > _MAX_TREE_ENTRIES:
            raise _SnapshotError("entry_limit_exceeded", path)
        if kind != "file":
            return
        if size > _MAX_REGULAR_FILE_BYTES:
            raise _SnapshotError("file_size_limit_exceeded", path)
        self.regular_file_bytes += size
        if self.regular_file_bytes > _MAX_TREE_FILE_BYTES:
            raise _SnapshotError("tree_size_limit_exceeded", path)


def _duplicate_rejecting_object(pairs: list[tuple[str, JsonValue]]) -> dict[str, JsonValue]:
    result: dict[str, JsonValue] = {}
    for key, value in pairs:
        if key in result:
            raise StrictJsonError("duplicate_key", key=key)
        result[key] = value
    return result


def _reject_constant(value: str) -> JsonValue:
    raise StrictJsonError("non_finite_number", key=value)


def _parse_finite_float(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed):
        raise StrictJsonError("non_finite_number", key=value)
    return parsed


def load_json_strict(data: bytes) -> JsonValue:
    """Decode JSON while rejecting duplicate keys and non-finite numbers."""
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise StrictJsonError("invalid_utf8") from error
    try:
        parsed = cast(
            JsonValue,
            json.loads(
                text,
                object_pairs_hook=_duplicate_rejecting_object,
                parse_constant=_reject_constant,
                parse_float=_parse_finite_float,
            ),
        )
        _validate_json_bounds(parsed)
        return parsed
    except StrictJsonError:
        raise
    except (json.JSONDecodeError, RecursionError, ValueError) as error:
        raise StrictJsonError("invalid_json") from error


def _validate_json_bounds(value: JsonValue) -> None:
    pending: list[tuple[JsonValue, int]] = [(value, 0)]
    nodes = 0
    while pending:
        current, depth = pending.pop()
        nodes += 1
        if nodes > _MAX_JSON_NODES:
            raise StrictJsonError("json_too_large")
        if depth > _MAX_JSON_DEPTH:
            raise StrictJsonError("json_too_deep")
        if isinstance(current, str):
            try:
                current.encode("utf-8")
            except UnicodeEncodeError as error:
                raise StrictJsonError("invalid_unicode") from error
        elif isinstance(current, list):
            pending.extend((item, depth + 1) for item in current)
        elif isinstance(current, dict):
            pending.extend((item, depth + 1) for item in current.values())
            pending.extend((key, depth + 1) for key in current)
        elif type(current) is int and not _MIN_JSON_INTEGER <= current <= _MAX_JSON_INTEGER:
            raise StrictJsonError("integer_out_of_range")


def _kind(mode: int) -> str:
    if stat.S_ISREG(mode):
        return "file"
    if stat.S_ISDIR(mode):
        return "directory"
    if stat.S_ISLNK(mode):
        return "symlink"
    if stat.S_ISFIFO(mode):
        return "fifo"
    if stat.S_ISSOCK(mode):
        return "socket"
    if stat.S_ISCHR(mode):
        return "character_device"
    if stat.S_ISBLK(mode):
        return "block_device"
    return "other"


def _stat_identity(node_stat: os.stat_result) -> tuple[int, ...]:
    return (
        node_stat.st_dev,
        node_stat.st_ino,
        stat.S_IFMT(node_stat.st_mode),
        stat.S_IMODE(node_stat.st_mode),
        node_stat.st_uid,
        node_stat.st_gid,
        node_stat.st_size,
        node_stat.st_nlink,
        node_stat.st_atime_ns,
        node_stat.st_mtime_ns,
        node_stat.st_ctime_ns,
    )


def _node_from_stat(
    relative: str,
    node_stat: os.stat_result,
    *,
    sha256: str | None = None,
    link_target: str | None = None,
) -> _Node:
    return _Node(
        path=relative,
        kind=_kind(node_stat.st_mode),
        mode=stat.S_IMODE(node_stat.st_mode),
        uid=node_stat.st_uid,
        gid=node_stat.st_gid,
        size=node_stat.st_size,
        link_count=node_stat.st_nlink,
        atime_ns=node_stat.st_atime_ns,
        mtime_ns=node_stat.st_mtime_ns,
        ctime_ns=node_stat.st_ctime_ns,
        device=node_stat.st_dev,
        inode=node_stat.st_ino,
        sha256=sha256,
        link_target=link_target,
    )


def _open_root(root: Path) -> int:
    flags = os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOATIME", 0)
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    return os.open(root, flags)


def _hash_regular_at(directory_fd: int, name: str, expected: os.stat_result) -> str:
    flags = os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_NOATIME", 0)
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    file_fd = os.open(name, flags, dir_fd=directory_fd)
    try:
        opened = os.fstat(file_fd)
        if not stat.S_ISREG(opened.st_mode) or _stat_identity(opened) != _stat_identity(expected):
            raise _SnapshotError("file_changed_while_opening", name)
        digest = hashlib.sha256()
        while chunk := os.read(file_fd, _READ_SIZE):
            digest.update(chunk)
        finished = os.fstat(file_fd)
        if _stat_identity(finished) != _stat_identity(opened):
            raise _SnapshotError("file_changed_while_reading", name)
        return digest.hexdigest()
    finally:
        os.close(file_fd)


def _scan_directory(directory_fd: int, prefix: PurePosixPath, budget: _ScanBudget) -> list[_Node]:
    nodes: list[_Node] = []
    try:
        with os.scandir(directory_fd) as iterator:
            entries = sorted(iterator, key=lambda entry: os.fsencode(entry.name))
    except OSError as error:
        relative = prefix.as_posix() if prefix.parts else "."
        raise _SnapshotError("scan_directory", relative, error) from error

    for entry in entries:
        relative_path = prefix / entry.name
        relative = relative_path.as_posix()
        try:
            node_stat = entry.stat(follow_symlinks=False)
        except OSError as error:
            raise _SnapshotError("stat_entry", relative, error) from error
        kind = _kind(node_stat.st_mode)
        if len(relative_path.parts) > _MAX_TREE_DEPTH:
            raise _SnapshotError("depth_limit_exceeded", relative)
        budget.observe(relative, kind, node_stat.st_size)
        if kind == "file":
            try:
                digest = _hash_regular_at(directory_fd, entry.name, node_stat)
            except OSError as error:
                raise _SnapshotError("read_file", relative, error) from error
            nodes.append(_node_from_stat(relative, node_stat, sha256=digest))
        elif kind == "symlink":
            # Symlinks are forbidden, so reading their targets would add no evidence
            # and can itself update symlink atime on Linux.
            nodes.append(_node_from_stat(relative, node_stat))
        elif kind == "directory":
            nodes.append(_node_from_stat(relative, node_stat))
            flags = (
                os.O_RDONLY
                | os.O_DIRECTORY
                | getattr(os, "O_NONBLOCK", 0)
                | getattr(os, "O_NOATIME", 0)
            )
            if hasattr(os, "O_CLOEXEC"):
                flags |= os.O_CLOEXEC
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            try:
                child_fd = os.open(entry.name, flags, dir_fd=directory_fd)
            except OSError as error:
                raise _SnapshotError("open_directory", relative, error) from error
            try:
                opened = os.fstat(child_fd)
                if _stat_identity(opened) != _stat_identity(node_stat):
                    raise _SnapshotError("directory_changed_while_opening", relative)
                nodes.extend(_scan_directory(child_fd, relative_path, budget))
            finally:
                os.close(child_fd)
        else:
            nodes.append(_node_from_stat(relative, node_stat))
    return nodes


def capture_tree_snapshot(root: Path) -> _TreeSnapshot:
    """Capture metadata and file content without following a source symlink."""
    try:
        root_fd = _open_root(root)
    except OSError as error:
        raise _SnapshotError("open_root", ".", error) from error
    try:
        root_stat = os.fstat(root_fd)
        budget = _ScanBudget()
        budget.observe(".", "directory", root_stat.st_size)
        nodes = [_node_from_stat(".", root_stat)]
        nodes.extend(_scan_directory(root_fd, PurePosixPath(), budget))
    finally:
        os.close(root_fd)
    ordered = tuple(sorted(nodes, key=lambda node: os.fsencode(node.path)))
    digest = hashlib.sha256()
    for node in ordered:
        digest.update(node.snapshot_bytes())
    return _TreeSnapshot(nodes=ordered, digest=digest.hexdigest())


def _safe_member_path(raw: str) -> PurePosixPath | None:
    if not raw or "\\" in raw or "\x00" in raw:
        return None
    candidate = PurePosixPath(raw)
    if candidate.is_absolute() or raw != candidate.as_posix():
        return None
    if not candidate.parts or any(part in {"", ".", ".."} for part in candidate.parts):
        return None
    return candidate


def _node_identity(node: _Node) -> tuple[int, ...]:
    return (
        node.device,
        node.inode,
        stat.S_IFMT(_mode_for_kind(node.kind)),
        node.mode,
        node.uid,
        node.gid,
        node.size,
        node.link_count,
        node.atime_ns,
        node.mtime_ns,
        node.ctime_ns,
    )


def _mode_for_kind(kind: str) -> int:
    return {
        "file": stat.S_IFREG,
        "directory": stat.S_IFDIR,
        "symlink": stat.S_IFLNK,
        "fifo": stat.S_IFIFO,
        "socket": stat.S_IFSOCK,
        "character_device": stat.S_IFCHR,
        "block_device": stat.S_IFBLK,
    }.get(kind, 0)


def _assert_opened_node(path: str, opened: os.stat_result, expected: _Node) -> None:
    if _stat_identity(opened) != _node_identity(expected):
        raise OSError(EIO, "member changed since initial snapshot", path)


def _read_member(
    root: Path,
    member: PurePosixPath,
    snapshot_nodes: dict[str, _Node],
    *,
    max_bytes: int,
) -> bytes:
    expected_root = snapshot_nodes["."]
    expected_member = snapshot_nodes.get(member.as_posix())
    if expected_member is None or expected_member.kind != "file":
        raise OSError(EIO, "member is absent or not a snapshotted regular file", member.as_posix())
    if expected_member.size > max_bytes:
        raise OSError(EFBIG, "member exceeds validation read limit", member.as_posix())
    root_fd = _open_root(root)
    current_fd = root_fd
    try:
        _assert_opened_node(".", os.fstat(root_fd), expected_root)
        prefix = PurePosixPath()
        for part in member.parts[:-1]:
            prefix /= part
            expected_directory = snapshot_nodes.get(prefix.as_posix())
            if expected_directory is None or expected_directory.kind != "directory":
                raise OSError(EIO, "directory changed since initial snapshot", prefix.as_posix())
            flags = (
                os.O_RDONLY
                | os.O_DIRECTORY
                | getattr(os, "O_NONBLOCK", 0)
                | getattr(os, "O_NOATIME", 0)
            )
            if hasattr(os, "O_CLOEXEC"):
                flags |= os.O_CLOEXEC
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            next_fd = os.open(part, flags, dir_fd=current_fd)
            if current_fd != root_fd:
                os.close(current_fd)
            current_fd = next_fd
            _assert_opened_node(prefix.as_posix(), os.fstat(current_fd), expected_directory)
        flags = os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_NOATIME", 0)
        if hasattr(os, "O_CLOEXEC"):
            flags |= os.O_CLOEXEC
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        file_fd = os.open(member.parts[-1], flags, dir_fd=current_fd)
        try:
            file_stat = os.fstat(file_fd)
            _assert_opened_node(member.as_posix(), file_stat, expected_member)
            digest = hashlib.sha256()
            data = bytearray()
            remaining = expected_member.size
            while remaining:
                chunk = os.read(file_fd, min(_READ_SIZE, remaining))
                if not chunk:
                    raise OSError(EIO, "member ended before snapshotted size", member.as_posix())
                digest.update(chunk)
                data.extend(chunk)
                remaining -= len(chunk)
            if os.read(file_fd, 1):
                raise OSError(EIO, "member exceeds snapshotted size", member.as_posix())
            _assert_opened_node(member.as_posix(), os.fstat(file_fd), expected_member)
            if digest.hexdigest() != expected_member.sha256:
                raise OSError(
                    EIO, "member digest changed since initial snapshot", member.as_posix()
                )
            return bytes(data)
        finally:
            os.close(file_fd)
    finally:
        if current_fd != root_fd:
            os.close(current_fd)
        os.close(root_fd)


def _read_member_range(
    root: Path,
    member: PurePosixPath,
    snapshot_nodes: dict[str, _Node],
    start: int,
    end: int,
) -> bytes:
    """Read only an exact byte range from a member bound to the first snapshot."""
    expected_root = snapshot_nodes["."]
    expected_member = snapshot_nodes.get(member.as_posix())
    if expected_member is None or expected_member.kind != "file":
        raise OSError(EIO, "member is absent or not a snapshotted regular file", member.as_posix())
    if start < 0 or end <= start or end > expected_member.size:
        raise OSError(EIO, "range is outside snapshotted member", member.as_posix())

    root_fd = _open_root(root)
    current_fd = root_fd
    try:
        _assert_opened_node(".", os.fstat(root_fd), expected_root)
        prefix = PurePosixPath()
        for part in member.parts[:-1]:
            prefix /= part
            expected_directory = snapshot_nodes.get(prefix.as_posix())
            if expected_directory is None or expected_directory.kind != "directory":
                raise OSError(EIO, "directory changed since initial snapshot", prefix.as_posix())
            flags = (
                os.O_RDONLY
                | os.O_DIRECTORY
                | getattr(os, "O_NONBLOCK", 0)
                | getattr(os, "O_NOATIME", 0)
            )
            if hasattr(os, "O_CLOEXEC"):
                flags |= os.O_CLOEXEC
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            next_fd = os.open(part, flags, dir_fd=current_fd)
            if current_fd != root_fd:
                os.close(current_fd)
            current_fd = next_fd
            _assert_opened_node(prefix.as_posix(), os.fstat(current_fd), expected_directory)

        flags = os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_NOATIME", 0)
        if hasattr(os, "O_CLOEXEC"):
            flags |= os.O_CLOEXEC
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        file_fd = os.open(member.parts[-1], flags, dir_fd=current_fd)
        try:
            _assert_opened_node(member.as_posix(), os.fstat(file_fd), expected_member)
            data = bytearray()
            offset = start
            remaining = end - start
            while remaining:
                chunk = os.pread(file_fd, min(_READ_SIZE, remaining), offset)
                if not chunk:
                    raise OSError(EIO, "member ended before requested range", member.as_posix())
                data.extend(chunk)
                offset += len(chunk)
                remaining -= len(chunk)
            _assert_opened_node(member.as_posix(), os.fstat(file_fd), expected_member)
            return bytes(data)
        finally:
            os.close(file_fd)
    finally:
        if current_fd != root_fd:
            os.close(current_fd)
        os.close(root_fd)


def _parse_manifest(data: bytes) -> tuple[list[_ManifestEntry], list[Diagnostic]]:
    diagnostics: list[Diagnostic] = []
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return [], [Diagnostic("MANIFEST_INVALID_UTF8", REPORT_MANIFEST)]
    if not text.endswith("\n"):
        diagnostics.append(Diagnostic("MANIFEST_MISSING_FINAL_NEWLINE", REPORT_MANIFEST))
    entries: list[_ManifestEntry] = []
    seen: set[str] = set()
    for line_number, line in enumerate(text.splitlines(), start=1):
        match = _MANIFEST_LINE.fullmatch(line)
        if match is None:
            diagnostics.append(
                Diagnostic(
                    "MANIFEST_INVALID_LINE",
                    REPORT_MANIFEST,
                    (("line", str(line_number)),),
                )
            )
            continue
        digest, raw_path = match.groups()
        member = _safe_member_path(raw_path)
        if member is None:
            diagnostics.append(Diagnostic("PATH_ESCAPE", raw_path, (("line", str(line_number)),)))
            continue
        canonical = member.as_posix()
        if canonical == REPORT_MANIFEST:
            diagnostics.append(Diagnostic("MANIFEST_SELF_REFERENCE", canonical))
            continue
        if canonical in seen:
            diagnostics.append(Diagnostic("MANIFEST_DUPLICATE_MEMBER", canonical))
            continue
        seen.add(canonical)
        entries.append(_ManifestEntry(path=canonical, sha256=digest))
    return entries, diagnostics


def _diagnostic_for_snapshot(error: _SnapshotError) -> Diagnostic:
    context: tuple[tuple[str, str], ...] = (("operation", error.operation),)
    if error.error is not None and error.error.errno is not None:
        context += (("errno", str(error.error.errno)),)
    return Diagnostic("SOURCE_SNAPSHOT_FAILED", error.path, tuple(sorted(context)))


def _bundle_digest(nodes: dict[str, _Node]) -> str:
    digest = hashlib.sha256()
    for path in sorted(nodes, key=os.fsencode):
        node = nodes[path]
        encoded_path = os.fsencode(path)
        payload = json.dumps(
            {
                "gid": node.gid,
                "kind": node.kind,
                "link_count": node.link_count,
                "link_target": node.link_target,
                "mode": node.mode,
                "sha256": node.sha256,
                "size": node.size,
                "uid": node.uid,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        digest.update(len(encoded_path).to_bytes(8, "big"))
        digest.update(encoded_path)
        digest.update(len(payload).to_bytes(8, "big"))
        digest.update(payload)
    return digest.hexdigest()


def _sorted_diagnostics(diagnostics: list[Diagnostic]) -> tuple[Diagnostic, ...]:
    return tuple(
        sorted(
            set(diagnostics),
            key=lambda item: (item.code, os.fsencode(item.path), item.context),
        )
    )


def _with_receipt_identity(receipt: ValidationReceipt) -> ValidationReceipt:
    payload = _canonical_receipt_bytes(receipt.identity_payload())
    identified = replace(
        receipt,
        validation_receipt_sha256=hashlib.sha256(payload).hexdigest(),
    )
    if (
        not identified.accepted
        or len(_canonical_receipt_bytes(identified.to_dict())) <= _MAX_RECEIPT_BYTES
    ):
        return identified
    compact = replace(
        receipt,
        accepted=False,
        diagnostics=_sorted_diagnostics(
            [*receipt.diagnostics, Diagnostic("RECEIPT_SIZE_LIMIT_EXCEEDED", ".")]
        ),
        evidence_anchors_checked=0,
        validated_evidence_members=(),
        validated_evidence_anchors=(),
        validation_receipt_sha256=None,
    )
    compact_payload = _canonical_receipt_bytes(compact.identity_payload())
    return replace(
        compact,
        validation_receipt_sha256=hashlib.sha256(compact_payload).hexdigest(),
    )


def _canonical_receipt_bytes(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except UnicodeEncodeError:
        # Rejected hostile filesystem names can contain surrogateescaped bytes.
        # Keep their receipts deterministic; accepted BOUND_V4 inputs are strict UTF-8.
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")


def validate_report_bundle(
    report_root: Path,
    *,
    expected_dependencies: DependencyPins | PackageDependencyPins | None = None,
    expected_evidence_lineage: EvidenceLineageTrust | None = None,
    allow_unbound: bool = False,
) -> ValidationReceipt:
    """Validate a report directory without modifying or executing anything in it."""
    validation_profile = _validation_profile(expected_dependencies)
    diagnostics: list[Diagnostic] = []
    try:
        before = capture_tree_snapshot(report_root)
    except _SnapshotError as error:
        diagnostic = _diagnostic_for_snapshot(error)
        return _with_receipt_identity(
            ValidationReceipt(
                validator_revision=VALIDATOR_REVISION,
                accepted=False,
                source_unchanged=False,
                bundle_sha256=None,
                report_manifest_sha256=None,
                discovered_members=0,
                declared_members=0,
                diagnostics=(diagnostic,),
                validation_profile=validation_profile,
            )
        )

    snapshot_nodes = {node.path: node for node in before.nodes}
    nodes = {path: node for path, node in snapshot_nodes.items() if path != "."}
    regular_members = {
        path for path, node in nodes.items() if node.kind == "file" and path != REPORT_MANIFEST
    }
    for path, node in nodes.items():
        if node.kind == "symlink":
            diagnostics.append(Diagnostic("SYMLINK_FORBIDDEN", path))
        elif node.kind not in {"file", "directory"}:
            diagnostics.append(Diagnostic("SPECIAL_NODE_FORBIDDEN", path, (("kind", node.kind),)))
        elif node.kind == "file" and node.link_count != 1:
            diagnostics.append(
                Diagnostic("HARDLINK_FORBIDDEN", path, (("link_count", str(node.link_count)),))
            )

    manifest_node = nodes.get(REPORT_MANIFEST)
    manifest_digest: str | None = None
    manifest_entries: list[_ManifestEntry] = []
    parsed_json: dict[str, JsonValue] = {}
    if manifest_node is None:
        diagnostics.append(Diagnostic("MANIFEST_MISSING", REPORT_MANIFEST))
    elif manifest_node.kind != "file":
        diagnostics.append(
            Diagnostic(
                "MANIFEST_NOT_REGULAR",
                REPORT_MANIFEST,
                (("kind", manifest_node.kind),),
            )
        )
    else:
        manifest_digest = manifest_node.sha256
        try:
            manifest_bytes = _read_member(
                report_root,
                PurePosixPath(REPORT_MANIFEST),
                snapshot_nodes,
                max_bytes=_MAX_MANIFEST_BYTES,
            )
        except OSError as error:
            manifest_context = (("errno", str(error.errno)),) if error.errno is not None else ()
            diagnostics.append(Diagnostic("MANIFEST_UNREADABLE", REPORT_MANIFEST, manifest_context))
        else:
            manifest_entries, manifest_diagnostics = _parse_manifest(manifest_bytes)
            diagnostics.extend(manifest_diagnostics)

    declared = {entry.path: entry for entry in manifest_entries}
    for path in sorted(regular_members - set(declared), key=os.fsencode):
        diagnostics.append(Diagnostic("MEMBER_UNDECLARED", path))
    for path in sorted(set(declared) - set(nodes), key=os.fsencode):
        diagnostics.append(Diagnostic("MEMBER_MISSING", path))
    for path in sorted(set(declared) & set(nodes), key=os.fsencode):
        node = nodes[path]
        if node.kind != "file":
            diagnostics.append(Diagnostic("MEMBER_NOT_REGULAR", path, (("kind", node.kind),)))
            continue
        if node.sha256 != declared[path].sha256:
            diagnostics.append(Diagnostic("MEMBER_DIGEST_MISMATCH", path))

    for path in sorted(regular_members, key=os.fsencode):
        if not path.lower().endswith(".json"):
            continue
        try:
            data = _read_member(
                report_root,
                PurePosixPath(path),
                snapshot_nodes,
                max_bytes=_MAX_JSON_BYTES,
            )
            parsed_json[path] = load_json_strict(data)
        except StrictJsonError as error:
            json_context: tuple[tuple[str, str], ...] = (("reason", error.reason),)
            if error.key is not None:
                json_context += (("key", error.key),)
            diagnostics.append(Diagnostic("JSON_NOT_STRICT", path, tuple(sorted(json_context))))
        except OSError as error:
            member_context = (("errno", str(error.errno)),) if error.errno is not None else ()
            diagnostics.append(Diagnostic("MEMBER_UNREADABLE", path, member_context))

    dependency_digests = (
        expected_dependencies.as_pairs() if expected_dependencies is not None else ()
    )
    evidence_anchors_checked = 0
    contract_revision: str | None = None
    validated_artifact_identity: ArtifactIdentityAttestation | None = None
    validated_evidence_members: tuple[EvidenceMemberAttestation, ...] = ()
    validated_evidence_anchors: tuple[EvidenceAnchorAttestation, ...] = ()
    if expected_dependencies is None:
        if not allow_unbound or VALIDATION_INPUT in nodes:
            diagnostics.append(Diagnostic("DEPENDENCY_PINS_REQUIRED", VALIDATION_INPUT))
    elif VALIDATION_INPUT not in nodes:
        diagnostics.append(Diagnostic("VALIDATION_INPUT_MISSING", VALIDATION_INPUT))
    elif VALIDATION_INPUT not in parsed_json:
        diagnostics.append(Diagnostic("VALIDATION_INPUT_INVALID", VALIDATION_INPUT))
    elif VALIDATION_INPUT in parsed_json:
        binding = validate_binding_contract(
            parsed_json[VALIDATION_INPUT],
            expected_dependencies=expected_dependencies,
            expected_evidence_lineage=expected_evidence_lineage,
            nodes=nodes,
            json_documents=parsed_json,
            path_is_safe=lambda raw: _safe_member_path(raw) is not None,
            read_range=lambda member, start, end: _read_member_range(
                report_root,
                PurePosixPath(member),
                snapshot_nodes,
                start,
                end,
            ),
        )
        diagnostics.extend(_binding_diagnostic(item) for item in binding.diagnostics)
        dependency_digests = binding.dependency_digests
        evidence_anchors_checked = binding.anchors_checked
        contract_revision = binding.contract_revision
        validated_artifact_identity = binding.validated_artifact_identity
        validated_evidence_members = binding.validated_evidence_members
        validated_evidence_anchors = binding.validated_evidence_anchors

    try:
        after = capture_tree_snapshot(report_root)
    except _SnapshotError as error:
        diagnostics.append(_diagnostic_for_snapshot(error))
        source_unchanged = False
    else:
        source_unchanged = before == after
        if not source_unchanged:
            diagnostics.append(Diagnostic("SOURCE_TREE_MUTATED", "."))

    ordered_diagnostics = _sorted_diagnostics(diagnostics)
    return _with_receipt_identity(
        ValidationReceipt(
            validator_revision=VALIDATOR_REVISION,
            accepted=not ordered_diagnostics,
            source_unchanged=source_unchanged,
            bundle_sha256=_bundle_digest(snapshot_nodes),
            report_manifest_sha256=manifest_digest,
            discovered_members=len(regular_members),
            declared_members=len(declared),
            diagnostics=ordered_diagnostics,
            dependency_digests=dependency_digests,
            evidence_anchors_checked=evidence_anchors_checked,
            validation_profile=validation_profile,
            contract_revision=contract_revision,
            validated_artifact_identity=validated_artifact_identity,
            validated_evidence_members=validated_evidence_members,
            validated_evidence_anchors=validated_evidence_anchors,
        )
    )


def _validation_profile(
    expected_dependencies: DependencyPins | PackageDependencyPins | None,
) -> str:
    if isinstance(expected_dependencies, PackageDependencyPins):
        return PACKAGE_BOUND_VALIDATION_PROFILE
    if expected_dependencies is not None:
        return BOUND_VALIDATION_PROFILE
    return "FILESYSTEM_ONLY"


def _binding_diagnostic(item: BindingDiagnostic) -> Diagnostic:
    return Diagnostic(item.code, item.path, item.context)
