"""Atomic multi-document publication from one queue snapshot."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from enum import StrEnum
from threading import Event, Thread
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .publication_config import TrackerPublicationConfig

from .core import (
    ORCHESTRATION_TRACKER_PUBLICATION_KIND,
    Lease,
    Queue,
    QueueSnapshot,
    _TrackerPublicationCheckpointGrant,
)
from .publisher import PublisherConflictError, PublisherPostWriteConflictError
from .tracker import render_html, render_markdown

_REVISION = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
_PATH = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,4095}$")
_MAX_TARGETS = 32
_MAX_DOCUMENT_BYTES = 900 * 1024
_MAX_DOCUMENT_SET_BYTES = 4 * 1024 * 1024
_MAX_PROTECTED_CONFIG_BYTES = 4 * 1024
_PROTECTED_CONFIG_REVISION = "phase4-v2-publication-config-pin-v1"
_HEARTBEAT_INTERVAL_SECONDS = 60


class TrackerFormat(StrEnum):
    MARKDOWN = "MARKDOWN"
    HTML = "HTML"


@dataclass(frozen=True, slots=True, order=True)
class TrackerTarget:
    path: str
    format: TrackerFormat

    def __post_init__(self) -> None:
        if (
            type(self.path) is not str
            or _PATH.fullmatch(self.path) is None
            or self.path.startswith("/")
            or self.path.endswith("/")
            or "//" in self.path
            or any(part in {".", ".."} for part in self.path.split("/"))
        ):
            raise ValueError("tracker target path must be canonical and relative")
        if type(self.format) is not TrackerFormat:
            raise ValueError("tracker target format must be a TrackerFormat")


@dataclass(frozen=True, slots=True, order=True)
class TrackerDocument:
    path: str
    body: bytes | None

    def __post_init__(self) -> None:
        TrackerTarget(self.path, TrackerFormat.MARKDOWN)
        if self.body is not None and type(self.body) is not bytes:
            raise ValueError("tracker document body must be exact bytes or missing")
        if self.body is not None and len(self.body) > _MAX_DOCUMENT_BYTES:
            raise ValueError("tracker document exceeds its byte limit")


@dataclass(frozen=True, slots=True)
class TrackerDocumentSet:
    revision: str
    documents: tuple[TrackerDocument, ...]

    def __post_init__(self) -> None:
        if type(self.revision) is not str or _REVISION.fullmatch(self.revision) is None:
            raise ValueError("tracker document-set revision is invalid")
        if type(self.documents) is not tuple or any(
            type(item) is not TrackerDocument for item in self.documents
        ):
            raise ValueError("tracker documents must be an exact tuple")
        if len(self.documents) > _MAX_TARGETS:
            raise ValueError("tracker document count exceeds its limit")
        if tuple(sorted(self.documents, key=lambda item: item.path)) != self.documents:
            raise ValueError("tracker documents must be sorted")
        if len({item.path for item in self.documents}) != len(self.documents):
            raise ValueError("tracker document paths must be unique")
        if sum(len(item.body or b"") for item in self.documents) > _MAX_DOCUMENT_SET_BYTES:
            raise ValueError("tracker document set exceeds its byte limit")


@dataclass(frozen=True, slots=True, init=False)
class FanoutPublishReceipt:
    queue_generation: str
    before_revision: str
    after_revision: str
    document_set_sha256: str
    publication_config_sha256: str
    paths: tuple[str, ...]
    changed: bool

    def __init__(self) -> None:
        raise ValueError("fanout receipts are issued only by the atomic publisher")


def publish_tracker_fanout(
    queue: Queue,
    lease: Lease,
    gateway: object,
    config: TrackerPublicationConfig,
) -> FanoutPublishReceipt:
    """Atomically publish every tracker view from one immutable snapshot."""

    from .github_tree import GitHubTreeGateway
    from .publication_config import TrackerPublicationConfig

    if type(config) is not TrackerPublicationConfig:
        raise ValueError("fanout requires an exact tracker publication config")
    if type(gateway) is not GitHubTreeGateway:
        raise PublisherConflictError("fanout requires the sealed GitHub tree gateway")
    if config.sha256 != _load_protected_publication_config_sha256():
        raise PublisherConflictError("publication config does not match protected deployment pin")
    canonical_targets = _targets(config.targets)
    endpoint = (gateway.repository, gateway.branch)
    if endpoint != (config.repository, config.branch):
        raise PublisherConflictError("tracker gateway endpoint does not match publication config")
    paths = tuple(item.path for item in canonical_targets)
    config_sha256 = config.sha256
    with _publication_guard(queue), _publication_heartbeat(queue, lease):
        queue.renew(lease, ttl_seconds=300)
        snapshot = _tracker_projection(queue.snapshot())
        desired = tuple(
            TrackerDocument(
                target.path,
                (
                    render_markdown(snapshot).encode()
                    if target.format is TrackerFormat.MARKDOWN
                    else render_html(snapshot).encode()
                ),
            )
            for target in canonical_targets
        )
        before = gateway.read(paths)
        if tuple(item.path for item in before.documents) != paths:
            raise PublisherConflictError("tracker gateway returned a different target set")
        before_digest = document_set_sha256(before.documents)
        desired_digest = document_set_sha256(desired)
        _require_current(queue, lease, snapshot.generation_id, post_write=False)
        if before.documents == desired:
            grant = object.__new__(_TrackerPublicationCheckpointGrant)
            for name, value in (
                ("lease_id", lease.lease_id),
                ("attempt_id", lease.attempt_id),
                ("event_type", "TRACKER_ALREADY_CURRENT"),
                ("queue_generation", snapshot.generation_id),
                ("publication_config_sha256", config_sha256),
                ("paths", paths),
                ("document_set_sha256", None),
                ("revision", None),
            ):
                object.__setattr__(grant, name, value)
            queue._checkpoint_tracker_publication(
                lease,
                grant,
            )
            _require_current(queue, lease, snapshot.generation_id, post_write=False)
            receipt = object.__new__(FanoutPublishReceipt)
            for name, value in (
                ("queue_generation", snapshot.generation_id),
                ("before_revision", before.revision),
                ("after_revision", before.revision),
                ("document_set_sha256", desired_digest),
                ("publication_config_sha256", config_sha256),
                ("paths", paths),
                ("changed", False),
            ):
                object.__setattr__(receipt, name, value)
            return receipt
        if not gateway.compare_and_replace(
            expected_revision=before.revision,
            expected_documents_sha256=before_digest,
            documents=desired,
        ):
            raise PublisherConflictError("tracker document set changed before publication")
        after = gateway.read(paths)
        if after.documents != desired:
            raise PublisherPostWriteConflictError(
                "tracker set was written but failed exact readback"
            )
        _require_current(queue, lease, snapshot.generation_id, post_write=True)
        try:
            grant = object.__new__(_TrackerPublicationCheckpointGrant)
            for name, value in (
                ("lease_id", lease.lease_id),
                ("attempt_id", lease.attempt_id),
                ("event_type", "TRACKER_PUBLISHED"),
                ("queue_generation", snapshot.generation_id),
                ("publication_config_sha256", config_sha256),
                ("paths", paths),
                ("document_set_sha256", desired_digest),
                ("revision", after.revision),
            ):
                object.__setattr__(grant, name, value)
            queue._checkpoint_tracker_publication(
                lease,
                grant,
            )
        except Exception as error:
            raise PublisherPostWriteConflictError(
                "tracker set was written but its event could not be recorded"
            ) from error
        _require_current(queue, lease, snapshot.generation_id, post_write=True)
        receipt = object.__new__(FanoutPublishReceipt)
        for name, value in (
            ("queue_generation", snapshot.generation_id),
            ("before_revision", before.revision),
            ("after_revision", after.revision),
            ("document_set_sha256", desired_digest),
            ("publication_config_sha256", config_sha256),
            ("paths", paths),
            ("changed", True),
        ):
            object.__setattr__(receipt, name, value)
        return receipt


def load_fanout_publish_receipt(
    raw: bytes,
    *,
    queue: Queue,
    lease: Lease,
    gateway: object,
    config: TrackerPublicationConfig,
) -> FanoutPublishReceipt:
    """Recover CLI output by checking its durable checkpoint and current remote tree."""
    from ..orchestration.completion import _validate_fanout_event

    if type(raw) is not bytes or len(raw) > 64 * 1024:
        raise PublisherConflictError("fanout receipt must be bounded JSON bytes")
    try:
        data = json.loads(raw)
        if json.dumps(data, sort_keys=True, separators=(",", ":")).encode() + b"\n" != raw:
            raise ValueError("noncanonical receipt")
        fields = tuple(FanoutPublishReceipt.__dataclass_fields__)
        if type(data) is not dict or set(data) != {*fields, "publication_config"}:
            raise ValueError("unexpected receipt fields")
        if data["publication_config"] != config.to_data() or type(data["paths"]) is not list:
            raise ValueError("receipt configuration mismatch")
        receipt = object.__new__(FanoutPublishReceipt)
        for name in fields:
            object.__setattr__(receipt, name, tuple(data[name]) if name == "paths" else data[name])
    except (ValueError, TypeError, RecursionError) as error:
        raise PublisherConflictError("invalid serialized fanout receipt") from error
    with _publication_guard(queue), _publication_heartbeat(queue, lease):
        queue.renew(lease, ttl_seconds=300)
        _validate_fanout_event(queue, lease, receipt)
        return _authenticate_tracker_fanout_receipt(queue, gateway, config, receipt)


@contextmanager
def _publication_heartbeat(queue: Queue, lease: Lease) -> Iterator[None]:
    """Keep the lease alive across a bounded series of remote requests."""
    stop = Event()
    errors: list[Exception] = []

    def renew() -> None:
        while not stop.wait(_HEARTBEAT_INTERVAL_SECONDS):
            try:
                queue.renew(lease, ttl_seconds=300)
            except Exception as error:
                errors.append(error)
                return

    thread = Thread(target=renew, daemon=True)
    thread.start()
    try:
        yield
        if errors:
            raise PublisherConflictError("publisher lease renewal failed") from errors[0]
    finally:
        stop.set()
        thread.join()


def _authenticate_tracker_fanout_receipt(
    queue: Queue,
    gateway: object,
    config: TrackerPublicationConfig,
    receipt: FanoutPublishReceipt,
) -> FanoutPublishReceipt:
    """Reauthenticate remote state while the caller holds the publication guard."""

    from .github_tree import GitHubTreeGateway
    from .publication_config import TrackerPublicationConfig

    if type(receipt) is not FanoutPublishReceipt:
        raise PublisherConflictError("publication requires an exact fanout receipt")
    if type(config) is not TrackerPublicationConfig:
        raise PublisherConflictError("publication requires an exact tracker config")
    if type(gateway) is not GitHubTreeGateway:
        raise PublisherConflictError("publication requires the sealed GitHub tree gateway")
    if config.sha256 != _load_protected_publication_config_sha256():
        raise PublisherConflictError("publication config does not match protected deployment pin")
    if (gateway.repository, gateway.branch) != (config.repository, config.branch):
        raise PublisherConflictError("tracker gateway endpoint does not match publication config")
    targets = _targets(config.targets)
    paths = tuple(item.path for item in targets)
    if (
        type(receipt.changed) is not bool
        or receipt.publication_config_sha256 != config.sha256
        or receipt.paths != paths
        or type(receipt.queue_generation) is not str
        or re.fullmatch(r"[0-9a-f]{64}", receipt.queue_generation) is None
        or type(receipt.document_set_sha256) is not str
        or re.fullmatch(r"[0-9a-f]{64}", receipt.document_set_sha256) is None
        or type(receipt.before_revision) is not str
        or _REVISION.fullmatch(receipt.before_revision) is None
        or type(receipt.after_revision) is not str
        or _REVISION.fullmatch(receipt.after_revision) is None
        or (receipt.changed and receipt.before_revision == receipt.after_revision)
        or (not receipt.changed and receipt.before_revision != receipt.after_revision)
    ):
        raise PublisherConflictError("fanout receipt does not match publication configuration")
    snapshot = _tracker_projection(queue.snapshot())
    if snapshot.generation_id != receipt.queue_generation:
        raise PublisherConflictError("fanout receipt belongs to another queue generation")
    desired = tuple(
        TrackerDocument(
            target.path,
            (
                render_markdown(snapshot).encode()
                if target.format is TrackerFormat.MARKDOWN
                else render_html(snapshot).encode()
            ),
        )
        for target in targets
    )
    if document_set_sha256(desired) != receipt.document_set_sha256:
        raise PublisherConflictError("fanout receipt does not bind the current tracker documents")
    remote = gateway.read(paths)
    if remote.revision != receipt.after_revision or remote.documents != desired:
        raise PublisherConflictError("remote tracker tree does not match the fanout receipt")
    if _tracker_projection(queue.snapshot()).generation_id != snapshot.generation_id:
        raise PublisherConflictError("queue changed while reauthenticating tracker publication")
    return receipt


def _tracker_projection(snapshot: QueueSnapshot) -> QueueSnapshot:
    """Remove self-referential publication stages from the published queue state."""

    if type(snapshot) is not QueueSnapshot:
        raise PublisherConflictError("tracker publication requires an exact queue snapshot")
    units = tuple(
        item for item in snapshot.units if item.kind != ORCHESTRATION_TRACKER_PUBLICATION_KIND
    )
    payload = {
        "schema_revision": snapshot.schema_revision,
        # Publication-stage CLAIMED/FINISHED events are self-referential. Unit
        # state and scheduler pins retain every externally meaningful change.
        "event_watermark": 0,
        "scheduler_state_digest": snapshot.scheduler_state_digest,
        "units": [item.as_dict() for item in units],
    }
    generation = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return QueueSnapshot(
        schema_revision=snapshot.schema_revision,
        event_watermark=0,
        scheduler_state_digest=snapshot.scheduler_state_digest,
        generation_id=generation,
        units=units,
    )


def publication_config_sha256(config: TrackerPublicationConfig) -> str:
    """Return the full repository, branch, path, and format commitment."""

    from .publication_config import TrackerPublicationConfig

    if type(config) is not TrackerPublicationConfig:
        raise ValueError("publication config must be an exact TrackerPublicationConfig")
    return config.sha256


def document_set_sha256(documents: tuple[TrackerDocument, ...]) -> str:
    """Bind paths, presence, and exact document bytes into one digest."""

    if type(documents) is not tuple or any(type(item) is not TrackerDocument for item in documents):
        raise ValueError("tracker documents must be an exact tuple")
    if len(documents) > _MAX_TARGETS:
        raise ValueError("tracker document count exceeds its limit")
    canonical = tuple(sorted(documents, key=lambda item: item.path))
    if len({item.path for item in canonical}) != len(canonical):
        raise ValueError("tracker document paths must be unique")
    if sum(len(item.body or b"") for item in canonical) > _MAX_DOCUMENT_SET_BYTES:
        raise ValueError("tracker document set exceeds its byte limit")
    payload = [
        {
            "body_sha256": None if item.body is None else hashlib.sha256(item.body).hexdigest(),
            "path": item.path,
            "present": item.body is not None,
        }
        for item in canonical
    ]
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _targets(targets: tuple[TrackerTarget, ...]) -> tuple[TrackerTarget, ...]:
    if (
        type(targets) is not tuple
        or not targets
        or len(targets) > _MAX_TARGETS
        or any(type(item) is not TrackerTarget for item in targets)
    ):
        raise ValueError("tracker targets must be a non-empty exact tuple")
    canonical = tuple(sorted(targets))
    if canonical != targets or len({item.path for item in targets}) != len(targets):
        raise ValueError("tracker targets must be sorted with unique paths")
    return canonical


def _require_current(queue: Queue, lease: Lease, generation: str, *, post_write: bool) -> None:
    try:
        queue.renew(lease, ttl_seconds=300)
    except Exception as error:
        message = "tracker set was written but publisher lease is stale"
        if post_write:
            raise PublisherPostWriteConflictError(message) from error
        raise PublisherConflictError("publisher lease is stale") from error
    if _tracker_projection(queue.snapshot()).generation_id != generation:
        if post_write:
            raise PublisherPostWriteConflictError(
                "tracker set was written but queue changed during publication"
            )
        raise PublisherConflictError("queue changed before tracker-set publication")


@contextmanager
def _publication_guard(queue: Queue) -> Iterator[None]:
    try:
        descriptor = queue._try_acquire_publication_guard()
    except Exception as error:
        raise PublisherConflictError("publisher guard is unsafe or inaccessible") from error
    if descriptor is None:
        raise PublisherConflictError("another tracker publisher holds the guard")
    try:
        yield
    finally:
        os.close(descriptor)


def _load_protected_publication_config_sha256() -> str:
    """Read the sole deployment-approved publication config digest."""

    directory_flags = (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    try:
        directory = os.open("/etc/ha-adjustable-bed", directory_flags)
    except OSError as error:
        raise PublisherConflictError("protected publication config is unavailable") from error
    try:
        directory_stat = os.fstat(directory)
        if (
            not stat.S_ISDIR(directory_stat.st_mode)
            or directory_stat.st_uid != 0
            or directory_stat.st_mode & 0o022
        ):
            raise PublisherConflictError("protected publication config parent is unsafe")
        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        try:
            descriptor = os.open(
                "phase4-v2-publication-config.pin.json",
                flags,
                dir_fd=directory,
            )
        except OSError as error:
            raise PublisherConflictError("protected publication config is unavailable") from error
        try:
            before = os.fstat(descriptor)
            if (
                not stat.S_ISREG(before.st_mode)
                or before.st_uid != 0
                or before.st_mode & 0o022
                or before.st_nlink != 1
                or before.st_size > _MAX_PROTECTED_CONFIG_BYTES
            ):
                raise PublisherConflictError("protected publication config is unsafe")
            chunks: list[bytes] = []
            remaining = _MAX_PROTECTED_CONFIG_BYTES + 1
            while remaining:
                chunk = os.read(descriptor, min(4096, remaining))
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            after = os.fstat(descriptor)
            raw = b"".join(chunks)
            if (
                _stat_identity(after) != _stat_identity(before)
                or len(raw) != before.st_size
                or len(raw) > _MAX_PROTECTED_CONFIG_BYTES
            ):
                raise PublisherConflictError("protected publication config changed while reading")
        finally:
            os.close(descriptor)
    finally:
        os.close(directory)
    try:
        value = json.loads(raw, object_pairs_hook=_unique_object)
    except (UnicodeError, ValueError, RecursionError) as error:
        raise PublisherConflictError("protected publication config is invalid") from error
    if type(value) is not dict or set(value) != {
        "publication_config_sha256",
        "revision",
    }:
        raise PublisherConflictError("protected publication config has unexpected fields")
    if value["revision"] != _PROTECTED_CONFIG_REVISION:
        raise PublisherConflictError("protected publication config revision is unsupported")
    digest = value["publication_config_sha256"]
    if type(digest) is not str or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
        raise PublisherConflictError("protected publication config digest is invalid")
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":")).encode() + b"\n"
    if raw != canonical:
        raise PublisherConflictError("protected publication config must be canonical JSON")
    return digest


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate JSON object key")
        value[key] = item
    return value


def _stat_identity(metadata: os.stat_result) -> tuple[int, ...]:
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_mode,
        metadata.st_nlink,
        metadata.st_uid,
        metadata.st_gid,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
    )
