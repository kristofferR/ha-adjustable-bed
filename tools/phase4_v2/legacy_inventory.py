"""Create a deterministic, read-only inventory of legacy Phase 4 workspaces.

The source tree is never opened for writing. Output is first built in a sibling
temporary directory, then published into a newly created destination outside
the source tree one payload at a time. The completion marker is moved last;
an interrupted publication may leave a partial destination without that marker.
"""

from __future__ import annotations

import argparse
import errno
import hashlib
import json
import os
import re
import shutil
import stat
import tempfile
from collections import Counter
from collections.abc import Buffer, Collection, Iterator, Sequence
from dataclasses import asdict, dataclass, field
from itertools import islice
from pathlib import Path, PurePosixPath
from typing import BinaryIO, Protocol

MANIFEST_SCHEMA = "phase4-v2-legacy-inventory-v1"
SCANNER_VERSION = "1"
_CLUSTER = re.compile(r"cluster-\d+", re.IGNORECASE)
_SHA256SUM = re.compile(r"^([0-9a-fA-F]{64})(?:\s+[*]?(.+?))?\s*$")
_BSD_SHA256 = re.compile(r"^SHA256 \((.+)\) = ([0-9a-fA-F]{64})$")
_HASH_MANIFEST_NAMES = frozenset({"sha256sums", "sha256sum"})
_MAX_ANALYSIS_JSON_BYTES = 16 * 1024**2
_MAX_HASH_MANIFEST_BYTES = 16 * 1024**2
_MAX_HASH_MANIFEST_DIAGNOSTICS = 4_096
_MAX_HASH_MANIFEST_DECLARATIONS = 4_096
_MAX_TREE_ENTRIES = 250_000


class InventoryError(RuntimeError):
    """Raised when an inventory cannot be created safely."""


class SourceTreeChangedError(InventoryError):
    """Raised when stable source metadata changes during inventory creation."""


class ObservedFileChangedError(InventoryError):
    """Raised when a file changes between discovery and a content read."""


class _Hash(Protocol):
    def update(self, data: Buffer, /) -> None: ...

    def hexdigest(self) -> str: ...


@dataclass(frozen=True, slots=True)
class Entry:
    """One filesystem node, captured without following symlinks."""

    path: str
    kind: str
    size: int
    mode: str
    uid: int
    gid: int
    mtime_ns: int
    ctime_ns: int
    device: int
    inode: int
    link_target: str | None
    workspace: str | None
    cluster: str | None
    package_ids: tuple[str, ...]
    roles: tuple[str, ...]
    active_protected: bool

    def to_json(self) -> str:
        """Return the canonical NDJSON representation."""
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))


@dataclass(frozen=True, slots=True)
class Diagnostic:
    """A historical irregularity observed without attempting repair."""

    path: str
    operation: str
    error: str
    active_protected: bool

    def to_json(self) -> str:
        """Return the canonical NDJSON representation."""
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))


@dataclass(frozen=True, slots=True)
class DeclaredHash:
    """A hash claim copied from an existing manifest, not recalculated."""

    manifest_path: str
    line: int
    algorithm: str
    digest: str
    target: str | None
    verification: str
    actual_digest: str | None
    resolved_target: str | None
    active_protected: bool

    def to_json(self) -> str:
        """Return the canonical NDJSON representation."""
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))


@dataclass(frozen=True, slots=True)
class ReportRecord:
    """Selected protocol-neutral metadata from an observed analysis report."""

    path: str
    status: str | None
    schema_revision: str | None
    package_id: str | None
    version_name: str | None
    version_code: str | None
    artifact_set_sha256: str | None
    package_ids: tuple[str, ...]
    workspace: str | None
    cluster: str | None
    roles: tuple[str, ...]
    active_protected: bool

    def to_json(self) -> str:
        """Return the canonical NDJSON representation."""
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))


@dataclass(frozen=True, slots=True)
class WorkspaceRecord:
    """Join record that gives every entry package and cluster provenance."""

    path: str
    entries: int
    regular_file_bytes: int
    package_ids: tuple[str, ...]
    clusters: tuple[str, ...]
    report_paths: tuple[str, ...]
    report_statuses: tuple[str, ...]
    schema_revisions: tuple[str, ...]
    roles: tuple[str, ...]
    active_protected: bool

    def to_json(self) -> str:
        """Return the canonical NDJSON representation."""
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))


@dataclass(slots=True)
class _WorkspaceState:
    entries: int = 0
    regular_file_bytes: int = 0
    package_ids: set[str] = field(default_factory=set)
    clusters: set[str] = field(default_factory=set)
    report_paths: list[str] = field(default_factory=list)
    report_statuses: set[str] = field(default_factory=set)
    schema_revisions: set[str] = field(default_factory=set)
    roles: set[str] = field(default_factory=set)
    active_protected: bool = False


@dataclass(frozen=True, slots=True)
class TreeSnapshot:
    """A metadata-only snapshot used to detect mutations during a scan."""

    stable_digest: str
    stable_entries: int
    stable_bytes: int
    observed_digest: str
    observed_entries: int
    observed_bytes: int


@dataclass(frozen=True, slots=True)
class InventorySummary:
    """Result returned after an inventory is safely published."""

    output_dir: Path
    snapshot: TreeSnapshot
    reports: int
    declared_hashes: int
    diagnostics: int
    coverage_status: str
    completion_marker: str


@dataclass(slots=True)
class _ScanState:
    stable_hash: _Hash
    observed_hash: _Hash
    stable_entries: int = 0
    stable_bytes: int = 0
    observed_entries: int = 0
    observed_bytes: int = 0

    @classmethod
    def create(cls) -> _ScanState:
        return cls(stable_hash=hashlib.sha256(), observed_hash=hashlib.sha256())

    def add(self, entry: Entry, payload: str | None = None) -> None:
        encoded = ((payload or entry.to_json()) + "\n").encode()
        self.observed_hash.update(encoded)
        self.observed_entries += 1
        self.observed_bytes += entry.size if entry.kind == "file" else 0
        if not entry.active_protected:
            self.stable_hash.update(encoded)
            self.stable_entries += 1
            self.stable_bytes += entry.size if entry.kind == "file" else 0

    def snapshot(self) -> TreeSnapshot:
        return TreeSnapshot(
            stable_digest=self.stable_hash.hexdigest(),
            stable_entries=self.stable_entries,
            stable_bytes=self.stable_bytes,
            observed_digest=self.observed_hash.hexdigest(),
            observed_entries=self.observed_entries,
            observed_bytes=self.observed_bytes,
        )


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


def _roles(path: PurePosixPath) -> tuple[str, ...]:
    text_parts = tuple(part.lower() for part in path.parts)
    roles: set[str] = set()
    tokens = {token for part in text_parts for token in re.split(r"[^a-z0-9]+", part) if token}
    for role in ("rejected", "failed", "repair", "audit", "reconciliation", "handoff"):
        if role in tokens:
            roles.add(role)
    if "acceptance" in tokens:
        roles.add("acceptance")
    if any(part in {"report", "final-report", "final_report"} for part in text_parts):
        roles.add("report")
    if "input" in tokens:
        roles.add("input")
    if "work" in tokens:
        roles.add("work")
    name = text_parts[-1] if text_parts else ""
    if _is_hash_manifest_name(name):
        roles.add("frozen_manifest")
    return tuple(sorted(roles))


def _is_active(path: PurePosixPath, active_paths: tuple[PurePosixPath, ...]) -> bool:
    return any(path == active or active in path.parents for active in active_paths)


def _cluster(path: PurePosixPath) -> str | None:
    return next((part for part in path.parts if _CLUSTER.fullmatch(part)), None)


def _entry_from_stat(
    relative: PurePosixPath,
    node_stat: os.stat_result,
    link_target: str | None,
    active_paths: tuple[PurePosixPath, ...],
) -> Entry:
    return Entry(
        path=relative.as_posix(),
        kind=_kind(node_stat.st_mode),
        size=node_stat.st_size,
        mode=f"{stat.S_IMODE(node_stat.st_mode):04o}",
        uid=node_stat.st_uid,
        gid=node_stat.st_gid,
        mtime_ns=node_stat.st_mtime_ns,
        ctime_ns=node_stat.st_ctime_ns,
        device=node_stat.st_dev,
        inode=node_stat.st_ino,
        link_target=link_target,
        workspace=(
            None
            if relative == PurePosixPath(".")
            or (len(relative.parts) == 1 and not stat.S_ISDIR(node_stat.st_mode))
            else relative.parts[0]
        ),
        cluster=_cluster(relative),
        package_ids=(),
        roles=_roles(relative),
        active_protected=_is_active(relative, active_paths),
    )


def _normalise_active_paths(paths: Collection[Path | str]) -> tuple[PurePosixPath, ...]:
    normalised: set[PurePosixPath] = set()
    for supplied in paths:
        raw = Path(supplied)
        if raw.is_absolute():
            raise InventoryError(f"active path must be relative to the source root: {raw}")
        candidate = PurePosixPath(raw.as_posix())
        if candidate == PurePosixPath(".") or ".." in candidate.parts:
            raise InventoryError(f"invalid active path: {raw}")
        normalised.add(candidate)
    return tuple(sorted(normalised, key=PurePosixPath.as_posix))


def _resolve_source_root(source_root: Path) -> Path:
    try:
        root = source_root.resolve(strict=True)
    except OSError as err:
        raise InventoryError(f"source root is not accessible: {source_root}") from err
    if not root.is_dir():
        raise InventoryError(f"source root is not a directory: {root}")
    return root


def _validate_active_paths(source_root: Path, active_paths: tuple[PurePosixPath, ...]) -> None:
    for active in active_paths:
        current = source_root
        for component in active.parts:
            current /= component
            try:
                node_stat = current.lstat()
            except OSError as err:
                raise InventoryError(
                    f"active path does not exist or is inaccessible: {active.as_posix()}"
                ) from err
            if stat.S_ISLNK(node_stat.st_mode):
                raise InventoryError(f"active path traverses a symlink: {active.as_posix()}")
        active_stat = current.lstat()
        if not stat.S_ISDIR(active_stat.st_mode):
            raise InventoryError(f"active path is not a directory: {active.as_posix()}")


def _walk(
    source_root: Path,
    active_paths: tuple[PurePosixPath, ...],
    diagnostics: list[Diagnostic],
) -> Iterator[tuple[Entry, Path]]:
    """Yield nodes in canonical order without following symlinks."""
    try:
        root_stat = source_root.lstat()
    except OSError as err:
        raise InventoryError(f"cannot stat source root {source_root}: {err}") from err
    root_entry = _entry_from_stat(PurePosixPath("."), root_stat, None, active_paths)
    yield root_entry, source_root
    remaining_entries = max(_MAX_TREE_ENTRIES - 1, 0)

    directory_flags = (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_NONBLOCK", 0)
    )

    def descend(
        directory_fd: int,
        directory: Path,
        relative_dir: PurePosixPath,
    ) -> Iterator[tuple[Entry, Path]]:
        nonlocal remaining_entries
        try:
            with os.scandir(directory_fd) as scan:
                children = list(islice(scan, remaining_entries + 1))
        except OSError as err:
            diagnostics.append(
                Diagnostic(
                    path=relative_dir.as_posix(),
                    operation="scandir",
                    error=f"{type(err).__name__}:{err.errno}",
                    active_protected=_is_active(relative_dir, active_paths),
                )
            )
            return
        if len(children) > remaining_entries:
            diagnostics.append(
                Diagnostic(
                    path=relative_dir.as_posix(),
                    operation="scandir",
                    error="entry_limit_exceeded",
                    active_protected=_is_active(relative_dir, active_paths),
                )
            )
            children.pop()
        remaining_entries -= len(children)
        children.sort(key=lambda child: child.name)
        for child in children:
            relative = (
                relative_dir / child.name if relative_dir.parts else PurePosixPath(child.name)
            )
            child_path = directory / child.name
            try:
                node_stat = child.stat(follow_symlinks=False)
                link_target = (
                    os.readlink(child.name, dir_fd=directory_fd)
                    if stat.S_ISLNK(node_stat.st_mode)
                    else None
                )
            except OSError as err:
                diagnostics.append(
                    Diagnostic(
                        path=relative.as_posix(),
                        operation="lstat",
                        error=f"{type(err).__name__}:{err.errno}",
                        active_protected=_is_active(relative, active_paths),
                    )
                )
                continue
            entry = _entry_from_stat(relative, node_stat, link_target, active_paths)
            yield entry, child_path
            if entry.kind == "directory":
                child_fd = -1
                try:
                    child_fd = os.open(child.name, directory_flags, dir_fd=directory_fd)
                    opened_stat = os.fstat(child_fd)
                    if (
                        not stat.S_ISDIR(opened_stat.st_mode)
                        or (opened_stat.st_dev, opened_stat.st_ino)
                        != (node_stat.st_dev, node_stat.st_ino)
                    ):
                        raise ObservedFileChangedError(
                            f"observed directory identity changed: {relative.as_posix()}"
                        )
                    yield from descend(child_fd, child_path, relative)
                except (OSError, ObservedFileChangedError) as err:
                    diagnostics.append(
                        Diagnostic(
                            path=relative.as_posix(),
                            operation="scandir",
                            error=f"{type(err).__name__}:{getattr(err, 'errno', None)}",
                            active_protected=_is_active(relative, active_paths),
                        )
                    )
                finally:
                    if child_fd >= 0:
                        os.close(child_fd)

    root_fd = -1
    try:
        root_fd = os.open(source_root, directory_flags)
        opened_root = os.fstat(root_fd)
        if (opened_root.st_dev, opened_root.st_ino) != (root_stat.st_dev, root_stat.st_ino):
            raise InventoryError(f"source root changed while opening: {source_root}")
        yield from descend(root_fd, source_root, PurePosixPath())
    except OSError as err:
        raise InventoryError(f"cannot open source root {source_root}: {err}") from err
    finally:
        if root_fd >= 0:
            os.close(root_fd)


def capture_tree_snapshot(
    source_root: Path,
    *,
    active_paths: Collection[Path | str] = (),
) -> TreeSnapshot:
    """Capture deterministic metadata for mutation detection."""
    root = _resolve_source_root(source_root)
    active = _normalise_active_paths(active_paths)
    state = _ScanState.create()
    diagnostics: list[Diagnostic] = []
    for entry, _ in _walk(root, active, diagnostics):
        state.add(entry)
    _add_stable_diagnostics(state, diagnostics)
    return state.snapshot()


def _add_stable_diagnostics(state: _ScanState, diagnostics: Collection[Diagnostic]) -> None:
    for diagnostic in sorted(diagnostics, key=lambda item: (item.path, item.operation, item.error)):
        if not diagnostic.active_protected:
            state.stable_hash.update((diagnostic.to_json() + "\n").encode())


def verify_unchanged(before: TreeSnapshot, after: TreeSnapshot) -> None:
    """Require equality for all source nodes outside active protected paths."""
    before_stable = (before.stable_digest, before.stable_entries, before.stable_bytes)
    after_stable = (after.stable_digest, after.stable_entries, after.stable_bytes)
    if before_stable != after_stable:
        raise SourceTreeChangedError(
            "source tree changed during inventory outside active protected paths"
        )


def _string(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _identifier(value: object) -> str | None:
    if isinstance(value, str | int):
        return str(value)
    return None


def _collect_named_strings(value: object, key: str) -> tuple[str, ...]:
    found: set[str] = set()
    stack = [value]
    while stack:
        current = stack.pop()
        if isinstance(current, dict):
            candidate = current.get(key)
            if isinstance(candidate, str):
                found.add(candidate)
            stack.extend(current.values())
        elif isinstance(current, list):
            stack.extend(current)
    return tuple(sorted(found))


def _open_observed_descriptor(entry: Entry, path: Path) -> int:
    noatime = getattr(os, "O_NOATIME", 0)
    flags = (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_NONBLOCK", 0)
        | noatime
    )
    try:
        descriptor = os.open(path, flags)
    except OSError as err:
        if not noatime or err.errno != errno.EPERM:
            raise
        descriptor = os.open(path, flags & ~noatime)
    try:
        opened_stat = os.fstat(descriptor)
        if not _matches_observed_entry(opened_stat, entry):
            raise ObservedFileChangedError(f"observed file identity changed: {entry.path}")
    except BaseException:
        os.close(descriptor)
        raise
    return descriptor


def _matches_observed_entry(node: os.stat_result, entry: Entry) -> bool:
    return stat.S_ISREG(node.st_mode) and (
        node.st_dev,
        node.st_ino,
        node.st_size,
        node.st_mtime_ns,
        node.st_ctime_ns,
    ) == (
        entry.device,
        entry.inode,
        entry.size,
        entry.mtime_ns,
        entry.ctime_ns,
    )


def _open_observed_binary(entry: Entry, path: Path) -> BinaryIO:
    return os.fdopen(_open_observed_descriptor(entry, path), "rb")


def _report_record(entry: Entry, path: Path) -> ReportRecord:
    if entry.size > _MAX_ANALYSIS_JSON_BYTES:
        raise ValueError("analysis.json exceeds the metadata parsing limit")
    with _open_observed_binary(entry, path) as report_file:
        payload = report_file.read(_MAX_ANALYSIS_JSON_BYTES + 1)
    if len(payload) > _MAX_ANALYSIS_JSON_BYTES:
        raise ValueError("analysis.json exceeds the metadata parsing limit")
    document = json.loads(payload, object_pairs_hook=_reject_duplicate_json_keys)
    if not isinstance(document, dict):
        raise ValueError("top-level JSON value is not an object")
    artifact = document.get("artifact")
    artifact_dict = artifact if isinstance(artifact, dict) else {}
    status = _string(document.get("status"))
    report_roles = set(entry.roles)
    if status == "COMPLETE":
        report_roles.add("accepted")
    elif status in {"PARTIAL", "BLOCKED"}:
        report_roles.add(status.lower())
    return ReportRecord(
        path=entry.path,
        status=status,
        schema_revision=_string(document.get("schema_revision")),
        package_id=_string(artifact_dict.get("package_id")),
        version_name=_string(artifact_dict.get("version_name")),
        version_code=_identifier(artifact_dict.get("version_code")),
        artifact_set_sha256=_string(artifact_dict.get("artifact_set_sha256")),
        package_ids=_collect_named_strings(document, "package_id"),
        workspace=entry.workspace,
        cluster=entry.cluster,
        roles=tuple(sorted(report_roles)),
        active_protected=entry.active_protected,
    )


def _reject_duplicate_json_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    document: dict[str, object] = {}
    for key, value in pairs:
        if key in document:
            raise ValueError(f"duplicate JSON key: {key}")
        document[key] = value
    return document


def _is_hash_manifest_name(name: str) -> bool:
    lowered = name.lower()
    return lowered.endswith(".sha256") or lowered in _HASH_MANIFEST_NAMES


def _is_hash_manifest(path: Path) -> bool:
    return _is_hash_manifest_name(path.name)


def _safe_declared_target(source_root: Path, candidate: Path) -> Path:
    if not candidate.is_relative_to(source_root):
        raise ValueError("outside_source")
    if candidate == source_root:
        raise ValueError("non_regular_target")
    current = source_root
    for component in candidate.relative_to(source_root).parts:
        current /= component
        node_stat = current.lstat()
        if stat.S_ISLNK(node_stat.st_mode):
            raise ValueError("symlink_target")
    target_stat = candidate.lstat()
    if not stat.S_ISREG(target_stat.st_mode):
        raise ValueError("non_regular_target")
    return candidate


def _verify_declared_hash(
    source_root: Path,
    manifest: Path,
    target: str | None,
    declared: str,
    digest_cache: dict[tuple[int, int, int, int, int], str],
) -> tuple[str, str | None, str | None]:
    if target is None:
        return "no_target", None, None
    supplied = Path(target)
    if supplied.is_absolute():
        return "absolute_target", None, None

    manifest_relative = manifest.relative_to(source_root)
    bases = [manifest.parent]
    if len(manifest_relative.parts) > 1:
        bases.append(source_root / manifest_relative.parts[0])
    bases.append(source_root)
    candidates = tuple(dict.fromkeys(Path(os.path.abspath(base / supplied)) for base in bases))
    errors: list[str] = []
    mismatches: list[tuple[str, str]] = []
    for candidate in candidates:
        try:
            safe_candidate = _safe_declared_target(source_root, candidate)
            before = safe_candidate.lstat()
            cache_key = (
                before.st_dev,
                before.st_ino,
                before.st_size,
                before.st_mtime_ns,
                before.st_ctime_ns,
            )
            cached_digest = digest_cache.get(cache_key)
            if cached_digest is not None:
                resolved = safe_candidate.relative_to(source_root).as_posix()
                if cached_digest == declared.lower():
                    return "match", cached_digest, resolved
                mismatches.append((cached_digest, resolved))
                continue
            target_entry = _entry_from_stat(
                PurePosixPath(safe_candidate.relative_to(source_root).as_posix()), before, None, ()
            )
            digest = hashlib.sha256()
            with _open_observed_binary(target_entry, safe_candidate) as target_file:
                for chunk in iter(lambda: target_file.read(1024 * 1024), b""):
                    digest.update(chunk)
            after = safe_candidate.lstat()
            if (
                before.st_dev,
                before.st_ino,
                before.st_size,
                before.st_mtime_ns,
                before.st_ctime_ns,
            ) != (
                after.st_dev,
                after.st_ino,
                after.st_size,
                after.st_mtime_ns,
                after.st_ctime_ns,
            ):
                errors.append("changed_during_read")
                continue
            digest_cache[cache_key] = digest.hexdigest()
        except FileNotFoundError:
            errors.append("missing_target")
            continue
        except PermissionError:
            errors.append("unreadable_target")
            continue
        except OSError as err:
            errors.append(f"filesystem_error:{type(err).__name__}")
            continue
        except ObservedFileChangedError:
            errors.append("changed_during_read")
            continue
        except ValueError as err:
            errors.append(str(err))
            continue
        actual = digest.hexdigest()
        resolved = safe_candidate.relative_to(source_root).as_posix()
        if actual == declared.lower():
            return "match", actual, resolved
        mismatches.append((actual, resolved))

    if mismatches:
        actual, resolved = mismatches[0]
        return "mismatch", actual, resolved
    error = next((item for item in errors if item != "missing_target"), "missing_target")
    return error, None, None


def _declared_hashes(
    entry: Entry,
    path: Path,
    source_root: Path,
    digest_cache: dict[tuple[int, int, int, int, int], str],
) -> tuple[list[DeclaredHash], list[Diagnostic]]:
    if entry.size > _MAX_HASH_MANIFEST_BYTES:
        return [], [
            Diagnostic(
                path=entry.path,
                operation="read_declared_hashes",
                error="manifest_too_large",
                active_protected=entry.active_protected,
            )
        ]
    try:
        with _open_observed_binary(entry, path) as manifest_file:
            payload = manifest_file.read(_MAX_HASH_MANIFEST_BYTES + 1)
            if len(payload) != entry.size:
                raise ObservedFileChangedError(
                    f"observed file size changed while reading: {entry.path}"
                )
            text = payload.decode("utf-8")
            result = _parse_declared_hash_lines(
                text,
                entry,
                path,
                source_root,
                digest_cache,
            )
            if not _matches_observed_entry(os.fstat(manifest_file.fileno()), entry):
                raise ObservedFileChangedError(
                    f"observed file metadata changed while reading: {entry.path}"
                )
            return result
    except (OSError, UnicodeError, ObservedFileChangedError) as err:
        return [], [
            Diagnostic(
                path=entry.path,
                operation="read_declared_hashes",
                error="OSError" if isinstance(err, OSError) else type(err).__name__,
                active_protected=entry.active_protected,
            )
        ]


def _parse_declared_hash_lines(
    text: str,
    entry: Entry,
    path: Path,
    source_root: Path,
    digest_cache: dict[tuple[int, int, int, int, int], str],
) -> tuple[list[DeclaredHash], list[Diagnostic]]:
    declarations: list[DeclaredHash] = []
    diagnostics: list[Diagnostic] = []
    line_start = 0
    line_number = 0
    while line_start < len(text):
        line_number += 1
        if len(diagnostics) >= _MAX_HASH_MANIFEST_DIAGNOSTICS - 1:
            diagnostics.append(
                Diagnostic(
                    path=entry.path,
                    operation="parse_declared_hashes",
                    error="diagnostic_limit_exceeded",
                    active_protected=entry.active_protected,
                )
            )
            break
        line_end = text.find("\n", line_start)
        if line_end < 0:
            line = text[line_start:]
            line_start = len(text)
        else:
            line = text[line_start:line_end]
            line_start = line_end + 1
        if line.endswith("\r"):
            line = line[:-1]
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = _SHA256SUM.fullmatch(stripped)
        if match:
            digest, target = match.groups()
        else:
            bsd_match = _BSD_SHA256.fullmatch(stripped)
            if not bsd_match:
                diagnostics.append(
                    Diagnostic(
                        path=entry.path,
                        operation=f"parse_declared_hash_line:{line_number}",
                        error="unrecognised_format",
                        active_protected=entry.active_protected,
                    )
                )
                continue
            target, digest = bsd_match.groups()
        if len(declarations) >= _MAX_HASH_MANIFEST_DECLARATIONS:
            diagnostics.append(
                Diagnostic(
                    path=entry.path,
                    operation="parse_declared_hashes",
                    error="declaration_limit_exceeded",
                    active_protected=entry.active_protected,
                )
            )
            break
        verification, actual_digest, resolved_target = _verify_declared_hash(
            source_root, path, target, digest, digest_cache
        )
        declarations.append(
            DeclaredHash(
                manifest_path=entry.path,
                line=line_number,
                algorithm="sha256",
                digest=digest.lower(),
                target=target,
                verification=verification,
                actual_digest=actual_digest,
                resolved_target=resolved_target,
                active_protected=entry.active_protected,
            )
        )
        if verification not in {"match", "no_target"}:
            diagnostics.append(
                Diagnostic(
                    path=entry.path,
                    operation=f"verify_declared_hash_line:{line_number}",
                    error=verification,
                    active_protected=entry.active_protected,
                )
            )
    return declarations, diagnostics


def _validate_output(source_root: Path, output_dir: Path) -> Path:
    if output_dir.exists() or output_dir.is_symlink():
        raise InventoryError(f"output directory already exists: {output_dir}")
    try:
        parent = output_dir.parent.resolve(strict=True)
    except OSError as err:
        raise InventoryError(
            f"output parent directory is not accessible: {output_dir.parent}"
        ) from err
    candidate = parent / output_dir.name
    if candidate == source_root or candidate.is_relative_to(source_root):
        raise InventoryError("output directory must be outside the source tree")
    if source_root.is_relative_to(candidate):
        raise InventoryError("output directory must not contain the source tree")
    return candidate


def _publish_without_replace(temp_dir: Path, destination: Path) -> None:
    """Publish into a newly created directory without replacing any existing path."""
    try:
        destination.mkdir()
    except FileExistsError as err:
        raise InventoryError(f"output directory appeared during scan: {destination}") from err
    try:
        destination_descriptor = os.open(
            destination,
            os.O_RDONLY
            | os.O_DIRECTORY
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0),
        )
    except OSError as err:
        raise InventoryError(
            f"new output directory could not be pinned safely: {destination}"
        ) from err
    if not _directory_descriptor_matches_path(destination_descriptor, destination):
        os.close(destination_descriptor)
        raise InventoryError(f"new output directory changed before publication: {destination}")
    children = sorted(
        temp_dir.iterdir(), key=lambda path: (path.name.startswith("INVENTORY."), path.name)
    )
    try:
        marker = next((child for child in children if child.name.startswith("INVENTORY.")), None)
        payloads = [child for child in children if child != marker]
        for child in payloads:
            _fsync_path(child)
            os.rename(child, child.name, dst_dir_fd=destination_descriptor)
        os.fsync(destination_descriptor)
        if not _directory_descriptor_matches_path(destination_descriptor, destination):
            raise InventoryError(f"output directory changed during publication: {destination}")
        if marker is not None:
            _fsync_path(marker)
            os.rename(marker, marker.name, dst_dir_fd=destination_descriptor)
            os.fsync(destination_descriptor)
        if not _directory_descriptor_matches_path(destination_descriptor, destination):
            raise InventoryError(f"output directory changed during publication: {destination}")
        _fsync_directory(destination.parent)
        temp_dir.rmdir()
    except OSError as err:
        raise InventoryError(
            f"publication was interrupted; incomplete output retained at {destination}"
        ) from err
    finally:
        os.close(destination_descriptor)


def _directory_descriptor_matches_path(descriptor: int, path: Path) -> bool:
    opened = os.fstat(descriptor)
    try:
        current = path.lstat()
    except OSError:
        return False
    return stat.S_ISDIR(current.st_mode) and (opened.st_dev, opened.st_ino) == (
        current.st_dev,
        current.st_ino,
    )


def _fsync_path(path: Path) -> None:
    with path.open("rb") as file:
        os.fsync(file.fileno())


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _attach_package_provenance(
    raw_entries: Path,
    entries: Path,
    workspaces: dict[str, _WorkspaceState],
    reports: Collection[ReportRecord],
) -> None:
    prefix_packages: dict[PurePosixPath, set[str]] = {}
    report_container_names = {"report", "final-report", "final_report", "reconciliation"}
    for report in reports:
        packages = set(report.package_ids)
        if report.package_id:
            packages.add(report.package_id)
        if not packages:
            continue
        report_parent = PurePosixPath(report.path).parent
        prefix = (
            report_parent.parent
            if report_parent.name.lower() in report_container_names
            else report_parent
        )
        prefix_packages.setdefault(prefix, set()).update(packages)
    with (
        raw_entries.open("r", encoding="utf-8") as source,
        entries.open("w", encoding="utf-8", newline="\n") as destination,
    ):
        for line in source:
            record = json.loads(line)
            if not isinstance(record, dict):
                raise InventoryError("internal entry stream is malformed")
            workspace = record.get("workspace")
            state = workspaces.get(workspace) if isinstance(workspace, str) else None
            path = record.get("path")
            relative = PurePosixPath(path) if isinstance(path, str) else PurePosixPath(".")
            nearest = next(
                (
                    prefix_packages[ancestor]
                    for ancestor in (relative, *relative.parents)
                    if ancestor in prefix_packages
                ),
                None,
            )
            record["package_ids"] = sorted(nearest or (state.package_ids if state else set()))
            destination.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")


def _payload_record(path: Path) -> dict[str, object]:
    digest = hashlib.sha256()
    with path.open("rb") as payload:
        for chunk in iter(lambda: payload.read(1024 * 1024), b""):
            digest.update(chunk)
    return {"bytes": path.stat().st_size, "sha256": digest.hexdigest()}


def _update_workspace_entry(
    workspaces: dict[str, _WorkspaceState],
    entry: Entry,
) -> None:
    if entry.workspace is None:
        return
    workspace = workspaces.setdefault(entry.workspace, _WorkspaceState())
    workspace.entries += 1
    if entry.kind == "file":
        workspace.regular_file_bytes += entry.size
    if entry.cluster:
        workspace.clusters.add(entry.cluster)
    workspace.roles.update(entry.roles)
    workspace.active_protected |= entry.active_protected


def _update_workspace_report(
    workspaces: dict[str, _WorkspaceState],
    report: ReportRecord,
) -> None:
    if report.workspace is None:
        return
    workspace = workspaces.setdefault(report.workspace, _WorkspaceState())
    workspace.package_ids.update(report.package_ids)
    if report.package_id:
        workspace.package_ids.add(report.package_id)
    if report.cluster:
        workspace.clusters.add(report.cluster)
    workspace.report_paths.append(report.path)
    workspace.report_statuses.add(report.status or "UNKNOWN")
    if report.schema_revision:
        workspace.schema_revisions.add(report.schema_revision)
    workspace.roles.update(report.roles)


def _workspace_record(path: str, state: _WorkspaceState) -> WorkspaceRecord:
    return WorkspaceRecord(
        path=path,
        entries=state.entries,
        regular_file_bytes=state.regular_file_bytes,
        package_ids=tuple(sorted(state.package_ids)),
        clusters=tuple(sorted(state.clusters)),
        report_paths=tuple(sorted(state.report_paths)),
        report_statuses=tuple(sorted(state.report_statuses)),
        schema_revisions=tuple(sorted(state.schema_revisions)),
        roles=tuple(sorted(state.roles)),
        active_protected=state.active_protected,
    )


def _duplicate_report_groups(reports: Collection[ReportRecord]) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str, str, str], list[ReportRecord]] = {}
    for report in reports:
        identity = (
            report.package_id or "",
            report.version_name or "",
            report.version_code or "",
            report.artifact_set_sha256 or "",
        )
        if not identity[0] or not identity[3]:
            continue
        grouped.setdefault(identity, []).append(report)
    duplicates: list[dict[str, object]] = []
    for identity, members in sorted(grouped.items()):
        workspaces = {member.workspace for member in members}
        if len(members) < 2 or len(workspaces) < 2:
            continue
        duplicates.append(
            {
                "package_id": identity[0],
                "version_name": identity[1],
                "version_code": identity[2],
                "artifact_set_sha256": identity[3],
                "report_paths": sorted(member.path for member in members),
                "classification": "duplicate_identity_possible_stale_history",
            }
        )
    return duplicates


def _human_summary(manifest: dict[str, object]) -> str:
    counts = manifest["counts"]
    audit = manifest["non_mutation_audit"]
    coverage = manifest["coverage"]
    active = manifest["active_protected_paths"]
    assert isinstance(counts, dict)
    assert isinstance(audit, dict)
    assert isinstance(coverage, dict)
    assert isinstance(active, list)
    role_lines = "\n".join(f"- {role}: {count}" for role, count in sorted(counts["roles"].items()))
    status_lines = "\n".join(
        f"- {status}: {count}" for status, count in sorted(counts["report_statuses"].items())
    )
    active_lines = "\n".join(f"- `{path}`" for path in active) or "- None"
    return f"""# Phase 4 legacy preservation inventory

- Schema: `{manifest["schema"]}`
- Source: `{manifest["source_root"]}`
- Scan mode: metadata only, symlinks not followed
- Filesystem entries: {counts["entries"]}
- Regular-file bytes observed: {counts["regular_file_bytes"]}
- Analysis reports: {counts["reports"]}
- Workspaces: {counts["workspaces"]}
- Duplicate identity groups: {counts["duplicate_report_groups"]}
- Existing SHA-256 declarations: {counts["declared_hashes"]}
- Diagnostics retained: {counts["diagnostics"]}
- Traversal coverage: {coverage["status"]} ({coverage["opaque_paths"]} opaque paths)

## Non-mutation audit

- Stable entries before: {audit["stable_entries_before"]}
- Stable entries after: {audit["stable_entries_after"]}
- Stable digest before: `{audit["stable_digest_before"]}`
- Stable digest after: `{audit["stable_digest_after"]}`
- Stable result: **UNCHANGED**
- Full observed-tree result: **{audit["observed_result"]}**

Active protected paths are inventoried but excluded from the equality gate because another
approved workflow may be writing them concurrently. This inventory never writes to the source.
The full-tree result reports whether those active paths changed during the scan. Opaque paths are
retained in `diagnostics.ndjson`; they are never chmodded or otherwise opened up by this tool.

## Active protected paths

{active_lines}

## Observed roles

{role_lines or "- None"}

## Report statuses

{status_lines or "- None"}
"""


def build_inventory(
    source_root: Path,
    output_dir: Path,
    *,
    active_paths: Collection[Path | str] = (),
) -> InventorySummary:
    """Build an inventory and publish its completion marker last to a new destination."""
    root = _resolve_source_root(source_root)
    active = _normalise_active_paths(active_paths)
    _validate_active_paths(root, active)
    destination = _validate_output(root, output_dir)

    temp_dir = Path(tempfile.mkdtemp(prefix=f".{destination.name}.tmp-", dir=destination.parent))
    raw_entries_path = temp_dir / "entries.raw.ndjson"
    entries_path = temp_dir / "entries.ndjson"
    hashes_path = temp_dir / "declared_hashes.ndjson"
    reports_path = temp_dir / "reports.ndjson"
    workspaces_path = temp_dir / "workspaces.ndjson"
    duplicates_path = temp_dir / "duplicate_reports.ndjson"
    diagnostics_path = temp_dir / "diagnostics.ndjson"

    state = _ScanState.create()
    diagnostics: list[Diagnostic] = []
    traversal_diagnostics: list[Diagnostic] = []
    role_counts: Counter[str] = Counter()
    kind_counts: Counter[str] = Counter()
    status_counts: Counter[str] = Counter()
    hash_verification_counts: Counter[str] = Counter()
    workspace_states: dict[str, _WorkspaceState] = {}
    report_records: list[ReportRecord] = []
    digest_cache: dict[tuple[int, int, int, int, int], str] = {}
    report_count = 0
    hash_count = 0
    try:
        with (
            raw_entries_path.open("w", encoding="utf-8", newline="\n") as entries_file,
            hashes_path.open("w", encoding="utf-8", newline="\n") as hashes_file,
            reports_path.open("w", encoding="utf-8", newline="\n") as reports_file,
        ):
            for entry, absolute_path in _walk(root, active, traversal_diagnostics):
                payload = entry.to_json()
                entries_file.write(payload + "\n")
                state.add(entry, payload)
                _update_workspace_entry(workspace_states, entry)
                kind_counts[entry.kind] += 1
                role_counts.update(entry.roles)
                if entry.kind != "file":
                    continue
                if absolute_path.name == "analysis.json":
                    try:
                        record = _report_record(entry, absolute_path)
                    except (
                        OSError,
                        RecursionError,
                        UnicodeError,
                        ValueError,
                        ObservedFileChangedError,
                    ) as err:
                        diagnostics.append(
                            Diagnostic(
                                path=entry.path,
                                operation="parse_analysis_json",
                                error=(
                                    "OSError" if isinstance(err, OSError) else type(err).__name__
                                ),
                                active_protected=entry.active_protected,
                            )
                        )
                    else:
                        reports_file.write(record.to_json() + "\n")
                        report_records.append(record)
                        _update_workspace_report(workspace_states, record)
                        role_counts.update(set(record.roles).difference(entry.roles))
                        report_count += 1
                        status_counts[record.status or "UNKNOWN"] += 1
                if _is_hash_manifest(absolute_path):
                    declarations, hash_diagnostics = _declared_hashes(
                        entry, absolute_path, root, digest_cache
                    )
                    for declaration in declarations:
                        hashes_file.write(declaration.to_json() + "\n")
                        hash_verification_counts[declaration.verification] += 1
                    hash_count += len(declarations)
                    diagnostics.extend(hash_diagnostics)

        _add_stable_diagnostics(state, traversal_diagnostics)
        diagnostics.extend(traversal_diagnostics)
        before = state.snapshot()
        after = capture_tree_snapshot(root, active_paths=[path.as_posix() for path in active])
        verify_unchanged(before, after)

        duplicate_groups = _duplicate_report_groups(report_records)
        for group_number, group in enumerate(duplicate_groups, start=1):
            report_paths = group["report_paths"]
            assert isinstance(report_paths, list)
            for report_path in report_paths:
                assert isinstance(report_path, str)
                diagnostics.append(
                    Diagnostic(
                        path=report_path,
                        operation=f"duplicate_report_identity:{group_number}",
                        error="possible_stale_history",
                        active_protected=any(
                            report.path == report_path and report.active_protected
                            for report in report_records
                        ),
                    )
                )

        with workspaces_path.open("w", encoding="utf-8", newline="\n") as workspaces_file:
            for workspace_path, workspace_state in sorted(workspace_states.items()):
                workspaces_file.write(
                    _workspace_record(workspace_path, workspace_state).to_json() + "\n"
                )
        with duplicates_path.open("w", encoding="utf-8", newline="\n") as duplicates_file:
            for group in duplicate_groups:
                duplicates_file.write(
                    json.dumps(group, sort_keys=True, separators=(",", ":")) + "\n"
                )
        _attach_package_provenance(raw_entries_path, entries_path, workspace_states, report_records)
        raw_entries_path.unlink()

        ordered_diagnostics = sorted(
            diagnostics, key=lambda item: (item.path, item.operation, item.error)
        )
        with diagnostics_path.open("w", encoding="utf-8", newline="\n") as diagnostics_file:
            for diagnostic in ordered_diagnostics:
                diagnostics_file.write(diagnostic.to_json() + "\n")

        observed_before = (
            before.observed_digest,
            before.observed_entries,
            before.observed_bytes,
        )
        observed_after = (
            after.observed_digest,
            after.observed_entries,
            after.observed_bytes,
        )
        observed_unchanged = observed_before == observed_after
        opaque_paths = {
            diagnostic.path
            for diagnostic in traversal_diagnostics
            if diagnostic.operation in {"scandir", "lstat"}
        }
        opaque_paths.update(
            diagnostic.path
            for diagnostic in diagnostics
            if (
                diagnostic.operation in {"parse_analysis_json", "read_declared_hashes"}
                and diagnostic.error
                in {"OSError", "PermissionError", "ObservedFileChangedError"}
            )
            or (
                diagnostic.operation.startswith("verify_declared_hash_line:")
                and (
                    diagnostic.error == "unreadable_target"
                    or diagnostic.error.startswith("filesystem_error:")
                )
            )
        )
        manifest: dict[str, object] = {
            "schema": MANIFEST_SCHEMA,
            "scanner_version": SCANNER_VERSION,
            "source_root": str(root),
            "scan_mode": "metadata_only",
            "ordering": "depth_first_with_lexically_sorted_siblings",
            "symlink_policy": "record_without_following",
            "active_protected_paths": [path.as_posix() for path in active],
            "counts": {
                "entries": before.observed_entries,
                "regular_file_bytes": before.observed_bytes,
                "kinds": dict(sorted(kind_counts.items())),
                "roles": dict(sorted(role_counts.items())),
                "reports": report_count,
                "workspaces": len(workspace_states),
                "duplicate_report_groups": len(duplicate_groups),
                "report_statuses": dict(sorted(status_counts.items())),
                "declared_hashes": hash_count,
                "declared_hash_verification": dict(sorted(hash_verification_counts.items())),
                "diagnostics": len(ordered_diagnostics),
            },
            "coverage": {
                "status": "COMPLETE" if not opaque_paths else "OPAQUE_PATHS_RECORDED",
                "opaque_paths": len(opaque_paths),
                "opaque_path_list": sorted(opaque_paths),
            },
            "non_mutation_audit": {
                "active_paths_excluded_from_equality": True,
                "stable_digest_before": before.stable_digest,
                "stable_digest_after": after.stable_digest,
                "stable_entries_before": before.stable_entries,
                "stable_entries_after": after.stable_entries,
                "stable_bytes_before": before.stable_bytes,
                "stable_bytes_after": after.stable_bytes,
                "stable_unchanged": True,
                "observed_digest_before": before.observed_digest,
                "observed_digest_after": after.observed_digest,
                "observed_entries_before": before.observed_entries,
                "observed_entries_after": after.observed_entries,
                "observed_unchanged": observed_unchanged,
                "observed_result": "UNCHANGED" if observed_unchanged else "ACTIVE_PATHS_CHANGED",
            },
            "files": {
                "entries": "entries.ndjson",
                "declared_hashes": "declared_hashes.ndjson",
                "reports": "reports.ndjson",
                "workspaces": "workspaces.ndjson",
                "duplicate_reports": "duplicate_reports.ndjson",
                "diagnostics": "diagnostics.ndjson",
                "human_summary": "SUMMARY.md",
            },
        }
        (temp_dir / "SUMMARY.md").write_text(_human_summary(manifest), encoding="utf-8")
        payload_names = (
            "entries.ndjson",
            "declared_hashes.ndjson",
            "reports.ndjson",
            "workspaces.ndjson",
            "duplicate_reports.ndjson",
            "diagnostics.ndjson",
            "SUMMARY.md",
        )
        manifest["payload_integrity"] = {
            name: _payload_record(temp_dir / name) for name in payload_names
        }
        _write_json(temp_dir / "manifest.json", manifest)
        manifest_digest = hashlib.sha256((temp_dir / "manifest.json").read_bytes()).hexdigest()
        completion_marker = "INVENTORY.COMPLETE" if not opaque_paths else "INVENTORY.PARTIAL"
        (temp_dir / completion_marker).write_text(
            f"{manifest_digest}  manifest.json\n", encoding="utf-8"
        )
        _publish_without_replace(temp_dir, destination)
    except BaseException:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise

    return InventorySummary(
        output_dir=destination,
        snapshot=before,
        reports=report_count,
        declared_hashes=hash_count,
        diagnostics=len(ordered_diagnostics),
        coverage_status="COMPLETE" if not opaque_paths else "OPAQUE_PATHS_RECORDED",
        completion_marker=completion_marker,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_root", type=Path, help="legacy tree to scan read-only")
    parser.add_argument("output_dir", type=Path, help="new output directory outside source_root")
    parser.add_argument(
        "--active-path",
        action="append",
        default=[],
        type=Path,
        help="relative subtree to inventory but exclude from the mutation equality gate",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the legacy inventory CLI."""
    args = _parser().parse_args(argv)
    try:
        result = build_inventory(
            args.source_root,
            args.output_dir,
            active_paths=args.active_path,
        )
    except InventoryError as err:
        raise SystemExit(f"inventory failed: {err}") from err
    print(
        f"Inventory written to {result.output_dir} "
        f"({result.snapshot.observed_entries} entries, {result.reports} reports; "
        f"coverage={result.coverage_status}, marker={result.completion_marker})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
