"""Atomic multi-document publication from one queue snapshot."""

from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from .core import Lease, Queue, _TrackerPublicationCheckpointGrant
from .publisher import PublisherConflictError, PublisherPostWriteConflictError
from .tracker import render_html, render_markdown

_REVISION = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
_PATH = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,4095}$")
_MAX_TARGETS = 32
_MAX_DOCUMENT_BYTES = 900 * 1024
_MAX_DOCUMENT_SET_BYTES = 4 * 1024 * 1024


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


class AtomicDocumentSetGateway(Protocol):
    def read(self, paths: tuple[str, ...]) -> TrackerDocumentSet: ...

    def compare_and_replace(
        self,
        *,
        expected_revision: str,
        expected_documents_sha256: str,
        documents: tuple[TrackerDocument, ...],
    ) -> bool: ...


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
    gateway: AtomicDocumentSetGateway,
    targets: tuple[TrackerTarget, ...],
) -> FanoutPublishReceipt:
    """Atomically publish every tracker view from one immutable snapshot."""

    canonical_targets = _targets(targets)
    paths = tuple(item.path for item in canonical_targets)
    config_sha256 = publication_config_sha256(canonical_targets)
    with _publication_guard(queue):
        queue.renew(lease, ttl_seconds=300)
        snapshot = queue.snapshot()
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


def publication_config_sha256(targets: tuple[TrackerTarget, ...]) -> str:
    """Hash the exact canonical path and renderer-format configuration."""

    canonical = _targets(targets)
    payload = json.dumps(
        [[target.path, target.format.value] for target in canonical],
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(b"phase4-v2:tracker-publication-config\0" + payload).hexdigest()


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
    if queue.snapshot().generation_id != generation:
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
